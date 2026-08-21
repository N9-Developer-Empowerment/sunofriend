from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys

import numpy as np
import pytest

import sunofriend.remix_musicfm_canary as canary_module
from sunofriend.remix_musicfm_canary import (
    create_musicfm_synthetic_canary_request,
    validate_musicfm_synthetic_canary_request,
    validate_musicfm_synthetic_canary_result,
    verify_musicfm_synthetic_canary_round_trip,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256


ROOT = Path(__file__).parents[1]
REQUEST_BUILDER = ROOT / "scripts" / "create-remix-musicfm-synthetic-canary-request.py"


def _request() -> dict:
    return create_musicfm_synthetic_canary_request(
        repository_commit="8" * 40,
        setup_receipt_sha256="7" * 64,
        setup_receipt_bytes=512,
    )


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _artifact(path: Path, kind: str, media_type: str) -> dict:
    return canary_module._file_record(path, kind, media_type)


def _result(output: Path, request: dict) -> dict:
    metrics = {
        "feature_shape": [1, 50, 1024],
        "feature_dtype": "float32",
        "finite": True,
        "feature_frames": 50,
        "feature_dimension": 1024,
        "feature_rate_hz": 25.0,
        "maximum_repeat_difference": 0.0,
        "network_attempts": 0,
    }
    first = output / "features-run-1.npy"
    second = output / "features-run-2.npy"
    metrics_path = output / "metrics.json"
    features = np.zeros((1, 50, 1024), dtype=np.float32)
    np.save(first, features, allow_pickle=False)
    np.save(second, features, allow_pickle=False)
    metrics_path.write_bytes(canonical_json_bytes(metrics))
    result = {
        "schema": "sunofriend.remix-musicfm-fma-synthetic-canary-result.v0",
        "status": "complete_verified_structure_unpromoted",
        "request_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "setup_receipt": {**request["setup_receipt"], "packages": 26},
        "checkpoint": {
            "filename": "pretrained_fma.pt",
            "bytes": 1_316_802_154,
            "sha256": "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96",
        },
        "loader": {
            "mode": "torch_load_weights_only_local_config_strict_state_v1",
            "weights_only": True,
            "map_location": "cpu",
            "checkpoint_sha256": "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96",
            "state_tensor_count": 500,
            "strict_key_shape_dtype_match": True,
            "state_key_migrations": [
                {
                    "from": "conformer.pos_conv_embed.conv.weight_g",
                    "to": "conformer.pos_conv_embed.conv.parametrizations.weight.original0",
                },
                {
                    "from": "conformer.pos_conv_embed.conv.weight_v",
                    "to": "conformer.pos_conv_embed.conv.parametrizations.weight.original1",
                },
            ],
            "batch_norm_counter_migration": {
                "keys": list(canary_module._BATCH_NORM_COUNTER_KEYS),
                "count": 18,
                "from_dtype": "float32",
                "to_dtype": "int64",
                "exact_value": 95_489,
                "meaning": "batch_norm_bookkeeping_only_not_learned_weight",
            },
            "local_config_only": True,
            "frozen_eval": True,
        },
        "synthetic_input": request["synthetic_input"],
        "metrics": metrics,
        "artifacts": [
            _artifact(first, "features_run_1", "application/x-npy"),
            _artifact(second, "features_run_2", "application/x-npy"),
            _artifact(metrics_path, "metrics", "application/json"),
        ],
        "environment": {
            "torch_version": "2.7.1+cu128",
            "cuda_version": "12.8",
            "device_name": "NVIDIA GeForce RTX 4080 Laptop GPU",
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
    _rehash(result)
    (output / "result.json").write_bytes(canonical_json_bytes(result))
    return result


def test_request_is_exact_path_free_synthetic_only_and_no_training() -> None:
    request = _request()
    assert validate_musicfm_synthetic_canary_request(request) == request
    encoded = json.dumps(request, sort_keys=True)
    assert "/Users/" not in encoded
    assert "C:\\" not in encoded
    assert request["synthetic_input"]["private_audio"] is False
    assert request["execution"] == {
        "device": "cuda",
        "maximum_executions": 1,
        "retries": 0,
        "network_allowed": False,
        "downloads_allowed": False,
    }
    assert request["authority"]["training_execution_authorized"] is False
    assert request["authority"]["product_ordering_changed"] is False


def test_request_builder_accepts_exact_commit_without_nested_git(
    tmp_path: Path,
) -> None:
    receipt = tmp_path / "setup-receipt.json"
    output = tmp_path / "request.json"
    receipt.write_text('{"technical":"setup"}', encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(REQUEST_BUILDER),
            str(receipt),
            "--repository-commit",
            "8" * 40,
            "--out",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    request = json.loads(output.read_text(encoding="utf-8"))
    assert request["repository_commit"] == "8" * 40
    assert validate_musicfm_synthetic_canary_request(request) == request


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("network", True),
        ("private", True),
        ("training", True),
        ("path", "C:\\private\\song.wav"),
    ],
)
def test_request_rejects_rehashed_authority_or_scope_changes(
    field: str, value: object
) -> None:
    request = deepcopy(_request())
    if field == "network":
        request["execution"]["network_allowed"] = value
    elif field == "private":
        request["authority"]["private_audio_access_authorized"] = value
    elif field == "training":
        request["authority"]["training_execution_authorized"] = value
    else:
        request["private_path"] = value
    _rehash(request)
    with pytest.raises(ValueError, match="changed"):
        validate_musicfm_synthetic_canary_request(request)


def test_result_and_round_trip_bind_exact_feature_bytes(tmp_path: Path) -> None:
    request = _request()
    output = tmp_path / "result"
    output.mkdir()
    result = _result(output, request)
    assert validate_musicfm_synthetic_canary_result(result, request) == result
    verification = verify_musicfm_synthetic_canary_round_trip(output, request)
    assert verification["status"] == "verified_synthetic_frozen_features_only"
    assert verification["private_audio_opened"] is False
    assert verification["training_started"] is False

    with (output / "features-run-1.npy").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="artifact bytes"):
        verify_musicfm_synthetic_canary_round_trip(output, request)


@pytest.mark.parametrize(
    "mutation",
    ["checkpoint", "loader", "training", "network_metric", "extra"],
)
def test_result_rejects_rehashed_false_evidence(tmp_path: Path, mutation: str) -> None:
    request = _request()
    output = tmp_path / mutation
    output.mkdir()
    result = _result(output, request)
    if mutation == "checkpoint":
        result["checkpoint"]["sha256"] = "9" * 64
    elif mutation == "loader":
        result["loader"]["weights_only"] = False
    elif mutation == "training":
        result["effects"]["training_started"] = True
    elif mutation == "network_metric":
        result["metrics"]["network_attempts"] = 1
    else:
        result["release_approved"] = True
    _rehash(result)
    with pytest.raises(ValueError, match="changed"):
        validate_musicfm_synthetic_canary_result(result, request)


def test_loader_source_uses_local_config_and_restricted_checkpoint_only() -> None:
    source = Path(canary_module.__file__).read_text(encoding="utf-8")
    assert 'torch.load(checkpoint, weights_only=True, map_location="cpu")' in source
    assert "Wav2Vec2ConformerConfig.from_dict(config_payload)" in source
    assert ".from_pretrained(" not in source
    assert "model.load_state_dict(state, strict=True)" in source
    assert "model.requires_grad_(False)" in source
    assert '"HF_HUB_OFFLINE": "1"' in source
    assert '"TRANSFORMERS_OFFLINE": "1"' in source


def test_checkpoint_key_migration_is_exactly_legacy_weight_norm_only() -> None:
    current = {
        "unchanged": object(),
        "conformer.pos_conv_embed.conv.parametrizations.weight.original0": object(),
        "conformer.pos_conv_embed.conv.parametrizations.weight.original1": object(),
    }
    legacy = {
        "unchanged": current["unchanged"],
        "conformer.pos_conv_embed.conv.weight_g": object(),
        "conformer.pos_conv_embed.conv.weight_v": object(),
    }
    migrated, evidence = canary_module._migrate_legacy_weight_norm_keys(legacy, current)
    assert set(migrated) == set(current)
    assert evidence == [
        {
            "from": "conformer.pos_conv_embed.conv.weight_g",
            "to": "conformer.pos_conv_embed.conv.parametrizations.weight.original0",
        },
        {
            "from": "conformer.pos_conv_embed.conv.weight_v",
            "to": "conformer.pos_conv_embed.conv.parametrizations.weight.original1",
        },
    ]
    with pytest.raises(ValueError, match="key roster"):
        canary_module._migrate_legacy_weight_norm_keys(
            {**legacy, "extra": object()}, current
        )


def test_network_guard_denies_and_records_lookup_without_network() -> None:
    original = socket.getaddrinfo
    with canary_module._deny_network() as attempts:
        with pytest.raises(RuntimeError, match="network access is denied"):
            socket.getaddrinfo("example.invalid", 443)
    assert len(attempts) == 1
    assert socket.getaddrinfo is original


def test_batch_norm_counter_migration_is_exact_and_bookkeeping_only() -> None:
    class Tensor:
        shape = ()

        def __init__(self, dtype: str, value: float) -> None:
            self.dtype = dtype
            self.value = value

        def item(self) -> float:
            return self.value

        def to(self, *, dtype: str) -> "Tensor":
            return Tensor(dtype, self.value)

    class Torch:
        float32 = "float32"
        int64 = "int64"

        @staticmethod
        def isfinite(value: Tensor) -> bool:
            return value.value == value.value

    state = {
        key: Tensor(Torch.float32, 95_489.0)
        for key in canary_module._BATCH_NORM_COUNTER_KEYS
    }
    expected = {
        key: Tensor(Torch.int64, 0.0) for key in canary_module._BATCH_NORM_COUNTER_KEYS
    }
    migrated, evidence = canary_module._migrate_exact_batch_norm_counters(
        state, expected, Torch
    )
    assert evidence["count"] == 18
    assert evidence["meaning"] == "batch_norm_bookkeeping_only_not_learned_weight"
    assert {value.dtype for value in migrated.values()} == {Torch.int64}

    changed = dict(state)
    changed[canary_module._BATCH_NORM_COUNTER_KEYS[0]] = Tensor(Torch.float32, 95_488.0)
    with pytest.raises(ValueError, match="BatchNorm counter changed"):
        canary_module._migrate_exact_batch_norm_counters(changed, expected, Torch)
