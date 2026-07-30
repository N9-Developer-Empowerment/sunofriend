"""Parent-only live checkpoint descriptor lease.

Acquisition bridges one exact, already-closed V1 static inspection to a newly
opened and independently parsed descriptor.  Only the checkpoint leaf FD is
retained; ancestor directory FDs are closed by the inspector bridge.

The raw FD exists only in module-private weak registry state.  No public API
duplicates, inherits, hands off, deserializes or executes it.  One private
Darwin-only fake-worker proof may pass the exact retained descriptor through a
one-shot bridge while the lease lock remains held; this does not widen the
public contract or enable real checkpoint loading.
"""

from __future__ import annotations

import os
import threading
import weakref
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _checkpoint_canonical_sha256,
    plain as _plain,
)
from ._separation_checkpoint_descriptor_io import (
    _close_if_owned as _close_if_owned,
    _file_identity as _file_identity,
    _file_identity_document as _file_identity_document,
    _hash_descriptor as _hash_descriptor,
)
from ._separation_checkpoint_lease_records import (
    SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID,
    SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_OBSERVATION_SCHEMA,
    SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_RECEIPT_SCHEMA,
    _TERMINAL_STATUSES,
    _TerminalAnchor,
    _TerminalOutcome,
    expected_acquisition_evidence as _records_expected_acquisition_evidence,
    expected_observation_document as _expected_observation_document,
    new_terminal_anchor as _records_new_terminal_anchor,
    observation_document as _observation_document,
    receipt_document as _receipt_document,
    validate_receipt_document as _records_validate_receipt_document,
    validate_terminal_anchor as _records_validate_terminal_anchor,
)
from ._separation_checkpoint_launch_v2_records import (
    _SeparationLaunchPlanV2Record,
    _build_blocked_separation_launch_plan_v2_record,
)
from ._separation_checkpoint_fd5_reservation import (
    _CheckpointDescriptorFD5Reservation,
    _FD5ReservationBinding,
    _new_fd5_reservation_binding,
    _require_fd5_reservation_authority,
    _validate_fd5_reservation_binding,
)
from ._separation_checkpoint_transport_records import (
    SeparationWorkerRequestV2Record,
)
from .separation_checkpoint_inspection import (
    MAX_CHECKPOINT_BYTES,
    SeparationCheckpointInspection,
    SeparationCheckpointInspectionRequest,
    _acquire_retained_checkpoint_observation,
    validate_separation_checkpoint_inspection,
)
from .separation_worker_contract import SeparationRuntimeArtifactIdentity

CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED = False
MAX_ACTIVE_CHECKPOINT_DESCRIPTOR_LEASES = 2
MAX_KNOWN_CHECKPOINT_DESCRIPTOR_LEASES = 64

_REGISTRY_LOCK = threading.RLock()
_KNOWN: weakref.WeakKeyDictionary[
    SeparationCheckpointDescriptorLease, _LeaseState
] = weakref.WeakKeyDictionary()
_ACTIVE: weakref.WeakSet[SeparationCheckpointDescriptorLease] = weakref.WeakSet()
_RESERVATIONS = 0
_FAKE_EXECUTION_BRIDGES: weakref.WeakKeyDictionary[
    _FakeExecutionLeaseBridgeAuthority, _FakeExecutionLeaseBridgeBinding
] = weakref.WeakKeyDictionary()


class SeparationCheckpointDescriptorLease:
    """Opaque exact identity for one module-private retained checkpoint FD."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("checkpoint descriptor leases are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("checkpoint descriptor leases cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("checkpoint descriptor leases cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("checkpoint descriptor leases cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("checkpoint descriptor leases cannot be serialized")


class _FakeExecutionLeaseBridgeAuthority:
    """Opaque one-shot proof that the exact lease lock admitted execution."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("fake execution lease bridges are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("fake execution lease bridges cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("fake execution lease bridges cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("fake execution lease bridges cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("fake execution lease bridges cannot be serialized")


@dataclass
class _FakeExecutionLeaseBridgeBinding:
    owner_pid: int
    lease_state: _LeaseState
    reservation: _CheckpointDescriptorFD5Reservation
    worker_request_v2: SeparationWorkerRequestV2Record
    lease_observation: SeparationCheckpointDescriptorLeaseObservation
    status: str


@dataclass(frozen=True, init=False)
class SeparationCheckpointDescriptorLeaseObservation(Mapping[str, Any]):
    """Immutable, path-free evidence for one live retained descriptor."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class SeparationCheckpointDescriptorLeaseTerminalReceipt(Mapping[str, Any]):
    """Immutable terminal integrity and cleanup evidence."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


class SeparationCheckpointDescriptorLeaseError(ValueError):
    """Terminal failure carrying its immutable path-free receipt."""

    def __init__(
        self,
        message: str,
        receipt: SeparationCheckpointDescriptorLeaseTerminalReceipt,
    ) -> None:
        super().__init__(message)
        self.receipt = receipt


class _IntegrityFailure(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _FakeExecutionLeaseFailure(RuntimeError):
    """Private aggregate retaining one primary and every cleanup failure."""

    def __init__(
        self,
        *,
        primary_error: BaseException | None,
        cleanup_failures: Sequence[tuple[str, BaseException]],
        lease_receipt: (
            SeparationCheckpointDescriptorLeaseTerminalReceipt | None
        ),
        core: Any | None,
    ) -> None:
        super().__init__("fake execution lease lifecycle failed")
        self.primary_error = primary_error
        self.cleanup_stages = tuple(
            stage for stage, _error in cleanup_failures
        )
        self.cleanup_errors = tuple(
            error for _stage, error in cleanup_failures
        )
        self.lease_receipt = lease_receipt
        self.core = core

    def _record_cleanup(self, stage: str, error: BaseException) -> None:
        self.cleanup_stages = (*self.cleanup_stages, stage)
        self.cleanup_errors = (*self.cleanup_errors, error)


@dataclass
class _LeaseState:
    lock: Any
    owner_pid: int
    descriptor: int | None
    file_identity: tuple[int, ...]
    request: SeparationCheckpointInspectionRequest
    trusted_inspection: SeparationCheckpointInspection
    acquisition_evidence: Mapping[str, Any]
    observation_document: Mapping[str, Any]
    terminal_anchor: _TerminalAnchor
    terminal_outcome: _TerminalOutcome | None
    terminal_document: Mapping[str, Any] | None
    finalizer: weakref.finalize
    status: str
    fd5_reservation: _FD5ReservationBinding | None


def acquire_separation_checkpoint_descriptor_lease(
    worker_request: Mapping[str, Any],
    *,
    checkpoint_inspection: SeparationCheckpointInspection,
    trusted_checkpoint_inspection: SeparationCheckpointInspection,
    trusted_request: SeparationCheckpointInspectionRequest,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> tuple[
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseObservation,
]:
    """Acquire one exact retained FD and a separate live observation."""

    _reserve()
    reserved = True
    retained = None
    finalizer = None
    try:
        retained = _acquire_retained_checkpoint_observation(
            worker_request,
            checkpoint_inspection=checkpoint_inspection,
            trusted_checkpoint_inspection=trusted_checkpoint_inspection,
            trusted_request=trusted_request,
            trusted_preflight=trusted_preflight,
            trusted_acceptance=trusted_acceptance,
            trusted_separation_request=trusted_separation_request,
            trusted_runtime_artifact=trusted_runtime_artifact,
        )
        lease = object.__new__(SeparationCheckpointDescriptorLease)
        observation_document = _observation_document(retained.evidence)
        terminal_anchor = _new_terminal_anchor(
            retained.evidence,
            observation_document,
        )
        observation = _observation_wrapper(observation_document)
        expected_devino = retained.file_identity[:2]
        finalizer = weakref.finalize(
            lease,
            _finalize_owned_descriptor,
            retained.descriptor,
            expected_devino,
        )
        state = _LeaseState(
            lock=threading.RLock(),
            owner_pid=os.getpid(),
            descriptor=retained.descriptor,
            file_identity=retained.file_identity,
            request=retained.request,
            trusted_inspection=retained.trusted_inspection,
            acquisition_evidence=retained.evidence,
            observation_document=observation_document,
            terminal_anchor=terminal_anchor,
            terminal_outcome=None,
            terminal_document=None,
            finalizer=finalizer,
            status="retained",
            fd5_reservation=None,
        )
        _register(lease, state)
        reserved = False
        retained = None
        return lease, observation
    except BaseException:
        if reserved:
            _release_reservation()
        if finalizer is not None and finalizer.alive:
            finalizer.detach()
        if retained is not None:
            _close_if_owned(
                retained.descriptor,
                retained.file_identity[:2],
            )
        raise


def recheck_separation_checkpoint_descriptor_lease(
    trusted_lease: SeparationCheckpointDescriptorLease,
) -> SeparationCheckpointDescriptorLeaseObservation:
    """Remeasure the exact retained FD under the lease lock."""

    lease, state = _known_state(trusted_lease)
    with state.lock:
        try:
            phase = _state_phase(lease, state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_state_matrix_invalid",),
            )
        if phase == "terminal":
            receipt = _receipt_wrapper(state)
            try:
                _require_owner(state)
            except _IntegrityFailure as exc:
                raise SeparationCheckpointDescriptorLeaseError(
                    str(exc),
                    receipt,
                ) from exc
            raise SeparationCheckpointDescriptorLeaseError(
                "checkpoint descriptor lease is already terminal",
                receipt,
            )
        try:
            _require_owner(state)
            _validate_state_authority(state)
            _remeasure(state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_authority_binding_invalid",),
            )
        return _observation_wrapper(state.observation_document)


def close_separation_checkpoint_descriptor_lease(
    trusted_lease: SeparationCheckpointDescriptorLease,
) -> SeparationCheckpointDescriptorLeaseTerminalReceipt:
    """Idempotently remeasure, detach and close one retained FD."""

    lease, state = _known_state(trusted_lease)
    with state.lock:
        try:
            phase = _state_phase(lease, state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_state_matrix_invalid",),
            )
        if phase == "terminal":
            receipt = _receipt_wrapper(state)
            try:
                _require_owner(state)
            except _IntegrityFailure as exc:
                raise SeparationCheckpointDescriptorLeaseError(
                    str(exc),
                    receipt,
                ) from exc
            return receipt
        try:
            _require_owner(state)
            _validate_state_authority(state)
            _remeasure(state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_authority_binding_invalid",),
            )
        if state.fd5_reservation is not None:
            raise ValueError(
                "checkpoint descriptor lease has an active FD5 reservation"
            )
        cleanup_status, cleanup_reasons = _detach_and_close(lease, state)
        status = "closed" if cleanup_status == "complete" else "cleanup_failed"
        _store_terminal(
            state=state,
            status=status,
            integrity_status="verified_before_close_attempt",
            integrity_reasons=(),
            cleanup_status=cleanup_status,
            cleanup_reasons=cleanup_reasons,
        )
        receipt = _receipt_wrapper(state)
        if cleanup_status != "complete":
            raise SeparationCheckpointDescriptorLeaseError(
                "checkpoint descriptor close call did not succeed",
                receipt,
            )
        return receipt


def _reserve_separation_checkpoint_descriptor_fd5(
    trusted_lease: SeparationCheckpointDescriptorLease,
    *,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    trusted_inspection_request: SeparationCheckpointInspectionRequest,
    current_lease_observation: (
        SeparationCheckpointDescriptorLeaseObservation
    ),
) -> _CheckpointDescriptorFD5Reservation:
    """Reserve the live lease for a future FD5 policy without installing it."""

    lease, state = _known_state(trusted_lease)
    if (
        type(current_lease_observation)
        is not SeparationCheckpointDescriptorLeaseObservation
    ):
        raise ValueError(
            "current lease observation must be an exact issued record"
        )
    with state.lock:
        _require_active_state_for_reservation(lease, state)
        try:
            _require_owner(state)
            _validate_state_authority(state)
            _remeasure(state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_authority_binding_invalid",),
            )
        if state.fd5_reservation is not None:
            raise ValueError(
                "checkpoint descriptor lease already has an FD5 reservation"
            )
        binding = _new_fd5_reservation_binding(
            worker_request_v2=trusted_worker_request_v2,
            inspection_request=trusted_inspection_request,
            lease_observation=current_lease_observation,
            expected_worker_request_v1=state.request.worker_request,
            expected_inspection_request=state.request,
            expected_inspection=state.trusted_inspection,
            expected_lease_observation=state.observation_document,
        )
        state.fd5_reservation = binding
        return binding.authority


def _release_separation_checkpoint_descriptor_fd5(
    trusted_lease: SeparationCheckpointDescriptorLease,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
) -> None:
    """Release one exact reservation after a final locked remeasurement."""

    lease, state = _known_state(trusted_lease)
    with state.lock:
        _require_active_state_for_reservation(lease, state)
        try:
            _require_owner(state)
            _validate_state_authority(state)
            _remeasure(state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_authority_binding_invalid",),
            )
        binding = state.fd5_reservation
        if binding is None:
            raise ValueError(
                "checkpoint descriptor lease has no FD5 reservation"
            )
        _require_fd5_reservation_authority(
            trusted_reservation,
            binding,
        )
        state.fd5_reservation = None


def _issue_blocked_separation_launch_plan_v2_record(
    trusted_lease: SeparationCheckpointDescriptorLease,
    *,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
) -> _SeparationLaunchPlanV2Record:
    """Issue historical blocked launch evidence for one exact reservation."""

    lease, state = _known_state(trusted_lease)
    with state.lock:
        _require_active_state_for_reservation(lease, state)
        try:
            _require_owner(state)
            _validate_state_authority(state)
            _remeasure(state)
        except _IntegrityFailure as exc:
            _terminal_failure(lease, state, (exc.reason,))
        except Exception:
            _terminal_failure(
                lease,
                state,
                ("lease_authority_binding_invalid",),
            )
        binding = state.fd5_reservation
        if binding is None:
            raise ValueError(
                "checkpoint descriptor lease has no FD5 reservation"
            )
        _require_fd5_reservation_authority(
            trusted_reservation,
            binding,
        )
        if trusted_worker_request_v2 is not binding.worker_request_v2:
            raise ValueError(
                "launch V2 request must be the exact reserved record"
            )
        return _build_blocked_separation_launch_plan_v2_record(
            worker_request_v2=trusted_worker_request_v2,
        )


def _execute_reserved_separation_fake_worker_darwin(
    trusted_lease: SeparationCheckpointDescriptorLease,
    *,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
    trusted_native_session: Any,
    native_session_observation: Any,
    private_root: str | os.PathLike[str],
) -> Any:
    """Enter the private synchronous fake executor without widening V1 API."""

    from ._separation_fake_executor_darwin import (
        _execute_reserved_fake_worker,
    )

    return _execute_reserved_fake_worker(
        trusted_lease=trusted_lease,
        trusted_reservation=trusted_reservation,
        trusted_worker_request_v2=trusted_worker_request_v2,
        current_lease_observation=current_lease_observation,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
        fake_launch_plan_v3=fake_launch_plan_v3,
        trusted_native_session=trusted_native_session,
        native_session_observation=native_session_observation,
        private_root=private_root,
    )


def _execute_reserved_fake_worker_under_lock(
    *,
    trusted_lease: SeparationCheckpointDescriptorLease,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
    trusted_native_session: Any,
    native_session_observation: Any,
    private_root: Any,
) -> tuple[Any, SeparationCheckpointDescriptorLeaseTerminalReceipt]:
    """Validate, execute and close while retaining the exact lease lock."""

    lease, state = _known_state(trusted_lease)
    primary_error: BaseException | None = None
    cleanup_failures: list[tuple[str, BaseException]] = []
    core: Any | None = None
    receipt: SeparationCheckpointDescriptorLeaseTerminalReceipt | None = None
    with state.lock:
        bridge_authority: _FakeExecutionLeaseBridgeAuthority | None = None
        try:
            _require_active_state_for_reservation(lease, state)
            _require_owner(state)
            _validate_state_authority(state)
            _remeasure(state)
            binding = state.fd5_reservation
            if binding is None:
                raise ValueError(
                    "checkpoint descriptor lease has no FD5 reservation"
                )
            _require_fd5_reservation_authority(
                trusted_reservation,
                binding,
            )
            if trusted_worker_request_v2 is not binding.worker_request_v2:
                raise ValueError(
                    "fake execution request must be the exact reserved record"
                )
            if (
                current_lease_observation is not binding.lease_observation
                or getattr(current_lease_observation, "_document", None)
                is not state.observation_document
            ):
                raise ValueError(
                    "fake execution requires the exact lease observation"
                )
            descriptor = state.descriptor
            if type(descriptor) is not int or descriptor < 3:
                raise ValueError(
                    "checkpoint descriptor lease ownership is invalid"
                )
            expected_blocked_launch_v2 = (
                _build_blocked_separation_launch_plan_v2_record(
                    worker_request_v2=trusted_worker_request_v2,
                )
            )
            bridge_authority = _issue_fake_execution_lease_bridge(
                state=state,
                trusted_reservation=trusted_reservation,
                trusted_worker_request_v2=trusted_worker_request_v2,
                current_lease_observation=current_lease_observation,
            )
            from ._separation_fake_executor_darwin import (
                _execute_admitted_fake_worker_under_lease,
            )

            core = _execute_admitted_fake_worker_under_lease(
                lease_bridge_authority=bridge_authority,
                trusted_worker_request_v2=trusted_worker_request_v2,
                current_lease_observation=current_lease_observation,
                expected_blocked_launch_v2=expected_blocked_launch_v2,
                fake_worker_request=fake_worker_request,
                fake_launch_plan_v1=fake_launch_plan_v1,
                blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
                fake_launch_plan_v3=fake_launch_plan_v3,
                trusted_native_session=trusted_native_session,
                native_session_observation=native_session_observation,
                checkpoint_descriptor=descriptor,
                private_root=private_root,
            )
            _remeasure(state)
        except BaseException as exc:
            primary_error = exc
        finally:
            if bridge_authority is not None:
                try:
                    _finish_fake_execution_lease_bridge(bridge_authority)
                except BaseException as cleanup_error:
                    cleanup_failures.append(
                        ("lease_bridge_finish", cleanup_error)
                    )
        try:
            if _state_phase(lease, state) == "active":
                if state.fd5_reservation is not None:
                    try:
                        _release_separation_checkpoint_descriptor_fd5(
                            lease,
                            trusted_reservation,
                        )
                    except BaseException as cleanup_error:
                        cleanup_failures.append(
                            ("fd5_reservation_release", cleanup_error)
                        )
                        receipt = _lease_receipt_from_error(cleanup_error)
                if (
                    receipt is None
                    and _state_phase(lease, state) == "active"
                    and state.fd5_reservation is None
                ):
                    try:
                        receipt = close_separation_checkpoint_descriptor_lease(
                            lease
                        )
                    except BaseException as cleanup_error:
                        cleanup_failures.append(
                            ("checkpoint_lease_close", cleanup_error)
                        )
                        receipt = _lease_receipt_from_error(cleanup_error)
        except BaseException as cleanup_error:
            cleanup_failures.append(
                ("checkpoint_lease_cleanup", cleanup_error)
            )
            if receipt is None:
                receipt = _lease_receipt_from_error(cleanup_error)
        if receipt is None:
            try:
                receipt = _terminalize_fake_execution_lease_after_failure(
                    lease,
                    state,
                )
            except BaseException as cleanup_error:
                cleanup_failures.append(
                    ("checkpoint_lease_forced_terminalization", cleanup_error)
                )
                receipt = _lease_receipt_from_error(cleanup_error)
        if (
            receipt is not None
            and (
                receipt["status"] != "closed"
                or receipt["cleanup"]["status"] != "complete"
            )
            and not cleanup_failures
        ):
            cleanup_failures.append(
                (
                    "checkpoint_lease_terminal_status",
                    RuntimeError(
                        "fake execution lease did not close cleanly"
                    ),
                )
            )
        if primary_error is not None or cleanup_failures:
            failure = _FakeExecutionLeaseFailure(
                primary_error=primary_error,
                cleanup_failures=cleanup_failures,
                lease_receipt=receipt,
                core=core,
            )
            if primary_error is not None:
                raise failure from primary_error
            raise failure
        if core is None or receipt is None:
            raise RuntimeError(
                "fake execution did not produce terminal lease evidence"
            )
        return core, receipt


def _lease_receipt_from_error(
    error: BaseException,
) -> SeparationCheckpointDescriptorLeaseTerminalReceipt | None:
    receipt = getattr(error, "receipt", None)
    if type(receipt) is SeparationCheckpointDescriptorLeaseTerminalReceipt:
        return receipt
    return None


def _terminalize_fake_execution_lease_after_failure(
    lease: SeparationCheckpointDescriptorLease,
    state: _LeaseState,
) -> SeparationCheckpointDescriptorLeaseTerminalReceipt:
    """End one admitted private attempt even if reservation release failed."""

    try:
        phase = _state_phase(lease, state)
    except _IntegrityFailure as exc:
        _terminal_failure(lease, state, (exc.reason,))
    except Exception:
        _terminal_failure(
            lease,
            state,
            ("lease_state_matrix_invalid",),
        )
    if phase == "terminal":
        return _receipt_wrapper(state)
    try:
        _require_owner(state)
        _validate_state_authority(state)
        _remeasure(state)
    except _IntegrityFailure as exc:
        _terminal_failure(lease, state, (exc.reason,))
    except Exception:
        _terminal_failure(
            lease,
            state,
            ("lease_authority_binding_invalid",),
        )
    state.fd5_reservation = None
    cleanup_status, cleanup_reasons = _detach_and_close(lease, state)
    status = "closed" if cleanup_status == "complete" else "cleanup_failed"
    _store_terminal(
        state=state,
        status=status,
        integrity_status="verified_before_close_attempt",
        integrity_reasons=(),
        cleanup_status=cleanup_status,
        cleanup_reasons=cleanup_reasons,
    )
    receipt = _receipt_wrapper(state)
    if cleanup_status != "complete":
        raise SeparationCheckpointDescriptorLeaseError(
            "checkpoint descriptor close call did not succeed",
            receipt,
        )
    return receipt


def _issue_fake_execution_lease_bridge(
    *,
    state: _LeaseState,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
) -> _FakeExecutionLeaseBridgeAuthority:
    authority = object.__new__(_FakeExecutionLeaseBridgeAuthority)
    binding = _FakeExecutionLeaseBridgeBinding(
        owner_pid=os.getpid(),
        lease_state=state,
        reservation=trusted_reservation,
        worker_request_v2=trusted_worker_request_v2,
        lease_observation=current_lease_observation,
        status="issued_under_lock",
    )
    with _REGISTRY_LOCK:
        if authority in _FAKE_EXECUTION_BRIDGES:
            raise RuntimeError("fake execution lease bridge registration failed")
        _FAKE_EXECUTION_BRIDGES[authority] = binding
    return authority


def _consume_fake_execution_lease_bridge(
    value: Any,
    *,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
) -> None:
    if type(value) is not _FakeExecutionLeaseBridgeAuthority:
        raise ValueError("fake execution requires an exact lease bridge")
    with _REGISTRY_LOCK:
        binding = _FAKE_EXECUTION_BRIDGES.get(value)
    if type(binding) is not _FakeExecutionLeaseBridgeBinding:
        raise ValueError("fake execution lease bridge is not registered")
    state = binding.lease_state
    with state.lock:
        _require_owner(state)
        if (
            binding.owner_pid != os.getpid()
            or binding.status != "issued_under_lock"
            or binding.worker_request_v2 is not trusted_worker_request_v2
            or binding.lease_observation is not current_lease_observation
            or state.fd5_reservation is None
            or state.fd5_reservation.authority is not binding.reservation
            or state.fd5_reservation.worker_request_v2
            is not trusted_worker_request_v2
            or state.fd5_reservation.lease_observation
            is not current_lease_observation
        ):
            raise ValueError("fake execution lease bridge binding changed")
        _validate_state_authority(state)
        _remeasure(state)
        binding.status = "consumed"


def _finish_fake_execution_lease_bridge(
    authority: _FakeExecutionLeaseBridgeAuthority,
) -> None:
    with _REGISTRY_LOCK:
        binding = _FAKE_EXECUTION_BRIDGES.get(authority)
        if type(binding) is not _FakeExecutionLeaseBridgeBinding:
            return
        binding.status = "terminal"
        del _FAKE_EXECUTION_BRIDGES[authority]


def _require_active_state_for_reservation(
    lease: SeparationCheckpointDescriptorLease,
    state: _LeaseState,
) -> None:
    try:
        phase = _state_phase(lease, state)
    except _IntegrityFailure as exc:
        _terminal_failure(lease, state, (exc.reason,))
    except Exception:
        _terminal_failure(
            lease,
            state,
            ("lease_state_matrix_invalid",),
        )
    if phase == "terminal":
        raise SeparationCheckpointDescriptorLeaseError(
            "checkpoint descriptor lease is already terminal",
            _receipt_wrapper(state),
        )


def _reserve() -> None:
    global _RESERVATIONS

    with _REGISTRY_LOCK:
        if len(_KNOWN) + _RESERVATIONS >= MAX_KNOWN_CHECKPOINT_DESCRIPTOR_LEASES:
            raise ValueError("known checkpoint descriptor lease limit reached")
        if len(_ACTIVE) + _RESERVATIONS >= MAX_ACTIVE_CHECKPOINT_DESCRIPTOR_LEASES:
            raise ValueError("active checkpoint descriptor lease limit reached")
        _RESERVATIONS += 1


def _release_reservation() -> None:
    global _RESERVATIONS

    with _REGISTRY_LOCK:
        if _RESERVATIONS <= 0:
            raise RuntimeError("checkpoint descriptor lease reservation underflow")
        _RESERVATIONS -= 1


def _register(
    lease: SeparationCheckpointDescriptorLease,
    state: _LeaseState,
) -> None:
    global _RESERVATIONS

    with _REGISTRY_LOCK:
        if _RESERVATIONS <= 0 or lease in _KNOWN:
            raise RuntimeError("checkpoint descriptor lease registration failed")
        _KNOWN[lease] = state
        _ACTIVE.add(lease)
        _RESERVATIONS -= 1


def _known_state(
    value: Any,
) -> tuple[SeparationCheckpointDescriptorLease, _LeaseState]:
    if type(value) is not SeparationCheckpointDescriptorLease:
        raise ValueError("lease must be an exact parent-issued record")
    with _REGISTRY_LOCK:
        state = _KNOWN.get(value)
    if type(state) is not _LeaseState:
        raise ValueError("lease is not the known registered object")
    return value, state


def _state_phase(
    lease: SeparationCheckpointDescriptorLease,
    state: _LeaseState,
) -> str:
    with _REGISTRY_LOCK:
        active = lease in _ACTIVE
    finalizer_alive = state.finalizer.alive
    reservation_shape_valid = (
        state.fd5_reservation is None
        or type(state.fd5_reservation) is _FD5ReservationBinding
    )
    active_matrix = (
        state.status == "retained"
        and state.descriptor is not None
        and state.terminal_outcome is None
        and state.terminal_document is None
        and finalizer_alive
        and active
        and reservation_shape_valid
    )
    terminal_matrix = (
        state.status in _TERMINAL_STATUSES
        and state.descriptor is None
        and state.terminal_outcome is not None
        and state.terminal_document is not None
        and not finalizer_alive
        and not active
        and state.fd5_reservation is None
    )
    if active_matrix:
        return "active"
    if terminal_matrix:
        _validate_terminal_anchor(state.terminal_anchor)
        _validate_receipt_document(
            state.terminal_document,
            anchor=state.terminal_anchor,
            outcome=state.terminal_outcome,
        )
        if state.terminal_outcome.status != state.status:
            raise _IntegrityFailure("lease_state_matrix_invalid")
        return "terminal"
    raise _IntegrityFailure("lease_state_matrix_invalid")


def _require_owner(state: _LeaseState) -> None:
    if state.owner_pid != os.getpid():
        raise _IntegrityFailure("trusted_parent_pid_convention_violated")


def _validate_state_authority(state: _LeaseState) -> None:
    try:
        validate_separation_checkpoint_inspection(
            state.trusted_inspection,
            trusted_inspection=state.trusted_inspection,
            trusted_request=state.request,
        )
        expected_evidence = _expected_acquisition_evidence(state)
        expected_observation = _expected_observation_document(
            expected_evidence
        )
        expected_anchor = _new_terminal_anchor(
            expected_evidence,
            expected_observation,
        )
        if state.fd5_reservation is not None:
            _validate_fd5_reservation_binding(
                state.fd5_reservation,
                expected_worker_request_v1=state.request.worker_request,
                expected_inspection_request=state.request,
                expected_inspection=state.trusted_inspection,
                expected_lease_observation=state.observation_document,
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise _IntegrityFailure("lease_authority_binding_invalid") from exc
    if (
        _plain(state.acquisition_evidence) != expected_evidence
        or _plain(state.observation_document) != expected_observation
        or state.terminal_anchor != expected_anchor
    ):
        raise _IntegrityFailure("lease_authority_binding_invalid")


def _expected_acquisition_evidence(
    state: _LeaseState,
) -> dict[str, Any]:
    return _records_expected_acquisition_evidence(
        file_identity=_file_identity_document(state.file_identity),
        request=state.request,
        trusted_inspection=state.trusted_inspection,
        hash_value=_hash,
    )


def _remeasure(state: _LeaseState) -> None:
    descriptor = state.descriptor
    if descriptor is None:
        raise _IntegrityFailure("lease_live_ownership_invalid")
    try:
        before = _file_identity(os.fstat(descriptor))
        if before[:2] != state.file_identity[:2]:
            raise _IntegrityFailure("checkpoint_descriptor_ownership_lost")
        if before != state.file_identity:
            raise _IntegrityFailure("checkpoint_file_identity_changed")
        if os.get_inheritable(descriptor):
            raise _IntegrityFailure("checkpoint_descriptor_became_inheritable")
        digest, byte_count = _hash_descriptor(
            descriptor,
            state.request.checkpoint_bytes + 1,
        )
        after = _file_identity(os.fstat(descriptor))
    except _IntegrityFailure:
        raise
    except (OSError, ValueError) as exc:
        raise _IntegrityFailure(
            "checkpoint_descriptor_remeasurement_failed"
        ) from exc
    if after[:2] != state.file_identity[:2]:
        raise _IntegrityFailure("checkpoint_descriptor_ownership_lost")
    if before != after or after != state.file_identity:
        raise _IntegrityFailure(
            "checkpoint_file_identity_changed_during_remeasurement"
        )
    if os.get_inheritable(descriptor):
        raise _IntegrityFailure("checkpoint_descriptor_became_inheritable")
    if byte_count != state.request.checkpoint_bytes:
        raise _IntegrityFailure("checkpoint_byte_count_changed")
    if digest != state.request.checkpoint_sha256:
        raise _IntegrityFailure("checkpoint_hash_changed")


def _terminal_failure(
    lease: SeparationCheckpointDescriptorLease,
    state: _LeaseState,
    integrity_reasons: Sequence[str],
) -> None:
    cleanup_status, cleanup_reasons = _detach_and_close(lease, state)
    _store_terminal(
        state=state,
        status=(
            "integrity_failed"
            if cleanup_status == "complete"
            else "integrity_and_cleanup_failed"
        ),
        integrity_status="failed",
        integrity_reasons=integrity_reasons,
        cleanup_status=cleanup_status,
        cleanup_reasons=cleanup_reasons,
    )
    raise SeparationCheckpointDescriptorLeaseError(
        "checkpoint descriptor lease failed integrity verification",
        _receipt_wrapper(state),
    )


def _store_terminal(
    *,
    state: _LeaseState,
    status: str,
    integrity_status: str,
    integrity_reasons: Sequence[str],
    cleanup_status: str,
    cleanup_reasons: Sequence[str],
) -> None:
    if state.status in _TERMINAL_STATUSES:
        return
    outcome = _TerminalOutcome(
        status=status,
        integrity_status=integrity_status,
        integrity_reasons=tuple(sorted(set(integrity_reasons))),
        cleanup_status=cleanup_status,
        cleanup_reasons=tuple(sorted(set(cleanup_reasons))),
    )
    document = _receipt_document(state.terminal_anchor, outcome)
    (
        state.terminal_outcome,
        state.terminal_document,
        state.status,
    ) = (outcome, document, status)


def _detach_and_close(
    lease: SeparationCheckpointDescriptorLease,
    state: _LeaseState,
) -> tuple[str, tuple[str, ...]]:
    with _REGISTRY_LOCK:
        _ACTIVE.discard(lease)
    if state.finalizer.alive:
        state.finalizer.detach()
    descriptor = state.descriptor
    state.descriptor = None
    state.fd5_reservation = None
    state.status = "terminalizing"
    if descriptor is None:
        return "close_not_attempted", ("checkpoint_descriptor_ownership_lost",)
    try:
        observed = os.fstat(descriptor)
    except OSError:
        return "close_not_attempted", ("checkpoint_descriptor_ownership_lost",)
    if (observed.st_dev, observed.st_ino) != state.file_identity[:2]:
        return "close_not_attempted", ("checkpoint_descriptor_ownership_lost",)
    try:
        os.close(descriptor)
    except OSError:
        return "close_unconfirmed", ("checkpoint_descriptor_close_failed",)
    return "complete", ()


def _new_terminal_anchor(
    evidence: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> _TerminalAnchor:
    return _records_new_terminal_anchor(
        evidence,
        observation,
        maximum_checkpoint_bytes=MAX_CHECKPOINT_BYTES,
    )


def _validate_terminal_anchor(anchor: _TerminalAnchor) -> None:
    _records_validate_terminal_anchor(
        anchor,
        maximum_checkpoint_bytes=MAX_CHECKPOINT_BYTES,
    )


def _validate_receipt_document(
    document: Mapping[str, Any],
    *,
    anchor: _TerminalAnchor,
    outcome: _TerminalOutcome,
) -> None:
    _records_validate_receipt_document(
        document,
        anchor=anchor,
        outcome=outcome,
        maximum_checkpoint_bytes=MAX_CHECKPOINT_BYTES,
    )


def _observation_wrapper(
    document: Mapping[str, Any],
) -> SeparationCheckpointDescriptorLeaseObservation:
    value = object.__new__(SeparationCheckpointDescriptorLeaseObservation)
    object.__setattr__(value, "_document", document)
    return value


def _receipt_wrapper(
    state: _LeaseState,
) -> SeparationCheckpointDescriptorLeaseTerminalReceipt:
    outcome = state.terminal_outcome
    document = state.terminal_document
    if outcome is None or document is None:
        raise ValueError("checkpoint descriptor terminal receipt is unavailable")
    _validate_receipt_document(
        document,
        anchor=state.terminal_anchor,
        outcome=outcome,
    )
    value = object.__new__(
        SeparationCheckpointDescriptorLeaseTerminalReceipt
    )
    object.__setattr__(value, "_document", document)
    return value


def _finalize_owned_descriptor(
    descriptor: int,
    expected_devino: tuple[int, ...],
) -> None:
    _close_if_owned(descriptor, expected_devino)


def _hash(value: Any) -> str:
    return _checkpoint_canonical_sha256(value)


__all__ = [
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
