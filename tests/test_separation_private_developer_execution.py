from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

import pytest

import sunofriend._separation_private_developer_execution as execution


def test_preflight_is_read_only_and_does_not_call_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    called = False

    def fail_executor(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("executor must not run in preflight")

    result = _run(context, queue_executor=fail_executor)

    assert result["status"] == execution.PREFLIGHT_STATUS
    assert result["readiness"]["explicit_execution_action_received"] is False
    assert result["readiness"]["model_run_started_this_invocation"] is False
    assert result["permissions"]["bounded_private_execution_for_exact_request"] is True
    assert result["permissions"]["source_graph_activation"] is False
    assert result["effects"] == {
        "execution_root_created_or_mutated": False,
        "model_run": False,
        "request_or_evidence_mutated": False,
        "source_graph_mutated": False,
    }
    assert called is False
    assert not context["output"].exists()


def test_preflight_requires_fresh_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["output"].mkdir(mode=0o700)

    with pytest.raises(FileExistsError, match="must be fresh"):
        _run(context)


def test_preflight_rejects_device_different_from_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="differs from request"):
        _run(context, device="cpu")


def test_preflight_rejects_output_inside_plan_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["output"] = context["plan_path"].parent / "execution"

    with pytest.raises(ValueError, match="overlaps evidence"):
        _run(context)


def test_explicit_execute_passes_exact_request_binding_to_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    observed: dict[str, object] = {}

    def fake_executor(plan: Path, **kwargs: object) -> dict[str, object]:
        observed["plan"] = plan
        observed.update(kwargs)
        return {
            "status": "private_chunk_execution_incomplete_not_selected",
            "chunks_executed_this_invocation": 1,
            "summary": {"all_worker_runs_complete": False},
            "output_directory": str(context["output"]),
            "report": str(context["output"] / "private-separation-full-song-execution.json"),
        }

    result = _run(context, execute=True, queue_executor=fake_executor)

    assert result["status"] == execution.EXECUTION_STATUS
    assert result["readiness"]["explicit_execution_action_received"] is True
    assert result["readiness"]["model_run_started_this_invocation"] is True
    assert result["readiness"]["all_worker_runs_complete"] is False
    assert observed["plan"] == context["plan_path"]
    assert observed["out_dir"] == context["output"]
    assert observed["device"] == "gpu"
    assert observed["maximum_chunks"] == 1
    assert observed["private_pilot_request_binding"] == result["request_binding"]
    assert result["request_binding"] == {
        "request_schema": "sunofriend.private-separation-execution-request.v1",
        "request_policy_id": "authorized-plan-bound-private-separation-request-v1",
        "request_report_sha256": "1" * 64,
        "request_document_sha256": "2" * 64,
        "checkpoint_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "companion_manifest_sha256": "5" * 64,
        "worker_source_sha256": "6" * 64,
    }


def test_explicit_execute_reports_worker_completion_but_still_requires_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)

    result = _run(
        context,
        execute=True,
        maximum_chunks=None,
        queue_executor=lambda *_args, **_kwargs: {
            "status": "private_chunk_execution_complete_not_selected",
            "chunks_executed_this_invocation": 7,
            "summary": {"all_worker_runs_complete": True},
        },
    )

    assert result["status"] == execution.COMPLETE_STATUS
    assert result["readiness"]["all_worker_runs_complete"] is True
    assert result["readiness"]["stitch_complete"] is False
    assert result["readiness"]["human_review_complete"] is False
    assert result["readiness"]["private_output_import_permitted"] is False


def test_rejects_invalid_maximum_chunks_before_loading_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="maximum chunks"):
        _run(context, maximum_chunks=0)


def _run(
    context: dict[str, object],
    *,
    device: str = "gpu",
    maximum_chunks: int | None = 1,
    execute: bool = False,
    queue_executor: object | None = None,
) -> dict[str, object]:
    kwargs = {}
    if queue_executor is not None:
        kwargs["queue_executor"] = queue_executor
    return execution._run_private_separation_developer_execution(
        context["request_path"],
        adapter_report_path=context["adapter_path"],
        design_report_path=context["design_path"],
        coverage_report_path=context["coverage_path"],
        plan_report_path=context["plan_path"],
        repository_root=context["repository"],
        runtime_launcher_path=context["runtime"],
        source_root=context["source_root"],
        checkpoint_path=context["checkpoint"],
        companion_root=context["companion_root"],
        out_dir=context["output"],
        device=device,
        maximum_chunks=maximum_chunks,
        execute=execute,
        **kwargs,
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    os.chmod(tmp_path, 0o700)
    plan_root = _private_dir(tmp_path / "plan")
    source_root = _private_dir(tmp_path / "backend-source")
    companion_root = _private_dir(tmp_path / "companions")
    paths = {
        "request_path": _private_file(tmp_path / "request.json"),
        "adapter_path": _private_file(tmp_path / "adapter.json"),
        "design_path": _private_file(tmp_path / "design.json"),
        "coverage_path": _private_file(tmp_path / "coverage.json"),
        "plan_path": _private_file(plan_root / "private-separation-full-song-plan.json"),
        "repository": _private_dir(tmp_path / "repository"),
        "runtime": _private_file(tmp_path / "python"),
        "source_root": source_root,
        "checkpoint": _private_file(tmp_path / "model.safetensors"),
        "companion_root": companion_root,
        "output": tmp_path / "fresh-execution",
    }
    design = {
        "path": paths["design_path"],
        "coverage": {"path": paths["coverage_path"]},
    }
    adapter = {
        "path": paths["adapter_path"],
        "design": design,
        "measured": {
            "source_root": source_root,
            "companion_root": companion_root,
        },
        "document": {
            "backend": {
                "execution_environment": {
                    "audited_source": {"manifest_sha256": "4" * 64},
                    "companion_manifest_sha256": "5" * 64,
                    "worker_source": {"sha256": "6" * 64},
                }
            }
        },
    }
    loaded = {
        "path": paths["request_path"],
        "sha256": "1" * 64,
        "document": {
            "schema": "sunofriend.private-separation-execution-request.v1",
            "policy_id": "authorized-plan-bound-private-separation-request-v1",
            "document_sha256": "2" * 64,
            "bindings": {"checkpoint_sha256": "3" * 64},
            "request": {"device": "gpu"},
        },
        "adapter": adapter,
        "plan_path": paths["plan_path"],
    }
    monkeypatch.setattr(
        execution,
        "_load_verified_private_separation_execution_request",
        lambda *_args, **_kwargs: deepcopy(loaded),
    )
    return paths


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def _private_file(path: Path) -> Path:
    path.write_bytes(b"private\n")
    os.chmod(path, 0o600)
    return path
