"""Pure contracts for one bounded private full-song six-role execution."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import PurePosixPath
import random
from typing import Any, Mapping, Sequence

from .separation_fine_stem_full_song_plan_contract import (
    validate_fine_stem_full_song_plan,
)
from .separation_other_refinement_next_synthetic_plan import (
    ALIGNED_CHUNK_SIZE,
    ALIGNED_STEP_SIZE,
)


EXECUTION_REQUEST_SCHEMA = (
    "sunofriend.fine-stem-full-song-six-role-execution-request.v1"
)
REPORT_SCHEMA = "sunofriend.fine-stem-full-song-six-role-report.v1"
REPORT_STATUS = "objective_execution_complete_private_review_required"
FAILURE_SCHEMA = "sunofriend.fine-stem-full-song-six-role-failure.v1"
WORKER_REQUEST_SCHEMA = "sunofriend.fine-stem-full-song-six-role-worker-request.v1"
WORKER_RESULT_SCHEMA = "sunofriend.fine-stem-full-song-six-role-worker-result.v1"
ARTIFACT_ROLES = (
    "reference",
    "vocals",
    "drums",
    "bass",
    "synth",
    "guitar",
    "other",
    "reconstruction_check",
)
PROFILE_MODES = ("scnet", "mega53-synth", "sw-guitar")
SW_CHUNK_SIZE = 588_800
SW_OVERLAP = 2
SW_STEP_SIZE = SW_CHUNK_SIZE // SW_OVERLAP
SW_BORDER_SIZE = SW_CHUNK_SIZE - SW_STEP_SIZE
SCNET_SEGMENT_FRAMES = 11 * 44_100
SCNET_STRIDE_FRAMES = int(0.75 * SCNET_SEGMENT_FRAMES)
SCNET_SHIFT_FRAMES = int(0.5 * 44_100)
SCNET_SHIFT_OFFSET_FRAMES = random.Random(0).randint(0, SCNET_SHIFT_FRAMES)
MAXIMUM_RECONSTRUCTION_ERROR_LSB = 2


def _sha256_document(value: Mapping[str, Any], *, excluded: Sequence[str]) -> str:
    payload = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def execution_request_sha256(value: Mapping[str, Any]) -> str:
    return _sha256_document(value, excluded=("document_sha256",))


def report_sha256(value: Mapping[str, Any]) -> str:
    return _sha256_document(value, excluded=("report_sha256",))


def mega53_chunk_starts(frames: int) -> tuple[int, ...]:
    """Return the minimal overlap-2 starts that cover one complete clock."""

    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        raise ValueError("Mega-53 full-song frame count differs")
    starts = [0]
    while starts[-1] + ALIGNED_CHUNK_SIZE < frames:
        starts.append(starts[-1] + ALIGNED_STEP_SIZE)
    return tuple(starts)


def sw_forward_calls(frames: int) -> int:
    """Mirror the verified SW backend's reflect-pad and overlap loop."""

    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        raise ValueError("BS-RoFormer-SW full-song frame count differs")
    total = frames
    if frames > 2 * SW_BORDER_SIZE:
        total += 2 * SW_BORDER_SIZE
    return math.ceil(total / SW_STEP_SIZE)


def scnet_forward_calls(frames: int) -> int:
    """Mirror the fixed seed-0 shift and sequential split contract."""

    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        raise ValueError("SCNet full-song frame count differs")
    shifted = frames + SCNET_SHIFT_FRAMES - SCNET_SHIFT_OFFSET_FRAMES
    return math.ceil(shifted / SCNET_STRIDE_FRAMES)


def full_song_forward_budget(plan: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_fine_stem_full_song_plan(plan)
    cases = []
    scnet_total = 0
    mega_total = 0
    guitar_total = 0
    for case in validated["cases"]:
        frames = int(case["full_song_source"]["expected_canonical_frames"])
        mega_starts = mega53_chunk_starts(frames)
        sw_calls = sw_forward_calls(frames)
        scnet_calls = scnet_forward_calls(frames)
        scnet_total += scnet_calls
        mega_total += len(mega_starts)
        guitar_total += sw_calls
        cases.append(
            {
                "track_id": case["track_id"],
                "canonical_frames": frames,
                "scnet_forward_calls": scnet_calls,
                "mega53_forward_calls": len(mega_starts),
                "mega53_chunk_starts": list(mega_starts),
                "sw_forward_calls": sw_calls,
            }
        )
    return {
        "cases": cases,
        "scnet_profile_attempts": 3,
        "scnet_shift_offset_frames": SCNET_SHIFT_OFFSET_FRAMES,
        "scnet_forward_calls": scnet_total,
        "mega53_profile_attempts": 3,
        "mega53_forward_calls": mega_total,
        "sw_profile_attempts": 3,
        "sw_forward_calls": guitar_total,
        "profile_attempts": 9,
    }


def build_execution_request(
    plan: Mapping[str, Any], *, proposed_output: str
) -> dict[str, Any]:
    """Build a path-light no-effects request from one immutable plan."""

    validated = validate_fine_stem_full_song_plan(plan)
    if not proposed_output or not proposed_output.startswith("/"):
        raise ValueError("full-song execution output must be absolute")
    request: dict[str, Any] = {
        "schema": EXECUTION_REQUEST_SCHEMA,
        "document_sha256": "",
        "status": "explicit_exact_hash_approval_required",
        "plan_sha256": validated["document_sha256"],
        "proposed_output": proposed_output,
        "source_bindings": [
            {
                "track_id": case["track_id"],
                "source_sha256": case["full_song_source"]["sha256"],
                "source_bytes": case["full_song_source"]["bytes"],
                "rights_category": case["rights_category"],
                "expected_canonical_frames": case["full_song_source"][
                    "expected_canonical_frames"
                ],
                "scored_target_roles": case["scored_target_roles"],
            }
            for case in validated["cases"]
        ],
        "forward_budget": full_song_forward_budget(validated),
        "execution_contract": copy.deepcopy(validated["execution_contract"]),
        "output_contract": copy.deepcopy(validated["output_contract"]),
        "review_contract": copy.deepcopy(validated["review_contract"]),
        "next_approval": copy.deepcopy(validated["next_approval"]),
        "effects": {
            "source_content_reads": 0,
            "canonical_audio_writes": 0,
            "model_loads": 0,
            "inference_attempts": 0,
            "audio_writes": 0,
            "network_attempts": 0,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
    }
    request["document_sha256"] = execution_request_sha256(request)
    return validate_execution_request(request, validated)


def validate_execution_request(
    value: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    validated_plan = validate_fine_stem_full_song_plan(plan)
    request = copy.deepcopy(dict(value))
    if (
        request.get("schema") != EXECUTION_REQUEST_SCHEMA
        or request.get("status") != "explicit_exact_hash_approval_required"
        or request.get("plan_sha256") != validated_plan["document_sha256"]
        or request.get("document_sha256") != execution_request_sha256(request)
        or request.get("forward_budget") != full_song_forward_budget(validated_plan)
    ):
        raise ValueError("full-song execution request identity differs")
    if request.get("next_approval") != validated_plan["next_approval"]:
        raise ValueError("full-song execution approval boundary differs")
    expected_bindings = [
        {
            "track_id": case["track_id"],
            "source_sha256": case["full_song_source"]["sha256"],
            "source_bytes": case["full_song_source"]["bytes"],
            "rights_category": case["rights_category"],
            "expected_canonical_frames": case["full_song_source"][
                "expected_canonical_frames"
            ],
            "scored_target_roles": case["scored_target_roles"],
        }
        for case in validated_plan["cases"]
    ]
    if (
        request.get("source_bindings") != expected_bindings
        or request.get("execution_contract") != validated_plan["execution_contract"]
        or request.get("output_contract") != validated_plan["output_contract"]
        or request.get("review_contract") != validated_plan["review_contract"]
        or not str(request.get("proposed_output", "")).startswith("/")
    ):
        raise ValueError("full-song execution request contract differs")
    expected_effects = {
        "source_content_reads": 0,
        "canonical_audio_writes": 0,
        "model_loads": 0,
        "inference_attempts": 0,
        "audio_writes": 0,
        "network_attempts": 0,
        "automatic_retry": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
    }
    if request.get("effects") != expected_effects:
        raise ValueError("full-song execution request effects differ")
    return request


def validate_full_song_report(
    value: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    validated_plan = validate_fine_stem_full_song_plan(plan)
    report = copy.deepcopy(dict(value))
    if (
        report.get("schema") != REPORT_SCHEMA
        or report.get("status") != REPORT_STATUS
        or report.get("plan_sha256") != validated_plan["document_sha256"]
        or report.get("approved_plan_sha256") != validated_plan["document_sha256"]
        or report.get("report_sha256") != report_sha256(report)
        or report.get("release_tier") != "private_studio_challenger"
        or report.get("profiles") != validated_plan["profiles"]
    ):
        raise ValueError("full-song execution report identity differs")
    runtime = report.get("runtime", {})
    if (
        runtime.get("network_denied_by_parent_sandbox") is not True
        or runtime.get("models_run_sequentially") is not True
        or runtime.get("writer_count") != 1
    ):
        raise ValueError("full-song execution runtime boundary differs")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("full-song execution report cases differ")
    plan_by_track = {case["track_id"]: case for case in validated_plan["cases"]}
    if {case.get("track_id") for case in cases} != set(plan_by_track):
        raise ValueError("full-song execution report track identities differ")
    for case in cases:
        planned = plan_by_track[case["track_id"]]
        frames = planned["full_song_source"]["expected_canonical_frames"]
        if (
            case.get("scored_target_roles") != planned["scored_target_roles"]
            or case.get("unscored_target_roles") != planned["unscored_target_roles"]
            or case.get("rights_category") != planned["rights_category"]
            or case.get("confirmed_present_targets")
            != planned["confirmed_present_targets"]
            or case.get("source_input", {}).get("bytes")
            != planned["full_song_source"]["bytes"]
            or case.get("source_input", {}).get("sha256")
            != planned["full_song_source"]["sha256"]
            or set(case.get("artifacts", {})) != set(ARTIFACT_ROLES)
            or case.get("maximum_reconstruction_error_lsb", 3)
            > MAXIMUM_RECONSTRUCTION_ERROR_LSB
            or case.get("projection", {}).get("method")
            != "fixed grouped-other-constrained three-way Wiener mask"
        ):
            raise ValueError("full-song execution case contract differs")
        for artifact in case["artifacts"].values():
            if (
                artifact.get("sample_rate_hz") != 44_100
                or artifact.get("channels") != 2
                or artifact.get("frames") != frames
                or artifact.get("subtype") != "PCM_24"
                or not isinstance(artifact.get("bytes"), int)
                or artifact["bytes"] <= 0
                or not isinstance(artifact.get("sha256"), str)
                or len(artifact["sha256"]) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in artifact["sha256"]
                )
                or not isinstance(artifact.get("relative_path"), str)
                or artifact["relative_path"].startswith("/")
                or ".." in PurePosixPath(artifact["relative_path"]).parts
            ):
                raise ValueError("full-song persisted artifact clock differs")
        if (
            case.get("elapsed_seconds", math.inf)
            > validated_plan["execution_contract"]["maximum_elapsed_seconds_per_song"]
        ):
            raise ValueError("full-song per-song resource gate differs")
    if report.get("forward_budget") != full_song_forward_budget(validated_plan):
        raise ValueError("full-song forward accounting differs")
    workers = report.get("workers", {})
    expected_worker_profiles = {
        "core_four": validated_plan["profiles"]["core_four"]["profile_id"],
        "synth": validated_plan["profiles"]["synth"]["profile_id"],
        "guitar": validated_plan["profiles"]["guitar"]["profile_id"],
    }
    if set(workers) != set(expected_worker_profiles):
        raise ValueError("full-song worker set differs")
    budget = full_song_forward_budget(validated_plan)
    expected_forward_calls = {
        "core_four": budget["scnet_forward_calls"],
        "synth": budget["mega53_forward_calls"],
        "guitar": budget["sw_forward_calls"],
    }
    for role, profile_id in expected_worker_profiles.items():
        worker = workers[role]
        if (
            worker.get("profile_id") != profile_id
            or worker.get("model_loads") != 1
            or worker.get("profile_inference_attempts") != 3
            or worker.get("network_attempts") != 0
            or worker.get("runtime", {}).get("network_denied") is not True
        ):
            raise ValueError("full-song worker identity differs")
        if worker.get("internal_forward_calls") != expected_forward_calls[role]:
            raise ValueError("full-song specialist forward accounting differs")
    effects = report.get("effects", {})
    if (
        effects.get("model_loads") != 3
        or effects.get("profile_inference_attempts") != 9
        or effects.get("source_files") != 3
        or effects.get("canonicalization_attempts") != 3
        or effects.get("audio_writes") != 24
        or effects.get("network_attempts") != 0
        or effects.get("automatic_retry") is not False
        or any(
            effects.get(key) is not False
            for key in (
                "public_activation",
                "source_selection",
                "midi_created",
                "hosting",
                "redistribution",
                "audio_upload",
            )
        )
    ):
        raise ValueError("full-song execution report effects differ")
    resources = report.get("resources", {})
    accounting = report.get("accounting", {})
    if (
        resources.get("within_ceilings") is not True
        or resources.get("elapsed_seconds", math.inf)
        > validated_plan["execution_contract"]["maximum_total_elapsed_seconds"]
        or resources.get("peak_memory_bytes", math.inf)
        > validated_plan["execution_contract"]["maximum_peak_unified_memory_bytes"]
    ):
        raise ValueError("full-song execution resource gate differs")
    if (
        accounting.get("projection") != validated_plan["output_contract"]["projection"]
        or accounting.get("maximum_reconstruction_error_lsb")
        != max(case["maximum_reconstruction_error_lsb"] for case in cases)
        or accounting.get("reconstruction_accounting_is_separation_accuracy")
        is not False
    ):
        raise ValueError("full-song execution accounting differs")
    return report


__all__ = [
    "ARTIFACT_ROLES",
    "EXECUTION_REQUEST_SCHEMA",
    "FAILURE_SCHEMA",
    "PROFILE_MODES",
    "REPORT_SCHEMA",
    "REPORT_STATUS",
    "WORKER_REQUEST_SCHEMA",
    "WORKER_RESULT_SCHEMA",
    "build_execution_request",
    "execution_request_sha256",
    "full_song_forward_budget",
    "mega53_chunk_starts",
    "report_sha256",
    "scnet_forward_calls",
    "sw_forward_calls",
    "validate_execution_request",
    "validate_full_song_report",
]
