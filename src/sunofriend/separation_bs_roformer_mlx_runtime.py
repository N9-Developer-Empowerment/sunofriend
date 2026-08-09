"""Shared strict-loading helpers for pinned BS-RoFormer MLX challengers.

This module deliberately contains no model selection, download or inference
entry point.  It only provides the state-dictionary and verified-source
primitives used by separately bounded profile loaders.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


def tensor_inventory(values: dict[str, Any]) -> dict[str, Any]:
    tensors = {
        key: {
            "shape": [int(size) for size in value.shape],
            "dtype": str(value.dtype),
            "numel": (
                int(value.numel())
                if callable(getattr(value, "numel", None))
                else _numel(value.shape)
            ),
        }
        for key, value in sorted(values.items())
    }
    return {
        "key_count": len(tensors),
        "total_numel": sum(item["numel"] for item in tensors.values()),
        "inventory_sha256": hashlib.sha256(
            json.dumps(tensors, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def _numel(shape: Any) -> int:
    result = 1
    for size in shape:
        result *= int(size)
    return result


def checkpoint_state_dict(document: Any) -> dict[str, Any]:
    """Return a tensor-only state dictionary from one weights-only load."""

    import torch

    candidate = document.get("state_dict") if isinstance(document, dict) else None
    if candidate is None and isinstance(document, dict):
        candidate = document
    if not isinstance(candidate, dict) or not candidate:
        raise RuntimeError("BS-RoFormer checkpoint has no state dictionary")
    candidate.pop("_metadata", None)
    if any(not isinstance(key, str) for key in candidate):
        raise RuntimeError("BS-RoFormer checkpoint has a non-string state key")
    if any(not torch.is_tensor(value) for value in candidate.values()):
        raise RuntimeError("BS-RoFormer checkpoint state contains a non-tensor value")
    return candidate


def install_verified_source_package(source_root: Path) -> None:
    """Expose only the already verified local source tree as ``bs_roformer``."""

    package_root = source_root / "src" / "bs_roformer"
    if not package_root.is_dir():
        raise RuntimeError("verified BS-RoFormer source package is missing")
    for name in tuple(sys.modules):
        if name == "bs_roformer" or name.startswith("bs_roformer."):
            del sys.modules[name]
    package = ModuleType("bs_roformer")
    package.__path__ = [str(package_root)]
    package.__package__ = "bs_roformer"
    package.__file__ = str(package_root / "__init__.py")
    sys.modules["bs_roformer"] = package


def compare_exact_mlx_state(
    model_values: dict[str, Any], weights: dict[str, Any]
) -> None:
    """Reject every converted key, shape or dtype mismatch before loading."""

    model_keys = set(model_values)
    weight_keys = set(weights)
    missing = sorted(model_keys - weight_keys)
    unexpected = sorted(weight_keys - model_keys)
    if missing or unexpected:
        raise RuntimeError(
            "BS-RoFormer converted state keys differ: "
            f"missing={missing[:8]}, unexpected={unexpected[:8]}"
        )
    shapes = []
    dtypes = []
    for key in sorted(model_keys):
        if tuple(model_values[key].shape) != tuple(weights[key].shape):
            shapes.append(
                (key, tuple(model_values[key].shape), tuple(weights[key].shape))
            )
        if model_values[key].dtype != weights[key].dtype:
            dtypes.append((key, str(model_values[key].dtype), str(weights[key].dtype)))
    if shapes or dtypes:
        raise RuntimeError(
            "BS-RoFormer converted tensor contracts differ: "
            f"shapes={shapes[:4]}, dtypes={dtypes[:4]}"
        )


__all__ = [
    "checkpoint_state_dict",
    "compare_exact_mlx_state",
    "install_verified_source_package",
    "tensor_inventory",
]
