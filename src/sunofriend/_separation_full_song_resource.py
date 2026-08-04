"""Summarise verified full-song execution resources without benchmark claims."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    _load_hashed_json,
    _load_verified_plan,
    _require_private_directory,
    _require_private_regular,
    _verify_completed_attempts,
    _verify_state_binding,
)
from ._separation_full_song_review import _load_stitch_report, _verify_stitch_audio
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME
from ._separation_melroformer_native_attempt_darwin import _TIMING_SCHEMA


SCHEMA = "sunofriend.private-separation-full-song-resource-observation.v1"
STATUS = "coarse_resource_observation_complete_acceptance_open"
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
_FALSE_EFFECTS = {
    "model_run_started": False,
    "audio_created": False,
    "audio_mutated": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "product_contract_mutated": False,
}


def _observe_private_separation_full_song_resources(
    plan_report_path: str | Path,
    execution_report_path: str | Path,
    stitch_report_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Verify completed evidence and write one coarse, non-benchmark report."""

    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    execution_path = Path(execution_report_path).expanduser().absolute()
    if execution_path.name != EXECUTION_REPORT_NAME:
        raise ValueError("private full-song execution filename differs")
    _require_private_regular(execution_path, "private full-song execution report")
    execution = _load_json(execution_path, "private full-song execution report")
    if (
        execution.get("schema") != EXECUTION_SCHEMA
        or execution.get("status") != "private_chunk_execution_complete_not_selected"
        or (execution.get("summary") or {}).get("all_worker_runs_complete") is not True
    ):
        raise ValueError("private full-song execution is incomplete")
    _verify_state_binding(execution, plan=plan, plan_sha256=plan_sha256)
    _verify_completed_attempts(execution_path.parent, execution, plan)

    stitch_path = Path(stitch_report_path).expanduser().absolute()
    if stitch_path.name != STITCH_REPORT_NAME:
        raise ValueError("private full-song stitch filename differs")
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_bindings(
        stitch,
        plan=plan,
        plan_sha256=plan_sha256,
        execution=execution,
        execution_sha256=_sha256(execution_path),
    )
    _verify_stitch_audio(stitch_path.parent, stitch)

    observations = []
    worker_resources = []
    native_resources = []
    missing_worker_resources = 0
    missing_native_resources = 0
    preserved_incomplete = 0
    for chunk in execution["chunks"]:
        preserved_incomplete += sum(
            item.get("status") == "preserved_incomplete"
            for item in chunk["attempts"]
        )
        selected = [
            item
            for item in chunk["attempts"]
            if item.get("attempt") == chunk.get("selected_attempt")
            and item.get("status") == "verified_complete"
        ]
        if len(selected) != 1:
            raise ValueError("private full-song selected attempt differs")
        attempt = execution_path.parent / selected[0]["path"]
        timing = _load_hashed_json(
            attempt / "native-attempt-timing.json",
            key="timing_sha256",
        )
        observations.append(_timing_observation(chunk["index"], timing))
        receipt = _load_hashed_json(
            attempt / "native-attempt-receipt.json",
            key="receipt_sha256",
        )
        projected = receipt.get("worker_resource_projection")
        if projected is None:
            missing_worker_resources += 1
        else:
            worker_resources.append(
                _worker_resource_observation(chunk["index"], receipt, projected)
            )
        native_projected = receipt.get("native_process_resource_projection")
        if native_projected is None:
            missing_native_resources += 1
        else:
            native_resources.append(
                _native_resource_observation(
                    chunk["index"], receipt, native_projected
                )
            )

    elapsed = [row["observed_total_seconds"] for row in observations]
    song_seconds = plan["canonical_clock"]["frames"] / 44_100
    total_seconds = math.fsum(elapsed)
    stage_names = observations[0]["stage_order"]
    if any(row["stage_order"] != stage_names for row in observations[1:]):
        raise ValueError("private full-song timing stage order differs")
    stage_summary = {
        name: _summary([row["stage_seconds"][name] for row in observations])
        for name in stage_names
    }
    worker_resource_summary = _worker_resource_summary(
        worker_resources,
        selected_attempt_count=len(observations),
        missing_count=missing_worker_resources,
    )
    complete_worker_resources = (
        len(worker_resources) == len(observations) and missing_worker_resources == 0
    )
    native_resource_summary = _native_resource_summary(
        native_resources,
        selected_attempt_count=len(observations),
        missing_count=missing_native_resources,
    )
    complete_native_resources = (
        len(native_resources) == len(observations) and missing_native_resources == 0
    )

    plan_tree = _tree_inventory(plan_path.parent, "private full-song plan tree")
    execution_tree = _tree_inventory(
        execution_path.parent, "private full-song execution tree"
    )
    stitch_tree = _tree_inventory(stitch_path.parent, "private full-song stitch tree")
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"private full-song resource report already exists: {output}")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_report_sha256": plan_sha256,
            "plan_document_sha256": plan["document_sha256"],
            "execution_report_sha256": _sha256(execution_path),
            "execution_state_sha256": execution["state_sha256"],
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
        },
        "source_clock": {
            "sample_rate": 44_100,
            "frames": plan["canonical_clock"]["frames"],
            "duration_seconds": round(song_seconds, 9),
            "chunk_count": len(plan["chunks"]),
        },
        "execution_observation": {
            "policy": "sum-of-selected-coarse-monotonic-attempt-timings-v1",
            "benchmark": False,
            "selected_attempt_count": len(observations),
            "preserved_incomplete_attempt_count": preserved_incomplete,
            "attempt_total_seconds": _summary(elapsed),
            "summed_observed_seconds": round(total_seconds, 6),
            "observed_serial_real_time_factor": round(total_seconds / song_seconds, 6),
            "observed_serial_audio_seconds_per_elapsed_second": round(
                song_seconds / total_seconds, 6
            ),
            "p95_policy": "nearest-rank",
            "stage_seconds": stage_summary,
            "chunks": observations,
            "worker_resources": worker_resource_summary,
            "native_process_resources": native_resource_summary,
        },
        "disk_snapshot": {
            "policy": "owner-only-regular-files-no-symbolic-links-v1",
            "plan_tree": plan_tree,
            "execution_tree": execution_tree,
            "stitch_tree": stitch_tree,
            "aggregate_regular_file_bytes": (
                plan_tree["regular_file_bytes"]
                + execution_tree["regular_file_bytes"]
                + stitch_tree["regular_file_bytes"]
            ),
        },
        "coverage": {
            "selected_attempt_integrity_verified": True,
            "stitched_audio_integrity_verified": True,
            "coarse_monotonic_timing_observed": True,
            "disk_snapshot_observed": True,
            "worker_model_inference_time_observed": complete_worker_resources,
            "peak_mlx_allocator_memory_observed": complete_worker_resources,
            "peak_process_rss_observed": complete_native_resources,
            "peak_total_unified_memory_observed": complete_native_resources,
            "peak_accelerator_memory_observed": False,
            "thermal_state_observed": False,
            "energy_use_observed": False,
            "controlled_repeated_benchmark_observed": False,
            "concurrent_load_observed": False,
            "offline_network_claim_evaluated_here": False,
        },
        "readiness": {
            "coarse_resource_observation_complete": True,
            "resource_envelope_accepted": False,
            "publication_ready": False,
        },
        "limitations": [
            "These are coarse per-attempt monotonic timings, not a benchmark.",
            "The operating-system cache, scheduler and thermal state were uncontrolled.",
            (
                "Peak MLX allocator memory was retained for every selected worker; "
                "it remains separate from Darwin RSS and physical-footprint evidence."
                if complete_worker_resources and complete_native_resources
                else "Complete MLX, process RSS and physical-footprint evidence was "
                "not retained for every selected worker."
            ),
            "Thermal behaviour, energy use and concurrent workloads were not measured.",
            "This report does not establish offline-network behaviour or product safety.",
        ],
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
    }
    report["document_sha256"] = _document_sha256(report)
    _write_json_atomic(output, report)
    return {**report, "report": str(output)}


def _verify_stitch_bindings(
    stitch: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
    execution: Mapping[str, Any],
    execution_sha256: str,
) -> None:
    expected = {
        "plan_report_sha256": plan_sha256,
        "plan_document_sha256": plan["document_sha256"],
        "execution_report_sha256": execution_sha256,
        "execution_state_sha256": execution["state_sha256"],
        "canonical_pcm24_int32_sequence_sha256": plan["canonical_clock"][
            "pcm24_int32_sequence_sha256"
        ],
    }
    clock = stitch.get("clock") or {}
    if (
        stitch.get("bindings") != expected
        or clock.get("frames") != plan["canonical_clock"]["frames"]
        or clock.get("duration_seconds") != plan["canonical_clock"]["duration_seconds"]
        or clock.get("chunk_count") != len(plan["chunks"])
        or clock.get("boundary_count") != len(plan["chunks"]) - 1
    ):
        raise ValueError("private full-song stitch binding differs")


def _timing_observation(chunk_index: int, timing: Mapping[str, Any]) -> dict[str, Any]:
    stages = timing.get("stage_seconds")
    order = timing.get("stage_order")
    total = timing.get("observed_total_through_output_evidence_seconds")
    longest = timing.get("longest_stage")
    if (
        timing.get("schema") != _TIMING_SCHEMA
        or timing.get("status") != "private_runtime_observation_not_benchmark"
        or timing.get("evidence_scope")
        != "private_local_coarse_stage_timing_only"
        or not isinstance(order, list)
        or not order
        or len(set(order)) != len(order)
        or not all(isinstance(name, str) and name for name in order)
        or not isinstance(stages, Mapping)
        or set(stages) != set(order)
        or not _positive_number(total)
        or not isinstance(longest, Mapping)
        or not isinstance(timing.get("permissions"), Mapping)
        or not timing["permissions"]
        or any(value is not False for value in timing["permissions"].values())
    ):
        raise ValueError("private full-song timing observation differs")
    values = {name: stages[name] for name in order}
    if any(not _nonnegative_number(value) for value in values.values()):
        raise ValueError("private full-song timing stage differs")
    maximum_name = max(order, key=lambda name: values[name])
    if (
        longest.get("name") != maximum_name
        or longest.get("seconds") != values[maximum_name]
        or math.fsum(values.values()) > float(total) + 0.001
    ):
        raise ValueError("private full-song timing summary differs")
    return {
        "chunk_index": chunk_index,
        "observed_total_seconds": round(float(total), 6),
        "longest_stage": {
            "name": maximum_name,
            "seconds": round(float(values[maximum_name]), 6),
        },
        "stage_order": list(order),
        "stage_seconds": {name: round(float(values[name]), 6) for name in order},
    }


def _worker_resource_observation(
    chunk_index: int,
    receipt: Mapping[str, Any],
    projection_value: object,
) -> dict[str, Any]:
    projection = dict(projection_value) if isinstance(projection_value, Mapping) else {}
    payload = dict(projection)
    projection_sha256 = payload.pop("projection_sha256", None)
    bindings = projection.get("bindings")
    semantics = projection.get("semantics")
    inference_seconds = projection.get("inference_seconds")
    peak_memory = projection.get("peak_mlx_allocator_memory_bytes")
    if (
        projection.get("schema")
        != "sunofriend.private-melroformer-worker-resource-projection.v1"
        or projection.get("status") != "worker_measurement_projected_not_benchmark"
        or projection.get("candidate_id") != "mlx-melroformer-kim-vocal-2"
        or projection_sha256 != _document_sha256(payload)
        or not isinstance(bindings, Mapping)
        or bindings.get("request_sha256") != receipt.get("request_sha256")
        or bindings.get("worker_result_sha256")
        != receipt.get("worker_result_sha256")
        or bindings.get("child_result_sha256")
        != receipt.get("child_result_sha256")
        or projection.get("device") not in {"cpu", "gpu"}
        or type(projection.get("frames")) is not int
        or not 4_096 <= projection["frames"] <= 661_500
        or type(projection.get("chunk_count")) is not int
        or not 1 <= projection["chunk_count"] <= 3
        or not _positive_number(inference_seconds)
        or float(inference_seconds) > 3_600.0
        or type(peak_memory) is not int
        or not 1 <= peak_memory <= 64 * 1024**3
        or semantics
        != {
            "inference_time_scope": "worker_model_calls_only",
            "memory_scope": "mlx_allocator_peak_not_process_rss",
            "benchmark": False,
        }
    ):
        raise ValueError("private full-song worker resource projection differs")
    return {
        "chunk_index": chunk_index,
        "device": projection["device"],
        "frames": projection["frames"],
        "chunk_count": projection["chunk_count"],
        "inference_seconds": round(float(inference_seconds), 6),
        "peak_mlx_allocator_memory_bytes": peak_memory,
        "projection_sha256": projection_sha256,
    }


def _worker_resource_summary(
    observations: list[dict[str, Any]],
    *,
    selected_attempt_count: int,
    missing_count: int,
) -> dict[str, Any]:
    complete = len(observations) == selected_attempt_count and missing_count == 0
    result: dict[str, Any] = {
        "policy": "parent-bound-worker-resource-projection-v1",
        "benchmark": False,
        "complete_for_selected_attempts": complete,
        "observed_attempt_count": len(observations),
        "missing_attempt_count": missing_count,
        "peak_process_rss_observed": False,
        "memory_scope": "mlx_allocator_peak_not_process_rss",
        "chunks": observations,
    }
    if observations:
        inference = [item["inference_seconds"] for item in observations]
        memory = [item["peak_mlx_allocator_memory_bytes"] for item in observations]
        result.update(
            {
                "inference_seconds": _summary(inference),
                "summed_inference_seconds": round(math.fsum(inference), 6),
                "peak_mlx_allocator_memory_bytes": _summary(memory),
                "maximum_peak_mlx_allocator_memory_bytes": max(memory),
            }
        )
    return result


def _native_resource_observation(
    chunk_index: int,
    receipt: Mapping[str, Any],
    projection_value: object,
) -> dict[str, Any]:
    projection = (
        dict(projection_value) if isinstance(projection_value, Mapping) else {}
    )
    payload = dict(projection)
    projection_sha256 = payload.pop("projection_sha256", None)
    bindings = projection.get("bindings")
    semantics = projection.get("semantics")
    peak_rss = projection.get("peak_process_rss_bytes")
    peak_unified = projection.get("peak_total_unified_memory_bytes")
    peak_neural = projection.get("peak_neural_footprint_bytes")
    if (
        projection.get("schema")
        != "sunofriend.private-melroformer-native-resource-projection.v1"
        or projection.get("status")
        != "exact_reap_process_resources_projected_not_benchmark"
        or projection_sha256 != _document_sha256(payload)
        or not isinstance(bindings, Mapping)
        or bindings.get("request_sha256") != receipt.get("request_sha256")
        or bindings.get("worker_result_sha256")
        != receipt.get("worker_result_sha256")
        or bindings.get("child_result_sha256")
        != receipt.get("child_result_sha256")
        or type(peak_rss) is not int
        or not 1 <= peak_rss <= 128 * 1024**3
        or type(peak_unified) is not int
        or not 1 <= peak_unified <= 128 * 1024**3
        or type(peak_neural) is not int
        or not 0 <= peak_neural <= 128 * 1024**3
        or semantics
        != {
            "process_rss": "wait4_ru_maxrss_darwin_bytes",
            "total_unified_memory": (
                "proc_pid_rusage_v6_lifetime_max_phys_footprint"
            ),
            "scope": "exact_owned_worker_process_lifetime",
            "pid_retained": False,
            "benchmark": False,
        }
    ):
        raise ValueError("private full-song native resource projection differs")
    return {
        "chunk_index": chunk_index,
        "peak_process_rss_bytes": peak_rss,
        "peak_total_unified_memory_bytes": peak_unified,
        "peak_neural_footprint_bytes": peak_neural,
        "projection_sha256": projection_sha256,
    }


def _native_resource_summary(
    observations: list[dict[str, Any]],
    *,
    selected_attempt_count: int,
    missing_count: int,
) -> dict[str, Any]:
    complete = len(observations) == selected_attempt_count and missing_count == 0
    result: dict[str, Any] = {
        "policy": "exact-owned-worker-darwin-resource-projection-v1",
        "benchmark": False,
        "complete_for_selected_attempts": complete,
        "observed_attempt_count": len(observations),
        "missing_attempt_count": missing_count,
        "pid_retained": False,
        "chunks": observations,
    }
    if observations:
        rss = [item["peak_process_rss_bytes"] for item in observations]
        unified = [
            item["peak_total_unified_memory_bytes"] for item in observations
        ]
        neural = [item["peak_neural_footprint_bytes"] for item in observations]
        result.update(
            {
                "peak_process_rss_bytes": _summary(rss),
                "maximum_peak_process_rss_bytes": max(rss),
                "peak_total_unified_memory_bytes": _summary(unified),
                "maximum_peak_total_unified_memory_bytes": max(unified),
                "peak_neural_footprint_bytes": _summary(neural),
                "maximum_peak_neural_footprint_bytes": max(neural),
            }
        )
    return result


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("private full-song resource observation is empty")
    ordered = sorted(float(value) for value in values)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "minimum": round(ordered[0], 6),
        "maximum": round(ordered[-1], 6),
        "mean": round(math.fsum(ordered) / len(ordered), 6),
        "p95_nearest_rank": round(ordered[p95_index], 6),
    }


def _tree_inventory(root: Path, label: str) -> dict[str, int]:
    _require_private_directory(root, label)
    regular_files = 0
    directories = 1
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        try:
            state = path.lstat()
        except OSError as error:
            raise ValueError(f"{label} changed") from error
        if stat.S_ISLNK(state.st_mode):
            raise ValueError(f"{label} contains a symbolic link")
        if state.st_uid != os.geteuid() or stat.S_IMODE(state.st_mode) & 0o077:
            raise ValueError(f"{label} contains non-private evidence")
        if stat.S_ISDIR(state.st_mode):
            directories += 1
        elif stat.S_ISREG(state.st_mode) and state.st_nlink == 1:
            regular_files += 1
            total_bytes += state.st_size
        else:
            raise ValueError(f"{label} contains unsupported evidence")
    return {
        "directory_count": directories,
        "regular_file_count": regular_files,
        "regular_file_bytes": total_bytes,
    }


def _positive_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _nonnegative_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} differs") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} differs")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.chmod(0o600)
        temporary.write_text(
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__: tuple[str, ...] = ()
