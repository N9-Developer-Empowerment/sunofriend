"""Read-only round-trip verification for the synthetic vocal pairwise canary."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from .audio_formats import file_sha256
from .gpu_worker_contract import validate_gpu_worker_request
from .source_receipt import document_sha256
from .vocal_pairwise_canary import build_synthetic_pairwise_fixture
from .vocal_pairwise_gpu_canary import (
    GPU_EXPERIMENT_ID,
    build_pairwise_gpu_canary_request,
    validate_pairwise_gpu_result,
)


VERIFICATION_SCHEMA = "sunofriend.vocal-pairwise-gpu-verification.v1"
RESULT_FILENAME = "gpu-worker-result.json"
OUTPUT_FILENAMES = {
    "metrics-json": "metrics.json",
    "checkpoint-step-120": "checkpoint-step-120.pt",
    "checkpoint-final-uninterrupted": "checkpoint-final-uninterrupted.pt",
    "checkpoint-final-resumed": "checkpoint-final-resumed.pt",
    "checkpoint-final-shuffled": "checkpoint-final-shuffled.pt",
}
CHECKPOINT_STEPS = {
    "checkpoint-step-120": 120,
    "checkpoint-final-uninterrupted": 300,
    "checkpoint-final-resumed": 300,
    "checkpoint-final-shuffled": 300,
}

_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|tmp|var|Volumes|mnt|etc)/)"
)


def verify_pairwise_gpu_canary_round_trip(
    request_path: str | Path,
    *,
    artifact_dir: str | Path,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify one returned synthetic CUDA canary without training or writing."""

    request = validate_gpu_worker_request(
        _read_json_document(Path(request_path), "vocal pairwise GPU request")
    )
    expected_request = build_pairwise_gpu_canary_request(
        str(request["repository_commit"])
    )
    if request != expected_request or request.get("experiment_id") != GPU_EXPERIMENT_ID:
        raise ValueError("vocal pairwise request is not the exact supported contract")

    root = Path(artifact_dir).expanduser().absolute()
    _verify_exact_local_roster(root)
    result = validate_pairwise_gpu_result(
        _read_json_document(root / RESULT_FILENAME, "vocal pairwise GPU result"),
        request=request,
    )
    if result.get("status") != "complete":
        raise ValueError(
            "vocal pairwise round-trip verification requires a complete result"
        )

    _reject_absolute_path_strings(request)
    _reject_absolute_path_strings(result)
    _verify_repository(
        Path(repository_root).expanduser().absolute()
        if repository_root is not None
        else Path(__file__).resolve().parents[2],
        expected_commit=str(request["repository_commit"]),
    )
    _verify_offline_evidence(request=request, result=result)

    expected_by_id = {str(row["output_id"]): row for row in request["expected_outputs"]}
    returned_by_id = {str(row["output_id"]): row for row in result["outputs"]}
    if list(returned_by_id) != list(expected_by_id):
        raise ValueError("vocal pairwise output roster or order changed")
    if set(expected_by_id) != set(OUTPUT_FILENAMES):
        raise ValueError("vocal pairwise verifier output roster is out of date")

    verified_outputs: list[dict[str, Any]] = []
    actual_output_bytes = 0
    for output_id, expected in expected_by_id.items():
        returned = returned_by_id[output_id]
        actual_bytes, actual_sha256 = _verify_local_artifact(
            root / OUTPUT_FILENAMES[output_id],
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
        raise ValueError("local artifact bytes do not match the result receipt")

    metrics = _read_json_document(root / OUTPUT_FILENAMES["metrics-json"], "metrics")
    checkpoints = _load_and_verify_checkpoints(root, request=request)
    recomputed = _recompute_evidence(checkpoints)
    _verify_metrics(metrics, request=request, result=result, recomputed=recomputed)

    verification: dict[str, Any] = {
        "schema": VERIFICATION_SCHEMA,
        "status": "verified_synthetic_technical_evidence_only",
        "repository_commit": request["repository_commit"],
        "experiment_id": request["experiment_id"],
        "request_document_sha256": request["document_sha256"],
        "result_document_sha256": result["document_sha256"],
        "dataset_sha256": request["dataset"]["sha256"],
        "outputs": verified_outputs,
        "recomputed_evidence": recomputed,
        "checks": {
            "exact_request_result_and_repository": True,
            "exact_local_output_roster": True,
            "local_artifact_size_and_sha256": True,
            "restricted_cpu_checkpoint_load": True,
            "checkpoint_identity_and_steps": True,
            "finite_metrics_match_checkpoint_evidence": True,
            "acceptance_recomputed": True,
            "offline_zero_retry_evidence": True,
            "absolute_paths_absent": True,
        },
        "authority": {
            "technical_synthetic_verification_only": True,
            "real_training_authorized": False,
            "musical_selection": False,
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
        raise ValueError(f"{label} exceeds the verifier size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _verify_exact_local_roster(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact directory must be a regular local directory")
    expected = {RESULT_FILENAME, *OUTPUT_FILENAMES.values()}
    observed = {entry.name for entry in root.iterdir()}
    if observed != expected:
        raise ValueError("local vocal pairwise artifact roster changed")


def _verify_local_artifact(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("a vocal pairwise artifact is not a regular local file")
    before = path.stat()
    if before.st_size != expected_bytes:
        raise ValueError("a vocal pairwise artifact size differs from its receipt")
    observed_sha256 = file_sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("a vocal pairwise artifact changed during verification")
    if observed_sha256 != expected_sha256:
        raise ValueError("a vocal pairwise artifact SHA-256 differs from its receipt")
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
        raise ValueError("repository HEAD does not match the vocal pairwise request")
    for arguments in (
        ("diff", "--quiet", "HEAD", "--"),
        ("diff", "--cached", "--quiet", "HEAD", "--"),
    ):
        if git(*arguments).returncode != 0:
            raise ValueError(
                "repository tracked files differ from the requested commit"
            )


def _verify_offline_evidence(
    *, request: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    environment = result["environment"]
    if (
        environment.get("network_used") is not False
        or environment.get("network_attempts") != 0
        or environment.get("downloads_used") is not False
        or environment.get("deterministic_algorithms") is not True
    ):
        raise ValueError("vocal pairwise result lacks offline deterministic evidence")
    if environment.get("cublas_workspace_config") != request["execution_policy"].get(
        "cublas_workspace_config"
    ):
        raise ValueError("vocal pairwise CuBLAS configuration changed")
    evidence = result["training_evidence"]
    if (
        evidence.get("synthetic_only") is not True
        or evidence.get("network_attempts") != 0
        or evidence.get("retries") != 0
    ):
        raise ValueError(
            "vocal pairwise training evidence is not synthetic offline evidence"
        )
    for section, keys in (
        (result["timings"], ("wall_seconds", "optimisation_steps", "arms")),
        (result["resources"], ("peak_gpu_bytes", "peak_ram_bytes", "output_bytes")),
    ):
        for key in keys:
            _finite_number(section.get(key), key)


def _load_and_verify_checkpoints(
    root: Path, *, request: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    checkpoints: dict[str, Mapping[str, Any]] = {}
    for output_id, expected_step in CHECKPOINT_STEPS.items():
        checkpoint_path = root / OUTPUT_FILENAMES[output_id]
        loaded = _load_checkpoint_weights_only(checkpoint_path)
        if not isinstance(loaded, Mapping):
            raise ValueError("vocal pairwise checkpoint must be a mapping")
        expected_identity = {
            "schema": "sunofriend.vocal-pairwise-gpu-checkpoint.v1",
            "request_document_sha256": request["document_sha256"],
            "dataset_sha256": request["dataset"]["sha256"],
            "repository_commit": request["repository_commit"],
            "experiment_id": request["experiment_id"],
            "step": expected_step,
            "synthetic_only": True,
        }
        if set(loaded) != {*expected_identity, "model", "optimiser"} or any(
            loaded.get(key) != value for key, value in expected_identity.items()
        ):
            raise ValueError("vocal pairwise checkpoint identity or step changed")
        model = loaded.get("model")
        optimiser = loaded.get("optimiser")
        if not isinstance(model, Mapping) or set(model) != {"weight"}:
            raise ValueError("vocal pairwise checkpoint model fields changed")
        weight = model["weight"]
        if tuple(weight.shape) != (1, 6) or str(weight.dtype) != "torch.float32":
            raise ValueError("vocal pairwise checkpoint model shape or dtype changed")
        if not all(math.isfinite(item) for item in _tensor_values(weight)):
            raise ValueError("vocal pairwise checkpoint contains non-finite weights")
        if not isinstance(optimiser, Mapping):
            raise ValueError("vocal pairwise checkpoint optimiser fields changed")
        _require_finite_nested(loaded)
        checkpoints[output_id] = loaded
    return checkpoints


def _recompute_evidence(
    checkpoints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fixture = build_synthetic_pairwise_fixture()
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]

    def accuracy(output_id: str) -> float:
        weights = _tensor_values(checkpoints[output_id]["model"]["weight"])
        correct = sum(
            int(
                int(
                    sum(
                        float(feature) * weight
                        for feature, weight in zip(row["feature_delta"], weights)
                    )
                    >= 0.0
                )
                == int(row["label"])
            )
            for row in heldout
        )
        return correct / len(heldout)

    clean_accuracy = accuracy("checkpoint-final-uninterrupted")
    resumed_accuracy = accuracy("checkpoint-final-resumed")
    shuffled_accuracy = accuracy("checkpoint-final-shuffled")
    parameter_difference = _maximum_nested_difference(
        checkpoints["checkpoint-final-uninterrupted"]["model"],
        checkpoints["checkpoint-final-resumed"]["model"],
    )
    optimiser_difference = _maximum_nested_difference(
        checkpoints["checkpoint-final-uninterrupted"]["optimiser"],
        checkpoints["checkpoint-final-resumed"]["optimiser"],
    )
    for name, value in (
        ("clean heldout accuracy", clean_accuracy),
        ("resumed heldout accuracy", resumed_accuracy),
        ("shuffled heldout accuracy", shuffled_accuracy),
        ("resume parameter difference", parameter_difference),
        ("resume optimiser difference", optimiser_difference),
    ):
        _finite_number(value, name)
    acceptance = {
        "clean_accuracy_at_least_0_85": clean_accuracy >= 0.85,
        "clean_advantage_at_least_0_20": clean_accuracy - shuffled_accuracy >= 0.20,
        "resume_equivalence_at_most_1e_7": max(
            parameter_difference, optimiser_difference
        )
        <= 1e-7,
    }
    return {
        "clean_heldout_accuracy": clean_accuracy,
        "resumed_heldout_accuracy": resumed_accuracy,
        "shuffled_heldout_accuracy": shuffled_accuracy,
        "clean_minus_shuffled_accuracy": clean_accuracy - shuffled_accuracy,
        "maximum_resume_parameter_difference": parameter_difference,
        "maximum_resume_optimiser_difference": optimiser_difference,
        "acceptance": acceptance,
    }


def _verify_metrics(
    metrics: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    recomputed: Mapping[str, Any],
) -> None:
    if metrics.get("schema") != "sunofriend.vocal-pairwise-gpu-canary-metrics.v1":
        raise ValueError("vocal pairwise metrics schema changed")
    unsigned = dict(metrics)
    observed_hash = unsigned.pop("document_sha256", None)
    if observed_hash != document_sha256(unsigned):
        raise ValueError("vocal pairwise metrics document SHA-256 does not match")
    if (
        metrics.get("request_document_sha256") != request["document_sha256"]
        or metrics.get("dataset_sha256") != request["dataset"]["sha256"]
    ):
        raise ValueError("vocal pairwise metrics do not bind request and dataset")
    if metrics.get("authority") != "technical_synthetic_pipeline_evidence_only":
        raise ValueError("vocal pairwise metrics grant unsupported authority")
    if metrics.get("network_attempts") != 0 or metrics.get("retries") != 0:
        raise ValueError("vocal pairwise metrics are not offline zero-retry evidence")

    evidence = result["training_evidence"]
    cross_checks = {
        "clean_heldout_accuracy": evidence["clean_heldout_accuracy"],
        "shuffled_heldout_accuracy": evidence["shuffled_heldout_accuracy"],
        "maximum_resume_parameter_difference": evidence["resume_parameter_difference"],
        "maximum_resume_optimiser_difference": evidence["resume_optimiser_difference"],
    }
    for key, result_value in cross_checks.items():
        observed = _finite_number(metrics.get(key), key)
        if observed != float(result_value) or observed != float(recomputed[key]):
            raise ValueError(f"vocal pairwise metrics {key} does not match evidence")
    advantage = _finite_number(
        metrics.get("clean_minus_shuffled_accuracy"),
        "clean_minus_shuffled_accuracy",
    )
    if advantage != float(recomputed["clean_minus_shuffled_accuracy"]):
        raise ValueError("vocal pairwise clean advantage does not match checkpoints")
    if metrics.get("acceptance") != recomputed["acceptance"]:
        raise ValueError(
            "vocal pairwise metrics acceptance was not independently reproduced"
        )
    if evidence.get("acceptance") != recomputed["acceptance"]:
        raise ValueError(
            "vocal pairwise result acceptance was not independently reproduced"
        )
    if not all(recomputed["acceptance"].values()):
        raise ValueError("vocal pairwise checkpoint evidence did not pass acceptance")
    _reject_absolute_path_strings(metrics)


def _require_finite_nested(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _require_finite_nested(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _require_finite_nested(item)
    elif _is_tensor_like(value):
        if not all(math.isfinite(item) for item in _tensor_values(value)):
            raise ValueError("vocal pairwise checkpoint contains non-finite tensors")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("vocal pairwise checkpoint contains non-finite values")


def _maximum_nested_difference(left: Any, right: Any) -> float:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            raise ValueError("resume checkpoint mapping fields differ")
        return max(
            (_maximum_nested_difference(left[key], right[key]) for key in left),
            default=0.0,
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if type(left) is not type(right) or len(left) != len(right):
            raise ValueError("resume checkpoint sequence fields differ")
        return max(
            (_maximum_nested_difference(a, b) for a, b in zip(left, right)),
            default=0.0,
        )
    if _is_tensor_like(left) and _is_tensor_like(right):
        if left.shape != right.shape or left.dtype != right.dtype:
            raise ValueError("resume checkpoint tensor shape or dtype differs")
        left_values = _tensor_values(left)
        right_values = _tensor_values(right)
        if len(left_values) != len(right_values):
            raise ValueError("resume checkpoint tensor sizes differ")
        return max((abs(a - b) for a, b in zip(left_values, right_values)), default=0.0)
    if isinstance(left, bool) or isinstance(right, bool):
        if left is not right:
            raise ValueError("resume checkpoint boolean fields differ")
        return 0.0
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        difference = abs(float(left) - float(right))
        if not math.isfinite(difference):
            raise ValueError("resume checkpoint numeric difference is non-finite")
        return difference
    if left != right:
        raise ValueError("resume checkpoint non-numeric fields differ")
    return 0.0


def _load_checkpoint_weights_only(path: Path) -> Any:
    import torch

    return torch.load(path, weights_only=True, map_location="cpu")


def _is_tensor_like(value: Any) -> bool:
    return all(
        hasattr(value, attribute)
        for attribute in ("shape", "dtype", "detach", "cpu", "reshape", "tolist")
    )


def _tensor_values(value: Any) -> list[float]:
    if not _is_tensor_like(value):
        raise ValueError("vocal pairwise checkpoint value is not a tensor")
    raw = value.detach().cpu().reshape(-1).tolist()
    if not isinstance(raw, list):
        raise ValueError("vocal pairwise checkpoint tensor values changed")
    return [float(item) for item in raw]


def _finite_number(value: Any, label: str) -> float:
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
        raise ValueError("vocal pairwise portable documents may not expose paths")


__all__ = [
    "CHECKPOINT_STEPS",
    "OUTPUT_FILENAMES",
    "RESULT_FILENAME",
    "VERIFICATION_SCHEMA",
    "verify_pairwise_gpu_canary_round_trip",
]
