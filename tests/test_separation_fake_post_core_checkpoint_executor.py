from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Callable

import pytest

import sunofriend._separation_fake_executor_darwin as executor
import sunofriend._separation_fake_post_core_checkpoint_failure_records as records
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
from sunofriend._separation_fake_execution_records import (
    _EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    _EXPECTED_FAKE_WORKER_SOURCE_SHA256,
    _build_prepared_separation_fake_launch_plan_v3_record,
    _build_separation_fake_worker_result_v2,
    _expected_outputs,
)
from sunofriend._separation_fake_launch_v2_records import (
    _build_blocked_separation_fake_launch_plan_v2_record,
)
from sunofriend._separation_fake_transport_records import (
    _build_separation_fake_launch_plan,
    _build_separation_fake_worker_request,
    _complete_descriptor_report,
)
from tests.test_separation_fake_post_lease_failure_records import (
    _native_observation,
)
from tests.test_separation_launch_v2_facade import _issue, _prepared


def _stat_identity(
    *,
    inode: int,
    byte_count: int,
    executable: bool = False,
) -> dict[str, int]:
    return {
        "device": 10,
        "inode": inode,
        "mode": stat.S_IFREG | (0o755 if executable else 0o600),
        "links": 1,
        "owner": 501,
        "group": 20,
        "bytes": byte_count,
        "modified_ns": 1_000_000 + inode,
        "changed_ns": 2_000_000 + inode,
    }


def _installed_post_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    after_core: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    fixture, lease, observation, worker_v2, reservation = _prepared(
        tmp_path / "lease"
    )
    checkpoint_launch = _issue(lease, reservation, worker_v2)
    request = _build_separation_fake_worker_request(
        worker_request_v2=worker_v2,
        blocked_launch_plan_v2=checkpoint_launch,
        run_nonce="a" * 64,
    )
    launch_v1 = _build_separation_fake_launch_plan(
        fake_worker_request=request,
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        fake_worker_sha256=_EXPECTED_FAKE_WORKER_SOURCE_SHA256,
        fake_worker_bytes=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    )
    launch_v2 = _build_blocked_separation_fake_launch_plan_v2_record(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        native_launcher_sha256="3" * 64,
        native_launcher_bytes=2_048,
        native_launcher_stat_identity=_stat_identity(
            inode=101,
            byte_count=2_048,
            executable=True,
        ),
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        runtime_executable_stat_identity=_stat_identity(
            inode=102,
            byte_count=4_096,
            executable=True,
        ),
        fake_worker_sha256=_EXPECTED_FAKE_WORKER_SOURCE_SHA256,
        fake_worker_bytes=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
        fake_worker_stat_identity=_stat_identity(
            inode=103,
            byte_count=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
        ),
    )
    launch_v3 = _build_prepared_separation_fake_launch_plan_v3_record(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
        native_build_receipt_sha256="4" * 64,
    )
    checkpoint = launch_v3["bindings"]
    result = _build_separation_fake_worker_result_v2(
        fake_launch_plan_v3=launch_v3,
        status="complete",
        process_report={
            "pid": 123,
            "pgid": 123,
            "pgid_equals_pid": True,
            "process_creation_attempted_by_worker": False,
            "reported_identifiers_are_signal_authority": False,
        },
        descriptor_report=_complete_descriptor_report(),
        checkpoint_report={
            "sha256": checkpoint["checkpoint_sha256"],
            "bytes": checkpoint["checkpoint_bytes"],
            "file_identity_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "identity_before_hash_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "identity_after_hash_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "unchanged": True,
            "full_hash_verified": True,
            "deserialized": False,
        },
        outputs=_expected_outputs(launch_v3),
        error=None,
    )
    native = _native_observation(
        plan_sha256=launch_v3["plan_sha256"],
        result_sha256=result["result_sha256"],
    )
    private_root = tmp_path / "private-root"
    values: dict[str, Any] = {
        "fixture": fixture,
        "lease": lease,
        "observation": observation,
        "worker_v2": worker_v2,
        "reservation": reservation,
        "request": request,
        "launch_v1": launch_v1,
        "launch_v2": launch_v2,
        "launch_v3": launch_v3,
        "result": result,
        "native": native,
        "private_root": private_root,
    }

    def admitted(**arguments: Any) -> Any:
        lease_module._consume_fake_execution_lease_bridge(
            arguments["lease_bridge_authority"],
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
        )
        os.mkdir(private_root, 0o700)
        os.chmod(private_root, 0o700)
        root_descriptor = executor._open_directory(private_root)
        core = executor._new_fake_execution_core(
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
            blocked_fake_launch_plan_v2=launch_v2,
            fake_launch_plan_v3=launch_v3,
            fake_worker_result_v2=result,
            native_execution=native,
            private_root_descriptor=root_descriptor,
            private_root_identity=executor._descriptor_object_identity(
                root_descriptor
            ),
        )
        values["core"] = core
        after_core(values)
        return core

    monkeypatch.setattr(
        executor,
        "_execute_admitted_fake_worker_under_lease",
        admitted,
    )
    return values


def _execute(values: dict[str, Any]) -> Any:
    return executor._execute_reserved_fake_worker(
        trusted_lease=values["lease"],
        trusted_reservation=values["reservation"],
        trusted_worker_request_v2=values["worker_v2"],
        current_lease_observation=values["observation"],
        fake_worker_request=values["request"],
        fake_launch_plan_v1=values["launch_v1"],
        blocked_fake_launch_plan_v2=values["launch_v2"],
        fake_launch_plan_v3=values["launch_v3"],
        trusted_native_session=object(),  # type: ignore[arg-type]
        native_session_observation=object(),  # type: ignore[arg-type]
        private_root=values["private_root"],
    )


def _flip_checkpoint(values: dict[str, Any]) -> None:
    checkpoint = values["fixture"]["checkpoint"]
    with checkpoint.open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 0x01]))
        stream.flush()
        os.fsync(stream.fileno())


def _flip_then_restore_checkpoint(values: dict[str, Any]) -> None:
    checkpoint = values["fixture"]["checkpoint"]
    with checkpoint.open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 0x01]))
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        stream.write(first)
        stream.flush()
        os.fsync(stream.fileno())


def test_post_core_checkpoint_mutation_has_exact_inert_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=_flip_checkpoint,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = records._validate_post_core_checkpoint_failed_terminal_receipt(
        failure.receipt
    )
    assert failure.primary_error.receipt["receipt_sha256"] == (
        failure.lease_terminal_receipt["receipt_sha256"]
    )
    assert receipt["status"] == "failed_post_core_checkpoint_integrity"
    assert receipt["failure"]["primary"]["stage"] == (
        "checkpoint_post_core_remeasurement"
    )
    assert receipt["failure"]["primary"]["reason_codes"] == (
        "checkpoint_file_identity_changed",
    )
    assert receipt["outputs"]["materialization_started"] is False
    assert receipt["permissions"]["publication_permitted"] is False
    assert receipt["checkpoint"]["exact_checkpoint_bytes_executed_proven"] is (
        False
    )
    assert failure.cleanup_stages == ()
    assert failure.private_root_owner is None
    assert values["core"].private_root_finalizer.alive is False
    assert not (values["private_root"] / "quarantine").exists()


def test_post_core_mutate_then_restore_is_still_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=_flip_then_restore_checkpoint,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    receipt = records._validate_post_core_checkpoint_failed_terminal_receipt(
        captured.value.receipt
    )
    assert receipt["failure"]["primary"]["reason_codes"] == (
        "checkpoint_file_identity_changed",
    )
    assert receipt["checkpoint"]["parent_post_core_integrity_matched"] is False
    assert values["core"].private_root_finalizer.alive is False


def test_post_core_checkpoint_root_close_failure_retains_exact_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=_flip_checkpoint,
    )
    original_close = executor._close_private_root_owner_strict
    cleanup = RuntimeError("synthetic post-core root close failure")
    monkeypatch.setattr(
        executor,
        "_close_private_root_owner_strict",
        lambda _owner: (_ for _ in ()).throw(cleanup),
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = records._validate_post_core_checkpoint_failed_terminal_receipt(
        failure.receipt
    )
    assert receipt["status"] == (
        "failed_post_core_checkpoint_integrity_with_cleanup_failures"
    )
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "private_root_descriptor_close"
    ]
    assert failure.cleanup_errors == (cleanup,)
    assert failure.private_root_owner is values["core"]
    assert failure.private_root_owner.private_root_finalizer.alive is True
    original_close(failure.private_root_owner)


@pytest.mark.parametrize("root_close_fails", (False, True))
def test_post_core_failure_capability_never_runs_root_cleanup_twice(
    root_close_fails: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=_flip_checkpoint,
    )
    original_composer = executor._whole_run_post_core_checkpoint_failure
    original_close = executor._close_private_root_owner_strict
    captured_raw: dict[str, Any] = {}
    close_owners: list[Any] = []
    cleanup = RuntimeError("synthetic one-use root close failure")

    def capture_composer(failure: Any, **keywords: Any) -> Any:
        captured_raw["failure"] = failure
        captured_raw["keywords"] = keywords
        return original_composer(failure, **keywords)

    def observe_close(owner: Any) -> None:
        close_owners.append(owner)
        if root_close_fails:
            raise cleanup
        original_close(owner)

    monkeypatch.setattr(
        executor,
        "_whole_run_post_core_checkpoint_failure",
        capture_composer,
    )
    monkeypatch.setattr(
        executor,
        "_close_private_root_owner_strict",
        observe_close,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed):
        _execute(values)

    assert close_owners == [values["core"]]
    assert original_composer(
        captured_raw["failure"],
        **captured_raw["keywords"],
    ) is None
    assert close_owners == [values["core"]]
    if root_close_fails:
        original_close(values["core"])


def test_mutation_plus_bridge_finish_failure_remains_receiptless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=_flip_checkpoint,
    )
    original_finish = lease_module._finish_fake_execution_lease_bridge
    cleanup = RuntimeError("synthetic bridge finish failure")

    def finish_then_fail(authority: Any) -> None:
        original_finish(authority)
        raise cleanup

    monkeypatch.setattr(
        lease_module,
        "_finish_fake_execution_lease_bridge",
        finish_then_fail,
    )

    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        _execute(values)

    failure = captured.value
    assert type(failure.primary_error) is (
        lease_module.SeparationCheckpointDescriptorLeaseError
    )
    assert failure.cleanup_stages == ("lease_bridge_finish",)
    assert failure.cleanup_errors == (cleanup,)
    assert failure.lease_receipt["integrity"]["status"] == "failed"
    assert failure.core is values["core"]
    assert failure.core.private_root_finalizer.alive is True
    executor._close_core_private_root_strict(failure.core)


def test_mutation_before_release_remeasurement_remains_receiptless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    original_finish = lease_module._finish_fake_execution_lease_bridge

    def finish_then_mutate(authority: Any) -> None:
        original_finish(authority)
        _flip_checkpoint(values)

    monkeypatch.setattr(
        lease_module,
        "_finish_fake_execution_lease_bridge",
        finish_then_mutate,
    )

    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        _execute(values)

    failure = captured.value
    assert failure.core is values["core"]
    assert failure.primary_error is None
    assert failure.cleanup_stages == ("fd5_reservation_release",)
    assert failure.lease_receipt["integrity"]["status"] == "failed"
    assert failure.core.private_root_finalizer.alive is True
    executor._close_core_private_root_strict(failure.core)


def test_healthy_control_keeps_existing_success_schema_and_is_historical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )

    receipt = _execute(values)
    original_receipt_hash = receipt["receipt_sha256"]
    lease_receipt = (
        lease_module.close_separation_checkpoint_descriptor_lease(
            values["lease"]
        )
    )
    _flip_checkpoint(values)

    assert receipt["schema"] == (
        "sunofriend.separation-fake-execution-terminal.v1"
    )
    assert receipt["status"] == "complete"
    assert receipt["receipt_sha256"] == original_receipt_hash
    assert (
        "checkpoint_content_may_change_after_last_remeasurement"
        in lease_receipt["limitations"]
    )
    assert (
        "descriptor_close_call_success_is_not_post_close_proof"
        in lease_receipt["limitations"]
    )
    assert values["core"].private_root_finalizer.alive is False


def test_path_replacement_is_detected_without_substituting_new_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def replace_path(values: dict[str, Any]) -> None:
        checkpoint = values["fixture"]["checkpoint"]
        replacement = checkpoint.with_name("replacement-checkpoint.pt")
        replacement.write_bytes(b"replacement bytes are not the retained file")
        os.replace(replacement, checkpoint)

    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=replace_path,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    receipt = records._validate_post_core_checkpoint_failed_terminal_receipt(
        captured.value.receipt
    )
    assert receipt["failure"]["primary"]["reason_codes"] == (
        "checkpoint_file_identity_changed",
    )
    assert values["fixture"]["checkpoint"].read_bytes() == (
        b"replacement bytes are not the retained file"
    )
    assert values["core"].private_root_finalizer.alive is False
