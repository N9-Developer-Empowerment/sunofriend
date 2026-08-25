"""Build an audible, editable identity scaffold from an authorised source song.

This is a pre-generation evidence step.  It combines an already extracted
lead-melody provenance file with beat accents and harmonic regions measured
from the source audio.  Every result remains automatic and unreviewed; no
output is a claim that the intended melody, chords or sections are correct.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

from .chords import generate_pad_notes
from .midi import MidiTrack, write_midi_file
from .models import ChordSegment, NoteEvent


SCHEMA = "sunofriend.source-identity-scaffold.v1"
ANALYSIS_SAMPLE_RATE = 22_050
HOP_LENGTH = 512
_CHORD_CHANGE_PENALTY = 0.24
_MINIMUM_HARMONY_MARGIN = 0.05


def build_source_identity_scaffold(
    source_audio: str | Path,
    melody_provenance: str | Path,
    out_dir: str | Path,
    *,
    bpm: float,
) -> dict[str, Any]:
    """Write a fresh MIDI scaffold and path-free, reviewable evidence."""

    source = _require_file(source_audio, "source audio")
    provenance_path = _require_file(melody_provenance, "melody provenance")
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"Scaffold output must be fresh: {destination}")
    if not math.isfinite(float(bpm)) or not 20.0 <= float(bpm) <= 320.0:
        raise ValueError("bpm must be a finite value from 20 to 320")

    melody_notes, melody_record = _load_melody_provenance(provenance_path)

    import librosa
    import numpy as np

    audio, sample_rate = librosa.load(
        str(source), sr=ANALYSIS_SAMPLE_RATE, mono=True
    )
    if audio.size == 0 or not np.all(np.isfinite(audio)):
        raise ValueError("source audio is empty or non-finite")
    duration = float(len(audio) / sample_rate)
    harmonic, percussive = librosa.effects.hpss(audio)
    onset = librosa.onset.onset_strength(
        y=percussive,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    beat_frames = _source_beat_frames(
        onset,
        duration=duration,
        bpm=float(bpm),
        sample_rate=sample_rate,
        librosa=librosa,
        np=np,
    )
    beat_times = librosa.frames_to_time(
        beat_frames,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    interval_times = _interval_times(beat_times, duration=duration)

    chroma = librosa.feature.chroma_cqt(
        y=harmonic,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]),
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    beat_chroma = _interval_chroma(
        chroma,
        frame_times,
        interval_times,
        np=np,
    )
    chord_names, chord_pitch_classes, chord_scores = _chord_templates(np=np)
    chord_indices = _viterbi_chords(
        chord_scores @ beat_chroma,
        change_penalty=_CHORD_CHANGE_PENALTY,
        np=np,
    )
    chord_segments = _collapse_chords(
        interval_times,
        chord_indices,
        chord_names=chord_names,
        chord_pitch_classes=chord_pitch_classes,
    )
    chord_margin = _median_chord_margin(
        chord_scores @ beat_chroma,
        chord_indices,
        np=np,
    )

    pulse_notes = _pulse_notes(
        beat_frames,
        onset,
        sample_rate=sample_rate,
        duration=duration,
        librosa=librosa,
        np=np,
    )
    bass_notes = _bass_notes(interval_times, chord_indices, chord_pitch_classes)
    pad_notes = generate_pad_notes(chord_segments, velocity=45)
    section_boundaries = _provisional_sections(
        beat_chroma,
        interval_times,
        np=np,
    )

    destination.mkdir(parents=True)
    melody_midi = destination / "source-melody.mid"
    harmony_midi = destination / "source-harmony.mid"
    pulse_midi = destination / "source-pulse.mid"
    scaffold_midi = destination / "source-identity-scaffold.mid"
    scaffold_with_harmony_midi = (
        destination / "source-identity-scaffold-with-harmony.mid"
    )
    chord_csv = destination / "source-chords-automatic.csv"
    section_json = destination / "source-sections-automatic.json"
    report_path = destination / "source-identity-report.json"

    melody_track = MidiTrack(
        "Source lead melody (automatic)",
        channel=0,
        program=73,
        notes=melody_notes,
    )
    pad_track = MidiTrack(
        "Source harmony (automatic)",
        channel=1,
        program=89,
        notes=pad_notes,
    )
    bass_track = MidiTrack(
        "Source bass roots (automatic)",
        channel=2,
        program=38,
        notes=bass_notes,
    )
    pulse_track = MidiTrack(
        "Source beat accents (automatic)",
        channel=9,
        program=0,
        notes=pulse_notes,
    )
    write_midi_file(melody_midi, [melody_track], bpm=float(bpm))
    write_midi_file(harmony_midi, [pad_track, bass_track], bpm=float(bpm))
    write_midi_file(pulse_midi, [pulse_track], bpm=float(bpm))
    write_midi_file(
        scaffold_midi,
        [melody_track, pulse_track],
        bpm=float(bpm),
    )
    write_midi_file(
        scaffold_with_harmony_midi,
        [melody_track, pad_track, bass_track, pulse_track],
        bpm=float(bpm),
    )
    _write_chord_csv(chord_csv, chord_segments)
    sections = [
        {
            "id": f"automatic-segment-{index + 1:02d}",
            "start_seconds": round(start, 6),
            "end_seconds": round(end, 6),
            "label": "unreviewed_source_segment",
        }
        for index, (start, end) in enumerate(
            zip(section_boundaries, section_boundaries[1:])
        )
    ]
    section_json.write_text(
        json.dumps(
            {
                "schema": "sunofriend.source-sections-automatic.v1",
                "status": "complete_unreviewed",
                "segments": sections,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    output_paths = [
        melody_midi,
        harmony_midi,
        pulse_midi,
        scaffold_midi,
        scaffold_with_harmony_midi,
        chord_csv,
        section_json,
    ]
    report = {
        "schema": SCHEMA,
        "status": "complete_unreviewed",
        "purpose": "pre_generation_source_identity_recognition_gate",
        "source": _file_record(source, duration_seconds=duration),
        "melody_provenance": {
            **_file_record(provenance_path),
            "schema_version": melody_record.get("schema_version"),
            "variant": melody_record.get("variant"),
        },
        "settings": {
            "bpm": float(bpm),
            "analysis_sample_rate": sample_rate,
            "hop_length": HOP_LENGTH,
        },
        "evidence": {
            "melody_note_count": len(melody_notes),
            "melody_pitch_low": min(note.pitch for note in melody_notes),
            "melody_pitch_high": max(note.pitch for note in melody_notes),
            "detected_beat_count": len(beat_frames),
            "pulse_note_count": len(pulse_notes),
            "automatic_chord_segment_count": len(chord_segments),
            "automatic_chord_median_margin": round(chord_margin, 6),
            "automatic_harmony_status": (
                "diagnostic_only_low_confidence"
                if chord_margin < _MINIMUM_HARMONY_MARGIN
                else "diagnostic_only_unreviewed"
            ),
            "automatic_harmony_in_primary_scaffold": False,
            "automatic_section_count": len(sections),
        },
        "algorithm": {
            "id": "lead-provenance+hpss-beats+cqt-triad-viterbi-v1",
            "chord_vocabulary": "24 major/minor triads",
            "chord_change_penalty": _CHORD_CHANGE_PENALTY,
            "minimum_harmony_margin": _MINIMUM_HARMONY_MARGIN,
            "section_method": "spaced beat-chroma novelty peaks",
        },
        "outputs": {
            path.name: _file_record(path, relative_name=path.name)
            for path in output_paths
        },
        "review": {
            "status": "required",
            "source_identity_recognised": False,
            "claim": (
                "A musician must confirm that the audible scaffold preserves "
                "the intended source melody, phrasing and useful rhythmic or "
                "harmonic identity before any generative accompaniment test."
            ),
        },
        "limitations": [
            "The supplied melody provenance is automatic and may reflect source singing errors or separation bleed.",
            "Chord names, beat accents and segment boundaries are automatic hypotheses, not transcription truth.",
            "Automatic harmony is kept out of the primary recognition scaffold and must be reviewed separately.",
            "The scaffold is an evidence and editing aid, not an enjoyable finished arrangement.",
            "No generative model was used and no source-identity gate was passed automatically.",
        ],
        "effects": {
            "source_audio_mutated": False,
            "network_used": False,
            "model_generation_used": False,
            "candidate_selected": False,
        },
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        **report,
        "root": str(destination),
        "report": str(report_path),
        "primary_midi": str(scaffold_midi),
    }


def _load_melody_provenance(path: Path) -> tuple[list[NoteEvent], dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("melody provenance must be valid UTF-8 JSON") from exc
    if not isinstance(document, dict) or not isinstance(document.get("notes"), list):
        raise ValueError("melody provenance must contain a notes list")
    notes: list[NoteEvent] = []
    for index, item in enumerate(document["notes"]):
        if not isinstance(item, dict):
            raise ValueError(f"melody provenance note {index} must be an object")
        try:
            note = NoteEvent(
                start=float(item["start"]),
                end=float(item["end"]),
                pitch=int(item["pitch"]),
                velocity=int(item["velocity"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"melody provenance note {index} is invalid") from exc
        if (
            not math.isfinite(note.start)
            or not math.isfinite(note.end)
            or note.start < 0
            or note.end <= note.start
            or not 0 <= note.pitch <= 127
            or not 1 <= note.velocity <= 127
        ):
            raise ValueError(f"melody provenance note {index} is outside MIDI bounds")
        notes.append(note)
    if not notes:
        raise ValueError("melody provenance contains no notes")
    return sorted(notes, key=lambda value: (value.start, value.pitch)), document


def _source_beat_frames(
    onset,
    *,
    duration: float,
    bpm: float,
    sample_rate: int,
    librosa,
    np,
):
    _tempo, frames = librosa.beat.beat_track(
        onset_envelope=onset,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
        bpm=bpm,
        units="frames",
    )
    frames = np.asarray(frames, dtype=int)
    if len(frames) >= 8:
        return frames
    times = np.arange(0.0, duration, 60.0 / bpm)
    return librosa.time_to_frames(
        times,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    ).astype(int)


def _interval_times(beat_times, *, duration: float) -> list[float]:
    values = [0.0]
    values.extend(
        float(value)
        for value in beat_times
        if 0.0 < float(value) < duration
    )
    values.append(duration)
    return sorted(set(round(value, 9) for value in values))


def _interval_chroma(chroma, frame_times, intervals: Sequence[float], *, np):
    values = np.zeros((12, len(intervals) - 1), dtype=float)
    for index, (start, end) in enumerate(zip(intervals, intervals[1:])):
        mask = (frame_times >= start) & (frame_times < end)
        if np.any(mask):
            values[:, index] = np.median(chroma[:, mask], axis=1)
    norms = np.linalg.norm(values, axis=0, keepdims=True)
    return values / (norms + 1e-9)


def _chord_templates(*, np):
    names: list[str] = []
    pitch_classes: list[tuple[int, ...]] = []
    templates = []
    note_names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    for root in range(12):
        for quality, intervals in (("major", (0, 4, 7)), ("minor", (0, 3, 7))):
            pcs = tuple((root + value) % 12 for value in intervals)
            template = np.zeros(12, dtype=float)
            template[list(pcs)] = 1.0
            template[root] = 1.35
            template /= np.linalg.norm(template)
            names.append(f"{note_names[root]} {quality}")
            pitch_classes.append(pcs)
            templates.append(template)
    return names, pitch_classes, np.asarray(templates)


def _viterbi_chords(emissions, *, change_penalty: float, np):
    if emissions.ndim != 2 or emissions.shape[1] == 0:
        raise ValueError("chord emissions must contain at least one interval")
    chord_count, interval_count = emissions.shape
    scores = np.full((interval_count, chord_count), -np.inf)
    back = np.zeros((interval_count, chord_count), dtype=int)
    scores[0] = emissions[:, 0]
    for interval in range(1, interval_count):
        for chord in range(chord_count):
            transitions = scores[interval - 1] - change_penalty
            transitions[chord] = scores[interval - 1, chord]
            previous = int(np.argmax(transitions))
            scores[interval, chord] = transitions[previous] + emissions[chord, interval]
            back[interval, chord] = previous
    result = [int(np.argmax(scores[-1]))]
    for interval in range(interval_count - 1, 0, -1):
        result.append(int(back[interval, result[-1]]))
    return list(reversed(result))


def _collapse_chords(
    intervals: Sequence[float],
    chord_indices: Sequence[int],
    *,
    chord_names: Sequence[str],
    chord_pitch_classes: Sequence[tuple[int, ...]],
) -> list[ChordSegment]:
    if len(intervals) != len(chord_indices) + 1:
        raise ValueError("chord intervals and labels differ")
    segments: list[ChordSegment] = []
    start_index = 0
    for index in range(1, len(chord_indices) + 1):
        if index < len(chord_indices) and chord_indices[index] == chord_indices[start_index]:
            continue
        chord = chord_indices[start_index]
        segments.append(
            ChordSegment(
                start=float(intervals[start_index]),
                end=float(intervals[index]),
                name=chord_names[chord],
                pitch_classes=tuple(chord_pitch_classes[chord]),
            )
        )
        start_index = index
    return segments


def _median_chord_margin(emissions, indices: Sequence[int], *, np) -> float:
    margins = []
    for interval, selected in enumerate(indices):
        column = np.sort(emissions[:, interval])
        if len(column) >= 2:
            margins.append(float(emissions[selected, interval] - column[-2]))
    return float(np.median(margins)) if margins else 0.0


def _pulse_notes(
    beat_frames,
    onset,
    *,
    sample_rate: int,
    duration: float,
    librosa,
    np,
) -> list[NoteEvent]:
    if len(beat_frames) == 0:
        return []
    strengths = np.asarray(
        [onset[min(max(0, int(frame)), len(onset) - 1)] for frame in beat_frames],
        dtype=float,
    )
    low = float(np.percentile(strengths, 10))
    high = float(np.percentile(strengths, 90))
    scale = max(1e-9, high - low)
    times = librosa.frames_to_time(
        beat_frames,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    notes: list[NoteEvent] = []
    median = float(np.median(strengths))
    for time_value, strength in zip(times, strengths):
        start = max(0.0, float(time_value))
        if start >= duration:
            continue
        velocity = int(round(42 + 48 * min(1.0, max(0.0, (strength - low) / scale))))
        notes.append(
            NoteEvent(
                start=start,
                end=min(duration, start + 0.045),
                pitch=42,
                velocity=velocity,
            )
        )
        if strength >= median:
            notes.append(
                NoteEvent(
                    start=start,
                    end=min(duration, start + 0.075),
                    pitch=36,
                    velocity=min(110, velocity + 12),
                )
            )
    return notes


def _bass_notes(
    intervals: Sequence[float],
    chord_indices: Sequence[int],
    chord_pitch_classes: Sequence[tuple[int, ...]],
) -> list[NoteEvent]:
    notes = []
    for index, chord in enumerate(chord_indices):
        start, end = float(intervals[index]), float(intervals[index + 1])
        if end - start < 0.03:
            continue
        root = chord_pitch_classes[chord][0]
        notes.append(
            NoteEvent(
                start=start,
                end=max(start + 0.03, end - 0.02),
                pitch=36 + root,
                velocity=50,
            )
        )
    return notes


def _provisional_sections(beat_chroma, intervals: Sequence[float], *, np) -> list[float]:
    duration = float(intervals[-1])
    if beat_chroma.shape[1] < 16:
        return [0.0, duration]
    novelty = np.linalg.norm(np.diff(beat_chroma, axis=1), axis=0)
    ranked = list(np.argsort(novelty)[::-1])
    selected: list[int] = []
    minimum_gap = 16
    for raw in ranked:
        boundary = int(raw) + 1
        if boundary < 8 or boundary > len(intervals) - 9:
            continue
        if all(abs(boundary - previous) >= minimum_gap for previous in selected):
            selected.append(boundary)
        if len(selected) >= 8:
            break
    return [0.0, *(float(intervals[index]) for index in sorted(selected)), duration]


def _write_chord_csv(path: Path, segments: Sequence[ChordSegment]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["start_seconds", "end_seconds", "automatic_chord"])
        for segment in segments:
            writer.writerow(
                [f"{segment.start:.6f}", f"{segment.end:.6f}", segment.name]
            )


def _require_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def _file_record(
    path: Path,
    *,
    relative_name: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    record: dict[str, Any] = {
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }
    if relative_name is not None:
        record["relative_name"] = relative_name
    if duration_seconds is not None:
        record["duration_seconds"] = round(float(duration_seconds), 6)
    return record


__all__ = ["SCHEMA", "build_source_identity_scaffold"]
