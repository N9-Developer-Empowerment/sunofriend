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


_MODULE_NAME = "_separation_native_spawn_darwin"
_METHOD_NAME = "_spawn_bound_fake_worker"
_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_canary_worker.py").resolve()
)
_HOLD_WORKER = (
    Path(__file__).with_name("_separation_native_spawn_hold_worker.py").resolve()
)
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
) -> dict[str, Path]:
    paths = {
        "request": directory / "request.bin",
        "result": directory / "result.bin",
        "checkpoint": directory / "checkpoint.bin",
    }
    paths["request"].write_bytes(_REQUEST_BYTES)
    paths["result"].write_bytes(b"")
    paths["checkpoint"].write_bytes(_CHECKPOINT_BYTES)
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


def run_canary_matrix(
    *,
    extension_path: Path,
    temporary_root: Path,
    expected_artifact_sha256: str,
    expected_source_sha256: str,
    expected_build_contract_sha256: str,
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
    worker_path = _WORKER.resolve(strict=True)
    runtime_before = _measure_runtime(runtime_path)
    worker_before = _measure_worker(worker_path)
    hold_worker_before = _measure_worker(_HOLD_WORKER)
    spawn = getattr(extension, _METHOD_NAME, None)
    if not callable(spawn):
        raise RuntimeError("native extension entry point is unavailable")
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
            native_owner.leader_reaped is not False
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
                    "native_owner_leader_reaped": (native_owner.leader_reaped),
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
    runtime_after = _measure_runtime(runtime_path)
    worker_after = _measure_worker(worker_path)
    hold_worker_after = _measure_worker(_HOLD_WORKER)
    if runtime_after != runtime_before:
        raise RuntimeError("bound runtime changed across canary matrix")
    if worker_after != worker_before:
        raise RuntimeError("bound worker changed across canary matrix")
    if hold_worker_after != hold_worker_before:
        raise RuntimeError("bound hold worker changed across canary matrix")
    expected_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    return {
        "schema": "sunofriend.native-spawn-canary-matrix.v2",
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
        "fixed_worker_identity": _path_free_file_identity(worker_after),
        "fixed_hold_worker_identity": _path_free_file_identity(hold_worker_after),
        "native_owner_type_qualification": {
            "direct_construction_rejected": direct_owner_construction_rejected,
            "raw_pid_not_exposed": True,
            "copy_and_pickle_rejected": True,
            "fork_clone_destructor_guard_present": True,
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
        "cases": cases,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("extension_path", type=Path)
    parser.add_argument("temporary_root", type=Path)
    parser.add_argument("expected_artifact_sha256")
    parser.add_argument("expected_source_sha256")
    parser.add_argument("expected_build_contract_sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_canary_matrix(
        extension_path=arguments.extension_path.resolve(strict=True),
        temporary_root=arguments.temporary_root.resolve(strict=True),
        expected_artifact_sha256=arguments.expected_artifact_sha256,
        expected_source_sha256=arguments.expected_source_sha256,
        expected_build_contract_sha256=(arguments.expected_build_contract_sha256),
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
