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
from mido import MetaMessage, MidiFile

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


def _contains_key(value, wanted: str) -> bool:
    if isinstance(value, dict):
        return wanted in value or any(_contains_key(item, wanted) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, wanted) for item in value)
    return False


def _relative_record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


class AIMatrixTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
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
        return audio, checkpoint, worker, runs

    def _run(
        self,
        *,
        audio: Path,
        checkpoint: Path,
        worker: Path,
        runs: Path,
        run_id: str,
        roles: tuple[str, ...] = (),
        start_seconds: float = 0.0,
        end_seconds: float = 15.0,
        bpm: float = 119.0,
    ) -> Path:
        run_ai_transcription(
            audio_path=audio,
            out_dir=runs,
            checkpoint_path=checkpoint,
            bpm=bpm,
            roles=roles,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            python=sys.executable,
            worker_path=worker,
            run_id=run_id,
        )
        return runs / run_id

    def _runs(self, root: Path) -> tuple[Path, Path]:
        audio, checkpoint, worker, runs = self._fixture(root)
        m0 = self._run(
            audio=audio,
            checkpoint=checkpoint,
            worker=worker,
            runs=runs,
            run_id="m0",
        )
        m3 = self._run(
            audio=audio,
            checkpoint=checkpoint,
            worker=worker,
            runs=runs,
            run_id="m3-voice",
            roles=("voice",),
            start_seconds=30.0,
            end_seconds=45.0,
        )
        return m0, m3

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

            output = root / "matrix.json"
            written = write_ai_candidate_matrix(lanes, output)
            self.assertEqual(written, first)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), first)
            with self.assertRaises(FileExistsError):
                write_ai_candidate_matrix(lanes, output)

    def test_matrix_uses_actual_worker_excerpt_duration_for_rtf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio, checkpoint, worker, runs = self._fixture(root)
            sample_rate = 8_000
            soundfile.write(
                audio,
                np.zeros(sample_rate * 9, dtype=np.float32),
                sample_rate,
            )
            m0 = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m0-eof-clipped",
                end_seconds=15.0,
            )
            candidate_path = m0 / "candidate.json"
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["metadata"]["excerpt"]["duration_seconds"] = 9.0
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            run_path = m0 / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["artifacts"]["candidate.json"] = _relative_record(candidate_path)
            run_path.write_text(json.dumps(run), encoding="utf-8")

            report = build_ai_candidate_matrix([("M0", m0)])
            row = report["lanes"][0]

            self.assertEqual(row["duration_seconds"], 9.0)
            self.assertEqual(
                row["real_time_factor"],
                round(float(run["elapsed_seconds"]) / 9.0, 6),
            )

    def test_matrix_rejects_invalid_or_source_inconsistent_excerpt_duration(self) -> None:
        for value, message in (
            (True, "duration is invalid"),
            (9.0, "disagrees with verified source frames"),
        ):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                m0, _m3 = self._runs(root)
                candidate_path = m0 / "candidate.json"
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                candidate["metadata"]["excerpt"]["duration_seconds"] = value
                candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
                run_path = m0 / "run.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                run["artifacts"]["candidate.json"] = _relative_record(candidate_path)
                run_path.write_text(json.dumps(run), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, message):
                    build_ai_candidate_matrix([("M0", m0)])

    def test_m4_role_overlap_compares_genuine_one_role_passes_without_a_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio, checkpoint, worker, runs = self._fixture(root)
            electric_bass = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-electric-bass",
                roles=("electric_bass",),
            )
            clean_guitar = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-clean-electric-guitar",
                roles=("clean_electric_guitar",),
            )

            report = build_ai_candidate_matrix(
                [
                    ("M4-electric-bass", electric_bass),
                    ("M4-clean-electric-guitar", clean_guitar),
                ]
            )

            self.assertEqual(len(report["m4_role_overlap"]), 1)
            overlap = report["m4_role_overlap"][0]
            self.assertEqual(overlap["left_lane"], "M4-clean-electric-guitar")
            self.assertEqual(overlap["left_requested_label"], "clean_electric_guitar")
            self.assertEqual(overlap["right_lane"], "M4-electric-bass")
            self.assertEqual(overlap["right_requested_label"], "electric_bass")
            self.assertEqual(overlap["matched_notes"], 1)
            self.assertEqual(overlap["left_requested_label_count"], 1)
            self.assertEqual(overlap["left_off_role_count"], 0)
            self.assertEqual(overlap["right_requested_label_count"], 1)
            self.assertEqual(overlap["right_off_role_count"], 0)
            self.assertTrue(overlap["possible_role_collapse"])
            self.assertIn("not an accuracy score or a winner", overlap["interpretation"])
            self.assertFalse(_contains_key(report, "winner"))
            self.assertNotIn(str(root), json.dumps(report, sort_keys=True))
            self.assertFalse(report["raw_candidates_mutated"])
            self.assertEqual(report["midi_notes_mutated"], 0)

    def test_m4_rejects_non_comparable_or_non_single_role_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio, checkpoint, worker, runs = self._fixture(root)
            electric_bass = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-electric-bass",
                roles=("electric_bass",),
            )
            clean_guitar = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-clean-electric-guitar",
                roles=("clean_electric_guitar",),
            )
            duplicate_role = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-electric-bass-duplicate",
                roles=("electric_bass",),
            )
            multi_role = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-multi-role",
                roles=("electric_bass", "clean_electric_guitar"),
            )
            alias_role = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-electric-bass-alias",
                roles=("Electric Bass",),
            )
            blank_role = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-blank-role",
                roles=("   ",),
            )
            alternate_audio = root / "alternate-source.wav"
            soundfile.write(
                alternate_audio,
                np.full(8_000 * 46, 0.1, dtype=np.float32),
                8_000,
            )
            different_source = self._run(
                audio=alternate_audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-different-source",
                roles=("clean_electric_guitar",),
            )
            different_excerpt = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-different-excerpt",
                roles=("clean_electric_guitar",),
                start_seconds=30.0,
                end_seconds=45.0,
            )
            different_bpm = self._run(
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
                runs=runs,
                run_id="m4-different-bpm",
                roles=("clean_electric_guitar",),
                bpm=120.0,
            )

            cases = (
                (
                    "duplicate roles",
                    [("M4-bass-a", electric_bass), ("M4-bass-b", duplicate_role)],
                    "distinct roles",
                ),
                (
                    "multiple roles in one pass",
                    [("M4-multi", multi_role)],
                    "exactly one role",
                ),
                (
                    "canonical duplicate roles",
                    [("M4-bass-a", electric_bass), ("M4-bass-b", alias_role)],
                    "distinct roles",
                ),
                (
                    "blank role",
                    [("M4-blank", blank_role)],
                    "nonblank canonical role",
                ),
                (
                    "different source",
                    [("M4-bass", electric_bass), ("M4-guitar", different_source)],
                    "same source audio",
                ),
                (
                    "different excerpt",
                    [("M4-bass", electric_bass), ("M4-guitar", different_excerpt)],
                    "same source excerpt",
                ),
                (
                    "different BPM",
                    [("M4-bass", electric_bass), ("M4-guitar", different_bpm)],
                    "same positive BPM",
                ),
            )
            for label, lanes, message in cases:
                with self.subTest(label=label):
                    with self.assertRaisesRegex(ValueError, message):
                        build_ai_candidate_matrix(lanes)

            # The valid control demonstrates that each rejection is caused by
            # the changed comparison dimension, not by the shared fixture.
            valid = build_ai_candidate_matrix(
                [("M4-bass", electric_bass), ("M4-guitar", clean_guitar)]
            )
            self.assertEqual(len(valid["m4_role_overlap"]), 1)

    def test_matrix_rejects_tampered_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            midi = m0 / "candidate.mid"
            midi.write_bytes(midi.read_bytes() + b"tampered")

            with self.assertRaisesRegex(ValueError, "size/SHA-256"):
                build_ai_candidate_matrix([("M0", m0)])

    def test_matrix_rejects_decoy_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            decoy = m0 / "candidate-decoy.json"
            decoy.write_bytes((m0 / "candidate.json").read_bytes())
            run_path = m0 / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["artifacts"]["candidate.json"] = _relative_record(decoy)
            run_path.write_text(json.dumps(run), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "artifact path disagrees"):
                build_ai_candidate_matrix([("M0", m0)])

    def test_matrix_rejects_candidate_execution_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            run_path = m0 / "run.json"
            candidate_path = m0 / "candidate.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["metadata"]["execution"] = json.loads(
                json.dumps(run["execution"])
            )
            candidate["metadata"]["execution"]["decoding"]["beam_size"] = 2
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            run["artifacts"]["candidate.json"] = _relative_record(candidate_path)
            run_path.write_text(json.dumps(run), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError, "execution differs from pinned candidate metadata"
            ):
                build_ai_candidate_matrix([("M0", m0)])

    def test_matrix_rejects_later_tempo_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            midi_path = m0 / "candidate.mid"
            midi = MidiFile(str(midi_path))
            midi.tracks[0].insert(
                len(midi.tracks[0]) - 1,
                MetaMessage("set_tempo", tempo=500_000, time=480),
            )
            midi.save(str(midi_path))
            run_path = m0 / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["artifacts"]["candidate.mid"] = _relative_record(midi_path)
            run_path.write_text(json.dumps(run), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must have one tempo event"):
                build_ai_candidate_matrix([("M0", m0)])

    def test_matrix_binds_bpm_to_midi_and_allowlists_execution_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m0, _m3 = self._runs(root)
            run_path = m0 / "run.json"
            original = json.loads(run_path.read_text(encoding="utf-8"))

            changed = dict(original)
            changed["bpm"] = 999.0
            run_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pinned candidate MIDI"):
                build_ai_candidate_matrix([("M0", m0)])

            changed = json.loads(json.dumps(original))
            changed["execution"]["diagnostic"] = {
                "cwd": str(root / "private-working-directory"),
                "model_path": str(root / "private-model.safetensors"),
            }
            run_path.write_text(json.dumps(changed), encoding="utf-8")
            report = build_ai_candidate_matrix([("M0", m0)])
            rendered = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("diagnostic", report["execution"])
            self.assertAlmostEqual(report["lanes"][0]["bpm"], 119.0, places=3)

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
