from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_final_acceptance_review_result import (
    _resolve_private_candidate_followup_variant_final_acceptance_reviews,
)
from sunofriend._separation_candidate_followup_variant_final_readiness_reassessment import (
    STATUS,
    _reassess_private_candidate_followup_variant_final_readiness,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from tests.test_separation_candidate_followup_variant_final_acceptance_review_result import (
    _completed_acceptance_reviews,
)
from tests.test_separation_candidate_followup_variant_full_song_review import (
    VARIANTS,
    _write,
)


def test_reassesses_one_accepted_candidate_without_selecting_or_activating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path,
        monkeypatch,
        eligible=list(VARIANTS),
        decisions=("accept", "needs_more_work"),
    )
    result = _reassess(
        tmp_path,
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )

    assert result["status"] == STATUS
    assert result["reviewed_variant_ids"] == list(VARIANTS)
    assert result["private_pilot_readiness"] == {
        "reassessment_complete": True,
        "ready_variant_ids": [VARIANTS[0]],
        "ready_variant_count": 1,
        "not_ready_variant_ids": [VARIANTS[1]],
        "not_ready_variant_count": 1,
        "zero_one_or_multiple_ready_variants_allowed": True,
        "bounded_private_pilot_available": True,
        "variant_selected": False,
        "separator_accepted_as_product_default": False,
        "original_audible_joins_resolved": False,
        "product_route_enabled": False,
        "publication_ready": False,
    }
    assert (
        result["variant_evidence"][0]["readiness"]["bounded_private_pilot_ready"]
        is True
    )
    assert result["variant_evidence"][1]["evidence"]["negative_answer_ids"] == [
        "candidate_suitable_for_private_pilot"
    ]
    assert result["next_action"] == (
        "prepare_bounded_private_pilot_without_product_activation"
    )
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert result["effects"]["candidate_selected"] is False
    assert (
        result["publication_boundary"]["current_global_gate_status_recomputed"] is False
    )
    assert (
        len(result["publication_boundary"]["unresolved_or_separately_evidenced_items"])
        == 7
    )
    assert Path(result["report"]).is_file()
    assert Path(result["report"]).stat().st_mode & 0o077 == 0
    assert Path(fixture["acceptance_out"]).is_dir()


def test_zero_or_multiple_private_pilot_candidates_remain_valid_without_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path / "zero",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("cannot_tell",),
    )
    zero = _reassess(
        tmp_path / "zero",
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    assert zero["private_pilot_readiness"]["ready_variant_ids"] == []
    assert zero["private_pilot_readiness"]["bounded_private_pilot_available"] is False
    assert zero["next_action"] == "return_to_bounded_remediation"
    assert zero["variant_evidence"][0]["evidence"]["uncertain_answer_ids"] == [
        "vocals_useful_for_melody_workflow",
        "instrumental_useful_for_midi_workflow",
        "reconstruction_continuous_and_synchronised",
        "candidate_suitable_for_private_pilot",
    ]

    _, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path / "multiple",
        monkeypatch,
        eligible=list(VARIANTS),
        decisions=("accept", "accept"),
    )
    multiple = _reassess(
        tmp_path / "multiple",
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    assert multiple["private_pilot_readiness"]["ready_variant_ids"] == list(VARIANTS)
    assert multiple["private_pilot_readiness"]["variant_selected"] is False
    assert multiple["interpretation"]["automatic_winner_selected"] is False


def test_changed_acceptance_result_existing_output_and_nested_output_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    changed = json.loads(acceptance.read_text(encoding="utf-8"))
    changed["private_pilot_acceptance"]["variant_selected"] = True
    changed["document_sha256"] = _document_sha256(changed)
    _write(acceptance, changed)
    output_root = tmp_path / "changed-output"
    output_root.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="acceptance review result differs"):
        _reassess_private_candidate_followup_variant_final_readiness(
            acceptance,
            final_acceptance_review_export_paths=reviews,
            out=output_root / "result.json",
            **arguments,
        )

    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path / "existing",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    existing_root = tmp_path / "existing-output"
    existing_root.mkdir(mode=0o700)
    existing = _write(existing_root / "result.json", {"keep": True})
    with pytest.raises(FileExistsError):
        _reassess_private_candidate_followup_variant_final_readiness(
            acceptance,
            final_acceptance_review_export_paths=reviews,
            out=existing,
            **arguments,
        )
    assert json.loads(existing.read_text(encoding="utf-8")) == {"keep": True}

    nested = Path(fixture["acceptance_out"]) / "nested-result.json"
    with pytest.raises(ValueError, match="outside input evidence roots"):
        _reassess_private_candidate_followup_variant_final_readiness(
            acceptance,
            final_acceptance_review_export_paths=reviews,
            out=nested,
            **arguments,
        )
    assert not nested.exists()


def test_post_publish_evidence_change_removes_readiness_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    import sunofriend._separation_candidate_followup_variant_final_readiness_reassessment as subject

    original = subject._derive_final_acceptance_result
    calls = 0

    def fail_after_publish(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("evidence changed after publication")
        return original(*args, **kwargs)

    monkeypatch.setattr(subject, "_derive_final_acceptance_result", fail_after_publish)
    output_root = tmp_path / "unstable-output"
    output_root.mkdir(mode=0o700)
    output = output_root / "result.json"
    with pytest.raises(ValueError, match="evidence changed"):
        _reassess_private_candidate_followup_variant_final_readiness(
            acceptance,
            final_acceptance_review_export_paths=reviews,
            out=output,
            **arguments,
        )
    assert not output.exists()


def _resolved_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    eligible: list[str],
    decisions: tuple[str, ...],
) -> tuple[dict[str, object], list[Path], dict[str, object], Path]:
    fixture, reviews, arguments = _completed_acceptance_reviews(
        tmp_path,
        monkeypatch,
        eligible=eligible,
        decisions=decisions,
    )
    result_root = tmp_path / "acceptance-result"
    result_root.mkdir(mode=0o700, exist_ok=True)
    result = result_root / "resolved.json"
    _resolve_private_candidate_followup_variant_final_acceptance_reviews(
        reviews,
        out=result,
        **arguments,
    )
    return fixture, reviews, arguments, result


def _reassess(
    tmp_path: Path,
    *,
    acceptance: Path,
    reviews: list[Path],
    arguments: dict[str, object],
) -> dict[str, object]:
    output_root = tmp_path / "final-readiness"
    output_root.mkdir(mode=0o700, exist_ok=True)
    return _reassess_private_candidate_followup_variant_final_readiness(
        acceptance,
        final_acceptance_review_export_paths=reviews,
        out=output_root / "result.json",
        **arguments,
    )
