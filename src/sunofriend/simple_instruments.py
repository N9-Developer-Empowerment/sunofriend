"""Sound-aware, automatic instrument handoff for Simple mode.

The exact production-primary MIDI remains untouched in ``MIDI/``.  This
module creates separately labelled starter-sound proxies which use the same
deterministic General MIDI policy as the combined listening interpretation.
It therefore makes the sound decision visible and reproducible without
claiming that a General MIDI program identifies the source instrument or a
private GarageBand factory patch.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import read_midi_clips
from .instrument_catalog import (
    starter_program_document,
    starter_program_for_role,
)
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .role_semantics import is_drum_role


SIMPLE_INSTRUMENT_PLAN_SCHEMA = "sunofriend.simple-instrument-plan.v1"
SIMPLE_INSTRUMENT_POLICY = "deterministic-role-general-midi-starter-v1"
SIMPLE_INSTRUMENT_PREVIEW_SECONDS = 8.0
_PREVIEW_PREROLL_SECONDS = 0.25
_PREVIEW_ACTIVITY_DBFS = -60.0


def build_simple_instrument_handoff(
    selection: Sequence[Mapping[str, Any]],
    lanes: list[dict[str, Any]],
    combined_tracks: Sequence[MidiTrack],
    *,
    root: str | Path,
    bpm: float,
) -> dict[str, Any]:
    """Write starter-sound MIDI, short previews, a JSON plan and a guide."""

    destination = Path(root).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("Simple instrument handoff root must already exist")
    if len(selection) != len(lanes):
        raise ValueError("Simple instrument handoff selection and lanes differ")

    sounds_root = destination / "SOUNDS"
    midi_root = sounds_root / "MIDI"
    preview_root = sounds_root / "PREVIEWS"
    sounds_root.mkdir()
    midi_root.mkdir()
    preview_root.mkdir()

    drum_tracks = [track for track in combined_tracks if track.channel == 9]
    melodic_tracks = [track for track in combined_tracks if track.channel != 9]
    melodic_index = 0
    rows: list[dict[str, Any]] = []

    for item, lane in zip(selection, lanes):
        role = str(item["role"]).strip().lower()
        drum = is_drum_role(role)
        sound = starter_program_document(role, drum=drum)
        if drum:
            if not drum_tracks:
                raise ValueError("Simple drum sound has no combined drum track")
            combined_channel = 9
        else:
            if melodic_index >= len(melodic_tracks):
                raise ValueError("Simple pitched sound has no combined MIDI track")
            combined_track = melodic_tracks[melodic_index]
            melodic_index += 1
            expected_program = starter_program_for_role(role)
            if int(combined_track.program) != expected_program:
                raise ValueError("Simple combined MIDI starter program drifted")
            combined_channel = int(combined_track.channel)

        selection_index = int(item["selection_index"])
        token = _safe_token(role)
        starter_midi = (
            midi_root
            / f"{selection_index:02d}-{token}-automatic-starter-sound.mid"
        )
        notes = _notes_from_midi(Path(str(item["midi_path"])), role=role)
        if not notes:
            raise ValueError("Simple starter-sound MIDI has no playable notes")
        write_midi_file(
            starter_midi,
            [
                MidiTrack(
                    f"{_display_role(role)} - automatic starter - {sound['name']}",
                    combined_channel,
                    0 if drum else int(sound["program_zero_based"]),
                    notes,
                )
            ],
            bpm=bpm,
        )

        preview_path = (
            preview_root
            / f"{selection_index:02d}-{token}-automatic-starter-sound.wav"
        )
        preview_window = _write_preview_excerpt(
            Path(str(lane["preview_path"])),
            preview_path,
        )
        starter_midi_record = _relative_record(starter_midi, destination)
        preview_record = {
            **_relative_record(preview_path, destination),
            **preview_window,
        }
        sound_assignment = {
            **sound,
            "combined_midi_channel_one_based": combined_channel + 1,
            "assignment_status": "automatic_unreviewed_starter",
            "selection_basis": SIMPLE_INSTRUMENT_POLICY,
            "physical_instrument_claim": False,
            "factory_patch_selected": False,
            "native_garageband_patch_embedded": False,
        }
        row = {
            "selection_index": selection_index,
            "role": role,
            "source_midi_sha256": str(item["midi"]["sha256"]),
            "source_midi_bytes": int(item["midi"]["bytes"]),
            "automatic_primary_midi": str(item["garageband_pack_archive_member"]),
            "starter_sound_midi": starter_midi_record,
            "starter_sound_preview": preview_record,
            "starter_sound": sound_assignment,
            "garageband": {
                "preferred_import": starter_midi_record["archive_path"],
                "standard_midi_assignment_embedded": True,
                "native_factory_patch_embedded": False,
                "native_factory_patch_status": "not-selected",
                "instruction": (
                    "Import the starter-sound MIDI. It requests the named General "
                    "MIDI sound; GarageBand may substitute an installed comparable "
                    "patch. Use the preview as the audible reference."
                ),
            },
            "effects": {
                "source_midi_mutated": False,
                "notes_selected": False,
                "notes_ranked": False,
                "human_feedback_recorded": False,
                "factory_patch_promoted": False,
                "starter_proxy_created": True,
            },
        }
        rows.append(row)
        lane["starter_sound"] = sound_assignment
        lane["starter_midi_archive_member"] = starter_midi_record["archive_path"]
        lane["starter_preview_archive_member"] = preview_record["archive_path"]

    if melodic_index != len(melodic_tracks):
        raise ValueError("Simple combined MIDI contains an unexplained pitched track")

    payload = {
        "schema": SIMPLE_INSTRUMENT_PLAN_SCHEMA,
        "policy": SIMPLE_INSTRUMENT_POLICY,
        "label": "Automatic starter instruments",
        "automatic": True,
        "review_status": "not_reviewed",
        "review_recommended": True,
        "path_free_document": True,
        "combined_midi": "MIDI/combined-gm-interpretation.mid",
        "automatic_primary_midi_directory": "MIDI",
        "starter_sound_midi_directory": "SOUNDS/MIDI",
        "starter_sound_preview_directory": "SOUNDS/PREVIEWS",
        "tracks": rows,
        "effects": {
            "source_midi_mutated": False,
            "automatic_sound_assignment": True,
            "automatic_factory_match_selection": False,
            "human_decision_events": 0,
            "feedback_recorded": False,
        },
        "boundary": (
            "General MIDI starter sounds make the handoff immediately audible. "
            "They are editable proxies, not instrument-recognition results, exact "
            "GarageBand factory patches or human-reviewed winners."
        ),
    }
    document = {**payload, "document_sha256": _document_hash(payload)}
    plan_path = sounds_root / "automatic-starter-instruments.json"
    plan_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    guide_path = sounds_root / "INSTRUMENTS-START-HERE.md"
    guide_path.write_text(_instrument_guide(document), encoding="utf-8")
    return {
        "plan": document,
        "plan_record": _relative_record(plan_path, destination),
        "guide_record": _relative_record(guide_path, destination),
    }


def _notes_from_midi(path: Path, *, role: str) -> list[NoteEvent]:
    notes: list[NoteEvent] = []
    for clip in read_midi_clips(path, role=role):
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


def _write_preview_excerpt(source: Path, destination: Path) -> dict[str, Any]:
    try:
        import numpy as np
        import soundfile
    except (ImportError, OSError) as exc:
        raise ValueError("Simple instrument previews require audio dependencies") from exc

    info = soundfile.info(str(source))
    sample_rate = int(info.samplerate)
    total_frames = int(info.frames)
    if sample_rate <= 0 or total_frames <= 0:
        raise ValueError("Simple instrument preview has invalid audio geometry")
    threshold = 10.0 ** (_PREVIEW_ACTIVITY_DBFS / 20.0)
    block_frames = max(1, min(sample_rate // 4, 16_384))
    first_active: int | None = None
    offset = 0
    with soundfile.SoundFile(str(source), mode="r") as handle:
        while offset < total_frames:
            block = handle.read(
                min(block_frames, total_frames - offset),
                dtype="float32",
                always_2d=True,
            )
            if not len(block):
                break
            amplitudes = np.max(np.abs(block), axis=1)
            active = np.flatnonzero(amplitudes > threshold)
            if len(active):
                first_active = offset + int(active[0])
                break
            offset += len(block)
        if first_active is None:
            raise ValueError("Simple instrument starter preview is silent")
        start_frame = max(
            0,
            first_active - round(_PREVIEW_PREROLL_SECONDS * sample_rate),
        )
        maximum_frames = max(1, round(SIMPLE_INSTRUMENT_PREVIEW_SECONDS * sample_rate))
        frame_count = min(maximum_frames, total_frames - start_frame)
        handle.seek(start_frame)
        audio = handle.read(frame_count, dtype="float32", always_2d=True)
    soundfile.write(
        str(destination),
        audio,
        sample_rate,
        subtype="PCM_24",
        format="WAV",
    )
    return {
        "window_policy": "first-audible-minus-0.25s-preroll-max-8s-v1",
        "activity_threshold_dbfs": _PREVIEW_ACTIVITY_DBFS,
        "start_seconds": round(start_frame / sample_rate, 6),
        "duration_seconds": round(len(audio) / sample_rate, 6),
        "sample_rate": sample_rate,
        "channels": int(audio.shape[1]),
    }


def _instrument_guide(document: Mapping[str, Any]) -> str:
    lines = [
        "# Sunofriend automatic starter instruments",
        "",
        "These sounds are already assigned in the files under `SOUNDS/MIDI/` and",
        "in `MIDI/combined-gm-interpretation.mid`. They reproduce the sound family",
        "used by the first listening interpretation; they are editable starting",
        "points, not claims about the original instruments.",
        "",
        "## Fastest GarageBand route",
        "",
        "1. Set the GarageBand project to the BPM in `START-HERE.txt`.",
        "2. Import `MIDI/combined-gm-interpretation.mid` for one multitrack setup,",
        "   or import the separate files under `SOUNDS/MIDI/`.",
        "3. Listen to the matching short files under `SOUNDS/PREVIEWS/`.",
        "4. If GarageBand substitutes a sound, choose a comparable Library patch",
        "   while using the named General MIDI sound and preview as the reference.",
        "5. Keep `MIDI/*automatic-primary.mid` as the unchanged transcription",
        "   evidence; the sound-aware copies are separately labelled proxies.",
        "",
        "## Track plan",
        "",
        "| Track | Part | Automatic starter sound | GarageBand MIDI | Preview |",
        "|---:|---|---|---|---|",
    ]
    for row in document["tracks"]:
        sound = row["starter_sound"]
        if sound["family"] == "general-midi-drum-kit":
            label = "Standard Drum Kit (channel 10)"
        else:
            label = (
                f"GM {int(sound['general_midi_number'])}: {sound['name']}"
            )
        lines.append(
            f"| {int(row['selection_index']):02d} | {_display_role(row['role'])} | "
            f"{label} | `{row['starter_sound_midi']['archive_path']}` | "
            f"`{row['starter_sound_preview']['archive_path']}` |"
        )
    lines.extend(
        [
            "",
            "## Honest boundary",
            "",
            "A `.mid` file can request a standard program or drum channel, but it",
            "cannot embed or redistribute a private GarageBand factory patch. No",
            "factory match has been silently selected. Use Studio when you want to",
            "compare installed patches and record an explicit listening decision.",
            "",
        ]
    )
    return "\n".join(lines)


def _safe_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return token[:48] or "part"


def _display_role(value: str) -> str:
    return str(value).replace("_", " ").strip().title()


def _relative_record(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        archive_path = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Simple instrument artifact escapes its output") from exc
    return {
        "archive_path": archive_path,
        "sha256": _sha256(resolved),
        "bytes": resolved.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "SIMPLE_INSTRUMENT_PLAN_SCHEMA",
    "SIMPLE_INSTRUMENT_POLICY",
    "build_simple_instrument_handoff",
]
