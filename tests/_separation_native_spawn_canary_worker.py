"""Fixed stdlib-only worker for the Darwin native-spawn canary.

This file is test evidence, not a separation worker.  The audited launcher
executes it with ``python -I -B -S`` and exposes only logical request, result
and checkpoint descriptors 3, 4 and 5.  It performs no model, audio, network
or filesystem-path operation.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import resource
import stat
import sys
from typing import Any


_TRANSPORT_FDS = (3, 4, 5)
_MAX_INPUT_BYTES = 65_536
_MAX_RESULT_BYTES = 65_536
_ACCESS_NAMES = {
    os.O_RDONLY: "read_only",
    os.O_WRONLY: "write_only",
    os.O_RDWR: "read_write",
}
_RUNTIME_INJECTED_ENVIRONMENT_KEY = "__CF_USER_TEXT_ENCODING"


def _harden_transport_descriptors() -> None:
    for descriptor in _TRANSPORT_FDS:
        os.set_inheritable(descriptor, False)


def _read_regular_file_at_zero(descriptor: int) -> bytes:
    byte_count = os.fstat(descriptor).st_size
    if byte_count < 0 or byte_count > _MAX_INPUT_BYTES:
        raise ValueError("canary input size is invalid")
    chunks: list[bytes] = []
    offset = 0
    while offset < byte_count:
        chunk = os.pread(descriptor, byte_count - offset, offset)
        if not chunk:
            raise ValueError("canary input is truncated")
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _write_regular_file_at_zero(descriptor: int, payload: bytes) -> None:
    if len(payload) > _MAX_RESULT_BYTES:
        raise ValueError("canary result is too large")
    offset = 0
    while offset < len(payload):
        written = os.pwrite(descriptor, payload[offset:], offset)
        if written <= 0:
            raise OSError("canary result write made no progress")
        offset += written


def _soft_descriptor_limit() -> int:
    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit == resource.RLIM_INFINITY:
        return 1_048_576
    return int(soft_limit)


def _open_descriptors() -> list[int]:
    descriptors: list[int] = []
    for descriptor in range(_soft_descriptor_limit()):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        descriptors.append(descriptor)
    return descriptors


def _access_name(descriptor: int) -> str:
    access = fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
    return _ACCESS_NAMES.get(access, f"unexpected_{access}")


def _rejected_errno(operation: Any) -> int | None:
    try:
        operation()
    except OSError as error:
        return error.errno
    return None


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _environment_observation() -> dict[str, Any]:
    environment = dict(os.environ)
    injected = environment.pop(_RUNTIME_INJECTED_ENVIRONMENT_KEY, None)
    return {
        "required_bindings": dict(sorted(environment.items())),
        "runtime_injected": {
            "name": _RUNTIME_INJECTED_ENVIRONMENT_KEY,
            "present": injected is not None,
            "value": injected,
            "value_sha256": (
                hashlib.sha256(injected.encode("utf-8")).hexdigest()
                if injected is not None
                else None
            ),
        },
    }


def _stdio_observation() -> dict[str, Any]:
    identities = []
    for descriptor in (0, 1, 2):
        facts = os.fstat(descriptor)
        identities.append(
            {
                "device": facts.st_dev,
                "inode": facts.st_ino,
                "special_device": facts.st_rdev,
                "file_type": stat.S_IFMT(facts.st_mode),
            }
        )
    return {
        "identities": identities,
        "same_identity": identities[0] == identities[1] == identities[2],
        "all_character_devices": all(
            item["file_type"] == stat.S_IFCHR for item in identities
        ),
        "access": {
            str(descriptor): _access_name(descriptor) for descriptor in (0, 1, 2)
        },
    }


def main() -> int:
    _harden_transport_descriptors()

    request = _read_regular_file_at_zero(3)
    checkpoint = _read_regular_file_at_zero(5)
    document = {
        "schema": "sunofriend.native-spawn-descriptor-canary.v1",
        "ok": True,
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "descriptor_scan_soft_limit": _soft_descriptor_limit(),
        "open_descriptors": _open_descriptors(),
        "transport_inheritable": {
            str(descriptor): os.get_inheritable(descriptor)
            for descriptor in _TRANSPORT_FDS
        },
        "transport_access": {
            str(descriptor): _access_name(descriptor) for descriptor in _TRANSPORT_FDS
        },
        "stdio_observation": _stdio_observation(),
        "rejected_operation_errno": {
            "request_write": _rejected_errno(lambda: os.pwrite(3, b"x", 0)),
            "result_read": _rejected_errno(lambda: os.pread(4, 1, 0)),
            "checkpoint_write": _rejected_errno(lambda: os.pwrite(5, b"x", 0)),
        },
        "request_bytes": len(request),
        "request_sha256": hashlib.sha256(request).hexdigest(),
        "checkpoint_bytes": len(checkpoint),
        "checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(),
        "environment_observation": _environment_observation(),
        "python_flags": {
            "isolated": sys.flags.isolated,
            "dont_write_bytecode": sys.flags.dont_write_bytecode,
            "no_site": sys.flags.no_site,
        },
    }
    _write_regular_file_at_zero(4, _canonical_bytes(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
