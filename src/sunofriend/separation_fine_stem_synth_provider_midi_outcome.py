"""Pure outcome for the source-visible three-arm synth MIDI review."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_synth_provider_midi_canary import (
    validate_fine_stem_synth_provider_midi_canary,
)
from .separation_fine_stem_synth_provider_midi_plan import ARM_IDS
from .separation_fine_stem_synth_provider_midi_review import (
    validate_provider_synth_midi_review,
)


OUTCOME_SCHEMA = "sunofriend.fine-stem-synth-provider-midi-outcome.v1"
OUTCOME_STATUS = "private_synth_midi_bottleneck_recorded_no_selection"
_RECOGNISABLE_RANK = {
    "not_useful": 0,
    "partly_useful": 1,
    "useful": 2,
}


def outcome_document_sha256(value: Mapping[str, Any]) -> str:
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


def _recognisable_comparison(current: str, provider: str) -> str:
    current_rank = _RECOGNISABLE_RANK.get(current)
    provider_rank = _RECOGNISABLE_RANK.get(provider)
    if current_rank is None or provider_rank is None:
        return "inconclusive"
    if current_rank > provider_rank:
        return "current_separator_better"
    if current_rank < provider_rank:
        return "provider_estimate_better"
    return "tie"


def build_fine_stem_synth_provider_midi_outcome(
    *, report: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Reduce the completed review without opening audio or granting authority."""

    objective = validate_fine_stem_synth_provider_midi_canary(report)
    listening = validate_provider_synth_midi_review(review, objective)
    if listening["status"] != "human_three_arm_listening_complete_no_selection":
        raise ValueError("provider synth MIDI listening is incomplete")

    reviews_by_id = {case["case_id"]: case for case in listening["cases"]}
    cases = []
    for objective_case in objective["cases"]:
        reviewed = reviews_by_id[objective_case["case_id"]]
        display_by_arm = {
            output["arm_id"]: display_id
            for display_id, output in objective_case["outputs"].items()
        }
        if set(display_by_arm) != set(ARM_IDS):
            raise ValueError("provider synth MIDI outcome arm mapping differs")
        ratings_by_arm = {
            arm_id: dict(reviewed["ratings"][display_by_arm[arm_id]])
            for arm_id in ARM_IDS
        }
        best_display = reviewed["best_display"]
        best_arm = (
            objective_case["outputs"][best_display]["arm_id"]
            if best_display in {"A", "B", "C"}
            else best_display
        )
        cases.append(
            {
                "case_id": objective_case["case_id"],
                "ratings_by_arm": ratings_by_arm,
                "best_arm": best_arm,
                "current_vs_provider_recognisable": _recognisable_comparison(
                    ratings_by_arm["current_separator_estimate"][
                        "recognisable_notes"
                    ],
                    ratings_by_arm["provider_synth_estimate"][
                        "recognisable_notes"
                    ],
                ),
                "notes_recorded": bool(reviewed["notes"].strip()),
            }
        )

    arm_aggregates = []
    for arm_id in ARM_IDS:
        ratings = [case["ratings_by_arm"][arm_id] for case in cases]
        arm_aggregates.append(
            {
                "arm_id": arm_id,
                "best_case_count": sum(case["best_arm"] == arm_id for case in cases),
                "recognisable_notes_counts": _counts(
                    [rating["recognisable_notes"] for rating in ratings]
                ),
                "timing_usefulness_counts": _counts(
                    [rating["timing_usefulness"] for rating in ratings]
                ),
                "edit_workload_counts": _counts(
                    [rating["edit_workload"] for rating in ratings]
                ),
            }
        )
    comparison_counts = _counts(
        [case["current_vs_provider_recognisable"] for case in cases]
    )
    grouped_best_count = sum(
        case["best_arm"] == "grouped_other_control" for case in cases
    )

    document: dict[str, Any] = {
        "schema": OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": OUTCOME_STATUS,
        "canary_document_sha256": objective["document_sha256"],
        "plan_document_sha256": objective["plan"]["document_sha256"],
        "review_document_sha256": listening["document_sha256"],
        "methodology": {
            "source_reference_present_during_completed_review": True,
            "blind_display_order": True,
            "same_transcriber_parameters_for_all_arms": True,
            "provider_presence_outcome_bound": True,
            "provider_estimates_are_comparison_estimates_not_truth": True,
            "grouped_other_is_not_an_isolated_synth_reference": True,
            "result_can_promote_or_select_a_source": False,
        },
        "cases": cases,
        "arm_aggregates": arm_aggregates,
        "summary": {
            "reviewed_case_count": len(cases),
            "grouped_other_best_case_count": grouped_best_count,
            "isolated_arm_best_case_count": len(cases) - grouped_best_count,
            "current_vs_provider_recognisable_counts": comparison_counts,
            "result": "no_isolated_synth_midi_advantage_over_grouped_other_observed",
        },
        "decisions": {
            "audio_stem_evidence": {
                "status": "retain_private_six_role_audio_evidence",
                "basis": (
                    "MIDI usefulness is a separate downstream decision and does not "
                    "veto the completed human-reviewed synth audio evidence"
                ),
            },
            "midi": {
                "status": "retain_grouped_other_control_no_automatic_choice",
                "basis": "grouped other was the explicit best display in all four cases",
            },
            "separator_attribution": {
                "status": "provider_replacement_not_supported",
                "basis": (
                    "the current separator was recognisably better than the provider "
                    "estimate twice and tied it twice under the frozen transcriber"
                ),
            },
            "next_step": {
                "status": "separate_audio_stem_admission_from_midi_method_choice",
                "basis": (
                    "proceed with bounded private Studio packaging for qualified synth "
                    "audio while keeping grouped other available for MIDI"
                ),
            },
        },
        "known_limitations": [
            "provider stems are comparison estimates rather than reference truth",
            "grouped other can contain pitched non-synth material",
            "neutral General MIDI previews do not reproduce source timbre or articulation",
            "four confirmed-present excerpts are directional private evidence, not a public default",
        ],
        "feedback_policy": {
            "poor_or_mixed_midi_feedback_disables_core_four": False,
            "poor_or_mixed_midi_feedback_erases_private_six_role_audio_evidence": False,
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
    document["document_sha256"] = outcome_document_sha256(document)
    return document


def validate_fine_stem_synth_provider_midi_outcome(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != OUTCOME_SCHEMA
        or document.get("status") != OUTCOME_STATUS
        or document.get("document_sha256") != outcome_document_sha256(document)
    ):
        raise ValueError("provider synth MIDI outcome identity differs")
    cases = document.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != 4
        or len({case.get("case_id") for case in cases}) != 4
        or any(set(case.get("ratings_by_arm", {})) != set(ARM_IDS) for case in cases)
    ):
        raise ValueError("provider synth MIDI outcome cases differ")
    aggregates = document.get("arm_aggregates")
    if (
        not isinstance(aggregates, list)
        or [aggregate.get("arm_id") for aggregate in aggregates] != list(ARM_IDS)
        or sum(aggregate.get("best_case_count", -1) for aggregate in aggregates) != 4
    ):
        raise ValueError("provider synth MIDI outcome aggregates differ")
    summary = document.get("summary", {})
    if (
        summary.get("reviewed_case_count") != 4
        or summary.get("grouped_other_best_case_count") != 4
        or summary.get("isolated_arm_best_case_count") != 0
        or summary.get("result")
        != "no_isolated_synth_midi_advantage_over_grouped_other_observed"
    ):
        raise ValueError("provider synth MIDI outcome summary differs")
    methodology = document.get("methodology", {})
    if (
        methodology.get("source_reference_present_during_completed_review") is not True
        or methodology.get("blind_display_order") is not True
        or methodology.get("same_transcriber_parameters_for_all_arms") is not True
        or methodology.get("result_can_promote_or_select_a_source") is not False
    ):
        raise ValueError("provider synth MIDI outcome methodology differs")
    if any(bool(effect) for effect in document.get("effects", {}).values()):
        raise ValueError("provider synth MIDI outcome contains effects")
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
        raise ValueError("provider synth MIDI outcome grants permission")
    return document


__all__ = [
    "OUTCOME_SCHEMA",
    "OUTCOME_STATUS",
    "build_fine_stem_synth_provider_midi_outcome",
    "outcome_document_sha256",
    "validate_fine_stem_synth_provider_midi_outcome",
]
