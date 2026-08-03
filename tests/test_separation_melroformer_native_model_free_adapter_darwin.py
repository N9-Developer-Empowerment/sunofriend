from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

import sunofriend._separation_melroformer_native_model_free_adapter_darwin as adapter
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
    _build_private_melroformer_native_result,
    _encode_private_melroformer_native_request,
    _encode_private_melroformer_native_result,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _request(staging: Path):
    worker = (
        Path(__file__).resolve().parent
        / "_separation_native_spawn_frame_bootstrap_worker.py"
    )
    return _build_private_melroformer_native_request(
        run_nonce=_digest("model-free-adapter-run"),
        paths={
            "repository_root": str(staging / "repository-root"),
            "source_root": str(staging / "source-root"),
            "checkpoint_path": str(staging / "checkpoint.safetensors"),
            "companion_root": str(staging / "companion-root"),
            "authorisation_report_path": str(staging / "authorisation.json"),
            "staging_directory": str(staging),
        },
        identities={
            "worker_source_sha256": hashlib.sha256(worker.read_bytes()).hexdigest(),
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": _digest("authorisation"),
            "source_manifest_sha256": _digest("source"),
            "companion_manifest_sha256": _digest("companions"),
        },
        device="cpu",
    )


def _child_result() -> dict[str, Any]:
    return {
        "schema": (
            "sunofriend.private-melroformer-native-"
            "sandbox-bootstrap-child.v1"
        ),
        "status": "model_free_native_sandbox_bootstrap_complete",
        "request_frame_validated": True,
        "request_paths_opened": False,
        "request_paths_retained": False,
        "checkpoint_descriptor_regular": True,
        "checkpoint_descriptor_bytes_read": 0,
        "ready_release_completed": True,
        "ready_sha256": _digest("ready"),
        "release_sha256": _digest("release"),
        "open_descriptors_after_handshake": [0, 1, 2, 3, 4, 5],
        "model_imported": False,
        "checkpoint_loaded": False,
        "audio_read": False,
        "network_used": False,
        "product_authority_granted": False,
        "sandbox_canaries": {
            "network_connect_errno": 1,
            "network_errno_name": "EPERM",
            "process_fork_errno": 1,
            "process_fork_errno_name": "EPERM",
            "outside_write_errno": 1,
            "outside_write_errno_name": "EPERM",
            "fixed_sandbox_environment_observed": True,
        },
    }


def _open_transport(staging: Path, request):
    request_path = staging / "request.bin"
    result_path = staging / "result.bin"
    checkpoint_path = staging / "checkpoint-placeholder.bin"
    request_path.write_bytes(_encode_private_melroformer_native_request(request))
    result_path.write_bytes(b"")
    checkpoint_path.write_bytes(b"model-free-checkpoint-placeholder\n")
    descriptors = {
        "request": os.open(request_path, os.O_RDONLY),
        "result_write": os.open(result_path, os.O_WRONLY),
        "result_read": os.open(result_path, os.O_RDONLY),
        "checkpoint": os.open(checkpoint_path, os.O_RDONLY),
    }
    for descriptor in descriptors.values():
        os.set_inheritable(descriptor, False)
    return descriptors, result_path


def _close_transport(descriptors: dict[str, int]) -> None:
    for descriptor in descriptors.values():
        try:
            os.close(descriptor)
        except OSError:
            pass


def test_transport_and_staging_verify_only_the_result_changed(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    request = _request(staging)
    descriptors, result_path = _open_transport(staging, request)
    try:
        transport = adapter._validate_transport_descriptors(
            request=request,
            request_read_descriptor=descriptors["request"],
            result_write_descriptor=descriptors["result_write"],
            result_read_descriptor=descriptors["result_read"],
            checkpoint_placeholder_descriptor=descriptors["checkpoint"],
        )
        before = adapter._measure_model_free_staging(
            staging,
            transport=transport,
            expected_result_frame=None,
        )
        result = _build_private_melroformer_native_result(
            request=request,
            private_process_identity={"pid": 7171, "pgid": 7171},
            child_result=_child_result(),
        )
        frame = _encode_private_melroformer_native_result(
            result,
            request=request,
        )
        result_path.write_bytes(frame)
        after = adapter._measure_model_free_staging(
            staging,
            transport=transport,
            expected_result_frame=frame,
        )
    finally:
        _close_transport(descriptors)

    assert before["entry_count"] == after["entry_count"] == 3
    assert before["stable_input_manifest_sha256"] == after[
        "stable_input_manifest_sha256"
    ]
    assert before["manifest_sha256"] != after["manifest_sha256"]
    assert after["result_frame_sha256"] == hashlib.sha256(frame).hexdigest()
    assert after["paths_retained"] is False


def test_bounded_fd4_reader_decodes_one_exact_result(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    request = _request(staging)
    descriptors, result_path = _open_transport(staging, request)
    result = _build_private_melroformer_native_result(
        request=request,
        private_process_identity={"pid": 7171, "pgid": 7171},
        child_result=_child_result(),
    )
    frame = _encode_private_melroformer_native_result(result, request=request)
    result_path.write_bytes(frame)
    try:
        decoded = adapter._read_bounded_result_frame(
            descriptors["result_read"],
            request=request,
            timeout_seconds=0.1,
        )
    finally:
        _close_transport(descriptors)

    assert decoded["result_sha256"] == result["result_sha256"]
    assert decoded["private_process_identity"] == {"pid": 7171, "pgid": 7171}


def test_bounded_fd4_reader_times_out_on_an_empty_result(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    request = _request(staging)
    descriptors, _result_path = _open_transport(staging, request)
    try:
        with pytest.raises(TimeoutError, match="did not complete"):
            adapter._read_bounded_result_frame(
                descriptors["result_read"],
                request=request,
                timeout_seconds=0.01,
            )
    finally:
        _close_transport(descriptors)


def test_bounded_fd4_reader_rejects_an_oversized_result(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    request = _request(staging)
    descriptors, result_path = _open_transport(staging, request)
    os.truncate(result_path, adapter.RESULT_MAXIMUM_BYTES + 1)
    try:
        with pytest.raises(RuntimeError, match="exceeds its bound"):
            adapter._read_bounded_result_frame(
                descriptors["result_read"],
                request=request,
                timeout_seconds=0.1,
            )
    finally:
        _close_transport(descriptors)


def test_transport_rejects_checkpoint_sized_fd5(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    request = _request(staging)
    descriptors, _result_path = _open_transport(staging, request)
    os.close(descriptors["checkpoint"])
    checkpoint_path = staging / "checkpoint-placeholder.bin"
    os.truncate(checkpoint_path, CONVERSION_CHECKPOINT_BYTES)
    descriptors["checkpoint"] = os.open(checkpoint_path, os.O_RDONLY)
    os.set_inheritable(descriptors["checkpoint"], False)
    try:
        with pytest.raises(ValueError, match="transport geometry"):
            adapter._validate_transport_descriptors(
                request=request,
                request_read_descriptor=descriptors["request"],
                result_write_descriptor=descriptors["result_write"],
                result_read_descriptor=descriptors["result_read"],
                checkpoint_placeholder_descriptor=descriptors["checkpoint"],
            )
    finally:
        _close_transport(descriptors)


def test_model_free_child_result_rejects_any_checkpoint_read() -> None:
    child = _child_result()
    child["checkpoint_descriptor_bytes_read"] = 1

    with pytest.raises(ValueError, match="child result differs"):
        adapter._validate_model_free_child_result(child)


def test_adapter_rejects_a_python_spawn_callback() -> None:
    with pytest.raises(TypeError, match="spawn binding differs"):
        adapter._validate_spawn_binding(lambda: None)


def test_model_free_adapter_has_no_public_or_tui_route() -> None:
    assert "private-melroformer-native-model-free-adapter" not in PUBLIC_COMMANDS
    assert (
        "private-melroformer-native-model-free-adapter"
        not in DIRECT_TUI_COMMANDS
    )
    assert adapter.__all__ == ()
