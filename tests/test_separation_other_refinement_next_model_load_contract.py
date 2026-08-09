from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess

import pytest

from sunofriend.separation_other_refinement_next_model_load_contract import (
    CHECKPOINT,
    CONFIG,
    EXPECTED_EFFECTS,
    EXPECTED_GUARDS,
    EXPECTED_MODEL_INVENTORIES,
    MODEL_LOAD_REPORT_SCHEMA,
    MODEL_LOAD_REPORT_STATUS,
    PROFILE_ID,
    RUNTIME,
    SOURCE,
    build_model_load_receipt,
    model_load_report_sha256,
    validate_model_load_report,
)


ROOT = Path(__file__).resolve().parents[1]


def _report() -> dict[str, object]:
    common = copy.deepcopy(EXPECTED_MODEL_INVENTORIES["converted"])
    value: dict[str, object] = {
        "schema": MODEL_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": MODEL_LOAD_REPORT_STATUS,
        "profile_id": PROFILE_ID,
        "checkpoint": CHECKPOINT,
        "config": CONFIG,
        "source": SOURCE,
        "runtime": RUNTIME,
        "model": {
            "architecture": "BSRoformerMLX, 53 stems, stock MLP heads",
            "checkpoint_inventory": copy.deepcopy(
                EXPECTED_MODEL_INVENTORIES["checkpoint"]
            ),
            "converted_inventory": common,
            "constructed_inventory": copy.deepcopy(common),
            "loaded_inventory": copy.deepcopy(common),
            "state_keys_equal": True,
            "state_shapes_equal": True,
            "state_dtypes_equal": True,
            "load_strict": True,
            "model_retained_until_process_exit": True,
            "config_declared_mlp_expansion_factor": 2,
            "checkpoint_derived_mlp_expansion_factor": 4,
            "checkpoint_derived_mask_estimator_expansion_factor": 2,
            "checkpoint_parameter_dtype": "mlx.core.float16",
            "architecture_remediation": {
                "cycles_used": 1,
                "maximum_cycles": 1,
                "reason": "fixture",
                "derivation": "checkpoint tensor shapes and dtypes only",
            },
            "native_role_count": 53,
            "target_role": "synth",
            "inference_chunk_size": 882000,
            "stft_hop_length": 512,
            "chunk_alignment_valid_for_inference": False,
        },
        "guards": copy.deepcopy(EXPECTED_GUARDS),
        "effects": copy.deepcopy(EXPECTED_EFFECTS),
    }
    value["report_sha256"] = model_load_report_sha256(value)
    return value


def test_model_load_contract_validates_and_builds_narrow_receipt(tmp_path: Path) -> None:
    report = _report()
    assert validate_model_load_report(report) == report
    receipt = build_model_load_receipt(
        report, published_root=tmp_path.resolve(), recorded_at="now"
    )
    assert receipt["checkpoint_loaded"] is True
    assert receipt["inference_performed"] is False
    assert receipt["audio_processed"] is False
    assert "inference" in receipt["not_approved"]


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("effects", "inference_runs"), 1, "effects differ"),
        (("guards", "restricted_torch_load_calls"), 2, "guards differ"),
        (("model", "state_dtypes_equal"), False, "dtypes were not equal"),
        (("model", "chunk_alignment_valid_for_inference"), True, "unaligned"),
    ],
)
def test_model_load_contract_rejects_boundary_changes(
    path: tuple[str, str], value: object, message: str
) -> None:
    report = _report()
    report[path[0]][path[1]] = value  # type: ignore[index]
    report["report_sha256"] = model_load_report_sha256(report)
    with pytest.raises(ValueError, match=message):
        validate_model_load_report(report)


def test_model_load_route_requires_specific_acceptance(tmp_path: Path) -> None:
    setup = ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    result = subprocess.run(
        [str(setup), "--construct-and-load-model"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "separation"),
        },
    )

    assert result.returncode == 2
    assert "requires --accept-restricted-model-load" in result.stderr
    assert not (tmp_path / "separation").exists()


def test_model_load_route_is_exact_offline_and_has_no_forward_or_audio() -> None:
    setup = (
        ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    ).read_text(encoding="utf-8")
    verifier = (
        ROOT / "scripts" / "verify-separation-other-refinement-next-model-load.py"
    ).read_text(encoding="utf-8")
    loader = (
        ROOT / "src" / "sunofriend" / "separation_other_refinement_next_model_loading.py"
    ).read_text(encoding="utf-8")
    guard = (
        ROOT / "src" / "sunofriend" / "separation_other_refinement_next_execution_guard.py"
    ).read_text(encoding="utf-8")

    assert "--construct-and-load-model" in setup
    assert "--accept-restricted-model-load" in setup
    assert "(deny network*)" in setup
    assert '"$RUNTIME_IMPORT_ROOT/runtime/bin/python" -I -B "$MODEL_LOAD_SCRIPT"' in setup
    assert "weights_only=True, map_location=\"cpu\"" in loader
    assert "model.load_weights(list(converted.items()), strict=True)" in loader
    assert "compare_exact_mlx_state(constructed, converted)" in loader
    assert "from .separation_bs_roformer_mlx_runtime import" in loader
    assert "forward_calls = 0" in guard
    assert "AUDIO_SUFFIXES" in guard
    assert "load_mega53_model(" in verifier
    assert ".separate(" not in verifier
    assert "soundfile" not in verifier
