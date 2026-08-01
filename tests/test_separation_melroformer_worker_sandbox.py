from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_worker_sandbox import (
    _run_private_melroformer_synthetic_worker_canary,
    _validate_private_melroformer_synthetic_worker_canary,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only sandbox")
def test_live_synthetic_worker_binds_denials_and_parent_pcm24_verification(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[1]
    evidence = _run_private_melroformer_synthetic_worker_canary(
        repository_root=repository,
        runtime_path=sys.executable,
        staging_directory=tmp_path / "staging",
    )

    assert evidence["status"] == "synthetic_worker_complete_parent_verified"
    assert evidence["canaries"] == {
        "network_connect_ex": 1,
        "network_errno_name": "EPERM",
        "process_fork_errno": 1,
        "process_fork_errno_name": "EPERM",
        "outside_write_errno": 1,
        "outside_write_errno_name": "EPERM",
    }
    assert evidence["quarantine"]["evidence_identical"] is True
    assert evidence["conclusion"]["model_worker_verified"] is False
    assert evidence["artifacts"]["complete_python_import_closure_bound"] is False
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in repr(evidence)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only sandbox")
def test_worker_sandbox_script_outputs_path_free_json(tmp_path: Path) -> None:
    repository = Path(__file__).parents[1]
    script = repository / "scripts/private-melroformer-worker-sandbox.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repository-root",
            str(repository),
            "--runtime",
            sys.executable,
            "--staging-directory",
            str(tmp_path / "staging"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(repository / "src")},
    )
    evidence = json.loads(completed.stdout)
    assert evidence["conclusion"]["pcm24_quarantine_bound_to_synthetic_worker"]
    assert "/Users/" not in completed.stdout


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only sandbox")
def test_resigned_model_claim_is_rejected(tmp_path: Path) -> None:
    repository = Path(__file__).parents[1]
    evidence = plain(
        _run_private_melroformer_synthetic_worker_canary(
            repository_root=repository,
            runtime_path=sys.executable,
            staging_directory=tmp_path / "staging",
        )
    )
    evidence["conclusion"]["model_worker_verified"] = True
    unsigned = dict(evidence)
    unsigned.pop("evidence_sha256")
    evidence["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()

    with pytest.raises(ValueError, match="conclusion differs"):
        _validate_private_melroformer_synthetic_worker_canary(evidence)


def test_private_worker_sandbox_has_no_public_route() -> None:
    assert "private-melroformer-worker-sandbox" not in PUBLIC_COMMANDS
    assert "private-melroformer-worker-sandbox" not in DIRECT_TUI_COMMANDS
