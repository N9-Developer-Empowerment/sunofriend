"""Offline fixed-profile worker for the core-four PyTorch fallback.

The coordinator launches this process under macOS network denial. The worker
uses only an explicit local demucs-infer repository, never passes the upstream
segment override, and reuses Sunofriend's exact PCM24 accounting contract.
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
from typing import Any

from sunofriend.separation_demucs_mlx_worker import (
    CHANNELS,
    MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
    MODEL_SOURCE_ORDER,
    PERSISTED_ROLE_ORDER,
    SAMPLE_RATE,
    WORKER_SCHEMA,
    _sha256,
    _verified_file,
    persist_core_four,
    read_canonical_source,
)
from sunofriend.separation_profiles import (
    CORE_FOUR_FALLBACK_PROFILE_ID,
    separation_profile,
)


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    spec = separation_profile(CORE_FOUR_FALLBACK_PROFILE_ID)
    _validate_platform()
    packages = {name: importlib.metadata.version(name) for name in spec.packages()}
    if packages != dict(spec.packages()):
        raise RuntimeError("fallback runtime package identity differs")
    if args.network_denial_enforced is not True:
        raise RuntimeError("fallback worker requires coordinator network denial")

    source_path = args.source.expanduser().absolute()
    destination = args.destination.expanduser().absolute()
    result_path = args.result.expanduser().absolute()
    model_root = args.model_root.expanduser().absolute()
    if result_path.parent != destination:
        raise ValueError("worker result must be directly inside destination")
    if not source_path.is_file() or not model_root.is_dir():
        raise FileNotFoundError("fallback source or explicit local model repo is missing")
    weights = model_root / "955717e8-8726e21a.th"
    config = model_root / "htdemucs.yaml"
    weights_identity = _verified_file(weights, spec.artifact("weights"))
    config_identity = _verified_file(config, spec.artifact("config"))
    if config.read_text(encoding="utf-8") != "models: ['955717e8']\n":
        raise ValueError("fallback local model repository binding differs")
    source_hash = _sha256(source_path)

    import numpy as np
    import torch

    from demucs_infer.api import Separator
    from demucs_infer.apply import BagOfModels

    source = read_canonical_source(source_path, np=np)
    source_tensor = torch.from_numpy(np.ascontiguousarray(source.T)).clone()
    random.seed(0)
    torch.manual_seed(0)
    load_started = time.perf_counter()
    separator = Separator(
        model="htdemucs",
        repo=model_root,
        device="cpu",
        shifts=1,
        split=True,
        overlap=0.25,
        segment=None,
        jobs=0,
        progress=False,
    )
    load_seconds = time.perf_counter() - load_started
    model = separator.model
    if not isinstance(model, BagOfModels) or len(model.models) != 1:
        raise ValueError("fallback must load the single htdemucs model bag")
    if (
        tuple(model.sources) != MODEL_SOURCE_ORDER
        or int(model.samplerate) != SAMPLE_RATE
        or int(model.audio_channels) != CHANNELS
    ):
        raise ValueError("fallback model role or clock contract differs")
    native_segments = [submodel.segment for submodel in model.models]
    if any(
        type(value) not in (int, float)
        or not math.isfinite(float(value))
        or float(value) <= 0
        for value in native_segments
    ):
        raise ValueError("fallback model native segment is not finite and numeric")

    inference_started = time.perf_counter()
    with torch.inference_mode():
        restored, separated = separator.separate_tensor(source_tensor, SAMPLE_RATE)
    inference_seconds = time.perf_counter() - inference_started
    if tuple(restored.shape) != (CHANNELS, len(source)):
        raise ValueError("fallback restored source geometry differs")
    if set(separated) != set(MODEL_SOURCE_ORDER):
        raise ValueError("fallback model roles differ from the exact contract")
    estimates = {
        role: np.ascontiguousarray(separated[role].detach().cpu().numpy().T)
        for role in MODEL_SOURCE_ORDER
    }
    peak_memory = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if peak_memory > MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES:
        raise MemoryError("fallback inference exceeded the 12 GiB memory ceiling")
    persistence = persist_core_four(source, estimates, destination, np=np)
    if (
        _sha256(source_path) != source_hash
        or _sha256(weights) != weights_identity["sha256"]
        or _sha256(config) != config_identity["sha256"]
    ):
        raise ValueError("fallback input or model artifact changed during inference")

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
            "native_segments": [float(value) for value in native_segments],
            "segment_verified_numeric": True,
            "segment_override": None,
            "explicit_local_repo": True,
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
            "device": "cpu",
            "pytorch_present": True,
            "network_denial_enforced": True,
            "network_used": False,
        },
        "resources": {
            "peak_unified_memory_bytes": peak_memory,
            "maximum_peak_unified_memory_bytes": MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
            "measurement": "maximum resident set size for CPU-only inference",
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
        raise RuntimeError("fallback worker requires macOS on Apple silicon")
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("fallback worker requires Python 3.13")


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
