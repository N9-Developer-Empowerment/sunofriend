"""Validation and identity binding for one private six-role canary."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_integration_plan import PERSISTED_ROLES


REPORT_SCHEMA = "sunofriend.fine-stem-six-role-integration-report.v1"
REPORT_STATUS = "objective_execution_complete_private_review_required"
ARTIFACT_ROLES = ("reference", *PERSISTED_ROLES, "reconstruction_check")


def integration_report_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "report_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def validate_fine_stem_integration_report(value: Mapping[str, Any]) -> dict[str, Any]:
    report = copy.deepcopy(dict(value))
    if report.get("schema") != REPORT_SCHEMA or report.get("status") != REPORT_STATUS:
        raise ValueError("fine-stem integration report identity differs")
    if report.get("report_sha256") != integration_report_sha256(report):
        raise ValueError("fine-stem integration report hash differs")
    if report.get("plan_sha256") != report.get("approved_plan_sha256"):
        raise ValueError("fine-stem integration approval binding differs")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 8:
        raise ValueError("fine-stem integration report cases differ")
    if len({case.get("case_id") for case in cases}) != 8:
        raise ValueError("fine-stem integration report case identities differ")
    for case in cases:
        if set(case.get("artifacts", {})) != set(ARTIFACT_ROLES):
            raise ValueError("fine-stem integration artifact roles differ")
        if case.get("maximum_reconstruction_error_lsb", 3) > 2:
            raise ValueError("fine-stem integration reconstruction accounting failed")
        if case.get("projection", {}).get("method") != (
            "fixed grouped-other-constrained three-way Wiener mask"
        ):
            raise ValueError("fine-stem integration projection differs")
    effects = report.get("effects", {})
    if (
        effects.get("model_loads") != 3
        or effects.get("inference_attempts") != 16
        or effects.get("source_artifacts") != 8
        or effects.get("reused_primary_artifacts") != 8
        or effects.get("model_audio_reads") != 16
        or effects.get("coordinator_audio_reads") != 16
        or effects.get("audio_read_operations") != 32
        or effects.get("audio_writes") != 64
        or any(
            effects.get(key) is not False
            for key in (
                "automatic_retry",
                "public_activation",
                "source_selection",
                "midi_created",
                "hosting",
                "redistribution",
                "audio_upload",
            )
        )
    ):
        raise ValueError("fine-stem integration effects differ")
    return report


__all__ = [
    "ARTIFACT_ROLES",
    "REPORT_SCHEMA",
    "REPORT_STATUS",
    "integration_report_sha256",
    "validate_fine_stem_integration_report",
]
