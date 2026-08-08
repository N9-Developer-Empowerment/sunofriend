from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_reference_plan import (
    build_query_reference_plan,
    validate_query_reference_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def test_reference_plan_is_song_disjoint_bounded_and_no_effects() -> None:
    plan = build_query_reference_plan()
    queries = plan["query_bank"]["queries"]
    mixtures = plan["test_mixtures"]

    assert plan["status"] == (
        "blocked_pending_explicit_rights_bound_reference_inference_approval"
    )
    assert plan["registered"] is False
    assert plan["executable"] is False
    assert plan["query_bank"]["song_disjoint_from_every_test_mixture"] is True
    assert len(queries) == 3
    assert {item["target_id"] for item in queries} == {
        "guitar",
        "keyboard",
        "synth",
    }
    assert len(mixtures) == 3
    assert all(item["track_id"] != plan["query_bank"]["track_id"] for item in mixtures)
    assert plan["execution_contract"]["inference_attempt_limit"] == 9
    assert plan["execution_contract"]["remediation_cycle_limit"] == 1
    assert plan["execution_contract"]["maximum_persisted_reconstruction_error_lsb"] == 2
    assert (
        plan["private_outputs"]["reconstruction_accounting_is_not_separation_accuracy"]
        is True
    )
    assert plan["feedback_policy"]["minimum_usefulness_rating"] is None
    assert plan["feedback_policy"]["poor_feedback_triggers_query_hunt"] is False
    assert plan["next_approval"]["authorizes_public_activation"] is False
    assert plan["effects"]["inference_runs"] == 0
    assert validate_query_reference_plan(plan) == plan


def test_reference_plan_binds_the_two_tracked_corpus_manifests() -> None:
    plan = build_query_reference_plan()
    binding = plan["evidence_binding"]
    for path_field, hash_field in (
        ("authorised_corpus_manifest", "authorised_corpus_manifest_sha256"),
        ("frozen_window_manifest", "frozen_window_manifest_sha256"),
    ):
        path = ROOT / binding[path_field]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding[hash_field]


def test_reference_plan_rejects_authority_expansion() -> None:
    plan = copy.deepcopy(build_query_reference_plan())
    plan["next_approval"]["authorizes_midi"] = True
    with pytest.raises(ValueError, match="differs from the reviewed plan"):
        validate_query_reference_plan(plan)


def test_reference_plan_script_only_prints_the_plan() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                ROOT / "scripts" / "plan-separation-other-refinement-query-reference.py"
            ),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == build_query_reference_plan()
