"""Read-only preparation contract for a future separation bake-off.

This module can prove that a frozen acceptance policy and its hidden manifest
are internally consistent, then derive a redacted orchestration plan.  It
cannot execute a separator, load a checkpoint, read audio or results, calculate
scores, decide a pass, promote a role or write an artifact.

Every preparation and validation reloads the complete canonical acceptance
artifact and re-verifies the complete canonical hidden manifest.  The returned
document binds those inputs by content hashes while exposing only aggregate
coverage and the public orchestration identifiers needed by a later runner.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .separation_acceptance import (
    MAX_ACCEPTANCE_BYTES,
    MAX_HIDDEN_MANIFEST_BYTES,
    SEPARATION_ACCEPTANCE_SCHEMA,
    SEPARATION_HIDDEN_MANIFEST_SCHEMA,
    canonical_json_bytes,
    load_separation_acceptance_thresholds,
    verify_hidden_evaluation_manifest,
)


SEPARATION_BAKEOFF_PREPARATION_SCHEMA = (
    "sunofriend.separation-bakeoff-preparation.v1"
)
SEPARATION_BAKEOFF_PREPARATION_STATUS = "prepared_not_run"
SEPARATION_BAKEOFF_ORCHESTRATION_PROTOCOL = (
    "baseline-then-candidate-paired-arms-v1"
)
MAX_BAKEOFF_PREPARATION_BYTES = 512 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PREPARATION_ID_RE = re.compile(
    r"^separation-bakeoff-preparation:[0-9a-f]{64}$"
)
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:/-]{0,191}$")
_ROLE_ID_RE = re.compile(r"^role-prepared:[a-z][a-z0-9_]*$")
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_FORBIDDEN_TEXT = frozenset(
    {
        "changeme",
        "n/a",
        "na",
        "none",
        "null",
        "placeholder",
        "tbd",
        "todo",
        "unknown",
    }
)
_GATE_IDS = (
    "gate:human-noninferiority",
    "gate:licence",
    "gate:offline",
    "gate:resource",
    "gate:technical-metrics",
)
_TOP_FIELDS = frozenset(
    {
        "schema",
        "status",
        "preparation_id",
        "preparation_sha256",
        "acceptance",
        "hidden_evaluation",
        "orchestration",
        "effects",
    }
)
_ACCEPTANCE_FIELDS = frozenset(
    {
        "schema",
        "status",
        "profile_id",
        "artifact_sha256",
        "canonical_document_sha256",
    }
)
_HIDDEN_FIELDS = frozenset(
    {
        "schema",
        "manifest_sha256",
        "split_sha256",
        "total_songs",
        "groups",
        "ground_truth_pairs_by_role",
    }
)
_GROUP_FIELDS = frozenset(
    {"acoustic", "electronic_ai_generated", "mixed"}
)
_ORCHESTRATION_FIELDS = frozenset(
    {
        "protocol",
        "arms",
        "role_prepared_ids",
        "downstream_midi_identity_by_role",
        "metric_evaluator_identity_id",
        "resource_class_ids",
        "gate_ids",
        "paired_unit",
        "aggregate_policy",
    }
)
_ARM_FIELDS = frozenset(
    {"order", "arm_id", "separator_identity_id"}
)
_EFFECT_FIELDS = frozenset(
    {
        "model_executed",
        "model_loaded",
        "worker_started",
        "inference_started",
        "inference_executed",
        "checkpoint_loaded",
        "model_downloaded",
        "checkpoint_downloaded",
        "audio_read",
        "audio_written",
        "network_used",
        "files_written",
        "results_read",
        "metrics_computed",
        "scores_read",
        "hidden_scores_read",
        "threshold_values_exposed",
        "private_metadata_exposed",
        "candidate_selected",
        "roles_selected",
        "promotion_decided",
        "automatic_defaults_changed",
    }
)


def separation_bakeoff_preparation_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash a preparation excluding only its self-hash field."""

    payload = _plain(_mapping(document, "bake-off preparation"))
    payload.pop("preparation_sha256", None)
    _reject_invalid_tree(payload, "bake-off preparation")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def prepare_separation_bakeoff(
    *,
    acceptance_path: str | Path,
    hidden_manifest_path: str | Path,
    maximum_acceptance_bytes: int = MAX_ACCEPTANCE_BYTES,
    maximum_hidden_manifest_bytes: int = MAX_HIDDEN_MANIFEST_BYTES,
) -> Mapping[str, Any]:
    """Reload, reverify and redact the inputs into an immutable plan."""

    acceptance, hidden = _reload_verified_inputs(
        acceptance_path=acceptance_path,
        hidden_manifest_path=hidden_manifest_path,
        maximum_acceptance_bytes=maximum_acceptance_bytes,
        maximum_hidden_manifest_bytes=maximum_hidden_manifest_bytes,
    )
    document = _build_preparation(
        acceptance=acceptance,
        hidden=hidden,
    )
    _validate_structure(document)
    return _freeze(document)


def validate_separation_bakeoff_preparation(
    document: Mapping[str, Any],
    *,
    acceptance_path: str | Path,
    hidden_manifest_path: str | Path,
    maximum_acceptance_bytes: int = MAX_ACCEPTANCE_BYTES,
    maximum_hidden_manifest_bytes: int = MAX_HIDDEN_MANIFEST_BYTES,
) -> Mapping[str, Any]:
    """Reverify both inputs and return an immutable canonical preparation.

    A preparation is not self-sufficient evidence: callers must provide the
    complete frozen acceptance artifact and hidden manifest every time.
    """

    supplied = _plain(_mapping(document, "bake-off preparation"))
    _validate_structure(supplied)
    acceptance, hidden = _reload_verified_inputs(
        acceptance_path=acceptance_path,
        hidden_manifest_path=hidden_manifest_path,
        maximum_acceptance_bytes=maximum_acceptance_bytes,
        maximum_hidden_manifest_bytes=maximum_hidden_manifest_bytes,
    )
    expected = _build_preparation(
        acceptance=acceptance,
        hidden=hidden,
    )
    if supplied != expected:
        raise ValueError(
            "bake-off preparation does not match the reverified frozen inputs"
        )
    return _freeze(supplied)


def load_separation_bakeoff_preparation(
    path: str | Path,
    *,
    acceptance_path: str | Path,
    hidden_manifest_path: str | Path,
    maximum_bytes: int = MAX_BAKEOFF_PREPARATION_BYTES,
    maximum_acceptance_bytes: int = MAX_ACCEPTANCE_BYTES,
    maximum_hidden_manifest_bytes: int = MAX_HIDDEN_MANIFEST_BYTES,
) -> Mapping[str, Any]:
    """Load bounded canonical JSON, then reverify both bound inputs."""

    document, raw = _load_canonical_json(
        path,
        maximum_bytes=maximum_bytes,
        label="separation bake-off preparation",
    )
    checked = validate_separation_bakeoff_preparation(
        document,
        acceptance_path=acceptance_path,
        hidden_manifest_path=hidden_manifest_path,
        maximum_acceptance_bytes=maximum_acceptance_bytes,
        maximum_hidden_manifest_bytes=maximum_hidden_manifest_bytes,
    )
    if raw != canonical_json_bytes(checked):
        raise ValueError(
            "separation bake-off preparation is not canonical JSON"
        )
    return checked


def _reload_verified_inputs(
    *,
    acceptance_path: str | Path,
    hidden_manifest_path: str | Path,
    maximum_acceptance_bytes: int,
    maximum_hidden_manifest_bytes: int,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    acceptance = load_separation_acceptance_thresholds(
        acceptance_path,
        maximum_bytes=maximum_acceptance_bytes,
    )
    hidden = verify_hidden_evaluation_manifest(
        hidden_manifest_path,
        acceptance_artifact=acceptance,
        maximum_bytes=maximum_hidden_manifest_bytes,
    )
    return acceptance, hidden


def _build_preparation(
    *,
    acceptance: Mapping[str, Any],
    hidden: Mapping[str, Any],
) -> dict[str, Any]:
    identities = acceptance["identities"]
    role_ids = sorted(acceptance["role_promotion"])
    resource_ids = [
        item["class_id"]
        for item in acceptance["resource_gates"]["mac_classes"]
    ]
    downstream = {
        role_id: identities["downstream_midi_by_role"][role_id][
            "identity_id"
        ]
        for role_id in role_ids
    }
    acceptance_binding = {
        "schema": acceptance["schema"],
        "status": acceptance["status"],
        "profile_id": acceptance["profile_id"],
        "artifact_sha256": acceptance["artifact_sha256"],
        "canonical_document_sha256": hashlib.sha256(
            canonical_json_bytes(acceptance)
        ).hexdigest(),
    }
    hidden_binding = {
        "schema": SEPARATION_HIDDEN_MANIFEST_SCHEMA,
        "manifest_sha256": hidden["manifest_sha256"],
        "split_sha256": hidden["split_sha256"],
        "total_songs": hidden["total_songs"],
        "groups": {
            group: hidden["groups"][group]
            for group in sorted(_GROUP_FIELDS)
        },
        "ground_truth_pairs_by_role": {
            role_id: hidden["ground_truth_pairs_by_role"][role_id]
            for role_id in role_ids
        },
    }
    orchestration = {
        "protocol": SEPARATION_BAKEOFF_ORCHESTRATION_PROTOCOL,
        "arms": [
            {
                "order": 1,
                "arm_id": "baseline",
                "separator_identity_id": identities[
                    "baseline_separator"
                ]["identity_id"],
            },
            {
                "order": 2,
                "arm_id": "candidate",
                "separator_identity_id": identities[
                    "candidate_separator"
                ]["identity_id"],
            },
        ],
        "role_prepared_ids": role_ids,
        "downstream_midi_identity_by_role": downstream,
        "metric_evaluator_identity_id": identities["metric_evaluator"][
            "identity_id"
        ],
        "resource_class_ids": resource_ids,
        "gate_ids": list(_GATE_IDS),
        "paired_unit": acceptance["hidden_evaluation_set"]["unit"],
        "aggregate_policy": next(
            iter(acceptance["role_promotion"].values())
        )["aggregate_policy"],
    }
    effects = {field_name: False for field_name in sorted(_EFFECT_FIELDS)}
    identity_payload = {
        "schema": SEPARATION_BAKEOFF_PREPARATION_SCHEMA,
        "status": SEPARATION_BAKEOFF_PREPARATION_STATUS,
        "acceptance": acceptance_binding,
        "hidden_evaluation": hidden_binding,
        "orchestration": orchestration,
        "effects": effects,
    }
    preparation_id = (
        "separation-bakeoff-preparation:"
        + hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
    )
    document = {
        **identity_payload,
        "preparation_id": preparation_id,
        "preparation_sha256": "",
    }
    document["preparation_sha256"] = (
        separation_bakeoff_preparation_sha256(document)
    )
    return document


def _validate_structure(document: Mapping[str, Any]) -> None:
    _exact_fields(document, _TOP_FIELDS, "bake-off preparation")
    _reject_invalid_tree(document, "bake-off preparation")
    if document["schema"] != SEPARATION_BAKEOFF_PREPARATION_SCHEMA:
        raise ValueError("unsupported separation bake-off preparation schema")
    if document["status"] != SEPARATION_BAKEOFF_PREPARATION_STATUS:
        raise ValueError("bake-off preparation status must be prepared_not_run")
    preparation_id = _text(
        document["preparation_id"], "preparation_id"
    )
    if (
        not _PREPARATION_ID_RE.fullmatch(preparation_id)
        or preparation_id.endswith("0" * 64)
    ):
        raise ValueError("preparation_id is invalid")
    preparation_hash = _sha256(
        document["preparation_sha256"], "preparation_sha256"
    )

    acceptance = _mapping(document["acceptance"], "acceptance")
    _exact_fields(acceptance, _ACCEPTANCE_FIELDS, "acceptance")
    if acceptance["schema"] != SEPARATION_ACCEPTANCE_SCHEMA:
        raise ValueError("preparation acceptance schema is invalid")
    if acceptance["status"] != "frozen":
        raise ValueError("preparation acceptance status must be frozen")
    _safe_id(acceptance["profile_id"], "acceptance.profile_id")
    _sha256(
        acceptance["artifact_sha256"],
        "acceptance.artifact_sha256",
    )
    _sha256(
        acceptance["canonical_document_sha256"],
        "acceptance.canonical_document_sha256",
    )

    hidden = _mapping(document["hidden_evaluation"], "hidden_evaluation")
    _exact_fields(hidden, _HIDDEN_FIELDS, "hidden_evaluation")
    if hidden["schema"] != SEPARATION_HIDDEN_MANIFEST_SCHEMA:
        raise ValueError("hidden evaluation schema is invalid")
    _sha256(
        hidden["manifest_sha256"],
        "hidden_evaluation.manifest_sha256",
    )
    _sha256(
        hidden["split_sha256"],
        "hidden_evaluation.split_sha256",
    )
    total_songs = _positive_integer(
        hidden["total_songs"], "hidden_evaluation.total_songs"
    )
    groups = _mapping(hidden["groups"], "hidden_evaluation.groups")
    _exact_fields(groups, _GROUP_FIELDS, "hidden_evaluation.groups")
    group_total = 0
    for group in sorted(_GROUP_FIELDS):
        group_total += _positive_integer(
            groups[group], f"hidden_evaluation.groups.{group}"
        )
    if group_total != total_songs:
        raise ValueError("hidden aggregate group counts do not sum")
    role_counts = _mapping(
        hidden["ground_truth_pairs_by_role"],
        "hidden_evaluation.ground_truth_pairs_by_role",
    )
    if not role_counts:
        raise ValueError("hidden aggregate role counts must not be empty")
    for role_id, count in role_counts.items():
        _role_id(role_id, "hidden role-count key")
        checked_count = _positive_integer(
            count,
            f"hidden_evaluation.ground_truth_pairs_by_role.{role_id}",
        )
        if checked_count > total_songs:
            raise ValueError("hidden role count exceeds total songs")

    orchestration = _mapping(
        document["orchestration"], "orchestration"
    )
    _exact_fields(
        orchestration, _ORCHESTRATION_FIELDS, "orchestration"
    )
    if (
        orchestration["protocol"]
        != SEPARATION_BAKEOFF_ORCHESTRATION_PROTOCOL
    ):
        raise ValueError("bake-off orchestration protocol is invalid")
    arms = _sequence(orchestration["arms"], "orchestration.arms")
    if len(arms) != 2:
        raise ValueError("bake-off orchestration requires exactly two arms")
    expected_arms = ((1, "baseline"), (2, "candidate"))
    for index, raw_arm in enumerate(arms):
        arm = _mapping(raw_arm, f"orchestration.arms[{index}]")
        _exact_fields(
            arm, _ARM_FIELDS, f"orchestration.arms[{index}]"
        )
        expected_order, expected_id = expected_arms[index]
        order = _positive_integer(
            arm["order"], f"orchestration.arms[{index}].order"
        )
        if order != expected_order or arm["arm_id"] != expected_id:
            raise ValueError(
                "bake-off arms must run baseline before candidate"
            )
        _safe_id(
            arm["separator_identity_id"],
            f"orchestration.arms[{index}].separator_identity_id",
        )
    if (
        arms[0]["separator_identity_id"]
        == arms[1]["separator_identity_id"]
    ):
        raise ValueError("baseline and candidate identities must differ")

    roles = _sequence(
        orchestration["role_prepared_ids"],
        "orchestration.role_prepared_ids",
    )
    checked_roles = [
        _role_id(role, f"orchestration.role_prepared_ids[{index}]")
        for index, role in enumerate(roles)
    ]
    if not checked_roles or checked_roles != sorted(set(checked_roles)):
        raise ValueError("orchestration roles must be sorted and unique")
    if set(role_counts) != set(checked_roles):
        raise ValueError("hidden aggregate roles must match orchestration")
    downstream = _mapping(
        orchestration["downstream_midi_identity_by_role"],
        "orchestration.downstream_midi_identity_by_role",
    )
    if set(downstream) != set(checked_roles):
        raise ValueError("downstream MIDI identities must match roles")
    for role_id in checked_roles:
        _safe_id(
            downstream[role_id],
            f"downstream MIDI identity for {role_id}",
        )
    _safe_id(
        orchestration["metric_evaluator_identity_id"],
        "orchestration.metric_evaluator_identity_id",
    )
    resources = _sequence(
        orchestration["resource_class_ids"],
        "orchestration.resource_class_ids",
    )
    checked_resources = [
        _safe_id(item, f"resource_class_ids[{index}]")
        for index, item in enumerate(resources)
    ]
    if (
        not checked_resources
        or checked_resources != sorted(set(checked_resources))
    ):
        raise ValueError("resource class IDs must be sorted and unique")
    gates = _sequence(orchestration["gate_ids"], "orchestration.gate_ids")
    if tuple(gates) != _GATE_IDS:
        raise ValueError("bake-off gate IDs must be the fixed conjunction")
    if orchestration["paired_unit"] != "unique-song-role-pair":
        raise ValueError("bake-off paired unit is invalid")
    if orchestration["aggregate_policy"] != (
        "median-over-eligible-song-role-pairs-v1"
    ):
        raise ValueError("bake-off aggregate policy is invalid")

    effects = _mapping(document["effects"], "effects")
    _exact_fields(effects, _EFFECT_FIELDS, "effects")
    for field_name in _EFFECT_FIELDS:
        if effects[field_name] is not False:
            raise ValueError(
                f"preparation effect {field_name} must be false"
            )

    expected_id_payload = {
        "schema": document["schema"],
        "status": document["status"],
        "acceptance": _plain(acceptance),
        "hidden_evaluation": _plain(hidden),
        "orchestration": _plain(orchestration),
        "effects": _plain(effects),
    }
    expected_id = (
        "separation-bakeoff-preparation:"
        + hashlib.sha256(
            canonical_json_bytes(expected_id_payload)
        ).hexdigest()
    )
    if preparation_id != expected_id:
        raise ValueError("preparation_id does not match its bound plan")
    expected_hash = separation_bakeoff_preparation_sha256(document)
    if preparation_hash != expected_hash:
        raise ValueError(
            "preparation_sha256 does not match bake-off preparation"
        )


def _load_canonical_json(
    path: str | Path,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 1
    ):
        raise ValueError("maximum_bytes must be a positive integer")
    file_path = Path(path)
    try:
        path_stat = file_path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is missing") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(
        path_stat.st_mode
    ):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if path_stat.st_size < 2 or path_stat.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its byte bound")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(file_path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != path_stat.st_dev
            or opened.st_ino != path_stat.st_ino
        ):
            raise ValueError(f"{label} changed while opening")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum_bytes:
            raise ValueError(f"{label} exceeds its byte bound")
        finished = os.fstat(descriptor)
        if (
            finished.st_size != len(raw)
            or finished.st_mtime_ns != opened.st_mtime_ns
        ):
            raise ValueError(f"{label} changed while reading")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value, raw


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _reject_invalid_tree(value: Any, label: str) -> None:
    if value is None:
        raise ValueError(f"{label} must not contain null")
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (
            value == 0.0 and math.copysign(1.0, value) < 0.0
        ):
            raise ValueError(
                f"{label} must contain finite canonical numbers"
            )
        return
    if isinstance(value, str):
        text = _text(value, label)
        folded = text.casefold()
        if (
            folded in _FORBIDDEN_TEXT
            or "placeholder" in folded
            or "${" in text
        ):
            raise ValueError(f"{label} contains placeholder text")
        return
    if isinstance(value, Mapping):
        if not value:
            raise ValueError(f"{label} must not contain empty objects")
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    f"{label} object keys must be non-empty strings"
                )
            if unicodedata.normalize("NFC", key) != key:
                raise ValueError(
                    f"{label} object keys must use NFC-normalized text"
                )
            _reject_invalid_tree(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError(f"{label} must not contain empty arrays")
        for index, item in enumerate(value):
            _reject_invalid_tree(item, f"{label}[{index}]")
        return
    raise ValueError(f"{label} contains an unsupported value")


def _exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = set(value)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise ValueError(
            f"{label} fields are invalid (missing={missing}, extra={extra})"
        )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)) or isinstance(value, str):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if not value or value != value.strip() or len(value) > 512:
        raise ValueError(f"{label} must be bounded non-blank text")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} must not contain control characters")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{label} must use NFC-normalized text")
    _reject_private_path_or_url(value, label)
    return value


def _reject_private_path_or_url(value: str, label: str) -> None:
    folded = value.casefold()
    embedded_private_roots = (
        ":/applications/",
        ":/home/",
        ":/library/",
        ":/private/",
        ":/tmp/",
        ":/users/",
        ":/var/",
        ":/volumes/",
    )
    if (
        value.startswith(("/", "~", "./", "../"))
        or _WINDOWS_ABSOLUTE_PATH_RE.match(value)
        or "://" in value
        or folded.startswith("file:")
        or "/users/" in folded
        or "\\users\\" in folded
        or any(root in folded for root in embedded_private_roots)
    ):
        raise ValueError(f"{label} must not contain a private path or URL")


def _safe_id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SAFE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a safe identifier")
    return text


def _role_id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _ROLE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a role-prepared ID")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SHA256_RE.fullmatch(text) or set(text) == {"0"}:
        raise ValueError(f"{label} must be a non-zero lowercase SHA-256")
    return text


def _positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
            if unicodedata.normalize("NFC", key) != key:
                raise ValueError("object keys must use NFC-normalized text")
            result[key] = _plain(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(value[key]) for key in sorted(value)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


__all__ = [
    "MAX_BAKEOFF_PREPARATION_BYTES",
    "SEPARATION_BAKEOFF_ORCHESTRATION_PROTOCOL",
    "SEPARATION_BAKEOFF_PREPARATION_SCHEMA",
    "SEPARATION_BAKEOFF_PREPARATION_STATUS",
    "load_separation_bakeoff_preparation",
    "prepare_separation_bakeoff",
    "separation_bakeoff_preparation_sha256",
    "validate_separation_bakeoff_preparation",
]
