"""Pure contracts for bounded synth and guitar separation canaries."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from .separation_other_refinement_next_model_load_contract import (
    CHECKPOINT as MEGA53_CHECKPOINT,
    CONFIG as MEGA53_CONFIG,
    SOURCE as BS_ROFORMER_SOURCE,
)
from .separation_other_refinement_next_synthetic_plan import (
    ALIGNED_CHUNK_SIZE,
    NATIVE_ROLES as MEGA53_NATIVE_ROLES,
    SYNTH_ROLE_INDEX,
)
from .separation_target_presence_review import validate_presence_result


CANARY_PLAN_SCHEMA = "sunofriend.fine-stem-canary-plan.v1"
CANARY_REPORT_SCHEMA = "sunofriend.fine-stem-canary-report.v1"
SAMPLE_RATE_HZ = 44_100
WINDOW_SECONDS = 15
WINDOW_FRAMES = SAMPLE_RATE_HZ * WINDOW_SECONDS
MAXIMUM_CASES = 4
MAXIMUM_ELAPSED_SECONDS = 900
MAXIMUM_PEAK_MLX_MEMORY_BYTES = 30 * 1024**3
MAXIMUM_RECONSTRUCTION_ERROR_LSB = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

SW_CHECKPOINT = {
    "file": "BS-Rofo-SW-Fixed.ckpt",
    "bytes": 699_412_152,
    "sha256": "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e",
}
SW_CONFIG = {
    "file": "BS-Rofo-SW-Fixed.yaml",
    "bytes": 686,
    "sha256": "52df622c95ff3c1f4e1389f476ed737581a2c2dc12324d52c9763be9ccd2be2b",
}
SW_NATIVE_ROLES = ("bass", "drums", "other", "vocals", "guitar", "piano")


PROFILE_CONTRACTS = {
    "bs-roformer-mega-53-synth-v1": {
        "target_id": "synth_keyboard",
        "target_role": "synth",
        "target_role_index": SYNTH_ROLE_INDEX,
        "native_roles": list(MEGA53_NATIVE_ROLES),
        "checkpoint": MEGA53_CHECKPOINT,
        "config": MEGA53_CONFIG,
        "source": BS_ROFORMER_SOURCE,
        "terms": "provisional local noncommercial evaluation; no redistribution",
        "strategy": "one aligned padded MLX forward per confirmed case",
        "model_forward_calls_per_case": 1,
        "model_input_frames": ALIGNED_CHUNK_SIZE,
    },
    "bs-roformer-sw-guitar-v1": {
        "target_id": "guitar",
        "target_role": "guitar",
        "target_role_index": 4,
        "native_roles": list(SW_NATIVE_ROLES),
        "checkpoint": SW_CHECKPOINT,
        "config": SW_CONFIG,
        "source": BS_ROFORMER_SOURCE,
        "terms": "CC-BY-NC-SA-4.0 local noncommercial evaluation",
        "strategy": "verified MLX overlap-add using the frozen upstream clock",
        "model_forward_calls_per_case": 5,
        "model_input_frames": 588_800,
    },
}


def canary_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"document_sha256", "report_sha256", "recorded_at"}
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _presence_cases(
    profile: Mapping[str, Any],
    manifest: Mapping[str, Any],
    presence_result: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], bool, bool]:
    validated = validate_presence_result(dict(presence_result), dict(manifest))
    target_id = profile["target_id"]
    result_by_id = {case["case_id"]: case for case in validated["cases"]}
    cases = []
    for case in manifest.get("cases", []):
        if case.get("target_id") != target_id:
            continue
        result = result_by_id.get(case.get("case_id"), {})
        cases.append(
            {
                "case_id": case["case_id"],
                "track_id": case["track_id"],
                "title": case["title"],
                "target_id": case["target_id"],
                "window_seconds": case["window_seconds"],
                "source_artifact": copy.deepcopy(case["artifacts"]["source"]),
                "presence_listened": result.get("listened") is True,
                "presence_decision": result.get("decision", ""),
            }
        )
    complete = (
        len(cases) == MAXIMUM_CASES
        and len({case["track_id"] for case in cases}) == MAXIMUM_CASES
        and all(
            case["presence_listened"]
            and case["presence_decision"] in {"present", "absent", "cannot_tell"}
            for case in cases
        )
    )
    all_present = (
        len(cases) == MAXIMUM_CASES
        and len({case["track_id"] for case in cases}) == MAXIMUM_CASES
        and all(
            case["presence_listened"] and case["presence_decision"] == "present"
            for case in cases
        )
    )
    return cases, complete, all_present


def build_fine_stem_canary_plan(
    profile_id: str,
    manifest: Mapping[str, Any],
    presence_result: Mapping[str, Any],
    *,
    checkpoint_available: bool,
    config_available: bool,
) -> dict[str, Any]:
    """Build a no-effects plan from one exact source-presence review."""

    if profile_id not in PROFILE_CONTRACTS:
        raise ValueError("fine-stem canary profile differs")
    profile = PROFILE_CONTRACTS[profile_id]
    cases, review_complete, all_present = _presence_cases(
        profile, manifest, presence_result
    )
    if not review_complete:
        status = "blocked_target_presence_review_incomplete"
    elif not all_present:
        status = "blocked_replacement_target_presence_required"
    elif not checkpoint_available or not config_available:
        status = "blocked_verified_profile_artifact_missing"
    else:
        status = "ready_for_bounded_private_execution"
    plan: dict[str, Any] = {
        "schema": CANARY_PLAN_SCHEMA,
        "document_sha256": "",
        "status": status,
        "profile_id": profile_id,
        "release_tier": "private_studio_challenger",
        "presence_binding": {
            "manifest_sha256": manifest.get("document_sha256"),
            "result_sha256": validate_presence_result(
                dict(presence_result), dict(manifest)
            )["document_sha256"],
            "review_complete": review_complete,
            "all_four_target_cases_present": all_present,
            "absent_or_cannot_tell_is_model_failure": False,
        },
        "profile": copy.deepcopy(profile),
        "artifact_availability": {
            "checkpoint": checkpoint_available,
            "config": config_available,
        },
        "cases": cases,
        "execution": {
            "case_limit": MAXIMUM_CASES,
            "song_disjoint": len({case["track_id"] for case in cases}) == len(cases),
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "window_seconds": WINDOW_SECONDS,
            "window_frames": WINDOW_FRAMES,
            "model_loads": 1,
            "model_constructions": 1,
            "model_forward_calls": (
                len(cases) * profile["model_forward_calls_per_case"]
            ),
            "automatic_retry": False,
            "network_denied": True,
            "maximum_elapsed_seconds": MAXIMUM_ELAPSED_SECONDS,
            "maximum_peak_mlx_memory_bytes": MAXIMUM_PEAK_MLX_MEMORY_BYTES,
        },
        "output_contract": {
            "persisted_roles": [profile["target_role"], "residual"],
            "reference": "shared-attenuation PCM24 source reference",
            "residual_definition": "persisted reference - persisted target",
            "maximum_reconstruction_error_lsb": MAXIMUM_RECONSTRUCTION_ERROR_LSB,
            "target_quantization_correction_rms_and_peak_recorded": True,
            "separation_accuracy_claimed_by_reconstruction": False,
            "human_review_required": True,
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
    plan["document_sha256"] = canary_document_sha256(plan)
    return plan


def validate_fine_stem_canary_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema") != CANARY_PLAN_SCHEMA:
        raise ValueError("fine-stem canary plan schema differs")
    if value.get("profile_id") not in PROFILE_CONTRACTS:
        raise ValueError("fine-stem canary plan profile differs")
    if value.get("document_sha256") != canary_document_sha256(value):
        raise ValueError("fine-stem canary plan hash differs")
    if len(value.get("cases", [])) > MAXIMUM_CASES:
        raise ValueError("fine-stem canary case bound differs")
    effects = value.get("effects", {})
    if any(bool(item) for item in effects.values()):
        raise ValueError("fine-stem canary plan contains effects")
    return copy.deepcopy(dict(value))


def validate_fine_stem_canary_report(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate objective execution evidence without importing a model runtime."""

    if value.get("schema") != CANARY_REPORT_SCHEMA:
        raise ValueError("fine-stem canary report schema differs")
    if value.get("profile_id") not in PROFILE_CONTRACTS:
        raise ValueError("fine-stem canary report profile differs")
    profile = PROFILE_CONTRACTS[value["profile_id"]]
    if value.get("target_role") != profile["target_role"]:
        raise ValueError("fine-stem canary report target role differs")
    if value.get("report_sha256") != canary_document_sha256(value):
        raise ValueError("fine-stem canary report hash differs")
    if value.get("status") != "objective_execution_complete_review_required":
        raise ValueError("fine-stem canary report status differs")
    plan = value.get("plan", {})
    if plan.get("status") != "ready_for_bounded_private_execution":
        raise ValueError("fine-stem canary report plan was not executable")
    validate_fine_stem_canary_plan(plan)
    cases = value.get("cases", [])
    if len(cases) != MAXIMUM_CASES:
        raise ValueError("fine-stem canary report case count differs")
    case_ids = {case.get("case_id") for case in cases}
    if case_ids != {case["case_id"] for case in plan["cases"]}:
        raise ValueError("fine-stem canary report case identity differs")
    planned_cases = {case["case_id"]: case for case in plan["cases"]}
    artifact_paths: set[str] = set()
    for case in cases:
        planned = planned_cases[case["case_id"]]
        if any(
            case.get(key) != planned[key]
            for key in ("track_id", "title", "window_seconds")
        ):
            raise ValueError("fine-stem canary case source binding differs")
        if case.get("target_role") != profile["target_role"]:
            raise ValueError("fine-stem canary case target role differs")
        if case.get("source_input_sha256") != planned["source_artifact"]["sha256"]:
            raise ValueError("fine-stem canary case source hash differs")
        if case.get("all_samples_finite") is not True:
            raise ValueError("fine-stem canary emitted non-finite audio")
        error = case.get("maximum_reconstruction_error_lsb")
        if not isinstance(error, int) or not 0 <= error <= 2:
            raise ValueError("fine-stem canary reconstruction accounting failed")
        artifacts = case.get("artifacts", {})
        if set(artifacts) != {"reference", "target", "residual"}:
            raise ValueError("fine-stem canary artifacts differ")
        for artifact in artifacts.values():
            relative = artifact.get("relative_path")
            parsed = PurePosixPath(relative) if isinstance(relative, str) else None
            if (
                parsed is None
                or parsed.is_absolute()
                or ".." in parsed.parts
                or relative in artifact_paths
                or not isinstance(artifact.get("bytes"), int)
                or artifact["bytes"] <= 0
                or _SHA256.fullmatch(str(artifact.get("sha256"))) is None
                or artifact.get("sample_rate_hz") != SAMPLE_RATE_HZ
                or artifact.get("channels") != 2
                or artifact.get("frames") != WINDOW_FRAMES
                or artifact.get("subtype") != "PCM_24"
            ):
                raise ValueError("fine-stem canary audio artifact differs")
            artifact_paths.add(relative)
    guards = value.get("guards", {})
    if any(
        guards.get(key) != expected
        for key, expected in {
            "network_attempts": 0,
            "forbidden_audio_attempts": 0,
            "external_checkpoint_attempts": 0,
            "restricted_torch_load_calls": 1,
            "forward_calls": plan["execution"]["model_forward_calls"],
            "expected_forward_calls": plan["execution"]["model_forward_calls"],
            "os_network_denial_required": True,
        }.items()
    ):
        raise ValueError("fine-stem canary execution guard differs")
    resource = value.get("resource", {})
    elapsed = resource.get("elapsed_seconds")
    peak = resource.get("peak_mlx_memory_bytes")
    if (
        not isinstance(elapsed, (int, float))
        or isinstance(elapsed, bool)
        or not math.isfinite(elapsed)
        or not 0 <= elapsed <= plan["execution"]["maximum_elapsed_seconds"]
        or not isinstance(peak, int)
        or isinstance(peak, bool)
        or not 0 <= peak <= plan["execution"]["maximum_peak_mlx_memory_bytes"]
        or resource.get("elapsed_ceiling_seconds")
        != plan["execution"]["maximum_elapsed_seconds"]
        or resource.get("memory_ceiling_bytes")
        != plan["execution"]["maximum_peak_mlx_memory_bytes"]
    ):
        raise ValueError("fine-stem canary resource evidence differs")
    effects = value.get("effects", {})
    expected = {
        "checkpoint_loads": 1,
        "model_constructions": 1,
        "inference_attempts": MAXIMUM_CASES,
        "audio_reads": MAXIMUM_CASES,
        "audio_writes": MAXIMUM_CASES * 3,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "automatic_retry": False,
        "human_review_recorded": False,
    }
    if set(effects) != set(expected) or any(
        effects.get(key) != item for key, item in expected.items()
    ):
        raise ValueError("fine-stem canary report expanded authority")
    return copy.deepcopy(dict(value))


__all__ = [
    "CANARY_PLAN_SCHEMA",
    "CANARY_REPORT_SCHEMA",
    "MAXIMUM_CASES",
    "MAXIMUM_ELAPSED_SECONDS",
    "MAXIMUM_PEAK_MLX_MEMORY_BYTES",
    "PROFILE_CONTRACTS",
    "SAMPLE_RATE_HZ",
    "SW_CHECKPOINT",
    "SW_CONFIG",
    "SW_NATIVE_ROLES",
    "WINDOW_FRAMES",
    "WINDOW_SECONDS",
    "build_fine_stem_canary_plan",
    "canary_document_sha256",
    "validate_fine_stem_canary_plan",
    "validate_fine_stem_canary_report",
]
