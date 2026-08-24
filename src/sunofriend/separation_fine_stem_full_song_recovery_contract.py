"""Pure request and report contracts for model-free full-song recovery.

The public recovery facade owns execution. This module owns only immutable
schema identity and validation, so callers do not need filesystem, NumPy,
publication or review-rendering knowledge to interpret retained evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ._private_verified_audio_inputs import require_safe_private_basename
from .separation_fine_stem_full_song_execution_contract import (
    ARTIFACT_ROLES,
    full_song_forward_budget,
)
from .separation_fine_stem_full_song_plan_contract import (
    validate_fine_stem_full_song_plan,
)


RECOVERY_REQUEST_SCHEMA = "sunofriend.fine-stem-full-song-six-role-recovery-request.v1"
RECOVERY_REQUEST_STATUS = "explicit_exact_hash_no_model_recovery_approval_required"
RECOVERY_REPORT_SCHEMA = "sunofriend.fine-stem-full-song-six-role-recovery-report.v1"
RECOVERY_REPORT_STATUS = (
    "private_review_package_recovered_model_free_resource_gate_incomplete"
)
JSON_EVIDENCE = {
    "failure_report": "FAILED-REPORT.json",
    "scnet_request": "TEMP/scnet-request.json",
    "scnet_result": "TEMP/scnet-result.json",
    "synth_request": "TEMP/mega53-synth-request.json",
    "synth_result": "TEMP/mega53-synth-result.json",
    "guitar_request": "TEMP/sw-guitar-request.json",
}
RECOVERY_AUDIO_READS = 21
RECOVERY_AUDIO_WRITES = 24
RECOVERY_RETAINED_VERIFICATION_PASSES = 3
RETAINED_TREE_FILES = len(JSON_EVIDENCE) + RECOVERY_AUDIO_READS
AUDIO_PAYLOAD_SUFFIXES = {
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".npy",
    ".wav",
}
_DIRECTORY_INTEGER_FIELDS = (
    "device",
    "inode",
    "uid",
    "mtime_ns",
    "ctime_ns",
    "mode",
)
_OBSERVED_FILE_FIELDS = (
    "device",
    "inode",
    "bytes",
    "mtime_ns",
    "ctime_ns",
    "mode",
    "uid",
)
_INPUT_ROLES = {
    "reference",
    "vocals",
    "drums",
    "bass",
    "other",
    "synth",
    "guitar",
}


def _document_sha256(value: Mapping[str, Any], field: str) -> str:
    payload = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def recovery_request_sha256(value: Mapping[str, Any]) -> str:
    return _document_sha256(value, "document_sha256")


def recovery_report_sha256(value: Mapping[str, Any]) -> str:
    return _document_sha256(value, "report_sha256")


def value_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def case_ids(plan: Mapping[str, Any]) -> list[str]:
    return [
        require_safe_private_basename(
            case["track_id"], label="full-song recovery track id"
        )
        for case in plan["cases"]
    ]


def finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _private_directories_are_valid(directories: Any) -> bool:
    return (
        isinstance(directories, list)
        and bool(directories)
        and directories[0].get("relative_path") == "."
        and directories[0].get("mode") == 0o700
        and all(
            all(isinstance(item.get(field), int) for field in _DIRECTORY_INTEGER_FIELDS)
            for item in directories
        )
        and all(item.get("mode") in {0o700, 0o755} for item in directories[1:])
    )


def _private_files_are_valid(files: Any) -> bool:
    return (
        isinstance(files, list)
        and all(item.get("mode") == 0o600 for item in files)
        and all(
            item.get("uid") == os.geteuid() and item.get("links") == 1
            for item in files
        )
    )


def _legacy_mode_count_is_valid(
    tree: Mapping[str, Any], directories: Sequence[Mapping[str, Any]]
) -> bool:
    return tree.get("legacy_inner_directory_modes_0755") == sum(
        item.get("mode") == 0o755 for item in directories[1:]
    )


def _validate_request_identity(
    request: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    if (
        request.get("schema") != RECOVERY_REQUEST_SCHEMA
        or request.get("status") != RECOVERY_REQUEST_STATUS
        or request.get("document_sha256") != recovery_request_sha256(request)
        or request.get("original_plan_sha256") != plan["document_sha256"]
        or len(request.get("retained_payloads", [])) != RECOVERY_AUDIO_READS
        or len(request.get("retained_json", {})) != len(JSON_EVIDENCE)
        or len(request.get("retained_tree", {}).get("files", []))
        != RETAINED_TREE_FILES
    ):
        raise ValueError("full-song recovery request identity differs")


def _validate_output_binding(request: Mapping[str, Any]) -> None:
    failed_path = Path(str(request.get("failed_root", "")))
    output_path = Path(str(request.get("proposed_output", "")))
    if (
        not failed_path.is_absolute()
        or not output_path.is_absolute()
        or output_path.parent != failed_path.parent
        or output_path == failed_path
    ):
        raise ValueError("full-song recovery request output binding differs")
    parent = request.get("output_parent_binding", {})
    if (
        parent.get("absolute_path") != str(output_path.parent)
        or parent.get("uid") != os.geteuid()
        or not isinstance(parent.get("device"), int)
        or not isinstance(parent.get("inode"), int)
        or not isinstance(parent.get("mode"), int)
        or parent["mode"] & 0o022
    ):
        raise ValueError("full-song recovery request parent binding differs")


def _validate_retained_tree(
    request: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    tree = request["retained_tree"]
    directories = tree.get("directories", [])
    files = tree.get("files", [])
    if not _private_directories_are_valid(directories):
        raise ValueError("full-song recovery retained tree contract differs")
    if not _private_files_are_valid(files):
        raise ValueError("full-song recovery retained tree contract differs")
    if not _legacy_mode_count_is_valid(tree, directories):
        raise ValueError("full-song recovery retained tree contract differs")
    retained_paths = {item.get("relative_path") for item in files}
    expected_paths = {
        *JSON_EVIDENCE.values(),
        *(item.get("relative_path") for item in request["retained_payloads"]),
    }
    if retained_paths != expected_paths:
        raise ValueError("full-song recovery retained tree contract differs")
    return files


def _validate_retained_json(
    request: Mapping[str, Any], retained_files: Sequence[Mapping[str, Any]]
) -> None:
    retained_json = request["retained_json"]
    if set(retained_json) != set(JSON_EVIDENCE) or any(
        identity.get("relative_path") != JSON_EVIDENCE[name]
        or not isinstance(identity.get("bytes"), int)
        or identity["bytes"] <= 0
        or len(identity.get("sha256", "")) != 64
        for name, identity in retained_json.items()
    ):
        raise ValueError("full-song recovery retained JSON binding differs")
    files_by_path = {item["relative_path"]: item for item in retained_files}
    for identity in retained_json.values():
        approved = files_by_path[identity["relative_path"]]
        observed = identity.get("observed_file_identity", {})
        if any(observed.get(field) != approved[field] for field in _OBSERVED_FILE_FIELDS):
            raise ValueError("full-song recovery JSON descriptor binding differs")
        if observed.get("links") != approved["links"]:
            raise ValueError("full-song recovery JSON descriptor binding differs")


def _expected_payload_path(track: str, role: str) -> str:
    if role == "reference":
        return f"TEMP/canonical/{track}/reference.wav"
    folder = "scnet" if role in {"vocals", "drums", "bass", "other"} else role
    return f"TEMP/{folder}/{track}/{role}.npy"


def _expected_payload_kind(role: str) -> str:
    if role == "reference":
        return "canonical_pcm24"
    if role == "guitar":
        return "float32_estimate_unreceipted"
    return "float32_estimate"


def _validate_retained_payloads(
    request: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    payloads = request["retained_payloads"]
    expected_roles = {
        (case["track_id"], role) for case in plan["cases"] for role in _INPUT_ROLES
    }
    if {(item.get("track_id"), item.get("role")) for item in payloads} != expected_roles:
        raise ValueError("full-song recovery retained payload roles differ")
    frames_by_track = {
        case["track_id"]: case["full_song_source"]["expected_canonical_frames"]
        for case in plan["cases"]
    }
    for item in payloads:
        role = item["role"]
        track = item["track_id"]
        if (
            item.get("kind") != _expected_payload_kind(role)
            or item.get("relative_path") != _expected_payload_path(track, role)
            or item.get("expected_frames") != frames_by_track[track]
            or len(item.get("expected_sha256", "")) != 64
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
            or item.get("mode") != 0o600
            or item.get("content_opened") is not (role == "guitar")
        ):
            raise ValueError("full-song recovery retained payload identity differs")


def _validate_implementation(request: Mapping[str, Any]) -> None:
    implementation = request.get("implementation")
    if (
        not isinstance(implementation, list)
        or len(implementation) < 7
        or len({item.get("relative_path") for item in implementation})
        != len(implementation)
        or any(len(item.get("sha256", "")) != 64 for item in implementation)
    ):
        raise ValueError("full-song recovery implementation binding differs")


def _prior_report_file(files: Any) -> Mapping[str, Any] | None:
    if not isinstance(files, list):
        return None
    return next(
        (item for item in files if item.get("relative_path") == "FAILED-REPORT.json"),
        None,
    )


def _prior_audio_count(files: Any) -> int:
    if not isinstance(files, list):
        return -1
    return sum(
        PurePosixPath(item.get("relative_path", "")).suffix.lower()
        in AUDIO_PAYLOAD_SUFFIXES
        for item in files
    )


def _validate_prior_identity(
    prior: Any,
    tree: Mapping[str, Any],
    files: Any,
    directories: Any,
) -> None:
    if (
        not isinstance(prior, dict)
        or prior.get("must_remain_unchanged") is not True
        or not isinstance(prior.get("root"), str)
        or len(prior.get("failure_report", {}).get("sha256", "")) != 64
        or not isinstance(files, list)
        or not files
        or any(len(item.get("sha256", "")) != 64 for item in files)
        or not _private_directories_are_valid(directories)
        or not _private_files_are_valid(files)
        or not _legacy_mode_count_is_valid(tree, directories)
    ):
        raise ValueError("full-song recovery prior failure binding differs")


def _validate_prior_hashes(
    prior: Mapping[str, Any],
    tree: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    audio_count: int,
) -> None:
    report_file = _prior_report_file(files)
    if (
        prior.get("tree_binding_sha256") != value_sha256(tree)
        or prior.get("files_content_hashed") != len(files)
        or prior.get("audio_payloads_content_hashed") != audio_count
        or not isinstance(report_file, Mapping)
        or prior.get("failure_report", {}).get("sha256")
        != report_file.get("sha256")
        or prior.get("failure_report", {}).get("bytes") != report_file.get("bytes")
    ):
        raise ValueError("full-song recovery prior failure binding differs")


def _validate_prior_package(request: Mapping[str, Any]) -> tuple[int, int]:
    prior = request.get("prior_failed_package")
    tree = prior.get("tree", {}) if isinstance(prior, dict) else {}
    files = tree.get("files", [])
    directories = tree.get("directories", [])
    _validate_prior_identity(prior, tree, files, directories)
    audio_count = _prior_audio_count(files)
    _validate_prior_hashes(prior, tree, files, audio_count)
    return len(files), audio_count


def _expected_recovery_contract(
    *, prior_file_count: int, prior_audio_count: int
) -> dict[str, Any]:
    passes = RECOVERY_RETAINED_VERIFICATION_PASSES
    return {
        "network_denied": True,
        "parent_sandbox_reexecs": 1,
        "model_worker_subprocesses": 0,
        "failed_package_preserved_byte_for_byte": True,
        "canonicalization_attempts": 0,
        "checkpoint_loads": 0,
        "model_constructions": 0,
        "model_loads": 0,
        "inference_attempts": 0,
        "private_audio_reads": RECOVERY_AUDIO_READS,
        "current_audio_payload_file_opens": RECOVERY_AUDIO_READS,
        "retained_json_file_opens": len(JSON_EVIDENCE) * passes,
        "retained_guitar_array_hash_opens": 3 * passes,
        "prior_failed_audio_payload_hash_opens": prior_audio_count * passes,
        "prior_failed_file_hash_opens": prior_file_count * passes,
        "retained_evidence_verification_passes": passes,
        "pcm24_audio_writes": RECOVERY_AUDIO_WRITES,
        "writer_count": 1,
        "automatic_retry": False,
        "fresh_atomic_output": True,
    }


def _validate_incomplete_evidence(request: Mapping[str, Any]) -> None:
    incomplete = request.get("incomplete_historical_evidence", {})
    if (
        incomplete.get("guitar_worker_result_receipt") is not False
        or incomplete.get("guitar_guard_counters_persisted") is not False
        or incomplete.get("guitar_peak_memory_persisted") is not False
        or incomplete.get("guitar_resource_gate_complete") is not False
        or incomplete.get("full_objective_qualification_allowed") is not False
    ):
        raise ValueError("full-song recovery incompleteness differs")


def _expected_request_effects(
    *, prior_file_count: int, prior_audio_count: int
) -> dict[str, Any]:
    return {
        "audio_payloads_opened": 3 + prior_audio_count,
        "retained_json_files_content_read": len(JSON_EVIDENCE),
        "guitar_arrays_content_hashed": 3,
        "prior_failed_files_content_hashed": prior_file_count,
        "prior_failed_audio_payloads_content_hashed": prior_audio_count,
        "audio_writes": 0,
        "checkpoint_loads": 0,
        "model_constructions": 0,
        "model_loads": 0,
        "inference_attempts": 0,
        "network_attempts": 0,
        "automatic_retry": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
    }


def validate_recovery_request(
    value: Mapping[str, Any], plan_value: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a defensive copy of one exact, model-free recovery request."""

    plan = validate_fine_stem_full_song_plan(plan_value)
    request = copy.deepcopy(dict(value))
    _validate_request_identity(request, plan)
    _validate_output_binding(request)
    retained_files = _validate_retained_tree(request)
    _validate_retained_json(request, retained_files)
    _validate_retained_payloads(request, plan)
    _validate_implementation(request)
    prior_file_count, prior_audio_count = _validate_prior_package(request)
    if request.get("recovery_contract") != _expected_recovery_contract(
        prior_file_count=prior_file_count,
        prior_audio_count=prior_audio_count,
    ):
        raise ValueError("full-song recovery effects contract differs")
    _validate_incomplete_evidence(request)
    if request.get("effects") != _expected_request_effects(
        prior_file_count=prior_file_count,
        prior_audio_count=prior_audio_count,
    ):
        raise ValueError("full-song recovery preflight contains effects")
    return request


def _validate_report_identity(
    report: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    if (
        report.get("schema") != RECOVERY_REPORT_SCHEMA
        or report.get("status") != RECOVERY_REPORT_STATUS
        or report.get("report_sha256") != recovery_report_sha256(report)
        or report.get("plan_sha256") != plan["document_sha256"]
        or report.get("release_tier") != "private_studio_challenger"
        or report.get("full_objective_qualification") is not False
        or report.get("public_activation_allowed") is not False
        or report.get("profiles") != plan["profiles"]
    ):
        raise ValueError("full-song recovery report identity differs")


def _request_payloads(
    report: Mapping[str, Any],
    plan: Mapping[str, Any],
    request_value: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[tuple[str, str], Mapping[str, Any]] | None]:
    if request_value is None:
        return None, None
    request = validate_recovery_request(request_value, plan)
    if report.get("recovery_request_sha256") != request["document_sha256"]:
        raise ValueError("full-song recovery report request binding differs")
    payloads = {
        (item["track_id"], item["role"]): item
        for item in request["retained_payloads"]
    }
    return request, payloads


def _validate_case_contract(
    case: Mapping[str, Any], planned: Mapping[str, Any]
) -> None:
    correction = case.get("scnet_native_other_correction", {})
    if (
        case.get("title") != planned["title"]
        or case.get("rights_category") != planned["rights_category"]
        or case.get("scored_target_roles") != planned["scored_target_roles"]
        or case.get("unscored_target_roles") != planned["unscored_target_roles"]
        or case.get("confirmed_present_targets")
        != planned["confirmed_present_targets"]
        or set(case.get("artifacts", {})) != set(ARTIFACT_ROLES)
        or not isinstance(case.get("maximum_reconstruction_error_lsb"), int)
        or not 0 <= case["maximum_reconstruction_error_lsb"] <= 2
        or not finite_nonnegative(case.get("recovery_elapsed_seconds"))
        or not finite_nonnegative(case.get("shared_attenuation"))
        or not 0 < float(case["shared_attenuation"]) <= 1
        or correction.get("used_for_separation_accuracy_claim") is not False
        or not finite_nonnegative(correction.get("rms"))
        or not finite_nonnegative(correction.get("peak"))
    ):
        raise ValueError("full-song recovery case contract differs")


def _validate_projection(case: Mapping[str, Any]) -> None:
    projection = case.get("projection", {})
    corrections = projection.get("raw_to_projected_correction", {})
    if (
        projection.get("method")
        != "fixed grouped-other-constrained three-way Wiener mask"
        or not finite_nonnegative(projection.get("maximum_float_reconstruction_error"))
        or set(corrections) != {"synth", "guitar"}
        or any(
            not finite_nonnegative(corrections[role].get(field))
            for role in ("synth", "guitar")
            for field in ("rms", "peak")
        )
    ):
        raise ValueError("full-song recovery projection accounting differs")


def _validate_artifact(
    artifact: Mapping[str, Any], *, track_id: str, role: str, frames: int
) -> None:
    relative_path = artifact.get("relative_path")
    if (
        artifact.get("sample_rate_hz") != 44_100
        or artifact.get("channels") != 2
        or artifact.get("frames") != frames
        or artifact.get("subtype") != "PCM_24"
        or not isinstance(artifact.get("bytes"), int)
        or artifact["bytes"] <= 0
        or not isinstance(artifact.get("sha256"), str)
        or len(artifact["sha256"]) != 64
        or not isinstance(relative_path, str)
        or relative_path != f"CASES/{track_id}/{role}.wav"
        or relative_path.startswith("/")
        or ".." in PurePosixPath(relative_path).parts
    ):
        raise ValueError("full-song recovery persisted artifact differs")


def _validate_report_cases(
    report: Mapping[str, Any], plan: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    cases = report.get("cases")
    plan_by_track = {case["track_id"]: case for case in plan["cases"]}
    if (
        not isinstance(cases, list)
        or {case.get("track_id") for case in cases} != set(plan_by_track)
        or len(cases) != 3
    ):
        raise ValueError("full-song recovery report cases differ")
    for case in cases:
        planned = plan_by_track[case["track_id"]]
        frames = planned["full_song_source"]["expected_canonical_frames"]
        _validate_case_contract(case, planned)
        _validate_projection(case)
        for role, artifact in case["artifacts"].items():
            _validate_artifact(
                artifact, track_id=case["track_id"], role=role, frames=frames
            )
    return cases


def _validate_receipted_worker_summary(
    value: Mapping[str, Any],
    *,
    profile_id: str,
    expected_case_ids: Sequence[str],
    expected_forward_calls: int,
) -> None:
    elapsed = value.get("case_elapsed_seconds")
    runtime = value.get("runtime")
    if (
        value.get("profile_id") != profile_id
        or value.get("evidence_origin") != "persisted_worker_receipt"
        or value.get("result_receipt_persisted") is not True
        or value.get("model_loads") != 1
        or value.get("profile_inference_attempts") != 3
        or value.get("internal_forward_calls") != expected_forward_calls
        or not isinstance(elapsed, dict)
        or set(elapsed) != set(expected_case_ids)
        or any(not finite_nonnegative(item) for item in elapsed.values())
        or not finite_nonnegative(value.get("elapsed_seconds"))
        or not isinstance(value.get("peak_memory_bytes"), int)
        or value["peak_memory_bytes"] <= 0
        or value.get("network_attempts") != 0
        or not isinstance(runtime, dict)
        or runtime.get("network_denied") is not True
    ):
        raise ValueError("full-song recovery retained worker summary differs")


def _validate_guitar_summary(
    guitar: Mapping[str, Any], plan: Mapping[str, Any]
) -> None:
    if (
        guitar.get("profile_id") != plan["profiles"]["guitar"]["profile_id"]
        or guitar.get("evidence_origin")
        != "reconstructed_from_bound_request_and_complete_arrays"
        or guitar.get("result_receipt_persisted") is not False
        or guitar.get("guard_counters_persisted") is not False
        or guitar.get("peak_memory_bytes") is not None
        or guitar.get("profile_inference_attempts") != 3
        or guitar.get("internal_forward_calls") is not None
        or guitar.get("expected_internal_forward_calls")
        != full_song_forward_budget(plan)["sw_forward_calls"]
        or guitar.get("internal_forward_calls_evidence")
        != "derived_from_bound_backend_and_complete_outputs_not_receipted"
    ):
        raise ValueError("full-song recovery resource incompleteness differs")


def _validate_incomplete_resource_gate(resources: Mapping[str, Any]) -> None:
    if (
        resources.get("guitar_resource_gate_complete") is not False
        or resources.get("full_resource_gate_complete") is not False
        or resources.get("within_known_ceilings") is not None
    ):
        raise ValueError("full-song recovery resource incompleteness differs")


def _validate_resource_measurements(
    resources: Mapping[str, Any], workers: Mapping[str, Any]
) -> None:
    expected_peaks = {
        "core_four": workers["core_four"]["peak_memory_bytes"],
        "synth": workers["synth"]["peak_memory_bytes"],
        "guitar": None,
    }
    if (
        resources.get("known_peak_memory_bytes") != expected_peaks
        or not finite_nonnegative(resources.get("failed_attempt_elapsed_seconds"))
        or not finite_nonnegative(resources.get("recovery_elapsed_seconds"))
        or not isinstance(resources.get("recovery_peak_resident_set_bytes"), int)
        or resources["recovery_peak_resident_set_bytes"] <= 0
    ):
        raise ValueError("full-song recovery resource incompleteness differs")


def _validate_guitar_resources(
    guitar: Mapping[str, Any],
    resources: Mapping[str, Any],
    workers: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    _validate_guitar_summary(guitar, plan)
    _validate_incomplete_resource_gate(resources)
    _validate_resource_measurements(resources, workers)


def _validate_workers(
    report: Mapping[str, Any], plan: Mapping[str, Any]
) -> list[str]:
    workers = report.get("workers", {})
    if not isinstance(workers, dict) or set(workers) != {
        "core_four",
        "synth",
        "guitar",
    }:
        raise ValueError("full-song recovery worker summaries differ")
    expected_case_ids = case_ids(plan)
    budget = full_song_forward_budget(plan)
    _validate_receipted_worker_summary(
        workers["core_four"],
        profile_id=plan["profiles"]["core_four"]["profile_id"],
        expected_case_ids=expected_case_ids,
        expected_forward_calls=budget["scnet_forward_calls"],
    )
    _validate_receipted_worker_summary(
        workers["synth"],
        profile_id=plan["profiles"]["synth"]["profile_id"],
        expected_case_ids=expected_case_ids,
        expected_forward_calls=budget["mega53_forward_calls"],
    )
    _validate_guitar_resources(
        workers["guitar"], report.get("resources", {}), workers, plan
    )
    return expected_case_ids


def _validate_input_identity(
    identity: Mapping[str, Any], *, role: str, frames: int
) -> None:
    expected_dtype = "pcm24_float64_decode" if role == "reference" else "float32"
    if (
        identity.get("shape") != [frames, 2]
        or identity.get("dtype") != expected_dtype
        or identity.get("finite") is not True
        or len(identity.get("sha256", "")) != 64
        or not isinstance(identity.get("bytes"), int)
        or identity["bytes"] <= 0
        or not isinstance(identity.get("relative_path"), str)
    ):
        raise ValueError("full-song recovery input identity differs")
    if role != "reference" and (
        not finite_nonnegative(identity.get("rms"))
        or not finite_nonnegative(identity.get("peak"))
    ):
        raise ValueError("full-song recovery input statistics differ")


def _validate_input_request_binding(
    identity: Mapping[str, Any], approved: Mapping[str, Any]
) -> None:
    observed = identity.get("observed_file_identity", {})
    if (
        identity.get("relative_path") != approved["relative_path"]
        or identity.get("bytes") != approved["bytes"]
        or identity.get("sha256") != approved["expected_sha256"]
        or identity.get("shape") != [approved["expected_frames"], 2]
        or any(observed.get(field) != approved[field] for field in _OBSERVED_FILE_FIELDS)
        or observed.get("links") != approved["links"]
    ):
        raise ValueError("full-song recovery input request binding differs")


def _validate_recovered_inputs(
    report: Mapping[str, Any],
    plan: Mapping[str, Any],
    expected_case_ids: Sequence[str],
    request_payloads: Mapping[tuple[str, str], Mapping[str, Any]] | None,
) -> None:
    recovered = report.get("recovered_inputs")
    if not isinstance(recovered, dict) or set(recovered) != set(expected_case_ids):
        raise ValueError("full-song recovery input identities differ")
    for planned in plan["cases"]:
        track_id = planned["track_id"]
        inputs = recovered[track_id]
        frames = planned["full_song_source"]["expected_canonical_frames"]
        if not isinstance(inputs, dict) or set(inputs) != _INPUT_ROLES:
            raise ValueError("full-song recovery input roles differ")
        for role, identity in inputs.items():
            _validate_input_identity(identity, role=role, frames=frames)
            if request_payloads is not None:
                _validate_input_request_binding(
                    identity, request_payloads[(track_id, role)]
                )


def _validate_accounting(
    report: Mapping[str, Any],
    plan: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
) -> None:
    accounting = report.get("accounting", {})
    if (
        accounting.get("projection") != plan["output_contract"]["projection"]
        or accounting.get("maximum_reconstruction_error_lsb")
        != max(case["maximum_reconstruction_error_lsb"] for case in cases)
        or accounting.get("reconstruction_accounting_is_separation_accuracy")
        is not False
    ):
        raise ValueError("full-song recovery accounting differs")


def _validate_recovery_effect_shape(recovery: Mapping[str, Any]) -> tuple[int, int]:
    prior_audio = recovery.get("prior_failed_audio_payload_hash_opens")
    prior_files = recovery.get("prior_failed_file_hash_opens")
    passes = RECOVERY_RETAINED_VERIFICATION_PASSES
    if (
        not isinstance(prior_audio, int)
        or isinstance(prior_audio, bool)
        or prior_audio < 0
        or prior_audio % passes
        or not isinstance(prior_files, int)
        or isinstance(prior_files, bool)
        or prior_files <= 0
        or prior_files % passes
    ):
        raise ValueError("full-song recovery prior audio verification differs")
    return prior_audio, prior_files


def _expected_report_recovery_effects(
    *, prior_audio_hash_opens: int, prior_file_hash_opens: int
) -> dict[str, Any]:
    return {
        "checkpoint_loads": 0,
        "model_constructions": 0,
        "model_loads": 0,
        "inference_attempts": 0,
        "canonicalization_attempts": 0,
        "parent_sandbox_reexecs": 1,
        "model_worker_subprocesses": 0,
        "private_audio_reads": RECOVERY_AUDIO_READS,
        "current_audio_payload_file_opens": RECOVERY_AUDIO_READS,
        "retained_json_file_opens": (
            len(JSON_EVIDENCE) * RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "retained_guitar_array_hash_opens": (
            3 * RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "prior_failed_audio_payload_hash_opens": prior_audio_hash_opens,
        "prior_failed_file_hash_opens": prior_file_hash_opens,
        "retained_evidence_verification_passes": RECOVERY_RETAINED_VERIFICATION_PASSES,
        "pcm24_audio_writes": RECOVERY_AUDIO_WRITES,
        "network_attempts": 0,
        "automatic_retry": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
    }


def _validate_report_effects(
    report: Mapping[str, Any], request: Mapping[str, Any] | None
) -> None:
    effects = report.get("effects", {})
    if effects.get("historical_failed_attempt") != {
        "model_loads": 3,
        "profile_inference_attempts": 9,
        "canonicalization_attempts": 3,
        "temporary_estimate_writes": 18,
        "automatic_retry": False,
    }:
        raise ValueError("full-song recovery historical effects differ")
    recovery = effects.get("recovery", {})
    prior_audio, prior_files = _validate_recovery_effect_shape(recovery)
    if recovery != _expected_report_recovery_effects(
        prior_audio_hash_opens=prior_audio,
        prior_file_hash_opens=prior_files,
    ):
        raise ValueError("full-song recovery report effects differ")
    if request is not None and (
        prior_audio
        != request["prior_failed_package"]["audio_payloads_content_hashed"]
        * RECOVERY_RETAINED_VERIFICATION_PASSES
        or prior_files
        != request["prior_failed_package"]["files_content_hashed"]
        * RECOVERY_RETAINED_VERIFICATION_PASSES
    ):
        raise ValueError("full-song recovery prior audio request binding differs")


def _validate_preservation(
    report: Mapping[str, Any], request: Mapping[str, Any] | None
) -> None:
    preservation = report.get("failed_package_preservation", {})
    if (
        preservation.get("unchanged") is not True
        or preservation.get("original_failed_root_retained") is not True
        or preservation.get("prior_failed_root_retained") is not True
        or len(preservation.get("failed_report_sha256", "")) != 64
        or len(preservation.get("prior_failed_report_sha256", "")) != 64
        or len(preservation.get("failed_tree_binding_sha256", "")) != 64
        or len(preservation.get("prior_failed_tree_binding_sha256", "")) != 64
    ):
        raise ValueError("full-song recovery package preservation differs")
    if request is not None and (
        preservation["failed_report_sha256"]
        != request["retained_json"]["failure_report"]["sha256"]
        or preservation["prior_failed_report_sha256"]
        != request["prior_failed_package"]["failure_report"]["sha256"]
        or preservation["failed_tree_binding_sha256"]
        != value_sha256(request["retained_tree"])
        or preservation["prior_failed_tree_binding_sha256"]
        != request["prior_failed_package"]["tree_binding_sha256"]
    ):
        raise ValueError("full-song recovery package binding differs")


def validate_recovery_report(
    value: Mapping[str, Any],
    plan_value: Mapping[str, Any],
    request_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a defensive copy of one bounded, resource-incomplete report."""

    plan = validate_fine_stem_full_song_plan(plan_value)
    report = copy.deepcopy(dict(value))
    _validate_report_identity(report, plan)
    request, request_payloads = _request_payloads(report, plan, request_value)
    cases = _validate_report_cases(report, plan)
    expected_case_ids = _validate_workers(report, plan)
    _validate_recovered_inputs(report, plan, expected_case_ids, request_payloads)
    _validate_accounting(report, plan, cases)
    _validate_report_effects(report, request)
    _validate_preservation(report, request)
    return report


__all__ = [
    "RECOVERY_REPORT_SCHEMA",
    "RECOVERY_REPORT_STATUS",
    "RECOVERY_REQUEST_SCHEMA",
    "RECOVERY_REQUEST_STATUS",
    "recovery_report_sha256",
    "recovery_request_sha256",
    "validate_recovery_report",
    "validate_recovery_request",
]
