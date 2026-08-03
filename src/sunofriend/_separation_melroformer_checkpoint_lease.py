"""Private descriptor lease for the exact Kim Vocal 2 Safetensors file.

The general separation checkpoint lease is intentionally rooted in the
pre-registered public bake-off acceptance contract.  This separate lease is
for the already-approved private Kim evaluation only.  It binds the fixed
native request, author-hosted licence evidence and exact descriptor-pinned
Safetensors inspection without inventing a hidden-corpus acceptance result.

It does not load tensor values, import a model, start a process, read audio or
grant execution/product authority.
"""

from __future__ import annotations

import fcntl
import os
import stat
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_native_transport import (
    _validate_private_melroformer_native_request,
)
from ._separation_melroformer_upstream_evidence import (
    _verify_private_melroformer_upstream_evidence,
)
from ._separation_safetensors_inspection import (
    _inspect_private_safetensors_descriptor,
)
from ._separation_worker_request_v2_values import _validate_path_free


__all__: tuple[str, ...] = ()

_OBSERVATION_SCHEMA = "sunofriend.private-kim-checkpoint-lease-observation.v1"
_RECEIPT_SCHEMA = "sunofriend.private-kim-checkpoint-lease-receipt.v1"
_POLICY_ID = "private-kim-vocal-2-checkpoint-descriptor-lease-v1"
_MAXIMUM_ACTIVE = 2
_REGISTRY_LOCK = threading.RLock()
_ACQUIRING = 0


class _PrivateMelroformerCheckpointLease:
    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("private Kim checkpoint leases are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("private Kim checkpoint leases cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("private Kim checkpoint leases cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("private Kim checkpoint leases cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("private Kim checkpoint leases cannot be serialized")


@dataclass(frozen=True, init=False)
class _PrivateMelroformerCheckpointLeaseObservation(Mapping[str, Any]):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class _PrivateMelroformerCheckpointLeaseReceipt(Mapping[str, Any]):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


class _PrivateMelroformerCheckpointLeaseError(RuntimeError):
    def __init__(
        self,
        message: str,
        receipt: _PrivateMelroformerCheckpointLeaseReceipt,
    ) -> None:
        super().__init__(message)
        self.receipt = receipt


@dataclass
class _LeaseState:
    lock: Any
    owner_pid: int
    request: Mapping[str, Any]
    checkpoint_path: Path
    descriptor: int | None
    file_identity: tuple[int, ...]
    inspection: Mapping[str, Any]
    upstream_evidence_sha256: str
    observation_document: Mapping[str, Any]
    terminal_document: Mapping[str, Any] | None
    finalizer: weakref.finalize
    status: str


_KNOWN: weakref.WeakKeyDictionary[
    _PrivateMelroformerCheckpointLease, _LeaseState
] = weakref.WeakKeyDictionary()
_ACTIVE: weakref.WeakSet[_PrivateMelroformerCheckpointLease] = weakref.WeakSet()


def _acquire_private_melroformer_checkpoint_lease(
    request: Mapping[str, Any],
) -> tuple[
    _PrivateMelroformerCheckpointLease,
    _PrivateMelroformerCheckpointLeaseObservation,
]:
    """Retain one exact local checkpoint descriptor without loading it."""

    global _ACQUIRING

    checked_request = _validate_private_melroformer_native_request(request)
    checkpoint_path = Path(checked_request["paths"]["checkpoint_path"])
    repository_root = checked_request["paths"]["repository_root"]
    with _REGISTRY_LOCK:
        if len(_ACTIVE) + _ACQUIRING >= _MAXIMUM_ACTIVE:
            raise RuntimeError("private Kim checkpoint lease limit reached")
        _ACQUIRING += 1

    descriptor: int | None = None
    finalizer: weakref.finalize | None = None
    acquisition_reserved = True
    try:
        upstream = _verify_private_melroformer_upstream_evidence(
            repository_root
        )
        upstream_sha256 = _hash(_plain(upstream))
        descriptor, file_identity = _open_exact_checkpoint(
            checkpoint_path,
            expected_bytes=checked_request["identities"]["checkpoint_bytes"],
        )
        inspection = _inspect_private_safetensors_descriptor(
            descriptor,
            expected_bytes=checked_request["identities"]["checkpoint_bytes"],
            expected_sha256=checked_request["identities"]["checkpoint_sha256"],
        )
        _require_checkpoint_unchanged(
            checkpoint_path,
            descriptor,
            file_identity,
        )
        observation_document = _build_observation(
            request=checked_request,
            file_identity=file_identity,
            inspection=inspection,
            upstream_evidence_sha256=upstream_sha256,
        )
        lease = object.__new__(_PrivateMelroformerCheckpointLease)
        finalizer = weakref.finalize(
            lease,
            _finalize_descriptor,
            descriptor,
            file_identity[:2],
        )
        state = _LeaseState(
            lock=threading.RLock(),
            owner_pid=os.getpid(),
            request=checked_request,
            checkpoint_path=checkpoint_path,
            descriptor=descriptor,
            file_identity=file_identity,
            inspection=_freeze(_plain(inspection)),
            upstream_evidence_sha256=upstream_sha256,
            observation_document=observation_document,
            terminal_document=None,
            finalizer=finalizer,
            status="retained",
        )
        with _REGISTRY_LOCK:
            _KNOWN[lease] = state
            _ACTIVE.add(lease)
            _ACQUIRING -= 1
            acquisition_reserved = False
        descriptor = None
        return lease, _observation(observation_document)
    except BaseException:
        if finalizer is not None and finalizer.alive:
            finalizer.detach()
        _close_if_open(descriptor)
        if acquisition_reserved:
            with _REGISTRY_LOCK:
                _ACQUIRING -= 1
        raise


def _recheck_private_melroformer_checkpoint_lease(
    trusted_lease: _PrivateMelroformerCheckpointLease,
) -> _PrivateMelroformerCheckpointLeaseObservation:
    """Remeasure the exact descriptor and pathname binding under the lease."""

    lease, state = _known_state(trusted_lease)
    with state.lock:
        _require_owner(state)
        if state.status != "retained":
            raise _PrivateMelroformerCheckpointLeaseError(
                "private Kim checkpoint lease is terminal",
                _receipt(state),
            )
        try:
            _remeasure(state)
        except BaseException as error:
            receipt = _terminalize(
                lease,
                state,
                status="integrity_failed",
                integrity_status="failed",
                integrity_reason="checkpoint_remeasurement_failed",
            )
            raise _PrivateMelroformerCheckpointLeaseError(
                "private Kim checkpoint lease integrity failed",
                receipt,
            ) from error
        return _observation(state.observation_document)


def _close_private_melroformer_checkpoint_lease(
    trusted_lease: _PrivateMelroformerCheckpointLease,
) -> _PrivateMelroformerCheckpointLeaseReceipt:
    """Remeasure and close one exact private checkpoint descriptor."""

    lease, state = _known_state(trusted_lease)
    with state.lock:
        _require_owner(state)
        if state.status != "retained":
            return _receipt(state)
        try:
            _remeasure(state)
        except BaseException as error:
            receipt = _terminalize(
                lease,
                state,
                status="integrity_failed",
                integrity_status="failed",
                integrity_reason="checkpoint_remeasurement_failed",
            )
            raise _PrivateMelroformerCheckpointLeaseError(
                "private Kim checkpoint lease integrity failed",
                receipt,
            ) from error
        receipt = _terminalize(
            lease,
            state,
            status="closed",
            integrity_status="verified_before_close_attempt",
            integrity_reason=None,
        )
        if receipt["cleanup"]["status"] != "complete":
            raise _PrivateMelroformerCheckpointLeaseError(
                "private Kim checkpoint descriptor close failed",
                receipt,
            )
        return receipt


def _open_exact_checkpoint(
    path: Path,
    *,
    expected_bytes: int,
) -> tuple[int, tuple[int, ...]]:
    before = path.lstat()
    if (
        not path.is_absolute()
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) & 0o077
        or before.st_size != expected_bytes
    ):
        raise ValueError("private Kim checkpoint file boundary differs")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        identity = _file_identity(opened)
        if (
            os.get_inheritable(descriptor)
            or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
            != os.O_RDONLY
            or identity != _file_identity(before)
        ):
            raise ValueError("private Kim checkpoint changed before lease")
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _remeasure(state: _LeaseState) -> None:
    descriptor = state.descriptor
    if descriptor is None:
        raise RuntimeError("private Kim checkpoint descriptor is unavailable")
    _require_checkpoint_unchanged(
        state.checkpoint_path,
        descriptor,
        state.file_identity,
    )
    inspection = _inspect_private_safetensors_descriptor(
        descriptor,
        expected_bytes=state.request["identities"]["checkpoint_bytes"],
        expected_sha256=state.request["identities"]["checkpoint_sha256"],
    )
    _require_checkpoint_unchanged(
        state.checkpoint_path,
        descriptor,
        state.file_identity,
    )
    if _plain(inspection) != _plain(state.inspection):
        raise RuntimeError("private Kim checkpoint inspection changed")
    expected = _build_observation(
        request=state.request,
        file_identity=state.file_identity,
        inspection=inspection,
        upstream_evidence_sha256=state.upstream_evidence_sha256,
    )
    if _plain(expected) != _plain(state.observation_document):
        raise RuntimeError("private Kim checkpoint lease authority changed")


def _require_checkpoint_unchanged(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, ...],
) -> None:
    descriptor_state = os.fstat(descriptor)
    path_state = path.lstat()
    if (
        os.get_inheritable(descriptor)
        or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
        != os.O_RDONLY
        or _file_identity(descriptor_state) != expected_identity
        or _file_identity(path_state) != expected_identity
    ):
        raise RuntimeError("private Kim checkpoint identity changed")


def _build_observation(
    *,
    request: Mapping[str, Any],
    file_identity: tuple[int, ...],
    inspection: Mapping[str, Any],
    upstream_evidence_sha256: str,
) -> Mapping[str, Any]:
    payload = {
        "schema": _OBSERVATION_SCHEMA,
        "policy_id": _POLICY_ID,
        "status": "retained_not_loaded",
        "evidence_scope": "private_local_checkpoint_identity_only",
        "bindings": {
            "native_request_sha256": request["request_sha256"],
            "checkpoint_sha256": request["identities"]["checkpoint_sha256"],
            "checkpoint_bytes": request["identities"]["checkpoint_bytes"],
            "checkpoint_file_identity_sha256": _hash(
                _file_identity_document(file_identity)
            ),
            "safetensors_inspection_sha256": _hash(_plain(inspection)),
            "upstream_evidence_sha256": upstream_evidence_sha256,
        },
        "inspection": {
            "container": inspection["container"],
            "status": inspection["status"],
            "tensor_count": inspection["tensor_count"],
            "tensor_names_sha256": inspection["tensor_names_sha256"],
            "tensor_values_observed": inspection["tensor_values_observed"],
            "descriptor_pinned": inspection["descriptor_pinned"],
        },
        "descriptor": {
            "retained": True,
            "read_only": True,
            "inheritable": False,
            "raw_descriptor_exposed": False,
            "pathname_matches_descriptor": True,
        },
        "effects": {
            "checkpoint_opened": True,
            "checkpoint_hashed": True,
            "tensor_values_observed": False,
            "checkpoint_loaded": False,
            "model_imported": False,
            "process_started": False,
            "audio_read": False,
            "network_used": False,
            "files_written": False,
        },
        "permissions": _permissions(),
        "limitations": [
            "lease_is_not_execution_or_model_load_authority",
            "checkpoint_path_can_change_after_the_last_remeasurement",
            "checkpoint_file_is_not_an_immutable_snapshot",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = _freeze({**payload, "observation_sha256": _hash(payload)})
    _validate_path_free(_plain(document), "private Kim checkpoint observation")
    return document


def _terminalize(
    lease: _PrivateMelroformerCheckpointLease,
    state: _LeaseState,
    *,
    status: str,
    integrity_status: str,
    integrity_reason: str | None,
) -> _PrivateMelroformerCheckpointLeaseReceipt:
    descriptor = state.descriptor
    cleanup_status = "complete"
    cleanup_reason: str | None = None
    try:
        _close_if_open(descriptor)
    except OSError:
        cleanup_status = "close_unconfirmed"
        cleanup_reason = "checkpoint_descriptor_close_failed"
    else:
        if state.finalizer.alive:
            state.finalizer.detach()
    state.descriptor = None
    with _REGISTRY_LOCK:
        _ACTIVE.discard(lease)
    if cleanup_status != "complete":
        status = (
            "integrity_and_cleanup_failed"
            if integrity_status == "failed"
            else "cleanup_failed"
        )
    state.status = status
    state.terminal_document = _build_receipt(
        state,
        status=status,
        integrity_status=integrity_status,
        integrity_reason=integrity_reason,
        cleanup_status=cleanup_status,
        cleanup_reason=cleanup_reason,
    )
    return _receipt(state)


def _build_receipt(
    state: _LeaseState,
    *,
    status: str,
    integrity_status: str,
    integrity_reason: str | None,
    cleanup_status: str,
    cleanup_reason: str | None,
) -> Mapping[str, Any]:
    payload = {
        "schema": _RECEIPT_SCHEMA,
        "policy_id": _POLICY_ID,
        "status": status,
        "bindings": {
            "lease_observation_sha256": state.observation_document[
                "observation_sha256"
            ],
            **_plain(state.observation_document["bindings"]),
        },
        "integrity": {
            "status": integrity_status,
            "reasons": [] if integrity_reason is None else [integrity_reason],
        },
        "cleanup": {
            "status": cleanup_status,
            "reasons": [] if cleanup_reason is None else [cleanup_reason],
            "descriptor_close_attempted": True,
            "descriptor_close_call_succeeded": cleanup_status == "complete",
        },
        "effects": {
            "checkpoint_descriptor_retained": False,
            "checkpoint_descriptor_close_attempted": True,
            "checkpoint_descriptor_close_call_succeeded": (
                cleanup_status == "complete"
            ),
            "checkpoint_loaded": False,
            "model_imported": False,
            "process_started": False,
            "audio_read": False,
            "network_used": False,
            "files_written": False,
        },
        "permissions": _permissions(),
        "limitations": [
            "descriptor_close_success_is_not_post_close_kernel_proof",
            "checkpoint_content_can_change_after_the_last_remeasurement",
        ],
    }
    document = _freeze({**payload, "receipt_sha256": _hash(payload)})
    _validate_path_free(_plain(document), "private Kim checkpoint receipt")
    return document


def _permissions() -> dict[str, bool]:
    return {
        "model_load_permitted": False,
        "execution_permitted": False,
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _file_identity_document(value: tuple[int, ...]) -> dict[str, int]:
    return dict(
        zip(
            ("device", "inode", "mode", "links", "uid", "bytes", "mtime_ns", "ctime_ns"),
            value,
        )
    )


def _observation(
    document: Mapping[str, Any],
) -> _PrivateMelroformerCheckpointLeaseObservation:
    value = object.__new__(_PrivateMelroformerCheckpointLeaseObservation)
    object.__setattr__(value, "_document", document)
    return value


def _receipt(state: _LeaseState) -> _PrivateMelroformerCheckpointLeaseReceipt:
    if state.terminal_document is None:
        raise RuntimeError("private Kim checkpoint lease is not terminal")
    value = object.__new__(_PrivateMelroformerCheckpointLeaseReceipt)
    object.__setattr__(value, "_document", state.terminal_document)
    return value


def _known_state(
    value: Any,
) -> tuple[_PrivateMelroformerCheckpointLease, _LeaseState]:
    if type(value) is not _PrivateMelroformerCheckpointLease:
        raise ValueError("private Kim checkpoint lease must be exactly issued")
    with _REGISTRY_LOCK:
        state = _KNOWN.get(value)
    if type(state) is not _LeaseState:
        raise ValueError("private Kim checkpoint lease is not registered")
    return value, state


def _require_owner(state: _LeaseState) -> None:
    if state.owner_pid != os.getpid():
        raise RuntimeError("private Kim checkpoint lease owner changed")


def _finalize_descriptor(descriptor: int, identity: tuple[int, int]) -> None:
    try:
        current = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) == identity:
            os.close(descriptor)
    except OSError:
        pass


def _close_if_open(descriptor: int | None) -> None:
    if descriptor is not None:
        os.close(descriptor)
