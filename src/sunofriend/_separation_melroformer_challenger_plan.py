"""Read-only plan for one exact private MLX MelBand-RoFormer challenger.

This candidate has stronger checkpoint identity and licence evidence than the
blocked broad BS-RoFormer release, but it is intentionally narrower: it
separates vocals and derives instrumental as the residual. Its private loader,
bounded adapter, isolated worker and downstream-MIDI evaluator exist; no
installer, downloader or product route is provided here.
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
from ._separation_melroformer_conversion_parity import (
    CONVERSION_TOOL_REVISION,
    EVIDENCE_NAME as CONVERSION_PARITY_EVIDENCE,
    EVIDENCE_SHA256 as CONVERSION_PARITY_EVIDENCE_SHA256,
    POLICY_ID as CONVERSION_PARITY_POLICY_ID,
    SCHEMA as CONVERSION_PARITY_SCHEMA,
)
from ._separation_melroformer_inference_parity import (
    EVIDENCE_NAME as INFERENCE_PARITY_EVIDENCE,
    EVIDENCE_SHA256 as INFERENCE_PARITY_EVIDENCE_SHA256,
    POLICY_ID as INFERENCE_PARITY_POLICY_ID,
    SCHEMA as INFERENCE_PARITY_SCHEMA,
)
from ._separation_melroformer_precision_review import (
    POLICY_ID as PRECISION_REVIEW_POLICY_ID,
    REVIEW_SCHEMA as PRECISION_REVIEW_SCHEMA,
)
from ._separation_macos_sandbox_probe import SCHEMA as SANDBOX_CANARY_SCHEMA
from ._separation_melroformer_pcm24_quarantine import (
    SCHEMA as PCM24_QUARANTINE_SCHEMA,
)
from ._separation_melroformer_worker_sandbox import (
    SCHEMA as SYNTHETIC_WORKER_SANDBOX_SCHEMA,
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


AUTHORISED_WORKER_SANDBOX_SCHEMA = (
    "sunofriend.private-melroformer-authorised-worker-sandbox.v1"
)


PLAN_SCHEMA = "sunofriend.private-melroformer-challenger-plan.v14"
POLICY_ID = "private-mlx-melroformer-kim-vocal-2-plan-v14"
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
    "complete_worker_import_closure_not_bound",
    "equal_level_human_listening_not_completed",
    "fp32_bf16_precision_listening_not_completed",
    "model_worker_hash_before_exec_path_toctou_not_closed",
    "outbound_model_attempt_observation_not_implemented",
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
        _inspect_companion_files(companion_root) if companion_root is not None else None
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
            "weight_conversion_parity": {
                "schema": CONVERSION_PARITY_SCHEMA,
                "policy_id": CONVERSION_PARITY_POLICY_ID,
                "observed_at": "2026-08-01",
                "status": "verified_exact_bf16_weight_conversion",
                "conversion_tool_revision": CONVERSION_TOOL_REVISION,
                "source_checkpoint_sha256": SOURCE_CHECKPOINT_SHA256,
                "converted_checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
                "source_state_dict_key_count": 684,
                "retained_source_key_count": 684,
                "converted_tensor_count": 708,
                "packed_qkv_split_count": 12,
                "tensor_payload_manifest_sha256": (
                    "ce0c29ffbe67266e5d42f143afad430a4dd107f6a8c086477dfdc300feede8ba"
                ),
                "report_document_sha256": (
                    "c5edf50929a73261d6d2cceb20163793f3d44f1c7e31c6a1f75b3b2ae1ed158e"
                ),
                "persisted_report_sha256": (CONVERSION_PARITY_EVIDENCE_SHA256),
                "tracked_evidence": CONVERSION_PARITY_EVIDENCE,
                "restricted_weights_only_load": True,
                "every_tensor_name_shape_and_bf16_payload_bit_exact": True,
                "inference_output_parity_independently_verified": False,
                "separator_quality_measured_by_this_gate": False,
                "product_route_changed": False,
            },
            "inference_output_parity": {
                "schema": INFERENCE_PARITY_SCHEMA,
                "policy_id": INFERENCE_PARITY_POLICY_ID,
                "observed_at": "2026-08-01",
                "status": (
                    "verified_bf16_runtime_parity_source_precision_delta_recorded"
                ),
                "authorised_track_id": "be-alone",
                "source_window_seconds": 8.0,
                "device": "cpu",
                "threshold_sdr_db": 40.0,
                "pytorch_bf16_roundtrip_vs_mlx_bf16_sdr_db": (117.70021782500807),
                "pytorch_original_fp32_vs_mlx_bf16_sdr_db": (29.141354808391004),
                "pytorch_original_fp32_vs_bf16_roundtrip_sdr_db": (29.141580379949556),
                "converted_bf16_runtime_output_parity_above_threshold": True,
                "original_fp32_source_to_converted_mlx_above_threshold": False,
                "upstream_reported_66_08_db_independently_reproduced": False,
                "same_audio_as_upstream_test": False,
                "report_document_sha256": (
                    "fd6b5d035ec579ffff1f3ee901d4b71b28f7816f2db50094a00c313cdeb29b93"
                ),
                "tracked_evidence": INFERENCE_PARITY_EVIDENCE,
                "persisted_report_sha256": INFERENCE_PARITY_EVIDENCE_SHA256,
                "separator_quality_measured_by_this_gate": False,
                "product_route_changed": False,
            },
            "precision_listening_review": {
                "schema": PRECISION_REVIEW_SCHEMA,
                "policy_id": PRECISION_REVIEW_POLICY_ID,
                "observed_at": "2026-08-01",
                "status": "prepared_unreviewed",
                "authorised_track_id": "be-alone",
                "source_seconds": [191.0, 199.0],
                "sample_rate": 44_100,
                "channels": 2,
                "frames": 352_800,
                "candidate_level_method": (
                    "pairwise-fixed-window-rms-attenuation-plus-common-peak-guard-v1"
                ),
                "candidate_a_rms_dbfs": -21.093168,
                "candidate_b_rms_dbfs": -21.093168,
                "final_pcm24_rms_mismatch_db": 0.0,
                "audio_manifest_sha256": (
                    "202b5e6d91478321b40f276e90ae25f2c7dc8449c1071a2d42d11462932c97d9"
                ),
                "answer_key_sha256": (
                    "298d5f174dc79223772f3e64ebfb3761c3a028230a7d57abc4a4419e52b6998f"
                ),
                "answer_key_embedded_in_html": False,
                "answer_key_opened_by_developer": False,
                "human_listening_complete": False,
                "winner_selected": False,
                "separator_enabled": False,
                "product_route_changed": False,
            },
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
            "installed_state_verified_in_this_call": False,
            "private_evaluation_environment_materialised_on_development_host": True,
            "installation_command": None,
            "installation_permitted": False,
            "network_denial_canary_schema": SANDBOX_CANARY_SCHEMA,
            "network_denial_canary_implemented": True,
            "network_denial_canary_passed_on_development_host": True,
            "network_denial_canary_latest_observation": {
                "observed_at": "2026-08-01",
                "evidence_sha256": (
                    "ff64dca9e59a8862b68202842ed1ede67e39bbcfb824bb97427620c23c658b86"
                ),
                "provider_sha256": (
                    "8857d087219f0f39d3e3c163e5d0a0aed690cc22f34b50c7eee3d74f93e69688"
                ),
                "runtime_sha256": (
                    "d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
                ),
                "control_errno": "ECONNREFUSED",
                "sandboxed_errno": "EPERM",
                "external_destination_contacted": False,
                "model_or_checkpoint_loaded": False,
            },
            "network_denial_bound_to_model_worker": True,
            "outbound_model_attempt_observation_implemented": False,
            "pcm24_quarantine_schema": PCM24_QUARANTINE_SCHEMA,
            "pcm24_quarantine_implemented": True,
            "pcm24_quarantine_synthetic_full_excerpt_passed": True,
            "pcm24_quarantine_deterministic_bytes_observed": True,
            "pcm24_quarantine_maximum_reconstruction_error_lsb": 2,
            "pcm24_quarantine_bound_to_worker": True,
            "pcm24_quarantine_outside_write_denial_proven": True,
            "synthetic_worker_sandbox_schema": SYNTHETIC_WORKER_SANDBOX_SCHEMA,
            "synthetic_worker_sandbox_implemented": True,
            "synthetic_worker_sandbox_passed_on_development_host": True,
            "synthetic_worker_sandbox_latest_observation": {
                "observed_at": "2026-08-01",
                "evidence_sha256": (
                    "8b1a91a95609d09175be6240af2a9d44f5bd8161249ebab01b9878e7cb406cb4"
                ),
                "network_denial_canary": "EPERM",
                "child_process_denial_canary": "EPERM",
                "outside_write_denial_canary": "EPERM",
                "child_and_parent_pcm24_evidence_identical": True,
                "model_or_checkpoint_loaded": False,
                "complete_python_import_closure_bound": False,
            },
            "synthetic_worker_implemented": True,
            "authorised_worker_sandbox_schema": AUTHORISED_WORKER_SANDBOX_SCHEMA,
            "authorised_worker_sandbox_implemented": True,
            "authorised_worker_sandbox_passed_on_development_host": True,
            "authorised_worker_sandbox_latest_observation": {
                "observed_at": "2026-08-01",
                "evidence_sha256": (
                    "53b6fd72797e127c4582d29e9c4454cf3c9afe247daf84279e92710abffb00e1"
                ),
                "persisted_observation_file_sha256": (
                    "bf331358c526773c9722169c691a6eaded1b6b1c2052bef4eed9192877cb38f0"
                ),
                "authorisation_report_sha256": (
                    "9f98d864601ef66ed9d7a06c5a95aeee1c0969b39c70a65078ef2da6f86d982d"
                ),
                "track_id": "i-am-a-alien-mashup",
                "network_denial_canary": "EPERM",
                "child_process_denial_canary": "EPERM",
                "outside_write_denial_canary": "EPERM",
                "child_and_parent_pcm24_evidence_identical": True,
                "pcm24_reconstruction_maximum_integer_error_lsb": 1,
                "vocal_pcm24_sha256": (
                    "6076f011db09f1b0ed781a718c95ea984762ee2d0be06872340d1c61ecbd7f83"
                ),
                "instrumental_pcm24_sha256": (
                    "31b9b1319f23680fdb90ccc5bef9b44aba4a82bddd63334c2fa2cd4c40271ef2"
                ),
                "observation_persisted_owner_only": True,
                "complete_python_import_closure_bound": False,
                "hash_before_exec_path_toctou_closed": False,
                "product_route_permitted": False,
            },
            "model_worker_implemented": True,
            "apple_resource_bounds_measured": True,
            "resource_measurement_host": "Apple silicon Mac with 36 GB RAM",
            "supported_private_devices": ["gpu", "cpu"],
            "default_private_device": "gpu",
            "device_selection_explicitly_pinned": True,
            "worker_protocol_schema": WORKER_PROTOCOL_SCHEMA,
            "worker_protocol_defined": True,
            "adapter_observation_schema": ADAPTER_OBSERVATION_SCHEMA,
            "synthetic_adapter_contract_defined": True,
            "real_bridge_probe_schema": (
                "sunofriend.private-melroformer-real-bridge-probe.v1"
            ),
            "real_model_bridge_probe_implemented": True,
            "real_adapter_implemented": True,
            "real_adapter_maximum_probe_seconds": 8.0,
            "full_excerpt_chunk_transport_implemented": True,
            "maximum_full_excerpt_seconds": 15.0,
            "nominal_chunk_seconds": 8.0,
            "nominal_hop_seconds": 4.0,
            "synthetic_real_model_smoke_passed": True,
            "synthetic_full_excerpt_smoke_passed": True,
            "full_excerpt_smoke_measurement": {
                "device": "gpu",
                "duration_seconds": 15.0,
                "chunk_count": 3,
                "inference_seconds": 2.573881250107661,
                "peak_memory_bytes": 2_419_165_306,
                "maximum_absolute_reconstruction_error": (7.450580596923828e-09),
                "filesystem_written": False,
            },
            "authorised_excerpt_smoke_passed": True,
            "numeric_repeatability_observation": {
                "gpu_authorised_excerpt_same_process": {
                    "duration_seconds": 15.0,
                    "byte_identical": False,
                    "differing_float32_samples": 597_663,
                    "maximum_absolute_float32_difference": (8.940696716308594e-08),
                    "root_mean_square_float32_difference": (4.4276054481828306e-09),
                    "pcm24_projection_differing_sample_fraction": (
                        0.011880574452003023
                    ),
                    "pcm24_projection_maximum_integer_difference": 1,
                },
                "cpu_full_excerpt_separate_processes": {
                    "duration_seconds": 15.0,
                    "byte_identical": True,
                    "differing_float32_samples": 0,
                    "maximum_absolute_float32_difference": 0.0,
                    "first_inference_seconds": 23.409394500078633,
                    "second_inference_seconds": 23.439723541028798,
                    "peak_memory_bytes": 3_581_510_326,
                },
                "interpretation": (
                    "GPU is faster but varied within one PCM24 least-significant bit; "
                    "CPU was bit-identical across two full 15-second synthetic processes"
                ),
            },
            "output_repeatability_policy": {
                "defined": True,
                "default_mode": "fast_gpu",
                "fast_gpu": {
                    "device": "gpu",
                    "cross_run_byte_identity_required": False,
                    "each_actual_artifact_must_be_hashed": True,
                    "additive_reconstruction_must_pass_per_run": True,
                    "observed_pcm24_variation_upper_bound_lsb": 1,
                    "observation_is_not_a_universal_model_guarantee": True,
                },
                "repeatable_cpu": {
                    "device": "cpu",
                    "cross_run_byte_identity_required": True,
                    "full_excerpt_repeat_observed": True,
                    "slower_than_fast_gpu": True,
                },
            },
            "worker_implemented": True,
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
            "latest_private_observation": {
                "observed_at": "2026-08-01",
                "status": "descriptive_controls_compared_no_winner",
                "track_id": "be-alone",
                "source_seconds": [191.0, 206.0],
                "authorisation_report_sha256": (
                    "00685db1ba4d5ac0927c25a5ef40792ab36c56cdb36dcc20cc5f926fb9774e90"
                ),
                "source_pcm24_sha256": (
                    "807fbfa4b37b2ad102d7bba6f973c4b9e2c6922908267a3e9465c525199e642e"
                ),
                "observed_vocal_float32_sha256_single_run": (
                    "f470918cf7bf4d1c62a3ba9717c292961543c8ff69fea7ca08146e2a48965ce7"
                ),
                "observed_instrumental_float32_sha256_single_run": (
                    "592e8e11d58ad45511b7bb6fd21b716b5b87b4578e75ff53e63cb6daf713d1af"
                ),
                "inference_seconds": 2.778583916835487,
                "device": "gpu",
                "peak_memory_bytes": 2_419_165_306,
                "chunk_count": 3,
                "maximum_absolute_reconstruction_error": (2.9802322387695312e-08),
                "audio_persisted": False,
                "quality_comparison_completed": True,
                "control_report_sha256": (
                    "4e83d7c80923ad0b148f6b1d75e2a121d6a3261ce6368f7babf44d2ece36b10c"
                ),
                "descriptive_similarity": {
                    "local-htdemucs": 0.973562363,
                    "moises": 0.994807696,
                    "suno-a": 0.926349629,
                    "suno-b": 0.921463681,
                },
                "controls_are_estimated_not_ground_truth": True,
                "winner_selected": False,
            },
            "cross_song_downstream_vocal_midi_complete": True,
            "downstream_vocal_midi_observations": [
                {
                    "observed_at": "2026-08-01",
                    "status": "complete_observation_not_acceptance",
                    "track_id": "be-alone",
                    "source_seconds": [191.0, 206.0],
                    "report_document_sha256": (
                        "e2ae906d872d55369d4dc658e63669b63e6a310f0498e0a000991db7facb3a0c"
                    ),
                    "worker_evidence_sha256": (
                        "ff086359cce141f906a090b5b5edbc21d102a909660b189399bc50a18ce457b0"
                    ),
                    "production_pipeline": "production_vocal_dominant_contour",
                    "tracker_mode": "pyin",
                    "phrase_repair": True,
                    "bpm": 136.0,
                    "tuning_hz": 440.0,
                    "note_count": 14,
                    "midi_sha256": (
                        "65111b1dadbc9daaa7ea015a542a256510bd1b8f3ecbb88a36f55dc63dd5dcc1"
                    ),
                    "exact_pitch_onset_f1_against_estimated_controls": {
                        "local-htdemucs": 0.518518519,
                        "moises": 0.6,
                        "suno-a": 0.56,
                        "suno-b": 0.461538462,
                    },
                    "controls_are_estimated_not_ground_truth": True,
                    "winner_selected": False,
                    "equal_level_blind_review_prepared": True,
                    "equal_level_blind_review_audio_manifest_sha256": (
                        "11a05fad5752c44025c018603ed4c21dd9003f7a201118ab0a716d95dadb794c"
                    ),
                    "equal_level_blind_review_complete": False,
                    "answer_key_opened_by_developer": False,
                },
                {
                    "observed_at": "2026-08-01",
                    "status": "complete_observation_not_acceptance",
                    "track_id": "i-am-a-alien-mashup",
                    "source_seconds": [219.0, 234.0],
                    "report_document_sha256": (
                        "36599d2b139320ea4d48a0805630ca5e7acf619746aec39fbfcd77cca7098f18"
                    ),
                    "worker_evidence_sha256": (
                        "53b6fd72797e127c4582d29e9c4454cf3c9afe247daf84279e92710abffb00e1"
                    ),
                    "production_pipeline": "production_vocal_dominant_contour",
                    "tracker_mode": "pyin",
                    "phrase_repair": True,
                    "bpm": 114.0,
                    "tuning_hz": 440.0,
                    "note_count": 23,
                    "midi_sha256": (
                        "776a07c43bdddbde585736e039f202ab8df13ed50d54750e6e83969aa39747e5"
                    ),
                    "exact_pitch_onset_f1_against_estimated_controls": {
                        "local-htdemucs": 0.888888889,
                        "moises": 0.913043478,
                        "suno-a": 0.844444444,
                        "suno-b": 0.772727273,
                    },
                    "controls_are_estimated_not_ground_truth": True,
                    "winner_selected": False,
                    "equal_level_blind_review_prepared": True,
                    "equal_level_blind_review_audio_manifest_sha256": (
                        "dab62596f47a13f05a10a96db1e06b8ab39c98b43899f5978b52ad32348655d8"
                    ),
                    "equal_level_blind_review_complete": False,
                    "answer_key_opened_by_developer": False,
                },
            ],
        },
        "decision": {
            "status": "blocked",
            "run_status": (
                "bf16_runtime_parity_verified_precision_and_midi_reviews_pending"
            ),
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
                "compare original-FP32 and published-BF16 vocal outputs in an equal-level blind review before deciding whether a larger FP32 MLX artifact is justified",
                "complete both prepared equal-level blind Kim-Vocal-2-versus-Moises MIDI listening reviews without opening either answer key",
                "resolve only the user-exported complete reviews and compare cross-song listening evidence before reconsidering any default",
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
            root / CONFIG_NAME,
            expected_bytes=CONFIG_BYTES,
            expected_sha256=CONFIG_SHA256,
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
        raise ValueError(
            "MelBand-RoFormer companion must be a single-link regular file"
        )
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
