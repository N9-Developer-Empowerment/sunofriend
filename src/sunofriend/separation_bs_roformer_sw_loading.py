"""Strict offline construction of the pinned BS-RoFormer-SW MLX model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .separation_bs_roformer_mlx_runtime import (
    checkpoint_state_dict,
    compare_exact_mlx_state,
    install_verified_source_package,
    tensor_inventory,
)


@dataclass(frozen=True)
class SwModelLoadResult:
    model: Any
    config: Any
    evidence: dict[str, Any]


def load_sw_model(
    *, checkpoint: Path, config_document: dict[str, Any], source_root: Path
) -> SwModelLoadResult:
    """Load the exact six-role checkpoint once with strict converted state."""

    import mlx.core as mx
    from mlx.utils import tree_flatten
    import torch

    install_verified_source_package(source_root)
    from bs_roformer.backends.mlx_backend import MLXBackend
    from bs_roformer.mlx import BSRoformerMLX, convert_torch_to_mlx_weights

    config = SimpleNamespace(
        model=config_document["model"],
        training=SimpleNamespace(**config_document["training"]),
        inference=SimpleNamespace(**config_document["inference"]),
    )
    document = torch.load(checkpoint, weights_only=True, map_location="cpu")
    state = checkpoint_state_dict(document)
    checkpoint_inventory = tensor_inventory(state)
    converted = convert_torch_to_mlx_weights(state, variant=None)
    converted_inventory = tensor_inventory(converted)
    dtypes = {value.dtype for value in converted.values()}
    if len(dtypes) != 1:
        raise RuntimeError("BS-RoFormer-SW checkpoint has mixed parameter dtypes")
    checkpoint_dtype = dtypes.pop()
    model_args = MLXBackend._model_args(config, variation=None)
    model = BSRoformerMLX(**model_args)
    model.set_dtype(checkpoint_dtype)
    model.eval()
    constructed = dict(tree_flatten(model.parameters()))
    compare_exact_mlx_state(constructed, converted)
    constructed_inventory = tensor_inventory(constructed)
    model.load_weights(list(converted.items()), strict=True)
    mx.eval(model.parameters())
    loaded = dict(tree_flatten(model.parameters()))
    loaded_inventory = tensor_inventory(loaded)
    if loaded_inventory != constructed_inventory:
        raise RuntimeError("BS-RoFormer-SW loaded inventory differs")
    del document
    del state
    del converted
    del constructed
    roles = list(config_document["training"]["instruments"])
    return SwModelLoadResult(
        model=model,
        config=config,
        evidence={
            "architecture": "BSRoformerMLX, six-role SW checkpoint",
            "checkpoint_inventory": checkpoint_inventory,
            "converted_inventory": converted_inventory,
            "constructed_inventory": constructed_inventory,
            "loaded_inventory": loaded_inventory,
            "state_keys_equal": True,
            "state_shapes_equal": True,
            "state_dtypes_equal": True,
            "load_strict": True,
            "model_retained_until_process_exit": True,
            "checkpoint_parameter_dtype": str(checkpoint_dtype),
            "native_roles": roles,
            "native_role_count": len(roles),
            "target_role": "guitar",
            "target_role_index": roles.index("guitar"),
            "chunk_size": int(config_document["inference"]["chunk_size"]),
            "num_overlap": int(config_document["inference"]["num_overlap"]),
            "stft_hop_length": int(
                config_document["model"].get("stft_hop_length", 512)
            ),
        },
    )


__all__ = ["SwModelLoadResult", "load_sw_model"]
