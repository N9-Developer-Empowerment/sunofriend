"""Private bounded pipe handshake for a model worker observation point.

The child emits one path-free post-inference readiness record through an
explicit inherited pipe and then blocks until the parent releases it through a
second pipe.  This lets a parent inspect one exact live process without using
stdout, signals, polling a guessed delay, or retaining a PID in evidence.

The transport grants no model or product authority.  It is deliberately
private and is used only by the authorised MelRoFormer development worker.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .separation_contract import _canonical_json_bytes, _freeze_json


READY_SCHEMA = "sunofriend.private-melroformer-worker-ready.v1"
READY_PHASE = "post_inference_pre_quarantine"
RELEASE_PROTOCOL = "parent-native-image-inventory-release-v1"
_RELEASE_BYTES = b"sunofriend-native-image-inventory-release-v1\n"
_MAXIMUM_READY_BYTES = 16 * 1024
_RELEASE_TIMEOUT_SECONDS = 120.0
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class _PreparedWorkerReadyHandshake:
    ready_read_fd: int
    ready_write_fd: int
    release_read_fd: int
    release_write_fd: int
    child_ends_closed: bool = False
    readiness_received: bool = False
    release_sent: bool = False


def _prepare_worker_ready_handshake() -> _PreparedWorkerReadyHandshake:
    """Create two non-inheritable pipes whose child ends are passed explicitly."""

    ready_read_fd, ready_write_fd = os.pipe()
    try:
        release_read_fd, release_write_fd = os.pipe()
    except BaseException:
        os.close(ready_read_fd)
        os.close(ready_write_fd)
        raise
    prepared = _PreparedWorkerReadyHandshake(
        ready_read_fd=ready_read_fd,
        ready_write_fd=ready_write_fd,
        release_read_fd=release_read_fd,
        release_write_fd=release_write_fd,
    )
    for descriptor in _all_descriptors(prepared):
        os.set_inheritable(descriptor, False)
    return prepared


def _worker_ready_child_arguments(
    prepared: _PreparedWorkerReadyHandshake,
) -> tuple[str, ...]:
    _require_prepared(prepared)
    return (
        "--native-image-ready-fd",
        str(prepared.ready_write_fd),
        "--native-image-release-fd",
        str(prepared.release_read_fd),
    )


def _worker_ready_child_pass_fds(
    prepared: _PreparedWorkerReadyHandshake,
) -> tuple[int, int]:
    _require_prepared(prepared)
    return (prepared.ready_write_fd, prepared.release_read_fd)


def _read_worker_ready_handshake(
    prepared: _PreparedWorkerReadyHandshake,
    *,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    """Read exactly one bounded readiness record after the child was spawned."""

    _require_prepared(prepared)
    if prepared.readiness_received:
        raise RuntimeError("worker readiness was already received")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 120:
        raise ValueError("worker readiness timeout is outside bounds")
    _close_child_ends_in_parent(prepared)
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + float(timeout_seconds)
    received = bytearray()
    try:
        selector.register(prepared.ready_read_fd, selectors.EVENT_READ)
        while b"\n" not in received:
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(remaining):
                raise RuntimeError(
                    "worker did not reach the native-image observation point"
                )
            block = os.read(prepared.ready_read_fd, _MAXIMUM_READY_BYTES + 1)
            if not block:
                break
            received.extend(block)
            if len(received) > _MAXIMUM_READY_BYTES:
                raise RuntimeError("worker readiness record exceeds its bound")
    finally:
        selector.close()
        _close_if_open(prepared.ready_read_fd)
        prepared.ready_read_fd = -1
    if not received.endswith(b"\n") or received.count(b"\n") != 1:
        raise RuntimeError("worker readiness record is incomplete")
    try:
        decoded = received[:-1].decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("worker readiness record is invalid") from error
    prepared.readiness_received = True
    return _validate_worker_ready_claim(value)


def _release_worker_ready_handshake(
    prepared: _PreparedWorkerReadyHandshake,
) -> None:
    """Release one child only after the parent observation has completed."""

    _require_prepared(prepared)
    if not prepared.readiness_received or prepared.release_sent:
        raise RuntimeError("worker readiness release state differs")
    try:
        _write_all(prepared.release_write_fd, _RELEASE_BYTES)
    finally:
        _close_if_open(prepared.release_write_fd)
        prepared.release_write_fd = -1
    prepared.release_sent = True


def _abort_worker_ready_handshake(prepared: _PreparedWorkerReadyHandshake) -> None:
    """Close every still-owned pipe end without claiming a completed handshake."""

    if type(prepared) is not _PreparedWorkerReadyHandshake:
        return
    for name in (
        "ready_read_fd",
        "ready_write_fd",
        "release_read_fd",
        "release_write_fd",
    ):
        descriptor = getattr(prepared, name)
        _close_if_open(descriptor)
        setattr(prepared, name, -1)


def _worker_wait_for_native_image_inventory(
    *,
    ready_fd: int,
    release_fd: int,
    claim: Mapping[str, Any],
) -> None:
    """Child side: publish readiness, then require the exact parent release."""

    if (
        type(ready_fd) is not int
        or type(release_fd) is not int
        or ready_fd < 3
        or release_fd < 3
        or ready_fd == release_fd
    ):
        raise ValueError("worker readiness descriptors differ")
    checked = _validate_worker_ready_claim(claim)
    payload = _canonical_json_bytes(checked)
    if len(payload) > _MAXIMUM_READY_BYTES:
        raise ValueError("worker readiness record exceeds its bound")
    try:
        _write_all(ready_fd, payload)
    finally:
        os.close(ready_fd)
    received = _read_release(release_fd)
    if bytes(received) != _RELEASE_BYTES:
        raise RuntimeError("worker native-image observation release differs")


def _read_release(release_fd: int) -> bytearray:
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + _RELEASE_TIMEOUT_SECONDS
    received = bytearray()
    try:
        selector.register(release_fd, selectors.EVENT_READ)
        while len(received) < len(_RELEASE_BYTES):
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(remaining):
                raise RuntimeError("worker native-image observation release timed out")
            block = os.read(release_fd, len(_RELEASE_BYTES) + 1 - len(received))
            if not block:
                break
            received.extend(block)
    finally:
        selector.close()
        os.close(release_fd)
    return received


def _validate_worker_ready_claim(value: Mapping[str, Any]) -> Mapping[str, Any]:
    checked = _plain(value)
    expected = {
        "schema",
        "phase",
        "candidate_id",
        "checkpoint_sha256",
        "authorised_audio_sha256",
        "source_frames",
        "vocal_float32_sha256",
        "instrumental_float32_sha256",
        "release_protocol",
    }
    if not isinstance(checked, dict) or set(checked) != expected:
        raise ValueError("worker readiness fields differ")
    if (
        checked["schema"] != READY_SCHEMA
        or checked["phase"] != READY_PHASE
        or checked["candidate_id"] != "mlx-melroformer-kim-vocal-2"
        or not _is_sha(checked["checkpoint_sha256"])
        or not _is_sha(checked["authorised_audio_sha256"])
        or type(checked["source_frames"]) is not int
        or not 1 <= checked["source_frames"] <= 661_500
        or not _is_sha(checked["vocal_float32_sha256"])
        or not _is_sha(checked["instrumental_float32_sha256"])
        or checked["release_protocol"] != RELEASE_PROTOCOL
    ):
        raise ValueError("worker readiness identity differs")
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("worker readiness claim is not path-free")
    return _freeze_json(checked)


def _close_child_ends_in_parent(prepared: _PreparedWorkerReadyHandshake) -> None:
    if prepared.child_ends_closed:
        return
    _close_if_open(prepared.ready_write_fd)
    _close_if_open(prepared.release_read_fd)
    prepared.ready_write_fd = -1
    prepared.release_read_fd = -1
    prepared.child_ends_closed = True


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise RuntimeError("worker readiness pipe write did not advance")
        offset += written


def _all_descriptors(
    prepared: _PreparedWorkerReadyHandshake,
) -> Sequence[int]:
    return (
        prepared.ready_read_fd,
        prepared.ready_write_fd,
        prepared.release_read_fd,
        prepared.release_write_fd,
    )


def _close_if_open(descriptor: int) -> None:
    if descriptor < 0:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _require_prepared(prepared: _PreparedWorkerReadyHandshake) -> None:
    if type(prepared) is not _PreparedWorkerReadyHandshake:
        raise ValueError("worker readiness preparation differs")


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = ()
