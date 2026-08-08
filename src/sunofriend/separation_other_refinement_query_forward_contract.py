"""Pure, source-bound contract for the proposed Banquet synthetic forward.

This module describes the exact pinned upstream forward path and setup-C model
configuration.  It deliberately imports no model or audio runtime, constructs
nothing and exposes no inference function.  The separate, single-use adapter
and approved runner must validate this immutable document before execution.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .separation_other_refinement_query_load_contract import (
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_PROFILE_ID,
)


QUERY_FORWARD_CONTRACT_SCHEMA = (
    "sunofriend.other-refinement-query-forward-contract.v1"
)

PINNED_SOURCE_SHA256 = {
    "core/models/e2e/bandit/bandit.py": (
        "4bc60d09c567e83539ca5b51422c5ebf158971a3af3a8519c74ffea456004dcb"
    ),
    "core/models/e2e/bandit/bandsplit.py": (
        "61971985bd9314012151152d3d49c74f40ab0a19e72c0867b11ebfd39a8b2d89"
    ),
    "core/models/e2e/bandit/maskestim.py": (
        "1b04032dde1b2dae622e3d0fa6626cafb7dcedfaa558bee2fb9216b19c39ed5c"
    ),
    "core/models/e2e/bandit/tfmodel.py": (
        "364a76bdf45f68c7a8445e5f0ac892efcfd94f3157bd573bdfdefcc52cdb0ebb"
    ),
    "core/models/e2e/querier/passt.py": (
        "9513322b60e945be1a96b6bbb872f39310ddd9fe9d00591294847a8dc1c2859d"
    ),
    "core/models/e2e/conditioners/film.py": (
        "2f2cd916a602acad698f4c5b7c767380fcecbd3a287a9338d3be111685f54f70"
    ),
    "core/models/e2e/conditioners/base.py": (
        "e13345f55462261e105d7f1b70a098f2be81da3175064bb8aec20cc1b9cdb971"
    ),
    "config/models/bandit-query-pre.yml": (
        "124db6059cf9395d2bb0d2e91fb2eb3479e83281aa893eadee435cb3e636aa94"
    ),
    "expt/setup-c/bandit-everything-query-pre-d-aug.yml": (
        "26d204e259ee9ba55897b573d6e500f1d0d1471355b3e7e2d64885465b38bd0c"
    ),
}


def query_forward_contract_sha256(value: dict[str, Any]) -> str:
    """Return the canonical digest with the document self-hash omitted."""

    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_query_forward_contract() -> dict[str, Any]:
    """Describe the implemented forward path without constructing or running it."""

    contract: dict[str, Any] = {
        "schema": QUERY_FORWARD_CONTRACT_SCHEMA,
        "document_sha256": "",
        "status": "source_bound_implementation_ready_not_executed",
        "profile_id": QUERY_PROFILE_ID,
        "source": {
            "repository": "https://github.com/kwatcharasupat/query-bandit",
            "revision": QUERY_BANDIT_SOURCE_REVISION,
            "file_sha256": PINNED_SOURCE_SHA256,
        },
        "configuration": {
            "mixture_sample_rate_hz": 44_100,
            "mixture_channels": 2,
            "band_type": "musical",
            "bands": 64,
            "band_embedding": 128,
            "tf_residual_gru_pairs": 8,
            "tf_residual_gru_modules": 16,
            "gru_hidden_size": 256,
            "gru_bidirectional": True,
            "mask_mlp_hidden_size": 512,
            "mask_mlp_activation": "tanh",
            "complex_masks": True,
            "overlap_add_frequency_weights": True,
            "film": {
                "group_norm_groups": 8,
                "multiplicative": True,
                "additive": True,
                "order": ["multiplicative", "additive"],
                "query_embedding": 768,
            },
            "stft": {
                "n_fft": 2_048,
                "win_length": 2_048,
                "hop_length": 512,
                "normalized": True,
                "center": True,
                "pad_mode": "reflect",
                "onesided": True,
            },
            "query_encoder": {
                "channel_reduction": "mean",
                "sample_rate_hz": 32_000,
                "mel_bins": 128,
                "time_frames": 998,
                "embedding": 768,
                "pretrained_network_resolution": False,
            },
        },
        "forward_steps": [
            {
                "step": 1,
                "operation": "mixture_stft",
                "input_shape": ["batch", 2, "samples"],
                "output_shape": ["batch", 2, 1_025, "frames"],
                "dtype": "complex",
            },
            {
                "step": 2,
                "operation": "musical_band_split",
                "output_shape": ["batch", 64, "frames", 128],
            },
            {
                "step": 3,
                "operation": "residual_time_frequency_grus",
                "module_count": 16,
                "axis_order": ["time", "frequency"],
            },
            {
                "step": 4,
                "operation": "query_passt_embedding",
                "channel_reduction": "mean",
                "resample_hz": 32_000,
                "mel_time_frames": 998,
                "output_shape": ["batch", 768],
            },
            {
                "step": 5,
                "operation": "film_conditioning",
                "conditioned_shape": ["batch", 128, 64, "frames"],
                "output_shape": ["batch", 64, "frames", 128],
            },
            {
                "step": 6,
                "operation": "complex_mask_estimation_and_frequency_overlap_add",
                "mask_heads": 64,
                "output_shape": ["batch", 2, 1_025, "frames"],
            },
            {
                "step": 7,
                "operation": "mask_mixture_and_inverse_stft",
                "inverse_stft_length": "exact_mixture_input_samples",
                "output_shape": ["batch", 2, "samples"],
            },
        ],
        "implementation_boundary": {
            "forward_math_implemented": True,
            "synthetic_runner_implemented": True,
            "report_validator_implemented": True,
            "load_adapter_still_has_no_forward_method": True,
            "single_use_forward_adapter": True,
            "upstream_cli_allowed": False,
            "upstream_checkpoint_loader_allowed": False,
        },
        "effects": {
            "network_used": False,
            "checkpoint_opened": False,
            "model_constructed": False,
            "inference_runs": 0,
            "generated_tensors_created": False,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    contract["document_sha256"] = query_forward_contract_sha256(contract)
    return contract


def validate_query_forward_contract(value: dict[str, Any]) -> dict[str, Any]:
    """Reject source, configuration or authority mutation."""

    expected = build_query_forward_contract()
    if value != expected:
        raise ValueError("query forward contract differs from the pinned contract")
    if value["document_sha256"] != query_forward_contract_sha256(value):
        raise ValueError("query forward contract document hash differs")
    return value


__all__ = [
    "PINNED_SOURCE_SHA256",
    "QUERY_FORWARD_CONTRACT_SCHEMA",
    "build_query_forward_contract",
    "query_forward_contract_sha256",
    "validate_query_forward_contract",
]
