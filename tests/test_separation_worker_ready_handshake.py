from __future__ import annotations

import os
import threading

import pytest

import sunofriend._separation_worker_ready_handshake as handshake
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_exact_pipe_handshake_blocks_until_parent_release() -> None:
    prepared = handshake._prepare_worker_ready_handshake()
    child_ready = os.dup(prepared.ready_write_fd)
    child_release = os.dup(prepared.release_read_fd)
    result: list[object] = []

    def child() -> None:
        try:
            handshake._worker_wait_for_native_image_inventory(
                ready_fd=child_ready,
                release_fd=child_release,
                claim=_claim(),
            )
        except BaseException as error:  # pragma: no cover - assertion reports it
            result.append(error)
        else:
            result.append("released")

    thread = threading.Thread(target=child)
    thread.start()
    ready = handshake._read_worker_ready_handshake(
        prepared,
        timeout_seconds=1.0,
    )
    assert ready == _claim()
    assert thread.is_alive()
    handshake._release_worker_ready_handshake(prepared)
    thread.join(timeout=1.0)
    handshake._abort_worker_ready_handshake(prepared)

    assert result == ["released"]
    assert not thread.is_alive()


def test_readiness_rejects_path_and_product_overclaim() -> None:
    value = _claim()
    value["candidate_id"] = "/Users/example/model"

    with pytest.raises(ValueError, match="identity"):
        handshake._validate_worker_ready_claim(value)


def test_release_requires_a_received_readiness_record() -> None:
    prepared = handshake._prepare_worker_ready_handshake()
    try:
        with pytest.raises(RuntimeError, match="release state"):
            handshake._release_worker_ready_handshake(prepared)
    finally:
        handshake._abort_worker_ready_handshake(prepared)


def test_child_release_wait_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    monkeypatch.setattr(handshake, "_RELEASE_TIMEOUT_SECONDS", 0.01)
    try:
        with pytest.raises(RuntimeError, match="release timed out"):
            handshake._worker_wait_for_native_image_inventory(
                ready_fd=ready_write,
                release_fd=release_read,
                claim=_claim(),
            )
    finally:
        os.close(ready_read)
        os.close(release_write)


def test_worker_ready_handshake_has_no_public_route() -> None:
    assert "private-worker-ready-handshake" not in PUBLIC_COMMANDS
    assert "private-worker-ready-handshake" not in DIRECT_TUI_COMMANDS
    assert handshake.__all__ == ()


def _claim() -> dict[str, object]:
    return {
        "schema": handshake.READY_SCHEMA,
        "phase": handshake.READY_PHASE,
        "candidate_id": "mlx-melroformer-kim-vocal-2",
        "checkpoint_sha256": "a" * 64,
        "authorised_audio_sha256": "b" * 64,
        "source_frames": 44_100,
        "vocal_float32_sha256": "c" * 64,
        "instrumental_float32_sha256": "d" * 64,
        "release_protocol": handshake.RELEASE_PROTOCOL,
    }
