"""Path-free evidence for bounded reused-model MuScriptor sessions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ai_bakeoff import MUSCRIPTOR_INSTRUMENT_ROLES, _candidate_tracks
from .ai_benchmark import build_ai_performance_benchmark
from .ai_matrix import build_ai_candidate_matrix
from .ai_runtime import AITranscriptionCandidate
from .ai_session import MUSCRIPTOR_SESSION_SCHEMA
from .midi import write_midi_file
from .ai_worker import (
    MUSCRIPTOR_SESSION_REQUEST_PERFORMANCE_SCHEMA,
    MUSCRIPTOR_SESSION_RESPONSE_SCHEMA,
    MUSCRIPTOR_SESSION_TRANSPORT,
)


AI_SESSION_BENCHMARK_SCHEMA = "sunofriend.ai-session-performance-benchmark.v1"
_REQUEST_TIMING_FIELDS = (
    "audio_preparation",
    "transcription",
    "request_total",
    "time_to_first_note_start",
    "time_to_first_completed_note",
    "time_to_first_completed_chunk",
)
_SESSION_MEMORY_SCOPE = (
    "persistent process RSS high-water including model load and prior requests; "
    "accelerator allocation excluded"
)
_CLOCK = "time.perf_counter"
_TOLERANCE_SECONDS = 0.05
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_INSTANCE_ID = re.compile(r"^[0-9a-f]{32}$")
_SESSION_REQUEST_FIELDS = {
    "session_id",
    "worker_instance_id",
    "sequence",
    "prior_completed_requests",
    "warm_model_request",
    "model_reused_from_prior_request",
    "model_load_count",
    "request_started_at",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_ai_session_benchmark(
    session_dir: str | Path,
    fresh_run_dirs: Sequence[str | Path],
    output_path: str | Path,
) -> dict[str, Any]:
    """Verify one completed session and publish a fresh path-free report."""

    output = Path(output_path).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"AI session benchmark already exists: {output}")
    report = build_ai_session_benchmark(session_dir, fresh_run_dirs)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise FileExistsError(
                f"AI session benchmark already exists: {output}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return report


def build_ai_session_benchmark(
    session_dir: str | Path,
    fresh_run_dirs: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Validate reused-model requests separately from optional fresh controls."""

    root = Path(session_dir).expanduser().absolute().resolve()
    session = _read_json(root / "session.json", "session manifest")
    if (
        session.get("schema") != MUSCRIPTOR_SESSION_SCHEMA
        or session.get("status") != "complete"
    ):
        raise ValueError("AI session benchmark requires a completed session")
    session_id = _nonempty(session.get("session_id"), "session_id")
    if not _SAFE_SESSION_ID.fullmatch(session_id):
        raise ValueError("AI session has an unsafe session_id")
    session_cache = session.get("cache_regime")
    if (
        not isinstance(session_cache, Mapping)
        or session_cache.get("worker_process") != "bounded-shared-session"
        or session_cache.get("model_loaded_once") is not True
        or session_cache.get("model_reused_across_requests") is not True
        or session_cache.get("application_content_cache") is not False
        or session_cache.get("cache_hits") != 0
        or session_cache.get("operating_system_file_cache") != "uncontrolled"
        or session_cache.get("cold_start_claimed") is not False
        or session.get("promotion_allowed") is not False
        or session.get("automatic_selection") is not False
        or session.get("raw_candidates_mutated") is not False
        or session.get("midi_notes_mutated") != 0
    ):
        raise ValueError("AI session policy or cache evidence is invalid")
    run_rows = session.get("runs")
    if not isinstance(run_rows, list) or len(run_rows) < 2:
        raise ValueError("AI session benchmark needs at least two session requests")
    if session.get("repetitions_completed") != len(run_rows):
        raise ValueError("AI session completed count disagrees with its run list")
    attempts = session.get("attempts")
    if (
        session.get("repetitions_requested") != len(run_rows)
        or session.get("repetitions_attempted") != len(run_rows)
        or not isinstance(attempts, list)
        or len(attempts) != len(run_rows)
    ):
        raise ValueError("AI session complete record has invalid attempt counts")
    for attempt, run_row in zip(attempts, run_rows):
        if (
            not isinstance(attempt, Mapping)
            or attempt.get("status") != "complete"
            or any(
                attempt.get(key) != run_row.get(key)
                for key in (
                    "run_id",
                    "run_dir",
                    "sequence",
                    "run_json_sha256",
                    "candidate_json_sha256",
                    "candidate_midi_sha256",
                    "warm_model_request",
                )
            )
        ):
            raise ValueError("AI session attempt evidence disagrees with completed runs")

    ready = _verified_session_artifact(root, session, "session.ready.json")
    closed = _verified_session_artifact(root, session, "session.closed.json")
    started = _verified_session_artifact(root, session, "session.started.json")
    template = _verified_session_artifact(
        root, session, "session.request-template.json"
    )
    template_sha256 = _sha256(root / "session.request-template.json")
    for log_name in ("worker.stdout.log", "worker.stderr.log"):
        _verify_session_file(root, session, log_name)
    if ready.get("session_id") != session_id or closed.get("session_id") != session_id:
        raise ValueError("AI session ready/closed identities disagree")
    if (
        ready.get("schema") != MUSCRIPTOR_SESSION_RESPONSE_SCHEMA
        or ready.get("kind") != "ready"
        or ready.get("status") != "ready"
        or ready.get("transport") != MUSCRIPTOR_SESSION_TRANSPORT
        or ready.get("maximum_requests") != len(run_rows)
        or closed.get("schema") != MUSCRIPTOR_SESSION_RESPONSE_SCHEMA
        or closed.get("kind") != "closed"
        or closed.get("status") != "complete"
        or closed.get("integrity_status") != "verified-unchanged"
        or closed.get("changed_inputs") != []
    ):
        raise ValueError("AI session ready/closed protocol evidence is invalid")
    instance_id = _nonempty(ready.get("worker_instance_id"), "worker instance")
    if not _SAFE_INSTANCE_ID.fullmatch(instance_id):
        raise ValueError("AI session worker instance identity is invalid")
    if closed.get("worker_instance_id") != instance_id:
        raise ValueError("AI session worker instance changed before close")
    if ready.get("model_load_count") != 1 or closed.get("model_load_count") != 1:
        raise ValueError("AI session must load exactly one model")
    if closed.get("request_count") != len(run_rows) or closed.get(
        "completed_request_count"
    ) != len(run_rows):
        raise ValueError("AI session close record has an invalid request count")
    startup_seconds = _positive(ready.get("startup_total_seconds"), "startup total")
    model_load_seconds = _positive(ready.get("model_load_seconds"), "model load")
    if model_load_seconds > startup_seconds + _TOLERANCE_SECONDS:
        raise ValueError("AI session model load exceeds startup total")
    ready_started = _timestamp(ready.get("session_started_at"), "session ready start")
    model_loaded = _timestamp(ready.get("model_loaded_at"), "session model load time")
    closed_started = _timestamp(closed.get("session_started_at"), "session close start")
    closed_at = _timestamp(closed.get("completed_at"), "session close completed_at")
    parent_started = _timestamp(session.get("started_at"), "session parent started_at")
    parent_completed = _timestamp(
        session.get("completed_at"), "session parent completed_at"
    )
    if (
        model_loaded < ready_started
        or closed_started != ready_started
        or closed_at < model_loaded
        or ready_started < parent_started
        or parent_completed < closed_at
    ):
        raise ValueError("AI session lifecycle timestamps are invalid")
    session_total = _positive(closed.get("session_total_seconds"), "session total")
    if startup_seconds > session_total + _TOLERANCE_SECONDS:
        raise ValueError("AI session startup exceeds total session time")
    startup_rss = _positive_integer(
        ready.get("peak_process_rss_bytes"), "startup RSS"
    )
    _validate_started_record(
        started,
        session=session,
        session_id=session_id,
        run_count=len(run_rows),
        template=template,
    )
    if (
        session.get("error") is not None
        or session.get("ready") != ready
        or session.get("closed") != closed
    ):
        raise ValueError("AI session final snapshots contradict pinned lifecycle evidence")

    run_dirs: list[Path] = []
    for index, row in enumerate(run_rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError("AI session run list is invalid")
        expected_id = f"repetition-{index:03d}"
        if row.get("run_id") != expected_id or row.get("sequence") != index:
            raise ValueError("AI session run identities are not contiguous")
        run_dir = (root / expected_id).resolve()
        if run_dir.parent != root or not run_dir.is_dir():
            raise ValueError("AI session run directory escaped the session root")
        if (
            row.get("run_dir") != str(run_dir)
            or row.get("run_json_sha256") != _sha256(run_dir / "run.json")
            or row.get("warm_model_request") is not (index > 1)
        ):
            raise ValueError("AI session run.json changed after session close")
        run_dirs.append(run_dir)

    lanes = [(f"M3-session-{index:03d}", path) for index, path in enumerate(run_dirs, 1)]
    matrix = build_ai_candidate_matrix(lanes)
    matrix_rows = {row["lane"]: row for row in matrix["lanes"]}
    requested_roles = matrix_rows["M3-session-001"]["requested_labels"]
    if (
        not isinstance(requested_roles, list)
        or any(role not in MUSCRIPTOR_INSTRUMENT_ROLES for role in requested_roles)
    ):
        raise ValueError("AI session requested roles are not canonical MuScriptor roles")
    for index, row in enumerate(run_rows, start=1):
        matrix_row = matrix_rows[f"M3-session-{index:03d}"]
        if (
            row.get("candidate_json_sha256")
            != matrix_row["candidate_json_sha256"]
            or row.get("candidate_midi_sha256")
            != matrix_row["candidate_midi_sha256"]
            or not math.isclose(
                float(matrix_row["bpm"]), float(session.get("bpm", 0.0)), abs_tol=0.001
            )
            or matrix_row["source_sha256"]
            != matrix_rows["M3-session-001"]["source_sha256"]
            or matrix_row["requested_labels"]
            != matrix_rows["M3-session-001"]["requested_labels"]
        ):
            raise ValueError("AI session run row differs from its verified candidate")
    session_worker = session.get("worker")
    session_checkpoint = session.get("checkpoint")
    session_source = session.get("source")
    config = (
        session_checkpoint.get("config")
        if isinstance(session_checkpoint, Mapping)
        else None
    )
    if (
        not isinstance(session_worker, Mapping)
        or session_worker.get("sha256") != matrix["worker_sha256"]
        or not isinstance(session_checkpoint, Mapping)
        or session_checkpoint.get("sha256") != matrix["checkpoint_sha256"]
        or not isinstance(config, Mapping)
        or config.get("sha256") != matrix["model_config_sha256"]
        or not isinstance(session_source, Mapping)
        or session_source.get("sha256")
        != matrix_rows["M3-session-001"]["source_sha256"]
        or session.get("execution") != matrix["execution"]
        or ready.get("checkpoint_sha256") != matrix["checkpoint_sha256"]
        or ready.get("config_sha256") != matrix["model_config_sha256"]
        or ready.get("source_sha256")
        != matrix_rows["M3-session-001"]["source_sha256"]
        or ready.get("request_template_sha256")
        != template_sha256
        or template != session.get("request_template")
        or ready.get("model_size") != matrix["execution"].get("model_size")
        or not str(matrix["model_version"]).startswith(
            f"muscriptor-{ready.get('model_version')}/"
        )
    ):
        raise ValueError("AI session provenance differs from its verified runs")
    runtime_profile: dict[str, str] | None = None
    request_template_hash = template_sha256
    requests: list[dict[str, Any]] = []
    previous_completed: datetime | None = None
    previous_worker_completed: datetime | None = None
    rss_values: list[int] = []
    candidate_hashes: list[str] = []
    midi_hashes: list[str] = []
    response_elapsed_values: list[float] = []

    for index, run_dir in enumerate(run_dirs, start=1):
        lane = f"M3-session-{index:03d}"
        matrix_row = matrix_rows[lane]
        run = _read_json(run_dir / "run.json", f"session run {index}")
        candidate = _read_json(run_dir / "candidate.json", f"session candidate {index}")
        raw_candidate = _read_json(
            run_dir / "candidate.raw.json", f"session raw candidate {index}"
        )
        performance = _read_json(
            run_dir / "muscriptor.performance.json",
            f"session performance {index}",
        )
        response = _read_json(
            run_dir / "worker.response.json", f"session response {index}"
        )
        artifacts = run.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"AI session run {index} has no artifact manifest")
        for name in ("muscriptor.performance.json", "worker.response.json"):
            record = artifacts.get(name)
            if not isinstance(record, Mapping):
                raise ValueError(f"AI session run {index} does not pin {name}")
            if (
                record.get("path") != name
                or record.get("bytes") != (run_dir / name).stat().st_size
                or record.get("sha256") != _sha256(run_dir / name)
            ):
                raise ValueError(f"AI session run {index} {name} changed")
        if (
            run.get("worker_execution_mode") != "persistent-session-request"
            or run.get("worker_process_started_for_run") is not False
        ):
            raise ValueError("AI session run execution mode is invalid")
        canonical_raw = AITranscriptionCandidate.from_dict(raw_candidate).to_dict()
        expected_candidate = dict(raw_candidate)
        expected_candidate["manifest"] = canonical_raw["manifest"]
        if json.dumps(
            expected_candidate, sort_keys=True, separators=(",", ":")
        ) != json.dumps(candidate, sort_keys=True, separators=(",", ":")):
            raise ValueError("AI session candidate.json differs from worker raw output")
        _validate_candidate_midi(
            candidate,
            bpm=float(run.get("bpm", 0.0)),
            midi_path=run_dir / "candidate.mid",
        )
        transport = run.get("worker_transport")
        if not isinstance(transport, Mapping):
            raise ValueError(f"AI session run {index} has no worker transport evidence")
        expected_warm = index > 1
        if (
            transport.get("mode") != "bounded-persistent-session"
            or transport.get("session_id") != session_id
            or transport.get("worker_instance_id") != instance_id
            or transport.get("model_load_count") != 1
            or transport.get("sequence") != index
            or transport.get("prior_completed_requests") != index - 1
            or transport.get("warm_model_request") is not expected_warm
            or transport.get("model_reused_from_prior_request") is not expected_warm
        ):
            raise ValueError(f"AI session run {index} transport evidence is invalid")
        _validate_response(
            response,
            session_id=session_id,
            instance_id=instance_id,
            sequence=index,
            run_id=f"repetition-{index:03d}",
            source_sha256=str(ready["source_sha256"]),
            expected_note_count=int(matrix_row["note_count"]),
            request_path=run_dir / "request.json",
            candidate_path=run_dir / "candidate.raw.json",
            performance_path=run_dir / "muscriptor.performance.json",
        )
        candidate_metadata = candidate.get("metadata")
        excerpt = (
            candidate_metadata.get("excerpt")
            if isinstance(candidate_metadata, Mapping)
            else None
        )
        if not isinstance(excerpt, Mapping):
            raise ValueError("AI session candidate has no excerpt evidence")
        actual_duration = _positive(
            excerpt.get("duration_seconds"), "session actual duration"
        )
        normalised_performance = _validate_request_performance(
            performance,
            session_id=session_id,
            instance_id=instance_id,
            sequence=index,
            expected_warm=expected_warm,
            expected_device=str(ready.get("device")),
            expected_note_count=int(matrix_row["note_count"]),
            expected_chunk_seconds=float(matrix["execution"]["chunking"]["seconds"]),
            actual_duration_seconds=actual_duration,
        )
        worker_started = _timestamp(
            response.get("request_started_at"),
            f"session response {index} request_started_at",
        )
        worker_completed = _timestamp(
            response.get("completed_at"), f"session response {index} completed_at"
        )
        if worker_completed < worker_started:
            raise ValueError("AI session worker request completed before it started")
        if (
            previous_worker_completed is not None
            and worker_started < previous_worker_completed
        ):
            raise ValueError("AI session worker request windows overlap")
        previous_worker_completed = worker_completed
        if (
            normalised_performance["session"].get("request_started_at")
            != response.get("request_started_at")
        ):
            raise ValueError("AI session performance request start disagrees")
        parent_request = _positive(
            run.get("worker_request_elapsed_seconds"),
            f"session run {index} worker request",
        )
        response_elapsed = _positive(
            response.get("request_elapsed_seconds"),
            f"session response {index} elapsed",
        )
        pipeline = _positive(
            run.get("elapsed_seconds"), f"session run {index} pipeline"
        )
        worker_total = float(
            normalised_performance["timings_seconds"]["request_total"]
        )
        if worker_total > parent_request + _TOLERANCE_SECONDS:
            raise ValueError("AI session worker request exceeds parent round trip")
        if worker_total > response_elapsed + _TOLERANCE_SECONDS:
            raise ValueError("AI session request_total exceeds worker response time")
        if response_elapsed > parent_request + _TOLERANCE_SECONDS:
            raise ValueError("AI session response time exceeds parent round trip")
        if parent_request > pipeline + _TOLERANCE_SECONDS:
            raise ValueError("AI session parent round trip exceeds pipeline time")
        started = _timestamp(run.get("started_at"), f"session run {index} started_at")
        completed = _timestamp(
            run.get("completed_at"), f"session run {index} completed_at"
        )
        if completed < started:
            raise ValueError("AI session run completed before it started")
        if worker_started < started or worker_completed > completed:
            raise ValueError("AI session worker timing escapes the parent run window")
        if previous_completed is not None and started < previous_completed:
            raise ValueError("AI session request windows overlap")
        previous_completed = completed
        current_runtime = _runtime_profile(run.get("runtime"), lane=f"run {index}")
        if runtime_profile is None:
            runtime_profile = current_runtime
        elif runtime_profile != current_runtime:
            raise ValueError("AI session runtime profile changed between requests")
        current_request_hash = _sha256(run_dir / "request.json")
        if (
            current_request_hash != request_template_hash
            or _read_json(run_dir / "request.json", "session request") != template
        ):
            raise ValueError("AI session request differs from the exact startup template")
        transcription = float(
            normalised_performance["timings_seconds"]["transcription"]
        )
        row = {
            "sequence": index,
            "run_id": f"repetition-{index:03d}",
            "warm_model_request": expected_warm,
            "prior_completed_requests": index - 1,
            "actual_duration_seconds": _rounded(actual_duration),
            "pipeline_elapsed_seconds": _rounded(pipeline),
            "pipeline_real_time_factor": _rounded(pipeline / actual_duration),
            "worker_request_elapsed_seconds": _rounded(parent_request),
            "worker_request_real_time_factor": _rounded(
                parent_request / actual_duration
            ),
            "transcription_real_time_factor": _rounded(
                transcription / actual_duration
            ),
            "performance": normalised_performance,
            "note_count": int(matrix_row["note_count"]),
            "candidate_json_sha256": matrix_row["candidate_json_sha256"],
            "candidate_midi_sha256": matrix_row["candidate_midi_sha256"],
        }
        requests.append(row)
        rss_values.append(int(normalised_performance["peak_process_rss_bytes"]))
        response_elapsed_values.append(response_elapsed)
        candidate_hashes.append(str(matrix_row["candidate_json_sha256"]))
        midi_hashes.append(str(matrix_row["candidate_midi_sha256"]))

    if any(later < earlier for earlier, later in zip(rss_values, rss_values[1:])):
        raise ValueError("AI session process RSS high-water values decreased")
    if rss_values[0] < startup_rss:
        raise ValueError("AI session first request RSS is below startup high-water")
    final_rss = _positive_integer(closed.get("peak_process_rss_bytes"), "final RSS")
    if final_rss < max(rss_values):
        raise ValueError("AI session final RSS is below a request high-water mark")
    if session_total + _TOLERANCE_SECONDS < (
        startup_seconds + sum(response_elapsed_values)
    ):
        raise ValueError("AI session total is shorter than its serial worker activity")

    if runtime_profile is None or session.get("runtime") != _read_json(
        run_dirs[0] / "run.json", "first session run"
    ).get("runtime"):
        raise ValueError("AI session runtime snapshot differs from its first request")
    parent_timings = _validate_parent_timings(
        session,
        request_count=len(run_rows),
        pipeline_seconds=sum(
            float(row["pipeline_elapsed_seconds"]) for row in requests
        ),
        worker_startup_seconds=startup_seconds,
        worker_session_seconds=session_total,
    )

    first = requests[0]
    warm = requests[1:]
    warm_pipeline = [float(row["pipeline_elapsed_seconds"]) for row in warm]
    warm_request = [float(row["worker_request_elapsed_seconds"]) for row in warm]
    warm_transcription = [
        float(row["performance"]["timings_seconds"]["transcription"])
        for row in warm
    ]
    first_pipeline = float(first["pipeline_elapsed_seconds"])
    parent_timings["session_total_real_time_factor"] = _rounded(
        float(parent_timings["session_total_seconds"])
        / (float(first["actual_duration_seconds"]) * len(requests))
    )
    report: dict[str, Any] = {
        "schema": AI_SESSION_BENCHMARK_SCHEMA,
        "backend": "muscriptor",
        "session_id": session_id,
        "checkpoint_sha256": matrix["checkpoint_sha256"],
        "model_config_sha256": matrix["model_config_sha256"],
        "model_version": matrix["model_version"],
        "worker_sha256": matrix["worker_sha256"],
        "execution": matrix["execution"],
        "runtime_profile": runtime_profile,
        "source_sha256": matrix_rows["M3-session-001"]["source_sha256"],
        "excerpt": {
            "requested_start_seconds": _rounded(
                float(session["request_template"]["start_seconds"])
            ),
            "requested_end_seconds": (
                None
                if session["request_template"].get("end_seconds") is None
                else _rounded(float(session["request_template"]["end_seconds"]))
            ),
            "actual_duration_seconds": first["actual_duration_seconds"],
        },
        "bpm": matrix_rows["M3-session-001"]["bpm"],
        "roles": requested_roles,
        "device": ready["device"],
        "request_count": len(requests),
        "warm_request_count": len(warm),
        "cache_regime": {
            "worker_process": "bounded-shared-session",
            "model_loaded_once": True,
            "model_reused_across_requests": True,
            "application_content_cache": False,
            "cache_hits": 0,
            "operating_system_file_cache": "uncontrolled",
            "cold_start_claimed": False,
        },
        "session_startup": {
            "model_load_seconds": _rounded(model_load_seconds),
            "startup_total_seconds": _rounded(startup_seconds),
            "model_load_count": 1,
            "first_request_is_warm": False,
        },
        "parent_observed_session": parent_timings,
        "requests": requests,
        "steady_state_warm_aggregates": {
            "pipeline_elapsed_seconds": _summary(warm_pipeline),
            "worker_request_elapsed_seconds": _summary(warm_request),
            "transcription_seconds": _summary(warm_transcription),
        },
        "first_request_vs_warm_median_pipeline_ratio": _rounded(
            first_pipeline / statistics.median(warm_pipeline)
        ),
        "repeatability": {
            "candidate_json": _repeatability(candidate_hashes),
            "candidate_midi": _repeatability(midi_hashes),
            "note_count": _repeatability(
                [str(row["note_count"]) for row in requests]
            ),
        },
        "memory": {
            "scope": _SESSION_MEMORY_SCOPE,
            "startup_high_water_bytes": startup_rss,
            "request_high_water_bytes": rss_values,
            "session_final_high_water_bytes": final_rss,
            "interpretation": (
                "Cumulative process high-water evidence, not per-request allocation "
                "or a standalone leak measurement."
            ),
        },
        "fresh_control": None,
        "promotion_allowed": False,
        "automatic_selection": False,
        "raw_candidates_mutated": False,
        "midi_notes_mutated": 0,
        "interpretation": (
            "Diagnostic execution and exact-output evidence only. Request one has "
            "a resident model but no prior transcription; only requests two and "
            "later are reused-model warm requests. This report cannot promote a "
            "musical candidate."
        ),
    }

    if fresh_run_dirs:
        if len(fresh_run_dirs) < 2:
            raise ValueError("AI session fresh control needs at least two runs")
        fresh = build_ai_performance_benchmark(fresh_run_dirs)
        _validate_fresh_contract(report, fresh)
        fresh_pipeline = float(fresh["aggregates"]["pipeline_elapsed_seconds"]["median"])
        fresh_worker = float(
            fresh["aggregates"]["worker_subprocess_elapsed_seconds"]["median"]
        )
        fresh_transcription = float(
            fresh["aggregates"]["performance_transcription_seconds"]["median"]
        )
        report["fresh_control"] = {
            "status": "verified",
            "repetition_count": fresh["repetition_count"],
            "candidate_json_sha256": fresh["repetitions"][0][
                "candidate_json_sha256"
            ],
            "candidate_midi_sha256": fresh["repetitions"][0][
                "candidate_midi_sha256"
            ],
            "median_pipeline_elapsed_seconds": _rounded(fresh_pipeline),
            "median_worker_subprocess_elapsed_seconds": _rounded(fresh_worker),
            "median_transcription_seconds": _rounded(fresh_transcription),
            "warm_to_fresh_pipeline_ratio": _rounded(
                statistics.median(warm_pipeline) / fresh_pipeline
            ),
            "warm_to_fresh_transcription_ratio": _rounded(
                statistics.median(warm_transcription) / fresh_transcription
            ),
            "same_candidate_json": (
                len(set(candidate_hashes)) == 1
                and candidate_hashes[0]
                == fresh["repetitions"][0]["candidate_json_sha256"]
            ),
            "same_candidate_midi": (
                len(set(midi_hashes)) == 1
                and midi_hashes[0]
                == fresh["repetitions"][0]["candidate_midi_sha256"]
            ),
        }
    return report


def _verified_session_artifact(
    root: Path, session: Mapping[str, Any], name: str
) -> dict[str, Any]:
    artifacts = session.get("artifacts")
    record = artifacts.get(name) if isinstance(artifacts, Mapping) else None
    path = root / name
    if not isinstance(record, Mapping) or not path.is_file():
        raise ValueError(f"AI session does not pin {name}")
    if (
        record.get("path") != name
        or record.get("bytes") != path.stat().st_size
        or record.get("sha256") != _sha256(path)
    ):
        raise ValueError(f"AI session artifact changed: {name}")
    return _read_json(path, name)


def _verify_session_file(
    root: Path, session: Mapping[str, Any], name: str
) -> Path:
    artifacts = session.get("artifacts")
    record = artifacts.get(name) if isinstance(artifacts, Mapping) else None
    path = root / name
    if (
        not isinstance(record, Mapping)
        or not path.is_file()
        or record.get("path") != name
        or record.get("bytes") != path.stat().st_size
        or record.get("sha256") != _sha256(path)
    ):
        raise ValueError(f"AI session artifact changed: {name}")
    return path


def _validate_started_record(
    started: Mapping[str, Any],
    *,
    session: Mapping[str, Any],
    session_id: str,
    run_count: int,
    template: Mapping[str, Any],
) -> None:
    cache = started.get("cache_regime")
    if (
        started.get("schema") != MUSCRIPTOR_SESSION_SCHEMA
        or started.get("session_id") != session_id
        or started.get("status") != "starting"
        or started.get("started_at") != session.get("started_at")
        or started.get("repetitions") != run_count
        or started.get("source") != session.get("source")
        or started.get("checkpoint") != session.get("checkpoint")
        or started.get("worker") != session.get("worker")
        or started.get("request_template") != template
        or started.get("execution") != session.get("execution")
        or started.get("bpm") != session.get("bpm")
        or not isinstance(started.get("python"), str)
        or not started.get("python")
        or not isinstance(cache, Mapping)
        or cache.get("worker_process") != "bounded-shared-session"
        or cache.get("model_loaded_once") is not None
        or cache.get("application_content_cache") is not False
        or cache.get("cache_hits") != 0
        or cache.get("operating_system_file_cache") != "uncontrolled"
        or cache.get("cold_start_claimed") is not False
    ):
        raise ValueError("AI session start record is invalid")


def _validate_candidate_midi(
    candidate_document: Mapping[str, Any], *, bpm: float, midi_path: Path
) -> None:
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("AI session candidate MIDI has invalid BPM evidence")
    candidate = AITranscriptionCandidate.from_dict(candidate_document)
    with tempfile.TemporaryDirectory(prefix="sunofriend-session-midi-") as directory:
        regenerated = Path(directory) / "candidate.mid"
        write_midi_file(regenerated, _candidate_tracks(candidate), bpm=bpm)
        if regenerated.read_bytes() != midi_path.read_bytes():
            raise ValueError("AI session candidate MIDI differs from candidate.json")


def _validate_parent_timings(
    session: Mapping[str, Any],
    *,
    request_count: int,
    pipeline_seconds: float,
    worker_startup_seconds: float,
    worker_session_seconds: float,
) -> dict[str, Any]:
    values = session.get("parent_timings_seconds")
    expected = {
        "prepare_and_publish",
        "worker_startup_to_ready",
        "request_phase",
        "worker_shutdown_and_final_integrity",
        "session_total",
    }
    if not isinstance(values, Mapping) or set(values) != expected:
        raise ValueError("AI session parent timing evidence is invalid")
    normalised = {name: _positive(values.get(name), name) for name in expected}
    stage_total = sum(
        normalised[name] for name in expected if name != "session_total"
    )
    if stage_total > normalised["session_total"] + _TOLERANCE_SECONDS:
        raise ValueError("AI session parent timing stages exceed total")
    if abs(stage_total - normalised["session_total"]) > _TOLERANCE_SECONDS:
        raise ValueError("AI session parent timing stages do not account for total")
    if (
        session.get("parent_clock") != "time.monotonic"
        or normalised["request_phase"] + 1e-9 < pipeline_seconds
        or normalised["worker_startup_to_ready"] + _TOLERANCE_SECONDS
        < worker_startup_seconds
        or normalised["session_total"] + _TOLERANCE_SECONDS
        < worker_session_seconds
    ):
        raise ValueError("AI session parent timings contradict worker or run timings")
    total = normalised["session_total"]
    return {
        "prepare_and_publish_seconds": _rounded(
            normalised["prepare_and_publish"]
        ),
        "worker_startup_to_ready_seconds": _rounded(
            normalised["worker_startup_to_ready"]
        ),
        "request_phase_seconds": _rounded(normalised["request_phase"]),
        "worker_shutdown_and_final_integrity_seconds": _rounded(
            normalised["worker_shutdown_and_final_integrity"]
        ),
        "session_total_seconds": _rounded(total),
        "amortized_session_total_seconds_per_request": _rounded(
            total / request_count
        ),
    }


def _validate_response(
    response: Mapping[str, Any],
    *,
    session_id: str,
    instance_id: str,
    sequence: int,
    run_id: str,
    source_sha256: str,
    expected_note_count: int,
    request_path: Path,
    candidate_path: Path,
    performance_path: Path,
) -> None:
    expected_warm = sequence > 1
    if (
        response.get("schema") != MUSCRIPTOR_SESSION_RESPONSE_SCHEMA
        or response.get("kind") != "result"
        or response.get("status") != "complete"
        or response.get("session_id") != session_id
        or response.get("worker_instance_id") != instance_id
        or response.get("sequence") != sequence
        or response.get("run_id") != run_id
        or response.get("request_sha256") != _sha256(request_path)
        or response.get("source_sha256") != source_sha256
        or response.get("candidate_sha256") != _sha256(candidate_path)
        or response.get("performance_sha256") != _sha256(performance_path)
        or response.get("note_count") != expected_note_count
        or response.get("prior_completed_requests") != sequence - 1
        or response.get("warm_model_request") is not expected_warm
        or response.get("model_reused_from_prior_request") is not expected_warm
        or response.get("model_load_count") != 1
    ):
        raise ValueError(f"AI session response {sequence} is invalid")


def _validate_request_performance(
    performance: Mapping[str, Any],
    *,
    session_id: str,
    instance_id: str,
    sequence: int,
    expected_warm: bool,
    expected_device: str,
    expected_note_count: int,
    expected_chunk_seconds: float,
    actual_duration_seconds: float,
) -> dict[str, Any]:
    if (
        performance.get("schema") != MUSCRIPTOR_SESSION_REQUEST_PERFORMANCE_SCHEMA
        or performance.get("measurement_mode") != "persistent-session-request"
        or performance.get("device") != expected_device
        or performance.get("clock") != _CLOCK
        or performance.get("memory_scope") != _SESSION_MEMORY_SCOPE
        or performance.get("note_count") != expected_note_count
    ):
        raise ValueError(f"AI session performance {sequence} identity is invalid")
    session = performance.get("session")
    if not isinstance(session, Mapping) or set(session) != _SESSION_REQUEST_FIELDS or (
        session.get("session_id") != session_id
        or session.get("worker_instance_id") != instance_id
        or session.get("sequence") != sequence
        or session.get("prior_completed_requests") != sequence - 1
        or session.get("warm_model_request") is not expected_warm
        or session.get("model_reused_from_prior_request") is not expected_warm
        or session.get("model_load_count") != 1
    ):
        raise ValueError(f"AI session performance {sequence} reuse evidence is invalid")
    request_started_at = _timestamp(
        session.get("request_started_at"),
        f"AI session performance {sequence} request_started_at",
    )
    timings = performance.get("timings_seconds")
    if not isinstance(timings, Mapping) or set(timings) != set(_REQUEST_TIMING_FIELDS):
        raise ValueError(f"AI session performance {sequence} timings are invalid")
    normalised: dict[str, float | None] = {}
    for name in _REQUEST_TIMING_FIELDS:
        value = timings[name]
        normalised[name] = None if value is None else _nonnegative(value, name)
    for name in ("audio_preparation", "transcription", "request_total"):
        if normalised[name] is None:
            raise ValueError(f"AI session performance {sequence} is missing {name}")
    request_total = float(normalised["request_total"])
    if request_total <= 0:
        raise ValueError("AI session request_total must be positive")
    stage_total = float(normalised["audio_preparation"]) + float(
        normalised["transcription"]
    )
    if stage_total > request_total + _TOLERANCE_SECONDS:
        raise ValueError("AI session performance stages exceed request_total")
    for name in _REQUEST_TIMING_FIELDS[3:]:
        if normalised[name] is not None and float(normalised[name]) > (
            request_total + _TOLERANCE_SECONDS
        ):
            raise ValueError("AI session first-event timing exceeds request_total")
    first_start = normalised["time_to_first_note_start"]
    first_note = normalised["time_to_first_completed_note"]
    if expected_note_count:
        if first_start is None or first_note is None:
            raise ValueError("AI session note timings are missing")
        if float(first_start) > float(first_note) + _TOLERANCE_SECONDS:
            raise ValueError("AI session first-note timings are not ordered")
    elif first_start is not None or first_note is not None:
        raise ValueError("AI session first-note timings require notes")
    if normalised["time_to_first_completed_chunk"] is None:
        raise ValueError("AI session first-chunk timing is missing")
    chunks = performance.get("chunks")
    if not isinstance(chunks, Mapping) or set(chunks) != {
        "seconds",
        "planned",
        "reported",
    }:
        raise ValueError("AI session chunk evidence is invalid")
    seconds = _positive(chunks.get("seconds"), "session chunk seconds")
    planned = _positive_integer(chunks.get("planned"), "session planned chunks")
    reported = _positive_integer(chunks.get("reported"), "session reported chunks")
    expected_planned = math.ceil(actual_duration_seconds / expected_chunk_seconds)
    if not math.isclose(seconds, expected_chunk_seconds, abs_tol=1e-6):
        raise ValueError("AI session chunk seconds disagree with execution")
    if planned != expected_planned or reported != planned:
        raise ValueError("AI session did not report every planned chunk")
    peak = _positive_integer(performance.get("peak_process_rss_bytes"), "request RSS")
    return {
        "schema": MUSCRIPTOR_SESSION_REQUEST_PERFORMANCE_SCHEMA,
        "measurement_mode": "persistent-session-request",
        "session": {
            "session_id": session_id,
            "worker_instance_id": instance_id,
            "sequence": sequence,
            "prior_completed_requests": sequence - 1,
            "warm_model_request": expected_warm,
            "model_reused_from_prior_request": expected_warm,
            "model_load_count": 1,
            "request_started_at": request_started_at.isoformat().replace(
                "+00:00", "Z"
            ),
        },
        "device": expected_device,
        "timings_seconds": {
            name: None if value is None else _rounded(value)
            for name, value in normalised.items()
        },
        "chunks": {
            "seconds": _rounded(seconds),
            "planned": planned,
            "reported": reported,
        },
        "note_count": expected_note_count,
        "peak_process_rss_bytes": peak,
        "memory_scope": _SESSION_MEMORY_SCOPE,
        "clock": _CLOCK,
    }


def _validate_fresh_contract(
    session: Mapping[str, Any], fresh: Mapping[str, Any]
) -> None:
    fields = (
        "backend",
        "checkpoint_sha256",
        "model_config_sha256",
        "model_version",
        "worker_sha256",
        "execution",
        "runtime_profile",
        "source_sha256",
        "excerpt",
        "bpm",
        "roles",
        "device",
    )
    mismatch = [name for name in fields if session.get(name) != fresh.get(name)]
    if mismatch:
        raise ValueError(
            "AI session fresh control differs in: " + ", ".join(mismatch)
        )
    repetitions = fresh.get("repetitions")
    repeatability = fresh.get("repeatability")
    cache = fresh.get("cache_regime")
    if (
        not isinstance(repetitions, list)
        or len(repetitions) < 2
        or any(row.get("performance_status") != "verified" for row in repetitions)
        or not isinstance(repeatability, Mapping)
        or any(
            not isinstance(repeatability.get(name), Mapping)
            or repeatability[name].get("all_identical") is not True
            for name in ("candidate_json", "candidate_midi", "note_count")
        )
        or not isinstance(cache, Mapping)
        or cache.get("worker_process") != "fresh-per-repetition"
        or cache.get("model_reused") is not False
        or cache.get("application_content_cache") is not False
    ):
        raise ValueError("AI session fresh controls are not verified repeatable fresh runs")
    fresh_candidate = fresh["repetitions"][0]["candidate_json_sha256"]
    fresh_midi = fresh["repetitions"][0]["candidate_midi_sha256"]
    if any(row["candidate_json_sha256"] != fresh_candidate for row in session["requests"]):
        raise ValueError("AI session candidate JSON differs from the fresh control")
    if any(row["candidate_midi_sha256"] != fresh_midi for row in session["requests"]):
        raise ValueError("AI session MIDI differs from the fresh control")


def _runtime_profile(value: Any, *, lane: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"AI session {lane} has no runtime profile")
    torch = value.get("torch")
    backends = value.get("backends")
    muscriptor = backends.get("muscriptor") if isinstance(backends, Mapping) else None
    if not isinstance(torch, Mapping) or not isinstance(muscriptor, Mapping):
        raise ValueError(f"AI session {lane} runtime profile is invalid")
    return {
        "platform_architecture": _nonempty(value.get("platform"), "platform"),
        "python_version": _nonempty(value.get("python"), "Python version"),
        "torch_version": _nonempty(torch.get("version"), "torch version"),
        "muscriptor_version": _nonempty(
            muscriptor.get("version"), "MuScriptor version"
        ),
    }


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _repeatability(values: Sequence[str]) -> dict[str, Any]:
    return {"all_identical": len(set(values)) == 1, "unique_count": len(set(values))}


def _summary(values: Sequence[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": _rounded(min(values)),
        "median": _rounded(statistics.median(values)),
        "max": _rounded(max(values)),
    }


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return number


def _positive(value: Any, label: str) -> float:
    number = _nonnegative(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _rounded(value: int | float) -> int | float:
    if isinstance(value, int):
        return value
    return round(float(value), 6)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid AI session benchmark {label}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"AI session benchmark {label} must be an object")
    return document


__all__ = [
    "AI_SESSION_BENCHMARK_SCHEMA",
    "build_ai_session_benchmark",
    "write_ai_session_benchmark",
]
