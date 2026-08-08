"""No-effects runtime audit for the Banquet query challenger.

This module records what was learned from static source and checkpoint
inspection.  It deliberately does not import a model dependency, inspect a
private audio file, download an artifact or make the challenger executable.
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
        "status": "blocked_pending_hash_locked_runtime_plan",
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
                "loaded": False,
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
                "loaded": False,
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
            "state_dict_keys_and_tensor_shapes_verified_before_strict_load": True,
            "no_audio_during_first_restricted_load": True,
            "dependency_artifacts_require_sha256": True,
            "runtime_environment_isolated": True,
        },
        "proposed_runtime_identity": {
            "platform": "macOS 11 or later, arm64",
            "python": "3.12",
            "direct_candidates_not_yet_approved": {
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
            "model_artifact_hashes_complete": True,
            "runtime_dependency_hashes_complete": False,
            "installation_approved": False,
            "apple_silicon_import_verified": False,
        },
        "next_gate": {
            "kind": "review_hash_locked_runtime_plan",
            "next_action": (
                "prepare a fully hash-locked dependency and restricted-loading "
                "plan without installing or loading anything"
            ),
            "dependency_artifact_download_approved": False,
            "dependency_installation": False,
            "model_loading": False,
            "model_construction": False,
            "inference": False,
            "audio_processing": False,
            "public_activation": False,
            "source_or_midi_activation": False,
            "requires_separate_approval_before_download_or_install": True,
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
