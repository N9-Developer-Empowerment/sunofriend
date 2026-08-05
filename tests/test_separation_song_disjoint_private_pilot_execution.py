from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

import sunofriend._separation_song_disjoint_private_pilot_execution as execution
from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
)
from sunofriend._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_SHA256,
)


def test_request_bound_execution_preflight_remeasures_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _loaded(tmp_path)
    _patch_inputs(monkeypatch, loaded)
    out = tmp_path / "must-not-exist"

    result = execution._execute_song_disjoint_private_pilot_request(
        "request.json",
        out_dir=out,
        **_runtime_arguments(tmp_path),
        preflight=True,
    )

    assert execution.__all__ == ()
    assert result["status"] == "request_bound_preflight_complete_no_model_run"
    assert result["readiness"]["execution_environment_reverified"] is True
    assert result["effects"]["model_run"] is False
    assert not out.exists()


def test_request_bound_execution_writes_completion_only_after_all_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _loaded(tmp_path)
    _patch_inputs(monkeypatch, loaded)
    out = tmp_path / "execution"
    observed: list[Mapping[str, Any]] = []

    def partial(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
        observed.append(kwargs["private_pilot_request_binding"])
        _write_execution_report(out, "1" * 64)
        return _state(complete=False)

    first = execution._execute_song_disjoint_private_pilot_request(
        "request.json",
        out_dir=out,
        **_runtime_arguments(tmp_path),
        queue_executor=partial,
    )
    assert first["completion_binding_report"] is None
    assert not (out / execution.REPORT_NAME).exists()

    state = _state(complete=True)
    _write_execution_report(out, state["state_sha256"])

    def complete(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
        observed.append(kwargs["private_pilot_request_binding"])
        return state

    final = execution._execute_song_disjoint_private_pilot_request(
        "request.json",
        out_dir=out,
        **_runtime_arguments(tmp_path),
        maximum_chunks=None,
        queue_executor=complete,
    )
    report = out / execution.REPORT_NAME
    assert final["completion_binding_report"] == str(report)
    assert report.is_file()
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == execution.STATUS
    assert observed[0] == observed[1]

    repeated = execution._execute_song_disjoint_private_pilot_request(
        "request.json",
        out_dir=out,
        **_runtime_arguments(tmp_path),
        maximum_chunks=None,
        queue_executor=complete,
    )
    assert repeated["completion_binding_report"] == str(report)


def test_request_bound_execution_rejects_environment_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _loaded(tmp_path)
    monkeypatch.setattr(
        execution,
        "_load_verified_song_disjoint_private_pilot_request",
        lambda value: loaded,
    )
    changed = dict(loaded["document"]["execution_environment"])
    changed["worker_source"] = {"bytes": 1, "sha256": "9" * 64}
    monkeypatch.setattr(
        execution,
        "_measure_request_execution_environment",
        lambda **kwargs: {"execution_environment": changed},
    )

    with pytest.raises(ValueError, match="execution environment changed"):
        execution._execute_song_disjoint_private_pilot_request(
            "request.json",
            out_dir=tmp_path / "execution",
            **_runtime_arguments(tmp_path),
            preflight=True,
        )


def test_request_bound_execution_rejects_legacy_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _loaded(tmp_path)
    loaded["document"]["schema"] = (
        "sunofriend.private-separation-song-disjoint-pilot-request.v1"
    )
    monkeypatch.setattr(
        execution,
        "_load_verified_song_disjoint_private_pilot_request",
        lambda value: loaded,
    )

    with pytest.raises(ValueError, match="must be regenerated"):
        execution._execute_song_disjoint_private_pilot_request(
            "request.json",
            out_dir=None,
            **_runtime_arguments(tmp_path),
            preflight=True,
        )


def _patch_inputs(
    monkeypatch: pytest.MonkeyPatch,
    loaded: Mapping[str, Any],
) -> None:
    monkeypatch.setattr(
        execution,
        "_load_verified_song_disjoint_private_pilot_request",
        lambda value: loaded,
    )
    monkeypatch.setattr(
        execution,
        "_measure_request_execution_environment",
        lambda **kwargs: {
            "execution_environment": loaded["document"]["execution_environment"]
        },
    )


def _loaded(root: Path) -> dict[str, Any]:
    plan = root / "request/PLAN/private-separation-full-song-plan.json"
    plan.parent.mkdir(parents=True)
    plan.write_text("{}\n", encoding="utf-8")
    environment = {
        "checkpoint": {"sha256": CONVERSION_CHECKPOINT_SHA256},
        "audited_source": {"manifest_sha256": SOURCE_MANIFEST_SHA256},
        "companion_manifest_sha256": "3" * 64,
        "worker_source": {"bytes": 10, "sha256": "4" * 64},
    }
    document = {
        "schema": execution.REQUEST_SCHEMA,
        "policy_id": execution.REQUEST_POLICY_ID,
        "pilot": {"device": "gpu"},
        "execution_environment": environment,
        "document_sha256": "2" * 64,
    }
    return {
        "path": root / "request/private-separation-song-disjoint-pilot-request.json",
        "sha256": "1" * 64,
        "document": document,
        "plan_path": plan,
        "plan_sha256": "5" * 64,
        "plan": {"document_sha256": "6" * 64},
    }


def _runtime_arguments(root: Path) -> dict[str, Any]:
    return {
        "repository_root": root / "repository",
        "runtime_launcher_path": root / "runtime",
        "source_root": root / "source",
        "checkpoint_path": root / "checkpoint",
        "companion_root": root / "companions",
        "device": "gpu",
    }


def _state(*, complete: bool) -> dict[str, Any]:
    state = {
        "status": (
            "private_chunk_execution_complete_not_selected"
            if complete
            else "private_chunk_execution_incomplete_not_selected"
        ),
        "state_sha256": "7" * 64,
        "summary": {
            "total_chunks": 2,
            "verified_chunks": 2 if complete else 1,
            "remaining_chunks": 0 if complete else 1,
            "all_worker_runs_complete": complete,
            "stitched_outputs_complete": False,
            "human_boundary_review_complete": False,
            "quality_accepted": False,
        },
        "chunks_executed_this_invocation": 1,
    }
    return state


def _write_execution_report(root: Path, state_sha256: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    document = {"state_sha256": state_sha256}
    document["document_sha256"] = _document_sha256(document)
    path = root / EXECUTION_REPORT_NAME
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    path.chmod(0o600)
