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
    _encode_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


def _request(
    *,
    nonce: str = "a" * 64,
    worker_sha256: str = "1" * 64,
    staging_directory: Path | None = None,
):
    staging = (
        "/private/tmp/staging"
        if staging_directory is None
        else str(staging_directory.resolve())
    )
    return _build_private_melroformer_native_request(
        run_nonce=nonce,
        paths={
            "repository_root": "/private/tmp/repository",
            "source_root": "/private/tmp/source",
            "checkpoint_path": "/private/tmp/checkpoint.safetensors",
            "companion_root": "/private/tmp/companions",
            "authorisation_report_path": "/private/tmp/authorisation.json",
            "staging_directory": staging,
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
    owner_type = type(
        "_OwnedSpawnChild",
        (),
        {
            "start_state": "started_owned",
            "no_start_stage": None,
            "native_status": None,
            "leader_reaped": False,
            "ownership_released": False,
            "ownership_lost": False,
        },
    )
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
        native_owner=None,
    )
    with session._REGISTRY_LOCK:
        session._SESSIONS[trusted] = state
    return trusted, observation, state


def _transport_descriptors(tmp_path: Path, request):
    request_path = tmp_path / "request.frame"
    request_path.write_bytes(_encode_private_melroformer_native_request(request))
    request_read = os.open(request_path, os.O_RDONLY)
    result_path = tmp_path / "result.frame"
    result_write = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    checkpoint_path = tmp_path / "checkpoint.safetensors"
    checkpoint_build = os.open(
        checkpoint_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        os.ftruncate(checkpoint_build, CONVERSION_CHECKPOINT_BYTES)
    finally:
        os.close(checkpoint_build)
    checkpoint_read = os.open(checkpoint_path, os.O_RDONLY)
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    return {
        "request_read_descriptor": request_read,
        "result_write_descriptor": result_write,
        "checkpoint_read_descriptor": checkpoint_read,
        "ready_write_descriptor": ready_write,
        "release_read_descriptor": release_read,
        "parent_descriptors": (ready_read, release_write),
    }


def _close_if_open(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _assert_closed(descriptor: int) -> None:
    with pytest.raises(OSError):
        os.fstat(descriptor)


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


def test_guarded_start_consumes_admission_and_closes_child_transport_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="e" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    calls: list[tuple[object, ...]] = []
    owner = state.owner_type()

    def spawn(*arguments: object) -> object:
        calls.append(arguments)
        return owner

    state.spawn_method = spawn
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    try:
        started = session._start_verified_private_melroformer_native_worker(
            trusted,
            session_observation=observation,
            trusted_admission=admission,
            request=request,
            staging_directory=staging,
            **{
                key: value
                for key, value in descriptors.items()
                if key != "parent_descriptors"
            },
        )

        assert started is owner
        assert state.run_status == "running"
        assert state.native_owner is owner
        assert (
            session._known_started_private_melroformer_native_owner(
                trusted,
                owner,
            )
            is owner
        )
        assert len(calls) == 1
        assert calls[0][:4] == (
            os.fsencode(state.sandbox_provider_path),
            os.fsencode(state.runtime_path),
            os.fsencode(state.worker_path),
            os.fsencode(staging),
        )
        for key in (
            "request_read_descriptor",
            "result_write_descriptor",
            "ready_write_descriptor",
            "release_read_descriptor",
        ):
            _assert_closed(descriptors[key])
        os.fstat(descriptors["checkpoint_read_descriptor"])
        assert os.lseek(descriptors["checkpoint_read_descriptor"], 0, os.SEEK_CUR) == 0
        with pytest.raises(RuntimeError, match="unavailable"):
            session._finish_private_melroformer_native_admission(
                admission,
                expected_status="consumed",
            )
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_running_session_records_one_exact_reap_terminal_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, _observation, state = _registered_session()
    owner = state.owner_type()
    owner.leader_reaped = True
    owner.ownership_released = True
    owner.ownership_lost = False
    state.native_owner = owner
    state.run_status = "running"
    remeasurements: list[object] = []
    monkeypatch.setattr(
        session,
        "_remeasure_state",
        lambda value: remeasurements.append(value),
    )

    receipt = session._finish_started_private_melroformer_native_session(
        trusted,
        owner,
        terminal_observation=_normal_terminal(),
    )

    assert receipt["status"] == "normal_zero_exit_exact_reap_recorded"
    assert receipt["active_owner_released_from_session"] is True
    assert receipt["paths_retained"] is False
    assert all(value is False for value in receipt["permissions"].values())
    assert remeasurements == [state]
    assert state.run_status == "terminal"
    assert state.native_owner is None
    with pytest.raises(ValueError, match="not the active owner"):
        session._finish_started_private_melroformer_native_session(
            trusted,
            owner,
            terminal_observation=_normal_terminal(),
        )


def test_terminal_transition_rejects_incomplete_owner_without_mutating_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, _observation, state = _registered_session()
    owner = state.owner_type()
    state.native_owner = owner
    state.run_status = "running"
    monkeypatch.setattr(session, "_remeasure_state", lambda _value: None)

    with pytest.raises(ValueError, match="not exactly reaped"):
        session._finish_started_private_melroformer_native_session(
            trusted,
            owner,
            terminal_observation=_normal_terminal(),
        )

    assert state.run_status == "running"
    assert state.native_owner is owner


def test_terminal_transition_rejects_nonzero_or_wrong_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, _observation, state = _registered_session()
    owner = state.owner_type()
    owner.leader_reaped = True
    owner.ownership_released = True
    state.native_owner = owner
    state.run_status = "running"
    monkeypatch.setattr(session, "_remeasure_state", lambda _value: None)
    failed = _normal_terminal()
    failed["wait"]["exit_code"] = 1

    with pytest.raises(ValueError, match="did not exit normally"):
        session._finish_started_private_melroformer_native_session(
            trusted,
            owner,
            terminal_observation=failed,
        )
    with pytest.raises(ValueError, match="not the active owner"):
        session._finish_started_private_melroformer_native_session(
            trusted,
            state.owner_type(),
            terminal_observation=_normal_terminal(),
        )
    assert state.run_status == "running"
    assert state.native_owner is owner


def test_failed_terminal_transition_releases_one_exactly_reaped_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, _observation, state = _registered_session()
    owner = state.owner_type()
    owner.leader_reaped = True
    owner.group_empty = True
    owner.ownership_released = True
    owner.ownership_lost = False
    state.native_owner = owner
    state.run_status = "running"
    monkeypatch.setattr(session, "_remeasure_state", lambda _value: None)
    failed = _normal_terminal()
    failed["wait"]["exit_code"] = 7

    receipt = session._finish_failed_started_private_melroformer_native_session(
        trusted,
        owner,
        terminal_observation=failed,
    )

    assert receipt["status"] == "failed_run_exact_reap_recorded"
    assert receipt["execution_success_claimed"] is False
    assert receipt["active_owner_released_from_session"] is True
    assert state.run_status == "terminal"
    assert state.native_owner is None


def test_failed_terminal_transition_rejects_normal_or_incomplete_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, _observation, state = _registered_session()
    owner = state.owner_type()
    owner.leader_reaped = True
    owner.group_empty = True
    owner.ownership_released = True
    state.native_owner = owner
    state.run_status = "running"
    monkeypatch.setattr(session, "_remeasure_state", lambda _value: None)

    with pytest.raises(ValueError, match="failed exit evidence differs"):
        session._finish_failed_started_private_melroformer_native_session(
            trusted,
            owner,
            terminal_observation=_normal_terminal(),
        )
    failed = _normal_terminal()
    failed["wait"]["exit_code"] = 3
    failed["group_empty"] = False
    with pytest.raises(ValueError, match="ownership is incomplete"):
        session._finish_failed_started_private_melroformer_native_session(
            trusted,
            owner,
            terminal_observation=failed,
        )
    assert state.run_status == "running"
    assert state.native_owner is owner


def test_guarded_start_rejects_wrong_pipe_geometry_without_spawning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="f" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    calls: list[tuple[object, ...]] = []
    state.spawn_method = lambda *arguments: calls.append(arguments)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    ready = descriptors["ready_write_descriptor"]
    release = descriptors["release_read_descriptor"]
    descriptors["ready_write_descriptor"] = release
    descriptors["release_read_descriptor"] = ready
    try:
        with pytest.raises(ValueError, match="descriptor geometry differs"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == []
        assert state.run_status == "ready"
        assert state.native_owner is None
        _assert_closed(ready)
        _assert_closed(release)
        os.fstat(descriptors["checkpoint_read_descriptor"])
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_invalid_duplicate_never_closes_checkpoint_lease_descriptor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="6" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    original_request = descriptors["request_read_descriptor"]
    checkpoint = descriptors["checkpoint_read_descriptor"]
    descriptors["request_read_descriptor"] = checkpoint
    calls: list[tuple[object, ...]] = []
    state.spawn_method = lambda *arguments: calls.append(arguments)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    try:
        with pytest.raises(ValueError, match="descriptors are invalid"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == []
        assert state.run_status == "ready"
        os.fstat(checkpoint)
        assert os.lseek(checkpoint, 0, os.SEEK_CUR) == 0
    finally:
        _close_if_open(original_request)
        _close_if_open(checkpoint)
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_unhashable_invalid_descriptor_still_retires_admission_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="5" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    original_request = descriptors["request_read_descriptor"]
    descriptors["request_read_descriptor"] = []
    calls: list[tuple[object, ...]] = []
    state.spawn_method = lambda *arguments: calls.append(arguments)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    try:
        with pytest.raises(ValueError, match="descriptors are invalid"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == []
        assert state.run_status == "ready"
        os.fstat(descriptors["checkpoint_read_descriptor"])
        for key in (
            "result_write_descriptor",
            "ready_write_descriptor",
            "release_read_descriptor",
        ):
            _assert_closed(descriptors[key])
    finally:
        _close_if_open(original_request)
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_invalid_request_still_retires_admission_and_transferred_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="4" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    calls: list[tuple[object, ...]] = []
    state.spawn_method = lambda *arguments: calls.append(arguments)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    invalid_request = session._plain(request)
    invalid_request["request_sha256"] = "f" * 64
    try:
        with pytest.raises(ValueError, match="request identity differs"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=invalid_request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == []
        assert state.run_status == "ready"
        os.fstat(descriptors["checkpoint_read_descriptor"])
        for key in (
            "request_read_descriptor",
            "result_write_descriptor",
            "ready_write_descriptor",
            "release_read_descriptor",
        ):
            _assert_closed(descriptors[key])
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_guarded_start_rejects_request_frame_drift_and_requires_exact_admission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="7" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    calls: list[tuple[object, ...]] = []
    state.spawn_method = lambda *arguments: calls.append(arguments)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    with (tmp_path / "request.frame").open("r+b") as changed_request:
        changed_request.write(b"x")
    try:
        with pytest.raises(ValueError, match="request descriptor content differs"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == []
        assert state.run_status == "ready"
        assert state.native_owner is None
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_guarded_start_marks_native_call_exception_unproven(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="8" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    calls = 0

    def spawn(*_arguments: object) -> object:
        nonlocal calls
        calls += 1
        raise OSError("synthetic spawn failure")

    state.spawn_method = spawn
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    try:
        with pytest.raises(OSError, match="synthetic spawn failure"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == 1
        assert state.run_status == "consumed_start_unproven"
        assert state.native_owner is None
        for key in (
            "request_read_descriptor",
            "result_write_descriptor",
            "ready_write_descriptor",
            "release_read_descriptor",
        ):
            _assert_closed(descriptors[key])
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_guarded_start_rejects_non_private_staging_before_admission_consumption(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o755)
    request = _request(nonce="9" * 64, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    calls: list[tuple[object, ...]] = []
    state.spawn_method = lambda *arguments: calls.append(arguments)
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    try:
        with pytest.raises(ValueError, match="staging directory is not owner-only"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert calls == []
        assert state.run_status == "ready"
        assert state.native_owner is None
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_guarded_start_rejects_exact_no_start_without_retaining_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    trusted, observation, state = _registered_session()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir(mode=0o700)
    request = _request(nonce="0a" * 32, staging_directory=staging)
    descriptors = _transport_descriptors(tmp_path, request)
    owner = state.owner_type()
    owner.start_state = "not_started"
    owner.no_start_stage = "posix_spawn"
    owner.native_status = 2
    state.spawn_method = lambda *_arguments: owner
    monkeypatch.setattr(session, "_remeasure_state", lambda value: None)
    admission = session._issue_private_melroformer_native_admission(
        trusted_session=trusted,
        session_observation=observation,
        request=request,
    )
    try:
        with pytest.raises(RuntimeError, match="worker was not started"):
            session._start_verified_private_melroformer_native_worker(
                trusted,
                session_observation=observation,
                trusted_admission=admission,
                request=request,
                staging_directory=staging,
                **{
                    key: value
                    for key, value in descriptors.items()
                    if key != "parent_descriptors"
                },
            )
        assert state.run_status == "consumed_no_start"
        assert state.native_owner is None
        with pytest.raises(RuntimeError, match="unavailable"):
            session._finish_private_melroformer_native_admission(
                admission,
                expected_status="consumed",
            )
    finally:
        _close_if_open(descriptors["checkpoint_read_descriptor"])
        for descriptor in descriptors["parent_descriptors"]:
            _close_if_open(descriptor)


def test_module_has_one_guarded_spawn_call_and_no_product_route() -> None:
    source = Path(session.__file__).read_text(encoding="utf-8")
    assert source.count("state.spawn_method(") == 1
    assert "subprocess" not in source
    assert "socket" not in source
    for path in (
        Path(sunofriend.__file__),
        Path(sunofriend.__file__).with_name("cli.py"),
    ):
        assert "_separation_melroformer_native_session_darwin" not in (
            path.read_text(encoding="utf-8")
        )


def _normal_terminal() -> dict[str, object]:
    return {
        "wait": {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "leader_exit_observed": True,
        "leader_reaped": True,
        "group_empty": True,
        "ownership_released": True,
        "ownership_lost": False,
    }


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
