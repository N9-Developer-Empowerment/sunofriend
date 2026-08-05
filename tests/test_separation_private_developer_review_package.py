from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_private_developer_review_package as package


def test_review_package_creates_automatic_stages_once_and_stops_for_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    calls = {"stitch": 0, "alignment": 0}

    def stitch(*_args: object, **kwargs: object) -> dict[str, object]:
        calls["stitch"] += 1
        root = Path(kwargs["out_dir"])
        root.mkdir(mode=0o700)
        (root / package.STITCH_REPORT_NAME).write_text("{}\n", encoding="utf-8")
        return {}

    def align(*_args: object, **kwargs: object) -> dict[str, object]:
        calls["alignment"] += 1
        output = Path(kwargs["out"])
        output.parent.mkdir(mode=0o700)
        output.write_text("{}\n", encoding="utf-8")
        return {}

    first = _run(context, stitch_runner=stitch, alignment_runner=align)
    second = _run(context, stitch_runner=stitch, alignment_runner=align)

    assert calls == {"stitch": 1, "alignment": 1}
    assert first["status"] == package.STATUS
    assert first["stages_created_this_invocation"] == {
        "stitch": True,
        "alignment": True,
    }
    assert second["stages_created_this_invocation"] == {
        "stitch": False,
        "alignment": False,
    }
    assert first["stages"]["full_song_and_boundary_review"] == "pending"
    assert first["readiness"]["playable_review_package_complete"] is True
    assert first["readiness"]["human_review_complete"] is False
    assert first["permissions"] == package._FALSE_PERMISSIONS
    assert first["effects"]["model_run"] is False
    assert Path(first["review_html"]) == context["output"] / "STITCH/review.html"
    report = context["output"] / package.REPORT_NAME
    assert report.stat().st_mode & 0o777 == 0o600
    persisted = json.loads(report.read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == first["document_sha256"]


def test_review_package_rejects_incomplete_execution_before_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(
        package,
        "_load_verified_execution",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("song-disjoint pilot execution differs")
        ),
    )

    with pytest.raises(ValueError, match="execution differs"):
        _run(context)

    assert not context["output"].exists()


def test_review_package_rejects_output_inside_execution_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["output"] = context["execution_root"] / "review"

    with pytest.raises(ValueError, match="overlaps evidence"):
        _run(context)


def test_review_package_rejects_shared_existing_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["output"].mkdir(mode=0o755)
    context["output"].chmod(0o755)

    with pytest.raises(ValueError, match="not an owner-only directory"):
        _run(context)


def _run(context: dict[str, Path], **kwargs: object) -> dict[str, object]:
    return package._prepare_private_separation_developer_review_package(
        context["request"],
        adapter_report_path=context["adapter"],
        design_report_path=context["design"],
        coverage_report_path=context["coverage"],
        plan_report_path=context["plan"],
        repository_root=context["repository"],
        runtime_launcher_path=context["runtime"],
        source_root=context["source_root"],
        checkpoint_path=context["checkpoint"],
        companion_root=context["companion_root"],
        execution_dir=context["execution_root"],
        out_dir=context["output"],
        **kwargs,
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    os.chmod(tmp_path, 0o700)
    paths = {
        "request": _private_file(tmp_path / "request.json"),
        "adapter": _private_file(tmp_path / "adapter.json"),
        "design": _private_file(tmp_path / "design.json"),
        "coverage": _private_file(tmp_path / "coverage.json"),
        "plan": _private_file(_private_dir(tmp_path / "plan") / "plan.json"),
        "repository": _private_dir(tmp_path / "repository"),
        "runtime": _private_file(tmp_path / "python"),
        "source_root": _private_dir(tmp_path / "source"),
        "checkpoint": _private_file(tmp_path / "model.safetensors"),
        "companion_root": _private_dir(tmp_path / "companions"),
        "execution_root": _private_dir(tmp_path / "execution"),
        "output": tmp_path / "review-package",
    }
    _private_file(paths["execution_root"] / package.EXECUTION_REPORT_NAME)
    request_binding = {
        "request_schema": "sunofriend.private-separation-execution-request.v1",
        "request_policy_id": "authorized-plan-bound-private-separation-request-v1",
        "request_report_sha256": "1" * 64,
        "request_document_sha256": "2" * 64,
        "checkpoint_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "companion_manifest_sha256": "5" * 64,
        "worker_source_sha256": "6" * 64,
    }
    loaded = {
        "path": paths["request"],
        "sha256": "1" * 64,
        "document": {
            "document_sha256": "2" * 64,
            "bindings": {
                "backend_adapter_sha256": "a" * 64,
                "route_design_sha256": "b" * 64,
                "coverage_report_sha256": "c" * 64,
            },
            "request": {
                "track_id": "track-id",
                "track_title": "Track title",
                "candidate_id": "kim-vocal-2",
            },
        },
        "adapter": {
            "path": paths["adapter"],
            "sha256": "a" * 64,
            "document": {
                "document_sha256": "d" * 64,
                "backend": {
                    "execution_environment": {
                        "checkpoint": {"sha256": "3" * 64},
                        "audited_source": {"manifest_sha256": "4" * 64},
                        "companion_manifest_sha256": "5" * 64,
                        "worker_source": {"sha256": "6" * 64},
                    }
                },
            },
            "design": {
                "path": paths["design"],
                "coverage": {"path": paths["coverage"]},
            },
            "measured": {
                "source_root": paths["source_root"],
                "companion_root": paths["companion_root"],
            },
        },
        "plan_path": paths["plan"],
        "plan_sha256": "7" * 64,
        "plan": {"document_sha256": "8" * 64},
    }
    execution = {
        "path": paths["execution_root"] / package.EXECUTION_REPORT_NAME,
        "sha256": "9" * 64,
        "document": {"state_sha256": "e" * 64},
    }
    stitch = {
        "document_sha256": "f" * 64,
        "clock": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 100,
            "boundary_count": 1,
        },
        "boundary_review": {"html": "review.html"},
    }
    alignment = {
        "path": paths["output"] / "ALIGNMENT" / package.ALIGNMENT_REPORT_NAME,
        "sha256": "0" * 64,
        "document": {
            "document_sha256": "1" * 64,
            "summary": {"gate_passed": True},
        },
    }
    seed = {"package_commitment": "2" * 64}
    monkeypatch.setattr(
        package,
        "_load_verified_private_separation_execution_request",
        lambda *_args, **_kwargs: deepcopy(loaded),
    )
    monkeypatch.setattr(package, "_request_binding", lambda value: request_binding)
    monkeypatch.setattr(
        package,
        "_load_verified_execution",
        lambda *_args, **_kwargs: deepcopy(execution),
    )
    monkeypatch.setattr(package, "_load_stitch_report", lambda _value: stitch)
    monkeypatch.setattr(package, "_verify_stitch_audio", lambda *_args: None)
    monkeypatch.setattr(package, "_sha256", lambda _value: "3" * 64)
    monkeypatch.setattr(package, "_verify_stitch_chain", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        package,
        "_load_verified_alignment",
        lambda *_args, **_kwargs: alignment,
    )
    monkeypatch.setattr(
        package,
        "_load_verified_unreviewed_seed",
        lambda *_args, **_kwargs: (seed, "4" * 64),
    )
    return paths


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def _private_file(path: Path) -> Path:
    path.write_bytes(b"{}\n")
    path.chmod(0o600)
    return path
