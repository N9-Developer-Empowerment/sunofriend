"""Private verified native-launcher session for deterministic fake execution.

This module is the import boundary between the provenance-only Darwin builder
and a later live fake executor.  It creates one fresh owner-only build,
remeasures the extension immediately before and after import, binds that exact
artifact to the current Python executable and the pinned stdlib-only fake
worker, and retains the imported module only in module-private registry state.

The opaque session is not execution authority.  A separate private executor
may consume it once through the exact fixed spawn method; there is no public,
CLI or TUI route.  The private registry is part of the trusted-parent boundary,
not a defence against hostile Python in that process.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import fcntl
import os
import signal
import stat
import sys
import threading
import time
import weakref
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from . import _separation_native_build_darwin as _native_build
from ._separation_checkpoint_canonical import (
    canonical_sha256 as _canonical_sha256,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_fake_execution_records import (
    _EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    _EXPECTED_FAKE_WORKER_SOURCE_SHA256,
    _SeparationFakeLaunchPlanV3Record,
    _SeparationFakeWorkerResultV2Record,
)
from ._separation_fake_execution_protocol import (
    _decode_fake_execution_result_frame,
    _expected_fake_execution_result_frame_bytes,
)


__all__: tuple[str, ...] = ()

_SESSION_SCHEMA = "sunofriend.separation-native-launcher-session.v1"
_SESSION_POLICY_ID = "private-darwin-native-session-v1"
_MODULE_NAME = "_separation_native_spawn_darwin"
_SPAWN_METHOD_NAME = "_spawn_bound_fake_worker"
_WORKER_RESOURCE_NAME = "_separation_fake_worker_darwin.py"
_MAXIMUM_RUNTIME_BYTES = 134_217_728
_MAXIMUM_WORKER_BYTES = 65_536
_READ_CHUNK_BYTES = 1_048_576
_RESULT_HEADER_BYTES = 16
_RUN_TIMEOUT_NS = 5_000_000_000
_TERM_GRACE_NS = 1_000_000_000
_KILL_REAP_NS = 1_000_000_000
_POLL_SECONDS = 0.01

_REGISTRY_LOCK = threading.RLock()


class _VerifiedNativeLauncherSession:
    """Opaque identity for one measured, imported native launcher."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("verified native launcher sessions are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("verified native launcher sessions cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("verified native launcher sessions cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("verified native launcher sessions cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("verified native launcher sessions cannot be serialized")


@dataclass(frozen=True, init=False)
class _VerifiedNativeLauncherSessionObservation(Mapping[str, Any]):
    """Immutable path-free evidence for one exact imported session."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class _VerifiedNativeLauncherExecutionObservation(Mapping[str, Any]):
    """Immutable path-free evidence after one exact native reap."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass
class _SessionState:
    lock: Any
    owner_pid: int
    build: Any
    module: ModuleType
    spawn_method: Any
    artifact_measurement: Mapping[str, Any]
    runtime_path: Path
    runtime_measurement: Mapping[str, Any]
    worker_path: Path
    worker_measurement: Mapping[str, Any]
    observation_document: Mapping[str, Any]
    run_status: str


_KNOWN: weakref.WeakKeyDictionary[
    _VerifiedNativeLauncherSession, _SessionState
] = weakref.WeakKeyDictionary()


def _open_verified_native_launcher_session(
    *,
    cache_root: str | Path | None = None,
) -> tuple[
    _VerifiedNativeLauncherSession,
    _VerifiedNativeLauncherSessionObservation,
]:
    """Build, import and bind one fresh launcher without starting a process."""

    if not _native_build._darwin_host():
        raise RuntimeError("native launcher sessions are supported only on macOS")
    runtime_path = Path(sys.executable).resolve(strict=True)
    worker_path = Path(__file__).with_name(_WORKER_RESOURCE_NAME).resolve(strict=True)
    if worker_path.parent != Path(__file__).resolve(strict=True).parent:
        raise RuntimeError("fixed fake worker escaped the installed package")

    runtime_before = _measure_bound_file(
        runtime_path,
        label="bound Python runtime",
        maximum_bytes=_MAXIMUM_RUNTIME_BYTES,
        executable=True,
        require_not_group_or_other_writable=True,
    )
    worker_before = _measure_bound_file(
        worker_path,
        label="bound fixed fake worker",
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
        executable=False,
        require_not_group_or_other_writable=True,
    )
    if (
        worker_before["sha256"] != _EXPECTED_FAKE_WORKER_SOURCE_SHA256
        or worker_before["bytes"] != _EXPECTED_FAKE_WORKER_SOURCE_BYTES
    ):
        raise RuntimeError("fixed fake worker failed its pinned identity")

    build = _native_build._build_native_launcher(cache_root=cache_root)
    receipt = build.receipt.to_dict()
    artifact_before = _remeasure_build_artifact(build, receipt=receipt)
    module = _load_extension(build.artifact_path)
    artifact_after = _remeasure_build_artifact(build, receipt=receipt)
    if artifact_after != artifact_before:
        raise RuntimeError("native launcher changed across extension import")
    if getattr(module, "_SUNOFRIEND_NATIVE_SOURCE_SHA256", None) != (
        _native_build._EXPECTED_SOURCE_SHA256
    ):
        raise RuntimeError("native launcher source binding is invalid")
    if getattr(
        module,
        "_SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256",
        None,
    ) != _native_build._EXPECTED_BUILD_CONTRACT_SHA256:
        raise RuntimeError("native launcher build-contract binding is invalid")
    spawn_method = getattr(module, _SPAWN_METHOD_NAME, None)
    if (
        type(spawn_method).__name__ != "builtin_function_or_method"
        or getattr(spawn_method, "__module__", None) != _MODULE_NAME
        or getattr(spawn_method, "__self__", None) is not module
    ):
        raise RuntimeError("native launcher spawn method binding is invalid")

    runtime_after = _measure_bound_file(
        runtime_path,
        label="bound Python runtime",
        maximum_bytes=_MAXIMUM_RUNTIME_BYTES,
        executable=True,
        require_not_group_or_other_writable=True,
    )
    worker_after = _measure_bound_file(
        worker_path,
        label="bound fixed fake worker",
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
        executable=False,
        require_not_group_or_other_writable=True,
    )
    if runtime_after != runtime_before:
        raise RuntimeError("bound Python runtime changed during native import")
    if worker_after != worker_before:
        raise RuntimeError("fixed fake worker changed during native import")

    bindings = {
        "native_launcher": _artifact_binding(
            artifact_after,
            path=build.artifact_path,
        ),
        "runtime_executable": _plain(runtime_after),
        "fake_worker": _plain(worker_after),
        "native_build_receipt_sha256": build.receipt_sha256,
        "native_source_sha256": _native_build._EXPECTED_SOURCE_SHA256,
        "native_build_contract_sha256": (
            _native_build._EXPECTED_BUILD_CONTRACT_SHA256
        ),
    }
    payload = {
        "schema": _SESSION_SCHEMA,
        "policy_id": _SESSION_POLICY_ID,
        "status": "verified_not_run",
        "evidence_scope": "private_native_import_only",
        "execution_authority": False,
        "bindings": bindings,
        "capabilities": {
            "fresh_private_build_verified": True,
            "native_artifact_imported": True,
            "spawn_method_bound": True,
            "fake_worker_started": False,
            "real_separation_supported": False,
        },
        "effects": {
            "filesystem_accessed": True,
            "native_build_files_written": True,
            "native_artifact_imported": True,
            "process_started": False,
            "worker_started": False,
            "checkpoint_accessed": False,
            "model_imported": False,
            "audio_read": False,
            "network_used": False,
            "publication_permitted": False,
        },
        "limitations": [
            "opaque_session_is_not_execution_authority",
            "session_open_and_recheck_routes_do_not_start_a_process",
            "guarded_native_call_requires_private_executor_admission",
            "no_public_route_exists_in_this_module",
            "trusted_parent_python_can_inspect_private_process_state",
            "runtime_and_worker_path_toctou_remain_until_live_remeasurement",
            "no_checkpoint_descriptor_admission_result_or_terminal_receipt",
            "no_model_audio_selection_publication_or_user_route",
        ],
    }
    document = _freeze(
        {
            **payload,
            "observation_sha256": _canonical_sha256(payload),
        }
    )
    session = object.__new__(_VerifiedNativeLauncherSession)
    state = _SessionState(
        lock=threading.RLock(),
        owner_pid=os.getpid(),
        build=build,
        module=module,
        spawn_method=spawn_method,
        artifact_measurement=_freeze(artifact_after),
        runtime_path=runtime_path,
        runtime_measurement=_freeze(runtime_after),
        worker_path=worker_path,
        worker_measurement=_freeze(worker_after),
        observation_document=document,
        run_status="ready",
    )
    with _REGISTRY_LOCK:
        if session in _KNOWN:
            raise RuntimeError("native launcher session registration failed")
        _KNOWN[session] = state
    return session, _observation(document)


def _recheck_verified_native_launcher_session(
    trusted_session: _VerifiedNativeLauncherSession,
) -> _VerifiedNativeLauncherSessionObservation:
    """Remeasure every path-bound artifact without starting the worker."""

    _session, state = _known_state(trusted_session)
    with state.lock:
        _require_owner(state)
        _remeasure_session_state(state)
        return _observation(state.observation_document)


def _validate_verified_native_launcher_session_observation(
    trusted_session: _VerifiedNativeLauncherSession,
    value: Any,
) -> _VerifiedNativeLauncherSessionObservation:
    """Require the exact observation issued with one exact live session."""

    _session, state = _known_state(trusted_session)
    with state.lock:
        _require_owner(state)
        if (
            type(value) is not _VerifiedNativeLauncherSessionObservation
            or getattr(value, "_document", None) is not state.observation_document
        ):
            raise ValueError(
                "native launcher observation must be the exact issued object"
            )
        _remeasure_session_state(state)
        return value


def _execute_verified_native_fake_worker(
    trusted_session: _VerifiedNativeLauncherSession,
    *,
    trusted_admission: Any,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    request_descriptor: int,
    owned_result_write_descriptor: int,
    result_read_descriptor: int,
    checkpoint_descriptor: int,
) -> tuple[
    _SeparationFakeWorkerResultV2Record,
    _VerifiedNativeLauncherExecutionObservation,
]:
    """Synchronously run the fixed worker through one consumed admission."""

    _session, state = _known_state(trusted_session)
    descriptors = (
        request_descriptor,
        owned_result_write_descriptor,
        result_read_descriptor,
        checkpoint_descriptor,
    )
    if (
        any(type(item) is not int or item < 3 for item in descriptors)
        or len(set(descriptors)) != 4
    ):
        raise ValueError("native launcher execution descriptors are invalid")
    _validate_result_descriptor_pair(
        owned_result_write_descriptor,
        result_read_descriptor,
    )
    native_owner: Any | None = None
    raw_wait_status: int | None = None
    timed_out = False
    term_sent = False
    kill_sent = False
    result_writer_owned = True
    with state.lock:
        _require_owner(state)
        if state.run_status != "ready":
            raise RuntimeError("verified native launcher session is single-use")
        _remeasure_session_state(state)
        from ._separation_fake_executor_darwin import (
            _consume_native_start_admission,
        )

        _consume_native_start_admission(
            trusted_admission,
            trusted_session=trusted_session,
            fake_launch_plan_v3=fake_launch_plan_v3,
        )
        state.run_status = "starting"
        try:
            native_owner = state.spawn_method(
                os.fsencode(state.runtime_path),
                os.fsencode(state.worker_path),
                request_descriptor,
                owned_result_write_descriptor,
                checkpoint_descriptor,
            )
            expected_owner_type = getattr(state.module, "_OwnedSpawnChild", None)
            if (
                not isinstance(expected_owner_type, type)
                or type(native_owner) is not expected_owner_type
            ):
                raise RuntimeError("native launcher returned an invalid owner")
        except BaseException:
            state.run_status = "start_failed_consumed"
            try:
                os.close(owned_result_write_descriptor)
                result_writer_owned = False
            except OSError:
                pass
            raise
        state.run_status = "running"
    try:
        (
            raw_wait_status,
            timed_out,
            term_sent,
            kill_sent,
        ) = _supervise_native_owner(native_owner)
        os.close(owned_result_write_descriptor)
        result_writer_owned = False
        wait = _normalise_owned_wait_status(raw_wait_status)
        if (
            timed_out
            or wait["kind"] != "exited"
            or wait["exit_code"] != 0
        ):
            raise RuntimeError("fixed fake worker did not exit successfully")
        result = _read_fake_result_v2(
            result_read_descriptor,
            fake_launch_plan_v3=fake_launch_plan_v3,
        )
        process_report = result["process_report"]
        if (
            native_owner.matches_pid_and_pgid(
                process_report["pid"],
                process_report["pgid"],
            )
            is not True
        ):
            raise RuntimeError("fixed fake worker identity did not match owner")
        with state.lock:
            _require_owner(state)
            if (
                native_owner.leader_reaped is not True
                or native_owner.ownership_released is not True
                or native_owner.ownership_lost is not False
            ):
                raise RuntimeError(
                    "native launcher lacks exact terminal ownership"
                )
            _remeasure_session_state(state)
            state.run_status = "consumed_complete"
        payload = {
            "schema": (
                "sunofriend.separation-native-launcher-execution.v1"
            ),
            "status": "verified_after_exact_reap",
            "native_session_observation_sha256": state.observation_document[
                "observation_sha256"
            ],
            "fake_launch_plan_v3_sha256": fake_launch_plan_v3["plan_sha256"],
            "fake_worker_result_v2_sha256": result["result_sha256"],
            "wait": _plain(wait),
            "timed_out": False,
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "leader_reaped": True,
            "ownership_released": True,
            "ownership_lost": False,
            "worker_reported_identity_matched": True,
            "native_artifact_remeasured_after_reap": True,
            "runtime_remeasured_after_reap": True,
            "fake_worker_remeasured_after_reap": True,
            "raw_pid_in_execution_observation": False,
            "private_result_frame_contains_worker_pid": True,
            "signal_authority_exposed": False,
            "limitations": [
                "runtime_exec_and_worker_script_path_toctou_not_eliminated",
                "destructor_backstop_is_not_terminal_evidence",
                "outer_one_shot_supervisor_required_for_strict_hard_timeout",
                "deterministic_fixture_only_no_source_audio_or_model",
            ],
        }
        terminal = _execution_observation(
            _freeze(
                {
                    **payload,
                    "observation_sha256": _canonical_sha256(payload),
                }
            )
        )
        return result, terminal
    except BaseException:
        with state.lock:
            state.run_status = "consumed_failed"
        raise
    finally:
        if result_writer_owned:
            try:
                os.close(owned_result_write_descriptor)
            except OSError:
                pass
        if native_owner is not None and not native_owner.leader_reaped:
            try:
                _supervise_native_owner(
                    native_owner,
                    timeout_ns=0,
                    term_grace_ns=_TERM_GRACE_NS,
                    kill_reap_ns=_KILL_REAP_NS,
                )
            except BaseException:
                # Dropping the final strong owner outside Python locks invokes
                # the audited native emergency SIGKILL/exact-wait backstop.
                # It is never accepted as terminal execution evidence.
                pass
        native_owner = None


def _known_state(
    value: Any,
) -> tuple[_VerifiedNativeLauncherSession, _SessionState]:
    if type(value) is not _VerifiedNativeLauncherSession:
        raise ValueError("native launcher session must be an exact issued object")
    with _REGISTRY_LOCK:
        state = _KNOWN.get(value)
    if type(state) is not _SessionState:
        raise ValueError("native launcher session is not registered")
    return value, state


def _validate_result_descriptor_pair(
    write_descriptor: int,
    read_descriptor: int,
) -> None:
    try:
        write_flags = fcntl.fcntl(write_descriptor, fcntl.F_GETFL)
        read_flags = fcntl.fcntl(read_descriptor, fcntl.F_GETFL)
        write_stat = os.fstat(write_descriptor)
        read_stat = os.fstat(read_descriptor)
    except OSError as exc:
        raise ValueError("native result descriptors are unavailable") from exc
    if (
        write_flags & os.O_ACCMODE != os.O_WRONLY
        or read_flags & os.O_ACCMODE != os.O_RDONLY
        or os.get_inheritable(write_descriptor)
        or os.get_inheritable(read_descriptor)
        or not stat.S_ISREG(write_stat.st_mode)
        or not stat.S_ISREG(read_stat.st_mode)
        or (write_stat.st_dev, write_stat.st_ino)
        != (read_stat.st_dev, read_stat.st_ino)
    ):
        raise ValueError("native result descriptor pair is invalid")


def _supervise_native_owner(
    native_owner: Any,
    *,
    timeout_ns: int = _RUN_TIMEOUT_NS,
    term_grace_ns: int = _TERM_GRACE_NS,
    kill_reap_ns: int = _KILL_REAP_NS,
) -> tuple[int, bool, bool, bool]:
    """Bound TERM/KILL polling around one exact native owner."""

    for value in (timeout_ns, term_grace_ns, kill_reap_ns):
        if type(value) is not int or value < 0:
            raise ValueError("native supervision deadline is invalid")
    timed_out = False
    term_sent = False
    kill_sent = False
    status = _poll_native_owner_until(
        native_owner,
        time.monotonic_ns() + timeout_ns,
    )
    if status is not None:
        return status, timed_out, term_sent, kill_sent
    timed_out = True
    term_sent = _signal_native_owner(native_owner, signal.SIGTERM)
    status = _poll_native_owner_until(
        native_owner,
        time.monotonic_ns() + term_grace_ns,
    )
    if status is not None:
        return status, timed_out, term_sent, kill_sent
    kill_sent = _signal_native_owner(native_owner, signal.SIGKILL)
    status = _poll_native_owner_until(
        native_owner,
        time.monotonic_ns() + kill_reap_ns,
    )
    if status is None:
        raise RuntimeError("native child did not exact-reap within bounds")
    return status, timed_out, term_sent, kill_sent


def _poll_native_owner_until(native_owner: Any, deadline_ns: int) -> int | None:
    while True:
        status = native_owner.wait_nohang()
        if status is not None:
            if type(status) is not int or status < 0:
                raise RuntimeError("native launcher wait status is invalid")
            return status
        if time.monotonic_ns() >= deadline_ns:
            return None
        time.sleep(_POLL_SECONDS)


def _signal_native_owner(native_owner: Any, signal_number: int) -> bool:
    try:
        native_owner.signal_owned_group(signal_number)
        return True
    except RuntimeError:
        if native_owner.ownership_lost:
            raise RuntimeError("native child ownership was lost")
        if native_owner.leader_reaped and native_owner.ownership_released:
            return False
        raise


def _normalise_owned_wait_status(raw_status: int) -> Mapping[str, Any]:
    """Return a path-free exact interpretation of one waitpid status."""

    if type(raw_status) is not int or raw_status < 0 or raw_status > 0xFFFF:
        raise ValueError("native wait status is invalid")
    if os.WIFEXITED(raw_status):
        return _freeze(
            {
                "kind": "exited",
                "exit_code": os.WEXITSTATUS(raw_status),
                "signal": None,
                "core_dumped": False,
            }
        )
    if os.WIFSIGNALED(raw_status):
        core_dumped = (
            bool(os.WCOREDUMP(raw_status))
            if hasattr(os, "WCOREDUMP")
            else False
        )
        return _freeze(
            {
                "kind": "signaled",
                "exit_code": None,
                "signal": os.WTERMSIG(raw_status),
                "core_dumped": core_dumped,
            }
        )
    raise ValueError("native wait status is not terminal")


def _read_fake_result_v2(
    descriptor: int,
    *,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> _SeparationFakeWorkerResultV2Record:
    try:
        if os.get_inheritable(descriptor):
            raise ValueError("fake result descriptor must be non-inheritable")
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        before = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError("fake result descriptor is unavailable") from exc
    if (
        flags & os.O_ACCMODE != os.O_RDONLY
        or not stat.S_ISREG(before.st_mode)
        or before.st_size <= _RESULT_HEADER_BYTES
    ):
        raise ValueError("fake result descriptor is invalid")
    header = _pread_exact(descriptor, _RESULT_HEADER_BYTES, 0)
    expected = _expected_fake_execution_result_frame_bytes(header)
    if before.st_size != expected:
        raise ValueError("fake result frame is truncated or has trailing bytes")
    frame = _pread_exact(descriptor, expected, 0)
    after = os.fstat(descriptor)
    if _stat_identity(after) != _stat_identity(before):
        raise ValueError("fake result descriptor changed during read")
    return _decode_fake_execution_result_frame(
        frame,
        fake_launch_plan_v3=fake_launch_plan_v3,
    )


def _pread_exact(descriptor: int, byte_count: int, offset: int) -> bytes:
    chunks: list[bytes] = []
    position = offset
    remaining = byte_count
    while remaining:
        chunk = os.pread(descriptor, remaining, position)
        if not chunk:
            raise ValueError("descriptor read is truncated")
        chunks.append(chunk)
        position += len(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _remeasure_session_state(state: _SessionState) -> None:
    receipt = state.build.receipt.to_dict()
    artifact = _remeasure_build_artifact(state.build, receipt=receipt)
    runtime = _measure_bound_file(
        state.runtime_path,
        label="bound Python runtime",
        maximum_bytes=_MAXIMUM_RUNTIME_BYTES,
        executable=True,
        require_not_group_or_other_writable=True,
    )
    worker = _measure_bound_file(
        state.worker_path,
        label="bound fixed fake worker",
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
        executable=False,
        require_not_group_or_other_writable=True,
    )
    if (
        artifact != _plain(state.artifact_measurement)
        or runtime != _plain(state.runtime_measurement)
        or worker != _plain(state.worker_measurement)
    ):
        raise RuntimeError("verified native launcher session binding changed")
    if (
        getattr(
            state.module,
            "_SUNOFRIEND_NATIVE_SOURCE_SHA256",
            None,
        )
        != _native_build._EXPECTED_SOURCE_SHA256
        or getattr(
            state.module,
            "_SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256",
            None,
        )
        != _native_build._EXPECTED_BUILD_CONTRACT_SHA256
        or getattr(state.module, _SPAWN_METHOD_NAME, None)
        is not state.spawn_method
    ):
        raise RuntimeError("verified native launcher module binding changed")


def _remeasure_build_artifact(
    build: Any,
    *,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if type(build) is not _native_build._NativeLauncherBuild:
        raise RuntimeError("native launcher build identity is invalid")
    if build.receipt_sha256 != build.receipt.sha256:
        raise RuntimeError("native launcher build receipt binding changed")
    target = receipt["build_input"]["target"]
    expected = receipt["artifact"]
    measured = _native_build._measure_native_artifact(
        build.artifact_path,
        architecture=target["architecture"],
        expected_cpu_type=target["mach_cpu_type"],
        expected_sdk_version=receipt["build_input"]["toolchain"]["sdk"]["version"],
    )
    _native_build._require_exact_mapping(
        measured,
        {key: expected[key] for key in measured},
        "verified native launcher session artifact",
    )
    return measured


def _load_extension(path: Path) -> ModuleType:
    if _MODULE_NAME in sys.modules:
        raise RuntimeError("native launcher module name is already registered")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    if (
        spec is None
        or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader)
        or spec.name != _MODULE_NAME
    ):
        raise RuntimeError("native launcher extension specification is invalid")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.modules.get(_MODULE_NAME) is module:
            del sys.modules[_MODULE_NAME]
    if _MODULE_NAME in sys.modules:
        raise RuntimeError("native launcher import polluted module registry")
    module_spec = module.__spec__
    if (
        type(module) is not ModuleType
        or module.__name__ != _MODULE_NAME
        or module_spec is None
        or module_spec.name != _MODULE_NAME
        or not isinstance(
            module_spec.loader,
            importlib.machinery.ExtensionFileLoader,
        )
        or module_spec.origin != str(path)
        or module.__file__ != str(path)
    ):
        raise RuntimeError("native launcher extension module identity is invalid")
    return module


def _measure_bound_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    executable: bool,
    require_not_group_or_other_writable: bool,
) -> dict[str, Any]:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or type(maximum_bytes) is not int
        or maximum_bytes <= 0
    ):
        raise RuntimeError(f"{label} measurement request is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        listed = os.lstat(path)
        _validate_bound_file_stat(
            before,
            label=label,
            maximum_bytes=maximum_bytes,
            executable=executable,
            require_not_group_or_other_writable=(
                require_not_group_or_other_writable
            ),
        )
        if (listed.st_dev, listed.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"{label} path and descriptor identities differ")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(
                descriptor,
                min(_READ_CHUNK_BYTES, before.st_size - offset),
                offset,
            )
            if not chunk:
                raise RuntimeError(f"{label} is truncated")
            digest.update(chunk)
            offset += len(chunk)
        after = os.fstat(descriptor)
        listed_after = os.lstat(path)
        if (
            _stat_identity(after) != _stat_identity(before)
            or (listed_after.st_dev, listed_after.st_ino)
            != (before.st_dev, before.st_ino)
        ):
            raise RuntimeError(f"{label} changed during measurement")
        identity = _stat_identity(after)
        return {
            "sha256": digest.hexdigest(),
            "bytes": after.st_size,
            "stat_identity": identity,
            "stat_identity_sha256": _canonical_sha256(identity),
        }
    finally:
        os.close(descriptor)


def _validate_bound_file_stat(
    value: os.stat_result,
    *,
    label: str,
    maximum_bytes: int,
    executable: bool,
    require_not_group_or_other_writable: bool,
) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid not in {0, os.getuid()}
        or value.st_size <= 0
        or value.st_size > maximum_bytes
        or (
            require_not_group_or_other_writable
            and value.st_mode & 0o022
        )
    ):
        raise RuntimeError(f"{label} ownership or geometry is invalid")
    if executable and not value.st_mode & 0o111:
        raise RuntimeError(f"{label} is not executable")


def _artifact_binding(
    value: Mapping[str, Any],
    *,
    path: Path,
) -> dict[str, Any]:
    facts = os.lstat(path)
    identity = _stat_identity(facts)
    measured_identity = _plain(value["stat_identity"])
    expected_measured_identity = {
        **identity,
        "mode": stat.S_IMODE(facts.st_mode),
    }
    if measured_identity != expected_measured_identity:
        raise RuntimeError("native launcher binding identity is invalid")
    return {
        "sha256": value["sha256"],
        "bytes": value["bytes"],
        "stat_identity": identity,
        "stat_identity_sha256": _canonical_sha256(identity),
    }


def _stat_identity(value: os.stat_result) -> dict[str, int]:
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "links": value.st_nlink,
        "owner": value.st_uid,
        "group": value.st_gid,
        "bytes": value.st_size,
        "modified_ns": value.st_mtime_ns,
        "changed_ns": value.st_ctime_ns,
    }


def _require_owner(state: _SessionState) -> None:
    if state.owner_pid != os.getpid():
        raise RuntimeError("native launcher session belongs to another process")


def _observation(
    document: Mapping[str, Any],
) -> _VerifiedNativeLauncherSessionObservation:
    value = object.__new__(_VerifiedNativeLauncherSessionObservation)
    object.__setattr__(value, "_document", document)
    return value


def _execution_observation(
    document: Mapping[str, Any],
) -> _VerifiedNativeLauncherExecutionObservation:
    value = object.__new__(_VerifiedNativeLauncherExecutionObservation)
    object.__setattr__(value, "_document", document)
    return value
