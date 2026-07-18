"""Arrangement-aware playability checks for source-derived sample instruments.

Building a valid SF2 file is not the same as building a useful instrument.
This module checks the generated zones against the *actual* MIDI performance
before an instrument bundle recommends the bank for musical use.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Sequence


USABILITY_SCHEMA = "sunofriend.instrument-usability.v1"
DRUM_KINDS = frozenset(
    {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums"}
)
ATTACK_FLOOR_SECONDS = 0.12
MUSICAL_FLOOR_SECONDS = 0.35
REQUIRED_NOTE_COVERAGE_RATIO = 1.0
REQUIRED_ATTACK_SUPPORT_RATIO = 0.99
REQUIRED_MUSICAL_SUPPORT_RATIO = 0.90
STABLE_TUNING_STATUSES = frozenset({"applied"})


def analyze_sample_instrument_usability(
    clip: Any,
    rows: Sequence[dict[str, Any]],
    *,
    kind: str,
    cluster_summary: dict[str, Any] | None = None,
    looped_zone_count: int = 0,
) -> dict[str, Any]:
    """Classify whether generated zones can carry the supplied performance.

    The hard gate deliberately uses observable sampler behaviour only: mapped
    pitch/velocity zones and enough one-shot audio to make each performance
    note audible. Pitch and timbre analyses remain review evidence because a
    failed pitch estimate does not prove that a noisy or percussive sound is
    musically invalid.
    """

    normalized_kind = str(kind).strip().lower()
    drums = normalized_kind in DRUM_KINDS
    notes = list(clip.notes)
    if not notes:
        raise ValueError("Instrument usability requires a note-bearing performance")
    if not rows:
        raise ValueError("Instrument usability requires at least one sample zone")

    zone_ranges = [
        {
            "root_key": int(row["pitch"]),
            "low_key": int(row["low_key"]),
            "high_key": int(row["high_key"]),
            "low_velocity": int(row.get("low_velocity", 0)),
            "high_velocity": int(row.get("high_velocity", 127)),
            "sample_duration_seconds": _sample_duration(row),
            "looped": bool(row.get("loop_start") is not None),
        }
        for row in rows
    ]
    note_durations = [_note_duration_seconds(clip, note) for note in notes]
    mapped: list[tuple[Any, dict[str, Any], float, float]] = []
    unmapped = []
    for note, note_duration in zip(notes, note_durations):
        zone = _zone_for(note, rows)
        if zone is None:
            unmapped.append(note)
            continue
        playback_duration = _effective_sample_duration(zone, int(note.pitch))
        mapped.append((note, zone, note_duration, playback_duration))

    attack_supported = sum(
        _supports_duration(playback, duration, ATTACK_FLOOR_SECONDS)
        for _, _, duration, playback in mapped
    )
    if drums:
        musical_supported = len(mapped)
    else:
        musical_supported = sum(
            _supports_duration(playback, duration, MUSICAL_FLOOR_SECONDS)
            for _, _, duration, playback in mapped
        )
    note_count = len(notes)
    mapped_count = len(mapped)
    coverage_ratio = mapped_count / note_count
    attack_ratio = attack_supported / note_count
    musical_ratio = musical_supported / note_count
    notes_ending_early = sum(
        playback + 1e-9 < duration for _, _, duration, playback in mapped
    )
    effective_durations = [playback for _, _, _, playback in mapped]
    sample_durations = [item["sample_duration_seconds"] for item in zone_ranges]

    tuning_statuses = Counter(
        str(row.get("tuning", {}).get("status", "unknown")) for row in rows
    )
    stable_tuning_count = sum(
        count
        for status, count in tuning_statuses.items()
        if status in STABLE_TUNING_STATUSES
    )
    cluster_summary = dict(cluster_summary or {})
    family_count = int(cluster_summary.get("identity_candidate_cluster_count", 0))
    outlier_count = int(cluster_summary.get("identity_outlier_count", 0))

    failures: list[dict[str, Any]] = []
    if coverage_ratio + 1e-12 < REQUIRED_NOTE_COVERAGE_RATIO:
        failures.append(
            {
                "code": "unmapped-performance-notes",
                "detail": (
                    f"{len(unmapped)} of {note_count} performance notes have no "
                    "matching key/velocity zone"
                ),
            }
        )
    if attack_ratio + 1e-12 < REQUIRED_ATTACK_SUPPORT_RATIO:
        failures.append(
            {
                "code": "insufficient-audible-attack-duration",
                "detail": (
                    f"Only {attack_supported} of {note_count} notes have at least "
                    f"min(note duration, {ATTACK_FLOOR_SECONDS:.2f}s) of sample audio"
                ),
            }
        )
    if not drums and musical_ratio + 1e-12 < REQUIRED_MUSICAL_SUPPORT_RATIO:
        failures.append(
            {
                "code": "insufficient-musical-duration",
                "detail": (
                    f"Only {musical_supported} of {note_count} notes have at least "
                    f"min(note duration, {MUSICAL_FLOOR_SECONDS:.2f}s) of sample audio"
                ),
            }
        )

    functional_status = "fail" if failures else "pass"
    status = "texture-only" if failures else "review-required"
    recommended_use = (
        "optional-texture-layer-under-a-complete-instrument"
        if failures
        else "primary-candidate-after-full-range-listening-review"
    )
    warnings: list[str] = []
    inconclusive_tuning = len(rows) - stable_tuning_count
    if not drums and inconclusive_tuning:
        warnings.append(
            f"Stable tuning was confirmed for {stable_tuning_count} of {len(rows)} "
            "zones. Other tuning results are inconclusive review evidence, not "
            "automatic sample failures."
        )
    if not drums and looped_zone_count == 0:
        warnings.append(
            "All pitched zones are unlooped one-shots; long MIDI notes end when the "
            "sample audio ends."
        )
    if family_count > 1:
        warnings.append(
            f"Source analysis found {family_count} candidate timbre families. "
            "Listen for inconsistent tone; clustering does not identify physical "
            "instruments or remove samples automatically."
        )
    if outlier_count:
        warnings.append(
            f"{outlier_count} source events were retained as review outliers."
        )

    pitches = [int(note.pitch) for note in notes]
    velocities = [int(note.velocity) for note in notes]
    unmapped_pitches = Counter(int(note.pitch) for note in unmapped)
    unique_pitches = sorted(set(pitches))
    # Derive unique-pitch coverage from the exact note/velocity mapping above.
    # This keeps the summary and the hard note-coverage gate on one source of
    # truth when velocity-layer ranges are introduced.
    mapped_unique_pitches = sorted({int(note.pitch) for note, _, _, _ in mapped})
    return {
        "schema": USABILITY_SCHEMA,
        "status": status,
        "functional_status": functional_status,
        "recommended_use": recommended_use,
        "automatic_primary_recommendation": False,
        "requires_listening": True,
        "kind": normalized_kind,
        "one_shot_role": drums,
        "policy": {
            "required_note_coverage_ratio": REQUIRED_NOTE_COVERAGE_RATIO,
            "attack_floor_seconds": ATTACK_FLOOR_SECONDS,
            "required_attack_support_ratio": REQUIRED_ATTACK_SUPPORT_RATIO,
            "musical_floor_seconds": None if drums else MUSICAL_FLOOR_SECONDS,
            "required_musical_support_ratio": (
                None if drums else REQUIRED_MUSICAL_SUPPORT_RATIO
            ),
            "tuning_and_timbre_are_review_evidence": True,
        },
        "performance": {
            "track_title": str(clip.title),
            "note_count": note_count,
            "unique_pitch_count": len(unique_pitches),
            "pitch_range": [min(pitches), max(pitches)],
            "velocity_range": [min(velocities), max(velocities)],
            "duration_seconds": _summary(note_durations),
            "instrument_suggestions": list(clip.instrument.suggestions),
        },
        "zones": {
            "zone_count": len(zone_ranges),
            "key_range": [
                min(item["low_key"] for item in zone_ranges),
                max(item["high_key"] for item in zone_ranges),
            ],
            "velocity_range": [
                min(item["low_velocity"] for item in zone_ranges),
                max(item["high_velocity"] for item in zone_ranges),
            ],
            "sample_duration_seconds": _summary(sample_durations),
            "looped_zone_count": int(looped_zone_count),
            "ranges": zone_ranges,
        },
        "coverage": {
            "mapped_note_count": mapped_count,
            "unmapped_note_count": len(unmapped),
            "note_coverage_ratio": _round(coverage_ratio),
            "mapped_unique_pitch_count": len(mapped_unique_pitches),
            "unique_pitch_coverage_ratio": _round(
                len(mapped_unique_pitches) / len(unique_pitches)
            ),
            "unmapped_pitch_counts": {
                str(pitch): count for pitch, count in sorted(unmapped_pitches.items())
            },
        },
        "duration_support": {
            "attack_supported_note_count": attack_supported,
            "attack_support_ratio": _round(attack_ratio),
            "musical_supported_note_count": musical_supported,
            "musical_support_ratio": _round(musical_ratio),
            "notes_ending_before_midi_note_off": notes_ending_early,
            "effective_sample_duration_seconds": _summary(effective_durations),
        },
        "pitch_evidence": {
            "stable_zone_count": stable_tuning_count,
            "inconclusive_or_rejected_zone_count": inconclusive_tuning,
            "statuses": dict(sorted(tuning_statuses.items())),
            "interpretation": (
                "Inconclusive or rejected tuning estimates require listening and "
                "do not independently fail a zone."
            ),
        },
        "timbre_evidence": {
            "candidate_family_count": family_count,
            "retained_outlier_count": outlier_count,
            "interpretation": (
                "Multiple candidate families require consistency review; they are "
                "not confirmed physical instruments."
            ),
        },
        "failures": failures,
        "warnings": warnings,
        "effects": {
            "source_midi_changed": False,
            "sample_audio_changed": False,
            "soundfont_mapping_changed": False,
            "automatic_sample_removals": 0,
        },
    }


def write_instrument_usability_audition(
    path: str | Path,
    clip: Any,
    *,
    bpm: float = 120.0,
) -> dict[str, Any]:
    """Write a compact MIDI that exposes missing pitches and velocity response."""

    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent

    performance_notes = list(clip.notes)
    if not performance_notes:
        raise ValueError("Usability audition requires a note-bearing performance")
    by_pitch: dict[int, list[int]] = {}
    for note in performance_notes:
        by_pitch.setdefault(int(note.pitch), []).append(int(note.velocity))
    notes: list[NoteEvent] = []
    cursor = 0.0
    for pitch in sorted(by_pitch):
        velocity = int(round(median(by_pitch[pitch])))
        notes.append(NoteEvent(cursor, cursor + 0.35, pitch, velocity))
        cursor += 0.5
    probe_pitch = sorted(by_pitch)[len(by_pitch) // 2]
    probe_velocities = (32, 64, 96, 127)
    cursor += 0.5
    for velocity in probe_velocities:
        notes.append(NoteEvent(cursor, cursor + 0.35, probe_pitch, velocity))
        cursor += 0.5
    write_midi_file(
        path,
        [MidiTrack("Instrument Usability Gate v1", 0, 0, notes)],
        bpm=float(bpm),
    )
    return {
        "midi": Path(path).name,
        "note_count": len(notes),
        "performance_pitch_count": len(by_pitch),
        "performance_pitch_range": [min(by_pitch), max(by_pitch)],
        "pitch_order": sorted(by_pitch),
        "velocity_probe_pitch": probe_pitch,
        "velocity_probe_values": list(probe_velocities),
        "note_seconds": 0.35,
        "step_seconds": 0.5,
        "interpretation": (
            "Every distinct performance pitch is played once, followed by four "
            "velocity probes. Silence exposes an unmapped or inaudible zone."
        ),
    }


def _zone_for(note: Any, rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if (
            int(row["low_key"]) <= int(note.pitch) <= int(row["high_key"])
            and int(row.get("low_velocity", 0))
            <= int(note.velocity)
            <= int(row.get("high_velocity", 127))
        ):
            return row
    return None


def _sample_duration(row: dict[str, Any]) -> float:
    duration = float(row.get("sample_duration_seconds", 0.0))
    if duration <= 0.0:
        duration = float(row["end_seconds"]) - float(row["start_seconds"])
    return max(0.0, duration)


def _effective_sample_duration(row: dict[str, Any], played_pitch: int) -> float:
    if row.get("loop_start") is not None:
        return math.inf
    root = int(row["pitch"])
    return _sample_duration(row) * 2.0 ** ((root - played_pitch) / 12.0)


def _note_duration_seconds(clip: Any, note: Any) -> float:
    source_duration = float(note.source_end_seconds) - float(note.source_start_seconds)
    if source_duration > 0.0 and math.isfinite(source_duration):
        return source_duration
    start = clip.tempo_map.musical_seconds_at(float(note.start_beat))
    end = clip.tempo_map.musical_seconds_at(
        float(note.start_beat) + float(note.duration_beats)
    )
    return max(0.0, end - start)


def _supports_duration(playback: float, note_duration: float, floor: float) -> bool:
    return playback + 1e-9 >= min(note_duration, floor)


def _summary(values: Sequence[float]) -> dict[str, float | None]:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return {"minimum": None, "median": None, "maximum": None}
    return {
        "minimum": _round(finite[0]),
        "median": _round(float(median(finite))),
        "maximum": _round(finite[-1]),
    }


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "USABILITY_SCHEMA",
    "analyze_sample_instrument_usability",
    "write_instrument_usability_audition",
]
