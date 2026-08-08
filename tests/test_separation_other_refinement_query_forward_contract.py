from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_forward_contract import (
    PINNED_SOURCE_SHA256,
    build_query_forward_contract,
    validate_query_forward_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def test_forward_contract_is_exact_and_has_no_effects() -> None:
    contract = build_query_forward_contract()

    assert contract["status"] == "source_bound_implementation_ready_not_executed"
    assert contract["source"]["file_sha256"] == PINNED_SOURCE_SHA256
    assert len(PINNED_SOURCE_SHA256) == 9
    assert contract["configuration"]["bands"] == 64
    assert contract["configuration"]["tf_residual_gru_modules"] == 16
    assert contract["configuration"]["query_encoder"]["embedding"] == 768
    assert [step["operation"] for step in contract["forward_steps"]] == [
        "mixture_stft",
        "musical_band_split",
        "residual_time_frequency_grus",
        "query_passt_embedding",
        "film_conditioning",
        "complex_mask_estimation_and_frequency_overlap_add",
        "mask_mixture_and_inverse_stft",
    ]
    assert contract["implementation_boundary"]["forward_math_implemented"] is True
    assert contract["implementation_boundary"]["synthetic_runner_implemented"] is True
    assert contract["implementation_boundary"]["single_use_forward_adapter"] is True
    assert contract["effects"]["inference_runs"] == 0
    assert not any(
        value is True
        for key, value in contract["effects"].items()
        if key not in {"inference_runs", "audio_reads", "audio_writes"}
    )
    assert validate_query_forward_contract(contract) == contract


def test_forward_contract_rejects_source_or_configuration_mutation() -> None:
    contract = copy.deepcopy(build_query_forward_contract())
    contract["configuration"]["bands"] = 63

    with pytest.raises(ValueError, match="differs from the pinned contract"):
        validate_query_forward_contract(contract)


def test_forward_contract_script_only_prints_the_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "plan-separation-other-refinement-query-forward.py"
            ),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == build_query_forward_contract()
