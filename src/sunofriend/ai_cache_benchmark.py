"""Path-free verification for one AI cache miss and repeated exact hits."""

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

import soundfile

from .ai_bakeoff import AI_RUN_SCHEMA, _candidate_tracks
from .ai_cache import (
    AI_CACHE_BENCHMARK_SCHEMA,
    AI_CACHE_ENTRY_SCHEMA,
    AI_CACHE_EVENT_SCHEMA,
    build_muscriptor_cache_identity,
)
from .ai_runtime import AITranscriptionCandidate, AITranscriptionRequest
from .ai_expression import expression_velocities, recover_source_expression
from .midi import write_midi_file


_TIMING_TOLERANCE_SECONDS = 0.05
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def write_ai_cache_benchmark(
    miss_run: str | Path,
    hit_runs: Sequence[str | Path],
    output_path: str | Path,
) -> dict[str, Any]:
    """Verify the completed experiment and atomically write a fresh report."""

    output = Path(output_path).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"AI cache benchmark already exists: {output}")
    report = build_ai_cache_benchmark(miss_run, hit_runs)
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
                f"AI cache benchmark already exists: {output}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return report


def build_ai_cache_benchmark(
    miss_run: str | Path, hit_runs: Sequence[str | Path]
) -> dict[str, Any]:
    """Compare one verified miss-stored run with at least two verified hits."""

    if isinstance(hit_runs, (str, bytes, Path)) or len(hit_runs) < 2:
        raise ValueError("AI cache benchmark needs at least two cache-hit runs")
    paths = [
        Path(miss_run).expanduser().absolute().resolve(),
        *(Path(value).expanduser().absolute().resolve() for value in hit_runs),
    ]
    if len(set(paths)) != len(paths):
        raise ValueError("AI cache benchmark run directories must be unique")

    loaded = [
        _load_run(paths[0], expected_status="miss-stored", repetition=0),
        *(
            _load_run(path, expected_status="verified-hit", repetition=index)
            for index, path in enumerate(paths[1:], start=1)
        ),
    ]
    _validate_sequence(loaded)
    keys = {item["cache_event"]["key_sha256"] for item in loaded}
    entry_hashes = {item["cache_event"]["entry_manifest_sha256"] for item in loaded}
    if len(keys) != 1 or len(entry_hashes) != 1:
        raise ValueError("AI cache benchmark runs do not use one immutable entry")

    comparison_fields = (
        "source_sha256",
        "checkpoint_sha256",
        "config_sha256",
        "worker_sha256",
        "candidate_raw_sha256",
        "candidate_json_sha256",
        "candidate_midi_sha256",
        "candidate_expression_sha256",
        "candidate_expression_midi_sha256",
        "candidate_quality_sha256",
        "candidate_programs_sha256",
        "origin_performance_sha256",
        "note_count",
        "bpm",
        "actual_duration_seconds",
    )
    for field in comparison_fields:
        values = {item[field] for item in loaded}
        if len(values) != 1:
            raise ValueError(f"AI cache benchmark {field} differs across runs")

    miss = loaded[0]
    hits = loaded[1:]
    hit_pipeline_values = [item["pipeline_seconds"] for item in hits]
    hit_preflight_values = [item["preflight_seconds"] for item in hits]
    hit_lookup_values = [item["lookup_seconds"] for item in hits]
    hit_materialise_values = [item["materialise_seconds"] for item in hits]
    hit_postprocess_values = [item["postprocess_seconds"] for item in hits]
    duration = float(miss["actual_duration_seconds"])
    hit_pipeline_median = statistics.median(hit_pipeline_values)
    miss_pipeline = float(miss["pipeline_seconds"])

    report = {
        "schema": AI_CACHE_BENCHMARK_SCHEMA,
        "status": "verified",
        "backend": "muscriptor",
        "cache_key_sha256": next(iter(keys)),
        "cache_entry_manifest_sha256": next(iter(entry_hashes)),
        "source_sha256": miss["source_sha256"],
        "checkpoint_sha256": miss["checkpoint_sha256"],
        "model_config_sha256": miss["config_sha256"],
        "worker_sha256": miss["worker_sha256"],
        "runtime_identity": miss["cache_entry"]["key"]["runtime"],
        "request": miss["cache_entry"]["key"]["request"],
        "bpm": miss["bpm"],
        "actual_duration_seconds": duration,
        "note_count": miss["note_count"],
        "hit_count": len(hits),
        "cache_regime": {
            "application_content_cache": True,
            "payload": "verified-raw-model-output",
            "miss_worker_process": "fresh-process",
            "hit_worker_process_started": False,
            "hit_model_loaded": False,
            "hit_inference_executed": False,
            "resident_model_reused": False,
            "operating_system_file_cache": "uncontrolled",
            "cold_start_claimed": False,
        },
        "timing_definitions": {
            "pipeline_seconds": (
                "Parent pipeline time through current post-processing and cache "
                "evidence, before the final run manifest."
            ),
            "lookup_seconds": "Current verified cache lookup and artifact hashing.",
            "identity_and_preflight_seconds": (
                "Current input hashing, runtime probe and canonical cache-key build."
            ),
            "materialise_seconds": (
                "Current byte-copy time from the verified entry; no hard links."
            ),
            "worker_subprocess_seconds": (
                "Current fresh-process worker duration on the cache miss; null on hits."
            ),
            "postprocess_seconds": (
                "Current quality, GM mapping, source-expression and MIDI derivation."
            ),
            "origin_performance": (
                "muscriptor.performance.json belongs to the original miss inference "
                "and is never interpreted as hit timing."
            ),
        },
        "miss": _public_row(miss),
        "hits": [_public_row(item) for item in hits],
        "aggregates": {
            "hit_pipeline_seconds": _summary(hit_pipeline_values),
            "hit_pipeline_real_time_factor": _rounded(hit_pipeline_median / duration),
            "hit_lookup_seconds": _summary(hit_lookup_values),
            "hit_identity_and_preflight_seconds": _summary(hit_preflight_values),
            "hit_materialise_seconds": _summary(hit_materialise_values),
            "hit_postprocess_seconds": _summary(hit_postprocess_values),
            "miss_pipeline_seconds": _rounded(miss_pipeline),
            "miss_pipeline_real_time_factor": _rounded(miss_pipeline / duration),
            "observed_hit_to_miss_pipeline_ratio": _rounded(
                hit_pipeline_median / miss_pipeline
            ),
        },
        "repeatability": {
            "candidate_raw": _identical(
                [item["candidate_raw_sha256"] for item in loaded]
            ),
            "candidate_json": _identical(
                [item["candidate_json_sha256"] for item in loaded]
            ),
            "candidate_midi": _identical(
                [item["candidate_midi_sha256"] for item in loaded]
            ),
            "candidate_expression": _identical(
                [item["candidate_expression_sha256"] for item in loaded]
            ),
            "candidate_expression_midi": _identical(
                [item["candidate_expression_midi_sha256"] for item in loaded]
            ),
            "candidate_quality": _identical(
                [item["candidate_quality_sha256"] for item in loaded]
            ),
            "candidate_programs": _identical(
                [item["candidate_programs_sha256"] for item in loaded]
            ),
            "note_count": {
                "all_identical": len({item["note_count"] for item in loaded}) == 1,
                "value": miss["note_count"],
                "unique_count": len({item["note_count"] for item in loaded}),
            },
        },
        "privacy": (
            "Paths and caller-supplied run IDs are omitted, but content hashes, "
            "timestamps and runtime identity may identify private material or a "
            "machine and are not publication consent."
        ),
        "promotion_allowed": False,
        "raw_candidates_mutated": False,
        "midi_notes_mutated": 0,
        "interpretation": (
            "A verified hit proves reuse of one prior raw result, not repeated model "
            "agreement, warm-model execution or improved musical accuracy."
        ),
    }
    return report


def _load_run(
    run_dir: Path, *, expected_status: str, repetition: int
) -> dict[str, Any]:
    if not run_dir.is_dir():
        raise ValueError(f"AI cache benchmark run directory does not exist: {run_dir}")
    run = _read_json(run_dir / "run.json", "run manifest")
    if run.get("schema") != AI_RUN_SCHEMA or run.get("status") != "complete":
        raise ValueError("AI cache benchmark needs completed immutable runs")
    if run.get("backend") != "muscriptor":
        raise ValueError("AI cache benchmark supports MuScriptor only")
    run_id = run.get("run_id")
    if not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("AI cache benchmark run_id is invalid")

    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("AI cache benchmark run has no artifact manifest")
    required = (
        "request.json",
        "candidate.raw.json",
        "candidate.json",
        "candidate.mid",
        "candidate.expression.json",
        "candidate.expression.mid",
        "candidate.quality.json",
        "candidate.programs.json",
        "muscriptor.performance.json",
        "cache.entry.json",
        "cache.performance.json",
    )
    verified: dict[str, Path] = {}
    for label in required:
        record = artifacts.get(label)
        if not isinstance(record, Mapping):
            raise ValueError(f"AI cache benchmark run is missing {label}")
        verified[label] = _verify_record(record, run_dir, label)
        if verified[label] != (run_dir / label).resolve():
            raise ValueError(f"AI cache benchmark artifact path changed: {label}")

    source_record = _mapping(run.get("source"), "source")
    checkpoint_record = _mapping(run.get("checkpoint"), "checkpoint")
    worker_record = _mapping(run.get("worker"), "worker")
    source_path = _verify_record(source_record, None, "source")
    _verify_record(checkpoint_record, None, "checkpoint")
    _verify_record(worker_record, None, "worker")
    config_record = _mapping(checkpoint_record.get("config"), "model config")
    _verify_record(config_record, None, "model config")

    request_document = _read_json(verified["request.json"], "request")
    request = AITranscriptionRequest.from_dict(request_document)
    if Path(request.audio_path).resolve() != source_path:
        raise ValueError("AI cache benchmark request source changed")
    if run.get("request") != request_document:
        raise ValueError("AI cache benchmark request evidence disagrees")
    raw_document = _read_json(verified["candidate.raw.json"], "raw candidate")
    raw_candidate = AITranscriptionCandidate.from_dict(raw_document)
    performance = _read_json(
        verified["muscriptor.performance.json"], "origin performance"
    )
    if performance.get("schema") != "sunofriend.muscriptor-performance.v1":
        raise ValueError("AI cache benchmark origin performance schema is invalid")
    if performance.get("measurement_mode") != "fresh-process":
        raise ValueError("AI cache benchmark origin was not fresh-process inference")
    performance_timings = _mapping(
        performance.get("timings_seconds"), "origin performance timings"
    )
    origin_model_load = _positive(
        performance_timings.get("model_load"), "origin model load"
    )
    origin_transcription = _positive(
        performance_timings.get("transcription"), "origin transcription"
    )
    candidate_document = _read_json(verified["candidate.json"], "candidate")
    candidate = AITranscriptionCandidate.from_dict(candidate_document)
    if raw_candidate.to_dict() != candidate.to_dict():
        raise ValueError("AI cache benchmark raw and normalised candidates differ")
    if len(candidate.notes) != int(run.get("note_count", -1)):
        raise ValueError("AI cache benchmark candidate note count changed")
    if candidate.metadata.get("checkpoint_sha256") != checkpoint_record.get("sha256"):
        raise ValueError("AI cache benchmark candidate checkpoint changed")
    expression_document = _read_json(
        verified["candidate.expression.json"], "candidate expression"
    )
    _validate_derived_artifacts(
        source_path=source_path,
        candidate=candidate,
        expression_document=expression_document,
        candidate_midi=verified["candidate.mid"],
        expression_midi=verified["candidate.expression.mid"],
        bpm=_positive(run.get("bpm"), "BPM"),
    )

    cache_event = _read_json(verified["cache.performance.json"], "cache performance")
    cache_entry = _read_json(verified["cache.entry.json"], "cache entry")
    if cache_event.get("schema") != AI_CACHE_EVENT_SCHEMA:
        raise ValueError("AI cache benchmark event schema is invalid")
    if cache_event.get("status") != "complete":
        raise ValueError("AI cache benchmark event is not complete")
    if cache_event.get("run_origin_performance_matches_entry") is not True:
        raise ValueError("AI cache benchmark run does not carry the entry performance")
    if cache_event.get("application_cache_status") != expected_status:
        raise ValueError(
            f"AI cache benchmark expected {expected_status}, got "
            f"{cache_event.get('application_cache_status')}"
        )
    if cache_entry.get("schema") != AI_CACHE_ENTRY_SCHEMA:
        raise ValueError("AI cache benchmark entry schema is invalid")
    if cache_entry.get("status") != "complete":
        raise ValueError("AI cache benchmark entry is not complete")

    cache_summary = _mapping(run.get("application_cache"), "run cache summary")
    for field in (
        "application_cache_status",
        "key_sha256",
        "entry_manifest_sha256",
        "application_cache_hit",
        "entry_published_by_run",
    ):
        if cache_summary.get(field) != cache_event.get(field):
            raise ValueError(f"AI cache benchmark run/event {field} disagrees")
    if cache_entry.get("key_sha256") != cache_event.get("key_sha256"):
        raise ValueError("AI cache benchmark entry/event key disagrees")
    entry_sha256 = _sha256(verified["cache.entry.json"])
    if entry_sha256 != cache_event.get("entry_manifest_sha256"):
        raise ValueError("AI cache benchmark entry manifest hash disagrees")

    identity = build_muscriptor_cache_identity(
        request=request,
        bpm=_positive(run.get("bpm"), "BPM"),
        source=source_record,
        checkpoint=checkpoint_record,
        worker=worker_record,
        runtime=_mapping(run.get("runtime"), "runtime"),
    )
    if identity["key_sha256"] != cache_event.get("key_sha256"):
        raise ValueError("AI cache benchmark recomputed key differs")
    if identity["document"] != cache_entry.get("key"):
        raise ValueError("AI cache benchmark entry identity differs")

    entry_artifacts = _mapping(cache_entry.get("artifacts"), "entry artifacts")
    for label in ("candidate.raw.json", "muscriptor.performance.json"):
        entry_record = _mapping(entry_artifacts.get(label), f"entry {label}")
        run_record = _mapping(artifacts.get(label), f"run {label}")
        if entry_record.get("bytes") != run_record.get("bytes") or entry_record.get(
            "sha256"
        ) != run_record.get("sha256"):
            raise ValueError(f"AI cache benchmark cached {label} differs")

    is_hit = expected_status == "verified-hit"
    if cache_event.get("muscriptor_performance_is_current_run_inference") is is_hit:
        raise ValueError("AI cache benchmark performance timing semantics are invalid")
    _validate_execution_contract(run, cache_event, is_hit=is_hit)
    timings = _mapping(cache_event.get("timings_seconds"), "cache timings")
    preflight = _nonnegative(
        timings.get("identity_and_preflight"), "cache identity and preflight"
    )
    lookup = _nonnegative(timings.get("lookup"), "cache lookup")
    materialise = _optional_nonnegative(
        timings.get("materialise"), "cache materialisation"
    )
    worker_subprocess = _optional_nonnegative(
        timings.get("worker_subprocess"), "cache worker subprocess"
    )
    store = _optional_nonnegative(timings.get("store"), "cache store")
    postprocess = _nonnegative(timings.get("postprocess"), "cache postprocess")
    pipeline = _positive(
        timings.get("pipeline_before_final_evidence"), "cache pipeline"
    )
    elapsed = _positive(run.get("elapsed_seconds"), "run elapsed")
    if pipeline > elapsed + _TIMING_TOLERANCE_SECONDS:
        raise ValueError("AI cache benchmark pipeline exceeds run elapsed time")
    if is_hit and (
        materialise is None or worker_subprocess is not None or store is not None
    ):
        raise ValueError("AI cache hit timing fields are invalid")
    if not is_hit and (
        materialise is not None or worker_subprocess is None or store is None
    ):
        raise ValueError("AI cache miss timing fields are invalid")
    serial_stages = [preflight, lookup, postprocess]
    serial_stages.append(materialise if is_hit else worker_subprocess)
    if not is_hit:
        serial_stages.append(store)
    if sum(float(value) for value in serial_stages if value is not None) > (
        pipeline + _TIMING_TOLERANCE_SECONDS
    ):
        raise ValueError("AI cache benchmark serial stages exceed pipeline timing")
    if not is_hit:
        worker_total = _positive(
            performance_timings.get("worker_total"), "origin worker total"
        )
        if worker_total > float(worker_subprocess) + _TIMING_TOLERANCE_SECONDS:
            raise ValueError("AI cache origin worker timing exceeds subprocess timing")

    started = _timestamp(run.get("started_at"), "started_at")
    completed = _timestamp(run.get("completed_at"), "completed_at")
    if completed < started:
        raise ValueError("AI cache benchmark run completed before it started")
    duration = _actual_duration(source_path, request)
    return {
        "repetition": repetition,
        "run_id": run_id,
        "started": started,
        "completed": completed,
        "started_at": _normalised_timestamp(started),
        "completed_at": _normalised_timestamp(completed),
        "source_sha256": str(source_record["sha256"]),
        "checkpoint_sha256": str(checkpoint_record["sha256"]),
        "config_sha256": str(config_record["sha256"]),
        "worker_sha256": str(worker_record["sha256"]),
        "candidate_raw_sha256": str(artifacts["candidate.raw.json"]["sha256"]),
        "candidate_json_sha256": str(artifacts["candidate.json"]["sha256"]),
        "candidate_midi_sha256": str(artifacts["candidate.mid"]["sha256"]),
        "candidate_expression_sha256": str(
            artifacts["candidate.expression.json"]["sha256"]
        ),
        "candidate_expression_midi_sha256": str(
            artifacts["candidate.expression.mid"]["sha256"]
        ),
        "candidate_quality_sha256": str(artifacts["candidate.quality.json"]["sha256"]),
        "candidate_programs_sha256": str(
            artifacts["candidate.programs.json"]["sha256"]
        ),
        "origin_performance_sha256": str(
            artifacts["muscriptor.performance.json"]["sha256"]
        ),
        "origin_model_load_seconds": origin_model_load,
        "origin_transcription_seconds": origin_transcription,
        "note_count": len(candidate.notes),
        "bpm": float(run["bpm"]),
        "actual_duration_seconds": _rounded(duration),
        "pipeline_seconds": pipeline,
        "preflight_seconds": preflight,
        "lookup_seconds": lookup,
        "materialise_seconds": materialise,
        "worker_subprocess_seconds": worker_subprocess,
        "store_seconds": store,
        "postprocess_seconds": postprocess,
        "cache_event": cache_event,
        "cache_entry": cache_entry,
    }


def _validate_derived_artifacts(
    *,
    source_path: Path,
    candidate: AITranscriptionCandidate,
    expression_document: Mapping[str, Any],
    candidate_midi: Path,
    expression_midi: Path,
    bpm: float,
) -> None:
    expected_expression = recover_source_expression(source_path, candidate)
    recorded_source = expression_document.get("source_audio")
    if (
        not isinstance(recorded_source, str)
        or Path(recorded_source).expanduser().resolve() != source_path.resolve()
    ):
        raise ValueError("AI cache benchmark expression source changed")
    expected_expression["source_audio"] = recorded_source
    if dict(expression_document) != expected_expression:
        raise ValueError("AI cache benchmark expression is not reproducible")
    velocities = expression_velocities(
        dict(expression_document), expected_notes=len(candidate.notes)
    )
    with tempfile.TemporaryDirectory(prefix="sunofriend-cache-midi-") as directory:
        root = Path(directory)
        regenerated_candidate = root / "candidate.mid"
        regenerated_expression = root / "candidate.expression.mid"
        write_midi_file(
            regenerated_candidate,
            _candidate_tracks(candidate),
            bpm=bpm,
        )
        write_midi_file(
            regenerated_expression,
            _candidate_tracks(candidate, velocities=velocities),
            bpm=bpm,
        )
        if regenerated_candidate.read_bytes() != candidate_midi.read_bytes():
            raise ValueError("AI cache benchmark candidate MIDI is not reproducible")
        if regenerated_expression.read_bytes() != expression_midi.read_bytes():
            raise ValueError("AI cache benchmark expression MIDI is not reproducible")


def _validate_execution_contract(
    run: Mapping[str, Any], event: Mapping[str, Any], *, is_hit: bool
) -> None:
    if run.get("worker_transport") is not None:
        raise ValueError("AI cache benchmark cannot contain a persistent session")
    expected_mode = "application-cache-hit" if is_hit else "fresh-subprocess"
    if run.get("worker_execution_mode") != expected_mode:
        raise ValueError("AI cache benchmark execution mode is invalid")
    if run.get("model_reused_from_prior_request") is not False:
        raise ValueError("AI cache benchmark must not claim resident-model reuse")
    for field in (
        "worker_process_started_for_run",
        "inference_executed_for_run",
        "model_loaded_for_run",
        "model_reused_from_prior_request",
    ):
        if event.get(field) != run.get(field):
            raise ValueError(f"AI cache benchmark run/event {field} disagrees")
    if is_hit:
        if any(
            (
                run.get("worker_process_started_for_run") is not False,
                run.get("inference_executed_for_run") is not False,
                run.get("model_loaded_for_run") is not False,
                run.get("worker_subprocess_elapsed_seconds") is not None,
                run.get("worker_request_elapsed_seconds") is not None,
                run.get("exit_code") is not None,
                run.get("command") != [],
                event.get("application_cache_hit") is not True,
                event.get("entry_published_by_run") is not False,
            )
        ):
            raise ValueError("AI cache hit falsely claims worker or model execution")
    else:
        if any(
            (
                run.get("worker_process_started_for_run") is not True,
                run.get("inference_executed_for_run") is not True,
                run.get("model_loaded_for_run") is not True,
                not isinstance(run.get("command"), list) or not run.get("command"),
                run.get("exit_code") != 0,
                event.get("application_cache_hit") is not False,
                event.get("entry_published_by_run") is not True,
            )
        ):
            raise ValueError("AI cache miss lacks fresh inference evidence")
        _positive(
            run.get("worker_subprocess_elapsed_seconds"),
            "cache miss worker subprocess elapsed",
        )


def _validate_sequence(loaded: Sequence[Mapping[str, Any]]) -> None:
    for previous, current in zip(loaded, loaded[1:]):
        if current["started"] < previous["completed"]:
            raise ValueError("AI cache benchmark runs overlap or are out of order")


def _public_row(item: Mapping[str, Any]) -> dict[str, Any]:
    hit = bool(item["cache_event"]["application_cache_hit"])
    return {
        # run_id remains private input evidence: callers may legally use a song,
        # project or person name even though paths are omitted from this report.
        "started_at": item["started_at"],
        "completed_at": item["completed_at"],
        "application_cache_status": item["cache_event"]["application_cache_status"],
        "application_cache_hit": hit,
        "inference_executed_for_run": not hit,
        "worker_process_started_for_run": not hit,
        "model_loaded_for_run": not hit,
        "model_reused_from_prior_request": False,
        "pipeline_seconds": _rounded(float(item["pipeline_seconds"])),
        "pipeline_real_time_factor": _rounded(
            float(item["pipeline_seconds"]) / float(item["actual_duration_seconds"])
        ),
        "identity_and_preflight_seconds": _rounded(float(item["preflight_seconds"])),
        "lookup_seconds": _rounded(float(item["lookup_seconds"])),
        "materialise_seconds": (
            None
            if item["materialise_seconds"] is None
            else _rounded(float(item["materialise_seconds"]))
        ),
        "worker_subprocess_seconds": (
            None
            if item["worker_subprocess_seconds"] is None
            else _rounded(float(item["worker_subprocess_seconds"]))
        ),
        "store_seconds": (
            None
            if item["store_seconds"] is None
            else _rounded(float(item["store_seconds"]))
        ),
        "postprocess_seconds": _rounded(float(item["postprocess_seconds"])),
        "current_model_load_seconds": (
            None if hit else _rounded(float(item["origin_model_load_seconds"]))
        ),
        "current_inference_seconds": (
            None if hit else _rounded(float(item["origin_transcription_seconds"]))
        ),
        "candidate_raw_sha256": item["candidate_raw_sha256"],
        "candidate_json_sha256": item["candidate_json_sha256"],
        "candidate_midi_sha256": item["candidate_midi_sha256"],
        "note_count": item["note_count"],
    }


def _verify_record(record: Mapping[str, Any], root: Path | None, label: str) -> Path:
    path_value = record.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"AI cache benchmark {label} path is invalid")
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        if root is None:
            raise ValueError(f"AI cache benchmark {label} path is not absolute")
        path = root / path
    resolved = path.resolve()
    if root is not None:
        resolved_root = root.resolve()
        if resolved_root not in resolved.parents:
            raise ValueError(f"AI cache benchmark {label} path escaped the run")
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"AI cache benchmark {label} is missing or linked")
    if resolved.stat().st_size != record.get("bytes") or _sha256(
        resolved
    ) != record.get("sha256"):
        raise ValueError(f"AI cache benchmark {label} hash changed")
    return resolved


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"AI cache benchmark {label} is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"AI cache benchmark {label} must be an object")
    return document


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"AI cache benchmark {label} is invalid")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _actual_duration(path: Path, request: AITranscriptionRequest) -> float:
    info = soundfile.info(path)
    start_frame = min(info.frames, round(request.start_seconds * info.samplerate))
    end_frame = (
        info.frames
        if request.end_seconds is None
        else min(info.frames, round(request.end_seconds * info.samplerate))
    )
    frames = end_frame - start_frame
    if frames <= 0:
        raise ValueError("AI cache benchmark excerpt has no source frames")
    return frames / info.samplerate


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"AI cache benchmark {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"AI cache benchmark {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"AI cache benchmark {label} has no timezone")
    return parsed.astimezone(timezone.utc)


def _normalised_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"AI cache benchmark {label} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"AI cache benchmark {label} is not finite")
    return number


def _positive(value: Any, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise ValueError(f"AI cache benchmark {label} must be positive")
    return number


def _nonnegative(value: Any, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"AI cache benchmark {label} must be non-negative")
    return number


def _optional_nonnegative(value: Any, label: str) -> float | None:
    return None if value is None else _nonnegative(value, label)


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "minimum": _rounded(min(values)),
        "median": _rounded(statistics.median(values)),
        "maximum": _rounded(max(values)),
    }


def _identical(values: Sequence[str]) -> dict[str, Any]:
    return {
        "all_identical": len(set(values)) == 1,
        "sha256": values[0] if values and len(set(values)) == 1 else None,
        "unique_count": len(set(values)),
    }


__all__ = [
    "build_ai_cache_benchmark",
    "write_ai_cache_benchmark",
]
