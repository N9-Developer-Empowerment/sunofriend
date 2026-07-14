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
