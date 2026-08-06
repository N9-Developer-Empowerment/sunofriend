"""Offline fixed-profile worker for the pinned official SCNet release.

The worker is intentionally narrower than upstream inference helpers. It loads
only the installed, hash-bound release source and checkpoint, accepts canonical
PCM24 stereo 44.1 kHz input, applies one deterministic shift with fixed split
settings, and delegates persistence to Sunofriend's exact reconstruction
accounting contract.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import resource
import sys
import time
from typing import Any, Mapping, Sequence

from sunofriend.separation_demucs_mlx_worker import (
    CHANNELS,
    MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
    MODEL_SOURCE_ORDER,
    PERSISTED_ROLE_ORDER,
    SAMPLE_RATE,
    WORKER_SCHEMA,
    _sha256,
    persist_core_four,
    read_canonical_source,
)
from sunofriend.separation_profiles import (
    SCNET_RELEASE_PROFILE_ID,
    separation_profile,
)
from sunofriend.separation_scnet_compatibility import (
    EXPECTED_ARTIFACTS,
    EXPECTED_PARAMETER_COUNT,
    EXPECTED_STATE_BYTES,
    _load_release_module,
    _normalize_uniform_prefix,
    _state_mapping,
    _verify_artifacts,
)


SEGMENT_SECONDS = 11
SEGMENT_FRAMES = SAMPLE_RATE * SEGMENT_SECONDS
OVERLAP = 0.25
SHIFT_SECONDS = 0.5
SHIFT_FRAMES = int(SAMPLE_RATE * SHIFT_SECONDS)
SEED = 0
MAXIMUM_SECONDS_PER_AUDIO_MINUTE = 120.0
MAXIMUM_SECONDS_PER_SONG = 900.0


def split_offsets(length: int) -> tuple[int, ...]:
    """Return the immutable sequential chunk offsets for a source length."""

    if length <= 0:
        raise ValueError("SCNet split length must be positive")
    stride = int((1.0 - OVERLAP) * SEGMENT_FRAMES)
    if stride <= 0:
        raise ValueError("SCNet split stride must be positive")
    return tuple(range(0, length, stride))


def _triangular_weight(*, torch: Any) -> Any:
    first = torch.arange(1, SEGMENT_FRAMES // 2 + 1, dtype=torch.float32)
    second = torch.arange(
        SEGMENT_FRAMES - SEGMENT_FRAMES // 2,
        0,
        -1,
        dtype=torch.float32,
    )
    weight = torch.cat((first, second))
    return weight / weight.max()


def _apply_split(model: Any, mix: Any, *, torch: Any) -> tuple[Any, int]:
    """Apply the model sequentially with fixed chunks and overlap accounting."""

    if tuple(mix.shape[:2]) != (1, CHANNELS) or mix.ndim != 3:
        raise ValueError("SCNet normalized input geometry differs")
    length = int(mix.shape[-1])
    output = torch.zeros(
        (1, len(MODEL_SOURCE_ORDER), CHANNELS, length),
        dtype=mix.dtype,
        device=mix.device,
    )
    sum_weight = torch.zeros(length, dtype=mix.dtype, device=mix.device)
    weight = _triangular_weight(torch=torch).to(device=mix.device, dtype=mix.dtype)
    forward_passes = 0
    for offset in split_offsets(length):
        chunk_length = min(SEGMENT_FRAMES, length - offset)
        chunk = mix[..., offset : offset + chunk_length]
        if chunk_length < SEGMENT_FRAMES:
            chunk = torch.nn.functional.pad(
                chunk, (0, SEGMENT_FRAMES - chunk_length)
            )
        estimate = model(chunk)
        forward_passes += 1
        expected_shape = (
            1,
            len(MODEL_SOURCE_ORDER),
            CHANNELS,
            SEGMENT_FRAMES,
        )
        if tuple(estimate.shape) != expected_shape:
            raise ValueError(
                "SCNet chunk output geometry differs: "
                f"expected {expected_shape!r}, got {tuple(estimate.shape)!r}"
            )
        chunk_weight = weight[:chunk_length]
        output[..., offset : offset + chunk_length] += (
            estimate[..., :chunk_length] * chunk_weight
        )
        sum_weight[offset : offset + chunk_length] += chunk_weight
    if bool(torch.any(sum_weight <= 0)):
        raise ValueError("SCNet overlap accounting left uncovered samples")
    return output / sum_weight, forward_passes


def _apply_one_shift(model: Any, mix: Any, *, torch: Any) -> tuple[Any, int, int]:
    """Apply one deterministic upstream-compatible time shift."""

    generator = random.Random(SEED)
    offset = generator.randint(0, SHIFT_FRAMES)
    padded = torch.nn.functional.pad(mix, (SHIFT_FRAMES, SHIFT_FRAMES))
    shifted_length = int(mix.shape[-1]) + SHIFT_FRAMES - offset
    shifted = padded[..., offset : offset + shifted_length]
    estimate, forward_passes = _apply_split(model, shifted, torch=torch)
    crop = SHIFT_FRAMES - offset
    restored = estimate[..., crop : crop + int(mix.shape[-1])]
    if int(restored.shape[-1]) != int(mix.shape[-1]):
        raise ValueError("SCNet shifted output clock differs")
    return restored, offset, forward_passes


def _load_model(root: Path, *, torch: Any, yaml: Any) -> tuple[Any, dict[str, Any]]:
    artifacts = _verify_artifacts(root)
    config = yaml.safe_load(
        (root / "model/scnet-large-config.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(config, Mapping) or not isinstance(config.get("model"), Mapping):
        raise ValueError("SCNet config lacks the reviewed model mapping")
    if config.get("data", {}).get("samplerate") != SAMPLE_RATE:
        raise ValueError("SCNet config sample rate differs")
    if config.get("data", {}).get("channels") != CHANNELS:
        raise ValueError("SCNet config channel count differs")
    if tuple(config["model"].get("sources", ())) != MODEL_SOURCE_ORDER:
        raise ValueError("SCNet config source order differs")
    if config.get("data", {}).get("segment") != SEGMENT_SECONDS:
        raise ValueError("SCNet config segment differs")

    module = _load_release_module(root)
    model = module.SCNet(**dict(config["model"]))
    expected_state = model.state_dict()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    state_bytes = sum(
        value.numel() * value.element_size() for value in expected_state.values()
    )
    if parameter_count != EXPECTED_PARAMETER_COUNT or state_bytes != EXPECTED_STATE_BYTES:
        raise ValueError("SCNet constructed architecture identity differs")
    package = torch.load(
        root / "model/SCNet-large.th",
        map_location="cpu",
        weights_only=True,
        mmap=True,
    )
    state, container, wrapper_cycles = _state_mapping(
        package, tensor_type=torch.Tensor
    )
    normalized, removed_prefix, prefix_cycles = _normalize_uniform_prefix(
        state, set(expected_state)
    )
    if wrapper_cycles + prefix_cycles != 1:
        raise ValueError("SCNet checkpoint remediation identity differs")
    model.load_state_dict(normalized, strict=True)
    model.eval()
    return model, {
        "artifacts": artifacts,
        "checkpoint_container": container,
        "removed_uniform_prefix": removed_prefix,
        "remediation_cycles": wrapper_cycles + prefix_cycles,
        "parameter_count": parameter_count,
        "state_dict_bytes": state_bytes,
    }


def validate_destination_staging(source_path: Path, destination: Path) -> None:
    """Allow only the coordinator's exact canonical input or synthetic evidence."""

    if not destination.exists():
        return
    allowed = {"GROUND-TRUTH", "synthetic-fixture.json"}
    canonical = destination / "TEMP/source-44100-stereo-pcm24.wav"
    if source_path == canonical:
        temporary = destination / "TEMP"
        if (
            temporary.is_symlink()
            or canonical.is_symlink()
            or not canonical.is_file()
            or {entry.name for entry in temporary.iterdir()}
            != {"source-44100-stereo-pcm24.wav"}
        ):
            raise FileExistsError("SCNet coordinator TEMP input contract differs")
        allowed.add("TEMP")
    if {entry.name for entry in destination.iterdir()} - allowed:
        raise FileExistsError("SCNet worker destination contains unexpected files")


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    _validate_platform()
    if args.network_denial_enforced is not True:
        raise RuntimeError("SCNet worker requires coordinator network denial")

    spec = separation_profile(SCNET_RELEASE_PROFILE_ID)
    packages = {name: importlib.metadata.version(name) for name in spec.packages()}
    if packages != dict(spec.packages()):
        raise RuntimeError("SCNet runtime package identity differs")

    source_path = args.source.expanduser().absolute()
    destination = args.destination.expanduser().absolute()
    result_path = args.result.expanduser().absolute()
    model_root = args.model_root.expanduser().absolute()
    if result_path.parent != destination:
        raise ValueError("SCNet worker result must be directly inside destination")
    if not source_path.is_file() or not model_root.is_dir():
        raise FileNotFoundError("SCNet source or explicit local profile root is missing")
    validate_destination_staging(source_path, destination)
    destination.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(source_path)

    import numpy as np
    import torch
    import yaml

    torch.set_grad_enabled(False)
    torch.manual_seed(SEED)
    random.seed(SEED)
    source = read_canonical_source(source_path, np=np)
    source_tensor = torch.from_numpy(np.ascontiguousarray(source.T)).unsqueeze(0)
    mono = source_tensor.mean(dim=1)
    mean = mono.mean()
    standard_deviation = mono.std()
    if not math.isfinite(float(standard_deviation)) or float(standard_deviation) <= 0:
        raise ValueError("SCNet source has no separable signal variance")
    normalized = (source_tensor - mean) / standard_deviation

    load_started = time.perf_counter()
    model, model_receipt = _load_model(model_root, torch=torch, yaml=yaml)
    load_seconds = time.perf_counter() - load_started
    if tuple(model.sources) != MODEL_SOURCE_ORDER or model.audio_channels != CHANNELS:
        raise ValueError("SCNet loaded role or channel contract differs")

    inference_started = time.perf_counter()
    with torch.inference_mode():
        separated, shift_offset, forward_passes = _apply_one_shift(
            model, normalized, torch=torch
        )
    inference_seconds = time.perf_counter() - inference_started
    expected_shape = (
        1,
        len(MODEL_SOURCE_ORDER),
        CHANNELS,
        len(source),
    )
    if tuple(separated.shape) != expected_shape:
        raise ValueError("SCNet final output geometry differs")
    separated = separated * standard_deviation + mean
    raw = separated[0].detach().cpu().numpy()
    estimates = {
        role: np.ascontiguousarray(raw[index].T, dtype=np.float32)
        for index, role in enumerate(MODEL_SOURCE_ORDER)
    }

    peak_memory = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if peak_memory > MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES:
        raise MemoryError("SCNet inference exceeded the 12 GiB memory ceiling")
    persistence = persist_core_four(source, estimates, destination, np=np)

    if _sha256(source_path) != source_hash:
        raise ValueError("SCNet input changed during inference")
    for relative_path, identity in model_receipt["artifacts"].items():
        if _sha256(model_root / relative_path) != identity["sha256"]:
            raise ValueError("SCNet model artifact changed during inference")

    elapsed = time.perf_counter() - started
    duration_seconds = len(source) / SAMPLE_RATE
    runtime_ceiling = min(
        MAXIMUM_SECONDS_PER_SONG,
        MAXIMUM_SECONDS_PER_AUDIO_MINUTE * duration_seconds / 60.0,
    )
    document: dict[str, Any] = {
        "schema": WORKER_SCHEMA,
        "status": "complete_unreviewed",
        "profile_id": spec.profile_id,
        "roles": list(PERSISTED_ROLE_ORDER),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "frames": len(source),
        "duration_seconds": duration_seconds,
        "inference": dict(spec.inference_settings),
        "model": {
            "model_id": spec.model_id,
            "model_revision": spec.model_revision,
            "source_revision": spec.runtime_source_revision,
            "source_order": list(MODEL_SOURCE_ORDER),
            "weights_sha256": EXPECTED_ARTIFACTS["model/SCNet-large.th"][1],
            "config_sha256": EXPECTED_ARTIFACTS[
                "model/scnet-large-config.yaml"
            ][1],
            "checkpoint_container": model_receipt["checkpoint_container"],
            "checkpoint_weights_only": True,
            "checkpoint_mmap": True,
            "checkpoint_local_only": True,
            "strict_state_dict": True,
            "removed_uniform_prefix": model_receipt["removed_uniform_prefix"],
            "compatibility_remediation_cycles": model_receipt[
                "remediation_cycles"
            ],
            "parameter_count": model_receipt["parameter_count"],
            "state_dict_bytes": model_receipt["state_dict_bytes"],
            "named_or_network_model_resolution": False,
        },
        "runtime": {
            "backend": spec.backend,
            "packages": packages,
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "device": "cpu",
            "pytorch_present": True,
            "network_denial_enforced": True,
            "network_used": False,
            "writer_count": 1,
        },
        "determinism": {
            "shifts": 1,
            "seed": SEED,
            "maximum_shift_frames": SHIFT_FRAMES,
            "selected_shift_offset_frames": shift_offset,
            "overlap": OVERLAP,
            "segment_seconds": SEGMENT_SECONDS,
            "segment_frames": SEGMENT_FRAMES,
            "split_offsets": list(split_offsets(len(source) + SHIFT_FRAMES - shift_offset)),
            "forward_passes": forward_passes,
            "batch_size": 1,
            "parallel_workers": 0,
        },
        "resources": {
            "peak_unified_memory_bytes": peak_memory,
            "maximum_peak_unified_memory_bytes": MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
            "model_load_seconds": load_seconds,
            "inference_seconds": inference_seconds,
            "elapsed_seconds": elapsed,
            "maximum_elapsed_seconds": runtime_ceiling,
            "within_runtime_ceiling": elapsed <= runtime_ceiling,
        },
        "source_unchanged": True,
        "model_artifacts_unchanged": True,
        "elapsed_seconds": elapsed,
        **persistence,
    }
    if elapsed > runtime_ceiling:
        raise TimeoutError(
            f"SCNet inference took {elapsed:.3f}s, exceeding the "
            f"{runtime_ceiling:.3f}s resource ceiling"
        )
    result_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return document


def _validate_platform() -> None:
    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("SCNet worker requires macOS on Apple silicon")
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("SCNet worker requires the pinned Python 3.13 runtime")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--network-denial-enforced", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Exception as error:
        print(f"SCNet worker failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MAXIMUM_SECONDS_PER_AUDIO_MINUTE",
    "MAXIMUM_SECONDS_PER_SONG",
    "OVERLAP",
    "SEED",
    "SEGMENT_FRAMES",
    "SEGMENT_SECONDS",
    "SHIFT_FRAMES",
    "main",
    "run",
    "split_offsets",
    "validate_destination_staging",
]
