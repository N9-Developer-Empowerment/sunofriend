from __future__ import annotations

import copy
import hashlib
import pickle
import platform
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import sunofriend
from sunofriend import _separation_native_session_darwin as session_module
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


def test_session_module_is_private_and_has_no_spawn_call_or_product_route() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert session_module.__all__ == ()
    assert not hasattr(sunofriend, "_open_verified_native_launcher_session")
    assert "_spawn_bound_fake_worker(" not in source
    assert ".spawn_method(" not in source
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
