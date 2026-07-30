"""Isolated adversarial harness for a built Darwin launcher extension.

The harness is deliberately independent of the future build module.  Give it
an absolute path to a provenance-approved extension artifact and an absolute
temporary directory.  It loads that private artifact, closes every unrelated
descriptor, and exercises all source-descriptor permutations involving
logical FD 3, 4 and 5.

This script performs no compilation, network access, model import, audio
operation or separation.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import itertools
import json
import os
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
_LOGICAL_ROLES = ("request", "result", "checkpoint")
_TARGET_FDS = (3, 4, 5)
_LOW_CANARY_FDS = (6, 7, 8)
_CANARY_SOFT_LIMIT = 4_096
_HIGH_CANARY_FDS = (
    _CANARY_SOFT_LIMIT - 3,
    _CANARY_SOFT_LIMIT - 2,
    _CANARY_SOFT_LIMIT - 1,
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

    def __init__(self, pid: int) -> None:
        if type(pid) is not int or pid <= 0:
            raise ValueError("owned canary PID is invalid")
        self.pid = pid
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
            try:
                waited, status = os.waitpid(self.pid, os.WNOHANG)
            except InterruptedError:
                continue
            except ChildProcessError as error:
                raise RuntimeError("canary lost exact child ownership") from error
            if waited == self.pid:
                self._reaped = True
                return status
            time.sleep(0.005)
        return None

    def _signal_owned_group_or_pid(
        self,
        *,
        deadline: float,
    ) -> None:
        while True:
            try:
                os.killpg(self.pid, signal.SIGKILL)
                return
            except ProcessLookupError:
                try:
                    os.kill(self.pid, signal.SIGKILL)
                    return
                except ProcessLookupError:
                    return
                except InterruptedError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("canary exact-child signal was interrupted")
            except InterruptedError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("canary child-group signal was interrupted")

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
    role_by_descriptor = dict(zip(source_fds, _LOGICAL_ROLES))
    for descriptor in _TARGET_FDS:
        role = role_by_descriptor[descriptor]
        flags = os.O_WRONLY if role == "result" else os.O_RDONLY
        opened = os.open(paths[role], flags)
        if opened != descriptor:
            os.close(opened)
            raise RuntimeError("isolated transport descriptor order changed")
        os.set_inheritable(opened, False)
        os.lseek(opened, _INITIAL_OFFSETS[role], os.SEEK_SET)
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
        descriptor = _move_to_exact_descriptor(reader, target)
        reader = -1
        os.set_inheritable(descriptor, True)
    finally:
        if reader >= 0:
            os.close(reader)
        os.close(writer)


def _install_socket_canary(target: int) -> None:
    local, peer = socket.socketpair()
    try:
        source = local.detach()
        descriptor = _move_to_exact_descriptor(source, target)
        os.set_inheritable(descriptor, True)
    finally:
        local.close()
        peer.close()


def _install_unrelated_inheritable_canaries(directory: Path) -> None:
    low_regular, low_pipe, low_socket = _LOW_CANARY_FDS
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
    pid: int,
    null_identity: dict[str, int],
) -> None:
    expected_hashes = {
        "request": hashlib.sha256(_REQUEST_BYTES).hexdigest(),
        "checkpoint": hashlib.sha256(_CHECKPOINT_BYTES).hexdigest(),
    }
    if report.get("schema") != ("sunofriend.native-spawn-descriptor-canary.v1"):
        raise AssertionError("canary result schema is invalid")
    if report.get("ok") is not True:
        raise AssertionError("canary worker did not complete")
    if report.get("pid") != pid or report.get("pgid") != pid:
        raise AssertionError("canary worker does not own a new PID-matched group")
    if report.get("open_descriptors") != [0, 1, 2, 3, 4, 5]:
        raise AssertionError("child descriptor allowlist is not exact")
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
) -> None:
    by_descriptor = {item.descriptor: item for item in snapshot}
    expected = (*_LOW_CANARY_FDS, *_HIGH_CANARY_FDS)
    if any(descriptor not in by_descriptor for descriptor in expected):
        raise AssertionError("parent canary descriptor is missing")
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


def _source_fd_permutations() -> Iterator[tuple[int, int, int]]:
    yield from itertools.permutations(_TARGET_FDS)


def run_canary_matrix(
    *,
    extension_path: Path,
    temporary_root: Path,
    expected_artifact_sha256: str,
    expected_source_sha256: str,
    expected_build_contract_sha256: str,
) -> dict[str, Any]:
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
    spawn = getattr(extension, _METHOD_NAME, None)
    if not callable(spawn):
        raise RuntimeError("native extension entry point is unavailable")
    null_identity = _null_device_identity()
    cases: list[dict[str, Any]] = []
    for index, source_fds in enumerate(_source_fd_permutations(), start=1):
        _close_descriptors_from_three()
        case_directory = temporary_root / f"case-{index}"
        case_directory.mkdir(mode=0o700)
        paths = _install_transport_descriptors(case_directory, source_fds)
        _install_unrelated_inheritable_canaries(case_directory)
        before = snapshot_parent_descriptors()
        _assert_canaries_present_in_parent(before)
        pid = spawn(
            os.fsencode(runtime_path),
            os.fsencode(worker_path),
            *source_fds,
        )
        if type(pid) is not int or pid <= 0:
            raise AssertionError("native launcher returned an invalid PID")
        with _OwnedCanaryChild(pid) as child:
            after_spawn = snapshot_parent_descriptors()
            _assert_parent_unchanged(before, after_spawn)
            status = child.wait()
            after_reap = snapshot_parent_descriptors()
            _assert_parent_unchanged(before, after_reap)
            if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
                raise AssertionError("canary child did not exit successfully")
            report = _read_single_json(paths["result"])
            _assert_worker_report(
                report,
                pid=pid,
                null_identity=null_identity,
            )
            cases.append(
                {
                    "source_fds": list(source_fds),
                    "pid": pid,
                    "pgid": report["pgid"],
                    "open_descriptors": report["open_descriptors"],
                    "parent_offsets_unchanged_after_spawn": True,
                    "parent_offsets_unchanged_after_reap": True,
                }
            )
    runtime_after = _measure_runtime(runtime_path)
    worker_after = _measure_worker(worker_path)
    if runtime_after != runtime_before:
        raise RuntimeError("bound runtime changed across canary matrix")
    if worker_after != worker_before:
        raise RuntimeError("bound worker changed across canary matrix")
    expected_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    return {
        "schema": "sunofriend.native-spawn-canary-matrix.v1",
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
        "runtime_environment_qualification": (
            "exact_three_entry_envp_by_contract_with_one_validated_"
            "post_exec_darwin_cpython_injection"
        ),
        "signal_state_canary": {
            "observed": False,
            "spawn_attribute_claim_proven": False,
            "reason": (
                "cpython_startup_can_change_signal_state_before_worker_user_code"
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
            "arbitrary_source_descriptor_values_proven": False,
        },
        "outer_supervisor_qualification": {
            "close_fds_required": True,
            "pass_fds_required": (),
            "observed_from_inside_harness": False,
            "clean_outer_process_dependency_resolved": False,
        },
        "unresolved_boundaries": (
            "extension_path_import_toctou_not_eliminated",
            "runtime_executable_path_exec_toctou_not_eliminated",
            "worker_script_path_open_toctou_not_eliminated",
            "clean_outer_supervisor_not_proven_inside_harness",
        ),
        "complete_descriptor_scan_soft_limit": _CANARY_SOFT_LIMIT,
        "inherited_descriptor_clearance_original_soft_limit": (original_soft_limit),
        "case_count": len(cases),
        "all_source_fd_permutations_exercised": len(cases) == 6,
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
