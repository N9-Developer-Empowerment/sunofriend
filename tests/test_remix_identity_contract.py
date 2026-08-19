from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import pytest

from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
)
from sunofriend.remix_identity import (
    REMIX_IDENTITY_STATE_SCHEMA,
    REMIX_REQUEST_SCHEMA,
    REMIX_RESULT_SCHEMA,
    REMIX_REVIEW_SCHEMA,
    create_remix_identity_state,
    create_remix_request,
    create_remix_result,
    create_remix_review,
    validate_remix_identity_state,
    validate_remix_request,
    validate_remix_result,
    validate_remix_review,
)
from sunofriend.source_receipt import document_sha256


def test_identity_state_binds_owner_labels_to_separation_estimates() -> None:
    musical_state = _musical_state()
    identity = _identity_state(musical_state)

    assert identity["schema"] == REMIX_IDENTITY_STATE_SCHEMA
    assert identity["status"] == "complete_owner_anchored_no_remix"
    assert identity["binding"] == {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": musical_state["document_sha256"],
    }
    assert identity["method_natures"] == ["D", "H"]
    assert identity["model_used"] is False
    assert identity["training_used"] is False
    assert identity["network_used"] is False
    assert not any(identity["effects"].values())

    estimate = identity["separation_estimates"][0]
    assert estimate["source_estimate_id"] == "grouped-other-estimate-001"
    assert estimate["source_kind"] == "separation_estimate"
    assert estimate["role_interpretation"] == "estimate_not_ground_truth"
    assert estimate["estimated_role"] == "grouped_other"

    anchor = identity["owner_anchors"][0]
    assert anchor["anchor_id"] == "chorus-accompaniment-hook"
    assert anchor["owner_label"] == (
        "The accompaniment hook that makes the song recognisable"
    )
    assert anchor["label_authority"] == "explicit_owner_label"
    assert anchor["source_estimate_id"] == estimate["source_estimate_id"]
    assert anchor["geometry"] == {
        "sample_rate_hz": 8_000,
        "start_frame": 8_000,
        "end_frame": 16_000,
    }
    assert validate_remix_identity_state(identity, musical_state) == identity
    _assert_path_free(identity)


def test_identity_state_rejects_other_state_and_ground_truth_language() -> None:
    musical_state = _musical_state()
    identity = _identity_state(musical_state)

    other_state = deepcopy(musical_state)
    other_state["clock"]["bpm"] = 101.0
    _rehash(other_state)
    with pytest.raises(ValueError, match="musical.state|state.*SHA-256|state.*hash"):
        validate_remix_identity_state(identity, other_state)

    changed = deepcopy(identity)
    changed["separation_estimates"][0]["source_kind"] = "original_studio_stem"
    changed["separation_estimates"][0]["role_interpretation"] = "ground_truth"
    _rehash(changed)
    with pytest.raises(ValueError, match="separation estimate|ground truth|estimate"):
        validate_remix_identity_state(changed, musical_state)


def test_request_contains_one_bounded_delta_envelope_and_no_model_work() -> None:
    musical_state = _musical_state()
    identity = _identity_state(musical_state)
    request = _request(identity)

    assert request["schema"] == REMIX_REQUEST_SCHEMA
    assert request["status"] == "planned_deterministic_one_variable_remix"
    assert request["binding"] == {
        "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
        "identity_state_sha256": identity["document_sha256"],
        "musical_state_sha256": musical_state["document_sha256"],
    }
    assert request["method_natures"] == ["D"]
    assert request["model_used"] is False
    assert request["training_used"] is False
    assert request["network_used"] is False
    assert request["operation_count"] == 1
    assert request["one_variable_policy"] == "gain_delta_envelope_only"
    assert request["fixed_factors"] == [
        "source_audio_bytes",
        "clock",
        "duration",
        "channel_geometry",
        "all_non_target_sources",
    ]

    operation = request["operations"][0]
    assert operation == {
        "operation": "apply_gain_delta_envelope",
        "source_estimate_id": "grouped-other-estimate-001",
        "anchor_id": "chorus-accompaniment-hook",
        "start_frame": 8_000,
        "end_frame": 16_000,
        "points": [
            {"frame": 8_000, "delta_db": 0.0},
            {"frame": 12_000, "delta_db": -3.0},
            {"frame": 16_000, "delta_db": 0.0},
        ],
    }
    assert not any(request["effects"].values())
    assert validate_remix_request(request, identity) == request
    _assert_path_free(request)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda request: request["operations"].append(
                deepcopy(request["operations"][0])
            ),
            "one.*operation|operation count",
        ),
        (
            lambda request: request["operations"][0].update(
                {"pitch_shift_semitones": 2}
            ),
            "one.variable|delta envelope|unsupported",
        ),
        (
            lambda request: request["operations"][0].update({"start_frame": 8_001}),
            "geometry|anchor|frame",
        ),
        (
            lambda request: request.update({"model_used": True}),
            "model",
        ),
        (
            lambda request: request.update({"training_used": True}),
            "training",
        ),
        (
            lambda request: request.update({"network_used": True}),
            "network",
        ),
    ),
    ids=(
        "second-operation",
        "second-variable",
        "wrong-geometry",
        "model",
        "training",
        "network",
    ),
)
def test_request_rejects_scope_or_authority_expansion(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    identity = _identity_state(_musical_state())
    request = _request(identity)
    mutate(request)
    _rehash(request)

    with pytest.raises(ValueError, match=message):
        validate_remix_request(request, identity)


def test_result_is_exact_geometry_unreviewed_deterministic_evidence() -> None:
    musical_state = _musical_state()
    identity = _identity_state(musical_state)
    request = _request(identity)
    result = _result(request, identity)

    assert result["schema"] == REMIX_RESULT_SCHEMA
    assert result["status"] == "complete_unreviewed_deterministic_remix"
    assert result["binding"] == {
        "identity_state_sha256": identity["document_sha256"],
        "musical_state_sha256": musical_state["document_sha256"],
        "remix_request_schema": REMIX_REQUEST_SCHEMA,
        "remix_request_sha256": request["document_sha256"],
    }
    assert result["method_natures"] == ["D"]
    assert result["model_used"] is False
    assert result["training_used"] is False
    assert result["network_used"] is False
    assert result["review_status"] == "not_reviewed"
    assert result["owner_identity_preserved"] is None
    assert result["selected_for_product"] is False
    assert result["output"]["geometry"] == {
        "sample_rate_hz": 8_000,
        "channels": 1,
        "frames": 32_000,
    }
    assert result["effects"] == {
        "source_mutated": False,
        "identity_state_mutated": False,
        "request_mutated": False,
        "remix_audio_derivative_rendered": True,
        "human_review_created": False,
        "selection_created": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }
    assert validate_remix_result(result, request, identity) == result
    _assert_path_free(result)


def test_result_rejects_request_drift_geometry_drift_and_review_claims() -> None:
    identity = _identity_state(_musical_state())
    request = _request(identity)
    result = _result(request, identity)

    wrong_request = deepcopy(request)
    wrong_request["operations"][0]["points"][1]["delta_db"] = -2.0
    _rehash(wrong_request)
    with pytest.raises(
        ValueError, match="request.*SHA-256|request.*hash|request binding"
    ):
        validate_remix_result(result, wrong_request, identity)

    wrong_geometry = deepcopy(result)
    wrong_geometry["output"]["geometry"]["frames"] -= 1
    _rehash(wrong_geometry)
    with pytest.raises(ValueError, match="geometry|frames"):
        validate_remix_result(wrong_geometry, request, identity)

    false_review = deepcopy(result)
    false_review["review_status"] = "reviewed"
    false_review["owner_identity_preserved"] = True
    _rehash(false_review)
    with pytest.raises(ValueError, match="unreviewed|owner|identity"):
        validate_remix_result(false_review, request, identity)


def test_review_requires_explicit_owner_anchor_labels_not_playback() -> None:
    musical_state = _musical_state()
    identity = _identity_state(musical_state)
    request = _request(identity)
    result = _result(request, identity)
    labels = [
        {
            "anchor_id": "chorus-accompaniment-hook",
            "heard": True,
            "identity_relationship": "preserved",
            "musical_usefulness": "useful",
        }
    ]
    review = create_remix_review(
        result,
        request,
        identity,
        owner_anchor_labels=labels,
    )

    assert review["schema"] == REMIX_REVIEW_SCHEMA
    assert review["status"] == "complete_explicit_owner_review_no_selection"
    assert review["binding"] == {
        "identity_state_sha256": identity["document_sha256"],
        "musical_state_sha256": musical_state["document_sha256"],
        "remix_request_sha256": request["document_sha256"],
        "remix_result_schema": REMIX_RESULT_SCHEMA,
        "remix_result_sha256": result["document_sha256"],
    }
    assert review["owner_anchor_labels"] == labels
    assert review["method_natures"] == ["H"]
    assert review["label_authority"] == "explicit_owner_listening_decision"
    assert review["playback_inference_permitted"] is False
    assert review["model_used"] is False
    assert review["training_used"] is False
    assert review["network_used"] is False
    assert review["selected_for_product"] is False
    assert review["training_eligible"] is False
    assert not any(review["effects"].values())
    assert validate_remix_review(review, result, request, identity) == review
    _assert_path_free(review)


def test_review_rejects_playback_inference_incomplete_labels_and_hash_drift() -> None:
    identity = _identity_state(_musical_state())
    request = _request(identity)
    result = _result(request, identity)

    with pytest.raises(ValueError, match="owner.*label|anchor.*label|explicit"):
        create_remix_review(
            result,
            request,
            identity,
            owner_anchor_labels=[],
        )

    review = create_remix_review(
        result,
        request,
        identity,
        owner_anchor_labels=[
            {
                "anchor_id": "chorus-accompaniment-hook",
                "heard": True,
                "identity_relationship": "preserved",
                "musical_usefulness": "useful",
            }
        ],
    )
    playback_claim = deepcopy(review)
    playback_claim["label_authority"] = "inferred_from_playback"
    playback_claim["playback_inference_permitted"] = True
    _rehash(playback_claim)
    with pytest.raises(ValueError, match="playback|explicit owner"):
        validate_remix_review(playback_claim, result, request, identity)

    changed_result = deepcopy(result)
    changed_result["output"]["audio_sha256"] = "f" * 64
    _rehash(changed_result)
    with pytest.raises(ValueError, match="result.*SHA-256|result.*hash|result binding"):
        validate_remix_review(review, changed_result, request, identity)


def _identity_state(musical_state: dict[str, Any]) -> dict[str, Any]:
    return create_remix_identity_state(
        musical_state,
        separation_estimates=[
            {
                "source_estimate_id": "grouped-other-estimate-001",
                "source_kind": "separation_estimate",
                "estimated_role": "grouped_other",
                "role_interpretation": "estimate_not_ground_truth",
                "audio_sha256": "a" * 64,
                "audio_bytes": 96_044,
                "geometry": {
                    "sample_rate_hz": 8_000,
                    "channels": 1,
                    "frames": 32_000,
                },
            }
        ],
        owner_anchors=[
            {
                "anchor_id": "chorus-accompaniment-hook",
                "anchor_kind": "motif",
                "owner_label": (
                    "The accompaniment hook that makes the song recognisable"
                ),
                "label_authority": "explicit_owner_label",
                "source_estimate_id": "grouped-other-estimate-001",
                "geometry": {
                    "sample_rate_hz": 8_000,
                    "start_frame": 8_000,
                    "end_frame": 16_000,
                },
            }
        ],
    )


def _request(identity: dict[str, Any]) -> dict[str, Any]:
    return create_remix_request(
        identity,
        anchor_id="chorus-accompaniment-hook",
        source_estimate_id="grouped-other-estimate-001",
        delta_envelope_points=[
            {"frame": 8_000, "delta_db": 0.0},
            {"frame": 12_000, "delta_db": -3.0},
            {"frame": 16_000, "delta_db": 0.0},
        ],
    )


def _result(request: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    return create_remix_result(
        request,
        identity,
        output_audio_sha256="b" * 64,
        output_audio_bytes=96_044,
        output_geometry={
            "sample_rate_hz": 8_000,
            "channels": 1,
            "frames": 32_000,
        },
    )


def _musical_state() -> dict[str, Any]:
    empty_effects = {
        "source_mutated": False,
        "lyrics_mutated": False,
        "selection_created": False,
        "human_decision_created": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
        "training_started": False,
        "model_weights_changed": False,
        "remix_rendered": False,
    }
    state: dict[str, Any] = {
        "schema": MUSICAL_STATE_SCHEMA,
        "status": "complete_unreviewed_no_selection",
        "state_scope": "audio_native_vocal_foundation",
        "method_natures": ["D", "H"],
        "clock": {
            "origin": "common_recorded_song_zero",
            "bpm": 100.0,
            "tuning_hz": 440.0,
        },
        "authorization": {
            "rights_category": "owned",
            "rights_confirmed": True,
            "common_recorded_zero_confirmed": True,
        },
        "lyrics": {
            "canonical": _file_record("LYRICS/lyrics.txt", "1" * 64),
            "authority": "user_supplied_canonical",
            "automatic_rewrite_permitted": False,
        },
        "structure": {
            "phrase_timeline": _file_record(
                "TIMELINE/reviewed-phrase-timeline.json", "2" * 64
            ),
            "phrase_timeline_schema": VOCAL_COMP_TIMELINE_SCHEMA,
            "review_status": "reviewed",
            "phrases": [
                {
                    "phrase_id": "chorus-001",
                    "start_seconds": 1.0,
                    "end_seconds": 2.0,
                    "lyrics": "The heart sees",
                }
            ],
        },
        "vocal_performance_state": {
            "schema": VOCAL_PERFORMANCE_STATE_SCHEMA,
            "processing_chain": "dry",
            "reference": None,
            "takes": [],
            "continuous_f0_evidence": [],
            "lyric_phoneme_evidence": [],
            "non_pitched_event_evidence": [],
            "signal_quality_evidence": [],
            "explicit_phrase_decisions": [],
            "edit_maps": [],
            "correction_derivatives": [],
            "selection_authority": "human_only",
        },
        "optional_derived_evidence": {"midi": [], "notes": []},
        "training": {
            "explicit_labels": [],
            "training_eligible": False,
            "reason": "no explicit phrase comparison decision in this state",
        },
        "network_used": False,
        "effects": empty_effects,
    }
    _rehash(state)
    return state


def _file_record(path: str, sha256: str) -> dict[str, Any]:
    return {"path": path, "bytes": 1, "sha256": sha256}


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _assert_path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert key not in {"path", "absolute_path", "source_path", "output_path"}
            _assert_path_free(child)
    elif isinstance(value, list):
        for child in value:
            _assert_path_free(child)
    elif isinstance(value, str):
        assert not value.startswith("/")
        assert ":\\" not in value
