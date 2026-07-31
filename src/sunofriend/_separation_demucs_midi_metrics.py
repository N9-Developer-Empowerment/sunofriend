"""Pure MIDI observations for the private Demucs separation bake-off.

The reference is always the MIDI transcribed from an exact synthetic role and
the estimate is MIDI transcribed from the matching separated role.  Every
alignment is deterministic, one-to-one and inclusive at the configured onset
tolerance.  These observations do not select or promote either transcription.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from numbers import Integral, Real
from typing import Any, Sequence

from .models import NoteEvent
from .note_alignment import AlignmentEvent, AlignmentResult, align_events
from .transcribe_drums import DrumHit


_DEFAULT_TOLERANCE_SECONDS = 0.04
_MATCHING_POLICY = "earliest_compatible"


def _compare_note_events(
    reference: Sequence[NoteEvent],
    estimate: Sequence[NoteEvent],
    *,
    tolerance_seconds: float = _DEFAULT_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Compare note events without reading, writing or changing either input.

    Onset timing uses pitch-agnostic matches. Duration error uses exact-pitch
    onset matches. Register accuracy asks whether chroma-matched notes also
    occupy the same MIDI octave.
    """

    reference_notes = _validated_notes(reference, "reference")
    estimate_notes = _validated_notes(estimate, "estimate")
    tolerance = _positive_finite_tolerance(tolerance_seconds)
    exact_pitch = _align_notes(
        reference_notes,
        estimate_notes,
        tolerance=tolerance,
        pitch_mode="exact",
    )
    chroma = _align_notes(
        reference_notes,
        estimate_notes,
        tolerance=tolerance,
        pitch_mode="chroma",
    )
    onset_only = _align_notes(
        reference_notes,
        estimate_notes,
        tolerance=tolerance,
        pitch_mode="ignore",
    )
    _require_nested_alignment_counts(
        exact_pitch=exact_pitch,
        chroma=chroma,
        onset_only=onset_only,
    )
    reference_active = bool(reference_notes)
    reference_count = len(reference_notes)
    estimate_count = len(estimate_notes)
    return {
        "schema": "sunofriend.private-demucs-midi-note-metrics.v1",
        "status": (
            "active_reference_comparison"
            if reference_active
            else "silent_reference_false_positive_observation"
        ),
        "tolerance_ms": round(tolerance * 1000.0, 9),
        "reference_active": reference_active,
        "counts": {
            "reference": reference_count,
            "estimate": estimate_count,
            "false_positive_against_silence": (
                None if reference_active else estimate_count
            ),
        },
        "exact_pitch_onset": _match_scores(
            exact_pitch,
            reference_count=reference_count,
            estimate_count=estimate_count,
            reference_active=reference_active,
        ),
        "chroma_onset": _match_scores(
            chroma,
            reference_count=reference_count,
            estimate_count=estimate_count,
            reference_active=reference_active,
        ),
        "onset_only": _match_scores(
            onset_only,
            reference_count=reference_count,
            estimate_count=estimate_count,
            reference_active=reference_active,
        ),
        "exact_pitch_accuracy_among_onset_only_matches": _nested_match_accuracy(
            numerator=exact_pitch,
            denominator=onset_only,
            condition="maximum-cardinality event-onset match count",
            success=(
                "a separate maximum-cardinality exact-pitch-and-onset "
                "alignment also recovers the event"
            ),
            reference_active=reference_active,
        ),
        "pitch_class_accuracy_among_onset_only_matches": _nested_match_accuracy(
            numerator=chroma,
            denominator=onset_only,
            condition="maximum-cardinality event-onset match count",
            success=(
                "a separate maximum-cardinality pitch-class-and-onset "
                "alignment also recovers the event"
            ),
            reference_active=reference_active,
        ),
        "octave_register_accuracy_conditional_on_chroma_matches": (
            _nested_match_accuracy(
                numerator=exact_pitch,
                denominator=chroma,
                condition="maximum-cardinality pitch-class-and-onset match count",
                success=(
                    "a separate maximum-cardinality exact-pitch-and-onset "
                    "alignment also recovers the chroma match in the same register"
                ),
                reference_active=reference_active,
            )
        ),
        "onset_timing_from_onset_only_matches": _onset_timing(
            onset_only,
            reference_active=reference_active,
        ),
        "same_pitch_duration_error": _note_duration_error(
            exact_pitch,
            reference_notes,
            estimate_notes,
            reference_active=reference_active,
        ),
        "semantics": {
            "matching": (
                "deterministic one-to-one earliest-compatible alignment; "
                "the tolerance boundary is inclusive"
            ),
            "precision": "matched estimate events divided by all estimate events",
            "recall": "matched reference events divided by all reference events",
            "onset_error": (
                "absolute estimate-minus-reference onset error over event-onset matches"
            ),
            "onset_drift": (
                "last signed estimate-minus-reference onset error minus the first, "
                "ordered by reference onset; unavailable with fewer than two matches"
            ),
            "duration_error": (
                "absolute estimate-minus-reference duration error over exact-pitch "
                "onset matches"
            ),
            "nested_accuracy": (
                "a ratio of separate nested maximum-cardinality alignment counts, "
                "not a pitch reclassification of arbitrary event-onset pair objects"
            ),
            "p95": (
                "95th percentile with linear interpolation over sorted absolute errors"
            ),
            "silent_reference": (
                "an empty reference reports estimate events as false positives; "
                "precision, recall and F1 remain unavailable rather than perfect"
            ),
        },
    }


def _compare_drum_hits(
    reference_hits: Sequence[DrumHit],
    estimate_hits: Sequence[DrumHit],
    *,
    tolerance_seconds: float = _DEFAULT_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Compare drum onsets once without pitch and once by exact family."""

    reference = _validated_hits(reference_hits, "reference")
    estimate = _validated_hits(estimate_hits, "estimate")
    tolerance = _positive_finite_tolerance(tolerance_seconds)
    onset_only = _align_hits(
        reference,
        estimate,
        tolerance=tolerance,
        family_mode="ignore",
    )
    broad_family = _align_hits(
        reference,
        estimate,
        tolerance=tolerance,
        family_mode="broad",
    )
    articulation_family = _align_hits(
        reference,
        estimate,
        tolerance=tolerance,
        family_mode="articulation",
    )
    reference_active = bool(reference)
    reference_count = len(reference)
    estimate_count = len(estimate)
    return {
        "schema": "sunofriend.private-demucs-midi-drum-metrics.v1",
        "status": (
            "active_reference_comparison"
            if reference_active
            else "silent_reference_false_positive_observation"
        ),
        "tolerance_ms": round(tolerance * 1000.0, 9),
        "reference_active": reference_active,
        "counts": {
            "reference": reference_count,
            "estimate": estimate_count,
            "false_positive_against_silence": (
                None if reference_active else estimate_count
            ),
        },
        "broad_family_counts": {
            "reference": _family_counts(
                reference,
                family_mode="broad",
            ),
            "estimate": _family_counts(
                estimate,
                family_mode="broad",
            ),
        },
        "articulation_family_counts": {
            "reference": _family_counts(reference),
            "estimate": _family_counts(estimate),
        },
        "onset_only": _match_scores(
            onset_only,
            reference_count=reference_count,
            estimate_count=estimate_count,
            reference_active=reference_active,
        ),
        "broad_family_onset": _match_scores(
            broad_family,
            reference_count=reference_count,
            estimate_count=estimate_count,
            reference_active=reference_active,
        ),
        "articulation_family_onset": _match_scores(
            articulation_family,
            reference_count=reference_count,
            estimate_count=estimate_count,
            reference_active=reference_active,
        ),
        "onset_only_timing": _onset_timing(
            onset_only,
            reference_active=reference_active,
        ),
        "broad_family_timing": _onset_timing(
            broad_family,
            reference_active=reference_active,
        ),
        "articulation_family_timing": _onset_timing(
            articulation_family,
            reference_active=reference_active,
        ),
        "semantics": {
            "matching": (
                "deterministic one-to-one earliest-compatible alignment; "
                "the tolerance boundary is inclusive"
            ),
            "onset_only": "family and GM pitch are ignored",
            "broad_family": (
                "classifier family is reduced to kick, snare, hat, toms, "
                "cymbals or percussion_other before onset matching"
            ),
            "articulation_family": (
                "exact classifier articulation text and onset must both match; "
                "GM pitch is not compared"
            ),
            "timing": (
                "absolute estimate-minus-reference onset error over the named matches; "
                "drift is last signed error minus first signed error"
            ),
            "p95": (
                "95th percentile with linear interpolation over sorted absolute errors"
            ),
            "silent_reference": (
                "an empty reference reports estimate hits as false positives; "
                "precision, recall and F1 remain unavailable rather than perfect"
            ),
        },
    }


def _align_notes(
    reference: Sequence[NoteEvent],
    estimate: Sequence[NoteEvent],
    *,
    tolerance: float,
    pitch_mode: str,
) -> AlignmentResult:
    def pitch(note: NoteEvent) -> int:
        if pitch_mode == "exact":
            return note.pitch
        if pitch_mode == "chroma":
            return note.pitch % 12
        return 0

    return align_events(
        [
            AlignmentEvent(index, note.start, pitch(note))
            for index, note in enumerate(reference)
        ],
        [
            AlignmentEvent(index, note.start, pitch(note))
            for index, note in enumerate(estimate)
        ],
        left_offset=0.0,
        right_offset=0.0,
        tolerance=tolerance,
        pitch_policy="exact_integer",
        require_exact_label=False,
        matching_policy=_MATCHING_POLICY,
    )


def _align_hits(
    reference: Sequence[DrumHit],
    estimate: Sequence[DrumHit],
    *,
    tolerance: float,
    family_mode: str,
) -> AlignmentResult:
    if family_mode not in {"ignore", "broad", "articulation"}:
        raise ValueError("drum family mode is invalid")

    def label(hit: DrumHit) -> str | None:
        if family_mode == "ignore":
            return None
        if family_mode == "broad":
            return _broad_drum_family(hit.family)
        return hit.family

    return align_events(
        [
            AlignmentEvent(
                source_index=index,
                onset=hit.time,
                pitch=0,
                label=label(hit),
            )
            for index, hit in enumerate(reference)
        ],
        [
            AlignmentEvent(
                source_index=index,
                onset=hit.time,
                pitch=0,
                label=label(hit),
            )
            for index, hit in enumerate(estimate)
        ],
        left_offset=0.0,
        right_offset=0.0,
        tolerance=tolerance,
        pitch_policy="exact_integer",
        require_exact_label=family_mode != "ignore",
        matching_policy=_MATCHING_POLICY,
    )


def _match_scores(
    alignment: AlignmentResult,
    *,
    reference_count: int,
    estimate_count: int,
    reference_active: bool,
) -> dict[str, Any]:
    matched = len(alignment.matches)
    false_positive_count = estimate_count - matched
    false_negative_count = reference_count - matched
    if not reference_active:
        return {
            "applicable": False,
            "reason": "reference_is_empty_or_silent",
            "matched_count": 0,
            "false_positive_count": estimate_count,
            "false_negative_count": 0,
            "precision": None,
            "recall": None,
            "f1": None,
        }
    precision = matched / estimate_count if estimate_count else 0.0
    recall = matched / reference_count
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "applicable": True,
        "matched_count": matched,
        "false_positive_count": false_positive_count,
        "false_negative_count": false_negative_count,
        "precision": round(precision, 9),
        "recall": round(recall, 9),
        "f1": round(f1, 9),
    }


def _nested_match_accuracy(
    *,
    numerator: AlignmentResult,
    denominator: AlignmentResult,
    condition: str,
    success: str,
    reference_active: bool,
) -> dict[str, Any]:
    matched = len(denominator.matches)
    if not reference_active:
        return {
            "applicable": False,
            "reason": "reference_is_empty_or_silent",
            "matched_count": 0,
            "correct_count": 0,
            "value": None,
            "condition": condition,
            "success": success,
        }
    if not matched:
        return {
            "applicable": False,
            "reason": "no_condition_matches",
            "matched_count": 0,
            "correct_count": 0,
            "value": None,
            "condition": condition,
            "success": success,
        }
    correct = len(numerator.matches)
    if correct > matched:
        raise ValueError(
            "more constrained MIDI alignment exceeded its parent alignment"
        )
    return {
        "applicable": True,
        "matched_count": matched,
        "correct_count": correct,
        "value": round(correct / matched, 9),
        "condition": condition,
        "success": success,
    }


def _onset_timing(
    alignment: AlignmentResult,
    *,
    reference_active: bool,
) -> dict[str, Any]:
    if not reference_active:
        return {
            "applicable": False,
            "reason": "reference_is_empty_or_silent",
            "matched_count": 0,
            "absolute_error_median_ms": None,
            "absolute_error_p95_ms": None,
            "signed_error_drift_ms": None,
            "drift_applicable": False,
        }
    signed_errors = [match.onset_delta_seconds * 1000.0 for match in alignment.matches]
    if not signed_errors:
        return {
            "applicable": False,
            "reason": "no_onset_matches",
            "matched_count": 0,
            "absolute_error_median_ms": None,
            "absolute_error_p95_ms": None,
            "signed_error_drift_ms": None,
            "drift_applicable": False,
        }
    absolute_errors = [abs(value) for value in signed_errors]
    return {
        "applicable": True,
        "matched_count": len(signed_errors),
        "absolute_error_median_ms": _rounded_median(absolute_errors),
        "absolute_error_p95_ms": _rounded_percentile(absolute_errors, 0.95),
        "signed_error_drift_ms": (
            _rounded(signed_errors[-1] - signed_errors[0])
            if len(signed_errors) >= 2
            else None
        ),
        "drift_applicable": len(signed_errors) >= 2,
    }


def _note_duration_error(
    alignment: AlignmentResult,
    reference: Sequence[NoteEvent],
    estimate: Sequence[NoteEvent],
    *,
    reference_active: bool,
) -> dict[str, Any]:
    if not reference_active:
        return {
            "applicable": False,
            "reason": "reference_is_empty_or_silent",
            "same_pitch_match_count": 0,
            "absolute_error_median_ms": None,
            "absolute_error_p95_ms": None,
        }
    errors = [
        abs(
            (estimate[match.right_index].end - estimate[match.right_index].start)
            - (reference[match.left_index].end - reference[match.left_index].start)
        )
        * 1000.0
        for match in alignment.matches
    ]
    if not errors:
        return {
            "applicable": False,
            "reason": "no_exact_pitch_onset_matches",
            "same_pitch_match_count": 0,
            "absolute_error_median_ms": None,
            "absolute_error_p95_ms": None,
        }
    return {
        "applicable": True,
        "same_pitch_match_count": len(errors),
        "absolute_error_median_ms": _rounded_median(errors),
        "absolute_error_p95_ms": _rounded_percentile(errors, 0.95),
    }


def _family_counts(
    hits: Sequence[DrumHit],
    *,
    family_mode: str = "articulation",
) -> dict[str, int]:
    if family_mode == "articulation":
        values = (hit.family for hit in hits)
    elif family_mode == "broad":
        values = (_broad_drum_family(hit.family) for hit in hits)
    else:
        raise ValueError("drum family mode is invalid")
    return dict(sorted(Counter(values).items()))


def _broad_drum_family(family: str) -> str:
    normalized = family.strip().lower()
    if normalized == "kick" or normalized.startswith("kick_"):
        return "kick"
    if normalized == "snare" or normalized.startswith("snare_"):
        return "snare"
    if normalized == "hat" or normalized.startswith("hat_"):
        return "hat"
    if normalized in {"tom", "toms"} or normalized.startswith("tom_"):
        return "toms"
    if normalized in {"cymbals", "crash", "ride"}:
        return "cymbals"
    if normalized in {"unknown", "perc", "percussion_other", "other_kit"}:
        return "percussion_other"
    raise ValueError(f"unsupported drum articulation family: {family!r}")


def _require_nested_alignment_counts(
    *,
    exact_pitch: AlignmentResult,
    chroma: AlignmentResult,
    onset_only: AlignmentResult,
) -> None:
    exact_count = len(exact_pitch.matches)
    chroma_count = len(chroma.matches)
    onset_count = len(onset_only.matches)
    if not 0 <= exact_count <= chroma_count <= onset_count:
        raise ValueError("MIDI alignment counts violate exact <= chroma <= event-onset")


def _validated_notes(
    values: Sequence[NoteEvent],
    label: str,
) -> tuple[NoteEvent, ...]:
    rows = _sequence(values, f"{label} notes")
    if any(not isinstance(value, NoteEvent) for value in rows):
        raise ValueError(f"{label} notes contain a malformed value")
    for note in rows:
        start = _finite_real(note.start, f"{label} note start")
        end = _finite_real(note.end, f"{label} note end")
        if start < 0 or end < start:
            raise ValueError(
                f"{label} note times must be non-negative and end at or after start"
            )
        if (
            isinstance(note.pitch, bool)
            or not isinstance(note.pitch, Integral)
            or not 0 <= int(note.pitch) <= 127
        ):
            raise ValueError(f"{label} note pitch must be an integer from 0 to 127")
    return rows


def _validated_hits(
    values: Sequence[DrumHit],
    label: str,
) -> tuple[DrumHit, ...]:
    rows = _sequence(values, f"{label} drum hits")
    if any(not isinstance(value, DrumHit) for value in rows):
        raise ValueError(f"{label} drum hits contain a malformed value")
    for hit in rows:
        time = _finite_real(hit.time, f"{label} drum hit time")
        if time < 0:
            raise ValueError(f"{label} drum hit time must be non-negative")
        if not isinstance(hit.family, str) or not hit.family.strip():
            raise ValueError(f"{label} drum hit family must be non-empty text")
    return rows


def _sequence(values: Any, label: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{label} must be a sequence")
    return tuple(values)


def _positive_finite_tolerance(value: Any) -> float:
    converted = _finite_real(value, "tolerance_seconds")
    if converted <= 0:
        raise ValueError("tolerance_seconds must be positive")
    return converted


def _finite_real(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def _rounded_median(values: Sequence[float]) -> float:
    return _rounded(float(statistics.median(values)))


def _rounded_percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return _rounded(ordered[0])
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return _rounded(ordered[lower])
    weight = position - lower
    return _rounded(ordered[lower] + weight * (ordered[upper] - ordered[lower]))


def _rounded(value: float) -> float:
    rounded = round(value, 9)
    return 0.0 if rounded == 0 else rounded


__all__: tuple[str, ...] = ()
