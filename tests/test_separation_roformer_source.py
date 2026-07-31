from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_roformer_source as source


def _fixture(root: Path) -> dict[str, bytes]:
    model_root = root / "models" / "bs_roformer"
    model_root.mkdir(parents=True)
    values = {
        "LICENSE": b"MIT fixture\n",
        "models/bs_roformer/attend.py": b"ATTEND = True\n",
        "models/bs_roformer/bs_roformer.py": b"MODEL = True\n",
    }
    for relative_path, contents in values.items():
        (root / relative_path).write_bytes(contents)
    return values


def _spec(values: dict[str, bytes]) -> dict[str, dict[str, int | str]]:
    return {
        path: {
            "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
        }
        for path, contents in values.items()
    }


def test_tracked_manifest_is_hash_bound_to_exact_source_spec() -> None:
    root = Path(__file__).parents[1]
    manifest_path = root / source.SOURCE_MANIFEST
    contents = manifest_path.read_bytes()
    manifest = json.loads(contents)

    assert hashlib.sha256(contents).hexdigest() == source.SOURCE_MANIFEST_SHA256
    assert manifest["revision"] == source.SOURCE_REVISION
    assert {
        item["path"]: {
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
        for item in manifest["files"]
    } == source._SOURCE_FILES  # noqa: SLF001
    assert manifest["package_initializer_permitted"] is False
    assert manifest["model_import_permitted_by_manifest"] is False


def test_verifies_fixed_source_files_without_import_or_process(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    with (
        patch.object(source, "_SOURCE_FILES", _spec(values)),
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        result = source._verify_private_roformer_source_tree(tmp_path)

    assert result["status"] == "verified_not_imported"
    assert result["revision_verified_by_git"] is False
    assert [item["path"] for item in result["files"]] == list(values)
    assert result["package_initializer_executed"] is False
    assert result["model_import_permitted"] is False
    assert result["effects"] == {
        "filesystem_accessed": True,
        "filesystem_written": False,
        "network_used": False,
        "model_imported": False,
        "process_started": False,
        "package_installed": False,
    }


def test_rejects_changed_source_bytes(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    spec = _spec(values)
    changed = tmp_path / "models" / "bs_roformer" / "attend.py"
    changed.write_bytes(b"changed bytes\n")

    with (
        patch.object(source, "_SOURCE_FILES", spec),
        pytest.raises(ValueError, match="size differs|hash differs"),
    ):
        source._verify_private_roformer_source_tree(tmp_path)


def test_rejects_symlinked_source_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    values = _fixture(real)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)

    with (
        patch.object(source, "_SOURCE_FILES", _spec(values)),
        pytest.raises(ValueError, match="non-symlink directory"),
    ):
        source._verify_private_roformer_source_tree(linked)
