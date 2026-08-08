"""Strict objective validation for one Banquet synthetic report.

Validation is pure and accepts either an objective pass or a retained failure.
It rejects subjective ratings, mismatched evidence, invented retries and every
product-authority effect.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from .separation_other_refinement_query_synthetic_report_contract import (
    EXPECTED_GENERATED_INPUTS,
    EXPECTED_GUARDS,
    EXPECTED_RUNTIME,
    FAILURE_CODES,
    QUERY_SYNTHETIC_REPORT_SCHEMA,
    SHA256_RE,
    build_query_synthetic_report_contract,
    query_synthetic_report_sha256,
)
from .separation_other_refinement_query_synthetic_report_projection import (
    project_query_synthetic_result,
)


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"query synthetic {label} fields differ")
    return value


def _finite_number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
    ):
        raise ValueError(f"query synthetic {label} is invalid")
    return float(value)


def _optional_finite_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    return _finite_number(value, label)


def validate_query_synthetic_report(
    value: Any,
    *,
    expected_plan_sha256: str,
) -> dict[str, Any]:
    """Validate a pass or retained failure without importing the model runtime."""

    if not SHA256_RE.fullmatch(expected_plan_sha256):
        raise ValueError("expected query synthetic plan SHA-256 is invalid")
    report = _exact_keys(
        value,
        {
            "schema",
            "report_sha256",
            "status",
            "evidence_binding",
            "attempt",
            "runtime",
            "generated_inputs",
            "guards",
            "result",
            "objective_gates",
            "decision",
            "effects",
        },
        "report",
    )
    if report["schema"] != QUERY_SYNTHETIC_REPORT_SCHEMA:
        raise ValueError("query synthetic report schema differs")
    report_sha256 = report["report_sha256"]
    if not isinstance(report_sha256, str) or not SHA256_RE.fullmatch(
        report_sha256
    ):
        raise ValueError("query synthetic report SHA-256 is invalid")
    if report_sha256 != query_synthetic_report_sha256(report):
        raise ValueError("query synthetic report SHA-256 differs")

    contract = build_query_synthetic_report_contract()
    expected_binding = {
        **contract["identity"],
        "synthetic_plan_document_sha256": expected_plan_sha256,
        "report_contract_document_sha256": contract["document_sha256"],
    }
    if report["evidence_binding"] != expected_binding:
        raise ValueError("query synthetic evidence binding differs")
    if report["attempt"] != contract["attempt_contract"]:
        raise ValueError("query synthetic attempt contract differs")
    if report["runtime"] != EXPECTED_RUNTIME:
        raise ValueError("query synthetic runtime identity differs")
    if report["generated_inputs"] != EXPECTED_GENERATED_INPUTS:
        raise ValueError("query synthetic generated inputs differ")
    if report["guards"] != EXPECTED_GUARDS:
        raise ValueError("query synthetic guards differ")

    result = _exact_keys(
        report["result"],
        {
            "forward_completed",
            "output_shape",
            "output_dtype",
            "output_sample_rate_hz",
            "all_output_samples_finite",
            "target_peak",
            "residual_peak",
            "maximum_reconstruction_error",
            "residual_definition",
            "elapsed_seconds",
            "peak_resident_set_bytes",
            "failure_code",
        },
        "result",
    )
    if not isinstance(result["forward_completed"], bool):
        raise ValueError("query synthetic forward completion flag differs")
    _finite_number(result["elapsed_seconds"], "elapsed seconds")
    if (
        not isinstance(result["peak_resident_set_bytes"], int)
        or isinstance(result["peak_resident_set_bytes"], bool)
        or result["peak_resident_set_bytes"] <= 0
    ):
        raise ValueError("query synthetic peak memory is invalid")
    if result["failure_code"] not in FAILURE_CODES:
        raise ValueError("query synthetic failure code differs")
    for field in (
        "target_peak",
        "residual_peak",
        "maximum_reconstruction_error",
    ):
        _optional_finite_number(result[field], field.replace("_", " "))

    if result["forward_completed"]:
        if (
            not isinstance(result["output_shape"], list)
            or len(result["output_shape"]) != 3
            or any(
                not isinstance(item, int) or isinstance(item, bool) or item <= 0
                for item in result["output_shape"]
            )
            or not isinstance(result["output_dtype"], str)
            or not isinstance(result["output_sample_rate_hz"], int)
            or isinstance(result["output_sample_rate_hz"], bool)
            or result["output_sample_rate_hz"] <= 0
            or not isinstance(result["all_output_samples_finite"], bool)
            or not isinstance(result["residual_definition"], str)
        ):
            raise ValueError("query synthetic completed output record is invalid")
    elif any(
        result[field] is not None
        for field in (
            "output_shape",
            "output_dtype",
            "output_sample_rate_hz",
            "all_output_samples_finite",
            "target_peak",
            "residual_peak",
            "maximum_reconstruction_error",
            "residual_definition",
        )
    ):
        raise ValueError("query synthetic failed forward retained output claims")

    projection = project_query_synthetic_result(result)
    expected_gates = projection["objective_gates"]
    if report["objective_gates"] != expected_gates:
        raise ValueError("query synthetic objective gate projection differs")
    all_pass = projection["all_pass"]
    expected_status = projection["status"]
    if report["status"] != expected_status:
        raise ValueError("query synthetic status differs from objective gates")
    if result["failure_code"] != projection["failure_code"]:
        raise ValueError("query synthetic failure code differs from objective gates")

    expected_decision = {
        "objective_gates_passed": all_pass,
        "result_retained": True,
        "eligible_for_separate_next_plan": all_pass,
        "automatic_retry_or_remediation": False,
        "subjective_feedback_considered": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
    }
    if report["decision"] != expected_decision:
        raise ValueError("query synthetic decision projection differs")
    expected_effects = {
        "checkpoint_loaded": True,
        "model_constructed": True,
        "generated_tensors_created": True,
        "inference_attempts": 1,
        "inference_completions": 1 if result["forward_completed"] else 0,
        "audio_reads": 0,
        "audio_writes": 0,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
    }
    if report["effects"] != expected_effects:
        raise ValueError("query synthetic effects differ")
    return dict(report)


__all__ = ["validate_query_synthetic_report"]
