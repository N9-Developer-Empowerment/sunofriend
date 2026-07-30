from __future__ import annotations

import ast
import copy
import gc
import os
import pickle
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

import pytest
import sunofriend._separation_checkpoint_fd5_reservation as reservation_module
import sunofriend.separation_checkpoint_descriptor_lease as lease_module

from sunofriend._separation_checkpoint_fd5_reservation import (
    _CheckpointDescriptorFD5Reservation,
)
from sunofriend._separation_checkpoint_transport_records import (
    SeparationWorkerRequestV2Record,
    build_separation_worker_request_v2_record,
)
from sunofriend.separation_checkpoint_descriptor_lease import (
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseError,
    SeparationCheckpointDescriptorLeaseObservation,
    _release_separation_checkpoint_descriptor_fd5,
    _reserve_separation_checkpoint_descriptor_fd5,
    acquire_separation_checkpoint_descriptor_lease,
    close_separation_checkpoint_descriptor_lease,
    recheck_separation_checkpoint_descriptor_lease,
)
from tests._separation_checkpoint_fixtures import (
    canonical_sha256 as _canonical_sha256,
)
from tests._separation_checkpoint_fixtures import (
    checkpoint_fixture as _checkpoint_fixture,
)
from tests._separation_checkpoint_fixtures import (
    inspect_checkpoint as _inspect_checkpoint,
)
from tests._separation_checkpoint_fixtures import (
    inspection_kwargs as _inspection_kwargs,
)
from tests._separation_checkpoint_fixtures import torch_zip as _torch_zip


_ADMISSION_BLOCKERS = sorted(
    {
        "checkpoint_descriptor_not_carried_to_loader",
        "checkpoint_path_to_loader_toctou_unresolved",
        "static_checkpoint_inspection_not_load_authority",
    }
)
_ADMISSION_ADVISORIES = ["private_evidence_only"]


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fixture(tmp_path: Path) -> dict[str, Any]:
    fixture = _checkpoint_fixture(tmp_path, _torch_zip())
    inspection = _inspect_checkpoint(fixture)
    return {
        **fixture,
        "checkpoint_inspection": inspection,
        "lease_kwargs": _inspection_kwargs(fixture),
    }


def _acquire(
    fixture: Mapping[str, Any],
) -> tuple[
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseObservation,
]:
    return acquire_separation_checkpoint_descriptor_lease(
        fixture["worker_request"],
        checkpoint_inspection=fixture["checkpoint_inspection"],
        trusted_checkpoint_inspection=fixture["checkpoint_inspection"],
        **fixture["lease_kwargs"],
    )


def _record(
    fixture: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    inert_suffix: str = "f",
) -> SeparationWorkerRequestV2Record:
    request = _plain(fixture["worker_request"])
    inspection = _plain(fixture["checkpoint_inspection"])
    observed = _plain(observation)
    bindings = {
        "worker_request_sha256": request["request_sha256"],
        "preflight_sha256": request["preflight"]["preflight_sha256"],
        "acceptance_artifact_sha256": request["preflight"]["bindings"][
            "acceptance_artifact_sha256"
        ],
        "separation_request_fingerprint_sha256": request[
            "separation_request_fingerprint_sha256"
        ],
        "output_allowlist_sha256": _canonical_sha256(
            request["output_allowlist"]
        ),
        "execution_admission_binding_sha256": inert_suffix * 64,
        "checkpoint_inspection_sha256": inspection["inspection_sha256"],
        "checkpoint_classification_evidence_sha256": inspection[
            "classification"
        ]["classification_evidence_sha256"],
        "lease_observation_sha256": observed["observation_sha256"],
        "checkpoint_sha256": observed["bindings"]["checkpoint_sha256"],
        "checkpoint_bytes": observed["bindings"]["checkpoint_bytes"],
        "checkpoint_file_identity_sha256": observed["bindings"][
            "checkpoint_file_identity_sha256"
        ],
        "archive_evidence_sha256": observed["bindings"][
            "archive_evidence_sha256"
        ],
        "pickle_evidence_sha256": observed["bindings"][
            "pickle_evidence_sha256"
        ],
        "runtime_artifact_sha256": "d" * 64,
        "runtime_parent_measurements_sha256": inert_suffix * 64,
    }
    logical_request = {
        key: request[key]
        for key in (
            "preflight",
            "identities",
            "roles",
            "settings",
            "seed",
            "isolation",
        )
    }
    return build_separation_worker_request_v2_record(
        expected_bindings=bindings,
        expected_logical_request=logical_request,
        expected_admission_blockers=_ADMISSION_BLOCKERS,
        expected_admission_advisories=_ADMISSION_ADVISORIES,
    )


def _reserve(
    fixture: Mapping[str, Any],
    lease: SeparationCheckpointDescriptorLease,
    observation: SeparationCheckpointDescriptorLeaseObservation,
    *,
    record: SeparationWorkerRequestV2Record | None = None,
) -> _CheckpointDescriptorFD5Reservation:
    return _reserve_separation_checkpoint_descriptor_fd5(
        lease,
        trusted_worker_request_v2=(
            _record(fixture, observation) if record is None else record
        ),
        trusted_inspection_request=fixture["trusted_request"],
        current_lease_observation=observation,
    )


def test_reservation_is_opaque_recheckable_and_blocks_healthy_close(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    current_observation = recheck_separation_checkpoint_descriptor_lease(
        lease
    )
    assert current_observation is not observation
    record = _record(fixture, current_observation)
    reservation = _reserve(
        fixture,
        lease,
        current_observation,
        record=record,
    )

    assert type(reservation) is _CheckpointDescriptorFD5Reservation
    assert not hasattr(reservation, "__dict__")
    assert not hasattr(reservation, "descriptor")
    assert not hasattr(reservation, "lease")
    assert str(tmp_path) not in repr(reservation)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(reservation)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(reservation)
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(reservation, protocol=protocol)
    with pytest.raises(AttributeError):
        reservation.value = 5  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="cannot be subclassed"):
        type(
            "ForgedReservation",
            (_CheckpointDescriptorFD5Reservation,),
            {},
        )

    assert _plain(
        recheck_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(observation)
    with pytest.raises(ValueError, match="active FD5 reservation"):
        close_separation_checkpoint_descriptor_lease(lease)
    _known_lease, state = lease_module._known_state(lease)
    assert state.descriptor is not None
    os.fstat(state.descriptor)
    assert state.terminal_document is None
    assert state.fd5_reservation is not None
    assert state.fd5_reservation.authority is reservation
    assert state.fd5_reservation.worker_request_v2 is record
    assert state.fd5_reservation.worker_request_v2_sha256 == record[
        "request_sha256"
    ]
    assert (
        state.fd5_reservation.inspection_request
        is fixture["trusted_request"]
    )
    assert (
        state.fd5_reservation.lease_observation
        is current_observation
    )
    assert _plain(
        recheck_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(observation)
    with pytest.raises(ValueError, match="already has"):
        _reserve(fixture, lease, observation)

    forged = object.__new__(_CheckpointDescriptorFD5Reservation)
    with pytest.raises(ValueError, match="exact issued authority"):
        _release_separation_checkpoint_descriptor_fd5(lease, forged)
    with pytest.raises(ValueError, match="active FD5 reservation"):
        close_separation_checkpoint_descriptor_lease(lease)

    _release_separation_checkpoint_descriptor_fd5(lease, reservation)
    receipt = close_separation_checkpoint_descriptor_lease(lease)
    assert receipt["status"] == "closed"
    assert receipt["bindings"]["lease_observation_sha256"] == observation[
        "observation_sha256"
    ]


def test_reservation_requires_exact_cross_bound_records(
    tmp_path: Path,
) -> None:
    first = _fixture(tmp_path / "first")
    second = _fixture(tmp_path / "second")
    lease, observation = _acquire(first)
    second_lease, second_observation = _acquire(second)
    try:
        record = _record(first, observation)
        with pytest.raises(ValueError, match="exact validated record"):
            _reserve_separation_checkpoint_descriptor_fd5(
                lease,
                trusted_worker_request_v2=record["request_sha256"],  # type: ignore[arg-type]
                trusted_inspection_request=first["trusted_request"],
                current_lease_observation=observation,
            )
        with pytest.raises(ValueError, match="inspection request"):
            _reserve_separation_checkpoint_descriptor_fd5(
                lease,
                trusted_worker_request_v2=record,
                trusted_inspection_request=copy.copy(
                    first["trusted_request"]
                ),
                current_lease_observation=observation,
            )
        with pytest.raises(ValueError, match="does not bind"):
            _reserve(
                first,
                lease,
                observation,
                record=_record(second, second_observation),
            )
        with pytest.raises(ValueError, match="substituted"):
            _reserve_separation_checkpoint_descriptor_fd5(
                lease,
                trusted_worker_request_v2=record,
                trusted_inspection_request=first["trusted_request"],
                current_lease_observation=second_observation,
            )

        # The three facts for which the lease has no authority remain inert,
        # but are still retained in and protected by the exact V2 record.
        inert_record = _record(first, observation, inert_suffix="e")
        reservation = _reserve(
            first,
            lease,
            observation,
            record=inert_record,
        )
        second_reservation = _reserve(
            second,
            second_lease,
            second_observation,
        )
        with pytest.raises(ValueError, match="exact issued authority"):
            _release_separation_checkpoint_descriptor_fd5(
                lease,
                second_reservation,
            )
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
        _release_separation_checkpoint_descriptor_fd5(
            second_lease,
            second_reservation,
        )
    finally:
        close_separation_checkpoint_descriptor_lease(lease)
        close_separation_checkpoint_descriptor_lease(second_lease)


def test_reservation_does_not_retain_lease_or_prevent_finalizer_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    reservation = _reserve(fixture, lease, observation)
    lease_reference = weakref.ref(lease)
    original_close = lease_module.os.close
    closed: list[int] = []

    def observed_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(lease_module.os, "close", observed_close)
    del lease
    for _attempt in range(3):
        gc.collect()
        if lease_reference() is None:
            break

    assert lease_reference() is None
    assert len(closed) == 1
    assert type(reservation) is _CheckpointDescriptorFD5Reservation


@pytest.mark.parametrize("operation", ["reserve", "release"])
def test_reserve_and_release_each_remeasure_full_checkpoint(
    tmp_path: Path,
    operation: str,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    record = _record(fixture, observation)
    reservation = (
        _reserve(fixture, lease, observation, record=record)
        if operation == "release"
        else None
    )
    fixture["checkpoint"].write_bytes(b"x" * len(_torch_zip()))

    with pytest.raises(
        SeparationCheckpointDescriptorLeaseError
    ) as failed:
        if operation == "reserve":
            _reserve(fixture, lease, observation, record=record)
        else:
            assert reservation is not None
            _release_separation_checkpoint_descriptor_fd5(
                lease,
                reservation,
            )
    assert failed.value.receipt["integrity"]["status"] == "failed"
    assert failed.value.receipt["cleanup"]["status"] == "complete"
    assert _plain(
        close_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(failed.value.receipt)


@pytest.mark.parametrize("tamper", ["binding_hash", "v2_record"])
def test_internal_reservation_tamper_fails_closed(
    tmp_path: Path,
    tamper: str,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    record = _record(fixture, observation)
    reservation = _reserve(
        fixture,
        lease,
        observation,
        record=record,
    )
    _known_lease, state = lease_module._known_state(lease)
    binding = state.fd5_reservation
    assert binding is not None
    if tamper == "binding_hash":
        object.__setattr__(
            binding,
            "worker_request_v2_sha256",
            "0" * 64,
        )
    else:
        altered = _plain(record)
        altered["request_sha256"] = "0" * 64
        object.__setattr__(record, "_document", altered)

    with pytest.raises(
        SeparationCheckpointDescriptorLeaseError
    ) as failed:
        recheck_separation_checkpoint_descriptor_lease(lease)
    assert failed.value.receipt["integrity"]["status"] == "failed"
    assert failed.value.receipt["cleanup"]["status"] == "complete"
    assert state.fd5_reservation is None
    with pytest.raises(SeparationCheckpointDescriptorLeaseError):
        _release_separation_checkpoint_descriptor_fd5(
            lease,
            reservation,
        )
    assert _plain(
        close_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(failed.value.receipt)


def test_double_release_rejects_without_harming_live_lease(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    reservation = _reserve(fixture, lease, observation)

    _release_separation_checkpoint_descriptor_fd5(lease, reservation)
    with pytest.raises(ValueError, match="no FD5 reservation"):
        _release_separation_checkpoint_descriptor_fd5(
            lease,
            reservation,
        )
    assert _plain(
        recheck_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(observation)
    assert close_separation_checkpoint_descriptor_lease(lease)[
        "status"
    ] == "closed"


@pytest.mark.parametrize("failure", ["checkpoint", "owner_pid"])
def test_reserved_integrity_or_owner_failure_terminalizes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    reservation = _reserve(fixture, lease, observation)
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
    ) as failed:
        close_separation_checkpoint_descriptor_lease(lease)
    assert failed.value.receipt["integrity"]["status"] == "failed"
    assert len(closed) == 1

    if failure == "owner_pid":
        monkeypatch.setattr(lease_module.os, "getpid", original_getpid)
    repeated = close_separation_checkpoint_descriptor_lease(lease)
    assert _plain(repeated) == _plain(failed.value.receipt)
    assert len(closed) == 1
    with pytest.raises(SeparationCheckpointDescriptorLeaseError):
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
    assert len(closed) == 1


def test_concurrent_reserve_and_release_close_are_serialized(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    record = _record(fixture, observation)

    def attempt_reserve() -> Any:
        try:
            return _reserve(
                fixture,
                lease,
                observation,
                record=record,
            )
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: attempt_reserve(), range(8)))
    reservations = [
        item
        for item in results
        if type(item) is _CheckpointDescriptorFD5Reservation
    ]
    assert len(reservations) == 1
    assert sum(isinstance(item, ValueError) for item in results) == 7
    reservation = reservations[0]

    def release() -> Any:
        try:
            _release_separation_checkpoint_descriptor_fd5(
                lease, reservation
            )
            return "released"
        except Exception as exc:  # pragma: no cover - diagnostic branch
            return exc

    def close() -> Any:
        try:
            return close_separation_checkpoint_descriptor_lease(lease)
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        release_result, close_result = list(
            executor.map(lambda fn: fn(), (release, close))
        )
    assert release_result == "released"
    if isinstance(close_result, ValueError):
        close_result = close_separation_checkpoint_descriptor_lease(lease)
    assert close_result["status"] == "closed"


def test_concurrent_reserve_and_close_have_one_serialized_outcome(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    record = _record(fixture, observation)
    barrier = threading.Barrier(2)

    def reserve() -> Any:
        barrier.wait(timeout=5)
        try:
            return _reserve(
                fixture,
                lease,
                observation,
                record=record,
            )
        except Exception as exc:
            return exc

    def close() -> Any:
        barrier.wait(timeout=5)
        try:
            return close_separation_checkpoint_descriptor_lease(lease)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        reserve_result, close_result = list(
            executor.map(lambda fn: fn(), (reserve, close))
        )

    if type(reserve_result) is _CheckpointDescriptorFD5Reservation:
        assert isinstance(close_result, ValueError)
        assert not isinstance(
            close_result,
            SeparationCheckpointDescriptorLeaseError,
        )
        _release_separation_checkpoint_descriptor_fd5(
            lease,
            reserve_result,
        )
        assert close_separation_checkpoint_descriptor_lease(lease)[
            "status"
        ] == "closed"
    else:
        assert isinstance(
            reserve_result,
            SeparationCheckpointDescriptorLeaseError,
        )
        assert close_result["status"] == "closed"


def test_concurrent_rechecks_remain_available_while_reserved(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    reservation = _reserve(fixture, lease, observation)

    with ThreadPoolExecutor(max_workers=8) as executor:
        observed = list(
            executor.map(
                lambda _index: (
                    recheck_separation_checkpoint_descriptor_lease(lease)
                ),
                range(24),
            )
        )
    assert all(_plain(item) == _plain(observation) for item in observed)
    _release_separation_checkpoint_descriptor_fd5(lease, reservation)
    assert close_separation_checkpoint_descriptor_lease(lease)[
        "status"
    ] == "closed"


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_reservation_helper_has_no_io_process_model_or_descriptor_api() -> None:
    assert (
        "_reserve_separation_checkpoint_descriptor_fd5"
        not in lease_module.__all__
    )
    assert (
        "_release_separation_checkpoint_descriptor_fd5"
        not in lease_module.__all__
    )
    assert (
        "_CheckpointDescriptorFD5Reservation"
        not in lease_module.__all__
    )
    source = Path(reservation_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "asyncio",
        "ctypes",
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
        "eval",
        "exec",
        "open",
        "dup",
        "dup2",
        "set_inheritable",
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
        elif isinstance(node, ast.Call):
            assert _qualified_name(node.func) not in forbidden_calls
