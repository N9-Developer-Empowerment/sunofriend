"""Narrow receipt construction for one validated Banquet synthetic result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .separation_other_refinement_query_load_contract import QUERY_PROFILE_ID
from .separation_other_refinement_query_synthetic_report_contract import (
    QUERY_SYNTHETIC_RECEIPT_SCHEMA,
)
from .separation_other_refinement_query_synthetic_report_validation import (
    validate_query_synthetic_report,
)


def build_query_synthetic_receipt(
    report: Any,
    *,
    expected_plan_sha256: str,
    published_root: Path,
    recorded_at: str,
) -> dict[str, Any]:
    """Build a receipt that cannot grant retry or product authority."""

    validated = validate_query_synthetic_report(
        report,
        expected_plan_sha256=expected_plan_sha256,
    )
    if not published_root.is_absolute():
        raise ValueError("query synthetic published root must be absolute")
    if not isinstance(recorded_at, str) or not recorded_at:
        raise ValueError("query synthetic receipt time is required")
    passed = validated["status"] == "objective_pass"
    return {
        "schema": QUERY_SYNTHETIC_RECEIPT_SCHEMA,
        "status": (
            "synthetic_objective_pass_recorded_no_product_authority"
            if passed
            else "synthetic_objective_failure_retained_no_retry_authority"
        ),
        "recorded_at": recorded_at,
        "profile_id": QUERY_PROFILE_ID,
        "published_root": str(published_root),
        "synthetic_plan_document_sha256": expected_plan_sha256,
        "synthetic_report_sha256": validated["report_sha256"],
        "report_contract_document_sha256": validated["evidence_binding"][
            "report_contract_document_sha256"
        ],
        "objective_gates_passed": passed,
        "result_retained": True,
        "next_action": (
            "review_a_separate_authorised_audio_query_plan"
            if passed
            else "review_one_bounded_remediation_plan"
        ),
        "retry_authorized": False,
        "audio_processing_authorized": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
    }


__all__ = ["build_query_synthetic_receipt"]
