from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_private_backend_adapter_contract as adapter
from sunofriend._separation_authorised_excerpt import _document_sha256


def test_builds_path_free_model_free_backend_adapter_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    output = context["output_parent"] / adapter.REPORT_NAME

    result = adapter._build_private_separation_backend_adapter_contract(
        context["design_path"],
        coverage_report_path=context["coverage_path"],
        repository_root=context["repository"],
        runtime_launcher_path=context["runtime"],
        source_root=context["source_root"],
        checkpoint_path=context["checkpoint"],
        companion_root=context["companion_root"],
        out=output,
    )

    assert result["status"] == adapter.STATUS
    assert result["backend"]["candidate_id"] == "mlx-melroformer-kim-vocal-2"
    assert result["backend"]["role_contract"] == {
        "primary": ["vocals", "instrumental"],
        "diagnostic": ["reconstruction"],
    }
    assert result["execution_boundary"]["this_contract_is_an_execution_request"] is False
    assert result["execution_boundary"]["this_contract_authorizes_model_execution"] is False
    assert result["readiness"]["next_stage"] == (
        "implement_private_execution_request_builder"
    )
    assert not any(result["permissions"].values())
    assert result["effects"]["model_run"] is False
    assert result["effects"]["audio_created_or_mutated"] is False
    assert os.stat(output.parent).st_mode & 0o777 == 0o700
    assert os.stat(output).st_mode & 0o777 == 0o600
    persisted = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    document = json.loads(persisted)
    assert document["document_sha256"] == _document_sha256(document)


def test_rejects_environment_that_may_observe_tensor_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["measured"]["execution_environment"]["checkpoint"][
        "tensor_values_observed"
    ] = True

    with pytest.raises(ValueError, match="backend environment differs"):
        _build(context)


def test_rejects_environment_change_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    original = deepcopy(context["measured"])
    changed = deepcopy(original)
    changed["execution_environment"]["runtime"]["sha256"] = "f" * 64
    calls = iter((original, changed))
    monkeypatch.setattr(
        adapter,
        "_measure_request_execution_environment",
        lambda **_kwargs: next(calls),
    )

    with pytest.raises(ValueError, match="inputs changed"):
        _build(context)


def test_rejects_route_design_change_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    first = deepcopy(context["design"])
    second = deepcopy(first)
    second["sha256"] = "e" * 64
    calls = iter((first, second))
    monkeypatch.setattr(
        adapter,
        "_load_verified_private_separation_route_design",
        lambda *_args, **_kwargs: next(calls),
    )

    with pytest.raises(ValueError, match="inputs changed"):
        _build(context)


def test_requires_fresh_fixed_named_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="filename"):
        _build(context, output=context["output_parent"] / "different.json")

    output = context["output_parent"] / adapter.REPORT_NAME
    _build(context, output=output)
    with pytest.raises(FileExistsError):
        _build(context, output=output)


def test_rejects_output_inside_backend_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="overlaps evidence"):
        _build(context, output=context["source_root"] / adapter.REPORT_NAME)


def _build(
    context: dict[str, object],
    *,
    output: Path | None = None,
) -> dict[str, object]:
    return adapter._build_private_separation_backend_adapter_contract(
        context["design_path"],
        coverage_report_path=context["coverage_path"],
        repository_root=context["repository"],
        runtime_launcher_path=context["runtime"],
        source_root=context["source_root"],
        checkpoint_path=context["checkpoint"],
        companion_root=context["companion_root"],
        out=output or context["output_parent"] / adapter.REPORT_NAME,
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    os.chmod(tmp_path, 0o700)
    output_parent = _private_dir(tmp_path / "output")
    repository = _private_dir(tmp_path / "repository")
    source_root = _private_dir(tmp_path / "source")
    companion_root = _private_dir(tmp_path / "companions")
    runtime = _private_file(tmp_path / "python", b"runtime\n")
    checkpoint = _private_file(tmp_path / "checkpoint.safetensors", b"checkpoint\n")
    design_path = _private_file(tmp_path / "private-separation-route-design.json", b"design\n")
    coverage_path = _private_file(
        tmp_path / "private-separation-multi-song-private-pilot-coverage.json",
        b"coverage\n",
    )
    design_snapshot = {
        "path": design_path,
        "sha256": "a" * 64,
        "document": {
            "document_sha256": "b" * 64,
            "mode_isolation": {
                "simple_can_discover_output": False,
                "studio_can_discover_output": False,
                "tui_can_execute_route": False,
                "public_cli_can_execute_route": False,
                "source_graph_can_import_output": False,
                "download_pack_can_include_output": False,
            },
        },
        "coverage": {
            "path": coverage_path,
            "sha256": "c" * 64,
            "document": {"document_sha256": "d" * 64},
        },
    }
    measured = {
        "repository_root": repository,
        "runtime_launcher_path": runtime,
        "source_root": source_root,
        "checkpoint_path": checkpoint,
        "companion_root": companion_root,
        "execution_environment": {
            "runtime": {"sha256": "1" * 64},
            "checkpoint": {
                "sha256": "2" * 64,
                "tensor_values_observed": False,
                "tensor_library_imported": False,
            },
            "audited_source": {
                "status": "verified_not_imported",
                "revision": "test",
            },
            "offline_environment_required": True,
        },
    }
    monkeypatch.setattr(
        adapter,
        "_load_verified_private_separation_route_design",
        lambda *_args, **_kwargs: deepcopy(design_snapshot),
    )
    monkeypatch.setattr(
        adapter,
        "_measure_request_execution_environment",
        lambda **_kwargs: deepcopy(measured),
    )
    return {
        "output_parent": output_parent,
        "repository": repository,
        "source_root": source_root,
        "companion_root": companion_root,
        "runtime": runtime,
        "checkpoint": checkpoint,
        "design_path": design_path,
        "coverage_path": coverage_path,
        "design": design_snapshot,
        "measured": measured,
    }


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def _private_file(path: Path, contents: bytes) -> Path:
    path.write_bytes(contents)
    os.chmod(path, 0o600)
    return path
