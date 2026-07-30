from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
import sunofriend.separation_launch_contract as launch_v1_module

from sunofriend._separation_checkpoint_fd5_reservation import (
    _CheckpointDescriptorFD5Reservation,
)
from sunofriend._separation_checkpoint_launch_v2_records import (
    _SeparationLaunchPlanV2Record,
    _validate_blocked_separation_launch_plan_v2_record_shape,
)
from sunofriend._separation_checkpoint_transport_records import (
    SeparationWorkerRequestV2Record,
)
from sunofriend.separation_checkpoint_descriptor_lease import (
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseError,
    _issue_blocked_separation_launch_plan_v2_record,
    _release_separation_checkpoint_descriptor_fd5,
    close_separation_checkpoint_descriptor_lease,
    recheck_separation_checkpoint_descriptor_lease,
)
from tests._separation_checkpoint_fixtures import torch_zip as _torch_zip
from tests.test_separation_checkpoint_fd5_reservation import (
    _acquire,
    _fixture,
    _plain,
    _record,
    _reserve,
)


_V1_LEASE_PUBLIC_SURFACE = [
    "CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED",
    "MAX_ACTIVE_CHECKPOINT_DESCRIPTOR_LEASES",
    "SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID",
    "SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_OBSERVATION_SCHEMA",
    "SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_RECEIPT_SCHEMA",
    "SeparationCheckpointDescriptorLease",
    "SeparationCheckpointDescriptorLeaseError",
    "SeparationCheckpointDescriptorLeaseObservation",
    "SeparationCheckpointDescriptorLeaseTerminalReceipt",
    "acquire_separation_checkpoint_descriptor_lease",
    "close_separation_checkpoint_descriptor_lease",
    "recheck_separation_checkpoint_descriptor_lease",
]


def _prepared(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    SeparationCheckpointDescriptorLease,
    Any,
    SeparationWorkerRequestV2Record,
    _CheckpointDescriptorFD5Reservation,
]:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    current_observation = recheck_separation_checkpoint_descriptor_lease(
        lease
    )
    record = _record(fixture, current_observation)
    reservation = _reserve(
        fixture,
        lease,
        current_observation,
        record=record,
    )
    return fixture, lease, current_observation, record, reservation


def _issue(
    lease: SeparationCheckpointDescriptorLease,
    reservation: _CheckpointDescriptorFD5Reservation,
    record: SeparationWorkerRequestV2Record,
) -> _SeparationLaunchPlanV2Record:
    return _issue_blocked_separation_launch_plan_v2_record(
        lease,
        trusted_reservation=reservation,
        trusted_worker_request_v2=record,
    )


def test_exact_reserved_request_issues_historical_blocked_record_and_keeps_lease(
    tmp_path: Path,
) -> None:
    fixture, lease, observation, record, reservation = _prepared(tmp_path)
    _known_lease, state = lease_module._known_state(lease)
    descriptor = state.descriptor
    reservation_binding = state.fd5_reservation

    try:
        plan = _issue(lease, reservation, record)

        assert type(plan) is _SeparationLaunchPlanV2Record
        assert _validate_blocked_separation_launch_plan_v2_record_shape(
            plan
        ) is plan
        assert plan["status"] == "blocked"
        assert plan["run_status"] == "not_run"
        assert plan["execution_permitted"] is False
        assert all(value is False for value in plan["capabilities"].values())
        assert all(value is False for value in plan["effects"].values())
        assert plan["construction_requirements"]["authority_scope"] == (
            "requirements_only_not_proven_by_record"
        )
        assert state.descriptor == descriptor
        assert state.fd5_reservation is reservation_binding
        assert state.fd5_reservation is not None
        assert state.fd5_reservation.authority is reservation
        assert state.fd5_reservation.worker_request_v2 is record
        assert _plain(
            recheck_separation_checkpoint_descriptor_lease(lease)
        ) == _plain(observation)
        with pytest.raises(ValueError, match="active FD5 reservation"):
            close_separation_checkpoint_descriptor_lease(lease)
    finally:
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
        assert close_separation_checkpoint_descriptor_lease(lease)[
            "status"
        ] == "closed"
        assert fixture["checkpoint"].exists()


def test_equivalent_plain_and_same_type_forged_v2_records_are_rejected(
    tmp_path: Path,
) -> None:
    fixture, lease, observation, record, reservation = _prepared(tmp_path)
    equivalent = _record(fixture, observation)
    forged = object.__new__(SeparationWorkerRequestV2Record)
    object.__setattr__(forged, "_document", record._document)  # noqa: SLF001

    try:
        for replacement in (_plain(record), equivalent, forged):
            with pytest.raises(
                ValueError, match="exact reserved record"
            ):
                _issue_blocked_separation_launch_plan_v2_record(
                    lease,
                    trusted_reservation=reservation,
                    trusted_worker_request_v2=replacement,  # type: ignore[arg-type]
                )
        assert type(_issue(lease, reservation, record)) is (
            _SeparationLaunchPlanV2Record
        )
    finally:
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
        close_separation_checkpoint_descriptor_lease(lease)


def test_forged_and_cross_lease_reservations_are_rejected(
    tmp_path: Path,
) -> None:
    (
        _first_fixture,
        first_lease,
        _first_observation,
        first_record,
        first_reservation,
    ) = _prepared(tmp_path / "first")
    (
        _second_fixture,
        second_lease,
        _second_observation,
        second_record,
        second_reservation,
    ) = _prepared(tmp_path / "second")
    forged = object.__new__(_CheckpointDescriptorFD5Reservation)

    try:
        for replacement in (forged, second_reservation):
            with pytest.raises(
                ValueError, match="exact issued authority"
            ):
                _issue(first_lease, replacement, first_record)
        with pytest.raises(ValueError, match="exact reserved record"):
            _issue(first_lease, first_reservation, second_record)
        assert type(
            _issue(first_lease, first_reservation, first_record)
        ) is _SeparationLaunchPlanV2Record
    finally:
        _release_separation_checkpoint_descriptor_fd5(
            first_lease,
            first_reservation,
        )
        _release_separation_checkpoint_descriptor_fd5(
            second_lease,
            second_reservation,
        )
        close_separation_checkpoint_descriptor_lease(first_lease)
        close_separation_checkpoint_descriptor_lease(second_lease)


@pytest.mark.parametrize("failure", ["checkpoint", "owner_pid"])
def test_mutation_or_parent_pid_change_terminalizes_issuance_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    fixture, lease, _observation, record, reservation = _prepared(tmp_path)
    original_close = lease_module.os.close
    original_getpid = lease_module.os.getpid
    closed: list[int] = []

    def observed_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(lease_module.os, "close", observed_close)
    if failure == "checkpoint":
        fixture["checkpoint"].write_bytes(b"x" * len(_torch_zip()))
    else:
        owner_pid = os.getpid()
        monkeypatch.setattr(
            lease_module.os,
            "getpid",
            lambda: owner_pid + 1,
        )

    with pytest.raises(
        SeparationCheckpointDescriptorLeaseError
    ) as captured:
        _issue(lease, reservation, record)
    assert captured.value.receipt["integrity"]["status"] == "failed"
    assert captured.value.receipt["cleanup"]["status"] == "complete"
    assert len(closed) == 1

    if failure == "owner_pid":
        monkeypatch.setattr(lease_module.os, "getpid", original_getpid)
    assert _plain(
        close_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(captured.value.receipt)
    assert len(closed) == 1


def test_success_does_not_change_or_install_a_parent_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture_value, lease, _observation, record, reservation = _prepared(
        tmp_path
    )
    _known_lease, state = lease_module._known_state(lease)
    descriptor = state.descriptor
    assert descriptor is not None
    identity_before = os.fstat(descriptor)
    offset_before = os.lseek(descriptor, 0, os.SEEK_CUR)
    inheritable_before = os.get_inheritable(descriptor)
    original_close = lease_module.os.close
    close_calls: list[int] = []

    def unexpected(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("launch V2 issuance attempted descriptor authority")

    def observed_close(value: int) -> None:
        close_calls.append(value)
        original_close(value)

    for name in ("dup", "dup2", "open", "set_inheritable"):
        monkeypatch.setattr(lease_module.os, name, unexpected)
    monkeypatch.setattr(lease_module.os, "close", observed_close)

    plan = _issue(lease, reservation, record)

    assert type(plan) is _SeparationLaunchPlanV2Record
    assert state.descriptor == descriptor
    assert os.fstat(descriptor) == identity_before
    assert os.lseek(descriptor, 0, os.SEEK_CUR) == offset_before == 0
    assert os.get_inheritable(descriptor) is inheritable_before is False
    assert close_calls == []
    assert state.fd5_reservation is not None

    monkeypatch.undo()
    _release_separation_checkpoint_descriptor_fd5(lease, reservation)
    close_separation_checkpoint_descriptor_lease(lease)


def test_issued_record_remains_historical_after_release_and_close(
    tmp_path: Path,
) -> None:
    _fixture_value, lease, _observation, record, reservation = _prepared(
        tmp_path
    )
    plan = _issue(lease, reservation, record)
    document = _plain(plan)

    _release_separation_checkpoint_descriptor_fd5(lease, reservation)
    receipt = close_separation_checkpoint_descriptor_lease(lease)

    assert receipt["status"] == "closed"
    assert _plain(plan) == document
    assert _validate_blocked_separation_launch_plan_v2_record_shape(
        plan
    ) is plan
    assert plan["construction_requirements"]["authority_scope"] == (
        "requirements_only_not_proven_by_record"
    )
    assert plan["capabilities"]["checkpoint_fd5_installation_supported"] is (
        False
    )
    assert plan["effects"]["checkpoint_descriptor_installed"] is False


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_facade_has_no_install_process_model_or_public_surface() -> None:
    source = Path(lease_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "ctypes",
        "http",
        "importlib",
        "multiprocessing",
        "onnxruntime",
        "pickle",
        "requests",
        "safetensors",
        "socket",
        "subprocess",
        "torch",
        "urllib",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            }.intersection(forbidden_imports)
        elif isinstance(node, ast.ImportFrom):
            assert (
                node.module or ""
            ).split(".", 1)[0] not in forbidden_imports
    issuance = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_issue_blocked_separation_launch_plan_v2_record"
    )
    forbidden_calls = {
        "dup",
        "dup2",
        "exec",
        "fork",
        "open",
        "posix_spawn",
        "posix_spawnp",
        "set_inheritable",
        "spawn",
        "subprocess.Popen",
        "subprocess.run",
        "_detach_and_close",
        "_release_separation_checkpoint_descriptor_fd5",
    }
    assert not {
        _qualified_name(node.func)
        for node in ast.walk(issuance)
        if isinstance(node, ast.Call)
    }.intersection(forbidden_calls)
    assert (
        "_issue_blocked_separation_launch_plan_v2_record"
        not in lease_module.__all__
    )
    assert lease_module.__all__ == _V1_LEASE_PUBLIC_SURFACE


def test_launch_v1_surface_policy_and_descriptor_rows_are_unchanged() -> None:
    assert launch_v1_module.REAL_WORKER_EXECUTION_SUPPORTED is False
    assert launch_v1_module.SEPARATION_LAUNCH_PLAN_SCHEMA == (
        "sunofriend.separation-launch-plan.v1"
    )
    assert launch_v1_module.SEPARATION_DESCRIPTOR_POLICY_SHA256 == (
        "a7f79d6f13021ac514ce6246ebfd2ccb9ecf3f07964a71fc624f039a15ed16ea"
    )
    assert launch_v1_module.SEPARATION_LAUNCH_ENVIRONMENT_SHA256 == (
        "c0cc9234783b12689f52fddd1cce92058d00daaca4b52e6e73d4596b68ecdd8b"
    )
    assert launch_v1_module.SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256 == (
        "1e07954c1bf9a8408b0700c9c9eadd554a10b1bab52427ef07b9b92363414a3d"
    )
    assert [
        item["descriptor"]
        for item in launch_v1_module._DESCRIPTOR_POLICY["descriptors"]
    ] == [0, 1, 2, 3, 4]
    source = Path(launch_v1_module.__file__).read_text(encoding="utf-8")
    assert "_separation_checkpoint_launch_v2_records" not in source
