"""Pure outcome for one completed fine-stem downstream-MIDI review."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_midi_canary import (
    validate_fine_stem_midi_canary,
)
from .separation_fine_stem_midi_review import validate_midi_review


MIDI_OUTCOME_SCHEMA = "sunofriend.fine-stem-downstream-midi-outcome.v1"
METHODOLOGY_LIMITED_STATUS = "private_midi_evidence_recorded_source_reference_limited"
TARGET_ROLES = ("synth", "guitar")


def midi_outcome_document_sha256(value: Mapping[str, Any]) -> str:
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
    cohort = [
        case for case in report_cases if case["confirmed_present_target_role"] == role
    ]
    if len(cohort) != 4:
        raise ValueError("fine-stem MIDI outcome role cohort differs")
    reviewed = [reviews_by_id[case["case_id"]] for case in cohort]
    comparison = _counts([case["candidate_vs_control"] for case in reviewed])
    candidate_better = comparison.get("candidate_better", 0)
    if candidate_better >= 3:
        directional_result = "directional_isolated_stem_benefit_private_only"
    elif candidate_better == 0:
        directional_result = "no_isolated_stem_advantage_observed"
    else:
        directional_result = "mixed_isolated_stem_result"
    return {
        "target_role": role,
        "case_ids": [case["case_id"] for case in cohort],
        "confirmed_present_case_count": len(cohort),
        "recognisable_notes_counts": _counts(
            [case["recognisable_notes"] for case in reviewed]
        ),
        "timing_usefulness_counts": _counts(
            [case["timing_usefulness"] for case in reviewed]
        ),
        "edit_workload_counts": _counts([case["edit_workload"] for case in reviewed]),
        "candidate_vs_control_counts": comparison,
        "candidate_better_case_count": candidate_better,
        "directional_result": directional_result,
        "qualifies_for_source_selection_or_public_promotion": False,
    }


def build_fine_stem_midi_outcome(
    *,
    report: Mapping[str, Any],
    review: Mapping[str, Any],
    source_reference_present_during_completed_review: bool,
    repaired_page_source_reference_present: bool,
) -> dict[str, Any]:
    """Reduce exact feedback without reading audio or granting MIDI authority."""

    objective = validate_fine_stem_midi_canary(report)
    listening = validate_midi_review(review, objective)
    if listening["status"] != "human_listening_complete_no_selection":
        raise ValueError("fine-stem MIDI listening is incomplete")
    if source_reference_present_during_completed_review:
        raise ValueError("this outcome schema is for the source-omitted review")
    if not repaired_page_source_reference_present:
        raise ValueError("the repaired MIDI review source reference is absent")

    reviews_by_id = {case["case_id"]: case for case in listening["cases"]}
    targets = [
        _role_outcome(role, objective["cases"], reviews_by_id) for role in TARGET_ROLES
    ]
    target_by_role = {target["target_role"]: target for target in targets}
    document: dict[str, Any] = {
        "schema": MIDI_OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": METHODOLOGY_LIMITED_STATUS,
        "canary_document_sha256": objective["document_sha256"],
        "plan_document_sha256": objective["plan"]["document_sha256"],
        "review_document_sha256": listening["document_sha256"],
        "methodology": {
            "source_reference_present_during_completed_review": False,
            "repaired_page_source_reference_present": True,
            "saved_answers_changed_by_repair": False,
            "result_can_promote_or_select_a_source": False,
            "limitation": (
                "the completed A/B review omitted the exact source mix, so "
                "recognisability and preference are directional private "
                "evidence rather than promotion evidence"
            ),
        },
        "targets": targets,
        "decisions": {
            "synth": {
                "status": "bottleneck_attribution_required",
                "basis": target_by_role["synth"]["directional_result"],
                "next_step": (
                    "one source-present three-arm comparison of the current "
                    "synth estimate, a provider synth-or-keyboard estimate "
                    "and grouped other under the same transcriber"
                ),
            },
            "guitar": {
                "status": "retain_private_studio_challenger_directional_only",
                "basis": target_by_role["guitar"]["directional_result"],
                "next_step": (
                    "retain the private evidence and do not rerun separation "
                    "until a separately bounded guitar-transcriber comparison"
                ),
            },
        },
        "known_limitations": [
            "the completed MIDI page omitted the exact source reference",
            "synth candidate MIDI did not beat grouped other in any of four cases",
            "guitar candidate MIDI was only partly useful in three cases and not useful in one",
            "neutral General MIDI previews do not reproduce source timbre or articulation",
        ],
        "feedback_policy": {
            "poor_or_mixed_feedback_disables_core_four": False,
            "poor_or_mixed_feedback_erases_private_six_role_evidence": False,
            "automatic_retry": False,
            "automatic_winner_selection": False,
        },
        "boundaries": {
            "outcome_only": True,
            "audio_opened": False,
            "separator_model_loaded": False,
            "transcriber_run": False,
            "midi_created": False,
            "source_selected": False,
            "public_activation": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
        "effects": {
            "audio_reads": 0,
            "audio_writes": 0,
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "separator_inference_attempts": 0,
            "midi_transcription_attempts": 0,
            "midi_writes": 0,
            "network_attempts": 0,
            "source_selections": 0,
            "public_activations": 0,
        },
    }
    document["document_sha256"] = midi_outcome_document_sha256(document)
    return document


def validate_fine_stem_midi_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != MIDI_OUTCOME_SCHEMA
        or document.get("status") != METHODOLOGY_LIMITED_STATUS
        or document.get("document_sha256") != midi_outcome_document_sha256(document)
    ):
        raise ValueError("fine-stem MIDI outcome identity differs")
    if [target.get("target_role") for target in document.get("targets", [])] != [
        *TARGET_ROLES
    ]:
        raise ValueError("fine-stem MIDI outcome targets differ")
    methodology = document.get("methodology", {})
    if (
        methodology.get("source_reference_present_during_completed_review") is not False
        or methodology.get("repaired_page_source_reference_present") is not True
        or methodology.get("result_can_promote_or_select_a_source") is not False
    ):
        raise ValueError("fine-stem MIDI outcome methodology differs")
    if any(bool(effect) for effect in document.get("effects", {}).values()):
        raise ValueError("fine-stem MIDI outcome contains effects")
    boundaries = document.get("boundaries", {})
    if boundaries.get("outcome_only") is not True or any(
        boundaries.get(key) is not False
        for key in (
            "audio_opened",
            "separator_model_loaded",
            "transcriber_run",
            "midi_created",
            "source_selected",
            "public_activation",
            "hosting",
            "redistribution",
            "audio_upload",
        )
    ):
        raise ValueError("fine-stem MIDI outcome grants permission")
    return document


__all__ = [
    "METHODOLOGY_LIMITED_STATUS",
    "MIDI_OUTCOME_SCHEMA",
    "TARGET_ROLES",
    "build_fine_stem_midi_outcome",
    "midi_outcome_document_sha256",
    "validate_fine_stem_midi_outcome",
]
