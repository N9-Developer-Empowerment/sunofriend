from __future__ import annotations

import unittest

from sunofriend.clip import (
    ClipNote,
    Instrument,
    MidiClip,
    TempoMap,
    TimeSignature,
)
from sunofriend.drum_mapping import (
    DRUM_MAPPING_SCHEMA,
    drum_note_candidates,
    propose_drum_family_mapping,
)


def _note(start: float, pitch: int) -> ClipNote:
    return ClipNote(
        start_beat=start * 2.0,
        duration_beats=0.2,
        pitch=pitch,
        velocity=96,
        source_start_seconds=start,
        source_end_seconds=start + 0.1,
    )


class DrumMappingTests(unittest.TestCase):
    def test_distinct_family_notes_are_proposed_without_changing_outlier(self):
        clip = MidiClip(
            title="Kick",
            tempo_map=TempoMap.constant(120.0),
            time_signature=TimeSignature(4, 4),
            instrument=Instrument("kick", channel=0),
            notes=(_note(0.1, 36), _note(0.6, 36), _note(1.1, 40)),
        )
        first = [0.0] * 20
        second = [2.0] * 17 + [0.8, 0.7, 0.6]
        outlier = [-4.0] * 20
        clusters = {
            "identity_candidate_clusters": [
                {"cluster_id": "I1", "event_count": 1, "medoid_event_index": 0},
                {"cluster_id": "I2", "event_count": 1, "medoid_event_index": 1},
            ],
            "events": [
                {
                    "event_index": 0,
                    "note_index": 0,
                    "pitch": 36,
                    "identity_candidate_cluster": "I1",
                    "identity_outlier": False,
                },
                {
                    "event_index": 1,
                    "note_index": 1,
                    "pitch": 36,
                    "identity_candidate_cluster": "I2",
                    "identity_outlier": False,
                },
                {
                    "event_index": 2,
                    "note_index": 2,
                    "pitch": 40,
                    "identity_candidate_cluster": None,
                    "identity_outlier": True,
                },
            ],
        }

        proposed, evidence = propose_drum_family_mapping(
            kind="kick",
            clip=clip,
            source_event_clusters=clusters,
            source_vectors=[first, second, outlier],
            candidate_vectors={35: first, 36: second},
        )

        self.assertEqual(evidence["schema"], DRUM_MAPPING_SCHEMA)
        self.assertTrue(evidence["review_required"])
        self.assertEqual([note.pitch for note in clip.notes], [36, 36, 40])
        self.assertEqual([note.pitch for note in proposed.notes], [35, 36, 40])
        self.assertEqual(proposed.instrument.channel, 9)
        self.assertEqual(evidence["summary"]["distinct_assigned_note_count"], 2)
        self.assertEqual(evidence["effects"]["retained_outlier_note_indices"], [2])
        self.assertEqual(
            [
                (note.start_beat, note.duration_beats, note.velocity)
                for note in proposed.notes
            ],
            [
                (note.start_beat, note.duration_beats, note.velocity)
                for note in clip.notes
            ],
        )

    def test_candidate_sets_are_role_specific_and_stable(self):
        self.assertEqual(drum_note_candidates("kick"), (35, 36))
        self.assertEqual(drum_note_candidates("hat"), (42, 44, 46))
        self.assertEqual(drum_note_candidates("toms"), (41, 43, 45, 47, 48, 50))
        self.assertEqual(drum_note_candidates("other_kit"), tuple(range(35, 82)))

    def test_existing_distinct_kit_notes_are_not_collapsed_by_one_timbre_cluster(self):
        clip = MidiClip(
            title="Snare",
            tempo_map=TempoMap.constant(120.0),
            time_signature=TimeSignature(4, 4),
            instrument=Instrument("snare", channel=9),
            notes=(_note(0.1, 38), _note(0.6, 40)),
        )
        first = [0.0] * 20
        second = [2.0] * 20
        clusters = {
            "identity_candidate_clusters": [
                {"cluster_id": "I1", "event_count": 2, "medoid_event_index": 0}
            ],
            "events": [
                {
                    "event_index": 0,
                    "note_index": 0,
                    "pitch": 38,
                    "identity_candidate_cluster": "I1",
                    "identity_outlier": False,
                },
                {
                    "event_index": 1,
                    "note_index": 1,
                    "pitch": 40,
                    "identity_candidate_cluster": "I1",
                    "identity_outlier": False,
                },
            ],
        }

        proposed, evidence = propose_drum_family_mapping(
            kind="snare",
            clip=clip,
            source_event_clusters=clusters,
            source_vectors=[first, second],
            candidate_vectors={
                37: [8.0] * 20,
                38: first,
                39: [-8.0] * 20,
                40: second,
            },
        )

        self.assertEqual([note.pitch for note in proposed.notes], [38, 40])
        self.assertEqual(evidence["summary"]["source_identity_cluster_count"], 1)
        self.assertEqual(evidence["summary"]["candidate_timbre_family_count"], 2)
        self.assertEqual(evidence["summary"]["proposed_note_change_count"], 0)
        self.assertEqual(
            [row["mapping_unit_id"] for row in evidence["family_mappings"]],
            ["I1-P038", "I1-P040"],
        )


if __name__ == "__main__":
    unittest.main()
