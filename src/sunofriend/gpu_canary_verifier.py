"""Read-only, path-free verification for a returned C0 GPU canary."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from .audio_formats import file_sha256
from .gpu_canary import EXPERIMENT_ID, build_c0_canary_request
from .gpu_worker_contract import (
    validate_gpu_worker_request,
    validate_gpu_worker_result,
)
from .source_receipt import document_sha256


VERIFICATION_SCHEMA = "sunofriend.gpu-canary-round-trip-verification.v1"
RESULT_FILENAME = "gpu-worker-result.json"
OUTPUT_FILENAMES = {
    "metrics-json": "metrics.json",
    "checkpoint-step-100": "checkpoint-step-100.pt",
    "checkpoint-final-uninterrupted": "checkpoint-final-uninterrupted.pt",
    "checkpoint-final-resumed": "checkpoint-final-resumed.pt",
    "checkpoint-final-shuffled": "checkpoint-final-shuffled.pt",
}

_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|tmp|var|Volumes|mnt|etc)/)"
)


def verify_c0_canary_round_trip(
    request_path: str | Path,
    *,
    artifact_dir: str | Path,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify one completed C0 result without loading a checkpoint or writing files."""

    request = _read_json_document(Path(request_path), "GPU canary request")
    request = validate_gpu_worker_request(request)
    expected_request = build_c0_canary_request(str(request["repository_commit"]))
    if request != expected_request:
        raise ValueError("GPU request is not the exact supported C0 canary contract")
    if request.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("GPU request is not the C0 experiment")

    root = Path(artifact_dir).expanduser().absolute()
    result = _read_json_document(root / RESULT_FILENAME, "GPU worker result")
    result = validate_gpu_worker_result(result, request=request)
    if result.get("status") != "complete":
        raise ValueError("C0 round-trip verification requires a complete result")

    _reject_absolute_path_strings(request)
    _reject_absolute_path_strings(result)
    _verify_repository(
        Path(repository_root).expanduser().absolute()
        if repository_root is not None
        else Path(__file__).resolve().parents[2],
        expected_commit=str(request["repository_commit"]),
    )
    _verify_offline_and_resource_evidence(request=request, result=result)

    expected_by_id = {str(row["output_id"]): row for row in request["expected_outputs"]}
    returned_by_id = {str(row["output_id"]): row for row in result["outputs"]}
    if list(returned_by_id) != list(expected_by_id):
        raise ValueError("C0 result output roster or order changed")
    if set(OUTPUT_FILENAMES) != set(expected_by_id):
        raise ValueError("C0 verifier output filename roster is out of date")

    verified_outputs: list[dict[str, Any]] = []
    actual_output_bytes = 0
    for output_id, expected in expected_by_id.items():
        returned = returned_by_id[output_id]
        artifact = root / OUTPUT_FILENAMES[output_id]
        actual_bytes, actual_sha256 = _verify_local_artifact(
            artifact,
            expected_bytes=int(returned["bytes"]),
            expected_sha256=str(returned["sha256"]),
        )
        actual_output_bytes += actual_bytes
        verified_outputs.append(
            {
                "output_id": output_id,
                "kind": expected["kind"],
                "media_type": expected["media_type"],
                "shape": expected["shape"],
                "bytes": actual_bytes,
                "sha256": actual_sha256,
            }
        )

    if actual_output_bytes != int(result["resources"]["output_bytes"]):
        raise ValueError(
            "local artifact bytes do not match the result resource receipt"
        )

    metrics = _read_json_document(root / OUTPUT_FILENAMES["metrics-json"], "metrics")
    _verify_metrics(metrics, request=request, result=result)

    verification: dict[str, Any] = {
        "schema": VERIFICATION_SCHEMA,
        "status": "verified_technical_evidence_only",
        "repository_commit": request["repository_commit"],
        "experiment_id": request["experiment_id"],
        "request_document_sha256": request["document_sha256"],
        "result_document_sha256": result["document_sha256"],
        "outputs": verified_outputs,
        "checks": {
            "exact_c0_request": True,
            "result_binds_request": True,
            "repository_commit_and_tracked_files": True,
            "output_roster_kind_media_type_and_shape": True,
            "local_artifact_size_and_sha256": True,
            "resource_ceilings": True,
            "finite_training_evidence": True,
            "offline_zero_retry_evidence": True,
            "absolute_paths_absent": True,
        },
        "authority": {
            "technical_verification_only": True,
            "musical_selection": False,
            "representation_admitted": False,
            "checkpoint_promoted": False,
            "product_changed": False,
        },
    }
    _reject_absolute_path_strings(verification)
    verification["document_sha256"] = document_sha256(verification)
    return verification


def _read_json_document(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular local file")
    if path.stat().st_size > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"{label} exceeds the read-only verifier size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _verify_local_artifact(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("a declared C0 artifact is missing or is not a regular file")
    before = path.stat()
    if before.st_size != expected_bytes:
        raise ValueError("a local C0 artifact size does not match its result receipt")
    observed_sha256 = file_sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("a local C0 artifact changed while it was being verified")
    if observed_sha256 != expected_sha256:
        raise ValueError(
            "a local C0 artifact SHA-256 does not match its result receipt"
        )
    return before.st_size, observed_sha256


def _verify_repository(repository: Path, *, expected_commit: str) -> None:
    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )

    observed = git("rev-parse", "HEAD")
    if observed.returncode != 0 or observed.stdout.strip() != expected_commit:
        raise ValueError("repository HEAD does not match the C0 request commit")
    for arguments in (
        ("diff", "--quiet", "HEAD", "--"),
        ("diff", "--cached", "--quiet", "HEAD", "--"),
    ):
        if git(*arguments).returncode != 0:
            raise ValueError(
                "repository tracked files differ from the C0 request commit"
            )


def _verify_offline_and_resource_evidence(
    *, request: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    environment = result["environment"]
    if environment.get("network_used") is not False:
        raise ValueError("C0 result must report that network was not used")
    if environment.get("network_attempts") != 0:
        raise ValueError("C0 result must report zero network attempts")
    if environment.get("downloads_used") is not False:
        raise ValueError("C0 result must report that downloads were not used")
    if environment.get("deterministic_algorithms") is not True:
        raise ValueError("C0 result must report deterministic algorithms")
    if environment.get("cublas_workspace_config") != request["execution_policy"].get(
        "cublas_workspace_config"
    ):
        raise ValueError("C0 result deterministic CuBLAS configuration changed")
    execution = result["training_evidence"]["execution"]
    if execution.get("network_attempts") != 0 or execution.get("retries") != 0:
        raise ValueError("C0 training evidence must be offline with zero retries")
    for section, keys in (
        (result["timings"], ("wall_seconds",)),
        (
            result["resources"],
            ("peak_gpu_bytes", "peak_ram_bytes", "output_bytes"),
        ),
    ):
        for key in keys:
            _require_finite_number(section.get(key), key)


def _verify_metrics(
    metrics: Mapping[str, Any], *, request: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    if metrics.get("schema") != "sunofriend.gpu-canary-metrics.v1":
        raise ValueError("C0 metrics schema changed")
    unsigned = dict(metrics)
    observed_document_sha256 = unsigned.pop("document_sha256", None)
    if observed_document_sha256 != document_sha256(unsigned):
        raise ValueError("C0 metrics document SHA-256 does not match")
    expected_identity = {
        "experiment_id": request["experiment_id"],
        "request_document_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "dataset_sha256": request["dataset"]["sha256"],
    }
    for key, expected in expected_identity.items():
        if metrics.get(key) != expected:
            raise ValueError(f"C0 metrics {key} does not bind the request")
    if metrics.get("authority") != "technical_research_challenger_only":
        raise ValueError("C0 metrics may grant only technical challenger authority")
    if metrics.get("network_attempts") != 0 or metrics.get("retries") != 0:
        raise ValueError("C0 metrics must report offline execution with zero retries")

    evidence = result["training_evidence"]
    arms = evidence["arms"]
    numeric_cross_checks = {
        "clean_heldout_accuracy": arms[0]["heldout_accuracy"],
        "shuffled_heldout_accuracy": arms[2]["heldout_accuracy"],
        "clean_minus_shuffled_accuracy": (
            float(arms[0]["heldout_accuracy"]) - float(arms[2]["heldout_accuracy"])
        ),
        "resume_max_abs_parameter_difference": evidence["resume_equivalence"][
            "maximum_parameter_difference"
        ],
        "resume_max_abs_optimiser_difference": evidence["resume_equivalence"][
            "maximum_optimiser_difference"
        ],
    }
    for key, expected in numeric_cross_checks.items():
        observed = _require_finite_number(metrics.get(key), key)
        if observed != float(expected):
            raise ValueError(f"C0 metrics {key} does not match training evidence")
    if metrics.get("pipeline_acceptance") != evidence["acceptance"]:
        raise ValueError("C0 metrics acceptance does not match training evidence")
    curves = metrics.get("curves")
    if not isinstance(curves, Mapping) or set(curves) != {
        "clean_uninterrupted",
        "clean_resumed",
        "shuffled_control",
    }:
        raise ValueError("C0 metrics curve roster changed")
    for curve in curves.values():
        if not isinstance(curve, list) or not curve:
            raise ValueError("C0 metrics curves must be non-empty lists")
        for point in curve:
            if not isinstance(point, Mapping):
                raise ValueError("C0 metrics curve points must be objects")
            _require_finite_number(point.get("step"), "curve step")
            _require_finite_number(point.get("loss"), "curve loss")
    _reject_absolute_path_strings(metrics)


def _require_finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _reject_absolute_path_strings(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_absolute_path_strings(item)
    elif isinstance(value, list):
        for item in value:
            _reject_absolute_path_strings(item)
    elif isinstance(value, str) and _ABSOLUTE_PATH.search(value):
        raise ValueError("C0 portable documents may not expose absolute paths")


__all__ = [
    "OUTPUT_FILENAMES",
    "RESULT_FILENAME",
    "VERIFICATION_SCHEMA",
    "verify_c0_canary_round_trip",
]
