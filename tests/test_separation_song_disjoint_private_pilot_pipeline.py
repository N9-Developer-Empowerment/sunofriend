from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend import _separation_song_disjoint_private_pilot_pipeline as pipeline


def _preflight_result() -> dict[str, object]:
    return {
        "status": "request_bound_preflight_complete_no_model_run",
        "request_binding": {"request_document_sha256": "a" * 64},
        "readiness": {"all_worker_runs_complete": False},
    }


def _common_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "pragmatic_authorization_path": tmp_path / "authorization.json",
        "reference_v2_execution_path": tmp_path / "reference.json",
        "repository_root": tmp_path / "repository",
        "runtime_launcher_path": tmp_path / "python",
        "source_root": tmp_path / "source",
        "checkpoint_path": tmp_path / "checkpoint.safetensors",
        "companion_root": tmp_path / "companions",
    }


def test_pipeline_preflight_writes_nothing_and_runs_no_downstream_stage(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def execute(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return _preflight_result()

    output = tmp_path / "pipeline"
    result = pipeline._run_song_disjoint_private_pilot_pipeline(
        tmp_path / "request.json",
        out_dir=output,
        preflight=True,
        execution_runner=execute,
        stitch_runner=lambda *args, **kwargs: pytest.fail("stitch ran"),
        alignment_runner=lambda *args, **kwargs: pytest.fail("alignment ran"),
        evidence_runner=lambda *args, **kwargs: pytest.fail("evidence ran"),
        **_common_kwargs(tmp_path),
    )

    assert result["status"] == "automatic_pipeline_preflight_complete_no_model_run"
    assert result["stages"]["human_review"] == "not_run"
    assert result["effects"]["filesystem_write"] is False
    assert result["effects"]["model_run"] is False
    assert len(calls) == 1
    assert calls[0]["preflight"] is True
    assert calls[0]["out_dir"] is None
    assert not output.exists()


def test_pipeline_stops_after_an_incomplete_resumable_worker_queue(
    tmp_path: Path,
) -> None:
    calls = 0

    def execute(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if kwargs["preflight"]:
            return _preflight_result()
        Path(kwargs["out_dir"]).mkdir(mode=0o700)
        return {
            "status": "private_chunk_execution_incomplete",
            "readiness": {"all_worker_runs_complete": False},
            "summary": {"remaining_chunks": 15},
        }

    output = tmp_path / "pipeline"
    result = pipeline._run_song_disjoint_private_pilot_pipeline(
        tmp_path / "request.json",
        out_dir=output,
        execution_runner=execute,
        stitch_runner=lambda *args, **kwargs: pytest.fail("stitch ran"),
        alignment_runner=lambda *args, **kwargs: pytest.fail("alignment ran"),
        evidence_runner=lambda *args, **kwargs: pytest.fail("evidence ran"),
        **_common_kwargs(tmp_path),
    )

    assert calls == 2
    assert result["status"] == "worker_execution_incomplete_resume_required"
    assert result["stages"]["worker_execution"] == "incomplete"
    assert result["stages"]["human_review"] == "not_run"
    assert (output / pipeline.EXECUTION_DIRECTORY).is_dir()
    assert not (output / pipeline.STITCH_DIRECTORY).exists()


def test_pipeline_creates_each_automatic_stage_once_and_resumes_to_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = tmp_path / "request.json"
    plan = tmp_path / "plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "_load_verified_song_disjoint_private_pilot_request",
        lambda value: {
            "plan_path": plan,
            "plan": {},
            "plan_sha256": "9" * 64,
        },
    )
    monkeypatch.setattr(
        pipeline,
        "_verify_automatic_stage_chain",
        lambda **kwargs: {},
    )
    counters = {"execution": 0, "stitch": 0, "alignment": 0, "evidence": 0}

    def execute(*args: object, **kwargs: object) -> dict[str, object]:
        if kwargs["preflight"]:
            return _preflight_result()
        counters["execution"] += 1
        root = Path(kwargs["out_dir"])
        root.mkdir(mode=0o700, exist_ok=True)
        (root / pipeline.EXECUTION_REPORT_NAME).write_text("{}\n", encoding="utf-8")
        (root / pipeline.COMPLETION_REPORT_NAME).write_text("{}\n", encoding="utf-8")
        return {
            "status": "private_chunk_execution_complete_not_selected",
            "readiness": {"all_worker_runs_complete": True},
        }

    def stitch(*args: object, **kwargs: object) -> dict[str, object]:
        counters["stitch"] += 1
        root = Path(kwargs["out_dir"])
        root.mkdir(mode=0o700)
        (root / "private-separation-full-song-stitch.json").write_text(
            "{}\n", encoding="utf-8"
        )
        return {}

    def align(*args: object, **kwargs: object) -> dict[str, object]:
        counters["alignment"] += 1
        out = Path(kwargs["out"])
        out.parent.mkdir(mode=0o700)
        out.write_text("{}\n", encoding="utf-8")
        return {}

    def evidence(*args: object, **kwargs: object) -> dict[str, object]:
        counters["evidence"] += 1
        out = Path(kwargs["out"])
        out.parent.mkdir(mode=0o700)
        out.write_text("{}\n", encoding="utf-8")
        return {}

    review = tmp_path / "review.html"
    verified = {
        "bindings": {
            "pilot_request_sha256": "1" * 64,
            "pilot_execution_sha256": "2" * 64,
            "pilot_stitch_sha256": "3" * 64,
            "pilot_alignment_sha256": "4" * 64,
            "automatic_evidence_sha256": "5" * 64,
        },
        "clock": {"sample_rate": 44_100, "frames": 100, "boundary_count": 1},
        "alignment_summary": {"gate_passed": True},
        "human_review": {"status": "pending", "boundary_count": 1},
        "readiness": {
            "human_full_song_and_boundary_review_complete": False,
            "publication_ready": False,
        },
        "review_html": review,
    }
    monkeypatch.setattr(pipeline, "_verify_completed_pipeline", lambda **kwargs: verified)

    output = tmp_path / "pipeline"
    first = pipeline._run_song_disjoint_private_pilot_pipeline(
        request,
        out_dir=output,
        execution_runner=execute,
        stitch_runner=stitch,
        alignment_runner=align,
        evidence_runner=evidence,
        **_common_kwargs(tmp_path),
    )
    second = pipeline._run_song_disjoint_private_pilot_pipeline(
        request,
        out_dir=output,
        execution_runner=execute,
        stitch_runner=stitch,
        alignment_runner=align,
        evidence_runner=evidence,
        **_common_kwargs(tmp_path),
    )

    assert first["status"] == pipeline.STATUS
    assert first["stages_created_this_invocation"] == {
        "stitch": True,
        "alignment": True,
        "automatic_evidence": True,
    }
    assert second["stages_created_this_invocation"] == {
        "stitch": False,
        "alignment": False,
        "automatic_evidence": False,
    }
    assert counters == {"execution": 2, "stitch": 1, "alignment": 1, "evidence": 1}
    report = output / pipeline.REPORT_NAME
    persisted = json.loads(report.read_text(encoding="utf-8"))
    assert persisted["status"] == pipeline.STATUS
    assert persisted["stages"]["human_review"] == "pending"
    assert persisted["readiness"]["publication_ready"] is False
    assert persisted["permissions"] == pipeline._FALSE_PERMISSIONS
    assert report.stat().st_mode & 0o777 == 0o600


def test_pipeline_rejects_a_shared_existing_root(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    root.mkdir(mode=0o755)
    root.chmod(0o755)

    with pytest.raises(ValueError, match="not an owner-only directory"):
        pipeline._run_song_disjoint_private_pilot_pipeline(
            tmp_path / "request.json",
            out_dir=root,
            execution_runner=lambda *args, **kwargs: _preflight_result(),
            **_common_kwargs(tmp_path),
        )


def test_completed_pipeline_verifier_rejects_stale_evidence_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = [f"{number:x}" * 64 for number in range(1, 10)]
    context = {
        "authorization": {"sha256": values[0]},
        "reference": {"sha256": values[1]},
        "request": {"sha256": values[2]},
        "plan_sha256": values[3],
        "execution": {"sha256": values[4]},
        "completion": {"sha256": values[5]},
        "stitch_sha256": values[6],
        "alignment": {
            "sha256": values[7],
            "document": {"summary": {"gate_passed": True}},
        },
        "review_seed_sha256": values[8],
        "stitch": {
            "clock": {"sample_rate": 44_100},
            "boundary_review": {"html": "BOUNDARY-REVIEW/review.html"},
        },
        "stitch_package": tmp_path / "stitch",
    }
    monkeypatch.setattr(pipeline, "_load_context", lambda *args, **kwargs: context)
    monkeypatch.setattr(
        pipeline,
        "_load_verified_song_disjoint_private_pilot_evidence",
        lambda value: {
            "sha256": "f" * 64,
            "document": {
                "document_sha256": "e" * 64,
                "bindings": {
                    "pragmatic_authorization_sha256": values[0],
                    "reference_v2_execution_sha256": values[1],
                    "pilot_request_sha256": "0" * 64,
                    "pilot_plan_sha256": values[3],
                    "pilot_execution_sha256": values[4],
                    "pilot_completion_binding_sha256": values[5],
                    "pilot_stitch_sha256": values[6],
                    "pilot_alignment_sha256": values[7],
                    "pilot_review_seed_sha256": values[8],
                },
                "human_review": {"status": "pending"},
                "readiness": {"publication_ready": False},
            },
        },
    )

    with pytest.raises(ValueError, match="evidence binding differs"):
        pipeline._verify_completed_pipeline(
            pragmatic_authorization_path="authorization",
            reference_v2_execution_path="reference",
            request_report_path="request",
            plan_report_path="plan",
            execution_report_path="execution",
            request_completion_binding_path="completion",
            stitch_package_dir="stitch",
            alignment_result_path="alignment",
            evidence_path="evidence",
        )
