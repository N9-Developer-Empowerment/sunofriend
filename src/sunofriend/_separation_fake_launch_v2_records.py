"""Pure, permanently blocked native fake-launch V2 records.

This private module describes the exact process boundary that a later,
separately audited fake-worker executor would need.  It binds immutable
artifact claims, a fixed argv/environment policy, collision-safe child-only
FD 3/4/5 file actions, and a bounded lifecycle/error state machine.

It deliberately performs no filesystem access, descriptor operation, native
loading, process creation, model operation or publication.  Claimed stat
identities are data, not live measurements.  The existing fake request and
fake launch V1 records remain historical bindings and never become execution
authority.  This V2 record is also permanently non-executable; a future
executor requires a new schema carrying live, non-copyable authority.
"""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_fake_transport_records import (
    _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
    _validate_fake_launch_plan_shape,
    _validate_fake_worker_request_shape,
)
from ._separation_worker_request_v2_values import (
    _bounded_json_copy,
    _object_with_fields,
    _sha,
    _validate_path_free,
)


_FAKE_LAUNCH_V2_SCHEMA = "sunofriend.separation-fake-launch-plan.v2"
_FAKE_LAUNCH_V2_POLICY_ID = (
    "private-blocked-native-fake-launch-contract-v2"
)
_ARGV_ENV_POLICY_ID = "fixed-isolated-fake-worker-invocation-v2"
_DESCRIPTOR_POLICY_ID = "darwin-child-only-close-all-fd345-v2"
_MAPPING_POLICY_ID = "collision-safe-child-scratch-fd345-v2"
_LIFECYCLE_POLICY_ID = "owned-pgid-timeout-reap-v2"
_ERROR_POLICY_ID = "bounded-native-fake-launch-errors-v2"
_AUTHORITY_POLICY_ID = "live-noncopyable-launch-authority-v2"
_STATE_MACHINE_POLICY_ID = "permanently-blocked-native-fake-launch-v2"
_MAXIMUM_PLAN_BYTES = 262_144
_MAXIMUM_ARTIFACT_BYTES = 1_073_741_824
_MAXIMUM_STAT_INTEGER = 2**63 - 1
_RUN_NONCE_RE = re.compile(r"^[0-9a-f]{64}$")


def _fields(value: str) -> frozenset[str]:
    return frozenset(value.split())


_TOP_LEVEL_FIELDS = _fields(
    """
    schema policy_id evidence_scope publication_scope status run_status
    backend_scope test_only_worker_start_supported
    test_only_worker_start_permitted real_separation_supported
    real_separation_permitted run_nonce bindings artifacts
    argv_environment_policy descriptor_contract lifecycle_contract
    output_contract error_taxonomy authority capabilities state_machine
    decision limitations effects plan_sha256
    """
)
_BINDING_FIELDS = _fields(
    """
    fake_worker_request_sha256 fake_launch_plan_v1_sha256
    checkpoint_sha256 checkpoint_bytes checkpoint_file_identity_sha256
    native_launcher_sha256 native_launcher_bytes
    native_launcher_stat_identity_sha256 runtime_executable_sha256
    runtime_executable_bytes runtime_executable_stat_identity_sha256
    fake_worker_sha256 fake_worker_bytes fake_worker_stat_identity_sha256
    """
)
_ARTIFACT_SET_FIELDS = _fields(
    "native_launcher runtime_executable fake_worker"
)
_ARTIFACT_FIELDS = _fields(
    """
    artifact_kind sha256 bytes stat_identity stat_identity_sha256
    measurement_authority
    """
)
_STAT_IDENTITY_FIELDS = _fields(
    """
    device inode mode links owner group bytes modified_ns changed_ns
    """
)
_ARGV_ENV_FIELDS = _fields(
    """
    policy_id shell path_search preexec_callback argv_template
    argv_materialized path_values_serialized dynamic_arguments_permitted
    environment_inherited environment python_isolated_mode
    python_environment_variables_relied_upon working_directory_inherited
    working_directory_serialized hash_randomization_enabled
    determinism_relies_on_pythonhashseed
    """
)
_ENVIRONMENT_FIELDS = _fields("LANG LC_ALL TZ")
_DESCRIPTOR_FIELDS = _fields(
    """
    policy_id observation_scope parent_descriptor_table_mutation_forbidden
    parent_descriptor_table_changed parent_logical_fd3_changed
    parent_logical_fd4_changed parent_logical_fd5_changed
    child_only_mapping_required child_only_mapping_attempted
    cloexec_default_required cloexec_default_enabled
    unlisted_descriptor_closure_required
    unlisted_descriptor_closure_proven raw_descriptor_values_serialized
    logical_descriptors logical_fd345_cross_one_exec_required
    logical_fd345_inheritable_at_intended_exec_required
    logical_fd345_inheritable_at_intended_exec_proven
    worker_first_user_code_fd345_noninheritable_required
    worker_first_user_code_fd345_noninheritable_proven
    worker_first_user_code_action
    birth_time_or_pre_cpython_noninheritability_proven
    further_exec_permitted worker_entry_allowed_descriptors
    worker_entry_unlisted_descriptors_allowed
    child_file_action_group_order stdio_contract mapping_contract
    """
)
_STDIO_FIELDS = _fields(
    """
    policy_id logical_descriptors replacement_actions
    native_launcher_owned_null_device_required
    null_device_name_serialized child_file_actions_attempted
    """
)
_STDIO_ACTION_FIELDS = _fields(
    "ordinal operation target_descriptor access"
)
_MAPPING_FIELDS = _fields(
    """
    policy_id source_refs target_descriptors scratch_refs scratch_floor
    scratch_count scratch_selection_algorithm
    sources_distinct_required
    scratch_distinct_from_sources_required
    scratch_distinct_from_targets_required
    scratch_within_nofile_limit_required
    existing_unlisted_scratch_targets_replaced_by_dup2
    parent_fd_duplication_permitted source_descriptor_values_serialized
    child_file_actions
    """
)
_ACTION_FIELDS = _fields("ordinal operation source_ref target_ref")
_LIFECYCLE_FIELDS = _fields(
    """
    policy_id timeout_seconds term_grace_seconds
    clock_source single_absolute_deadline_required
    single_absolute_deadline_established process_group_creation
    new_process_group_required new_process_group_created
    pgid_equals_pid_required pgid_equals_pid_proven
    process_group_identifier_serialized exact_pid_ownership_required
    exact_pid_owned signal_mask_reset_required required_signal_mask
    signal_mask_reset_proven signal_defaults_required
    required_signal_defaults signal_defaults_proven termination_target
    parent_sigchld_disposition_compatibility_required
    required_parent_sigchld_disposition
    parent_sigchld_disposition_compatibility_proven
    timeout_sequence reap_required reap_completed
    supervised_unreaped_is_terminal orphan_absence_required
    orphan_absence_proven
    """
)
_OUTPUT_FIELDS = _fields(
    """
    policy_id child_output_path_serialized
    child_output_directory_descriptor_supplied
    child_output_file_descriptor_supplied payload_channel
    payload_maximum_bytes child_creates_files
    parent_validates_payload_before_materialization
    parent_materializes_private_quarantine
    parent_reopens_and_verifies_quarantine
    parent_materialization_implemented publication_permitted
    fake_envelope_v1_binds_launch_v2 fake_result_v1_binds_launch_v2
    new_envelope_schema_required new_result_schema_required
    """
)
_ERROR_FIELDS = _fields(
    """
    policy_id implemented unknown_codes_permitted
    messages_path_free_required worker_result_channel worker_result_codes
    parent_terminal_receipt_channel parent_terminal_receipt_implemented
    parent_lifecycle_codes primary_failure_preserved_required
    cleanup_failures_accumulated_required
    terminal_receipt_multiple_failures_required
    """
)
_AUTHORITY_FIELDS = _fields(
    """
    policy_id serialized_plan_is_execution_authority
    fake_launch_v1_is_execution_authority run_nonce_present
    run_nonce_freshness_proven run_nonce_single_use_proven
    live_lease_authority_present live_reservation_authority_present
    noncopyable_run_authority_present native_build_receipt_present
    immediate_native_launcher_remeasurement_performed
    immediate_runtime_remeasurement_performed
    immediate_fake_worker_remeasurement_performed
    native_launcher_build_provenance_proven
    loaded_native_extension_identity_proven
    runtime_exec_toctou_resolved worker_script_open_toctou_resolved
    child_creation_authorized process_start_authorized
    """
)
_CAPABILITY_FIELDS = _fields(
    """
    native_launcher_build_supported native_launcher_load_supported
    artifact_live_remeasurement_supported child_file_actions_supported
    stdio_replacement_supported cloexec_default_supported
    process_group_creation_supported process_start_supported
    worker_start_supported fd3_request_transport_supported
    fd4_result_transport_supported fd5_checkpoint_transport_supported
    timeout_termination_supported exact_reap_supported
    orphan_verification_supported terminal_receipt_supported
    parent_quarantine_materialization_supported fake_execution_supported
    checkpoint_deserialization_supported model_import_supported
    inference_supported real_execution_supported selection_supported
    publication_supported acceptance_supported promotion_supported
    """
)
_STATE_MACHINE_FIELDS = _fields(
    """
    policy_id initial_state current_state run_state states
    future_transition_graph executed_transitions transitions_supported
    transitions_permitted terminal_states
    """
)
_TRANSITION_FIELDS = _fields("from_state to_state trigger")
_DECISION_FIELDS = _fields("status run_status blockers")
_EFFECT_FIELDS = _fields(
    """
    filesystem_accessed native_launcher_loaded descriptor_actions_created
    parent_descriptor_table_changed parent_logical_fd3_changed
    parent_logical_fd4_changed parent_logical_fd5_changed process_started
    worker_started process_group_created signal_sent process_reaped
    orphan_check_performed checkpoint_remeasured_in_child
    checkpoint_deserialized model_imported inference_started network_used
    audio_read output_payloads_generated output_files_created
    quarantine_created files_written publication_permitted
    selection_permitted acceptance_eligible promotion_eligible
    """
)

_ARGV_TEMPLATE = (
    "bound_runtime_executable",
    "-I",
    "-B",
    "-S",
    "bound_fake_worker_entrypoint",
)
_FIXED_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
}
_STDIO_REPLACEMENT_ACTIONS = (
    {
        "ordinal": 1,
        "operation": "open_native_null_device",
        "target_descriptor": 0,
        "access": "read_only",
    },
    {
        "ordinal": 2,
        "operation": "open_native_null_device",
        "target_descriptor": 1,
        "access": "write_only",
    },
    {
        "ordinal": 3,
        "operation": "open_native_null_device",
        "target_descriptor": 2,
        "access": "write_only",
    },
)
_SOURCE_REFS = (
    "request_source",
    "result_source",
    "checkpoint_source",
)
_SCRATCH_REFS = (
    "request_scratch",
    "result_scratch",
    "checkpoint_scratch",
)
_TARGET_DESCRIPTORS = (3, 4, 5)
_CHILD_FILE_ACTIONS = (
    {
        "ordinal": 1,
        "operation": "dup2",
        "source_ref": "request_source",
        "target_ref": "request_scratch",
    },
    {
        "ordinal": 2,
        "operation": "dup2",
        "source_ref": "result_source",
        "target_ref": "result_scratch",
    },
    {
        "ordinal": 3,
        "operation": "dup2",
        "source_ref": "checkpoint_source",
        "target_ref": "checkpoint_scratch",
    },
    {
        "ordinal": 4,
        "operation": "close",
        "source_ref": "request_source",
        "target_ref": None,
    },
    {
        "ordinal": 5,
        "operation": "close",
        "source_ref": "result_source",
        "target_ref": None,
    },
    {
        "ordinal": 6,
        "operation": "close",
        "source_ref": "checkpoint_source",
        "target_ref": None,
    },
    {
        "ordinal": 7,
        "operation": "dup2",
        "source_ref": "request_scratch",
        "target_ref": 3,
    },
    {
        "ordinal": 8,
        "operation": "dup2",
        "source_ref": "result_scratch",
        "target_ref": 4,
    },
    {
        "ordinal": 9,
        "operation": "dup2",
        "source_ref": "checkpoint_scratch",
        "target_ref": 5,
    },
    {
        "ordinal": 10,
        "operation": "close",
        "source_ref": "request_scratch",
        "target_ref": None,
    },
    {
        "ordinal": 11,
        "operation": "close",
        "source_ref": "result_scratch",
        "target_ref": None,
    },
    {
        "ordinal": 12,
        "operation": "close",
        "source_ref": "checkpoint_scratch",
        "target_ref": None,
    },
)
_TIMEOUT_SEQUENCE = (
    "wait_for_owned_pid_until_timeout",
    "signal_owned_process_group_term",
    "wait_for_term_grace",
    "signal_owned_process_group_kill",
    "reap_exact_owned_pid",
    "verify_no_owned_process_remains",
)
_REQUIRED_SIGNAL_DEFAULTS = (
    "SIGABRT",
    "SIGALRM",
    "SIGBUS",
    "SIGCHLD",
    "SIGCONT",
    "SIGEMT",
    "SIGFPE",
    "SIGHUP",
    "SIGILL",
    "SIGINFO",
    "SIGINT",
    "SIGIO",
    "SIGPIPE",
    "SIGPROF",
    "SIGQUIT",
    "SIGSEGV",
    "SIGSYS",
    "SIGTERM",
    "SIGTRAP",
    "SIGTSTP",
    "SIGTTIN",
    "SIGTTOU",
    "SIGURG",
    "SIGUSR1",
    "SIGUSR2",
    "SIGVTALRM",
    "SIGWINCH",
    "SIGXCPU",
    "SIGXFSZ",
)
_WORKER_RESULT_ERROR_CODES = (
    "checkpoint_identity_mismatch",
    "descriptor_contract_violation",
    "fixture_generation_failed",
    "request_invalid",
)
_PARENT_LIFECYCLE_ERROR_CODES = (
    "artifact_identity_changed",
    "authority_invalid",
    "checkpoint_remeasurement_failed",
    "child_descriptor_mapping_failed",
    "cloexec_default_failed",
    "descriptor_cleanup_failed",
    "exec_failed",
    "exec_path_identity_race",
    "kill_signal_failed",
    "lease_release_failed",
    "native_build_unavailable",
    "native_launcher_remeasurement_failed",
    "orphan_not_excluded",
    "process_group_failed",
    "protocol_invalid",
    "quarantine_materialization_failed",
    "quarantine_verification_failed",
    "reap_failed",
    "request_frame_oversize",
    "request_frame_trailing_bytes",
    "request_frame_truncated",
    "result_binding_invalid",
    "result_frame_oversize",
    "result_frame_trailing_bytes",
    "result_frame_truncated",
    "runtime_remeasurement_failed",
    "spawn_failed",
    "term_signal_failed",
    "terminal_verification_failed",
    "timeout_kill_failed",
    "worker_exit_nonzero",
    "worker_remeasurement_failed",
    "worker_signaled",
)
_STATES = (
    "blocked",
    "admitted",
    "spawned",
    "running",
    "terminating",
    "killing",
    "supervised_unreaped",
    "reaped",
    "verified",
    "failed",
)
_FUTURE_TRANSITIONS = (
    {
        "from_state": "blocked",
        "to_state": "admitted",
        "trigger": "new_schema_with_live_authority",
    },
    {
        "from_state": "admitted",
        "to_state": "spawned",
        "trigger": "native_spawn_success",
    },
    {
        "from_state": "admitted",
        "to_state": "failed",
        "trigger": "native_spawn_failure",
    },
    {
        "from_state": "spawned",
        "to_state": "running",
        "trigger": "worker_protocol_started",
    },
    {
        "from_state": "spawned",
        "to_state": "terminating",
        "trigger": "startup_timeout",
    },
    {
        "from_state": "running",
        "to_state": "reaped",
        "trigger": "worker_exit",
    },
    {
        "from_state": "running",
        "to_state": "terminating",
        "trigger": "worker_timeout",
    },
    {
        "from_state": "terminating",
        "to_state": "reaped",
        "trigger": "term_exit",
    },
    {
        "from_state": "terminating",
        "to_state": "killing",
        "trigger": "term_grace_expired",
    },
    {
        "from_state": "killing",
        "to_state": "reaped",
        "trigger": "kill_exit",
    },
    {
        "from_state": "killing",
        "to_state": "supervised_unreaped",
        "trigger": "reap_failure",
    },
    {
        "from_state": "supervised_unreaped",
        "to_state": "reaped",
        "trigger": "later_reap_success",
    },
    {
        "from_state": "reaped",
        "to_state": "verified",
        "trigger": "terminal_verification_complete",
    },
    {
        "from_state": "reaped",
        "to_state": "failed",
        "trigger": "terminal_verification_failure",
    },
)
_BLOCKERS = (
    "child_only_descriptor_mapping_not_implemented",
    "cloexec_default_not_enabled_or_proven",
    "fake_launch_v2_permanently_non_executable",
    "fake_transport_v1_does_not_bind_launch_v2",
    "fake_worker_identity_not_live_remeasured",
    "fresh_parent_run_nonce_not_proven",
    "live_lease_authority_not_present",
    "live_reservation_authority_not_present",
    "loaded_native_extension_identity_unproven",
    "native_launcher_build_provenance_unproven",
    "native_launcher_build_receipt_not_present",
    "native_launcher_identity_not_live_remeasured",
    "new_envelope_and_result_schemas_not_implemented",
    "new_process_group_not_created",
    "noncopyable_run_authority_not_present",
    "parent_quarantine_materialization_not_implemented",
    "run_nonce_single_use_not_proven",
    "runtime_identity_not_live_remeasured",
    "runtime_path_exec_toctou_unresolved",
    "stdio_null_replacement_not_implemented",
    "timeout_and_reap_not_implemented",
    "worker_first_user_code_fd345_cloexec_hardening_not_proven",
    "worker_result_not_received_or_verified",
    "worker_script_open_toctou_unresolved",
)
_LIMITATIONS = (
    "fake_envelope_and_result_v1_do_not_bind_fake_launch_v2",
    "fake_launch_v1_is_historical_and_not_execution_authority",
    "fake_launch_v2_is_permanently_non_executable",
    "fd345_remain_inheritable_until_fixed_worker_first_user_code_hardening",
    "future_execution_requires_a_new_schema_and_audited_native_launcher",
    "live_lease_reservation_and_noncopyable_authority_are_not_serialized",
    "loaded_native_extension_identity_and_build_provenance_are_unproven",
    "native_build_receipt_is_absent",
    "real_backend_model_inference_publication_acceptance_and_promotion_forbidden",
    "runtime_path_exec_identity_cannot_be_proven_by_this_record",
    "serialized_nonce_does_not_prove_freshness_or_single_use",
    "worker_script_open_identity_cannot_be_proven_by_this_record",
)


@dataclass(frozen=True, init=False)
class _SeparationFakeLaunchPlanV2Record(Mapping[str, Any]):
    """Deeply immutable blocked contract; never live launch authority."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_blocked_separation_fake_launch_plan_v2_record(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    native_launcher_sha256: str,
    native_launcher_bytes: int,
    native_launcher_stat_identity: Mapping[str, Any],
    runtime_executable_sha256: str,
    runtime_executable_bytes: int,
    runtime_executable_stat_identity: Mapping[str, Any],
    fake_worker_sha256: str,
    fake_worker_bytes: int,
    fake_worker_stat_identity: Mapping[str, Any],
) -> _SeparationFakeLaunchPlanV2Record:
    """Seal one blocked native-launch design from exact V1 records.

    The supplied artifact identities are claims only.  This pure builder does
    not measure them and cannot prove their liveness or provenance.
    """

    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch_v1 = _validate_fake_launch_plan_shape(fake_launch_plan_v1)
    if (
        launch_v1["fake_worker_request_sha256"]
        != request["request_sha256"]
        or launch_v1["run_nonce"] != request["run_nonce"]
    ):
        raise ValueError("fake launch V1 does not bind the exact fake request")

    native_launcher = _artifact(
        artifact_kind="cpython_native_launcher_extension",
        sha256=native_launcher_sha256,
        byte_count=native_launcher_bytes,
        stat_identity=native_launcher_stat_identity,
        executable=False,
        label="native launcher",
    )
    runtime_executable = _artifact(
        artifact_kind="native_executable",
        sha256=runtime_executable_sha256,
        byte_count=runtime_executable_bytes,
        stat_identity=runtime_executable_stat_identity,
        executable=True,
        label="runtime executable",
    )
    fake_worker = _artifact(
        artifact_kind="regular_file",
        sha256=fake_worker_sha256,
        byte_count=fake_worker_bytes,
        stat_identity=fake_worker_stat_identity,
        executable=False,
        label="fake worker",
    )
    expected_runtime = launch_v1["runtime_identity"]
    if (
        runtime_executable["sha256"]
        != expected_runtime["runtime_executable_sha256"]
        or runtime_executable["bytes"]
        != expected_runtime["runtime_executable_bytes"]
        or fake_worker["sha256"] != expected_runtime["fake_worker_sha256"]
        or fake_worker["bytes"] != expected_runtime["fake_worker_bytes"]
    ):
        raise ValueError(
            "V2 runtime or worker identity does not match fake launch V1"
        )
    artifacts = {
        "native_launcher": native_launcher,
        "runtime_executable": runtime_executable,
        "fake_worker": fake_worker,
    }
    _require_distinct_artifact_nodes(artifacts)
    bindings = _bindings(request, launch_v1, artifacts)
    payload = {
        "schema": _FAKE_LAUNCH_V2_SCHEMA,
        "policy_id": _FAKE_LAUNCH_V2_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "status": "blocked",
        "run_status": "not_run",
        "backend_scope": "deterministic_transport_fixture_only",
        "test_only_worker_start_supported": False,
        "test_only_worker_start_permitted": False,
        "real_separation_supported": False,
        "real_separation_permitted": False,
        "run_nonce": request["run_nonce"],
        "bindings": bindings,
        "artifacts": artifacts,
        "argv_environment_policy": _argv_environment_policy(),
        "descriptor_contract": _descriptor_contract(request),
        "lifecycle_contract": _lifecycle_contract(),
        "output_contract": _output_contract(),
        "error_taxonomy": _error_taxonomy(),
        "authority": _authority(),
        "capabilities": {
            key: False for key in sorted(_CAPABILITY_FIELDS)
        },
        "state_machine": _state_machine(),
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "blockers": list(_BLOCKERS),
        },
        "limitations": list(_LIMITATIONS),
        "effects": {key: False for key in sorted(_EFFECT_FIELDS)},
    }
    return _new_blocked_separation_fake_launch_plan_v2_record(
        {**payload, "plan_sha256": _hash(payload)},
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
    )


def _validate_blocked_separation_fake_launch_plan_v2_record_shape(
    value: Any,
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
) -> _SeparationFakeLaunchPlanV2Record:
    if type(value) is not _SeparationFakeLaunchPlanV2Record:
        raise ValueError(
            "fake launch V2 must be an exact validated record"
        )
    checked = _new_blocked_separation_fake_launch_plan_v2_record(
        value,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
    )
    if _canonical_json(_plain(value)) != _canonical_json(_plain(checked)):
        raise ValueError("fake launch V2 changed after validation")
    return value


def _new_blocked_separation_fake_launch_plan_v2_record(
    document: Mapping[str, Any],
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
) -> _SeparationFakeLaunchPlanV2Record:
    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch_v1 = _validate_fake_launch_plan_shape(fake_launch_plan_v1)
    value = _object_with_fields(
        document, _TOP_LEVEL_FIELDS, "fake launch V2"
    )
    _validate_path_free(value, "fake launch V2")
    if (
        value["schema"] != _FAKE_LAUNCH_V2_SCHEMA
        or value["policy_id"] != _FAKE_LAUNCH_V2_POLICY_ID
        or value["evidence_scope"] != "private_development"
        or value["publication_scope"] != "private_local_contract_evidence"
        or value["status"] != "blocked"
        or value["run_status"] != "not_run"
        or value["backend_scope"]
        != "deterministic_transport_fixture_only"
        or value["test_only_worker_start_supported"] is not False
        or value["test_only_worker_start_permitted"] is not False
        or value["real_separation_supported"] is not False
        or value["real_separation_permitted"] is not False
    ):
        raise ValueError("fake launch V2 policy is invalid")
    _run_nonce(value["run_nonce"])
    if (
        value["run_nonce"] != request["run_nonce"]
        or value["run_nonce"] != launch_v1["run_nonce"]
        or launch_v1["fake_worker_request_sha256"]
        != request["request_sha256"]
    ):
        raise ValueError("fake launch V2 records do not match")

    artifacts = _artifacts(value["artifacts"])
    _require_distinct_artifact_nodes(artifacts)
    expected_runtime = launch_v1["runtime_identity"]
    if (
        artifacts["runtime_executable"]["sha256"]
        != expected_runtime["runtime_executable_sha256"]
        or artifacts["runtime_executable"]["bytes"]
        != expected_runtime["runtime_executable_bytes"]
        or artifacts["fake_worker"]["sha256"]
        != expected_runtime["fake_worker_sha256"]
        or artifacts["fake_worker"]["bytes"]
        != expected_runtime["fake_worker_bytes"]
    ):
        raise ValueError("fake launch V2 artifacts do not match V1")
    if value["bindings"] != _bindings(request, launch_v1, artifacts):
        raise ValueError("fake launch V2 bindings are invalid")
    if value["argv_environment_policy"] != _argv_environment_policy():
        raise ValueError("fake launch V2 argv or environment is invalid")
    if value["descriptor_contract"] != _descriptor_contract(request):
        raise ValueError("fake launch V2 descriptor contract is invalid")
    if value["lifecycle_contract"] != _lifecycle_contract():
        raise ValueError("fake launch V2 lifecycle contract is invalid")
    if value["output_contract"] != _output_contract():
        raise ValueError("fake launch V2 output contract is invalid")
    if value["error_taxonomy"] != _error_taxonomy():
        raise ValueError("fake launch V2 error taxonomy is invalid")
    if value["authority"] != _authority():
        raise ValueError("fake launch V2 authority is invalid")
    capabilities = _object_with_fields(
        value["capabilities"],
        _CAPABILITY_FIELDS,
        "fake launch V2 capabilities",
    )
    if any(item is not False for item in capabilities.values()):
        raise ValueError("fake launch V2 capabilities must all be false")
    if value["state_machine"] != _state_machine():
        raise ValueError("fake launch V2 state machine is invalid")
    decision = _object_with_fields(
        value["decision"], _DECISION_FIELDS, "fake launch V2 decision"
    )
    if decision != {
        "status": "blocked",
        "run_status": "not_run",
        "blockers": list(_BLOCKERS),
    }:
        raise ValueError("fake launch V2 decision is invalid")
    if value["limitations"] != list(_LIMITATIONS):
        raise ValueError("fake launch V2 limitations are invalid")
    effects = _object_with_fields(
        value["effects"], _EFFECT_FIELDS, "fake launch V2 effects"
    )
    if any(item is not False for item in effects.values()):
        raise ValueError("fake launch V2 effects must all be false")
    _sha(value["plan_sha256"], "fake launch V2 plan sha256")
    if value["plan_sha256"] != _self_hash(value, "plan_sha256"):
        raise ValueError("fake launch V2 plan hash is invalid")
    if len(_canonical_json(value)) > _MAXIMUM_PLAN_BYTES:
        raise ValueError("fake launch V2 exceeds maximum bytes")
    record = object.__new__(_SeparationFakeLaunchPlanV2Record)
    object.__setattr__(record, "_document", _freeze(dict(value)))
    return record


def _bindings(
    request: _SeparationFakeWorkerRequestRecord,
    launch_v1: _SeparationFakeLaunchPlanRecord,
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    request_bindings = request["bindings"]
    result = {
        "fake_worker_request_sha256": request["request_sha256"],
        "fake_launch_plan_v1_sha256": launch_v1["plan_sha256"],
        "checkpoint_sha256": request_bindings["checkpoint_sha256"],
        "checkpoint_bytes": request_bindings["checkpoint_bytes"],
        "checkpoint_file_identity_sha256": request_bindings[
            "checkpoint_file_identity_sha256"
        ],
    }
    for name in ("native_launcher", "runtime_executable", "fake_worker"):
        artifact = artifacts[name]
        result[f"{name}_sha256"] = artifact["sha256"]
        result[f"{name}_bytes"] = artifact["bytes"]
        result[f"{name}_stat_identity_sha256"] = artifact[
            "stat_identity_sha256"
        ]
    checked = _object_with_fields(
        result, _BINDING_FIELDS, "fake launch V2 bindings"
    )
    for key, item in checked.items():
        if key.endswith("_sha256"):
            _sha(item, key)
        elif key.endswith("_bytes"):
            _byte_count(item, key)
    return checked


def _artifact(
    *,
    artifact_kind: str,
    sha256: str,
    byte_count: int,
    stat_identity: Mapping[str, Any],
    executable: bool,
    label: str,
) -> dict[str, Any]:
    digest = _sha(sha256, f"{label} sha256")
    if digest == "0" * 64:
        raise ValueError(f"{label} sha256 cannot be all-zero")
    size = _byte_count(byte_count, f"{label} bytes")
    identity = _stat_identity(
        stat_identity,
        expected_bytes=size,
        executable=executable,
        label=f"{label} stat identity",
    )
    return {
        "artifact_kind": artifact_kind,
        "sha256": digest,
        "bytes": size,
        "stat_identity": identity,
        "stat_identity_sha256": _hash(identity),
        "measurement_authority": "caller_claim_only_not_live_remeasurement",
    }


def _artifacts(value: Any) -> dict[str, dict[str, Any]]:
    raw = _object_with_fields(
        value, _ARTIFACT_SET_FIELDS, "fake launch V2 artifacts"
    )
    expected = {
        "native_launcher": (
            "cpython_native_launcher_extension",
            False,
        ),
        "runtime_executable": ("native_executable", True),
        "fake_worker": ("regular_file", False),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, (kind, executable) in expected.items():
        item = _object_with_fields(
            raw[name], _ARTIFACT_FIELDS, f"fake launch V2 {name}"
        )
        if (
            item["artifact_kind"] != kind
            or item["measurement_authority"]
            != "caller_claim_only_not_live_remeasurement"
        ):
            raise ValueError(f"fake launch V2 {name} policy is invalid")
        digest = _sha(item["sha256"], f"{name} sha256")
        if digest == "0" * 64:
            raise ValueError(f"{name} sha256 cannot be all-zero")
        size = _byte_count(item["bytes"], f"{name} bytes")
        identity = _stat_identity(
            item["stat_identity"],
            expected_bytes=size,
            executable=executable,
            label=f"{name} stat identity",
        )
        if item["stat_identity_sha256"] != _hash(identity):
            raise ValueError(f"{name} stat identity hash is invalid")
        result[name] = {
            "artifact_kind": kind,
            "sha256": digest,
            "bytes": size,
            "stat_identity": identity,
            "stat_identity_sha256": item["stat_identity_sha256"],
            "measurement_authority": (
                "caller_claim_only_not_live_remeasurement"
            ),
        }
    return result


def _stat_identity(
    value: Any,
    *,
    expected_bytes: int,
    executable: bool,
    label: str,
) -> dict[str, int]:
    identity = _object_with_fields(value, _STAT_IDENTITY_FIELDS, label)
    checked: dict[str, int] = {}
    for key, item in identity.items():
        if (
            type(item) is not int
            or not 0 <= item <= _MAXIMUM_STAT_INTEGER
        ):
            raise ValueError(f"{label}.{key} is outside supported bounds")
        checked[key] = item
    if (
        checked["device"] == 0
        or checked["inode"] == 0
        or checked["links"] != 1
        or checked["bytes"] != expected_bytes
        or not stat.S_ISREG(checked["mode"])
        or bool(checked["mode"] & 0o022)
        or (executable and not checked["mode"] & 0o111)
    ):
        raise ValueError(f"{label} does not identify the required file")
    return checked


def _require_distinct_artifact_nodes(
    artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    nodes = [
        (
            artifact["stat_identity"]["device"],
            artifact["stat_identity"]["inode"],
        )
        for artifact in artifacts.values()
    ]
    if len(set(nodes)) != len(nodes):
        raise ValueError("fake launch V2 artifacts must be distinct file nodes")


def _argv_environment_policy() -> dict[str, Any]:
    return {
        "policy_id": _ARGV_ENV_POLICY_ID,
        "shell": False,
        "path_search": False,
        "preexec_callback": False,
        "argv_template": list(_ARGV_TEMPLATE),
        "argv_materialized": False,
        "path_values_serialized": False,
        "dynamic_arguments_permitted": False,
        "environment_inherited": False,
        "environment": dict(_FIXED_ENVIRONMENT),
        "python_isolated_mode": True,
        "python_environment_variables_relied_upon": False,
        "working_directory_inherited": False,
        "working_directory_serialized": False,
        "hash_randomization_enabled": True,
        "determinism_relies_on_pythonhashseed": False,
    }


def _descriptor_contract(
    request: _SeparationFakeWorkerRequestRecord,
) -> dict[str, Any]:
    mapping = {
        "policy_id": _MAPPING_POLICY_ID,
        "source_refs": list(_SOURCE_REFS),
        "target_descriptors": list(_TARGET_DESCRIPTORS),
        "scratch_refs": list(_SCRATCH_REFS),
        "scratch_floor": 6,
        "scratch_count": 3,
        "scratch_selection_algorithm": (
            "lowest_three_integers_at_or_above_6_excluding_source_and_"
            "target_values_within_nofile_limit"
        ),
        "sources_distinct_required": True,
        "scratch_distinct_from_sources_required": True,
        "scratch_distinct_from_targets_required": True,
        "scratch_within_nofile_limit_required": True,
        "existing_unlisted_scratch_targets_replaced_by_dup2": True,
        "parent_fd_duplication_permitted": False,
        "source_descriptor_values_serialized": False,
        "child_file_actions": [_plain(item) for item in _CHILD_FILE_ACTIONS],
    }
    stdio = {
        "policy_id": "native-null-stdio-replacement-v2",
        "logical_descriptors": [0, 1, 2],
        "replacement_actions": [
            _plain(item) for item in _STDIO_REPLACEMENT_ACTIONS
        ],
        "native_launcher_owned_null_device_required": True,
        "null_device_name_serialized": False,
        "child_file_actions_attempted": False,
    }
    for action in stdio["replacement_actions"]:
        _object_with_fields(
            action,
            _STDIO_ACTION_FIELDS,
            "fake launch V2 stdio action",
        )
    _object_with_fields(stdio, _STDIO_FIELDS, "fake launch V2 stdio")
    return {
        "policy_id": _DESCRIPTOR_POLICY_ID,
        "observation_scope": "pure_record_construction_only",
        "parent_descriptor_table_mutation_forbidden": True,
        "parent_descriptor_table_changed": False,
        "parent_logical_fd3_changed": False,
        "parent_logical_fd4_changed": False,
        "parent_logical_fd5_changed": False,
        "child_only_mapping_required": True,
        "child_only_mapping_attempted": False,
        "cloexec_default_required": True,
        "cloexec_default_enabled": False,
        "unlisted_descriptor_closure_required": True,
        "unlisted_descriptor_closure_proven": False,
        "raw_descriptor_values_serialized": False,
        "logical_descriptors": _plain(request["descriptor_requirements"]),
        "logical_fd345_cross_one_exec_required": True,
        "logical_fd345_inheritable_at_intended_exec_required": True,
        "logical_fd345_inheritable_at_intended_exec_proven": False,
        "worker_first_user_code_fd345_noninheritable_required": True,
        "worker_first_user_code_fd345_noninheritable_proven": False,
        "worker_first_user_code_action": (
            "set_fd345_noninheritable_before_request_parse_or_checkpoint_read"
        ),
        "birth_time_or_pre_cpython_noninheritability_proven": False,
        "further_exec_permitted": False,
        "worker_entry_allowed_descriptors": [0, 1, 2, 3, 4, 5],
        "worker_entry_unlisted_descriptors_allowed": False,
        "child_file_action_group_order": [
            "transport_mapping_actions_1_through_12",
            "stdio_replacement_actions_1_through_3",
        ],
        "stdio_contract": stdio,
        "mapping_contract": mapping,
    }


def _lifecycle_contract() -> dict[str, Any]:
    return {
        "policy_id": _LIFECYCLE_POLICY_ID,
        "timeout_seconds": 5,
        "term_grace_seconds": 1,
        "clock_source": "monotonic",
        "single_absolute_deadline_required": True,
        "single_absolute_deadline_established": False,
        "process_group_creation": "setpgroup_zero",
        "new_process_group_required": True,
        "new_process_group_created": False,
        "pgid_equals_pid_required": True,
        "pgid_equals_pid_proven": False,
        "process_group_identifier_serialized": False,
        "exact_pid_ownership_required": True,
        "exact_pid_owned": False,
        "signal_mask_reset_required": True,
        "required_signal_mask": [],
        "signal_mask_reset_proven": False,
        "signal_defaults_required": True,
        "required_signal_defaults": list(_REQUIRED_SIGNAL_DEFAULTS),
        "signal_defaults_proven": False,
        "termination_target": "owned_process_group_only",
        "parent_sigchld_disposition_compatibility_required": True,
        "required_parent_sigchld_disposition": (
            "reap_compatible_not_sig_ign_or_nocldwait"
        ),
        "parent_sigchld_disposition_compatibility_proven": False,
        "timeout_sequence": list(_TIMEOUT_SEQUENCE),
        "reap_required": True,
        "reap_completed": False,
        "supervised_unreaped_is_terminal": False,
        "orphan_absence_required": True,
        "orphan_absence_proven": False,
    }


def _output_contract() -> dict[str, Any]:
    return {
        "policy_id": "parent-owned-fd4-payload-quarantine-v2",
        "child_output_path_serialized": False,
        "child_output_directory_descriptor_supplied": False,
        "child_output_file_descriptor_supplied": False,
        "payload_channel": "bounded_logical_fd4_only",
        "payload_maximum_bytes": _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
        "child_creates_files": False,
        "parent_validates_payload_before_materialization": True,
        "parent_materializes_private_quarantine": True,
        "parent_reopens_and_verifies_quarantine": True,
        "parent_materialization_implemented": False,
        "publication_permitted": False,
        "fake_envelope_v1_binds_launch_v2": False,
        "fake_result_v1_binds_launch_v2": False,
        "new_envelope_schema_required": True,
        "new_result_schema_required": True,
    }


def _error_taxonomy() -> dict[str, Any]:
    return {
        "policy_id": _ERROR_POLICY_ID,
        "implemented": False,
        "unknown_codes_permitted": False,
        "messages_path_free_required": True,
        "worker_result_channel": "logical_fd4_only",
        "worker_result_codes": list(_WORKER_RESULT_ERROR_CODES),
        "parent_terminal_receipt_channel": (
            "parent_owned_terminal_receipt_only"
        ),
        "parent_terminal_receipt_implemented": False,
        "parent_lifecycle_codes": list(_PARENT_LIFECYCLE_ERROR_CODES),
        "primary_failure_preserved_required": True,
        "cleanup_failures_accumulated_required": True,
        "terminal_receipt_multiple_failures_required": True,
    }


def _authority() -> dict[str, Any]:
    return {
        "policy_id": _AUTHORITY_POLICY_ID,
        "serialized_plan_is_execution_authority": False,
        "fake_launch_v1_is_execution_authority": False,
        "run_nonce_present": True,
        "run_nonce_freshness_proven": False,
        "run_nonce_single_use_proven": False,
        "live_lease_authority_present": False,
        "live_reservation_authority_present": False,
        "noncopyable_run_authority_present": False,
        "native_build_receipt_present": False,
        "immediate_native_launcher_remeasurement_performed": False,
        "immediate_runtime_remeasurement_performed": False,
        "immediate_fake_worker_remeasurement_performed": False,
        "native_launcher_build_provenance_proven": False,
        "loaded_native_extension_identity_proven": False,
        "runtime_exec_toctou_resolved": False,
        "worker_script_open_toctou_resolved": False,
        "child_creation_authorized": False,
        "process_start_authorized": False,
    }


def _state_machine() -> dict[str, Any]:
    for transition in _FUTURE_TRANSITIONS:
        _object_with_fields(
            transition,
            _TRANSITION_FIELDS,
            "fake launch V2 future transition",
        )
    return {
        "policy_id": _STATE_MACHINE_POLICY_ID,
        "initial_state": "blocked",
        "current_state": "blocked",
        "run_state": "not_run",
        "states": list(_STATES),
        "future_transition_graph": [
            _plain(item) for item in _FUTURE_TRANSITIONS
        ],
        "executed_transitions": [],
        "transitions_supported": False,
        "transitions_permitted": False,
        "terminal_states": ["blocked", "verified", "failed"],
    }


def _byte_count(value: Any, label: str) -> int:
    if (
        type(value) is not int
        or not 0 < value <= _MAXIMUM_ARTIFACT_BYTES
    ):
        raise ValueError(f"{label} is outside supported bounds")
    return value


def _run_nonce(value: Any) -> str:
    if not isinstance(value, str) or _RUN_NONCE_RE.fullmatch(value) is None:
        raise ValueError("fake launch V2 run nonce must be 64 lowercase hex")
    return value


def _self_hash(value: Mapping[str, Any], key: str) -> str:
    payload = _bounded_json_copy(value, "fake launch V2")
    payload.pop(key, None)
    return _hash(payload)


__all__: list[str] = []
