"""Private records for the deterministic fake transport execution boundary.

These records are the executable-transport successors to the permanently
blocked fake request/launch V1 and fake launch V2 records.  The V3 plan is
still only a prepared value: it says that the fixed fake worker is supported,
but it does not grant permission to start it and is never serialized
authority.  A later parent executor must hold the exact live checkpoint
lease, reservation, native build and one non-copyable admission object before
it can frame the separate V2 admitted envelope.

The worker-result V2 record is worker-authored evidence only.  It can report
the fixed code-owned PCM24 fixture, checkpoint hash observation and the main
thread's signal state after CPython startup; it cannot reconstruct the
pre-exec signal instant and can never represent source separation, model
execution, publication, selection, acceptance or promotion.
"""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_fake_launch_v2_records import (
    _SeparationFakeLaunchPlanV2Record,
    _validate_blocked_separation_fake_launch_plan_v2_record_shape,
)
from ._separation_fake_transport_records import (
    _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
    _complete_descriptor_report,
    _validate_fake_launch_plan_shape,
    _validate_fake_worker_request_shape,
)
from ._separation_worker_request_v2_values import (
    _bounded_json_copy,
    _object_with_fields,
    _sha,
    _validate_path_free,
)


_FAKE_LAUNCH_V3_SCHEMA = "sunofriend.separation-fake-launch-plan.v3"
_FAKE_RESULT_V2_SCHEMA = "sunofriend.separation-fake-worker-result.v2"
_FAKE_EXECUTION_POLICY_ID = "private-deterministic-fake-execution-v1"
_FAKE_FIXTURE_ID = "code-owned-two-frame-pcm24-v1"
_EXPECTED_FAKE_WORKER_SOURCE_SHA256 = (
    "8efec22498bdabef33d951eafaba9cc80cc51a7e0f0adef52ab21e883c38b741"
)
_EXPECTED_FAKE_WORKER_SOURCE_BYTES = 24_003
_MAXIMUM_PLAN_BYTES = 262_144
_MAXIMUM_RESULT_BYTES = _FAKE_RESULT_MAXIMUM_FRAME_BYTES - 16
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_NONCE_RE = re.compile(r"^[0-9a-f]{64}$")


def _fields(value: str) -> frozenset[str]:
    return frozenset(value.split())


_PLAN_FIELDS = _fields(
    """
    schema policy_id evidence_scope publication_scope status run_status
    backend_scope test_only_worker_start_supported
    test_only_worker_start_permitted real_separation_supported
    real_separation_permitted run_nonce historical_bindings bindings
    fixture roles output_slots invocation descriptor_contract
    lifecycle_contract authority capabilities limitations effects plan_sha256
    """
)
_HISTORICAL_FIELDS = _fields(
    """
    fake_worker_request_v1_sha256 fake_launch_plan_v1_sha256
    blocked_fake_launch_plan_v2_sha256
    historical_records_are_execution_authority
    """
)
_BINDING_FIELDS = _fields(
    """
    checkpoint_sha256 checkpoint_bytes checkpoint_file_identity_sha256
    native_launcher_sha256 native_launcher_bytes
    native_launcher_stat_identity_sha256 runtime_executable_sha256
    runtime_executable_bytes runtime_executable_stat_identity_sha256
    fake_worker_sha256 fake_worker_bytes fake_worker_stat_identity_sha256
    native_build_receipt_sha256
    """
)
_FIXTURE_FIELDS = _fields(
    """
    fixture_id generation source_audio_read checkpoint_deserialized
    model_imported inference_started
    """
)
_OUTPUT_SLOT_FIELDS = _fields(
    "role slot_id artifact_kind maximum_bytes"
)
_INVOCATION_FIELDS = _fields(
    """
    argv environment shell path_search preexec_callback
    environment_inherited working_directory_inherited
    """
)
_DESCRIPTOR_CONTRACT_FIELDS = _fields(
    """
    logical_descriptors worker_entry_allowed_descriptors
    unlisted_descriptors_permitted first_user_code_action
    further_exec_permitted request_maximum_bytes result_maximum_bytes
    """
)
_LIFECYCLE_FIELDS = _fields(
    """
    timeout_seconds term_grace_seconds clock_source
    exact_owned_child_required process_group_required fixed_worker_descendants
    terminal_receipt_required
    """
)
_AUTHORITY_FIELDS = _fields(
    """
    serialized_plan_is_execution_authority
    parent_live_admission_required parent_live_admission_serialized
    exact_lease_required exact_reservation_required
    fresh_single_use_nonce_required
    """
)
_CAPABILITY_FIELDS = _fields(
    """
    deterministic_fixture_supported checkpoint_full_hash_supported
    source_audio_supported checkpoint_deserialization_supported
    model_import_supported inference_supported real_separation_supported
    selection_supported publication_supported acceptance_supported
    promotion_supported
    """
)
_EFFECT_FIELDS = _fields(
    """
    filesystem_accessed native_launcher_loaded process_started worker_started
    process_group_created signal_sent process_reaped
    checkpoint_remeasured_in_child checkpoint_deserialized model_imported
    inference_started network_used audio_read output_payloads_generated
    output_files_created quarantine_created files_written
    publication_permitted selection_permitted acceptance_eligible
    promotion_eligible
    """
)

_RESULT_FIELDS = _fields(
    """
    schema policy_id evidence_scope status backend_scope evidence_authority
    run_nonce fake_launch_plan_v3_sha256 process_report signal_report
    descriptor_report checkpoint_report outputs error effects result_sha256
    """
)
_PROCESS_REPORT_FIELDS = _fields(
    """
    pid pgid pgid_equals_pid process_creation_attempted_by_worker
    reported_identifiers_are_signal_authority
    """
)
_SIGNAL_REPORT_FIELDS = _fields(
    """
    observation_point main_thread_mask_empty blocked_signal_names handlers
    termination_signals_default sigchld_default
    cpython_runtime_adjustments_observed pre_exec_signal_state_reconstructed
    """
)
_DESCRIPTOR_REPORT_FIELDS = _fields(
    """
    fd3_noninheritable fd3_read_only fd4_noninheritable fd4_write_only
    fd5_noninheritable fd5_read_only unexpected_open_descriptors
    offset_independent_checkpoint_reader
    """
)
_CHECKPOINT_REPORT_FIELDS = _fields(
    """
    sha256 bytes file_identity_sha256 identity_before_hash_sha256
    identity_after_hash_sha256 unchanged full_hash_verified deserialized
    """
)
_RESULT_OUTPUT_FIELDS = _fields(
    """
    role slot_id artifact_kind payload_encoding payload_hex sha256 bytes
    geometry
    """
)
_GEOMETRY_FIELDS = _fields(
    "sample_rate channels frames duration_seconds"
)

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
    "request_maximum_bytes": _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    "result_maximum_bytes": _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
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
_LIMITATIONS = (
    "prepared_v3_plan_is_not_serialized_execution_authority",
    "admitted_v2_envelope_requires_exact_parent_live_authority",
    "historical_v1_and_v2_records_remain_permanently_non_executable",
    "fixed_process_creation_free_deterministic_worker_only",
    "source_audio_model_inference_selection_publication_acceptance_forbidden",
    "runtime_exec_and_worker_script_path_toctou_remain_unresolved",
    "finite_descriptor_canary_matrix_is_not_exhaustive_arbitrary_fd_proof",
    "post_cpython_signal_state_does_not_reconstruct_pre_exec_instant",
)


@dataclass(frozen=True, init=False)
class _SeparationFakeLaunchPlanV3Record(Mapping[str, Any]):
    """Prepared fixed-worker plan; never the parent live authority."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class _SeparationFakeWorkerResultV2Record(Mapping[str, Any]):
    """Exact worker-authored transport evidence."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_prepared_separation_fake_launch_plan_v3_record(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    native_build_receipt_sha256: str,
) -> _SeparationFakeLaunchPlanV3Record:
    """Bind the fixed fixture to exact historical records and build evidence."""

    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch_v1 = _validate_fake_launch_plan_shape(fake_launch_plan_v1)
    launch_v2 = (
        _validate_blocked_separation_fake_launch_plan_v2_record_shape(
            blocked_fake_launch_plan_v2,
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
        )
    )
    v2_bindings = _plain(launch_v2["bindings"])
    if (
        v2_bindings["fake_worker_sha256"]
        != _EXPECTED_FAKE_WORKER_SOURCE_SHA256
        or v2_bindings["fake_worker_bytes"]
        != _EXPECTED_FAKE_WORKER_SOURCE_BYTES
    ):
        raise ValueError("fake launch V3 requires the pinned worker source")
    bindings = {
        key: v2_bindings[key]
        for key in _BINDING_FIELDS
        if key != "native_build_receipt_sha256"
    }
    bindings["native_build_receipt_sha256"] = _sha(
        native_build_receipt_sha256,
        "native build receipt sha256",
    )
    payload = {
        "schema": _FAKE_LAUNCH_V3_SCHEMA,
        "policy_id": _FAKE_EXECUTION_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_transport_evidence",
        "status": "prepared",
        "run_status": "not_run",
        "backend_scope": "deterministic_transport_fixture_only",
        "test_only_worker_start_supported": True,
        "test_only_worker_start_permitted": False,
        "real_separation_supported": False,
        "real_separation_permitted": False,
        "run_nonce": request["run_nonce"],
        "historical_bindings": {
            "fake_worker_request_v1_sha256": request["request_sha256"],
            "fake_launch_plan_v1_sha256": launch_v1["plan_sha256"],
            "blocked_fake_launch_plan_v2_sha256": launch_v2["plan_sha256"],
            "historical_records_are_execution_authority": False,
        },
        "bindings": bindings,
        "fixture": _plain(request["fixture"]),
        "roles": _plain(request["roles"]),
        "output_slots": _plain(request["output_slots"]),
        "invocation": _plain(_INVOCATION),
        "descriptor_contract": _plain(_DESCRIPTOR_CONTRACT),
        "lifecycle_contract": _plain(_LIFECYCLE_CONTRACT),
        "authority": _plain(_AUTHORITY),
        "capabilities": _plain(_CAPABILITIES),
        "limitations": list(_LIMITATIONS),
        "effects": {key: False for key in sorted(_EFFECT_FIELDS)},
    }
    return _new_prepared_separation_fake_launch_plan_v3_record(
        {**payload, "plan_sha256": _hash(payload)},
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
    )


def _validate_prepared_separation_fake_launch_plan_v3_record_shape(
    value: Any,
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
) -> _SeparationFakeLaunchPlanV3Record:
    if type(value) is not _SeparationFakeLaunchPlanV3Record:
        raise ValueError("fake launch V3 must be an exact validated record")
    checked = _new_prepared_separation_fake_launch_plan_v3_record(
        value,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
    )
    if _canonical_json(_plain(value)) != _canonical_json(_plain(checked)):
        raise ValueError("fake launch V3 changed after validation")
    return value


def _new_prepared_separation_fake_launch_plan_v3_record(
    document: Mapping[str, Any],
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
) -> _SeparationFakeLaunchPlanV3Record:
    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch_v1 = _validate_fake_launch_plan_shape(fake_launch_plan_v1)
    launch_v2 = (
        _validate_blocked_separation_fake_launch_plan_v2_record_shape(
            blocked_fake_launch_plan_v2,
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
        )
    )
    value = _object_with_fields(document, _PLAN_FIELDS, "fake launch V3")
    _validate_path_free(value, "fake launch V3")
    if (
        value["schema"] != _FAKE_LAUNCH_V3_SCHEMA
        or value["policy_id"] != _FAKE_EXECUTION_POLICY_ID
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
    ):
        raise ValueError("fake launch V3 policy is invalid")
    _run_nonce(value["run_nonce"])
    if (
        value["run_nonce"] != request["run_nonce"]
        or value["run_nonce"] != launch_v1["run_nonce"]
        or value["run_nonce"] != launch_v2["run_nonce"]
    ):
        raise ValueError("fake launch V3 nonce binding is invalid")
    historical = _object_with_fields(
        value["historical_bindings"],
        _HISTORICAL_FIELDS,
        "fake launch V3 historical bindings",
    )
    if historical != {
        "fake_worker_request_v1_sha256": request["request_sha256"],
        "fake_launch_plan_v1_sha256": launch_v1["plan_sha256"],
        "blocked_fake_launch_plan_v2_sha256": launch_v2["plan_sha256"],
        "historical_records_are_execution_authority": False,
    }:
        raise ValueError("fake launch V3 historical bindings are invalid")
    bindings = _object_with_fields(
        value["bindings"], _BINDING_FIELDS, "fake launch V3 bindings"
    )
    v2_bindings = launch_v2["bindings"]
    for key, item in bindings.items():
        if key.endswith("_sha256"):
            _sha(item, key)
        elif type(item) is not int or item <= 0:
            raise ValueError(f"{key} is outside supported bounds")
        if (
            key != "native_build_receipt_sha256"
            and item != v2_bindings[key]
        ):
            raise ValueError("fake launch V3 artifact binding changed")
    fixture = _object_with_fields(
        value["fixture"], _FIXTURE_FIELDS, "fake launch V3 fixture"
    )
    if (
        fixture != _plain(request["fixture"])
        or fixture["fixture_id"] != _FAKE_FIXTURE_ID
    ):
        raise ValueError("fake launch V3 fixture is invalid")
    if (
        value["roles"] != _plain(request["roles"])
        or value["output_slots"] != _plain(request["output_slots"])
    ):
        raise ValueError("fake launch V3 roles or output slots changed")
    _validate_output_slots(value["output_slots"], value["roles"])
    if value["invocation"] != _INVOCATION:
        raise ValueError("fake launch V3 invocation is invalid")
    _object_with_fields(
        value["invocation"], _INVOCATION_FIELDS, "fake launch V3 invocation"
    )
    if value["descriptor_contract"] != _DESCRIPTOR_CONTRACT:
        raise ValueError("fake launch V3 descriptor contract is invalid")
    _object_with_fields(
        value["descriptor_contract"],
        _DESCRIPTOR_CONTRACT_FIELDS,
        "fake launch V3 descriptor contract",
    )
    if value["lifecycle_contract"] != _LIFECYCLE_CONTRACT:
        raise ValueError("fake launch V3 lifecycle contract is invalid")
    _object_with_fields(
        value["lifecycle_contract"],
        _LIFECYCLE_FIELDS,
        "fake launch V3 lifecycle contract",
    )
    if value["authority"] != _AUTHORITY:
        raise ValueError("fake launch V3 authority is invalid")
    _object_with_fields(
        value["authority"], _AUTHORITY_FIELDS, "fake launch V3 authority"
    )
    if value["capabilities"] != _CAPABILITIES:
        raise ValueError("fake launch V3 capabilities are invalid")
    _object_with_fields(
        value["capabilities"],
        _CAPABILITY_FIELDS,
        "fake launch V3 capabilities",
    )
    if value["limitations"] != list(_LIMITATIONS):
        raise ValueError("fake launch V3 limitations are invalid")
    effects = _object_with_fields(
        value["effects"], _EFFECT_FIELDS, "fake launch V3 effects"
    )
    if any(item is not False for item in effects.values()):
        raise ValueError("fake launch V3 effects must all be false")
    _sha(value["plan_sha256"], "fake launch V3 plan sha256")
    if value["plan_sha256"] != _self_hash(value, "plan_sha256"):
        raise ValueError("fake launch V3 plan hash is invalid")
    if len(_canonical_json(value)) > _MAXIMUM_PLAN_BYTES:
        raise ValueError("fake launch V3 exceeds maximum bytes")
    return _wrap(_SeparationFakeLaunchPlanV3Record, value)


def _build_separation_fake_worker_result_v2(
    *,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    status: str,
    process_report: Mapping[str, Any],
    signal_report: Mapping[str, Any],
    descriptor_report: Mapping[str, Any],
    checkpoint_report: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
    error: Mapping[str, Any] | None,
) -> _SeparationFakeWorkerResultV2Record:
    """Build one worker-report-only V2 result from a validated V3 plan."""

    if type(fake_launch_plan_v3) is not _SeparationFakeLaunchPlanV3Record:
        raise ValueError("fake result requires an exact V3 plan")
    if status != "complete" or error is not None:
        raise ValueError("fake result V2 supports complete evidence only")
    payload = {
        "schema": _FAKE_RESULT_V2_SCHEMA,
        "policy_id": _FAKE_EXECUTION_POLICY_ID,
        "evidence_scope": "private_development",
        "status": status,
        "backend_scope": "deterministic_transport_fixture_only",
        "evidence_authority": "worker_report_only",
        "run_nonce": fake_launch_plan_v3["run_nonce"],
        "fake_launch_plan_v3_sha256": fake_launch_plan_v3["plan_sha256"],
        "process_report": _plain(process_report),
        "signal_report": _plain(signal_report),
        "descriptor_report": _plain(descriptor_report),
        "checkpoint_report": _plain(checkpoint_report),
        "outputs": [_plain(item) for item in outputs],
        "error": _plain(error) if error is not None else None,
        "effects": _result_effects(),
    }
    return _new_separation_fake_worker_result_v2_record(
        {**payload, "result_sha256": _hash(payload)},
        fake_launch_plan_v3=fake_launch_plan_v3,
    )


def _validate_separation_fake_worker_result_v2_record_shape(
    value: Any,
    *,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> _SeparationFakeWorkerResultV2Record:
    if type(value) is not _SeparationFakeWorkerResultV2Record:
        raise ValueError("fake result V2 must be an exact validated record")
    checked = _new_separation_fake_worker_result_v2_record(
        value,
        fake_launch_plan_v3=fake_launch_plan_v3,
    )
    if _canonical_json(_plain(value)) != _canonical_json(_plain(checked)):
        raise ValueError("fake result V2 changed after validation")
    return value


def _new_separation_fake_worker_result_v2_record(
    document: Mapping[str, Any],
    *,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> _SeparationFakeWorkerResultV2Record:
    if type(fake_launch_plan_v3) is not _SeparationFakeLaunchPlanV3Record:
        raise ValueError("fake result requires an exact V3 plan")
    value = _object_with_fields(document, _RESULT_FIELDS, "fake result V2")
    _validate_path_free(value, "fake result V2")
    if (
        value["schema"] != _FAKE_RESULT_V2_SCHEMA
        or value["policy_id"] != _FAKE_EXECUTION_POLICY_ID
        or value["evidence_scope"] != "private_development"
        or value["backend_scope"]
        != "deterministic_transport_fixture_only"
        or value["evidence_authority"] != "worker_report_only"
        or value["run_nonce"] != fake_launch_plan_v3["run_nonce"]
        or value["fake_launch_plan_v3_sha256"]
        != fake_launch_plan_v3["plan_sha256"]
    ):
        raise ValueError("fake result V2 bindings are invalid")
    _run_nonce(value["run_nonce"])
    process = _process_report(value["process_report"])
    signal_report = _object_with_fields(
        value["signal_report"],
        _SIGNAL_REPORT_FIELDS,
        "fake result V2 signal report",
    )
    descriptor = _object_with_fields(
        value["descriptor_report"],
        _DESCRIPTOR_REPORT_FIELDS,
        "fake result V2 descriptor report",
    )
    checkpoint = _object_with_fields(
        value["checkpoint_report"],
        _CHECKPOINT_REPORT_FIELDS,
        "fake result V2 checkpoint report",
    )
    outputs = _result_outputs(value["outputs"], fake_launch_plan_v3)
    if (
        value["status"] != "complete"
        or value["error"] is not None
        or descriptor != _complete_descriptor_report()
        or signal_report != _expected_post_cpython_signal_report()
        or outputs != _expected_outputs(fake_launch_plan_v3)
    ):
        raise ValueError("complete fake result V2 is invalid")
    _validate_complete_checkpoint(checkpoint, fake_launch_plan_v3)
    if process["process_creation_attempted_by_worker"] is not False:
        raise ValueError("fixed fake worker cannot create processes")
    if value["effects"] != _result_effects():
        raise ValueError("fake result V2 effects are invalid")
    _sha(value["result_sha256"], "fake result V2 sha256")
    if value["result_sha256"] != _self_hash(value, "result_sha256"):
        raise ValueError("fake result V2 hash is invalid")
    if len(_canonical_json(value)) > _MAXIMUM_RESULT_BYTES:
        raise ValueError("fake result V2 exceeds maximum bytes")
    return _wrap(_SeparationFakeWorkerResultV2Record, value)


def _expected_outputs(
    plan: _SeparationFakeLaunchPlanV3Record,
) -> list[dict[str, Any]]:
    return [
        {
            "role": slot["role"],
            "slot_id": slot["slot_id"],
            "artifact_kind": "pcm24_wav",
            "payload_encoding": "lowercase_hex",
            "payload_hex": _fixture_wav_bytes(slot["role"]).hex(),
            "sha256": _hash_bytes(_fixture_wav_bytes(slot["role"])),
            "bytes": len(_fixture_wav_bytes(slot["role"])),
            "geometry": {
                "sample_rate": 8_000,
                "channels": 1,
                "frames": 2,
                "duration_seconds": 0.00025,
            },
        }
        for slot in plan["output_slots"]
    ]


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


def _process_report(value: Any) -> dict[str, Any]:
    report = _object_with_fields(
        value, _PROCESS_REPORT_FIELDS, "fake result V2 process report"
    )
    if (
        type(report["pid"]) is not int
        or report["pid"] <= 0
        or type(report["pgid"]) is not int
        or report["pgid"] <= 0
        or report["pgid"] != report["pid"]
        or report["pgid_equals_pid"] is not True
        or report["process_creation_attempted_by_worker"] is not False
        or report["reported_identifiers_are_signal_authority"] is not False
    ):
        raise ValueError("fake result V2 process report is invalid")
    return report


def _expected_post_cpython_signal_report() -> dict[str, Any]:
    """Return the exact Darwin CPython worker-entry signal contract."""

    return {
        "observation_point": "worker_main_after_cpython_startup",
        "main_thread_mask_empty": True,
        "blocked_signal_names": [],
        "handlers": {
            "SIGHUP": "default",
            "SIGINT": "python_default_int_handler",
            "SIGQUIT": "default",
            "SIGPIPE": "ignored",
            "SIGTERM": "default",
            "SIGCHLD": "default",
            "SIGXFSZ": "ignored",
        },
        "termination_signals_default": True,
        "sigchld_default": True,
        "cpython_runtime_adjustments_observed": True,
        "pre_exec_signal_state_reconstructed": False,
    }


def _result_outputs(
    value: Any,
    plan: _SeparationFakeLaunchPlanV3Record,
) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        raise ValueError("fake result V2 outputs must be an array")
    outputs: list[dict[str, Any]] = []
    for raw in value:
        item = _object_with_fields(
            raw, _RESULT_OUTPUT_FIELDS, "fake result V2 output"
        )
        if (
            item["artifact_kind"] != "pcm24_wav"
            or item["payload_encoding"] != "lowercase_hex"
            or not isinstance(item["payload_hex"], str)
            or len(item["payload_hex"]) > 8_192
            or re.fullmatch(r"(?:[0-9a-f]{2})+", item["payload_hex"]) is None
        ):
            raise ValueError("fake result V2 output payload is invalid")
        payload = bytes.fromhex(item["payload_hex"])
        if (
            type(item["bytes"]) is not int
            or item["bytes"] != len(payload)
            or item["sha256"] != _hash_bytes(payload)
        ):
            raise ValueError("fake result V2 output identity is invalid")
        geometry = _object_with_fields(
            item["geometry"], _GEOMETRY_FIELDS, "fake result V2 geometry"
        )
        if geometry != {
            "sample_rate": 8_000,
            "channels": 1,
            "frames": 2,
            "duration_seconds": 0.00025,
        }:
            raise ValueError("fake result V2 geometry is invalid")
        outputs.append({**item, "geometry": geometry})
    if [item["slot_id"] for item in outputs] != [
        item["slot_id"] for item in plan["output_slots"]
    ]:
        raise ValueError("fake result V2 output slots are invalid")
    return outputs


def _validate_complete_checkpoint(
    value: Mapping[str, Any],
    plan: _SeparationFakeLaunchPlanV3Record,
) -> None:
    bindings = plan["bindings"]
    expected = {
        "sha256": bindings["checkpoint_sha256"],
        "bytes": bindings["checkpoint_bytes"],
        "file_identity_sha256": bindings[
            "checkpoint_file_identity_sha256"
        ],
        "identity_before_hash_sha256": bindings[
            "checkpoint_file_identity_sha256"
        ],
        "identity_after_hash_sha256": bindings[
            "checkpoint_file_identity_sha256"
        ],
        "unchanged": True,
        "full_hash_verified": True,
        "deserialized": False,
    }
    if value != expected:
        raise ValueError("complete fake result V2 checkpoint report is invalid")


def _validate_output_slots(value: Any, roles: Sequence[str]) -> None:
    if not isinstance(value, (list, tuple)) or len(value) != len(roles):
        raise ValueError("fake launch V3 output slots are invalid")
    for index, (role, raw) in enumerate(zip(roles, value), 1):
        item = _object_with_fields(
            raw, _OUTPUT_SLOT_FIELDS, "fake launch V3 output slot"
        )
        if item != {
            "role": role,
            "slot_id": f"stem-{index:02d}",
            "artifact_kind": "pcm24_wav",
            "maximum_bytes": 4_096,
        }:
            raise ValueError("fake launch V3 output slot is invalid")


def _result_effects() -> dict[str, bool]:
    return {
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
    }


def _run_nonce(value: Any) -> str:
    if not isinstance(value, str) or _RUN_NONCE_RE.fullmatch(value) is None:
        raise ValueError("fake execution nonce must be 64 lowercase hex")
    return value


def _self_hash(value: Mapping[str, Any], key: str) -> str:
    payload = _bounded_json_copy(value, "fake execution record")
    payload.pop(key, None)
    return _hash(payload)


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _wrap(record_type: type[Any], value: Mapping[str, Any]) -> Any:
    record = object.__new__(record_type)
    object.__setattr__(record, "_document", _freeze(dict(value)))
    return record


__all__: list[str] = []
