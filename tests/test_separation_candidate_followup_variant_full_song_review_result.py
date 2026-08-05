from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_full_song_review import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
)
from sunofriend._separation_candidate_followup_variant_full_song_review_result import (
    RESULT_STATUS,
    _resolve_private_candidate_followup_variant_full_song_reviews,
    _status_private_candidate_followup_variant_full_song_reviews,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from tests.test_separation_candidate_followup_variant_full_song_review import (
    VARIANTS,
    _build,
    _fixture,
    _write,
)


def test_status_and_resolution_require_every_variant_without_selecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(
        tmp_path, monkeypatch, eligible=list(VARIANTS)
    )
    arguments = _arguments(fixture)
    status = _status_private_candidate_followup_variant_full_song_reviews(
        list(reversed(reviews)), **arguments
    )

    assert status["status"] == "complete_review_set_verified_no_activation"
    assert status["reviewed_variant_ids"] == list(VARIANTS)
    assert status["reviewed_variant_count"] == 2
    assert status["required_review_count"] == 2
    assert status["automatic_winner_selected"] is False
    assert status["effects"]["review_record_created"] is False

    result_root = tmp_path / "full-song-result"
    result_root.mkdir(mode=0o700)
    result = _resolve_private_candidate_followup_variant_full_song_reviews(
        list(reversed(reviews)),
        out=result_root / "resolved.json",
        **arguments,
    )
    assert result["status"] == RESULT_STATUS
    assert result["reviewed_variant_ids"] == list(VARIANTS)
    assert [item["variant_id"] for item in result["variant_results"]] == list(
        VARIANTS
    )
    assert all(
        item["boundary_summary"]["all_boundaries_clean"]
        for item in result["variant_results"]
    )
    assert all(
        item["readiness_evidence"]["fresh_alignment_review_eligible"]
        for item in result["variant_results"]
    )
    assert all(
        item["readiness_evidence"]["selected"] is False
        for item in result["variant_results"]
    )
    assert result["readiness_evidence"]["variant_selected"] is False
    assert result["readiness_evidence"]["publication_ready"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS


def test_one_eligible_variant_produces_one_independent_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(tmp_path, monkeypatch, eligible=[VARIANTS[1]])
    status = _status_private_candidate_followup_variant_full_song_reviews(
        reviews, **_arguments(fixture)
    )

    assert status["reviewed_variant_ids"] == [VARIANTS[1]]
    assert status["reviewed_variant_count"] == 1
    assert status["reviewed_boundaries_per_variant"] == {VARIANTS[1]: 1}


def test_missing_duplicate_or_foreign_review_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(
        tmp_path, monkeypatch, eligible=list(VARIANTS)
    )
    arguments = _arguments(fixture)

    with pytest.raises(ValueError, match="complete eligible-variant review set"):
        _status_private_candidate_followup_variant_full_song_reviews(
            reviews[:1], **arguments
        )
    with pytest.raises(ValueError, match="duplicated"):
        _status_private_candidate_followup_variant_full_song_reviews(
            [reviews[0], reviews[0]], **arguments
        )

    foreign = json.loads(reviews[1].read_text(encoding="utf-8"))
    foreign["package_commitment"] = "f" * 64
    _write(reviews[1], foreign)
    with pytest.raises(ValueError, match="does not belong"):
        _status_private_candidate_followup_variant_full_song_reviews(
            reviews, **arguments
        )


def test_changed_immutable_review_or_boundary_audio_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(tmp_path, monkeypatch, eligible=[VARIANTS[0]])
    arguments = _arguments(fixture)
    changed = json.loads(reviews[0].read_text(encoding="utf-8"))
    changed["title"] = "changed"
    _write(reviews[0], changed)
    with pytest.raises(ValueError, match="immutable evidence"):
        _status_private_candidate_followup_variant_full_song_reviews(
            reviews, **arguments
        )

    fixture, reviews = _completed_reviews(
        tmp_path / "audio-change", monkeypatch, eligible=[VARIANTS[0]]
    )
    arguments = _arguments(fixture)
    report = json.loads(
        (Path(fixture["out"]) / PACKAGE_REPORT_NAME).read_text(encoding="utf-8")
    )
    review_root = Path(fixture["out"]) / report["variant_packages"][0]["directory"]
    audio = review_root / "BOUNDARY-REVIEW/audio/boundary-01-vocals.wav"
    with audio.open("r+b") as stream:
        stream.seek(-1, 2)
        value = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([value[0] ^ 1]))
    with pytest.raises(ValueError, match="audio"):
        _status_private_candidate_followup_variant_full_song_reviews(
            reviews, **arguments
        )


def test_self_hashed_parent_inventory_change_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(tmp_path, monkeypatch, eligible=[VARIANTS[0]])
    report_path = Path(fixture["out"]) / PACKAGE_REPORT_NAME
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["variant_packages"][0]["readiness"]["selected"] = True
    report["document_sha256"] = _document_sha256(report)
    _write(report_path, report)

    with pytest.raises(ValueError, match="inventory differs"):
        _status_private_candidate_followup_variant_full_song_reviews(
            reviews, **_arguments(fixture)
        )


def test_incomplete_review_and_existing_result_path_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(tmp_path, monkeypatch, eligible=[VARIANTS[0]])
    arguments = _arguments(fixture)
    incomplete = json.loads(reviews[0].read_text(encoding="utf-8"))
    incomplete["units"][0]["heard_all"] = False
    _write(reviews[0], incomplete)
    with pytest.raises(ValueError, match="incomplete"):
        _status_private_candidate_followup_variant_full_song_reviews(
            reviews, **arguments
        )

    fixture, reviews = _completed_reviews(
        tmp_path / "existing", monkeypatch, eligible=[VARIANTS[0]]
    )
    output_root = tmp_path / "existing-result"
    output_root.mkdir(mode=0o700)
    output = _write(output_root / "resolved.json", {"existing": True})
    with pytest.raises(FileExistsError):
        _resolve_private_candidate_followup_variant_full_song_reviews(
            reviews,
            out=output,
            **_arguments(fixture),
        )
    assert json.loads(output.read_text(encoding="utf-8")) == {"existing": True}


def test_evidence_change_after_result_write_removes_new_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews = _completed_reviews(tmp_path, monkeypatch, eligible=[VARIANTS[0]])
    module = (
        "sunofriend."
        "_separation_candidate_followup_variant_full_song_review_result"
    )
    import sunofriend._separation_candidate_followup_variant_full_song_review_result as subject

    original = subject._reverify_completed_reviews
    calls = 0

    def fail_after_publish(context: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("evidence changed after publication")
        original(context)

    monkeypatch.setattr(f"{module}._reverify_completed_reviews", fail_after_publish)
    output_root = tmp_path / "unstable-result"
    output_root.mkdir(mode=0o700)
    output = output_root / "resolved.json"
    with pytest.raises(ValueError, match="evidence changed"):
        _resolve_private_candidate_followup_variant_full_song_reviews(
            reviews,
            out=output,
            **_arguments(fixture),
        )
    assert not output.exists()


def _completed_reviews(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    eligible: list[str],
) -> tuple[dict[str, object], list[Path]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    fixture = _fixture(tmp_path, monkeypatch, eligible=eligible)
    result = _build(fixture)
    _patch_sources(fixture, monkeypatch)
    reviews = []
    for item in result["variant_packages"]:
        seed_path = (
            Path(fixture["out"])
            / item["directory"]
            / item["boundary_review"]["seed"]
        )
        review = json.loads(seed_path.read_text(encoding="utf-8"))
        review["status"] = "reviewed"
        review["full_song"]["heard_all"] = True
        review["full_song"]["ratings"] = {
            "vocals": "useful",
            "instrumental": "useful",
            "reconstruction": "useful",
        }
        review["full_song"]["notes"] = f"Reviewed {item['variant_id']}."
        for unit in review["units"]:
            unit["heard_all"] = True
            unit["ratings"] = {
                "vocals": "clean",
                "instrumental": "clean",
                "reconstruction": "clean",
            }
            unit["notes"] = "No audible join."
        review["summary"] = {
            "full_song_reviewed": True,
            "reviewed_boundaries": len(review["units"]),
            "boundary_count": len(review["units"]),
        }
        reviews.append(
            _write(
                tmp_path / f"exports/{item['variant_id']}.reviewed.json",
                review,
            )
        )
    return fixture, reviews


def _patch_sources(
    fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = (
        "sunofriend."
        "_separation_candidate_followup_variant_full_song_review_result"
    )
    monkeypatch.setattr(
        f"{prefix}._load_verified_variant_inputs",
        lambda *args, **kwargs: fixture["context"],
    )
    monkeypatch.setattr(
        f"{prefix}._verified_exact_variant_result",
        lambda *args, **kwargs: fixture["result"],
    )
    monkeypatch.setattr(
        f"{prefix}._load_stitch_report",
        lambda *args, **kwargs: fixture["stitch_document"],
    )
    monkeypatch.setattr(f"{prefix}._verify_stitch_audio", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        f"{prefix}._verify_stitch_bound_to_v2", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(f"{prefix}._reverify_inputs", lambda *args, **kwargs: None)


def _arguments(fixture: dict[str, object]) -> dict[str, object]:
    return {
        "review_package_dir": fixture["out"],
        "variant_review_result_path": fixture["result_path"],
        "variant_reviewed_export_path": fixture["reviewed_export"],
        "variant_review_package_dir": fixture["review_package"],
        "plan_path": fixture["plan_path"],
        "execution_dir": fixture["base_root"],
        "v2_execution_dir": fixture["v2_root"],
        "variant_execution_dir": fixture["variant_root"],
        "stitch_package_dir": fixture["stitch_root"],
    }
