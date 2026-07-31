from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

import sunofriend._separation_demucs_mlx_parity as parity
from sunofriend._separation_demucs_private_run import (
    PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA,
    _document_sha256,
)
from sunofriend.ai_mlx_separation_worker import (
    EXACT_PACKAGES,
    MODEL_SOURCE_ORDER,
    TARGETS,
    _validate_request,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


FAKE_WORKER = r"""from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np
import soundfile

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument('--request', required=True)
parser.add_argument('--arrays-root', required=True)
parser.add_argument('--result', required=True)
args = parser.parse_args()
request = json.loads(Path(args.request).read_text())
fractions = {'bass': .15, 'drums': .20, 'guitar': .10, 'other': .20, 'piano': .25, 'vocals': .10}
cases = {}
for position, case in enumerate(request['cases'], start=1):
    source, rate = soundfile.read(case['source_path'], dtype='float32', always_2d=True)
    case_dir = Path(args.arrays_root) / case['case_id']
    case_dir.mkdir()
    arrays = {}
    for role, fraction in fractions.items():
        value = (source * np.float32(fraction)).astype('float32')
        path = case_dir / f'{role}.float32.npy'
        with path.open('xb') as handle:
            np.save(handle, value, allow_pickle=False)
        arrays[role] = {
            'file': path.name,
            'sha256': sha256(path),
            'bytes': path.stat().st_size,
            'minimum': float(np.min(value)),
            'maximum': float(np.max(value)),
            'rms': float(np.sqrt(np.mean(np.square(value.astype('float64'))))),
        }
    cases[case['case_id']] = {
        'source_sha256': sha256(Path(case['source_path'])),
        'frames': int(source.shape[0]),
        'channels': int(source.shape[1]),
        'sample_rate': rate,
        'run_position': position,
        'inference_seconds': 0.25,
        'arrays': arrays,
        'source_unchanged_after_inference': True,
    }
result = {
    'schema': 'sunofriend.private-demucs-mlx-parity-worker-result.v1',
    'status': 'complete',
    'backend': 'demucs-mlx',
    'model_variant': 'htdemucs_6s',
    'model_signature': '5c90dfd2',
    'checkpoint_sha256': request['model']['checkpoint_sha256'],
    'checkpoint_hash_verified_before_deserialisation': True,
    'checkpoint_unchanged_after_inference': True,
    'packages': request['runtime']['packages'],
    'platform': {'system':'Darwin','machine':'arm64','python':'test','device':'mlx-gpu'},
    'targets': ['bass','drums','guitar','other','piano','vocals'],
    'model_source_order': ['drums','bass','other','vocals','guitar','piano'],
    'model_load_seconds': .1,
    'in_memory_conversion_seconds': .2,
    'conversion': {
        'source': 'caller-supplied hash-pinned PyTorch checkpoint',
        'named_model_resolution_called': False,
        'model_cache_api_called': False,
        'converted_weight_cache_written': False,
    },
    'inference': request['inference'],
    'cases': cases,
    'maximum_resident_set_size_native_units': 1234,
    'resource_platform': 'test',
    'effects': {
        'network_denial_enforced': False,
        'network_attempt_observation_available': False,
        'automatic_selection': False,
        'automatic_promotion': False,
        'public_result': False,
    },
}
Path(args.result).write_text(json.dumps(result, sort_keys=True) + '\n')
print(json.dumps(result, sort_keys=True))
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root: Path) -> tuple[Path, Path, Path, str]:
    root.mkdir(parents=True)
    source = root / "source-excerpt.wav"
    checkpoint = root / "5c90dfd2-34c22ccb.th"
    worker = root / "fake_mlx_worker.py"
    sample_rate = 44_100
    times = np.arange(sample_rate, dtype=np.float32) / sample_rate
    audio = np.column_stack(
        (
            0.2 * np.sin(2 * np.pi * 110.0 * times),
            0.15 * np.sin(2 * np.pi * 220.0 * times),
        )
    ).astype("float32")
    soundfile.write(source, audio, sample_rate, subtype="PCM_24")
    checkpoint.write_bytes(b"private fake checkpoint")
    worker.write_text(FAKE_WORKER, encoding="utf-8")
    return source, checkpoint, worker, _sha256(checkpoint)


def _reference(root: Path, source: Path, checkpoint_hash: str) -> Path:
    root.mkdir()
    copied_source = root / "source-excerpt.wav"
    copied_source.write_bytes(source.read_bytes())
    arrays_root = root / "MODEL-ARRAYS"
    arrays_root.mkdir()
    source_audio, _ = soundfile.read(
        copied_source, dtype="float32", always_2d=True
    )
    fractions = {
        "bass": 0.15,
        "drums": 0.20,
        "guitar": 0.10,
        "other": 0.20,
        "piano": 0.25,
        "vocals": 0.10,
    }
    estimated = {}
    for role, fraction in fractions.items():
        value = (source_audio * np.float32(fraction)).astype("float32")
        array = arrays_root / f"{role}.float32.npy"
        with array.open("xb") as handle:
            np.save(handle, value, allow_pickle=False)
        estimated[role] = {
            "model_array_sha256": _sha256(array),
            "geometry": {
                "sample_rate": 44_100,
                "channels": 2,
                "frames": len(source_audio),
                "duration_seconds": 1.0,
            },
        }
    report = {
        "schema": PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA,
        "status": "complete_review_required",
        "backend": {
            "model_variant": "htdemucs_6s",
            "model_signature": "5c90dfd2",
            "checkpoint_sha256": checkpoint_hash,
        },
        "inference": {
            "device": "cpu",
            "shifts": 0,
            "overlap": 0.25,
            "split": True,
            "num_workers": 0,
        },
        "excerpt": {
            "persisted_source": {
                "path": copied_source.name,
                "sha256": _sha256(copied_source),
            }
        },
        "estimated_stems": estimated,
        "worker_result": {"inference_seconds": 1.0},
    }
    report["document_sha256"] = _document_sha256(report)
    (root / "private-separation-experiment.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def test_read_only_plan_names_exact_install_without_installing() -> None:
    with tempfile.TemporaryDirectory() as directory:
        _, checkpoint, _, checkpoint_hash = _fixture(Path(directory) / "fixture")
        with patch.object(parity, "CHECKPOINT_SHA256", checkpoint_hash):
            plan = parity._build_private_demucs_mlx_parity_plan(
                checkpoint_path=checkpoint,
                python=sys.executable,
            )
        assert plan["read_only"] is True
        assert plan["checkpoint"]["download_required"] is False
        assert plan["runtime"]["installation_required"] is True
        assert plan["runtime"]["code_licenses"]["demucs-mlx"] == "MIT"
        assert "files.pythonhosted.org" in plan["runtime"]["network_destinations"]
        assert plan["execution"]["model_cache_read_or_write"] is False
        assert plan["execution"]["public_result"] is False


def test_private_parity_run_is_exact_inactive_and_sealed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, checkpoint, worker, checkpoint_hash = _fixture(root / "fixture")
        reference = _reference(root / "reference", source, checkpoint_hash)
        destination = root / "parity"
        ready_plan = {
            "runtime": {
                "installation_required": False,
                "exact_package_matches": {name: True for name in EXACT_PACKAGES},
            }
        }
        with (
            patch.object(parity, "CHECKPOINT_SHA256", checkpoint_hash),
            patch.object(
                parity,
                "_build_private_demucs_mlx_parity_plan",
                return_value=ready_plan,
            ),
        ):
            report = parity._run_private_demucs_mlx_parity(
                [reference],
                out_dir=destination,
                checkpoint_path=checkpoint,
                python=sys.executable,
                worker_path=worker,
            )
        assert report["status"] == "complete_review_required"
        assert report["summary"]["same_checkpoint_proven"] is True
        assert report["summary"]["separator_quality_improvement_claimed"] is False
        assert report["permissions"]["accepted"] is False
        assert report["permissions"]["simple_mode_available"] is False
        metrics = report["cases"]["case-01"]["role_metrics"]
        assert set(metrics) == set(TARGETS)
        assert all(value["maximum_absolute_error"] == 0 for value in metrics.values())
        assert all(value["correlation"] == 1.0 for value in metrics.values())
        persisted = json.loads(
            (destination / "private-demucs-mlx-parity.json").read_text()
        )
        assert persisted["document_sha256"] == _document_sha256(persisted)
        assert (destination / "ESTIMATED-STEMS/case-01/bass.wav").is_file()
        assert _sha256(checkpoint) == checkpoint_hash
        assert _sha256(reference / "source-excerpt.wav") == report[
            "reference_runs"
        ][0]["source_sha256"]


def test_worker_request_forbids_named_resolution_or_cache_conversion() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, checkpoint, _, _ = _fixture(root / "fixture")
        request = {
            "schema": "sunofriend.private-demucs-mlx-parity-request.v1",
            "backend": "demucs-mlx",
            "model": {
                "variant": "htdemucs_6s",
                "signature": "5c90dfd2",
                "checkpoint_path": str(checkpoint),
                "checkpoint_sha256": parity.CHECKPOINT_SHA256,
            },
            "runtime": {
                "packages": dict(EXACT_PACKAGES),
                "conversion": "verified-local-checkpoint-in-memory-only",
            },
            "inference": {
                "device": "mlx-gpu",
                "shifts": 0,
                "overlap": 0.25,
                "split": True,
                "num_workers": 0,
                "batch_size": 1,
            },
            "cases": [
                {
                    "case_id": "case-01",
                    "source_path": str(source),
                    "source_sha256": _sha256(source),
                    "sample_rate": 44_100,
                    "channels": 2,
                    "frames": 44_100,
                }
            ],
        }
        _validate_request(request)
        request["runtime"]["conversion"] = "named-model-auto-download"
        try:
            _validate_request(request)
        except ValueError as exc:
            assert "conversion contract" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("unsafe conversion route was accepted")


def test_private_mlx_parity_has_no_public_or_tui_route() -> None:
    forbidden = {"private-demucs-mlx-parity", "demucs-mlx"}
    assert forbidden.isdisjoint(PUBLIC_COMMANDS)
    assert forbidden.isdisjoint(DIRECT_TUI_COMMANDS)
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/sunofriend/cli.py",
        "src/sunofriend/tui.py",
        "src/sunofriend/simple_create.py",
        "src/sunofriend/workbench_server.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "_separation_demucs_mlx_parity" not in source


def test_private_mlx_script_requires_explicit_acceptance() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("SUNOFRIEND_ACCEPT_DEMUCS_MLX_PRIVATE_EVALUATION", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/private-demucs-mlx-parity.py"),
            "--reference-run",
            "/does/not/exist",
            "--out",
            "/does/not/exist-output",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "SUNOFRIEND_ACCEPT_DEMUCS_MLX_PRIVATE_EVALUATION=1" in completed.stderr


def test_source_order_is_official_and_presentation_order_is_stable() -> None:
    assert MODEL_SOURCE_ORDER == (
        "drums",
        "bass",
        "other",
        "vocals",
        "guitar",
        "piano",
    )
    assert TARGETS == ("bass", "drums", "guitar", "other", "piano", "vocals")
