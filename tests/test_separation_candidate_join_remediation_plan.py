from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_join_remediation_plan import (
    REPORT_NAME,
    SCHEMA,
    STATUS,
    _plan_private_candidate_join_remediation,
)
from sunofriend._separation_candidate_readiness_reassessment import (
    _reassess_private_candidate_readiness,
)
from tests.test_separation_candidate_readiness_reassessment import (
    _args as _reassessment_args,
    _fixture as _reassessment_fixture,
    _json,
)


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    audible_reconstruction: bool = False,
) -> dict[str, object]:
    fixture = _reassessment_fixture(tmp_path, monkeypatch)
    review_path = Path(fixture["review"]["path"])
    review = json.loads(review_path.read_text(encoding="utf-8"))
    for boundary, frame in zip(
        review["boundaries"], (10 * 44_100, 30 * 44_100)
    ):
        boundary["frame"] = frame
        boundary["seconds"] = frame / 44_100
    review["boundaries"][0]["ratings"]["vocals"] = "audible_join"
    review["boundaries"][1]["ratings"]["instrumental"] = "audible_join"
    audible = {
        "vocals": [1],
        "instrumental": [2],
        "reconstruction": [],
    }
    if audible_reconstruction:
        review["boundaries"][0]["ratings"]["reconstruction"] = "audible_join"
        audible["reconstruction"] = [1]
    for role, boundaries in audible.items():
        review["boundary_summary"]["rating_counts_by_role"][role] = {
            "audible_join": len(boundaries),
            "cannot_tell": 0,
            "clean": 2 - len(boundaries),
        }
    review["boundary_summary"]["audible_join_boundaries_by_role"] = audible
    review["boundary_summary"]["all_candidate_boundaries_clean"] = False
    review["readiness_evidence"]["all_candidate_boundaries_clean"] = False
    review["document_sha256"] = _document_sha256(review)
    _json(review_path, review)
    fixture["review"]["document"] = review

    reassessment = _reassess_private_candidate_readiness(
        fixture["v2"]["path"], **_reassessment_args(fixture)
    )
    context = fixture["context"]
    context["stitch"]["artifacts"] = {"source": {"sha256": "1" * 64}}
    context["v2_report"]["artifacts"] = {
        role: {"sha256": character * 64}
        for role, character in (
            ("vocals", "2"),
            ("instrumental", "3"),
            ("reconstruction", "4"),
        )
    }
    context["v2_plan"] = {
        "windows": [
            {
                "boundary_index": 11,
                "patch_target_role": "vocals",
            },
            {
                "boundary_index": 13,
                "patch_target_role": "instrumental",
            },
        ]
    }
    monkeypatch.setattr(
        "sunofriend._separation_candidate_join_remediation_plan._load_review_inputs",
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_join_remediation_plan._verify_passing_v2_review_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_join_remediation_plan._verify_candidate_review_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_join_remediation_plan._verify_candidate_alignment_result",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_join_remediation_plan._reverify_all",
        lambda *args, **kwargs: None,
    )
    fixture["reassessment"] = reassessment
    fixture["reassessment_path"] = fixture["out"]
    return fixture


def _args(fixture: dict[str, object], output: Path) -> dict[str, object]:
    tmp = output.parent.parent
    return {
        "candidate_review_result_path": fixture["review"]["path"],
        "candidate_alignment_result_path": fixture["alignment"]["path"],
        "readiness_reassessment_path": fixture["reassessment_path"],
        "v2_execution_dir": tmp / "unused-v2",
        "v2_plan_path": tmp / "unused-v2-plan.json",
        "v1_execution_dir": tmp / "unused-v1",
        "stitch_package_dir": tmp / "unused-stitch",
        "full_song_review_result_path": tmp / "unused-review.json",
        "v1_plan_path": tmp / "unused-v1-plan.json",
        "resolved_join_review_result_path": tmp / "unused-join.json",
        "publication_readiness_path": tmp / "unused-readiness.json",
        "out": output,
    }


def test_plan_derives_only_explicit_audible_role_joins_without_running_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "followup-plan" / REPORT_NAME

    result = _plan_private_candidate_join_remediation(
        fixture["v2"]["path"], **_args(fixture, output)
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == STATUS
    assert result["summary"] == {
        "human_rated_audible_role_join_count": 2,
        "unique_boundary_count": 2,
        "planned_model_call_count": 2,
        "target_roles": ["vocals", "instrumental"],
        "outside_prior_v2_target_role_join_count": 2,
        "private_listener_notes_copied": False,
        "v2_candidate_control_count": 1,
        "new_candidate_count": 0,
    }
    assert {
        (window["boundary_index"], tuple(window["patch_target_roles"]))
        for window in result["windows"]
    } == {(1, ("vocals",)), (2, ("instrumental",))}
    assert result["readiness"]["targeted_remediation_plan_ready"] is True
    assert result["readiness"]["new_candidate_created"] is False
    assert result["effects"]["model_run"] is False
    assert all(value is False for value in result["permissions"].values())
    assert output.is_file()
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == _document_sha256(persisted)


def test_plan_rejects_audible_reconstruction_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, audible_reconstruction=True)
    output = tmp_path / "followup-plan" / REPORT_NAME

    with pytest.raises(ValueError, match="reconstruction joins require diagnosis"):
        _plan_private_candidate_join_remediation(
            fixture["v2"]["path"], **_args(fixture, output)
        )
    assert not output.exists()


def test_plan_rejects_reassessment_that_claims_acceptance_is_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    reassessment_path = Path(fixture["reassessment_path"])
    reassessment = json.loads(reassessment_path.read_text(encoding="utf-8"))
    reassessment["readiness"]["final_human_acceptance_review_eligible"] = True
    reassessment["document_sha256"] = _document_sha256(reassessment)
    _json(reassessment_path, reassessment)
    output = tmp_path / "followup-plan" / REPORT_NAME

    with pytest.raises(ValueError, match="failed candidate readiness evidence"):
        _plan_private_candidate_join_remediation(
            fixture["v2"]["path"], **_args(fixture, output)
        )
    assert not output.exists()


def test_plan_refuses_output_inside_input_evidence_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    output = fixture["context"]["v2_root"] / REPORT_NAME

    with pytest.raises(ValueError, match="outside input evidence roots"):
        _plan_private_candidate_join_remediation(
            fixture["v2"]["path"], **_args(fixture, output)
        )
    assert not output.exists()
