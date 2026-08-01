from __future__ import annotations

from dataclasses import dataclass

import pytest

from sunofriend._separation_melroformer_real_bridge import (
    _transform_checkpoint_keys,
    _validate_weight_inventory,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


@dataclass(frozen=True)
class _Array:
    shape: tuple[int, ...]
    dtype: str = "mlx.core.bfloat16"


def test_reproduces_every_audited_sanitizer_key_transformation() -> None:
    transformed, dropped = _transform_checkpoint_keys(
        (
            "layers.0.time.to_qkv.weight",
            "layers.0.time.to_out.0.weight",
            "layers.0.time.norm.gamma",
            "layers.0.time.rotary_embed.freqs",
            "mask_estimators.0.to_freqs.4.0.2.bias",
            "plain.weight",
        )
    )

    assert transformed == (
        "layers.0.time.norm.weight",
        "layers.0.time.to_k.weight",
        "layers.0.time.to_out.weight",
        "layers.0.time.to_q.weight",
        "layers.0.time.to_v.weight",
        "mask_estimators.0.to_freqs.4.1.0.bias",
        "plain.weight",
    )
    assert dropped == ("layers.0.time.rotary_embed.freqs",)


def test_accepts_only_complete_key_shape_and_dtype_coverage() -> None:
    raw = {
        "layer.to_qkv.weight": _Array((6, 2)),
        "layer.rotary_embed.freqs": _Array((2,)),
        "norm.gamma": _Array((2,)),
    }
    sanitized = {
        "layer.to_q.weight": _Array((2, 2)),
        "layer.to_k.weight": _Array((2, 2)),
        "layer.to_v.weight": _Array((2, 2)),
        "norm.weight": _Array((2,)),
    }
    expected = dict(sanitized)

    result = _validate_weight_inventory(raw=raw, sanitized=sanitized, expected=expected)

    assert result["raw_checkpoint_key_count"] == 3
    assert result["sanitized_key_count"] == 4
    assert result["expected_model_key_count"] == 4
    assert result["dropped_raw_weight_keys"] == ["layer.rotary_embed.freqs"]
    assert result["complete"] is True


def test_rejects_sanitizer_drift_shape_drift_and_dtype_drift() -> None:
    raw = {"plain.weight": _Array((2,))}
    expected = {"plain.weight": _Array((2,))}
    with pytest.raises(ValueError, match="sanitizer mapping"):
        _validate_weight_inventory(
            raw=raw,
            sanitized={"other.weight": _Array((2,))},
            expected=expected,
        )
    with pytest.raises(ValueError, match="tensor shapes"):
        _validate_weight_inventory(
            raw=raw,
            sanitized={"plain.weight": _Array((3,))},
            expected=expected,
        )
    with pytest.raises(ValueError, match="runtime dtype"):
        _validate_weight_inventory(
            raw={"plain.weight": _Array((2,), dtype="mlx.core.float32")},
            sanitized={"plain.weight": _Array((2,), dtype="mlx.core.float32")},
            expected=expected,
        )


def test_private_bridge_has_no_public_cli_or_tui_route() -> None:
    assert "private-melroformer-bridge" not in PUBLIC_COMMANDS
    assert "private-melroformer-bridge" not in DIRECT_TUI_COMMANDS
