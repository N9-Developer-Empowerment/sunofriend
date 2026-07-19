"""Bounded parent-owned MuScriptor worker sessions.

The session uses one inherited Unix socket pair: it opens no listening port,
cannot outlive its parent intentionally, serialises every inference request and
exits after a small fixed number of requests. Candidate and MIDI processing
remain in :mod:`sunofriend.ai_bakeoff`; this module only transports one
hash-pinned request at a time to an already-loaded model.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import select
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from .ai_worker import (
    MUSCRIPTOR_SESSION_COMMAND_SCHEMA,
    MUSCRIPTOR_SESSION_RESPONSE_SCHEMA,
    MUSCRIPTOR_SESSION_TRANSPORT,
)


MUSCRIPTOR_PARENT_SESSION_SCHEMA = "sunofriend.muscriptor-parent-session.v1"
_MAX_MESSAGE_BYTES = 65_536


class PersistentWorkerError(RuntimeError):
    """A bounded worker session failed or violated its protocol."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


class PersistentMuScriptorSession:
    """One loaded MuScriptor model serving a bounded serial request sequence."""

    def __init__(
        self,
        *,
        python: str | Path,
        worker_path: str | Path,
        session_root: str | Path,
        template_path: str | Path,
        session_id: str,
        bpm: float,
        maximum_requests: int,
        startup_timeout_seconds: float = 180.0,
    ) -> None:
        if maximum_requests < 2 or maximum_requests > 20:
            raise ValueError("maximum_requests must be between 2 and 20")
        if not math.isfinite(bpm) or bpm <= 0:
            raise ValueError("bpm must be finite and positive")
        if (
            not math.isfinite(startup_timeout_seconds)
            or startup_timeout_seconds <= 0
        ):
            raise ValueError("startup_timeout_seconds must be finite and positive")
        self.python = Path(python).expanduser().absolute()
        self.worker_path = Path(worker_path).expanduser().absolute()
        self.session_root = Path(session_root).expanduser().absolute()
        self.template_path = Path(template_path).expanduser().absolute()
        self.session_id = session_id
        self.bpm = float(bpm)
        self.maximum_requests = maximum_requests
        if not self.python.is_file():
            raise FileNotFoundError(f"AI interpreter was not found: {self.python}")
        if not self.worker_path.is_file() or self.worker_path.is_symlink():
            raise FileNotFoundError(
                f"AI worker must be an existing non-symlink file: {self.worker_path}"
            )
        if not self.session_root.is_dir() or self.session_root.is_symlink():
            raise ValueError("session_root must be an existing non-symlink directory")
        if (
            not self.template_path.is_file()
            or self.template_path.is_symlink()
            or self.template_path.resolve()
            != (self.session_root.resolve() / "session.request-template.json")
        ):
            raise ValueError("session template is not the fixed session-root template")

        self.worker_sha256 = _sha256(self.worker_path)
        self.template_sha256 = _sha256(self.template_path)
        template = json.loads(self.template_path.read_text(encoding="utf-8"))
        self.source_sha256 = _sha256(Path(str(template["audio_path"])))
        options = template.get("options", {})
        self.checkpoint_sha256 = str(options.get("model_sha256", ""))
        self.config_sha256 = str(options.get("model_config_sha256", ""))
        self.requested_device = str(options.get("device", ""))

        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._sequence = 0
        self._closed = False
        self._poisoned = False
        parent_socket: socket.socket | None = None
        child_socket: socket.socket | None = None
        try:
            parent_socket, child_socket = socket.socketpair()
            self._socket = parent_socket
            self._stdout_handle = (self.session_root / "worker.stdout.log").open(
                "wb"
            )
            self._stderr_handle = (self.session_root / "worker.stderr.log").open(
                "wb"
            )
            self.command = [
                str(self.python),
                str(self.worker_path),
                "--session-template",
                str(self.template_path),
                "--session-root",
                str(self.session_root),
                "--session-id",
                self.session_id,
                "--maximum-requests",
                str(self.maximum_requests),
                "--control-fd",
                str(child_socket.fileno()),
            ]
            environment = os.environ.copy()
            environment.update(
                {
                    "HF_HUB_OFFLINE": "1",
                    "HF_DATASETS_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                }
            )
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.DEVNULL,
                stdout=self._stdout_handle,
                stderr=self._stderr_handle,
                pass_fds=(child_socket.fileno(),),
                close_fds=True,
                env=environment,
            )
        except BaseException:
            for stream in (
                getattr(self, "_stdout_handle", None),
                getattr(self, "_stderr_handle", None),
            ):
                if stream is not None:
                    stream.close()
            for endpoint in (child_socket, parent_socket):
                if endpoint is not None:
                    endpoint.close()
            raise
        child_socket.close()
        try:
            ready = self._receive(startup_timeout_seconds)
            self._validate_ready(ready)
            self.ready = ready
            self.worker_instance_id = str(ready["worker_instance_id"])
            _atomic_json(self.session_root / "session.ready.json", ready)
        except BaseException:
            self._poison_and_reap()
            raise

    def __enter__(self) -> PersistentMuScriptorSession:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    def execute(
        self,
        *,
        run_id: str,
        request_path: Path,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if self._closed or self._poisoned:
            raise PersistentWorkerError("persistent worker session is not usable")
        if not self._lock.acquire(blocking=False):
            raise PersistentWorkerError("persistent worker requests must be serial")
        try:
            expected_sequence = self._sequence + 1
            if expected_sequence > self.maximum_requests:
                raise PersistentWorkerError("persistent worker request limit reached")
            run_dir = self.session_root.resolve() / run_id
            request = request_path.expanduser().absolute()
            if (
                request.is_symlink()
                or request.resolve() != run_dir / "request.json"
                or run_dir.parent != self.session_root.resolve()
            ):
                raise PersistentWorkerError("persistent request escaped session root")
            request_sha256 = _sha256(request)
            if request_sha256 != self.template_sha256:
                raise PersistentWorkerError(
                    "persistent request differs from the session template"
                )
            command = {
                "schema": MUSCRIPTOR_SESSION_COMMAND_SCHEMA,
                "operation": "transcribe",
                "session_id": self.session_id,
                "sequence": expected_sequence,
                "run_id": run_id,
                "request_sha256": request_sha256,
                "source_sha256": self.source_sha256,
            }
            started = time.monotonic()
            self._send(command)
            response = self._receive(timeout_seconds)
            elapsed = time.monotonic() - started
            # Preserve every bounded worker response before semantic validation.
            # The private run record therefore retains structured failure evidence.
            _atomic_json(run_dir / "worker.response.json", response)
            self._validate_result(
                response,
                run_id=run_id,
                sequence=expected_sequence,
                request_sha256=request_sha256,
                run_dir=run_dir,
            )
            self._sequence = expected_sequence
            return {
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "elapsed_seconds": elapsed,
                "response": response,
                "transport": MUSCRIPTOR_SESSION_TRANSPORT,
                "command": list(self.command),
            }
        except BaseException:
            self._poison_and_reap()
            raise
        finally:
            self._lock.release()

    def close(self, timeout_seconds: float = 30.0) -> dict[str, Any]:
        if self._poisoned:
            self._poison_and_reap()
            raise PersistentWorkerError("persistent worker session is poisoned")
        if self._closed:
            return getattr(self, "closed", {})
        if not self._lock.acquire(blocking=False):
            raise PersistentWorkerError(
                "cannot close a persistent worker while a request is active"
            )
        try:
            self._send(
                {
                    "schema": MUSCRIPTOR_SESSION_COMMAND_SCHEMA,
                    "operation": "shutdown",
                    "session_id": self.session_id,
                }
            )
            response = self._receive(timeout_seconds)
            _atomic_json(self.session_root / "session.closed.json", response)
            self._finish_closed(response, timeout_seconds=timeout_seconds)
            return response
        except BaseException:
            self._poison_and_reap()
            raise
        finally:
            self._close_handles()
            self._lock.release()

    def abort(self) -> None:
        self._poison_and_reap()

    def private_session_record(self) -> dict[str, Any]:
        return {
            "schema": MUSCRIPTOR_PARENT_SESSION_SCHEMA,
            "session_id": self.session_id,
            "bpm": self.bpm,
            "transport": MUSCRIPTOR_SESSION_TRANSPORT,
            "maximum_requests": self.maximum_requests,
            "worker": {
                "path": str(self.worker_path),
                "sha256": self.worker_sha256,
            },
            "python": str(self.python),
            "command": list(self.command),
            "request_template": {
                "path": str(self.template_path),
                "sha256": self.template_sha256,
            },
            "ready": self.ready,
            "closed": getattr(self, "closed", None),
            "request_count": self._sequence,
            "poisoned": self._poisoned,
        }

    def _send(self, document: Mapping[str, Any]) -> None:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        ) + b"\n"
        if len(payload) > _MAX_MESSAGE_BYTES:
            raise PersistentWorkerError("persistent worker command exceeds 64 KiB")
        self._socket.sendall(payload)

    def _receive(self, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                payload = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                if len(payload) > _MAX_MESSAGE_BYTES:
                    raise PersistentWorkerError("persistent worker response exceeds 64 KiB")
                try:
                    document = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise PersistentWorkerError(
                        f"invalid persistent worker response: {exc}"
                    ) from exc
                if not isinstance(document, dict):
                    raise PersistentWorkerError(
                        "persistent worker response must be a JSON object"
                    )
                return document
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PersistentWorkerError("persistent worker response timed out")
            readable, _writable, _errors = select.select(
                [self._socket], [], [], remaining
            )
            if not readable:
                raise PersistentWorkerError("persistent worker response timed out")
            block = self._socket.recv(8192)
            if not block:
                return_code = self._process.poll()
                raise PersistentWorkerError(
                    "persistent worker closed its control channel"
                    + (
                        ""
                        if return_code is None
                        else f" with process status {return_code}"
                    )
                )
            self._buffer.extend(block)
            if len(self._buffer) > _MAX_MESSAGE_BYTES + 1:
                raise PersistentWorkerError("persistent worker response exceeds 64 KiB")

    def _validate_ready(self, response: Mapping[str, Any]) -> None:
        if (
            response.get("schema") != MUSCRIPTOR_SESSION_RESPONSE_SCHEMA
            or response.get("kind") != "ready"
            or response.get("status") != "ready"
            or response.get("session_id") != self.session_id
            or response.get("transport") != MUSCRIPTOR_SESSION_TRANSPORT
            or response.get("model_load_count") != 1
            or response.get("request_template_sha256") != self.template_sha256
            or response.get("source_sha256") != self.source_sha256
            or response.get("checkpoint_sha256") != self.checkpoint_sha256
            or response.get("config_sha256") != self.config_sha256
            or response.get("maximum_requests") != self.maximum_requests
        ):
            raise PersistentWorkerError("persistent worker ready response is invalid")
        if response.get("device") not in {"cpu", "mps", "cuda"}:
            raise PersistentWorkerError("persistent worker effective device is invalid")
        if self.requested_device not in {"auto", response.get("device")}:
            raise PersistentWorkerError(
                "persistent worker effective device differs from the request"
            )
        for key in ("model_load_seconds", "startup_total_seconds"):
            value = response.get(key)
            if not isinstance(value, (int, float)) or value <= 0 or not math.isfinite(value):
                raise PersistentWorkerError(f"persistent worker {key} is invalid")
        if float(response["model_load_seconds"]) > float(
            response["startup_total_seconds"]
        ) + 0.05:
            raise PersistentWorkerError(
                "persistent worker model load exceeds startup time"
            )
        instance = response.get("worker_instance_id")
        if not isinstance(instance, str) or not instance:
            raise PersistentWorkerError("persistent worker instance identity is missing")

    def _validate_result(
        self,
        response: Mapping[str, Any],
        *,
        run_id: str,
        sequence: int,
        request_sha256: str,
        run_dir: Path,
    ) -> None:
        expected_warm = sequence > 1
        if response.get("status") != "complete":
            raise PersistentWorkerError(
                f"persistent worker request failed: {response.get('error_type', 'error')}"
            )
        if (
            response.get("schema") != MUSCRIPTOR_SESSION_RESPONSE_SCHEMA
            or response.get("kind") != "result"
            or response.get("session_id") != self.session_id
            or response.get("worker_instance_id") != self.worker_instance_id
            or response.get("sequence") != sequence
            or response.get("run_id") != run_id
            or response.get("request_sha256") != request_sha256
            or response.get("source_sha256") != self.source_sha256
            or response.get("model_load_count") != 1
            or response.get("prior_completed_requests") != sequence - 1
            or response.get("warm_model_request") is not expected_warm
            or response.get("model_reused_from_prior_request") is not expected_warm
        ):
            raise PersistentWorkerError("persistent worker result response is invalid")
        candidate = run_dir / "candidate.raw.json"
        performance = run_dir / "muscriptor.performance.json"
        if not candidate.is_file() or not performance.is_file():
            raise PersistentWorkerError("persistent worker omitted required output")
        if response.get("candidate_sha256") != _sha256(candidate):
            raise PersistentWorkerError("persistent candidate hash does not match")
        if response.get("performance_sha256") != _sha256(performance):
            raise PersistentWorkerError("persistent performance hash does not match")

    def _finish_closed(
        self, response: Mapping[str, Any], *, timeout_seconds: float
    ) -> None:
        if (
            response.get("schema") != MUSCRIPTOR_SESSION_RESPONSE_SCHEMA
            or response.get("kind") != "closed"
            or response.get("status") != "complete"
            or response.get("session_id") != self.session_id
            or response.get("worker_instance_id") != self.worker_instance_id
            or response.get("request_count") != self._sequence
            or response.get("completed_request_count") != self._sequence
            or response.get("model_load_count") != 1
            or response.get("integrity_status") != "verified-unchanged"
            or response.get("changed_inputs") != []
        ):
            raise PersistentWorkerError("persistent worker close response is invalid")
        try:
            self._socket.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        return_code = self._process.wait(timeout=timeout_seconds)
        if return_code != 0:
            raise PersistentWorkerError(
                f"persistent worker exited with status {return_code}"
            )
        self.closed = dict(response)
        self._closed = True
        self._socket.close()
        self._close_handles()

    def _poison_and_reap(self) -> None:
        self._poisoned = True
        process = getattr(self, "_process", None)
        try:
            running = process is not None and process.poll() is None
        except BaseException:
            running = process is not None
        if running and process is not None:
            try:
                process.terminate()
            except BaseException:
                pass
            try:
                process.wait(timeout=5.0)
            except BaseException:
                try:
                    process.kill()
                except BaseException:
                    pass
                try:
                    process.wait(timeout=5.0)
                except BaseException:
                    pass
        self._closed = True
        try:
            self._socket.close()
        except BaseException:
            pass
        try:
            self._close_handles()
        except BaseException:
            pass

    def _close_handles(self) -> None:
        for handle in (
            getattr(self, "_stdout_handle", None),
            getattr(self, "_stderr_handle", None),
        ):
            if handle is not None and not handle.closed:
                handle.close()


__all__ = [
    "MUSCRIPTOR_PARENT_SESSION_SCHEMA",
    "PersistentMuScriptorSession",
    "PersistentWorkerError",
]
