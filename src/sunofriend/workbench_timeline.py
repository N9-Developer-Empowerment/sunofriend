"""Path-free, read-only timeline evidence for the local Workbench.

The visual result explorer must make several analytical and AI candidates easy
to compare without turning the display into another ranking system.  This
module therefore projects hash-pinned source audio into a small waveform and
projects the unchanged MIDI files into note rectangles.  It does not render,
edit, merge, select, or promote any candidate.
"""

from __future__ import annotations

import audioop
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import MidiNoteLimitError, read_midi_clips
from .workbench_privacy import path_free_role


WORKBENCH_TIMELINE_SCHEMA = "sunofriend.workbench-timeline.v1"
WORKBENCH_ARRANGEMENT_TIMELINE_SCHEMA = (
    "sunofriend.workbench-arrangement-timeline.v1"
)
WAVEFORM_POLICY = "pcm-wav-min-max-envelope-v1"
MIDI_NOTE_POLICY = "midi-tempo-map-source-seconds-v1"
DEFAULT_WAVEFORM_BINS = 720
DEFAULT_ARRANGEMENT_WAVEFORM_BINS = 320
MAX_TIMELINE_NOTES = 20_000
MAX_TIMELINE_MIDI_BYTES = 8 * 1024 * 1024
MAX_TIMELINE_CANDIDATES = 12
MAX_ARRANGEMENT_TIMELINE_NOTES = 40_000
MAX_ARRANGEMENT_MIDI_LANES = 24
MAX_ARRANGEMENT_SOURCE_LANES = 24
_DRUM_ROLES = frozenset(
    {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums", "percussion"}
)


class _TruncatedPCMDataError(ValueError):
    pass


@dataclass(frozen=True)
class _PCMGeometry:
    channels: int
    sample_width: int
    sample_rate: int
    frame_count: int
    data_offset: int
    block_align: int


class TimelineArtifactChangedError(ValueError):
    """Raised when a catalogued timeline input no longer matches its record."""


def build_stem_timeline(
    catalog: Mapping[str, Any],
    stem_id: str,
    *,
    waveform_bins: int = DEFAULT_WAVEFORM_BINS,
    candidate_ids: Sequence[str] | None = None,
    include_source: bool = True,
) -> dict[str, Any]:
    """Return deterministic source-waveform and candidate-note evidence.

    Every decoded input is re-hashed before and after projection. A
    reference-only source is re-hashed once because its audio is not decoded.
    The returned document deliberately contains no paths, process score,
    preference, or default choice. Candidate order is the already deterministic
    catalog order.
    """

    if not 64 <= int(waveform_bins) <= 4096:
        raise ValueError("waveform_bins must be between 64 and 4096")
    stem = _stem(catalog, stem_id)
    source_record = _record(stem.get("source"), label="source audio")
    all_candidate_rows = list(stem.get("candidates", []))
    candidate_rows = _selected_candidate_rows(all_candidate_rows, candidate_ids)
    for candidate in candidate_rows:
        _record(candidate.get("midi"), label="candidate MIDI")

    if include_source:
        _verify_inputs(stem, candidate_rows)
        source = _source_timeline(source_record, maximum_bins=int(waveform_bins))
    else:
        _verify_record(source_record, "source audio")
        _verify_candidate_inputs(candidate_rows)
        source = _source_reference(source_record)
    candidates = [
        _candidate_timeline(stem, candidate) for candidate in candidate_rows
    ]
    if include_source:
        _verify_inputs(stem, candidate_rows)
    else:
        _verify_candidate_inputs(candidate_rows)

    duration = max(
        [float(source.get("duration_seconds") or 0.0)]
        + [float(item.get("duration_seconds") or 0.0) for item in candidates]
    )
    document: dict[str, Any] = {
        "schema": WORKBENCH_TIMELINE_SCHEMA,
        "project_id": str(catalog.get("project_id", "")),
        "stem_id": str(stem.get("stem_id", "")),
        "role": path_free_role(stem.get("role"))[0],
        "duration_seconds": round(duration, 9),
        "source": source,
        "candidates": candidates,
        "candidate_scope": {
            "mode": "primary-default" if candidate_ids is None else "explicit",
            "source_projection": "included" if include_source else "reference-only",
            "available_candidate_count": len(all_candidate_rows),
            "returned_candidate_count": len(candidate_rows),
        },
        "policies": {
            "waveform": WAVEFORM_POLICY,
            "midi_notes": MIDI_NOTE_POLICY,
            "candidate_order": "catalog-order-unchanged",
            "alignment": (
                "MIDI tempo-map seconds are displayed against the catalogued "
                "source; no additional alignment is inferred"
            ),
            "midi_expression": (
                "note-on/off rectangles only; sustain, controllers, pitch bend "
                "and later program changes are not applied"
            ),
            "tempo": (
                "embedded MIDI tempo map; files without a tempo event use the "
                "Standard MIDI File 120 BPM default"
            ),
            "visual_limits": {
                "maximum_notes_per_candidate": MAX_TIMELINE_NOTES,
                "maximum_midi_bytes_per_candidate": MAX_TIMELINE_MIDI_BYTES,
                "maximum_candidates_per_request": MAX_TIMELINE_CANDIDATES,
            },
        },
        "effects": {
            "source_audio_mutated": False,
            "source_midi_mutated": False,
            "midi_created": False,
            "candidate_order_changed": False,
            "automatic_selection": False,
            "automatic_ranking": False,
            "default_selection_changed": False,
        },
    }
    document["timeline_sha256"] = _document_hash(document)
    return document


def build_arrangement_timeline(
    catalog: Mapping[str, Any],
    selection: Sequence[Mapping[str, Any]],
    *,
    waveform_bins: int = DEFAULT_ARRANGEMENT_WAVEFORM_BINS,
) -> dict[str, Any]:
    """Project source stems and the current explicit selection onto one timeline.

    ``selection`` must already have been derived by the Workbench's
    :func:`selected_candidates` policy.  The browser cannot supply an arbitrary
    candidate list to this projection.  Exact duplicate source audio is shown
    once, with every associated stem/role retained, while selected MIDI is
    never deduplicated.

    The aggregate note budget is enforced while each MIDI file is parsed, so a
    dense or hostile file cannot make the arrangement response grow without a
    bound.  A lane that exceeds the remaining budget stays visible as explicit
    unavailable evidence and the later, smaller lanes can still be inspected.
    """

    if not 64 <= int(waveform_bins) <= 4096:
        raise ValueError("waveform_bins must be between 64 and 4096")
    if len(selection) > MAX_ARRANGEMENT_MIDI_LANES:
        raise ValueError(
            "an arrangement timeline may include at most "
            f"{MAX_ARRANGEMENT_MIDI_LANES} selected MIDI lanes"
        )

    resolved: list[
        tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]
    ] = []
    seen: set[tuple[str, str]] = set()
    selection_identity: list[dict[str, Any]] = []
    for item in selection:
        stem_id = str(item.get("stem_id", ""))
        candidate_id = str(item.get("candidate_id", ""))
        identity = (stem_id, candidate_id)
        if not stem_id or not candidate_id or identity in seen:
            raise ValueError("selected arrangement rows must be unique and identified")
        seen.add(identity)
        stem = _stem(catalog, stem_id)
        candidate = _candidate(stem, candidate_id)
        if candidate.get("audition_blocked"):
            raise ValueError("selected arrangement contains a diagnostic-only candidate")
        record = _record(candidate.get("midi"), label="candidate MIDI")
        supplied_record = item.get("midi")
        if isinstance(supplied_record, Mapping) and (
            supplied_record.get("sha256") != record.get("sha256")
            or supplied_record.get("bytes") != record.get("bytes")
        ):
            raise ValueError("selected candidate no longer matches the catalog")
        decision = str(item.get("decision", ""))
        if decision not in {"main", "optional"}:
            raise ValueError("arrangement timeline accepts only main or optional choices")
        role = path_free_role(item.get("role") or stem.get("role"))[0]
        resolved.append((stem, candidate, item))
        selection_identity.append(
            {
                "stem_id": stem_id,
                "candidate_id": candidate_id,
                "role": role,
                "decision": decision,
                "midi_sha256": str(record["sha256"]),
                "midi_bytes": int(record["bytes"]),
            }
        )

    source_groups = _arrangement_source_groups(catalog)
    if len(source_groups) > MAX_ARRANGEMENT_SOURCE_LANES:
        raise ValueError(
            "an arrangement timeline may include at most "
            f"{MAX_ARRANGEMENT_SOURCE_LANES} distinct source lanes"
        )

    _verify_arrangement_inputs(source_groups, resolved)
    sources: list[dict[str, Any]] = []
    for group in source_groups:
        source = _source_timeline(
            group["records"][0], maximum_bins=int(waveform_bins)
        )
        sources.append(
            {
                **source,
                "source_id": group["source_id"],
                "stem_ids": list(group["stem_ids"]),
                "roles": list(group["roles"]),
                "labels": list(group["labels"]),
                "duplicate_catalog_source_count": len(group["records"]),
            }
        )

    remaining_notes = MAX_ARRANGEMENT_TIMELINE_NOTES
    midi_lanes: list[dict[str, Any]] = []
    for stem, candidate, item in resolved:
        lane = _candidate_timeline(
            stem,
            candidate,
            maximum_notes=min(MAX_TIMELINE_NOTES, remaining_notes),
        )
        if lane["status"] in {"available", "empty"}:
            remaining_notes -= int(lane.get("note_count") or 0)
        midi_lanes.append(
            {
                **lane,
                "stem_id": str(stem["stem_id"]),
                "role": path_free_role(item.get("role") or stem.get("role"))[0],
                "decision": str(item["decision"]),
                "source_sha256": str(stem["source"]["sha256"]),
            }
        )
    _verify_arrangement_inputs(source_groups, resolved)

    duration = max(
        [float(source.get("duration_seconds") or 0.0) for source in sources]
        + [float(lane.get("duration_seconds") or 0.0) for lane in midi_lanes]
        + [0.0]
    )
    selection_sha256 = _document_hash(
        {
            "project_id": str(catalog.get("project_id", "")),
            "bpm": catalog.get("setup", {}).get("bpm"),
            "selection": selection_identity,
        }
    )
    document: dict[str, Any] = {
        "schema": WORKBENCH_ARRANGEMENT_TIMELINE_SCHEMA,
        "project_id": str(catalog.get("project_id", "")),
        "selection_sha256": selection_sha256,
        "duration_seconds": round(duration, 9),
        "source_lane_count": len(sources),
        "selected_midi_lane_count": len(midi_lanes),
        "rendered_note_count": sum(
            int(lane.get("note_count") or 0)
            for lane in midi_lanes
            if lane["status"] in {"available", "empty"}
        ),
        "sources": sources,
        "midi_lanes": midi_lanes,
        "selection": selection_identity,
        "policies": {
            "waveform": WAVEFORM_POLICY,
            "midi_notes": MIDI_NOTE_POLICY,
            "source_duplicates": (
                "byte-identical catalog source audio shares one audition lane; "
                "every associated stem and role remains listed"
            ),
            "selected_midi": (
                "only active explicit main and optional choices; selected MIDI "
                "is never deduplicated"
            ),
            "alignment": (
                "every source and MIDI file starts at its recorded zero; no "
                "additional source/MIDI offset is inferred"
            ),
            "playback": (
                "browser media elements share elapsed seconds but are not "
                "sample-accurate"
            ),
            "mixer": (
                "visibility, mute, solo, gain, preset, loop and playhead are "
                "temporary audition state only"
            ),
            "visual_limits": {
                "maximum_total_rendered_notes": MAX_ARRANGEMENT_TIMELINE_NOTES,
                "maximum_notes_per_midi": MAX_TIMELINE_NOTES,
                "maximum_midi_bytes_per_candidate": MAX_TIMELINE_MIDI_BYTES,
                "maximum_selected_midi_lanes": MAX_ARRANGEMENT_MIDI_LANES,
                "maximum_distinct_source_lanes": MAX_ARRANGEMENT_SOURCE_LANES,
            },
        },
        "effects": {
            "source_audio_mutated": False,
            "source_midi_mutated": False,
            "midi_created": False,
            "selection_changed": False,
            "feedback_recorded": False,
            "automatic_selection": False,
            "automatic_ranking": False,
            "default_selection_changed": False,
        },
    }
    document["timeline_sha256"] = _document_hash(document)
    return document


def _source_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the hash-pinned source identity without rebuilding its waveform."""

    return {
        "sha256": str(record["sha256"]),
        "bytes": int(record["bytes"]),
        "waveform_policy": WAVEFORM_POLICY,
        "status": "reference-only",
        "reason_code": "source-projection-not-requested",
        "duration_seconds": None,
        "peaks": [],
    }


def _source_timeline(
    record: Mapping[str, Any], *, maximum_bins: int
) -> dict[str, Any]:
    path = Path(str(record["path"]))
    base = {
        "sha256": str(record["sha256"]),
        "bytes": int(record["bytes"]),
        "waveform_policy": WAVEFORM_POLICY,
    }
    if path.suffix.lower() not in {".wav", ".wave"}:
        return {
            **base,
            "status": "unavailable",
            "reason_code": "unsupported-audio-container",
            "duration_seconds": None,
            "peaks": [],
        }
    try:
        geometry = _pcm_geometry(path)
        bin_count = min(maximum_bins, geometry.frame_count)
        with path.open("rb") as reader:
            peaks: list[list[float]] = []
            full_scale = float(1 << (geometry.sample_width * 8 - 1))
            for index in range(bin_count):
                start = index * geometry.frame_count // bin_count
                end = (index + 1) * geometry.frame_count // bin_count
                reader.seek(geometry.data_offset + start * geometry.block_align)
                frames_in_bin = max(1, end - start)
                fragment = reader.read(frames_in_bin * geometry.block_align)
                expected_bytes = frames_in_bin * geometry.block_align
                if len(fragment) != expected_bytes:
                    raise _TruncatedPCMDataError
                if geometry.sample_width == 1:
                    fragment = audioop.bias(fragment, 1, -128)
                minimum, maximum = audioop.minmax(
                    fragment, geometry.sample_width
                )
                peaks.append(
                    [
                        round(max(-1.0, minimum / full_scale), 6),
                        round(min(1.0, maximum / full_scale), 6),
                    ]
                )
    except _TruncatedPCMDataError:
        return {
            **base,
            "status": "unavailable",
            "reason_code": "truncated-pcm-data",
            "duration_seconds": None,
            "peaks": [],
        }
    except (EOFError, OSError, ValueError, audioop.error):
        return {
            **base,
            "status": "unavailable",
            "reason_code": "unsupported-or-invalid-pcm-wav",
            "duration_seconds": None,
            "peaks": [],
        }
    return {
        **base,
        "status": "available",
        "reason_code": None,
        "duration_seconds": round(
            geometry.frame_count / geometry.sample_rate, 9
        ),
        "sample_rate": geometry.sample_rate,
        "channels": geometry.channels,
        "sample_width_bits": geometry.sample_width * 8,
        "frame_count": geometry.frame_count,
        "bin_count": bin_count,
        "peaks": peaks,
    }


def _pcm_geometry(path: Path) -> _PCMGeometry:
    """Read classic or WAVE_EXTENSIBLE integer-PCM geometry.

    Python 3.9's :mod:`wave` rejects WAVE_FORMAT_EXTENSIBLE even when its
    subformat is ordinary PCM. Moises/FFmpeg commonly write 24-bit stems that
    way, so the Workbench reads only the small RIFF header itself and still
    streams bounded waveform bins from disk.
    """

    file_size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise ValueError("not a little-endian RIFF WAVE file")
        position = 12
        format_data: bytes | None = None
        data_offset: int | None = None
        data_size: int | None = None
        while position + 8 <= file_size:
            handle.seek(position)
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                raise _TruncatedPCMDataError
            chunk_id = chunk_header[:4]
            chunk_size = struct.unpack("<I", chunk_header[4:])[0]
            chunk_offset = position + 8
            chunk_end = chunk_offset + chunk_size
            if chunk_end > file_size:
                raise _TruncatedPCMDataError
            if chunk_id == b"fmt ":
                if chunk_size > 1024 * 1024:
                    raise ValueError("implausibly large WAVE format chunk")
                handle.seek(chunk_offset)
                format_data = handle.read(chunk_size)
            elif chunk_id == b"data" and data_offset is None:
                data_offset = chunk_offset
                data_size = chunk_size
            if format_data is not None and data_offset is not None:
                break
            position = chunk_end + (chunk_size & 1)

    if format_data is None or data_offset is None or data_size is None:
        raise ValueError("WAVE file needs fmt and data chunks")
    if len(format_data) < 16:
        raise ValueError("truncated WAVE format chunk")
    (
        format_tag,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    ) = struct.unpack("<HHIIHH", format_data[:16])
    if format_tag == 0xFFFE:
        if len(format_data) < 40:
            raise ValueError("truncated WAVE_EXTENSIBLE format")
        extension_size = struct.unpack("<H", format_data[16:18])[0]
        pcm_subformat = bytes.fromhex("0100000000001000800000aa00389b71")
        if extension_size < 22 or format_data[24:40] != pcm_subformat:
            raise ValueError("unsupported WAVE_EXTENSIBLE subformat")
    elif format_tag != 1:
        raise ValueError("unsupported non-PCM WAVE encoding")
    if channels <= 0 or sample_rate <= 0:
        raise ValueError("invalid PCM channel or sample-rate geometry")
    if bits_per_sample not in {8, 16, 24, 32}:
        raise ValueError("unsupported PCM sample width")
    sample_width = bits_per_sample // 8
    expected_block_align = channels * sample_width
    if block_align != expected_block_align:
        raise ValueError("invalid PCM block alignment")
    if byte_rate != sample_rate * block_align:
        raise ValueError("invalid PCM byte rate")
    if data_size <= 0 or data_size % block_align:
        raise _TruncatedPCMDataError
    if data_offset + data_size > file_size:
        raise _TruncatedPCMDataError
    return _PCMGeometry(
        channels=channels,
        sample_width=sample_width,
        sample_rate=sample_rate,
        frame_count=data_size // block_align,
        data_offset=data_offset,
        block_align=block_align,
    )


def _candidate_timeline(
    stem: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    maximum_notes: int | None = None,
) -> dict[str, Any]:
    record = _record(candidate.get("midi"), label="candidate MIDI")
    note_limit = MAX_TIMELINE_NOTES if maximum_notes is None else int(maximum_notes)
    if note_limit < 0 or note_limit > MAX_TIMELINE_NOTES:
        raise ValueError(
            f"maximum_notes must be between 0 and {MAX_TIMELINE_NOTES}"
        )
    note_limit_reason = (
        "note-count-exceeds-visual-limit"
        if note_limit == MAX_TIMELINE_NOTES
        else "note-count-exceeds-arrangement-visual-budget"
    )
    stem_role = str(stem.get("role") or "unclassified").strip().lower()
    role_display_mode = (
        "drum-grid" if stem_role in _DRUM_ROLES else "piano-roll"
    )
    base: dict[str, Any] = {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "midi_sha256": str(record["sha256"]),
        "midi_bytes": int(record["bytes"]),
        "primary": bool(candidate.get("primary")),
        "diagnostic_only": bool(candidate.get("diagnostic_only")),
        "audition_blocked": bool(candidate.get("audition_blocked")),
        "note_policy": MIDI_NOTE_POLICY,
        "source_relationship": _source_relationship(stem, candidate),
    }
    if note_limit == 0:
        return {
            **base,
            "status": "unavailable",
            "reason_code": "arrangement-note-budget-exhausted",
            "note_count": None,
            "track_count": None,
            "display_mode": role_display_mode,
            "note_representation": "note-on-off-only",
            "duration_seconds": 0.0,
            "pitch_range": None,
            "tempo_points": [],
            "time_signature": None,
            "tracks": [],
        }
    if int(record["bytes"]) > MAX_TIMELINE_MIDI_BYTES:
        return {
            **base,
            "status": "unavailable",
            "reason_code": "midi-file-exceeds-visual-limit",
            "note_count": None,
            "track_count": None,
            "display_mode": role_display_mode,
            "note_representation": "note-on-off-only",
            "duration_seconds": 0.0,
            "pitch_range": None,
            "tempo_points": [],
            "time_signature": None,
            "tracks": [],
        }
    try:
        clips = read_midi_clips(
            str(record["path"]),
            role=str(stem.get("role") or "unclassified"),
            max_notes=note_limit,
        )
    except MidiNoteLimitError as exc:
        return {
            **base,
            "status": "unavailable",
            "reason_code": note_limit_reason,
            "note_count": exc.minimum_count,
            "note_count_is_lower_bound": True,
            "track_count": None,
            "display_mode": role_display_mode,
            "note_representation": "note-on-off-only",
            "duration_seconds": 0.0,
            "pitch_range": None,
            "tempo_points": [],
            "time_signature": None,
            "tracks": [],
        }
    except (EOFError, IndexError, OSError, ValueError, struct.error):
        return {
            **base,
            "status": "unavailable",
            "reason_code": "unsupported-or-invalid-midi",
            "note_count": None,
            "track_count": None,
            "display_mode": role_display_mode,
            "note_representation": "note-on-off-only",
            "duration_seconds": 0.0,
            "pitch_range": None,
            "tempo_points": [],
            "time_signature": None,
            "tracks": [],
        }

    note_count = sum(len(clip.notes) for clip in clips)
    if note_count > note_limit:
        return {
            **base,
            "status": "unavailable",
            "reason_code": note_limit_reason,
            "note_count": note_count,
            "track_count": len(clips),
            "display_mode": role_display_mode,
            "note_representation": "note-on-off-only",
            "duration_seconds": round(
                max(
                    (
                        note.source_end_seconds
                        for clip in clips
                        for note in clip.notes
                    ),
                    default=0.0,
                ),
                9,
            ),
            "pitch_range": None,
            "tempo_points": [],
            "time_signature": None,
            "tracks": [],
        }

    drum_role = stem_role in _DRUM_ROLES
    tracks: list[dict[str, Any]] = []
    for track_index, clip in enumerate(clips):
        track_notes = []
        for note in clip.notes:
            track_notes.append(
                {
                    "start_seconds": round(note.source_start_seconds, 9),
                    "end_seconds": round(note.source_end_seconds, 9),
                    "start_beat": round(note.start_beat, 9),
                    "end_beat": round(note.end_beat, 9),
                    "pitch": note.pitch,
                    "velocity": note.velocity,
                }
            )
        track_notes.sort(
            key=lambda note: (
                note["start_seconds"],
                note["pitch"],
                note["end_seconds"],
            )
        )
        track_pitches = [int(note["pitch"]) for note in track_notes]
        is_drums = drum_role or clip.instrument.is_drums
        tracks.append(
            {
                "track_id": clip.clip_id,
                "track_index": track_index,
                "title": clip.title,
                "channel": clip.instrument.channel,
                "program": clip.instrument.program,
                "display_mode": "drum-grid" if is_drums else "piano-roll",
                "note_count": len(track_notes),
                "pitch_range": (
                    [min(track_pitches), max(track_pitches)]
                    if track_pitches
                    else None
                ),
                "notes": track_notes,
            }
        )
    pitches = [int(note["pitch"]) for track in tracks for note in track["notes"]]
    display_modes = {str(track["display_mode"]) for track in tracks}
    if not display_modes:
        display_mode = role_display_mode
    elif len(display_modes) == 1:
        display_mode = next(iter(display_modes))
    else:
        display_mode = "mixed"
    first_clip = clips[0] if clips else None
    status = "available" if pitches else "empty"
    return {
        **base,
        "status": status,
        "reason_code": None if pitches else "no-note-events",
        "note_count": note_count,
        "track_count": len(clips),
        "display_mode": display_mode,
        "note_representation": "note-on-off-only",
        "duration_seconds": round(
            max(
                (
                    float(note["end_seconds"])
                    for track in tracks
                    for note in track["notes"]
                ),
                default=0.0,
            ),
            9,
        ),
        "pitch_range": [min(pitches), max(pitches)] if pitches else None,
        "tempo_points": (
            [
                {"beat": round(point.beat, 9), "bpm": round(point.bpm, 9)}
                for point in first_clip.tempo_map.tempo_points
            ]
            if first_clip
            else []
        ),
        "time_signature": (
            {
                "numerator": first_clip.time_signature.numerator,
                "denominator": first_clip.time_signature.denominator,
            }
            if first_clip
            else None
        ),
        "tracks": tracks,
    }


def _selected_candidate_rows(
    candidate_rows: Sequence[Mapping[str, Any]],
    candidate_ids: Sequence[str] | None,
) -> list[Mapping[str, Any]]:
    if candidate_ids is None:
        selected = [
            candidate for candidate in candidate_rows if candidate.get("primary")
        ]
    else:
        requested = [str(candidate_id).strip() for candidate_id in candidate_ids]
        if not requested or any(not candidate_id for candidate_id in requested):
            raise ValueError("candidate_id must not be empty")
        if len(set(requested)) != len(requested):
            raise ValueError("candidate_id values must be unique")
        known = {
            str(candidate.get("candidate_id", "")): candidate
            for candidate in candidate_rows
        }
        missing = [candidate_id for candidate_id in requested if candidate_id not in known]
        if missing:
            raise ValueError("unknown candidate_id for workbench stem")
        requested_ids = set(requested)
        selected = [
            candidate
            for candidate in candidate_rows
            if str(candidate.get("candidate_id", "")) in requested_ids
        ]
    if len(selected) > MAX_TIMELINE_CANDIDATES:
        raise ValueError(
            f"a timeline request may include at most {MAX_TIMELINE_CANDIDATES} candidates"
        )
    return selected


def _arrangement_source_groups(
    catalog: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Group byte-identical sources without hiding their catalog roles."""

    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for stem in catalog.get("stems", []):
        record = _record(stem.get("source"), label="source audio")
        digest = str(record["sha256"])
        if digest not in groups:
            order.append(digest)
            groups[digest] = {
                "source_id": f"source-{digest[:24]}",
                "stem_ids": [],
                "roles": [],
                "labels": [],
                "records": [],
            }
        group = groups[digest]
        group["stem_ids"].append(str(stem.get("stem_id", "")))
        role = path_free_role(stem.get("role"))[0]
        label = str(stem.get("label") or role)
        if role not in group["roles"]:
            group["roles"].append(role)
        if label not in group["labels"]:
            group["labels"].append(label)
        group["records"].append(record)
    return [groups[digest] for digest in order]


def _verify_arrangement_inputs(
    source_groups: Sequence[Mapping[str, Any]],
    resolved: Sequence[
        tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]
    ],
) -> None:
    for group in source_groups:
        for record in group["records"]:
            _verify_record(record, "source audio")
    for _stem_row, candidate, _selection_row in resolved:
        _verify_record(
            _record(candidate.get("midi"), label="candidate MIDI"),
            "candidate MIDI",
        )


def _candidate(
    stem: Mapping[str, Any], candidate_id: str
) -> Mapping[str, Any]:
    matches = [
        candidate
        for candidate in stem.get("candidates", [])
        if str(candidate.get("candidate_id", "")) == str(candidate_id)
    ]
    if len(matches) != 1:
        raise ValueError("selected candidate does not belong to its workbench stem")
    return matches[0]


def _source_relationship(
    stem: Mapping[str, Any], candidate: Mapping[str, Any]
) -> str:
    diagnostics = candidate.get("ai_diagnostics")
    source = stem.get("source")
    if isinstance(diagnostics, Mapping) and isinstance(source, Mapping):
        if diagnostics.get("source_audio_sha256") == source.get("sha256"):
            return "verified-ai-source-content"
    return "catalog-association-only"


def _stem(catalog: Mapping[str, Any], stem_id: str) -> Mapping[str, Any]:
    matches = [
        stem
        for stem in catalog.get("stems", [])
        if str(stem.get("stem_id", "")) == str(stem_id)
    ]
    if len(matches) != 1:
        raise ValueError("unknown workbench stem_id")
    return matches[0]


def _record(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"missing {label} record")
    path = value.get("path")
    digest = value.get("sha256")
    size = value.get("bytes")
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"invalid {label} record")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError(f"invalid {label} byte count")
    return value


def _verify_inputs(
    stem: Mapping[str, Any], candidate_rows: Sequence[Mapping[str, Any]]
) -> None:
    _verify_record(_record(stem.get("source"), label="source audio"), "source audio")
    for candidate in candidate_rows:
        _verify_record(
            _record(candidate.get("midi"), label="candidate MIDI"),
            "candidate MIDI",
        )


def _verify_candidate_inputs(candidate_rows: Sequence[Mapping[str, Any]]) -> None:
    for candidate in candidate_rows:
        _verify_record(
            _record(candidate.get("midi"), label="candidate MIDI"),
            "candidate MIDI",
        )


def _verify_record(record: Mapping[str, Any], label: str) -> None:
    path = Path(str(record["path"]))
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise TimelineArtifactChangedError(
            f"{label} is no longer available"
        ) from exc
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TimelineArtifactChangedError(
            f"{label} is no longer available"
        ) from exc
    if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
        raise TimelineArtifactChangedError(
            f"{label} changed after it was catalogued"
        )


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "DEFAULT_ARRANGEMENT_WAVEFORM_BINS",
    "DEFAULT_WAVEFORM_BINS",
    "MAX_ARRANGEMENT_MIDI_LANES",
    "MAX_ARRANGEMENT_SOURCE_LANES",
    "MAX_ARRANGEMENT_TIMELINE_NOTES",
    "MAX_TIMELINE_CANDIDATES",
    "MAX_TIMELINE_NOTES",
    "MIDI_NOTE_POLICY",
    "TimelineArtifactChangedError",
    "WAVEFORM_POLICY",
    "WORKBENCH_ARRANGEMENT_TIMELINE_SCHEMA",
    "WORKBENCH_TIMELINE_SCHEMA",
    "build_arrangement_timeline",
    "build_stem_timeline",
]
