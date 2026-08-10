"""No-effects request for attributing the remaining synth MIDI bottleneck."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_midi_canary import validate_fine_stem_midi_canary
from .separation_fine_stem_midi_outcome import (
    METHODOLOGY_LIMITED_STATUS,
    validate_fine_stem_midi_outcome,
)


SYNTH_BOTTLENECK_PLAN_SCHEMA = "sunofriend.fine-stem-synth-bottleneck-request.v1"
SYNTH_BOTTLENECK_PLAN_STATUS = "awaiting_four_provider_synth_or_keyboard_estimates"
SYNTH_CASE_COUNT = 4


def synth_bottleneck_plan_document_sha256(value: Mapping[str, Any]) -> str:
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


def _artifact_identity(artifact: Mapping[str, Any], *, role: str) -> dict[str, Any]:
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


def _provider_inventory(track_id: str, corpus: Mapping[str, Any]) -> dict[str, Any]:
    tracks = corpus.get("tracks", [])
    match = next(
        (track for track in tracks if track.get("id") == track_id),
        None,
    )
    if match is None:
        return {
            "status": "not_catalogued_in_current_provider_manifest",
            "exact_provider_artifact_bound": False,
            "request": (
                "supply the best available local synth, keyboard or keys "
                "provider estimate for this exact song"
            ),
        }
    cues: list[dict[str, Any]] = []
    if int(match.get("suno", {}).get("packs", 0)) > 0:
        cues.extend(
            [
                {
                    "provider": "Suno",
                    "label": "Synth",
                    "interpretation": "provider estimate, not truth",
                },
                {
                    "provider": "Suno",
                    "label": "Keyboard",
                    "interpretation": "broader provider estimate, not truth",
                },
            ]
        )
    if int(match.get("moises", {}).get("files", 0)) > 0:
        cues.append(
            {
                "provider": "Moises",
                "label": "keys",
                "interpretation": "broader provider estimate, not truth",
            }
        )
    return {
        "status": "provider_pack_catalogued_exact_artifact_not_yet_bound",
        "corpus_directory": match.get("directory"),
        "candidate_labels": cues,
        "exact_provider_artifact_bound": False,
        "selection_policy": (
            "prefer a discrete synth estimate; otherwise use the broadest "
            "keyboard or keys estimate and disclose its overlap"
        ),
    }


def _case_plan(
    midi_case: Mapping[str, Any],
    integration_case: Mapping[str, Any],
    corpus: Mapping[str, Any],
) -> dict[str, Any]:
    if integration_case["reused_primary_role"] != "synth":
        raise ValueError("synth bottleneck integration role differs")
    if (
        midi_case["track_id"] != integration_case["track_id"]
        or midi_case["window_seconds"] != integration_case["window_seconds"]
    ):
        raise ValueError("synth bottleneck case binding differs")
    return {
        "case_id": midi_case["case_id"],
        "track_id": midi_case["track_id"],
        "title": midi_case["title"],
        "window_seconds": midi_case["window_seconds"],
        "target_presence": {
            "role": "synth",
            "status": "human_reviewed_present_before_separator_canary",
            "provider_label_alone_proves_presence": False,
        },
        "source_reference": _artifact_identity(
            integration_case["artifacts"]["reference"], role="reference"
        ),
        "current_separator_estimate": _artifact_identity(
            integration_case["artifacts"]["synth"], role="synth"
        ),
        "grouped_other_control": _artifact_identity(
            midi_case["grouped_other_control"]["artifact"],
            role="grouped_other",
        ),
        "provider_estimate_request": _provider_inventory(midi_case["track_id"], corpus),
        "frozen_transcription": {
            "metadata": midi_case["metadata"],
            "transcription": midi_case["transcription"],
            "parameters": {
                "onset_threshold": 0.5,
                "frame_threshold": 0.3,
                "min_note_ms": 60.0,
            },
            "same_parameters_for_all_three_arms": True,
        },
        "future_arms": [
            "current_separator_estimate",
            "provider_synth_or_keyboard_estimate",
            "grouped_other_control",
        ],
    }


def build_fine_stem_synth_bottleneck_plan(
    *,
    midi_report: Mapping[str, Any],
    midi_outcome: Mapping[str, Any],
    integration_report: Mapping[str, Any],
    provider_corpus: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the next request using JSON identities only; do not open audio."""

    canary = validate_fine_stem_midi_canary(midi_report)
    outcome = validate_fine_stem_midi_outcome(midi_outcome)
    integration = validate_fine_stem_integration_report(integration_report)
    if outcome["status"] != METHODOLOGY_LIMITED_STATUS:
        raise ValueError("synth bottleneck MIDI outcome status differs")
    if outcome["canary_document_sha256"] != canary["document_sha256"]:
        raise ValueError("synth bottleneck canary/outcome binding differs")
    if canary["integration"]["report_sha256"] != integration["report_sha256"]:
        raise ValueError("synth bottleneck integration binding differs")
    if provider_corpus.get("schema") != "sunofriend.authorised-separation-corpus.v1":
        raise ValueError("synth bottleneck provider corpus schema differs")

    integration_by_id = {case["case_id"]: case for case in integration["cases"]}
    synth_cases = [
        case
        for case in canary["cases"]
        if case["confirmed_present_target_role"] == "synth"
    ]
    if len(synth_cases) != SYNTH_CASE_COUNT:
        raise ValueError("synth bottleneck cohort differs")
    cases = [
        _case_plan(case, integration_by_id[case["case_id"]], provider_corpus)
        for case in synth_cases
    ]
    catalogued = sum(
        case["provider_estimate_request"]["status"]
        == "provider_pack_catalogued_exact_artifact_not_yet_bound"
        for case in cases
    )
    document: dict[str, Any] = {
        "schema": SYNTH_BOTTLENECK_PLAN_SCHEMA,
        "document_sha256": "",
        "status": SYNTH_BOTTLENECK_PLAN_STATUS,
        "created_on": "2026-08-10",
        "midi_canary_document_sha256": canary["document_sha256"],
        "midi_review_document_sha256": outcome["review_document_sha256"],
        "midi_outcome_document_sha256": outcome["document_sha256"],
        "integration_report_sha256": integration["report_sha256"],
        "provider_corpus": {
            "schema": provider_corpus["schema"],
            "checked_on": provider_corpus.get("checked_on"),
            "status": provider_corpus.get("status"),
            "catalogued_track_count": catalogued,
            "provider_estimates_are_ground_truth": False,
        },
        "purpose": (
            "distinguish a synth-separator bottleneck from a MIDI-transcriber "
            "or representation bottleneck before any tuning or training"
        ),
        "cases": cases,
        "required_inputs_before_execution_plan": {
            "exact_provider_artifacts": SYNTH_CASE_COUNT,
            "each_artifact_requires": [
                "absolute local source path recorded only in private evidence",
                "rights category and provider-use boundary",
                "source song identity and exact frozen window alignment",
                "byte size and SHA-256",
                "canonical stereo 44.1 kHz PCM24 derivative identity",
                "human confirmation that the provider estimate contains the target",
            ],
            "acceptable_role_order": ["synth", "keyboard", "keys"],
            "missing_exact_artifact_count": SYNTH_CASE_COUNT,
        },
        "future_execution_contract": {
            "song_disjoint_cases": SYNTH_CASE_COUNT,
            "arms_per_case": 3,
            "midi_transcription_attempt_budget": 12,
            "separator_rerun": False,
            "automatic_retry": False,
            "same_transcriber_bpm_key_tuning_and_window": True,
            "source_reference_visible_and_playable_during_review": True,
            "automatic_playback_recording": True,
            "manual_listened_checkbox": False,
            "blind_display_order_for_three_midi_previews": True,
            "automatic_winner_selection": False,
        },
        "attribution_policy": {
            "provider_useful_current_not_useful": "separator_bottleneck_likely",
            "provider_and_current_not_useful": (
                "transcriber_or_editable_representation_bottleneck_likely"
            ),
            "provider_and_current_useful": (
                "both_routes_workable_or_prior_source-omitted_review_limited"
            ),
            "current_useful_provider_not_useful": (
                "provider_estimate_is_not_a_useful_control; retain current evidence"
            ),
            "cannot_tell_or_not_tested": "inconclusive_no_automatic_retry",
            "poor_result_disables_core_four_or_six_role_evidence": False,
        },
        "permissions_required_for_later_execution": [
            "read four exact provider estimates plus the bound source, current synth and grouped-other artifacts",
            "write private aligned provider derivatives when needed",
            "run exactly 12 same-settings local MIDI transcription attempts",
            "write 12 private MIDI files, neutral previews and one source-present review package",
        ],
        "boundaries": {
            "request_only": True,
            "ready_for_execution": False,
            "private_audio_opened": False,
            "provider_audio_bound": False,
            "separator_model_loaded": False,
            "transcriber_run": False,
            "midi_created": False,
            "source_selected": False,
            "public_activation": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
            "training_started": False,
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
    document["document_sha256"] = synth_bottleneck_plan_document_sha256(document)
    return document


def validate_fine_stem_synth_bottleneck_plan(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != SYNTH_BOTTLENECK_PLAN_SCHEMA
        or document.get("status") != SYNTH_BOTTLENECK_PLAN_STATUS
        or document.get("document_sha256")
        != synth_bottleneck_plan_document_sha256(document)
    ):
        raise ValueError("synth bottleneck request identity differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != SYNTH_CASE_COUNT:
        raise ValueError("synth bottleneck request cases differ")
    if len({case.get("case_id") for case in cases}) != SYNTH_CASE_COUNT:
        raise ValueError("synth bottleneck request case identities differ")
    if any(
        case.get("target_presence", {}).get("status")
        != "human_reviewed_present_before_separator_canary"
        or case.get("provider_estimate_request", {}).get(
            "exact_provider_artifact_bound"
        )
        is not False
        for case in cases
    ):
        raise ValueError("synth bottleneck request evidence differs")
    if any(bool(effect) for effect in document.get("effects", {}).values()):
        raise ValueError("synth bottleneck request contains effects")
    boundaries = document.get("boundaries", {})
    if boundaries.get("request_only") is not True or any(
        boundaries.get(key) is not False
        for key in (
            "ready_for_execution",
            "private_audio_opened",
            "provider_audio_bound",
            "separator_model_loaded",
            "transcriber_run",
            "midi_created",
            "source_selected",
            "public_activation",
            "hosting",
            "redistribution",
            "audio_upload",
            "training_started",
        )
    ):
        raise ValueError("synth bottleneck request grants permission")
    return document


__all__ = [
    "SYNTH_BOTTLENECK_PLAN_SCHEMA",
    "SYNTH_BOTTLENECK_PLAN_STATUS",
    "build_fine_stem_synth_bottleneck_plan",
    "synth_bottleneck_plan_document_sha256",
    "validate_fine_stem_synth_bottleneck_plan",
]
