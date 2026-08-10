"""Pure outcome for the source-visible provider synth presence review."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_synth_provider_qualification import (
    validate_fine_stem_synth_provider_qualification,
)
from .separation_fine_stem_synth_provider_review import validate_provider_review


OUTCOME_SCHEMA = "sunofriend.fine-stem-synth-provider-presence-outcome.v1"
READY_STATUS = "four_provider_synth_estimates_present_plan_ready"
INCOMPLETE_STATUS = "provider_target_presence_incomplete_no_automatic_retry"


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


def build_fine_stem_synth_provider_outcome(
    *, report: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    """Record target presence without reading audio or granting execution."""

    objective = validate_fine_stem_synth_provider_qualification(report)
    listening = validate_provider_review(review, objective)
    if listening["status"] != "human_provider_presence_review_complete_no_selection":
        raise ValueError("provider presence review is incomplete")
    reviews = {case["case_id"]: case for case in listening["cases"]}
    decisions = [
        reviews[case["case_id"]]["provider_target_presence"]
        for case in objective["cases"]
    ]
    present = decisions.count("present")
    ready = present == len(objective["cases"])
    document: dict[str, Any] = {
        "schema": OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": READY_STATUS if ready else INCOMPLETE_STATUS,
        "qualification_document_sha256": objective["document_sha256"],
        "request_document_sha256": objective["request_document_sha256"],
        "review_document_sha256": listening["document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "provider_target_presence": reviews[case["case_id"]][
                    "provider_target_presence"
                ],
                "provider_role_breadth": reviews[case["case_id"]][
                    "provider_role_breadth"
                ],
                "qualifies_for_same_transcriber_arm": reviews[case["case_id"]][
                    "provider_target_presence"
                ]
                == "present",
            }
            for case in objective["cases"]
        ],
        "summary": {
            "decision_counts": dict(sorted(Counter(decisions).items())),
            "confirmed_present_count": present,
            "required_present_count": len(objective["cases"]),
            "ready_for_exact_12_attempt_plan": ready,
            "automatic_retry": False,
        },
        "decision": {
            "next_step": (
                "build exact source-visible three-arm same-transcriber plan"
                if ready
                else "retain outcome and request a separately bounded provider replacement only if useful"
            ),
            "poor_musical_feedback_blocks_core_four": False,
            "provider_label_alone_proves_presence": False,
            "provider_estimate_is_ground_truth": False,
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
            "training_started": False,
            "automatic_retry": False,
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
            "training_attempts": 0,
        },
    }
    document["document_sha256"] = outcome_document_sha256(document)
    return document


def validate_fine_stem_synth_provider_outcome(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != OUTCOME_SCHEMA
        or document.get("status") not in {READY_STATUS, INCOMPLETE_STATUS}
        or document.get("document_sha256") != outcome_document_sha256(document)
    ):
        raise ValueError("provider presence outcome identity differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("provider presence outcome cases differ")
    if len({case.get("case_id") for case in cases}) != 4:
        raise ValueError("provider presence outcome case identities differ")
    decisions = [case.get("provider_target_presence") for case in cases]
    present = decisions.count("present")
    ready = present == 4
    if (
        document["status"] != (READY_STATUS if ready else INCOMPLETE_STATUS)
        or document.get("summary", {}).get("confirmed_present_count") != present
        or document.get("summary", {}).get("ready_for_exact_12_attempt_plan")
        is not ready
        or any(
            case.get("qualifies_for_same_transcriber_arm")
            is not (case.get("provider_target_presence") == "present")
            for case in cases
        )
    ):
        raise ValueError("provider presence outcome decision differs")
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
            "training_started",
            "automatic_retry",
        )
    ):
        raise ValueError("provider presence outcome grants permission")
    if any(bool(effect) for effect in document.get("effects", {}).values()):
        raise ValueError("provider presence outcome contains effects")
    return document


__all__ = [
    "INCOMPLETE_STATUS",
    "OUTCOME_SCHEMA",
    "READY_STATUS",
    "build_fine_stem_synth_provider_outcome",
    "outcome_document_sha256",
    "validate_fine_stem_synth_provider_outcome",
]
