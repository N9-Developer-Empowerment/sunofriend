from __future__ import annotations

import json
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

import pytest

import sunofriend._separation_macos_sandbox_probe as sandbox_probe
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_macos_sandbox_probe import (
    _run_private_macos_network_denial_canary,
    _validate_private_macos_network_denial_canary,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_model_free_canary_contract_is_cross_platform_testable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sandbox_probe.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(sandbox_probe.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        sandbox_probe,
        "_regular_file_identity",
        lambda value: {
            "resolved_path": "/synthetic/executable",
            "bytes": 100,
            "sha256": "1" * 64,
        },
    )
    observations = iter(
        (
            {
                "address": "ipv4-loopback-discard",
                "arithmetic": 42,
                "connect_ex": 61,
                "errno_name": "ECONNREFUSED",
                "probe_id": sandbox_probe.PROBE_ID,
            },
            {
                "address": "ipv4-loopback-discard",
                "arithmetic": 42,
                "connect_ex": 1,
                "errno_name": "EPERM",
                "probe_id": sandbox_probe.PROBE_ID,
            },
        )
    )
    monkeypatch.setattr(sandbox_probe, "_run_probe", lambda command: next(observations))

    evidence = sandbox_probe._run_private_macos_network_denial_canary()

    assert evidence["conclusion"]["os_network_denial_observed_for_canary"] is True
    assert evidence["limitations"][
        "measured_artifact_execution_toctou_closed"
    ] is False


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only canary")
def test_live_canary_proves_network_denial_without_authorizing_worker() -> None:
    evidence = _run_private_macos_network_denial_canary()

    assert evidence["status"] == "network_denial_verified_canary_observation_only"
    assert evidence["observation"]["control"]["connect_ex"] != 1
    assert evidence["observation"]["sandboxed"]["connect_ex"] == 1
    assert evidence["observation"]["sandboxed"]["errno_name"] == "EPERM"
    assert evidence["conclusion"]["os_network_denial_observed_for_canary"] is True
    assert evidence["conclusion"]["arbitrary_model_attempt_stream_observed"] is False
    assert evidence["conclusion"]["bound_to_model_worker"] is False
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in repr(evidence)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only canary")
def test_canary_self_hash_rejects_changed_conclusion() -> None:
    evidence = plain(_run_private_macos_network_denial_canary())
    evidence["conclusion"]["bound_to_model_worker"] = True

    with pytest.raises(ValueError, match="self-hash differs"):
        _validate_private_macos_network_denial_canary(evidence)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only canary")
def test_canary_rejects_resigned_policy_drift() -> None:
    evidence = plain(_run_private_macos_network_denial_canary())
    evidence["limitations"]["complete_attempt_observer_available"] = True
    unsigned = dict(evidence)
    unsigned.pop("evidence_sha256")
    evidence["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()

    with pytest.raises(ValueError, match="limitations differ"):
        _validate_private_macos_network_denial_canary(evidence)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only canary")
def test_private_canary_script_outputs_json_without_public_route() -> None:
    repository = Path(__file__).parents[1]
    script = repository / "scripts/private-macos-sandbox-probe.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(repository / "src")},
    )
    evidence = json.loads(completed.stdout)

    assert evidence["conclusion"]["os_network_denial_observed_for_canary"] is True
    assert evidence["conclusion"]["worker_authorized"] is False
    assert "private-macos-sandbox-probe" not in PUBLIC_COMMANDS
    assert "private-macos-sandbox-probe" not in DIRECT_TUI_COMMANDS
