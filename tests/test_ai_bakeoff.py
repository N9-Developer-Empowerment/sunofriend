from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.ai_bakeoff import (
    AI_GM_PROGRAM_MAPPING_SCHEMA,
    AI_RUN_SCHEMA,
    AIWorkerRunError,
    _candidate_tracks,
    run_ai_transcription,
)
from sunofriend.ai_expression import (
    AI_EXPRESSION_SCHEMA,
    expression_velocities,
    recover_source_expression,
)
from sunofriend.ai_quality import AI_QUALITY_SCHEMA, assess_candidate_quality
from sunofriend.ai_worker import _game_notes, _rmvpe_frames_to_notes
from sunofriend.ai_runtime import (
    AI_CANDIDATE_SCHEMA,
    AI_REQUEST_SCHEMA,
    AITranscriptionCandidate,
    AITranscriptionNote,
)


SUCCESS_WORKER = r"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
request = json.load(open(args.request, encoding="utf-8"))
candidate = {
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": request["backend"],
    "model_version": "fake-1/checkpoint-test",
    "notes": [{
        "start_seconds": 0.25,
        "end_seconds": 0.75,
        "pitch": 64.25,
        "confidence": None,
        "instrument": "lead vocal",
        "velocity": None,
        "source_event_id": "fake-0",
    }],
    "warnings": ["synthetic worker"],
    "raw_artifacts": [],
    "metadata": {
        "fixture": True,
        "checkpoint_sha256": request["options"]["model_sha256"],
    },
}
if request["backend"] == "rmvpe":
    frames = open(
        __import__("pathlib").Path(args.output).with_name("rmvpe.frames.json"),
        "w",
        encoding="utf-8",
    )
    json.dump({"schema": "sunofriend.rmvpe-f0-frames.v1", "frames": []}, frames)
    frames.close()
    candidate["raw_artifacts"] = ["rmvpe.frames.json"]
if request["backend"] == "pesto":
    from pathlib import Path
    frames_path = Path(args.output).with_name("pesto.frames.json")
    activations_path = Path(args.output).with_name("pesto.activations.npy")
    frames_path.write_text(
        '{"schema":"sunofriend.pesto-f0-frames.v1","frames":[]}',
        encoding="utf-8",
    )
    activations_path.write_bytes(b"synthetic numpy evidence")
    candidate["raw_artifacts"] = [
        "pesto.frames.json",
        "pesto.activations.npy",
    ]
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
print("synthetic worker complete")
"""


FAILURE_WORKER = r"""
import sys
print("synthetic model failure", file=sys.stderr)
raise SystemExit(7)
"""


TIMEOUT_WORKER = r"""
import time
time.sleep(10)
"""


class AIBakeoffTests(unittest.TestCase):
    def _fixture(self, directory: str, worker_source: str):
        root = Path(directory)
        audio = root / "excerpt.wav"
        sample_rate = 16_000
        times = np.arange(sample_rate, dtype=np.float32) / sample_rate
        signal = 0.2 * np.sin(2.0 * np.pi * 220.0 * times)
        soundfile.write(audio, signal, sample_rate)
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"synthetic checkpoint evidence")
        worker = root / "worker.py"
        worker.write_text(textwrap.dedent(worker_source), encoding="utf-8")
        return audio, checkpoint, worker

    def _game_bundle(self, root: Path) -> Path:
        bundle = root / "game-onnx"
        bundle.mkdir()
        (bundle / "config.json").write_text(
            '{"samplerate":44100,"timestep":0.01}', encoding="utf-8"
        )
        for name in (
            "encoder.onnx",
            "segmenter.onnx",
            "estimator.onnx",
            "dur2bd.onnx",
            "bd2dur.onnx",
        ):
            (bundle / name).write_bytes(f"synthetic {name}".encode())
        return bundle

    def test_success_preserves_raw_normalized_midi_logs_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, checkpoint, worker = self._fixture(directory, SUCCESS_WORKER)
            output = Path(directory) / "runs"
            result = run_ai_transcription(
                audio_path=audio,
                out_dir=output,
                checkpoint_path=checkpoint,
                bpm=119,
                roles=("lead vocal",),
                python=sys.executable,
                worker_path=worker,
                run_id="fixture-success",
            )

            run_dir = output / "fixture-success"
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            request = json.loads(
                (run_dir / "request.json").read_text(encoding="utf-8")
            )
            candidate = json.loads(
                (run_dir / "candidate.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["schema"], AI_RUN_SCHEMA)
            self.assertEqual(saved["status"], "complete")
            self.assertEqual(saved["note_count"], 1)
            self.assertEqual(request["schema"], AI_REQUEST_SCHEMA)
            self.assertEqual(request["roles"], ["lead vocal"])
            self.assertEqual(candidate["schema"], AI_CANDIDATE_SCHEMA)
            self.assertEqual(
                candidate["manifest"]["weights_license"], "CC-BY-NC-4.0"
            )
            self.assertEqual(
                saved["source"]["sha256"], hashlib.sha256(audio.read_bytes()).hexdigest()
            )
            self.assertEqual(
                saved["checkpoint"]["sha256"],
                hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            )
            self.assertTrue((run_dir / "candidate.raw.json").is_file())
            self.assertEqual((run_dir / "candidate.mid").read_bytes()[:4], b"MThd")
            programs = json.loads(
                (run_dir / "candidate.programs.json").read_text(encoding="utf-8")
            )
            self.assertEqual(programs["schema"], AI_GM_PROGRAM_MAPPING_SCHEMA)
            self.assertEqual(programs["tracks"][0]["instrument"], "lead vocal")
            self.assertEqual(programs["tracks"][0]["program"], 52)
            self.assertEqual(programs["notes_mutated"], 0)
            self.assertFalse(programs["raw_candidate_mutated"])
            self.assertIn("candidate.programs.json", saved["artifacts"])
            self.assertEqual(
                saved["postprocessing"]["gm_program_mapping"]["policy"],
                "canonical-instrument-label-v1",
            )
            quality = json.loads(
                (run_dir / "candidate.quality.json").read_text(encoding="utf-8")
            )
            self.assertEqual(quality["schema"], AI_QUALITY_SCHEMA)
            self.assertEqual(quality["status"], "pass")
            self.assertTrue(quality["promotion_allowed"])
            expression = json.loads(
                (run_dir / "candidate.expression.json").read_text(encoding="utf-8")
            )
            self.assertEqual(expression["schema"], AI_EXPRESSION_SCHEMA)
            self.assertEqual(expression["status"], "complete")
            self.assertEqual(expression["notes"][0]["velocity"], 88)
            self.assertIsNone(candidate["notes"][0]["velocity"])
            self.assertEqual(
                (run_dir / "candidate.expression.mid").read_bytes()[:4], b"MThd"
            )
            self.assertNotEqual(
                (run_dir / "candidate.mid").read_bytes(),
                (run_dir / "candidate.expression.mid").read_bytes(),
            )
            self.assertFalse(
                saved["postprocessing"]["source_velocity"][
                    "raw_candidate_mutated"
                ]
            )
            self.assertIn(
                "synthetic worker complete",
                (run_dir / "worker.stdout.log").read_text(encoding="utf-8"),
            )

    def test_game_bundle_is_recorded_by_component_and_runs_model_neutrally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, _checkpoint, worker = self._fixture(directory, SUCCESS_WORKER)
            bundle = self._game_bundle(Path(directory))
            output = Path(directory) / "runs"

            result = run_ai_transcription(
                audio_path=audio,
                out_dir=output,
                checkpoint_path=bundle,
                bpm=119,
                backend="game",
                roles=("voice",),
                python=sys.executable,
                worker_path=worker,
                run_id="game-success",
            )

            self.assertEqual(result["backend"], "game")
            self.assertEqual(result["checkpoint"]["kind"], "directory")
            self.assertEqual(
                set(result["checkpoint"]["components"]),
                {
                    "config.json",
                    "encoder.onnx",
                    "segmenter.onnx",
                    "estimator.onnx",
                    "dur2bd.onnx",
                    "bd2dur.onnx",
                },
            )
            candidate = json.loads(
                (output / "game-success" / "candidate.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(candidate["backend"], "game")
            self.assertEqual(candidate["manifest"]["code_license"], "MIT")

    def test_ai_candidate_tracks_use_role_aware_gm_audition_programs(self) -> None:
        candidate = AITranscriptionCandidate(
            backend="muscriptor",
            model_version="test-small",
            notes=(
                AITranscriptionNote(
                    0.0,
                    0.5,
                    40.0,
                    instrument="electric_bass",
                    source_event_id="bass",
                ),
                AITranscriptionNote(
                    0.0,
                    0.5,
                    60.0,
                    instrument="electric_piano",
                    source_event_id="keys",
                ),
                AITranscriptionNote(
                    0.0,
                    0.5,
                    64.0,
                    instrument="synth_pad",
                    source_event_id="pad",
                ),
                AITranscriptionNote(
                    0.0,
                    0.1,
                    36.0,
                    instrument="drums",
                    source_event_id="kick",
                ),
            ),
        )

        tracks = {track.name: track for track in _candidate_tracks(candidate)}

        self.assertEqual(tracks["electric_bass"].program, 33)
        self.assertEqual(tracks["electric_piano"].program, 4)
        self.assertEqual(tracks["synth_pad"].program, 89)
        self.assertEqual(tracks["drums"].channel, 9)
        self.assertEqual(tracks["drums"].program, 0)

    def test_rmvpe_file_and_declared_frame_evidence_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, _checkpoint, worker = self._fixture(directory, SUCCESS_WORKER)
            model = Path(directory) / "rmvpe.onnx"
            model.write_bytes(b"synthetic rmvpe checkpoint")
            output = Path(directory) / "runs"

            result = run_ai_transcription(
                audio_path=audio,
                out_dir=output,
                checkpoint_path=model,
                bpm=119,
                backend="rmvpe",
                roles=("lead vocal",),
                python=sys.executable,
                worker_path=worker,
                run_id="rmvpe-success",
            )

            self.assertEqual(result["backend"], "rmvpe")
            self.assertEqual(result["checkpoint"]["kind"], "file")
            self.assertIn("rmvpe.frames.json", result["artifacts"])
            self.assertEqual(
                result["artifacts"]["rmvpe.frames.json"]["sha256"],
                hashlib.sha256(
                    (output / "rmvpe-success" / "rmvpe.frames.json").read_bytes()
                ).hexdigest(),
            )

    def test_pesto_file_and_declared_raw_evidence_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, _checkpoint, worker = self._fixture(directory, SUCCESS_WORKER)
            model = Path(directory) / "mir-1k_g7.ckpt"
            model.write_bytes(b"synthetic pesto checkpoint")
            output = Path(directory) / "runs"

            result = run_ai_transcription(
                audio_path=audio,
                out_dir=output,
                checkpoint_path=model,
                bpm=119,
                backend="pesto",
                roles=("lead vocal",),
                python=sys.executable,
                worker_path=worker,
                run_id="pesto-success",
            )

            self.assertEqual(result["backend"], "pesto")
            self.assertEqual(result["checkpoint"]["kind"], "file")
            self.assertIn("pesto.frames.json", result["artifacts"])
            self.assertIn("pesto.activations.npy", result["artifacts"])
            candidate = json.loads(
                (output / "pesto-success" / "candidate.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(candidate["manifest"]["code_license"], "LGPL-3.0")

    def test_worker_declared_raw_artifact_cannot_escape_the_run(self) -> None:
        escaping_worker = SUCCESS_WORKER.replace(
            '"raw_artifacts": [],', '"raw_artifacts": ["../escape.json"],'
        )
        with tempfile.TemporaryDirectory() as directory:
            audio, checkpoint, worker = self._fixture(directory, escaping_worker)
            output = Path(directory) / "runs"

            with self.assertRaisesRegex(AIWorkerRunError, "escapes"):
                run_ai_transcription(
                    audio_path=audio,
                    out_dir=output,
                    checkpoint_path=checkpoint,
                    bpm=119,
                    python=sys.executable,
                    worker_path=worker,
                    run_id="escaping-artifact",
                )

            run = json.loads(
                (output / "escaping-artifact" / "run.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(run["status"], "failed")
            self.assertIn("escapes", run["error"])

    def test_rmvpe_frame_decoder_suppresses_vibrato_and_short_pitch_glitch(self) -> None:
        times = np.arange(60, dtype=np.float64) * 0.01
        midi = np.concatenate(
            [
                60.0 + 0.25 * np.sin(np.arange(30) * 0.9),
                64.0 + 0.2 * np.sin(np.arange(30) * 0.8),
            ]
        )
        midi[14:16] = 61.2
        frequency = 440.0 * (2.0 ** ((midi - 69.0) / 12.0))
        confidence = np.full(60, 0.9, dtype=np.float64)
        confidence[20:23] = 0.0

        notes, decoder = _rmvpe_frames_to_notes(
            times,
            frequency,
            confidence,
            start_seconds=10.0,
            excerpt_duration=0.6,
            instrument="lead vocal",
            confidence_threshold=0.03,
            minimum_note_ms=80.0,
            maximum_gap_ms=50.0,
            pitch_change_semitones=0.75,
        )

        self.assertEqual(len(notes), 2)
        self.assertAlmostEqual(notes[0]["pitch"], 60.0, delta=0.4)
        self.assertAlmostEqual(notes[1]["pitch"], 64.0, delta=0.4)
        self.assertAlmostEqual(notes[0]["start_seconds"], 10.0)
        self.assertEqual(decoder["bridged_frames"], 3)
        self.assertEqual(decoder["frame_count"], 60)
        self.assertEqual(decoder["minimum_note_frames"], 8)

    def test_rmvpe_frame_decoder_keeps_a_long_unvoiced_rest(self) -> None:
        times = np.arange(60, dtype=np.float64) * 0.01
        frequency = np.full(60, 220.0, dtype=np.float64)
        confidence = np.full(60, 0.9, dtype=np.float64)
        confidence[20:35] = 0.0

        notes, decoder = _rmvpe_frames_to_notes(
            times,
            frequency,
            confidence,
            start_seconds=0.0,
            excerpt_duration=0.6,
            instrument="voice",
            confidence_threshold=0.03,
            minimum_note_ms=80.0,
            maximum_gap_ms=50.0,
            pitch_change_semitones=0.75,
        )

        self.assertEqual(len(notes), 2)
        self.assertLessEqual(notes[0]["end_seconds"], 0.21)
        self.assertGreaterEqual(notes[1]["start_seconds"], 0.35)
        self.assertEqual(decoder["bridged_frames"], 0)

    def test_source_expression_maps_louder_note_to_higher_velocity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sample_rate = 16_000
            times = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
            signal = np.zeros(sample_rate * 2, dtype=np.float32)
            signal[:sample_rate] = 0.04 * np.sin(
                2.0 * np.pi * 220.0 * times[:sample_rate]
            )
            signal[sample_rate:] = 0.55 * np.sin(
                2.0 * np.pi * 220.0 * times[sample_rate:]
            )
            audio = Path(directory) / "dynamic.wav"
            soundfile.write(audio, signal, sample_rate)
            candidate = AITranscriptionCandidate(
                backend="muscriptor",
                model_version="test-small",
                notes=(
                    AITranscriptionNote(
                        0.1,
                        0.9,
                        57.0,
                        instrument="electric_bass",
                        source_event_id="quiet",
                    ),
                    AITranscriptionNote(
                        1.1,
                        1.9,
                        57.0,
                        instrument="electric_bass",
                        source_event_id="loud",
                    ),
                ),
            )

            expression = recover_source_expression(audio, candidate)
            velocities = expression_velocities(expression, expected_notes=2)

            self.assertEqual(expression["status"], "complete")
            self.assertGreater(velocities[1], velocities[0])
            self.assertIsNone(candidate.notes[0].velocity)
            self.assertIsNone(candidate.notes[1].velocity)
            self.assertFalse(expression["policy"]["raw_candidate_mutated"])

    def test_game_note_adapter_keeps_float_pitch_and_advances_over_rests(self) -> None:
        notes, regions = _game_notes(
            np.asarray([0.25, 0.5, 0.25], dtype=np.float32),
            np.asarray([True, True, True]),
            np.asarray([True, False, True]),
            np.asarray([60.25, 0.0, 64.75], dtype=np.float32),
            start_seconds=10.0,
            excerpt_duration=1.0,
        )

        self.assertEqual(regions, 3)
        self.assertEqual(len(notes), 2)
        self.assertAlmostEqual(notes[0]["pitch"], 60.25)
        self.assertAlmostEqual(notes[1]["pitch"], 64.75)
        self.assertAlmostEqual(notes[1]["start_seconds"], 10.75)

    def test_quality_gate_flags_dense_short_decoder_burst(self) -> None:
        notes = tuple(
            AITranscriptionNote(
                1.0,
                1.01,
                float(35 + index % 40),
                instrument="drums",
                source_event_id=str(index),
            )
            for index in range(200)
        )
        candidate = AITranscriptionCandidate(
            backend="muscriptor",
            model_version="test-small",
            notes=notes,
            metadata={"excerpt": {"duration_seconds": 15.0}},
        )

        quality = assess_candidate_quality(candidate)

        self.assertEqual(quality["status"], "review-required")
        self.assertFalse(quality["promotion_allowed"])
        self.assertEqual(quality["metrics"]["max_onsets_in_20ms"], 200)
        self.assertEqual(quality["metrics"]["maximum_simultaneous_notes"], 200)
        self.assertGreaterEqual(len(quality["warnings"]), 2)

    def test_quality_gate_records_restricted_instrument_leakage(self) -> None:
        candidate = AITranscriptionCandidate(
            backend="muscriptor",
            model_version="test-small",
            notes=(
                AITranscriptionNote(
                    0.0,
                    0.5,
                    60.0,
                    instrument="flutes",
                    source_event_id="wrong-label",
                ),
            ),
        )

        quality = assess_candidate_quality(candidate, requested_roles=("voice",))

        self.assertEqual(quality["status"], "review-required")
        self.assertEqual(quality["unexpected_instruments"], {"flutes": 1})

    def test_existing_run_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, checkpoint, worker = self._fixture(directory, SUCCESS_WORKER)
            arguments = {
                "audio_path": audio,
                "out_dir": Path(directory) / "runs",
                "checkpoint_path": checkpoint,
                "bpm": 120,
                "python": sys.executable,
                "worker_path": worker,
                "run_id": "same-run",
            }
            run_ai_transcription(**arguments)
            original = (
                Path(arguments["out_dir"]) / "same-run" / "run.json"
            ).read_bytes()
            with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                run_ai_transcription(**arguments)
            self.assertEqual(
                (Path(arguments["out_dir"]) / "same-run" / "run.json").read_bytes(),
                original,
            )

    def test_failed_worker_leaves_auditable_final_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, checkpoint, worker = self._fixture(directory, FAILURE_WORKER)
            output = Path(directory) / "runs"
            with self.assertRaisesRegex(AIWorkerRunError, "status 7"):
                run_ai_transcription(
                    audio_path=audio,
                    out_dir=output,
                    checkpoint_path=checkpoint,
                    bpm=120,
                    python=sys.executable,
                    worker_path=worker,
                    run_id="fixture-failure",
                )
            run_dir = output / "fixture-failure"
            manifest = json.loads(
                (run_dir / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["exit_code"], 7)
            self.assertIn(
                "synthetic model failure",
                (run_dir / "worker.stderr.log").read_text(encoding="utf-8"),
            )
            self.assertFalse((run_dir / "candidate.mid").exists())

    def test_timed_out_worker_leaves_logs_and_final_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, checkpoint, worker = self._fixture(directory, TIMEOUT_WORKER)
            output = Path(directory) / "runs"
            with self.assertRaisesRegex(AIWorkerRunError, "timed out"):
                run_ai_transcription(
                    audio_path=audio,
                    out_dir=output,
                    checkpoint_path=checkpoint,
                    bpm=120,
                    python=sys.executable,
                    worker_path=worker,
                    timeout_seconds=0.05,
                    run_id="fixture-timeout",
                )
            manifest = json.loads(
                (output / "fixture-timeout" / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertIsNone(manifest["exit_code"])
            self.assertIn("timed out", manifest["error"])

    def test_real_worker_rejects_model_alias_before_import_or_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "excerpt.wav"
            audio.touch()
            request = root / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "schema": AI_REQUEST_SCHEMA,
                        "audio_path": str(audio),
                        "backend": "muscriptor",
                        "roles": [],
                        "start_seconds": 0.0,
                        "end_seconds": None,
                        "options": {"model_path": "small"},
                    }
                ),
                encoding="utf-8",
            )
            output = root / "candidate.json"
            worker = (
                Path(__file__).resolve().parents[1]
                / "src"
                / "sunofriend"
                / "ai_worker.py"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(worker),
                    "--request",
                    str(request),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("model aliases", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
