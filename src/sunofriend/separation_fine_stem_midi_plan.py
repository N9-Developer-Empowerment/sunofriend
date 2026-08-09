"""No-effects plan for testing whether fine stems improve editable MIDI.

The plan binds the completed six-role integration report and outcome.  It does
not open audio, construct a model, run inference, transcribe MIDI or select a
source.  A later, separately approved executor can materialise the exact A/B
comparison described here.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_integration_outcome import (
    QUALIFIED_STATUS,
    validate_fine_stem_integration_outcome,
)
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)


MIDI_PLAN_SCHEMA = "sunofriend.fine-stem-downstream-midi-plan.v1"
MIDI_PLAN_STATUS = "ready_for_explicit_private_midi_canary_approval"
TARGET_ROLES = ("synth", "guitar")

# These values come from the already authorised source-export metadata used to
# select the frozen windows.  Repeated tracks deliberately share one entry.
TRACK_METADATA: dict[str, dict[str, Any]] = {
    "be-alone": {"bpm": 136.0, "key": "G# minor", "tuning_hz": 440.0},
    "i-am-a-alien-mashup": {
        "bpm": 114.0,
        "key": "Eb minor",
        "tuning_hz": 440.0,
    },
    "tell-me-that-i-do-it-bitch": {
        "bpm": 129.0,
        "key": "C# minor",
        "tuning_hz": 440.0,
    },
    "uni-ava": {"bpm": 123.0, "key": "G major", "tuning_hz": 440.0},
    "in-the-way": {"bpm": 90.0, "key": "Bb minor", "tuning_hz": 440.0},
    "mauvais-djo-pile": {
        "bpm": 130.0,
        "key": "Bb minor",
        "tuning_hz": 440.0,
    },
    "like-fire": {"bpm": 128.0, "key": "Bb major", "tuning_hz": 440.0},
}


def midi_plan_document_sha256(value: Mapping[str, Any]) -> str:
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


def _artifact_identity(case: Mapping[str, Any], role: str) -> dict[str, Any]:
    artifact = case["artifacts"][role]
    return {
        "role": role,
        "relative_path": artifact["relative_path"],
        "bytes": artifact["bytes"],
        "sha256": artifact["sha256"],
        "sample_rate_hz": artifact["sample_rate_hz"],
        "channels": artifact["channels"],
        "frames": artifact["frames"],
        "subtype": artifact["subtype"],
    }


def _case_plan(case: Mapping[str, Any]) -> dict[str, Any]:
    role = case["reused_primary_role"]
    if role not in TARGET_ROLES:
        raise ValueError("fine-stem MIDI target role differs")
    metadata = TRACK_METADATA.get(case["track_id"])
    if metadata is None:
        raise ValueError("fine-stem MIDI track metadata is missing")
    if role == "synth":
        transcription = {
            "public_role": "synth",
            "source_folder_token": "synth",
            "processing_kind": "synth",
            "general_midi_channel": 5,
            "general_midi_program_zero_based": 81,
            "starter_sound": "Flow Synth Pluck",
        }
    else:
        transcription = {
            "public_role": "guitar",
            "source_folder_token": "rhythm",
            "processing_kind": "keys",
            "general_midi_channel": 8,
            "general_midi_program_zero_based": 27,
            "starter_sound": "Electric Guitar (clean)",
            "known_limitation": (
                "the first guitar candidate uses the conservative polyphonic "
                "keys transcriber; it is not guitar-technique recognition"
            ),
        }
    return {
        "case_id": case["case_id"],
        "track_id": case["track_id"],
        "title": case["title"],
        "window_seconds": case["window_seconds"],
        "confirmed_present_target_role": role,
        "metadata": {
            **metadata,
            "evidence": "already authorised source-export metadata",
            "guessed": False,
        },
        "candidate": _artifact_identity(case, role),
        "grouped_other_control_inputs": [
            _artifact_identity(case, input_role)
            for input_role in ("synth", "guitar", "other")
        ],
        "grouped_other_control": {
            "construction": (
                "sample-exact PCM24 sum of persisted synth, guitar and "
                "residual-other estimates"
            ),
            "maximum_permitted_reconstruction_error_lsb": 0,
            "separator_inference_required": False,
        },
        "transcription": transcription,
        "comparison": {
            "same_transcriber_and_parameters": True,
            "same_bpm_key_tuning_and_window": True,
            "candidate_and_control_loudness_matched_for_review": True,
            "blind_order": (
                "deterministic SHA-256 ordering bound to case_id and seed 0"
            ),
            "automatic_winner_selection": False,
        },
    }


def build_fine_stem_midi_plan(
    *, report: Mapping[str, Any], outcome: Mapping[str, Any]
) -> dict[str, Any]:
    """Create a fully bound plan without reading any referenced audio."""

    objective = validate_fine_stem_integration_report(report)
    result = validate_fine_stem_integration_outcome(outcome)
    if result["status"] != QUALIFIED_STATUS:
        raise ValueError("private six-role integration is not qualified")
    if result["report_sha256"] != objective["report_sha256"]:
        raise ValueError("fine-stem MIDI outcome/report binding differs")
    if result["plan_sha256"] != objective["plan_sha256"]:
        raise ValueError("fine-stem MIDI source plan binding differs")
    cases = [_case_plan(case) for case in objective["cases"]]
    if [case["confirmed_present_target_role"] for case in cases].count("synth") != 4:
        raise ValueError("fine-stem MIDI synth cohort differs")
    if [case["confirmed_present_target_role"] for case in cases].count("guitar") != 4:
        raise ValueError("fine-stem MIDI guitar cohort differs")

    plan: dict[str, Any] = {
        "schema": MIDI_PLAN_SCHEMA,
        "document_sha256": "",
        "status": MIDI_PLAN_STATUS,
        "created_on": "2026-08-09",
        "integration_plan_sha256": objective["plan_sha256"],
        "integration_report_sha256": objective["report_sha256"],
        "integration_review_document_sha256": result["review_document_sha256"],
        "integration_outcome_document_sha256": result["document_sha256"],
        "scope": {
            "purpose": (
                "measure whether the isolated synth or guitar estimate makes "
                "a more useful editable MIDI interpretation than grouped other"
            ),
            "confirmed_present_cases_per_role": 4,
            "target_roles": [*TARGET_ROLES],
            "separator_rerun": False,
            "checkpoint_reload": False,
            "automatic_retry": False,
        },
        "cases": cases,
        "review_schema": {
            "per_case_fields": [
                "recognisable_notes",
                "timing_usefulness",
                "edit_workload",
                "candidate_vs_control",
                "notes",
            ],
            "allowed_comparison_results": [
                "candidate_better",
                "control_better",
                "same",
                "cannot_tell",
                "not_tested",
            ],
            "cannot_tell_is_valid": True,
            "not_tested_is_valid": True,
            "minimum_usefulness_rating_for_profile_retention": None,
            "negative_feedback_disables_six_role_profile": False,
            "review_selects_source_automatically": False,
        },
        "decision_policy": {
            "profile_retention": (
                "the private six-role evidence remains available regardless "
                "of MIDI usefulness"
            ),
            "product_integration": (
                "human comparison informs a later explicit Studio/Create "
                "decision; this plan cannot make that decision"
            ),
            "poor_result": (
                "record the limitation and test one bounded transcription "
                "challenger without rerunning separation"
            ),
        },
        "permissions_required_for_execution": [
            "read the 24 bound private PCM24 synth, guitar and other artifacts",
            "write eight temporary grouped-other controls",
            "run exactly 16 local MIDI transcription attempts",
            "write private MIDI, neutral preview audio and a review page",
        ],
        "boundaries": {
            "plan_only": True,
            "private_audio_opened": False,
            "separator_model_loaded": False,
            "separator_inference_run": False,
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
        },
    }
    plan["document_sha256"] = midi_plan_document_sha256(plan)
    return plan


def validate_fine_stem_midi_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    plan = copy.deepcopy(dict(value))
    if plan.get("schema") != MIDI_PLAN_SCHEMA or plan.get("status") != MIDI_PLAN_STATUS:
        raise ValueError("fine-stem MIDI plan identity differs")
    if plan.get("document_sha256") != midi_plan_document_sha256(plan):
        raise ValueError("fine-stem MIDI plan hash differs")
    cases = plan.get("cases")
    if not isinstance(cases, list) or len(cases) != 8:
        raise ValueError("fine-stem MIDI plan cases differ")
    if len({case.get("case_id") for case in cases}) != 8:
        raise ValueError("fine-stem MIDI plan case identities differ")
    if any(bool(effect) for effect in plan.get("effects", {}).values()):
        raise ValueError("fine-stem MIDI plan contains effects")
    boundaries = plan.get("boundaries", {})
    if boundaries.get("plan_only") is not True or any(
        boundaries.get(key) is not False
        for key in (
            "private_audio_opened",
            "separator_model_loaded",
            "separator_inference_run",
            "midi_created",
            "source_selected",
            "public_activation",
            "hosting",
            "redistribution",
            "audio_upload",
        )
    ):
        raise ValueError("fine-stem MIDI plan grants permission")
    for case in cases:
        if case.get("metadata", {}).get("guessed") is not False:
            raise ValueError("fine-stem MIDI plan contains guessed metadata")
        if len(case.get("grouped_other_control_inputs", [])) != 3:
            raise ValueError("fine-stem MIDI grouped-other inputs differ")
        if case.get("candidate", {}).get("role") != case.get(
            "confirmed_present_target_role"
        ):
            raise ValueError("fine-stem MIDI candidate role differs")
    return plan


__all__ = [
    "MIDI_PLAN_SCHEMA",
    "MIDI_PLAN_STATUS",
    "TARGET_ROLES",
    "TRACK_METADATA",
    "build_fine_stem_midi_plan",
    "midi_plan_document_sha256",
    "validate_fine_stem_midi_plan",
]
