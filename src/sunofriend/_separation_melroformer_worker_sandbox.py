"""Private synthetic worker proof for the MelRoFormer sandbox boundary.

The parent launches one code-owned worker under a fixed macOS profile that
denies network, process forks and all writes outside one fresh staging tree.
The worker performs deliberate denied canaries and materializes only synthetic
PCM24 outputs. The parent independently verifies the output tree. No model,
checkpoint or authorised song audio is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Mapping

from ._separation_macos_sandbox_probe import (
    SANDBOX_EXEC_PATH,
    _regular_file_identity,
)
from ._separation_melroformer_pcm24_quarantine import (
    _validate_private_melroformer_pcm24_quarantine,
    _verify_private_melroformer_pcm24_quarantine,
)
from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-melroformer-synthetic-worker-sandbox.v1"
POLICY_ID = "private-melroformer-synthetic-worker-sandbox-v1"
WORKER_RELATIVE_PATH = "scripts/private-melroformer-worker.py"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_MAXIMUM_STDOUT_BYTES = 64 * 1024


def _run_private_melroformer_synthetic_worker_canary(
    *,
    repository_root: str | Path,
    runtime_path: str | Path,
    staging_directory: str | Path,
) -> Mapping[str, Any]:
    """Run and parent-verify one bounded synthetic worker on Darwin."""

    if platform.system() != "Darwin":
        raise RuntimeError("MelRoFormer synthetic worker sandbox requires Darwin")
    repository = Path(repository_root).expanduser().resolve(strict=True)
    if not repository.is_dir() or repository.is_symlink():
        raise ValueError("MelRoFormer worker repository root must be a directory")
    worker_path = repository / WORKER_RELATIVE_PATH
    worker_before = _regular_non_symlink_file_identity(worker_path)
    runtime_launch_path = Path(runtime_path).expanduser().absolute()
    runtime_before = _regular_file_identity(runtime_launch_path)
    provider_before = _regular_file_identity(SANDBOX_EXEC_PATH)

    staging = Path(staging_directory).expanduser().absolute()
    staging.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(staging, 0o700)
    output = staging / "output"
    outside = staging.parent / f".{staging.name}-outside-write-canary"
    if outside.exists() or outside.is_symlink():
        raise ValueError("MelRoFormer outside-write canary path already exists")
    profile = _sandbox_profile(staging)
    environment = {
        "HOME": "/var/empty",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(repository / "src"),
        "TMPDIR": "/var/empty",
    }
    completed = subprocess.run(
        [
            provider_before["resolved_path"],
            "-p",
            profile,
            str(runtime_launch_path),
            "-B",
            str(worker_path),
            "--synthetic-canary",
            "--destination",
            str(output),
            "--outside-write-canary",
            str(outside),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=repository,
        env=environment,
        timeout=30.0,
    )
    if (
        completed.returncode != 0
        or completed.stderr
        or not 1 <= len(completed.stdout.encode("utf-8")) <= _MAXIMUM_STDOUT_BYTES
    ):
        raise RuntimeError(
            "MelRoFormer synthetic worker did not complete cleanly: "
            f"exit={completed.returncode}; "
            f"stderr_bytes={len(completed.stderr.encode('utf-8'))}; "
            "stderr_sha256="
            f"{hashlib.sha256(completed.stderr.encode('utf-8')).hexdigest()}"
        )
    try:
        child = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("MelRoFormer synthetic worker returned invalid JSON") from error
    _validate_child_envelope(child)
    child_quarantine = _validate_private_melroformer_pcm24_quarantine(
        child["quarantine"]
    )
    _validate_child_canaries(child["canaries"])
    if outside.exists() or outside.is_symlink():
        raise RuntimeError("MelRoFormer outside-write canary unexpectedly persisted")
    if sorted(item.name for item in staging.iterdir()) != ["output"]:
        raise RuntimeError("MelRoFormer staging tree contains an unexpected entry")

    np = __import__("numpy")
    source, _, _ = _synthetic_arrays(np)
    claims = {
        item["role"]: {
            key: item[key]
            for key in ("role", "relative_path", "bytes", "sha256", "geometry")
        }
        for item in child_quarantine["outputs"]
    }
    parent_quarantine = _verify_private_melroformer_pcm24_quarantine(
        destination=output,
        source=source,
        claims=claims,
        np=np,
    )
    if parent_quarantine["evidence_sha256"] != child_quarantine["evidence_sha256"]:
        raise RuntimeError("MelRoFormer child and parent quarantine evidence differ")

    worker_after = _regular_non_symlink_file_identity(worker_path)
    runtime_after = _regular_file_identity(runtime_launch_path)
    provider_after = _regular_file_identity(SANDBOX_EXEC_PATH)
    if any(
        before[key] != after[key]
        for before, after in (
            (worker_before, worker_after),
            (runtime_before, runtime_after),
            (provider_before, provider_after),
        )
        for key in ("bytes", "sha256")
    ):
        raise RuntimeError("MelRoFormer worker launch artifact changed during canary")

    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "synthetic_worker_complete_parent_verified",
        "artifacts": {
            "provider": _path_free_identity(provider_before),
            "runtime": _path_free_identity(runtime_before),
            "worker": _path_free_identity(worker_before),
            "unchanged_after_worker": True,
            "hash_before_exec_path_toctou_closed": False,
            "complete_python_import_closure_bound": False,
        },
        "isolation": {
            "profile_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
            "environment_sha256": hashlib.sha256(
                _canonical_json_bytes(environment)
            ).hexdigest(),
            "network_denial": "enforced_canary_observed",
            "child_process_denial": "enforced_canary_observed",
            "outside_write_denial": "enforced_canary_observed",
            "arbitrary_attempt_stream_observed": False,
            "allowed_write_scope": "fresh_private_staging_tree_only",
        },
        "canaries": child["canaries"],
        "quarantine": {
            "child_evidence_sha256": child_quarantine["evidence_sha256"],
            "parent_evidence_sha256": parent_quarantine["evidence_sha256"],
            "evidence_identical": True,
            "output_count": len(parent_quarantine["outputs"]),
            "maximum_integer_reconstruction_error_lsb": parent_quarantine[
                "additive_reconstruction"
            ]["maximum_integer_error_lsb"],
        },
        "conclusion": {
            "network_denial_bound_to_synthetic_worker": True,
            "child_process_denial_bound_to_synthetic_worker": True,
            "outside_write_denial_bound_to_synthetic_worker": True,
            "pcm24_quarantine_bound_to_synthetic_worker": True,
            "model_worker_verified": False,
            "worker_authorized_for_product": False,
        },
        "permissions": {
            "checkpoint_access_permitted": False,
            "model_import_permitted": False,
            "authorised_audio_access_permitted": False,
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "process_started": True,
            "filesystem_written": True,
            "synthetic_audio_persisted": True,
            "network_used": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "authorised_audio_read": False,
            "source_graph_changed": False,
        },
        "limitations": {
            "synthetic_worker_only": True,
            "model_or_checkpoint_loaded": False,
            "arbitrary_model_attempt_stream_observed": False,
            "hash_before_exec_path_toctou_closed": False,
            "complete_python_import_closure_bound": False,
            "ordinary_outputs_can_change_after_parent_verification": True,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_melroformer_synthetic_worker_canary(document)


def _validate_private_melroformer_synthetic_worker_canary(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    required = {
        "schema",
        "policy_id",
        "status",
        "artifacts",
        "isolation",
        "canaries",
        "quarantine",
        "conclusion",
        "permissions",
        "effects",
        "limitations",
        "evidence_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("MelRoFormer synthetic worker evidence fields differ")
    digest = value.pop("evidence_sha256")
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("MelRoFormer synthetic worker evidence self-hash differs")
    if (
        value["schema"] != SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["status"] != "synthetic_worker_complete_parent_verified"
    ):
        raise ValueError("MelRoFormer synthetic worker evidence identity differs")
    for name in ("provider", "runtime", "worker"):
        identity = value["artifacts"].get(name)
        if (
            not isinstance(identity, dict)
            or set(identity) != {"bytes", "sha256"}
            or type(identity["bytes"]) is not int
            or identity["bytes"] <= 0
            or not _is_sha(identity["sha256"])
        ):
            raise ValueError("MelRoFormer synthetic worker artifact evidence differs")
    if set(value["artifacts"]) != {
        "provider",
        "runtime",
        "worker",
        "unchanged_after_worker",
        "hash_before_exec_path_toctou_closed",
        "complete_python_import_closure_bound",
    }:
        raise ValueError("MelRoFormer synthetic worker artifact fields differ")
    if (
        value["artifacts"].get("unchanged_after_worker") is not True
        or value["artifacts"].get("hash_before_exec_path_toctou_closed") is not False
        or value["artifacts"].get("complete_python_import_closure_bound") is not False
    ):
        raise ValueError("MelRoFormer synthetic worker artifact conclusion differs")
    _validate_child_canaries(value["canaries"])
    if set(value["isolation"]) != {
        "profile_sha256",
        "environment_sha256",
        "network_denial",
        "child_process_denial",
        "outside_write_denial",
        "arbitrary_attempt_stream_observed",
        "allowed_write_scope",
    } or value["isolation"].get("network_denial") != "enforced_canary_observed" or (
        value["isolation"].get("child_process_denial")
        != "enforced_canary_observed"
        or value["isolation"].get("outside_write_denial")
        != "enforced_canary_observed"
        or value["isolation"].get("arbitrary_attempt_stream_observed") is not False
        or value["isolation"].get("allowed_write_scope")
        != "fresh_private_staging_tree_only"
        or not _is_sha(value["isolation"].get("profile_sha256"))
        or not _is_sha(value["isolation"].get("environment_sha256"))
    ):
        raise ValueError("MelRoFormer synthetic worker isolation evidence differs")
    quarantine = value["quarantine"]
    if (
        set(quarantine)
        != {
            "child_evidence_sha256",
            "parent_evidence_sha256",
            "evidence_identical",
            "output_count",
            "maximum_integer_reconstruction_error_lsb",
        }
        or
        not _is_sha(quarantine.get("child_evidence_sha256"))
        or quarantine.get("parent_evidence_sha256")
        != quarantine.get("child_evidence_sha256")
        or quarantine.get("evidence_identical") is not True
        or quarantine.get("output_count") != 2
        or type(quarantine.get("maximum_integer_reconstruction_error_lsb"))
        is not int
        or not 0 <= quarantine["maximum_integer_reconstruction_error_lsb"] <= 2
    ):
        raise ValueError("MelRoFormer synthetic worker quarantine evidence differs")
    if value["conclusion"] != {
        "network_denial_bound_to_synthetic_worker": True,
        "child_process_denial_bound_to_synthetic_worker": True,
        "outside_write_denial_bound_to_synthetic_worker": True,
        "pcm24_quarantine_bound_to_synthetic_worker": True,
        "model_worker_verified": False,
        "worker_authorized_for_product": False,
    }:
        raise ValueError("MelRoFormer synthetic worker conclusion differs")
    if value["permissions"] != {
        "checkpoint_access_permitted": False,
        "model_import_permitted": False,
        "authorised_audio_access_permitted": False,
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }:
        raise ValueError("MelRoFormer synthetic worker grants a permission")
    if value["effects"] != {
        "process_started": True,
        "filesystem_written": True,
        "synthetic_audio_persisted": True,
        "network_used": False,
        "checkpoint_opened": False,
        "model_imported": False,
        "authorised_audio_read": False,
        "source_graph_changed": False,
    }:
        raise ValueError("MelRoFormer synthetic worker effects differ")
    if value["limitations"] != {
        "synthetic_worker_only": True,
        "model_or_checkpoint_loaded": False,
        "arbitrary_model_attempt_stream_observed": False,
        "hash_before_exec_path_toctou_closed": False,
        "complete_python_import_closure_bound": False,
        "ordinary_outputs_can_change_after_parent_verification": True,
    }:
        raise ValueError("MelRoFormer synthetic worker limitations differ")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "://" in encoded:
        raise ValueError("MelRoFormer synthetic worker evidence is not path-free")
    return _freeze_json(checked)


def _synthetic_arrays(np: Any) -> tuple[Any, Any, Any]:
    timeline = np.arange(4_096, dtype=np.float32) / np.float32(44_100.0)
    left = (0.3 * np.sin(2 * np.pi * 220 * timeline)).astype(np.float32)
    right = (0.25 * np.sin(2 * np.pi * 330 * timeline)).astype(np.float32)
    source = np.stack([left, right], axis=1)
    vocals = (source * np.float32(0.41)).astype(np.float32)
    instrumental = (source - vocals).astype(np.float32)
    return source, vocals, instrumental


def _sandbox_profile(staging: Path) -> str:
    value = str(staging.resolve(strict=True))
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("MelRoFormer staging path cannot be represented in profile")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        "(deny process-fork)\n"
        "(deny file-write*)\n"
        f'(allow file-write* (subpath "{escaped}"))\n'
    )


def _validate_child_canaries(value: Any) -> None:
    if value != {
        "network_connect_ex": 1,
        "network_errno_name": "EPERM",
        "process_fork_errno": 1,
        "process_fork_errno_name": "EPERM",
        "outside_write_errno": 1,
        "outside_write_errno_name": "EPERM",
    }:
        raise ValueError("MelRoFormer synthetic worker canary results differ")


def _validate_child_envelope(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "status", "canaries", "quarantine"}
        or value["schema"]
        != "sunofriend.private-melroformer-synthetic-worker-child.v1"
        or value["status"] != "complete"
    ):
        raise ValueError("MelRoFormer synthetic worker child envelope differs")


def _regular_non_symlink_file_identity(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("MelRoFormer worker must be a non-symlink regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("MelRoFormer worker changed while hashing")
    return {
        "resolved_path": str(path),
        "bytes": before.st_size,
        "sha256": digest.hexdigest(),
    }


def _path_free_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"bytes": value["bytes"], "sha256": value["sha256"]}


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "POLICY_ID",
    "SCHEMA",
    "_run_private_melroformer_synthetic_worker_canary",
    "_synthetic_arrays",
    "_validate_private_melroformer_synthetic_worker_canary",
]
