from __future__ import annotations

import ast
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import sunofriend._separation_fake_launch_v2_records as module

from sunofriend._separation_fake_launch_v2_records import (
    _FAKE_LAUNCH_V2_POLICY_ID,
    _FAKE_LAUNCH_V2_SCHEMA,
    _SeparationFakeLaunchPlanV2Record,
    _build_blocked_separation_fake_launch_plan_v2_record,
    _validate_blocked_separation_fake_launch_plan_v2_record_shape,
)
from tests.test_separation_fake_transport_records import _records


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _stat_identity(
    *,
    device: int,
    inode: int,
    byte_count: int,
    executable: bool = False,
) -> dict[str, int]:
    return {
        "device": device,
        "inode": inode,
        "mode": stat.S_IFREG | (0o755 if executable else 0o644),
        "links": 1,
        "owner": 501,
        "group": 20,
        "bytes": byte_count,
        "modified_ns": 1_000_000 + inode,
        "changed_ns": 2_000_000 + inode,
    }


def _plan(tmp_path: Path):
    records = _records(tmp_path)
    request = records[5]
    launch_v1 = records[6]
    plan = _build_blocked_separation_fake_launch_plan_v2_record(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        native_launcher_sha256="3" * 64,
        native_launcher_bytes=2_048,
        native_launcher_stat_identity=_stat_identity(
            device=10,
            inode=101,
            byte_count=2_048,
        ),
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        runtime_executable_stat_identity=_stat_identity(
            device=10,
            inode=102,
            byte_count=4_096,
            executable=True,
        ),
        fake_worker_sha256="2" * 64,
        fake_worker_bytes=8_192,
        fake_worker_stat_identity=_stat_identity(
            device=10,
            inode=103,
            byte_count=8_192,
        ),
    )
    return request, launch_v1, plan


def _build(
    request: Any,
    launch_v1: Any,
    **overrides: Any,
) -> _SeparationFakeLaunchPlanV2Record:
    values = {
        "native_launcher_sha256": "3" * 64,
        "native_launcher_bytes": 2_048,
        "native_launcher_stat_identity": _stat_identity(
            device=10,
            inode=101,
            byte_count=2_048,
        ),
        "runtime_executable_sha256": "1" * 64,
        "runtime_executable_bytes": 4_096,
        "runtime_executable_stat_identity": _stat_identity(
            device=10,
            inode=102,
            byte_count=4_096,
            executable=True,
        ),
        "fake_worker_sha256": "2" * 64,
        "fake_worker_bytes": 8_192,
        "fake_worker_stat_identity": _stat_identity(
            device=10,
            inode=103,
            byte_count=8_192,
        ),
    }
    values.update(overrides)
    return _build_blocked_separation_fake_launch_plan_v2_record(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        **values,
    )


def test_v2_is_exact_immutable_and_permanently_blocked(
    tmp_path: Path,
) -> None:
    request, launch_v1, plan = _plan(tmp_path)

    assert type(plan) is _SeparationFakeLaunchPlanV2Record
    assert _validate_blocked_separation_fake_launch_plan_v2_record_shape(
        plan,
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
    ) is plan
    assert plan["schema"] == _FAKE_LAUNCH_V2_SCHEMA
    assert plan["policy_id"] == _FAKE_LAUNCH_V2_POLICY_ID
    assert plan["schema"] != launch_v1["schema"]
    assert plan["status"] == "blocked"
    assert plan["run_status"] == "not_run"
    assert plan["test_only_worker_start_supported"] is False
    assert plan["test_only_worker_start_permitted"] is False
    assert plan["real_separation_supported"] is False
    assert plan["real_separation_permitted"] is False
    assert plan["run_nonce"] == request["run_nonce"]
    assert plan["decision"]["blockers"] == tuple(
        sorted(set(plan["decision"]["blockers"]))
    )
    assert plan["limitations"] == tuple(
        sorted(set(plan["limitations"]))
    )
    assert all(value is False for value in plan["effects"].values())
    with pytest.raises(TypeError):
        plan["bindings"]["fake_worker_bytes"] = 1
    with pytest.raises(ValueError, match="exact validated"):
        _validate_blocked_separation_fake_launch_plan_v2_record_shape(
            _plain(plan),
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
        )


def test_v2_binds_exact_artifact_hash_size_and_stat_identity(
    tmp_path: Path,
) -> None:
    request, launch_v1, plan = _plan(tmp_path)
    bindings = plan["bindings"]
    artifacts = plan["artifacts"]

    assert bindings["fake_worker_request_sha256"] == (
        request["request_sha256"]
    )
    assert bindings["fake_launch_plan_v1_sha256"] == (
        launch_v1["plan_sha256"]
    )
    assert bindings["checkpoint_sha256"] == (
        request["bindings"]["checkpoint_sha256"]
    )
    assert bindings["checkpoint_file_identity_sha256"] == (
        request["bindings"]["checkpoint_file_identity_sha256"]
    )
    for name in ("native_launcher", "runtime_executable", "fake_worker"):
        artifact = artifacts[name]
        assert bindings[f"{name}_sha256"] == artifact["sha256"]
        assert bindings[f"{name}_bytes"] == artifact["bytes"]
        assert bindings[f"{name}_stat_identity_sha256"] == (
            artifact["stat_identity_sha256"]
        )
        assert artifact["bytes"] == artifact["stat_identity"]["bytes"]
        assert artifact["stat_identity"]["links"] == 1
        assert artifact["measurement_authority"] == (
            "caller_claim_only_not_live_remeasurement"
        )
    assert len(
        {
            (
                artifact["stat_identity"]["device"],
                artifact["stat_identity"]["inode"],
            )
            for artifact in artifacts.values()
        }
    ) == 3


def test_v2_has_fixed_path_free_argv_and_environment(
    tmp_path: Path,
) -> None:
    _request, _launch_v1, plan = _plan(tmp_path)
    policy = plan["argv_environment_policy"]

    assert policy["argv_template"] == (
        "bound_runtime_executable",
        "-I",
        "-B",
        "-S",
        "bound_fake_worker_entrypoint",
    )
    assert policy["environment"] == {
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
    }
    assert policy["shell"] is False
    assert policy["path_search"] is False
    assert policy["preexec_callback"] is False
    assert policy["dynamic_arguments_permitted"] is False
    assert policy["environment_inherited"] is False
    assert policy["python_isolated_mode"] is True
    assert policy["python_environment_variables_relied_upon"] is False
    assert policy["hash_randomization_enabled"] is True
    assert policy["determinism_relies_on_pythonhashseed"] is False
    assert policy["argv_materialized"] is False
    assert policy["path_values_serialized"] is False
    assert "/" not in str(_plain(plan))
    assert "\\" not in str(_plain(plan))


def test_v2_child_only_fd_mapping_preserves_parent_fd345(
    tmp_path: Path,
) -> None:
    request, _launch_v1, plan = _plan(tmp_path)
    descriptor = plan["descriptor_contract"]
    mapping = descriptor["mapping_contract"]

    assert descriptor["observation_scope"] == (
        "pure_record_construction_only"
    )
    assert descriptor["parent_descriptor_table_mutation_forbidden"] is True
    assert descriptor["parent_descriptor_table_changed"] is False
    assert descriptor["parent_logical_fd3_changed"] is False
    assert descriptor["parent_logical_fd4_changed"] is False
    assert descriptor["parent_logical_fd5_changed"] is False
    assert descriptor["child_only_mapping_required"] is True
    assert descriptor["child_only_mapping_attempted"] is False
    assert descriptor["cloexec_default_required"] is True
    assert descriptor["cloexec_default_enabled"] is False
    assert descriptor["unlisted_descriptor_closure_required"] is True
    assert descriptor["unlisted_descriptor_closure_proven"] is False
    assert descriptor["raw_descriptor_values_serialized"] is False
    assert descriptor["logical_descriptors"] == (
        request["descriptor_requirements"]
    )
    assert descriptor["logical_fd345_cross_one_exec_required"] is True
    assert (
        descriptor["logical_fd345_inheritable_at_intended_exec_required"]
        is True
    )
    assert (
        descriptor["logical_fd345_inheritable_at_intended_exec_proven"]
        is False
    )
    assert (
        descriptor["worker_first_user_code_fd345_noninheritable_required"]
        is True
    )
    assert (
        descriptor["worker_first_user_code_fd345_noninheritable_proven"]
        is False
    )
    assert descriptor["worker_first_user_code_action"] == (
        "set_fd345_noninheritable_before_request_parse_or_checkpoint_read"
    )
    assert (
        descriptor["birth_time_or_pre_cpython_noninheritability_proven"]
        is False
    )
    assert descriptor["further_exec_permitted"] is False
    assert descriptor["worker_entry_allowed_descriptors"] == (
        0,
        1,
        2,
        3,
        4,
        5,
    )
    assert descriptor["worker_entry_unlisted_descriptors_allowed"] is False
    assert descriptor["child_file_action_group_order"] == (
        "transport_mapping_actions_1_through_12",
        "stdio_replacement_actions_1_through_3",
    )
    stdio = descriptor["stdio_contract"]
    assert stdio["logical_descriptors"] == (0, 1, 2)
    assert [
        (item["target_descriptor"], item["access"])
        for item in stdio["replacement_actions"]
    ] == [(0, "read_only"), (1, "write_only"), (2, "write_only")]
    assert stdio["native_launcher_owned_null_device_required"] is True
    assert stdio["null_device_name_serialized"] is False
    assert stdio["child_file_actions_attempted"] is False

    assert mapping["source_refs"] == (
        "request_source",
        "result_source",
        "checkpoint_source",
    )
    assert mapping["target_descriptors"] == (3, 4, 5)
    assert mapping["scratch_refs"] == (
        "request_scratch",
        "result_scratch",
        "checkpoint_scratch",
    )
    assert mapping["scratch_floor"] == 6
    assert mapping["scratch_count"] == 3
    assert mapping["sources_distinct_required"] is True
    assert mapping["scratch_distinct_from_sources_required"] is True
    assert mapping["scratch_distinct_from_targets_required"] is True
    assert mapping["scratch_within_nofile_limit_required"] is True
    assert mapping["parent_fd_duplication_permitted"] is False
    assert mapping["source_descriptor_values_serialized"] is False
    actions = mapping["child_file_actions"]
    assert [item["ordinal"] for item in actions] == list(range(1, 13))
    assert [item["operation"] for item in actions[:3]] == ["dup2"] * 3
    assert [item["operation"] for item in actions[3:6]] == ["close"] * 3
    assert [item["source_ref"] for item in actions[3:6]] == list(
        mapping["source_refs"]
    )
    assert [item["operation"] for item in actions[6:9]] == ["dup2"] * 3
    assert [item["target_ref"] for item in actions[6:9]] == [3, 4, 5]
    assert [item["operation"] for item in actions[9:]] == ["close"] * 3


def test_v2_requires_owned_pgid_timeout_reap_and_bounded_errors(
    tmp_path: Path,
) -> None:
    _request, _launch_v1, plan = _plan(tmp_path)
    lifecycle = plan["lifecycle_contract"]
    errors = plan["error_taxonomy"]

    assert lifecycle["timeout_seconds"] == 5
    assert lifecycle["term_grace_seconds"] == 1
    assert lifecycle["clock_source"] == "monotonic"
    assert lifecycle["single_absolute_deadline_required"] is True
    assert lifecycle["single_absolute_deadline_established"] is False
    assert lifecycle["process_group_creation"] == "setpgroup_zero"
    assert lifecycle["new_process_group_required"] is True
    assert lifecycle["new_process_group_created"] is False
    assert lifecycle["pgid_equals_pid_required"] is True
    assert lifecycle["pgid_equals_pid_proven"] is False
    assert lifecycle["process_group_identifier_serialized"] is False
    assert lifecycle["exact_pid_ownership_required"] is True
    assert lifecycle["exact_pid_owned"] is False
    assert lifecycle["required_signal_mask"] == ()
    assert {
        "SIGCHLD",
        "SIGINT",
        "SIGPIPE",
        "SIGTERM",
    }.issubset(set(lifecycle["required_signal_defaults"]))
    assert "SIGKILL" not in lifecycle["required_signal_defaults"]
    assert "SIGSTOP" not in lifecycle["required_signal_defaults"]
    assert (
        lifecycle["parent_sigchld_disposition_compatibility_required"]
        is True
    )
    assert lifecycle["required_parent_sigchld_disposition"] == (
        "reap_compatible_not_sig_ign_or_nocldwait"
    )
    assert (
        lifecycle["parent_sigchld_disposition_compatibility_proven"]
        is False
    )
    assert lifecycle["termination_target"] == "owned_process_group_only"
    assert lifecycle["timeout_sequence"] == (
        "wait_for_owned_pid_until_timeout",
        "signal_owned_process_group_term",
        "wait_for_term_grace",
        "signal_owned_process_group_kill",
        "reap_exact_owned_pid",
        "verify_no_owned_process_remains",
    )
    assert lifecycle["reap_required"] is True
    assert lifecycle["reap_completed"] is False
    assert lifecycle["supervised_unreaped_is_terminal"] is False
    assert lifecycle["orphan_absence_required"] is True
    assert lifecycle["orphan_absence_proven"] is False

    assert errors["implemented"] is False
    assert errors["unknown_codes_permitted"] is False
    assert errors["messages_path_free_required"] is True
    assert errors["worker_result_channel"] == "logical_fd4_only"
    assert errors["worker_result_codes"] == tuple(
        sorted(set(errors["worker_result_codes"]))
    )
    assert errors["parent_terminal_receipt_channel"] == (
        "parent_owned_terminal_receipt_only"
    )
    assert errors["parent_terminal_receipt_implemented"] is False
    assert errors["parent_lifecycle_codes"] == tuple(
        sorted(set(errors["parent_lifecycle_codes"]))
    )
    assert errors["primary_failure_preserved_required"] is True
    assert errors["cleanup_failures_accumulated_required"] is True
    assert errors["terminal_receipt_multiple_failures_required"] is True
    assert {
        "artifact_identity_changed",
        "checkpoint_remeasurement_failed",
        "descriptor_cleanup_failed",
        "exec_path_identity_race",
        "kill_signal_failed",
        "lease_release_failed",
        "orphan_not_excluded",
        "process_group_failed",
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
        "term_signal_failed",
        "timeout_kill_failed",
        "worker_remeasurement_failed",
    }.issubset(set(errors["parent_lifecycle_codes"]))
    assert {
        "checkpoint_identity_mismatch",
        "descriptor_contract_violation",
        "request_invalid",
    }.issubset(set(errors["worker_result_codes"]))


def test_v2_authority_absences_and_state_are_explicit(
    tmp_path: Path,
) -> None:
    _request, _launch_v1, plan = _plan(tmp_path)
    authority = plan["authority"]
    output = plan["output_contract"]
    machine = plan["state_machine"]
    blockers = set(plan["decision"]["blockers"])

    assert authority["serialized_plan_is_execution_authority"] is False
    assert authority["fake_launch_v1_is_execution_authority"] is False
    assert authority["run_nonce_present"] is True
    for key, value in authority.items():
        if key not in {"policy_id", "run_nonce_present"}:
            assert value is False
    assert {
        "fresh_parent_run_nonce_not_proven",
        "run_nonce_single_use_not_proven",
        "live_lease_authority_not_present",
        "live_reservation_authority_not_present",
        "noncopyable_run_authority_not_present",
        "native_launcher_build_receipt_not_present",
        "native_launcher_build_provenance_unproven",
        "loaded_native_extension_identity_unproven",
        "runtime_path_exec_toctou_unresolved",
        "worker_script_open_toctou_unresolved",
        "child_only_descriptor_mapping_not_implemented",
        "worker_first_user_code_fd345_cloexec_hardening_not_proven",
        "timeout_and_reap_not_implemented",
        "new_envelope_and_result_schemas_not_implemented",
        "parent_quarantine_materialization_not_implemented",
    }.issubset(blockers)
    assert all(value is False for value in plan["capabilities"].values())

    assert output["child_output_path_serialized"] is False
    assert output["child_output_directory_descriptor_supplied"] is False
    assert output["child_output_file_descriptor_supplied"] is False
    assert output["payload_channel"] == "bounded_logical_fd4_only"
    assert output["payload_maximum_bytes"] == 1_048_576
    assert output["child_creates_files"] is False
    assert output["parent_validates_payload_before_materialization"] is True
    assert output["parent_materializes_private_quarantine"] is True
    assert output["parent_reopens_and_verifies_quarantine"] is True
    assert output["parent_materialization_implemented"] is False
    assert output["fake_envelope_v1_binds_launch_v2"] is False
    assert output["fake_result_v1_binds_launch_v2"] is False
    assert output["new_envelope_schema_required"] is True
    assert output["new_result_schema_required"] is True

    assert machine["initial_state"] == "blocked"
    assert machine["current_state"] == "blocked"
    assert machine["run_state"] == "not_run"
    assert machine["executed_transitions"] == ()
    assert machine["transitions_supported"] is False
    assert machine["transitions_permitted"] is False
    first = machine["future_transition_graph"][0]
    assert first == {
        "from_state": "blocked",
        "to_state": "admitted",
        "trigger": "new_schema_with_live_authority",
    }
    assert plan["effects"]["process_started"] is False
    assert plan["effects"]["worker_started"] is False
    reap_failure = next(
        item
        for item in machine["future_transition_graph"]
        if item["trigger"] == "reap_failure"
    )
    assert reap_failure["to_state"] == "supervised_unreaped"
    assert "supervised_unreaped" not in machine["terminal_states"]


def test_v2_rejects_artifact_mismatch_alias_and_invalid_stat(
    tmp_path: Path,
) -> None:
    request, launch_v1, _plan_value = _plan(tmp_path)

    with pytest.raises(ValueError, match="does not match fake launch V1"):
        _build(
            request,
            launch_v1,
            runtime_executable_sha256="4" * 64,
        )
    with pytest.raises(ValueError, match="distinct file nodes"):
        _build(
            request,
            launch_v1,
            fake_worker_stat_identity=_stat_identity(
                device=10,
                inode=102,
                byte_count=8_192,
            ),
        )
    with pytest.raises(ValueError, match="required file"):
        invalid = _stat_identity(
            device=10,
            inode=102,
            byte_count=4_096,
            executable=False,
        )
        _build(
            request,
            launch_v1,
            runtime_executable_stat_identity=invalid,
        )
    with pytest.raises(ValueError, match="required file"):
        invalid = _stat_identity(
            device=10,
            inode=101,
            byte_count=2_048,
        )
        invalid["links"] = 2
        _build(
            request,
            launch_v1,
            native_launcher_stat_identity=invalid,
        )
    with pytest.raises(ValueError, match="required file"):
        invalid = _stat_identity(
            device=10,
            inode=103,
            byte_count=8_192,
        )
        invalid["mode"] = stat.S_IFREG | 0o666
        _build(
            request,
            launch_v1,
            fake_worker_stat_identity=invalid,
        )


def test_v2_rejects_mismatched_exact_v1_records(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _records(first_dir)
    second = _records(second_dir)

    with pytest.raises(ValueError, match="does not bind the exact"):
        _build(first[5], second[6])


def test_v2_rejects_policy_and_self_hash_tampering(
    tmp_path: Path,
) -> None:
    request, launch_v1, plan = _plan(tmp_path)
    document = _plain(plan)
    document["plan_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="plan hash is invalid"):
        module._new_blocked_separation_fake_launch_plan_v2_record(
            document,
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
        )

    document = _plain(plan)
    document["authority"]["native_build_receipt_present"] = True
    payload = dict(document)
    payload.pop("plan_sha256")
    document["plan_sha256"] = module._hash(payload)
    with pytest.raises(ValueError, match="authority is invalid"):
        module._new_blocked_separation_fake_launch_plan_v2_record(
            document,
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
        )


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_v2_record_module_has_no_effectful_surface() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "asyncio",
        "ctypes",
        "fcntl",
        "http",
        "importlib",
        "multiprocessing",
        "onnxruntime",
        "os",
        "pickle",
        "requests",
        "runpy",
        "safetensors",
        "socket",
        "subprocess",
        "torch",
        "urllib",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "dup",
        "dup2",
        "eval",
        "exec",
        "fork",
        "load",
        "loads",
        "open",
        "popen",
        "posix_spawn",
        "posix_spawnp",
        "set_inheritable",
        "spawn",
        "system",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            } & forbidden_imports
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in (
                forbidden_imports
            )
        elif isinstance(node, ast.Call):
            qualified = _qualified_name(node.func)
            assert (
                qualified.rsplit(".", 1)[-1] not in forbidden_calls
                or qualified == "re.compile"
            )
    assert module.__all__ == []
