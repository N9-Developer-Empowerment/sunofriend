from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_runtime import (
    build_query_runtime_audit,
    validate_query_runtime_audit,
)


ROOT = Path(__file__).resolve().parents[1]


def test_query_runtime_audit_names_hidden_artifact_and_forbids_loaders() -> None:
    audit = build_query_runtime_audit()

    assert audit["status"] == "blocked_pending_hash_locked_runtime_plan"
    assert audit["registered"] is False
    assert audit["executable"] is False
    assert audit["source_audit"]["query_bandit"]["revision"] == (
        "79ed5bb75e5c3a40cd319d9d990cee913fc65c26"
    )
    assert audit["source_audit"]["query_bandit"][
        "checkpoint_lightning_version_observed_statically"
    ] == "2.1.3"
    passt = audit["required_artifacts"]["passt_openmic"]
    assert passt["published_bytes"] == 341_546_630
    assert passt["sha256"] == (
        "dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da"
    )
    assert passt["evidence_sha256"] == (
        "990348267a373e2fe62c2fc87a13914411d7fe763b160568c87127a315f58362"
    )
    assert passt["evidence_complete"] is True
    assert passt["evidence_only_download_approved"] is True
    assert passt["network_denied_static_inspection_complete"] is True
    assert passt["loaded"] is False
    contract = audit["restricted_loading_contract"]
    assert contract["use_upstream_train_cli"] is False
    assert contract["use_lightning_load_from_checkpoint"] is False
    assert contract["use_upstream_passt_download_helper"] is False
    assert contract["use_unrestricted_torch_load"] is False
    assert "weights_only=True" in contract["banquet_loader"]
    assert "weights_only=True" in contract["passt_loader"]
    assert audit["proposed_runtime_identity"]["model_artifact_hashes_complete"] is True
    assert (
        audit["proposed_runtime_identity"]["runtime_dependency_hashes_complete"]
        is False
    )
    assert audit["next_gate"]["kind"] == "review_hash_locked_runtime_plan"
    assert audit["next_gate"]["dependency_artifact_download_approved"] is False
    assert audit["next_gate"]["dependency_installation"] is False
    assert audit["next_gate"]["model_loading"] is False
    assert not any(
        value is True
        for key, value in audit["effects"].items()
        if key not in {"inference_runs", "audio_reads", "audio_writes"}
    )
    assert audit["effects"]["inference_runs"] == 0
    assert validate_query_runtime_audit(audit) == audit


def test_query_runtime_audit_rejects_authority_expansion() -> None:
    audit = build_query_runtime_audit()
    changed = copy.deepcopy(audit)
    changed["next_gate"]["model_loading"] = True

    with pytest.raises(ValueError, match="differs from the reviewed audit"):
        validate_query_runtime_audit(changed)


def test_query_runtime_plan_script_is_read_only() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "plan-separation-other-refinement-query-runtime.py"
            ),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)

    assert document == build_query_runtime_audit()
    assert document["effects"]["network_used_by_plan"] is False
    assert document["effects"]["artifact_downloaded_by_plan"] is False
