"""Static, network-denied inspection for the six-source MLX installation.

This inspection verifies immutable files, exact package versions and the one
allowed config normalization.  It deliberately does not import MLX, open the
safetensors payload, construct a model, read audio or run inference.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from typing import Any

from .separation_other_refinement_demucs_mlx_candidate import (
    EXPECTED_SEGMENT,
    MODEL_SOURCE_ORDER,
    RUNTIME_REQUIREMENTS_BYTES,
    RUNTIME_REQUIREMENTS_SHA256,
    normalize_pinned_six_source_config,
)
from .separation_profiles import (
    OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
    separation_profile,
)


INSPECTION_SCHEMA = "sunofriend.other-refinement-demucs-mlx-inspection.v1"


def inspect_installation(root: Path) -> dict[str, Any]:
    root = root.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("candidate installation root must be a real directory")
    profile = separation_profile(OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID)

    artifacts: dict[str, dict[str, Any]] = {}
    for expected in profile.artifacts:
        path = _regular_file(root / expected.relative_path, expected.name)
        digest = _sha256(path)
        if path.stat().st_size != expected.bytes or digest != expected.sha256:
            raise ValueError(f"candidate {expected.name} identity differs")
        artifacts[expected.name] = {
            "relative_path": expected.relative_path,
            "bytes": expected.bytes,
            "sha256": digest,
        }

    requirements = _regular_file(
        root / "TERMS/separation-runtime-requirements.txt", "runtime lock"
    )
    if (
        requirements.stat().st_size != RUNTIME_REQUIREMENTS_BYTES
        or _sha256(requirements) != RUNTIME_REQUIREMENTS_SHA256
    ):
        raise ValueError("candidate runtime lock identity differs")

    packages = {
        name: importlib.metadata.version(name) for name in profile.packages()
    }
    if packages != dict(profile.packages()):
        raise ValueError("candidate installed package identity differs")
    if importlib.util.find_spec("torch") is not None:
        raise ValueError("candidate inference runtime must not contain PyTorch")

    config_path = root / profile.artifact("config").relative_path
    config_bytes_before = config_path.read_bytes()
    try:
        config = json.loads(config_bytes_before.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("candidate config is not valid UTF-8 JSON") from exc
    normalized = normalize_pinned_six_source_config(config)
    if config_path.read_bytes() != config_bytes_before:
        raise ValueError("candidate config changed during static inspection")
    if tuple(normalized["kwargs"]["sources"]) != MODEL_SOURCE_ORDER:
        raise ValueError("normalized candidate role order differs")
    if normalized["kwargs"]["segment"] != float(EXPECTED_SEGMENT):
        raise ValueError("normalized candidate segment differs")

    return {
        "schema": INSPECTION_SCHEMA,
        "status": "passed_static_identity_and_config_only",
        "profile_id": profile.profile_id,
        "artifacts": artifacts,
        "runtime": {
            "packages": packages,
            "requirements_bytes": requirements.stat().st_size,
            "requirements_sha256": _sha256(requirements),
            "pytorch_present": False,
        },
        "config": {
            "model_name": config["model_name"],
            "model_source_order": list(MODEL_SOURCE_ORDER),
            "source_segment_value": config["kwargs"]["segment"],
            "normalized_segment_seconds": normalized["kwargs"]["segment"],
            "normalization_in_memory_only": True,
            "source_artifact_unchanged": True,
        },
        "next_gate": (
            "separately review and approve model construction plus a network-denied "
            "synthetic inference canary"
        ),
        "effects": {
            "network_denial_enforced_by_coordinator": True,
            "network_used": False,
            "model_module_imported": False,
            "checkpoint_payload_opened": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
        },
    }


def _regular_file(path: Path, label: str) -> Path:
    path = path.absolute()
    attached = path.lstat()
    if path.is_symlink() or not path.is_file() or attached.st_nlink != 1:
        raise ValueError(f"candidate {label} must be a single-link regular file")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["INSPECTION_SCHEMA", "inspect_installation"]
