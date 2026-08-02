"""Fixed model-free worker for the native ready/release transport canary.

The audited launcher maps request, result and checkpoint files to descriptors
3/4/5, plus the exact existing Kim worker readiness pipes to descriptors 6/7.
This stdlib-only worker emits a valid path-free Kim readiness claim, blocks
until the exact release bytes arrive, writes one bounded result and exits zero.

This is test evidence only.  It reads no request, checkpoint, audio or model,
opens no network destination and grants no production execution authority.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import resource
from typing import Any


_TRANSPORT_FDS = (3, 4, 5, 6, 7)
_READY_FD = 6
_RELEASE_FD = 7
_RELEASE_BYTES = b"sunofriend-native-image-inventory-release-v1\n"
_MAXIMUM_RESULT_BYTES = 65_536
_READY_CLAIM = {
    "schema": "sunofriend.private-melroformer-worker-ready.v1",
    "phase": "post_inference_pre_quarantine",
    "candidate_id": "mlx-melroformer-kim-vocal-2",
    "checkpoint_sha256": "0" * 64,
    "authorised_audio_sha256": "1" * 64,
    "source_frames": 1,
    "vocal_float32_sha256": "2" * 64,
    "instrumental_float32_sha256": "3" * 64,
    "release_protocol": "parent-native-image-inventory-release-v1",
}


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


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise RuntimeError("ready/release canary write made no progress")
        offset += written


def _read_release() -> bytes:
    received = bytearray()
    try:
        while len(received) <= len(_RELEASE_BYTES):
            block = os.read(
                _RELEASE_FD,
                len(_RELEASE_BYTES) + 1 - len(received),
            )
            if not block:
                break
            received.extend(block)
    finally:
        os.close(_RELEASE_FD)
    return bytes(received)


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


def _write_result(payload: bytes) -> None:
    if not payload or len(payload) > _MAXIMUM_RESULT_BYTES:
        raise RuntimeError("ready/release canary result size is invalid")
    offset = 0
    while offset < len(payload):
        written = os.pwrite(4, payload[offset:], offset)
        if written <= 0:
            raise RuntimeError("ready/release result write made no progress")
        offset += written
    os.ftruncate(4, len(payload))


def main() -> int:
    _harden_transport_descriptors()
    ready_bytes = _canonical_bytes(_READY_CLAIM)
    try:
        _write_all(_READY_FD, ready_bytes)
    finally:
        os.close(_READY_FD)
    release = _read_release()
    if release != _RELEASE_BYTES:
        return 2
    result = {
        "schema": "sunofriend.native-owner-ready-release-result.v1",
        "ok": True,
        "ready_sha256": hashlib.sha256(ready_bytes).hexdigest(),
        "release_sha256": hashlib.sha256(release).hexdigest(),
        "open_descriptors_after_handshake": _open_descriptors(),
        "pid_or_pgid_exported": False,
        "model_or_checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
    }
    _write_result(_canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
