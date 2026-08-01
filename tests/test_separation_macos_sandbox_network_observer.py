from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

import pytest

import sunofriend._separation_macos_sandbox_network_observer as observer
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend.separation_contract import _canonical_json_bytes


def _event(message: str) -> dict[str, object]:
    return {
        "eventType": "logEvent",
        "senderImagePath": observer.SENDER_IMAGE_PATH,
        "eventMessage": message,
    }


def _stream(events: list[dict[str, object]]) -> bytes:
    lines = [json.dumps(event, sort_keys=True) for event in events]
    lines.append(json.dumps({"count": len(events), "finished": 1}))
    return ("\n".join(lines) + "\n").encode()


def _identity() -> dict[str, object]:
    return {
        "resolved_path": "/usr/bin/log",
        "bytes": 1_024,
        "sha256": "a" * 64,
    }


def test_observation_retains_counts_not_pid_destination_or_raw_message() -> None:
    target_pid = 41_234
    raw = _stream(
        [
            _event(
                f"Sandbox: Python({target_pid}) deny(1) "
                "network-outbound remote:*:9"
            ),
            _event(
                f"Sandbox: Python({target_pid}) deny(1) "
                "network-bind local:*:0"
            ),
            _event("Sandbox: unrelated(9988) deny(1) network-outbound remote:*:80"),
        ]
    )

    evidence = observer._build_observation(
        raw_stdout=raw,
        stdout_bytes=len(raw),
        target_pid=target_pid,
        expected_canary_port=9,
        identity=_identity(),
    )

    counts = evidence["observation"]
    assert counts["summary_event_count"] == 3
    assert counts["target_network_denial_count"] == 2
    assert counts["deliberate_canary_denial_count"] == 1
    assert counts["other_target_network_denial_count"] == 1
    assert counts["unrelated_network_denial_count"] == 1
    encoded = repr(evidence)
    assert str(target_pid) not in encoded
    assert "remote:" not in encoded
    assert "local:" not in encoded
    assert "Sandbox: " not in encoded
    assert "/Users/" not in encoded


@pytest.mark.parametrize(
    "raw, message",
    [
        (b"not-json\n", "malformed JSON"),
        (_stream([_event("not a sandbox denial")]), "denial message differs"),
        (
            (
                json.dumps(_event("Sandbox: Python(123) deny(1) network-outbound remote:*:9"))
                + "\n"
                + json.dumps({"count": 2, "finished": 1})
                + "\n"
            ).encode(),
            "final count differs",
        ),
    ],
)
def test_observation_fails_closed_on_malformed_or_incomplete_stream(
    raw: bytes, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        observer._build_observation(
            raw_stdout=raw,
            stdout_bytes=len(raw),
            target_pid=123,
            expected_canary_port=9,
            identity=_identity(),
        )


def test_observation_validator_rejects_permission_drift() -> None:
    raw = _stream(
        [_event("Sandbox: Python(123) deny(1) network-outbound remote:*:9")]
    )
    evidence = observer._build_observation(
        raw_stdout=raw,
        stdout_bytes=len(raw),
        target_pid=123,
        expected_canary_port=9,
        identity=_identity(),
    )
    changed = plain(evidence)
    changed["privacy"]["raw_log_persisted"] = True
    unsigned = dict(changed)
    unsigned.pop("evidence_sha256")
    changed["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()

    with pytest.raises(ValueError, match="boundary differs"):
        observer._validate_macos_sandbox_network_observation(changed)


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only observer")
def test_live_observer_binds_kernel_denial_to_exact_child_pid(tmp_path: Path) -> None:
    child_source = """\
import errno
import json
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    result = sock.connect_ex(("127.0.0.1", 9))
finally:
    sock.close()
print(json.dumps({"connect_ex": result, "errno_name": errno.errorcode.get(result)}))
"""
    completed, evidence = observer._run_with_macos_sandbox_network_observer(
        command=[
            "/usr/bin/sandbox-exec",
            "-p",
            "(version 1)\n(allow default)\n(deny network*)\n",
            "/usr/bin/python3",
            "-I",
            "-S",
            "-c",
            child_source,
        ],
        cwd=tmp_path,
        environment={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        timeout_seconds=10.0,
        expected_canary_port=9,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["errno_name"] == "EPERM"
    assert evidence["observation"]["deliberate_canary_denial_count"] >= 1
    assert evidence["observation"]["other_target_network_denial_count"] == 0
    assert evidence["privacy"]["raw_log_persisted"] is False
