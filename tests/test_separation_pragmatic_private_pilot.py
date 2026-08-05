from __future__ import annotations

import pytest

from sunofriend._separation_pragmatic_private_pilot import (
    _path_free_artifact_binding,
    _require_pragmatic_gate,
    _validated_absolute_assessment,
    _validated_review_summary,
)


def test_whole_song_good_enough_can_pass_despite_microscopic_edge_ambiguity() -> None:
    assessment = _assessment()
    summary = _validated_review_summary(_review_result())

    _require_pragmatic_gate(assessment, review_summary=summary)

    assert summary == {
        "reviewed_unit_count": 36,
        "choice_counts": {
            "equivalent": 25,
            "followup_control_preferred": 2,
            "neither": 9,
        },
        "followup_control_preference_count": 2,
        "replacement_variant_preference_count": 0,
        "replacement_variant_showed_audible_advantage": False,
    }


def test_normal_listening_join_problem_blocks_private_pilot() -> None:
    assessment = _assessment()
    assessment["joins_generally_noticeable"] = True

    with pytest.raises(ValueError, match="private-pilot gate"):
        _require_pragmatic_gate(
            assessment,
            review_summary=_validated_review_summary(_review_result()),
        )


def test_replacement_preference_blocks_automatic_control_selection() -> None:
    result = _review_result()
    result["units"][0]["resolved_choice"] = "shifted_variant_preferred"

    with pytest.raises(ValueError, match="private-pilot gate"):
        _require_pragmatic_gate(
            _assessment(), review_summary=_validated_review_summary(result)
        )


def test_quality_labels_do_not_accept_poor_or_cannot_tell() -> None:
    assessment = _assessment()
    assessment["overall_audio_quality"] = "poor"

    with pytest.raises(ValueError, match="assessment values"):
        _validated_absolute_assessment(assessment)


def test_artifact_binding_excludes_source_path() -> None:
    artifact = {
        "path": "CANDIDATES/vocals.wav",
        "sha256": "a" * 64,
        "pcm24_int32_sequence_sha256": "b" * 64,
        "bytes": 123,
        "geometry": {
            "channels": 2,
            "frames": 100,
            "sample_rate": 44_100,
            "sample_width_bytes": 3,
        },
    }

    binding = _path_free_artifact_binding(artifact, role="vocals")

    assert binding["role"] == "vocals"
    assert "path" not in binding


def _assessment() -> dict[str, object]:
    return _validated_absolute_assessment(
        {
            "overall_audio_quality": "good_or_good_enough",
            "listener_assessed_separator_accuracy": "good_or_good_enough",
            "joins_generally_noticeable": False,
            "joins_detectable_when_cued_with_concentrated_headphones": True,
            "joins_reduce_musical_usefulness": False,
            "patch_edge_beat_ambiguity_present": True,
        }
    )


def _review_result() -> dict[str, object]:
    choices = (
        ["equivalent"] * 25
        + ["followup_control_preferred"] * 2
        + ["neither"] * 9
    )
    return {"units": [{"resolved_choice": choice} for choice in choices]}
