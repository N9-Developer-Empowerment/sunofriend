"""Fixed model-free worker for the combined native-owner canary.

The audited launcher starts this exact stdlib-only file with ``-I -B -S``.
The first stage replaces itself with ``sandbox-exec`` and the same fixed
Python/file pair.  The sandboxed stage loads a fixed set of native modules,
writes one PID-free ready marker, performs one deliberately denied loopback
connection, then writes one bounded private result containing its process
identity for an owner-side boolean match.  It remains alive briefly so the
parent can finish the owner-bound network and image observations before a
normal zero exit.

This is test evidence only.  It opens no checkpoint content, audio, model,
product route or external network destination.
"""

from __future__ import annotations

import _bz2
import _ctypes
import _hashlib
import _lzma
import _sqlite3
import _ssl
import errno
import fcntl
import hashlib
import json
import os
import resource
import socket
import sys
import time
import zlib
from pathlib import Path
from typing import Any


_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
_INSIDE_ARGUMENT = "--inside-combined-native-owner-canary"
_TRANSPORT_FDS = (3, 4, 5)
_MAXIMUM_RESULT_BYTES = 65_536
_READY_HOLD_SECONDS = 1.0
_DRAIN_HOLD_SECONDS = 2.0
_NATIVE_MODULES = tuple(
    module.__name__
    for module in (
        _bz2,
        _ctypes,
        _hashlib,
        _lzma,
        _sqlite3,
        _ssl,
        zlib,
    )
)


def _harden_transport_descriptors() -> None:
    for descriptor in _TRANSPORT_FDS:
        os.set_inheritable(descriptor, False)


def _open_descriptors() -> list[int]:
    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit == resource.RLIM_INFINITY:
        soft_limit = 1_048_576
    result: list[int] = []
    for descriptor in range(int(soft_limit)):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        result.append(descriptor)
    return result


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


def _write_result(payload: bytes) -> None:
    if not payload or len(payload) > _MAXIMUM_RESULT_BYTES:
        raise RuntimeError("combined canary result size is invalid")
    offset = 0
    while offset < len(payload):
        written = os.pwrite(4, payload[offset:], offset)
        if written <= 0:
            raise RuntimeError("combined canary result write made no progress")
        offset += written
    os.ftruncate(4, len(payload))


def _enter_sandbox() -> None:
    worker = Path(__file__).resolve(strict=True)
    runtime = Path(sys.executable).resolve(strict=True)
    os.execve(
        _SANDBOX_EXEC,
        [
            _SANDBOX_EXEC,
            "-p",
            _PROFILE,
            str(runtime),
            "-I",
            "-B",
            "-S",
            str(worker),
            _INSIDE_ARGUMENT,
        ],
        dict(os.environ),
    )


def _run_combined_canary() -> int:
    _harden_transport_descriptors()
    ready = {
        "schema": "sunofriend.native-owner-combined-ready.v1",
        "phase": "fixed_native_modules_loaded",
        "native_modules": list(_NATIVE_MODULES),
        "pid_or_pgid_exported": False,
        "model_or_checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
    }
    ready_bytes = _canonical_bytes(ready)
    _write_result(ready_bytes)
    time.sleep(_READY_HOLD_SECONDS)

    attached = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connect_result = attached.connect_ex(("127.0.0.1", 9))
    finally:
        attached.close()
    payload = {
        "schema": "sunofriend.native-owner-combined-result.v1",
        "ok": connect_result == errno.EPERM,
        "ready_sha256": hashlib.sha256(ready_bytes).hexdigest(),
        "private_process_identity": {
            "pid": os.getpid(),
            "pgid": os.getpgrp(),
        },
        "connect_errno_name": errno.errorcode.get(connect_result, "UNKNOWN"),
        "loopback_only": True,
        "external_destination_contacted": False,
        "open_descriptors": _open_descriptors(),
        "native_modules": list(_NATIVE_MODULES),
        "model_or_checkpoint_loaded": False,
        "audio_read": False,
    }
    _write_result(_canonical_bytes(payload))
    time.sleep(_DRAIN_HOLD_SECONDS)
    return 0 if payload["ok"] else 1


def main() -> int:
    if sys.argv[1:] == [_INSIDE_ARGUMENT]:
        return _run_combined_canary()
    if sys.argv[1:]:
        raise ValueError("combined native-owner canary arguments differ")
    _enter_sandbox()
    raise AssertionError("sandbox exec unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
