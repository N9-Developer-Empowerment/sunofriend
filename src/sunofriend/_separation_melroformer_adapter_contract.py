"""Synthetic-only validation core for a future MelBand-RoFormer worker.

The real model bridge does not exist.  This module accepts only an explicitly
labelled synthetic engine result, validates the audio and post-sanitisation
weight-key contracts, derives the instrumental residual and records additive
accounting.  It performs no file, checkpoint, tensor-runtime, network or
process operation and is imported by no public interface.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import deep_freeze as _freeze


SCHEMA = "sunofriend.private-melroformer-adapter-observation.v1"
ENGINE_SCHEMA = "sunofriend.private-melroformer-synthetic-engine-result.v1"
SAMPLE_RATE = 44_100
CHANNELS = 2
MAXIMUM_FRAMES = 661_500
MAXIMUM_ABSOLUTE_MODEL_SAMPLE = 16.0
MAXIMUM_WEIGHT_KEYS = 100_000
MAXIMUM_WEIGHT_KEY_BYTES = 1024
RECONSTRUCTION_TOLERANCE = 1e-6
_FLOAT32 = struct.Struct("<f")
_STEREO_FLOAT32 = struct.Struct("<ff")
_WEIGHT_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_PERMITTED_DROPPED_SUFFIX = ".rotary_embed.freqs"
_NO_EFFECTS = {
    "filesystem_accessed": False,
    "filesystem_written": False,
    "network_used": False,
    "package_installed": False,
    "checkpoint_opened": False,
    "tensor_deserialized": False,
    "model_imported": False,
    "process_started": False,
}


@dataclass(frozen=True)
class _SyntheticMelRoFormerEngineResult:
    """Test-double output.  This is not runtime or checkpoint authority."""

    schema: str
    engine_kind: str
    vocals: Sequence[Sequence[float]]
    sanitized_weight_keys: Sequence[str]
    expected_model_keys: Sequence[str]
    dropped_raw_weight_keys: Sequence[str]
    effects: Mapping[str, bool]


@dataclass(frozen=True)
class _SyntheticMelRoFormerAdapterObservation:
    """Immutable synthetic audio plus its path-free evidence document."""

    vocals: tuple[tuple[float, float], ...]
    instrumental: tuple[tuple[float, float], ...]
    evidence: Mapping[str, Any]


def _exercise_private_melroformer_adapter_contract(
    source: Sequence[Sequence[float]],
    *,
    sample_rate: int,
    engine_result: _SyntheticMelRoFormerEngineResult,
) -> _SyntheticMelRoFormerAdapterObservation:
    """Exercise the validation core without importing or invoking a model."""

    if type(sample_rate) is not int or sample_rate != SAMPLE_RATE:
        raise ValueError("MelRoFormer adapter requires exact 44.1 kHz audio")
    if type(engine_result) is not _SyntheticMelRoFormerEngineResult:
        raise ValueError("MelRoFormer adapter requires an exact synthetic result")
    if (
        engine_result.schema != ENGINE_SCHEMA
        or engine_result.engine_kind != "synthetic_test_double"
    ):
        raise ValueError("MelRoFormer adapter accepts only a synthetic test double")
    effects = _validate_no_effects(engine_result.effects)
    source_frames = _validate_audio(source, label="source", maximum_absolute=1.0)
    vocal_frames = _validate_audio(
        engine_result.vocals,
        label="vocals",
        maximum_absolute=MAXIMUM_ABSOLUTE_MODEL_SAMPLE,
    )
    if len(vocal_frames) != len(source_frames):
        raise ValueError("MelRoFormer vocals frame count differs from source")
    coverage = _validate_weight_coverage(engine_result)

    instrumental: list[tuple[float, float]] = []
    maximum_error = 0.0
    squared_error = 0.0
    for source_frame, vocal_frame in zip(source_frames, vocal_frames):
        residual = (
            _float32(source_frame[0] - vocal_frame[0]),
            _float32(source_frame[1] - vocal_frame[1]),
        )
        instrumental.append(residual)
        for channel in range(CHANNELS):
            error = abs(
                source_frame[channel]
                - (vocal_frame[channel] + residual[channel])
            )
            maximum_error = max(maximum_error, error)
            squared_error += error * error
    if maximum_error > RECONSTRUCTION_TOLERANCE:
        raise ValueError("MelRoFormer residual accounting exceeds tolerance")

    instrumental_frames = tuple(instrumental)
    sample_count = len(source_frames) * CHANNELS
    evidence = {
        "schema": SCHEMA,
        "status": "synthetic_contract_complete_real_worker_absent",
        "engine": {
            "schema": ENGINE_SCHEMA,
            "kind": "synthetic_test_double",
            "invoked_by_adapter": False,
            "model_runtime_available": False,
        },
        "geometry": {
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "frames": len(source_frames),
            "duration_seconds": len(source_frames) / SAMPLE_RATE,
            "maximum_frames": MAXIMUM_FRAMES,
        },
        "weight_coverage": coverage,
        "outputs": {
            "vocals": _audio_evidence(vocal_frames),
            "instrumental": _audio_evidence(instrumental_frames),
        },
        "additive_accounting": {
            "equation": "source = vocals + instrumental",
            "sample_count": sample_count,
            "maximum_absolute_error": maximum_error,
            "root_mean_square_error": math.sqrt(squared_error / sample_count),
            "tolerance": RECONSTRUCTION_TOLERANCE,
            "passed": True,
            "pcm24_persistence_verified": False,
        },
        "permissions": {
            "runtime_installation_permitted": False,
            "checkpoint_access_permitted": False,
            "checkpoint_loading_permitted": False,
            "model_import_permitted": False,
            "worker_start_permitted": False,
            "inference_permitted": False,
            "publication_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
        },
        "effects": effects,
    }
    return _SyntheticMelRoFormerAdapterObservation(
        vocals=vocal_frames,
        instrumental=instrumental_frames,
        evidence=_freeze(evidence),
    )


def _validate_audio(
    value: Sequence[Sequence[float]], *, label: str, maximum_absolute: float
) -> tuple[tuple[float, float], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"MelRoFormer {label} audio must be a frame sequence")
    if not 1 <= len(value) <= MAXIMUM_FRAMES:
        raise ValueError(f"MelRoFormer {label} frame count is outside the bound")
    frames: list[tuple[float, float]] = []
    for frame in value:
        if isinstance(frame, (str, bytes)) or not isinstance(frame, Sequence):
            raise ValueError(f"MelRoFormer {label} frame must be stereo")
        if len(frame) != CHANNELS:
            raise ValueError(f"MelRoFormer {label} frame must be stereo")
        channels: list[float] = []
        for sample in frame:
            if isinstance(sample, bool) or not isinstance(sample, (int, float)):
                raise ValueError(f"MelRoFormer {label} sample is invalid")
            number = float(sample)
            if not math.isfinite(number) or abs(number) > maximum_absolute:
                raise ValueError(f"MelRoFormer {label} sample is outside the bound")
            channels.append(_float32(number))
        frames.append((channels[0], channels[1]))
    return tuple(frames)


def _validate_weight_coverage(
    result: _SyntheticMelRoFormerEngineResult,
) -> dict[str, Any]:
    sanitized = _weight_keys(result.sanitized_weight_keys, "sanitized")
    expected = _weight_keys(result.expected_model_keys, "expected")
    dropped = _weight_keys(
        result.dropped_raw_weight_keys, "dropped", allow_empty=True
    )
    sanitized_set = set(sanitized)
    expected_set = set(expected)
    missing = sorted(expected_set - sanitized_set)
    unexpected = sorted(sanitized_set - expected_set)
    if missing or unexpected:
        raise ValueError("MelRoFormer post-sanitisation model-key coverage differs")
    if any(not key.endswith(_PERMITTED_DROPPED_SUFFIX) for key in dropped):
        raise ValueError("MelRoFormer sanitizer dropped an unapproved weight key")
    return {
        "sanitized_key_count": len(sanitized),
        "expected_model_key_count": len(expected),
        "dropped_raw_key_count": len(dropped),
        "sanitized_keys_sha256": _string_sequence_sha256(sanitized),
        "expected_model_keys_sha256": _string_sequence_sha256(expected),
        "dropped_raw_keys_sha256": _string_sequence_sha256(dropped),
        "missing_model_keys": [],
        "unexpected_sanitized_keys": [],
        "permitted_dropped_suffix": _PERMITTED_DROPPED_SUFFIX,
        "complete": True,
    }


def _weight_keys(
    value: Sequence[str], label: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"MelRoFormer {label} weight keys must be a sequence")
    if len(value) > MAXIMUM_WEIGHT_KEYS or (not allow_empty and not value):
        raise ValueError(f"MelRoFormer {label} weight key count is invalid")
    keys: list[str] = []
    for key in value:
        if (
            not isinstance(key, str)
            or not key
            or len(key.encode("utf-8")) > MAXIMUM_WEIGHT_KEY_BYTES
            or not _WEIGHT_KEY_RE.fullmatch(key)
        ):
            raise ValueError(f"MelRoFormer {label} weight key is invalid")
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError(f"MelRoFormer {label} weight keys contain duplicates")
    return tuple(sorted(keys))


def _validate_no_effects(value: Mapping[str, bool]) -> dict[str, bool]:
    if type(value) is not dict or value != _NO_EFFECTS:
        raise ValueError("MelRoFormer synthetic engine effects differ from no-effects policy")
    return dict(_NO_EFFECTS)


def _audio_evidence(frames: tuple[tuple[float, float], ...]) -> dict[str, Any]:
    digest = hashlib.sha256()
    square_sum = 0.0
    peak = 0.0
    for left, right in frames:
        digest.update(_STEREO_FLOAT32.pack(left, right))
        for sample in (left, right):
            peak = max(peak, abs(sample))
            square_sum += sample * sample
    return {
        "representation": "little-endian stereo float32",
        "sha256": digest.hexdigest(),
        "frames": len(frames),
        "sample_count": len(frames) * CHANNELS,
        "peak": peak,
        "rms": math.sqrt(square_sum / (len(frames) * CHANNELS)),
        "persisted": False,
    }


def _string_sequence_sha256(value: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for item in value:
        encoded = item.encode("utf-8")
        digest.update(struct.pack("<I", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _float32(value: float) -> float:
    return _FLOAT32.unpack(_FLOAT32.pack(value))[0]


__all__ = [
    "ENGINE_SCHEMA",
    "SCHEMA",
    "_SyntheticMelRoFormerAdapterObservation",
    "_SyntheticMelRoFormerEngineResult",
    "_exercise_private_melroformer_adapter_contract",
]
