"""Read-only plan for one exact private MLX MelBand-RoFormer challenger.

This candidate has stronger checkpoint identity and licence evidence than the
blocked broad BS-RoFormer release, but it is intentionally narrower: it
separates vocals and derives instrumental as the residual.  No installer,
downloader, model import, worker or product route is provided here.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from ._separation_melroformer_adapter_contract import (
    SCHEMA as ADAPTER_OBSERVATION_SCHEMA,
)
from ._separation_melroformer_runtime_evidence import (
    RUNTIME_LOCK,
    RUNTIME_LOCK_SHA256,
    SOURCE_MANIFEST,
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION as RUNTIME_SOURCE_REVISION,
    _verify_private_melroformer_source_tree,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
    CONVERSION_REPOSITORY,
    CONVERSION_REVISION,
    SOURCE_CHECKPOINT_SHA256,
    SOURCE_REPOSITORY,
    SOURCE_REVISION,
    UPSTREAM_EVIDENCE,
    UPSTREAM_EVIDENCE_BYTES,
    UPSTREAM_EVIDENCE_SHA256,
)
from ._separation_melroformer_worker_protocol import SCHEMA as WORKER_PROTOCOL_SCHEMA
from ._separation_safetensors_inspection import (
    SCHEMA as SAFETENSORS_INSPECTION_SCHEMA,
    _inspect_private_safetensors,
)


PLAN_SCHEMA = "sunofriend.private-melroformer-challenger-plan.v3"
POLICY_ID = "private-mlx-melroformer-kim-vocal-2-plan-v3"
AUDITED_AT = "2026-08-01"
APPROVAL_RECORDED_AT = "2026-08-01"
CHECKPOINT_NAME = "model.safetensors"
CHECKPOINT_URL = (
    "https://huggingface.co/mlx-community/"
    "mel-roformer-kim-vocal-2-mlx/resolve/"
    f"{CONVERSION_REVISION}/{CHECKPOINT_NAME}"
)
CONFIG_NAME = "config.json"
CONFIG_BYTES = 833
CONFIG_SHA256 = "3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58"
LICENSE_NAME = "LICENSE"
LICENSE_BYTES = 1_500
LICENSE_SHA256 = "1aa245b55067df5c63c847894e7040f76fa79ddde83e9e5ed8a5c29ef1865c14"
_BASE_BLOCKERS = (
    "apple_runtime_resource_bounds_unmeasured",
    "conversion_parity_not_independently_verified",
    "real_model_adapter_not_implemented",
    "runtime_worker_not_implemented",
)


def _build_private_melroformer_challenger_plan(
    *,
    checkpoint_path: str | Path | None = None,
    source_root: str | Path | None = None,
    companion_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return one deterministic plan without network, imports or execution."""

    local_checkpoint = (
        _inspect_local_checkpoint(checkpoint_path)
        if checkpoint_path is not None
        else {
            "provided": False,
            "path": None,
            "bytes": None,
            "sha256": None,
            "published_size_match": False,
            "published_sha256_match": False,
            "cryptographic_identity_verified": False,
        }
    )
    static_inspection = (
        _inspect_private_safetensors(
            local_checkpoint["path"],
            expected_bytes=CONVERSION_CHECKPOINT_BYTES,
            expected_sha256=CONVERSION_CHECKPOINT_SHA256,
        )
        if local_checkpoint["cryptographic_identity_verified"]
        else None
    )
    source_observation = (
        _verify_private_melroformer_source_tree(source_root)
        if source_root is not None
        else None
    )
    companion_observation = (
        _inspect_companion_files(companion_root)
        if companion_root is not None
        else None
    )
    source_ready = source_observation is not None
    companions_ready = bool(
        companion_observation
        and companion_observation["all_cryptographic_identities_verified"]
    )
    inspection_ready = static_inspection is not None
    artifact_preflight_complete = bool(
        local_checkpoint["cryptographic_identity_verified"]
        and source_ready
        and companions_ready
        and inspection_ready
    )
    blockers = list(_BASE_BLOCKERS)
    if not local_checkpoint["cryptographic_identity_verified"]:
        blockers.append("checkpoint_local_hash_unverified")
    if not source_ready:
        blockers.append("runtime_source_materialisation_missing")
    if not companions_ready:
        blockers.append("checkpoint_companion_files_unverified")
    if not inspection_ready:
        blockers.append("safetensors_static_inspection_not_completed")
    blockers.sort()
    return {
        "schema": PLAN_SCHEMA,
        "status": "blocked",
        "policy_id": POLICY_ID,
        "audit_date": AUDITED_AT,
        "read_only": True,
        "candidate": {
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "architecture": "Mel-Band-RoFormer",
            "checkpoint_family": "Kim Vocal 2",
            "purpose": "independent role-specific vocal separation challenger",
            "roles": ["vocals"],
            "derived_roles": ["instrumental"],
            "derived_role_equation": "instrumental = mixture - vocals",
            "broad_separator": False,
            "sample_rate": 44_100,
            "channels": 2,
            "chunk_frames": 352_800,
            "chunk_seconds": 8.0,
            "overlap": 2,
            "automatic_selection": False,
            "automatic_promotion": False,
        },
        "source": {
            "conversion_repository": CONVERSION_REPOSITORY,
            "conversion_revision": CONVERSION_REVISION,
            "original_repository": SOURCE_REPOSITORY,
            "original_revision": SOURCE_REVISION,
            "original_checkpoint_sha256": SOURCE_CHECKPOINT_SHA256,
            "conversion_tool_revision_reported": "8380ab8",
            "source_identity_pinned": True,
            "runtime_source_repository": "Blaizzy/mlx-audio",
            "runtime_source_revision": RUNTIME_SOURCE_REVISION,
            "runtime_source_manifest": SOURCE_MANIFEST,
            "runtime_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "runtime_source_audited_by_sunofriend": True,
            "runtime_source_materialised": source_ready,
            "runtime_source_observation": source_observation,
            "upstream_from_pretrained_permitted": False,
            "stale_runtime_gpl_comment_recorded": True,
        },
        "checkpoint": {
            "name": CHECKPOINT_NAME,
            "url": CHECKPOINT_URL,
            "format": "safetensors",
            "published_bytes": CONVERSION_CHECKPOINT_BYTES,
            "published_sha256": CONVERSION_CHECKPOINT_SHA256,
            "published_terms": "MIT",
            "checkpoint_specific_terms_verified": True,
            "published_identity_pinned": True,
            "pickle_deserialization_required": False,
            "acquisition_status": (
                "local_identity_verified"
                if local_checkpoint["cryptographic_identity_verified"]
                else (
                    "local_identity_mismatch"
                    if local_checkpoint["provided"]
                    else "not_present"
                )
            ),
            "download_permitted": False,
            "static_inspection_contract": SAFETENSORS_INSPECTION_SCHEMA,
            "static_inspection_contract_defined": True,
            "static_inspection_completed": inspection_ready,
            "static_inspection": static_inspection,
            "model_loading_permitted": False,
            "redistribution_approved_by_sunofriend": False,
            "local_observation": local_checkpoint,
        },
        "companion_files": {
            "published": {
                CONFIG_NAME: {
                    "bytes": CONFIG_BYTES,
                    "sha256": CONFIG_SHA256,
                    "identity_pinned": True,
                },
                LICENSE_NAME: {
                    "bytes": LICENSE_BYTES,
                    "sha256": LICENSE_SHA256,
                    "identity_pinned": True,
                },
            },
            "local_observation": companion_observation,
            "all_cryptographic_identities_verified": companions_ready,
        },
        "licensing": {
            "original_checkpoint_owner": "Kimberley Jensen",
            "original_checkpoint_relicensed_to": "MIT",
            "original_relicense_revision": SOURCE_REVISION,
            "conversion_license": "MIT",
            "conversion_license_names_original_weights": True,
            "private_local_evaluation_allowed_by_published_terms": True,
            "legal_advice": False,
            "explicit_user_approval_recorded": True,
            "approval_recorded_at": APPROVAL_RECORDED_AT,
            "approval_scope": "exact checkpoint for private local evaluation only",
            "checkpoint_redistribution_approved": False,
        },
        "alternatives_reviewed": [
            {
                "candidate_id": "viperx-bs-roformer-1297",
                "published_sha256": (
                    "5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa"
                ),
                "identity_corroborated": True,
                "checkpoint_terms_authoritatively_verified": False,
                "admitted": False,
            },
            {
                "candidate_id": "viperx-melband-roformer-1143",
                "published_sha256": (
                    "21b9d0958e35b8ebfbe2afe69bbd5444e5ffe2f5d80ae0d583b833d2f3c0d139"
                ),
                "identity_corroborated": True,
                "checkpoint_terms_authoritatively_verified": False,
                "admitted": False,
            },
        ],
        "upstream_evidence": {
            "path": UPSTREAM_EVIDENCE,
            "bytes": UPSTREAM_EVIDENCE_BYTES,
            "sha256": UPSTREAM_EVIDENCE_SHA256,
            "observed_at": AUDITED_AT,
            "official_primary_sources_only": True,
            "checkpoint_terms_verified": True,
            "checkpoint_published_sha256_verified": True,
            "local_checkpoint_identity_verified": local_checkpoint[
                "cryptographic_identity_verified"
            ],
            "verified_in_this_call": False,
            "verification_command": (
                "scripts/private-melroformer-upstream-evidence.py "
                "--repository-root /absolute/path/to/Sunofriend"
            ),
        },
        "runtime": {
            "target": "Apple silicon MLX in a fresh isolated environment",
            "reported_package": "mlx-audio>=0.4.3",
            "reported_mlx_version_at_conversion": "0.31.0",
            "reported_weight_dtype": "bfloat16",
            "reported_parity_sdr_db": 66.08,
            "reported_parity_is_model_ground_truth_score": False,
            "reported_parity_independently_verified_by_sunofriend": False,
            "exact_source_manifest_defined": True,
            "exact_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "dependency_input_defined": True,
            "dependency_lock_defined": True,
            "dependency_lock": RUNTIME_LOCK,
            "dependency_lock_sha256": RUNTIME_LOCK_SHA256,
            "dependency_license_audit_defined": True,
            "minimal_packages": ["mlx", "mlx-metal", "numpy"],
            "upstream_mlx_audio_distribution_required": False,
            "installed": False,
            "installation_command": None,
            "installation_permitted": False,
            "network_denial_verified": False,
            "apple_resource_bounds_measured": False,
            "worker_protocol_schema": WORKER_PROTOCOL_SCHEMA,
            "worker_protocol_defined": True,
            "adapter_observation_schema": ADAPTER_OBSERVATION_SCHEMA,
            "synthetic_adapter_contract_defined": True,
            "real_adapter_implemented": False,
            "worker_implemented": False,
        },
        "evaluation_contract": {
            "controls": [
                "pinned local HTDemucs vocals",
                "authorised provider vocal leaves when present",
            ],
            "initial_evidence": "existing sealed authorised 15-second excerpts",
            "maximum_initial_excerpt_seconds": 15.0,
            "maximum_initial_cases": 2,
            "required_outputs": ["vocals", "instrumental"],
            "primary_quality_gates": [
                "improve vocal isolation without damaging source-clock alignment",
                "improve downstream vocal-melody MIDI over the existing zero-note failure",
                "improve human recognition in an equal-level blind listening comparison",
                "preserve mixture = vocals + instrumental accounting within PCM tolerance",
                "record runtime, peak memory and offline behaviour",
                "produce no automatic winner, selection or public result",
            ],
        },
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "candidate_registered": True,
            "checkpoint_published_identity_pinned": True,
            "checkpoint_local_identity_verified": local_checkpoint[
                "cryptographic_identity_verified"
            ],
            "checkpoint_terms_verified": True,
            "artifact_preflight_complete": artifact_preflight_complete,
            "private_evaluation_eligible": artifact_preflight_complete,
            "worker_start_permitted": False,
            "blockers": blockers,
            "next_safe_actions": [
                "implement the isolated real-model bridge behind the synthetic-only adapter contract",
                "implement the two-role excerpt worker behind the existing non-executable protocol",
                "measure resource and offline bounds before any wider evaluation",
            ],
        },
        "effects": {
            "filesystem_written": False,
            "local_checkpoint_opened": local_checkpoint["provided"],
            "runtime_source_opened": source_ready,
            "checkpoint_companions_opened": companion_root is not None,
            "network_used": False,
            "package_installed": False,
            "checkpoint_downloaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "source_graph_changed": False,
            "simple_or_studio_availability_changed": False,
        },
    }


def _inspect_companion_files(value: str | Path) -> dict[str, Any]:
    root = Path(value).expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("MelBand-RoFormer companion root must be a directory")
    files = {
        CONFIG_NAME: _inspect_file_identity(
            root / CONFIG_NAME, expected_bytes=CONFIG_BYTES, expected_sha256=CONFIG_SHA256
        ),
        LICENSE_NAME: _inspect_file_identity(
            root / LICENSE_NAME,
            expected_bytes=LICENSE_BYTES,
            expected_sha256=LICENSE_SHA256,
        ),
    }
    return {
        "root": str(root),
        "files": files,
        "all_cryptographic_identities_verified": all(
            item["cryptographic_identity_verified"] for item in files.values()
        ),
    }


def _inspect_file_identity(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> dict[str, Any]:
    before = path.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ValueError("MelBand-RoFormer companion must be a single-link regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(before):
            raise ValueError("MelBand-RoFormer companion changed before hashing")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = path.lstat()
    if _identity(after) != _identity(opened) or _identity(rebound) != _identity(opened):
        raise ValueError("MelBand-RoFormer companion changed during hashing")
    sha256 = digest.hexdigest()
    size_match = opened.st_size == expected_bytes
    hash_match = sha256 == expected_sha256
    return {
        "path": str(path),
        "bytes": opened.st_size,
        "sha256": sha256,
        "published_size_match": size_match,
        "published_sha256_match": hash_match,
        "cryptographic_identity_verified": size_match and hash_match,
    }


def _inspect_local_checkpoint(value: str | Path) -> dict[str, Any]:
    path = Path(value).expanduser().absolute()
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(
            "MelBand-RoFormer checkpoint must be a non-symlink regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if (
            os.get_inheritable(descriptor)
            or not stat.S_ISREG(opened.st_mode)
            or _identity(opened) != _identity(before)
        ):
            raise ValueError("MelBand-RoFormer checkpoint changed before hashing")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = path.lstat()
    if _identity(after) != _identity(opened) or _identity(rebound) != _identity(opened):
        raise ValueError("MelBand-RoFormer checkpoint changed during hashing")
    sha256 = digest.hexdigest()
    size_match = opened.st_size == CONVERSION_CHECKPOINT_BYTES
    hash_match = sha256 == CONVERSION_CHECKPOINT_SHA256
    return {
        "provided": True,
        "path": str(path),
        "bytes": opened.st_size,
        "sha256": sha256,
        "published_size_match": size_match,
        "published_sha256_match": hash_match,
        "cryptographic_identity_verified": size_match and hash_match,
    }


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


__all__ = [
    "AUDITED_AT",
    "APPROVAL_RECORDED_AT",
    "CHECKPOINT_NAME",
    "CHECKPOINT_URL",
    "PLAN_SCHEMA",
    "_build_private_melroformer_challenger_plan",
    "_inspect_local_checkpoint",
    "_inspect_companion_files",
]
