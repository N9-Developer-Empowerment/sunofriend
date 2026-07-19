from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.ai_bakeoff import run_ai_transcription
from sunofriend.ai_matrix import (
    AI_MATRIX_SCHEMA,
    build_ai_candidate_matrix,
    write_ai_candidate_matrix,
)


_WORKER = r"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
request = json.load(open(args.request, encoding="utf-8"))
start = float(request["start_seconds"])
role = request["roles"][0] if request["roles"] else "flutes"
candidate = {
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": "muscriptor",
    "model_version": "muscriptor-test-small",
    "notes": [{
        "start_seconds": start + 5.0,
        "end_seconds": start + 5.5,
        "pitch": 64.0,
        "confidence": None,
        "instrument": role,
        "velocity": None,
        "source_event_id": "boundary-note",
    }],
    "warnings": [],
    "raw_artifacts": [],
    "metadata": {
        "checkpoint_sha256": request["options"]["model_sha256"],
        "excerpt": {
            "start_seconds": start,
            "end_seconds": request["end_seconds"],
            "duration_seconds": 15.0,
        },
    },
}
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
"""


class AIMatrixTests(unittest.TestCase):
    def _runs(self, root: Path) -> tuple[Path, Path]:
        sample_rate = 8_000
        audio = root / "source.wav"
        soundfile.write(audio, np.zeros(sample_rate * 46, dtype=np.float32), sample_rate)
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"matrix-test-checkpoint")
        (root / "config.json").write_text(
            '{"model_type":"muscriptor","variant":"small","dim":768}',
            encoding="utf-8",
        )
        worker = root / "worker.py"
        worker.write_text(textwrap.dedent(_WORKER), encoding="utf-8")
        runs = root / "runs"
        run_ai_transcription(
            audio_path=audio,
            out_dir=runs,
            checkpoint_path=checkpoint,
            bpm=119,
            start_seconds=0.0,
            end_seconds=15.0,
            python=sys.executable,
            worker_path=worker,
            run_id="m0",
        )
        run_ai_transcription(
            audio_path=audio,
            out_dir=runs,
            checkpoint_path=checkpoint,
            bpm=119,
            roles=("voice",),
            start_seconds=30.0,
            end_seconds=45.0,
            python=sys.executable,
            worker_path=worker,
            run_id="m3-voice",
        )
        return runs / "m0", runs / "m3-voice"

    def test_matrix_is_deterministic_path_free_and_uses_local_chunk_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, m3 = self._runs(root)
            lanes = [("M0", m0), ("M3-voice", m3)]

            first = build_ai_candidate_matrix(lanes)
            second = build_ai_candidate_matrix(list(reversed(lanes)))

            self.assertEqual(first, second)
            self.assertEqual(first["schema"], AI_MATRIX_SCHEMA)
            m3_row = next(row for row in first["lanes"] if row["lane"] == "M3-voice")
            boundary = m3_row["five_second_boundaries"]["boundaries"][0]
            self.assertEqual(boundary["local_seconds"], 5.0)
            self.assertEqual(boundary["source_seconds"], 35.0)
            self.assertEqual(boundary["onsets_within_tolerance"], 1)
            overlap = first["cross_lane_note_overlap"][0]
            self.assertEqual(overlap["matched_notes"], 1)
            self.assertTrue(overlap["possible_role_leakage"])
            rendered = json.dumps(first, sort_keys=True)
            self.assertNotIn(str(root), rendered)
            self.assertFalse(first["raw_candidates_mutated"])
            self.assertEqual(first["midi_notes_mutated"], 0)

            m4 = build_ai_candidate_matrix([("M0", m0), ("M4-voice", m3)])
            self.assertEqual(m4["cross_lane_note_overlap"][0]["reference_lane"], "M4-voice")
            self.assertEqual(m4["cross_lane_note_overlap"][0]["matched_notes"], 1)

            output = root / "matrix.json"
            written = write_ai_candidate_matrix(lanes, output)
            self.assertEqual(written, first)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), first)
            with self.assertRaises(FileExistsError):
                write_ai_candidate_matrix(lanes, output)

    def test_matrix_rejects_tampered_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            midi = m0 / "candidate.mid"
            midi.write_bytes(midi.read_bytes() + b"tampered")

            with self.assertRaisesRegex(ValueError, "size/SHA-256"):
                build_ai_candidate_matrix([("M0", m0)])

    def test_matrix_rejects_tampered_raw_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            raw = m0 / "candidate.raw.json"
            raw.write_bytes(raw.read_bytes() + b" ")

            with self.assertRaisesRegex(ValueError, "size/SHA-256"):
                build_ai_candidate_matrix([("M0", m0)])

    def test_matrix_recomputes_quality_instead_of_trusting_stored_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            quality_path = m0 / "candidate.quality.json"
            quality_path.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.ai-candidate-quality.v1",
                        "status": "review-required",
                        "promotion_allowed": False,
                        "metrics": {
                            "note_count": 100000,
                            "notes_per_second": 10000.0,
                            "maximum_simultaneous_notes": 10000,
                        },
                        "warnings": ["stale report"],
                    }
                ),
                encoding="utf-8",
            )
            run_path = m0 / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["artifacts"]["candidate.quality.json"] = {
                "path": "candidate.quality.json",
                "bytes": quality_path.stat().st_size,
                "sha256": hashlib.sha256(quality_path.read_bytes()).hexdigest(),
            }
            run_path.write_text(json.dumps(run), encoding="utf-8")

            report = build_ai_candidate_matrix([("M0", m0)])
            quality = report["lanes"][0]["quality"]
            self.assertTrue(quality["playable"])
            self.assertEqual(quality["severe_codes"], [])

    def test_matrix_requires_one_worker_and_execution_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, m3 = self._runs(root)
            alternate_worker = root / "alternate-worker.py"
            alternate_worker.write_text("# different worker\n", encoding="utf-8")
            run_path = m3 / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["worker"] = {
                "path": str(alternate_worker.resolve()),
                "bytes": alternate_worker.stat().st_size,
                "sha256": hashlib.sha256(alternate_worker.read_bytes()).hexdigest(),
            }
            run_path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "same pinned worker"):
                build_ai_candidate_matrix([("M0", m0), ("M3-voice", m3)])

            run = json.loads(run_path.read_text(encoding="utf-8"))
            original_worker = json.loads((m0 / "run.json").read_text(encoding="utf-8"))[
                "worker"
            ]
            run["worker"] = original_worker
            run["execution"]["decoding"]["beam_size"] = 2
            run_path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "same execution settings"):
                build_ai_candidate_matrix([("M0", m0), ("M3-voice", m3)])


if __name__ == "__main__":
    unittest.main()
