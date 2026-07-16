"""Immutable, independently scored vocal tracker evidence and consensus.

This module deliberately sits beside the normal ``vocal-melody`` workflow.
It publishes pYIN frames, Basic Pitch note events and an optional existing
RMVPE frame record before creating any fused result.  Consensus is therefore
reproducible from hashed evidence and can never erase a tracker disagreement.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluate import evaluate_stem_midi
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .vocal_boundary import BoundaryProposal, repair_vocal_boundaries
from .vocal import (
    PitchFrame,
    VocalCandidate,
    VocalConfig,
    consensus_pitch_frames_with_audit,
    extract_backing_candidates,
    extract_pitch_frames,
    project_basic_pitch_candidates,
    transcribe_vocal_frames,
)


VOCAL_TRACKER_RUN_SCHEMA = "sunofriend.vocal-tracker-run.v1"
VOCAL_TRACKER_EVIDENCE_SCHEMA = "sunofriend.vocal-tracker-evidence.v1"
VOCAL_TRACKER_CONSENSUS_SCHEMA = "sunofriend.vocal-tracker-consensus.v1"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    label = path.relative_to(relative_to) if relative_to else path
    return {
        "path": str(label),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _new_run_id(audio_sha256: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-vocal-trackers-{audio_sha256[:8]}"


def _frame_values(frame: PitchFrame) -> list[Any]:
    return [
        frame.time,
        frame.f0_hz,
        frame.voiced_probability,
        frame.rms,
        frame.onset_strength,
        frame.source,
    ]


def _note_values(note: NoteEvent, *, confidence: float | None = None) -> dict[str, Any]:
    return {
        "start_seconds": note.start,
        "end_seconds": note.end,
        "pitch": note.pitch,
        "velocity": note.velocity,
        "confidence": confidence,
    }


def _tracker_midi(
    path: Path,
    notes: Sequence[NoteEvent],
    *,
    name: str,
    role: str,
    bpm: float,
    tuning_hz: float,
) -> None:
    channel, program = (2, 73) if role == "lead" else (3, 65)
    tuning_cents = 1200.0 * math.log2(tuning_hz / 440.0)
    write_midi_file(
        path,
        [
            MidiTrack(
                name,
                channel,
                program,
                list(notes),
                pitch_bend_cents=tuning_cents,
            )
        ],
        bpm=bpm,
    )


def _pypi_version(name: str) -> str:
    try:
        return version(name)
    except Exception:
        return "unknown"


def _basic_pitch_model_record() -> dict[str, Any]:
    from .transcribe_pitched import _model_path

    model = Path(_model_path()).absolute()
    return {
        **_file_record(model),
        "package": "basic-pitch",
        "package_version": _pypi_version("basic-pitch"),
    }


def _decoded_pyin_notes(
    frames: Sequence[PitchFrame],
    *,
    config: VocalConfig,
) -> list[NoteEvent]:
    # The independent record keeps the raw frames.  This note candidate is a
    # named deterministic adapter over those frames, not additional evidence.
    decoded = transcribe_vocal_frames(
        frames,
        config=replace(
            config,
            role="lead",
            tracker_mode="pyin",
            phrase_repair=False,
        ),
    )
    return list(decoded.variants.get("contour_clean", ()))


def _basic_pitch_notes(candidates: Sequence[VocalCandidate]) -> list[NoteEvent]:
    return sorted(
        (candidate.note for candidate in candidates),
        key=lambda note: (note.start, note.pitch, note.end),
    )


def load_rmvpe_evidence(
    frames_path: str | Path,
    *,
    source_sha256: str,
    reference_frames: Sequence[PitchFrame],
) -> tuple[list[PitchFrame], dict[str, Any]]:
    """Load a prior RMVPE record only when its immutable source hash matches."""

    path = Path(frames_path).expanduser().absolute()
    if not path.is_file():
        raise FileNotFoundError(f"RMVPE frame evidence does not exist: {path}")
    run_path = path.parent / "run.json"
    candidate_path = path.parent / "candidate.json"
    if not run_path.is_file() or not candidate_path.is_file():
        raise ValueError(
            "RMVPE evidence must remain beside its immutable run.json and candidate.json"
        )
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("status") != "complete" or run.get("backend") != "rmvpe":
        raise ValueError("RMVPE run must be a completed rmvpe backend record")
    recorded_source = run.get("source", {})
    if recorded_source.get("sha256") != source_sha256:
        raise ValueError("RMVPE source hash does not match the vocal tracker source")

    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "sunofriend.rmvpe-f0-frames.v1":
        raise ValueError("unsupported RMVPE frame evidence schema")
    excerpt = document.get("excerpt", {})
    if float(excerpt.get("start_seconds", 0.0)) != 0.0:
        raise ValueError("RMVPE evidence must start at zero for this source WAV")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    checkpoint_sha256 = run.get("checkpoint", {}).get("sha256")
    if not checkpoint_sha256 or (
        document.get("checkpoint_sha256") != checkpoint_sha256
        or candidate.get("metadata", {}).get("checkpoint_sha256")
        != checkpoint_sha256
    ):
        raise ValueError("RMVPE evidence checkpoint hash does not match its run")
    decoder = candidate.get("metadata", {}).get("note_decoder", {})
    confidence_threshold = float(decoder.get("confidence_threshold", 0.03))

    references = list(reference_frames)
    position = 0
    frames: list[PitchFrame] = []
    for raw in document.get("frames", []):
        if not isinstance(raw, list) or len(raw) < 3:
            raise ValueError("RMVPE frames must be [time, frequency, confidence]")
        time, frequency, confidence = map(float, raw[:3])
        while position + 1 < len(references) and abs(
            references[position + 1].time - time
        ) <= abs(references[position].time - time):
            position += 1
        reference = references[position] if references else None
        voiced = (
            frequency
            if math.isfinite(frequency)
            and frequency > 0
            and confidence >= confidence_threshold
            else None
        )
        frames.append(
            PitchFrame(
                time=time,
                f0_hz=voiced,
                voiced_probability=max(0.0, min(1.0, confidence)),
                rms=reference.rms if reference is not None else 0.0,
                onset_strength=(
                    reference.onset_strength if reference is not None else 0.0
                ),
                source="rmvpe",
            )
        )
    return frames, {
        "frames": _file_record(path),
        "run_manifest": _file_record(run_path),
        "candidate": _file_record(candidate_path),
        "checkpoint": run.get("checkpoint"),
        "model_version": candidate.get("model_version"),
        "confidence_threshold": confidence_threshold,
    }


def load_game_boundary_candidates(
    candidate_path: str | Path,
    *,
    source_sha256: str,
) -> tuple[list[BoundaryProposal], dict[str, Any]]:
    """Load raw GAME boundaries only from a matching immutable source run."""

    from .ai_runtime import AITranscriptionCandidate

    path = Path(candidate_path).expanduser().absolute()
    if not path.is_file():
        raise FileNotFoundError(f"GAME candidate does not exist: {path}")
    run_path = path.parent / "run.json"
    if not run_path.is_file():
        raise ValueError("GAME candidate must remain beside its immutable run.json")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("status") != "complete" or run.get("backend") != "game":
        raise ValueError("GAME run must be a completed game backend record")
    if run.get("source", {}).get("sha256") != source_sha256:
        raise ValueError("GAME source hash does not match the vocal tracker source")
    candidate = AITranscriptionCandidate.from_dict(
        json.loads(path.read_text(encoding="utf-8"))
    )
    if candidate.backend != "game":
        raise ValueError("boundary candidate must use the game backend")
    excerpt = candidate.metadata.get("excerpt", {})
    if float(excerpt.get("start_seconds", 0.0)) != 0.0:
        raise ValueError("GAME boundary evidence must start at zero for this source WAV")
    checkpoint_sha256 = run.get("checkpoint", {}).get("sha256")
    if (
        not checkpoint_sha256
        or candidate.metadata.get("checkpoint_sha256") != checkpoint_sha256
    ):
        raise ValueError("GAME candidate checkpoint hash does not match its run")

    velocities: dict[int, int] = {}
    expression_path = path.parent / "candidate.expression.json"
    if expression_path.is_file():
        expression = json.loads(expression_path.read_text(encoding="utf-8"))
        for record in expression.get("notes", []):
            if "candidate_index" in record and record.get("velocity") is not None:
                velocities[int(record["candidate_index"])] = int(record["velocity"])
    proposals = [
        BoundaryProposal(
            provider="game",
            source_event_id=note.source_event_id or f"game-{index}",
            start_seconds=note.start_seconds,
            end_seconds=note.end_seconds,
            pitch=note.pitch,
            confidence=note.confidence,
            velocity=note.velocity or velocities.get(index),
        )
        for index, note in enumerate(candidate.notes)
    ]
    record = {
        "candidate": _file_record(path),
        "run_manifest": _file_record(run_path),
        "checkpoint": run.get("checkpoint"),
        "model_version": candidate.model_version,
        "seed": candidate.metadata.get("seed"),
        "language": candidate.metadata.get("language"),
        "boundary_threshold": candidate.metadata.get("boundary_threshold"),
        "expression": (
            _file_record(expression_path) if expression_path.is_file() else None
        ),
    }
    return proposals, record


def _evaluation(
    path: Path,
    source: Path,
    midi_or_notes: str | Path | Sequence[NoteEvent],
) -> dict[str, Any]:
    # Score the serialized MIDI whenever one exists. This includes tick
    # rounding and the writer's overlap-safety policy rather than reporting
    # slightly more flattering pre-serialization event timing.
    report = evaluate_stem_midi(source, midi_or_notes, kind="lead")
    _atomic_json(path, report.to_dict())
    return report.to_dict()


def _headline(report: Mapping[str, Any]) -> dict[str, Any]:
    onsets = report["onsets"]
    pitched = report.get("pitched") or {}
    return {
        "notes": report["note_count"],
        "strong_onset_f1": onsets["strong"]["f1"],
        "possible_onset_f1": onsets["possible"]["f1"],
        "timing_p50_ms": onsets["timing"]["absolute_error_p50_ms"],
        "timing_p95_ms": onsets["timing"]["absolute_error_p95_ms"],
        "chroma_similarity": pitched.get("chroma_similarity"),
        "mean_pitch_support": pitched.get("mean_pitch_support"),
        "supported_note_ratio": pitched.get("supported_note_ratio"),
        "octave_accuracy": pitched.get("octave_accuracy"),
        "contour_direction_accuracy": pitched.get("contour_direction_accuracy"),
        "contour_pitch_correlation": pitched.get("contour_pitch_correlation"),
    }


def run_vocal_tracker_bakeoff(
    *,
    audio_path: str | Path,
    out_dir: str | Path,
    bpm: float,
    role: str,
    tuning_hz: float = 440.0,
    fmin_hz: float = 65.4,
    fmax_hz: float = 1046.5,
    rmvpe_frames_path: str | Path | None = None,
    game_candidate_path: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Publish raw trackers, optional consensus, and agreed-F0 boundary repairs."""

    source = Path(audio_path).expanduser().absolute()
    if not source.is_file():
        raise FileNotFoundError(f"vocal source does not exist: {source}")
    if role not in {"lead", "backing"}:
        raise ValueError("role must be lead or backing")
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("bpm must be finite and positive")
    if not math.isfinite(tuning_hz) or tuning_hz <= 0:
        raise ValueError("tuning_hz must be finite and positive")
    if game_candidate_path is not None and rmvpe_frames_path is None:
        raise ValueError("game_candidate_path requires rmvpe_frames_path")
    source_record = _file_record(source)
    game_proposals: list[BoundaryProposal] = []
    game_record = None
    if game_candidate_path is not None:
        game_proposals, game_record = load_game_boundary_candidates(
            game_candidate_path,
            source_sha256=source_record["sha256"],
        )
    identifier = run_id or _new_run_id(source_record["sha256"])
    if not _SAFE_RUN_ID.fullmatch(identifier):
        raise ValueError("run_id may contain only letters, numbers, dot, dash and underscore")
    run_dir = Path(out_dir).expanduser().absolute() / identifier
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"vocal tracker run already exists and will not be overwritten: {run_dir}"
        ) from exc

    config = VocalConfig(
        role=role,
        tuning_hz=tuning_hz,
        tuning_source="vocal-trackers-command",
        bpm=bpm,
        fmin_hz=fmin_hz,
        fmax_hz=fmax_hz,
        tracker_mode="consensus",
        phrase_repair=False,
    )
    pyin_frames = extract_pitch_frames(source, config=config)
    basic_candidates = extract_backing_candidates(source, config=config)
    pyin_notes = _decoded_pyin_notes(pyin_frames, config=config)
    basic_notes = _basic_pitch_notes(basic_candidates)

    pyin_evidence_path = run_dir / "pyin.evidence.json"
    basic_evidence_path = run_dir / "basic-pitch.evidence.json"
    pyin_midi_path = run_dir / "pyin.candidate.mid"
    basic_midi_path = run_dir / "basic-pitch.candidate.mid"
    pyin_evaluation_path = run_dir / "pyin.evaluation.json"
    basic_evaluation_path = run_dir / "basic-pitch.evaluation.json"
    _atomic_json(
        pyin_evidence_path,
        {
            "schema": VOCAL_TRACKER_EVIDENCE_SCHEMA,
            "tracker": "pyin",
            "source": source_record,
            "runtime": {
                "librosa_version": _pypi_version("librosa"),
                "numpy_version": _pypi_version("numpy"),
            },
            "parameters": {
                "fmin_hz": fmin_hz,
                "fmax_hz": fmax_hz,
                "hop_length": config.hop_length,
                "sample_rate": 22050,
                "tuning_hz": tuning_hz,
                "note_decoder": "sunofriend-contour-clean-v1-no-phrase-repair",
            },
            "frame_fields": [
                "time_seconds",
                "frequency_hz",
                "confidence",
                "rms",
                "onset_strength",
                "source",
            ],
            "frames": [_frame_values(frame) for frame in pyin_frames],
            "decoded_notes": [_note_values(note) for note in pyin_notes],
        },
    )
    _atomic_json(
        basic_evidence_path,
        {
            "schema": VOCAL_TRACKER_EVIDENCE_SCHEMA,
            "tracker": "basic-pitch",
            "source": source_record,
            "model": _basic_pitch_model_record(),
            "parameters": {
                "onset_threshold": 0.35,
                "frame_threshold": 0.22,
                "minimum_note_ms": max(45.0, config.min_note_ms),
                "fmin_hz": fmin_hz,
                "fmax_hz": fmax_hz,
                "melodia_trick": False,
                "multiple_pitch_bends": False,
                "pitch_policy": "raw integer Basic Pitch note events",
            },
            "notes": [
                _note_values(candidate.note, confidence=candidate.confidence)
                for candidate in basic_candidates
            ],
        },
    )
    _tracker_midi(
        pyin_midi_path,
        pyin_notes,
        name="pYIN independent candidate",
        role=role,
        bpm=bpm,
        tuning_hz=tuning_hz,
    )
    _tracker_midi(
        basic_midi_path,
        basic_notes,
        name="Basic Pitch independent candidate",
        role=role,
        bpm=bpm,
        tuning_hz=tuning_hz,
    )
    pyin_evaluation = _evaluation(pyin_evaluation_path, source, pyin_midi_path)
    basic_evaluation = _evaluation(
        basic_evaluation_path, source, basic_midi_path
    )

    trackers: dict[str, Sequence[PitchFrame]] = {
        "pyin": pyin_frames,
        "basic-pitch": project_basic_pitch_candidates(
            basic_candidates,
            config=config,
            reference_frames=pyin_frames,
        ),
    }
    rmvpe_record = None
    if rmvpe_frames_path is not None:
        rmvpe_frames, rmvpe_record = load_rmvpe_evidence(
            rmvpe_frames_path,
            source_sha256=source_record["sha256"],
            reference_frames=pyin_frames,
        )
        trackers["rmvpe"] = rmvpe_frames

    results: dict[str, Any] = {
        "pyin": {
            "evidence": str(pyin_evidence_path),
            "midi": str(pyin_midi_path),
            "evaluation": str(pyin_evaluation_path),
            "metrics": _headline(pyin_evaluation),
        },
        "basic-pitch": {
            "evidence": str(basic_evidence_path),
            "midi": str(basic_midi_path),
            "evaluation": str(basic_evaluation_path),
            "metrics": _headline(basic_evaluation),
        },
    }
    if rmvpe_record is not None:
        consensus_frames, audit = consensus_pitch_frames_with_audit(
            trackers,
            config=config,
        )
        consensus_notes = _decoded_pyin_notes(consensus_frames, config=config)
        consensus_path = run_dir / "consensus.evidence.json"
        consensus_midi_path = run_dir / "consensus.candidate.mid"
        consensus_evaluation_path = run_dir / "consensus.evaluation.json"
        classifications = Counter(record["classification"] for record in audit)
        selected_sources = Counter(
            record["selected"]["source"] for record in audit
        )
        input_records = {
            "pyin": _file_record(pyin_evidence_path, relative_to=run_dir),
            "basic-pitch": _file_record(basic_evidence_path, relative_to=run_dir),
            "rmvpe": rmvpe_record,
        }
        _atomic_json(
            consensus_path,
            {
                "schema": VOCAL_TRACKER_CONSENSUS_SCHEMA,
                "source": source_record,
                "policy": {
                    "name": "sunofriend-time-aligned-vocal-consensus-v1",
                    "base_timeline": "pyin",
                    "minimum_trackers": config.consensus_min_trackers,
                    "tolerance_cents": config.consensus_tolerance_cents,
                    "solo_policy": "retain pYIN below clean confidence",
                    "disagreement_policy": "retain every observation in alignment",
                },
                "inputs": input_records,
                "summary": {
                    "frames": len(audit),
                    "classifications": dict(sorted(classifications.items())),
                    "selected_sources": dict(sorted(selected_sources.items())),
                    "decoded_notes": len(consensus_notes),
                },
                "alignment": audit,
                "decoded_notes": [_note_values(note) for note in consensus_notes],
            },
        )
        _tracker_midi(
            consensus_midi_path,
            consensus_notes,
            name="Auditable three-tracker consensus v1",
            role=role,
            bpm=bpm,
            tuning_hz=tuning_hz,
        )
        consensus_evaluation = _evaluation(
            consensus_evaluation_path,
            source,
            consensus_midi_path,
        )
        results["consensus"] = {
            "status": "review-required",
            "evidence": str(consensus_path),
            "midi": str(consensus_midi_path),
            "evaluation": str(consensus_evaluation_path),
            "metrics": _headline(consensus_evaluation),
            "summary": {
                "classifications": dict(sorted(classifications.items())),
                "selected_sources": dict(sorted(selected_sources.items())),
            },
            "selection_policy": (
                "experimental challenger; independent evidence remains authoritative"
            ),
        }

        basic_proposals = [
            BoundaryProposal(
                provider="basic-pitch",
                source_event_id=f"basic-pitch-{index}",
                start_seconds=candidate.note.start,
                end_seconds=candidate.note.end,
                pitch=float(candidate.note.pitch),
                confidence=candidate.confidence,
                velocity=candidate.note.velocity,
            )
            for index, candidate in enumerate(basic_candidates)
        ]
        boundary_variants, boundary_document = repair_vocal_boundaries(
            audit,
            [*basic_proposals, *game_proposals],
            bpm=bpm,
        )
        boundary_path = run_dir / "boundary-repair.evidence.json"
        boundary_document.update(
            {
                "source": source_record,
                "role": role,
                "inputs": {
                    "consensus": _file_record(
                        consensus_path,
                        relative_to=run_dir,
                    ),
                    "basic-pitch": _file_record(
                        basic_evidence_path,
                        relative_to=run_dir,
                    ),
                    "game": game_record,
                },
                "backing_policy": (
                    "monophonic experimental line; raw polyphonic Basic Pitch "
                    "and the normal backing harmony stack remain separate"
                    if role == "backing"
                    else None
                ),
            }
        )
        _atomic_json(boundary_path, boundary_document)
        boundary_published: dict[str, Any] = {}
        file_tokens = {
            "basic-pitch": "boundary-basic-pitch",
            "game": "boundary-game",
            "combined": "boundary-repair",
        }
        for variant_name, notes in sorted(boundary_variants.items()):
            token = file_tokens[variant_name]
            midi_path = run_dir / f"{token}.candidate.mid"
            evaluation_path = run_dir / f"{token}.evaluation.json"
            _tracker_midi(
                midi_path,
                notes,
                name=f"Agreed F0 {variant_name} boundaries",
                role=role,
                bpm=bpm,
                tuning_hz=tuning_hz,
            )
            evaluation = _evaluation(evaluation_path, source, midi_path)
            boundary_published[variant_name] = {
                "status": "review-required" if notes else "no-evidence",
                "notes": len(notes),
                "midi": str(midi_path),
                "evaluation": str(evaluation_path),
                "metrics": _headline(evaluation),
            }
        results["boundary-repair"] = {
            "status": boundary_published["combined"]["status"],
            "evidence": str(boundary_path),
            "primary_variant": "combined",
            "variants": boundary_published,
            "summary": boundary_document["summary"],
            "selection_policy": (
                "experimental boundaries only; pitch requires pYIN+RMVPE agreement; "
                "raw candidates remain authoritative"
            ),
        }

    artifacts = {
        path.name: _file_record(path, relative_to=run_dir)
        for path in sorted(run_dir.iterdir())
        if path.is_file()
    }
    manifest = {
        "schema": VOCAL_TRACKER_RUN_SCHEMA,
        "run_id": identifier,
        "status": "complete",
        "source": source_record,
        "role": role,
        "bpm": bpm,
        "tuning_hz": tuning_hz,
        "trackers": [
            "pyin",
            "basic-pitch",
            *(["rmvpe"] if rmvpe_record else []),
        ],
        "boundary_sources": [
            *(["basic-pitch"] if rmvpe_record else []),
            *(["game"] if game_record else []),
        ],
        "consensus_created": rmvpe_record is not None,
        "boundary_repair_created": rmvpe_record is not None,
        "results": results,
        "artifacts": artifacts,
        "immutable": True,
    }
    _atomic_json(run_dir / "run.json", manifest)
    return manifest


__all__ = [
    "VOCAL_TRACKER_CONSENSUS_SCHEMA",
    "VOCAL_TRACKER_EVIDENCE_SCHEMA",
    "VOCAL_TRACKER_RUN_SCHEMA",
    "load_game_boundary_candidates",
    "load_rmvpe_evidence",
    "run_vocal_tracker_bakeoff",
]
