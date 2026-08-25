"""Evidence contracts for an owner-specific controlled-remix learner.

These contracts deliberately stop before model execution.  They turn explicit
owner A/B judgements over deterministic remix variants into immutable,
path-free evidence while preserving the existing renderer's no-training and
no-selection authority boundaries.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

from .musical_state import validate_musical_state
from .remix_identity import (
    REMIX_IDENTITY_STATE_SCHEMA,
    validate_remix_identity_state,
    validate_remix_request,
    validate_remix_result,
)
from .source_receipt import document_sha256


REMIX_OWNER_REGISTRY_SCHEMA = "sunofriend.remix-owner-anchor-registry.v0"
REMIX_VARIANT_SET_SCHEMA = "sunofriend.remix-controlled-variant-set.v0"
REMIX_PAIRWISE_LABEL_SCHEMA = "sunofriend.remix-pairwise-preference-label.v0"
REMIX_TRAINING_SNAPSHOT_SCHEMA = "sunofriend.remix-pairwise-training-snapshot.v0"

REMIX_EVIDENCE_GATES = {
    "minimum_explicit_labels": 200,
    "minimum_directional_labels": 120,
    "minimum_left_directional_labels": 30,
    "minimum_right_directional_labels": 30,
    "minimum_compositions": 6,
    "minimum_groups": 12,
    "minimum_train_compositions": 4,
    "minimum_validation_compositions": 1,
    "minimum_test_compositions": 1,
}

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OUTCOMES = frozenset({"left", "right", "equivalent", "neither", "cannot_tell"})
_IDENTITY = frozenset({"preserved", "partly_preserved", "lost", "cannot_tell"})
_REASONS = frozenset(
    {
        "change_more_useful",
        "identity_better_preserved",
        "separation_artifact",
        "change_inaudible",
        "both_unusable",
        "unable_to_compare",
        "energy_shape",
        "groove_fit",
        "arrangement_fit",
        "other",
    }
)
_SPLITS = frozenset({"train", "validation", "test"})


def create_remix_owner_registry(
    *, registry_id: str, entries: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Bind owner-confirmed composition/group relationships to exact evidence."""

    _safe_id(registry_id, "registry_id")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ValueError("owner registry entries must be a sequence")
    rows: list[dict[str, Any]] = []
    group_compositions: dict[str, set[str]] = defaultdict(set)
    for raw in entries:
        item = dict(_mapping(raw, "owner registry entry"))
        if set(item) != {
            "composition_id",
            "group_id",
            "musical_state",
            "identity_state",
            "source_control",
            "rights_scope",
            "cloud_training_approved",
        }:
            raise ValueError("owner registry entry fields changed")
        composition_id = _safe_id(item["composition_id"], "composition_id")
        group_id = _safe_id(item["group_id"], "group_id")
        state = validate_musical_state(item["musical_state"])
        identity = validate_remix_identity_state(item["identity_state"], state)
        control = _audio_record(item["source_control"], "source control")
        if item["rights_scope"] != "owner_local_training":
            raise ValueError(
                "owner registry currently permits owner-local training only"
            )
        if item["cloud_training_approved"] is not False:
            raise ValueError("cloud training requires a separate future authorization")
        group_compositions[group_id].add(composition_id)
        relationship = {
            "composition_id": composition_id,
            "group_id": group_id,
            "musical_state_sha256": state["document_sha256"],
            "identity_state_sha256": identity["document_sha256"],
            "source_control_audio_sha256": control["audio_sha256"],
        }
        rows.append(
            {
                **relationship,
                "relationship_sha256": document_sha256(relationship),
                "source_control_audio_bytes": control["audio_bytes"],
                "source_control_geometry": control["geometry"],
                "anchor_ids": sorted(
                    row["anchor_id"] for row in identity["owner_anchors"]
                ),
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        )
    if not rows:
        raise ValueError("owner registry requires at least one entry")
    if any(len(values) != 1 for values in group_compositions.values()):
        raise ValueError("each group must belong to one composition")
    if len(
        {(row["musical_state_sha256"], row["identity_state_sha256"]) for row in rows}
    ) != len(rows):
        raise ValueError("owner registry repeats an exact evidence relationship")
    document: dict[str, Any] = {
        "schema": REMIX_OWNER_REGISTRY_SCHEMA,
        "status": "complete_owner_confirmed_registry",
        "registry_id": str(registry_id),
        "method_natures": ["D", "H"],
        "entries": sorted(
            rows, key=lambda row: (row["composition_id"], row["group_id"])
        ),
        "authority": {
            "owner_confirmed_relationships": True,
            "automatic_relationship_inference": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        },
        "privacy": {
            "local_training_approved": True,
            "cloud_training_approved": False,
            "paths_embedded": False,
        },
        "effects": {
            "sources_mutated": False,
            "remix_rendered": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return _validate_registry_structure(document)


def validate_remix_owner_registry(
    registry: Mapping[str, Any],
    *,
    musical_states: Sequence[Mapping[str, Any]],
    identity_states: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    document = _validate_registry_structure(registry)
    states = {
        row["document_sha256"]: row
        for row in map(validate_musical_state, musical_states)
    }
    identities: dict[str, dict[str, Any]] = {}
    for value in identity_states:
        binding = _mapping(value.get("binding"), "identity binding")
        state = states.get(binding.get("musical_state_sha256"))
        if state is None:
            raise ValueError("registry identity state has no supplied musical state")
        checked = validate_remix_identity_state(value, state)
        identities[checked["document_sha256"]] = checked
    for row in document["entries"]:
        state = states.get(row["musical_state_sha256"])
        identity = identities.get(row["identity_state_sha256"])
        if state is None or identity is None:
            raise ValueError("registry entry does not bind supplied immutable evidence")
        if identity["binding"]["musical_state_sha256"] != state["document_sha256"]:
            raise ValueError("registry identity and musical-state relationship changed")
        if row["anchor_ids"] != sorted(
            item["anchor_id"] for item in identity["owner_anchors"]
        ):
            raise ValueError("registry owner anchor roster changed")
    return document


def create_remix_controlled_variant_set(
    registry: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    variant_set_id: str,
    variant_family_id: str,
    source_control: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    owner_registry = _validate_registry_structure(registry)
    _safe_id(variant_set_id, "variant_set_id")
    _safe_id(variant_family_id, "variant_family_id")
    identity = _validate_identity_structure(identity_state)
    control = _audio_record(source_control, "source control")
    registry_row = _registry_row(owner_registry, identity, control)
    rows = _variant_rows(variants, identity)
    document: dict[str, Any] = {
        "schema": REMIX_VARIANT_SET_SCHEMA,
        "status": "complete_deterministic_controlled_variants",
        "variant_set_id": str(variant_set_id),
        "registry_sha256": owner_registry["document_sha256"],
        "composition_id": registry_row["composition_id"],
        "group_id": registry_row["group_id"],
        "musical_state_sha256": identity["binding"]["musical_state_sha256"],
        "identity_state_sha256": identity["document_sha256"],
        "identity_state": identity,
        "source_control": control,
        "variant_family": {
            "variant_family_id": str(variant_family_id),
            "variable": "gain_delta_envelope_only",
            "all_other_factors_fixed": True,
        },
        "variants": rows,
        "method_natures": ["D"],
        "authority": {
            "automatic_preference": False,
            "training_label_created": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        },
        "effects": {
            "source_mutated": False,
            "variant_audio_rendered_by_this_contract": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_controlled_variant_set(document, owner_registry, identity)


def validate_remix_controlled_variant_set(
    variant_set: Mapping[str, Any],
    registry: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    owner_registry = _validate_registry_structure(registry)
    identity = _validate_identity_structure(identity_state)
    document = _verified_document(variant_set, REMIX_VARIANT_SET_SCHEMA, "variant set")
    _validate_variant_set_document(document)
    _validate_variant_set_binding(document, owner_registry, identity)
    _validate_variant_set_family(document, identity)
    _validate_variant_set_authority(document)
    _reject_private_fields_and_paths(document)
    return document


def _validate_variant_set_document(document: Mapping[str, Any]) -> None:
    """Own the exact controlled-variant top-level schema and status."""

    expected_keys = {
        "schema",
        "status",
        "variant_set_id",
        "registry_sha256",
        "composition_id",
        "group_id",
        "musical_state_sha256",
        "identity_state_sha256",
        "identity_state",
        "source_control",
        "variant_family",
        "variants",
        "method_natures",
        "authority",
        "effects",
        "document_sha256",
    }
    if (
        set(document) != expected_keys
        or document.get("status") != "complete_deterministic_controlled_variants"
    ):
        raise ValueError("controlled variant-set fields or status changed")
    _safe_id(document.get("variant_set_id"), "variant_set_id")


def _validate_variant_set_binding(
    document: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> None:
    """Bind the set to owner registry, state identity and source control."""

    if document.get("registry_sha256") != owner_registry["document_sha256"]:
        raise ValueError("variant set registry evidence changed")
    if (
        document.get("identity_state_sha256") != identity["document_sha256"]
        or document.get("identity_state") != identity
    ):
        raise ValueError("variant set identity evidence changed")
    control = _audio_record(document.get("source_control"), "source control")
    registry_row = _registry_row(owner_registry, identity, control)
    if any(
        document.get(key) != registry_row[key] for key in ("composition_id", "group_id")
    ):
        raise ValueError("variant set registry relationship changed")
    if (
        document.get("musical_state_sha256")
        != identity["binding"]["musical_state_sha256"]
    ):
        raise ValueError("variant set musical-state evidence changed")


def _validate_variant_set_family(
    document: Mapping[str, Any], identity: Mapping[str, Any]
) -> None:
    """Validate the one-variable family and its request/result evidence rows."""

    family = _mapping(document.get("variant_family"), "variant family")
    if set(family) != {"variant_family_id", "variable", "all_other_factors_fixed"}:
        raise ValueError("variant family fields changed")
    _safe_id(family.get("variant_family_id"), "variant_family_id")
    if (
        family.get("variable") != "gain_delta_envelope_only"
        or family.get("all_other_factors_fixed") is not True
    ):
        raise ValueError("variant family must isolate one deterministic variable")
    rows = _variant_rows(document.get("variants", []), identity)
    if rows != document.get("variants"):
        raise ValueError("variant request/result evidence changed")


def _validate_variant_set_authority(document: Mapping[str, Any]) -> None:
    """Keep selection, training and product authority absent."""

    if document.get("method_natures") != ["D"] or document.get("authority") != {
        "automatic_preference": False,
        "training_label_created": False,
        "training_execution_authorized": False,
        "product_selection_authorized": False,
    }:
        raise ValueError("variant set authority changed")
    if document.get("effects") != {
        "source_mutated": False,
        "variant_audio_rendered_by_this_contract": False,
        "training_started": False,
        "model_weights_changed": False,
    }:
        raise ValueError("variant set effects changed")


def create_remix_pairwise_label(
    registry: Mapping[str, Any],
    variant_set: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    left_variant_id: str,
    right_variant_id: str,
    heard_control: bool,
    heard_left: bool,
    heard_right: bool,
    outcome: str,
    left_identity_relationship: str,
    right_identity_relationship: str,
    reason_codes: Sequence[str],
    training_admission: str | None,
    presentation_seed: int,
    reviewed_at: str | None,
) -> dict[str, Any]:
    owner_registry = _validate_registry_structure(registry)
    identity = _validate_identity_structure(identity_state)
    variants = validate_remix_controlled_variant_set(
        variant_set, owner_registry, identity
    )
    left = _variant_side(variants, left_variant_id)
    right = _variant_side(variants, right_variant_id)
    if (
        left_variant_id == right_variant_id
        or left["remix_result"]["output"]["audio_sha256"]
        == right["remix_result"]["output"]["audio_sha256"]
    ):
        raise ValueError("pairwise label requires two distinct variants")
    if not all(value is True for value in (heard_control, heard_left, heard_right)):
        raise ValueError("pairwise label requires heard control, left and right")
    _pairwise_values(
        outcome, left_identity_relationship, right_identity_relationship, reason_codes
    )
    if training_admission != "explicit_owner_local_training":
        raise ValueError("pairwise label requires explicit local-training admission")
    if isinstance(presentation_seed, bool) or not isinstance(presentation_seed, int):
        raise ValueError("presentation_seed must be an integer")
    if reviewed_at is not None and not str(reviewed_at).strip():
        raise ValueError("reviewed_at must be non-empty text or null")
    document: dict[str, Any] = {
        "schema": REMIX_PAIRWISE_LABEL_SCHEMA,
        "status": "complete_explicit_owner_pairwise_label",
        "method_natures": ["D", "H"],
        "binding": {
            "owner_registry_sha256": owner_registry["document_sha256"],
            "musical_state_sha256": variants["musical_state_sha256"],
            "identity_state_sha256": identity["document_sha256"],
            "variant_set_sha256": variants["document_sha256"],
            "variant_family_id": variants["variant_family"]["variant_family_id"],
        },
        "control": variants["source_control"],
        "left": left,
        "right": right,
        "listening": {
            "heard_control": True,
            "heard_left": True,
            "heard_right": True,
            "playback_implies_label": False,
        },
        "outcome": str(outcome),
        "identity_relationships": {
            "left": str(left_identity_relationship),
            "right": str(right_identity_relationship),
        },
        "reason_codes": list(reason_codes),
        "presentation": {"seed": presentation_seed, "reviewed_at": reviewed_at},
        "training": {
            "explicitly_admitted": True,
            "admission_scope": "owner_local_training",
            "training_eligible": False,
        },
        "authority": {
            "automatic_preference": False,
            "selected_for_product": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
        },
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_pairwise_label(document, owner_registry, variants, identity)


def validate_remix_pairwise_label(
    label: Mapping[str, Any],
    registry: Mapping[str, Any],
    variant_set: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    owner_registry = _validate_registry_structure(registry)
    identity = _validate_identity_structure(identity_state)
    variants = validate_remix_controlled_variant_set(
        variant_set, owner_registry, identity
    )
    document = _verified_document(label, REMIX_PAIRWISE_LABEL_SCHEMA, "pairwise label")
    expected_keys = {
        "schema",
        "status",
        "method_natures",
        "binding",
        "control",
        "left",
        "right",
        "listening",
        "outcome",
        "identity_relationships",
        "reason_codes",
        "presentation",
        "training",
        "authority",
        "network_used",
        "document_sha256",
    }
    if (
        set(document) != expected_keys
        or document.get("status") != "complete_explicit_owner_pairwise_label"
    ):
        raise ValueError("pairwise label fields or status changed")
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError("pairwise label method nature changed")
    expected_binding = {
        "owner_registry_sha256": owner_registry["document_sha256"],
        "musical_state_sha256": variants["musical_state_sha256"],
        "identity_state_sha256": identity["document_sha256"],
        "variant_set_sha256": variants["document_sha256"],
        "variant_family_id": variants["variant_family"]["variant_family_id"],
    }
    if (
        document.get("binding") != expected_binding
        or document.get("control") != variants["source_control"]
    ):
        raise ValueError("pairwise label control or evidence binding changed")
    left_id = _mapping(document.get("left"), "left variant").get("variant_id")
    right_id = _mapping(document.get("right"), "right variant").get("variant_id")
    left = _variant_side(variants, left_id)
    right = _variant_side(variants, right_id)
    if (
        document.get("left") != left
        or document.get("right") != right
        or left_id == right_id
    ):
        raise ValueError("pairwise label variant request/result evidence changed")
    if document.get("listening") != {
        "heard_control": True,
        "heard_left": True,
        "heard_right": True,
        "playback_implies_label": False,
    }:
        raise ValueError(
            "pairwise label requires explicit heard control, left and right"
        )
    identities = _mapping(
        document.get("identity_relationships"), "identity relationships"
    )
    _pairwise_values(
        document.get("outcome"),
        identities.get("left"),
        identities.get("right"),
        document.get("reason_codes", []),
    )
    presentation = _mapping(document.get("presentation"), "presentation")
    if (
        set(presentation) != {"seed", "reviewed_at"}
        or isinstance(presentation.get("seed"), bool)
        or not isinstance(presentation.get("seed"), int)
    ):
        raise ValueError("pairwise presentation evidence changed")
    if (
        presentation.get("reviewed_at") is not None
        and not str(presentation["reviewed_at"]).strip()
    ):
        raise ValueError("reviewed_at must be non-empty text or null")
    if document.get("training") != {
        "explicitly_admitted": True,
        "admission_scope": "owner_local_training",
        "training_eligible": False,
    }:
        raise ValueError("pairwise training admission or eligibility changed")
    if (
        document.get("authority")
        != {
            "automatic_preference": False,
            "selected_for_product": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
        }
        or document.get("network_used") is not False
    ):
        raise ValueError("pairwise label authority changed")
    _reject_private_fields_and_paths(document)
    return document


def create_remix_training_snapshot(
    *,
    labels: Sequence[Mapping[str, Any]],
    owner_registries: Sequence[Mapping[str, Any]],
    variant_sets: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    snapshot_id: str,
) -> dict[str, Any]:
    _safe_id(snapshot_id, "snapshot_id")
    registries = [_validate_registry_structure(value) for value in owner_registries]
    registry_by_hash = {row["document_sha256"]: row for row in registries}
    variants = [
        _validate_variant_embedded(value, registry_by_hash) for value in variant_sets
    ]
    variant_by_hash = {row["document_sha256"]: row for row in variants}
    if len(registry_by_hash) != len(registries) or len(variant_by_hash) != len(
        variants
    ):
        raise ValueError("training snapshot repeats a registry or variant set")
    checked_labels = [
        _validate_label_embedded(value, registry_by_hash, variant_by_hash)
        for value in labels
    ]
    label_by_hash = {row["document_sha256"]: row for row in checked_labels}
    if not checked_labels or len(label_by_hash) != len(checked_labels):
        raise ValueError("training snapshot requires unique explicit labels")
    checked_assignments = _assignments(assignments, label_by_hash, variant_by_hash)
    _disjoint(checked_assignments)
    _reject_unordered_duplicates(checked_labels, checked_assignments)
    evidence = _snapshot_evidence(checked_labels, checked_assignments)
    document: dict[str, Any] = {
        "schema": REMIX_TRAINING_SNAPSHOT_SCHEMA,
        "status": "training_ineligible",
        "snapshot_id": str(snapshot_id),
        "method_natures": ["D", "H"],
        "labels": sorted(checked_labels, key=lambda row: row["document_sha256"]),
        "owner_registries": sorted(registries, key=lambda row: row["document_sha256"]),
        "variant_sets": sorted(variants, key=lambda row: row["document_sha256"]),
        "assignments": sorted(
            checked_assignments, key=lambda row: row["label_document_sha256"]
        ),
        "split_policy": {
            "composition_disjoint": True,
            "group_disjoint": True,
            "musical_state_disjoint": True,
            "variant_family_disjoint": True,
        },
        "evidence_gate": evidence,
        "authority": {
            "explicit_labels_only": True,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_admitted": False,
        },
        "privacy": {
            "paths_embedded": False,
            "audio_embedded": False,
            "cloud_training_approved": False,
        },
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_training_snapshot(document)


def validate_remix_training_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    document = _verified_document(
        snapshot, REMIX_TRAINING_SNAPSHOT_SCHEMA, "training snapshot"
    )
    expected_keys = {
        "schema",
        "status",
        "snapshot_id",
        "method_natures",
        "labels",
        "owner_registries",
        "variant_sets",
        "assignments",
        "split_policy",
        "evidence_gate",
        "authority",
        "privacy",
        "network_used",
        "document_sha256",
    }
    if (
        set(document) != expected_keys
        or document.get("status") != "training_ineligible"
    ):
        raise ValueError("training snapshot fields or ineligible status changed")
    _safe_id(document.get("snapshot_id"), "snapshot_id")
    registries = [
        _validate_registry_structure(value)
        for value in _sequence(document.get("owner_registries"), "registries")
    ]
    registry_by_hash = {row["document_sha256"]: row for row in registries}
    variants = [
        _validate_variant_embedded(value, registry_by_hash)
        for value in _sequence(document.get("variant_sets"), "variant sets")
    ]
    variant_by_hash = {row["document_sha256"]: row for row in variants}
    labels = [
        _validate_label_embedded(value, registry_by_hash, variant_by_hash)
        for value in _sequence(document.get("labels"), "labels")
    ]
    label_by_hash = {row["document_sha256"]: row for row in labels}
    assignments = _assignments(
        document.get("assignments", []), label_by_hash, variant_by_hash
    )
    _disjoint(assignments)
    _reject_unordered_duplicates(labels, assignments)
    if document.get("method_natures") != ["D", "H"] or document.get("split_policy") != {
        "composition_disjoint": True,
        "group_disjoint": True,
        "musical_state_disjoint": True,
        "variant_family_disjoint": True,
    }:
        raise ValueError("training snapshot split contract changed")
    if document.get("evidence_gate") != _snapshot_evidence(labels, assignments):
        raise ValueError("training snapshot evidence gate changed")
    if document.get("authority") != {
        "explicit_labels_only": True,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_admitted": False,
    }:
        raise ValueError("training snapshot authority changed while ineligible")
    if (
        document.get("privacy")
        != {
            "paths_embedded": False,
            "audio_embedded": False,
            "cloud_training_approved": False,
        }
        or document.get("network_used") is not False
    ):
        raise ValueError("training snapshot privacy or network boundary changed")
    _reject_private_fields_and_paths(document)
    return document


def _validate_registry_structure(value: Mapping[str, Any]) -> dict[str, Any]:
    document = _verified_document(value, REMIX_OWNER_REGISTRY_SCHEMA, "owner registry")
    if set(document) != {
        "schema",
        "status",
        "registry_id",
        "method_natures",
        "entries",
        "authority",
        "privacy",
        "effects",
        "document_sha256",
    }:
        raise ValueError("owner registry fields changed")
    if document.get("status") != "complete_owner_confirmed_registry" or document.get(
        "method_natures"
    ) != ["D", "H"]:
        raise ValueError("owner registry status or method nature changed")
    _safe_id(document.get("registry_id"), "registry_id")
    expected_entry_keys = {
        "composition_id",
        "group_id",
        "musical_state_sha256",
        "identity_state_sha256",
        "source_control_audio_sha256",
        "relationship_sha256",
        "source_control_audio_bytes",
        "source_control_geometry",
        "anchor_ids",
        "rights_scope",
        "cloud_training_approved",
    }
    rows = _sequence(document.get("entries"), "owner registry entries")
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        row = _mapping(row, "owner registry entry")
        if set(row) != expected_entry_keys:
            raise ValueError("owner registry entry fields changed")
        composition = _safe_id(row.get("composition_id"), "composition_id")
        group = _safe_id(row.get("group_id"), "group_id")
        for key in (
            "musical_state_sha256",
            "identity_state_sha256",
            "source_control_audio_sha256",
        ):
            _sha(row.get(key), key)
        relationship = {
            key: row[key]
            for key in (
                "composition_id",
                "group_id",
                "musical_state_sha256",
                "identity_state_sha256",
                "source_control_audio_sha256",
            )
        }
        if row.get("relationship_sha256") != document_sha256(relationship):
            raise ValueError(
                "owner registry immutable composition relationship changed"
            )
        _positive_int(row.get("source_control_audio_bytes"), "source control bytes")
        _geometry(row.get("source_control_geometry"))
        anchors = row.get("anchor_ids")
        if (
            not isinstance(anchors, list)
            or not anchors
            or anchors != sorted(set(anchors))
        ):
            raise ValueError("owner registry anchor roster changed")
        for anchor in anchors:
            _safe_id(anchor, "anchor_id")
        if (
            row.get("rights_scope") != "owner_local_training"
            or row.get("cloud_training_approved") is not False
        ):
            raise ValueError("owner registry rights scope changed")
        groups[group].add(composition)
    if not rows or any(len(values) != 1 for values in groups.values()):
        raise ValueError("each group must belong to one composition")
    if (
        document.get("authority")
        != {
            "owner_confirmed_relationships": True,
            "automatic_relationship_inference": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        }
        or document.get("privacy")
        != {
            "local_training_approved": True,
            "cloud_training_approved": False,
            "paths_embedded": False,
        }
        or document.get("effects")
        != {
            "sources_mutated": False,
            "remix_rendered": False,
            "training_started": False,
            "model_weights_changed": False,
        }
    ):
        raise ValueError("owner registry authority, privacy or effects changed")
    _reject_private_fields_and_paths(document)
    return document


def _validate_variant_embedded(
    value: Mapping[str, Any], registries: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    document = dict(value)
    registry = registries.get(str(document.get("registry_sha256", "")))
    if registry is None:
        raise ValueError("variant set has no embedded owner registry")
    identity = _mapping(document.get("identity_state"), "embedded identity state")
    return validate_remix_controlled_variant_set(document, registry, identity)


def _validate_label_embedded(
    value: Mapping[str, Any],
    registries: Mapping[str, Mapping[str, Any]],
    variants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    document = dict(value)
    binding = _mapping(document.get("binding"), "label binding")
    registry = registries.get(str(binding.get("owner_registry_sha256", "")))
    variant_set = variants.get(str(binding.get("variant_set_sha256", "")))
    if registry is None or variant_set is None:
        raise ValueError("label has no embedded registry or variant evidence")
    return validate_remix_pairwise_label(
        document, registry, variant_set, variant_set["identity_state"]
    )


def _validate_identity_structure(value: Mapping[str, Any]) -> dict[str, Any]:
    document = _verified_document(value, REMIX_IDENTITY_STATE_SCHEMA, "identity state")
    if document.get("status") != "complete_owner_anchored_no_remix":
        raise ValueError("identity state status changed")
    if (
        document.get("model_used") is not False
        or document.get("training_used") is not False
        or document.get("network_used") is not False
    ):
        raise ValueError("identity state cannot use model, training or network")
    return document


def _variant_rows(
    values: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or len(values) < 2
    ):
        raise ValueError("controlled variant set requires at least two variants")
    rows: list[dict[str, Any]] = []
    for raw in values:
        item = dict(_mapping(raw, "controlled variant"))
        if set(item) not in (
            {"variant_id", "remix_request", "remix_result"},
            {
                "variant_id",
                "remix_request",
                "remix_result",
                "variant_evidence_sha256",
            },
        ):
            raise ValueError("controlled variant fields changed")
        variant_id = _safe_id(item["variant_id"], "variant_id")
        request = validate_remix_request(item["remix_request"], identity)
        result = validate_remix_result(item["remix_result"], request, identity)
        if request.get("one_variable_policy") != "gain_delta_envelope_only":
            raise ValueError("variant set contains a second variable")
        evidence = {
            "variant_id": variant_id,
            "remix_request_sha256": request["document_sha256"],
            "remix_result_sha256": result["document_sha256"],
            "output_audio_sha256": result["output"]["audio_sha256"],
        }
        supplied_commitment = item.get("variant_evidence_sha256")
        expected_commitment = document_sha256(evidence)
        if (
            supplied_commitment is not None
            and supplied_commitment != expected_commitment
        ):
            raise ValueError("variant result evidence commitment changed")
        rows.append(
            {
                "variant_id": variant_id,
                "remix_request": request,
                "remix_result": result,
                "variant_evidence_sha256": expected_commitment,
            }
        )
    if len({row["variant_id"] for row in rows}) != len(rows):
        raise ValueError("variant set contains duplicate variant IDs")
    if len({row["remix_result"]["output"]["audio_sha256"] for row in rows}) != len(
        rows
    ):
        raise ValueError("variant set contains duplicate challenger audio")
    return rows


def _variant_side(variant_set: Mapping[str, Any], variant_id: Any) -> dict[str, Any]:
    for row in variant_set["variants"]:
        if row["variant_id"] == variant_id:
            return {
                "variant_id": row["variant_id"],
                "remix_request": row["remix_request"],
                "remix_result": row["remix_result"],
                "variant_evidence_sha256": row["variant_evidence_sha256"],
            }
    raise ValueError("pairwise label references an unknown variant")


def _registry_row(
    registry: Mapping[str, Any], identity: Mapping[str, Any], control: Mapping[str, Any]
) -> Mapping[str, Any]:
    matches = [
        row
        for row in registry["entries"]
        if row["identity_state_sha256"] == identity["document_sha256"]
        and row["source_control_audio_sha256"] == control["audio_sha256"]
    ]
    if len(matches) != 1:
        raise ValueError(
            "registry does not contain one exact identity/control relationship"
        )
    row = matches[0]
    if (
        row["source_control_audio_bytes"] != control["audio_bytes"]
        or row["source_control_geometry"] != control["geometry"]
    ):
        raise ValueError("source control evidence changed from registry")
    return row


def _assignments(
    values: Sequence[Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
    variant_sets: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected = {
        "label_document_sha256",
        "composition_id",
        "group_id",
        "musical_state_sha256",
        "variant_family_id",
        "split",
    }
    for raw in _sequence(values, "training assignments"):
        row = dict(_mapping(raw, "training assignment"))
        if set(row) != expected:
            raise ValueError("training assignment fields changed")
        label_hash = _sha(row["label_document_sha256"], "label assignment")
        label = labels.get(label_hash)
        if label is None:
            raise ValueError("training assignment references an unknown label")
        for key in ("composition_id", "group_id", "variant_family_id"):
            _safe_id(row[key], key)
        _sha(row["musical_state_sha256"], "musical_state assignment")
        if row["split"] not in _SPLITS:
            raise ValueError("training assignment split changed")
        binding = label["binding"]
        variant_set = variant_sets.get(binding["variant_set_sha256"])
        if variant_set is None:
            raise ValueError("training assignment has no exact variant set")
        if (
            row["musical_state_sha256"] != binding["musical_state_sha256"]
            or row["variant_family_id"] != binding["variant_family_id"]
            or row["composition_id"] != variant_set["composition_id"]
            or row["group_id"] != variant_set["group_id"]
        ):
            raise ValueError(
                "training assignment changed label composition, group, state or variant-family split identity"
            )
        rows.append(row)
    if len(rows) != len(labels) or len(
        {row["label_document_sha256"] for row in rows}
    ) != len(rows):
        raise ValueError("every label requires exactly one assignment")
    return rows


def _disjoint(rows: Sequence[Mapping[str, Any]]) -> None:
    for key, label in (
        ("composition_id", "composition"),
        ("group_id", "group"),
        ("musical_state_sha256", "musical_state"),
        ("variant_family_id", "variant_family"),
    ):
        seen: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            seen[str(row[key])].add(str(row["split"]))
        if any(len(splits) != 1 for splits in seen.values()):
            raise ValueError(f"{label} IDs must be split-disjoint")


def _reject_unordered_duplicates(
    labels: Sequence[Mapping[str, Any]], assignments: Sequence[Mapping[str, Any]]
) -> None:
    by_hash = {row["document_sha256"]: row for row in labels}
    seen: set[tuple[str, str, frozenset[str]]] = set()
    for assignment in assignments:
        label = by_hash[assignment["label_document_sha256"]]
        pair = (
            assignment["composition_id"],
            assignment["variant_family_id"],
            frozenset(
                {
                    label["left"]["remix_result"]["output"]["audio_sha256"],
                    label["right"]["remix_result"]["output"]["audio_sha256"],
                }
            ),
        )
        if pair in seen:
            raise ValueError("training snapshot contains a duplicate unordered pair")
        seen.add(pair)


def _snapshot_evidence(
    labels: Sequence[Mapping[str, Any]], assignments: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    outcomes = Counter(str(row["outcome"]) for row in labels)
    splits = defaultdict(set)
    for row in assignments:
        splits[row["split"]].add(row["composition_id"])
    directional = outcomes["left"] + outcomes["right"]
    observed = {
        "explicit_labels": len(labels),
        "directional_labels": directional,
        "left_directional_labels": outcomes["left"],
        "right_directional_labels": outcomes["right"],
        "compositions": len({row["composition_id"] for row in assignments}),
        "groups": len({row["group_id"] for row in assignments}),
        "train_compositions": len(splits["train"]),
        "validation_compositions": len(splits["validation"]),
        "test_compositions": len(splits["test"]),
        "outcomes": {name: outcomes[name] for name in sorted(_OUTCOMES)},
    }
    checks = {
        key.removeprefix("minimum_"): observed[key.removeprefix("minimum_")] >= minimum
        for key, minimum in REMIX_EVIDENCE_GATES.items()
    }
    return {
        "thresholds": dict(REMIX_EVIDENCE_GATES),
        "observed": observed,
        "checks": checks,
        "evidence_gate_passed": all(checks.values()),
    }


def _pairwise_values(
    outcome: Any, left_identity: Any, right_identity: Any, reasons: Sequence[str]
) -> None:
    if outcome not in _OUTCOMES:
        raise ValueError("unsupported remix pairwise outcome")
    if left_identity not in _IDENTITY or right_identity not in _IDENTITY:
        raise ValueError("unsupported identity relationship")
    _pairwise_reason_values(reasons)
    _pairwise_reason_relationship(outcome, reasons)


def _pairwise_reason_values(reasons: Sequence[str]) -> None:
    """Validate the bounded, distinct remix reason vocabulary."""

    if (
        not isinstance(reasons, Sequence)
        or isinstance(reasons, (str, bytes))
        or not 1 <= len(reasons) <= 4
        or len(reasons) != len(set(reasons))
        or any(reason not in _REASONS for reason in reasons)
    ):
        raise ValueError("remix pairwise reason codes changed")


def _pairwise_reason_relationship(outcome: str, reasons: Sequence[str]) -> None:
    """Require special outcomes to retain their explanatory reason."""

    if outcome == "cannot_tell" and "unable_to_compare" not in reasons:
        raise ValueError("cannot_tell requires unable_to_compare")
    if outcome == "neither" and "both_unusable" not in reasons:
        raise ValueError("neither requires both_unusable")


def _audio_record(value: Any, label: str) -> dict[str, Any]:
    row = dict(_mapping(value, label))
    if set(row) != {"audio_sha256", "audio_bytes", "geometry"}:
        raise ValueError(f"{label} fields changed")
    return {
        "audio_sha256": _sha(row["audio_sha256"], label),
        "audio_bytes": _positive_int(row["audio_bytes"], f"{label} bytes"),
        "geometry": _geometry(row["geometry"]),
    }


def _geometry(value: Any) -> dict[str, int]:
    row = dict(_mapping(value, "audio geometry"))
    if set(row) != {"sample_rate_hz", "channels", "frames"}:
        raise ValueError("audio geometry fields changed")
    return {
        key: _positive_int(row[key], key)
        for key in ("sample_rate_hz", "channels", "frames")
    }


def _verified_document(
    value: Mapping[str, Any], schema: str, label: str
) -> dict[str, Any]:
    document = dict(_mapping(value, label))
    if document.get("schema") != schema:
        raise ValueError(f"unsupported {label} schema")
    supplied = _sha(document.get("document_sha256"), f"{label} document")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if document_sha256(unsigned) != supplied:
        raise ValueError(f"{label} document hash changed")
    return document


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    return value


def _safe_id(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} must be a safe path-free identifier")
    return text


def _sha(value: Any, label: str) -> str:
    text = str(value)
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} SHA-256 is invalid")
    return text


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _reject_private_fields_and_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            folded = str(key).casefold()
            if folded in {
                "path",
                "absolute_path",
                "source_path",
                "output_path",
                "private_notes",
                "notes",
                "lyrics",
            }:
                raise ValueError(
                    "portable remix-learning evidence contains private fields"
                )
            _reject_private_fields_and_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_fields_and_paths(item)
    elif isinstance(value, str):
        posix = PurePosixPath(value)
        windows = PureWindowsPath(value)
        if posix.is_absolute() or windows.is_absolute():
            raise ValueError("portable remix-learning evidence must be path-free")


__all__ = [
    "REMIX_EVIDENCE_GATES",
    "REMIX_OWNER_REGISTRY_SCHEMA",
    "REMIX_PAIRWISE_LABEL_SCHEMA",
    "REMIX_TRAINING_SNAPSHOT_SCHEMA",
    "REMIX_VARIANT_SET_SCHEMA",
    "create_remix_controlled_variant_set",
    "create_remix_owner_registry",
    "create_remix_pairwise_label",
    "create_remix_training_snapshot",
    "validate_remix_controlled_variant_set",
    "validate_remix_owner_registry",
    "validate_remix_pairwise_label",
    "validate_remix_training_snapshot",
]
