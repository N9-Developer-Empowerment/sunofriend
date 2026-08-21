"""Restricted MusicFM-FMA loading and a synthetic frozen-feature canary."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import random
import re
import socket
import sys
from typing import Any, Iterator, Mapping

from .remix_musicfm_fma_windows_setup import create_windows_asset_manifest
from .source_receipt import canonical_json_bytes, document_sha256


MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA = (
    "sunofriend.remix-musicfm-fma-synthetic-canary-request.v0"
)
MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA = (
    "sunofriend.remix-musicfm-fma-synthetic-canary-result.v0"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAMPLE_RATE = 24_000
_SYNTHETIC_FRAMES = 48_000
_LAYER_INDEX = 7
_FEATURE_DIMENSION = 1_024
_EXPECTED_FEATURE_FRAMES = 50
_CHECKPOINT_SHA256 = "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96"
_BATCH_NORM_COUNTER_KEYS = (
    *(
        f"conv.conv.{layer}.bn{batch_norm}.num_batches_tracked"
        for layer in range(2)
        for batch_norm in range(1, 4)
    ),
    *(
        f"conformer.layers.{layer}.conv_module.batch_norm.num_batches_tracked"
        for layer in range(12)
    ),
)


def create_musicfm_synthetic_canary_request(
    *,
    repository_commit: str,
    setup_receipt_sha256: str,
    setup_receipt_bytes: int,
) -> dict[str, Any]:
    """Create the one-run request; it contains no local path or private data."""

    if not _COMMIT.fullmatch(repository_commit):
        raise ValueError("repository_commit must be a full Git commit")
    if not _SHA256.fullmatch(setup_receipt_sha256):
        raise ValueError("setup receipt SHA-256 is invalid")
    if isinstance(setup_receipt_bytes, bool) or setup_receipt_bytes <= 0:
        raise ValueError("setup receipt byte count must be positive")
    document = _request_values(
        repository_commit=repository_commit,
        setup_receipt_sha256=setup_receipt_sha256,
        setup_receipt_bytes=setup_receipt_bytes,
    )
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_synthetic_canary_request(document)


def validate_musicfm_synthetic_canary_request(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = dict(value)
    commit = str(document.get("repository_commit") or "")
    setup = document.get("setup_receipt")
    if (
        document.get("schema") != MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA
        or not _COMMIT.fullmatch(commit)
        or not isinstance(setup, Mapping)
        or not _SHA256.fullmatch(str(setup.get("sha256") or ""))
        or isinstance(setup.get("bytes"), bool)
        or not isinstance(setup.get("bytes"), int)
        or setup["bytes"] <= 0
    ):
        raise ValueError("invalid MusicFM synthetic canary request")
    expected = _request_values(
        repository_commit=commit,
        setup_receipt_sha256=str(setup["sha256"]),
        setup_receipt_bytes=int(setup["bytes"]),
    )
    expected["document_sha256"] = document_sha256(expected)
    if document != expected:
        raise ValueError("MusicFM synthetic canary request changed")
    return document


def run_musicfm_synthetic_canary(
    request: Mapping[str, Any],
    *,
    runtime_root: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Load pinned weights and extract features from generated audio only."""

    checked = validate_musicfm_synthetic_canary_request(request)
    root = _real_directory(runtime_root, "runtime_root")
    output = Path(out_dir)
    if output.exists() or output.is_symlink():
        raise ValueError("canary output directory must not already exist")
    setup = _verify_setup_receipt(root, checked)
    asset_records = _verify_runtime_assets(root, checked["repository_commit"])

    with _deny_network() as attempts:
        model, torch, loader = _load_restricted_model(root, asset_records)
        device = torch.device("cuda")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the Windows MusicFM canary")
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        model = model.to(device)
        waveform = _synthetic_waveform(torch).to(device)
        with torch.inference_mode():
            first = model.get_latent(waveform, layer_ix=_LAYER_INDEX).float().cpu()
            second = model.get_latent(waveform, layer_ix=_LAYER_INDEX).float().cpu()
    if attempts:
        raise RuntimeError("MusicFM canary attempted network access")
    _validate_feature_tensor(first, torch)
    _validate_feature_tensor(second, torch)
    maximum_repeat_difference = float(torch.max(torch.abs(first - second)).item())
    if maximum_repeat_difference != 0.0:
        raise RuntimeError("MusicFM synthetic feature extraction is not repeatable")

    import numpy as np

    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    first_path = output / "features-run-1.npy"
    second_path = output / "features-run-2.npy"
    np.save(first_path, first.numpy(), allow_pickle=False)
    np.save(second_path, second.numpy(), allow_pickle=False)
    first_path.chmod(0o600)
    second_path.chmod(0o600)
    metrics = {
        "feature_shape": list(first.shape),
        "feature_dtype": "float32",
        "finite": True,
        "feature_frames": int(first.shape[1]),
        "feature_dimension": int(first.shape[2]),
        "feature_rate_hz": first.shape[1] / (_SYNTHETIC_FRAMES / _SAMPLE_RATE),
        "maximum_repeat_difference": maximum_repeat_difference,
        "network_attempts": len(attempts),
    }
    metrics_path = output / "metrics.json"
    metrics_path.write_bytes(canonical_json_bytes(metrics))
    metrics_path.chmod(0o600)
    artifacts = [
        _file_record(first_path, "features_run_1", "application/x-npy"),
        _file_record(second_path, "features_run_2", "application/x-npy"),
        _file_record(metrics_path, "metrics", "application/json"),
    ]
    result = _result_values(
        checked,
        setup=setup,
        loader=loader,
        asset_records=asset_records,
        artifacts=artifacts,
        metrics=metrics,
        torch=torch,
    )
    result["document_sha256"] = document_sha256(result)
    validate_musicfm_synthetic_canary_result(result, checked)
    result_path = output / "result.json"
    result_path.write_bytes(canonical_json_bytes(result))
    result_path.chmod(0o600)
    return result


def validate_musicfm_synthetic_canary_result(
    value: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    checked = validate_musicfm_synthetic_canary_request(request)
    document = dict(value)
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if (
        document.get("schema") != MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA
        or supplied != document_sha256(unsigned)
        or document.get("request_sha256") != checked["document_sha256"]
    ):
        raise ValueError("invalid MusicFM synthetic canary result")
    if set(document) != {
        "schema",
        "status",
        "request_sha256",
        "repository_commit",
        "setup_receipt",
        "checkpoint",
        "loader",
        "synthetic_input",
        "metrics",
        "artifacts",
        "environment",
        "authority",
        "effects",
        "document_sha256",
    }:
        raise ValueError("MusicFM synthetic canary result fields changed")
    if (
        document.get("status") != "complete_verified_structure_unpromoted"
        or document.get("repository_commit") != checked["repository_commit"]
        or document.get("setup_receipt") != {**checked["setup_receipt"], "packages": 26}
        or document.get("checkpoint")
        != {
            "filename": "pretrained_fma.pt",
            "bytes": 1_316_802_154,
            "sha256": _CHECKPOINT_SHA256,
        }
        or document.get("synthetic_input") != checked["synthetic_input"]
    ):
        raise ValueError("MusicFM synthetic canary evidence binding changed")
    loader = document.get("loader")
    if (
        not isinstance(loader, Mapping)
        or set(loader)
        != {
            "mode",
            "weights_only",
            "map_location",
            "checkpoint_sha256",
            "state_tensor_count",
            "strict_key_shape_dtype_match",
            "state_key_migrations",
            "batch_norm_counter_migration",
            "local_config_only",
            "frozen_eval",
        }
        or loader.get("mode") != "torch_load_weights_only_local_config_strict_state_v1"
        or loader.get("weights_only") is not True
        or loader.get("map_location") != "cpu"
        or loader.get("checkpoint_sha256") != _CHECKPOINT_SHA256
        or isinstance(loader.get("state_tensor_count"), bool)
        or not isinstance(loader.get("state_tensor_count"), int)
        or loader["state_tensor_count"] <= 0
        or loader.get("strict_key_shape_dtype_match") is not True
        or loader.get("state_key_migrations")
        != [
            {
                "from": "conformer.pos_conv_embed.conv.weight_g",
                "to": "conformer.pos_conv_embed.conv.parametrizations.weight.original0",
            },
            {
                "from": "conformer.pos_conv_embed.conv.weight_v",
                "to": "conformer.pos_conv_embed.conv.parametrizations.weight.original1",
            },
        ]
        or loader.get("batch_norm_counter_migration")
        != {
            "keys": list(_BATCH_NORM_COUNTER_KEYS),
            "count": 18,
            "from_dtype": "float32",
            "to_dtype": "int64",
            "exact_value": 95_489,
            "meaning": "batch_norm_bookkeeping_only_not_learned_weight",
        }
        or loader.get("local_config_only") is not True
        or loader.get("frozen_eval") is not True
    ):
        raise ValueError("MusicFM synthetic canary loader evidence changed")
    environment = document.get("environment")
    if (
        not isinstance(environment, Mapping)
        or set(environment) != {"torch_version", "cuda_version", "device_name"}
        or environment.get("torch_version") != "2.7.1+cu128"
        or environment.get("cuda_version") != "12.8"
        or environment.get("device_name") != "NVIDIA GeForce RTX 4080 Laptop GPU"
        or any(
            not isinstance(environment.get(key), str)
            or not environment[key]
            or "/" in environment[key]
            or "\\" in environment[key]
            for key in environment
        )
    ):
        raise ValueError("MusicFM synthetic canary environment changed")
    metrics = document.get("metrics")
    if metrics != {
        "feature_shape": [1, _EXPECTED_FEATURE_FRAMES, _FEATURE_DIMENSION],
        "feature_dtype": "float32",
        "finite": True,
        "feature_frames": _EXPECTED_FEATURE_FRAMES,
        "feature_dimension": _FEATURE_DIMENSION,
        "feature_rate_hz": 25.0,
        "maximum_repeat_difference": 0.0,
        "network_attempts": 0,
    }:
        raise ValueError("MusicFM synthetic canary metrics changed")
    if document.get("authority") != {
        "private_audio_access_authorized": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_changed": False,
    } or document.get("effects") != {
        "model_loaded_restricted": True,
        "synthetic_features_extracted": True,
        "private_audio_opened": False,
        "training_started": False,
        "model_weights_changed": False,
    }:
        raise ValueError("MusicFM synthetic canary authority changed")
    _validate_artifact_records(document.get("artifacts"))
    return document


def verify_musicfm_synthetic_canary_round_trip(
    output_dir: Path,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the retained result and artifact bytes without loading the model."""

    checked = validate_musicfm_synthetic_canary_request(request)
    root = _real_directory(output_dir, "output_dir")
    expected_names = {
        "features-run-1.npy",
        "features-run-2.npy",
        "metrics.json",
        "result.json",
    }
    children = {path.name for path in root.iterdir()}
    if children != expected_names or any(path.is_symlink() for path in root.iterdir()):
        raise ValueError("MusicFM canary output roster changed")
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    validate_musicfm_synthetic_canary_result(result, checked)
    records = {row["filename"]: row for row in result["artifacts"]}
    for name in expected_names - {"result.json"}:
        path = root / name
        record = records.get(name)
        if not path.is_file() or record != _file_record(
            path, record["kind"], record["media_type"]
        ):
            raise ValueError("MusicFM canary artifact bytes changed")
    import numpy as np

    first = np.load(root / "features-run-1.npy", allow_pickle=False)
    second = np.load(root / "features-run-2.npy", allow_pickle=False)
    if (
        first.shape != (1, _EXPECTED_FEATURE_FRAMES, _FEATURE_DIMENSION)
        or first.dtype.name != "float32"
        or not np.isfinite(first).all()
        or not np.array_equal(first, second)
    ):
        raise ValueError("MusicFM canary feature arrays changed")
    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    if metrics != result["metrics"]:
        raise ValueError("MusicFM canary metrics artifact changed")
    return {
        "schema": "sunofriend.remix-musicfm-fma-synthetic-canary-verification.v0",
        "status": "verified_synthetic_frozen_features_only",
        "request_sha256": checked["document_sha256"],
        "result_sha256": result["document_sha256"],
        "artifacts_verified": 3,
        "private_audio_opened": False,
        "training_started": False,
        "product_ordering_changed": False,
    }


def _request_values(
    *, repository_commit: str, setup_receipt_sha256: str, setup_receipt_bytes: int
) -> dict[str, Any]:
    return {
        "schema": MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA,
        "status": "authorized_single_synthetic_frozen_feature_canary",
        "repository_commit": repository_commit,
        "setup_receipt": {
            "sha256": setup_receipt_sha256,
            "bytes": setup_receipt_bytes,
        },
        "model": {
            "provider": "musicfm-fma-25hz",
            "checkpoint_sha256": _CHECKPOINT_SHA256,
            "restricted_weights_only_load": True,
            "local_config_only": True,
            "frozen_eval": True,
            "layer_index": _LAYER_INDEX,
        },
        "synthetic_input": {
            "generator": "fixed_sines_chirp_and_pulses_v1",
            "sample_rate_hz": _SAMPLE_RATE,
            "channels": 1,
            "frames": _SYNTHETIC_FRAMES,
            "private_audio": False,
        },
        "expected_output": {
            "shape": [1, _EXPECTED_FEATURE_FRAMES, _FEATURE_DIMENSION],
            "dtype": "float32",
            "finite": True,
            "exact_repeat_required": True,
        },
        "execution": {
            "device": "cuda",
            "maximum_executions": 1,
            "retries": 0,
            "network_allowed": False,
            "downloads_allowed": False,
        },
        "authority": {
            "model_load_authorized": True,
            "synthetic_inference_authorized": True,
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
    }


def _result_values(
    request: Mapping[str, Any],
    *,
    setup: Mapping[str, Any],
    loader: Mapping[str, Any],
    asset_records: Mapping[str, Mapping[str, Any]],
    artifacts: list[dict[str, Any]],
    metrics: Mapping[str, Any],
    torch: Any,
) -> dict[str, Any]:
    return {
        "schema": MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA,
        "status": "complete_verified_structure_unpromoted",
        "request_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "setup_receipt": dict(setup),
        "checkpoint": dict(asset_records["assets/pretrained_fma.pt"]),
        "loader": dict(loader),
        "synthetic_input": dict(request["synthetic_input"]),
        "metrics": dict(metrics),
        "artifacts": artifacts,
        "environment": {
            "torch_version": str(torch.__version__),
            "cuda_version": str(torch.version.cuda),
            "device_name": str(torch.cuda.get_device_name(0)),
        },
        "authority": {
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "effects": {
            "model_loaded_restricted": True,
            "synthetic_features_extracted": True,
            "private_audio_opened": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }


def _verify_setup_receipt(root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
    path = root / "setup-receipt.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("MusicFM setup receipt is missing")
    raw = path.read_bytes()
    expected = request["setup_receipt"]
    if (
        len(raw) != expected["bytes"]
        or hashlib.sha256(raw).hexdigest() != expected["sha256"]
    ):
        raise ValueError("MusicFM setup receipt identity changed")
    document = json.loads(raw.decode("utf-8-sig"))
    if (
        document.get("schema")
        != "sunofriend.remix-musicfm-fma-windows-setup-receipt.v0"
        or document.get("packages") != 26
        or document.get("fresh_environment") is not True
        or document.get("offline_no_deps_install") is not True
        or any(
            document.get(key) is not False
            for key in (
                "model_imported",
                "checkpoint_loaded",
                "synthetic_canary_run",
                "private_audio_opened",
            )
        )
    ):
        raise ValueError("MusicFM setup receipt claims changed effects")
    return {
        "sha256": expected["sha256"],
        "bytes": expected["bytes"],
        "packages": 26,
    }


def _verify_runtime_assets(
    root: Path, repository_commit: str
) -> dict[str, dict[str, Any]]:
    manifest = create_windows_asset_manifest(repository_commit=repository_commit)
    records: dict[str, dict[str, Any]] = {}
    for row in manifest["items"]:
        relative = row["target_relative_path"]
        path = root.joinpath(*relative.split("/"))
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"MusicFM runtime asset is missing: {relative}")
        observed = _file_identity(path)
        if observed != {"bytes": row["bytes"], "sha256": row["sha256"]}:
            raise ValueError(f"MusicFM runtime asset changed: {relative}")
        records[relative] = {"filename": Path(relative).name, **observed}
    return records


def _load_restricted_model(
    root: Path, asset_records: Mapping[str, Mapping[str, Any]]
) -> tuple[Any, Any, dict[str, Any]]:
    torch = importlib.import_module("torch")
    nn = torch.nn
    source_root = root / "source"
    sys.path.insert(0, str(source_root))
    try:
        features_module = importlib.import_module("musicfm.modules.features")
        conv_module = importlib.import_module("musicfm.modules.conv")
        quantizer_module = importlib.import_module("musicfm.modules.random_quantizer")
    finally:
        try:
            sys.path.remove(str(source_root))
        except ValueError:
            pass
    conformer = importlib.import_module(
        "transformers.models.wav2vec2_conformer.modeling_wav2vec2_conformer"
    )
    config_payload = json.loads(
        (root / "assets" / "wav2vec2-conformer-config.json").read_text(encoding="utf-8")
    )
    config = conformer.Wav2Vec2ConformerConfig.from_dict(config_payload)
    config.num_hidden_layers = 12
    config.hidden_size = 1_024
    stats = json.loads((root / "assets" / "fma_stats.json").read_text(encoding="utf-8"))

    class RestrictedMusicFM25Hz(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = ["melspec_2048"]
            self.stat = stats
            self.preprocessor_melspec_2048 = features_module.MelSTFT(
                n_fft=2048, hop_length=240, is_db=True
            )
            self.quantizer_melspec_2048_0 = quantizer_module.RandomProjectionQuantizer(
                128 * 4, 16, 4096, seed=142
            )
            self.conv = conv_module.Conv2dSubsampling(
                1, 512, 1_024, strides=[2, 2], n_bands=128
            )
            self.conformer = conformer.Wav2Vec2ConformerEncoder(config)
            self.linear = nn.Linear(1_024, 4096)
            self.loss = nn.CrossEntropyLoss()
            random.seed(142)
            self.cls_token = nn.Parameter(torch.randn(1_024))

        def get_latent(self, waveform: Any, layer_ix: int = 12) -> Any:
            mel = self.preprocessor_melspec_2048.float()(waveform.float())[..., :-1]
            mel = (mel - self.stat["melspec_2048_mean"]) / self.stat["melspec_2048_std"]
            encoded = self.conv(mel)
            hidden = self.conformer(encoded, output_hidden_states=True)["hidden_states"]
            return hidden[layer_ix]

    model = RestrictedMusicFM25Hz()
    checkpoint = root / "assets" / "pretrained_fma.pt"
    loaded = torch.load(checkpoint, weights_only=True, map_location="cpu")
    if not isinstance(loaded, Mapping) or not isinstance(
        loaded.get("state_dict"), Mapping
    ):
        raise ValueError("MusicFM checkpoint wrapper changed")
    state: dict[str, Any] = {}
    for key, tensor in loaded["state_dict"].items():
        if (
            not isinstance(key, str)
            or not key.startswith("model.")
            or not torch.is_tensor(tensor)
        ):
            raise ValueError("MusicFM checkpoint state changed")
        state[key[6:]] = tensor
    expected = model.state_dict()
    state, migrations = _migrate_legacy_weight_norm_keys(state, expected)
    state, counter_migration = _migrate_exact_batch_norm_counters(
        state, expected, torch
    )
    for key, tensor in state.items():
        reference = expected[key]
        if tensor.shape != reference.shape or tensor.dtype != reference.dtype:
            raise ValueError(f"MusicFM checkpoint tensor changed: {key}")
    model.load_state_dict(state, strict=True)
    model.eval()
    model.requires_grad_(False)
    return (
        model,
        torch,
        {
            "mode": "torch_load_weights_only_local_config_strict_state_v1",
            "weights_only": True,
            "map_location": "cpu",
            "checkpoint_sha256": asset_records["assets/pretrained_fma.pt"]["sha256"],
            "state_tensor_count": len(state),
            "strict_key_shape_dtype_match": True,
            "state_key_migrations": migrations,
            "batch_norm_counter_migration": counter_migration,
            "local_config_only": True,
            "frozen_eval": True,
        },
    )


def _synthetic_waveform(torch: Any) -> Any:
    time = torch.arange(_SYNTHETIC_FRAMES, dtype=torch.float32) / _SAMPLE_RATE
    phase = 2 * math.pi * (180.0 * time + 0.5 * 220.0 * time * time)
    pulse = ((torch.arange(_SYNTHETIC_FRAMES) % 6_000) < 240).float()
    waveform = (
        0.18 * torch.sin(2 * math.pi * 220.0 * time)
        + 0.11 * torch.sin(2 * math.pi * 329.6276 * time)
        + 0.07 * torch.sin(phase)
        + 0.03 * pulse
    )
    return waveform.unsqueeze(0)


def _validate_feature_tensor(value: Any, torch: Any) -> None:
    if (
        list(value.shape) != [1, _EXPECTED_FEATURE_FRAMES, _FEATURE_DIMENSION]
        or value.dtype != torch.float32
        or not bool(torch.isfinite(value).all())
    ):
        raise RuntimeError("MusicFM synthetic feature geometry changed")


@contextmanager
def _deny_network() -> Iterator[list[str]]:
    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection
    original_lookup = socket.getaddrinfo
    original_environment = {
        key: os.environ.get(key)
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "PIP_NO_INDEX")
    }

    def denied(*args: Any, **kwargs: Any) -> Any:
        attempts.append(repr(args[1:] if len(args) > 1 else args))
        raise RuntimeError("network access is denied during the MusicFM canary")

    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied
    os.environ.update(
        {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PIP_NO_INDEX": "1"}
    )
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create
        socket.getaddrinfo = original_lookup
        for key, value in original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _migrate_legacy_weight_norm_keys(
    state: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Admit only PyTorch's exact old-to-new weight-norm key rename."""

    migrated = dict(state)
    missing = set(expected) - set(migrated)
    unexpected = set(migrated) - set(expected)
    legacy_to_current = {
        "conformer.pos_conv_embed.conv.weight_g": (
            "conformer.pos_conv_embed.conv.parametrizations.weight.original0"
        ),
        "conformer.pos_conv_embed.conv.weight_v": (
            "conformer.pos_conv_embed.conv.parametrizations.weight.original1"
        ),
    }
    if not missing and not unexpected:
        return migrated, []
    if missing != set(legacy_to_current.values()) or unexpected != set(
        legacy_to_current
    ):
        raise ValueError("MusicFM checkpoint key roster changed")
    migrations = []
    for old, new in legacy_to_current.items():
        migrated[new] = migrated.pop(old)
        migrations.append({"from": old, "to": new})
    if set(migrated) != set(expected):
        raise ValueError("MusicFM checkpoint key migration changed")
    return migrated, migrations


def _migrate_exact_batch_norm_counters(
    state: Mapping[str, Any], expected: Mapping[str, Any], torch: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cast only the exact pinned checkpoint's non-learned BN counters."""

    migrated = dict(state)
    for key in _BATCH_NORM_COUNTER_KEYS:
        source = migrated.get(key)
        target = expected.get(key)
        if (
            source is None
            or target is None
            or tuple(source.shape) != ()
            or tuple(target.shape) != ()
            or source.dtype != torch.float32
            or target.dtype != torch.int64
            or not bool(torch.isfinite(source))
            or float(source.item()) != 95_489.0
        ):
            raise ValueError(f"MusicFM BatchNorm counter changed: {key}")
        migrated[key] = source.to(dtype=target.dtype)
    return migrated, {
        "keys": list(_BATCH_NORM_COUNTER_KEYS),
        "count": len(_BATCH_NORM_COUNTER_KEYS),
        "from_dtype": "float32",
        "to_dtype": "int64",
        "exact_value": 95_489,
        "meaning": "batch_norm_bookkeeping_only_not_learned_weight",
    }


def _validate_artifact_records(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("MusicFM synthetic canary artifact roster changed")
    expected = {
        ("features-run-1.npy", "features_run_1", "application/x-npy"),
        ("features-run-2.npy", "features_run_2", "application/x-npy"),
        ("metrics.json", "metrics", "application/json"),
    }
    observed = set()
    for row in value:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"filename", "kind", "media_type", "bytes", "sha256"}
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] <= 0
            or not _SHA256.fullmatch(str(row.get("sha256") or ""))
        ):
            raise ValueError("MusicFM synthetic canary artifact record changed")
        observed.add((row["filename"], row["kind"], row["media_type"]))
    if observed != expected:
        raise ValueError("MusicFM synthetic canary artifact names changed")


def _file_record(path: Path, kind: str, media_type: str) -> dict[str, Any]:
    identity = _file_identity(path)
    return {
        "filename": path.name,
        "kind": kind,
        "media_type": media_type,
        **identity,
    }


def _file_identity(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _real_directory(path: Path, label: str) -> Path:
    value = Path(path)
    if not value.is_dir() or value.is_symlink():
        raise ValueError(f"{label} must be a real directory")
    return value.resolve()


__all__ = [
    "MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA",
    "MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA",
    "create_musicfm_synthetic_canary_request",
    "run_musicfm_synthetic_canary",
    "validate_musicfm_synthetic_canary_request",
    "validate_musicfm_synthetic_canary_result",
    "verify_musicfm_synthetic_canary_round_trip",
]
