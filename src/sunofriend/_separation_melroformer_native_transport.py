"""Pure framed-value contract for a future native-owned Kim worker.

This module defines the bounded private request and result carried on logical
descriptors 3 and 4.  A request may contain local absolute paths because it is
private worker input; a result must be path-free.  Neither value is execution
authority.  The parent must still own the exact native child, checkpoint lease,
artifact measurements, sandbox observers and one fresh admission decision.

The module performs no filesystem, descriptor, process, model, network or
audio operation.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from ._separation_worker_ready_handshake import (
    READY_SCHEMA,
    RELEASE_PROTOCOL,
)


REQUEST_SCHEMA = "sunofriend.private-melroformer-native-request.v1"
RESULT_SCHEMA = "sunofriend.private-melroformer-native-result.v1"
POLICY_ID = "private-kim-vocal-2-native-transport-v1"
REQUEST_MAGIC = b"SFMNREQ1"
RESULT_MAGIC = b"SFMNRES1"
REQUEST_MAXIMUM_BYTES = 65_536
RESULT_MAXIMUM_BYTES = 2 * 1024 * 1024
_FRAME_HEADER = struct.Struct(">8sQ")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_NONCE_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_MAXIMUM_JSON_DEPTH = 32
_MAXIMUM_JSON_NODES = 1_000_000
_MAXIMUM_PATH_BYTES = 4_096
_REQUEST_FIELDS = frozenset(
    """
    schema policy_id evidence_scope status candidate_id run_nonce paths
    identities execution descriptor_contract authority request_sha256
    """.split()
)
_PATH_FIELDS = frozenset(
    """
    repository_root source_root checkpoint_path companion_root
    authorisation_report_path staging_directory
    """.split()
)
_IDENTITY_FIELDS = frozenset(
    """
    worker_source_sha256 checkpoint_sha256 checkpoint_bytes
    authorisation_report_sha256 source_manifest_sha256
    companion_manifest_sha256
    """.split()
)
_EXECUTION_FIELDS = frozenset(
    """
    action device sample_rate maximum_source_frames
    bind_python_import_closure observe_outbound_attempts
    bind_native_image_inventory bind_real_worker_supervision
    """.split()
)
_DESCRIPTOR_FIELDS = frozenset(
    """
    logical_descriptors request_read_fd result_write_fd checkpoint_read_fd
    ready_write_fd release_read_fd first_user_code_action
    request_maximum_bytes result_maximum_bytes ready_schema release_protocol
    """.split()
)
_AUTHORITY_FIELDS = frozenset(
    """
    serialized_request_is_execution_authority
    parent_live_native_admission_required publication_permitted
    automatic_selection_permitted product_route_permitted
    """.split()
)
_RESULT_FIELDS = frozenset(
    """
    schema policy_id evidence_scope status candidate_id run_nonce
    request_sha256 evidence_authority private_process_identity child_result
    child_result_sha256 paths_retained product_authority_granted result_sha256
    """.split()
)


def _build_private_melroformer_native_request(
    *,
    run_nonce: str,
    paths: Mapping[str, Any],
    identities: Mapping[str, Any],
    device: str,
) -> Mapping[str, Any]:
    """Build immutable prepared input; the value never grants spawn authority."""

    payload = {
        "schema": REQUEST_SCHEMA,
        "policy_id": POLICY_ID,
        "evidence_scope": "private_local_evaluation",
        "status": "prepared_not_execution_authority",
        "candidate_id": "mlx-melroformer-kim-vocal-2",
        "run_nonce": run_nonce,
        "paths": dict(paths),
        "identities": dict(identities),
        "execution": {
            "action": "authorised_excerpt",
            "device": device,
            "sample_rate": 44_100,
            "maximum_source_frames": 661_500,
            "bind_python_import_closure": True,
            "observe_outbound_attempts": True,
            "bind_native_image_inventory": True,
            "bind_real_worker_supervision": True,
        },
        "descriptor_contract": {
            "logical_descriptors": [3, 4, 5, 6, 7],
            "request_read_fd": 3,
            "result_write_fd": 4,
            "checkpoint_read_fd": 5,
            "ready_write_fd": 6,
            "release_read_fd": 7,
            "first_user_code_action": "set_fd34567_noninheritable",
            "request_maximum_bytes": REQUEST_MAXIMUM_BYTES,
            "result_maximum_bytes": RESULT_MAXIMUM_BYTES,
            "ready_schema": READY_SCHEMA,
            "release_protocol": RELEASE_PROTOCOL,
        },
        "authority": {
            "serialized_request_is_execution_authority": False,
            "parent_live_native_admission_required": True,
            "publication_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
        },
    }
    request = {
        **payload,
        "request_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    return _validate_private_melroformer_native_request(request)


def _encode_private_melroformer_native_request(
    request: Mapping[str, Any],
) -> bytes:
    return _encode_frame(
        _plain(_validate_private_melroformer_native_request(request)),
        magic=REQUEST_MAGIC,
        maximum_bytes=REQUEST_MAXIMUM_BYTES,
        label="MelRoFormer native request",
    )


def _decode_private_melroformer_native_request(frame: bytes) -> Mapping[str, Any]:
    return _validate_private_melroformer_native_request(
        _decode_frame(
            frame,
            magic=REQUEST_MAGIC,
            maximum_bytes=REQUEST_MAXIMUM_BYTES,
            label="MelRoFormer native request",
        )
    )


def _build_private_melroformer_native_result(
    *,
    request: Mapping[str, Any],
    private_process_identity: Mapping[str, Any],
    child_result: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Build private worker output whose process identity must be consumed."""

    checked_request = _plain(
        _validate_private_melroformer_native_request(request)
    )
    child = _json_object(child_result, "MelRoFormer child result")
    _reject_paths(child, "MelRoFormer child result")
    child_hash = hashlib.sha256(_canonical_json(child)).hexdigest()
    payload = {
        "schema": RESULT_SCHEMA,
        "policy_id": POLICY_ID,
        "evidence_scope": "private_parent_verification_only",
        "status": "worker_complete_parent_verification_required",
        "candidate_id": checked_request["candidate_id"],
        "run_nonce": checked_request["run_nonce"],
        "request_sha256": checked_request["request_sha256"],
        "evidence_authority": "worker_claim_not_parent_verification",
        "private_process_identity": dict(private_process_identity),
        "child_result": child,
        "child_result_sha256": child_hash,
        "paths_retained": False,
        "product_authority_granted": False,
    }
    result = {
        **payload,
        "result_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    return _validate_private_melroformer_native_result(
        result,
        request=checked_request,
    )


def _encode_private_melroformer_native_result(
    result: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> bytes:
    return _encode_frame(
        _plain(_validate_private_melroformer_native_result(result, request=request)),
        magic=RESULT_MAGIC,
        maximum_bytes=RESULT_MAXIMUM_BYTES,
        label="MelRoFormer native result",
    )


def _decode_private_melroformer_native_result(
    frame: bytes,
    *,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _validate_private_melroformer_native_result(
        _decode_frame(
            frame,
            magic=RESULT_MAGIC,
            maximum_bytes=RESULT_MAXIMUM_BYTES,
            label="MelRoFormer native result",
        ),
        request=request,
    )


def _validate_private_melroformer_native_request(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _json_object(document, "MelRoFormer native request")
    if set(value) != _REQUEST_FIELDS:
        raise ValueError("MelRoFormer native request fields differ")
    digest = value.pop("request_sha256")
    if (
        not _is_sha(digest)
        or digest != hashlib.sha256(_canonical_json(value)).hexdigest()
        or value["schema"] != REQUEST_SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["evidence_scope"] != "private_local_evaluation"
        or value["status"] != "prepared_not_execution_authority"
        or value["candidate_id"] != "mlx-melroformer-kim-vocal-2"
        or not isinstance(value["run_nonce"], str)
        or _RUN_NONCE_RE.fullmatch(value["run_nonce"]) is None
        or value["run_nonce"] == "0" * 64
    ):
        raise ValueError("MelRoFormer native request identity differs")
    value["paths"] = _validated_paths(value["paths"])
    value["identities"] = _validated_identities(value["identities"])
    value["execution"] = _validated_execution(value["execution"])
    value["descriptor_contract"] = _validated_descriptor_contract(
        value["descriptor_contract"]
    )
    value["authority"] = _validated_authority(value["authority"])
    value["request_sha256"] = digest
    return _freeze(value)


def _validate_private_melroformer_native_result(
    document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    checked_request = _plain(_validate_private_melroformer_native_request(request))
    value = _json_object(document, "MelRoFormer native result")
    if set(value) != _RESULT_FIELDS:
        raise ValueError("MelRoFormer native result fields differ")
    digest = value.pop("result_sha256")
    child = _json_object(value.get("child_result"), "MelRoFormer child result")
    identity = _json_object(
        value.get("private_process_identity"),
        "MelRoFormer private process identity",
    )
    if (
        not _is_sha(digest)
        or digest != hashlib.sha256(_canonical_json(value)).hexdigest()
        or value["schema"] != RESULT_SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["evidence_scope"] != "private_parent_verification_only"
        or value["status"] != "worker_complete_parent_verification_required"
        or value["candidate_id"] != checked_request["candidate_id"]
        or value["run_nonce"] != checked_request["run_nonce"]
        or value["request_sha256"] != checked_request["request_sha256"]
        or value["evidence_authority"] != "worker_claim_not_parent_verification"
        or set(identity) != {"pid", "pgid"}
        or any(type(identity[key]) is not int or identity[key] <= 0 for key in identity)
        or value["child_result_sha256"]
        != hashlib.sha256(_canonical_json(child)).hexdigest()
        or value["paths_retained"] is not False
        or value["product_authority_granted"] is not False
    ):
        raise ValueError("MelRoFormer native result identity differs")
    _reject_paths(child, "MelRoFormer child result")
    value["private_process_identity"] = identity
    value["child_result"] = child
    value["result_sha256"] = digest
    return _freeze(value)


def _validated_paths(value: Any) -> dict[str, str]:
    paths = _json_object(value, "MelRoFormer native paths")
    if set(paths) != _PATH_FIELDS:
        raise ValueError("MelRoFormer native path fields differ")
    checked = {key: _absolute_private_path(item, key) for key, item in paths.items()}
    if len(set(checked.values())) != len(checked):
        raise ValueError("MelRoFormer native paths must be distinct")
    return checked


def _validated_identities(value: Any) -> dict[str, Any]:
    identities = _json_object(value, "MelRoFormer native identities")
    if set(identities) != _IDENTITY_FIELDS:
        raise ValueError("MelRoFormer native identity fields differ")
    for key in _IDENTITY_FIELDS - {"checkpoint_bytes"}:
        if not _is_sha(identities[key]) or identities[key] == "0" * 64:
            raise ValueError("MelRoFormer native artifact identity differs")
    if (
        identities["checkpoint_sha256"] != CONVERSION_CHECKPOINT_SHA256
        or identities["checkpoint_bytes"] != CONVERSION_CHECKPOINT_BYTES
    ):
        raise ValueError("MelRoFormer native checkpoint identity differs")
    return identities


def _validated_execution(value: Any) -> dict[str, Any]:
    execution = _json_object(value, "MelRoFormer native execution")
    if (
        set(execution) != _EXECUTION_FIELDS
        or execution["action"] != "authorised_excerpt"
        or execution["device"] not in {"cpu", "gpu"}
        or execution["sample_rate"] != 44_100
        or execution["maximum_source_frames"] != 661_500
        or any(
            execution[key] is not True
            for key in _EXECUTION_FIELDS
            - {"action", "device", "sample_rate", "maximum_source_frames"}
        )
    ):
        raise ValueError("MelRoFormer native execution policy differs")
    return execution


def _validated_descriptor_contract(value: Any) -> dict[str, Any]:
    descriptor = _json_object(value, "MelRoFormer native descriptor contract")
    expected = {
        "logical_descriptors": [3, 4, 5, 6, 7],
        "request_read_fd": 3,
        "result_write_fd": 4,
        "checkpoint_read_fd": 5,
        "ready_write_fd": 6,
        "release_read_fd": 7,
        "first_user_code_action": "set_fd34567_noninheritable",
        "request_maximum_bytes": REQUEST_MAXIMUM_BYTES,
        "result_maximum_bytes": RESULT_MAXIMUM_BYTES,
        "ready_schema": READY_SCHEMA,
        "release_protocol": RELEASE_PROTOCOL,
    }
    if set(descriptor) != _DESCRIPTOR_FIELDS or descriptor != expected:
        raise ValueError("MelRoFormer native descriptor contract differs")
    return descriptor


def _validated_authority(value: Any) -> dict[str, Any]:
    authority = _json_object(value, "MelRoFormer native authority")
    if set(authority) != _AUTHORITY_FIELDS or authority != {
        "serialized_request_is_execution_authority": False,
        "parent_live_native_admission_required": True,
        "publication_permitted": False,
        "automatic_selection_permitted": False,
        "product_route_permitted": False,
    }:
        raise ValueError("MelRoFormer native authority differs")
    return authority


def _encode_frame(
    value: Mapping[str, Any],
    *,
    magic: bytes,
    maximum_bytes: int,
    label: str,
) -> bytes:
    payload = _canonical_json(value)
    if not payload or len(payload) > maximum_bytes - _FRAME_HEADER.size:
        raise ValueError(f"{label} exceeds its byte bound")
    return _FRAME_HEADER.pack(magic, len(payload)) + payload


def _decode_frame(
    frame: bytes,
    *,
    magic: bytes,
    maximum_bytes: int,
    label: str,
) -> dict[str, Any]:
    if type(frame) is not bytes or len(frame) < _FRAME_HEADER.size:
        raise ValueError(f"{label} frame is incomplete")
    observed_magic, payload_bytes = _FRAME_HEADER.unpack(frame[: _FRAME_HEADER.size])
    if (
        observed_magic != magic
        or payload_bytes <= 0
        or payload_bytes > maximum_bytes - _FRAME_HEADER.size
        or len(frame) != _FRAME_HEADER.size + payload_bytes
    ):
        raise ValueError(f"{label} frame boundary differs")
    payload = frame[_FRAME_HEADER.size :]
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} JSON is invalid") from error
    if type(value) is not dict or _canonical_json(value) != payload:
        raise ValueError(f"{label} JSON is not canonical")
    _validate_json_shape(value, label)
    return value


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    result = _plain(value)
    if type(result) is not dict:
        raise ValueError(f"{label} must be an exact object")
    _validate_json_shape(result, label)
    return result


def _validate_json_shape(value: Any, label: str) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > _MAXIMUM_JSON_NODES or depth > _MAXIMUM_JSON_DEPTH:
            raise ValueError(f"{label} JSON shape exceeds bounds")
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ValueError(f"{label} JSON keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif item is None or type(item) in {str, int, float, bool}:
            continue
        else:
            raise ValueError(f"{label} contains a non-JSON value")


def _absolute_private_path(value: Any, label: str) -> str:
    components = value.split("/")[1:] if type(value) is str else []
    if (
        type(value) is not str
        or value == "/"
        or not value.startswith("/")
        or "\x00" in value
        or "://" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(component in {"", ".", ".."} for component in components)
        or len(value.encode("utf-8")) > _MAXIMUM_PATH_BYTES
    ):
        raise ValueError(f"MelRoFormer native {label} is not an absolute path")
    return value


def _reject_paths(value: Any, label: str) -> None:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, str) and (
            item.startswith("/")
            or _WINDOWS_ABSOLUTE_RE.match(item) is not None
            or item.startswith("file:")
            or item.startswith("www.")
            or "://" in item
        ):
            raise ValueError(f"{label} must be path-free")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value} is invalid")


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


__all__: tuple[str, ...] = ()
