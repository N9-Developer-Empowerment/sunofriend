from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_final_acceptance_review import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
)
from sunofriend._separation_candidate_followup_variant_final_acceptance_review_result import (
    RESULT_STATUS,
    _resolve_private_candidate_followup_variant_final_acceptance_reviews,
    _status_private_candidate_followup_variant_final_acceptance_reviews,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from tests.test_separation_candidate_followup_variant_final_acceptance_review import (
    _build,
    _pipeline,
)
from tests.test_separation_candidate_followup_variant_full_song_review import (
    VARIANTS,
    _write,
)


def test_status_and_resolution_preserve_independent_acceptance_without_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=list(VARIANTS),
        decisions=("accept", "needs_more_work"),
    )
    status = _status_private_candidate_followup_variant_final_acceptance_reviews(
        list(reversed(reviews)), **arguments
    )

    assert status["status"] == "complete_review_set_verified_no_activation"
    assert status["reviewed_variant_ids"] == list(VARIANTS)
    assert status["reviewed_variant_count"] == 2
    assert status["required_review_count"] == 2
    assert status["answer_interpretation_performed"] is False
    assert status["automatic_winner_selected"] is False
    assert status["effects"]["acceptance_record_created"] is False

    result_root = tmp_path / "acceptance-result"
    result_root.mkdir(mode=0o700)
    result = _resolve_private_candidate_followup_variant_final_acceptance_reviews(
        list(reversed(reviews)),
        out=result_root / "resolved.json",
        **arguments,
    )
    assert result["status"] == RESULT_STATUS
    assert result["reviewed_variant_ids"] == list(VARIANTS)
    assert [item["variant_id"] for item in result["variant_results"]] == list(
        VARIANTS
    )
    assert result["variant_results"][0]["decision_evidence"] == {
        "accepted_for_private_pilot": True,
        "negative_answer_ids": [],
        "uncertain_answer_ids": [],
        "all_required_answers_affirmative": True,
    }
    assert result["variant_results"][1]["decision_evidence"] == {
        "accepted_for_private_pilot": False,
        "negative_answer_ids": ["candidate_suitable_for_private_pilot"],
        "uncertain_answer_ids": [],
        "all_required_answers_affirmative": False,
    }
    assert result["private_pilot_acceptance"]["accepted_variant_ids"] == [
        VARIANTS[0]
    ]
    assert result["private_pilot_acceptance"]["variant_selected"] is False
    assert (
        result["private_pilot_acceptance"]["separator_accepted_as_product_default"]
        is False
    )
    assert result["private_pilot_acceptance"]["product_route_enabled"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert result["effects"]["candidate_accepted_for_private_pilot"] is True


def test_one_uncertain_review_remains_complete_but_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[1]],
        decisions=("cannot_tell",),
    )
    result_root = tmp_path / "uncertain-result"
    result_root.mkdir(mode=0o700)
    result = _resolve_private_candidate_followup_variant_final_acceptance_reviews(
        reviews,
        out=result_root / "resolved.json",
        **arguments,
    )

    evidence = result["variant_results"][0]["decision_evidence"]
    assert evidence["accepted_for_private_pilot"] is False
    assert evidence["uncertain_answer_ids"] == [
        "vocals_useful_for_melody_workflow",
        "instrumental_useful_for_midi_workflow",
        "reconstruction_continuous_and_synchronised",
        "candidate_suitable_for_private_pilot",
    ]
    assert result["private_pilot_acceptance"]["accepted_variant_ids"] == []
    assert result["next_action"] == "return_to_bounded_remediation"
    assert result["effects"]["candidate_accepted_for_private_pilot"] is False


def test_missing_duplicate_or_foreign_export_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=list(VARIANTS),
        decisions=("accept", "accept"),
    )
    with pytest.raises(ValueError, match="complete final acceptance review set"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews[:1], **arguments
        )
    with pytest.raises(ValueError, match="duplicated"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            [reviews[0], reviews[0]], **arguments
        )

    foreign = json.loads(reviews[1].read_text(encoding="utf-8"))
    foreign["package_commitment"] = "f" * 64
    _write(reviews[1], foreign)
    with pytest.raises(ValueError, match="does not belong"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, **arguments
        )


def test_changed_immutable_incomplete_or_nonprivate_export_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    changed = json.loads(reviews[0].read_text(encoding="utf-8"))
    changed["candidate_label"] = "Changed"
    _write(reviews[0], changed)
    with pytest.raises(ValueError, match="immutable evidence"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, **arguments
        )

    _, reviews, arguments = _completed_acceptance_reviews(
        tmp_path / "incomplete",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    incomplete = json.loads(reviews[0].read_text(encoding="utf-8"))
    incomplete["heard"]["vocals"] = False
    _write(reviews[0], incomplete)
    with pytest.raises(ValueError, match="incomplete"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, **arguments
        )

    _, reviews, arguments = _completed_acceptance_reviews(
        tmp_path / "permissions",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    reviews[0].chmod(0o644)
    with pytest.raises(ValueError, match="group or other"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, **arguments
        )
    reviews[0].chmod(0o600)
    linked = reviews[0].with_name("linked.reviewed.json")
    linked.symlink_to(reviews[0])
    with pytest.raises(ValueError, match="regular non-link"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            [linked], **arguments
        )
    oversized = reviews[0].with_name("oversized.reviewed.json")
    with oversized.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    oversized.chmod(0o600)
    with pytest.raises(ValueError, match="no larger than 8 MiB"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            [oversized], **arguments
        )


def test_package_audio_or_self_hashed_inventory_change_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    report = json.loads(
        (Path(fixture["acceptance_out"]) / PACKAGE_REPORT_NAME).read_text(
            encoding="utf-8"
        )
    )
    audio = (
        Path(fixture["acceptance_out"])
        / report["reviews"][0]["directory"]
        / "audio/vocals.wav"
    )
    with audio.open("r+b") as stream:
        stream.seek(-1, 2)
        value = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([value[0] ^ 1]))
    with pytest.raises(ValueError, match="audio"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, **arguments
        )

    fixture, reviews, arguments = _completed_acceptance_reviews(
        tmp_path / "inventory",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    report_path = Path(fixture["acceptance_out"]) / PACKAGE_REPORT_NAME
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["reviews"][0]["readiness"]["selected"] = True
    report["document_sha256"] = _document_sha256(report)
    _write(report_path, report)
    with pytest.raises(ValueError, match="package differs"):
        _status_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, **arguments
        )


def test_existing_result_and_post_write_evidence_change_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    output_root = tmp_path / "existing-result"
    output_root.mkdir(mode=0o700)
    output = _write(output_root / "resolved.json", {"keep": True})
    with pytest.raises(FileExistsError):
        _resolve_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, out=output, **arguments
        )
    assert json.loads(output.read_text(encoding="utf-8")) == {"keep": True}

    fixture, reviews, arguments = _completed_acceptance_reviews(
        tmp_path / "unstable",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    import sunofriend._separation_candidate_followup_variant_final_acceptance_review_result as subject

    original = subject._reverify_completed_reviews
    calls = 0

    def fail_after_publish(context: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("evidence changed after publication")
        original(context)

    monkeypatch.setattr(subject, "_reverify_completed_reviews", fail_after_publish)
    result_root = tmp_path / "unstable-result"
    result_root.mkdir(mode=0o700)
    result_path = result_root / "resolved.json"
    with pytest.raises(ValueError, match="evidence changed"):
        _resolve_private_candidate_followup_variant_final_acceptance_reviews(
            reviews, out=result_path, **arguments
        )
    assert not result_path.exists()
    assert Path(fixture["acceptance_out"]).is_dir()


def _completed_acceptance_reviews(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    eligible: list[str],
    decisions: tuple[str, ...],
) -> tuple[dict[str, object], list[Path], dict[str, object]]:
    if len(decisions) != len(eligible):
        raise ValueError("one decision is required per eligible variant")
    fixture, full_song_reviews, review_result, alignment, readiness = _pipeline(
        tmp_path, monkeypatch, eligible=eligible
    )
    package = _build(
        fixture,
        reviews=full_song_reviews,
        review_result=review_result,
        alignment=alignment,
        readiness=readiness,
    )
    exports: list[Path] = []
    for item, decision in zip(package["reviews"], decisions):
        seed_path = (
            Path(fixture["acceptance_out"])
            / item["directory"]
            / item["seed"]["path"]
        )
        review = json.loads(seed_path.read_text(encoding="utf-8"))
        review["status"] = "reviewed"
        review["heard"] = {
            "source": True,
            "vocals": True,
            "instrumental": True,
            "reconstruction": True,
        }
        if decision == "accept":
            review["ratings"] = {
                "vocals_useful_for_melody_workflow": "yes",
                "instrumental_useful_for_midi_workflow": "yes",
                "reconstruction_continuous_and_synchronised": "yes",
                "candidate_suitable_for_private_pilot": "accept_private_pilot",
            }
        elif decision == "needs_more_work":
            review["ratings"] = {
                "vocals_useful_for_melody_workflow": "yes",
                "instrumental_useful_for_midi_workflow": "yes",
                "reconstruction_continuous_and_synchronised": "yes",
                "candidate_suitable_for_private_pilot": "needs_more_work",
            }
        elif decision == "cannot_tell":
            review["ratings"] = {
                "vocals_useful_for_melody_workflow": "cannot_tell",
                "instrumental_useful_for_midi_workflow": "cannot_tell",
                "reconstruction_continuous_and_synchronised": "cannot_tell",
                "candidate_suitable_for_private_pilot": "cannot_tell",
            }
        else:
            raise ValueError("unknown acceptance decision")
        review["notes"] = f"Explicit {decision} review."
        review["summary"] = {"complete": True, "answered_questions": 4}
        exports.append(
            _write(
                tmp_path / f"acceptance-exports/{item['review_id']}.reviewed.json",
                review,
            )
        )
    arguments: dict[str, object] = {
        "review_package_dir": fixture["acceptance_out"],
        "readiness_result_path": readiness,
        "full_song_review_result_path": review_result,
        "alignment_package_dir": alignment,
        "full_song_review_export_paths": full_song_reviews,
        "full_song_review_package_dir": fixture["out"],
        "variant_review_result_path": fixture["result_path"],
        "variant_reviewed_export_path": fixture["reviewed_export"],
        "variant_review_package_dir": fixture["review_package"],
        "plan_path": fixture["plan_path"],
        "execution_dir": fixture["base_root"],
        "v2_execution_dir": fixture["v2_root"],
        "variant_execution_dir": fixture["variant_root"],
        "stitch_package_dir": fixture["stitch_root"],
    }
    return fixture, exports, arguments
