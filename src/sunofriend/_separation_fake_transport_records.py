"""Pure records for the deterministic fake separation transport.

These private schemas are the future-worker-parseable *test-only* successor
to the permanently blocked worker-request and launch-plan V2 design records.
They can describe one fixed, code-owned transport fixture, but they cannot
start a process, access a descriptor, read audio, deserialize a checkpoint,
import a model, publish output or authorize real separation.  Request and
launch V1 are permanently non-executable; an actual fake executor requires a
new launch schema and separate live authority.

The later parent executor must supply the live authority that these records
deliberately cannot serialize: exact lease and reservation objects, immediate
runtime/checkpoint remeasurement, child creation and parent-observed
quarantine evidence.
"""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TypeVar

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_checkpoint_launch_v2_records import (
    _SeparationLaunchPlanV2Record,
    _validate_blocked_separation_launch_plan_v2_record_shape,
)
from ._separation_checkpoint_transport_records import (
    SeparationWorkerRequestV2Record,
    _validate_separation_worker_request_v2_record_shape,
)
from ._separation_worker_request_v2_values import (
    _bounded_json_copy,
    _object_with_fields,
    _sha,
    _validate_path_free,
    _validated_roles,
)


_FAKE_REQUEST_SCHEMA = "sunofriend.separation-fake-worker-request.v1"
_FAKE_LAUNCH_SCHEMA = "sunofriend.separation-fake-launch-plan.v1"
_FAKE_RESULT_SCHEMA = "sunofriend.separation-fake-worker-result.v1"
_FAKE_POLICY_ID = "private-deterministic-transport-fixture-v1"
_FAKE_FIXTURE_ID = "code-owned-two-frame-pcm24-v1"
_FAKE_DESCRIPTOR_POLICY_ID = "child-only-logical-fd345-v1"
_FAKE_PROCESS_POLICY_ID = "native-close-all-launcher-required-v1"

_FAKE_FRAME_HEADER_BYTES = 16
_FAKE_REQUEST_MAXIMUM_FRAME_BYTES = 65_536
_FAKE_RESULT_MAXIMUM_FRAME_BYTES = 1_048_576
_MAX_LAUNCH_BYTES = 65_536
_MAX_ARTIFACT_BYTES = 4_096
_MAX_RUNTIME_ARTIFACT_BYTES = 1_073_741_824
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_RE = re.compile(r"^(?:[0-9a-f]{2})+$")
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_REQUEST_FIELDS = frozenset(
    """
    schema policy_id evidence_scope status run_status backend_scope
    test_only_execution_supported test_only_execution_permitted
    real_separation_supported real_separation_permitted historical_design
    run_nonce bindings roles seed fixture output_slots descriptor_requirements
    limitations effects request_sha256
    """.split()
)
_HISTORICAL_FIELDS = frozenset(
    """
    worker_request_v2_sha256 blocked_launch_plan_v2_sha256
    blocked_v2_is_execution_authority purpose
    """.split()
)
_REQUEST_BINDING_FIELDS = frozenset(
    """
    worker_request_v1_sha256 preflight_sha256
    separation_request_fingerprint_sha256 worker_request_v2_sha256
    blocked_launch_plan_v2_sha256 lease_observation_sha256
    checkpoint_inspection_sha256 checkpoint_sha256 checkpoint_bytes
    checkpoint_file_identity_sha256 runtime_artifact_sha256
    runtime_parent_measurements_sha256
    """.split()
)
_FIXTURE_FIELDS = frozenset(
    """
    fixture_id generation source_audio_read checkpoint_deserialized
    model_imported inference_started
    """.split()
)
_OUTPUT_SLOT_FIELDS = frozenset("role slot_id artifact_kind maximum_bytes".split())
_DESCRIPTOR_FIELDS = frozenset(
    "logical_descriptor purpose direction access maximum_bytes".split()
)
_PREPARED_EFFECT_FIELDS = frozenset(
    """
    filesystem_accessed request_materialized result_channel_created
    checkpoint_descriptor_installed process_started worker_started
    checkpoint_remeasured_in_child checkpoint_deserialized model_imported
    inference_started network_used audio_read outputs_created
    quarantine_created files_written publication_permitted
    acceptance_eligible promotion_eligible
    """.split()
)

_LAUNCH_FIELDS = frozenset(
    """
    schema policy_id evidence_scope status run_status backend_scope
    test_only_worker_start_supported test_only_worker_start_permitted
    real_separation_supported real_separation_permitted
    run_nonce fake_worker_request_sha256 runtime_identity descriptor_policy
    process_policy decision limitations effects plan_sha256
    """.split()
)
_RUNTIME_IDENTITY_FIELDS = frozenset(
    """
    runtime_executable_sha256 runtime_executable_bytes
    fake_worker_sha256 fake_worker_bytes
    """.split()
)
_DESCRIPTOR_POLICY_FIELDS = frozenset(
    """
    policy_id parent_descriptor_table_mutation_forbidden
    child_only_mapping_required child_only_mapping_proven
    inherit_unlisted_descriptors_required
    inherit_unlisted_descriptors_proven raw_descriptor_values_serialized
    logical_descriptors
    """.split()
)
_PROCESS_POLICY_FIELDS = frozenset(
    """
    policy_id process_api_required process_api_implemented shell path_search
    preexec_callback native_close_all_launcher_required
    native_close_all_launcher_implemented
    fixed_worker_fd_hygiene_required fixed_worker_fd_hygiene_proven
    required_environment
    request_maximum_bytes result_maximum_bytes timeout_seconds
    argv_serialized
    """.split()
)
_LAUNCH_DECISION_FIELDS = frozenset("status run_status blockers".split())
_LAUNCH_BLOCKERS = (
    "child_only_logical_mapping_not_proven",
    "exact_preexec_checkpoint_remeasurement_not_performed",
    "fresh_parent_run_nonce_not_proven",
    "live_lease_and_reservation_authority_not_present",
    "native_close_all_launcher_not_implemented",
    "parent_quarantine_verification_not_performed",
    "unlisted_descriptor_closure_not_proven",
)

_RESULT_FIELDS = frozenset(
    """
    schema policy_id evidence_scope status backend_scope evidence_authority
    run_nonce fake_worker_request_sha256 fake_launch_plan_sha256
    descriptor_report checkpoint_report outputs error effects result_sha256
    """.split()
)
_DESCRIPTOR_REPORT_FIELDS = frozenset(
    """
    fd3_noninheritable fd3_read_only fd4_noninheritable fd4_write_only
    fd5_noninheritable fd5_read_only unexpected_open_descriptors
    offset_independent_checkpoint_reader
    """.split()
)
_CHECKPOINT_REPORT_FIELDS = frozenset(
    """
    sha256 bytes file_identity_sha256 identity_before_hash_sha256
    identity_after_hash_sha256 unchanged full_hash_verified
    deserialized
    """.split()
)
_RESULT_OUTPUT_FIELDS = frozenset(
    """
    role slot_id artifact_kind payload_encoding payload_hex sha256 bytes
    geometry
    """.split()
)
_GEOMETRY_FIELDS = frozenset(
    "sample_rate channels frames duration_seconds".split()
)
_ERROR_FIELDS = frozenset("code message retryable".split())
_RESULT_EFFECT_FIELDS = frozenset(
    """
    process_started worker_started checkpoint_remeasured_in_child
    checkpoint_deserialized model_imported inference_started network_used
    audio_read output_payloads_generated output_files_created
    publication_permitted acceptance_eligible promotion_eligible
    """.split()
)

_REQUEST_LIMITATIONS = (
    "test_only_transport_fixture_not_source_separation",
    "blocked_v2_records_are_historical_bindings_not_execution_authority",
    "fake_request_v1_is_permanently_non_executable",
    "live_lease_reservation_and_descriptor_authority_are_not_serialized",
    "run_nonce_shape_does_not_prove_parent_freshness_or_single_use",
    "source_audio_is_not_available_to_the_fake_worker",
    "checkpoint_bytes_must_be_hashed_but_never_deserialized",
    "real_backend_model_inference_publication_acceptance_and_promotion_forbidden",
)
_LAUNCH_LIMITATIONS = (
    "serialized_plan_does_not_prove_live_parent_authority",
    "fake_launch_v1_is_permanently_non_executable",
    "fixed_fake_worker_only",
    "native_close_all_launcher_is_required_but_not_implemented",
    "child_only_mapping_and_unlisted_descriptor_closure_are_unproven",
    "runtime_and_checkpoint_remeasurement_are_future_executor_responsibilities",
    "actual_fake_executor_requires_a_new_launch_schema",
    "real_backend_model_inference_publication_acceptance_and_promotion_forbidden",
)

_RecordT = TypeVar("_RecordT", bound="_Record")


@dataclass(frozen=True, init=False)
class _Record(Mapping[str, Any]):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


class _SeparationFakeWorkerRequestRecord(_Record):
    """Exact prepared request for only the deterministic transport fixture."""


class _SeparationFakeLaunchPlanRecord(_Record):
    """Exact test-only launch plan; serialized bytes are not live authority."""


class _SeparationFakeWorkerResultRecord(_Record):
    """Exact worker-authored result, not parent verification evidence."""


def _build_separation_fake_worker_request(
    *,
    worker_request_v2: SeparationWorkerRequestV2Record,
    blocked_launch_plan_v2: _SeparationLaunchPlanV2Record,
    run_nonce: str,
) -> _SeparationFakeWorkerRequestRecord:
    request_v2 = _validate_separation_worker_request_v2_record_shape(
        worker_request_v2
    )
    launch_v2 = _validate_blocked_separation_launch_plan_v2_record_shape(
        blocked_launch_plan_v2
    )
    if (
        launch_v2["bindings"]["worker_request_v2_sha256"]
        != request_v2["request_sha256"]
    ):
        raise ValueError("blocked launch V2 does not bind worker request V2")
    source_bindings = _plain(launch_v2["bindings"])
    bindings = {
        "worker_request_v1_sha256": source_bindings[
            "worker_request_sha256"
        ],
        "preflight_sha256": source_bindings["preflight_sha256"],
        "separation_request_fingerprint_sha256": source_bindings[
            "separation_request_fingerprint_sha256"
        ],
        "worker_request_v2_sha256": request_v2["request_sha256"],
        "blocked_launch_plan_v2_sha256": launch_v2["plan_sha256"],
        "lease_observation_sha256": source_bindings[
            "lease_observation_sha256"
        ],
        "checkpoint_inspection_sha256": source_bindings[
            "checkpoint_inspection_sha256"
        ],
        "checkpoint_sha256": source_bindings["checkpoint_sha256"],
        "checkpoint_bytes": source_bindings["checkpoint_bytes"],
        "checkpoint_file_identity_sha256": source_bindings[
            "checkpoint_file_identity_sha256"
        ],
        "runtime_artifact_sha256": source_bindings[
            "runtime_artifact_sha256"
        ],
        "runtime_parent_measurements_sha256": source_bindings[
            "runtime_parent_measurements_sha256"
        ],
    }
    roles = list(request_v2["logical_request"]["roles"])
    output_slots = _output_slots(roles)
    payload = {
        "schema": _FAKE_REQUEST_SCHEMA,
        "policy_id": _FAKE_POLICY_ID,
        "evidence_scope": "private_development",
        "status": "prepared",
        "run_status": "not_run",
        "backend_scope": "deterministic_transport_fixture_only",
        "test_only_execution_supported": False,
        "test_only_execution_permitted": False,
        "real_separation_supported": False,
        "real_separation_permitted": False,
        "run_nonce": _run_nonce(run_nonce),
        "historical_design": {
            "worker_request_v2_sha256": request_v2["request_sha256"],
            "blocked_launch_plan_v2_sha256": launch_v2["plan_sha256"],
            "blocked_v2_is_execution_authority": False,
            "purpose": "design_hash_continuity_only",
        },
        "bindings": bindings,
        "roles": roles,
        "seed": request_v2["logical_request"]["seed"],
        "fixture": {
            "fixture_id": _FAKE_FIXTURE_ID,
            "generation": "code_owned_two_frame_pcm24_per_role",
            "source_audio_read": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "inference_started": False,
        },
        "output_slots": output_slots,
        "descriptor_requirements": _logical_descriptor_rows(),
        "limitations": list(_REQUEST_LIMITATIONS),
        "effects": _all_false(_PREPARED_EFFECT_FIELDS),
    }
    return _new_request({**payload, "request_sha256": _hash(payload)})


def _build_separation_fake_launch_plan(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    runtime_executable_sha256: str,
    runtime_executable_bytes: int,
    fake_worker_sha256: str,
    fake_worker_bytes: int,
) -> _SeparationFakeLaunchPlanRecord:
    request = _validate_fake_worker_request_shape(fake_worker_request)
    runtime_identity = {
        "runtime_executable_sha256": _sha(
            runtime_executable_sha256, "runtime executable sha256"
        ),
        "runtime_executable_bytes": _bounded_bytes(
            runtime_executable_bytes,
            "runtime executable bytes",
            _MAX_RUNTIME_ARTIFACT_BYTES,
        ),
        "fake_worker_sha256": _sha(
            fake_worker_sha256, "fake worker sha256"
        ),
        "fake_worker_bytes": _bounded_bytes(
            fake_worker_bytes,
            "fake worker bytes",
            _MAX_RUNTIME_ARTIFACT_BYTES,
        ),
    }
    descriptor_policy = {
        "policy_id": _FAKE_DESCRIPTOR_POLICY_ID,
        "parent_descriptor_table_mutation_forbidden": True,
        "child_only_mapping_required": True,
        "child_only_mapping_proven": False,
        "inherit_unlisted_descriptors_required": False,
        "inherit_unlisted_descriptors_proven": False,
        "raw_descriptor_values_serialized": False,
        "logical_descriptors": _logical_descriptor_rows(),
    }
    process_policy = {
        "policy_id": _FAKE_PROCESS_POLICY_ID,
        "process_api_required": "native_close_all_launcher",
        "process_api_implemented": False,
        "shell": False,
        "path_search": False,
        "preexec_callback": False,
        "native_close_all_launcher_required": True,
        "native_close_all_launcher_implemented": False,
        "fixed_worker_fd_hygiene_required": True,
        "fixed_worker_fd_hygiene_proven": False,
        "required_environment": [
            "lang_c_utf8",
            "pythonhashseed_zero",
            "pythondontwritebytecode",
            "pythonno_usersite",
            "tz_utc",
        ],
        "request_maximum_bytes": _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        "result_maximum_bytes": _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        "timeout_seconds": 5,
        "argv_serialized": False,
    }
    payload = {
        "schema": _FAKE_LAUNCH_SCHEMA,
        "policy_id": _FAKE_POLICY_ID,
        "evidence_scope": "private_development",
        "status": "blocked",
        "run_status": "not_run",
        "backend_scope": "deterministic_transport_fixture_only",
        "test_only_worker_start_supported": False,
        "test_only_worker_start_permitted": False,
        "real_separation_supported": False,
        "real_separation_permitted": False,
        "run_nonce": request["run_nonce"],
        "fake_worker_request_sha256": request["request_sha256"],
        "runtime_identity": runtime_identity,
        "descriptor_policy": descriptor_policy,
        "process_policy": process_policy,
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "blockers": list(_LAUNCH_BLOCKERS),
        },
        "limitations": list(_LAUNCH_LIMITATIONS),
        "effects": _all_false(_PREPARED_EFFECT_FIELDS),
    }
    return _new_launch({**payload, "plan_sha256": _hash(payload)})


def _build_separation_fake_worker_result(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan: _SeparationFakeLaunchPlanRecord,
    status: str,
    descriptor_report: Mapping[str, Any],
    checkpoint_report: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
    error: Mapping[str, Any] | None,
) -> _SeparationFakeWorkerResultRecord:
    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch = _validate_fake_launch_plan_shape(fake_launch_plan)
    if launch["fake_worker_request_sha256"] != request["request_sha256"]:
        raise ValueError("fake launch plan does not bind fake worker request")
    if launch["run_nonce"] != request["run_nonce"]:
        raise ValueError("fake launch plan nonce does not bind fake worker request")
    payload = {
        "schema": _FAKE_RESULT_SCHEMA,
        "policy_id": _FAKE_POLICY_ID,
        "evidence_scope": "private_development",
        "status": status,
        "backend_scope": "deterministic_transport_fixture_only",
        "evidence_authority": "worker_report_only",
        "run_nonce": request["run_nonce"],
        "fake_worker_request_sha256": request["request_sha256"],
        "fake_launch_plan_sha256": launch["plan_sha256"],
        "descriptor_report": _plain(descriptor_report),
        "checkpoint_report": _plain(checkpoint_report),
        "outputs": [_plain(item) for item in outputs],
        "error": _plain(error) if error is not None else None,
        "effects": _result_effects(status),
    }
    return _new_result(
        {**payload, "result_sha256": _hash(payload)},
        request=request,
        launch=launch,
    )


def _validate_fake_worker_request_shape(
    value: Any,
) -> _SeparationFakeWorkerRequestRecord:
    return _revalidate_exact(value, _SeparationFakeWorkerRequestRecord, _new_request)


def _validate_fake_launch_plan_shape(
    value: Any,
) -> _SeparationFakeLaunchPlanRecord:
    return _revalidate_exact(value, _SeparationFakeLaunchPlanRecord, _new_launch)


def _validate_fake_worker_result_shape(
    value: Any,
    *,
    request: _SeparationFakeWorkerRequestRecord,
    launch: _SeparationFakeLaunchPlanRecord,
) -> _SeparationFakeWorkerResultRecord:
    if type(value) is not _SeparationFakeWorkerResultRecord:
        raise ValueError("fake worker result must be an exact validated record")
    checked = _new_result(value, request=request, launch=launch)
    if _canonical_json(_plain(value)) != _canonical_json(_plain(checked)):
        raise ValueError("fake worker result changed after validation")
    return value


def _new_request(
    document: Mapping[str, Any],
) -> _SeparationFakeWorkerRequestRecord:
    value = _object_with_fields(document, _REQUEST_FIELDS, "fake worker request")
    _validate_common_record(value, _FAKE_REQUEST_SCHEMA)
    if (
        value["status"] != "prepared"
        or value["run_status"] != "not_run"
        or value["test_only_execution_supported"] is not False
        or value["test_only_execution_permitted"] is not False
    ):
        raise ValueError("fake worker request execution policy is invalid")
    _run_nonce(value["run_nonce"])
    historical = _object_with_fields(
        value["historical_design"],
        _HISTORICAL_FIELDS,
        "fake request historical design",
    )
    bindings = _request_bindings(value["bindings"])
    if historical != {
        "worker_request_v2_sha256": bindings["worker_request_v2_sha256"],
        "blocked_launch_plan_v2_sha256": bindings[
            "blocked_launch_plan_v2_sha256"
        ],
        "blocked_v2_is_execution_authority": False,
        "purpose": "design_hash_continuity_only",
    }:
        raise ValueError("fake request historical design is invalid")
    roles = _validated_roles(value["roles"])
    seed = value["seed"]
    if seed is not None and type(seed) is not int:
        raise ValueError("fake request seed must be an integer or null")
    fixture = _object_with_fields(
        value["fixture"], _FIXTURE_FIELDS, "fake request fixture"
    )
    if fixture != {
        "fixture_id": _FAKE_FIXTURE_ID,
        "generation": "code_owned_two_frame_pcm24_per_role",
        "source_audio_read": False,
        "checkpoint_deserialized": False,
        "model_imported": False,
        "inference_started": False,
    }:
        raise ValueError("fake request fixture is invalid")
    if value["output_slots"] != _output_slots(roles):
        raise ValueError("fake request output slots are invalid")
    if value["descriptor_requirements"] != _logical_descriptor_rows():
        raise ValueError("fake request descriptor requirements are invalid")
    if value["limitations"] != list(_REQUEST_LIMITATIONS):
        raise ValueError("fake request limitations are invalid")
    _require_all_false(
        value["effects"], _PREPARED_EFFECT_FIELDS, "fake request effects"
    )
    _sha(value["request_sha256"], "fake request sha256")
    if value["request_sha256"] != _self_hash(value, "request_sha256"):
        raise ValueError("fake worker request hash is invalid")
    _bounded_framed_record(
        value,
        _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        "fake worker request",
    )
    return _wrap(_SeparationFakeWorkerRequestRecord, value)


def _new_launch(
    document: Mapping[str, Any],
) -> _SeparationFakeLaunchPlanRecord:
    value = _object_with_fields(document, _LAUNCH_FIELDS, "fake launch plan")
    _validate_common_record(value, _FAKE_LAUNCH_SCHEMA)
    if (
        value["status"] != "blocked"
        or value["run_status"] != "not_run"
        or value["test_only_worker_start_supported"] is not False
        or value["test_only_worker_start_permitted"] is not False
    ):
        raise ValueError("fake launch plan execution policy is invalid")
    _run_nonce(value["run_nonce"])
    _sha(value["fake_worker_request_sha256"], "fake request sha256")
    runtime = _object_with_fields(
        value["runtime_identity"],
        _RUNTIME_IDENTITY_FIELDS,
        "fake launch runtime identity",
    )
    for key, item in runtime.items():
        if key.endswith("_sha256"):
            _sha(item, key)
        else:
            _bounded_bytes(item, key, _MAX_RUNTIME_ARTIFACT_BYTES)
    descriptor_policy = _object_with_fields(
        value["descriptor_policy"],
        _DESCRIPTOR_POLICY_FIELDS,
        "fake launch descriptor policy",
    )
    if descriptor_policy != {
        "policy_id": _FAKE_DESCRIPTOR_POLICY_ID,
        "parent_descriptor_table_mutation_forbidden": True,
        "child_only_mapping_required": True,
        "child_only_mapping_proven": False,
        "inherit_unlisted_descriptors_required": False,
        "inherit_unlisted_descriptors_proven": False,
        "raw_descriptor_values_serialized": False,
        "logical_descriptors": _logical_descriptor_rows(),
    }:
        raise ValueError("fake launch descriptor policy is invalid")
    process_policy = _object_with_fields(
        value["process_policy"],
        _PROCESS_POLICY_FIELDS,
        "fake launch process policy",
    )
    if process_policy != {
        "policy_id": _FAKE_PROCESS_POLICY_ID,
        "process_api_required": "native_close_all_launcher",
        "process_api_implemented": False,
        "shell": False,
        "path_search": False,
        "preexec_callback": False,
        "native_close_all_launcher_required": True,
        "native_close_all_launcher_implemented": False,
        "fixed_worker_fd_hygiene_required": True,
        "fixed_worker_fd_hygiene_proven": False,
        "required_environment": [
            "lang_c_utf8",
            "pythonhashseed_zero",
            "pythondontwritebytecode",
            "pythonno_usersite",
            "tz_utc",
        ],
        "request_maximum_bytes": _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        "result_maximum_bytes": _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        "timeout_seconds": 5,
        "argv_serialized": False,
    }:
        raise ValueError("fake launch process policy is invalid")
    decision = _object_with_fields(
        value["decision"],
        _LAUNCH_DECISION_FIELDS,
        "fake launch decision",
    )
    if decision != {
        "status": "blocked",
        "run_status": "not_run",
        "blockers": list(_LAUNCH_BLOCKERS),
    }:
        raise ValueError("fake launch decision is invalid")
    if value["limitations"] != list(_LAUNCH_LIMITATIONS):
        raise ValueError("fake launch limitations are invalid")
    _require_all_false(
        value["effects"], _PREPARED_EFFECT_FIELDS, "fake launch effects"
    )
    _sha(value["plan_sha256"], "fake launch plan sha256")
    if value["plan_sha256"] != _self_hash(value, "plan_sha256"):
        raise ValueError("fake launch plan hash is invalid")
    _bounded_record(value, _MAX_LAUNCH_BYTES, "fake launch plan")
    return _wrap(_SeparationFakeLaunchPlanRecord, value)


def _new_result(
    document: Mapping[str, Any],
    *,
    request: _SeparationFakeWorkerRequestRecord,
    launch: _SeparationFakeLaunchPlanRecord,
) -> _SeparationFakeWorkerResultRecord:
    request = _validate_fake_worker_request_shape(request)
    launch = _validate_fake_launch_plan_shape(launch)
    value = _object_with_fields(document, _RESULT_FIELDS, "fake worker result")
    _validate_path_free(value, "fake worker result")
    if (
        value["schema"] != _FAKE_RESULT_SCHEMA
        or value["policy_id"] != _FAKE_POLICY_ID
        or value["evidence_scope"] != "private_development"
        or value["backend_scope"] != "deterministic_transport_fixture_only"
        or value["evidence_authority"] != "worker_report_only"
        or value["run_nonce"] != request["run_nonce"]
        or value["run_nonce"] != launch["run_nonce"]
        or value["fake_worker_request_sha256"] != request["request_sha256"]
        or value["fake_launch_plan_sha256"] != launch["plan_sha256"]
    ):
        raise ValueError("fake worker result bindings are invalid")
    if launch["fake_worker_request_sha256"] != request["request_sha256"]:
        raise ValueError("fake result launch and request do not match")
    descriptor = _object_with_fields(
        value["descriptor_report"],
        _DESCRIPTOR_REPORT_FIELDS,
        "fake result descriptor report",
    )
    checkpoint = _object_with_fields(
        value["checkpoint_report"],
        _CHECKPOINT_REPORT_FIELDS,
        "fake result checkpoint report",
    )
    outputs = _result_outputs(value["outputs"], request)
    error = _validated_error(value["error"])
    if value["status"] == "complete":
        if error is not None:
            raise ValueError("complete fake result cannot contain an error")
        if descriptor != _complete_descriptor_report():
            raise ValueError("complete fake result descriptor report is invalid")
        _complete_checkpoint_report(checkpoint, request)
        if outputs != _expected_fixture_outputs(request):
            raise ValueError("complete fake result outputs are not deterministic")
    elif value["status"] == "failed":
        if outputs or error is None:
            raise ValueError("failed fake result requires only an error")
        _failed_checkpoint_report(checkpoint, request)
    else:
        raise ValueError("fake worker result status is invalid")
    if value["effects"] != _result_effects(value["status"]):
        raise ValueError("fake worker result effects are invalid")
    _sha(value["result_sha256"], "fake result sha256")
    if value["result_sha256"] != _self_hash(value, "result_sha256"):
        raise ValueError("fake worker result hash is invalid")
    _run_nonce(value["run_nonce"])
    _bounded_framed_record(
        value,
        _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        "fake worker result",
    )
    return _wrap(_SeparationFakeWorkerResultRecord, value)


def _validate_common_record(value: Mapping[str, Any], schema: str) -> None:
    _validate_path_free(value, "fake transport record")
    if (
        value["schema"] != schema
        or value["policy_id"] != _FAKE_POLICY_ID
        or value["evidence_scope"] != "private_development"
        or value["backend_scope"] != "deterministic_transport_fixture_only"
        or value.get("real_separation_supported") is not False
        or value.get("real_separation_permitted") is not False
    ):
        raise ValueError("fake transport record policy is invalid")


def _request_bindings(value: Any) -> dict[str, Any]:
    bindings = _object_with_fields(
        value, _REQUEST_BINDING_FIELDS, "fake request bindings"
    )
    for key, item in bindings.items():
        if key == "checkpoint_bytes":
            _bounded_bytes(item, key, 8 * 1024 * 1024 * 1024)
        else:
            _sha(item, key)
    return bindings


def _output_slots(roles: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "slot_id": f"stem-{index:02d}",
            "artifact_kind": "pcm24_wav",
            "maximum_bytes": _MAX_ARTIFACT_BYTES,
        }
        for index, role in enumerate(roles, 1)
    ]


def _logical_descriptor_rows() -> list[dict[str, Any]]:
    return [
        {
            "logical_descriptor": 3,
            "purpose": "canonical_fake_transport_envelope",
            "direction": "parent_to_worker",
            "access": "read_only",
            "maximum_bytes": _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        },
        {
            "logical_descriptor": 4,
            "purpose": "bounded_fake_worker_result",
            "direction": "worker_to_parent",
            "access": "write_only",
            "maximum_bytes": _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        },
        {
            "logical_descriptor": 5,
            "purpose": "read_only_checkpoint_hash_fixture",
            "direction": "parent_to_worker",
            "access": "read_only",
            "maximum_bytes": 8 * 1024 * 1024 * 1024,
        },
    ]


def _expected_fixture_outputs(
    request: _SeparationFakeWorkerRequestRecord,
) -> list[dict[str, Any]]:
    slots = request["output_slots"]
    outputs = []
    for slot in slots:
        payload = _fixture_wav_bytes(slot["role"])
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
    sample = hashlib.sha256(role.encode("ascii")).digest()[:6]
    data_bytes = len(sample)
    riff_bytes = 36 + data_bytes
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", riff_bytes),
            b"WAVEfmt ",
            struct.pack("<IHHIIHH", 16, 1, 1, 8_000, 24_000, 3, 24),
            b"data",
            struct.pack("<I", data_bytes),
            sample,
        )
    )


def _result_outputs(
    value: Any,
    request: _SeparationFakeWorkerRequestRecord,
) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        raise ValueError("fake result outputs must be an array")
    outputs = []
    for raw in value:
        item = _object_with_fields(
            raw, _RESULT_OUTPUT_FIELDS, "fake result output"
        )
        if item["artifact_kind"] != "pcm24_wav":
            raise ValueError("fake result output kind is invalid")
        if item["payload_encoding"] != "lowercase_hex":
            raise ValueError("fake result payload encoding is invalid")
        payload_hex = item["payload_hex"]
        if (
            not isinstance(payload_hex, str)
            or len(payload_hex) > _MAX_ARTIFACT_BYTES * 2
            or _HEX_RE.fullmatch(payload_hex) is None
        ):
            raise ValueError("fake result payload is invalid")
        payload = bytes.fromhex(payload_hex)
        if (
            item["bytes"] != len(payload)
            or item["bytes"] > _MAX_ARTIFACT_BYTES
            or item["sha256"] != hashlib.sha256(payload).hexdigest()
        ):
            raise ValueError("fake result payload identity is invalid")
        _geometry(item["geometry"])
        outputs.append(item)
    expected_order = [
        (slot["role"], slot["slot_id"]) for slot in request["output_slots"]
    ]
    if [(item["role"], item["slot_id"]) for item in outputs] not in (
        [],
        expected_order,
    ):
        raise ValueError("fake result outputs are not canonical")
    return outputs


def _geometry(value: Any) -> dict[str, Any]:
    geometry = _object_with_fields(value, _GEOMETRY_FIELDS, "fake geometry")
    if geometry != {
        "sample_rate": 8_000,
        "channels": 1,
        "frames": 2,
        "duration_seconds": 0.00025,
    }:
        raise ValueError("fake output geometry is invalid")
    return geometry


def _complete_descriptor_report() -> dict[str, Any]:
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


def _complete_checkpoint_report(
    value: Mapping[str, Any],
    request: _SeparationFakeWorkerRequestRecord,
) -> None:
    bindings = request["bindings"]
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
        raise ValueError("complete fake checkpoint report is invalid")


def _failed_checkpoint_report(
    value: Mapping[str, Any],
    request: _SeparationFakeWorkerRequestRecord,
) -> None:
    bindings = request["bindings"]
    for key in (
        "sha256",
        "bytes",
        "file_identity_sha256",
    ):
        if value[key] != bindings[f"checkpoint_{key}"]:
            raise ValueError("failed fake checkpoint report is unbound")
    for key in ("identity_before_hash_sha256", "identity_after_hash_sha256"):
        item = value[key]
        if item is not None:
            _sha(item, key)
    for key in ("unchanged", "full_hash_verified", "deserialized"):
        if type(value[key]) is not bool:
            raise ValueError("failed fake checkpoint report is invalid")
    if value["deserialized"] is not False:
        raise ValueError("fake checkpoint must never be deserialized")


def _validated_error(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    error = _object_with_fields(value, _ERROR_FIELDS, "fake result error")
    if (
        not isinstance(error["code"], str)
        or _ERROR_CODE_RE.fullmatch(error["code"]) is None
        or not isinstance(error["message"], str)
        or not error["message"]
        or len(error["message"]) > 1_024
        or type(error["retryable"]) is not bool
    ):
        raise ValueError("fake result error is invalid")
    _validate_path_free(error, "fake result error")
    return error


def _result_effects(status: str) -> dict[str, bool]:
    complete = status == "complete"
    if status not in {"complete", "failed"}:
        complete = False
    return {
        "process_started": True,
        "worker_started": True,
        "checkpoint_remeasured_in_child": complete,
        "checkpoint_deserialized": False,
        "model_imported": False,
        "inference_started": False,
        "network_used": False,
        "audio_read": False,
        "output_payloads_generated": complete,
        "output_files_created": False,
        "publication_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }


def _all_false(fields: frozenset[str]) -> dict[str, bool]:
    return {key: False for key in sorted(fields)}


def _require_all_false(
    value: Any,
    fields: frozenset[str],
    label: str,
) -> None:
    document = _object_with_fields(value, fields, label)
    if any(item is not False for item in document.values()):
        raise ValueError(f"{label} must all be false")


def _bounded_bytes(value: Any, label: str, maximum: int) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError(f"{label} is outside supported bounds")
    return value


def _run_nonce(value: Any) -> str:
    if not isinstance(value, str) or _NONCE_RE.fullmatch(value) is None:
        raise ValueError("fake transport run nonce must be 64 lowercase hex")
    return value


def _bounded_record(value: Mapping[str, Any], maximum: int, label: str) -> None:
    if len(_canonical_json(value)) > maximum:
        raise ValueError(f"{label} exceeds maximum bytes")


def _bounded_framed_record(
    value: Mapping[str, Any],
    maximum_frame_bytes: int,
    label: str,
) -> None:
    _bounded_record(
        value,
        maximum_frame_bytes - _FAKE_FRAME_HEADER_BYTES,
        label,
    )


def _self_hash(value: Mapping[str, Any], key: str) -> str:
    payload = _bounded_json_copy(value, "fake transport record")
    payload.pop(key, None)
    return _hash(payload)


def _wrap(record_type: type[_RecordT], value: Mapping[str, Any]) -> _RecordT:
    record = object.__new__(record_type)
    object.__setattr__(record, "_document", _freeze(dict(value)))
    return record


def _revalidate_exact(
    value: Any,
    record_type: type[_RecordT],
    constructor: Any,
) -> _RecordT:
    if type(value) is not record_type:
        raise ValueError("fake transport value must be an exact validated record")
    checked = constructor(value)
    if _canonical_json(_plain(value)) != _canonical_json(_plain(checked)):
        raise ValueError("fake transport record changed after validation")
    return value


__all__: list[str] = []
