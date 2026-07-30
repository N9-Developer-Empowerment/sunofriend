from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

import sunofriend._separation_fake_executor_darwin as executor
import sunofriend._separation_fake_post_lease_failure_records as records
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
from tests.test_separation_fake_execution_records import _execution_records
from tests.test_separation_fake_post_lease_failure_records import (
    _lease_receipt,
    _native_observation,
)


def _installed_post_lease_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    collision: bool = False,
) -> dict[str, Any]:
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )
    native = _native_observation(
        plan_sha256=launch_v3["plan_sha256"],
        result_sha256=result["result_sha256"],
    )
    lease_receipt = _lease_receipt(request)
    root = tmp_path / "execution"
    state: dict[str, Any] = {}

    def bridge(**arguments: Any) -> tuple[Any, Any]:
        private_root = Path(arguments["private_root"])
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
        if collision:
            os.mkdir("quarantine", 0o700, dir_fd=root_descriptor)
        state["core"] = core
        return core, lease_receipt

    monkeypatch.setattr(
        lease_module,
        "_execute_reserved_fake_worker_under_lock",
        bridge,
    )
    return {
        "request": request,
        "launch_v1": launch_v1,
        "launch_v2": launch_v2,
        "launch_v3": launch_v3,
        "native": native,
        "root": root,
        "state": state,
    }


def _execute(values: dict[str, Any]) -> Any:
    return executor._execute_reserved_fake_worker(
        trusted_lease=object(),
        trusted_reservation=object(),
        trusted_worker_request_v2=object(),  # type: ignore[arg-type]
        current_lease_observation=object(),
        fake_worker_request=values["request"],
        fake_launch_plan_v1=values["launch_v1"],
        blocked_fake_launch_plan_v2=values["launch_v2"],
        fake_launch_plan_v3=values["launch_v3"],
        trusted_native_session=object(),  # type: ignore[arg-type]
        native_session_observation=object(),  # type: ignore[arg-type]
        private_root=values["root"],
    )


def _post_receipt(
    failure: executor._SeparationFakeExecutionFailed,
) -> records._SeparationFakeExecutionPostLeaseFailedReceipt:
    return records._validate_post_lease_failed_terminal_receipt(
        failure.receipt
    )


def test_post_lease_success_closes_root_before_terminal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)

    receipt = _execute(values)

    assert receipt["status"] == "complete"
    core = values["state"]["core"]
    assert core.private_root_finalizer.alive is False
    with pytest.raises(OSError):
        os.fstat(core.private_root_descriptor)


def test_materialization_cleanup_is_lifo_then_directory_then_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_open_read = executor._open_owned_read_at
    original_close_owned = executor._close_owned_descriptor_strict
    original_close_root = executor._close_core_private_root_strict
    created_reads: list[tuple[int, int]] = []
    closed: list[tuple[str, tuple[int, int] | None]] = []

    def observe_open(*arguments: Any, **keywords: Any) -> Any:
        owner = original_open_read(*arguments, **keywords)
        created_reads.append(owner.identity)
        return owner

    def observe_close(owner: Any) -> None:
        if owner.stage != "quarantine_output_write_descriptor_close":
            closed.append((owner.stage, owner.identity))
        original_close_owned(owner)

    def observe_root(core: Any) -> None:
        closed.append(("private_root_descriptor_close", None))
        original_close_root(core)

    monkeypatch.setattr(executor, "_open_owned_read_at", observe_open)
    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        observe_close,
    )
    monkeypatch.setattr(
        executor,
        "_close_core_private_root_strict",
        observe_root,
    )

    receipt = _execute(values)

    assert receipt["status"] == "complete"
    assert [identity for _stage, identity in closed[:-2]] == list(
        reversed(created_reads)
    )
    assert closed[-2][0] == "quarantine_directory_descriptor_close"
    assert closed[-1][0] == "private_root_descriptor_close"


def test_each_write_descriptor_closes_before_matching_read_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_open_read = executor._open_owned_read_at
    original_close_owned = executor._close_owned_descriptor_strict
    events: list[tuple[str, tuple[int, int]]] = []

    def observe_open(*arguments: Any, **keywords: Any) -> Any:
        owner = original_open_read(*arguments, **keywords)
        events.append(("read_open", owner.identity))
        return owner

    def observe_close(owner: Any) -> None:
        if owner.stage == "quarantine_output_write_descriptor_close":
            events.append(("write_close", owner.identity))
        original_close_owned(owner)

    monkeypatch.setattr(executor, "_open_owned_read_at", observe_open)
    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        observe_close,
    )

    receipt = _execute(values)

    assert receipt["status"] == "complete"
    read_identities = [
        identity for event, identity in events if event == "read_open"
    ]
    assert read_identities
    for identity in read_identities:
        assert events.index(("write_close", identity)) < events.index(
            ("read_open", identity)
        )


def test_quarantine_collision_has_exact_inert_post_lease_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(
        tmp_path,
        monkeypatch,
        collision=True,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert type(failure.primary_error) is FileExistsError
    assert receipt["failure"]["primary"]["stage"] == (
        "quarantine_directory_materialization"
    )
    assert receipt["failure"]["cleanup"] == ()
    assert receipt["outputs"]["materialization_started"] is True
    assert receipt["outputs"]["quarantine_verification_present"] is False
    assert failure.private_root_owner is None
    assert failure.descriptor_owners == ()
    assert values["state"]["core"].private_root_finalizer.alive is False


@pytest.mark.parametrize(
    ("target", "expected_stage", "materialization_started"),
    (
        (
            "_revalidate_result_for_materialization",
            "result_revalidation",
            False,
        ),
        (
            "_revalidate_private_root_for_materialization",
            "private_root_revalidation",
            False,
        ),
        (
            "_write_all",
            "quarantine_output_materialization",
            True,
        ),
        (
            "_validate_fake_execution_materialization_observation",
            "materialization_observation_seal",
            True,
        ),
    ),
)
def test_post_lease_primary_stage_hooks_are_exact(
    target: str,
    expected_stage: str,
    materialization_started: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    primary = RuntimeError(f"synthetic {expected_stage} failure")
    monkeypatch.setattr(
        executor,
        target,
        lambda *_arguments, **_keywords: (_ for _ in ()).throw(primary),
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert receipt["failure"]["primary"]["stage"] == expected_stage
    assert (
        receipt["outputs"]["materialization_started"]
        is materialization_started
    )
    expected_quarantine = (
        expected_stage == "materialization_observation_seal"
    )
    assert (
        receipt["outputs"]["quarantine_verification_present"]
        is expected_quarantine
    )
    assert receipt["outputs"]["materialization_observation_present"] is False
    assert failure.private_root_owner is None
    assert values["state"]["core"].private_root_finalizer.alive is False


def test_quarantine_verifier_failure_closes_every_owned_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    primary = RuntimeError("synthetic verifier failure")

    def fail_verifier(**_arguments: Any) -> Any:
        raise primary

    monkeypatch.setattr(
        executor,
        "_verify_fake_execution_quarantine_v2",
        fail_verifier,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert receipt["failure"]["primary"]["stage"] == (
        "quarantine_verification"
    )
    assert receipt["failure"]["cleanup"] == ()
    assert receipt["outputs"]["quarantine_verification_present"] is False
    assert receipt["outputs"]["materialization_observation_present"] is False
    assert failure.private_root_owner is None
    assert failure.descriptor_owners == ()


@pytest.mark.parametrize(
    ("target", "expected_primary", "expected_cleanup"),
    (
        (
            "_open_owned_directory_at",
            "quarantine_directory_materialization",
            "quarantine_directory_descriptor_close",
        ),
        (
            "_create_owned_file_at",
            "quarantine_output_materialization",
            "quarantine_output_write_descriptor_close",
        ),
        (
            "_open_owned_read_at",
            "quarantine_output_materialization",
            "quarantine_output_read_descriptor_close",
        ),
    ),
)
def test_owned_setup_and_close_failure_integrates_without_losing_owner(
    target: str,
    expected_primary: str,
    expected_cleanup: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_open = getattr(executor, target)
    original_close = executor._close_owned_descriptor_strict
    primary = RuntimeError(f"synthetic {target} setup failure")
    cleanup = RuntimeError(f"synthetic {target} cleanup failure")
    failed_once = False

    def fail_after_owned_open(*arguments: Any, **keywords: Any) -> Any:
        nonlocal failed_once
        owner = original_open(*arguments, **keywords)
        if not failed_once:
            failed_once = True
            raise executor._OwnedDescriptorSetupFailure(
                primary_error=primary,
                cleanup_error=cleanup,
                owner=owner,
            )
        return owner

    monkeypatch.setattr(executor, target, fail_after_owned_open)

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert failure.cleanup_errors[0] is cleanup
    assert receipt["failure"]["primary"]["stage"] == expected_primary
    assert receipt["failure"]["cleanup"][0]["stage"] == expected_cleanup
    assert len(failure.descriptor_owners) == 1
    assert failure.descriptor_owners[0].finalizer.alive is True
    original_close(failure.descriptor_owners[0])


def test_materialization_cleanup_preserves_first_and_duplicate_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_close = executor._close_owned_descriptor_strict
    first = RuntimeError("synthetic first read close failure")
    second = RuntimeError("synthetic second read close failure")
    remaining = [first, second]

    def fail_two_reads(owner: Any) -> None:
        if (
            owner.stage == "quarantine_output_read_descriptor_close"
            and remaining
        ):
            raise remaining.pop(0)
        original_close(owner)

    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        fail_two_reads,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is first
    assert failure.cleanup_errors == (first, second)
    assert receipt["failure"]["primary"]["stage"] == (
        "materialization_descriptor_cleanup"
    )
    assert receipt["outputs"]["quarantine_verification_present"] is True
    assert receipt["outputs"]["materialization_observation_present"] is True
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "quarantine_output_read_descriptor_close",
        "quarantine_output_read_descriptor_close"
    ]
    assert len(failure.descriptor_owners) == 2
    assert failure.private_root_owner is None
    for owner in failure.descriptor_owners:
        original_close(owner)
        assert owner.finalizer.alive is False


def test_write_close_only_failure_is_primary_and_recorded_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_close = executor._close_owned_descriptor_strict
    primary = RuntimeError("synthetic write close-only failure")
    failed_once = False

    def fail_one_write(owner: Any) -> None:
        nonlocal failed_once
        if (
            owner.stage == "quarantine_output_write_descriptor_close"
            and not failed_once
        ):
            failed_once = True
            raise primary
        original_close(owner)

    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        fail_one_write,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert failure.cleanup_errors == (primary,)
    assert receipt["failure"]["primary"]["stage"] == (
        "quarantine_output_materialization"
    )
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "quarantine_output_write_descriptor_close"
    ]
    assert len(failure.descriptor_owners) == 1
    assert failure.descriptor_owners[0].finalizer.alive is True
    original_close(failure.descriptor_owners[0])


def test_prior_primary_survives_private_root_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(
        tmp_path,
        monkeypatch,
        collision=True,
    )
    original_close = executor._close_core_private_root_strict
    cleanup = RuntimeError("synthetic root cleanup failure")
    monkeypatch.setattr(
        executor,
        "_close_core_private_root_strict",
        lambda _core: (_ for _ in ()).throw(cleanup),
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert type(failure.primary_error) is FileExistsError
    assert failure.cleanup_errors == (cleanup,)
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "private_root_descriptor_close"
    ]
    assert failure.private_root_owner is values["state"]["core"]
    original_close(failure.private_root_owner)


def test_first_primary_and_all_cleanup_failures_keep_exact_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_owned_close = executor._close_owned_descriptor_strict
    original_root_close = executor._close_core_private_root_strict
    primary = RuntimeError("synthetic output write primary")
    write_cleanup = RuntimeError("synthetic output write close failure")
    directory_cleanup = RuntimeError("synthetic directory close failure")
    root_cleanup = RuntimeError("synthetic root close failure")

    monkeypatch.setattr(
        executor,
        "_write_all",
        lambda *_arguments: (_ for _ in ()).throw(primary),
    )

    def fail_owned_cleanup(owner: Any) -> None:
        if owner.stage == "quarantine_output_write_descriptor_close":
            raise write_cleanup
        if owner.stage == "quarantine_directory_descriptor_close":
            raise directory_cleanup
        original_owned_close(owner)

    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        fail_owned_cleanup,
    )
    monkeypatch.setattr(
        executor,
        "_close_core_private_root_strict",
        lambda _core: (_ for _ in ()).throw(root_cleanup),
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert failure.cleanup_errors == (
        write_cleanup,
        directory_cleanup,
        root_cleanup,
    )
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "quarantine_output_write_descriptor_close",
        "quarantine_directory_descriptor_close",
        "private_root_descriptor_close",
    ]
    assert len(failure.descriptor_owners) == 2
    for owner in failure.descriptor_owners:
        assert owner.finalizer.alive is True
        original_owned_close(owner)
    assert failure.private_root_owner.private_root_finalizer.alive is True
    original_root_close(failure.private_root_owner)


def test_root_close_failure_is_primary_after_complete_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_close = executor._close_core_private_root_strict
    primary = RuntimeError("synthetic final root close failure")
    monkeypatch.setattr(
        executor,
        "_close_core_private_root_strict",
        lambda _core: (_ for _ in ()).throw(primary),
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert receipt["failure"]["primary"]["stage"] == (
        "private_root_descriptor_close"
    )
    assert receipt["failure"]["cleanup"] == ()
    assert receipt["outputs"]["quarantine_verification_present"] is True
    assert receipt["outputs"]["materialization_observation_present"] is True
    assert failure.private_root_owner is values["state"]["core"]
    original_close(failure.private_root_owner)


def test_terminal_receipt_failure_occurs_after_root_is_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    primary = RuntimeError("synthetic terminal receipt failure")
    def fail_terminal(**_arguments: Any) -> Any:
        assert values["state"]["core"].private_root_finalizer.alive is False
        raise primary

    monkeypatch.setattr(executor, "_terminal_receipt", fail_terminal)

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.primary_error is primary
    assert receipt["failure"]["primary"]["stage"] == (
        "whole_run_receipt_seal"
    )
    assert receipt["outputs"]["quarantine_verification_present"] is True
    assert receipt["outputs"]["materialization_observation_present"] is True
    assert failure.private_root_owner is None
    assert values["state"]["core"].private_root_finalizer.alive is False


def test_reentrant_root_failure_cannot_change_receipt_carrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_close = executor._close_core_private_root_strict
    primary = RuntimeError("synthetic reentrant root failure")

    def mutate_then_fail(core: Any) -> None:
        object.__setattr__(core, "native_execution", object())
        raise primary

    monkeypatch.setattr(
        executor,
        "_close_core_private_root_strict",
        mutate_then_fail,
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = _post_receipt(failure)
    assert failure.native_failure_observation is values["native"]
    assert receipt["bindings"][
        "native_execution_observation_sha256"
    ] == values["native"]["observation_sha256"]
    original_close(failure.private_root_owner)


def test_failure_receipt_seal_failure_preserves_primary_and_descriptor_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_close = executor._close_owned_descriptor_strict
    primary = RuntimeError("synthetic retained read close failure")
    sealing = RuntimeError("synthetic post-lease seal failure")
    failed_once = False

    def fail_one_read(owner: Any) -> None:
        nonlocal failed_once
        if (
            owner.stage == "quarantine_output_read_descriptor_close"
            and not failed_once
        ):
            failed_once = True
            raise primary
        original_close(owner)

    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        fail_one_read,
    )
    monkeypatch.setattr(
        executor,
        "_build_post_lease_failed_terminal_receipt",
        lambda **_arguments: (_ for _ in ()).throw(sealing),
    )

    with pytest.raises(
        executor._SeparationFakeExecutionPostLeaseUnsealedFailure
    ) as captured:
        _execute(values)

    failure = captured.value
    assert failure.receipt is None
    assert failure.primary_error is primary
    assert failure.sealing_error is sealing
    assert failure.primary_stage == "materialization_descriptor_cleanup"
    assert failure.private_root_owner is None
    assert len(failure.descriptor_owners) == 1
    assert failure.descriptor_owners[0].finalizer.alive is True
    original_close(failure.descriptor_owners[0])


def test_snapshot_failure_does_not_replace_materialization_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(
        tmp_path,
        monkeypatch,
        collision=True,
    )
    snapshot = RuntimeError("synthetic evidence snapshot failure")
    monkeypatch.setattr(
        executor,
        "_snapshot_fake_execution_core",
        lambda _core: (_ for _ in ()).throw(snapshot),
    )

    with pytest.raises(
        executor._SeparationFakeExecutionPostLeaseUnsealedFailure
    ) as captured:
        _execute(values)

    failure = captured.value
    assert failure.receipt is None
    assert type(failure.primary_error) is FileExistsError
    assert failure.sealing_error is snapshot
    assert failure.primary_stage == "quarantine_directory_materialization"
    assert failure.private_root_owner is values["state"]["core"]
    assert failure.private_root_owner.private_root_finalizer.alive is True
    executor._close_core_private_root_strict(failure.private_root_owner)


def test_failure_seal_catastrophe_retains_failed_root_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(
        tmp_path,
        monkeypatch,
        collision=True,
    )
    original_root_close = executor._close_core_private_root_strict
    root_cleanup = RuntimeError("synthetic retained root close failure")
    sealing = RuntimeError("synthetic retained-root seal failure")
    monkeypatch.setattr(
        executor,
        "_close_core_private_root_strict",
        lambda _core: (_ for _ in ()).throw(root_cleanup),
    )
    monkeypatch.setattr(
        executor,
        "_build_post_lease_failed_terminal_receipt",
        lambda **_arguments: (_ for _ in ()).throw(sealing),
    )

    with pytest.raises(
        executor._SeparationFakeExecutionPostLeaseUnsealedFailure
    ) as captured:
        _execute(values)

    failure = captured.value
    assert failure.receipt is None
    assert type(failure.primary_error) is FileExistsError
    assert failure.sealing_error is sealing
    assert failure.cleanup_errors == (root_cleanup,)
    assert failure.private_root_owner is values["state"]["core"]
    assert failure.private_root_owner.private_root_finalizer.alive is True
    original_root_close(failure.private_root_owner)


def test_terminal_seal_catastrophe_has_no_live_owners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    terminal = RuntimeError("synthetic terminal builder failure")
    sealing = RuntimeError("synthetic terminal failure seal failure")
    monkeypatch.setattr(
        executor,
        "_terminal_receipt",
        lambda **_arguments: (_ for _ in ()).throw(terminal),
    )
    monkeypatch.setattr(
        executor,
        "_build_post_lease_failed_terminal_receipt",
        lambda **_arguments: (_ for _ in ()).throw(sealing),
    )

    with pytest.raises(
        executor._SeparationFakeExecutionPostLeaseUnsealedFailure
    ) as captured:
        _execute(values)

    failure = captured.value
    assert failure.receipt is None
    assert failure.primary_error is terminal
    assert failure.sealing_error is sealing
    assert failure.private_root_owner is None
    assert failure.descriptor_owners == ()
    assert values["state"]["core"].private_root_finalizer.alive is False


def test_owned_open_retains_descriptor_when_setup_and_close_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "owned.bin"
    target.write_bytes(b"x")
    descriptor = os.open(target, os.O_RDONLY)
    primary = RuntimeError("synthetic descriptor setup failure")
    cleanup = RuntimeError("synthetic descriptor cleanup failure")
    original_close = executor._close_owned_descriptor_strict
    monkeypatch.setattr(
        executor,
        "_close_owned_descriptor_strict",
        lambda _owner: (_ for _ in ()).throw(cleanup),
    )

    with pytest.raises(executor._OwnedDescriptorSetupFailure) as captured:
        executor._finish_owned_descriptor_open(
            descriptor=descriptor,
            stage="quarantine_output_read_descriptor_close",
            setup=lambda _descriptor: (_ for _ in ()).throw(primary),
        )

    failure = captured.value
    assert failure.primary_error is primary
    assert failure.cleanup_error is cleanup
    assert failure.owner.finalizer.alive is True
    original_close(failure.owner)
    assert failure.owner.finalizer.alive is False


def test_pre_owner_identity_failure_retains_without_raw_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "identity.bin"
    target.write_bytes(b"x")
    descriptor = os.open(target, os.O_RDONLY)
    original_os_close = os.close
    primary = RuntimeError("synthetic identity failure")
    monkeypatch.setattr(
        executor,
        "_descriptor_object_identity",
        lambda _descriptor: (_ for _ in ()).throw(primary),
    )
    monkeypatch.setattr(
        executor.os,
        "close",
        lambda _descriptor: pytest.fail("unsafe raw close attempted"),
    )

    with pytest.raises(executor._OwnedDescriptorPreOwnerFailure) as captured:
        executor._finish_owned_descriptor_open(
            descriptor=descriptor,
            stage="quarantine_output_read_descriptor_close",
            setup=lambda _descriptor: None,
        )

    failure = captured.value
    assert failure.receipt is None
    assert failure.primary_error is primary
    assert "raw close is unsafe" in str(failure.cleanup_error)
    assert failure.descriptor == descriptor
    assert failure.identity is None
    original_os_close(descriptor)


def test_pre_owner_backstop_failure_preserves_exact_close_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "backstop.bin"
    target.write_bytes(b"x")
    descriptor = os.open(target, os.O_RDONLY)
    original_os_close = os.close
    primary = RuntimeError("synthetic backstop failure")
    cleanup = RuntimeError("synthetic exact close failure")
    monkeypatch.setattr(
        executor,
        "_new_owned_descriptor_cleanup_backstop",
        lambda **_arguments: (_ for _ in ()).throw(primary),
    )
    monkeypatch.setattr(
        executor,
        "_close_descriptor_if_same",
        lambda *_arguments: (_ for _ in ()).throw(cleanup),
    )

    with pytest.raises(executor._OwnedDescriptorPreOwnerFailure) as captured:
        executor._finish_owned_descriptor_open(
            descriptor=descriptor,
            stage="quarantine_output_read_descriptor_close",
            setup=lambda _descriptor: None,
        )

    failure = captured.value
    assert failure.receipt is None
    assert failure.primary_error is primary
    assert failure.cleanup_error is cleanup
    assert failure.descriptor == descriptor
    assert failure.identity is not None
    original_os_close(descriptor)


def test_pre_owner_backstop_race_never_closes_replacement_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = tmp_path / "original.bin"
    replacement = tmp_path / "replacement.bin"
    original.write_bytes(b"original")
    replacement.write_bytes(b"replacement")
    descriptor = os.open(original, os.O_RDONLY)
    primary = RuntimeError("synthetic re-entrant backstop failure")

    def replace_then_fail(**_arguments: Any) -> Any:
        os.close(descriptor)
        replacement_descriptor = os.open(replacement, os.O_RDONLY)
        if replacement_descriptor != descriptor:
            os.dup2(replacement_descriptor, descriptor)
            os.close(replacement_descriptor)
        raise primary

    monkeypatch.setattr(
        executor,
        "_new_owned_descriptor_cleanup_backstop",
        replace_then_fail,
    )

    with pytest.raises(executor._OwnedDescriptorPreOwnerFailure) as captured:
        executor._finish_owned_descriptor_open(
            descriptor=descriptor,
            stage="quarantine_output_read_descriptor_close",
            setup=lambda _descriptor: None,
        )

    failure = captured.value
    assert failure.receipt is None
    assert failure.primary_error is primary
    assert "descriptor identity changed" in str(failure.cleanup_error)
    assert failure.identity is not None
    assert os.pread(descriptor, 11, 0) == b"replacement"
    os.close(descriptor)


def test_pre_owner_catastrophe_is_not_converted_to_terminal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_lease_bridge(tmp_path, monkeypatch)
    original_backstop = executor._new_owned_descriptor_cleanup_backstop
    original_os_close = os.close
    primary = RuntimeError("synthetic quarantine owner allocation failure")
    cleanup = RuntimeError("synthetic quarantine raw close failure")

    def fail_quarantine_owner(**arguments: Any) -> Any:
        if arguments["stage"] == "quarantine_directory_descriptor_close":
            raise primary
        return original_backstop(**arguments)

    monkeypatch.setattr(
        executor,
        "_new_owned_descriptor_cleanup_backstop",
        fail_quarantine_owner,
    )
    monkeypatch.setattr(
        executor.os,
        "close",
        lambda _descriptor: (_ for _ in ()).throw(cleanup),
    )

    with pytest.raises(executor._OwnedDescriptorPreOwnerFailure) as captured:
        _execute(values)

    failure = captured.value
    assert failure.receipt is None
    assert failure.primary_error is primary
    assert failure.cleanup_error is cleanup
    assert failure.primary_stage == "quarantine_directory_materialization"
    assert failure.private_root_owner is values["state"]["core"]
    assert failure.private_root_owner.private_root_finalizer.alive is True
    original_os_close(failure.descriptor)
    monkeypatch.setattr(executor.os, "close", original_os_close)
    executor._close_core_private_root_strict(failure.private_root_owner)
