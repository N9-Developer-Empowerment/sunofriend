"""Runtime and restricted-load audit for the Banquet challenger.

This module records completed static, isolated-import and strict model-load
evidence. Building the document itself does not import a model dependency,
inspect audio, load a checkpoint or make the challenger executable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


QUERY_RUNTIME_AUDIT_SCHEMA = "sunofriend.other-refinement-query-runtime-audit.v1"


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


def build_query_runtime_audit() -> dict[str, Any]:
    """Return the immutable no-effects audit and next evidence gate."""

    audit: dict[str, Any] = {
        "schema": QUERY_RUNTIME_AUDIT_SCHEMA,
        "document_sha256": "",
        "status": "reference_objective_pass_human_listening_pending",
        "checked_on": "2026-08-08",
        "scope_id": "other-query-refinement-v1",
        "proposed_profile_id": "query-bandit-ev-pre-aug-v1",
        "registered": False,
        "executable": False,
        "source_audit": {
            "query_bandit": {
                "repository": "https://github.com/kwatcharasupat/query-bandit",
                "revision": "79ed5bb75e5c3a40cd319d9d990cee913fc65c26",
                "revision_date": "2025-07-29T13:52:38-07:00",
                "git_archive_sha256": (
                    "41cbf13408e2922e587a2367e6062adc3d0f9f439e4144d8707ff29d1fcbcb18"
                ),
                "license": "MIT",
                "dependency_lock_present": False,
                "packaging_metadata_present": False,
                "checkpoint_lightning_version_observed_statically": "2.1.3",
                "upstream_cli_approved_for_runtime": False,
            },
            "hear21passt": {
                "repository": "https://github.com/kkoutini/passt_hear21",
                "package": "hear21passt==0.0.26",
                "revision": "5f1cce6a54b88faf0abad82ed428355e7931213a",
                "revision_date": "2024-01-02T12:26:43+01:00",
                "git_archive_sha256": (
                    "a2adcca3dc8a9b903413cf39f211e134ba68def25bb3a01cc5227608888b1ca9"
                ),
                "wheel_sha256": (
                    "a3a7377604c6d829369111ab26a86fc5dd40154ec611b8fa5819ecaa6b252550"
                ),
                "package_metadata_license": "Apache-2.0",
                "automatic_download_loader_approved_for_runtime": False,
            },
            "passt_release": {
                "repository": "https://github.com/kkoutini/PaSST",
                "release_tag": "v0.0.5",
                "release_revision": "d7049e78e84ba38173ffd779479d1c9ec7d1c116",
                "release_revision_date": "2022-03-29T13:10:12+02:00",
                "release_license": "Apache-2.0",
                "license_sha256": (
                    "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
                ),
                "training_dataset": "OpenMIC-2018",
                "training_dataset_license": "CC-BY-4.0",
            },
        },
        "required_artifacts": {
            "banquet": {
                "file": "ev-pre-aug.ckpt",
                "bytes": 645_470_187,
                "sha256": (
                    "657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2"
                ),
                "license": "CC-BY-NC-SA-4.0",
                "evidence_complete": True,
                "loaded": True,
            },
            "passt_openmic": {
                "file": "openmic-passt-s-f128-10sec-p16-s10-ap.85.pt",
                "url": (
                    "https://github.com/kkoutini/PaSST/releases/download/v0.0.5/"
                    "openmic-passt-s-f128-10sec-p16-s10-ap.85.pt"
                ),
                "published_bytes": 341_546_630,
                "sha256": (
                    "dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da"
                ),
                "evidence_sha256": (
                    "990348267a373e2fe62c2fc87a13914411d7fe763b160568c87127a315f58362"
                ),
                "evidence_complete": True,
                "evidence_only_download_approved": True,
                "network_denied_static_inspection_complete": True,
                "loaded": True,
            },
        },
        "observed_upstream_hazards": [
            {
                "id": "unrestricted_lightning_checkpoint_load",
                "evidence": "train.py calls EndToEndLightningSystem.load_from_checkpoint",
                "disposition": "upstream CLI is forbidden",
            },
            {
                "id": "automatic_passt_network_resolution",
                "evidence": (
                    "Passt constructs get_basic_model(arch='openmic'), whose helper "
                    "downloads a release checkpoint"
                ),
                "disposition": "construct without pretrained download and load one explicit local file",
            },
            {
                "id": "unrestricted_passt_checkpoint_load",
                "evidence": "hear21passt loader calls torch.load without weights_only=True",
                "disposition": "upstream loader is forbidden",
            },
            {
                "id": "training_dependency_surface",
                "evidence": (
                    "train.py imports data, augmentation, metrics, pandas and Lightning "
                    "training modules at process start"
                ),
                "disposition": "use a minimal Sunofriend inference adapter",
            },
            {
                "id": "unlocked_upstream_runtime",
                "evidence": "query-bandit publishes no requirements or lock file",
                "disposition": "Sunofriend must create and hash every runtime artifact",
            },
        ],
        "restricted_loading_contract": {
            "use_upstream_train_cli": False,
            "use_lightning_load_from_checkpoint": False,
            "use_upstream_passt_download_helper": False,
            "use_unrestricted_torch_load": False,
            "banquet_loader": "torch.load(weights_only=True, map_location='cpu')",
            "passt_loader": "torch.load(weights_only=True, map_location='cpu')",
            "passt_construction": "pretrained=False with explicit local weights",
            "network_denied_for_import_construction_and_load": True,
            "explicit_local_cache_only": True,
            "state_dict_keys_shapes_and_dtypes_verified_before_strict_load": True,
            "no_audio_during_first_restricted_load": True,
            "dependency_artifacts_require_sha256": True,
            "runtime_environment_isolated": True,
        },
        "proposed_runtime_identity": {
            "platform": "macOS 11 or later, arm64",
            "python": "3.12",
            "approved_direct_requirements": {
                "torch": "2.2.2",
                "torchaudio": "2.2.2",
                "torchvision": "0.17.2",
                "hear21passt": "0.0.26",
                "timm": "0.9.12",
                "numpy": "1.26.4",
            },
            "excluded_from_inference_adapter": [
                "pytorch-lightning",
                "torchmetrics",
                "pandas",
                "torch-audiomentations",
                "omegaconf",
            ],
            "wheel_evidence": {
                "target": "CPython 3.12, macOS 11+, arm64",
                "package_count": 28,
                "wheel_bytes": 99_354_620,
                "approved_cap_bytes": 1_073_741_824,
                "peak_staged_bytes": 159_772_783,
                "static_evidence_sha256": (
                    "d5976d21a919648dbe6a371f1ce1f7d19adee75296f31739f4c662c040dd5329"
                ),
                "requirements_file": (
                    "separation-other-refinement-query-runtime-requirements.txt"
                ),
                "requirements_sha256": (
                    "28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92"
                ),
                "download_complete": True,
                "network_denied_non_importing_inspection_complete": True,
                "dependency_installed": False,
                "packages_imported": False,
                "license_disposition": (
                    "wheel metadata and licence-member hashes retained; no "
                    "contradiction found for local noncommercial research"
                ),
            },
            "model_artifact_hashes_complete": True,
            "runtime_dependency_hashes_complete": True,
            "installation_approved": True,
            "installation_complete": True,
            "apple_silicon_import_verified": True,
            "restricted_model_load_approved": True,
            "restricted_model_load_complete": True,
            "import_evidence": {
                "status": (
                    "isolated_hash_locked_runtime_imports_verified_network_denied"
                ),
                "target": "CPython 3.12.10, macOS arm64",
                "locked_package_count": 28,
                "bootstrap_package": "pip==25.0.1",
                "runtime_file_count": 21_493,
                "runtime_logical_file_bytes": 511_510_119,
                "imported_modules": [
                    "numpy",
                    "torch",
                    "torchaudio",
                    "torchvision",
                    "timm",
                    "hear21passt",
                    "hear21passt.models.passt",
                    "hear21passt.base",
                ],
                "import_report_sha256": (
                    "8f0b23e9943aa4e3f520f599479e575589102c07fa1c199424690cff0711768a"
                ),
                "import_report_file_sha256": (
                    "369c7f63b4cb93591d8060d76043ab9f3509e42b26c0c57cc1ca5f7bbf41657d"
                ),
                "approval_receipt_file_sha256": (
                    "ffd25870b284126925f9f8f1a46577882f7e35442bc45a68c2ade9f58c2ec39b"
                ),
                "network_denied": True,
                "network_attempts": 0,
                "checkpoint_open_attempts": 0,
                "torch_load_calls": 0,
                "audio_open_attempts": 0,
                "dependency_installed": True,
                "checkpoint_loaded": False,
                "model_constructed": False,
                "inference_runs": 0,
                "audio_reads": 0,
            },
            "model_load_evidence": {
                "status": (
                    "two_exact_models_constructed_and_strictly_loaded_network_denied"
                ),
                "target": "CPython 3.12.10, macOS arm64",
                "source_revision": (
                    "79ed5bb75e5c3a40cd319d9d990cee913fc65c26"
                ),
                "model_load_report_sha256": (
                    "12c028e88afdb94a22aa4344b75fb63a23386fd4f2292d9bf9aac0405b12dced"
                ),
                "model_load_report_file_sha256": (
                    "6707d71ac08abf884e050921d1ee5e6b973b9e33c87d2905eb1acf2120809843"
                ),
                "approval_receipt_file_sha256": (
                    "0dc27808000cd2a8afc6ff5a15aee8f31671c223e5ec84da8b16a172b5df4bdc"
                ),
                "banquet": {
                    "state_key_count": 1_069,
                    "total_numel": 111_234_333,
                    "inventory_sha256": (
                        "c562cc6f0b6807470d4d36ee4f6a048870e917afac9d7f92b2e35d7b9efec27f"
                    ),
                    "keys_equal": True,
                    "shapes_equal": True,
                    "dtypes_equal": True,
                    "strict_load_missing_keys": [],
                    "strict_load_unexpected_keys": [],
                },
                "passt": {
                    "state_key_count": 159,
                    "total_numel": 85_373_992,
                    "inventory_sha256": (
                        "ed94f5ea73d96f5965b1f67f11e84264f0afadd2efbbfad4d22783a4fc2aef96"
                    ),
                    "keys_equal": True,
                    "shapes_equal": True,
                    "dtypes_equal": True,
                    "strict_load_missing_keys": [],
                    "strict_load_unexpected_keys": [],
                },
                "torch_load_contract": (
                    "two calls using weights_only=True and map_location='cpu'"
                ),
                "network_denied": True,
                "network_attempts": 0,
                "audio_open_attempts": 0,
                "unapproved_checkpoint_open_attempts": 0,
                "checkpoint_loaded": True,
                "model_constructed": True,
                "inference_runs": 0,
                "audio_reads": 0,
                "audio_writes": 0,
            },
            "synthetic_forward_evidence": {
                "status": "objective_pass",
                "report_sha256": (
                    "bd5fa57716267488cfd9a0d1d69bc1627da6244d283fdaec5a5592234d51cec8"
                ),
                "report_file_sha256": (
                    "397293bb60d9bf658632cdb7526ece03ffb6007de5e1d86883d6cedb1408699a"
                ),
                "synthetic_plan_document_sha256": (
                    "0c2e83e0e55f40a8c38a6d103aae81a6443f1c935f5c1f08e35cdbb241426356"
                ),
                "attempts_authorized": 1,
                "attempts_consumed": 1,
                "inference_completions": 1,
                "elapsed_seconds": 2.853968958137557,
                "peak_resident_set_bytes": 2_052_014_080,
                "output_shape": [1, 2, 88_200],
                "output_dtype": "float32",
                "output_sample_rate_hz": 44_100,
                "all_output_samples_finite": True,
                "target_peak": 4.118360084248707e-05,
                "residual_peak": 0.15990281105041504,
                "maximum_reconstruction_error": 7.450580596923828e-09,
                "network_attempts": 0,
                "audio_open_attempts": 0,
                "unapproved_checkpoint_open_attempts": 0,
                "private_audio_processed": False,
                "audio_persisted": False,
                "musical_usefulness_established": False,
                "automatic_retry_authorized": False,
                "public_activation_authorized": False,
                "source_selection_authorized": False,
                "midi_authorized": False,
            },
            "reference_query_evidence": {
                "status": (
                    "objective_execution_complete_listening_pending_no_selection"
                ),
                "report_sha256": (
                    "fd15e3ba9524a49ebd182f86fa5c50ea0f5b02e95cc776ee5943a09147206ea8"
                ),
                "plan_document_sha256": (
                    "abfebe4f3eddfa3d891c8972edcbfd2dc62b968dc71e6c20dfb4311068059c76"
                ),
                "attempts_authorized": 9,
                "attempts_consumed": 9,
                "inference_completions": 9,
                "elapsed_seconds": 64.00747604202479,
                "peak_resident_set_bytes": 3_259_236_352,
                "private_pcm24_artifact_count": 36,
                "maximum_reconstruction_error_lsb": 0,
                "network_attempts": 0,
                "forbidden_audio_attempts": 0,
                "unapproved_checkpoint_attempts": 0,
                "all_six_source_hashes_unchanged": True,
                "musical_usefulness_established": False,
                "human_listening_pending": True,
                "automatic_retry_authorized": False,
                "public_activation_authorized": False,
                "source_selection_authorized": False,
                "midi_authorized": False,
            },
        },
        "next_gate": {
            "kind": "complete_private_reference_query_human_listen",
            "next_action": (
                "listen to all nine private guitar, keyboard and synth cases and "
                "record usefulness or limitations without selecting a source or "
                "starting MIDI"
            ),
            "plan_command": (
                "python3 scripts/plan-separation-other-refinement-query-reference.py"
            ),
            "plan_document_sha256": (
                "abfebe4f3eddfa3d891c8972edcbfd2dc62b968dc71e6c20dfb4311068059c76"
            ),
            "rights_category": "owned",
            "song_disjoint_inference_attempt_limit": 9,
            "dependency_artifact_download_approved": True,
            "dependency_artifact_download_complete": True,
            "dependency_installation": True,
            "package_import": True,
            "model_loading": True,
            "model_construction": True,
            "synthetic_inference_complete": True,
            "reference_inference_complete": True,
            "reference_audio_processing_complete": True,
            "human_listening_complete": False,
            "further_inference": False,
            "audio_processing": False,
            "public_activation": False,
            "source_or_midi_activation": False,
            "requires_separate_approval_before_further_inference_or_audio_processing": True,
        },
        "effects": {
            "network_used_by_plan": False,
            "artifact_downloaded_by_plan": False,
            "dependency_installed": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    audit["document_sha256"] = _document_sha256(audit)
    return audit


def validate_query_runtime_audit(value: dict[str, Any]) -> dict[str, Any]:
    """Reject mutation or accidental expansion of the reviewed authority."""

    expected = build_query_runtime_audit()
    if value != expected:
        raise ValueError("query runtime audit differs from the reviewed audit")
    if value["document_sha256"] != _document_sha256(value):
        raise ValueError("query runtime audit document hash differs")
    return value
