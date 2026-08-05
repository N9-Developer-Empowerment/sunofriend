from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_private_local_workflow as local
from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256


def test_profile_resolves_only_fixed_repository_and_private_model_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    profile = local._resolve_private_separation_local_profile(tmp_path / "repo")

    assert profile.repository_root == (tmp_path / "repo").absolute()
    assert (
        profile.runtime_launcher
        == (tmp_path / "repo/work/private-runtime-python313/venv/bin/python").absolute()
    )
    assert (
        profile.checkpoint
        == (
            tmp_path / "home/.local/share/sunofriend/private-evaluation/"
            "kim-vocal-2-mlx-v1/model.safetensors"
        ).absolute()
    )


def test_doctor_is_read_only_and_reports_only_two_stem_capability(
    tmp_path: Path,
) -> None:
    profile = _profile(tmp_path)
    before = sorted(tmp_path.rglob("*"))

    result = local._check_private_separation_local_profile(
        profile,
        adapter_loader=lambda *_args, **_kwargs: {
            "sha256": "1" * 64,
            "document": {
                "document_sha256": "2" * 64,
                "backend": {"candidate_id": "mlx-melroformer-kim-vocal-2"},
            },
        },
    )

    assert result["status"] == local.DOCTOR_STATUS
    assert result["primary_roles"] == ["vocals", "instrumental"]
    assert result["readiness"]["public_multi_stem_separator_available"] is False
    assert result["effects"]["filesystem_write"] is False
    assert sorted(tmp_path.rglob("*")) == before


def test_start_prepares_once_and_requires_explicit_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    calls = {"plan": 0, "request": 0, "preflight": 0}

    def plan_builder(
        _corpus: Path, _track_id: str, *, out_dir: Path
    ) -> dict[str, object]:
        calls["plan"] += 1
        _private_dir(out_dir)
        _private_file(out_dir / local.PLAN_REPORT_NAME, b"plan\n")
        return {}

    def request_builder(
        adapter_report: Path,
        *,
        out: Path,
        plan_report_path: Path,
        design_report_path: Path,
        coverage_report_path: Path,
        repository_root: Path,
        runtime_launcher_path: Path,
        source_root: Path,
        checkpoint_path: Path,
        companion_root: Path,
        device: str,
    ) -> dict[str, object]:
        assert adapter_report == context["repository"] / "adapter.json"
        assert plan_report_path.name == local.PLAN_REPORT_NAME
        assert design_report_path.name == "design.json"
        assert coverage_report_path.name == "coverage.json"
        assert repository_root == context["repository"]
        assert runtime_launcher_path.name == "python"
        assert source_root.name == "source"
        assert checkpoint_path.name == "model.safetensors"
        assert companion_root.name == "companions"
        assert device == "gpu"
        calls["request"] += 1
        _private_dir(out.parent)
        _private_file(out, b"request\n")
        return {}

    def execution_runner(*_args: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["execute"] is False
        calls["preflight"] += 1
        return {"status": "preflight", "readiness": {}}

    first = _start(
        context,
        plan_builder=plan_builder,
        request_builder=request_builder,
        execution_runner=execution_runner,
    )
    second = _start(
        context,
        plan_builder=plan_builder,
        request_builder=request_builder,
        execution_runner=execution_runner,
    )

    assert first["status"] == local.PREPARED_STATUS
    assert first["next_action"] == "repeat_with_explicit_execute"
    assert first["created_this_invocation"] == {
        "plan": True,
        "request": True,
        "review_package": False,
    }
    assert second["created_this_invocation"] == {
        "plan": False,
        "request": False,
        "review_package": False,
    }
    assert calls == {"plan": 1, "request": 1, "preflight": 2}
    assert not (context["root"] / local.EXECUTION_DIRECTORY).exists()


def test_explicit_start_stops_on_partial_execution_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _seed_prepared_root(context)

    result = _start(
        context,
        execute=True,
        execution_runner=lambda *_args, **_kwargs: {
            "status": "private_request_bound_execution_incomplete_review_required",
            "readiness": {"all_worker_runs_complete": False},
        },
    )

    assert result["status"] == local.INCOMPLETE_STATUS
    assert result["next_action"] == "repeat_with_explicit_execute"
    assert result["permissions"] == local._FALSE_PRODUCT_PERMISSIONS
    assert not (context["root"] / local.REVIEW_DIRECTORY).exists()


def test_explicit_complete_start_creates_review_and_repeatable_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _seed_prepared_root(context)
    execution_root = context["root"] / local.EXECUTION_DIRECTORY

    def execution_runner(*_args: object, **_kwargs: object) -> dict[str, object]:
        _private_dir(execution_root)
        return {
            "status": local.EXECUTION_COMPLETE_STATUS,
            "readiness": {
                "model_run_started_this_invocation": True,
                "all_worker_runs_complete": True,
            },
        }

    def review_builder(
        *_args: object, out_dir: Path, **_kwargs: object
    ) -> dict[str, object]:
        root = _private_dir(out_dir)
        report = _private_file(root / local.REVIEW_REPORT_NAME, b"review\n")
        html = _private_file(root / "review.html", b"<html></html>\n")
        return {
            "report": str(report),
            "review_html": str(html),
            "document_sha256": "8" * 64,
        }

    first = _start(
        context,
        execute=True,
        execution_runner=execution_runner,
        review_builder=review_builder,
    )
    second = _start(
        context,
        execute=True,
        execution_runner=execution_runner,
        review_builder=review_builder,
    )

    assert first["status"] == local.REVIEW_STATUS
    assert first["stages"]["human_review"] == "pending"
    assert first["readiness"]["finish_workflow_eligible"] is False
    assert first["created_this_invocation"]["review_package"] is True
    assert second["created_this_invocation"]["review_package"] is False
    report = context["root"] / local.REPORT_NAME
    assert report.stat().st_mode & 0o777 == 0o600
    persisted = json.loads(report.read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == _document_sha256(persisted)


def test_resume_rejects_changed_corpus_or_track(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _seed_prepared_root(context)
    context["plan"]["corpus"]["manifest_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="plan source differs"):
        _start(context)


def _start(
    context: dict[str, object],
    **kwargs: object,
) -> dict[str, object]:
    defaults = {
        "profile_checker": lambda _profile: deepcopy(context["doctor"]),
        "plan_loader": lambda _path: (
            Path(_path),
            deepcopy(context["plan"]),
            "3" * 64,
        ),
        "request_loader": lambda *_args, **_kwargs: deepcopy(context["request"]),
        "execution_runner": lambda *_args, **_kwargs: {
            "status": "preflight",
            "readiness": {},
        },
    }
    defaults.update(kwargs)
    return local._start_private_separation_local_workflow(
        context["corpus"],
        context["track_id"],
        out_dir=context["root"],
        repository_root=context["repository"],
        device="gpu",
        **defaults,
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    os.chmod(tmp_path, 0o700)
    repository = _private_dir(tmp_path / "repo")
    corpus = _private_file(tmp_path / "corpus.json", b'{"schema":"test"}\n')
    track_id = "owned-track"
    doctor = {
        "status": local.DOCTOR_STATUS,
        "adapter": {"sha256": "1" * 64, "document_sha256": "2" * 64},
    }
    plan = {
        "document_sha256": "4" * 64,
        "corpus": {
            "manifest_sha256": _sha256(corpus),
            "track_id": track_id,
            "track_title": "Owned track",
        },
    }
    request_path = (
        tmp_path / "out" / local.REQUEST_DIRECTORY / local.REQUEST_REPORT_NAME
    )
    request = {
        "path": request_path,
        "document": {
            "document_sha256": "5" * 64,
            "request": {"device": "gpu"},
        },
    }
    monkeypatch.setattr(
        local,
        "_resolve_private_separation_local_profile",
        lambda _root: _profile(repository),
    )
    return {
        "repository": repository,
        "corpus": corpus,
        "track_id": track_id,
        "root": tmp_path / "out",
        "doctor": doctor,
        "plan": plan,
        "request": request,
    }


def _seed_prepared_root(context: dict[str, object]) -> None:
    root = _private_dir(Path(context["root"]))
    _private_file(root / local.PLAN_DIRECTORY / local.PLAN_REPORT_NAME, b"plan\n")
    _private_file(
        root / local.REQUEST_DIRECTORY / local.REQUEST_REPORT_NAME, b"request\n"
    )


def _profile(root: Path) -> local.PrivateSeparationLocalProfile:
    repository = _private_dir(root) if not root.exists() else root
    return local.PrivateSeparationLocalProfile(
        repository_root=repository,
        adapter_report=repository / "adapter.json",
        design_report=repository / "design.json",
        coverage_report=repository / "coverage.json",
        runtime_launcher=repository / "python",
        source_root=repository / "source",
        checkpoint=repository / "model.safetensors",
        companion_root=repository / "companions",
    )


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.chmod(0o700)
    return path


def _private_file(path: Path, payload: bytes = b"private\n") -> Path:
    _private_dir(path.parent)
    path.write_bytes(payload)
    path.chmod(0o600)
    return path
