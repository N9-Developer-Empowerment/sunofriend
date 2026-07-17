from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.cli import _find_exact_stem, main
from sunofriend.models import NoteEvent
from sunofriend.vocal import (
    PitchFrame,
    VocalConfig,
    fractional_midi_to_hz,
    select_backing_vocal_variants,
    transcribe_vocal_frames,
)


def _lead_result(tuning_hz: float = 429.0):
    frames = [
        PitchFrame(
            time=index * 0.01,
            f0_hz=fractional_midi_to_hz(60.0 if index < 50 else 64.0, tuning_hz),
            voiced_probability=0.95,
            rms=0.1 if index < 50 else 0.2,
            onset_strength=0.8 if index in {0, 50} else 0.0,
            source="synthetic",
        )
        for index in range(100)
    ]
    return transcribe_vocal_frames(
        frames,
        config=VocalConfig(
            role="lead",
            tuning_hz=tuning_hz,
            tuning_source="parent-folder",
            bpm=85.0,
        ),
    )


class VocalCliTests(unittest.TestCase):
    def test_melody_profile_routes_reviewed_choices_to_fresh_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "reviewed-first.json"
            second = Path(tmp) / "reviewed-second.json"
            output = Path(tmp) / "profile.json"
            result = {
                "status": "complete",
                "explicit_choice_count": 4,
            }

            with patch(
                "sunofriend.melody_profile.build_personal_melody_profile",
                return_value=result,
            ) as build, redirect_stdout(StringIO()):
                status = main(
                    [
                        "melody-profile",
                        str(first),
                        str(second),
                        "--out",
                        str(output),
                    ]
                )

            self.assertEqual(status, 0)
            build.assert_called_once_with(
                [str(first), str(second)],
                out_path=str(output),
            )

    def test_melody_guide_routes_one_unit_to_fresh_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / "review"
            guide = Path(tmp) / "guide.wav"
            output = Path(tmp) / "guided"
            result = {
                "status": "review-required",
                "guide": {"status": "complete"},
            }

            with patch(
                "sunofriend.phrase_review.build_guided_melody_phrase_review",
                return_value=result,
            ) as build, redirect_stdout(StringIO()):
                status = main(
                    [
                        "melody-guide",
                        str(review),
                        "--unit",
                        "2",
                        "--guide",
                        str(guide),
                        "--guide-kind",
                        "tap",
                        "--search-seconds",
                        "0.4",
                        "--out-dir",
                        str(output),
                    ]
                )

            self.assertEqual(status, 0)
            build.assert_called_once_with(
                str(review),
                unit=2,
                guide_path=str(guide),
                out_dir=str(output),
                guide_kind="tap",
                search_seconds=0.4,
            )

    def test_melody_review_routes_tracker_run_and_fresh_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "tracker-run"
            output = Path(tmp) / "review"
            source = Path(tmp) / "moved.wav"
            ranking_profile = Path(tmp) / "profile.json"
            result = {
                "status": "review-required",
                "phrase_count": 2,
            }

            with patch(
                "sunofriend.phrase_review.build_melody_phrase_review",
                return_value=result,
            ) as build, redirect_stdout(StringIO()):
                status = main(
                    [
                        "melody-review",
                        str(run),
                        "--out-dir",
                        str(output),
                        "--source-stem",
                        str(source),
                        "--padding-seconds",
                        "0.4",
                        "--minimum-bars",
                        "3",
                        "--maximum-bars",
                        "6",
                        "--beats-per-bar",
                        "3",
                        "--ranking-profile",
                        str(ranking_profile),
                    ]
                )

            self.assertEqual(status, 0)
            build.assert_called_once_with(
                str(run),
                out_dir=str(output),
                source_stem=str(source),
                padding_seconds=0.4,
                minimum_bars=3,
                maximum_bars=6,
                beats_per_bar=3,
                ranking_profile=str(ranking_profile),
            )

    def test_vocal_trackers_routes_independent_evidence_and_rmvpe_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            stem = Path(tmp) / "voice.wav"
            stem.touch()
            rmvpe = Path(tmp) / "rmvpe.frames.json"
            rmvpe.touch()
            game = Path(tmp) / "game.candidate.json"
            game.touch()
            output = Path(tmp) / "runs"
            manifest = {
                "schema": "sunofriend.vocal-tracker-run.v1",
                "status": "complete",
            }

            with patch(
                "sunofriend.vocal_trackers.run_vocal_tracker_bakeoff",
                return_value=manifest,
            ) as run, redirect_stdout(StringIO()):
                status = main(
                    [
                        "vocal-trackers",
                        str(stem),
                        "--role",
                        "lead",
                        "--bpm",
                        "119",
                        "--tuning-hz",
                        "440",
                        "--rmvpe-frames",
                        str(rmvpe),
                        "--game-candidate",
                        str(game),
                        "--out-dir",
                        str(output),
                        "--run-id",
                        "fixture-run",
                    ]
                )

            self.assertEqual(status, 0)
            run.assert_called_once_with(
                audio_path=stem,
                out_dir=str(output),
                bpm=119.0,
                role="lead",
                tuning_hz=440.0,
                fmin_hz=65.4,
                fmax_hz=1046.5,
                rmvpe_frames_path=str(rmvpe),
                game_candidate_path=str(game),
                run_id="fixture-run",
            )

    def test_optional_muscriptor_challenger_is_published_without_replacing_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Song-C major-85bpm-440hz"
            folder.mkdir()
            stem = folder / "Song-vocals-C major-85bpm-440hz.wav"
            stem.touch()
            checkpoint = Path(tmp) / "model.safetensors"
            checkpoint.write_bytes(b"accepted-model")
            output = Path(tmp) / "out"
            baseline_result = _lead_result(tuning_hz=440.0)

            def fake_ai_run(**arguments):
                run_dir = Path(arguments["out_dir"]) / "run-1"
                run_dir.mkdir(parents=True)
                candidate = {
                    "schema": "sunofriend.ai-transcription-candidate.v1",
                    "backend": "muscriptor",
                    "model_version": "test-small",
                    "notes": [
                        {
                            "start_seconds": 0.0,
                            "end_seconds": 0.48,
                            "pitch": 60.0,
                            "confidence": None,
                            "instrument": "voice",
                            "velocity": None,
                            "source_event_id": "event-0",
                        },
                        {
                            "start_seconds": 0.5,
                            "end_seconds": 0.98,
                            "pitch": 64.0,
                            "confidence": None,
                            "instrument": "voice",
                            "velocity": None,
                            "source_event_id": "event-1",
                        },
                    ],
                    "warnings": [],
                    "raw_artifacts": [],
                    "metadata": {},
                }
                (run_dir / "candidate.json").write_text(json.dumps(candidate))
                (run_dir / "candidate.mid").write_bytes(b"raw-midi")
                expression = {
                    "schema": "sunofriend.ai-source-expression.v1",
                    "status": "complete",
                    "notes": [
                        {
                            "candidate_index": 0,
                            "velocity": 52,
                            "velocity_source": "source-relative-energy",
                        },
                        {
                            "candidate_index": 1,
                            "velocity": 110,
                            "velocity_source": "source-relative-energy",
                        },
                    ],
                    "velocity_summary": {
                        "count": 2,
                        "minimum": 52,
                        "maximum": 110,
                        "median": 81.0,
                        "distinct": 2,
                    },
                }
                (run_dir / "candidate.expression.json").write_text(
                    json.dumps(expression)
                )
                (run_dir / "candidate.expression.mid").write_bytes(
                    b"expression-midi"
                )
                (run_dir / "run.json").write_text("{}")
                return {
                    "run_id": "run-1",
                    "checkpoint": {"sha256": "checkpoint-sha"},
                }

            with patch(
                "sunofriend.vocal.transcribe_vocal_melody",
                return_value=baseline_result,
            ), patch(
                "sunofriend.ai_runtime.resolve_muscriptor_checkpoint",
                return_value=checkpoint,
            ), patch(
                "sunofriend.ai_bakeoff.run_ai_transcription",
                side_effect=fake_ai_run,
            ) as ai_run, redirect_stdout(StringIO()):
                status = main(
                    [
                        "vocal-melody",
                        str(stem),
                        "--role",
                        "lead",
                        "--out-dir",
                        str(output),
                        "--muscriptor",
                    ]
                )

            self.assertEqual(status, 0)
            ai_run.assert_called_once()
            self.assertEqual(ai_run.call_args.kwargs["roles"], ("voice",))
            self.assertEqual(
                ai_run.call_args.kwargs["options"],
                {"device": "cpu", "beam_size": 1},
            )
            summary = json.loads((output / "vocal_summary.json").read_text())
            self.assertEqual(
                summary["primary_variant"], baseline_result.primary_variant
            )
            self.assertEqual(summary["variants"]["muscriptor"]["notes"], 2)
            self.assertEqual(
                summary["variants"]["muscriptor"]["velocity_summary"][
                    "maximum"
                ],
                110,
            )
            self.assertEqual(
                summary["variants"]["muscriptor"]["selection_policy"],
                "explicit challenger; never automatic primary",
            )
            self.assertTrue(
                (output / "variants/lead_vocal-muscriptor.mid").is_file()
            )
            provenance = json.loads(
                (
                    output / "variants/lead_vocal-muscriptor.provenance.json"
                ).read_text()
            )
            self.assertEqual(provenance["counts"]["notes"], 2)
            self.assertEqual(
                provenance["notes"][0]["details"]["source_event_id"],
                "event-0",
            )
            self.assertEqual(provenance["notes"][0]["velocity"], 52)
            self.assertEqual(
                provenance["notes"][1]["details"]["velocity_source"],
                "source-relative-energy",
            )

    def test_seeded_game_and_muscriptor_publish_as_separate_challengers(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Song-C major-85bpm-440hz"
            folder.mkdir()
            stem = folder / "Song-vocals-C major-85bpm-440hz.wav"
            stem.touch()
            muscriptor_model = Path(tmp) / "model.safetensors"
            muscriptor_model.write_bytes(b"accepted-model")
            game_model = Path(tmp) / "game-model"
            game_model.mkdir()
            output = Path(tmp) / "out"
            baseline_result = _lead_result(tuning_hz=440.0)

            def fake_ai_run(**arguments):
                backend = arguments["backend"]
                run_id = f"run-{backend}"
                run_dir = Path(arguments["out_dir"]) / run_id
                run_dir.mkdir(parents=True)
                candidate = {
                    "schema": "sunofriend.ai-transcription-candidate.v1",
                    "backend": backend,
                    "model_version": f"{backend}-test",
                    "notes": [
                        {
                            "start_seconds": 0.0,
                            "end_seconds": 0.48,
                            "pitch": 60.25,
                            "confidence": None,
                            "instrument": "voice",
                            "velocity": None,
                            "source_event_id": f"{backend}-0",
                        },
                        {
                            "start_seconds": 0.5,
                            "end_seconds": 0.98,
                            "pitch": 64.75,
                            "confidence": None,
                            "instrument": "voice",
                            "velocity": None,
                            "source_event_id": f"{backend}-1",
                        },
                    ],
                    "warnings": [],
                    "raw_artifacts": [],
                    "metadata": {"seed": 17} if backend == "game" else {},
                }
                (run_dir / "candidate.json").write_text(json.dumps(candidate))
                (run_dir / "candidate.mid").write_bytes(b"raw-midi")
                (run_dir / "candidate.quality.json").write_text(
                    json.dumps({"status": "pass", "warnings": []})
                )
                expression = {
                    "schema": "sunofriend.ai-source-expression.v1",
                    "status": "complete",
                    "notes": [
                        {
                            "candidate_index": 0,
                            "velocity": 58,
                            "velocity_source": "source-relative-energy",
                        },
                        {
                            "candidate_index": 1,
                            "velocity": 104,
                            "velocity_source": "source-relative-energy",
                        },
                    ],
                    "velocity_summary": {
                        "count": 2,
                        "minimum": 58,
                        "maximum": 104,
                        "median": 81.0,
                        "distinct": 2,
                    },
                }
                (run_dir / "candidate.expression.json").write_text(
                    json.dumps(expression)
                )
                (run_dir / "candidate.expression.mid").write_bytes(
                    b"expression-midi"
                )
                (run_dir / "run.json").write_text("{}")
                return {
                    "run_id": run_id,
                    "checkpoint": {"sha256": f"{backend}-checkpoint-sha"},
                }

            with patch(
                "sunofriend.vocal.transcribe_vocal_melody",
                return_value=baseline_result,
            ), patch(
                "sunofriend.ai_runtime.resolve_muscriptor_checkpoint",
                return_value=muscriptor_model,
            ), patch(
                "sunofriend.ai_runtime.resolve_game_model",
                return_value=game_model,
            ), patch(
                "sunofriend.ai_bakeoff.run_ai_transcription",
                side_effect=fake_ai_run,
            ) as ai_run, redirect_stdout(StringIO()):
                status = main(
                    [
                        "vocal-melody",
                        str(stem),
                        "--role",
                        "lead",
                        "--out-dir",
                        str(output),
                        "--muscriptor",
                        "--game",
                        "--game-language",
                        "en",
                        "--game-seed",
                        "17",
                        "--no-correction-report",
                    ]
                )

            self.assertEqual(status, 0)
            self.assertEqual(ai_run.call_count, 2)
            calls = {
                call.kwargs["backend"]: call.kwargs
                for call in ai_run.call_args_list
            }
            self.assertEqual(
                calls["game"]["options"],
                {
                    "device": "cpu",
                    "language": "en",
                    "seed": 17,
                    "boundary_threshold": 0.2,
                    "boundary_radius_ms": 20.0,
                    "presence_threshold": 0.2,
                    "game_steps": 8,
                },
            )
            summary = json.loads((output / "vocal_summary.json").read_text())
            self.assertEqual(
                summary["primary_variant"], baseline_result.primary_variant
            )
            self.assertEqual(
                set(summary["ai_challengers"]), {"muscriptor", "game"}
            )
            self.assertEqual(summary["variants"]["game"]["model_version"], "game-test")
            self.assertEqual(summary["variants"]["game"]["model_metadata"]["seed"], 17)
            self.assertEqual(
                summary["variants"]["game"]["selection_policy"],
                "explicit challenger; never automatic primary",
            )
            self.assertTrue((output / "variants/lead_vocal-game.mid").is_file())
            self.assertTrue(
                (output / "variants/lead_vocal-muscriptor.mid").is_file()
            )
            provenance = json.loads(
                (output / "variants/lead_vocal-game.provenance.json").read_text()
            )
            self.assertEqual(provenance["notes"][0]["sources"], ["game"])
            self.assertEqual(provenance["notes"][0]["details"]["raw_pitch"], 60.25)

    def test_repeatable_short_hum_snippet_can_patch_primary_melody(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Song-C major-85bpm-429hz"
            folder.mkdir()
            stem = folder / "Song-vocals-C major-85bpm-429hz.wav"
            stem.touch()
            reference = Path(tmp) / "verse-reference.wav"
            hum = Path(tmp) / "verse-hum.wav"
            soundfile.write(reference, np.zeros(160_000, dtype=np.float32), 16_000)
            soundfile.write(hum, np.zeros(160_000, dtype=np.float32), 16_000)
            output = Path(tmp) / "out"

            with patch(
                "sunofriend.vocal.transcribe_vocal_melody",
                return_value=_lead_result(),
            ), patch(
                "sunofriend.melody_correction._transcribe_hummed_notes",
                return_value=([NoteEvent(0.0, 0.35, 55, 84)], []),
            ), redirect_stdout(StringIO()):
                status = main(
                    [
                        "vocal-melody",
                        str(stem),
                        "--role",
                        "lead",
                        "--guide-snippet",
                        str(reference),
                        str(hum),
                        "0",
                        "--prefer-guide",
                        "--out-dir",
                        str(output),
                    ]
                )

            self.assertEqual(status, 0)
            summary = json.loads((output / "vocal_summary.json").read_text())
            self.assertEqual(summary["primary_variant"], "snippet_patched")
            self.assertEqual(summary["guide_alignment"]["mode"], "snippets")
            self.assertEqual(
                summary["guide_alignment"]["accepted_snippet_count"], 1
            )
            self.assertIn("snippet_patched", summary["variants"])

    def test_exact_stem_lookup_does_not_confuse_backing_and_lead_vocals(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            backing = folder / "Song-backing_vocals-C major-85bpm-429hz.wav"
            lead = folder / "Song-vocals-C major-85bpm-429hz.wav"
            backing.touch()
            lead.touch()

            self.assertEqual(_find_exact_stem(folder, "vocals"), lead)
            self.assertEqual(_find_exact_stem(folder, "backing_vocals"), backing)

    def test_command_infers_metadata_and_publishes_tuned_and_concert_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Song-C major-85bpm-429hz"
            folder.mkdir()
            stem = folder / "Song-vocals-C major-85bpm-429hz.wav"
            stem.touch()
            output = Path(tmp) / "out"
            result = _lead_result()

            with patch(
                "sunofriend.vocal.transcribe_vocal_melody",
                return_value=result,
            ), redirect_stdout(StringIO()):
                status = main(
                    [
                        "vocal-melody",
                        str(stem),
                        "--role",
                        "lead",
                        "--out-dir",
                        str(output),
                    ]
                )

            self.assertEqual(status, 0)
            summary = json.loads((output / "vocal_summary.json").read_text())
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["bpm"], 85.0)
            self.assertEqual(summary["tuning_hz"], 429.0)
            self.assertAlmostEqual(summary["garageband_fine_tune_cents"], -43.831051)
            tuned = (output / "lead_vocal_melody.mid").read_bytes()
            concert = (output / "variants/lead_vocal-concert-pitch.mid").read_bytes()
            self.assertIn(bytes([0xB2, 101, 0]), tuned)
            self.assertNotIn(bytes([0xB2, 101, 0]), concert)
            provenance = json.loads((output / "lead_vocal_provenance.json").read_text())
            self.assertEqual(provenance["counts"]["notes"], 2)
            self.assertTrue((output / "melody_correction.html").is_file())
            self.assertTrue((output / "melody_corrections.json").is_file())
            self.assertEqual(
                summary["correction"]["html"],
                str(output / "melody_correction.html"),
            )

    def test_no_evidence_is_a_successful_explicit_result_without_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Song-G major-93bpm-441hz"
            folder.mkdir()
            stem = folder / "Song-backing_vocals-G major-93bpm-441hz.wav"
            stem.touch()
            output = Path(tmp) / "out"
            result = select_backing_vocal_variants(
                [],
                config=VocalConfig(
                    role="backing",
                    tuning_hz=441.0,
                    tuning_source="parent-folder",
                    bpm=93.0,
                ),
            )

            with patch(
                "sunofriend.vocal.transcribe_vocal_melody",
                return_value=result,
            ), redirect_stdout(StringIO()):
                status = main(
                    [
                        "vocal-melody",
                        str(stem),
                        "--role",
                        "backing",
                        "--out-dir",
                        str(output),
                    ]
                )

            self.assertEqual(status, 0)
            summary = json.loads((output / "vocal_summary.json").read_text())
            self.assertEqual(summary["status"], "no-evidence")
            self.assertIsNone(summary["primary_midi"])
            self.assertFalse((output / "backing_vocal_melody.mid").exists())


if __name__ == "__main__":
    unittest.main()
