"""Immutable, no-effects contract for one Banquet synthetic report.

This foundational module owns only identities, fixed objective limits,
canonical hashing and the public contract document.  It imports no model or
audio runtime and performs no validation side effects.
"""

from __future__ import annotations

import hashlib
import json
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
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
    "QUERY_SYNTHETIC_PLAN_SCHEMA",
    "QUERY_SYNTHETIC_RECEIPT_SCHEMA",
    "QUERY_SYNTHETIC_REPORT_CONTRACT_SCHEMA",
    "QUERY_SYNTHETIC_REPORT_SCHEMA",
    "SHA256_RE",
    "build_query_synthetic_report_contract",
    "query_synthetic_report_contract_sha256",
    "query_synthetic_report_sha256",
    "validate_query_synthetic_report_contract",
]
