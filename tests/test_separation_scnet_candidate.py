from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from sunofriend.separation_scnet_candidate import (
    SCNET_CANDIDATE_PLAN_SCHEMA,
    SCNET_CHECKPOINT_BYTES,
    SCNET_CHECKPOINT_SHA256,
    SCNET_PARAMETER_COUNT,
    SCNET_RUNTIME_WHEEL_BYTES,
    SCNET_SETUP_PLAN_SCHEMA,
    SCNET_SOURCE_REVISION,
    SCNET_STATE_DICT_BYTES,
    SCNET_TOTAL_DOWNLOAD_BYTES,
    scnet_candidate_plan,
)
from sunofriend.separation_scnet_compatibility import (
    _normalize_uniform_prefix,
    _state_mapping,
)


ROOT = Path(__file__).resolve().parents[1]


def test_scnet_profile_plan_is_public_opt_in_and_has_no_effects() -> None:
    plan = scnet_candidate_plan()

    assert plan["schema"] == SCNET_CANDIDATE_PLAN_SCHEMA
    assert plan["status"] == "public_opt_in"
    assert plan["profile"]["profile_id"] == "scnet-large-musdb-release-v1"
    assert plan["installation_enabled"] is True
    assert plan["compatibility_inspection_enabled"] is True
    assert plan["synthetic_execution_enabled"] is True
    assert plan["execution_enabled"] is True
    assert plan["checkpoint"]["bytes"] == SCNET_CHECKPOINT_BYTES == 168_848_417
    assert plan["checkpoint"]["sha256"] == SCNET_CHECKPOINT_SHA256 == (
        "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
    )
    assert plan["checkpoint"]["separate_terms_file"] is None
    assert plan["checkpoint"]["provisional_terms_evidence_accepted"] is True
    assert plan["checkpoint"]["immutable_artifact_identity_complete"] is True
    assert plan["config"]["roles"] == ["drums", "bass", "other", "vocals"]
    assert plan["proposed_adapter"]["runtime_wheel_download_bytes"] == (
        SCNET_RUNTIME_WHEEL_BYTES
    )
    setup = plan["compatibility_setup_plan"]
    assert setup["schema"] == SCNET_SETUP_PLAN_SCHEMA
    assert setup["future_install_command_enabled"] is True
    assert setup["download_budget"]["exact_expected_total_bytes"] == (
        SCNET_TOTAL_DOWNLOAD_BYTES
    )
    assert SCNET_TOTAL_DOWNLOAD_BYTES == 264_851_903
    assert setup["runtime_lock"]["package_count"] == 12
    assert setup["runtime_lock"]["pip_require_hashes"] is True
    assert setup["compatibility_acceptance"]["weights_only_loader_required"] is True
    assert setup["compatibility_acceptance"]["forward_pass_allowed"] is False
    assert setup["remediation_policy"]["maximum_remediation_cycles"] == 1
    assert plan["synthetic_canary"]["status"] == "objective_pass"
    assert plan["synthetic_canary"]["maximum_reconstruction_error_lsb"] == 0
    assert plan["synthetic_canary"]["subjective_quality_threshold"] is None
    assert all(not values for values in plan["effects"].values())


def test_scnet_checkpoint_free_architecture_evidence_is_exact() -> None:
    probe = scnet_candidate_plan()["architecture_probe"]

    assert probe["checkpoint_loaded"] is False
    assert probe["audio_processed"] is False
    assert probe["network_denied"] is True
    assert probe["parameter_count"] == SCNET_PARAMETER_COUNT == 42_181_232
    assert SCNET_STATE_DICT_BYTES == 168_724_928
    assert probe["uncompressed_state_dict_bytes"] == SCNET_STATE_DICT_BYTES
    assert probe["source_revision"] == SCNET_SOURCE_REVISION == (
        "6236f8c559778dc271e1aea9baa3993ae655e905"
    )
    assert probe["maximum_resident_set_bytes"] == 380_043_264


def test_scnet_plan_script_only_prints_the_no_write_record(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/plan-separation-core-four-scnet.py"),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "public_opt_in"
    assert set(tmp_path.iterdir()) == before


def test_scnet_setup_plan_is_read_only_and_install_requires_both_acceptances(
    tmp_path: Path,
) -> None:
    script = ROOT / "scripts/setup-separation-core-four-scnet-macos.sh"
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

    assert planned.returncode == 0
    assert "nothing was downloaded, installed, deserialized or executed" in (
        planned.stdout
    )
    assert "requires separate explicit approval" in planned.stdout
    assert refused.returncode == 2
    assert "requires both --accept-model-terms" in refused.stderr
    assert not (tmp_path / "data").exists()


def test_scnet_compatibility_allows_only_official_wrapper_and_one_prefix() -> None:
    class FakeTensor:
        pass

    tensor = FakeTensor()
    state, container, wrapper_cycles = _state_mapping(
        {"state": {"module.encoder.weight": tensor}},
        tensor_type=FakeTensor,
    )
    normalized, removed_prefix, remediation_cycles = _normalize_uniform_prefix(
        state,
        {"encoder.weight"},
    )

    assert container == "official_state_wrapper"
    assert wrapper_cycles == 0
    assert normalized == {"encoder.weight": tensor}
    assert removed_prefix == "module."
    assert remediation_cycles == 1

    best_state, best_container, best_wrapper_cycles = _state_mapping(
        {"best_state": {"encoder.weight": tensor}},
        tensor_type=FakeTensor,
    )
    assert best_state == {"encoder.weight": tensor}
    assert best_container == "official_best_state_wrapper"
    assert best_wrapper_cycles == 1


def test_scnet_enabled_setup_keeps_inspection_weights_only_and_offline() -> None:
    inspector = (
        ROOT / "src/sunofriend/separation_scnet_compatibility.py"
    ).read_text(encoding="utf-8")
    setup = (
        ROOT / "scripts/setup-separation-core-four-scnet-macos.sh"
    ).read_text(encoding="utf-8")

    assert "weights_only=True" in inspector
    assert 'map_location="cpu"' in inspector
    assert "model.load_state_dict(normalized_state, strict=True)" in inspector
    assert "forward_passes\": 0" in inspector
    assert "--max-filesize \"$scnet_max_bytes\"" in setup
    assert "ulimit -f 2097152" in setup
    assert "(deny network*)" in setup
    assert "--require-hashes" in setup
