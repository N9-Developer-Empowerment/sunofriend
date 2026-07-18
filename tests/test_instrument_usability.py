from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sunofriend.clip import read_midi_clips
from sunofriend.instrument_usability import (
    analyze_sample_instrument_usability,
    write_instrument_usability_audition,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class InstrumentUsabilityTests(unittest.TestCase):
    def _clip(self, root: Path, notes: list[NoteEvent], *, channel: int = 0):
        midi = root / "performance.mid"
        write_midi_file(
            midi,
            [MidiTrack("Keys", channel, 4, notes)],
            bpm=120.0,
        )
        return list(read_midi_clips(midi))[0]

    @staticmethod
    def _row(
        pitch: int,
        low_key: int,
        high_key: int,
        duration: float,
        *,
        tuning_status: str = "applied",
    ) -> dict[str, object]:
        return {
            "pitch": pitch,
            "low_key": low_key,
            "high_key": high_key,
            "low_velocity": 0,
            "high_velocity": 127,
            "start_seconds": 0.0,
            "end_seconds": duration,
            "sample_duration_seconds": duration,
            "tuning": {"status": tuning_status},
        }

    def test_unmapped_and_too_short_pitched_notes_make_bank_texture_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clip = self._clip(
                root,
                [
                    NoteEvent(0.0, 0.50, 60, 80),
                    NoteEvent(0.6, 1.10, 64, 100),
                    NoteEvent(1.2, 1.70, 90, 110),
                ],
            )
            rows = [
                self._row(60, 54, 62, 0.10, tuning_status="no-stable-pitch"),
                self._row(64, 63, 70, 0.20, tuning_status="rejected-unstable"),
            ]

            result = analyze_sample_instrument_usability(clip, rows, kind="keys")

            self.assertEqual(result["status"], "texture-only")
            self.assertEqual(result["functional_status"], "fail")
            self.assertEqual(result["coverage"]["mapped_note_count"], 2)
            self.assertEqual(result["coverage"]["unmapped_pitch_counts"], {"90": 1})
            self.assertEqual(
                {item["code"] for item in result["failures"]},
                {
                    "unmapped-performance-notes",
                    "insufficient-audible-attack-duration",
                    "insufficient-musical-duration",
                },
            )
            self.assertFalse(result["effects"]["source_midi_changed"])
            self.assertFalse(result["effects"]["soundfont_mapping_changed"])

    def test_complete_pitched_bank_remains_review_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clip = self._clip(
                root,
                [
                    NoteEvent(0.0, 0.30, 60, 80),
                    NoteEvent(0.4, 0.70, 64, 105),
                ],
            )
            rows = [
                self._row(60, 54, 62, 0.50),
                self._row(64, 63, 70, 0.50),
            ]

            result = analyze_sample_instrument_usability(clip, rows, kind="keys")

            self.assertEqual(result["status"], "review-required")
            self.assertEqual(result["functional_status"], "pass")
            self.assertEqual(result["coverage"]["note_coverage_ratio"], 1.0)
            self.assertEqual(result["duration_support"]["attack_support_ratio"], 1.0)
            self.assertEqual(
                result["duration_support"]["musical_support_ratio"], 1.0
            )
            self.assertEqual(result["failures"], [])
            self.assertFalse(result["automatic_primary_recommendation"])

    def test_drum_one_shot_does_not_require_pitched_sustain_or_tuning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clip = self._clip(
                root,
                [NoteEvent(0.0, 0.10, 36, 110)],
                channel=9,
            )
            rows = [
                self._row(36, 36, 36, 0.12, tuning_status="disabled"),
            ]

            result = analyze_sample_instrument_usability(clip, rows, kind="kick")

            self.assertEqual(result["functional_status"], "pass")
            self.assertTrue(result["one_shot_role"])
            self.assertIsNone(result["policy"]["musical_floor_seconds"])
            self.assertEqual(result["pitch_evidence"]["stable_zone_count"], 0)

    def test_audition_plays_each_performance_pitch_then_velocity_probes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clip = self._clip(
                root,
                [
                    NoteEvent(0.0, 0.20, 60, 80),
                    NoteEvent(0.3, 0.50, 60, 100),
                    NoteEvent(0.6, 0.80, 67, 110),
                ],
            )
            output = root / "usability.mid"

            report = write_instrument_usability_audition(output, clip, bpm=120.0)
            audition = list(read_midi_clips(output))[0]

            self.assertEqual(report["pitch_order"], [60, 67])
            self.assertEqual(report["note_count"], 6)
            self.assertEqual(len(audition.notes), 6)
            self.assertEqual(
                [note.velocity for note in audition.notes[-4:]], [32, 64, 96, 127]
            )


if __name__ == "__main__":
    unittest.main()
