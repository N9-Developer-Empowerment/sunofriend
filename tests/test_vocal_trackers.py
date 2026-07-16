from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.models import NoteEvent
from sunofriend.vocal import (
    PitchFrame,
    VocalCandidate,
    fractional_midi_to_hz,
)
from sunofriend.vocal_trackers import (
    VOCAL_TRACKER_CONSENSUS_SCHEMA,
    VOCAL_TRACKER_EVIDENCE_SCHEMA,
    VOCAL_TRACKER_RUN_SCHEMA,
    load_game_boundary_candidates,
    load_rmvpe_evidence,
    run_vocal_tracker_bakeoff,
)


def _frames(count: int = 200) -> list[PitchFrame]:
    return [
        PitchFrame(
            time=index * 0.01,
            f0_hz=fractional_midi_to_hz(60.0 if index < count // 2 else 64.0),
            voiced_probability=0.92,
            rms=0.1,
            onset_strength=0.8 if index in {0, count // 2} else 0.0,
            source="pyin",
        )
        for index in range(count)
    ]


def _write_rmvpe_run(root: Path, source: Path, *, source_hash: str | None = None) -> Path:
    run = root / "rmvpe-run"
    run.mkdir()
    digest = source_hash or hashlib.sha256(source.read_bytes()).hexdigest()
    (run / "run.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "backend": "rmvpe",
                "source": {"path": str(source), "sha256": digest},
                "checkpoint": {"sha256": "checkpoint-sha"},
            }
        ),
        encoding="utf-8",
    )
    (run / "candidate.json").write_text(
        json.dumps(
            {
                "model_version": "rmvpe-test",
                "metadata": {
                    "checkpoint_sha256": "checkpoint-sha",
                    "note_decoder": {"confidence_threshold": 0.03},
                },
            }
        ),
        encoding="utf-8",
    )
    frames = [
        [
            index * 0.01,
            fractional_midi_to_hz(60.1 if index < 100 else 64.1),
            0.90,
        ]
        for index in range(200)
    ]
    frames[50][2] = 0.01
    path = run / "rmvpe.frames.json"
    path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.rmvpe-f0-frames.v1",
                "checkpoint_sha256": "checkpoint-sha",
                "excerpt": {"start_seconds": 0.0, "duration_seconds": 2.0},
                "frames": frames,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_game_run(root: Path, source: Path, *, source_hash: str | None = None) -> Path:
    run = root / "game-run"
    run.mkdir()
    digest = source_hash or hashlib.sha256(source.read_bytes()).hexdigest()
    (run / "run.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "backend": "game",
                "source": {"path": str(source), "sha256": digest},
                "checkpoint": {"sha256": "game-checkpoint-sha"},
            }
        ),
        encoding="utf-8",
    )
    candidate = run / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema": "sunofriend.ai-transcription-candidate.v1",
                "backend": "game",
                "model_version": "game-test",
                "notes": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 0.9,
                        "pitch": 60.1,
                        "confidence": None,
                        "instrument": "voice",
                        "velocity": None,
                        "source_event_id": "game-0",
                    },
                    {
                        "start_seconds": 1.0,
                        "end_seconds": 1.9,
                        "pitch": 64.1,
                        "confidence": None,
                        "instrument": "voice",
                        "velocity": None,
                        "source_event_id": "game-1",
                    },
                ],
                "warnings": [],
                "raw_artifacts": [],
                "metadata": {
                    "checkpoint_sha256": "game-checkpoint-sha",
                    "excerpt": {"start_seconds": 0.0},
                    "seed": 0,
                    "language": "en",
                },
            }
        ),
        encoding="utf-8",
    )
    return candidate


class VocalTrackerBakeoffTests(unittest.TestCase):
    def _audio(self, root: Path) -> Path:
        sample_rate = 16_000
        time = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
        audio = 0.2 * np.sin(2.0 * np.pi * 261.63 * time)
        path = root / "voice.wav"
        soundfile.write(path, audio, sample_rate)
        return path

    def test_rmvpe_loader_checks_source_and_applies_recorded_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = self._audio(root)
            evidence = _write_rmvpe_run(root, audio)
            source_hash = hashlib.sha256(audio.read_bytes()).hexdigest()

            frames, record = load_rmvpe_evidence(
                evidence,
                source_sha256=source_hash,
                reference_frames=_frames(),
            )

            self.assertEqual(len(frames), 200)
            self.assertIsNone(frames[50].f0_hz)
            self.assertEqual(record["model_version"], "rmvpe-test")
            with self.assertRaisesRegex(ValueError, "source hash"):
                load_rmvpe_evidence(
                    evidence,
                    source_sha256="0" * 64,
                    reference_frames=_frames(),
                )

            candidate = evidence.parent / "candidate.json"
            document = json.loads(candidate.read_text(encoding="utf-8"))
            document["metadata"]["checkpoint_sha256"] = "different-checkpoint"
            candidate.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkpoint hash"):
                load_rmvpe_evidence(
                    evidence,
                    source_sha256=source_hash,
                    reference_frames=_frames(),
                )

    def test_game_boundaries_require_rmvpe_pitch_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = self._audio(root)
            game = _write_game_run(root, audio)

            with self.assertRaisesRegex(ValueError, "requires rmvpe_frames_path"):
                run_vocal_tracker_bakeoff(
                    audio_path=audio,
                    out_dir=root / "runs",
                    bpm=119,
                    role="lead",
                    game_candidate_path=game,
                )

    def test_game_loader_requires_matching_immutable_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = self._audio(root)
            candidate = _write_game_run(root, audio)
            source_hash = hashlib.sha256(audio.read_bytes()).hexdigest()

            proposals, record = load_game_boundary_candidates(
                candidate,
                source_sha256=source_hash,
            )

            self.assertEqual(len(proposals), 2)
            self.assertEqual(proposals[0].provider, "game")
            self.assertEqual(record["model_version"], "game-test")
            with self.assertRaisesRegex(ValueError, "source hash"):
                load_game_boundary_candidates(
                    candidate,
                    source_sha256="0" * 64,
                )

            document = json.loads(candidate.read_text(encoding="utf-8"))
            document["metadata"]["checkpoint_sha256"] = "different-checkpoint"
            candidate.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkpoint hash"):
                load_game_boundary_candidates(
                    candidate,
                    source_sha256=source_hash,
                )

    def test_run_keeps_independent_records_and_builds_hashed_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = self._audio(root)
            rmvpe = _write_rmvpe_run(root, audio)
            game = _write_game_run(root, audio)
            candidates = [
                VocalCandidate(NoteEvent(0.0, 0.9, 60, 92), 0.88),
                VocalCandidate(NoteEvent(1.0, 1.9, 64, 104), 0.91),
            ]
            model_record = {
                "path": "fixture.onnx",
                "bytes": 1,
                "sha256": "model-sha",
                "package": "basic-pitch",
                "package_version": "test",
            }
            output = root / "runs"

            with patch(
                "sunofriend.vocal_trackers.extract_pitch_frames",
                return_value=_frames(),
            ), patch(
                "sunofriend.vocal_trackers.extract_backing_candidates",
                return_value=candidates,
            ), patch(
                "sunofriend.vocal_trackers._basic_pitch_model_record",
                return_value=model_record,
            ):
                first = run_vocal_tracker_bakeoff(
                    audio_path=audio,
                    out_dir=output,
                    bpm=119,
                    role="lead",
                    rmvpe_frames_path=rmvpe,
                    game_candidate_path=game,
                    run_id="first",
                )
                second = run_vocal_tracker_bakeoff(
                    audio_path=audio,
                    out_dir=output,
                    bpm=119,
                    role="lead",
                    rmvpe_frames_path=rmvpe,
                    game_candidate_path=game,
                    run_id="second",
                )

            self.assertEqual(first["schema"], VOCAL_TRACKER_RUN_SCHEMA)
            self.assertEqual(first["trackers"], ["pyin", "basic-pitch", "rmvpe"])
            self.assertTrue(first["consensus_created"])
            self.assertTrue(first["boundary_repair_created"])
            self.assertEqual(first["boundary_sources"], ["basic-pitch", "game"])
            pyin = json.loads((output / "first/pyin.evidence.json").read_text())
            basic = json.loads(
                (output / "first/basic-pitch.evidence.json").read_text()
            )
            consensus = json.loads(
                (output / "first/consensus.evidence.json").read_text()
            )
            self.assertEqual(pyin["schema"], VOCAL_TRACKER_EVIDENCE_SCHEMA)
            self.assertEqual(basic["schema"], VOCAL_TRACKER_EVIDENCE_SCHEMA)
            self.assertEqual(consensus["schema"], VOCAL_TRACKER_CONSENSUS_SCHEMA)
            self.assertEqual(consensus["policy"]["minimum_trackers"], 2)
            self.assertEqual(
                consensus["inputs"]["pyin"]["sha256"],
                hashlib.sha256(
                    (output / "first/pyin.evidence.json").read_bytes()
                ).hexdigest(),
            )
            for name in (
                "pyin.evidence.json",
                "basic-pitch.evidence.json",
                "consensus.evidence.json",
                "boundary-repair.evidence.json",
                "pyin.candidate.mid",
                "basic-pitch.candidate.mid",
                "consensus.candidate.mid",
                "boundary-basic-pitch.candidate.mid",
                "boundary-game.candidate.mid",
                "boundary-repair.candidate.mid",
            ):
                self.assertEqual(
                    (output / "first" / name).read_bytes(),
                    (output / "second" / name).read_bytes(),
                    name,
                )
            self.assertEqual(second["results"]["consensus"]["status"], "review-required")
            with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                run_vocal_tracker_bakeoff(
                    audio_path=audio,
                    out_dir=output,
                    bpm=119,
                    role="lead",
                    run_id="first",
                )


if __name__ == "__main__":
    unittest.main()
