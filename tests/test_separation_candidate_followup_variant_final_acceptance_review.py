from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_final_acceptance_review import (
    REPORT_NAME,
    REVIEW_SCHEMA,
    STATUS,
    _build_private_candidate_followup_variant_final_acceptance_reviews,
)
from sunofriend._separation_candidate_followup_variant_full_song_review_result import (
    _resolve_private_candidate_followup_variant_full_song_reviews,
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
from tests.test_separation_candidate_followup_variant_readiness_reassessment import (
    _patch_passing_alignment,
    _reassess,
)


def test_builds_one_independent_final_acceptance_review_without_accepting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result, alignment, readiness = _pipeline(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    result = _build(
        fixture,
        reviews=reviews,
        review_result=review_result,
        alignment=alignment,
        readiness=readiness,
    )

    assert result["status"] == STATUS
    assert result["eligible_variant_ids"] == [VARIANTS[0]]
    assert result["required_review_count"] == 1
    assert result["readiness"]["separator_accepted"] is False
    assert result["readiness"]["variant_selected"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert result["effects"]["candidate_accepted"] is False
    assert result["interpretation"]["reviews_are_independent_not_comparative"]
    assert len(result["review_html"]) == 1

    output = Path(result["output_directory"])
    review = result["reviews"][0]
    seed = json.loads(
        (output / review["directory"] / review["seed"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    page = (output / review["directory"] / review["html"]["path"]).read_text(
        encoding="utf-8"
    )
    assert seed["schema"] == REVIEW_SCHEMA
    assert seed["status"] == "unreviewed"
    assert all(value is False for value in seed["heard"].values())
    assert all(value is None for value in seed["ratings"].values())
    assert seed["effects"]["candidate_accepted"] is False
    assert VARIANTS[0] not in page
    assert "independent, not a comparison or ranking" in page
    assert (output / REPORT_NAME).is_file()


def test_every_eligible_variant_is_included_in_canonical_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result, alignment, readiness = _pipeline(
        tmp_path, monkeypatch, eligible=list(VARIANTS)
    )
    result = _build(
        fixture,
        reviews=list(reversed(reviews)),
        review_result=review_result,
        alignment=alignment,
        readiness=readiness,
    )

    assert result["eligible_variant_ids"] == list(VARIANTS)
    assert [item["variant_id"] for item in result["reviews"]] == list(VARIANTS)
    assert [item["candidate_label"] for item in result["reviews"]] == [
        "Candidate 1 of 2",
        "Candidate 2 of 2",
    ]
    assert all(item["readiness"]["selected"] is False for item in result["reviews"])
    assert all(item["readiness"]["accepted"] is False for item in result["reviews"])


def test_zero_eligible_variants_create_no_acceptance_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result, alignment, readiness = _pipeline(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]], failed_boundary=True
    )
    with pytest.raises(ValueError, match="no variant is eligible"):
        _build(
            fixture,
            reviews=reviews,
            review_result=review_result,
            alignment=alignment,
            readiness=readiness,
        )
    assert not Path(fixture["acceptance_out"]).exists()


def test_changed_readiness_and_existing_destination_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result, alignment, readiness = _pipeline(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    changed = json.loads(readiness.read_text(encoding="utf-8"))
    changed["readiness"]["separator_accepted"] = True
    changed["document_sha256"] = _document_sha256(changed)
    _write(readiness, changed)
    with pytest.raises(ValueError, match="readiness reassessment differs"):
        _build(
            fixture,
            reviews=reviews,
            review_result=review_result,
            alignment=alignment,
            readiness=readiness,
        )
    assert not Path(fixture["acceptance_out"]).exists()

    fixture, reviews, review_result, alignment, readiness = _pipeline(
        tmp_path / "existing", monkeypatch, eligible=[VARIANTS[0]]
    )
    destination = Path(fixture["acceptance_out"])
    destination.mkdir(mode=0o700)
    marker = _write(destination / "existing.json", {"keep": True})
    with pytest.raises(FileExistsError):
        _build(
            fixture,
            reviews=reviews,
            review_result=review_result,
            alignment=alignment,
            readiness=readiness,
        )
    assert json.loads(marker.read_text(encoding="utf-8")) == {"keep": True}
    assert not (destination / REPORT_NAME).exists()


def _pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    eligible: list[str],
    failed_boundary: bool = False,
) -> tuple[dict[str, object], list[Path], Path, Path, Path]:
    _patch_passing_alignment(monkeypatch)
    if not failed_boundary:
        fixture, reviews, review_result = _resolved_fixture(
            tmp_path, monkeypatch, eligible=eligible
        )
    else:
        fixture, reviews = _completed_reviews(
            tmp_path, monkeypatch, eligible=eligible
        )
        changed = json.loads(reviews[0].read_text(encoding="utf-8"))
        changed["units"][0]["ratings"]["vocals"] = "audible_join"
        _write(reviews[0], changed)
        result_root = tmp_path / "full-song-result"
        result_root.mkdir(mode=0o700)
        review_result = result_root / "resolved.json"
        _resolve_private_candidate_followup_variant_full_song_reviews(
            reviews,
            out=review_result,
            **_arguments(fixture),
        )
        fixture["alignment_out"] = tmp_path / "alignments"
    measured = _measure(fixture, reviews=reviews, result=review_result)
    alignment = Path(measured["output_directory"])
    reassessed = _reassess(
        fixture,
        reviews=reviews,
        review_result=review_result,
        alignment_dir=alignment,
    )
    readiness = Path(reassessed["report"])
    acceptance_parent = tmp_path / "final-acceptance-parent"
    acceptance_parent.mkdir(mode=0o700)
    fixture["acceptance_out"] = acceptance_parent / "package"
    return fixture, reviews, review_result, alignment, readiness


def _build(
    fixture: dict[str, object],
    *,
    reviews: list[Path],
    review_result: Path,
    alignment: Path,
    readiness: Path,
) -> dict[str, object]:
    return _build_private_candidate_followup_variant_final_acceptance_reviews(
        readiness,
        full_song_review_result_path=review_result,
        alignment_package_dir=alignment,
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
        out_dir=fixture["acceptance_out"],
    )
