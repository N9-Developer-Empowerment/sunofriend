"""Deterministic C0 training-pipeline canary for an authorised RTX worker."""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from typing import Any, Callable, Mapping

from .audio_formats import file_sha256
from .gpu_worker_contract import (
    build_gpu_worker_request,
    build_gpu_worker_result,
    validate_gpu_worker_request,
    validate_gpu_worker_result,
)
from .source_receipt import canonical_json_bytes, document_sha256


SYNTHETIC_FIXTURE_SCHEMA = "sunofriend.synthetic-pairwise.v1"
EXPERIMENT_ID = "c0-synthetic-tiny-overfit-001"


def build_synthetic_fixture(*, seed: int = 1729) -> dict[str, Any]:
    """Create a private-audio-free, composition-grouped binary fixture."""

    generator = random.Random(seed)
    examples: list[dict[str, Any]] = []
    feature_count = 16
    group_count = 16
    examples_per_group = 16
    for group_index in range(group_count):
        split = "train" if group_index < 12 else "heldout"
        for example_index in range(examples_per_group):
            features = [
                round(generator.uniform(-1.0, 1.0), 9) for _ in range(feature_count)
            ]
            score = features[0] + 0.65 * features[1] - 0.35 * features[2]
            if abs(score) < 0.20:
                features[0] = round(features[0] + (0.30 if score >= 0 else -0.30), 9)
                score = features[0] + 0.65 * features[1] - 0.35 * features[2]
            examples.append(
                {
                    "example_id": f"group-{group_index:02d}-example-{example_index:02d}",
                    "group_id": f"composition-{group_index:02d}",
                    "composition_id": f"composition-{group_index:02d}",
                    "split": split,
                    "features": features,
                    "label": int(score >= 0),
                }
            )
    return {
        "schema": SYNTHETIC_FIXTURE_SCHEMA,
        "seed": seed,
        "feature_count": feature_count,
        "group_count": group_count,
        "examples": examples,
    }


def build_c0_canary_request(repository_commit: str) -> dict[str, Any]:
    """Build the exact offline request for the first bounded CUDA canary."""

    fixture = build_synthetic_fixture()
    fixture_sha256 = document_sha256(fixture)
    train_group_ids = sorted(
        {row["group_id"] for row in fixture["examples"] if row["split"] == "train"}
    )
    heldout_group_ids = sorted(
        {row["group_id"] for row in fixture["examples"] if row["split"] == "heldout"}
    )
    train_composition_ids = sorted(
        {
            row["composition_id"]
            for row in fixture["examples"]
            if row["split"] == "train"
        }
    )
    heldout_composition_ids = sorted(
        {
            row["composition_id"]
            for row in fixture["examples"]
            if row["split"] == "heldout"
        }
    )
    return build_gpu_worker_request(
        repository_commit=repository_commit,
        experiment_id=EXPERIMENT_ID,
        task_kind="tiny_overfit_test",
        method_natures=["D", "T"],
        authorised_asset_hashes=[fixture_sha256],
        dataset={
            "dataset_id": "synthetic-margin-v1",
            "schema": SYNTHETIC_FIXTURE_SCHEMA,
            "sha256": fixture_sha256,
            "synthetic": True,
            "group_count": fixture["group_count"],
            "feature_count": fixture["feature_count"],
            "example_count": len(fixture["examples"]),
            "feature_shape": [256, 16],
            "train_shape": [192, 16],
            "heldout_shape": [64, 16],
            "dtype": "float32",
            "train_group_count": 12,
            "heldout_group_count": 4,
            "train_group_ids": train_group_ids,
            "heldout_group_ids": heldout_group_ids,
            "train_composition_ids": train_composition_ids,
            "heldout_composition_ids": heldout_composition_ids,
            "generation_seed": fixture["seed"],
        },
        model={
            "name": "tiny-pairwise-pipeline-canary",
            "version": "0.0.1",
            "architecture": "linear16-tanh-linear1",
            "input_features": 16,
            "hidden_features": 16,
            "output_features": 1,
            "parameter_dtype": "float32",
            "initialisation_seed": 1729,
            "authority": "pipeline_test_only",
        },
        windows=[],
        training={
            "seed": 1729,
            "optimiser": "adamw",
            "maximum_steps_per_arm": 200,
            "resume_step": 100,
            "batch_size": 32,
            "learning_rate": 0.01,
            "shuffled_label_control": True,
            "checkpoint_steps": [100, 200],
            "deterministic_algorithms": True,
        },
        expected_outputs=[
            {
                "output_id": "metrics-json",
                "kind": "metrics",
                "media_type": "application/json",
                "shape": {"arm_count": 3, "scalar_metric_count": 3},
            },
            {
                "output_id": "checkpoint-step-100",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
                "shape": {"parameter_count": 289, "step": 100},
            },
            {
                "output_id": "checkpoint-final-uninterrupted",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
                "shape": {"parameter_count": 289, "step": 200},
            },
            {
                "output_id": "checkpoint-final-resumed",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
                "shape": {"parameter_count": 289, "step": 200},
            },
            {
                "output_id": "checkpoint-final-shuffled",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
                "shape": {"parameter_count": 289, "step": 200},
            },
        ],
        resource_ceiling={
            "maximum_wall_seconds": 900,
            "maximum_gpu_bytes": 4_294_967_296,
            "maximum_ram_bytes": 8_589_934_592,
            "maximum_output_bytes": 67_108_864,
        },
        execution_policy={
            "network_allowed": False,
            "downloads_allowed": False,
            "maximum_retries": 0,
            "cublas_workspace_config": ":4096:8",
        },
        stop_rules=[
            "stop if CUDA is unavailable",
            "stop on non-finite loss or metric",
            "stop before any declared resource ceiling is exceeded",
            "stop on request, dataset or repository identity mismatch",
            "stop if resumed and uninterrupted weights differ beyond 1e-7",
        ],
    )


def run_c0_canary(request: Mapping[str, Any], *, out_dir: str | Path) -> dict[str, Any]:
    """Run the approved synthetic canary; no network or private audio is used."""

    request_document = validate_gpu_worker_request(request)
    _validate_exact_c0_request(request_document)
    started = time.monotonic()
    required_workspace = request_document["execution_policy"]["cublas_workspace_config"]
    existing_workspace = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if existing_workspace not in {None, required_workspace}:
        raise RuntimeError(
            "CUBLAS_WORKSPACE_CONFIG conflicts with the authorised request"
        )
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = required_workspace
    _verify_repository_commit(str(request_document["repository_commit"]))
    network_counter = _install_network_denial()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("C0 canary requires the authorised CUDA worker")
    device = torch.device("cuda")
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.cuda.reset_peak_memory_stats(device)

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"GPU canary output already exists: {destination}")
    destination.mkdir(parents=True)
    guard = _RuntimeGuard(
        torch=torch,
        device=device,
        started=started,
        destination=destination,
        ceiling=request_document["resource_ceiling"],
    )
    guard.check()

    fixture = build_synthetic_fixture(
        seed=int(request_document["dataset"]["generation_seed"])
    )
    if document_sha256(fixture) != request_document["dataset"]["sha256"]:
        raise ValueError("synthetic fixture identity does not match request")
    features, labels, heldout_features, heldout_labels = _tensor_fixture(
        torch, fixture, device
    )
    training = request_document["training"]
    seed = int(training["seed"])
    maximum_steps = int(training["maximum_steps_per_arm"])
    resume_step = int(training["resume_step"])
    batch_size = int(training["batch_size"])
    learning_rate = float(training["learning_rate"])

    uninterrupted = _new_model(torch, device, seed)
    uninterrupted_optimizer = torch.optim.AdamW(
        uninterrupted.parameters(), lr=learning_rate
    )
    clean_curve, checkpoint = _train_steps(
        torch,
        uninterrupted,
        uninterrupted_optimizer,
        features,
        labels,
        request=request_document,
        start_step=0,
        end_step=maximum_steps,
        batch_size=batch_size,
        checkpoint_step=resume_step,
        resource_check=guard.check,
    )
    if checkpoint is None:
        raise RuntimeError("C0 canary did not produce the required resume checkpoint")
    checkpoint_path = destination / "checkpoint-step-100.pt"
    final_path = destination / "checkpoint-final-uninterrupted.pt"
    torch.save(checkpoint, checkpoint_path)
    torch.save(
        _checkpoint(
            uninterrupted,
            uninterrupted_optimizer,
            maximum_steps,
            request=request_document,
        ),
        final_path,
    )
    guard.check()

    resumed = _new_model(torch, device, seed)
    resumed_optimizer = torch.optim.AdamW(resumed.parameters(), lr=learning_rate)
    resumed.load_state_dict(checkpoint["model"])
    resumed_optimizer.load_state_dict(checkpoint["optimiser"])
    resumed_curve, _ = _train_steps(
        torch,
        resumed,
        resumed_optimizer,
        features,
        labels,
        request=request_document,
        start_step=resume_step,
        end_step=maximum_steps,
        batch_size=batch_size,
        resource_check=guard.check,
    )
    resumed_path = destination / "checkpoint-final-resumed.pt"
    torch.save(
        _checkpoint(
            resumed,
            resumed_optimizer,
            maximum_steps,
            request=request_document,
        ),
        resumed_path,
    )
    guard.check()

    shuffled_labels = labels.detach().clone()
    permutation = torch.randperm(
        shuffled_labels.shape[0],
        generator=torch.Generator().manual_seed(seed + 1),
    ).to(device)
    shuffled_labels = shuffled_labels[permutation]
    shuffled = _new_model(torch, device, seed)
    shuffled_optimizer = torch.optim.AdamW(shuffled.parameters(), lr=learning_rate)
    shuffled_curve, _ = _train_steps(
        torch,
        shuffled,
        shuffled_optimizer,
        features,
        shuffled_labels,
        request=request_document,
        start_step=0,
        end_step=maximum_steps,
        batch_size=batch_size,
        resource_check=guard.check,
    )
    shuffled_path = destination / "checkpoint-final-shuffled.pt"
    torch.save(
        _checkpoint(
            shuffled,
            shuffled_optimizer,
            maximum_steps,
            request=request_document,
        ),
        shuffled_path,
    )
    guard.check()

    clean_accuracy = _accuracy(torch, uninterrupted, heldout_features, heldout_labels)
    shuffled_accuracy = _accuracy(torch, shuffled, heldout_features, heldout_labels)
    resume_max_abs = _maximum_parameter_difference(torch, uninterrupted, resumed)
    resume_optimiser_max_abs = _maximum_nested_numeric_difference(
        torch,
        uninterrupted_optimizer.state_dict(),
        resumed_optimizer.state_dict(),
    )
    clean_advantage = clean_accuracy - shuffled_accuracy
    resume_tolerance = 1e-7
    acceptance = {
        "clean_accuracy_at_least_0_90": clean_accuracy >= 0.90,
        "clean_advantage_at_least_0_20": clean_advantage >= 0.20,
        "resume_equivalence_at_most_1e_7": (
            resume_max_abs <= resume_tolerance
            and resume_optimiser_max_abs <= resume_tolerance
        ),
    }
    metrics = {
        "schema": "sunofriend.gpu-canary-metrics.v1",
        "experiment_id": EXPERIMENT_ID,
        "request_document_sha256": request_document["document_sha256"],
        "repository_commit": request_document["repository_commit"],
        "dataset_sha256": request_document["dataset"]["sha256"],
        "clean_heldout_accuracy": clean_accuracy,
        "shuffled_heldout_accuracy": shuffled_accuracy,
        "clean_minus_shuffled_accuracy": clean_advantage,
        "resume_max_abs_parameter_difference": resume_max_abs,
        "resume_max_abs_optimiser_difference": resume_optimiser_max_abs,
        "curves": {
            "clean_uninterrupted": clean_curve,
            "clean_resumed": resumed_curve,
            "shuffled_control": shuffled_curve,
        },
        "pipeline_acceptance": acceptance,
        "authority": "technical_research_challenger_only",
        "network_attempts": network_counter["attempts"],
        "retries": 0,
    }
    if not all(
        math.isfinite(float(value))
        for value in (
            clean_accuracy,
            shuffled_accuracy,
            resume_max_abs,
            resume_optimiser_max_abs,
            clean_curve[-1]["loss"],
            resumed_curve[-1]["loss"],
            shuffled_curve[-1]["loss"],
        )
    ):
        raise RuntimeError("C0 canary produced a non-finite metric")
    metrics["document_sha256"] = document_sha256(metrics)
    metrics_path = destination / "metrics.json"
    metrics_path.write_bytes(canonical_json_bytes(metrics))
    guard.check()

    elapsed = time.monotonic() - started
    outputs = [
        _output_record("metrics-json", "metrics", metrics_path),
        _output_record("checkpoint-step-100", "checkpoint", checkpoint_path),
        _output_record("checkpoint-final-uninterrupted", "checkpoint", final_path),
        _output_record("checkpoint-final-resumed", "checkpoint", resumed_path),
        _output_record("checkpoint-final-shuffled", "checkpoint", shuffled_path),
    ]
    training_evidence = {
        "dataset": {
            "sha256": request_document["dataset"]["sha256"],
            "generation_seed": request_document["dataset"]["generation_seed"],
            "dtype": request_document["dataset"]["dtype"],
            "train_shape": request_document["dataset"]["train_shape"],
            "heldout_shape": request_document["dataset"]["heldout_shape"],
            "train_group_ids": request_document["dataset"]["train_group_ids"],
            "heldout_group_ids": request_document["dataset"]["heldout_group_ids"],
            "train_composition_ids": request_document["dataset"][
                "train_composition_ids"
            ],
            "heldout_composition_ids": request_document["dataset"][
                "heldout_composition_ids"
            ],
        },
        "model": {
            key: request_document["model"][key]
            for key in (
                "architecture",
                "input_features",
                "hidden_features",
                "output_features",
                "parameter_dtype",
            )
        },
        "execution": dict(training)
        | {
            "network_attempts": network_counter["attempts"],
            "retries": 0,
        },
        "arms": [
            {
                "arm_id": "clean_uninterrupted",
                "steps": maximum_steps,
                "final_loss": clean_curve[-1]["loss"],
                "heldout_accuracy": clean_accuracy,
                "finite_losses": True,
            },
            {
                "arm_id": "clean_resumed",
                "steps": maximum_steps,
                "final_loss": resumed_curve[-1]["loss"],
                "heldout_accuracy": _accuracy(
                    torch, resumed, heldout_features, heldout_labels
                ),
                "finite_losses": True,
            },
            {
                "arm_id": "shuffled_label_control",
                "steps": maximum_steps,
                "final_loss": shuffled_curve[-1]["loss"],
                "heldout_accuracy": shuffled_accuracy,
                "finite_losses": True,
            },
        ],
        "resume_equivalence": {
            "maximum_parameter_difference": resume_max_abs,
            "maximum_optimiser_difference": resume_optimiser_max_abs,
            "tolerance": resume_tolerance,
            "passed": acceptance["resume_equivalence_at_most_1e_7"],
        },
        "acceptance": acceptance,
    }
    result_status = "complete" if all(acceptance.values()) else "failed"
    result = build_gpu_worker_result(
        request=request_document,
        status=result_status,
        environment={
            "operating_system": sys.platform,
            "python": sys.version.split()[0],
            "torch": str(torch.__version__),
            "cuda_runtime": str(torch.version.cuda),
            "gpu": str(torch.cuda.get_device_name(device)),
            "deterministic_algorithms": True,
            "cublas_workspace_config": required_workspace,
            "network_used": False,
            "network_attempts": network_counter["attempts"],
            "downloads_used": False,
        },
        outputs=outputs,
        timings={
            "wall_seconds": elapsed,
            "optimisation_steps": maximum_steps,
            "arms": 3,
        },
        resources={
            "peak_gpu_bytes": int(torch.cuda.max_memory_allocated(device)),
            "peak_ram_bytes": _resident_set_bytes(),
            "output_bytes": sum(row["bytes"] for row in outputs),
        },
        training_evidence=training_evidence,
        warnings=(
            []
            if all(acceptance.values())
            else ["one or more technical canary acceptance checks failed"]
        ),
    )
    validate_gpu_worker_result(result, request=request_document)
    (destination / "gpu-worker-result.json").write_bytes(canonical_json_bytes(result))
    guard.check()
    return result


def _validate_exact_c0_request(request: Mapping[str, Any]) -> None:
    expected = build_c0_canary_request(str(request["repository_commit"]))
    if request != expected:
        raise ValueError("GPU request is not the exact supported C0 canary contract")


def _tensor_fixture(
    torch: Any, fixture: Mapping[str, Any], device: Any
) -> tuple[Any, ...]:
    train = [row for row in fixture["examples"] if row["split"] == "train"]
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]
    return (
        torch.tensor(
            [row["features"] for row in train], dtype=torch.float32, device=device
        ),
        torch.tensor(
            [row["label"] for row in train], dtype=torch.float32, device=device
        ),
        torch.tensor(
            [row["features"] for row in heldout], dtype=torch.float32, device=device
        ),
        torch.tensor(
            [row["label"] for row in heldout], dtype=torch.float32, device=device
        ),
    )


def _new_model(torch: Any, device: Any, seed: int) -> Any:
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    model = torch.nn.Sequential(
        torch.nn.Linear(16, 16),
        torch.nn.Tanh(),
        torch.nn.Linear(16, 1),
    )
    return model.to(device=device, dtype=torch.float32)


def _train_steps(
    torch: Any,
    model: Any,
    optimiser: Any,
    features: Any,
    labels: Any,
    *,
    request: Mapping[str, Any],
    start_step: int,
    end_step: int,
    batch_size: int,
    checkpoint_step: int | None = None,
    resource_check: Callable[[], None] | None = None,
) -> tuple[list[dict[str, float | int]], dict[str, Any] | None]:
    loss_function = torch.nn.BCEWithLogitsLoss()
    curve: list[dict[str, float | int]] = []
    saved: dict[str, Any] | None = None
    for step in range(start_step, end_step):
        indexes = (
            torch.arange(batch_size, device=features.device) + step * batch_size
        ) % features.shape[0]
        optimiser.zero_grad(set_to_none=True)
        logits = model(features[indexes]).squeeze(1)
        loss = loss_function(logits, labels[indexes])
        if not torch.isfinite(loss):
            raise RuntimeError("C0 canary produced non-finite loss")
        loss.backward()
        optimiser.step()
        _require_finite_model(torch, model)
        completed = step + 1
        if completed in {1, 25, 50, 100, 150, 200}:
            curve.append({"step": completed, "loss": float(loss.detach().cpu())})
        if checkpoint_step is not None and completed == checkpoint_step:
            saved = _checkpoint(model, optimiser, completed, request=request)
        if resource_check is not None:
            resource_check()
    return curve, saved


def _checkpoint(
    model: Any,
    optimiser: Any,
    step: int,
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "sunofriend.gpu-canary-checkpoint.v1",
        "experiment_id": request["experiment_id"],
        "repository_commit": request["repository_commit"],
        "request_document_sha256": request["document_sha256"],
        "dataset_sha256": request["dataset"]["sha256"],
        "parameter_dtype": "float32",
        "model": deepcopy(model.state_dict()),
        "optimiser": deepcopy(optimiser.state_dict()),
        "step": step,
    }


def _accuracy(torch: Any, model: Any, features: Any, labels: Any) -> float:
    with torch.no_grad():
        predictions = (model(features).squeeze(1) >= 0).to(labels.dtype)
        return float((predictions == labels).to(torch.float32).mean().cpu())


def _maximum_parameter_difference(torch: Any, left: Any, right: Any) -> float:
    maximum = 0.0
    for left_value, right_value in zip(left.parameters(), right.parameters()):
        difference = float(
            torch.max(torch.abs(left_value - right_value)).detach().cpu()
        )
        maximum = max(maximum, difference)
    return maximum


def _maximum_nested_numeric_difference(torch: Any, left: Any, right: Any) -> float:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return math.inf
        return max(
            (
                _maximum_nested_numeric_difference(torch, left[key], right[key])
                for key in left
            ),
            default=0.0,
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return math.inf
        return max(
            (
                _maximum_nested_numeric_difference(torch, one, two)
                for one, two in zip(left, right)
            ),
            default=0.0,
        )
    if torch.is_tensor(left) and torch.is_tensor(right):
        if tuple(left.shape) != tuple(right.shape):
            return math.inf
        return float(torch.max(torch.abs(left - right)).detach().cpu())
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right))
    return 0.0 if left == right else math.inf


def _require_finite_model(torch: Any, model: Any) -> None:
    if any(not bool(torch.isfinite(value).all()) for value in model.parameters()):
        raise RuntimeError("C0 canary produced a non-finite model parameter")


class _RuntimeGuard:
    def __init__(
        self,
        *,
        torch: Any,
        device: Any,
        started: float,
        destination: Path,
        ceiling: Mapping[str, Any],
    ) -> None:
        self._torch = torch
        self._device = device
        self._started = started
        self._destination = destination
        self._ceiling = ceiling

    def check(self) -> None:
        if time.monotonic() - self._started > int(
            self._ceiling["maximum_wall_seconds"]
        ):
            raise RuntimeError("C0 canary stopped at the wall-time resource gate")
        if int(self._torch.cuda.max_memory_allocated(self._device)) > int(
            self._ceiling["maximum_gpu_bytes"]
        ):
            raise RuntimeError("C0 canary stopped at the GPU-memory resource gate")
        if _resident_set_bytes() > int(self._ceiling["maximum_ram_bytes"]):
            raise RuntimeError("C0 canary stopped at the RAM resource gate")
        output_bytes = sum(
            path.stat().st_size
            for path in self._destination.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        if output_bytes > int(self._ceiling["maximum_output_bytes"]):
            raise RuntimeError("C0 canary stopped at the output-size resource gate")


def _verify_repository_commit(expected_commit: str) -> None:
    repository = Path(__file__).resolve().parents[2]
    observed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if observed != expected_commit:
        raise RuntimeError("C0 canary repository commit does not match the request")
    clean = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--"],
        cwd=repository,
        check=False,
    )
    if clean.returncode != 0:
        raise RuntimeError("C0 canary requires an unchanged tracked worktree")


def _install_network_denial() -> dict[str, int]:
    counter = {"attempts": 0}
    blocked_events = {
        "socket.bind",
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyaddr",
        "socket.gethostbyname",
        "socket.listen",
    }

    def deny(event: str, _arguments: tuple[Any, ...]) -> None:
        if event in blocked_events:
            counter["attempts"] += 1
            raise RuntimeError("C0 canary blocked an unauthorised network attempt")

    sys.addaudithook(deny)
    return counter


def _output_record(output_id: str, kind: str, path: Path) -> dict[str, Any]:
    return {
        "output_id": output_id,
        "kind": kind,
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def _resident_set_bytes() -> int:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel32.GetCurrentProcess()
        failures: list[str] = []
        for library_name, function_name in (
            ("kernel32", "K32GetProcessMemoryInfo"),
            ("psapi", "GetProcessMemoryInfo"),
        ):
            try:
                library = ctypes.WinDLL(library_name, use_last_error=True)
                function = getattr(library, function_name)
            except (OSError, AttributeError) as exc:
                failures.append(f"{function_name}:unavailable:{exc}")
                continue
            function.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            function.restype = wintypes.BOOL
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            ctypes.set_last_error(0)
            if function(process, ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
            failures.append(f"{function_name}:winerror:{ctypes.get_last_error()}")
        raise RuntimeError(
            "could not read Windows process memory (" + ", ".join(failures) + ")"
        )
    import resource

    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


__all__ = [
    "EXPERIMENT_ID",
    "SYNTHETIC_FIXTURE_SCHEMA",
    "build_c0_canary_request",
    "build_synthetic_fixture",
    "run_c0_canary",
]
