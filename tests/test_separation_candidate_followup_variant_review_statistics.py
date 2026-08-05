from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_candidate_followup_variant_review_statistics import (
    REPORT_NAME,
    SCHEMA,
    _analyze_private_candidate_followup_variant_review,
    _fisher_exact_two_sided,
    _proportion_statistics,
)


def test_real_shape_statistics_do_not_claim_normal_quality_or_change_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _resolved_result()
    result_path = _private_json(tmp_path / "resolved.json", result)
    reviewed = _private_json(tmp_path / "reviewed.json", {"reviewed": True})
    package = tmp_path / "package"
    base = tmp_path / "base"
    v2 = tmp_path / "v2"
    variants = tmp_path / "variants"
    for directory in (package, base, v2, variants):
        directory.mkdir(mode=0o700)
    plan = tmp_path / "plan.json"
    plan.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_review_statistics._verified_exact_variant_result",
        lambda *args, **kwargs: deepcopy(result),
    )
    destination = tmp_path / "statistics" / REPORT_NAME
    report = _analyze_private_candidate_followup_variant_review(
        result_path,
        reviewed_export_path=reviewed,
        variant_review_package_dir=package,
        plan_path=plan,
        execution_dir=base,
        v2_execution_dir=v2,
        variant_execution_dir=variants,
        out=destination,
    )

    assert report["schema"] == SCHEMA
    assert report["groups"]["overall"]["unit_count"] == 36
    edge = report["patch_edge_neither_concentration"]
    assert edge["observed"] == [[9, 11], [0, 16]]
    assert edge["risk_difference"] == pytest.approx(0.45)
    assert edge["fisher_exact_two_sided_p_value"] < 0.01
    assert edge["contrast_pre_specified_before_review"] is False
    assert edge["p_value_is_exploratory"] is True
    contingency = report["outcome_by_unit_kind"]
    assert contingency["column_order"] == [
        "equivalent",
        "followup_control_preferred",
        "neither",
    ]
    assert (
        contingency["asymptotic_reliability"]["use_asymptotic_p_value_for_decision"]
        is False
    )
    assert contingency["exact_conditional_permutation"]["monte_carlo"] is False
    assert (
        report["assumptions_and_boundaries"]["raw_review_choices_assumed_normal"]
        is False
    )
    assert report["assumptions_and_boundaries"]["quality_confidence_level"] is None
    assert report["interpretation"]["review_gate_changed"] is False
    assert all(value is False for value in report["permissions"].values())
    assert all(value is False for value in report["effects"].values())
    persisted = json.loads(destination.read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == _document_sha256(persisted)


def test_proportion_statistics_use_wilson_not_raw_normal_distribution() -> None:
    zero = _proportion_statistics(0, n=16, confidence_level=0.95)
    nine = _proportion_statistics(9, n=20, confidence_level=0.95)

    assert zero["population_indicator_standard_deviation"] == 0.0
    assert zero["wilson_score_interval"]["upper"] > 0.0
    assert nine["proportion"] == pytest.approx(0.45)
    assert nine["wilson_score_interval"]["lower"] < 0.45
    assert nine["wilson_score_interval"]["upper"] > 0.45


def test_fisher_exact_matches_symmetric_extreme_table() -> None:
    assert _fisher_exact_two_sided([[1, 9], [9, 1]]) == pytest.approx(
        0.001093333910671372
    )


def test_report_is_no_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _resolved_result()
    result_path = _private_json(tmp_path / "resolved.json", result)
    reviewed = _private_json(tmp_path / "reviewed.json", {"reviewed": True})
    package = tmp_path / "package"
    base = tmp_path / "base"
    v2 = tmp_path / "v2"
    variants = tmp_path / "variants"
    for directory in (package, base, v2, variants):
        directory.mkdir(mode=0o700)
    plan = tmp_path / "plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_review_statistics._verified_exact_variant_result",
        lambda *args, **kwargs: deepcopy(result),
    )
    destination = tmp_path / "statistics" / REPORT_NAME
    kwargs = {
        "reviewed_export_path": reviewed,
        "variant_review_package_dir": package,
        "plan_path": plan,
        "execution_dir": base,
        "v2_execution_dir": v2,
        "variant_execution_dir": variants,
        "out": destination,
    }
    _analyze_private_candidate_followup_variant_review(result_path, **kwargs)
    with pytest.raises(FileExistsError, match="exists"):
        _analyze_private_candidate_followup_variant_review(result_path, **kwargs)


def _resolved_result() -> dict:
    rows = {
        "boundary_role_pair": ["equivalent"] * 9 + ["followup_control_preferred"],
        "patch_edge_pair": ["equivalent"] * 11 + ["neither"] * 9,
        "complete_song_pair": ["equivalent"] * 5 + ["followup_control_preferred"],
    }
    outcomes = (
        "equivalent",
        "followup_control_preferred",
        "shifted_context_standard_edge_preferred",
        "preserved_centre_extended_edge_preferred",
        "neither",
        "cannot_tell",
    )
    units = []
    counts = {}
    overall = {outcome: 0 for outcome in outcomes}
    for kind, choices in rows.items():
        counts[kind] = {outcome: choices.count(outcome) for outcome in outcomes}
        for index, choice in enumerate(choices, start=1):
            units.append(
                {
                    "unit_id": f"{kind}-{index:02d}",
                    "kind": kind,
                    "resolved_choice": choice,
                }
            )
            overall[choice] += 1
    result = {
        "schema": "sunofriend.private-separation-candidate-followup-variant-review-result.v1",
        "status": "complete_review_no_activation",
        "bindings": {"review_export_sha256": "a" * 64},
        "reviewed_unit_count": len(units),
        "counts_by_kind_and_outcome": counts,
        "overall_outcome_counts": overall,
        "units": units,
        "permissions": {},
        "effects": {},
    }
    result["document_sha256"] = _document_sha256(result)
    return result


def _private_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
