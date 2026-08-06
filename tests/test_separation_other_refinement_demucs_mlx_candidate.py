from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess

import pytest

from sunofriend.separation_other_refinement_demucs_mlx_candidate import (
    DIRECT_ARTIFACT_DOWNLOAD_BYTES,
    MAXIMUM_SETUP_DOWNLOAD_BYTES,
    MODEL_SOURCE_ORDER,
    PLAN_SCHEMA,
    RUNTIME_REQUIREMENTS_BYTES,
    RUNTIME_REQUIREMENTS_SHA256,
    SETUP_PLAN_SCHEMA,
    demucs_mlx_other_refinement_candidate_plan,
    normalize_pinned_six_source_config,
)
from sunofriend.separation_profiles import (
    OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
    separation_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict[str, object]:
    return {
        "model_name": "htdemucs_6s",
        "model_class": "BagOfModelsMLX",
        "sub_model_class": "HTDemucsMLX",
        "num_models": 1,
        "weights": [[1.0] * 6],
        "args": [],
        "kwargs": {
            "sources": list(MODEL_SOURCE_ORDER),
            "audio_channels": 2,
            "samplerate": 44_100,
            "segment": "39/5",
        },
        "mlx_version": "0.30.3",
        "tensor_count": 565,
    }


def test_candidate_profile_is_exact_blocked_and_studio_only() -> None:
    profile = separation_profile(OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID)

    assert profile.profile_id == "demucs-mlx-htdemucs-6s-other-refinement-v1"
    assert profile.scope_id == "other-refinement-v1"
    assert profile.status == "blocked"
    assert profile.target_release_tier == "studio_challenger"
    assert profile.executable is False
    assert profile.supported_roles == MODEL_SOURCE_ORDER
    assert profile.runtime_wheel_sha256 == (
        "dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64"
    )
    assert profile.artifact("weights").bytes == 109_726_583
    assert profile.artifact("weights").sha256 == (
        "d298f7f746bf53c21baad44fb08e88807ef47feb551dd22f1601a546c85b8e02"
    )
    assert profile.artifact("config").bytes == 1_946
    assert profile.artifact("config").sha256 == (
        "97f8315891d8edc9aa6f59e56e0d352fbad5ebfb8a4faf46341ab2f1844596a9"
    )
    assert profile.worker_script == "not-available"


def test_candidate_plan_requests_setup_only_and_has_no_effects() -> None:
    plan = demucs_mlx_other_refinement_candidate_plan()

    assert plan["schema"] == PLAN_SCHEMA
    assert plan["status"] == "approval_required_no_install_or_execution"
    assert plan["profile"]["profile_id"] == (
        "demucs-mlx-htdemucs-6s-other-refinement-v1"
    )
    assert plan["checkpoint"]["bytes"] == 109_726_583
    assert plan["config"]["model_source_order"] == list(MODEL_SOURCE_ORDER)
    assert plan["target_mapping"]["keys"]["model_role"] == "piano"
    assert plan["target_mapping"]["keys"]["semantic_status"] == (
        "disclosed_piano_proxy_not_general_keys"
    )
    remediation = plan["known_runtime_failure_and_remediation"]
    assert remediation["same_string_representation_observed"] is True
    assert remediation["pinned_config_mutation_permitted"] is False
    assert remediation["maximum_remediation_cycles"] == 1
    assert remediation["compatibility_passed"] is False
    setup = plan["setup_plan"]
    assert setup["schema"] == SETUP_PLAN_SCHEMA
    assert setup["runtime_lock"] == {
        "path": "separation-core-four-runtime-requirements.txt",
        "bytes": RUNTIME_REQUIREMENTS_BYTES,
        "sha256": RUNTIME_REQUIREMENTS_SHA256,
        "package_count": 9,
        "pip_require_hashes": True,
        "pytorch_free": True,
    }
    assert DIRECT_ARTIFACT_DOWNLOAD_BYTES == 109_735_289
    assert setup["download_budget"]["direct_pinned_artifact_bytes"] == (
        DIRECT_ARTIFACT_DOWNLOAD_BYTES
    )
    assert MAXIMUM_SETUP_DOWNLOAD_BYTES == 1_073_741_824
    assert setup["download_budget"]["maximum_total_network_bytes"] == (
        MAXIMUM_SETUP_DOWNLOAD_BYTES
    )
    assert setup["post_install_inspection"]["model_constructed"] is False
    assert setup["post_install_inspection"]["inference_runs"] == 0
    assert all(not value for value in plan["effects"].values())


def test_fraction_remediation_is_exact_in_memory_and_non_mutating() -> None:
    original = _config()
    before = copy.deepcopy(original)

    normalized = normalize_pinned_six_source_config(original)

    assert original == before
    assert original["kwargs"]["segment"] == "39/5"
    assert normalized["kwargs"]["segment"] == 7.8
    assert normalized is not original
    assert normalized["kwargs"] is not original["kwargs"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["kwargs"].update(segment="7.8"), "segment text"),
        (lambda value: value["kwargs"].update(sources=list(reversed(MODEL_SOURCE_ORDER))), "role order"),
        (lambda value: value.update(tensor_count=564), "tensor count"),
        (lambda value: value.update(model_name="htdemucs"), "model name"),
    ],
)
def test_fraction_remediation_rejects_semantic_drift(mutation, message: str) -> None:
    config = _config()
    mutation(config)

    with pytest.raises(ValueError, match=message):
        normalize_pinned_six_source_config(config)


def test_plan_script_is_deterministic_and_writes_nothing(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    command = [
        str(ROOT / ".venv/bin/python"),
        str(ROOT / "scripts/plan-separation-other-refinement-demucs-mlx.py"),
    ]
    first = subprocess.run(
        command, cwd=tmp_path, check=False, capture_output=True, text=True
    )
    second = subprocess.run(
        command, cwd=tmp_path, check=False, capture_output=True, text=True
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert set(tmp_path.iterdir()) == before


def test_setup_plan_is_inert_and_install_requires_both_acceptances(
    tmp_path: Path,
) -> None:
    script = (
        ROOT / "scripts/setup-separation-other-refinement-demucs-mlx-macos.sh"
    )
    environment = {
        **os.environ,
        "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "data"),
    }

    planned = subprocess.run(
        [str(script), "--plan"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    refused = subprocess.run(
        [str(script), "--install"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert planned.returncode == 0, planned.stderr
    assert "nothing was downloaded, installed, deserialized, constructed or executed" in (
        planned.stdout
    )
    assert "requires separate explicit approval" in planned.stdout
    assert "will not authorize model construction" in planned.stdout
    assert refused.returncode == 2
    assert "requires both --accept-model-terms" in refused.stderr
    assert not (tmp_path / "data").exists()


def test_setup_static_inspection_cannot_load_or_execute_the_model() -> None:
    setup = (
        ROOT / "scripts/setup-separation-other-refinement-demucs-mlx-macos.sh"
    ).read_text(encoding="utf-8")
    inspector = (
        ROOT
        / "src/sunofriend/separation_other_refinement_demucs_mlx_inspection.py"
    ).read_text(encoding="utf-8")

    approval_check = setup.index('if [ "$ACCEPTED_TERMS" != true ]')
    first_staging_write = setup.index('mkdir -p "$DATA_ROOT"')
    assert approval_check < first_staging_write
    assert "(deny network*)" in setup
    assert "--require-hashes" in setup
    assert "--max-filesize" in setup
    assert "import mlx" not in inspector
    assert "import demucs_mlx" not in inspector
    assert "safetensors.mlx" not in inspector
    assert "checkpoint_payload_opened\": False" in inspector
    assert "inference_runs\": 0" in inspector
