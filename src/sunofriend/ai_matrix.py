"""Deterministic Phase 5 reports over immutable AI transcription runs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

import soundfile

from .ai_quality import (
    AI_QUALITY_SCHEMA,
    assess_candidate_quality,
    severe_quality_codes,
)
from .ai_runtime import (
    AITranscriptionCandidate,
    AITranscriptionRequest,
)
from .midi_tempo import MICROSECONDS_PER_MINUTE, _scan_midi


AI_MATRIX_SCHEMA = "sunofriend.ai-candidate-matrix.v1"
_RUN_SCHEMA = "sunofriend.ai-bakeoff-run.v1"
_LANE = re.compile(r"^(?:S0|M[0-4]|H1|E1)(?:-[a-z0-9][a-z0-9_-]*)?$")


def write_ai_candidate_matrix(
    lanes: Sequence[tuple[str, str | Path]],
    output_path: str | Path,
    *,
    boundary_tolerance_ms: float = 80.0,
    overlap_tolerance_ms: float = 80.0,
) -> dict[str, Any]:
    """Validate explicit immutable runs and write one path-free matrix report."""

    output = Path(output_path).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"AI matrix report already exists: {output}")
    report = build_ai_candidate_matrix(
        lanes,
        boundary_tolerance_ms=boundary_tolerance_ms,
        overlap_tolerance_ms=overlap_tolerance_ms,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    return report


def build_ai_candidate_matrix(
    lanes: Sequence[tuple[str, str | Path]],
    *,
    boundary_tolerance_ms: float = 80.0,
    overlap_tolerance_ms: float = 80.0,
) -> dict[str, Any]:
    """Return a deterministic comparison without editing any source run."""

    if not lanes:
        raise ValueError("AI matrix needs at least one LANE=RUN_DIR input")
    _positive_finite(boundary_tolerance_ms, "boundary_tolerance_ms")
    _positive_finite(overlap_tolerance_ms, "overlap_tolerance_ms")
    names = [name for name, _ in lanes]
    if len(set(names)) != len(names):
        raise ValueError("AI matrix lane names must be unique")
    for name in names:
        if not _LANE.fullmatch(name):
            raise ValueError(
                "lane must be S0, M0..M4, H1 or E1 with an optional -role suffix"
            )

    cache: dict[tuple[str, int, int, str], bool] = {}
    loaded = [
        _load_lane(name, Path(run_dir).expanduser().absolute(), cache)
        for name, run_dir in lanes
    ]
    checkpoint_hashes = {item["checkpoint_sha256"] for item in loaded}
    if len(checkpoint_hashes) != 1:
        raise ValueError("AI matrix lanes must use the same pinned checkpoint")
    config_hashes = {item["model_config_sha256"] for item in loaded}
    if len(config_hashes) != 1:
        raise ValueError("AI matrix lanes must use the same pinned model config")
    backends = {item["candidate"].backend for item in loaded}
    if len(backends) != 1:
        raise ValueError("AI matrix lanes must use the same backend")
    model_versions = {item["candidate"].model_version for item in loaded}
    if len(model_versions) != 1:
        raise ValueError("AI matrix lanes must use the same model/runtime version")
    worker_hashes = {item["worker_sha256"] for item in loaded}
    if len(worker_hashes) != 1:
        raise ValueError("AI matrix lanes must use the same pinned worker")
    execution_profiles = {
        json.dumps(_path_free_execution(item["execution"]), sort_keys=True)
        for item in loaded
    }
    if len(execution_profiles) != 1:
        raise ValueError("AI matrix lanes must use the same execution settings")
    _validate_m4_lanes(loaded)

    rows = [
        _lane_report(
            item,
            boundary_tolerance_seconds=boundary_tolerance_ms / 1000.0,
        )
        for item in loaded
    ]
    rows.sort(key=lambda row: row["lane"])
    report = {
        "schema": AI_MATRIX_SCHEMA,
        "backend": next(iter(backends)),
        "checkpoint_sha256": next(iter(checkpoint_hashes)),
        "model_config_sha256": next(iter(config_hashes)),
        "model_version": next(iter(model_versions)),
        "worker_sha256": next(iter(worker_hashes)),
        "execution": _path_free_execution(loaded[0]["execution"]),
        "lane_count": len(rows),
        "boundary_tolerance_ms": float(boundary_tolerance_ms),
        "overlap_tolerance_ms": float(overlap_tolerance_ms),
        "lanes": rows,
        "label_stability": _label_stability(rows),
        "cross_lane_note_overlap": _cross_lane_overlap(
            loaded, tolerance_seconds=overlap_tolerance_ms / 1000.0
        ),
        "m4_role_overlap": _m4_role_overlap(
            loaded, tolerance_seconds=overlap_tolerance_ms / 1000.0
        ),
        "raw_candidates_mutated": False,
        "midi_notes_mutated": 0,
        "interpretation": (
            "Boundary and cross-lane overlap are diagnostics, not proof that a "
            "note or instrument label is correct. Listening remains required."
        ),
    }
    return report


def _load_lane(
    lane: str,
    run_dir: Path,
    cache: dict[tuple[str, int, int, str], bool],
) -> dict[str, Any]:
    if not run_dir.is_dir():
        raise ValueError(f"AI matrix run directory does not exist: {run_dir}")
    run = _read_json(run_dir / "run.json")
    if run.get("schema") != _RUN_SCHEMA or run.get("status") != "complete":
        raise ValueError(f"AI matrix lane {lane} is not a completed immutable run")
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError(f"AI matrix lane {lane} has no artifact manifest")
    for required in (
        "request.json",
        "candidate.raw.json",
        "candidate.json",
        "candidate.mid",
    ):
        record = artifacts.get(required)
        if not isinstance(record, Mapping):
            raise ValueError(f"AI matrix lane {lane} is missing {required}")
    verified_artifacts: dict[str, Path] = {}
    for name, record in artifacts.items():
        if not isinstance(name, str) or not isinstance(record, Mapping):
            raise ValueError(f"AI matrix lane {lane} has an invalid artifact record")
        verified_artifacts[name] = _verify_record(
            record, run_dir, cache, label=f"{lane} {name}"
        )
        if (
            name
            in {
                "request.json",
                "candidate.raw.json",
                "candidate.json",
                "candidate.mid",
                "candidate.quality.json",
            }
            and verified_artifacts[name] != (run_dir / name).resolve()
        ):
            raise ValueError(
                f"AI matrix lane {lane} {name} artifact path disagrees"
            )

    source_path = _verify_record(
        run.get("source"), None, cache, label=f"{lane} source"
    )
    worker = run.get("worker")
    _verify_record(worker, None, cache, label=f"{lane} worker")
    checkpoint = run.get("checkpoint")
    _verify_record(checkpoint, None, cache, label=f"{lane} checkpoint")
    if isinstance(checkpoint, Mapping) and isinstance(checkpoint.get("config"), Mapping):
        _verify_record(
            checkpoint["config"], None, cache, label=f"{lane} model config"
        )

    request_document = _read_json(run_dir / "request.json")
    request = AITranscriptionRequest.from_dict(request_document, require_audio=False)
    if Path(request.audio_path).expanduser().resolve() != source_path:
        raise ValueError(f"AI matrix lane {lane} request source differs from run source")
    source_duration, duration_tolerance = _source_excerpt_duration(
        source_path, request, lane=lane
    )
    if isinstance(run.get("request"), Mapping) and run["request"] != request_document:
        raise ValueError(f"AI matrix lane {lane} request.json differs from run.json")
    candidate_document = _read_json(run_dir / "candidate.json")
    candidate = AITranscriptionCandidate.from_dict(candidate_document)
    _validate_candidate_excerpt_duration(
        candidate,
        source_duration=source_duration,
        tolerance_seconds=duration_tolerance,
        lane=lane,
    )
    if candidate.backend != run.get("backend") or candidate.backend != request.backend:
        raise ValueError(f"AI matrix lane {lane} backend records disagree")
    if len(candidate.notes) != int(run.get("note_count", -1)):
        raise ValueError(f"AI matrix lane {lane} note count differs from run.json")
    checkpoint_hash = str(checkpoint.get("sha256", ""))
    requested_checkpoint_hash = request.options.get("model_sha256")
    if (
        requested_checkpoint_hash is not None
        and requested_checkpoint_hash != checkpoint_hash
    ):
        raise ValueError(f"AI matrix lane {lane} request checkpoint hash disagrees")
    if candidate.metadata.get("checkpoint_sha256") != checkpoint_hash:
        raise ValueError(f"AI matrix lane {lane} candidate checkpoint hash disagrees")
    for raw_name in candidate.raw_artifacts:
        raw_record = artifacts.get(Path(raw_name).name)
        if not isinstance(raw_record, Mapping):
            raise ValueError(
                f"AI matrix lane {lane} does not pin raw artifact {raw_name}"
            )

    config_record = checkpoint.get("config") if isinstance(checkpoint, Mapping) else None
    config_hash = (
        str(config_record.get("sha256", ""))
        if isinstance(config_record, Mapping)
        else ""
    )
    if candidate.backend == "muscriptor" and not config_hash:
        raise ValueError(f"AI matrix lane {lane} has no pinned MuScriptor config")
    candidate_execution = candidate.metadata.get("execution")
    if (
        isinstance(candidate_execution, Mapping)
        and run.get("execution") != candidate_execution
    ):
        raise ValueError(
            f"AI matrix lane {lane} execution differs from pinned candidate metadata"
        )
    execution = run.get("execution") or candidate_execution
    _verify_execution_against_request(execution, request, lane=lane)
    if isinstance(execution, Mapping):
        execution_config_hash = execution.get("model_config_sha256")
        if execution_config_hash is not None and execution_config_hash != config_hash:
            raise ValueError(f"AI matrix lane {lane} execution config hash disagrees")
    requested_config_hash = request.options.get("model_config_sha256")
    if requested_config_hash is not None and requested_config_hash != config_hash:
        raise ValueError(f"AI matrix lane {lane} request config hash disagrees")

    quality_path = run_dir / "candidate.quality.json"
    quality_record = artifacts.get("candidate.quality.json")
    if quality_path.is_file() and isinstance(quality_record, Mapping):
        _verify_record(
            quality_record, run_dir, cache, label=f"{lane} candidate.quality.json"
        )
        recorded_quality = _read_json(quality_path)
        if recorded_quality.get("schema") != AI_QUALITY_SCHEMA:
            raise ValueError(f"AI matrix lane {lane} has an invalid quality report")
    quality = assess_candidate_quality(candidate, requested_roles=request.roles)
    bpm = _verified_candidate_bpm(
        verified_artifacts["candidate.mid"], run.get("bpm"), lane=lane
    )

    return {
        "lane": lane,
        "run": run,
        "request": request,
        "candidate": candidate,
        "quality": quality,
        "checkpoint_sha256": checkpoint_hash,
        "model_config_sha256": config_hash,
        "worker_sha256": str(worker.get("sha256", "")),
        "execution": execution,
        "candidate_midi_sha256": artifacts["candidate.mid"]["sha256"],
        "candidate_json_sha256": artifacts["candidate.json"]["sha256"],
        "bpm": bpm,
        "duration_seconds": source_duration,
    }


def _lane_report(
    item: Mapping[str, Any], *, boundary_tolerance_seconds: float
) -> dict[str, Any]:
    run = item["run"]
    request: AITranscriptionRequest = item["request"]
    candidate: AITranscriptionCandidate = item["candidate"]
    quality = item["quality"]
    counts = Counter(note.instrument or "unlabelled" for note in candidate.notes)
    requested = list(request.roles)
    detected = sorted(counts)
    metrics = dict(quality.get("metrics", {}))
    severe_codes = severe_quality_codes(metrics)
    block_reasons = list(severe_codes)
    if not candidate.notes:
        block_reasons.append("no-note-evidence")
    duration = float(item["duration_seconds"])
    elapsed = float(run.get("elapsed_seconds", 0.0))
    execution = item["execution"]
    return {
        "lane": item["lane"],
        "run_id": run.get("run_id"),
        "source_sha256": run.get("source", {}).get("sha256"),
        "candidate_json_sha256": item["candidate_json_sha256"],
        "candidate_midi_sha256": item["candidate_midi_sha256"],
        "bpm": round(float(item["bpm"]), 6),
        "model_version": candidate.model_version,
        "model_size": (
            execution.get("model_size") if isinstance(execution, Mapping) else None
        ),
        "execution": _path_free_execution(execution),
        "requested_labels": requested,
        "detected_labels": detected,
        "missing_requested_labels": sorted(set(requested) - set(detected)),
        "unexpected_labels": sorted(set(detected) - set(requested)) if requested else [],
        "instrument_counts": dict(sorted(counts.items())),
        "note_count": len(candidate.notes),
        "duration_seconds": round(duration, 6),
        "elapsed_seconds": round(elapsed, 6),
        "real_time_factor": round(elapsed / duration, 6) if duration else None,
        "quality": {
            "status": quality.get("status"),
            "promotion_allowed": bool(quality.get("promotion_allowed")),
            "metrics": metrics,
            "warnings": list(quality.get("warnings", [])),
            "severe_codes": severe_codes,
            "audition_safe": not severe_codes,
            "playable": not block_reasons,
            "block_reasons": block_reasons,
        },
        "per_instrument": _per_instrument(candidate),
        "five_second_boundaries": _boundary_report(
            candidate,
            request,
            duration=duration,
            tolerance_seconds=boundary_tolerance_seconds,
        ),
        "raw_candidate_mutated": False,
        "midi_notes_mutated": 0,
    }


def _per_instrument(candidate: AITranscriptionCandidate) -> list[dict[str, Any]]:
    labels = sorted({note.instrument or "unlabelled" for note in candidate.notes})
    rows = []
    for label in labels:
        notes = tuple(
            note
            for note in candidate.notes
            if (note.instrument or "unlabelled") == label
        )
        subset = AITranscriptionCandidate(
            backend=candidate.backend,
            model_version=candidate.model_version,
            notes=notes,
            metadata=candidate.metadata,
        )
        quality = assess_candidate_quality(subset)
        rows.append(
            {
                "instrument": label,
                "note_count": len(notes),
                "quality_status": quality["status"],
                "metrics": quality["metrics"],
                "severe_codes": severe_quality_codes(quality["metrics"]),
            }
        )
    return rows


def _boundary_report(
    candidate: AITranscriptionCandidate,
    request: AITranscriptionRequest,
    *,
    duration: float,
    tolerance_seconds: float,
) -> dict[str, Any]:
    boundaries = []
    count = max(0, int(math.ceil(duration / 5.0)) - 1)
    for index in range(1, count + 1):
        boundary = index * 5.0
        onsets = 0
        crossings = 0
        for note in candidate.notes:
            start = note.start_seconds - request.start_seconds
            end = note.end_seconds - request.start_seconds
            if abs(start - boundary) <= tolerance_seconds:
                onsets += 1
            if start < boundary < end:
                crossings += 1
        boundaries.append(
            {
                "local_seconds": boundary,
                "source_seconds": request.start_seconds + boundary,
                "onsets_within_tolerance": onsets,
                "notes_crossing_boundary": crossings,
            }
        )
    return {
        "chunk_seconds": 5.0,
        "tolerance_ms": round(tolerance_seconds * 1000.0, 6),
        "boundaries": boundaries,
        "total_onsets_within_tolerance": sum(
            row["onsets_within_tolerance"] for row in boundaries
        ),
        "interpretation": "diagnostic only; a boundary onset may be musically correct",
    }


def _label_stability(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    by_lane = {str(row["lane"]): row for row in rows}
    m0 = by_lane.get("M0")
    m1 = by_lane.get("M1")
    if not m0 or not m1:
        return None
    labels0 = set(m0["detected_labels"])
    labels1 = set(m1["detected_labels"])
    union = labels0 | labels1
    return {
        "lanes": ["M0", "M1"],
        "jaccard": round(len(labels0 & labels1) / len(union), 6) if union else 1.0,
        "retained": sorted(labels0 & labels1),
        "only_m0": sorted(labels0 - labels1),
        "only_m1": sorted(labels1 - labels0),
    }


def _cross_lane_overlap(
    loaded: Sequence[Mapping[str, Any]], *, tolerance_seconds: float
) -> list[dict[str, Any]]:
    discovery = [item for item in loaded if item["lane"].split("-", 1)[0] in {"M0", "M1", "M2"}]
    stems = [
        item
        for item in loaded
        if item["lane"].split("-", 1)[0] in {"M3", "M4"}
    ]
    rows = []
    for source in sorted(discovery, key=lambda item: item["lane"]):
        source_candidate: AITranscriptionCandidate = source["candidate"]
        labels = sorted({note.instrument or "unlabelled" for note in source_candidate.notes})
        for label in labels:
            source_notes = [
                note
                for note in source_candidate.notes
                if (note.instrument or "unlabelled") == label
            ]
            for reference in sorted(stems, key=lambda item: item["lane"]):
                reference_notes = list(reference["candidate"].notes)
                matched = _greedy_note_overlap(
                    source_notes,
                    reference_notes,
                    source_offset=float(source["request"].start_seconds),
                    reference_offset=float(reference["request"].start_seconds),
                    tolerance_seconds=tolerance_seconds,
                )
                rows.append(
                    {
                        "source_lane": source["lane"],
                        "source_label": label,
                        "reference_lane": reference["lane"],
                        "reference_requested_labels": list(reference["request"].roles),
                        "matched_notes": matched,
                        "source_note_count": len(source_notes),
                        "reference_note_count": len(reference_notes),
                        "source_overlap_ratio": round(matched / len(source_notes), 6)
                        if source_notes
                        else 0.0,
                        "possible_role_leakage": matched > 0,
                    }
                )
    return rows


def _validate_m4_lanes(loaded: Sequence[Mapping[str, Any]]) -> None:
    """Require every M4 lane to be one comparable role-conditioned pass."""

    lanes = [item for item in loaded if item["lane"].split("-", 1)[0] == "M4"]
    if not lanes:
        return
    roles = []
    for item in lanes:
        request: AITranscriptionRequest = item["request"]
        if len(request.roles) != 1:
            raise ValueError("each M4 lane must request exactly one role")
        role = re.sub(r"[^a-z0-9]+", "_", request.roles[0].casefold()).strip("_")
        if not role:
            raise ValueError("each M4 lane must request one nonblank canonical role")
        roles.append(role)
    if len(roles) != len(set(roles)):
        raise ValueError("M4 lanes must request distinct roles")

    sources = {str(item["run"].get("source", {}).get("sha256", "")) for item in lanes}
    if len(sources) != 1 or not next(iter(sources)):
        raise ValueError("M4 lanes must use the same source audio")
    excerpts = {
        (item["request"].start_seconds, item["request"].end_seconds)
        for item in lanes
    }
    if len(excerpts) != 1:
        raise ValueError("M4 lanes must use the same source excerpt")
    bpms = {float(item["bpm"]) for item in lanes}
    if len(bpms) != 1 or next(iter(bpms)) <= 0:
        raise ValueError("M4 lanes must use the same positive BPM")


def _m4_role_overlap(
    loaded: Sequence[Mapping[str, Any]], *, tolerance_seconds: float
) -> list[dict[str, Any]]:
    """Compare same-source M4 passes without treating overlap as correctness."""

    lanes = sorted(
        (
            item
            for item in loaded
            if item["lane"].split("-", 1)[0] == "M4"
        ),
        key=lambda item: item["lane"],
    )
    rows: list[dict[str, Any]] = []
    for left, right in combinations(lanes, 2):
        left_candidate: AITranscriptionCandidate = left["candidate"]
        right_candidate: AITranscriptionCandidate = right["candidate"]
        left_notes = list(left_candidate.notes)
        right_notes = list(right_candidate.notes)
        matched = _greedy_note_overlap(
            left_notes,
            right_notes,
            source_offset=float(left["request"].start_seconds),
            reference_offset=float(right["request"].start_seconds),
            tolerance_seconds=tolerance_seconds,
        )
        left_role = left["request"].roles[0]
        right_role = right["request"].roles[0]
        label_pairs = []
        left_labels = sorted({note.instrument or "unlabelled" for note in left_notes})
        right_labels = sorted({note.instrument or "unlabelled" for note in right_notes})
        for left_label in left_labels:
            left_group = [
                note
                for note in left_notes
                if (note.instrument or "unlabelled") == left_label
            ]
            for right_label in right_labels:
                right_group = [
                    note
                    for note in right_notes
                    if (note.instrument or "unlabelled") == right_label
                ]
                pair_matches = _greedy_note_overlap(
                    left_group,
                    right_group,
                    source_offset=float(left["request"].start_seconds),
                    reference_offset=float(right["request"].start_seconds),
                    tolerance_seconds=tolerance_seconds,
                )
                label_pairs.append(
                    {
                        "left_label": left_label,
                        "right_label": right_label,
                        "matched_notes": pair_matches,
                        "left_note_count": len(left_group),
                        "right_note_count": len(right_group),
                    }
                )
        left_requested_count = sum(
            (note.instrument or "unlabelled") == left_role for note in left_notes
        )
        right_requested_count = sum(
            (note.instrument or "unlabelled") == right_role for note in right_notes
        )
        rows.append(
            {
                "left_lane": left["lane"],
                "left_requested_label": left_role,
                "right_lane": right["lane"],
                "right_requested_label": right_role,
                "matched_notes": matched,
                "left_note_count": len(left_notes),
                "right_note_count": len(right_notes),
                "left_overlap_ratio": round(matched / len(left_notes), 6)
                if left_notes
                else 0.0,
                "right_overlap_ratio": round(matched / len(right_notes), 6)
                if right_notes
                else 0.0,
                "left_requested_label_count": left_requested_count,
                "left_off_role_count": len(left_notes) - left_requested_count,
                "right_requested_label_count": right_requested_count,
                "right_off_role_count": len(right_notes) - right_requested_count,
                "label_pairs": label_pairs,
                "possible_role_collapse": matched > 0,
                "interpretation": (
                    "Same-pitch/onset overlap can reveal duplicated or relabelled "
                    "events, but it is not an accuracy score or a winner."
                ),
            }
        )
    return rows


def _greedy_note_overlap(
    source,
    reference,
    *,
    source_offset: float,
    reference_offset: float,
    tolerance_seconds: float,
) -> int:
    used: set[int] = set()
    matches = 0
    for note in sorted(source, key=lambda value: value.start_seconds):
        best_index = None
        best_distance = tolerance_seconds + 1.0
        for index, other in enumerate(reference):
            if index in used or round(note.pitch) != round(other.pitch):
                continue
            distance = abs(
                (note.start_seconds - source_offset)
                - (other.start_seconds - reference_offset)
            )
            if distance <= tolerance_seconds and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is not None:
            used.add(best_index)
            matches += 1
    return matches


def _source_excerpt_duration(
    source_path: Path,
    request: AITranscriptionRequest,
    *,
    lane: str,
) -> tuple[float, float]:
    """Reproduce the worker's frame-exact clipping from verified source audio."""

    try:
        info = soundfile.info(str(source_path))
    except (OSError, RuntimeError) as exc:
        raise ValueError(
            f"AI matrix lane {lane} source audio metadata is unavailable"
        ) from exc
    sample_rate = int(info.samplerate)
    frames = int(info.frames)
    if sample_rate <= 0 or frames <= 0:
        raise ValueError(f"AI matrix lane {lane} source audio is empty or invalid")
    start_frame = round(request.start_seconds * sample_rate)
    end_frame = (
        frames
        if request.end_seconds is None
        else min(frames, round(request.end_seconds * sample_rate))
    )
    if start_frame >= frames or end_frame <= start_frame:
        raise ValueError(
            f"AI matrix lane {lane} request does not overlap the source audio"
        )
    return (end_frame - start_frame) / sample_rate, 1.0 / sample_rate


def _validate_candidate_excerpt_duration(
    candidate: AITranscriptionCandidate,
    *,
    source_duration: float,
    tolerance_seconds: float,
    lane: str,
) -> None:
    excerpt = candidate.metadata.get("excerpt")
    if not isinstance(excerpt, Mapping) or "duration_seconds" not in excerpt:
        return
    value = excerpt.get("duration_seconds")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(
            f"AI matrix lane {lane} candidate excerpt duration is invalid"
        )
    if not math.isclose(
        float(value), source_duration, rel_tol=0.0, abs_tol=tolerance_seconds
    ):
        raise ValueError(
            f"AI matrix lane {lane} candidate excerpt duration disagrees with "
            "verified source frames"
        )


def _path_free_execution(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        key: value[key]
        for key in ("schema", "model_size", "model_config_sha256")
        if key in value and isinstance(value[key], (str, int, float, bool))
    }
    nested_fields = {
        "decoding": (
            "strategy",
            "beam_size",
            "batch_size",
            "cfg_coef",
            "temperature",
            "use_sampling",
            "no_eos_is_ok",
        ),
        "chunking": (
            "seconds",
            "policy",
            "prelude_forcing",
            "prelude_forcing_supported",
        ),
    }
    for section, names in nested_fields.items():
        source = value.get(section)
        if not isinstance(source, Mapping):
            continue
        result[section] = {
            name: source[name]
            for name in names
            if name in source
            and isinstance(source[name], (str, int, float, bool))
        }
    return result


def _verify_execution_against_request(
    value: Any, request: AITranscriptionRequest, *, lane: str
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"AI matrix lane {lane} has no execution settings")
    options = request.options
    expected = {
        "model_size": options.get("model_size"),
        "decoding": {
            "beam_size": options.get("beam_size"),
            "batch_size": options.get("batch_size"),
            "cfg_coef": options.get("cfg_coef"),
            "temperature": options.get("temperature"),
            "use_sampling": options.get("use_sampling"),
            "no_eos_is_ok": options.get("no_eos_is_ok"),
        },
        "chunking": {
            "seconds": options.get("chunk_seconds"),
            "prelude_forcing": options.get("prelude_forcing"),
            "prelude_forcing_supported": options.get(
                "prelude_forcing_supported"
            ),
        },
    }
    actual = _path_free_execution(value) or {}
    for name, expected_value in expected.items():
        if isinstance(expected_value, Mapping):
            actual_section = actual.get(name)
            if not isinstance(actual_section, Mapping):
                raise ValueError(
                    "AI matrix lanes must use the same execution settings pinned "
                    f"in request ({lane} has no {name})"
                )
            for field, field_value in expected_value.items():
                if field_value is not None and actual_section.get(field) != field_value:
                    raise ValueError(
                        "AI matrix lanes must use the same execution settings pinned "
                        f"in request ({lane} {name}.{field} differs)"
                    )
        elif expected_value is not None and actual.get(name) != expected_value:
            raise ValueError(
                "AI matrix lanes must use the same execution settings pinned in "
                f"request ({lane} {name} differs)"
            )
    requested_config = options.get("model_config_sha256")
    recorded_config = actual.get("model_config_sha256")
    if recorded_config is not None and recorded_config != requested_config:
        raise ValueError(
            f"AI matrix lane {lane} execution config hash differs from request"
        )


def _verified_candidate_bpm(path: Path, declared: Any, *, lane: str) -> float:
    try:
        declared_bpm = float(declared)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AI matrix lane {lane} has no valid BPM") from exc
    if not math.isfinite(declared_bpm) or declared_bpm <= 0:
        raise ValueError(f"AI matrix lane {lane} has no valid BPM")
    layout = _scan_midi(path.read_bytes())
    if len(layout.tempo_events) != 1:
        raise ValueError(
            f"AI matrix lane {lane} candidate MIDI must have one tempo event"
        )
    tick_zero = [event for event in layout.tempo_events if event.tick == 0]
    tempos = {event.microseconds_per_quarter for event in tick_zero}
    if len(tempos) != 1:
        raise ValueError(
            f"AI matrix lane {lane} candidate MIDI has no unambiguous tick-zero tempo"
        )
    encoded = MICROSECONDS_PER_MINUTE / next(iter(tempos))
    if abs(encoded - declared_bpm) > 0.001:
        raise ValueError(
            f"AI matrix lane {lane} BPM differs from its pinned candidate MIDI"
        )
    return encoded


def _verify_record(
    value: Any,
    root: Path | None,
    cache: dict[tuple[str, int, int, str], bool],
    *,
    label: str,
) -> Path:
    if not isinstance(value, Mapping):
        raise ValueError(f"AI matrix {label} has no file record")
    path = Path(str(value.get("path", "")))
    if root is not None and not path.is_absolute():
        path = root / path
    path = path.resolve()
    if root is not None:
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"AI matrix {label} escapes its run directory") from exc
    if not path.is_file():
        raise ValueError(f"AI matrix {label} file is missing")
    stat = path.stat()
    expected_hash = str(value.get("sha256", ""))
    key = (str(path), stat.st_size, stat.st_mtime_ns, expected_hash)
    verified = cache.get(key)
    if verified is None:
        verified = stat.st_size == value.get("bytes") and _sha256(path) == expected_hash
        cache[key] = verified
    if not verified:
        raise ValueError(f"AI matrix {label} failed its size/SHA-256 check")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid AI matrix JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"AI matrix JSON must be an object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _positive_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


__all__ = [
    "AI_MATRIX_SCHEMA",
    "build_ai_candidate_matrix",
    "write_ai_candidate_matrix",
]
