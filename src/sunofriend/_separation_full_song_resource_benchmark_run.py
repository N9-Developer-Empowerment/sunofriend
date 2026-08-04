"""Run one fresh-process repetition of the private resource benchmark.

The public product cannot import this module.  One script process may create
one fresh repetition root, execute the complete sealed song, stitch it and
write a path-free measurement report.  A separate verifier must see every
planned repetition before it can make even a private-development threshold
statement.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import secrets
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
    _execute_private_separation_full_song_queue,
    _load_verified_plan,
    _require_private_directory,
)
from ._separation_full_song_resource import (
    SCHEMA as RESOURCE_SCHEMA,
    _observe_private_separation_full_song_resources,
    _write_json_atomic,
)
from ._separation_full_song_resource_benchmark import (
    _file_claim,
    _load_verified_resource_benchmark_plan,
    _probe_machine,
    _resolved_regular_file,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    _stitch_private_separation_full_song,
)


SCHEMA = "sunofriend.private-separation-full-song-resource-benchmark-repetition.v1"
STATUS = "controlled_resource_benchmark_repetition_complete"
REPORT_NAME = "private-separation-full-song-resource-benchmark-repetition.json"
_THERMAL_NAMES = {
    0: "nominal",
    1: "fair",
    2: "serious",
    3: "critical",
}
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "benchmark_claim": False,
    "performance_acceptance": False,
    "source_graph_activation": False,
    "simple_mode_available": False,
    "studio_import_available": False,
    "product_route_permitted": False,
    "publication_permitted": False,
}

Executor = Callable[..., Mapping[str, Any]]
Stitcher = Callable[..., Mapping[str, Any]]
Observer = Callable[..., Mapping[str, Any]]
CommandRunner = Callable[[Sequence[str]], str]
Clock = Callable[[], int]
NonceFactory = Callable[[], str]


def _run_private_full_song_resource_benchmark_repetition(
    benchmark_plan_path: str | Path,
    plan_report_path: str | Path,
    *,
    repetition_index: int,
    out_dir: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    command_runner: CommandRunner = lambda command: _run_probe_command(command),
    thermal_probe: Callable[[], Mapping[str, Any]] = lambda: _probe_thermal_state(),
    monotonic_ns: Clock = time.monotonic_ns,
    wall_time_ns: Clock = time.time_ns,
    nonce_factory: NonceFactory = lambda: secrets.token_hex(32),
    executor: Executor = _execute_private_separation_full_song_queue,
    stitcher: Stitcher = _stitch_private_separation_full_song,
    observer: Observer = _observe_private_separation_full_song_resources,
) -> dict[str, Any]:
    """Execute one exact repetition in one fresh owner-only root."""

    _benchmark_path, benchmark, benchmark_sha256 = (
        _load_verified_resource_benchmark_plan(benchmark_plan_path)
    )
    repetitions = benchmark["benchmark_contract"]["repetitions"]
    if (
        isinstance(repetition_index, bool)
        or not isinstance(repetition_index, int)
        or not 1 <= repetition_index <= repetitions
    ):
        raise ValueError("resource benchmark repetition index differs")

    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    if (
        plan_sha256 != benchmark["bindings"]["plan_report_sha256"]
        or plan["document_sha256"]
        != benchmark["bindings"]["plan_document_sha256"]
        or plan["canonical_clock"]["pcm24_int32_sequence_sha256"]
        != benchmark["bindings"]["canonical_pcm24_int32_sequence_sha256"]
    ):
        raise ValueError("resource benchmark full-song plan differs")

    runtime = _resolved_regular_file(runtime_launcher_path, "runtime launcher")
    checkpoint = _resolved_regular_file(checkpoint_path, "Kim checkpoint")
    _verify_file_binding(
        runtime,
        expected_sha256=benchmark["bindings"]["runtime_executable_sha256"],
        expected_bytes=benchmark["bindings"]["runtime_executable_bytes"],
        label="runtime launcher",
    )
    _verify_file_binding(
        checkpoint,
        expected_sha256=benchmark["bindings"]["checkpoint_sha256"],
        expected_bytes=benchmark["bindings"]["checkpoint_bytes"],
        label="Kim checkpoint",
    )
    observed_machine = _probe_machine(runtime, command_runner=command_runner)
    if observed_machine != benchmark["machine_class"]:
        raise ValueError("resource benchmark machine differs")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"resource benchmark repetition root already exists: {destination}"
        )
    destination.mkdir(parents=False, mode=0o700)
    destination.chmod(0o700)
    _require_private_directory(destination, "resource benchmark repetition root")

    nonce = nonce_factory()
    if not isinstance(nonce, str) or len(nonce) < 32 or len(nonce) > 256:
        raise ValueError("resource benchmark repetition nonce differs")
    nonce_sha256 = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    thermal_before = _verified_thermal_state(thermal_probe())
    wall_started_ns = wall_time_ns()
    monotonic_started_ns = monotonic_ns()

    execution_root = destination / "execution"
    execution = executor(
        plan_path,
        out_dir=execution_root,
        repository_root=repository_root,
        runtime_launcher_path=runtime,
        source_root=source_root,
        checkpoint_path=checkpoint,
        companion_root=companion_root,
        device=benchmark["candidate"]["device"],
        maximum_chunks=None,
    )
    execution_report = execution_root / EXECUTION_REPORT_NAME
    stitch_root = destination / "stitch"
    stitch = stitcher(
        plan_path,
        execution_report,
        out_dir=stitch_root,
    )
    stitch_report = stitch_root / STITCH_REPORT_NAME
    resource_report = destination / "resource-observation.json"
    resource = observer(
        plan_path,
        execution_report,
        stitch_report,
        out=resource_report,
    )

    if _sha256(plan_path) != plan_sha256:
        raise ValueError("resource benchmark full-song plan changed during execution")
    _verify_file_binding(
        runtime,
        expected_sha256=benchmark["bindings"]["runtime_executable_sha256"],
        expected_bytes=benchmark["bindings"]["runtime_executable_bytes"],
        label="runtime launcher",
    )
    _verify_file_binding(
        checkpoint,
        expected_sha256=benchmark["bindings"]["checkpoint_sha256"],
        expected_bytes=benchmark["bindings"]["checkpoint_bytes"],
        label="Kim checkpoint",
    )

    monotonic_finished_ns = monotonic_ns()
    wall_finished_ns = wall_time_ns()
    thermal_after = _verified_thermal_state(thermal_probe())
    if (
        monotonic_finished_ns <= monotonic_started_ns
        or wall_finished_ns <= wall_started_ns
    ):
        raise ValueError("resource benchmark repetition clock differs")
    elapsed_seconds = (monotonic_finished_ns - monotonic_started_ns) / 1e9
    report = _build_repetition_report(
        benchmark=benchmark,
        benchmark_sha256=benchmark_sha256,
        repetition_index=repetition_index,
        nonce_sha256=nonce_sha256,
        wall_started_ns=wall_started_ns,
        wall_finished_ns=wall_finished_ns,
        elapsed_seconds=elapsed_seconds,
        thermal_before=thermal_before,
        thermal_after=thermal_after,
        execution=execution,
        execution_report=execution_report,
        stitch=stitch,
        stitch_report=stitch_report,
        resource=resource,
        resource_report=resource_report,
    )
    output = destination / REPORT_NAME
    _write_json_atomic(output, report)
    return {**report, "report": str(output), "output_directory": str(destination)}


def _build_repetition_report(
    *,
    benchmark: Mapping[str, Any],
    benchmark_sha256: str,
    repetition_index: int,
    nonce_sha256: str,
    wall_started_ns: int,
    wall_finished_ns: int,
    elapsed_seconds: float,
    thermal_before: Mapping[str, Any],
    thermal_after: Mapping[str, Any],
    execution: Mapping[str, Any],
    execution_report: Path,
    stitch: Mapping[str, Any],
    stitch_report: Path,
    resource: Mapping[str, Any],
    resource_report: Path,
) -> dict[str, Any]:
    native = (resource.get("execution_observation") or {}).get(
        "native_process_resources"
    )
    worker = (resource.get("execution_observation") or {}).get("worker_resources")
    coverage = resource.get("coverage")
    if (
        execution.get("status") != "private_chunk_execution_complete_not_selected"
        or (execution.get("summary") or {}).get("all_worker_runs_complete") is not True
        or stitch.get("status") != "exact_clock_stitch_complete_review_required"
        or resource.get("schema") != RESOURCE_SCHEMA
        or not isinstance(native, Mapping)
        or native.get("complete_for_selected_attempts") is not True
        or not isinstance(worker, Mapping)
        or worker.get("complete_for_selected_attempts") is not True
        or not isinstance(coverage, Mapping)
        or coverage.get("peak_process_rss_observed") is not True
        or coverage.get("peak_total_unified_memory_observed") is not True
        or coverage.get("peak_mlx_allocator_memory_observed") is not True
        or coverage.get("worker_model_inference_time_observed") is not True
    ):
        raise ValueError("resource benchmark repetition evidence is incomplete")

    song_seconds = benchmark["source_clock"]["duration_seconds"]
    wall_per_audio_minute = elapsed_seconds / (song_seconds / 60.0)
    peak_unified_bytes = native.get("maximum_peak_total_unified_memory_bytes")
    peak_rss_bytes = native.get("maximum_peak_process_rss_bytes")
    peak_mlx_bytes = worker.get("maximum_peak_mlx_allocator_memory_bytes")
    worker_seconds = worker.get("summed_inference_seconds")
    if (
        not _positive_number(elapsed_seconds)
        or not _positive_number(wall_per_audio_minute)
        or not _positive_number(worker_seconds)
        or float(worker_seconds) > elapsed_seconds + 0.001
        or type(peak_unified_bytes) is not int
        or type(peak_rss_bytes) is not int
        or type(peak_mlx_bytes) is not int
        or min(peak_unified_bytes, peak_rss_bytes, peak_mlx_bytes) <= 0
    ):
        raise ValueError("resource benchmark repetition measurement differs")
    thresholds = benchmark["benchmark_contract"]["thresholds"]
    checks = {
        "wall_time_seconds_per_audio_minute": (
            wall_per_audio_minute
            <= thresholds["wall_time_seconds_per_audio_minute_max"]
        ),
        "single_song_wall_time_seconds": (
            elapsed_seconds <= thresholds["single_song_wall_time_seconds_max"]
        ),
        "peak_total_unified_memory_gib": (
            peak_unified_bytes / 1024**3
            <= thresholds["peak_unified_memory_gib_max"]
        ),
        "timeout": True,
        "oom": True,
    }
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "benchmark_plan_sha256": benchmark_sha256,
            "benchmark_plan_document_sha256": benchmark["document_sha256"],
            "plan_report_sha256": benchmark["bindings"]["plan_report_sha256"],
            "execution_report_sha256": _sha256(execution_report),
            "execution_state_sha256": execution["state_sha256"],
            "stitch_report_sha256": _sha256(stitch_report),
            "stitch_document_sha256": stitch["document_sha256"],
            "resource_observation_sha256": _sha256(resource_report),
            "resource_observation_document_sha256": resource["document_sha256"],
        },
        "candidate": dict(benchmark["candidate"]),
        "machine_class": dict(benchmark["machine_class"]),
        "repetition": {
            "index": repetition_index,
            "nonce_sha256": nonce_sha256,
            "runner_process_scope": "one_script_process_one_repetition",
            "fresh_execution_root": True,
        },
        "interval": {
            "wall_started_unix_ns": wall_started_ns,
            "wall_finished_unix_ns": wall_finished_ns,
            "parent_observed_elapsed_seconds": round(elapsed_seconds, 6),
            "scope": "execute_stitch_and_resource_observation",
        },
        "measurements": {
            "song_duration_seconds": song_seconds,
            "parent_observed_full_song_wall_time_seconds": round(
                elapsed_seconds, 6
            ),
            "wall_time_seconds_per_audio_minute": round(
                wall_per_audio_minute, 6
            ),
            "summed_worker_model_call_seconds": worker_seconds,
            "peak_process_rss_bytes": peak_rss_bytes,
            "peak_mlx_allocator_memory_bytes": peak_mlx_bytes,
            "peak_total_unified_memory_bytes": peak_unified_bytes,
            "peak_total_unified_memory_gib": round(
                peak_unified_bytes / 1024**3, 6
            ),
            "thermal_state_before": dict(thermal_before),
            "thermal_state_after": dict(thermal_after),
            "timeout_observed": False,
            "oom_observed": False,
        },
        "threshold_checks": checks,
        "readiness": {
            "repetition_complete": True,
            "all_required_measurements_observed": True,
            "this_repetition_within_frozen_thresholds": all(checks.values()),
            "controlled_repeated_benchmark_complete": False,
            "resource_envelope_accepted": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "model_run_started": True,
            "private_audio_created": True,
            "separator_selected": False,
            "source_graph_mutated": False,
            "product_contract_mutated": False,
        },
    }
    report["document_sha256"] = _document_sha256(report)
    return report


def _verify_file_binding(
    path: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    label: str,
) -> None:
    claim = _file_claim(path)
    if claim["sha256"] != expected_sha256 or claim["bytes"] != expected_bytes:
        raise ValueError(f"resource benchmark {label} differs")


def _verified_thermal_state(value: Mapping[str, Any]) -> dict[str, Any]:
    state = value.get("value") if isinstance(value, Mapping) else None
    name = value.get("name") if isinstance(value, Mapping) else None
    if type(state) is not int or state not in _THERMAL_NAMES:
        raise ValueError("resource benchmark thermal state differs")
    if name != _THERMAL_NAMES[state]:
        raise ValueError("resource benchmark thermal state differs")
    return {"value": state, "name": name}


def _probe_thermal_state() -> dict[str, Any]:
    source = 'ObjC.import("Foundation"); $.NSProcessInfo.processInfo.thermalState'
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", source],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
            cwd="/",
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            close_fds=True,
        )
        value = int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError("resource benchmark thermal probe failed") from error
    if result.stderr or value not in _THERMAL_NAMES:
        raise ValueError("resource benchmark thermal probe differs")
    return {"value": value, "name": _THERMAL_NAMES[value]}


def _run_probe_command(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
            cwd="/",
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            close_fds=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("resource benchmark machine probe failed") from error
    if result.stderr:
        raise ValueError("resource benchmark machine probe produced diagnostics")
    return result.stdout


def _positive_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


__all__: tuple[str, ...] = ()
