"""Pure validation and receipt contract for one Banquet synthetic attempt.

The future inference process may emit either an objective pass or a retained
objective failure.  This module imports no model or audio runtime and grants no
retry, audio, activation, source-selection or MIDI authority.  Subjective
ratings are deliberately absent from the schema.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .separation_other_refinement_query_forward_contract import (
    build_query_forward_contract,
)
from .separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_PROFILE_ID,
)


QUERY_SYNTHETIC_REPORT_CONTRACT_SCHEMA = (
    "sunofriend.other-refinement-query-synthetic-report-contract.v1"
)
QUERY_SYNTHETIC_REPORT_SCHEMA = (
    "sunofriend.other-refinement-query-synthetic-report.v1"
)
QUERY_SYNTHETIC_RECEIPT_SCHEMA = (
    "sunofriend.other-refinement-query-synthetic-receipt.v1"
)
QUERY_SYNTHETIC_PLAN_SCHEMA = (
    "sunofriend.other-refinement-query-synthetic-inference-plan.v1"
)
MODEL_LOAD_REPORT_SHA256 = (
    "12c028e88afdb94a22aa4344b75fb63a23386fd4f2292d9bf9aac0405b12dced"
)
MAXIMUM_ELAPSED_SECONDS = 180.0
MAXIMUM_PEAK_RESIDENT_SET_BYTES = 12_884_901_888
MAXIMUM_RECONSTRUCTION_ERROR = 1e-6

OBJECTIVE_GATE_NAMES = (
    "checkpoint_and_model_identity",
    "network_denied",
    "no_audio_access",
    "forward_completed",
    "output_shape_and_clock",
    "finite_output",
    "target_and_residual_peaks_recorded",
    "reconstruction_accounting",
    "elapsed_time_ceiling",
    "peak_memory_ceiling",
)
GATE_OUTCOMES = ("pass", "fail", "not_reached")
FAILURE_CODES = (
    "none",
    "forward_exception",
    "output_contract",
    "elapsed_time_ceiling",
    "peak_memory_ceiling",
)
EXPECTED_RUNTIME = {
    "device": "cpu",
    "numpy": "1.26.4",
    "python": "3.12.10",
    "torch": "2.2.2",
    "torchaudio": "2.2.2",
}
EXPECTED_GENERATED_INPUTS = {
    "origin": "generated_in_memory_fixed_oscillators",
    "random_seed": 0,
    "mixture": {
        "shape": [1, 2, 88_200],
        "dtype": "float32",
        "sample_rate_hz": 44_100,
        "duration_seconds": 2.0,
    },
    "query": {
        "shape": [1, 2, 441_000],
        "dtype": "float32",
        "sample_rate_hz": 44_100,
        "duration_seconds": 10.0,
    },
}
EXPECTED_GUARDS = {
    "os_network_denial_required": True,
    "network_attempts": 0,
    "audio_open_attempts": 0,
    "unapproved_checkpoint_open_attempts": 0,
    "restricted_torch_load_calls": 2,
    "pretrained_network_resolution": False,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_sha256(value: Mapping[str, Any], *, omitted_key: str) -> str:
    payload = {key: item for key, item in value.items() if key != omitted_key}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def query_synthetic_report_contract_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical contract digest without its self-hash."""

    return _canonical_sha256(value, omitted_key="document_sha256")


def query_synthetic_report_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical result digest without its self-hash."""

    return _canonical_sha256(value, omitted_key="report_sha256")


def build_query_synthetic_report_contract() -> dict[str, Any]:
    """Build the immutable, no-effects result contract document."""

    forward_contract = build_query_forward_contract()
    contract: dict[str, Any] = {
        "schema": QUERY_SYNTHETIC_REPORT_CONTRACT_SCHEMA,
        "document_sha256": "",
        "status": "validator_ready_inference_unapproved",
        "report_schema": QUERY_SYNTHETIC_REPORT_SCHEMA,
        "synthetic_plan_schema": QUERY_SYNTHETIC_PLAN_SCHEMA,
        "identity": {
            "scope_id": "other-query-refinement-v1",
            "profile_id": QUERY_PROFILE_ID,
            "source_revision": QUERY_BANDIT_SOURCE_REVISION,
            "model_load_report_sha256": MODEL_LOAD_REPORT_SHA256,
            "forward_contract_document_sha256": forward_contract[
                "document_sha256"
            ],
            "checkpoints": EXPECTED_CHECKPOINTS,
        },
        "attempt_contract": {
            "configuration_count": 1,
            "attempt_index": 1,
            "remediation_cycle": 0,
            "inference_attempt_limit": 1,
        },
        "runtime": EXPECTED_RUNTIME,
        "generated_inputs": EXPECTED_GENERATED_INPUTS,
        "required_guards": EXPECTED_GUARDS,
        "objective_gates": {
            "names": list(OBJECTIVE_GATE_NAMES),
            "allowed_outcomes": list(GATE_OUTCOMES),
            "all_must_pass_for_objective_pass": True,
            "not_reached_is_not_a_pass": True,
        },
        "ceilings": {
            "maximum_elapsed_seconds": MAXIMUM_ELAPSED_SECONDS,
            "maximum_peak_resident_set_bytes": (
                MAXIMUM_PEAK_RESIDENT_SET_BYTES
            ),
            "maximum_reconstruction_error": MAXIMUM_RECONSTRUCTION_ERROR,
        },
        "allowed_statuses": [
            "objective_pass",
            "objective_failure_recorded",
        ],
        "failure_codes": list(FAILURE_CODES),
        "decision_policy": {
            "subjective_feedback_fields_allowed": False,
            "objective_failure_must_be_retained": True,
            "automatic_retry_or_remediation": False,
            "automatic_public_activation": False,
            "automatic_source_selection": False,
            "automatic_midi": False,
        },
        "effects": {
            "network_used": False,
            "checkpoint_opened": False,
            "model_constructed": False,
            "inference_runs": 0,
            "generated_tensors_created": False,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    contract["document_sha256"] = query_synthetic_report_contract_sha256(
        contract
    )
    return contract


def validate_query_synthetic_report_contract(value: Any) -> dict[str, Any]:
    """Reject mutation or authority expansion in the no-effects contract."""

    expected = build_query_synthetic_report_contract()
    if value != expected:
        raise ValueError("query synthetic report contract differs")
    if value["document_sha256"] != query_synthetic_report_contract_sha256(value):
        raise ValueError("query synthetic report contract SHA-256 differs")
    return value


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


def _expected_gate_outcomes(result: Mapping[str, Any]) -> dict[str, str]:
    completed = result["forward_completed"]
    output_shape = result["output_shape"]
    output_dtype = result["output_dtype"]
    output_sample_rate_hz = result["output_sample_rate_hz"]
    finite_output = result["all_output_samples_finite"]
    target_peak = result["target_peak"]
    residual_peak = result["residual_peak"]
    reconstruction = result["maximum_reconstruction_error"]
    residual_definition = result["residual_definition"]
    elapsed = float(result["elapsed_seconds"])
    peak_memory = result["peak_resident_set_bytes"]
    return {
        "checkpoint_and_model_identity": "pass",
        "network_denied": "pass",
        "no_audio_access": "pass",
        "forward_completed": "pass" if completed else "fail",
        "output_shape_and_clock": (
            "pass"
            if completed
            and output_shape == [1, 2, 88_200]
            and output_dtype == "float32"
            and output_sample_rate_hz == 44_100
            else "fail" if completed else "not_reached"
        ),
        "finite_output": (
            "pass"
            if completed and finite_output is True
            else "fail" if completed else "not_reached"
        ),
        "target_and_residual_peaks_recorded": (
            "pass"
            if completed and target_peak is not None and residual_peak is not None
            else "fail" if completed else "not_reached"
        ),
        "reconstruction_accounting": (
            "pass"
            if completed
            and reconstruction is not None
            and residual_definition == "generated_mixture - requested_target"
            and float(reconstruction) <= MAXIMUM_RECONSTRUCTION_ERROR
            else "fail" if completed else "not_reached"
        ),
        "elapsed_time_ceiling": (
            "pass" if elapsed <= MAXIMUM_ELAPSED_SECONDS else "fail"
        ),
        "peak_memory_ceiling": (
            "pass"
            if peak_memory <= MAXIMUM_PEAK_RESIDENT_SET_BYTES
            else "fail"
        ),
    }


def _expected_failure_code(gates: Mapping[str, str]) -> str:
    if gates["forward_completed"] == "fail":
        return "forward_exception"
    if any(
        gates[name] == "fail"
        for name in (
            "output_shape_and_clock",
            "finite_output",
            "target_and_residual_peaks_recorded",
            "reconstruction_accounting",
        )
    ):
        return "output_contract"
    if gates["elapsed_time_ceiling"] == "fail":
        return "elapsed_time_ceiling"
    if gates["peak_memory_ceiling"] == "fail":
        return "peak_memory_ceiling"
    return "none"


def validate_query_synthetic_report(
    value: Any,
    *,
    expected_plan_sha256: str,
) -> dict[str, Any]:
    """Validate a pass or retained failure without importing the model runtime."""

    if not _SHA256_RE.fullmatch(expected_plan_sha256):
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
    if not isinstance(report_sha256, str) or not _SHA256_RE.fullmatch(
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

    expected_gates = _expected_gate_outcomes(result)
    if report["objective_gates"] != expected_gates:
        raise ValueError("query synthetic objective gate projection differs")
    all_pass = all(value == "pass" for value in expected_gates.values())
    expected_status = "objective_pass" if all_pass else "objective_failure_recorded"
    if report["status"] != expected_status:
        raise ValueError("query synthetic status differs from objective gates")
    if result["failure_code"] != _expected_failure_code(expected_gates):
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


def build_query_synthetic_receipt(
    report: Any,
    *,
    expected_plan_sha256: str,
    published_root: Path,
    recorded_at: str,
) -> dict[str, Any]:
    """Build a narrow receipt that cannot grant retry or product authority."""

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


__all__ = [
    "EXPECTED_GENERATED_INPUTS",
    "EXPECTED_GUARDS",
    "EXPECTED_RUNTIME",
    "FAILURE_CODES",
    "GATE_OUTCOMES",
    "MAXIMUM_ELAPSED_SECONDS",
    "MAXIMUM_PEAK_RESIDENT_SET_BYTES",
    "MAXIMUM_RECONSTRUCTION_ERROR",
    "MODEL_LOAD_REPORT_SHA256",
    "OBJECTIVE_GATE_NAMES",
    "QUERY_SYNTHETIC_RECEIPT_SCHEMA",
    "QUERY_SYNTHETIC_PLAN_SCHEMA",
    "QUERY_SYNTHETIC_REPORT_CONTRACT_SCHEMA",
    "QUERY_SYNTHETIC_REPORT_SCHEMA",
    "build_query_synthetic_receipt",
    "build_query_synthetic_report_contract",
    "query_synthetic_report_contract_sha256",
    "query_synthetic_report_sha256",
    "validate_query_synthetic_report",
    "validate_query_synthetic_report_contract",
]
