"""Split-safe snapshots for real source-delta remix preference labels.

The public operation rechecks every local render before admitting its label,
then returns a path-free immutable snapshot.  It owns dataset sufficiency and
split isolation only; it never extracts features, starts training or grants
product authority.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping, Sequence

from .remix_learning_contract import REMIX_EVIDENCE_GATES
from .remix_source_delta import verify_remix_source_delta_result
from .remix_source_delta_label import (
    validate_remix_source_delta_pairwise_label,
    validate_remix_source_delta_pairwise_label_document,
)
from .remix_source_state import validate_remix_source_state
from .source_receipt import document_sha256


REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA = (
    "sunofriend.remix-source-delta-training-snapshot.v0"
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SPLITS = frozenset({"train", "validation", "test"})


def create_remix_source_delta_training_snapshot(
    *, snapshot_id: str, examples: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Recheck exact renders and create one no-authority training snapshot."""

    _safe_id(snapshot_id)
    if not isinstance(examples, Sequence) or isinstance(examples, (str, bytes)):
        raise ValueError("source-delta examples must be a sequence")
    rows = [_checked_local_example(value) for value in examples]
    if not rows:
        raise ValueError("source-delta snapshot requires at least one label")
    labels = _unique_documents([row["label"] for row in rows], "label")
    states = _unique_documents([row["source_state"] for row in rows], "source state")
    assignments = sorted(
        [row["assignment"] for row in rows],
        key=lambda row: row["label_document_sha256"],
    )
    _validate_assignments(assignments, labels, states)
    evidence = _evidence_gate(labels, assignments)
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA,
        "status": "training_ineligible",
        "snapshot_id": snapshot_id,
        "method_natures": ["D", "H"],
        "labels": sorted(labels, key=lambda row: row["document_sha256"]),
        "source_states": sorted(states, key=lambda row: row["document_sha256"]),
        "assignments": assignments,
        "split_policy": _split_policy(),
        "evidence_gate": evidence,
        "readiness": _readiness(evidence),
        "authority": _zero_authority(),
        "effects": _zero_effects(),
        "privacy": _privacy(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_delta_training_snapshot(document)


def validate_remix_source_delta_training_snapshot(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Revalidate the immutable snapshot without reopening private audio."""

    document = _verified_document(value)
    if set(document) != {
        "schema",
        "status",
        "snapshot_id",
        "method_natures",
        "labels",
        "source_states",
        "assignments",
        "split_policy",
        "evidence_gate",
        "readiness",
        "authority",
        "effects",
        "privacy",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("source-delta training snapshot fields changed")
    if (
        document.get("schema") != REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA
        or document.get("status") != "training_ineligible"
        or document.get("method_natures") != ["D", "H"]
    ):
        raise ValueError("source-delta training snapshot identity changed")
    _safe_id(document.get("snapshot_id"))
    labels = _unique_documents(
        [
            validate_remix_source_delta_pairwise_label_document(row)
            for row in _sequence(document.get("labels"), "labels")
        ],
        "label",
    )
    states = _unique_documents(
        [
            validate_remix_source_state(row)
            for row in _sequence(document.get("source_states"), "source states")
        ],
        "source state",
    )
    assignments = list(_sequence(document.get("assignments"), "assignments"))
    _validate_assignments(assignments, labels, states)
    evidence = _evidence_gate(labels, assignments)
    if (
        document["labels"] != sorted(labels, key=lambda row: row["document_sha256"])
        or document["source_states"]
        != sorted(states, key=lambda row: row["document_sha256"])
        or document["assignments"]
        != sorted(assignments, key=lambda row: row["label_document_sha256"])
        or document.get("split_policy") != _split_policy()
        or document.get("evidence_gate") != evidence
        or document.get("readiness") != _readiness(evidence)
    ):
        raise ValueError("source-delta training snapshot evidence changed")
    if (
        document.get("authority") != _zero_authority()
        or document.get("effects") != _zero_effects()
        or document.get("privacy") != _privacy()
        or document.get("network_used") is not False
    ):
        raise ValueError("source-delta snapshot authority or effects changed")
    _reject_absolute_paths(document)
    return document


def _checked_local_example(value: Mapping[str, Any]) -> dict[str, Any]:
    row = _mapping(value, "source-delta example")
    if set(row) != {"label", "render_root", "source_state", "split"}:
        raise ValueError("source-delta example fields changed")
    root = Path(row["render_root"]).expanduser().resolve(strict=True)
    label = validate_remix_source_delta_pairwise_label(row["label"], root)
    state = validate_remix_source_state(row["source_state"])
    result = verify_remix_source_delta_result(root)
    try:
        plan = json.loads((root / "EVIDENCE/plan.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("source-delta plan is unreadable") from exc
    binding = label["binding"]
    if (
        binding["source_state_sha256"] != state["document_sha256"]
        or binding["plan_sha256"] != plan.get("document_sha256")
        or binding["render_result_sha256"] != result["document_sha256"]
    ):
        raise ValueError("source-delta source-state binding changed")
    split = str(row["split"])
    if split not in _SPLITS:
        raise ValueError("source-delta split must be train, validation or test")
    return {
        "label": label,
        "source_state": state,
        "assignment": {
            "label_document_sha256": label["document_sha256"],
            "source_state_sha256": state["document_sha256"],
            "composition_id": state["composition_id"],
            "group_id": state["group_id"],
            "variant_family_sha256": binding["variant_family_sha256"],
            "plan_sha256": binding["plan_sha256"],
            "render_result_sha256": binding["render_result_sha256"],
            "split": split,
        },
    }


def _validate_assignments(
    assignments: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    states: Sequence[Mapping[str, Any]],
) -> None:
    label_by_hash = {row["document_sha256"]: row for row in labels}
    state_by_hash = {row["document_sha256"]: row for row in states}
    if len(assignments) != len(labels):
        raise ValueError("each source-delta label requires one assignment")
    seen: set[str] = set()
    pairs: set[tuple[str, str, frozenset[str]]] = set()
    checked: list[dict[str, Any]] = []
    for raw in assignments:
        row = _mapping(raw, "source-delta assignment")
        label = label_by_hash.get(str(row.get("label_document_sha256")))
        state = state_by_hash.get(str(row.get("source_state_sha256")))
        if label is None or state is None:
            raise ValueError("source-delta assignment has no embedded evidence")
        expected = _expected_assignment(label, state, row.get("split"))
        if row != expected:
            raise ValueError("source-delta assignment evidence changed")
        identity = label["document_sha256"]
        if identity in seen:
            raise ValueError("source-delta assignment repeats a label")
        seen.add(identity)
        pair = (
            state["composition_id"],
            label["binding"]["variant_family_sha256"],
            frozenset({label["left"]["audio_sha256"], label["right"]["audio_sha256"]}),
        )
        if pair in pairs:
            raise ValueError("source-delta snapshot repeats an unordered variant pair")
        pairs.add(pair)
        checked.append(row)
    _require_split_isolation(checked)


def _expected_assignment(
    label: Mapping[str, Any], state: Mapping[str, Any], split_value: Any
) -> dict[str, Any]:
    split = str(split_value)
    if split not in _SPLITS:
        raise ValueError("source-delta split must be train, validation or test")
    binding = label["binding"]
    if binding["source_state_sha256"] != state["document_sha256"]:
        raise ValueError("source-delta label and source state differ")
    return {
        "label_document_sha256": label["document_sha256"],
        "source_state_sha256": state["document_sha256"],
        "composition_id": state["composition_id"],
        "group_id": state["group_id"],
        "variant_family_sha256": binding["variant_family_sha256"],
        "plan_sha256": binding["plan_sha256"],
        "render_result_sha256": binding["render_result_sha256"],
        "split": split,
    }


def _require_split_isolation(assignments: Sequence[Mapping[str, Any]]) -> None:
    dimensions = (
        "composition_id",
        "group_id",
        "source_state_sha256",
        "variant_family_sha256",
    )
    for field in dimensions:
        split_by_value: dict[str, set[str]] = defaultdict(set)
        for row in assignments:
            split_by_value[str(row[field])].add(str(row["split"]))
        if any(len(splits) > 1 for splits in split_by_value.values()):
            raise ValueError(f"source-delta {field} is not split-disjoint")


def _evidence_gate(
    labels: Sequence[Mapping[str, Any]], assignments: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    outcomes = Counter(row["outcome"] for row in labels)
    composition_splits = {
        (row["composition_id"], row["split"]) for row in assignments
    }
    observed = {
        "explicit_labels": len(labels),
        "directional_labels": outcomes["left"] + outcomes["right"],
        "left_directional_labels": outcomes["left"],
        "right_directional_labels": outcomes["right"],
        "compositions": len({row["composition_id"] for row in assignments}),
        "groups": len({row["group_id"] for row in assignments}),
        "train_compositions": sum(split == "train" for _, split in composition_splits),
        "validation_compositions": sum(
            split == "validation" for _, split in composition_splits
        ),
        "test_compositions": sum(split == "test" for _, split in composition_splits),
    }
    checks = {
        name.removeprefix("minimum_"): observed[name.removeprefix("minimum_")]
        >= minimum
        for name, minimum in REMIX_EVIDENCE_GATES.items()
    }
    return {
        "thresholds": dict(REMIX_EVIDENCE_GATES),
        "observed": observed,
        "checks": checks,
        "evidence_gate_passed": all(checks.values()),
        "meaning": "dataset sufficiency only; training remains separately unauthorized",
    }


def _readiness(evidence: Mapping[str, Any]) -> dict[str, Any]:
    observed = evidence["observed"]
    shortfalls = {
        name.removeprefix("minimum_"): max(
            0, int(minimum) - int(observed[name.removeprefix("minimum_")])
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
        "shortfalls": shortfalls,
        "next_gate": (
            "request_separate_feature_and_training_authority"
            if passed
            else "collect_owner_labels"
        ),
    }


def _unique_documents(
    values: Sequence[Mapping[str, Any]], label: str
) -> list[dict[str, Any]]:
    rows = [dict(value) for value in values]
    identities = [str(row.get("document_sha256")) for row in rows]
    if len(identities) != len(set(identities)):
        if label == "source state":
            unique = {row["document_sha256"]: row for row in rows}
            return list(unique.values())
        raise ValueError(f"source-delta snapshot repeats a {label}")
    return rows


def _verified_document(value: Mapping[str, Any]) -> dict[str, Any]:
    document = _mapping(value, "source-delta training snapshot")
    supplied = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("source-delta training snapshot SHA-256 changed")
    return document


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"source-delta snapshot {label} must be a non-empty list")
    if any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"source-delta snapshot {label} entries must be objects")
    return value


def _safe_id(value: Any) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError("source-delta snapshot_id is invalid")
    return text


def _split_policy() -> dict[str, bool]:
    return {
        "composition_disjoint": True,
        "group_disjoint": True,
        "source_state_disjoint": True,
        "variant_family_disjoint": True,
    }


def _zero_authority() -> dict[str, bool]:
    return {
        "explicit_labels_only": True,
        "feature_extraction_authorized": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_admitted": False,
    }


def _zero_effects() -> dict[str, bool]:
    return {
        "audio_read_for_exact_revalidation": True,
        "features_extracted": False,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
    }


def _privacy() -> dict[str, bool]:
    return {
        "owner_local_only": True,
        "paths_embedded": False,
        "audio_embedded": False,
        "cloud_training_approved": False,
    }


def _looks_like_absolute_path(text: str) -> bool:
    return (
        text.startswith(("/", "~", "file:"))
        or bool(re.match(r"^[A-Za-z]:", text))
        or PurePosixPath(text).is_absolute()
        or PureWindowsPath(text).is_absolute()
    )


def _reject_absolute_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_absolute_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_absolute_paths(item)
    elif isinstance(value, str) and _looks_like_absolute_path(value):
        raise ValueError("source-delta training snapshot must not contain paths")


__all__ = [
    "REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA",
    "create_remix_source_delta_training_snapshot",
    "validate_remix_source_delta_training_snapshot",
]
