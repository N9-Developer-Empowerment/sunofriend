"""Independent recomputation verifier for the synthetic remix-ranker canary."""

from __future__ import annotations

from typing import Any, Mapping

from .remix_ranker_canary import (
    build_remix_ranker_canary_request,
    run_remix_ranker_canary,
    validate_remix_ranker_canary_result,
)
from .source_receipt import document_sha256


REMIX_RANKER_VERIFICATION_SCHEMA = "sunofriend.remix-ranker-verification.v0"


def verify_remix_ranker_canary(
    request: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    if dict(request) != build_remix_ranker_canary_request():
        raise ValueError("verifier accepts only the exact synthetic remix request")
    supplied = validate_remix_ranker_canary_result(result, request=request)
    recomputed = run_remix_ranker_canary(request)
    if supplied != recomputed:
        raise ValueError(
            "synthetic remix result differs from independent recomputation"
        )
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_VERIFICATION_SCHEMA,
        "status": "verified_synthetic_technical_evidence",
        "request_document_sha256": request["document_sha256"],
        "result_document_sha256": supplied["document_sha256"],
        "checks": {
            "request_exact": True,
            "result_recomputed_exactly": True,
            "checkpoint_resume_exact": True,
            "constant_baseline_present": True,
            "linear_baseline_present": True,
            "shuffled_control_present": True,
        },
        "privacy": {
            "synthetic_only": True,
            "audio_read": False,
            "real_snapshot_read": False,
            "network_used": False,
            "downloads_used": False,
            "paths_embedded": False,
        },
        "authority": {
            "technical_verification_only": True,
            "training_authorized": False,
            "checkpoint_promoted": False,
            "product_admitted": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


__all__ = ["REMIX_RANKER_VERIFICATION_SCHEMA", "verify_remix_ranker_canary"]
