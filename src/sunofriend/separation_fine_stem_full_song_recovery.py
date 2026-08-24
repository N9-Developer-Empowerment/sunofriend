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
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import tempfile
import time
from typing import Any, Mapping, NamedTuple, Sequence

import numpy as np

from ._private_atomic_directory import (
    AtomicDirectoryUnavailable,
    UnsafeDirectoryEntryName,
    UnsafeDirectoryPath,
    exclusive_directory_rename_implementation,
    open_absolute_directory_nofollow,
    rename_directory_no_replace_at,
    require_safe_directory_entry_name,
)
from ._private_verified_audio_inputs import (
    load_verified_private_float32_npy,
    load_verified_private_pcm24,
    read_verified_private_bytes,
)
from .separation_fine_stem_full_song_execution_contract import (
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
from .separation_fine_stem_full_song_recovery_contract import (
    AUDIO_PAYLOAD_SUFFIXES as _AUDIO_PAYLOAD_SUFFIXES,
    JSON_EVIDENCE as _CONTRACT_JSON_EVIDENCE,
    RECOVERY_AUDIO_READS as _CONTRACT_RECOVERY_AUDIO_READS,
    RECOVERY_AUDIO_WRITES as _CONTRACT_RECOVERY_AUDIO_WRITES,
    RECOVERY_REPORT_SCHEMA as _CONTRACT_RECOVERY_REPORT_SCHEMA,
    RECOVERY_REPORT_STATUS as _CONTRACT_RECOVERY_REPORT_STATUS,
    RECOVERY_REQUEST_SCHEMA as _CONTRACT_RECOVERY_REQUEST_SCHEMA,
    RECOVERY_REQUEST_STATUS as _CONTRACT_RECOVERY_REQUEST_STATUS,
    RECOVERY_RETAINED_VERIFICATION_PASSES as _CONTRACT_VERIFICATION_PASSES,
    RETAINED_TREE_FILES as _CONTRACT_RETAINED_TREE_FILES,
    case_ids as _case_ids,
    recovery_report_sha256 as _contract_recovery_report_sha256,
    recovery_request_sha256 as _contract_recovery_request_sha256,
    validate_recovery_report as _validate_recovery_report_contract,
    validate_recovery_request as _validate_recovery_request_contract,
    value_sha256 as _value_sha256,
)
from .separation_fine_stem_integration_audio import (
    persist_six_roles,
    project_within_grouped_other,
    quantize_six_roles,
)


RECOVERY_FAILURE_SCHEMA = "sunofriend.fine-stem-full-song-six-role-recovery-failure.v1"
RECOVERY_REQUEST_SCHEMA = _CONTRACT_RECOVERY_REQUEST_SCHEMA
RECOVERY_REQUEST_STATUS = _CONTRACT_RECOVERY_REQUEST_STATUS
RECOVERY_REPORT_SCHEMA = _CONTRACT_RECOVERY_REPORT_SCHEMA
RECOVERY_REPORT_STATUS = _CONTRACT_RECOVERY_REPORT_STATUS
JSON_EVIDENCE = _CONTRACT_JSON_EVIDENCE
RECOVERY_AUDIO_READS = _CONTRACT_RECOVERY_AUDIO_READS
RECOVERY_AUDIO_WRITES = _CONTRACT_RECOVERY_AUDIO_WRITES
RECOVERY_RETAINED_VERIFICATION_PASSES = _CONTRACT_VERIFICATION_PASSES
RETAINED_TREE_FILES = _CONTRACT_RETAINED_TREE_FILES
NETWORK_SANDBOX_ENV = "SUNOFRIEND_FULL_SONG_RECOVERY_NETWORK_SANDBOX"
EXPECTED_FAILURE_FRAGMENT = "fine-stem canary crossed its effects boundary"
MAXIMUM_RETAINED_JSON_BYTES = 16 * 1024**2


class _RetainedRecoveryEvidence(NamedTuple):
    tree: dict[str, Any]
    documents: dict[str, dict[str, Any]]
    json_receipts: dict[str, dict[str, Any]]
    payload_inventory: list[dict[str, Any]]


class _PriorFailedPackageEvidence(NamedTuple):
    package: dict[str, Any]
    file_count: int
    audio_payload_count: int


class _TreeSnapshotEntries(NamedTuple):
    directories: list[dict[str, Any]]
    files: list[dict[str, Any]]


def recovery_request_sha256(value: Mapping[str, Any]) -> str:
    return _contract_recovery_request_sha256(value)


def recovery_report_sha256(value: Mapping[str, Any]) -> str:
    return _contract_recovery_report_sha256(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _directory_snapshot_identity(
    relative_path: str, details: os.stat_result
) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mtime_ns": details.st_mtime_ns,
        "ctime_ns": details.st_ctime_ns,
        "mode": stat.S_IMODE(details.st_mode),
    }


def _file_snapshot_identity(
    relative_path: str, details: os.stat_result
) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "bytes": details.st_size,
        "device": details.st_dev,
        "inode": details.st_ino,
        "mtime_ns": details.st_mtime_ns,
        "ctime_ns": details.st_ctime_ns,
        "mode": stat.S_IMODE(details.st_mode),
        "uid": details.st_uid,
        "links": details.st_nlink,
    }


def _enumerate_tree_snapshot(root: Path) -> _TreeSnapshotEntries:
    root_details = root.lstat()
    if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
        raise ValueError("full-song recovery tree root differs")
    directories = [_directory_snapshot_identity(".", root_details)]
    files = []
    for candidate in sorted(root.rglob("*")):
        details = candidate.lstat()
        relative = candidate.relative_to(root).as_posix()
        if stat.S_ISLNK(details.st_mode):
            raise ValueError("full-song recovery tree must not contain symlinks")
        if stat.S_ISDIR(details.st_mode):
            directories.append(_directory_snapshot_identity(relative, details))
        elif stat.S_ISREG(details.st_mode):
            files.append(_file_snapshot_identity(relative, details))
        else:
            raise ValueError("full-song recovery tree contains a special file")
    return _TreeSnapshotEntries(directories=directories, files=files)


def _validate_tree_file_inventory(
    files: Sequence[Mapping[str, Any]], expected_files: set[str] | None
) -> None:
    observed = {item["relative_path"] for item in files}
    if expected_files is not None and observed != expected_files:
        raise ValueError("full-song recovery retained file inventory differs")


def _validate_tree_directory_invariants(
    directories: Sequence[Mapping[str, Any]],
    *,
    require_private_directory_modes: bool,
) -> None:
    if directories[0]["mode"] != 0o700:
        raise ValueError("full-song recovery retained root mode differs")
    if any(item["mode"] not in {0o700, 0o755} for item in directories[1:]):
        raise ValueError("full-song recovery retained inner directory mode differs")
    if require_private_directory_modes and any(
        item["mode"] != 0o700 for item in directories
    ):
        raise ValueError("full-song recovery retained directory mode differs")


def _validate_tree_file_invariants(files: Sequence[Mapping[str, Any]]) -> None:
    if any(item["mode"] != 0o600 for item in files):
        raise ValueError("full-song recovery retained file mode differs")
    if any(item["uid"] != os.geteuid() or item["links"] != 1 for item in files):
        raise ValueError("full-song recovery retained file ownership differs")


def _tree_snapshot(
    root: Path,
    *,
    expected_files: set[str] | None = None,
    require_private_directory_modes: bool = False,
) -> dict[str, Any]:
    """Bind a private tree without following links or decoding audio."""

    entries = _enumerate_tree_snapshot(root)
    _validate_tree_file_inventory(entries.files, expected_files)
    _validate_tree_directory_invariants(
        entries.directories,
        require_private_directory_modes=require_private_directory_modes,
    )
    _validate_tree_file_invariants(entries.files)
    return {
        "directories": entries.directories,
        "files": entries.files,
        "legacy_inner_directory_modes_0755": sum(
            item["relative_path"] != "." and item["mode"] == 0o755
            for item in entries.directories
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
    try:
        return open_absolute_directory_nofollow(path)
    except AtomicDirectoryUnavailable as error:
        raise RuntimeError(
            "full-song recovery requires no-follow directory opens"
        ) from error
    except UnsafeDirectoryPath as error:
        raise ValueError("full-song recovery output parent path differs") from error


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


def _result_case_map(
    result: Mapping[str, Any], *, expected_case_ids: Sequence[str]
) -> dict[str, Mapping[str, Any]]:
    cases = result.get("cases")
    if not isinstance(cases, list) or [case.get("track_id") for case in cases] != list(
        expected_case_ids
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
        or result.get("status") != "complete_unpublished_private_temporary_estimates"
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
            {"vocals", "drums", "bass", "other"} if mode == "scnet" else {"synth"}
        )
        if (
            case.get("forward_calls") != expected_calls
            or float(case.get("elapsed_seconds", math.inf)) > 900
            or set(case.get("outputs", {})) != expected_roles
        ):
            raise ValueError("full-song recovery worker case receipt differs")
    return cases


def _worker_request_cases(
    request: Mapping[str, Any],
    *,
    mode: str,
    plan: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    cases = request.get("cases")
    if (
        request.get("schema") != WORKER_REQUEST_SCHEMA
        or request.get("mode") != mode
        or request.get("network_denied") is not True
        or not isinstance(cases, list)
        or [case.get("track_id") for case in cases] != _case_ids(plan)
    ):
        raise ValueError("full-song recovery worker request differs")
    return cases  # type: ignore[return-value]


def _expected_worker_forward_calls(
    mode: str, plan: Mapping[str, Any]
) -> int:
    budget = full_song_forward_budget(plan)
    return {
        "scnet": budget["scnet_forward_calls"],
        "mega53-synth": budget["mega53_forward_calls"],
        "sw-guitar": budget["sw_forward_calls"],
    }[mode]


def _validate_worker_source_binding(
    case: Mapping[str, Any], planned: Mapping[str, Any]
) -> None:
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


def _validate_scnet_output_binding(
    case: Mapping[str, Any], *, track: str
) -> None:
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


def _validate_specialist_output_binding(
    case: Mapping[str, Any], *, mode: str, track: str
) -> None:
    role = "synth" if mode == "mega53-synth" else "guitar"
    expected_output = f"TEMP/{role}/{track}/{role}.npy"
    if _recorded_relative_path(case.get("output")) != expected_output:
        raise ValueError("full-song recovery specialist request path differs")


def _validate_worker_case_binding(
    case: Mapping[str, Any],
    planned: Mapping[str, Any],
    *,
    mode: str,
) -> None:
    _validate_worker_source_binding(case, planned)
    if mode == "scnet":
        _validate_scnet_output_binding(case, track=planned["track_id"])
    else:
        _validate_specialist_output_binding(
            case, mode=mode, track=planned["track_id"]
        )


def _validate_worker_request_binding(
    request: Mapping[str, Any],
    *,
    mode: str,
    plan: Mapping[str, Any],
) -> None:
    cases = _worker_request_cases(request, mode=mode, plan=plan)
    expected_calls = _expected_worker_forward_calls(mode, plan)
    if request.get("expected_forward_calls") != expected_calls:
        raise ValueError("full-song recovery worker forward budget differs")
    for case, planned in zip(cases, plan["cases"]):
        _validate_worker_case_binding(case, planned, mode=mode)


def _worker_source_bindings(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "path",
        "bytes",
        "sha256",
        "sample_rate_hz",
        "channels",
        "frames",
        "subtype",
    )
    return [
        {field: case["source"][field] for field in fields} for case in request["cases"]
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
    _validate_worker_request_binding(synth_request, mode="mega53-synth", plan=plan)
    _validate_worker_request_binding(guitar_request, mode="sw-guitar", plan=plan)
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
    guitar_cases = {case["track_id"]: case for case in guitar_request["cases"]}
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
            if _recorded_relative_path(recorded["path"]) != relative or role_metadata[
                "bytes"
            ] != recorded.get("bytes"):
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
        if _recorded_relative_path(
            synth_recorded["path"]
        ) != synth_relative or synth_metadata["bytes"] != synth_recorded.get("bytes"):
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
        package / "_private_atomic_directory.py",
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


def _resolve_recovery_request_paths(
    failed_root_value: str | Path,
    *,
    proposed_output: str | Path,
) -> tuple[Path, Path]:
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
    return failed_root, output


def _expected_retained_files(plan: Mapping[str, Any]) -> set[str]:
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
    return expected_files


def _retained_guitar_hashes(
    plan: Mapping[str, Any],
    failed_root: Path,
    retained_files: Mapping[str, Mapping[str, Any]],
    retained_directories: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
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
    return guitar_sha256


def _capture_retained_recovery_evidence(
    plan: Mapping[str, Any], failed_root: Path
) -> _RetainedRecoveryEvidence:
    expected_files = _expected_retained_files(plan)
    retained_tree = _tree_snapshot(failed_root, expected_files=expected_files)
    retained_directories = _tree_directory_map(retained_tree)
    retained_files = _tree_file_map(retained_tree)
    documents, retained_json = _read_bound_json_documents(failed_root, retained_tree)
    _failure, scnet, synth, guitar_request = _validate_failure_and_requests(
        plan, documents
    )
    guitar_sha256 = _retained_guitar_hashes(
        plan, failed_root, retained_files, retained_directories
    )
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
    return _RetainedRecoveryEvidence(
        tree=retained_tree,
        documents=documents,
        json_receipts=retained_json,
        payload_inventory=inventory,
    )


def _capture_prior_failed_package(
    prior_failed_root_value: str | Path | None,
) -> _PriorFailedPackageEvidence:
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
    audio_payload_count = sum(
        PurePosixPath(item["relative_path"]).suffix.lower()
        in _AUDIO_PAYLOAD_SUFFIXES
        for item in prior_tree["files"]
    )
    file_count = len(prior_tree["files"])
    package = {
        "root": str(prior_root),
        "failure_report": {
            "relative_path": "FAILED-REPORT.json",
            "bytes": prior_report_identity["bytes"],
            "sha256": prior_report_identity["sha256"],
        },
        "tree": prior_tree,
        "tree_binding_sha256": _value_sha256(prior_tree),
        "files_content_hashed": file_count,
        "audio_payloads_content_hashed": audio_payload_count,
        "must_remain_unchanged": True,
    }
    return _PriorFailedPackageEvidence(
        package=package,
        file_count=file_count,
        audio_payload_count=audio_payload_count,
    )


def _recovery_request_document(
    plan: Mapping[str, Any],
    *,
    failed_root: Path,
    output: Path,
    retained: _RetainedRecoveryEvidence,
    prior: _PriorFailedPackageEvidence,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema": RECOVERY_REQUEST_SCHEMA,
        "document_sha256": "",
        "status": RECOVERY_REQUEST_STATUS,
        "original_plan_sha256": plan["document_sha256"],
        "failed_root": str(failed_root),
        "proposed_output": str(output),
        "output_parent_binding": _output_parent_binding(output.parent),
        "prior_failed_package": prior.package,
        "implementation": _implementation_identities(),
        "retained_json": retained.json_receipts,
        "retained_payloads": retained.payload_inventory,
        "retained_tree": retained.tree,
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
                prior.audio_payload_count * RECOVERY_RETAINED_VERIFICATION_PASSES
            ),
            "prior_failed_file_hash_opens": (
                prior.file_count * RECOVERY_RETAINED_VERIFICATION_PASSES
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
            "audio_payloads_opened": 3 + prior.audio_payload_count,
            "retained_json_files_content_read": len(JSON_EVIDENCE),
            "guitar_arrays_content_hashed": 3,
            "prior_failed_files_content_hashed": prior.file_count,
            "prior_failed_audio_payloads_content_hashed": prior.audio_payload_count,
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
            f"{prior.audio_payload_count} prior-package private audio payload(s) "
            f"during each of {RECOVERY_RETAINED_VERIFICATION_PASSES} fixed "
            "verification passes."
        ),
    }
    request["document_sha256"] = recovery_request_sha256(request)
    return request


def _build_recovery_request_with_documents(
    plan_value: Mapping[str, Any],
    failed_root_value: str | Path,
    *,
    proposed_output: str | Path,
    prior_failed_root_value: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Build an exact no-write request, hashing three guitar payloads."""

    plan = validate_fine_stem_full_song_plan(plan_value)
    failed_root, output = _resolve_recovery_request_paths(
        failed_root_value, proposed_output=proposed_output
    )
    retained = _capture_retained_recovery_evidence(plan, failed_root)
    prior = _capture_prior_failed_package(prior_failed_root_value)
    request = _recovery_request_document(
        plan,
        failed_root=failed_root,
        output=output,
        retained=retained,
        prior=prior,
    )
    return validate_recovery_request(request, plan), retained.documents


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
    """Validate through the pure contract while retaining this public facade."""

    return _validate_recovery_request_contract(value, plan_value)
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


def _inventory_map(
    request: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    mapped = {
        (item["track_id"], item["role"]): item for item in request["retained_payloads"]
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
    try:
        require_safe_directory_entry_name(staging.name)
        require_safe_directory_entry_name(destination.name)
    except UnsafeDirectoryEntryName as error:
        raise ValueError("full-song recovery publication name differs") from error
    try:
        implementation = exclusive_directory_rename_implementation()
    except AtomicDirectoryUnavailable as error:
        raise RuntimeError(
            "full-song recovery requires atomic exclusive directory publication"
        ) from error
    owns_descriptor = parent_descriptor is None
    parent_fd = (
        _open_absolute_directory_nofollow(staging.parent)
        if parent_descriptor is None
        else parent_descriptor
    )
    try:
        held_parent = os.fstat(parent_fd)
        visible_parent = staging.parent.lstat()
        if _directory_identity(held_parent) != _directory_identity(visible_parent) or (
            expected_parent_binding is not None
            and {
                "absolute_path": str(staging.parent),
                **_directory_identity(held_parent),
            }
            != expected_parent_binding
        ):
            raise RuntimeError("full-song recovery publication parent changed")
        held_staging = os.stat(staging.name, dir_fd=parent_fd, follow_symlinks=False)
        visible_staging = staging.lstat()
        if (
            not stat.S_ISDIR(held_staging.st_mode)
            or _directory_identity(held_staging) != _directory_identity(visible_staging)
            or (
                expected_staging_identity is not None
                and _directory_identity(held_staging) != dict(expected_staging_identity)
            )
            or held_staging.st_uid != os.geteuid()
            or stat.S_IMODE(held_staging.st_mode) != 0o700
        ):
            raise RuntimeError("full-song recovery staging binding changed")
        try:
            rename_directory_no_replace_at(
                parent_fd,
                staging.name,
                destination.name,
                implementation=implementation,
            )
        except FileExistsError:
            raise FileExistsError(destination) from None
        except OSError as error:
            raise OSError(
                error.errno,
                os.strerror(error.errno),
                destination,
            ) from None
    finally:
        if owns_descriptor:
            os.close(parent_fd)


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


def validate_recovery_report(
    value: Mapping[str, Any],
    plan_value: Mapping[str, Any],
    request_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate through the pure contract while retaining this public facade."""

    return _validate_recovery_report_contract(value, plan_value, request_value)
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
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
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
            persisted = persist_six_roles(staging, case_id=track, quantized=quantized)
            native_other_delta = grouped_other - core["other"]
            recovered_inputs[track] = input_identities
            cases.append(
                {
                    "track_id": track,
                    "title": planned["title"],
                    "rights_category": planned["rights_category"],
                    "scored_target_roles": planned["scored_target_roles"],
                    "unscored_target_roles": planned["unscored_target_roles"],
                    "confirmed_present_targets": planned["confirmed_present_targets"],
                    "recovery_elapsed_seconds": time.monotonic() - case_started,
                    "scnet_native_other_correction": {
                        "rms": float(np.sqrt(np.mean(np.square(native_other_delta)))),
                        "peak": float(np.max(np.abs(native_other_delta), initial=0.0)),
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
                        len(JSON_EVIDENCE) * RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "retained_guitar_array_hash_opens": (
                        3 * RECOVERY_RETAINED_VERIFICATION_PASSES
                    ),
                    "prior_failed_audio_payload_hash_opens": (
                        request["prior_failed_package"]["audio_payloads_content_hashed"]
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
                "failed_report_sha256": request["retained_json"]["failure_report"][
                    "sha256"
                ],
                "prior_failed_report_sha256": request["prior_failed_package"][
                    "failure_report"
                ]["sha256"],
                "failed_tree_binding_sha256": _value_sha256(request["retained_tree"]),
                "prior_failed_tree_binding_sha256": request["prior_failed_package"][
                    "tree_binding_sha256"
                ],
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
                json.dumps(failure, indent=2, sort_keys=True, allow_nan=False) + "\n",
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
