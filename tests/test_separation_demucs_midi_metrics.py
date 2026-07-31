from __future__ import annotations

import json
import math

import pytest

from sunofriend._separation_demucs_midi_metrics import (
    __all__,
    _compare_drum_hits,
    _compare_note_events,
)
from sunofriend.models import NoteEvent
from sunofriend.transcribe_drums import DrumHit


def _note(
    start: float,
    pitch: int,
    *,
    duration: float = 0.5,
) -> NoteEvent:
    return NoteEvent(start, start + duration, pitch, 90)


def _hit(
    time: float,
    family: str,
    *,
    gm_pitch: int | None = None,
) -> DrumHit:
    default_pitch = {
        "kick": 36,
        "kick_deep": 36,
        "kick_high": 35,
        "snare": 38,
        "snare_body": 38,
        "hat": 42,
        "hat_closed": 42,
        "perc": 39,
        "unknown": 39,
    }.get(family, 39)
    return DrumHit(
        time=time,
        gm_pitch=default_pitch if gm_pitch is None else gm_pitch,
        velocity=90,
        strength=1.0,
        family=family,
    )


def test_note_metrics_distinguish_pitch_chroma_register_and_onset() -> None:
    reference = [
        _note(0.0, 60, duration=0.5),
        _note(1.0, 64, duration=0.4),
        _note(2.0, 67, duration=0.5),
    ]
    estimate = [
        _note(0.02, 72, duration=0.6),
        _note(1.06, 65, duration=0.3),
        _note(2.08, 67, duration=0.7),
        _note(3.0, 69),
    ]

    result = _compare_note_events(
        reference,
        estimate,
        tolerance_seconds=0.08,
    )

    assert result["status"] == "active_reference_comparison"
    assert result["tolerance_ms"] == 80.0
    assert result["counts"] == {
        "reference": 3,
        "estimate": 4,
        "false_positive_against_silence": None,
    }
    assert result["exact_pitch_onset"] == {
        "applicable": True,
        "matched_count": 1,
        "false_positive_count": 3,
        "false_negative_count": 2,
        "precision": 0.25,
        "recall": 0.333333333,
        "f1": 0.285714286,
    }
    assert result["chroma_onset"]["matched_count"] == 2
    assert result["chroma_onset"]["f1"] == 0.571428571
    assert result["onset_only"]["matched_count"] == 3
    assert result["onset_only"]["f1"] == 0.857142857
    assert result["pitch_class_accuracy_among_onset_only_matches"]["value"] == (
        0.666666667
    )
    pitch_accuracy = result["exact_pitch_accuracy_among_onset_only_matches"]
    assert pitch_accuracy["matched_count"] == 3
    assert pitch_accuracy["correct_count"] == 1
    assert pitch_accuracy["value"] == 0.333333333
    register_accuracy = result["octave_register_accuracy_conditional_on_chroma_matches"]
    assert register_accuracy["matched_count"] == 2
    assert register_accuracy["correct_count"] == 1
    assert register_accuracy["value"] == 0.5
    timing = result["onset_timing_from_onset_only_matches"]
    assert timing == {
        "applicable": True,
        "matched_count": 3,
        "absolute_error_median_ms": 60.0,
        "absolute_error_p95_ms": 78.0,
        "signed_error_drift_ms": 60.0,
        "drift_applicable": True,
    }
    assert result["same_pitch_duration_error"] == {
        "applicable": True,
        "same_pitch_match_count": 1,
        "absolute_error_median_ms": 200.0,
        "absolute_error_p95_ms": 200.0,
    }
    json.dumps(result, allow_nan=False)


def test_note_duration_percentiles_use_exact_pitch_matches_only() -> None:
    reference = [
        _note(0.0, 60, duration=0.5),
        _note(1.0, 62, duration=0.5),
        _note(2.0, 64, duration=0.5),
    ]
    estimate = [
        _note(0.0, 60, duration=0.5),
        _note(1.0, 62, duration=0.6),
        _note(2.0, 64, duration=0.8),
    ]

    duration = _compare_note_events(reference, estimate)["same_pitch_duration_error"]

    assert duration["same_pitch_match_count"] == 3
    assert duration["absolute_error_median_ms"] == 100.0
    assert duration["absolute_error_p95_ms"] == 280.0


def test_large_simultaneous_polyphony_does_not_depend_on_pairing_order() -> None:
    reference = [_note(0.0, pitch) for pitch in range(36, 76)]
    estimate = list(reversed(reference))

    result = _compare_note_events(reference, estimate)

    assert result["exact_pitch_onset"]["matched_count"] == 40
    assert result["chroma_onset"]["matched_count"] == 40
    assert result["onset_only"]["matched_count"] == 40
    assert result["exact_pitch_accuracy_among_onset_only_matches"]["value"] == 1.0
    assert result["pitch_class_accuracy_among_onset_only_matches"]["value"] == 1.0
    assert (
        result["octave_register_accuracy_conditional_on_chroma_matches"]["value"] == 1.0
    )


@pytest.mark.parametrize("estimate_count", [0, 2])
def test_empty_note_reference_is_never_reported_as_perfect(
    estimate_count: int,
) -> None:
    estimate = [_note(float(index), 60 + index) for index in range(estimate_count)]

    result = _compare_note_events([], estimate)

    assert result["status"] == "silent_reference_false_positive_observation"
    assert result["reference_active"] is False
    assert result["counts"]["false_positive_against_silence"] == estimate_count
    for name in ("exact_pitch_onset", "chroma_onset", "onset_only"):
        metric = result[name]
        assert metric["applicable"] is False
        assert metric["false_positive_count"] == estimate_count
        assert metric["precision"] is None
        assert metric["recall"] is None
        assert metric["f1"] is None
    assert result["exact_pitch_accuracy_among_onset_only_matches"]["value"] is None
    assert (
        result["octave_register_accuracy_conditional_on_chroma_matches"]["value"]
        is None
    )
    assert (
        result["onset_timing_from_onset_only_matches"]["absolute_error_median_ms"]
        is None
    )


def test_active_note_reference_with_no_estimate_is_a_complete_miss() -> None:
    result = _compare_note_events([_note(0.0, 60)], [])

    for name in ("exact_pitch_onset", "chroma_onset", "onset_only"):
        metric = result[name]
        assert metric["applicable"] is True
        assert metric["matched_count"] == 0
        assert metric["false_positive_count"] == 0
        assert metric["false_negative_count"] == 1
        assert metric["precision"] == 0.0
        assert metric["recall"] == 0.0
        assert metric["f1"] == 0.0
    assert result["onset_timing_from_onset_only_matches"]["applicable"] is False
    assert result["same_pitch_duration_error"]["applicable"] is False


def test_note_tolerance_is_inclusive_and_defaults_to_forty_ms() -> None:
    reference = [_note(1.0, 60)]

    boundary = _compare_note_events(reference, [_note(1.04, 60)])
    outside = _compare_note_events(reference, [_note(1.040001, 60)])

    assert boundary["exact_pitch_onset"]["matched_count"] == 1
    assert outside["exact_pitch_onset"]["matched_count"] == 0
    assert (
        boundary["onset_timing_from_onset_only_matches"]["signed_error_drift_ms"]
        is None
    )
    assert boundary["onset_timing_from_onset_only_matches"]["drift_applicable"] is False


def test_drum_metrics_separate_onsets_from_exact_families() -> None:
    reference = [
        _hit(0.0, "kick"),
        _hit(1.0, "snare"),
        _hit(2.0, "hat"),
    ]
    estimate = [
        _hit(0.01, "kick"),
        _hit(1.03, "kick"),
        _hit(2.08, "hat"),
        _hit(3.0, "perc"),
    ]

    result = _compare_drum_hits(
        reference,
        estimate,
        tolerance_seconds=0.08,
    )

    assert result["broad_family_counts"] == {
        "reference": {"hat": 1, "kick": 1, "snare": 1},
        "estimate": {"hat": 1, "kick": 2, "percussion_other": 1},
    }
    assert result["articulation_family_counts"] == {
        "reference": {"hat": 1, "kick": 1, "snare": 1},
        "estimate": {"hat": 1, "kick": 2, "perc": 1},
    }
    assert result["onset_only"]["matched_count"] == 3
    assert result["onset_only"]["f1"] == 0.857142857
    assert result["broad_family_onset"]["matched_count"] == 2
    assert result["broad_family_onset"]["f1"] == 0.571428571
    assert result["articulation_family_onset"]["matched_count"] == 2
    assert result["articulation_family_onset"]["f1"] == 0.571428571
    assert result["onset_only_timing"] == {
        "applicable": True,
        "matched_count": 3,
        "absolute_error_median_ms": 30.0,
        "absolute_error_p95_ms": 75.0,
        "signed_error_drift_ms": 70.0,
        "drift_applicable": True,
    }
    assert result["articulation_family_timing"] == {
        "applicable": True,
        "matched_count": 2,
        "absolute_error_median_ms": 45.0,
        "absolute_error_p95_ms": 76.5,
        "signed_error_drift_ms": 70.0,
        "drift_applicable": True,
    }
    json.dumps(result, allow_nan=False)


def test_drum_metrics_distinguish_broad_family_from_articulation() -> None:
    result = _compare_drum_hits(
        [_hit(0.0, "kick_deep")],
        [_hit(0.0, "kick_high")],
    )

    assert result["onset_only"]["f1"] == 1.0
    assert result["broad_family_onset"]["f1"] == 1.0
    assert result["articulation_family_onset"]["f1"] == 0.0


def test_unknown_gm_39_articulation_is_not_counted_as_broad_snare() -> None:
    result = _compare_drum_hits(
        [_hit(0.0, "snare_body")],
        [_hit(0.0, "unknown")],
    )

    assert result["onset_only"]["f1"] == 1.0
    assert result["broad_family_onset"]["f1"] == 0.0
    assert result["articulation_family_onset"]["f1"] == 0.0


@pytest.mark.parametrize("estimate_count", [0, 2])
def test_empty_drum_reference_reports_only_false_positive_evidence(
    estimate_count: int,
) -> None:
    estimate = [_hit(float(index), "kick") for index in range(estimate_count)]

    result = _compare_drum_hits([], estimate)

    assert result["reference_active"] is False
    assert result["counts"]["false_positive_against_silence"] == estimate_count
    for name in (
        "onset_only",
        "broad_family_onset",
        "articulation_family_onset",
    ):
        assert result[name]["applicable"] is False
        assert result[name]["false_positive_count"] == estimate_count
        assert result[name]["f1"] is None
    assert result["onset_only_timing"]["applicable"] is False
    assert result["broad_family_timing"]["applicable"] is False
    assert result["articulation_family_timing"]["applicable"] is False


@pytest.mark.parametrize("tolerance", [0.0, -0.1, math.inf, math.nan, True])
def test_comparators_reject_invalid_tolerances(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance_seconds"):
        _compare_note_events([], [], tolerance_seconds=tolerance)
    with pytest.raises(ValueError, match="tolerance_seconds"):
        _compare_drum_hits([], [], tolerance_seconds=tolerance)


def test_comparators_reject_malformed_events_without_mutating_inputs() -> None:
    reference = [_note(0.0, 60)]
    estimate = [_note(0.02, 60)]
    reference_before = list(reference)
    estimate_before = list(estimate)

    _compare_note_events(reference, estimate)

    assert reference == reference_before
    assert estimate == estimate_before
    with pytest.raises(ValueError, match="malformed"):
        _compare_note_events([object()], [])
    with pytest.raises(ValueError, match="end at or after start"):
        _compare_note_events([NoteEvent(1.0, 0.5, 60, 90)], [])
    with pytest.raises(ValueError, match="malformed"):
        _compare_drum_hits([object()], [])
    with pytest.raises(ValueError, match="non-empty text"):
        _compare_drum_hits([_hit(0.0, " ")], [])


def test_private_module_exports_nothing() -> None:
    assert __all__ == ()
