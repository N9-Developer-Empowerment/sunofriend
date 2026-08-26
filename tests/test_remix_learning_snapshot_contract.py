from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from remix_learning_contract_fixtures import rehash, remix_fixture
from sunofriend.remix_learning_contract import (
    REMIX_EVIDENCE_GATES,
    REMIX_TRAINING_SNAPSHOT_SCHEMA,
    create_remix_controlled_variant_set,
    create_remix_owner_registry,
    create_remix_pairwise_label,
    create_remix_training_snapshot,
    validate_remix_training_snapshot,
)


def _evidence(
    suffix: str = "001",
    *,
    composition_id: str | None = None,
    group_id: str | None = None,
    family_id: str | None = None,
    fixture: dict | None = None,
    middle_db: float = -3.0,
) -> tuple[dict, dict, dict, dict]:
    fixture = fixture or remix_fixture(suffix=suffix, middle_db=middle_db)
    composition_id = composition_id or f"composition-{suffix}"
    group_id = group_id or f"group-{suffix}"
    family_id = family_id or f"gain-family-{suffix}"
    registry = create_remix_owner_registry(
        registry_id=f"registry-{suffix}",
        entries=[
            {
                "composition_id": composition_id,
                "group_id": group_id,
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
        variant_set_id=f"variants-{suffix}",
        variant_family_id=family_id,
        source_control=fixture["control"],
        variants=[
            {
                "variant_id": f"left-{suffix}",
                "remix_request": fixture["left_request"],
                "remix_result": fixture["left_result"],
            },
            {
                "variant_id": f"right-{suffix}",
                "remix_request": fixture["right_request"],
                "remix_result": fixture["right_result"],
            },
        ],
    )
    label = create_remix_pairwise_label(
        registry,
        variants,
        fixture["identity"],
        left_variant_id=f"left-{suffix}",
        right_variant_id=f"right-{suffix}",
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
    return fixture, registry, variants, label


def test_snapshot_embeds_full_labels_registries_and_variant_manifests() -> None:
    fixture, registry, variants, label = _evidence()
    snapshot = create_remix_training_snapshot(
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

    assert snapshot["schema"] == REMIX_TRAINING_SNAPSHOT_SCHEMA
    assert snapshot["status"] == "training_ineligible"
    assert snapshot["labels"] == [label]
    assert snapshot["owner_registries"] == [registry]
    assert snapshot["variant_sets"] == [variants]
    assert snapshot["evidence_gate"]["observed"]["explicit_labels"] == 1
    assert snapshot["evidence_gate"]["evidence_gate_passed"] is False
    assert snapshot["evidence_gate"]["thresholds"] == REMIX_EVIDENCE_GATES
    assert snapshot["authority"]["training_execution_authorized"] is False
    assert snapshot["authority"]["product_admitted"] is False
    assert "/Users/" not in str(snapshot)
    assert validate_remix_training_snapshot(snapshot) == snapshot

    forged = deepcopy(snapshot)
    forged["authority"]["training_execution_authorized"] = True
    rehash(forged)
    with pytest.raises(ValueError, match="authority|ineligible"):
        validate_remix_training_snapshot(forged)


def test_snapshot_revalidates_full_embedded_evidence_not_only_hash_projection() -> None:
    fixture, registry, variants, label = _evidence()
    snapshot = create_remix_training_snapshot(
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
        snapshot_id="full-evidence-tamper-test",
    )
    changed = deepcopy(snapshot)
    changed["labels"][0]["left"]["remix_result"]["output"]["audio_sha256"] = "9" * 64
    rehash(changed["labels"][0]["left"]["remix_result"])
    rehash(changed["labels"][0])
    rehash(changed)
    with pytest.raises(ValueError, match="label|result|variant|evidence"):
        validate_remix_training_snapshot(changed)


@pytest.mark.parametrize(
    "changed_field",
    ["composition_id", "group_id", "musical_state_sha256", "variant_family_id"],
)
def test_snapshot_rejects_every_split_leakage_dimension(changed_field: str) -> None:
    if changed_field == "composition_id":
        first = _evidence("001", composition_id="composition-shared")
        second = _evidence("002", composition_id="composition-shared")
    elif changed_field == "group_id":
        first = _evidence("001", group_id="group-shared")
        second = _evidence("002", group_id="group-shared")
    elif changed_field == "musical_state_sha256":
        shared_fixture = remix_fixture(suffix="003", middle_db=-3.0)
        first = _evidence("003a", fixture=shared_fixture, family_id="family-003a")
        second_fixture = remix_fixture(suffix="003", middle_db=-4.0)
        second = _evidence("003b", fixture=second_fixture, family_id="family-003b")
    else:
        first = _evidence("001", family_id="family-shared")
        second = _evidence("002", family_id="family-shared")
    assignment_a = {
        "label_document_sha256": first[3]["document_sha256"],
        "composition_id": first[1]["entries"][0]["composition_id"],
        "group_id": first[1]["entries"][0]["group_id"],
        "musical_state_sha256": first[0]["state"]["document_sha256"],
        "variant_family_id": first[2]["variant_family"]["variant_family_id"],
        "split": "train",
    }
    assignment_b = {
        "label_document_sha256": second[3]["document_sha256"],
        "composition_id": second[1]["entries"][0]["composition_id"],
        "group_id": second[1]["entries"][0]["group_id"],
        "musical_state_sha256": second[0]["state"]["document_sha256"],
        "variant_family_id": second[2]["variant_family"]["variant_family_id"],
        "split": "test",
    }
    with pytest.raises(
        ValueError,
        match=f"{changed_field.replace('_id', '').replace('_sha256', '')}.*disjoint|split",
    ):
        create_remix_training_snapshot(
            labels=[first[3], second[3]],
            owner_registries=[first[1], second[1]],
            variant_sets=[first[2], second[2]],
            assignments=[assignment_a, assignment_b],
            snapshot_id=f"leak-{changed_field}",
        )


def test_snapshot_rejects_reversed_duplicate_pair() -> None:
    fixture, registry, variants, label = _evidence()
    reversed_label = create_remix_pairwise_label(
        registry,
        variants,
        fixture["identity"],
        left_variant_id="right-001",
        right_variant_id="left-001",
        heard_control=True,
        heard_left=True,
        heard_right=True,
        outcome="right",
        left_identity_relationship="partly_preserved",
        right_identity_relationship="preserved",
        reason_codes=["change_more_useful"],
        training_admission="explicit_owner_local_training",
        presentation_seed=20260822,
        reviewed_at="2026-08-21T12:01:00Z",
    )
    assignments = [
        {
            "label_document_sha256": row["document_sha256"],
            "composition_id": "composition-001",
            "group_id": "group-001",
            "musical_state_sha256": fixture["state"]["document_sha256"],
            "variant_family_id": "gain-family-001",
            "split": "train",
        }
        for row in (label, reversed_label)
    ]
    with pytest.raises(ValueError, match="unordered|duplicate.*pair"):
        create_remix_training_snapshot(
            labels=[label, reversed_label],
            owner_registries=[registry],
            variant_sets=[variants],
            assignments=assignments,
            snapshot_id="duplicate-unordered-pair",
        )
