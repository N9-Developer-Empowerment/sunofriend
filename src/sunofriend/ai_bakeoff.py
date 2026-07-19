"""Immutable execution records for isolated AI transcription workers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
from copy import deepcopy
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
    collect_ai_runtime_fingerprint,
    resolve_ai_python,
)
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent


AI_RUN_SCHEMA = "sunofriend.ai-bakeoff-run.v1"
AI_GM_PROGRAM_MAPPING_SCHEMA = "sunofriend.ai-gm-program-mapping.v1"
MUSCRIPTOR_EXECUTION_SCHEMA = "sunofriend.muscriptor-execution.v1"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MUSCRIPTOR_MODEL_SIZES = {"small", "medium", "large"}

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
MUSCRIPTOR_INSTRUMENT_ROLES = frozenset({*AI_GM_PROGRAMS, "drums"})
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
        _muscriptor_model_config(path)
    elif backend == "game":
        if not path.is_dir():
            raise ValueError("GAME checkpoint must be an existing local ONNX directory")
        missing = [name for name in GAME_MODEL_FILENAMES if not (path / name).is_file()]
        if missing:
            raise ValueError(
                "GAME ONNX bundle is incomplete; missing: " + ", ".join(missing)
            )
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


def _muscriptor_model_config(checkpoint: Path) -> tuple[Path, dict[str, Any]]:
    """Read the architecture config which MuScriptor loads beside its weights."""

    config = checkpoint.with_name("config.json")
    if not config.is_file():
        raise ValueError(
            "MuScriptor checkpoint requires an adjacent config.json so the "
            "model architecture and size can be pinned"
        )
    try:
        document = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid MuScriptor config.json: {exc}") from exc
    if not isinstance(document, dict) or document.get("model_type") != "muscriptor":
        raise ValueError("MuScriptor config.json must declare model_type=muscriptor")
    variant = document.get("variant")
    if variant not in _MUSCRIPTOR_MODEL_SIZES:
        raise ValueError(
            "MuScriptor config.json variant must be small, medium or large"
        )
    return config, document


def _muscriptor_checkpoint_record(checkpoint: Path) -> dict[str, Any]:
    config_path, config = _muscriptor_model_config(checkpoint)
    return {
        **_file_record(checkpoint),
        "kind": "file",
        "variant": config["variant"],
        "model_config": config,
        "config": _file_record(config_path),
    }


def _normalise_muscriptor_options(
    options: Mapping[str, Any], checkpoint_record: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pin every effective MuScriptor 0.2.1 decoding control.

    The released runtime has independent five-second chunks and no prelude
    forcing API.  That absence is explicit evidence: requesting the newer
    behaviour is rejected instead of silently accepting a no-op flag.
    """

    normalised = dict(options)
    model_size = str(normalised.get("model_size", "auto"))
    actual_size = str(checkpoint_record["variant"])
    if model_size not in {*_MUSCRIPTOR_MODEL_SIZES, "auto"}:
        raise ValueError("MuScriptor model_size must be auto, small, medium or large")
    if model_size != "auto" and model_size != actual_size:
        raise ValueError(
            f"requested MuScriptor model_size={model_size}, but config.json is {actual_size}"
        )

    beam_size = int(normalised.get("beam_size", 1))
    batch_size = int(normalised.get("batch_size", 1))
    cfg_coef = float(normalised.get("cfg_coef", 1.0))
    temperature = float(normalised.get("temperature", 1.0))
    use_sampling = normalised.get("use_sampling", False)
    no_eos_is_ok = normalised.get("no_eos_is_ok", True)
    prelude_forcing = normalised.get("prelude_forcing", False)
    if beam_size < 1:
        raise ValueError("MuScriptor beam_size must be positive")
    if batch_size < 1:
        raise ValueError("MuScriptor batch_size must be positive")
    if not math.isfinite(cfg_coef) or cfg_coef < 0:
        raise ValueError("MuScriptor cfg_coef must be finite and non-negative")
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("MuScriptor temperature must be finite and positive")
    if not isinstance(use_sampling, bool) or not isinstance(no_eos_is_ok, bool):
        raise ValueError("MuScriptor sampling and EOS controls must be booleans")
    if not isinstance(prelude_forcing, bool):
        raise ValueError("MuScriptor prelude_forcing must be a boolean")
    if prelude_forcing:
        raise ValueError(
            "MuScriptor 0.2.1 does not support prelude forcing; use false until "
            "a separately pinned supporting runtime is installed"
        )
    if use_sampling and beam_size > 1:
        raise ValueError("MuScriptor sampling and beam search cannot be combined")

    normalised.update(
        {
            "model_size": actual_size,
            "beam_size": beam_size,
            "batch_size": batch_size,
            "cfg_coef": cfg_coef,
            "temperature": temperature,
            "use_sampling": use_sampling,
            "no_eos_is_ok": no_eos_is_ok,
            "prelude_forcing": False,
            "prelude_forcing_supported": False,
            "chunk_seconds": 5.0,
        }
    )
    execution = {
        "schema": MUSCRIPTOR_EXECUTION_SCHEMA,
        "model_size": actual_size,
        "decoding": {
            "strategy": (
                "sampling"
                if use_sampling
                else ("beam-search" if beam_size > 1 else "greedy")
            ),
            "beam_size": beam_size,
            "batch_size": batch_size,
            "cfg_coef": cfg_coef,
            "temperature": temperature,
            "use_sampling": use_sampling,
            "no_eos_is_ok": no_eos_is_ok,
        },
        "chunking": {
            "seconds": 5.0,
            "policy": "independent-five-second-chunks",
            "prelude_forcing": False,
            "prelude_forcing_supported": False,
        },
    }
    return normalised, execution


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
            int(velocities[index]) if velocities is not None else (note.velocity or 90)
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


def prepare_ai_transcription_request(
    *,
    audio_path: str | Path,
    checkpoint_path: str | Path,
    backend: str = "muscriptor",
    roles: Sequence[str] = (),
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    options: Mapping[str, Any] | None = None,
) -> tuple[
    AITranscriptionRequest,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
]:
    """Build the exact hash-pinned request used by one-shot and session runs."""

    audio = Path(audio_path).expanduser().absolute()
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    if backend not in AI_MODEL_MANIFESTS:
        raise ValueError(
            "backend must be one of: " + ", ".join(sorted(AI_MODEL_MANIFESTS))
        )
    if not audio.is_file():
        raise ValueError(f"audio does not exist: {audio}")
    _validate_checkpoint(checkpoint, backend)
    audio_record = _file_record(audio)
    if backend == "game":
        checkpoint_record = _game_bundle_record(checkpoint)
    elif backend == "muscriptor":
        checkpoint_record = _muscriptor_checkpoint_record(checkpoint)
    else:
        checkpoint_record = {**_file_record(checkpoint), "kind": "file"}
    request_options = dict(options or {})
    execution: dict[str, Any] | None = None
    if backend == "muscriptor":
        request_options, execution = _normalise_muscriptor_options(
            request_options, checkpoint_record
        )
    request_options["model_path"] = str(checkpoint)
    request_options["model_sha256"] = checkpoint_record["sha256"]
    if backend == "muscriptor":
        config_record = checkpoint_record["config"]
        request_options["model_config_path"] = config_record["path"]
        request_options["model_config_sha256"] = config_record["sha256"]
        if execution is not None:
            execution = {
                **execution,
                "model_config_sha256": config_record["sha256"],
            }
    request = AITranscriptionRequest(
        audio_path=str(audio),
        backend=backend,
        roles=tuple(roles),
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        options=request_options,
    )
    request.validate()
    return request, audio_record, checkpoint_record, execution


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
    worker_session: Any | None = None,
    application_cache_dir: str | Path | None = None,
    _prepared_inputs: tuple[
        AITranscriptionRequest,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any] | None,
    ]
    | None = None,
    timeout_seconds: float = 1800.0,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one backend without overwriting inputs or a previous run."""

    audio = Path(audio_path).expanduser().absolute()
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("bpm must be finite and positive")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    cache_command_started_at = _utc_now() if application_cache_dir is not None else None
    cache_command_started_clock = (
        time.monotonic() if application_cache_dir is not None else None
    )
    cache_preflight_seconds: float | None = None

    executable = resolve_ai_python(python)
    worker = (
        Path(worker_path).expanduser().absolute()
        if worker_path
        else Path(__file__).with_name("ai_worker.py")
    )
    if not worker.is_file():
        raise FileNotFoundError(f"AI worker was not found: {worker}")
    worker_record = _file_record(worker)
    if worker_session is not None:
        if backend != "muscriptor":
            raise ValueError(
                "persistent worker sessions currently support MuScriptor only"
            )
        if Path(worker_session.worker_path).resolve() != worker.resolve():
            raise ValueError("persistent session worker differs from requested worker")
        if Path(worker_session.python).resolve() != executable.resolve():
            raise ValueError(
                "persistent session interpreter differs from requested Python"
            )
        if worker_session.worker_sha256 != worker_record["sha256"]:
            raise ValueError("persistent session worker changed after startup")
        if not math.isclose(float(worker_session.bpm), float(bpm), abs_tol=1e-9):
            raise ValueError("persistent session BPM differs from requested BPM")
    if application_cache_dir is not None:
        if backend != "muscriptor":
            raise ValueError("AI application cache v1 supports MuScriptor only")
        unknown_roles = sorted(set(roles) - MUSCRIPTOR_INSTRUMENT_ROLES)
        if unknown_roles:
            raise ValueError(
                "AI application cache requires exact MuScriptor role(s): "
                + ", ".join(unknown_roles)
            )
        if worker_session is not None:
            raise ValueError(
                "AI application cache and persistent worker reuse are separate "
                "execution regimes"
            )
        cache_root = Path(application_cache_dir).expanduser().absolute().resolve()
        output_root = Path(out_dir).expanduser().absolute().resolve()
        if (
            cache_root == output_root
            or cache_root in output_root.parents
            or output_root in cache_root.parents
        ):
            raise ValueError(
                "AI application cache and immutable run output must not contain "
                "one another"
            )

    if _prepared_inputs is None:
        request, audio_record, checkpoint_record, execution = (
            prepare_ai_transcription_request(
                audio_path=audio,
                checkpoint_path=checkpoint,
                backend=backend,
                roles=roles,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                options=options,
            )
        )
    else:
        if worker_session is None:
            raise ValueError(
                "prepared AI inputs are only valid inside a worker session"
            )
        request, audio_record, checkpoint_record, execution = deepcopy(_prepared_inputs)
        if (
            request.audio_path != str(audio)
            or request.backend != backend
            or request.roles != tuple(roles)
            or request.start_seconds != start_seconds
            or request.end_seconds != end_seconds
            or request.options.get("model_path") != str(checkpoint)
            or audio_record.get("path") != str(audio)
            or checkpoint_record.get("path") != str(checkpoint)
        ):
            raise ValueError("prepared AI inputs differ from the requested session run")

    runtime_record: dict[str, Any] | None = None
    cache_identity: dict[str, Any] | None = None
    if application_cache_dir is not None:
        from .ai_cache import build_muscriptor_cache_identity

        runtime_record = collect_ai_runtime_fingerprint(executable)
        cache_identity = build_muscriptor_cache_identity(
            request=request,
            bpm=bpm,
            source=audio_record,
            checkpoint=checkpoint_record,
            worker=worker_record,
            runtime=runtime_record,
        )
        cache_preflight_seconds = time.monotonic() - float(cache_command_started_clock)

    identifier = run_id or _new_run_id(backend, audio_record["sha256"])
    if not _SAFE_RUN_ID.fullmatch(identifier):
        raise ValueError(
            "run_id may contain only letters, numbers, dot, dash and underscore"
        )
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
    cache_entry_path = run_dir / "cache.entry.json"
    cache_performance_path = run_dir / "cache.performance.json"
    cache_enabled = application_cache_dir is not None
    command = (
        list(worker_session.command)
        if worker_session is not None
        else [
            str(executable),
            str(worker),
            "--request",
            str(request_path),
            "--output",
            str(raw_candidate_path),
        ]
    )
    started_at = cache_command_started_at or _utc_now()
    started_clock = (
        float(cache_command_started_clock)
        if cache_command_started_clock is not None
        else time.monotonic()
    )
    _atomic_json(request_path, request.to_dict())
    _atomic_json(
        started_path,
        {
            "schema": AI_RUN_SCHEMA,
            "run_id": identifier,
            "status": "running",
            "started_at": started_at,
            "command": command,
            "worker_execution_mode": (
                "application-cache-read-through"
                if cache_enabled
                else (
                    "fresh-subprocess"
                    if worker_session is None
                    else "persistent-session-request"
                )
            ),
            "worker_process_started_for_run": (
                None if cache_enabled else worker_session is None
            ),
            "source": audio_record,
            "checkpoint": checkpoint_record,
            "worker": worker_record,
            "backend_manifest": asdict(AI_MODEL_MANIFESTS[backend]),
            "request": request.to_dict(),
            "execution": execution,
            "application_cache": (
                None
                if cache_identity is None
                else {
                    "schema": "sunofriend.ai-transcription-cache-event.v1",
                    "status": "lookup-pending",
                    "scope": cache_identity["scope"],
                    "key_sha256": cache_identity["key_sha256"],
                    "fallback_to_inference_on_invalid_entry": False,
                }
            ),
            "worker_transport": (
                None
                if worker_session is None
                else {
                    "mode": "bounded-persistent-session",
                    "transport": worker_session.ready["transport"],
                    "session_id": worker_session.session_id,
                    "worker_instance_id": worker_session.worker_instance_id,
                    "model_load_count": 1,
                }
            ),
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
    worker_subprocess_started_clock: float | None = None
    worker_subprocess_elapsed_seconds: float | None = None
    worker_request_elapsed_seconds: float | None = None
    worker_response: dict[str, Any] | None = None
    worker_process_started_for_run = False
    inference_executed_for_run = False
    model_loaded_for_run = False
    cache_entry: Any | None = None
    cache_hit = False
    cache_entry_published = False
    cache_lookup_seconds: float | None = None
    cache_materialise_seconds: float | None = None
    cache_store_seconds: float | None = None
    postprocess_started_clock: float | None = None
    postprocess_seconds: float | None = None
    try:
        if cache_enabled:
            from .ai_cache import (
                find_muscriptor_cache_entry,
                materialise_muscriptor_cache_entry,
            )

            lookup_started = time.monotonic()
            cache_entry = find_muscriptor_cache_entry(
                application_cache_dir, cache_identity
            )
            cache_lookup_seconds = time.monotonic() - lookup_started
            if cache_entry is not None:
                cache_hit = True
                materialise_started = time.monotonic()
                materialise_muscriptor_cache_entry(cache_entry, run_dir)
                cache_materialise_seconds = time.monotonic() - materialise_started
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text("", encoding="utf-8")
        if cache_hit:
            exit_code = None
        elif worker_session is None:
            worker_subprocess_started_clock = time.monotonic()
            worker_process_started_for_run = True
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            worker_subprocess_elapsed_seconds = (
                time.monotonic() - worker_subprocess_started_clock
            )
            exit_code = completed.returncode
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
        else:
            worker_subprocess_started_clock = time.monotonic()
            session_result = worker_session.execute(
                run_id=identifier,
                request_path=request_path,
                timeout_seconds=timeout_seconds,
            )
            worker_request_elapsed_seconds = float(session_result["elapsed_seconds"])
            exit_code = int(session_result["returncode"])
            worker_response = dict(session_result["response"])
            stdout_path.write_text(str(session_result["stdout"]), encoding="utf-8")
            stderr_path.write_text(str(session_result["stderr"]), encoding="utf-8")
        if not cache_hit and exit_code != 0:
            error = f"worker exited with status {exit_code}"
        elif not raw_candidate_path.is_file():
            error = "worker completed without writing candidate.raw.json"
        else:
            postprocess_started_clock = time.monotonic()
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
            # A launched worker is only an attempt.  Claim inference/model-load
            # execution after validated worker output provides positive evidence;
            # early exit, timeout and malformed-output failures remain conservative.
            if not cache_hit:
                inference_executed_for_run = True
                model_loaded_for_run = worker_session is None
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
            postprocess_seconds = time.monotonic() - postprocess_started_clock

    except subprocess.TimeoutExpired as exc:
        worker_subprocess_elapsed_seconds = time.monotonic() - float(
            worker_subprocess_started_clock
        )
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
        if (
            worker_session is None
            and worker_process_started_for_run
            and worker_subprocess_started_clock is not None
            and worker_subprocess_elapsed_seconds is None
        ):
            worker_subprocess_elapsed_seconds = (
                time.monotonic() - worker_subprocess_started_clock
            )
        if (
            worker_session is not None
            and worker_subprocess_started_clock is not None
            and worker_request_elapsed_seconds is None
        ):
            worker_request_elapsed_seconds = (
                time.monotonic() - worker_subprocess_started_clock
            )
        error = f"{type(exc).__name__}: {exc}"
        response_path = run_dir / "worker.response.json"
        if worker_session is not None and response_path.is_file():
            try:
                loaded_response = json.loads(response_path.read_text(encoding="utf-8"))
                if isinstance(loaded_response, dict):
                    worker_response = loaded_response
                    worker_request_elapsed_seconds = float(
                        loaded_response.get(
                            "request_elapsed_seconds",
                            worker_request_elapsed_seconds or 0.0,
                        )
                    )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        if not stdout_path.exists():
            stdout_path.write_text("", encoding="utf-8")
        if not stderr_path.exists():
            stderr_path.write_text(error + "\n", encoding="utf-8")

    if cache_enabled and error is None:
        try:
            config_record = checkpoint_record.get("config")
            config_path = (
                Path(str(config_record.get("path")))
                if isinstance(config_record, Mapping)
                else None
            )
            if _sha256(audio) != audio_record["sha256"]:
                raise ValueError("AI cache source changed before run completion")
            if _sha256(checkpoint) != checkpoint_record["sha256"]:
                raise ValueError("AI cache checkpoint changed before run completion")
            if (
                config_path is None
                or not config_path.is_file()
                or _sha256(config_path) != config_record["sha256"]
            ):
                raise ValueError("AI cache model config changed before run completion")
            if _sha256(worker) != worker_record["sha256"]:
                raise ValueError("AI cache worker changed before run completion")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if not stderr_path.exists():
                stderr_path.write_text(error + "\n", encoding="utf-8")

    if cache_enabled and not cache_hit and error is None:
        try:
            from .ai_cache import (
                copy_muscriptor_cache_entry_manifest,
                publish_muscriptor_cache_entry,
            )

            store_started = time.monotonic()
            cache_entry, cache_entry_published = publish_muscriptor_cache_entry(
                cache_dir=application_cache_dir,
                identity=cache_identity,
                run_dir=run_dir,
                origin={
                    "run_id": identifier,
                    "worker_execution_mode": "fresh-subprocess",
                    "worker_sha256": worker_record["sha256"],
                    "source_sha256": audio_record["sha256"],
                    "checkpoint_sha256": checkpoint_record["sha256"],
                },
            )
            cache_store_seconds = time.monotonic() - store_started
            copy_muscriptor_cache_entry_manifest(cache_entry, run_dir)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if not stderr_path.exists():
                stderr_path.write_text(error + "\n", encoding="utf-8")

    if cache_enabled:
        from .ai_cache import AI_CACHE_EVENT_SCHEMA

        if error is not None:
            cache_status = "failed"
        elif cache_hit:
            cache_status = "verified-hit"
        elif cache_entry_published:
            cache_status = "miss-stored"
        else:
            cache_status = "miss-verified-existing"
        entry_performance_record = (
            cache_entry.document.get("artifacts", {}).get("muscriptor.performance.json")
            if cache_entry is not None
            else None
        )
        run_origin_performance_matches_entry = (
            isinstance(entry_performance_record, Mapping)
            and (run_dir / "muscriptor.performance.json").is_file()
            and (run_dir / "muscriptor.performance.json").stat().st_size
            == entry_performance_record.get("bytes")
            and _sha256(run_dir / "muscriptor.performance.json")
            == entry_performance_record.get("sha256")
        )
        muscriptor_performance_is_current_run_inference = False
        performance_path = run_dir / "muscriptor.performance.json"
        if inference_executed_for_run and performance_path.is_file():
            try:
                performance_document = json.loads(
                    performance_path.read_text(encoding="utf-8")
                )
                muscriptor_performance_is_current_run_inference = (
                    isinstance(performance_document, Mapping)
                    and performance_document.get("schema")
                    == "sunofriend.muscriptor-performance.v1"
                    and performance_document.get("measurement_mode") == "fresh-process"
                )
            except (OSError, json.JSONDecodeError):
                muscriptor_performance_is_current_run_inference = False
        if run_origin_performance_matches_entry:
            origin_performance_semantics = (
                "The run's muscriptor.performance.json is the cache entry's "
                "original fresh-inference evidence; it is not cache-hit timing."
            )
        elif muscriptor_performance_is_current_run_inference:
            origin_performance_semantics = (
                "A concurrent identical producer won cache publication. The cache "
                "entry retains the winner's original performance, while this fresh "
                "miss retains its own muscriptor.performance.json."
            )
        else:
            origin_performance_semantics = (
                "No valid current-run MuScriptor inference performance artifact was "
                "produced."
            )
        cache_event = {
            "schema": AI_CACHE_EVENT_SCHEMA,
            "status": "complete" if error is None else "failed",
            "application_cache_status": cache_status,
            "scope": cache_identity["scope"],
            "key_sha256": cache_identity["key_sha256"],
            "entry_manifest_sha256": (
                cache_entry.manifest_sha256 if cache_entry is not None else None
            ),
            "entry_manifest_bytes": (
                cache_entry.manifest_bytes if cache_entry is not None else None
            ),
            "application_cache_hit": cache_hit,
            "entry_published_by_run": cache_entry_published,
            "inference_executed_for_run": inference_executed_for_run,
            "worker_process_started_for_run": worker_process_started_for_run,
            "model_loaded_for_run": model_loaded_for_run,
            "model_reused_from_prior_request": False,
            "fallback_to_inference_on_invalid_entry": False,
            "timings_seconds": {
                "identity_and_preflight": cache_preflight_seconds,
                "lookup": cache_lookup_seconds,
                "materialise": cache_materialise_seconds,
                "worker_subprocess": worker_subprocess_elapsed_seconds,
                "store": cache_store_seconds,
                "postprocess": postprocess_seconds,
                "pipeline_before_final_evidence": time.monotonic() - started_clock,
            },
            "origin_inference": (
                dict(cache_entry.document["origin"])
                if cache_entry is not None
                else None
            ),
            "run_origin_performance_matches_entry": (
                run_origin_performance_matches_entry
            ),
            "muscriptor_performance_is_current_run_inference": (
                muscriptor_performance_is_current_run_inference
            ),
            "origin_performance_semantics": origin_performance_semantics,
            "effects": {
                "raw_candidate_mutated": False,
                "midi_rebuilt_by_current_sunofriend": error is None,
                "automatic_selection": False,
                "promotion_allowed": False,
            },
            "error": error,
        }
        _atomic_json(cache_performance_path, cache_event)

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
        cache_entry_path,
        cache_performance_path,
        run_dir / "worker.response.json",
        run_dir / "muscriptor.performance.json",
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
        "worker_subprocess_elapsed_seconds": worker_subprocess_elapsed_seconds,
        "worker_request_elapsed_seconds": worker_request_elapsed_seconds,
        "backend": backend,
        "backend_manifest": asdict(AI_MODEL_MANIFESTS[backend]),
        "runtime": runtime_record or collect_ai_diagnostics(executable),
        "worker": worker_record,
        "command": (
            []
            if cache_hit or (cache_enabled and not worker_process_started_for_run)
            else command
        ),
        "worker_execution_mode": (
            "application-cache-hit"
            if cache_hit
            else (
                "application-cache-read-failed"
                if cache_enabled and not worker_process_started_for_run
                else (
                    "fresh-subprocess"
                    if worker_session is None
                    else "persistent-session-request"
                )
            )
        ),
        "worker_process_started_for_run": worker_process_started_for_run,
        "inference_executed_for_run": inference_executed_for_run,
        "model_loaded_for_run": model_loaded_for_run,
        "model_reused_from_prior_request": (
            worker_response.get("model_reused_from_prior_request")
            if worker_response is not None
            else False
        ),
        "application_cache": (
            None
            if not cache_enabled
            else {
                "schema": cache_event["schema"],
                "application_cache_status": cache_event["application_cache_status"],
                "scope": cache_event["scope"],
                "key_sha256": cache_event["key_sha256"],
                "entry_manifest_sha256": cache_event["entry_manifest_sha256"],
                "application_cache_hit": cache_event["application_cache_hit"],
                "entry_published_by_run": cache_event["entry_published_by_run"],
                "fallback_to_inference_on_invalid_entry": False,
                "muscriptor_performance_is_current_run_inference": (
                    cache_event["muscriptor_performance_is_current_run_inference"]
                ),
                "run_origin_performance_matches_entry": cache_event[
                    "run_origin_performance_matches_entry"
                ],
            }
        ),
        "worker_transport": (
            None
            if worker_session is None
            else {
                "mode": "bounded-persistent-session",
                "transport": worker_session.ready["transport"],
                "session_id": worker_session.session_id,
                "worker_instance_id": worker_session.worker_instance_id,
                "model_load_count": 1,
                "sequence": (
                    worker_response.get("sequence") if worker_response else None
                ),
                "prior_completed_requests": (
                    worker_response.get("prior_completed_requests")
                    if worker_response
                    else None
                ),
                "warm_model_request": (
                    worker_response.get("warm_model_request")
                    if worker_response
                    else None
                ),
                "model_reused_from_prior_request": (
                    worker_response.get("model_reused_from_prior_request")
                    if worker_response
                    else None
                ),
            }
        ),
        "exit_code": exit_code,
        "source": audio_record,
        "checkpoint": checkpoint_record,
        "request": request.to_dict(),
        "execution": (
            candidate.metadata.get("execution", execution) if candidate else execution
        ),
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
    "MUSCRIPTOR_EXECUTION_SCHEMA",
    "MUSCRIPTOR_INSTRUMENT_ROLES",
    "AIWorkerRunError",
    "prepare_ai_transcription_request",
    "run_ai_transcription",
]
