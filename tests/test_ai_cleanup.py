from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.ai_cleanup import AICleanupRunError, run_ai_cleanup
from sunofriend.cli import main


FAKE_WORKER = r"""from __future__ import annotations
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
parser.add_argument("--target-array", required=True)
parser.add_argument("--result", required=True)
args = parser.parse_args()
request = json.loads(Path(args.request).read_text())
source, _ = soundfile.read(
    request["source_excerpt"]["path"], dtype="float32", always_2d=True
)
target = (source * np.float32(0.4)).astype("float32")
with Path(args.target_array).open("wb") as handle:
    np.save(handle, target, allow_pickle=False)
result = {
    "schema": "sunofriend.ai-cleanup-worker-result.v1",
    "status": "complete",
    "target": request["target"],
    "checkpoint_sha256": request["model"]["checkpoint_sha256"],
    "source_excerpt_sha256": request["source_excerpt"]["sha256"],
    "target_array_sha256": sha256(args.target_array),
    "test_worker": True,
}
Path(args.result).write_text(json.dumps(result, sort_keys=True) + "\n")
print(json.dumps(result, sort_keys=True))
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AICleanupTests(unittest.TestCase):
    def _fixtures(self, root: Path) -> tuple[Path, Path, Path, str]:
        audio = root / "bass.wav"
        checkpoint = root / "955717e8-8726e21a.th"
        worker = root / "fake_worker.py"
        sample_rate = 44100
        time = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
        mono = 0.25 * np.sin(2 * np.pi * 110 * time)
        stereo = np.column_stack((mono, mono * 0.8)).astype("float32")
        soundfile.write(audio, stereo, sample_rate, subtype="PCM_24")
        checkpoint.write_bytes(b"trusted test checkpoint")
        worker.write_text(FAKE_WORKER, encoding="utf-8")
        return audio, checkpoint, worker, _sha256(checkpoint)

    def test_cleanup_is_fresh_reconstructable_and_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint, worker, checkpoint_hash = self._fixtures(root)
            runtime = {"runtime_ready": True, "test": True}
            with (
                patch(
                    "sunofriend.ai_cleanup.DEMUCS_HTDEMUCS_SHA256",
                    checkpoint_hash,
                ),
                patch(
                    "sunofriend.ai_cleanup.collect_ai_diagnostics",
                    return_value=runtime,
                ),
            ):
                first = run_ai_cleanup(
                    audio,
                    out_dir=root / "first",
                    checkpoint_path=checkpoint,
                    target="bass",
                    start_seconds=0.25,
                    end_seconds=1.75,
                    python=sys.executable,
                    worker_path=worker,
                )
                second = run_ai_cleanup(
                    audio,
                    out_dir=root / "second",
                    checkpoint_path=checkpoint,
                    target="bass",
                    start_seconds=0.25,
                    end_seconds=1.75,
                    python=sys.executable,
                    worker_path=worker,
                )

            self.assertEqual(first["status"], "complete")
            self.assertTrue(first["reconstruction"]["passed"])
            self.assertLessEqual(
                first["reconstruction"]["maximum_absolute_error"], 1e-6
            )
            self.assertFalse(first["effects"]["automatic_promotion"])
            self.assertTrue(first["effects"]["source_audio_unchanged_after_run"])
            self.assertTrue(first["effects"]["checkpoint_unchanged_after_run"])
            self.assertEqual(first["backend"]["runtime"], runtime)
            self.assertEqual(first["energy"]["target_samples_clipped_before_pcm24"], 0)
            self.assertEqual(
                first["energy"]["residual_samples_clipped_before_pcm24"], 0
            )
            for name in ("source-excerpt.wav", "target.wav", "residual.wav"):
                self.assertEqual(
                    first["artifacts"][name]["sha256"],
                    second["artifacts"][name]["sha256"],
                )
            with patch("sunofriend.ai_cleanup.DEMUCS_HTDEMUCS_SHA256", checkpoint_hash):
                with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                    run_ai_cleanup(
                        audio,
                        out_dir=root / "first",
                        checkpoint_path=checkpoint,
                        target="bass",
                        end_seconds=1.0,
                        python=sys.executable,
                        worker_path=worker,
                    )

    def test_checkpoint_hash_is_rejected_before_output_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint, worker, _ = self._fixtures(root)
            destination = root / "rejected"
            with self.assertRaisesRegex(ValueError, "checkpoint hash"):
                run_ai_cleanup(
                    audio,
                    out_dir=destination,
                    checkpoint_path=checkpoint,
                    target="bass",
                    end_seconds=1.0,
                    python=sys.executable,
                    worker_path=worker,
                )
            self.assertFalse(destination.exists())

    def test_failed_worker_preserves_immutable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint, _, checkpoint_hash = self._fixtures(root)
            worker = root / "fail.py"
            worker.write_text("raise SystemExit(7)\n", encoding="utf-8")
            destination = root / "failed"
            with (
                patch(
                    "sunofriend.ai_cleanup.DEMUCS_HTDEMUCS_SHA256",
                    checkpoint_hash,
                ),
                patch(
                    "sunofriend.ai_cleanup.collect_ai_diagnostics",
                    return_value={"runtime_ready": True},
                ),
            ):
                with self.assertRaises(AICleanupRunError):
                    run_ai_cleanup(
                        audio,
                        out_dir=destination,
                        checkpoint_path=checkpoint,
                        target="bass",
                        end_seconds=1.0,
                        python=sys.executable,
                        worker_path=worker,
                    )
            report = json.loads((destination / "ai_cleanup.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertIn("status 7", report["error"])
            self.assertTrue((destination / "request.json").is_file())
            self.assertTrue((destination / "source-excerpt.wav").is_file())

    def test_real_worker_rejects_unpinned_request_before_model_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, checkpoint, _, _ = self._fixtures(root)
            request = {
                "schema": "sunofriend.ai-cleanup-request.v1",
                "backend": "demucs",
                "model": {
                    "variant": "htdemucs",
                    "signature": "955717e8",
                    "package_version": "4.0.1",
                    "checkpoint_path": str(checkpoint),
                    "checkpoint_sha256": "0" * 64,
                },
                "source_excerpt": {
                    "path": str(audio),
                    "sha256": _sha256(audio),
                    "sample_rate": 44100,
                    "channels": 2,
                    "frames": 88200,
                },
                "target": "bass",
                "inference": {
                    "device": "cpu",
                    "shifts": 0,
                    "overlap": 0.25,
                    "split": True,
                    "num_workers": 0,
                },
            }
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            worker = (
                Path(__file__).resolve().parents[1]
                / "src"
                / "sunofriend"
                / "ai_cleanup_worker.py"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(worker),
                    "--request",
                    str(request_path),
                    "--target-array",
                    str(root / "target.npy"),
                    "--result",
                    str(root / "result.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("pinned htdemucs hash", completed.stderr)

    @patch("sunofriend.ai_cleanup.run_ai_cleanup")
    @patch("sunofriend.ai_runtime.resolve_demucs_model")
    def test_cli_routes_cleanup_controls(self, resolve_model, run_cleanup) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "bass.wav"
            audio.touch()
            model = root / "model.th"
            model.touch()
            resolve_model.return_value = model
            run_cleanup.return_value = {"status": "complete"}
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "ai-cleanup",
                        str(audio),
                        "--target",
                        "bass",
                        "--start-seconds",
                        "192",
                        "--end-seconds",
                        "208",
                        "--overlap",
                        "0.5",
                        "--out-dir",
                        str(root / "run"),
                    ]
                )
            self.assertEqual(result, 0)
            resolve_model.assert_called_once_with(None)
            arguments = run_cleanup.call_args.kwargs
            self.assertEqual(arguments["target"], "bass")
            self.assertEqual(arguments["start_seconds"], 192.0)
            self.assertEqual(arguments["end_seconds"], 208.0)
            self.assertEqual(arguments["overlap"], 0.5)


if __name__ == "__main__":
    unittest.main()
