"""Construct and strictly load the exact Mega-53 MLX model without inference."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
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
class Mega53ModelLoadResult:
    model: Any
    evidence: dict[str, Any]


def _checkpoint_expansion_factor(weights: dict[str, Any], dim: int) -> int:
    candidates = {
        int(value.shape[0]) // dim
        for key, value in weights.items()
        if key.endswith(".ff.net.layers.1.weight")
        and len(value.shape) == 2
        and int(value.shape[1]) == dim
        and int(value.shape[0]) % dim == 0
    }
    if len(candidates) != 1:
        raise RuntimeError(
            f"Mega-53 checkpoint expansion factor is ambiguous: {sorted(candidates)}"
        )
    return candidates.pop()


def _checkpoint_mask_expansion_factor(weights: dict[str, Any], dim: int) -> int:
    candidates = {
        int(value.shape[0]) // dim
        for key, value in weights.items()
        if key.startswith("mask_estimators_")
        and key.endswith(".layers.0.weight")
        and ".to_freqs_" in key
        and len(value.shape) == 2
        and int(value.shape[1]) == dim
        and int(value.shape[0]) % dim == 0
    }
    if len(candidates) != 1:
        raise RuntimeError(
            "Mega-53 checkpoint mask expansion factor is ambiguous: "
            f"{sorted(candidates)}"
        )
    return candidates.pop()


def _construct_split_expansion_model(
    model_type: Any,
    model_args: dict[str, Any],
    *,
    mask_expansion_factor: int,
) -> Any:
    """Keep verified source immutable while separating its conflated dimensions."""

    heads = importlib.import_module("bs_roformer.mlx.heads")
    original = heads.build_mask_estimator

    def build_mask_estimator(**kwargs: Any) -> Any:
        kwargs["mlp_expansion_factor"] = mask_expansion_factor
        return original(**kwargs)

    heads.build_mask_estimator = build_mask_estimator
    try:
        return model_type(**model_args)
    finally:
        heads.build_mask_estimator = original


def load_mega53_model(
    *, checkpoint: Path, config_document: dict[str, Any], source_root: Path
) -> Mega53ModelLoadResult:
    """Perform one weights-only CPU load, exact conversion and strict MLX load."""

    import mlx.core as mx
    from mlx.utils import tree_flatten
    import torch

    install_verified_source_package(source_root)
    from bs_roformer.backends.mlx_backend import MLXBackend
    from bs_roformer.mlx import BSRoformerMLX, convert_torch_to_mlx_weights

    config = SimpleNamespace(
        model=config_document["model"],
        inference=SimpleNamespace(**config_document["inference"]),
        audio=SimpleNamespace(**config_document["audio"]),
    )
    document = torch.load(checkpoint, weights_only=True, map_location="cpu")
    state = checkpoint_state_dict(document)
    checkpoint_inventory = tensor_inventory(state)
    converted = convert_torch_to_mlx_weights(state, variant=None)
    converted_inventory = tensor_inventory(converted)
    model_args = MLXBackend._model_args(config, variation=None)
    declared_expansion = int(model_args["mlp_expansion_factor"])
    checkpoint_expansion = _checkpoint_expansion_factor(
        converted, int(model_args["dim"])
    )
    mask_expansion = _checkpoint_mask_expansion_factor(
        converted, int(model_args["dim"])
    )
    model_args["mlp_expansion_factor"] = checkpoint_expansion
    checkpoint_dtypes = {value.dtype for value in converted.values()}
    if len(checkpoint_dtypes) != 1:
        raise RuntimeError(
            "Mega-53 converted checkpoint uses more than one parameter dtype"
        )
    checkpoint_dtype = checkpoint_dtypes.pop()

    model = _construct_split_expansion_model(
        BSRoformerMLX,
        model_args,
        mask_expansion_factor=mask_expansion,
    )
    model.set_dtype(checkpoint_dtype)
    model.eval()
    constructed = dict(tree_flatten(model.parameters()))
    constructed_inventory = tensor_inventory(constructed)
    compare_exact_mlx_state(constructed, converted)

    model.load_weights(list(converted.items()), strict=True)
    mx.eval(model.parameters())
    loaded = dict(tree_flatten(model.parameters()))
    loaded_inventory = tensor_inventory(loaded)
    if loaded_inventory != constructed_inventory:
        raise RuntimeError("Mega-53 loaded model inventory differs from construction")

    del document
    del state
    del converted
    del constructed
    inference_chunk = int(config_document["inference"]["chunk_size"])
    hop = int(config_document["model"].get("stft_hop_length", 512))
    return Mega53ModelLoadResult(
        model=model,
        evidence={
            "architecture": "BSRoformerMLX, 53 stems, stock MLP heads",
            "checkpoint_inventory": checkpoint_inventory,
            "converted_inventory": converted_inventory,
            "constructed_inventory": constructed_inventory,
            "loaded_inventory": loaded_inventory,
            "state_keys_equal": True,
            "state_shapes_equal": True,
            "state_dtypes_equal": True,
            "load_strict": True,
            "model_retained_until_process_exit": True,
            "config_declared_mlp_expansion_factor": declared_expansion,
            "checkpoint_derived_mlp_expansion_factor": checkpoint_expansion,
            "checkpoint_derived_mask_estimator_expansion_factor": mask_expansion,
            "checkpoint_parameter_dtype": str(checkpoint_dtype),
            "architecture_remediation": {
                "cycles_used": 1,
                "maximum_cycles": 1,
                "reason": (
                    "the verified MLX port conflates transformer and mask-head "
                    "expansion; the exact checkpoint requires factors 4 and 2 "
                    "respectively, and its converted parameters are float16"
                ),
                "derivation": "checkpoint tensor shapes and dtypes only",
            },
            "native_role_count": int(config_document["model"]["num_stems"]),
            "target_role": "synth",
            "inference_chunk_size": inference_chunk,
            "stft_hop_length": hop,
            "chunk_alignment_valid_for_inference": inference_chunk % hop == 0,
        },
    )


__all__ = ["Mega53ModelLoadResult", "load_mega53_model"]
