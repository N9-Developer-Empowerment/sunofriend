from __future__ import annotations

from copy import deepcopy

import pytest

from devtools.code_risk_ratchet import assess_code_risk_ratchet


def _record(
    name: str,
    *,
    function_hash: str,
    score: str,
    covered: int,
    possible: int,
) -> dict[str, object]:
    return {
        "target": {
            "path": "src/sunofriend/example.py",
            "qualified_name": name,
            "function_source_sha256": function_hash,
        },
        "crap_score": score,
        "status": "ok",
        "coverage": {
            "covered_opportunities": covered,
            "possible_opportunities": possible,
        },
    }


def _report(*records: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "sunofriend-code-risk.v1",
        "status": "advisory_complete",
        "binding": {"source_tree_sha256": "a" * 64},
        "formula": {
            "id": "crap1",
            "expression": "complexity^2 * (1 - coverage_fraction)^3 + complexity",
            "coverage_opportunities": "statements_plus_branches",
            "threshold": "30",
        },
        "functions": list(records),
    }


def test_unchanged_functions_do_not_ratchet_when_the_module_changes() -> None:
    baseline = _report(
        _record("stable", function_hash="1" * 64, score="45", covered=5, possible=10)
    )
    current = deepcopy(baseline)
    current["binding"]["source_tree_sha256"] = "b" * 64
    current["functions"][0]["crap_score"] = "50"
    current["functions"][0]["coverage"]["covered_opportunities"] = 4

    result = assess_code_risk_ratchet(baseline, current)

    assert result["status"] == "passed"
    assert result["summary"]["materially_changed_function_count"] == 0


def test_changed_and_new_functions_enforce_the_adoption_policy() -> None:
    baseline = _report(
        _record("changed", function_hash="1" * 64, score="20", covered=8, possible=10)
    )
    current = _report(
        _record("changed", function_hash="2" * 64, score="21", covered=7, possible=10),
        _record("new_ok", function_hash="3" * 64, score="30", covered=10, possible=10),
        _record("new_bad", function_hash="4" * 64, score="30.1", covered=10, possible=10),
    )

    result = assess_code_risk_ratchet(baseline, current)

    assert result["status"] == "failed"
    assert result["summary"] == {
        "baseline_function_count": 1,
        "current_function_count": 3,
        "materially_changed_function_count": 3,
        "new_function_count": 2,
        "failure_count": 3,
    }
    assert [failure["kind"] for failure in result["failures"]] == [
        "changed_function_crap_increased",
        "changed_function_coverage_reduced",
        "new_function_above_threshold",
    ]


def test_ratchet_rejects_incomplete_or_unbound_reports() -> None:
    baseline = _report(
        _record("changed", function_hash="1" * 64, score="20", covered=8, possible=10)
    )
    current = deepcopy(baseline)
    current["status"] = "incomplete"
    with pytest.raises(ValueError, match="complete advisory"):
        assess_code_risk_ratchet(baseline, current)

    current = deepcopy(baseline)
    current["functions"][0]["target"].pop("function_source_sha256")
    with pytest.raises(ValueError, match="source hash"):
        assess_code_risk_ratchet(baseline, current)
