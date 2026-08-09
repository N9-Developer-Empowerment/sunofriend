from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend.separation_bs_roformer_sw_load_contract import (
    EXPECTED_EFFECTS,
    EXPECTED_GUARDS,
    SW_LOAD_REPORT_SCHEMA,
    SW_LOAD_REPORT_STATUS,
    SW_PROFILE_ID,
    sw_load_report_sha256,
    validate_sw_load_report,
)
from sunofriend.separation_fine_stem_canary_contract import (
    SW_CHECKPOINT,
    SW_CONFIG,
    SW_NATIVE_ROLES,
)
from sunofriend.separation_other_refinement_next_model_load_contract import (
    RUNTIME,
    SOURCE,
)


def _inventory() -> dict[str, object]:
    return {"key_count": 2, "total_numel": 3, "inventory_sha256": "0" * 64}


def _report() -> dict:
    report = {
        "schema": SW_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": SW_LOAD_REPORT_STATUS,
        "profile_id": SW_PROFILE_ID,
        "checkpoint": SW_CHECKPOINT,
        "config": SW_CONFIG,
        "source": SOURCE,
        "runtime": RUNTIME,
        "model": {
            "architecture": "BSRoformerMLX, six-role SW checkpoint",
            "checkpoint_inventory": _inventory(),
            "converted_inventory": _inventory(),
            "constructed_inventory": _inventory(),
            "loaded_inventory": _inventory(),
            "state_keys_equal": True,
            "state_shapes_equal": True,
            "state_dtypes_equal": True,
            "load_strict": True,
            "model_retained_until_process_exit": True,
            "native_roles": list(SW_NATIVE_ROLES),
            "native_role_count": 6,
            "target_role": "guitar",
            "target_role_index": 4,
            "chunk_size": 588800,
            "num_overlap": 2,
            "stft_hop_length": 512,
        },
        "guards": EXPECTED_GUARDS,
        "effects": EXPECTED_EFFECTS,
    }
    report["report_sha256"] = sw_load_report_sha256(report)
    return report


def test_sw_load_report_is_strict_and_authority_bounded() -> None:
    report = _report()
    assert validate_sw_load_report(report) == report
    changed = json.loads(json.dumps(report))
    changed["effects"]["inference_runs"] = 1
    changed["report_sha256"] = sw_load_report_sha256(changed)
    with pytest.raises(ValueError, match="effects differ"):
        validate_sw_load_report(changed)


def test_sw_load_verifier_has_one_weights_only_load_and_no_inference() -> None:
    source = (
        Path(__file__).parents[1]
        / "scripts/verify-separation-bs-roformer-sw-model-load.py"
    ).read_text()
    loader = (
        Path(__file__).parents[1]
        / "src/sunofriend/separation_bs_roformer_sw_loading.py"
    ).read_text()
    assert "weights_only=True, map_location=\"cpu\"" in loader
    assert "compare_exact_mlx_state(constructed, converted)" in loader
    assert "model.load_weights(list(converted.items()), strict=True)" in loader
    assert "load_sw_model(" in source
    assert ".separate(" not in source
    assert "record_forward" not in source
