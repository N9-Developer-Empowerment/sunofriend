"""Bounded repeated MuScriptor transcription sessions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ai_bakeoff import (
    MUSCRIPTOR_INSTRUMENT_ROLES,
    prepare_ai_transcription_request,
    run_ai_transcription,
)
from .ai_runtime import AI_MODEL_MANIFESTS, resolve_ai_python
from .ai_worker_session import PersistentMuScriptorSession


MUSCRIPTOR_SESSION_SCHEMA = "sunofriend.muscriptor-transcription-session.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    label = path.relative_to(relative_to) if relative_to else path
    return {
        "path": str(label),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"muscriptor-session-{timestamp}-{secrets.token_hex(4)}"


def run_muscriptor_session(
    *,
    audio_path: str | Path,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    bpm: float,
    repetitions: int,
    roles: Sequence[str] = (),
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    options: Mapping[str, Any] | None = None,
    python: str | Path | None = None,
    worker_path: str | Path | None = None,
    startup_timeout_seconds: float = 180.0,
    request_timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Load one model, transcribe the same request serially, then exit."""

    if repetitions < 2 or repetitions > 20:
        raise ValueError("repetitions must be between 2 and 20")
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("bpm must be finite and positive")
    if not math.isfinite(startup_timeout_seconds) or startup_timeout_seconds <= 0:
        raise ValueError("startup_timeout_seconds must be finite and positive")
    if not math.isfinite(request_timeout_seconds) or request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be finite and positive")
    unknown_roles = sorted(set(roles) - MUSCRIPTOR_INSTRUMENT_ROLES)
    if unknown_roles:
        raise ValueError(
            "unknown MuScriptor instrument role(s): "
            + ", ".join(unknown_roles)
            + "; use exact canonical instrument names"
        )

    session_started_clock = time.monotonic()
    started_at = _utc_now()
    root = Path(out_dir).expanduser().absolute().resolve()
    if root.exists():
        raise FileExistsError(
            f"MuScriptor session already exists and will not be overwritten: {root}"
        )
    executable = resolve_ai_python(python)
    worker = (
        Path(worker_path).expanduser().absolute()
        if worker_path
        else Path(__file__).with_name("ai_worker.py")
    )
    if not worker.is_file() or worker.is_symlink():
        raise FileNotFoundError(
            f"AI worker must be an existing non-symlink file: {worker}"
        )
    worker_record = _record(worker)
    request, source_record, checkpoint_record, execution = (
        prepare_ai_transcription_request(
            audio_path=audio_path,
            checkpoint_path=checkpoint_path,
            backend="muscriptor",
            roles=roles,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            options=options,
        )
    )
    try:
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"MuScriptor session already exists and will not be overwritten: {root}"
        ) from exc
    template_path = root / "session.request-template.json"
    _atomic_json(template_path, request.to_dict())
    identifier = _session_id()
    started_path = root / "session.started.json"
    manifest_path = root / "session.json"
    _atomic_json(
        started_path,
        {
            "schema": MUSCRIPTOR_SESSION_SCHEMA,
            "session_id": identifier,
            "status": "starting",
            "started_at": started_at,
            "repetitions": repetitions,
            "source": source_record,
            "checkpoint": checkpoint_record,
            "worker": worker_record,
            "python": str(executable),
            "request_template": request.to_dict(),
            "execution": execution,
            "bpm": bpm,
            "backend_manifest": asdict(AI_MODEL_MANIFESTS["muscriptor"]),
            "cache_regime": {
                "worker_process": "bounded-shared-session",
                "model_loaded_once": None,
                "application_content_cache": False,
                "cache_hits": 0,
                "operating_system_file_cache": "uncontrolled",
                "cold_start_claimed": False,
            },
        },
    )

    prepared_inputs = (request, source_record, checkpoint_record, execution)
    preparation_elapsed_seconds = time.monotonic() - session_started_clock
    runs: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    session: PersistentMuScriptorSession | None = None
    error: str | None = None
    caught: BaseException | None = None
    startup_elapsed_seconds: float | None = None
    request_phase_elapsed_seconds: float | None = None
    shutdown_elapsed_seconds: float | None = None
    startup_started_clock = time.monotonic()
    try:
        session = PersistentMuScriptorSession(
            python=executable,
            worker_path=worker,
            session_root=root,
            template_path=template_path,
            session_id=identifier,
            bpm=bpm,
            maximum_requests=repetitions,
            startup_timeout_seconds=startup_timeout_seconds,
        )
        startup_elapsed_seconds = time.monotonic() - startup_started_clock
        request_phase_started_clock = time.monotonic()
        for index in range(1, repetitions + 1):
            run_id = f"repetition-{index:03d}"
            attempt: dict[str, Any] = {
                "run_id": run_id,
                "run_dir": str(root / run_id),
                "sequence": index,
                "expected_warm_model_request": index > 1,
                "status": "running",
            }
            attempts.append(attempt)
            try:
                manifest = run_ai_transcription(
                    audio_path=audio_path,
                    out_dir=root,
                    checkpoint_path=checkpoint_path,
                    bpm=bpm,
                    backend="muscriptor",
                    roles=roles,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    options=options,
                    python=executable,
                    worker_path=worker,
                    worker_session=session,
                    _prepared_inputs=prepared_inputs,
                    timeout_seconds=request_timeout_seconds,
                    run_id=run_id,
                )
            except BaseException:
                run_manifest_path = root / run_id / "run.json"
                attempt["status"] = "failed"
                if run_manifest_path.is_file():
                    failed_run = json.loads(
                        run_manifest_path.read_text(encoding="utf-8")
                    )
                    attempt["run_json_sha256"] = _sha256(run_manifest_path)
                    attempt["artifacts"] = failed_run.get("artifacts", {})
                    attempt["error"] = failed_run.get("error")
                raise
            run_row = {
                "run_id": run_id,
                "run_dir": str(root / run_id),
                "run_json_sha256": _sha256(root / run_id / "run.json"),
                "candidate_json_sha256": manifest["artifacts"]["candidate.json"][
                    "sha256"
                ],
                "candidate_midi_sha256": manifest["artifacts"]["candidate.mid"][
                    "sha256"
                ],
                "sequence": manifest["worker_transport"]["sequence"],
                "warm_model_request": manifest["worker_transport"][
                    "warm_model_request"
                ],
            }
            runs.append(run_row)
            attempt.update({**run_row, "status": "complete"})
        request_phase_elapsed_seconds = (
            time.monotonic() - request_phase_started_clock
        )
        shutdown_started_clock = time.monotonic()
        session.close(timeout_seconds=request_timeout_seconds)
        shutdown_elapsed_seconds = time.monotonic() - shutdown_started_clock
    except BaseException as exc:
        if startup_elapsed_seconds is None:
            startup_elapsed_seconds = time.monotonic() - startup_started_clock
        if "request_phase_started_clock" in locals() and request_phase_elapsed_seconds is None:
            request_phase_elapsed_seconds = (
                time.monotonic() - request_phase_started_clock
            )
        if "shutdown_started_clock" in locals() and shutdown_elapsed_seconds is None:
            shutdown_elapsed_seconds = time.monotonic() - shutdown_started_clock
        error = f"{type(exc).__name__}: {exc}"
        caught = exc
        if session is not None and not session.poisoned:
            session.abort()

    completed_at = _utc_now()
    total_elapsed_seconds = time.monotonic() - session_started_clock
    artifacts: dict[str, Any] = {}
    for path in (
        template_path,
        started_path,
        root / "session.ready.json",
        root / "session.closed.json",
        root / "worker.stdout.log",
        root / "worker.stderr.log",
    ):
        if path.is_file():
            artifacts[path.name] = _record(path, relative_to=root)
    manifest = {
        "schema": MUSCRIPTOR_SESSION_SCHEMA,
        "session_id": identifier,
        "status": "complete" if error is None else "failed",
        "started_at": started_at,
        "completed_at": completed_at,
        "repetitions_requested": repetitions,
        "repetitions_attempted": len(attempts),
        "repetitions_completed": len(runs),
        "source": source_record,
        "checkpoint": checkpoint_record,
        "worker": worker_record,
        "runtime": (
            runs and json.loads((root / runs[0]["run_id"] / "run.json").read_text())[
                "runtime"
            ]
        )
        or None,
        "request_template": request.to_dict(),
        "execution": execution,
        "bpm": bpm,
        "runs": runs,
        "attempts": attempts,
        "ready": (
            json.loads((root / "session.ready.json").read_text(encoding="utf-8"))
            if (root / "session.ready.json").is_file()
            else None
        ),
        "closed": (
            json.loads((root / "session.closed.json").read_text(encoding="utf-8"))
            if (root / "session.closed.json").is_file()
            else None
        ),
        "cache_regime": {
            "worker_process": "bounded-shared-session",
            "model_loaded_once": bool(
                (root / "session.ready.json").is_file()
                and json.loads(
                    (root / "session.ready.json").read_text(encoding="utf-8")
                ).get("model_load_count")
                == 1
            ),
            "model_reused_across_requests": len(runs) > 1,
            "application_content_cache": False,
            "cache_hits": 0,
            "operating_system_file_cache": "uncontrolled",
            "cold_start_claimed": False,
        },
        "parent_timings_seconds": {
            "prepare_and_publish": preparation_elapsed_seconds,
            "worker_startup_to_ready": startup_elapsed_seconds,
            "request_phase": request_phase_elapsed_seconds,
            "worker_shutdown_and_final_integrity": shutdown_elapsed_seconds,
            "session_total": total_elapsed_seconds,
        },
        "parent_clock": "time.monotonic",
        "artifacts": artifacts,
        "error": error,
        "promotion_allowed": False,
        "automatic_selection": False,
        "raw_candidates_mutated": False,
        "midi_notes_mutated": 0,
    }
    _atomic_json(manifest_path, manifest)
    if error is not None:
        if caught is not None and not isinstance(caught, Exception):
            raise caught
        raise RuntimeError(
            f"MuScriptor session failed; immutable session record: {manifest_path}; "
            f"{error}"
        )
    return manifest


__all__ = ["MUSCRIPTOR_SESSION_SCHEMA", "run_muscriptor_session"]
