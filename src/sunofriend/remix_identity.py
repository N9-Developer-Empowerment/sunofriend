"""Bounded identity-anchor contracts for deterministic remix comparisons."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import document_sha256


REMIX_IDENTITY_STATE_SCHEMA = "sunofriend.remix-identity-state.v0"
REMIX_REQUEST_SCHEMA = "sunofriend.bounded-remix-request.v0"
REMIX_RESULT_SCHEMA = "sunofriend.bounded-remix-result.v0"
REMIX_REVIEW_SCHEMA = "sunofriend.bounded-remix-review.v0"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FIXED_FACTORS = [
    "source_audio_bytes",
    "clock",
    "duration",
    "channel_geometry",
    "all_non_target_sources",
]


def create_remix_identity_state(
    musical_state: Mapping[str, Any],
    *,
    separation_estimates: Sequence[Mapping[str, Any]],
    owner_anchors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind explicit owner identity labels to hash-only separation estimates."""

    state = validate_musical_state(musical_state)
    estimates = [_validate_estimate(dict(item)) for item in separation_estimates]
    if not estimates:
        raise ValueError("remix identity state requires a separation estimate")
    _unique(estimates, "source_estimate_id", "separation estimate")
    by_estimate = {row["source_estimate_id"]: row for row in estimates}
    anchors = [_validate_anchor(dict(item), by_estimate) for item in owner_anchors]
    if not anchors:
        raise ValueError("remix identity state requires an explicit owner anchor")
    _unique(anchors, "anchor_id", "owner anchor")
    document: dict[str, Any] = {
        "schema": REMIX_IDENTITY_STATE_SCHEMA,
        "status": "complete_owner_anchored_no_remix",
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "method_natures": ["D", "H"],
        "separation_estimates": estimates,
        "owner_anchors": anchors,
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": _identity_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_identity_state(document, state)


def validate_remix_identity_state(
    identity_state: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate an identity state against the exact Musical State."""

    state = validate_musical_state(musical_state)
    document = dict(identity_state)
    _verify_document(document, REMIX_IDENTITY_STATE_SCHEMA, "remix identity state")
    if document.get("status") != "complete_owner_anchored_no_remix":
        raise ValueError("remix identity state status is unsupported")
    if document.get("binding") != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }:
        raise ValueError("remix identity state does not bind this musical state hash")
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError(
            "remix identity state must declare deterministic and human work"
        )
    estimates_value = document.get("separation_estimates")
    if not isinstance(estimates_value, list) or not estimates_value:
        raise ValueError("remix identity state requires separation estimates")
    estimates = [
        _validate_estimate(dict(_mapping(row, "estimate"))) for row in estimates_value
    ]
    _unique(estimates, "source_estimate_id", "separation estimate")
    by_estimate = {row["source_estimate_id"]: row for row in estimates}
    anchors_value = document.get("owner_anchors")
    if not isinstance(anchors_value, list) or not anchors_value:
        raise ValueError("remix identity state requires explicit owner anchors")
    anchors = [
        _validate_anchor(dict(_mapping(row, "owner anchor")), by_estimate)
        for row in anchors_value
    ]
    _unique(anchors, "anchor_id", "owner anchor")
    if estimates != estimates_value or anchors != anchors_value:
        raise ValueError("remix identity state evidence changed")
    _require_false_flags(document)
    if document.get("effects") != _identity_effects():
        raise ValueError("remix identity state cannot create remix effects")
    _reject_paths(document)
    return document


def create_remix_request(
    identity_state: Mapping[str, Any],
    *,
    anchor_id: str,
    source_estimate_id: str,
    delta_envelope_points: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Plan one deterministic gain-delta envelope against one estimate."""

    identity = _validated_identity_without_state(identity_state)
    anchor = _row_by_id(identity["owner_anchors"], "anchor_id", anchor_id, "anchor")
    estimate = _row_by_id(
        identity["separation_estimates"],
        "source_estimate_id",
        source_estimate_id,
        "separation estimate",
    )
    if anchor["source_estimate_id"] != source_estimate_id:
        raise ValueError("request anchor does not bind the target separation estimate")
    points = _validate_points(delta_envelope_points, anchor["geometry"])
    operation = {
        "operation": "apply_gain_delta_envelope",
        "source_estimate_id": source_estimate_id,
        "anchor_id": anchor_id,
        "start_frame": anchor["geometry"]["start_frame"],
        "end_frame": anchor["geometry"]["end_frame"],
        "points": points,
    }
    document: dict[str, Any] = {
        "schema": REMIX_REQUEST_SCHEMA,
        "status": "planned_deterministic_one_variable_remix",
        "binding": {
            "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
            "identity_state_sha256": identity["document_sha256"],
            "musical_state_sha256": identity["binding"]["musical_state_sha256"],
        },
        "method_natures": ["D"],
        "operation_count": 1,
        "one_variable_policy": "gain_delta_envelope_only",
        "fixed_factors": list(_FIXED_FACTORS),
        "operations": [operation],
        "target_estimate_geometry": dict(estimate["geometry"]),
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": _request_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_request(document, identity)


def validate_remix_request(
    remix_request: Mapping[str, Any], identity_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one-variable deterministic remix authority."""

    identity = _validated_identity_without_state(identity_state)
    document = dict(remix_request)
    _verify_document(document, REMIX_REQUEST_SCHEMA, "remix request")
    if document.get("status") != "planned_deterministic_one_variable_remix":
        raise ValueError("remix request status is unsupported")
    if document.get("binding") != {
        "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
        "identity_state_sha256": identity["document_sha256"],
        "musical_state_sha256": identity["binding"]["musical_state_sha256"],
    }:
        raise ValueError("remix request binding or identity state hash changed")
    if document.get("method_natures") != ["D"]:
        raise ValueError("remix request must be deterministic")
    if document.get("operation_count") != 1:
        raise ValueError("remix request must contain exactly one operation")
    operations = document.get("operations")
    if not isinstance(operations, list) or len(operations) != 1:
        raise ValueError("remix request must contain exactly one operation")
    operation = dict(_mapping(operations[0], "remix operation"))
    allowed = {
        "operation",
        "source_estimate_id",
        "anchor_id",
        "start_frame",
        "end_frame",
        "points",
    }
    if (
        set(operation) != allowed
        or operation.get("operation") != "apply_gain_delta_envelope"
    ):
        raise ValueError("unsupported second variable in delta envelope operation")
    anchor = _row_by_id(
        identity["owner_anchors"], "anchor_id", operation.get("anchor_id"), "anchor"
    )
    estimate = _row_by_id(
        identity["separation_estimates"],
        "source_estimate_id",
        operation.get("source_estimate_id"),
        "separation estimate",
    )
    if anchor["source_estimate_id"] != estimate["source_estimate_id"]:
        raise ValueError("remix request anchor and estimate geometry do not match")
    geometry = anchor["geometry"]
    if (
        operation.get("start_frame") != geometry["start_frame"]
        or operation.get("end_frame") != geometry["end_frame"]
    ):
        raise ValueError("remix request operation geometry changed from anchor frames")
    points = _validate_points(operation.get("points", []), geometry)
    expected_operation = {**operation, "points": points}
    if operation != expected_operation:
        raise ValueError("remix request delta envelope changed")
    if document.get("target_estimate_geometry") != estimate["geometry"]:
        raise ValueError("remix request target geometry changed")
    if document.get("one_variable_policy") != "gain_delta_envelope_only":
        raise ValueError("remix request one-variable policy changed")
    if document.get("fixed_factors") != _FIXED_FACTORS:
        raise ValueError("remix request fixed factors changed")
    _require_false_flags(document)
    if document.get("effects") != _request_effects():
        raise ValueError("planned remix request cannot claim rendered effects")
    _reject_paths(document)
    return document


def create_remix_result(
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    output_audio_sha256: str,
    output_audio_bytes: int,
    output_geometry: Mapping[str, Any],
) -> dict[str, Any]:
    """Record one unreviewed deterministic derivative by identity only."""

    identity = _validated_identity_without_state(identity_state)
    request = validate_remix_request(remix_request, identity)
    output = _validate_output(
        output_audio_sha256, output_audio_bytes, dict(output_geometry)
    )
    if output["geometry"] != request["target_estimate_geometry"]:
        raise ValueError("remix result output geometry or frames changed")
    document: dict[str, Any] = {
        "schema": REMIX_RESULT_SCHEMA,
        "status": "complete_unreviewed_deterministic_remix",
        "binding": {
            "identity_state_sha256": identity["document_sha256"],
            "musical_state_sha256": identity["binding"]["musical_state_sha256"],
            "remix_request_schema": REMIX_REQUEST_SCHEMA,
            "remix_request_sha256": request["document_sha256"],
        },
        "method_natures": ["D"],
        "output": output,
        "review_status": "not_reviewed",
        "owner_identity_preserved": None,
        "selected_for_product": False,
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": _result_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_result(document, request, identity)


def validate_remix_result(
    remix_result: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an exact unreviewed result against its request."""

    identity = _validated_identity_without_state(identity_state)
    request = validate_remix_request(remix_request, identity)
    document = dict(remix_result)
    _verify_document(document, REMIX_RESULT_SCHEMA, "remix result")
    if document.get("binding") != {
        "identity_state_sha256": identity["document_sha256"],
        "musical_state_sha256": identity["binding"]["musical_state_sha256"],
        "remix_request_schema": REMIX_REQUEST_SCHEMA,
        "remix_request_sha256": request["document_sha256"],
    }:
        raise ValueError("remix result request binding or SHA-256 changed")
    if document.get("status") != "complete_unreviewed_deterministic_remix":
        raise ValueError("remix result must remain complete and unreviewed")
    if document.get("method_natures") != ["D"]:
        raise ValueError("remix result must remain deterministic")
    output_row = _mapping(document.get("output"), "remix output")
    output = _validate_output(
        str(output_row.get("audio_sha256", "")),
        output_row.get("audio_bytes"),
        dict(_mapping(output_row.get("geometry"), "output geometry")),
    )
    if (
        output != output_row
        or output["geometry"] != request["target_estimate_geometry"]
    ):
        raise ValueError("remix result output geometry or frames changed")
    if (
        document.get("review_status") != "not_reviewed"
        or document.get("owner_identity_preserved") is not None
        or document.get("selected_for_product") is not False
    ):
        raise ValueError(
            "unreviewed remix result cannot claim owner identity or selection"
        )
    _require_false_flags(document)
    if document.get("effects") != _result_effects():
        raise ValueError("remix result effects changed")
    _reject_paths(document)
    return document


def create_remix_review(
    remix_result: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    owner_anchor_labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Record explicit owner listening labels without selecting a product result."""

    identity = _validated_identity_without_state(identity_state)
    request = validate_remix_request(remix_request, identity)
    result = validate_remix_result(remix_result, request, identity)
    labels = _validate_owner_labels(owner_anchor_labels, identity)
    document: dict[str, Any] = {
        "schema": REMIX_REVIEW_SCHEMA,
        "status": "complete_explicit_owner_review_no_selection",
        "method_natures": ["H"],
        "binding": {
            "identity_state_sha256": identity["document_sha256"],
            "musical_state_sha256": identity["binding"]["musical_state_sha256"],
            "remix_request_sha256": request["document_sha256"],
            "remix_result_schema": REMIX_RESULT_SCHEMA,
            "remix_result_sha256": result["document_sha256"],
        },
        "owner_anchor_labels": labels,
        "label_authority": "explicit_owner_listening_decision",
        "playback_inference_permitted": False,
        "model_used": False,
        "training_used": False,
        "selected_for_product": False,
        "training_eligible": False,
        "effects": _review_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_review(document, result, request, identity)


def validate_remix_review(
    remix_review: Mapping[str, Any],
    remix_result: Mapping[str, Any],
    remix_request: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate explicit review labels against exact artifacts."""

    identity = _validated_identity_without_state(identity_state)
    request = validate_remix_request(remix_request, identity)
    result = validate_remix_result(remix_result, request, identity)
    document = dict(remix_review)
    _verify_document(document, REMIX_REVIEW_SCHEMA, "remix review")
    if document.get("binding") != {
        "identity_state_sha256": identity["document_sha256"],
        "musical_state_sha256": identity["binding"]["musical_state_sha256"],
        "remix_request_sha256": request["document_sha256"],
        "remix_result_schema": REMIX_RESULT_SCHEMA,
        "remix_result_sha256": result["document_sha256"],
    }:
        raise ValueError("remix review result binding or SHA-256 changed")
    if document.get("status") != "complete_explicit_owner_review_no_selection":
        raise ValueError("remix review status is unsupported")
    if document.get("method_natures") != ["H"]:
        raise ValueError("remix review must declare explicit human work")
    labels = _validate_owner_labels(document.get("owner_anchor_labels", []), identity)
    if labels != document.get("owner_anchor_labels"):
        raise ValueError("owner anchor labels changed")
    if (
        document.get("label_authority") != "explicit_owner_listening_decision"
        or document.get("playback_inference_permitted") is not False
    ):
        raise ValueError("review labels require explicit owner authority, not playback")
    if document.get("selected_for_product") is not False:
        raise ValueError("remix review cannot select a product result")
    if document.get("training_eligible") is not False:
        raise ValueError("single remix review is not training eligible")
    _require_false_flags(document)
    if (
        document.get("effects") != _review_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError("remix review cannot claim downstream effects")
    _reject_paths(document)
    return document


def _validated_identity_without_state(
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    document = dict(identity_state)
    _verify_document(document, REMIX_IDENTITY_STATE_SCHEMA, "remix identity state")
    if document.get("status") != "complete_owner_anchored_no_remix":
        raise ValueError("remix identity state status is unsupported")
    binding = _mapping(document.get("binding"), "identity binding")
    if binding.get(
        "musical_state_schema"
    ) != MUSICAL_STATE_SCHEMA or not _SHA256.fullmatch(
        str(binding.get("musical_state_sha256", ""))
    ):
        raise ValueError("remix identity musical state binding is invalid")
    estimates = document.get("separation_estimates")
    if not isinstance(estimates, list) or not estimates:
        raise ValueError("remix identity requires separation estimates")
    checked_estimates = [
        _validate_estimate(dict(_mapping(row, "estimate"))) for row in estimates
    ]
    _unique(checked_estimates, "source_estimate_id", "separation estimate")
    by_estimate = {row["source_estimate_id"]: row for row in checked_estimates}
    anchors = document.get("owner_anchors")
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("remix identity requires owner anchors")
    checked_anchors = [
        _validate_anchor(dict(_mapping(row, "anchor")), by_estimate) for row in anchors
    ]
    _unique(checked_anchors, "anchor_id", "owner anchor")
    _require_false_flags(document)
    if (
        document.get("method_natures") != ["D", "H"]
        or document.get("effects") != _identity_effects()
    ):
        raise ValueError("remix identity authority is unsupported")
    _reject_paths(document)
    return document


def _validate_estimate(row: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "source_estimate_id",
        "source_kind",
        "estimated_role",
        "role_interpretation",
        "audio_sha256",
        "audio_bytes",
        "geometry",
    }
    if set(row) != expected_keys:
        raise ValueError("separation estimate fields are unsupported")
    if (
        row.get("source_kind") != "separation_estimate"
        or row.get("role_interpretation") != "estimate_not_ground_truth"
    ):
        raise ValueError("source must remain a separation estimate, not ground truth")
    if (
        not str(row.get("source_estimate_id", "")).strip()
        or not str(row.get("estimated_role", "")).strip()
    ):
        raise ValueError("separation estimate identity and role are required")
    if not _SHA256.fullmatch(str(row.get("audio_sha256", ""))):
        raise ValueError("separation estimate audio SHA-256 is invalid")
    if (
        isinstance(row.get("audio_bytes"), bool)
        or not isinstance(row.get("audio_bytes"), int)
        or row["audio_bytes"] <= 0
    ):
        raise ValueError("separation estimate audio bytes must be positive")
    row["geometry"] = _validate_audio_geometry(row.get("geometry"))
    return row


def _validate_anchor(
    row: dict[str, Any], estimates: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    expected_keys = {
        "anchor_id",
        "anchor_kind",
        "owner_label",
        "label_authority",
        "source_estimate_id",
        "geometry",
    }
    if set(row) != expected_keys:
        raise ValueError("owner anchor fields are unsupported")
    if (
        row.get("label_authority") != "explicit_owner_label"
        or not str(row.get("owner_label", "")).strip()
    ):
        raise ValueError("anchor requires an explicit owner label")
    estimate_id = str(row.get("source_estimate_id", ""))
    if estimate_id not in estimates:
        raise ValueError("anchor references an unknown separation estimate")
    geometry = dict(_mapping(row.get("geometry"), "anchor geometry"))
    if set(geometry) != {"sample_rate_hz", "start_frame", "end_frame"}:
        raise ValueError("anchor geometry fields are unsupported")
    estimate_geometry = estimates[estimate_id]["geometry"]
    if (
        geometry.get("sample_rate_hz") != estimate_geometry["sample_rate_hz"]
        or isinstance(geometry.get("start_frame"), bool)
        or not isinstance(geometry.get("start_frame"), int)
        or isinstance(geometry.get("end_frame"), bool)
        or not isinstance(geometry.get("end_frame"), int)
        or geometry["start_frame"] < 0
        or geometry["end_frame"] <= geometry["start_frame"]
        or geometry["end_frame"] > estimate_geometry["frames"]
    ):
        raise ValueError("anchor frame geometry is outside the separation estimate")
    row["geometry"] = geometry
    return row


def _validate_points(
    points: Sequence[Mapping[str, Any]], geometry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if (
        not isinstance(points, Sequence)
        or isinstance(points, (str, bytes))
        or len(points) < 2
    ):
        raise ValueError("delta envelope requires at least two points")
    result: list[dict[str, Any]] = []
    for item in points:
        row = dict(_mapping(item, "delta envelope point"))
        if set(row) != {"frame", "delta_db"}:
            raise ValueError("unsupported second variable in delta envelope")
        frame = row.get("frame")
        delta = row.get("delta_db")
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise ValueError("delta envelope frame must be an integer")
        if (
            isinstance(delta, bool)
            or not isinstance(delta, (int, float))
            or not math.isfinite(float(delta))
        ):
            raise ValueError("delta envelope gain must be finite")
        result.append({"frame": frame, "delta_db": float(delta)})
    frames = [row["frame"] for row in result]
    if (
        frames[0] != geometry["start_frame"]
        or frames[-1] != geometry["end_frame"]
        or frames != sorted(frames)
        or len(set(frames)) != len(frames)
    ):
        raise ValueError("delta envelope frame geometry must span the exact anchor")
    return result


def _validate_output(
    sha256: str, byte_count: Any, geometry: dict[str, Any]
) -> dict[str, Any]:
    if not _SHA256.fullmatch(sha256):
        raise ValueError("remix output audio SHA-256 is invalid")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count <= 0
    ):
        raise ValueError("remix output audio bytes must be positive")
    return {
        "audio_sha256": sha256,
        "audio_bytes": byte_count,
        "geometry": _validate_audio_geometry(geometry),
    }


def _validate_audio_geometry(value: Any) -> dict[str, int]:
    row = dict(_mapping(value, "audio geometry"))
    if set(row) != {"sample_rate_hz", "channels", "frames"}:
        raise ValueError("audio geometry fields are unsupported")
    if any(
        isinstance(row.get(key), bool)
        or not isinstance(row.get(key), int)
        or row[key] <= 0
        for key in row
    ):
        raise ValueError("audio geometry values must be positive integers")
    return row


def _validate_owner_labels(
    labels: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if (
        not isinstance(labels, Sequence)
        or isinstance(labels, (str, bytes))
        or not labels
    ):
        raise ValueError("explicit owner anchor labels are required")
    anchors = {row["anchor_id"] for row in identity["owner_anchors"]}
    result = [dict(_mapping(row, "owner anchor label")) for row in labels]
    if {row.get("anchor_id") for row in result} != anchors or len(result) != len(
        anchors
    ):
        raise ValueError("owner anchor labels must cover every explicit anchor")
    for row in result:
        if set(row) != {
            "anchor_id",
            "heard",
            "identity_relationship",
            "musical_usefulness",
        }:
            raise ValueError("owner anchor label fields are unsupported")
        if not isinstance(row["heard"], bool):
            raise ValueError("owner anchor heard label must be explicit")
        if row["identity_relationship"] not in {
            "preserved",
            "partly_preserved",
            "lost",
            "cannot_tell",
        }:
            raise ValueError("owner identity relationship label is unsupported")
        if row["musical_usefulness"] not in {
            "useful",
            "not_useful",
            "equivalent",
            "cannot_tell",
        }:
            raise ValueError("owner musical usefulness label is unsupported")
    return result


def _row_by_id(
    rows: Sequence[Mapping[str, Any]], key: str, value: Any, label: str
) -> Mapping[str, Any]:
    for row in rows:
        if row.get(key) == value:
            return row
    raise ValueError(f"unknown {label}")


def _unique(rows: Sequence[Mapping[str, Any]], key: str, label: str) -> None:
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} identity")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _verify_document(document: Mapping[str, Any], schema: str, label: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"unsupported {label} schema")
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 does not match")


def _require_false_flags(document: Mapping[str, Any]) -> None:
    for key, label in (
        ("model_used", "model"),
        ("training_used", "training"),
        ("network_used", "network"),
    ):
        if document.get(key) is not False:
            raise ValueError(f"bounded deterministic remix cannot use a {label}")


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in {
                "path",
                "absolute_path",
                "source_path",
                "output_path",
            }:
                raise ValueError("portable remix contract must be path-free")
            _reject_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str) and (
        value.startswith(("/", "\\\\"))
        or (len(value) >= 3 and value[1:3] in {":/", ":\\"})
    ):
        raise ValueError("portable remix contract must not contain an absolute path")


def _identity_effects() -> dict[str, bool]:
    return {
        "identity_state_created": False,
        "remix_audio_derivative_rendered": False,
        "human_review_created": False,
        "selection_created": False,
        "training_label_created": False,
    }


def _request_effects() -> dict[str, bool]:
    return {
        "remix_request_created": False,
        "remix_audio_derivative_rendered": False,
        "human_review_created": False,
        "selection_created": False,
        "training_label_created": False,
    }


def _result_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "identity_state_mutated": False,
        "request_mutated": False,
        "remix_audio_derivative_rendered": True,
        "human_review_created": False,
        "selection_created": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }


def _review_effects() -> dict[str, bool]:
    return {
        "result_mutated": False,
        "selection_created": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }


__all__ = [
    "REMIX_IDENTITY_STATE_SCHEMA",
    "REMIX_REQUEST_SCHEMA",
    "REMIX_RESULT_SCHEMA",
    "REMIX_REVIEW_SCHEMA",
    "create_remix_identity_state",
    "create_remix_request",
    "create_remix_result",
    "create_remix_review",
    "validate_remix_identity_state",
    "validate_remix_request",
    "validate_remix_result",
    "validate_remix_review",
]
