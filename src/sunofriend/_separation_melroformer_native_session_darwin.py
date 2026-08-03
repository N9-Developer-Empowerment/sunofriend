"""Private measured Darwin session and single-use admission for native Kim.

The session wraps one freshly built and verified native-launcher session while
binding the separate fixed Kim worker entry point and ``sandbox-exec`` method.
Neither the session observation nor the serialized worker request is execution
authority. A parent-issued admission binds one exact live session and request
nonce and may be consumed only once by the later private executor.

The guarded start boundary validates the request/staging/descriptor geometry,
consumes one exact admission and may invoke the fixed native spawn method. It
does not open or read the checkpoint, read audio, supervise a worker or grant
product authority. No public, CLI, TUI, Simple, Studio or source-graph route
imports it.
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

from . import _separation_native_session_darwin as _base
from ._separation_checkpoint_canonical import (
    canonical_sha256 as _canonical_sha256,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_native_transport import (
    _encode_private_melroformer_native_request,
    _validate_private_melroformer_native_request,
)
from ._separation_melroformer_native_runtime_darwin import (
    _measure_private_runtime_launcher,
    _path_free_runtime_binding,
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
    runtime_launcher_path: Path
    runtime_environment_root: Path
    base_runtime_root: Path
    runtime_measurement: Mapping[str, Any]
    worker_path: Path
    worker_measurement: Mapping[str, Any]
    sandbox_provider_path: Path
    sandbox_provider_measurement: Mapping[str, Any]
    observation_document: Mapping[str, Any]
    observation_object: _VerifiedPrivateMelroformerNativeSessionObservation
    run_status: str
    native_owner: Any | None


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
    runtime_launcher_path: str | Path,
    cache_root: str | Path | None = None,
) -> tuple[
    _VerifiedPrivateMelroformerNativeSession,
    _VerifiedPrivateMelroformerNativeSessionObservation,
]:
    """Build and bind one fresh native session without starting a process."""

    runtime_before = _measure_private_runtime_launcher(runtime_launcher_path)
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
        native_module = base_state.module
    runtime_after = _measure_private_runtime_launcher(runtime_launcher_path)
    worker_after = _measure_worker(worker_path)
    provider_after = _measure_provider(provider_path)
    if worker_after != worker_before:
        raise RuntimeError("fixed private Kim worker changed during session open")
    if provider_after != provider_before:
        raise RuntimeError("sandbox provider changed during session open")
    if runtime_after != runtime_before:
        raise RuntimeError("private Kim runtime changed during session open")
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
            "private_ai_runtime": _path_free_runtime_binding(runtime_after),
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
            "explicit_ai_runtime_bound": True,
            "virtual_environment_bound": True,
            "fixed_worker_bound": True,
            "sandbox_provider_bound": True,
            "guarded_descriptor_start_adapter_available": True,
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
            "measured_runtime_worker_and_sandbox_provider_paths_retain_exec_toctou",
            "base_runtime_files_outside_the_virtual_environment_are_observed_again_after_execution_but_not_frozen",
            "checkpoint_lease_source_companions_and_post_run_staging_verification_are_not_yet_bound",
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
        runtime_launcher_path=Path(runtime_after["runtime_launcher_path"]),
        runtime_environment_root=Path(runtime_after["runtime_environment_root"]),
        base_runtime_root=Path(runtime_after["base_runtime_root"]),
        runtime_measurement=_freeze(runtime_after),
        worker_path=worker_path,
        worker_measurement=_freeze(worker_after),
        sandbox_provider_path=provider_path,
        sandbox_provider_measurement=_freeze(provider_after),
        observation_document=document,
        observation_object=observation,
        run_status="ready",
        native_owner=None,
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


def _start_verified_private_melroformer_native_worker(
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    *,
    session_observation: _VerifiedPrivateMelroformerNativeSessionObservation,
    trusted_admission: _PrivateMelroformerNativeAdmission,
    request: Mapping[str, Any],
    staging_directory: str | Path,
    request_read_descriptor: int,
    result_write_descriptor: int,
    checkpoint_read_descriptor: int,
    ready_write_descriptor: int,
    release_read_descriptor: int,
) -> Any:
    """Start one fixed worker after consuming one exact live admission.

    Invocation transfers the four child-only request/result/ready/release
    descriptors to this boundary. They are closed in the parent on every
    outcome. The checkpoint descriptor remains owned by its separate live
    lease and is never closed or read here.

    The returned value is the exact native opaque owner. It carries no public
    PID/PGID attribute and is also retained in the private session registry so
    later observer and terminal phases can require object identity.
    """

    transferred_descriptors = (
        request_read_descriptor,
        result_write_descriptor,
        ready_write_descriptor,
        release_read_descriptor,
    )
    native_owner: Any | None = None
    consumed = False
    primary_error: BaseException | None = None
    cleanup_failures: list[tuple[str, BaseException]] = []
    start_state: str | None = None
    state: _SessionState | None = None
    try:
        checked_request = _validate_private_melroformer_native_request(request)
        _session, state = _known_session(trusted_session)
        descriptor_measurement = _validate_private_native_start_descriptors(
            request=checked_request,
            request_read_descriptor=request_read_descriptor,
            result_write_descriptor=result_write_descriptor,
            checkpoint_read_descriptor=checkpoint_read_descriptor,
            ready_write_descriptor=ready_write_descriptor,
            release_read_descriptor=release_read_descriptor,
        )
        staging_before = _measure_private_staging_directory(
            staging_directory,
            request=checked_request,
            require_empty=True,
        )
        _validate_verified_private_melroformer_native_session_observation(
            trusted_session,
            session_observation,
        )
        with state.lock:
            _require_owner(state)
            if state.run_status != "admission_issued":
                raise RuntimeError(
                    "private Kim native session lacks an issued admission"
                )
            _remeasure_state(state)
            if _measure_private_staging_directory(
                staging_directory,
                request=checked_request,
                require_empty=True,
            ) != staging_before:
                raise RuntimeError(
                    "private Kim staging changed before native start"
                )
            _recheck_private_native_start_descriptors(
                descriptor_measurement,
                request=checked_request,
                request_read_descriptor=request_read_descriptor,
                result_write_descriptor=result_write_descriptor,
                checkpoint_read_descriptor=checkpoint_read_descriptor,
                ready_write_descriptor=ready_write_descriptor,
                release_read_descriptor=release_read_descriptor,
            )
            _consume_private_melroformer_native_admission(
                trusted_admission,
                trusted_session=trusted_session,
                request=checked_request,
            )
            consumed = True
            state.run_status = "starting"
            native_owner = state.spawn_method(
                os.fsencode(state.sandbox_provider_path),
                os.fsencode(state.runtime_launcher_path),
                os.fsencode(state.worker_path),
                os.fsencode(Path(staging_before["resolved_path"])),
                request_read_descriptor,
                result_write_descriptor,
                checkpoint_read_descriptor,
                ready_write_descriptor,
                release_read_descriptor,
            )
            start_state, _no_start_stage, _native_status = (
                _base._validate_native_start_outcome(
                    native_owner,
                    expected_owner_type=state.owner_type,
                )
            )
            if start_state != "started_owned":
                state.run_status = "consumed_no_start"
                raise RuntimeError("private Kim native worker was not started")
            if _staging_identity(
                _measure_private_staging_directory(
                    staging_directory,
                    request=checked_request,
                    require_empty=False,
                )
            ) != _staging_identity(staging_before):
                state.run_status = "consumed_start_unproven"
                raise RuntimeError("private Kim staging changed during start")
            state.run_status = "started_pending_parent_cleanup"
    except BaseException as exc:
        primary_error = exc
        if state is not None:
            with state.lock:
                if consumed and state.run_status not in {
                    "consumed_no_start",
                    "consumed_start_unproven",
                }:
                    state.run_status = "consumed_start_unproven"

    cleanup_failures.extend(
        _close_transferred_private_native_descriptors(
            transferred_descriptors,
            protected_descriptor=checkpoint_read_descriptor,
        )
    )
    try:
        _finish_private_melroformer_native_admission(
            trusted_admission,
            expected_status="consumed" if consumed else "issued",
        )
    except BaseException as exc:
        cleanup_failures.append(("native_admission_finish", exc))

    if primary_error is None and cleanup_failures:
        primary_error = RuntimeError(
            "private Kim native parent descriptor cleanup was incomplete"
        )
        if state is None:
            raise primary_error
        with state.lock:
            state.run_status = "consumed_start_unproven"
    if primary_error is not None:
        # Dropping an unretained exact owner invokes the native emergency
        # containment backstop. It is not accepted as terminal evidence.
        native_owner = None
        if cleanup_failures:
            detail = ", ".join(label for label, _error in cleanup_failures)
            raise RuntimeError(
                f"private Kim native start failed; cleanup: {detail}"
            ) from primary_error
        raise primary_error
    if start_state != "started_owned" or native_owner is None:
        if state is None:
            raise RuntimeError("private Kim native start session is unproven")
        with state.lock:
            state.run_status = "consumed_start_unproven"
        raise RuntimeError("private Kim native start outcome is unproven")
    if state is None:
        native_owner = None
        raise RuntimeError("private Kim native start session is unproven")
    with state.lock:
        _require_owner(state)
        if state.run_status != "started_pending_parent_cleanup":
            native_owner = None
            state.run_status = "consumed_start_unproven"
            raise RuntimeError("private Kim native start state changed")
        state.native_owner = native_owner
        state.run_status = "running"
    return native_owner


def _known_started_private_melroformer_native_owner(
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    value: Any,
) -> Any:
    """Require the exact native owner retained by one running session."""

    _session, state = _known_session(trusted_session)
    with state.lock:
        _require_owner(state)
        if (
            state.run_status != "running"
            or type(value) is not state.owner_type
            or value is not state.native_owner
        ):
            raise ValueError("private Kim native owner is not the active owner")
        return value


def _finish_started_private_melroformer_native_session(
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    native_owner: Any,
    *,
    terminal_observation: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Record one normal exact-reap terminal transition exactly once.

    The process supervisor remains a separate fixed parent component. This
    transition accepts only its path-free normal-exit observation, requires the
    exact owner retained by the running session and remeasures every session
    binding before releasing that owner from the registry.
    """

    terminal = _validate_private_native_terminal_observation(
        terminal_observation
    )
    _session, state = _known_session(trusted_session)
    with state.lock:
        _require_owner(state)
        if (
            state.run_status != "running"
            or type(native_owner) is not state.owner_type
            or native_owner is not state.native_owner
        ):
            raise ValueError("private Kim native owner is not the active owner")
        if (
            getattr(native_owner, "leader_reaped", None) is not True
            or getattr(native_owner, "ownership_released", None) is not True
            or getattr(native_owner, "ownership_lost", None) is not False
        ):
            raise ValueError("private Kim native owner is not exactly reaped")
        _remeasure_state(state)
        payload = {
            "schema": "sunofriend.private-melroformer-native-session-terminal.v1",
            "policy_id": "private-kim-native-session-terminal-transition-v1",
            "status": "normal_zero_exit_exact_reap_recorded",
            "session_observation_sha256": state.observation_document[
                "observation_sha256"
            ],
            "terminal": _plain(terminal),
            "session_bindings_remeasured_after_reap": True,
            "active_owner_released_from_session": True,
            "paths_retained": False,
            "permissions": {
                "automatic_selection_permitted": False,
                "product_route_permitted": False,
                "publication_permitted": False,
            },
        }
        receipt = _freeze(
            {
                **payload,
                "evidence_sha256": _canonical_sha256(payload),
            }
        )
        state.native_owner = None
        state.run_status = "terminal"
        return receipt


def _finish_failed_started_private_melroformer_native_session(
    trusted_session: _VerifiedPrivateMelroformerNativeSession,
    native_owner: Any,
    *,
    terminal_observation: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Release one failed but completely reaped exact owner from its session.

    Unlike the successful transition above, this record accepts no quality or
    execution-success claim.  It exists only so a coordinator failure cannot
    leave a fully reaped owner registered as running.  A missing owner, lost
    ownership, incomplete group drain or unproved reap still fails closed.
    """

    terminal = _validate_private_native_failed_terminal_observation(
        terminal_observation
    )
    _session, state = _known_session(trusted_session)
    with state.lock:
        _require_owner(state)
        if (
            state.run_status != "running"
            or type(native_owner) is not state.owner_type
            or native_owner is not state.native_owner
        ):
            raise ValueError("private Kim native owner is not the active owner")
        if (
            getattr(native_owner, "leader_reaped", None) is not True
            or getattr(native_owner, "group_empty", None) is not True
            or getattr(native_owner, "ownership_released", None) is not True
            or getattr(native_owner, "ownership_lost", None) is not False
        ):
            raise ValueError("private Kim failed native owner is not exactly reaped")
        _remeasure_state(state)
        payload = {
            "schema": "sunofriend.private-melroformer-native-session-terminal.v1",
            "policy_id": "private-kim-native-session-terminal-transition-v1",
            "status": "failed_run_exact_reap_recorded",
            "session_observation_sha256": state.observation_document[
                "observation_sha256"
            ],
            "terminal": _plain(terminal),
            "session_bindings_remeasured_after_reap": True,
            "active_owner_released_from_session": True,
            "execution_success_claimed": False,
            "paths_retained": False,
            "permissions": {
                "automatic_selection_permitted": False,
                "product_route_permitted": False,
                "publication_permitted": False,
            },
        }
        receipt = _freeze(
            {
                **payload,
                "evidence_sha256": _canonical_sha256(payload),
            }
        )
        state.native_owner = None
        state.run_status = "terminal"
        return receipt


def _validate_private_native_failed_terminal_observation(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    terminal = _plain(value)
    if not isinstance(terminal, dict) or set(terminal) != {
        "wait",
        "timed_out",
        "term_sent",
        "kill_sent",
        "leader_exit_observed",
        "leader_reaped",
        "group_empty",
        "ownership_released",
        "ownership_lost",
    }:
        raise ValueError("private Kim failed terminal observation fields differ")
    wait = terminal["wait"]
    if (
        not isinstance(wait, dict)
        or set(wait) != {"kind", "exit_code", "signal", "core_dumped"}
        or wait["kind"] not in {"exited", "signaled"}
        or type(wait["core_dumped"]) is not bool
    ):
        raise ValueError("private Kim failed terminal wait evidence differs")
    if wait["kind"] == "exited":
        if (
            type(wait["exit_code"]) is not int
            or wait["exit_code"] == 0
            or wait["signal"] is not None
        ):
            raise ValueError("private Kim failed exit evidence differs")
    elif (
        wait["exit_code"] is not None
        or type(wait["signal"]) is not int
        or wait["signal"] <= 0
    ):
        raise ValueError("private Kim failed signal evidence differs")
    if any(
        terminal[key] is not True
        for key in (
            "leader_exit_observed",
            "leader_reaped",
            "group_empty",
            "ownership_released",
        )
    ) or terminal["ownership_lost"] is not False:
        raise ValueError("private Kim failed terminal ownership is incomplete")
    for key in ("timed_out", "term_sent", "kill_sent"):
        if type(terminal[key]) is not bool:
            raise ValueError("private Kim failed terminal flags differ")
    return _freeze(terminal)


def _validate_private_native_terminal_observation(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    terminal = _plain(value)
    if not isinstance(terminal, dict) or set(terminal) != {
        "wait",
        "timed_out",
        "term_sent",
        "kill_sent",
        "leader_exit_observed",
        "leader_reaped",
        "group_empty",
        "ownership_released",
        "ownership_lost",
    }:
        raise ValueError("private Kim terminal observation fields differ")
    if terminal["wait"] != {
        "kind": "exited",
        "exit_code": 0,
        "signal": None,
        "core_dumped": False,
    }:
        raise ValueError("private Kim native worker did not exit normally")
    if any(
        terminal[key] is not True
        for key in (
            "leader_exit_observed",
            "leader_reaped",
            "group_empty",
            "ownership_released",
        )
    ) or any(
        terminal[key] is not False
        for key in (
            "timed_out",
            "term_sent",
            "kill_sent",
            "ownership_lost",
        )
    ):
        raise ValueError("private Kim terminal ownership is incomplete")
    return _freeze(terminal)


def _validate_private_native_start_descriptors(
    *,
    request: Mapping[str, Any],
    request_read_descriptor: int,
    result_write_descriptor: int,
    checkpoint_read_descriptor: int,
    ready_write_descriptor: int,
    release_read_descriptor: int,
) -> Mapping[str, Any]:
    descriptors = (
        request_read_descriptor,
        result_write_descriptor,
        checkpoint_read_descriptor,
        ready_write_descriptor,
        release_read_descriptor,
    )
    if (
        any(type(descriptor) is not int or descriptor < 3 for descriptor in descriptors)
        or len(set(descriptors)) != 5
    ):
        raise ValueError("private Kim native descriptors are invalid")
    measurements = {
        "request": _descriptor_measurement(request_read_descriptor),
        "result": _descriptor_measurement(result_write_descriptor),
        "checkpoint": _descriptor_measurement(checkpoint_read_descriptor),
        "ready": _descriptor_measurement(ready_write_descriptor),
        "release": _descriptor_measurement(release_read_descriptor),
    }
    if any(item["inheritable"] for item in measurements.values()):
        raise ValueError("private Kim native descriptor is inheritable")
    if (
        measurements["request"]["access_mode"] != os.O_RDONLY
        or measurements["request"]["file_type"] != "regular"
        or measurements["result"]["access_mode"] != os.O_WRONLY
        or measurements["result"]["file_type"] != "regular"
        or measurements["result"]["size"] != 0
        or measurements["result"]["append"] is True
        or measurements["checkpoint"]["access_mode"] != os.O_RDONLY
        or measurements["checkpoint"]["file_type"] != "regular"
        or measurements["checkpoint"]["size"]
        != request["identities"]["checkpoint_bytes"]
        or measurements["ready"]["access_mode"] != os.O_WRONLY
        or measurements["ready"]["file_type"] != "fifo"
        or measurements["release"]["access_mode"] != os.O_RDONLY
        or measurements["release"]["file_type"] != "fifo"
    ):
        raise ValueError("private Kim native descriptor geometry differs")
    frame = _encode_private_melroformer_native_request(request)
    if measurements["request"]["size"] != len(frame):
        raise ValueError("private Kim native request descriptor size differs")
    if _pread_exact(request_read_descriptor, len(frame)) != frame:
        raise ValueError("private Kim native request descriptor content differs")
    if _descriptor_measurement(request_read_descriptor) != measurements["request"]:
        raise ValueError("private Kim native request descriptor changed")
    return _freeze(measurements)


def _recheck_private_native_start_descriptors(
    expected: Mapping[str, Any],
    **descriptors: Any,
) -> None:
    request = descriptors.pop("request")
    measured = _validate_private_native_start_descriptors(
        request=request,
        **descriptors,
    )
    if measured != expected:
        raise RuntimeError("private Kim native descriptors changed before start")


def _descriptor_measurement(descriptor: int) -> Mapping[str, Any]:
    try:
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        value = os.fstat(descriptor)
        inheritable = os.get_inheritable(descriptor)
    except OSError as exc:
        raise ValueError("private Kim native descriptor is unavailable") from exc
    if stat.S_ISREG(value.st_mode):
        file_type = "regular"
    elif stat.S_ISFIFO(value.st_mode):
        file_type = "fifo"
    else:
        file_type = "other"
    return _freeze(
        {
            "access_mode": flags & os.O_ACCMODE,
            "append": bool(flags & os.O_APPEND),
            "inheritable": inheritable,
            "file_type": file_type,
            "device": value.st_dev,
            "inode": value.st_ino,
            "mode": stat.S_IMODE(value.st_mode),
            "size": value.st_size,
            "modified_ns": value.st_mtime_ns,
            "changed_ns": value.st_ctime_ns,
        }
    )


def _measure_private_staging_directory(
    value: str | Path,
    *,
    request: Mapping[str, Any],
    require_empty: bool,
) -> Mapping[str, Any]:
    requested = Path(request["paths"]["staging_directory"])
    supplied = Path(value)
    if supplied != requested or not supplied.is_absolute():
        raise ValueError("private Kim staging path differs from request")
    try:
        link_state = supplied.lstat()
        resolved = supplied.resolve(strict=True)
        resolved_state = resolved.stat()
    except OSError as exc:
        raise ValueError("private Kim staging directory is unavailable") from exc
    if (
        not stat.S_ISDIR(link_state.st_mode)
        or resolved != supplied
        or (link_state.st_dev, link_state.st_ino)
        != (resolved_state.st_dev, resolved_state.st_ino)
        or resolved_state.st_uid != os.getuid()
        or stat.S_IMODE(resolved_state.st_mode) & 0o077
    ):
        raise ValueError("private Kim staging directory is not owner-only")
    if require_empty:
        try:
            with os.scandir(resolved) as entries:
                if next(entries, None) is not None:
                    raise ValueError("private Kim staging directory is not fresh")
        except OSError as exc:
            raise ValueError("private Kim staging directory is unavailable") from exc
    return _freeze(
        {
            "resolved_path": str(resolved),
            "device": resolved_state.st_dev,
            "inode": resolved_state.st_ino,
            "uid": resolved_state.st_uid,
            "mode": stat.S_IMODE(resolved_state.st_mode),
        }
    )


def _staging_identity(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(value[key] for key in ("resolved_path", "device", "inode", "uid", "mode"))


def _pread_exact(descriptor: int, byte_count: int) -> bytes:
    received = bytearray()
    offset = 0
    while len(received) < byte_count:
        block = os.pread(descriptor, byte_count - len(received), offset)
        if not block:
            break
        received.extend(block)
        offset += len(block)
    return bytes(received)


def _close_transferred_private_native_descriptors(
    descriptors: tuple[int, ...],
    *,
    protected_descriptor: int,
) -> tuple[tuple[str, BaseException], ...]:
    failures: list[tuple[str, BaseException]] = []
    seen: set[int] = set()
    for descriptor in descriptors:
        if (
            type(descriptor) is not int
            or descriptor < 3
            or descriptor == protected_descriptor
            or descriptor in seen
        ):
            continue
        seen.add(descriptor)
        try:
            os.close(descriptor)
        except OSError as exc:
            failures.append(("child_transport_descriptor_close", exc))
    return tuple(failures)


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
    runtime = _measure_private_runtime_launcher(state.runtime_launcher_path)
    _base_session, base_state = _base._known_state(state.base_session)
    if (
        worker != _plain(state.worker_measurement)
        or provider != _plain(state.sandbox_provider_measurement)
        or runtime != _plain(state.runtime_measurement)
        or base_state.module is not state.native_module
        or getattr(state.native_module, _SPAWN_METHOD_NAME, None)
        is not state.spawn_method
        or base_state.owner_type is not state.owner_type
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
