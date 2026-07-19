"""Private content-addressed cache for exact MuScriptor raw worker results.

The cache is deliberately narrower than an immutable AI run.  It stores only
the verified worker candidate and its original inference-performance artifact.
Every cache hit creates a fresh run and repeats Sunofriend's current quality,
expression and MIDI derivation.  A hit therefore never represents a new model
inference or a reused resident model.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import soundfile

from .ai_runtime import (
    AI_CANDIDATE_SCHEMA,
    AI_REQUEST_SCHEMA,
    AITranscriptionCandidate,
    AITranscriptionRequest,
)


AI_CACHE_KEY_SCHEMA = "sunofriend.ai-transcription-cache-key.v1"
AI_CACHE_ENTRY_SCHEMA = "sunofriend.ai-transcription-cache-entry.v1"
AI_CACHE_EVENT_SCHEMA = "sunofriend.ai-transcription-cache-event.v1"
AI_CACHE_BENCHMARK_SCHEMA = "sunofriend.ai-cache-benchmark.v1"
AI_CACHE_NAMESPACE = "muscriptor-raw-v1"
MUSCRIPTOR_PERFORMANCE_SCHEMA = "sunofriend.muscriptor-performance.v1"

_CACHE_SCOPE = "exact-muscriptor-raw-worker-result-v1"
_PATH_OPTIONS = frozenset({"model_path", "model_config_path"})
_CACHE_OPTION_KEYS = frozenset(
    {
        "batch_size",
        "beam_size",
        "cfg_coef",
        "chunk_seconds",
        "device",
        "model_config_sha256",
        "model_sha256",
        "model_size",
        "no_eos_is_ok",
        "prelude_forcing",
        "prelude_forcing_supported",
        "temperature",
        "use_sampling",
    }
)
_RAW_ARTIFACTS = ("muscriptor.performance.json",)
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class AICacheEntry:
    """One fully verified immutable entry in the private cache."""

    cache_root: Path
    entry_dir: Path
    document: Mapping[str, Any]
    manifest_sha256: str
    manifest_bytes: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    data = (
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _copy_verified(
    source: Path, destination: Path, expected: Mapping[str, Any]
) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(
            f"AI cache source artifact is not a regular file: {source.name}"
        )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            f"AI cache materialisation path already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("xb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
        output_handle.flush()
        os.fsync(output_handle.fileno())
    expected_bytes = expected.get("bytes")
    expected_sha256 = expected.get("sha256")
    if (
        destination.stat().st_size != expected_bytes
        or _sha256(destination) != expected_sha256
    ):
        raise ValueError(f"AI cache artifact changed while copying: {source.name}")


def _file_record(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(relative_to)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AI cache runtime has no {label}")
    return value.strip()


def _runtime_identity(
    runtime: Mapping[str, Any], request: AITranscriptionRequest
) -> dict[str, Any]:
    if runtime.get("schema") != "sunofriend.ai-runtime.v1":
        raise ValueError("AI cache requires a complete path-free runtime identity")
    if runtime.get("runtime_ready") is not True:
        raise ValueError("AI cache requires a supported Python runtime")
    if runtime.get("torch_ready") is not True:
        raise ValueError("AI cache requires an importable PyTorch runtime")
    packages = runtime.get("packages")
    torch = runtime.get("torch")
    backends = runtime.get("backends")
    muscriptor = backends.get("muscriptor") if isinstance(backends, Mapping) else None
    if not isinstance(packages, Mapping) or not isinstance(torch, Mapping):
        raise ValueError("AI cache runtime package evidence is incomplete")
    if not isinstance(muscriptor, Mapping):
        raise ValueError("AI cache MuScriptor runtime evidence is incomplete")
    if muscriptor.get("software_ready") is not True:
        raise ValueError("AI cache requires an importable MuScriptor runtime")

    requested_device = str(request.options.get("device", "auto"))
    if requested_device not in {"auto", "cpu", "mps"}:
        raise ValueError("AI cache device must be auto, cpu or mps")
    effective_device = (
        str(runtime.get("preferred_device"))
        if requested_device == "auto"
        else requested_device
    )
    if effective_device not in {"cpu", "mps"}:
        raise ValueError("AI cache could not determine the effective device")
    if effective_device == "mps" and not bool(torch.get("mps_available")):
        raise ValueError("AI cache cannot identify MPS as available")

    return {
        "platform_architecture": _nonempty_string(runtime.get("platform"), "platform"),
        "python_version": _nonempty_string(runtime.get("python"), "Python version"),
        "torch_version": _nonempty_string(torch.get("version"), "PyTorch version"),
        "muscriptor_version": _nonempty_string(
            muscriptor.get("version"), "MuScriptor version"
        ),
        "einops_version": _nonempty_string(packages.get("einops"), "einops version"),
        "numpy_version": _nonempty_string(packages.get("numpy"), "NumPy version"),
        "soundfile_version": _nonempty_string(
            packages.get("soundfile"), "SoundFile version"
        ),
        "safetensors_version": _nonempty_string(
            packages.get("safetensors"), "safetensors version"
        ),
        "requested_device": requested_device,
        "effective_device": effective_device,
        "mps_built": bool(torch.get("mps_built")),
        "mps_available": bool(torch.get("mps_available")),
    }


def build_muscriptor_cache_identity(
    *,
    request: AITranscriptionRequest,
    bpm: float,
    source: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    worker: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one canonical, path-free identity for an exact cached request."""

    if request.backend != "muscriptor":
        raise ValueError("AI application cache v1 supports MuScriptor only")
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("AI cache BPM must be finite and positive")
    if request.options.get("use_sampling") is True:
        raise ValueError("AI cache v1 does not accept stochastic MuScriptor sampling")

    source_path = Path(request.audio_path)
    info = soundfile.info(source_path)
    config = checkpoint.get("config")
    if not isinstance(config, Mapping):
        raise ValueError("AI cache requires a hash-pinned MuScriptor config")
    path_free_options = {
        str(key): value
        for key, value in request.options.items()
        if key not in _PATH_OPTIONS
    }
    unexpected_options = set(path_free_options).difference(_CACHE_OPTION_KEYS)
    if unexpected_options:
        raise ValueError(
            "AI cache v1 does not recognise MuScriptor option(s): "
            + ", ".join(sorted(unexpected_options))
        )
    # This validation rejects non-finite or non-JSON options instead of silently
    # omitting a value that could affect inference.
    _canonical_bytes(path_free_options)
    runtime_identity = _runtime_identity(runtime, request)
    document: dict[str, Any] = {
        "schema": AI_CACHE_KEY_SCHEMA,
        "scope": _CACHE_SCOPE,
        "backend": "muscriptor",
        "source": {
            "sha256": source.get("sha256"),
            "bytes": source.get("bytes"),
            "audio": {
                "format": info.format,
                "subtype": info.subtype,
                "sample_rate": int(info.samplerate),
                "channels": int(info.channels),
                "frames": int(info.frames),
            },
        },
        "request": {
            "schema": AI_REQUEST_SCHEMA,
            "roles": list(request.roles),
            "start_seconds": request.start_seconds,
            "end_seconds": request.end_seconds,
            "bpm": float(bpm),
            "options": path_free_options,
        },
        "checkpoint": {
            "sha256": checkpoint.get("sha256"),
            "bytes": checkpoint.get("bytes"),
            "variant": checkpoint.get("variant"),
            "config_sha256": config.get("sha256"),
            "config_bytes": config.get("bytes"),
        },
        "worker": {
            "sha256": worker.get("sha256"),
            "bytes": worker.get("bytes"),
        },
        "runtime": runtime_identity,
        "output_contract": {
            "candidate_schema": AI_CANDIDATE_SCHEMA,
            "raw_artifacts": list(_RAW_ARTIFACTS),
            "performance_schema": MUSCRIPTOR_PERFORMANCE_SCHEMA,
        },
    }
    for label, record in (
        ("source", document["source"]),
        ("checkpoint", document["checkpoint"]),
        ("worker", document["worker"]),
    ):
        if not isinstance(record.get("sha256"), str) or len(record["sha256"]) != 64:
            raise ValueError(f"AI cache {label} SHA-256 evidence is invalid")
        if not isinstance(record.get("bytes"), int) or record["bytes"] < 0:
            raise ValueError(f"AI cache {label} byte evidence is invalid")
    config_sha256 = document["checkpoint"].get("config_sha256")
    if not isinstance(config_sha256, str) or len(config_sha256) != 64:
        raise ValueError("AI cache model-config SHA-256 evidence is invalid")
    digest = hashlib.sha256(_canonical_bytes(document)).hexdigest()
    return {
        "schema": AI_CACHE_KEY_SCHEMA,
        "scope": _CACHE_SCOPE,
        "key_sha256": digest,
        "document": document,
        "runtime": runtime_identity,
    }


def _cache_root(value: str | Path) -> Path:
    root = Path(value).expanduser().absolute()
    if root.is_symlink():
        raise ValueError("AI application cache root must not be a symlink")
    if root.exists() and not root.is_dir():
        raise ValueError("AI application cache root must be a directory")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise ValueError(
            "AI application cache root must not grant group or other permissions"
        )
    return root


def _entry_dir(root: Path, key: str) -> Path:
    if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
        raise ValueError("AI cache key must be a lowercase SHA-256 digest")
    namespace = root / AI_CACHE_NAMESPACE / "sha256"
    entry = namespace / key[:2] / key
    for component in (root / AI_CACHE_NAMESPACE, namespace, entry.parent):
        if component.is_symlink():
            raise ValueError("AI cache namespace must not contain symbolic links")
    resolved_root = root.resolve()
    resolved_namespace = namespace.resolve()
    resolved_entry = entry.resolve()
    if (
        resolved_root not in resolved_namespace.parents
        or resolved_namespace not in resolved_entry.parents
    ):
        raise ValueError("AI cache entry path escaped its namespace")
    return entry


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"AI cache {label} is not a regular file")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"AI cache {label} is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"AI cache {label} must be a JSON object")
    return document


def _validate_origin_performance(
    performance: Mapping[str, Any],
    candidate: AITranscriptionCandidate,
    identity: Mapping[str, Any],
) -> None:
    expected_fields = {
        "schema",
        "measurement_mode",
        "device",
        "timings_seconds",
        "chunks",
        "note_count",
        "peak_process_rss_bytes",
        "memory_scope",
        "clock",
    }
    if set(performance) != expected_fields:
        raise ValueError("AI cache origin performance fields are invalid")
    if performance.get("schema") != MUSCRIPTOR_PERFORMANCE_SCHEMA:
        raise ValueError("AI cache origin performance schema is invalid")
    if performance.get("measurement_mode") != "fresh-process":
        raise ValueError("AI cache origin was not a fresh-process inference")
    expected_device = identity["document"]["runtime"]["effective_device"]
    if performance.get("device") != expected_device:
        raise ValueError("AI cache origin performance device changed")
    if performance.get("note_count") != len(candidate.notes):
        raise ValueError("AI cache origin performance note count changed")
    timings = performance.get("timings_seconds")
    chunks = performance.get("chunks")
    if not isinstance(timings, Mapping) or not isinstance(chunks, Mapping):
        raise ValueError("AI cache origin performance evidence is incomplete")
    required_timings = (
        "audio_preparation",
        "model_load",
        "transcription",
        "worker_total",
    )
    optional_timings = (
        "time_to_first_note_start",
        "time_to_first_completed_note",
        "time_to_first_completed_chunk",
    )
    if set(timings) != {*required_timings, *optional_timings}:
        raise ValueError("AI cache origin performance timing fields are invalid")
    for label in required_timings:
        value = timings.get(label)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError(f"AI cache origin performance {label} is invalid")
    for label in optional_timings:
        value = timings.get(label)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
            or float(value) > float(timings["worker_total"]) + 0.05
        ):
            raise ValueError(f"AI cache origin performance {label} is invalid")
    if candidate.notes and any(
        timings.get(label) is None
        for label in ("time_to_first_note_start", "time_to_first_completed_note")
    ):
        raise ValueError("AI cache origin performance first-note timing is missing")
    if (
        timings.get("time_to_first_note_start") is not None
        and timings.get("time_to_first_completed_note") is not None
        and float(timings["time_to_first_note_start"])
        > float(timings["time_to_first_completed_note"]) + 0.05
    ):
        raise ValueError("AI cache origin first-note timings are out of order")
    if float(timings["worker_total"]) + 0.05 < sum(
        float(timings[label])
        for label in ("audio_preparation", "model_load", "transcription")
    ):
        raise ValueError("AI cache origin performance stages exceed worker total")
    if set(chunks) != {"seconds", "planned", "reported"}:
        raise ValueError("AI cache origin performance chunk fields are invalid")
    if chunks.get("seconds") != 5.0:
        raise ValueError("AI cache origin performance chunk size changed")
    for label in ("planned", "reported"):
        value = chunks.get(label)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"AI cache origin performance chunks.{label} is invalid")
    excerpt = candidate.metadata["excerpt"]
    expected_planned = math.ceil(float(excerpt["duration_seconds"]) / 5.0)
    if chunks.get("planned") != expected_planned:
        raise ValueError("AI cache origin performance planned chunks changed")
    if int(chunks["reported"]) > int(chunks["planned"]):
        raise ValueError("AI cache origin reported chunks exceed planned chunks")
    peak_rss = performance.get("peak_process_rss_bytes")
    if isinstance(peak_rss, bool) or not isinstance(peak_rss, int) or peak_rss < 0:
        raise ValueError("AI cache origin peak RSS is invalid")
    if (
        performance.get("memory_scope")
        != "process RSS high-water; accelerator allocation excluded"
    ):
        raise ValueError("AI cache origin memory scope changed")
    if performance.get("clock") != "time.perf_counter":
        raise ValueError("AI cache origin performance clock changed")


def _validate_candidate_identity(
    candidate: AITranscriptionCandidate, identity: Mapping[str, Any]
) -> None:
    key = identity["document"]
    request = key["request"]
    options = request["options"]
    runtime = key["runtime"]
    metadata = candidate.metadata
    expected_metadata_keys = {
        "device",
        "checkpoint_sha256",
        "excerpt",
        "source_sample_rate",
        "instruments",
        "progress",
        "execution",
        "velocity_policy",
    }
    if set(metadata) != expected_metadata_keys:
        raise ValueError("AI cache candidate metadata fields are invalid")
    if candidate.backend != "muscriptor":
        raise ValueError("AI cache candidate backend is not MuScriptor")
    if tuple(candidate.raw_artifacts) != _RAW_ARTIFACTS:
        raise ValueError("AI cache candidate raw artifact declaration is invalid")
    if metadata.get("checkpoint_sha256") != key["checkpoint"]["sha256"]:
        raise ValueError("AI cache candidate checkpoint identity changed")
    if metadata.get("device") != runtime["effective_device"]:
        raise ValueError("AI cache candidate effective device changed")
    if metadata.get("instruments") != request["roles"]:
        raise ValueError("AI cache candidate requested instruments changed")
    if metadata.get("source_sample_rate") != key["source"]["audio"]["sample_rate"]:
        raise ValueError("AI cache candidate source sample rate changed")
    expected_model_version = (
        f"muscriptor-{runtime['muscriptor_version']}/{key['checkpoint']['sha256'][:12]}"
    )
    if candidate.model_version != expected_model_version:
        raise ValueError("AI cache candidate model version changed")

    excerpt = metadata.get("excerpt")
    if not isinstance(excerpt, Mapping):
        raise ValueError("AI cache candidate excerpt evidence is missing")
    if set(excerpt) != {"start_seconds", "end_seconds", "duration_seconds"}:
        raise ValueError("AI cache candidate excerpt fields are invalid")
    if excerpt.get("start_seconds") != request["start_seconds"]:
        raise ValueError("AI cache candidate excerpt start changed")
    if excerpt.get("end_seconds") != request["end_seconds"]:
        raise ValueError("AI cache candidate excerpt end changed")
    audio = key["source"]["audio"]
    sample_rate = int(audio["sample_rate"])
    frames = int(audio["frames"])
    start_frame = round(float(request["start_seconds"]) * sample_rate)
    end_frame = (
        frames
        if request["end_seconds"] is None
        else min(frames, round(float(request["end_seconds"]) * sample_rate))
    )
    if start_frame >= frames or end_frame <= start_frame:
        raise ValueError("AI cache candidate excerpt does not overlap the source")
    duration = (end_frame - start_frame) / sample_rate
    candidate_duration = excerpt.get("duration_seconds")
    if (
        isinstance(candidate_duration, bool)
        or not isinstance(candidate_duration, (int, float))
        or not math.isclose(float(candidate_duration), duration, abs_tol=1e-9)
    ):
        raise ValueError("AI cache candidate excerpt duration changed")
    excerpt_end = float(request["start_seconds"]) + duration
    for note in candidate.notes:
        if note.start_seconds + 1e-9 < float(request["start_seconds"]):
            raise ValueError("AI cache candidate note starts before the excerpt")
        if note.end_seconds > excerpt_end + 1e-9:
            raise ValueError("AI cache candidate note ends after the excerpt")

    execution = metadata.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("AI cache candidate execution evidence is missing")
    strategy = (
        "sampling"
        if options["use_sampling"]
        else ("beam-search" if int(options["beam_size"]) > 1 else "greedy")
    )
    expected_execution = {
        "schema": "sunofriend.muscriptor-execution.v1",
        "model_size": options["model_size"],
        "model_config_sha256": key["checkpoint"]["config_sha256"],
        "decoding": {
            "strategy": strategy,
            "beam_size": options["beam_size"],
            "batch_size": options["batch_size"],
            "cfg_coef": options["cfg_coef"],
            "temperature": options["temperature"],
            "use_sampling": options["use_sampling"],
            "no_eos_is_ok": options["no_eos_is_ok"],
        },
        "chunking": {
            "seconds": options["chunk_seconds"],
            "policy": "independent-five-second-chunks",
            "prelude_forcing": False,
            "prelude_forcing_supported": False,
        },
    }
    if dict(execution) != expected_execution:
        raise ValueError("AI cache candidate execution evidence changed")
    if (
        metadata.get("velocity_policy")
        != "not supplied by MuScriptor; preserved as null"
    ):
        raise ValueError("AI cache candidate velocity policy changed")
    progress = metadata.get("progress")
    if not isinstance(progress, list):
        raise ValueError("AI cache candidate progress evidence is invalid")
    for item in progress:
        if not isinstance(item, Mapping) or set(item) != {"completed", "total"}:
            raise ValueError("AI cache candidate progress item is invalid")
        completed = item.get("completed")
        total = item.get("total")
        if (
            isinstance(completed, bool)
            or not isinstance(completed, int)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or completed < 0
            or total < 0
            or completed > total
        ):
            raise ValueError("AI cache candidate progress values are invalid")


def _validate_entry(
    root: Path, entry_dir: Path, identity: Mapping[str, Any]
) -> AICacheEntry:
    if entry_dir.is_symlink() or not entry_dir.is_dir():
        raise ValueError("AI cache entry is not a regular directory")
    entry_path = entry_dir / "entry.json"
    document = _read_json(entry_path, "entry manifest")
    if document.get("schema") != AI_CACHE_ENTRY_SCHEMA:
        raise ValueError("AI cache entry schema is invalid")
    expected_document_keys = {
        "schema",
        "status",
        "created_at",
        "key_sha256",
        "key",
        "scope",
        "origin",
        "candidate",
        "artifacts",
        "effects",
    }
    if set(document) != expected_document_keys:
        raise ValueError("AI cache entry manifest fields are invalid")
    if document.get("status") != "complete":
        raise ValueError("AI cache entry is not complete")
    if document.get("scope") != _CACHE_SCOPE:
        raise ValueError("AI cache entry scope is invalid")
    created_at = document.get("created_at")
    if not isinstance(created_at, str):
        raise ValueError("AI cache entry creation time is invalid")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("AI cache entry creation time is invalid") from exc
    if parsed_created_at.tzinfo is None or parsed_created_at.utcoffset() is None:
        raise ValueError("AI cache entry creation time has no timezone")
    if document.get("key_sha256") != identity.get("key_sha256"):
        raise ValueError("AI cache entry key does not match the requested key")
    if document.get("key") != identity.get("document"):
        raise ValueError("AI cache entry identity changed")
    if hashlib.sha256(_canonical_bytes(document["key"])).hexdigest() != document.get(
        "key_sha256"
    ):
        raise ValueError("AI cache entry key digest is invalid")

    effects = document.get("effects")
    if effects != {
        "raw_candidate_mutated": False,
        "midi_cached": False,
        "source_cached": False,
        "checkpoint_cached": False,
    }:
        raise ValueError("AI cache entry effects are invalid")
    origin = document.get("origin")
    expected_origin_keys = {
        "run_id",
        "worker_execution_mode",
        "worker_sha256",
        "source_sha256",
        "checkpoint_sha256",
    }
    if not isinstance(origin, Mapping) or set(origin) != expected_origin_keys:
        raise ValueError("AI cache entry origin is invalid")
    run_id = origin.get("run_id")
    if not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("AI cache entry origin run_id is invalid")
    if origin.get("worker_execution_mode") != "fresh-subprocess":
        raise ValueError("AI cache entry origin execution mode is invalid")
    expected_origin_hashes = {
        "worker_sha256": document["key"]["worker"]["sha256"],
        "source_sha256": document["key"]["source"]["sha256"],
        "checkpoint_sha256": document["key"]["checkpoint"]["sha256"],
    }
    if any(
        origin.get(label) != value for label, value in expected_origin_hashes.items()
    ):
        raise ValueError("AI cache entry origin hashes are invalid")

    artifacts = document.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("AI cache entry artifact manifest is invalid")
    expected_labels = {"candidate.raw.json", *_RAW_ARTIFACTS}
    if set(artifacts) != expected_labels:
        raise ValueError("AI cache entry has an unexpected artifact set")

    expected_files = {Path("entry.json")}
    for label in sorted(expected_labels):
        record = artifacts.get(label)
        if not isinstance(record, Mapping):
            raise ValueError(f"AI cache artifact record is invalid: {label}")
        if set(record) != {"path", "bytes", "sha256", "semantics"}:
            raise ValueError(f"AI cache artifact record fields are invalid: {label}")
        expected_relative = Path("payload") / label
        if record.get("path") != str(expected_relative):
            raise ValueError(f"AI cache artifact path is invalid: {label}")
        path = entry_dir / expected_relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"AI cache artifact is missing or linked: {label}")
        if path.stat().st_size != record.get("bytes") or _sha256(path) != record.get(
            "sha256"
        ):
            raise ValueError(f"AI cache artifact hash changed: {label}")
        expected_semantics = (
            "raw-model-candidate"
            if label == "candidate.raw.json"
            else "origin-inference-performance-not-current-hit-timing"
        )
        if record.get("semantics") != expected_semantics:
            raise ValueError(f"AI cache artifact semantics changed: {label}")
        expected_files.add(expected_relative)

    actual_files: set[Path] = set()
    for path in entry_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError("AI cache entry contains a symbolic link")
        if path.is_file():
            actual_files.add(path.relative_to(entry_dir))
        elif path.is_dir() and path.name != "payload":
            raise ValueError("AI cache entry contains an unexpected directory")
    if actual_files != expected_files:
        raise ValueError("AI cache entry contains unexpected files")

    raw = _read_json(entry_dir / "payload" / "candidate.raw.json", "raw candidate")
    candidate = AITranscriptionCandidate.from_dict(raw)
    _validate_candidate_identity(candidate, identity)
    expected_candidate_summary = {
        "model_version": candidate.model_version,
        "note_count": len(candidate.notes),
        "candidate_raw_sha256": artifacts["candidate.raw.json"]["sha256"],
    }
    if document.get("candidate") != expected_candidate_summary:
        raise ValueError("AI cache entry candidate summary is invalid")
    performance = _read_json(
        entry_dir / "payload" / "muscriptor.performance.json",
        "origin performance",
    )
    _validate_origin_performance(performance, candidate, identity)

    return AICacheEntry(
        cache_root=root,
        entry_dir=entry_dir,
        document=document,
        manifest_sha256=_sha256(entry_path),
        manifest_bytes=entry_path.stat().st_size,
    )


def find_muscriptor_cache_entry(
    cache_dir: str | Path, identity: Mapping[str, Any]
) -> AICacheEntry | None:
    """Return a verified entry, or ``None`` for a clean cache miss."""

    root = _cache_root(cache_dir)
    entry = _entry_dir(root, str(identity.get("key_sha256", "")))
    if not entry.exists():
        return None
    return _validate_entry(root, entry, identity)


def materialise_muscriptor_cache_entry(
    entry: AICacheEntry, run_dir: str | Path
) -> list[Path]:
    """Copy a verified entry into one fresh immutable run without hard links."""

    target = Path(run_dir).expanduser().absolute()
    if not target.is_dir():
        raise ValueError("AI cache materialisation requires an existing run directory")
    artifacts = entry.document["artifacts"]
    copied: list[Path] = []
    for label in ("candidate.raw.json", *_RAW_ARTIFACTS):
        source = entry.entry_dir / str(artifacts[label]["path"])
        destination = target / label
        _copy_verified(source, destination, artifacts[label])
        copied.append(destination)
    entry_copy = target / "cache.entry.json"
    _copy_verified(
        entry.entry_dir / "entry.json",
        entry_copy,
        {"bytes": entry.manifest_bytes, "sha256": entry.manifest_sha256},
    )
    copied.append(entry_copy)
    return copied


def copy_muscriptor_cache_entry_manifest(
    entry: AICacheEntry, run_dir: str | Path
) -> Path:
    """Copy only the verified entry manifest into a fresh producer run."""

    target = Path(run_dir).expanduser().absolute() / "cache.entry.json"
    _copy_verified(
        entry.entry_dir / "entry.json",
        target,
        {"bytes": entry.manifest_bytes, "sha256": entry.manifest_sha256},
    )
    return target


def publish_muscriptor_cache_entry(
    *,
    cache_dir: str | Path,
    identity: Mapping[str, Any],
    run_dir: str | Path,
    origin: Mapping[str, Any],
) -> tuple[AICacheEntry, bool]:
    """Atomically publish a verified fresh result without replacing an entry."""

    root = _cache_root(cache_dir)
    destination = _entry_dir(root, str(identity.get("key_sha256", "")))
    existing = find_muscriptor_cache_entry(root, identity)
    if existing is not None:
        return _compare_origin_with_existing(existing, Path(run_dir)), False

    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary: Path | None = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
    )
    try:
        payload = temporary / "payload"
        payload.mkdir(mode=0o700)
        source_root = Path(run_dir).expanduser().absolute()
        records: dict[str, dict[str, Any]] = {}
        for label in ("candidate.raw.json", *_RAW_ARTIFACTS):
            source = source_root / label
            if source.is_symlink() or not source.is_file():
                raise ValueError(
                    f"AI cache origin artifact is missing or linked: {label}"
                )
            destination_path = payload / label
            expected = {
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
            }
            _copy_verified(source, destination_path, expected)
            records[label] = {
                **_file_record(destination_path, relative_to=temporary),
                "semantics": (
                    "raw-model-candidate"
                    if label == "candidate.raw.json"
                    else "origin-inference-performance-not-current-hit-timing"
                ),
            }

        raw = _read_json(payload / "candidate.raw.json", "origin raw candidate")
        candidate = AITranscriptionCandidate.from_dict(raw)
        _validate_candidate_identity(candidate, identity)
        performance = _read_json(
            payload / "muscriptor.performance.json", "origin performance"
        )
        _validate_origin_performance(performance, candidate, identity)

        document = {
            "schema": AI_CACHE_ENTRY_SCHEMA,
            "status": "complete",
            "created_at": _utc_now(),
            "key_sha256": identity["key_sha256"],
            "key": identity["document"],
            "scope": _CACHE_SCOPE,
            "origin": dict(origin),
            "candidate": {
                "model_version": candidate.model_version,
                "note_count": len(candidate.notes),
                "candidate_raw_sha256": records["candidate.raw.json"]["sha256"],
            },
            "artifacts": records,
            "effects": {
                "raw_candidate_mutated": False,
                "midi_cached": False,
                "source_cached": False,
                "checkpoint_cached": False,
            },
        }
        _write_json(temporary / "entry.json", document)
        directory_fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        try:
            os.rename(temporary, destination)
        except OSError:
            if not destination.exists():
                raise
            winner = _validate_entry(root, destination, identity)
            return _compare_origin_with_existing(winner, source_root), False
        temporary = None
        return _validate_entry(root, destination, identity), True
    finally:
        if temporary is not None and temporary.exists() and temporary.is_dir():
            shutil.rmtree(temporary)


def _compare_origin_with_existing(entry: AICacheEntry, run_dir: Path) -> AICacheEntry:
    artifacts = entry.document["artifacts"]
    # Timing and RSS in muscriptor.performance.json are intentionally
    # run-specific.  Concurrent identical producers are equivalent when their
    # raw musical candidate is byte-identical; the winning entry retains its
    # own original performance provenance.
    label = "candidate.raw.json"
    source = run_dir / label
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"AI cache origin artifact is missing or linked: {label}")
    if (
        source.stat().st_size != artifacts[label]["bytes"]
        or _sha256(source) != artifacts[label]["sha256"]
    ):
        raise ValueError(
            "AI cache conflict: identical inputs produced different raw candidates"
        )
    return entry


__all__ = [
    "AI_CACHE_BENCHMARK_SCHEMA",
    "AI_CACHE_ENTRY_SCHEMA",
    "AI_CACHE_EVENT_SCHEMA",
    "AI_CACHE_KEY_SCHEMA",
    "AI_CACHE_NAMESPACE",
    "AICacheEntry",
    "build_muscriptor_cache_identity",
    "copy_muscriptor_cache_entry_manifest",
    "find_muscriptor_cache_entry",
    "materialise_muscriptor_cache_entry",
    "publish_muscriptor_cache_entry",
]
