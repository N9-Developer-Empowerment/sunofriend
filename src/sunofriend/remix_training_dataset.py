"""Small facade for preparing a split-safe real remix-training dataset.

The caller chooses one split per owner-confirmed composition.  This module
derives the repeated group, Musical-State and variant-family bindings from the
sealed label and variant-set evidence, then delegates full validation to the
canonical snapshot contract.  It reads no audio and grants no training
authority.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .remix_learning_contract import (
    REMIX_EVIDENCE_GATES,
    create_remix_training_snapshot,
    validate_remix_training_snapshot,
)
from .source_receipt import document_sha256


REMIX_TRAINING_DATASET_PREPARATION_SCHEMA = (
    "sunofriend.remix-training-dataset-preparation.v1"
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SPLITS = frozenset({"train", "validation", "test"})


def prepare_remix_training_dataset(
    *,
    snapshot_id: str,
    labels: Sequence[Mapping[str, Any]],
    owner_registries: Sequence[Mapping[str, Any]],
    variant_sets: Sequence[Mapping[str, Any]],
    composition_splits: Mapping[str, str],
) -> dict[str, Any]:
    """Create one canonical snapshot and an exact no-authority gap report."""

    checked_splits = _composition_splits(composition_splits)
    variants = _variant_lookup(variant_sets)
    assignments = _derive_assignments(labels, variants, checked_splits)
    snapshot = create_remix_training_snapshot(
        labels=labels,
        owner_registries=owner_registries,
        variant_sets=variant_sets,
        assignments=assignments,
        snapshot_id=snapshot_id,
    )
    readiness = _readiness(snapshot)
    document: dict[str, Any] = {
        "schema": REMIX_TRAINING_DATASET_PREPARATION_SCHEMA,
        "status": "prepared_path_free_snapshot_no_training_authority",
        "snapshot": snapshot,
        "readiness": readiness,
        "authority": _zero_authority(),
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_training_dataset_preparation(document)


def validate_remix_training_dataset_preparation(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Revalidate the embedded snapshot and recompute every readiness claim."""

    if not isinstance(value, Mapping):
        raise ValueError("remix training dataset preparation must be an object")
    document = dict(value)
    if set(document) != {
        "schema",
        "status",
        "snapshot",
        "readiness",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    } or document.get("schema") != REMIX_TRAINING_DATASET_PREPARATION_SCHEMA:
        raise ValueError("remix training dataset preparation fields changed")
    if document.get("status") != "prepared_path_free_snapshot_no_training_authority":
        raise ValueError("remix training dataset preparation status changed")
    snapshot = validate_remix_training_snapshot(_mapping(document.get("snapshot")))
    if document.get("snapshot") != snapshot or document.get("readiness") != _readiness(
        snapshot
    ):
        raise ValueError("remix training dataset readiness changed")
    if (
        document.get("authority") != _zero_authority()
        or document.get("effects") != _zero_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError("remix training dataset authority or effects changed")
    unhashed = dict(document)
    supplied_hash = unhashed.pop("document_sha256", None)
    if supplied_hash != document_sha256(unhashed):
        raise ValueError("remix training dataset preparation hash changed")
    return document


def _composition_splits(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        return {}
    result: dict[str, str] = {}
    for raw_composition, raw_split in value.items():
        composition = str(raw_composition)
        split = str(raw_split)
        if not _SAFE_ID.fullmatch(composition):
            raise ValueError("composition split ID is invalid")
        if split not in _SPLITS:
            raise ValueError("composition split must be train, validation or test")
        result[composition] = split
    return result


def _variant_lookup(
    variant_sets: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(variant_sets, Sequence) or isinstance(
        variant_sets, (str, bytes)
    ):
        raise ValueError("variant sets must be a sequence")
    result: dict[str, Mapping[str, Any]] = {}
    for value in variant_sets:
        row = _mapping(value)
        identity = str(row.get("document_sha256"))
        if identity in result:
            raise ValueError("variant sets repeat a document identity")
        result[identity] = row
    return result


def _derive_assignments(
    labels: Sequence[Mapping[str, Any]],
    variants: Mapping[str, Mapping[str, Any]],
    composition_splits: Mapping[str, str],
) -> list[dict[str, Any]]:
    if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)):
        raise ValueError("labels must be a sequence")
    assignments: list[dict[str, Any]] = []
    used_compositions: set[str] = set()
    for value in labels:
        label = _mapping(value)
        binding = _mapping(label.get("binding"))
        variant = variants.get(str(binding.get("variant_set_sha256")))
        if variant is None:
            raise ValueError("label has no supplied exact variant set")
        composition = str(variant.get("composition_id"))
        split = composition_splits.get(composition)
        if split is None:
            raise ValueError(f"composition split is missing for composition {composition}")
        used_compositions.add(composition)
        assignments.append(
            {
                "label_document_sha256": label.get("document_sha256"),
                "composition_id": composition,
                "group_id": variant.get("group_id"),
                "musical_state_sha256": binding.get("musical_state_sha256"),
                "variant_family_id": binding.get("variant_family_id"),
                "split": split,
            }
        )
    unused = sorted(set(composition_splits) - used_compositions)
    if unused:
        raise ValueError(
            "composition split contains unused composition IDs: " + ", ".join(unused)
        )
    return assignments


def _readiness(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    evidence = snapshot["evidence_gate"]
    observed = evidence["observed"]
    shortfalls = {
        name.removeprefix("minimum_"): max(
            0,
            int(minimum) - int(observed[name.removeprefix("minimum_")]),
        )
        for name, minimum in REMIX_EVIDENCE_GATES.items()
    }
    passed = evidence["evidence_gate_passed"] is True
    return {
        "status": (
            "evidence_gate_met_training_still_unauthorized"
            if passed
            else "collecting_owner_labels"
        ),
        "snapshot_sha256": snapshot["document_sha256"],
        "shortfalls": shortfalls,
        "checks": dict(evidence["checks"]),
        "next_gate": (
            "admit_frozen_features_and_request_separate_training_authority"
            if passed
            else "collect_owner_labels"
        ),
        "authority": _zero_authority(),
        "effects": _zero_effects(),
    }


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("remix training dataset evidence must be an object")
    return dict(value)


def _zero_authority() -> dict[str, bool]:
    return {
        "training_execution_authorized": False,
        "private_audio_extraction_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_authorized": False,
    }


def _zero_effects() -> dict[str, bool]:
    return {
        "audio_read": False,
        "audio_rendered": False,
        "training_started": False,
        "model_weights_changed": False,
        "product_state_changed": False,
    }


__all__ = [
    "REMIX_TRAINING_DATASET_PREPARATION_SCHEMA",
    "prepare_remix_training_dataset",
    "validate_remix_training_dataset_preparation",
]
