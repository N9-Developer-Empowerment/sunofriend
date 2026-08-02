from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import sunofriend._separation_melroformer_native_worker as worker
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
    _decode_private_melroformer_native_result,
    _encode_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


REPOSITORY = Path(__file__).parents[1]
ENTRYPOINT = REPOSITORY / worker.WORKER_RELATIVE_PATH


def _companion_observation() -> dict[str, object]:
    return {
        "files": {
            worker.CONFIG_NAME: {
                "bytes": worker.CONFIG_BYTES,
                "sha256": worker.CONFIG_SHA256,
                "cryptographic_identity_verified": True,
            },
            worker.LICENSE_NAME: {
                "bytes": worker.LICENSE_BYTES,
                "sha256": worker.LICENSE_SHA256,
                "cryptographic_identity_verified": True,
            },
        },
        "all_cryptographic_identities_verified": True,
    }


def test_native_worker_bootstrap_hardens_descriptors_before_project_imports() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")

    first_hardening = source.index("os.set_inheritable(_transport_descriptor, False)")
    assert first_hardening < source.index("import sys")
    assert first_hardening < source.index("from pathlib import Path")
    assert first_hardening < source.index("from sunofriend.")
    assert 'sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))' in source
    assert "sys.argv" not in source
    assert "PYTHONPATH" not in source


def test_native_worker_has_no_public_product_route() -> None:
    assert "private-melroformer-native-worker" not in PUBLIC_COMMANDS
    assert "private-melroformer-native-worker" not in DIRECT_TUI_COMMANDS


def test_companion_manifest_is_path_free_and_deterministic() -> None:
    first = worker._companion_manifest_identity(_companion_observation())
    second = worker._companion_manifest_identity(_companion_observation())

    assert first == second
    assert [item["name"] for item in first["files"]] == [
        worker.LICENSE_NAME,
        worker.CONFIG_NAME,
    ]
    assert "/Users/" not in repr(first)


def test_request_reader_requires_regular_bounded_noninheritable_file(
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "request.bin"
    request_path.write_bytes(b"not-a-frame")
    descriptor = os.open(request_path, os.O_RDONLY)
    try:
        os.set_inheritable(descriptor, True)
        with pytest.raises(ValueError, match="request descriptor differs"):
            worker._read_private_melroformer_native_request(descriptor)
    finally:
        os.close(descriptor)


def test_real_native_worker_core_uses_fd5_and_writes_path_free_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    companion_root = tmp_path / "companions"
    staging = tmp_path / "staging"
    for directory in (source_root, companion_root, staging):
        directory.mkdir(mode=0o700)
    checkpoint_path = tmp_path / "checkpoint.safetensors"
    checkpoint_path.write_bytes(b"descriptor-bound-test-checkpoint")
    authorisation_path = tmp_path / "authorisation.json"
    authorisation_path.write_text("{}", encoding="utf-8")
    companion_identity = worker._companion_manifest_identity(
        _companion_observation()
    )
    entrypoint_sha256 = hashlib.sha256(ENTRYPOINT.read_bytes()).hexdigest()
    request = _build_private_melroformer_native_request(
        run_nonce="a" * 64,
        paths={
            "repository_root": str(REPOSITORY),
            "source_root": str(source_root),
            "checkpoint_path": str(checkpoint_path),
            "companion_root": str(companion_root),
            "authorisation_report_path": str(authorisation_path),
            "staging_directory": str(staging),
        },
        identities={
            "worker_source_sha256": entrypoint_sha256,
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": "b" * 64,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "companion_manifest_sha256": companion_identity["manifest_sha256"],
        },
        device="cpu",
    )
    request_path = tmp_path / "request.frame"
    request_path.write_bytes(_encode_private_melroformer_native_request(request))
    result_path = tmp_path / "result.frame"
    result_path.touch(mode=0o600)
    request_fd = os.open(request_path, os.O_RDONLY)
    result_fd = os.open(result_path, os.O_WRONLY)
    checkpoint_fd = os.open(checkpoint_path, os.O_RDONLY)
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    for descriptor in (
        request_fd,
        result_fd,
        checkpoint_fd,
        ready_read,
        ready_write,
        release_read,
        release_write,
    ):
        os.set_inheritable(descriptor, False)

    loaded: dict[str, object] = {}
    fake_handle = SimpleNamespace(
        np=object(),
        evidence={
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "checkpoint": {
                "transport": "inherited_read_only_descriptor",
                "path_reopened_by_loader": False,
            },
        },
    )
    fake_observation = SimpleNamespace(
        vocals=object(),
        instrumental=object(),
        evidence={
            "geometry": {"frames": 44_100},
            "outputs": {
                "vocals": {"sha256": "c" * 64},
                "instrumental": {"sha256": "d" * 64},
            },
        },
    )

    def fake_load(**kwargs):
        loaded.update(kwargs)
        os.fstat(kwargs["checkpoint_descriptor"])
        return fake_handle

    def fake_handshake(*, ready_fd, release_fd, claim):
        assert ready_fd == ready_write
        assert release_fd == release_read
        assert claim["source_frames"] == 44_100
        os.close(ready_fd)
        os.close(release_fd)

    monkeypatch.setattr(worker, "REQUEST_DESCRIPTOR", request_fd)
    monkeypatch.setattr(worker, "RESULT_DESCRIPTOR", result_fd)
    monkeypatch.setattr(worker, "CHECKPOINT_DESCRIPTOR", checkpoint_fd)
    monkeypatch.setattr(worker, "READY_DESCRIPTOR", ready_write)
    monkeypatch.setattr(worker, "RELEASE_DESCRIPTOR", release_read)
    monkeypatch.setattr(worker, "_inspect_companion_files", lambda _path: _companion_observation())
    monkeypatch.setattr(worker, "_sandbox_canaries", lambda _path: {"all_denied": True})
    monkeypatch.setattr(worker, "_observe_post_cpython_signal_state", lambda: {"expected": True})
    monkeypatch.setattr(worker, "_load_private_melroformer_model", fake_load)
    monkeypatch.setattr(
        worker,
        "_load_private_authorised_excerpt",
        lambda *_args, **_kwargs: (
            object(),
            {"audio_sha256": "e" * 64, "rights_authority": "test"},
        ),
    )
    monkeypatch.setattr(
        worker,
        "_infer_private_melroformer_excerpt",
        lambda *_args, **_kwargs: fake_observation,
    )
    monkeypatch.setattr(worker, "_worker_wait_for_native_image_inventory", fake_handshake)
    monkeypatch.setattr(
        worker,
        "_materialize_private_melroformer_pcm24_quarantine",
        lambda **_kwargs: {
            "schema": "test-quarantine",
            "outputs": [{"relative_path": "STEMS/vocals.wav"}],
        },
    )
    monkeypatch.setattr(worker, "_capture_python_import_closure_claim", lambda **_kwargs: {"claim": True})
    monkeypatch.setattr(worker, "_mark_python_import_closure_stable", lambda value: value)
    monkeypatch.setattr(worker.os, "getpid", lambda: 7171)
    monkeypatch.setattr(worker.os, "getpgrp", lambda: 7171)

    try:
        assert worker._run_private_melroformer_native_worker(
            worker_path=ENTRYPOINT,
            repository_root=REPOSITORY,
        ) == 0
        result = _decode_private_melroformer_native_result(
            result_path.read_bytes(),
            request=request,
        )
    finally:
        for descriptor in (ready_read, release_write):
            os.close(descriptor)

    assert loaded["checkpoint_descriptor"] == checkpoint_fd
    assert loaded["checkpoint_path"] == str(checkpoint_path)
    assert result["private_process_identity"] == {"pid": 7171, "pgid": 7171}
    assert result["child_result"]["descriptor_contract"] == {
        "request_frame_read_from_fd3": True,
        "result_frame_written_to_fd4": True,
        "checkpoint_loaded_from_fd5": True,
        "ready_release_completed_on_fd6_fd7": True,
        "checkpoint_path_reopened": False,
        "logical_descriptors_retained": False,
    }
    assert result["child_result"]["permissions"] == {
        "publication_permitted": False,
        "automatic_selection_permitted": False,
        "product_route_permitted": False,
    }
    assert "/Users/" not in repr(plain(result))
