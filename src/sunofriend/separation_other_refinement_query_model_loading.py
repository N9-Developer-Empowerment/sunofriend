"""Strict local checkpoint loading for the Banquet/PaSST evidence gate.

The caller owns filesystem and network guards.  This module owns only the exact
weights-only load sequence, state compatibility checks and retained model
objects.  It contains no forward call or audio interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
from torch import nn

from .separation_other_refinement_query_load_contract import EXPECTED_MODEL_STATES
from .separation_other_refinement_query_model_adapter import (
    BanquetLoadAdapter,
    new_passt,
)


@dataclass(frozen=True)
class QueryModelLoadResult:
    """The two retained models and their report-ready compatibility evidence."""

    banquet: nn.Module
    passt: nn.Module
    evidence: dict[str, Any]


def _state_dict(document: Any, label: str) -> dict[str, torch.Tensor]:
    candidate = document.get("state_dict") if isinstance(document, dict) else None
    if candidate is None and isinstance(document, dict):
        candidate = document
    if not isinstance(candidate, dict) or not candidate:
        raise RuntimeError(f"{label} checkpoint has no state dictionary")
    if any(not isinstance(key, str) for key in candidate):
        raise RuntimeError(f"{label} state dictionary contains a non-string key")
    if any(not torch.is_tensor(value) for value in candidate.values()):
        raise RuntimeError(f"{label} state dictionary contains a non-tensor value")
    return candidate


def _inventory(state: dict[str, torch.Tensor]) -> dict[str, Any]:
    tensors = {
        key: {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "numel": value.numel(),
            "device": str(value.device),
            "requires_grad": bool(value.requires_grad),
        }
        for key, value in sorted(state.items())
    }
    return {
        "key_count": len(tensors),
        "total_numel": sum(value["numel"] for value in tensors.values()),
        "inventory_sha256": hashlib.sha256(
            json.dumps(tensors, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _verify_state_contract(
    label: str,
    model_state: dict[str, torch.Tensor],
    checkpoint_state: dict[str, torch.Tensor],
) -> dict[str, Any]:
    model_keys = set(model_state)
    checkpoint_keys = set(checkpoint_state)
    missing = sorted(model_keys - checkpoint_keys)
    unexpected = sorted(checkpoint_keys - model_keys)
    if missing or unexpected:
        raise RuntimeError(
            f"{label} state keys differ: missing={missing[:8]}, unexpected={unexpected[:8]}"
        )
    shape_mismatches = []
    dtype_mismatches = []
    for key in sorted(model_keys):
        if model_state[key].shape != checkpoint_state[key].shape:
            shape_mismatches.append(
                {
                    "key": key,
                    "model": list(model_state[key].shape),
                    "checkpoint": list(checkpoint_state[key].shape),
                }
            )
        if model_state[key].dtype != checkpoint_state[key].dtype:
            dtype_mismatches.append(
                {
                    "key": key,
                    "model": str(model_state[key].dtype),
                    "checkpoint": str(checkpoint_state[key].dtype),
                }
            )
    if shape_mismatches or dtype_mismatches:
        raise RuntimeError(
            f"{label} state tensor contracts differ: "
            f"shape={shape_mismatches[:4]}, dtype={dtype_mismatches[:4]}"
        )
    inventory = _inventory(checkpoint_state)
    expected = EXPECTED_MODEL_STATES[label]
    for field in ("inventory_sha256", "key_count", "total_numel"):
        if inventory[field] != expected[field]:
            raise RuntimeError(f"{label} checkpoint {field} differs")
    return {
        "keys_equal": True,
        "shapes_equal": True,
        "dtypes_equal": True,
        **inventory,
    }


def load_query_models(
    paths: Mapping[str, Path],
    load_calls: Sequence[str],
) -> QueryModelLoadResult:
    """Construct and strictly load the two exact state-compatible models."""

    passt_document = torch.load(
        paths["passt"],
        weights_only=True,
        map_location="cpu",
    )
    passt_state = _state_dict(passt_document, "passt")
    passt_model = new_passt(n_classes=20).eval()
    passt_contract = _verify_state_contract(
        "passt", passt_model.state_dict(), passt_state
    )
    passt_result = passt_model.load_state_dict(passt_state, strict=True)
    if passt_result.missing_keys or passt_result.unexpected_keys:
        raise RuntimeError("PaSST strict load returned unresolved keys")
    del passt_document
    del passt_state

    banquet_document = torch.load(
        paths["banquet"],
        weights_only=True,
        map_location="cpu",
    )
    raw_banquet_state = _state_dict(banquet_document, "banquet")
    if not all(key.startswith("model.") for key in raw_banquet_state):
        raise RuntimeError("Banquet checkpoint state is not rooted at model")
    banquet_state = {
        key.removeprefix("model."): value for key, value in raw_banquet_state.items()
    }
    banquet_model = BanquetLoadAdapter().eval()
    banquet_contract = _verify_state_contract(
        "banquet",
        {f"model.{key}": value for key, value in banquet_model.state_dict().items()},
        raw_banquet_state,
    )
    banquet_result = banquet_model.load_state_dict(banquet_state, strict=True)
    if banquet_result.missing_keys or banquet_result.unexpected_keys:
        raise RuntimeError("Banquet strict load returned unresolved keys")
    del banquet_document
    del raw_banquet_state
    del banquet_state

    if list(load_calls) != [str(paths["passt"]), str(paths["banquet"])]:
        raise RuntimeError("restricted model load order differs")
    return QueryModelLoadResult(
        banquet=banquet_model,
        passt=passt_model,
        evidence={
            "passt": {
                **passt_contract,
                "architecture": "OpenMIC PaSST, pretrained=False, 20 classes",
                "strict_load_missing_keys": [],
                "strict_load_unexpected_keys": [],
            },
            "banquet": {
                **banquet_contract,
                "architecture": (
                    "pinned setup-C PasstFiLMConditionedBandit load adapter, "
                    "64 musical bands, 8 sequential band modules, embedded "
                    "OpenMIC PaSST pretrained=False with 527 classes"
                ),
                "checkpoint_root_prefix_removed_for_load": "model.",
                "strict_load_missing_keys": [],
                "strict_load_unexpected_keys": [],
            },
            "models_retained_until_process_exit": True,
        },
    )


__all__ = ["QueryModelLoadResult", "load_query_models"]
