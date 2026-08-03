"""Isolated adversarial harness for a built Darwin launcher extension.

The harness is deliberately independent of the future build module.  Give it
an absolute path to a provenance-approved extension artifact and an absolute
temporary directory.  It loads that private artifact, closes every unrelated
descriptor, and exercises all source-descriptor permutations involving
logical FD 3, 4 and 5 plus fixed representative low, mixed-collision and
near-limit physical layouts.

This script performs no compilation, network access, model import, audio
operation or separation.
"""

from __future__ import annotations

import argparse
import copy
import errno
import fcntl
import gc
import hashlib
import importlib.machinery
import importlib.util
import itertools
import json
import os
import pickle
import re
import resource
import signal
import socket
import stat
import sys
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator


_REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY / "src"))
import sunofriend._separation_macos_loaded_images as _loaded_images  # noqa: E402
import sunofriend._separation_macos_sandbox_network_observer as _network_observer  # noqa: E402
import sunofriend._separation_melroformer_native_model_free_adapter_darwin as _model_free_parent_adapter  # noqa: E402
import sunofriend._separation_melroformer_native_transport as _native_transport  # noqa: E402
import sunofriend._separation_melroformer_supervision as _supervision  # noqa: E402
import sunofriend._separation_melroformer_upstream_evidence as _melroformer_evidence  # noqa: E402
import sunofriend._separation_worker_ready_handshake as _ready_handshake  # noqa: E402


_MODULE_NAME = "_separation_native_spawn_darwin"
_METHOD_NAME = "_spawn_bound_fake_worker"
_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_canary_worker.py").resolve()
)
_HOLD_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_hold_worker.py").resolve()
)
_DESCENDANT_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_descendant_worker.py").resolve()
)
_NETWORK_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_network_worker.py").resolve()
)
_READY_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_ready_worker.py").resolve()
)
_COMBINED_WORKER = (
    Path(__file__)
    .with_name("_separation_native_spawn_combined_worker.py")
    .resolve()
)
_READY_RELEASE_WORKER = (
    Path(__file__)
    .with_name("_separation_native_spawn_ready_release_worker.py")
    .resolve()
)
_FRAME_BOOTSTRAP_WORKER = (
    Path(__file__)
    .with_name("_separation_native_spawn_frame_bootstrap_worker.py")
    .resolve()
)
_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
_LOGICAL_ROLES = ("request", "result", "checkpoint")
_TARGET_FDS = (3, 4, 5)
_LOW_CANARY_FDS = (6, 7, 8)
_ALTERNATE_LOW_CANARY_FDS = (12, 13, 14)
_CANARY_SOFT_LIMIT = 4_096
_HIGH_CANARY_FDS = (
    _CANARY_SOFT_LIMIT - 3,
    _CANARY_SOFT_LIMIT - 2,
    _CANARY_SOFT_LIMIT - 1,
)
_REPRESENTATIVE_SOURCE_FD_LAYOUTS = (
    (9, 10, 11),
    (11, 9, 10),
    (6, 7, 8),
    (6, 10, 5),
    (3, 9, 10),
    (9, 4, 10),
    (9, 10, 5),
    (3, 10, 5),
    (11, 4, 3),
    (64, 1_024, _CANARY_SOFT_LIMIT - 4),
)
_EXPECTED_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
}
_REQUEST_BYTES = b"sunofriend-native-canary-request-v1\n"
_CHECKPOINT_BYTES = b"sunofriend-native-canary-checkpoint-v1\n"
_INITIAL_OFFSETS = {
    "request": 2,
    "result": 7,
    "checkpoint": 3,
}
_WAIT_SECONDS = 5.0
_MAX_ARTIFACT_BYTES = 16_777_216
_MAX_RUNTIME_BYTES = 134_217_728
_MAX_WORKER_BYTES = 65_536
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CDHASH_RE = re.compile(r"^[0-9a-f]{40}$")
_DARWIN_TEXT_ENCODING_RE = re.compile(r"^0x[0-9A-Fa-f]{1,8}:[0-9]{1,5}:[0-9]{1,5}$")


@dataclass(frozen=True)
class DescriptorSnapshot:
    descriptor: int
    descriptor_flags: int
    access_mode: int
    append_enabled: bool
    nonblocking_enabled: bool
    async_enabled: bool
    inheritable: bool
    device: int
    inode: int
    mode: int
    links: int
    owner: int
    group: int
    special_device: int
    offset: int | None


@dataclass(frozen=True)
class BoundFileSnapshot:
    sha256: str
    device: int
    inode: int
    mode: int
    links: int
    owner: int
    group: int
    bytes: int
    modified_ns: int
    changed_ns: int


class _OwnedCanaryChild:
    """Exact child ownership with bounded failure cleanup."""

    def __init__(self, native_owner: Any) -> None:
        self._native_owner = native_owner
        self._reaped = False

    def __enter__(self) -> "_OwnedCanaryChild":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: Any,
    ) -> bool:
        del exception_type, traceback
        if self._reaped:
            return False
        try:
            self.terminate_and_reap()
        except BaseException as cleanup_error:
            if exception is not None:
                raise RuntimeError(
                    "canary failure cleanup could not prove exact child reap"
                ) from exception
            raise cleanup_error
        return False

    def _wait_until(self, deadline: float) -> int | None:
        while time.monotonic() < deadline:
            status = self._native_owner.wait_nohang()
            if status is not None:
                self._reaped = True
                return status
            time.sleep(0.005)
        return None

    def _signal_owned_group_or_pid(
        self,
        *,
        deadline: float,
    ) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("canary child-group deadline elapsed")
        self._native_owner.signal_owned_group(signal.SIGKILL)

    def terminate_and_reap(self) -> int:
        if self._reaped:
            raise RuntimeError("canary child was already reaped")
        deadline = time.monotonic() + 1.0
        self._signal_owned_group_or_pid(deadline=deadline)
        status = self._wait_until(deadline)
        if status is None:
            raise TimeoutError("canary child could not be reaped")
        return status

    def wait(self) -> int:
        if self._reaped:
            raise RuntimeError("canary child was already reaped")
        status = self._wait_until(time.monotonic() + _WAIT_SECONDS)
        if status is not None:
            return status
        self.terminate_and_reap()
        raise TimeoutError("native spawn canary timed out")


def _soft_descriptor_limit() -> int:
    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit == resource.RLIM_INFINITY:
        raise RuntimeError("unbounded descriptor limits are unsupported")
    return int(soft_limit)


def _assert_descriptor_range_closed(start: int, end: int) -> None:
    for descriptor in range(start, end):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        raise RuntimeError("an inherited descriptor survived isolation")


def _prepare_isolated_descriptor_limit() -> int:
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if (
        soft_limit == resource.RLIM_INFINITY
        or hard_limit < _CANARY_SOFT_LIMIT
        or soft_limit < _CANARY_SOFT_LIMIT
    ):
        raise RuntimeError("descriptor limit is too low for complete canary scan")
    original_soft_limit = int(soft_limit)
    os.closerange(3, original_soft_limit)
    _assert_descriptor_range_closed(3, original_soft_limit)
    resource.setrlimit(
        resource.RLIMIT_NOFILE,
        (_CANARY_SOFT_LIMIT, hard_limit),
    )
    if _soft_descriptor_limit() != _CANARY_SOFT_LIMIT:
        raise RuntimeError("fixed canary descriptor limit was not established")
    _assert_descriptor_range_closed(
        _CANARY_SOFT_LIMIT,
        original_soft_limit,
    )
    return original_soft_limit


def _observe_outer_supervisor_descriptors() -> dict[str, Any]:
    """Observe the harness entry state before it performs any FD cleanup."""

    descriptors = [
        snapshot.descriptor for snapshot in snapshot_parent_descriptors()
    ]
    return {
        "observation_point": "harness_entry_before_descriptor_cleanup",
        "open_descriptors": descriptors,
        "only_standard_descriptors_open": descriptors == [0, 1, 2],
    }


def _snapshot_descriptor(descriptor: int) -> DescriptorSnapshot:
    facts = os.fstat(descriptor)
    status_flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
    try:
        offset = os.lseek(descriptor, 0, os.SEEK_CUR)
    except OSError as error:
        if error.errno != errno.ESPIPE:
            raise
        offset = None
    return DescriptorSnapshot(
        descriptor=descriptor,
        descriptor_flags=fcntl.fcntl(descriptor, fcntl.F_GETFD),
        access_mode=status_flags & os.O_ACCMODE,
        append_enabled=bool(status_flags & os.O_APPEND),
        nonblocking_enabled=bool(status_flags & os.O_NONBLOCK),
        async_enabled=bool(status_flags & getattr(os, "O_ASYNC", 0)),
        inheritable=os.get_inheritable(descriptor),
        device=facts.st_dev,
        inode=facts.st_ino,
        mode=facts.st_mode,
        links=facts.st_nlink,
        owner=facts.st_uid,
        group=facts.st_gid,
        special_device=facts.st_rdev,
        offset=offset,
    )


def snapshot_parent_descriptors() -> tuple[DescriptorSnapshot, ...]:
    snapshots: list[DescriptorSnapshot] = []
    for descriptor in range(_soft_descriptor_limit()):
        try:
            snapshots.append(_snapshot_descriptor(descriptor))
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
    return tuple(snapshots)


def _close_descriptors_from_three() -> None:
    os.closerange(3, _soft_descriptor_limit())


def _measure_bound_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    required_mode: int | None = None,
    current_owner_required: bool,
    executable_required: bool,
) -> BoundFileSnapshot:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > maximum_bytes
        ):
            raise RuntimeError("bound regular file is invalid")
        permissions = stat.S_IMODE(before.st_mode)
        if (
            (required_mode is not None and permissions != required_mode)
            or (current_owner_required and before.st_uid != os.getuid())
            or (permissions & 0o022) != 0
            or (executable_required and (permissions & 0o111) == 0)
        ):
            raise RuntimeError("bound regular file permissions are invalid")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(
                descriptor,
                min(1_048_576, before.st_size - offset),
                offset,
            )
            if not chunk:
                raise RuntimeError("native extension artifact is truncated")
            digest.update(chunk)
            offset += len(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_uid,
            before.st_gid,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_gid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if after_identity != before_identity:
            raise RuntimeError("native extension changed during measurement")
        return BoundFileSnapshot(
            sha256=digest.hexdigest(),
            device=after.st_dev,
            inode=after.st_ino,
            mode=after.st_mode,
            links=after.st_nlink,
            owner=after.st_uid,
            group=after.st_gid,
            bytes=after.st_size,
            modified_ns=after.st_mtime_ns,
            changed_ns=after.st_ctime_ns,
        )
    finally:
        os.close(descriptor)


def _measure_artifact(path: Path) -> BoundFileSnapshot:
    return _measure_bound_regular_file(
        path,
        maximum_bytes=_MAX_ARTIFACT_BYTES,
        required_mode=0o500,
        current_owner_required=True,
        executable_required=True,
    )


def _measure_runtime(path: Path) -> BoundFileSnapshot:
    return _measure_bound_regular_file(
        path,
        maximum_bytes=_MAX_RUNTIME_BYTES,
        current_owner_required=False,
        executable_required=True,
    )


def _measure_worker(path: Path) -> BoundFileSnapshot:
    return _measure_bound_regular_file(
        path,
        maximum_bytes=_MAX_WORKER_BYTES,
        current_owner_required=True,
        executable_required=False,
    )


def _path_free_file_identity(snapshot: BoundFileSnapshot) -> dict[str, int | str]:
    return {
        "sha256": snapshot.sha256,
        "device": snapshot.device,
        "inode": snapshot.inode,
        "mode": stat.S_IMODE(snapshot.mode),
        "file_type": stat.S_IFMT(snapshot.mode),
        "links": snapshot.links,
        "owner": snapshot.owner,
        "group": snapshot.group,
        "bytes": snapshot.bytes,
        "modified_ns": snapshot.modified_ns,
        "changed_ns": snapshot.changed_ns,
    }


def supervised_harness_subprocess_policy() -> dict[str, Any]:
    """Required outer-process descriptor hygiene for future live wiring."""

    return {
        "close_fds": True,
        "pass_fds": (),
    }


def _move_to_exact_descriptor(source: int, target: int) -> int:
    if source != target:
        os.dup2(source, target, inheritable=False)
        os.close(source)
    return target


def _install_transport_descriptors(
    directory: Path,
    source_fds: tuple[int, int, int],
    *,
    request_bytes: bytes = _REQUEST_BYTES,
    checkpoint_bytes: bytes = _CHECKPOINT_BYTES,
) -> dict[str, Path]:
    paths = {
        "request": directory / "request.bin",
        "result": directory / "result.bin",
        "checkpoint": directory / "checkpoint.bin",
    }
    paths["request"].write_bytes(request_bytes)
    paths["result"].write_bytes(b"")
    paths["checkpoint"].write_bytes(checkpoint_bytes)
    if (
        len(set(source_fds)) != len(_LOGICAL_ROLES)
        or any(descriptor < 3 for descriptor in source_fds)
        or max(source_fds) >= _soft_descriptor_limit()
        or set(source_fds)
        & set((*_canary_fds_for_source_layout(source_fds), *_HIGH_CANARY_FDS))
    ):
        raise RuntimeError("canary source descriptor layout is invalid")
    roles_by_target = sorted(
        zip(_LOGICAL_ROLES, source_fds),
        key=lambda item: (item[1] in _TARGET_FDS, item[1]),
    )
    for role, descriptor in roles_by_target:
        flags = os.O_WRONLY if role == "result" else os.O_RDONLY
        opened = os.open(paths[role], flags)
        descriptor = _move_to_exact_descriptor(opened, descriptor)
        os.set_inheritable(descriptor, False)
        os.lseek(descriptor, _INITIAL_OFFSETS[role], os.SEEK_SET)
    return paths


def _install_regular_canary(path: Path, target: int) -> None:
    path.write_bytes(b"unrelated regular descriptor canary\n")
    descriptor = _move_to_exact_descriptor(
        os.open(path, os.O_RDONLY),
        target,
    )
    os.set_inheritable(descriptor, True)


def _install_pipe_canary(target: int) -> None:
    reader, writer = os.pipe()
    try:
        os.close(writer)
        writer = -1
        descriptor = _move_to_exact_descriptor(reader, target)
        reader = -1
        os.set_inheritable(descriptor, True)
    finally:
        if reader >= 0:
            os.close(reader)
        if writer >= 0:
            os.close(writer)


def _install_socket_canary(target: int) -> None:
    local, peer = socket.socketpair()
    try:
        peer.close()
        source = local.detach()
        descriptor = _move_to_exact_descriptor(source, target)
        os.set_inheritable(descriptor, True)
    finally:
        local.close()
        peer.close()


def _canary_fds_for_source_layout(
    source_fds: tuple[int, int, int],
) -> tuple[int, int, int]:
    if set(source_fds) & set(_LOW_CANARY_FDS):
        return _ALTERNATE_LOW_CANARY_FDS
    return _LOW_CANARY_FDS


def _install_unrelated_inheritable_canaries(
    directory: Path,
    *,
    low_canary_fds: tuple[int, int, int],
) -> None:
    low_regular, low_pipe, low_socket = low_canary_fds
    high_regular, high_pipe, high_socket = _HIGH_CANARY_FDS
    if _soft_descriptor_limit() <= max(_HIGH_CANARY_FDS):
        raise RuntimeError("descriptor limit is too low for high canaries")
    _install_regular_canary(directory / "low-regular.bin", low_regular)
    _install_pipe_canary(low_pipe)
    _install_socket_canary(low_socket)
    _install_regular_canary(directory / "high-regular.bin", high_regular)
    _install_pipe_canary(high_pipe)
    _install_socket_canary(high_socket)


def _load_extension(path: Path) -> ModuleType:
    expected_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if (
        not isinstance(expected_suffix, str)
        or not expected_suffix
        or not path.name.endswith(expected_suffix)
    ):
        raise RuntimeError("native extension suffix is invalid")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    if (
        spec is None
        or not isinstance(
            spec.loader,
            importlib.machinery.ExtensionFileLoader,
        )
        or spec.name != _MODULE_NAME
    ):
        raise RuntimeError("native extension specification is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module_spec = module.__spec__
    if (
        module.__name__ != _MODULE_NAME
        or module_spec is None
        or module_spec.name != _MODULE_NAME
        or not isinstance(
            module_spec.loader,
            importlib.machinery.ExtensionFileLoader,
        )
        or module_spec.origin != str(path)
        or module.__file__ != str(path)
    ):
        raise RuntimeError("native extension module identity is invalid")
    return module


def _load_verified_extension(
    path: Path,
    *,
    expected_artifact_sha256: str,
    expected_source_sha256: str,
    expected_build_contract_sha256: str,
) -> tuple[ModuleType, BoundFileSnapshot]:
    expected_values = (
        expected_artifact_sha256,
        expected_source_sha256,
        expected_build_contract_sha256,
    )
    if any(_SHA256_RE.fullmatch(value) is None for value in expected_values):
        raise ValueError("expected native identity is invalid")
    before = _measure_artifact(path)
    if before.sha256 != expected_artifact_sha256:
        raise RuntimeError("native extension artifact hash is unexpected")
    module = _load_extension(path)
    after = _measure_artifact(path)
    if after != before:
        raise RuntimeError("native extension changed across import")
    if getattr(module, "_SUNOFRIEND_NATIVE_SOURCE_SHA256", None) != (
        expected_source_sha256
    ):
        raise RuntimeError("native extension source binding is invalid")
    if (
        getattr(
            module,
            "_SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256",
            None,
        )
        != expected_build_contract_sha256
    ):
        raise RuntimeError("native extension build binding is invalid")
    return module, after


def _read_single_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > 65_536 or not raw.endswith(b"\n"):
        raise AssertionError("canary result framing is invalid")
    decoder = json.JSONDecoder()
    document, end = decoder.raw_decode(raw.decode("ascii"))
    if raw.decode("ascii")[end:] != "\n" or not isinstance(document, dict):
        raise AssertionError("canary result contains trailing data")
    return document


def _wait_for_result_schema(
    path: Path,
    *,
    schema: str,
    deadline: float,
) -> tuple[dict[str, Any], bytes]:
    """Read one complete bounded JSON generation from a replaced result file."""

    while time.monotonic() < deadline:
        raw = path.read_bytes()
        if len(raw) > 65_536:
            raise AssertionError("canary result exceeded its bound")
        if raw.endswith(b"\n"):
            try:
                document = json.loads(raw.decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            else:
                if isinstance(document, dict) and document.get("schema") == schema:
                    return document, raw
        time.sleep(0.005)
    raise TimeoutError(f"{schema} result was not written")


def _read_bounded_pid_marker(path: Path, *, deadline: float) -> int:
    while time.monotonic() < deadline:
        raw = path.read_bytes()
        if raw.endswith(b"\n") and raw[:-1].isdigit():
            pid = int(raw[:-1])
            if pid > 0:
                return pid
        if len(raw) > 32:
            raise AssertionError("native owner marker is invalid")
        time.sleep(0.005)
    raise TimeoutError("native owner marker was not written")


def _assert_parent_unchanged(
    expected: tuple[DescriptorSnapshot, ...],
    observed: tuple[DescriptorSnapshot, ...],
) -> None:
    def stable(snapshot: DescriptorSnapshot) -> tuple[Any, ...]:
        return (
            snapshot.descriptor,
            snapshot.descriptor_flags,
            snapshot.access_mode,
            snapshot.append_enabled,
            snapshot.nonblocking_enabled,
            snapshot.async_enabled,
            snapshot.inheritable,
            snapshot.device,
            snapshot.inode,
            snapshot.mode,
            snapshot.links,
            snapshot.owner,
            snapshot.group,
            snapshot.special_device,
            snapshot.offset,
        )

    if tuple(map(stable, observed)) != tuple(map(stable, expected)):
        raise AssertionError(
            "native launcher changed the parent descriptor table, identity, "
            "stable flags or inheritability"
        )


def _assert_worker_report(
    report: dict[str, Any],
    *,
    native_owner: Any,
    null_identity: dict[str, int],
) -> None:
    expected_hashes = {
        "request": hashlib.sha256(_REQUEST_BYTES).hexdigest(),
        "checkpoint": hashlib.sha256(_CHECKPOINT_BYTES).hexdigest(),
    }
    if report.get("schema") != ("sunofriend.native-spawn-descriptor-canary.v2"):
        raise AssertionError("canary result schema is invalid")
    if report.get("ok") is not True:
        raise AssertionError("canary worker did not complete")
    if not native_owner.matches_pid_and_pgid(
        report.get("pid"),
        report.get("pgid"),
    ):
        raise AssertionError("canary worker does not own a new PID-matched group")
    if report.get("open_descriptors") != [0, 1, 2, 3, 4, 5]:
        raise AssertionError("child descriptor allowlist is not exact")
    if report.get("signal_state_observation") != {
        "observation_point": "worker_main_after_cpython_startup",
        "main_thread_mask_empty": True,
        "blocked_signal_names": [],
        "handlers": {
            "SIGHUP": "default",
            "SIGINT": "python_default_int_handler",
            "SIGQUIT": "default",
            "SIGPIPE": "ignored",
            "SIGTERM": "default",
            "SIGCHLD": "default",
            "SIGXFSZ": "ignored",
        },
        "termination_signals_default": True,
        "sigchld_default": True,
        "cpython_runtime_adjustments_observed": True,
    }:
        raise AssertionError("child post-CPython signal state differs")
    if report.get("descriptor_scan_soft_limit") != _CANARY_SOFT_LIMIT:
        raise AssertionError("child descriptor scan did not cover the fixed limit")
    if report.get("transport_inheritable") != {
        "3": False,
        "4": False,
        "5": False,
    }:
        raise AssertionError("worker did not harden FD 3/4/5")
    if report.get("transport_access") != {
        "3": "read_only",
        "4": "write_only",
        "5": "read_only",
    }:
        raise AssertionError("logical descriptor access is incorrect")
    stdio = report.get("stdio_observation")
    if not isinstance(stdio, dict):
        raise AssertionError("child stdio observation is invalid")
    if (
        stdio.get("same_identity") is not True
        or stdio.get("all_character_devices") is not True
        or stdio.get("access")
        != {"0": "read_only", "1": "write_only", "2": "write_only"}
        or stdio.get("identities") != [null_identity] * 3
    ):
        raise AssertionError("child stdio is not the fixed null device")
    if report.get("rejected_operation_errno") != {
        "request_write": errno.EBADF,
        "result_read": errno.EBADF,
        "checkpoint_write": errno.EBADF,
    }:
        raise AssertionError("logical descriptor negative access is incorrect")
    if (
        report.get("request_bytes") != len(_REQUEST_BYTES)
        or report.get("request_sha256") != expected_hashes["request"]
        or report.get("checkpoint_bytes") != len(_CHECKPOINT_BYTES)
        or report.get("checkpoint_sha256") != expected_hashes["checkpoint"]
    ):
        raise AssertionError("logical request or checkpoint data is incorrect")
    environment = report.get("environment_observation")
    if not isinstance(environment, dict):
        raise AssertionError("worker environment observation is invalid")
    if environment.get("required_bindings") != _EXPECTED_ENVIRONMENT:
        raise AssertionError("worker fixed environment bindings are invalid")
    injected = environment.get("runtime_injected")
    if not isinstance(injected, dict):
        raise AssertionError("worker runtime environment observation is invalid")
    value = injected.get("value")
    if (
        injected.get("name") != "__CF_USER_TEXT_ENCODING"
        or injected.get("present") is not True
        or not isinstance(value, str)
        or len(value) > 40
        or _DARWIN_TEXT_ENCODING_RE.fullmatch(value) is None
        or injected.get("value_sha256")
        != hashlib.sha256(value.encode("utf-8")).hexdigest()
    ):
        raise AssertionError("Darwin runtime environment injection is invalid")
    if report.get("python_flags") != {
        "isolated": 1,
        "dont_write_bytecode": 1,
        "no_site": 1,
    }:
        raise AssertionError("worker Python isolation flags are incorrect")


def _assert_canaries_present_in_parent(
    snapshot: tuple[DescriptorSnapshot, ...],
    *,
    source_fds: tuple[int, int, int],
    low_canary_fds: tuple[int, int, int],
) -> None:
    by_descriptor = {item.descriptor: item for item in snapshot}
    expected = (*low_canary_fds, *_HIGH_CANARY_FDS)
    if any(descriptor not in by_descriptor for descriptor in expected):
        raise AssertionError(
            f"parent canary descriptor is missing for source layout {source_fds}"
        )
    if any(not by_descriptor[item].inheritable for item in expected):
        raise AssertionError("parent canary descriptor is not inheritable")
    expected_kinds = (
        stat.S_IFREG,
        stat.S_IFIFO,
        stat.S_IFSOCK,
        stat.S_IFREG,
        stat.S_IFIFO,
        stat.S_IFSOCK,
    )
    observed_kinds = tuple(stat.S_IFMT(by_descriptor[item].mode) for item in expected)
    if observed_kinds != expected_kinds:
        raise AssertionError("parent canary descriptor kinds are invalid")


def _null_device_identity() -> dict[str, int]:
    facts = os.stat("/dev/null")
    if not stat.S_ISCHR(facts.st_mode):
        raise RuntimeError("native null device is not a character device")
    return {
        "device": facts.st_dev,
        "inode": facts.st_ino,
        "special_device": facts.st_rdev,
        "file_type": stat.S_IFMT(facts.st_mode),
    }


def _exact_target_source_fd_permutations() -> Iterator[tuple[int, int, int]]:
    yield from itertools.permutations(_TARGET_FDS)


def _source_fd_layouts() -> Iterator[tuple[str, tuple[int, int, int]]]:
    for source_fds in _exact_target_source_fd_permutations():
        yield "exact_target_permutation", source_fds
    for source_fds in _REPRESENTATIVE_SOURCE_FD_LAYOUTS:
        yield "representative_physical_layout", source_fds


def _run_owner_drop_canary(
    *,
    spawn: Any,
    runtime_path: Path,
    temporary_root: Path,
) -> dict[str, Any]:
    _close_descriptors_from_three()
    case_directory = temporary_root / "owner-drop"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before = snapshot_parent_descriptors()
    native_owner = spawn(
        os.fsencode(runtime_path),
        os.fsencode(_HOLD_WORKER),
        *_TARGET_FDS,
    )
    worker_pid = _read_bounded_pid_marker(
        paths["result"],
        deadline=time.monotonic() + _WAIT_SECONDS,
    )
    if not native_owner.matches_pid_and_pgid(worker_pid, worker_pid):
        raise AssertionError("native owner marker identity is invalid")
    if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
        raise AssertionError("native owner exposes transferable authority")
    for operation in (copy.copy, pickle.dumps):
        try:
            operation(native_owner)
        except (TypeError, AttributeError):
            continue
        raise AssertionError("native owner can be copied or serialized")
    after_spawn = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after_spawn)
    del native_owner
    gc.collect()
    after_drop = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after_drop)
    try:
        os.waitpid(worker_pid, os.WNOHANG)
    except ChildProcessError:
        exact_reap_observed = True
    else:
        exact_reap_observed = False
    if not exact_reap_observed:
        raise AssertionError("dropped native owner did not exact-reap its child")
    return {
        "worker_pid_reported_by_child": True,
        "owner_identity_confirmed": True,
        "raw_pid_not_exposed": True,
        "copy_and_pickle_rejected": True,
        "drop_forced_exact_reap": True,
        "parent_descriptors_unchanged": True,
    }


def _run_external_reap_poison_canary(
    *,
    spawn: Any,
    runtime_path: Path,
    temporary_root: Path,
) -> dict[str, Any]:
    _close_descriptors_from_three()
    case_directory = temporary_root / "external-reap-poison"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before = snapshot_parent_descriptors()
    native_owner = spawn(
        os.fsencode(runtime_path),
        os.fsencode(_HOLD_WORKER),
        *_TARGET_FDS,
    )
    worker_pid = _read_bounded_pid_marker(
        paths["result"],
        deadline=time.monotonic() + _WAIT_SECONDS,
    )
    if not native_owner.matches_pid_and_pgid(worker_pid, worker_pid):
        raise AssertionError("stolen-owner marker identity is invalid")
    os.kill(worker_pid, signal.SIGKILL)
    while True:
        try:
            waited, status = os.waitpid(worker_pid, 0)
        except InterruptedError:
            continue
        break
    if waited != worker_pid or not os.WIFSIGNALED(status):
        raise AssertionError("external reaper did not consume exact child")
    try:
        native_owner.signal_owned_group(signal.SIGKILL)
    except RuntimeError as error:
        ownership_loss_rejected = "ownership was lost before group signal" in str(error)
    else:
        ownership_loss_rejected = False
    if (
        not ownership_loss_rejected
        or native_owner.ownership_lost is not True
        or native_owner.ownership_released is not False
    ):
        raise AssertionError("native owner did not poison stolen ownership")
    try:
        native_owner.wait_nohang()
    except RuntimeError:
        poisoned_wait_rejected = True
    else:
        poisoned_wait_rejected = False
    if not poisoned_wait_rejected:
        raise AssertionError("poisoned native owner retained wait authority")
    del native_owner
    gc.collect()
    after_drop = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after_drop)
    return {
        "external_exact_reap_observed": True,
        "owner_transitioned_to_lost": True,
        "direct_stale_signal_rejected": True,
        "poisoned_wait_rejected": True,
        "drop_after_loss_did_not_touch_parent_descriptors": True,
    }


def _run_owner_bound_process_image_canary(
    *,
    spawn: Any,
    runtime_path: Path,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
    temporary_root: Path,
) -> dict[str, Any]:
    """Exercise live image observation without exporting child authority."""

    _close_descriptors_from_three()
    case_directory = temporary_root / "owner-bound-process-image"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before = snapshot_parent_descriptors()
    native_owner = spawn(
        os.fsencode(runtime_path),
        os.fsencode(_HOLD_WORKER),
        *_TARGET_FDS,
    )
    worker_pid = _read_bounded_pid_marker(
        paths["result"],
        deadline=time.monotonic() + _WAIT_SECONDS,
    )
    if not native_owner.matches_pid_and_pgid(worker_pid, worker_pid):
        raise AssertionError("process-image canary marker identity is invalid")
    if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
        raise AssertionError("process-image observer exposes transferable authority")
    wrong_path = temporary_root / "deliberately-not-the-owned-process-image"
    try:
        native_owner.observe_owned_process_image(
            os.fsencode(wrong_path),
            os.fsencode(wrong_path),
            expected_process_image_cdhash.encode("ascii"),
        )
    except RuntimeError as error:
        wrong_path_rejected = "process image path differs" in str(error)
    else:
        wrong_path_rejected = False
    if not wrong_path_rejected:
        raise AssertionError("owner-bound observer accepted a wrong process image")
    wrong_cdhash = (
        ("0" if expected_process_image_cdhash[0] != "0" else "1")
        + expected_process_image_cdhash[1:]
    )
    try:
        native_owner.observe_owned_process_image(
            os.fsencode(runtime_path),
            os.fsencode(expected_process_image_path),
            wrong_cdhash.encode("ascii"),
        )
    except RuntimeError as error:
        wrong_cdhash_rejected = "process image CDHash differs" in str(error)
    else:
        wrong_cdhash_rejected = False
    if not wrong_cdhash_rejected:
        raise AssertionError("owner-bound observer accepted a wrong CDHash")
    if (
        native_owner.ownership_released is not False
        or native_owner.ownership_lost is not False
    ):
        raise AssertionError("failed image observation altered native ownership")
    observation = native_owner.observe_owned_process_image(
        os.fsencode(runtime_path),
        os.fsencode(expected_process_image_path),
        expected_process_image_cdhash.encode("ascii"),
    )
    if observation != {
        "kernel_cdhash": expected_process_image_cdhash,
        "path_state": "matched_expected_process_image",
    }:
        raise AssertionError("owner-bound process-image observation differs")
    after_observation = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after_observation)
    native_owner.signal_owned_group(signal.SIGKILL)
    with _OwnedCanaryChild(native_owner) as child:
        status = child.wait()
    if not os.WIFSIGNALED(status) or os.WTERMSIG(status) != signal.SIGKILL:
        raise AssertionError("process-image canary was not exactly terminated")
    after_reap = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after_reap)
    return {
        "wrong_process_image_rejected": True,
        "wrong_cdhash_rejected": True,
        "rejection_preserved_ownership": True,
        "expected_process_image_matched": True,
        "kernel_cdhash_matched_static_identity": True,
        "raw_pid_or_pgid_retained": False,
        "exact_reap_after_observation": True,
        "parent_descriptors_unchanged": True,
    }


def _run_owner_bound_network_canary(
    *,
    spawn: Any,
    runtime_path: Path,
    temporary_root: Path,
) -> dict[str, Any]:
    """Bind one kernel-denial stream to the opaque owner without its PID."""

    _close_descriptors_from_three()
    case_directory = temporary_root / "owner-bound-network"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before_observer = snapshot_parent_descriptors()
    broker = _network_observer._prepare_owner_bound_network_observer()
    native_owner: Any | None = None
    try:
        with_observer = snapshot_parent_descriptors()
        native_owner = spawn(
            os.fsencode(runtime_path),
            os.fsencode(_NETWORK_WORKER),
            *_TARGET_FDS,
        )
        if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
            raise AssertionError("network canary owner exposes transferable authority")
        with _OwnedCanaryChild(native_owner) as child:
            deadline = time.monotonic() + _WAIT_SECONDS
            while time.monotonic() < deadline:
                raw = paths["result"].read_bytes()
                if raw.endswith(b"\n"):
                    break
                if len(raw) > 65_536:
                    raise AssertionError("network canary result exceeded its bound")
                time.sleep(0.005)
            else:
                raise TimeoutError("network canary result was not written")
            worker_report = _read_single_json(paths["result"])
            if worker_report != {
                "schema": "sunofriend.native-owner-network-canary-worker.v1",
                "ok": True,
                "connect_errno_name": "EPERM",
                "loopback_only": True,
                "external_destination_contacted": False,
                "open_descriptors": [0, 1, 2, 3, 4, 5],
                "model_or_checkpoint_loaded": False,
            }:
                raise AssertionError("owner-bound network worker report differs")
            observation = broker.finish(native_owner=native_owner)
            if broker.consumed is not True:
                raise AssertionError("owner-bound network broker was not consumed")
            try:
                broker.finish(native_owner=native_owner)
            except RuntimeError as error:
                reuse_rejected = "already consumed" in str(error)
            else:
                reuse_rejected = False
            if not reuse_rejected:
                raise AssertionError("owner-bound network broker was reusable")
            after_observation = snapshot_parent_descriptors()
            _assert_parent_unchanged(before_observer, after_observation)
            status = child.wait()
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise AssertionError("owner-bound network canary did not exit normally")
        if (
            native_owner.leader_reaped is not True
            or native_owner.group_empty is not True
            or native_owner.ownership_released is not True
            or native_owner.ownership_lost is not False
        ):
            raise AssertionError("owner-bound network canary was not exact-reaped")
        if observation["observation"]["deliberate_canary_denial_count"] < 1:
            raise AssertionError("owner-bound network denial canary was absent")
        if observation["privacy"] != {
            "raw_log_persisted": False,
            "raw_event_messages_retained": False,
            "destination_details_retained": False,
            "target_pid_retained": False,
            "owner_pid_or_pgid_exported": False,
            "broker_single_use": True,
        }:
            raise AssertionError("owner-bound network privacy contract differs")
        encoded = json.dumps(
            _network_observer._plain(observation),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if "Sandbox: " in encoded or "remote:" in encoded or "local:" in encoded:
            raise AssertionError("owner-bound network evidence retained raw details")
        after_reap = snapshot_parent_descriptors()
        _assert_parent_unchanged(before_observer, after_reap)
        return {
            "observer_ready_before_native_spawn": (
                len(with_observer) > len(before_observer)
            ),
            "native_owner_bound": True,
            "deliberate_canary_denial_observed": True,
            "other_owned_network_denial_count": observation["observation"][
                "other_target_network_denial_count"
            ],
            "broker_single_use_rejected_replay": True,
            "raw_pid_or_pgid_retained": False,
            "raw_destination_retained": False,
            "normal_zero_exit_observed": True,
            "group_empty_before_exact_reap": True,
            "exact_reap_after_observation": True,
            "evidence_sha256": observation["evidence_sha256"],
            "parent_descriptors_unchanged": True,
        }
    finally:
        if not broker.consumed:
            broker.abort()


def _run_owner_bound_worker_ready_native_image_canary(
    *,
    spawn: Any,
    runtime_path: Path,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
    temporary_root: Path,
) -> dict[str, Any]:
    """Inventory a PID-free ready worker through its opaque native owner."""

    _close_descriptors_from_three()
    case_directory = temporary_root / "owner-bound-worker-ready-native-images"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before = snapshot_parent_descriptors()
    native_owner = spawn(
        os.fsencode(runtime_path),
        os.fsencode(_READY_WORKER),
        *_TARGET_FDS,
    )
    if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
        raise AssertionError("worker-ready image owner exposes transferable authority")
    with _OwnedCanaryChild(native_owner) as child:
        deadline = time.monotonic() + _WAIT_SECONDS
        while time.monotonic() < deadline:
            raw = paths["result"].read_bytes()
            if raw.endswith(b"\n"):
                break
            if len(raw) > 65_536:
                raise AssertionError("worker-ready result exceeded its bound")
            time.sleep(0.005)
        else:
            raise TimeoutError("worker-ready result was not written")
        ready = _read_single_json(paths["result"])
        if ready != {
            "schema": "sunofriend.native-owner-worker-ready-canary.v1",
            "phase": "fixed_native_modules_loaded",
            "native_modules": [
                "_bz2",
                "_ctypes",
                "_hashlib",
                "_lzma",
                "_sqlite3",
                "_ssl",
                "zlib",
            ],
            "pid_or_pgid_exported": False,
            "model_or_checkpoint_loaded": False,
            "audio_read": False,
            "network_used": False,
        }:
            raise AssertionError("owner-bound worker-ready report differs")
        process_image = native_owner.observe_owned_process_image(
            os.fsencode(runtime_path),
            os.fsencode(expected_process_image_path),
            expected_process_image_cdhash.encode("ascii"),
        )
        if process_image != {
            "kernel_cdhash": expected_process_image_cdhash,
            "path_state": "matched_expected_process_image",
        }:
            raise AssertionError("worker-ready process-image observation differs")
        first = _loaded_images._enumerate_owned_executable_regions(native_owner)
        time.sleep(0.02)
        second = _loaded_images._enumerate_owned_executable_regions(native_owner)
        if _loaded_images._snapshot_key(first) != _loaded_images._snapshot_key(
            second
        ):
            raise AssertionError("owner-bound executable-region snapshots differ")
        measured = _loaded_images._measure_mapped_files(
            second,
            process_image_path=expected_process_image_path,
        )
        artifacts = _loaded_images._path_free_artifacts(measured)
        file_backed = [region for region in second if region.path is not None]
        unpathed = [region for region in second if region.path is None]
        if sum(item["matches_process_image"] for item in artifacts) != 1:
            raise AssertionError("owned process image is not present exactly once")
        encoded_artifacts = json.dumps(
            artifacts,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        native_owner.signal_owned_group(signal.SIGKILL)
        status = child.wait()
    if not os.WIFSIGNALED(status) or os.WTERMSIG(status) != signal.SIGKILL:
        raise AssertionError("worker-ready image canary was not exactly terminated")
    _loaded_images._remeasure_mapped_files(measured)
    if (
        native_owner.leader_reaped is not True
        or native_owner.group_empty is not True
        or native_owner.ownership_released is not True
        or native_owner.ownership_lost is not False
    ):
        raise AssertionError("worker-ready image canary was not exact-reaped")
    after = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after)
    return {
        "pid_free_worker_ready_marker_observed": True,
        "native_owner_bound": True,
        "stable_consecutive_snapshots": True,
        "executable_region_count": len(second),
        "file_backed_executable_region_count": len(file_backed),
        "unpathed_executable_region_count": len(unpathed),
        "mapped_file_count": len(measured),
        "main_process_image_present_once": True,
        "mapped_artifact_manifest_sha256": hashlib.sha256(
            encoded_artifacts
        ).hexdigest(),
        "raw_pid_or_pgid_retained": False,
        "raw_executable_paths_retained": False,
        "model_or_checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
        "exact_reap_after_observation": True,
        "parent_descriptors_unchanged": True,
    }


def _run_combined_fixed_worker_bridge_canary(
    *,
    spawn: Any,
    owner_type: type[Any],
    runtime_path: Path,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
    native_artifact_sha256: str,
    native_source_sha256: str,
    native_build_contract_sha256: str,
    temporary_root: Path,
) -> dict[str, Any]:
    """Join every owner-bound observer and terminal projection in one run."""

    _close_descriptors_from_three()
    case_directory = temporary_root / "combined-fixed-worker-bridge"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before_observer = snapshot_parent_descriptors()
    worker_before = _measure_worker(_COMBINED_WORKER)
    runtime_before = _measure_runtime(runtime_path)
    process_image_before = _measure_runtime(expected_process_image_path)
    broker = _network_observer._prepare_owner_bound_network_observer()
    native_owner: Any | None = None
    try:
        observer_descriptors = snapshot_parent_descriptors()
        native_owner = spawn(
            os.fsencode(runtime_path),
            os.fsencode(_COMBINED_WORKER),
            *_TARGET_FDS,
        )
        if type(native_owner) is not owner_type:
            raise AssertionError("combined bridge owner type differs")
        if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
            raise AssertionError("combined bridge exposes transferable authority")
        with _OwnedCanaryChild(native_owner) as child:
            ready, ready_bytes = _wait_for_result_schema(
                paths["result"],
                schema="sunofriend.native-owner-combined-ready.v1",
                deadline=time.monotonic() + _WAIT_SECONDS,
            )
            if ready != {
                "schema": "sunofriend.native-owner-combined-ready.v1",
                "phase": "fixed_native_modules_loaded",
                "native_modules": [
                    "_bz2",
                    "_ctypes",
                    "_hashlib",
                    "_lzma",
                    "_sqlite3",
                    "_ssl",
                    "zlib",
                ],
                "pid_or_pgid_exported": False,
                "model_or_checkpoint_loaded": False,
                "audio_read": False,
                "network_used": False,
            }:
                raise AssertionError("combined bridge ready marker differs")
            ready_sha256 = hashlib.sha256(ready_bytes).hexdigest()
            process_image = native_owner.observe_owned_process_image(
                os.fsencode(runtime_path),
                os.fsencode(expected_process_image_path),
                expected_process_image_cdhash.encode("ascii"),
            )
            if process_image != {
                "kernel_cdhash": expected_process_image_cdhash,
                "path_state": "matched_expected_process_image",
            }:
                raise AssertionError("combined bridge process image differs")
            first = _loaded_images._enumerate_owned_executable_regions(native_owner)
            time.sleep(0.02)
            second = _loaded_images._enumerate_owned_executable_regions(native_owner)
            if _loaded_images._snapshot_key(first) != _loaded_images._snapshot_key(
                second
            ):
                raise AssertionError("combined bridge image snapshots differ")
            measured = _loaded_images._measure_mapped_files(
                second,
                process_image_path=expected_process_image_path,
            )
            artifacts = _loaded_images._path_free_artifacts(measured)
            encoded_artifacts = json.dumps(
                artifacts,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            mapped_manifest_sha256 = hashlib.sha256(encoded_artifacts).hexdigest()
            final, final_bytes = _wait_for_result_schema(
                paths["result"],
                schema="sunofriend.native-owner-combined-result.v1",
                deadline=time.monotonic() + _WAIT_SECONDS,
            )
            private_identity = final.pop("private_process_identity", None)
            if (
                not isinstance(private_identity, dict)
                or set(private_identity) != {"pid", "pgid"}
                or type(private_identity["pid"]) is not int
                or type(private_identity["pgid"]) is not int
            ):
                raise AssertionError("combined bridge private identity differs")
            if final != {
                "schema": "sunofriend.native-owner-combined-result.v1",
                "ok": True,
                "ready_sha256": ready_sha256,
                "connect_errno_name": "EPERM",
                "loopback_only": True,
                "external_destination_contacted": False,
                "open_descriptors": [0, 1, 2, 3, 4, 5],
                "native_modules": ready["native_modules"],
                "model_or_checkpoint_loaded": False,
                "audio_read": False,
            }:
                raise AssertionError("combined bridge final result differs")
            del final_bytes
            redacted_worker_result_bytes = (
                json.dumps(
                    final,
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            worker_result_sha256 = hashlib.sha256(
                redacted_worker_result_bytes
            ).hexdigest()
            network_observation = broker.finish(native_owner=native_owner)
            if broker.consumed is not True:
                raise AssertionError("combined bridge network broker was not consumed")
            status = child.wait()
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise AssertionError("combined fixed worker did not exit normally")
        _loaded_images._remeasure_mapped_files(measured)
        if (
            native_owner.leader_exit_observed is not True
            or native_owner.leader_reaped is not True
            or native_owner.group_empty is not True
            or native_owner.ownership_released is not True
            or native_owner.ownership_lost is not False
        ):
            raise AssertionError("combined bridge lacks exact terminal ownership")
        worker_after = _measure_worker(_COMBINED_WORKER)
        runtime_after = _measure_runtime(runtime_path)
        process_image_after = _measure_runtime(expected_process_image_path)
        if worker_after != worker_before:
            raise AssertionError("combined fixed worker changed across execution")
        if runtime_after != runtime_before:
            raise AssertionError("combined bridge runtime changed across execution")
        if process_image_after != process_image_before:
            raise AssertionError("combined bridge process image changed")

        session_payload = {
            "native_artifact_sha256": native_artifact_sha256,
            "native_source_sha256": native_source_sha256,
            "native_build_contract_sha256": native_build_contract_sha256,
            "runtime_sha256": runtime_after.sha256,
            "process_image_sha256": process_image_after.sha256,
            "fixed_worker_sha256": worker_after.sha256,
            "ready_sha256": ready_sha256,
        }
        native_session_sha256 = hashlib.sha256(
            json.dumps(
                session_payload,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        ).hexdigest()
        execution_payload = {
            "process_image": process_image,
            "network_observation_sha256": network_observation["evidence_sha256"],
            "mapped_artifact_manifest_sha256": mapped_manifest_sha256,
            "worker_result_sha256": worker_result_sha256,
            "wait": {
                "kind": "exited",
                "exit_code": 0,
                "signal": None,
                "core_dumped": False,
            },
            "group_empty": True,
            "exact_reap": True,
        }
        native_execution_sha256 = hashlib.sha256(
            json.dumps(
                execution_payload,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        ).hexdigest()
        projection = _supervision._derive_model_free_native_terminal_projection(
            native_owner=native_owner,
            expected_owner_type=owner_type,
            native_session_observation_sha256=native_session_sha256,
            native_execution_observation_sha256=native_execution_sha256,
            worker_result_sha256=worker_result_sha256,
            worker_reported_pid=private_identity["pid"],
            worker_reported_pgid=private_identity["pgid"],
        )
        if network_observation["observation"][
            "deliberate_canary_denial_count"
        ] < 1:
            raise AssertionError("combined bridge network canary was absent")
        after = snapshot_parent_descriptors()
        _assert_parent_unchanged(before_observer, after)
        encoded_projection = json.dumps(
            _supervision._plain(projection),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if '"pid":' in encoded_projection or '"pgid":' in encoded_projection:
            raise AssertionError("combined terminal projection retained authority")
        return {
            "observer_ready_before_native_spawn": (
                len(observer_descriptors) > len(before_observer)
            ),
            "pid_free_ready_marker_observed": True,
            "process_image_matched": True,
            "stable_consecutive_executable_region_snapshots": True,
            "mapped_artifact_manifest_sha256": mapped_manifest_sha256,
            "deliberate_network_denial_observed": True,
            "other_owned_network_denial_count": network_observation[
                "observation"
            ]["other_target_network_denial_count"],
            "network_observation_sha256": network_observation["evidence_sha256"],
            "worker_result_sha256": worker_result_sha256,
            "terminal_projection": _supervision._plain(projection),
            "raw_pid_or_pgid_retained": False,
            "raw_executable_paths_retained": False,
            "raw_network_destination_retained": False,
            "model_or_checkpoint_loaded": False,
            "audio_read": False,
            "normal_zero_exit_observed": True,
            "group_empty_before_exact_reap": True,
            "exact_reap_observed": True,
            "parent_descriptors_unchanged": True,
        }
    finally:
        if not broker.consumed:
            broker.abort()


def _bootstrap_digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _build_model_free_native_request(
    *,
    case_directory: Path,
    worker_sha256: str,
) -> Any:
    private_paths = {
        "repository_root": str(case_directory / "repository-root"),
        "source_root": str(case_directory / "source-root"),
        "checkpoint_path": str(case_directory / "checkpoint.safetensors"),
        "companion_root": str(case_directory / "companion-root"),
        "authorisation_report_path": str(case_directory / "authorisation.json"),
        "staging_directory": str(case_directory),
    }
    identities = {
        "worker_source_sha256": worker_sha256,
        "checkpoint_sha256": _melroformer_evidence.CONVERSION_CHECKPOINT_SHA256,
        "checkpoint_bytes": _melroformer_evidence.CONVERSION_CHECKPOINT_BYTES,
        "authorisation_report_sha256": _bootstrap_digest(
            "model-free-native-bootstrap-authorisation"
        ),
        "source_manifest_sha256": _bootstrap_digest(
            "model-free-native-bootstrap-source"
        ),
        "companion_manifest_sha256": _bootstrap_digest(
            "model-free-native-bootstrap-companions"
        ),
    }
    return _native_transport._build_private_melroformer_native_request(
        run_nonce=os.urandom(32).hex(),
        paths=private_paths,
        identities=identities,
        device="cpu",
    )


def _wait_for_private_native_result_frame(
    path: Path,
    *,
    request: Any,
    deadline: float,
) -> Any:
    while time.monotonic() < deadline:
        raw = path.read_bytes()
        if len(raw) > _native_transport.RESULT_MAXIMUM_BYTES:
            raise AssertionError("native bootstrap result exceeded its bound")
        if raw:
            try:
                return _native_transport._decode_private_melroformer_native_result(
                    raw,
                    request=request,
                )
            except ValueError:
                pass
        time.sleep(0.005)
    raise TimeoutError("native bootstrap result frame was not written")


def _run_invalid_native_frame_bootstrap_canary(
    *,
    spawn: Any,
    owner_type: type[Any],
    runtime_path: Path,
    temporary_root: Path,
    worker_sha256: str,
) -> dict[str, Any]:
    cases = []
    for case_name in ("trailing_frame_byte", "tampered_request_hash"):
        _close_descriptors_from_three()
        case_directory = temporary_root / f"native-frame-bootstrap-{case_name}"
        case_directory.mkdir(mode=0o700)
        request = _build_model_free_native_request(
            case_directory=case_directory,
            worker_sha256=worker_sha256,
        )
        frame = _native_transport._encode_private_melroformer_native_request(
            request
        )
        if case_name == "trailing_frame_byte":
            invalid_frame = frame + b"x"
        else:
            request_value = _ready_handshake._plain(request)
            request_value["request_sha256"] = "f" * 64
            payload = json.dumps(
                request_value,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            invalid_frame = (
                _native_transport.REQUEST_MAGIC
                + len(payload).to_bytes(8, "big")
                + payload
            )
        paths = _install_transport_descriptors(
            case_directory,
            _TARGET_FDS,
            request_bytes=invalid_frame,
        )
        baseline = snapshot_parent_descriptors()
        prepared = _ready_handshake._prepare_worker_ready_handshake()
        native_owner: Any | None = None
        try:
            before_spawn = snapshot_parent_descriptors()
            native_owner = spawn(
                os.fsencode(runtime_path),
                os.fsencode(_FRAME_BOOTSTRAP_WORKER),
                *_TARGET_FDS,
                prepared.ready_write_fd,
                prepared.release_read_fd,
            )
            if type(native_owner) is not owner_type:
                raise AssertionError("invalid-frame native owner type differs")
            _assert_parent_unchanged(
                before_spawn,
                snapshot_parent_descriptors(),
            )
            with _OwnedCanaryChild(native_owner) as child:
                try:
                    _ready_handshake._read_worker_ready_handshake(
                        prepared,
                        timeout_seconds=_WAIT_SECONDS,
                    )
                except RuntimeError:
                    rejected_before_ready = True
                else:
                    raise AssertionError("invalid request reached worker readiness")
                status = child.wait()
            if not os.WIFEXITED(status) or os.WEXITSTATUS(status) == 0:
                raise AssertionError("invalid request did not fail closed")
            if paths["result"].read_bytes() != b"":
                raise AssertionError("invalid request produced a result frame")
            if (
                native_owner.leader_exit_observed is not True
                or native_owner.leader_reaped is not True
                or native_owner.group_empty is not True
                or native_owner.ownership_released is not True
                or native_owner.ownership_lost is not False
            ):
                raise AssertionError("invalid-frame owner terminality differs")
            cases.append(
                {
                    "case": case_name,
                    "rejected_before_ready": rejected_before_ready,
                    "result_frame_written": False,
                    "normal_zero_exit_observed": False,
                    "group_empty_before_exact_reap": True,
                    "exact_reap_observed": True,
                }
            )
        finally:
            _ready_handshake._abort_worker_ready_handshake(prepared)
        _assert_parent_unchanged(baseline, snapshot_parent_descriptors())
    return {
        "case_count": len(cases),
        "all_invalid_requests_rejected_before_ready": all(
            case["rejected_before_ready"] for case in cases
        ),
        "no_result_frame_written": all(
            case["result_frame_written"] is False for case in cases
        ),
        "all_owned_groups_drained_and_exact_reaped": all(
            case["group_empty_before_exact_reap"]
            and case["exact_reap_observed"]
            for case in cases
        ),
        "raw_pid_or_pgid_retained": False,
        "cases": cases,
    }


def _run_native_frame_bootstrap_canary(
    *,
    spawn: Any,
    owner_type: type[Any],
    runtime_path: Path,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
    temporary_root: Path,
    worker_sha256: str,
    sandboxed: bool = False,
) -> dict[str, Any]:
    """Consume fd3/fd4 frames under one opaque native owner, model-free."""

    _close_descriptors_from_three()
    case_directory = temporary_root / (
        "native-sandbox-frame-bootstrap-valid"
        if sandboxed
        else "native-frame-bootstrap-valid"
    )
    case_directory.mkdir(mode=0o700)
    request = _build_model_free_native_request(
        case_directory=case_directory,
        worker_sha256=worker_sha256,
    )
    request_frame = _native_transport._encode_private_melroformer_native_request(
        request
    )
    paths = _install_transport_descriptors(
        case_directory,
        _TARGET_FDS,
        request_bytes=request_frame,
    )
    baseline = snapshot_parent_descriptors()
    prepared = _ready_handshake._prepare_worker_ready_handshake()
    native_owner: Any | None = None
    retained: dict[str, Any] | None = None
    try:
        before_spawn = snapshot_parent_descriptors()
        spawn_arguments = (
            (
                os.fsencode(_SANDBOX_EXEC),
                os.fsencode(runtime_path),
                os.fsencode(_FRAME_BOOTSTRAP_WORKER),
                os.fsencode(case_directory),
                *_TARGET_FDS,
                prepared.ready_write_fd,
                prepared.release_read_fd,
            )
            if sandboxed
            else (
                os.fsencode(runtime_path),
                os.fsencode(_FRAME_BOOTSTRAP_WORKER),
                *_TARGET_FDS,
                prepared.ready_write_fd,
                prepared.release_read_fd,
            )
        )
        native_owner = spawn(*spawn_arguments)
        if type(native_owner) is not owner_type:
            raise AssertionError("frame-bootstrap native owner type differs")
        if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
            raise AssertionError("frame-bootstrap owner exposes authority")
        _assert_parent_unchanged(before_spawn, snapshot_parent_descriptors())
        with _OwnedCanaryChild(native_owner) as child:
            ready = _ready_handshake._read_worker_ready_handshake(
                prepared,
                timeout_seconds=_WAIT_SECONDS,
            )
            if native_owner.wait_nohang() is not None:
                raise AssertionError("frame bootstrap did not block for release")
            process_image = native_owner.observe_owned_process_image(
                os.fsencode(runtime_path),
                os.fsencode(expected_process_image_path),
                expected_process_image_cdhash.encode("ascii"),
            )
            if process_image != {
                "kernel_cdhash": expected_process_image_cdhash,
                "path_state": "matched_expected_process_image",
            }:
                raise AssertionError("frame-bootstrap process image differs")
            _ready_handshake._release_worker_ready_handshake(prepared)
            result = _wait_for_private_native_result_frame(
                paths["result"],
                request=request,
                deadline=time.monotonic() + _WAIT_SECONDS,
            )
            private_identity = result["private_process_identity"]
            if not native_owner.matches_pid_and_pgid(
                private_identity["pid"],
                private_identity["pgid"],
            ):
                raise AssertionError("frame-bootstrap private identity differs")
            child_result = _ready_handshake._plain(result["child_result"])
            expected_child = {
                "schema": (
                    "sunofriend.private-melroformer-native-"
                    "sandbox-bootstrap-child.v1"
                    if sandboxed
                    else "sunofriend.private-melroformer-"
                    "native-bootstrap-child.v1"
                ),
                "status": (
                    "model_free_native_sandbox_bootstrap_complete"
                    if sandboxed
                    else "model_free_frame_bootstrap_complete"
                ),
                "request_frame_validated": True,
                "request_paths_opened": False,
                "request_paths_retained": False,
                "checkpoint_descriptor_regular": True,
                "checkpoint_descriptor_bytes_read": 0,
                "ready_release_completed": True,
                "ready_sha256": hashlib.sha256(
                    json.dumps(
                        _ready_handshake._plain(ready),
                        ensure_ascii=True,
                        allow_nan=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("ascii")
                    + b"\n"
                ).hexdigest(),
                "release_sha256": hashlib.sha256(
                    _ready_handshake._RELEASE_BYTES
                ).hexdigest(),
                "open_descriptors_after_handshake": [0, 1, 2, 3, 4, 5],
                "model_imported": False,
                "checkpoint_loaded": False,
                "audio_read": False,
                "network_used": False,
                "product_authority_granted": False,
            }
            if sandboxed:
                expected_child["sandbox_canaries"] = {
                    "network_connect_errno": errno.EPERM,
                    "network_errno_name": "EPERM",
                    "process_fork_errno": errno.EPERM,
                    "process_fork_errno_name": "EPERM",
                    "outside_write_errno": errno.EPERM,
                    "outside_write_errno_name": "EPERM",
                    "fixed_sandbox_environment_observed": True,
                }
            if child_result != expected_child:
                raise AssertionError("frame-bootstrap child result differs")
            result_sha256 = result["result_sha256"]
            child_result_sha256 = result["child_result_sha256"]
            del private_identity, result
            status = child.wait()
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise AssertionError("frame-bootstrap worker did not exit zero")
        if (
            native_owner.leader_exit_observed is not True
            or native_owner.leader_reaped is not True
            or native_owner.group_empty is not True
            or native_owner.ownership_released is not True
            or native_owner.ownership_lost is not False
        ):
            raise AssertionError("frame-bootstrap owner terminality differs")
        retained = {
            "request_frame_validated_by_worker": True,
            "result_frame_validated_by_parent": True,
            "request_sha256": request["request_sha256"],
            "result_sha256": result_sha256,
            "child_result_sha256": child_result_sha256,
            "private_process_identity_matched_then_discarded": True,
            "worker_blocked_until_parent_release": True,
            "process_image_matched_while_blocked": True,
            "request_paths_opened": False,
            "request_paths_retained": False,
            "checkpoint_descriptor_bytes_read": 0,
            "model_or_checkpoint_loaded": False,
            "audio_read": False,
            "network_used": False,
            "normal_zero_exit_after_release": True,
            "group_empty_before_exact_reap": True,
            "exact_reap_observed": True,
            "raw_pid_or_pgid_retained": False,
            "fixed_native_sandbox_launch_shape": sandboxed,
            "network_fork_and_outside_write_denied": sandboxed,
        }
    finally:
        _ready_handshake._abort_worker_ready_handshake(prepared)
    _assert_parent_unchanged(baseline, snapshot_parent_descriptors())
    if retained is None:
        raise AssertionError("frame-bootstrap evidence was not retained")
    retained["parent_descriptors_unchanged_by_spawn"] = True
    retained["temporary_pipe_descriptors_closed"] = True
    return retained


def _run_native_ready_release_transport_canary(
    *,
    spawn: Any,
    owner_type: type[Any],
    runtime_path: Path,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
    temporary_root: Path,
) -> dict[str, Any]:
    """Exercise the exact Kim ready/release pipes through one native owner."""

    _close_descriptors_from_three()
    case_directory = temporary_root / "native-ready-release-transport"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    baseline = snapshot_parent_descriptors()
    invalid_prepared = _ready_handshake._prepare_worker_ready_handshake()
    try:
        try:
            spawn(
                os.fsencode(runtime_path),
                os.fsencode(_READY_RELEASE_WORKER),
                *_TARGET_FDS,
                invalid_prepared.release_read_fd,
                invalid_prepared.ready_write_fd,
            )
        except ValueError:
            wrong_pipe_access_rejected_before_spawn = True
        else:
            raise AssertionError("swapped ready/release access was accepted")
    finally:
        _ready_handshake._abort_worker_ready_handshake(invalid_prepared)
    _assert_parent_unchanged(baseline, snapshot_parent_descriptors())
    prepared = _ready_handshake._prepare_worker_ready_handshake()
    native_owner: Any | None = None
    try:
        before_spawn = snapshot_parent_descriptors()
        native_owner = spawn(
            os.fsencode(runtime_path),
            os.fsencode(_READY_RELEASE_WORKER),
            *_TARGET_FDS,
            prepared.ready_write_fd,
            prepared.release_read_fd,
        )
        if type(native_owner) is not owner_type:
            raise AssertionError("ready/release native owner type differs")
        if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
            raise AssertionError("ready/release owner exposes transferable authority")
        after_spawn = snapshot_parent_descriptors()
        _assert_parent_unchanged(before_spawn, after_spawn)
        with _OwnedCanaryChild(native_owner) as child:
            ready = _ready_handshake._read_worker_ready_handshake(
                prepared,
                timeout_seconds=_WAIT_SECONDS,
            )
            if native_owner.wait_nohang() is not None:
                raise AssertionError("ready/release worker did not block for release")
            process_image = native_owner.observe_owned_process_image(
                os.fsencode(runtime_path),
                os.fsencode(expected_process_image_path),
                expected_process_image_cdhash.encode("ascii"),
            )
            if process_image != {
                "kernel_cdhash": expected_process_image_cdhash,
                "path_state": "matched_expected_process_image",
            }:
                raise AssertionError("ready/release process image differs")
            _ready_handshake._release_worker_ready_handshake(prepared)
            status = child.wait()
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise AssertionError("ready/release worker did not exit zero")
        if (
            native_owner.leader_exit_observed is not True
            or native_owner.leader_reaped is not True
            or native_owner.group_empty is not True
            or native_owner.ownership_released is not True
            or native_owner.ownership_lost is not False
        ):
            raise AssertionError("ready/release owner terminality differs")
        ready_document = _ready_handshake._plain(ready)
        ready_bytes = (
            json.dumps(
                ready_document,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        result = _read_single_json(paths["result"])
        if result != {
            "schema": "sunofriend.native-owner-ready-release-result.v1",
            "ok": True,
            "ready_sha256": hashlib.sha256(ready_bytes).hexdigest(),
            "release_sha256": hashlib.sha256(
                _ready_handshake._RELEASE_BYTES
            ).hexdigest(),
            "open_descriptors_after_handshake": [0, 1, 2, 3, 4, 5],
            "pid_or_pgid_exported": False,
            "model_or_checkpoint_loaded": False,
            "audio_read": False,
            "network_used": False,
        }:
            raise AssertionError("ready/release worker result differs")
        final = snapshot_parent_descriptors()
        _assert_parent_unchanged(baseline, final)
        return {
            "fixed_descriptor_targets": [3, 4, 5, 6, 7],
            "wrong_pipe_access_rejected_before_spawn": (
                wrong_pipe_access_rejected_before_spawn
            ),
            "existing_kim_ready_schema_validated": True,
            "worker_blocked_until_parent_release": True,
            "process_image_matched_while_blocked": True,
            "normal_zero_exit_after_release": True,
            "group_empty_before_exact_reap": True,
            "exact_reap_observed": True,
            "parent_descriptors_unchanged_by_spawn": True,
            "temporary_pipe_descriptors_closed": True,
            "raw_pid_or_pgid_retained": False,
            "model_or_checkpoint_loaded": False,
            "audio_read": False,
            "network_used": False,
        }
    finally:
        _ready_handshake._abort_worker_ready_handshake(prepared)


def _run_descendant_group_canary(
    *,
    spawn: Any,
    runtime_path: Path,
    temporary_root: Path,
) -> dict[str, Any]:
    _close_descriptors_from_three()
    case_directory = temporary_root / "descendant-group"
    case_directory.mkdir(mode=0o700)
    paths = _install_transport_descriptors(case_directory, _TARGET_FDS)
    before = snapshot_parent_descriptors()
    native_owner = spawn(
        os.fsencode(runtime_path),
        os.fsencode(_DESCENDANT_WORKER),
        *_TARGET_FDS,
    )
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        raw = paths["result"].read_bytes()
        if raw.endswith(b"\n"):
            break
        if len(raw) > 65_536:
            raise AssertionError("descendant canary result exceeded its bound")
        time.sleep(0.005)
    else:
        raise TimeoutError("descendant canary result was not written")
    report = _read_single_json(paths["result"])
    if (
        report.get("schema")
        != "sunofriend.native-spawn-descendant-canary.v1"
        or report.get("ok") is not True
        or report.get("descendant_started") is not True
        or not native_owner.matches_pid_and_pgid(
            report.get("pid"), report.get("pgid")
        )
    ):
        raise AssertionError("descendant canary worker report is invalid")
    if report.get("request_sha256") != hashlib.sha256(_REQUEST_BYTES).hexdigest():
        raise AssertionError("descendant canary request identity differs")
    if report.get("checkpoint_sha256") != hashlib.sha256(
        _CHECKPOINT_BYTES
    ).hexdigest():
        raise AssertionError("descendant canary checkpoint identity differs")

    while time.monotonic() < deadline:
        if native_owner.wait_nohang() is not None:
            raise AssertionError("native owner reaped before its group was empty")
        if native_owner.leader_exit_observed:
            break
        time.sleep(0.005)
    else:
        raise TimeoutError("native owner did not observe descendant leader exit")
    if (
        native_owner.leader_reaped is not False
        or native_owner.group_empty is not False
        or native_owner.ownership_released is not False
        or native_owner.ownership_lost is not False
    ):
        raise AssertionError("native owner released a live descendant group")

    native_owner.signal_owned_group(signal.SIGKILL)
    status = None
    while time.monotonic() < deadline:
        status = native_owner.wait_nohang()
        if status is not None:
            break
        time.sleep(0.005)
    if status is None:
        raise TimeoutError("native owner did not drain its descendant group")
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError("descendant canary leader exit status differs")
    if (
        native_owner.leader_exit_observed is not True
        or native_owner.leader_reaped is not True
        or native_owner.group_empty is not True
        or native_owner.ownership_released is not True
        or native_owner.ownership_lost is not False
    ):
        raise AssertionError("native descendant group did not become terminal")
    after = snapshot_parent_descriptors()
    _assert_parent_unchanged(before, after)
    return {
        "leader_exit_observed_without_reap": True,
        "live_descendant_prevented_ownership_release": True,
        "whole_owned_group_signalled": True,
        "group_empty_before_exact_leader_reap": True,
        "leader_exact_reaped": True,
        "ownership_released_only_after_group_empty": True,
        "raw_pid_or_pgid_retained": False,
        "parent_descriptors_unchanged": True,
    }


def run_canary_matrix(
    *,
    extension_path: Path,
    temporary_root: Path,
    expected_artifact_sha256: str,
    expected_source_sha256: str,
    expected_build_contract_sha256: str,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
) -> dict[str, Any]:
    outer_supervisor_descriptors = _observe_outer_supervisor_descriptors()
    if outer_supervisor_descriptors["only_standard_descriptors_open"] is not True:
        raise RuntimeError("outer supervisor leaked a descriptor into the harness")
    original_soft_limit = _prepare_isolated_descriptor_limit()
    extension, artifact = _load_verified_extension(
        extension_path,
        expected_artifact_sha256=expected_artifact_sha256,
        expected_source_sha256=expected_source_sha256,
        expected_build_contract_sha256=expected_build_contract_sha256,
    )
    runtime_path = Path(sys.executable).resolve(strict=True)
    expected_process_image_path = expected_process_image_path.resolve(strict=True)
    if not _CDHASH_RE.fullmatch(expected_process_image_cdhash):
        raise ValueError("expected process-image CDHash is invalid")
    worker_path = _WORKER.resolve(strict=True)
    runtime_before = _measure_runtime(runtime_path)
    process_image_before = _measure_runtime(expected_process_image_path)
    sandbox_provider_before = _measure_runtime(_SANDBOX_EXEC)
    worker_before = _measure_worker(worker_path)
    hold_worker_before = _measure_worker(_HOLD_WORKER)
    descendant_worker_before = _measure_worker(_DESCENDANT_WORKER)
    network_worker_before = _measure_worker(_NETWORK_WORKER)
    ready_worker_before = _measure_worker(_READY_WORKER)
    combined_worker_before = _measure_worker(_COMBINED_WORKER)
    ready_release_worker_before = _measure_worker(_READY_RELEASE_WORKER)
    frame_bootstrap_worker_before = _measure_worker(_FRAME_BOOTSTRAP_WORKER)
    spawn = getattr(extension, _METHOD_NAME, None)
    if not callable(spawn):
        raise RuntimeError("native extension entry point is unavailable")
    spawn_with_ready_release = getattr(
        extension,
        "_spawn_bound_fake_worker_with_ready_release",
        None,
    )
    if not callable(spawn_with_ready_release):
        raise RuntimeError("native ready/release entry point is unavailable")
    spawn_private_melroformer = getattr(
        extension,
        "_spawn_bound_private_melroformer_worker",
        None,
    )
    if not callable(spawn_private_melroformer):
        raise RuntimeError("native private Kim sandbox entry point is unavailable")
    owner_type = getattr(extension, "_OwnedSpawnChild", None)
    if not isinstance(owner_type, type):
        raise RuntimeError("native owner type is unavailable")
    try:
        owner_type()
    except TypeError:
        direct_owner_construction_rejected = True
    else:
        raise RuntimeError("native owner type is publicly constructible")
    null_identity = _null_device_identity()
    cases: list[dict[str, Any]] = []
    for index, (layout_class, source_fds) in enumerate(
        _source_fd_layouts(),
        start=1,
    ):
        _close_descriptors_from_three()
        case_directory = temporary_root / f"case-{index}"
        case_directory.mkdir(mode=0o700)
        paths = _install_transport_descriptors(case_directory, source_fds)
        low_canary_fds = _canary_fds_for_source_layout(source_fds)
        _install_unrelated_inheritable_canaries(
            case_directory,
            low_canary_fds=low_canary_fds,
        )
        before = snapshot_parent_descriptors()
        _assert_canaries_present_in_parent(
            before,
            source_fds=source_fds,
            low_canary_fds=low_canary_fds,
        )
        native_owner = spawn(
            os.fsencode(runtime_path),
            os.fsencode(worker_path),
            *source_fds,
        )
        if (
            native_owner.leader_exit_observed is not False
            or native_owner.leader_reaped is not False
            or native_owner.group_empty is not False
            or native_owner.ownership_released is not False
            or native_owner.ownership_lost is not False
        ):
            raise AssertionError("native launcher returned a released owner")
        with _OwnedCanaryChild(native_owner) as child:
            after_spawn = snapshot_parent_descriptors()
            _assert_parent_unchanged(before, after_spawn)
            status = child.wait()
            if native_owner.wait_nohang() != status:
                raise AssertionError("native owner cached wait status changed")
            try:
                native_owner.signal_owned_group(signal.SIGKILL)
            except RuntimeError:
                post_reap_signal_rejected = True
            else:
                post_reap_signal_rejected = False
            if not post_reap_signal_rejected:
                raise AssertionError("native owner signalled after exact reap")
            after_reap = snapshot_parent_descriptors()
            _assert_parent_unchanged(before, after_reap)
            if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
                raise AssertionError("canary child did not exit successfully")
            report = _read_single_json(paths["result"])
            _assert_worker_report(
                report,
                native_owner=native_owner,
                null_identity=null_identity,
            )
            cases.append(
                {
                    "layout_class": layout_class,
                    "source_fds": list(source_fds),
                    "unrelated_low_canary_fds": list(low_canary_fds),
                    "native_owner_pid_pgid_match_observed": True,
                    "open_descriptors": report["open_descriptors"],
                    "native_owner_leader_exit_observed": (
                        native_owner.leader_exit_observed
                    ),
                    "native_owner_leader_reaped": (native_owner.leader_reaped),
                    "native_owner_group_empty": native_owner.group_empty,
                    "native_owner_ownership_released": (
                        native_owner.ownership_released
                    ),
                    "native_owner_ownership_lost": (native_owner.ownership_lost),
                    "native_owner_cached_wait_stable": True,
                    "native_owner_post_reap_signal_rejected": True,
                    "native_owner_normal_exit_observed": True,
                    "native_owner_signal_termination_observed": False,
                    "native_owner_exit_status_zero": True,
                    "post_cpython_signal_state_observed": True,
                    "parent_offsets_unchanged_after_spawn": True,
                    "parent_offsets_unchanged_after_reap": True,
                }
            )
    owner_drop_canary = _run_owner_drop_canary(
        spawn=spawn,
        runtime_path=runtime_path,
        temporary_root=temporary_root,
    )
    external_reap_poison_canary = _run_external_reap_poison_canary(
        spawn=spawn,
        runtime_path=runtime_path,
        temporary_root=temporary_root,
    )
    owner_bound_process_image_canary = _run_owner_bound_process_image_canary(
        spawn=spawn,
        runtime_path=runtime_path,
        expected_process_image_path=expected_process_image_path,
        expected_process_image_cdhash=expected_process_image_cdhash,
        temporary_root=temporary_root,
    )
    owner_bound_network_canary = _run_owner_bound_network_canary(
        spawn=spawn,
        runtime_path=runtime_path,
        temporary_root=temporary_root,
    )
    owner_bound_worker_ready_native_image_canary = (
        _run_owner_bound_worker_ready_native_image_canary(
            spawn=spawn,
            runtime_path=runtime_path,
            expected_process_image_path=expected_process_image_path,
            expected_process_image_cdhash=expected_process_image_cdhash,
            temporary_root=temporary_root,
        )
    )
    combined_fixed_worker_bridge_canary = (
        _run_combined_fixed_worker_bridge_canary(
            spawn=spawn,
            owner_type=owner_type,
            runtime_path=runtime_path,
            expected_process_image_path=expected_process_image_path,
            expected_process_image_cdhash=expected_process_image_cdhash,
            native_artifact_sha256=artifact.sha256,
            native_source_sha256=expected_source_sha256,
            native_build_contract_sha256=expected_build_contract_sha256,
            temporary_root=temporary_root,
        )
    )
    native_ready_release_transport_canary = (
        _run_native_ready_release_transport_canary(
            spawn=spawn_with_ready_release,
            owner_type=owner_type,
            runtime_path=runtime_path,
            expected_process_image_path=expected_process_image_path,
            expected_process_image_cdhash=expected_process_image_cdhash,
            temporary_root=temporary_root,
        )
    )
    invalid_native_frame_bootstrap_canary = (
        _run_invalid_native_frame_bootstrap_canary(
            spawn=spawn_with_ready_release,
            owner_type=owner_type,
            runtime_path=runtime_path,
            temporary_root=temporary_root,
            worker_sha256=frame_bootstrap_worker_before.sha256,
        )
    )
    native_frame_bootstrap_canary = _run_native_frame_bootstrap_canary(
        spawn=spawn_with_ready_release,
        owner_type=owner_type,
        runtime_path=runtime_path,
        expected_process_image_path=expected_process_image_path,
        expected_process_image_cdhash=expected_process_image_cdhash,
        temporary_root=temporary_root,
        worker_sha256=frame_bootstrap_worker_before.sha256,
    )
    native_sandbox_frame_bootstrap_canary = _run_native_frame_bootstrap_canary(
        spawn=spawn_private_melroformer,
        owner_type=owner_type,
        runtime_path=runtime_path,
        expected_process_image_path=expected_process_image_path,
        expected_process_image_cdhash=expected_process_image_cdhash,
        temporary_root=temporary_root,
        worker_sha256=frame_bootstrap_worker_before.sha256,
        sandboxed=True,
    )
    descendant_group_canary = _run_descendant_group_canary(
        spawn=spawn,
        runtime_path=runtime_path,
        temporary_root=temporary_root,
    )
    runtime_after = _measure_runtime(runtime_path)
    process_image_after = _measure_runtime(expected_process_image_path)
    sandbox_provider_after = _measure_runtime(_SANDBOX_EXEC)
    worker_after = _measure_worker(worker_path)
    hold_worker_after = _measure_worker(_HOLD_WORKER)
    descendant_worker_after = _measure_worker(_DESCENDANT_WORKER)
    network_worker_after = _measure_worker(_NETWORK_WORKER)
    ready_worker_after = _measure_worker(_READY_WORKER)
    combined_worker_after = _measure_worker(_COMBINED_WORKER)
    ready_release_worker_after = _measure_worker(_READY_RELEASE_WORKER)
    frame_bootstrap_worker_after = _measure_worker(_FRAME_BOOTSTRAP_WORKER)
    if runtime_after != runtime_before:
        raise RuntimeError("bound runtime changed across canary matrix")
    if process_image_after != process_image_before:
        raise RuntimeError("bound runtime process image changed across canary matrix")
    if sandbox_provider_after != sandbox_provider_before:
        raise RuntimeError("bound sandbox provider changed across canary matrix")
    if worker_after != worker_before:
        raise RuntimeError("bound worker changed across canary matrix")
    if hold_worker_after != hold_worker_before:
        raise RuntimeError("bound hold worker changed across canary matrix")
    if descendant_worker_after != descendant_worker_before:
        raise RuntimeError("bound descendant worker changed across canary matrix")
    if network_worker_after != network_worker_before:
        raise RuntimeError("bound network worker changed across canary matrix")
    if ready_worker_after != ready_worker_before:
        raise RuntimeError("bound worker-ready worker changed across canary matrix")
    if combined_worker_after != combined_worker_before:
        raise RuntimeError("bound combined worker changed across canary matrix")
    if ready_release_worker_after != ready_release_worker_before:
        raise RuntimeError("bound ready/release worker changed across canary matrix")
    if frame_bootstrap_worker_after != frame_bootstrap_worker_before:
        raise RuntimeError("bound frame-bootstrap worker changed across canary matrix")
    expected_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    return {
        "schema": "sunofriend.native-spawn-canary-matrix.v10",
        "extension_path_serialized": False,
        "worker_path_serialized": False,
        "proof_scope": (
            "exact_host_toolchain_python_abi_canary_not_portable_execution_authority"
        ),
        "artifact_sha256": artifact.sha256,
        "native_artifact_identity": _path_free_file_identity(artifact),
        "extension_loader": {
            "kind": "ExtensionFileLoader",
            "module_name": _MODULE_NAME,
            "module_spec_name": _MODULE_NAME,
            "expected_suffix": expected_suffix,
            "identity_checks_passed": True,
        },
        "native_source_sha256": expected_source_sha256,
        "native_build_contract_sha256": expected_build_contract_sha256,
        "runtime_executable_identity": _path_free_file_identity(runtime_after),
        "runtime_process_image_identity": _path_free_file_identity(
            process_image_after
        ),
        "fixed_sandbox_provider_identity": _path_free_file_identity(
            sandbox_provider_after
        ),
        "fixed_worker_identity": _path_free_file_identity(worker_after),
        "fixed_hold_worker_identity": _path_free_file_identity(hold_worker_after),
        "fixed_descendant_worker_identity": _path_free_file_identity(
            descendant_worker_after
        ),
        "fixed_network_worker_identity": _path_free_file_identity(
            network_worker_after
        ),
        "fixed_ready_worker_identity": _path_free_file_identity(
            ready_worker_after
        ),
        "fixed_combined_worker_identity": _path_free_file_identity(
            combined_worker_after
        ),
        "fixed_ready_release_worker_identity": _path_free_file_identity(
            ready_release_worker_after
        ),
        "fixed_frame_bootstrap_worker_identity": _path_free_file_identity(
            frame_bootstrap_worker_after
        ),
        "native_owner_type_qualification": {
            "direct_construction_rejected": direct_owner_construction_rejected,
            "raw_pid_not_exposed": True,
            "copy_and_pickle_rejected": True,
            "fork_clone_destructor_guard_present": True,
            "owner_bound_process_image_observer_present": True,
            "owner_bound_network_observation_broker_present": True,
            "network_broker_single_use": True,
            "owner_bound_worker_ready_native_image_observer_present": True,
            "combined_fixed_worker_bridge_present": True,
            "model_free_terminal_projection_from_live_owner_present": True,
            "fixed_native_ready_release_transport_present": True,
            "existing_kim_ready_schema_exercised_model_free": True,
            "fixed_model_free_frame_bootstrap_present": True,
            "private_request_result_frames_consumed_model_free": True,
            "fixed_native_kim_sandbox_launch_shape_present": True,
            "native_kim_sandbox_denials_exercised_model_free": True,
            "observer_exports_pid_or_pgid": False,
        },
        "runtime_environment_qualification": (
            "exact_three_entry_envp_by_contract_with_one_validated_"
            "post_exec_darwin_cpython_injection"
        ),
        "signal_state_canary": {
            "observed": True,
            "observation_point": "worker_main_after_cpython_startup",
            "main_thread_mask_empty": True,
            "termination_signals_default": True,
            "sigchld_default": True,
            "cpython_runtime_adjustments_observed": True,
            "spawn_attribute_claim_proven": False,
            "reason": (
                "post_cpython_state_does_not_reconstruct_the_pre_exec_instant"
            ),
        },
        "stdio_qualification": {
            "fixed_null_device_identity_verified": True,
            "all_three_same_identity_verified": True,
            "stdin_access": "read_only",
            "stdout_access": "write_only",
            "stderr_access": "write_only",
        },
        "parent_status_flag_claim": {
            "compared_bits": (
                "O_ACCMODE",
                "O_APPEND",
                "O_NONBLOCK",
                "O_ASYNC",
            ),
            "opaque_f_getfl_bits_compared": False,
        },
        "source_descriptor_scope": {
            "exact_physical_descriptors": (3, 4, 5),
            "all_six_permutations_proven": True,
            "representative_physical_layouts": (_REPRESENTATIVE_SOURCE_FD_LAYOUTS),
            "representative_layout_classes": (
                "ordinary_low_non_target",
                "scratch_candidate_collision",
                "mixed_fixed_target_collision",
                "near_fixed_scan_limit",
            ),
            "arbitrary_source_descriptor_values_proven": False,
        },
        "outer_supervisor_qualification": {
            "close_fds_required": True,
            "pass_fds_required": (),
            "observed_from_inside_harness": True,
            "observation_point": outer_supervisor_descriptors["observation_point"],
            "harness_entry_open_descriptors": outer_supervisor_descriptors[
                "open_descriptors"
            ],
            "no_unexpected_inherited_descriptors": True,
            "clean_outer_process_dependency_resolved": True,
        },
        "unresolved_boundaries": (
            "extension_path_import_toctou_not_eliminated",
            "runtime_executable_path_exec_toctou_not_eliminated",
            "worker_script_path_open_toctou_not_eliminated",
            "pre_exec_signal_state_not_reconstructed_after_cpython_startup",
            "owner_bound_worker_ready_observer_not_attached_to_real_worker",
            "combined_fixed_worker_bridge_is_not_a_real_model_worker",
            "native_ready_release_transport_is_not_attached_to_real_worker",
            "native_frame_bootstrap_is_model_free_not_real_kim_worker",
            "native_sandbox_frame_bootstrap_is_model_free_not_real_kim_worker",
            "real_model_worker_not_under_native_owner",
        ),
        "complete_descriptor_scan_soft_limit": _CANARY_SOFT_LIMIT,
        "inherited_descriptor_clearance_original_soft_limit": (original_soft_limit),
        "case_count": len(cases),
        "all_source_fd_permutations_exercised": (
            sum(case["layout_class"] == "exact_target_permutation" for case in cases)
            == 6
        ),
        "all_representative_source_fd_layouts_exercised": (
            {
                tuple(case["source_fds"])
                for case in cases
                if case["layout_class"] == "representative_physical_layout"
            }
            == set(_REPRESENTATIVE_SOURCE_FD_LAYOUTS)
        ),
        "post_spawn_owner_drop_canary": owner_drop_canary,
        "external_reap_poison_canary": external_reap_poison_canary,
        "owner_bound_process_image_canary": owner_bound_process_image_canary,
        "owner_bound_network_canary": owner_bound_network_canary,
        "owner_bound_worker_ready_native_image_canary": (
            owner_bound_worker_ready_native_image_canary
        ),
        "combined_fixed_worker_bridge_canary": (
            combined_fixed_worker_bridge_canary
        ),
        "native_ready_release_transport_canary": (
            native_ready_release_transport_canary
        ),
        "invalid_native_frame_bootstrap_canary": (
            invalid_native_frame_bootstrap_canary
        ),
        "native_frame_bootstrap_canary": native_frame_bootstrap_canary,
        "native_sandbox_frame_bootstrap_canary": (
            native_sandbox_frame_bootstrap_canary
        ),
        "descendant_group_canary": descendant_group_canary,
        "cases": cases,
    }


def run_sandbox_frame_bootstrap_canary(
    *,
    extension_path: Path,
    temporary_root: Path,
    expected_artifact_sha256: str,
    expected_source_sha256: str,
    expected_build_contract_sha256: str,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
) -> dict[str, Any]:
    """Run only the fixed sandboxed frame gate in an isolated process."""

    outer = _observe_outer_supervisor_descriptors()
    if outer["only_standard_descriptors_open"] is not True:
        raise RuntimeError("sandbox-frame harness inherited a descriptor")
    _prepare_isolated_descriptor_limit()
    extension, artifact = _load_verified_extension(
        extension_path,
        expected_artifact_sha256=expected_artifact_sha256,
        expected_source_sha256=expected_source_sha256,
        expected_build_contract_sha256=expected_build_contract_sha256,
    )
    spawn = getattr(
        extension,
        "_spawn_bound_private_melroformer_worker",
        None,
    )
    owner_type = getattr(extension, "_OwnedSpawnChild", None)
    if not callable(spawn) or not isinstance(owner_type, type):
        raise RuntimeError("private Kim sandbox native boundary is unavailable")
    runtime = Path(sys.executable).resolve(strict=True)
    process_image = expected_process_image_path.resolve(strict=True)
    runtime_before = _measure_runtime(runtime)
    image_before = _measure_runtime(process_image)
    provider_before = _measure_runtime(_SANDBOX_EXEC)
    worker_before = _measure_worker(_FRAME_BOOTSTRAP_WORKER)
    canary = _run_native_frame_bootstrap_canary(
        spawn=spawn,
        owner_type=owner_type,
        runtime_path=runtime,
        expected_process_image_path=process_image,
        expected_process_image_cdhash=expected_process_image_cdhash,
        temporary_root=temporary_root,
        worker_sha256=worker_before.sha256,
        sandboxed=True,
    )
    if (
        _measure_runtime(runtime) != runtime_before
        or _measure_runtime(process_image) != image_before
        or _measure_runtime(_SANDBOX_EXEC) != provider_before
        or _measure_worker(_FRAME_BOOTSTRAP_WORKER) != worker_before
    ):
        raise RuntimeError("sandbox-frame launch artifact changed")
    return {
        "schema": "sunofriend.native-kim-sandbox-frame-canary.v1",
        "status": "model_free_native_sandbox_launch_proved",
        "native_artifact_identity": _path_free_file_identity(artifact),
        "runtime_identity": _path_free_file_identity(runtime_before),
        "process_image_identity": _path_free_file_identity(image_before),
        "sandbox_provider_identity": _path_free_file_identity(provider_before),
        "worker_identity": _path_free_file_identity(worker_before),
        "canary": canary,
        "real_model_worker_executed": False,
        "checkpoint_opened": False,
        "audio_opened": False,
        "product_authority_granted": False,
    }


def run_fixed_model_free_parent_adapter_canary(
    *,
    extension_path: Path,
    temporary_root: Path,
    expected_artifact_sha256: str,
    expected_source_sha256: str,
    expected_build_contract_sha256: str,
    expected_process_image_path: Path,
    expected_process_image_cdhash: str,
) -> dict[str, Any]:
    """Run only the concrete model-free parent adapter, never Kim."""

    outer = _observe_outer_supervisor_descriptors()
    if outer["only_standard_descriptors_open"] is not True:
        raise RuntimeError("fixed-parent harness inherited a descriptor")
    _prepare_isolated_descriptor_limit()
    extension, artifact = _load_verified_extension(
        extension_path,
        expected_artifact_sha256=expected_artifact_sha256,
        expected_source_sha256=expected_source_sha256,
        expected_build_contract_sha256=expected_build_contract_sha256,
    )
    spawn = getattr(extension, "_spawn_bound_private_melroformer_worker", None)
    owner_type = getattr(extension, "_OwnedSpawnChild", None)
    if not callable(spawn) or not isinstance(owner_type, type):
        raise RuntimeError("fixed model-free native boundary is unavailable")
    runtime = Path(sys.executable).resolve(strict=True)
    process_image = expected_process_image_path.resolve(strict=True)
    worker_before = _measure_worker(_FRAME_BOOTSTRAP_WORKER)
    case_directory = temporary_root / "fixed-model-free-parent-adapter"
    case_directory.mkdir(mode=0o700)
    request = _build_model_free_native_request(
        case_directory=case_directory,
        worker_sha256=worker_before.sha256,
    )
    paths = _install_transport_descriptors(
        case_directory,
        _TARGET_FDS,
        request_bytes=_native_transport._encode_private_melroformer_native_request(
            request
        ),
    )
    result_reader = os.open(paths["result"], os.O_RDONLY)
    os.set_inheritable(result_reader, False)
    session_payload = {
        "native_artifact_sha256": artifact.sha256,
        "native_source_sha256": expected_source_sha256,
        "native_build_contract_sha256": expected_build_contract_sha256,
        "runtime_sha256": _measure_runtime(runtime).sha256,
        "process_image_cdhash": expected_process_image_cdhash,
        "worker_sha256": worker_before.sha256,
    }
    session_sha256 = hashlib.sha256(
        json.dumps(
            session_payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    evidence = _model_free_parent_adapter._run_fixed_model_free_macos_parent_adapter(
        request=request,
        native_session_observation_sha256=session_sha256,
        spawn_native=spawn,
        expected_owner_type=owner_type,
        runtime_path=runtime,
        expected_process_image_path=process_image,
        expected_process_image_cdhash=expected_process_image_cdhash,
        staging_directory=case_directory,
        request_read_descriptor=3,
        result_write_descriptor=4,
        result_read_descriptor=result_reader,
        checkpoint_placeholder_descriptor=5,
    )
    _close_descriptors_from_three()
    failure_directory = temporary_root / "fixed-model-free-parent-failure"
    failure_directory.mkdir(mode=0o700)
    failure_request = _build_model_free_native_request(
        case_directory=failure_directory,
        worker_sha256=worker_before.sha256,
    )
    failure_paths = _install_transport_descriptors(
        failure_directory,
        _TARGET_FDS,
        request_bytes=_native_transport._encode_private_melroformer_native_request(
            failure_request
        ),
    )
    failure_reader = os.open(failure_paths["result"], os.O_RDONLY)
    os.set_inheritable(failure_reader, False)
    wrong_cdhash = (
        ("0" if expected_process_image_cdhash[0] != "0" else "1")
        + expected_process_image_cdhash[1:]
    )
    try:
        _model_free_parent_adapter._run_fixed_model_free_macos_parent_adapter(
            request=failure_request,
            native_session_observation_sha256=session_sha256,
            spawn_native=spawn,
            expected_owner_type=owner_type,
            runtime_path=runtime,
            expected_process_image_path=process_image,
            expected_process_image_cdhash=wrong_cdhash,
            staging_directory=failure_directory,
            request_read_descriptor=3,
            result_write_descriptor=4,
            result_read_descriptor=failure_reader,
            checkpoint_placeholder_descriptor=5,
        )
    except _model_free_parent_adapter._FixedModelFreeMacosParentAdapterFailure as error:
        failure = {
            "case": "wrong_process_image_cdhash",
            "rejected_before_worker_release": True,
            "terminal_cleanup_complete": error.terminal_cleanup_complete,
            "cleanup_error_count": len(error.cleanup_errors),
            "real_model_worker_started": False,
            "checkpoint_opened": False,
            "audio_opened": False,
        }
    else:
        raise RuntimeError("fixed model-free parent accepted the wrong process image")
    if _measure_worker(_FRAME_BOOTSTRAP_WORKER) != worker_before:
        raise RuntimeError("fixed model-free parent worker changed")
    payload = {
        "schema": "sunofriend.native-model-free-parent-adapter-canary.v1",
        "status": "fixed_model_free_parent_adapter_and_cleanup_proved",
        "adapter_evidence": _model_free_parent_adapter._plain(evidence),
        "adversarial_cleanup": failure,
        "real_model_worker_executed": False,
        "accepted_checkpoint_opened": False,
        "audio_opened": False,
        "product_authority_granted": False,
    }
    return {
        **payload,
        "report_sha256": hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        ).hexdigest(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox-frame-only", action="store_true")
    parser.add_argument("--fixed-parent-adapter-only", action="store_true")
    parser.add_argument("extension_path", type=Path)
    parser.add_argument("temporary_root", type=Path)
    parser.add_argument("expected_artifact_sha256")
    parser.add_argument("expected_source_sha256")
    parser.add_argument("expected_build_contract_sha256")
    parser.add_argument("expected_process_image_path", type=Path)
    parser.add_argument("expected_process_image_cdhash")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.sandbox_frame_only and arguments.fixed_parent_adapter_only:
        raise ValueError("choose only one native canary mode")
    if arguments.fixed_parent_adapter_only:
        runner = run_fixed_model_free_parent_adapter_canary
    elif arguments.sandbox_frame_only:
        runner = run_sandbox_frame_bootstrap_canary
    else:
        runner = run_canary_matrix
    report = runner(
        extension_path=arguments.extension_path.resolve(strict=True),
        temporary_root=arguments.temporary_root.resolve(strict=True),
        expected_artifact_sha256=arguments.expected_artifact_sha256,
        expected_source_sha256=arguments.expected_source_sha256,
        expected_build_contract_sha256=(arguments.expected_build_contract_sha256),
        expected_process_image_path=arguments.expected_process_image_path,
        expected_process_image_cdhash=arguments.expected_process_image_cdhash,
    )
    sys.stdout.write(
        json.dumps(
            report,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
