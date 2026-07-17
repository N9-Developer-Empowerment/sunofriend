from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import soundfile

from sunofriend.conversion import NoteProvenance
from sunofriend.melody_correction import apply_melody_corrections
from sunofriend.melody_profile import build_personal_melody_profile
from sunofriend.models import NoteEvent
from sunofriend.phrase_guide import ShortGuideResult
from sunofriend.phrase_review import (
    PHRASE_REVIEW_SCHEMA,
    _evaluate_alternative,
    _merge_phrase_records,
    build_guided_melody_phrase_review,
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
        pyin_path = run_dir / "pyin.evidence.json"
        boundary_path = run_dir / "boundary-repair.evidence.json"
        basic_path.write_text(json.dumps(basic), encoding="utf-8")
        pyin = {
            "schema": "sunofriend.vocal-tracker-evidence.v1",
            "tracker": "pyin",
            "source": source_record,
            "frame_fields": [
                "time_seconds",
                "frequency_hz",
                "confidence",
                "rms",
                "onset_strength",
                "source",
            ],
            "frames": [
                [index / 10.0, 261.63, 0.9, 0.1, 0.5 if index == 2 else 0.0, "pyin"]
                for index in range(20)
            ],
        }
        pyin_path.write_text(json.dumps(pyin), encoding="utf-8")
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
                pyin_path.name: _record(pyin_path),
                boundary_path.name: _record(boundary_path),
                combined_midi.name: _record(combined_midi),
            },
        }
        (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
        return run_dir

    def _repeated_tracker_run(self, root: Path) -> Path:
        source = root / "repeated-voice.wav"
        time = np.arange(64_000, dtype=np.float32) / 16_000
        soundfile.write(source, 0.1 * np.sin(2 * np.pi * 261.63 * time), 16_000)
        source_record = {
            "path": str(source),
            "bytes": source.stat().st_size,
            "sha256": _sha256(source),
        }
        starts = [0.2, 0.55, 0.95, 2.2, 2.55, 2.95]
        ends = [0.45, 0.85, 1.2, 2.45, 2.85, 3.2]
        pitches = [60, 64, 62, 60, 64, 62]
        notes = [
            {
                "start_seconds": start,
                "end_seconds": end,
                "pitch": pitch,
                "velocity": 84,
                "confidence": 0.9,
            }
            for start, end, pitch in zip(starts, ends, pitches)
        ]
        basic = {
            "schema": "sunofriend.vocal-tracker-evidence.v1",
            "source": source_record,
            "notes": notes,
        }
        boundary = {
            "schema": "sunofriend.vocal-boundary-repair.v1",
            "source": source_record,
            "role": "lead",
            "policy": {"raw_candidates_mutated": False},
            "phrases": {
                "combined": [
                    {
                        "phrase_index": 0,
                        "start_seconds": 0.2,
                        "end_seconds": 1.2,
                        "note_count": 3,
                        "mean_agreement_ratio": 0.9,
                        "mean_selection_score": 0.9,
                        "providers": ["basic-pitch", "game"],
                    },
                    {
                        "phrase_index": 1,
                        "start_seconds": 2.2,
                        "end_seconds": 3.2,
                        "note_count": 3,
                        "mean_agreement_ratio": 0.9,
                        "mean_selection_score": 0.9,
                        "providers": ["basic-pitch", "game"],
                    },
                ]
            },
            "variants": {
                "game": [
                    {
                        "start_seconds": value["start_seconds"],
                        "end_seconds": value["end_seconds"],
                        "pitch": value["pitch"],
                        "velocity": 86,
                    }
                    for value in notes
                ],
                "combined": [
                    {
                        "start_seconds": value["start_seconds"],
                        "end_seconds": value["end_seconds"],
                        "pitch": value["pitch"],
                        "velocity": value["velocity"],
                    }
                    for value in notes
                ],
            },
        }
        run_dir = root / "repeated-tracker-run"
        run_dir.mkdir()
        basic_path = run_dir / "basic-pitch.evidence.json"
        boundary_path = run_dir / "boundary-repair.evidence.json"
        pyin_path = run_dir / "pyin.evidence.json"
        basic_path.write_text(json.dumps(basic), encoding="utf-8")
        boundary_path.write_text(json.dumps(boundary), encoding="utf-8")
        pyin_path.write_text(
            json.dumps(
                {
                    "schema": "sunofriend.vocal-tracker-evidence.v1",
                    "tracker": "pyin",
                    "source": source_record,
                    "frame_fields": [
                        "time_seconds",
                        "frequency_hz",
                        "confidence",
                        "rms",
                        "onset_strength",
                        "source",
                    ],
                    "frames": [
                        [index / 10.0, 261.63, 0.9, 0.1, 0.0, "pyin"]
                        for index in range(40)
                    ],
                }
            ),
            encoding="utf-8",
        )
        combined_midi = run_dir / "boundary-repair.candidate.mid"
        combined_midi.write_bytes(b"MThd")
        run = {
            "schema": "sunofriend.vocal-tracker-run.v1",
            "run_id": "repeated-fixture-run",
            "status": "complete",
            "source": source_record,
            "role": "lead",
            "bpm": 120.0,
            "tuning_hz": 440.0,
            "boundary_repair_created": True,
            "artifacts": {
                path.name: _record(path)
                for path in (
                    basic_path,
                    boundary_path,
                    pyin_path,
                    combined_midi,
                )
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
            self.assertEqual(manifest["source_phrase_count"], 1)
            self.assertEqual(manifest["review_unit_count"], 1)
            self.assertEqual(manifest["segmentation"]["minimum_bars"], 2)
            self.assertEqual(manifest["segmentation"]["maximum_bars"], 8)
            self.assertEqual(manifest["segmentation"]["short_unit_count"], 1)
            self.assertEqual(
                manifest["segmentation"]["bar_alignment"],
                "duration-only; no unconfirmed downbeat was assumed",
            )
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
            self.assertIn("Review unit 1", html)
            self.assertIn("no unconfirmed downbeat is assumed", html)
            self.assertIn("Export review JSON", html)
            self.assertIn("None are close — add a short guide", html)
            self.assertIn("sunofriend melody-guide", html)
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

            unresolved = json.loads(json.dumps(seed))
            unresolved["review"]["status"] = "unresolved"
            unresolved["review"]["unresolved_unit_indices"] = [0]
            unresolved_path = root / "unresolved.json"
            unresolved_path.write_text(json.dumps(unresolved), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unresolved units: 1"):
                apply_melody_corrections(
                    unresolved_path,
                    out_path=root / "unresolved.mid",
                )

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

    def test_short_guide_creates_fresh_source_supported_alternative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._tracker_run(root)
            parent = root / "parent-review"
            first = root / "guided-first"
            second = root / "guided-second"
            guide = root / "short-hum.wav"
            soundfile.write(guide, np.zeros(12_000, dtype=np.float32), 8_000)
            note = NoteEvent(0.25, 0.75, 61, 85)
            provenance = NoteProvenance.from_note(
                note,
                origin="repaired",
                confidence=0.82,
                family="vocals",
                sources=("short-hum", "source-contour"),
            )
            guided = ShortGuideResult(
                notes=(note,),
                provenance=(provenance,),
                report={
                    "schema": "sunofriend.short-melody-guide.v1",
                    "status": "complete",
                    "kind": "hum",
                    "guide_duration_seconds": 1.5,
                    "unit_start_seconds": 0.2,
                    "unit_end_seconds": 1.2,
                    "search_seconds": 0.5,
                    "guide_note_count": 1,
                    "accepted_note_count": 1,
                    "detection": {"method": "fixture"},
                    "alignment": {"status": "complete"},
                    "warnings": [],
                    "source_pitch_support_required": True,
                    "raw_candidates_mutated": False,
                },
            )

            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ):
                build_melody_phrase_review(run, out_dir=parent)
            parent_hashes = {
                path.relative_to(parent): _sha256(path)
                for path in parent.rglob("*")
                if path.is_file()
            }
            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ), patch(
                "sunofriend.phrase_guide.prepare_short_guide",
                return_value=guided,
            ):
                result = build_guided_melody_phrase_review(
                    parent,
                    unit=1,
                    guide_path=guide,
                    out_dir=first,
                    guide_kind="hum",
                    search_seconds=0.5,
                )
                build_guided_melody_phrase_review(
                    parent / "phrase_review.json",
                    unit=1,
                    guide_path=guide,
                    out_dir=second,
                    guide_kind="hum",
                    search_seconds=0.5,
                )

            self.assertEqual(result["guide"]["status"], "complete")
            manifest = json.loads((first / "phrase_review.json").read_text())
            self.assertEqual(
                manifest["phrases"][0]["alternative_names"],
                ["basic-pitch", "game-boundary", "combined", "guide-assisted"],
            )
            self.assertEqual(
                manifest["phrases"][0]["alternatives"]["guide-assisted"][
                    "note_count"
                ],
                1,
            )
            evidence = json.loads((first / "guide.evidence.json").read_text())
            self.assertTrue(evidence["source_pitch_support_required"])
            self.assertFalse(evidence["raw_candidates_mutated"])
            self.assertEqual(evidence["parent_review"]["verified_artifact_count"], 15)
            self.assertEqual(evidence["notes"][0]["pitch"], 61)
            reviewed = json.loads(
                (first / "melody_corrections_unreviewed.json").read_text()
            )
            reviewed["review"]["status"] = "reviewed"
            reviewed["review"]["choices"][0].update(
                {"selected": "guide-assisted", "reviewed": True}
            )
            reviewed["notes"] = manifest["phrases"][0]["alternatives"][
                "guide-assisted"
            ]["notes"]
            reviewed_path = root / "guided-reviewed.json"
            reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
            audit = apply_melody_corrections(
                reviewed_path,
                out_path=root / "guided-reviewed.mid",
            )
            self.assertEqual(audit["note_count"], 1)
            self.assertEqual(
                audit["review"]["choices"][0]["selected"],
                "guide-assisted",
            )
            self.assertEqual(
                parent_hashes,
                {
                    path.relative_to(parent): _sha256(path)
                    for path in parent.rglob("*")
                    if path.is_file()
                },
            )
            for relative in manifest["artifacts"]:
                self.assertEqual(
                    (first / relative).read_bytes(),
                    (second / relative).read_bytes(),
                    relative,
                )

    def test_short_guide_rejects_mutated_parent_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._tracker_run(root)
            parent = root / "parent-review"
            guide = root / "short-hum.wav"
            soundfile.write(guide, np.zeros(8_000, dtype=np.float32), 8_000)
            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ):
                build_melody_phrase_review(run, out_dir=parent)
            artifact = parent / "audio" / "unit-01-source.wav"
            artifact.write_bytes(artifact.read_bytes() + b"mutated")
            output = root / "guided"

            with self.assertRaisesRegex(ValueError, "hash"):
                build_guided_melody_phrase_review(
                    parent,
                    unit=1,
                    guide_path=guide,
                    out_dir=output,
                )

            self.assertFalse(output.exists())

    def test_short_guide_output_must_not_modify_parent_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "parent-review"
            parent.mkdir()
            manifest = parent / "phrase_review.json"
            manifest.write_text("{}", encoding="utf-8")
            guide = root / "guide.wav"
            soundfile.write(guide, np.zeros(8_000, dtype=np.float32), 8_000)

            with self.assertRaisesRegex(ValueError, "outside the immutable parent"):
                build_guided_melody_phrase_review(
                    parent,
                    unit=1,
                    guide_path=guide,
                    out_dir=parent / "guided-child",
                )

            self.assertFalse((parent / "guided-child").exists())

    def test_repeat_suggestion_requires_explicit_audited_propagation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self._repeated_tracker_run(root)
            first = root / "repeat-review-first"
            second = root / "repeat-review-second"
            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ):
                build_melody_phrase_review(
                    run,
                    out_dir=first,
                    minimum_bars=1,
                    maximum_bars=1,
                    beats_per_bar=2,
                )
                build_melody_phrase_review(
                    run,
                    out_dir=second,
                    minimum_bars=1,
                    maximum_bars=1,
                    beats_per_bar=2,
                )

            manifest = json.loads((first / "phrase_review.json").read_text())
            repetition = manifest["repetition"]
            self.assertEqual(repetition["accepted_pair_count"], 1)
            self.assertFalse(repetition["policy"]["automatic_selection"])
            pair = repetition["accepted_pairs"][0]
            self.assertEqual(pair["similarity_score"], 1.0)
            self.assertEqual(
                manifest["phrases"][0]["repeat_matches"][0][
                    "target_phrase_index"
                ],
                1,
            )
            html = (first / "melody_phrase_review.html").read_text()
            self.assertIn("Conservative repeat suggestion", html)
            self.assertIn(
                "Apply this unit’s current choice to repeat unit 2",
                html,
            )
            self.assertIn("propagated_from_phrase_index", html)

            correction = json.loads(
                (first / "melody_corrections_unreviewed.json").read_text()
            )
            correction["review"]["status"] = "reviewed"
            for choice in correction["review"]["choices"]:
                choice.update({"selected": "game-boundary", "reviewed": True})
            target = correction["review"]["choices"][1]
            target.update(
                {
                    "propagated_from_phrase_index": 0,
                    "propagation_policy": repetition["policy"]["name"],
                    "repeat_match": pair,
                }
            )
            correction["notes"] = [
                note
                for phrase in manifest["phrases"]
                for note in phrase["alternatives"]["game-boundary"]["notes"]
            ]
            reviewed = root / "repeat-reviewed.json"
            reviewed.write_text(json.dumps(correction), encoding="utf-8")
            audit = apply_melody_corrections(
                reviewed,
                out_path=root / "repeat-reviewed.mid",
            )
            self.assertEqual(audit["note_count"], 6)
            self.assertEqual(
                audit["review"]["choices"][1][
                    "propagated_from_phrase_index"
                ],
                0,
            )

            tampered = json.loads(json.dumps(correction))
            tampered["review"]["choices"][1]["repeat_match"][
                "similarity_score"
            ] = 0.99
            tampered_path = root / "repeat-tampered.json"
            tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence does not match"):
                apply_melody_corrections(
                    tampered_path,
                    out_path=root / "repeat-tampered.mid",
                )

            mismatch = json.loads(json.dumps(correction))
            mismatch["review"]["choices"][0]["selected"] = "combined"
            mismatch_path = root / "repeat-choice-mismatch.json"
            mismatch_path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source choice does not match"):
                apply_melody_corrections(
                    mismatch_path,
                    out_path=root / "repeat-choice-mismatch.mid",
                )

            self.assertEqual(
                (first / "phrase_review.json").read_bytes(),
                (second / "phrase_review.json").read_bytes(),
            )

    def test_personal_profile_is_advisory_and_inherited_by_guided_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviewed = root / "synthetic-reviewed.json"
            reviewed.write_text(
                json.dumps(
                    {
                        "format": "sunofriend-melody-corrections-v1",
                        "review": {
                            "format": PHRASE_REVIEW_SCHEMA,
                            "status": "reviewed",
                            "tracker_run_sha256": "synthetic-tracker",
                            "choices": [
                                {
                                    "phrase_index": 0,
                                    "selected": "game-boundary",
                                    "reviewed": True,
                                    "ranking_context": {
                                        "duration_bars": 0.5,
                                        "mean_agreement_ratio": 0.7,
                                        "mean_selection_score": 0.8,
                                        "combined_note_density_per_bar": 4.0,
                                        "alternative_names": [
                                            "basic-pitch",
                                            "game-boundary",
                                            "combined",
                                        ],
                                    },
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            profile = root / "profile.json"
            build_personal_melody_profile([reviewed], out_path=profile)
            run = self._tracker_run(root)
            parent = root / "profile-review"
            guide = root / "short-guide.wav"
            soundfile.write(guide, np.zeros(8_000, dtype=np.float32), 8_000)
            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ):
                build_melody_phrase_review(
                    run,
                    out_dir=parent,
                    ranking_profile=profile,
                )

            manifest = json.loads((parent / "phrase_review.json").read_text())
            phrase = manifest["phrases"][0]
            self.assertEqual(phrase["default_alternative"], "combined")
            self.assertEqual(
                phrase["alternative_names"],
                ["basic-pitch", "game-boundary", "combined"],
            )
            self.assertEqual(
                phrase["personal_ranking"]["history_first"],
                "game-boundary",
            )
            self.assertFalse(
                phrase["personal_ranking"]["default_selection_changed"]
            )
            self.assertFalse(
                manifest["personal_ranking"]["automatic_selection"]
            )
            html = (parent / "melody_phrase_review.html").read_text()
            self.assertIn("Your local review history", html)
            self.assertIn("not confidence", html)
            seed = json.loads(
                (parent / "melody_corrections_unreviewed.json").read_text()
            )
            self.assertFalse(seed["review"]["choices"][0]["reviewed"])
            self.assertEqual(
                seed["review"]["choices"][0]["selected"],
                "combined",
            )
            self.assertIn(
                "ranking_context",
                seed["review"]["choices"][0],
            )

            no_evidence = ShortGuideResult(
                notes=(),
                provenance=(),
                report={
                    "schema": "sunofriend.short-melody-guide.v1",
                    "status": "no-evidence",
                    "kind": "hum",
                    "guide_duration_seconds": 1.0,
                    "unit_start_seconds": 0.2,
                    "unit_end_seconds": 1.2,
                    "search_seconds": 0.75,
                    "guide_note_count": 0,
                    "accepted_note_count": 0,
                    "detection": {"method": "fixture"},
                    "alignment": {"status": "no-evidence"},
                    "warnings": ["fixture no evidence"],
                    "source_pitch_support_required": True,
                    "raw_candidates_mutated": False,
                },
            )
            guided = root / "profile-guided-review"
            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=_fake_render,
            ), patch(
                "sunofriend.phrase_review._evaluate_alternative",
                return_value=_evaluation(),
            ), patch(
                "sunofriend.phrase_guide.prepare_short_guide",
                return_value=no_evidence,
            ):
                build_guided_melody_phrase_review(
                    parent,
                    unit=1,
                    guide_path=guide,
                    out_dir=guided,
                )
            guided_manifest = json.loads(
                (guided / "phrase_review.json").read_text()
            )
            self.assertEqual(
                guided_manifest["personal_ranking"]["profile"]["sha256"],
                manifest["personal_ranking"]["profile"]["sha256"],
            )
            self.assertEqual(
                len(guided_manifest["phrases"][0]["personal_ranking"]["ranking"]),
                4,
            )

            profile.write_text(profile.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "profile hash"):
                build_guided_melody_phrase_review(
                    parent,
                    unit=1,
                    guide_path=guide,
                    out_dir=root / "tampered-profile-guided-review",
                )

    def test_merges_note_clusters_into_two_bar_review_units(self):
        records = [
            {
                "phrase_index": index,
                "start_seconds": start,
                "end_seconds": end,
                "note_count": notes,
                "providers": ["basic-pitch"],
                "mean_agreement_ratio": agreement,
                "mean_selection_score": score,
            }
            for index, (start, end, notes, agreement, score) in enumerate(
                [
                    (0.50, 1.90, 4, 0.63, 0.77),
                    (2.52, 3.53, 4, 0.45, 0.70),
                    (4.53, 4.72, 1, 0.44, 0.71),
                    (5.24, 5.42, 1, 0.44, 0.70),
                    (7.09, 7.87, 3, 0.49, 0.74),
                    (9.10, 9.61, 2, 0.57, 0.77),
                    (10.85, 12.93, 6, 0.53, 0.74),
                    (13.36, 13.68, 1, 0.46, 0.70),
                    (14.78, 14.90, 1, 0.50, 0.72),
                ]
            )
        ]
        original = json.loads(json.dumps(records))

        units, policy = _merge_phrase_records(
            records,
            duration_seconds=15.0,
            bpm=120.0,
            minimum_bars=2,
            maximum_bars=8,
            beats_per_bar=4,
        )

        self.assertEqual(records, original)
        self.assertEqual(len(units), 3)
        self.assertEqual(
            [unit["source_phrase_indices"] for unit in units],
            [[0, 1, 2], [3, 4, 5], [6, 7, 8]],
        )
        self.assertTrue(
            all(unit["length_status"] == "within-range" for unit in units)
        )
        self.assertTrue(all(2.0 <= unit["duration_bars"] <= 8.0 for unit in units))
        self.assertEqual(policy["source_phrase_count"], 9)
        self.assertEqual(policy["review_unit_count"], 3)
        self.assertEqual(policy["short_unit_count"], 0)
        self.assertFalse(policy["raw_phrase_records_mutated"])

    def test_rejects_invalid_review_unit_bar_range(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            _merge_phrase_records(
                [
                    {
                        "phrase_index": 0,
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                        "note_count": 1,
                        "providers": [],
                        "mean_agreement_ratio": 0.5,
                        "mean_selection_score": 0.5,
                    }
                ],
                duration_seconds=2.0,
                bpm=120.0,
                minimum_bars=9,
                maximum_bars=8,
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
