"""Immutable execution records for isolated AI transcription workers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ai_runtime import (
    AI_MODEL_MANIFESTS,
    GAME_MODEL_FILENAMES,
    AITranscriptionCandidate,
    AITranscriptionRequest,
    collect_ai_diagnostics,
    resolve_ai_python,
)
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent


AI_RUN_SCHEMA = "sunofriend.ai-bakeoff-run.v1"
AI_GM_PROGRAM_MAPPING_SCHEMA = "sunofriend.ai-gm-program-mapping.v1"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Zero-based General MIDI programs used only for an immediately intelligible
# audition.  The model's instrument label and raw notes remain authoritative
# evidence; this map neither identifies a GarageBand patch nor changes a note.
AI_GM_PROGRAMS = {
    "acoustic_piano": 0,
    "electric_piano": 4,
    "chromatic_percussion": 11,
    "organ": 16,
    "acoustic_guitar": 24,
    "clean_electric_guitar": 27,
    "distorted_electric_guitar": 30,
    "acoustic_bass": 32,
    "electric_bass": 33,
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "contrabass": 43,
    "orchestral_harp": 46,
    "timpani": 47,
    "string_ensemble": 48,
    "synth_strings": 50,
    "voice": 52,
    "orchestra_hit": 55,
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "french_horn": 60,
    "brass_section": 61,
    "soprano_and_alto_sax": 64,
    "tenor_sax": 66,
    "baritone_sax": 67,
    "oboe": 68,
    "english_horn": 69,
    "bassoon": 70,
    "clarinet": 71,
    "flutes": 73,
    "synth_lead": 81,
    "synth_pad": 89,
}
AI_GM_PROGRAM_ALIASES = {
    "piano": "acoustic_piano",
    "keys": "electric_piano",
    "bass": "electric_bass",
    "lead": "synth_lead",
    "lead_vocal": "voice",
    "lead_vocals": "voice",
    "backing": "voice",
    "backing_vocal": "voice",
    "backing_vocals": "voice",
    "vocal": "voice",
    "vocals": "voice",
    "strings": "string_ensemble",
    "pads": "synth_pad",
    "flute": "flutes",
}


class AIWorkerRunError(RuntimeError):
    """An isolated worker failed after its immutable run directory was made."""

    def __init__(self, message: str, run_dir: Path):
        super().__init__(f"{message}; immutable run record: {run_dir}")
        self.run_dir = run_dir


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


def _game_bundle_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    components: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for name in GAME_MODEL_FILENAMES:
        component = path / name
        record = _file_record(component, relative_to=path)
        components[name] = record
        total_bytes += record["bytes"]
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        with component.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return {
        "path": str(path),
        "kind": "directory",
        "bytes": total_bytes,
        "sha256": digest.hexdigest(),
        "components": components,
    }


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_run_id(backend: str, audio_sha256: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{backend}-{audio_sha256[:8]}"


def _validate_checkpoint(path: Path, backend: str) -> None:
    if not path.is_absolute():
        raise ValueError("checkpoint must be an absolute, existing local path")
    if backend == "muscriptor":
        if not path.is_file():
            raise ValueError("MuScriptor checkpoint must be an existing local file")
        if path.suffix.lower() != ".safetensors":
            raise ValueError("MuScriptor checkpoint must be a .safetensors file")
    elif backend == "game":
        if not path.is_dir():
            raise ValueError("GAME checkpoint must be an existing local ONNX directory")
        missing = [name for name in GAME_MODEL_FILENAMES if not (path / name).is_file()]
        if missing:
            raise ValueError("GAME ONNX bundle is incomplete; missing: " + ", ".join(missing))
    elif backend == "rmvpe":
        if not path.is_file():
            raise ValueError("RMVPE checkpoint must be an existing local file")
        if path.suffix.lower() != ".onnx":
            raise ValueError("RMVPE checkpoint must be an .onnx file")
    elif backend == "pesto":
        if not path.is_file():
            raise ValueError("PESTO checkpoint must be an existing local file")
        if path.suffix.lower() != ".ckpt":
            raise ValueError("PESTO checkpoint must be a .ckpt file")
    else:
        raise ValueError(f"the current worker does not support backend: {backend}")


def _raw_artifact_paths(
    candidate: AITranscriptionCandidate, run_dir: Path
) -> list[Path]:
    """Resolve worker-declared artifacts while preventing path escape."""

    paths: list[Path] = []
    root = run_dir.resolve()
    for label in candidate.raw_artifacts:
        relative = Path(label)
        if relative.is_absolute():
            raise ValueError("AI raw artifact paths must be relative to the run")
        path = run_dir / relative
        resolved = path.resolve()
        if resolved == root or root not in resolved.parents:
            raise ValueError("AI raw artifact path escapes the immutable run")
        if not resolved.is_file():
            raise ValueError(f"AI worker declared a missing raw artifact: {label}")
        paths.append(path)
    return paths


def _candidate_tracks(
    candidate: AITranscriptionCandidate,
    *,
    velocities: Sequence[int] | None = None,
) -> list[MidiTrack]:
    if velocities is not None and len(velocities) != len(candidate.notes):
        raise ValueError("velocity count does not match the AI candidate")
    grouped: dict[str, list[NoteEvent]] = defaultdict(list)
    for index, note in enumerate(candidate.notes):
        name = note.instrument or f"{candidate.backend} candidate"
        velocity = (
            int(velocities[index])
            if velocities is not None
            else (note.velocity or 90)
        )
        grouped[name].append(
            NoteEvent(
                start=note.start_seconds,
                end=note.end_seconds,
                pitch=max(0, min(127, round(note.pitch))),
                velocity=velocity,
            )
        )
    if not grouped:
        grouped[f"{candidate.backend} candidate"] = []

    melodic_channels = [channel for channel in range(16) if channel != 9]
    tracks: list[MidiTrack] = []
    melodic_index = 0
    for name in sorted(grouped):
        lowered = name.lower()
        is_drums = any(
            token in lowered
            for token in ("drum", "percussion", "cymbal", "snare", "kick", "hat")
        )
        if is_drums:
            channel = 9
        else:
            channel = melodic_channels[melodic_index % len(melodic_channels)]
            melodic_index += 1
        tracks.append(
            MidiTrack(
                name=name,
                channel=channel,
                program=_gm_program_for_instrument(name),
                notes=sorted(
                    grouped[name], key=lambda note: (note.start, note.pitch, note.end)
                ),
            )
        )
    return tracks


def _canonical_instrument_label(name: str) -> str:
    label = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return AI_GM_PROGRAM_ALIASES.get(label, label)


def _gm_program_for_instrument(name: str) -> int:
    """Return a conservative GM audition program without altering model evidence."""

    return AI_GM_PROGRAMS.get(_canonical_instrument_label(name), 0)


def _gm_program_mapping(candidate: AITranscriptionCandidate) -> dict[str, Any]:
    tracks = _candidate_tracks(candidate)
    return {
        "schema": AI_GM_PROGRAM_MAPPING_SCHEMA,
        "status": "complete",
        "policy": "canonical-instrument-label-v1",
        "purpose": "General MIDI audition only; not a GarageBand patch identification.",
        "raw_candidate_mutated": False,
        "notes_mutated": 0,
        "tracks": [
            {
                "instrument": track.name,
                "channel": track.channel,
                "program": track.program,
                "matched_label": (
                    _canonical_instrument_label(track.name) in AI_GM_PROGRAMS
                ),
                "note_count": len(track.notes),
            }
            for track in tracks
        ],
    }


def run_ai_transcription(
    *,
    audio_path: str | Path,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    bpm: float,
    backend: str = "muscriptor",
    roles: Sequence[str] = (),
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    options: Mapping[str, Any] | None = None,
    python: str | Path | None = None,
    worker_path: str | Path | None = None,
    timeout_seconds: float = 1800.0,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one backend without overwriting inputs or a previous run."""

    audio = Path(audio_path).expanduser().absolute()
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    if backend not in AI_MODEL_MANIFESTS:
        raise ValueError(
            "backend must be one of: " + ", ".join(sorted(AI_MODEL_MANIFESTS))
        )
    if not audio.is_file():
        raise ValueError(f"audio does not exist: {audio}")
    _validate_checkpoint(checkpoint, backend)
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("bpm must be finite and positive")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")

    executable = resolve_ai_python(python)
    worker = (
        Path(worker_path).expanduser().absolute()
        if worker_path
        else Path(__file__).with_name("ai_worker.py")
    )
    if not worker.is_file():
        raise FileNotFoundError(f"AI worker was not found: {worker}")

    audio_record = _file_record(audio)
    checkpoint_record = (
        _game_bundle_record(checkpoint)
        if backend == "game"
        else {**_file_record(checkpoint), "kind": "file"}
    )
    request_options = dict(options or {})
    request_options["model_path"] = str(checkpoint)
    request_options["model_sha256"] = checkpoint_record["sha256"]
    request = AITranscriptionRequest(
        audio_path=str(audio),
        backend=backend,
        roles=tuple(roles),
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        options=request_options,
    )
    request.validate()

    identifier = run_id or _new_run_id(backend, audio_record["sha256"])
    if not _SAFE_RUN_ID.fullmatch(identifier):
        raise ValueError("run_id may contain only letters, numbers, dot, dash and underscore")
    run_dir = Path(out_dir).expanduser().absolute() / identifier
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"AI run already exists and will not be overwritten: {run_dir}"
        ) from exc

    request_path = run_dir / "request.json"
    raw_candidate_path = run_dir / "candidate.raw.json"
    candidate_path = run_dir / "candidate.json"
    quality_path = run_dir / "candidate.quality.json"
    midi_path = run_dir / "candidate.mid"
    program_mapping_path = run_dir / "candidate.programs.json"
    expression_path = run_dir / "candidate.expression.json"
    expression_midi_path = run_dir / "candidate.expression.mid"
    stdout_path = run_dir / "worker.stdout.log"
    stderr_path = run_dir / "worker.stderr.log"
    started_path = run_dir / "run.started.json"
    run_path = run_dir / "run.json"
    command = [
        str(executable),
        str(worker),
        "--request",
        str(request_path),
        "--output",
        str(raw_candidate_path),
    ]
    started_at = _utc_now()
    started_clock = time.monotonic()
    _atomic_json(request_path, request.to_dict())
    _atomic_json(
        started_path,
        {
            "schema": AI_RUN_SCHEMA,
            "run_id": identifier,
            "status": "running",
            "started_at": started_at,
            "command": command,
            "source": audio_record,
            "checkpoint": checkpoint_record,
            "backend_manifest": asdict(AI_MODEL_MANIFESTS[backend]),
        },
    )

    exit_code: int | None = None
    error: str | None = None
    candidate: AITranscriptionCandidate | None = None
    raw_artifact_paths: list[Path] = []
    expression_record: dict[str, Any] = {
        "status": "not-run",
        "policy": "source-relative-energy-v1",
        "raw_candidate_mutated": False,
    }
    quality_record: dict[str, Any] = {
        "status": "not-run",
        "promotion_allowed": False,
        "raw_candidate_mutated": False,
    }
    program_mapping_record: dict[str, Any] = {
        "status": "not-run",
        "raw_candidate_mutated": False,
        "notes_mutated": 0,
    }
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        if exit_code != 0:
            error = f"worker exited with status {exit_code}"
        elif not raw_candidate_path.is_file():
            error = "worker completed without writing candidate.raw.json"
        else:
            raw_document = json.loads(raw_candidate_path.read_text(encoding="utf-8"))
            candidate = AITranscriptionCandidate.from_dict(raw_document)
            if candidate.backend != backend:
                raise ValueError(
                    f"worker returned {candidate.backend}, expected {backend}"
                )
            if (
                candidate.metadata.get("checkpoint_sha256")
                != checkpoint_record["sha256"]
            ):
                raise ValueError(
                    "worker checkpoint hash does not match the pre-inference hash"
                )
            raw_artifact_paths = _raw_artifact_paths(candidate, run_dir)
            _atomic_json(candidate_path, candidate.to_dict())
            try:
                from .ai_quality import assess_candidate_quality

                quality = assess_candidate_quality(candidate, requested_roles=roles)
                _atomic_json(quality_path, quality)
                quality_record = {
                    "status": quality["status"],
                    "promotion_allowed": quality["promotion_allowed"],
                    "metrics": quality["metrics"],
                    "warnings": quality["warnings"],
                    "raw_candidate_mutated": False,
                }
            except Exception as exc:
                quality_record = {
                    "status": "unavailable",
                    "promotion_allowed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "raw_candidate_mutated": False,
                }
                _atomic_json(
                    quality_path,
                    {
                        "schema": "sunofriend.ai-candidate-quality.v1",
                        **quality_record,
                    },
                )
            program_mapping_record = _gm_program_mapping(candidate)
            _atomic_json(program_mapping_path, program_mapping_record)
            write_midi_file(midi_path, _candidate_tracks(candidate), bpm=bpm)
            try:
                from .ai_expression import (
                    expression_velocities,
                    recover_source_expression,
                )

                expression = recover_source_expression(audio, candidate)
                _atomic_json(expression_path, expression)
                velocities = expression_velocities(
                    expression,
                    expected_notes=len(candidate.notes),
                )
                write_midi_file(
                    expression_midi_path,
                    _candidate_tracks(candidate, velocities=velocities),
                    bpm=bpm,
                )
                expression_record = {
                    "status": expression["status"],
                    "policy": expression["policy"]["name"],
                    "raw_candidate_mutated": False,
                    "velocity_summary": expression["velocity_summary"],
                }
            except Exception as exc:
                expression_record = {
                    "status": "unavailable",
                    "policy": "source-relative-energy-v1",
                    "raw_candidate_mutated": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                _atomic_json(
                    expression_path,
                    {
                        "schema": "sunofriend.ai-source-expression.v1",
                        **expression_record,
                    },
                )
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        error = f"worker timed out after {timeout_seconds:g} seconds"
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if not stdout_path.exists():
            stdout_path.write_text("", encoding="utf-8")
        if not stderr_path.exists():
            stderr_path.write_text(error + "\n", encoding="utf-8")

    completed_at = _utc_now()
    elapsed_seconds = time.monotonic() - started_clock
    artifacts = {}
    recorded_paths = [
        request_path,
        raw_candidate_path,
        candidate_path,
        quality_path,
        midi_path,
        program_mapping_path,
        expression_path,
        expression_midi_path,
        stdout_path,
        stderr_path,
        started_path,
        *raw_artifact_paths,
    ]
    for path in recorded_paths:
        if path.is_file():
            artifacts[path.name] = _file_record(path, relative_to=run_dir)
    manifest: dict[str, Any] = {
        "schema": AI_RUN_SCHEMA,
        "run_id": identifier,
        "status": "complete" if error is None else "failed",
        "started_at": started_at,
        "completed_at": completed_at,
        "elapsed_seconds": elapsed_seconds,
        "backend": backend,
        "backend_manifest": asdict(AI_MODEL_MANIFESTS[backend]),
        "runtime": collect_ai_diagnostics(executable),
        "worker": _file_record(worker),
        "command": command,
        "exit_code": exit_code,
        "source": audio_record,
        "checkpoint": checkpoint_record,
        "bpm": bpm,
        "note_count": len(candidate.notes) if candidate else 0,
        "candidate_quality": quality_record,
        "postprocessing": {
            "source_velocity": expression_record,
            "gm_program_mapping": program_mapping_record,
        },
        "artifacts": artifacts,
        "error": error,
    }
    _atomic_json(run_path, manifest)
    if error is not None:
        raise AIWorkerRunError(error, run_dir)
    return manifest


__all__ = [
    "AI_GM_PROGRAM_MAPPING_SCHEMA",
    "AI_RUN_SCHEMA",
    "AIWorkerRunError",
    "run_ai_transcription",
]
