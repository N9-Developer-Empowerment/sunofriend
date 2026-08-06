"""Read-only evidence plan for the public opt-in SCNet-large profile."""

from __future__ import annotations

from typing import Any

from .separation_profiles import (
    SCNET_RELEASE_PROFILE_ID,
    separation_profile,
)


SCNET_CANDIDATE_PLAN_SCHEMA = "sunofriend.scnet-candidate-plan.v1"
SCNET_SETUP_PLAN_SCHEMA = "sunofriend.scnet-compatibility-setup-plan.v1"
SCNET_CURRENT_SOURCE_REVISION = "5d95bf96b19c3eede63248d171efeca8e3abb948"
SCNET_SOURCE_REVISION = "6236f8c559778dc271e1aea9baa3993ae655e905"
SCNET_RELEASE_TAG = "update"
SCNET_RELEASE_REVISION = "6236f8c559778dc271e1aea9baa3993ae655e905"
SCNET_RELEASE_ID = 176_435_283
SCNET_CHECKPOINT_DRIVE_ID = "1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t"
SCNET_CHECKPOINT_BYTES = 168_848_417
SCNET_CHECKPOINT_SHA256 = (
    "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
)
SCNET_CONFIG_DRIVE_ID = "1qxK7SZx6-Gsp1s3wCrj98X7--UcI4O3K"
SCNET_RUNTIME_WHEEL_BYTES = 95_981_536
SCNET_RUNTIME_REQUIREMENTS_BYTES = 1_236
SCNET_RUNTIME_REQUIREMENTS_SHA256 = (
    "692c8c5fb0606c70e60e559be60eac5ba1c439b652dc2df26174effd66acc508"
)
SCNET_ARTIFACT_DOWNLOAD_BYTES = 168_870_367
SCNET_TOTAL_DOWNLOAD_BYTES = 264_851_903
SCNET_REQUIRED_FREE_DISK_BYTES = 2_000_000_000
SCNET_CHECKPOINT_DOWNLOAD_CAP_BYTES = 1_073_741_824
SCNET_PARAMETER_COUNT = 42_181_232
SCNET_STATE_DICT_BYTES = 168_724_928
SCNET_ARCHITECTURE_PROBE_MAX_RSS_BYTES = 380_043_264


def scnet_candidate_plan() -> dict[str, Any]:
    """Return the exact no-write decision record; never resolve or load a model."""

    profile = separation_profile(SCNET_RELEASE_PROFILE_ID)
    return {
        "schema": SCNET_CANDIDATE_PLAN_SCHEMA,
        "status": "public_opt_in",
        "profile": profile.to_dict(),
        "installation_enabled": True,
        "compatibility_inspection_enabled": True,
        "synthetic_execution_enabled": True,
        "execution_enabled": True,
        "source": {
            "repository": "https://github.com/starrytong/SCNet",
            "revision": SCNET_SOURCE_REVISION,
            "selection_reason": "checkpoint publication release revision",
            "release_tag": SCNET_RELEASE_TAG,
            "release_revision": SCNET_RELEASE_REVISION,
            "release_id": SCNET_RELEASE_ID,
            "release_assets": [],
            "current_source_revision": SCNET_CURRENT_SOURCE_REVISION,
            "current_source_differs_from_selected_release_source": True,
        },
        "checkpoint": {
            "name": "SCNet-large.th",
            "google_drive_file_id": SCNET_CHECKPOINT_DRIVE_ID,
            "bytes": SCNET_CHECKPOINT_BYTES,
            "sha256": SCNET_CHECKPOINT_SHA256,
            "separate_terms_file": None,
            "official_readme_linked": True,
            "provisional_terms_evidence_accepted": True,
            "evidence_captured_on": "2026-08-06",
            "immutable_artifact_identity_complete": True,
        },
        "config": {
            "name": "config.yaml",
            "google_drive_file_id": SCNET_CONFIG_DRIVE_ID,
            "bytes": 1_080,
            "sha256": (
                "629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0"
            ),
            "roles": ["drums", "bass", "other", "vocals"],
            "sample_rate": 44_100,
            "channels": 2,
            "segment_seconds": 11,
        },
        "proposed_adapter": {
            "device": "cpu",
            "shifts": 1,
            "seed": 0,
            "overlap": 0.25,
            "batch_size": 1,
            "writer_count": 1,
            "canonical_input_only": "stereo 44.1 kHz PCM24",
            "network_denial": True,
            "checkpoint_local_only": True,
            "training_only_upstream_dependencies_removed": [
                "accelerate",
                "julius",
                "ml-collections",
                "soundfile",
                "torchaudio",
                "tqdm",
            ],
            "runtime_packages": dict(profile.packages()),
            "runtime_wheel_download_bytes": SCNET_RUNTIME_WHEEL_BYTES,
        },
        "architecture_probe": {
            "checkpoint_loaded": False,
            "audio_processed": False,
            "network_denied": True,
            "torch": "2.8.0",
            "parameter_count": SCNET_PARAMETER_COUNT,
            "uncompressed_state_dict_bytes": SCNET_STATE_DICT_BYTES,
            "maximum_resident_set_bytes": SCNET_ARCHITECTURE_PROBE_MAX_RSS_BYTES,
            "roles": ["drums", "bass", "other", "vocals"],
            "channels": 2,
            "source_revision": SCNET_SOURCE_REVISION,
        },
        "compatibility_setup_plan": {
            "schema": SCNET_SETUP_PLAN_SCHEMA,
            "status": "complete_after_one_transparent_remediation",
            "setup_script": "scripts/setup-separation-core-four-scnet-macos.sh",
            "plan_command": (
                "scripts/setup-separation-core-four-scnet-macos.sh --plan"
            ),
            "future_install_command": (
                "scripts/setup-separation-core-four-scnet-macos.sh --install "
                "--accept-model-terms --accept-checkpoint-use"
            ),
            "future_install_command_enabled": True,
            "platform": {
                "os": "macOS",
                "architecture": "arm64",
                "python": "3.13",
                "first_verified_machine": "Apple M3 Max with 36 GB unified memory",
                "verified_16_gib_benchmark": False,
                "other_apple_silicon_classes": "accessible_but_unverified",
            },
            "default_install_root": (
                "$HOME/.local/share/sunofriend/separation/"
                "scnet-large-musdb-release-v1"
            ),
            "network_destinations_during_approved_setup": [
                "drive.usercontent.google.com",
                "raw.githubusercontent.com",
                "pypi.org",
                "files.pythonhosted.org",
            ],
            "download_budget": {
                "artifact_bytes": SCNET_ARTIFACT_DOWNLOAD_BYTES,
                "runtime_wheel_bytes": SCNET_RUNTIME_WHEEL_BYTES,
                "exact_expected_total_bytes": SCNET_TOTAL_DOWNLOAD_BYTES,
                "checkpoint_hard_cap_bytes": SCNET_CHECKPOINT_DOWNLOAD_CAP_BYTES,
            },
            "disk": {
                "minimum_free_bytes_before_setup": SCNET_REQUIRED_FREE_DISK_BYTES,
                "fresh_install_root_required": True,
                "atomic_staging_required": True,
                "overwrite_existing_root": False,
            },
            "runtime_lock": {
                "path": "separation-core-four-scnet-runtime-requirements.txt",
                "bytes": SCNET_RUNTIME_REQUIREMENTS_BYTES,
                "sha256": SCNET_RUNTIME_REQUIREMENTS_SHA256,
                "package_count": len(profile.runtime_identity),
                "packages": dict(profile.packages()),
                "pip_require_hashes": True,
                "binary_wheels_only": True,
            },
            "ordered_stages": [
                {
                    "id": "preflight",
                    "effects": "read_only",
                    "requirements": [
                        "Darwin arm64",
                        "Python 3.13",
                        "at least 2000000000 free bytes",
                        "fresh target root",
                    ],
                },
                {
                    "id": "verified_staging",
                    "effects": "approved_network_and_fresh_staging_writes",
                    "requirements": [
                        "hard-cap the checkpoint transfer at 1073741824 bytes",
                        "verify every artifact byte count and SHA-256",
                        "never publish a partial or mismatched staging root",
                    ],
                },
                {
                    "id": "isolated_runtime",
                    "effects": "approved_fresh_venv_install",
                    "requirements": [
                        "install only the 12 hash-locked binary wheels",
                        "verify exact package receipt",
                        "retain no package capable of upstream model resolution",
                    ],
                },
                {
                    "id": "offline_weights_only_compatibility",
                    "effects": "approved_checkpoint_deserialization_without_inference",
                    "requirements": [
                        "deny network access",
                        "use torch.load(weights_only=True, map_location='cpu')",
                        "reject custom globals and executable pickle payloads",
                        "construct the release source with the pinned config",
                        "require exact four roles and strict state-dict keys/shapes",
                        "run no forward pass and read no audio",
                    ],
                },
                {
                    "id": "atomic_publication",
                    "effects": "approved_local_publish",
                    "requirements": [
                        "publish only after every prior gate passes",
                        "write an exact installation and compatibility receipt",
                        "leave release tier controlled by the immutable registry",
                    ],
                },
            ],
            "compatibility_acceptance": {
                "checkpoint_bytes_and_sha_match": True,
                "weights_only_loader_required": True,
                "custom_pickle_globals_allowed": False,
                "strict_state_dict_required": True,
                "expected_roles": ["drums", "bass", "other", "vocals"],
                "expected_sample_rate": 44_100,
                "expected_channels": 2,
                "forward_pass_allowed": False,
                "audio_reads_allowed": False,
                "inference_allowed": False,
            },
            "remediation_policy": {
                "baseline_configurations": 1,
                "maximum_remediation_cycles": 1,
                "allowed_remediation": (
                    "one transparent checkpoint wrapper or uniform key-prefix "
                    "normalization with no tensor, role or shape coercion"
                ),
                "strict_key_or_shape_failure_after_remediation": "stop_candidate",
                "automatic_backend_search": False,
            },
            "stop_ship_conditions": [
                "artifact byte or SHA-256 mismatch",
                "checkpoint transfer exceeds the hard cap",
                "weights-only loader requests a custom global",
                "unexpected checkpoint container or tensor mutation requirement",
                "missing or extra roles",
                "state-dict key or shape mismatch after the one remediation",
                "network access during compatibility inspection",
                "crash or OOM on the declared supported machine",
            ],
            "post_setup_status": "installed_pending_separate_activation_evidence",
        },
        "synthetic_canary": {
            "status": "objective_pass",
            "command": (
                ".venv/bin/python "
                "scripts/run-separation-core-four-scnet-synthetic.py "
                "--out FRESH --execute --confirm-synthetic"
            ),
            "duration_seconds": 60.0,
            "worker_elapsed_seconds": 69.96541137504391,
            "inference_seconds": 68.51223383308388,
            "peak_resident_set_bytes": 6_581_846_016,
            "maximum_peak_resident_set_bytes": 12 * 1024**3,
            "network_denied": True,
            "four_roles_persisted": True,
            "maximum_reconstruction_error_lsb": 0,
            "machine": "Apple M3 Max with 36 GB unified memory",
            "verified_16_gib_benchmark": False,
            "development_machine_repeat_runs": 3,
            "development_machine_worker_elapsed_seconds": [
                69.96541137504391,
                70.19936337508261,
                71.18379291682504,
            ],
            "development_machine_peak_resident_set_bytes": [
                6_581_846_016,
                6_719_586_304,
                6_588_547_072,
            ],
            "all_persisted_audio_hashes_identical": True,
            "subjective_quality_threshold": None,
            "catastrophic_listen_complete": True,
        },
        "full_song_canaries": {
            "status": "objective_pass",
            "song_disjoint_count": 3,
            "coverage": ["vocal_forward", "dense_electronic", "acoustic_mixed"],
            "catastrophic_listens_complete": True,
            "catastrophic_defects_reported": 0,
        },
        "blockers": list(profile.blockers),
        "effects": {
            "network": [],
            "downloads": [],
            "installs": [],
            "model_loads": [],
            "audio_reads": [],
            "writes": [],
        },
        "next_bounded_action": (
            "Collect scope/profile-bound usefulness feedback and review after "
            "30 days or 10 valid reports; do not disable the functioning preview "
            "or start an unlimited tuning loop in response to poor feedback."
        ),
    }


__all__ = [
    "SCNET_CANDIDATE_PLAN_SCHEMA",
    "SCNET_RELEASE_PROFILE_ID",
    "SCNET_CHECKPOINT_BYTES",
    "SCNET_CHECKPOINT_SHA256",
    "SCNET_SETUP_PLAN_SCHEMA",
    "scnet_candidate_plan",
]
