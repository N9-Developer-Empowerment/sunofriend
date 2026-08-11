"""No-model recovery for one retained full-song six-role failure.

Planning reads the retained JSON, hashes the three unreceipted guitar arrays,
and hashes every file in the earlier failed package so both retained trees are
cryptographically bound.  Execution reuses exact temporary estimates from one
failed package, performs the already-fixed projection and PCM24 persistence,
and never constructs or runs a model.  The result remains resource-incomplete
because the failed guitar worker did not persist its peak-memory or guard
receipt.
"""

from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

import numpy as np

from ._private_verified_audio_inputs import (
    load_verified_private_float32_npy,
    load_verified_private_pcm24,
    read_verified_private_bytes,
    require_safe_private_basename,
)
from .separation_fine_stem_full_song_execution_contract import (
    ARTIFACT_ROLES,
    FAILURE_SCHEMA,
    WORKER_REQUEST_SCHEMA,
    WORKER_RESULT_SCHEMA,
    full_song_forward_budget,
    mega53_chunk_starts,
    scnet_forward_calls,
)
from .separation_fine_stem_full_song_plan_contract import (
    validate_fine_stem_full_song_plan,
)
from .separation_fine_stem_integration_audio import (
    persist_six_roles,
    project_within_grouped_other,
    quantize_six_roles,
)


RECOVERY_REQUEST_SCHEMA = (
    "sunofriend.fine-stem-full-song-six-role-recovery-request.v1"
)
RECOVERY_REQUEST_STATUS = "explicit_exact_hash_no_model_recovery_approval_required"
RECOVERY_REPORT_SCHEMA = "sunofriend.fine-stem-full-song-six-role-recovery-report.v1"
RECOVERY_REPORT_STATUS = (
    "private_review_package_recovered_model_free_resource_gate_incomplete"
)
RECOVERY_FAILURE_SCHEMA = (
    "sunofriend.fine-stem-full-song-six-role-recovery-failure.v1"
)
NETWORK_SANDBOX_ENV = "SUNOFRIEND_FULL_SONG_RECOVERY_NETWORK_SANDBOX"
EXPECTED_FAILURE_FRAGMENT = "fine-stem canary crossed its effects boundary"
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
MAXIMUM_RETAINED_JSON_BYTES = 16 * 1024**2
_AUDIO_PAYLOAD_SUFFIXES = {
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".npy",
    ".wav",
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _value_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("full-song recovery JSON must be an object")
    return value


def _relative_regular(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("full-song recovery path escaped the failed package")
    path = root.joinpath(*relative.parts)
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError("full-song recovery input must be a regular non-symlink")
    resolved = path.resolve(strict=True)
    if root != resolved and root not in resolved.parents:
        raise ValueError("full-song recovery input escaped the failed package")
    return resolved


def _tree_snapshot(
    root: Path,
    *,
    expected_files: set[str] | None = None,
    require_private_directory_modes: bool = False,
) -> dict[str, Any]:
    """Bind a private tree without following links or decoding audio."""

    root_details = root.lstat()
    if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
        raise ValueError("full-song recovery tree root differs")
    directories = [
        {
            "relative_path": ".",
            "device": root_details.st_dev,
            "inode": root_details.st_ino,
            "uid": root_details.st_uid,
            "mtime_ns": root_details.st_mtime_ns,
            "ctime_ns": root_details.st_ctime_ns,
            "mode": stat.S_IMODE(root_details.st_mode),
        }
    ]
    files = []
    for candidate in sorted(root.rglob("*")):
        details = candidate.lstat()
        relative = candidate.relative_to(root).as_posix()
        if stat.S_ISLNK(details.st_mode):
            raise ValueError("full-song recovery tree must not contain symlinks")
        if stat.S_ISDIR(details.st_mode):
            directories.append(
                {
                    "relative_path": relative,
                    "device": details.st_dev,
                    "inode": details.st_ino,
                    "uid": details.st_uid,
                    "mtime_ns": details.st_mtime_ns,
                    "ctime_ns": details.st_ctime_ns,
                    "mode": stat.S_IMODE(details.st_mode),
                }
            )
        elif stat.S_ISREG(details.st_mode):
            identity = {
                "relative_path": relative,
                "bytes": details.st_size,
                "device": details.st_dev,
                "inode": details.st_ino,
                "mtime_ns": details.st_mtime_ns,
                "ctime_ns": details.st_ctime_ns,
                "mode": stat.S_IMODE(details.st_mode),
                "uid": details.st_uid,
                "links": details.st_nlink,
            }
            files.append(identity)
        else:
            raise ValueError("full-song recovery tree contains a special file")
    observed = {item["relative_path"] for item in files}
    if expected_files is not None and observed != expected_files:
        raise ValueError("full-song recovery retained file inventory differs")
    if directories[0]["mode"] != 0o700:
        raise ValueError("full-song recovery retained root mode differs")
    if any(item["mode"] not in {0o700, 0o755} for item in directories[1:]):
        raise ValueError("full-song recovery retained inner directory mode differs")
    if require_private_directory_modes and any(
        item["mode"] != 0o700 for item in directories
    ):
        raise ValueError("full-song recovery retained directory mode differs")
    if any(item["mode"] != 0o600 for item in files):
        raise ValueError("full-song recovery retained file mode differs")
    if any(item["uid"] != os.geteuid() or item["links"] != 1 for item in files):
        raise ValueError("full-song recovery retained file ownership differs")
    return {
        "directories": directories,
        "files": files,
        "legacy_inner_directory_modes_0755": sum(
            item["relative_path"] != "." and item["mode"] == 0o755
            for item in directories
        ),
    }


def _tree_directory_map(
    snapshot: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    directories = snapshot.get("directories")
    if not isinstance(directories, list):
        raise ValueError("full-song recovery directory snapshot differs")
    mapped = {item.get("relative_path"): item for item in directories}
    if len(mapped) != len(directories) or not all(
        isinstance(path, str) for path in mapped
    ):
        raise ValueError("full-song recovery directory inventory differs")
    return mapped  # type: ignore[return-value]


def _tree_file_map(
    snapshot: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    files = snapshot.get("files")
    if not isinstance(files, list):
        raise ValueError("full-song recovery file snapshot differs")
    mapped = {item.get("relative_path"): item for item in files}
    if len(mapped) != len(files) or not all(isinstance(path, str) for path in mapped):
        raise ValueError("full-song recovery file inventory differs")
    return mapped  # type: ignore[return-value]


def _read_bound_json_documents(
    root: Path,
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    directories = _tree_directory_map(snapshot)
    files = _tree_file_map(snapshot)
    documents = {}
    receipts = {}
    for name, relative_path in JSON_EVIDENCE.items():
        loaded = read_verified_private_bytes(
            root,
            files[relative_path],
            expected_directories=directories,
            maximum_bytes=MAXIMUM_RETAINED_JSON_BYTES,
        )
        try:
            value = json.loads(loaded.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("full-song recovery retained JSON differs") from error
        if not isinstance(value, dict):
            raise ValueError("full-song recovery retained JSON must be an object")
        documents[name] = value
        receipts[name] = loaded.receipt()
    return documents, receipts


def _directory_identity(details: os.stat_result) -> dict[str, int]:
    return {
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
    }


def _open_absolute_directory_nofollow(path: Path) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError("full-song recovery requires no-follow directory opens")
    if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError("full-song recovery output parent path differs")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | no_follow
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open("/", flags)
    try:
        os.set_inheritable(descriptor, False)
        for component in path.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.set_inheritable(next_descriptor, False)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _output_parent_binding(path: Path) -> dict[str, Any]:
    descriptor = _open_absolute_directory_nofollow(path)
    try:
        held = os.fstat(descriptor)
        visible = path.lstat()
        if (
            not stat.S_ISDIR(held.st_mode)
            or _directory_identity(held) != _directory_identity(visible)
            or held.st_uid != os.geteuid()
            or stat.S_IMODE(held.st_mode) & 0o022
        ):
            raise ValueError("full-song recovery output parent is not safely bound")
        return {"absolute_path": str(path), **_directory_identity(held)}
    finally:
        os.close(descriptor)


def _bind_output_parent(
    path: Path,
    expected: Mapping[str, Any],
    *,
    fresh_names: Sequence[str],
) -> int:
    descriptor = _open_absolute_directory_nofollow(path)
    try:
        held = os.fstat(descriptor)
        visible = path.lstat()
        observed = {"absolute_path": str(path), **_directory_identity(held)}
        if (
            observed != expected
            or _directory_identity(held) != _directory_identity(visible)
            or held.st_uid != os.geteuid()
            or stat.S_IMODE(held.st_mode) & 0o022
        ):
            raise RuntimeError("full-song recovery output parent binding changed")
        for name in fresh_names:
            if Path(name).name != name or name in {"", ".", ".."}:
                raise ValueError("full-song recovery output name differs")
            try:
                os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise FileExistsError(f"full-song recovery output exists: {name}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _recorded_relative_path(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("full-song recovery recorded path differs")
    parts = Path(value).parts
    try:
        index = parts.index("TEMP")
    except ValueError as error:
        raise ValueError("full-song recovery evidence lacks TEMP binding") from error
    return PurePosixPath(*parts[index:]).as_posix()


def _case_ids(plan: Mapping[str, Any]) -> list[str]:
    values = [case["track_id"] for case in plan["cases"]]
    return [
        require_safe_private_basename(value, label="full-song recovery track id")
        for value in values
    ]


def _result_case_map(
    result: Mapping[str, Any], *, expected_case_ids: Sequence[str]
) -> dict[str, Mapping[str, Any]]:
    cases = result.get("cases")
    if (
        not isinstance(cases, list)
        or [case.get("track_id") for case in cases] != list(expected_case_ids)
    ):
        raise ValueError("full-song recovery worker cases differ")
    return {case["track_id"]: case for case in cases}


def _validate_completed_result(
    result: Mapping[str, Any],
    *,
    mode: str,
    plan: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    cases = _result_case_map(result, expected_case_ids=_case_ids(plan))
    role_key = "core_four" if mode == "scnet" else "synth"
    expected_profile = plan["profiles"][role_key]["profile_id"]
    budget = full_song_forward_budget(plan)
    expected_total = (
        budget["scnet_forward_calls"]
        if mode == "scnet"
        else budget["mega53_forward_calls"]
    )
    expected_effects = {
        "model_loads": 1,
        "profile_inference_attempts": 3,
        "network_attempts": 0,
        "automatic_retry": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
    }
    if (
        result.get("schema") != WORKER_RESULT_SCHEMA
        or result.get("status")
        != "complete_unpublished_private_temporary_estimates"
        or result.get("mode") != mode
        or result.get("runtime", {}).get("network_denied") is not True
        or result.get("effects") != expected_effects
        or result.get("model", {}).get("profile_id") != expected_profile
        or result.get("model", {}).get("model_loads") != 1
        or result.get("model", {}).get("forward_calls") != expected_total
        or not isinstance(result.get("elapsed_seconds"), (int, float))
        or not math.isfinite(float(result["elapsed_seconds"]))
    ):
        raise ValueError("full-song recovery completed worker receipt differs")
    for planned in plan["cases"]:
        case = cases[planned["track_id"]]
        frames = int(planned["full_song_source"]["expected_canonical_frames"])
        expected_calls = (
            scnet_forward_calls(frames)
            if mode == "scnet"
            else len(mega53_chunk_starts(frames))
        )
        expected_roles = (
            {"vocals", "drums", "bass", "other"}
            if mode == "scnet"
            else {"synth"}
        )
        if (
            case.get("forward_calls") != expected_calls
            or float(case.get("elapsed_seconds", math.inf)) > 900
            or set(case.get("outputs", {})) != expected_roles
        ):
            raise ValueError("full-song recovery worker case receipt differs")
    return cases


def _validate_worker_request_binding(
    request: Mapping[str, Any],
    *,
    mode: str,
    plan: Mapping[str, Any],
) -> None:
    cases = request.get("cases")
    if (
        request.get("schema") != WORKER_REQUEST_SCHEMA
        or request.get("mode") != mode
        or request.get("network_denied") is not True
        or not isinstance(cases, list)
        or [case.get("track_id") for case in cases] != _case_ids(plan)
    ):
        raise ValueError("full-song recovery worker request differs")
    budget = full_song_forward_budget(plan)
    expected_calls = {
        "scnet": budget["scnet_forward_calls"],
        "mega53-synth": budget["mega53_forward_calls"],
        "sw-guitar": budget["sw_forward_calls"],
    }[mode]
    if request.get("expected_forward_calls") != expected_calls:
        raise ValueError("full-song recovery worker forward budget differs")
    for case, planned in zip(cases, plan["cases"]):
        track = planned["track_id"]
        source = case.get("source", {})
        canonical_relative = f"TEMP/canonical/{track}/reference.wav"
        if (
            _recorded_relative_path(source.get("path")) != canonical_relative
            or source.get("frames")
            != planned["full_song_source"]["expected_canonical_frames"]
            or source.get("sample_rate_hz") != 44_100
            or source.get("channels") != 2
            or source.get("subtype") != "PCM_24"
            or not isinstance(source.get("bytes"), int)
            or source["bytes"] <= 0
            or not isinstance(source.get("sha256"), str)
            or len(source["sha256"]) != 64
        ):
            raise ValueError("full-song recovery worker source binding differs")
        if mode == "scnet":
            expected_outputs = {
                role: f"TEMP/scnet/{track}/{role}.npy"
                for role in ("vocals", "drums", "bass", "other")
            }
            outputs = case.get("outputs")
            if not isinstance(outputs, dict) or set(outputs) != set(expected_outputs):
                raise ValueError("full-song recovery SCNet request roles differ")
            if any(
                _recorded_relative_path(outputs[role]) != relative
                for role, relative in expected_outputs.items()
            ):
                raise ValueError("full-song recovery SCNet request paths differ")
        else:
            role = "synth" if mode == "mega53-synth" else "guitar"
            expected_output = f"TEMP/{role}/{track}/{role}.npy"
            if _recorded_relative_path(case.get("output")) != expected_output:
                raise ValueError("full-song recovery specialist request path differs")


def _worker_source_bindings(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = ("path", "bytes", "sha256", "sample_rate_hz", "channels", "frames", "subtype")
    return [
        {field: case["source"][field] for field in fields}
        for case in request["cases"]
    ]


def _validate_failure_and_requests(
    plan: Mapping[str, Any], documents: Mapping[str, Mapping[str, Any]]
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    failure = dict(documents["failure_report"])
    scnet_request = dict(documents["scnet_request"])
    scnet = dict(documents["scnet_result"])
    synth_request = dict(documents["synth_request"])
    synth = dict(documents["synth_result"])
    guitar_request = dict(documents["guitar_request"])
    if (
        failure.get("schema") != FAILURE_SCHEMA
        or failure.get("status") != "objective_failure_retained_no_retry"
        or failure.get("plan_sha256") != plan["document_sha256"]
        or failure.get("approved_plan_sha256") != plan["document_sha256"]
        or EXPECTED_FAILURE_FRAGMENT not in str(failure.get("failure", ""))
        or failure.get("automatic_retry") is not False
    ):
        raise ValueError("full-song recovery failure binding differs")
    _validate_worker_request_binding(scnet_request, mode="scnet", plan=plan)
    _validate_worker_request_binding(
        synth_request, mode="mega53-synth", plan=plan
    )
    _validate_worker_request_binding(
        guitar_request, mode="sw-guitar", plan=plan
    )
    source_bindings = _worker_source_bindings(scnet_request)
    if (
        _worker_source_bindings(synth_request) != source_bindings
        or _worker_source_bindings(guitar_request) != source_bindings
    ):
        raise ValueError("full-song recovery worker canonical identities differ")
    _validate_completed_result(scnet, mode="scnet", plan=plan)
    _validate_completed_result(synth, mode="mega53-synth", plan=plan)
    return failure, scnet, synth, guitar_request


def _payload_inventory(
    plan: Mapping[str, Any],
    retained_files: Mapping[str, Mapping[str, Any]],
    guitar_sha256: Mapping[str, str],
    scnet: Mapping[str, Any],
    synth: Mapping[str, Any],
    guitar_request: Mapping[str, Any],
) -> list[dict[str, Any]]:
    scnet_cases = _result_case_map(scnet, expected_case_ids=_case_ids(plan))
    synth_cases = _result_case_map(synth, expected_case_ids=_case_ids(plan))
    guitar_cases = {
        case["track_id"]: case for case in guitar_request["cases"]
    }
    inventory = []

    def metadata(relative_path: str) -> dict[str, Any]:
        return {**retained_files[relative_path], "content_opened": False}

    for planned in plan["cases"]:
        track = planned["track_id"]
        frames = int(planned["full_song_source"]["expected_canonical_frames"])
        canonical_relative = f"TEMP/canonical/{track}/reference.wav"
        canonical = metadata(canonical_relative)
        request_source = guitar_cases[track]["source"]
        if (
            _recorded_relative_path(request_source["path"]) != canonical_relative
            or request_source.get("frames") != frames
            or request_source.get("sample_rate_hz") != 44_100
            or request_source.get("channels") != 2
            or request_source.get("subtype") != "PCM_24"
            or canonical["bytes"] != request_source.get("bytes")
        ):
            raise ValueError("full-song recovery canonical binding differs")
        inventory.append(
            {
                **canonical,
                "kind": "canonical_pcm24",
                "track_id": track,
                "role": "reference",
                "expected_sha256": request_source["sha256"],
                "expected_frames": frames,
            }
        )
        for role in ("vocals", "drums", "bass", "other"):
            relative = f"TEMP/scnet/{track}/{role}.npy"
            recorded = scnet_cases[track]["outputs"][role]
            role_metadata = metadata(relative)
            if (
                _recorded_relative_path(recorded["path"]) != relative
                or role_metadata["bytes"] != recorded.get("bytes")
            ):
                raise ValueError("full-song recovery SCNet array binding differs")
            inventory.append(
                {
                    **role_metadata,
                    "kind": "float32_estimate",
                    "track_id": track,
                    "role": role,
                    "expected_sha256": recorded["sha256"],
                    "expected_frames": frames,
                }
            )
        synth_relative = f"TEMP/synth/{track}/synth.npy"
        synth_recorded = synth_cases[track]["outputs"]["synth"]
        synth_metadata = metadata(synth_relative)
        if (
            _recorded_relative_path(synth_recorded["path"]) != synth_relative
            or synth_metadata["bytes"] != synth_recorded.get("bytes")
        ):
            raise ValueError("full-song recovery synth array binding differs")
        inventory.append(
            {
                **synth_metadata,
                "kind": "float32_estimate",
                "track_id": track,
                "role": "synth",
                "expected_sha256": synth_recorded["sha256"],
                "expected_frames": frames,
            }
        )
        guitar_relative = f"TEMP/guitar/{track}/guitar.npy"
        guitar_metadata = metadata(guitar_relative)
        if _recorded_relative_path(guitar_cases[track]["output"]) != guitar_relative:
            raise ValueError("full-song recovery guitar array binding differs")
        inventory.append(
            {
                **guitar_metadata,
                "kind": "float32_estimate_unreceipted",
                "track_id": track,
                "role": "guitar",
                "expected_sha256": guitar_sha256[track],
                "expected_frames": frames,
                "content_opened": True,
            }
        )
    if len(inventory) != RECOVERY_AUDIO_READS:
        raise RuntimeError("full-song recovery payload inventory differs")
    return inventory


def _implementation_identities() -> list[dict[str, Any]]:
    package = Path(__file__).resolve().parent
    repository = package.parents[1]
    files = (
        Path(__file__).resolve(),
        package / "separation_fine_stem_full_song_execution_contract.py",
        package / "separation_fine_stem_full_song_plan_contract.py",
        package / "separation_fine_stem_full_song_execution_review.py",
        package / "separation_fine_stem_integration_audio.py",
        package / "_private_verified_audio_inputs.py",
        repository / "scripts/recover-fine-stem-full-song-six-role.py",
    )
    identities = []
    for path in files:
        resolved = path.resolve(strict=True)
        identities.append(
            {
                "relative_path": resolved.relative_to(repository).as_posix(),
                "bytes": resolved.stat().st_size,
                "sha256": _file_sha256(resolved),
            }
        )
    return identities


def _build_recovery_request_with_documents(
    plan_value: Mapping[str, Any],
    failed_root_value: str | Path,
    *,
    proposed_output: str | Path,
    prior_failed_root_value: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build an exact no-write request, hashing three guitar payloads."""

    plan = validate_fine_stem_full_song_plan(plan_value)
    failed_root = Path(failed_root_value).expanduser().resolve(strict=True)
    if not failed_root.is_dir() or failed_root.is_symlink():
        raise ValueError("full-song recovery needs a regular failed directory")
    proposed = Path(proposed_output).expanduser()
    if not proposed.is_absolute() or proposed.name in {"", ".", ".."}:
        raise ValueError("full-song recovery output must be an absolute sibling")
    output = proposed.parent.resolve(strict=True) / proposed.name
    if output.parent != failed_root.parent or output == failed_root:
        raise ValueError("full-song recovery output must be a fresh exact sibling")
    if output.exists() or output.with_name(output.name + "-RECOVERY-FAILED").exists():
        raise FileExistsError("full-song recovery output target must be fresh")
    expected_files = set(JSON_EVIDENCE.values())
    for track in _case_ids(plan):
        expected_files.add(f"TEMP/canonical/{track}/reference.wav")
        expected_files.update(
            f"TEMP/scnet/{track}/{role}.npy"
            for role in ("vocals", "drums", "bass", "other")
        )
        expected_files.add(f"TEMP/synth/{track}/synth.npy")
        expected_files.add(f"TEMP/guitar/{track}/guitar.npy")
    if len(expected_files) != RETAINED_TREE_FILES:
        raise RuntimeError("full-song recovery expected tree inventory differs")
    retained_tree = _tree_snapshot(failed_root, expected_files=expected_files)
    retained_directories = _tree_directory_map(retained_tree)
    retained_files = _tree_file_map(retained_tree)
    documents, retained_json = _read_bound_json_documents(
        failed_root, retained_tree
    )
    failure, scnet, synth, guitar_request = _validate_failure_and_requests(
        plan, documents
    )
    guitar_sha256 = {}
    for track in _case_ids(plan):
        relative = f"TEMP/guitar/{track}/guitar.npy"
        loaded_guitar = read_verified_private_bytes(
            failed_root,
            retained_files[relative],
            expected_directories=retained_directories,
        )
        guitar_sha256[track] = loaded_guitar.sha256
        del loaded_guitar
    inventory = _payload_inventory(
        plan,
        retained_files,
        guitar_sha256,
        scnet,
        synth,
        guitar_request,
    )
    if {item["relative_path"] for item in inventory} | set(
        JSON_EVIDENCE.values()
    ) != expected_files:
        raise RuntimeError("full-song recovery payload tree binding differs")
    if _tree_snapshot(failed_root, expected_files=expected_files) != retained_tree:
        raise RuntimeError("full-song recovery retained tree changed during preflight")
    if prior_failed_root_value is None:
        raise ValueError("full-song recovery requires the prior failed package")
    prior_root = Path(prior_failed_root_value).expanduser().resolve(strict=True)
    if not prior_root.is_dir() or prior_root.is_symlink():
        raise ValueError("full-song recovery prior failed root differs")
    prior_tree_snapshot = _tree_snapshot(prior_root)
    prior_directories = _tree_directory_map(prior_tree_snapshot)
    prior_tree = copy.deepcopy(prior_tree_snapshot)
    prior_report_identity = None
    for item in prior_tree["files"]:
        loaded_prior = read_verified_private_bytes(
            prior_root,
            item,
            expected_directories=prior_directories,
        )
        item["sha256"] = loaded_prior.sha256
        if item["relative_path"] == "FAILED-REPORT.json":
            prior_report_identity = loaded_prior.receipt()
        del loaded_prior
    if prior_report_identity is None:
        raise ValueError("full-song recovery prior failure report is missing")
    if _tree_snapshot(prior_root) != prior_tree_snapshot:
        raise RuntimeError("full-song recovery prior tree changed during preflight")
    prior_audio_payloads_hashed = sum(
        PurePosixPath(item["relative_path"]).suffix.lower()
        in _AUDIO_PAYLOAD_SUFFIXES
        for item in prior_tree["files"]
    )
    prior_failure = {
        "root": str(prior_root),
        "failure_report": {
            "relative_path": "FAILED-REPORT.json",
            "bytes": prior_report_identity["bytes"],
            "sha256": prior_report_identity["sha256"],
        },
        "tree": prior_tree,
        "tree_binding_sha256": _value_sha256(prior_tree),
        "files_content_hashed": len(prior_tree["files"]),
        "audio_payloads_content_hashed": prior_audio_payloads_hashed,
        "must_remain_unchanged": True,
    }
    request: dict[str, Any] = {
        "schema": RECOVERY_REQUEST_SCHEMA,
        "document_sha256": "",
        "status": RECOVERY_REQUEST_STATUS,
        "original_plan_sha256": plan["document_sha256"],
        "failed_root": str(failed_root),
        "proposed_output": str(output),
        "output_parent_binding": _output_parent_binding(output.parent),
        "prior_failed_package": prior_failure,
        "implementation": _implementation_identities(),
        "retained_json": retained_json,
        "retained_payloads": inventory,
        "retained_tree": retained_tree,
        "recovery_contract": {
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
            "retained_json_file_opens": (
                len(JSON_EVIDENCE) * RECOVERY_RETAINED_VERIFICATION_PASSES
            ),
            "retained_guitar_array_hash_opens": (
                3 * RECOVERY_RETAINED_VERIFICATION_PASSES
            ),
            "prior_failed_audio_payload_hash_opens": (
                prior_audio_payloads_hashed * RECOVERY_RETAINED_VERIFICATION_PASSES
            ),
            "prior_failed_file_hash_opens": (
                len(prior_tree["files"])
                * RECOVERY_RETAINED_VERIFICATION_PASSES
            ),
            "retained_evidence_verification_passes": (
                RECOVERY_RETAINED_VERIFICATION_PASSES
            ),
            "pcm24_audio_writes": RECOVERY_AUDIO_WRITES,
            "writer_count": 1,
            "automatic_retry": False,
            "fresh_atomic_output": True,
        },
        "incomplete_historical_evidence": {
            "guitar_worker_result_receipt": False,
            "guitar_guard_counters_persisted": False,
            "guitar_peak_memory_persisted": False,
            "guitar_resource_gate_complete": False,
            "full_objective_qualification_allowed": False,
            "failure_classification": (
                "consistent_with_known_caught_loopback_bind_probe_not_proven"
            ),
        },
        "effects": {
            "audio_payloads_opened": 3 + prior_audio_payloads_hashed,
            "retained_json_files_content_read": len(JSON_EVIDENCE),
            "guitar_arrays_content_hashed": 3,
            "prior_failed_files_content_hashed": len(prior_tree["files"]),
            "prior_failed_audio_payloads_content_hashed": (
                prior_audio_payloads_hashed
            ),
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
        },
        "approval_text": (
            "Approve one exact-hash network-denied no-model recovery. Read and "
            "verify the six retained JSON evidence files and 21 retained private "
            "audio payloads, perform only the "
            "fixed projection and 24 PCM24 writes, preserve the failed package, "
            "preserve the separately bound prior failed package, and retain the "
            f"incomplete guitar resource/guard evidence. Rehash the "
            f"{prior_audio_payloads_hashed} prior-package private audio payload(s) "
            f"during each of {RECOVERY_RETAINED_VERIFICATION_PASSES} fixed "
            "verification passes."
        ),
    }
    request["document_sha256"] = recovery_request_sha256(request)
    return validate_recovery_request(request, plan), documents


def build_recovery_request(
    plan_value: Mapping[str, Any],
    failed_root_value: str | Path,
    *,
    proposed_output: str | Path,
    prior_failed_root_value: str | Path | None = None,
) -> dict[str, Any]:
    """Build one no-write descriptor-bound exact recovery request."""

    request, _documents = _build_recovery_request_with_documents(
        plan_value,
        failed_root_value,
        proposed_output=proposed_output,
        prior_failed_root_value=prior_failed_root_value,
    )
    return request


def validate_recovery_request(
    value: Mapping[str, Any], plan_value: Mapping[str, Any]
) -> dict[str, Any]:
    plan = validate_fine_stem_full_song_plan(plan_value)
    request = copy.deepcopy(dict(value))
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
    failed_path = Path(str(request.get("failed_root", "")))
    output_path = Path(str(request.get("proposed_output", "")))
    if (
        not failed_path.is_absolute()
        or not output_path.is_absolute()
        or output_path.parent != failed_path.parent
        or output_path == failed_path
    ):
        raise ValueError("full-song recovery request output binding differs")
    parent_binding = request.get("output_parent_binding", {})
    if (
        parent_binding.get("absolute_path") != str(output_path.parent)
        or parent_binding.get("uid") != os.geteuid()
        or not isinstance(parent_binding.get("device"), int)
        or not isinstance(parent_binding.get("inode"), int)
        or not isinstance(parent_binding.get("mode"), int)
        or parent_binding["mode"] & 0o022
    ):
        raise ValueError("full-song recovery request parent binding differs")
    retained_tree = request["retained_tree"]
    retained_directories = retained_tree.get("directories", [])
    retained_files = retained_tree.get("files", [])
    retained_paths = {item.get("relative_path") for item in retained_files}
    expected_paths = {
        *JSON_EVIDENCE.values(),
        *(item.get("relative_path") for item in request["retained_payloads"]),
    }
    if (
        not isinstance(retained_directories, list)
        or not retained_directories
        or retained_directories[0].get("relative_path") != "."
        or retained_directories[0].get("mode") != 0o700
        or any(
            not all(
                isinstance(item.get(field), int)
                for field in ("device", "inode", "uid", "mtime_ns", "ctime_ns", "mode")
            )
            for item in retained_directories
        )
        or any(
            item.get("mode") not in {0o700, 0o755}
            for item in retained_directories[1:]
        )
        or retained_tree.get("legacy_inner_directory_modes_0755")
        != sum(item.get("mode") == 0o755 for item in retained_directories[1:])
        or retained_paths != expected_paths
        or any(item.get("mode") != 0o600 for item in retained_files)
        or any(
            item.get("uid") != os.geteuid() or item.get("links") != 1
            for item in retained_files
        )
    ):
        raise ValueError("full-song recovery retained tree contract differs")
    retained_json = request["retained_json"]
    if set(retained_json) != set(JSON_EVIDENCE) or any(
        identity.get("relative_path") != JSON_EVIDENCE[name]
        or not isinstance(identity.get("bytes"), int)
        or identity["bytes"] <= 0
        or len(identity.get("sha256", "")) != 64
        for name, identity in retained_json.items()
    ):
        raise ValueError("full-song recovery retained JSON binding differs")
    retained_files_by_path = {
        item["relative_path"]: item for item in retained_files
    }
    for identity in retained_json.values():
        approved_file = retained_files_by_path[identity["relative_path"]]
        observed_file = identity.get("observed_file_identity", {})
        if any(
            observed_file.get(field) != approved_file[field]
            for field in (
                "device",
                "inode",
                "bytes",
                "mtime_ns",
                "ctime_ns",
                "mode",
                "uid",
            )
        ) or observed_file.get("links") != approved_file["links"]:
            raise ValueError("full-song recovery JSON descriptor binding differs")
    payloads = request["retained_payloads"]
    expected_payload_roles = {
        (case["track_id"], role)
        for case in plan["cases"]
        for role in ("reference", "vocals", "drums", "bass", "other", "synth", "guitar")
    }
    if {
        (item.get("track_id"), item.get("role")) for item in payloads
    } != expected_payload_roles:
        raise ValueError("full-song recovery retained payload roles differ")
    frames_by_track = {
        case["track_id"]: case["full_song_source"]["expected_canonical_frames"]
        for case in plan["cases"]
    }
    for item in payloads:
        role = item["role"]
        track = item["track_id"]
        expected_kind = (
            "canonical_pcm24"
            if role == "reference"
            else "float32_estimate_unreceipted"
            if role == "guitar"
            else "float32_estimate"
        )
        expected_relative = (
            f"TEMP/canonical/{track}/reference.wav"
            if role == "reference"
            else f"TEMP/{'scnet' if role in {'vocals', 'drums', 'bass', 'other'} else role}/{track}/{role}.npy"
        )
        if (
            item.get("kind") != expected_kind
            or item.get("relative_path") != expected_relative
            or item.get("expected_frames") != frames_by_track[track]
            or len(item.get("expected_sha256", "")) != 64
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
            or item.get("mode") != 0o600
            or item.get("content_opened") is not (role == "guitar")
        ):
            raise ValueError("full-song recovery retained payload identity differs")
    implementation = request.get("implementation")
    if (
        not isinstance(implementation, list)
        or len(implementation) < 7
        or len({item.get("relative_path") for item in implementation})
        != len(implementation)
        or any(len(item.get("sha256", "")) != 64 for item in implementation)
    ):
        raise ValueError("full-song recovery implementation binding differs")
    prior = request.get("prior_failed_package")
    prior_tree = prior.get("tree", {}) if isinstance(prior, dict) else {}
    prior_files = prior_tree.get("files", [])
    prior_directories = prior_tree.get("directories", [])
    prior_report_file = next(
        (
            item
            for item in (prior_files if isinstance(prior_files, list) else [])
            if item.get("relative_path") == "FAILED-REPORT.json"
        ),
        None,
    )
    prior_audio_count = (
        sum(
            PurePosixPath(item.get("relative_path", "")).suffix.lower()
            in _AUDIO_PAYLOAD_SUFFIXES
            for item in prior_files
        )
        if isinstance(prior_files, list)
        else -1
    )
    if (
        not isinstance(prior, dict)
        or prior.get("must_remain_unchanged") is not True
        or not isinstance(prior.get("root"), str)
        or len(prior.get("failure_report", {}).get("sha256", "")) != 64
        or not isinstance(prior_files, list)
        or not prior_files
        or any(len(item.get("sha256", "")) != 64 for item in prior_files)
        or not isinstance(prior_directories, list)
        or not prior_directories
        or prior_directories[0].get("relative_path") != "."
        or prior_directories[0].get("mode") != 0o700
        or any(
            not all(
                isinstance(item.get(field), int)
                for field in ("device", "inode", "uid", "mtime_ns", "ctime_ns", "mode")
            )
            for item in prior_directories
        )
        or any(
            item.get("mode") not in {0o700, 0o755}
            for item in prior_directories[1:]
        )
        or any(item.get("mode") != 0o600 for item in prior_files)
        or any(
            item.get("uid") != os.geteuid() or item.get("links") != 1
            for item in prior_files
        )
        or prior_tree.get("legacy_inner_directory_modes_0755")
        != sum(item.get("mode") == 0o755 for item in prior_directories[1:])
        or prior.get("tree_binding_sha256") != _value_sha256(prior_tree)
        or prior.get("files_content_hashed") != len(prior_files)
        or prior.get("audio_payloads_content_hashed") != prior_audio_count
        or not isinstance(prior_report_file, dict)
        or prior.get("failure_report", {}).get("sha256")
        != prior_report_file.get("sha256")
        or prior.get("failure_report", {}).get("bytes")
        != prior_report_file.get("bytes")
    ):
        raise ValueError("full-song recovery prior failure binding differs")
    contract = request.get("recovery_contract", {})
    if contract != {
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
        "retained_json_file_opens": (
            len(JSON_EVIDENCE) * RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "retained_guitar_array_hash_opens": (
            3 * RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "prior_failed_audio_payload_hash_opens": (
            prior_audio_count * RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "prior_failed_file_hash_opens": (
            len(prior_files) * RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "retained_evidence_verification_passes": (
            RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "pcm24_audio_writes": RECOVERY_AUDIO_WRITES,
        "writer_count": 1,
        "automatic_retry": False,
        "fresh_atomic_output": True,
    }:
        raise ValueError("full-song recovery effects contract differs")
    incomplete = request.get("incomplete_historical_evidence", {})
    if (
        incomplete.get("guitar_worker_result_receipt") is not False
        or incomplete.get("guitar_guard_counters_persisted") is not False
        or incomplete.get("guitar_peak_memory_persisted") is not False
        or incomplete.get("guitar_resource_gate_complete") is not False
        or incomplete.get("full_objective_qualification_allowed") is not False
    ):
        raise ValueError("full-song recovery incompleteness differs")
    effects = request.get("effects", {})
    expected_effects = {
        "audio_payloads_opened": 3 + prior_audio_count,
        "retained_json_files_content_read": len(JSON_EVIDENCE),
        "guitar_arrays_content_hashed": 3,
        "prior_failed_files_content_hashed": len(prior_files),
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
    if effects != expected_effects:
        raise ValueError("full-song recovery preflight contains effects")
    return request


def _load_pcm24(
    root: Path,
    identity: Mapping[str, Any],
    *,
    expected_directories: Mapping[str, Mapping[str, Any]],
) -> tuple[np.ndarray, dict[str, Any]]:
    loaded = load_verified_private_pcm24(
        root,
        identity,
        expected_directories=expected_directories,
        np=np,
    )
    return loaded.samples, loaded.receipt()


def _load_estimate(
    root: Path,
    identity: Mapping[str, Any],
    *,
    expected_directories: Mapping[str, Mapping[str, Any]],
) -> tuple[np.ndarray, dict[str, Any]]:
    loaded = load_verified_private_float32_npy(
        root,
        identity,
        expected_directories=expected_directories,
        np=np,
    )
    as_float64 = loaded.samples.astype(np.float64)
    return as_float64, {
        **loaded.receipt(),
        "rms": float(np.sqrt(np.mean(np.square(as_float64)))),
        "peak": float(np.max(np.abs(as_float64), initial=0.0)),
        "receipt_origin": (
            "reconstructed_from_request_and_array"
            if identity["role"] == "guitar"
            else "persisted_worker_receipt"
        ),
    }


def _inventory_map(request: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    mapped = {
        (item["track_id"], item["role"]): item
        for item in request["retained_payloads"]
    }
    if len(mapped) != RECOVERY_AUDIO_READS:
        raise RuntimeError("full-song recovery retained role inventory differs")
    return mapped


def _worker_summary(
    result: Mapping[str, Any], *, evidence_origin: str
) -> dict[str, Any]:
    model = result["model"]
    peak = model.get("peak_unified_memory_bytes", model.get("peak_mlx_memory_bytes"))
    return {
        "profile_id": model["profile_id"],
        "evidence_origin": evidence_origin,
        "result_receipt_persisted": True,
        "model_loads": 1,
        "profile_inference_attempts": 3,
        "internal_forward_calls": model["forward_calls"],
        "case_elapsed_seconds": {
            case["track_id"]: case["elapsed_seconds"] for case in result["cases"]
        },
        "elapsed_seconds": result["elapsed_seconds"],
        "peak_memory_bytes": int(peak),
        "network_attempts": 0,
        "runtime": result["runtime"],
    }


def _exclusive_publish(
    staging: Path,
    destination: Path,
    *,
    parent_descriptor: int | None = None,
    expected_parent_binding: Mapping[str, Any] | None = None,
    expected_staging_identity: Mapping[str, Any] | None = None,
) -> None:
    """Atomically publish a directory without replacing a raced destination."""

    if staging.parent != destination.parent:
        raise ValueError("full-song recovery publication must stay on one parent")
    if (
        Path(staging.name).name != staging.name
        or Path(destination.name).name != destination.name
        or staging.name in {"", ".", ".."}
        or destination.name in {"", ".", ".."}
    ):
        raise ValueError("full-song recovery publication name differs")
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        flag = 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        flag = 0x00000001  # RENAME_NOREPLACE
    else:
        function = None
        flag = 0
    if function is None:
        raise RuntimeError(
            "full-song recovery requires atomic exclusive directory publication"
        )
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    owns_descriptor = parent_descriptor is None
    parent_fd = (
        _open_absolute_directory_nofollow(staging.parent)
        if parent_descriptor is None
        else parent_descriptor
    )
    try:
        held_parent = os.fstat(parent_fd)
        visible_parent = staging.parent.lstat()
        if (
            _directory_identity(held_parent) != _directory_identity(visible_parent)
            or (
                expected_parent_binding is not None
                and {
                    "absolute_path": str(staging.parent),
                    **_directory_identity(held_parent),
                }
                != expected_parent_binding
            )
        ):
            raise RuntimeError("full-song recovery publication parent changed")
        held_staging = os.stat(
            staging.name, dir_fd=parent_fd, follow_symlinks=False
        )
        visible_staging = staging.lstat()
        if (
            not stat.S_ISDIR(held_staging.st_mode)
            or _directory_identity(held_staging)
            != _directory_identity(visible_staging)
            or (
                expected_staging_identity is not None
                and _directory_identity(held_staging)
                != dict(expected_staging_identity)
            )
            or held_staging.st_uid != os.geteuid()
            or stat.S_IMODE(held_staging.st_mode) != 0o700
        ):
            raise RuntimeError("full-song recovery staging binding changed")
        result = function(
            parent_fd,
            os.fsencode(staging.name),
            parent_fd,
            os.fsencode(destination.name),
            flag,
        )
    finally:
        if owns_descriptor:
            os.close(parent_fd)
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def _validate_staging(
    staging: Path,
    report: Mapping[str, Any],
    request: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    expected_files = {
        "TECHNICAL/RECOVERY-REQUEST.json",
        "TECHNICAL/FULL-SONG-SIX-ROLE-RECOVERY-REPORT.json",
        "REVIEW/full_song_six_role_review.html",
        *(
            artifact["relative_path"]
            for case in report["cases"]
            for artifact in case["artifacts"].values()
        ),
    }
    if len(expected_files) != RECOVERY_AUDIO_WRITES + 3:
        raise RuntimeError("full-song recovery staged file count differs")
    _tree_snapshot(
        staging,
        expected_files=expected_files,
        require_private_directory_modes=True,
    )
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = _relative_regular(staging, artifact["relative_path"])
            if (
                path.stat().st_size != artifact["bytes"]
                or _file_sha256(path) != artifact["sha256"]
            ):
                raise RuntimeError("full-song recovery staged artifact differs")
    request_path = _relative_regular(staging, "TECHNICAL/RECOVERY-REQUEST.json")
    report_path = _relative_regular(
        staging, "TECHNICAL/FULL-SONG-SIX-ROLE-RECOVERY-REPORT.json"
    )
    if _json(request_path) != request:
        raise RuntimeError("full-song recovery staged request differs")
    validate_recovery_report(_json(report_path), plan, request)


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _validate_receipted_worker_summary(
    value: Mapping[str, Any],
    *,
    profile_id: str,
    case_ids: Sequence[str],
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
        or set(elapsed) != set(case_ids)
        or any(not _finite_nonnegative(item) for item in elapsed.values())
        or not _finite_nonnegative(value.get("elapsed_seconds"))
        or not isinstance(value.get("peak_memory_bytes"), int)
        or value["peak_memory_bytes"] <= 0
        or value.get("network_attempts") != 0
        or not isinstance(runtime, dict)
        or runtime.get("network_denied") is not True
    ):
        raise ValueError("full-song recovery retained worker summary differs")


def validate_recovery_report(
    value: Mapping[str, Any],
    plan_value: Mapping[str, Any],
    request_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    plan = validate_fine_stem_full_song_plan(plan_value)
    report = copy.deepcopy(dict(value))
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
    if request_value is not None:
        request = validate_recovery_request(request_value, plan)
        if report.get("recovery_request_sha256") != request["document_sha256"]:
            raise ValueError("full-song recovery report request binding differs")
        request_payloads = {
            (item["track_id"], item["role"]): item
            for item in request["retained_payloads"]
        }
    else:
        request_payloads = None
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
        if (
            case.get("title") != planned["title"]
            or case.get("rights_category") != planned["rights_category"]
            or case.get("scored_target_roles") != planned["scored_target_roles"]
            or case.get("unscored_target_roles")
            != planned["unscored_target_roles"]
            or case.get("confirmed_present_targets")
            != planned["confirmed_present_targets"]
            or set(case.get("artifacts", {})) != set(ARTIFACT_ROLES)
            or not isinstance(case.get("maximum_reconstruction_error_lsb"), int)
            or not 0 <= case["maximum_reconstruction_error_lsb"] <= 2
            or not _finite_nonnegative(case.get("recovery_elapsed_seconds"))
            or not _finite_nonnegative(case.get("shared_attenuation"))
            or not 0 < float(case["shared_attenuation"]) <= 1
            or case.get("scnet_native_other_correction", {}).get(
                "used_for_separation_accuracy_claim"
            )
            is not False
            or not _finite_nonnegative(
                case.get("scnet_native_other_correction", {}).get("rms")
            )
            or not _finite_nonnegative(
                case.get("scnet_native_other_correction", {}).get("peak")
            )
        ):
            raise ValueError("full-song recovery case contract differs")
        projection = case.get("projection", {})
        corrections = projection.get("raw_to_projected_correction", {})
        if (
            projection.get("method")
            != "fixed grouped-other-constrained three-way Wiener mask"
            or not _finite_nonnegative(
                projection.get("maximum_float_reconstruction_error")
            )
            or set(corrections) != {"synth", "guitar"}
            or any(
                not _finite_nonnegative(corrections[role].get(field))
                for role in ("synth", "guitar")
                for field in ("rms", "peak")
            )
        ):
            raise ValueError("full-song recovery projection accounting differs")
        for role, artifact in case["artifacts"].items():
            if (
                artifact.get("sample_rate_hz") != 44_100
                or artifact.get("channels") != 2
                or artifact.get("frames") != frames
                or artifact.get("subtype") != "PCM_24"
                or not isinstance(artifact.get("bytes"), int)
                or artifact["bytes"] <= 0
                or not isinstance(artifact.get("sha256"), str)
                or len(artifact["sha256"]) != 64
                or not isinstance(artifact.get("relative_path"), str)
                or artifact["relative_path"]
                != f"CASES/{case['track_id']}/{role}.wav"
                or artifact["relative_path"].startswith("/")
                or ".." in PurePosixPath(artifact["relative_path"]).parts
            ):
                raise ValueError("full-song recovery persisted artifact differs")
    workers = report.get("workers", {})
    if not isinstance(workers, dict) or set(workers) != {
        "core_four",
        "synth",
        "guitar",
    }:
        raise ValueError("full-song recovery worker summaries differ")
    case_ids = _case_ids(plan)
    forward_budget = full_song_forward_budget(plan)
    _validate_receipted_worker_summary(
        workers["core_four"],
        profile_id=plan["profiles"]["core_four"]["profile_id"],
        case_ids=case_ids,
        expected_forward_calls=forward_budget["scnet_forward_calls"],
    )
    _validate_receipted_worker_summary(
        workers["synth"],
        profile_id=plan["profiles"]["synth"]["profile_id"],
        case_ids=case_ids,
        expected_forward_calls=forward_budget["mega53_forward_calls"],
    )
    guitar = workers["guitar"]
    resources = report.get("resources", {})
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
        or resources.get("guitar_resource_gate_complete") is not False
        or resources.get("full_resource_gate_complete") is not False
        or resources.get("within_known_ceilings") is not None
        or resources.get("known_peak_memory_bytes")
        != {
            "core_four": workers["core_four"]["peak_memory_bytes"],
            "synth": workers["synth"]["peak_memory_bytes"],
            "guitar": None,
        }
        or not _finite_nonnegative(resources.get("failed_attempt_elapsed_seconds"))
        or not _finite_nonnegative(resources.get("recovery_elapsed_seconds"))
        or not isinstance(resources.get("recovery_peak_resident_set_bytes"), int)
        or resources["recovery_peak_resident_set_bytes"] <= 0
    ):
        raise ValueError("full-song recovery resource incompleteness differs")
    recovered_inputs = report.get("recovered_inputs")
    if not isinstance(recovered_inputs, dict) or set(recovered_inputs) != set(case_ids):
        raise ValueError("full-song recovery input identities differ")
    for planned in plan["cases"]:
        inputs = recovered_inputs[planned["track_id"]]
        frames = planned["full_song_source"]["expected_canonical_frames"]
        if not isinstance(inputs, dict) or set(inputs) != {
            "reference",
            "vocals",
            "drums",
            "bass",
            "other",
            "synth",
            "guitar",
        }:
            raise ValueError("full-song recovery input roles differ")
        for role, identity in inputs.items():
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
                not _finite_nonnegative(identity.get("rms"))
                or not _finite_nonnegative(identity.get("peak"))
            ):
                raise ValueError("full-song recovery input statistics differ")
            if request_payloads is not None:
                approved = request_payloads[(planned["track_id"], role)]
                observed_file = identity.get("observed_file_identity", {})
                if (
                    identity.get("relative_path") != approved["relative_path"]
                    or identity.get("bytes") != approved["bytes"]
                    or identity.get("sha256") != approved["expected_sha256"]
                    or identity.get("shape")
                    != [approved["expected_frames"], 2]
                    or any(
                        observed_file.get(field) != approved[field]
                        for field in (
                            "device",
                            "inode",
                            "bytes",
                            "mtime_ns",
                            "ctime_ns",
                            "mode",
                            "uid",
                        )
                    )
                    or observed_file.get("links") != approved["links"]
                ):
                    raise ValueError(
                        "full-song recovery input request binding differs"
                    )
    accounting = report.get("accounting", {})
    if (
        accounting.get("projection") != plan["output_contract"]["projection"]
        or accounting.get("maximum_reconstruction_error_lsb")
        != max(case["maximum_reconstruction_error_lsb"] for case in cases)
        or accounting.get("reconstruction_accounting_is_separation_accuracy")
        is not False
    ):
        raise ValueError("full-song recovery accounting differs")
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
    prior_audio_hash_opens = recovery.get(
        "prior_failed_audio_payload_hash_opens"
    )
    prior_file_hash_opens = recovery.get("prior_failed_file_hash_opens")
    if (
        not isinstance(prior_audio_hash_opens, int)
        or isinstance(prior_audio_hash_opens, bool)
        or prior_audio_hash_opens < 0
        or prior_audio_hash_opens % RECOVERY_RETAINED_VERIFICATION_PASSES
        or not isinstance(prior_file_hash_opens, int)
        or isinstance(prior_file_hash_opens, bool)
        or prior_file_hash_opens <= 0
        or prior_file_hash_opens % RECOVERY_RETAINED_VERIFICATION_PASSES
    ):
        raise ValueError("full-song recovery prior audio verification differs")
    if recovery != {
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
        "retained_evidence_verification_passes": (
            RECOVERY_RETAINED_VERIFICATION_PASSES
        ),
        "pcm24_audio_writes": RECOVERY_AUDIO_WRITES,
        "network_attempts": 0,
        "automatic_retry": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
    }:
        raise ValueError("full-song recovery report effects differ")
    if request_value is not None and (
        prior_audio_hash_opens
        != request["prior_failed_package"]["audio_payloads_content_hashed"]
        * RECOVERY_RETAINED_VERIFICATION_PASSES
        or prior_file_hash_opens
        != request["prior_failed_package"]["files_content_hashed"]
        * RECOVERY_RETAINED_VERIFICATION_PASSES
    ):
        raise ValueError("full-song recovery prior audio request binding differs")
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
    if request_value is not None and (
        preservation["failed_report_sha256"]
        != request["retained_json"]["failure_report"]["sha256"]
        or preservation["prior_failed_report_sha256"]
        != request["prior_failed_package"]["failure_report"]["sha256"]
        or preservation["failed_tree_binding_sha256"]
        != _value_sha256(request["retained_tree"])
        or preservation["prior_failed_tree_binding_sha256"]
        != request["prior_failed_package"]["tree_binding_sha256"]
    ):
        raise ValueError("full-song recovery package binding differs")
    return report


def execute_recovery(
    plan_value: Mapping[str, Any],
    request_value: Mapping[str, Any],
    *,
    approved_recovery_sha256: str,
    confirm_rights: bool,
    network_sandbox_verified: bool = False,
) -> dict[str, Any]:
    """Execute one already-approved recovery into its fresh output."""

    plan = validate_fine_stem_full_song_plan(plan_value)
    request = validate_recovery_request(request_value, plan)
    if not confirm_rights:
        raise RuntimeError("full-song recovery requires --confirm-rights")
    if approved_recovery_sha256 != request["document_sha256"]:
        raise RuntimeError("full-song recovery approval SHA-256 differs")
    if (
        network_sandbox_verified is not True
        or os.environ.get(NETWORK_SANDBOX_ENV) != "1"
    ):
        raise RuntimeError(
            "full-song recovery requires the verified network-denied CLI context"
        )
    failed_root = Path(request["failed_root"]).resolve(strict=True)
    prior_failed_root = Path(request["prior_failed_package"]["root"]).resolve(
        strict=True
    )
    rebuilt, retained_documents = _build_recovery_request_with_documents(
        plan,
        failed_root,
        proposed_output=request["proposed_output"],
        prior_failed_root_value=prior_failed_root,
    )
    if rebuilt != request:
        raise RuntimeError("full-song recovery retained package changed after approval")
    output = Path(request["proposed_output"])
    failed_output = output.with_name(output.name + "-RECOVERY-FAILED")
    if output.exists() or failed_output.exists():
        raise FileExistsError("full-song recovery output target must be fresh")
    parent_descriptor = _bind_output_parent(
        output.parent,
        request["output_parent_binding"],
        fresh_names=(output.name, failed_output.name),
    )
    previous_umask = os.umask(0o077)
    staging: Path | None = None
    staging_identity: dict[str, Any] | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent)
        )
        staging.chmod(0o700)
        staging_identity = _directory_identity(staging.lstat())
        if staging_identity != _directory_identity(
            os.stat(staging.name, dir_fd=parent_descriptor, follow_symlinks=False)
        ):
            raise RuntimeError("full-song recovery staging creation was redirected")
        started = time.monotonic()
        failure, scnet, synth, _guitar_request = _validate_failure_and_requests(
            plan, retained_documents
        )
        inventory = _inventory_map(request)
        retained_directories = {
            item["relative_path"]: item
            for item in request["retained_tree"]["directories"]
        }
        recovered_inputs: dict[str, Any] = {}
        cases = []
        for planned in plan["cases"]:
            track = planned["track_id"]
            case_started = time.monotonic()
            reference, reference_identity = _load_pcm24(
                failed_root,
                inventory[(track, "reference")],
                expected_directories=retained_directories,
            )
            core: dict[str, np.ndarray] = {}
            input_identities = {"reference": reference_identity}
            for role in ("vocals", "drums", "bass", "other"):
                value, identity = _load_estimate(
                    failed_root,
                    inventory[(track, role)],
                    expected_directories=retained_directories,
                )
                core[role] = value
                input_identities[role] = identity
            raw_synth, synth_identity = _load_estimate(
                failed_root,
                inventory[(track, "synth")],
                expected_directories=retained_directories,
            )
            raw_guitar, guitar_identity = _load_estimate(
                failed_root,
                inventory[(track, "guitar")],
                expected_directories=retained_directories,
            )
            input_identities["synth"] = synth_identity
            input_identities["guitar"] = guitar_identity
            grouped_other = reference - core["vocals"] - core["drums"] - core["bass"]
            projected = project_within_grouped_other(
                grouped_other, raw_synth, raw_guitar
            )
            quantized = quantize_six_roles(
                reference=reference,
                vocals=core["vocals"],
                drums=core["drums"],
                bass=core["bass"],
                synth=projected["synth"],
                guitar=projected["guitar"],
            )
            persisted = persist_six_roles(
                staging, case_id=track, quantized=quantized
            )
            native_other_delta = grouped_other - core["other"]
            recovered_inputs[track] = input_identities
            cases.append(
                {
                    "track_id": track,
                    "title": planned["title"],
                    "rights_category": planned["rights_category"],
                    "scored_target_roles": planned["scored_target_roles"],
                    "unscored_target_roles": planned["unscored_target_roles"],
                    "confirmed_present_targets": planned[
                        "confirmed_present_targets"
                    ],
                    "recovery_elapsed_seconds": time.monotonic() - case_started,
                    "scnet_native_other_correction": {
                        "rms": float(
                            np.sqrt(np.mean(np.square(native_other_delta)))
                        ),
                        "peak": float(
                            np.max(np.abs(native_other_delta), initial=0.0)
                        ),
                        "used_for_separation_accuracy_claim": False,
                    },
                    "projection": projected["accounting"],
                    **persisted,
                }
            )
        if (
            build_recovery_request(
                plan,
                failed_root,
                proposed_output=request["proposed_output"],
                prior_failed_root_value=prior_failed_root,
            )
            != request
        ):
            raise RuntimeError("full-song recovery failed package changed during read")
        recovery_elapsed = time.monotonic() - started
        recovery_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        report: dict[str, Any] = {
            "schema": RECOVERY_REPORT_SCHEMA,
            "report_sha256": "",
            "status": RECOVERY_REPORT_STATUS,
            "plan_sha256": plan["document_sha256"],
            "recovery_request_sha256": request["document_sha256"],
            "release_tier": "private_studio_challenger",
            "full_objective_qualification": False,
            "public_activation_allowed": False,
            "profiles": plan["profiles"],
            "workers": {
                "core_four": _worker_summary(
                    scnet, evidence_origin="persisted_worker_receipt"
                ),
                "synth": _worker_summary(
                    synth, evidence_origin="persisted_worker_receipt"
                ),
                "guitar": {
                    "profile_id": plan["profiles"]["guitar"]["profile_id"],
                    "evidence_origin": (
                        "reconstructed_from_bound_request_and_complete_arrays"
                    ),
                    "result_receipt_persisted": False,
                    "guard_counters_persisted": False,
                    "peak_memory_bytes": None,
                    "profile_inference_attempts": 3,
                    "internal_forward_calls": None,
                    "expected_internal_forward_calls": full_song_forward_budget(plan)[
                        "sw_forward_calls"
                    ],
                    "internal_forward_calls_evidence": (
                        "derived_from_bound_backend_and_complete_outputs_not_receipted"
                    ),
                    "failure_classification": (
                        "consistent_with_known_caught_loopback_bind_probe_not_proven"
                    ),
                },
            },
            "resources": {
                "failed_attempt_elapsed_seconds": failure["elapsed_seconds"],
                "known_peak_memory_bytes": {
                    "core_four": scnet["model"]["peak_unified_memory_bytes"],
                    "synth": synth["model"]["peak_unified_memory_bytes"],
                    "guitar": None,
                },
                "within_known_ceilings": None,
                "guitar_resource_gate_complete": False,
                "full_resource_gate_complete": False,
                "recovery_elapsed_seconds": recovery_elapsed,
                "recovery_peak_resident_set_bytes": recovery_peak,
            },
            "cases": cases,
            "recovered_inputs": recovered_inputs,
            "accounting": {
                "projection": plan["output_contract"]["projection"],
                "maximum_reconstruction_error_lsb": max(
                    case["maximum_reconstruction_error_lsb"] for case in cases
                ),
                "reconstruction_accounting_is_separation_accuracy": False,
            },
            "effects": {
                "historical_failed_attempt": {
                    "model_loads": 3,
                    "profile_inference_attempts": 9,
                    "canonicalization_attempts": 3,
                    "temporary_estimate_writes": 18,
                    "automatic_retry": False,
                },
                "recovery": {
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
                        len(JSON_EVIDENCE)
                        * RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "retained_guitar_array_hash_opens": (
                        3 * RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "prior_failed_audio_payload_hash_opens": (
                        request["prior_failed_package"][
                            "audio_payloads_content_hashed"
                        ]
                        * RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "prior_failed_file_hash_opens": (
                        request["prior_failed_package"]["files_content_hashed"]
                        * RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "retained_evidence_verification_passes": (
                        RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "pcm24_audio_writes": RECOVERY_AUDIO_WRITES,
                    "network_attempts": 0,
                    "automatic_retry": False,
                    "public_activation": False,
                    "source_selection": False,
                    "midi_created": False,
                    "hosting": False,
                    "redistribution": False,
                    "audio_upload": False,
                },
            },
            "failed_package_preservation": {
                "failed_report_sha256": request["retained_json"][
                    "failure_report"
                ]["sha256"],
                "prior_failed_report_sha256": request["prior_failed_package"][
                    "failure_report"
                ]["sha256"],
                "failed_tree_binding_sha256": _value_sha256(
                    request["retained_tree"]
                ),
                "prior_failed_tree_binding_sha256": request[
                    "prior_failed_package"
                ]["tree_binding_sha256"],
                "unchanged": True,
                "original_failed_root_retained": True,
                "prior_failed_root_retained": True,
            },
        }
        report["report_sha256"] = recovery_report_sha256(report)
        validate_recovery_report(report, plan, request)
        technical = staging / "TECHNICAL"
        technical.mkdir(mode=0o700)
        (technical / "RECOVERY-REQUEST.json").write_text(
            json.dumps(request, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (technical / "FULL-SONG-SIX-ROLE-RECOVERY-REPORT.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for path in technical.iterdir():
            path.chmod(0o600)
        from .separation_fine_stem_full_song_execution_review import (
            render_full_song_review,
        )

        review = staging / "REVIEW"
        review.mkdir(mode=0o700)
        page = review / "full_song_six_role_review.html"
        page.write_text(render_full_song_review(report, plan), encoding="utf-8")
        page.chmod(0o600)
        _validate_staging(staging, report, request, plan)
        if (
            build_recovery_request(
                plan,
                failed_root,
                proposed_output=request["proposed_output"],
                prior_failed_root_value=prior_failed_root,
            )
            != request
        ):
            raise RuntimeError(
                "full-song recovery retained packages changed before publication"
            )
        if output.exists() or failed_output.exists():
            raise FileExistsError("full-song recovery output became occupied")
        _exclusive_publish(
            staging,
            output,
            parent_descriptor=parent_descriptor,
            expected_parent_binding=request["output_parent_binding"],
            expected_staging_identity=staging_identity,
        )
        return report
    except BaseException as error:
        if staging is not None and staging.is_dir():
            failure = {
                "schema": RECOVERY_FAILURE_SCHEMA,
                "status": "no_model_recovery_failed_retained_no_retry",
                "plan_sha256": plan["document_sha256"],
                "recovery_request_sha256": request["document_sha256"],
                "failure_type": type(error).__name__,
                "failure": str(error),
                "checkpoint_loads": 0,
                "model_constructions": 0,
                "model_loads": 0,
                "inference_attempts": 0,
                "model_worker_subprocesses": 0,
                "automatic_retry": False,
                "public_activation": False,
                "source_selection": False,
                "midi_created": False,
                "hosting": False,
                "redistribution": False,
                "audio_upload": False,
            }
            path = staging / "RECOVERY-FAILED-REPORT.json"
            path.write_text(
                json.dumps(failure, indent=2, sort_keys=True, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            _exclusive_publish(
                staging,
                failed_output,
                parent_descriptor=parent_descriptor,
                expected_parent_binding=request["output_parent_binding"],
                expected_staging_identity=staging_identity,
            )
        raise
    finally:
        os.umask(previous_umask)
        os.close(parent_descriptor)


__all__ = [
    "RECOVERY_FAILURE_SCHEMA",
    "RECOVERY_REPORT_SCHEMA",
    "RECOVERY_REPORT_STATUS",
    "RECOVERY_REQUEST_SCHEMA",
    "RECOVERY_REQUEST_STATUS",
    "NETWORK_SANDBOX_ENV",
    "build_recovery_request",
    "execute_recovery",
    "recovery_report_sha256",
    "recovery_request_sha256",
    "validate_recovery_report",
    "validate_recovery_request",
]
