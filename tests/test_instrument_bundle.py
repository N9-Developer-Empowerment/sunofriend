from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.instrument_bundle import build_instrument_bundle
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
