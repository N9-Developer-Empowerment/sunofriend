from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
from pathlib import Path

import pytest

import sunofriend._separation_macos_process_image as process_image
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_validates_exact_path_free_model_free_observation() -> None:
    evidence = process_image._validate_private_macos_runtime_process_image(
        _evidence()
    )

    assert evidence["status"] == "runtime_process_image_parent_observed"
    assert evidence["runtime"]["process_image"][
        "static_and_kernel_cdhash_match"
    ] is True
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in repr(evidence)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["runtime"]["process_image"].__setitem__(
                "observed_kernel_cdhash", "d" * 40
            ),
            "kernel identity",
        ),
        (
            lambda value: value["permissions"].__setitem__(
                "model_import_permitted", True
            ),
            "grants a permission",
        ),
        (
            lambda value: value["conclusion"].__setitem__(
                "bound_to_model_worker", True
            ),
            "conclusion",
        ),
        (
            lambda value: value["limitations"].__setitem__(
                "provider_runtime_complete_byte_identity_toctou_closed", True
            ),
            "limitations",
        ),
    ],
)
def test_rejects_resigned_semantic_overclaims(mutate: object, message: str) -> None:
    value = _evidence()
    mutate(value)  # type: ignore[operator]
    _resign(value)

    with pytest.raises(ValueError, match=message):
        process_image._validate_private_macos_runtime_process_image(value)


def test_observer_waits_for_provider_to_exec_expected_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "provider"
    runtime = tmp_path / "runtime"
    provider.write_bytes(b"provider")
    runtime.write_bytes(b"runtime")
    paths = iter((provider, provider, runtime))
    monkeypatch.setattr(process_image, "_proc_pidpath", lambda _pid: next(paths))
    monkeypatch.setattr(process_image, "_pid_cdhash", lambda _pid: "c" * 40)

    observed = process_image._observe_process_image(
        123,
        provider_path=provider,
        runtime_launcher_path=runtime,
        expected_image_path=runtime,
        expected_cdhash="c" * 40,
    )

    assert observed == {
        "kernel_cdhash": "c" * 40,
        "path_state": "matched_expected_process_image",
    }


def test_observer_rejects_an_unexpected_process_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "provider"
    runtime = tmp_path / "runtime"
    substitute = tmp_path / "substitute"
    for path in (provider, runtime, substitute):
        path.write_bytes(path.name.encode())
    monkeypatch.setattr(process_image, "_proc_pidpath", lambda _pid: substitute)

    with pytest.raises(RuntimeError, match="path differs"):
        process_image._observe_process_image(
            123,
            provider_path=provider,
            runtime_launcher_path=runtime,
            expected_image_path=runtime,
            expected_cdhash="c" * 40,
        )


def test_observer_rejects_a_different_kernel_cdhash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "provider"
    runtime = tmp_path / "runtime"
    provider.write_bytes(b"provider")
    runtime.write_bytes(b"runtime")
    monkeypatch.setattr(process_image, "_proc_pidpath", lambda _pid: runtime)
    monkeypatch.setattr(process_image, "_pid_cdhash", lambda _pid: "d" * 40)

    with pytest.raises(RuntimeError, match="CDHash differs"):
        process_image._observe_process_image(
            123,
            provider_path=provider,
            runtime_launcher_path=runtime,
            expected_image_path=runtime,
            expected_cdhash="c" * 40,
        )


def test_python_org_framework_transition_is_explicit(tmp_path: Path) -> None:
    version = tmp_path / "Versions" / "3.12"
    runtime = version / "bin" / "python3.12"
    image = version / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    runtime.parent.mkdir(parents=True)
    image.parent.mkdir(parents=True)
    runtime.write_bytes(b"launcher")
    image.write_bytes(b"image")

    assert process_image._expected_python_process_image(runtime) == image


def test_non_framework_runtime_remains_its_own_process_image(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.write_bytes(b"runtime")

    assert process_image._expected_python_process_image(runtime) == runtime


def test_parent_canary_builds_zero_permission_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "provider"
    launcher = tmp_path / "python"
    image = tmp_path / "Python"
    for path in (provider, launcher, image):
        path.write_bytes(path.name.encode())
    identities = {
        str(provider): _identity(provider, "provider"),
        str(launcher): _identity(launcher, "launcher"),
        str(image): _identity(image, "image"),
    }
    monkeypatch.setattr(process_image.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(process_image.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(process_image, "SANDBOX_EXEC_PATH", provider)
    monkeypatch.setattr(
        process_image,
        "_regular_file_identity",
        lambda path: dict(identities[str(Path(path).absolute())]),
    )
    monkeypatch.setattr(
        process_image, "_expected_python_process_image", lambda _path: image
    )
    cdhashes = {provider: "a" * 40, launcher: "b" * 40, image: "c" * 40}
    monkeypatch.setattr(
        process_image,
        "_static_code_identity",
        lambda path: {"cdhash": cdhashes[Path(path)]},
    )
    monkeypatch.setattr(process_image, "_filesystem_is_read_only", lambda _: True)
    monkeypatch.setattr(
        process_image,
        "_observe_process_image",
        lambda *_args, **_kwargs: {
            "kernel_cdhash": "c" * 40,
            "path_state": "matched_expected_process_image",
        },
    )
    monkeypatch.setattr(
        process_image.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(args, kwargs),
    )

    evidence = process_image._run_private_macos_runtime_process_image_canary(
        runtime_path=launcher
    )

    assert evidence["runtime"]["transition"] == (
        "python-org-framework-launcher-to-app-image"
    )
    assert evidence["conclusion"][
        "runtime_process_code_identity_bound_to_exact_child_pid"
    ] is True
    assert evidence["conclusion"]["bound_to_model_worker"] is False
    assert all(value is False for value in evidence["permissions"].values())


def test_prepared_binding_seals_exact_child_without_retaining_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "provider"
    launcher = tmp_path / "python"
    image = tmp_path / "Python"
    for path in (provider, launcher, image):
        path.write_bytes(path.name.encode())
    identities = {
        str(provider): _identity(provider, "provider"),
        str(launcher): _identity(launcher, "launcher"),
        str(image): _identity(image, "image"),
    }
    monkeypatch.setattr(process_image.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(process_image.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(process_image, "SANDBOX_EXEC_PATH", provider)
    monkeypatch.setattr(
        process_image,
        "_regular_file_identity",
        lambda path: dict(identities[str(Path(path).absolute())]),
    )
    monkeypatch.setattr(
        process_image, "_expected_python_process_image", lambda _path: image
    )
    cdhashes = {provider: "a" * 40, launcher: "b" * 40, image: "c" * 40}
    monkeypatch.setattr(
        process_image,
        "_static_code_identity",
        lambda path: {"cdhash": cdhashes[Path(path)]},
    )
    monkeypatch.setattr(process_image, "_filesystem_is_read_only", lambda _: True)
    monkeypatch.setattr(
        process_image,
        "_observe_process_image",
        lambda *_args, **_kwargs: {
            "kernel_cdhash": "c" * 40,
            "path_state": "matched_expected_process_image",
        },
    )

    prepared = process_image._prepare_runtime_process_image_binding(
        runtime_path=launcher
    )
    observed = process_image._observe_prepared_runtime_process_image(
        123, prepared=prepared
    )
    evidence = process_image._complete_runtime_process_image_binding(
        prepared=prepared,
        observed=observed,
    )

    assert evidence["schema"] == process_image.BINDING_SCHEMA
    assert evidence["runtime"]["process_image"][
        "static_and_kernel_cdhash_match"
    ] is True
    assert evidence["conclusion"][
        "runtime_process_code_identity_bound_to_exact_child_pid"
    ] is True
    assert "/Users/" not in repr(evidence)
    assert str(tmp_path) not in repr(evidence)

    changed = process_image._plain(evidence)
    changed["limitations"]["dynamic_native_library_closure_bound"] = True
    _resign(changed)
    with pytest.raises(ValueError, match="binding limitations"):
        process_image._validate_runtime_process_image_binding(changed)


def test_private_runner_writes_owner_only_and_never_replaces(
    tmp_path: Path,
) -> None:
    script = (
        Path(__file__).parents[1]
        / "scripts"
        / "private-macos-runtime-process-image.py"
    )
    specification = importlib.util.spec_from_file_location(
        "private_macos_runtime_process_image_script", script
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    destination = tmp_path / "observation.json"

    module._write_private_observation(destination, '{"status":"fixture"}\n')

    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "status": "fixture"
    }
    with pytest.raises(FileExistsError):
        module._write_private_observation(destination, "{}\n")


def test_runtime_process_image_has_no_public_route() -> None:
    assert "private-macos-runtime-process-image" not in PUBLIC_COMMANDS
    assert "private-macos-runtime-process-image" not in DIRECT_TUI_COMMANDS
    assert process_image.__all__ == ()


class _FakeProcess:
    def __init__(self, args: object, kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs
        self.pid = 123
        self.returncode = 0

    def communicate(self, timeout: float) -> tuple[bytes, bytes]:
        assert timeout == 3.0
        return (
            b'{"arithmetic":42,"probe_id":"parent-pid-code-identity-v1"}\n',
            b"",
        )

    def poll(self) -> int:
        return 0

    def kill(self) -> None:
        raise AssertionError("completed fake child must not be killed")

    def wait(self, timeout: float) -> int:
        assert timeout == 3.0
        return 0


def _identity(path: Path, label: str) -> dict[str, object]:
    return {
        "resolved_path": str(path.absolute()),
        "bytes": len(label),
        "sha256": hashlib.sha256(label.encode()).hexdigest(),
    }


def _evidence() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": process_image.SCHEMA,
        "policy_id": process_image.POLICY_ID,
        "status": "runtime_process_image_parent_observed",
        "platform": {"system": "Darwin", "machine": "arm64"},
        "provider": {
            "bytes": 100,
            "sha256": "a" * 64,
            "static_cdhash": "a" * 40,
            "strict_code_signature_valid": True,
            "filesystem_read_only": True,
        },
        "runtime": {
            "launcher": {
                "bytes": 101,
                "sha256": "b" * 64,
                "static_cdhash": "b" * 40,
                "strict_code_signature_valid": True,
            },
            "process_image": {
                "bytes": 102,
                "sha256": "c" * 64,
                "static_cdhash": "c" * 40,
                "observed_kernel_cdhash": "c" * 40,
                "strict_code_signature_valid": True,
                "static_and_kernel_cdhash_match": True,
            },
            "transition": "python-org-framework-launcher-to-app-image",
        },
        "observation": {
            "probe_id": process_image.PROBE_ID,
            "exact_child_pid_observed": True,
            "child_pid_retained": False,
            "parent_proc_pidpath_used": True,
            "parent_csops_cdhash_used": True,
            "process_image_path_matched_expected": True,
            "artifacts_unchanged_after_child": True,
            "network_attempted": False,
            "filesystem_written": False,
        },
        "conclusion": {
            "provider_path_mutation_confined_by_read_only_filesystem": True,
            "runtime_process_code_identity_bound_to_exact_child_pid": True,
            "runtime_launcher_transition_explicit": True,
            "bound_to_model_worker": False,
            "separator_enabled": False,
        },
        "permissions": {
            "model_import_permitted": False,
            "checkpoint_access_permitted": False,
            "authorised_audio_access_permitted": False,
            "separator_execution_permitted": False,
            "source_graph_activation_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "process_started": True,
            "filesystem_written": False,
            "network_used": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_read": False,
            "source_graph_changed": False,
        },
        "limitations": {
            "model_free_canary_only": True,
            "authorised_worker_not_bound": True,
            "provider_runtime_complete_byte_identity_toctou_closed": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
            "code_signature_identity_is_not_full_file_sha256": True,
        },
    }
    payload["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _resign(value: dict[str, object]) -> None:
    value.pop("evidence_sha256", None)
    value["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()
