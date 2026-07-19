"""Standalone Python 3.12 worker for optional AI transcription backends.

This file is executed by the isolated AI interpreter rather than imported by
the Python 3.9 Sunofriend core. The worker accepts only explicit local model
files or bundles: model aliases and URLs are rejected before a backend is
imported, so an optional dependency cannot download weights silently.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any


REQUEST_SCHEMA = "sunofriend.ai-transcription-request.v1"
CANDIDATE_SCHEMA = "sunofriend.ai-transcription-candidate.v1"
MUSCRIPTOR_PERFORMANCE_SCHEMA = "sunofriend.muscriptor-performance.v1"
GAME_MODEL_FILENAMES = (
    "config.json",
    "encoder.onnx",
    "segmenter.onnx",
    "estimator.onnx",
    "dur2bd.onnx",
    "bd2dur.onnx",
)


def _normalise_peak_rss_bytes(
    ru_maxrss: int | float, platform_name: str
) -> int:
    """Normalise ``getrusage().ru_maxrss`` for supported worker platforms."""

    value = float(ru_maxrss)
    if not math.isfinite(value) or value < 0:
        raise ValueError("ru_maxrss must be finite and non-negative")
    if platform_name == "darwin":
        return int(value)
    if platform_name.startswith("linux"):
        return int(value * 1024)
    raise ValueError(f"unsupported ru_maxrss platform: {platform_name}")


def _peak_process_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return _normalise_peak_rss_bytes(usage.ru_maxrss, sys.platform)


def _load_request(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"request schema must be {REQUEST_SCHEMA}")
    if document.get("backend") not in {"muscriptor", "game", "rmvpe", "pesto"}:
        raise ValueError(
            "this worker supports only muscriptor, game, rmvpe and pesto"
        )
    audio_path = Path(str(document.get("audio_path", "")))
    if not audio_path.is_absolute() or not audio_path.is_file():
        raise ValueError("audio_path must be an absolute, existing local file")
    return document


def _local_checkpoint(options: dict[str, Any]) -> Path:
    value = options.get("model_path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("options.model_path must name an explicit local checkpoint")
    if "://" in value:
        raise ValueError("checkpoint URLs are not accepted; provide a local file")
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError(
            "MuScriptor checkpoint must be an absolute, existing local file; "
            "model aliases such as 'small' are intentionally rejected"
        )
    if path.suffix.lower() != ".safetensors":
        raise ValueError("MuScriptor checkpoint must be a .safetensors file")
    return path


def _muscriptor_config(
    checkpoint: Path, options: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    value = options.get("model_config_path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("options.model_config_path must pin adjacent config.json")
    path = Path(value).expanduser()
    expected_path = checkpoint.with_name("config.json")
    if path != expected_path or not path.is_absolute() or not path.is_file():
        raise ValueError("MuScriptor config must be the adjacent existing config.json")
    expected_hash = options.get("model_config_sha256")
    actual_hash = _sha256(path)
    if not isinstance(expected_hash, str) or expected_hash != actual_hash:
        raise ValueError("MuScriptor config changed after the run was prepared")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("model_type") != "muscriptor":
        raise ValueError("MuScriptor config must declare model_type=muscriptor")
    if document.get("variant") != options.get("model_size"):
        raise ValueError("MuScriptor config variant does not match requested model_size")
    return path, document


def _local_game_bundle(options: dict[str, Any]) -> Path:
    value = options.get("model_path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("options.model_path must name an explicit local GAME bundle")
    if "://" in value:
        raise ValueError("GAME model URLs are not accepted; provide a local directory")
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError(
            "GAME model must be an absolute, existing local ONNX directory; "
            "release aliases are intentionally rejected"
        )
    missing = [name for name in GAME_MODEL_FILENAMES if not (path / name).is_file()]
    if missing:
        raise ValueError("GAME ONNX bundle is incomplete; missing: " + ", ".join(missing))
    return path


def _local_rmvpe_model(options: dict[str, Any]) -> Path:
    value = options.get("model_path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("options.model_path must name an explicit local RMVPE model")
    if "://" in value:
        raise ValueError("RMVPE model URLs are not accepted; provide a local file")
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError(
            "RMVPE model must be an absolute, existing local ONNX file; "
            "remote model aliases are intentionally rejected"
        )
    if path.suffix.lower() != ".onnx":
        raise ValueError("RMVPE model must be an .onnx file")
    return path


def _local_pesto_model(options: dict[str, Any]) -> Path:
    value = options.get("model_path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("options.model_path must name an explicit local PESTO model")
    if "://" in value:
        raise ValueError("PESTO model URLs are not accepted; provide a local file")
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError(
            "PESTO model must be an absolute, existing local checkpoint; "
            "remote model aliases are intentionally rejected"
        )
    if path.suffix.lower() != ".ckpt":
        raise ValueError("PESTO model must be a .ckpt file")
    return path


def _device(value: Any, torch: Any) -> str:
    requested = str(value or "auto").lower()
    if requested == "auto":
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if requested == "mps":
        if not torch.backends.mps.is_available():
            raise ValueError("MPS was requested but is not available")
        return requested
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA was requested but is not available")
        return requested
    if requested != "cpu":
        raise ValueError("device must be auto, cpu, mps or cuda")
    return requested


def _prepared_audio(
    audio_path: Path,
    start_seconds: float,
    end_seconds: float | None,
    torch: Any,
) -> tuple[tuple[Any, int] | str, float, int]:
    import soundfile as sf

    info = sf.info(str(audio_path))
    if start_seconds == 0.0 and end_seconds is None:
        return str(audio_path), info.frames / info.samplerate, int(info.samplerate)

    start_frame = round(start_seconds * info.samplerate)
    end_frame = (
        info.frames
        if end_seconds is None
        else min(info.frames, round(end_seconds * info.samplerate))
    )
    if start_frame >= info.frames or end_frame <= start_frame:
        raise ValueError("requested excerpt does not overlap the source audio")
    audio, sample_rate = sf.read(
        str(audio_path),
        start=start_frame,
        stop=end_frame,
        dtype="float32",
        always_2d=True,
    )
    mono = audio.mean(axis=1).copy()
    duration_seconds = len(mono) / sample_rate
    return (torch.from_numpy(mono), int(sample_rate)), duration_seconds, int(sample_rate)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_game_bundle(path: Path) -> str:
    digest = hashlib.sha256()
    for name in GAME_MODEL_FILENAMES:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        with (path / name).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def _transcribe_muscriptor(
    document: dict[str, Any],
    *,
    performance_path: Path,
    worker_started_at: float,
) -> dict[str, Any]:
    options = document.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("request options must be an object")
    checkpoint = _local_checkpoint(options)
    checkpoint_sha256 = _sha256(checkpoint)
    expected_sha256 = options.get("model_sha256")
    if expected_sha256 and expected_sha256 != checkpoint_sha256:
        raise ValueError("MuScriptor checkpoint changed after the run was prepared")
    config_path, model_config = _muscriptor_config(checkpoint, options)

    import torch
    from muscriptor import TranscriptionModel
    from muscriptor.events import NoteEndEvent, NoteStartEvent, ProgressEvent

    device = _device(options.get("device"), torch)
    audio_path = Path(document["audio_path"])
    start_seconds = float(document.get("start_seconds", 0.0))
    raw_end = document.get("end_seconds")
    end_seconds = None if raw_end is None else float(raw_end)
    if start_seconds < 0 or (
        end_seconds is not None and end_seconds <= start_seconds
    ):
        raise ValueError("invalid excerpt start/end seconds")
    if not math.isfinite(start_seconds) or (
        end_seconds is not None and not math.isfinite(end_seconds)
    ):
        raise ValueError("excerpt start/end seconds must be finite")
    audio_preparation_started_at = time.perf_counter()
    audio, excerpt_duration, source_sample_rate = _prepared_audio(
        audio_path, start_seconds, end_seconds, torch
    )
    audio_preparation_seconds = time.perf_counter() - audio_preparation_started_at

    instruments = document.get("roles") or None
    if instruments is not None and not all(
        isinstance(instrument, str) for instrument in instruments
    ):
        raise ValueError("roles must contain exact MuScriptor instrument names")
    batch_size = int(options.get("batch_size", 1))
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    beam_size = int(options.get("beam_size", 1))
    if beam_size < 1:
        raise ValueError("beam_size must be positive")
    cfg_coef = float(options.get("cfg_coef", 1.0))
    temperature = float(options.get("temperature", 1.0))
    use_sampling = options.get("use_sampling", False)
    no_eos_is_ok = options.get("no_eos_is_ok", True)
    if not math.isfinite(cfg_coef) or cfg_coef < 0:
        raise ValueError("cfg_coef must be finite and non-negative")
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be finite and positive")
    if not isinstance(use_sampling, bool) or not isinstance(no_eos_is_ok, bool):
        raise ValueError("sampling and EOS controls must be booleans")
    if options.get("prelude_forcing") is not False:
        raise ValueError("MuScriptor 0.2.1 does not support prelude forcing")
    if options.get("prelude_forcing_supported") is not False:
        raise ValueError("MuScriptor prelude support must be recorded as false")
    if use_sampling and beam_size > 1:
        raise ValueError("sampling and beam search cannot be combined")

    execution = {
        "schema": "sunofriend.muscriptor-execution.v1",
        "model_size": model_config["variant"],
        "model_config_sha256": _sha256(config_path),
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

    model_load_started_at = time.perf_counter()
    model = TranscriptionModel.load_model(str(checkpoint), device=device)
    model_load_seconds = time.perf_counter() - model_load_started_at
    starts: dict[int, NoteStartEvent] = {}
    notes: list[dict[str, Any]] = []
    warnings: list[str] = []
    progress: list[dict[str, int]] = []
    events_after_excerpt = 0
    note_start_observed_at: dict[int, float] = {}
    first_note_start_seconds: float | None = None
    first_completed_note_seconds: float | None = None
    first_completed_chunk_seconds: float | None = None
    valid_note_start_observations: list[float] = []
    reported_chunks = 0
    # MuScriptor returns a lazy iterator.  Iterating it performs the backend's
    # audio preprocessing, condition construction and decoding, so this is an
    # inclusive transcription timer rather than a model-forward-only timer.
    transcription_started_at = time.perf_counter()
    events = model.transcribe(
        audio,
        use_sampling=use_sampling,
        temperature=temperature,
        cfg_coef=cfg_coef,
        instruments=list(instruments) if instruments else None,
        batch_size=batch_size,
        no_eos_is_ok=no_eos_is_ok,
        beam_size=beam_size,
    )
    for event in events:
        if isinstance(event, NoteStartEvent):
            starts[event.index] = event
            note_start_observed_at[event.index] = (
                time.perf_counter() - worker_started_at
            )
        elif isinstance(event, NoteEndEvent):
            start = starts.pop(event.start_event_index, event.start_event)
            local_start = float(start.start_time)
            local_end = min(float(event.end_time), excerpt_duration)
            if local_start >= excerpt_duration:
                events_after_excerpt += 1
                continue
            note_start = start_seconds + local_start
            note_end = start_seconds + local_end
            if note_end <= note_start:
                warnings.append(f"discarded non-positive event {start.index}")
                continue
            notes.append(
                {
                    "start_seconds": note_start,
                    "end_seconds": note_end,
                    "pitch": float(start.pitch),
                    "confidence": None,
                    "instrument": start.instrument,
                    "velocity": None,
                    "source_event_id": str(start.index),
                }
            )
            observed_start = note_start_observed_at.get(start.index)
            if observed_start is not None:
                valid_note_start_observations.append(observed_start)
            if first_completed_note_seconds is None:
                first_completed_note_seconds = (
                    time.perf_counter() - worker_started_at
                )
        elif isinstance(event, ProgressEvent):
            progress.append({"completed": event.completed, "total": event.total})
            reported_chunks = max(reported_chunks, int(event.completed))
            if first_completed_chunk_seconds is None and event.completed > 0:
                first_completed_chunk_seconds = time.perf_counter() - worker_started_at

    transcription_seconds = time.perf_counter() - transcription_started_at

    if notes:
        first_note_start_seconds = min(valid_note_start_observations, default=None)
    else:
        first_note_start_seconds = None
        first_completed_note_seconds = None

    if starts:
        warnings.append(f"discarded {len(starts)} unterminated note start event(s)")
    if events_after_excerpt:
        warnings.append(
            f"discarded {events_after_excerpt} event(s) in padded audio after excerpt end"
        )
    notes.sort(
        key=lambda note: (
            note["start_seconds"],
            note["pitch"],
            note["end_seconds"],
        )
    )
    version = importlib.metadata.version("muscriptor")
    candidate = {
        "schema": CANDIDATE_SCHEMA,
        "backend": "muscriptor",
        "model_version": f"muscriptor-{version}/{checkpoint_sha256[:12]}",
        "notes": notes,
        "warnings": warnings,
        "raw_artifacts": [performance_path.name],
        "metadata": {
            "device": device,
            "checkpoint_sha256": checkpoint_sha256,
            "excerpt": {
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "duration_seconds": excerpt_duration,
            },
            "source_sample_rate": source_sample_rate,
            "instruments": list(instruments) if instruments else [],
            "progress": progress,
            "execution": execution,
            "velocity_policy": "not supplied by MuScriptor; preserved as null",
        },
    }
    performance = {
        "schema": MUSCRIPTOR_PERFORMANCE_SCHEMA,
        "measurement_mode": "fresh-process",
        "device": device,
        "timings_seconds": {
            "audio_preparation": audio_preparation_seconds,
            "model_load": model_load_seconds,
            "transcription": transcription_seconds,
            "worker_total": time.perf_counter() - worker_started_at,
            "time_to_first_note_start": first_note_start_seconds,
            "time_to_first_completed_note": first_completed_note_seconds,
            "time_to_first_completed_chunk": first_completed_chunk_seconds,
        },
        "chunks": {
            "seconds": 5.0,
            "planned": math.ceil(excerpt_duration / 5.0),
            "reported": reported_chunks,
        },
        "note_count": len(notes),
        "peak_process_rss_bytes": _peak_process_rss_bytes(),
        "memory_scope": "process RSS high-water; accelerator allocation excluded",
        "clock": "time.perf_counter",
    }
    _atomic_json(performance_path, performance)
    return candidate


def _game_excerpt(
    audio_path: Path,
    start_seconds: float,
    end_seconds: float | None,
    target_sample_rate: int,
) -> tuple[Any, float, int]:
    import numpy as np
    import soundfile as sf
    import soxr

    info = sf.info(str(audio_path))
    start_frame = round(start_seconds * info.samplerate)
    end_frame = (
        info.frames
        if end_seconds is None
        else min(info.frames, round(end_seconds * info.samplerate))
    )
    if start_frame >= info.frames or end_frame <= start_frame:
        raise ValueError("requested excerpt does not overlap the source audio")
    audio, sample_rate = sf.read(
        str(audio_path),
        start=start_frame,
        stop=end_frame,
        dtype="float32",
        always_2d=True,
    )
    mono = np.nan_to_num(audio.mean(axis=1), copy=False).astype(np.float32, copy=False)
    source_duration = len(mono) / float(sample_rate)
    if sample_rate != target_sample_rate:
        mono = soxr.resample(mono, sample_rate, target_sample_rate, quality="HQ")
    return np.asarray(mono, dtype=np.float32)[None, :], source_duration, int(sample_rate)


def _game_float_option(
    options: dict[str, Any], name: str, default: float, minimum: float, maximum: float
) -> float:
    value = float(options.get(name, default))
    if not math.isfinite(value) or not minimum <= value < maximum:
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum})")
    return value


def _game_notes(
    durations: Any,
    mask: Any,
    presence: Any,
    scores: Any,
    *,
    start_seconds: float,
    excerpt_duration: float,
) -> tuple[list[dict[str, Any]], int]:
    notes: list[dict[str, Any]] = []
    elapsed = 0.0
    regions = 0
    last_time = start_seconds
    for duration, valid, voiced, score in zip(
        durations.tolist(), mask.tolist(), presence.tolist(), scores.tolist()
    ):
        if not valid:
            continue
        local_start = min(excerpt_duration, elapsed)
        elapsed += max(0.0, float(duration))
        local_end = min(excerpt_duration, elapsed)
        regions += 1
        if not voiced or local_end <= local_start:
            continue
        pitch = float(score)
        if not math.isfinite(pitch) or not 0 <= pitch <= 127:
            continue
        note_start = max(start_seconds + local_start, last_time)
        note_end = max(note_start, start_seconds + local_end)
        if note_end <= note_start:
            continue
        notes.append(
            {
                "start_seconds": note_start,
                "end_seconds": note_end,
                "pitch": pitch,
                "confidence": None,
                "instrument": "voice",
                "velocity": None,
                "source_event_id": f"game-{regions - 1}",
            }
        )
        last_time = note_end
    return notes, regions


def _transcribe_game(document: dict[str, Any]) -> dict[str, Any]:
    options = document.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("request options must be an object")
    bundle = _local_game_bundle(options)
    bundle_sha256 = _sha256_game_bundle(bundle)
    expected_sha256 = options.get("model_sha256")
    if expected_sha256 and expected_sha256 != bundle_sha256:
        raise ValueError("GAME model bundle changed after the run was prepared")

    requested_device = str(options.get("device", "auto")).lower()
    if requested_device not in {"auto", "cpu"}:
        raise ValueError("GAME ONNX currently supports device auto or cpu")

    import numpy as np
    import onnxruntime as ort

    seed = int(options.get("seed", 0))
    if not 0 <= seed <= 2_147_483_647:
        raise ValueError("seed must be between 0 and 2147483647")
    ort.set_seed(seed)

    config = json.loads((bundle / "config.json").read_text(encoding="utf-8"))
    sample_rate = int(config["samplerate"])
    timestep = float(config["timestep"])
    languages = config.get("languages") or {}
    language = options.get("language")
    if language in (None, "", "auto"):
        language_id = 0
        language = None
    elif language not in languages:
        raise ValueError(
            f"GAME language {language!r} is unsupported; choose: "
            + ", ".join(sorted(languages))
        )
    else:
        language_id = int(languages[language])

    start_seconds = float(document.get("start_seconds", 0.0))
    raw_end = document.get("end_seconds")
    end_seconds = None if raw_end is None else float(raw_end)
    if start_seconds < 0 or (
        end_seconds is not None and end_seconds <= start_seconds
    ):
        raise ValueError("invalid excerpt start/end seconds")
    if not math.isfinite(start_seconds) or (
        end_seconds is not None and not math.isfinite(end_seconds)
    ):
        raise ValueError("excerpt start/end seconds must be finite")
    waveform, excerpt_duration, source_sample_rate = _game_excerpt(
        Path(document["audio_path"]), start_seconds, end_seconds, sample_rate
    )

    seg_threshold = _game_float_option(
        options, "boundary_threshold", 0.2, 0.0, 1.0
    )
    presence_threshold = _game_float_option(
        options, "presence_threshold", 0.2, 0.0, 1.0
    )
    radius_ms = float(options.get("boundary_radius_ms", 20.0))
    if not math.isfinite(radius_ms) or radius_ms <= 0:
        raise ValueError("boundary_radius_ms must be finite and positive")
    radius_frames = max(1, round((radius_ms / 1000.0) / timestep))
    steps = int(options.get("game_steps", 8))
    if steps < 1:
        raise ValueError("game_steps must be positive")
    t0 = _game_float_option(options, "game_t0", 0.0, 0.0, 1.0)
    schedule = [t0 + index * ((1.0 - t0) / steps) for index in range(steps)]

    providers = ["CPUExecutionProvider"]
    encoder = ort.InferenceSession(str(bundle / "encoder.onnx"), providers=providers)
    segmenter = ort.InferenceSession(
        str(bundle / "segmenter.onnx"), providers=providers
    )
    boundary_decoder = ort.InferenceSession(
        str(bundle / "bd2dur.onnx"), providers=providers
    )
    estimator = ort.InferenceSession(
        str(bundle / "estimator.onnx"), providers=providers
    )

    duration_input = np.asarray([excerpt_duration], dtype=np.float32)
    x_seg, x_est, mask_t = encoder.run(
        ["x_seg", "x_est", "maskT"],
        {"waveform": waveform, "duration": duration_input},
    )
    known_boundaries = np.zeros_like(mask_t, dtype=np.bool_)
    boundaries = known_boundaries
    language_input = np.asarray([language_id], dtype=np.int64)
    for t_value in schedule:
        boundaries = segmenter.run(
            ["boundaries"],
            {
                "x_seg": x_seg,
                "language": language_input,
                "known_boundaries": known_boundaries,
                "prev_boundaries": boundaries,
                "t": np.asarray([t_value], dtype=np.float32),
                "maskT": mask_t,
                "threshold": np.asarray(seg_threshold, dtype=np.float32),
                "radius": np.asarray(radius_frames, dtype=np.int64),
            },
        )[0]
    durations, mask_n = boundary_decoder.run(
        ["durations", "maskN"], {"boundaries": boundaries, "maskT": mask_t}
    )
    presence, scores = estimator.run(
        ["presence", "scores"],
        {
            "x_est": x_est,
            "boundaries": boundaries,
            "maskT": mask_t,
            "maskN": mask_n,
            "threshold": np.asarray(presence_threshold, dtype=np.float32),
        },
    )
    notes, region_count = _game_notes(
        durations[0],
        mask_n[0],
        presence[0],
        scores[0],
        start_seconds=start_seconds,
        excerpt_duration=excerpt_duration,
    )
    warnings: list[str] = []
    if not notes:
        warnings.append("GAME returned no voiced notes for this excerpt")
    return {
        "schema": CANDIDATE_SCHEMA,
        "backend": "game",
        "model_version": f"game-1.0.3-small-onnx/{bundle_sha256[:12]}",
        "notes": notes,
        "warnings": warnings,
        "raw_artifacts": [],
        "metadata": {
            "device": "cpu",
            "execution_provider": "CPUExecutionProvider",
            "onnxruntime_version": importlib.metadata.version("onnxruntime"),
            "seed": seed,
            "checkpoint_sha256": bundle_sha256,
            "excerpt": {
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "duration_seconds": excerpt_duration,
            },
            "source_sample_rate": source_sample_rate,
            "model_sample_rate": sample_rate,
            "model_timestep_seconds": timestep,
            "language": language,
            "language_id": language_id,
            "boundary_threshold": seg_threshold,
            "boundary_radius_ms": radius_ms,
            "boundary_radius_frames": radius_frames,
            "presence_threshold": presence_threshold,
            "d3pm_schedule": schedule,
            "region_count": region_count,
            "voiced_note_count": len(notes),
            "pitch_policy": "floating GAME MIDI pitch preserved; candidate MIDI rounds",
            "velocity_policy": "not supplied by GAME; preserved as null",
        },
    }


def _rmvpe_excerpt(
    audio_path: Path, start_seconds: float, end_seconds: float | None
) -> tuple[Any, float, int]:
    import numpy as np
    import soundfile as sf

    info = sf.info(str(audio_path))
    start_frame = round(start_seconds * info.samplerate)
    end_frame = (
        info.frames
        if end_seconds is None
        else min(info.frames, round(end_seconds * info.samplerate))
    )
    if start_frame >= info.frames or end_frame <= start_frame:
        raise ValueError("requested excerpt does not overlap the source audio")
    audio, sample_rate = sf.read(
        str(audio_path),
        start=start_frame,
        stop=end_frame,
        dtype="float32",
        always_2d=True,
    )
    mono = np.nan_to_num(audio.mean(axis=1), copy=False).astype(np.float32, copy=False)
    return mono, len(mono) / float(sample_rate), int(sample_rate)


def _rmvpe_option(
    options: dict[str, Any], name: str, default: float, minimum: float, maximum: float
) -> float:
    value = float(options.get(name, default))
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum}]")
    return value


def _label_runs(labels: Any) -> list[tuple[int, int, int]]:
    runs: list[tuple[int, int, int]] = []
    if len(labels) == 0:
        return runs
    start = 0
    label = int(labels[0])
    for index in range(1, len(labels)):
        next_label = int(labels[index])
        if next_label != label:
            runs.append((start, index, label))
            start = index
            label = next_label
    runs.append((start, len(labels), label))
    return runs


def _rmvpe_frames_to_notes(
    times: Any,
    frequency: Any,
    confidence: Any,
    *,
    start_seconds: float,
    excerpt_duration: float,
    instrument: str,
    confidence_threshold: float,
    minimum_note_ms: float,
    maximum_gap_ms: float,
    pitch_change_semitones: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Decode immutable F0 frames conservatively into a monophonic note draft."""

    import numpy as np

    times = np.asarray(times, dtype=np.float64).reshape(-1)
    frequency = np.asarray(frequency, dtype=np.float64).reshape(-1)
    confidence = np.asarray(confidence, dtype=np.float64).reshape(-1)
    if not (len(times) == len(frequency) == len(confidence)):
        raise ValueError("RMVPE time, frequency and confidence lengths differ")
    if len(times) == 0:
        return [], {
            "frame_count": 0,
            "raw_voiced_frames": 0,
            "bridged_frames": 0,
            "discarded_short_runs": 0,
            "hop_seconds": 0.01,
        }

    positive_steps = np.diff(times)
    positive_steps = positive_steps[positive_steps > 0]
    hop_seconds = float(np.median(positive_steps)) if len(positive_steps) else 0.01
    raw_midi = np.full(len(times), np.nan, dtype=np.float64)
    valid_frequency = np.isfinite(frequency) & (frequency >= 30.0) & (frequency <= 2000.0)
    raw_midi[valid_frequency] = 69.0 + 12.0 * np.log2(
        frequency[valid_frequency] / 440.0
    )
    voiced = (
        valid_frequency
        & np.isfinite(confidence)
        & (confidence >= confidence_threshold)
        & (raw_midi >= 0.0)
        & (raw_midi <= 127.0)
    )
    raw_voiced_frames = int(voiced.sum())

    smoothed = raw_midi.copy()
    radius = 2
    for index in np.flatnonzero(voiced):
        left = max(0, index - radius)
        right = min(len(times), index + radius + 1)
        neighbours = raw_midi[left:right][voiced[left:right]]
        if len(neighbours):
            smoothed[index] = float(np.median(neighbours))

    maximum_gap_frames = max(0, round((maximum_gap_ms / 1000.0) / hop_seconds))
    bridged_frames = 0
    index = 0
    while index < len(voiced):
        if voiced[index]:
            index += 1
            continue
        gap_start = index
        while index < len(voiced) and not voiced[index]:
            index += 1
        gap_end = index
        if (
            gap_start > 0
            and gap_end < len(voiced)
            and gap_end - gap_start <= maximum_gap_frames
            and abs(smoothed[gap_start - 1] - smoothed[gap_end])
            <= max(1.0, pitch_change_semitones)
        ):
            span = gap_end - gap_start + 1
            for offset, frame in enumerate(range(gap_start, gap_end), start=1):
                fraction = offset / span
                smoothed[frame] = (
                    smoothed[gap_start - 1] * (1.0 - fraction)
                    + smoothed[gap_end] * fraction
                )
                raw_midi[frame] = smoothed[frame]
                voiced[frame] = True
                bridged_frames += 1

    labels = np.full(len(times), -1, dtype=np.int16)
    previous_label: int | None = None
    previous_voiced = False
    for index in range(len(times)):
        if not voiced[index]:
            previous_label = None
            previous_voiced = False
            continue
        proposed = int(np.clip(np.rint(smoothed[index]), 0, 127))
        if (
            previous_voiced
            and previous_label is not None
            and abs(smoothed[index] - previous_label) < pitch_change_semitones
        ):
            labels[index] = previous_label
        else:
            labels[index] = proposed
            previous_label = proposed
        previous_voiced = True

    minimum_ratio = (minimum_note_ms / 1000.0) / hop_seconds
    minimum_frames = max(1, math.ceil(minimum_ratio - 1e-9))
    discarded_short_runs = 0
    for _iteration in range(8):
        runs = _label_runs(labels)
        changed = False
        for run_index, (run_start, run_end, label) in enumerate(runs):
            if label < 0 or run_end - run_start >= minimum_frames:
                continue
            neighbours: list[int] = []
            if run_index > 0 and runs[run_index - 1][2] >= 0:
                neighbours.append(runs[run_index - 1][2])
            if run_index + 1 < len(runs) and runs[run_index + 1][2] >= 0:
                neighbours.append(runs[run_index + 1][2])
            target = min(neighbours, key=lambda value: abs(value - label)) if neighbours else -1
            if target >= 0 and abs(target - label) <= 2:
                labels[run_start:run_end] = target
            else:
                labels[run_start:run_end] = -1
                discarded_short_runs += 1
            changed = True
        if not changed:
            break

    notes: list[dict[str, Any]] = []
    for run_start, run_end, label in _label_runs(labels):
        if label < 0 or run_end - run_start < minimum_frames:
            continue
        note_start = start_seconds + max(0.0, float(times[run_start]))
        local_end = min(excerpt_duration, float(times[run_end - 1]) + hop_seconds)
        note_end = start_seconds + max(float(times[run_start]), local_end)
        if note_end <= note_start:
            continue
        pitches = raw_midi[run_start:run_end]
        pitches = pitches[np.isfinite(pitches)]
        confidences = confidence[run_start:run_end]
        confidences = confidences[np.isfinite(confidences)]
        pitch = float(np.median(pitches)) if len(pitches) else float(label)
        note_confidence = (
            float(np.clip(np.median(confidences), 0.0, 1.0))
            if len(confidences)
            else None
        )
        notes.append(
            {
                "start_seconds": note_start,
                "end_seconds": note_end,
                "pitch": float(np.clip(pitch, 0.0, 127.0)),
                "confidence": note_confidence,
                "instrument": instrument,
                "velocity": None,
                "source_event_id": f"rmvpe-{len(notes)}",
            }
        )
    return notes, {
        "frame_count": len(times),
        "raw_voiced_frames": raw_voiced_frames,
        "bridged_frames": bridged_frames,
        "discarded_short_runs": discarded_short_runs,
        "hop_seconds": hop_seconds,
        "minimum_note_frames": minimum_frames,
    }


def _transcribe_rmvpe(
    document: dict[str, Any], *, frames_path: Path
) -> dict[str, Any]:
    options = document.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("request options must be an object")
    checkpoint = _local_rmvpe_model(options)
    checkpoint_sha256 = _sha256(checkpoint)
    expected_sha256 = options.get("model_sha256")
    if expected_sha256 and expected_sha256 != checkpoint_sha256:
        raise ValueError("RMVPE checkpoint changed after the run was prepared")

    requested_device = str(options.get("device", "auto")).lower()
    if requested_device not in {"auto", "cpu"}:
        raise ValueError("RMVPE ONNX currently supports device auto or cpu")

    import numpy as np
    from rmvpe_onnx import RMVPE

    start_seconds = float(document.get("start_seconds", 0.0))
    raw_end = document.get("end_seconds")
    end_seconds = None if raw_end is None else float(raw_end)
    if start_seconds < 0 or (
        end_seconds is not None and end_seconds <= start_seconds
    ):
        raise ValueError("invalid excerpt start/end seconds")
    if not math.isfinite(start_seconds) or (
        end_seconds is not None and not math.isfinite(end_seconds)
    ):
        raise ValueError("excerpt start/end seconds must be finite")
    audio, excerpt_duration, source_sample_rate = _rmvpe_excerpt(
        Path(document["audio_path"]), start_seconds, end_seconds
    )

    confidence_threshold = _rmvpe_option(
        options, "confidence_threshold", 0.03, 0.0, 1.0
    )
    minimum_note_ms = _rmvpe_option(
        options, "minimum_note_ms", 80.0, 10.0, 1000.0
    )
    maximum_gap_ms = _rmvpe_option(
        options, "maximum_gap_ms", 50.0, 0.0, 500.0
    )
    pitch_change_semitones = _rmvpe_option(
        options, "pitch_change_semitones", 0.75, 0.25, 6.0
    )
    roles = document.get("roles") or []
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise ValueError("roles must be a list of strings")
    instrument = roles[0] if len(roles) == 1 else "voice"

    model = RMVPE(model_path=str(checkpoint), device="cpu")
    times, frequency, confidence, activation = model.predict(
        np.asarray(audio, dtype=np.float32), source_sample_rate
    )
    notes, decoder = _rmvpe_frames_to_notes(
        times,
        frequency,
        confidence,
        start_seconds=start_seconds,
        excerpt_duration=excerpt_duration,
        instrument=instrument,
        confidence_threshold=confidence_threshold,
        minimum_note_ms=minimum_note_ms,
        maximum_gap_ms=maximum_gap_ms,
        pitch_change_semitones=pitch_change_semitones,
    )

    version = importlib.metadata.version("rmvpe-onnx")
    model_version = f"rmvpe-onnx-{version}/{checkpoint_sha256[:12]}"
    frames_document = {
        "schema": "sunofriend.rmvpe-f0-frames.v1",
        "backend": "rmvpe",
        "model_version": model_version,
        "checkpoint_sha256": checkpoint_sha256,
        "excerpt": {
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "duration_seconds": excerpt_duration,
        },
        "fields": ["time_seconds", "frequency_hz", "confidence"],
        "frames": [
            [
                start_seconds + float(frame_time),
                float(frame_frequency),
                float(frame_confidence),
            ]
            for frame_time, frame_frequency, frame_confidence in zip(
                times.tolist(), frequency.tolist(), confidence.tolist()
            )
        ],
        "activation_shape": list(activation.shape),
        "note_decoder": {
            "policy": "sunofriend-rmvpe-frame-to-note-v1",
            "confidence_threshold": confidence_threshold,
            "minimum_note_ms": minimum_note_ms,
            "maximum_gap_ms": maximum_gap_ms,
            "pitch_change_semitones": pitch_change_semitones,
            **decoder,
        },
    }
    _atomic_json(frames_path, frames_document)
    warnings: list[str] = []
    if not notes:
        warnings.append("RMVPE frame-to-note decoder returned no voiced notes")
    return {
        "schema": CANDIDATE_SCHEMA,
        "backend": "rmvpe",
        "model_version": model_version,
        "notes": notes,
        "warnings": warnings,
        "raw_artifacts": [frames_path.name],
        "metadata": {
            "device": "cpu",
            "execution_provider": "CPUExecutionProvider",
            "onnxruntime_version": importlib.metadata.version("onnxruntime"),
            "rmvpe_onnx_version": version,
            "checkpoint_sha256": checkpoint_sha256,
            "excerpt": frames_document["excerpt"],
            "source_sample_rate": source_sample_rate,
            "model_sample_rate": 16000,
            "instrument": instrument,
            "frame_evidence": frames_path.name,
            "activation_shape": list(activation.shape),
            "note_decoder": frames_document["note_decoder"],
            "pitch_policy": "floating median F0 MIDI pitch preserved; candidate MIDI rounds",
            "velocity_policy": "not supplied by RMVPE; preserved as null",
        },
    }


def _transcribe_pesto(
    document: dict[str, Any], *, frames_path: Path, activations_path: Path
) -> dict[str, Any]:
    """Run PESTO and retain both its F0 frames and raw activation matrix."""

    options = document.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("request options must be an object")
    checkpoint = _local_pesto_model(options)
    checkpoint_sha256 = _sha256(checkpoint)
    expected_sha256 = options.get("model_sha256")
    if expected_sha256 and expected_sha256 != checkpoint_sha256:
        raise ValueError("PESTO checkpoint changed after the run was prepared")

    import numpy as np
    import pesto
    import torch

    device = _device(options.get("device"), torch)
    start_seconds = float(document.get("start_seconds", 0.0))
    raw_end = document.get("end_seconds")
    end_seconds = None if raw_end is None else float(raw_end)
    if start_seconds < 0 or (
        end_seconds is not None and end_seconds <= start_seconds
    ):
        raise ValueError("invalid excerpt start/end seconds")
    if not math.isfinite(start_seconds) or (
        end_seconds is not None and not math.isfinite(end_seconds)
    ):
        raise ValueError("excerpt start/end seconds must be finite")
    audio, excerpt_duration, source_sample_rate = _rmvpe_excerpt(
        Path(document["audio_path"]), start_seconds, end_seconds
    )

    confidence_threshold = _rmvpe_option(
        options, "confidence_threshold", 0.2, 0.0, 1.0
    )
    minimum_note_ms = _rmvpe_option(
        options, "minimum_note_ms", 80.0, 10.0, 1000.0
    )
    maximum_gap_ms = _rmvpe_option(
        options, "maximum_gap_ms", 50.0, 0.0, 500.0
    )
    pitch_change_semitones = _rmvpe_option(
        options, "pitch_change_semitones", 0.75, 0.25, 6.0
    )
    step_size_ms = _rmvpe_option(options, "step_size_ms", 10.0, 2.0, 100.0)
    reduction = str(options.get("reduction", "alwa"))
    if reduction not in {"alwa", "argmax", "mean"}:
        raise ValueError("PESTO reduction must be alwa, argmax or mean")
    num_chunks = int(options.get("num_chunks", 1))
    if num_chunks < 1:
        raise ValueError("PESTO num_chunks must be positive")
    roles = document.get("roles") or []
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise ValueError("roles must be a list of strings")
    instrument = roles[0] if len(roles) == 1 else "voice"

    waveform = torch.from_numpy(np.asarray(audio, dtype=np.float32)).to(device)
    time_ms, frequency, confidence, activations = pesto.predict(
        waveform,
        source_sample_rate,
        step_size=step_size_ms,
        model_name=str(checkpoint),
        reduction=reduction,
        num_chunks=num_chunks,
        convert_to_freq=True,
    )
    time_seconds = time_ms.detach().cpu().numpy().astype(np.float64) / 1000.0
    frequency_np = frequency.detach().cpu().numpy().astype(np.float64)
    confidence_np = confidence.detach().cpu().numpy().astype(np.float64)
    activations_np = activations.detach().cpu().numpy().astype(np.float32)
    np.save(activations_path, activations_np, allow_pickle=False)

    notes, decoder = _rmvpe_frames_to_notes(
        time_seconds,
        frequency_np,
        confidence_np,
        start_seconds=start_seconds,
        excerpt_duration=excerpt_duration,
        instrument=instrument,
        confidence_threshold=confidence_threshold,
        minimum_note_ms=minimum_note_ms,
        maximum_gap_ms=maximum_gap_ms,
        pitch_change_semitones=pitch_change_semitones,
    )

    version = importlib.metadata.version("pesto-pitch")
    model_version = f"pesto-pitch-{version}-mir-1k_g7/{checkpoint_sha256[:12]}"
    frames_document = {
        "schema": "sunofriend.pesto-f0-frames.v1",
        "backend": "pesto",
        "model_version": model_version,
        "checkpoint_sha256": checkpoint_sha256,
        "excerpt": {
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "duration_seconds": excerpt_duration,
        },
        "fields": ["time_seconds", "frequency_hz", "confidence"],
        "frames": [
            [
                start_seconds + float(frame_time),
                float(frame_frequency),
                float(frame_confidence),
            ]
            for frame_time, frame_frequency, frame_confidence in zip(
                time_seconds.tolist(),
                frequency_np.tolist(),
                confidence_np.tolist(),
            )
        ],
        "activations": {
            "path": activations_path.name,
            "shape": list(activations_np.shape),
            "dtype": str(activations_np.dtype),
        },
        "note_decoder": {
            "policy": "sunofriend-pesto-frame-to-note-v1",
            "confidence_threshold": confidence_threshold,
            "minimum_note_ms": minimum_note_ms,
            "maximum_gap_ms": maximum_gap_ms,
            "pitch_change_semitones": pitch_change_semitones,
            **decoder,
        },
    }
    _atomic_json(frames_path, frames_document)
    warnings: list[str] = []
    if not notes:
        warnings.append("PESTO frame-to-note decoder returned no voiced notes")
    return {
        "schema": CANDIDATE_SCHEMA,
        "backend": "pesto",
        "model_version": model_version,
        "notes": notes,
        "warnings": warnings,
        "raw_artifacts": [frames_path.name, activations_path.name],
        "metadata": {
            "device": device,
            "torch_version": torch.__version__,
            "torchaudio_version": importlib.metadata.version("torchaudio"),
            "pesto_version": version,
            "checkpoint_sha256": checkpoint_sha256,
            "excerpt": frames_document["excerpt"],
            "source_sample_rate": source_sample_rate,
            "instrument": instrument,
            "step_size_ms": step_size_ms,
            "reduction": reduction,
            "num_chunks": num_chunks,
            "frame_evidence": frames_path.name,
            "activations_evidence": activations_path.name,
            "activation_shape": list(activations_np.shape),
            "note_decoder": frames_document["note_decoder"],
            "pitch_policy": (
                "floating PESTO F0 MIDI pitch preserved; candidate MIDI rounds"
            ),
            "velocity_policy": "not supplied by PESTO; preserved as null",
        },
    }


def _transcribe(
    document: dict[str, Any], *, output_path: Path, worker_started_at: float
) -> dict[str, Any]:
    if document["backend"] == "muscriptor":
        return _transcribe_muscriptor(
            document,
            performance_path=output_path.with_name("muscriptor.performance.json"),
            worker_started_at=worker_started_at,
        )
    if document["backend"] == "game":
        return _transcribe_game(document)
    if document["backend"] == "rmvpe":
        return _transcribe_rmvpe(
            document, frames_path=output_path.with_name("rmvpe.frames.json")
        )
    if document["backend"] == "pesto":
        return _transcribe_pesto(
            document,
            frames_path=output_path.with_name("pesto.frames.json"),
            activations_path=output_path.with_name("pesto.activations.npy"),
        )
    raise ValueError(f"unsupported backend: {document['backend']}")


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    worker_started_at = time.perf_counter()
    parser = argparse.ArgumentParser(prog="sunofriend-ai-worker")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        request = _load_request(args.request)
        candidate = _transcribe(
            request,
            output_path=args.output,
            worker_started_at=worker_started_at,
        )
        _atomic_json(args.output, candidate)
    except Exception as exc:
        print(f"sunofriend-ai-worker: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(candidate['notes'])} raw note candidate(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
