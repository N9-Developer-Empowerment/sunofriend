from __future__ import annotations

import ast
import copy
import hashlib
import os
import pickle
import platform
import stat
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import sunofriend
from sunofriend import _separation_native_session_darwin as session_module
from sunofriend import _separation_fake_executor_darwin as executor_module
from sunofriend import _separation_native_failure_records as failure_records
from sunofriend._separation_checkpoint_canonical import canonical_sha256
from sunofriend._separation_fake_execution_records import (
    _EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    _EXPECTED_FAKE_WORKER_SOURCE_SHA256,
)


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = (
    REPOSITORY
    / "src"
    / "sunofriend"
    / "_separation_native_session_darwin.py"
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def test_session_module_has_one_admission_guarded_spawn_and_no_product_route() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert session_module.__all__ == ()
    assert not hasattr(sunofriend, "_open_verified_native_launcher_session")
    assert "_spawn_bound_fake_worker(" not in source
    spawn_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "spawn_method"
    ]
    assert len(spawn_calls) == 1
    execution = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_execute_verified_native_fake_worker"
    )
    assert spawn_calls[0] in ast.walk(execution)
    assert "_consume_native_start_admission(" in source
    assert "_VerifiedNativeLauncherRun" not in source
    assert "subprocess" not in source
    assert "socket" not in source
    assert "urllib" not in source
    assert "requests" not in source
    for path in (
        REPOSITORY / "src" / "sunofriend" / "__init__.py",
        REPOSITORY / "src" / "sunofriend" / "cli.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert "_separation_native_session_darwin" not in text


def test_session_identity_is_parent_issued_noncopyable_and_nonserializable() -> None:
    session_type = session_module._VerifiedNativeLauncherSession

    with pytest.raises(TypeError, match="parent-issued"):
        session_type()
    value = object.__new__(session_type)
    assert repr(value) == "_VerifiedNativeLauncherSession()"
    with pytest.raises(TypeError, match="copied"):
        copy.copy(value)
    with pytest.raises(TypeError, match="copied"):
        copy.deepcopy(value)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(value)
    with pytest.raises(ValueError, match="not registered"):
        session_module._recheck_verified_native_launcher_session(value)


def test_off_platform_open_fails_before_build_or_file_measurement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(session_module._native_build, "_darwin_host", lambda: False)

    def unexpected_build(**_kwargs: Any) -> Any:
        raise AssertionError("off-platform session tried to build")

    monkeypatch.setattr(
        session_module._native_build,
        "_build_native_launcher",
        unexpected_build,
    )
    with pytest.raises(RuntimeError, match="only on macOS"):
        session_module._open_verified_native_launcher_session(
            cache_root=tmp_path / "must-not-exist"
        )
    assert not (tmp_path / "must-not-exist").exists()


def test_bound_file_measurement_is_full_path_bound_and_offset_independent(
    tmp_path: Path,
) -> None:
    payload = b"measured native-session fixture"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)
    path.chmod(0o600)

    result = session_module._measure_bound_file(
        path.resolve(),
        label="test fixture",
        maximum_bytes=1024,
        executable=False,
        require_not_group_or_other_writable=True,
    )

    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["bytes"] == len(payload)
    assert result["stat_identity"]["mode"] == path.stat().st_mode
    assert result["stat_identity_sha256"] == canonical_sha256(
        result["stat_identity"]
    )


def test_bound_file_measurement_rejects_aliases_and_unsafe_worker_mode(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fixture.bin"
    path.write_bytes(b"fixture")
    path.chmod(0o620)
    alias = tmp_path / "alias.bin"
    alias.symlink_to(path)

    with pytest.raises(RuntimeError, match="ownership or geometry"):
        session_module._measure_bound_file(
            path.resolve(),
            label="unsafe fixture",
            maximum_bytes=1024,
            executable=False,
            require_not_group_or_other_writable=True,
        )
    with pytest.raises(OSError):
        session_module._measure_bound_file(
            alias,
            label="aliased fixture",
            maximum_bytes=1024,
            executable=False,
            require_not_group_or_other_writable=True,
        )


def test_cleanup_reap_after_primary_failure_carries_terminal_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeOwnedChild:
        def __init__(self) -> None:
            self.leader_reaped = False
            self.ownership_released = False
            self.ownership_lost = False

        def wait_nohang(self) -> int:
            raise AssertionError("test uses controlled supervision")

        def signal_owned_group(self, _signal_number: int) -> None:
            raise AssertionError("nonzero test child should not be signaled")

        def matches_pid_and_pgid(
            self,
            _process_id: int,
            _process_group_id: int,
        ) -> bool:
            return False

    owner = FakeOwnedChild()
    module = ModuleType("fake_native_failure_test")
    module._OwnedSpawnChild = FakeOwnedChild  # type: ignore[attr-defined]
    session = object.__new__(session_module._VerifiedNativeLauncherSession)
    state = session_module._SessionState(
        lock=threading.RLock(),
        owner_pid=os.getpid(),
        build=object(),
        module=module,
        spawn_method=lambda *_args: owner,
        artifact_measurement={},
        runtime_path=tmp_path / "runtime",
        runtime_measurement={},
        worker_path=tmp_path / "worker",
        worker_measurement={},
        observation_document={"observation_sha256": "1" * 64},
        run_status="ready",
    )
    with session_module._REGISTRY_LOCK:
        session_module._KNOWN[session] = state
    monkeypatch.setattr(
        executor_module,
        "_consume_native_start_admission",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        session_module,
        "_remeasure_session_state",
        lambda _state: None,
    )
    supervision_calls = 0

    def fail_then_reap(
        native_owner: FakeOwnedChild,
        **_kwargs: object,
    ) -> tuple[int, bool, bool, bool]:
        nonlocal supervision_calls
        supervision_calls += 1
        if supervision_calls == 1:
            raise RuntimeError("synthetic initial supervision failure")
        native_owner.leader_reaped = True
        native_owner.ownership_released = True
        return 7 << 8, True, True, True

    monkeypatch.setattr(
        session_module,
        "_supervise_native_owner",
        fail_then_reap,
    )
    request_path = tmp_path / "request.frame"
    result_path = tmp_path / "result.frame"
    checkpoint_path = tmp_path / "checkpoint.bin"
    request_path.write_bytes(b"request")
    result_path.write_bytes(b"")
    checkpoint_path.write_bytes(b"checkpoint")
    request_descriptor = os.open(request_path, os.O_RDONLY)
    result_write_descriptor = os.open(result_path, os.O_WRONLY)
    result_read_descriptor = os.open(result_path, os.O_RDONLY)
    checkpoint_descriptor = os.open(checkpoint_path, os.O_RDONLY)
    for descriptor in (
        request_descriptor,
        result_write_descriptor,
        result_read_descriptor,
        checkpoint_descriptor,
    ):
        os.set_inheritable(descriptor, False)
    try:
        with pytest.raises(
            session_module._VerifiedNativeLauncherExecutionFailure
        ) as captured:
            session_module._execute_verified_native_fake_worker(
                session,
                trusted_admission=object(),
                fake_launch_plan_v3={  # type: ignore[arg-type]
                    "plan_sha256": "2" * 64
                },
                request_descriptor=request_descriptor,
                owned_result_write_descriptor=result_write_descriptor,
                result_read_descriptor=result_read_descriptor,
                checkpoint_descriptor=checkpoint_descriptor,
            )
        failure = captured.value
        assert isinstance(failure.primary_error, RuntimeError)
        assert "initial supervision" in str(failure.primary_error)
        assert failure.cleanup_errors == ()
        observation = (
            failure_records._validate_exact_reap_failure_observation(
                failure.observation
            )
        )
        assert observation["failure_stage"] == "worker_exit"
        assert observation["process"]["wait"]["exit_code"] == 7
        assert observation["process"]["timed_out"] is True
        assert observation["process"]["term_sent"] is True
        assert observation["process"]["kill_sent"] is True
        assert observation["process"]["leader_reaped"] is True
        assert observation["result"]["validated"] is False
        assert state.run_status == "consumed_failed"
        assert supervision_calls == 2
    finally:
        for descriptor in (
            request_descriptor,
            result_write_descriptor,
            result_read_descriptor,
            checkpoint_descriptor,
        ):
            try:
                os.close(descriptor)
            except OSError:
                pass
        with session_module._REGISTRY_LOCK:
            session_module._KNOWN.pop(session, None)


@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live native launcher sessions require macOS",
)
def test_live_session_imports_one_fresh_build_without_starting_worker(
    tmp_path: Path,
) -> None:
    session, observation = (
        session_module._open_verified_native_launcher_session(
            cache_root=tmp_path / "native-builds"
        )
    )

    assert (
        session_module._recheck_verified_native_launcher_session(session)[
            "observation_sha256"
        ]
        == observation["observation_sha256"]
    )
    document = _plain(observation)
    observation_sha256 = document.pop("observation_sha256")
    assert observation_sha256 == canonical_sha256(document)
    assert document["schema"] == session_module._SESSION_SCHEMA
    assert document["status"] == "verified_not_run"
    assert document["execution_authority"] is False
    assert document["capabilities"] == {
        "fresh_private_build_verified": True,
        "native_artifact_imported": True,
        "spawn_method_bound": True,
        "fake_worker_started": False,
        "real_separation_supported": False,
    }
    assert document["effects"]["process_started"] is False
    assert document["effects"]["worker_started"] is False
    assert document["effects"]["checkpoint_accessed"] is False
    assert document["effects"]["audio_read"] is False
    assert document["effects"]["network_used"] is False
    assert (
        document["bindings"]["fake_worker"]["sha256"]
        == _EXPECTED_FAKE_WORKER_SOURCE_SHA256
    )
    assert (
        document["bindings"]["fake_worker"]["bytes"]
        == _EXPECTED_FAKE_WORKER_SOURCE_BYTES
    )
    assert document["bindings"]["runtime_executable"]["bytes"] == (
        Path(sys.executable).resolve().stat().st_size
    )
    assert stat.S_ISREG(
        document["bindings"]["native_launcher"]["stat_identity"]["mode"]
    )
    assert not any(
        key.endswith("path")
        for key in _strings(document)
        if isinstance(key, str)
    )
    assert not any(
        isinstance(value, str) and value.startswith("/")
        for value in _values(document)
    )


def _strings(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [
            item
            for key, nested in value.items()
            for item in [key, *_strings(nested)]
        ]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _strings(nested)]
    return [value]


def _values(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [
            item
            for nested in value.values()
            for item in [nested, *_values(nested)]
        ]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _values(nested)]
    return [value]
