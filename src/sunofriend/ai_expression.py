"""Source-evidence expression for otherwise velocity-free AI note events.

The model candidate remains untouched.  This module measures the source audio
under each predicted note and creates a separate, auditable velocity layer for
MIDI audition and DAW use.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import soundfile as sf

from .ai_runtime import AITranscriptionCandidate


AI_EXPRESSION_SCHEMA = "sunofriend.ai-source-expression.v1"
_DEFAULT_VELOCITY = 88
_MIN_VELOCITY = 42
_MAX_VELOCITY = 116


def recover_source_expression(
    audio_path: str | Path,
    candidate: AITranscriptionCandidate,
) -> dict[str, Any]:
    """Measure note-local attack/body energy and derive relative velocities."""

    audio = Path(audio_path).expanduser().absolute()
    if not audio.is_file():
        raise ValueError(f"source audio does not exist: {audio}")
    if not candidate.notes:
        return {
            "schema": AI_EXPRESSION_SCHEMA,
            "status": "no-evidence",
            "source_audio": str(audio),
            "policy": _policy_document(),
            "excerpt": None,
            "normalization_groups": {},
            "notes": [],
            "velocity_summary": None,
            "warnings": [],
        }

    info = sf.info(str(audio))
    sample_rate = int(info.samplerate)
    if sample_rate <= 0 or info.frames <= 0:
        raise ValueError("source audio has no readable samples")
    audio_duration = info.frames / sample_rate
    start_seconds = max(0.0, min(note.start_seconds for note in candidate.notes) - 0.05)
    end_seconds = min(
        audio_duration,
        max(note.end_seconds for note in candidate.notes) + 0.05,
    )
    if end_seconds <= start_seconds:
        raise ValueError("candidate notes do not overlap the source audio")
    start_frame = int(math.floor(start_seconds * sample_rate))
    end_frame = int(math.ceil(end_seconds * sample_rate))
    with sf.SoundFile(str(audio)) as handle:
        handle.seek(start_frame)
        values = handle.read(
            frames=max(0, end_frame - start_frame),
            dtype="float32",
            always_2d=True,
        )
    if not len(values):
        raise ValueError("candidate excerpt contains no readable source samples")
    mono = np.mean(values, axis=1, dtype=np.float64)
    floor_rms = _percentile_window_rms(mono, sample_rate, percentile=15.0)
    floor_dbfs = _dbfs(floor_rms)

    measurements: list[dict[str, Any]] = []
    for index, note in enumerate(candidate.notes):
        note_start = _local_frame(
            note.start_seconds, start_seconds, sample_rate, len(mono)
        )
        note_end = _local_frame(
            note.end_seconds, start_seconds, sample_rate, len(mono)
        )
        note_end = max(note_start + 1, note_end)
        note_end = min(note_end, len(mono))
        body = mono[note_start:note_end]
        attack_end = min(
            note_end,
            note_start + max(1, int(round(0.12 * sample_rate))),
        )
        attack = mono[note_start:attack_end]
        body_rms = _rms(body)
        attack_peak_rms = _peak_window_rms(attack, sample_rate)
        combined_rms = math.sqrt(
            0.65 * attack_peak_rms * attack_peak_rms
            + 0.35 * body_rms * body_rms
        )
        measurements.append(
            {
                "candidate_index": index,
                "source_event_id": note.source_event_id,
                "instrument": note.instrument,
                "start_seconds": round(float(note.start_seconds), 6),
                "end_seconds": round(float(note.end_seconds), 6),
                "pitch": float(note.pitch),
                "model_velocity": note.velocity,
                "attack_peak_dbfs": _round_db(_dbfs(attack_peak_rms)),
                "body_rms_dbfs": _round_db(_dbfs(body_rms)),
                "combined_dbfs": _round_db(_dbfs(combined_rms)),
            }
        )

    groups: dict[str, list[int]] = defaultdict(list)
    missing_indices: list[int] = []
    for index, (note, measurement) in enumerate(zip(candidate.notes, measurements)):
        if note.velocity is not None:
            measurement["velocity"] = int(note.velocity)
            measurement["velocity_source"] = "model"
            continue
        group = note.instrument or f"{candidate.backend}-unlabelled"
        groups[group].append(index)
        missing_indices.append(index)

    global_values = [measurements[index]["combined_dbfs"] for index in missing_indices]
    normalization: dict[str, dict[str, Any]] = {}
    for group, indices in sorted(groups.items()):
        group_values = [measurements[index]["combined_dbfs"] for index in indices]
        selected = group_values if len(group_values) >= 3 else global_values
        low, high = _normalization_bounds(selected)
        normalization[group] = {
            "note_count": len(indices),
            "basis": "instrument" if len(group_values) >= 3 else "global",
            "low_dbfs": low,
            "high_dbfs": high,
        }
        for index in indices:
            measurement = measurements[index]
            measurement["velocity"] = _velocity_from_db(
                measurement["combined_dbfs"],
                low,
                high,
                floor_dbfs,
            )
            measurement["velocity_source"] = "source-relative-energy"

    velocities = [int(measurement["velocity"]) for measurement in measurements]
    return {
        "schema": AI_EXPRESSION_SCHEMA,
        "status": "complete",
        "source_audio": str(audio),
        "policy": _policy_document(),
        "excerpt": {
            "start_seconds": round(start_seconds, 6),
            "end_seconds": round(end_seconds, 6),
            "sample_rate": sample_rate,
            "channels": int(info.channels),
            "analysis_floor_dbfs": _round_db(floor_dbfs),
        },
        "normalization_groups": normalization,
        "notes": measurements,
        "velocity_summary": {
            "count": len(velocities),
            "minimum": min(velocities),
            "maximum": max(velocities),
            "median": round(float(median(velocities)), 3),
            "distinct": len(set(velocities)),
        },
        "warnings": [
            "Velocity represents relative source energy, not a recovered performance control signal."
        ],
    }


def expression_velocities(
    document: dict[str, Any],
    *,
    expected_notes: int,
) -> list[int]:
    """Validate and return velocities in candidate-note order."""

    if document.get("schema") != AI_EXPRESSION_SCHEMA:
        raise ValueError(f"expression schema must be {AI_EXPRESSION_SCHEMA}")
    notes = document.get("notes")
    if not isinstance(notes, list) or len(notes) != expected_notes:
        raise ValueError("expression note count does not match the AI candidate")
    ordered = sorted(notes, key=lambda note: int(note["candidate_index"]))
    if [int(note["candidate_index"]) for note in ordered] != list(
        range(expected_notes)
    ):
        raise ValueError("expression candidate indices are incomplete")
    velocities = [int(note["velocity"]) for note in ordered]
    if any(not 1 <= velocity <= 127 for velocity in velocities):
        raise ValueError("expression velocities must be in the MIDI range 1..127")
    return velocities


def _policy_document() -> dict[str, Any]:
    return {
        "name": "note-local-source-energy-v1",
        "attack_weight": 0.65,
        "body_weight": 0.35,
        "attack_window_ms": 120.0,
        "normalization_percentiles": [10.0, 90.0],
        "normalization_scope": "per instrument when at least three notes, otherwise global",
        "velocity_range": [_MIN_VELOCITY, _MAX_VELOCITY],
        "flat_dynamic_default": _DEFAULT_VELOCITY,
        "raw_candidate_mutated": False,
    }


def _local_frame(
    seconds: float,
    excerpt_start: float,
    sample_rate: int,
    length: int,
) -> int:
    return max(
        0,
        min(length, int(round((float(seconds) - excerpt_start) * sample_rate))),
    )


def _rms(values: np.ndarray) -> float:
    if not len(values):
        return 0.0
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))


def _peak_window_rms(values: np.ndarray, sample_rate: int) -> float:
    if not len(values):
        return 0.0
    window = max(1, int(round(0.02 * sample_rate)))
    if len(values) <= window:
        return _rms(values)
    hop = max(1, window // 4)
    return max(
        _rms(values[start : start + window])
        for start in range(0, len(values) - window + 1, hop)
    )


def _percentile_window_rms(
    values: np.ndarray,
    sample_rate: int,
    *,
    percentile: float,
) -> float:
    window = max(1, int(round(0.02 * sample_rate)))
    hop = max(1, window // 2)
    readings = [
        _rms(values[start : start + window])
        for start in range(0, max(1, len(values) - window + 1), hop)
    ]
    return float(np.percentile(readings or [0.0], percentile))


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-7))


def _round_db(value: float) -> float:
    return round(float(value), 6)


def _normalization_bounds(values: list[float]) -> tuple[float, float]:
    if not values:
        return -60.0, -60.0
    low = float(np.percentile(values, 10.0))
    high = float(np.percentile(values, 90.0))
    return _round_db(low), _round_db(high)


def _velocity_from_db(value: float, low: float, high: float, floor: float) -> int:
    if high - low < 1.5:
        return _DEFAULT_VELOCITY
    if value <= floor + 1.0:
        return _MIN_VELOCITY
    position = max(0.0, min(1.0, (value - low) / (high - low)))
    return int(round(_MIN_VELOCITY + position * (_MAX_VELOCITY - _MIN_VELOCITY)))


__all__ = [
    "AI_EXPRESSION_SCHEMA",
    "expression_velocities",
    "recover_source_expression",
]
