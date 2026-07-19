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
) -> dict[str, Any]:
    source_record = _file_record(source)
    stem_identity = "\0".join(
        (str(source_record["sha256"]), role, source.name.casefold())
    ).encode("utf-8")
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
    ai_diagnostics = _ai_candidate_diagnostics(midi, midi_record)
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
            marker in lower_name for marker in ("possible", "uncertain", "rejected")
        ) or blocked,
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
        _verify_ai_record(record, root=midi.parent, label=name)
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
        return {
            key: _path_free_value(item)
            for key, item in value.items()
            if key not in {"path", "model_path", "model_config_path"}
        }
    if isinstance(value, list):
        return [_path_free_value(item) for item in value]
    return value


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
