from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sunofriend._separation_demucs_demo_evaluation import (
    _best_lag,
    _document_sha256 as _evaluation_document_sha256,
    _envelope_alignment,
    _evaluate_private_demucs_demo_run,
    _si_sdr,
)
from sunofriend._separation_demucs_demo_fixture import (
    _create_private_demucs_demo_fixture,
)
from sunofriend._separation_demucs_private_run import (
    PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
    _document_sha256 as _experiment_document_sha256,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _perfect_experiment(root: Path, fixture: dict) -> Path:
    stem_dir = root / "ESTIMATED-STEMS"
    stem_dir.mkdir(parents=True)
    estimated = {}
    for role, source in fixture["reference_paths"].items():
        target = stem_dir / f"{role}.wav"
        shutil.copyfile(source, target)
        estimated[role] = {
            "path": f"ESTIMATED-STEMS/{role}.wav",
            "sha256": _sha256(target),
        }
    document = {
        "schema": PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
        "status": "complete_review_required",
        "evidence_scope": "private_development_only",
        "source": {"sha256": fixture["mixture"]["sha256"]},
        "backend": {
            "checkpoint_sha256": "a" * 64,
            "worker_sha256": "b" * 64,
        },
        "estimated_stems": estimated,
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
    }
    document["document_sha256"] = _experiment_document_sha256(document)
    path = root / "private-separation-experiment.json"
    path.write_text(json.dumps(document, sort_keys=True) + "\n")
    return path


def test_perfect_reference_copy_is_observed_without_acceptance() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _perfect_experiment(root / "experiment", fixture)
        result = _evaluate_private_demucs_demo_run(
            fixture["manifest"],
            experiment,
            out_dir=root / "evaluation",
        )

        assert result["status"] == "complete_observation_not_acceptance"
        for role in ("bass", "drums", "other"):
            metric = result["role_metrics"][role]
            assert metric["scale_invariant_sdr"]["perfect_scaled_match"] is True
            assert metric["gain_error_db"] == 0.0
            assert metric["envelope_alignment"]["estimate_lag_ms"] == 0.0
        vocals = result["role_metrics"]["vocals"]
        assert vocals["reference_active"] is False
        assert vocals["estimate_rms"] == 0.0
        assert vocals["estimate_dbfs"] is None
        assert result["downstream_midi"]["status"] == "not_run"
        assert result["permissions"]["accepted"] is False

        persisted = json.loads(Path(result["report"]).read_text())
        assert persisted["document_sha256"] == _evaluation_document_sha256(persisted)
        energy = result["energy_diagnostics"]
        assert energy[
            "sum_per_role_output_energy_to_source_energy_ratio"
        ] == pytest.approx(0.999534606072)
        assert (
            energy["sum_per_role_output_energy_to_sum_per_role_reference_energy_ratio"]
            == 1.0
        )
        assert "sum_output_energy_to_source_energy_ratio" not in energy


def test_stale_estimated_stem_hash_is_rejected_without_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _perfect_experiment(root / "experiment", fixture)
        report = json.loads(experiment.read_text())
        report["estimated_stems"]["bass"]["sha256"] = "0" * 64
        report["document_sha256"] = _experiment_document_sha256(report)
        experiment.write_text(json.dumps(report, sort_keys=True) + "\n")
        destination = root / "rejected"
        with pytest.raises(ValueError, match="bass estimate hash changed"):
            _evaluate_private_demucs_demo_run(
                fixture["manifest"],
                experiment,
                out_dir=destination,
            )
        assert not destination.exists()


def test_stale_fixture_mixture_hash_is_rejected_without_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _perfect_experiment(root / "experiment", fixture)
        source = Path(fixture["mixture_path"])
        source.write_bytes(source.read_bytes() + b"tampered")
        destination = root / "rejected"
        with pytest.raises(ValueError, match="fixture mixture hash changed"):
            _evaluate_private_demucs_demo_run(
                fixture["manifest"],
                experiment,
                out_dir=destination,
            )
        assert not destination.exists()


def test_evaluation_requires_fresh_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _perfect_experiment(root / "experiment", fixture)
        destination = root / "evaluation"
        _evaluate_private_demucs_demo_run(
            fixture["manifest"], experiment, out_dir=destination
        )
        with pytest.raises(FileExistsError, match="already exists"):
            _evaluate_private_demucs_demo_run(
                fixture["manifest"], experiment, out_dir=destination
            )


def test_zero_estimate_is_not_a_perfect_scale_invariant_match() -> None:
    reference = np.arange(1.0, 9.0, dtype=np.float64).reshape(-1, 1)
    result = _si_sdr(np.zeros_like(reference), reference, np=np)

    assert result == {
        "applicable": False,
        "reason": "estimate_has_no_energy",
        "perfect_scaled_match": False,
        "value_db": None,
        "scale": 0.0,
    }


def test_flat_envelope_alignment_is_explicitly_unavailable() -> None:
    samples = np.ones((441 * 12, 2), dtype=np.float64)
    result = _envelope_alignment(
        samples,
        samples,
        sample_rate=44_100,
        np=np,
    )

    assert result["applicable"] is False
    assert result["reason"] == "estimate_envelope_has_no_variation"
    assert result["estimate_lag_windows"] is None
    assert result["estimate_lag_ms"] is None
    assert result["correlation"] is None
    assert result["first_to_last_lag_drift_ms"] is None
    assert all(segment["applicable"] is False for segment in result["segments"])


def test_equal_alignment_correlations_prefer_zero_lag() -> None:
    periodic = np.tile(np.array([0.0, 1.0]), 100)

    result = _best_lag(periodic, periodic, np=np)

    assert result["applicable"] is True
    assert result["estimate_lag_windows"] == 0
    assert result["correlation"] == 1.0
