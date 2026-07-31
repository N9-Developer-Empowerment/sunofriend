"""Isolated MLX worker for private same-checkpoint Demucs parity.

This worker never resolves a named model and never calls demucs-mlx's cache or
download path.  It hashes the caller-supplied official PyTorch checkpoint,
deserialises that exact file, converts the loaded model to MLX in memory and
runs only the request-bound audio excerpts.  It is private development code,
not a public separator backend.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import resource
import stat
import sys
import time
from pathlib import Path
from typing import Any, Mapping


REQUEST_SCHEMA = "sunofriend.private-demucs-mlx-parity-request.v1"
RESULT_SCHEMA = "sunofriend.private-demucs-mlx-parity-worker-result.v1"
MODEL_VARIANT = "htdemucs_6s"
MODEL_SIGNATURE = "5c90dfd2"
CHECKPOINT_SHA256 = (
    "34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd"
)
MODEL_SOURCE_ORDER = ("drums", "bass", "other", "vocals", "guitar", "piano")
TARGETS = ("bass", "drums", "guitar", "other", "piano", "vocals")
EXACT_PACKAGES = {
    "demucs": "4.0.1",
    "demucs-mlx": "1.4.4",
    "mlx": "0.31.2",
    "mlx-audio-io": "1.3.11",
    "mlx-metal": "0.31.2",
    "mlx-spectro": "0.7.0",
    "torch": "2.13.0",
}
_CASE_ID = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--arrays-root", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)

    request_path = _regular_file(Path(args.request), "request")
    arrays_root = _empty_directory(Path(args.arrays_root), "arrays root")
    result_path = Path(args.result).expanduser().absolute()
    if result_path.exists() or result_path.is_symlink():
        raise FileExistsError(f"result already exists: {result_path}")

    request = json.loads(request_path.read_text(encoding="utf-8"))
    _validate_request(request)
    checkpoint = _regular_file(
        Path(request["model"]["checkpoint_path"]), "Demucs checkpoint"
    )
    checkpoint_hash = _sha256(checkpoint)
    if checkpoint_hash != request["model"]["checkpoint_sha256"]:
        raise ValueError("checkpoint changed after the parity request was written")
    if checkpoint_hash != CHECKPOINT_SHA256:
        raise ValueError("checkpoint is not the pinned htdemucs_6s checkpoint")

    package_versions = _installed_versions()
    mismatches = {
        name: {"expected": expected, "actual": package_versions.get(name)}
        for name, expected in EXACT_PACKAGES.items()
        if package_versions.get(name) != expected
    }
    if mismatches:
        raise ValueError(f"MLX parity package versions are not exact: {mismatches}")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("MLX parity v1 requires Apple-silicon macOS")

    # The official .th file is a pickle-backed checkpoint.  No import capable
    # of deserialising it happens before the complete pinned hash matches.
    import numpy as np
    import soundfile
    import torch
    from demucs.states import load_model

    torch.set_num_threads(1)
    torch.manual_seed(0)
    load_started = time.monotonic()
    model_package = torch.load(checkpoint, map_location="cpu", weights_only=False)
    torch_model = load_model(model_package)
    torch_model.to("cpu")
    torch_model.eval()
    load_seconds = time.monotonic() - load_started
    if tuple(torch_model.sources) != MODEL_SOURCE_ORDER:
        raise ValueError(f"unexpected Demucs source roles: {torch_model.sources}")
    if int(torch_model.samplerate) != 44_100:
        raise ValueError("pinned Demucs model sample rate changed")

    # Convert the already verified in-memory model directly.  Deliberately do
    # not import or call get_mlx_model(), get_model() or any model-cache API.
    import mlx.core as mx
    from demucs_mlx.apply_mlx import apply_model
    from demucs_mlx.mlx_convert import convert_single_model

    mx.set_default_device(mx.gpu)
    conversion_started = time.monotonic()
    mlx_model = convert_single_model(torch_model, verbose=False)
    if hasattr(mlx_model, "eval"):
        mlx_model.eval()
    conversion_seconds = time.monotonic() - conversion_started
    if tuple(mlx_model.sources) != MODEL_SOURCE_ORDER:
        raise ValueError("converted MLX model source order changed")
    del torch_model, model_package
    gc.collect()

    cases_result: dict[str, Any] = {}
    for position, case in enumerate(request["cases"]):
        case_id = str(case["case_id"])
        source_path = _regular_file(Path(case["source_path"]), "source excerpt")
        source_hash = _sha256(source_path)
        if source_hash != case["source_sha256"]:
            raise ValueError(f"{case_id} source changed after request creation")
        source, sample_rate = soundfile.read(
            source_path, dtype="float32", always_2d=True
        )
        expected_shape = (int(case["frames"]), int(case["channels"]))
        if sample_rate != 44_100 or source.shape != expected_shape:
            raise ValueError(f"{case_id} source geometry changed")
        if not np.all(np.isfinite(source)):
            raise ValueError(f"{case_id} source contains non-finite samples")

        original_channels = int(source.shape[1])
        inference_source = source
        if original_channels == 1:
            inference_source = np.repeat(source, 2, axis=1)
        waveform = torch.from_numpy(inference_source.T.copy())
        reference = waveform.mean(0)
        mean = reference.mean()
        std = reference.std()
        if not torch.isfinite(std) or float(std) <= 0:
            raise ValueError(f"{case_id} source has no usable variance")
        normalized = ((waveform - mean) / std).numpy()
        mix = mx.array(normalized[None])

        inference_started = time.monotonic()
        estimates_mx = apply_model(
            mlx_model,
            mix,
            shifts=0,
            split=True,
            overlap=float(request["inference"]["overlap"]),
            progress=False,
            num_workers=0,
            batch_size=int(request["inference"]["batch_size"]),
            seed=0,
        )
        mx.eval(estimates_mx)
        inference_seconds = time.monotonic() - inference_started
        raw = np.asarray(estimates_mx[0])
        mean_value = np.float32(mean.item())
        std_value = np.float32(std.item())

        case_dir = arrays_root / case_id
        case_dir.mkdir(mode=0o700)
        arrays: dict[str, Any] = {}
        for index, role in enumerate(MODEL_SOURCE_ORDER):
            estimate = (raw[index].T * std_value + mean_value).astype("float32")
            if original_channels == 1:
                estimate = estimate.mean(axis=1, keepdims=True, dtype="float32")
            if estimate.shape != source.shape or not np.all(np.isfinite(estimate)):
                raise ValueError(f"{case_id} {role} MLX estimate is invalid")
            path = case_dir / f"{role}.float32.npy"
            _write_array(path, estimate, np=np)
            arrays[role] = _array_evidence(path, estimate, np=np)

        cases_result[case_id] = {
            "source_sha256": source_hash,
            "frames": int(source.shape[0]),
            "channels": int(source.shape[1]),
            "sample_rate": sample_rate,
            "run_position": position + 1,
            "inference_seconds": round(inference_seconds, 6),
            "arrays": arrays,
            "source_unchanged_after_inference": _sha256(source_path) == source_hash,
        }

    result = {
        "schema": RESULT_SCHEMA,
        "status": "complete",
        "backend": "demucs-mlx",
        "model_variant": MODEL_VARIANT,
        "model_signature": MODEL_SIGNATURE,
        "checkpoint_sha256": checkpoint_hash,
        "checkpoint_hash_verified_before_deserialisation": True,
        "checkpoint_unchanged_after_inference": _sha256(checkpoint)
        == checkpoint_hash,
        "packages": package_versions,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "device": "mlx-gpu",
        },
        "targets": list(TARGETS),
        "model_source_order": list(MODEL_SOURCE_ORDER),
        "model_load_seconds": round(load_seconds, 6),
        "in_memory_conversion_seconds": round(conversion_seconds, 6),
        "conversion": {
            "source": "caller-supplied hash-pinned PyTorch checkpoint",
            "named_model_resolution_called": False,
            "model_cache_api_called": False,
            "converted_weight_cache_written": False,
        },
        "inference": dict(request["inference"]),
        "cases": cases_result,
        "maximum_resident_set_size_native_units": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ),
        "resource_platform": sys.platform,
        "effects": {
            "network_denial_enforced": False,
            "network_attempt_observation_available": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "public_result": False,
        },
    }
    _write_json(result_path, result)
    print(json.dumps(result, sort_keys=True))
    return 0


def _validate_request(request: Mapping[str, Any]) -> None:
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("unsupported MLX parity request schema")
    if request.get("backend") != "demucs-mlx":
        raise ValueError("MLX parity backend must be demucs-mlx")
    model = request.get("model")
    inference = request.get("inference")
    cases = request.get("cases")
    runtime = request.get("runtime")
    if not all(isinstance(value, Mapping) for value in (model, inference, runtime)):
        raise ValueError("model, runtime and inference must be objects")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 8:
        raise ValueError("MLX parity requires 1-8 cases")
    if model.get("variant") != MODEL_VARIANT:
        raise ValueError("MLX parity model variant changed")
    if model.get("signature") != MODEL_SIGNATURE:
        raise ValueError("MLX parity model signature changed")
    if model.get("checkpoint_sha256") != CHECKPOINT_SHA256:
        raise ValueError("MLX parity checkpoint hash is not pinned")
    checkpoint = Path(str(model.get("checkpoint_path", "")))
    if not checkpoint.is_absolute() or not checkpoint.is_file():
        raise ValueError("checkpoint_path must be an existing absolute file")
    if runtime.get("packages") != EXACT_PACKAGES:
        raise ValueError("MLX parity runtime package contract changed")
    if runtime.get("conversion") != "verified-local-checkpoint-in-memory-only":
        raise ValueError("MLX parity conversion contract changed")
    if inference != {
        "device": "mlx-gpu",
        "shifts": 0,
        "overlap": inference.get("overlap"),
        "split": True,
        "num_workers": 0,
        "batch_size": 1,
    }:
        raise ValueError("MLX parity inference settings are not exact")
    overlap = inference.get("overlap")
    if type(overlap) not in (int, float) or not math.isfinite(float(overlap)):
        raise ValueError("MLX parity overlap must be finite")
    if not 0 <= float(overlap) < 1:
        raise ValueError("MLX parity overlap is outside the supported range")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("MLX parity case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
            raise ValueError("MLX parity case_id is invalid")
        if case_id in seen:
            raise ValueError("MLX parity case_id must be unique")
        seen.add(case_id)
        source = Path(str(case.get("source_path", "")))
        if not source.is_absolute() or not source.is_file():
            raise ValueError("source_path must be an existing absolute file")
        sha256 = case.get("source_sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("MLX parity source hash is invalid")
        if case.get("sample_rate") != 44_100:
            raise ValueError("MLX parity source must be 44100 Hz")
        if case.get("channels") not in (1, 2):
            raise ValueError("MLX parity source must be mono or stereo")
        frames = case.get("frames")
        if type(frames) is not int or not 1 <= frames <= 30 * 44_100:
            raise ValueError("MLX parity source frame count is invalid")


def _installed_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in EXACT_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _regular_file(path: Path, label: str) -> Path:
    path = path.expanduser().absolute()
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} must be a regular non-link file")
    if details.st_size <= 0:
        raise ValueError(f"{label} must not be empty")
    return path


def _empty_directory(path: Path, label: str) -> Path:
    path = path.expanduser().absolute()
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise ValueError(f"{label} must be a non-link directory")
    if any(path.iterdir()):
        raise ValueError(f"{label} must be empty")
    return path


def _write_array(path: Path, value: Any, *, np: Any) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"model array already exists: {path.name}")
    with path.open("xb") as handle:
        np.save(handle, value, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _array_evidence(path: Path, value: Any, *, np: Any) -> dict[str, Any]:
    return {
        "file": path.name,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "minimum": float(np.min(value)),
        "maximum": float(np.max(value)),
        "rms": float(np.sqrt(np.mean(np.square(value.astype("float64"))))),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    path.chmod(0o600)


if __name__ == "__main__":
    raise SystemExit(main())


__all__: tuple[str, ...] = ()
