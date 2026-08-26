from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
)
from sunofriend.source_receipt import document_sha256
from sunofriend.vocal_pairwise_canary import (
    PAIRWISE_CANARY_RESULT_SCHEMA,
    SYNTHETIC_PAIRWISE_FIXTURE_SCHEMA,
    build_pairwise_ranker_canary_request,
    build_synthetic_pairwise_fixture,
    run_pairwise_ranker_canary,
    validate_pairwise_ranker_canary_result,
)
from sunofriend.vocal_pairwise_label import (
    VOCAL_PAIRWISE_LABEL_SCHEMA,
    create_vocal_pairwise_label,
    validate_vocal_pairwise_label,
)
from sunofriend.vocal_training_snapshot import (
    EVIDENCE_GATES,
    VOCAL_TRAINING_SNAPSHOT_SCHEMA,
    create_vocal_training_snapshot,
    validate_vocal_training_snapshot,
)


@pytest.mark.parametrize(
    ("outcome", "reasons"),
    (
        ("left", ["pitch_contour", "context_fit"]),
        ("right", ["phrase_completeness"]),
        ("equivalent", ["performance_consistency"]),
        ("neither", ["no_usable_attempt", "technical_quality"]),
        ("cannot_tell", ["unable_to_compare"]),
    ),
)
def test_explicit_pairwise_label_binds_state_phrase_and_two_sources(
    outcome: str, reasons: list[str]
) -> None:
    state = _musical_state()

    label = create_vocal_pairwise_label(
        state,
        phrase_id="phrase-001",
        left_source_id="take-001",
        right_source_id="take-002",
        outcome=outcome,
        reason_codes=reasons,
        reviewed_at="2026-08-20T12:00:00Z",
    )

    assert label["schema"] == VOCAL_PAIRWISE_LABEL_SCHEMA
    assert label["binding"]["musical_state_sha256"] == state["document_sha256"]
    assert label["left"]["audio_sha256"] == "4" * 64
    assert label["right"]["audio_sha256"] == "5" * 64
    assert label["outcome"] == outcome
    assert label["reason_codes"] == reasons
    assert label["training"]["explicit_pairwise_label"] is True
    assert label["training"]["training_eligible"] is False
    assert not any(label["interaction_limits"].values())
    assert not any(label["authority_limits"].values())
    assert validate_vocal_pairwise_label(label, musical_state=state) == label


def test_pairwise_label_rejects_inferred_or_ambiguous_actions() -> None:
    state = _musical_state()
    with pytest.raises(ValueError, match="outcome"):
        _label(state, outcome="played_longest", reasons=["context_fit"])
    with pytest.raises(ValueError, match="unable_to_compare"):
        _label(state, outcome="cannot_tell", reasons=["context_fit"])
    with pytest.raises(ValueError, match="no_usable_attempt"):
        _label(state, outcome="neither", reasons=["technical_quality"])
    with pytest.raises(ValueError, match="different sources"):
        create_vocal_pairwise_label(
            state,
            phrase_id="phrase-001",
            left_source_id="take-001",
            right_source_id="take-001",
            outcome="left",
            reason_codes=["context_fit"],
        )

    changed = _label(state)
    changed["interaction_limits"]["playback_implies_label"] = True
    _rehash(changed)
    with pytest.raises(ValueError, match="interaction"):
        validate_vocal_pairwise_label(changed, musical_state=state)


def test_pairwise_label_detects_state_source_and_private_field_tampering() -> None:
    state = _musical_state()
    label = _label(state)

    changed_source = deepcopy(label)
    changed_source["left"]["audio_sha256"] = "9" * 64
    _rehash(changed_source)
    with pytest.raises(ValueError, match="source identity"):
        validate_vocal_pairwise_label(changed_source, musical_state=state)

    changed_state = deepcopy(label)
    changed_state["binding"]["musical_state_sha256"] = "8" * 64
    _rehash(changed_state)
    with pytest.raises(ValueError, match="exact musical state"):
        validate_vocal_pairwise_label(changed_state, musical_state=state)

    changed_notes = deepcopy(label)
    changed_notes["review"]["notes"] = "private observation"
    _rehash(changed_notes)
    with pytest.raises(ValueError, match="authority|field|private"):
        validate_vocal_pairwise_label(changed_notes)


def test_pairwise_label_standalone_contract_accepts_exact_v3_capture_class() -> None:
    label = _label(_musical_state())
    label["right"] = {
        "source_id": "capture-001",
        "source_class": "human_vocal_phrase_capture",
        "audio_sha256": "6" * 64,
    }
    _rehash(label)

    assert validate_vocal_pairwise_label(label)["right"]["source_class"] == (
        "human_vocal_phrase_capture"
    )


def test_one_label_snapshot_is_path_free_and_training_ineligible() -> None:
    label = _label(_musical_state())
    snapshot = create_vocal_training_snapshot(
        [label],
        assignments=[
            {
                "label_document_sha256": label["document_sha256"],
                "composition_id": "heart-sees-owner-id",
                "group_id": "browser-round-001",
                "split": "train",
            }
        ],
        snapshot_id="vocal-pairwise-pilot-001",
    )

    assert snapshot["schema"] == VOCAL_TRAINING_SNAPSHOT_SCHEMA
    assert snapshot["status"] == "training_ineligible"
    assert snapshot["evidence_gate"]["observed"]["explicit_labels"] == 1
    assert snapshot["evidence_gate"]["evidence_gate_passed"] is False
    assert set(snapshot["evidence_gate"]["thresholds"]) == set(EVIDENCE_GATES)
    assert snapshot["authority"]["training_execution_authorized"] is False
    assert not any("notes" in row for row in snapshot["labels"])
    assert "/Users/" not in str(snapshot)
    assert validate_vocal_training_snapshot(snapshot) == snapshot

    changed_projection = deepcopy(snapshot)
    changed_projection["labels"][0]["left_audio_sha256"] = "9" * 64
    _rehash(changed_projection)
    with pytest.raises(ValueError, match="projection"):
        validate_vocal_training_snapshot(changed_projection)

    granted_authority = deepcopy(snapshot)
    granted_authority["authority"]["training_execution_authorized"] = True
    _rehash(granted_authority)
    with pytest.raises(ValueError, match="authority"):
        validate_vocal_training_snapshot(granted_authority)

    extra_authority = deepcopy(snapshot)
    extra_authority["training_approved"] = True
    _rehash(extra_authority)
    with pytest.raises(ValueError, match="fields"):
        validate_vocal_training_snapshot(extra_authority)


def test_snapshot_rejects_split_leakage_duplicate_pair_and_assignment_paths() -> None:
    first_state = _musical_state()
    first = _label(first_state)
    second_state = _musical_state(second_phrase=True)
    second = _label(second_state, phrase_id="phrase-002")
    assignments = [
        {
            "label_document_sha256": first["document_sha256"],
            "composition_id": "composition-001",
            "group_id": "group-001",
            "split": "train",
        },
        {
            "label_document_sha256": second["document_sha256"],
            "composition_id": "composition-001",
            "group_id": "group-002",
            "split": "test",
        },
    ]
    with pytest.raises(ValueError, match="composition.*disjoint"):
        create_vocal_training_snapshot(
            [first, second], assignments=assignments, snapshot_id="bad-split"
        )

    private_assignment = deepcopy(assignments[:1])
    private_assignment[0]["group_id"] = "/Users/private/round"
    with pytest.raises(ValueError, match="path-free"):
        create_vocal_training_snapshot(
            [first], assignments=private_assignment, snapshot_id="bad-private"
        )

    reversed_pair = create_vocal_pairwise_label(
        first_state,
        phrase_id="phrase-001",
        left_source_id="take-002",
        right_source_id="take-001",
        outcome="right",
        reason_codes=["context_fit"],
    )
    duplicate_assignments = [
        assignments[0],
        {
            "label_document_sha256": reversed_pair["document_sha256"],
            "composition_id": "composition-001",
            "group_id": "group-001",
            "split": "train",
        },
    ]
    with pytest.raises(ValueError, match="unordered A/B pair"):
        create_vocal_training_snapshot(
            [first, reversed_pair],
            assignments=duplicate_assignments,
            snapshot_id="duplicate-pair",
        )


def test_synthetic_pairwise_ranker_canary_is_deterministic_and_technical_only() -> None:
    fixture = build_synthetic_pairwise_fixture()
    request = build_pairwise_ranker_canary_request()
    first = run_pairwise_ranker_canary(request)
    second = run_pairwise_ranker_canary(request)

    assert fixture == build_synthetic_pairwise_fixture()
    assert fixture["schema"] == SYNTHETIC_PAIRWISE_FIXTURE_SCHEMA
    assert len(fixture["examples"]) == 192
    train_compositions = {
        row["composition_id"] for row in fixture["examples"] if row["split"] == "train"
    }
    heldout_compositions = {
        row["composition_id"]
        for row in fixture["examples"]
        if row["split"] == "heldout"
    }
    assert train_compositions.isdisjoint(heldout_compositions)
    assert first == second
    assert first["schema"] == PAIRWISE_CANARY_RESULT_SCHEMA
    assert first["status"] == "complete_pipeline_canary"
    assert first["metrics"]["clean_heldout_accuracy"] == pytest.approx(0.953125)
    assert first["metrics"]["shuffled_heldout_accuracy"] == pytest.approx(0.484375)
    assert first["metrics"]["maximum_resume_parameter_difference"] == 0.0
    assert (
        first["checkpoint"]["resumed_final_sha256"]
        == first["checkpoint"]["uninterrupted_final_sha256"]
    )
    assert all(first["acceptance"].values())
    assert first["authority"]["technical_completion_only"] is True
    assert first["authority"]["checkpoint_promoted"] is False
    assert first["privacy"]["real_labels_used"] is False


def test_synthetic_canary_rejects_request_and_result_tampering() -> None:
    request = build_pairwise_ranker_canary_request()
    changed_request = deepcopy(request)
    changed_request["training"]["final_step"] = 301
    _rehash(changed_request)
    with pytest.raises(ValueError, match="fixed contract"):
        run_pairwise_ranker_canary(changed_request)

    result = run_pairwise_ranker_canary(request)
    changed_result = deepcopy(result)
    changed_result["authority"]["checkpoint_promoted"] = True
    _rehash(changed_result)
    with pytest.raises(ValueError, match="authority"):
        validate_pairwise_ranker_canary_result(changed_result, request=request)

    forged_metrics = deepcopy(result)
    forged_metrics["metrics"]["clean_heldout_accuracy"] = 0.0
    forged_metrics["metrics"]["shuffled_heldout_accuracy"] = 1.0
    forged_metrics["metrics"]["clean_minus_shuffled_accuracy"] = -1.0
    forged_metrics["arms"][0]["heldout_accuracy"] = 0.0
    forged_metrics["arms"][1]["heldout_accuracy"] = 0.0
    forged_metrics["arms"][2]["heldout_accuracy"] = 1.0
    _rehash(forged_metrics)
    with pytest.raises(ValueError, match="acceptance"):
        validate_pairwise_ranker_canary_result(forged_metrics, request=request)

    coherent_forge = deepcopy(result)
    coherent_forge["metrics"] = {
        "clean_heldout_accuracy": 1.0,
        "shuffled_heldout_accuracy": 0.0,
        "clean_minus_shuffled_accuracy": 1.0,
        "maximum_resume_parameter_difference": 0.0,
    }
    coherent_forge["arms"][0]["heldout_accuracy"] = 1.0
    coherent_forge["arms"][1]["heldout_accuracy"] = 1.0
    coherent_forge["arms"][2]["heldout_accuracy"] = 0.0
    coherent_forge["checkpoint"]["resumed_final_sha256"] = "9" * 64
    coherent_forge["checkpoint"]["uninterrupted_final_sha256"] = "9" * 64
    _rehash(coherent_forge)
    with pytest.raises(ValueError, match="fixed fixture"):
        validate_pairwise_ranker_canary_result(coherent_forge, request=request)

    extra_authority = deepcopy(result)
    extra_authority["training_approved"] = True
    _rehash(extra_authority)
    with pytest.raises(ValueError, match="fields changed"):
        validate_pairwise_ranker_canary_result(extra_authority, request=request)


def _label(
    state: dict[str, Any],
    *,
    phrase_id: str = "phrase-001",
    outcome: str = "left",
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    return create_vocal_pairwise_label(
        state,
        phrase_id=phrase_id,
        left_source_id="take-001",
        right_source_id="take-002",
        outcome=outcome,
        reason_codes=reasons or ["context_fit"],
    )


def _musical_state(*, second_phrase: bool = False) -> dict[str, Any]:
    phrase_id = "phrase-002" if second_phrase else "phrase-001"
    start = 1.1 if second_phrase else 0.0
    phrase = {
        "phrase_id": phrase_id,
        "start_seconds": start,
        "end_seconds": start + 1.0,
        "lyrics": "Known canonical phrase",
    }

    def file_record(path: str, sha: str) -> dict[str, Any]:
        return {"path": path, "bytes": 128, "sha256": sha}

    def take(source_id: str, sha: str) -> dict[str, Any]:
        return {
            "source_id": source_id,
            "source_class": "human_vocal_take",
            "label": f"{source_id}.wav",
            "audio": file_record(f"SOURCES/takes/{source_id}.wav", sha),
            "audio_properties": {
                "format": "WAV",
                "subtype": "PCM_24",
                "sample_rate": 44_100,
                "channels": 1,
                "frames": 220_500,
                "duration_seconds": 5.0,
            },
            "recorded_zero_offset_seconds": 0.0,
            "review_status": "not_reviewed_in_this_state",
        }

    state: dict[str, Any] = {
        "schema": MUSICAL_STATE_SCHEMA,
        "status": "complete_unreviewed_no_selection",
        "state_scope": "audio_native_vocal_foundation",
        "method_natures": ["D", "H"],
        "clock": {
            "origin": "common_recorded_song_zero",
            "bpm": 96.0,
            "tuning_hz": 440.0,
        },
        "authorization": {
            "rights_category": "owned",
            "rights_confirmed": True,
            "common_recorded_zero_confirmed": True,
        },
        "lyrics": {
            "canonical": file_record("LYRICS/lyrics.txt", "1" * 64),
            "authority": "user_supplied_canonical",
            "automatic_rewrite_permitted": False,
        },
        "structure": {
            "phrase_timeline": file_record("TIMELINE/phrases.json", "2" * 64),
            "phrase_timeline_schema": VOCAL_COMP_TIMELINE_SCHEMA,
            "review_status": "reviewed",
            "phrases": [phrase],
        },
        "vocal_performance_state": {
            "schema": VOCAL_PERFORMANCE_STATE_SCHEMA,
            "processing_chain": "dry",
            "reference": None,
            "takes": [take("take-001", "4" * 64), take("take-002", "5" * 64)],
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
        "effects": {
            "source_mutated": False,
            "lyrics_mutated": False,
            "selection_created": False,
            "human_decision_created": False,
            "audio_comp_rendered": False,
            "pitch_correction_applied": False,
            "training_started": False,
            "model_weights_changed": False,
            "remix_rendered": False,
        },
    }
    _rehash(state)
    return state


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
