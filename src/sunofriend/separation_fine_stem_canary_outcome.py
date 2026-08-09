"""Pure portfolio outcome for completed synth and guitar canary reviews."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_canary_contract import (
    MAXIMUM_CASES,
    validate_fine_stem_canary_report,
)
from .separation_fine_stem_canary_review import validate_fine_stem_canary_review


PORTFOLIO_OUTCOME_SCHEMA = "sunofriend.fine-stem-canary-portfolio-outcome.v1"
PORTFOLIO_OUTCOME_STATUS = "private_studio_integration_qualified"
SUCCESS_THRESHOLD = 0.60
EXPECTED_PROFILES = {
    "synth": "bs-roformer-mega-53-synth-v1",
    "guitar": "bs-roformer-sw-guitar-v1",
}


def portfolio_outcome_document_sha256(value: Mapping[str, Any]) -> str:
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


def _target_outcome(
    report: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    objective = validate_fine_stem_canary_report(report)
    listening = validate_fine_stem_canary_review(review, objective)
    role = objective["target_role"]
    if (
        EXPECTED_PROFILES.get(role) != objective["profile_id"]
        or listening["status"] != "human_listening_complete_no_selection"
        or len(listening["cases"]) != MAXIMUM_CASES
    ):
        raise ValueError("fine-stem portfolio target binding differs")
    usefulness = Counter(case["usefulness"] for case in listening["cases"])
    catastrophic = Counter(
        case["catastrophic_result"] for case in listening["cases"]
    )
    issues = {
        issue: dict(sorted(Counter(case["issues"][issue] for case in listening["cases"]).items()))
        for issue in (
            "bleed",
            "missing_content",
            "artefacts",
            "timing_or_join_problems",
        )
    }
    success_count = usefulness["useful"] + usefulness["partly_useful"]
    success_fraction = success_count / MAXIMUM_CASES
    qualifies = (
        success_fraction >= SUCCESS_THRESHOLD
        and catastrophic["catastrophic_defect"] == 0
    )
    return {
        "profile_id": objective["profile_id"],
        "target_role": role,
        "report_sha256": objective["report_sha256"],
        "review_document_sha256": listening["document_sha256"],
        "confirmed_present_case_count": MAXIMUM_CASES,
        "song_disjoint": objective["plan"]["execution"]["song_disjoint"],
        "usefulness_counts": dict(sorted(usefulness.items())),
        "catastrophic_counts": dict(sorted(catastrophic.items())),
        "issue_counts": issues,
        "successful_case_count": success_count,
        "success_fraction_all_present": success_fraction,
        "success_threshold": SUCCESS_THRESHOLD,
        "qualifies_for_private_studio_integration": qualifies,
        "downstream_midi_tested": any(
            case["downstream_midi"] != "not_tested" for case in listening["cases"]
        ),
    }


def build_fine_stem_portfolio_outcome(
    *,
    synth_report: Mapping[str, Any],
    synth_review: Mapping[str, Any],
    guitar_report: Mapping[str, Any],
    guitar_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Record usefulness without selecting, activating or starting MIDI."""

    targets = [
        _target_outcome(synth_report, synth_review),
        _target_outcome(guitar_report, guitar_review),
    ]
    if [target["target_role"] for target in targets] != ["synth", "guitar"]:
        raise ValueError("fine-stem portfolio target order differs")
    both_qualified = all(
        target["qualifies_for_private_studio_integration"] for target in targets
    )
    document: dict[str, Any] = {
        "schema": PORTFOLIO_OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": (
            PORTFOLIO_OUTCOME_STATUS
            if both_qualified
            else "private_challenger_evidence_recorded"
        ),
        "success_definition": {
            "minimum_useful_or_partly_useful_fraction": SUCCESS_THRESHOLD,
            "denominator": "all four confirmed-present song-disjoint cases",
            "catastrophic_defect_allowed": False,
            "reconstruction_accounting_is_separation_accuracy": False,
        },
        "targets": targets,
        "both_targets_qualified": both_qualified,
        "next_bounded_step": (
            "mixture-consistent vocals/drums/bass/synth/guitar/residual-other "
            "private Studio integration canary"
        ),
        "known_limitations": [
            "review reported some target content remaining in the residual for all synth cases",
            "review reported some target content remaining in the residual for three guitar cases",
            "downstream MIDI usefulness was not tested",
            "the two target models have not yet been reconciled into one mutually exclusive six-role output",
        ],
        "boundaries": {
            "private_studio_evidence_only": True,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
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
    document["document_sha256"] = portfolio_outcome_document_sha256(document)
    return document


def validate_fine_stem_portfolio_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema") != PORTFOLIO_OUTCOME_SCHEMA:
        raise ValueError("fine-stem portfolio outcome schema differs")
    if value.get("document_sha256") != portfolio_outcome_document_sha256(value):
        raise ValueError("fine-stem portfolio outcome hash differs")
    if [target.get("target_role") for target in value.get("targets", [])] != [
        "synth",
        "guitar",
    ]:
        raise ValueError("fine-stem portfolio outcome targets differ")
    if any(bool(item) for item in value.get("effects", {}).values()):
        raise ValueError("fine-stem portfolio outcome contains effects")
    expected_status = (
        PORTFOLIO_OUTCOME_STATUS
        if value.get("both_targets_qualified") is True
        else "private_challenger_evidence_recorded"
    )
    if value.get("status") != expected_status:
        raise ValueError("fine-stem portfolio outcome status differs")
    return copy.deepcopy(dict(value))


__all__ = [
    "EXPECTED_PROFILES",
    "PORTFOLIO_OUTCOME_SCHEMA",
    "PORTFOLIO_OUTCOME_STATUS",
    "SUCCESS_THRESHOLD",
    "build_fine_stem_portfolio_outcome",
    "portfolio_outcome_document_sha256",
    "validate_fine_stem_portfolio_outcome",
]
