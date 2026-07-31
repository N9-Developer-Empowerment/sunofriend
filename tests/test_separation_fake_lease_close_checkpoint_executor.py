from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

import sunofriend._separation_fake_executor_darwin as executor
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
from sunofriend import (
    _separation_fake_lease_close_checkpoint_failure_records as close_records,
)
from sunofriend import (
    _separation_fake_post_core_checkpoint_failure_records as post_core_records,
)
from sunofriend import (
    _separation_fake_reservation_release_checkpoint_failure_records as release_records,
)
from tests.test_separation_fake_post_core_checkpoint_executor import (
    _execute,
    _flip_checkpoint,
    _installed_post_core,
)
from tests.test_separation_fake_reservation_release_checkpoint_executor import (
    _mutate_during_normal_bridge_finish,
)


def _mutate_after_normal_reservation_release(
    values: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_release = (
        lease_module._release_separation_checkpoint_descriptor_fd5
    )

    def release_then_mutate(*arguments: Any, **keywords: Any) -> None:
        original_release(*arguments, **keywords)
        _flip_checkpoint(values)

    monkeypatch.setattr(
        lease_module,
        "_release_separation_checkpoint_descriptor_fd5",
        release_then_mutate,
    )


def test_lease_close_checkpoint_mutation_has_exact_inert_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    _mutate_after_normal_reservation_release(values, monkeypatch)

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = close_records._validate_lease_close_checkpoint_failed_terminal_receipt(
        failure.receipt
    )
    assert type(failure.primary_error) is (
        lease_module.SeparationCheckpointDescriptorLeaseError
    )
    assert failure.primary_error.receipt._document is (
        failure.lease_terminal_receipt._document
    )
    assert receipt["schema"] == (
        "sunofriend.separation-fake-lease-close-checkpoint-failure.v1"
    )
    assert receipt["status"] == "failed_lease_close_checkpoint_integrity"
    assert receipt["failure"]["primary"]["stage"] == (
        "checkpoint_lease_close_checkpoint_remeasurement"
    )
    checkpoint = receipt["checkpoint"]
    assert checkpoint["parent_post_core_integrity_matched"] is True
    assert checkpoint["parent_reservation_release_integrity_matched"] is True
    assert checkpoint["parent_checkpoint_lease_close_integrity_matched"] is False
    assert receipt["outputs"]["materialization_started"] is False
    assert receipt["permissions"]["publication_permitted"] is False
    assert failure.cleanup_stages == ()
    assert failure.cleanup_errors == ()
    assert failure.private_root_owner is None
    assert values["core"].private_root_finalizer.alive is False
    assert not (values["private_root"] / "quarantine").exists()


def test_lease_close_root_close_failure_retains_exact_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    _mutate_after_normal_reservation_release(values, monkeypatch)
    original_close = executor._close_private_root_owner_strict
    cleanup = RuntimeError("synthetic lease-close root close failure")
    monkeypatch.setattr(
        executor,
        "_close_private_root_owner_strict",
        lambda _owner: (_ for _ in ()).throw(cleanup),
    )

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    failure = captured.value
    receipt = close_records._validate_lease_close_checkpoint_failed_terminal_receipt(
        failure.receipt
    )
    assert receipt["status"] == (
        "failed_lease_close_checkpoint_integrity_with_cleanup_failures"
    )
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "private_root_descriptor_close"
    ]
    assert failure.cleanup_stages == ("private_root_descriptor_close",)
    assert failure.cleanup_errors == (cleanup,)
    assert failure.private_root_owner is values["core"]
    assert failure.private_root_owner.private_root_finalizer.alive is True
    original_close(failure.private_root_owner)


@pytest.mark.parametrize("root_close_fails", (False, True))
def test_lease_close_failure_capability_never_closes_root_twice(
    root_close_fails: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    _mutate_after_normal_reservation_release(values, monkeypatch)
    original_composer = executor._whole_run_lease_close_checkpoint_failure
    original_close = executor._close_private_root_owner_strict
    captured_raw: dict[str, Any] = {}
    close_owners: list[Any] = []
    cleanup = RuntimeError("synthetic one-use lease-close root failure")

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
        "_whole_run_lease_close_checkpoint_failure",
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


def test_bridge_finish_plus_lease_close_integrity_remains_receiptless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    _mutate_after_normal_reservation_release(values, monkeypatch)
    original_finish = lease_module._finish_fake_execution_lease_bridge
    bridge_cleanup = RuntimeError("synthetic bridge finish failure")

    def finish_then_fail(authority: Any) -> None:
        original_finish(authority)
        raise bridge_cleanup

    monkeypatch.setattr(
        lease_module,
        "_finish_fake_execution_lease_bridge",
        finish_then_fail,
    )

    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        _execute(values)

    failure = captured.value
    assert failure.primary_error is None
    assert failure.cleanup_stages == (
        "lease_bridge_finish",
        "checkpoint_lease_close",
    )
    assert failure.cleanup_errors[0] is bridge_cleanup
    assert type(failure.cleanup_errors[1]) is (
        lease_module.SeparationCheckpointDescriptorLeaseError
    )
    assert failure.core is values["core"]
    assert failure.core.private_root_finalizer.alive is True
    executor._close_core_private_root_strict(failure.core)


def test_release_failure_plus_lease_close_integrity_remains_receiptless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    original_release = (
        lease_module._release_separation_checkpoint_descriptor_fd5
    )
    release_cleanup = RuntimeError("synthetic release completion failure")

    def release_mutate_then_fail(
        *arguments: Any,
        **keywords: Any,
    ) -> None:
        original_release(*arguments, **keywords)
        _flip_checkpoint(values)
        raise release_cleanup

    monkeypatch.setattr(
        lease_module,
        "_release_separation_checkpoint_descriptor_fd5",
        release_mutate_then_fail,
    )

    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        _execute(values)

    failure = captured.value
    assert failure.primary_error is None
    assert failure.cleanup_stages == (
        "fd5_reservation_release",
        "checkpoint_lease_close",
    )
    assert failure.cleanup_errors[0] is release_cleanup
    assert type(failure.cleanup_errors[1]) is (
        lease_module.SeparationCheckpointDescriptorLeaseError
    )
    assert failure.core is values["core"]
    assert failure.core.private_root_finalizer.alive is True
    executor._close_core_private_root_strict(failure.core)


def test_broader_lease_close_descriptor_reason_remains_receiptless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    original_release = (
        lease_module._release_separation_checkpoint_descriptor_fd5
    )

    def release_then_make_checkpoint_inheritable(
        *arguments: Any,
        **keywords: Any,
    ) -> None:
        original_release(*arguments, **keywords)
        _lease, state = lease_module._known_state(values["lease"])
        assert state.descriptor is not None
        os.set_inheritable(state.descriptor, True)

    monkeypatch.setattr(
        lease_module,
        "_release_separation_checkpoint_descriptor_fd5",
        release_then_make_checkpoint_inheritable,
    )

    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        _execute(values)

    failure = captured.value
    assert failure.primary_error is None
    assert failure.cleanup_stages == ("checkpoint_lease_close",)
    assert failure.lease_receipt["integrity"]["reasons"] == (
        "checkpoint_descriptor_became_inheritable",
    )
    assert failure.core is values["core"]
    assert failure.core.private_root_finalizer.alive is True
    executor._close_core_private_root_strict(failure.core)


def test_integrity_plus_checkpoint_descriptor_cleanup_stays_receiptless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    _mutate_after_normal_reservation_release(values, monkeypatch)
    _lease, state = lease_module._known_state(values["lease"])
    checkpoint_descriptor = state.descriptor
    assert checkpoint_descriptor is not None
    original_close = os.close

    def fail_checkpoint_close(descriptor: int) -> None:
        if descriptor == checkpoint_descriptor:
            raise OSError("synthetic checkpoint descriptor close failure")
        original_close(descriptor)

    monkeypatch.setattr(os, "close", fail_checkpoint_close)

    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        _execute(values)

    failure = captured.value
    assert failure.primary_error is None
    assert failure.cleanup_stages == ("checkpoint_lease_close",)
    assert failure.lease_receipt["status"] == "integrity_and_cleanup_failed"
    assert failure.lease_receipt["integrity"]["status"] == "failed"
    assert failure.lease_receipt["cleanup"]["status"] == "close_unconfirmed"
    assert failure.core is values["core"]
    assert failure.core.private_root_finalizer.alive is True
    monkeypatch.setattr(os, "close", original_close)
    original_close(checkpoint_descriptor)
    executor._close_core_private_root_strict(failure.core)


def test_healthy_execution_keeps_existing_success_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )

    receipt = _execute(values)

    assert receipt["schema"] == (
        "sunofriend.separation-fake-execution-terminal.v1"
    )
    assert receipt["status"] == "complete"
    assert values["core"].private_root_finalizer.alive is False


def test_immediate_post_core_schema_remains_disjoint(
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

    receipt = post_core_records._validate_post_core_checkpoint_failed_terminal_receipt(
        captured.value.receipt
    )
    assert receipt["schema"] == (
        "sunofriend.separation-fake-post-core-checkpoint-failure.v1"
    )
    assert values["core"].private_root_finalizer.alive is False


def test_reservation_release_schema_remains_disjoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _installed_post_core(
        tmp_path,
        monkeypatch,
        after_core=lambda _values: None,
    )
    _mutate_during_normal_bridge_finish(values, monkeypatch)

    with pytest.raises(executor._SeparationFakeExecutionFailed) as captured:
        _execute(values)

    receipt = (
        release_records
        ._validate_reservation_release_checkpoint_failed_terminal_receipt(
            captured.value.receipt
        )
    )
    assert receipt["schema"] == (
        "sunofriend.separation-fake-reservation-release-checkpoint-failure.v1"
    )
    assert values["core"].private_root_finalizer.alive is False
