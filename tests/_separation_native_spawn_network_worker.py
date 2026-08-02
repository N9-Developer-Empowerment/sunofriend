"""Fixed self-sandboxing worker for the owner-bound network canary.

The audited native launcher starts this exact stdlib-only file with Python
``-I -B -S``.  Its first stage replaces itself with ``sandbox-exec`` and then
the same Python/file pair, so the private native owner retains the process
identity across the sandbox transition.  The second stage performs one
loopback connection that must be denied, writes a bounded PID-free report and
briefly remains alive while the parent drains the kernel log stream.

This is model-free test evidence.  It opens no checkpoint content, audio,
product route or external network destination.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import resource
import socket
import sys
import time
from pathlib import Path
from typing import Any


_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
_INSIDE_ARGUMENT = "--inside-owner-bound-network-canary"
_TRANSPORT_FDS = (3, 4, 5)
_MAXIMUM_RESULT_BYTES = 65_536
_DRAIN_HOLD_SECONDS = 2.0


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
        raise RuntimeError("network canary result size is invalid")
    offset = 0
    while offset < len(payload):
        written = os.pwrite(4, payload[offset:], offset)
        if written <= 0:
            raise RuntimeError("network canary result write made no progress")
        offset += written
    os.ftruncate(4, len(payload))


def _enter_sandbox() -> None:
    worker = Path(__file__).resolve(strict=True)
    runtime = Path(sys.executable).resolve(strict=True)
    environment = dict(os.environ)
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
        environment,
    )


def _run_denied_canary() -> int:
    _harden_transport_descriptors()
    attached = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connect_result = attached.connect_ex(("127.0.0.1", 9))
    finally:
        attached.close()
    report = {
        "schema": "sunofriend.native-owner-network-canary-worker.v1",
        "ok": connect_result == errno.EPERM,
        "connect_errno_name": errno.errorcode.get(connect_result, "UNKNOWN"),
        "loopback_only": True,
        "external_destination_contacted": False,
        "open_descriptors": _open_descriptors(),
        "model_or_checkpoint_loaded": False,
    }
    _write_result(_canonical_bytes(report))
    time.sleep(_DRAIN_HOLD_SECONDS)
    return 0 if report["ok"] else 1


def main() -> int:
    if sys.argv[1:] == [_INSIDE_ARGUMENT]:
        return _run_denied_canary()
    if sys.argv[1:]:
        raise ValueError("owner-bound network canary arguments differ")
    _enter_sandbox()
    raise AssertionError("sandbox exec unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
