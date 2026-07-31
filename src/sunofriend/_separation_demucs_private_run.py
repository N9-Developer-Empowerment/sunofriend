"""Private hash-pinned HTDemucs development experiments.

This module is intentionally not imported by the CLI, TUI, Simple workflow,
Workbench or public separation contract.  It exercises one already-installed,
hash-pinned checkpoint on one bounded excerpt and preserves review evidence.
It does not create an accepted source, mutate the source graph, select a
candidate, enable a backend or make any publication claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .ai_cleanup import (
    DEMUCS_MODEL_SIGNATURE,
    DEMUCS_MODEL_VARIANT,
    DEMUCS_PACKAGE_VERSION,
    DEMUCS_SAMPLE_RATE,
    DEMUCS_TARGETS,
    MAXIMUM_EXCERPT_SECONDS,
)
from .ai_runtime import (
    AI_CLEANUP_MODEL_MANIFESTS,
    AI_PRIVATE_EVALUATION_MODEL_MANIFESTS,
    DEMUCS_HTDEMUCS_SHA256,
    DEMUCS_HTDEMUCS_6S_SHA256,
    collect_ai_diagnostics,
    resolve_ai_python,
)
from .separation_quality import inspect_pcm_wav


PRIVATE_DEMUCS_REQUEST_SCHEMA = "sunofriend.private-ai-separation-request.v1"
PRIVATE_DEMUCS_WORKER_RESULT_SCHEMA = (
    "sunofriend.private-ai-separation-worker-result.v1"
)
PRIVATE_DEMUCS_EXPERIMENT_SCHEMA = "sunofriend.private-demucs-four-stem-experiment.v1"
PRIVATE_DEMUCS_POLICY_ID = "private-demucs-four-stem-development-v1"
PRIVATE_DEMUCS_6S_REQUEST_SCHEMA = (
    "sunofriend.private-ai-six-source-separation-request.v1"
)
PRIVATE_DEMUCS_6S_WORKER_RESULT_SCHEMA = (
    "sunofriend.private-ai-six-source-separation-worker-result.v1"
)
PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA = (
    "sunofriend.private-demucs-six-source-experiment.v1"
)
PRIVATE_DEMUCS_6S_POLICY_ID = "private-demucs-six-source-development-v1"
DEMUCS_6S_MODEL_VARIANT = "htdemucs_6s"
DEMUCS_6S_MODEL_SIGNATURE = "5c90dfd2"
DEMUCS_6S_TARGETS = ("bass", "drums", "guitar", "other", "piano", "vocals")
_REPORT_NAME = "private-separation-experiment.json"
_ARRAY_DIRECTORY = "MODEL-ARRAYS"
_STEM_DIRECTORY = "ESTIMATED-STEMS"
_RECONSTRUCTION_DIRECTORY = "RECONSTRUCTION"
_OFFLINE_ENVIRONMENT_HINTS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "PYTHONNOUSERSITE": "1",
}


@dataclass(frozen=True)
class _PrivateDemucsConfiguration:
    request_schema: str
    worker_result_schema: str
    experiment_schema: str
    policy_id: str
    operation: str
    model_variant: str
    model_signature: str
    checkpoint_sha256: str
    targets: tuple[str, ...]
    manifest_registry: str


_FOUR_STEM_CONFIGURATION = _PrivateDemucsConfiguration(
    request_schema=PRIVATE_DEMUCS_REQUEST_SCHEMA,
    worker_result_schema=PRIVATE_DEMUCS_WORKER_RESULT_SCHEMA,
    experiment_schema=PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
    policy_id=PRIVATE_DEMUCS_POLICY_ID,
    operation="private-demucs-four-stem-experiment",
    model_variant=DEMUCS_MODEL_VARIANT,
    model_signature=DEMUCS_MODEL_SIGNATURE,
    checkpoint_sha256=DEMUCS_HTDEMUCS_SHA256,
    targets=DEMUCS_TARGETS,
    manifest_registry="cleanup",
)

_SIX_STEM_CONFIGURATION = _PrivateDemucsConfiguration(
    request_schema=PRIVATE_DEMUCS_6S_REQUEST_SCHEMA,
    worker_result_schema=PRIVATE_DEMUCS_6S_WORKER_RESULT_SCHEMA,
    experiment_schema=PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA,
    policy_id=PRIVATE_DEMUCS_6S_POLICY_ID,
    operation="private-demucs-six-source-experiment",
    model_variant=DEMUCS_6S_MODEL_VARIANT,
    model_signature=DEMUCS_6S_MODEL_SIGNATURE,
    checkpoint_sha256=DEMUCS_HTDEMUCS_6S_SHA256,
    targets=DEMUCS_6S_TARGETS,
    manifest_registry="private_evaluation",
)


class _PrivateDemucsExperimentError(RuntimeError):
    """A private real-model experiment failed after evidence was reserved."""

    def __init__(self, message: str, run_dir: Path):
        super().__init__(f"{message}; private experiment record: {run_dir}")
        self.run_dir = run_dir


def _run_private_demucs_four_stem_experiment(
    audio_path: str | Path,
    *,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    overlap: float = 0.25,
    python: str | Path | None = None,
    worker_path: str | Path | None = None,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Run one bounded four-stem development experiment.

    The result is always review-required and production-ineligible.  The
    caller must supply a fresh output path and an existing local checkpoint;
    this function never installs or downloads a model.
    """

    return _run_private_demucs_experiment(
        audio_path,
        out_dir=out_dir,
        checkpoint_path=checkpoint_path,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        overlap=overlap,
        python=python,
        worker_path=worker_path,
        timeout_seconds=timeout_seconds,
        configuration=replace(
            _FOUR_STEM_CONFIGURATION,
            checkpoint_sha256=DEMUCS_HTDEMUCS_SHA256,
        ),
    )


def _run_private_demucs_six_source_experiment(
    audio_path: str | Path,
    *,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    overlap: float = 0.25,
    python: str | Path | None = None,
    worker_path: str | Path | None = None,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Run one bounded, private six-source development experiment."""

    return _run_private_demucs_experiment(
        audio_path,
        out_dir=out_dir,
        checkpoint_path=checkpoint_path,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        overlap=overlap,
        python=python,
        worker_path=worker_path,
        timeout_seconds=timeout_seconds,
        configuration=replace(
            _SIX_STEM_CONFIGURATION,
            checkpoint_sha256=DEMUCS_HTDEMUCS_6S_SHA256,
        ),
    )


def _run_private_demucs_experiment(
    audio_path: str | Path,
    *,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    start_seconds: float,
    end_seconds: float | None,
    overlap: float,
    python: str | Path | None,
    worker_path: str | Path | None,
    timeout_seconds: float,
    configuration: _PrivateDemucsConfiguration,
) -> dict[str, Any]:
    """Run one exact private model configuration without installing it."""

    import numpy as np
    import soundfile

    audio = _regular_input(audio_path, "source audio")
    checkpoint = _regular_input(checkpoint_path, "Demucs checkpoint")
    destination = Path(out_dir).expanduser().absolute()
    _validate_options(
        destination,
        checkpoint=checkpoint,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        overlap=overlap,
        timeout_seconds=timeout_seconds,
    )
    source_sha256 = _sha256(audio)
    checkpoint_sha256 = _sha256(checkpoint)
    source_identity = _file_identity(audio)
    checkpoint_identity = _file_identity(checkpoint)
    if checkpoint_sha256 != configuration.checkpoint_sha256:
        raise ValueError(
            "Demucs checkpoint hash does not match the pinned "
            f"{configuration.model_variant} checkpoint: expected "
            f"{configuration.checkpoint_sha256}, "
            f"got {checkpoint_sha256}"
        )

    executable = _executable_input(resolve_ai_python(python), "AI interpreter")
    worker = _regular_input(
        (
            Path(worker_path).expanduser().absolute()
            if worker_path is not None
            else Path(__file__).with_name("ai_cleanup_worker.py")
        ),
        "private separation worker",
    )
    worker_sha256 = _sha256(worker)
    worker_identity = _file_identity(worker)
    executable_resolved = executable.resolve(strict=True)
    executable_sha256 = _sha256(executable_resolved)
    executable_identity = _file_identity(executable, follow_symlinks=True)
    runtime = collect_ai_diagnostics(executable)

    source, sample_rate, channels, source_frames, source_duration, start, end = (
        _read_excerpt(
            audio,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            np=np,
            soundfile=soundfile,
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            "Private separation output already exists and will not be "
            f"overwritten: {destination}"
        ) from exc
    destination.chmod(0o700)

    array_dir = destination / _ARRAY_DIRECTORY
    stem_dir = destination / _STEM_DIRECTORY
    reconstruction_dir = destination / _RECONSTRUCTION_DIRECTORY
    for directory in (array_dir, stem_dir, reconstruction_dir):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)

    source_output = destination / "source-excerpt.wav"
    request_path = destination / "request.json"
    worker_result_path = destination / "worker-result.json"
    stdout_path = destination / "worker.stdout.log"
    stderr_path = destination / "worker.stderr.log"
    report_path = destination / _REPORT_NAME

    soundfile.write(source_output, source, sample_rate, subtype="PCM_24")
    _make_private_file(source_output)
    persisted_source, persisted_rate = soundfile.read(
        source_output, dtype="float32", always_2d=True
    )
    if persisted_rate != sample_rate or persisted_source.shape != source.shape:
        raise _PrivateDemucsExperimentError(
            "persisted source excerpt geometry changed", destination
        )
    source_excerpt_sha256 = _sha256(source_output)
    source_excerpt_identity = _file_identity(source_output)
    request: dict[str, Any] = {
        "schema": configuration.request_schema,
        "policy_id": configuration.policy_id,
        "evidence_scope": "private_development_only",
        "backend": "demucs",
        "model": {
            "variant": configuration.model_variant,
            "signature": configuration.model_signature,
            "package_version": DEMUCS_PACKAGE_VERSION,
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": checkpoint_sha256,
        },
        "source_excerpt": {
            "path": str(source_output),
            "sha256": source_excerpt_sha256,
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": int(len(persisted_source)),
        },
        "targets": list(configuration.targets),
        "inference": {
            "device": "cpu",
            "shifts": 0,
            "overlap": float(overlap),
            "split": True,
            "num_workers": 0,
        },
        "permissions": {
            "network_denial_enforced": False,
            "network_attempt_observation_available": False,
            "outside_write_confinement_proven": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
        },
    }
    _write_json(request_path, request)
    command = [
        str(executable),
        str(worker),
        "--request",
        str(request_path),
        "--stems-dir",
        str(array_dir),
        "--result",
        str(worker_result_path),
    ]
    environment = os.environ.copy()
    environment.update(_OFFLINE_ENVIRONMENT_HINTS)
    started_at = _utc_now()
    started_clock = time.monotonic()
    error: str | None = None
    exit_code: int | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=destination,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            close_fds=True,
            start_new_session=True,
        )
        exit_code = int(completed.returncode)
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        _make_private_file(stdout_path)
        _make_private_file(stderr_path)
        if exit_code != 0:
            error = f"worker exited with status {exit_code}"
        elif not worker_result_path.is_file():
            error = "worker completed without its result JSON"
        else:
            _make_private_file(worker_result_path)
    except subprocess.TimeoutExpired as exc:
        error = f"worker timed out after {timeout_seconds:g} seconds"
        stdout_path.write_text(_subprocess_text(exc.stdout), encoding="utf-8")
        stderr_path.write_text(_subprocess_text(exc.stderr), encoding="utf-8")
        _make_private_file(stdout_path)
        _make_private_file(stderr_path)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(error + "\n", encoding="utf-8")
        _make_private_file(stdout_path)
        _make_private_file(stderr_path)

    base_report: dict[str, Any] = {
        "schema": configuration.experiment_schema,
        "policy_id": configuration.policy_id,
        "status": "failed" if error else "validating",
        "evidence_scope": "private_development_only",
        "operation": configuration.operation,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "elapsed_seconds": round(time.monotonic() - started_clock, 6),
        "command": command,
        "exit_code": exit_code,
        "error": error,
        "source": {
            "path": str(audio),
            "sha256": source_sha256,
            "identity": source_identity,
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": source_frames,
            "duration_seconds": round(source_duration, 9),
        },
        "excerpt": {
            "start_seconds": round(start, 9),
            "end_seconds": round(end, 9),
            "duration_seconds": round(len(persisted_source) / sample_rate, 9),
            "frames": int(len(persisted_source)),
            "persisted_source": {
                "path": str(source_output.relative_to(destination)),
                "sha256": source_excerpt_sha256,
                "identity": source_excerpt_identity,
            },
        },
        "backend": {
            "manifest": _manifest_document(configuration),
            "model_variant": configuration.model_variant,
            "model_signature": configuration.model_signature,
            "package_version": DEMUCS_PACKAGE_VERSION,
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": checkpoint_sha256,
            "checkpoint_identity": checkpoint_identity,
            "expected_checkpoint_sha256": configuration.checkpoint_sha256,
            "checkpoint_hash_verified_before_output": True,
            "worker": str(worker),
            "worker_sha256": worker_sha256,
            "worker_identity": worker_identity,
            "runtime_launcher_identity": executable_identity,
            "runtime_launcher_resolved_path": str(executable_resolved),
            "runtime_launcher_sha256": executable_sha256,
            "runtime": runtime,
        },
        "inference": request["inference"],
        "permissions": {
            "accepted": False,
            "production_eligible": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
            "simple_mode_available": False,
            "studio_import_available": False,
        },
        "isolation": {
            "model_download_attempted_by_parent": False,
            "offline_environment_hints": dict(_OFFLINE_ENVIRONMENT_HINTS),
            "network_denial_enforced": False,
            "network_attempt_observation_available": False,
            "outside_write_confinement_proven": False,
            "complete_process_tree_supervision_proven": False,
        },
        "limitations": [
            "This is private development evidence, not an accepted or public separator result.",
            "Broad Demucs labels are estimates, not recovered original studio tracks.",
            "Additive reconstruction is accounting evidence, not proof that any role is accurate.",
            "Environment hints do not prove network denial or observe attempted connections.",
            "Outside-write confinement and complete descendant supervision are unproven.",
            "The installed checkpoint terms remain private-evaluation-only in Sunofriend policy.",
            "No source-graph node, MIDI candidate, selection or product output was created.",
        ],
    }
    if error:
        base_report["artifacts"] = _existing_artifacts(
            destination,
            reject_unsafe=False,
        )
        _write_sealed_report(report_path, base_report)
        raise _PrivateDemucsExperimentError(error, destination)

    try:
        source_excerpt_unchanged = _unchanged_regular_file(
            source_output,
            expected_sha256=source_excerpt_sha256,
            expected_identity=source_excerpt_identity,
        )
        if not source_excerpt_unchanged:
            raise ValueError(
                "request-bound source excerpt changed during private separation"
            )
        revalidated_source, revalidated_rate = soundfile.read(
            source_output,
            dtype="float32",
            always_2d=True,
        )
        if (
            revalidated_rate != sample_rate
            or revalidated_source.shape != persisted_source.shape
            or not _unchanged_regular_file(
                source_output,
                expected_sha256=source_excerpt_sha256,
                expected_identity=source_excerpt_identity,
            )
        ):
            raise ValueError(
                "request-bound source excerpt geometry changed during "
                "private separation"
            )
        persisted_source = revalidated_source
        worker_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
        _validate_worker_result(
            worker_result,
            request=request,
            array_dir=array_dir,
            expected_source_shape=persisted_source.shape,
            configuration=configuration,
        )
        estimates: dict[str, Any] = {}
        stem_evidence: dict[str, Any] = {}
        persisted_estimates: list[Any] = []
        for role in configuration.targets:
            array_path = array_dir / f"{role}.float32.npy"
            _make_private_file(array_path)
            estimate = np.load(array_path, allow_pickle=False)
            _validate_estimate(
                estimate,
                role=role,
                expected_shape=persisted_source.shape,
                np=np,
            )
            estimates[role] = estimate
            clipping_count = int(np.count_nonzero(np.abs(estimate) > 1.0))
            stem_path = stem_dir / f"{role}.wav"
            soundfile.write(stem_path, estimate, sample_rate, subtype="PCM_24")
            _make_private_file(stem_path)
            persisted, rate = soundfile.read(stem_path, dtype="float32", always_2d=True)
            if rate != sample_rate or persisted.shape != persisted_source.shape:
                raise ValueError(f"persisted {role} stem geometry changed")
            persisted_estimates.append(persisted)
            inspection = inspect_pcm_wav(stem_path)
            stem_evidence[role] = {
                "path": str(stem_path.relative_to(destination)),
                "sha256": inspection.sha256,
                "geometry": inspection.geometry.to_dict(),
                "peak": inspection.peak,
                "rms": inspection.rms,
                "silence_fraction": inspection.silence_fraction,
                "clipped_samples": inspection.clipped_samples,
                "samples_outside_pcm_range_before_persistence": clipping_count,
                "model_array_sha256": _sha256(array_path),
            }

        raw_sum = np.zeros_like(persisted_source, dtype="float64")
        for role in configuration.targets:
            raw_sum += estimates[role].astype("float64")
        raw_error = persisted_source.astype("float64") - raw_sum
        persisted_stem_sum = np.zeros_like(persisted_source, dtype="float64")
        for estimate in persisted_estimates:
            persisted_stem_sum += estimate.astype("float64")
        sum_clipping_count = int(np.count_nonzero(np.abs(persisted_stem_sum) > 1.0))
        sum_path = reconstruction_dir / "estimated-stem-sum.wav"
        soundfile.write(
            sum_path,
            persisted_stem_sum,
            sample_rate,
            subtype="PCM_24",
        )
        _make_private_file(sum_path)
        persisted_sum_wav, rate = soundfile.read(
            sum_path, dtype="float32", always_2d=True
        )
        if rate != sample_rate or persisted_sum_wav.shape != persisted_source.shape:
            raise ValueError("persisted estimated-stem sum geometry changed")

        residual = persisted_source.astype("float64") - persisted_stem_sum
        residual_clipping_count = int(np.count_nonzero(np.abs(residual) > 1.0))
        residual_wav_path = reconstruction_dir / "source-minus-estimated-sum.wav"
        residual_array_path = (
            reconstruction_dir / "source-minus-estimated-sum-unpersistable.float64.npy"
        )
        closure_available = residual_clipping_count == 0
        if closure_available:
            soundfile.write(residual_wav_path, residual, sample_rate, subtype="PCM_24")
            _make_private_file(residual_wav_path)
            persisted_residual, rate = soundfile.read(
                residual_wav_path, dtype="float32", always_2d=True
            )
            if (
                rate != sample_rate
                or persisted_residual.shape != persisted_source.shape
            ):
                raise ValueError("persisted reconstruction residual geometry changed")
            closure_error = persisted_source.astype("float64") - (
                persisted_stem_sum + persisted_residual.astype("float64")
            )
            closure_maximum: float | None = float(np.max(np.abs(closure_error)))
            closure_rms: float | None = _rms(closure_error)
            residual_evidence = {
                "path": str(residual_wav_path.relative_to(destination)),
                "sha256": _sha256(residual_wav_path),
                "samples_outside_pcm_range_before_persistence": 0,
                "pcm24_persisted": True,
            }
        else:
            with residual_array_path.open("xb") as handle:
                np.save(handle, residual.astype("float64"), allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            _make_private_file(residual_array_path)
            closure_maximum = None
            closure_rms = None
            residual_evidence = {
                "path": str(residual_array_path.relative_to(destination)),
                "sha256": _sha256(residual_array_path),
                "samples_outside_pcm_range_before_persistence": (
                    residual_clipping_count
                ),
                "pcm24_persisted": False,
            }
        source_unchanged = _unchanged_regular_file(
            audio,
            expected_sha256=source_sha256,
            expected_identity=source_identity,
        )
        checkpoint_unchanged = _unchanged_regular_file(
            checkpoint,
            expected_sha256=checkpoint_sha256,
            expected_identity=checkpoint_identity,
        )
        worker_unchanged = _unchanged_regular_file(
            worker,
            expected_sha256=worker_sha256,
            expected_identity=worker_identity,
        )
        executable_unchanged = _unchanged_runtime_launcher(
            executable,
            expected_resolved=executable_resolved,
            expected_sha256=executable_sha256,
            expected_identity=executable_identity,
        )
        if not source_unchanged:
            raise ValueError("source audio changed during private separation")
        if not checkpoint_unchanged:
            raise ValueError("checkpoint changed during private separation")
        if not worker_unchanged:
            raise ValueError("worker changed during private separation")
        if not executable_unchanged:
            raise ValueError("AI runtime launcher changed during private separation")
        if worker_result["source_unchanged_after_inference"] is not True:
            raise ValueError("worker did not prove source stability after inference")
        if worker_result["checkpoint_unchanged_after_inference"] is not True:
            raise ValueError(
                "worker did not prove checkpoint stability after inference"
            )

        source_rms = _rms(persisted_source)
        raw_error_rms = _rms(raw_error)
        quantization_threshold = 2.0 / (1 << 23)
        report = {
            **base_report,
            "status": "complete_review_required",
            "completed_at": _utc_now(),
            "error": None,
            "worker_result": worker_result,
            "estimated_stems": stem_evidence,
            "additive_accounting": {
                "model_stem_sum": {
                    "maximum_absolute_error": round(
                        float(np.max(np.abs(raw_error))), 12
                    ),
                    "rms_error": round(raw_error_rms, 12),
                    "error_to_source_db": _relative_db(raw_error_rms, source_rms),
                    "meaning": (
                        "Difference between the persisted source excerpt and "
                        f"the {len(configuration.targets)} unpersisted float32 "
                        "model estimates."
                    ),
                },
                "persisted_sum": {
                    "path": str(sum_path.relative_to(destination)),
                    "sha256": _sha256(sum_path),
                    "samples_outside_pcm_range_before_persistence": (
                        sum_clipping_count
                    ),
                    "purpose": "audition_only",
                    "used_for_accounting": False,
                    "meaning": (
                        "A PCM24 audition rendering of the persisted stem "
                        "arrays. It can clip and is never used to "
                        "calculate the residual or accounting closure."
                    ),
                },
                "source_minus_estimated_sum": {
                    **residual_evidence,
                },
                "persisted_sum_plus_residual": {
                    "available": closure_available,
                    "maximum_absolute_error": (
                        round(closure_maximum, 12)
                        if closure_maximum is not None
                        else None
                    ),
                    "rms_error": (
                        round(closure_rms, 12) if closure_rms is not None else None
                    ),
                    "threshold": round(quantization_threshold, 12),
                    "passed": (
                        closure_maximum <= quantization_threshold
                        if closure_maximum is not None
                        else False
                    ),
                    "meaning": (
                        "PCM accounting closure of the float64 sum of the "
                        f"{len(configuration.targets)} re-read persisted stem "
                        "WAV arrays plus the "
                        "persisted residual; this does not measure "
                        "separation accuracy. The audition sum WAV is not "
                        "used."
                    ),
                },
            },
            "immutability": {
                "source_audio_unchanged_after_run": source_unchanged,
                "request_bound_source_excerpt_unchanged_after_run": (
                    source_excerpt_unchanged
                ),
                "checkpoint_unchanged_after_run": checkpoint_unchanged,
                "worker_unchanged_after_run": worker_unchanged,
                "runtime_launcher_unchanged_after_run": executable_unchanged,
            },
            "downstream": {
                "midi_evaluation_required": True,
                "listening_review_required": True,
                "candidate_import_created": False,
                "source_graph_mutated": False,
            },
            "artifacts": _existing_artifacts(destination),
        }
        _write_sealed_report(report_path, report)
        sealed = json.loads(report_path.read_text(encoding="utf-8"))
        sealed["report"] = str(report_path)
        return sealed
    except Exception as exc:
        _remove_derived_audio(stem_dir, reconstruction_dir)
        base_report.update(
            {
                "status": "failed",
                "completed_at": _utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
                "artifacts": _existing_artifacts(
                    destination,
                    reject_unsafe=False,
                ),
            }
        )
        _write_sealed_report(report_path, base_report)
        raise _PrivateDemucsExperimentError(
            str(base_report["error"]), destination
        ) from exc


def _regular_input(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable: {path}") from exc
    if stat.S_ISLNK(details.st_mode):
        raise ValueError(f"{label} must not be a symbolic link")
    if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
        raise ValueError(f"{label} must be a non-empty regular file")
    return path


def _executable_input(value: str | Path, label: str) -> Path:
    """Accept a virtual-environment launcher while validating its target."""

    path = Path(value).expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"{label} must be an executable regular file")
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable: {path}") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
        raise ValueError(f"{label} target must be a non-empty regular file")
    return path


def _validate_options(
    destination: Path,
    *,
    checkpoint: Path,
    start_seconds: float,
    end_seconds: float | None,
    overlap: float,
    timeout_seconds: float,
) -> None:
    if destination.exists() or os.path.lexists(destination):
        raise FileExistsError(
            "Private separation output already exists and will not be "
            f"overwritten: {destination}"
        )
    if checkpoint.suffix.lower() != ".th":
        raise ValueError("Demucs checkpoint must be a .th file")
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


def _read_excerpt(
    audio: Path,
    *,
    start_seconds: float,
    end_seconds: float | None,
    np: Any,
    soundfile: Any,
) -> tuple[Any, int, int, int, float, float, float]:
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
                "Private separation v1 requires an excerpt of at most "
                f"{MAXIMUM_EXCERPT_SECONDS:g} seconds"
            )
        if sample_rate != DEMUCS_SAMPLE_RATE:
            raise ValueError(
                f"Private separation v1 requires {DEMUCS_SAMPLE_RATE} Hz audio; "
                f"source is {sample_rate} Hz"
            )
        if channels not in (1, 2):
            raise ValueError("Private separation v1 supports mono or stereo audio")
        start_frame = int(round(start * sample_rate))
        end_frame = min(frames, int(round(end * sample_rate)))
        handle.seek(start_frame)
        source = handle.read(end_frame - start_frame, dtype="float32", always_2d=True)
    if not len(source):
        raise ValueError("The requested excerpt contains no audio frames")
    if not np.all(np.isfinite(source)):
        raise ValueError("Source audio contains non-finite samples")
    return (
        source,
        sample_rate,
        channels,
        frames,
        duration_seconds,
        start,
        end,
    )


def _validate_worker_result(
    result: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    array_dir: Path,
    expected_source_shape: tuple[int, ...],
    configuration: _PrivateDemucsConfiguration,
) -> None:
    if result.get("schema") != configuration.worker_result_schema:
        raise ValueError("worker returned an unsupported private result schema")
    if result.get("status") != "complete" or result.get("backend") != "demucs":
        raise ValueError("worker result is not a complete Demucs result")
    if result.get("package_version") != DEMUCS_PACKAGE_VERSION:
        raise ValueError("worker Demucs package version changed")
    if result.get("model_variant") != configuration.model_variant:
        raise ValueError("worker model variant changed")
    if result.get("model_signature") != configuration.model_signature:
        raise ValueError("worker model signature changed")
    if result.get("checkpoint_sha256") != request["model"]["checkpoint_sha256"]:
        raise ValueError("worker checkpoint hash does not match the request")
    if result.get("source_excerpt_sha256") != request["source_excerpt"]["sha256"]:
        raise ValueError("worker source hash does not match the request")
    if result.get("targets") != list(configuration.targets):
        raise ValueError("worker targets are not the exact configured role set")
    if result.get("model_applications") != 1:
        raise ValueError("worker did not report exactly one model application")
    if (
        result.get("device") != "cpu"
        or result.get("shifts") != 0
        or result.get("overlap") != request["inference"]["overlap"]
    ):
        raise ValueError("worker inference settings changed")
    inference_seconds = result.get("inference_seconds")
    maximum_resident = result.get("maximum_resident_set_size_native_units")
    if (
        type(inference_seconds) not in (int, float)
        or not math.isfinite(float(inference_seconds))
        or float(inference_seconds) < 0
        or type(maximum_resident) is not int
        or maximum_resident < 0
        or type(result.get("resource_platform")) is not str
        or not result["resource_platform"]
    ):
        raise ValueError("worker resource evidence is invalid")
    if (
        result.get("frames") != expected_source_shape[0]
        or result.get("channels") != expected_source_shape[1]
        or result.get("sample_rate") != DEMUCS_SAMPLE_RATE
    ):
        raise ValueError("worker result geometry does not match the source")
    arrays = result.get("arrays")
    if not isinstance(arrays, Mapping) or set(arrays) != set(configuration.targets):
        raise ValueError("worker array evidence is incomplete")
    entries = list(array_dir.iterdir())
    for path in entries:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise ValueError(
                "worker array directory must contain only regular non-link files"
            )
    actual_names = {path.name for path in entries}
    expected_array_names = frozenset(
        f"{role}.float32.npy" for role in configuration.targets
    )
    if actual_names != expected_array_names:
        raise ValueError("worker array directory is incomplete or contains extras")
    expected_payload_bytes = math.prod(expected_source_shape) * 4
    maximum_npy_bytes = expected_payload_bytes + 1024 * 1024
    for role in configuration.targets:
        evidence = arrays[role]
        path = array_dir / f"{role}.float32.npy"
        if not isinstance(evidence, Mapping):
            raise ValueError(f"worker {role} array evidence is invalid")
        if evidence.get("file") != path.name:
            raise ValueError(f"worker {role} array filename changed")
        if evidence.get("sha256") != _sha256(path):
            raise ValueError(f"worker {role} array hash is invalid")
        if evidence.get("bytes") != path.stat().st_size:
            raise ValueError(f"worker {role} array size is invalid")
        if not expected_payload_bytes <= path.stat().st_size <= maximum_npy_bytes:
            raise ValueError(f"worker {role} array size is outside safe bounds")
    effects = result.get("effects")
    if not isinstance(effects, Mapping) or effects != {
        "network_denial_enforced": False,
        "network_attempt_observation_available": False,
        "automatic_selection": False,
        "automatic_promotion": False,
        "public_result": False,
    }:
        raise ValueError("worker effect boundary changed")
    if result.get("checkpoint_hash_verified_before_deserialisation") is not True:
        raise ValueError("worker did not verify checkpoint before deserialisation")


def _remove_derived_audio(stem_dir: Path, reconstruction_dir: Path) -> None:
    """Remove parent-created loadable audio after failed validation."""

    for directory in (stem_dir, reconstruction_dir):
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink():
                path.unlink()


def _validate_estimate(
    estimate: Any,
    *,
    role: str,
    expected_shape: tuple[int, ...],
    np: Any,
) -> None:
    if not isinstance(estimate, np.ndarray):
        raise ValueError(f"{role} model array is not a NumPy array")
    if estimate.dtype != np.float32:
        raise ValueError(f"{role} model array must be float32")
    if estimate.shape != expected_shape:
        raise ValueError(
            f"{role} model array shape {estimate.shape} does not match {expected_shape}"
        )
    if not np.all(np.isfinite(estimate)):
        raise ValueError(f"{role} model array contains non-finite samples")


def _manifest_document(
    configuration: _PrivateDemucsConfiguration,
) -> dict[str, Any]:
    if configuration.manifest_registry == "cleanup":
        manifest = AI_CLEANUP_MODEL_MANIFESTS["demucs"]
    elif configuration.manifest_registry == "private_evaluation":
        manifest = AI_PRIVATE_EVALUATION_MODEL_MANIFESTS["demucs-6s"]
    else:  # pragma: no cover - closed construction above
        raise ValueError("unknown private Demucs manifest registry")
    return {
        "backend": manifest.backend,
        "name": manifest.name,
        "tasks": list(manifest.tasks),
        "code_license": manifest.code_license,
        "weights_license": manifest.weights_license,
        "package": manifest.package,
        "homepage": manifest.homepage,
        "distribution_policy": manifest.distribution_policy,
    }


def _existing_artifacts(
    directory: Path,
    *,
    reject_unsafe: bool = True,
) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode):
            if reject_unsafe:
                raise ValueError("private separation output contains a symbolic link")
            artifacts[relative] = {"unsafe_type": "symbolic_link"}
            continue
        if stat.S_ISDIR(details.st_mode):
            continue
        if not stat.S_ISREG(details.st_mode):
            if reject_unsafe:
                raise ValueError(
                    "private separation output contains a non-regular entry"
                )
            artifacts[relative] = {"unsafe_type": "non_regular"}
            continue
        if path.name == _REPORT_NAME:
            continue
        artifacts[relative] = {
            "bytes": details.st_size,
            "sha256": _sha256(path),
        }
    return artifacts


def _write_sealed_report(path: Path, document: Mapping[str, Any]) -> None:
    payload = dict(document)
    payload.pop("document_sha256", None)
    payload["document_sha256"] = _document_sha256(payload)
    _write_json(path, payload)


def _document_sha256(document: Mapping[str, Any]) -> str:
    canonical = dict(document)
    canonical.pop("document_sha256", None)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    _make_private_file(path)


def _make_private_file(path: Path) -> None:
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"private artifact must be a regular non-link file: {path}")
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_identity(
    path: Path,
    *,
    follow_symlinks: bool = False,
) -> dict[str, int]:
    details = path.stat() if follow_symlinks else path.lstat()
    return {
        "device": int(details.st_dev),
        "inode": int(details.st_ino),
        "mode": int(details.st_mode),
        "bytes": int(details.st_size),
        "modified_ns": int(details.st_mtime_ns),
    }


def _unchanged_regular_file(
    path: Path,
    *,
    expected_sha256: str,
    expected_identity: Mapping[str, int],
) -> bool:
    try:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            return False
        return (
            _file_identity(path) == expected_identity
            and _sha256(path) == expected_sha256
        )
    except OSError:
        return False


def _unchanged_runtime_launcher(
    path: Path,
    *,
    expected_resolved: Path,
    expected_sha256: str,
    expected_identity: Mapping[str, int],
) -> bool:
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
        if not stat.S_ISREG(details.st_mode):
            return False
        return (
            resolved == expected_resolved
            and _file_identity(path, follow_symlinks=True) == expected_identity
            and _sha256(resolved) == expected_sha256
        )
    except OSError:
        return False


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


__all__: tuple[str, ...] = ()
