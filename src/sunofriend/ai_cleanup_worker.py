"""Isolated Demucs worker for the experimental learned-cleanup boundary."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any, Mapping


REQUEST_SCHEMA = "sunofriend.ai-cleanup-request.v1"
RESULT_SCHEMA = "sunofriend.ai-cleanup-worker-result.v1"
EXPECTED_PACKAGE_VERSION = "4.0.1"
EXPECTED_MODEL_VARIANT = "htdemucs"
EXPECTED_MODEL_SIGNATURE = "955717e8"
EXPECTED_CHECKPOINT_SHA256 = (
    "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
)
TARGETS = ("bass", "drums", "other", "vocals")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--target-array", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)

    request_path = Path(args.request).expanduser().absolute()
    target_array_path = Path(args.target_array).expanduser().absolute()
    result_path = Path(args.result).expanduser().absolute()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    _validate_request(request)

    source_path = Path(request["source_excerpt"]["path"])
    checkpoint_path = Path(request["model"]["checkpoint_path"])
    source_hash = _sha256(source_path)
    checkpoint_hash = _sha256(checkpoint_path)
    if source_hash != request["source_excerpt"]["sha256"]:
        raise ValueError("source excerpt changed after the request was written")
    if checkpoint_hash != request["model"]["checkpoint_sha256"]:
        raise ValueError("checkpoint changed after the request was written")
    if checkpoint_hash != EXPECTED_CHECKPOINT_SHA256:
        raise ValueError("checkpoint is not the pinned official htdemucs model")

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
    if list(model.sources) != ["drums", "bass", "other", "vocals"]:
        raise ValueError(f"unexpected htdemucs source roles: {model.sources}")

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
    separated = separated * std + mean
    target_index = list(model.sources).index(request["target"])
    target = separated[target_index].detach().cpu().numpy().T.astype("float32")
    if original_channels == 1:
        target = target.mean(axis=1, keepdims=True, dtype="float32")
    if target.shape != source.shape:
        raise ValueError(f"target shape {target.shape} does not match {source.shape}")
    if not np.all(np.isfinite(target)):
        raise ValueError("model target contains non-finite samples")

    target_array_path.parent.mkdir(parents=True, exist_ok=True)
    with target_array_path.open("wb") as handle:
        np.save(handle, target, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    result: dict[str, Any] = {
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
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"request schema must be {REQUEST_SCHEMA}")
    if request.get("backend") != "demucs":
        raise ValueError("worker backend must be demucs")
    model = request.get("model")
    source = request.get("source_excerpt")
    inference = request.get("inference")
    if not isinstance(model, Mapping) or not isinstance(source, Mapping):
        raise ValueError("request model and source_excerpt must be objects")
    if not isinstance(inference, Mapping):
        raise ValueError("request inference must be an object")
    if model.get("variant") != EXPECTED_MODEL_VARIANT:
        raise ValueError("request model variant is not htdemucs")
    if model.get("signature") != EXPECTED_MODEL_SIGNATURE:
        raise ValueError("request model signature is not pinned")
    if model.get("package_version") != EXPECTED_PACKAGE_VERSION:
        raise ValueError("request demucs package version is not pinned")
    checkpoint = Path(str(model.get("checkpoint_path", "")))
    audio = Path(str(source.get("path", "")))
    if not checkpoint.is_absolute() or not checkpoint.is_file():
        raise ValueError("checkpoint_path must be an existing absolute file")
    if not audio.is_absolute() or not audio.is_file():
        raise ValueError("source excerpt path must be an existing absolute file")
    if model.get("checkpoint_sha256") != EXPECTED_CHECKPOINT_SHA256:
        raise ValueError("request checkpoint hash is not the pinned htdemucs hash")
    if request.get("target") not in TARGETS:
        raise ValueError("unsupported target role")
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
