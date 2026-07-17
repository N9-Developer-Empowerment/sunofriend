"""Conservative repeated-unit suggestions for explicit melody review."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Mapping, Sequence

from .models import NoteEvent


REPEAT_SCHEMA = "sunofriend.melody-review-repetition.v1"
REPEAT_POLICY_NAME = "exact-count-source-contour-repeat-v1"
REPEAT_MINIMUM_NOTES = 3
REPEAT_MINIMUM_UNIT_DURATION_RATIO = 0.80
REPEAT_MINIMUM_PITCH_MATCH = 0.80
REPEAT_MINIMUM_INTERVAL_MATCH = 0.75
REPEAT_MAXIMUM_TIMING_P90_BEATS = 0.25
REPEAT_MINIMUM_NOTE_DURATION_SIMILARITY = 0.60
REPEAT_MINIMUM_CONTENT_TIME_SCALE = 0.85
REPEAT_MAXIMUM_CONTENT_TIME_SCALE = 1.15


def detect_repeated_review_units(
    review_units: Sequence[Mapping[str, Any]],
    combined_notes: Sequence[NoteEvent],
    *,
    bpm: float,
) -> dict[str, Any]:
    """Suggest only strong pairwise repeats; never select a review choice."""

    tempo = float(bpm)
    if not math.isfinite(tempo) or tempo <= 0:
        raise ValueError("repeat detection BPM must be finite and positive")
    units = [_normalise_unit(value) for value in review_units]
    indices = [unit["phrase_index"] for unit in units]
    if len(indices) != len(set(indices)):
        raise ValueError("repeat detection review-unit indices must be unique")
    notes = sorted(combined_notes, key=lambda note: (note.start, note.pitch, note.end))
    notes_by_unit = {
        unit["phrase_index"]: _notes_in_unit(
            notes,
            start=unit["start_seconds"],
            end=unit["end_seconds"],
        )
        for unit in units
    }
    beat_seconds = 60.0 / tempo
    evaluated: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for pair_index, (left, right) in enumerate(combinations(units, 2)):
        record = _compare_units(
            left,
            notes_by_unit[left["phrase_index"]],
            right,
            notes_by_unit[right["phrase_index"]],
            beat_seconds=beat_seconds,
        )
        record["pair_index"] = pair_index
        evaluated.append(record)
        if record["status"] == "accepted":
            accepted.append(record)
    groups = _repeat_groups(accepted)
    return {
        "schema": REPEAT_SCHEMA,
        "policy": {
            "name": REPEAT_POLICY_NAME,
            "minimum_notes": REPEAT_MINIMUM_NOTES,
            "note_count": "exact",
            "minimum_unit_duration_ratio": REPEAT_MINIMUM_UNIT_DURATION_RATIO,
            "minimum_pitch_match_ratio": REPEAT_MINIMUM_PITCH_MATCH,
            "minimum_interval_match_ratio": REPEAT_MINIMUM_INTERVAL_MATCH,
            "maximum_timing_p90_beats": REPEAT_MAXIMUM_TIMING_P90_BEATS,
            "minimum_note_duration_similarity": (
                REPEAT_MINIMUM_NOTE_DURATION_SIMILARITY
            ),
            "content_time_scale_range": [
                REPEAT_MINIMUM_CONTENT_TIME_SCALE,
                REPEAT_MAXIMUM_CONTENT_TIME_SCALE,
            ],
            "absolute_pitch_required": True,
            "automatic_selection": False,
            "human_confirmation_required": True,
        },
        "review_unit_count": len(units),
        "evaluated_pair_count": len(evaluated),
        "accepted_pair_count": len(accepted),
        "evaluated_pairs": evaluated,
        "accepted_pairs": accepted,
        "groups": groups,
        "raw_candidates_mutated": False,
    }


def repeat_matches_for_unit(
    repetition: Mapping[str, Any],
    phrase_index: int,
) -> list[dict[str, Any]]:
    """Return symmetric, stable UI suggestions for one review unit."""

    matches: list[dict[str, Any]] = []
    for pair in repetition.get("accepted_pairs", []):
        if not isinstance(pair, Mapping):
            continue
        left = int(pair["left_phrase_index"])
        right = int(pair["right_phrase_index"])
        if phrase_index == left:
            matches.append(
                {
                    "target_phrase_index": right,
                    "lag_seconds": pair["lag_seconds"],
                    "pair": dict(pair),
                }
            )
        elif phrase_index == right:
            matches.append(
                {
                    "target_phrase_index": left,
                    "lag_seconds": round(-float(pair["lag_seconds"]), 6),
                    "pair": dict(pair),
                }
            )
    return sorted(matches, key=lambda value: value["target_phrase_index"])


def _normalise_unit(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("repeat detection review unit must be an object")
    try:
        phrase_index = int(value["phrase_index"])
        start = float(value["start_seconds"])
        end = float(value["end_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("repeat detection review unit has invalid values") from exc
    if phrase_index < 0 or not all(math.isfinite(item) for item in (start, end)):
        raise ValueError("repeat detection review unit has invalid values")
    if start < 0 or end <= start:
        raise ValueError("repeat detection review unit has invalid bounds")
    return {
        "phrase_index": phrase_index,
        "start_seconds": start,
        "end_seconds": end,
    }


def _notes_in_unit(
    notes: Sequence[NoteEvent],
    *,
    start: float,
    end: float,
) -> list[NoteEvent]:
    selected: list[NoteEvent] = []
    for note in notes:
        if note.end <= start or note.start >= end:
            continue
        clipped_start = max(start, note.start)
        clipped_end = min(end, note.end)
        if clipped_end - clipped_start >= 0.03:
            selected.append(
                NoteEvent(clipped_start, clipped_end, note.pitch, note.velocity)
            )
    return selected


def _compare_units(
    left: Mapping[str, Any],
    left_notes: Sequence[NoteEvent],
    right: Mapping[str, Any],
    right_notes: Sequence[NoteEvent],
    *,
    beat_seconds: float,
) -> dict[str, Any]:
    left_index = int(left["phrase_index"])
    right_index = int(right["phrase_index"])
    left_duration = float(left["end_seconds"]) - float(left["start_seconds"])
    right_duration = float(right["end_seconds"]) - float(right["start_seconds"])
    duration_ratio = min(left_duration, right_duration) / max(
        left_duration, right_duration
    )
    reasons: list[str] = []
    if min(len(left_notes), len(right_notes)) < REPEAT_MINIMUM_NOTES:
        reasons.append("insufficient-notes")
    if len(left_notes) != len(right_notes):
        reasons.append("note-count-mismatch")
    if duration_ratio < REPEAT_MINIMUM_UNIT_DURATION_RATIO:
        reasons.append("unit-duration-mismatch")

    pitch_match = 0.0
    interval_match = 0.0
    timing_p90 = None
    note_duration_similarity = 0.0
    content_time_scale = None
    if left_notes and len(left_notes) == len(right_notes):
        count = len(left_notes)
        pitch_match = sum(
            left_note.pitch == right_note.pitch
            for left_note, right_note in zip(left_notes, right_notes)
        ) / count
        if count == 1:
            interval_match = 1.0
        else:
            left_intervals = [
                current.pitch - previous.pitch
                for previous, current in zip(left_notes, left_notes[1:])
            ]
            right_intervals = [
                current.pitch - previous.pitch
                for previous, current in zip(right_notes, right_notes[1:])
            ]
            interval_match = sum(
                left_value == right_value
                for left_value, right_value in zip(left_intervals, right_intervals)
            ) / len(left_intervals)

        left_span = left_notes[-1].end - left_notes[0].start
        right_span = right_notes[-1].end - right_notes[0].start
        if left_span > 0 and right_span > 0:
            content_time_scale = left_span / right_span
            onset_errors = [
                abs(
                    (left_note.start - left_notes[0].start)
                    - (right_note.start - right_notes[0].start)
                    * content_time_scale
                )
                / beat_seconds
                for left_note, right_note in zip(left_notes, right_notes)
            ]
            timing_p90 = _percentile(onset_errors, 90.0)
            duration_similarities = [
                min(
                    left_note.end - left_note.start,
                    (right_note.end - right_note.start) * content_time_scale,
                )
                / max(
                    left_note.end - left_note.start,
                    (right_note.end - right_note.start) * content_time_scale,
                )
                for left_note, right_note in zip(left_notes, right_notes)
            ]
            note_duration_similarity = sum(duration_similarities) / len(
                duration_similarities
            )

    if pitch_match < REPEAT_MINIMUM_PITCH_MATCH:
        reasons.append("absolute-pitch-mismatch")
    if interval_match < REPEAT_MINIMUM_INTERVAL_MATCH:
        reasons.append("contour-interval-mismatch")
    if timing_p90 is None or timing_p90 > REPEAT_MAXIMUM_TIMING_P90_BEATS:
        reasons.append("onset-timing-mismatch")
    if note_duration_similarity < REPEAT_MINIMUM_NOTE_DURATION_SIMILARITY:
        reasons.append("note-duration-mismatch")
    if content_time_scale is None or not (
        REPEAT_MINIMUM_CONTENT_TIME_SCALE
        <= content_time_scale
        <= REPEAT_MAXIMUM_CONTENT_TIME_SCALE
    ):
        reasons.append("content-time-scale-mismatch")

    timing_similarity = (
        0.0
        if timing_p90 is None
        else max(0.0, 1.0 - timing_p90 / max(0.5, 1e-9))
    )
    score = (
        0.35 * pitch_match
        + 0.25 * interval_match
        + 0.20 * timing_similarity
        + 0.10 * note_duration_similarity
        + 0.10 * duration_ratio
    )
    return {
        "status": "accepted" if not reasons else "rejected",
        "left_phrase_index": left_index,
        "right_phrase_index": right_index,
        "lag_seconds": round(
            float(right["start_seconds"]) - float(left["start_seconds"]),
            6,
        ),
        "left_note_count": len(left_notes),
        "right_note_count": len(right_notes),
        "unit_duration_ratio": round(duration_ratio, 6),
        "pitch_match_ratio": round(pitch_match, 6),
        "interval_match_ratio": round(interval_match, 6),
        "timing_p90_beats": None if timing_p90 is None else round(timing_p90, 6),
        "note_duration_similarity": round(note_duration_similarity, 6),
        "content_time_scale": (
            None if content_time_scale is None else round(content_time_scale, 6)
        ),
        "similarity_score": round(score, 6),
        "rejection_reasons": reasons,
        "absolute_pitch_required": True,
        "automatic_selection": False,
    }


def _repeat_groups(pairs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    adjacency: dict[int, set[int]] = {}
    for pair in pairs:
        left = int(pair["left_phrase_index"])
        right = int(pair["right_phrase_index"])
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    groups: list[dict[str, Any]] = []
    remaining = set(adjacency)
    while remaining:
        root = min(remaining)
        pending = [root]
        members: set[int] = set()
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(sorted(adjacency.get(current, set()) - members))
        remaining -= members
        member_list = sorted(members)
        pair_indices = sorted(
            int(pair["pair_index"])
            for pair in pairs
            if int(pair["left_phrase_index"]) in members
            and int(pair["right_phrase_index"]) in members
        )
        groups.append(
            {
                "group_index": len(groups),
                "phrase_indices": member_list,
                "pair_indices": pair_indices,
            }
        )
    return groups


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


__all__ = [
    "REPEAT_POLICY_NAME",
    "REPEAT_SCHEMA",
    "detect_repeated_review_units",
    "repeat_matches_for_unit",
]
