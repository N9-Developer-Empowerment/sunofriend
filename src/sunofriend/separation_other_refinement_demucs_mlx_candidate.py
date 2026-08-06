"""Read-only plan for the first grouped-other Studio challenger.

The plan pins an Apple-native six-source Demucs MLX runtime and its exact
artifacts.  Importing or printing this module downloads, installs, loads and
executes nothing.  Installation remains behind two explicit acceptance flags;
model construction, inference and private-audio processing remain later gates.
"""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from typing import Any, Mapping

from .separation_profiles import (
    OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
    separation_profile,
)


PLAN_SCHEMA = "sunofriend.other-refinement-demucs-mlx-candidate-plan.v1"
SETUP_PLAN_SCHEMA = "sunofriend.other-refinement-demucs-mlx-setup-plan.v1"
MODEL_REVISION = "d4519e24ddc2dd4a11d56a193092433d852c3961"
RUNTIME_SOURCE_REVISION = "b37e6ba3c5985af531f61c43564cf13c6ed349fd"
RUNTIME_RELEASE_TAG_REVISION = "36b43ce2fc908129fb9166d4c109f7ccb77d12bf"
RUNTIME_REQUIREMENTS_BYTES = 1_640
RUNTIME_REQUIREMENTS_SHA256 = (
    "11af62d2ce759e8e4937bd10046892c03dc8ba61bf8cb2537b6a53f4a257587c"
)
MODEL_SOURCE_ORDER = (
    "drums",
    "bass",
    "other",
    "vocals",
    "guitar",
    "piano",
)
EXPECTED_SEGMENT_TEXT = "39/5"
EXPECTED_SEGMENT = Fraction(39, 5)
DIRECT_ARTIFACT_DOWNLOAD_BYTES = 109_735_289
MAXIMUM_SETUP_DOWNLOAD_BYTES = 1_073_741_824


def normalize_pinned_six_source_config(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the pinned semantic identity and normalize only its fraction.

    This is the single allowed first remediation for the known demucs-mlx
    fractional-segment failure.  The caller receives a copy; the hash-pinned
    source document must never be edited in place or written back.
    """

    if set(document) != {
        "model_name",
        "model_class",
        "sub_model_class",
        "num_models",
        "weights",
        "args",
        "kwargs",
        "mlx_version",
        "tensor_count",
    }:
        raise ValueError("six-source config fields differ from the pinned contract")
    if document.get("model_name") != "htdemucs_6s":
        raise ValueError("six-source model name differs")
    if document.get("model_class") != "BagOfModelsMLX":
        raise ValueError("six-source model class differs")
    if document.get("sub_model_class") != "HTDemucsMLX":
        raise ValueError("six-source sub-model class differs")
    if document.get("num_models") != 1 or document.get("tensor_count") != 565:
        raise ValueError("six-source model or tensor count differs")
    if document.get("weights") != [[1.0] * 6] or document.get("args") != []:
        raise ValueError("six-source bag declaration differs")
    kwargs = document.get("kwargs")
    if not isinstance(kwargs, Mapping):
        raise ValueError("six-source model kwargs are missing")
    if tuple(kwargs.get("sources", ())) != MODEL_SOURCE_ORDER:
        raise ValueError("six-source role order differs")
    if kwargs.get("audio_channels") != 2 or kwargs.get("samplerate") != 44_100:
        raise ValueError("six-source clock contract differs")
    if kwargs.get("segment") != EXPECTED_SEGMENT_TEXT:
        raise ValueError("six-source segment text differs")
    if Fraction(str(kwargs["segment"])) != EXPECTED_SEGMENT:
        raise ValueError("six-source segment fraction differs")

    normalized = deepcopy(dict(document))
    normalized["kwargs"]["segment"] = float(EXPECTED_SEGMENT)
    return normalized


def demucs_mlx_other_refinement_candidate_plan() -> dict[str, Any]:
    """Return the deterministic, no-effect audit and approval record."""

    profile = separation_profile(OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID)
    return {
        "schema": PLAN_SCHEMA,
        "status": "approval_required_no_install_or_execution",
        "scope_id": "other-refinement-v1",
        "profile": profile.to_dict(),
        "selection": {
            "candidate_position": "first_studio_challenger",
            "selection_reason": (
                "Apple-silicon-native, PyTorch-free inference path with a pinned "
                "official six-source model conversion and an existing hash-locked runtime"
            ),
            "public_baseline_changed": False,
            "winner_selected": False,
        },
        "source": {
            "runtime_repository": "https://github.com/ssmall256/demucs-mlx",
            "runtime_source_revision": RUNTIME_SOURCE_REVISION,
            "runtime_release_tag": "v1.4.4",
            "runtime_release_tag_revision": RUNTIME_RELEASE_TAG_REVISION,
            "wheel_is_authoritative_executable_artifact": True,
            "model_repository": "https://huggingface.co/mlx-community/demucs-mlx",
            "model_revision": MODEL_REVISION,
            "original_model_repository": "https://github.com/facebookresearch/demucs",
            "original_model_release": "v4.0.1",
        },
        "checkpoint": {
            "name": "htdemucs_6s.safetensors",
            "bytes": 109_726_583,
            "sha256": (
                "d298f7f746bf53c21baad44fb08e88807ef47feb551dd22f1601a546c85b8e02"
            ),
            "safe_serialization": "safetensors",
            "model_card_declared_license": "MIT",
            "direct_original_checkpoint_conversion_declared": True,
            "separate_checkpoint_terms_file": None,
            "provisional_local_studio_use_evidence_sufficient": True,
        },
        "config": {
            "name": "htdemucs_6s_config.json",
            "bytes": 1_946,
            "sha256": (
                "97f8315891d8edc9aa6f59e56e0d352fbad5ebfb8a4faf46341ab2f1844596a9"
            ),
            "model_source_order": list(MODEL_SOURCE_ORDER),
            "sample_rate": 44_100,
            "channels": 2,
            "tensor_count": 565,
            "segment_source_value": EXPECTED_SEGMENT_TEXT,
            "segment_seconds_after_exact_normalization": float(EXPECTED_SEGMENT),
        },
        "target_mapping": {
            "guitar": {
                "model_role": "guitar",
                "canonical_role": "rhythm",
                "semantic_status": "direct_experimental_role",
            },
            "keys": {
                "model_role": "piano",
                "canonical_role": "keys",
                "semantic_status": "disclosed_piano_proxy_not_general_keys",
            },
            "one_target_per_run": True,
            "persist_only": ["requested_target", "other_residual"],
            "diagnostic_model_roles_must_match_exactly": list(MODEL_SOURCE_ORDER),
        },
        "known_runtime_failure_and_remediation": {
            "failure_id": "demucs-mlx-fractional-segment-runtime-v1",
            "same_string_representation_observed": True,
            "allowed_remediation": (
                "verify the immutable config, copy it in memory, replace only "
                "kwargs.segment with float(Fraction(39, 5)), and construct the model "
                "without writing a derived config or using named/network resolution"
            ),
            "pinned_config_mutation_permitted": False,
            "automatic_conversion_permitted": False,
            "maximum_remediation_cycles": 1,
            "compatibility_passed": True,
            "qualification_evidence": {
                "network_denied_synthetic_canary_passed": True,
                "authorised_full_song_duration_seconds": 234.0,
                "full_song_targets_passed": ["guitar", "keys"],
                "elapsed_seconds": [9.939911500085145, 9.215111209079623],
                "peak_unified_memory_bytes": [3_492_069_640, 3_492_069_624],
                "maximum_reconstruction_error_lsb": 0,
                "automatic_selection": False,
            },
        },
        "setup_plan": {
            "schema": SETUP_PLAN_SCHEMA,
            "plan_command": (
                "scripts/setup-separation-other-refinement-demucs-mlx-macos.sh --plan"
            ),
            "future_install_command": (
                "scripts/setup-separation-other-refinement-demucs-mlx-macos.sh "
                "--install --accept-model-terms --accept-checkpoint-use"
            ),
            "approval_flags_required": [
                "--accept-model-terms",
                "--accept-checkpoint-use",
            ],
            "runtime_lock": {
                "path": "separation-core-four-runtime-requirements.txt",
                "bytes": RUNTIME_REQUIREMENTS_BYTES,
                "sha256": RUNTIME_REQUIREMENTS_SHA256,
                "package_count": 9,
                "pip_require_hashes": True,
                "pytorch_free": True,
            },
            "download_budget": {
                "direct_pinned_artifact_bytes": DIRECT_ARTIFACT_DOWNLOAD_BYTES,
                "maximum_total_network_bytes": MAXIMUM_SETUP_DOWNLOAD_BYTES,
            },
            "post_install_inspection": {
                "network_denied": True,
                "hashes_and_bytes_verified": True,
                "config_semantics_verified": True,
                "model_constructed": False,
                "checkpoint_deserialized": False,
                "inference_runs": 0,
                "audio_reads": 0,
            },
            "status_after_install": (
                "installed_pending_fraction_normalized_loader_and_synthetic_canary"
            ),
        },
        "approval_requested": {
            "install_exact_hash_locked_dependencies": True,
            "download_exact_checkpoint_and_evidence_files": True,
            "retain_model_terms_evidence_locally": True,
            "run_network_denied_static_identity_and_config_inspection": True,
        },
        "approval_not_requested": {
            "construct_or_load_model": True,
            "run_inference": True,
            "read_or_process_private_audio": True,
            "publish_or_host_conversion": True,
            "activate_refined_sources_or_midi": True,
            "select_or_promote_model": True,
        },
        "objective_next_gates": [
            "collect human listening feedback without a minimum usefulness rating",
            "keep the parent and refined children mutually exclusive for activation",
            "require a later explicit musical choice before source activation or MIDI",
            "retain 16 GiB and other Apple-silicon classes as accessible but unverified",
        ],
        "subjective_policy": {
            "minimum_usefulness_rating": None,
            "mixed_or_negative_feedback_blocks_studio_access": False,
            "poor_feedback_action": (
                "publish a limitation and permit one bounded challenger experiment"
            ),
            "public_core_four_profile_affected": False,
        },
        "effects": {
            "network_used_by_plan": False,
            "files_written_by_plan": False,
            "dependencies_installed": False,
            "checkpoint_downloaded": False,
            "model_loaded": False,
            "model_executed": False,
            "audio_read": False,
            "audio_created": False,
            "source_graph_mutated": False,
            "midi_created": False,
            "candidate_selected": False,
            "profile_promoted": False,
        },
    }


__all__ = [
    "DIRECT_ARTIFACT_DOWNLOAD_BYTES",
    "EXPECTED_SEGMENT",
    "EXPECTED_SEGMENT_TEXT",
    "MAXIMUM_SETUP_DOWNLOAD_BYTES",
    "MODEL_SOURCE_ORDER",
    "PLAN_SCHEMA",
    "RUNTIME_REQUIREMENTS_BYTES",
    "RUNTIME_REQUIREMENTS_SHA256",
    "SETUP_PLAN_SCHEMA",
    "demucs_mlx_other_refinement_candidate_plan",
    "normalize_pinned_six_source_config",
]
