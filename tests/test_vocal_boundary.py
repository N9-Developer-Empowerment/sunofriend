from __future__ import annotations

import unittest

from sunofriend.vocal_boundary import (
    BoundaryProposal,
    VOCAL_BOUNDARY_REPAIR_SCHEMA,
    repair_vocal_boundaries,
)


def _alignment() -> list[dict]:
    records = []
    for index in range(100):
        if index < 40:
            pyin_pitch, rmvpe_pitch = 60.05, 60.15
        elif index < 80:
            pyin_pitch, rmvpe_pitch = 63.95, 64.10
        else:
            pyin_pitch, rmvpe_pitch = 67.0, 70.0
        records.append(
            {
                "time_seconds": index * 0.01,
                "observations": {
                    "pyin": {
                        "status": "voiced",
                        "fractional_midi": pyin_pitch,
                        "confidence": 0.92,
                    },
                    "rmvpe": {
                        "status": "voiced",
                        "fractional_midi": rmvpe_pitch,
                        "confidence": 0.90,
                    },
                },
            }
        )
    return records


class VocalBoundaryRepairTests(unittest.TestCase):
    def test_boundaries_are_accepted_only_over_agreed_pitch(self):
        proposals = [
            BoundaryProposal("basic-pitch", "bp-good", 0.0, 0.4, 60.3, 0.9, 96),
            BoundaryProposal("game", "game-good", 0.4, 0.8, 64.2, None, 88),
            BoundaryProposal("basic-pitch", "bp-wrong", 0.4, 0.8, 72.0, 0.9),
            BoundaryProposal("game", "game-disputed", 0.8, 1.0, 67.0),
        ]

        variants, document = repair_vocal_boundaries(
            _alignment(), proposals, bpm=120.0
        )

        self.assertEqual(document["schema"], VOCAL_BOUNDARY_REPAIR_SCHEMA)
        self.assertEqual(
            [note.pitch for note in variants["combined"]],
            [60, 64],
        )
        self.assertEqual(len(variants["basic-pitch"]), 1)
        self.assertEqual(len(variants["game"]), 1)
        records = {
            record["source_event_id"]: record for record in document["proposals"]
        }
        self.assertEqual(records["bp-good"]["status"], "accepted")
        self.assertEqual(records["game-good"]["status"], "accepted")
        self.assertIn(
            "boundary-pitch-disagrees",
            records["bp-wrong"]["reasons"],
        )
        self.assertIn(
            "insufficient-agreement-frames",
            records["game-disputed"]["reasons"],
        )
        self.assertFalse(document["policy"]["raw_candidates_mutated"])
        self.assertEqual(document["summary"]["variant_notes"]["combined"], 2)
        self.assertEqual(document["summary"]["phrase_counts"]["combined"], 1)

    def test_overlapping_providers_create_one_monophonic_combined_note(self):
        proposals = [
            BoundaryProposal("basic-pitch", "bp", 0.0, 0.4, 60.0, 0.8),
            BoundaryProposal("game", "game", 0.0, 0.4, 60.0, 0.9),
        ]

        variants, document = repair_vocal_boundaries(
            _alignment(), proposals, bpm=120.0
        )

        self.assertEqual(len(variants["basic-pitch"]), 1)
        self.assertEqual(len(variants["game"]), 1)
        self.assertEqual(len(variants["combined"]), 1)
        selected = [
            record
            for record in document["proposals"]
            if "combined" in record["selected_variants"]
        ]
        self.assertEqual(len(selected), 1)

    def test_output_pitch_is_equal_midpoint_not_confidence_weighted(self):
        alignment = []
        for index in range(40):
            alignment.append(
                {
                    "time_seconds": index * 0.01,
                    "observations": {
                        "pyin": {
                            "status": "voiced",
                            "fractional_midi": 60.0,
                            "confidence": 0.01,
                        },
                        "rmvpe": {
                            "status": "voiced",
                            "fractional_midi": 60.6,
                            "confidence": 0.99,
                        },
                    },
                }
            )

        variants, _ = repair_vocal_boundaries(
            alignment,
            [BoundaryProposal("game", "equal-vote", 0.0, 0.4, 60.3)],
            bpm=120.0,
        )

        self.assertEqual(variants["combined"][0].pitch, 60)


if __name__ == "__main__":
    unittest.main()
