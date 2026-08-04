from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    REPORT_NAME as REVIEW_NAME,
    _prepare_private_candidate_join_remediation_review,
)
from sunofriend._separation_candidate_join_remediation_review_result import (
    RESULT_SCHEMA,
    _resolve_private_candidate_join_remediation_review,
    _status_private_candidate_join_remediation_review,
)
from tests.test_separation_candidate_join_remediation_review import (
    _evidence,
    _read,
    _write,
)


def test_status_keeps_key_unopened_and_resolution_preserves_zero_activation(
    tmp_path: Path,
) -> None:
    execution, v2, review_root, reviewed = _completed_review(tmp_path)
    arguments = {
        "review_package_dir": review_root,
        "execution_dir": execution,
        "v2_execution_dir": v2,
    }

    status = _status_private_candidate_join_remediation_review(reviewed, **arguments)

    assert status["status"] == "complete_review_verified_key_unopened"
    assert status["reviewed_units"] == 6
    assert status["counts_by_kind"] == {
        "boundary_role_pair": 1,
        "patch_edge_pair": 2,
        "complete_song_pair": 3,
    }
    assert status["audio_references_verified"] == 12
    assert status["answer_key_opened"] is False
    assert status["identity_mapping_revealed"] is False
    assert status["verification_claims"]["answer_key_verified"] is False
    assert all(value is False for value in status["permissions"].values())
    assert all(value is False for value in status["effects"].values())

    result_path = tmp_path / "result" / "resolved.json"
    result = _resolve_private_candidate_join_remediation_review(
        reviewed, out=result_path, **arguments
    )

    assert result["schema"] == RESULT_SCHEMA
    assert result["status"] == "complete_review_no_activation"
    assert result["reviewed_unit_count"] == 6
    assert result["readiness_evidence"] == {
        "targeted_followup_review_complete": True,
        "all_targeted_boundaries_followup_preferred": True,
        "all_patch_edges_followup_or_equivalent": True,
        "all_complete_songs_followup_or_equivalent": True,
        "targeted_followup_listening_pass": True,
        "fresh_all_boundaries_review_eligible": True,
        "fresh_alignment_eligible": True,
        "followup_complete_song_review_complete": False,
        "followup_alignment_complete": False,
        "original_audible_joins_resolved": False,
        "publication_ready": False,
    }
    assert result_path.is_file()
    persisted = _read(result_path)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert all(
        unit["resolved_choice"] == "followup_candidate_preferred"
        for unit in result["units"]
    )


def test_status_rejects_incomplete_or_immutable_browser_changes(tmp_path: Path) -> None:
    execution, v2 = _evidence(tmp_path)
    review_root = tmp_path / "review"
    _prepare_private_candidate_join_remediation_review(
        execution, v2_execution_dir=v2, out_dir=review_root
    )
    arguments = {
        "review_package_dir": review_root,
        "execution_dir": execution,
        "v2_execution_dir": v2,
    }
    incomplete = tmp_path / "incomplete.json"
    _write(incomplete, _read(review_root / REVIEW_NAME))
    with pytest.raises(ValueError, match="incomplete"):
        _status_private_candidate_join_remediation_review(incomplete, **arguments)

    changed = deepcopy(_read(review_root / REVIEW_NAME))
    changed["question"] = "changed"
    changed["status"] = "reviewed"
    changed["summary"] = {
        "reviewed_units": len(changed["units"]),
        "total_units": len(changed["units"]),
        "complete": True,
    }
    for unit in changed["units"]:
        unit["heard"] = {"A": True, "B": True}
        unit["choice"] = "equivalent"
    changed_path = tmp_path / "changed.json"
    _write(changed_path, changed)
    with pytest.raises(ValueError, match="immutable evidence"):
        _status_private_candidate_join_remediation_review(changed_path, **arguments)


def test_resolution_refuses_existing_result(tmp_path: Path) -> None:
    execution, v2, review_root, reviewed = _completed_review(tmp_path)
    output = tmp_path / "result.json"
    output.write_text("keep\n", encoding="utf-8")
    output.chmod(0o600)

    with pytest.raises(FileExistsError):
        _resolve_private_candidate_join_remediation_review(
            reviewed,
            review_package_dir=review_root,
            execution_dir=execution,
            v2_execution_dir=v2,
            out=output,
        )
    assert output.read_text(encoding="utf-8") == "keep\n"


def _completed_review(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    execution, v2 = _evidence(tmp_path)
    review_root = tmp_path / "review"
    _prepare_private_candidate_join_remediation_review(
        execution, v2_execution_dir=v2, out_dir=review_root
    )
    review = _read(review_root / REVIEW_NAME)
    answer = _read(review_root / ANSWER_KEY_NAME)
    review["status"] = "reviewed"
    review["summary"] = {
        "reviewed_units": len(review["units"]),
        "total_units": len(review["units"]),
        "complete": True,
    }
    for unit, answer_unit in zip(review["units"], answer["units"]):
        unit["heard"] = {"A": True, "B": True}
        unit["choice"] = next(
            slot
            for slot, identity in answer_unit["assignment"].items()
            if identity == "followup_candidate"
        )
        unit["notes"] = ""
    reviewed = tmp_path / "reviewed.json"
    _write(reviewed, review)
    return execution, v2, review_root, reviewed
