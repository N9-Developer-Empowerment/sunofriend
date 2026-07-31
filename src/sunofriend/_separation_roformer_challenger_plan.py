"""Read-only registration plan for one exact private BS-RoFormer challenger.

This module deliberately has no installer, downloader, model import or worker.
It records the strongest exact public identity available for one official
release and fails closed on the evidence that the release does not publish.
The plan is private-development evidence only and cannot activate a separator.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any


PLAN_SCHEMA = "sunofriend.private-roformer-challenger-plan.v1"
POLICY_ID = "private-bs-roformer-musdb18hq-v1.0.12-plan-v1"
AUDITED_AT = "2026-07-31"

REPOSITORY = "https://github.com/ZFTurbo/Music-Source-Separation-Training"
RELEASE_TAG = "v1.0.12"
RELEASE_URL = f"{REPOSITORY}/releases/tag/{RELEASE_TAG}"
RELEASE_REVISION = "aef04b2e52fb3beaf25e333199f5a7236e628e7b"
LICENSE_ADDED_REVISION = "6149a2254758c546ab39235497a9beb9256c7833"
LICENSE_SHA256_AT_RELEASE = (
    "3282dc057695ef5b9a64909a7092ca40b2c292c232580fc6ace6e5d665cc0207"
)

CONFIG_ASSET_ID = 209603348
CONFIG_NAME = "config_bs_roformer_384_8_2_485100.yaml"
CONFIG_BYTES = 4_566
CONFIG_SHA256 = "d8afb980318d0c08b9c2e24a7adc00d4f3150320c127a7e4de861800d1321939"
CONFIG_URL = f"{REPOSITORY}/releases/download/{RELEASE_TAG}/{CONFIG_NAME}"

CHECKPOINT_ASSET_ID = 209597731
CHECKPOINT_NAME = "model_bs_roformer_ep_17_sdr_9.6568.ckpt"
CHECKPOINT_BYTES = 527_385_512
CHECKPOINT_URL = f"{REPOSITORY}/releases/download/{RELEASE_TAG}/{CHECKPOINT_NAME}"

RUNTIME_DEPENDENCY_INPUT = "requirements-private-separation-roformer-macos.in"
RUNTIME_DEPENDENCY_INPUT_SHA256 = (
    "3dd80522744c40ef2eca66a0109a76e5a117a266851805b59f7bdbb0399c7cee"
)
RUNTIME_DEPENDENCY_LOCK = "requirements-private-separation-roformer-macos.txt"
RUNTIME_DEPENDENCY_LOCK_SHA256 = (
    "7b8ade3828d75cca47cacc447dfa90e733c9425eccd0e341d5a6ba220a81ba65"
)
RUNTIME_LICENSE_AUDIT = "requirements-private-separation-roformer-macos.licenses.json"
RUNTIME_LICENSE_AUDIT_SHA256 = (
    "ecc5b6a012e5c8e1c97dba0426b6f0f172e17b765c94382e14477f005766e4d8"
)

_BLOCKERS = (
    "apple_runtime_resource_bounds_unmeasured",
    "checkpoint_allowed_use_unverified",
    "checkpoint_sha256_unpublished",
    "checkpoint_static_inspection_not_completed",
    "checkpoint_terms_unverified",
    "explicit_private_evaluation_approval_missing",
    "runtime_worker_not_implemented",
)


def _build_private_roformer_challenger_plan(
    *, checkpoint_path: str | Path | None = None
) -> dict[str, Any]:
    """Return one deterministic, read-only plan without network or imports."""

    local_checkpoint = (
        _inspect_local_checkpoint(checkpoint_path)
        if checkpoint_path is not None
        else {
            "provided": False,
            "path": None,
            "bytes": None,
            "sha256": None,
            "release_size_match": False,
            "cryptographic_identity_verified": False,
        }
    )
    return {
        "schema": PLAN_SCHEMA,
        "status": "blocked",
        "policy_id": POLICY_ID,
        "audit_date": AUDITED_AT,
        "read_only": True,
        "candidate": {
            "candidate_id": "zfturbo-bs-roformer-musdb18hq-v1.0.12",
            "architecture": "BS-RoFormer",
            "purpose": "independent four-stem quality challenger",
            "training_dataset_reported_by_release": "MUSDB18HQ",
            "roles": ["drums", "bass", "other", "vocals"],
            "sample_rate": 44_100,
            "channels": 2,
            "chunk_frames": 485_100,
            "chunk_seconds": 11.0,
            "checkpoint_filename_reported_sdr_db": 9.6568,
            "quality_claim_accepted_by_sunofriend": False,
            "automatic_selection": False,
            "automatic_promotion": False,
        },
        "source": {
            "repository": REPOSITORY,
            "release_tag": RELEASE_TAG,
            "release_url": RELEASE_URL,
            "release_revision": RELEASE_REVISION,
            "inference_entrypoint": "inference.py",
            "model_type": "bs_roformer",
            "code_license": "MIT",
            "license_added_revision": LICENSE_ADDED_REVISION,
            "license_sha256_at_release": LICENSE_SHA256_AT_RELEASE,
            "code_identity_pinned": True,
        },
        "config": {
            "release_asset_id": CONFIG_ASSET_ID,
            "name": CONFIG_NAME,
            "url": CONFIG_URL,
            "bytes": CONFIG_BYTES,
            "sha256": CONFIG_SHA256,
            "identity_pinned": True,
            "flash_attention_requested": True,
            "apple_mps_compatibility_verified": False,
        },
        "checkpoint": {
            "release_asset_id": CHECKPOINT_ASSET_ID,
            "name": CHECKPOINT_NAME,
            "url": CHECKPOINT_URL,
            "published_bytes": CHECKPOINT_BYTES,
            "published_sha256": None,
            "published_checkpoint_terms": None,
            "repository_code_license_projected_onto_checkpoint": False,
            "release_asset_acquisition_status": (
                "local_unverified_file_present"
                if local_checkpoint["provided"]
                else "not_present"
            ),
            "download_permitted": False,
            "deserialization_permitted": False,
            "redistribution_allowed_by_sunofriend": False,
            "local_observation": local_checkpoint,
        },
        "runtime": {
            "environment": "fresh .venv-roformer-private after separate approval",
            "existing_ai_environment_may_be_modified": False,
            "source_revision_pinned": True,
            "dependency_requirements_sha256_at_release": (
                "cd957de7a9f89c85488560ddd1f8c233602212f75728bdccc50ffd67806050fc"
            ),
            "upstream_broad_requirements_used_for_install": False,
            "adapter_boundary": (
                "exact attend.py and bs_roformer.py modules loaded through "
                "an isolated synthetic package plus a future bounded "
                "Sunofriend PCM-WAV inference adapter"
            ),
            "upstream_package_initializer_executed": False,
            "canonical_pcm_wav_io": "Python standard library",
            "excluded_dependency_groups": [
                "training",
                "GUI",
                "experiment tracking",
                "other separator architectures",
                "optional validation metrics",
                "upstream broad inference utility",
                "unrelated MelBand package initializer and librosa tree",
                "SoundFile and bundled media libraries",
            ],
            "dependency_input": {
                "path": RUNTIME_DEPENDENCY_INPUT,
                "sha256": RUNTIME_DEPENDENCY_INPUT_SHA256,
                "direct_packages": 6,
            },
            "dependency_lock": {
                "path": RUNTIME_DEPENDENCY_LOCK,
                "sha256": RUNTIME_DEPENDENCY_LOCK_SHA256,
                "resolved_packages": 15,
                "versions_fully_pinned": True,
                "distribution_hashes_required": True,
                "binary_distributions_only": True,
                "resolver": "uv",
                "resolution_python": "CPython 3.12.10",
                "resolution_platform": "this Darwin arm64 Mac",
                "minimum_macos_observed_for_torch_wheel": "14.0",
                "dry_run_resolved": True,
                "installed": False,
            },
            "dependency_license_audit": {
                "path": RUNTIME_LICENSE_AUDIT,
                "sha256": RUNTIME_LICENSE_AUDIT_SHA256,
                "all_locked_packages_accounted_for": True,
                "private_local_evaluation_compatible": True,
                "redistribution_review_required": True,
                "checkpoint_terms_covered": False,
            },
            "dependency_licenses_verified_for_private_local_evaluation": True,
            "installation_command": None,
            "installation_permitted": False,
            "network_destinations_if_later_approved": [
                "github.com",
                "objects.githubusercontent.com or GitHub's selected release CDN",
                "pypi.org",
                "files.pythonhosted.org or PyPI's selected CDN",
            ],
            "apple_device_path_reported_by_source": "mps",
            "apple_device_path_verified_for_candidate": False,
        },
        "evaluation_contract": {
            "control": "pinned local PyTorch HTDemucs",
            "first_authorised_evidence": (
                "the existing sealed 15-second private excerpts"
            ),
            "required_roles": ["drums", "bass", "other", "vocals"],
            "primary_quality_gates": [
                "improve composite other without harming drum onset timing",
                "improve downstream MIDI rather than isolated-stem SDR only",
                "preserve source-clock alignment and additive accounting",
                "produce no automatic winner, selection or public result",
            ],
            "vocal_gate": (
                "evaluate audio quality independently of the current zero-note "
                "dominant-contour result"
            ),
            "maximum_initial_excerpt_seconds": 15.0,
            "maximum_initial_cases": 2,
        },
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "candidate_registered": True,
            "checkpoint_identity_pinned": False,
            "private_evaluation_eligible": False,
            "worker_start_permitted": False,
            "blockers": list(_BLOCKERS),
            "next_safe_actions": [
                "obtain checkpoint-specific terms or an explicit upstream clarification",
                "obtain and independently verify a published checkpoint SHA-256",
                "define static checkpoint inspection and bounded worker contracts",
                "request separate approval only after every preceding blocker closes",
            ],
        },
        "effects": {
            "filesystem_written": False,
            "local_checkpoint_opened": local_checkpoint["provided"],
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


def _inspect_local_checkpoint(value: str | Path) -> dict[str, Any]:
    path = Path(value).expanduser().absolute()
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("RoFormer checkpoint must be a non-symlink regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("RoFormer checkpoint must remain a regular file")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("RoFormer checkpoint changed before inspection")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after:
        raise ValueError("RoFormer checkpoint changed during inspection")
    return {
        "provided": True,
        "path": str(path),
        "bytes": opened.st_size,
        "sha256": digest.hexdigest(),
        "release_size_match": opened.st_size == CHECKPOINT_BYTES,
        "cryptographic_identity_verified": False,
    }
