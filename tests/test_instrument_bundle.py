from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.instrument_bundle import build_instrument_bundle
from sunofriend.instrument_preference import (
    build_personal_instrument_profile,
    record_instrument_patch_feedback,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class InstrumentBundleTests(unittest.TestCase):
    def _source(self, root: Path) -> tuple[Path, Path]:
        sample_rate = 16_000
        times = np.arange(round(1.2 * sample_rate), dtype=np.float32) / sample_rate
        audio = np.zeros_like(times)
        first = (0.35 * np.sin(2 * np.pi * 261.63 * times[:5600])).astype(np.float32)
        second = (0.30 * np.sin(2 * np.pi * 329.63 * times[:5600])).astype(np.float32)
        audio[1600:7200] = first
        audio[9600:15200] = second
        stem = root / "lead.wav"
        midi = root / "lead.mid"
        soundfile.write(stem, audio, sample_rate)
        write_midi_file(
            midi,
            [
                MidiTrack(
                    "Lead",
                    0,
                    80,
                    [
                        NoteEvent(0.1, 0.45, 60, 100),
                        NoteEvent(0.6, 0.95, 64, 96),
                    ],
                )
            ],
            bpm=120.0,
        )
        return stem, midi

    def test_bundle_keeps_editable_midi_source_sound_and_match_recipe_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._source(root)
            output = root / "bundle"

            report = build_instrument_bundle(
                stem,
                midi,
                kind="lead",
                out_dir=output,
                include_factory=False,
                include_gm=False,
                render_preview=False,
            )

            self.assertEqual(report["status"], "complete")
            self.assertTrue((output / "performance.mid").is_file())
            self.assertTrue((output / "source-reference.wav").is_file())
            self.assertTrue((output / "matches/instrument_matches.json").is_file())
            self.assertTrue(
                (output / "source-instrument/sunofriend-instrument.sf2").is_file()
            )
            recipe = json.loads((output / "instrument_recipe.json").read_text())
            self.assertEqual(recipe["format"], "sunofriend-instrument-bundle-v1")
            self.assertFalse(recipe["garageband"]["factory_content_embedded"])
            self.assertEqual(
                recipe["sound"]["source_instrument"]["soundfont"],
                "sunofriend-instrument.sf2",
            )
            self.assertEqual(
                recipe["match"]["source_event_clusters"],
                "matches/source_event_clusters.json",
            )
            self.assertTrue((output / "matches/source_event_clusters.svg").is_file())
            self.assertTrue((output / "matches/source_event_dynamics.json").is_file())
            self.assertTrue((output / "matches/source_event_dynamics.svg").is_file())
            self.assertTrue(
                (output / "source-instrument/source_event_clusters.json").is_file()
            )
            self.assertTrue(
                (output / "source-instrument/source_event_dynamics.json").is_file()
            )
            self.assertTrue(
                (output / "source-instrument/source_sample_loops.json").is_file()
            )
            self.assertTrue(
                (output / "source-instrument/source_sample_loops.svg").is_file()
            )
            self.assertTrue(
                (output / "source-instrument/instrument_usability.json").is_file()
            )
            self.assertEqual(
                recipe["match"]["source_event_dynamics"],
                "matches/source_event_dynamics.json",
            )
            self.assertEqual(
                recipe["sound"]["source_instrument"][
                    "sample_loop_suggestions_report"
                ],
                "source-instrument/source_sample_loops.json",
            )
            self.assertEqual(
                recipe["sound"]["source_instrument"]["status"], "review-required"
            )
            self.assertEqual(
                recipe["sound"]["source_instrument"]["usability_summary"][
                    "functional_status"
                ],
                "pass",
            )
            self.assertEqual(
                recipe["selection"]["source_instrument_role"],
                "review-required-primary-candidate",
            )
            self.assertEqual(report["preference_profile_status"], "not-requested")

    def test_bundle_carries_advisory_explicit_patch_history_without_selecting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._source(root)
            evidence = root / "feedback-source-bundle"
            evidence.mkdir()
            (evidence / "performance.mid").write_bytes(midi.read_bytes())
            (evidence / "instrument_bundle.json").write_text(
                json.dumps(
                    {
                        "operation": "instrument-bundle",
                        "format": "sunofriend-instrument-bundle-v1",
                        "status": "complete",
                        "kind": "keys",
                        "stem": str(stem),
                        "midi": str(midi),
                        "source_instrument_status": "texture-only",
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "instrument_recipe.json").write_text(
                json.dumps(
                    {
                        "format": "sunofriend-instrument-bundle-v1",
                        "format_version": 1,
                        "kind": "keys",
                    }
                ),
                encoding="utf-8",
            )
            feedback = root / "feedback.json"
            profile = root / "profile.json"
            record_instrument_patch_feedback(
                evidence,
                patch_name="Small Time Piano",
                out_path=feedback,
            )
            build_personal_instrument_profile([feedback], out_path=profile)
            output = root / "bundle"

            report = build_instrument_bundle(
                stem,
                midi,
                kind="keys",
                out_dir=output,
                include_factory=False,
                include_gm=False,
                render_preview=False,
                preference_profile_path=profile,
            )

            recipe = json.loads((output / "instrument_recipe.json").read_text())
            preference = recipe["selection"]["personal_preference"]
            self.assertEqual(report["preference_profile_status"], "advisory")
            self.assertTrue((output / "preference-profile.json").is_file())
            self.assertEqual(
                report["artifacts"]["preference_profile"],
                "preference-profile.json",
            )
            self.assertEqual(preference["history_first"], "Small Time Piano")
            self.assertFalse(preference["automatic_selection"])
            self.assertFalse(preference["match_ranking_changed"])
            self.assertFalse(preference["playability_gate_bypassed"])
            self.assertIn(
                "Small Time Piano", " ".join(recipe["garageband"]["steps"])
            )
            self.assertEqual(
                " ".join(recipe["garageband"]["steps"]).count("Small Time Piano"),
                1,
            )
            self.assertIsNone(recipe["match"]["best_rendered_gm_proxy"])
            self.assertIsNone(recipe["match"]["best_garageband_factory_asset"])

    def test_bundle_demotes_incomplete_source_sampler_to_texture_layer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._source(root)
            write_midi_file(
                midi,
                [
                    MidiTrack(
                        "Lead",
                        0,
                        80,
                        [
                            NoteEvent(0.1, 0.45, 60, 100),
                            NoteEvent(0.6, 0.95, 64, 96),
                            NoteEvent(1.0, 1.15, 90, 100),
                        ],
                    )
                ],
                bpm=120.0,
            )
            output = root / "bundle"

            report = build_instrument_bundle(
                stem,
                midi,
                kind="lead",
                out_dir=output,
                include_factory=False,
                include_gm=False,
                render_preview=False,
            )

            recipe = json.loads((output / "instrument_recipe.json").read_text())
            source_sound = recipe["sound"]["source_instrument"]
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["source_instrument_status"], "texture-only")
            self.assertEqual(source_sound["status"], "texture-only")
            self.assertEqual(
                source_sound["usability_summary"]["functional_status"], "fail"
            )
            self.assertEqual(
                recipe["selection"]["primary_strategy"],
                "complete-garageband-or-gm-instrument",
            )
            self.assertEqual(
                recipe["selection"]["source_instrument_role"],
                "optional-texture-layer",
            )
            readme = (output / "README.md").read_text()
            self.assertIn("texture-only", readme)
            self.assertIn("Use a complete GarageBand or GM instrument", readme)
            self.assertIn("not a primary instrument", " ".join(report["warnings"]))
            self.assertIn("optional texture", recipe["garageband"]["reason"])

    def test_bundle_reports_partial_when_safe_sampling_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._source(root)
            output = root / "bundle"
            with patch(
                "sunofriend.instrument_match.build_sample_pack",
                side_effect=ValueError("no isolated notes"),
            ):
                report = build_instrument_bundle(
                    stem,
                    midi,
                    kind="lead",
                    out_dir=output,
                    include_factory=False,
                    include_gm=False,
                    render_preview=False,
                )

            self.assertEqual(report["status"], "partial")
            self.assertTrue((output / "performance.mid").is_file())
            self.assertFalse((output / "source-instrument").exists())
            self.assertIn("no isolated notes", " ".join(report["warnings"]))

    def test_bundle_carries_drum_family_review_midi_wav_and_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._source(root)
            source_audio, sample_rate = soundfile.read(stem, dtype="float32")
            soundfont = root / "fixture.sf2"
            soundfont.write_bytes(b"fixture-soundfont")
            output = root / "drum-bundle"

            def fake_render(_midi_path, wav_path, **_kwargs):
                soundfile.write(wav_path, source_audio, sample_rate)
                return Path(wav_path)

            with (
                patch("sunofriend.render.find_soundfont", return_value=str(soundfont)),
                patch("sunofriend.render.render_midi_to_wav", side_effect=fake_render),
            ):
                report = build_instrument_bundle(
                    stem,
                    midi,
                    kind="kick",
                    out_dir=output,
                    include_factory=False,
                    include_gm=True,
                    build_source_instrument=False,
                    render_preview=False,
                )

            self.assertEqual(report["status"], "complete")
            self.assertTrue((output / "matches/gm_drum_family_mapping.json").is_file())
            self.assertTrue((output / "previews/gm-drum-family-proposal.mid").is_file())
            self.assertTrue((output / "previews/gm-drum-family-proposal.wav").is_file())
            recipe = json.loads((output / "instrument_recipe.json").read_text())
            self.assertEqual(
                recipe["match"]["gm_drum_family_mapping"],
                "matches/gm_drum_family_mapping.json",
            )
            self.assertTrue(
                recipe["match"]["gm_drum_family_mapping_summary"][
                    "candidate_timbre_family_count"
                ]
                >= 1
            )
            self.assertIn(
                "previews/gm-drum-family-proposal.mid",
                " ".join(recipe["garageband"]["steps"]),
            )


if __name__ == "__main__":
    unittest.main()
