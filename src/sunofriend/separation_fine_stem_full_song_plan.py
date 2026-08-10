"""Pure no-effects contract for a bounded private full-song six-role canary."""

from __future__ import annotations

import copy
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from .separation_fine_stem_canary_contract import (
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_MLX_MEMORY_BYTES,
)
from .separation_fine_stem_full_song_plan_contract import (
    FULL_SONG_PLAN_DIRECTORY_NAME,
    FULL_SONG_PLAN_FILE_NAME,
    FULL_SONG_PLAN_SCHEMA,
    FULL_SONG_PLAN_STATUS,
    MAXIMUM_TOTAL_ELAPSED_SECONDS,
    SELECTION_SLOTS,
    TARGET_ID_TO_ROLE,
    full_song_plan_document_sha256,
    full_song_profile_contracts,
    validate_fine_stem_full_song_plan,
)
from .separation_fine_stem_integration_outcome import (
    QUALIFIED_STATUS,
    validate_fine_stem_integration_outcome,
)
from .separation_fine_stem_integration_plan import PERSISTED_ROLES
from .separation_target_presence_review import (
    PRESENCE_MANIFEST_SCHEMA,
    presence_document_sha256,
    validate_presence_result,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _validate_presence_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(dict(value))
    if (
        manifest.get("schema") != PRESENCE_MANIFEST_SCHEMA
        or manifest.get("status") != "source_presence_pending_no_model_inference"
        or manifest.get("document_sha256") != presence_document_sha256(manifest)
    ):
        raise ValueError("full-song source-presence manifest identity differs")
    qualification = manifest.get("qualification", {})
    if (
        qualification.get("schema")
        != "sunofriend.fine-stem-target-presence-qualification.v1"
        or qualification.get("status") != "qualified_source_presence_no_model_inference"
        or qualification.get("document_sha256")
        != presence_document_sha256(qualification)
        or qualification.get("rules", {}).get("decision_required") != "present"
        or qualification.get("rules", {}).get("song_disjoint_within_target") is not True
    ):
        raise ValueError("full-song source-presence qualification differs")
    return manifest


def _source_identity(case: Mapping[str, Any]) -> dict[str, Any]:
    source = copy.deepcopy(dict(case.get("source_input", {})))
    relative = source.get("relative_path")
    if (
        not isinstance(relative, str)
        or not relative
        or PurePosixPath(relative).is_absolute()
        or ".." in PurePosixPath(relative).parts
        or not isinstance(source.get("bytes"), int)
        or source["bytes"] <= 0
        or not isinstance(source.get("frames"), int)
        or source["frames"] <= 0
        or source.get("channels") != 2
        or not isinstance(source.get("sample_rate_hz"), int)
        or source["sample_rate_hz"] <= 0
        or not isinstance(source.get("sha256"), str)
        or _SHA256.fullmatch(source["sha256"]) is None
    ):
        raise ValueError("full-song source identity differs")
    return source


def _canonical_frames(source: Mapping[str, Any]) -> int:
    numerator = int(source["frames"]) * 44_100
    denominator = int(source["sample_rate_hz"])
    quotient, remainder = divmod(numerator, denominator)
    if remainder * 2 < denominator:
        return quotient
    if remainder * 2 > denominator:
        return quotient + 1
    return quotient + (quotient % 2)


def _presence_evidence(
    case: Mapping[str, Any],
    result_case: Mapping[str, Any],
    qualified_case_ids: Mapping[str, set[str]],
) -> dict[str, Any]:
    target_id = str(case.get("target_id"))
    role = TARGET_ID_TO_ROLE.get(target_id)
    if role is None:
        raise ValueError("full-song target role differs")
    source_artifact = copy.deepcopy(case.get("artifacts", {}).get("source", {}))
    if (
        result_case.get("listened") is not True
        or result_case.get("decision") != "present"
        or case.get("case_id") not in qualified_case_ids.get(role, set())
        or source_artifact.get("sample_rate_hz") != 44_100
        or source_artifact.get("channels") != 2
        or source_artifact.get("frames") != 661_500
        or _SHA256.fullmatch(str(source_artifact.get("sha256", ""))) is None
    ):
        raise ValueError("full-song confirmed-present evidence differs")
    return {
        "target_role": role,
        "target_id": target_id,
        "case_id": case["case_id"],
        "window_seconds": copy.deepcopy(case["window_seconds"]),
        "source_excerpt": {
            key: copy.deepcopy(source_artifact[key])
            for key in (
                "bytes",
                "channels",
                "frames",
                "sample_rate_hz",
                "sha256",
                "subtype",
            )
        },
        "human_decision": "present",
        "listened_before_model_scoring": True,
        "provider_label_used_as_truth": False,
    }


def _case_for_slot(
    *,
    slot: str,
    track_id: str,
    manifest_cases: list[Mapping[str, Any]],
    results_by_id: Mapping[str, Mapping[str, Any]],
    qualified_case_ids: Mapping[str, set[str]],
    source_root: str,
    source_observations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    expected_roles = {
        "both_targets": {"synth", "guitar"},
        "synth": {"synth"},
        "guitar": {"guitar"},
    }[slot]
    candidates = [case for case in manifest_cases if case.get("track_id") == track_id]
    selected = [
        case
        for case in candidates
        if TARGET_ID_TO_ROLE.get(str(case.get("target_id"))) in expected_roles
    ]
    roles = [TARGET_ID_TO_ROLE[str(case["target_id"])] for case in selected]
    if len(selected) != len(expected_roles) or set(roles) != expected_roles:
        raise ValueError(f"full-song {slot} source-presence coverage differs")
    sources = [_source_identity(case) for case in selected]
    if any(source != sources[0] for source in sources[1:]):
        raise ValueError("full-song repeated-track source identities differ")
    source = sources[0]
    observation = copy.deepcopy(dict(source_observations.get(track_id, {})))
    expected_path = str(PurePosixPath(source_root) / source["relative_path"])
    if (
        observation.get("absolute_path") != expected_path
        or observation.get("regular_file") is not True
        or observation.get("observed_bytes") != source["bytes"]
        or observation.get("content_opened") is not False
    ):
        raise ValueError("full-song source metadata observation differs")
    rights = {case.get("rights_category") for case in selected}
    titles = {case.get("title") for case in selected}
    if len(rights) != 1 or len(titles) != 1 or None in rights or None in titles:
        raise ValueError("full-song title or rights binding differs")
    evidence = [
        _presence_evidence(
            case,
            results_by_id[case["case_id"]],
            qualified_case_ids,
        )
        for case in sorted(
            selected,
            key=lambda item: (
                TARGET_ID_TO_ROLE[str(item["target_id"])],
                item["case_id"],
            ),
        )
    ]
    unscored = sorted({"synth", "guitar"} - expected_roles)
    return {
        "slot": slot,
        "track_id": track_id,
        "title": titles.pop(),
        "rights_category": rights.pop(),
        "full_song_source": {
            **source,
            "absolute_path": observation["absolute_path"],
            "expected_canonical_frames": _canonical_frames(source),
            "expected_canonical_sample_rate_hz": 44_100,
            "expected_canonical_channels": 2,
            "expected_canonical_subtype": "PCM_24",
        },
        "planning_observation": observation,
        "confirmed_present_targets": evidence,
        "scored_target_roles": sorted(expected_roles),
        "unscored_target_roles": unscored,
        "unconfirmed_target_absence_is_model_failure": False,
    }


def build_fine_stem_full_song_plan(
    *,
    presence_manifest: Mapping[str, Any],
    presence_result: Mapping[str, Any],
    integration_outcome: Mapping[str, Any],
    selections: Mapping[str, str],
    source_root: str,
    source_observations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one fixed three-song plan without opening any source content."""

    manifest = _validate_presence_manifest(presence_manifest)
    result = validate_presence_result(copy.deepcopy(dict(presence_result)), manifest)
    outcome = validate_fine_stem_integration_outcome(integration_outcome)
    if (
        result["status"] != "presence_review_complete_no_model_inference"
        or result.get("qualification_sha256")
        != manifest["qualification"]["document_sha256"]
        or outcome["status"] != QUALIFIED_STATUS
        or outcome.get("qualified_for_private_six_role_integration") is not True
    ):
        raise ValueError("full-song prerequisite evidence is not qualified")
    if set(selections) != set(SELECTION_SLOTS) or any(
        not isinstance(selections[slot], str) or not selections[slot]
        for slot in SELECTION_SLOTS
    ):
        raise ValueError("full-song selection slots differ")
    if len(set(selections.values())) != len(SELECTION_SLOTS):
        raise ValueError("full-song corpus must contain three song-disjoint tracks")
    root = PurePosixPath(source_root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("full-song source root must be absolute")

    results_by_id = {case["case_id"]: case for case in result["cases"]}
    qualified_case_ids = {
        target["target_role"]: set(target["case_ids"]) for target in outcome["targets"]
    }
    cases = [
        _case_for_slot(
            slot=slot,
            track_id=selections[slot],
            manifest_cases=manifest["cases"],
            results_by_id=results_by_id,
            qualified_case_ids=qualified_case_ids,
            source_root=str(root),
            source_observations=source_observations,
        )
        for slot in SELECTION_SLOTS
    ]

    plan: dict[str, Any] = {
        "schema": FULL_SONG_PLAN_SCHEMA,
        "document_sha256": "",
        "status": FULL_SONG_PLAN_STATUS,
        "created_on": "2026-08-11",
        "release_tier": "private_studio_challenger",
        "evidence_binding": {
            "presence_manifest_sha256": manifest["document_sha256"],
            "presence_result_sha256": result["document_sha256"],
            "presence_qualification_sha256": manifest["qualification"][
                "document_sha256"
            ],
            "integration_plan_sha256": outcome["plan_sha256"],
            "integration_report_sha256": outcome["report_sha256"],
            "integration_review_sha256": outcome["review_document_sha256"],
            "integration_outcome_sha256": outcome["document_sha256"],
        },
        "scope": {
            "purpose": (
                "test full-song continuity and private Studio usefulness for exact "
                "vocals, drums, bass, synth, guitar and residual other"
            ),
            "song_count": 3,
            "song_disjoint": True,
            "coverage_slots": list(SELECTION_SLOTS),
            "one_fixed_configuration": True,
            "automatic_retry": False,
            "remediation_cycles_in_this_plan": 0,
        },
        "profiles": full_song_profile_contracts(),
        "cases": cases,
        "execution_contract": {
            "execution_authorized": False,
            "source_files": 3,
            "canonicalization_attempts": 3,
            "model_loads": 3,
            "models_run_sequentially": True,
            "profile_inference_attempts": {
                "core_four": 3,
                "synth": 3,
                "guitar": 3,
                "total": 9,
            },
            "duration_dependent_internal_forward_calls": (
                "derived from each exact canonical frame count and frozen backend "
                "chunk contract before execution, then reported"
            ),
            "writer_count": 1,
            "network_denied": True,
            "automatic_retry": False,
            "maximum_elapsed_seconds_per_song": MAXIMUM_ELAPSED_SECONDS,
            "maximum_total_elapsed_seconds": MAXIMUM_TOTAL_ELAPSED_SECONDS,
            "maximum_peak_unified_memory_bytes": MAXIMUM_PEAK_MLX_MEMORY_BYTES,
            "first_supported_machine_class": "Apple M3 Max with 36 GB unified memory",
            "resource_failure_policy": (
                "preserve the failed attempt and stop; no automatic retry or "
                "feedback-driven configuration search"
            ),
        },
        "output_contract": {
            "persisted_roles": list(PERSISTED_ROLES),
            "review_artifacts_per_song": [
                "reference",
                *PERSISTED_ROLES,
                "reconstruction_check",
            ],
            "parent_roles_preserved": ["vocals", "drums", "bass"],
            "specialists_allocated_only_inside": "SCNet grouped other",
            "projection": {
                "method": "fixed grouped-other-constrained three-way Wiener mask",
                "components": ["raw synth", "raw guitar", "raw residual"],
                "residual_other_constructed_last": True,
            },
            "one_shared_attenuation_if_required": True,
            "sample_rate_hz": 44_100,
            "channels": 2,
            "subtype": "PCM_24",
            "maximum_reconstruction_error_lsb": 2,
            "finite_samples_required": True,
            "matching_clocks_required": True,
            "bounded_peaks_required": True,
            "atomic_publication": True,
            "reconstruction_accounting_is_separation_accuracy": False,
        },
        "admission_policy": {
            "objective_stop_ship_conditions": [
                "licence or artifact-hash contradiction",
                "inference network access",
                "source mutation or privacy breach",
                "corrupt or missing roles",
                "non-finite audio",
                "clock mismatch",
                "failed reconstruction accounting",
                "resource ceiling, crash or OOM",
            ],
            "subjective_feedback_is_execution_veto": False,
            "minimum_usefulness_rating": None,
            "poor_feedback_disables_core_four": False,
            "poor_feedback_disables_last_functioning_private_profile": False,
            "poor_feedback_action": (
                "record limitations and proceed to the already bounded next "
                "product decision without retuning this configuration"
            ),
        },
        "review_contract": {
            "full_song_listen_per_case": True,
            "playback_recorded_automatically": True,
            "listened_checkbox": False,
            "confirmed_present_windows_replayed": True,
            "score_only_confirmed_present_target_roles": True,
            "complementary_unconfirmed_role_can_be_absent": True,
            "catastrophic_check_separate_from_usefulness": True,
            "minimum_usefulness_for_private_package": None,
            "required_fields": [
                "overall and per-role usefulness",
                "bleed",
                "missing content",
                "artefacts",
                "timing or join problems",
                "cannot_tell or not_tested when appropriate",
            ],
            "exhaustive_internal_chunk_boundary_review": False,
            "review_selects_source_or_midi": False,
        },
        "next_approval": {
            "required": True,
            "received": False,
            "bind_document_sha256_in_approval": True,
            "exact_text_template": (
                "I approve one network-denied private full-song six-role canary "
                "bound to plan SHA-256 [PLAN_SHA256], over its three exact "
                "song-disjoint owner-authorised sources. I approve canonicalising "
                "each source once to stereo 44.1 kHz PCM24, loading SCNet core-four, "
                "Mega-53 synth and BS-RoFormer-SW guitar once each and running the "
                "nine fixed full-song profile attempts sequentially. I approve the "
                "fixed grouped-other-constrained projection and private PCM24 source, "
                "vocals, drums, bass, synth, guitar, residual-other and reconstruction "
                "review artifacts. No automatic retry, public activation, source "
                "selection, MIDI, hosting, redistribution or audio upload is approved."
            ),
        },
        "boundaries": {
            "plan_only": True,
            "source_content_opened": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_run": False,
            "private_audio_written": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
        "effects": {
            "source_content_reads": 0,
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "inference_attempts": 0,
            "audio_writes": 0,
            "network_attempts": 0,
            "public_activations": 0,
            "source_selections": 0,
            "midi_writes": 0,
        },
    }
    plan["document_sha256"] = full_song_plan_document_sha256(plan)
    return plan


__all__ = [
    "FULL_SONG_PLAN_DIRECTORY_NAME",
    "FULL_SONG_PLAN_FILE_NAME",
    "FULL_SONG_PLAN_SCHEMA",
    "FULL_SONG_PLAN_STATUS",
    "SELECTION_SLOTS",
    "build_fine_stem_full_song_plan",
    "full_song_plan_document_sha256",
    "validate_fine_stem_full_song_plan",
]
