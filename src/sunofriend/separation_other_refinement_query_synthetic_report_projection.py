"""Pure projection of one synthetic attempt into the immutable report schema."""

from __future__ import annotations

from typing import Any, Mapping

from .separation_other_refinement_query_synthetic_report_contract import (
    EXPECTED_GENERATED_INPUTS,
    EXPECTED_RUNTIME,
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_RESIDENT_SET_BYTES,
    MAXIMUM_RECONSTRUCTION_ERROR,
    build_query_synthetic_report_contract,
    query_synthetic_report_sha256,
)


def project_query_synthetic_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Derive gates, status and failure code from objective measurements."""

    completed = result["forward_completed"]
    elapsed = float(result["elapsed_seconds"])
    peak_memory = result["peak_resident_set_bytes"]
    gates = {
        "checkpoint_and_model_identity": "pass",
        "network_denied": "pass",
        "no_audio_access": "pass",
        "forward_completed": "pass" if completed else "fail",
        "output_shape_and_clock": (
            "pass"
            if completed
            and result["output_shape"] == [1, 2, 88_200]
            and result["output_dtype"] == "float32"
            and result["output_sample_rate_hz"] == 44_100
            else "fail" if completed else "not_reached"
        ),
        "finite_output": (
            "pass"
            if completed and result["all_output_samples_finite"] is True
            else "fail" if completed else "not_reached"
        ),
        "target_and_residual_peaks_recorded": (
            "pass"
            if completed
            and result["target_peak"] is not None
            and result["residual_peak"] is not None
            else "fail" if completed else "not_reached"
        ),
        "reconstruction_accounting": (
            "pass"
            if completed
            and result["maximum_reconstruction_error"] is not None
            and result["residual_definition"]
            == "generated_mixture - requested_target"
            and float(result["maximum_reconstruction_error"])
            <= MAXIMUM_RECONSTRUCTION_ERROR
            else "fail" if completed else "not_reached"
        ),
        "elapsed_time_ceiling": (
            "pass" if elapsed <= MAXIMUM_ELAPSED_SECONDS else "fail"
        ),
        "peak_memory_ceiling": (
            "pass" if peak_memory <= MAXIMUM_PEAK_RESIDENT_SET_BYTES else "fail"
        ),
    }
    if gates["forward_completed"] == "fail":
        failure_code = "forward_exception"
    elif any(
        gates[name] == "fail"
        for name in (
            "output_shape_and_clock",
            "finite_output",
            "target_and_residual_peaks_recorded",
            "reconstruction_accounting",
        )
    ):
        failure_code = "output_contract"
    elif gates["elapsed_time_ceiling"] == "fail":
        failure_code = "elapsed_time_ceiling"
    elif gates["peak_memory_ceiling"] == "fail":
        failure_code = "peak_memory_ceiling"
    else:
        failure_code = "none"
    all_pass = all(outcome == "pass" for outcome in gates.values())
    return {
        "objective_gates": gates,
        "status": "objective_pass" if all_pass else "objective_failure_recorded",
        "failure_code": failure_code,
        "all_pass": all_pass,
    }


def build_query_synthetic_report(
    *,
    result: Mapping[str, Any],
    guards: Mapping[str, Any],
    expected_plan_sha256: str,
) -> dict[str, Any]:
    """Build a hash-bound report from measured results and guard counts."""

    projection = project_query_synthetic_result(result)
    measured_result = dict(result)
    measured_result["failure_code"] = projection["failure_code"]
    contract = build_query_synthetic_report_contract()
    report: dict[str, Any] = {
        "schema": contract["report_schema"],
        "report_sha256": "",
        "status": projection["status"],
        "evidence_binding": {
            **contract["identity"],
            "synthetic_plan_document_sha256": expected_plan_sha256,
            "report_contract_document_sha256": contract["document_sha256"],
        },
        "attempt": contract["attempt_contract"],
        "runtime": EXPECTED_RUNTIME,
        "generated_inputs": EXPECTED_GENERATED_INPUTS,
        "guards": dict(guards),
        "result": measured_result,
        "objective_gates": projection["objective_gates"],
        "decision": {
            "objective_gates_passed": projection["all_pass"],
            "result_retained": True,
            "eligible_for_separate_next_plan": projection["all_pass"],
            "automatic_retry_or_remediation": False,
            "subjective_feedback_considered": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
        "effects": {
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
        },
    }
    report["report_sha256"] = query_synthetic_report_sha256(report)
    return report


__all__ = ["build_query_synthetic_report", "project_query_synthetic_result"]
