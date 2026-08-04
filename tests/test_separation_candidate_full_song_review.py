from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_full_song_review import (
    REPORT_NAME,
    STATUS,
    _build_private_candidate_full_song_review,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
)
from sunofriend._separation_full_song_join_remediation_review_result_v2 import (
    RESULT_SCHEMA,
    RESULT_STATUS,
)
from sunofriend._separation_full_song_join_remediation_review_v2 import (
    POLICY_ID,
    _FALSE_EFFECTS as REVIEW_FALSE_EFFECTS,
    _source_bindings,
)
from sunofriend._separation_full_song_stitch import _write_boundary_review


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _write_audio(path: Path, values: np.ndarray) -> dict[str, object]:
    soundfile.write(path, values, 44_100, subtype="PCM_24")
    path.chmod(0o600)
    observed = _read_pcm24_snapshot(
        path,
        None,
        expected_frames=len(values),
        label="test PCM24 audio",
    )
    return {
        "path": path.name,
        "sha256": observed["sha256"],
        "bytes": observed["bytes"],
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": len(values),
            "sample_width_bytes": 3,
        },
        "pcm24_int32_sequence_sha256": observed[
            "pcm24_int32_sequence_sha256"
        ],
    }


def _json(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    tmp_path.chmod(0o700)
    stitch_root = _private_dir(tmp_path / "stitch")
    source_root = _private_dir(stitch_root / "SOURCE")
    stems_root = _private_dir(stitch_root / "STEMS")
    v1_root = _private_dir(tmp_path / "v1")
    v2_root = _private_dir(tmp_path / "v2")
    candidates = _private_dir(v2_root / "CANDIDATES")
    frames = 8_820
    clock = np.arange(frames, dtype="float64") / 44_100
    source = np.column_stack(
        (0.12 * np.sin(2 * np.pi * 110 * clock), 0.11 * np.sin(2 * np.pi * 110 * clock))
    )
    vocals = np.column_stack(
        (0.08 * np.sin(2 * np.pi * 220 * clock), 0.07 * np.sin(2 * np.pi * 220 * clock))
    )
    instrumental = np.column_stack(
        (0.06 * np.sin(2 * np.pi * 330 * clock), 0.05 * np.sin(2 * np.pi * 330 * clock))
    )
    reconstruction = vocals + instrumental

    source_claim = _write_audio(source_root / "source-44100.wav", source)
    source_claim["path"] = "SOURCE/source-44100.wav"
    original_roles = {
        "source": source_root / "source-44100.wav",
        "vocals": stems_root / "vocals.wav",
        "instrumental": stems_root / "instrumental.wav",
        "reconstruction": stems_root / "reconstruction.wav",
    }
    _write_audio(original_roles["vocals"], vocals)
    _write_audio(original_roles["instrumental"], instrumental)
    _write_audio(original_roles["reconstruction"], reconstruction)
    boundary_review = _write_boundary_review(
        stitch_root,
        title="Fixture",
        boundaries=[4_410],
        role_paths=original_roles,
        soundfile=soundfile,
        np=np,
    )

    v2_artifacts: dict[str, object] = {}
    for role, values in (
        ("vocals", vocals * 0.97),
        ("instrumental", instrumental * 0.96),
        ("reconstruction", reconstruction * 0.965),
    ):
        claim = _write_audio(candidates / f"{role}.wav", values)
        claim["path"] = f"CANDIDATES/{role}.wav"
        v2_artifacts[role] = claim

    snapshots: dict[str, dict[str, object]] = {}
    for name in ("v2-plan", "stitch-report", "v1-execution", "v1-candidate", "v2-execution"):
        snapshot_root = _private_dir(tmp_path / name)
        path = _json(snapshot_root / "evidence.json", {"name": name})
        snapshots[name] = {"path": path, "sha256": _sha256(path), "document": {"name": name}}
    authority_paths = []
    for index in range(4):
        authority_root = _private_dir(tmp_path / f"authority-{index}")
        authority_paths.append(_json(authority_root / "evidence.json", {"index": index}))

    stitch = {
        "clock": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": frames,
            "duration_seconds": frames / 44_100,
            "chunk_count": 2,
            "boundary_count": 1,
            "gap_frames": 0,
            "overlap_frames": 0,
            "crossfade_frames": 0,
        },
        "artifacts": {"source": source_claim},
        "boundary_review": boundary_review,
        "document_sha256": "1" * 64,
    }
    context = {
        "v1_root": v1_root,
        "v2_root": v2_root,
        "stitch_root": stitch_root,
        "stitch": stitch,
        "v2_plan_snapshot": snapshots["v2-plan"],
        "v2_plan": {"document_sha256": "2" * 64},
        "stitch_snapshot": snapshots["stitch-report"],
        "v1_execution_snapshot": snapshots["v1-execution"],
        "v1_state": {"state_sha256": "3" * 64},
        "v1_candidate_snapshot": snapshots["v1-candidate"],
        "v1_candidate": {"document_sha256": "4" * 64},
        "v2_snapshot": snapshots["v2-execution"],
        "v2_report": {"document_sha256": "5" * 64, "artifacts": v2_artifacts},
        "authority_paths": tuple(authority_paths),
    }
    monkeypatch.setattr(
        "sunofriend._separation_candidate_full_song_review._load_review_inputs",
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_full_song_review._reverify_inputs",
        lambda value: None,
    )

    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "package_commitment": hashlib.sha256(b"fixture").hexdigest(),
        "bindings": {
            **_source_bindings(context),
            "review_seed_sha256": "6" * 64,
            "review_export_sha256": "7" * 64,
            "answer_key_sha256": "8" * 64,
        },
        "readiness_evidence": {
            "targeted_v2_review_complete": True,
            "all_targeted_v2_boundary_versions_clean": True,
            "all_v2_patch_edges_clean": True,
            "targeted_v2_absolute_cleanliness_pass": True,
            "fresh_candidate_bound_full_song_review_eligible": True,
            "fresh_candidate_bound_alignment_review_eligible": True,
            "new_candidate_full_song_review_complete": False,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(REVIEW_FALSE_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    result_root = _private_dir(tmp_path / "v2-review-result")
    result_path = _json(result_root / "result.json", result)
    return {
        "context": context,
        "result": result,
        "result_path": result_path,
        "out": tmp_path / "candidate-review",
    }


def _build_args(fixture: dict[str, object]) -> dict[str, object]:
    tmp = Path(fixture["result_path"]).parent
    return {
        "v2_execution_dir": tmp / "unused-v2",
        "v2_plan_path": tmp / "unused-plan.json",
        "v1_execution_dir": tmp / "unused-v1",
        "stitch_package_dir": tmp / "unused-stitch",
        "full_song_review_result_path": tmp / "unused-full-review.json",
        "v1_plan_path": tmp / "unused-v1-plan.json",
        "resolved_join_review_result_path": tmp / "unused-join-result.json",
        "publication_readiness_path": tmp / "unused-readiness.json",
        "out_dir": fixture["out"],
    }


def test_builds_fresh_candidate_bound_full_song_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = _build_private_candidate_full_song_review(
        fixture["result_path"], **_build_args(fixture)
    )

    out = Path(fixture["out"])
    assert result["status"] == STATUS
    assert result["clock"]["boundary_count"] == 1
    assert result["readiness"]["new_candidate_full_song_review_complete"] is False
    assert (out / REPORT_NAME).is_file()
    assert (out / "BOUNDARY-REVIEW/separation_boundary_review.html").is_file()
    assert (out / "BOUNDARY-REVIEW/separation_boundary_review.json").is_file()
    assert len(list((out / "BOUNDARY-REVIEW/audio").glob("*.wav"))) == 4
    assert all((out / record["path"]).is_file() for record in result["artifacts"].values())


def test_refuses_non_passing_targeted_review_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = fixture["result"]
    result["readiness_evidence"]["all_v2_patch_edges_clean"] = False
    result["readiness_evidence"]["targeted_v2_absolute_cleanliness_pass"] = False
    result["readiness_evidence"]["fresh_candidate_bound_full_song_review_eligible"] = False
    result["document_sha256"] = _document_sha256(result)
    _json(fixture["result_path"], result)

    with pytest.raises(ValueError, match="did not pass"):
        _build_private_candidate_full_song_review(
            fixture["result_path"], **_build_args(fixture)
        )
    assert not Path(fixture["out"]).exists()


def test_refuses_result_with_wrong_v2_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = fixture["result"]
    result["bindings"]["v2_execution_report_sha256"] = "f" * 64
    result["document_sha256"] = _document_sha256(result)
    _json(fixture["result_path"], result)

    with pytest.raises(ValueError, match="result differs"):
        _build_private_candidate_full_song_review(
            fixture["result_path"], **_build_args(fixture)
        )
    assert not Path(fixture["out"]).exists()


def test_refuses_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    Path(fixture["out"]).mkdir(mode=0o700)
    with pytest.raises(FileExistsError):
        _build_private_candidate_full_song_review(
            fixture["result_path"], **_build_args(fixture)
        )
