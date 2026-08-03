from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

from sunofriend import (
    _separation_melroformer_native_one_shot_darwin as one_shot,
)
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
    _decode_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _request(root: Path):
    staging = root / "staging"
    staging.mkdir(mode=0o700)
    return _build_private_melroformer_native_request(
        run_nonce=_digest("one-shot-run"),
        paths={
            "repository_root": str(root / "repository"),
            "source_root": str(root / "source"),
            "checkpoint_path": str(root / "checkpoint.safetensors"),
            "companion_root": str(root / "companions"),
            "authorisation_report_path": str(root / "authorisation.json"),
            "staging_directory": str(staging),
        },
        identities={
            "worker_source_sha256": _digest("worker"),
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": _digest("authorisation"),
            "source_manifest_sha256": _digest("source"),
            "companion_manifest_sha256": _digest("companions"),
        },
        device="cpu",
    )


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def test_one_shot_owns_exact_transport_and_removes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_root(tmp_path)
    request = _request(root)
    transport = root / "transport"
    authority = {
        "trusted_lease": object(),
        "trusted_reservation": object(),
        "trusted_worker_request_v2": object(),
        "current_lease_observation": object(),
        "trusted_native_session": object(),
        "native_session_observation": object(),
    }
    receipt = {"receipt_sha256": _digest("receipt")}

    def coordinate(*args: Any, **kwargs: Any):
        assert args == (authority["trusted_lease"],)
        for key in authority.keys() - {"trusted_lease"}:
            assert kwargs[key] is authority[key]
        assert kwargs["staging_directory"] == request["paths"][
            "staging_directory"
        ]
        request_read = kwargs["request_read_descriptor"]
        result_write = kwargs["result_write_descriptor"]
        result_read = kwargs["result_read_descriptor"]
        assert len({request_read, result_write, result_read}) == 3
        assert not any(
            os.get_inheritable(descriptor)
            for descriptor in (request_read, result_write, result_read)
        )
        request_frame = os.pread(
            request_read,
            os.fstat(request_read).st_size,
            0,
        )
        assert _decode_private_melroformer_native_request(
            request_frame
        ) == request
        assert (os.fstat(result_write).st_dev, os.fstat(result_write).st_ino) == (
            os.fstat(result_read).st_dev,
            os.fstat(result_read).st_ino,
        )
        os.write(result_write, b"result")
        assert os.pread(result_read, 6, 0) == b"result"
        for descriptor in (request_read, result_write, result_read):
            os.close(descriptor)
        return receipt

    monkeypatch.setattr(
        one_shot,
        "_coordinate_reserved_private_melroformer_native_worker_darwin",
        coordinate,
    )

    assert one_shot._run_reserved_private_melroformer_native_one_shot_darwin(
        **authority,
        request=request,
        transport_directory=transport,
    ) == receipt
    assert not transport.exists()
    assert Path(request["paths"]["staging_directory"]).is_dir()


def test_one_shot_preserves_coordinator_error_and_cleans_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_root(tmp_path)
    request = _request(root)
    transport = root / "transport"
    primary = RuntimeError("substituted coordinator failure")

    def fail(*_args: Any, **_kwargs: Any):
        raise primary

    monkeypatch.setattr(
        one_shot,
        "_coordinate_reserved_private_melroformer_native_worker_darwin",
        fail,
    )

    with pytest.raises(
        one_shot._PrivateMelroformerNativeOneShotFailure
    ) as caught:
        one_shot._run_reserved_private_melroformer_native_one_shot_darwin(
            object(),
            trusted_reservation=object(),
            trusted_worker_request_v2=object(),
            current_lease_observation=object(),
            trusted_native_session=object(),
            native_session_observation=object(),
            request=request,
            transport_directory=transport,
        )
    assert caught.value.primary_error is primary
    assert caught.value.cleanup_stages == ()
    assert caught.value.cleanup_errors == ()
    assert not transport.exists()


def test_one_shot_preserves_primary_when_transport_cleanup_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_root(tmp_path)
    request = _request(root)
    transport = root / "transport"
    primary = RuntimeError("substituted coordinator failure")
    real_unlink = one_shot.os.unlink

    monkeypatch.setattr(
        one_shot,
        "_coordinate_reserved_private_melroformer_native_worker_darwin",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(primary),
    )

    def fail_result_unlink(path: str, *, dir_fd: int) -> None:
        if path == one_shot._RESULT_NAME:
            raise PermissionError("substituted result cleanup failure")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(one_shot.os, "unlink", fail_result_unlink)

    with pytest.raises(
        one_shot._PrivateMelroformerNativeOneShotFailure
    ) as caught:
        one_shot._run_reserved_private_melroformer_native_one_shot_darwin(
            object(),
            trusted_reservation=object(),
            trusted_worker_request_v2=object(),
            current_lease_observation=object(),
            trusted_native_session=object(),
            native_session_observation=object(),
            request=request,
            transport_directory=transport,
        )
    assert caught.value.primary_error is primary
    assert caught.value.cleanup_stages == (
        "result_frame_unlink",
        "transport_directory_remove",
    )
    assert len(caught.value.cleanup_errors) == 2


def test_one_shot_rejects_non_private_parent_before_creating_transport(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shared"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    request = _request(root)
    transport = root / "transport"

    with pytest.raises(
        one_shot._PrivateMelroformerNativeOneShotFailure
    ) as caught:
        one_shot._run_reserved_private_melroformer_native_one_shot_darwin(
            object(),
            trusted_reservation=object(),
            trusted_worker_request_v2=object(),
            current_lease_observation=object(),
            trusted_native_session=object(),
            native_session_observation=object(),
            request=request,
            transport_directory=transport,
        )
    assert isinstance(caught.value.primary_error, ValueError)
    assert not transport.exists()


def test_one_shot_is_private_and_has_no_product_route() -> None:
    assert one_shot.__all__ == ()
    assert not any("melroformer" in command for command in PUBLIC_COMMANDS)
    assert not any("melroformer" in command for command in DIRECT_TUI_COMMANDS)
