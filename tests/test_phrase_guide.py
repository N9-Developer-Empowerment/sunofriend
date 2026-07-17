from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.models import NoteEvent
from sunofriend.phrase_guide import load_pyin_frames, prepare_short_guide
from sunofriend.vocal import PitchFrame, fractional_midi_to_hz


def _source_frames() -> list[PitchFrame]:
    return [
        PitchFrame(
            time=index * 0.02,
            f0_hz=fractional_midi_to_hz(
                64.0 if index < 75 else 67.0,
                440.0,
            ),
            voiced_probability=0.92,
            rms=0.1,
            onset_strength=0.5 if index in {50, 75} else 0.0,
            source="pyin",
        )
        for index in range(150)
    ]


class PhraseGuideTests(unittest.TestCase):
    def _guide(self, root: Path) -> Path:
        path = root / "guide.wav"
        soundfile.write(path, np.zeros(24_000, dtype=np.float32), 8_000)
        return path

    def test_loads_hash_bound_pyin_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pyin.evidence.json"
            document = {
                "schema": "sunofriend.vocal-tracker-evidence.v1",
                "tracker": "pyin",
                "source": {"sha256": "source-hash"},
                "frame_fields": [
                    "time_seconds",
                    "frequency_hz",
                    "confidence",
                    "rms",
                    "onset_strength",
                    "source",
                ],
                "frames": [
                    [0.0, 261.63, 0.9, 0.1, 0.4, "pyin"],
                    [0.1, None, 0.2, 0.01, 0.0, "pyin"],
                ],
            }
            path.write_text(json.dumps(document), encoding="utf-8")

            frames = load_pyin_frames(path, source_sha256="source-hash")

            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0].f0_hz, 261.63)
            self.assertIsNone(frames[1].f0_hz)
            with self.assertRaisesRegex(ValueError, "source hash"):
                load_pyin_frames(path, source_sha256="different")

    def test_hum_contour_is_transposed_and_gated_by_source_pitch(self):
        with tempfile.TemporaryDirectory() as directory:
            guide = self._guide(Path(directory))
            guide_notes = [
                NoteEvent(0.0, 0.45, 55, 80),
                NoteEvent(0.5, 0.95, 58, 90),
            ]

            with patch(
                "sunofriend.phrase_guide.transcribe_short_pitch_guide",
                return_value=(guide_notes, []),
            ):
                result = prepare_short_guide(
                    guide,
                    kind="hum",
                    source_frames=_source_frames(),
                    unit_start_seconds=1.0,
                    unit_end_seconds=2.0,
                    bpm=120.0,
                    tuning_hz=440.0,
                    search_seconds=0.2,
                )

            self.assertEqual(result.report["status"], "complete")
            self.assertEqual([note.pitch for note in result.notes], [64, 67])
            self.assertTrue(result.report["source_pitch_support_required"])
            self.assertTrue(
                all("source-contour" in record.sources for record in result.provenance)
            )

    def test_single_note_guide_uses_rhythm_but_ignores_guide_pitch(self):
        with tempfile.TemporaryDirectory() as directory:
            guide = self._guide(Path(directory))
            guide_notes = [
                NoteEvent(0.0, 0.45, 40, 72),
                NoteEvent(0.5, 0.95, 40, 99),
            ]

            with patch(
                "sunofriend.phrase_guide.transcribe_short_pitch_guide",
                return_value=(guide_notes, []),
            ):
                result = prepare_short_guide(
                    guide,
                    kind="single-note",
                    source_frames=_source_frames(),
                    unit_start_seconds=1.0,
                    unit_end_seconds=2.0,
                    bpm=120.0,
                    tuning_hz=440.0,
                    search_seconds=0.2,
                )

            self.assertEqual([note.pitch for note in result.notes], [64, 67])
            self.assertEqual([note.velocity for note in result.notes], [72, 99])
            self.assertTrue(result.report["alignment"]["guide_pitch_ignored"])
            self.assertTrue(
                all(
                    record.details["guide_pitch_ignored"]
                    for record in result.provenance
                )
            )

    def test_tap_guide_uses_detected_onsets_and_source_contour(self):
        with tempfile.TemporaryDirectory() as directory:
            guide = self._guide(Path(directory))
            taps = [
                NoteEvent(0.0, 0.4, 60, 75),
                NoteEvent(0.5, 0.9, 60, 100),
            ]
            detection = {"method": "fixture-onsets", "detected_onsets": 2}

            with patch(
                "sunofriend.phrase_guide._transcribe_tap_guide",
                return_value=(taps, detection),
            ):
                result = prepare_short_guide(
                    guide,
                    kind="tap",
                    source_frames=_source_frames(),
                    unit_start_seconds=1.0,
                    unit_end_seconds=2.0,
                    bpm=120.0,
                    tuning_hz=440.0,
                    search_seconds=0.2,
                )

            self.assertEqual([note.pitch for note in result.notes], [64, 67])
            self.assertEqual(result.report["detection"], detection)
            self.assertTrue(
                all("tap-guide" in record.sources for record in result.provenance)
            )

    def test_no_source_evidence_keeps_automatic_alternatives_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            guide = self._guide(Path(directory))
            with patch(
                "sunofriend.phrase_guide.transcribe_short_pitch_guide",
                return_value=([NoteEvent(0.0, 0.5, 60, 80)], []),
            ):
                result = prepare_short_guide(
                    guide,
                    kind="whistle",
                    source_frames=[],
                    unit_start_seconds=1.0,
                    unit_end_seconds=2.0,
                    bpm=120.0,
                    tuning_hz=440.0,
                )

            self.assertEqual(result.report["status"], "no-evidence")
            self.assertEqual(result.notes, ())
            self.assertEqual(result.provenance, ())
            self.assertTrue(
                any("remain unchanged" in value for value in result.report["warnings"])
            )


if __name__ == "__main__":
    unittest.main()
