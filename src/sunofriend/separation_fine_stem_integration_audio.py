"""Model-free projection and PCM24 accounting for six-role integration."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .separation_fine_stem_canary_audio import PCM24_MAX, PCM24_MIN, PCM24_SCALE


FFT_SIZE = 4096
HOP_SIZE = 1024
EPSILON = 1e-12


def _geometry(*values: np.ndarray) -> tuple[np.ndarray, ...]:
    arrays = tuple(np.asarray(value, dtype=np.float64) for value in values)
    if not arrays or arrays[0].ndim != 2 or arrays[0].shape[1] != 2:
        raise ValueError("fine-stem integration requires frame-major stereo audio")
    if any(value.shape != arrays[0].shape for value in arrays):
        raise ValueError("fine-stem integration audio clocks differ")
    if any(not np.isfinite(value).all() for value in arrays):
        raise ValueError("fine-stem integration audio is non-finite")
    return arrays


def _periodic_hann(size: int) -> np.ndarray:
    return np.hanning(size + 1)[:-1].astype(np.float64)


def _stft(value: np.ndarray) -> tuple[np.ndarray, dict[str, int]]:
    channels = value.T
    edge = FFT_SIZE // 2
    padded = np.pad(channels, ((0, 0), (edge, edge)))
    remainder = (padded.shape[1] - FFT_SIZE) % HOP_SIZE
    tail = (HOP_SIZE - remainder) % HOP_SIZE
    if tail:
        padded = np.pad(padded, ((0, 0), (0, tail)))
    frames = np.lib.stride_tricks.sliding_window_view(
        padded, FFT_SIZE, axis=1
    )[:, ::HOP_SIZE, :]
    window = _periodic_hann(FFT_SIZE)
    spectrum = np.fft.rfft(frames * window, axis=-1)
    return spectrum, {
        "frames": value.shape[0],
        "edge": edge,
        "padded_frames": padded.shape[1],
    }


def _istft(spectrum: np.ndarray, geometry: Mapping[str, int]) -> np.ndarray:
    window = _periodic_hann(FFT_SIZE)
    padded_frames = int(geometry["padded_frames"])
    output = np.zeros((spectrum.shape[0], padded_frames), dtype=np.float64)
    weight = np.zeros(padded_frames, dtype=np.float64)
    frames = np.fft.irfft(spectrum, n=FFT_SIZE, axis=-1)
    for index in range(frames.shape[1]):
        start = index * HOP_SIZE
        stop = start + FFT_SIZE
        output[:, start:stop] += frames[:, index, :] * window
        weight[start:stop] += np.square(window)
    nonzero = weight > EPSILON
    output[:, nonzero] /= weight[nonzero]
    edge = int(geometry["edge"])
    count = int(geometry["frames"])
    return output[:, edge : edge + count].T


def project_within_grouped_other(
    grouped_other: np.ndarray,
    raw_synth: np.ndarray,
    raw_guitar: np.ndarray,
) -> dict[str, Any]:
    """Allocate grouped other with one fixed three-way Wiener-like mask."""

    other, synth, guitar = _geometry(grouped_other, raw_synth, raw_guitar)
    other_stft, geometry = _stft(other)
    synth_stft, synth_geometry = _stft(synth)
    guitar_stft, guitar_geometry = _stft(guitar)
    if synth_geometry != geometry or guitar_geometry != geometry:
        raise RuntimeError("fine-stem integration STFT clocks differ")
    raw_residual_stft = other_stft - synth_stft - guitar_stft
    powers = np.stack(
        (
            np.square(np.abs(synth_stft)),
            np.square(np.abs(guitar_stft)),
            np.square(np.abs(raw_residual_stft)),
        ),
        axis=0,
    )
    denominator = np.sum(powers, axis=0)
    silent = denominator <= EPSILON
    denominator = np.where(silent, 1.0, denominator)
    masks = powers / denominator
    masks[0] = np.where(silent, 0.0, masks[0])
    masks[1] = np.where(silent, 0.0, masks[1])
    masks[2] = np.where(silent, 1.0, masks[2])
    projected_synth = _istft(masks[0] * other_stft, geometry)
    projected_guitar = _istft(masks[1] * other_stft, geometry)
    projected_other = other - projected_synth - projected_guitar
    if not all(
        np.isfinite(value).all()
        for value in (projected_synth, projected_guitar, projected_other)
    ):
        raise RuntimeError("fine-stem integration projection is non-finite")

    def correction(projected: np.ndarray, raw: np.ndarray) -> dict[str, float]:
        delta = projected - raw
        return {
            "rms": float(np.sqrt(np.mean(np.square(delta)))),
            "peak": float(np.max(np.abs(delta), initial=0.0)),
        }

    maximum_error = float(
        np.max(
            np.abs(projected_synth + projected_guitar + projected_other - other),
            initial=0.0,
        )
    )
    return {
        "synth": projected_synth,
        "guitar": projected_guitar,
        "other": projected_other,
        "accounting": {
            "maximum_float_reconstruction_error": maximum_error,
            "raw_to_projected_correction": {
                "synth": correction(projected_synth, synth),
                "guitar": correction(projected_guitar, guitar),
            },
            "method": "fixed grouped-other-constrained three-way Wiener mask",
        },
    }


def quantize_six_roles(
    *,
    reference: np.ndarray,
    vocals: np.ndarray,
    drums: np.ndarray,
    bass: np.ndarray,
    synth: np.ndarray,
    guitar: np.ndarray,
) -> dict[str, Any]:
    """Apply one shared attenuation and construct integer other last."""

    source, vocal, drum, bass_value, synth_value, guitar_value = _geometry(
        reference, vocals, drums, bass, synth, guitar
    )
    preliminary_other = source - vocal - drum - bass_value - synth_value - guitar_value
    peak = max(
        float(np.max(np.abs(value), initial=0.0))
        for value in (
            source,
            vocal,
            drum,
            bass_value,
            synth_value,
            guitar_value,
            preliminary_other,
        )
    )
    safe_peak = (PCM24_MAX - 8) / PCM24_SCALE
    gain = min(1.0, safe_peak / peak) if peak > 0 else 1.0
    for _attempt in range(8):
        reference_i = np.rint(source * gain * PCM24_SCALE).astype(np.int64)
        roles = {
            "vocals": np.rint(vocal * gain * PCM24_SCALE).astype(np.int64),
            "drums": np.rint(drum * gain * PCM24_SCALE).astype(np.int64),
            "bass": np.rint(bass_value * gain * PCM24_SCALE).astype(np.int64),
            "synth": np.rint(synth_value * gain * PCM24_SCALE).astype(np.int64),
            "guitar": np.rint(guitar_value * gain * PCM24_SCALE).astype(np.int64),
        }
        roles["other"] = reference_i - sum(roles.values())
        values = (reference_i, *roles.values())
        if all(
            value.min(initial=0) >= PCM24_MIN
            and value.max(initial=0) <= PCM24_MAX
            for value in values
        ):
            reconstruction = sum(roles.values())
            return {
                "reference": reference_i,
                "roles": roles,
                "shared_attenuation": gain,
                "maximum_reconstruction_error_lsb": int(
                    np.max(np.abs(reconstruction - reference_i), initial=0)
                ),
            }
        gain *= 0.999999
    raise RuntimeError("fine-stem six-role PCM24 accounting could not be bounded")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_pcm24(path: Path, integer: np.ndarray, *, sample_rate: int) -> dict[str, Any]:
    import soundfile as sf

    if integer.ndim != 2 or integer.shape[1] != 2:
        raise ValueError("fine-stem integration PCM24 geometry differs")
    if integer.min(initial=0) < PCM24_MIN or integer.max(initial=0) > PCM24_MAX:
        raise ValueError("fine-stem integration PCM24 range differs")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise FileExistsError("fine-stem integration artifact already exists")
    sf.write(
        path,
        integer.astype(np.float64) / PCM24_SCALE,
        sample_rate,
        subtype="PCM_24",
        format="WAV",
    )
    path.chmod(0o600)
    info = sf.info(path)
    persisted = sf.read(path, dtype="float64", always_2d=True)[0]
    persisted_integer = np.rint(persisted * PCM24_SCALE).astype(np.int64)
    if (
        info.samplerate != sample_rate
        or info.channels != 2
        or info.frames != len(integer)
        or info.subtype != "PCM_24"
        or not np.array_equal(persisted_integer, integer)
    ):
        raise RuntimeError("fine-stem integration PCM24 persistence differs")
    return {
        "relative_path": "",  # Filled only after the package root is known.
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "sample_rate_hz": sample_rate,
        "channels": 2,
        "frames": len(integer),
        "subtype": "PCM_24",
    }


def persist_six_roles(
    root: Path,
    *,
    case_id: str,
    quantized: Mapping[str, Any],
    sample_rate: int = 44_100,
) -> dict[str, Any]:
    """Persist one exact six-role review set with a reconstruction check."""

    reference = np.asarray(quantized["reference"], dtype=np.int64)
    roles = {
        role: np.asarray(quantized["roles"][role], dtype=np.int64)
        for role in ("vocals", "drums", "bass", "synth", "guitar", "other")
    }
    if any(value.shape != reference.shape for value in roles.values()):
        raise ValueError("fine-stem integration persisted role clocks differ")
    reconstruction = sum(roles.values())
    maximum_error = int(np.max(np.abs(reference - reconstruction), initial=0))
    if maximum_error > 2:
        raise ValueError("fine-stem integration reconstruction tolerance differs")
    arrays = {
        "reference": reference,
        **roles,
        "reconstruction_check": reconstruction,
    }
    case_root = root / "CASES" / case_id
    artifacts = {}
    for role, integer in arrays.items():
        path = case_root / f"{role}.wav"
        identity = _write_pcm24(path, integer, sample_rate=sample_rate)
        identity["relative_path"] = path.relative_to(root).as_posix()
        artifacts[role] = identity
    return {
        "artifacts": artifacts,
        "shared_attenuation": float(quantized["shared_attenuation"]),
        "maximum_reconstruction_error_lsb": maximum_error,
    }


__all__ = [
    "FFT_SIZE",
    "HOP_SIZE",
    "persist_six_roles",
    "project_within_grouped_other",
    "quantize_six_roles",
]
