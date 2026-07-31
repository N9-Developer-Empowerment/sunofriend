from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_roformer_admission as admission
from sunofriend._separation_roformer_source import SOURCE_REVISION


def _copy_repository_evidence(root: Path) -> None:
    repository = Path(__file__).parents[1]
    for name in admission._EXPECTED_FILES:  # noqa: SLF001
        shutil.copyfile(repository / name, root / name)


def _source_verification(repository_root: Path) -> dict[str, object]:
    manifest = json.loads(
        (
            repository_root / "private-separation-roformer-source-manifest.json"
        ).read_text(encoding="utf-8")
    )
    files = []
    for item in manifest["files"]:
        report: dict[str, object] = {
            "path": item["path"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
            "regular_file": True,
            "symlink": False,
        }
        if item["kind"] == "runtime_module":
            report["static_analysis"] = {
                "syntax": "parsed_not_executed",
                "direct_import_roots": item["direct_import_roots"],
                "relative_imports": [],
                "wildcard_imports": [],
                "dynamic_import_or_codegen_calls": [],
            }
        files.append(report)
    return {
        "schema": "sunofriend.private-roformer-source-verification.v2",
        "status": "verified_not_imported",
        "source_root": "/private/source/path",
        "revision_claim": SOURCE_REVISION,
        "revision_verified_by_git": False,
        "manifest": {
            "path": "private-separation-roformer-source-manifest.json",
            "sha256": admission.SOURCE_MANIFEST_SHA256,
        },
        "files": files,
        "static_source_policy": {
            "maximum_file_bytes": 65_536,
            "exact_direct_import_roots_required": True,
            "relative_imports_permitted": False,
            "wildcard_imports_permitted": False,
            "dynamic_import_or_codegen_calls_permitted": False,
        },
        "package_initializer_executed": False,
        "model_import_permitted": False,
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "model_imported": False,
            "process_started": False,
            "package_installed": False,
        },
    }


def _all_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _all_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _all_strings(child)]
    return [value] if isinstance(value, str) else []


def test_admission_binds_source_runtime_and_licence_without_enabling(
    tmp_path: Path,
) -> None:
    _copy_repository_evidence(tmp_path)
    source = _source_verification(tmp_path)
    with (
        patch.object(
            admission, "_verify_private_roformer_source_tree", return_value=source
        ),
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        result = admission._build_private_roformer_admission(
            repository_root=tmp_path,
            source_tree=tmp_path / "upstream",
        )

    assert result["status"] == "blocked"
    assert result["path_free"] is True
    assert result["admission_sha256"] == admission._admission_sha256(result)
    assert result["repository_evidence"]["direct_package_count"] == 6
    assert result["repository_evidence"]["locked_package_count"] == 15
    assert result["readiness"] == {
        "exact_source_tree_verified": True,
        "exact_import_surface_verified": True,
        "runtime_input_verified": True,
        "runtime_lock_verified": True,
        "runtime_licence_audit_verified": True,
        "code_and_runtime_plan_ready": True,
        "checkpoint_identity_verified": False,
        "checkpoint_terms_verified": False,
        "checkpoint_static_inspection_completed": False,
        "runtime_environment_installed_and_verified": False,
        "worker_implemented": False,
        "private_evaluation_eligible": False,
        "worker_start_permitted": False,
    }
    assert "checkpoint_sha256_unpublished" in result["blockers"]
    assert "checkpoint_terms_unverified" in result["blockers"]
    assert all(
        not text.startswith("/") and str(tmp_path) not in text
        for text in _all_strings(result)
    )
    assert result["effects"] == {
        "filesystem_accessed": True,
        "filesystem_written": False,
        "network_used": False,
        "package_installed": False,
        "checkpoint_opened": False,
        "checkpoint_downloaded": False,
        "checkpoint_deserialized": False,
        "model_imported": False,
        "process_started": False,
        "product_route_changed": False,
    }


@pytest.mark.parametrize("name", tuple(admission._EXPECTED_FILES))  # noqa: SLF001
def test_admission_rejects_changed_repository_evidence(
    tmp_path: Path, name: str
) -> None:
    _copy_repository_evidence(tmp_path)
    source = _source_verification(tmp_path)
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b"changed")

    with (
        patch.object(
            admission,
            "_verify_private_roformer_source_tree",
            return_value=source,
        ),
        pytest.raises(ValueError, match="size differs|hash differs"),
    ):
        admission._build_private_roformer_admission(
            repository_root=tmp_path,
            source_tree=tmp_path / "upstream",
        )


def test_admission_rejects_symlinked_repository_evidence(tmp_path: Path) -> None:
    _copy_repository_evidence(tmp_path)
    name = admission.RUNTIME_DEPENDENCY_INPUT
    target = tmp_path / "target.in"
    path = tmp_path / name
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)

    with (
        patch.object(
            admission,
            "_verify_private_roformer_source_tree",
            return_value=_source_verification(tmp_path),
        ),
        pytest.raises(ValueError, match="evidence is unsafe"),
    ):
        admission._build_private_roformer_admission(
            repository_root=tmp_path,
            source_tree=tmp_path / "upstream",
        )


def test_admission_rejects_semantically_changed_licence_finding(
    tmp_path: Path,
) -> None:
    _copy_repository_evidence(tmp_path)
    path = tmp_path / admission.RUNTIME_LICENSE_AUDIT
    audit = json.loads(path.read_text(encoding="utf-8"))
    audit["finding"]["checkpoint_terms_covered"] = True
    data = (json.dumps(audit, indent=2) + "\n").encode("utf-8")
    path.write_bytes(data)
    expected = copy.deepcopy(admission._EXPECTED_FILES)  # noqa: SLF001
    expected[admission.RUNTIME_LICENSE_AUDIT] = {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "maximum_bytes": 512 * 1024,
    }

    with (
        patch.object(admission, "_EXPECTED_FILES", expected),
        patch.object(
            admission,
            "_verify_private_roformer_source_tree",
            return_value=_source_verification(tmp_path),
        ),
        pytest.raises(ValueError, match="finding differs"),
    ):
        admission._build_private_roformer_admission(
            repository_root=tmp_path,
            source_tree=tmp_path / "upstream",
        )


def test_admission_rejects_non_exact_source_verification(tmp_path: Path) -> None:
    _copy_repository_evidence(tmp_path)
    source = _source_verification(tmp_path)
    source["model_import_permitted"] = True

    with (
        patch.object(
            admission, "_verify_private_roformer_source_tree", return_value=source
        ),
        pytest.raises(ValueError, match="execution boundary differs"),
    ):
        admission._build_private_roformer_admission(
            repository_root=tmp_path,
            source_tree=tmp_path / "upstream",
        )
