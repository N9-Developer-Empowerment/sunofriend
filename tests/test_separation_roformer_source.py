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


def _spec(values: dict[str, bytes]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {
        path: {
            "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
        }
        for path, contents in values.items()
    }
    for path in (
        "models/bs_roformer/attend.py",
        "models/bs_roformer/bs_roformer.py",
    ):
        result[path]["direct_import_roots"] = ()
    return result


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
    } == {
        path: {"bytes": item["bytes"], "sha256": item["sha256"]}
        for path, item in source._SOURCE_FILES.items()  # noqa: SLF001
    }
    assert {
        item["path"]: item["direct_import_roots"]
        for item in manifest["files"]
        if item["kind"] == "runtime_module"
    } == {
        path: list(item["direct_import_roots"])
        for path, item in source._SOURCE_FILES.items()  # noqa: SLF001
        if "direct_import_roots" in item
    }
    assert manifest["static_source_policy"] == {
        "maximum_file_bytes": 65_536,
        "exact_direct_import_roots_required": True,
        "relative_imports_permitted": False,
        "wildcard_imports_permitted": False,
        "dynamic_import_or_codegen_calls_permitted": False,
        "analysis_executes_source": False,
    }
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
    assert result["static_source_policy"] == {
        "maximum_file_bytes": 65_536,
        "exact_direct_import_roots_required": True,
        "relative_imports_permitted": False,
        "wildcard_imports_permitted": False,
        "dynamic_import_or_codegen_calls_permitted": False,
    }
    for item in result["files"][1:]:
        assert item["static_analysis"] == {
            "syntax": "parsed_not_executed",
            "direct_import_roots": [],
            "relative_imports": [],
            "wildcard_imports": [],
            "dynamic_import_or_codegen_calls": [],
        }
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


def test_rejects_unregistered_import_root(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    changed = b"import socket\n"
    path = "models/bs_roformer/attend.py"
    (tmp_path / path).write_bytes(changed)
    values[path] = changed

    with (
        patch.object(source, "_SOURCE_FILES", _spec(values)),
        pytest.raises(ValueError, match="import surface differs"),
    ):
        source._verify_private_roformer_source_tree(tmp_path)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (b"__import__('socket')\n", "dynamic import or codegen"),
        (b"from . import attend\n", "relative import"),
        (b"from torch import *\n", "wildcard import"),
        (b"def broken(:\n", "syntax is invalid"),
    ],
)
def test_rejects_unsafe_static_source_constructs(
    tmp_path: Path, contents: bytes, message: str
) -> None:
    values = _fixture(tmp_path)
    path = "models/bs_roformer/attend.py"
    (tmp_path / path).write_bytes(contents)
    values[path] = contents
    spec = _spec(values)
    if contents == b"from torch import *\n":
        spec[path]["direct_import_roots"] = ("torch",)

    with (
        patch.object(source, "_SOURCE_FILES", spec),
        pytest.raises(ValueError, match=message),
    ):
        source._verify_private_roformer_source_tree(tmp_path)
