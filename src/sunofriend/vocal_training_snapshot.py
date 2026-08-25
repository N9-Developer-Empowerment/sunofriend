"""Immutable, path-free snapshots of explicit vocal A/B labels."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

from .source_receipt import document_sha256
from .vocal_pairwise_label import (
    PAIRWISE_REASON_CODES,
    VOCAL_PAIRWISE_LABEL_SCHEMA,
    validate_vocal_pairwise_label,
)


VOCAL_TRAINING_SNAPSHOT_SCHEMA = "sunofriend.vocal-pairwise-training-snapshot.v1"
SPLITS = frozenset({"train", "validation", "test"})
EVIDENCE_GATES = {
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


def create_vocal_training_snapshot(
    labels: Sequence[Mapping[str, Any]],
    *,
    assignments: Sequence[Mapping[str, Any]],
    snapshot_id: str,
) -> dict[str, Any]:
    """Create a path-free snapshot without granting training execution."""

    if not _SAFE_ID.fullmatch(str(snapshot_id)):
        raise ValueError("snapshot_id must be a safe path-free identifier")
    validated = [validate_vocal_pairwise_label(item) for item in labels]
    if not validated:
        raise ValueError("training snapshot requires explicit pairwise labels")
    by_hash = {item["document_sha256"]: item for item in validated}
    if len(by_hash) != len(validated):
        raise ValueError("training snapshot contains duplicate label documents")

    assignment_by_hash: dict[str, dict[str, str]] = {}
    for raw in assignments:
        row = dict(raw)
        if set(row) != {
            "label_document_sha256",
            "composition_id",
            "group_id",
            "split",
        }:
            raise ValueError("training split assignment fields changed")
        label_hash = _sha256(row["label_document_sha256"], "label assignment")
        for key in ("composition_id", "group_id"):
            if not _SAFE_ID.fullmatch(str(row[key])):
                raise ValueError(f"{key} must be a safe path-free identifier")
        if row["split"] not in SPLITS:
            raise ValueError("training split must be train, validation or test")
        if label_hash in assignment_by_hash:
            raise ValueError("training snapshot contains duplicate assignments")
        assignment_by_hash[label_hash] = {
            "label_document_sha256": label_hash,
            "composition_id": str(row["composition_id"]),
            "group_id": str(row["group_id"]),
            "split": str(row["split"]),
        }
    if assignment_by_hash.keys() != by_hash.keys():
        raise ValueError("every explicit label requires exactly one split assignment")
    _enforce_disjoint_splits(validated, assignment_by_hash)

    rows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str, frozenset[str]]] = set()
    for label_hash in sorted(by_hash):
        label = by_hash[label_hash]
        assignment = assignment_by_hash[label_hash]
        pair_key = (
            label["binding"]["musical_state_sha256"],
            label["phrase"]["phrase_sha256"],
            assignment["composition_id"],
            frozenset({label["left"]["audio_sha256"], label["right"]["audio_sha256"]}),
        )
        if pair_key in seen_pairs:
            raise ValueError("training snapshot repeats the same unordered A/B pair")
        seen_pairs.add(pair_key)
        rows.append(
            {
                "explicit_label": label,
                "label_schema": VOCAL_PAIRWISE_LABEL_SCHEMA,
                "label_document_sha256": label_hash,
                "musical_state_sha256": label["binding"]["musical_state_sha256"],
                "phrase_id": label["phrase"]["phrase_id"],
                "phrase_sha256": label["phrase"]["phrase_sha256"],
                "left_audio_sha256": label["left"]["audio_sha256"],
                "right_audio_sha256": label["right"]["audio_sha256"],
                "outcome": label["outcome"],
                "reason_codes": list(label["reason_codes"]),
                "composition_id": assignment["composition_id"],
                "group_id": assignment["group_id"],
                "split": assignment["split"],
            }
        )

    evidence = _evidence(rows)
    document: dict[str, Any] = {
        "schema": VOCAL_TRAINING_SNAPSHOT_SCHEMA,
        "status": "training_ineligible",
        "snapshot_id": str(snapshot_id),
        "method_natures": ["D", "H"],
        "labels": rows,
        "split_policy": {
            "group_disjoint": True,
            "composition_disjoint": True,
            "musical_state_disjoint": True,
        },
        "evidence_gate": evidence,
        "registry_gate": {
            "owner_confirmed_composition_registry_bound": False,
            "owner_confirmed_group_registry_bound": False,
            "training_request_eligible": False,
            "reason": "owner-confirmed immutable composition/group registry is not yet implemented",
        },
        "authority": {
            "explicit_labels_only": True,
            "playback_derived_labels": False,
            "phrase_selection_derived_labels": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_selection_authorized": False,
        },
        "privacy": {
            "paths_embedded": False,
            "notes_embedded": False,
            "lyrics_embedded": False,
            "audio_embedded": False,
        },
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_training_snapshot(document)


def validate_vocal_training_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    if document.get("schema") != VOCAL_TRAINING_SNAPSHOT_SCHEMA:
        raise ValueError("unsupported vocal training snapshot schema")
    if set(document) != {
        "schema",
        "status",
        "snapshot_id",
        "method_natures",
        "labels",
        "split_policy",
        "evidence_gate",
        "registry_gate",
        "authority",
        "privacy",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("vocal training snapshot fields changed")
    supplied_hash = _sha256(document.get("document_sha256"), "snapshot document")
    without_hash = dict(document)
    without_hash.pop("document_sha256", None)
    if document_sha256(without_hash) != supplied_hash:
        raise ValueError("vocal training snapshot document hash changed")
    if not _SAFE_ID.fullmatch(str(document.get("snapshot_id", ""))):
        raise ValueError("snapshot_id must be a safe path-free identifier")
    labels = document.get("labels")
    if not isinstance(labels, list) or not labels:
        raise ValueError("training snapshot requires explicit label rows")
    _reject_private_fields_and_paths(document)
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError("snapshot must declare deterministic and human evidence")
    if document.get("split_policy") != {
        "group_disjoint": True,
        "composition_disjoint": True,
        "musical_state_disjoint": True,
    }:
        raise ValueError("training split policy changed")
    if document.get("authority") != {
        "explicit_labels_only": True,
        "playback_derived_labels": False,
        "phrase_selection_derived_labels": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_selection_authorized": False,
    }:
        raise ValueError("training snapshot authority changed")
    if document.get("privacy") != {
        "paths_embedded": False,
        "notes_embedded": False,
        "lyrics_embedded": False,
        "audio_embedded": False,
    }:
        raise ValueError("training snapshot privacy declaration changed")
    if document.get("network_used") is not False:
        raise ValueError("training snapshot must record network_used=false")
    _validate_snapshot_rows(labels)
    expected_evidence = _evidence(labels)
    if document.get("evidence_gate") != expected_evidence:
        raise ValueError("training snapshot evidence gate changed")
    if document.get("status") != "training_ineligible":
        raise ValueError("training snapshot eligibility status changed")
    if document.get("registry_gate") != {
        "owner_confirmed_composition_registry_bound": False,
        "owner_confirmed_group_registry_bound": False,
        "training_request_eligible": False,
        "reason": "owner-confirmed immutable composition/group registry is not yet implemented",
    }:
        raise ValueError("training snapshot registry gate changed")
    return document


def _enforce_disjoint_splits(
    labels: Sequence[Mapping[str, Any]], assignments: Mapping[str, Mapping[str, str]]
) -> None:
    dimensions: dict[str, dict[str, set[str]]] = {
        "composition": defaultdict(set),
        "group": defaultdict(set),
        "musical state": defaultdict(set),
    }
    group_compositions: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        assignment = assignments[label["document_sha256"]]
        split = assignment["split"]
        dimensions["composition"][assignment["composition_id"]].add(split)
        dimensions["group"][assignment["group_id"]].add(split)
        dimensions["musical state"][label["binding"]["musical_state_sha256"]].add(split)
        group_compositions[assignment["group_id"]].add(assignment["composition_id"])
    for name, rows in dimensions.items():
        if any(len(splits) != 1 for splits in rows.values()):
            raise ValueError(f"{name} IDs must be split-disjoint")
    if any(len(values) != 1 for values in group_compositions.values()):
        raise ValueError("each group_id must belong to one composition")


def _validate_snapshot_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    expected = {
        "label_schema",
        "explicit_label",
        "label_document_sha256",
        "musical_state_sha256",
        "phrase_id",
        "phrase_sha256",
        "left_audio_sha256",
        "right_audio_sha256",
        "outcome",
        "reason_codes",
        "composition_id",
        "group_id",
        "split",
    }
    compositions: dict[str, set[str]] = defaultdict(set)
    groups: dict[str, set[str]] = defaultdict(set)
    states: dict[str, set[str]] = defaultdict(set)
    group_compositions: dict[str, set[str]] = defaultdict(set)
    hashes: set[str] = set()
    pairs: set[tuple[str, str, str, frozenset[str]]] = set()
    for row in rows:
        label_hash = _validate_snapshot_row(row, expected=expected)
        if label_hash in hashes:
            raise ValueError("training snapshot duplicates a label")
        hashes.add(label_hash)
        pair = (
            row["musical_state_sha256"],
            row["phrase_sha256"],
            row["composition_id"],
            frozenset({row["left_audio_sha256"], row["right_audio_sha256"]}),
        )
        if pair in pairs:
            raise ValueError("training snapshot repeats the same unordered A/B pair")
        pairs.add(pair)
        split = row["split"]
        compositions[row["composition_id"]].add(split)
        groups[row["group_id"]].add(split)
        states[row["musical_state_sha256"]].add(split)
        group_compositions[row["group_id"]].add(row["composition_id"])
    _validate_snapshot_split_dimensions(
        compositions=compositions,
        groups=groups,
        states=states,
        group_compositions=group_compositions,
    )


def _validate_snapshot_row(row: Mapping[str, Any], *, expected: set[str]) -> str:
    if not isinstance(row, Mapping) or set(row) != expected:
        raise ValueError("training snapshot label row fields changed")
    if row["label_schema"] != VOCAL_PAIRWISE_LABEL_SCHEMA:
        raise ValueError("training snapshot contains a non-pairwise label")
    label = validate_vocal_pairwise_label(row["explicit_label"])
    label_hash = _sha256(row["label_document_sha256"], "snapshot label")
    if label_hash != label["document_sha256"]:
        raise ValueError("snapshot label projection does not bind its explicit label")
    projection = {
        "label_schema": VOCAL_PAIRWISE_LABEL_SCHEMA,
        "label_document_sha256": label["document_sha256"],
        "musical_state_sha256": label["binding"]["musical_state_sha256"],
        "phrase_id": label["phrase"]["phrase_id"],
        "phrase_sha256": label["phrase"]["phrase_sha256"],
        "left_audio_sha256": label["left"]["audio_sha256"],
        "right_audio_sha256": label["right"]["audio_sha256"],
        "outcome": label["outcome"],
        "reason_codes": label["reason_codes"],
    }
    if any(row[key] != value for key, value in projection.items()):
        raise ValueError("snapshot row projection changed from its explicit label")
    for key in (
        "musical_state_sha256",
        "phrase_sha256",
        "left_audio_sha256",
        "right_audio_sha256",
    ):
        _sha256(row[key], key)
    for key in ("phrase_id", "composition_id", "group_id"):
        if not _SAFE_ID.fullmatch(str(row[key])):
            raise ValueError(f"snapshot {key} must be path-free")
    _validate_snapshot_outcome(row)
    return label_hash


def _validate_snapshot_outcome(row: Mapping[str, Any]) -> None:
    if row["split"] not in SPLITS:
        raise ValueError("training split changed")
    if row["outcome"] not in {"left", "right", "equivalent", "neither", "cannot_tell"}:
        raise ValueError("training snapshot outcome changed")
    reasons = _snapshot_reason_codes(row["reason_codes"])
    _validate_snapshot_reason_relationship(row["outcome"], reasons)


def _snapshot_reason_codes(value: Any) -> list[str]:
    """Validate the bounded explicit reason vocabulary retained for training."""

    reasons = value
    if (
        not isinstance(reasons, list)
        or not 1 <= len(reasons) <= 4
        or len(reasons) != len(set(reasons))
        or any(reason not in PAIRWISE_REASON_CODES for reason in reasons)
    ):
        raise ValueError("training snapshot reason codes changed")
    return reasons


def _validate_snapshot_reason_relationship(outcome: str, reasons: list[str]) -> None:
    """Keep special reason codes consistent with their explicit outcome."""

    if outcome == "cannot_tell" and "unable_to_compare" not in reasons:
        raise ValueError("cannot_tell snapshot row requires unable_to_compare")
    if outcome == "neither" and "no_usable_attempt" not in reasons:
        raise ValueError("neither snapshot row requires no_usable_attempt")
    if outcome not in {"cannot_tell", "neither"} and {
        "unable_to_compare",
        "no_usable_attempt",
    }.intersection(reasons):
        raise ValueError("snapshot reason code does not match outcome")


def _validate_snapshot_split_dimensions(
    *,
    compositions: Mapping[str, set[str]],
    groups: Mapping[str, set[str]],
    states: Mapping[str, set[str]],
    group_compositions: Mapping[str, set[str]],
) -> None:
    for name, values in (
        ("composition", compositions),
        ("group", groups),
        ("musical state", states),
    ):
        if any(len(splits) != 1 for splits in values.values()):
            raise ValueError(f"{name} IDs must be split-disjoint")
    if any(len(values) != 1 for values in group_compositions.values()):
        raise ValueError("each group_id must belong to one composition")


def _evidence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(str(row["outcome"]) for row in rows)
    compositions = {str(row["composition_id"]) for row in rows}
    groups = {str(row["group_id"]) for row in rows}
    split_compositions = {
        split: {str(row["composition_id"]) for row in rows if row["split"] == split}
        for split in sorted(SPLITS)
    }
    observed = {
        "explicit_labels": len(rows),
        "directional_labels": outcomes["left"] + outcomes["right"],
        "left_directional_labels": outcomes["left"],
        "right_directional_labels": outcomes["right"],
        "compositions": len(compositions),
        "groups": len(groups),
        "train_compositions": len(split_compositions["train"]),
        "validation_compositions": len(split_compositions["validation"]),
        "test_compositions": len(split_compositions["test"]),
    }
    checks = {
        name: observed[name.removeprefix("minimum_")] >= minimum
        for name, minimum in EVIDENCE_GATES.items()
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "thresholds": dict(EVIDENCE_GATES),
        "observed": observed,
        "checks": checks,
        "failed_checks": failures,
        "evidence_gate_passed": not failures,
        "meaning": "dataset sufficiency only; execution and product use remain unauthorized",
    }


def _sha256(value: Any, label: str) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _reject_private_fields_and_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).casefold()
            if lowered in {
                "path",
                "notes",
                "note",
                "lyrics",
                "filename",
                "source_name",
            }:
                raise ValueError(
                    "training snapshot contains private text or a path field"
                )
            _reject_private_fields_and_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_fields_and_paths(item)
    elif isinstance(value, str):
        if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
            raise ValueError("training snapshot contains an absolute path")
