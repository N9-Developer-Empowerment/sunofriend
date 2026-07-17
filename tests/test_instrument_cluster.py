from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from sunofriend.instrument_cluster import (
    SOURCE_EVENT_CLUSTER_SCHEMA,
    cluster_source_events,
    source_event_clusters_svg,
)


FEATURE_NAMES = tuple(f"feature_{index}" for index in range(20))


def _fixture_events():
    segments = []
    vectors = []
    for index in range(13):
        family = 0 if index < 6 else 1 if index < 12 else 2
        short = index % 2 == 0
        duration = 0.25 if short else 1.0
        segments.append(
            SimpleNamespace(
                note_index=index,
                start_seconds=index * 1.2,
                end_seconds=index * 1.2 + duration,
                pitch=48 + index % 5,
                velocity=70 + index,
                rms=0.10 + (index % 3) * 0.01,
                isolated=True,
                overlap_count=0,
                samples=np.zeros(100, dtype=np.float32),
            )
        )
        if family == 0:
            identity = np.linspace(0.0, 0.3, 17)
        elif family == 1:
            identity = np.linspace(2.0, 2.3, 17)
        else:
            identity = np.asarray(
                [10.0 if feature % 2 == 0 else -10.0 for feature in range(17)]
            )
        identity = identity + (index % 3) * 0.01
        articulation = [0.10, 0.08, 0.15] if short else [0.85, 0.80, 0.30]
        vectors.append([*identity.tolist(), *articulation])
    return segments, vectors


class InstrumentClusterTests(unittest.TestCase):
    def test_separates_timbre_and_articulation_and_retains_outlier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            midi = root / "part.mid"
            source.write_bytes(b"source")
            midi.write_bytes(b"midi")
            segments, vectors = _fixture_events()

            report = cluster_source_events(
                segments,
                vectors,
                sample_rate=16_000,
                source_path=source,
                midi_path=midi,
                feature_names=FEATURE_NAMES,
                selected_note_indices=[0, 8],
            )

            self.assertEqual(report["schema"], SOURCE_EVENT_CLUSTER_SCHEMA)
            self.assertEqual(report["summary"]["identity_candidate_cluster_count"], 2)
            self.assertEqual(report["summary"]["articulation_cluster_count"], 2)
            self.assertEqual(report["summary"]["identity_outlier_count"], 1)
            self.assertEqual(report["summary"]["selected_sample_event_count"], 2)
            self.assertEqual(
                report["identity_candidate_clusters"][0]["event_indices"],
                [0, 1, 2, 3, 4, 5],
            )
            self.assertEqual(
                report["identity_candidate_clusters"][1]["event_indices"],
                [6, 7, 8, 9, 10, 11],
            )
            self.assertTrue(report["events"][12]["identity_outlier"])
            self.assertIsNone(report["events"][12]["identity_candidate_cluster"])
            self.assertEqual(report["effects"]["midi_notes_changed"], 0)
            self.assertEqual(report["effects"]["sample_events_removed"], 0)
            self.assertFalse(report["effects"]["instrument_ranking_changed"])

    def test_report_and_svg_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            midi = root / "part.mid"
            source.write_bytes(b"source")
            midi.write_bytes(b"midi")
            segments, vectors = _fixture_events()
            arguments = dict(
                sample_rate=16_000,
                source_path=source,
                midi_path=midi,
                feature_names=FEATURE_NAMES,
            )

            first = cluster_source_events(segments, vectors, **arguments)
            second = cluster_source_events(segments, vectors, **arguments)

            self.assertEqual(first, second)
            self.assertEqual(
                source_event_clusters_svg(first), source_event_clusters_svg(second)
            )
            self.assertIn("retained outlier", source_event_clusters_svg(first))


if __name__ == "__main__":
    unittest.main()
