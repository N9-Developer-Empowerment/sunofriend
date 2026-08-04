from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_full_song_alignment import (
    POLICY_ID,
    SCHEMA,
    _measure_private_candidate_full_song_alignment,
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
    POLICY_ID as REVIEW_POLICY_ID,
    _FALSE_EFFECTS as REVIEW_FALSE_EFFECTS,
    _source_bindings,
)


SAMPLE_RATE = 44_100
FRAMES = 6 * SAMPLE_RATE


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _json(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _package(tmp_path: Path) -> Path:
    package = _private_dir(tmp_path / "stitch")
    source_dir = _private_dir(package / "SOURCE")
    stems_dir = _private_dir(package / "STEMS")
    time = np.arange(FRAMES, dtype=np.float64) / SAMPLE_RATE
    carrier = np.sin(2.0 * np.pi * (110.0 * time + 15.0 * time * time))
    movement = 0.6 + 0.3 * np.sin(2.0 * np.pi * 1.7 * time)
    accents = np.where((time % 0.71) < 0.08, 0.25, 0.0)
    mono = 0.22 * carrier * movement + accents * np.sin(2.0 * np.pi * 880.0 * time)
    source = np.column_stack((mono, 0.93 * mono))
    reconstruction = 0.82 * source
    arrays = {
        "source": source,
        "vocals": 0.35 * reconstruction,
        "instrumental": 0.65 * reconstruction,
        "reconstruction": reconstruction,
    }
    paths = {
        "source": source_dir / "source-44100.wav",
        "vocals": stems_dir / "vocals.wav",
        "instrumental": stems_dir / "instrumental.wav",
        "reconstruction": stems_dir / "reconstruction.wav",
    }
    artifacts = {}
    for role, path in paths.items():
        soundfile.write(path, arrays[role], SAMPLE_RATE, subtype="PCM_24")
        path.chmod(0o600)
        artifacts[role] = {
            "path": path.relative_to(package).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "frames": FRAMES,
                "sample_width_bytes": 3,
            },
        }
    document = {
        "schema": "sunofriend.private-separation-full-song-stitch.v1",
        "status": "exact_clock_stitch_complete_review_required",
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_document_sha256": hashlib.sha256(b"plan").hexdigest(),
            "execution_state_sha256": hashlib.sha256(b"execution").hexdigest(),
        },
        "clock": {
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": FRAMES,
            "duration_seconds": FRAMES / SAMPLE_RATE,
            "chunk_count": 2,
            "boundary_count": 1,
            "gap_frames": 0,
            "overlap_frames": 0,
            "crossfade_frames": 0,
        },
        "artifacts": artifacts,
        "boundary_review": {"boundary_count": 1},
        "permissions": dict(_FALSE_PERMISSIONS),
    }
    document["document_sha256"] = _document_sha256(document)
    report = _json(package / "private-separation-full-song-stitch.json", document)
    report.chmod(0o600)
    os.chmod(tmp_path, stat.S_IMODE(tmp_path.stat().st_mode) & ~0o077)
    return package


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    tmp_path.chmod(0o700)
    stitch_root = _package(tmp_path)
    stitch_path = stitch_root / "private-separation-full-song-stitch.json"
    stitch = json.loads(stitch_path.read_text(encoding="utf-8"))
    v1_root = _private_dir(tmp_path / "v1")
    v2_root = _private_dir(tmp_path / "v2")
    candidates = _private_dir(v2_root / "CANDIDATES")
    reconstruction = candidates / "reconstruction.wav"
    shutil.copyfile(stitch_root / "STEMS/reconstruction.wav", reconstruction)
    reconstruction.chmod(0o600)
    observed = _read_pcm24_snapshot(
        reconstruction,
        None,
        expected_frames=int(stitch["clock"]["frames"]),
        label="test candidate reconstruction",
    )
    artifact = {
        "path": "CANDIDATES/reconstruction.wav",
        "sha256": observed["sha256"],
        "bytes": observed["bytes"],
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": int(stitch["clock"]["frames"]),
            "sample_width_bytes": 3,
        },
        "pcm24_int32_sequence_sha256": observed[
            "pcm24_int32_sequence_sha256"
        ],
    }

    def snapshot(name: str) -> dict[str, object]:
        root = _private_dir(tmp_path / name)
        path = _json(root / "evidence.json", {"name": name})
        return {"path": path, "sha256": _sha256(path), "document": {"name": name}}

    v2_plan_snapshot = snapshot("v2-plan")
    stitch_snapshot = {
        "path": stitch_path,
        "sha256": _sha256(stitch_path),
        "document": stitch,
    }
    v1_execution_snapshot = snapshot("v1-execution")
    v1_candidate_snapshot = snapshot("v1-candidate")
    v2_snapshot = snapshot("v2-execution")
    authority_paths = []
    for index in range(4):
        root = _private_dir(tmp_path / f"authority-{index}")
        authority_paths.append(_json(root / "evidence.json", {"index": index}))
    context = {
        "v1_root": v1_root,
        "v2_root": v2_root,
        "stitch_root": stitch_root,
        "stitch": stitch,
        "v2_plan_snapshot": v2_plan_snapshot,
        "v2_plan": {"document_sha256": "2" * 64},
        "stitch_snapshot": stitch_snapshot,
        "v1_execution_snapshot": v1_execution_snapshot,
        "v1_state": {"state_sha256": "3" * 64},
        "v1_candidate_snapshot": v1_candidate_snapshot,
        "v1_candidate": {"document_sha256": "4" * 64},
        "v2_snapshot": v2_snapshot,
        "v2_report": {"document_sha256": "5" * 64, "artifacts": {"reconstruction": artifact}},
        "authority_paths": tuple(authority_paths),
    }
    monkeypatch.setattr(
        "sunofriend._separation_candidate_full_song_alignment._load_review_inputs",
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_full_song_alignment._reverify_inputs",
        lambda value: None,
    )

    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": REVIEW_POLICY_ID,
        "package_commitment": "6" * 64,
        "bindings": _source_bindings(context),
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
    result_root = _private_dir(tmp_path / "v2-result")
    result_path = _json(result_root / "result.json", result)
    output_root = _private_dir(tmp_path / "alignment-result")
    return {
        "context": context,
        "review_result": result,
        "review_result_path": result_path,
        "out": output_root / "alignment.json",
    }


def _args(fixture: dict[str, object]) -> dict[str, object]:
    tmp = Path(fixture["review_result_path"]).parent.parent
    return {
        "v2_execution_dir": tmp / "unused-v2",
        "v2_plan_path": tmp / "unused-v2-plan.json",
        "v1_execution_dir": tmp / "unused-v1",
        "stitch_package_dir": tmp / "unused-stitch",
        "full_song_review_result_path": tmp / "unused-full-review.json",
        "v1_plan_path": tmp / "unused-v1-plan.json",
        "resolved_join_review_result_path": tmp / "unused-join-result.json",
        "publication_readiness_path": tmp / "unused-readiness.json",
        "out": fixture["out"],
    }


def test_measures_fresh_candidate_bound_alignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = _measure_private_candidate_full_song_alignment(
        fixture["review_result_path"], **_args(fixture)
    )

    assert result["schema"] == SCHEMA
    assert result["policy_id"] == POLICY_ID
    assert len(result["windows"]) == 9
    assert result["readiness_evidence"]["alignment_gate_passed"] is True
    assert result["readiness_evidence"]["new_candidate_alignment_complete"] is True
    assert result["readiness_evidence"]["new_candidate_full_song_review_complete"] is False
    assert result["readiness_evidence"]["original_audible_joins_resolved"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert Path(fixture["out"]).is_file()


def test_alignment_refuses_non_passing_targeted_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = fixture["review_result"]
    result["readiness_evidence"]["all_v2_patch_edges_clean"] = False
    result["readiness_evidence"]["targeted_v2_absolute_cleanliness_pass"] = False
    result["document_sha256"] = _document_sha256(result)
    _json(fixture["review_result_path"], result)

    with pytest.raises(ValueError, match="did not pass"):
        _measure_private_candidate_full_song_alignment(
            fixture["review_result_path"], **_args(fixture)
        )
    assert not Path(fixture["out"]).exists()
