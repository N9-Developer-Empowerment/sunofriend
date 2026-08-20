"""Exact offline CUDA worker for the synthetic vocal pairwise canary."""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any, Mapping

from .gpu_canary import (
    _install_network_denial,
    _maximum_nested_numeric_difference,
    _maximum_parameter_difference,
    _output_record,
    _resident_set_bytes,
    _verify_repository_commit,
)
from .gpu_worker_contract import (
    build_gpu_worker_request,
    build_gpu_worker_result,
    validate_gpu_worker_request,
    validate_gpu_worker_result,
)
from .source_receipt import canonical_json_bytes, document_sha256
from .vocal_pairwise_canary import build_synthetic_pairwise_fixture


GPU_EXPERIMENT_ID = "vocal-pairwise-ranker-synthetic-gpu-001"


def build_pairwise_gpu_canary_request(repository_commit: str) -> dict[str, Any]:
    fixture = build_synthetic_pairwise_fixture()
    fixture_hash = fixture["document_sha256"]
    return build_gpu_worker_request(
        repository_commit=repository_commit,
        experiment_id=GPU_EXPERIMENT_ID,
        task_kind="pairwise_vocal_ranker",
        method_natures=["D", "T"],
        authorised_asset_hashes=[fixture_hash],
        dataset={
            "dataset_id": "synthetic-vocal-pairwise-v1",
            "schema": "sunofriend.synthetic-vocal-pairwise.v1",
            "sha256": fixture_hash,
            "synthetic": True,
            "group_count": 12,
            "composition_count": 12,
            "example_count": 192,
            "feature_count": 6,
            "train_shape": [128, 6],
            "heldout_shape": [64, 6],
            "generation_seed": 20_260_820,
        },
        model={
            "name": "provisional-linear-vocal-pairwise-ranker",
            "version": "0.0.1",
            "architecture": "linear6-no-bias",
            "parameter_count": 6,
            "parameter_dtype": "float32",
            "authority": "synthetic_pipeline_canary_only",
        },
        windows=[
            {
                "window_id": "synthetic-feature-window",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "source_sha256": fixture_hash,
            }
        ],
        training={
            "seed": 20_260_820,
            "optimiser": "sgd",
            "maximum_steps_per_arm": 300,
            "resume_step": 120,
            "batch_size": 128,
            "learning_rate": 0.2,
            "shuffled_label_control": True,
            "deterministic_algorithms": True,
        },
        expected_outputs=[
            {
                "output_id": "metrics-json",
                "kind": "metrics",
                "media_type": "application/json",
                "shape": {"arm_count": 3, "scalar_metric_count": 4},
            },
            *[
                {
                    "output_id": output_id,
                    "kind": "checkpoint",
                    "media_type": "application/x-pytorch",
                    "shape": {"parameter_count": 6, "step": step},
                }
                for output_id, step in (
                    ("checkpoint-step-120", 120),
                    ("checkpoint-final-uninterrupted", 300),
                    ("checkpoint-final-resumed", 300),
                    ("checkpoint-final-shuffled", 300),
                )
            ],
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
            "stop on request, dataset or repository identity mismatch",
            "stop on non-finite loss, metric or parameter",
            "stop before a declared resource ceiling is exceeded",
            "stop if resumed and uninterrupted states differ beyond 1e-7",
        ],
    )


def run_pairwise_gpu_canary(
    request: Mapping[str, Any], *, out_dir: str | Path
) -> dict[str, Any]:
    request_document = validate_gpu_worker_request(request)
    expected = build_pairwise_gpu_canary_request(request_document["repository_commit"])
    if request_document != expected:
        raise ValueError("pairwise GPU canary request differs from the fixed contract")
    required_workspace = request_document["execution_policy"]["cublas_workspace_config"]
    existing_workspace = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if existing_workspace not in {None, required_workspace}:
        raise RuntimeError("CUBLAS_WORKSPACE_CONFIG conflicts with the request")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = required_workspace
    _verify_repository_commit(request_document["repository_commit"])
    network_counter = _install_network_denial()
    started = time.monotonic()

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("vocal pairwise GPU canary requires CUDA")
    device = torch.device("cuda")
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.cuda.reset_peak_memory_stats(device)
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"pairwise GPU canary output already exists: {destination}")
    destination.mkdir(parents=True)

    fixture = build_synthetic_pairwise_fixture()
    if fixture["document_sha256"] != request_document["dataset"]["sha256"]:
        raise ValueError("pairwise GPU fixture identity changed")
    train = [row for row in fixture["examples"] if row["split"] == "train"]
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]
    features = torch.tensor(
        [row["feature_delta"] for row in train], dtype=torch.float32, device=device
    )
    labels = torch.tensor(
        [row["label"] for row in train], dtype=torch.float32, device=device
    )
    heldout_features = torch.tensor(
        [row["feature_delta"] for row in heldout], dtype=torch.float32, device=device
    )
    heldout_labels = torch.tensor(
        [row["label"] for row in heldout], dtype=torch.float32, device=device
    )

    clean, clean_optimizer = _new_model(torch, device)
    checkpoint = _train(
        torch,
        clean,
        clean_optimizer,
        features,
        labels,
        start=0,
        end=120,
        ceiling=request_document["resource_ceiling"],
        started=started,
        request=request_document,
    )
    checkpoint_path = destination / "checkpoint-step-120.pt"
    torch.save(checkpoint, checkpoint_path)
    _train(
        torch,
        clean,
        clean_optimizer,
        features,
        labels,
        start=120,
        end=300,
        ceiling=request_document["resource_ceiling"],
        started=started,
        request=request_document,
    )
    clean_path = destination / "checkpoint-final-uninterrupted.pt"
    torch.save(_checkpoint(clean, clean_optimizer, 300, request_document), clean_path)

    resumed, resumed_optimizer = _new_model(torch, device)
    loaded = torch.load(checkpoint_path, map_location=device, weights_only=True)
    _validate_checkpoint_identity(loaded, request_document, expected_step=120)
    resumed.load_state_dict(loaded["model"])
    resumed_optimizer.load_state_dict(loaded["optimiser"])
    _train(
        torch,
        resumed,
        resumed_optimizer,
        features,
        labels,
        start=120,
        end=300,
        ceiling=request_document["resource_ceiling"],
        started=started,
        request=request_document,
    )
    resumed_path = destination / "checkpoint-final-resumed.pt"
    torch.save(
        _checkpoint(resumed, resumed_optimizer, 300, request_document), resumed_path
    )

    shuffled_labels = labels.detach().clone()
    permutation = torch.randperm(
        len(train), generator=torch.Generator().manual_seed(20_260_821)
    ).to(device)
    shuffled_labels = shuffled_labels[permutation]
    shuffled, shuffled_optimizer = _new_model(torch, device)
    _train(
        torch,
        shuffled,
        shuffled_optimizer,
        features,
        shuffled_labels,
        start=0,
        end=300,
        ceiling=request_document["resource_ceiling"],
        started=started,
        request=request_document,
    )
    shuffled_path = destination / "checkpoint-final-shuffled.pt"
    torch.save(
        _checkpoint(shuffled, shuffled_optimizer, 300, request_document), shuffled_path
    )

    clean_accuracy = _accuracy(torch, clean, heldout_features, heldout_labels)
    shuffled_accuracy = _accuracy(torch, shuffled, heldout_features, heldout_labels)
    parameter_difference = _maximum_parameter_difference(torch, clean, resumed)
    optimiser_difference = _maximum_nested_numeric_difference(
        torch, clean_optimizer.state_dict(), resumed_optimizer.state_dict()
    )
    acceptance = {
        "clean_accuracy_at_least_0_85": clean_accuracy >= 0.85,
        "clean_advantage_at_least_0_20": clean_accuracy - shuffled_accuracy >= 0.20,
        "resume_equivalence_at_most_1e_7": max(
            parameter_difference, optimiser_difference
        )
        <= 1e-7,
    }
    metrics = {
        "schema": "sunofriend.vocal-pairwise-gpu-canary-metrics.v1",
        "request_document_sha256": request_document["document_sha256"],
        "dataset_sha256": fixture["document_sha256"],
        "clean_heldout_accuracy": clean_accuracy,
        "shuffled_heldout_accuracy": shuffled_accuracy,
        "clean_minus_shuffled_accuracy": clean_accuracy - shuffled_accuracy,
        "maximum_resume_parameter_difference": parameter_difference,
        "maximum_resume_optimiser_difference": optimiser_difference,
        "acceptance": acceptance,
        "network_attempts": network_counter["attempts"],
        "retries": 0,
        "authority": "technical_synthetic_pipeline_evidence_only",
    }
    if any(
        not math.isfinite(float(value))
        for value in (
            clean_accuracy,
            shuffled_accuracy,
            parameter_difference,
            optimiser_difference,
        )
    ):
        raise RuntimeError("pairwise GPU canary produced non-finite evidence")
    metrics["document_sha256"] = document_sha256(metrics)
    metrics_path = destination / "metrics.json"
    metrics_path.write_bytes(canonical_json_bytes(metrics))
    outputs = [
        _output_record("metrics-json", "metrics", metrics_path),
        _output_record("checkpoint-step-120", "checkpoint", checkpoint_path),
        _output_record("checkpoint-final-uninterrupted", "checkpoint", clean_path),
        _output_record("checkpoint-final-resumed", "checkpoint", resumed_path),
        _output_record("checkpoint-final-shuffled", "checkpoint", shuffled_path),
    ]
    elapsed = time.monotonic() - started
    result = build_gpu_worker_result(
        request=request_document,
        status="complete" if all(acceptance.values()) else "failed",
        environment={
            "operating_system": os.name,
            "python": __import__("sys").version.split()[0],
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
        timings={"wall_seconds": elapsed, "optimisation_steps": 300, "arms": 3},
        resources={
            "peak_gpu_bytes": int(torch.cuda.max_memory_allocated(device)),
            "peak_ram_bytes": _resident_set_bytes(),
            "output_bytes": sum(row["bytes"] for row in outputs),
        },
        training_evidence={
            "synthetic_only": True,
            "clean_heldout_accuracy": clean_accuracy,
            "shuffled_heldout_accuracy": shuffled_accuracy,
            "resume_parameter_difference": parameter_difference,
            "resume_optimiser_difference": optimiser_difference,
            "acceptance": acceptance,
            "network_attempts": network_counter["attempts"],
            "retries": 0,
        },
        warnings=[] if all(acceptance.values()) else ["technical acceptance failed"],
    )
    validate_pairwise_gpu_result(result, request=request_document)
    (destination / "gpu-worker-result.json").write_bytes(canonical_json_bytes(result))
    return result


def validate_pairwise_gpu_result(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply strict experiment-specific checks beyond the generic worker contract."""

    request_document = validate_gpu_worker_request(request)
    if request_document != build_pairwise_gpu_canary_request(
        request_document["repository_commit"]
    ):
        raise ValueError("pairwise GPU request differs from the fixed contract")
    result = validate_gpu_worker_result(value, request=request_document)
    expected = request_document["expected_outputs"]
    if [row["output_id"] for row in result["outputs"]] != [
        row["output_id"] for row in expected
    ]:
        raise ValueError("pairwise GPU output roster or order changed")
    if result["resources"].get("output_bytes") != sum(
        row["bytes"] for row in result["outputs"]
    ):
        raise ValueError("pairwise GPU output byte receipt changed")
    if (
        result["timings"].get("optimisation_steps") != 300
        or result["timings"].get("arms") != 3
    ):
        raise ValueError("pairwise GPU timing/arm receipt changed")
    environment = result["environment"]
    if (
        environment.get("network_used") is not False
        or environment.get("network_attempts") != 0
        or environment.get("downloads_used") is not False
        or environment.get("deterministic_algorithms") is not True
        or environment.get("cublas_workspace_config") != ":4096:8"
    ):
        raise ValueError("pairwise GPU result lacks offline deterministic evidence")
    evidence = result.get("training_evidence")
    required = {
        "synthetic_only",
        "clean_heldout_accuracy",
        "shuffled_heldout_accuracy",
        "resume_parameter_difference",
        "resume_optimiser_difference",
        "acceptance",
        "network_attempts",
        "retries",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != required:
        raise ValueError("pairwise GPU training evidence fields changed")
    numeric = [
        evidence["clean_heldout_accuracy"],
        evidence["shuffled_heldout_accuracy"],
        evidence["resume_parameter_difference"],
        evidence["resume_optimiser_difference"],
    ]
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in numeric
    ):
        raise ValueError("pairwise GPU training evidence must be finite")
    acceptance = {
        "clean_accuracy_at_least_0_85": evidence["clean_heldout_accuracy"] >= 0.85,
        "clean_advantage_at_least_0_20": evidence["clean_heldout_accuracy"]
        - evidence["shuffled_heldout_accuracy"]
        >= 0.20,
        "resume_equivalence_at_most_1e_7": max(
            evidence["resume_parameter_difference"],
            evidence["resume_optimiser_difference"],
        )
        <= 1e-7,
    }
    if (
        evidence["synthetic_only"] is not True
        or evidence["network_attempts"] != 0
        or evidence["retries"] != 0
        or evidence["acceptance"] != acceptance
    ):
        raise ValueError("pairwise GPU evidence or acceptance changed")
    expected_status = "complete" if all(acceptance.values()) else "failed"
    if result["status"] != expected_status:
        raise ValueError("pairwise GPU result status does not match acceptance")
    return result


def _new_model(torch: Any, device: Any) -> tuple[Any, Any]:
    torch.manual_seed(20_260_820)
    model = torch.nn.Linear(6, 1, bias=False, device=device, dtype=torch.float32)
    torch.nn.init.zeros_(model.weight)
    return model, torch.optim.SGD(model.parameters(), lr=0.2)


def _train(
    torch: Any,
    model: Any,
    optimiser: Any,
    features: Any,
    labels: Any,
    *,
    start: int,
    end: int,
    ceiling: Mapping[str, Any],
    started: float,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    loss_function = torch.nn.BCEWithLogitsLoss()
    for _step in range(start, end):
        optimiser.zero_grad(set_to_none=True)
        loss = loss_function(model(features).squeeze(1), labels)
        if not bool(torch.isfinite(loss)):
            raise RuntimeError("pairwise GPU canary produced non-finite loss")
        loss.backward()
        optimiser.step()
        if time.monotonic() - started > int(ceiling["maximum_wall_seconds"]):
            raise RuntimeError("pairwise GPU canary exceeded wall-time ceiling")
        if int(torch.cuda.max_memory_allocated()) > int(ceiling["maximum_gpu_bytes"]):
            raise RuntimeError("pairwise GPU canary exceeded GPU-memory ceiling")
        if _resident_set_bytes() > int(ceiling["maximum_ram_bytes"]):
            raise RuntimeError("pairwise GPU canary exceeded RAM ceiling")
    return _checkpoint(model, optimiser, end, request)


def _checkpoint(
    model: Any, optimiser: Any, step: int, request: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema": "sunofriend.vocal-pairwise-gpu-checkpoint.v1",
        "request_document_sha256": request["document_sha256"],
        "dataset_sha256": request["dataset"]["sha256"],
        "repository_commit": request["repository_commit"],
        "experiment_id": request["experiment_id"],
        "step": step,
        "model": model.state_dict(),
        "optimiser": optimiser.state_dict(),
        "synthetic_only": True,
    }


def _validate_checkpoint_identity(
    checkpoint: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    expected_step: int,
) -> None:
    expected = {
        "schema": "sunofriend.vocal-pairwise-gpu-checkpoint.v1",
        "request_document_sha256": request["document_sha256"],
        "dataset_sha256": request["dataset"]["sha256"],
        "repository_commit": request["repository_commit"],
        "experiment_id": request["experiment_id"],
        "step": expected_step,
        "synthetic_only": True,
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise ValueError("pairwise GPU checkpoint identity changed")
    if set(checkpoint) != {*expected, "model", "optimiser"}:
        raise ValueError("pairwise GPU checkpoint fields changed")


def _accuracy(torch: Any, model: Any, features: Any, labels: Any) -> float:
    with torch.no_grad():
        predictions = (model(features).squeeze(1) >= 0).to(labels.dtype)
        return float((predictions == labels).to(torch.float32).mean().cpu())
