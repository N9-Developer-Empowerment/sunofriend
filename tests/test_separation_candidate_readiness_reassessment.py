from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_full_song_alignment import (
    POLICY_ID as ALIGNMENT_POLICY_ID,
    SCHEMA as ALIGNMENT_SCHEMA,
    STATUS as ALIGNMENT_STATUS,
    _FALSE_EFFECTS as ALIGNMENT_FALSE_EFFECTS,
)
from sunofriend._separation_candidate_full_song_review_result import (
    RESULT_SCHEMA as REVIEW_SCHEMA,
    RESULT_STATUS as REVIEW_STATUS,
    _RESULT_EFFECTS as REVIEW_EFFECTS,
)
from sunofriend._separation_candidate_readiness_reassessment import (
    SCHEMA,
    STATUS,
    _reassess_private_candidate_readiness,
)
from sunofriend._separation_full_song_alignment import (
    FEATURE_FRAME_MILLISECONDS,
    FEATURE_HOP_MILLISECONDS,
    MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
    MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
    MAXIMUM_SEARCH_LAG_MILLISECONDS,
    MAXIMUM_WINDOW_SECONDS,
    MINIMUM_ACCEPTED_WINDOW_CORRELATION,
    MINIMUM_ACTIVE_RMS_DBFS,
    WINDOW_COUNT,
    _song_third,
    _window_start_frames,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _json(path: Path, document: dict[str, object]) -> Path:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    return path


def _sha(character: str) -> str:
    return character * 64


def _snapshot(
    tmp_path: Path, name: str, document: dict[str, object]
) -> dict[str, object]:
    root = _private_dir(tmp_path / name)
    path = _json(root / f"{name}.json", document)
    return {"path": path, "sha256": _sha256(path), "document": document}


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    tmp_path.chmod(0o700)
    clock = {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 120 * 44_100,
        "duration_seconds": 120.0,
        "chunk_count": 3,
        "boundary_count": 2,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    v1_root = _private_dir(tmp_path / "v1")
    v2_root = _private_dir(tmp_path / "v2")
    stitch_root = _private_dir(tmp_path / "stitch")
    v2_report = {"document_sha256": _sha("2")}
    stitch = {"document_sha256": _sha("3"), "clock": clock}
    v2_snapshot = _snapshot(tmp_path, "v2-execution", v2_report)
    v2_plan_snapshot = _snapshot(tmp_path, "v2-plan", {"document_sha256": _sha("4")})
    stitch_snapshot = _snapshot(tmp_path, "stitch-report", stitch)
    v1_execution_snapshot = _snapshot(
        tmp_path, "v1-execution", {"state_sha256": _sha("5")}
    )
    v1_candidate_snapshot = _snapshot(
        tmp_path, "v1-candidate", {"document_sha256": _sha("6")}
    )
    authority_paths = tuple(
        _snapshot(tmp_path, f"authority-{index}", {"index": index})["path"]
        for index in range(4)
    )
    context = {
        "v1_root": v1_root,
        "v2_root": v2_root,
        "stitch_root": stitch_root,
        "v2_snapshot": v2_snapshot,
        "v2_report": v2_report,
        "v2_plan_snapshot": v2_plan_snapshot,
        "stitch_snapshot": stitch_snapshot,
        "stitch": stitch,
        "v1_execution_snapshot": v1_execution_snapshot,
        "v1_candidate_snapshot": v1_candidate_snapshot,
        "authority_paths": authority_paths,
    }
    monkeypatch.setattr(
        "sunofriend._separation_candidate_readiness_reassessment._load_review_inputs",
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_readiness_reassessment._verify_passing_v2_review_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_readiness_reassessment._require_review_result_unchanged",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_readiness_reassessment._reverify_inputs",
        lambda *args, **kwargs: None,
    )

    v2_result = {
        "schema": "fixture.v2",
        "status": "complete",
    }
    v2_result["document_sha256"] = _document_sha256(v2_result)
    v2_result_snapshot = _snapshot(tmp_path, "v2-review-result", v2_result)

    boundaries = [
        {
            "boundary_index": index,
            "frame": frame,
            "seconds": frame / clock["sample_rate"],
            "ratings": {
                role: "clean" for role in ("vocals", "instrumental", "reconstruction")
            },
            "notes": "No audible join.",
        }
        for index, frame in enumerate((44_100, 88_200), start=1)
    ]
    roles = ("vocals", "instrumental", "reconstruction")
    counts = {role: {"audible_join": 0, "cannot_tell": 0, "clean": 2} for role in roles}
    review_bindings = {
        "candidate_review_package_report_sha256": _sha("7"),
        "candidate_review_package_document_sha256": _sha("8"),
        "candidate_review_seed_sha256": _sha("9"),
        "candidate_review_export_sha256": _sha("a"),
        "candidate_review_package_commitment": _sha("b"),
        "v2_review_result_sha256": v2_result_snapshot["sha256"],
        "v2_review_result_document_sha256": v2_result["document_sha256"],
        "v2_execution_report_sha256": v2_snapshot["sha256"],
        "v2_execution_document_sha256": v2_report["document_sha256"],
    }
    review = {
        "schema": REVIEW_SCHEMA,
        "status": REVIEW_STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": "v2_expanded_context_join_remediation",
        "bindings": review_bindings,
        "clock": clock,
        "full_song": {
            "heard_all": True,
            "ratings": {role: "useful" for role in roles},
            "notes": "All three roles are useful.",
        },
        "boundary_summary": {
            "reviewed_boundaries": 2,
            "rating_counts_by_role": counts,
            "audible_join_boundaries_by_role": {role: [] for role in roles},
            "all_candidate_boundaries_clean": True,
        },
        "boundaries": boundaries,
        "readiness_evidence": {
            "targeted_v2_absolute_cleanliness_pass": True,
            "new_candidate_full_song_review_complete": True,
            "all_candidate_boundaries_clean": True,
            "all_candidate_full_song_roles_useful": True,
            "fresh_candidate_bound_alignment_review_eligible": True,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "full_song_review_completion_is_candidate_acceptance": False,
            "clean_boundaries_are_separator_accuracy": False,
            "alignment_still_requires_fresh_review": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(REVIEW_EFFECTS),
    }
    review["document_sha256"] = _document_sha256(review)
    review_snapshot = _snapshot(tmp_path, "candidate-review-result", review)

    window_seconds = min(MAXIMUM_WINDOW_SECONDS, clock["duration_seconds"] / 12.0)
    window_frames = round(window_seconds * clock["sample_rate"])
    starts = _window_start_frames(
        total_frames=clock["frames"], window_frames=window_frames
    )
    windows = [
        {
            "window_index": index,
            "song_third": _song_third(index),
            "start_frame": start,
            "end_frame": start + window_frames,
            "start_seconds": round(start / clock["sample_rate"], 6),
            "end_seconds": round((start + window_frames) / clock["sample_rate"], 6),
            "source_rms_dbfs": -20.0,
            "reconstruction_rms_dbfs": -21.0,
            "eligible": True,
            "best_lag_milliseconds": 0.0,
            "peak_normalized_correlation": 0.99,
        }
        for index, start in enumerate(starts, start=1)
    ]
    alignment = {
        "schema": ALIGNMENT_SCHEMA,
        "status": ALIGNMENT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": ALIGNMENT_POLICY_ID,
        "candidate_identity": "v2_expanded_context_join_remediation",
        "bindings": {
            "v2_review_result_sha256": v2_result_snapshot["sha256"],
            "v2_review_result_document_sha256": v2_result["document_sha256"],
            "v2_execution_report_sha256": v2_snapshot["sha256"],
            "v2_execution_document_sha256": v2_report["document_sha256"],
            "stitch_report_sha256": stitch_snapshot["sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": _sha("c"),
            "source_pcm24_int32_sequence_sha256": _sha("d"),
            "reconstruction_audio_sha256": _sha("e"),
            "reconstruction_pcm24_int32_sequence_sha256": _sha("f"),
        },
        "clock": clock,
        "protocol": {
            "comparison": "canonical source versus diagnostic reconstruction",
            "feature": "log spectral-band energy",
            "window_count": WINDOW_COUNT,
            "window_seconds": round(window_frames / clock["sample_rate"], 6),
            "feature_frame_milliseconds": FEATURE_FRAME_MILLISECONDS,
            "feature_hop_milliseconds": FEATURE_HOP_MILLISECONDS,
            "maximum_search_lag_milliseconds": MAXIMUM_SEARCH_LAG_MILLISECONDS,
            "lag_sign": "positive means reconstruction is later than source",
            "source_and_reconstruction_gain_normalized_for_timing": True,
        },
        "thresholds": {
            "minimum_active_rms_dbfs": MINIMUM_ACTIVE_RMS_DBFS,
            "minimum_eligible_window_count": WINDOW_COUNT,
            "all_song_thirds_required": True,
            "maximum_absolute_lag_milliseconds": MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
            "maximum_lag_spread_milliseconds": MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
            "minimum_window_normalized_correlation": MINIMUM_ACCEPTED_WINDOW_CORRELATION,
        },
        "windows": windows,
        "summary": {
            "eligible_window_count": WINDOW_COUNT,
            "maximum_absolute_lag_milliseconds": 0.0,
            "lag_spread_milliseconds": 0.0,
            "minimum_window_normalized_correlation": 0.99,
            "early_middle_late_coverage_complete": True,
        },
        "readiness_evidence": {
            "targeted_v2_absolute_cleanliness_pass": True,
            "new_candidate_alignment_complete": True,
            "source_to_reconstruction_alignment_verified": True,
            "drift_acceptance_complete": True,
            "alignment_gate_passed": True,
            "new_candidate_full_song_review_complete": False,
            "original_audible_joins_resolved": False,
            "separator_accuracy_established": False,
            "publication_ready": False,
        },
        "interpretation": {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(ALIGNMENT_FALSE_EFFECTS),
        "limitations": [
            "This report measures only the exact v2 source-to-reconstruction clock and drift.",
            "The earlier candidate's alignment result is not inherited.",
            "A synchronized reconstruction can still contain bleed, omissions or artefacts.",
            "Fresh candidate-bound full-song and boundary listening remains separate evidence.",
        ],
    }
    alignment["document_sha256"] = _document_sha256(alignment)
    alignment_snapshot = _snapshot(tmp_path, "candidate-alignment-result", alignment)
    out_root = _private_dir(tmp_path / "reassessment")
    return {
        "context": context,
        "v2": v2_result_snapshot,
        "review": review_snapshot,
        "alignment": alignment_snapshot,
        "out": out_root / "result.json",
    }


def _args(fixture: dict[str, object]) -> dict[str, object]:
    tmp = Path(fixture["out"]).parent.parent
    return {
        "candidate_review_result_path": fixture["review"]["path"],
        "candidate_alignment_result_path": fixture["alignment"]["path"],
        "v2_execution_dir": tmp / "unused-v2",
        "v2_plan_path": tmp / "unused-v2-plan.json",
        "v1_execution_dir": tmp / "unused-v1",
        "stitch_package_dir": tmp / "unused-stitch",
        "full_song_review_result_path": tmp / "unused-review.json",
        "v1_plan_path": tmp / "unused-v1-plan.json",
        "resolved_join_review_result_path": tmp / "unused-join.json",
        "publication_readiness_path": tmp / "unused-readiness.json",
        "out": fixture["out"],
    }


def test_reassessment_requires_final_human_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = _reassess_private_candidate_readiness(
        fixture["v2"]["path"], **_args(fixture)
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == STATUS
    assert result["evidence"]["technical_and_listening_prerequisites_met"] is True
    assert result["readiness"]["final_human_acceptance_review_eligible"] is True
    assert result["readiness"]["final_human_acceptance_review_complete"] is False
    assert result["readiness"]["original_audible_joins_resolved"] is False
    assert result["readiness"]["separator_accepted"] is False
    assert result["readiness"]["publication_ready"] is False
    assert Path(fixture["out"]).is_file()


def test_reassessment_rejects_recomputed_false_review_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    review_path = fixture["review"]["path"]
    review = json.loads(review_path.read_text())
    review["readiness_evidence"]["all_candidate_boundaries_clean"] = False
    review["document_sha256"] = _document_sha256(review)
    _json(review_path, review)

    with pytest.raises(ValueError, match="review claims differ"):
        _reassess_private_candidate_readiness(fixture["v2"]["path"], **_args(fixture))
    assert not Path(fixture["out"]).exists()


def test_reassessment_records_failed_alignment_without_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    alignment_path = fixture["alignment"]["path"]
    alignment = json.loads(alignment_path.read_text())
    alignment["windows"][0]["best_lag_milliseconds"] = 30.0
    alignment["summary"] = {
        "eligible_window_count": WINDOW_COUNT,
        "maximum_absolute_lag_milliseconds": 30.0,
        "lag_spread_milliseconds": 30.0,
        "minimum_window_normalized_correlation": 0.99,
        "early_middle_late_coverage_complete": True,
    }
    for key in (
        "source_to_reconstruction_alignment_verified",
        "drift_acceptance_complete",
        "alignment_gate_passed",
    ):
        alignment["readiness_evidence"][key] = False
    alignment["document_sha256"] = _document_sha256(alignment)
    _json(alignment_path, alignment)

    result = _reassess_private_candidate_readiness(
        fixture["v2"]["path"], **_args(fixture)
    )
    assert result["evidence"]["candidate_alignment_gate_passed"] is False
    assert result["readiness"]["final_human_acceptance_review_eligible"] is False
    assert result["next_action"] == "remediate_failed_candidate_evidence"
    assert result["readiness"]["separator_accepted"] is False


def test_reassessment_rejects_wrong_v2_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    alignment_path = fixture["alignment"]["path"]
    alignment = json.loads(alignment_path.read_text())
    alignment["bindings"]["v2_review_result_sha256"] = _sha("0")
    alignment["document_sha256"] = _document_sha256(alignment)
    _json(alignment_path, alignment)

    with pytest.raises(ValueError, match="alignment bindings differ"):
        _reassess_private_candidate_readiness(fixture["v2"]["path"], **_args(fixture))
    assert not Path(fixture["out"]).exists()


def test_reassessment_refuses_output_inside_input_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    unsafe = fixture["context"]["v2_root"] / "result.json"
    args = _args(fixture)
    args["out"] = unsafe
    with pytest.raises(ValueError, match="outside input evidence roots"):
        _reassess_private_candidate_readiness(fixture["v2"]["path"], **args)
    assert not unsafe.exists()
