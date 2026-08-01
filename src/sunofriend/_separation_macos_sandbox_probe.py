"""Private, model-free proof of macOS ``sandbox-exec`` network denial.

The canary deliberately compares one loopback TCP connection from the same
small standard-library probe with and without a deny-network sandbox.  It
proves only that the observed sandboxed child received ``EPERM`` while the
control child did not.  It does not start a model, observe arbitrary model
connection attempts, confine filesystem writes or authorize a worker.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-macos-sandbox-network-canary.v1"
POLICY_ID = "private-macos-sandbox-exec-network-denial-canary-v1"
PROVIDER_ID = "apple-sandbox-exec-deprecated"
PROBE_ID = "stdlib-loopback-connect-ex-v1"
SANDBOX_EXEC_PATH = Path("/usr/bin/sandbox-exec")
SANDBOX_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
_ENVIRONMENT = {
    "HOME": "/var/empty",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONNOUSERSITE": "1",
}
_CHILD_SOURCE = """\
import errno
import json
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    result = sock.connect_ex(("127.0.0.1", 9))
finally:
    sock.close()
print(json.dumps({
    "address": "ipv4-loopback-discard",
    "arithmetic": 6 * 7,
    "connect_ex": result,
    "errno_name": errno.errorcode.get(result, "UNKNOWN"),
    "probe_id": "stdlib-loopback-connect-ex-v1",
}, sort_keys=True, separators=(",", ":")))
"""
_REQUIRED_FIELDS = {
    "schema",
    "policy_id",
    "status",
    "platform",
    "provider",
    "runtime",
    "profile",
    "canary",
    "observation",
    "conclusion",
    "limitations",
    "permissions",
    "effects",
    "evidence_sha256",
}
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _run_private_macos_network_denial_canary(
    *, runtime_path: str | Path | None = None
) -> Mapping[str, Any]:
    """Run one bounded, model-free loopback canary and return path-free evidence."""

    if platform.system() != "Darwin":
        raise RuntimeError("macOS sandbox network canary requires Darwin")
    provider = _regular_file_identity(SANDBOX_EXEC_PATH)
    runtime = _regular_file_identity(runtime_path or sys.executable)
    probe_command = [
        runtime["resolved_path"],
        "-I",
        "-S",
        "-c",
        _CHILD_SOURCE,
    ]
    control = _run_probe(probe_command)
    sandboxed = _run_probe(
        [
            provider["resolved_path"],
            "-p",
            SANDBOX_PROFILE,
            *probe_command,
        ]
    )
    if control["connect_ex"] == errno.EPERM:
        raise RuntimeError("unsandboxed loopback control was already permission denied")
    if sandboxed["connect_ex"] != errno.EPERM:
        raise RuntimeError("sandboxed loopback connection was not denied with EPERM")

    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "network_denial_verified_canary_observation_only",
        "platform": {
            "system": "Darwin",
            "machine": platform.machine(),
        },
        "provider": {
            "provider_id": PROVIDER_ID,
            "bytes": provider["bytes"],
            "sha256": provider["sha256"],
            "deprecated_by_platform_manual": True,
        },
        "runtime": {
            "bytes": runtime["bytes"],
            "sha256": runtime["sha256"],
            "isolated_mode": True,
            "site_import_disabled": True,
        },
        "profile": {
            "sha256": hashlib.sha256(SANDBOX_PROFILE.encode("utf-8")).hexdigest(),
            "default_policy": "allow",
            "network_policy": "deny_all",
            "filesystem_write_policy": "not_confined",
            "child_process_policy": "not_confined",
        },
        "canary": {
            "probe_id": PROBE_ID,
            "source_sha256": hashlib.sha256(_CHILD_SOURCE.encode("utf-8")).hexdigest(),
            "environment_sha256": hashlib.sha256(
                _canonical_json_bytes(_ENVIRONMENT)
            ).hexdigest(),
            "target_scope": "ipv4_loopback_only",
            "external_destination_contacted": False,
        },
        "observation": {
            "control": control,
            "sandboxed": sandboxed,
            "same_probe_source": True,
            "same_runtime_identity": True,
        },
        "conclusion": {
            "os_network_denial_observed_for_canary": True,
            "denial_errno": "EPERM",
            "code_owned_attempt_observed": True,
            "arbitrary_model_attempt_stream_observed": False,
            "bound_to_model_worker": False,
            "worker_authorized": False,
        },
        "limitations": {
            "provider_is_deprecated": True,
            "one_ipv4_loopback_operation_tested": True,
            "ipv6_tested": False,
            "dns_tested": False,
            "unix_domain_socket_tested": False,
            "filesystem_confinement_tested": False,
            "child_process_denial_tested": False,
            "model_or_checkpoint_loaded": False,
            "complete_attempt_observer_available": False,
            "measured_artifact_execution_toctou_closed": False,
        },
        "permissions": {
            "worker_start_permitted": False,
            "model_import_permitted": False,
            "checkpoint_access_permitted": False,
            "audio_persistence_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "process_started": True,
            "filesystem_written": False,
            "external_network_used": False,
            "loopback_connection_attempted": True,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_inference_called": False,
            "source_graph_changed": False,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_macos_network_denial_canary(document)


def _validate_private_macos_network_denial_canary(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate the fixed path-free canary shape and its self-hash."""

    if not isinstance(document, Mapping):
        raise ValueError("macOS sandbox canary evidence must be an object")
    value = _plain(document)
    if set(value) != _REQUIRED_FIELDS:
        raise ValueError("macOS sandbox canary evidence fields differ")
    digest = value.pop("evidence_sha256")
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise ValueError("macOS sandbox canary evidence hash is invalid")
    if digest != hashlib.sha256(_canonical_json_bytes(value)).hexdigest():
        raise ValueError("macOS sandbox canary evidence self-hash differs")
    if (
        value["schema"] != SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["status"] != "network_denial_verified_canary_observation_only"
    ):
        raise ValueError("macOS sandbox canary identity differs")
    _exact_fields(value["platform"], {"system", "machine"}, "platform")
    if (
        value["platform"]["system"] != "Darwin"
        or not isinstance(value["platform"]["machine"], str)
        or not value["platform"]["machine"]
    ):
        raise ValueError("macOS sandbox canary platform differs")
    _exact_fields(
        value["provider"],
        {"provider_id", "bytes", "sha256", "deprecated_by_platform_manual"},
        "provider",
    )
    _exact_fields(
        value["runtime"],
        {"bytes", "sha256", "isolated_mode", "site_import_disabled"},
        "runtime",
    )
    _require_sha(value["provider"], "sha256", "provider")
    _require_sha(value["runtime"], "sha256", "runtime")
    if (
        value["provider"]["provider_id"] != PROVIDER_ID
        or value["provider"]["deprecated_by_platform_manual"] is not True
        or type(value["provider"]["bytes"]) is not int
        or value["provider"]["bytes"] <= 0
        or value["runtime"]["isolated_mode"] is not True
        or value["runtime"]["site_import_disabled"] is not True
        or type(value["runtime"]["bytes"]) is not int
        or value["runtime"]["bytes"] <= 0
    ):
        raise ValueError("macOS sandbox canary executable evidence differs")
    expected_profile = {
        "sha256": hashlib.sha256(SANDBOX_PROFILE.encode("utf-8")).hexdigest(),
        "default_policy": "allow",
        "network_policy": "deny_all",
        "filesystem_write_policy": "not_confined",
        "child_process_policy": "not_confined",
    }
    if value["profile"] != expected_profile:
        raise ValueError("macOS sandbox canary profile differs")
    expected_canary = {
        "probe_id": PROBE_ID,
        "source_sha256": hashlib.sha256(_CHILD_SOURCE.encode("utf-8")).hexdigest(),
        "environment_sha256": hashlib.sha256(
            _canonical_json_bytes(_ENVIRONMENT)
        ).hexdigest(),
        "target_scope": "ipv4_loopback_only",
        "external_destination_contacted": False,
    }
    if value["canary"] != expected_canary:
        raise ValueError("macOS sandbox canary probe binding differs")
    _exact_fields(
        value["observation"],
        {"control", "sandboxed", "same_probe_source", "same_runtime_identity"},
        "observation",
    )
    control = value["observation"]["control"]
    sandboxed = value["observation"]["sandboxed"]
    for item, label in ((control, "control"), (sandboxed, "sandboxed")):
        _exact_fields(
            item,
            {"address", "arithmetic", "connect_ex", "errno_name", "probe_id"},
            label,
        )
    if (
        control["probe_id"] != PROBE_ID
        or sandboxed["probe_id"] != PROBE_ID
        or control["address"] != "ipv4-loopback-discard"
        or sandboxed["address"] != "ipv4-loopback-discard"
        or control["arithmetic"] != 42
        or sandboxed["arithmetic"] != 42
        or type(control["connect_ex"]) is not int
        or type(sandboxed["connect_ex"]) is not int
        or control["errno_name"]
        != errno.errorcode.get(control["connect_ex"], "UNKNOWN")
        or control["connect_ex"] == errno.EPERM
        or sandboxed["connect_ex"] != errno.EPERM
        or sandboxed["errno_name"] != "EPERM"
        or value["observation"]["same_probe_source"] is not True
        or value["observation"]["same_runtime_identity"] is not True
    ):
        raise ValueError("macOS sandbox canary observation differs")
    expected_conclusion = {
        "os_network_denial_observed_for_canary": True,
        "denial_errno": "EPERM",
        "code_owned_attempt_observed": True,
        "arbitrary_model_attempt_stream_observed": False,
        "bound_to_model_worker": False,
        "worker_authorized": False,
    }
    expected_limitations = {
        "provider_is_deprecated": True,
        "one_ipv4_loopback_operation_tested": True,
        "ipv6_tested": False,
        "dns_tested": False,
        "unix_domain_socket_tested": False,
        "filesystem_confinement_tested": False,
        "child_process_denial_tested": False,
        "model_or_checkpoint_loaded": False,
        "complete_attempt_observer_available": False,
        "measured_artifact_execution_toctou_closed": False,
    }
    expected_permissions = {
        "worker_start_permitted": False,
        "model_import_permitted": False,
        "checkpoint_access_permitted": False,
        "audio_persistence_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }
    expected_effects = {
        "process_started": True,
        "filesystem_written": False,
        "external_network_used": False,
        "loopback_connection_attempted": True,
        "checkpoint_opened": False,
        "model_imported": False,
        "audio_inference_called": False,
        "source_graph_changed": False,
    }
    if value["conclusion"] != expected_conclusion:
        raise ValueError("macOS sandbox canary conclusion differs")
    if value["limitations"] != expected_limitations:
        raise ValueError("macOS sandbox canary limitations differ")
    if value["permissions"] != expected_permissions:
        raise ValueError("macOS sandbox canary grants a permission")
    if value["effects"] != expected_effects:
        raise ValueError("macOS sandbox canary effects differ")
    frozen = {**value, "evidence_sha256": digest}
    _reject_paths_and_urls(frozen)
    return _freeze_json(frozen)


def _run_probe(command: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        env=dict(_ENVIRONMENT),
        timeout=10.0,
    )
    if completed.returncode != 0 or completed.stderr or len(completed.stdout) > 2_048:
        raise RuntimeError("macOS sandbox canary child did not complete cleanly")
    try:
        result = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as error:
        raise RuntimeError("macOS sandbox canary child returned invalid JSON") from error
    if not isinstance(result, dict) or set(result) != {
        "address",
        "arithmetic",
        "connect_ex",
        "errno_name",
        "probe_id",
    }:
        raise RuntimeError("macOS sandbox canary child result fields differ")
    if (
        result["probe_id"] != PROBE_ID
        or result["address"] != "ipv4-loopback-discard"
        or type(result["arithmetic"]) is not int
        or result["arithmetic"] != 42
        or type(result["connect_ex"]) is not int
        or not isinstance(result["errno_name"], str)
    ):
        raise RuntimeError("macOS sandbox canary child result differs")
    return result


def _regular_file_identity(value: str | Path) -> dict[str, Any]:
    path = Path(value).expanduser().resolve(strict=True)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not os.access(path, os.X_OK):
        raise ValueError("macOS sandbox canary executable must be a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    after = path.stat()
    if _stat_identity(before) != _stat_identity(after):
        raise ValueError("macOS sandbox canary executable changed while hashing")
    return {
        "resolved_path": str(path),
        "bytes": before.st_size,
        "sha256": digest.hexdigest(),
    }


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _require_sha(value: Any, key: str, label: str) -> None:
    if (
        not isinstance(value, Mapping)
        or not isinstance(value.get(key), str)
        or not _SHA_RE.fullmatch(value[key])
    ):
        raise ValueError(f"macOS sandbox canary {label} hash is invalid")


def _exact_fields(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"macOS sandbox canary {label} fields differ")


def _reject_paths_and_urls(value: Any) -> None:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("macOS sandbox canary evidence is not path-free")


__all__ = [
    "POLICY_ID",
    "PROBE_ID",
    "PROVIDER_ID",
    "SANDBOX_EXEC_PATH",
    "SANDBOX_PROFILE",
    "SCHEMA",
    "_run_private_macos_network_denial_canary",
    "_validate_private_macos_network_denial_canary",
]
