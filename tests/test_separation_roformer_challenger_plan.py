from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_roformer_challenger_plan as roformer
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_plan_is_exact_read_only_and_fail_closed() -> None:
    with (
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        plan = roformer._build_private_roformer_challenger_plan()

    assert plan["status"] == "blocked"
    assert plan["read_only"] is True
    assert plan["source"]["release_tag"] == "v1.0.12"
    assert plan["source"]["release_revision"] == (
        "aef04b2e52fb3beaf25e333199f5a7236e628e7b"
    )
    assert plan["config"]["sha256"] == roformer.CONFIG_SHA256
    assert plan["checkpoint"]["published_bytes"] == 527_385_512
    assert plan["checkpoint"]["published_sha256"] is None
    assert plan["checkpoint"]["download_permitted"] is False
    assert plan["runtime"]["installation_command"] is None
    assert plan["runtime"]["dependency_lock"]["resolved_packages"] == 38
    assert plan["runtime"]["dependency_lock"]["installed"] is False
    assert plan["decision"]["candidate_registered"] is True
    assert plan["decision"]["worker_start_permitted"] is False
    assert {
        "checkpoint_terms_unverified",
        "checkpoint_allowed_use_unverified",
        "checkpoint_sha256_unpublished",
        "runtime_dependency_licenses_unverified",
        "runtime_worker_not_implemented",
    }.issubset(plan["decision"]["blockers"])
    assert "runtime_dependency_lock_missing" not in plan["decision"]["blockers"]
    assert all(value is False for value in plan["effects"].values())


def test_optional_local_observation_hashes_without_claiming_identity() -> None:
    with tempfile.TemporaryDirectory() as directory:
        checkpoint = Path(directory) / roformer.CHECKPOINT_NAME
        checkpoint.write_bytes(b"not the release checkpoint")
        plan = roformer._build_private_roformer_challenger_plan(
            checkpoint_path=checkpoint
        )

    observed = plan["checkpoint"]["local_observation"]
    assert observed["provided"] is True
    assert observed["bytes"] == len(b"not the release checkpoint")
    assert observed["release_size_match"] is False
    assert observed["cryptographic_identity_verified"] is False
    assert plan["checkpoint"]["release_asset_acquisition_status"] == (
        "local_unverified_file_present"
    )
    assert plan["decision"]["checkpoint_identity_pinned"] is False
    assert plan["decision"]["status"] == "blocked"
    assert plan["effects"]["local_checkpoint_opened"] is True


def test_optional_local_observation_rejects_symlink() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "target.ckpt"
        link = root / "link.ckpt"
        target.write_bytes(b"checkpoint")
        link.symlink_to(target)
        with pytest.raises(ValueError, match="non-symlink regular file"):
            roformer._build_private_roformer_challenger_plan(checkpoint_path=link)


def test_private_plan_script_outputs_json_without_public_route() -> None:
    script = Path(__file__).parents[1] / "scripts/private-roformer-challenger.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--plan"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    plan = json.loads(completed.stdout)
    assert plan["decision"]["run_status"] == "not_run"
    assert plan["effects"]["network_used"] is False
    assert "private-roformer-challenger" not in PUBLIC_COMMANDS
    assert "private-roformer-challenger" not in DIRECT_TUI_COMMANDS


def test_dependency_input_and_lock_are_exact_and_exclude_broad_runtime() -> None:
    root = Path(__file__).parents[1]
    dependency_input = root / roformer.RUNTIME_DEPENDENCY_INPUT
    dependency_lock = root / roformer.RUNTIME_DEPENDENCY_LOCK

    assert hashlib.sha256(dependency_input.read_bytes()).hexdigest() == (
        roformer.RUNTIME_DEPENDENCY_INPUT_SHA256
    )
    assert hashlib.sha256(dependency_lock.read_bytes()).hexdigest() == (
        roformer.RUNTIME_DEPENDENCY_LOCK_SHA256
    )
    input_text = dependency_input.read_text(encoding="utf-8")
    lock_text = dependency_lock.read_text(encoding="utf-8")
    assert (
        sum(1 for line in input_text.splitlines() if line and not line.startswith("#"))
        == 8
    )
    assert (
        sum(
            1
            for line in lock_text.splitlines()
            if "==" in line and not line.startswith((" ", "#"))
        )
        == 38
    )
    for excluded in (
        "accelerate",
        "bitsandbytes",
        "ml-collections",
        "omegaconf",
        "torchaudio",
        "wandb",
        "wxpython",
    ):
        assert f"{excluded}==" not in lock_text
