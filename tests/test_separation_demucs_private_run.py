from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile

from sunofriend._separation_demucs_private_run import (
    _PrivateDemucsExperimentError,
    _document_sha256,
    _run_private_demucs_four_stem_experiment,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation import REAL_SEPARATION_BACKENDS_SUPPORTED
from sunofriend.separation_checkpoint_descriptor_lease import (
    CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED,
)


FAKE_FOUR_STEM_WORKER = r"""from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--stems-dir", required=True)
parser.add_argument("--result", required=True)
args = parser.parse_args()
request = json.loads(Path(args.request).read_text())
source, _ = soundfile.read(
    request["source_excerpt"]["path"], dtype="float32", always_2d=True
)
fractions = {"bass": 0.20, "drums": 0.30, "other": 0.40, "vocals": 0.10}
arrays = {}
for role in ("bass", "drums", "other", "vocals"):
    estimate = (source * np.float32(fractions[role])).astype("float32")
    path = Path(args.stems_dir) / f"{role}.float32.npy"
    with path.open("xb") as handle:
        np.save(handle, estimate, allow_pickle=False)
    arrays[role] = {
        "file": path.name,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "minimum": float(np.min(estimate)),
        "maximum": float(np.max(estimate)),
        "rms": float(np.sqrt(np.mean(np.square(estimate.astype("float64"))))),
    }
result = {
    "schema": "sunofriend.private-ai-separation-worker-result.v1",
    "status": "complete",
    "backend": "demucs",
    "package_version": "4.0.1",
    "model_variant": "htdemucs",
    "model_signature": "955717e8",
    "checkpoint_sha256": request["model"]["checkpoint_sha256"],
    "source_excerpt_sha256": request["source_excerpt"]["sha256"],
    "targets": ["bass", "drums", "other", "vocals"],
    "arrays": arrays,
    "frames": int(source.shape[0]),
    "channels": int(source.shape[1]),
    "sample_rate": 44100,
    "device": "cpu",
    "shifts": 0,
    "overlap": float(request["inference"]["overlap"]),
    "model_applications": 1,
    "inference_seconds": 0.01,
    "maximum_resident_set_size_native_units": 1234,
    "resource_platform": "test",
    "source_unchanged_after_inference": True,
    "checkpoint_unchanged_after_inference": True,
    "checkpoint_hash_verified_before_deserialisation": True,
    "effects": {
        "network_denial_enforced": False,
        "network_attempt_observation_available": False,
        "automatic_selection": False,
        "automatic_promotion": False,
        "public_result": False,
    },
}
Path(args.result).write_text(json.dumps(result, sort_keys=True) + "\n")
print(json.dumps(result, sort_keys=True))
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixtures(root: Path) -> tuple[Path, Path, Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    audio = root / "mix.wav"
    checkpoint = root / "955717e8-8726e21a.th"
    worker = root / "fake_four_stem_worker.py"
    sample_rate = 44_100
    times = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    left = 0.25 * np.sin(2 * np.pi * 110.0 * times)
    right = 0.20 * np.sin(2 * np.pi * 220.0 * times)
    soundfile.write(
        audio,
        np.column_stack((left, right)).astype("float32"),
        sample_rate,
        subtype="PCM_24",
    )
    checkpoint.write_bytes(b"trusted private-test checkpoint")
    worker.write_text(FAKE_FOUR_STEM_WORKER, encoding="utf-8")
    return audio, checkpoint, worker, _sha256(checkpoint)


def _run(
    root: Path,
    *,
    worker: Path | None = None,
) -> tuple[dict, Path, Path, Path]:
    audio, checkpoint, default_worker, checkpoint_hash = _fixtures(root)
    destination = root / "run"
    with (
        patch(
            "sunofriend._separation_demucs_private_run.DEMUCS_HTDEMUCS_SHA256",
            checkpoint_hash,
        ),
        patch(
            "sunofriend._separation_demucs_private_run.collect_ai_diagnostics",
            return_value={"runtime_ready": True, "test": True},
        ),
    ):
        report = _run_private_demucs_four_stem_experiment(
            audio,
            out_dir=destination,
            checkpoint_path=checkpoint,
            end_seconds=1.5,
            python=sys.executable,
            worker_path=worker or default_worker,
        )
    return report, destination, audio, checkpoint


def test_private_four_stem_run_is_fresh_accounted_and_review_required() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        report, destination, audio, checkpoint = _run(root)

        assert report["status"] == "complete_review_required"
        assert report["evidence_scope"] == "private_development_only"
        assert set(report["estimated_stems"]) == {
            "bass",
            "drums",
            "other",
            "vocals",
        }
        assert report["worker_result"]["model_applications"] == 1
        assert report["permissions"] == {
            "accepted": False,
            "production_eligible": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
            "simple_mode_available": False,
            "studio_import_available": False,
        }
        assert report["downstream"]["midi_evaluation_required"] is True
        assert report["downstream"]["source_graph_mutated"] is False
        closure = report["additive_accounting"]["persisted_sum_plus_residual"]
        assert closure["passed"] is True
        assert closure["maximum_absolute_error"] <= closure["threshold"]
        assert report["immutability"] == {
            "source_audio_unchanged_after_run": True,
            "request_bound_source_excerpt_unchanged_after_run": True,
            "checkpoint_unchanged_after_run": True,
            "worker_unchanged_after_run": True,
            "runtime_launcher_unchanged_after_run": True,
        }
        assert _sha256(audio) == report["source"]["sha256"]
        assert _sha256(checkpoint) == report["backend"]["checkpoint_sha256"]
        for role in ("bass", "drums", "other", "vocals"):
            stem = destination / "ESTIMATED-STEMS" / f"{role}.wav"
            assert stem.is_file() and stem.stat().st_size > 0
            assert report["estimated_stems"][role]["sha256"] == _sha256(stem)
        persisted = json.loads(
            (destination / "private-separation-experiment.json").read_text()
        )
        assert persisted["document_sha256"] == _document_sha256(persisted)
        assert (destination.stat().st_mode & 0o777) == 0o700
        for artifact in destination.rglob("*"):
            if artifact.is_file():
                assert (artifact.stat().st_mode & 0o777) == 0o600


def test_private_four_stem_run_is_repeatable_for_same_fake_worker() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first, first_root, _, _ = _run(root / "first")
        second, second_root, _, _ = _run(root / "second")
        for role in ("bass", "drums", "other", "vocals"):
            assert (
                first["estimated_stems"][role]["sha256"]
                == second["estimated_stems"][role]["sha256"]
            )
            assert _sha256(first_root / "ESTIMATED-STEMS" / f"{role}.wav") == (
                _sha256(second_root / "ESTIMATED-STEMS" / f"{role}.wav")
            )


def test_checkpoint_hash_is_rejected_before_output_creation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio, checkpoint, worker, _ = _fixtures(root)
        destination = root / "rejected"
        with pytest.raises(ValueError, match="checkpoint hash"):
            _run_private_demucs_four_stem_experiment(
                audio,
                out_dir=destination,
                checkpoint_path=checkpoint,
                end_seconds=1.0,
                python=sys.executable,
                worker_path=worker,
            )
        assert not destination.exists()


def test_partial_worker_result_fails_and_preserves_terminal_evidence() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio, checkpoint, _, checkpoint_hash = _fixtures(root)
        worker = root / "fail.py"
        worker.write_text("raise SystemExit(7)\n", encoding="utf-8")
        destination = root / "failed"
        with (
            patch(
                "sunofriend._separation_demucs_private_run.DEMUCS_HTDEMUCS_SHA256",
                checkpoint_hash,
            ),
            patch(
                "sunofriend._separation_demucs_private_run.collect_ai_diagnostics",
                return_value={"runtime_ready": True},
            ),
            pytest.raises(_PrivateDemucsExperimentError, match="status 7"),
        ):
            _run_private_demucs_four_stem_experiment(
                audio,
                out_dir=destination,
                checkpoint_path=checkpoint,
                end_seconds=1.0,
                python=sys.executable,
                worker_path=worker,
            )
        report = json.loads(
            (destination / "private-separation-experiment.json").read_text()
        )
        assert report["status"] == "failed"
        assert "status 7" in report["error"]
        assert report["document_sha256"] == _document_sha256(report)
        assert (destination / "request.json").is_file()
        assert (destination / "source-excerpt.wav").is_file()
        assert not (destination / "ESTIMATED-STEMS" / "bass.wav").exists()


def test_checkpoint_mutation_after_worker_result_removes_derived_audio() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio, checkpoint, _, checkpoint_hash = _fixtures(root)
        worker = root / "mutating_worker.py"
        worker.write_text(
            FAKE_FOUR_STEM_WORKER
            + "\nPath(request['model']['checkpoint_path']).write_bytes(b'mutated')\n",
            encoding="utf-8",
        )
        destination = root / "mutated"
        with (
            patch(
                "sunofriend._separation_demucs_private_run.DEMUCS_HTDEMUCS_SHA256",
                checkpoint_hash,
            ),
            patch(
                "sunofriend._separation_demucs_private_run.collect_ai_diagnostics",
                return_value={"runtime_ready": True},
            ),
            pytest.raises(
                _PrivateDemucsExperimentError,
                match="checkpoint changed",
            ),
        ):
            _run_private_demucs_four_stem_experiment(
                audio,
                out_dir=destination,
                checkpoint_path=checkpoint,
                end_seconds=1.0,
                python=sys.executable,
                worker_path=worker,
            )
        report = json.loads(
            (destination / "private-separation-experiment.json").read_text()
        )
        assert report["status"] == "failed"
        assert not list((destination / "ESTIMATED-STEMS").glob("*.wav"))
        assert not list((destination / "RECONSTRUCTION").iterdir())
        assert len(list((destination / "MODEL-ARRAYS").glob("*.npy"))) == 4


def test_source_excerpt_mutation_after_worker_result_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio, checkpoint, _, checkpoint_hash = _fixtures(root)
        worker = root / "source_mutating_worker.py"
        worker.write_text(
            FAKE_FOUR_STEM_WORKER
            + "\nPath(request['source_excerpt']['path']).write_bytes(b'mutated')\n",
            encoding="utf-8",
        )
        destination = root / "mutated"
        with (
            patch(
                "sunofriend._separation_demucs_private_run.DEMUCS_HTDEMUCS_SHA256",
                checkpoint_hash,
            ),
            patch(
                "sunofriend._separation_demucs_private_run.collect_ai_diagnostics",
                return_value={"runtime_ready": True},
            ),
            pytest.raises(
                _PrivateDemucsExperimentError,
                match="request-bound source excerpt changed",
            ),
        ):
            _run_private_demucs_four_stem_experiment(
                audio,
                out_dir=destination,
                checkpoint_path=checkpoint,
                end_seconds=1.0,
                python=sys.executable,
                worker_path=worker,
            )
        report = json.loads(
            (destination / "private-separation-experiment.json").read_text()
        )
        assert report["status"] == "failed"
        assert not list((destination / "ESTIMATED-STEMS").glob("*.wav"))
        assert len(list((destination / "MODEL-ARRAYS").glob("*.npy"))) == 4


def test_clipped_audition_sum_cannot_create_false_accounting_pass() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        worker = root / "oversummed_worker.py"
        worker.write_text(
            FAKE_FOUR_STEM_WORKER.replace(
                'fractions = {"bass": 0.20, "drums": 0.30, '
                '"other": 0.40, "vocals": 0.10}',
                'fractions = {"bass": 2.0, "drums": 2.0, "other": 2.0, "vocals": 2.0}',
            ),
            encoding="utf-8",
        )
        report, destination, _, _ = _run(root, worker=worker)

        accounting = report["additive_accounting"]
        assert (
            accounting["persisted_sum"]["samples_outside_pcm_range_before_persistence"]
            > 0
        )
        assert accounting["persisted_sum"]["purpose"] == "audition_only"
        assert accounting["persisted_sum"]["used_for_accounting"] is False
        residual = accounting["source_minus_estimated_sum"]
        assert residual["pcm24_persisted"] is False
        assert residual["path"].endswith(".float64.npy")
        closure = accounting["persisted_sum_plus_residual"]
        assert closure["available"] is False
        assert closure["passed"] is False
        assert closure["maximum_absolute_error"] is None
        assert not (
            destination / "RECONSTRUCTION" / "source-minus-estimated-sum.wav"
        ).exists()


def test_array_directory_rejects_extra_directory_entries() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio, checkpoint, _, checkpoint_hash = _fixtures(root)
        worker = root / "extra_directory_worker.py"
        worker.write_text(
            FAKE_FOUR_STEM_WORKER + "\n(Path(args.stems_dir) / 'unexpected').mkdir()\n",
            encoding="utf-8",
        )
        destination = root / "extra"
        with (
            patch(
                "sunofriend._separation_demucs_private_run.DEMUCS_HTDEMUCS_SHA256",
                checkpoint_hash,
            ),
            patch(
                "sunofriend._separation_demucs_private_run.collect_ai_diagnostics",
                return_value={"runtime_ready": True},
            ),
            pytest.raises(
                _PrivateDemucsExperimentError,
                match="only regular non-link files",
            ),
        ):
            _run_private_demucs_four_stem_experiment(
                audio,
                out_dir=destination,
                checkpoint_path=checkpoint,
                end_seconds=1.0,
                python=sys.executable,
                worker_path=worker,
            )
        report = json.loads(
            (destination / "private-separation-experiment.json").read_text()
        )
        assert report["status"] == "failed"


def test_private_runner_has_no_public_or_tui_route() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {
        "private-demucs-four-stem",
        "private-separation-experiment",
    }
    assert REAL_SEPARATION_BACKENDS_SUPPORTED is False
    assert CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED is False
    assert forbidden.isdisjoint(PUBLIC_COMMANDS)
    assert forbidden.isdisjoint(DIRECT_TUI_COMMANDS)
    for relative in (
        "src/sunofriend/cli.py",
        "src/sunofriend/tui.py",
        "src/sunofriend/tui_conversion.py",
        "src/sunofriend/tui_model.py",
        "src/sunofriend/simple_create.py",
        "src/sunofriend/workbench_server.py",
        "src/sunofriend/__init__.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "_separation_demucs_private_run" not in source


def test_output_path_is_never_reused() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _, destination, audio, checkpoint = _run(root)
        with pytest.raises(FileExistsError, match="will not be overwritten"):
            _run_private_demucs_four_stem_experiment(
                audio,
                out_dir=destination,
                checkpoint_path=checkpoint,
                end_seconds=1.0,
                python=sys.executable,
            )
