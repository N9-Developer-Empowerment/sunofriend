from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_followup_full_song_review import (
    REPORT_NAME,
    STATUS,
    _build_private_candidate_followup_full_song_review,
    _verified_passing_targeted_result,
)
from sunofriend._separation_candidate_join_remediation_review_result import (
    _resolve_private_candidate_join_remediation_review,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
)
from sunofriend._separation_full_song_stitch import _write_boundary_review
from tests.test_separation_candidate_join_remediation_review_result import (
    _completed_review,
)


SAMPLE_RATE = 44_100


def _write(path: Path, document: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _audio(path: Path, values: np.ndarray, *, relative: str) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    soundfile.write(path, values, SAMPLE_RATE, subtype="PCM_24")
    path.chmod(0o600)
    snapshot = _read_pcm24_snapshot(
        path, None, expected_frames=len(values), label="test follow-up audio"
    )
    return {
        "path": relative,
        "sha256": snapshot["sha256"],
        "bytes": snapshot["bytes"],
        "geometry": {
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": len(values),
            "sample_width_bytes": 3,
        },
        "pcm24_int32_sequence_sha256": snapshot[
            "pcm24_int32_sequence_sha256"
        ],
    }


def test_rederives_and_accepts_only_the_exact_passing_targeted_result(
    tmp_path: Path,
) -> None:
    execution, v2, review_root, reviewed = _completed_review(tmp_path)
    result_path = tmp_path / "result" / "resolved.json"
    expected = _resolve_private_candidate_join_remediation_review(
        reviewed,
        review_package_dir=review_root,
        execution_dir=execution,
        v2_execution_dir=v2,
        out=result_path,
    )
    expected.pop("report")

    verified = _verified_passing_targeted_result(
        result_path,
        reviewed_export_path=reviewed,
        targeted_review_package_dir=review_root,
        execution_dir=execution,
        v2_execution_dir=v2,
    )

    assert verified == expected
    assert verified["readiness_evidence"]["targeted_followup_listening_pass"] is True

    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["readiness_evidence"]["publication_ready"] = True
    tampered["document_sha256"] = _document_sha256(tampered)
    _write(result_path, tampered)
    with pytest.raises(ValueError, match="result differs"):
        _verified_passing_targeted_result(
            result_path,
            reviewed_export_path=reviewed,
            targeted_review_package_dir=review_root,
            execution_dir=execution,
            v2_execution_dir=v2,
        )


def _builder_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    tmp_path.chmod(0o700)
    frames = SAMPLE_RATE * 2
    time = np.arange(frames, dtype="float64") / SAMPLE_RATE
    vocals = np.column_stack(
        (0.08 * np.sin(2 * np.pi * 220 * time),) * 2
    )
    instrumental = np.column_stack(
        (0.12 * np.sin(2 * np.pi * 110 * time),) * 2
    )
    source = vocals + instrumental
    reconstruction = source.copy()

    execution = tmp_path / "execution"
    v2 = tmp_path / "v2"
    review_package = tmp_path / "targeted-review"
    stitch_root = tmp_path / "stitch"
    for root in (execution, v2, review_package, stitch_root):
        root.mkdir(mode=0o700)
    candidates = execution / "CANDIDATES"
    candidates.mkdir(mode=0o700)
    candidate_artifacts = {
        role: _audio(
            candidates / f"{role}.wav",
            values,
            relative=f"{role}.wav",
        )
        for role, values in (
            ("vocals", vocals),
            ("instrumental", instrumental),
            ("reconstruction", reconstruction),
        )
    }
    source_claim = _audio(
        stitch_root / "SOURCE/source-44100.wav",
        source,
        relative="SOURCE/source-44100.wav",
    )
    original_roles = {
        "source": stitch_root / "SOURCE/source-44100.wav",
        "vocals": stitch_root / "STEMS/vocals.wav",
        "instrumental": stitch_root / "STEMS/instrumental.wav",
        "reconstruction": stitch_root / "STEMS/reconstruction.wav",
    }
    for role, values in (
        ("vocals", vocals),
        ("instrumental", instrumental),
        ("reconstruction", reconstruction),
    ):
        _audio(original_roles[role], values, relative=f"STEMS/{role}.wav")
    boundary_review = _write_boundary_review(
        stitch_root,
        title="Synthetic original",
        boundaries=[SAMPLE_RATE],
        role_paths=original_roles,
        soundfile=soundfile,
        np=np,
    )
    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": frames,
        "duration_seconds": 2.0,
        "chunk_count": 2,
        "boundary_count": 1,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    stitch = {
        "clock": clock,
        "artifacts": {"source": source_claim},
        "boundary_review": boundary_review,
        "document_sha256": "a" * 64,
    }
    stitch_path = _write(
        stitch_root / "private-separation-full-song-stitch.json", {"fixture": True}
    )
    snapshots = {}
    for name in ("execution", "candidate", "v2"):
        path = _write(tmp_path / f"{name}-snapshot/evidence.json", {"name": name})
        snapshots[name] = {
            "path": path,
            "sha256": _sha256(path),
            "document": {"name": name},
        }
    inputs = {
        "execution_snapshot": snapshots["execution"],
        "candidate_snapshot": snapshots["candidate"],
        "v2_snapshot": snapshots["v2"],
        "execution": {"document_sha256": "b" * 64, "clock": clock},
        "candidate": {
            "document_sha256": "c" * 64,
            "clock": clock,
            "artifacts": candidate_artifacts,
        },
        "v2": {"document_sha256": "d" * 64, "clock": clock},
        "candidate_paths": {
            role: candidates / f"{role}.wav" for role in candidate_artifacts
        },
    }
    result = {
        "document_sha256": "e" * 64,
        "bindings": {"review_export_sha256": "f" * 64},
    }
    result_path = _write(tmp_path / "resolved/result.json", result)
    reviewed = _write(tmp_path / "export/reviewed.json", {"reviewed": True})

    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._load_verified_inputs",
        lambda *args, **kwargs: inputs,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._verified_passing_targeted_result",
        lambda *args, **kwargs: result,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._load_stitch_report",
        lambda path: stitch,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._verify_stitch_audio",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._verify_stitch_bound_to_v2",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._reverify_inputs",
        lambda *args, **kwargs: None,
    )
    return {
        "execution": execution,
        "v2": v2,
        "review_package": review_package,
        "stitch": stitch_root,
        "stitch_path": stitch_path,
        "result_path": result_path,
        "reviewed": reviewed,
        "out": tmp_path / "full-review",
        "inputs": inputs,
    }


def _build(fixture: dict[str, object]) -> dict[str, object]:
    return _build_private_candidate_followup_full_song_review(
        fixture["result_path"],
        reviewed_export_path=fixture["reviewed"],
        targeted_review_package_dir=fixture["review_package"],
        execution_dir=fixture["execution"],
        v2_execution_dir=fixture["v2"],
        stitch_package_dir=fixture["stitch"],
        out_dir=fixture["out"],
    )


def test_builds_fresh_followup_full_song_and_all_boundary_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _builder_fixture(tmp_path, monkeypatch)
    result = _build(fixture)
    out = Path(fixture["out"])

    assert result["status"] == STATUS
    assert result["clock"]["boundary_count"] == 1
    assert result["readiness"]["followup_complete_song_review_complete"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert (out / REPORT_NAME).is_file()
    assert (out / "BOUNDARY-REVIEW/separation_boundary_review.html").is_file()
    assert len(list((out / "BOUNDARY-REVIEW/audio").glob("*.wav"))) == 4
    assert all((out / record["path"]).is_file() for record in result["artifacts"].values())


def test_gate_failure_or_existing_destination_never_claims_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _builder_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_review._verified_passing_targeted_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("did not pass")),
    )
    with pytest.raises(ValueError, match="did not pass"):
        _build(fixture)
    assert not Path(fixture["out"]).exists()

    Path(fixture["out"]).mkdir(mode=0o700)
    with pytest.raises(FileExistsError):
        _build(fixture)
    assert not (Path(fixture["out"]) / REPORT_NAME).exists()
