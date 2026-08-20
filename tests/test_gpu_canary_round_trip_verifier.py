from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from sunofriend.audio_formats import file_sha256
from sunofriend.gpu_canary import build_c0_canary_request
from sunofriend.gpu_canary_verifier import (
    OUTPUT_FILENAMES,
    VERIFICATION_SCHEMA,
    verify_c0_canary_round_trip,
)
from sunofriend.gpu_worker_contract import build_gpu_worker_result
from sunofriend.source_receipt import canonical_json_bytes, document_sha256


def test_verifier_source_has_no_training_install_download_or_checkpoint_load() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            repository / "src/sunofriend/gpu_canary_verifier.py",
            repository / "scripts/verify-gpu-canary-round-trip.py",
        )
    )
    for forbidden in (
        "run_c0_canary",
        "torch.load",
        "pip install",
        'subprocess.run(["curl"',
        "urllib.request",
        "requests.",
    ):
        assert forbidden not in source


def test_round_trip_verifier_is_read_only_path_free_and_hash_bound(
    tmp_path: Path,
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir = _round_trip(tmp_path, commit)
    before = {
        path.relative_to(tmp_path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    verification = verify_c0_canary_round_trip(
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
    assert verification["status"] == "verified_technical_evidence_only"
    assert verification["repository_commit"] == commit
    assert [row["output_id"] for row in verification["outputs"]] == list(
        OUTPUT_FILENAMES
    )
    assert all(verification["checks"].values())
    assert verification["authority"] == {
        "technical_verification_only": True,
        "musical_selection": False,
        "representation_admitted": False,
        "checkpoint_promoted": False,
        "product_changed": False,
    }
    assert "/" not in json.dumps(verification["authority"])
    assert verification["document_sha256"] == document_sha256(
        {key: value for key, value in verification.items() if key != "document_sha256"}
    )


def test_cli_accepts_a_separately_preserved_exact_commit_checkout(
    tmp_path: Path,
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir = _round_trip(tmp_path, commit)
    script = (
        Path(__file__).resolve().parents[1] / "scripts/verify-gpu-canary-round-trip.py"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--repository-root",
            str(repository),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    verification = json.loads(completed.stdout)
    assert verification["repository_commit"] == commit
    assert verification["status"] == "verified_technical_evidence_only"
    assert str(repository) not in completed.stdout


def test_round_trip_verifier_rejects_tampered_or_symlinked_artifact(
    tmp_path: Path,
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir = _round_trip(tmp_path, commit)
    target = artifact_dir / OUTPUT_FILENAMES["checkpoint-final-resumed"]
    target.write_bytes(target.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="size"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )

    request_path, artifact_dir = _round_trip(tmp_path, commit, name="second")
    target = artifact_dir / OUTPUT_FILENAMES["checkpoint-final-resumed"]
    original = artifact_dir / "unlisted-copy.pt"
    original.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(original)
    with pytest.raises(ValueError, match="regular file"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )


def test_round_trip_verifier_rejects_repository_mismatch_and_tracked_changes(
    tmp_path: Path,
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir = _round_trip(tmp_path, commit)
    other_repository, _ = _repository(tmp_path, name="other-repository")

    with pytest.raises(ValueError, match="HEAD"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=other_repository,
        )

    (repository / "tracked.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="tracked files"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )


def test_round_trip_verifier_rejects_path_leak_and_online_evidence(
    tmp_path: Path,
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir = _round_trip(tmp_path, commit)
    result_path = artifact_dir / "gpu-worker-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["warnings"] = [r"worker log at C:\Users\person\private"]
    _rehash(result)
    result_path.write_bytes(canonical_json_bytes(result))

    with pytest.raises(ValueError, match="absolute paths"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )

    request_path, artifact_dir = _round_trip(tmp_path, commit, name="online")
    result_path = artifact_dir / "gpu-worker-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["environment"]["network_used"] = True
    _rehash(result)
    result_path.write_bytes(canonical_json_bytes(result))
    with pytest.raises(ValueError, match="network was not used"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )


def test_round_trip_verifier_rejects_non_finite_or_unbound_metrics(
    tmp_path: Path,
) -> None:
    repository, commit = _repository(tmp_path)
    request_path, artifact_dir = _round_trip(
        tmp_path,
        commit,
        metrics_change={"clean_heldout_accuracy": math.nan},
    )
    with pytest.raises(ValueError, match="finite"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )

    request_path, artifact_dir = _round_trip(
        tmp_path,
        commit,
        name="unbound",
        metrics_change={"request_document_sha256": "f" * 64},
    )
    with pytest.raises(ValueError, match="request_document_sha256"):
        verify_c0_canary_round_trip(
            request_path,
            artifact_dir=artifact_dir,
            repository_root=repository,
        )


def _repository(tmp_path: Path, *, name: str = "repository") -> tuple[Path, str]:
    repository = tmp_path / name
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / "tracked.txt").write_text(name, encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Sunofriend Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, commit


def _round_trip(
    tmp_path: Path,
    commit: str,
    *,
    name: str = "round-trip",
    metrics_change: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    root = tmp_path / name
    root.mkdir()
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir()
    request = build_c0_canary_request(commit)
    request_path = root / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))

    metrics = _metrics(request)
    if metrics_change:
        metrics.update(metrics_change)
    if any(
        isinstance(value, float) and not math.isfinite(value)
        for value in metrics.values()
    ):
        metrics["document_sha256"] = "0" * 64
    else:
        _rehash(metrics)
    metrics_path = artifact_dir / OUTPUT_FILENAMES["metrics-json"]
    metrics_path.write_text(
        json.dumps(metrics, allow_nan=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    for output_id, filename in OUTPUT_FILENAMES.items():
        if output_id != "metrics-json":
            (artifact_dir / filename).write_bytes(
                (output_id + "-opaque-checkpoint").encode("ascii")
            )
    outputs = []
    for expected in request["expected_outputs"]:
        path = artifact_dir / OUTPUT_FILENAMES[expected["output_id"]]
        outputs.append(
            {
                **expected,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    result = build_gpu_worker_result(
        request=request,
        status="complete",
        environment={
            "operating_system": "win32",
            "python": "3.11.9",
            "torch": "2.8.0",
            "cuda_runtime": "12.8",
            "gpu": "RTX 4080 Laptop GPU",
            "deterministic_algorithms": True,
            "cublas_workspace_config": ":4096:8",
            "network_used": False,
            "network_attempts": 0,
            "downloads_used": False,
        },
        outputs=outputs,
        timings={"wall_seconds": 12.5, "optimisation_steps": 200, "arms": 3},
        resources={
            "peak_gpu_bytes": 1_000_000_000,
            "peak_ram_bytes": 2_000_000_000,
            "output_bytes": sum(row["bytes"] for row in outputs),
        },
        training_evidence=_training_evidence(request),
    )
    (artifact_dir / "gpu-worker-result.json").write_bytes(canonical_json_bytes(result))
    return request_path, artifact_dir


def _training_evidence(request: dict[str, Any]) -> dict[str, Any]:
    train_ids = [f"composition-{index:02d}" for index in range(12)]
    heldout_ids = [f"composition-{index:02d}" for index in range(12, 16)]
    return {
        "dataset": {
            "sha256": request["dataset"]["sha256"],
            "generation_seed": 1729,
            "dtype": "float32",
            "train_shape": [192, 16],
            "heldout_shape": [64, 16],
            "train_group_ids": train_ids,
            "heldout_group_ids": heldout_ids,
            "train_composition_ids": train_ids,
            "heldout_composition_ids": heldout_ids,
        },
        "model": {
            key: request["model"][key]
            for key in (
                "architecture",
                "input_features",
                "hidden_features",
                "output_features",
                "parameter_dtype",
            )
        },
        "execution": dict(request["training"]) | {"network_attempts": 0, "retries": 0},
        "arms": [
            {
                "arm_id": "clean_uninterrupted",
                "steps": 200,
                "final_loss": 0.002,
                "heldout_accuracy": 0.96,
                "finite_losses": True,
            },
            {
                "arm_id": "clean_resumed",
                "steps": 200,
                "final_loss": 0.002,
                "heldout_accuracy": 0.96,
                "finite_losses": True,
            },
            {
                "arm_id": "shuffled_label_control",
                "steps": 200,
                "final_loss": 0.85,
                "heldout_accuracy": 0.52,
                "finite_losses": True,
            },
        ],
        "resume_equivalence": {
            "maximum_parameter_difference": 0.0,
            "maximum_optimiser_difference": 0.0,
            "tolerance": 1e-7,
            "passed": True,
        },
        "acceptance": {
            "clean_accuracy_at_least_0_90": True,
            "clean_advantage_at_least_0_20": True,
            "resume_equivalence_at_most_1e_7": True,
        },
    }


def _metrics(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "sunofriend.gpu-canary-metrics.v1",
        "experiment_id": request["experiment_id"],
        "request_document_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "dataset_sha256": request["dataset"]["sha256"],
        "clean_heldout_accuracy": 0.96,
        "shuffled_heldout_accuracy": 0.52,
        "clean_minus_shuffled_accuracy": 0.43999999999999995,
        "resume_max_abs_parameter_difference": 0.0,
        "resume_max_abs_optimiser_difference": 0.0,
        "curves": {
            "clean_uninterrupted": [{"step": 200, "loss": 0.002}],
            "clean_resumed": [{"step": 200, "loss": 0.002}],
            "shuffled_control": [{"step": 200, "loss": 0.85}],
        },
        "pipeline_acceptance": {
            "clean_accuracy_at_least_0_90": True,
            "clean_advantage_at_least_0_20": True,
            "resume_equivalence_at_most_1e_7": True,
        },
        "authority": "technical_research_challenger_only",
        "network_attempts": 0,
        "retries": 0,
    }


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
