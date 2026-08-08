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
    assert plan["next_gate"]["kind"] == (
        "hash_locked_macos_arm64_dependency_closure_evidence"
    )
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
