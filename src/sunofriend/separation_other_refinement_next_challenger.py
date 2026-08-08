"""No-effects plan for the synth-first fine-stem challenger.

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
        "status": "artifact_evidence_verified_runtime_not_authorized",
        "checked_on": "2026-08-08",
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
        ],
        "next_gate": {
            "kind": "hash_locked_macos_arm64_dependency_closure_evidence",
            "maximum_download_bytes": None,
            "artifact_download": False,
            "runtime_wheel_download": False,
            "dependency_installation": False,
            "package_import": False,
            "checkpoint_loading": False,
            "model_construction": False,
            "inference": False,
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
