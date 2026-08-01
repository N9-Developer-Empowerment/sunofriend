from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_melroformer_runtime_evidence as evidence
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_tracked_runtime_evidence_is_exact_and_non_authorising() -> None:
    root = Path(__file__).parents[1]
    result = evidence._verify_tracked_melroformer_runtime_evidence(root)

    assert result["status"] == "verified_not_installed_not_imported"
    assert result["source_manifest"]["sha256"] == evidence.SOURCE_MANIFEST_SHA256
    assert result["runtime_lock"]["sha256"] == evidence.RUNTIME_LOCK_SHA256
    assert result["runtime_lock"]["packages"] == ["mlx", "mlx-metal", "numpy"]
    assert result["loader_policy"]["upstream_from_pretrained_permitted"] is False
    assert result["stale_runtime_licence_comment_recorded"] is True
    assert result["authorises_installation"] is False
    assert result["authorises_model_import"] is False
    assert result["effects"]["network_used"] is False


def test_source_manifest_records_exact_release_and_loader_boundary() -> None:
    root = Path(__file__).parents[1]
    contents = (root / evidence.SOURCE_MANIFEST).read_bytes()
    manifest = json.loads(contents)

    assert hashlib.sha256(contents).hexdigest() == evidence.SOURCE_MANIFEST_SHA256
    assert manifest["release"] == "v0.4.3"
    assert manifest["revision"] == evidence.SOURCE_REVISION
    assert manifest["loader_policy"]["upstream_from_pretrained_permitted"] is False
    assert manifest["loader_policy"]["local_checkpoint_descriptor_required"] is True
    assert manifest["licence_note"]["stale_runtime_documentation_found"] is True
    assert manifest["authorises_inference"] is False


def test_runtime_lock_is_minimal_hash_pinned_and_not_an_installer() -> None:
    root = Path(__file__).parents[1]
    contents = (root / evidence.RUNTIME_LOCK).read_bytes()
    lock = json.loads(contents)

    assert hashlib.sha256(contents).hexdigest() == evidence.RUNTIME_LOCK_SHA256
    assert [item["name"] for item in lock["packages"]] == [
        "mlx",
        "mlx-metal",
        "numpy",
    ]
    assert all(len(item["sha256"]) == 64 for item in lock["packages"])
    assert lock["source_overlay"]["manifest_sha256"] == (
        evidence.SOURCE_MANIFEST_SHA256
    )
    assert lock["installation_command"] is None
    assert lock["authorises_installation"] is False


def _source_fixture(root: Path) -> dict[str, object]:
    values = {
        "LICENSE": b"MIT fixture\n",
        "mlx_audio/__init__.py": b"import os\n",
        "mlx_audio/dsp.py": (
            b"import functools\nimport math\nimport mlx.core\nimport numpy\n"
            b"import typing\nimport warnings\n"
        ),
        "mlx_audio/sts/models/mel_roformer/config.py": (
            b"import dataclasses\nimport typing\n"
        ),
        "mlx_audio/sts/models/mel_roformer/model.py": (
            b"import dataclasses\nimport json\nimport math\nimport mlx.core as mx\n"
            b"import mlx_audio.dsp\nimport numpy\nimport pathlib\nimport re\nimport typing\n"
            b"from .config import Config\n"
            b"def load(model):\n"
            b"    get_model_path('x')\n"
            b"    mx.load('x')\n"
            b"    model.load_weights([])\n"
        ),
        "pyproject.toml": b"[project]\nname='fixture'\n",
    }
    files = []
    for path, contents in values.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        item: dict[str, object] = {
            "path": path,
            "kind": (
                "runtime_module"
                if path.endswith(".py")
                else "license" if path == "LICENSE" else "package_metadata"
            ),
            "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
        }
        if path.endswith(".py"):
            tree_roots = {
                "mlx_audio/__init__.py": ["os"],
                "mlx_audio/dsp.py": ["functools", "math", "mlx", "numpy", "typing", "warnings"],
                "mlx_audio/sts/models/mel_roformer/config.py": ["dataclasses", "typing"],
                "mlx_audio/sts/models/mel_roformer/model.py": [
                    "dataclasses", "json", "math", "mlx", "mlx_audio", "numpy", "pathlib", "re", "typing"
                ],
            }
            item["direct_import_roots"] = tree_roots[path]
            item["permitted_relative_imports"] = [".config"] if path.endswith("model.py") else []
        files.append(item)
    return {"files": files}


def test_verifies_exact_source_without_importing_it(tmp_path: Path) -> None:
    manifest = _source_fixture(tmp_path)
    with (
        patch.object(evidence, "_expected_source_manifest", return_value=manifest),
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        result = evidence._verify_private_melroformer_source_tree(tmp_path)

    assert result["status"] == "verified_not_imported"
    model = next(item for item in result["files"] if item["path"].endswith("model.py"))
    assert model["static_analysis"]["upstream_convenience_loader_present"] is True
    assert model["static_analysis"]["loader_calls"] == [
        "get_model_path",
        "model.load_weights",
        "mx.load",
    ]
    assert result["model_import_permitted"] is False


def test_source_verifier_rejects_unregistered_import(tmp_path: Path) -> None:
    manifest = _source_fixture(tmp_path)
    model_path = tmp_path / "mlx_audio/sts/models/mel_roformer/model.py"
    changed = model_path.read_bytes() + b"import socket\n"
    model_path.write_bytes(changed)
    model = next(item for item in manifest["files"] if item["path"].endswith("model.py"))
    model["bytes"] = len(changed)
    model["sha256"] = hashlib.sha256(changed).hexdigest()
    with (
        patch.object(evidence, "_expected_source_manifest", return_value=manifest),
        pytest.raises(ValueError, match="import surface differs"),
    ):
        evidence._verify_private_melroformer_source_tree(tmp_path)


def test_source_verifier_rejects_symlinked_source_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    _source_fixture(real)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="non-symlink directory"):
        evidence._verify_private_melroformer_source_tree(link)


def test_tracked_verifier_rejects_changed_record(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    source = (root / evidence.SOURCE_MANIFEST).read_bytes()
    lock = (root / evidence.RUNTIME_LOCK).read_bytes()
    (tmp_path / evidence.SOURCE_MANIFEST).write_bytes(source)
    (tmp_path / evidence.RUNTIME_LOCK).write_bytes(lock + b" ")
    with pytest.raises(ValueError, match="hash differs"):
        evidence._verify_tracked_melroformer_runtime_evidence(tmp_path)


def test_private_runtime_script_has_no_cli_or_tui_route() -> None:
    repository = Path(__file__).parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts/private-melroformer-runtime-evidence.py"),
            "--repository-root",
            str(repository),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repository / "src")},
    )
    result = json.loads(completed.stdout)
    assert result["tracked"]["status"] == "verified_not_installed_not_imported"
    assert "private-melroformer-runtime-evidence" not in PUBLIC_COMMANDS
    assert "private-melroformer-runtime-evidence" not in DIRECT_TUI_COMMANDS
