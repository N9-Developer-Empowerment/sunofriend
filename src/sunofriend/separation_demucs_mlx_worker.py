"""Offline fixed-profile worker for the public core-four stem preview.

The coordinator launches this process under macOS network denial.  The worker
accepts only canonical PCM24 stereo 44.1 kHz audio, loads only the explicit
local safetensors cache with conversion disabled, and writes one exact set of
vocals, drums, bass and grouped-other artifacts.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import platform
from pathlib import Path
import resource
import sys
import time
from typing import Any, Mapping
import wave

from sunofriend.separation_profiles import CORE_FOUR_PROFILE_ID, separation_profile


SAMPLE_RATE = 44_100
CHANNELS = 2
PCM24_SCALE = 8_388_608
PCM24_MIN = -8_388_608
PCM24_MAX = 8_388_607
TARGET_PEAK = 0.99
MAXIMUM_PRE_ATTENUATION_PEAK = 4.0
MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES = 12 * 1024**3
MODEL_SOURCE_ORDER = ("drums", "bass", "other", "vocals")
PERSISTED_ROLE_ORDER = ("vocals", "drums", "bass", "other")
WORKER_SCHEMA = "sunofriend.experimental-core-four-worker.v1"


def decode_pcm24(contents: bytes, *, np: Any) -> Any:
    if len(contents) % (3 * CHANNELS):
        raise ValueError("PCM24 payload does not contain complete stereo frames")
    packed = np.frombuffer(contents, dtype=np.uint8).reshape(-1, 3)
    unsigned = (
        packed[:, 0].astype(np.int32)
        | (packed[:, 1].astype(np.int32) << 8)
        | (packed[:, 2].astype(np.int32) << 16)
    )
    signed = np.where(unsigned & 0x800000, unsigned - 0x1000000, unsigned)
    return (signed.astype(np.float32) / PCM24_SCALE).reshape(-1, CHANNELS)


def pack_pcm24(values: Any, *, np: Any) -> bytes:
    integers = np.asarray(values)
    if integers.dtype.kind not in "iu":
        raise ValueError("PCM24 packer requires integer samples")
    if integers.size and (
        int(integers.min()) < PCM24_MIN or int(integers.max()) > PCM24_MAX
    ):
        raise ValueError("PCM24 integer sample is outside the representable range")
    unsigned = integers.astype(np.int32, copy=False).reshape(-1) & 0xFFFFFF
    packed = np.empty((len(unsigned), 3), dtype=np.uint8)
    packed[:, 0] = unsigned & 0xFF
    packed[:, 1] = (unsigned >> 8) & 0xFF
    packed[:, 2] = (unsigned >> 16) & 0xFF
    return packed.tobytes()


def read_canonical_source(path: Path, *, np: Any) -> Any:
    with wave.open(str(path), "rb") as reader:
        if (
            reader.getnchannels() != CHANNELS
            or reader.getsampwidth() != 3
            or reader.getframerate() != SAMPLE_RATE
            or reader.getcomptype() != "NONE"
        ):
            raise ValueError("worker source must be PCM24 stereo 44.1 kHz WAV")
        frames = reader.getnframes()
        contents = reader.readframes(frames)
        if reader.readframes(1):
            raise ValueError("worker source contains undeclared frames")
    source = decode_pcm24(contents, np=np)
    if source.shape != (frames, CHANNELS) or not np.all(np.isfinite(source)):
        raise ValueError("worker source geometry or samples are invalid")
    return source


def quantize_pcm24(values: Any, *, np: Any) -> Any:
    values = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("non-finite audio cannot be quantized")
    return np.clip(
        np.rint(values * PCM24_SCALE), PCM24_MIN, PCM24_MAX
    ).astype(np.int32)


def write_pcm24_integers(path: Path, values: Any, *, np: Any) -> dict[str, Any]:
    integers = np.asarray(values)
    if integers.shape[1:] != (CHANNELS,) or integers.ndim != 2:
        raise ValueError("PCM24 output must have frames-by-stereo geometry")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(CHANNELS)
        writer.setsampwidth(3)
        writer.setframerate(SAMPLE_RATE)
        block = 65_536
        for start in range(0, len(integers), block):
            writer.writeframes(pack_pcm24(integers[start : start + block], np=np))
    return {
        "frames": len(integers),
        "channels": CHANNELS,
        "sample_rate": SAMPLE_RATE,
        "sample_width_bytes": 3,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def persist_core_four(
    source: Any,
    estimates: Mapping[str, Any],
    destination: Path,
    *,
    np: Any,
) -> dict[str, Any]:
    """Persist exact core-four PCM24 output from already-computed estimates."""

    source = np.asarray(source, dtype=np.float32)
    if source.ndim != 2 or source.shape[1] != CHANNELS or not len(source):
        raise ValueError("core-four source geometry differs")
    if set(estimates) != set(MODEL_SOURCE_ORDER):
        raise ValueError("core-four worker roles differ from the exact model contract")
    native: dict[str, Any] = {}
    peaks = [float(np.max(np.abs(source)))]
    for role in MODEL_SOURCE_ORDER:
        value = np.asarray(estimates[role], dtype=np.float32)
        if value.shape != source.shape or not np.all(np.isfinite(value)):
            raise ValueError(f"core-four {role} estimate geometry or samples differ")
        role_peak = float(np.max(np.abs(value)))
        if not math.isfinite(role_peak) or role_peak > MAXIMUM_PRE_ATTENUATION_PEAK:
            raise ValueError(f"core-four {role} estimate exceeds the peak bound")
        native[role] = value
        peaks.append(role_peak)
    if max(peaks[1:]) < 1.0 / PCM24_SCALE:
        raise ValueError("all four model roles are silent")

    residual = source - sum(native[role] for role in MODEL_SOURCE_ORDER)
    corrected_other = native["other"] + residual
    correction_rms = float(np.sqrt(np.mean(residual.astype(np.float64) ** 2)))
    correction_peak = float(np.max(np.abs(residual)))
    corrected_peak = float(np.max(np.abs(corrected_other)))
    if not math.isfinite(corrected_peak) or corrected_peak > MAXIMUM_PRE_ATTENUATION_PEAK:
        raise ValueError("reconstruction-corrected other exceeds the peak bound")
    peaks.append(corrected_peak)
    maximum_peak = max(peaks)
    gain = min(1.0, TARGET_PEAK / maximum_peak) if maximum_peak else 1.0

    source_int = quantize_pcm24(source * gain, np=np)
    vocals_int = quantize_pcm24(native["vocals"] * gain, np=np)
    drums_int = quantize_pcm24(native["drums"] * gain, np=np)
    bass_int = quantize_pcm24(native["bass"] * gain, np=np)
    other_wide = (
        source_int.astype(np.int64)
        - vocals_int.astype(np.int64)
        - drums_int.astype(np.int64)
        - bass_int.astype(np.int64)
    )
    if int(other_wide.min()) < PCM24_MIN or int(other_wide.max()) > PCM24_MAX:
        raise ValueError("shared attenuation left grouped other outside PCM24")
    other_int = other_wide.astype(np.int32)
    reconstruction_wide = (
        vocals_int.astype(np.int64)
        + drums_int.astype(np.int64)
        + bass_int.astype(np.int64)
        + other_int.astype(np.int64)
    )
    error = np.abs(source_int.astype(np.int64) - reconstruction_wide)
    maximum_error_lsb = int(error.max())
    if maximum_error_lsb > 2:
        raise ValueError("persisted core-four stems exceed reconstruction tolerance")
    reconstruction_int = reconstruction_wide.astype(np.int32)

    paths = {
        "source_reference": destination / "SOURCE/source-reference.wav",
        "vocals": destination / "STEMS/vocals.wav",
        "drums": destination / "STEMS/drums.wav",
        "bass": destination / "STEMS/bass.wav",
        "other": destination / "STEMS/other.wav",
        "reconstruction_check": destination / "AUDIO/reconstruction-check.wav",
    }
    arrays = {
        "source_reference": source_int,
        "vocals": vocals_int,
        "drums": drums_int,
        "bass": bass_int,
        "other": other_int,
        "reconstruction_check": reconstruction_int,
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("core-four worker output path already exists")
    outputs = {
        role: write_pcm24_integers(paths[role], arrays[role], np=np)
        for role in paths
    }
    return {
        "outputs": outputs,
        "level_management": {
            "policy": "one_shared_linear_attenuation_with_pcm24_headroom",
            "original_maximum_absolute_peak": maximum_peak,
            "shared_linear_gain": gain,
            "target_peak": TARGET_PEAK,
        },
        "native_other_correction": {
            "equation": "corrected_other = native_other + source_minus_sum_of_native_estimates",
            "measurement_point": "native float32 estimates before shared attenuation",
            "rms": correction_rms,
            "peak": correction_peak,
            "used_for_separation_accuracy_claim": False,
        },
        "additive_accounting": {
            "equation": "source_reference = vocals + drums + bass + other in PCM24",
            "maximum_absolute_error_lsb": maximum_error_lsb,
            "tolerance_lsb": 2,
            "passed": True,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    spec = separation_profile(CORE_FOUR_PROFILE_ID)
    _validate_platform()
    packages = {
        name: importlib.metadata.version(name) for name in spec.packages()
    }
    if packages != dict(spec.packages()):
        raise RuntimeError("core-four runtime package identity differs")
    if importlib.util.find_spec("torch") is not None:
        raise RuntimeError("core-four inference runtime must not contain PyTorch")
    if args.network_denial_enforced is not True:
        raise RuntimeError("core-four worker requires coordinator network denial")

    source_path = args.source.expanduser().absolute()
    destination = args.destination.expanduser().absolute()
    result_path = args.result.expanduser().absolute()
    model_root = args.model_root.expanduser().absolute()
    if result_path.parent != destination:
        raise ValueError("worker result must be directly inside destination")
    if not source_path.is_file() or not model_root.is_dir():
        raise FileNotFoundError("core-four source or explicit local model root is missing")
    weights = model_root / "htdemucs.safetensors"
    config = model_root / "htdemucs_config.json"
    weights_identity = _verified_file(weights, spec.artifact("weights"))
    config_identity = _verified_file(config, spec.artifact("config"))
    segment_seconds = _configured_segment_seconds(config)
    if (model_root / "htdemucs_mlx.pkl").exists():
        raise ValueError("unapproved first-run conversion artifact is present")
    source_hash = _sha256(source_path)

    import mlx.core as mx
    import numpy as np

    from demucs_mlx.apply_mlx import apply_model
    from demucs_mlx.mlx_convert import load_mlx_model

    source = read_canonical_source(source_path, np=np)
    reference = source.mean(axis=1, dtype=np.float32)
    mean = np.float32(reference.mean(dtype=np.float64))
    standard_deviation = np.float32(reference.std(dtype=np.float64))
    if not math.isfinite(float(standard_deviation)) or standard_deviation <= 0:
        raise ValueError("core-four source has no separable signal variance")
    normalized = np.ascontiguousarray(
        ((source.T - mean) / standard_deviation)[None], dtype=np.float32
    )

    mx.reset_peak_memory()
    load_started = time.perf_counter()
    model = load_mlx_model(
        "htdemucs", cache_dir=str(model_root), auto_convert=False, verbose=False
    )
    load_seconds = time.perf_counter() - load_started
    if (
        tuple(model.sources) != MODEL_SOURCE_ORDER
        or int(model.samplerate) != SAMPLE_RATE
        or int(model.audio_channels) != CHANNELS
    ):
        raise ValueError("loaded model role or clock contract differs")
    if hasattr(model, "eval"):
        model.eval()
    inference_started = time.perf_counter()
    estimates_mx = apply_model(
        model,
        mx.array(normalized),
        shifts=1,
        seed=0,
        split=True,
        overlap=0.25,
        progress=False,
        num_workers=0,
        segment=segment_seconds,
        batch_size=1,
    )
    mx.eval(estimates_mx)
    inference_seconds = time.perf_counter() - inference_started
    raw = np.asarray(estimates_mx[0])
    if raw.shape != (len(MODEL_SOURCE_ORDER), CHANNELS, len(source)):
        raise ValueError("loaded model output geometry differs")
    estimates = {
        role: np.ascontiguousarray(
            raw[index].T * standard_deviation + mean, dtype=np.float32
        )
        for index, role in enumerate(MODEL_SOURCE_ORDER)
    }
    peak_memory = int(mx.get_peak_memory())
    if peak_memory > MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES:
        raise MemoryError("core-four inference exceeded the 12 GiB memory ceiling")
    persistence = persist_core_four(source, estimates, destination, np=np)
    if (
        _sha256(source_path) != source_hash
        or _sha256(weights) != weights_identity["sha256"]
        or _sha256(config) != config_identity["sha256"]
    ):
        raise ValueError("core-four input or model artifact changed during inference")

    elapsed = time.perf_counter() - started
    document: dict[str, Any] = {
        "schema": WORKER_SCHEMA,
        "status": "complete_unreviewed",
        "profile_id": spec.profile_id,
        "roles": list(PERSISTED_ROLE_ORDER),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "frames": len(source),
        "duration_seconds": len(source) / SAMPLE_RATE,
        "inference": dict(spec.inference_settings),
        "model": {
            "model_id": spec.model_id,
            "model_revision": spec.model_revision,
            "weights_sha256": weights_identity["sha256"],
            "config_sha256": config_identity["sha256"],
            "source_order": list(MODEL_SOURCE_ORDER),
            "segment_config_value": "39/5",
            "auto_convert": False,
            "named_or_network_model_resolution": False,
        },
        "runtime": {
            "backend": spec.backend,
            "source_revision": spec.runtime_source_revision,
            "wheel_sha256": spec.runtime_wheel_sha256,
            "packages": packages,
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "device": "mlx-gpu",
            "pytorch_present": False,
            "network_denial_enforced": True,
            "network_used": False,
        },
        "resources": {
            "peak_unified_memory_bytes": peak_memory,
            "maximum_peak_unified_memory_bytes": MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
            "maximum_resident_set_size_native_units": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            ),
            "model_load_seconds": load_seconds,
            "inference_seconds": inference_seconds,
        },
        "source_unchanged": True,
        "model_artifacts_unchanged": True,
        "elapsed_seconds": elapsed,
        **persistence,
    }
    result_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return document


def _validate_platform() -> None:
    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("core-four worker requires macOS on Apple silicon")
    if sys.version_info[:2] not in {(3, 12), (3, 13)}:
        raise RuntimeError("core-four worker requires Python 3.12 or 3.13")


def _verified_file(path: Path, artifact: Any) -> dict[str, Any]:
    attached = path.lstat()
    if path.is_symlink() or not path.is_file() or attached.st_nlink != 1:
        raise ValueError(f"model artifact must be a single-link regular file: {path}")
    digest = _sha256(path)
    if attached.st_size != artifact.bytes or digest != artifact.sha256:
        raise ValueError(f"model artifact identity differs: {path}")
    return {"bytes": attached.st_size, "sha256": digest}


def _configured_segment_seconds(path: Path) -> float:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        value = document["kwargs"]["segment"]
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("core-four pinned segment configuration is invalid") from exc
    if value != "39/5":
        raise ValueError("core-four pinned segment configuration differs")
    segment = Fraction(value)
    if segment != Fraction(39, 5):
        raise ValueError("core-four pinned segment fraction differs")
    return float(segment)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--network-denial-enforced", action="store_true")
    return parser


def main() -> int:
    run(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
