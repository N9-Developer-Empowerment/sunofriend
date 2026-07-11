from __future__ import annotations

import unittest

from sunofriend.compare import (
    PitchedDiff,
    PitchedEdit,
    PitchedNoteEvidence,
    pitched_edit_detail,
    propose_pitched_edits,
)
from sunofriend.loop import _apply_edits_pitched
from sunofriend.models import NoteEvent


def _evidence(
    note: NoteEvent,
    *,
    confidence: float = 0.9,
    support: float = 0.3,
    onset: float | None = 0.8,
) -> PitchedNoteEvidence:
    sources = ("transcription", "spectrum", "onset") if onset is not None else (
        "transcription",
        "spectrum",
    )
    return PitchedNoteEvidence(
        note=note,
        confidence=confidence,
        spectral_support=support,
        onset_strength=onset,
        sources=sources,
    )


class PitchedRefinementTests(unittest.TestCase):
    def test_adds_only_missed_notes_with_three_way_stem_evidence(self):
        existing = NoteEvent(0.0, 0.5, 60, 80)
        evidence = [
            _evidence(existing),
            _evidence(NoteEvent(1.0, 1.5, 64, 86)),
            # Spectrum + transcription without an onset is not enough to add.
            _evidence(NoteEvent(2.0, 2.5, 67, 84), onset=None),
            # Nor is a weakly corroborated onset hypothesis.
            _evidence(
                NoteEvent(3.0, 3.5, 69, 82), confidence=0.6, support=0.1, onset=0.3
            ),
        ]

        edits = propose_pitched_edits([existing], evidence)

        additions = [edit for edit in edits if edit.action == "add"]
        self.assertEqual([edit.after.pitch for edit in additions], [64])
        self.assertIn("transcription+spectrum+onset", additions[0].rationale)

    def test_repairs_octave_timing_duration_and_velocity_together(self):
        candidate = NoteEvent(0.06, 1.0, 72, 50)
        reference = _evidence(NoteEvent(0.0, 1.2, 60, 90), confidence=0.96, support=0.42)

        edits = propose_pitched_edits(
            [candidate], [reference], candidate_support=[0.05]
        )

        self.assertEqual(len(edits), 1)
        repair = edits[0]
        self.assertEqual(repair.action, "repair")
        self.assertEqual(repair.note_index, 0)
        self.assertEqual(repair.fields, ("octave", "timing", "duration", "velocity"))
        self.assertEqual(repair.after, NoteEvent(0.0, 1.2, 60, 90))

    def test_repairs_small_pitch_error_when_reference_is_stronger(self):
        candidate = NoteEvent(2.0, 2.5, 65, 80)
        reference = _evidence(NoteEvent(2.0, 2.5, 64, 80), support=0.4)

        edits = propose_pitched_edits(
            [candidate], [reference], candidate_support=[0.08]
        )

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].fields, ("pitch",))
        self.assertEqual(edits[0].after.pitch, 64)

    def test_does_not_replace_a_well_supported_candidate_pitch(self):
        candidate = NoteEvent(2.0, 2.5, 65, 80)
        reference = _evidence(NoteEvent(2.0, 2.5, 64, 80), support=0.2)

        edits = propose_pitched_edits(
            [candidate], [reference], candidate_support=[0.3]
        )

        self.assertFalse(any(edit.action == "repair" for edit in edits))

    def test_does_not_repeat_duration_extension_past_same_pitch_retrigger(self):
        first = NoteEvent(0.0, 0.5, 60, 80)
        retrigger = NoteEvent(0.5, 1.0, 60, 80)
        reference = _evidence(
            NoteEvent(0.0, 0.8, 60, 80), confidence=0.95, support=0.4
        )

        edits = propose_pitched_edits([first, retrigger], [reference])

        self.assertFalse(any("duration" in edit.fields for edit in edits))

    def test_low_confidence_evidence_does_not_move_timing(self):
        candidate = NoteEvent(1.0, 1.5, 64, 80)
        reference = _evidence(
            NoteEvent(0.94, 1.44, 64, 80), confidence=0.7, support=0.3, onset=0.8
        )

        edits = propose_pitched_edits([candidate], [reference])

        self.assertFalse(any("timing" in edit.fields for edit in edits))

    def test_structure_locked_parts_only_adjust_expression(self):
        candidate = NoteEvent(1.0, 1.5, 60, 70)
        evidence = [
            _evidence(NoteEvent(0.94, 1.8, 60, 92), confidence=0.95, support=0.4),
            _evidence(NoteEvent(2.0, 2.5, 67, 88), confidence=0.95, support=0.4),
            _evidence(NoteEvent(1.0, 1.5, 72, 94), confidence=0.98, support=0.5),
        ]

        edits = propose_pitched_edits(
            [candidate], evidence, preserve_structure=True, allow_additions=False
        )

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].fields, ("velocity",))
        self.assertEqual(edits[0].after.start, candidate.start)
        self.assertEqual(edits[0].after.end, candidate.end)
        self.assertEqual(edits[0].after.pitch, candidate.pitch)
        self.assertFalse(any(edit.action == "add" for edit in edits))

    def test_apply_repairs_before_spurious_removal_and_deduplicates_additions(self):
        wrong_octave = NoteEvent(0.0, 0.5, 72, 70)
        unsupported = NoteEvent(1.0, 1.4, 66, 60)
        repaired = NoteEvent(0.0, 0.6, 60, 82)
        addition = NoteEvent(2.0, 2.4, 64, 88)
        diff = PitchedDiff(
            spurious_notes=[0, 1],
            edits=[
                PitchedEdit(
                    "repair", 0, wrong_octave, repaired, ("octave",), 0.94, "supported"
                ),
                PitchedEdit("add", None, None, addition, ("note",), 0.91, "supported"),
                PitchedEdit("add", None, None, addition, ("note",), 0.91, "supported"),
            ],
        )

        got = _apply_edits_pitched([wrong_octave, unsupported], diff)

        self.assertEqual(got, [repaired, addition])

    def test_result_is_stable_once_repairs_are_applied(self):
        candidate = NoteEvent(0.04, 0.9, 72, 55)
        references = [
            _evidence(NoteEvent(0.0, 1.0, 60, 85), confidence=0.95, support=0.4),
            _evidence(NoteEvent(1.5, 2.0, 64, 78), confidence=0.9, support=0.3),
        ]
        first_diff = PitchedDiff(
            edits=propose_pitched_edits([candidate], references, candidate_support=[0.04])
        )
        first = _apply_edits_pitched([candidate], first_diff)

        second_edits = propose_pitched_edits(first, references, candidate_support=[0.4, 0.3])

        self.assertEqual(second_edits, [])

    def test_iteration_detail_preserves_confidence_and_rationale(self):
        note = NoteEvent(0.0, 0.5, 60, 90)
        diff = PitchedDiff(
            edits=[
                PitchedEdit(
                    "add", None, None, note, ("note",), 0.8764, "three independent signals"
                )
            ]
        )

        detail = pitched_edit_detail(diff)

        self.assertEqual(detail[0]["confidence"], 0.876)
        self.assertEqual(detail[0]["rationale"], "three independent signals")
        self.assertEqual(detail[0]["target"]["pitch"], 60)


if __name__ == "__main__":
    unittest.main()
