from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.instrument_loops import (
    SAMPLE_LOOP_SUGGESTIONS_SCHEMA,
    analyze_sample_loop_suggestions,
    sample_loop_suggestions_svg,
)


SAMPLE_RATE = 16_000


class InstrumentLoopSuggestionTests(unittest.TestCase):
    def test_stationary_pitched_sample_gets_repeatable_review_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            for directory in (first, second):
                (directory / "samples").mkdir(parents=True)
                time = np.arange(round(1.6 * SAMPLE_RATE)) / SAMPLE_RATE
                envelope = np.minimum(1.0, time / 0.08)
                audio = (0.32 * envelope * np.sin(2.0 * np.pi * 220.0 * time)).astype(
                    np.float32
                )
                soundfile.write(
                    directory / "samples/a3.wav", audio, SAMPLE_RATE, subtype="PCM_24"
                )

            samples = [{"file": "samples/a3.wav", "pitch": 57}]
            report = analyze_sample_loop_suggestions(first, samples, kind="bass")
            repeated = analyze_sample_loop_suggestions(second, samples, kind="bass")

            self.assertEqual(report["schema"], SAMPLE_LOOP_SUGGESTIONS_SCHEMA)
            self.assertEqual(report["status"], "complete")
            self.assertTrue(report["advisory_only"])
            self.assertTrue(report["review_required"])
            self.assertEqual(report["summary"]["candidate_sample_count"], 1)
            self.assertEqual(report["summary"]["suggested_loop_count"], 3)
            self.assertEqual(report["effects"]["looped_zones_added"], 0)
            suggestion = report["samples"][0]["suggestions"][0]
            self.assertLess(
                suggestion["loop_start_frame"], suggestion["loop_end_frame"]
            )
            self.assertGreaterEqual(suggestion["loop_length_seconds"], 0.24)
            self.assertIn("waveform_continuity", suggestion)
            self.assertIn("representation_continuity", suggestion)
            self.assertEqual(suggestion["selection_effect"], "none")
            self.assertTrue((first / suggestion["audition"]).is_file())
            self.assertEqual(
                [row["audition_sha256"] for row in report["samples"][0]["suggestions"]],
                [
                    row["audition_sha256"]
                    for row in repeated["samples"][0]["suggestions"]
                ],
            )
            self.assertEqual(
                [
                    (
                        row["loop_start_frame"],
                        row["loop_end_frame"],
                        row["continuity_score"],
                    )
                    for row in report["samples"][0]["suggestions"]
                ],
                [
                    (
                        row["loop_start_frame"],
                        row["loop_end_frame"],
                        row["continuity_score"],
                    )
                    for row in repeated["samples"][0]["suggestions"]
                ],
            )
            svg = sample_loop_suggestions_svg(report)
            self.assertIn("Advisory sample-loop boundaries", svg)
            self.assertIn("MIDI 57", svg)

    def test_short_and_percussive_samples_are_not_suggested(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "samples").mkdir()
            time = np.arange(round(0.30 * SAMPLE_RATE)) / SAMPLE_RATE
            audio = (0.4 * np.sin(2.0 * np.pi * 110.0 * time)).astype(np.float32)
            soundfile.write(root / "samples/hit.wav", audio, SAMPLE_RATE)
            samples = [{"file": "samples/hit.wav", "pitch": 36}]

            pitched = analyze_sample_loop_suggestions(root, samples, kind="bass")
            drums = analyze_sample_loop_suggestions(root, samples, kind="kick")

            self.assertEqual(pitched["samples"][0]["status"], "too-short")
            self.assertEqual(pitched["summary"]["suggested_loop_count"], 0)
            self.assertEqual(drums["status"], "not-applicable")
            self.assertEqual(drums["samples"][0]["status"], "not-applicable")
            self.assertEqual(drums["summary"]["suggested_loop_count"], 0)
            self.assertFalse((root / "loop-auditions").exists())


if __name__ == "__main__":
    unittest.main()
