from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_next_challenger import (
    build_next_challenger_plan,
    validate_next_challenger_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def test_next_challenger_is_synth_first_and_no_effects() -> None:
    plan = build_next_challenger_plan()

    assert plan["priority"] == ["synth", "guitar", "wind"]
    assert plan["candidate"]["first_target"] == "synth"
    assert "never a proxy" in plan["piano_policy"]
    assert plan["registered"] is False
    assert plan["executable"] is False
    assert plan["status"] == "model_load_verified_synthetic_inference_not_authorized"
    assert not any(plan["effects"].values())
    assert validate_next_challenger_plan(plan) == plan


def test_next_challenger_pins_source_artifacts_and_safe_loader() -> None:
    plan = build_next_challenger_plan()
    source = plan["runtime_source"]
    checkpoint = plan["artifacts"]["checkpoint"]

    assert source["revision"] == "de35ada5817b878da0194ee2860253dda3a9c2b2"
    assert source["backend"] == "mlx"
    assert source["automatic_download_allowed"] is False
    assert source["download_missing"] is False
    assert source["upstream_unrestricted_torch_load_allowed"] is False
    assert "weights_only=True" in source["required_loader"]
    assert checkpoint["declared_bytes"] == 1_368_919_887
    assert checkpoint["declared_sha256"] == (
        "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"
    )
    assert checkpoint["locally_verified"] is True
    assert checkpoint["observed_sha256"] == checkpoint["declared_sha256"]
    assert checkpoint["download_authorized"] is False
    assert checkpoint["evidence_download_status"] == "complete_authority_consumed"
    assert plan["artifacts"]["evidence_sha256"] == (
        "d855138176807a7ca8738bd660141eb2b142676e41ccf56014be64e53f012a24"
    )
    assert plan["runtime_wheel_evidence"]["package_count"] == 29
    assert plan["runtime_wheel_evidence"]["wheel_bytes"] == 127_527_173
    assert plan["runtime_wheel_evidence"]["dependency_installed"] is False
    assert plan["runtime_wheel_evidence"]["package_imported"] is False
    runtime_import = plan["runtime_import_evidence"]
    assert runtime_import["locked_package_count"] == 29
    assert runtime_import["dependency_installed"] is True
    assert runtime_import["python_network_attempts"] == 0
    assert runtime_import["local_bind_attempts"] == [
        "requests:socket.bind:('::1', 0)"
    ]
    assert runtime_import["checkpoint_loaded"] is False
    assert runtime_import["model_constructed"] is False
    assert runtime_import["remediation"]["cycles_used"] == 1
    source_evidence = plan["source_evidence"]
    assert source_evidence["archive_bytes"] == 144_791
    assert source_evidence["critical_file_hashes_match"] is True
    model_load = plan["model_load_evidence"]
    assert model_load["checkpoint_loads"] == 1
    assert model_load["state_keys_equal"] is True
    assert model_load["state_shapes_equal"] is True
    assert model_load["state_dtypes_equal"] is True
    assert model_load["forward_calls"] == 0
    assert model_load["architecture_remediation"][
        "checkpoint_derived_transformer_expansion"
    ] == 4
    assert model_load["architecture_remediation"][
        "checkpoint_derived_mask_head_expansion"
    ] == 2
    assert model_load["upstream_chunk_alignment"]["valid_for_inference"] is False
    assert plan["next_gate"]["kind"] == "one_four_song_synth_canary_plan"
    assert plan["synthetic_forward_evidence"]["authority_consumed"] is True
    assert plan["synthetic_forward_evidence"]["inference_attempts"] == 1
    assert plan["synthetic_forward_evidence"]["musical_usefulness_established"] is False
    assert plan["next_gate"]["requires_separate_approval"] is True
    assert plan["next_gate"]["runtime_wheel_download"] is False


def test_presence_is_separate_from_model_usefulness() -> None:
    evaluation = build_next_challenger_plan()["evaluation"]
    presence = evaluation["instrument_presence_review"]

    assert presence["required_before_model_usefulness_scoring"] is True
    assert presence["absent_or_cannot_tell_is_model_failure"] is False
    assert presence["absent_or_cannot_tell_triggers_replacement_case"] is False
    assert evaluation["usefulness_review"]["minimum_rating_for_preview_admission"] is None
    assert evaluation["usefulness_review"]["poor_feedback_triggers_unbounded_tuning"] is False
    assert len(evaluation["cases"]) == 4
    assert len({case["track_id"] for case in evaluation["cases"]}) == 4


def test_next_challenger_rejects_authority_expansion() -> None:
    changed = copy.deepcopy(build_next_challenger_plan())
    changed["next_gate"]["inference"] = True

    with pytest.raises(ValueError, match="differs from the reviewed contract"):
        validate_next_challenger_plan(changed)


def test_next_challenger_plan_script_is_read_only() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "plan-separation-other-refinement-next-challenger.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)

    assert document == build_next_challenger_plan()
    assert document["effects"]["network_used_by_plan"] is False
    assert document["effects"]["artifact_downloaded_by_plan"] is False
