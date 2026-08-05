from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_full_song_alignment import (
    REPORT_NAME,
    STATUS,
    VARIANT_REPORT_NAME,
    _measure_private_candidate_followup_variant_full_song_alignments,
)
from sunofriend._separation_candidate_followup_variant_full_song_review_result import (
    _resolve_private_candidate_followup_variant_full_song_reviews,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from tests.test_separation_candidate_followup_variant_full_song_review import (
    VARIANTS,
    _write,
)
from tests.test_separation_candidate_followup_variant_full_song_review_result import (
    _arguments,
    _completed_reviews,
)


def test_aligns_every_reviewed_variant_in_canonical_order_without_selecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=list(VARIANTS)
    )
    alignment = _measure(fixture, reviews=list(reversed(reviews)), result=review_result)

    assert alignment["status"] == STATUS
    assert alignment["reviewed_variant_ids"] == list(VARIANTS)
    assert alignment["aligned_variant_ids"] == list(VARIANTS)
    assert alignment["aligned_variant_count"] == 2
    assert [item["variant_id"] for item in alignment["variant_alignments"]] == list(
        VARIANTS
    )
    assert all(item["selected"] is False for item in alignment["variant_alignments"])
    assert all(item["accepted"] is False for item in alignment["variant_alignments"])
    assert alignment["interpretation"]["automatic_winner_selected"] is False
    assert alignment["readiness_evidence"]["variant_selected"] is False
    assert alignment["permissions"] == _FALSE_PERMISSIONS
    assert (Path(fixture["alignment_out"]) / REPORT_NAME).is_file()
    for index, item in enumerate(alignment["variant_alignments"], start=1):
        child = Path(fixture["alignment_out"]) / item["report"]
        assert child == (
            Path(fixture["alignment_out"])
            / f"variant-{index:02d}"
            / VARIANT_REPORT_NAME
        )
        document = json.loads(child.read_text(encoding="utf-8"))
        assert document["variant_id"] == item["variant_id"]
        assert document["readiness_evidence"]["selected"] is False
        assert document["readiness_evidence"]["accepted"] is False


def test_one_reviewed_variant_produces_one_independent_alignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=[VARIANTS[1]]
    )
    alignment = _measure(fixture, reviews=reviews, result=review_result)

    assert alignment["aligned_variant_ids"] == [VARIANTS[1]]
    assert alignment["aligned_variant_count"] == 1
    assert len(alignment["variant_reports"]) == 1


def test_missing_review_or_changed_resolved_result_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=list(VARIANTS)
    )
    with pytest.raises(ValueError, match="complete eligible-variant review set"):
        _measure(fixture, reviews=reviews[:1], result=review_result)
    assert not Path(fixture["alignment_out"]).exists()

    changed = json.loads(review_result.read_text(encoding="utf-8"))
    changed["readiness_evidence"]["variant_selected"] = True
    changed["document_sha256"] = _document_sha256(changed)
    _write(review_result, changed)
    with pytest.raises(ValueError, match="review result differs"):
        _measure(fixture, reviews=reviews, result=review_result)
    assert not Path(fixture["alignment_out"]).exists()


def test_existing_destination_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    destination = Path(fixture["alignment_out"])
    destination.mkdir(mode=0o700)
    marker = _write(destination / "existing.json", {"keep": True})

    with pytest.raises(FileExistsError):
        _measure(fixture, reviews=reviews, result=review_result)
    assert json.loads(marker.read_text(encoding="utf-8")) == {"keep": True}
    assert not (destination / REPORT_NAME).exists()


def test_post_publish_evidence_change_removes_alignment_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, review_result = _resolved_fixture(
        tmp_path, monkeypatch, eligible=[VARIANTS[0]]
    )
    module = (
        "sunofriend."
        "_separation_candidate_followup_variant_full_song_alignment"
    )
    import sunofriend._separation_candidate_followup_variant_full_song_alignment as subject

    original = subject._reverify_alignment_inputs
    calls = 0

    def fail_after_publish(**kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("evidence changed after publication")
        original(**kwargs)

    monkeypatch.setattr(f"{module}._reverify_alignment_inputs", fail_after_publish)
    with pytest.raises(ValueError, match="evidence changed"):
        _measure(fixture, reviews=reviews, result=review_result)
    assert not Path(fixture["alignment_out"]).exists()


def _resolved_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    eligible: list[str],
) -> tuple[dict[str, object], list[Path], Path]:
    fixture, reviews = _completed_reviews(tmp_path, monkeypatch, eligible=eligible)
    result_root = tmp_path / "full-song-result"
    result_root.mkdir(mode=0o700)
    result_path = result_root / "resolved.json"
    _resolve_private_candidate_followup_variant_full_song_reviews(
        reviews,
        out=result_path,
        **_arguments(fixture),
    )
    fixture["alignment_out"] = tmp_path / "alignments"
    return fixture, reviews, result_path


def _measure(
    fixture: dict[str, object], *, reviews: list[Path], result: Path
) -> dict[str, object]:
    return _measure_private_candidate_followup_variant_full_song_alignments(
        result,
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
        out_dir=fixture["alignment_out"],
    )
