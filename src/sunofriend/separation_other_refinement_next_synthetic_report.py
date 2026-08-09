"""Pure validation for the single Mega-53 generated-tensor report."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .separation_other_refinement_next_synthetic_plan import (
    ALIGNED_CHUNK_SIZE,
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_MLX_MEMORY_BYTES,
    MAXIMUM_RECONSTRUCTION_ERROR,
    MODEL_LOAD_REPORT_SHA256,
    NATIVE_ROLES,
    SYNTH_ROLE_INDEX,
)

REPORT_SCHEMA = "sunofriend.mega53-generated-tensor-forward-report.v1"


def report_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "report_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def validate_synthetic_report(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != REPORT_SCHEMA:
        raise ValueError("Mega-53 synthetic report schema differs")
    if value.get("report_sha256") != report_sha256(value):
        raise ValueError("Mega-53 synthetic report hash differs")
    if value.get("profile_id") != "bs-roformer-mega-53-synth-v1":
        raise ValueError("Mega-53 synthetic profile differs")
    if value.get("model_load_report_sha256") != MODEL_LOAD_REPORT_SHA256:
        raise ValueError("Mega-53 model-load binding differs")
    guards = value.get("guards", {})
    if guards != {
        "audio_open_attempts": 0,
        "external_checkpoint_open_attempts": 0,
        "network_attempts": 0,
        "os_network_denial_required": True,
        "restricted_torch_load_calls": 1,
        "forward_calls": 1,
    }:
        raise ValueError("Mega-53 synthetic effects boundary differs")
    result = value.get("result", {})
    completed = result.get("forward_completed") is True
    if completed:
        if result.get("output_shape") != [1, len(NATIVE_ROLES), 2, ALIGNED_CHUNK_SIZE]:
            raise ValueError("Mega-53 synthetic output shape differs")
        if (
            result.get("output_dtype") != "float32"
            or result.get("all_samples_finite") is not True
        ):
            raise ValueError("Mega-53 synthetic output samples differ")
        if result.get("synth_role_index") != SYNTH_ROLE_INDEX:
            raise ValueError("Mega-53 synthetic role mapping differs")
        if (
            not 0
            <= result.get("maximum_reconstruction_error", -1)
            <= MAXIMUM_RECONSTRUCTION_ERROR
        ):
            raise ValueError("Mega-53 reconstruction accounting failed")
    if not 0 < result.get("elapsed_seconds", 0) <= MAXIMUM_ELAPSED_SECONDS:
        raise ValueError("Mega-53 synthetic elapsed ceiling failed")
    if not 0 < result.get("peak_mlx_memory_bytes", 0) <= MAXIMUM_PEAK_MLX_MEMORY_BYTES:
        raise ValueError("Mega-53 synthetic memory ceiling failed")
    effects = value.get("effects", {})
    if effects != {
        "audio_reads": 0,
        "audio_writes": 0,
        "inference_attempts": 1,
        "persisted_audio": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "automatic_retry": False,
    }:
        raise ValueError("Mega-53 synthetic report expanded authority")
    return json.loads(json.dumps(value))


__all__ = ["REPORT_SCHEMA", "report_sha256", "validate_synthetic_report"]
