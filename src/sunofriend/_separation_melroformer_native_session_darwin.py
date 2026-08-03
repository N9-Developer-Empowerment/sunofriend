"""Private measured Darwin session and single-use admission for native Kim.

The session wraps one freshly built and verified native-launcher session while
binding the separate fixed Kim worker entry point and ``sandbox-exec`` method.
Neither the session observation nor the serialized worker request is execution
authority. A parent-issued admission binds one exact live session and request
nonce and may be consumed only once by the later private executor.

This module does not open a checkpoint, read audio or invoke the native spawn
method. No public, CLI, TUI, Simple, Studio or source-graph route imports it.
"""

from __future__ import annotations

import os
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import _separation_native_session_darwin as _base
from ._separation_checkpoint_canonical import (
    canonical_sha256 as _canonical_sha256,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_native_transport import (
    _validate_private_melroformer_native_request,
)


__all__: tuple[str, ...] = ()

_SESSION_SCHEMA = "sunofriend.private-melroformer-native-session.v1"
_SESSION_POLICY_ID = "private-kim-native-session-darwin-v1"
_SPAWN_METHOD_NAME = "_spawn_bound_private_melroformer_worker"
_WORKER_RELATIVE_PATH = Path("scripts/private-melroformer-native-worker.py")
_SANDBOX_PROVIDER_PATH = Path("/usr/bin/sandbox-exec")
_MAXIMUM_WORKER_BYTES = 1_048_576
_MAXIMUM_PROVIDER_BYTES = 8_388_608
_MAXIMUM_USED_NONCES = 1_024
_REGISTRY_LOCK = threading.RLock()
_USED_NONCES: set[str] = set()


class _VerifiedPrivateMelroformerNativeSession:
    """Opaque parent-issued identity for one measured real-worker session."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("private Kim native sessions are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("private Kim native sessions cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("private Kim native sessions cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("private Kim native sessions cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("private Kim native sessions cannot be serialized")


@dataclass(frozen=True, init=False)
class _VerifiedPrivateMelroformerNativeSessionObservation(Mapping[str, Any]):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


class _PrivateMelroformerNativeAdmission:
    """Opaque single-use start permission bound to one session and request."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("private Kim native admissions are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("private Kim native admissions cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("private Kim native admissions cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("private Kim native admissions cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("private Kim native admissions cannot be serialized")


@dataclass
class _SessionState:
    lock: Any
    owner_pid: int
    base_session: Any
    base_observation: Any
    native_module: Any
    spawn_method: Any
    owner_type: type[Any]
    runtime_path: Path
    worker_path: Path
    worker_measurement: Mapping[str, Any]
    sandbox_provider_path: Path
    sandbox_provider_measurement: Mapping[str, Any]
    observation_document: Mapping[str, Any]
    observation_object: _VerifiedPrivateMelroformerNativeSessionObservation
    run_status: str


@dataclass
class _AdmissionState:
    owner_pid: int
    session: _VerifiedPrivateMelroformerNativeSession
    request_sha256: str
    run_nonce: str
    status: str


_SESSIONS: weakref.WeakKeyDictionary[
    _VerifiedPrivateMelroformerNativeSession, _SessionState
] = weakref.WeakKeyDictionary()
_ADMISSIONS: weakref.WeakKeyDictionary[
    _PrivateMelroformerNativeAdmission, _AdmissionState
] = weakref.WeakKeyDictionary()


def _open_verified_private_melroformer_native_session(
    *,
    cache_root: str | Path | None = None,
) -> tuple[
    _VerifiedPrivateMelroformerNativeSession,
    _VerifiedPrivateMelroformerNativeSessionObservation,
]:
    """Build and bind one fresh native session without starting a process."""

    base_session, base_observation = _base._open_verified_native_launcher_session(
        cache_root=cache_root
    )
    _base_session, base_state = _base._known_state(base_session)
    worker_path = _fixed_worker_path()
    provider_path = _SANDBOX_PROVIDER_PATH.resolve(strict=True)
    worker_before = _measure_worker(worker_path)
    provider_before = _measure_provider(provider_path)
    with base_state.lock:
        _base._require_owner(base_state)
        spawn_method = getattr(base_state.module, _SPAWN_METHOD_NAME, None)
        if (
            type(spawn_method).__name__ != "builtin_function_or_method"
            or getattr(spawn_method, "__module__", None)
            != base_state.module.__name__
            or getattr(spawn_method, "__self__", None) is not base_state.module
        ):
            raise RuntimeError("private Kim native spawn binding is invalid")
        owner_type = base_state.owner_type
        runtime_path = base_state.runtime_path
        native_module = base_state.module
    worker_after = _measure_worker(worker_path)
    provider_after = _measure_provider(provider_path)
    if worker_after != worker_before:
        raise RuntimeError("fixed private Kim worker changed during session open")
    if provider_after != provider_before:
        raise RuntimeError("sandbox provider changed during session open")
    base_document = _plain(base_observation)
    payload = {
        "schema": _SESSION_SCHEMA,
        "policy_id": _SESSION_POLICY_ID,
        "status": "verified_not_run",
        "evidence_scope": "private_native_import_and_binding_only",
        "execution_authority": False,
        "bindings": {
            "base_native_session_observation_sha256": base_document[
                "observation_sha256"
            ],
            "native_launcher": base_document["bindings"]["native_launcher"],
            "runtime_executable": base_document["bindings"][
                "runtime_executable"
            ],
            "fixed_kim_worker": _path_free_binding(worker_after),
            "sandbox_provider": _path_free_binding(provider_after),
            "native_build_receipt_sha256": base_document["bindings"][
                "native_build_receipt_sha256"
            ],
        },
        "capabilities": {
            "fresh_private_native_build_verified": True,
            "fixed_kim_spawn_method_bound": True,
            "opaque_owner_type_bound": True,
            "fixed_worker_bound": True,
            "sandbox_provider_bound": True,
            "worker_started": False,
            "real_separation_executed": False,
        },
        "effects": {
            "native_build_files_written": True,
            "native_artifact_imported": True,
            "process_started": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_read": False,
            "network_used": False,
            "publication_permitted": False,
        },
        "limitations": [
            "opaque_session_and_observation_are_not_execution_authority",
            "single_use_admission_is_still_required_immediately_before_spawn",
            "runtime_worker_and_sandbox_provider_paths_retain_exec_toctou",
            "checkpoint_source_companions_and_staging_are_not_yet_bound",
            "no_live_observer_or_terminal_evidence_exists",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = _freeze(
        {
            **payload,
            "observation_sha256": _canonical_sha256(payload),
        }
    )
    session = object.__new__(_VerifiedPrivateMelroformerNativeSession)
    observation = _session_observation(document)
    state = _SessionState(
        lock=threading.RLock(),
        owner_pid=os.getpid(),
        base_session=base_session,
        base_observation=base_observation,
        native_module=native_module,
        spawn_method=spawn_method,
        owner_type=owner_type,
        runtime_path=runtime_path,
        worker_path=worker_path,
        worker_measurement=_freeze(worker_after),
        sandbox_provider_path=provider_path,
        sandbox_provider_measurement=_freeze(provider_after),
        observation_document=document,
        observation_object=observation,
        run_status="ready",
    )
    with _REGISTRY_LOCK:
        _SESSIONS[session] = state
    return session, observation


def _validate_verified_private_melroformer_native_session_observation(
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    value: Any,
) -> _VerifiedPrivateMelroformerNativeSessionObservation:
    """Require the exact issued observation and remeasure every binding."""

    _session, state = _known_session(trusted_session)
    with state.lock:
        _require_owner(state)
        if (
            type(value)
            is not _VerifiedPrivateMelroformerNativeSessionObservation
            or value is not state.observation_object
            or getattr(value, "_document", None) is not state.observation_document
        ):
            raise ValueError(
                "private Kim session observation must be the exact issued object"
            )
        _remeasure_state(state)
        return value


def _issue_private_melroformer_native_admission(
    *,
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    session_observation: _VerifiedPrivateMelroformerNativeSessionObservation,
    request: Mapping[str, Any],
) -> _PrivateMelroformerNativeAdmission:
    """Mint one request-bound admission after a fresh complete remeasurement."""

    checked_request = _validate_private_melroformer_native_request(request)
    _validate_verified_private_melroformer_native_session_observation(
        trusted_session,
        session_observation,
    )
    _session, state = _known_session(trusted_session)
    nonce = checked_request["run_nonce"]
    with state.lock, _REGISTRY_LOCK:
        _require_owner(state)
        if (
            checked_request["identities"]["worker_source_sha256"]
            != state.worker_measurement["sha256"]
            or Path(checked_request["paths"]["repository_root"])
            != state.worker_path.parents[1]
        ):
            raise ValueError("private Kim request does not bind the fixed worker")
        if state.run_status != "ready":
            raise RuntimeError("private Kim native session is single-use")
        if nonce in _USED_NONCES:
            raise ValueError("private Kim native request nonce was already used")
        if len(_USED_NONCES) >= _MAXIMUM_USED_NONCES:
            raise RuntimeError("private Kim native nonce registry is full")
        admission = object.__new__(_PrivateMelroformerNativeAdmission)
        _ADMISSIONS[admission] = _AdmissionState(
            owner_pid=os.getpid(),
            session=trusted_session,
            request_sha256=checked_request["request_sha256"],
            run_nonce=nonce,
            status="issued",
        )
        _USED_NONCES.add(nonce)
        state.run_status = "admission_issued"
    return admission


def _consume_private_melroformer_native_admission(
    value: Any,
    *,
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    request: Mapping[str, Any],
) -> None:
    """Consume the exact admission immediately before the future native call."""

    checked_request = _validate_private_melroformer_native_request(request)
    if type(value) is not _PrivateMelroformerNativeAdmission:
        raise ValueError("private Kim native start requires an exact admission")
    _session, session_state = _known_session(trusted_session)
    with session_state.lock, _REGISTRY_LOCK:
        _require_owner(session_state)
        if (
            checked_request["identities"]["worker_source_sha256"]
            != session_state.worker_measurement["sha256"]
            or Path(checked_request["paths"]["repository_root"])
            != session_state.worker_path.parents[1]
        ):
            raise ValueError("private Kim request does not bind the fixed worker")
        admission_state = _ADMISSIONS.get(value)
        if (
            type(admission_state) is not _AdmissionState
            or admission_state.owner_pid != os.getpid()
            or admission_state.session is not trusted_session
            or admission_state.request_sha256 != checked_request["request_sha256"]
            or admission_state.run_nonce != checked_request["run_nonce"]
            or admission_state.status != "issued"
            or session_state.run_status != "admission_issued"
        ):
            raise ValueError("private Kim native admission is invalid")
        admission_state.status = "consumed"
        session_state.run_status = "admitted"


def _finish_private_melroformer_native_admission(
    value: _PrivateMelroformerNativeAdmission,
    *,
    expected_status: str,
) -> None:
    """Erase one admission while requiring its expected single-use state."""

    if expected_status not in {"issued", "consumed"}:
        raise ValueError("private Kim admission terminal expectation differs")
    with _REGISTRY_LOCK:
        state = _ADMISSIONS.get(value)
        if type(state) is not _AdmissionState:
            raise RuntimeError("private Kim native admission is unavailable")
        mismatch = state.status != expected_status
        state.status = "terminal"
        del _ADMISSIONS[value]
    _session, session_state = _known_session(state.session)
    with session_state.lock:
        _require_owner(session_state)
        if expected_status == "issued" and not mismatch:
            if session_state.run_status != "admission_issued":
                raise RuntimeError("private Kim native session state differs")
            session_state.run_status = "ready"
    if mismatch:
        raise RuntimeError("private Kim native admission state differs")


def _known_session(
    value: Any,
) -> tuple[_VerifiedPrivateMelroformerNativeSession, _SessionState]:
    if type(value) is not _VerifiedPrivateMelroformerNativeSession:
        raise ValueError("private Kim native session must be exactly issued")
    with _REGISTRY_LOCK:
        state = _SESSIONS.get(value)
    if type(state) is not _SessionState:
        raise ValueError("private Kim native session is not registered")
    return value, state


def _remeasure_state(state: _SessionState) -> None:
    _base._validate_verified_native_launcher_session_observation(
        state.base_session,
        state.base_observation,
    )
    worker = _measure_worker(state.worker_path)
    provider = _measure_provider(state.sandbox_provider_path)
    _base_session, base_state = _base._known_state(state.base_session)
    if (
        worker != _plain(state.worker_measurement)
        or provider != _plain(state.sandbox_provider_measurement)
        or base_state.module is not state.native_module
        or getattr(state.native_module, _SPAWN_METHOD_NAME, None)
        is not state.spawn_method
        or base_state.owner_type is not state.owner_type
        or base_state.runtime_path != state.runtime_path
    ):
        raise RuntimeError("private Kim native session binding changed")


def _measure_worker(path: Path) -> Mapping[str, Any]:
    return _base._measure_bound_file(
        path,
        label="fixed private Kim worker",
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
        executable=False,
        require_not_group_or_other_writable=True,
    )


def _measure_provider(path: Path) -> Mapping[str, Any]:
    return _base._measure_bound_file(
        path,
        label="fixed macOS sandbox provider",
        maximum_bytes=_MAXIMUM_PROVIDER_BYTES,
        executable=True,
        require_not_group_or_other_writable=True,
    )


def _fixed_worker_path() -> Path:
    repository = Path(__file__).resolve(strict=True).parents[2]
    worker = (repository / _WORKER_RELATIVE_PATH).resolve(strict=True)
    if worker.parent != (repository / "scripts").resolve(strict=True):
        raise RuntimeError("fixed private Kim worker escaped the repository")
    return worker


def _path_free_binding(value: Mapping[str, Any]) -> Mapping[str, Any]:
    measured = _plain(value)
    return {
        "sha256": measured["sha256"],
        "bytes": measured["bytes"],
        "stat_identity_sha256": measured["stat_identity_sha256"],
    }


def _require_owner(state: _SessionState) -> None:
    if state.owner_pid != os.getpid():
        raise RuntimeError("private Kim native session belongs to another process")


def _session_observation(
    document: Mapping[str, Any],
) -> _VerifiedPrivateMelroformerNativeSessionObservation:
    value = object.__new__(_VerifiedPrivateMelroformerNativeSessionObservation)
    object.__setattr__(value, "_document", document)
    return value
