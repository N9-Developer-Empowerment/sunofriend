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
from sunofriend._separation_candidate_followup_full_song_review_result import (
    RESULT_STATUS,
    _load_completed_review,
    _resolve_private_candidate_followup_full_song_review,
    _status_private_candidate_followup_full_song_review,
)
from sunofriend._separation_candidate_followup_full_song_alignment import (
    POLICY_ID as FOLLOWUP_ALIGNMENT_POLICY_ID,
    SCHEMA as FOLLOWUP_ALIGNMENT_SCHEMA,
    _measure_private_candidate_followup_full_song_alignment,
)
from sunofriend._separation_candidate_followup_readiness_reassessment import (
    STATUS as FOLLOWUP_REASSESSMENT_STATUS,
    _reassess_private_candidate_followup_readiness,
)
from sunofriend._separation_candidate_followup_remediation_plan import (
    CONTEXT_SHIFT_FRAMES,
    EXTENDED_EDGE_BLEND_FRAMES,
    REPORT_NAME as FOLLOWUP_PLAN_REPORT_NAME,
    _plan_private_candidate_followup_remediation,
    _window as followup_remediation_window,
)
from sunofriend._separation_candidate_join_remediation_review import ANSWER_KEY_NAME
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
    frames = SAMPLE_RATE * 6
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
        boundaries=[SAMPLE_RATE * 3],
        role_paths=original_roles,
        soundfile=soundfile,
        np=np,
    )
    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": frames,
        "duration_seconds": 6.0,
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
        "stitch_document": stitch,
        "targeted_result": result,
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


def _completed_full_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], Path]:
    fixture = _builder_fixture(tmp_path, monkeypatch)
    _build(fixture)
    _patch_result_sources(fixture, monkeypatch)
    seed = json.loads(
        (Path(fixture["out"]) / "BOUNDARY-REVIEW/separation_boundary_review.json").read_text(
            encoding="utf-8"
        )
    )
    seed["status"] = "reviewed"
    seed["full_song"]["heard_all"] = True
    seed["full_song"]["ratings"] = {
        "vocals": "useful",
        "instrumental": "useful",
        "reconstruction": "useful",
    }
    seed["full_song"]["notes"] = "Useful complete fixture."
    for unit in seed["units"]:
        unit["heard_all"] = True
        unit["ratings"] = {
            "vocals": "clean",
            "instrumental": "clean",
            "reconstruction": "clean",
        }
        unit["notes"] = "No audible join."
    seed["summary"] = {
        "full_song_reviewed": True,
        "reviewed_boundaries": len(seed["units"]),
        "boundary_count": len(seed["units"]),
    }
    reviewed = _write(tmp_path / "full-export/reviewed.json", seed)
    return fixture, reviewed


def _patch_result_sources(
    fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = (
        "sunofriend._separation_candidate_followup_full_song_review_result"
    )
    monkeypatch.setattr(
        f"{prefix}._load_verified_inputs",
        lambda *args, **kwargs: fixture["inputs"],
    )
    monkeypatch.setattr(
        f"{prefix}._verified_passing_targeted_result",
        lambda *args, **kwargs: fixture["targeted_result"],
    )
    monkeypatch.setattr(
        f"{prefix}._load_stitch_report",
        lambda *args, **kwargs: fixture["stitch_document"],
    )
    monkeypatch.setattr(
        f"{prefix}._verify_stitch_audio", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        f"{prefix}._verify_stitch_bound_to_v2", lambda *args, **kwargs: None
    )


def _result_args(fixture: dict[str, object]) -> dict[str, object]:
    return {
        "review_package_dir": fixture["out"],
        "targeted_review_result_path": fixture["result_path"],
        "targeted_reviewed_export_path": fixture["reviewed"],
        "targeted_review_package_dir": fixture["review_package"],
        "execution_dir": fixture["execution"],
        "v2_execution_dir": fixture["v2"],
        "stitch_package_dir": fixture["stitch"],
    }


def test_status_and_resolution_record_complete_review_without_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviewed = _completed_full_review(tmp_path, monkeypatch)
    arguments = _result_args(fixture)
    status = _status_private_candidate_followup_full_song_review(
        reviewed, **arguments
    )

    assert status["status"] == "complete_review_verified_no_activation"
    assert status["reviewed_boundaries"] == 1
    assert status["rating_counts_by_role"]["vocals"]["clean"] == 1
    assert status["effects"]["review_record_created"] is False

    result_root = tmp_path / "full-result"
    result_root.mkdir(mode=0o700)
    result = _resolve_private_candidate_followup_full_song_review(
        reviewed,
        out=result_root / "result.json",
        **arguments,
    )
    assert result["status"] == RESULT_STATUS
    assert result["boundary_summary"]["all_followup_boundaries_clean"] is True
    assert result["readiness_evidence"]["all_followup_full_song_roles_useful"] is True
    assert result["readiness_evidence"]["followup_alignment_complete"] is False
    assert result["readiness_evidence"]["publication_ready"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS


def test_resolver_rejects_incomplete_export_and_changed_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviewed = _completed_full_review(tmp_path, monkeypatch)
    arguments = _result_args(fixture)
    document = json.loads(reviewed.read_text(encoding="utf-8"))
    document["units"][0]["heard_all"] = False
    _write(reviewed, document)
    with pytest.raises(ValueError, match="incomplete"):
        _status_private_candidate_followup_full_song_review(reviewed, **arguments)

    document["units"][0]["heard_all"] = True
    _write(reviewed, document)
    audio = Path(fixture["out"]) / "STEMS/vocals.wav"
    with audio.open("r+b") as stream:
        stream.seek(-1, 2)
        value = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([value[0] ^ 1]))
    with pytest.raises(ValueError, match="audio"):
        _status_private_candidate_followup_full_song_review(reviewed, **arguments)


def _alignment_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], Path, Path, dict[str, object]]:
    fixture, reviewed = _completed_full_review(tmp_path, monkeypatch)
    arguments = _result_args(fixture)
    context = _load_completed_review(reviewed, **arguments)
    result_root = tmp_path / "full-result"
    result_root.mkdir(mode=0o700)
    result_path = result_root / "result.json"
    _resolve_private_candidate_followup_full_song_review(
        reviewed,
        out=result_path,
        **arguments,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_full_song_alignment._load_completed_review",
        lambda *args, **kwargs: context,
    )
    return fixture, reviewed, result_path, context


def _alignment_args(
    fixture: dict[str, object], reviewed: Path, *, out: Path
) -> dict[str, object]:
    return {
        "full_song_review_export_path": reviewed,
        "full_song_review_package_dir": fixture["out"],
        "targeted_review_result_path": fixture["result_path"],
        "targeted_reviewed_export_path": fixture["reviewed"],
        "targeted_review_package_dir": fixture["review_package"],
        "execution_dir": fixture["execution"],
        "v2_execution_dir": fixture["v2"],
        "stitch_package_dir": fixture["stitch"],
        "out": out,
    }


def test_measures_fresh_followup_alignment_only_after_exact_full_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviewed, result_path, _ = _alignment_fixture(tmp_path, monkeypatch)
    output_root = tmp_path / "alignment-result"
    output_root.mkdir(mode=0o700)
    output = output_root / "alignment.json"
    result = _measure_private_candidate_followup_full_song_alignment(
        result_path,
        **_alignment_args(fixture, reviewed, out=output),
    )

    assert result["schema"] == FOLLOWUP_ALIGNMENT_SCHEMA
    assert result["policy_id"] == FOLLOWUP_ALIGNMENT_POLICY_ID
    assert len(result["windows"]) == 9
    assert result["readiness_evidence"]["followup_alignment_complete"] is True
    assert isinstance(result["readiness_evidence"]["alignment_gate_passed"], bool)
    assert result["readiness_evidence"]["original_audible_joins_resolved"] is False
    assert result["readiness_evidence"]["publication_ready"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert output.is_file()


def test_alignment_rejects_a_self_hashed_but_changed_full_review_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviewed, result_path, _ = _alignment_fixture(tmp_path, monkeypatch)
    changed = json.loads(result_path.read_text(encoding="utf-8"))
    changed["readiness_evidence"]["publication_ready"] = True
    changed["document_sha256"] = _document_sha256(changed)
    _write(result_path, changed)
    output_root = tmp_path / "alignment-result"
    output_root.mkdir(mode=0o700)
    output = output_root / "alignment.json"

    with pytest.raises(ValueError, match="review result differs"):
        _measure_private_candidate_followup_full_song_alignment(
            result_path,
            **_alignment_args(fixture, reviewed, out=output),
        )
    assert not output.exists()


def _readiness_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], Path, Path, Path, dict[str, object]]:
    fixture, reviewed, review_result, context = _alignment_fixture(
        tmp_path, monkeypatch
    )
    alignment_root = tmp_path / "alignment-result"
    alignment_root.mkdir(mode=0o700)
    alignment_path = alignment_root / "alignment.json"
    alignment = _measure_private_candidate_followup_full_song_alignment(
        review_result,
        **_alignment_args(fixture, reviewed, out=alignment_path),
    )
    return fixture, reviewed, review_result, alignment_path, alignment


def _readiness_args(
    fixture: dict[str, object],
    reviewed: Path,
    alignment_path: Path,
    *,
    out: Path,
) -> dict[str, object]:
    return {
        "alignment_result_path": alignment_path,
        "full_song_review_export_path": reviewed,
        "full_song_review_package_dir": fixture["out"],
        "targeted_review_result_path": fixture["result_path"],
        "targeted_reviewed_export_path": fixture["reviewed"],
        "targeted_review_package_dir": fixture["review_package"],
        "execution_dir": fixture["execution"],
        "v2_execution_dir": fixture["v2"],
        "stitch_package_dir": fixture["stitch"],
        "out": out,
    }


def test_reassessment_retains_failed_alignment_as_non_activating_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviewed, review_result, alignment_path, _ = _readiness_fixture(
        tmp_path, monkeypatch
    )
    result_root = tmp_path / "readiness-result"
    result_root.mkdir(mode=0o700)
    result = _reassess_private_candidate_followup_readiness(
        review_result,
        **_readiness_args(
            fixture,
            reviewed,
            alignment_path,
            out=result_root / "result.json",
        ),
    )

    assert result["status"] == FOLLOWUP_REASSESSMENT_STATUS
    assert result["evidence"]["followup_alignment_complete"] is True
    assert result["evidence"]["followup_alignment_gate_passed"] is False
    assert result["readiness"]["final_human_acceptance_review_eligible"] is False
    assert result["readiness"]["separator_accepted"] is False
    assert result["next_action"] == "remediate_failed_followup_candidate_evidence"
    assert result["permissions"] == _FALSE_PERMISSIONS


def test_reassessment_can_only_make_final_human_review_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviewed, review_result, alignment_path, alignment = _readiness_fixture(
        tmp_path, monkeypatch
    )
    positive = {key: value for key, value in alignment.items() if key != "report"}
    for key in (
        "source_to_reconstruction_alignment_verified",
        "drift_acceptance_complete",
        "alignment_gate_passed",
    ):
        positive["readiness_evidence"][key] = True
    positive["document_sha256"] = _document_sha256(positive)
    _write(alignment_path, positive)
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_readiness_reassessment._measure_private_candidate_followup_full_song_alignment",
        lambda *args, **kwargs: {**positive, "report": str(kwargs["out"])},
    )
    result_root = tmp_path / "readiness-result"
    result_root.mkdir(mode=0o700)
    result = _reassess_private_candidate_followup_readiness(
        review_result,
        **_readiness_args(
            fixture,
            reviewed,
            alignment_path,
            out=result_root / "result.json",
        ),
    )

    assert result["evidence"]["technical_and_listening_prerequisites_met"] is True
    assert result["readiness"]["final_human_acceptance_review_eligible"] is True
    assert result["readiness"]["final_human_acceptance_review_complete"] is False
    assert result["readiness"]["separator_selected"] is False
    assert result["readiness"]["publication_ready"] is False
    assert result["next_action"] == "run_explicit_final_followup_candidate_acceptance_review"


def _failed_targeted_review(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    execution, v2, review_root, reviewed = _completed_review(tmp_path)
    review = json.loads(reviewed.read_text(encoding="utf-8"))
    answer = json.loads((review_root / ANSWER_KEY_NAME).read_text(encoding="utf-8"))
    for unit, answer_unit in zip(review["units"], answer["units"]):
        if unit["kind"] == "boundary_role_pair":
            unit["choice"] = next(
                slot
                for slot, identity in answer_unit["assignment"].items()
                if identity == "v2_control"
            )
        elif unit["kind"] == "patch_edge_pair" and unit["unit_id"].endswith(
            "-start"
        ):
            unit["choice"] = "neither"
        else:
            unit["choice"] = "equivalent"
    _write(reviewed, review)
    result_root = tmp_path / "failed-result"
    result_path = result_root / "resolved.json"
    _resolve_private_candidate_join_remediation_review(
        reviewed,
        review_package_dir=review_root,
        execution_dir=execution,
        v2_execution_dir=v2,
        out=result_path,
    )
    return execution, v2, review_root, reviewed, result_path


def test_failed_targeted_review_produces_only_a_bounded_model_free_plan(
    tmp_path: Path,
) -> None:
    execution, v2, review_root, reviewed, result_path = _failed_targeted_review(
        tmp_path
    )
    plan_root = tmp_path / "plan"
    output = plan_root / FOLLOWUP_PLAN_REPORT_NAME
    plan = _plan_private_candidate_followup_remediation(
        result_path,
        reviewed_export_path=reviewed,
        targeted_review_package_dir=review_root,
        execution_dir=execution,
        v2_execution_dir=v2,
        out=output,
    )

    assert plan["summary"]["remediation_role_boundary_count"] == 1
    assert plan["summary"]["action_counts"] == {
        "revert_patch_to_v2_control": 1
    }
    assert plan["summary"]["planned_model_call_count"] == 0
    assert plan["summary"]["candidate_variant_count"] == 2
    assert plan["protocol"]["reinference_context_shift_frames"] == 88_200
    assert plan["protocol"]["candidate_variants"][1][
        "failed_edge_blend_frames"
    ] == EXTENDED_EDGE_BLEND_FRAMES
    assert plan["readiness"]["remediation_execution_complete"] is False
    assert plan["effects"]["model_run"] is False
    assert plan["permissions"] == _FALSE_PERMISSIONS
    assert output.is_file()
    assert plan_root.stat().st_mode & 0o077 == 0


def test_model_window_uses_new_later_context_instead_of_repeating_worker() -> None:
    patch = {
        "patch_start_frame": 400_000,
        "patch_end_frame": 576_400,
        "edge_blend_frames": 4_410,
    }
    window = followup_remediation_window(
        3,
        actions={
            "vocals": {
                "action": "reinfer_role_boundary",
                "model_call_required": True,
                "boundary_outcome": "equivalent",
                "failed_edges": [],
            }
        },
        patches={(3, "vocals"): patch},
        total_frames=2_000_000,
        window_index=1,
    )

    assert window["actual_context_shift_frames"] == CONTEXT_SHIFT_FRAMES
    assert window["source_start_frame"] == (
        window["unshifted_source_start_frame"] + CONTEXT_SHIFT_FRAMES
    )
    assert window["source_end_frame"] - window["source_start_frame"] == 661_500


def test_passing_targeted_review_refuses_a_remediation_plan(tmp_path: Path) -> None:
    execution, v2, review_root, reviewed = _completed_review(tmp_path)
    result_root = tmp_path / "passing-result"
    result_path = result_root / "resolved.json"
    _resolve_private_candidate_join_remediation_review(
        reviewed,
        review_package_dir=review_root,
        execution_dir=execution,
        v2_execution_dir=v2,
        out=result_path,
    )
    plan_root = tmp_path / "plan"
    plan_root.mkdir(mode=0o700)
    output = plan_root / FOLLOWUP_PLAN_REPORT_NAME
    with pytest.raises(ValueError, match="needs no remediation"):
        _plan_private_candidate_followup_remediation(
            result_path,
            reviewed_export_path=reviewed,
            targeted_review_package_dir=review_root,
            execution_dir=execution,
            v2_execution_dir=v2,
            out=output,
        )
    assert not output.exists()
