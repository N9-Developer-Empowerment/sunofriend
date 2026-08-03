from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

from sunofriend import _separation_melroformer_checkpoint_lease as lease_module
from sunofriend import _separation_melroformer_native_session_darwin as session_module
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _request(root: Path, checkpoint: Path):
    return _build_private_melroformer_native_request(
        run_nonce=_digest(f"lease-run:{root}"),
        paths={
            "repository_root": str(root / "repository"),
            "source_root": str(root / "source"),
            "checkpoint_path": str(checkpoint),
            "companion_root": str(root / "companions"),
            "authorisation_report_path": str(root / "authorisation.json"),
            "staging_directory": str(root / "staging"),
        },
        identities={
            "worker_source_sha256": _digest("worker"),
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": _digest("authorisation"),
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "companion_manifest_sha256": _digest("companions"),
        },
        device="cpu",
    )


def _sparse_checkpoint(root: Path) -> Path:
    checkpoint = root / "checkpoint.safetensors"
    descriptor = os.open(
        checkpoint,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        os.ftruncate(descriptor, CONVERSION_CHECKPOINT_BYTES)
    finally:
        os.close(descriptor)
    checkpoint.chmod(0o600)
    return checkpoint


def _inspection() -> dict[str, Any]:
    return {
        "schema": "sunofriend.private-safetensors-static-inspection.v1",
        "status": "verified_header_only_not_deserialized",
        "bytes": CONVERSION_CHECKPOINT_BYTES,
        "sha256": CONVERSION_CHECKPOINT_SHA256,
        "container": "safetensors",
        "header_bytes": 77_111,
        "data_bytes": 456_406_344,
        "tensor_count": 708,
        "tensor_names_sha256": _digest("tensor-names"),
        "dtype_counts": {"BF16": 708},
        "metadata_keys": [],
        "metadata_encoding": "json_null_treated_as_empty_for_mlx_compatibility",
        "metadata_spec_conformant": False,
        "mlx_null_metadata_compatibility_applied": True,
        "metadata_values_observed": False,
        "tensor_values_observed": False,
        "tensor_library_imported": False,
        "descriptor_pinned": True,
        "path_retained": False,
        "authorises_loading": False,
        "authorises_model_import": False,
        "authorises_inference": False,
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "tensor_deserialized": False,
            "model_imported": False,
            "process_started": False,
        },
    }


def _install_static_substitutions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    calls: list[int] = []

    def inspect(descriptor: int, **kwargs: Any):
        assert kwargs == {
            "expected_bytes": CONVERSION_CHECKPOINT_BYTES,
            "expected_sha256": CONVERSION_CHECKPOINT_SHA256,
        }
        assert os.fstat(descriptor).st_size == CONVERSION_CHECKPOINT_BYTES
        calls.append(descriptor)
        return _inspection()

    monkeypatch.setattr(
        lease_module,
        "_inspect_private_safetensors_descriptor",
        inspect,
    )
    monkeypatch.setattr(
        lease_module,
        "_verify_private_melroformer_upstream_evidence",
        lambda _root: {"verification_sha256": _digest("upstream")},
    )
    return calls


def test_private_checkpoint_lease_is_path_free_recheckable_and_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    checkpoint = _sparse_checkpoint(root)
    request = _request(root, checkpoint)
    calls = _install_static_substitutions(monkeypatch)

    lease, observation = (
        lease_module._acquire_private_melroformer_checkpoint_lease(request)
    )
    document = _plain(observation)
    assert document["status"] == "retained_not_loaded"
    assert document["inspection"]["tensor_count"] == 708
    assert document["permissions"] == {
        "model_load_permitted": False,
        "execution_permitted": False,
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }
    assert str(root) not in repr(lease)
    assert all(str(root) not in value for value in _strings(document))

    rechecked = lease_module._recheck_private_melroformer_checkpoint_lease(
        lease
    )
    assert _plain(rechecked) == document
    receipt = lease_module._close_private_melroformer_checkpoint_lease(lease)
    assert receipt["status"] == "closed"
    assert receipt["cleanup"]["status"] == "complete"
    assert _plain(
        lease_module._close_private_melroformer_checkpoint_lease(lease)
    ) == _plain(receipt)
    assert len(calls) == 3


def test_private_checkpoint_lease_detects_path_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    checkpoint = _sparse_checkpoint(root)
    request = _request(root, checkpoint)
    _install_static_substitutions(monkeypatch)
    lease, _observation = (
        lease_module._acquire_private_melroformer_checkpoint_lease(request)
    )
    checkpoint.chmod(0o400)

    with pytest.raises(
        lease_module._PrivateMelroformerCheckpointLeaseError
    ) as caught:
        lease_module._recheck_private_melroformer_checkpoint_lease(lease)
    assert caught.value.receipt["status"] == "integrity_failed"
    assert caught.value.receipt["cleanup"]["status"] == "complete"


def test_private_checkpoint_fd5_reservation_guards_exact_native_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    checkpoint = _sparse_checkpoint(root)
    request = _request(root, checkpoint)
    _install_static_substitutions(monkeypatch)
    lease, observation = (
        lease_module._acquire_private_melroformer_checkpoint_lease(request)
    )
    reservation = lease_module._reserve_private_melroformer_checkpoint_fd5(
        lease,
        current_lease_observation=observation,
    )
    session = object()
    session_observation = object()
    checked_session_observation = {"observation_sha256": _digest("session")}
    admission = object()
    owner = object()
    calls: list[str] = []

    monkeypatch.setattr(
        session_module,
        "_validate_verified_private_melroformer_native_session_observation",
        lambda trusted, value: (
            calls.append("validate_session")
            or checked_session_observation
            if trusted is session and value is session_observation
            else (_ for _ in ()).throw(AssertionError("wrong session"))
        ),
    )

    def issue(**kwargs: Any):
        assert kwargs == {
            "trusted_session": session,
            "session_observation": checked_session_observation,
            "request": request,
        }
        calls.append("issue_admission")
        return admission

    monkeypatch.setattr(
        session_module,
        "_issue_private_melroformer_native_admission",
        issue,
    )

    def start(trusted: Any, **kwargs: Any):
        assert trusted is session
        assert kwargs["session_observation"] is checked_session_observation
        assert kwargs["trusted_admission"] is admission
        assert kwargs["request"] == request
        descriptor = kwargs["checkpoint_read_descriptor"]
        assert os.fstat(descriptor).st_size == CONVERSION_CHECKPOINT_BYTES
        assert os.get_inheritable(descriptor) is False
        assert kwargs["staging_directory"] == request["paths"][
            "staging_directory"
        ]
        assert {
            kwargs["request_read_descriptor"],
            kwargs["result_write_descriptor"],
            kwargs["ready_write_descriptor"],
            kwargs["release_read_descriptor"],
        } == {31, 32, 33, 34}
        calls.append("start")
        return owner

    monkeypatch.setattr(
        session_module,
        "_start_verified_private_melroformer_native_worker",
        start,
    )

    assert (
        lease_module._start_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            current_lease_observation=observation,
            trusted_native_session=session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=request["paths"]["staging_directory"],
            request_read_descriptor=31,
            result_write_descriptor=32,
            ready_write_descriptor=33,
            release_read_descriptor=34,
        )
        is owner
    )
    assert calls == ["validate_session", "issue_admission", "start"]
    with pytest.raises(ValueError, match="remains active"):
        lease_module._close_private_melroformer_checkpoint_lease(lease)
    lease_module._release_private_melroformer_checkpoint_fd5(
        lease,
        reservation,
    )
    assert lease_module._close_private_melroformer_checkpoint_lease(lease)[
        "status"
    ] == "closed"


def test_private_checkpoint_fd5_reservation_rejects_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    checkpoint = _sparse_checkpoint(root)
    request = _request(root, checkpoint)
    _install_static_substitutions(monkeypatch)
    lease, observation = (
        lease_module._acquire_private_melroformer_checkpoint_lease(request)
    )
    reservation = lease_module._reserve_private_melroformer_checkpoint_fd5(
        lease,
        current_lease_observation=observation,
    )

    with pytest.raises(ValueError, match="reservation differs"):
        lease_module._release_private_melroformer_checkpoint_fd5(
            lease,
            object(),
        )
    with pytest.raises(ValueError, match="already reserved"):
        lease_module._reserve_private_melroformer_checkpoint_fd5(
            lease,
            current_lease_observation=observation,
        )
    lease_module._release_private_melroformer_checkpoint_fd5(
        lease,
        reservation,
    )
    lease_module._close_private_melroformer_checkpoint_lease(lease)


@pytest.mark.trusted_local
def test_real_kim_checkpoint_lease_rechecks_without_loading_model(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    private_root = Path(
        "/Users/errolelliott/.local/share/sunofriend/private-evaluation/"
        "kim-vocal-2-mlx-v1"
    )
    checkpoint = private_root / "model.safetensors"
    if not checkpoint.is_file():
        pytest.skip("approved private Kim checkpoint is not installed")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    request = _build_private_melroformer_native_request(
        run_nonce=_digest("real-kim-lease-static-check"),
        paths={
            "repository_root": str(repository),
            "source_root": str(private_root / "mlx-audio-source"),
            "checkpoint_path": str(checkpoint),
            "companion_root": str(private_root / "checkpoint-directory"),
            "authorisation_report_path": str(root / "authorisation.json"),
            "staging_directory": str(root / "staging"),
        },
        identities={
            "worker_source_sha256": _sha256_file(
                repository / "scripts/private-melroformer-native-worker.py"
            ),
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": _digest("authorisation"),
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "companion_manifest_sha256": _digest("companions"),
        },
        device="cpu",
    )

    lease, observation = (
        lease_module._acquire_private_melroformer_checkpoint_lease(request)
    )
    assert observation["inspection"]["tensor_count"] == 708
    lease_module._recheck_private_melroformer_checkpoint_lease(lease)
    receipt = lease_module._close_private_melroformer_checkpoint_lease(lease)
    assert receipt["status"] == "closed"
    assert receipt["effects"]["checkpoint_loaded"] is False
    assert receipt["effects"]["model_imported"] is False


def test_private_checkpoint_lease_has_no_product_route() -> None:
    assert lease_module.__all__ == ()
    assert not any("melroformer" in command for command in PUBLIC_COMMANDS)
    assert not any("melroformer" in command for command in DIRECT_TUI_COMMANDS)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []
