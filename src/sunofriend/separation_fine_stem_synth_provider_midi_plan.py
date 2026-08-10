"""No-effects exact plan for the three-arm provider synth MIDI comparison."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_synth_bottleneck_plan import (
    validate_fine_stem_synth_bottleneck_plan,
)
from .separation_fine_stem_synth_provider_outcome import (
    READY_STATUS,
    validate_fine_stem_synth_provider_outcome,
)
from .separation_fine_stem_synth_provider_qualification import (
    validate_fine_stem_synth_provider_qualification,
)


MIDI_PLAN_SCHEMA = "sunofriend.fine-stem-synth-provider-midi-plan.v1"
MIDI_PLAN_STATUS = "awaiting_explicit_exact_12_attempt_private_midi_approval"
ARM_IDS = (
    "current_separator_estimate",
    "provider_synth_estimate",
    "grouped_other_control",
)


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


def _blind_order(request_sha256: str, case_id: str) -> list[str]:
    return sorted(
        ARM_IDS,
        key=lambda arm: hashlib.sha256(
            f"{request_sha256}:{case_id}:{arm}".encode("utf-8")
        ).digest(),
    )


def _provider_artifact(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "role": "synth",
        **case["artifacts"]["provider_synth"],
    }


def build_fine_stem_synth_provider_midi_plan(
    *,
    request: Mapping[str, Any],
    qualification: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind all 12 future attempts without opening audio or running MIDI."""

    bottleneck = validate_fine_stem_synth_bottleneck_plan(request)
    provider = validate_fine_stem_synth_provider_qualification(qualification)
    presence = validate_fine_stem_synth_provider_outcome(outcome)
    if presence["status"] != READY_STATUS:
        raise ValueError("four provider synth targets are not confirmed present")
    if (
        provider["request_document_sha256"] != bottleneck["document_sha256"]
        or presence["request_document_sha256"] != bottleneck["document_sha256"]
        or presence["qualification_document_sha256"] != provider["document_sha256"]
    ):
        raise ValueError("provider synth MIDI plan binding differs")
    provider_by_id = {case["case_id"]: case for case in provider["cases"]}
    presence_by_id = {case["case_id"]: case for case in presence["cases"]}
    cases = []
    attempts = []
    attempt_number = 0
    for request_case in bottleneck["cases"]:
        case_id = request_case["case_id"]
        provider_case = provider_by_id.get(case_id)
        presence_case = presence_by_id.get(case_id)
        if (
            provider_case is None
            or presence_case is None
            or presence_case["provider_target_presence"] != "present"
            or provider_case["track_id"] != request_case["track_id"]
            or provider_case["window_seconds"] != request_case["window_seconds"]
        ):
            raise ValueError("provider synth MIDI case binding differs")
        arms = {
            "current_separator_estimate": {
                "root_kind": "six_role_integration",
                "artifact": request_case["current_separator_estimate"],
            },
            "provider_synth_estimate": {
                "root_kind": "provider_qualification",
                "artifact": _provider_artifact(provider_case),
            },
            "grouped_other_control": {
                "root_kind": "downstream_midi_canary",
                "artifact": request_case["grouped_other_control"],
            },
        }
        order = _blind_order(bottleneck["document_sha256"], case_id)
        for display_id, arm_id in zip(("A", "B", "C"), order):
            attempt_number += 1
            attempts.append(
                {
                    "attempt_number": attempt_number,
                    "case_id": case_id,
                    "display_id": display_id,
                    "arm_id": arm_id,
                    "root_kind": arms[arm_id]["root_kind"],
                    "processing_kind": request_case["frozen_transcription"][
                        "transcription"
                    ]["processing_kind"],
                }
            )
        cases.append(
            {
                "case_id": case_id,
                "track_id": request_case["track_id"],
                "title": request_case["title"],
                "window_seconds": request_case["window_seconds"],
                "source_reference": {
                    "root_kind": "provider_qualification",
                    "artifact": {
                        "role": "reference",
                        **provider_case["artifacts"]["reference"],
                    },
                },
                "provider_presence_reviewed": True,
                "provider_role_breadth": presence_case["provider_role_breadth"],
                "arms": arms,
                "blind_display_order": order,
                "frozen_transcription": request_case["frozen_transcription"],
            }
        )
    document: dict[str, Any] = {
        "schema": MIDI_PLAN_SCHEMA,
        "document_sha256": "",
        "status": MIDI_PLAN_STATUS,
        "created_on": "2026-08-10",
        "request_document_sha256": bottleneck["document_sha256"],
        "qualification_document_sha256": provider["document_sha256"],
        "presence_outcome_document_sha256": presence["document_sha256"],
        "integration_report_sha256": provider["integration_report_sha256"],
        "purpose": (
            "attribute the remaining synth MIDI bottleneck using the current separator, "
            "one human-confirmed provider estimate and grouped other under one frozen transcriber"
        ),
        "cases": cases,
        "attempts": attempts,
        "execution_contract": {
            "song_disjoint_cases": 4,
            "arms_per_case": 3,
            "exact_midi_transcription_attempt_budget": 12,
            "attempt_numbers": list(range(1, 13)),
            "separator_rerun": False,
            "separator_checkpoint_loads": 0,
            "automatic_retry": False,
            "same_transcriber_bpm_key_tuning_window_and_thresholds": True,
            "private_pcm24_inputs": 12,
            "private_midi_outputs": 12,
            "neutral_preview_outputs": 12,
            "source_reference_visible_during_review": True,
        },
        "review_contract": {
            "blind_display_labels": ["A", "B", "C"],
            "order_derived_from_bound_request_and_case_identity": True,
            "source_reference_visible_and_playable": True,
            "automatic_playback_recording": True,
            "manual_listened_checkbox": False,
            "cannot_tell_and_not_tested_valid": True,
            "automatic_winner_selection": False,
            "review_writes_model_choice": False,
            "poor_feedback_disables_core_four": False,
        },
        "attribution_policy": bottleneck["attribution_policy"],
        "approval_request": (
            "approve one network-denied private 12-attempt same-transcriber synth "
            "comparison bound to this exact plan SHA-256; no separator rerun, automatic "
            "retry, source selection, public activation, hosting, redistribution or upload"
        ),
        "boundaries": {
            "plan_only": True,
            "ready_for_execution_after_explicit_plan_hash_approval": True,
            "private_audio_opened": False,
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
    document["document_sha256"] = midi_plan_document_sha256(document)
    return document


def validate_fine_stem_synth_provider_midi_plan(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != MIDI_PLAN_SCHEMA
        or document.get("status") != MIDI_PLAN_STATUS
        or document.get("document_sha256") != midi_plan_document_sha256(document)
    ):
        raise ValueError("provider synth MIDI plan identity differs")
    cases = document.get("cases")
    attempts = document.get("attempts")
    if (
        not isinstance(cases, list)
        or len(cases) != 4
        or len({case.get("case_id") for case in cases}) != 4
        or not isinstance(attempts, list)
        or len(attempts) != 12
        or [attempt.get("attempt_number") for attempt in attempts] != list(range(1, 13))
    ):
        raise ValueError("provider synth MIDI plan budget differs")
    for case in cases:
        if (
            set(case.get("arms", {})) != set(ARM_IDS)
            or set(case.get("blind_display_order", [])) != set(ARM_IDS)
            or case.get("provider_presence_reviewed") is not True
        ):
            raise ValueError("provider synth MIDI plan arms differ")
    attempts_by_case = {
        case["case_id"]: [
            attempt for attempt in attempts if attempt.get("case_id") == case["case_id"]
        ]
        for case in cases
    }
    if any(
        len(case_attempts) != 3
        or {attempt.get("arm_id") for attempt in case_attempts} != set(ARM_IDS)
        or {attempt.get("display_id") for attempt in case_attempts} != {"A", "B", "C"}
        for case_attempts in attempts_by_case.values()
    ):
        raise ValueError("provider synth MIDI plan attempt mapping differs")
    contract = document.get("execution_contract", {})
    if (
        contract.get("exact_midi_transcription_attempt_budget") != 12
        or contract.get("separator_rerun") is not False
        or contract.get("automatic_retry") is not False
    ):
        raise ValueError("provider synth MIDI execution contract differs")
    boundaries = document.get("boundaries", {})
    if (
        boundaries.get("plan_only") is not True
        or boundaries.get("ready_for_execution_after_explicit_plan_hash_approval")
        is not True
        or any(
            boundaries.get(key) is not False
            for key in (
                "private_audio_opened",
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
        )
    ):
        raise ValueError("provider synth MIDI plan grants permission")
    if any(bool(effect) for effect in document.get("effects", {}).values()):
        raise ValueError("provider synth MIDI plan contains effects")
    return document


__all__ = [
    "ARM_IDS",
    "MIDI_PLAN_SCHEMA",
    "MIDI_PLAN_STATUS",
    "build_fine_stem_synth_provider_midi_plan",
    "midi_plan_document_sha256",
    "validate_fine_stem_synth_provider_midi_plan",
]
