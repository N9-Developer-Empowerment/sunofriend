from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from remix_learning_contract_fixtures import rehash, remix_fixture
from sunofriend.remix_learning_contract import (
    REMIX_OWNER_REGISTRY_SCHEMA,
    REMIX_PAIRWISE_LABEL_SCHEMA,
    REMIX_VARIANT_SET_SCHEMA,
    create_remix_controlled_variant_set,
    create_remix_owner_registry,
    create_remix_pairwise_label,
    validate_remix_controlled_variant_set,
    validate_remix_owner_registry,
    validate_remix_pairwise_label,
)


def _registry(fixture: dict) -> dict:
    return create_remix_owner_registry(
        registry_id="owner-remix-registry-001",
        entries=[
            {
                "composition_id": "composition-001",
                "group_id": "recording-group-001",
                "musical_state": fixture["state"],
                "identity_state": fixture["identity"],
                "source_control": fixture["control"],
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        ],
    )


def _variants(fixture: dict, registry: dict) -> dict:
    return create_remix_controlled_variant_set(
        registry,
        fixture["identity"],
        variant_set_id="variant-set-001",
        variant_family_id="same-anchor-gain-envelope-001",
        source_control=fixture["control"],
        variants=[
            {
                "variant_id": "delta-3db",
                "remix_request": fixture["left_request"],
                "remix_result": fixture["left_result"],
            },
            {
                "variant_id": "delta-5db",
                "remix_request": fixture["right_request"],
                "remix_result": fixture["right_result"],
            },
        ],
    )


def _label(fixture: dict, registry: dict, variants: dict, **overrides: object) -> dict:
    values = {
        "left_variant_id": "delta-3db",
        "right_variant_id": "delta-5db",
        "heard_control": True,
        "heard_left": True,
        "heard_right": True,
        "outcome": "left",
        "left_identity_relationship": "preserved",
        "right_identity_relationship": "partly_preserved",
        "reason_codes": ["change_more_useful", "identity_better_preserved"],
        "training_admission": "explicit_owner_local_training",
        "presentation_seed": 20260821,
        "reviewed_at": "2026-08-21T12:00:00Z",
    }
    values.update(overrides)
    return create_remix_pairwise_label(
        registry, variants, fixture["identity"], **values
    )


def test_owner_registry_is_immutable_hash_bound_and_path_free() -> None:
    fixture = remix_fixture()
    registry = _registry(fixture)

    assert registry["schema"] == REMIX_OWNER_REGISTRY_SCHEMA
    assert registry["status"] == "complete_owner_confirmed_registry"
    row = registry["entries"][0]
    assert row["composition_id"] == "composition-001"
    assert row["group_id"] == "recording-group-001"
    assert row["musical_state_sha256"] == fixture["state"]["document_sha256"]
    assert row["identity_state_sha256"] == fixture["identity"]["document_sha256"]
    assert row["source_control_audio_sha256"] == fixture["control"]["audio_sha256"]
    assert row["anchor_ids"] == ["hook-001"]
    assert registry["authority"]["owner_confirmed_relationships"] is True
    assert registry["authority"]["automatic_relationship_inference"] is False
    assert registry["privacy"]["cloud_training_approved"] is False
    assert "/Users/" not in str(registry)
    assert (
        validate_remix_owner_registry(
            registry,
            musical_states=[fixture["state"]],
            identity_states=[fixture["identity"]],
        )
        == registry
    )

    changed = deepcopy(registry)
    changed["entries"][0]["composition_id"] = "silently-renamed-composition"
    rehash(changed)
    with pytest.raises(ValueError, match="registry|composition|immutable"):
        validate_remix_owner_registry(
            changed,
            musical_states=[fixture["state"]],
            identity_states=[fixture["identity"]],
        )


def test_registry_rejects_one_group_assigned_to_two_compositions() -> None:
    first = remix_fixture(suffix="001")
    second = remix_fixture(suffix="002")
    entries = []
    for composition_id, fixture in (
        ("composition-001", first),
        ("composition-002", second),
    ):
        entries.append(
            {
                "composition_id": composition_id,
                "group_id": "same-recording-group",
                "musical_state": fixture["state"],
                "identity_state": fixture["identity"],
                "source_control": fixture["control"],
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        )
    with pytest.raises(ValueError, match="group.*one composition"):
        create_remix_owner_registry(registry_id="bad-registry", entries=entries)


def test_variant_set_binds_control_identity_requests_results_and_one_variable() -> None:
    fixture = remix_fixture()
    registry = _registry(fixture)
    variant_set = _variants(fixture, registry)

    assert variant_set["schema"] == REMIX_VARIANT_SET_SCHEMA
    assert variant_set["status"] == "complete_deterministic_controlled_variants"
    assert variant_set["source_control"] == fixture["control"]
    assert (
        variant_set["identity_state_sha256"] == fixture["identity"]["document_sha256"]
    )
    assert variant_set["variant_family"]["variable"] == "gain_delta_envelope_only"
    assert variant_set["variant_family"]["all_other_factors_fixed"] is True
    assert [row["variant_id"] for row in variant_set["variants"]] == [
        "delta-3db",
        "delta-5db",
    ]
    assert variant_set["variants"][0]["remix_request"] == fixture["left_request"]
    assert variant_set["variants"][0]["remix_result"] == fixture["left_result"]
    assert variant_set["authority"]["automatic_preference"] is False
    assert variant_set["authority"]["training_label_created"] is False
    assert (
        validate_remix_controlled_variant_set(
            variant_set, registry, fixture["identity"]
        )
        == variant_set
    )

    drift = deepcopy(variant_set)
    drift["variants"][0]["remix_result"]["output"]["audio_sha256"] = "f" * 64
    rehash(drift["variants"][0]["remix_result"])
    rehash(drift)
    with pytest.raises(ValueError, match="result|variant|evidence|hash"):
        validate_remix_controlled_variant_set(drift, registry, fixture["identity"])


@pytest.mark.parametrize("missing", ["heard_control", "heard_left", "heard_right"])
def test_pairwise_label_requires_hearing_control_left_and_right(missing: str) -> None:
    fixture = remix_fixture()
    registry = _registry(fixture)
    variants = _variants(fixture, registry)
    with pytest.raises(ValueError, match="heard|control|left|right"):
        _label(fixture, registry, variants, **{missing: False})


def test_pairwise_label_binds_full_evidence_and_explicit_training_admission() -> None:
    fixture = remix_fixture()
    registry = _registry(fixture)
    variants = _variants(fixture, registry)
    label = _label(fixture, registry, variants)

    assert label["schema"] == REMIX_PAIRWISE_LABEL_SCHEMA
    assert label["status"] == "complete_explicit_owner_pairwise_label"
    assert label["binding"] == {
        "owner_registry_sha256": registry["document_sha256"],
        "musical_state_sha256": fixture["state"]["document_sha256"],
        "identity_state_sha256": fixture["identity"]["document_sha256"],
        "variant_set_sha256": variants["document_sha256"],
        "variant_family_id": "same-anchor-gain-envelope-001",
    }
    assert label["control"]["audio_sha256"] == fixture["control"]["audio_sha256"]
    assert label["left"]["remix_request"] == fixture["left_request"]
    assert label["left"]["remix_result"] == fixture["left_result"]
    assert label["right"]["remix_request"] == fixture["right_request"]
    assert label["right"]["remix_result"] == fixture["right_result"]
    assert label["listening"] == {
        "heard_control": True,
        "heard_left": True,
        "heard_right": True,
        "playback_implies_label": False,
    }
    assert label["training"] == {
        "explicitly_admitted": True,
        "admission_scope": "owner_local_training",
        "training_eligible": False,
    }
    assert label["authority"]["automatic_preference"] is False
    assert label["authority"]["selected_for_product"] is False
    assert (
        validate_remix_pairwise_label(label, registry, variants, fixture["identity"])
        == label
    )

    with pytest.raises(ValueError, match="admission|training"):
        _label(fixture, registry, variants, training_admission=None)


def test_pairwise_label_revalidates_embedded_request_and_result_evidence() -> None:
    fixture = remix_fixture()
    registry = _registry(fixture)
    variants = _variants(fixture, registry)
    label = _label(fixture, registry, variants)

    changed = deepcopy(label)
    changed["left"]["remix_request"]["operations"][0]["points"][1]["delta_db"] = -1.0
    rehash(changed["left"]["remix_request"])
    rehash(changed)
    with pytest.raises(ValueError, match="request|variant|evidence"):
        validate_remix_pairwise_label(changed, registry, variants, fixture["identity"])

    changed_control = deepcopy(label)
    changed_control["control"]["audio_sha256"] = "9" * 64
    rehash(changed_control)
    with pytest.raises(ValueError, match="control|evidence"):
        validate_remix_pairwise_label(
            changed_control, registry, variants, fixture["identity"]
        )
