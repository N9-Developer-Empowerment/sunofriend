"""Verify tracked upstream evidence for the private MelBand-RoFormer plan.

The snapshot is a bounded record of exact Hugging Face model metadata, file
identities and the original checkpoint owner's licence history.  This module
never uses the network, opens either checkpoint or turns published permission
into authority to download, install or run a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping


UPSTREAM_EVIDENCE = "private-separation-melroformer-upstream-evidence.json"
UPSTREAM_EVIDENCE_BYTES = 7_573
UPSTREAM_EVIDENCE_SHA256 = (
    "2f5b00c591241318dba834bde736580407b4313af9b4d588a2a96406de6a18a2"
)
UPSTREAM_EVIDENCE_SCHEMA = "sunofriend.private-melroformer-upstream-evidence.v1"
UPSTREAM_VERIFICATION_SCHEMA = (
    "sunofriend.private-melroformer-upstream-evidence-verification.v1"
)
OBSERVED_AT = "2026-08-01"
CONVERSION_REPOSITORY = "mlx-community/mel-roformer-kim-vocal-2-mlx"
CONVERSION_REVISION = "64cbfcb004e39430e5f584552c05949440ec39ce"
CONVERSION_CHECKPOINT = "model.safetensors"
CONVERSION_CHECKPOINT_BYTES = 456_483_463
CONVERSION_CHECKPOINT_SHA256 = (
    "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
)
SOURCE_REPOSITORY = "KimberleyJSN/melbandroformer"
SOURCE_REVISION = "ac9b0614ab3cd7f77219e18ba494dfd93956c348"
SOURCE_CHECKPOINT = "MelBandRoformer.ckpt"
SOURCE_CHECKPOINT_BYTES = 913_106_900
SOURCE_CHECKPOINT_SHA256 = (
    "87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e"
)
_MAXIMUM_EVIDENCE_BYTES = 64 * 1024


def _verify_private_melroformer_upstream_evidence(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Read and validate the exact tracked snapshot without network access."""

    root = Path(repository_root).expanduser().absolute()
    before = root.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ValueError("MelBand-RoFormer repository root must be a directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(root, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(before):
            raise ValueError(
                "MelBand-RoFormer repository root changed before verification"
            )
        contents = _read_evidence_file(descriptor)
        after = root.lstat()
        if _identity(after) != _identity(before):
            raise ValueError(
                "MelBand-RoFormer repository root changed during verification"
            )
    finally:
        os.close(descriptor)
    return _report_from_verified_contents(contents)


def _report_from_verified_contents(contents: bytes) -> dict[str, Any]:
    if len(contents) != UPSTREAM_EVIDENCE_BYTES:
        raise ValueError("MelBand-RoFormer evidence file size differs")
    digest = hashlib.sha256(contents).hexdigest()
    if digest != UPSTREAM_EVIDENCE_SHA256:
        raise ValueError("MelBand-RoFormer evidence file hash differs")
    try:
        document = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "MelBand-RoFormer evidence is not valid UTF-8 JSON"
        ) from error
    if not isinstance(document, Mapping):
        raise ValueError("MelBand-RoFormer evidence must be an object")
    _validate_private_melroformer_upstream_evidence(document)
    report: dict[str, Any] = {
        "schema": UPSTREAM_VERIFICATION_SCHEMA,
        "status": "verified_candidate_identity_and_terms_not_authorized",
        "path_free": True,
        "verification_sha256": "",
        "snapshot": {
            "path": UPSTREAM_EVIDENCE,
            "bytes": len(contents),
            "sha256": digest,
            "observed_at": document["observed_at"],
        },
        "candidate": {
            "repository": CONVERSION_REPOSITORY,
            "revision": CONVERSION_REVISION,
            "architecture": "Mel-Band-RoFormer",
            "checkpoint_family": "Kim Vocal 2",
            "target": "vocals",
            "derived_residual": "instrumental = mixture - vocals",
        },
        "checkpoint": {
            "name": CONVERSION_CHECKPOINT,
            "bytes": CONVERSION_CHECKPOINT_BYTES,
            "published_sha256": CONVERSION_CHECKPOINT_SHA256,
            "format": "safetensors",
            "published_terms": "MIT",
            "terms_verified": True,
            "published_identity_pinned": True,
            "local_identity_verified": False,
        },
        "source_checkpoint": {
            "repository": SOURCE_REPOSITORY,
            "revision": SOURCE_REVISION,
            "name": SOURCE_CHECKPOINT,
            "bytes": SOURCE_CHECKPOINT_BYTES,
            "published_sha256": SOURCE_CHECKPOINT_SHA256,
            "owner_relicense": "MIT",
            "owner_relicense_verified": True,
            "independent_matching_lfs_records": 2,
        },
        "alternatives": {
            "viperx_identity_records_reviewed": 2,
            "viperx_checkpoint_terms_authoritatively_verified": False,
            "viperx_candidates_admitted": 0,
            "secondary_lead_archive_sha256": (
                "8f0e06928eea399648e0b30df5e41f415b72b411aecf96a5e1f017c223d3924f"
            ),
            "download_helper_executed": False,
        },
        "claims": {
            "apple_silicon_runtime_reported": True,
            "parity_sdr_db_reported": 66.08,
            "parity_independently_verified_by_sunofriend": False,
            "resource_bounds_measured_by_sunofriend": False,
        },
        "readiness": {
            "checkpoint_terms_verified": True,
            "checkpoint_allowed_use_verified_for_private_local_evaluation": True,
            "checkpoint_published_sha256_verified": True,
            "checkpoint_local_identity_verified": False,
            "runtime_source_audited": False,
            "runtime_dependencies_locked": False,
            "explicit_private_evaluation_approval_recorded": False,
            "private_evaluation_eligible": False,
        },
        "blockers": [
            "apple_runtime_resource_bounds_unmeasured",
            "checkpoint_local_hash_unverified",
            "conversion_parity_not_independently_verified",
            "explicit_private_evaluation_approval_missing",
            "runtime_dependency_lock_missing",
            "runtime_source_audit_missing",
            "runtime_worker_not_implemented",
            "safetensors_static_inspection_not_completed",
        ],
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "checkpoint_opened": False,
            "checkpoint_downloaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "product_route_changed": False,
        },
    }
    report["verification_sha256"] = _verification_sha256(report)
    return report


def _validate_private_melroformer_upstream_evidence(
    value: Mapping[str, Any],
) -> None:
    if set(value) != {
        "schema",
        "observed_at",
        "observation",
        "conversion_repository",
        "source_repository",
        "licensing",
        "secondary_lead_review",
        "lineage",
        "findings",
    }:
        raise ValueError("MelBand-RoFormer evidence fields differ")
    if value.get("schema") != UPSTREAM_EVIDENCE_SCHEMA:
        raise ValueError("MelBand-RoFormer evidence schema differs")
    if value.get("observed_at") != OBSERVED_AT:
        raise ValueError("MelBand-RoFormer observation date differs")
    _validate_observation(_mapping(value.get("observation"), "observation"))
    _validate_conversion_repository(
        _mapping(value.get("conversion_repository"), "conversion repository")
    )
    _validate_source_repository(
        _mapping(value.get("source_repository"), "source repository")
    )
    _validate_licensing(_mapping(value.get("licensing"), "licensing"))
    _validate_secondary_lead_review(
        _mapping(value.get("secondary_lead_review"), "secondary lead review")
    )
    _validate_lineage(_mapping(value.get("lineage"), "lineage"))
    _validate_findings(_mapping(value.get("findings"), "findings"))


def _validate_observation(value: Mapping[str, Any]) -> None:
    expected = {
        "official_primary_sources_only": True,
        "conversion_model_api_url": (
            "https://huggingface.co/api/models/"
            "mlx-community/mel-roformer-kim-vocal-2-mlx"
        ),
        "conversion_tree_api_url": (
            "https://huggingface.co/api/models/"
            "mlx-community/mel-roformer-kim-vocal-2-mlx/tree/"
            f"{CONVERSION_REVISION}?recursive=true&expand=true"
        ),
        "conversion_readme_url": _conversion_raw_url("README.md"),
        "conversion_license_url": _conversion_raw_url("LICENSE"),
        "conversion_config_url": _conversion_raw_url("config.json"),
        "source_model_api_url": (
            "https://huggingface.co/api/models/KimberleyJSN/melbandroformer"
        ),
        "source_tree_api_url": (
            "https://huggingface.co/api/models/KimberleyJSN/"
            f"melbandroformer/tree/{SOURCE_REVISION}?recursive=true&expand=true"
        ),
        "source_readme_url": (
            "https://huggingface.co/KimberleyJSN/melbandroformer/raw/"
            f"{SOURCE_REVISION}/README.md"
        ),
        "source_license_commit_url": (
            "https://huggingface.co/KimberleyJSN/melbandroformer/commit/"
            f"{SOURCE_REVISION}"
        ),
        "source_license_discussion_url": (
            "https://huggingface.co/KimberleyJSN/melbandroformer/discussions/2"
        ),
        "network_used_to_observe": True,
        "conversion_checkpoint_downloaded": False,
        "source_checkpoint_downloaded": False,
    }
    if dict(value) != expected:
        raise ValueError("MelBand-RoFormer observation differs")


def _validate_conversion_repository(value: Mapping[str, Any]) -> None:
    expected = {
        "id": CONVERSION_REPOSITORY,
        "revision": CONVERSION_REVISION,
        "last_modified": "2026-05-01T15:37:43.000Z",
        "public": True,
        "gated": False,
        "disabled": False,
        "license": "mit",
        "base_model": SOURCE_REPOSITORY,
        "files": value.get("files"),
    }
    if dict(value) != expected:
        raise ValueError("MelBand-RoFormer conversion repository differs")
    files = _mapping(value.get("files"), "conversion files")
    if files != {
        "README.md": {
            "bytes": 8_846,
            "git_oid": "567b788a8810cb348bcb18c6f31d72cf66cd507a",
            "sha256": (
                "2bcb814963a9f0057259ee7736dea03c1346586d4124eebd75673fef13b30f55"
            ),
        },
        "LICENSE": {
            "bytes": 1_500,
            "git_oid": "fe7d79957141c5a1c3e3840c9c1189b68145cde0",
            "sha256": (
                "1aa245b55067df5c63c847894e7040f76fa79ddde83e9e5ed8a5c29ef1865c14"
            ),
        },
        "config.json": {
            "bytes": 833,
            "git_oid": "4e7f9ed2cfcb2b3232166a5c803adf20d6816031",
            "sha256": (
                "3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58"
            ),
        },
        CONVERSION_CHECKPOINT: {
            "bytes": CONVERSION_CHECKPOINT_BYTES,
            "git_oid": "a7aee57f5a6b2f1f92fd5781651311a0cac4796b",
            "lfs_sha256": CONVERSION_CHECKPOINT_SHA256,
            "xet_hash": (
                "a0cf3a6749f1a3f5f225eb13c230f16ec94ef26855497cbe34ab9e0c9e03a81f"
            ),
        },
    }:
        raise ValueError("MelBand-RoFormer conversion files differ")


def _validate_source_repository(value: Mapping[str, Any]) -> None:
    expected = {
        "id": SOURCE_REPOSITORY,
        "revision": SOURCE_REVISION,
        "last_modified": "2026-04-22T12:30:27.000Z",
        "public": True,
        "gated": False,
        "disabled": False,
        "license": "mit",
        "files": value.get("files"),
        "independent_identity_corroboration": value.get(
            "independent_identity_corroboration"
        ),
    }
    if dict(value) != expected:
        raise ValueError("MelBand-RoFormer source repository differs")
    files = _mapping(value.get("files"), "source files")
    if files != {
        "README.md": {
            "bytes": 20,
            "git_oid": "acb132c8f50ba394d4f63c298904c290319877a2",
            "sha256": (
                "5c1b3fd193f37b9dcdd947a12e566189f1c9d2664f4e5e95548e6a4b9fc7adab"
            ),
        },
        SOURCE_CHECKPOINT: {
            "bytes": SOURCE_CHECKPOINT_BYTES,
            "git_oid": "e9269937826d8cedf1855096bc9c1d49298bb4f8",
            "lfs_sha256": SOURCE_CHECKPOINT_SHA256,
            "xet_hash": (
                "05f6ab10ff7f425b7713f992332ec8c5851395f9af68e3f28107ef17f73eea2a"
            ),
        },
    }:
        raise ValueError("MelBand-RoFormer source files differ")
    corroboration = value.get("independent_identity_corroboration")
    if corroboration != [
        {
            "repository": "KitsuneX07/Music_Source_Sepetration_Models",
            "revision": "b7b7daa869684790fb1704a050f737fefc77e469",
            "path": "vocal_models/Kim_MelBandRoformer.ckpt",
            "bytes": SOURCE_CHECKPOINT_BYTES,
            "lfs_sha256": SOURCE_CHECKPOINT_SHA256,
        },
        {
            "repository": "FunAudioLLM/Fun-CineForge",
            "revision": "b01378e640d426b08c1cccb12339bf0f449ddfa5",
            "path": SOURCE_CHECKPOINT,
            "bytes": SOURCE_CHECKPOINT_BYTES,
            "lfs_sha256": SOURCE_CHECKPOINT_SHA256,
        },
    ]:
        raise ValueError("MelBand-RoFormer identity corroboration differs")


def _validate_licensing(value: Mapping[str, Any]) -> None:
    if dict(value) != {
        "checkpoint_owner": "Kimberley Jensen",
        "owner_permission_comment_date": "2025-06-03T23:42:59.000Z",
        "owner_permission_comment_scope": "use it any way you like",
        "gpl_assignment_date": "2025-06-17T17:10:21.000Z",
        "gpl_revision": "f45f9e3d8570a406c94ac34b29f49ce43fda3bc8",
        "gpl_readme_sha256": (
            "0b6ea463a516d9c7b8a0bc5522e66765e18707a549e2c369daa487d88233550e"
        ),
        "mit_relicense_date": "2026-04-22T12:30:27.000Z",
        "mit_relicense_revision": SOURCE_REVISION,
        "mit_relicense_diff": {
            "path": "README.md",
            "from": "license: gpl-3.0",
            "to": "license: mit",
            "author": "KimberleyJSN",
        },
        "conversion_license": "MIT",
        "conversion_license_names_original_weights": True,
        "conversion_performed_after_mit_relicense": True,
    }:
        raise ValueError("MelBand-RoFormer licensing evidence differs")


def _validate_lineage(value: Mapping[str, Any]) -> None:
    if dict(value) != {
        "architecture": "Mel-Band-RoFormer",
        "checkpoint_family": "Kim Vocal 2",
        "target": "vocals",
        "derived_residual": "instrumental = mixture - vocals",
        "sample_rate": 44_100,
        "channels": 2,
        "chunk_frames": 352_800,
        "overlap": 2,
        "parameter_count_reported": 228_000_000,
        "conversion_tool_revision": "8380ab8",
        "mlx_version_reported": "0.31.0",
        "output_dtype": "bfloat16",
        "config_source_sha256_matches_source_repository": True,
        "parity_sdr_db_reported": 66.08,
        "parity_claim_independently_verified_by_sunofriend": False,
    }:
        raise ValueError("MelBand-RoFormer lineage evidence differs")


def _validate_secondary_lead_review(value: Mapping[str, Any]) -> None:
    if dict(value) != {
        "archive_sha256": (
            "8f0e06928eea399648e0b30df5e41f415b72b411aecf96a5e1f017c223d3924f"
        ),
        "archive_bytes": 8_405,
        "regular_files_reviewed": 5,
        "checkpoint_files_present": False,
        "download_helper_executed": False,
        "model_download_started": False,
        "admission_authority_inferred_from_pack": False,
        "viperx_alternatives": [
            {
                "filename": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
                "bytes": 639_331_213,
                "sha256": (
                    "5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa"
                ),
                "identity_independently_corroborated": True,
                "checkpoint_terms_authoritatively_verified": False,
                "admitted": False,
            },
            {
                "filename": "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
                "bytes": 1_007_816_988,
                "sha256": (
                    "21b9d0958e35b8ebfbe2afe69bbd5444e5ffe2f5d80ae0d583b833d2f3c0d139"
                ),
                "identity_independently_corroborated": True,
                "checkpoint_terms_authoritatively_verified": False,
                "admitted": False,
            },
        ],
    }:
        raise ValueError("MelBand-RoFormer secondary lead review differs")


def _validate_findings(value: Mapping[str, Any]) -> None:
    if dict(value) != {
        "checkpoint_specific_terms_verified": True,
        "checkpoint_allowed_use_verified_for_private_local_evaluation": True,
        "conversion_checkpoint_published_sha256": True,
        "source_checkpoint_published_sha256": True,
        "conversion_checkpoint_format": "safetensors",
        "conversion_checkpoint_pickle_deserialization_required": False,
        "conversion_checkpoint_local_identity_verified": False,
        "runtime_source_audited_by_sunofriend": False,
        "runtime_dependencies_locked_by_sunofriend": False,
        "apple_runtime_resource_bounds_measured_by_sunofriend": False,
        "private_evaluation_authorized": False,
        "private_evaluation_eligible": False,
    }:
        raise ValueError("MelBand-RoFormer findings differ")


def _conversion_raw_url(filename: str) -> str:
    return (
        "https://huggingface.co/mlx-community/"
        "mel-roformer-kim-vocal-2-mlx/raw/"
        f"{CONVERSION_REVISION}/{filename}"
    )


def _read_evidence_file(root_descriptor: int) -> bytes:
    attached = os.stat(UPSTREAM_EVIDENCE, dir_fd=root_descriptor, follow_symlinks=False)
    if not stat.S_ISREG(attached.st_mode) or stat.S_ISLNK(attached.st_mode):
        raise ValueError("MelBand-RoFormer evidence file is unsafe")
    if attached.st_size != UPSTREAM_EVIDENCE_BYTES:
        raise ValueError("MelBand-RoFormer evidence file size differs")
    if attached.st_size > _MAXIMUM_EVIDENCE_BYTES:
        raise ValueError("MelBand-RoFormer evidence exceeds audit bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(UPSTREAM_EVIDENCE, flags, dir_fd=root_descriptor)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(attached):
            raise ValueError("MelBand-RoFormer evidence file changed")
        contents = bytearray()
        digest = hashlib.sha256()
        while block := os.read(descriptor, 64 * 1024):
            contents.extend(block)
            digest.update(block)
            if len(contents) > UPSTREAM_EVIDENCE_BYTES:
                raise ValueError("MelBand-RoFormer evidence file grew")
        after = os.fstat(descriptor)
        rebound = os.stat(
            UPSTREAM_EVIDENCE,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if _identity(after) != _identity(opened) or _identity(rebound) != _identity(
            opened
        ):
            raise ValueError("MelBand-RoFormer evidence file changed")
    finally:
        os.close(descriptor)
    if len(contents) != UPSTREAM_EVIDENCE_BYTES:
        raise ValueError("MelBand-RoFormer evidence file size differs")
    if digest.hexdigest() != UPSTREAM_EVIDENCE_SHA256:
        raise ValueError("MelBand-RoFormer evidence file hash differs")
    return bytes(contents)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"MelBand-RoFormer {label} must be an object")
    return dict(value)


def _verification_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("verification_sha256", None)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
    )


__all__ = [
    "CONVERSION_CHECKPOINT_BYTES",
    "CONVERSION_CHECKPOINT_SHA256",
    "CONVERSION_REPOSITORY",
    "CONVERSION_REVISION",
    "SOURCE_CHECKPOINT_SHA256",
    "SOURCE_REPOSITORY",
    "SOURCE_REVISION",
    "UPSTREAM_EVIDENCE",
    "UPSTREAM_EVIDENCE_BYTES",
    "UPSTREAM_EVIDENCE_SHA256",
    "_report_from_verified_contents",
    "_validate_private_melroformer_upstream_evidence",
    "_verification_sha256",
    "_verify_private_melroformer_upstream_evidence",
]
