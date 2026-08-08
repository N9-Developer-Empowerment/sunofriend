from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_synthetic_plan import (
    build_query_synthetic_plan,
    validate_query_synthetic_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_plan_is_bounded_and_has_no_effects() -> None:
    plan = build_query_synthetic_plan()

    assert plan["status"] == "blocked_pending_explicit_synthetic_inference_approval"
    assert plan["registered"] is False
    assert plan["executable"] is False
    assert plan["proposed_single_run"]["configuration_count"] == 1
    assert plan["proposed_single_run"]["mixture"]["shape"] == [1, 2, 88_200]
    assert plan["proposed_single_run"]["query"]["shape"] == [1, 2, 441_000]
    assert plan["proposed_single_run"]["audio_files_read"] == 0
    assert plan["proposed_single_run"]["audio_files_written"] == 0
    assert plan["evidence_binding"]["forward_contract_schema"] == (
        "sunofriend.other-refinement-query-forward-contract.v1"
    )
    assert len(plan["evidence_binding"]["forward_contract_document_sha256"]) == 64
    assert plan["evidence_binding"]["report_contract_schema"] == (
        "sunofriend.other-refinement-query-synthetic-report-contract.v1"
    )
    assert len(plan["evidence_binding"]["report_contract_document_sha256"]) == 64
    assert (
        plan["implementation_boundary"]["load_adapter_has_forward_method"] is False
    )
    assert plan["objective_acceptance"]["musical_usefulness_gate"] is False
    assert plan["next_approval"]["authorizes_inference_runs"] == 1
    assert plan["next_approval"]["authorizes_private_audio"] is False
    assert plan["effects"]["inference_runs"] == 0
    assert plan["effects"]["checkpoint_opened_by_plan"] is False
    assert validate_query_synthetic_plan(plan) == plan


def test_synthetic_plan_rejects_authority_expansion() -> None:
    plan = copy.deepcopy(build_query_synthetic_plan())
    plan["next_approval"]["authorizes_song_processing"] = True

    with pytest.raises(ValueError, match="differs from the reviewed plan"):
        validate_query_synthetic_plan(plan)


def test_synthetic_plan_script_only_prints_the_plan() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "plan-separation-other-refinement-query-synthetic.py"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == build_query_synthetic_plan()


def test_public_capability_binds_the_exact_synthetic_plan() -> None:
    capability = json.loads(
        (ROOT / "website" / "public" / "agent-capabilities.json").read_text(
            encoding="utf-8"
        )
    )
    published = capability["experiments"]["finished_mix_separation"][
        "other_refinement"
    ]["next_query_challenger"]
    plan = build_query_synthetic_plan()

    assert published["status"] == plan["status"]
    assert published["synthetic_plan_document_sha256"] == plan["document_sha256"]
    assert published["synthetic_plan_run_limit"] == plan["next_approval"][
        "authorizes_inference_runs"
    ]
    assert published["synthetic_plan_uses_private_audio"] is False
    assert published["synthetic_report_contract_document_sha256"] == plan[
        "evidence_binding"
    ]["report_contract_document_sha256"]
    assert published["synthetic_report_accepts_objective_failure"] is True
    assert published["synthetic_report_allows_subjective_feedback"] is False
    assert published["synthetic_report_grants_retry_or_activation"] is False
