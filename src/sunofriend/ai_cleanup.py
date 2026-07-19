"""Immutable learned target/residual challengers for short local excerpts."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .ai_runtime import (
    AI_CLEANUP_MODEL_MANIFESTS,
    DEMUCS_HTDEMUCS_SHA256,
    collect_ai_diagnostics,
    resolve_ai_python,
)


AI_CLEANUP_SCHEMA = "sunofriend.ai-cleanup.v1"
AI_CLEANUP_REQUEST_SCHEMA = "sunofriend.ai-cleanup-request.v1"
MAXIMUM_EXCERPT_SECONDS = 60.0
DEMUCS_MODEL_SIGNATURE = "955717e8"
DEMUCS_MODEL_VARIANT = "htdemucs"
DEMUCS_PACKAGE_VERSION = "4.0.1"
DEMUCS_TARGETS = ("bass", "drums", "other", "vocals")
DEMUCS_SAMPLE_RATE = 44100


class AICleanupRunError(RuntimeError):
    """A learned cleanup failed after its immutable evidence directory existed."""

    def __init__(self, message: str, run_dir: Path):
        super().__init__(f"{message}; immutable run record: {run_dir}")
        self.run_dir = run_dir


def run_ai_cleanup(
    audio_path: str | Path,
    *,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    target: str,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    overlap: float = 0.25,
    python: str | Path | None = None,
    worker_path: str | Path | None = None,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Run pinned htdemucs and preserve a reconstructable review challenger."""

    import numpy as np
    import soundfile

    audio = Path(audio_path).expanduser().absolute()
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    destination = Path(out_dir).expanduser().absolute()
    _validate_inputs(
        audio,
        checkpoint,
        destination,
        target=target,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        overlap=overlap,
        timeout_seconds=timeout_seconds,
    )
    source_sha256 = _sha256(audio)
    checkpoint_sha256 = _sha256(checkpoint)
    if checkpoint_sha256 != DEMUCS_HTDEMUCS_SHA256:
        raise ValueError(
            "Demucs checkpoint hash does not match the pinned official htdemucs "
            f"checkpoint: expected {DEMUCS_HTDEMUCS_SHA256}, got {checkpoint_sha256}"
        )

    executable = resolve_ai_python(python)
    worker = (
        Path(worker_path).expanduser().absolute()
        if worker_path
        else Path(__file__).with_name("ai_cleanup_worker.py")
    )
    if not worker.is_file():
        raise FileNotFoundError(f"AI cleanup worker was not found: {worker}")

    with soundfile.SoundFile(str(audio)) as handle:
        sample_rate = int(handle.samplerate)
        channels = int(handle.channels)
        frames = int(len(handle))
        duration_seconds = frames / sample_rate
        end = duration_seconds if end_seconds is None else float(end_seconds)
        start = float(start_seconds)
        if end > duration_seconds + 1.0 / sample_rate:
            raise ValueError(
                f"end_seconds exceeds the {duration_seconds:.6f}-second source"
            )
        if end - start > MAXIMUM_EXCERPT_SECONDS:
            raise ValueError(
                "ai-cleanup is a short experimental workflow; choose an excerpt "
                f"of at most {MAXIMUM_EXCERPT_SECONDS:g} seconds"
            )
        if sample_rate != DEMUCS_SAMPLE_RATE:
            raise ValueError(
                f"ai-cleanup v1 requires {DEMUCS_SAMPLE_RATE} Hz PCM audio; "
                f"source is {sample_rate} Hz"
            )
        if channels not in (1, 2):
            raise ValueError("ai-cleanup v1 supports mono or stereo audio")
        start_frame = int(round(start * sample_rate))
        end_frame = min(frames, int(round(end * sample_rate)))
        handle.seek(start_frame)
        source = handle.read(end_frame - start_frame, dtype="float32", always_2d=True)
    if not len(source):
        raise ValueError("The requested excerpt contains no audio frames")
    if not np.all(np.isfinite(source)):
        raise ValueError("Source audio contains non-finite samples")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"AI cleanup output already exists and will not be overwritten: {destination}"
        ) from exc

    source_output = destination / "source-excerpt.wav"
    target_array = destination / "model-target.float32.npy"
    target_output = destination / "target.wav"
    residual_output = destination / "residual.wav"
    request_path = destination / "request.json"
    worker_result_path = destination / "worker-result.json"
    stdout_path = destination / "worker.stdout.log"
    stderr_path = destination / "worker.stderr.log"
    report_path = destination / "ai_cleanup.json"

    soundfile.write(source_output, source, sample_rate, subtype="PCM_24")
    persisted_source, _ = soundfile.read(source_output, dtype="float32", always_2d=True)
    request: dict[str, Any] = {
        "schema": AI_CLEANUP_REQUEST_SCHEMA,
        "backend": "demucs",
        "model": {
            "variant": DEMUCS_MODEL_VARIANT,
            "signature": DEMUCS_MODEL_SIGNATURE,
            "package_version": DEMUCS_PACKAGE_VERSION,
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": checkpoint_sha256,
        },
        "source_excerpt": {
            "path": str(source_output),
            "sha256": _sha256(source_output),
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": len(persisted_source),
        },
        "target": target,
        "inference": {
            "device": "cpu",
            "shifts": 0,
            "overlap": float(overlap),
            "split": True,
            "num_workers": 0,
        },
    }
    _write_json(request_path, request)
    command = [
        str(executable),
        str(worker),
        "--request",
        str(request_path),
        "--target-array",
        str(target_array),
        "--result",
        str(worker_result_path),
    ]
    started_at = _utc_now()
    started_clock = time.monotonic()
    error: str | None = None
    exit_code: int | None = None
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
        elif not target_array.is_file() or not worker_result_path.is_file():
            error = "worker completed without its target array and result JSON"
    except subprocess.TimeoutExpired as exc:
        error = f"worker timed out after {timeout_seconds:g} seconds"
        stdout_path.write_text(_subprocess_text(exc.stdout), encoding="utf-8")
        stderr_path.write_text(_subprocess_text(exc.stderr), encoding="utf-8")
    except Exception as exc:  # Preserve the failed run as evidence.
        error = f"{type(exc).__name__}: {exc}"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(error + "\n", encoding="utf-8")

    base_report: dict[str, Any] = {
        "schema": AI_CLEANUP_SCHEMA,
        "status": "failed" if error else "running",
        "operation": "ai-cleanup",
        "purpose": (
            "Pinned learned-separation challenger for listening and transcription; "
            "not an automatically promoted source identification."
        ),
        "started_at": started_at,
        "completed_at": _utc_now(),
        "elapsed_seconds": round(time.monotonic() - started_clock, 6),
        "command": command,
        "exit_code": exit_code,
        "error": error,
        "source": {
            "path": str(audio),
            "sha256": source_sha256,
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": frames,
            "duration_seconds": round(duration_seconds, 9),
        },
        "excerpt": {
            "start_seconds": round(start, 9),
            "end_seconds": round(end, 9),
            "duration_seconds": round(len(persisted_source) / sample_rate, 9),
            "frames": len(persisted_source),
        },
        "backend": {
            "manifest": asdict(AI_CLEANUP_MODEL_MANIFESTS["demucs"]),
            "model_variant": DEMUCS_MODEL_VARIANT,
            "model_signature": DEMUCS_MODEL_SIGNATURE,
            "package_version": DEMUCS_PACKAGE_VERSION,
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": checkpoint_sha256,
            "expected_checkpoint_sha256": DEMUCS_HTDEMUCS_SHA256,
            "checkpoint_hash_verified_before_deserialisation": True,
            "trusted_pickle_opt_in": True,
            "runtime": collect_ai_diagnostics(executable),
        },
        "target_role": target,
        "inference": request["inference"],
        "effects": {
            "source_audio_mutated": False,
            "checkpoint_mutated": False,
            "midi_mutated": False,
            "automatic_promotion": False,
        },
        "warnings": [
            "The official repository does not state separate pretrained-weight terms; keep this checkpoint and output private.",
            "Demucs roles are broad source families, not proof of the original instrument or patch.",
            "Listen to the unchanged source, target and residual before using the target for MIDI transcription.",
        ],
    }
    if error:
        base_report["artifacts"] = _existing_artifacts(destination)
        _write_json(report_path, base_report)
        raise AICleanupRunError(error, destination)

    try:
        worker_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
        _validate_worker_result(worker_result, request, target_array)
        learned_target = np.load(target_array, allow_pickle=False)
        if learned_target.shape != persisted_source.shape:
            raise ValueError(
                "worker target shape does not match the persisted source excerpt: "
                f"{learned_target.shape} != {persisted_source.shape}"
            )
        if learned_target.dtype != np.float32:
            learned_target = learned_target.astype("float32")
        if not np.all(np.isfinite(learned_target)):
            raise ValueError("worker target contains non-finite samples")
        clipping_count = int(np.count_nonzero(np.abs(learned_target) > 1.0))
        learned_target = np.clip(learned_target, -1.0, 1.0)
        soundfile.write(target_output, learned_target, sample_rate, subtype="PCM_24")
        persisted_target, _ = soundfile.read(
            target_output, dtype="float32", always_2d=True
        )
        # Define the residual from persisted evidence, so quantisation cannot
        # hide a reconstruction failure.
        residual = persisted_source - persisted_target
        residual_clipping_count = int(np.count_nonzero(np.abs(residual) > 1.0))
        soundfile.write(residual_output, residual, sample_rate, subtype="PCM_24")
        persisted_residual, _ = soundfile.read(
            residual_output, dtype="float32", always_2d=True
        )
        reconstruction_error = persisted_source - (
            persisted_target + persisted_residual
        )
        maximum_error = float(np.max(np.abs(reconstruction_error)))
        rms_error = _rms(reconstruction_error)
        reconstruction_passed = maximum_error <= 1e-6
        source_rms = _rms(persisted_source)
        target_rms = _rms(persisted_target)
        residual_rms = _rms(persisted_residual)
        source_unchanged = _sha256(audio) == source_sha256
        checkpoint_unchanged = _sha256(checkpoint) == checkpoint_sha256
        report = {
            **base_report,
            "status": "complete" if reconstruction_passed else "review-required",
            "completed_at": _utc_now(),
            "worker": worker_result,
            "energy": {
                "source_rms": round(source_rms, 12),
                "target_rms": round(target_rms, 12),
                "residual_rms": round(residual_rms, 12),
                "target_to_source_db": _relative_db(target_rms, source_rms),
                "residual_to_source_db": _relative_db(residual_rms, source_rms),
                "target_samples_clipped_before_pcm24": clipping_count,
                "residual_samples_clipped_before_pcm24": residual_clipping_count,
            },
            "reconstruction": {
                "residual_definition": "persisted source excerpt minus persisted learned target",
                "maximum_absolute_error": round(maximum_error, 12),
                "rms_error": round(rms_error, 12),
                "threshold": 1e-6,
                "passed": reconstruction_passed,
                "persisted_pcm24_wavs_checked": True,
            },
            "artifacts": _existing_artifacts(destination),
            "effects": {
                **base_report["effects"],
                "source_audio_unchanged_after_run": source_unchanged,
                "checkpoint_unchanged_after_run": checkpoint_unchanged,
                "target_plus_residual_reconstructs_source": reconstruction_passed,
            },
        }
        _write_json(report_path, report)
        report["report"] = str(report_path)
        return report
    except Exception as exc:
        base_report.update(
            {
                "status": "failed",
                "completed_at": _utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
                "artifacts": _existing_artifacts(destination),
            }
        )
        _write_json(report_path, base_report)
        raise AICleanupRunError(base_report["error"], destination) from exc


def _validate_inputs(
    audio: Path,
    checkpoint: Path,
    destination: Path,
    *,
    target: str,
    start_seconds: float,
    end_seconds: float | None,
    overlap: float,
    timeout_seconds: float,
) -> None:
    if not audio.is_file():
        raise ValueError(f"audio does not exist: {audio}")
    if not checkpoint.is_file() or checkpoint.suffix.lower() != ".th":
        raise ValueError("Demucs checkpoint must be an existing local .th file")
    if destination.exists():
        raise FileExistsError(
            f"AI cleanup output already exists and will not be overwritten: {destination}"
        )
    if target not in DEMUCS_TARGETS:
        raise ValueError("target must be one of: " + ", ".join(DEMUCS_TARGETS))
    if not math.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError("start_seconds must be finite and non-negative")
    if end_seconds is not None and (
        not math.isfinite(end_seconds) or end_seconds <= start_seconds
    ):
        raise ValueError("end_seconds must be finite and later than start_seconds")
    if not math.isfinite(overlap) or not 0 <= overlap < 1:
        raise ValueError("overlap must be finite and in the range 0 <= overlap < 1")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")


def _validate_worker_result(
    result: Mapping[str, Any], request: Mapping[str, Any], target_array: Path
) -> None:
    if result.get("schema") != "sunofriend.ai-cleanup-worker-result.v1":
        raise ValueError("worker returned an unsupported result schema")
    if result.get("status") != "complete":
        raise ValueError("worker result is not complete")
    if result.get("target") != request["target"]:
        raise ValueError("worker returned a different target role")
    if result.get("checkpoint_sha256") != request["model"]["checkpoint_sha256"]:
        raise ValueError("worker checkpoint hash does not match the request")
    if result.get("source_excerpt_sha256") != request["source_excerpt"]["sha256"]:
        raise ValueError("worker source hash does not match the request")
    if result.get("target_array_sha256") != _sha256(target_array):
        raise ValueError("worker target-array hash does not match the saved array")


def _existing_artifacts(directory: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "ai_cleanup.json":
            artifacts[path.name] = {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
    return artifacts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rms(samples: Any) -> float:
    import numpy as np

    return float(np.sqrt(np.mean(np.square(samples.astype("float64")))))


def _relative_db(numerator: float, denominator: float) -> float | None:
    if numerator <= 0 or denominator <= 0:
        return None
    return round(20.0 * math.log10(numerator / denominator), 9)


def _subprocess_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


__all__ = [
    "AI_CLEANUP_REQUEST_SCHEMA",
    "AI_CLEANUP_SCHEMA",
    "AICleanupRunError",
    "DEMUCS_MODEL_SIGNATURE",
    "DEMUCS_MODEL_VARIANT",
    "DEMUCS_PACKAGE_VERSION",
    "DEMUCS_SAMPLE_RATE",
    "DEMUCS_TARGETS",
    "MAXIMUM_EXCERPT_SECONDS",
    "run_ai_cleanup",
]
