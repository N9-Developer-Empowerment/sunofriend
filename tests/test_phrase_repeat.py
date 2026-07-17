from __future__ import annotations

import unittest

from sunofriend.models import NoteEvent
from sunofriend.phrase_repeat import (
    REPEAT_POLICY_NAME,
    detect_repeated_review_units,
    repeat_matches_for_unit,
)


def _units() -> list[dict]:
    return [
        {"phrase_index": 0, "start_seconds": 0.0, "end_seconds": 2.0},
        {"phrase_index": 1, "start_seconds": 4.0, "end_seconds": 6.0},
    ]


def _phrase(offset: float, pitches: tuple[int, ...] = (60, 64, 62)) -> list[NoteEvent]:
    starts = (0.10, 0.55, 1.15)
    durations = (0.28, 0.38, 0.50)
    return [
        NoteEvent(offset + start, offset + start + duration, pitch, 84)
        for start, duration, pitch in zip(starts, durations, pitches)
    ]


class PhraseRepeatTests(unittest.TestCase):
    def test_accepts_exact_source_pitch_contour_and_rhythm_repeat(self):
        result = detect_repeated_review_units(
            _units(),
            [*_phrase(0.0), *_phrase(4.0)],
            bpm=120.0,
        )

        self.assertEqual(result["policy"]["name"], REPEAT_POLICY_NAME)
        self.assertFalse(result["policy"]["automatic_selection"])
        self.assertEqual(result["evaluated_pair_count"], 1)
        self.assertEqual(result["accepted_pair_count"], 1)
        pair = result["accepted_pairs"][0]
        self.assertEqual(pair["status"], "accepted")
        self.assertEqual(pair["similarity_score"], 1.0)
        self.assertEqual(pair["pitch_match_ratio"], 1.0)
        self.assertEqual(pair["timing_p90_beats"], 0.0)
        self.assertEqual(result["groups"][0]["phrase_indices"], [0, 1])
        left = repeat_matches_for_unit(result, 0)
        right = repeat_matches_for_unit(result, 1)
        self.assertEqual(left[0]["target_phrase_index"], 1)
        self.assertEqual(left[0]["lag_seconds"], 4.0)
        self.assertEqual(right[0]["target_phrase_index"], 0)
        self.assertEqual(right[0]["lag_seconds"], -4.0)

    def test_rejects_octave_transposition_despite_matching_contour(self):
        result = detect_repeated_review_units(
            _units(),
            [*_phrase(0.0), *_phrase(4.0, (72, 76, 74))],
            bpm=120.0,
        )

        self.assertEqual(result["accepted_pair_count"], 0)
        pair = result["evaluated_pairs"][0]
        self.assertIn("absolute-pitch-mismatch", pair["rejection_reasons"])
        self.assertEqual(pair["interval_match_ratio"], 1.0)
        self.assertTrue(pair["absolute_pitch_required"])

    def test_rejects_different_note_count_and_sparse_units(self):
        mismatch = detect_repeated_review_units(
            _units(),
            [
                *_phrase(0.0),
                *_phrase(4.0),
                NoteEvent(5.8, 5.95, 62, 80),
            ],
            bpm=120.0,
        )
        sparse = detect_repeated_review_units(
            _units(),
            [
                NoteEvent(0.1, 0.5, 60, 80),
                NoteEvent(0.7, 1.1, 62, 80),
                NoteEvent(4.1, 4.5, 60, 80),
                NoteEvent(4.7, 5.1, 62, 80),
            ],
            bpm=120.0,
        )

        self.assertIn(
            "note-count-mismatch",
            mismatch["evaluated_pairs"][0]["rejection_reasons"],
        )
        self.assertIn(
            "insufficient-notes",
            sparse["evaluated_pairs"][0]["rejection_reasons"],
        )
        self.assertEqual(mismatch["accepted_pairs"], [])
        self.assertEqual(sparse["accepted_pairs"], [])

    def test_output_is_deterministic_and_input_notes_are_unchanged(self):
        notes = [*_phrase(0.0), *_phrase(4.0)]
        original = list(notes)

        first = detect_repeated_review_units(_units(), notes, bpm=119.0)
        second = detect_repeated_review_units(_units(), notes, bpm=119.0)

        self.assertEqual(first, second)
        self.assertEqual(notes, original)
        self.assertFalse(first["raw_candidates_mutated"])


if __name__ == "__main__":
    unittest.main()
