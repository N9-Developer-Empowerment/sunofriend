"""Pure plan for reconciling qualified synth and guitar into six roles."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from .separation_fine_stem_canary_contract import (
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_MLX_MEMORY_BYTES,
    validate_fine_stem_canary_report,
)
from .separation_fine_stem_canary_outcome import (
    PORTFOLIO_OUTCOME_STATUS,
    validate_fine_stem_portfolio_outcome,
)
from .separation_fine_stem_canary_review import validate_fine_stem_canary_review


INTEGRATION_PLAN_SCHEMA = "sunofriend.fine-stem-six-role-integration-plan.v1"
INTEGRATION_PLAN_STATUS = "awaiting_explicit_bounded_private_integration_approval"
PERSISTED_ROLES = ("vocals", "drums", "bass", "synth", "guitar", "other")
CORE_FOUR_PROFILE_ID = "scnet-large-musdb-release-v1"
SYNTH_PROFILE_ID = "bs-roformer-mega-53-synth-v1"
GUITAR_PROFILE_ID = "bs-roformer-sw-guitar-v1"


def integration_plan_document_sha256(value: Mapping[str, Any]) -> str:
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


def _validated_pair(
    report: Mapping[str, Any], review: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    objective = validate_fine_stem_canary_report(report)
    listening = validate_fine_stem_canary_review(review, objective)
    if listening["status"] != "human_listening_complete_no_selection":
        raise ValueError("fine-stem integration requires completed listening")
    return objective, listening


def build_fine_stem_six_role_integration_plan(
    *,
    portfolio_outcome: Mapping[str, Any],
    synth_report: Mapping[str, Any],
    synth_review: Mapping[str, Any],
    guitar_report: Mapping[str, Any],
    guitar_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an effects-free plan from the exact qualified review portfolio."""

    outcome = validate_fine_stem_portfolio_outcome(portfolio_outcome)
    synth_objective, synth_listening = _validated_pair(synth_report, synth_review)
    guitar_objective, guitar_listening = _validated_pair(guitar_report, guitar_review)
    if outcome["status"] != PORTFOLIO_OUTCOME_STATUS:
        raise ValueError("fine-stem portfolio has not qualified for integration")
    pairs = ((synth_objective, synth_listening), (guitar_objective, guitar_listening))
    expected_profiles = (SYNTH_PROFILE_ID, GUITAR_PROFILE_ID)
    if tuple(item[0]["profile_id"] for item in pairs) != expected_profiles:
        raise ValueError("fine-stem integration profile order differs")
    outcome_targets = {target["profile_id"]: target for target in outcome["targets"]}
    for objective, listening in pairs:
        target = outcome_targets.get(objective["profile_id"], {})
        if (
            target.get("report_sha256") != objective["report_sha256"]
            or target.get("review_document_sha256") != listening["document_sha256"]
            or target.get("qualifies_for_private_studio_integration") is not True
        ):
            raise ValueError("fine-stem integration evidence binding differs")

    cases = []
    for objective, listening in pairs:
        review_by_id = {case["case_id"]: case for case in listening["cases"]}
        primary_role = objective["target_role"]
        complementary_role = "guitar" if primary_role == "synth" else "synth"
        for case in objective["cases"]:
            reviewed = review_by_id[case["case_id"]]
            cases.append(
                {
                    "case_id": case["case_id"],
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "window_seconds": copy.deepcopy(case["window_seconds"]),
                    "canonical_reference_artifact": copy.deepcopy(
                        case["artifacts"]["reference"]
                    ),
                    "reused_primary_estimate": {
                        "role": primary_role,
                        "artifact": copy.deepcopy(case["artifacts"]["target"]),
                        "presence": "confirmed_present_before_inference",
                        "usefulness": reviewed["usefulness"],
                    },
                    "new_complementary_estimate": {
                        "role": complementary_role,
                        "presence": "not_evaluated_for_this_exact_window",
                        "absence_is_model_failure": False,
                    },
                }
            )

    if len(cases) != 8 or len({case["case_id"] for case in cases}) != 8:
        raise ValueError("fine-stem integration case portfolio differs")
    plan: dict[str, Any] = {
        "schema": INTEGRATION_PLAN_SCHEMA,
        "document_sha256": "",
        "status": INTEGRATION_PLAN_STATUS,
        "release_tier": "private_studio_challenger",
        "evidence_binding": {
            "portfolio_outcome_sha256": outcome["document_sha256"],
            "synth_report_sha256": synth_objective["report_sha256"],
            "synth_review_sha256": synth_listening["document_sha256"],
            "guitar_report_sha256": guitar_objective["report_sha256"],
            "guitar_review_sha256": guitar_listening["document_sha256"],
            "both_targets_qualified": True,
        },
        "profiles": {
            "core_four": CORE_FOUR_PROFILE_ID,
            "synth": SYNTH_PROFILE_ID,
            "guitar": GUITAR_PROFILE_ID,
        },
        "cases": cases,
        "execution_contract": {
            "case_count": 8,
            "reuse_existing_primary_estimates": 8,
            "new_core_four_inference_attempts": 8,
            "new_synth_inference_attempts": 4,
            "new_guitar_inference_attempts": 4,
            "model_loads": 3,
            "models_run_sequentially": True,
            "writer_count": 1,
            "automatic_retry": False,
            "network_denied": True,
            "maximum_elapsed_seconds": MAXIMUM_ELAPSED_SECONDS,
            "maximum_peak_unified_memory_bytes": MAXIMUM_PEAK_MLX_MEMORY_BYTES,
        },
        "integration_contract": {
            "persisted_roles": list(PERSISTED_ROLES),
            "parent_roles_preserved": ["vocals", "drums", "bass"],
            "allocation_parent": "SCNet grouped other",
            "raw_specialist_inputs": "full canonical reference",
            "projection": {
                "method": "fixed grouped-other-constrained three-way Wiener mask",
                "fft_size": 4096,
                "hop_size": 1024,
                "window": "periodic Hann",
                "power": 2,
                "components": ["raw synth", "raw guitar", "raw residual"],
                "raw_residual_definition": "grouped other - raw synth - raw guitar",
                "projected_phase": "grouped-other phase",
                "time_domain_other_definition": (
                    "grouped other - projected synth - projected guitar"
                ),
            },
            "one_shared_attenuation_if_required": True,
            "pcm24_other_constructed_last": True,
            "maximum_reconstruction_error_lsb": 2,
            "raw_to_projected_correction_rms_and_peak_recorded": True,
            "reconstruction_accounting_is_separation_accuracy": False,
        },
        "review_policy": {
            "one_complete_internal_listen_per_case": True,
            "minimum_usefulness_for_execution": None,
            "secondary_target_absence_is_valid": True,
            "one_configuration": True,
            "remediation_cycles": 0,
            "poor_feedback_disables_core_four": False,
        },
        "next_approval": {
            "required": True,
            "received": False,
            "bind_document_sha256_in_approval": True,
            "exact_text": (
                "I approve one network-denied private six-role integration canary "
                "for the exact plan document SHA-256 I cite, over its eight already "
                "reviewed 15-second reference artifacts. I approve reusing the eight "
                "persisted primary fine-stem estimates, running SCNet core-four once "
                "per artifact, and running only the missing Mega-53 synth or "
                "BS-RoFormer-SW guitar estimate once per artifact in verified local "
                "runtimes. I approve the fixed grouped-other-constrained projection "
                "and private PCM24 vocals, drums, bass, synth, guitar and residual-"
                "other review artifacts. No download, automatic retry, public "
                "activation, source selection, MIDI, hosting, redistribution or "
                "audio upload is approved."
            ),
        },
        "effects": {
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "inference_attempts": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "network_attempts": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
        },
    }
    plan["document_sha256"] = integration_plan_document_sha256(plan)
    return plan


def validate_fine_stem_six_role_integration_plan(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if value.get("schema") != INTEGRATION_PLAN_SCHEMA:
        raise ValueError("fine-stem integration plan schema differs")
    if value.get("status") != INTEGRATION_PLAN_STATUS:
        raise ValueError("fine-stem integration plan status differs")
    if value.get("document_sha256") != integration_plan_document_sha256(value):
        raise ValueError("fine-stem integration plan hash differs")
    if value.get("integration_contract", {}).get("persisted_roles") != list(
        PERSISTED_ROLES
    ):
        raise ValueError("fine-stem integration role contract differs")
    if len(value.get("cases", [])) != 8:
        raise ValueError("fine-stem integration case count differs")
    if any(bool(item) for item in value.get("effects", {}).values()):
        raise ValueError("fine-stem integration plan contains effects")
    return copy.deepcopy(dict(value))


__all__ = [
    "INTEGRATION_PLAN_SCHEMA",
    "INTEGRATION_PLAN_STATUS",
    "PERSISTED_ROLES",
    "build_fine_stem_six_role_integration_plan",
    "integration_plan_document_sha256",
    "validate_fine_stem_six_role_integration_plan",
]
