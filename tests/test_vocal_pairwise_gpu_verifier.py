from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from sunofriend.audio_formats import file_sha256
from sunofriend.gpu_worker_contract import build_gpu_worker_result
from sunofriend.source_receipt import canonical_json_bytes, document_sha256
from sunofriend.vocal_pairwise_gpu_canary import build_pairwise_gpu_canary_request
from sunofriend.vocal_pairwise_gpu_verifier import (
    OUTPUT_FILENAMES,
    VERIFICATION_SCHEMA,
    verify_pairwise_gpu_canary_round_trip,
)
import sunofriend.vocal_pairwise_gpu_verifier as verifier_module


class _FakeTensor:
    def __init__(self, values: list[float], *, shape: tuple[int, ...]) -> None:
        self._values = list(values)
        self.shape = shape
        self.dtype = "torch.float32"

    def detach(self) -> _FakeTensor:
        return self

    def cpu(self) -> _FakeTensor:
        return self

    def reshape(self, *_shape: int) -> _FakeTensor:
        return _FakeTensor(self._values, shape=(len(self._values),))

    def tolist(self) -> list[float]:
        return list(self._values)


def test_verifier_uses_restricted_cpu_loader_and_has_no_training_or_network() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            repository / "src/sunofriend/vocal_pairwise_gpu_verifier.py",
            repository / "scripts/verify-vocal-pairwise-gpu-canary.py",
        )
    )
    assert 'torch.load(path, weights_only=True, map_location="cpu")' in source
    for forbidden in (
        "run_pairwise_gpu_canary",
        "torch.optim",
        "loss.backward",
        "pip install",
        "urllib.request",
        "requests.",
    ):
        assert forbidden not in source


def test_round_trip_is_read_only_path_free_and_recomputes_checkpoint_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir, checkpoints = _round_trip(tmp_path, commit)
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    before = {
        path.relative_to(tmp_path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    verification = verify_pairwise_gpu_canary_round_trip(
        request_path,
        artifact_dir=artifact_dir,
        repository_root=repository,
    )

    after = {
        path.relative_to(tmp_path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before
    assert verification["schema"] == VERIFICATION_SCHEMA
    assert verification["status"] == "verified_synthetic_technical_evidence_only"
    assert verification["repository_commit"] == commit
    assert [row["output_id"] for row in verification["outputs"]] == list(
        OUTPUT_FILENAMES
    )
    assert verification["recomputed_evidence"] == {
        "clean_heldout_accuracy": 1.0,
        "resumed_heldout_accuracy": 1.0,
        "shuffled_heldout_accuracy": 0.5625,
        "clean_minus_shuffled_accuracy": 0.4375,
        "maximum_resume_parameter_difference": 0.0,
        "maximum_resume_optimiser_difference": 0.0,
        "acceptance": {
            "clean_accuracy_at_least_0_85": True,
            "clean_advantage_at_least_0_20": True,
            "resume_equivalence_at_most_1e_7": True,
        },
    }
    assert all(verification["checks"].values())
    assert verification["authority"]["musical_selection"] is False
    assert verification["document_sha256"] == document_sha256(
        {key: value for key, value in verification.items() if key != "document_sha256"}
    )


def test_verifier_rejects_extra_tampered_and_path_leaking_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir, checkpoints = _round_trip(tmp_path, commit)
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    (artifact_dir / "worker.log").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="roster"):
        verify_pairwise_gpu_canary_round_trip(
            request_path, artifact_dir=artifact_dir, repository_root=repository
        )

    request_path, artifact_dir, checkpoints = _round_trip(
        tmp_path, commit, name="tampered"
    )
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    target = artifact_dir / OUTPUT_FILENAMES["checkpoint-final-shuffled"]
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="size"):
        verify_pairwise_gpu_canary_round_trip(
            request_path, artifact_dir=artifact_dir, repository_root=repository
        )

    request_path, artifact_dir, checkpoints = _round_trip(tmp_path, commit, name="path")
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    result_path = artifact_dir / "gpu-worker-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["warnings"] = [r"C:\Users\person\private"]
    _rehash(result)
    result_path.write_bytes(canonical_json_bytes(result))
    with pytest.raises(ValueError, match="paths"):
        verify_pairwise_gpu_canary_round_trip(
            request_path, artifact_dir=artifact_dir, repository_root=repository
        )


def test_verifier_rejects_checkpoint_identity_metrics_and_repository_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir, checkpoints = _round_trip(tmp_path, commit)
    checkpoints["checkpoint-step-120.pt"]["step"] = 121
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    with pytest.raises(ValueError, match="identity or step"):
        verify_pairwise_gpu_canary_round_trip(
            request_path, artifact_dir=artifact_dir, repository_root=repository
        )

    request_path, artifact_dir, checkpoints = _round_trip(tmp_path, commit, name="nan")
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    metrics_path = artifact_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["clean_heldout_accuracy"] = "nan"
    _rehash(metrics)
    metrics_path.write_bytes(canonical_json_bytes(metrics))
    _bind_output(artifact_dir, "metrics-json", metrics_path)
    with pytest.raises(ValueError, match="finite"):
        verify_pairwise_gpu_canary_round_trip(
            request_path, artifact_dir=artifact_dir, repository_root=repository
        )

    request_path, artifact_dir, checkpoints = _round_trip(
        tmp_path, commit, name="dirty-repo"
    )
    monkeypatch.setattr(
        verifier_module,
        "_load_checkpoint_weights_only",
        lambda path: checkpoints[path.name],
    )
    (repository / "tracked.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="tracked files"):
        verify_pairwise_gpu_canary_round_trip(
            request_path, artifact_dir=artifact_dir, repository_root=repository
        )


def _round_trip(
    tmp_path: Path, commit: str, *, name: str = "round-trip"
) -> tuple[Path, Path, dict[str, dict[str, Any]]]:
    request = build_pairwise_gpu_canary_request(commit)
    request_path = tmp_path / f"{name}-request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    artifact_dir = tmp_path / f"{name}-artifacts"
    artifact_dir.mkdir()

    clean_weights = [1.5, -1.0, 0.8, 0.4, -0.6, 0.2]
    shuffled_weights = [0.0] * 6
    checkpoints: dict[str, dict[str, Any]] = {}
    for output_id, filename in OUTPUT_FILENAMES.items():
        if output_id == "metrics-json":
            continue
        step = 120 if output_id == "checkpoint-step-120" else 300
        weights = (
            shuffled_weights
            if output_id == "checkpoint-final-shuffled"
            else clean_weights
        )
        checkpoints[filename] = {
            "schema": "sunofriend.vocal-pairwise-gpu-checkpoint.v1",
            "request_document_sha256": request["document_sha256"],
            "dataset_sha256": request["dataset"]["sha256"],
            "repository_commit": commit,
            "experiment_id": request["experiment_id"],
            "step": step,
            "model": {"weight": _FakeTensor(weights, shape=(1, 6))},
            "optimiser": {"state": {}, "param_groups": [{"lr": 0.2, "params": [0]}]},
            "synthetic_only": True,
        }
        (artifact_dir / filename).write_bytes(f"synthetic:{filename}".encode())

    acceptance = {
        "clean_accuracy_at_least_0_85": True,
        "clean_advantage_at_least_0_20": True,
        "resume_equivalence_at_most_1e_7": True,
    }
    metrics = {
        "schema": "sunofriend.vocal-pairwise-gpu-canary-metrics.v1",
        "request_document_sha256": request["document_sha256"],
        "dataset_sha256": request["dataset"]["sha256"],
        "clean_heldout_accuracy": 1.0,
        "shuffled_heldout_accuracy": 0.5625,
        "clean_minus_shuffled_accuracy": 0.4375,
        "maximum_resume_parameter_difference": 0.0,
        "maximum_resume_optimiser_difference": 0.0,
        "acceptance": acceptance,
        "network_attempts": 0,
        "retries": 0,
        "authority": "technical_synthetic_pipeline_evidence_only",
    }
    metrics["document_sha256"] = document_sha256(metrics)
    (artifact_dir / "metrics.json").write_bytes(canonical_json_bytes(metrics))

    expected = {row["output_id"]: row for row in request["expected_outputs"]}
    outputs = []
    for output_id, filename in OUTPUT_FILENAMES.items():
        path = artifact_dir / filename
        outputs.append(
            {
                "output_id": output_id,
                "kind": expected[output_id]["kind"],
                "media_type": expected[output_id]["media_type"],
                "shape": expected[output_id]["shape"],
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    result = build_gpu_worker_result(
        request=request,
        status="complete",
        environment={
            "operating_system": "nt",
            "python": "3.12.0",
            "torch": "2.8.0",
            "cuda_runtime": "12.8",
            "gpu": "synthetic-test-device",
            "deterministic_algorithms": True,
            "cublas_workspace_config": ":4096:8",
            "network_used": False,
            "network_attempts": 0,
            "downloads_used": False,
        },
        outputs=outputs,
        timings={"wall_seconds": 1.0, "optimisation_steps": 300, "arms": 3},
        resources={
            "peak_gpu_bytes": 1024,
            "peak_ram_bytes": 2048,
            "output_bytes": sum(row["bytes"] for row in outputs),
        },
        training_evidence={
            "synthetic_only": True,
            "clean_heldout_accuracy": 1.0,
            "shuffled_heldout_accuracy": 0.5625,
            "resume_parameter_difference": 0.0,
            "resume_optimiser_difference": 0.0,
            "acceptance": acceptance,
            "network_attempts": 0,
            "retries": 0,
        },
    )
    (artifact_dir / "gpu-worker-result.json").write_bytes(canonical_json_bytes(result))
    return request_path, artifact_dir, checkpoints


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "synthetic@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Synthetic Test"],
        cwd=repository,
        check=True,
    )
    (repository / "tracked.txt").write_text("exact", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repository, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, commit


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _bind_output(artifact_dir: Path, output_id: str, target: Path) -> None:
    result_path = artifact_dir / "gpu-worker-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for output in result["outputs"]:
        if output["output_id"] == output_id:
            output["bytes"] = target.stat().st_size
            output["sha256"] = file_sha256(target)
    result["resources"]["output_bytes"] = sum(
        int(row["bytes"]) for row in result["outputs"]
    )
    _rehash(result)
    result_path.write_bytes(canonical_json_bytes(result))
