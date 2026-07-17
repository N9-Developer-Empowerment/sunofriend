from __future__ import annotations

import unittest

from sunofriend.instrument_dynamics import (
    SOURCE_EVENT_DYNAMICS_SCHEMA,
    analyze_source_event_dynamics,
    source_event_dynamics_svg,
)


def _cluster_report() -> dict:
    events = []
    for index in range(16):
        quiet = index < 8
        events.append(
            {
                "event_index": index,
                "note_index": index,
                "start_seconds": index * 0.5,
                "end_seconds": index * 0.5 + 0.12,
                "pitch": 36,
                "velocity": 44 + index % 3 if quiet else 98 + index % 3,
                "rms": 0.045 + (index % 3) * 0.002
                if quiet
                else 0.19 + (index % 3) * 0.004,
                "isolated": True,
                "overlap_count": 0,
                "identity_candidate_cluster": "I1",
                "articulation_cluster": "A1",
                "identity_outlier": False,
                "timbre_vector": [
                    (0.1 if quiet else 0.15) + (index % 4) * 0.005 for _ in range(20)
                ],
            }
        )
    events.append(
        {
            "event_index": 16,
            "note_index": 16,
            "start_seconds": 8.0,
            "end_seconds": 8.1,
            "pitch": 36,
            "velocity": 127,
            "rms": 0.5,
            "isolated": True,
            "overlap_count": 0,
            "identity_candidate_cluster": None,
            "articulation_cluster": "A1",
            "identity_outlier": True,
            "timbre_vector": [9.0] * 20,
        }
    )
    return {
        "source": {"path": "/fixture/source.wav", "sha256": "source"},
        "midi": {"path": "/fixture/source.mid", "sha256": "midi"},
        "events": events,
    }


class InstrumentDynamicsTests(unittest.TestCase):
    def test_discovers_two_source_loudness_layers_and_round_robin_candidates(self):
        report = analyze_source_event_dynamics(_cluster_report())

        self.assertEqual(report["schema"], SOURCE_EVENT_DYNAMICS_SCHEMA)
        self.assertEqual(report["summary"]["source_event_count"], 17)
        self.assertEqual(report["summary"]["comparable_unit_count"], 1)
        self.assertEqual(report["summary"]["velocity_layer_candidate_unit_count"], 1)
        self.assertEqual(report["summary"]["velocity_layer_count"], 2)
        self.assertEqual(report["summary"]["round_robin_candidate_set_count"], 2)
        self.assertEqual(report["summary"]["round_robin_candidate_event_count"], 6)
        self.assertEqual(report["summary"]["retained_outlier_count"], 1)
        self.assertGreaterEqual(
            report["units"][0]["velocity_split"]["median_rms_gap_db"], 3.0
        )
        self.assertEqual(
            [layer["event_count"] for layer in report["units"][0]["layers"]],
            [8, 8],
        )
        self.assertEqual(report["effects"]["midi_velocities_changed"], 0)
        self.assertEqual(report["effects"]["soundfont_zones_changed"], 0)

    def test_report_and_svg_are_deterministic(self):
        first = analyze_source_event_dynamics(_cluster_report())
        second = analyze_source_event_dynamics(_cluster_report())

        self.assertEqual(first, second)
        self.assertEqual(
            source_event_dynamics_svg(first), source_event_dynamics_svg(second)
        )
        self.assertIn("round-robin candidate", source_event_dynamics_svg(first))


if __name__ == "__main__":
    unittest.main()
