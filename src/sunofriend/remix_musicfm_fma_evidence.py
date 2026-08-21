"""Static, non-loading evidence for the exact MusicFM-FMA provider assets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .remix_musicfm_fma import (
    MUSICFM_FMA_PROVIDER_ID,
    validate_musicfm_fma_admission_plan,
)
from .separation_other_refinement_next_challenger_evidence import (
    _inspect_checkpoint,
)
from .source_receipt import document_sha256


MUSICFM_FMA_EVIDENCE_SCHEMA = "sunofriend.remix-musicfm-fma-static-evidence.v0"

CHECKPOINT_FILE = "pretrained_fma.pt"
CHECKPOINT_BYTES = 1_316_802_154
CHECKPOINT_SHA256 = "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96"
STATS_FILE = "fma_stats.json"
STATS_BYTES = 2_281
CONFIG_FILE = "wav2vec2-conformer-config.json"
CONFIG_BYTES = 2_239
MODEL_PUBLICATION_REVISION = "4513b38bc25ad1d227b1980819b9691ba97f4d87"
CONFIG_PUBLICATION_REVISION = "6b36ef01c6443c67ae7ed0822876d091ab50e4aa"
MAX_TOTAL_BYTES = 1_317_000_000
MAX_JSON_BYTES = 64 * 1024


def inspect_musicfm_fma_static_evidence(
    plan: Mapping[str, Any],
    *,
    checkpoint_path: str | Path,
    statistics_path: str | Path,
    conformer_config_path: str | Path,
) -> dict[str, Any]:
    """Hash and inspect approved files without deserialising the checkpoint."""

    checked_plan = validate_musicfm_fma_admission_plan(plan)
    checkpoint, archive, pickle = _inspect_checkpoint(
        Path(checkpoint_path),
        expected_bytes=CHECKPOINT_BYTES,
        expected_sha256=CHECKPOINT_SHA256,
        artifact_file=CHECKPOINT_FILE,
        maximum_bytes=MAX_TOTAL_BYTES,
    )
    statistics, statistics_structure = _inspect_json(
        Path(statistics_path),
        expected_file=STATS_FILE,
        expected_bytes=STATS_BYTES,
    )
    conformer_config, config_structure = _inspect_json(
        Path(conformer_config_path),
        expected_file=CONFIG_FILE,
        expected_bytes=CONFIG_BYTES,
    )
    observed_total = (
        checkpoint["bytes"] + statistics["bytes"] + conformer_config["bytes"]
    )
    if observed_total > MAX_TOTAL_BYTES:
        raise ValueError("MusicFM-FMA artifacts exceed the approved byte cap")
    if not {"melspec_2048_mean", "melspec_2048_std"}.issubset(
        statistics_structure["top_level_keys"]
    ):
        raise ValueError("MusicFM-FMA statistics lack required normalisation keys")
    if config_structure["selected_values"].get("model_type") not in {
        "wav2vec2-conformer",
        "wav2vec2_conformer",
    }:
        raise ValueError("external configuration model type changed")
    document: dict[str, Any] = {
        "schema": MUSICFM_FMA_EVIDENCE_SCHEMA,
        "status": "artifacts_verified_statically_not_loaded",
        "binding": {
            "admission_plan_sha256": checked_plan["document_sha256"],
            "sunofriend_repository_commit": checked_plan["repository_commit"],
            "provider_id": MUSICFM_FMA_PROVIDER_ID,
            "model_publication_revision": MODEL_PUBLICATION_REVISION,
            "config_publication_revision": CONFIG_PUBLICATION_REVISION,
        },
        "artifacts": {
            "checkpoint": checkpoint,
            "statistics": statistics,
            "external_conformer_config": conformer_config,
        },
        "download": {
            "approved_maximum_bytes": MAX_TOTAL_BYTES,
            "observed_total_bytes": observed_total,
            "within_approved_cap": True,
            "automatic_retry_used": False,
        },
        "checkpoint_archive": archive,
        "checkpoint_pickle": pickle,
        "json_structure": {
            "statistics": statistics_structure,
            "external_conformer_config": config_structure,
        },
        "classification": {
            "kind": "pytorch_zip_checkpoint_static_structure_only",
            "loading_safety": "not_established_by_static_opcode_inspection",
            "future_required_loader": (
                "torch.load(path, weights_only=True, map_location='cpu')"
            ),
            "authorizes_loading": False,
            "authorizes_execution": False,
        },
        "authority": {
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
        },
        "effects": {
            "artifact_bytes_read": True,
            "archive_metadata_parsed": True,
            "pickle_opcodes_parsed": True,
            "json_parsed": True,
            "checkpoint_deserialized": False,
            "torch_load_called": False,
            "dependency_installed": False,
            "model_imported": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "features_extracted": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_fma_static_evidence(document, checked_plan)


def validate_musicfm_fma_static_evidence(
    evidence: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    checked_plan = validate_musicfm_fma_admission_plan(plan)
    document = dict(evidence)
    if document.get("schema") != MUSICFM_FMA_EVIDENCE_SCHEMA:
        raise ValueError("unsupported MusicFM-FMA static evidence schema")
    _verify_hash(document)
    if set(document) != {
        "schema",
        "status",
        "binding",
        "artifacts",
        "download",
        "checkpoint_archive",
        "checkpoint_pickle",
        "json_structure",
        "classification",
        "authority",
        "privacy",
        "effects",
        "document_sha256",
    }:
        raise ValueError("MusicFM-FMA static evidence fields changed")
    if document.get("status") != "artifacts_verified_statically_not_loaded":
        raise ValueError("MusicFM-FMA static evidence status changed")
    if document.get("binding") != {
        "admission_plan_sha256": checked_plan["document_sha256"],
        "sunofriend_repository_commit": checked_plan["repository_commit"],
        "provider_id": MUSICFM_FMA_PROVIDER_ID,
        "model_publication_revision": MODEL_PUBLICATION_REVISION,
        "config_publication_revision": CONFIG_PUBLICATION_REVISION,
    }:
        raise ValueError("MusicFM-FMA static evidence binding changed")
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("MusicFM-FMA artifact records changed")
    if artifacts.get("checkpoint") != {
        "file": CHECKPOINT_FILE,
        "bytes": CHECKPOINT_BYTES,
        "sha256": CHECKPOINT_SHA256,
    }:
        raise ValueError("MusicFM-FMA checkpoint identity changed")
    for key, filename, expected_bytes in (
        ("statistics", STATS_FILE, STATS_BYTES),
        ("external_conformer_config", CONFIG_FILE, CONFIG_BYTES),
    ):
        row = artifacts.get(key)
        if (
            not isinstance(row, Mapping)
            or row.get("file") != filename
            or row.get("bytes") != expected_bytes
            or not _is_sha256(row.get("sha256"))
        ):
            raise ValueError(f"MusicFM-FMA {key} identity changed")
    if document.get("download") != {
        "approved_maximum_bytes": MAX_TOTAL_BYTES,
        "observed_total_bytes": CHECKPOINT_BYTES + STATS_BYTES + CONFIG_BYTES,
        "within_approved_cap": True,
        "automatic_retry_used": False,
    }:
        raise ValueError("MusicFM-FMA download evidence changed")
    if document.get("classification") != {
        "kind": "pytorch_zip_checkpoint_static_structure_only",
        "loading_safety": "not_established_by_static_opcode_inspection",
        "future_required_loader": (
            "torch.load(path, weights_only=True, map_location='cpu')"
        ),
        "authorizes_loading": False,
        "authorizes_execution": False,
    }:
        raise ValueError("MusicFM-FMA static classification changed")
    if document.get("authority") != {
        "dependency_install_authorized": False,
        "model_load_authorized": False,
        "synthetic_inference_authorized": False,
        "private_audio_access_authorized": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_changed": False,
    }:
        raise ValueError("MusicFM-FMA static authority changed")
    if document.get("privacy") != {
        "paths_embedded": False,
        "audio_embedded": False,
        "private_notes_embedded": False,
    }:
        raise ValueError("MusicFM-FMA static privacy changed")
    if document.get("effects") != {
        "artifact_bytes_read": True,
        "archive_metadata_parsed": True,
        "pickle_opcodes_parsed": True,
        "json_parsed": True,
        "checkpoint_deserialized": False,
        "torch_load_called": False,
        "dependency_installed": False,
        "model_imported": False,
        "model_constructed": False,
        "inference_runs": 0,
        "audio_reads": 0,
        "features_extracted": False,
        "training_started": False,
        "model_weights_changed": False,
    }:
        raise ValueError("MusicFM-FMA static effects changed")
    return document


def verify_musicfm_fma_static_evidence_round_trip(
    evidence_root: str | Path,
    plan: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-read the exact three-file root and reproduce the evidence document."""

    root = Path(evidence_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("MusicFM-FMA evidence root must be a real directory")
    actual = {row.name for row in root.iterdir()}
    expected = {CHECKPOINT_FILE, STATS_FILE, CONFIG_FILE}
    if actual != expected:
        raise ValueError("MusicFM-FMA evidence root file roster changed")
    if any((root / name).is_symlink() for name in expected):
        raise ValueError("MusicFM-FMA evidence artifacts must not be symlinks")
    reproduced = inspect_musicfm_fma_static_evidence(
        plan,
        checkpoint_path=root / CHECKPOINT_FILE,
        statistics_path=root / STATS_FILE,
        conformer_config_path=root / CONFIG_FILE,
    )
    checked = validate_musicfm_fma_static_evidence(evidence, plan)
    if reproduced != checked:
        raise ValueError("MusicFM-FMA static evidence does not match artifact bytes")
    return {
        "status": "verified_static_evidence_round_trip",
        "evidence_document_sha256": checked["document_sha256"],
        "artifact_count": 3,
        "model_loaded": False,
        "inference_runs": 0,
        "audio_reads": 0,
        "training_started": False,
    }


def _inspect_json(
    path: Path, *, expected_file: str, expected_bytes: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.name != expected_file:
        raise ValueError("JSON artifact filename changed")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or details.st_size != expected_bytes
        ):
            raise ValueError("JSON artifact is not the exact regular file")
        if expected_bytes > MAX_JSON_BYTES:
            raise ValueError("JSON artifact exceeds inspection limit")
        data = os.read(descriptor, expected_bytes + 1)
        if len(data) != expected_bytes:
            raise ValueError("JSON artifact bounded read differs")
        try:
            parsed = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("JSON artifact is not bounded canonical data") from error
        if not isinstance(parsed, dict):
            raise ValueError("JSON artifact top level must be an object")
    finally:
        os.close(descriptor)
    selected = {
        key: parsed[key]
        for key in ("model_type", "hidden_size", "num_hidden_layers")
        if key in parsed
    }
    return (
        {
            "file": expected_file,
            "bytes": expected_bytes,
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        {
            "kind": "bounded-json-object",
            "top_level_keys": sorted(parsed),
            "top_level_key_count": len(parsed),
            "selected_values": selected,
            "code_executed": False,
        },
    )


def _verify_hash(document: Mapping[str, Any]) -> None:
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("MusicFM-FMA static evidence document hash changed")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "MUSICFM_FMA_EVIDENCE_SCHEMA",
    "inspect_musicfm_fma_static_evidence",
    "validate_musicfm_fma_static_evidence",
    "verify_musicfm_fma_static_evidence_round_trip",
]
