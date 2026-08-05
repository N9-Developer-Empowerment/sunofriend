from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_full_song_review_result import (
    _resolve_private_candidate_followup_variant_full_song_reviews,
)
from sunofriend._separation_candidate_followup_variant_readiness_reassessment import (
    STATUS,
    _reassess_private_candidate_followup_variant_readiness,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from tests.test_separation_candidate_followup_variant_full_song_alignment import (
    _measure,
    _resolved_fixture,
)
from tests.test_separation_candidate_followup_variant_full_song_review import (
    VARIANTS,
    _write,
)
from tests.test_separation_candidate_followup_variant_full_song_review_result import (
    _arguments,
    _completed_reviews,
)


def test_reassesses_every_variant_without_ranking_or_selecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_passing_alignment(monkeypatch)
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=list(VARIANTS)
    )
    alignment = _measure(
        fixture, reviews=list(reversed(reviews)), result=review_result
    )
    readiness = _reassess(
        fixture,
        reviews=list(reversed(reviews)),
        review_result=review_result,
        alignment_dir=Path(alignment["output_directory"]),
    )

    assert readiness["status"] == STATUS
    assert readiness["reviewed_variant_ids"] == list(VARIANTS)
    assert [item["variant_id"] for item in readiness["variant_evidence"]] == list(
        VARIANTS
    )
    assert readiness["readiness"][
        "final_human_acceptance_review_eligible_variant_ids"
    ] == list(VARIANTS)
    assert readiness["readiness"][
        "final_human_acceptance_review_eligible_variant_count"
    ] == 2
    assert readiness["readiness"]["variant_selected"] is False
    assert readiness["readiness"]["separator_accepted"] is False
    assert readiness["interpretation"]["automatic_winner_selected"] is False
    assert readiness["interpretation"]["multiple_variants_may_remain_eligible"] is True
    assert readiness["permissions"] == _FALSE_PERMISSIONS
    assert all(item["readiness"]["selected"] is False for item in readiness["variant_evidence"])


def test_failed_human_prerequisite_is_preserved_without_losing_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_passing_alignment(monkeypatch)
    fixture, reviews = _completed_reviews(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    changed = json.loads(reviews[0].read_text(encoding="utf-8"))
    changed["units"][0]["ratings"]["vocals"] = "audible_join"
    _write(reviews[0], changed)
    result_root = tmp_path / "full-song-result"
    result_root.mkdir(mode=0o700)
    review_result = result_root / "resolved.json"
    _resolve_private_candidate_followup_variant_full_song_reviews(
        reviews, out=review_result, **_arguments(fixture)
    )
    fixture["alignment_out"] = tmp_path / "alignments"
    alignment = _measure(fixture, reviews=reviews, result=review_result)
    readiness = _reassess(
        fixture,
        reviews=reviews,
        review_result=review_result,
        alignment_dir=Path(alignment["output_directory"]),
    )

    evidence = readiness["variant_evidence"][0]
    assert evidence["variant_id"] == VARIANTS[0]
    assert evidence["evidence"]["all_original_boundaries_clean"] is False
    assert evidence["evidence"]["alignment_gate_passed"] is True
    assert evidence["evidence"]["technical_and_listening_prerequisites_met"] is False
    assert readiness["readiness"][
        "final_human_acceptance_review_eligible_variant_ids"
    ] == []
    assert readiness["next_action"] == "remediate_failed_variant_evidence"


def test_changed_alignment_package_and_existing_output_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    alignment = _measure(fixture, reviews=reviews, result=review_result)
    alignment_root = Path(alignment["output_directory"])
    parent_path = Path(alignment["report"])
    changed = json.loads(parent_path.read_text(encoding="utf-8"))
    changed["readiness_evidence"]["variant_selected"] = True
    changed["document_sha256"] = _document_sha256(changed)
    _write(parent_path, changed)
    with pytest.raises(ValueError, match="alignment package differs"):
        _reassess(
            fixture,
            reviews=reviews,
            review_result=review_result,
            alignment_dir=alignment_root,
        )
    assert not Path(fixture["readiness_out"]).exists()

    existing = Path(fixture["readiness_out"])
    existing.parent.mkdir(mode=0o700, exist_ok=True)
    _write(existing, {"keep": True})
    with pytest.raises(FileExistsError):
        _reassess(
            fixture,
            reviews=reviews,
            review_result=review_result,
            alignment_dir=alignment_root,
        )
    assert json.loads(existing.read_text(encoding="utf-8")) == {"keep": True}


def test_post_publish_evidence_change_removes_readiness_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    alignment = _measure(fixture, reviews=reviews, result=review_result)
    module = (
        "sunofriend."
        "_separation_candidate_followup_variant_readiness_reassessment"
    )
    import sunofriend._separation_candidate_followup_variant_readiness_reassessment as subject

    original = subject._derive_alignment_package
    calls = 0

    def fail_after_publish(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("evidence changed after publication")
        return original(*args, **kwargs)

    monkeypatch.setattr(f"{module}._derive_alignment_package", fail_after_publish)
    with pytest.raises(ValueError, match="evidence changed"):
        _reassess(
            fixture,
            reviews=reviews,
            review_result=review_result,
            alignment_dir=Path(alignment["output_directory"]),
        )
    assert not Path(fixture["readiness_out"]).exists()


def _reassess(
    fixture: dict[str, object],
    *,
    reviews: list[Path],
    review_result: Path,
    alignment_dir: Path,
) -> dict[str, object]:
    output_root = Path(fixture["out"]).parent / "readiness-result"
    output_root.mkdir(mode=0o700, exist_ok=True)
    output = output_root / "result.json"
    fixture["readiness_out"] = output
    return _reassess_private_candidate_followup_variant_readiness(
        review_result,
        alignment_package_dir=alignment_dir,
        full_song_review_export_paths=reviews,
        full_song_review_package_dir=fixture["out"],
        variant_review_result_path=fixture["result_path"],
        variant_reviewed_export_path=fixture["reviewed_export"],
        variant_review_package_dir=fixture["review_package"],
        plan_path=fixture["plan_path"],
        execution_dir=fixture["base_root"],
        v2_execution_dir=fixture["v2_root"],
        variant_execution_dir=fixture["variant_root"],
        stitch_package_dir=fixture["stitch_root"],
        out=output,
    )


def _patch_passing_alignment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_alignment._measure_alignment_observation",
        lambda *args, **kwargs: {
            "protocol": {"comparison": "test source versus reconstruction"},
            "thresholds": {"test_gate": True},
            "windows": [],
            "summary": {"eligible_window_count": 9},
            "gate_passed": True,
        },
    )
