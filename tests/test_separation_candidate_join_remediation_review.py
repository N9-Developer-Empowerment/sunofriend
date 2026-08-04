from __future__ import annotations

import json
from pathlib import Path
import stat

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    CANDIDATES_DIRECTORY,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
    _EFFECTS_COMPLETE,
)
from sunofriend._separation_candidate_join_remediation_plan import POLICY_ID
from sunofriend._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    REPORT_NAME,
    SCHEMA,
    _prepare_private_candidate_join_remediation_review,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    REPORT_NAME as V2_REPORT_NAME,
    SCHEMA as V2_SCHEMA,
    STATUS as V2_STATUS,
    _EFFECTS as V2_EFFECTS,
    _FALSE_PERMISSIONS,
    _audio_claim,
    _read_pcm24_snapshot,
)
from sunofriend._separation_full_song_join_remediation_plan_v2 import (
    POLICY_ID as V2_POLICY_ID,
)
from sunofriend._separation_full_song_join_remediation_review import HTML_NAME


SAMPLE_RATE = 44_100


def test_builds_blind_v2_control_followup_review_with_playable_audio(
    tmp_path: Path,
) -> None:
    execution, v2 = _evidence(tmp_path)
    output = tmp_path / "review"

    result = _prepare_private_candidate_join_remediation_review(
        execution, v2_execution_dir=v2, out_dir=output
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == "unreviewed"
    assert result["expected_counts"] == {
        "boundary_role_pairs": 1,
        "patch_edge_pairs": 2,
        "complete_song_pairs": 3,
        "total_units": 6,
    }
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert all(value is False for value in result["readiness"].values())

    report = _read(output / REPORT_NAME)
    answer = _read(output / ANSWER_KEY_NAME)
    assert report["document_sha256"] == _document_sha256(report)
    assert answer["document_sha256"] == _document_sha256(answer)
    assert report["bindings"]["answer_key_sha256"] == _sha256(
        output / ANSWER_KEY_NAME
    )
    assert len(answer["units"]) == 6
    for unit in answer["units"]:
        assert set(unit["assignment"].values()) == {
            "v2_control",
            "followup_candidate",
        }

    page = (output / HTML_NAME).read_text(encoding="utf-8")
    assert '"assignment"' not in page
    assert ANSWER_KEY_NAME not in page
    for unit in report["units"]:
        for record in unit["audio"].values():
            path = (output / record["path"]).resolve()
            assert path.is_file()
            assert path.stat().st_size == record["bytes"]
            assert _sha256(path) == record["sha256"]
            assert soundfile.info(path).frames > 0
            assert record["path"] in page
    for path in output.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def test_review_refuses_existing_output_and_changed_candidate_audio(
    tmp_path: Path,
) -> None:
    execution, v2 = _evidence(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o700)
    marker = existing / "keep"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="review exists"):
        _prepare_private_candidate_join_remediation_review(
            execution, v2_execution_dir=v2, out_dir=existing
        )
    assert marker.read_text(encoding="utf-8") == "keep\n"

    candidate = execution / CANDIDATES_DIRECTORY / "vocals.wav"
    candidate.chmod(0o600)
    with candidate.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="binding differs"):
        _prepare_private_candidate_join_remediation_review(
            execution,
            v2_execution_dir=v2,
            out_dir=tmp_path / "changed-review",
        )
    assert not (tmp_path / "changed-review").exists()


def _evidence(tmp_path: Path) -> tuple[Path, Path]:
    frames = 12 * SAMPLE_RATE
    time = np.arange(frames, dtype="float64") / SAMPLE_RATE
    base_vocals = np.column_stack(
        (0.08 * np.sin(2 * np.pi * 220 * time), 0.08 * np.sin(2 * np.pi * 220 * time))
    )
    base_instrumental = np.column_stack(
        (0.12 * np.sin(2 * np.pi * 110 * time), 0.12 * np.sin(2 * np.pi * 110 * time))
    )
    changed_vocals = base_vocals.copy()
    start = 4 * SAMPLE_RATE
    end = 8 * SAMPLE_RATE
    changed_vocals[start:end] *= 0.92

    v2 = tmp_path / "v2"
    execution = tmp_path / "followup"
    v2_candidates = v2 / CANDIDATES_DIRECTORY
    candidates = execution / CANDIDATES_DIRECTORY
    v2_candidates.mkdir(parents=True, mode=0o700)
    candidates.mkdir(parents=True, mode=0o700)
    v2.chmod(0o700)
    execution.chmod(0o700)

    v2_artifacts = _write_roles(
        v2_candidates, base_vocals, base_instrumental, report_root=v2
    )
    candidate_artifacts = _write_roles(
        candidates, changed_vocals, base_instrumental, report_root=candidates
    )
    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": frames,
        "boundary_count": 1,
        "duration_seconds": frames / SAMPLE_RATE,
    }
    v2_report = {
        "schema": V2_SCHEMA,
        "status": V2_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": V2_POLICY_ID,
        "clock": clock,
        "artifacts": v2_artifacts,
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(V2_EFFECTS),
    }
    v2_report["document_sha256"] = _document_sha256(v2_report)
    _write(v2 / V2_REPORT_NAME, v2_report)

    protocol = {
        "edge_blend_frames": SAMPLE_RATE // 10,
        "patch_duration_frames": end - start,
    }
    patch = {
        "window_index": 1,
        "boundary_index": 1,
        "role": "vocals",
        "patch_start_frame": start,
        "patch_end_frame": end,
        "edge_blend_frames": SAMPLE_RATE // 10,
    }
    candidate = {
        "schema": "sunofriend.private-separation-candidate-join-remediation-candidates.v1",
        "status": "candidate_audio_complete_review_required",
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "v2_execution_report_sha256": _sha256(v2 / V2_REPORT_NAME),
            "v2_execution_document_sha256": v2_report["document_sha256"],
            "v2_vocals_audio_sha256": v2_artifacts["vocals"]["sha256"],
            "v2_instrumental_audio_sha256": v2_artifacts["instrumental"]["sha256"],
        },
        "clock": clock,
        "protocol": protocol,
        "patches": [patch],
        "artifacts": candidate_artifacts,
        "summary": {"patched_boundary_role_pair_count": 1},
        "readiness": {
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS_COMPLETE),
    }
    candidate["document_sha256"] = _document_sha256(candidate)
    _write(candidates / CANDIDATE_REPORT_NAME, candidate)

    current_artifacts = {
        role: {**claim, "path": f"{CANDIDATES_DIRECTORY}/{role}.wav"}
        for role, claim in candidate_artifacts.items()
    }
    current = {
        "schema": EXECUTION_SCHEMA,
        "status": EXECUTION_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "candidate_report_sha256": _sha256(candidates / CANDIDATE_REPORT_NAME),
            "candidate_document_sha256": candidate["document_sha256"],
        },
        "clock": clock,
        "protocol": protocol,
        "artifacts": current_artifacts,
        "readiness": {
            "candidate_audio_complete": True,
            "candidate_review_complete": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS_COMPLETE),
    }
    current["document_sha256"] = _document_sha256(current)
    _write(execution / EXECUTION_REPORT_NAME, current)
    return execution, v2


def _write_roles(
    root: Path,
    vocals: np.ndarray,
    instrumental: np.ndarray,
    *,
    report_root: Path,
) -> dict[str, dict[str, object]]:
    values = {
        "vocals": vocals,
        "instrumental": instrumental,
        "reconstruction": vocals + instrumental,
    }
    artifacts: dict[str, dict[str, object]] = {}
    for role, samples in values.items():
        path = root / f"{role}.wav"
        soundfile.write(path, samples, SAMPLE_RATE, subtype="PCM_24")
        path.chmod(0o600)
        snapshot = _read_pcm24_snapshot(
            path, None, expected_frames=len(samples), label=f"test {role}"
        )
        claim = _audio_claim(path, root=report_root, snapshot=snapshot)
        artifacts[role] = claim
    return artifacts


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
