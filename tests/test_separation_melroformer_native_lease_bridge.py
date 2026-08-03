from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from sunofriend import _separation_melroformer_native_session_darwin as session
from sunofriend._separation_checkpoint_canonical import deep_freeze
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend import separation_checkpoint_descriptor_lease as lease_module


def _request(*, checkpoint_path: Path, worker_sha256: str = "1" * 64):
    root = checkpoint_path.parent
    return _build_private_melroformer_native_request(
        run_nonce="a" * 64,
        paths={
            "repository_root": str(root / "repository"),
            "source_root": str(root / "source"),
            "checkpoint_path": str(checkpoint_path),
            "companion_root": str(root / "companions"),
            "authorisation_report_path": str(root / "authorisation.json"),
            "staging_directory": str(root / "staging"),
        },
        identities={
            "worker_source_sha256": worker_sha256,
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": "2" * 64,
            "source_manifest_sha256": "3" * 64,
            "companion_manifest_sha256": "4" * 64,
        },
        device="cpu",
    )


def _lease_observation(*, checkpoint_sha256: str = CONVERSION_CHECKPOINT_SHA256):
    document = deep_freeze(
        {
            "bindings": {
                "checkpoint_sha256": checkpoint_sha256,
                "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            },
            "observation_sha256": "5" * 64,
        }
    )
    return lease_module._observation_wrapper(document), document


def _worker_request(observation, *, checkpoint_sha256=CONVERSION_CHECKPOINT_SHA256):
    return deep_freeze(
        {
            "bindings": {
                "lease_observation_sha256": observation[
                    "observation_sha256"
                ],
                "checkpoint_sha256": checkpoint_sha256,
                "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            }
        }
    )


def _session_observation(*, worker_sha256: str = "1" * 64):
    return deep_freeze(
        {
            "bindings": {
                "fixed_kim_worker": {"sha256": worker_sha256},
            }
        }
    )


def _install_substituted_lease(
    monkeypatch: pytest.MonkeyPatch,
    *,
    checkpoint_path: Path,
    descriptor: int,
    observation,
    observation_document,
    worker_request,
):
    lease = object.__new__(lease_module.SeparationCheckpointDescriptorLease)
    reservation = object()
    binding = SimpleNamespace(
        authority=reservation,
        worker_request_v2=worker_request,
        lease_observation=observation,
    )
    state = SimpleNamespace(
        lock=threading.RLock(),
        owner_pid=os.getpid(),
        descriptor=descriptor,
        request=SimpleNamespace(checkpoint_path=checkpoint_path),
        observation_document=observation_document,
        fd5_reservation=binding,
    )
    monkeypatch.setattr(
        lease_module,
        "_known_state",
        lambda value: (lease, state),
    )
    monkeypatch.setattr(
        lease_module,
        "_require_active_state_for_reservation",
        lambda *_args: None,
    )
    monkeypatch.setattr(lease_module, "_require_owner", lambda *_args: None)
    monkeypatch.setattr(
        lease_module,
        "_validate_state_authority",
        lambda *_args: None,
    )
    monkeypatch.setattr(lease_module, "_remeasure", lambda *_args: None)
    monkeypatch.setattr(
        lease_module,
        "_require_fd5_reservation_authority",
        lambda value, expected: (
            None
            if value is expected.authority
            else (_ for _ in ()).throw(ValueError("reservation differs"))
        ),
    )
    return lease, reservation, state


def test_private_native_start_receives_fd5_only_inside_the_locked_lease_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_path = (tmp_path / "checkpoint.safetensors").resolve()
    checkpoint_path.write_bytes(b"model-free-descriptor")
    descriptor = os.open(checkpoint_path, os.O_RDONLY)
    observation, observation_document = _lease_observation()
    worker_request = _worker_request(observation)
    trusted_lease, reservation, state = _install_substituted_lease(
        monkeypatch,
        checkpoint_path=checkpoint_path,
        descriptor=descriptor,
        observation=observation,
        observation_document=observation_document,
        worker_request=worker_request,
    )
    request = _request(checkpoint_path=checkpoint_path)
    native_observation = _session_observation()
    native_session = object()
    admission = object()
    owner = object()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        session,
        "_validate_verified_private_melroformer_native_session_observation",
        lambda trusted, value: value,
    )
    monkeypatch.setattr(
        session,
        "_issue_private_melroformer_native_admission",
        lambda **_kwargs: admission,
    )

    def start(trusted, **kwargs):
        assert trusted is native_session
        calls.append(kwargs)
        return owner

    monkeypatch.setattr(
        session,
        "_start_verified_private_melroformer_native_worker",
        start,
    )
    try:
        result = (
            lease_module._start_reserved_private_melroformer_native_worker_darwin(
                trusted_lease,
                trusted_reservation=reservation,
                trusted_worker_request_v2=worker_request,
                current_lease_observation=observation,
                trusted_native_session=native_session,
                native_session_observation=native_observation,
                request=request,
                staging_directory=request["paths"]["staging_directory"],
                request_read_descriptor=11,
                result_write_descriptor=12,
                ready_write_descriptor=13,
                release_read_descriptor=14,
            )
        )

        assert result is owner
        assert len(calls) == 1
        assert calls[0]["checkpoint_read_descriptor"] == descriptor
        assert calls[0]["trusted_admission"] is admission
        assert calls[0]["request"] == request
        assert state.fd5_reservation is not None
        os.fstat(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "lease_sha,worker_sha,session_worker_sha,checkpoint_name,message",
    [
        (
            "f" * 64,
            CONVERSION_CHECKPOINT_SHA256,
            "1" * 64,
            "checkpoint.safetensors",
            "does not bind the leased checkpoint",
        ),
        (
            CONVERSION_CHECKPOINT_SHA256,
            "f" * 64,
            "1" * 64,
            "checkpoint.safetensors",
            "reserved worker request does not bind",
        ),
        (
            CONVERSION_CHECKPOINT_SHA256,
            CONVERSION_CHECKPOINT_SHA256,
            "9" * 64,
            "checkpoint.safetensors",
            "does not bind the fixed session worker",
        ),
        (
            CONVERSION_CHECKPOINT_SHA256,
            CONVERSION_CHECKPOINT_SHA256,
            "1" * 64,
            "other.safetensors",
            "checkpoint path differs",
        ),
    ],
)
def test_private_native_lease_bridge_rejects_cross_binding_drift_before_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lease_sha: str,
    worker_sha: str,
    session_worker_sha: str,
    checkpoint_name: str,
    message: str,
) -> None:
    checkpoint_path = (tmp_path / "checkpoint.safetensors").resolve()
    checkpoint_path.write_bytes(b"model-free-descriptor")
    descriptor = os.open(checkpoint_path, os.O_RDONLY)
    observation, observation_document = _lease_observation(
        checkpoint_sha256=lease_sha
    )
    worker_request = _worker_request(
        observation,
        checkpoint_sha256=worker_sha,
    )
    trusted_lease, reservation, state = _install_substituted_lease(
        monkeypatch,
        checkpoint_path=checkpoint_path,
        descriptor=descriptor,
        observation=observation,
        observation_document=observation_document,
        worker_request=worker_request,
    )
    request_path = (tmp_path / checkpoint_name).resolve()
    request = _request(checkpoint_path=request_path)
    admission_calls: list[object] = []
    monkeypatch.setattr(
        session,
        "_validate_verified_private_melroformer_native_session_observation",
        lambda trusted, value: value,
    )
    monkeypatch.setattr(
        session,
        "_issue_private_melroformer_native_admission",
        lambda **kwargs: admission_calls.append(kwargs),
    )
    monkeypatch.setattr(
        session,
        "_start_verified_private_melroformer_native_worker",
        lambda *_args, **_kwargs: pytest.fail("native start must not run"),
    )
    try:
        with pytest.raises(ValueError, match=message):
            lease_module._start_reserved_private_melroformer_native_worker_darwin(
                trusted_lease,
                trusted_reservation=reservation,
                trusted_worker_request_v2=worker_request,
                current_lease_observation=observation,
                trusted_native_session=object(),
                native_session_observation=_session_observation(
                    worker_sha256=session_worker_sha
                ),
                request=request,
                staging_directory=request["paths"]["staging_directory"],
                request_read_descriptor=11,
                result_write_descriptor=12,
                ready_write_descriptor=13,
                release_read_descriptor=14,
            )
        assert admission_calls == []
        assert state.fd5_reservation is not None
        os.fstat(descriptor)
    finally:
        os.close(descriptor)


def test_private_native_lease_bridge_rejects_substituted_reservation_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_path = (tmp_path / "checkpoint.safetensors").resolve()
    checkpoint_path.write_bytes(b"model-free-descriptor")
    descriptor = os.open(checkpoint_path, os.O_RDONLY)
    observation, observation_document = _lease_observation()
    worker_request = _worker_request(observation)
    trusted_lease, reservation, _state = _install_substituted_lease(
        monkeypatch,
        checkpoint_path=checkpoint_path,
        descriptor=descriptor,
        observation=observation,
        observation_document=observation_document,
        worker_request=worker_request,
    )
    request = _request(checkpoint_path=checkpoint_path)
    monkeypatch.setattr(
        session,
        "_validate_verified_private_melroformer_native_session_observation",
        lambda trusted, value: value,
    )
    try:
        with pytest.raises(ValueError, match="reservation differs"):
            lease_module._start_reserved_private_melroformer_native_worker_darwin(
                trusted_lease,
                trusted_reservation=object(),
                trusted_worker_request_v2=worker_request,
                current_lease_observation=observation,
                trusted_native_session=object(),
                native_session_observation=_session_observation(),
                request=request,
                staging_directory=request["paths"]["staging_directory"],
                request_read_descriptor=11,
                result_write_descriptor=12,
                ready_write_descriptor=13,
                release_read_descriptor=14,
            )
        with pytest.raises(ValueError, match="exact reserved request"):
            lease_module._start_reserved_private_melroformer_native_worker_darwin(
                trusted_lease,
                trusted_reservation=reservation,
                trusted_worker_request_v2=deep_freeze(dict(worker_request)),
                current_lease_observation=observation,
                trusted_native_session=object(),
                native_session_observation=_session_observation(),
                request=request,
                staging_directory=request["paths"]["staging_directory"],
                request_read_descriptor=11,
                result_write_descriptor=12,
                ready_write_descriptor=13,
                release_read_descriptor=14,
            )
    finally:
        os.close(descriptor)


def test_private_native_lease_binding_validator_rejects_incomplete_evidence(
    tmp_path: Path,
) -> None:
    checkpoint_path = (tmp_path / "checkpoint.safetensors").resolve()
    observation, _document = _lease_observation()

    with pytest.raises(ValueError, match="binding evidence is incomplete"):
        lease_module._validate_private_melroformer_native_lease_bindings(
            request=_request(checkpoint_path=checkpoint_path),
            lease_observation=observation,
            inspection_request=SimpleNamespace(
                checkpoint_path=checkpoint_path,
            ),
            worker_request_v2=_worker_request(observation),
            native_session_observation=deep_freeze(
                {"bindings": {"fixed_kim_worker": {}}}
            ),
        )
