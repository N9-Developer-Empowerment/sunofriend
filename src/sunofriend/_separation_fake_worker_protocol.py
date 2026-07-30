"""Bounded fake-worker framing and parent-only quarantine verification.

This private module is deliberately process-free.  It defines the byte
boundary that a later supervisor may carry over logical FD 3 and FD 4, plus
descriptor-based verification of already-written quarantine files.  It does
not spawn a worker, install FD 5, load a checkpoint, publish an output or
turn historical separation records into execution authority.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import struct
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_fake_transport_records import (
    _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
    _SeparationFakeWorkerResultRecord,
    _new_launch,
    _new_request,
    _new_result,
    _validate_fake_launch_plan_shape,
    _validate_fake_worker_request_shape,
    _validate_fake_worker_result_shape,
)


_REQUEST_MAGIC = b"SFRQv001"
_RESULT_MAGIC = b"SFRSv001"
_FRAME_HEADER = struct.Struct(">8sQ")
_MAXIMUM_JSON_DEPTH = 32
_MAXIMUM_JSON_NODES = 1_000_000
_HASH_CHUNK_BYTES = 1024 * 1024
_QUARANTINE_SCHEMA = "sunofriend.separation-fake-quarantine-verification.v1"
_QUARANTINE_POLICY_ID = "parent-descriptor-observation-v1"
_ENVELOPE_SCHEMA = "sunofriend.separation-fake-transport-envelope.v1"


def _encode_fake_worker_request_frame(
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan: _SeparationFakeLaunchPlanRecord,
) -> bytes:
    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch = _validate_fake_launch_plan_shape(fake_launch_plan)
    if (
        launch["run_nonce"] != request["run_nonce"]
        or launch["fake_worker_request_sha256"]
        != request["request_sha256"]
    ):
        raise ValueError("fake transport envelope records do not match")
    payload = {
        "schema": _ENVELOPE_SCHEMA,
        "run_nonce": request["run_nonce"],
        "fake_worker_request_sha256": request["request_sha256"],
        "fake_launch_plan_sha256": launch["plan_sha256"],
        "fake_worker_request": _plain(request),
        "fake_launch_plan": _plain(launch),
    }
    return _encode_frame(
        {**payload, "envelope_sha256": _hash(payload)},
        magic=_REQUEST_MAGIC,
        maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        label="fake-worker request",
    )


def _decode_fake_worker_request_frame(
    frame: bytes,
) -> tuple[
    _SeparationFakeWorkerRequestRecord,
    _SeparationFakeLaunchPlanRecord,
]:
    envelope = _decode_frame(
        frame,
        magic=_REQUEST_MAGIC,
        maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        label="fake-worker request",
    )
    if set(envelope) != {
        "schema",
        "run_nonce",
        "fake_worker_request_sha256",
        "fake_launch_plan_sha256",
        "fake_worker_request",
        "fake_launch_plan",
        "envelope_sha256",
    }:
        raise ValueError("fake transport envelope fields are invalid")
    payload = dict(envelope)
    envelope_sha256 = payload.pop("envelope_sha256")
    if (
        envelope["schema"] != _ENVELOPE_SCHEMA
        or envelope_sha256 != _hash(payload)
    ):
        raise ValueError("fake transport envelope identity is invalid")
    request = _new_request(envelope["fake_worker_request"])
    launch = _new_launch(envelope["fake_launch_plan"])
    if (
        envelope["run_nonce"] != request["run_nonce"]
        or envelope["run_nonce"] != launch["run_nonce"]
        or envelope["fake_worker_request_sha256"]
        != request["request_sha256"]
        or envelope["fake_launch_plan_sha256"] != launch["plan_sha256"]
        or launch["fake_worker_request_sha256"]
        != request["request_sha256"]
    ):
        raise ValueError("fake transport envelope bindings are invalid")
    return request, launch


def _encode_fake_worker_result_frame(
    fake_worker_result: _SeparationFakeWorkerResultRecord,
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan: _SeparationFakeLaunchPlanRecord,
) -> bytes:
    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch = _validate_fake_launch_plan_shape(fake_launch_plan)
    result = _validate_fake_worker_result_shape(
        fake_worker_result,
        request=request,
        launch=launch,
    )
    return _encode_frame(
        result,
        magic=_RESULT_MAGIC,
        maximum_frame_bytes=_FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        label="fake-worker result",
    )


def _decode_fake_worker_result_frame(
    frame: bytes,
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan: _SeparationFakeLaunchPlanRecord,
) -> _SeparationFakeWorkerResultRecord:
    document = _decode_frame(
        frame,
        magic=_RESULT_MAGIC,
        maximum_frame_bytes=_FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        label="fake-worker result",
    )
    return _new_result(
        document,
        request=fake_worker_request,
        launch=fake_launch_plan,
    )


def _expected_fake_worker_request_frame_bytes(header: bytes) -> int:
    return _expected_frame_bytes(
        header,
        magic=_REQUEST_MAGIC,
        maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        label="fake-worker request",
    )


def _expected_fake_worker_result_frame_bytes(header: bytes) -> int:
    return _expected_frame_bytes(
        header,
        magic=_RESULT_MAGIC,
        maximum_frame_bytes=_FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        label="fake-worker result",
    )


def _verify_fake_worker_quarantine(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan: _SeparationFakeLaunchPlanRecord,
    fake_worker_result: _SeparationFakeWorkerResultRecord,
    quarantine_directory_descriptor: int,
    readable_descriptors: Mapping[str, int],
) -> Mapping[str, Any]:
    """Verify one complete fake result against an exact private directory.

    The directory and file descriptors must be distinct, read-only and
    non-inheritable.  The directory must contain exactly one code-owned name
    per request slot.  Files are matched by device/inode, fully hashed with
    ``pread`` and rechecked by descriptor and directory entry.  No path is
    accepted or returned.
    """

    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch = _validate_fake_launch_plan_shape(fake_launch_plan)
    result = _validate_fake_worker_result_shape(
        fake_worker_result,
        request=request,
        launch=launch,
    )
    if result["status"] != "complete":
        raise ValueError("quarantine verification requires a complete result")
    slots = list(request["output_slots"])
    claims = list(result["outputs"])
    slot_ids = [item["slot_id"] for item in slots]
    if type(readable_descriptors) is not dict:
        raise ValueError("quarantine descriptors must be an exact dictionary")
    descriptors_by_slot = dict(readable_descriptors)
    if set(descriptors_by_slot) != set(slot_ids):
        raise ValueError(
            "quarantine descriptors must cover every exact output slot"
        )
    descriptors = list(descriptors_by_slot.values())
    if (
        any(type(item) is not int or item < 0 for item in descriptors)
        or type(quarantine_directory_descriptor) is not int
        or quarantine_directory_descriptor < 0
        or quarantine_directory_descriptor in descriptors
        or len(set(descriptors)) != len(descriptors)
    ):
        raise ValueError(
            "quarantine descriptors must be distinct non-negative integers"
        )
    directory_before = _verified_quarantine_directory(
        quarantine_directory_descriptor
    )
    expected_names = {f"{item['slot_id']}.wav" for item in slots}
    try:
        observed_names = sorted(os.listdir(quarantine_directory_descriptor))
    except OSError as exc:
        raise ValueError("quarantine directory could not be listed") from exc
    if observed_names != sorted(expected_names):
        raise ValueError(
            "quarantine directory entry observation does not match outputs"
        )
    claims_by_slot = {item["slot_id"]: item for item in claims}

    verified: list[dict[str, Any]] = []
    observed_file_objects: set[tuple[int, int]] = set()
    total_bytes = 0
    for slot in slots:
        slot_id = slot["slot_id"]
        claim = claims_by_slot[slot_id]
        if any(
            claim[key] != slot[key]
            for key in ("slot_id", "role", "artifact_kind")
        ):
            raise ValueError("claimed output does not match its exact slot")
        descriptor = descriptors_by_slot[slot_id]
        name = f"{slot_id}.wav"
        evidence = _verify_one_output(
            descriptor,
            claim,
            directory_descriptor=quarantine_directory_descriptor,
            entry_name=name,
            maximum_bytes=slot["maximum_bytes"],
        )
        file_object = tuple(evidence.pop("_file_object_identity"))
        if file_object in observed_file_objects:
            raise ValueError(
                "quarantine output slots must use distinct file objects"
            )
        observed_file_objects.add(file_object)
        total_bytes += evidence["bytes"]
        verified.append(evidence)

    directory_after = _verified_quarantine_directory(
        quarantine_directory_descriptor
    )
    if _file_identity(directory_before) != _file_identity(directory_after):
        raise ValueError("quarantine directory changed during verification")
    parent_outputs = [
        {
            key: _plain(claim[key])
            for key in (
                "role",
                "slot_id",
                "artifact_kind",
                "sha256",
                "bytes",
                "geometry",
            )
        }
        for claim in claims
    ]
    quarantine_identity_sha256 = _hash(
        {
            "directory_identity_sha256": _identity_sha256(directory_after),
            "fake_worker_request_sha256": request["request_sha256"],
            "fake_launch_plan_sha256": launch["plan_sha256"],
        }
    )
    observed_entry_set_sha256 = _hash(
        [
            {
                "entry_name": f"{item['slot_id']}.wav",
                "file_identity_sha256": item["file_identity_sha256"],
                "sha256": item["sha256"],
                "bytes": item["bytes"],
            }
            for item in verified
        ]
    )
    payload = {
        "schema": _QUARANTINE_SCHEMA,
        "policy_id": _QUARANTINE_POLICY_ID,
        "status": "verified",
        "run_nonce": request["run_nonce"],
        "fake_worker_request_sha256": request["request_sha256"],
        "fake_launch_plan_sha256": launch["plan_sha256"],
        "fake_worker_result_sha256": result["result_sha256"],
        "publication_permitted": False,
        "selection_permitted": False,
        "ordinary_file_immutable_backing_proven": False,
        "quarantine_identity_sha256": quarantine_identity_sha256,
        "observed_entry_set_sha256": observed_entry_set_sha256,
        "output_count": len(verified),
        "total_bytes": total_bytes,
        "outputs": verified,
        "parent_outputs": parent_outputs,
        "limitations": [
            "verification_is_one_parent_observation",
            "ordinary_files_can_change_after_verification",
            "fresh_quarantine_and_exact_tree_are_not_proven",
            "verification_does_not_authorize_publication",
        ],
    }
    return _freeze(
        {
            **payload,
            "verification_sha256": _hash(payload),
        }
    )


def _encode_frame(
    document: Mapping[str, Any],
    *,
    magic: bytes,
    maximum_frame_bytes: int,
    label: str,
) -> bytes:
    if not isinstance(document, Mapping):
        raise ValueError(f"{label} must be an object")
    value = _plain(document)
    _validate_json_shape(value, label)
    try:
        payload = _canonical_json(
            value,
            error_message=f"{label} must contain canonical JSON values",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{label} must contain canonical JSON values"
        ) from exc
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
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} payload is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} payload must be an object")
    _validate_json_shape(value, label)
    if _canonical_json(value) != payload:
        raise ValueError(f"{label} payload is not canonical JSON")
    return value


def _expected_frame_bytes(
    header: bytes,
    *,
    magic: bytes,
    maximum_frame_bytes: int,
    label: str,
) -> int:
    if type(header) is not bytes or len(header) != _FRAME_HEADER.size:
        raise ValueError(f"{label} frame header is incomplete")
    observed_magic, payload_bytes = _FRAME_HEADER.unpack(header)
    if observed_magic != magic:
        raise ValueError(f"{label} frame magic is invalid")
    if not 0 < payload_bytes <= maximum_frame_bytes - _FRAME_HEADER.size:
        raise ValueError(f"{label} frame length exceeds bounds")
    return _FRAME_HEADER.size + payload_bytes


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value!r} is unsupported")


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


def _verify_one_output(
    descriptor: int,
    claim: Mapping[str, Any],
    *,
    directory_descriptor: int,
    entry_name: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    try:
        if os.get_inheritable(descriptor):
            raise ValueError(
                "quarantine verification descriptor must be non-inheritable"
            )
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        if flags & os.O_ACCMODE != os.O_RDONLY:
            raise ValueError(
                "quarantine verification descriptor must be read-only"
            )
        before = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError(
            "quarantine verification descriptor is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) & 0o077
    ):
        raise ValueError("quarantine output file ownership is invalid")
    if (
        before.st_size != claim["bytes"]
        or before.st_size > maximum_bytes
    ):
        raise ValueError("quarantine output byte count does not match claim")
    try:
        entry_before = os.stat(
            entry_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValueError(
            "quarantine output entry is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(entry_before.st_mode)
        or _file_object_identity(entry_before)
        != _file_object_identity(before)
    ):
        raise ValueError(
            "quarantine output descriptor does not match its exact entry"
        )

    digest = hashlib.sha256()
    offset = 0
    try:
        while offset < before.st_size:
            chunk = os.pread(
                descriptor,
                min(_HASH_CHUNK_BYTES, before.st_size - offset),
                offset,
            )
            if not chunk:
                raise ValueError("quarantine output is truncated")
            digest.update(chunk)
            offset += len(chunk)
    except OSError as exc:
        raise ValueError("quarantine output could not be verified") from exc
    if digest.hexdigest() != claim["sha256"]:
        raise ValueError("quarantine output hash does not match claim")
    geometry = _read_pcm24_wav_geometry(
        descriptor,
        file_bytes=before.st_size,
    )
    if geometry != _plain(claim["geometry"]):
        raise ValueError("quarantine PCM24 geometry does not match claim")
    try:
        after = os.fstat(descriptor)
        entry_after = os.stat(
            entry_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValueError("quarantine output could not be rechecked") from exc
    if (
        _file_identity(before) != _file_identity(after)
        or _file_identity(entry_before) != _file_identity(entry_after)
        or _file_object_identity(entry_after) != _file_object_identity(after)
    ):
        raise ValueError("quarantine output changed during verification")
    try:
        final = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError("quarantine output could not be rechecked") from exc
    if _file_identity(final) != _file_identity(after):
        raise ValueError("quarantine output changed during verification")
    return {
        "slot_id": claim["slot_id"],
        "role": claim["role"],
        "artifact_kind": claim["artifact_kind"],
        "bytes": claim["bytes"],
        "sha256": claim["sha256"],
        "file_identity_sha256": _identity_sha256(final),
        "regular_file": True,
        "owner_only_permissions": True,
        "read_only_verification_descriptor": True,
        "descriptor_noninheritable": True,
        "identity_stable_during_full_hash": True,
        "code_owned_fixture_bytes_matched": True,
        "pcm24_geometry_verified": True,
        "_file_object_identity": list(_file_object_identity(final)),
    }


def _verified_quarantine_directory(descriptor: int) -> os.stat_result:
    try:
        if os.get_inheritable(descriptor):
            raise ValueError(
                "quarantine directory descriptor must be non-inheritable"
            )
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        if flags & os.O_ACCMODE != os.O_RDONLY:
            raise ValueError(
                "quarantine directory descriptor must be read-only"
            )
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError(
            "quarantine directory descriptor is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) & 0o077
    ):
        raise ValueError("quarantine directory ownership is invalid")
    return opened


def _read_pcm24_wav_geometry(
    descriptor: int,
    *,
    file_bytes: int,
) -> dict[str, Any]:
    try:
        header = os.pread(descriptor, 12, 0)
    except OSError as exc:
        raise ValueError("quarantine PCM24 header could not be read") from exc
    if (
        len(header) != 12
        or header[:4] != b"RIFF"
        or header[8:] != b"WAVE"
        or struct.unpack("<I", header[4:8])[0] + 8 != file_bytes
    ):
        raise ValueError("quarantine output is not a complete RIFF WAVE")

    position = 12
    format_data: bytes | None = None
    data_bytes: int | None = None
    while position + 8 <= file_bytes:
        chunk_header = os.pread(descriptor, 8, position)
        if len(chunk_header) != 8:
            raise ValueError("quarantine WAVE chunk header is truncated")
        chunk_size = struct.unpack("<I", chunk_header[4:8])[0]
        chunk_start = position + 8
        chunk_end = chunk_start + chunk_size
        padded_end = chunk_end + (chunk_size & 1)
        if chunk_end > file_bytes or (
            padded_end > file_bytes and chunk_end != file_bytes
        ):
            raise ValueError("quarantine WAVE chunk is truncated")
        if chunk_header[:4] == b"fmt " and format_data is None:
            if not 16 <= chunk_size <= 1024:
                raise ValueError("quarantine WAVE format chunk is invalid")
            format_data = os.pread(descriptor, chunk_size, chunk_start)
            if len(format_data) != chunk_size:
                raise ValueError("quarantine WAVE format chunk is truncated")
        elif chunk_header[:4] == b"data" and data_bytes is None:
            data_bytes = chunk_size
        position = min(padded_end, file_bytes)

    if format_data is None or data_bytes is None or len(format_data) < 16:
        raise ValueError("quarantine WAVE needs format and data chunks")
    (
        format_tag,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    ) = struct.unpack("<HHIIHH", format_data[:16])
    if (
        format_tag != 1
        or not 1 <= channels <= 2
        or not 1 <= sample_rate <= 768_000
        or bits_per_sample != 24
        or block_align != channels * 3
        or byte_rate != sample_rate * block_align
        or data_bytes <= 0
        or data_bytes % block_align
    ):
        raise ValueError("quarantine output is not packed PCM24")
    frames = data_bytes // block_align
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": frames / sample_rate,
    }


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _file_object_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _identity_sha256(value: os.stat_result) -> str:
    return _hash(
        {
            "device": value.st_dev,
            "inode": value.st_ino,
            "mode": value.st_mode,
            "links": value.st_nlink,
            "owner": value.st_uid,
            "group": value.st_gid,
            "bytes": value.st_size,
            "modified_ns": value.st_mtime_ns,
            "changed_ns": value.st_ctime_ns,
        }
    )


__all__: list[str] = []
