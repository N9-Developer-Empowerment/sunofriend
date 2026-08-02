"""Fixed model-free fd3/fd4 bootstrap for the Darwin native-owner canary.

The worker consumes the exact private Kim request frame from descriptor 3,
uses the existing readiness/release pipes on descriptors 6 and 7, and writes
the exact private result frame to descriptor 4.  It deliberately does not read
descriptor 5, open any request path, import a model, read audio or use a
network.  This is test evidence only and grants no product execution authority.
"""

# ruff: noqa: E402

from __future__ import annotations

import os


# This is the first effectful user-code action.  Python has already opened this
# fixed script by pathname, which remains an explicit TOCTOU limitation.
for _transport_descriptor in (3, 4, 5, 6, 7):
    os.set_inheritable(_transport_descriptor, False)
del _transport_descriptor

import errno
import fcntl
import hashlib
import json
import re
import resource
import stat
import struct
from typing import Any


_REQUEST_MAGIC = b"SFMNREQ1"
_RESULT_MAGIC = b"SFMNRES1"
_FRAME_HEADER = struct.Struct(">8sQ")
_REQUEST_MAXIMUM_BYTES = 65_536
_RESULT_MAXIMUM_BYTES = 2 * 1024 * 1024
_REQUEST_SCHEMA = "sunofriend.private-melroformer-native-request.v1"
_RESULT_SCHEMA = "sunofriend.private-melroformer-native-result.v1"
_POLICY_ID = "private-kim-vocal-2-native-transport-v1"
_READY_SCHEMA = "sunofriend.private-melroformer-worker-ready.v1"
_READY_PHASE = "post_inference_pre_quarantine"
_RELEASE_PROTOCOL = "parent-native-image-inventory-release-v1"
_RELEASE_BYTES = b"sunofriend-native-image-inventory-release-v1\n"
_CHECKPOINT_SHA256 = (
    "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
)
_CHECKPOINT_BYTES = 456_483_463
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_FIELDS = {
    "repository_root",
    "source_root",
    "checkpoint_path",
    "companion_root",
    "authorisation_report_path",
    "staging_directory",
}
_IDENTITY_FIELDS = {
    "worker_source_sha256",
    "checkpoint_sha256",
    "checkpoint_bytes",
    "authorisation_report_sha256",
    "source_manifest_sha256",
    "companion_manifest_sha256",
}
_REQUEST_FIELDS = {
    "schema",
    "policy_id",
    "evidence_scope",
    "status",
    "candidate_id",
    "run_nonce",
    "paths",
    "identities",
    "execution",
    "descriptor_contract",
    "authority",
    "request_sha256",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value} is invalid")


def _is_sha(value: Any) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


def _validate_json_shape(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 1_000_000 or depth > 32:
            raise ValueError("request JSON shape exceeds bounds")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("request JSON keys differ")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif item is None or type(item) in {str, int, float, bool}:
            continue
        else:
            raise ValueError("request contains a non-JSON value")


def _absolute_private_path(value: Any) -> bool:
    components = value.split("/")[1:] if type(value) is str else []
    return bool(
        type(value) is str
        and value != "/"
        and value.startswith("/")
        and "\x00" not in value
        and "://" not in value
        and not any(
            ord(character) < 32 or ord(character) == 127 for character in value
        )
        and not any(component in {"", ".", ".."} for component in components)
        and len(value.encode("utf-8")) <= 4_096
    )


def _read_request_frame() -> dict[str, Any]:
    header = os.pread(3, _FRAME_HEADER.size, 0)
    if len(header) != _FRAME_HEADER.size:
        raise ValueError("request frame is incomplete")
    magic, payload_bytes = _FRAME_HEADER.unpack(header)
    descriptor_state = os.fstat(3)
    if (
        magic != _REQUEST_MAGIC
        or payload_bytes <= 0
        or payload_bytes > _REQUEST_MAXIMUM_BYTES - _FRAME_HEADER.size
        or descriptor_state.st_size != _FRAME_HEADER.size + payload_bytes
    ):
        raise ValueError("request frame boundary differs")
    payload = os.pread(3, payload_bytes, _FRAME_HEADER.size)
    if len(payload) != payload_bytes:
        raise ValueError("request frame is truncated")
    value = json.loads(
        payload,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if type(value) is not dict or _canonical_bytes(value) != payload:
        raise ValueError("request JSON is not canonical")
    _validate_json_shape(value)
    return _validate_request(value)


def _validate_request(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != _REQUEST_FIELDS:
        raise ValueError("request fields differ")
    unsigned = dict(value)
    digest = unsigned.pop("request_sha256")
    if (
        not _is_sha(digest)
        or digest != hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
        or value["schema"] != _REQUEST_SCHEMA
        or value["policy_id"] != _POLICY_ID
        or value["evidence_scope"] != "private_local_evaluation"
        or value["status"] != "prepared_not_execution_authority"
        or value["candidate_id"] != "mlx-melroformer-kim-vocal-2"
        or not _is_sha(value["run_nonce"])
        or value["run_nonce"] == "0" * 64
    ):
        raise ValueError("request identity differs")
    paths = value["paths"]
    if (
        type(paths) is not dict
        or set(paths) != _PATH_FIELDS
        or not all(_absolute_private_path(path) for path in paths.values())
        or len(set(paths.values())) != len(paths)
    ):
        raise ValueError("request paths differ")
    identities = value["identities"]
    if (
        type(identities) is not dict
        or set(identities) != _IDENTITY_FIELDS
        or any(
            not _is_sha(identities[key]) or identities[key] == "0" * 64
            for key in _IDENTITY_FIELDS - {"checkpoint_bytes"}
        )
        or identities["checkpoint_sha256"] != _CHECKPOINT_SHA256
        or identities["checkpoint_bytes"] != _CHECKPOINT_BYTES
    ):
        raise ValueError("request identities differ")
    execution = value["execution"]
    if type(execution) is not dict or execution != {
        "action": "authorised_excerpt",
        "device": execution.get("device"),
        "sample_rate": 44_100,
        "maximum_source_frames": 661_500,
        "bind_python_import_closure": True,
        "observe_outbound_attempts": True,
        "bind_native_image_inventory": True,
        "bind_real_worker_supervision": True,
    } or execution.get("device") not in {"cpu", "gpu"}:
        raise ValueError("request execution differs")
    if value["descriptor_contract"] != {
        "logical_descriptors": [3, 4, 5, 6, 7],
        "request_read_fd": 3,
        "result_write_fd": 4,
        "checkpoint_read_fd": 5,
        "ready_write_fd": 6,
        "release_read_fd": 7,
        "first_user_code_action": "set_fd34567_noninheritable",
        "request_maximum_bytes": _REQUEST_MAXIMUM_BYTES,
        "result_maximum_bytes": _RESULT_MAXIMUM_BYTES,
        "ready_schema": _READY_SCHEMA,
        "release_protocol": _RELEASE_PROTOCOL,
    }:
        raise ValueError("request descriptor contract differs")
    if value["authority"] != {
        "serialized_request_is_execution_authority": False,
        "parent_live_native_admission_required": True,
        "publication_permitted": False,
        "automatic_selection_permitted": False,
        "product_route_permitted": False,
    }:
        raise ValueError("request authority differs")
    return value


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise RuntimeError("bootstrap pipe write made no progress")
        offset += written


def _read_release() -> bytes:
    received = bytearray()
    try:
        while len(received) <= len(_RELEASE_BYTES):
            block = os.read(7, len(_RELEASE_BYTES) + 1 - len(received))
            if not block:
                break
            received.extend(block)
    finally:
        os.close(7)
    return bytes(received)


def _open_descriptors() -> list[int]:
    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit == resource.RLIM_INFINITY:
        soft_limit = 1_048_576
    result: list[int] = []
    for descriptor in range(int(soft_limit)):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        result.append(descriptor)
    return result


def _write_result_frame(result: dict[str, Any]) -> None:
    payload = _canonical_bytes(result)
    if not payload or len(payload) > _RESULT_MAXIMUM_BYTES - _FRAME_HEADER.size:
        raise RuntimeError("bootstrap result exceeds its bound")
    frame = _FRAME_HEADER.pack(_RESULT_MAGIC, len(payload)) + payload
    offset = 0
    while offset < len(frame):
        written = os.pwrite(4, frame[offset:], offset)
        if written <= 0:
            raise RuntimeError("bootstrap result write made no progress")
        offset += written
    os.ftruncate(4, len(frame))


def _build_result(request: dict[str, Any], ready_bytes: bytes) -> dict[str, Any]:
    checkpoint_state = os.fstat(5)
    child = {
        "schema": "sunofriend.private-melroformer-native-bootstrap-child.v1",
        "status": "model_free_frame_bootstrap_complete",
        "request_frame_validated": True,
        "request_paths_opened": False,
        "request_paths_retained": False,
        "checkpoint_descriptor_regular": stat.S_ISREG(checkpoint_state.st_mode),
        "checkpoint_descriptor_bytes_read": 0,
        "ready_release_completed": True,
        "ready_sha256": hashlib.sha256(ready_bytes).hexdigest(),
        "release_sha256": hashlib.sha256(_RELEASE_BYTES).hexdigest(),
        "open_descriptors_after_handshake": _open_descriptors(),
        "model_imported": False,
        "checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
        "product_authority_granted": False,
    }
    child_hash = hashlib.sha256(_canonical_bytes(child)).hexdigest()
    payload = {
        "schema": _RESULT_SCHEMA,
        "policy_id": _POLICY_ID,
        "evidence_scope": "private_parent_verification_only",
        "status": "worker_complete_parent_verification_required",
        "candidate_id": request["candidate_id"],
        "run_nonce": request["run_nonce"],
        "request_sha256": request["request_sha256"],
        "evidence_authority": "worker_claim_not_parent_verification",
        "private_process_identity": {
            "pid": os.getpid(),
            "pgid": os.getpgrp(),
        },
        "child_result": child,
        "child_result_sha256": child_hash,
        "paths_retained": False,
        "product_authority_granted": False,
    }
    return {
        **payload,
        "result_sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
    }


def main() -> int:
    try:
        request = _read_request_frame()
        if os.getpgrp() != os.getpid():
            return 71
        ready = {
            "schema": _READY_SCHEMA,
            "phase": _READY_PHASE,
            "candidate_id": request["candidate_id"],
            "checkpoint_sha256": request["identities"]["checkpoint_sha256"],
            "authorised_audio_sha256": request["identities"][
                "source_manifest_sha256"
            ],
            "source_frames": 1,
            "vocal_float32_sha256": hashlib.sha256(
                b"model-free-native-frame-bootstrap-vocals"
            ).hexdigest(),
            "instrumental_float32_sha256": hashlib.sha256(
                b"model-free-native-frame-bootstrap-instrumental"
            ).hexdigest(),
            "release_protocol": _RELEASE_PROTOCOL,
        }
        ready_bytes = _canonical_bytes(ready) + b"\n"
        try:
            _write_all(6, ready_bytes)
        finally:
            os.close(6)
        if _read_release() != _RELEASE_BYTES:
            return 72
        _write_result_frame(_build_result(request, ready_bytes))
        return 0
    except (OSError, RuntimeError, TypeError, ValueError, UnicodeError):
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
