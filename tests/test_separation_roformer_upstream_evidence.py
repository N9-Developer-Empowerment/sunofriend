from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_roformer_upstream_evidence as evidence
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _copy_evidence(root: Path) -> Path:
    repository = Path(__file__).parents[1]
    target = root / evidence.UPSTREAM_EVIDENCE
    shutil.copyfile(repository / evidence.UPSTREAM_EVIDENCE, target)
    return target


def _all_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _all_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _all_strings(child)]
    return [value] if isinstance(value, str) else []


def test_exact_upstream_snapshot_is_verified_but_does_not_authorize(
    tmp_path: Path,
) -> None:
    _copy_evidence(tmp_path)
    with (
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        result = evidence._verify_private_roformer_upstream_evidence(tmp_path)

    assert result["status"] == "verified_no_checkpoint_authority"
    assert result["path_free"] is True
    assert result["verification_sha256"] == evidence._verification_sha256(result)
    assert result["snapshot"] == {
        "path": evidence.UPSTREAM_EVIDENCE,
        "bytes": evidence.UPSTREAM_EVIDENCE_BYTES,
        "sha256": evidence.UPSTREAM_EVIDENCE_SHA256,
        "observed_at": "2026-08-01",
    }
    assert result["release"]["revision"] == evidence.RELEASE_REVISION
    assert result["checkpoint"]["published_digest"] is None
    assert result["checkpoint"]["terms_stated_in_release_body"] is False
    assert result["checkpoint"]["allowed_use_verified"] is False
    assert result["readiness"]["private_evaluation_eligible"] is False
    assert result["blockers"] == [
        "checkpoint_allowed_use_unverified",
        "checkpoint_sha256_unpublished",
        "checkpoint_terms_unverified",
    ]
    assert all(
        not text.startswith("/") and str(tmp_path) not in text
        for text in _all_strings(result)
    )
    assert result["effects"] == {
        "filesystem_accessed": True,
        "filesystem_written": False,
        "network_used": False,
        "checkpoint_opened": False,
        "checkpoint_downloaded": False,
        "checkpoint_deserialized": False,
        "model_imported": False,
        "process_started": False,
        "product_route_changed": False,
    }


def test_upstream_snapshot_rejects_changed_or_symlinked_file(tmp_path: Path) -> None:
    snapshot = _copy_evidence(tmp_path)
    snapshot.write_bytes(snapshot.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="size differs"):
        evidence._verify_private_roformer_upstream_evidence(tmp_path)

    snapshot.unlink()
    target = tmp_path / "target.json"
    shutil.copyfile(
        Path(__file__).parents[1] / evidence.UPSTREAM_EVIDENCE,
        target,
    )
    snapshot.symlink_to(target)
    with pytest.raises(ValueError, match="unsafe"):
        evidence._verify_private_roformer_upstream_evidence(tmp_path)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.update({"unexpected": True}), "fields differ"),
        (
            lambda value: value["release"].update({"body": "MIT weights"}),
            "release evidence differs",
        ),
        (
            lambda value: value["release"]["assets"][1].update(
                {"digest": "sha256:" + "a" * 64}
            ),
            "release assets differ",
        ),
        (
            lambda value: value["findings"].update(
                {"checkpoint_allowed_use_verified": True}
            ),
            "findings differ",
        ),
    ],
)
def test_semantic_validator_rejects_authority_or_identity_drift(
    mutator: object,
    message: str,
) -> None:
    repository = Path(__file__).parents[1]
    value = json.loads(
        (repository / evidence.UPSTREAM_EVIDENCE).read_text(encoding="utf-8")
    )
    changed = copy.deepcopy(value)
    assert callable(mutator)
    mutator(changed)
    with pytest.raises(ValueError, match=message):
        evidence._validate_private_roformer_upstream_evidence(changed)


def test_private_evidence_script_has_no_public_route() -> None:
    repository = Path(__file__).parents[1]
    script = repository / "scripts/private-roformer-upstream-evidence.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repository-root",
            str(repository),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repository / "src")},
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "verified_no_checkpoint_authority"
    assert result["effects"]["network_used"] is False
    assert "private-roformer-upstream-evidence" not in PUBLIC_COMMANDS
    assert "private-roformer-upstream-evidence" not in DIRECT_TUI_COMMANDS
