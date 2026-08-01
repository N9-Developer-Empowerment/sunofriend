from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_melroformer_challenger_plan as melroformer
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_plan_is_exact_read_only_and_fail_closed() -> None:
    with (
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        plan = melroformer._build_private_melroformer_challenger_plan()

    assert plan["status"] == "blocked"
    assert plan["read_only"] is True
    assert plan["candidate"]["roles"] == ["vocals"]
    assert plan["candidate"]["broad_separator"] is False
    assert plan["candidate"]["derived_role_equation"] == (
        "instrumental = mixture - vocals"
    )
    assert plan["source"]["conversion_revision"] == (
        "64cbfcb004e39430e5f584552c05949440ec39ce"
    )
    assert plan["checkpoint"]["format"] == "safetensors"
    assert plan["checkpoint"]["published_sha256"] == (
        "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
    )
    assert plan["checkpoint"]["checkpoint_specific_terms_verified"] is True
    assert plan["checkpoint"]["download_permitted"] is False
    assert plan["checkpoint"]["static_inspection_contract_defined"] is True
    assert plan["licensing"]["explicit_user_approval_recorded"] is False
    assert plan["alternatives_reviewed"][0]["admitted"] is False
    assert plan["alternatives_reviewed"][1]["admitted"] is False
    assert plan["upstream_evidence"] == {
        "path": melroformer.UPSTREAM_EVIDENCE,
        "bytes": melroformer.UPSTREAM_EVIDENCE_BYTES,
        "sha256": melroformer.UPSTREAM_EVIDENCE_SHA256,
        "observed_at": "2026-08-01",
        "official_primary_sources_only": True,
        "checkpoint_terms_verified": True,
        "checkpoint_published_sha256_verified": True,
        "local_checkpoint_identity_verified": False,
        "verified_in_this_call": False,
        "verification_command": (
            "scripts/private-melroformer-upstream-evidence.py "
            "--repository-root /absolute/path/to/Sunofriend"
        ),
    }
    assert plan["runtime"]["installation_command"] is None
    assert plan["runtime"]["installation_permitted"] is False
    assert plan["runtime"]["exact_source_manifest_defined"] is True
    assert plan["runtime"]["dependency_lock_defined"] is True
    assert plan["runtime"]["dependency_license_audit_defined"] is True
    assert plan["runtime"]["worker_protocol_defined"] is True
    assert plan["runtime"]["synthetic_adapter_contract_defined"] is True
    assert plan["runtime"]["real_adapter_implemented"] is False
    assert plan["source"]["upstream_from_pretrained_permitted"] is False
    assert plan["runtime"]["reported_parity_is_model_ground_truth_score"] is False
    assert plan["decision"]["checkpoint_published_identity_pinned"] is True
    assert plan["decision"]["checkpoint_local_identity_verified"] is False
    assert plan["decision"]["worker_start_permitted"] is False
    assert plan["decision"]["blockers"] == sorted(
        plan["decision"]["blockers"]
    )
    assert {
        "checkpoint_local_hash_unverified",
        "explicit_private_evaluation_approval_missing",
        "runtime_source_materialisation_missing",
        "runtime_worker_not_implemented",
    }.issubset(plan["decision"]["blockers"])
    assert all(value is False for value in plan["effects"].values())


def test_optional_local_observation_hashes_without_authorizing(tmp_path: Path) -> None:
    checkpoint = tmp_path / melroformer.CHECKPOINT_NAME
    checkpoint.write_bytes(b"not the published checkpoint")
    plan = melroformer._build_private_melroformer_challenger_plan(
        checkpoint_path=checkpoint
    )

    observed = plan["checkpoint"]["local_observation"]
    assert observed["provided"] is True
    assert observed["bytes"] == len(b"not the published checkpoint")
    assert observed["published_size_match"] is False
    assert observed["published_sha256_match"] is False
    assert observed["cryptographic_identity_verified"] is False
    assert plan["checkpoint"]["acquisition_status"] == "local_identity_mismatch"
    assert plan["decision"]["private_evaluation_eligible"] is False
    assert plan["effects"]["local_checkpoint_opened"] is True
    assert plan["effects"]["model_imported"] is False


def test_optional_local_observation_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.safetensors"
    link = tmp_path / "link.safetensors"
    target.write_bytes(b"checkpoint")
    link.symlink_to(target)
    with pytest.raises(ValueError, match="non-symlink regular file"):
        melroformer._build_private_melroformer_challenger_plan(
            checkpoint_path=link
        )


def test_private_plan_script_outputs_json_without_public_route() -> None:
    repository = Path(__file__).parents[1]
    script = repository / "scripts/private-melroformer-challenger.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--plan"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repository / "src")},
    )
    plan = json.loads(completed.stdout)
    assert plan["decision"]["run_status"] == "not_run"
    assert plan["effects"]["network_used"] is False
    assert "private-melroformer-challenger" not in PUBLIC_COMMANDS
    assert "private-melroformer-challenger" not in DIRECT_TUI_COMMANDS
