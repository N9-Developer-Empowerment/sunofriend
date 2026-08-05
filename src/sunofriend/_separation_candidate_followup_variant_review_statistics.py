"""Describe uncertainty in one resolved private variant review.

The browser choices are categorical, clustered listening evidence from one
listener.  This module therefore does not fit a normal quality distribution or
change a review gate.  It reports bounded descriptive proportions, Wilson
intervals, an outcome-by-unit-kind chi-square diagnostic, an exact conditional
permutation test, and an exact patch-edge ``neither`` comparison.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_variant_full_song_review import (
    _verified_exact_variant_result,
)
from ._separation_candidate_followup_variant_review_result import _KINDS
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)


SCHEMA = "sunofriend.private-separation-candidate-followup-variant-review-statistics.v1"
STATUS = "descriptive_review_statistics_no_quality_inference"
POLICY_ID = "categorical-review-wilson-and-exact-conditional-v1"
REPORT_NAME = "private-separation-candidate-followup-variant-review-statistics.json"
CONFIDENCE_LEVEL = 0.95
_OUTCOME_ORDER = (
    "equivalent",
    "followup_control_preferred",
    "shifted_context_standard_edge_preferred",
    "preserved_centre_extended_edge_preferred",
    "neither",
    "cannot_tell",
)
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_selected": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_evidence_mutated": False,
    "review_gate_changed": False,
    "separator_accepted": False,
    "source_graph_mutated": False,
}


def _analyze_private_candidate_followup_variant_review(
    variant_review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write a no-overwrite, non-authorising statistical diagnostic."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private statistics filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private statistics report exists: {output}")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "private review statistics root")

    review_package = Path(variant_review_package_dir).expanduser().absolute()
    _require_private_directory(review_package, "private variant review package")
    result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=review_package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    result_snapshot = _load_private_json_snapshot(
        variant_review_result_path, "private follow-up variant review result"
    )
    if result_snapshot["document"] != result:
        raise ValueError("private follow-up variant review result changed")

    reviewed_export = Path(reviewed_export_path).expanduser().absolute()
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            Path(execution_dir).expanduser().absolute(),
            Path(v2_execution_dir).expanduser().absolute(),
            Path(variant_execution_dir).expanduser().absolute(),
            review_package,
        ),
        evidence_paths=(
            result_snapshot["path"],
            reviewed_export,
            Path(plan_path).expanduser().absolute(),
        ),
    )

    units, outcomes, table = _validated_table(result)
    group_statistics = {
        kind: _group_statistics(
            table[index], outcomes=outcomes, confidence_level=CONFIDENCE_LEVEL
        )
        for index, kind in enumerate(_KINDS)
    }
    totals = [
        sum(table[row][column] for row in range(len(table)))
        for column in range(len(outcomes))
    ]
    group_statistics["overall"] = _group_statistics(
        totals, outcomes=outcomes, confidence_level=CONFIDENCE_LEVEL
    )
    contingency = _contingency_analysis(table, row_names=_KINDS, column_names=outcomes)
    edge_neither = _edge_neither_analysis(units, confidence_level=CONFIDENCE_LEVEL)

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "variant_review_result_sha256": result_snapshot["sha256"],
            "variant_review_result_document_sha256": result["document_sha256"],
            "review_export_sha256": result["bindings"]["review_export_sha256"],
            "reviewed_unit_count": len(units),
        },
        "outcome_order": list(outcomes),
        "groups": group_statistics,
        "outcome_by_unit_kind": contingency,
        "patch_edge_neither_concentration": edge_neither,
        "assumptions_and_boundaries": {
            "raw_review_choices_assumed_normal": False,
            "normal_quantile_used_only_for_wilson_score_intervals": True,
            "wilson_confidence_level": CONFIDENCE_LEVEL,
            "independent_bernoulli_trials_established": False,
            "units_share_song_boundaries_and_listener": True,
            "single_listener": True,
            "listener_reliability_estimable": False,
            "inter_listener_agreement_estimable": False,
            "separator_accuracy_estimable": False,
            "audio_quality_distribution_estimable": False,
            "quality_confidence_level": None,
        },
        "interpretation": {
            "statistics_are_descriptive_review_evidence": True,
            "standard_deviation_is_for_binary_outcome_indicators": True,
            "neither_means_formal_comparative_choice_not_unusable_audio": True,
            "exact_conditional_test_conditions_on_observed_margins": True,
            "small_p_value_would_mean_outcome_pattern_depends_on_unit_kind": True,
            "small_p_value_would_not_prove_audio_quality_or_separator_accuracy": True,
            "automatic_winner_selected": False,
            "review_gate_changed": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "The 36 responses are not 36 independent listeners or songs.",
            "Wilson intervals use an independent-Bernoulli approximation and are descriptive here.",
            "The asymptotic chi-square p-value is unreliable when expected cells are sparse.",
            "The exact conditional test describes association with unit kind, not musical quality.",
            "Repeated blinded sessions or additional listeners are needed to estimate listening reliability.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _validated_table(
    result: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], tuple[str, ...], list[list[int]]]:
    raw_units = result.get("units")
    raw_counts = result.get("counts_by_kind_and_outcome")
    raw_overall = result.get("overall_outcome_counts")
    if (
        not isinstance(raw_units, list)
        or not raw_units
        or not isinstance(raw_counts, Mapping)
        or not isinstance(raw_overall, Mapping)
    ):
        raise ValueError("variant review statistical inventory is invalid")
    units: list[Mapping[str, Any]] = []
    observed_outcomes: set[str] = set()
    recomputed: dict[str, dict[str, int]] = {kind: {} for kind in _KINDS}
    for unit in raw_units:
        if not isinstance(unit, Mapping):
            raise ValueError("variant review statistical unit is invalid")
        kind = unit.get("kind")
        outcome = unit.get("resolved_choice")
        if kind not in _KINDS or not isinstance(outcome, str) or not outcome:
            raise ValueError("variant review statistical unit fields are invalid")
        units.append(unit)
        observed_outcomes.add(outcome)
        recomputed[kind][outcome] = recomputed[kind].get(outcome, 0) + 1

    ordered = [item for item in _OUTCOME_ORDER if item in raw_overall]
    ordered.extend(sorted(set(raw_overall) - set(ordered)))
    if not ordered or observed_outcomes - set(ordered):
        raise ValueError("variant review statistical outcome inventory differs")
    outcomes = tuple(ordered)
    table = [
        [recomputed[kind].get(outcome, 0) for outcome in outcomes] for kind in _KINDS
    ]
    expected_counts = {
        kind: {outcome: table[row][column] for column, outcome in enumerate(outcomes)}
        for row, kind in enumerate(_KINDS)
    }
    overall = {
        outcome: sum(table[row][column] for row in range(len(_KINDS)))
        for column, outcome in enumerate(outcomes)
    }
    if (
        expected_counts != raw_counts
        or overall != raw_overall
        or sum(overall.values()) != result.get("reviewed_unit_count")
    ):
        raise ValueError("variant review statistical counts differ")
    return units, outcomes, table


def _group_statistics(
    counts: Sequence[int], *, outcomes: Sequence[str], confidence_level: float
) -> dict[str, Any]:
    n = sum(counts)
    if n <= 0 or len(counts) != len(outcomes):
        raise ValueError("statistical group is empty or inconsistent")
    return {
        "unit_count": n,
        "outcomes": {
            outcome: _proportion_statistics(
                count, n=n, confidence_level=confidence_level
            )
            for outcome, count in zip(outcomes, counts)
        },
    }


def _proportion_statistics(
    count: int, *, n: int, confidence_level: float
) -> dict[str, Any]:
    if count < 0 or count > n or n <= 0:
        raise ValueError("binomial count is invalid")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence level is invalid")
    proportion = count / n
    population_sd = math.sqrt(proportion * (1.0 - proportion))
    sample_sd = (
        math.sqrt(n * proportion * (1.0 - proportion) / (n - 1)) if n > 1 else 0.0
    )
    z = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    denominator = 1.0 + z * z / n
    centre = (proportion + z * z / (2.0 * n)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / n + z * z / (4.0 * n * n))
        / denominator
    )
    return {
        "count": count,
        "proportion": proportion,
        "population_indicator_standard_deviation": population_sd,
        "sample_indicator_standard_deviation": sample_sd,
        "standard_error_of_proportion": population_sd / math.sqrt(n),
        "wilson_score_interval": {
            "confidence_level": confidence_level,
            "lower": max(0.0, centre - half),
            "upper": min(1.0, centre + half),
        },
    }


def _contingency_analysis(
    table: Sequence[Sequence[int]],
    *,
    row_names: Sequence[str],
    column_names: Sequence[str],
) -> dict[str, Any]:
    if len(table) != len(row_names) or not table:
        raise ValueError("contingency rows differ")
    active_columns = [
        index
        for index in range(len(column_names))
        if sum(row[index] for row in table) > 0
    ]
    active_names = [column_names[index] for index in active_columns]
    active_table = [[row[index] for index in active_columns] for row in table]
    row_totals = [sum(row) for row in active_table]
    column_totals = [
        sum(row[column] for row in active_table)
        for column in range(len(active_columns))
    ]
    total = sum(row_totals)
    if total <= 0 or any(value <= 0 for value in row_totals + column_totals):
        raise ValueError("contingency margins are invalid")
    expected = [
        [row_total * column_total / total for column_total in column_totals]
        for row_total in row_totals
    ]
    statistic = _pearson_chi_square(active_table, expected)
    degrees = (len(row_totals) - 1) * (len(column_totals) - 1)
    expected_flat = [value for row in expected for value in row]
    exact = _exact_conditional_chi_square(
        active_table, row_totals=row_totals, column_totals=column_totals
    )
    return {
        "row_order": list(row_names),
        "column_order": active_names,
        "observed": active_table,
        "expected_under_independence": expected,
        "pearson_chi_square": statistic,
        "degrees_of_freedom": degrees,
        "asymptotic_p_value": _chi_square_survival_even_df(statistic, degrees),
        "asymptotic_reliability": {
            "minimum_expected_count": min(expected_flat),
            "cells_below_5": sum(value < 5.0 for value in expected_flat),
            "total_cells": len(expected_flat),
            "all_expected_counts_at_least_5": all(
                value >= 5.0 for value in expected_flat
            ),
            "use_asymptotic_p_value_for_decision": False,
        },
        "exact_conditional_permutation": exact,
    }


def _pearson_chi_square(
    observed: Sequence[Sequence[int]], expected: Sequence[Sequence[float]]
) -> float:
    return sum(
        (actual - target) ** 2 / target
        for actual_row, expected_row in zip(observed, expected)
        for actual, target in zip(actual_row, expected_row)
    )


def _chi_square_survival_even_df(statistic: float, degrees: int) -> float | None:
    if statistic < 0.0 or degrees <= 0 or degrees % 2:
        return None
    half = statistic / 2.0
    return math.exp(-half) * sum(
        half**index / math.factorial(index) for index in range(degrees // 2)
    )


def _exact_conditional_chi_square(
    observed: Sequence[Sequence[int]],
    *,
    row_totals: Sequence[int],
    column_totals: Sequence[int],
) -> dict[str, Any]:
    expected = [
        [row * column / sum(row_totals) for column in column_totals]
        for row in row_totals
    ]
    observed_statistic = _pearson_chi_square(observed, expected)
    log_constant = (
        sum(math.lgamma(value + 1) for value in row_totals)
        + sum(math.lgamma(value + 1) for value in column_totals)
        - math.lgamma(sum(row_totals) + 1)
    )
    total_probability = 0.0
    extreme_probability = 0.0
    table_count = 0
    for candidate in _tables_with_margins(row_totals, column_totals):
        probability = math.exp(
            log_constant
            - sum(math.lgamma(value + 1) for row in candidate for value in row)
        )
        statistic = _pearson_chi_square(candidate, expected)
        total_probability += probability
        if statistic + 1e-12 >= observed_statistic:
            extreme_probability += probability
        table_count += 1
    return {
        "method": "exact-enumeration-of-fixed-margin-permutation-tables",
        "tables_enumerated": table_count,
        "enumerated_probability_mass": total_probability,
        "p_value": min(1.0, extreme_probability / total_probability),
        "monte_carlo": False,
    }


def _tables_with_margins(
    row_totals: Sequence[int], column_totals: Sequence[int]
) -> Iterable[list[list[int]]]:
    if len(row_totals) < 2 or len(column_totals) < 2:
        raise ValueError(
            "exact conditional table requires at least two rows and columns"
        )

    def visit(
        row_index: int, remaining_columns: tuple[int, ...], rows: list[list[int]]
    ) -> Iterable[list[list[int]]]:
        if row_index == len(row_totals) - 1:
            if sum(remaining_columns) == row_totals[row_index]:
                yield [*rows, list(remaining_columns)]
            return
        for allocation in _bounded_compositions(
            row_totals[row_index], remaining_columns
        ):
            remaining = tuple(
                cap - value for cap, value in zip(remaining_columns, allocation)
            )
            yield from visit(row_index + 1, remaining, [*rows, allocation])

    yield from visit(0, tuple(column_totals), [])


def _bounded_compositions(total: int, caps: Sequence[int]) -> Iterable[list[int]]:
    if len(caps) == 1:
        if 0 <= total <= caps[0]:
            yield [total]
        return
    tail_capacity = sum(caps[1:])
    lower = max(0, total - tail_capacity)
    upper = min(total, caps[0])
    for first in range(lower, upper + 1):
        for tail in _bounded_compositions(total - first, caps[1:]):
            yield [first, *tail]


def _edge_neither_analysis(
    units: Sequence[Mapping[str, Any]], *, confidence_level: float
) -> dict[str, Any]:
    edge = [unit for unit in units if unit["kind"] == "patch_edge_pair"]
    non_edge = [unit for unit in units if unit["kind"] != "patch_edge_pair"]
    edge_neither = sum(unit["resolved_choice"] == "neither" for unit in edge)
    non_edge_neither = sum(unit["resolved_choice"] == "neither" for unit in non_edge)
    table = [
        [edge_neither, len(edge) - edge_neither],
        [non_edge_neither, len(non_edge) - non_edge_neither],
    ]
    edge_stats = _proportion_statistics(
        edge_neither, n=len(edge), confidence_level=confidence_level
    )
    non_edge_stats = _proportion_statistics(
        non_edge_neither, n=len(non_edge), confidence_level=confidence_level
    )
    return {
        "question": "Is the formal neither outcome concentrated in patch-edge units?",
        "row_order": ["patch_edge_pair", "non_patch_edge"],
        "column_order": ["neither", "other_outcome"],
        "observed": table,
        "patch_edge_neither": edge_stats,
        "non_patch_edge_neither": non_edge_stats,
        "risk_difference": edge_stats["proportion"] - non_edge_stats["proportion"],
        "odds_ratio": (
            table[0][0] * table[1][1] / (table[0][1] * table[1][0])
            if table[0][1] and table[1][0]
            else None
        ),
        "odds_ratio_note": (
            "undefined because at least one denominator cell is zero"
            if not table[0][1] or not table[1][0]
            else None
        ),
        "fisher_exact_two_sided_p_value": _fisher_exact_two_sided(table),
        "contrast_pre_specified_before_review": False,
        "multiple_comparison_adjustment_applied": False,
        "p_value_is_exploratory": True,
        "interpretation_boundary": (
            "This tests where one formal response occurred; it does not mean "
            "that neither-labelled audio was useless or poor."
        ),
    }


def _fisher_exact_two_sided(table: Sequence[Sequence[int]]) -> float:
    a, b = table[0]
    c, d = table[1]
    row = a + b
    neither = a + c
    other = b + d
    total = row + c + d
    denominator = math.comb(total, row)

    def probability(value: int) -> float:
        return math.comb(neither, value) * math.comb(other, row - value) / denominator

    observed_probability = probability(a)
    lower = max(0, row - other)
    upper = min(row, neither)
    return min(
        1.0,
        sum(
            probability(value)
            for value in range(lower, upper + 1)
            if probability(value) <= observed_probability + 1e-15
        ),
    )
