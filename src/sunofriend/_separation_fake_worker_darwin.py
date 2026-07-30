"""Fixed stdlib-only worker for the deterministic Darwin fake transport.

The audited native launcher executes this exact file with ``python -I -B -S``
and exposes only logical request, result and checkpoint descriptors 3, 4 and
5.  It reads no path or source audio, imports no Sunofriend module, creates no
process, opens no file, deserializes no checkpoint and performs no model
operation.  Its only output is a bounded result frame containing code-owned
two-frame PCM24 fixtures.
"""

from __future__ import annotations

import os


# This is intentionally the first effectful worker code.  FD 3/4/5 must not
# survive any later exec even if a future edit fails before ``main`` starts.
for _transport_descriptor in (3, 4, 5):
    os.set_inheritable(_transport_descriptor, False)
del _transport_descriptor


import errno  # noqa: E402
import fcntl  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import stat  # noqa: E402
import struct  # noqa: E402
from typing import Any, Mapping, Sequence  # noqa: E402


_TRANSPORT_FDS = (3, 4, 5)
_REQUEST_FD = 3
_RESULT_FD = 4
_CHECKPOINT_FD = 5
_REQUEST_MAGIC = b"SFRQv002"
_RESULT_MAGIC = b"SFRSv002"
_FRAME_HEADER = struct.Struct(">8sQ")
_REQUEST_MAXIMUM_BYTES = 65_536
_RESULT_MAXIMUM_BYTES = 1_048_576
_CHECKPOINT_MAXIMUM_BYTES = 8 * 1024 * 1024 * 1024
_MAXIMUM_JSON_DEPTH = 32
_MAXIMUM_JSON_NODES = 1_000_000
_HASH_CHUNK_BYTES = 1024 * 1024
_ENVELOPE_SCHEMA = "sunofriend.separation-fake-transport-envelope.v2"
_PLAN_SCHEMA = "sunofriend.separation-fake-launch-plan.v3"
_RESULT_SCHEMA = "sunofriend.separation-fake-worker-result.v2"
_POLICY_ID = "private-deterministic-fake-execution-v1"
_FIXTURE_ID = "code-owned-two-frame-pcm24-v1"
_ROLE_IDS = frozenset(
    """
    backing_vocals bass cymbals drums hat keys kick lead other other_kit
    piano rhythm snare strings synth toms vocals wind
    """.split()
)
_PLAN_FIELDS = frozenset(
    """
    schema policy_id evidence_scope publication_scope status run_status
    backend_scope test_only_worker_start_supported
    test_only_worker_start_permitted real_separation_supported
    real_separation_permitted run_nonce historical_bindings bindings
    fixture roles output_slots invocation descriptor_contract
    lifecycle_contract authority capabilities limitations effects plan_sha256
    """.split()
)
_BINDING_FIELDS = frozenset(
    """
    checkpoint_sha256 checkpoint_bytes checkpoint_file_identity_sha256
    native_launcher_sha256 native_launcher_bytes
    native_launcher_stat_identity_sha256 runtime_executable_sha256
    runtime_executable_bytes runtime_executable_stat_identity_sha256
    fake_worker_sha256 fake_worker_bytes fake_worker_stat_identity_sha256
    native_build_receipt_sha256
    """.split()
)
_FIXTURE = {
    "fixture_id": _FIXTURE_ID,
    "generation": "code_owned_two_frame_pcm24_per_role",
    "source_audio_read": False,
    "checkpoint_deserialized": False,
    "model_imported": False,
    "inference_started": False,
}
_INVOCATION = {
    "argv": [
        "bound_runtime_executable",
        "-I",
        "-B",
        "-S",
        "bound_fake_worker_entrypoint",
    ],
    "environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
    "shell": False,
    "path_search": False,
    "preexec_callback": False,
    "environment_inherited": False,
    "working_directory_inherited": False,
}
_DESCRIPTOR_CONTRACT = {
    "logical_descriptors": [3, 4, 5],
    "worker_entry_allowed_descriptors": [0, 1, 2, 3, 4, 5],
    "unlisted_descriptors_permitted": False,
    "first_user_code_action": "set_fd345_noninheritable",
    "further_exec_permitted": False,
    "request_maximum_bytes": _REQUEST_MAXIMUM_BYTES,
    "result_maximum_bytes": _RESULT_MAXIMUM_BYTES,
}
_LIFECYCLE_CONTRACT = {
    "timeout_seconds": 5,
    "term_grace_seconds": 1,
    "clock_source": "monotonic",
    "exact_owned_child_required": True,
    "process_group_required": True,
    "fixed_worker_descendants": 0,
    "terminal_receipt_required": True,
}
_AUTHORITY = {
    "serialized_plan_is_execution_authority": False,
    "parent_live_admission_required": True,
    "parent_live_admission_serialized": False,
    "exact_lease_required": True,
    "exact_reservation_required": True,
    "fresh_single_use_nonce_required": True,
}
_CAPABILITIES = {
    "deterministic_fixture_supported": True,
    "checkpoint_full_hash_supported": True,
    "source_audio_supported": False,
    "checkpoint_deserialization_supported": False,
    "model_import_supported": False,
    "inference_supported": False,
    "real_separation_supported": False,
    "selection_supported": False,
    "publication_supported": False,
    "acceptance_supported": False,
    "promotion_supported": False,
}
_LIMITATIONS = [
    "prepared_v3_plan_is_not_serialized_execution_authority",
    "admitted_v2_envelope_requires_exact_parent_live_authority",
    "historical_v1_and_v2_records_remain_permanently_non_executable",
    "fixed_process_creation_free_deterministic_worker_only",
    "source_audio_model_inference_selection_publication_acceptance_forbidden",
    "runtime_exec_and_worker_script_path_toctou_remain_unresolved",
    "finite_descriptor_canary_matrix_is_not_exhaustive_arbitrary_fd_proof",
    "post_cpython_signal_state_is_not_independently_proven",
]


def _harden_transport_descriptors() -> None:
    for descriptor in _TRANSPORT_FDS:
        os.set_inheritable(descriptor, False)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_request_frame() -> dict[str, Any]:
    before = os.fstat(_REQUEST_FD)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size <= _FRAME_HEADER.size
        or before.st_size > _REQUEST_MAXIMUM_BYTES
    ):
        raise ValueError("request_frame_invalid")
    header = _pread_exact(_REQUEST_FD, _FRAME_HEADER.size, 0)
    magic, payload_bytes = _FRAME_HEADER.unpack(header)
    if (
        magic != _REQUEST_MAGIC
        or payload_bytes <= 0
        or payload_bytes > _REQUEST_MAXIMUM_BYTES - _FRAME_HEADER.size
        or before.st_size != _FRAME_HEADER.size + payload_bytes
    ):
        raise ValueError("request_frame_invalid")
    payload = _pread_exact(_REQUEST_FD, payload_bytes, _FRAME_HEADER.size)
    after = os.fstat(_REQUEST_FD)
    if _identity_tuple(before) != _identity_tuple(after):
        raise ValueError("request_frame_changed")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("request_json_invalid") from exc
    if type(value) is not dict:
        raise ValueError("request_json_invalid")
    _validate_json_shape(value)
    if _canonical_bytes(value) != payload:
        raise ValueError("request_json_noncanonical")
    return value


def _validate_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
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
        raise ValueError("request_fields_invalid")
    payload = dict(envelope)
    envelope_sha256 = payload.pop("envelope_sha256")
    if (
        envelope["schema"] != _ENVELOPE_SCHEMA
        or envelope["policy_id"] != _POLICY_ID
        or envelope["evidence_scope"] != "private_development"
        or envelope["status"] != "admitted"
        or envelope["backend_scope"]
        != "deterministic_transport_fixture_only"
        or envelope["test_only_execution_permitted"] is not True
        or envelope["real_separation_permitted"] is not False
        or envelope["serialized_envelope_is_parent_authority"] is not False
        or not _is_sha(envelope_sha256)
        or envelope_sha256 != _canonical_hash(payload)
    ):
        raise ValueError("request_policy_invalid")
    plan = _validate_plan(envelope["fake_launch_plan_v3"])
    if (
        envelope["run_nonce"] != plan["run_nonce"]
        or envelope["fake_launch_plan_v3_sha256"] != plan["plan_sha256"]
    ):
        raise ValueError("request_binding_invalid")
    return plan


def _validate_plan(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _PLAN_FIELDS:
        raise ValueError("plan_fields_invalid")
    payload = dict(value)
    plan_sha256 = payload.pop("plan_sha256")
    if (
        value["schema"] != _PLAN_SCHEMA
        or value["policy_id"] != _POLICY_ID
        or value["evidence_scope"] != "private_development"
        or value["publication_scope"] != "private_local_transport_evidence"
        or value["status"] != "prepared"
        or value["run_status"] != "not_run"
        or value["backend_scope"]
        != "deterministic_transport_fixture_only"
        or value["test_only_worker_start_supported"] is not True
        or value["test_only_worker_start_permitted"] is not False
        or value["real_separation_supported"] is not False
        or value["real_separation_permitted"] is not False
        or not _is_nonce(value["run_nonce"])
        or not _is_sha(plan_sha256)
        or plan_sha256 != _canonical_hash(payload)
    ):
        raise ValueError("plan_policy_invalid")
    historical = value["historical_bindings"]
    if (
        type(historical) is not dict
        or set(historical)
        != {
            "fake_worker_request_v1_sha256",
            "fake_launch_plan_v1_sha256",
            "blocked_fake_launch_plan_v2_sha256",
            "historical_records_are_execution_authority",
        }
        or historical["historical_records_are_execution_authority"] is not False
        or any(
            not _is_sha(item)
            for key, item in historical.items()
            if key.endswith("_sha256")
        )
    ):
        raise ValueError("plan_historical_binding_invalid")
    bindings = value["bindings"]
    if type(bindings) is not dict or set(bindings) != _BINDING_FIELDS:
        raise ValueError("plan_binding_invalid")
    for key, item in bindings.items():
        if key.endswith("_sha256") and not _is_sha(item):
            raise ValueError("plan_binding_invalid")
        if key.endswith("_bytes") and (
            type(item) is not int or item <= 0
        ):
            raise ValueError("plan_binding_invalid")
    if (
        value["fixture"] != _FIXTURE
        or value["invocation"] != _INVOCATION
        or value["descriptor_contract"] != _DESCRIPTOR_CONTRACT
        or value["lifecycle_contract"] != _LIFECYCLE_CONTRACT
        or value["authority"] != _AUTHORITY
        or value["capabilities"] != _CAPABILITIES
        or value["limitations"] != _LIMITATIONS
        or type(value["effects"]) is not dict
        or any(item is not False for item in value["effects"].values())
    ):
        raise ValueError("plan_contract_invalid")
    roles = value["roles"]
    if (
        type(roles) is not list
        or roles != sorted(set(roles))
        or not roles
        or any(role not in _ROLE_IDS for role in roles)
    ):
        raise ValueError("plan_roles_invalid")
    slots = value["output_slots"]
    if type(slots) is not list or len(slots) != len(roles):
        raise ValueError("plan_output_slots_invalid")
    for index, (role, slot) in enumerate(zip(roles, slots), 1):
        if slot != {
            "role": role,
            "slot_id": f"stem-{index:02d}",
            "artifact_kind": "pcm24_wav",
            "maximum_bytes": 4_096,
        }:
            raise ValueError("plan_output_slots_invalid")
    return value


def _descriptor_report() -> dict[str, Any]:
    access = {
        descriptor: fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
        for descriptor in _TRANSPORT_FDS
    }
    inheritable = {
        descriptor: os.get_inheritable(descriptor)
        for descriptor in _TRANSPORT_FDS
    }
    open_descriptors = _open_descriptors()
    if open_descriptors != [0, 1, 2, 3, 4, 5]:
        raise ValueError("descriptor_contract_violation")
    if (
        access[_REQUEST_FD] != os.O_RDONLY
        or access[_RESULT_FD] != os.O_WRONLY
        or access[_CHECKPOINT_FD] != os.O_RDONLY
        or any(inheritable.values())
    ):
        raise ValueError("descriptor_contract_violation")
    return {
        "fd3_noninheritable": True,
        "fd3_read_only": True,
        "fd4_noninheritable": True,
        "fd4_write_only": True,
        "fd5_noninheritable": True,
        "fd5_read_only": True,
        "unexpected_open_descriptors": 0,
        "offset_independent_checkpoint_reader": True,
    }


def _checkpoint_report(plan: Mapping[str, Any]) -> dict[str, Any]:
    expected = plan["bindings"]
    before = os.fstat(_CHECKPOINT_FD)
    before_identity_sha256 = _checkpoint_identity_sha256(before)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size <= 0
        or before.st_size > _CHECKPOINT_MAXIMUM_BYTES
        or before.st_size != expected["checkpoint_bytes"]
        or before_identity_sha256
        != expected["checkpoint_file_identity_sha256"]
    ):
        raise ValueError("checkpoint_identity_mismatch")
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(
            _CHECKPOINT_FD,
            min(_HASH_CHUNK_BYTES, before.st_size - offset),
            offset,
        )
        if not chunk:
            raise ValueError("checkpoint_truncated")
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(_CHECKPOINT_FD)
    after_identity_sha256 = _checkpoint_identity_sha256(after)
    if (
        _identity_tuple(before) != _identity_tuple(after)
        or after_identity_sha256 != before_identity_sha256
        or digest.hexdigest() != expected["checkpoint_sha256"]
    ):
        raise ValueError("checkpoint_identity_mismatch")
    return {
        "sha256": digest.hexdigest(),
        "bytes": offset,
        "file_identity_sha256": before_identity_sha256,
        "identity_before_hash_sha256": before_identity_sha256,
        "identity_after_hash_sha256": after_identity_sha256,
        "unchanged": True,
        "full_hash_verified": True,
        "deserialized": False,
    }


def _fixture_outputs(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for slot in plan["output_slots"]:
        payload = _fixture_wav_bytes(slot["role"])
        if len(payload) > slot["maximum_bytes"]:
            raise ValueError("fixture_generation_failed")
        outputs.append(
            {
                "role": slot["role"],
                "slot_id": slot["slot_id"],
                "artifact_kind": "pcm24_wav",
                "payload_encoding": "lowercase_hex",
                "payload_hex": payload.hex(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "geometry": {
                    "sample_rate": 8_000,
                    "channels": 1,
                    "frames": 2,
                    "duration_seconds": 0.00025,
                },
            }
        )
    return outputs


def _fixture_wav_bytes(role: str) -> bytes:
    samples = hashlib.sha256(role.encode("ascii")).digest()[:6]
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", 36 + len(samples)),
            b"WAVEfmt ",
            struct.pack("<IHHIIHH", 16, 1, 1, 8_000, 24_000, 3, 24),
            b"data",
            struct.pack("<I", len(samples)),
            samples,
        )
    )


def _result_document(
    plan: Mapping[str, Any],
    *,
    descriptor_report: Mapping[str, Any],
    checkpoint_report: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    pid = os.getpid()
    pgid = os.getpgrp()
    if pgid != pid:
        raise ValueError("process_group_invalid")
    payload = {
        "schema": _RESULT_SCHEMA,
        "policy_id": _POLICY_ID,
        "evidence_scope": "private_development",
        "status": "complete",
        "backend_scope": "deterministic_transport_fixture_only",
        "evidence_authority": "worker_report_only",
        "run_nonce": plan["run_nonce"],
        "fake_launch_plan_v3_sha256": plan["plan_sha256"],
        "process_report": {
            "pid": pid,
            "pgid": pgid,
            "pgid_equals_pid": True,
            "process_creation_attempted_by_worker": False,
            "reported_identifiers_are_signal_authority": False,
        },
        "descriptor_report": dict(descriptor_report),
        "checkpoint_report": dict(checkpoint_report),
        "outputs": [dict(item) for item in outputs],
        "error": None,
        "effects": {
            "process_started": True,
            "worker_started": True,
            "checkpoint_remeasured_in_child": True,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "inference_started": False,
            "network_used": False,
            "audio_read": False,
            "output_payloads_generated": True,
            "output_files_created": False,
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
    }
    return {**payload, "result_sha256": _canonical_hash(payload)}


def _write_result_frame(result: Mapping[str, Any]) -> None:
    payload = _canonical_bytes(result)
    if not payload or len(payload) > _RESULT_MAXIMUM_BYTES - _FRAME_HEADER.size:
        raise ValueError("result_frame_oversize")
    frame = _FRAME_HEADER.pack(_RESULT_MAGIC, len(payload)) + payload
    os.ftruncate(_RESULT_FD, 0)
    offset = 0
    while offset < len(frame):
        written = os.pwrite(_RESULT_FD, frame[offset:], offset)
        if written <= 0:
            raise OSError("result_write_failed")
        offset += written
    os.fsync(_RESULT_FD)


def _checkpoint_identity_sha256(value: os.stat_result) -> str:
    return _canonical_hash(
        {
            "device": value.st_dev,
            "inode": value.st_ino,
            "mode": value.st_mode,
            "links": value.st_nlink,
            "bytes": value.st_size,
            "mtime_ns": value.st_mtime_ns,
            "ctime_ns": value.st_ctime_ns,
            "uid": value.st_uid,
        }
    )


def _pread_exact(descriptor: int, byte_count: int, offset: int) -> bytes:
    chunks: list[bytes] = []
    remaining = byte_count
    position = offset
    while remaining:
        chunk = os.pread(descriptor, remaining, position)
        if not chunk:
            raise ValueError("descriptor_read_truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
        position += len(chunk)
    return b"".join(chunks)


def _open_descriptors() -> list[int]:
    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    limit = 1_048_576 if soft_limit == resource.RLIM_INFINITY else int(soft_limit)
    result: list[int] = []
    for descriptor in range(limit):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        result.append(descriptor)
    return result


def _identity_tuple(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
    )


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non_finite_json_constant:{value}")


def _validate_json_shape(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAXIMUM_JSON_NODES or depth > _MAXIMUM_JSON_DEPTH:
            raise ValueError("request_json_structure_exceeds_bounds")
        if isinstance(current, dict):
            if any(type(key) is not str for key in current):
                raise ValueError("request_json_key_invalid")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif current is not None and type(current) not in {
            bool,
            int,
            float,
            str,
        }:
            raise ValueError("request_json_value_invalid")


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_nonce(value: Any) -> bool:
    return _is_sha(value)


def main() -> int:
    _harden_transport_descriptors()
    try:
        descriptor_report = _descriptor_report()
        envelope = _read_request_frame()
        plan = _validate_envelope(envelope)
        checkpoint_report = _checkpoint_report(plan)
        outputs = _fixture_outputs(plan)
        result = _result_document(
            plan,
            descriptor_report=descriptor_report,
            checkpoint_report=checkpoint_report,
            outputs=outputs,
        )
        _write_result_frame(result)
        return 0
    except BaseException:
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
