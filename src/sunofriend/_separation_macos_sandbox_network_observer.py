"""Private bounded observation of macOS Sandbox network denials.

The observer starts before the target child, reads the macOS unified-log stream
for kernel Sandbox ``network-*`` denial records, and binds matching records to
the exact child PID.  Raw log records, destinations and the PID are discarded;
only bounded path-free counts are retained.  This is development evidence, not
a public separation route or a claim that unified logging is a packet monitor.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ._separation_macos_process_image import (
    _PreparedRuntimeProcessImageBinding,
    _observe_prepared_runtime_process_image,
)
from ._separation_macos_sandbox_probe import _regular_file_identity
from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-macos-sandbox-network-observation.v1"
POLICY_ID = "private-macos-kernel-sandbox-network-denial-observer-v1"
LOG_PATH = Path("/usr/bin/log")
SENDER_IMAGE_PATH = "/System/Library/Extensions/Sandbox.kext/Contents/MacOS/Sandbox"
PREDICATE = (
    'process == "kernel" AND senderImagePath == '
    f'"{SENDER_IMAGE_PATH}" AND eventMessage CONTAINS " network-"'
)
_READY_PREFIX = b"Filtering the log data using "
_MAX_READY_BYTES = 16 * 1024
_MAX_STDOUT_BYTES = 1024 * 1024
_MAX_STDERR_BYTES = 256 * 1024
_MAX_EVENT_RECORDS = 1024
_READY_TIMEOUT_SECONDS = 5.0
_DRAIN_SECONDS = 0.75
_STOP_TIMEOUT_SECONDS = 5.0
_MESSAGE_RE = re.compile(
    r"^Sandbox: [A-Za-z0-9_.-]{1,64}\((\d+)\) "
    r"deny\((\d+)\) (network-[a-z-]+)(?: (.*))?$"
)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class _BoundedBytes:
    limit: int
    data: bytearray = field(default_factory=bytearray)
    total: int = 0
    overflow: bool = False

    def add(self, chunk: bytes) -> None:
        self.total += len(chunk)
        remaining = max(0, self.limit - len(self.data))
        if remaining:
            self.data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.overflow = True


@dataclass
class _ObserverState:
    process: subprocess.Popen[bytes]
    identity_before: Mapping[str, Any]
    stdout: _BoundedBytes
    stderr: _BoundedBytes
    threads: tuple[threading.Thread, threading.Thread]


def _run_with_macos_sandbox_network_observer(
    *,
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
    expected_canary_port: int = 9,
    stdin: Any = subprocess.DEVNULL,
) -> tuple[subprocess.CompletedProcess[str], Mapping[str, Any]]:
    """Run one child while observing kernel Sandbox network denials."""

    completed, observation, process_image = _run_observed_child(
        command=command,
        cwd=cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
        expected_canary_port=expected_canary_port,
        stdin=stdin,
        process_image_binding=None,
        pass_fds=(),
        after_process_image_observed=None,
    )
    if process_image is not None:
        raise RuntimeError("unexpected macOS runtime process-image observation")
    return completed, observation


def _run_with_macos_sandbox_network_and_process_image_observer(
    *,
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
    process_image_binding: _PreparedRuntimeProcessImageBinding,
    expected_canary_port: int = 9,
    stdin: Any = subprocess.DEVNULL,
) -> tuple[subprocess.CompletedProcess[str], Mapping[str, Any], Mapping[str, Any]]:
    """Run one child and bind both denial stream and final process image."""

    completed, observation, process_image = _run_observed_child(
        command=command,
        cwd=cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
        expected_canary_port=expected_canary_port,
        stdin=stdin,
        process_image_binding=process_image_binding,
        pass_fds=(),
        after_process_image_observed=None,
    )
    if process_image is None:
        raise RuntimeError("macOS runtime process-image observation is absent")
    return completed, observation, process_image


def _run_with_macos_sandbox_network_process_image_and_ready_observer(
    *,
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
    process_image_binding: _PreparedRuntimeProcessImageBinding,
    ready_observer: Callable[[int], Any],
    pass_fds: Sequence[int],
    expected_canary_port: int = 9,
    stdin: Any = subprocess.DEVNULL,
) -> tuple[
    subprocess.CompletedProcess[str],
    Mapping[str, Any],
    Mapping[str, Any],
    Any,
]:
    """Run one child with an explicit parent observation at worker readiness."""

    captured: dict[str, Any] = {}

    def observe(pid: int) -> None:
        captured["worker_ready"] = ready_observer(pid)

    completed, observation, process_image = _run_observed_child(
        command=command,
        cwd=cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
        expected_canary_port=expected_canary_port,
        stdin=stdin,
        process_image_binding=process_image_binding,
        pass_fds=pass_fds,
        after_process_image_observed=observe,
    )
    if process_image is None or "worker_ready" not in captured:
        raise RuntimeError("macOS worker-ready observation is absent")
    return completed, observation, process_image, captured["worker_ready"]


def _run_observed_child(
    *,
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
    expected_canary_port: int,
    stdin: Any,
    process_image_binding: _PreparedRuntimeProcessImageBinding | None,
    pass_fds: Sequence[int],
    after_process_image_observed: Callable[[int], None] | None,
) -> tuple[
    subprocess.CompletedProcess[str],
    Mapping[str, Any],
    Mapping[str, Any] | None,
]:
    state = _start_observer()
    target: subprocess.Popen[str] | None = None
    timed_out = False
    process_image: Mapping[str, Any] | None = None
    try:
        target = subprocess.Popen(
            list(command),
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=dict(environment),
            close_fds=True,
            pass_fds=tuple(pass_fds),
        )
        if process_image_binding is not None:
            process_image = _observe_prepared_runtime_process_image(
                target.pid,
                prepared=process_image_binding,
            )
        if after_process_image_observed is not None:
            after_process_image_observed(target.pid)
        try:
            stdout, stderr = target.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            target.kill()
            stdout, stderr = target.communicate()
        observation = _finish_observer(
            state,
            target_pid=target.pid,
            expected_canary_port=expected_canary_port,
        )
    except BaseException:
        if target is not None and target.poll() is None:
            target.kill()
            target.communicate()
        _abort_observer(state)
        raise
    if timed_out:
        raise RuntimeError("observed sandbox worker exceeded its timeout")
    completed = subprocess.CompletedProcess(
        list(command), target.returncode, stdout, stderr
    )
    return completed, observation, process_image


def _start_observer() -> _ObserverState:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS Sandbox network observer requires Darwin")
    identity = _regular_file_identity(LOG_PATH)
    process = subprocess.Popen(
        [
            identity["resolved_path"],
            "stream",
            "--style",
            "ndjson",
            "--level",
            "info",
            "--predicate",
            PREDICATE,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise RuntimeError("macOS Sandbox observer pipes were not created")
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        ready_sources = selector.select(_READY_TIMEOUT_SECONDS)
        if not ready_sources:
            raise RuntimeError("macOS Sandbox observer did not become ready")
        ready_pipe = ready_sources[0][0].fileobj
        ready = ready_pipe.readline(_MAX_READY_BYTES + 1)
        if len(ready) > _MAX_READY_BYTES or not ready.startswith(_READY_PREFIX):
            raise RuntimeError("macOS Sandbox observer readiness message differs")
    except BaseException:
        _stop_process(process)
        raise
    finally:
        selector.close()

    stdout = _BoundedBytes(_MAX_STDOUT_BYTES)
    stderr = _BoundedBytes(_MAX_STDERR_BYTES)
    threads = (
        threading.Thread(
            target=_drain_pipe,
            args=(process.stdout, stdout),
            name="sunofriend-sandbox-log-stdout",
            daemon=True,
        ),
        threading.Thread(
            target=_drain_pipe,
            args=(process.stderr, stderr),
            name="sunofriend-sandbox-log-stderr",
            daemon=True,
        ),
    )
    for thread in threads:
        thread.start()
    return _ObserverState(process, identity, stdout, stderr, threads)


def _finish_observer(
    state: _ObserverState,
    *,
    target_pid: int,
    expected_canary_port: int,
) -> Mapping[str, Any]:
    if type(target_pid) is not int or target_pid <= 0:
        _abort_observer(state)
        raise ValueError("macOS Sandbox observer target PID is invalid")
    if type(expected_canary_port) is not int or not 1 <= expected_canary_port <= 65535:
        _abort_observer(state)
        raise ValueError("macOS Sandbox observer canary port is invalid")
    time.sleep(_DRAIN_SECONDS)
    _stop_process(state.process)
    for thread in state.threads:
        thread.join(_STOP_TIMEOUT_SECONDS)
    if any(thread.is_alive() for thread in state.threads):
        raise RuntimeError("macOS Sandbox observer reader did not stop")
    if state.process.returncode != 0:
        raise RuntimeError("macOS Sandbox observer did not stop cleanly")
    if state.stdout.overflow or state.stderr.overflow:
        raise RuntimeError("macOS Sandbox observer exceeded its byte bound")
    if state.stderr.total:
        raise RuntimeError("macOS Sandbox observer emitted unexpected stderr")
    identity_after = _regular_file_identity(LOG_PATH)
    if any(
        state.identity_before[key] != identity_after[key] for key in ("bytes", "sha256")
    ):
        raise RuntimeError("macOS Sandbox observer executable changed")
    return _build_observation(
        raw_stdout=bytes(state.stdout.data),
        stdout_bytes=state.stdout.total,
        target_pid=target_pid,
        expected_canary_port=expected_canary_port,
        identity=state.identity_before,
    )


def _abort_observer(state: _ObserverState) -> None:
    if state.process.poll() is None:
        _stop_process(state.process)
    for thread in state.threads:
        thread.join(_STOP_TIMEOUT_SECONDS)


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_STOP_TIMEOUT_SECONDS)


def _drain_pipe(pipe: Any, destination: _BoundedBytes) -> None:
    while True:
        chunk = pipe.read(8192)
        if not chunk:
            return
        destination.add(chunk)


def _build_observation(
    *,
    raw_stdout: bytes,
    stdout_bytes: int,
    target_pid: int,
    expected_canary_port: int,
    identity: Mapping[str, Any],
) -> Mapping[str, Any]:
    try:
        text = raw_stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("macOS Sandbox observer output was not UTF-8") from error
    records: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "macOS Sandbox observer emitted malformed JSON"
            ) from error
        if not isinstance(item, dict):
            raise RuntimeError("macOS Sandbox observer record was not an object")
        if set(item) == {"count", "finished"}:
            if summary is not None or item["finished"] != 1:
                raise RuntimeError("macOS Sandbox observer final summary differs")
            summary = item
            continue
        if summary is not None:
            raise RuntimeError("macOS Sandbox observer event followed final summary")
        if len(records) >= _MAX_EVENT_RECORDS:
            raise RuntimeError("macOS Sandbox observer exceeded its event bound")
        if (
            item.get("eventType") != "logEvent"
            or item.get("senderImagePath") != SENDER_IMAGE_PATH
            or not isinstance(item.get("eventMessage"), str)
        ):
            raise RuntimeError("macOS Sandbox observer event identity differs")
        records.append(item)
    if summary is None or type(summary.get("count")) is not int:
        raise RuntimeError("macOS Sandbox observer final summary is absent")
    if summary["count"] != len(records):
        raise RuntimeError("macOS Sandbox observer final count differs")

    target_operations: dict[str, int] = {}
    target_count = 0
    canary_count = 0
    unrelated_count = 0
    canary_marker = f"remote:*:{expected_canary_port}"
    for record in records:
        match = _MESSAGE_RE.fullmatch(record["eventMessage"])
        if match is None:
            raise RuntimeError("macOS Sandbox observer denial message differs")
        event_pid = int(match.group(1))
        operation = match.group(3)
        detail = match.group(4) or ""
        if event_pid != target_pid:
            unrelated_count += 1
            continue
        target_count += 1
        target_operations[operation] = target_operations.get(operation, 0) + 1
        if operation == "network-outbound" and canary_marker in detail.split():
            canary_count += 1
    if canary_count < 1:
        raise RuntimeError("macOS Sandbox observer did not see the deliberate canary")

    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "sandbox_network_denials_bound_to_exact_child_pid",
        "provider": {
            "bytes": identity["bytes"],
            "sha256": identity["sha256"],
            "unchanged_after_observation": True,
        },
        "query": {
            "predicate_sha256": hashlib.sha256(PREDICATE.encode("utf-8")).hexdigest(),
            "style": "ndjson",
            "level": "info",
            "ready_before_child": True,
        },
        "bounds": {
            "stdout_limit_bytes": _MAX_STDOUT_BYTES,
            "stderr_limit_bytes": _MAX_STDERR_BYTES,
            "event_limit": _MAX_EVENT_RECORDS,
            "drain_milliseconds": round(_DRAIN_SECONDS * 1000),
            "stdout_bytes": stdout_bytes,
        },
        "observation": {
            "final_summary_verified": True,
            "summary_event_count": len(records),
            "target_pid_bound": True,
            "target_network_denial_count": target_count,
            "target_operation_counts": [
                {"operation": operation, "count": count}
                for operation, count in sorted(target_operations.items())
            ],
            "deliberate_canary_denial_count": canary_count,
            "other_target_network_denial_count": target_count - canary_count,
            "unrelated_network_denial_count": unrelated_count,
            "malformed_record_count": 0,
            "overflow_observed": False,
        },
        "privacy": {
            "raw_log_persisted": False,
            "raw_event_messages_retained": False,
            "destination_details_retained": False,
            "target_pid_retained": False,
        },
        "limitations": {
            "sandbox_denied_network_acquisitions_only": True,
            "successful_network_operations_observed": False,
            "unified_logging_is_not_a_packet_monitor": True,
            "executable_path_toctou_closed": False,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_macos_sandbox_network_observation(document)


def _validate_macos_sandbox_network_observation(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    digest = value.pop("evidence_sha256", None) if isinstance(value, dict) else None
    if (
        not _is_sha(digest)
        or digest != hashlib.sha256(_canonical_json_bytes(value)).hexdigest()
    ):
        raise ValueError("macOS Sandbox network observation self-hash differs")
    if (
        value.get("schema") != SCHEMA
        or value.get("policy_id") != POLICY_ID
        or value.get("status") != "sandbox_network_denials_bound_to_exact_child_pid"
        or set(value)
        != {
            "schema",
            "policy_id",
            "status",
            "provider",
            "query",
            "bounds",
            "observation",
            "privacy",
            "limitations",
        }
    ):
        raise ValueError("macOS Sandbox network observation fields differ")
    if (
        value["provider"]
        != {
            "bytes": value["provider"].get("bytes"),
            "sha256": value["provider"].get("sha256"),
            "unchanged_after_observation": True,
        }
        or type(value["provider"]["bytes"]) is not int
        or value["provider"]["bytes"] <= 0
        or not _is_sha(value["provider"]["sha256"])
    ):
        raise ValueError("macOS Sandbox network observer identity differs")
    if value["query"] != {
        "predicate_sha256": hashlib.sha256(PREDICATE.encode("utf-8")).hexdigest(),
        "style": "ndjson",
        "level": "info",
        "ready_before_child": True,
    }:
        raise ValueError("macOS Sandbox network observer query differs")
    bounds = value["bounds"]
    if (
        bounds
        != {
            "stdout_limit_bytes": _MAX_STDOUT_BYTES,
            "stderr_limit_bytes": _MAX_STDERR_BYTES,
            "event_limit": _MAX_EVENT_RECORDS,
            "drain_milliseconds": round(_DRAIN_SECONDS * 1000),
            "stdout_bytes": bounds.get("stdout_bytes"),
        }
        or type(bounds["stdout_bytes"]) is not int
        or not 1 <= bounds["stdout_bytes"] <= _MAX_STDOUT_BYTES
    ):
        raise ValueError("macOS Sandbox network observer bounds differ")
    observation = value["observation"]
    operations = observation.get("target_operation_counts")
    if (
        set(observation)
        != {
            "final_summary_verified",
            "summary_event_count",
            "target_pid_bound",
            "target_network_denial_count",
            "target_operation_counts",
            "deliberate_canary_denial_count",
            "other_target_network_denial_count",
            "unrelated_network_denial_count",
            "malformed_record_count",
            "overflow_observed",
        }
        or observation["final_summary_verified"] is not True
        or observation["target_pid_bound"] is not True
        or not isinstance(operations, list)
        or any(
            set(item) != {"operation", "count"}
            or not isinstance(item["operation"], str)
            or not item["operation"].startswith("network-")
            or type(item["count"]) is not int
            or item["count"] <= 0
            for item in operations
        )
        or [item["operation"] for item in operations]
        != sorted(item["operation"] for item in operations)
    ):
        raise ValueError("macOS Sandbox network observation counts differ")
    integers = (
        "summary_event_count",
        "target_network_denial_count",
        "deliberate_canary_denial_count",
        "other_target_network_denial_count",
        "unrelated_network_denial_count",
        "malformed_record_count",
    )
    if any(
        type(observation[name]) is not int or observation[name] < 0 for name in integers
    ):
        raise ValueError("macOS Sandbox network observation integer differs")
    if (
        observation["deliberate_canary_denial_count"] < 1
        or observation["target_network_denial_count"]
        != sum(item["count"] for item in operations)
        or observation["other_target_network_denial_count"]
        != observation["target_network_denial_count"]
        - observation["deliberate_canary_denial_count"]
        or observation["summary_event_count"]
        != observation["target_network_denial_count"]
        + observation["unrelated_network_denial_count"]
        or observation["malformed_record_count"] != 0
        or observation["overflow_observed"] is not False
    ):
        raise ValueError("macOS Sandbox network observation accounting differs")
    if value["privacy"] != {
        "raw_log_persisted": False,
        "raw_event_messages_retained": False,
        "destination_details_retained": False,
        "target_pid_retained": False,
    } or value["limitations"] != {
        "sandbox_denied_network_acquisitions_only": True,
        "successful_network_operations_observed": False,
        "unified_logging_is_not_a_packet_monitor": True,
        "executable_path_toctou_closed": False,
    }:
        raise ValueError("macOS Sandbox network observation boundary differs")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("macOS Sandbox network observation is not path-free")
    return _freeze_json(checked)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "POLICY_ID",
    "SCHEMA",
    "_run_with_macos_sandbox_network_and_process_image_observer",
    "_run_with_macos_sandbox_network_process_image_and_ready_observer",
    "_run_with_macos_sandbox_network_observer",
    "_validate_macos_sandbox_network_observation",
]
