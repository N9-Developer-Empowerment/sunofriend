"""Verify every controlled full-song resource repetition as one result."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_resource import _require_private_regular, _write_json_atomic
from ._separation_full_song_resource_benchmark import (
    _FALSE_PERMISSIONS as _PLAN_FALSE_PERMISSIONS,
    _load_verified_resource_benchmark_plan,
)
from ._separation_full_song_resource_benchmark_run import (
    REPORT_NAME as REPETITION_REPORT_NAME,
    SCHEMA as REPETITION_SCHEMA,
    STATUS as REPETITION_STATUS,
    _THERMAL_NAMES,
)


SCHEMA = "sunofriend.private-separation-full-song-resource-benchmark-result.v1"
STATUS = "controlled_resource_benchmark_complete_private_development_only"
_FALSE_EFFECTS = {
    "model_run_started": False,
    "audio_created": False,
    "audio_mutated": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "product_contract_mutated": False,
}


def _verify_private_full_song_resource_benchmark(
    benchmark_plan_path: str | Path,
    repetition_report_paths: Sequence[str | Path],
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Verify one exact report for every frozen slot and aggregate it."""

    _plan_path, benchmark, benchmark_sha256 = (
        _load_verified_resource_benchmark_plan(benchmark_plan_path)
    )
    required = benchmark["benchmark_contract"]["repetitions"]
    if isinstance(repetition_report_paths, (str, bytes)) or len(
        repetition_report_paths
    ) != required:
        raise ValueError("resource benchmark repetition report count differs")
    repetitions = [
        _load_verified_repetition(
            value,
            benchmark=benchmark,
            benchmark_sha256=benchmark_sha256,
        )
        for value in repetition_report_paths
    ]
    repetitions.sort(key=lambda item: item["document"]["repetition"]["index"])
    if [item["document"]["repetition"]["index"] for item in repetitions] != list(
        range(1, required + 1)
    ):
        raise ValueError("resource benchmark repetition slots differ")
    nonces = [
        item["document"]["repetition"]["nonce_sha256"] for item in repetitions
    ]
    if len(set(nonces)) != required:
        raise ValueError("resource benchmark repetition nonce differs")
    for earlier, later in zip(repetitions, repetitions[1:]):
        if (
            earlier["document"]["interval"]["wall_finished_unix_ns"]
            > later["document"]["interval"]["wall_started_unix_ns"]
        ):
            raise ValueError("resource benchmark repetitions overlap")

    measurement_rows = [item["document"]["measurements"] for item in repetitions]
    elapsed = [
        row["parent_observed_full_song_wall_time_seconds"]
        for row in measurement_rows
    ]
    per_minute = [row["wall_time_seconds_per_audio_minute"] for row in measurement_rows]
    worker = [row["summed_worker_model_call_seconds"] for row in measurement_rows]
    rss = [row["peak_process_rss_bytes"] for row in measurement_rows]
    mlx = [row["peak_mlx_allocator_memory_bytes"] for row in measurement_rows]
    unified = [row["peak_total_unified_memory_bytes"] for row in measurement_rows]
    all_within = all(
        item["document"]["readiness"][
            "this_repetition_within_frozen_thresholds"
        ]
        for item in repetitions
    )
    acceptance_machine = benchmark["machine_class"]["unified_memory_gib"] == 16
    resource_accepted = all_within and acceptance_machine
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "benchmark_plan_sha256": benchmark_sha256,
            "benchmark_plan_document_sha256": benchmark["document_sha256"],
            "plan_report_sha256": benchmark["bindings"]["plan_report_sha256"],
            "checkpoint_sha256": benchmark["bindings"]["checkpoint_sha256"],
            "runtime_executable_sha256": benchmark["bindings"][
                "runtime_executable_sha256"
            ],
        },
        "candidate": dict(benchmark["candidate"]),
        "machine_class": dict(benchmark["machine_class"]),
        "protocol": {
            "name": benchmark["benchmark_contract"]["protocol"],
            "planned_repetitions": required,
            "verified_repetitions": required,
            "serial_non_overlapping": True,
            "distinct_process_scoped_nonces": True,
            "operating_system_cache_controlled": False,
        },
        "repetitions": [
            {
                "index": item["document"]["repetition"]["index"],
                "report_sha256": item["file_sha256"],
                "document_sha256": item["document"]["document_sha256"],
                "nonce_sha256": item["document"]["repetition"]["nonce_sha256"],
                "wall_started_unix_ns": item["document"]["interval"][
                    "wall_started_unix_ns"
                ],
                "wall_finished_unix_ns": item["document"]["interval"][
                    "wall_finished_unix_ns"
                ],
                "within_frozen_thresholds": item["document"]["readiness"][
                    "this_repetition_within_frozen_thresholds"
                ],
            }
            for item in repetitions
        ],
        "aggregate": {
            "parent_observed_full_song_wall_time_seconds": _summary(elapsed),
            "wall_time_seconds_per_audio_minute": _summary(per_minute),
            "summed_worker_model_call_seconds": _summary(worker),
            "peak_process_rss_bytes": _summary(rss),
            "peak_mlx_allocator_memory_bytes": _summary(mlx),
            "peak_total_unified_memory_bytes": _summary(unified),
            "maximum_peak_total_unified_memory_gib": round(max(unified) / 1024**3, 6),
            "thermal_state_before": [
                row["thermal_state_before"] for row in measurement_rows
            ],
            "thermal_state_after": [
                row["thermal_state_after"] for row in measurement_rows
            ],
            "timeouts_observed": 0,
            "oom_events_observed": 0,
        },
        "thresholds": dict(benchmark["benchmark_contract"]["thresholds"]),
        "coverage": {
            "controlled_repetitions_observed": required,
            "all_required_measurements_observed": True,
            "same_plan_checkpoint_runtime_device_and_machine_observed": True,
            "serial_non_overlapping_execution_observed": True,
            "required_16_gib_acceptance_class_observed": acceptance_machine,
            "development_machine_thresholds_met": all_within,
        },
        "readiness": {
            "controlled_repeated_benchmark_complete": True,
            "development_machine_thresholds_met": all_within,
            "resource_envelope_accepted": resource_accepted,
            "publication_ready": False,
        },
        "limitations": [
            "The operating-system cache was not controlled.",
            "Peak MLX allocator, process RSS and Darwin physical footprint remain distinct measurements.",
            (
                "This machine is the required 16 GiB acceptance class."
                if acceptance_machine
                else "This development machine is not the required 16 GiB acceptance class."
            ),
            "This private benchmark does not select a separator or enable a product route.",
        ],
        "permissions": dict(_PLAN_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
    }
    report["document_sha256"] = _document_sha256(report)
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"private resource benchmark result exists: {output}")
    _write_json_atomic(output, report)
    return {**report, "report": str(output)}


def _load_verified_repetition(
    value: str | Path,
    *,
    benchmark: Mapping[str, Any],
    benchmark_sha256: str,
) -> dict[str, Any]:
    path = Path(value).expanduser().absolute()
    if path.name != REPETITION_REPORT_NAME:
        raise ValueError("resource benchmark repetition filename differs")
    _require_private_regular(path, "resource benchmark repetition report")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("resource benchmark repetition JSON differs") from error
    repetition = document.get("repetition") if isinstance(document, dict) else None
    interval = document.get("interval") if isinstance(document, dict) else None
    measurements = (
        document.get("measurements") if isinstance(document, dict) else None
    )
    bindings = document.get("bindings") if isinstance(document, dict) else None
    readiness = document.get("readiness") if isinstance(document, dict) else None
    checks = document.get("threshold_checks") if isinstance(document, dict) else None
    effects = document.get("effects") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema") != REPETITION_SCHEMA
        or document.get("status") != REPETITION_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(bindings, dict)
        or bindings.get("benchmark_plan_sha256") != benchmark_sha256
        or bindings.get("benchmark_plan_document_sha256")
        != benchmark["document_sha256"]
        or bindings.get("plan_report_sha256")
        != benchmark["bindings"]["plan_report_sha256"]
        or not _all_hashes(bindings)
        or document.get("candidate") != benchmark["candidate"]
        or document.get("machine_class") != benchmark["machine_class"]
        or not isinstance(repetition, dict)
        or type(repetition.get("index")) is not int
        or not 1
        <= repetition["index"]
        <= benchmark["benchmark_contract"]["repetitions"]
        or not _hash(repetition.get("nonce_sha256"))
        or repetition.get("runner_process_scope")
        != "one_script_process_one_repetition"
        or repetition.get("fresh_execution_root") is not True
        or not isinstance(interval, dict)
        or type(interval.get("wall_started_unix_ns")) is not int
        or type(interval.get("wall_finished_unix_ns")) is not int
        or interval["wall_started_unix_ns"] <= 0
        or interval["wall_finished_unix_ns"] <= interval["wall_started_unix_ns"]
        or interval.get("scope") != "execute_stitch_and_resource_observation"
        or not isinstance(measurements, dict)
        or not isinstance(readiness, dict)
        or not isinstance(checks, dict)
        or document.get("permissions") != _PLAN_FALSE_PERMISSIONS
        or effects
        != {
            "model_run_started": True,
            "private_audio_created": True,
            "separator_selected": False,
            "source_graph_mutated": False,
            "product_contract_mutated": False,
        }
    ):
        raise ValueError("resource benchmark repetition identity differs")
    _verify_measurements(
        measurements,
        interval=interval,
        source_clock=benchmark["source_clock"],
    )
    expected_checks = _threshold_checks(
        measurements,
        benchmark["benchmark_contract"]["thresholds"],
    )
    if (
        checks != expected_checks
        or readiness
        != {
            "repetition_complete": True,
            "all_required_measurements_observed": True,
            "this_repetition_within_frozen_thresholds": all(
                expected_checks.values()
            ),
            "controlled_repeated_benchmark_complete": False,
            "resource_envelope_accepted": False,
            "publication_ready": False,
        }
    ):
        raise ValueError("resource benchmark repetition threshold differs")
    raw = path.read_bytes()
    if b'"path"' in raw or b'"paths"' in raw or b'"/' in raw or b"://" in raw:
        raise ValueError("resource benchmark repetition retained a path")
    return {
        "document": document,
        "file_sha256": _sha256(path),
    }


def _verify_measurements(
    measurements: Mapping[str, Any],
    *,
    interval: Mapping[str, Any],
    source_clock: Mapping[str, Any],
) -> None:
    required_numbers = (
        "song_duration_seconds",
        "parent_observed_full_song_wall_time_seconds",
        "wall_time_seconds_per_audio_minute",
        "summed_worker_model_call_seconds",
        "peak_total_unified_memory_gib",
    )
    required_ints = (
        "peak_process_rss_bytes",
        "peak_mlx_allocator_memory_bytes",
        "peak_total_unified_memory_bytes",
    )
    if (
        set(measurements)
        != {
            *required_numbers,
            *required_ints,
            "thermal_state_before",
            "thermal_state_after",
            "timeout_observed",
            "oom_observed",
        }
        or any(not _positive_number(measurements.get(key)) for key in required_numbers)
        or any(
            type(measurements.get(key)) is not int or measurements[key] <= 0
            for key in required_ints
        )
        or measurements.get("timeout_observed") is not False
        or measurements.get("oom_observed") is not False
        or not _thermal(measurements.get("thermal_state_before"))
        or not _thermal(measurements.get("thermal_state_after"))
        or not math.isclose(
            float(measurements["song_duration_seconds"]),
            float(source_clock["duration_seconds"]),
            abs_tol=1e-6,
        )
        or float(measurements["summed_worker_model_call_seconds"])
        > float(measurements["parent_observed_full_song_wall_time_seconds"])
        + 0.001
        or not math.isclose(
            float(measurements["parent_observed_full_song_wall_time_seconds"]),
            float(interval["parent_observed_elapsed_seconds"]),
            abs_tol=1e-6,
        )
        or not math.isclose(
            float(measurements["wall_time_seconds_per_audio_minute"]),
            float(measurements["parent_observed_full_song_wall_time_seconds"])
            / (float(measurements["song_duration_seconds"]) / 60.0),
            abs_tol=1e-5,
        )
        or not math.isclose(
            float(measurements["peak_total_unified_memory_gib"]),
            measurements["peak_total_unified_memory_bytes"] / 1024**3,
            abs_tol=1e-5,
        )
    ):
        raise ValueError("resource benchmark repetition measurement differs")


def _threshold_checks(
    measurements: Mapping[str, Any], thresholds: Mapping[str, Any]
) -> dict[str, bool]:
    return {
        "wall_time_seconds_per_audio_minute": (
            measurements["wall_time_seconds_per_audio_minute"]
            <= thresholds["wall_time_seconds_per_audio_minute_max"]
        ),
        "single_song_wall_time_seconds": (
            measurements["parent_observed_full_song_wall_time_seconds"]
            <= thresholds["single_song_wall_time_seconds_max"]
        ),
        "peak_total_unified_memory_gib": (
            measurements["peak_total_unified_memory_gib"]
            <= thresholds["peak_unified_memory_gib_max"]
        ),
        "timeout": measurements["timeout_observed"] is False,
        "oom": measurements["oom_observed"] is False,
    }


def _all_hashes(bindings: Mapping[str, Any]) -> bool:
    expected = {
        "benchmark_plan_sha256",
        "benchmark_plan_document_sha256",
        "plan_report_sha256",
        "execution_report_sha256",
        "execution_state_sha256",
        "stitch_report_sha256",
        "stitch_document_sha256",
        "resource_observation_sha256",
        "resource_observation_document_sha256",
    }
    return set(bindings) == expected and all(_hash(bindings[key]) for key in expected)


def _hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _thermal(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"value", "name"}
        and type(value.get("value")) is int
        and value["value"] in _THERMAL_NAMES
        and value.get("name") == _THERMAL_NAMES[value["value"]]
    )


def _positive_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _summary(values: Sequence[int | float]) -> dict[str, int | float]:
    return {
        "count": len(values),
        "minimum": min(values),
        "median": round(float(statistics.median(values)), 6),
        "maximum": max(values),
    }


__all__: tuple[str, ...] = ()
