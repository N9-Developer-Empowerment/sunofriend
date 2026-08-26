from __future__ import annotations

from copy import deepcopy

import pytest

from sunofriend.remix_musicfm_fma import (
    MUSICFM_FMA_ADMISSION_PLAN_SCHEMA,
    MUSICFM_FMA_PROVIDER_ID,
    create_musicfm_fma_admission_plan,
    validate_musicfm_fma_admission_plan,
)
from sunofriend.source_receipt import document_sha256


def _plan() -> dict:
    return create_musicfm_fma_admission_plan(
        plan_id="musicfm-fma-admission-001",
        repository_commit="9" * 40,
    )


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def test_plan_pins_provider_without_checkpoint_access_or_authority() -> None:
    plan = _plan()

    assert plan["schema"] == MUSICFM_FMA_ADMISSION_PLAN_SCHEMA
    assert plan["status"] == "planned_no_checkpoint_access"
    assert plan["provider"]["provider_id"] == MUSICFM_FMA_PROVIDER_ID
    assert plan["provider"]["extractor_frozen"] is True
    assert plan["provider"]["gradient_into_extractor"] is False
    assert plan["planned_assets"]["checkpoint"] == {
        "filename": "pretrained_fma.pt",
        "bytes": 1_316_802_154,
        "sha256": "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96",
        "serialization": "pytorch_pickle_state_dict_wrapper",
        "present_locally": False,
        "opened": False,
    }
    assert plan["proposed_feature_contract"]["feature_rate_hz"] == 25
    assert plan["proposed_feature_contract"]["layer_index"] == 7
    assert plan["proposed_feature_contract"]["feature_dimension"] == 1024
    assert plan["authority"] == {
        "download_authorized": False,
        "dependency_install_authorized": False,
        "model_load_authorized": False,
        "synthetic_inference_authorized": False,
        "private_audio_access_authorized": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_changed": False,
    }
    assert all(value is False for value in plan["effects"].values())
    assert validate_musicfm_fma_admission_plan(plan) == plan


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row["planned_assets"]["checkpoint"].update(bytes=7),
            "evidence or authority",
        ),
        (
            lambda row: row["authority"].update(download_authorized=True),
            "evidence or authority",
        ),
        (
            lambda row: row["effects"].update(model_loaded=True),
            "evidence or authority",
        ),
        (
            lambda row: row["required_runtime_controls"].update(
                network_during_load_and_inference=True
            ),
            "evidence or authority",
        ),
        (
            lambda row: row["provider"].update(gradient_into_extractor=True),
            "evidence or authority",
        ),
    ],
)
def test_plan_rejects_rehashed_false_evidence_or_authority(mutate, message) -> None:
    changed = deepcopy(_plan())
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_musicfm_fma_admission_plan(changed)


def test_plan_rejects_paths_extra_fields_and_noncanonical_identity() -> None:
    with pytest.raises(ValueError, match="path-free"):
        create_musicfm_fma_admission_plan(
            plan_id="../private/model", repository_commit="9" * 40
        )

    changed = deepcopy(_plan())
    changed["private_checkpoint_path"] = "/Users/person/model.pt"
    _rehash(changed)
    with pytest.raises(ValueError, match="fields changed"):
        validate_musicfm_fma_admission_plan(changed)

    changed = deepcopy(_plan())
    changed["planned_assets"]["statistics"]["sha256"] = "0" * 64
    _rehash(changed)
    with pytest.raises(ValueError, match="evidence or authority"):
        validate_musicfm_fma_admission_plan(changed)


def test_plan_records_upstream_fetch_and_pickle_risks() -> None:
    plan = _plan()

    assert (
        plan["planned_assets"]["implicit_upstream_dependency"][
            "automatic_fetch_allowed"
        ]
        is False
    )
    assert plan["required_runtime_controls"]["torch_load_weights_only_required"]
    assert not plan["gates"]["external_conformer_config_pinned"]
    assert plan["gates"]["external_conformer_publication_revision_pinned"]
    assert not plan["gates"]["restricted_weights_only_load_passed"]
    assert plan["next_gate"] == {
        "kind": "explicit_checkpoint_and_runtime_evidence_approval",
        "maximum_checkpoint_bytes": 1_316_802_154,
        "maximum_total_bytes": 1_316_806_674,
        "permits_installation": False,
        "permits_model_load": False,
        "permits_inference": False,
        "permits_private_audio_access": False,
    }
