"""Freeze a controlled full-song resource benchmark before model execution.

This private-development contract binds one sealed full-song plan, the exact
Kim checkpoint and runtime executable, the current Mac class, fixed resource
ceilings and a bounded set of fresh serial repetitions.  It starts no model
and cannot turn later observations into acceptance by itself.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import _load_verified_plan
from ._separation_full_song_resource import (
    _require_private_regular,
    _write_json_atomic,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


SCHEMA = "sunofriend.private-separation-full-song-resource-benchmark-plan.v1"
STATUS = "controlled_resource_benchmark_planned_not_executed"
PROTOCOL = "fresh-process-resource-measurement-v1"
DEFAULT_REPETITIONS = 3
MAXIMUM_REPETITIONS = 10
WALL_TIME_SECONDS_PER_AUDIO_MINUTE_MAX = 120.0
SINGLE_SONG_WALL_TIME_SECONDS_MAX = 900.0
PEAK_UNIFIED_MEMORY_GIB_MAX = 12.0

_OS_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?")
_OS_BUILD_RE = re.compile(r"[0-9]{2}[A-Z][0-9]+[a-z]?")
_RUNTIME_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
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
CommandRunner = Callable[[Sequence[str]], str]


def _prepare_private_full_song_resource_benchmark_plan(
    plan_report_path: str | Path,
    *,
    runtime_launcher_path: str | Path,
    checkpoint_path: str | Path,
    out: str | Path,
    device: str = "gpu",
    repetitions: int = DEFAULT_REPETITIONS,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Write one path-free, non-executing repeated-resource plan."""

    if device not in {"cpu", "gpu"}:
        raise ValueError("resource benchmark device must be cpu or gpu")
    if (
        isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or not DEFAULT_REPETITIONS <= repetitions <= MAXIMUM_REPETITIONS
    ):
        raise ValueError(
            f"resource benchmark repetitions must be {DEFAULT_REPETITIONS}.."
            f"{MAXIMUM_REPETITIONS}"
        )

    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    runtime = _resolved_regular_file(runtime_launcher_path, "runtime launcher")
    checkpoint = _resolved_regular_file(checkpoint_path, "Kim checkpoint")
    runtime_claim = _file_claim(runtime)
    checkpoint_claim = _file_claim(checkpoint)
    if (
        checkpoint_claim["bytes"] != CONVERSION_CHECKPOINT_BYTES
        or checkpoint_claim["sha256"] != CONVERSION_CHECKPOINT_SHA256
    ):
        raise ValueError("Kim checkpoint identity differs")

    machine = _probe_machine(
        runtime,
        command_runner=command_runner or _run_probe_command,
    )
    if _file_claim(runtime) != runtime_claim:
        raise ValueError("runtime launcher changed during benchmark planning")
    if _file_claim(checkpoint) != checkpoint_claim:
        raise ValueError("Kim checkpoint changed during benchmark planning")
    if PEAK_UNIFIED_MEMORY_GIB_MAX > machine["unified_memory_gib"]:
        raise ValueError("resource ceiling exceeds the observed unified memory")

    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(
            f"private full-song resource benchmark plan already exists: {output}"
        )

    song_seconds = plan["canonical_clock"]["frames"] / 44_100
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_report_sha256": plan_sha256,
            "plan_document_sha256": plan["document_sha256"],
            "canonical_pcm24_int32_sequence_sha256": plan["canonical_clock"][
                "pcm24_int32_sequence_sha256"
            ],
            "checkpoint_sha256": checkpoint_claim["sha256"],
            "checkpoint_bytes": checkpoint_claim["bytes"],
            "runtime_executable_sha256": runtime_claim["sha256"],
            "runtime_executable_bytes": runtime_claim["bytes"],
        },
        "candidate": {
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "device": device,
        },
        "source_clock": {
            "sample_rate": 44_100,
            "frames": plan["canonical_clock"]["frames"],
            "duration_seconds": round(song_seconds, 9),
            "chunk_count": len(plan["chunks"]),
        },
        "machine_class": machine,
        "benchmark_contract": {
            "protocol": PROTOCOL,
            "repetitions": repetitions,
            "fresh_process_per_repetition": True,
            "fresh_execution_root_per_repetition": True,
            "serial_non_overlapping_execution_required": True,
            "same_plan_checkpoint_runtime_device_and_machine_required": True,
            "operating_system_cache_controlled": False,
            "concurrent_load_permitted": False,
            "thresholds": {
                "wall_time_seconds_per_audio_minute_max": (
                    WALL_TIME_SECONDS_PER_AUDIO_MINUTE_MAX
                ),
                "single_song_wall_time_seconds_max": (
                    SINGLE_SONG_WALL_TIME_SECONDS_MAX
                ),
                "peak_unified_memory_gib_max": PEAK_UNIFIED_MEMORY_GIB_MAX,
                "timeout_is_failure": True,
                "oom_is_failure": True,
            },
            "required_measurements": {
                "parent_observed_full_song_wall_time": True,
                "worker_model_call_time": True,
                "peak_process_rss": True,
                "peak_mlx_allocator_memory": True,
                "peak_total_unified_memory": True,
                "thermal_state_before_and_after": True,
                "timeout_and_oom_outcome": True,
            },
            "repetition_slots": [
                {
                    "index": index,
                    "status": "not_run",
                    "execution_report_sha256": None,
                    "stitch_report_sha256": None,
                    "resource_observation_sha256": None,
                }
                for index in range(1, repetitions + 1)
            ],
        },
        "coverage": {
            "thresholds_frozen_before_repetitions": True,
            "current_machine_profile_observed": True,
            "runtime_and_checkpoint_rechecked_after_probe": True,
            "required_16_gib_acceptance_class_observed": (
                machine["unified_memory_gib"] == 16
            ),
            "controlled_repetitions_observed": 0,
            "all_required_measurements_observed": False,
        },
        "readiness": {
            "benchmark_plan_complete": True,
            "controlled_repeated_benchmark_complete": False,
            "resource_envelope_accepted": False,
            "publication_ready": False,
        },
        "limitations": [
            "This document freezes a benchmark contract; it contains no run result.",
            "The current machine class alone cannot satisfy the required 16 GiB class unless it is exactly 16 GiB.",
            "MLX allocator peak is not process RSS or total unified-memory usage.",
            "The operating-system cache remains uncontrolled and must be disclosed.",
            "Energy and concurrent-load experiments are outside this first acceptance benchmark.",
            "A later verifier must reject missing, overlapping, mixed-identity or incomplete repetitions.",
        ],
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
    }
    report["document_sha256"] = _document_sha256(report)
    _write_json_atomic(output, report)
    return {**report, "report": str(output)}


def _load_verified_resource_benchmark_plan(
    value: str | Path,
) -> tuple[Path, dict[str, Any], str]:
    """Load one exact inert benchmark plan and reject contract drift."""

    path = Path(value).expanduser().absolute()
    _require_private_regular(path, "private resource benchmark plan")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private resource benchmark plan JSON differs") from error
    contract = document.get("benchmark_contract") if isinstance(document, dict) else None
    bindings = document.get("bindings") if isinstance(document, dict) else None
    candidate = document.get("candidate") if isinstance(document, dict) else None
    source_clock = document.get("source_clock") if isinstance(document, dict) else None
    machine = document.get("machine_class") if isinstance(document, dict) else None
    slots = contract.get("repetition_slots") if isinstance(contract, dict) else None
    repetitions = contract.get("repetitions") if isinstance(contract, dict) else None
    if (
        document.get("schema") != SCHEMA
        or document.get("status") != STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("evidence_scope") != "private_development_only"
        or not isinstance(bindings, dict)
        or set(bindings)
        != {
            "plan_report_sha256",
            "plan_document_sha256",
            "canonical_pcm24_int32_sequence_sha256",
            "checkpoint_sha256",
            "checkpoint_bytes",
            "runtime_executable_sha256",
            "runtime_executable_bytes",
        }
        or not all(
            isinstance(bindings[key], str) and re.fullmatch(r"[0-9a-f]{64}", bindings[key])
            for key in (
                "plan_report_sha256",
                "plan_document_sha256",
                "canonical_pcm24_int32_sequence_sha256",
                "checkpoint_sha256",
                "runtime_executable_sha256",
            )
        )
        or bindings.get("checkpoint_sha256") != CONVERSION_CHECKPOINT_SHA256
        or bindings.get("checkpoint_bytes") != CONVERSION_CHECKPOINT_BYTES
        or type(bindings.get("runtime_executable_bytes")) is not int
        or bindings["runtime_executable_bytes"] <= 0
        or not isinstance(source_clock, dict)
        or set(source_clock)
        != {"sample_rate", "frames", "duration_seconds", "chunk_count"}
        or source_clock.get("sample_rate") != 44_100
        or type(source_clock.get("frames")) is not int
        or source_clock["frames"] <= 0
        or type(source_clock.get("chunk_count")) is not int
        or source_clock["chunk_count"] <= 0
        or not isinstance(source_clock.get("duration_seconds"), (int, float))
        or isinstance(source_clock.get("duration_seconds"), bool)
        or not math.isclose(
            float(source_clock["duration_seconds"]),
            source_clock["frames"] / 44_100,
            abs_tol=1e-9,
        )
        or not isinstance(machine, dict)
        or set(machine)
        != {
            "probe_policy",
            "class_id",
            "os_name",
            "os_version",
            "os_build",
            "runtime",
            "architecture",
            "hardware_family",
            "unified_memory_gib",
        }
        or machine.get("probe_policy") != "fixed-local-macos-machine-probe-v1"
        or machine.get("os_name") != "macOS"
        or not isinstance(machine.get("os_version"), str)
        or not _OS_VERSION_RE.fullmatch(machine["os_version"])
        or not isinstance(machine.get("os_build"), str)
        or not _OS_BUILD_RE.fullmatch(machine["os_build"])
        or not isinstance(machine.get("runtime"), str)
        or not re.fullmatch(r"cpython-[0-9]+\.[0-9]+\.[0-9]+", machine["runtime"])
        or machine.get("architecture") != "arm64"
        or machine.get("hardware_family") != "Apple silicon"
        or type(machine.get("unified_memory_gib")) is not int
        or not 8 <= machine["unified_memory_gib"] <= 512
        or machine.get("class_id")
        != f"apple-silicon-{machine['unified_memory_gib']}gib"
        or not isinstance(contract, dict)
        or contract.get("protocol") != PROTOCOL
        or type(repetitions) is not int
        or not DEFAULT_REPETITIONS <= repetitions <= MAXIMUM_REPETITIONS
        or not isinstance(slots, list)
        or len(slots) != repetitions
        or any(
            slot
            != {
                "index": index,
                "status": "not_run",
                "execution_report_sha256": None,
                "stitch_report_sha256": None,
                "resource_observation_sha256": None,
            }
            for index, slot in enumerate(slots, start=1)
        )
        or contract.get("thresholds")
        != {
            "wall_time_seconds_per_audio_minute_max": (
                WALL_TIME_SECONDS_PER_AUDIO_MINUTE_MAX
            ),
            "single_song_wall_time_seconds_max": SINGLE_SONG_WALL_TIME_SECONDS_MAX,
            "peak_unified_memory_gib_max": PEAK_UNIFIED_MEMORY_GIB_MAX,
            "timeout_is_failure": True,
            "oom_is_failure": True,
        }
        or contract.get("required_measurements")
        != {
            "parent_observed_full_song_wall_time": True,
            "worker_model_call_time": True,
            "peak_process_rss": True,
            "peak_mlx_allocator_memory": True,
            "peak_total_unified_memory": True,
            "thermal_state_before_and_after": True,
            "timeout_and_oom_outcome": True,
        }
        or contract.get("fresh_process_per_repetition") is not True
        or contract.get("fresh_execution_root_per_repetition") is not True
        or contract.get("serial_non_overlapping_execution_required") is not True
        or contract.get("same_plan_checkpoint_runtime_device_and_machine_required")
        is not True
        or contract.get("operating_system_cache_controlled") is not False
        or contract.get("concurrent_load_permitted") is not False
        or not isinstance(candidate, dict)
        or candidate
        != {
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "device": candidate.get("device"),
        }
        or candidate.get("device") not in {"cpu", "gpu"}
        or document.get("coverage")
        != {
            "thresholds_frozen_before_repetitions": True,
            "current_machine_profile_observed": True,
            "runtime_and_checkpoint_rechecked_after_probe": True,
            "required_16_gib_acceptance_class_observed": (
                machine["unified_memory_gib"] == 16
            ),
            "controlled_repetitions_observed": 0,
            "all_required_measurements_observed": False,
        }
        or document.get("readiness")
        != {
            "benchmark_plan_complete": True,
            "controlled_repeated_benchmark_complete": False,
            "resource_envelope_accepted": False,
            "publication_ready": False,
        }
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != _FALSE_EFFECTS
    ):
        raise ValueError("private resource benchmark plan identity differs")
    raw = path.read_bytes()
    if b'"path"' in raw or b'"paths"' in raw or b'"/' in raw or b"://" in raw:
        raise ValueError("private resource benchmark plan retained a path")
    return path, document, _sha256(path)


def _probe_machine(
    runtime_launcher: Path,
    *,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    product_version = command_runner(("/usr/bin/sw_vers", "-productVersion")).strip()
    build = command_runner(("/usr/bin/sw_vers", "-buildVersion")).strip()
    architecture = command_runner(("/usr/bin/uname", "-m")).strip()
    memory_text = command_runner(("/usr/sbin/sysctl", "-n", "hw.memsize")).strip()
    runtime_text = command_runner(
        (
            str(runtime_launcher),
            "-I",
            "-c",
            (
                "import json,platform;"
                "print(json.dumps([platform.python_implementation(),"
                "platform.python_version()]))"
            ),
        )
    ).strip()
    try:
        implementation, runtime_version = json.loads(runtime_text)
        memory_bytes = int(memory_text)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("resource benchmark machine probe differs") from error
    gib = memory_bytes / 1024**3
    if (
        not _OS_VERSION_RE.fullmatch(product_version)
        or not _OS_BUILD_RE.fullmatch(build)
        or architecture != "arm64"
        or implementation != "CPython"
        or not isinstance(runtime_version, str)
        or not _RUNTIME_VERSION_RE.fullmatch(runtime_version)
        or memory_bytes < 8 * 1024**3
        or memory_bytes > 512 * 1024**3
        or not math.isclose(gib, round(gib), abs_tol=1e-9)
    ):
        raise ValueError("resource benchmark machine probe differs")
    unified_memory_gib = round(gib)
    return {
        "probe_policy": "fixed-local-macos-machine-probe-v1",
        "class_id": f"apple-silicon-{unified_memory_gib}gib",
        "os_name": "macOS",
        "os_version": product_version,
        "os_build": build,
        "runtime": f"cpython-{runtime_version}",
        "architecture": architecture,
        "hardware_family": "Apple silicon",
        "unified_memory_gib": unified_memory_gib,
    }


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


def _resolved_regular_file(value: str | Path, label: str) -> Path:
    source = Path(value).expanduser().absolute()
    try:
        resolved = source.resolve(strict=True)
        state = resolved.stat()
    except OSError as error:
        raise ValueError(f"{label} differs") from error
    if not stat.S_ISREG(state.st_mode) or state.st_nlink < 1:
        raise ValueError(f"{label} differs")
    return resolved


def _file_claim(path: Path) -> dict[str, int | str]:
    try:
        state = path.stat()
    except OSError as error:
        raise ValueError("resource benchmark input changed") from error
    return {
        "bytes": state.st_size,
        "device": state.st_dev,
        "inode": state.st_ino,
        "modified_ns": state.st_mtime_ns,
        "sha256": _sha256(path),
    }


__all__: tuple[str, ...] = ()
