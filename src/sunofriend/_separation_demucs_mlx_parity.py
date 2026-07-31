"""Private same-checkpoint parity harness for Demucs PyTorch and MLX.

The harness consumes complete, sealed six-source PyTorch experiment records.
It asks a separate worker to convert the same already-installed checkpoint in
memory, compares unchanged float32 model arrays and preserves listening WAVs.
It never installs software, resolves a named model, selects a separator or
creates a public Sunofriend source-graph result.
"""

from __future__ import annotations

import json
import math
import os
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_demucs_private_run import (
    PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA,
    _document_sha256,
    _executable_input,
    _file_identity,
    _make_private_file,
    _regular_input,
    _sha256,
    _unchanged_regular_file,
    _utc_now,
    _write_json,
    _write_sealed_report,
)
from .ai_mlx_separation_worker import (
    CHECKPOINT_SHA256,
    EXACT_PACKAGES,
    MODEL_SIGNATURE,
    MODEL_SOURCE_ORDER,
    MODEL_VARIANT,
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    TARGETS,
)
from .ai_runtime import resolve_ai_python, resolve_demucs_6s_model
from .separation_quality import inspect_pcm_wav


EXPERIMENT_SCHEMA = "sunofriend.private-demucs-mlx-parity-experiment.v1"
POLICY_ID = "private-demucs-mlx-same-checkpoint-parity-v1"
RUNTIME_REPOSITORY = "https://github.com/ssmall256/demucs-mlx"
RUNTIME_TAG = "v1.4.4"
RUNTIME_TAG_REVISION = "36b43ce2fc908129fb9166d4c109f7ccb77d12bf"
RUNTIME_MAIN_REVISION_OBSERVED = "b37e6ba3c5985af531f61c43564cf13c6ed349fd"
_REPORT_NAME = "private-demucs-mlx-parity.json"
_OFFLINE_ENVIRONMENT_HINTS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "PYTHONNOUSERSITE": "1",
}
_INSTALL_ARTIFACTS = (
    {
        "package": "demucs-mlx",
        "version": "1.4.4",
        "artifact": "demucs_mlx-1.4.4-py3-none-any.whl",
        "sha256": "dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64",
        "license": "MIT",
    },
    {
        "package": "mlx",
        "version": "0.31.2",
        "artifact": "mlx-0.31.2-cp312-cp312-macosx_26_0_arm64.whl",
        "sha256": "51ca102db641b01e7cb083ce8ecb580e281530a141a7ca12544bb370641630ae",
        "license": "MIT",
    },
    {
        "package": "mlx-metal",
        "version": "0.31.2",
        "artifact": "mlx_metal-0.31.2-py3-none-macosx_26_0_arm64.whl",
        "sha256": "84ffb60ee503f03eb684f5fb168d5cff31e2a16b7f27c1731eaf7662bd6e9b46",
        "license": "MIT",
    },
    {
        "package": "mlx-audio-io",
        "version": "1.3.11",
        "artifact": "mlx_audio_io-1.3.11.tar.gz",
        "sha256": "5e9f4e6bbca373cac5a51b9d6b19224cf2ea20f01ef751e34a4a986a01da327d",
        "license": "MIT",
    },
    {
        "package": "mlx-spectro",
        "version": "0.7.0",
        "artifact": "mlx_spectro-0.7.0-py3-none-any.whl",
        "sha256": "ef7879bf45f0b62455db4083bef74a19c62731b02ffc5abff43e6cc2cc39d884",
        "license": "MIT",
    },
)


class _PrivateDemucsMlxParityError(RuntimeError):
    def __init__(self, message: str, run_dir: Path):
        super().__init__(f"{message}; private parity record: {run_dir}")
        self.run_dir = run_dir


def _build_private_demucs_mlx_parity_plan(
    *,
    checkpoint_path: str | Path | None = None,
    python: str | Path | None = None,
) -> dict[str, Any]:
    """Return a read-only, exact install/run plan; never import MLX."""

    checkpoint = _regular_input(
        resolve_demucs_6s_model(checkpoint_path), "Demucs checkpoint"
    )
    checkpoint_hash = _sha256(checkpoint)
    if checkpoint_hash != CHECKPOINT_SHA256:
        raise ValueError("Demucs six-source checkpoint does not match the pinned hash")
    executable = _executable_input(resolve_ai_python(python), "AI interpreter")
    probe = _probe_runtime(executable)
    packages = probe.get("packages", {})
    exact = {
        name: packages.get(name) == version
        for name, version in EXACT_PACKAGES.items()
    }
    installation_required = not all(exact.values())
    return {
        "schema": "sunofriend.private-demucs-mlx-parity-plan.v1",
        "status": "ready" if not installation_required else "approval_required",
        "policy_id": POLICY_ID,
        "read_only": True,
        "checkpoint": {
            "path": str(checkpoint),
            "bytes": checkpoint.stat().st_size,
            "sha256": checkpoint_hash,
            "expected_sha256": CHECKPOINT_SHA256,
            "exact": True,
            "download_required": False,
            "redistribution_allowed_by_sunofriend": False,
        },
        "runtime": {
            "python": str(executable),
            "probe": probe,
            "required_packages": dict(EXACT_PACKAGES),
            "exact_package_matches": exact,
            "installation_required": installation_required,
            "requirements": "requirements-private-separation-mlx-macos.txt",
            "install_command_after_separate_approval": (
                "uv pip install --python .venv-ai/bin/python --strict "
                "--requirements requirements-private-separation-mlx-macos.txt"
            ),
            "environment_changed_by_install": str(executable.parent.parent),
            "system_packages_changed": [],
            "resolved_new_packages": [
                "demucs-mlx==1.4.4",
                "mlx==0.31.2",
                "mlx-audio-io==1.3.11",
                "mlx-metal==0.31.2",
                "mlx-spectro==0.7.0",
            ],
            "network_destinations": [
                "pypi.org",
                "files.pythonhosted.org",
                "a PyPI mirror or CDN selected by uv/PyPI may vary",
            ],
            "artifacts_observed_for_this_mac": list(_INSTALL_ARTIFACTS),
            "code_licenses": {
                "demucs-mlx": "MIT",
                "mlx": "MIT",
                "mlx-metal": "MIT",
                "mlx-audio-io": "MIT",
                "mlx-spectro": "MIT",
            },
            "repository": RUNTIME_REPOSITORY,
            "tag": RUNTIME_TAG,
            "tag_revision": RUNTIME_TAG_REVISION,
            "main_revision_observed_during_audit": RUNTIME_MAIN_REVISION_OBSERVED,
        },
        "execution": {
            "input_scope": "1-8 sealed private six-source experiment excerpts",
            "model_conversion": "verified local checkpoint, in memory only",
            "named_model_resolution": False,
            "model_cache_read_or_write": False,
            "model_network_access_expected": False,
            "output_scope": "fresh private parity directory only",
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "simple_or_studio_availability": False,
            "public_result": False,
        },
        "limitations": [
            "Package installation needs separate approval before mutation.",
            "The official repository does not state separate pretrained-checkpoint terms; the already accepted checkpoint remains private-evaluation-only.",
            "The runtime's published speed result was measured on one M4 Max and is not a promise for this Mac.",
            "Same-checkpoint numerical parity measures a runtime port; it cannot improve separation quality.",
            "Offline environment hints do not prove kernel-level network denial or outside-write confinement.",
        ],
    }


def _run_private_demucs_mlx_parity(
    reference_runs: Sequence[str | Path],
    *,
    out_dir: str | Path,
    checkpoint_path: str | Path | None = None,
    python: str | Path | None = None,
    worker_path: str | Path | None = None,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Run one in-memory conversion and compare it with sealed PyTorch runs."""

    import numpy as np
    import soundfile

    if not 1 <= len(reference_runs) <= 8:
        raise ValueError("MLX parity requires 1-8 reference runs")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    plan = _build_private_demucs_mlx_parity_plan(
        checkpoint_path=checkpoint_path, python=python
    )
    if plan["runtime"]["installation_required"]:
        missing = {
            name: details
            for name, details in plan["runtime"]["exact_package_matches"].items()
            if not details
        }
        raise RuntimeError(
            "MLX parity runtime is not installed exactly; run the read-only plan "
            f"and obtain separate install approval first: {missing}"
        )

    checkpoint = _regular_input(
        resolve_demucs_6s_model(checkpoint_path), "Demucs checkpoint"
    )
    checkpoint_identity = _file_identity(checkpoint)
    executable = _executable_input(resolve_ai_python(python), "AI interpreter")
    worker = _regular_input(
        (
            Path(worker_path).expanduser().absolute()
            if worker_path is not None
            else Path(__file__).with_name("ai_mlx_separation_worker.py")
        ),
        "MLX parity worker",
    )
    worker_hash = _sha256(worker)
    worker_identity = _file_identity(worker)
    references = [
        _load_reference_run(Path(value).expanduser().absolute(), index=index)
        for index, value in enumerate(reference_runs, start=1)
    ]
    overlaps = {float(item["report"]["inference"]["overlap"]) for item in references}
    if len(overlaps) != 1:
        raise ValueError("reference runs use different inference overlap values")
    overlap = overlaps.pop()

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists() or os.path.lexists(destination):
        raise FileExistsError(f"private parity output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    arrays_root = destination / "MODEL-ARRAYS"
    stems_root = destination / "ESTIMATED-STEMS"
    worker_home = destination / "WORKER-HOME"
    for directory in (arrays_root, stems_root, worker_home):
        directory.mkdir(mode=0o700)

    cases = []
    for item in references:
        source = item["source"]
        geometry = item["source_geometry"]
        cases.append(
            {
                "case_id": item["case_id"],
                "source_path": str(source),
                "source_sha256": item["source_sha256"],
                "sample_rate": geometry["sample_rate"],
                "channels": geometry["channels"],
                "frames": geometry["frames"],
            }
        )
    request = {
        "schema": REQUEST_SCHEMA,
        "policy_id": POLICY_ID,
        "evidence_scope": "private_development_only",
        "backend": "demucs-mlx",
        "model": {
            "variant": MODEL_VARIANT,
            "signature": MODEL_SIGNATURE,
            "checkpoint_path": str(checkpoint),
            "checkpoint_sha256": CHECKPOINT_SHA256,
        },
        "runtime": {
            "packages": dict(EXACT_PACKAGES),
            "repository": RUNTIME_REPOSITORY,
            "tag": RUNTIME_TAG,
            "tag_revision": RUNTIME_TAG_REVISION,
            "conversion": "verified-local-checkpoint-in-memory-only",
        },
        "inference": {
            "device": "mlx-gpu",
            "shifts": 0,
            "overlap": overlap,
            "split": True,
            "num_workers": 0,
            "batch_size": 1,
        },
        "cases": cases,
        "permissions": {
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
        },
    }
    request_path = destination / "request.json"
    result_path = destination / "worker-result.json"
    stdout_path = destination / "worker.stdout.log"
    stderr_path = destination / "worker.stderr.log"
    report_path = destination / _REPORT_NAME
    _write_json(request_path, request)
    command = [
        str(executable),
        str(worker),
        "--request",
        str(request_path),
        "--arrays-root",
        str(arrays_root),
        "--result",
        str(result_path),
    ]
    environment = os.environ.copy()
    environment.update(_OFFLINE_ENVIRONMENT_HINTS)
    environment.update(
        {
            "HOME": str(worker_home),
            "XDG_CACHE_HOME": str(worker_home / ".cache"),
            "TORCH_HOME": str(worker_home / ".cache" / "torch"),
        }
    )
    started_at = _utc_now()
    started = time.monotonic()
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
        elif not result_path.is_file():
            error = "worker completed without result JSON"
        else:
            _make_private_file(result_path)
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

    base_report = {
        "schema": EXPERIMENT_SCHEMA,
        "policy_id": POLICY_ID,
        "status": "failed" if error else "validating",
        "evidence_scope": "private_development_only",
        "started_at": started_at,
        "completed_at": _utc_now(),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "command": command,
        "exit_code": exit_code,
        "error": error,
        "plan": plan,
        "checkpoint": {
            "path": str(checkpoint),
            "sha256": CHECKPOINT_SHA256,
            "identity": checkpoint_identity,
        },
        "worker": {
            "path": str(worker),
            "sha256": worker_hash,
            "identity": worker_identity,
        },
        "reference_runs": [item["evidence"] for item in references],
        "permissions": _permissions(),
        "limitations": _limitations(),
    }
    if error:
        _write_sealed_report(report_path, base_report)
        raise _PrivateDemucsMlxParityError(error, destination)

    try:
        worker_result = json.loads(result_path.read_text(encoding="utf-8"))
        _validate_worker_result(
            worker_result, request=request, arrays_root=arrays_root, references=references
        )
        cases_report: dict[str, Any] = {}
        global_relative_maximum = 0.0
        all_within_reference = True
        speed_factors: list[float] = []
        for item in references:
            case_id = item["case_id"]
            case_worker = worker_result["cases"][case_id]
            case_stems = stems_root / case_id
            case_stems.mkdir(mode=0o700)
            role_metrics: dict[str, Any] = {}
            for role in TARGETS:
                reference_array = np.load(
                    item["arrays"][role], allow_pickle=False
                )
                mlx_path = arrays_root / case_id / f"{role}.float32.npy"
                mlx_array = np.load(mlx_path, allow_pickle=False)
                metrics = _comparison_metrics(reference_array, mlx_array, np=np)
                role_metrics[role] = metrics
                global_relative_maximum = max(
                    global_relative_maximum, metrics["maximum_relative_error"]
                )
                all_within_reference = (
                    all_within_reference
                    and metrics["within_direct_model_reference_tolerance"]
                )
                stem_path = case_stems / f"{role}.wav"
                soundfile.write(stem_path, mlx_array, 44_100, subtype="PCM_24")
                _make_private_file(stem_path)
                inspection = inspect_pcm_wav(stem_path)
                metrics["mlx_listening_wav"] = {
                    "path": str(stem_path.relative_to(destination)),
                    "sha256": inspection.sha256,
                    "geometry": inspection.geometry.to_dict(),
                    "peak": inspection.peak,
                    "rms": inspection.rms,
                }
            pytorch_seconds = float(
                item["report"]["worker_result"]["inference_seconds"]
            )
            mlx_seconds = float(case_worker["inference_seconds"])
            speed_factor = (
                pytorch_seconds / mlx_seconds if mlx_seconds > 0 else None
            )
            if speed_factor is not None:
                speed_factors.append(speed_factor)
            cases_report[case_id] = {
                "reference_run": str(item["root"]),
                "source_sha256": item["source_sha256"],
                "same_source_proven": True,
                "same_checkpoint_proven": True,
                "role_metrics": role_metrics,
                "runtime": {
                    "pytorch_cpu_inference_seconds": pytorch_seconds,
                    "mlx_gpu_inference_seconds": mlx_seconds,
                    "observed_speed_factor": (
                        round(speed_factor, 6) if speed_factor is not None else None
                    ),
                    "mlx_run_position": case_worker["run_position"],
                },
            }

        checkpoint_unchanged = _unchanged_regular_file(
            checkpoint,
            expected_sha256=CHECKPOINT_SHA256,
            expected_identity=checkpoint_identity,
        )
        worker_unchanged = _unchanged_regular_file(
            worker,
            expected_sha256=worker_hash,
            expected_identity=worker_identity,
        )
        references_unchanged = all(_reference_unchanged(item) for item in references)
        if not checkpoint_unchanged or not worker_unchanged or not references_unchanged:
            raise ValueError("a parity input changed during execution")
        report = {
            **base_report,
            "status": "complete_review_required",
            "completed_at": _utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "worker_result": worker_result,
            "cases": cases_report,
            "summary": {
                "same_checkpoint_proven": True,
                "same_sources_proven": True,
                "maximum_relative_error_across_roles": round(
                    global_relative_maximum, 12
                ),
                "all_roles_within_direct_model_reference_tolerance": (
                    all_within_reference
                ),
                "direct_model_reference_tolerance": 1e-4,
                "tolerance_scope": (
                    "The demucs-mlx converter's direct random-input verifier uses "
                    "relative maximum error 1e-4. Applying it here is descriptive, "
                    "not an automatic acceptance gate for split full-pipeline output."
                ),
                "observed_speed_factor_range": (
                    [round(min(speed_factors), 6), round(max(speed_factors), 6)]
                    if speed_factors
                    else None
                ),
                "runtime_parity_only": True,
                "separator_quality_improvement_claimed": False,
                "accepted": False,
            },
            "immutability": {
                "checkpoint_unchanged": checkpoint_unchanged,
                "worker_unchanged": worker_unchanged,
                "reference_inputs_unchanged": references_unchanged,
            },
            "artifacts": _artifacts(destination),
        }
        _write_sealed_report(report_path, report)
        sealed = json.loads(report_path.read_text(encoding="utf-8"))
        sealed["report"] = str(report_path)
        return sealed
    except Exception as exc:
        base_report.update(
            {
                "status": "failed",
                "completed_at": _utc_now(),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        _write_sealed_report(report_path, base_report)
        raise _PrivateDemucsMlxParityError(str(base_report["error"]), destination) from exc


def _load_reference_run(root: Path, *, index: int) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"reference run must be a non-link directory: {root}")
    report_path = _regular_input(root / "private-separation-experiment.json", "report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("document_sha256") != _document_sha256(report):
        raise ValueError(f"reference report seal is invalid: {root}")
    if report.get("schema") != PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA:
        raise ValueError(f"reference is not a six-source experiment: {root}")
    if report.get("status") != "complete_review_required":
        raise ValueError(f"reference six-source experiment is incomplete: {root}")
    backend = report.get("backend", {})
    if (
        backend.get("model_variant") != MODEL_VARIANT
        or backend.get("model_signature") != MODEL_SIGNATURE
        or backend.get("checkpoint_sha256") != CHECKPOINT_SHA256
    ):
        raise ValueError(f"reference model identity changed: {root}")
    inference = report.get("inference", {})
    if (
        inference.get("device") != "cpu"
        or inference.get("shifts") != 0
        or inference.get("split") is not True
        or inference.get("num_workers") != 0
    ):
        raise ValueError(f"reference inference settings are not comparable: {root}")
    persisted = report["excerpt"]["persisted_source"]
    source = _regular_input(root / persisted["path"], "reference source excerpt")
    if _sha256(source) != persisted["sha256"]:
        raise ValueError(f"reference source excerpt hash changed: {root}")
    source_identity = _file_identity(source)
    arrays: dict[str, Path] = {}
    array_identities: dict[str, Any] = {}
    for role in TARGETS:
        evidence = report["estimated_stems"][role]
        path = _regular_input(
            root / "MODEL-ARRAYS" / f"{role}.float32.npy",
            f"reference {role} array",
        )
        if _sha256(path) != evidence["model_array_sha256"]:
            raise ValueError(f"reference {role} array hash changed: {root}")
        arrays[role] = path
        array_identities[role] = _file_identity(path)
    source_geometry = {
        "sample_rate": int(report["estimated_stems"][TARGETS[0]]["geometry"]["sample_rate"]),
        "channels": int(report["estimated_stems"][TARGETS[0]]["geometry"]["channels"]),
        "frames": int(report["estimated_stems"][TARGETS[0]]["geometry"]["frames"]),
    }
    return {
        "case_id": f"case-{index:02d}",
        "root": root,
        "report_path": report_path,
        "report": report,
        "report_identity": _file_identity(report_path),
        "report_sha256": _sha256(report_path),
        "source": source,
        "source_sha256": persisted["sha256"],
        "source_identity": source_identity,
        "source_geometry": source_geometry,
        "arrays": arrays,
        "array_identities": array_identities,
        "evidence": {
            "case_id": f"case-{index:02d}",
            "root": str(root),
            "report": str(report_path),
            "report_sha256": _sha256(report_path),
            "document_sha256": report["document_sha256"],
            "source_sha256": persisted["sha256"],
            "checkpoint_sha256": CHECKPOINT_SHA256,
        },
    }


def _validate_worker_result(
    result: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    arrays_root: Path,
    references: Sequence[Mapping[str, Any]],
) -> None:
    if result.get("schema") != RESULT_SCHEMA or result.get("status") != "complete":
        raise ValueError("MLX parity worker result schema/status changed")
    if result.get("backend") != "demucs-mlx":
        raise ValueError("MLX parity worker backend changed")
    if (
        result.get("model_variant") != MODEL_VARIANT
        or result.get("model_signature") != MODEL_SIGNATURE
        or result.get("checkpoint_sha256") != CHECKPOINT_SHA256
    ):
        raise ValueError("MLX parity worker model identity changed")
    if result.get("packages") != EXACT_PACKAGES:
        raise ValueError("MLX parity worker package versions changed")
    if result.get("targets") != list(TARGETS):
        raise ValueError("MLX parity worker target order changed")
    if result.get("model_source_order") != list(MODEL_SOURCE_ORDER):
        raise ValueError("MLX parity model source order changed")
    if result.get("inference") != request["inference"]:
        raise ValueError("MLX parity worker inference settings changed")
    conversion = result.get("conversion")
    if conversion != {
        "source": "caller-supplied hash-pinned PyTorch checkpoint",
        "named_model_resolution_called": False,
        "model_cache_api_called": False,
        "converted_weight_cache_written": False,
    }:
        raise ValueError("MLX parity direct-conversion evidence changed")
    if result.get("checkpoint_hash_verified_before_deserialisation") is not True:
        raise ValueError("MLX parity checkpoint was not verified before loading")
    if result.get("checkpoint_unchanged_after_inference") is not True:
        raise ValueError("MLX parity checkpoint changed during inference")
    effects = result.get("effects")
    if effects != {
        "network_denial_enforced": False,
        "network_attempt_observation_available": False,
        "automatic_selection": False,
        "automatic_promotion": False,
        "public_result": False,
    }:
        raise ValueError("MLX parity worker effect boundary changed")
    cases = result.get("cases")
    expected_ids = {item["case_id"] for item in references}
    if not isinstance(cases, Mapping) or set(cases) != expected_ids:
        raise ValueError("MLX parity worker cases are incomplete")
    if {path.name for path in arrays_root.iterdir()} != expected_ids:
        raise ValueError("MLX parity arrays root is incomplete or contains extras")
    for item in references:
        case_id = item["case_id"]
        case = cases[case_id]
        if case.get("source_sha256") != item["source_sha256"]:
            raise ValueError(f"{case_id} MLX source hash changed")
        geometry = item["source_geometry"]
        if any(case.get(name) != geometry[name] for name in geometry):
            raise ValueError(f"{case_id} MLX source geometry changed")
        if case.get("source_unchanged_after_inference") is not True:
            raise ValueError(f"{case_id} source changed during MLX inference")
        if type(case.get("run_position")) is not int:
            raise ValueError(f"{case_id} MLX run position is invalid")
        seconds = case.get("inference_seconds")
        if type(seconds) not in (int, float) or not math.isfinite(float(seconds)):
            raise ValueError(f"{case_id} MLX inference timing is invalid")
        case_dir = arrays_root / case_id
        if not case_dir.is_dir() or case_dir.is_symlink():
            raise ValueError(f"{case_id} MLX array directory is invalid")
        if {path.name for path in case_dir.iterdir()} != {
            f"{role}.float32.npy" for role in TARGETS
        }:
            raise ValueError(f"{case_id} MLX arrays are incomplete or contain extras")
        arrays = case.get("arrays")
        if not isinstance(arrays, Mapping) or set(arrays) != set(TARGETS):
            raise ValueError(f"{case_id} MLX array evidence is incomplete")
        for role in TARGETS:
            path = _regular_input(case_dir / f"{role}.float32.npy", "MLX array")
            evidence = arrays[role]
            if (
                evidence.get("file") != path.name
                or evidence.get("sha256") != _sha256(path)
                or evidence.get("bytes") != path.stat().st_size
            ):
                raise ValueError(f"{case_id} {role} MLX array evidence is invalid")


def _comparison_metrics(reference: Any, candidate: Any, *, np: Any) -> dict[str, Any]:
    if (
        not isinstance(reference, np.ndarray)
        or not isinstance(candidate, np.ndarray)
        or reference.dtype != np.float32
        or candidate.dtype != np.float32
        or reference.shape != candidate.shape
        or not np.all(np.isfinite(reference))
        or not np.all(np.isfinite(candidate))
    ):
        raise ValueError("parity arrays must be finite, shape-matched float32")
    ref = reference.astype("float64")
    cand = candidate.astype("float64")
    difference = cand - ref
    maximum = float(np.max(np.abs(difference)))
    reference_peak = float(np.max(np.abs(ref)))
    relative = maximum / max(reference_peak, 1e-12)
    difference_energy = float(np.sum(np.square(difference)))
    reference_energy = float(np.sum(np.square(ref)))
    snr = (
        10.0 * math.log10(reference_energy / difference_energy)
        if reference_energy > 0 and difference_energy > 0
        else None
    )
    ref_flat = ref.reshape(-1)
    cand_flat = cand.reshape(-1)
    if float(np.std(ref_flat)) > 0 and float(np.std(cand_flat)) > 0:
        correlation = float(np.corrcoef(ref_flat, cand_flat)[0, 1])
    else:
        correlation = None
    reference_rms = float(np.sqrt(np.mean(np.square(ref))))
    candidate_rms = float(np.sqrt(np.mean(np.square(cand))))
    level_delta = (
        20.0 * math.log10(candidate_rms / reference_rms)
        if reference_rms > 0 and candidate_rms > 0
        else None
    )
    return {
        "frames": int(reference.shape[0]),
        "channels": int(reference.shape[1]),
        "maximum_absolute_error": round(maximum, 12),
        "mean_absolute_error": round(float(np.mean(np.abs(difference))), 12),
        "rms_error": round(float(np.sqrt(np.mean(np.square(difference)))), 12),
        "reference_peak": round(reference_peak, 12),
        "maximum_relative_error": round(relative, 12),
        "within_direct_model_reference_tolerance": relative <= 1e-4,
        "signal_to_error_db": round(snr, 9) if snr is not None else None,
        "zero_difference": difference_energy == 0,
        "correlation": round(correlation, 12) if correlation is not None else None,
        "reference_rms": round(reference_rms, 12),
        "mlx_rms": round(candidate_rms, 12),
        "level_delta_db": round(level_delta, 9) if level_delta is not None else None,
        "exact_float32_sample_fraction": round(
            float(np.count_nonzero(reference == candidate)) / reference.size, 12
        ),
    }


def _probe_runtime(executable: Path) -> dict[str, Any]:
    script = """
import importlib.metadata as metadata
import json
import platform
names = %s
packages = {}
for name in names:
    try:
        packages[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        packages[name] = None
print(json.dumps({
    "python": platform.python_version(),
    "system": platform.system(),
    "machine": platform.machine(),
    "packages": packages,
}, sort_keys=True))
""" % repr(tuple(EXACT_PACKAGES))
    completed = subprocess.run(
        [str(executable), "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    if completed.returncode != 0:
        return {
            "probe_ready": False,
            "error": completed.stderr.strip() or f"exit {completed.returncode}",
            "packages": {},
        }
    result = json.loads(completed.stdout)
    result["probe_ready"] = True
    result["apple_silicon_ready"] = (
        result.get("system") == "Darwin" and result.get("machine") == "arm64"
    )
    return result


def _reference_unchanged(item: Mapping[str, Any]) -> bool:
    if not _unchanged_regular_file(
        item["report_path"],
        expected_sha256=item["report_sha256"],
        expected_identity=item["report_identity"],
    ):
        return False
    if not _unchanged_regular_file(
        item["source"],
        expected_sha256=item["source_sha256"],
        expected_identity=item["source_identity"],
    ):
        return False
    for role in TARGETS:
        path = item["arrays"][role]
        expected_hash = item["report"]["estimated_stems"][role][
            "model_array_sha256"
        ]
        if not _unchanged_regular_file(
            path,
            expected_sha256=expected_hash,
            expected_identity=item["array_identities"][role],
        ):
            return False
    return True


def _permissions() -> dict[str, bool]:
    return {
        "accepted": False,
        "production_eligible": False,
        "automatic_selection": False,
        "automatic_promotion": False,
        "source_graph_activation": False,
        "public_result": False,
        "simple_mode_available": False,
        "studio_import_available": False,
    }


def _limitations() -> list[str]:
    return [
        "This measures a runtime port of the same checkpoint, not a new separation model.",
        "Numerical agreement does not establish that any separated role is musically accurate.",
        "The six-source piano/guitar quality warning and private checkpoint terms remain unchanged.",
        "The first MLX case includes process-local first-use costs; later cases may reuse compiled work.",
        "Offline environment hints do not prove network denial, outside-write confinement or complete descendant supervision.",
        "No separator, MIDI candidate, source-graph node, Simple result or Studio result is activated.",
    ]


def _artifacts(root: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode):
            raise ValueError("private parity output contains a symbolic link")
        if stat.S_ISDIR(details.st_mode):
            continue
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("private parity output contains a non-regular entry")
        if path.name == _REPORT_NAME:
            continue
        artifacts[path.relative_to(root).as_posix()] = {
            "bytes": details.st_size,
            "sha256": _sha256(path),
        }
    return artifacts


def _subprocess_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


__all__: tuple[str, ...] = ()
