"""Isolated Demucs worker for private learned-separation experiments.

The original v1 target/residual request remains supported unchanged. The
separate private multi-source requests run one exact pinned model once and
persist every configured HTDemucs estimate for a parent-owned bake-off.
Neither request is a product admission, publication, selection or promotion
boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any, Mapping


REQUEST_SCHEMA = "sunofriend.ai-cleanup-request.v1"
RESULT_SCHEMA = "sunofriend.ai-cleanup-worker-result.v1"
FOUR_STEM_REQUEST_SCHEMA = "sunofriend.private-ai-separation-request.v1"
FOUR_STEM_RESULT_SCHEMA = "sunofriend.private-ai-separation-worker-result.v1"
SIX_SOURCE_REQUEST_SCHEMA = "sunofriend.private-ai-six-source-separation-request.v1"
SIX_SOURCE_RESULT_SCHEMA = (
    "sunofriend.private-ai-six-source-separation-worker-result.v1"
)
EXPECTED_PACKAGE_VERSION = "4.0.1"
EXPECTED_MODEL_VARIANT = "htdemucs"
EXPECTED_MODEL_SIGNATURE = "955717e8"
EXPECTED_CHECKPOINT_SHA256 = (
    "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
)
TARGETS = ("bass", "drums", "other", "vocals")
MODEL_SOURCE_ORDER = ("drums", "bass", "other", "vocals")
SIX_SOURCE_MODEL_VARIANT = "htdemucs_6s"
SIX_SOURCE_MODEL_SIGNATURE = "5c90dfd2"
SIX_SOURCE_CHECKPOINT_SHA256 = (
    "34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd"
)
SIX_SOURCE_TARGETS = ("bass", "drums", "guitar", "other", "piano", "vocals")
SIX_SOURCE_MODEL_ORDER = ("drums", "bass", "other", "vocals", "piano", "guitar")


def _model_configuration(schema: str) -> dict[str, Any]:
    if schema == SIX_SOURCE_REQUEST_SCHEMA:
        return {
            "variant": SIX_SOURCE_MODEL_VARIANT,
            "signature": SIX_SOURCE_MODEL_SIGNATURE,
            "checkpoint_sha256": SIX_SOURCE_CHECKPOINT_SHA256,
            "targets": SIX_SOURCE_TARGETS,
            "source_order": SIX_SOURCE_MODEL_ORDER,
            "result_schema": SIX_SOURCE_RESULT_SCHEMA,
        }
    if schema in {REQUEST_SCHEMA, FOUR_STEM_REQUEST_SCHEMA}:
        return {
            "variant": EXPECTED_MODEL_VARIANT,
            "signature": EXPECTED_MODEL_SIGNATURE,
            "checkpoint_sha256": EXPECTED_CHECKPOINT_SHA256,
            "targets": TARGETS,
            "source_order": MODEL_SOURCE_ORDER,
            "result_schema": FOUR_STEM_RESULT_SCHEMA,
        }
    raise ValueError("unknown private Demucs request schema")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--target-array")
    parser.add_argument("--stems-dir")
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)

    request_path = Path(args.request).expanduser().absolute()
    result_path = Path(args.result).expanduser().absolute()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    _validate_request(request)
    multi_source = request["schema"] in {
        FOUR_STEM_REQUEST_SCHEMA,
        SIX_SOURCE_REQUEST_SCHEMA,
    }
    configuration = _model_configuration(request["schema"])
    if multi_source:
        if args.target_array is not None or args.stems_dir is None:
            raise ValueError(
                "multi-source requests require --stems-dir and forbid "
                "--target-array"
            )
        stems_dir = Path(args.stems_dir).expanduser().absolute()
        target_array_path = None
        _validate_stems_dir(stems_dir)
    else:
        if args.target_array is None or args.stems_dir is not None:
            raise ValueError(
                "target requests require --target-array and forbid --stems-dir"
            )
        target_array_path = Path(args.target_array).expanduser().absolute()
        stems_dir = None

    source_path = Path(request["source_excerpt"]["path"])
    checkpoint_path = Path(request["model"]["checkpoint_path"])
    source_hash = _sha256(source_path)
    checkpoint_hash = _sha256(checkpoint_path)
    if source_hash != request["source_excerpt"]["sha256"]:
        raise ValueError("source excerpt changed after the request was written")
    if checkpoint_hash != request["model"]["checkpoint_sha256"]:
        raise ValueError("checkpoint changed after the request was written")
    if checkpoint_hash != configuration["checkpoint_sha256"]:
        raise ValueError("checkpoint is not the pinned configured Demucs model")

    # PyTorch checkpoints use pickle. Import and deserialise only after the
    # complete official checkpoint hash has matched the pinned value above.
    import numpy as np
    import soundfile
    import torch
    from demucs.apply import apply_model
    from demucs.states import load_model

    package_version = importlib.metadata.version("demucs")
    if package_version != EXPECTED_PACKAGE_VERSION:
        raise ValueError(
            f"demucs package must be {EXPECTED_PACKAGE_VERSION}, got {package_version}"
        )
    source, sample_rate = soundfile.read(source_path, dtype="float32", always_2d=True)
    if sample_rate != int(request["source_excerpt"]["sample_rate"]):
        raise ValueError("source sample rate changed after request validation")
    if source.shape != (
        int(request["source_excerpt"]["frames"]),
        int(request["source_excerpt"]["channels"]),
    ):
        raise ValueError("source shape changed after request validation")
    if not np.all(np.isfinite(source)):
        raise ValueError("source excerpt contains non-finite samples")

    torch.set_num_threads(1)
    torch.manual_seed(0)
    model_package = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = load_model(model_package)
    model.to("cpu")
    model.eval()
    if getattr(model, "samplerate", None) != sample_rate:
        raise ValueError(
            f"model sample rate is {getattr(model, 'samplerate', None)}, "
            f"source is {sample_rate}"
        )
    source_order = tuple(configuration["source_order"])
    if tuple(model.sources) != source_order:
        raise ValueError(f"unexpected Demucs source roles: {model.sources}")

    original_channels = source.shape[1]
    inference_source = source
    if original_channels == 1:
        inference_source = np.repeat(source, 2, axis=1)
    waveform = torch.from_numpy(inference_source.T.copy())
    reference = waveform.mean(0)
    mean = reference.mean()
    std = reference.std()
    if not torch.isfinite(std) or float(std) <= 0:
        raise ValueError("source excerpt has no usable variance")
    normalized = (waveform - mean) / std
    settings = request["inference"]
    inference_started = time.monotonic()
    with torch.inference_mode():
        separated = apply_model(
            model,
            normalized[None],
            device="cpu",
            shifts=0,
            split=True,
            overlap=float(settings["overlap"]),
            progress=False,
            num_workers=0,
        )[0]
    inference_seconds = time.monotonic() - inference_started
    separated = separated * std + mean
    estimates: dict[str, Any] = {}
    for index, role in enumerate(source_order):
        estimate = separated[index].detach().cpu().numpy().T.astype("float32")
        if original_channels == 1:
            estimate = estimate.mean(axis=1, keepdims=True, dtype="float32")
        if estimate.shape != source.shape:
            raise ValueError(
                f"{role} shape {estimate.shape} does not match {source.shape}"
            )
        if not np.all(np.isfinite(estimate)):
            raise ValueError(f"model {role} estimate contains non-finite samples")
        estimates[role] = estimate

    if multi_source:
        assert stems_dir is not None
        arrays: dict[str, dict[str, Any]] = {}
        targets = tuple(configuration["targets"])
        for role in targets:
            path = stems_dir / f"{role}.float32.npy"
            _write_array(path, estimates[role], np=np)
            arrays[role] = _array_evidence(path, estimates[role], np=np)
        result = {
            "schema": configuration["result_schema"],
            "status": "complete",
            "backend": "demucs",
            "package_version": package_version,
            "model_variant": request["model"]["variant"],
            "model_signature": request["model"]["signature"],
            "checkpoint_sha256": checkpoint_hash,
            "source_excerpt_sha256": source_hash,
            "targets": list(targets),
            "arrays": arrays,
            "frames": int(source.shape[0]),
            "channels": int(source.shape[1]),
            "sample_rate": sample_rate,
            "device": "cpu",
            "shifts": 0,
            "overlap": float(settings["overlap"]),
            "model_applications": 1,
            "inference_seconds": round(inference_seconds, 6),
            "maximum_resident_set_size_native_units": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            ),
            "resource_platform": sys.platform,
            "source_unchanged_after_inference": _sha256(source_path) == source_hash,
            "checkpoint_unchanged_after_inference": (
                _sha256(checkpoint_path) == checkpoint_hash
            ),
            "checkpoint_hash_verified_before_deserialisation": True,
            "effects": {
                "network_denial_enforced": False,
                "network_attempt_observation_available": False,
                "automatic_selection": False,
                "automatic_promotion": False,
                "public_result": False,
            },
        }
    else:
        assert target_array_path is not None
        target = estimates[request["target"]]
        target_array_path.parent.mkdir(parents=True, exist_ok=True)
        _write_array(target_array_path, target, np=np)
        result = {
            "schema": RESULT_SCHEMA,
            "status": "complete",
            "backend": "demucs",
            "package_version": package_version,
            "model_variant": request["model"]["variant"],
            "model_signature": request["model"]["signature"],
            "checkpoint_sha256": checkpoint_hash,
            "source_excerpt_sha256": source_hash,
            "target": request["target"],
            "target_array_sha256": _sha256(target_array_path),
            "frames": int(target.shape[0]),
            "channels": int(target.shape[1]),
            "sample_rate": sample_rate,
            "device": "cpu",
            "shifts": 0,
            "overlap": float(settings["overlap"]),
            "minimum": float(np.min(target)),
            "maximum": float(np.max(target)),
            "rms": float(np.sqrt(np.mean(np.square(target.astype("float64"))))),
            "checkpoint_hash_verified_before_deserialisation": True,
        }
    _write_json(result_path, result)
    print(json.dumps(result, sort_keys=True))
    return 0


def _validate_request(request: Mapping[str, Any]) -> None:
    schema = request.get("schema")
    if schema not in {
        REQUEST_SCHEMA,
        FOUR_STEM_REQUEST_SCHEMA,
        SIX_SOURCE_REQUEST_SCHEMA,
    }:
        raise ValueError(
            "request schema must be an exact supported private Demucs schema"
        )
    configuration = _model_configuration(str(schema))
    if request.get("backend") != "demucs":
        raise ValueError("worker backend must be demucs")
    model = request.get("model")
    source = request.get("source_excerpt")
    inference = request.get("inference")
    if not isinstance(model, Mapping) or not isinstance(source, Mapping):
        raise ValueError("request model and source_excerpt must be objects")
    if not isinstance(inference, Mapping):
        raise ValueError("request inference must be an object")
    if model.get("variant") != configuration["variant"]:
        raise ValueError("request model variant is not the configured Demucs model")
    if model.get("signature") != configuration["signature"]:
        raise ValueError("request model signature is not pinned")
    if model.get("package_version") != EXPECTED_PACKAGE_VERSION:
        raise ValueError("request demucs package version is not pinned")
    checkpoint = Path(str(model.get("checkpoint_path", "")))
    audio = Path(str(source.get("path", "")))
    if not checkpoint.is_absolute() or not checkpoint.is_file():
        raise ValueError("checkpoint_path must be an existing absolute file")
    if not audio.is_absolute() or not audio.is_file():
        raise ValueError("source excerpt path must be an existing absolute file")
    if model.get("checkpoint_sha256") != configuration["checkpoint_sha256"]:
        if schema == SIX_SOURCE_REQUEST_SCHEMA:
            raise ValueError(
                "request checkpoint hash is not the pinned htdemucs_6s hash"
            )
        raise ValueError("request checkpoint hash is not the pinned htdemucs hash")
    if schema == REQUEST_SCHEMA:
        if request.get("target") not in TARGETS or "targets" in request:
            raise ValueError("unsupported target role")
    elif (
        request.get("targets") != list(configuration["targets"])
        or "target" in request
    ):
        raise ValueError("multi-source request targets are not exact")
    if source.get("sample_rate") != 44100:
        raise ValueError("htdemucs worker requires 44100 Hz audio")
    if source.get("channels") not in (1, 2):
        raise ValueError("htdemucs worker supports mono or stereo audio")
    if inference.get("device") != "cpu" or inference.get("shifts") != 0:
        raise ValueError("v1 inference must use CPU with zero random shifts")
    if inference.get("split") is not True or inference.get("num_workers") != 0:
        raise ValueError("v1 inference split/worker settings are fixed")
    overlap = float(inference.get("overlap", -1))
    if not 0 <= overlap < 1:
        raise ValueError("inference overlap must be in the range 0 <= overlap < 1")


def _validate_stems_dir(path: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ValueError("stems directory must be an existing non-symlink directory")
    if any(path.iterdir()):
        raise ValueError("stems directory must be empty")


def _write_array(path: Path, value: Any, *, np: Any) -> None:
    if path.exists():
        raise FileExistsError(f"model array already exists: {path.name}")
    with path.open("xb") as handle:
        np.save(handle, value, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())


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
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
