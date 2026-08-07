from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_challenger import (
    build_query_challenger_plan,
    validate_query_challenger_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def test_query_challenger_plan_is_bounded_and_non_executable() -> None:
    plan = build_query_challenger_plan()

    assert plan["status"] == "blocked_pending_runtime_qualification"
    assert plan["registered"] is False
    assert plan["executable"] is False
    assert plan["candidate"]["checkpoint_bytes"] == 645_470_187
    assert plan["candidate"]["checkpoint_sha256"] == (
        "657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2"
    )
    evidence = plan["candidate"]["checkpoint_evidence"]
    assert evidence["archive_member_count"] == 3_491
    assert evidence["application_model_globals_observed"] is False
    assert evidence["checkpoint_deserialized"] is False
    assert evidence["authorizes_loading"] is False
    assert plan["approvals"]["checkpoint_evidence_download"] is True
    assert plan["approvals"]["dependency_installation"] is False
    assert plan["candidate"]["checkpoint_license"] == "CC-BY-NC-SA-4.0"
    assert set(plan["target_contract"]["targets"]) == {
        "guitar",
        "keyboard_synth",
    }
    assert plan["target_contract"]["targets"]["keyboard_synth"]["training_classes"] == [
        "electric_piano",
        "organ_electric_organ",
        "synth_pad",
        "synth_lead",
    ]
    assert plan["bounded_evaluation"]["configuration_count"] == 1
    assert plan["bounded_evaluation"]["remediation_cycle_count"] == 1
    assert not any(plan["effects"].values())
    assert validate_query_challenger_plan(plan) == plan


def test_query_challenger_plan_rejects_mutation() -> None:
    plan = build_query_challenger_plan()
    changed = copy.deepcopy(plan)
    changed["approvals"]["model_inference"] = True

    with pytest.raises(ValueError, match="differs from the reviewed plan"):
        validate_query_challenger_plan(changed)


def test_query_challenger_plan_script_is_read_only() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "plan-separation-other-refinement-query-challenger.py"
            ),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)

    assert document == build_query_challenger_plan()
    assert document["effects"]["network_used_by_plan"] is False
