from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_private_execution_request as request
from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_full_song_plan import POLICY_ID as PLAN_POLICY_ID


def test_builds_path_free_model_free_authorized_execution_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    output = context["output_parent"] / request.REPORT_NAME

    result = _build(context, output=output)

    assert result["status"] == request.STATUS
    assert result["request"]["track_id"] == "owned-track"
    assert result["request"]["candidate_id"] == "mlx-melroformer-kim-vocal-2"
    assert result["request"]["primary_roles"] == ["vocals", "instrumental"]
    assert result["request"]["diagnostic_roles"] == ["reconstruction"]
    assert result["readiness"]["private_execution_request_complete"] is True
    assert result["readiness"]["private_model_execution_permitted"] is False
    assert result["readiness"]["next_stage"] == (
        "implement_separate_developer_only_execution_gate"
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


def test_accepts_private_local_user_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["plan"]["corpus"]["rights_authority"] = (
        "user_authorised_private_local_evaluation"
    )

    result = _build(context)

    assert result["request"]["rights_authority"] == (
        "user_authorised_private_local_evaluation"
    )


def test_rejects_plan_without_supported_rights_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["plan"]["corpus"]["rights_authority"] = "unknown"

    with pytest.raises(ValueError, match="plan policy differs"):
        _build(context)


def test_rejects_plan_that_grants_source_graph_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["plan"]["permissions"]["source_graph_activation"] = True

    with pytest.raises(ValueError, match="plan policy differs"):
        _build(context)


def test_rejects_noncontiguous_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["plan"]["chunking"]["gap_frames"] = 1

    with pytest.raises(ValueError, match="plan policy differs"):
        _build(context)


def test_rejects_adapter_change_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    first = deepcopy(context["adapter"])
    second = deepcopy(first)
    second["sha256"] = "e" * 64
    calls = iter((first, second))
    monkeypatch.setattr(
        request,
        "_load_adapter",
        lambda *_args, **_kwargs: next(calls),
    )

    with pytest.raises(ValueError, match="inputs changed"):
        _build(context)


def test_rejects_plan_change_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    first = deepcopy(context["plan"])
    second = deepcopy(first)
    second["source"]["sha256"] = "e" * 64
    calls = iter((first, second))
    monkeypatch.setattr(
        request,
        "_load_verified_plan",
        lambda *_args, **_kwargs: (
            context["plan_path"],
            next(calls),
            "8" * 64,
        ),
    )

    with pytest.raises(ValueError, match="inputs changed"):
        _build(context)


def test_requires_explicit_device_and_fresh_fixed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="device"):
        _build(context, device="auto")
    with pytest.raises(ValueError, match="filename"):
        _build(context, output=context["output_parent"] / "other.json")

    output = context["output_parent"] / request.REPORT_NAME
    _build(context, output=output)
    with pytest.raises(FileExistsError):
        _build(context, output=output)


def test_rejects_output_inside_plan_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="overlaps evidence"):
        _build(context, output=context["plan_path"].parent / request.REPORT_NAME)


def test_loader_reconstructs_request_from_adapter_and_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    output = context["output_parent"] / request.REPORT_NAME
    result = _build(context, output=output)
    snapshot = {
        "path": output,
        "sha256": "d" * 64,
        "document": {key: value for key, value in result.items() if key not in {"report", "plan_report"}},
    }
    monkeypatch.setattr(
        request,
        "_load_private_json_snapshot",
        lambda *_args, **_kwargs: deepcopy(snapshot),
    )

    loaded = request._load_verified_private_separation_execution_request(
        output,
        adapter_report_path=context["adapter_path"],
        design_report_path=context["design_path"],
        coverage_report_path=context["coverage_path"],
        plan_report_path=context["plan_path"],
        repository_root=context["repository"],
        runtime_launcher_path=context["runtime"],
        source_root=context["source_root"],
        checkpoint_path=context["checkpoint"],
        companion_root=context["companion_root"],
    )

    assert loaded["document"]["status"] == request.STATUS
    assert loaded["plan_sha256"] == "8" * 64


def test_loader_rejects_rewritten_request_even_with_valid_self_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    output = context["output_parent"] / request.REPORT_NAME
    result = _build(context, output=output)
    document = {
        key: value for key, value in result.items() if key not in {"report", "plan_report"}
    }
    document["readiness"]["private_model_execution_permitted"] = True
    document["document_sha256"] = _document_sha256(document)
    monkeypatch.setattr(
        request,
        "_load_private_json_snapshot",
        lambda *_args, **_kwargs: {
            "path": output,
            "sha256": "d" * 64,
            "document": document,
        },
    )

    with pytest.raises(ValueError, match="request differs"):
        request._load_verified_private_separation_execution_request(
            output,
            adapter_report_path=context["adapter_path"],
            design_report_path=context["design_path"],
            coverage_report_path=context["coverage_path"],
            plan_report_path=context["plan_path"],
            repository_root=context["repository"],
            runtime_launcher_path=context["runtime"],
            source_root=context["source_root"],
            checkpoint_path=context["checkpoint"],
            companion_root=context["companion_root"],
        )


def _build(
    context: dict[str, object],
    *,
    output: Path | None = None,
    device: str = "gpu",
) -> dict[str, object]:
    return request._build_private_separation_execution_request(
        context["adapter_path"],
        design_report_path=context["design_path"],
        coverage_report_path=context["coverage_path"],
        plan_report_path=context["plan_path"],
        repository_root=context["repository"],
        runtime_launcher_path=context["runtime"],
        source_root=context["source_root"],
        checkpoint_path=context["checkpoint"],
        companion_root=context["companion_root"],
        device=device,
        out=output or context["output_parent"] / request.REPORT_NAME,
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
    plan_root = _private_dir(tmp_path / "plan")
    runtime = _private_file(tmp_path / "python", b"runtime\n")
    checkpoint = _private_file(tmp_path / "checkpoint.safetensors", b"checkpoint\n")
    adapter_path = _private_file(
        tmp_path / "private-separation-backend-adapter-contract.json",
        b"adapter\n",
    )
    design_path = _private_file(
        tmp_path / "private-separation-route-design.json",
        b"design\n",
    )
    coverage_path = _private_file(
        tmp_path / "private-separation-multi-song-private-pilot-coverage.json",
        b"coverage\n",
    )
    plan_path = _private_file(
        plan_root / "private-separation-full-song-plan.json",
        b"plan\n",
    )
    design_snapshot = {
        "path": design_path,
        "sha256": "1" * 64,
        "document": {"document_sha256": "2" * 64},
        "coverage": {
            "path": coverage_path,
            "sha256": "3" * 64,
            "document": {"document_sha256": "4" * 64},
        },
    }
    adapter_snapshot = {
        "path": adapter_path,
        "sha256": "5" * 64,
        "document": {
            "document_sha256": "6" * 64,
            "backend": {
                "candidate_id": "mlx-melroformer-kim-vocal-2",
                "execution_environment": {
                    "checkpoint": {"sha256": "7" * 64},
                },
            },
            "mode_isolation": {
                "simple_can_discover_output": False,
                "studio_can_discover_output": False,
                "tui_can_execute_route": False,
                "public_cli_can_execute_route": False,
                "source_graph_can_import_output": False,
                "download_pack_can_include_output": False,
            },
        },
        "design": design_snapshot,
    }
    plan = _plan_document()
    monkeypatch.setattr(
        request,
        "_load_adapter",
        lambda *_args, **_kwargs: deepcopy(adapter_snapshot),
    )
    monkeypatch.setattr(
        request,
        "_load_verified_plan",
        lambda *_args, **_kwargs: (plan_path, deepcopy(plan), "8" * 64),
    )
    return {
        "output_parent": output_parent,
        "repository": repository,
        "source_root": source_root,
        "companion_root": companion_root,
        "runtime": runtime,
        "checkpoint": checkpoint,
        "adapter_path": adapter_path,
        "design_path": design_path,
        "coverage_path": coverage_path,
        "plan_path": plan_path,
        "adapter": adapter_snapshot,
        "plan": plan,
    }


def _plan_document() -> dict[str, object]:
    return {
        "policy_id": PLAN_POLICY_ID,
        "document_sha256": "9" * 64,
        "corpus": {
            "manifest_sha256": "a" * 64,
            "track_id": "owned-track",
            "track_title": "Owned Track",
            "rights_authority": "creator_and_copyright_holder",
        },
        "source": {
            "sha256": "b" * 64,
            "bytes": 1_000_000,
            "extension": ".wav",
            "geometry": {
                "sample_rate": 48_000,
                "channels": 2,
                "frames": 4_800_000,
                "duration_seconds": 100.0,
            },
        },
        "canonical_clock": {
            "pcm24_int32_sequence_sha256": "c" * 64,
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 4_410_000,
            "duration_seconds": 100.0,
        },
        "chunking": {
            "chunk_count": 7,
            "maximum_chunk_frames": 661_500,
            "maximum_chunk_seconds": 15.0,
            "gap_frames": 0,
            "overlap_frames": 0,
            "contiguous_exact_frame_coverage": True,
        },
        "readiness": {
            "chunk_authorisations_ready": True,
            "worker_runs_complete": False,
            "stitched_outputs_complete": False,
            "boundary_listening_complete": False,
            "full_song_duration_and_alignment_gate_passed": False,
            "resource_envelope_gate_passed": False,
            "publication_ready": False,
        },
        "permissions": deepcopy(request._PLAN_PERMISSIONS),
        "effects": deepcopy(request._PLAN_EFFECTS),
    }


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def _private_file(path: Path, contents: bytes) -> Path:
    path.write_bytes(contents)
    os.chmod(path, 0o600)
    return path
