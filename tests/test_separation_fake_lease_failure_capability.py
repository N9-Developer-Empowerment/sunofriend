from __future__ import annotations

import copy
import gc
import pickle
import weakref
from pathlib import Path
from typing import Any

import pytest

import sunofriend._separation_fake_executor_darwin as executor_module
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
from tests.test_separation_launch_v2_facade import _prepared


def _issued_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    primary_error: BaseException | None = None,
) -> tuple[
    dict[str, Any],
    Any,
    Any,
    Any,
    Any,
    lease_module._FakeExecutionLeaseFailure,
    dict[str, object],
]:
    fixture, lease, observation, worker_v2, reservation = _prepared(tmp_path)
    primary = (
        ValueError("synthetic admitted execution failure")
        if primary_error is None
        else primary_error
    )
    fake_chain = {
        "fake_worker_request": {"request_sha256": "1" * 64},
        "fake_launch_plan_v1": {"plan_sha256": "2" * 64},
        "blocked_fake_launch_plan_v2": {"plan_sha256": "3" * 64},
        "fake_launch_plan_v3": {"plan_sha256": "4" * 64},
    }

    def fail_admitted(**_kwargs: object) -> object:
        raise primary

    monkeypatch.setattr(
        executor_module,
        "_execute_admitted_fake_worker_under_lease",
        fail_admitted,
    )
    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        lease_module._execute_reserved_fake_worker_under_lock(
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
            **fake_chain,
            trusted_native_session=object(),
            native_session_observation=object(),
            private_root=tmp_path / "unused-private-root",
        )
    failure = captured.value
    assert failure.primary_error is primary
    assert failure.lease_receipt is not None
    return (
        fixture,
        lease,
        reservation,
        worker_v2,
        observation,
        failure,
        fake_chain,
    )


def test_lease_issued_failure_authority_is_opaque_and_one_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, lease, reservation, worker_v2, observation, failure, chain = (
        _issued_failure(tmp_path, monkeypatch)
    )
    authority = failure._lease_failure_authority

    assert type(authority) is lease_module._FakeExecutionLeaseFailureAuthority
    with pytest.raises(TypeError, match="parent-issued"):
        lease_module._FakeExecutionLeaseFailureAuthority()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(authority)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(authority)

    receipt = lease_module._consume_fake_execution_lease_failure(
        failure,
        trusted_lease=lease,
        trusted_reservation=reservation,
        trusted_worker_request_v2=worker_v2,
        current_lease_observation=observation,
        **chain,
    )

    assert receipt is failure.lease_receipt
    assert receipt["status"] == "closed"
    assert receipt["cleanup"]["status"] == "complete"
    assert failure._lease_failure_authority is None
    with pytest.raises(ValueError, match="not lease-issued"):
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
            **chain,
        )
    _known_lease, state = lease_module._known_state(lease)
    with pytest.raises(RuntimeError, match="already issued"):
        lease_module._issue_fake_execution_lease_failure_authority(
            failure,
            trusted_lease=lease,
            lease_state=state,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
            lease_receipt=failure.lease_receipt,
            **chain,
        )
    assert fixture["checkpoint"].exists()


def test_constructed_failure_cannot_borrow_real_terminal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, lease, reservation, worker_v2, observation, issued, chain = (
        _issued_failure(tmp_path, monkeypatch)
    )
    forged = lease_module._FakeExecutionLeaseFailure(
        primary_error=issued.primary_error,
        cleanup_failures=(),
        lease_receipt=issued.lease_receipt,
        core=None,
    )

    with pytest.raises(ValueError, match="not lease-issued"):
        lease_module._consume_fake_execution_lease_failure(
            forged,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
            **chain,
        )

    assert (
        lease_module._consume_fake_execution_lease_failure(
            issued,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
            **chain,
        )
        is issued.lease_receipt
    )
    assert fixture["checkpoint"].exists()


def test_authentication_failure_never_replaces_the_execution_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authentication_error = RuntimeError(
        "synthetic authentication failure"
    )

    def fail_authentication(*_args: object, **_kwargs: object) -> object:
        raise authentication_error

    monkeypatch.setattr(
        lease_module,
        "_issue_fake_execution_lease_failure_authority",
        fail_authentication,
    )
    (
        fixture,
        _lease,
        _reservation,
        _worker,
        _observation,
        failure,
        _chain,
    ) = (
        _issued_failure(tmp_path, monkeypatch)
    )

    assert type(failure.primary_error) is ValueError
    assert failure.cleanup_stages == ("lease_failure_authentication",)
    assert failure.cleanup_errors == (authentication_error,)
    assert failure._lease_failure_authority is None
    assert fixture["checkpoint"].exists()


def test_nested_primary_mutation_invalidates_failure_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = executor_module._FakeExecutionAdmittedFailure(
        primary_error=ValueError("original nested primary"),
        cleanup_failures=(),
        private_root_owner=None,
        descriptor_owners=(),
    )
    fixture, lease, reservation, worker, observation, failure, chain = (
        _issued_failure(
            tmp_path,
            monkeypatch,
            primary_error=admitted,
        )
    )
    original_primary = admitted.primary_error
    admitted.primary_error = ValueError("replacement nested primary")

    with pytest.raises(ValueError, match="binding"):
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )
    admitted.primary_error = original_primary
    assert (
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )
        is failure.lease_receipt
    )

    assert fixture["checkpoint"].exists()


def test_exact_chain_hash_mutation_invalidates_failure_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, lease, reservation, worker, observation, failure, chain = (
        _issued_failure(tmp_path, monkeypatch)
    )
    launch_v3 = chain["fake_launch_plan_v3"]
    assert isinstance(launch_v3, dict)
    original_digest = launch_v3["plan_sha256"]
    launch_v3["plan_sha256"] = "5" * 64

    with pytest.raises(ValueError, match="binding"):
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )
    launch_v3["plan_sha256"] = original_digest
    assert (
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )
        is failure.lease_receipt
    )
    assert fixture["checkpoint"].exists()


def test_cleanup_tuple_mutation_invalidates_failure_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, lease, reservation, worker, observation, failure, chain = (
        _issued_failure(tmp_path, monkeypatch)
    )
    original_stages = failure.cleanup_stages
    original_errors = failure.cleanup_errors
    failure._record_cleanup(
        "private_root_descriptor_close",
        RuntimeError("synthetic unperformed cleanup"),
    )

    with pytest.raises(ValueError, match="binding"):
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )

    failure.cleanup_stages = original_stages
    failure.cleanup_errors = original_errors
    assert (
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )
        is failure.lease_receipt
    )
    assert fixture["checkpoint"].exists()


def test_authenticated_action_never_runs_for_mutated_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, lease, reservation, worker, observation, failure, chain = (
        _issued_failure(tmp_path, monkeypatch)
    )
    original_stages = failure.cleanup_stages
    original_errors = failure.cleanup_errors
    action_owners: list[object | None] = []

    def record_action(owner: object | None) -> str:
        action_owners.append(owner)
        return "ran"

    failure._record_cleanup(
        "private_root_descriptor_close",
        RuntimeError("synthetic unperformed cleanup"),
    )
    with pytest.raises(ValueError, match="binding"):
        lease_module._consume_fake_execution_lease_failure_with_authenticated_action(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            authenticated_action=record_action,
            **chain,
        )
    assert action_owners == []

    failure.cleanup_stages = original_stages
    failure.cleanup_errors = original_errors
    receipt, action_result = (
        lease_module._consume_fake_execution_lease_failure_with_authenticated_action(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            authenticated_action=record_action,
            **chain,
        )
    )
    assert receipt is failure.lease_receipt
    assert action_result == "ran"
    assert action_owners == [None]
    assert fixture["checkpoint"].exists()


def test_top_level_core_mutation_invalidates_failure_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, lease, reservation, worker, observation, failure, chain = (
        _issued_failure(tmp_path, monkeypatch)
    )
    failure.core = object()

    with pytest.raises(ValueError, match="binding"):
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )

    failure.core = None
    assert (
        lease_module._consume_fake_execution_lease_failure(
            failure,
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker,
            current_lease_observation=observation,
            **chain,
        )
        is failure.lease_receipt
    )
    assert fixture["checkpoint"].exists()


def test_unconsumed_failure_authority_is_not_kept_alive_by_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gc.collect()
    baseline = len(lease_module._FAKE_EXECUTION_LEASE_FAILURES)
    issued_baseline = len(
        lease_module._FAKE_EXECUTION_LEASE_FAILURES_EVER_ISSUED
    )
    (
        fixture,
        _lease,
        _reservation,
        _worker,
        _observation,
        failure,
        _chain,
    ) = (
        _issued_failure(tmp_path, monkeypatch)
    )
    authority = failure._lease_failure_authority
    failure_ref = weakref.ref(failure)
    authority_ref = weakref.ref(authority)
    failure.__traceback__ = None
    failure.__cause__ = None
    failure.__context__ = None
    primary = failure.primary_error
    assert primary is not None
    primary.__traceback__ = None
    primary.__cause__ = None
    primary.__context__ = None

    del authority
    del primary
    del failure
    gc.collect()

    assert failure_ref() is None
    assert authority_ref() is None
    assert len(lease_module._FAKE_EXECUTION_LEASE_FAILURES) == baseline
    assert (
        len(lease_module._FAKE_EXECUTION_LEASE_FAILURES_EVER_ISSUED)
        == issued_baseline
    )
    assert fixture["checkpoint"].exists()


def test_lease_failure_authority_rejects_every_cross_run_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _issued_failure(tmp_path / "first", monkeypatch)
    (
        first_fixture,
        first_lease,
        first_reservation,
        first_worker,
        first_observation,
        first_failure,
        first_chain,
    ) = first
    (
        second_fixture,
        second_lease,
        second_observation,
        second_worker,
        second_reservation,
    ) = _prepared(tmp_path / "second")

    exact = {
        "trusted_lease": first_lease,
        "trusted_reservation": first_reservation,
        "trusted_worker_request_v2": first_worker,
        "current_lease_observation": first_observation,
        **first_chain,
    }
    substitutions = {
        "trusted_lease": second_lease,
        "trusted_reservation": second_reservation,
        "trusted_worker_request_v2": second_worker,
        "current_lease_observation": second_observation,
        "fake_worker_request": object(),
        "fake_launch_plan_v1": object(),
        "blocked_fake_launch_plan_v2": object(),
        "fake_launch_plan_v3": object(),
    }
    try:
        for key, replacement in substitutions.items():
            changed = {**exact, key: replacement}
            with pytest.raises(ValueError, match="binding"):
                lease_module._consume_fake_execution_lease_failure(
                    first_failure,
                    **changed,
                )

        original_receipt = first_failure.lease_receipt
        second_receipt = None
        lease_module._release_separation_checkpoint_descriptor_fd5(
            second_lease,
            second_reservation,
        )
        second_receipt = (
            lease_module.close_separation_checkpoint_descriptor_lease(
                second_lease
            )
        )
        first_failure.lease_receipt = second_receipt
        with pytest.raises(ValueError, match="binding"):
            lease_module._consume_fake_execution_lease_failure(
                first_failure,
                **exact,
            )
        first_failure.lease_receipt = original_receipt

        assert (
            lease_module._consume_fake_execution_lease_failure(
                first_failure,
                **exact,
            )
            is original_receipt
        )
    finally:
        known_second, second_state = lease_module._known_state(second_lease)
        if lease_module._state_phase(known_second, second_state) == "active":
            lease_module._release_separation_checkpoint_descriptor_fd5(
                second_lease,
                second_reservation,
            )
            lease_module.close_separation_checkpoint_descriptor_lease(
                second_lease
            )
    assert first_fixture["checkpoint"].exists()
    assert second_fixture["checkpoint"].exists()


def test_private_failure_capability_does_not_widen_public_surface() -> None:
    assert "_consume_fake_execution_lease_failure" not in lease_module.__all__
    assert "_FakeExecutionLeaseFailureAuthority" not in lease_module.__all__
    assert (
        lease_module.CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED is False
    )
