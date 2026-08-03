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
_FAKE_EXECUTION_LEASE_FAILURES: weakref.WeakKeyDictionary[
    _FakeExecutionLeaseFailureAuthority, _FakeExecutionLeaseFailureBinding
] = weakref.WeakKeyDictionary()
_FAKE_EXECUTION_LEASE_FAILURES_EVER_ISSUED: weakref.WeakSet[
    _FakeExecutionLeaseFailure
] = weakref.WeakSet()


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


class _FakeExecutionLeaseFailureAuthority:
    """Opaque one-shot proof that the lease lifecycle issued one failure."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError(
            "fake execution lease failure authorities are parent-issued only"
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError(
            "fake execution lease failure authorities cannot be copied"
        )

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError(
            "fake execution lease failure authorities cannot be copied"
        )

    def __reduce__(self) -> Any:
        raise TypeError(
            "fake execution lease failure authorities cannot be serialized"
        )

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError(
            "fake execution lease failure authorities cannot be serialized"
        )


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
        self._lease_failure_authority: (
            _FakeExecutionLeaseFailureAuthority | None
        ) = None

    def _record_cleanup(self, stage: str, error: BaseException) -> None:
        self.cleanup_stages = (*self.cleanup_stages, stage)
        self.cleanup_errors = (*self.cleanup_errors, error)


@dataclass
class _FakeExecutionLeaseFailureBinding:
    owner_pid: int
    failure_ref: weakref.ReferenceType[_FakeExecutionLeaseFailure]
    lease: SeparationCheckpointDescriptorLease
    lease_state: _LeaseState
    reservation: _CheckpointDescriptorFD5Reservation
    worker_request_v2: SeparationWorkerRequestV2Record
    lease_observation: SeparationCheckpointDescriptorLeaseObservation
    lease_receipt: SeparationCheckpointDescriptorLeaseTerminalReceipt
    fake_worker_request: Any
    fake_launch_plan_v1: Any
    blocked_fake_launch_plan_v2: Any
    fake_launch_plan_v3: Any
    fake_chain_snapshot: tuple[tuple[type[Any], int, str], ...]
    primary_error_snapshot: tuple[Any, ...]
    cleanup_stages: tuple[str, ...]
    cleanup_error_identities: tuple[int, ...]
    core: Any | None
    private_root_owner: Any | None
    status: str


def _fake_execution_lease_failure_private_root_owner(
    value: _FakeExecutionLeaseFailure,
) -> Any | None:
    if value.core is not None:
        return value.core
    primary = value.primary_error
    return getattr(primary, "private_root_owner", None)


def _fake_execution_failure_snapshot(
    value: BaseException | None,
    *,
    depth: int = 0,
    seen: tuple[int, ...] = (),
) -> tuple[Any, ...]:
    """Capture identity-only nested failure state without exception text."""

    if value is None:
        return ("none",)
    if not isinstance(value, BaseException) or depth > 4:
        raise ValueError("fake execution primary failure chain is invalid")
    identity = id(value)
    if identity in seen:
        raise ValueError("fake execution primary failure chain is cyclic")
    cleanup_stages = getattr(value, "cleanup_stages", ())
    cleanup_errors = getattr(value, "cleanup_errors", ())
    descriptor_owners = getattr(value, "descriptor_owners", ())
    if (
        type(cleanup_stages) is not tuple
        or type(cleanup_errors) is not tuple
        or len(cleanup_stages) != len(cleanup_errors)
        or any(type(stage) is not str for stage in cleanup_stages)
        or any(
            not isinstance(error, BaseException)
            for error in cleanup_errors
        )
        or type(descriptor_owners) is not tuple
    ):
        raise ValueError("fake execution primary failure state is invalid")
    observation = getattr(value, "observation", None)
    private_root_owner = getattr(value, "private_root_owner", None)
    observation_sha256: str | None = None
    if observation is not None:
        if not isinstance(observation, Mapping):
            raise ValueError(
                "fake execution primary failure observation is invalid"
            )
        observation_sha256 = observation.get("observation_sha256")
        if (
            type(observation_sha256) is not str
            or len(observation_sha256) != 64
        ):
            raise ValueError(
                "fake execution primary failure observation is invalid"
            )
    child = getattr(value, "primary_error", None)
    child_snapshot = (
        ("absent",)
        if not hasattr(value, "primary_error")
        else _fake_execution_failure_snapshot(
            child,
            depth=depth + 1,
            seen=(*seen, identity),
        )
    )
    return (
        type(value),
        identity,
        cleanup_stages,
        tuple(id(error) for error in cleanup_errors),
        tuple(id(owner) for owner in descriptor_owners),
        id(private_root_owner) if private_root_owner is not None else None,
        id(observation) if observation is not None else None,
        observation_sha256,
        child_snapshot,
    )


def _fake_execution_chain_snapshot(
    *,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
) -> tuple[tuple[type[Any], int, str], ...]:
    values = (
        (fake_worker_request, "request_sha256"),
        (fake_launch_plan_v1, "plan_sha256"),
        (blocked_fake_launch_plan_v2, "plan_sha256"),
        (fake_launch_plan_v3, "plan_sha256"),
    )
    result: list[tuple[type[Any], int, str]] = []
    for value, field in values:
        if not isinstance(value, Mapping):
            raise ValueError("fake execution failure chain is invalid")
        digest = value.get(field)
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("fake execution failure chain is invalid")
        result.append((type(value), id(value), digest))
    return tuple(result)


def _valid_fake_execution_failure_cleanup_snapshot(
    value: _FakeExecutionLeaseFailure,
    binding: _FakeExecutionLeaseFailureBinding,
) -> bool:
    stages = value.cleanup_stages
    errors = value.cleanup_errors
    return (
        type(stages) is tuple
        and type(errors) is tuple
        and stages == binding.cleanup_stages
        and tuple(id(error) for error in errors)
        == binding.cleanup_error_identities
    )


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


def _start_reserved_private_melroformer_native_worker_darwin(
    trusted_lease: SeparationCheckpointDescriptorLease,
    *,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    trusted_native_session: Any,
    native_session_observation: Any,
    request: Mapping[str, Any],
    staging_directory: str | os.PathLike[str],
    request_read_descriptor: int,
    result_write_descriptor: int,
    ready_write_descriptor: int,
    release_read_descriptor: int,
) -> Any:
    """Start the fixed native Kim worker while fd5 remains lease-owned.

    This private bridge is the only place where the raw retained checkpoint
    descriptor crosses from the live lease registry to the guarded native
    start.  The descriptor never leaves this stack frame as a return value or
    serialized field.  The exact reservation remains active after a successful
    start so the later coordinator must supervise the owner, recheck fd5,
    release the reservation and close the lease.

    The four child-only transport descriptors transfer only when the guarded
    start is invoked.  Binding failures before that call leave them with the
    caller.  No public route imports this function.
    """

    from . import _separation_melroformer_native_session_darwin as native_session
    from ._separation_melroformer_native_transport import (
        _validate_private_melroformer_native_request,
    )

    checked_request = _validate_private_melroformer_native_request(request)
    lease, state = _known_state(trusted_lease)
    with state.lock:
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
                "private Kim native start must use the exact reserved request"
            )
        if (
            current_lease_observation is not binding.lease_observation
            or getattr(current_lease_observation, "_document", None)
            is not state.observation_document
        ):
            raise ValueError(
                "private Kim native start requires the exact lease observation"
            )
        descriptor = state.descriptor
        if type(descriptor) is not int or descriptor < 3:
            raise ValueError(
                "checkpoint descriptor lease ownership is invalid"
            )
        checked_session_observation = (
            native_session._validate_verified_private_melroformer_native_session_observation(
                trusted_native_session,
                native_session_observation,
            )
        )
        _validate_private_melroformer_native_lease_bindings(
            request=checked_request,
            lease_observation=current_lease_observation,
            inspection_request=state.request,
            worker_request_v2=trusted_worker_request_v2,
            native_session_observation=checked_session_observation,
        )
        admission = native_session._issue_private_melroformer_native_admission(
            trusted_session=trusted_native_session,
            session_observation=checked_session_observation,
            request=checked_request,
        )
        return native_session._start_verified_private_melroformer_native_worker(
            trusted_native_session,
            session_observation=checked_session_observation,
            trusted_admission=admission,
            request=checked_request,
            staging_directory=staging_directory,
            request_read_descriptor=request_read_descriptor,
            result_write_descriptor=result_write_descriptor,
            checkpoint_read_descriptor=descriptor,
            ready_write_descriptor=ready_write_descriptor,
            release_read_descriptor=release_read_descriptor,
        )


def _validate_private_melroformer_native_lease_bindings(
    *,
    request: Mapping[str, Any],
    lease_observation: Mapping[str, Any],
    inspection_request: Any,
    worker_request_v2: Mapping[str, Any],
    native_session_observation: Mapping[str, Any],
) -> None:
    """Cross-bind the native request to the exact lease and fixed session."""

    try:
        native_document = _plain(request)
        native_identities = native_document["identities"]
        native_paths = native_document["paths"]
        lease_document = _plain(lease_observation)
        worker_document = _plain(worker_request_v2)
        session_document = _plain(native_session_observation)
        lease_bindings = lease_document["bindings"]
        worker_bindings = worker_document["bindings"]
        fixed_worker = session_document["bindings"]["fixed_kim_worker"]
        inspection_checkpoint_path = inspection_request.checkpoint_path
        expected_checkpoint = {
            "sha256": lease_bindings["checkpoint_sha256"],
            "bytes": lease_bindings["checkpoint_bytes"],
        }
        native_checkpoint = {
            "sha256": native_identities["checkpoint_sha256"],
            "bytes": native_identities["checkpoint_bytes"],
        }
        native_worker_sha256 = native_identities["worker_source_sha256"]
        fixed_worker_sha256 = fixed_worker["sha256"]
        native_checkpoint_path = native_paths["checkpoint_path"]
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError(
            "private Kim native lease binding evidence is incomplete"
        ) from exc
    if native_checkpoint != expected_checkpoint:
        raise ValueError(
            "private Kim native request does not bind the leased checkpoint"
        )
    if (
        worker_bindings.get("lease_observation_sha256")
        != lease_document.get("observation_sha256")
        or worker_bindings.get("checkpoint_sha256")
        != expected_checkpoint["sha256"]
        or worker_bindings.get("checkpoint_bytes")
        != expected_checkpoint["bytes"]
    ):
        raise ValueError(
            "reserved worker request does not bind the leased checkpoint"
        )
    if native_worker_sha256 != fixed_worker_sha256:
        raise ValueError(
            "private Kim native request does not bind the fixed session worker"
        )
    if os.fspath(inspection_checkpoint_path) != native_checkpoint_path:
        raise ValueError(
            "private Kim native request checkpoint path differs from the lease"
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
            try:
                _remeasure(state)
            except _IntegrityFailure as exc:
                _terminal_failure(lease, state, (exc.reason,))
            except Exception:
                _terminal_failure(
                    lease,
                    state,
                    ("checkpoint_descriptor_remeasurement_failed",),
                )
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
            and primary_error is None
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
            failure = _new_fake_execution_lease_failure(
                trusted_lease=lease,
                lease_state=state,
                trusted_reservation=trusted_reservation,
                trusted_worker_request_v2=trusted_worker_request_v2,
                current_lease_observation=current_lease_observation,
                fake_worker_request=fake_worker_request,
                fake_launch_plan_v1=fake_launch_plan_v1,
                blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
                fake_launch_plan_v3=fake_launch_plan_v3,
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


def _new_fake_execution_lease_failure(
    *,
    trusted_lease: SeparationCheckpointDescriptorLease,
    lease_state: _LeaseState,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
    primary_error: BaseException | None,
    cleanup_failures: Sequence[tuple[str, BaseException]],
    lease_receipt: (SeparationCheckpointDescriptorLeaseTerminalReceipt | None),
    core: Any | None,
) -> _FakeExecutionLeaseFailure:
    """Create one aggregate and bind it when terminal lease proof is valid."""

    failure = _FakeExecutionLeaseFailure(
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
        lease_receipt=lease_receipt,
        core=core,
    )
    if lease_receipt is None:
        return failure
    try:
        authority = _issue_fake_execution_lease_failure_authority(
            failure,
            trusted_lease=trusted_lease,
            lease_state=lease_state,
            trusted_reservation=trusted_reservation,
            trusted_worker_request_v2=trusted_worker_request_v2,
            current_lease_observation=current_lease_observation,
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
            fake_launch_plan_v3=fake_launch_plan_v3,
            lease_receipt=lease_receipt,
        )
    except BaseException as authentication_error:
        # Authentication is fail-closed and must not replace the real failure.
        failure._record_cleanup(
            "lease_failure_authentication",
            authentication_error,
        )
        return failure
    failure._lease_failure_authority = authority
    return failure


def _issue_fake_execution_lease_failure_authority(
    failure: _FakeExecutionLeaseFailure,
    *,
    trusted_lease: SeparationCheckpointDescriptorLease,
    lease_state: _LeaseState,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
    lease_receipt: SeparationCheckpointDescriptorLeaseTerminalReceipt,
) -> _FakeExecutionLeaseFailureAuthority:
    """Bind one failure to exact terminal lease state while its lock is held."""

    if type(failure) is not _FakeExecutionLeaseFailure:
        raise ValueError("fake execution lease failure type is invalid")
    lease, known_state = _known_state(trusted_lease)
    if known_state is not lease_state:
        raise ValueError("fake execution lease failure state changed")
    _require_owner(lease_state)
    if _state_phase(lease, lease_state) != "terminal":
        raise ValueError("fake execution lease failure is not terminal")
    if (
        type(trusted_reservation) is not _CheckpointDescriptorFD5Reservation
        or type(trusted_worker_request_v2)
        is not SeparationWorkerRequestV2Record
        or type(current_lease_observation)
        is not SeparationCheckpointDescriptorLeaseObservation
        or current_lease_observation._document
        is not lease_state.observation_document
        or type(lease_receipt)
        is not SeparationCheckpointDescriptorLeaseTerminalReceipt
        or lease_receipt._document is not lease_state.terminal_document
        or failure.lease_receipt is not lease_receipt
    ):
        raise ValueError("fake execution lease failure binding is invalid")
    validated_receipt = _receipt_wrapper(lease_state)
    if (
        validated_receipt._document is not lease_receipt._document
        or validated_receipt["receipt_sha256"]
        != lease_receipt["receipt_sha256"]
    ):
        raise ValueError("fake execution lease failure receipt changed")
    authority = object.__new__(_FakeExecutionLeaseFailureAuthority)
    primary_error_snapshot = _fake_execution_failure_snapshot(
        failure.primary_error
    )
    fake_chain_snapshot = _fake_execution_chain_snapshot(
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
        fake_launch_plan_v3=fake_launch_plan_v3,
    )
    binding = _FakeExecutionLeaseFailureBinding(
        owner_pid=os.getpid(),
        failure_ref=weakref.ref(failure),
        lease=lease,
        lease_state=lease_state,
        reservation=trusted_reservation,
        worker_request_v2=trusted_worker_request_v2,
        lease_observation=current_lease_observation,
        lease_receipt=lease_receipt,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
        fake_launch_plan_v3=fake_launch_plan_v3,
        fake_chain_snapshot=fake_chain_snapshot,
        primary_error_snapshot=primary_error_snapshot,
        cleanup_stages=failure.cleanup_stages,
        cleanup_error_identities=tuple(
            id(error) for error in failure.cleanup_errors
        ),
        core=failure.core,
        private_root_owner=(
            _fake_execution_lease_failure_private_root_owner(failure)
        ),
        status="issued_under_terminal_lease_lock",
    )
    with _REGISTRY_LOCK:
        if (
            failure in _FAKE_EXECUTION_LEASE_FAILURES_EVER_ISSUED
            or failure._lease_failure_authority is not None
            or authority in _FAKE_EXECUTION_LEASE_FAILURES
        ):
            raise RuntimeError(
                "fake execution lease failure authority was already issued"
            )
        _FAKE_EXECUTION_LEASE_FAILURES_EVER_ISSUED.add(failure)
        _FAKE_EXECUTION_LEASE_FAILURES[authority] = binding
    return authority


def _consume_fake_execution_lease_failure(
    value: Any,
    *,
    trusted_lease: SeparationCheckpointDescriptorLease,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
) -> SeparationCheckpointDescriptorLeaseTerminalReceipt:
    """Consume exact one-use authority and return revalidated lease evidence."""

    receipt, _action_result = (
        _consume_fake_execution_lease_failure_with_authenticated_action(
            value,
            trusted_lease=trusted_lease,
            trusted_reservation=trusted_reservation,
            trusted_worker_request_v2=trusted_worker_request_v2,
            current_lease_observation=current_lease_observation,
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
            fake_launch_plan_v3=fake_launch_plan_v3,
            authenticated_action=lambda _private_root_owner: None,
        )
    )
    return receipt


def _consume_fake_execution_lease_failure_with_authenticated_action(
    value: Any,
    *,
    trusted_lease: SeparationCheckpointDescriptorLease,
    trusted_reservation: _CheckpointDescriptorFD5Reservation,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: SeparationCheckpointDescriptorLeaseObservation,
    fake_worker_request: Any,
    fake_launch_plan_v1: Any,
    blocked_fake_launch_plan_v2: Any,
    fake_launch_plan_v3: Any,
    authenticated_action: Any,
) -> tuple[SeparationCheckpointDescriptorLeaseTerminalReceipt, Any]:
    """Run one action only after exact failure authentication, then consume."""

    if type(value) is not _FakeExecutionLeaseFailure:
        raise ValueError("fake execution lease failure type is invalid")
    if not callable(authenticated_action):
        raise TypeError("fake execution authenticated action is not callable")
    authority = value._lease_failure_authority
    if type(authority) is not _FakeExecutionLeaseFailureAuthority:
        raise ValueError("fake execution lease failure is not lease-issued")
    lease, state = _known_state(trusted_lease)
    with state.lock:
        with _REGISTRY_LOCK:
            binding = _FAKE_EXECUTION_LEASE_FAILURES.get(authority)
        if (
            type(binding) is not _FakeExecutionLeaseFailureBinding
            or binding.owner_pid != os.getpid()
            or binding.status != "issued_under_terminal_lease_lock"
            or binding.failure_ref() is not value
            or binding.lease is not lease
            or binding.lease_state is not state
            or binding.reservation is not trusted_reservation
            or binding.worker_request_v2 is not trusted_worker_request_v2
            or binding.lease_observation is not current_lease_observation
            or binding.lease_receipt is not value.lease_receipt
            or binding.fake_worker_request is not fake_worker_request
            or binding.fake_launch_plan_v1 is not fake_launch_plan_v1
            or binding.blocked_fake_launch_plan_v2
            is not blocked_fake_launch_plan_v2
            or binding.fake_launch_plan_v3 is not fake_launch_plan_v3
            or binding.fake_chain_snapshot
            != _fake_execution_chain_snapshot(
                fake_worker_request=fake_worker_request,
                fake_launch_plan_v1=fake_launch_plan_v1,
                blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
                fake_launch_plan_v3=fake_launch_plan_v3,
            )
            or binding.primary_error_snapshot
            != _fake_execution_failure_snapshot(value.primary_error)
            or not _valid_fake_execution_failure_cleanup_snapshot(
                value,
                binding,
            )
            or binding.core is not value.core
            or binding.private_root_owner
            is not _fake_execution_lease_failure_private_root_owner(value)
        ):
            raise ValueError("fake execution lease failure binding changed")
        _require_owner(state)
        if _state_phase(lease, state) != "terminal":
            raise ValueError("fake execution lease failure is not terminal")
        if (
            type(trusted_reservation)
            is not _CheckpointDescriptorFD5Reservation
            or type(trusted_worker_request_v2)
            is not SeparationWorkerRequestV2Record
            or type(current_lease_observation)
            is not SeparationCheckpointDescriptorLeaseObservation
            or current_lease_observation._document
            is not state.observation_document
            or type(binding.lease_receipt)
            is not SeparationCheckpointDescriptorLeaseTerminalReceipt
            or binding.lease_receipt._document is not state.terminal_document
        ):
            raise ValueError("fake execution lease failure binding is invalid")
        validated_receipt = _receipt_wrapper(state)
        if (
            validated_receipt._document is not binding.lease_receipt._document
            or validated_receipt["receipt_sha256"]
            != binding.lease_receipt["receipt_sha256"]
        ):
            raise ValueError("fake execution lease failure receipt changed")
        action_result = authenticated_action(binding.private_root_owner)
        with _REGISTRY_LOCK:
            current = _FAKE_EXECUTION_LEASE_FAILURES.get(authority)
            if current is not binding:
                raise ValueError(
                    "fake execution lease failure authority changed"
                )
            binding.status = "consumed"
            del _FAKE_EXECUTION_LEASE_FAILURES[authority]
        value._lease_failure_authority = None
        return binding.lease_receipt, action_result


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
