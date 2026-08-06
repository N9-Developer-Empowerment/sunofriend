"""Offline worker for the six-source grouped-other Studio challenger.

The coordinator must launch this file under macOS network denial.  It accepts
only one canonical PCM24 grouped-``other`` parent and persists only the chosen
guitar or disclosed piano-as-keys estimate plus an exact PCM24 residual.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import math
import platform
from pathlib import Path
import resource
import sys
import time
from typing import Any

from sunofriend.separation_demucs_mlx_worker import (
    CHANNELS,
    MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
    PCM24_MAX,
    PCM24_MIN,
    PCM24_SCALE,
    SAMPLE_RATE,
    quantize_pcm24,
    read_canonical_source,
    write_pcm24_integers,
)
from sunofriend.separation_other_refinement_demucs_mlx_candidate import (
    MODEL_SOURCE_ORDER,
    normalize_pinned_six_source_config,
)
from sunofriend.separation_profiles import (
    OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
    separation_profile,
)


WORKER_SCHEMA = "sunofriend.other-refinement-demucs-mlx-worker.v1"
TARGET_MODEL_ROLES = {"guitar": "guitar", "keys": "piano"}
TARGET_PATHS = {"guitar": "STEMS/guitar.wav", "keys": "STEMS/keys.wav"}
MAXIMUM_PRE_PERSISTENCE_PEAK = 4.0


def load_verified_local_model(
    *, weights_path: Path, config_path: Path, spec: Any
) -> tuple[Any, dict[str, Any]]:
    """Construct only the verified local model with one in-memory remediation."""

    weights_identity = _verified_file(weights_path, spec.artifact("weights"))
    config_identity = _verified_file(config_path, spec.artifact("config"))
    immutable_config = json.loads(config_path.read_text(encoding="utf-8"))
    normalized_config = normalize_pinned_six_source_config(immutable_config)
    if _sha256(config_path) != config_identity["sha256"]:
        raise ValueError("six-source config changed during in-memory normalization")

    import mlx.core as mx
    from demucs_mlx.mlx_convert import BagOfModelsMLX, _load_weights_into_model
    from demucs_mlx.mlx_htdemucs import HTDemucsMLX
    from safetensors.mlx import load_file

    signature = inspect.signature(HTDemucsMLX)
    allowed = set(signature.parameters)
    kwargs = normalized_config["kwargs"]
    filtered = {key: value for key, value in kwargs.items() if key in allowed}
    dropped = sorted(set(kwargs) - allowed)
    if dropped:
        raise ValueError(f"six-source config contains unsupported constructor keys: {dropped}")
    model = HTDemucsMLX(*normalized_config["args"], **filtered)

    flat_checkpoint = load_file(str(weights_path))
    if len(flat_checkpoint) != normalized_config["tensor_count"]:
        raise ValueError("six-source checkpoint tensor count differs")
    prefix = "model_0."
    if not flat_checkpoint or any(not key.startswith(prefix) for key in flat_checkpoint):
        raise ValueError("six-source checkpoint key namespace differs")
    flat_model_state = {
        key[len(prefix) :]: value for key, value in flat_checkpoint.items()
    }
    _load_weights_into_model(model, flat_model_state)
    model.eval()
    bag = BagOfModelsMLX([model], normalized_config["weights"])
    if (
        tuple(bag.sources) != MODEL_SOURCE_ORDER
        or int(bag.samplerate) != SAMPLE_RATE
        or int(bag.audio_channels) != CHANNELS
    ):
        raise ValueError("six-source loaded role or clock contract differs")
    mx.eval(model.parameters())
    return bag, {
        "weights": weights_identity,
        "config": config_identity,
        "source_segment_value": immutable_config["kwargs"]["segment"],
        "normalized_segment_seconds": normalized_config["kwargs"]["segment"],
        "normalization_in_memory_only": True,
        "source_artifact_unchanged": _sha256(config_path)
        == config_identity["sha256"],
        "tensor_count": len(flat_checkpoint),
        "auto_convert": False,
        "named_or_network_model_resolution": False,
    }


def persist_target_and_residual(
    *, source: Any, target: Any, target_id: str, destination: Path, np: Any
) -> dict[str, Any]:
    source = np.asarray(source, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    if target.shape != source.shape or not np.all(np.isfinite(target)):
        raise ValueError("refinement target geometry or samples differ")
    peak = float(np.max(np.abs(target)))
    if not math.isfinite(peak) or peak > MAXIMUM_PRE_PERSISTENCE_PEAK:
        raise ValueError("refinement target exceeds the pre-persistence peak bound")

    source_int = quantize_pcm24(source, np=np)
    target_int = quantize_pcm24(target, np=np)
    residual_wide = source_int.astype(np.int64) - target_int.astype(np.int64)
    if int(residual_wide.min()) < PCM24_MIN or int(residual_wide.max()) > PCM24_MAX:
        raise ValueError("exact grouped-other residual is outside PCM24")
    residual_int = residual_wide.astype(np.int32)
    reconstructed = target_int.astype(np.int64) + residual_int.astype(np.int64)
    maximum_error = int(np.max(np.abs(source_int.astype(np.int64) - reconstructed)))
    if maximum_error > 2:
        raise ValueError("refinement outputs exceed the reconstruction tolerance")

    parent_path = destination / "PARENT/other.wav"
    target_path = destination / TARGET_PATHS[target_id]
    residual_path = destination / "STEMS/other-residual.wav"
    if any(path.exists() or path.is_symlink() for path in (parent_path, target_path, residual_path)):
        raise FileExistsError("refinement worker output path already exists")
    outputs = {
        "parent": write_pcm24_integers(parent_path, source_int, np=np),
        "target": write_pcm24_integers(target_path, target_int, np=np),
        "residual": write_pcm24_integers(residual_path, residual_int, np=np),
    }
    target_float = target_int.astype(np.float64) / PCM24_SCALE
    return {
        "outputs": outputs,
        "target_diagnostics": {
            "model_role": TARGET_MODEL_ROLES[target_id],
            "declared_target": target_id,
            "rms": float(np.sqrt(np.mean(np.square(target_float)))),
            "peak": float(np.max(np.abs(target_float))),
            "used_for_automatic_musical_selection": False,
        },
        "additive_accounting": {
            "equation": "parent_other = requested_target + residual in PCM24",
            "maximum_absolute_error_lsb": maximum_error,
            "tolerance_lsb": 2,
            "passed": True,
            "used_for_separation_accuracy_claim": False,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    _validate_platform()
    if args.network_denial_enforced is not True:
        raise RuntimeError("refinement worker requires coordinator network denial")
    target_id = str(args.target)
    if target_id not in TARGET_MODEL_ROLES:
        raise ValueError("refinement target must be guitar or keys")

    spec = separation_profile(OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID)
    packages = {name: importlib.metadata.version(name) for name in spec.packages()}
    if packages != dict(spec.packages()):
        raise RuntimeError("refinement runtime package identity differs")
    if importlib.util.find_spec("torch") is not None:
        raise RuntimeError("refinement inference runtime must not contain PyTorch")

    source_path = args.source.expanduser().absolute()
    destination = args.destination.expanduser().absolute()
    result_path = args.result.expanduser().absolute()
    model_root = args.model_root.expanduser().absolute()
    if result_path.parent != destination or not destination.is_dir():
        raise ValueError("worker result must be directly inside an existing destination")
    if any(destination.iterdir()):
        raise ValueError("refinement worker destination must start empty")
    if not source_path.is_file() or not model_root.is_dir():
        raise FileNotFoundError("refinement source or explicit local model root is missing")
    source_hash = _sha256(source_path)
    weights = model_root / "htdemucs_6s.safetensors"
    config = model_root / "htdemucs_6s_config.json"

    import mlx.core as mx
    import numpy as np
    from demucs_mlx.apply_mlx import apply_model

    source = read_canonical_source(source_path, np=np)
    reference = source.mean(axis=1, dtype=np.float32)
    mean = np.float32(reference.mean(dtype=np.float64))
    standard_deviation = np.float32(reference.std(dtype=np.float64))
    if not math.isfinite(float(standard_deviation)) or standard_deviation <= 0:
        raise ValueError("refinement source has no separable signal variance")
    normalized = np.ascontiguousarray(
        ((source.T - mean) / standard_deviation)[None], dtype=np.float32
    )

    mx.reset_peak_memory()
    load_started = time.perf_counter()
    model, loading = load_verified_local_model(
        weights_path=weights, config_path=config, spec=spec
    )
    load_seconds = time.perf_counter() - load_started
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
        segment=7.8,
        batch_size=1,
    )
    mx.eval(estimates_mx)
    inference_seconds = time.perf_counter() - inference_started
    raw = np.asarray(estimates_mx[0])
    if raw.shape != (len(MODEL_SOURCE_ORDER), CHANNELS, len(source)):
        raise ValueError("six-source model output geometry differs")
    if not np.all(np.isfinite(raw)):
        raise ValueError("six-source model returned non-finite samples")
    if float(np.max(np.abs(raw))) <= 0:
        raise ValueError("all six model roles are silent")
    target_index = MODEL_SOURCE_ORDER.index(TARGET_MODEL_ROLES[target_id])
    target = np.ascontiguousarray(
        raw[target_index].T * standard_deviation + mean, dtype=np.float32
    )

    peak_memory = int(mx.get_peak_memory())
    if peak_memory > MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES:
        raise MemoryError("refinement inference exceeded the 12 GiB memory ceiling")
    persistence = persist_target_and_residual(
        source=source,
        target=target,
        target_id=target_id,
        destination=destination,
        np=np,
    )
    if (
        _sha256(source_path) != source_hash
        or _sha256(weights) != loading["weights"]["sha256"]
        or _sha256(config) != loading["config"]["sha256"]
    ):
        raise ValueError("refinement input or model artifact changed during inference")

    elapsed = time.perf_counter() - started
    document: dict[str, Any] = {
        "schema": WORKER_SCHEMA,
        "status": "complete_unreviewed_no_activation",
        "profile_id": spec.profile_id,
        "target_id": target_id,
        "roles": list(MODEL_SOURCE_ORDER),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "frames": len(source),
        "duration_seconds": len(source) / SAMPLE_RATE,
        "inference": dict(spec.inference_settings),
        "model": {
            "model_id": spec.model_id,
            "model_revision": spec.model_revision,
            "source_order": list(MODEL_SOURCE_ORDER),
            **loading,
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
        "activation": {
            "source_graph_mutated": False,
            "midi_created": False,
            "candidate_selected": False,
        },
        **persistence,
    }
    result_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return document


def _validate_platform() -> None:
    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("refinement worker requires macOS on Apple silicon")
    if sys.version_info[:2] not in {(3, 12), (3, 13)}:
        raise RuntimeError("refinement worker requires Python 3.12 or 3.13")


def _verified_file(path: Path, artifact: Any) -> dict[str, Any]:
    attached = path.lstat()
    if path.is_symlink() or not path.is_file() or attached.st_nlink != 1:
        raise ValueError(f"model artifact must be a single-link regular file: {path}")
    digest = _sha256(path)
    if attached.st_size != artifact.bytes or digest != artifact.sha256:
        raise ValueError(f"model artifact identity differs: {path}")
    return {"bytes": attached.st_size, "sha256": digest}


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
    parser.add_argument("--target", choices=tuple(TARGET_MODEL_ROLES), required=True)
    parser.add_argument("--network-denial-enforced", action="store_true")
    return parser


def main() -> int:
    run(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
