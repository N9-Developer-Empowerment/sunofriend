"""Restricted local MusicFM-FMA loader and synthetic feature extraction.

This private module owns every framework-specific detail: offline process
guards, the exact pinned architecture, compatibility migrations and the frozen
CUDA inference operation.  Callers receive arrays and path-free evidence; they
never need to import MusicFM, Transformers or Torch.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import json
import math
import os
from pathlib import Path
import random
import socket
import sys
from typing import Any, Iterator, Mapping


CHECKPOINT_SHA256 = "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96"
SAMPLE_RATE = 24_000
SYNTHETIC_FRAMES = 48_000
LAYER_INDEX = 7
FEATURE_DIMENSION = 1_024
EXPECTED_FEATURE_FRAMES = 50
LEGACY_WEIGHT_NORM_KEYS = (
    "conformer.pos_conv_embed.conv.weight_g",
    "conformer.pos_conv_embed.conv.weight_v",
)
CURRENT_WEIGHT_NORM_KEYS = (
    "conformer.pos_conv_embed.conv.parametrizations.weight.original0",
    "conformer.pos_conv_embed.conv.parametrizations.weight.original1",
)
WEIGHT_NORM_MIGRATIONS = [
    {"from": old, "to": new}
    for old, new in zip(LEGACY_WEIGHT_NORM_KEYS, CURRENT_WEIGHT_NORM_KEYS)
]
BATCH_NORM_COUNTER_KEYS = (
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


@dataclass(frozen=True)
class FrozenFeatureExtraction:
    """Framework-neutral output of one exact synthetic frozen-feature run."""

    first: Any
    second: Any
    metrics: Mapping[str, Any]
    loader: Mapping[str, Any]
    environment: Mapping[str, str]


def extract_synthetic_frozen_features(
    runtime_root: Path,
    asset_records: Mapping[str, Mapping[str, Any]],
) -> FrozenFeatureExtraction:
    """Load the pinned local model once and extract the fixed signal twice."""

    root = Path(runtime_root)
    with deny_network() as attempts:
        model, torch, loader_evidence = _load_restricted_model(root, asset_records)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the Windows MusicFM canary")
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        device = torch.device("cuda")
        model = model.to(device)
        waveform = _synthetic_waveform(torch).to(device)
        with torch.inference_mode():
            first = model.get_latent(waveform, layer_ix=LAYER_INDEX).float().cpu()
            second = model.get_latent(waveform, layer_ix=LAYER_INDEX).float().cpu()
    if attempts:
        raise RuntimeError("MusicFM canary attempted network access")
    _validate_feature_tensor(first, torch)
    _validate_feature_tensor(second, torch)
    maximum_repeat_difference = float(torch.max(torch.abs(first - second)).item())
    if maximum_repeat_difference != 0.0:
        raise RuntimeError("MusicFM synthetic feature extraction is not repeatable")
    metrics = {
        "feature_shape": list(first.shape),
        "feature_dtype": "float32",
        "finite": True,
        "feature_frames": int(first.shape[1]),
        "feature_dimension": int(first.shape[2]),
        "feature_rate_hz": first.shape[1] / (SYNTHETIC_FRAMES / SAMPLE_RATE),
        "maximum_repeat_difference": maximum_repeat_difference,
        "network_attempts": len(attempts),
    }
    return FrozenFeatureExtraction(
        first=first.numpy(),
        second=second.numpy(),
        metrics=metrics,
        loader=loader_evidence,
        environment={
            "torch_version": str(torch.__version__),
            "cuda_version": str(torch.version.cuda),
            "device_name": str(torch.cuda.get_device_name(0)),
            "cublas_workspace_config": ":4096:8",
        },
    )


def expected_loader_evidence(*, state_tensor_count: int) -> dict[str, Any]:
    """Build the exact path-free evidence contract for a successful load."""

    if (
        isinstance(state_tensor_count, bool)
        or not isinstance(state_tensor_count, int)
        or state_tensor_count <= 0
    ):
        raise ValueError("state tensor count must be positive")
    return {
        "mode": "torch_load_weights_only_local_config_strict_state_v1",
        "weights_only": True,
        "map_location": "cpu",
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "state_tensor_count": state_tensor_count,
        "strict_key_shape_dtype_match": True,
        "state_key_migrations": WEIGHT_NORM_MIGRATIONS,
        "batch_norm_counter_migration": {
            "keys": list(BATCH_NORM_COUNTER_KEYS),
            "count": len(BATCH_NORM_COUNTER_KEYS),
            "from_dtype": "float32",
            "to_dtype": "int64",
            "exact_value": 95_489,
            "meaning": "batch_norm_bookkeeping_only_not_learned_weight",
        },
        "local_config_only": True,
        "frozen_eval": True,
    }


def migrate_legacy_weight_norm_keys(
    state: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Admit only PyTorch's exact old-to-new weight-norm key rename."""

    migrated = dict(state)
    missing = set(expected) - set(migrated)
    unexpected = set(migrated) - set(expected)
    if not missing and not unexpected:
        return migrated, []
    if missing != set(CURRENT_WEIGHT_NORM_KEYS) or unexpected != set(
        LEGACY_WEIGHT_NORM_KEYS
    ):
        raise ValueError("MusicFM checkpoint key roster changed")
    for migration in WEIGHT_NORM_MIGRATIONS:
        migrated[migration["to"]] = migrated.pop(migration["from"])
    if set(migrated) != set(expected):
        raise ValueError("MusicFM checkpoint key migration changed")
    return migrated, list(WEIGHT_NORM_MIGRATIONS)


def migrate_exact_batch_norm_counters(
    state: Mapping[str, Any], expected: Mapping[str, Any], torch: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cast only the exact pinned checkpoint's non-learned BN counters."""

    migrated = dict(state)
    for key in BATCH_NORM_COUNTER_KEYS:
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
    return migrated, expected_loader_evidence(state_tensor_count=1)[
        "batch_norm_counter_migration"
    ]


@contextmanager
def deny_network() -> Iterator[list[str]]:
    """Fail closed on common socket entry points and restore process state."""

    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection
    original_lookup = socket.getaddrinfo
    environment_keys = (
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "PIP_NO_INDEX",
        "CUBLAS_WORKSPACE_CONFIG",
    )
    original_environment = {key: os.environ.get(key) for key in environment_keys}

    def denied(*args: Any, **kwargs: Any) -> Any:
        del kwargs
        attempts.append(repr(args[1:] if len(args) > 1 else args))
        raise RuntimeError("network access is denied during the MusicFM canary")

    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PIP_NO_INDEX": "1",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        }
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


def _load_restricted_model(
    root: Path, asset_records: Mapping[str, Mapping[str, Any]]
) -> tuple[Any, Any, dict[str, Any]]:
    torch = importlib.import_module("torch")
    features_module, conv_module, quantizer_module = _import_musicfm_modules(
        root / "source"
    )
    conformer = importlib.import_module(
        "transformers.models.wav2vec2_conformer.modeling_wav2vec2_conformer"
    )
    config_payload = json.loads(
        (root / "assets" / "wav2vec2-conformer-config.json").read_text(encoding="utf-8")
    )
    config = conformer.Wav2Vec2ConformerConfig.from_dict(config_payload)
    config.num_hidden_layers = 12
    config.hidden_size = FEATURE_DIMENSION
    stats = json.loads((root / "assets" / "fma_stats.json").read_text(encoding="utf-8"))
    model = _build_restricted_model(
        torch,
        features_module=features_module,
        conv_module=conv_module,
        quantizer_module=quantizer_module,
        conformer=conformer,
        config=config,
        stats=stats,
    )
    checkpoint = root / "assets" / "pretrained_fma.pt"
    state = _checkpoint_state(checkpoint, torch)
    expected = model.state_dict()
    state, migrations = migrate_legacy_weight_norm_keys(state, expected)
    state, counter_migration = migrate_exact_batch_norm_counters(state, expected, torch)
    _validate_state_tensors(state, expected)
    model.load_state_dict(state, strict=True)
    model.eval()
    model.requires_grad_(False)
    evidence = expected_loader_evidence(state_tensor_count=len(state))
    evidence["state_key_migrations"] = migrations
    evidence["batch_norm_counter_migration"] = counter_migration
    if not _checkpoint_identity_matches(evidence, asset_records):
        raise ValueError("MusicFM checkpoint identity changed before loading")
    return model, torch, evidence


def _import_musicfm_modules(source_root: Path) -> tuple[Any, Any, Any]:
    sys.path.insert(0, str(source_root))
    try:
        return (
            importlib.import_module("musicfm.modules.features"),
            importlib.import_module("musicfm.modules.conv"),
            importlib.import_module("musicfm.modules.random_quantizer"),
        )
    finally:
        try:
            sys.path.remove(str(source_root))
        except ValueError:
            pass


def _checkpoint_state(checkpoint: Path, torch: Any) -> dict[str, Any]:
    loaded = torch.load(checkpoint, weights_only=True, map_location="cpu")
    if not isinstance(loaded, Mapping):
        raise ValueError("MusicFM checkpoint wrapper changed")
    state = loaded.get("state_dict")
    if not isinstance(state, Mapping):
        raise ValueError("MusicFM checkpoint wrapper changed")
    return _unwrap_state(state, torch)


def _validate_state_tensors(
    state: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    for key, tensor in state.items():
        reference = expected[key]
        if tensor.shape != reference.shape or tensor.dtype != reference.dtype:
            raise ValueError(f"MusicFM checkpoint tensor changed: {key}")


def _checkpoint_identity_matches(
    loader_evidence: Mapping[str, Any],
    asset_records: Mapping[str, Mapping[str, Any]],
) -> bool:
    record = asset_records.get("assets/pretrained_fma.pt")
    return isinstance(record, Mapping) and loader_evidence.get(
        "checkpoint_sha256"
    ) == record.get("sha256")


def _build_restricted_model(
    torch: Any,
    *,
    features_module: Any,
    conv_module: Any,
    quantizer_module: Any,
    conformer: Any,
    config: Any,
    stats: Mapping[str, Any],
) -> Any:
    nn = torch.nn

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
                1, 512, FEATURE_DIMENSION, strides=[2, 2], n_bands=128
            )
            self.conformer = conformer.Wav2Vec2ConformerEncoder(config)
            self.linear = nn.Linear(FEATURE_DIMENSION, 4096)
            self.loss = nn.CrossEntropyLoss()
            random.seed(142)
            self.cls_token = nn.Parameter(torch.randn(FEATURE_DIMENSION))

        def get_latent(self, waveform: Any, layer_ix: int = 12) -> Any:
            mel = self.preprocessor_melspec_2048.float()(waveform.float())[..., :-1]
            mel = (mel - self.stat["melspec_2048_mean"]) / self.stat["melspec_2048_std"]
            encoded = self.conv(mel)
            hidden = self.conformer(encoded, output_hidden_states=True)["hidden_states"]
            return hidden[layer_ix]

    return RestrictedMusicFM25Hz()


def _unwrap_state(value: Mapping[str, Any], torch: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for key, tensor in value.items():
        if (
            not isinstance(key, str)
            or not key.startswith("model.")
            or not torch.is_tensor(tensor)
        ):
            raise ValueError("MusicFM checkpoint state changed")
        state[key[6:]] = tensor
    return state


def _synthetic_waveform(torch: Any) -> Any:
    time = torch.arange(SYNTHETIC_FRAMES, dtype=torch.float32) / SAMPLE_RATE
    phase = 2 * math.pi * (180.0 * time + 0.5 * 220.0 * time * time)
    pulse = ((torch.arange(SYNTHETIC_FRAMES) % 6_000) < 240).float()
    waveform = (
        0.18 * torch.sin(2 * math.pi * 220.0 * time)
        + 0.11 * torch.sin(2 * math.pi * 329.6276 * time)
        + 0.07 * torch.sin(phase)
        + 0.03 * pulse
    )
    return waveform.unsqueeze(0)


def _validate_feature_tensor(value: Any, torch: Any) -> None:
    if (
        list(value.shape) != [1, EXPECTED_FEATURE_FRAMES, FEATURE_DIMENSION]
        or value.dtype != torch.float32
        or not bool(torch.isfinite(value).all())
    ):
        raise RuntimeError("MusicFM synthetic feature geometry changed")


__all__ = [
    "FrozenFeatureExtraction",
    "extract_synthetic_frozen_features",
]
