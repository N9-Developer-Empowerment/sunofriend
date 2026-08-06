from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sunofriend.listening_master import (
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_SCHEMA,
)
from sunofriend.product_contract import (
    PRODUCT_CONTRACT,
    PRODUCT_CONTRACT_SCHEMA,
    PRODUCT_OUTPUT_STATUS_SCHEMA,
    build_product_output_status,
    product_contract_document,
)
from sunofriend.workbench_balanced_contract import BALANCED_MIX_CONTRACT


def _selection() -> dict:
    return {
        "selection_manifest_sha256": "a" * 64,
        "selected_midi": [{"selection_index": 1}, {"selection_index": 2}],
    }


def _interpretation() -> dict:
    return {
        "schema": BALANCED_MIX_CONTRACT.arrangement_schema,
        "policy": BALANCED_MIX_CONTRACT.policy,
        "selection_manifest_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "preview": {"sha256": "c" * 64},
        "mastered": False,
    }


def _listening_master() -> dict:
    return {
        "receipt_schema": LISTENING_MASTER_SCHEMA,
        "policy": LISTENING_MASTER_POLICY,
        "selection_manifest_sha256": "a" * 64,
        "balanced_arrangement_manifest_sha256": "b" * 64,
        "balanced_preview_sha256": "c" * 64,
        "mastered": True,
        "release_master": False,
    }


def test_contract_has_exactly_two_first_class_outputs_and_fresh_documents() -> None:
    document = product_contract_document()

    assert document["schema"] == PRODUCT_CONTRACT_SCHEMA
    assert [row["output_id"] for row in document["required_outputs"]] == [
        "evaluated_editable_midi",
        "midi_derived_song_interpretation_wav",
    ]
    assert document["required_outputs"][0]["label"] == (
        "Editable MIDI arrangement"
    )
    assert all(row["required"] for row in document["required_outputs"])
    assert all(
        row["source_audio_mixed"] is False
        for row in document["required_outputs"]
    )
    assert document["source_evidence"]["mixed_into_song_interpretation_wav"] is False
    assert set(document["decision_boundary"].values()) == {False}

    document["required_outputs"][0]["label"] = "mutated"
    assert product_contract_document()["required_outputs"][0]["label"] != "mutated"


def test_contract_separates_simple_automatic_work_from_studio_review() -> None:
    modes = product_contract_document()["modes"]
    simple = modes["simple"]
    studio = modes["studio"]

    assert simple["default_human_entry"] is True
    assert simple["review_status"] == "not_reviewed"
    assert simple["quality_status"] == "review_recommended"
    assert simple["human_decision_events"] == 0
    assert simple["feedback_recorded"] is False
    assert simple["automatic_starter_instruments"] is True
    assert simple["automatic_factory_patch_selection"] is False
    assert simple["source_midi_mutated_for_sound_handoff"] is False
    assert simple["may_claim_human_review"] is False
    assert simple["result_schema"] == "sunofriend.simple-result.v1"

    assert studio["default_human_entry"] is False
    assert studio["review_status"] == "explicit"
    assert studio["human_decision_events"] == "explicit_only"
    assert studio["feedback_recorded"] == "explicit_only"
    assert studio["may_claim_human_review"] is True


def test_contract_maps_to_existing_accepted_audio_controls() -> None:
    document = product_contract_document()
    interpretation = document["required_outputs"][1]
    listening_master = document["optional_outputs"][0]

    assert interpretation["artifact_schema"] == (
        BALANCED_MIX_CONTRACT.arrangement_schema
    )
    assert interpretation["policy"] == BALANCED_MIX_CONTRACT.policy
    assert listening_master["artifact_schema"] == LISTENING_MASTER_SCHEMA
    assert listening_master["policy"] == LISTENING_MASTER_POLICY

    with pytest.raises(FrozenInstanceError):
        PRODUCT_CONTRACT.version = "changed"


def test_output_status_requires_a_matching_verified_interpretation() -> None:
    waiting = build_product_output_status(
        _selection(),
        None,
        full_mix_review_complete=True,
    )
    stale = build_product_output_status(
        _selection(),
        {**_interpretation(), "selection_manifest_sha256": "b" * 64},
        full_mix_review_complete=True,
    )
    complete = build_product_output_status(
        _selection(),
        _interpretation(),
        full_mix_review_complete=True,
    )

    assert waiting["schema"] == PRODUCT_OUTPUT_STATUS_SCHEMA
    assert waiting["mode"] == "studio"
    assert waiting["review_status"] == "reviewed"
    assert waiting["required_outputs"]["evaluated_editable_midi"]["ready"] is True
    assert (
        waiting["required_outputs"]["midi_derived_song_interpretation_wav"][
            "ready"
        ]
        is False
    )
    assert stale["complete"] is False
    assert complete["complete"] is True
    assert (
        complete["required_outputs"]["midi_derived_song_interpretation_wav"][
            "source_audio_mixed"
        ]
        is False
    )
    assert set(complete["effects"].values()) == {False}


def test_no_selected_midi_means_neither_required_output_is_ready() -> None:
    status = build_product_output_status(
        {"selection_manifest_sha256": "a" * 64, "selected_midi": []},
        _interpretation(),
        full_mix_review_complete=True,
    )

    assert status["complete"] is False
    assert status["review_status"] == "review_incomplete"
    assert all(
        row["ready"] is False for row in status["required_outputs"].values()
    )


def test_product_is_not_complete_until_selected_midi_has_full_mix_review() -> None:
    status = build_product_output_status(
        _selection(),
        _interpretation(),
        full_mix_review_complete=False,
    )

    assert (
        status["required_outputs"]["evaluated_editable_midi"]["ready"] is True
    )
    assert (
        status["required_outputs"]["evaluated_editable_midi"][
            "full_mix_review_complete"
        ]
        is False
    )
    assert (
        status["required_outputs"]["midi_derived_song_interpretation_wav"][
            "ready"
        ]
        is True
    )
    assert status["complete"] is False


def test_optional_listening_master_readiness_requires_exact_current_control() -> None:
    ready = build_product_output_status(
        _selection(),
        _interpretation(),
        _listening_master(),
        full_mix_review_complete=True,
    )
    stale_selection = build_product_output_status(
        _selection(),
        _interpretation(),
        {
            **_listening_master(),
            "selection_manifest_sha256": "d" * 64,
        },
        full_mix_review_complete=True,
    )
    stale_control = build_product_output_status(
        _selection(),
        _interpretation(),
        {
            **_listening_master(),
            "balanced_arrangement_manifest_sha256": "d" * 64,
        },
        full_mix_review_complete=True,
    )

    optional = ready["optional_outputs"]["comparative_listening_master"]
    assert ready["complete"] is True
    assert optional["available_through_cli"] is True
    assert optional["available_through_workbench"] is True
    assert optional["ready"] is True
    assert optional["mastered"] is True
    assert optional["release_master"] is False
    assert optional["automatic_promotion"] is False
    assert (
        stale_selection["optional_outputs"]["comparative_listening_master"][
            "ready"
        ]
        is False
    )
    assert (
        stale_control["optional_outputs"]["comparative_listening_master"][
            "ready"
        ]
        is False
    )
    assert stale_selection["complete"] is True
    assert stale_control["complete"] is True
