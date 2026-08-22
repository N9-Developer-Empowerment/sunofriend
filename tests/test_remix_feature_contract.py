from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from remix_learning_contract_fixtures import rehash, remix_fixture
from sunofriend.remix_feature_contract import (
    REMIX_OPERATION_FEATURE_MANIFEST_SCHEMA,
    REMIX_OPERATION_FEATURE_NAMES,
    REMIX_TRAINING_READINESS_SCHEMA,
    assess_remix_training_readiness,
    create_remix_operation_feature_manifest,
    validate_remix_operation_feature_manifest,
    validate_remix_training_readiness,
)
from sunofriend.remix_learning_contract import (
    create_remix_controlled_variant_set,
    create_remix_owner_registry,
    create_remix_pairwise_label,
    create_remix_training_snapshot,
)


def test_transparent_feature_manifest_is_recomputed_from_exact_recipes() -> None:
    snapshot = _snapshot()
    manifest = create_remix_operation_feature_manifest(
        snapshot,
        feature_set_id="transparent-remix-baseline-001",
        repository_commit="7" * 40,
    )

    assert manifest["schema"] == REMIX_OPERATION_FEATURE_MANIFEST_SCHEMA
    assert manifest["status"] == "complete_transparent_metadata_baseline"
    assert manifest["extractor"]["model_used"] is False
    assert manifest["extractor"]["audio_decoded"] is False
    assert len(manifest["rows"]) == 2
    assert manifest["rows"][0]["features"]["names"] == list(
        REMIX_OPERATION_FEATURE_NAMES
    )
    assert manifest["rows"][0]["features"]["shape"] == [6]
    assert manifest["authority"]["training_execution_authorized"] is False
    assert validate_remix_operation_feature_manifest(manifest, snapshot) == manifest

    changed = deepcopy(manifest)
    changed["rows"][0]["features"]["values"][2] = -99.0
    rehash(changed)
    with pytest.raises(ValueError, match="feature rows|recipe"):
        validate_remix_operation_feature_manifest(changed, snapshot)


def test_feature_manifest_rejects_snapshot_or_variant_drift() -> None:
    snapshot = _snapshot()
    manifest = create_remix_operation_feature_manifest(
        snapshot,
        feature_set_id="transparent-remix-baseline-001",
        repository_commit="7" * 40,
    )
    changed_snapshot = deepcopy(snapshot)
    changed_snapshot["snapshot_id"] = "another-snapshot"
    rehash(changed_snapshot)
    with pytest.raises(ValueError, match="snapshot binding"):
        validate_remix_operation_feature_manifest(manifest, changed_snapshot)


def test_readiness_names_exact_real_model_blockers_without_authority() -> None:
    snapshot = _snapshot()
    manifest = create_remix_operation_feature_manifest(
        snapshot,
        feature_set_id="transparent-remix-baseline-001",
        repository_commit="7" * 40,
    )
    readiness = assess_remix_training_readiness(snapshot, manifest)

    assert readiness["schema"] == REMIX_TRAINING_READINESS_SCHEMA
    assert readiness["status"] == "blocked_before_real_model_training"
    assert readiness["ready_for_real_weight_optimisation"] is False
    assert readiness["gates"]["transparent_operation_baseline_available"] is True
    assert readiness["gates"]["frozen_audio_feature_manifest_admitted"] is False
    assert (
        readiness["gates"]["remix_training_request_result_verifier_implemented"] is True
    )
    assert readiness["authority"]["training_execution_authorized"] is False
    assert validate_remix_training_readiness(readiness, snapshot, manifest) == readiness


def _snapshot() -> dict:
    fixture = remix_fixture()
    registry = create_remix_owner_registry(
        registry_id="registry-001",
        entries=[
            {
                "composition_id": "composition-001",
                "group_id": "group-001",
                "musical_state": fixture["state"],
                "identity_state": fixture["identity"],
                "source_control": fixture["control"],
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        ],
    )
    variants = create_remix_controlled_variant_set(
        registry,
        fixture["identity"],
        variant_set_id="variants-001",
        variant_family_id="gain-family-001",
        source_control=fixture["control"],
        variants=[
            {
                "variant_id": "left-001",
                "remix_request": fixture["left_request"],
                "remix_result": fixture["left_result"],
            },
            {
                "variant_id": "right-001",
                "remix_request": fixture["right_request"],
                "remix_result": fixture["right_result"],
            },
        ],
    )
    label = create_remix_pairwise_label(
        registry,
        variants,
        fixture["identity"],
        left_variant_id="left-001",
        right_variant_id="right-001",
        heard_control=True,
        heard_left=True,
        heard_right=True,
        outcome="left",
        left_identity_relationship="preserved",
        right_identity_relationship="partly_preserved",
        reason_codes=["change_more_useful"],
        training_admission="explicit_owner_local_training",
        presentation_seed=20260821,
        reviewed_at="2026-08-21T12:00:00Z",
    )
    return create_remix_training_snapshot(
        labels=[label],
        owner_registries=[registry],
        variant_sets=[variants],
        assignments=[
            {
                "label_document_sha256": label["document_sha256"],
                "composition_id": "composition-001",
                "group_id": "group-001",
                "musical_state_sha256": fixture["state"]["document_sha256"],
                "variant_family_id": "gain-family-001",
                "split": "train",
            }
        ],
        snapshot_id="remix-learning-pilot-001",
    )
