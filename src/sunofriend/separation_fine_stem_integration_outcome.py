"""Pure musical outcome for one completed private six-role integration review."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_canary_outcome import SUCCESS_THRESHOLD
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_integration_review import validate_integration_review


INTEGRATION_OUTCOME_SCHEMA = (
    "sunofriend.fine-stem-six-role-integration-outcome.v1"
)
QUALIFIED_STATUS = "private_six_role_integration_qualified"
RETAINED_STATUS = "private_six_role_integration_evidence_recorded"
TARGET_ROLES = ("synth", "guitar")


def integration_outcome_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _role_outcome(
    role: str,
    report_cases: list[Mapping[str, Any]],
    reviews_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    present_cases = [
        case for case in report_cases if case["reused_primary_role"] == role
    ]
    if len(present_cases) != 4:
        raise ValueError("fine-stem integration present-role cohort differs")
    reviewed = [reviews_by_id[case["case_id"]] for case in present_cases]
    usefulness = _counts([case["usefulness"][role] for case in reviewed])
    catastrophic = _counts(
        [case["catastrophic_result"] for case in reviewed]
    )
    issues = {
        issue: _counts([case["issues"][role][issue] for case in reviewed])
        for issue in (
            "bleed",
            "missing_content",
            "artefacts",
            "timing_or_join_problems",
        )
    }
    successful = usefulness.get("useful", 0) + usefulness.get(
        "partly_useful", 0
    )
    fraction = successful / len(reviewed)
    qualifies = (
        fraction >= SUCCESS_THRESHOLD
        and catastrophic.get("catastrophic_defect", 0) == 0
    )
    return {
        "target_role": role,
        "presence_basis": (
            "reused primary estimate from the exact confirmed-present "
            "four-song canary cohort"
        ),
        "case_ids": [case["case_id"] for case in present_cases],
        "confirmed_present_case_count": len(present_cases),
        "usefulness_counts": usefulness,
        "catastrophic_counts": catastrophic,
        "issue_counts": issues,
        "successful_case_count": successful,
        "success_fraction_all_present": fraction,
        "success_threshold": SUCCESS_THRESHOLD,
        "qualifies_for_private_six_role_integration": qualifies,
    }


def build_fine_stem_integration_outcome(
    *, report: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Reduce exact human feedback without selecting or activating a profile."""

    objective = validate_fine_stem_integration_report(report)
    listening = validate_integration_review(review, objective)
    if listening["status"] != "human_listening_complete_no_selection":
        raise ValueError("fine-stem integration listening is incomplete")
    reviews_by_id = {case["case_id"]: case for case in listening["cases"]}
    report_cases = objective["cases"]
    targets = [
        _role_outcome(role, report_cases, reviews_by_id) for role in TARGET_ROLES
    ]
    all_outputs_noncatastrophic = all(
        case["catastrophic_result"] != "catastrophic_defect"
        for case in listening["cases"]
    )
    both_qualified = all(
        target["qualifies_for_private_six_role_integration"]
        for target in targets
    )
    reconstruction_errors = [
        case["maximum_reconstruction_error_lsb"] for case in report_cases
    ]
    qualified = (
        both_qualified
        and all_outputs_noncatastrophic
        and max(reconstruction_errors) <= 2
    )
    document: dict[str, Any] = {
        "schema": INTEGRATION_OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": QUALIFIED_STATUS if qualified else RETAINED_STATUS,
        "report_sha256": objective["report_sha256"],
        "review_document_sha256": listening["document_sha256"],
        "plan_sha256": objective["plan_sha256"],
        "success_definition": {
            "minimum_useful_or_partly_useful_fraction": SUCCESS_THRESHOLD,
            "denominator": (
                "the four exact confirmed-present cases for each target role"
            ),
            "catastrophic_defect_allowed": False,
            "maximum_reconstruction_error_lsb": 2,
            "ratings_for_an_absent_role_are_scored": False,
            "reconstruction_accounting_is_separation_accuracy": False,
        },
        "targets": targets,
        "both_targets_qualified": both_qualified,
        "all_eight_outputs_noncatastrophic": all_outputs_noncatastrophic,
        "maximum_reconstruction_error_lsb": max(reconstruction_errors),
        "qualified_for_private_six_role_integration": qualified,
        "next_bounded_step": (
            "private downstream MIDI usefulness canary on exact role-present "
            "artifacts, followed by explicit Studio product-integration review"
        ),
        "known_limitations": [
            (
                "synth was only partly useful in two of four exact "
                "confirmed-present integration cases"
            ),
            (
                "three of four exact confirmed-present synth cases reported "
                "some synth content remaining outside the synth estimate"
            ),
            (
                "ratings for complementary roles on source-absent windows are "
                "retained as context and excluded from qualification"
            ),
            "downstream MIDI usefulness has not been tested",
            (
                "checkpoint terms and resource limits still prevent a public "
                "six-role product claim"
            ),
        ],
        "boundaries": {
            "private_studio_evidence_only": True,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
            "poor_feedback_disables_core_four": False,
        },
        "effects": {
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "inference_attempts": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "network_attempts": 0,
        },
    }
    document["document_sha256"] = integration_outcome_document_sha256(
        document
    )
    return document


def validate_fine_stem_integration_outcome(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if document.get("schema") != INTEGRATION_OUTCOME_SCHEMA:
        raise ValueError("fine-stem integration outcome schema differs")
    if document.get("document_sha256") != integration_outcome_document_sha256(
        document
    ):
        raise ValueError("fine-stem integration outcome hash differs")
    if [target.get("target_role") for target in document.get("targets", [])] != [
        *TARGET_ROLES
    ]:
        raise ValueError("fine-stem integration outcome targets differ")
    if any(bool(effect) for effect in document.get("effects", {}).values()):
        raise ValueError("fine-stem integration outcome contains effects")
    qualified = (
        document.get("qualified_for_private_six_role_integration") is True
    )
    expected_status = QUALIFIED_STATUS if qualified else RETAINED_STATUS
    if document.get("status") != expected_status:
        raise ValueError("fine-stem integration outcome status differs")
    if any(
        document.get("boundaries", {}).get(key) is not False
        for key in (
            "public_activation",
            "source_selection",
            "midi_created",
            "hosting",
            "redistribution",
            "audio_upload",
        )
    ):
        raise ValueError("fine-stem integration outcome grants permission")
    return document


__all__ = [
    "INTEGRATION_OUTCOME_SCHEMA",
    "QUALIFIED_STATUS",
    "RETAINED_STATUS",
    "TARGET_ROLES",
    "build_fine_stem_integration_outcome",
    "integration_outcome_document_sha256",
    "validate_fine_stem_integration_outcome",
]
