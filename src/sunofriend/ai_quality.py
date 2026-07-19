"""Model-neutral safety diagnostics for raw AI transcription candidates."""

from __future__ import annotations

import math
from collections import Counter
from statistics import median
from typing import Any, Mapping, Sequence

from .ai_runtime import AITranscriptionCandidate


AI_QUALITY_SCHEMA = "sunofriend.ai-candidate-quality.v1"


def assess_candidate_quality(
    candidate: AITranscriptionCandidate,
    *,
    requested_roles: Sequence[str] = (),
) -> dict[str, Any]:
    """Flag decoder bursts and role leakage without changing raw events."""

    notes = list(candidate.notes)
    if not notes:
        return {
            "schema": AI_QUALITY_SCHEMA,
            "status": "no-evidence",
            "promotion_allowed": False,
            "metrics": _empty_metrics(),
            "instrument_counts": {},
            "requested_roles": list(requested_roles),
            "unexpected_instruments": {},
            "warnings": ["The model emitted no note evidence."],
            "raw_candidate_mutated": False,
        }

    duration = _candidate_duration(candidate)
    durations = [note.end_seconds - note.start_seconds for note in notes]
    instrument_counts = Counter(
        note.instrument or f"{candidate.backend}-unlabelled" for note in notes
    )
    requested = set(requested_roles)
    unexpected = Counter(
        note.instrument or f"{candidate.backend}-unlabelled"
        for note in notes
        if requested and (note.instrument or "") not in requested
    )
    onset_buckets = Counter(
        int(math.floor(note.start_seconds / 0.02 + 1e-9)) for note in notes
    )
    signatures = Counter(
        (
            round(note.start_seconds, 4),
            round(note.end_seconds, 4),
            round(note.pitch, 3),
            note.instrument,
        )
        for note in notes
    )
    duplicate_count = sum(count - 1 for count in signatures.values())
    short_count = sum(value <= 0.020001 for value in durations)
    max_simultaneous = _maximum_simultaneous(notes)
    metrics = {
        "duration_seconds": round(duration, 6),
        "note_count": len(notes),
        "notes_per_second": round(len(notes) / duration, 6),
        "duration_p50_ms": round(float(median(durations)) * 1000.0, 6),
        "short_note_ratio_at_20ms": round(short_count / len(notes), 6),
        "duplicate_signature_ratio": round(duplicate_count / len(notes), 6),
        "max_onsets_in_20ms": max(onset_buckets.values(), default=0),
        "maximum_simultaneous_notes": max_simultaneous,
        "unexpected_instrument_ratio": round(
            sum(unexpected.values()) / len(notes), 6
        ),
    }
    warnings: list[str] = []
    if metrics["notes_per_second"] > 40.0:
        warnings.append(
            "Implausible note density suggests a decoder burst or duplicate events."
        )
    if metrics["max_onsets_in_20ms"] > 64:
        warnings.append(
            "More than 64 notes start within 20ms; do not promote this MIDI without review."
        )
    if (
        metrics["short_note_ratio_at_20ms"] > 0.8
        and metrics["notes_per_second"] > 10.0
    ):
        warnings.append(
            "Most notes are 20ms or shorter at high density; this resembles token noise rather than articulation."
        )
    if metrics["duplicate_signature_ratio"] > 0.2:
        warnings.append("The raw model output contains many duplicate note rectangles.")
    if metrics["maximum_simultaneous_notes"] > 64:
        warnings.append(
            "Extreme simultaneous polyphony may overload a synth and is unlikely to be musical."
        )
    if requested and unexpected:
        warnings.append(
            "The restricted model emitted instrument labels outside the requested roles."
        )
    status = "review-required" if warnings else "pass"
    return {
        "schema": AI_QUALITY_SCHEMA,
        "status": status,
        "promotion_allowed": status == "pass",
        "metrics": metrics,
        "instrument_counts": dict(sorted(instrument_counts.items())),
        "requested_roles": list(requested_roles),
        "unexpected_instruments": dict(sorted(unexpected.items())),
        "warnings": warnings,
        "raw_candidate_mutated": False,
    }


def severe_quality_codes(metrics: Mapping[str, Any]) -> list[str]:
    """Return synth-safety failures, excluding ordinary role-label cautions."""

    codes = []
    if float(metrics.get("notes_per_second") or 0.0) > 40.0:
        codes.append("extreme-note-density")
    if int(metrics.get("max_onsets_in_20ms") or 0) > 64:
        codes.append("extreme-onset-burst")
    if float(metrics.get("duplicate_signature_ratio") or 0.0) > 0.2:
        codes.append("duplicate-note-burst")
    if int(metrics.get("maximum_simultaneous_notes") or 0) > 64:
        codes.append("extreme-polyphony")
    return codes


def _candidate_duration(candidate: AITranscriptionCandidate) -> float:
    excerpt = candidate.metadata.get("excerpt")
    if isinstance(excerpt, dict):
        value = excerpt.get("duration_seconds")
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    notes = candidate.notes
    start = min(note.start_seconds for note in notes)
    end = max(note.end_seconds for note in notes)
    return max(0.001, end - start)


def _maximum_simultaneous(notes) -> int:
    events = []
    for note in notes:
        events.append((float(note.start_seconds), 1))
        events.append((float(note.end_seconds), -1))
    current = 0
    maximum = 0
    for _, change in sorted(events, key=lambda event: (event[0], event[1])):
        current += change
        maximum = max(maximum, current)
    return maximum


def _empty_metrics() -> dict[str, int | float | None]:
    return {
        "duration_seconds": None,
        "note_count": 0,
        "notes_per_second": 0.0,
        "duration_p50_ms": None,
        "short_note_ratio_at_20ms": 0.0,
        "duplicate_signature_ratio": 0.0,
        "max_onsets_in_20ms": 0,
        "maximum_simultaneous_notes": 0,
        "unexpected_instrument_ratio": 0.0,
    }


__all__ = ["AI_QUALITY_SCHEMA", "assess_candidate_quality", "severe_quality_codes"]
