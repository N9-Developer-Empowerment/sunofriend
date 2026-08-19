"""Deterministic C0 training-pipeline canary for an authorised RTX worker."""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Mapping

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
            features = [round(generator.uniform(-1.0, 1.0), 9) for _ in range(feature_count)]
            score = features[0] + 0.65 * features[1] - 0.35 * features[2]
            if abs(score) < 0.20:
                features[0] = round(features[0] + (0.30 if score >= 0 else -0.30), 9)
                score = features[0] + 0.65 * features[1] - 0.35 * features[2]
            examples.append(
                {
                    "example_id": f"group-{group_index:02d}-example-{example_index:02d}",
                    "group_id": f"composition-{group_index:02d}",
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
            "train_group_count": 12,
            "heldout_group_count": 4,
            "generator_seed": fixture["seed"],
        },
        model={
            "name": "tiny-pairwise-pipeline-canary",
            "version": "0.0.1",
            "architecture": "linear16-tanh-linear1",
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
        },
        expected_outputs=[
            {
                "output_id": "metrics-json",
                "kind": "metrics",
                "media_type": "application/json",
            },
            {
                "output_id": "checkpoint-step-100",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
            },
            {
                "output_id": "checkpoint-final-uninterrupted",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
            },
            {
                "output_id": "checkpoint-final-resumed",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
            },
            {
                "output_id": "checkpoint-final-shuffled",
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
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
        },
        stop_rules=[
            "stop if CUDA is unavailable",
            "stop on non-finite loss or metric",
            "stop before any declared resource ceiling is exceeded",
            "stop on request, dataset or repository identity mismatch",
            "stop if resumed and uninterrupted weights differ beyond 1e-7",
        ],
    )


def run_c0_canary(
    request: Mapping[str, Any], *, out_dir: str | Path
) -> dict[str, Any]:
    """Run the approved synthetic canary; no network or private audio is used."""

    request_document = validate_gpu_worker_request(request)
    _validate_exact_c0_request(request_document)
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"GPU canary output already exists: {destination}")
    destination.mkdir(parents=True)
    started = time.monotonic()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("C0 canary requires the authorised CUDA worker")
    device = torch.device("cuda")
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.cuda.reset_peak_memory_stats(device)

    fixture = build_synthetic_fixture(seed=int(request_document["dataset"]["generator_seed"]))
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
        start_step=0,
        end_step=maximum_steps,
        batch_size=batch_size,
        checkpoint_step=resume_step,
    )
    checkpoint_path = destination / "checkpoint-step-100.pt"
    final_path = destination / "checkpoint-final-uninterrupted.pt"
    torch.save(checkpoint, checkpoint_path)
    torch.save(_checkpoint(uninterrupted, uninterrupted_optimizer, maximum_steps), final_path)

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
        start_step=resume_step,
        end_step=maximum_steps,
        batch_size=batch_size,
    )
    resumed_path = destination / "checkpoint-final-resumed.pt"
    torch.save(_checkpoint(resumed, resumed_optimizer, maximum_steps), resumed_path)

    shuffled_labels = labels.detach().clone()
    permutation = torch.randperm(
        shuffled_labels.shape[0], generator=torch.Generator().manual_seed(seed + 1)
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
        start_step=0,
        end_step=maximum_steps,
        batch_size=batch_size,
    )
    shuffled_path = destination / "checkpoint-final-shuffled.pt"
    torch.save(_checkpoint(shuffled, shuffled_optimizer, maximum_steps), shuffled_path)

    clean_accuracy = _accuracy(torch, uninterrupted, heldout_features, heldout_labels)
    shuffled_accuracy = _accuracy(torch, shuffled, heldout_features, heldout_labels)
    resume_max_abs = _maximum_parameter_difference(torch, uninterrupted, resumed)
    metrics = {
        "schema": "sunofriend.gpu-canary-metrics.v1",
        "experiment_id": EXPERIMENT_ID,
        "dataset_sha256": request_document["dataset"]["sha256"],
        "clean_heldout_accuracy": clean_accuracy,
        "shuffled_heldout_accuracy": shuffled_accuracy,
        "clean_minus_shuffled_accuracy": clean_accuracy - shuffled_accuracy,
        "resume_max_abs_parameter_difference": resume_max_abs,
        "curves": {
            "clean_uninterrupted": clean_curve,
            "clean_resumed": resumed_curve,
            "shuffled_control": shuffled_curve,
        },
        "pipeline_acceptance": {
            "clean_accuracy_at_least_0_90": clean_accuracy >= 0.90,
            "clean_advantage_at_least_0_20": clean_accuracy - shuffled_accuracy >= 0.20,
            "resume_difference_at_most_1e_7": resume_max_abs <= 1e-7,
        },
        "authority": "technical_pipeline_evidence_only",
    }
    if not all(math.isfinite(float(value)) for value in (
        clean_accuracy,
        shuffled_accuracy,
        resume_max_abs,
    )):
        raise RuntimeError("C0 canary produced a non-finite metric")
    metrics_path = destination / "metrics.json"
    metrics_path.write_bytes(canonical_json_bytes(metrics))

    elapsed = time.monotonic() - started
    outputs = [
        _output_record("metrics-json", "metrics", metrics_path),
        _output_record("checkpoint-step-100", "checkpoint", checkpoint_path),
        _output_record("checkpoint-final-uninterrupted", "checkpoint", final_path),
        _output_record("checkpoint-final-resumed", "checkpoint", resumed_path),
        _output_record("checkpoint-final-shuffled", "checkpoint", shuffled_path),
    ]
    result = build_gpu_worker_result(
        request=request_document,
        status="complete",
        environment={
            "operating_system": sys.platform,
            "python": sys.version.split()[0],
            "torch": str(torch.__version__),
            "cuda_runtime": str(torch.version.cuda),
            "gpu": str(torch.cuda.get_device_name(device)),
            "deterministic_algorithms": True,
            "network_used": False,
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
        },
        warnings=(
            []
            if all(metrics["pipeline_acceptance"].values())
            else ["one or more technical canary acceptance checks failed"]
        ),
    )
    validate_gpu_worker_result(result, request=request_document)
    (destination / "gpu-worker-result.json").write_bytes(canonical_json_bytes(result))
    return result


def _validate_exact_c0_request(request: Mapping[str, Any]) -> None:
    expected = build_c0_canary_request(str(request["repository_commit"]))
    if request != expected:
        raise ValueError("GPU request is not the exact supported C0 canary contract")


def _tensor_fixture(torch: Any, fixture: Mapping[str, Any], device: Any) -> tuple[Any, ...]:
    train = [row for row in fixture["examples"] if row["split"] == "train"]
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]
    return (
        torch.tensor([row["features"] for row in train], dtype=torch.float32, device=device),
        torch.tensor([row["label"] for row in train], dtype=torch.float32, device=device),
        torch.tensor([row["features"] for row in heldout], dtype=torch.float32, device=device),
        torch.tensor([row["label"] for row in heldout], dtype=torch.float32, device=device),
    )


def _new_model(torch: Any, device: Any, seed: int) -> Any:
    torch.manual_seed(seed)
    model = torch.nn.Sequential(
        torch.nn.Linear(16, 16),
        torch.nn.Tanh(),
        torch.nn.Linear(16, 1),
    )
    return model.to(device)


def _train_steps(
    torch: Any,
    model: Any,
    optimiser: Any,
    features: Any,
    labels: Any,
    *,
    start_step: int,
    end_step: int,
    batch_size: int,
    checkpoint_step: int | None = None,
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
        completed = step + 1
        if completed in {1, 25, 50, 100, 150, 200}:
            curve.append({"step": completed, "loss": float(loss.detach().cpu())})
        if checkpoint_step is not None and completed == checkpoint_step:
            saved = _checkpoint(model, optimiser, completed)
    return curve, saved


def _checkpoint(model: Any, optimiser: Any, step: int) -> dict[str, Any]:
    return {
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
        difference = float(torch.max(torch.abs(left_value - right_value)).detach().cpu())
        maximum = max(maximum, difference)
    return maximum


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

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        )
        if not ok:
            raise RuntimeError("could not read Windows process memory")
        return int(counters.PeakWorkingSetSize)
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
