"""No-effects admission plan for the frozen MusicFM-FMA remix provider."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .source_receipt import document_sha256


MUSICFM_FMA_ADMISSION_PLAN_SCHEMA = "sunofriend.remix-musicfm-fma-admission-plan.v0"
MUSICFM_FMA_PROVIDER_ID = "musicfm-fma-25hz-layer7-v1"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")

_UPSTREAM_CODE_COMMIT = "b83ebedb401bcef639b26b05c0c8bee1dc2dfe71"
_MODEL_PUBLICATION_REVISION = "4513b38bc25ad1d227b1980819b9691ba97f4d87"
_CHECKPOINT_SHA256 = "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96"
_CHECKPOINT_BYTES = 1_316_802_154
_STATS_GIT_BLOB_SHA1 = "4b72fa21d6962f55ae9c95b3457e765eb19552e5"
_STATS_BYTES = 2_281


def create_musicfm_fma_admission_plan(
    *, plan_id: str, repository_commit: str
) -> dict[str, Any]:
    """Create an immutable plan without downloading, loading or running a model."""

    _safe_id(plan_id, "plan_id")
    _commit(repository_commit, "repository_commit")
    document = _expected_plan(
        plan_id=str(plan_id), repository_commit=str(repository_commit)
    )
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_fma_admission_plan(document)


def validate_musicfm_fma_admission_plan(
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the exact planned provider and its deliberately incomplete gates."""

    document = dict(plan)
    if document.get("schema") != MUSICFM_FMA_ADMISSION_PLAN_SCHEMA:
        raise ValueError("unsupported MusicFM-FMA admission plan schema")
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("MusicFM-FMA admission plan document hash changed")
    if set(document) != set(_expected_plan(plan_id="x", repository_commit="0" * 40)) | {
        "document_sha256"
    }:
        raise ValueError("MusicFM-FMA admission plan fields changed")
    plan_id = document.get("plan_id")
    repository_commit = document.get("repository_commit")
    _safe_id(plan_id, "plan_id")
    _commit(repository_commit, "repository_commit")
    expected = _expected_plan(
        plan_id=str(plan_id), repository_commit=str(repository_commit)
    )
    if unsigned != expected:
        raise ValueError("MusicFM-FMA admission plan evidence or authority changed")
    return document


def _expected_plan(*, plan_id: str, repository_commit: str) -> dict[str, Any]:
    gates = {
        "official_code_revision_pinned": True,
        "official_checkpoint_publication_revision_pinned": True,
        "checkpoint_size_and_lfs_sha256_recorded": True,
        "code_and_model_metadata_licence_recorded": True,
        "checkpoint_download_explicitly_authorized": False,
        "checkpoint_bytes_locally_verified": False,
        "statistics_sha256_locally_verified": False,
        "external_conformer_config_pinned": False,
        "hash_locked_runtime_available": False,
        "restricted_weights_only_load_passed": False,
        "network_denied_synthetic_feature_canary_passed": False,
        "authorised_audio_feature_extraction_approved": False,
    }
    return {
        "schema": MUSICFM_FMA_ADMISSION_PLAN_SCHEMA,
        "status": "planned_no_checkpoint_access",
        "plan_id": plan_id,
        "repository_commit": repository_commit,
        "provider": {
            "provider_id": MUSICFM_FMA_PROVIDER_ID,
            "family": "MusicFM",
            "variant": "FMA",
            "purpose": "frozen_remix_audio_feature_extractor_only",
            "extractor_frozen": True,
            "gradient_into_extractor": False,
            "generates_audio": False,
            "selects_remix": False,
        },
        "upstream": {
            "code": {
                "repository": "https://github.com/minzwon/musicfm",
                "revision": _UPSTREAM_CODE_COMMIT,
                "entrypoint": "model/musicfm_25hz.py:MusicFM25Hz",
                "licence_metadata": "MIT with one Apache-2.0 module",
            },
            "model_publication": {
                "repository": "https://huggingface.co/minzwon/MusicFM",
                "revision": _MODEL_PUBLICATION_REVISION,
                "licence_metadata": "mit",
                "training_corpus_declared_by_upstream": (
                    "FMA-large, approximately 8,000 hours of Creative "
                    "Commons-licensed audio"
                ),
                "legal_clearance_complete": False,
            },
        },
        "planned_assets": {
            "checkpoint": {
                "filename": "pretrained_fma.pt",
                "bytes": _CHECKPOINT_BYTES,
                "sha256": _CHECKPOINT_SHA256,
                "serialization": "pytorch_pickle_state_dict_wrapper",
                "present_locally": False,
                "opened": False,
            },
            "statistics": {
                "filename": "fma_stats.json",
                "bytes": _STATS_BYTES,
                "publication_git_blob_sha1": _STATS_GIT_BLOB_SHA1,
                "sha256": None,
                "present_locally": False,
                "opened": False,
            },
            "implicit_upstream_dependency": {
                "model_id": "facebook/wav2vec2-conformer-rope-large-960h-ft",
                "reason": "upstream constructor calls from_pretrained for configuration",
                "revision": None,
                "config_sha256": None,
                "automatic_fetch_allowed": False,
            },
        },
        "proposed_feature_contract": {
            "input_sample_rate_hz": 24_000,
            "input_channels": 1,
            "channel_policy": "explicit_deterministic_downmix_derivative",
            "source_audio_mutated": False,
            "feature_rate_hz": 25,
            "layer_index": 7,
            "feature_dimension": 1_024,
            "window_policy": "exact_anchor_window_maximum_30_seconds",
            "pooling": "mean_and_standard_deviation_over_exact_anchor_frames",
            "output_dtype": "float32",
            "transparent_operation_features_retained": True,
        },
        "required_runtime_controls": {
            "network_during_load_and_inference": False,
            "upstream_automatic_checkpoint_loader_allowed": False,
            "torch_load_weights_only_required": True,
            "checkpoint_key_shape_dtype_allowlist_required": True,
            "regular_files_no_symlinks_required": True,
            "finite_feature_values_required": True,
            "deterministic_repeat_required": True,
            "checkpoint_and_config_hash_revalidation_required": True,
        },
        "known_limitations": [
            "upstream reports weak pretrained key detection",
            "upstream downstream evaluation pipeline is not published",
            "licence metadata does not by itself clear every training-data risk",
            "upstream constructor can fetch an unpinned external configuration",
            "checkpoint is a pickle container and must not use unrestricted loading",
        ],
        "gates": gates,
        "missing": [key for key, passed in gates.items() if not passed],
        "next_gate": {
            "kind": "explicit_checkpoint_and_runtime_evidence_approval",
            "maximum_checkpoint_bytes": _CHECKPOINT_BYTES,
            "permits_installation": False,
            "permits_model_load": False,
            "permits_inference": False,
            "permits_private_audio_access": False,
        },
        "authority": {
            "download_authorized": False,
            "dependency_install_authorized": False,
            "model_load_authorized": False,
            "synthetic_inference_authorized": False,
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "privacy": {
            "paths_embedded": False,
            "audio_embedded": False,
            "private_notes_embedded": False,
            "network_accessed_only_for_public_metadata": True,
        },
        "effects": {
            "checkpoint_downloaded": False,
            "dependency_installed": False,
            "model_loaded": False,
            "audio_opened": False,
            "features_extracted": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }


def _safe_id(value: Any, label: str) -> None:
    if not _SAFE_ID.fullmatch(str(value)):
        raise ValueError(f"{label} must be a safe path-free identifier")


def _commit(value: Any, label: str) -> None:
    if not _COMMIT.fullmatch(str(value)):
        raise ValueError(f"{label} must be a full 40-character Git commit")


__all__ = [
    "MUSICFM_FMA_ADMISSION_PLAN_SCHEMA",
    "MUSICFM_FMA_PROVIDER_ID",
    "create_musicfm_fma_admission_plan",
    "validate_musicfm_fma_admission_plan",
]
