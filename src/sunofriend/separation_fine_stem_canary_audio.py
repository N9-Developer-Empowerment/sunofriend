"""PCM24 persistence and review-page helpers for fine-stem canaries."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from .separation_fine_stem_canary_contract import (
    SAMPLE_RATE_HZ,
    WINDOW_FRAMES,
)


PCM24_SCALE = 2**23
PCM24_MIN = -(2**23)
PCM24_MAX = 2**23 - 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_canonical_pcm24(path: Path) -> np.ndarray:
    """Read one exact stereo 44.1 kHz, 15-second PCM24 presence excerpt."""

    import soundfile as sf

    info = sf.info(path)
    if (
        info.samplerate != SAMPLE_RATE_HZ
        or info.channels != 2
        or info.frames != WINDOW_FRAMES
        or info.subtype != "PCM_24"
    ):
        raise RuntimeError("fine-stem canary source is not canonical PCM24")
    value = sf.read(path, dtype="float64", always_2d=True)[0]
    if value.shape != (WINDOW_FRAMES, 2) or not np.isfinite(value).all():
        raise RuntimeError("fine-stem canary source samples differ")
    integer = np.rint(value * PCM24_SCALE).astype(np.int64)
    if (integer < PCM24_MIN).any() or (integer > PCM24_MAX).any():
        raise RuntimeError("fine-stem canary source exceeds PCM24")
    return integer.astype(np.float64) / PCM24_SCALE


def _quantize_pair(
    source: np.ndarray, native_target: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    native_residual = source - native_target
    peak = max(
        float(np.max(np.abs(source))),
        float(np.max(np.abs(native_target))),
        float(np.max(np.abs(native_residual))),
    )
    safe_peak = (PCM24_MAX - 4) / PCM24_SCALE
    gain = min(1.0, safe_peak / peak) if peak > 0 else 1.0
    for _attempt in range(8):
        reference = np.rint(source * gain * PCM24_SCALE).astype(np.int64)
        target = np.rint(native_target * gain * PCM24_SCALE).astype(np.int64)
        residual = reference - target
        if all(
            not ((value < PCM24_MIN).any() or (value > PCM24_MAX).any())
            for value in (reference, target, residual)
        ):
            return reference, target, residual, gain
        gain *= 0.999999
    raise RuntimeError("fine-stem canary PCM24 accounting could not be bounded")


def _write_and_verify_pcm24(path: Path, integer: np.ndarray) -> None:
    import soundfile as sf

    if integer.shape != (WINDOW_FRAMES, 2):
        raise RuntimeError("fine-stem PCM24 artifact shape differs")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    sf.write(
        path,
        integer.astype(np.float64) / PCM24_SCALE,
        SAMPLE_RATE_HZ,
        subtype="PCM_24",
        format="WAV",
    )
    path.chmod(0o600)
    persisted = sf.read(path, dtype="float64", always_2d=True)[0]
    persisted_integer = np.rint(persisted * PCM24_SCALE).astype(np.int64)
    if not np.array_equal(persisted_integer, integer):
        raise RuntimeError("fine-stem PCM24 persistence changed integer samples")


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(path)
    if (
        info.samplerate != SAMPLE_RATE_HZ
        or info.channels != 2
        or info.frames != WINDOW_FRAMES
        or info.subtype != "PCM_24"
    ):
        raise RuntimeError("fine-stem persisted artifact geometry differs")
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": 2,
        "frames": WINDOW_FRAMES,
        "subtype": "PCM_24",
    }


def persist_target_and_residual(
    root: Path,
    *,
    case_id: str,
    source: np.ndarray,
    native_target: np.ndarray,
    target_role: str,
) -> dict[str, Any]:
    """Persist one target/residual pair with exact integer reconstruction."""

    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(native_target, dtype=np.float64)
    if (
        source.shape != (WINDOW_FRAMES, 2)
        or target.shape != source.shape
        or not np.isfinite(source).all()
        or not np.isfinite(target).all()
    ):
        raise RuntimeError("fine-stem canary target geometry differs")
    reference_i, target_i, residual_i, gain = _quantize_pair(source, target)
    case_root = root / "CASES" / case_id
    paths = {
        "reference": case_root / "reference.wav",
        "target": case_root / (target_role + ".wav"),
        "residual": case_root / "residual.wav",
    }
    _write_and_verify_pcm24(paths["reference"], reference_i)
    _write_and_verify_pcm24(paths["target"], target_i)
    _write_and_verify_pcm24(paths["residual"], residual_i)
    reconstruction_error = int(
        np.max(np.abs((target_i + residual_i) - reference_i))
    )
    correction = target_i.astype(np.float64) / (PCM24_SCALE * gain) - target
    return {
        "artifacts": {
            name: _artifact(path, root) for name, path in paths.items()
        },
        "shared_attenuation": gain,
        "shared_attenuation_db": float(20 * np.log10(gain)) if gain > 0 else None,
        "native_target_rms": float(np.sqrt(np.mean(np.square(target)))),
        "native_target_peak": float(np.max(np.abs(target))),
        "native_target_quantization_correction_rms": float(
            np.sqrt(np.mean(np.square(correction)))
        ),
        "native_target_quantization_correction_peak": float(
            np.max(np.abs(correction))
        ),
        "maximum_reconstruction_error_lsb": reconstruction_error,
        "all_samples_finite": True,
    }


__all__ = [
    "PCM24_MAX",
    "PCM24_MIN",
    "PCM24_SCALE",
    "file_sha256",
    "persist_target_and_residual",
    "read_canonical_pcm24",
]
