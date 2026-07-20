"""Content-addressed Workbench previews, arrangements, and DAW handoffs.

The Workbench never edits a discovered MIDI file.  These helpers create clearly
labelled audition proxies beneath the local Workbench state directory and keep
the original selected MIDI byte-for-byte in the GarageBand handoff.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import read_midi_clips
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .note_alignment import AlignmentEvent, align_events
from .render import find_soundfont, render_midi_to_wav
from .workbench_privacy import path_free_role
from .workbench_semantics import terminal_no_selection_outcome


NEUTRAL_PREVIEW_SCHEMA = "sunofriend.workbench-neutral-preview.v1"
DECODED_STEM_LOOP_SCHEMA = "sunofriend.workbench-decoded-stem-loop.v1"
ARRANGEMENT_SELECTION_SCHEMA = "sunofriend.workbench-arrangement-selection.v1"
DECODED_ARRANGEMENT_LOOP_SCHEMA = "sunofriend.workbench-decoded-arrangement-loop.v1"
ARRANGEMENT_SCHEMA = "sunofriend.workbench-arrangement.v1"
GARAGEBAND_HANDOFF_SCHEMA = "sunofriend.workbench-garageband-handoff.v1"
GARAGEBAND_PACK_PLAN_SCHEMA = "sunofriend.workbench-garageband-pack-plan.v1"
GARAGEBAND_PACK_BASKET_SCHEMA = "sunofriend.workbench-garageband-pack-basket.v1"
GARAGEBAND_PACK_SCHEMA = "sunofriend.workbench-garageband-pack.v1"
SELECTED_MIDI_OVERLAP_SCHEMA = "sunofriend.workbench-selected-midi-overlap.v1"
_RENDER_POLICY = "role-neutral-general-midi-v1"
_DECODED_LOOP_POLICY = "recorded-zero-source-frame-window-v1"
_DECODED_ARRANGEMENT_LOOP_POLICY = "recorded-zero-selected-arrangement-window-v1"
_DECODED_LOOP_MINIMUM_SECONDS = 0.5
_DECODED_LOOP_MAXIMUM_SECONDS = 15.0
_DECODED_LOOP_MAXIMUM_CANDIDATES = 6
_DECODED_ARRANGEMENT_MAXIMUM_TRACKS = 24
_DECODED_LOOP_MAXIMUM_OUTPUT_BYTES = 64 * 1024 * 1024
_DECODED_LOOP_MAXIMUM_INPUT_BYTES = 2 * 1024 * 1024 * 1024
_DECODED_LOOP_CACHE_MAXIMUM_BYTES = 256 * 1024 * 1024
_DECODED_LOOP_CACHE_MAXIMUM_ENTRIES = 32
_DECODED_LOOP_BUILDING_MAXIMUM_AGE_SECONDS = 6 * 60 * 60
_DECODED_LOOP_MAXIMUM_START_SECONDS = 24 * 60 * 60
_DECODED_LOOP_MINIMUM_SAMPLE_RATE = 8_000
_DECODED_LOOP_MAXIMUM_SAMPLE_RATE = 96_000
_DECODED_PCM16_WAV_HEADER_BUDGET_BYTES = 4 * 1024
_NEUTRAL_PREVIEW_MAXIMUM_SECONDS = 20 * 60
_OVERLAP_ONSET_TOLERANCE_SECONDS = 0.080
_SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES = 8
_SUBSTANTIAL_OVERLAP_MINIMUM_RATIO = 0.80
_DRUM_ROLES = {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums"}
_MELODIC_CHANNELS = tuple(channel for channel in range(16) if channel != 9)
_ROLE_PROGRAMS = {
    "bass": 33,
    "keys": 4,
    "piano": 0,
    "strings": 48,
    "pads": 89,
    "synth": 81,
    "lead": 81,
    "vocals": 73,
    "vocal": 73,
    "backing_vocals": 52,
    "rhythm": 27,
    "wind": 71,
}


class WorkbenchPackConflictError(ValueError):
    """The requested pack no longer describes the current Workbench state."""


class WorkbenchArtifacts:
    """Build and reuse immutable local artifacts for one Workbench project."""

    def __init__(
        self,
        root: str | Path,
        *,
        soundfont_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.soundfont_path = (
            Path(soundfont_path).expanduser().resolve() if soundfont_path else None
        )
        self._soundfont_cache: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def cached_candidate_preview(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_id: str,
        *,
        role_override: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            stem, candidate = _candidate(catalog, stem_id, candidate_id)
            try:
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
            except ValueError:
                return None
            expected = {
                "source_midi_sha256": candidate["midi"]["sha256"],
                "role": _preview_role(stem, role_override),
                "bpm": _project_bpm(catalog),
                "policy": _RENDER_POLICY,
            }
            soundfont_sha256 = self._available_soundfont_sha256()
            if not soundfont_sha256:
                return None
            expected["soundfont_sha256"] = soundfont_sha256
            return self._find_cached("previews", NEUTRAL_PREVIEW_SCHEMA, expected)

    def render_candidate_preview(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_id: str,
        *,
        role_override: str | None = None,
    ) -> dict[str, Any]:
        stem, candidate = _candidate(catalog, stem_id, candidate_id)
        if candidate.get("audition_blocked"):
            raise ValueError(
                "candidate audition is blocked because AI diagnostics found no "
                "playable evidence or an extreme decoder burst"
            )
        self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
        bpm = _project_bpm(catalog)
        role = _preview_role(stem, role_override)
        soundfont = self._soundfont()
        key_payload = {
            "schema": NEUTRAL_PREVIEW_SCHEMA,
            "source_midi_sha256": candidate["midi"]["sha256"],
            "role": role,
            "bpm": bpm,
            "policy": _RENDER_POLICY,
            "soundfont_sha256": soundfont["sha256"],
        }
        cache_key = _document_hash(key_payload)
        with self._lock:
            cached = self._load_cached("previews", cache_key, NEUTRAL_PREVIEW_SCHEMA)
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            channel = 9 if _is_drum_role(role) else 0
            program = 0 if channel == 9 else _program_for_role(role)
            work, final = self._building_directory("previews", cache_key)
            _restrict_private_permissions(work, 0o700)
            try:
                source_midi = _write_verified_private_snapshot(
                    Path(str(candidate["midi_path"])),
                    candidate["midi"],
                    work / ".verified-source.mid",
                    label="candidate MIDI",
                )
                source_soundfont = _write_verified_private_snapshot(
                    Path(str(soundfont["path"])),
                    soundfont,
                    work / ".verified-soundfont.sf2",
                    label="SoundFont",
                )
                clips = read_midi_clips(source_midi, role=role)
                notes = _clips_to_notes(clips)
                if not notes:
                    raise ValueError(
                        "selected candidate MIDI contains no playable notes"
                    )
                if max(note.end for note in notes) > _NEUTRAL_PREVIEW_MAXIMUM_SECONDS:
                    raise ValueError(
                        "selected candidate MIDI exceeds the 20 minute neutral-preview "
                        "rendering limit"
                    )
                tracks = [MidiTrack(_track_name(role), channel, program, notes)]
                midi_path = work / "neutral-preview.mid"
                wav_path = work / "neutral-preview.wav"
                write_midi_file(midi_path, tracks, bpm=bpm)
                render_midi_to_wav(
                    midi_path,
                    wav_path,
                    soundfont_path=source_soundfont,
                )
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
                self._verify_catalog_record(
                    soundfont,
                    label="SoundFont",
                    restart_hint=True,
                )
                source_midi.unlink()
                source_soundfont.unlink()
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "program": program,
                    "channel": channel,
                    "source_candidate_id": candidate_id,
                    "source_stem_id": stem_id,
                    "soundfont": _without_path(soundfont),
                    "midi": _relative_file_record(midi_path, work),
                    "preview": _relative_file_record(wav_path, work),
                    "original_midi_mutated": False,
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_cached("previews", cache_key, NEUTRAL_PREVIEW_SCHEMA)
            if result is None:
                raise RuntimeError("neutral preview cache verification failed")
            result["cache_hit"] = False
            return result

    def prepare_decoded_stem_loop(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_ids: Sequence[str],
        start_seconds: float,
        end_seconds: float,
    ) -> dict[str, Any]:
        """Build private PCM16 source/candidate windows for decoded switching."""

        start, end = _decoded_loop_window(start_seconds, end_seconds)
        requested_ids = _decoded_loop_candidate_ids(candidate_ids)
        stem = _stem(catalog, stem_id)
        source_record = stem.get("source")
        if not isinstance(source_record, Mapping):
            raise ValueError("selected stem has no catalogued source audio")

        candidates: list[Mapping[str, Any]] = []
        for candidate_id in requested_ids:
            _, candidate = _candidate(catalog, stem_id, candidate_id)
            if candidate.get("audition_blocked"):
                raise ValueError(
                    "candidate audition is blocked because AI diagnostics found no "
                    "playable evidence or an extreme decoder burst"
                )
            candidates.append(candidate)

        with self._lock:
            declared_input_bytes = _decoded_declared_input_bytes(
                [("source audio", source_record)]
                + [
                    ("candidate MIDI", candidate.get("midi"))
                    for candidate in candidates
                ]
            )
            _require_decoded_input_limit(declared_input_bytes)
            if self._soundfont_cache is not None:
                soundfont_size = _decoded_declared_input_bytes(
                    [("SoundFont", self._soundfont_cache)]
                )
            else:
                soundfont_path = self.soundfont_path or Path(find_soundfont()).resolve()
                try:
                    soundfont_size = soundfont_path.stat().st_size
                except OSError as exc:
                    raise ValueError(
                        f"SoundFont file does not exist: {soundfont_path}"
                    ) from exc
            _require_decoded_input_limit(declared_input_bytes + soundfont_size)

            source_path = self._verify_catalog_record(
                source_record, label="source audio"
            )
            for candidate in candidates:
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
            soundfont_record = self._soundfont()
            pre_render_input_bytes = _decoded_declared_input_bytes(
                [("source audio", source_record), ("SoundFont", soundfont_record)]
                + [
                    ("candidate MIDI", candidate.get("midi"))
                    for candidate in candidates
                ]
            )
            _require_decoded_input_limit(pre_render_input_bytes)
            np, soundfile = _decoded_audio_modules()
            required_soundfont_sha256 = str(soundfont_record["sha256"])

            previews: list[dict[str, Any]] = []
            for candidate_id in requested_ids:
                preview = self.cached_candidate_preview(catalog, stem_id, candidate_id)
                if preview is None:
                    preview = self.render_candidate_preview(
                        catalog, stem_id, candidate_id
                    )
                previews.append(preview)
            self._require_preview_renderer_consistency(
                previews,
                expected_soundfont_sha256=required_soundfont_sha256,
            )

            # Rendering a missing neutral preview can take long enough for an input
            # to change. Recheck all original inputs before reading any audio.
            source_path = self._verify_catalog_record(
                source_record, label="source audio"
            )
            for candidate in candidates:
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
            preview_paths = [
                self._verify_catalog_record(
                    preview["preview"], label="neutral candidate preview"
                )
                for preview in previews
            ]
            aggregate_input_bytes = pre_render_input_bytes + sum(
                int(preview["preview"]["bytes"]) for preview in previews
            )
            _require_decoded_input_limit(aggregate_input_bytes)

            source_info = _decoded_audio_info(
                soundfile, source_path, label="source audio"
            )
            source_start_frame = _nearest_audio_frame(start, source_info["sample_rate"])
            source_end_frame = _nearest_audio_frame(end, source_info["sample_rate"])
            if source_end_frame <= source_start_frame:
                raise ValueError("decoded loop window contains no source audio frames")
            quantized_start = source_start_frame / source_info["sample_rate"]
            quantized_end = source_end_frame / source_info["sample_rate"]

            inputs: list[dict[str, Any]] = [
                {
                    "track_id": "source",
                    "kind": "source",
                    "input_path": source_path,
                    "input_sha256": str(source_record["sha256"]),
                    "input_bytes": int(source_record["bytes"]),
                    "sample_rate": source_info["sample_rate"],
                    "channels": source_info["channels"],
                    "input_frames": source_info["frames"],
                    "start_frame": source_start_frame,
                    "end_frame": source_end_frame,
                }
            ]
            for index, (candidate_id, candidate, preview, preview_path) in enumerate(
                zip(requested_ids, candidates, previews, preview_paths),
                start=1,
            ):
                info = _decoded_audio_info(
                    soundfile,
                    preview_path,
                    label=f"neutral candidate preview {index}",
                )
                candidate_start = _nearest_audio_frame(
                    quantized_start, info["sample_rate"]
                )
                candidate_end = _nearest_audio_frame(quantized_end, info["sample_rate"])
                if candidate_end <= candidate_start:
                    raise ValueError(
                        "decoded loop window contains no candidate preview frames"
                    )
                inputs.append(
                    {
                        "track_id": f"candidate-{index}",
                        "kind": "candidate",
                        "candidate_id": candidate_id,
                        "input_path": preview_path,
                        "input_sha256": str(preview["preview"]["sha256"]),
                        "input_bytes": int(preview["preview"]["bytes"]),
                        "source_midi_sha256": str(candidate["midi"]["sha256"]),
                        "neutral_preview_cache_key": str(preview["cache_key"]),
                        "neutral_preview_policy": str(preview["policy"]),
                        "soundfont_sha256": str(preview["soundfont_sha256"]),
                        "sample_rate": info["sample_rate"],
                        "channels": info["channels"],
                        "input_frames": info["frames"],
                        "start_frame": candidate_start,
                        "end_frame": candidate_end,
                    }
                )

            input_fingerprints = [
                {key: value for key, value in item.items() if key != "input_path"}
                for item in inputs
            ]
            key_payload = {
                "schema": DECODED_STEM_LOOP_SCHEMA,
                "project_id": catalog.get("project_id"),
                "stem_id": stem_id,
                "candidate_ids": list(requested_ids),
                "window": {
                    "source_start_frame": source_start_frame,
                    "source_end_frame": source_end_frame,
                    "quantized_start_seconds": quantized_start,
                    "quantized_end_seconds": quantized_end,
                    "logical_duration_seconds": quantized_end - quantized_start,
                },
                "input_fingerprints": input_fingerprints,
                "policy": _DECODED_LOOP_POLICY,
                "renderer": {
                    "policy": _RENDER_POLICY,
                    "soundfont_sha256": required_soundfont_sha256,
                },
                "encoding": {
                    "container": "WAV",
                    "subtype": "PCM_16",
                    "sample_rate_policy": "preserve each decoded input rate",
                    "channel_policy": "preserve mono or stereo",
                },
                "resource_limits": {
                    "aggregate_input_bytes": aggregate_input_bytes,
                    "maximum_input_bytes": _DECODED_LOOP_MAXIMUM_INPUT_BYTES,
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                },
            }
            cache_key = _document_hash(key_payload)
            cached = self._load_decoded_stem_loop(cache_key, key_payload)
            if cached is not None:
                self._verify_decoded_loop_inputs(
                    source_record=source_record,
                    candidates=candidates,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                self._touch_and_prune_decoded_loop_cache(cache_key)
                cached["cache_hit"] = True
                return cached

            work, final = self._private_building_directory(
                "decoded-stem-loops", cache_key
            )
            try:
                decode_paths = [
                    _write_verified_private_snapshot(
                        Path(item["input_path"]),
                        source_record if index == 0 else previews[index - 1]["preview"],
                        work / f".verified-input-{index:02d}",
                        label=(
                            "source audio"
                            if index == 0
                            else f"neutral candidate preview {index}"
                        ),
                    )
                    for index, item in enumerate(inputs)
                ]
                for index, (item, decode_path) in enumerate(zip(inputs, decode_paths)):
                    snapshot_info = _decoded_audio_info(
                        soundfile,
                        decode_path,
                        label=(
                            "source audio snapshot"
                            if index == 0
                            else f"neutral candidate preview snapshot {index}"
                        ),
                    )
                    if (
                        snapshot_info["sample_rate"] != item["sample_rate"]
                        or snapshot_info["channels"] != item["channels"]
                        or snapshot_info["frames"] != item["input_frames"]
                    ):
                        raise ValueError(
                            "verified decoded audio snapshot metadata changed"
                        )
                tracks: list[dict[str, Any]] = []
                for index, item in enumerate(inputs):
                    output_path = work / f"{index:02d}-{item['kind']}.wav"
                    output_frames = int(item["end_frame"]) - int(item["start_frame"])
                    samples = _read_padded_audio_window(
                        np,
                        soundfile,
                        decode_paths[index],
                        start_frame=int(item["start_frame"]),
                        frames=output_frames,
                        channels=int(item["channels"]),
                    )
                    soundfile.write(
                        str(output_path),
                        samples,
                        int(item["sample_rate"]),
                        format="WAV",
                        subtype="PCM_16",
                    )
                    _restrict_private_permissions(output_path, 0o600)
                    written = soundfile.info(str(output_path))
                    if (
                        written.format != "WAV"
                        or written.subtype != "PCM_16"
                        or int(written.samplerate) != int(item["sample_rate"])
                        or int(written.channels) != int(item["channels"])
                        or int(written.frames) != output_frames
                    ):
                        raise RuntimeError(
                            "decoded loop PCM16 output verification failed"
                        )
                    audio_record = _relative_file_record(output_path, work)
                    track = {
                        "track_id": item["track_id"],
                        "kind": item["kind"],
                        "audio": audio_record,
                        "sample_rate": int(written.samplerate),
                        "channels": int(written.channels),
                        "frames": int(written.frames),
                        "start_frame": int(item["start_frame"]),
                        "silence_padded_frames": max(
                            0,
                            int(item["end_frame"])
                            - max(
                                int(item["start_frame"]),
                                min(
                                    int(item["end_frame"]),
                                    int(item["input_frames"]),
                                ),
                            ),
                        ),
                    }
                    if item["kind"] == "candidate":
                        track["candidate_id"] = item["candidate_id"]
                    tracks.append(track)

                aggregate_bytes = sum(int(track["audio"]["bytes"]) for track in tracks)
                if aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES:
                    raise ValueError(
                        "decoded loop aggregate output exceeds the 64 MiB limit"
                    )

                self._verify_decoded_loop_inputs(
                    source_record=source_record,
                    candidates=candidates,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                for decode_path in decode_paths:
                    decode_path.unlink()
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "start_seconds": quantized_start,
                    "end_seconds": quantized_end,
                    "duration_seconds": quantized_end - quantized_start,
                    "tracks": tracks,
                    "aggregate_output_bytes": aggregate_bytes,
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                    "path_free_manifest": True,
                    "private_audio": True,
                    "effects": {
                        "midi_mutated": False,
                        "selection_changed": False,
                        "feedback_recorded": False,
                        "event_appended": False,
                    },
                }
                manifest_path = work / "manifest.json"
                _write_json(manifest_path, manifest)
                _restrict_private_permissions(manifest_path, 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_decoded_stem_loop(cache_key, key_payload)
            if result is None:
                raise RuntimeError("decoded stem loop cache verification failed")
            self._touch_and_prune_decoded_loop_cache(cache_key)
            result["cache_hit"] = False
            return result

    def decoded_arrangement_selection_manifest(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return the canonical path-free tracks and preset groups for audition."""

        return decoded_arrangement_selection_manifest(catalog, current)

    def prepare_decoded_arrangement_loop(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        selection_manifest_sha256: str,
        start_seconds: float,
        end_seconds: float,
    ) -> dict[str, Any]:
        """Build one private short-loop bundle for the selected arrangement."""

        start, end = _decoded_loop_window(start_seconds, end_seconds)
        (
            selection_manifest,
            source_groups,
            selection,
        ) = _decoded_arrangement_selection(catalog, current)
        if (
            not _is_sha256(selection_manifest_sha256)
            or selection_manifest_sha256
            != selection_manifest["selection_manifest_sha256"]
        ):
            raise ValueError(
                "the decoded arrangement selection changed; reload the current "
                "arrangement before preparing it"
            )
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before preparing "
                "a decoded arrangement"
            )
        if len(source_groups) + len(selection) > _DECODED_ARRANGEMENT_MAXIMUM_TRACKS:
            raise ValueError(
                "decoded arrangement comparison supports at most 24 source and "
                "selected MIDI tracks"
            )

        with self._lock:
            source_records = [group["records"][0] for group in source_groups]
            declared_input_bytes = _decoded_declared_input_bytes(
                [("source audio", record) for record in source_records]
                + [("selected candidate MIDI", item.get("midi")) for item in selection]
            )
            _require_decoded_input_limit(declared_input_bytes)
            if self._soundfont_cache is not None:
                soundfont_size = _decoded_declared_input_bytes(
                    [("SoundFont", self._soundfont_cache)]
                )
            else:
                soundfont_path = self.soundfont_path or Path(find_soundfont()).resolve()
                try:
                    soundfont_size = soundfont_path.stat().st_size
                except OSError as exc:
                    raise ValueError(
                        f"SoundFont file does not exist: {soundfont_path}"
                    ) from exc
            _require_decoded_input_limit(declared_input_bytes + soundfont_size)

            for group in source_groups:
                for record in group["records"]:
                    self._verify_catalog_record(record, label="source audio")
            self._verify_selection(selection)
            soundfont_record = self._soundfont()
            pre_render_input_bytes = _decoded_declared_input_bytes(
                [("source audio", record) for record in source_records]
                + [("selected candidate MIDI", item.get("midi")) for item in selection]
                + [("SoundFont", soundfont_record)]
            )
            _require_decoded_input_limit(pre_render_input_bytes)

            previews: list[dict[str, Any]] = []
            aggregate_input_bytes = pre_render_input_bytes
            for item in selection:
                preview = self.cached_candidate_preview(
                    catalog,
                    str(item["stem_id"]),
                    str(item["candidate_id"]),
                    role_override=str(item["role"]),
                )
                if preview is None:
                    preview = self.render_candidate_preview(
                        catalog,
                        str(item["stem_id"]),
                        str(item["candidate_id"]),
                        role_override=str(item["role"]),
                    )
                preview_bytes = _decoded_declared_input_bytes(
                    [("neutral selected MIDI preview", preview.get("preview"))]
                )
                try:
                    _require_decoded_input_limit(
                        aggregate_input_bytes + preview_bytes
                    )
                except ValueError:
                    if preview.get("cache_hit") is False:
                        self._discard_new_preview(preview)
                    raise
                aggregate_input_bytes += preview_bytes
                previews.append(preview)
            required_soundfont_sha256 = str(soundfont_record["sha256"])
            self._require_preview_renderer_consistency(
                previews,
                expected_soundfont_sha256=required_soundfont_sha256,
            )

            self._verify_decoded_arrangement_inputs(
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                expected_soundfont_sha256=required_soundfont_sha256,
            )
            source_paths = [
                self._verify_catalog_record(record, label="source audio")
                for record in source_records
            ]
            preview_paths = [
                self._verify_catalog_record(
                    preview["preview"], label="neutral selected MIDI preview"
                )
                for preview in previews
            ]
            np, soundfile = _decoded_audio_modules()
            source_infos = [
                _decoded_audio_info(soundfile, path, label="source audio")
                for path in source_paths
            ]
            if not source_infos:
                raise ValueError("decoded arrangement requires source audio")
            anchor_sample_rate = int(source_infos[0]["sample_rate"])
            anchor_start_frame = _nearest_audio_frame(start, anchor_sample_rate)
            anchor_end_frame = _nearest_audio_frame(end, anchor_sample_rate)
            if anchor_end_frame <= anchor_start_frame:
                raise ValueError(
                    "decoded arrangement window contains no source audio frames"
                )
            quantized_start = anchor_start_frame / anchor_sample_rate
            quantized_end = anchor_end_frame / anchor_sample_rate

            inputs: list[dict[str, Any]] = []
            for group, record, path, info in zip(
                source_groups, source_records, source_paths, source_infos
            ):
                input_start = _nearest_audio_frame(
                    quantized_start, int(info["sample_rate"])
                )
                input_end = _nearest_audio_frame(
                    quantized_end, int(info["sample_rate"])
                )
                inputs.append(
                    {
                        "track_id": group["track_id"],
                        "kind": "source",
                        "stem_ids": list(group["stem_ids"]),
                        "roles": list(group["roles"]),
                        "source_sha256": str(record["sha256"]),
                        "input_path": path,
                        "expected_record": record,
                        "input_sha256": str(record["sha256"]),
                        "input_bytes": int(record["bytes"]),
                        "sample_rate": int(info["sample_rate"]),
                        "channels": int(info["channels"]),
                        "input_frames": int(info["frames"]),
                        "start_frame": input_start,
                        "end_frame": input_end,
                    }
                )

            for item, preview, path in zip(selection, previews, preview_paths):
                info = _decoded_audio_info(
                    soundfile,
                    path,
                    label="neutral selected MIDI preview",
                )
                input_start = _nearest_audio_frame(
                    quantized_start, int(info["sample_rate"])
                )
                input_end = _nearest_audio_frame(
                    quantized_end, int(info["sample_rate"])
                )
                inputs.append(
                    {
                        "track_id": item["track_id"],
                        "kind": "selected_midi",
                        "stem_id": item["stem_id"],
                        "candidate_id": item["candidate_id"],
                        "role": item["role"],
                        "decision": item["decision"],
                        "source_midi_sha256": str(item["midi"]["sha256"]),
                        "neutral_preview_cache_key": str(preview["cache_key"]),
                        "neutral_preview_policy": str(preview["policy"]),
                        "soundfont_sha256": str(preview["soundfont_sha256"]),
                        "input_path": path,
                        "expected_record": preview["preview"],
                        "input_sha256": str(preview["preview"]["sha256"]),
                        "input_bytes": int(preview["preview"]["bytes"]),
                        "sample_rate": int(info["sample_rate"]),
                        "channels": int(info["channels"]),
                        "input_frames": int(info["frames"]),
                        "start_frame": input_start,
                        "end_frame": input_end,
                    }
                )

            pcm16_output_upper_bound_bytes = _decoded_pcm16_output_upper_bound(
                inputs
            )
            if pcm16_output_upper_bound_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES:
                raise ValueError(
                    "decoded arrangement aggregate output exceeds the 64 MiB limit"
                )

            input_fingerprints = [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"input_path", "expected_record"}
                }
                for item in inputs
            ]
            key_payload = {
                "schema": DECODED_ARRANGEMENT_LOOP_SCHEMA,
                "project_id": catalog.get("project_id"),
                "selection_manifest_sha256": selection_manifest_sha256,
                "sources": selection_manifest["sources"],
                "selected_midi": selection_manifest["selected_midi"],
                "groups": selection_manifest["groups"],
                "window": {
                    "anchor_sample_rate": anchor_sample_rate,
                    "anchor_start_frame": anchor_start_frame,
                    "anchor_end_frame": anchor_end_frame,
                    "quantized_start_seconds": quantized_start,
                    "quantized_end_seconds": quantized_end,
                    "logical_duration_seconds": quantized_end - quantized_start,
                },
                "input_fingerprints": input_fingerprints,
                "policy": _DECODED_ARRANGEMENT_LOOP_POLICY,
                "renderer": {
                    "policy": _RENDER_POLICY,
                    "soundfont_sha256": required_soundfont_sha256,
                },
                "encoding": {
                    "container": "WAV",
                    "subtype": "PCM_16",
                    "sample_rate_policy": "preserve each decoded input rate",
                    "channel_policy": "preserve mono or stereo",
                },
                "resource_limits": {
                    "track_count": len(inputs),
                    "maximum_track_count": _DECODED_ARRANGEMENT_MAXIMUM_TRACKS,
                    "aggregate_input_bytes": aggregate_input_bytes,
                    "maximum_input_bytes": _DECODED_LOOP_MAXIMUM_INPUT_BYTES,
                    "pcm16_output_upper_bound_bytes": (
                        pcm16_output_upper_bound_bytes
                    ),
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                },
            }
            cache_key = _document_hash(key_payload)
            cached = self._load_decoded_arrangement_loop(cache_key, key_payload)
            if cached is not None:
                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                self._touch_and_prune_decoded_cache(
                    "decoded-arrangement-loops", cache_key
                )
                cached["cache_hit"] = True
                return cached

            work, final = self._private_building_directory(
                "decoded-arrangement-loops", cache_key
            )
            try:
                tracks: list[dict[str, Any]] = []
                for index, item in enumerate(inputs):
                    snapshot_path = work / f".verified-input-{index:02d}"
                    snapshot = _write_verified_private_snapshot(
                        Path(item["input_path"]),
                        item["expected_record"],
                        snapshot_path,
                        label=(
                            "source audio"
                            if item["kind"] == "source"
                            else "neutral selected MIDI preview"
                        ),
                    )
                    try:
                        snapshot_info = _decoded_audio_info(
                            soundfile,
                            snapshot,
                            label="verified decoded arrangement audio snapshot",
                        )
                        if (
                            snapshot_info["sample_rate"] != item["sample_rate"]
                            or snapshot_info["channels"] != item["channels"]
                            or snapshot_info["frames"] != item["input_frames"]
                        ):
                            raise ValueError(
                                "verified decoded arrangement snapshot metadata changed"
                            )
                        output_frames = int(item["end_frame"]) - int(
                            item["start_frame"]
                        )
                        if output_frames <= 0:
                            raise ValueError(
                                "decoded arrangement track has no output frames"
                            )
                        samples = _read_padded_audio_window(
                            np,
                            soundfile,
                            snapshot,
                            start_frame=int(item["start_frame"]),
                            frames=output_frames,
                            channels=int(item["channels"]),
                        )
                        output_path = work / f"{index:02d}-{item['kind']}.wav"
                        soundfile.write(
                            str(output_path),
                            samples,
                            int(item["sample_rate"]),
                            format="WAV",
                            subtype="PCM_16",
                        )
                        _restrict_private_permissions(output_path, 0o600)
                        written = soundfile.info(str(output_path))
                        if (
                            written.format != "WAV"
                            or written.subtype != "PCM_16"
                            or int(written.samplerate) != int(item["sample_rate"])
                            or int(written.channels) != int(item["channels"])
                            or int(written.frames) != output_frames
                        ):
                            raise RuntimeError(
                                "decoded arrangement PCM16 output verification failed"
                            )
                    finally:
                        snapshot.unlink(missing_ok=True)

                    track = {
                        key: item[key]
                        for key in (
                            "track_id",
                            "kind",
                            "stem_ids",
                            "roles",
                            "source_sha256",
                            "stem_id",
                            "candidate_id",
                            "role",
                            "decision",
                            "source_midi_sha256",
                        )
                        if key in item
                    }
                    track.update(
                        {
                            "audio": _relative_file_record(output_path, work),
                            "sample_rate": int(written.samplerate),
                            "channels": int(written.channels),
                            "frames": int(written.frames),
                            "start_frame": int(item["start_frame"]),
                            "silence_padded_frames": max(
                                0,
                                int(item["end_frame"])
                                - max(
                                    int(item["start_frame"]),
                                    min(
                                        int(item["end_frame"]),
                                        int(item["input_frames"]),
                                    ),
                                ),
                            ),
                        }
                    )
                    tracks.append(track)

                aggregate_bytes = sum(int(track["audio"]["bytes"]) for track in tracks)
                if aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES:
                    raise ValueError(
                        "decoded arrangement aggregate output exceeds the 64 MiB limit"
                    )
                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "start_seconds": quantized_start,
                    "end_seconds": quantized_end,
                    "duration_seconds": quantized_end - quantized_start,
                    "tracks": tracks,
                    "aggregate_output_bytes": aggregate_bytes,
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                    "path_free_manifest": True,
                    "private_audio": True,
                    "effects": _decoded_arrangement_effects(),
                }
                manifest_path = work / "manifest.json"
                _write_json(manifest_path, manifest)
                _restrict_private_permissions(manifest_path, 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_decoded_arrangement_loop(cache_key, key_payload)
            if result is None:
                raise RuntimeError("decoded arrangement loop cache verification failed")
            self._touch_and_prune_decoded_cache("decoded-arrangement-loops", cache_key)
            result["cache_hit"] = False
            return result

    def cached_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock:
            selection = selected_candidates(catalog, current)
            if not selection:
                return None
            try:
                self._verify_selection(selection)
            except ValueError:
                return None
            overlap = _selected_midi_overlap(selection)
            expected = {
                "selection_sha256": _selection_hash(catalog, selection),
                "selected_midi_overlap_sha256": _document_hash(overlap),
                "bpm": _project_bpm(catalog),
                "policy": _RENDER_POLICY,
            }
            soundfont_sha256 = self._available_soundfont_sha256()
            if soundfont_sha256:
                expected["soundfont_sha256"] = soundfont_sha256
            return self._find_cached("arrangements", ARRANGEMENT_SCHEMA, expected)

    def selected_midi_overlap(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return path-free overlap evidence for the active explicit selection."""

        selection = selected_candidates(catalog, current)
        self._verify_selection(selection)
        return _selected_midi_overlap(selection)

    def render_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        selection = selected_candidates(catalog, current)
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before rendering"
            )
        self._verify_selection(selection)
        bpm = _project_bpm(catalog)
        soundfont = self._soundfont()
        selection_sha256 = _selection_hash(catalog, selection)
        overlap = _selected_midi_overlap(selection)
        key_payload = {
            "schema": ARRANGEMENT_SCHEMA,
            "selection_sha256": selection_sha256,
            "selected_midi_overlap_sha256": _document_hash(overlap),
            "bpm": bpm,
            "policy": _RENDER_POLICY,
            "soundfont_sha256": soundfont["sha256"],
        }
        cache_key = _document_hash(key_payload)
        with self._lock:
            cached = self._load_cached("arrangements", cache_key, ARRANGEMENT_SCHEMA)
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            tracks = _arrangement_tracks(selection)
            work, final = self._building_directory("arrangements", cache_key)
            try:
                midi_path = work / "selected-arrangement-proxy.mid"
                wav_path = work / "selected-arrangement-proxy.wav"
                write_midi_file(midi_path, tracks, bpm=bpm)
                render_midi_to_wav(
                    midi_path,
                    wav_path,
                    soundfont_path=soundfont["path"],
                )
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "soundfont": _without_path(soundfont),
                    "selection": _public_selection(selection),
                    "selected_midi_overlap": overlap,
                    "track_count": len(tracks),
                    "midi": _relative_file_record(midi_path, work),
                    "preview": _relative_file_record(wav_path, work),
                    "timing_policy": (
                        "source MIDI note times preserved in seconds; proxy tempo set "
                        "to the inferred project BPM"
                    ),
                    "original_midi_mutated": False,
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_cached("arrangements", cache_key, ARRANGEMENT_SCHEMA)
            if result is None:
                raise RuntimeError("arrangement cache verification failed")
            result["cache_hit"] = False
            return result

    def build_garageband_handoff(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        selection = selected_candidates(catalog, current)
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before exporting"
            )
        self._verify_selection(selection)
        overlap = _selected_midi_overlap(selection)
        unresolved_overlap = [
            pair
            for pair in overlap["pairs"]
            if pair["substantial_overlap"]
            and not pair["both_decisions_confirmed_in_full_mix"]
        ]
        if unresolved_overlap:
            raise ValueError(
                "GarageBand handoff is blocked because selected candidates derived "
                "from the same candidate-origin source audio have substantial "
                "exact-pitch/onset overlap; review and save both choices in full_mix "
                "context before exporting"
            )
        arrangement = self.render_arrangement(catalog, current)
        selection_sha256 = _selection_hash(catalog, selection)
        key_payload = {
            "schema": GARAGEBAND_HANDOFF_SCHEMA,
            "selection_sha256": selection_sha256,
            "selected_midi_overlap_sha256": _document_hash(overlap),
            "arrangement_sha256": arrangement["midi"]["sha256"],
            "arrangement_preview_sha256": arrangement["preview"]["sha256"],
        }
        cache_key = _document_hash(key_payload)
        pack_dir = self.root / "handoffs" / cache_key
        zip_path = pack_dir / "sunofriend-garageband-handoff.zip"
        manifest_path = pack_dir / "manifest.json"
        with self._lock:
            cached = self._load_handoff(zip_path, manifest_path)
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            work = pack_dir.with_name(f".{pack_dir.name}.building-{uuid.uuid4().hex}")
            _remove_generated_path(pack_dir)
            work.mkdir(parents=True, exist_ok=False)
            try:
                pack_manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "project": {
                        "project_id": catalog.get("project_id"),
                        "name": catalog.get("name"),
                        "bpm": catalog.get("setup", {}).get("bpm"),
                        "key": catalog.get("setup", {}).get("key"),
                        "tuning_hz": catalog.get("setup", {}).get("tuning_hz"),
                        "downbeat": catalog.get("setup", {}).get("downbeat"),
                    },
                    "selection": _public_selection(selection),
                    "selected_midi_overlap": overlap,
                    "selection_policy": (
                        "only the latest explicit main choice and explicit optional "
                        "choices are included"
                    ),
                    "original_midi_mutated": False,
                    "arrangement_proxy": {
                        "sha256": arrangement["midi"]["sha256"],
                        "preview_sha256": arrangement["preview"]["sha256"],
                        "policy": arrangement["policy"],
                    },
                    "private_notes_included": False,
                    "source_audio_included": False,
                }
                zip_build = work / zip_path.name
                with zipfile.ZipFile(
                    zip_build, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    _zip_text(
                        archive,
                        "README.txt",
                        _garageband_readme(catalog, len(selection)),
                    )
                    _zip_text(
                        archive,
                        "sunofriend-garageband-handoff.json",
                        json.dumps(pack_manifest, indent=2, sort_keys=True) + "\n",
                    )
                    for index, item in enumerate(selection, start=1):
                        self._verify_catalog_record(
                            item["midi"], label="selected candidate MIDI"
                        )
                        role = _safe_token(str(item["role"]))
                        decision = _safe_token(str(item["decision"]))
                        name = f"{index:02d}-{role}-{decision}.mid"
                        _zip_file(archive, f"MIDI/{name}", Path(item["midi_path"]))
                    _zip_file(
                        archive,
                        "MIDI/selected-arrangement-proxy.mid",
                        Path(arrangement["midi"]["path"]),
                    )
                    _zip_file(
                        archive,
                        "PREVIEW/selected-arrangement-proxy.wav",
                        Path(arrangement["preview"]["path"]),
                    )
                manifest = {
                    **pack_manifest,
                    "zip": _relative_file_record(zip_build, work),
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(pack_dir)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_handoff(zip_path, manifest_path)
            if result is None:
                raise RuntimeError("GarageBand handoff cache verification failed")
            result["cache_hit"] = False
            return result

    def garageband_pack_plan(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return the path-free, hash-pinned inventory for a custom DAW pack."""

        selection = selected_candidates(catalog, current)
        self._verify_selection(selection)
        overlap = _selected_midi_overlap(selection)
        selection_sha256 = _selection_hash(catalog, selection)
        basket_scope_sha256 = _pack_basket_scope_hash(catalog, selection)
        items, _ = _garageband_pack_inventory(
            catalog,
            selection,
            basket_scope_sha256=basket_scope_sha256,
        )
        block_reasons: list[str] = []
        if not selection:
            block_reasons.append("no-selected-midi")
        if overlap["unconfirmed_substantial_overlap_pair_count"]:
            block_reasons.append("selected-midi-overlap-needs-full-mix-confirmation")
        setup = catalog.get("setup", {})
        plan: dict[str, Any] = {
            "schema": GARAGEBAND_PACK_PLAN_SCHEMA,
            "project_id": catalog.get("project_id"),
            "selection_sha256": selection_sha256,
            "basket_scope_sha256": basket_scope_sha256,
            "items": items,
            "build_blocked": bool(block_reasons),
            "block_reasons": block_reasons,
            "selected_midi_overlap": overlap,
            "setup": {
                "bpm": setup.get("bpm"),
                "key": setup.get("key"),
                "tuning_hz": setup.get("tuning_hz"),
                "downbeat": setup.get("downbeat"),
            },
            "policies": {
                "musical_selection": (
                    "current explicit main and optional decisions define the result "
                    "space; the basket independently chooses copied files"
                ),
                "selected_midi": (
                    "checked MIDI files are copied byte-for-byte and remain "
                    "authoritative"
                ),
                "source_audio": (
                    "excluded by default and allowed only with explicit local opt-in"
                ),
                "arrangement_proxy": (
                    "one generated dry MIDI/WAV audition pair; not an authoritative "
                    "GarageBand instrument choice"
                ),
            },
            "effects": {
                "musical_selection_changed": False,
                "midi_mutated": False,
                "feedback_recorded": False,
                "mixer_state_used": False,
            },
        }
        default_ids = [
            str(item["item_id"]) for item in items if item.get("default_included")
        ]
        if default_ids:
            plan["default_basket"] = canonical_garageband_pack_basket(
                plan,
                default_ids,
                source_audio_opt_in=False,
            )
        else:
            empty_basket = {
                "schema": GARAGEBAND_PACK_BASKET_SCHEMA,
                "project_id": catalog.get("project_id"),
                "basket_scope_sha256": basket_scope_sha256,
                "included_item_ids": [],
                "source_audio_opt_in": False,
            }
            empty_basket["basket_sha256"] = _document_hash(empty_basket)
            plan["default_basket"] = empty_basket
        plan["plan_sha256"] = _pack_plan_hash(plan)
        return plan

    def build_garageband_pack(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        plan_sha256: str,
        basket: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build one deterministic ZIP from a previously displayed pack basket."""

        plan = self.garageband_pack_plan(catalog, current)
        if plan_sha256 != plan["plan_sha256"]:
            raise WorkbenchPackConflictError(
                "GarageBand pack plan changed; review the current basket before building"
            )
        if basket.get("basket_scope_sha256") != plan["basket_scope_sha256"]:
            raise WorkbenchPackConflictError(
                "GarageBand basket no longer describes the current musical selection"
            )
        included_item_ids = basket.get("included_item_ids")
        source_audio_opt_in = basket.get("source_audio_opt_in")
        canonical = canonical_garageband_pack_basket(
            plan,
            included_item_ids,
            source_audio_opt_in=source_audio_opt_in,
        )
        for key in (
            "schema",
            "project_id",
            "basket_scope_sha256",
            "included_item_ids",
            "source_audio_opt_in",
            "basket_sha256",
        ):
            if basket.get(key) != canonical[key]:
                raise ValueError("GarageBand basket changed after it was canonicalised")
        if plan["build_blocked"]:
            reasons = ", ".join(str(value) for value in plan["block_reasons"])
            raise ValueError(f"GarageBand pack build is blocked: {reasons}")

        selection = selected_candidates(catalog, current)
        self._verify_selection(selection)
        public_items, internal_items = _garageband_pack_inventory(
            catalog,
            selection,
            basket_scope_sha256=str(plan["basket_scope_sha256"]),
        )
        if public_items != plan["items"]:
            raise WorkbenchPackConflictError(
                "GarageBand pack inventory changed; reload the current plan"
            )
        included_ids = set(canonical["included_item_ids"])
        included_items = [
            item for item in public_items if item["item_id"] in included_ids
        ]
        verified_input_payloads: dict[str, bytes] = {}
        for item in included_items:
            if item["kind"] == "arrangement_proxy":
                continue
            item_id = str(item["item_id"])
            internal = internal_items.get(item_id)
            if internal is None:
                raise WorkbenchPackConflictError(
                    "GarageBand pack item is no longer available"
                )
            kind = str(item["kind"])
            verified_input_payloads[item_id] = _verified_record_bytes(
                internal["record"],
                label=(
                    "selected candidate MIDI"
                    if kind == "selected_midi"
                    else "source audio"
                ),
            )
        include_proxy = any(
            item["kind"] == "arrangement_proxy" for item in included_items
        )
        arrangement = (
            self.render_arrangement(catalog, current) if include_proxy else None
        )

        key_payload: dict[str, Any] = {
            "schema": GARAGEBAND_PACK_SCHEMA,
            "project_id": catalog.get("project_id"),
            "selection_sha256": plan["selection_sha256"],
            "basket_scope_sha256": plan["basket_scope_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "basket_sha256": canonical["basket_sha256"],
            "included_item_ids": list(canonical["included_item_ids"]),
        }
        if arrangement is not None:
            key_payload["arrangement_proxy"] = {
                "midi_sha256": arrangement["midi"]["sha256"],
                "preview_sha256": arrangement["preview"]["sha256"],
            }
        cache_key = _document_hash(key_payload)
        pack_dir = self.root / "packs" / cache_key
        zip_path = pack_dir / "sunofriend-garageband-pack.zip"
        manifest_path = pack_dir / "manifest.json"
        with self._lock:
            cached = self._load_pack(
                zip_path,
                manifest_path,
                expected_key_payload=key_payload,
            )
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            work = pack_dir.with_name(f".{pack_dir.name}.building-{uuid.uuid4().hex}")
            _remove_generated_path(pack_dir)
            work.mkdir(parents=True, exist_ok=False)
            try:
                copied: list[dict[str, Any]] = []
                payloads: list[tuple[str, bytes]] = []
                for item in included_items:
                    item_id = str(item["item_id"])
                    kind = str(item["kind"])
                    if kind == "arrangement_proxy":
                        if arrangement is None:  # pragma: no cover - guarded above
                            raise RuntimeError("arrangement proxy was not prepared")
                        proxy_records = (
                            (
                                "MIDI/selected-arrangement-proxy.mid",
                                arrangement["midi"],
                                "arrangement proxy MIDI",
                            ),
                            (
                                "PREVIEW/selected-arrangement-proxy.wav",
                                arrangement["preview"],
                                "arrangement proxy preview",
                            ),
                        )
                        for archive_path, record, label in proxy_records:
                            data = _verified_record_bytes(record, label=label)
                            payloads.append((archive_path, data))
                            copied.append(
                                _pack_manifest_item(
                                    item_id=item_id,
                                    kind=kind,
                                    archive_path=archive_path,
                                    data=data,
                                )
                            )
                        continue
                    data = verified_input_payloads[item_id]
                    archive_path = str(item["archive_paths"][0])
                    payloads.append((archive_path, data))
                    copied.append(
                        _pack_manifest_item(
                            item_id=item_id,
                            kind=kind,
                            archive_path=archive_path,
                            data=data,
                        )
                    )

                source_count = sum(
                    item["kind"] == "source_audio" for item in included_items
                )
                midi_count = sum(
                    item["kind"] == "selected_midi" for item in included_items
                )
                pack_manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "schema": GARAGEBAND_PACK_SCHEMA,
                    "setup": dict(plan["setup"]),
                    "included_items": copied,
                    "selected_midi_count": midi_count,
                    "source_audio_count": source_count,
                    "source_audio_included": source_count > 0,
                    "source_audio_opt_in": canonical["source_audio_opt_in"],
                    "arrangement_proxy_included": include_proxy,
                    "selected_midi_overlap": plan["selected_midi_overlap"],
                    "selection_policy": (
                        "the basket is explicit and separate from current musical "
                        "main/optional decisions"
                    ),
                    "private_notes_included": False,
                    "absolute_paths_included": False,
                    "original_midi_mutated": False,
                }
                zip_build = work / zip_path.name
                with zipfile.ZipFile(
                    zip_build, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    _zip_text(
                        archive,
                        "README.txt",
                        _garageband_pack_readme(
                            catalog,
                            selected_midi_count=midi_count,
                            source_audio_count=source_count,
                            arrangement_proxy_included=include_proxy,
                        ),
                    )
                    _zip_text(
                        archive,
                        "sunofriend-garageband-pack.json",
                        json.dumps(pack_manifest, indent=2, sort_keys=True) + "\n",
                    )
                    for archive_path, data in payloads:
                        _zip_bytes(archive, archive_path, data)
                manifest = {
                    **pack_manifest,
                    "zip": _relative_file_record(zip_build, work),
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(pack_dir)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_pack(
                zip_path,
                manifest_path,
                expected_key_payload=key_payload,
            )
            if result is None:
                raise RuntimeError("GarageBand pack cache verification failed")
            result["cache_hit"] = False
            return result

    def _soundfont(self) -> dict[str, Any]:
        if self._soundfont_cache is not None:
            self._verify_catalog_record(
                self._soundfont_cache, label="SoundFont", restart_hint=True
            )
            return dict(self._soundfont_cache)
        path = self.soundfont_path or Path(find_soundfont()).resolve()
        if not path.is_file():
            raise ValueError(f"SoundFont file does not exist: {path}")
        self._soundfont_cache = _file_record(path)
        return dict(self._soundfont_cache)

    def _verify_selection(self, selection: Sequence[Mapping[str, Any]]) -> None:
        for item in selection:
            if item.get("audition_blocked"):
                reasons = ", ".join(
                    str(value) for value in item.get("block_reasons", [])
                )
                raise ValueError(
                    "a previously selected AI candidate is now diagnostic-only"
                    + (f": {reasons}" if reasons else "")
                )
            self._verify_catalog_record(item["midi"], label="selected candidate MIDI")

    def _verify_catalog_record(
        self,
        record: Mapping[str, Any],
        *,
        label: str,
        restart_hint: bool = False,
    ) -> Path:
        path = Path(str(record.get("path", ""))).resolve()
        if not path.is_file():
            raise ValueError(f"{label} no longer exists: {path}")
        stat = path.stat()
        expected_bytes = record.get("bytes")
        expected_sha256 = str(record.get("sha256", ""))
        verified = stat.st_size == expected_bytes and _sha256(path) == expected_sha256
        if not verified:
            suffix = (
                "; restart the Workbench to catalog it again" if restart_hint else ""
            )
            raise ValueError(f"{label} changed after it was catalogued{suffix}")
        return path

    def _available_soundfont_sha256(self) -> str | None:
        if self._soundfont_cache is not None or self.soundfont_path is not None:
            return str(self._soundfont()["sha256"])
        try:
            return str(self._soundfont()["sha256"])
        except (OSError, RuntimeError, ValueError):
            # A machine with no renderer/bank can still inspect existing
            # candidates. Once a bank is explicit or has been used in this
            # session, however, drift is an integrity error and is never hidden.
            return None

    def _building_directory(self, family: str, cache_key: str) -> tuple[Path, Path]:
        parent = self.root / family
        parent.mkdir(parents=True, exist_ok=True)
        final = parent / cache_key
        _remove_generated_path(final)
        work = parent / f".{cache_key}.building-{uuid.uuid4().hex}"
        work.mkdir(parents=True, exist_ok=False)
        return work, final

    def _discard_new_preview(self, preview: Mapping[str, Any]) -> None:
        """Remove only a preview created by the current bounded operation."""

        cache_key = preview.get("cache_key")
        if preview.get("cache_hit") is not False or not _is_sha256(cache_key):
            return
        path = self.root / "previews" / str(cache_key)
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)

    def _find_cached(
        self,
        family: str,
        schema: str,
        expected: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        parent = self.root / family
        if not parent.is_dir():
            return None
        manifests: list[tuple[int, Path]] = []
        for path in parent.glob("*/manifest.json"):
            if not _is_sha256(path.parent.name):
                continue
            try:
                modified = path.stat().st_mtime_ns
            except OSError:
                continue
            manifests.append((modified, path))
        manifests.sort(key=lambda item: item[0], reverse=True)
        for _modified, path in manifests:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if document.get("schema") != schema:
                continue
            if any(document.get(key) != value for key, value in expected.items()):
                continue
            result = self._materialize(document, path.parent)
            if result is not None:
                result["cache_hit"] = True
                return result
        return None

    def _load_cached(
        self, family: str, cache_key: str, schema: str
    ) -> dict[str, Any] | None:
        root = self.root / family / cache_key
        path = root / "manifest.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("schema") != schema or document.get("cache_key") != cache_key:
            return None
        return self._materialize(document, root)

    def _materialize(
        self, document: Mapping[str, Any], root: Path
    ) -> dict[str, Any] | None:
        result = dict(document)
        for key in ("midi", "preview"):
            record = document.get(key)
            if not isinstance(record, Mapping):
                return None
            materialized = self._materialize_file_record(record, root)
            if materialized is None:
                return None
            result[key] = materialized
        return result

    def _verify_decoded_loop_inputs(
        self,
        *,
        source_record: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        previews: Sequence[Mapping[str, Any]],
        expected_soundfont_sha256: str,
    ) -> None:
        self._verify_catalog_record(source_record, label="source audio")
        for candidate in candidates:
            self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
        self._require_preview_renderer_consistency(
            previews,
            expected_soundfont_sha256=expected_soundfont_sha256,
        )
        for preview in previews:
            record = preview.get("preview")
            if not isinstance(record, Mapping):
                raise ValueError("neutral candidate preview record is invalid")
            self._verify_catalog_record(record, label="neutral candidate preview")

    def _verify_decoded_arrangement_inputs(
        self,
        *,
        source_groups: Sequence[Mapping[str, Any]],
        selection: Sequence[Mapping[str, Any]],
        previews: Sequence[Mapping[str, Any]],
        expected_soundfont_sha256: str,
    ) -> None:
        for group in source_groups:
            for record in group["records"]:
                self._verify_catalog_record(record, label="source audio")
        self._verify_selection(selection)
        self._require_preview_renderer_consistency(
            previews,
            expected_soundfont_sha256=expected_soundfont_sha256,
        )
        for preview in previews:
            record = preview.get("preview")
            if not isinstance(record, Mapping):
                raise ValueError("neutral selected MIDI preview record is invalid")
            self._verify_catalog_record(record, label="neutral selected MIDI preview")

    def _require_preview_renderer_consistency(
        self,
        previews: Sequence[Mapping[str, Any]],
        *,
        expected_soundfont_sha256: str,
    ) -> None:
        if not previews:
            raise ValueError("decoded comparison requires at least one preview")
        for preview in previews:
            if (
                preview.get("schema") != NEUTRAL_PREVIEW_SCHEMA
                or preview.get("policy") != _RENDER_POLICY
                or preview.get("soundfont_sha256") != expected_soundfont_sha256
            ):
                raise ValueError(
                    "decoded comparison requires every MIDI preview to use the "
                    "same current SoundFont and neutral renderer policy"
                )

    def _touch_and_prune_decoded_loop_cache(self, keep_cache_key: str) -> None:
        self._touch_and_prune_decoded_cache("decoded-stem-loops", keep_cache_key)

    def _touch_and_prune_decoded_cache(
        self, keep_family: str, keep_cache_key: str
    ) -> None:
        families = ("decoded-stem-loops", "decoded-arrangement-loops")
        if keep_family not in families:
            raise ValueError("unknown decoded cache family")
        current = self.root / keep_family / keep_cache_key
        if current.is_dir() and not current.is_symlink():
            current.touch(exist_ok=True)
        entries: list[Path] = []
        for family in families:
            parent = self.root / family
            if not parent.is_dir():
                continue
            entries.extend(
                path
                for path in parent.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and len(path.name) == 64
                and all(character in "0123456789abcdef" for character in path.name)
            )
        entries.sort(
            key=lambda path: (path == current, path.stat().st_mtime_ns),
            reverse=True,
        )
        retained_entries = 0
        retained_bytes = 0
        for entry in entries:
            entry_bytes = _directory_regular_file_bytes(entry)
            keep = entry == current or (
                retained_entries < _DECODED_LOOP_CACHE_MAXIMUM_ENTRIES
                and retained_bytes + entry_bytes <= _DECODED_LOOP_CACHE_MAXIMUM_BYTES
            )
            if keep:
                retained_entries += 1
                retained_bytes += entry_bytes
                continue
            _remove_generated_path(entry)

    def _private_building_directory(
        self, family: str, cache_key: str
    ) -> tuple[Path, Path]:
        parent = self.root / family
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _restrict_private_permissions(parent, 0o700)
        if family in {"decoded-stem-loops", "decoded-arrangement-loops"}:
            _prune_stale_private_builds(parent)
        final = parent / cache_key
        _remove_generated_path(final)
        work = parent / f".{cache_key}.building-{uuid.uuid4().hex}"
        work.mkdir(mode=0o700, parents=False, exist_ok=False)
        _restrict_private_permissions(work, 0o700)
        return work, final

    def _load_decoded_stem_loop(
        self,
        cache_key: str,
        expected_key_payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        root = self.root / "decoded-stem-loops" / cache_key
        manifest_path = root / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            document.get("schema") != DECODED_STEM_LOOP_SCHEMA
            or document.get("cache_key") != cache_key
            or root.name != cache_key
            or any(
                document.get(key) != value
                for key, value in expected_key_payload.items()
            )
        ):
            return None
        expected_window = expected_key_payload.get("window")
        if not isinstance(expected_window, Mapping) or (
            document.get("start_seconds")
            != expected_window.get("quantized_start_seconds")
            or document.get("end_seconds")
            != expected_window.get("quantized_end_seconds")
            or document.get("duration_seconds")
            != expected_window.get("logical_duration_seconds")
            or document.get("maximum_output_bytes")
            != _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
            or document.get("path_free_manifest") is not True
            or document.get("private_audio") is not True
            or document.get("effects")
            != {
                "midi_mutated": False,
                "selection_changed": False,
                "feedback_recorded": False,
                "event_appended": False,
            }
        ):
            return None
        records = document.get("tracks")
        fingerprints = expected_key_payload.get("input_fingerprints")
        if (
            not isinstance(records, list)
            or not isinstance(fingerprints, list)
            or len(records) != 1 + len(expected_key_payload.get("candidate_ids", []))
            or len(records) != len(fingerprints)
        ):
            return None
        materialized_tracks: list[dict[str, Any]] = []
        aggregate_bytes = 0
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                return None
            fingerprint = fingerprints[index]
            if not isinstance(fingerprint, Mapping):
                return None
            audio = record.get("audio")
            if not isinstance(audio, Mapping):
                return None
            relative_path = Path(str(audio.get("path", "")))
            if relative_path.is_absolute() or len(relative_path.parts) != 1:
                return None
            expected_kind = "source" if index == 0 else "candidate"
            if (
                record.get("kind") != expected_kind
                or record.get("track_id")
                != ("source" if index == 0 else f"candidate-{index}")
                or not isinstance(record.get("sample_rate"), int)
                or not isinstance(record.get("channels"), int)
                or not isinstance(record.get("frames"), int)
                or int(record["frames"]) <= 0
                or record.get("sample_rate") != fingerprint.get("sample_rate")
                or record.get("channels") != fingerprint.get("channels")
                or record.get("start_frame") != fingerprint.get("start_frame")
                or record.get("frames")
                != int(fingerprint.get("end_frame", 0))
                - int(fingerprint.get("start_frame", 0))
            ):
                return None
            if (
                index > 0
                and record.get("candidate_id")
                != expected_key_payload.get("candidate_ids", [])[index - 1]
            ):
                return None
            materialized_audio = self._materialize_file_record(audio, root)
            if materialized_audio is None:
                return None
            aggregate_bytes += int(materialized_audio["bytes"])
            materialized_track = dict(record)
            materialized_track["audio"] = materialized_audio
            materialized_tracks.append(materialized_track)
        if (
            aggregate_bytes != document.get("aggregate_output_bytes")
            or aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
        ):
            return None
        _restrict_private_permissions(root, 0o700)
        _restrict_private_permissions(manifest_path, 0o600)
        for track in materialized_tracks:
            _restrict_private_permissions(Path(track["audio"]["path"]), 0o600)
        result = dict(document)
        result["tracks"] = materialized_tracks
        return result

    def _load_decoded_arrangement_loop(
        self,
        cache_key: str,
        expected_key_payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        root = self.root / "decoded-arrangement-loops" / cache_key
        manifest_path = root / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            document.get("schema") != DECODED_ARRANGEMENT_LOOP_SCHEMA
            or document.get("cache_key") != cache_key
            or root.name != cache_key
            or any(
                document.get(key) != value
                for key, value in expected_key_payload.items()
            )
        ):
            return None
        expected_window = expected_key_payload.get("window")
        if not isinstance(expected_window, Mapping) or (
            document.get("start_seconds")
            != expected_window.get("quantized_start_seconds")
            or document.get("end_seconds")
            != expected_window.get("quantized_end_seconds")
            or document.get("duration_seconds")
            != expected_window.get("logical_duration_seconds")
            or document.get("maximum_output_bytes")
            != _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
            or document.get("path_free_manifest") is not True
            or document.get("private_audio") is not True
            or document.get("effects") != _decoded_arrangement_effects()
        ):
            return None
        records = document.get("tracks")
        fingerprints = expected_key_payload.get("input_fingerprints")
        if (
            not isinstance(records, list)
            or not isinstance(fingerprints, list)
            or len(records) != len(fingerprints)
            or len(records) < 2
            or len(records) > _DECODED_ARRANGEMENT_MAXIMUM_TRACKS
        ):
            return None
        identity_keys = (
            "track_id",
            "kind",
            "stem_ids",
            "roles",
            "source_sha256",
            "stem_id",
            "candidate_id",
            "role",
            "decision",
            "source_midi_sha256",
        )
        materialized_tracks: list[dict[str, Any]] = []
        aggregate_bytes = 0
        for record, fingerprint in zip(records, fingerprints):
            if not isinstance(record, Mapping) or not isinstance(fingerprint, Mapping):
                return None
            audio = record.get("audio")
            if not isinstance(audio, Mapping):
                return None
            relative_path = Path(str(audio.get("path", "")))
            expected_frames = int(fingerprint.get("end_frame", 0)) - int(
                fingerprint.get("start_frame", 0)
            )
            silence_padded = record.get("silence_padded_frames")
            if (
                relative_path.is_absolute()
                or len(relative_path.parts) != 1
                or record.get("kind") not in {"source", "selected_midi"}
                or any(
                    record.get(key) != fingerprint.get(key)
                    for key in identity_keys
                    if key in fingerprint
                )
                or record.get("sample_rate") != fingerprint.get("sample_rate")
                or record.get("channels") != fingerprint.get("channels")
                or record.get("start_frame") != fingerprint.get("start_frame")
                or record.get("frames") != expected_frames
                or not isinstance(silence_padded, int)
                or isinstance(silence_padded, bool)
                or silence_padded < 0
                or silence_padded > expected_frames
            ):
                return None
            materialized_audio = self._materialize_file_record(audio, root)
            if materialized_audio is None:
                return None
            aggregate_bytes += int(materialized_audio["bytes"])
            materialized_track = dict(record)
            materialized_track["audio"] = materialized_audio
            materialized_tracks.append(materialized_track)
        if (
            aggregate_bytes != document.get("aggregate_output_bytes")
            or aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
        ):
            return None
        expected_ids = {
            str(track_id)
            for group in expected_key_payload.get("groups", {}).values()
            for track_id in group
        }
        if expected_ids != {str(track["track_id"]) for track in materialized_tracks}:
            return None
        _restrict_private_permissions(root, 0o700)
        _restrict_private_permissions(manifest_path, 0o600)
        for track in materialized_tracks:
            _restrict_private_permissions(Path(track["audio"]["path"]), 0o600)
        result = dict(document)
        result["tracks"] = materialized_tracks
        return result

    def _load_handoff(
        self, zip_path: Path, manifest_path: Path
    ) -> dict[str, Any] | None:
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("schema") != GARAGEBAND_HANDOFF_SCHEMA:
            return None
        record = document.get("zip")
        if not isinstance(record, Mapping):
            return None
        materialized = self._materialize_file_record(record, manifest_path.parent)
        if materialized is None or materialized["path"] != str(zip_path):
            return None
        result = dict(document)
        result["zip"] = materialized
        return result

    def _load_pack(
        self,
        zip_path: Path,
        manifest_path: Path,
        *,
        expected_key_payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("schema") != GARAGEBAND_PACK_SCHEMA:
            return None
        expected_cache_key = _document_hash(expected_key_payload)
        if (
            document.get("cache_key") != expected_cache_key
            or zip_path.parent.name != expected_cache_key
            or any(
                document.get(key) != value
                for key, value in expected_key_payload.items()
            )
        ):
            return None
        record = document.get("zip")
        if not isinstance(record, Mapping):
            return None
        materialized = self._materialize_file_record(record, manifest_path.parent)
        if materialized is None or materialized["path"] != str(zip_path):
            return None
        result = dict(document)
        result["zip"] = materialized
        return result

    def _materialize_file_record(
        self, record: Mapping[str, Any], root: Path
    ) -> dict[str, Any] | None:
        path = (root / str(record.get("path", ""))).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return None
        if not path.is_file() or path.stat().st_size != record.get("bytes"):
            return None
        verified = _sha256(path) == record.get("sha256")
        if not verified:
            return None
        result = dict(record)
        result["path"] = str(path)
        return result


def decoded_arrangement_selection_manifest(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the canonical, path-free selected-arrangement audition manifest."""

    manifest, _source_groups, _selection = _decoded_arrangement_selection(
        catalog, current
    )
    return manifest


def selected_candidates(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Resolve only active explicit main and explicit optional choices."""

    states = current.get("stems", {})
    selected: list[dict[str, Any]] = []
    for stem in catalog.get("stems", []):
        stem_id = str(stem["stem_id"])
        state = states.get(stem_id, {})
        outcome = state.get("outcome")
        if isinstance(outcome, Mapping) and terminal_no_selection_outcome(
            outcome.get("value")
        ):
            continue
        main_id = state.get("main_candidate_id")
        decisions = state.get("candidates", {})
        role, _ = path_free_role(
            state.get("role") or stem.get("role") or "unclassified"
        )
        for candidate in stem.get("candidates", []):
            candidate_id = str(candidate["candidate_id"])
            decision = decisions.get(candidate_id, {})
            value = decision.get("decision")
            if decision.get("selection_active") is False:
                continue
            if not (
                (value == "main" and candidate_id == main_id) or value == "optional"
            ):
                continue
            ai_diagnostics = candidate.get("ai_diagnostics") or {}
            candidate_origin_sha256 = ai_diagnostics.get("source_audio_sha256")
            if candidate_origin_sha256:
                candidate_origin_basis = "verified-ai-source"
            else:
                candidate_origin_sha256 = stem["source"]["sha256"]
                candidate_origin_basis = "review-stem-source-fallback"
            selected.append(
                {
                    "stem_id": stem_id,
                    "stem_label": stem.get("label"),
                    "candidate_id": candidate_id,
                    "candidate_label": candidate.get("label"),
                    "process": candidate.get("process"),
                    "role": role,
                    "decision": value,
                    "decision_context": decision.get("context"),
                    "candidate_origin_source_audio_sha256": (candidate_origin_sha256),
                    "candidate_origin_source_audio_sha256_basis": (
                        candidate_origin_basis
                    ),
                    "audition_blocked": bool(candidate.get("audition_blocked")),
                    "block_reasons": list(
                        (candidate.get("ai_diagnostics") or {}).get("block_reasons", [])
                    ),
                    "midi_path": candidate["midi_path"],
                    "midi": dict(candidate["midi"]),
                }
            )
    return selected


def _decoded_arrangement_selection(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    source_groups = _decoded_arrangement_source_groups(catalog, current)
    selection = selected_candidates(catalog, current)
    selected_rows: list[dict[str, Any]] = []
    decorated_selection: list[dict[str, Any]] = []
    track_ids = {str(group["track_id"]) for group in source_groups}
    for item in selection:
        midi = _decoded_record_identity(item.get("midi"), label="candidate MIDI")
        track_id = (
            "midi-"
            + _document_hash(
                {
                    "stem_id": item.get("stem_id"),
                    "candidate_id": item.get("candidate_id"),
                    "midi_sha256": midi["sha256"],
                }
            )[:24]
        )
        if track_id in track_ids:
            raise ValueError("decoded arrangement track identities are not unique")
        track_ids.add(track_id)
        selected_rows.append(
            {
                "track_id": track_id,
                "stem_id": str(item["stem_id"]),
                "candidate_id": str(item["candidate_id"]),
                "role": path_free_role(item.get("role"))[0],
                "decision": str(item["decision"]),
                "midi_sha256": midi["sha256"],
                "midi_bytes": midi["bytes"],
            }
        )
        decorated_selection.append({**item, "track_id": track_id})

    public_sources = [
        {
            "track_id": group["track_id"],
            "source_sha256": group["source_sha256"],
            "source_bytes": group["source_bytes"],
            "stem_ids": list(group["stem_ids"]),
            "roles": list(group["roles"]),
        }
        for group in source_groups
    ]
    source_ids = [str(source["track_id"]) for source in public_sources]
    midi_ids = [str(item["track_id"]) for item in selected_rows]
    groups = {
        "source-only": source_ids,
        "selected-midi": midi_ids,
        "hybrid": source_ids + midi_ids,
        "main-only": [
            str(item["track_id"])
            for item in selected_rows
            if item["decision"] == "main"
        ],
    }
    manifest: dict[str, Any] = {
        "schema": ARRANGEMENT_SELECTION_SCHEMA,
        "project_id": catalog.get("project_id"),
        "bpm": _project_bpm(catalog),
        "sources": public_sources,
        "selected_midi": selected_rows,
        "groups": groups,
    }
    manifest["selection_manifest_sha256"] = _document_hash(manifest)
    return manifest, source_groups, decorated_selection


def _decoded_arrangement_source_groups(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    states = current.get("stems", {})
    if not isinstance(states, Mapping):
        states = {}
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for stem in catalog.get("stems", []):
        if not isinstance(stem, Mapping):
            raise ValueError("decoded arrangement contains an invalid stem")
        stem_id = str(stem.get("stem_id", ""))
        if not stem_id:
            raise ValueError("decoded arrangement stem has no identity")
        record = stem.get("source")
        identity = _decoded_record_identity(record, label="source audio")
        digest = str(identity["sha256"])
        state = states.get(stem_id, {})
        if not isinstance(state, Mapping):
            state = {}
        role = path_free_role(state.get("role") or stem.get("role"))[0]
        if digest not in groups:
            order.append(digest)
            groups[digest] = {
                "track_id": f"source-{digest[:24]}",
                "source_sha256": digest,
                "source_bytes": identity["bytes"],
                "stem_ids": [],
                "roles": [],
                "records": [],
            }
        group = groups[digest]
        if group["source_bytes"] != identity["bytes"]:
            raise ValueError("duplicate source hash has inconsistent byte counts")
        group["stem_ids"].append(stem_id)
        if role not in group["roles"]:
            group["roles"].append(role)
        group["records"].append(record)
    if not order:
        raise ValueError("decoded arrangement requires at least one source stem")
    return [groups[digest] for digest in order]


def _decoded_record_identity(record: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError(f"{label} record is invalid")
    digest = record.get("sha256")
    byte_count = record.get("bytes")
    if not _is_sha256(digest):
        raise ValueError(f"{label} has no valid content hash")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise ValueError(f"{label} byte count is invalid")
    return {"sha256": str(digest), "bytes": byte_count}


def _decoded_arrangement_effects() -> dict[str, bool]:
    return {
        "source_audio_mutated": False,
        "midi_mutated": False,
        "selection_changed": False,
        "feedback_recorded": False,
        "event_appended": False,
        "automatic_selection": False,
        "automatic_ranking": False,
        "default_selection_changed": False,
    }


def canonical_garageband_pack_basket(
    plan: Mapping[str, Any],
    included_item_ids: Sequence[str] | Any,
    source_audio_opt_in: bool,
) -> dict[str, Any]:
    """Validate and canonicalise one explicit basket in server plan order."""

    if plan.get("schema") != GARAGEBAND_PACK_PLAN_SCHEMA:
        raise ValueError("unsupported GarageBand pack plan schema")
    recorded_plan_hash = plan.get("plan_sha256")
    if recorded_plan_hash is not None and recorded_plan_hash != _pack_plan_hash(plan):
        raise ValueError("GarageBand pack plan hash is invalid")
    project_id = plan.get("project_id")
    basket_scope_sha256 = plan.get("basket_scope_sha256")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("GarageBand pack plan has no project identity")
    if not _is_sha256(basket_scope_sha256):
        raise ValueError("GarageBand pack plan has no valid basket scope")
    if not isinstance(source_audio_opt_in, bool):
        raise ValueError("source_audio_opt_in must be true or false")
    if not isinstance(included_item_ids, (list, tuple)):
        raise ValueError("included_item_ids must be a list")
    if len(included_item_ids) > 512:
        raise ValueError("GarageBand basket contains too many items")
    if any(not isinstance(item_id, str) for item_id in included_item_ids):
        raise ValueError("GarageBand basket item IDs must be text")
    if len(set(included_item_ids)) != len(included_item_ids):
        raise ValueError("GarageBand basket item IDs must not be repeated")
    items = plan.get("items")
    if not isinstance(items, list):
        raise ValueError("GarageBand pack plan has no item inventory")
    inventory: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("GarageBand pack plan contains an invalid item")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or item_id in inventory:
            raise ValueError("GarageBand pack plan contains an invalid item ID")
        inventory[item_id] = item
    unknown = [item_id for item_id in included_item_ids if item_id not in inventory]
    if unknown:
        raise ValueError("GarageBand basket contains an unknown item ID")
    included = set(included_item_ids)
    canonical_ids = [
        str(item["item_id"]) for item in items if item["item_id"] in included
    ]
    selected_midi_count = sum(
        inventory[item_id].get("kind") == "selected_midi" for item_id in canonical_ids
    )
    if selected_midi_count < 1:
        raise ValueError("GarageBand basket must include at least one selected MIDI")
    source_audio_count = sum(
        inventory[item_id].get("kind") == "source_audio" for item_id in canonical_ids
    )
    if source_audio_count and not source_audio_opt_in:
        raise ValueError("source audio requires a separate explicit local pack opt-in")
    basket = {
        "schema": GARAGEBAND_PACK_BASKET_SCHEMA,
        "project_id": project_id,
        "basket_scope_sha256": basket_scope_sha256,
        "included_item_ids": canonical_ids,
        "source_audio_opt_in": source_audio_opt_in,
    }
    basket["basket_sha256"] = _document_hash(basket)
    return basket


def _pack_basket_scope_hash(
    catalog: Mapping[str, Any], selection: Sequence[Mapping[str, Any]]
) -> str:
    """Hash export eligibility while deliberately ignoring listening context."""

    setup = catalog.get("setup", {})
    return _document_hash(
        {
            "schema": GARAGEBAND_PACK_BASKET_SCHEMA,
            "project_id": catalog.get("project_id"),
            "setup": {
                "bpm": setup.get("bpm"),
                "key": setup.get("key"),
                "tuning_hz": setup.get("tuning_hz"),
                "downbeat": setup.get("downbeat"),
            },
            "selection": _public_selection(selection),
        }
    )


def _garageband_pack_inventory(
    catalog: Mapping[str, Any],
    selection: Sequence[Mapping[str, Any]],
    *,
    basket_scope_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return a public inventory plus server-only records for copied inputs."""

    items: list[dict[str, Any]] = []
    internal: dict[str, dict[str, Any]] = {}
    for index, selected in enumerate(selection, start=1):
        role = str(selected["role"])
        decision = str(selected["decision"])
        item_id = _pack_item_id(
            {
                "kind": "selected_midi",
                "stem_id": selected["stem_id"],
                "candidate_id": selected["candidate_id"],
                "midi_sha256": selected["midi"]["sha256"],
                "basket_scope_sha256": basket_scope_sha256,
            }
        )
        archive_path = (
            f"MIDI/{index:02d}-{_safe_token(role)}-{_safe_token(decision)}.mid"
        )
        item = {
            "item_id": item_id,
            "kind": "selected_midi",
            "label": f"{role.replace('_', ' ').title()} — {decision}",
            "stem_id": selected["stem_id"],
            "candidate_id": selected["candidate_id"],
            "candidate_label": selected.get("candidate_label"),
            "process": selected.get("process"),
            "role": role,
            "decision": decision,
            "selection_index": index,
            "default_included": True,
            "generated": False,
            "archive_paths": [archive_path],
            "bytes": selected["midi"]["bytes"],
            "content_sha256": selected["midi"]["sha256"],
        }
        items.append(item)
        internal[item_id] = {"record": dict(selected["midi"])}

    if selection:
        proxy_id = _pack_item_id(
            {
                "kind": "arrangement_proxy",
                "basket_scope_sha256": basket_scope_sha256,
            }
        )
        items.append(
            {
                "item_id": proxy_id,
                "kind": "arrangement_proxy",
                "label": "Dry selected-arrangement proxy MIDI and WAV",
                "default_included": True,
                "generated": True,
                "archive_paths": [
                    "MIDI/selected-arrangement-proxy.mid",
                    "PREVIEW/selected-arrangement-proxy.wav",
                ],
            }
        )

    source_groups: dict[str, dict[str, Any]] = {}
    for stem in catalog.get("stems", []):
        record = stem.get("source")
        if not isinstance(record, Mapping):
            continue
        sha256 = str(record.get("sha256", ""))
        if not _is_sha256(sha256):
            raise ValueError("Workbench source audio has no valid content hash")
        group = source_groups.setdefault(
            sha256,
            {
                "record": dict(record),
                "roles": [],
                "labels": [],
                "stem_ids": [],
            },
        )
        role = path_free_role(stem.get("role"))[0]
        label = str(stem.get("label") or role.replace("_", " ").title())
        if role not in group["roles"]:
            group["roles"].append(role)
        if label not in group["labels"]:
            group["labels"].append(label)
        stem_id = str(stem.get("stem_id") or "")
        if stem_id and stem_id not in group["stem_ids"]:
            group["stem_ids"].append(stem_id)
    for source_index, (sha256, group) in enumerate(source_groups.items(), start=1):
        roles = list(group["roles"])
        record = group["record"]
        suffix = Path(str(record.get("name") or record.get("path") or ".wav")).suffix
        suffix = suffix.lower() if suffix else ".wav"
        if not suffix.startswith(".") or not suffix[1:].isalnum():
            suffix = ".wav"
        role_token = _safe_token(roles[0] if len(roles) == 1 else "shared-source")
        archive_path = f"STEMS/{source_index:02d}-{role_token}-source{suffix}"
        item_id = _pack_item_id(
            {
                "kind": "source_audio",
                "source_sha256": sha256,
                "basket_scope_sha256": basket_scope_sha256,
            }
        )
        items.append(
            {
                "item_id": item_id,
                "kind": "source_audio",
                "label": " / ".join(group["labels"]),
                "roles": roles,
                "stem_ids": list(group["stem_ids"]),
                "source_index": source_index,
                "default_included": False,
                "generated": False,
                "archive_paths": [archive_path],
                "bytes": record.get("bytes"),
                "content_sha256": sha256,
            }
        )
        internal[item_id] = {"record": record}
    return items, internal


def _pack_item_id(payload: Mapping[str, Any]) -> str:
    return "pack-item-" + _document_hash(payload)


def _pack_plan_hash(plan: Mapping[str, Any]) -> str:
    return _document_hash(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _arrangement_tracks(selection: Sequence[Mapping[str, Any]]) -> list[MidiTrack]:
    drum_notes: list[NoteEvent] = []
    melodic: list[tuple[Mapping[str, Any], list[NoteEvent]]] = []
    for item in selection:
        clips = read_midi_clips(item["midi_path"], role=str(item["role"]))
        notes = _clips_to_notes(clips)
        if not notes:
            continue
        if _is_drum_role(str(item["role"])):
            drum_notes.extend(notes)
        else:
            melodic.append((item, notes))
    if len(melodic) > len(_MELODIC_CHANNELS):
        raise ValueError(
            "the proxy arrangement supports at most 15 selected pitched parts; "
            "mark fewer alternatives optional"
        )
    tracks: list[MidiTrack] = []
    if drum_notes:
        tracks.append(MidiTrack("Selected drums", 9, 0, drum_notes))
    for channel, (item, notes) in zip(_MELODIC_CHANNELS, melodic):
        role = str(item["role"])
        decision = str(item["decision"])
        tracks.append(
            MidiTrack(
                f"{_track_name(role)} ({decision})",
                channel,
                _program_for_role(role),
                notes,
            )
        )
    if not tracks:
        raise ValueError("the selected MIDI files contain no playable notes")
    return tracks


def _clips_to_notes(clips: Sequence[Any]) -> list[NoteEvent]:
    notes = []
    for clip in clips:
        for note in clip.notes:
            notes.append(
                NoteEvent(
                    start=float(note.source_start_seconds),
                    end=float(note.source_end_seconds),
                    pitch=int(note.pitch),
                    velocity=int(note.velocity),
                )
            )
    return sorted(notes, key=lambda note: (note.start, note.pitch, note.end))


def _decoded_loop_window(start_seconds: Any, end_seconds: Any) -> tuple[float, float]:
    if isinstance(start_seconds, bool) or isinstance(end_seconds, bool):
        raise ValueError("decoded loop bounds must be finite numbers")
    try:
        start = float(start_seconds)
        end = float(end_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("decoded loop bounds must be finite numbers") from exc
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("decoded loop bounds must be finite numbers")
    if start < 0.0:
        raise ValueError("decoded loop start must be zero or greater")
    if start > _DECODED_LOOP_MAXIMUM_START_SECONDS:
        raise ValueError("decoded loop start must be within the first 24 hours")
    duration = end - start
    if not _DECODED_LOOP_MINIMUM_SECONDS <= duration <= _DECODED_LOOP_MAXIMUM_SECONDS:
        raise ValueError("decoded loop duration must be between 0.5 and 15.0 seconds")
    return start, end


def _decoded_declared_input_bytes(records: Sequence[tuple[str, Any]]) -> int:
    """Validate and sum catalogued input sizes before expensive rendering."""

    total = 0
    for label, record in records:
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} record is invalid")
        value = record.get("bytes")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} byte count is invalid")
        total += value
    return total


def _require_decoded_input_limit(total_bytes: int) -> None:
    if total_bytes > _DECODED_LOOP_MAXIMUM_INPUT_BYTES:
        raise ValueError("decoded loop inputs exceed the 2 GiB aggregate safety limit")


def _decoded_pcm16_output_upper_bound(inputs: Sequence[Mapping[str, Any]]) -> int:
    """Return a conservative pre-write bound for separate PCM16 WAV tracks."""

    total = 0
    for item in inputs:
        start_frame = item.get("start_frame")
        end_frame = item.get("end_frame")
        channels = item.get("channels")
        if (
            isinstance(start_frame, bool)
            or not isinstance(start_frame, int)
            or isinstance(end_frame, bool)
            or not isinstance(end_frame, int)
            or end_frame <= start_frame
            or isinstance(channels, bool)
            or not isinstance(channels, int)
            or channels not in {1, 2}
        ):
            raise ValueError("decoded arrangement output geometry is invalid")
        total += (
            (end_frame - start_frame) * channels * 2
            + _DECODED_PCM16_WAV_HEADER_BUDGET_BYTES
        )
    return total


def _decoded_loop_candidate_ids(candidate_ids: Any) -> tuple[str, ...]:
    if isinstance(candidate_ids, (str, bytes)) or not isinstance(
        candidate_ids, Sequence
    ):
        raise ValueError("candidate_ids must be a sequence of catalog candidate IDs")
    values = tuple(candidate_ids)
    if not values:
        raise ValueError("choose at least one candidate for decoded comparison")
    if len(values) > _DECODED_LOOP_MAXIMUM_CANDIDATES:
        raise ValueError("decoded comparison supports at most 6 candidates")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("candidate_ids must contain non-empty strings")
    if len(set(values)) != len(values):
        raise ValueError("decoded comparison candidate IDs must be unique")
    return values


def _decoded_audio_modules() -> tuple[Any, Any]:
    try:
        import numpy as np
        import soundfile
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "decoded stem comparison requires the optional audio dependencies "
            "numpy and soundfile; install Sunofriend with the convert extra"
        ) from exc
    return np, soundfile


def _decoded_audio_info(soundfile: Any, path: Path, *, label: str) -> dict[str, int]:
    try:
        info = soundfile.info(str(path))
    except Exception as exc:
        raise ValueError(f"{label} is not a readable local audio file") from exc
    sample_rate = int(info.samplerate)
    channels = int(info.channels)
    frames = int(info.frames)
    if (
        not _DECODED_LOOP_MINIMUM_SAMPLE_RATE
        <= sample_rate
        <= (_DECODED_LOOP_MAXIMUM_SAMPLE_RATE)
    ):
        raise ValueError(f"{label} sample rate must be between 8 and 96 kHz")
    if channels not in {1, 2}:
        raise ValueError(f"{label} must be mono or stereo")
    if frames < 0:
        raise ValueError(f"{label} has an invalid frame count")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
    }


def _nearest_audio_frame(seconds: float, sample_rate: int) -> int:
    """Quantise seconds to the nearest frame using Python's ties-to-even rule."""

    return int(round(seconds * sample_rate))


def _read_padded_audio_window(
    np: Any,
    soundfile: Any,
    path: Path,
    *,
    start_frame: int,
    frames: int,
    channels: int,
) -> Any:
    output = np.zeros((frames, channels), dtype=np.float32)
    try:
        with soundfile.SoundFile(str(path), mode="r") as source:
            if int(source.channels) != channels:
                raise ValueError("audio channel count changed while decoding")
            available = max(0, int(len(source)) - start_frame)
            readable = min(frames, available)
            if readable:
                source.seek(start_frame)
                samples = source.read(
                    frames=readable,
                    dtype="float32",
                    always_2d=True,
                )
                if samples.shape != (readable, channels):
                    raise ValueError("decoded audio window has unexpected geometry")
                output[:readable, :] = samples
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("audio changed or became unreadable while decoding") from exc
    return output


def _restrict_private_permissions(path: Path, mode: int) -> None:
    """Set owner-only permissions for private decoded excerpts where supported."""

    try:
        path.chmod(mode)
    except NotImplementedError:  # pragma: no cover - platform-specific fallback
        pass


def _write_verified_private_snapshot(
    source_path: Path,
    expected_record: Mapping[str, Any],
    destination: Path,
    *,
    label: str,
) -> Path:
    """Copy one open input handle and verify the bytes used for decoding."""

    expected_bytes = expected_record.get("bytes")
    expected_sha256 = str(expected_record.get("sha256", ""))
    digest = hashlib.sha256()
    written = 0
    try:
        with source_path.open("rb") as source, destination.open("xb") as target:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                target.write(block)
                digest.update(block)
                written += len(block)
        _restrict_private_permissions(destination, 0o600)
        if written != expected_bytes or digest.hexdigest() != expected_sha256:
            raise ValueError(f"{label} changed while creating a verified snapshot")
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _directory_regular_file_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _prune_stale_private_builds(parent: Path) -> None:
    cutoff = time.time() - _DECODED_LOOP_BUILDING_MAXIMUM_AGE_SECONDS
    for path in parent.iterdir():
        if (
            not path.name.startswith(".")
            or ".building-" not in path.name
            or path.is_symlink()
        ):
            continue
        try:
            stale = path.is_dir() and path.stat().st_mtime < cutoff
        except OSError:
            continue
        if stale:
            _remove_generated_path(path)


def _stem(catalog: Mapping[str, Any], stem_id: str) -> Mapping[str, Any]:
    for stem in catalog.get("stems", []):
        if stem.get("stem_id") == stem_id:
            return stem
    raise ValueError("unknown workbench stem_id")


def _candidate(
    catalog: Mapping[str, Any], stem_id: str, candidate_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    for stem in catalog.get("stems", []):
        if stem.get("stem_id") != stem_id:
            continue
        for candidate in stem.get("candidates", []):
            if candidate.get("candidate_id") == candidate_id:
                return stem, candidate
        raise ValueError("candidate_id does not belong to the selected stem")
    raise ValueError("unknown workbench stem_id")


def _project_bpm(catalog: Mapping[str, Any]) -> float:
    value = catalog.get("setup", {}).get("bpm")
    if value is None:
        raise ValueError(
            "the Workbench needs an inferred project BPM to render aligned previews"
        )
    bpm = float(value)
    if not 1.0 <= bpm <= 1000.0:
        raise ValueError("project BPM must be between 1 and 1000")
    return bpm


def _preview_role(stem: Mapping[str, Any], role_override: str | None) -> str:
    return path_free_role(stem.get("role") if role_override is None else role_override)[
        0
    ]


def _program_for_role(role: str) -> int:
    return _ROLE_PROGRAMS.get(role.lower(), 0)


def _is_drum_role(role: str) -> bool:
    return role.lower() in _DRUM_ROLES


def _track_name(role: str) -> str:
    return "Neutral " + role.replace("_", " ").strip().title()


def _selection_hash(
    catalog: Mapping[str, Any], selection: Sequence[Mapping[str, Any]]
) -> str:
    return _document_hash(
        {
            "project_id": catalog.get("project_id"),
            "bpm": catalog.get("setup", {}).get("bpm"),
            "selection": [
                {
                    **row,
                    "decision_context": item.get("decision_context"),
                }
                for item, row in zip(selection, _public_selection(selection))
            ],
        }
    )


def _selected_midi_overlap(
    selection: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare same-origin selected MIDI as bounded listening diagnostics only."""

    note_cache: dict[str, list[NoteEvent]] = {}

    def notes_for(item: Mapping[str, Any]) -> list[NoteEvent]:
        midi_sha256 = str(item["midi"]["sha256"])
        if midi_sha256 not in note_cache:
            clips = read_midi_clips(item["midi_path"], role=str(item["role"]))
            note_cache[midi_sha256] = _clips_to_notes(clips)
        return note_cache[midi_sha256]

    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(selection):
        for right in selection[left_index + 1 :]:
            candidate_origin_sha256 = str(
                left.get("candidate_origin_source_audio_sha256") or ""
            )
            if not candidate_origin_sha256 or candidate_origin_sha256 != right.get(
                "candidate_origin_source_audio_sha256"
            ):
                continue
            left_notes = notes_for(left)
            right_notes = notes_for(right)
            matched_note_count = _greedy_exact_pitch_onset_matches(
                left_notes,
                right_notes,
                tolerance_seconds=_OVERLAP_ONSET_TOLERANCE_SECONDS,
            )
            left_ratio = matched_note_count / len(left_notes) if left_notes else 0.0
            right_ratio = matched_note_count / len(right_notes) if right_notes else 0.0
            substantial = (
                matched_note_count >= _SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES
                and left_ratio >= _SUBSTANTIAL_OVERLAP_MINIMUM_RATIO
                and right_ratio >= _SUBSTANTIAL_OVERLAP_MINIMUM_RATIO
            )
            left_context = left.get("decision_context")
            right_context = right.get("decision_context")
            pairs.append(
                {
                    "candidate_origin_source_audio_sha256": (candidate_origin_sha256),
                    "left": {
                        "stem_id": left["stem_id"],
                        "candidate_id": left["candidate_id"],
                        "midi_sha256": left["midi"]["sha256"],
                        "decision_context": left_context,
                        "candidate_origin_source_audio_sha256_basis": left.get(
                            "candidate_origin_source_audio_sha256_basis"
                        ),
                    },
                    "right": {
                        "stem_id": right["stem_id"],
                        "candidate_id": right["candidate_id"],
                        "midi_sha256": right["midi"]["sha256"],
                        "decision_context": right_context,
                        "candidate_origin_source_audio_sha256_basis": right.get(
                            "candidate_origin_source_audio_sha256_basis"
                        ),
                    },
                    "left_note_count": len(left_notes),
                    "right_note_count": len(right_notes),
                    "matched_note_count": matched_note_count,
                    "left_overlap_ratio": round(left_ratio, 6),
                    "right_overlap_ratio": round(right_ratio, 6),
                    "substantial_overlap": substantial,
                    "both_decisions_confirmed_in_full_mix": (
                        left_context == "full_mix" and right_context == "full_mix"
                    ),
                }
            )
    return {
        "schema": SELECTED_MIDI_OVERLAP_SCHEMA,
        "heuristic": {
            "policy": "greedy-earliest-compatible-exact-pitch-onset-v1",
            "onset_tolerance_ms": 80,
            "minimum_matched_notes_for_substantial": (
                _SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES
            ),
            "minimum_overlap_ratio_for_each_candidate": (
                _SUBSTANTIAL_OVERLAP_MINIMUM_RATIO
            ),
        },
        "same_candidate_origin_pair_count": len(pairs),
        "substantial_overlap_pair_count": sum(
            1 for pair in pairs if pair["substantial_overlap"]
        ),
        "unconfirmed_substantial_overlap_pair_count": sum(
            1
            for pair in pairs
            if pair["substantial_overlap"]
            and not pair["both_decisions_confirmed_in_full_mix"]
        ),
        "pairs": pairs,
        "interpretation": (
            "diagnostic only: candidates are grouped by verified AI source audio, "
            "or by review-stem source for non-AI fallback; overlap does not establish "
            "accuracy, role separation, or preference and never changes a selection"
        ),
    }


def _greedy_exact_pitch_onset_matches(
    left: Sequence[NoteEvent],
    right: Sequence[NoteEvent],
    *,
    tolerance_seconds: float,
) -> int:
    """Count deterministic earliest-compatible matches within each exact pitch."""

    result = align_events(
        [
            AlignmentEvent(
                source_index=index,
                onset=note.start,
                pitch=note.pitch,
            )
            for index, note in enumerate(left)
        ],
        [
            AlignmentEvent(
                source_index=index,
                onset=note.start,
                pitch=note.pitch,
            )
            for index, note in enumerate(right)
        ],
        left_offset=0.0,
        right_offset=0.0,
        tolerance=tolerance_seconds,
        pitch_policy="exact_integer",
        require_exact_label=False,
    )
    return len(result.matches)


def _public_selection(selection: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stem_id": item["stem_id"],
            "candidate_id": item["candidate_id"],
            "role": item["role"],
            "decision": item["decision"],
            "process": item.get("process"),
            "midi_sha256": item["midi"]["sha256"],
            "midi_bytes": item["midi"]["bytes"],
            "candidate_origin_source_audio_sha256": item.get(
                "candidate_origin_source_audio_sha256"
            ),
            "candidate_origin_source_audio_sha256_basis": item.get(
                "candidate_origin_source_audio_sha256_basis"
            ),
        }
        for item in selection
    ]


def _garageband_readme(catalog: Mapping[str, Any], count: int) -> str:
    setup = catalog.get("setup", {})
    downbeat = setup.get("downbeat")
    return (
        "Sunofriend GarageBand handoff\n"
        "================================\n\n"
        f"Project: {catalog.get('name')}\n"
        f"Selected parts: {count}\n"
        f"Set GarageBand tempo to: {setup.get('bpm')} BPM\n"
        f"Project key: {setup.get('key') or 'not inferred'}\n"
        f"Source tuning: {setup.get('tuning_hz') or 'not inferred'} Hz\n"
        f"Downbeat: {downbeat if downbeat is not None else 'not confirmed'}\n\n"
        "1. Create or open a GarageBand project and set the tempo above before import.\n"
        "2. Drag each file in MIDI/ onto its own Software Instrument track.\n"
        "3. Choose a playable GarageBand patch for each track in the Library.\n"
        "4. Use selected-arrangement-proxy.mid only as a convenience full-mix audition.\n"
        "5. The numbered MIDI files are byte-for-byte copies of your explicit choices; "
        "they are the authoritative handoff.\n\n"
        "The proxy WAV uses one consistent local GM SoundFont and role-based programs. "
        "It is not a claim that those are the final GarageBand instruments.\n"
    )


def _garageband_pack_readme(
    catalog: Mapping[str, Any],
    *,
    selected_midi_count: int,
    source_audio_count: int,
    arrangement_proxy_included: bool,
) -> str:
    setup = catalog.get("setup", {})
    lines = [
        "Sunofriend GarageBand pack",
        "============================",
        "",
        f"Project: {catalog.get('name')}",
        f"Selected MIDI files: {selected_midi_count}",
        f"Opted-in source stems: {source_audio_count}",
        f"Set GarageBand tempo to: {setup.get('bpm')} BPM",
        f"Project key: {setup.get('key') or 'not inferred'}",
        f"Source tuning: {setup.get('tuning_hz') or 'not inferred'} Hz",
        (
            f"Downbeat: {setup.get('downbeat')}"
            if setup.get("downbeat") is not None
            else "Downbeat: not confirmed"
        ),
        "",
        "1. Set the GarageBand tempo above before importing files.",
        "2. Drag each checked file in MIDI/ onto its own Software Instrument track.",
        "3. Choose a playable GarageBand patch for every MIDI track.",
    ]
    if source_audio_count:
        lines.append(
            "4. Source audio in STEMS/ was included only by your explicit local opt-in."
        )
    else:
        lines.append("4. No source audio is included in this pack.")
    if arrangement_proxy_included:
        lines.append(
            "5. The selected-arrangement proxy is a dry convenience audition only."
        )
    else:
        lines.append("5. No generated arrangement proxy was requested.")
    lines.extend(
        [
            "",
            "The numbered MIDI files are byte-for-byte copies of the checked explicit",
            "choices. They are authoritative; the basket does not alter musical choices,",
            "MIDI notes, timing, velocities or GarageBand instruments.",
            "",
        ]
    )
    return "\n".join(lines)


def _verified_record_bytes(record: Mapping[str, Any], *, label: str) -> bytes:
    """Read once, then verify the exact bytes which will enter an archive."""

    path = Path(str(record.get("path", ""))).resolve()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} no longer exists: {path}") from exc
    if len(data) != record.get("bytes") or hashlib.sha256(
        data
    ).hexdigest() != record.get("sha256"):
        raise ValueError(f"{label} changed after it was catalogued")
    return data


def _pack_manifest_item(
    *,
    item_id: str,
    kind: str,
    archive_path: str,
    data: bytes,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "kind": kind,
        "archive_path": archive_path,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _relative_file_record(path: Path, root: Path) -> dict[str, Any]:
    record = _file_record(path)
    record["path"] = str(path.relative_to(root))
    return record


def _without_path(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "path"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    data = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _remove_generated_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _safe_token(value: str) -> str:
    token = "-".join(value.lower().replace("_", " ").split())
    return "".join(char for char in token if char.isalnum() or char == "-") or "part"


def _zip_text(archive: zipfile.ZipFile, name: str, value: str) -> None:
    _zip_bytes(archive, name, value.encode("utf-8"))


def _zip_file(archive: zipfile.ZipFile, name: str, source: Path) -> None:
    _zip_bytes(archive, name, source.read_bytes())


def _zip_bytes(archive: zipfile.ZipFile, name: str, value: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, value)


__all__ = [
    "ARRANGEMENT_SCHEMA",
    "DECODED_STEM_LOOP_SCHEMA",
    "GARAGEBAND_HANDOFF_SCHEMA",
    "GARAGEBAND_PACK_BASKET_SCHEMA",
    "GARAGEBAND_PACK_PLAN_SCHEMA",
    "GARAGEBAND_PACK_SCHEMA",
    "NEUTRAL_PREVIEW_SCHEMA",
    "SELECTED_MIDI_OVERLAP_SCHEMA",
    "WorkbenchArtifacts",
    "WorkbenchPackConflictError",
    "canonical_garageband_pack_basket",
    "selected_candidates",
]
