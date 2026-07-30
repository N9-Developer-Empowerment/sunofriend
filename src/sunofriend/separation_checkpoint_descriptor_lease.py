"""Parent-only live checkpoint descriptor lease.

Acquisition bridges one exact, already-closed V1 static inspection to a newly
opened and independently parsed descriptor.  Only the checkpoint leaf FD is
retained; ancestor directory FDs are closed by the inspector bridge.

This is private contract groundwork, not a loader or launch transport.  The
raw FD exists only in module-private weak registry state.  No public API
duplicates, inherits, hands off, deserializes or executes it.
"""

from __future__ import annotations

import hashlib
import os
import threading
import weakref
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _checkpoint_canonical_sha256,
    plain as _plain,
)
from ._separation_checkpoint_lease_records import (
    SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID,
    SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_OBSERVATION_SCHEMA,
    SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_RECEIPT_SCHEMA,
    _TERMINAL_STATUSES,
    _TerminalAnchor,
    _TerminalOutcome,
    expected_observation_document as _expected_observation_document,
    new_terminal_anchor as _records_new_terminal_anchor,
    observation_document as _observation_document,
    receipt_document as _receipt_document,
    validate_receipt_document as _records_validate_receipt_document,
    validate_terminal_anchor as _records_validate_terminal_anchor,
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
    active_matrix = (
        state.status == "retained"
        and state.descriptor is not None
        and state.terminal_outcome is None
        and state.terminal_document is None
        and finalizer_alive
        and active
    )
    terminal_matrix = (
        state.status in _TERMINAL_STATUSES
        and state.descriptor is None
        and state.terminal_outcome is not None
        and state.terminal_document is not None
        and not finalizer_alive
        and not active
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
    inspection = state.trusted_inspection
    checkpoint = inspection["checkpoint"]
    classification = inspection["classification"]
    archive = inspection["archive"]
    pickle = inspection["pickle"]
    identity = _file_identity_document(state.file_identity)
    if (
        _plain(checkpoint["file_identity"]) != identity
        or checkpoint["sha256"] != state.request.checkpoint_sha256
        or checkpoint["bytes"] != state.request.checkpoint_bytes
    ):
        raise ValueError("retained checkpoint identity authority changed")
    return {
        "bindings": {
            "worker_request_sha256": state.request.request_sha256,
            "preflight_sha256": state.request.preflight_sha256,
            "acceptance_artifact_sha256": (
                state.request.acceptance_artifact_sha256
            ),
            "trusted_checkpoint_inspection_sha256": inspection[
                "inspection_sha256"
            ],
            "checkpoint_sha256": state.request.checkpoint_sha256,
            "checkpoint_bytes": state.request.checkpoint_bytes,
            "checkpoint_file_identity_sha256": _hash(identity),
            "classification_evidence_sha256": classification[
                "classification_evidence_sha256"
            ],
            "archive_evidence_sha256": _hash(_plain(archive)),
            "pickle_evidence_sha256": (
                None if pickle is None else _hash(_plain(pickle))
            ),
        },
        "classification": {
            "container_kind": classification["container_kind"],
            "confidence": classification["confidence"],
            "evidence_equal_to_trusted_inspection": True,
        },
        "archive_metadata_parsed": archive["archive_metadata_parsed"],
        "pickle_opcodes_parsed": archive["pickle_metadata_parsed"],
    }


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


def _hash_descriptor(descriptor: int, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    try:
        while True:
            chunk = os.pread(
                descriptor,
                min(1024 * 1024, maximum_bytes + 1 - count),
                count,
            )
            if not chunk:
                break
            count += len(chunk)
            if count > maximum_bytes or count > MAX_CHECKPOINT_BYTES:
                raise ValueError("checkpoint exceeds retained byte limit")
            digest.update(chunk)
        return digest.hexdigest(), count
    finally:
        if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
            raise ValueError("checkpoint descriptor offset reset failed")


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


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
    )


def _file_identity_document(
    value: tuple[int, ...],
) -> dict[str, int]:
    return {
        "device": value[0],
        "inode": value[1],
        "mode": value[2],
        "links": value[3],
        "bytes": value[4],
        "mtime_ns": value[5],
        "ctime_ns": value[6],
        "uid": value[7],
    }


def _finalize_owned_descriptor(
    descriptor: int,
    expected_devino: tuple[int, ...],
) -> None:
    _close_if_owned(descriptor, expected_devino)


def _close_if_owned(
    descriptor: int,
    expected_devino: tuple[int, ...],
) -> None:
    try:
        observed = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino) == expected_devino:
            os.close(descriptor)
    except OSError:
        pass


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
