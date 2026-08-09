import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_runner_is_single_use_tensor_only_and_json_only() -> None:
    source = (
        ROOT / "scripts/run-separation-other-refinement-next-synthetic.py"
    ).read_text()
    assert source.count("loaded.model(mx.array(generated))") == 1
    assert "guard.record_forward()" in source
    assert "--accept-approved-generated-tensor-forward" in source
    assert (
        "soundfile" not in source
        and "librosa" not in source
        and "torchaudio" not in source
    )
    assert ".wav" not in source and ".flac" not in source
    assert 'automatic_retry": False' in source


def test_existing_load_guard_still_defaults_to_zero_forward_authority() -> None:
    source = (
        ROOT / "src/sunofriend/separation_other_refinement_next_execution_guard.py"
    ).read_text()
    assert "expected_forward_calls: int = 0" in source
    assert "self.forward_calls != self.expected_forward_calls" in source


def test_report_validation_does_not_require_mlx(tmp_path: Path) -> None:
    report = tmp_path / "SYNTHETIC-REPORT.json"
    report.write_text(
        json.dumps(
            {
                "schema": "sunofriend.mega53-generated-tensor-forward-report.v1",
                "report_sha256": (
                    "07d8af0ccd913914f509a75015476c9a0efe85bb89639514032c138420ec3f10"
                ),
                "status": "objective_pass",
                "profile_id": "bs-roformer-mega-53-synth-v1",
                "plan_sha256": (
                    "1ac15c7082223fcf2bdfd1d7443320f782cae87b8ac6e89cf991c19553da9903"
                ),
                "model_load_report_sha256": (
                    "798b5250eacf18d3f6193fde9d5c613ee68520490aed663395313a47eea4d666"
                ),
                "guards": {
                    "audio_open_attempts": 0,
                    "external_checkpoint_open_attempts": 0,
                    "forward_calls": 1,
                    "network_attempts": 0,
                    "os_network_denial_required": True,
                    "restricted_torch_load_calls": 1,
                },
                "result": {
                    "all_samples_finite": True,
                    "elapsed_seconds": 18.186591000063345,
                    "failure": None,
                    "forward_completed": True,
                    "maximum_reconstruction_error": 9.313225746154785e-10,
                    "output_dtype": "float32",
                    "output_shape": [1, 53, 2, 881664],
                    "peak_mlx_memory_bytes": 15424362972,
                    "residual_peak": 0.02885768562555313,
                    "synth_peak": 0.1837383657693863,
                    "synth_role": "synth",
                    "synth_role_index": 38,
                },
                "effects": {
                    "audio_reads": 0,
                    "audio_writes": 0,
                    "automatic_retry": False,
                    "hosting": False,
                    "inference_attempts": 1,
                    "midi_created": False,
                    "persisted_audio": False,
                    "public_activation": False,
                    "redistribution": False,
                    "source_selection": False,
                },
            }
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run-separation-other-refinement-next-synthetic.py"),
            "--validate-report",
            str(report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["status"] == "objective_pass"
