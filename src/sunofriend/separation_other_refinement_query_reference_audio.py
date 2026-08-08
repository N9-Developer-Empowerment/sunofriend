"""Deterministic WAV I/O and PCM24 accounting for the reference canary."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
import wave

import numpy as np
import torch
import torchaudio


SAMPLE_RATE = 44_100
PCM24_SCALE = 8_388_608
PCM24_MIN = -8_388_608
PCM24_MAX = 8_388_607


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_pcm_wav(path: Path) -> dict[str, int | str]:
    with wave.open(str(path), "rb") as source:
        if source.getcomptype() != "NONE":
            raise RuntimeError("reference WAV must use uncompressed PCM")
        return {
            "sample_rate_hz": source.getframerate(),
            "channels": source.getnchannels(),
            "sample_width_bytes": source.getsampwidth(),
            "frames": source.getnframes(),
            "compression": source.getcomptype(),
        }


def _decode_pcm(payload: bytes, *, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (np.frombuffer(payload, dtype=np.uint8).astype(np.int32) - 128).astype(
            np.float32
        ) / 128.0
    if sample_width == 2:
        return np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32_768.0
    if sample_width == 3:
        raw = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3)
        values = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        return values.astype(np.float32) / float(PCM24_SCALE)
    if sample_width == 4:
        return (
            np.frombuffer(payload, dtype="<i4").astype(np.float32)
            / 2_147_483_648.0
        )
    raise RuntimeError("reference WAV sample width is unsupported")


def read_wav_window(
    path: Path,
    *,
    start_seconds: float,
    end_seconds: float,
    expected_frames: int,
) -> torch.Tensor:
    """Decode one exact window and canonicalise it to stereo float32/44.1 kHz."""

    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("reference WAV window is invalid")
    with wave.open(str(path), "rb") as source:
        if source.getcomptype() != "NONE":
            raise RuntimeError("reference WAV must use uncompressed PCM")
        channels = source.getnchannels()
        if channels not in {1, 2}:
            raise RuntimeError("reference WAV must be mono or stereo")
        rate = source.getframerate()
        start = round(start_seconds * rate)
        stop = round(end_seconds * rate)
        if start < 0 or stop > source.getnframes() or stop <= start:
            raise RuntimeError("reference WAV window exceeds its source")
        source.setpos(start)
        payload = source.readframes(stop - start)
        sample_width = source.getsampwidth()
    decoded = _decode_pcm(payload, sample_width=sample_width)
    if decoded.size != (stop - start) * channels:
        raise RuntimeError("reference WAV decoded frame count differs")
    decoded = decoded.reshape(-1, channels)
    if channels == 1:
        decoded = np.repeat(decoded, 2, axis=1)
    tensor = torch.from_numpy(decoded.T.copy()).unsqueeze(0)
    if rate != SAMPLE_RATE:
        tensor = torchaudio.functional.resample(tensor, rate, SAMPLE_RATE)
    tensor = tensor.to(dtype=torch.float32).contiguous()
    if tensor.shape != (1, 2, expected_frames):
        raise RuntimeError(
            f"canonical reference WAV shape differs: {tuple(tensor.shape)}"
        )
    if not bool(torch.isfinite(tensor).all()):
        raise RuntimeError("canonical reference WAV contains non-finite samples")
    return tensor


def _quantize(value: np.ndarray, attenuation: float) -> np.ndarray:
    quantized = np.rint(value.astype(np.float64) * attenuation * PCM24_SCALE)
    return quantized.astype(np.int64)


def build_pcm24_accounting(
    mixture: torch.Tensor,
    target: torch.Tensor,
) -> dict[str, Any]:
    """Create an exact integer residual while sharing any required attenuation."""

    if mixture.shape != target.shape or mixture.shape[0:2] != (1, 2):
        raise RuntimeError("reference target shape differs from its mixture")
    if mixture.dtype != torch.float32 or target.dtype != torch.float32:
        raise RuntimeError("reference tensors must be float32")
    if not bool(torch.isfinite(mixture).all() and torch.isfinite(target).all()):
        raise RuntimeError("reference tensors contain non-finite samples")
    mixture_np = mixture[0].T.detach().cpu().numpy()
    target_np = target[0].T.detach().cpu().numpy()
    residual_np = mixture_np - target_np
    peak = max(
        float(np.max(np.abs(mixture_np))),
        float(np.max(np.abs(target_np))),
        float(np.max(np.abs(residual_np))),
    )
    safe_peak = (PCM24_MAX - 2) / PCM24_SCALE
    attenuation = 1.0 if peak <= safe_peak or peak == 0 else safe_peak / peak
    source_pcm = _quantize(mixture_np, attenuation)
    target_pcm = _quantize(target_np, attenuation)
    residual_pcm = source_pcm - target_pcm
    for label, value in {
        "source": source_pcm,
        "target": target_pcm,
        "residual": residual_pcm,
    }.items():
        if value.min(initial=0) < PCM24_MIN or value.max(initial=0) > PCM24_MAX:
            raise RuntimeError(f"PCM24 {label} exceeds its integer range")
    maximum_error = int(np.max(np.abs((target_pcm + residual_pcm) - source_pcm)))
    return {
        "source": source_pcm.astype(np.int32),
        "target": target_pcm.astype(np.int32),
        "residual": residual_pcm.astype(np.int32),
        "shared_attenuation": attenuation,
        "source_peak": float(np.max(np.abs(mixture_np))),
        "target_peak": float(np.max(np.abs(target_np))),
        "residual_peak": float(np.max(np.abs(residual_np))),
        "maximum_reconstruction_error_lsb": maximum_error,
    }


def quantize_pcm24(value: torch.Tensor) -> tuple[np.ndarray, float]:
    if value.shape[0:2] != (1, 2) or not bool(torch.isfinite(value).all()):
        raise RuntimeError("reference audio tensor differs")
    frames = value[0].T.detach().cpu().numpy()
    peak = float(np.max(np.abs(frames)))
    safe_peak = (PCM24_MAX - 2) / PCM24_SCALE
    attenuation = 1.0 if peak <= safe_peak or peak == 0 else safe_peak / peak
    result = _quantize(frames, attenuation)
    if result.min(initial=0) < PCM24_MIN or result.max(initial=0) > PCM24_MAX:
        raise RuntimeError("PCM24 reference exceeds its integer range")
    return result.astype(np.int32), attenuation


def _pcm24_bytes(value: np.ndarray) -> bytes:
    if value.dtype != np.int32 or value.ndim != 2 or value.shape[1] != 2:
        raise ValueError("PCM24 writer requires frame-major stereo int32")
    little = np.ascontiguousarray(value.astype("<i4", copy=False))
    return little.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()


def write_pcm24(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(3)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(_pcm24_bytes(value))
    path.chmod(0o600)


def read_pcm24(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 2
            or source.getsampwidth() != 3
            or source.getframerate() != SAMPLE_RATE
            or source.getcomptype() != "NONE"
        ):
            raise RuntimeError("persisted reference audio geometry differs")
        frames = source.getnframes()
        payload = source.readframes(frames)
    decoded = _decode_pcm(payload, sample_width=3)
    return np.rint(decoded.reshape(frames, 2) * PCM24_SCALE).astype(np.int32)


def audio_artifact(path: Path, *, relative_to: Path) -> dict[str, Any]:
    info = inspect_pcm_wav(path)
    if info != {
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 2,
        "sample_width_bytes": 3,
        "frames": info["frames"],
        "compression": "NONE",
    }:
        raise RuntimeError("persisted reference audio contract differs")
    return {
        "relative_path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 2,
        "frames": info["frames"],
        "subtype": "PCM_24",
    }


__all__ = [
    "PCM24_MAX",
    "PCM24_MIN",
    "PCM24_SCALE",
    "SAMPLE_RATE",
    "audio_artifact",
    "build_pcm24_accounting",
    "file_sha256",
    "inspect_pcm_wav",
    "quantize_pcm24",
    "read_pcm24",
    "read_wav_window",
    "write_pcm24",
]
