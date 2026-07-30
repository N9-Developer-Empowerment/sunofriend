"""Private verified native-launcher session for deterministic fake execution.

This module is the import boundary between the provenance-only Darwin builder
and a later live fake executor.  It creates one fresh owner-only build,
remeasures the extension immediately before and after import, binds that exact
artifact to the current Python executable and the pinned stdlib-only fake
worker, and retains the imported module only in module-private registry state.

The opaque session is not execution authority.  This module makes no spawn
call and has no public, CLI or TUI route.  The private registry is part of the
trusted-parent boundary, not a defence against hostile Python in that process.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import os
import stat
import sys
import threading
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
            "no_direct_spawn_call_or_public_route_exists_in_this_module",
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
        return _observation(state.observation_document)


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
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    if (
        spec is None
        or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader)
        or spec.name != _MODULE_NAME
    ):
        raise RuntimeError("native launcher extension specification is invalid")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
