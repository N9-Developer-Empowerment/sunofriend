"""Static, non-loading evidence for the exact BS-RoFormer-SW checkpoint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .separation_fine_stem_canary_contract import SW_CHECKPOINT, SW_CONFIG
from .separation_other_refinement_next_challenger_evidence import (
    _inspect_checkpoint,
)


SW_EVIDENCE_SCHEMA = "sunofriend.bs-roformer-sw-artifact-evidence.v1"
SW_DOWNLOAD_CAP_BYTES = 750 * 1024 * 1024
SW_PROFILE_ID = "bs-roformer-sw-guitar-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _document_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "evidence_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_sw_artifact_evidence(
    checkpoint_path: str | Path,
    config_path: str | Path,
    *,
    expected_checkpoint_bytes: int = SW_CHECKPOINT["bytes"],
    expected_checkpoint_sha256: str = SW_CHECKPOINT["sha256"],
    expected_config_bytes: int = SW_CONFIG["bytes"],
    expected_config_sha256: str = SW_CONFIG["sha256"],
) -> dict[str, Any]:
    """Hash and inspect one checkpoint ZIP without deserializing its pickle."""

    checkpoint, archive, pickle = _inspect_checkpoint(
        Path(checkpoint_path),
        expected_bytes=expected_checkpoint_bytes,
        expected_sha256=expected_checkpoint_sha256,
        artifact_file=SW_CHECKPOINT["file"],
        maximum_bytes=SW_DOWNLOAD_CAP_BYTES,
    )
    config = Path(config_path)
    if (
        config.name != SW_CONFIG["file"]
        or config.stat().st_size != expected_config_bytes
        or _file_sha256(config) != expected_config_sha256
    ):
        raise ValueError("BS-RoFormer-SW packaged configuration identity differs")
    document: dict[str, Any] = {
        "schema": SW_EVIDENCE_SCHEMA,
        "evidence_sha256": "",
        "status": "checkpoint_verified_statically_not_loaded",
        "profile_id": SW_PROFILE_ID,
        "artifacts": {
            "checkpoint": checkpoint,
            "packaged_config": {
                "file": SW_CONFIG["file"],
                "bytes": expected_config_bytes,
                "sha256": expected_config_sha256,
                "source": "verified source revision packaged offline config",
            },
        },
        "download": {
            "approved_cap_bytes": SW_DOWNLOAD_CAP_BYTES,
            "observed_checkpoint_bytes": checkpoint["bytes"],
            "within_approved_cap": checkpoint["bytes"] <= SW_DOWNLOAD_CAP_BYTES,
        },
        "checkpoint_archive": archive,
        "checkpoint_pickle": pickle,
        "terms": {
            "checkpoint": "CC-BY-NC-SA-4.0",
            "permitted_evaluation": "local_noncommercial_only",
            "hosting_or_redistribution_approved": False,
        },
        "classification": {
            "kind": "pytorch_zip_checkpoint_static_structure_only",
            "loading_safety": "not_established_by_static_opcode_inspection",
            "required_loader": "torch.load(weights_only=True, map_location='cpu')",
        },
        "effects": {
            "checkpoint_bytes_read": True,
            "archive_metadata_parsed": True,
            "pickle_opcodes_parsed": True,
            "checkpoint_deserialized": False,
            "torch_load_called": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
        },
    }
    document["evidence_sha256"] = _document_sha256(document)
    return document


def validate_sw_artifact_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    document = json.loads(json.dumps(value, allow_nan=False))
    digest = document.get("evidence_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("BS-RoFormer-SW evidence hash is invalid")
    if digest != _document_sha256(document):
        raise ValueError("BS-RoFormer-SW evidence hash differs")
    if document.get("schema") != SW_EVIDENCE_SCHEMA:
        raise ValueError("BS-RoFormer-SW evidence schema differs")
    artifacts = document.get("artifacts", {})
    if artifacts.get("checkpoint") != SW_CHECKPOINT:
        raise ValueError("BS-RoFormer-SW checkpoint identity differs")
    expected_config = {**SW_CONFIG, "source": "verified source revision packaged offline config"}
    if artifacts.get("packaged_config") != expected_config:
        raise ValueError("BS-RoFormer-SW config identity differs")
    download = document.get("download", {})
    if (
        download.get("approved_cap_bytes") != SW_DOWNLOAD_CAP_BYTES
        or download.get("observed_checkpoint_bytes") != SW_CHECKPOINT["bytes"]
        or download.get("within_approved_cap") is not True
    ):
        raise ValueError("BS-RoFormer-SW download boundary differs")
    effects = document.get("effects", {})
    forbidden = (
        "checkpoint_deserialized",
        "torch_load_called",
        "model_constructed",
        "public_activation",
        "source_selection",
        "midi_created",
        "hosting",
        "redistribution",
    )
    if any(effects.get(key) is not False for key in forbidden):
        raise ValueError("BS-RoFormer-SW static evidence expanded authority")
    if effects.get("inference_runs") != 0 or effects.get("audio_reads") != 0:
        raise ValueError("BS-RoFormer-SW static evidence contains execution")
    return document


__all__ = [
    "SW_DOWNLOAD_CAP_BYTES",
    "SW_EVIDENCE_SCHEMA",
    "inspect_sw_artifact_evidence",
    "validate_sw_artifact_evidence",
]
