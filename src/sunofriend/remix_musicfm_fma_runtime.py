"""No-effects Windows runtime plan for the frozen MusicFM-FMA provider."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .remix_musicfm_fma import (
    MUSICFM_FMA_PROVIDER_ID,
    validate_musicfm_fma_admission_plan,
)
from .remix_musicfm_fma_evidence import (
    validate_musicfm_fma_readiness,
    validate_musicfm_fma_static_evidence,
)
from .source_receipt import document_sha256


MUSICFM_FMA_RUNTIME_PLAN_SCHEMA = "sunofriend.remix-musicfm-fma-runtime-plan.v0"

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_REVISION = "b83ebedb401bcef639b26b05c0c8bee1dc2dfe71"

_SOURCE_FILES = [
    {
        "path": "LICENSE",
        "git_blob_sha1": "9d8e4655469cb0acdae1e5ae01128c6499eaea09",
        "bytes": 12_888,
        "runtime_required": False,
        "purpose": "licence_evidence",
    },
    {
        "path": "model/__init__.py",
        "git_blob_sha1": "139597f9cb07c5d48bed18984ec4747f4b4f3438",
        "bytes": 2,
        "runtime_required": True,
        "purpose": "package_marker",
    },
    {
        "path": "model/musicfm_25hz.py",
        "git_blob_sha1": "e567c562c44e739beb42ebff9234303652670f75",
        "bytes": 8_605,
        "runtime_required": True,
        "purpose": "provider_entrypoint",
    },
    {
        "path": "modules/__init__.py",
        "git_blob_sha1": "139597f9cb07c5d48bed18984ec4747f4b4f3438",
        "bytes": 2,
        "runtime_required": True,
        "purpose": "package_marker",
    },
    {
        "path": "modules/conv.py",
        "git_blob_sha1": "9cc1a8f16cd103d09c86ace5b7c48b0583134e02",
        "bytes": 3_154,
        "runtime_required": True,
        "purpose": "convolution_frontend",
    },
    {
        "path": "modules/features.py",
        "git_blob_sha1": "c38f525e856eeefffeb2580c7bf61058ed228e0e",
        "bytes": 1_869,
        "runtime_required": True,
        "purpose": "mel_frontend",
    },
    {
        "path": "modules/random_quantizer.py",
        "git_blob_sha1": "1257014658a24e4557814ccbb746de455ec111fa",
        "bytes": 3_055,
        "runtime_required": True,
        "purpose": "checkpoint_architecture_member",
    },
]

_DIRECT_WHEELS = [
    {
        "package": "torch",
        "version": "2.7.1+cu128",
        "filename": "torch-2.7.1+cu128-cp311-cp311-win_amd64.whl",
        "bytes": 3_273_066_072,
        "sha256": "138c66dcd0ed2f07aafba3ed8b7958e2bed893694990e0b4b55b6b2b4a336aa6",
        "index": "https://download.pytorch.org/whl/cu128",
        "licence_metadata": "BSD-3-Clause",
    },
    {
        "package": "torchaudio",
        "version": "2.7.1+cu128",
        "filename": "torchaudio-2.7.1+cu128-cp311-cp311-win_amd64.whl",
        "bytes": 4_660_477,
        "sha256": "37a42de8c0f601dc0bc7dcccc4049644ef5adcf45920dd5813c339121e5b5a8c",
        "index": "https://download.pytorch.org/whl/cu128",
        "licence_metadata": "BSD-2-Clause",
    },
    {
        "package": "transformers",
        "version": "4.53.2",
        "filename": "transformers-4.53.2-py3-none-any.whl",
        "bytes": 10_826_609,
        "sha256": "db8f4819bb34f000029c73c3c557e7d06fc1b8e612ec142eecdae3947a9c78bf",
        "index": "https://pypi.org/simple",
        "licence_metadata": "Apache-2.0",
    },
    {
        "package": "einops",
        "version": "0.8.1",
        "filename": "einops-0.8.1-py3-none-any.whl",
        "bytes": 64_359,
        "sha256": "919387eb55330f5757c6bea9165c5ff5cfe63a642682ea788a6d472576d81737",
        "index": "https://pypi.org/simple",
        "licence_metadata": "MIT",
    },
]


def create_musicfm_fma_runtime_plan(
    admission_plan: Mapping[str, Any],
    static_evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
    *,
    repository_commit: str,
) -> dict[str, Any]:
    """Create a path-free runtime plan without fetching or installing packages."""

    checked_plan = validate_musicfm_fma_admission_plan(admission_plan)
    checked_evidence = validate_musicfm_fma_static_evidence(
        static_evidence, checked_plan
    )
    checked_readiness = validate_musicfm_fma_readiness(
        readiness, checked_plan, checked_evidence
    )
    if not _COMMIT.fullmatch(str(repository_commit)):
        raise ValueError("repository_commit must be a full 40-character Git commit")
    document = _runtime_values(
        checked_plan,
        checked_evidence,
        checked_readiness,
        repository_commit=str(repository_commit),
    )
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_fma_runtime_plan(
        document, checked_plan, checked_evidence, checked_readiness
    )


def validate_musicfm_fma_runtime_plan(
    runtime_plan: Mapping[str, Any],
    admission_plan: Mapping[str, Any],
    static_evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    checked_plan = validate_musicfm_fma_admission_plan(admission_plan)
    checked_evidence = validate_musicfm_fma_static_evidence(
        static_evidence, checked_plan
    )
    checked_readiness = validate_musicfm_fma_readiness(
        readiness, checked_plan, checked_evidence
    )
    document = dict(runtime_plan)
    if document.get("schema") != MUSICFM_FMA_RUNTIME_PLAN_SCHEMA:
        raise ValueError("unsupported MusicFM-FMA runtime plan schema")
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("MusicFM-FMA runtime plan document hash changed")
    repository_commit = document.get("repository_commit")
    if not _COMMIT.fullmatch(str(repository_commit)):
        raise ValueError("MusicFM-FMA runtime repository commit changed")
    expected = _runtime_values(
        checked_plan,
        checked_evidence,
        checked_readiness,
        repository_commit=str(repository_commit),
    )
    if unsigned != expected:
        raise ValueError("MusicFM-FMA runtime evidence or authority changed")
    return document


def _runtime_values(
    admission_plan: Mapping[str, Any],
    static_evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
    *,
    repository_commit: str,
) -> dict[str, Any]:
    direct_bytes = sum(row["bytes"] for row in _DIRECT_WHEELS)
    gates = {
        "static_model_artifact_evidence_complete": True,
        "upstream_source_revision_and_blob_roster_pinned": True,
        "direct_package_candidate_wheels_pinned": True,
        "source_files_materialized_and_sha256_verified": False,
        "complete_transitive_wheel_closure_resolved": False,
        "all_wheel_licences_reviewed": False,
        "isolated_runtime_created": False,
        "network_denied_import_gate_passed": False,
        "restricted_weights_only_load_passed": False,
        "synthetic_feature_canary_passed": False,
    }
    return {
        "schema": MUSICFM_FMA_RUNTIME_PLAN_SCHEMA,
        "status": "planned_dependency_closure_unresolved_no_install",
        "repository_commit": repository_commit,
        "binding": {
            "admission_plan_sha256": admission_plan["document_sha256"],
            "static_evidence_sha256": static_evidence["document_sha256"],
            "readiness_sha256": readiness["document_sha256"],
            "provider_id": MUSICFM_FMA_PROVIDER_ID,
        },
        "target_machine": {
            "operating_system": "Windows",
            "architecture": "win_amd64",
            "python_version": "3.11.16",
            "cuda_runtime": "12.8",
            "verified_gpu": "NVIDIA GeForce RTX 4080 Laptop GPU",
            "verified_gpu_memory_bytes": 12_878_086_144,
        },
        "isolation": {
            "dedicated_runtime_id": "musicfm-fma-windows-py311-cu128-v1",
            "reuse_existing_demucs_environment": False,
            "modify_existing_demucs_environment": False,
            "modify_system_python": False,
            "fresh_environment_required": True,
        },
        "source_snapshot": {
            "repository": "https://github.com/minzwon/musicfm",
            "revision": _SOURCE_REVISION,
            "upstream_requirements_lock_present": False,
            "files": list(_SOURCE_FILES),
            "materialized": False,
            "sha256_records_available": False,
        },
        "direct_wheel_candidates": {
            "items": list(_DIRECT_WHEELS),
            "observed_total_bytes": direct_bytes,
            "complete_transitive_closure": False,
            "installable_lock": False,
        },
        "required_adapter": {
            "upstream_from_pretrained_network_call_removed": True,
            "local_conformer_config_only": True,
            "torch_load_weights_only": True,
            "checkpoint_key_shape_dtype_allowlist": True,
            "is_flash": False,
            "network_during_import_load_and_inference": False,
            "model_eval_mode": True,
            "gradient_into_extractor": False,
            "layer_index": 7,
            "expected_feature_rate_hz": 25,
            "expected_feature_dimension": 1_024,
        },
        "gates": gates,
        "ready_for_dependency_download": False,
        "ready_for_installation": False,
        "ready_for_model_import": False,
        "ready_for_model_load": False,
        "ready_for_inference": False,
        "missing": [key for key, passed in gates.items() if not passed],
        "next_gate": {
            "kind": "resolve_hash_locked_transitive_wheel_closure",
            "public_metadata_only": True,
            "maximum_direct_candidate_bytes": direct_bytes,
            "maximum_total_closure_bytes": None,
            "downloads_wheels": False,
            "installs_packages": False,
            "imports_packages": False,
            "loads_model": False,
            "runs_inference": False,
            "opens_audio": False,
        },
        "authority": {
            "source_download_authorized": False,
            "wheel_download_authorized": False,
            "dependency_install_authorized": False,
            "model_import_authorized": False,
            "model_load_authorized": False,
            "synthetic_inference_authorized": False,
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "effects": {
            "source_downloaded": False,
            "wheel_downloaded": False,
            "dependency_installed": False,
            "model_imported": False,
            "model_loaded": False,
            "features_extracted": False,
            "training_started": False,
        },
    }


__all__ = [
    "MUSICFM_FMA_RUNTIME_PLAN_SCHEMA",
    "create_musicfm_fma_runtime_plan",
    "validate_musicfm_fma_runtime_plan",
]
