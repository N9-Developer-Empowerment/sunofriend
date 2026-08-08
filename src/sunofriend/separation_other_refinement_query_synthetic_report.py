"""Compatibility facade for the split Banquet synthetic-result contracts.

Contract construction, objective validation and receipt creation live in
separate pure modules.  This facade preserves the original import surface
without importing a model or audio runtime.
"""

from __future__ import annotations

from .separation_other_refinement_query_synthetic_report_contract import (
    EXPECTED_GENERATED_INPUTS,
    EXPECTED_GUARDS,
    EXPECTED_RUNTIME,
    FAILURE_CODES,
    GATE_OUTCOMES,
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_RESIDENT_SET_BYTES,
    MAXIMUM_RECONSTRUCTION_ERROR,
    MODEL_LOAD_REPORT_SHA256,
    OBJECTIVE_GATE_NAMES,
    QUERY_SYNTHETIC_PLAN_SCHEMA,
    QUERY_SYNTHETIC_RECEIPT_SCHEMA,
    QUERY_SYNTHETIC_REPORT_CONTRACT_SCHEMA,
    QUERY_SYNTHETIC_REPORT_SCHEMA,
    build_query_synthetic_report_contract,
    query_synthetic_report_contract_sha256,
    query_synthetic_report_sha256,
    validate_query_synthetic_report_contract,
)
from .separation_other_refinement_query_synthetic_report_receipt import (
    build_query_synthetic_receipt,
)
from .separation_other_refinement_query_synthetic_report_validation import (
    validate_query_synthetic_report,
)


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
    "build_query_synthetic_receipt",
    "build_query_synthetic_report_contract",
    "query_synthetic_report_contract_sha256",
    "query_synthetic_report_sha256",
    "validate_query_synthetic_report",
    "validate_query_synthetic_report_contract",
]
