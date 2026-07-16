from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import soundfile

from sunofriend.melody_correction import apply_melody_corrections
from sunofriend.phrase_review import (
    PHRASE_REVIEW_SCHEMA,
    _evaluate_alternative,
    build_melody_phrase_review,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(path: Path) -> dict:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _evaluation() -> dict:
    return {
        "note_count": 2,
        "onsets": {
            "strong": {"f1": 0.5},
            "possible": {"f1": 0.6},
            "timing": {"absolute_error_p95_ms": 20.0},
        },
        "pitched": {
            "chroma_similarity": 0.8,
            "supported_note_ratio": 0.5,
        },
    }


def _fake_render(
    _midi: str | Path,
    wav: str | Path,
    *,
    sample_rate: int = 8_000,
) -> Path:
    output = Path(wav)
    soundfile.write(output, np.zeros(sample_rate, dtype=np.float32), sample_rate)
    return output


class PhraseReviewTests(unittest.TestCase):
    def _tracker_run(self, root: Path, *, role: str = "lead") -> Path:
        source = root / "voice.wav"
        time = np.arange(32_000, dtype=np.float32) / 16_000
        soundfile.write(source, 0.1 * np.sin(2 * np.pi * 261.63 * time), 16_000)
        source_record = {
            "path": str(source),
            "bytes": source.stat().st_size,
            "sha256": _sha256(source),
        }
        run_dir = root / "tracker-run"
        run_dir.mkdir()
        basic = {
            "schema": "sunofriend.vocal-tracker-evidence.v1",
            "source": source_record,
            "notes": [
                {
                    "start_seconds": 0.2,
                    "end_seconds": 0.6,
                    "pitch": 60,
                    "velocity": 80,
                    "confidence": 0.8,
                },
                {
                    "start_seconds": 0.6,
                    "end_seconds": 1.2,
                    "pitch": 64,
                    "velocity": 90,
                    "confidence": 0.9,
                },
            ],
        }
        boundary = {
            "schema": "sunofriend.vocal-boundary-repair.v1",
            "source": source_record,
            "role": role,
            "policy": {"raw_candidates_mutated": False},
            "phrases": {
                "combined": [
                    {
                        "phrase_index": 0,
                        "confidence_rank": 1,
                        "start_seconds": 0.2,
                        "end_seconds": 1.2,
                        "mean_agreement_ratio": 0.7,
                        "mean_selection_score": 0.8,
                        "providers": ["basic-pitch", "game"],
                    }
                ]
            },
            "variants": {
                "game": [
                    {
                        "start_seconds": 0.2,
                        "end_seconds": 0.7,
                        "pitch": 60,
                        "velocity": 84,
                    },
                    {
                        "start_seconds": 0.7,
                        "end_seconds": 1.2,
                        "pitch": 62,
                        "velocity": 88,
                    },
                ],
                "combined": [
                    {
                        "start_seconds": 0.2,
                        "end_seconds": 0.6,
                        "pitch": 60,
                        "velocity": 80,
                    },
                    {
                        "start_seconds": 0.6,
                        "end_seconds": 1.2,
                        "pitch": 64,
                        "velocity": 90,
                    },
                ],
            },
        }
        basic_path = run_dir / "basic-pitch.evidence.json"
        boundary_path = run_dir / "boundary-repair.evidence.json"
        basic_path.write_text(json.dumps(basic), encoding="utf-8")
        boundary_path.write_text(json.dumps(boundary), encoding="utf-8")
        combined_midi = run_dir / "boundary-repair.candidate.mid"
        combined_midi.write_bytes(b"MThd")
        run = {
            "schema": "sunofriend.vocal-tracker-run.v1",
            "run_id": "fixture-run",
            "status": "complete",
            "source": source_record,
            "role": role,
            "bpm": 120.0,
            "tuning_hz": 440.0,
            "boundary_repair_created": True,
            "artifacts": {
                basic_path.name: _record(basic_path),
                boundary_path.name: _record(boundary_path),
                combined_midi.name: _record(combined_midi),
            },
        }
        (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
        return run_dir

    def test_builds_ranked_auditions_and_reviewed_correction_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._tracker_run(root)
            first = root / "review-first"
            second = root / "review-second"

            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ):
                result = build_melody_phrase_review(run, out_dir=first)
                build_melody_phrase_review(run, out_dir=second)

            self.assertEqual(result["status"], "review-required")
            self.assertEqual(result["phrase_count"], 1)
            manifest = json.loads((first / "phrase_review.json").read_text())
            self.assertEqual(manifest["schema"], PHRASE_REVIEW_SCHEMA)
            self.assertFalse(manifest["raw_candidates_mutated"])
            alternatives = manifest["phrases"][0]["alternatives"]
            self.assertEqual(
                set(alternatives),
                {"basic-pitch", "game-boundary", "combined"},
            )
            for candidate in alternatives.values():
                self.assertTrue((first / candidate["audio"]).is_file())
                self.assertTrue((first / candidate["overlay_audio"]).is_file())
                self.assertTrue((first / candidate["midi"]).is_file())
                self.assertTrue((first / candidate["evaluation"]).is_file())
            html = (first / "melody_phrase_review.html").read_text()
            self.assertIn("Choose by recognition", html)
            self.assertIn("Export reviewed correction JSON", html)
            seed_path = first / "melody_corrections_unreviewed.json"
            seed = json.loads(seed_path.read_text())
            self.assertEqual(seed["format"], "sunofriend-melody-corrections-v1")
            self.assertEqual(seed["review"]["status"], "unreviewed")
            with self.assertRaisesRegex(ValueError, "must be reviewed"):
                apply_melody_corrections(seed_path, out_path=root / "early.mid")
            with self.assertRaisesRegex(ValueError, "already exists"):
                build_melody_phrase_review(run, out_dir=first)

            incomplete = json.loads(json.dumps(seed))
            incomplete["review"]["status"] = "reviewed"
            incomplete_path = root / "incomplete.json"
            incomplete_path.write_text(json.dumps(incomplete), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete choices"):
                apply_melody_corrections(
                    incomplete_path,
                    out_path=root / "incomplete.mid",
                )

            wrong_source = json.loads(json.dumps(seed))
            wrong_source["source_stem_sha256"] = "0" * 64
            wrong_source["review"]["status"] = "reviewed"
            wrong_source["review"]["choices"][0]["reviewed"] = True
            wrong_source_path = root / "wrong-source.json"
            wrong_source_path.write_text(
                json.dumps(wrong_source),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "source stem hash"):
                apply_melody_corrections(
                    wrong_source_path,
                    out_path=root / "wrong-source.mid",
                )

            seed["review"]["status"] = "reviewed"
            seed["review"]["choices"][0].update(
                {"selected": "game-boundary", "reviewed": True}
            )
            seed["notes"] = alternatives["game-boundary"]["notes"]
            reviewed = root / "reviewed.json"
            reviewed.write_text(json.dumps(seed), encoding="utf-8")
            audit = apply_melody_corrections(
                reviewed,
                out_path=root / "reviewed.mid",
            )
            self.assertEqual(audit["review"]["status"], "reviewed")
            self.assertEqual(audit["note_count"], 2)

            for relative in manifest["artifacts"]:
                self.assertEqual(
                    (first / relative).read_bytes(),
                    (second / relative).read_bytes(),
                    relative,
                )
            self.assertEqual(
                (first / "phrase_review.json").read_bytes(),
                (second / "phrase_review.json").read_bytes(),
            )

    def test_rejects_mutated_evidence_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._tracker_run(root)
            evidence = run / "boundary-repair.evidence.json"
            evidence.write_text(evidence.read_text() + "\n", encoding="utf-8")
            output = root / "review"

            with self.assertRaisesRegex(ValueError, "hash"):
                build_melody_phrase_review(run, out_dir=output)

            self.assertFalse(output.exists())

    def test_rejects_backing_harmony(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._tracker_run(root, role="backing")

            with self.assertRaisesRegex(ValueError, "lead vocals only"):
                build_melody_phrase_review(run, out_dir=root / "review")

    def test_evaluation_publishes_safe_relative_labels(self):
        report = Mock()
        report.to_dict.return_value = {
            "stem_path": "/private/random/source.wav",
            "midi_path": "/private/random/candidate.mid",
            "note_count": 1,
        }
        with patch(
            "sunofriend.evaluate.evaluate_stem_midi",
            return_value=report,
        ):
            document = _evaluate_alternative(
                Path("/private/random/source.wav"),
                Path("/private/random/candidate.mid"),
            )

        self.assertEqual(document["stem_path"], "source.wav")
        self.assertEqual(document["midi_path"], "candidate.mid")


if __name__ == "__main__":
    unittest.main()
