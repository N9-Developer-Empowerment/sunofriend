from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from sunofriend._separation_melroformer_conversion_parity import (
    EVIDENCE_SHA256,
    _document_sha256,
    _float32_to_bf16_bytes,
    _verify_private_melroformer_weight_conversion,
    _verify_tracked_weight_conversion_evidence,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _safetensors(tensors: dict[str, np.ndarray]) -> bytes:
    offset = 0
    header: dict[str, object] = {"__metadata__": None}
    payload = bytearray()
    for name in sorted(tensors):
        array = np.asarray(tensors[name], dtype=np.float32)
        encoded = _float32_to_bf16_bytes(array, np=np)
        header[name] = {
            "dtype": "BF16",
            "shape": list(array.shape),
            "data_offsets": [offset, offset + len(encoded)],
        }
        payload.extend(encoded)
        offset += len(encoded)
    encoded_header = json.dumps(header, separators=(",", ":")).encode()
    return struct.pack("<Q", len(encoded_header)) + encoded_header + payload


def _run(
    tmp_path: Path,
    *,
    source_root: object,
    tensors: dict[str, np.ndarray],
) -> dict[str, object]:
    source = tmp_path / "MelBandRoformer.ckpt"
    source.write_bytes(b"synthetic exact source")
    converted = tmp_path / "model.safetensors"
    converted.write_bytes(_safetensors(tensors))
    return _verify_private_melroformer_weight_conversion(
        source.absolute(),
        converted.absolute(),
        checkpoint_loader=lambda _handle: source_root,
        expected_source_bytes=source.stat().st_size,
        expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        expected_converted_bytes=converted.stat().st_size,
        expected_converted_sha256=hashlib.sha256(converted.read_bytes()).hexdigest(),
    )


def test_verifies_stripping_prefix_normalisation_qkv_split_and_exact_bf16(
    tmp_path: Path,
) -> None:
    qkv = np.arange(12, dtype=np.float32).reshape(6, 2) / 7.0
    plain = np.asarray([1.0, -2.5, 0.33333334], dtype=np.float32)
    result = _run(
        tmp_path,
        source_root={
            "state_dict": {
                "model.block.to_qkv.weight": qkv,
                "model.plain.weight": plain,
                "model.norm.running_mean": np.zeros(2, dtype=np.float32),
            }
        },
        tensors={
            "block.to_q.weight": qkv[:2],
            "block.to_k.weight": qkv[2:4],
            "block.to_v.weight": qkv[4:],
            "plain.weight": plain,
        },
    )

    assert result["status"] == "verified_exact_bf16_weight_conversion"
    assert result["source"]["state_dict_key_count"] == 3
    assert result["source"]["retained_key_count"] == 2
    assert result["converted"]["tensor_count"] == 4
    assert result["converted"]["qkv_split_count"] == 1
    assert result["claims"]["bf16_tensor_payloads_bit_exact"] is True
    assert result["claims"]["inference_output_parity_independently_verified"] is False
    assert result["effects"]["restricted_weights_only_load"] is True
    assert result["document_sha256"] == _document_sha256(result)


def test_rejects_one_changed_converted_tensor_bit(tmp_path: Path) -> None:
    source = np.asarray([1.0, 2.0], dtype=np.float32)
    converted = _safetensors({"weight": source})
    changed = bytearray(converted)
    changed[-1] ^= 1
    source_file = tmp_path / "source.ckpt"
    source_file.write_bytes(b"source")
    converted_file = tmp_path / "model.safetensors"
    converted_file.write_bytes(changed)

    with pytest.raises(ValueError, match="tensor values differ"):
        _verify_private_melroformer_weight_conversion(
            source_file.absolute(),
            converted_file.absolute(),
            checkpoint_loader=lambda _handle: {"weight": source},
            expected_source_bytes=source_file.stat().st_size,
            expected_source_sha256=hashlib.sha256(source_file.read_bytes()).hexdigest(),
            expected_converted_bytes=converted_file.stat().st_size,
            expected_converted_sha256=hashlib.sha256(changed).hexdigest(),
        )


def test_rejects_source_identity_before_checkpoint_load(tmp_path: Path) -> None:
    source = tmp_path / "source.ckpt"
    source.write_bytes(b"wrong")
    converted = tmp_path / "model.safetensors"
    converted.write_bytes(_safetensors({"weight": np.ones(1, dtype=np.float32)}))
    called = False

    def loader(_handle: object) -> object:
        nonlocal called
        called = True
        return {"weight": np.ones(1, dtype=np.float32)}

    with pytest.raises(ValueError, match="SHA-256 differs"):
        _verify_private_melroformer_weight_conversion(
            source.absolute(),
            converted.absolute(),
            checkpoint_loader=loader,
            expected_source_bytes=source.stat().st_size,
            expected_source_sha256="0" * 64,
            expected_converted_bytes=converted.stat().st_size,
            expected_converted_sha256=hashlib.sha256(converted.read_bytes()).hexdigest(),
        )
    assert called is False


def test_rejects_key_and_model_prefix_collisions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tensor names differ"):
        _run(
            tmp_path,
            source_root={"weight": np.ones(1, dtype=np.float32)},
            tensors={"other": np.ones(1, dtype=np.float32)},
        )

    other = tmp_path / "collision"
    other.mkdir()
    with pytest.raises(ValueError, match="normalization collides"):
        _run(
            other,
            source_root={
                "model.weight": np.ones(1, dtype=np.float32),
                "weight": np.ones(1, dtype=np.float32),
            },
            tensors={"weight": np.ones(1, dtype=np.float32)},
        )


def test_private_conversion_parity_has_no_product_route() -> None:
    assert "private-melroformer-conversion-parity" not in PUBLIC_COMMANDS
    assert "private-melroformer-conversion-parity" not in DIRECT_TUI_COMMANDS


def test_tracked_real_observation_is_exact_path_free_and_non_promoting() -> None:
    repository = Path(__file__).resolve().parents[1]
    evidence = _verify_tracked_weight_conversion_evidence(repository)

    assert evidence["document_sha256"] == _document_sha256(evidence)
    assert evidence["converted"]["tensor_count"] == 708
    assert evidence["converted"]["qkv_split_count"] == 12
    assert evidence["permissions"] == {
        "automatic_promotion": False,
        "automatic_selection": False,
        "checkpoint_publication": False,
        "simple_mode": False,
        "source_graph": False,
        "studio_mode": False,
    }
    assert "/Users/" not in json.dumps(evidence)
    assert len(EVIDENCE_SHA256) == 64
