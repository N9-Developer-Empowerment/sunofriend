"""Path-free performance reports over repeated immutable MuScriptor runs.

The benchmark deliberately consumes completed runs instead of invoking a model.
That keeps the evidence immutable and lets the existing candidate-matrix verifier
bind every report row to its checkpoint, configuration, worker, request and
candidate artifacts before any timing is compared.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import soundfile

from .ai_matrix import build_ai_candidate_matrix


AI_PERFORMANCE_BENCHMARK_SCHEMA = "sunofriend.ai-performance-benchmark.v1"
MUSCRIPTOR_PERFORMANCE_SCHEMA = "sunofriend.muscriptor-performance.v1"

_TIMING_FIELDS = (
    "audio_preparation",
    "model_load",
    "transcription",
    "worker_total",
    "time_to_first_note_start",
    "time_to_first_completed_note",
    "time_to_first_completed_chunk",
)
_CORE_STAGE_TIMINGS = ("audio_preparation", "model_load", "transcription")
_MEMORY_SCOPE = "process RSS high-water; accelerator allocation excluded"
_CLOCK = "time.perf_counter"
_TIMING_TOLERANCE_SECONDS = 0.05
_DURATION_TOLERANCE_SECONDS = 1e-9
_EXPLICIT_EXECUTION_FIELDS = frozenset(
    {
        "worker_execution_mode",
        "worker_process_started_for_run",
        "inference_executed_for_run",
        "model_loaded_for_run",
        "application_cache",
    }
)
_CACHE_EVIDENCE_ARTIFACTS = frozenset(
    {"cache.entry.json", "cache.performance.json"}
)


def write_ai_performance_benchmark(
    run_dirs: Sequence[str | Path], output_path: str | Path
) -> dict[str, Any]:
    """Build and atomically publish a report at a fresh output path."""

    output = Path(output_path).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"AI performance benchmark already exists: {output}")
    report = build_ai_performance_benchmark(run_dirs)
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
            # A hard link publishes a complete file without replacing a path
            # that another process may have created after the initial check.
            os.link(temporary, output)
        except FileExistsError as exc:
            raise FileExistsError(
                f"AI performance benchmark already exists: {output}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return report


def build_ai_performance_benchmark(
    run_dirs: Sequence[str | Path],
) -> dict[str, Any]:
    """Compare at least two comparable, completed MuScriptor repetitions."""

    if isinstance(run_dirs, (str, bytes, Path)):
        raise ValueError("AI performance benchmark needs at least two run directories")
    paths = [Path(value).expanduser().absolute() for value in run_dirs]
    if len(paths) < 2:
        raise ValueError("AI performance benchmark needs at least two run directories")
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("AI performance benchmark run directories must be unique")

    preliminaries: list[tuple[datetime, datetime, str, str, str, Path]] = []
    for path in resolved:
        document = _read_json(path / "run.json", "run manifest")
        _fresh_execution_evidence(document, label="run manifest")
        run_id = document.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("AI performance benchmark run has no stable run_id")
        started, normalised_started = _validated_started_at(
            document.get("started_at"), run_id=run_id
        )
        completed, normalised_completed = _validated_completed_at(
            document.get("completed_at"), run_id=run_id
        )
        if completed < started:
            raise ValueError(
                f"AI performance benchmark run {run_id} completed_at precedes "
                "started_at"
            )
        preliminaries.append(
            (
                started,
                completed,
                run_id,
                normalised_started,
                normalised_completed,
                path,
            )
        )
    run_ids = [run_id for _start, _end, run_id, _ns, _ne, _path in preliminaries]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("AI performance benchmark run_id values must be unique")
    preliminaries.sort(key=lambda item: (item[0], item[2]))
    for previous, current in zip(preliminaries, preliminaries[1:]):
        if current[0] < previous[1]:
            raise ValueError(
                "AI performance benchmark repetitions overlap: "
                f"run {current[2]} started before run {previous[2]} completed"
            )

    lanes = [
        (f"M3-benchmark-{index:03d}", path)
        for index, (_started, _completed, _run_id, _ns, _ne, path) in enumerate(
            preliminaries, start=1
        )
    ]
    matrix = build_ai_candidate_matrix(lanes)
    if matrix.get("backend") != "muscriptor":
        raise ValueError("AI performance benchmark requires MuScriptor runs")
    matrix_rows = {str(row["lane"]): row for row in matrix["lanes"]}

    loaded: list[dict[str, Any]] = []
    for lane, (
        _started,
        _completed,
        run_id,
        started_at,
        completed_at,
        run_dir,
    ) in zip(lanes, preliminaries):
        lane_name = lane[0]
        loaded.append(
            _load_repetition(
                lane_name,
                run_id,
                started_at,
                completed_at,
                run_dir,
                matrix_rows[lane_name],
            )
        )
    comparison = _comparison_contract(loaded)

    repetitions = []
    aggregate_values: dict[str, list[int | float]] = {}
    for index, item in enumerate(loaded, start=1):
        row = item["matrix_row"]
        pipeline_elapsed = _positive_number(
            item["run"].get("elapsed_seconds"),
            f"repetition {index} pipeline elapsed_seconds",
        )
        duration = float(item["actual_duration_seconds"])
        pipeline_rtf = pipeline_elapsed / duration
        worker_elapsed = _optional_nonnegative_number(
            item["run"].get("worker_subprocess_elapsed_seconds"),
            f"repetition {index} worker_subprocess_elapsed_seconds",
        )
        if (
            worker_elapsed is not None
            and worker_elapsed > pipeline_elapsed + _TIMING_TOLERANCE_SECONDS
        ):
            raise ValueError(
                f"AI performance benchmark repetition {index} parent-observed "
                "worker subprocess elapsed time exceeds pipeline elapsed time"
            )
        worker_rtf = worker_elapsed / duration if worker_elapsed is not None else None
        performance = item["performance"]
        transcription_elapsed = (
            performance["timings_seconds"]["transcription"]
            if performance is not None
            else None
        )
        transcription_rtf = (
            float(transcription_elapsed) / duration
            if transcription_elapsed is not None
            else None
        )
        chunk_seconds = float(row["five_second_boundaries"]["chunk_seconds"])
        planned_chunks = max(1, math.ceil(duration / chunk_seconds))
        reported_chunks = None
        if performance is not None:
            chunk_seconds = float(performance["chunks"]["seconds"])
            planned_chunks = int(performance["chunks"]["planned"])
            reported_chunks = int(performance["chunks"]["reported"])

        repetition: dict[str, Any] = {
            "repetition": index,
            "run_id": item["run_id"],
            "execution_evidence": item["execution_evidence"],
            "started_at": item["started_at"],
            "completed_at": item["completed_at"],
            "actual_duration_seconds": _rounded(duration),
            "pipeline_elapsed_seconds": _rounded(pipeline_elapsed),
            "pipeline_real_time_factor": _rounded(pipeline_rtf),
            "worker_subprocess_elapsed_seconds": (
                _rounded(worker_elapsed) if worker_elapsed is not None else None
            ),
            "worker_subprocess_real_time_factor": (
                _rounded(worker_rtf) if worker_rtf is not None else None
            ),
            "transcription_real_time_factor": (
                _rounded(transcription_rtf)
                if transcription_rtf is not None
                else None
            ),
            "performance_status": (
                "verified" if performance is not None else "unavailable"
            ),
            "performance": performance,
            "note_count": int(row["note_count"]),
            "chunks": {
                "seconds": _rounded(chunk_seconds),
                "planned": planned_chunks,
                "reported": reported_chunks,
            },
            "five_second_boundaries": row["five_second_boundaries"],
            "candidate_json_sha256": row["candidate_json_sha256"],
            "candidate_midi_sha256": row["candidate_midi_sha256"],
        }
        repetitions.append(repetition)

        _collect(aggregate_values, "pipeline_elapsed_seconds", pipeline_elapsed)
        _collect(aggregate_values, "pipeline_real_time_factor", pipeline_rtf)
        _collect(
            aggregate_values,
            "worker_subprocess_elapsed_seconds",
            worker_elapsed,
        )
        _collect(
            aggregate_values,
            "worker_subprocess_real_time_factor",
            worker_rtf,
        )
        _collect(
            aggregate_values,
            "transcription_real_time_factor",
            transcription_rtf,
        )
        _collect(aggregate_values, "note_count", int(row["note_count"]))
        _collect(aggregate_values, "chunks_seconds", chunk_seconds)
        _collect(aggregate_values, "chunks_planned", planned_chunks)
        _collect(aggregate_values, "chunks_reported", reported_chunks)
        if performance is not None:
            for name, value in performance["timings_seconds"].items():
                _collect(aggregate_values, f"performance_{name}_seconds", value)
            _collect(
                aggregate_values,
                "performance_peak_process_rss_bytes",
                performance.get("peak_process_rss_bytes"),
            )

    elapsed_values = [float(row["pipeline_elapsed_seconds"]) for row in repetitions]
    later_median = statistics.median(elapsed_values[1:])
    first_vs_later = elapsed_values[0] / later_median if later_median > 0 else None

    candidate_hashes = [row["candidate_json_sha256"] for row in repetitions]
    midi_hashes = [row["candidate_midi_sha256"] for row in repetitions]
    note_counts = [row["note_count"] for row in repetitions]
    report = {
        "schema": AI_PERFORMANCE_BENCHMARK_SCHEMA,
        "backend": matrix["backend"],
        "checkpoint_sha256": matrix["checkpoint_sha256"],
        "model_config_sha256": matrix["model_config_sha256"],
        "model_version": matrix["model_version"],
        "worker_sha256": matrix["worker_sha256"],
        "execution": matrix["execution"],
        "runtime_profile": comparison["runtime_profile"],
        "source_sha256": comparison["source_sha256"],
        "excerpt": comparison["excerpt"],
        "bpm": comparison["bpm"],
        "roles": comparison["roles"],
        "device": comparison["device"],
        "repetition_count": len(repetitions),
        "cache_regime": {
            "worker_process": "fresh-per-repetition",
            "model_reused": False,
            "application_content_cache": False,
            "operating_system_file_cache": "uncontrolled",
            "cold_start_claimed": False,
        },
        "execution_evidence": {
            "explicit_current_count": sum(
                item["execution_evidence"] == "explicit-current-fields"
                for item in loaded
            ),
            "legacy_v1_count": sum(
                item["execution_evidence"] == "legacy-v1-fresh-subprocess"
                for item in loaded
            ),
            "legacy_policy": (
                "A legacy v1 run is accepted only with a successful non-empty "
                "subprocess command and no session or application-cache evidence."
            ),
        },
        "timing_definitions": {
            "pipeline_elapsed_seconds": (
                "Parent-process timer from request publication through the worker "
                "and local post-processing; the final runtime snapshot and manifest "
                "write follow this measurement."
            ),
            "pipeline_real_time_factor": (
                "pipeline_elapsed_seconds divided by actual processed excerpt duration."
            ),
            "worker_subprocess_elapsed_seconds": (
                "Parent-observed subprocess wall time, including worker start and exit."
            ),
            "worker_subprocess_real_time_factor": (
                "worker_subprocess_elapsed_seconds divided by actual processed "
                "excerpt duration."
            ),
            "transcription_real_time_factor": (
                "Worker-measured inclusive transcription seconds divided by actual "
                "processed excerpt duration. The timer covers iteration of "
                "MuScriptor's lazy model.transcribe result, including backend "
                "preprocessing, condition construction and decoding."
            ),
            "performance_timings_seconds": (
                "Worker time.perf_counter measurements from the verified "
                "muscriptor.performance.json artifact; worker_total ends when the "
                "candidate and performance data are ready, before their final JSON "
                "writes and process exit."
            ),
            "first_vs_later_median_wall_ratio": (
                "First repetition pipeline wall time divided by the median of later "
                "repetitions ordered by timezone-aware started_at, then run_id."
            ),
        },
        "repetitions": repetitions,
        "repeatability": {
            "candidate_json": _repeatability(candidate_hashes),
            "candidate_midi": _repeatability(midi_hashes),
            "note_count": {
                "all_identical": len(set(note_counts)) == 1,
                "unique_count": len(set(note_counts)),
            },
        },
        "first_vs_later_median_wall_ratio": (
            _rounded(first_vs_later) if first_vs_later is not None else None
        ),
        "aggregates": {
            name: _summary(values) for name, values in sorted(aggregate_values.items())
        },
        "promotion_allowed": False,
        "raw_candidates_mutated": False,
        "midi_notes_mutated": 0,
        "interpretation": (
            "Diagnostic timing and repeatability evidence only. This report cannot "
            "promote a musical candidate; listening review remains required."
        ),
    }
    return report


def _fresh_execution_evidence(run: Mapping[str, Any], *, label: str) -> str:
    """Validate current fields or the tightly bounded pre-field v1 contract."""

    rejection = (
        "AI performance benchmark accepts only cache-disabled fresh-process runs; "
        "use ai-session-benchmark for persistent sessions or ai-cache-benchmark "
        "for application-cache runs"
    )
    if run.get("worker_transport") is not None:
        raise ValueError(rejection)

    artifacts = run.get("artifacts")
    if isinstance(artifacts, Mapping) and _CACHE_EVIDENCE_ARTIFACTS.intersection(
        artifacts
    ):
        raise ValueError(rejection)

    present = {field for field in _EXPLICIT_EXECUTION_FIELDS if field in run}
    if present:
        if present != _EXPLICIT_EXECUTION_FIELDS:
            raise ValueError(
                f"AI performance benchmark {label} has incomplete execution fields"
            )
        if (
            run.get("worker_execution_mode") != "fresh-subprocess"
            or run.get("worker_process_started_for_run") is not True
            or run.get("inference_executed_for_run") is not True
            or run.get("model_loaded_for_run") is not True
            or run.get("model_reused_from_prior_request") is not False
            or run.get("application_cache") is not None
        ):
            raise ValueError(rejection)
        evidence = "explicit-current-fields"
    else:
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"AI performance benchmark {label} has no artifacts")
        evidence = "legacy-v1-fresh-subprocess"

    command = run.get("command")
    exit_code = run.get("exit_code")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
        or isinstance(exit_code, bool)
        or exit_code != 0
    ):
        raise ValueError(rejection)
    return evidence


def _load_repetition(
    lane: str,
    run_id: str,
    started_at: str,
    completed_at: str,
    run_dir: Path,
    matrix_row: Mapping[str, Any],
) -> dict[str, Any]:
    run = _read_json(run_dir / "run.json", f"{lane} run manifest")
    execution_evidence = _fresh_execution_evidence(run, label=f"{lane} run")
    manifest_run_id = run.get("run_id")
    if manifest_run_id != run_id:
        raise ValueError(f"AI performance benchmark {lane} run_id changed")
    _manifest_started, manifest_started_at = _validated_started_at(
        run.get("started_at"), run_id=run_id
    )
    if manifest_started_at != started_at:
        raise ValueError(f"AI performance benchmark {lane} started_at changed")
    _manifest_completed, manifest_completed_at = _validated_completed_at(
        run.get("completed_at"), run_id=run_id
    )
    if manifest_completed_at != completed_at:
        raise ValueError(f"AI performance benchmark {lane} completed_at changed")
    request = _read_json(run_dir / "request.json", f"{lane} request")
    candidate = _read_json(run_dir / "candidate.json", f"{lane} candidate")
    options = request.get("options")
    metadata = candidate.get("metadata")
    if not isinstance(options, Mapping) or not isinstance(metadata, Mapping):
        raise ValueError(f"AI performance benchmark {lane} has no device evidence")
    runtime_profile = _runtime_profile(run.get("runtime"), lane=lane)
    source = run.get("source")
    if not isinstance(source, Mapping):
        raise ValueError(f"AI performance benchmark {lane} has no source evidence")
    source_path_text = source.get("path")
    if not isinstance(source_path_text, str) or not source_path_text.strip():
        raise ValueError(f"AI performance benchmark {lane} source path is invalid")
    # The candidate matrix has already verified this record's bytes and hash.
    # The path is used only to check frame geometry and is never published.
    source_path = Path(source_path_text).expanduser().resolve()
    actual_duration = _candidate_actual_duration(
        candidate,
        request,
        source_path=source_path,
        lane=lane,
    )
    requested_device = options.get("device")
    candidate_device = metadata.get("device")
    if isinstance(candidate_device, str) and candidate_device.strip():
        device = candidate_device.strip()
    elif requested_device in {"cpu", "mps"}:
        device = str(requested_device)
    else:
        raise ValueError(f"AI performance benchmark {lane} has no effective device")
    if requested_device not in {None, "auto", device}:
        raise ValueError(
            f"AI performance benchmark {lane} request and candidate device disagree"
        )

    raw_artifacts = candidate.get("raw_artifacts")
    if not isinstance(raw_artifacts, list) or not all(
        isinstance(value, str) for value in raw_artifacts
    ):
        raise ValueError(f"AI performance benchmark {lane} raw artifacts are invalid")
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError(f"AI performance benchmark {lane} has no artifact manifest")
    performance_record = artifacts.get("muscriptor.performance.json")
    performance_declared = "muscriptor.performance.json" in raw_artifacts
    if performance_declared != isinstance(performance_record, Mapping):
        raise ValueError(
            f"AI performance benchmark {lane} performance artifact is not pinned"
        )

    performance = None
    if isinstance(performance_record, Mapping):
        record_path = Path(str(performance_record.get("path", "")))
        if not record_path.is_absolute():
            record_path = run_dir / record_path
        performance_path = record_path.resolve()
        expected = (run_dir / "muscriptor.performance.json").resolve()
        if performance_path != expected:
            raise ValueError(
                f"AI performance benchmark {lane} performance artifact path disagrees"
            )
        execution = matrix_row.get("execution")
        chunking = execution.get("chunking") if isinstance(execution, Mapping) else None
        if not isinstance(chunking, Mapping):
            raise ValueError(
                f"AI performance benchmark {lane} has no chunk execution setting"
            )
        expected_chunk_seconds = _positive_number(
            chunking.get("seconds"), f"{lane} execution chunking.seconds"
        )
        parent_worker_elapsed = _positive_number(
            run.get("worker_subprocess_elapsed_seconds"),
            f"{lane} worker_subprocess_elapsed_seconds",
        )
        performance = _validated_performance(
            _read_json(performance_path, f"{lane} performance"),
            lane=lane,
            expected_device=device,
            expected_note_count=int(matrix_row["note_count"]),
            expected_chunk_seconds=expected_chunk_seconds,
            actual_duration_seconds=actual_duration,
            parent_worker_elapsed_seconds=parent_worker_elapsed,
        )

    return {
        "lane": lane,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "execution_evidence": execution_evidence,
        "run": run,
        "request": request,
        "candidate": candidate,
        "device": device,
        "runtime_profile": runtime_profile,
        "actual_duration_seconds": actual_duration,
        "performance": performance,
        "matrix_row": matrix_row,
    }


def _comparison_contract(loaded: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sources = {str(item["matrix_row"]["source_sha256"]) for item in loaded}
    if len(sources) != 1 or not next(iter(sources)):
        raise ValueError("AI performance benchmark runs must use the same source hash")

    excerpts = set()
    roles = set()
    devices = set()
    bpms = set()
    actual_durations = set()
    runtime_profiles = set()
    for item in loaded:
        request = item["request"]
        start = _nonnegative_number(
            request.get("start_seconds"), "benchmark excerpt start_seconds"
        )
        end_value = request.get("end_seconds")
        end = (
            _positive_number(end_value, "benchmark excerpt end_seconds")
            if end_value is not None
            else None
        )
        excerpts.add((start, end))
        request_roles = request.get("roles")
        if not isinstance(request_roles, list) or not all(
            isinstance(role, str) for role in request_roles
        ):
            raise ValueError("AI performance benchmark run has invalid roles")
        roles.add(tuple(request_roles))
        devices.add(str(item["device"]))
        bpms.add(float(item["matrix_row"]["bpm"]))
        actual_durations.add(float(item["actual_duration_seconds"]))
        runtime_profiles.add(
            json.dumps(item["runtime_profile"], sort_keys=True, separators=(",", ":"))
        )
    if len(excerpts) != 1:
        raise ValueError("AI performance benchmark runs must use the same excerpt")
    if len(roles) != 1:
        raise ValueError("AI performance benchmark runs must use the same roles")
    if len(devices) != 1:
        raise ValueError("AI performance benchmark runs must use the same device")
    if len(bpms) != 1:
        raise ValueError("AI performance benchmark runs must use the same BPM")
    if len(actual_durations) != 1:
        raise ValueError(
            "AI performance benchmark runs must use the same actual processed duration"
        )
    if len(runtime_profiles) != 1:
        raise ValueError(
            "AI performance benchmark runs must use the same runtime profile"
        )

    start, end = next(iter(excerpts))
    actual_duration = next(iter(actual_durations))
    return {
        "source_sha256": next(iter(sources)),
        "excerpt": {
            "requested_start_seconds": _rounded(start),
            "requested_end_seconds": _rounded(end) if end is not None else None,
            "actual_duration_seconds": _rounded(actual_duration),
        },
        "roles": list(next(iter(roles))),
        "device": next(iter(devices)),
        "bpm": _rounded(next(iter(bpms))),
        "runtime_profile": json.loads(next(iter(runtime_profiles))),
    }


def _runtime_profile(value: Any, *, lane: str) -> dict[str, str]:
    """Select only comparable, path-free runtime identity fields."""

    if not isinstance(value, Mapping):
        raise ValueError(f"AI performance benchmark {lane} has no runtime profile")
    if value.get("schema") != "sunofriend.ai-runtime.v1":
        raise ValueError(
            f"AI performance benchmark {lane} runtime schema is invalid"
        )
    torch = value.get("torch")
    backends = value.get("backends")
    muscriptor = backends.get("muscriptor") if isinstance(backends, Mapping) else None
    if not isinstance(torch, Mapping) or not isinstance(muscriptor, Mapping):
        raise ValueError(
            f"AI performance benchmark {lane} runtime versions are invalid"
        )
    return {
        "platform_architecture": _nonempty_string(
            value.get("platform"), f"{lane} runtime platform/architecture"
        ),
        "python_version": _nonempty_string(
            value.get("python"), f"{lane} runtime Python version"
        ),
        "torch_version": _nonempty_string(
            torch.get("version"), f"{lane} runtime torch version"
        ),
        "muscriptor_version": _nonempty_string(
            muscriptor.get("version"), f"{lane} runtime MuScriptor version"
        ),
    }


def _candidate_actual_duration(
    candidate: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    source_path: Path,
    lane: str,
) -> float:
    """Validate worker duration against the verified source's frame geometry."""

    metadata = candidate.get("metadata")
    excerpt = metadata.get("excerpt") if isinstance(metadata, Mapping) else None
    if not isinstance(excerpt, Mapping):
        raise ValueError(
            f"AI performance benchmark {lane} has no candidate excerpt evidence"
        )
    actual = _positive_number(
        excerpt.get("duration_seconds"),
        f"{lane} candidate excerpt.duration_seconds",
    )
    requested_start = _nonnegative_number(
        request.get("start_seconds"), f"{lane} request start_seconds"
    )
    candidate_start = _nonnegative_number(
        excerpt.get("start_seconds"), f"{lane} candidate excerpt.start_seconds"
    )
    if not math.isclose(
        candidate_start, requested_start, rel_tol=0.0, abs_tol=1e-6
    ):
        raise ValueError(
            f"AI performance benchmark {lane} candidate excerpt start disagrees"
        )
    requested_end_value = request.get("end_seconds")
    candidate_end_value = excerpt.get("end_seconds")
    if requested_end_value is None:
        if candidate_end_value is not None:
            raise ValueError(
                f"AI performance benchmark {lane} candidate excerpt end disagrees"
            )
    else:
        requested_end = _positive_number(
            requested_end_value, f"{lane} request end_seconds"
        )
        candidate_end = _positive_number(
            candidate_end_value, f"{lane} candidate excerpt.end_seconds"
        )
        if not math.isclose(
            candidate_end, requested_end, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError(
                f"AI performance benchmark {lane} candidate excerpt end disagrees"
            )
        requested_duration = requested_end - requested_start
        if actual > requested_duration + _DURATION_TOLERANCE_SECONDS:
            raise ValueError(
                f"AI performance benchmark {lane} actual processed duration "
                "exceeds the requested excerpt"
            )

    try:
        info = soundfile.info(str(source_path))
    except (OSError, RuntimeError) as exc:
        raise ValueError(
            f"AI performance benchmark {lane} cannot inspect the verified source "
            f"audio geometry: {exc}"
        ) from exc
    sample_rate = int(info.samplerate)
    frame_count = int(info.frames)
    if sample_rate <= 0 or frame_count <= 0:
        raise ValueError(
            f"AI performance benchmark {lane} verified source audio geometry "
            "is invalid"
        )
    start_frame = round(requested_start * sample_rate)
    end_frame = (
        frame_count
        if requested_end_value is None
        else min(frame_count, round(float(requested_end_value) * sample_rate))
    )
    if start_frame >= frame_count or end_frame <= start_frame:
        raise ValueError(
            f"AI performance benchmark {lane} requested excerpt does not overlap "
            "the verified source audio"
        )
    expected_actual = (end_frame - start_frame) / sample_rate
    if not math.isclose(
        actual,
        expected_actual,
        rel_tol=0.0,
        abs_tol=_DURATION_TOLERANCE_SECONDS,
    ):
        raise ValueError(
            f"AI performance benchmark {lane} candidate actual processed duration "
            "does not match verified source audio frame geometry"
        )
    return actual


def _validated_performance(
    document: Mapping[str, Any],
    *,
    lane: str,
    expected_device: str,
    expected_note_count: int,
    expected_chunk_seconds: float,
    actual_duration_seconds: float,
    parent_worker_elapsed_seconds: float,
) -> dict[str, Any]:
    if document.get("schema") != MUSCRIPTOR_PERFORMANCE_SCHEMA:
        raise ValueError(f"AI performance benchmark {lane} has an invalid schema")
    if document.get("measurement_mode") != "fresh-process":
        raise ValueError(
            f"AI performance benchmark {lane} is not a fresh-process measurement"
        )
    if document.get("device") != expected_device:
        raise ValueError(
            f"AI performance benchmark {lane} performance device disagrees"
        )
    timings = document.get("timings_seconds")
    if not isinstance(timings, Mapping):
        raise ValueError(f"AI performance benchmark {lane} timings are invalid")
    unknown = set(timings) - set(_TIMING_FIELDS)
    if unknown:
        raise ValueError(
            f"AI performance benchmark {lane} has unknown timing fields"
        )
    normalised_timings: dict[str, int | float | None] = {}
    numeric_timings: dict[str, float | None] = {}
    for name in _TIMING_FIELDS:
        if name not in timings or timings[name] is None:
            normalised_timings[name] = None
            numeric_timings[name] = None
            continue
        number = _nonnegative_number(
            timings[name], f"{lane} timings_seconds.{name}"
        )
        numeric_timings[name] = number
        normalised_timings[name] = _rounded(number)
    missing_core = [
        name
        for name in (*_CORE_STAGE_TIMINGS, "worker_total")
        if numeric_timings[name] is None
    ]
    if missing_core:
        raise ValueError(
            f"AI performance benchmark {lane} is missing required timing fields: "
            + ", ".join(missing_core)
        )
    worker_total = float(numeric_timings["worker_total"])
    if worker_total <= 0:
        raise ValueError(
            f"AI performance benchmark {lane} timings_seconds.worker_total "
            "must be finite and positive"
        )

    chunks = document.get("chunks")
    if not isinstance(chunks, Mapping):
        raise ValueError(f"AI performance benchmark {lane} chunks are invalid")
    seconds = _positive_number(chunks.get("seconds"), f"{lane} chunks.seconds")
    planned = _positive_integer(chunks.get("planned"), f"{lane} chunks.planned")
    reported = _positive_integer(
        chunks.get("reported"), f"{lane} chunks.reported"
    )
    if not math.isclose(
        seconds, expected_chunk_seconds, rel_tol=0.0, abs_tol=1e-6
    ):
        raise ValueError(
            f"AI performance benchmark {lane} chunk seconds disagree with execution"
        )
    expected_planned = math.ceil(actual_duration_seconds / seconds)
    if planned != expected_planned:
        raise ValueError(
            f"AI performance benchmark {lane} planned chunks disagree with "
            "actual processed duration"
        )
    if reported > planned:
        raise ValueError(
            f"AI performance benchmark {lane} reported chunks exceed planned chunks"
        )
    if reported != planned:
        raise ValueError(
            f"AI performance benchmark {lane} completed run did not report all "
            "planned chunks"
        )
    note_count = _nonnegative_integer(
        document.get("note_count"), f"{lane} performance note_count"
    )
    if note_count != expected_note_count:
        raise ValueError(
            f"AI performance benchmark {lane} performance note count disagrees"
        )
    peak_rss = document.get("peak_process_rss_bytes")
    normalised_peak = _positive_integer(
        peak_rss, f"{lane} peak_process_rss_bytes"
    )
    memory_scope = document.get("memory_scope")
    if memory_scope != _MEMORY_SCOPE:
        raise ValueError(f"AI performance benchmark {lane} memory scope is invalid")
    clock = document.get("clock")
    if clock != _CLOCK:
        raise ValueError(f"AI performance benchmark {lane} clock is invalid")

    first_start = numeric_timings["time_to_first_note_start"]
    first_note = numeric_timings["time_to_first_completed_note"]
    if expected_note_count:
        if first_start is None or first_note is None:
            raise ValueError(
                f"AI performance benchmark {lane} note first timings are required "
                "when notes are present"
            )
        if first_start > first_note + _TIMING_TOLERANCE_SECONDS:
            raise ValueError(
                f"AI performance benchmark {lane} note first timings are not ordered"
            )
    elif first_start is not None or first_note is not None:
        raise ValueError(
            f"AI performance benchmark {lane} note first timings require notes"
        )
    first_chunk = numeric_timings["time_to_first_completed_chunk"]
    if first_chunk is None:
        raise ValueError(
            f"AI performance benchmark {lane} first chunk timing is required"
        )

    stage_total = sum(float(numeric_timings[name]) for name in _CORE_STAGE_TIMINGS)
    if stage_total > worker_total + _TIMING_TOLERANCE_SECONDS:
        raise ValueError(
            f"AI performance benchmark {lane} stage timings exceed worker_total"
        )
    bounded_names = (*_CORE_STAGE_TIMINGS, *(_TIMING_FIELDS[4:]))
    if any(
        numeric_timings[name] is not None
        and float(numeric_timings[name])
        > worker_total + _TIMING_TOLERANCE_SECONDS
        for name in bounded_names
    ):
        raise ValueError(
            f"AI performance benchmark {lane} timing exceeds worker_total"
        )
    if worker_total > parent_worker_elapsed_seconds + _TIMING_TOLERANCE_SECONDS:
        raise ValueError(
            f"AI performance benchmark {lane} worker_total exceeds parent-observed "
            "worker subprocess elapsed time"
        )

    return {
        "schema": MUSCRIPTOR_PERFORMANCE_SCHEMA,
        "measurement_mode": "fresh-process",
        "device": expected_device,
        "timings_seconds": normalised_timings,
        "chunks": {
            "seconds": _rounded(seconds),
            "planned": planned,
            "reported": reported,
        },
        "note_count": note_count,
        "peak_process_rss_bytes": normalised_peak,
        "memory_scope": memory_scope,
        "clock": clock,
    }


def _repeatability(values: Sequence[str]) -> dict[str, Any]:
    return {
        "all_identical": len(set(values)) == 1,
        "unique_count": len(set(values)),
    }


def _collect(
    destination: dict[str, list[int | float]],
    name: str,
    value: int | float | None,
) -> None:
    if value is not None:
        destination.setdefault(name, []).append(value)


def _summary(values: Sequence[int | float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": _rounded(min(values)),
        "median": _rounded(statistics.median(values)),
        "max": _rounded(max(values)),
    }


def _rounded(value: int | float) -> int | float:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return round(float(value), 6)


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite and non-negative")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return number


def _optional_nonnegative_number(value: Any, label: str) -> float | None:
    return None if value is None else _nonnegative_number(value, label)


def _positive_number(value: Any, label: str) -> float:
    number = _nonnegative_number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _validated_started_at(value: Any, *, run_id: str) -> tuple[datetime, str]:
    return _validated_timestamp(value, run_id=run_id, field="started_at")


def _validated_completed_at(value: Any, *, run_id: str) -> tuple[datetime, str]:
    return _validated_timestamp(value, run_id=run_id, field="completed_at")


def _validated_timestamp(
    value: Any, *, run_id: str, field: str
) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"AI performance benchmark run {run_id} has no {field} timestamp"
        )
    text = value.strip()
    iso_value = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError as exc:
        raise ValueError(
            f"AI performance benchmark run {run_id} {field} is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"AI performance benchmark run {run_id} {field} must be timezone-aware"
        )
    utc = parsed.astimezone(timezone.utc)
    return utc, utc.isoformat().replace("+00:00", "Z")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid AI performance benchmark {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"AI performance benchmark {label} must be an object")
    return value


__all__ = [
    "AI_PERFORMANCE_BENCHMARK_SCHEMA",
    "build_ai_performance_benchmark",
    "write_ai_performance_benchmark",
]
