from __future__ import annotations

import copy
import os
import pickle
import platform
import threading
from pathlib import Path
from types import ModuleType

import pytest

import sunofriend
from sunofriend import _separation_melroformer_native_session_darwin as session
from sunofriend._separation_checkpoint_canonical import deep_freeze
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


def _request(*, nonce: str = "a" * 64, worker_sha256: str = "1" * 64):
    return _build_private_melroformer_native_request(
        run_nonce=nonce,
        paths={
            "repository_root": "/private/tmp/repository",
            "source_root": "/private/tmp/source",
            "checkpoint_path": "/private/tmp/checkpoint.safetensors",
            "companion_root": "/private/tmp/companions",
            "authorisation_report_path": "/private/tmp/authorisation.json",
            "staging_directory": "/private/tmp/staging",
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


def _registered_session():
    base_session = object()
    base_observation = object()
    module = ModuleType("test_private_kim_native")
    spawn = object()
    owner_type = type("_OwnedSpawnChild", (), {})
    trusted = object.__new__(session._VerifiedPrivateMelroformerNativeSession)
    document = deep_freeze(
        {
            "schema": session._SESSION_SCHEMA,
            "observation_sha256": "5" * 64,
        }
    )
    observation = session._session_observation(document)
    state = session._SessionState(
        lock=threading.RLock(),
        owner_pid=os.getpid(),
        base_session=base_session,
        base_observation=base_observation,
        native_module=module,
        spawn_method=spawn,
        owner_type=owner_type,
        runtime_path=Path("/private/tmp/runtime"),
        worker_path=Path(
            "/private/tmp/repository/scripts/private-melroformer-native-worker.py"
        ),
        worker_measurement={"sha256": "1" * 64},
        sandbox_provider_path=Path("/usr/bin/sandbox-exec"),
        sandbox_provider_measurement={},
        observation_document=document,
        observation_object=observation,
        run_status="ready",
    )
    with session._REGISTRY_LOCK:
        session._SESSIONS[trusted] = state
    return trusted, observation, state


def test_session_and_admission_are_private_opaque_capabilities() -> None:
    assert session.__all__ == ()
    assert not hasattr(sunofriend, "_VerifiedPrivateMelroformerNativeSession")
    for capability in (
        session._VerifiedPrivateMelroformerNativeSession,
        session._PrivateMelroformerNativeAdmission,
    ):
        with pytest.raises(TypeError):
            capability()
        value = object.__new__(capability)
        with pytest.raises(TypeError):
            copy.copy(value)
        with pytest.raises(TypeError):
            copy.deepcopy(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_admission_binds_exact_session_request_and_is_single_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, observation, state = _registered_session()
    request = _request()
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)

    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    assert state.run_status == "admission_issued"
    session._consume_private_melroformer_native_admission(
        admission,
        trusted_session=trusted,
        request=request,
    )

    assert state.run_status == "admitted"
    with pytest.raises(ValueError, match="admission is invalid"):
        session._consume_private_melroformer_native_admission(
            admission,
            trusted_session=trusted,
            request=request,
        )
    session._finish_private_melroformer_native_admission(
        admission,
        expected_status="consumed",
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        session._finish_private_melroformer_native_admission(
            admission,
            expected_status="consumed",
        )


def test_admission_rejects_another_request_and_reused_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, observation, _state = _registered_session()
    request = _request(nonce="b" * 64)
    other = _request(nonce="c" * 64)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )

    with pytest.raises(ValueError, match="admission is invalid"):
        session._consume_private_melroformer_native_admission(
            admission,
            trusted_session=trusted,
            request=other,
        )
    session._finish_private_melroformer_native_admission(
        admission,
        expected_status="issued",
    )

    another, another_observation, _ = _registered_session()
    with pytest.raises(ValueError, match="nonce was already used"):
        session._issue_private_melroformer_native_admission(
            trusted_session=another,
            session_observation=another_observation,
            request=request,
        )


def test_admission_rejects_request_not_bound_to_fixed_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, observation, _state = _registered_session()
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)

    with pytest.raises(ValueError, match="does not bind the fixed worker"):
        session._issue_private_melroformer_native_admission(
            trusted_session=trusted,
            session_observation=observation,
            request=_request(nonce="d" * 64, worker_sha256="f" * 64),
        )


def test_session_observation_requires_exact_issued_object_and_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, observation, state = _registered_session()
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)

    assert (
        session._validate_verified_private_melroformer_native_session_observation(
            trusted,
            observation,
        )
        is observation
    )
    replacement = session._session_observation(observation._document)
    with pytest.raises(ValueError, match="exact issued object"):
        session._validate_verified_private_melroformer_native_session_observation(
            trusted,
            replacement,
        )
    state.owner_pid += 1
    with pytest.raises(RuntimeError, match="another process"):
        session._validate_verified_private_melroformer_native_session_observation(
            trusted,
            observation,
        )


def test_module_has_no_spawn_call_or_product_route() -> None:
    source = Path(session.__file__).read_text(encoding="utf-8")
    assert ".spawn_method(" not in source
    assert "subprocess" not in source
    assert "socket" not in source
    for path in (
        Path(sunofriend.__file__),
        Path(sunofriend.__file__).with_name("cli.py"),
    ):
        assert "_separation_melroformer_native_session_darwin" not in (
            path.read_text(encoding="utf-8")
        )


@pytest.mark.trusted_local
@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only session")
def test_fresh_real_session_binds_worker_provider_and_rechecks(
    tmp_path: Path,
) -> None:
    trusted, observation = (
        session._open_verified_private_melroformer_native_session(
            cache_root=tmp_path / "native-cache"
        )
    )

    assert observation["status"] == "verified_not_run"
    assert observation["execution_authority"] is False
    assert observation["capabilities"]["fixed_kim_spawn_method_bound"] is True
    assert observation["capabilities"]["worker_started"] is False
    assert observation["effects"]["checkpoint_opened"] is False
    assert observation["effects"]["audio_read"] is False
    assert (
        session._validate_verified_private_melroformer_native_session_observation(
            trusted,
            observation,
        )
        is observation
    )
