"""No-effects plan and completed evidence for the synth-first challenger.

The document records research evidence and a bounded evaluation contract.  It
does not download an artifact, construct a model, read audio or make a profile
executable.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


NEXT_CHALLENGER_SCHEMA = "sunofriend.other-refinement-next-challenger.v1"


def _document_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_next_challenger_plan() -> dict[str, Any]:
    """Return the immutable synth-first research and evaluation plan."""

    plan: dict[str, Any] = {
        "schema": NEXT_CHALLENGER_SCHEMA,
        "document_sha256": "",
        "status": "model_load_verified_synthetic_inference_not_authorized",
        "checked_on": "2026-08-09",
        "scope_id": "other-synth-refinement-v1",
        "proposed_profile_id": "bs-roformer-mega-53-synth-v1",
        "release_tier": "studio_challenger",
        "registered": False,
        "executable": False,
        "priority": ["synth", "guitar", "wind"],
        "piano_policy": (
            "optional acoustic-piano control only; never a proxy for modern "
            "keyboard or synth separation"
        ),
        "prior_results": [
            {
                "profile_id": "demucs-mlx-htdemucs-6s-other-refinement-v1",
                "conclusion": "technically_valid_musically_unsuccessful",
                "useful_guitar_cases": 0,
                "successful_piano_cases": 0,
                "rerun_authorized": False,
            },
            {
                "profile_id": "query-bandit-ev-pre-aug-v1",
                "conclusion": "technically_valid_musically_unsuccessful",
                "not_useful_cases": 8,
                "partly_useful_cases": 1,
                "rerun_authorized": False,
            },
        ],
        "candidate": {
            "architecture": "Band-Split RoFormer",
            "checkpoint_release": (
                "https://github.com/ZFTurbo/Music-Source-Separation-Training/"
                "releases/tag/v1.0.21"
            ),
            "release_revision": "ea7eb9c20ea0e3f94368a30fc1654b51cdd55789",
            "published_roles": [
                "accordion", "acoustic-guitar", "back-vocal", "banjo", "bass",
                "bassoon", "bells", "bowed_strings", "brass", "cello",
                "clarinet", "congas", "digital-piano", "dobro", "double-bass",
                "drums", "electric-guitar", "flute", "french-horn",
                "glockenspiel", "guitar", "harmonica", "harp", "harpsichord",
                "hh", "keys", "kick", "lead-vocal", "mandolin", "marimba",
                "oboe", "organ", "percussion", "piano", "saxophone", "sitar",
                "snare", "strings", "synth", "tambourine", "timpani", "toms",
                "triangle", "trombone", "trumpet", "tuba", "ukulele", "viola",
                "violin", "vocal", "wind", "wind-chimes", "woodwind",
            ],
            "first_target": "synth",
            "later_targets_require_separate_evidence": ["guitar", "wind"],
            "upstream_limitations": [
                "at least 16 GB VRAM recommended upstream",
                "individual roles may trail specialised models",
                "the 53 native outputs can overlap and do not reconstruct the mix",
            ],
            "sunofriend_output_contract": {
                "persisted_roles": ["synth", "residual_other"],
                "residual_definition": "canonical_grouped_other - persisted_synth",
                "native_53_stem_sum_used_as_reconstruction_claim": False,
                "shared_attenuation_before_pcm24_if_required": True,
                "maximum_reconstruction_error_lsb": 2,
                "native_synth_correction_rms_and_peak_recorded": True,
            },
        },
        "runtime_source": {
            "repository": "https://github.com/openmirlab/bs-roformer-infer",
            "revision": "de35ada5817b878da0194ee2860253dda3a9c2b2",
            "revision_date": "2026-08-01T11:40:00+08:00",
            "git_archive_sha256": (
                "e64fe7733a45f5efc53091bbc2ab6dd04a0ee7373a639f1c9b27275502f26691"
            ),
            "source_license": "MIT",
            "source_version_string": "0.1.5",
            "released_wheel_contains_audited_mlx_revision": False,
            "pin_exact_source_revision": True,
            "file_hashes": {
                "LICENSE": "d5ca885481147d15e92e5e525ba1a024ad1e92df743a10874bcdf7494f7e26eb",
                "pyproject.toml": "7244eb4250e4a35573f54cbc7a6d6bb304dc794a2615a29b296c53efd175389e",
                "src/bs_roformer/config/checkpoints.toml": (
                    "ed63c020d57ab30c73fd16d51e78ec9e124e9eee3cd966d68ddb3b1c132e5ca5"
                ),
                "src/bs_roformer/backends/mlx_backend.py": (
                    "355ff36235503dadbfc17fc9bcec01703b09224c038fcb7c7b1a1270f9482954"
                ),
                "src/bs_roformer/mlx/convert.py": (
                    "83e92b88e4553e2b6f387d8e55c2e3810195983bc8415df8ed9effc2a339a8a5"
                ),
                "src/bs_roformer/utils.py": (
                    "c30906f036e95480b8ab43f028fcc32ceef25eb24a144bb21e23261729fa4195"
                ),
            },
            "backend": "mlx",
            "automatic_download_allowed": False,
            "download_missing": False,
            "network_denied": True,
            "upstream_unrestricted_torch_load_allowed": False,
            "required_loader": "torch.load(weights_only=True, map_location='cpu')",
            "strict_keys_shapes_dtypes_required": True,
        },
        "source_evidence": {
            "status": "exact_source_archive_verified_statically_not_imported",
            "source_revision": "de35ada5817b878da0194ee2860253dda3a9c2b2",
            "archive_bytes": 144_791,
            "archive_sha256": (
                "9b95036b8219eb5cd7be61a29868e6633dd42df0078eda55a0f3710123551c73"
            ),
            "source_evidence_sha256": (
                "982ce7c2e9355be9a79d701c8f505237ada7da6ebad41695b48b70dc8c6aad97"
            ),
            "file_count": 64,
            "logical_bytes": 522_358,
            "critical_file_hashes_match": True,
            "network_denied": True,
            "source_imported_during_inspection": False,
            "checkpoint_loaded_during_inspection": False,
        },
        "artifacts": {
            "checkpoint": {
                "file": "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt",
                "declared_bytes": 1_368_919_887,
                "declared_sha256": (
                    "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"
                ),
                "observed_bytes": 1_368_919_887,
                "observed_sha256": (
                    "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"
                ),
                "locally_verified": True,
                "download_authorized": False,
                "evidence_download_status": "complete_authority_consumed",
            },
            "config": {
                "file": "mvsep_mega_model_bs_roformer_53_stems.yaml",
                "declared_bytes": 4_184,
                "declared_sha256": (
                    "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"
                ),
                "observed_bytes": 4_184,
                "observed_sha256": (
                    "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"
                ),
                "locally_verified": True,
                "download_authorized": False,
                "evidence_download_status": "complete_authority_consumed",
            },
            "evidence_sha256": (
                "d855138176807a7ca8738bd660141eb2b142676e41ccf56014be64e53f012a24"
            ),
            "observed_total_bytes": 1_368_924_071,
            "terms_evidence": {
                "checkpoint_registry_value": "not-reviewed",
                "public_github_release": True,
                "source_code_license": "MIT",
                "checkpoint_terms_established": False,
                "provisional_local_noncommercial_use_acknowledged": True,
                "hosted_service_or_redistribution_allowed": False,
            },
        },
        "runtime_wheel_evidence": {
            "status": "complete_authority_consumed",
            "target": {
                "platform": "macosx_14_0_arm64",
                "minimum_macos": "14.0",
                "python": "3.12",
                "implementation": "cp",
                "abi": "cp312",
                "only_binary": True,
            },
            "approved_cap_bytes": 1_610_612_736,
            "peak_staged_bytes": 128_346_422,
            "package_count": 29,
            "wheel_bytes": 127_527_173,
            "evidence_sha256": (
                "d8488079a9c82961056e296fa1050e07f2d341602293b01ed3e5b1de32ae5327"
            ),
            "requirements_file": (
                "separation-other-refinement-next-runtime-requirements.txt"
            ),
            "requirements_sha256": (
                "284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b"
            ),
            "direct_requirements": {
                "beartype": "0.22.9",
                "einops": "0.8.2",
                "ml-collections": "1.1.0",
                "mlx": "0.31.2",
                "mlx-spectro": "0.7.0",
                "numpy": "1.26.4",
                "packaging": "26.3",
                "pyyaml": "6.0.3",
                "requests": "2.34.2",
                "rotary-embedding-torch": "0.8.9",
                "soundfile": "0.14.0",
                "torch": "2.2.2",
                "tqdm": "4.70.0",
            },
            "resolution_notes": [
                "MLX 0.31.2 requires a macOS 14-or-later arm64 wheel target",
                "rotary-embedding-torch 0.9.1 requires Torch 2.4 or later",
                "0.8.9 is the newest published rotary release compatible with Torch 2.2.2",
            ],
            "licence_evidence": {
                "all_29_wheels_accounted_for": True,
                "metadata_and_bundled_licence_file_hashes_recorded": True,
                "private_local_evaluation_contradiction_found": False,
                "binary_redistribution_review_required": True,
                "checkpoint_terms_covered": False,
                "legal_advice": False,
            },
            "dependency_installed": False,
            "package_imported": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
        },
        "runtime_import_evidence": {
            "status": "isolated_hash_locked_runtime_imports_verified_network_denied",
            "target": "CPython 3.12.10, macOS 14+ arm64",
            "locked_package_count": 29,
            "bootstrap_package": "pip==25.0.1",
            "runtime_file_count": 21_124,
            "runtime_logical_file_bytes": 620_247_886,
            "imported_modules": [
                "numpy",
                "torch",
                "mlx",
                "mlx_spectro",
                "soundfile",
                "ml_collections",
                "tqdm",
                "beartype",
                "rotary_embedding_torch",
                "einops",
                "yaml",
                "requests",
                "packaging",
            ],
            "import_report_sha256": (
                "60eefa4285f720cc81f795b126c32dbc9462f05d1398662702bd313f394202a9"
            ),
            "import_report_file_sha256": (
                "567068a414c5ebc0cdb7cd47564934c5ec8f6b13c70425dd736c02af43892ac7"
            ),
            "approval_receipt_file_sha256": (
                "1e4a7c3f661171b4e62cf0efae55971a71eb51e0b52cd9b29176214e160080ed"
            ),
            "network_denied": True,
            "python_network_attempts": 0,
            "socket_constructions": ["requests:socket.__new__"],
            "local_bind_attempts": ["requests:socket.bind:('::1', 0)"],
            "checkpoint_open_attempts": 0,
            "torch_load_calls": 0,
            "audio_open_attempts": 0,
            "dependency_installed": True,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "remediation": {
                "maximum_cycles": 1,
                "cycles_used": 1,
                "initial_issue": (
                    "the verifier classified requests' unconnected local IPv6 "
                    "capability probe as external network access"
                ),
                "resolution": (
                    "record socket construction and the ::1 bind separately; "
                    "continue to fail connection, DNS or non-loopback operations"
                ),
            },
        },
        "model_load_evidence": {
            "status": "exact_mlx_model_constructed_and_strictly_loaded_offline",
            "report_sha256": (
                "798b5250eacf18d3f6193fde9d5c613ee68520490aed663395313a47eea4d666"
            ),
            "report_file_sha256": (
                "597ee1e7f3b9f52ad318c66fb28811b7919abebe6ab44c6543a6642099f770f6"
            ),
            "approval_receipt_file_sha256": (
                "11f4855feeac22e6c62459f9dbe2429c94a84cbf5a0bd5b8a070c48e2fd5f4cc"
            ),
            "checkpoint_loads": 1,
            "checkpoint_key_count": 13_595,
            "checkpoint_total_numel": 681_663_596,
            "checkpoint_inventory_sha256": (
                "1855b41c7ff9cfe6a9d248a4fa1635b7abeb8be4044be7c19ecd9245fd725b10"
            ),
            "converted_parameter_key_count": 13_571,
            "converted_parameter_total_numel": 681_662_828,
            "converted_parameter_inventory_sha256": (
                "565a9430061391486c8686d80eb4b6b65fdfd402b4bdeb603ab4ef5cf8c41fd8"
            ),
            "skipped_nonparameter_rotary_buffers": 24,
            "skipped_nonparameter_rotary_numel": 768,
            "state_keys_equal": True,
            "state_shapes_equal": True,
            "state_dtypes_equal": True,
            "strict_load": True,
            "network_attempts": 0,
            "forward_calls": 0,
            "audio_open_attempts": 0,
            "inference_runs": 0,
            "architecture_remediation": {
                "maximum_cycles": 1,
                "cycles_used": 1,
                "checkpoint_derived_transformer_expansion": 4,
                "checkpoint_derived_mask_head_expansion": 2,
                "checkpoint_parameter_dtype": "float16",
                "verified_source_mutated": False,
            },
            "upstream_chunk_alignment": {
                "chunk_size": 882_000,
                "step_size": 441_000,
                "stft_hop_length": 512,
                "num_overlap": 2,
                "valid_for_inference": False,
                "silently_changed": False,
            },
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
        "evaluation": {
            "configuration_count": 1,
            "remediation_cycle_limit": 1,
            "first_target": "synth",
            "inference_attempt_limit": 4,
            "machine": "Apple M3 Max with 36 GB unified memory",
            "network_denied": True,
            "input": "canonical grouped-other PCM24, stereo, 44.1 kHz",
            "case_duration_seconds": 15.0,
            "cases": [
                {"track_id": "be-alone", "window_seconds": [201.0, 216.0]},
                {"track_id": "i-am-a-alien-mashup", "window_seconds": [210.0, 225.0]},
                {"track_id": "in-the-way", "window_seconds": [129.0, 144.0]},
                {
                    "track_id": "tell-me-that-i-do-it-bitch",
                    "window_seconds": [135.0, 150.0],
                },
            ],
            "provider_stems_are_ground_truth": False,
            "instrument_presence_review": {
                "required_before_model_usefulness_scoring": True,
                "valid_values": ["present", "absent", "cannot_tell"],
                "absent_or_cannot_tell_is_model_failure": False,
                "absent_or_cannot_tell_triggers_replacement_case": False,
                "reason": (
                    "a separator cannot be judged for missing a target that is not "
                    "audibly present in the evaluation window"
                ),
            },
            "usefulness_review": {
                "valid_values": ["useful", "partly_useful", "not_useful", "cannot_tell"],
                "minimum_rating_for_preview_admission": None,
                "poor_feedback_disables_public_core_four": False,
                "poor_feedback_triggers_unbounded_tuning": False,
                "automatic_model_selection": False,
                "automatic_source_activation": False,
                "automatic_midi": False,
            },
        },
        "gates": [
            "capped evidence-only checkpoint and config download with exact hash verification",
            "network-denied non-loading and weights-only static inspection",
            "fully hash-locked macOS-arm64 dependency closure",
            "isolated install and import verification",
            "strict weights-only construction and load",
            "one generated-tensor synthetic objective run",
            "one four-song synth canary with no automatic retry",
        ],
        "completed_gates": [
            "capped evidence-only checkpoint and config download with exact hash verification",
            "network-denied non-loading static pickle/config inspection",
            "fully hash-locked macOS-arm64 dependency closure",
            "isolated install and import verification",
            "exact source archive materialisation and network-denied static verification",
            "strict weights-only construction and load",
        ],
        "next_gate": {
            "kind": "one_generated_tensor_synthetic_objective_run",
            "plan_command": (
                ".venv/bin/python "
                "scripts/plan-separation-other-refinement-next-synthetic.py"
            ),
            "plan_status": (
                "awaiting_explicit_generated_tensor_forward_approval"
            ),
            "published_chunk_size": 882_000,
            "published_step_size": 441_000,
            "aligned_chunk_size": 881_664,
            "aligned_step_size": 440_832,
            "stft_hop_length": 512,
            "num_overlap": 2,
            "alignment_adjustment_samples": -336,
            "maximum_download_bytes": 0,
            "artifact_download": False,
            "runtime_wheel_download": False,
            "dependency_installation": False,
            "package_import": False,
            "checkpoint_loading": False,
            "model_construction": False,
            "inference": False,
            "requires_separate_approval": True,
            "audio_processing": False,
            "public_activation": False,
            "source_selection": False,
            "midi": False,
        },
        "effects": {
            "network_used_by_plan": False,
            "artifact_downloaded_by_plan": False,
            "dependency_installed_by_plan": False,
            "checkpoint_loaded_by_plan": False,
            "model_constructed_by_plan": False,
            "audio_read_by_plan": False,
            "audio_written_by_plan": False,
            "profile_registered_by_plan": False,
            "source_selected_by_plan": False,
            "midi_created_by_plan": False,
        },
    }
    plan["document_sha256"] = _document_sha256(plan)
    return plan


def validate_next_challenger_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Refuse changed identity, authority or evaluation semantics."""

    expected = build_next_challenger_plan()
    if plan != expected:
        raise ValueError("next challenger plan differs from the reviewed contract")
    if plan["candidate"]["first_target"] != "synth":
        raise ValueError("the first target must remain synth")
    if plan["artifacts"]["terms_evidence"]["checkpoint_terms_established"]:
        raise ValueError("checkpoint terms have not been established")
    if any(plan["effects"].values()):
        raise ValueError("the plan must remain no-effects")
    return copy.deepcopy(plan)
