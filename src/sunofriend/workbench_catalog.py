"""Discover immutable source and MIDI artifacts for the local Workbench.

The workbench deliberately consumes existing outputs.  It does not transcribe,
render, move, or edit audio/MIDI while building a catalogue.  An optional JSON
catalogue can provide exact source/candidate pairings when automatic role-based
discovery would be ambiguous.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .metadata import infer_project_metadata


WORKBENCH_CATALOG_SCHEMA = "sunofriend.workbench-catalog.v1"
_AUDIO_SUFFIXES = {".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}
_MIDI_SUFFIXES = {".mid", ".midi"}
_IGNORED_SOURCE_ROLES = {"metronome"}
_MAX_DISCOVERED_MIDI = 5000
_PATH_KEY = re.compile(
    r"(?:^|_)(?:path|paths|dir|directory|cwd|command|argv|executable|python)(?:_|$)"
)
_PATH_SUFFIXES = (
    ".json",
    ".log",
    ".mid",
    ".onnx",
    ".py",
    ".safetensors",
    ".sf2",
    ".wav",
)
_REDACTED = object()

# Specific names precede broad aliases so backing vocals and other-kit are not
# silently collapsed into vocals or other.
_ROLE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backing_vocals", ("backing_vocals", "backing-vocals", "backing vocals")),
    ("other_kit", ("other_kit", "other-kit", "other kit", "percussion")),
    ("cymbals", ("cymbals", "cymbal")),
    ("strings", ("strings", "string")),
    ("vocals", ("vocals", "vocal", "voice")),
    ("metronome", ("metronome", "click-track", "click track")),
    ("snare", ("snare",)),
    ("kick", ("kick",)),
    ("hat", ("hi-hat", "hi_hat", "hihat", "hat")),
    ("toms", ("toms", "tom")),
    ("bass", ("bass",)),
    ("keys", ("keys", "keyboard", "electric-piano", "electric piano")),
    ("piano", ("piano",)),
    ("pads", ("pads", "pad")),
    ("synth", ("synth",)),
    ("lead", ("lead",)),
    ("wind", ("wind", "brass")),
    ("rhythm", ("rhythm", "guitar")),
    ("other", ("other",)),
)


def build_workbench_catalog(
    project_root: str | Path,
    *,
    candidate_roots: Sequence[str | Path] = (),
    catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a deterministic, hash-pinned catalogue of local artifacts."""

    project = _existing_directory(project_root, label="project")
    roots = _candidate_roots(project, candidate_roots)
    metadata = infer_project_metadata(project)
    if catalog_path is not None:
        document_path = _existing_file(catalog_path, label="workbench catalog")
        document = _read_json(document_path)
        if document.get("schema") != WORKBENCH_CATALOG_SCHEMA:
            raise ValueError("unsupported workbench catalog schema")
        stems = _stems_from_document(
            document,
            document_path=document_path,
            project_root=project,
            candidate_roots=roots,
        )
        catalog_source = _file_record(document_path)
    else:
        stems = _discover_stems(project, roots)
        catalog_source = None

    project_id = hashlib.sha256(str(project).encode("utf-8")).hexdigest()[:20]
    setup_files = [
        _file_record(path)
        for path in sorted(project.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in {".pdf", ".txt"}
    ]
    return {
        "schema": WORKBENCH_CATALOG_SCHEMA,
        "project_id": project_id,
        "name": project.name,
        "root": str(project),
        "candidate_roots": [str(root) for root in roots],
        "catalog_source": catalog_source,
        "setup": {
            "bpm": metadata.bpm,
            "key": metadata.key,
            "tuning_hz": metadata.tuning_hz,
            "downbeat": None,
            "files": setup_files,
        },
        "stems": stems,
        "privacy": {
            "mode": "local",
            "uploads_enabled": False,
            "third_party_scripts": False,
        },
    }


def public_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Remove absolute paths while retaining hashes and useful UI metadata."""

    stems = []
    for stem in catalog.get("stems", []):
        candidates = []
        for candidate in stem.get("candidates", []):
            public_candidate = {
                    key: value
                    for key, value in candidate.items()
                    if key not in {"midi_path", "preview_path"}
                }
            for record_name in ("midi", "preview"):
                record = public_candidate.get(record_name)
                if isinstance(record, Mapping):
                    public_candidate[record_name] = {
                        key: value for key, value in record.items() if key != "path"
                    }
            candidates.append(public_candidate)
        public_stem = {
                key: value
                for key, value in stem.items()
                if key not in {"source_path", "candidates"}
            }
        source = public_stem.get("source")
        if isinstance(source, Mapping):
            public_stem["source"] = {
                key: value for key, value in source.items() if key != "path"
            }
        public_stem["candidates"] = candidates
        stems.append(public_stem)
    return {
        "schema": catalog.get("schema"),
        "project_id": catalog.get("project_id"),
        "name": catalog.get("name"),
        "setup": _public_setup(catalog.get("setup", {})),
        "privacy": dict(catalog.get("privacy", {})),
        "stems": stems,
    }


def media_files(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return hash-pinned records for files which the local server may expose."""

    result: dict[str, dict[str, Any]] = {}
    for stem in catalog.get("stems", []):
        result[str(stem["source_media_id"])] = dict(stem["source"])
        for candidate in stem.get("candidates", []):
            result[str(candidate["midi_media_id"])] = dict(candidate["midi"])
            preview_id = candidate.get("preview_media_id")
            preview = candidate.get("preview")
            if preview and preview_id:
                result[str(preview_id)] = dict(preview)
    return result


def _discover_stems(project: Path, candidate_roots: Sequence[Path]) -> list[dict[str, Any]]:
    source_files = []
    for path in sorted(project.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() not in _AUDIO_SUFFIXES:
            continue
        resolved = path.resolve()
        if not _is_within(resolved, project):
            raise ValueError(f"project source symlink escapes the project: {path}")
        source_files.append(resolved)
    if not source_files:
        raise ValueError(
            "project contains no top-level audio stems; use a project directory "
            "with WAV/AIFF/FLAC stems or provide an explicit catalog"
        )

    midi_files = _discover_midi(candidate_roots)
    candidates_by_role: dict[str, list[dict[str, Any]]] = {}
    for midi in midi_files:
        role = infer_role(" ".join(midi.parts[-5:]))
        if role is None or midi.name.lower().startswith("full_arrangement"):
            continue
        candidate = _candidate_record(
            midi, role=role, candidate_roots=candidate_roots
        )
        bucket = candidates_by_role.setdefault(role, [])
        if not any(item["midi"]["sha256"] == candidate["midi"]["sha256"] for item in bucket):
            bucket.append(candidate)

    stems = []
    for source in source_files:
        role = infer_role(source.stem) or "unclassified"
        if role in _IGNORED_SOURCE_ROLES:
            continue
        candidates = sorted(
            candidates_by_role.get(role, []),
            key=_candidate_sort_key,
        )
        stems.append(_stem_record(source, role=role, candidates=candidates))
    if not stems:
        raise ValueError("project contains no reviewable audio stems")
    return stems


def _stems_from_document(
    document: Mapping[str, Any],
    *,
    document_path: Path,
    project_root: Path,
    candidate_roots: Sequence[Path],
) -> list[dict[str, Any]]:
    rows = document.get("stems")
    if not isinstance(rows, list) or not rows:
        raise ValueError("workbench catalog must contain at least one stem")
    stems: list[dict[str, Any]] = []
    allowed_candidates = tuple(candidate_roots)
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"workbench stem {index} must be an object")
        source = _resolve_document_path(row.get("source"), document_path.parent)
        _require_within(source, (project_root,), label=f"stem {index} source")
        if source.suffix.lower() not in _AUDIO_SUFFIXES:
            raise ValueError(f"stem {index} source is not a supported audio file")
        role = str(row.get("role") or infer_role(source.stem) or "unclassified")
        candidate_rows = row.get("candidates", [])
        if not isinstance(candidate_rows, list):
            raise ValueError(f"stem {index} candidates must be a list")
        candidates = []
        for candidate_index, candidate_row in enumerate(candidate_rows, start=1):
            if not isinstance(candidate_row, Mapping):
                raise ValueError(
                    f"stem {index} candidate {candidate_index} must be an object"
                )
            midi = _resolve_document_path(candidate_row.get("midi"), document_path.parent)
            _require_within(
                midi,
                allowed_candidates,
                label=f"stem {index} candidate {candidate_index} MIDI",
            )
            if midi.suffix.lower() not in _MIDI_SUFFIXES:
                raise ValueError(f"stem {index} candidate {candidate_index} is not MIDI")
            preview_value = candidate_row.get("preview")
            preview = None
            if preview_value:
                preview = _resolve_document_path(preview_value, document_path.parent)
                _require_within(
                    preview,
                    allowed_candidates,
                    label=f"stem {index} candidate {candidate_index} preview",
                )
                if preview.suffix.lower() not in _AUDIO_SUFFIXES:
                    raise ValueError(
                        f"stem {index} candidate {candidate_index} preview is not audio"
                    )
            candidate = _candidate_record(
                midi,
                role=role,
                preview=preview,
                candidate_roots=allowed_candidates,
                label=_optional_text(candidate_row.get("label")),
                description=_optional_text(candidate_row.get("description")),
                process=_optional_text(candidate_row.get("process")),
                warnings=_string_list(candidate_row.get("warnings", [])),
            )
            candidates.append(candidate)
        stems.append(
            _stem_record(
                source,
                role=role,
                label=_optional_text(row.get("label")),
                review_question=_optional_text(row.get("review_question")),
                listening_focus=_string_list(row.get("listening_focus", [])),
                candidates=_deduplicate_candidates(candidates),
            )
        )
    return stems


def _stem_record(
    source: Path,
    *,
    role: str,
    candidates: Sequence[Mapping[str, Any]],
    label: str | None = None,
    review_question: str | None = None,
    listening_focus: Sequence[str] = (),
) -> dict[str, Any]:
    source_record = _file_record(source)
    review_context = {
        "review_question": review_question,
        "listening_focus": list(listening_focus),
    }
    review_context_sha256 = _document_hash(review_context)
    identity_parts = [str(source_record["sha256"]), role, source.name.casefold()]
    if review_question is not None or listening_focus:
        identity_parts.append(review_context_sha256)
    stem_identity = "\0".join(identity_parts).encode("utf-8")
    stem_id = "stem-" + hashlib.sha256(stem_identity).hexdigest()[:20]
    candidate_rows = [dict(item) for item in candidates]
    # Preserve the already deterministic candidate order while limiting the
    # normal result space. Diagnostic "possible" and "uncertain" variants are
    # never silently promoted into the first three.
    ordered_primary_ids: list[str] = []
    for candidate in candidate_rows:
        candidate_id = str(candidate["candidate_id"])
        if candidate.get("diagnostic_only") or len(ordered_primary_ids) >= 3:
            continue
        ordered_primary_ids.append(candidate_id)
    primary_ids = set(ordered_primary_ids)
    primary_count = len(primary_ids)
    return {
        "stem_id": stem_id,
        "label": label or _human_label(source.stem),
        "role": role,
        "review_question": review_question,
        "listening_focus": list(listening_focus),
        "review_context_sha256": review_context_sha256,
        "source_path": str(source),
        "source": source_record,
        "source_media_id": "source-" + source_record["sha256"][:24],
        "candidate_count": len(candidate_rows),
        "primary_candidate_count": primary_count,
        "candidates": [
            {
                **candidate,
                "primary": str(candidate["candidate_id"]) in primary_ids,
            }
            for candidate in candidate_rows
        ],
    }


def _candidate_record(
    midi: Path,
    *,
    role: str,
    candidate_roots: Sequence[Path] = (),
    preview: Path | None = None,
    label: str | None = None,
    description: str | None = None,
    process: str | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    midi_record = _file_record(midi)
    ai_diagnostics = _ai_candidate_diagnostics(
        midi, midi_record
    ) or _ai_label_split_diagnostics(midi, midi_record)
    inferred_process, inferred_label, inferred_description = _describe_candidate(midi)
    lower_name = midi.stem.lower()
    preview = preview or _find_preview(midi, candidate_roots)
    preview_record = _file_record(preview) if preview else None
    combined_warnings = list(warnings)
    if ai_diagnostics:
        combined_warnings.extend(ai_diagnostics["warnings"])
    blocked = bool(ai_diagnostics and not ai_diagnostics["playable"])
    return {
        "candidate_id": "candidate-" + midi_record["sha256"][:16],
        "role": role,
        "label": label or inferred_label,
        "description": description or inferred_description,
        "process": process or inferred_process,
        "warnings": list(dict.fromkeys(combined_warnings)),
        "ai_diagnostics": ai_diagnostics,
        "audition_blocked": blocked,
        "diagnostic_only": any(
            marker in lower_name
            for marker in ("possible", "uncertain", "rejected", "complement")
        )
        or blocked,
        "midi_path": str(midi),
        "midi": midi_record,
        "midi_media_id": "midi-" + midi_record["sha256"][:24],
        "preview_path": str(preview) if preview else None,
        "preview": preview_record,
        "preview_media_id": (
            "preview-" + preview_record["sha256"][:24] if preview_record else None
        ),
        "preview_policy": (
            "existing-render-not-proven-level-matched" if preview else "not-rendered"
        ),
    }


def _ai_candidate_diagnostics(
    midi: Path, midi_record: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Attach verified, path-free AI evidence when a run sits beside the MIDI."""

    run_path = midi.parent / "run.json"
    request_path = midi.parent / "request.json"
    candidate_path = midi.parent / "candidate.json"
    if not all(path.is_file() for path in (run_path, request_path, candidate_path)):
        return None
    run = _read_json(run_path)
    if run.get("schema") != "sunofriend.ai-bakeoff-run.v1":
        return None
    if run.get("status") != "complete":
        raise ValueError(f"adjacent AI run is not complete: {run_path}")
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError(f"adjacent AI run has no artifact manifest: {run_path}")
    for required in (
        "request.json",
        "candidate.raw.json",
        "candidate.json",
        midi.name,
    ):
        if not isinstance(artifacts.get(required), Mapping):
            raise ValueError(f"adjacent AI run does not pin {required}")
    for name, record in artifacts.items():
        if not isinstance(name, str) or not isinstance(record, Mapping):
            raise ValueError("adjacent AI run has an invalid artifact record")
        artifact_path = _verify_ai_record(record, root=midi.parent, label=name)
        if (
            name
            in {
                "request.json",
                "candidate.raw.json",
                "candidate.json",
                "candidate.quality.json",
                midi.name,
            }
            and artifact_path != (midi.parent / name).resolve()
        ):
            raise ValueError(f"adjacent AI run artifact path disagrees: {name}")
    if artifacts.get(midi.name, {}).get("sha256") != midi_record.get("sha256"):
        raise ValueError("adjacent AI run MIDI does not match the discovered candidate")

    source_record = run.get("source")
    checkpoint_record = run.get("checkpoint")
    worker_record = run.get("worker")
    _verify_ai_record(source_record, label="source")
    _verify_ai_record(checkpoint_record, label="checkpoint")
    _verify_ai_record(worker_record, label="worker")
    if isinstance(checkpoint_record, Mapping) and isinstance(
        checkpoint_record.get("config"), Mapping
    ):
        _verify_ai_record(checkpoint_record["config"], label="model config")

    from .ai_quality import assess_candidate_quality, severe_quality_codes
    from .ai_runtime import AITranscriptionCandidate, AITranscriptionRequest

    request_document = _read_json(request_path)
    if isinstance(run.get("request"), Mapping) and run["request"] != request_document:
        raise ValueError("adjacent AI request.json differs from run.json")
    request = AITranscriptionRequest.from_dict(request_document, require_audio=False)
    candidate = AITranscriptionCandidate.from_dict(_read_json(candidate_path))
    if candidate.backend != request.backend or candidate.backend != run.get("backend"):
        raise ValueError("adjacent AI run backend records disagree")
    if len(candidate.notes) != int(run.get("note_count", -1)):
        raise ValueError("adjacent AI run note count disagrees")
    checkpoint_hash = str(checkpoint_record.get("sha256", ""))
    if candidate.metadata.get("checkpoint_sha256") != checkpoint_hash:
        raise ValueError("adjacent AI candidate checkpoint hash disagrees")
    requested_checkpoint_hash = request.options.get("model_sha256")
    if (
        requested_checkpoint_hash is not None
        and requested_checkpoint_hash != checkpoint_hash
    ):
        raise ValueError("adjacent AI request checkpoint hash disagrees")
    for raw_name in candidate.raw_artifacts:
        if Path(raw_name).name not in artifacts:
            raise ValueError(f"adjacent AI run does not pin raw artifact {raw_name}")

    config_record = (
        checkpoint_record.get("config")
        if isinstance(checkpoint_record, Mapping)
        else None
    )
    config_hash = (
        str(config_record.get("sha256", ""))
        if isinstance(config_record, Mapping)
        else ""
    )
    execution = run.get("execution") or candidate.metadata.get("execution")
    if isinstance(execution, Mapping):
        execution_config_hash = execution.get("model_config_sha256")
        if execution_config_hash is not None and execution_config_hash != config_hash:
            raise ValueError("adjacent AI execution config hash disagrees")
    requested_config_hash = request.options.get("model_config_sha256")
    if requested_config_hash is not None and requested_config_hash != config_hash:
        raise ValueError("adjacent AI request config hash disagrees")

    quality_path = midi.parent / "candidate.quality.json"
    quality_record = artifacts.get("candidate.quality.json")
    if quality_path.is_file() and isinstance(quality_record, Mapping):
        actual_quality = _file_record(quality_path)
        if (
            actual_quality["bytes"] != quality_record.get("bytes")
            or actual_quality["sha256"] != quality_record.get("sha256")
        ):
            raise ValueError("adjacent AI quality report changed after completion")
        recorded_quality = _read_json(quality_path)
        if recorded_quality.get("schema") != "sunofriend.ai-candidate-quality.v1":
            raise ValueError("adjacent AI quality report has an unsupported schema")
    quality = assess_candidate_quality(candidate, requested_roles=request.roles)
    metrics = dict(quality.get("metrics", {}))
    severe_codes = severe_quality_codes(metrics)
    duration = _ai_candidate_duration(candidate, request, metrics)
    elapsed = float(run.get("elapsed_seconds") or 0.0)
    detected = sorted(
        {note.instrument or "unlabelled" for note in candidate.notes}
    )
    warnings = [*candidate.warnings, *quality.get("warnings", [])]
    block_reasons = list(severe_codes)
    if not candidate.notes:
        block_reasons.append("no-note-evidence")
    return {
        "schema": "sunofriend.workbench-ai-diagnostics.v1",
        "run_id": run.get("run_id"),
        "backend": candidate.backend,
        "model_version": candidate.model_version,
        "model_size": (
            execution.get("model_size")
            if isinstance(execution, Mapping)
            else run.get("checkpoint", {}).get("variant")
        ),
        "checkpoint_sha256": run.get("checkpoint", {}).get("sha256"),
        "execution": _path_free_value(execution),
        "requested_labels": list(request.roles),
        "detected_labels": detected,
        "unexpected_instruments": dict(quality.get("unexpected_instruments", {})),
        "note_count": len(candidate.notes),
        "duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 6),
        "real_time_factor": (
            round(elapsed / duration, 6) if duration > 0 else None
        ),
        "quality_status": quality.get("status"),
        "quality_metrics": metrics,
        "warnings": list(dict.fromkeys(str(value) for value in warnings)),
        "severe_codes": severe_codes,
        "audition_safe": not severe_codes,
        "playable": not block_reasons,
        "block_reasons": block_reasons,
        "five_second_boundaries": _workbench_boundary_summary(
            candidate, request, duration=duration
        ),
        "raw_candidate_mutated": False,
    }


def _ai_label_split_diagnostics(
    midi: Path, midi_record: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Attach verified diagnostics for an exact AI-label MIDI derivative."""

    report_path = midi.parent / "ai_label_split.json"
    if not report_path.is_file():
        return None
    if midi.name not in {
        "requested-label.mid",
        "unexpected-label-complement.mid",
    }:
        # The byte-identical full-candidate MIDI is a listening control, not a
        # label derivative.  Let normal Workbench candidate handling describe
        # it instead of mislabelling it as the complement.
        return None
    report = _read_json(report_path)
    if report.get("schema") != "sunofriend.ai-label-split.v1":
        return None
    expected_report_hash = report.get("report_sha256")
    unhashed = dict(report)
    unhashed.pop("report_sha256", None)
    if expected_report_hash != _document_hash(unhashed):
        raise ValueError("adjacent AI label-split report failed its document hash")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("adjacent AI label split has no artifact manifest")
    for name, record in artifacts.items():
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError("adjacent AI label split has an invalid artifact name")
        artifact_path = _verify_ai_record(
            record, root=midi.parent, label=f"label split {name}"
        )
        if artifact_path != (midi.parent / name).resolve():
            raise ValueError("adjacent AI label-split artifact path disagrees")
    required_artifacts = {
        "unchanged-full-candidate.mid",
        "source-candidate.json",
        "source-request.json",
        "requested-label.mid",
        "unexpected-label-complement.mid",
        "label-partition.json",
    }
    if not required_artifacts.issubset(artifacts):
        raise ValueError("adjacent AI label split has an incomplete artifact manifest")
    midi_artifact = artifacts.get(midi.name)
    if not isinstance(midi_artifact, Mapping):
        raise ValueError("adjacent AI label split does not pin this MIDI")
    if midi_artifact.get("sha256") != midi_record.get("sha256"):
        raise ValueError("adjacent AI label-split MIDI hash disagrees")

    partition_path = midi.parent / "label-partition.json"
    partition = _read_json(partition_path)
    if partition.get("schema") != "sunofriend.ai-label-partition.v1":
        raise ValueError("adjacent AI label partition has an unsupported schema")
    label = _label_split_text(report.get("label"), label="report label")
    if partition.get("label") != label:
        raise ValueError("adjacent AI label-split report and partition labels disagree")
    source_run = report.get("source_run")
    if not isinstance(source_run, Mapping):
        raise ValueError("adjacent AI label split has invalid source-run evidence")
    source_candidate_sha = _label_split_record_sha256(
        source_run.get("candidate"), label="source candidate"
    )
    if partition.get("source_candidate_sha256") != source_candidate_sha:
        raise ValueError("adjacent AI label-split source candidate SHA-256 disagrees")
    if artifacts["source-candidate.json"].get("sha256") != source_candidate_sha:
        raise ValueError("adjacent AI label-split candidate control SHA-256 disagrees")
    source_candidate_midi_sha = _label_split_record_sha256(
        source_run.get("candidate_midi"), label="source candidate MIDI"
    )
    if partition.get("source_candidate_midi_sha256") != source_candidate_midi_sha:
        raise ValueError("adjacent AI label-split source MIDI SHA-256 disagrees")
    control_record = artifacts["unchanged-full-candidate.mid"]
    if control_record.get("sha256") != source_candidate_midi_sha:
        raise ValueError("adjacent AI label-split control is not the source candidate MIDI")
    request_record = source_run.get("request")
    request_sha = _label_split_record_sha256(
        request_record, label="source request"
    )
    if partition.get("source_request_sha256") != request_sha:
        raise ValueError("adjacent AI label-split source request SHA-256 disagrees")
    if artifacts["source-request.json"].get("sha256") != request_sha:
        raise ValueError("adjacent AI label-split request control SHA-256 disagrees")
    source_sha = _label_split_record_sha256(
        source_run.get("source"), label="source audio"
    )
    if partition.get("source_audio_sha256") != source_sha:
        raise ValueError("adjacent AI label-split source audio SHA-256 disagrees")

    from .ai_runtime import AITranscriptionCandidate, AITranscriptionRequest

    source_candidate = AITranscriptionCandidate.from_dict(
        _read_json(midi.parent / "source-candidate.json")
    )
    source_request = AITranscriptionRequest.from_dict(
        _read_json(midi.parent / "source-request.json"), require_audio=False
    )
    if (
        source_candidate.backend != source_request.backend
        or source_candidate.backend != source_run.get("backend")
        or source_candidate.model_version != source_run.get("model_version")
    ):
        raise ValueError("adjacent AI label-split source controls disagree")
    if request_record.get("roles") != list(source_request.roles):
        raise ValueError("adjacent AI label-split source request roles disagree")
    if request_record.get("start_seconds") != source_request.start_seconds:
        raise ValueError("adjacent AI label-split source request start disagrees")
    if request_record.get("end_seconds") != source_request.end_seconds:
        raise ValueError("adjacent AI label-split source request end disagrees")

    selected = partition.get("selected")
    complement = partition.get("complement")
    if not isinstance(selected, list) or not isinstance(complement, list):
        raise ValueError("adjacent AI label partition has invalid note groups")
    source_count = _label_split_nonnegative_int(
        partition.get("source_note_count"), label="source note count"
    )
    selected_notes = [
        _label_split_partition_note(row, label=label, selected=True)
        for row in selected
    ]
    complement_notes = [
        _label_split_partition_note(row, label=label, selected=False)
        for row in complement
    ]
    selected_indices = [_partition_source_index(row) for row in selected]
    complement_indices = [_partition_source_index(row) for row in complement]
    if sorted(selected_indices + complement_indices) != list(range(source_count)):
        raise ValueError("adjacent AI label partition is not exact and exhaustive")
    if len(set(selected_indices + complement_indices)) != source_count:
        raise ValueError("adjacent AI label partition duplicates a source note")
    if len(source_candidate.notes) != source_count:
        raise ValueError("adjacent AI label-split source candidate count disagrees")
    for index, note in zip(selected_indices, selected_notes):
        if note != source_candidate.notes[index]:
            raise ValueError("adjacent AI label partition changed a source candidate note")
    for index, note in zip(complement_indices, complement_notes):
        if note != source_candidate.notes[index]:
            raise ValueError("adjacent AI label partition changed a source candidate note")
    partition_flags = partition.get("partition")
    if not isinstance(partition_flags, Mapping):
        raise ValueError("adjacent AI label split has invalid partition flags")
    required_flags = {
        "disjoint": True,
        "exhaustive": True,
        "source_indices_changed": 0,
        "source_events_deleted": 0,
        "source_events_duplicated": 0,
    }
    if any(partition_flags.get(key) != value for key, value in required_flags.items()):
        raise ValueError("adjacent AI label split does not declare an exact partition")

    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("adjacent AI label split has invalid evidence")
    if evidence.get("selected_source_indices") != selected_indices:
        raise ValueError("adjacent AI label-split selected indices disagree")
    if evidence.get("complement_source_indices") != complement_indices:
        raise ValueError("adjacent AI label-split complement indices disagree")
    if evidence.get("selected_note_count") != len(selected):
        raise ValueError("adjacent AI label-split selected note count disagrees")
    if evidence.get("complement_note_count") != len(complement):
        raise ValueError("adjacent AI label-split complement note count disagrees")
    if evidence.get("selection_policy") != "exact-model-reported-instrument-label":
        raise ValueError("adjacent AI label split has an unsupported selection policy")
    if evidence.get("physical_instrument_identified") is not False:
        raise ValueError("adjacent AI label split overclaims a physical instrument")
    detected_counts = _label_split_counts(evidence.get("detected_label_counts"))
    actual_counts: dict[str, int] = {}
    for note in (*selected_notes, *complement_notes):
        instrument = note.instrument or "unlabelled"
        actual_counts[instrument] = actual_counts.get(instrument, 0) + 1
    if detected_counts != dict(sorted(actual_counts.items())):
        raise ValueError("adjacent AI label-split detected label counts disagree")
    if sum(detected_counts.values()) != source_count:
        raise ValueError("adjacent AI label-split label counts are not exhaustive")
    if detected_counts.get(label, 0) != len(selected):
        raise ValueError("adjacent AI label-split requested-label count disagrees")

    expected_status = "review-required" if selected else "no-evidence"
    if report.get("status") != expected_status:
        raise ValueError("adjacent AI label-split status disagrees with its evidence")
    if report.get("operation") != "ai-label-split":
        raise ValueError("adjacent AI label split has an unsupported operation")
    bpm = _label_split_positive_float(report.get("bpm"), label="BPM")
    duration = _label_split_positive_float(
        source_run.get("duration_seconds"), label="source duration"
    )
    if not isinstance(request_record, Mapping):
        raise ValueError("adjacent AI label split has invalid source request evidence")
    start_seconds = _label_split_finite_float(
        request_record.get("start_seconds"), label="request start"
    )
    if start_seconds < 0:
        raise ValueError("adjacent AI label split has an invalid source excerpt")
    end_value = request_record.get("end_seconds")
    if end_value is not None:
        end_seconds = _label_split_finite_float(end_value, label="request end")
        if end_seconds <= start_seconds:
            raise ValueError("adjacent AI label split has an invalid source excerpt")
        if not math.isclose(
            end_seconds - start_seconds,
            duration,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("adjacent AI label-split source duration disagrees")
    else:
        excerpt = source_candidate.metadata.get("excerpt")
        candidate_duration = None
        if isinstance(excerpt, Mapping):
            excerpt_duration = excerpt.get("duration_seconds")
            if (
                isinstance(excerpt_duration, (int, float))
                and not isinstance(excerpt_duration, bool)
                and math.isfinite(float(excerpt_duration))
                and float(excerpt_duration) > 0
            ):
                candidate_duration = float(excerpt_duration)
        if candidate_duration is None and source_candidate.notes:
            candidate_duration = max(
                note.end_seconds for note in source_candidate.notes
            ) - min(note.start_seconds for note in source_candidate.notes)
        if candidate_duration is None:
            candidate_duration = 0.001
        if not math.isclose(
            candidate_duration,
            duration,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("adjacent AI label-split source duration disagrees")
    effects = _verify_label_split_effects(
        report.get("effects"),
        selected_count=len(selected),
    )
    render_contract = _label_split_render_contract(partition, bpm=bpm)
    rendered_counts = {
        name: _verify_label_split_midi(
            midi.parent / name,
            rows=group_rows,
            notes=group_notes,
            bpm=bpm,
            backend=str(source_run.get("backend", "")),
            render_contract=render_contract,
            effects=effects,
        )
        for name, group_rows, group_notes in (
            ("requested-label.mid", selected, selected_notes),
            (
                "unexpected-label-complement.mid",
                complement,
                complement_notes,
            ),
        )
    }

    is_selected = midi.name == "requested-label.mid"
    rows = selected if is_selected else complement
    notes = selected_notes if is_selected else complement_notes
    expected_count = len(notes)
    rendered_note_count = rendered_counts[midi.name]
    detected = (
        [label]
        if is_selected and expected_count
        else sorted(
            name
            for name, count in detected_counts.items()
            if name != label and int(count) > 0
        )
    )
    from .ai_quality import assess_candidate_quality, severe_quality_codes
    candidate = AITranscriptionCandidate(
        backend=str(source_run.get("backend", "")),
        model_version=str(source_run.get("model_version", "")),
        notes=tuple(notes),
        metadata={"excerpt": {"duration_seconds": duration}},
    )
    candidate.validate()
    quality = assess_candidate_quality(
        candidate, requested_roles=([label] if is_selected else [])
    )
    metrics = dict(quality.get("metrics", {}))
    metrics.update(
        {
            "rendered_midi_note_count": rendered_note_count,
            "source_candidate_note_count": source_count,
            "selected_label_note_count": len(selected),
            "complement_note_count": len(complement),
        }
    )
    severe_codes = severe_quality_codes(metrics)
    block_reasons = list(severe_codes)
    if not expected_count or not rendered_note_count:
        block_reasons.append("no-note-evidence")
    warning_values = report.get("warnings", [])
    if not isinstance(warning_values, list) or not all(
        isinstance(value, str) for value in warning_values
    ):
        raise ValueError("adjacent AI label split has invalid warnings")
    warnings = list(warning_values)
    warnings.extend(str(value) for value in quality.get("warnings", []))
    if not is_selected:
        warnings.append(
            "This is the unexpected-label complement retained for diagnosis, not the requested role track."
        )
    execution = source_run.get("execution")
    candidate_execution = (
        execution.get("candidate") if isinstance(execution, Mapping) else None
    )
    model_size = (
        candidate_execution.get("model_size")
        if isinstance(candidate_execution, Mapping)
        else (execution.get("model_size") if isinstance(execution, Mapping) else None)
    )
    return {
        "schema": "sunofriend.workbench-ai-diagnostics.v1",
        "run_id": report.get("source_run", {}).get("run_id"),
        "backend": report.get("source_run", {}).get("backend"),
        "model_version": report.get("source_run", {}).get("model_version"),
        "model_size": model_size,
        "checkpoint_sha256": report.get("source_run", {})
        .get("checkpoint", {})
        .get("sha256"),
        "execution": _path_free_value(execution),
        "requested_labels": [label] if is_selected else [],
        "detected_labels": detected,
        "unexpected_instruments": dict(quality.get("unexpected_instruments", {})),
        "note_count": rendered_note_count,
        "duration_seconds": duration,
        "elapsed_seconds": None,
        "real_time_factor": None,
        "quality_status": (
            "no-evidence"
            if not expected_count or not rendered_note_count
            else "review-required"
        ),
        "quality_metrics": metrics,
        "warnings": list(dict.fromkeys(warnings)),
        "severe_codes": severe_codes,
        "audition_safe": not block_reasons,
        "playable": not block_reasons,
        "block_reasons": block_reasons,
        "five_second_boundaries": _partition_boundary_summary(
            rows,
            duration=duration,
            start_seconds=float(
                source_run.get("request", {}).get("start_seconds", 0.0)
            ),
        ),
        "raw_candidate_mutated": False,
        "derivative": {
            "schema": report.get("schema"),
            "operation": report.get("operation"),
            "label": label,
            "partition": "selected" if is_selected else "complement",
            "automatic_promotion": False,
        },
    }


def _label_split_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"adjacent AI label split has an invalid {label}")
    return value.strip()


def _label_split_record_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, Mapping):
        raise ValueError(f"adjacent AI label split has no {label} record")
    digest = value.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError(f"adjacent AI label split has an invalid {label} SHA-256")
    byte_count = value.get("bytes")
    if byte_count is not None and (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise ValueError(f"adjacent AI label split has an invalid {label} byte count")
    return digest


def _label_split_nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"adjacent AI label split has an invalid {label}")
    return value


def _label_split_finite_float(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"adjacent AI label split has an invalid {label}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"adjacent AI label split has an invalid {label}") from exc
    if not math.isfinite(result):
        raise ValueError(f"adjacent AI label split has an invalid {label}")
    return result


def _label_split_positive_float(value: Any, *, label: str) -> float:
    result = _label_split_finite_float(value, label=label)
    if result <= 0:
        raise ValueError(f"adjacent AI label split has an invalid {label}")
    return result


def _label_split_partition_note(value: Any, *, label: str, selected: bool):
    if not isinstance(value, Mapping) or not isinstance(value.get("note"), Mapping):
        raise ValueError("adjacent AI label partition note evidence is invalid")
    from .ai_runtime import AITranscriptionNote

    note = AITranscriptionNote.from_dict(value["note"])
    source_event_id = value.get("source_event_id")
    if source_event_id != note.source_event_id:
        raise ValueError("adjacent AI label partition source event IDs disagree")
    velocity = value.get("audition_velocity")
    if (
        isinstance(velocity, bool)
        or not isinstance(velocity, int)
        or not 1 <= velocity <= 127
    ):
        raise ValueError("adjacent AI label partition has an invalid audition velocity")
    actual_label = note.instrument or "unlabelled"
    if selected and actual_label != label:
        raise ValueError("adjacent AI label partition selected note has the wrong label")
    if not selected and actual_label == label:
        raise ValueError("adjacent AI label partition complement contains the target label")
    return note


def _label_split_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("adjacent AI label split has invalid label counts")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("adjacent AI label split has an invalid detected label")
        name = key
        result[name] = _label_split_nonnegative_int(
            count, label=f"detected-label count for {name}"
        )
    return dict(sorted(result.items()))


def _verify_label_split_effects(
    value: Any, *, selected_count: int
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("adjacent AI label split has invalid effects")
    required = {
        "automatic_promotion": False,
        "model_rerun": False,
        "source_run_mutated": False,
        "raw_candidate_mutated": False,
        "source_midi_mutated": False,
        "source_partition_events_deleted": 0,
        "source_partition_events_duplicated": 0,
        "source_request_control_byte_identical": True,
        "source_candidate_control_byte_identical": True,
        "unchanged_control_byte_identical": True,
        "selected_audition_velocities_written": selected_count,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise ValueError("adjacent AI label split has inconsistent mutation effects")
    rendering = value.get("midi_rendering")
    if not isinstance(rendering, Mapping) or set(rendering) != {
        "requested-label.mid",
        "unexpected-label-complement.mid",
    }:
        raise ValueError("adjacent AI label split has invalid MIDI-render effects")
    return value


def _label_split_render_contract(
    partition: Mapping[str, Any], *, bpm: float
) -> Mapping[str, Any]:
    value = partition.get("render_contract")
    if not isinstance(value, Mapping):
        raise ValueError("adjacent AI label split has no MIDI-render contract")
    expected_text = {
        "policy": "deterministic-midi-audition-v1",
        "purpose": "audition-only; label-partition.json is the exact event record",
        "pitch_quantization": (
            "nearest integer via Python round (ties to even), clamped 0..127"
        ),
        "time_quantization": (
            "nearest 1/480 quarter-note tick via Python round (ties to even)"
        ),
        "duplicate_onset_policy": (
            "same track/channel/pitch/tick collapses to longest end and greatest velocity"
        ),
        "same_pitch_overlap_policy": (
            "an earlier note ends at the next onset on the same track/channel/pitch"
        ),
    }
    if any(value.get(key) != expected for key, expected in expected_text.items()):
        raise ValueError("adjacent AI label split has an unsupported MIDI-render contract")
    if value.get("ticks_per_beat") != 480 or value.get("minimum_duration_ticks") != 1:
        raise ValueError("adjacent AI label split has an unsupported MIDI time grid")
    input_bpm = _label_split_positive_float(
        value.get("tempo_input_bpm"), label="render input BPM"
    )
    if not math.isclose(input_bpm, bpm, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("adjacent AI label-split render BPM disagrees")
    _label_split_positive_float(value.get("embedded_bpm"), label="embedded BPM")
    if value.get("velocity_policy") != partition.get("velocity_policy"):
        raise ValueError("adjacent AI label-split velocity policies disagree")
    expected_keys = {
        *expected_text,
        "ticks_per_beat",
        "tempo_input_bpm",
        "embedded_bpm",
        "minimum_duration_ticks",
        "velocity_policy",
    }
    if set(value) != expected_keys:
        raise ValueError("adjacent AI label split has an unknown MIDI-render contract")
    return value


def _verify_label_split_midi(
    midi: Path,
    *,
    rows: Sequence[Any],
    notes: Sequence[Any],
    bpm: float,
    backend: str,
    render_contract: Mapping[str, Any],
    effects: Mapping[str, Any],
) -> int:
    expected_summary, expected_signatures = _label_split_expected_render(
        rows, notes=notes, bpm=bpm, backend=backend
    )
    rendering = effects["midi_rendering"]
    if rendering.get(midi.name) != expected_summary:
        raise ValueError("adjacent AI label-split MIDI-render effects disagree")

    from .clip import read_midi_clips
    from .midi_tempo import MICROSECONDS_PER_MINUTE, _scan_midi

    raw = midi.read_bytes()
    layout = _scan_midi(raw)
    if layout.ticks_per_beat != 480:
        raise ValueError("adjacent AI label-split MIDI has an unexpected time grid")
    tick_zero = [event for event in layout.tempo_events if event.tick == 0]
    if len(tick_zero) != 1 or len(layout.tempo_events) != 1:
        raise ValueError("adjacent AI label-split MIDI has an invalid tempo map")
    embedded_bpm = MICROSECONDS_PER_MINUTE / tick_zero[0].microseconds_per_quarter
    if not math.isclose(
        embedded_bpm,
        float(render_contract["embedded_bpm"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("adjacent AI label-split MIDI tempo disagrees")
    actual_signatures = sorted(
        (
            owner,
            clip.instrument.channel,
            note.pitch,
            round(note.start_beat * layout.ticks_per_beat),
            round(note.end_beat * layout.ticks_per_beat),
            note.velocity,
        )
        for owner, clip in enumerate(read_midi_clips(midi))
        for note in clip.notes
    )
    if actual_signatures != expected_signatures:
        raise ValueError("adjacent AI label-split MIDI notes disagree with its partition")
    return len(actual_signatures)


def _label_split_expected_render(
    rows: Sequence[Any],
    *,
    notes: Sequence[Any],
    bpm: float,
    backend: str,
) -> tuple[dict[str, Any], list[tuple[int, int, int, int, int, int]]]:
    from .note_safety import MidiNoteInterval, normalize_midi_intervals

    names = sorted({note.instrument or f"{backend} candidate" for note in notes})
    melodic_channels = [channel for channel in range(16) if channel != 9]
    channels: dict[str, int] = {}
    melodic_index = 0
    for name in names:
        lowered = name.lower()
        if any(
            token in lowered
            for token in ("drum", "percussion", "cymbal", "snare", "kick", "hat")
        ):
            channels[name] = 9
        else:
            channels[name] = melodic_channels[melodic_index % len(melodic_channels)]
            melodic_index += 1
    owners = {name: owner for owner, name in enumerate(names)}
    seconds_per_tick = 60.0 / (bpm * 480)
    raw = []
    pitch_quantized = onset_quantized = end_quantized = duration_quantized = 0
    for row, note in zip(rows, notes):
        name = note.instrument or f"{backend} candidate"
        pitch = max(0, min(127, round(note.pitch)))
        start_tick = _label_split_seconds_to_ticks(note.start_seconds, bpm=bpm)
        end_tick = _label_split_seconds_to_ticks(note.end_seconds, bpm=bpm)
        if float(pitch) != note.pitch:
            pitch_quantized += 1
        if not math.isclose(
            start_tick * seconds_per_tick,
            note.start_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            onset_quantized += 1
        if not math.isclose(
            end_tick * seconds_per_tick,
            note.end_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            end_quantized += 1
        if not math.isclose(
            (end_tick - start_tick) * seconds_per_tick,
            note.end_seconds - note.start_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            duration_quantized += 1
        raw.append(
            MidiNoteInterval(
                owner=owners[name],
                channel=channels[name],
                start_tick=start_tick,
                end_tick=end_tick,
                pitch=pitch,
                velocity=int(row["audition_velocity"]),
            )
        )
    normalized = normalize_midi_intervals(raw)
    unique = {}
    for note in raw:
        key = (note.owner, note.channel, note.pitch, note.start_tick)
        existing = unique.get(key)
        safe_end = max(note.end_tick, note.start_tick + 1)
        if existing is None or safe_end > existing.end_tick:
            unique[key] = MidiNoteInterval(
                owner=note.owner,
                channel=note.channel,
                start_tick=note.start_tick,
                end_tick=safe_end,
                pitch=note.pitch,
                velocity=note.velocity,
            )
    voices: dict[tuple[int, int, int], list[Any]] = {}
    for note in unique.values():
        voices.setdefault((note.owner, note.channel, note.pitch), []).append(note)
    overlap_truncated = 0
    for voice in voices.values():
        voice.sort(key=lambda item: (item.start_tick, item.end_tick))
        overlap_truncated += sum(
            left.end_tick > right.start_tick
            for left, right in zip(voice, voice[1:])
        )
    changed = any(
        (
            pitch_quantized,
            onset_quantized,
            end_quantized,
            duration_quantized,
            sum(note.end_tick <= note.start_tick for note in raw),
            len(raw) - len(unique),
            overlap_truncated,
        )
    )
    summary = {
        "source_event_count": len(notes),
        "rendered_midi_note_count": len(normalized),
        "rendered_midi_note_signatures": [
            {
                "track_index": note.owner,
                "channel": note.channel,
                "start_tick": note.start_tick,
                "end_tick": note.end_tick,
                "pitch": note.pitch,
                "velocity": note.velocity,
            }
            for note in normalized
        ],
        "integer_pitch_quantized_event_count": pitch_quantized,
        "onset_tick_quantized_event_count": onset_quantized,
        "end_tick_quantized_event_count": end_quantized,
        "duration_tick_quantized_event_count": duration_quantized,
        "minimum_duration_extended_event_count": sum(
            note.end_tick <= note.start_tick for note in raw
        ),
        "duplicate_same_pitch_tick_onset_collapsed_event_count": (
            len(raw) - len(unique)
        ),
        "same_pitch_overlap_truncated_event_count": overlap_truncated,
        "source_event_to_midi_note_count_delta": len(normalized) - len(notes),
        "lossless_event_render": not changed,
    }
    signatures = sorted(
        (
            note.owner,
            note.channel,
            note.pitch,
            note.start_tick,
            note.end_tick,
            note.velocity,
        )
        for note in normalized
    )
    return summary, signatures


def _label_split_seconds_to_ticks(seconds: float, *, bpm: float) -> int:
    # Keep this expression identical to sunofriend.midi._seconds_to_ticks: the
    # order of floating-point operations can matter at an exact half tick.
    return int(round(seconds / (60.0 / bpm) * 480))


def _partition_source_index(value: Any) -> int:
    if not isinstance(value, Mapping):
        raise ValueError("adjacent AI label partition note must be an object")
    index = value.get("source_index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("adjacent AI label partition has an invalid source index")
    return index


def _partition_boundary_summary(
    rows: Sequence[Any], *, duration: float, start_seconds: float
) -> dict[str, Any]:
    notes = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("note"), Mapping):
            raise ValueError("adjacent AI label partition note evidence is invalid")
        notes.append(row["note"])
    boundaries = max(0, int((max(0.0, duration) - 1e-9) // 5.0))
    onset_count = 0
    crossing_count = 0
    for index in range(1, boundaries + 1):
        boundary = index * 5.0
        onset_count += sum(
            abs((float(note["start_seconds"]) - start_seconds) - boundary) <= 0.08
            for note in notes
        )
        crossing_count += sum(
            (float(note["start_seconds"]) - start_seconds)
            < boundary
            < (float(note["end_seconds"]) - start_seconds)
            for note in notes
        )
    return {
        "boundary_count": boundaries,
        "onsets_within_80ms": onset_count,
        "notes_crossing": crossing_count,
    }


def _workbench_boundary_summary(candidate, request, *, duration: float) -> dict[str, Any]:
    rows = []
    boundary_count = max(0, int((max(0.0, duration) - 1e-9) // 5.0))
    for index in range(1, boundary_count + 1):
        boundary = index * 5.0
        onsets = sum(
            abs((note.start_seconds - request.start_seconds) - boundary) <= 0.08
            for note in candidate.notes
        )
        crossings = sum(
            (note.start_seconds - request.start_seconds) < boundary
            < (note.end_seconds - request.start_seconds)
            for note in candidate.notes
        )
        rows.append(
            {
                "local_seconds": boundary,
                "onsets_within_80ms": onsets,
                "notes_crossing": crossings,
            }
        )
    return {
        "boundary_count": len(rows),
        "onsets_within_80ms": sum(row["onsets_within_80ms"] for row in rows),
        "notes_crossing": sum(row["notes_crossing"] for row in rows),
    }


def _path_free_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            name = str(key)
            normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            if _PATH_KEY.search(normalized) or any(
                token in normalized
                for token in ("workingdirectory", "filepath", "filename")
            ):
                continue
            cleaned = _path_free_value(item)
            if cleaned is not _REDACTED:
                result[name] = cleaned
        return result
    if isinstance(value, (list, tuple)):
        cleaned_items = [_path_free_value(item) for item in value]
        return [item for item in cleaned_items if item is not _REDACTED]
    if isinstance(value, str) and _looks_like_local_path(value):
        return _REDACTED
    return value


def _looks_like_local_path(value: str) -> bool:
    text = value.strip()
    lowered = text.lower()
    return bool(
        text.startswith(("/", "~/", "./", "../", "\\\\"))
        or lowered.startswith("file:")
        or re.match(r"^[a-zA-Z]:[\\/]", text)
        or "/" in text
        or "\\" in text
        or lowered.endswith(_PATH_SUFFIXES)
    )


def _discover_midi(roots: Sequence[Path]) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() in _MIDI_SUFFIXES:
                result.append(root.resolve())
            continue
        for path in root.rglob("*"):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            if path.is_file() and path.suffix.lower() in _MIDI_SUFFIXES:
                resolved = path.resolve()
                if not _is_within(resolved, root):
                    raise ValueError(
                        f"candidate MIDI symlink escapes its explicit root: {path}"
                    )
                result.append(resolved)
                if len(result) > _MAX_DISCOVERED_MIDI:
                    raise ValueError(
                        "candidate discovery found more than 5000 MIDI files; "
                        "use a narrower --candidate-root or explicit catalog"
                    )
    return sorted(set(result), key=lambda path: str(path).lower())


def _find_preview(midi: Path, roots: Sequence[Path]) -> Path | None:
    names = [
        midi.with_suffix(".preview.wav"),
        midi.with_suffix(".wav"),
        midi.parent / f"{midi.stem}.preview.wav",
    ]
    if midi.name.lower() == "performance.mid":
        names.extend(
            [
                midi.parent / "previews" / "best-matched-gm.wav",
                midi.parent / "best-matched-gm.wav",
                midi.parent / "previews" / "source-derived-performance.wav",
            ]
        )
    for path in names:
        if path.is_file():
            resolved = path.resolve()
            if not any(_is_within(resolved, root) for root in roots):
                raise ValueError(
                    f"candidate preview symlink escapes its explicit root: {path}"
                )
            return resolved
    return None


def infer_role(value: str) -> str | None:
    lowered = value.lower().replace("%20", " ")
    for role, aliases in _ROLE_ALIASES:
        for alias in aliases:
            pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
            if re.search(pattern, lowered):
                return role
    return None


def _describe_candidate(path: Path) -> tuple[str, str, str]:
    text = " ".join(path.parts[-5:]).lower()
    if "role-split" in text or "hybrid" in text or "combined" in text:
        return (
            "source-supported-hybrid",
            "Melody-focused combination",
            "A retained combination intended to separate or reinforce audible roles.",
        )
    if "demucs" in text or "cleanup" in text or "target" in text:
        return (
            "learned-cleanup",
            "Clearer-source experiment",
            "Transcription from a cleanup or target/residual experiment; compare by ear.",
        )
    if "muscriptor" in text or "candidate.expression" in text:
        return (
            "muscriptor-conditioned",
            "Role-conditioned AI transcription",
            "A model-backed challenger constrained by the requested musical role.",
        )
    if "melody" in path.stem.lower():
        return (
            "specialist-melody",
            "Melody-focused specialist",
            "A thinner specialist variant intended to retain the most melody-like line.",
        )
    if "accompaniment" in path.stem.lower():
        return (
            "specialist-accompaniment",
            "Accompaniment-focused specialist",
            "A specialist variant intended to retain chordal or supporting notes.",
        )
    if "raw-verified" in path.stem.lower():
        return (
            "specialist-raw-verified",
            "Strong observed notes only",
            "The verified raw note evidence before broader musical repair.",
        )
    if "root-safe" in path.stem.lower():
        return (
            "specialist-root-safe",
            "Chord-root-safe alternative",
            "A conservative chord-aware bass alternative retained for comparison.",
        )
    if any(marker in path.stem.lower() for marker in ("possible", "uncertain")):
        return (
            "diagnostic-evidence",
            "Low-confidence diagnostic notes",
            "Evidence retained for inspection; it is not a normal main-track candidate.",
        )
    if any(
        name in path.stem.lower()
        for name in ("listened", "baseline", "mode-repair", "mode_repair", "exact")
    ):
        return (
            "sunofriend-specialist",
            "Closest to the detected notes",
            "The conservative role-specific Sunofriend transcription.",
        )
    variant = path.stem.lower().split("-", 1)
    if len(variant) == 2:
        family = _human_label(variant[1])
        return (
            "specialist-role-variant",
            f"{family.title()} role layer",
            "A separated role/family layer from the specialist transcription.",
        )
    return (
        "alternative",
        "Alternative transcription",
        "An existing MIDI alternative retained for listening comparison.",
    )


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[int, int, int, str]:
    process_order = {
        "sunofriend-specialist": 0,
        "muscriptor-conditioned": 1,
        "source-supported-hybrid": 2,
        "specialist-melody": 2,
        "specialist-accompaniment": 3,
        "specialist-raw-verified": 3,
        "specialist-root-safe": 4,
        "specialist-role-variant": 4,
        "learned-cleanup": 5,
        "alternative": 6,
        "diagnostic-evidence": 9,
    }
    return (
        1 if candidate.get("diagnostic_only") else 0,
        process_order.get(str(candidate.get("process")), 9),
        0 if candidate.get("preview") else 1,
        str(candidate.get("midi_path", "")).lower(),
    )


def _deduplicate_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    hashes: set[str] = set()
    for candidate in candidates:
        digest = str(candidate.get("midi", {}).get("sha256", ""))
        if digest in hashes:
            continue
        hashes.add(digest)
        result.append(dict(candidate))
    return sorted(result, key=_candidate_sort_key)


def _candidate_roots(project: Path, roots: Sequence[str | Path]) -> list[Path]:
    result = [project]
    for value in roots:
        root = Path(value).expanduser().resolve()
        if not root.exists():
            raise ValueError(f"candidate root does not exist: {root}")
        if root not in result:
            result.append(root)
    return result


def _resolve_document_path(value: Any, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("workbench catalog path must be a non-empty string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return _existing_file(path, label="workbench artifact")


def _require_within(path: Path, roots: Sequence[Path], *, label: str) -> None:
    if not any(_is_within(path, root) for root in roots):
        raise ValueError(f"{label} is outside the explicit local project roots: {path}")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _existing_directory(value: str | Path, *, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"{label} directory does not exist: {path}")
    return path


def _existing_file(value: str | Path, *, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def _file_record(path: Path) -> dict[str, Any]:
    path = path.resolve()
    return {
        "path": str(path),
        "name": path.name,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _verify_ai_record(
    record: Any, *, label: str, root: Path | None = None
) -> Path:
    if not isinstance(record, Mapping):
        raise ValueError(f"adjacent AI run does not pin {label}")
    path = Path(str(record.get("path", ""))).expanduser()
    if root is not None and not path.is_absolute():
        path = root / path
    path = path.resolve()
    if root is not None:
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"adjacent AI artifact escapes its run: {label}") from exc
    if not path.is_file():
        raise ValueError(f"adjacent AI run file is missing: {label}")
    actual = _file_record(path)
    if (
        actual["bytes"] != record.get("bytes")
        or actual["sha256"] != record.get("sha256")
    ):
        raise ValueError(f"adjacent AI run artifact changed after completion: {label}")
    return path


def _ai_candidate_duration(candidate, request, metrics: Mapping[str, Any]) -> float:
    if request.end_seconds is not None:
        return max(0.0, request.end_seconds - request.start_seconds)
    excerpt = candidate.metadata.get("excerpt")
    if isinstance(excerpt, Mapping):
        value = excerpt.get("duration_seconds")
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    value = metrics.get("duration_seconds")
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        return float(value)
    if candidate.notes:
        return max(0.0, max(note.end_seconds for note in candidate.notes) - request.start_seconds)
    return 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read workbench catalog {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("workbench catalog must be a JSON object")
    return value


def _public_setup(setup: Mapping[str, Any]) -> dict[str, Any]:
    files = []
    for record in setup.get("files", []):
        files.append({key: value for key, value in record.items() if key != "path"})
    return {
        "bpm": setup.get("bpm"),
        "key": setup.get("key"),
        "tuning_hz": setup.get("tuning_hz"),
        "downbeat": setup.get("downbeat"),
        "files": files,
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("workbench text values must be non-empty strings")
    return value.strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("workbench warnings must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _human_label(value: str) -> str:
    return re.sub(r"[_-]+", " ", value).strip()
