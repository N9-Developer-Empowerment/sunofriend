"""Immutable identity and validation for private full-song six-role plans."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .core_four_approval import (
    CONFIG_SHA256 as SCNET_CONFIG_SHA256,
    PROFILE_ID as CORE_FOUR_PROFILE_ID,
    SOURCE_REVISION as SCNET_SOURCE_REVISION,
    WEIGHTS_SHA256 as SCNET_WEIGHTS_SHA256,
)
from .separation_fine_stem_canary_contract import (
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_MLX_MEMORY_BYTES,
    PROFILE_CONTRACTS,
)
from .separation_fine_stem_integration_plan import PERSISTED_ROLES


FULL_SONG_PLAN_SCHEMA = "sunofriend.fine-stem-full-song-six-role-plan.v1"
FULL_SONG_PLAN_STATUS = "ready_for_explicit_private_full_song_execution_approval"
FULL_SONG_PLAN_DIRECTORY_NAME = "fine-stem-full-song-six-role-plan-v1"
FULL_SONG_PLAN_FILE_NAME = "FULL-SONG-SIX-ROLE-PLAN.json"
SELECTION_SLOTS = ("both_targets", "synth", "guitar")
TARGET_ID_TO_ROLE = {"synth_keyboard": "synth", "guitar": "guitar"}
SPECIALIST_PROFILE_IDS = {
    "synth": "bs-roformer-mega-53-synth-v1",
    "guitar": "bs-roformer-sw-guitar-v1",
}
MAXIMUM_TOTAL_ELAPSED_SECONDS = MAXIMUM_ELAPSED_SECONDS * len(SELECTION_SLOTS)


def full_song_plan_document_sha256(value: Mapping[str, Any]) -> str:
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


def full_song_profile_contracts() -> dict[str, Any]:
    synth = PROFILE_CONTRACTS[SPECIALIST_PROFILE_IDS["synth"]]
    guitar = PROFILE_CONTRACTS[SPECIALIST_PROFILE_IDS["guitar"]]
    return {
        "core_four": {
            "profile_id": CORE_FOUR_PROFILE_ID,
            "source_revision": SCNET_SOURCE_REVISION,
            "checkpoint_sha256": SCNET_WEIGHTS_SHA256,
            "config_sha256": SCNET_CONFIG_SHA256,
            "roles": ["vocals", "drums", "bass", "other"],
            "terms": "public repository MIT metadata and README-linked checkpoint accepted for the local preview",
        },
        "synth": {
            "profile_id": SPECIALIST_PROFILE_IDS["synth"],
            "source": copy.deepcopy(synth["source"]),
            "checkpoint": copy.deepcopy(synth["checkpoint"]),
            "config": copy.deepcopy(synth["config"]),
            "terms": synth["terms"],
        },
        "guitar": {
            "profile_id": SPECIALIST_PROFILE_IDS["guitar"],
            "source": copy.deepcopy(guitar["source"]),
            "checkpoint": copy.deepcopy(guitar["checkpoint"]),
            "config": copy.deepcopy(guitar["config"]),
            "terms": guitar["terms"],
        },
    }


def validate_fine_stem_full_song_plan(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    plan = copy.deepcopy(dict(value))
    if (
        plan.get("schema") != FULL_SONG_PLAN_SCHEMA
        or plan.get("status") != FULL_SONG_PLAN_STATUS
        or plan.get("document_sha256") != full_song_plan_document_sha256(plan)
    ):
        raise ValueError("full-song six-role plan identity differs")
    cases = plan.get("cases")
    if (
        not isinstance(cases, list)
        or [case.get("slot") for case in cases] != list(SELECTION_SLOTS)
        or len({case.get("track_id") for case in cases}) != len(SELECTION_SLOTS)
    ):
        raise ValueError("full-song six-role corpus differs")
    expected_scored = {
        "both_targets": ["guitar", "synth"],
        "synth": ["synth"],
        "guitar": ["guitar"],
    }
    for case in cases:
        presence_roles = sorted(
            item.get("target_role")
            for item in case.get("confirmed_present_targets", [])
        )
        if (
            case.get("scored_target_roles") != expected_scored[case["slot"]]
            or presence_roles != expected_scored[case["slot"]]
            or case.get("planning_observation", {}).get("content_opened") is not False
            or case.get("planning_observation", {}).get("regular_file") is not True
            or case.get("planning_observation", {}).get("observed_bytes")
            != case.get("full_song_source", {}).get("bytes")
            or case.get("planning_observation", {}).get("absolute_path")
            != case.get("full_song_source", {}).get("absolute_path")
            or case.get("unconfirmed_target_absence_is_model_failure") is not False
        ):
            raise ValueError("full-song six-role case contract differs")
    if plan.get("profiles", {}).get("core_four", {}).get("profile_id") != (
        CORE_FOUR_PROFILE_ID
    ):
        raise ValueError("full-song six-role core-four profile differs")
    if plan.get("output_contract", {}).get("persisted_roles") != list(PERSISTED_ROLES):
        raise ValueError("full-song six-role output roles differ")
    execution = plan.get("execution_contract", {})
    if (
        execution.get("execution_authorized") is not False
        or execution.get("model_loads") != 3
        or execution.get("models_run_sequentially") is not True
        or execution.get("profile_inference_attempts")
        != {"core_four": 3, "synth": 3, "guitar": 3, "total": 9}
        or execution.get("automatic_retry") is not False
        or execution.get("network_denied") is not True
        or execution.get("maximum_elapsed_seconds_per_song") != MAXIMUM_ELAPSED_SECONDS
        or execution.get("maximum_total_elapsed_seconds")
        != MAXIMUM_TOTAL_ELAPSED_SECONDS
        or execution.get("maximum_peak_unified_memory_bytes")
        != MAXIMUM_PEAK_MLX_MEMORY_BYTES
    ):
        raise ValueError("full-song six-role execution contract differs")
    admission = plan.get("admission_policy", {})
    review = plan.get("review_contract", {})
    approval = plan.get("next_approval", {})
    if (
        admission.get("subjective_feedback_is_execution_veto") is not False
        or admission.get("minimum_usefulness_rating") is not None
        or admission.get("poor_feedback_disables_core_four") is not False
        or review.get("playback_recorded_automatically") is not True
        or review.get("listened_checkbox") is not False
        or review.get("score_only_confirmed_present_target_roles") is not True
        or review.get("minimum_usefulness_for_private_package") is not None
        or review.get("review_selects_source_or_midi") is not False
        or approval.get("required") is not True
        or approval.get("received") is not False
    ):
        raise ValueError("full-song six-role feedback or approval contract differs")
    if any(bool(effect) for effect in plan.get("effects", {}).values()):
        raise ValueError("full-song six-role plan contains effects")
    boundaries = plan.get("boundaries", {})
    if boundaries.get("plan_only") is not True or any(
        boundaries.get(key) is not False
        for key in (
            "source_content_opened",
            "checkpoint_loaded",
            "model_constructed",
            "inference_run",
            "private_audio_written",
            "public_activation",
            "source_selection",
            "midi_created",
            "hosting",
            "redistribution",
            "audio_upload",
        )
    ):
        raise ValueError("full-song six-role plan grants permission")
    return plan


__all__ = [
    "FULL_SONG_PLAN_DIRECTORY_NAME",
    "FULL_SONG_PLAN_FILE_NAME",
    "FULL_SONG_PLAN_SCHEMA",
    "FULL_SONG_PLAN_STATUS",
    "MAXIMUM_TOTAL_ELAPSED_SECONDS",
    "SELECTION_SLOTS",
    "SPECIALIST_PROFILE_IDS",
    "TARGET_ID_TO_ROLE",
    "full_song_plan_document_sha256",
    "full_song_profile_contracts",
    "validate_fine_stem_full_song_plan",
]
