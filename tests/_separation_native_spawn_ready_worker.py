"""Fixed PID-free readiness worker for owner-bound native-image canaries.

The audited native launcher starts this stdlib-only file with Python
``-I -B -S``.  It hardens its three fixed transport descriptors, imports a
small fixed native-module set, writes one bounded readiness record and remains
alive until the opaque parent owner terminates it after observation.

This worker opens no checkpoint or audio, starts no network operation and
does not expose its PID or process group.
"""

from __future__ import annotations

import _bz2
import _ctypes
import _hashlib
import _lzma
import _sqlite3
import _ssl
import json
import os
import signal
import time
import zlib
from typing import Any


_TRANSPORT_FDS = (3, 4, 5)
_MAXIMUM_RESULT_BYTES = 65_536
_NATIVE_MODULES = (
    _bz2,
    _ctypes,
    _hashlib,
    _lzma,
    _sqlite3,
    _ssl,
    zlib,
)


def _harden_transport_descriptors() -> None:
    for descriptor in _TRANSPORT_FDS:
        os.set_inheritable(descriptor, False)


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
        raise RuntimeError("native-image ready result size is invalid")
    offset = 0
    while offset < len(payload):
        written = os.pwrite(4, payload[offset:], offset)
        if written <= 0:
            raise RuntimeError("native-image ready result write made no progress")
        offset += written
    os.ftruncate(4, len(payload))


def main() -> int:
    _harden_transport_descriptors()
    report = {
        "schema": "sunofriend.native-owner-worker-ready-canary.v1",
        "phase": "fixed_native_modules_loaded",
        "native_modules": [module.__name__ for module in _NATIVE_MODULES],
        "pid_or_pgid_exported": False,
        "model_or_checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
    }
    _write_result(_canonical_bytes(report))
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
