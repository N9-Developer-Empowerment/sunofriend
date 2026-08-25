"""Compare two CRAP reports and enforce the changed-function ratchet."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Any

from devtools.code_risk import read_coverage_json


RATCHET_SCHEMA = "sunofriend-code-risk-ratchet.v1"
REPORT_SCHEMA = "sunofriend-code-risk.v1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _identity(record: Mapping[str, Any]) -> tuple[str, str]:
    target = record.get("target")
    if not isinstance(target, Mapping):
        raise ValueError("code-risk function requires a target")
    path = str(target.get("path", ""))
    qualified_name = str(target.get("qualified_name", ""))
    if not path or not qualified_name:
        raise ValueError("code-risk function identity is incomplete")
    return path, qualified_name


def _index(document: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    if document.get("schema") != REPORT_SCHEMA:
        raise ValueError("unsupported code-risk report schema")
    if document.get("status") != "advisory_complete":
        raise ValueError("code-risk ratchet requires complete advisory reports")
    functions = document.get("functions")
    if not isinstance(functions, list):
        raise ValueError("code-risk report functions must be a list")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in functions:
        if not isinstance(record, Mapping):
            raise ValueError("code-risk function must be an object")
        identity = _identity(record)
        if identity in result:
            raise ValueError(f"duplicate code-risk function identity: {identity}")
        target = record["target"]
        function_hash = str(target.get("function_source_sha256", ""))
        if SHA256_PATTERN.fullmatch(function_hash) is None:
            raise ValueError(f"function source hash is missing or invalid: {identity}")
        result[identity] = record
    return result


def _decimal(record: Mapping[str, Any], field: str) -> Decimal:
    value = record.get(field)
    if value is None:
        raise ValueError(f"changed executable function has no {field}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(
            f"changed executable function has invalid {field}"
        ) from error
    if not result.is_finite():
        raise ValueError(f"changed executable function has invalid {field}")
    return result


def _coverage_fraction(record: Mapping[str, Any]) -> Decimal:
    coverage = record.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("changed executable function has no coverage record")
    covered = coverage.get("covered_opportunities")
    possible = coverage.get("possible_opportunities")
    if (
        isinstance(covered, bool)
        or not isinstance(covered, int)
        or isinstance(possible, bool)
        or not isinstance(possible, int)
        or possible <= 0
        or covered < 0
        or covered > possible
    ):
        raise ValueError("changed executable function has invalid coverage")
    return Decimal(covered) / Decimal(possible)


def assess_code_risk_ratchet(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Return deterministic failures for new and materially changed functions."""

    baseline_functions = _index(baseline)
    current_functions = _index(current)
    baseline_formula = baseline.get("formula")
    current_formula = current.get("formula")
    if not isinstance(baseline_formula, Mapping) or not isinstance(
        current_formula, Mapping
    ):
        raise ValueError("code-risk reports require formula metadata")
    comparison_fields = ("id", "expression", "coverage_opportunities", "threshold")
    if any(
        baseline_formula.get(field) != current_formula.get(field)
        for field in comparison_fields
    ):
        raise ValueError("code-risk reports use different formulas or thresholds")
    try:
        threshold = Decimal(str(current_formula["threshold"]))
    except InvalidOperation as error:
        raise ValueError("code-risk threshold is invalid") from error
    if not threshold.is_finite() or threshold <= 0:
        raise ValueError("code-risk threshold is invalid")
    baseline_binding = baseline.get("binding")
    current_binding = current.get("binding")
    if not isinstance(baseline_binding, Mapping) or not isinstance(
        current_binding, Mapping
    ):
        raise ValueError("code-risk reports require source bindings")
    for binding in (baseline_binding, current_binding):
        if SHA256_PATTERN.fullmatch(str(binding.get("source_tree_sha256", ""))) is None:
            raise ValueError("code-risk source binding is missing or invalid")
    failures: list[dict[str, Any]] = []
    changed_count = 0
    new_count = 0
    for identity, record in sorted(current_functions.items()):
        target = record["target"]
        before = baseline_functions.get(identity)
        if before is not None and (
            before["target"]["function_source_sha256"]
            == target["function_source_sha256"]
        ):
            continue
        changed_count += 1
        if record.get("status") == "not_applicable":
            continue
        current_score = _decimal(record, "crap_score")
        current_coverage = _coverage_fraction(record)
        if before is None or before.get("status") == "not_applicable":
            new_count += 1
            if current_score > threshold:
                failures.append(
                    {
                        "kind": "new_function_above_threshold",
                        "path": identity[0],
                        "qualified_name": identity[1],
                        "crap_score": format(current_score, "f"),
                        "threshold": format(threshold, "f"),
                    }
                )
            continue
        baseline_score = _decimal(before, "crap_score")
        baseline_coverage = _coverage_fraction(before)
        if current_score > baseline_score:
            failures.append(
                {
                    "kind": "changed_function_crap_increased",
                    "path": identity[0],
                    "qualified_name": identity[1],
                    "before": format(baseline_score, "f"),
                    "after": format(current_score, "f"),
                }
            )
        if current_coverage < baseline_coverage:
            failures.append(
                {
                    "kind": "changed_function_coverage_reduced",
                    "path": identity[0],
                    "qualified_name": identity[1],
                    "before": format(baseline_coverage * Decimal(100), ".3f"),
                    "after": format(current_coverage * Decimal(100), ".3f"),
                }
            )
    return {
        "schema": RATCHET_SCHEMA,
        "status": "failed" if failures else "passed",
        "baseline_source_tree_sha256": baseline_binding["source_tree_sha256"],
        "current_source_tree_sha256": current_binding["source_tree_sha256"],
        "summary": {
            "baseline_function_count": len(baseline_functions),
            "current_function_count": len(current_functions),
            "materially_changed_function_count": changed_count,
            "new_function_count": new_count,
            "failure_count": len(failures),
        },
        "failures": failures,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        baseline, _ = read_coverage_json(args.baseline)
        current, _ = read_coverage_json(args.current)
        result = assess_code_risk_ratchet(baseline, current)
    except (ValueError, OSError) as error:
        parser.exit(2, f"code-risk ratchet blocked: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
