"""Validation framing for deterministic fake-worker execution evidence.

The prepared V3 plan is never execution authority.  This module deliberately
does not provide an admitted-envelope encoder or an admission issuer.  The
later Darwin executor must add that surface while it owns the exact live
checkpoint lease/reservation and has remeasured every executable artifact.
Merely constructing or deserializing a V2 envelope never recreates parent
authority.

This module performs no descriptor, filesystem, process, model, network,
audio, publication or quarantine operation.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    plain as _plain,
)
from ._separation_fake_execution_records import (
    _FAKE_EXECUTION_POLICY_ID,
    _SeparationFakeLaunchPlanV3Record,
    _SeparationFakeWorkerResultV2Record,
    _new_separation_fake_worker_result_v2_record,
    _validate_separation_fake_worker_result_v2_record_shape,
)
from ._separation_fake_launch_v2_records import (
    _SeparationFakeLaunchPlanV2Record,
)
from ._separation_fake_transport_records import (
    _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
)


_FAKE_EXECUTION_ENVELOPE_SCHEMA = (
    "sunofriend.separation-fake-transport-envelope.v2"
)
_REQUEST_MAGIC_V2 = b"SFRQv002"
_RESULT_MAGIC_V2 = b"SFRSv002"
_FRAME_HEADER = struct.Struct(">8sQ")
_MAXIMUM_JSON_DEPTH = 32
_MAXIMUM_JSON_NODES = 1_000_000


def _decode_fake_execution_request_frame(
    frame: bytes,
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
) -> _SeparationFakeLaunchPlanV3Record:
    envelope = _decode_frame(
        frame,
        magic=_REQUEST_MAGIC_V2,
        maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        label="fake execution request",
    )
    expected_fields = {
        "schema",
        "policy_id",
        "evidence_scope",
        "status",
        "backend_scope",
        "test_only_execution_permitted",
        "real_separation_permitted",
        "run_nonce",
        "fake_launch_plan_v3_sha256",
        "serialized_envelope_is_parent_authority",
        "fake_launch_plan_v3",
        "envelope_sha256",
    }
    if set(envelope) != expected_fields:
        raise ValueError("fake execution envelope fields are invalid")
    payload = dict(envelope)
    envelope_sha256 = payload.pop("envelope_sha256")
    if (
        envelope["schema"] != _FAKE_EXECUTION_ENVELOPE_SCHEMA
        or envelope["policy_id"] != _FAKE_EXECUTION_POLICY_ID
        or envelope["evidence_scope"] != "private_development"
        or envelope["status"] != "admitted"
        or envelope["backend_scope"]
        != "deterministic_transport_fixture_only"
        or envelope["test_only_execution_permitted"] is not True
        or envelope["real_separation_permitted"] is not False
        or envelope["serialized_envelope_is_parent_authority"] is not False
        or envelope_sha256 != _hash(payload)
    ):
        raise ValueError("fake execution envelope policy is invalid")
    plan = _new_plan(
        envelope["fake_launch_plan_v3"],
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
    )
    if (
        envelope["run_nonce"] != plan["run_nonce"]
        or envelope["fake_launch_plan_v3_sha256"] != plan["plan_sha256"]
    ):
        raise ValueError("fake execution envelope bindings are invalid")
    return plan


def _encode_fake_execution_result_frame(
    fake_worker_result: _SeparationFakeWorkerResultV2Record,
    *,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> bytes:
    result = _validate_separation_fake_worker_result_v2_record_shape(
        fake_worker_result,
        fake_launch_plan_v3=fake_launch_plan_v3,
    )
    return _encode_frame(
        result,
        magic=_RESULT_MAGIC_V2,
        maximum_frame_bytes=_FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        label="fake execution result",
    )


def _decode_fake_execution_result_frame(
    frame: bytes,
    *,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> _SeparationFakeWorkerResultV2Record:
    document = _decode_frame(
        frame,
        magic=_RESULT_MAGIC_V2,
        maximum_frame_bytes=_FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        label="fake execution result",
    )
    return _new_separation_fake_worker_result_v2_record(
        document,
        fake_launch_plan_v3=fake_launch_plan_v3,
    )


def _expected_fake_execution_request_frame_bytes(header: bytes) -> int:
    return _expected_frame_bytes(
        header,
        magic=_REQUEST_MAGIC_V2,
        maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        label="fake execution request",
    )


def _expected_fake_execution_result_frame_bytes(header: bytes) -> int:
    return _expected_frame_bytes(
        header,
        magic=_RESULT_MAGIC_V2,
        maximum_frame_bytes=_FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        label="fake execution result",
    )


def _new_plan(
    document: Mapping[str, Any],
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
) -> _SeparationFakeLaunchPlanV3Record:
    from ._separation_fake_execution_records import (
        _new_prepared_separation_fake_launch_plan_v3_record,
    )

    return _new_prepared_separation_fake_launch_plan_v3_record(
        document,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
    )


def _encode_frame(
    value: Mapping[str, Any],
    *,
    magic: bytes,
    maximum_frame_bytes: int,
    label: str,
) -> bytes:
    if type(value) is not dict:
        value = _plain(value)
    _validate_json_shape(value, label)
    payload = _canonical_json(value)
    maximum_payload_bytes = maximum_frame_bytes - _FRAME_HEADER.size
    if not payload or len(payload) > maximum_payload_bytes:
        raise ValueError(f"{label} payload exceeds maximum bytes")
    return _FRAME_HEADER.pack(magic, len(payload)) + payload


def _decode_frame(
    frame: bytes,
    *,
    magic: bytes,
    maximum_frame_bytes: int,
    label: str,
) -> dict[str, Any]:
    if type(frame) is not bytes:
        raise ValueError(f"{label} frame must be exact bytes")
    expected = _expected_frame_bytes(
        frame[: _FRAME_HEADER.size],
        magic=magic,
        maximum_frame_bytes=maximum_frame_bytes,
        label=label,
    )
    if len(frame) != expected:
        raise ValueError(f"{label} frame is truncated or has trailing bytes")
    payload = frame[_FRAME_HEADER.size :]
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} JSON is invalid") from exc
    if type(document) is not dict:
        raise ValueError(f"{label} JSON must be an object")
    _validate_json_shape(document, label)
    if _canonical_json(document) != payload:
        raise ValueError(f"{label} JSON is not canonical")
    return document


def _expected_frame_bytes(
    header: bytes,
    *,
    magic: bytes,
    maximum_frame_bytes: int,
    label: str,
) -> int:
    if type(header) is not bytes or len(header) != _FRAME_HEADER.size:
        raise ValueError(f"{label} header is incomplete")
    observed_magic, payload_bytes = _FRAME_HEADER.unpack(header)
    if observed_magic != magic:
        raise ValueError(f"{label} magic is invalid")
    maximum_payload_bytes = maximum_frame_bytes - _FRAME_HEADER.size
    if payload_bytes <= 0 or payload_bytes > maximum_payload_bytes:
        raise ValueError(f"{label} payload length exceeds bounds")
    return _FRAME_HEADER.size + payload_bytes


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _validate_json_shape(value: Any, label: str) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAXIMUM_JSON_NODES or depth > _MAXIMUM_JSON_DEPTH:
            raise ValueError(f"{label} JSON structure exceeds bounds")
        if isinstance(current, dict):
            if any(type(key) is not str for key in current):
                raise ValueError(f"{label} contains a non-string field")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend((item, depth + 1) for item in current)
        elif current is not None and type(current) not in {
            bool,
            int,
            float,
            str,
        }:
            raise ValueError(f"{label} contains a non-JSON value")


__all__: list[str] = []
