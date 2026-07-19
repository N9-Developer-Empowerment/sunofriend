"""Strict one-variable comparisons over immutable MuScriptor runs.

The comparator never launches a worker and never edits a candidate.  It
re-verifies two repeatable fresh-process arms, permits only the declared beam
size change, and publishes path-free diagnostic evidence for a later listening
decision.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ai_benchmark import build_ai_performance_benchmark
from .ai_matrix import build_ai_candidate_matrix


AI_SETTING_COMPARISON_SCHEMA = "sunofriend.ai-setting-comparison.v1"

_CONTROL_BEAM_SIZE = 1
_CHALLENGER_BEAM_SIZE = 2
_CONTROL_STRATEGY = "greedy"
_CHALLENGER_STRATEGY = "beam-search"
_BOUNDARY_TOLERANCE_MS = 80.0
_PATH_REQUEST_FIELDS = frozenset(
    {
        "model_path",
        "model_config_path",
        "model_sha256",
        "model_config_sha256",
    }
)
_REQUIRED_CACHE_REGIME = {
    "worker_process": "fresh-per-repetition",
    "model_reused": False,
    "application_content_cache": False,
    "operating_system_file_cache": "uncontrolled",
    "cold_start_claimed": False,
}
_TRACKED_OUTPUT_ARTIFACTS = (
    "candidate.raw.json",
    "candidate.json",
    "candidate.mid",
    "candidate.expression.json",
    "candidate.expression.mid",
    "candidate.quality.json",
    "candidate.programs.json",
)
_PERFORMANCE_FIELDS = (
    "pipeline_elapsed_seconds",
    "pipeline_real_time_factor",
    "worker_subprocess_elapsed_seconds",
    "worker_subprocess_real_time_factor",
    "transcription_real_time_factor",
    "performance_audio_preparation_seconds",
    "performance_model_load_seconds",
    "performance_transcription_seconds",
    "performance_worker_total_seconds",
    "performance_time_to_first_note_start_seconds",
    "performance_time_to_first_completed_note_seconds",
    "performance_time_to_first_completed_chunk_seconds",
    "performance_peak_process_rss_bytes",
)


def write_ai_setting_comparison(
    control_run_dirs: Sequence[str | Path],
    challenger_run_dirs: Sequence[str | Path],
    output_path: str | Path,
    *,
    boundary_tolerance_ms: float = _BOUNDARY_TOLERANCE_MS,
) -> dict[str, Any]:
    """Build and atomically publish a report at a fresh, external path."""

    control = _input_paths(control_run_dirs, arm="control")
    challenger = _input_paths(challenger_run_dirs, arm="challenger")
    all_inputs = (*control, *challenger)
    _require_globally_unique(all_inputs)

    output = Path(output_path).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"AI setting comparison already exists: {output}")
    output_resolved = output.resolve(strict=False)
    for run_dir in all_inputs:
        if output_resolved == run_dir or output_resolved.is_relative_to(run_dir):
            raise ValueError(
                "AI setting comparison output must not be inside an input run"
            )

    report = build_ai_setting_comparison(
        control,
        challenger,
        boundary_tolerance_ms=boundary_tolerance_ms,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                report,
                handle,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise FileExistsError(
                f"AI setting comparison already exists: {output}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return report


def build_ai_setting_comparison(
    control_run_dirs: Sequence[str | Path],
    challenger_run_dirs: Sequence[str | Path],
    *,
    boundary_tolerance_ms: float = _BOUNDARY_TOLERANCE_MS,
) -> dict[str, Any]:
    """Compare repeatable beam-1 and beam-2 fresh-process MuScriptor arms."""

    tolerance = _positive_finite(boundary_tolerance_ms, "boundary_tolerance_ms")
    control_paths = _input_paths(control_run_dirs, arm="control")
    challenger_paths = _input_paths(challenger_run_dirs, arm="challenger")
    _require_globally_unique((*control_paths, *challenger_paths))

    control = _build_arm(
        "control",
        control_paths,
        expected_beam_size=_CONTROL_BEAM_SIZE,
        expected_strategy=_CONTROL_STRATEGY,
        boundary_tolerance_ms=tolerance,
    )
    challenger = _build_arm(
        "challenger",
        challenger_paths,
        expected_beam_size=_CHALLENGER_BEAM_SIZE,
        expected_strategy=_CHALLENGER_STRATEGY,
        boundary_tolerance_ms=tolerance,
    )

    _require_shared_evidence(control, challenger)
    shared_execution = _require_only_beam_change(
        control["full_execution"],
        challenger["full_execution"],
    )
    _require_request_contract(control, challenger)
    execution_order = _global_execution_order(control, challenger)

    control_public = _public_arm(control)
    challenger_public = _public_arm(challenger)
    output_comparison = _compare_outputs(
        control_public,
        challenger_public,
        control_notes=control["representative_notes"],
        challenger_notes=challenger["representative_notes"],
        overlap_tolerance_ms=tolerance,
    )
    output_changed = bool(output_comparison["output_changed"])

    shared = {
        "source_sha256": control["benchmark"]["source_sha256"],
        "excerpt": control["benchmark"]["excerpt"],
        "bpm": control["benchmark"]["bpm"],
        "roles": control["benchmark"]["roles"],
        "device": control["benchmark"]["device"],
        "checkpoint_sha256": control["benchmark"]["checkpoint_sha256"],
        "model_config_sha256": control["benchmark"]["model_config_sha256"],
        "model_version": control["benchmark"]["model_version"],
        "worker_sha256": control["benchmark"]["worker_sha256"],
        "runtime_profile": control["benchmark"]["runtime_profile"],
        "model_size": shared_execution.get("model_size"),
        "cache_regime": deepcopy(_REQUIRED_CACHE_REGIME),
        "request_options_without_paths_or_beam_sha256": control[
            "request_contract_without_beam_sha256"
        ],
    }
    report = {
        "schema": AI_SETTING_COMPARISON_SCHEMA,
        "status": "verified",
        "backend": "muscriptor",
        "setting_change": {
            "semantic_setting": "beam_size",
            "field": "execution.decoding.beam_size",
            "control": _CONTROL_BEAM_SIZE,
            "challenger": _CHALLENGER_BEAM_SIZE,
            "derived_change": {
                "field": "execution.decoding.strategy",
                "control": _CONTROL_STRATEGY,
                "challenger": _CHALLENGER_STRATEGY,
            },
            "changed_semantic_field_count": 1,
            "all_other_execution_fields_equal": True,
        },
        "shared_evidence": shared,
        "execution_order": execution_order,
        "execution_order_caveat": (
            "Runs were sequential and non-overlapping, but order was not randomized; "
            "the operating-system file cache is uncontrolled. Timing differences are "
            "observed diagnostics, not causal speed evidence."
        ),
        "arms": {
            "control": control_public,
            "challenger": challenger_public,
        },
        "comparison": {
            "outputs": output_comparison,
            "labels": _compare_labels(control_public, challenger_public),
            "quality": _compare_quality(control_public, challenger_public),
            "five_second_boundaries": _compare_boundaries(
                control_public, challenger_public
            ),
            "performance": _compare_performance(control_public, challenger_public),
        },
        "effects": {
            "raw_candidates_mutated": False,
            "midi_notes_mutated": 0,
            "selection_changed": False,
            "promotion_allowed": False,
            "listening_review_required_before_default_change": output_changed,
        },
        "privacy": (
            "The report omits local paths, commands, timestamps and caller run IDs, "
            "but content hashes and runtime identity may still identify private "
            "material or a machine. Path-free does not mean anonymous or approved "
            "for publication."
        ),
        "interpretation": (
            "Read-only one-variable diagnostic. Candidate JSON hashes include "
            "execution provenance; note-payload and MIDI equality describe musical "
            "output more directly. No arm is a winner, and no default or preset may "
            "change without a same-renderer, same-patch, level-matched listening "
            "review when the musical output differs."
        ),
    }
    # Prove the public document itself is strict JSON before returning it.
    json.dumps(report, sort_keys=True, allow_nan=False)
    return report


def _build_arm(
    arm: str,
    paths: Sequence[Path],
    *,
    expected_beam_size: int,
    expected_strategy: str,
    boundary_tolerance_ms: float,
) -> dict[str, Any]:
    benchmark = build_ai_performance_benchmark(paths)
    if benchmark.get("backend") != "muscriptor":
        raise ValueError("AI setting comparison requires MuScriptor runs")
    count = int(benchmark.get("repetition_count", 0))
    if count < 2:
        raise ValueError(f"AI setting comparison needs at least two {arm} runs")
    evidence = benchmark.get("execution_evidence")
    if not isinstance(evidence, Mapping) or (
        evidence.get("explicit_current_count") != count
        or evidence.get("legacy_v1_count") != 0
    ):
        raise ValueError(
            "AI setting comparison accepts only explicit current fresh-process runs; "
            "legacy evidence is not accepted"
        )
    if benchmark.get("cache_regime") != _REQUIRED_CACHE_REGIME:
        raise ValueError(
            "AI setting comparison accepts only independent cache-disabled fresh runs"
        )
    if any(
        repetition.get("performance_status") != "verified"
        for repetition in benchmark.get("repetitions", ())
    ):
        raise ValueError(
            "AI setting comparison requires verified performance evidence for every run"
        )
    repeatability = benchmark.get("repeatability")
    if not isinstance(repeatability, Mapping) or not all(
        isinstance(repeatability.get(name), Mapping)
        and repeatability[name].get("all_identical") is True
        for name in ("candidate_json", "candidate_midi", "note_count")
    ):
        raise ValueError(
            f"AI setting comparison {arm} outputs are not exactly repeatable"
        )

    ordered_paths = _paths_in_benchmark_order(paths, benchmark)
    full_executions = [_strict_current_execution(path) for path in ordered_paths]
    if any(value != full_executions[0] for value in full_executions[1:]):
        raise ValueError(
            f"AI setting comparison {arm} full execution settings are not "
            "exactly repeatable"
        )
    lanes = [
        (f"M3-{arm}-{index:03d}", path)
        for index, path in enumerate(ordered_paths, start=1)
    ]
    matrix = build_ai_candidate_matrix(
        lanes, boundary_tolerance_ms=boundary_tolerance_ms
    )
    execution = benchmark.get("execution")
    if matrix.get("execution") != execution:
        raise ValueError(
            f"AI setting comparison {arm} matrix and benchmark execution disagree"
        )
    decoding = execution.get("decoding") if isinstance(execution, Mapping) else None
    if not isinstance(decoding, Mapping) or (
        decoding.get("beam_size") != expected_beam_size
        or decoding.get("strategy") != expected_strategy
        or decoding.get("use_sampling") is not False
    ):
        raise ValueError(
            "AI setting comparison v1 requires control beam 1/greedy and "
            "challenger beam 2/beam-search with sampling disabled"
        )

    matrix_rows = list(matrix.get("lanes", ()))
    if len(matrix_rows) != count:
        raise ValueError(f"AI setting comparison {arm} matrix is incomplete")
    musical_fields = (
        "candidate_json_sha256",
        "candidate_midi_sha256",
        "requested_labels",
        "detected_labels",
        "missing_requested_labels",
        "unexpected_labels",
        "instrument_counts",
        "note_count",
        "quality",
        "per_instrument",
        "five_second_boundaries",
    )
    for field in musical_fields:
        values = {_canonical_json(row.get(field)) for row in matrix_rows}
        if len(values) != 1:
            raise ValueError(
                f"AI setting comparison {arm} {field} is not exactly repeatable"
            )

    artifacts = [_tracked_artifacts(path) for path in ordered_paths]
    artifact_names = set(artifacts[0])
    if any(set(item) != artifact_names for item in artifacts[1:]):
        raise ValueError(
            f"AI setting comparison {arm} derived artifact sets are inconsistent"
        )
    artifact_repeatability: dict[str, dict[str, Any]] = {}
    for name in sorted(artifact_names):
        hashes = [item[name] for item in artifacts]
        identical = len(set(hashes)) == 1
        # Timing evidence is intentionally excluded from tracked outputs. Every
        # tracked musical/derived artifact must be stable inside an arm.
        if not identical:
            raise ValueError(
                f"AI setting comparison {arm} {name} is not exactly repeatable"
            )
        artifact_repeatability[name] = {
            "sha256": hashes[0],
            "all_identical": True,
        }

    note_payload_hashes = [_note_payload_hash(path) for path in ordered_paths]
    if len(set(note_payload_hashes)) != 1:
        raise ValueError(
            f"AI setting comparison {arm} note payload is not exactly repeatable"
        )
    request_documents = [_request_contract(path) for path in ordered_paths]
    request_contracts = {_canonical_json(value) for value in request_documents}
    if len(request_contracts) != 1:
        raise ValueError(
            f"AI setting comparison {arm} request options are not identical"
        )
    request_contract = request_documents[0]
    request_contract_without_beam = deepcopy(request_contract)
    request_contract_without_beam["options"].pop("beam_size", None)

    return {
        "arm": arm,
        "paths": ordered_paths,
        "benchmark": benchmark,
        # Kept internal: future execution fields may contain machine-local data.
        # The full mapping is used to prove that beam size is the only effective
        # cross-arm change, while the public report retains the path-free view.
        "full_execution": full_executions[0],
        "matrix": matrix,
        "representative": matrix_rows[0],
        "artifacts": artifact_repeatability,
        "note_payload_sha256": note_payload_hashes[0],
        "representative_notes": _candidate_notes(ordered_paths[0]),
        "request_contract": request_contract,
        "request_contract_without_beam_sha256": _canonical_hash(
            request_contract_without_beam
        ),
    }


def _public_arm(arm: Mapping[str, Any]) -> dict[str, Any]:
    benchmark = arm["benchmark"]
    representative = arm["representative"]
    performance = {
        name: deepcopy(benchmark["aggregates"][name])
        for name in _PERFORMANCE_FIELDS
        if name in benchmark["aggregates"]
    }
    return {
        "repetition_count": benchmark["repetition_count"],
        "execution": deepcopy(benchmark["execution"]),
        "repeatability": {
            **deepcopy(benchmark["repeatability"]),
            "note_payload": {"all_identical": True, "unique_count": 1},
            "tracked_artifacts": deepcopy(arm["artifacts"]),
        },
        "outputs": {
            "candidate_raw_sha256": arm["artifacts"]["candidate.raw.json"]["sha256"],
            "candidate_json_sha256": representative["candidate_json_sha256"],
            "note_payload_sha256": arm["note_payload_sha256"],
            "candidate_midi_sha256": representative["candidate_midi_sha256"],
            "note_count": representative["note_count"],
        },
        "labels": {
            "requested": deepcopy(representative["requested_labels"]),
            "detected": deepcopy(representative["detected_labels"]),
            "missing_requested": deepcopy(representative["missing_requested_labels"]),
            "unexpected": deepcopy(representative["unexpected_labels"]),
            "instrument_counts": deepcopy(representative["instrument_counts"]),
        },
        "quality": deepcopy(representative["quality"]),
        "per_instrument": deepcopy(representative["per_instrument"]),
        "five_second_boundaries": deepcopy(representative["five_second_boundaries"]),
        "performance": performance,
    }


def _require_shared_evidence(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> None:
    left = control["benchmark"]
    right = challenger["benchmark"]
    fields = (
        "backend",
        "checkpoint_sha256",
        "model_config_sha256",
        "model_version",
        "worker_sha256",
        "runtime_profile",
        "source_sha256",
        "excerpt",
        "bpm",
        "roles",
        "device",
        "cache_regime",
    )
    for field in fields:
        if left.get(field) != right.get(field):
            raise ValueError(
                "AI setting comparison arms differ outside beam_size: " + field
            )


def _require_only_beam_change(
    control_value: Any, challenger_value: Any
) -> dict[str, Any]:
    if not isinstance(control_value, Mapping) or not isinstance(
        challenger_value, Mapping
    ):
        raise ValueError("AI setting comparison requires pinned execution settings")
    control = deepcopy(dict(control_value))
    challenger = deepcopy(dict(challenger_value))
    for value, beam, strategy, arm in (
        (control, _CONTROL_BEAM_SIZE, _CONTROL_STRATEGY, "control"),
        (
            challenger,
            _CHALLENGER_BEAM_SIZE,
            _CHALLENGER_STRATEGY,
            "challenger",
        ),
    ):
        decoding = value.get("decoding")
        if not isinstance(decoding, dict):
            raise ValueError(f"AI setting comparison {arm} has no decoding settings")
        if decoding.get("beam_size") != beam or decoding.get("strategy") != strategy:
            raise ValueError(
                "AI setting comparison v1 requires exactly beam 1/greedy versus "
                "beam 2/beam-search"
            )
        if decoding.get("use_sampling") is not False:
            raise ValueError("AI setting comparison v1 does not accept sampling")
        decoding.pop("beam_size", None)
        decoding.pop("strategy", None)
    if control != challenger:
        raise ValueError(
            "AI setting comparison arms differ in an execution setting other than "
            "beam_size and its derived strategy"
        )
    return control


def _require_request_contract(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> None:
    left = deepcopy(control["request_contract"])
    right = deepcopy(challenger["request_contract"])
    left_options = left.get("options")
    right_options = right.get("options")
    if not isinstance(left_options, dict) or not isinstance(right_options, dict):
        raise ValueError("AI setting comparison request options are invalid")
    if left_options.pop("beam_size", None) != _CONTROL_BEAM_SIZE:
        raise ValueError("AI setting comparison control request must use beam_size 1")
    if right_options.pop("beam_size", None) != _CHALLENGER_BEAM_SIZE:
        raise ValueError(
            "AI setting comparison challenger request must use beam_size 2"
        )
    if left != right:
        raise ValueError(
            "AI setting comparison request options differ outside beam_size"
        )


def _global_execution_order(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> list[str]:
    windows: list[tuple[datetime, datetime, str, str]] = []
    run_ids: set[str] = set()
    for arm in (control, challenger):
        arm_name = str(arm["arm"])
        for repetition in arm["benchmark"]["repetitions"]:
            run_id = repetition.get("run_id")
            if not isinstance(run_id, str) or not run_id or run_id in run_ids:
                raise ValueError(
                    "AI setting comparison run IDs must be globally unique"
                )
            run_ids.add(run_id)
            start = _timestamp(repetition.get("started_at"), "started_at")
            end = _timestamp(repetition.get("completed_at"), "completed_at")
            if end < start:
                raise ValueError(
                    "AI setting comparison completed_at precedes started_at"
                )
            windows.append((start, end, arm_name, run_id))
    windows.sort(key=lambda value: (value[0], value[3]))
    for previous, current in zip(windows, windows[1:]):
        if current[0] < previous[1]:
            raise ValueError(
                "AI setting comparison execution windows overlap across arms"
            )
    return [arm for _start, _end, arm, _run_id in windows]


def _compare_outputs(
    control: Mapping[str, Any],
    challenger: Mapping[str, Any],
    *,
    control_notes: Sequence[Mapping[str, Any]],
    challenger_notes: Sequence[Mapping[str, Any]],
    overlap_tolerance_ms: float,
) -> dict[str, Any]:
    left = control["outputs"]
    right = challenger["outputs"]
    candidate_json_identical = (
        left["candidate_json_sha256"] == right["candidate_json_sha256"]
    )
    candidate_raw_identical = (
        left["candidate_raw_sha256"] == right["candidate_raw_sha256"]
    )
    note_payload_identical = left["note_payload_sha256"] == right["note_payload_sha256"]
    midi_identical = left["candidate_midi_sha256"] == right["candidate_midi_sha256"]
    tracked = {}
    control_artifacts = control["repeatability"]["tracked_artifacts"]
    challenger_artifacts = challenger["repeatability"]["tracked_artifacts"]
    if set(control_artifacts) != set(challenger_artifacts):
        raise ValueError("AI setting comparison tracked artifact sets differ")
    for name in sorted(control_artifacts):
        control_hash = control_artifacts[name]["sha256"]
        challenger_hash = challenger_artifacts[name]["sha256"]
        tracked[name] = {
            "control_sha256": control_hash,
            "challenger_sha256": challenger_hash,
            "identical": control_hash == challenger_hash,
        }
    auditionable_midi_identical = all(
        comparison["identical"]
        for name, comparison in tracked.items()
        if name.endswith(".mid")
    )
    expression_midi_identical = tracked["candidate.expression.mid"]["identical"]
    output_changed = not (note_payload_identical and auditionable_midi_identical)
    overlap = _representative_note_overlap(
        control_notes,
        challenger_notes,
        tolerance_ms=overlap_tolerance_ms,
    )
    return {
        "candidate_raw_identical": candidate_raw_identical,
        "candidate_json_identical": candidate_json_identical,
        "candidate_json_interpretation": (
            "Candidate JSON includes execution provenance, so a beam-only metadata "
            "difference is not itself a musical-output difference."
        ),
        "note_payload_identical": note_payload_identical,
        "candidate_midi_identical": midi_identical,
        "candidate_expression_midi_identical": expression_midi_identical,
        "all_auditionable_midi_identical": auditionable_midi_identical,
        "musical_output_identical": not output_changed,
        "output_changed": output_changed,
        "control_note_count": left["note_count"],
        "challenger_note_count": right["note_count"],
        "note_count_delta": right["note_count"] - left["note_count"],
        "tracked_artifacts": tracked,
        "same_pitch_label_onset_overlap": overlap,
    }


def _representative_note_overlap(
    control_notes: Sequence[Mapping[str, Any]],
    challenger_notes: Sequence[Mapping[str, Any]],
    *,
    tolerance_ms: float,
) -> dict[str, Any]:
    tolerance = tolerance_ms / 1000.0
    used: set[int] = set()
    matched = 0
    for note in control_notes:
        pitch = round(float(note["pitch"]))
        label = note.get("instrument") or "unlabelled"
        onset = float(note["start_seconds"])
        best_index = None
        best_distance = tolerance + 1.0
        for index, other in enumerate(challenger_notes):
            if index in used:
                continue
            if round(float(other["pitch"])) != pitch:
                continue
            if (other.get("instrument") or "unlabelled") != label:
                continue
            distance = abs(float(other["start_seconds"]) - onset)
            if distance <= tolerance and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is not None:
            used.add(best_index)
            matched += 1
    left_count = len(control_notes)
    right_count = len(challenger_notes)
    return {
        "tolerance_ms": tolerance_ms,
        "matched_notes": matched,
        "control_fraction": round(matched / left_count, 6)
        if left_count
        else (1.0 if right_count == 0 else 0.0),
        "challenger_fraction": round(matched / right_count, 6)
        if right_count
        else (1.0 if left_count == 0 else 0.0),
        "status": "diagnostic",
        "interpretation": (
            "Greedy one-to-one matches require the same rounded pitch, source label "
            f"and onset within {tolerance_ms:g} ms. Overlap is not an accuracy or "
            "preference score."
        ),
    }


def _compare_labels(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> dict[str, Any]:
    left = control["labels"]
    right = challenger["labels"]
    left_labels = set(left["detected"])
    right_labels = set(right["detected"])
    union = left_labels | right_labels
    counts = {}
    for label in sorted(union):
        control_count = int(left["instrument_counts"].get(label, 0))
        challenger_count = int(right["instrument_counts"].get(label, 0))
        counts[label] = {
            "control": control_count,
            "challenger": challenger_count,
            "delta": challenger_count - control_count,
        }
    return {
        "identical": left == right,
        "jaccard": round(len(left_labels & right_labels) / len(union), 6)
        if union
        else 1.0,
        "retained": sorted(left_labels & right_labels),
        "only_control": sorted(left_labels - right_labels),
        "only_challenger": sorted(right_labels - left_labels),
        "instrument_counts": counts,
    }


def _compare_quality(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> dict[str, Any]:
    left = control["quality"]
    right = challenger["quality"]
    left_codes = set(left.get("severe_codes", ()))
    right_codes = set(right.get("severe_codes", ()))
    metrics = {}
    left_metrics = left.get("metrics", {})
    right_metrics = right.get("metrics", {})
    for name in sorted(set(left_metrics) | set(right_metrics)):
        control_value = left_metrics.get(name)
        challenger_value = right_metrics.get(name)
        delta = None
        if _finite_number(control_value) and _finite_number(challenger_value):
            delta = round(float(challenger_value) - float(control_value), 6)
        metrics[name] = {
            "control": control_value,
            "challenger": challenger_value,
            "delta": delta,
        }
    return {
        "identical": left == right,
        "control_status": left.get("status"),
        "challenger_status": right.get("status"),
        "control_playable": left.get("playable"),
        "challenger_playable": right.get("playable"),
        "control_audition_safe": left.get("audition_safe"),
        "challenger_audition_safe": right.get("audition_safe"),
        "introduced_severe_codes": sorted(right_codes - left_codes),
        "resolved_severe_codes": sorted(left_codes - right_codes),
        "metrics": metrics,
        "interpretation": (
            "Automated quality metrics are diagnostics and cannot identify the more "
            "musically accurate arm."
        ),
    }


def _compare_boundaries(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> dict[str, Any]:
    left = control["five_second_boundaries"]
    right = challenger["five_second_boundaries"]
    if left.get("chunk_seconds") != right.get("chunk_seconds") or left.get(
        "tolerance_ms"
    ) != right.get("tolerance_ms"):
        raise ValueError("AI setting comparison boundary geometry differs")
    left_rows = list(left.get("boundaries", ()))
    right_rows = list(right.get("boundaries", ()))
    if len(left_rows) != len(right_rows):
        raise ValueError("AI setting comparison boundary counts differ")
    rows = []
    for left_row, right_row in zip(left_rows, right_rows):
        if left_row.get("local_seconds") != right_row.get("local_seconds"):
            raise ValueError("AI setting comparison boundary positions differ")
        control_onsets = int(left_row["onsets_within_tolerance"])
        challenger_onsets = int(right_row["onsets_within_tolerance"])
        control_crossings = int(left_row["notes_crossing_boundary"])
        challenger_crossings = int(right_row["notes_crossing_boundary"])
        rows.append(
            {
                "local_seconds": left_row["local_seconds"],
                "onsets": {
                    "control": control_onsets,
                    "challenger": challenger_onsets,
                    "delta": challenger_onsets - control_onsets,
                },
                "crossings": {
                    "control": control_crossings,
                    "challenger": challenger_crossings,
                    "delta": challenger_crossings - control_crossings,
                },
            }
        )
    return {
        "identical": left == right,
        "chunk_seconds": left.get("chunk_seconds"),
        "tolerance_ms": left.get("tolerance_ms"),
        "boundaries": rows,
        "interpretation": (
            "Boundary counts are diagnostics; an onset near a boundary may be "
            "musically correct."
        ),
    }


def _compare_performance(
    control: Mapping[str, Any], challenger: Mapping[str, Any]
) -> dict[str, Any]:
    left = control["performance"]
    right = challenger["performance"]
    fields = {}
    for name in sorted(set(left) | set(right)):
        control_summary = left.get(name)
        challenger_summary = right.get(name)
        control_median = (
            control_summary.get("median")
            if isinstance(control_summary, Mapping)
            else None
        )
        challenger_median = (
            challenger_summary.get("median")
            if isinstance(challenger_summary, Mapping)
            else None
        )
        delta = None
        ratio = None
        if _finite_number(control_median) and _finite_number(challenger_median):
            delta = round(float(challenger_median) - float(control_median), 6)
            if float(control_median) != 0:
                ratio = round(float(challenger_median) / float(control_median), 6)
        fields[name] = {
            "control": deepcopy(control_summary),
            "challenger": deepcopy(challenger_summary),
            "median_delta": delta,
            "challenger_to_control_median_ratio": ratio,
        }
    return {
        "fields": fields,
        "operating_system_file_cache": "uncontrolled",
        "order_randomized": False,
        "interpretation": (
            "Lower time or memory is only an observed resource difference. Run order "
            "and the operating-system cache prevent a causal speed claim, and resource "
            "use does not establish musical superiority."
        ),
    }


def _strict_current_execution(run_dir: Path) -> dict[str, Any]:
    """Return the complete execution mapping after proving fresh-run evidence.

    The generic benchmark publishes a deliberately path-free execution profile.
    A one-variable experiment must additionally compare every current and future
    execution field, so this verifier retains the full mapping internally only.
    """

    run = _read_json(run_dir / "run.json", "run manifest")
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("AI setting comparison run has no artifact manifest")
    cache_names = {"cache.entry.json", "cache.performance.json"}
    if cache_names.intersection(artifacts) or any(
        os.path.lexists(run_dir / name) for name in cache_names
    ):
        raise ValueError(
            "AI setting comparison accepts only cache-disabled fresh-process runs"
        )
    if (
        run.get("worker_execution_mode") != "fresh-subprocess"
        or run.get("worker_process_started_for_run") is not True
        or run.get("inference_executed_for_run") is not True
        or run.get("model_loaded_for_run") is not True
        or run.get("model_reused_from_prior_request") is not False
        or run.get("application_cache") is not None
        or run.get("worker_transport") is not None
    ):
        raise ValueError(
            "AI setting comparison accepts only explicit current, cache-disabled "
            "fresh-process runs without model reuse"
        )
    command = run.get("command")
    exit_code = run.get("exit_code")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
        or isinstance(exit_code, bool)
        or exit_code != 0
    ):
        raise ValueError(
            "AI setting comparison requires a successful fresh subprocess command"
        )
    execution = run.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("AI setting comparison run has no full execution settings")
    # Canonical encoding catches NaN/Infinity now instead of allowing an invalid
    # report or an equality comparison with surprising float semantics later.
    _canonical_json(execution)
    return deepcopy(dict(execution))


def _tracked_artifacts(run_dir: Path) -> dict[str, str]:
    run = _read_json(run_dir / "run.json", "run manifest")
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("AI setting comparison run has no artifact manifest")
    result: dict[str, str] = {}
    for name in _TRACKED_OUTPUT_ARTIFACTS:
        record = artifacts.get(name)
        if record is None:
            raise ValueError(
                f"AI setting comparison run is missing required current {name}"
            )
        if not isinstance(record, Mapping):
            raise ValueError(f"AI setting comparison {name} record is invalid")
        expected = (run_dir / name).resolve()
        raw_path = record.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"AI setting comparison {name} path is invalid")
        recorded = Path(raw_path)
        actual = (
            (run_dir / recorded).resolve()
            if not recorded.is_absolute()
            else recorded.resolve()
        )
        if actual != expected or not actual.is_file():
            raise ValueError(f"AI setting comparison {name} path disagrees")
        data = actual.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if record.get("bytes") != len(data) or record.get("sha256") != digest:
            raise ValueError(f"AI setting comparison {name} integrity check failed")
        result[name] = digest
    return result


def _note_payload_hash(run_dir: Path) -> str:
    return _canonical_hash(_candidate_notes(run_dir))


def _candidate_notes(run_dir: Path) -> list[dict[str, Any]]:
    document = _read_json(run_dir / "candidate.json", "candidate")
    notes = document.get("notes")
    if not isinstance(notes, list) or not all(isinstance(note, dict) for note in notes):
        raise ValueError("AI setting comparison candidate notes are invalid")
    return deepcopy(notes)


def _request_contract(run_dir: Path) -> dict[str, Any]:
    document = _read_json(run_dir / "request.json", "request")
    options = document.get("options")
    if not isinstance(options, Mapping):
        raise ValueError("AI setting comparison request options are invalid")
    sanitised_options = {
        key: deepcopy(value)
        for key, value in options.items()
        if key not in _PATH_REQUEST_FIELDS
    }
    return {
        "schema": document.get("schema"),
        "backend": document.get("backend"),
        "roles": deepcopy(document.get("roles")),
        "start_seconds": document.get("start_seconds"),
        "end_seconds": document.get("end_seconds"),
        "options": sanitised_options,
    }


def _paths_in_benchmark_order(
    paths: Sequence[Path], benchmark: Mapping[str, Any]
) -> list[Path]:
    by_run_id: dict[str, Path] = {}
    for path in paths:
        run = _read_json(path / "run.json", "run manifest")
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in by_run_id:
            raise ValueError("AI setting comparison run IDs must be unique")
        by_run_id[run_id] = path
    ordered = []
    for repetition in benchmark.get("repetitions", ()):
        run_id = repetition.get("run_id")
        if run_id not in by_run_id:
            raise ValueError("AI setting comparison benchmark run identity changed")
        ordered.append(by_run_id[run_id])
    if len(ordered) != len(paths):
        raise ValueError("AI setting comparison benchmark repetitions are incomplete")
    return ordered


def _input_paths(values: Sequence[str | Path], *, arm: str) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes, Path)):
        raise ValueError(
            f"AI setting comparison needs at least two {arm} run directories"
        )
    paths = tuple(Path(value).expanduser().absolute().resolve() for value in values)
    if len(paths) < 2:
        raise ValueError(
            f"AI setting comparison needs at least two {arm} run directories"
        )
    if len(set(paths)) != len(paths):
        raise ValueError(f"AI setting comparison {arm} run directories must be unique")
    return paths


def _require_globally_unique(paths: Sequence[Path]) -> None:
    if len(set(paths)) != len(paths):
        raise ValueError(
            "AI setting comparison run directories must be unique across both arms"
        )


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value or value.endswith("z"):
        raise ValueError(f"AI setting comparison {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"AI setting comparison {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"AI setting comparison {label} must include a timezone")
    return parsed


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"AI setting comparison cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"AI setting comparison {label} must be a JSON object")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _positive_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite and positive")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )
