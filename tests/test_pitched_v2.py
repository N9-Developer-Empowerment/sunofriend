from __future__ import annotations

import unittest
from unittest.mock import patch

from sunofriend.beatgrid import Grid
from sunofriend.imagine import (
    BASS_HIGH,
    BASS_LOW,
    _fold_pitch_to_register,
    _theory_clean,
    imagine_bass_variants,
)
from sunofriend.models import ChordSegment, NoteEvent
from sunofriend.transcribe_pitched import (
    build_keys_register_hypotheses,
    _BassSustainEvidence,
    repair_bass_octaves,
    repair_bass_sustain,
    select_bass_contour,
    separate_keys_roles,
    transcribe_pitched_stem,
)


class BassRegisterTests(unittest.TestCase):
    def test_octave_folding_preserves_pitch_class_down_to_b0(self):
        folded = _fold_pitch_to_register(15, BASS_LOW, BASS_HIGH)

        self.assertEqual((BASS_LOW, BASS_HIGH), (23, 52))
        self.assertEqual(folded, 27)
        self.assertEqual(folded % 12, 15 % 12)

    def test_d_sharp_one_is_not_changed_to_e_one(self):
        segment = ChordSegment(0.0, 2.0, "B", (11, 3, 6))

        got = _theory_clean(
            [NoteEvent(0.0, 0.5, 27, 90)],
            [segment],
            "B major",
            Grid(120.0),
            low=BASS_LOW,
            high=BASS_HIGH,
        )

        self.assertEqual([note.pitch for note in got], [27])

    def test_variants_expose_evidence_contour_and_chord_root_choices(self):
        evidence = [
            NoteEvent(0.02, 0.48, 27, 84),
            NoteEvent(0.51, 0.98, 30, 88),
        ]
        segments = [ChordSegment(0.0, 2.0, "B", (11, 3, 6))]

        with patch(
            "sunofriend.transcribe_pitched.transcribe_pitched_stem",
            return_value=evidence,
        ), patch(
            "sunofriend.imagine._verified",
            side_effect=lambda _path, notes, threshold: notes,
        ), patch(
            "sunofriend.transcribe_pitched.repair_bass_sustain",
            side_effect=lambda _path, notes, **_kwargs: list(notes),
        ), patch(
            "sunofriend.transcribe_pitched.repair_bass_octaves",
            side_effect=lambda _path, notes, **_kwargs: list(notes),
        ):
            variants = imagine_bass_variants(
                "synthetic.wav", Grid(120.0), segments, "B major"
            )

        self.assertEqual(
            set(variants),
            {
                "raw_verified",
                "contour_clean",
                "octave_resolved",
                "continuous_sustain",
                "root_safe",
            },
        )
        self.assertEqual(variants["raw_verified"], evidence)
        self.assertEqual(variants["octave_resolved"], evidence)
        self.assertEqual(variants["continuous_sustain"], evidence)
        self.assertEqual(variants["contour_clean"][0].pitch, 27)
        self.assertTrue(
            all(note.pitch % 12 == segments[0].root_pc for note in variants["root_safe"])
        )


class BassContourTests(unittest.TestCase):
    def test_octave_resolution_changes_only_a_dominant_pyin_harmonic(self):
        notes = [
            NoteEvent(0.0, 0.5, 47, 84),
            NoteEvent(0.6, 1.0, 39, 88),
        ]
        evidence = _BassSustainEvidence(
            frame_seconds=0.1,
            rms_active=(True,) * 12,
            voiced=(True,) * 12,
            pitches=(35,) * 6 + (39,) * 6,
        )

        with patch(
            "sunofriend.transcribe_pitched._bass_sustain_evidence",
            return_value=evidence,
        ):
            got = repair_bass_octaves("bass.wav", notes)

        self.assertEqual(got[0], NoteEvent(0.0, 0.5, 35, 84))
        self.assertEqual(got[1], notes[1])
        self.assertEqual(
            [(note.start, note.end, note.velocity) for note in got],
            [(note.start, note.end, note.velocity) for note in notes],
        )

    def test_octave_resolution_preserves_weak_or_different_pitch_evidence(self):
        note = NoteEvent(0.0, 0.5, 47, 84)
        evidence = _BassSustainEvidence(
            frame_seconds=0.1,
            rms_active=(True,) * 8,
            voiced=(True,) * 8,
            pitches=(35, 35, 35, 36, 36, 36, 36, 36),
        )

        with patch(
            "sunofriend.transcribe_pitched._bass_sustain_evidence",
            return_value=evidence,
        ):
            got = repair_bass_octaves("bass.wav", [note])

        self.assertEqual(got, [note])

    def test_continuous_sustain_extends_only_source_supported_short_gap(self):
        notes = [
            NoteEvent(0.0, 0.4, 35, 84),
            NoteEvent(0.8, 1.2, 38, 88),
        ]
        evidence = _BassSustainEvidence(
            frame_seconds=0.1,
            rms_active=(True,) * 16,
            voiced=(True,) * 16,
            pitches=(35,) * 9 + (38,) * 7,
        )

        with patch(
            "sunofriend.transcribe_pitched._bass_sustain_evidence",
            return_value=evidence,
        ):
            got = repair_bass_sustain("bass.wav", notes, bpm=120.0)

        self.assertEqual(got[0], NoteEvent(0.0, 0.8, 35, 84))
        self.assertEqual(got[1], notes[1])
        self.assertEqual(
            [(note.start, note.pitch, note.velocity) for note in got],
            [(note.start, note.pitch, note.velocity) for note in notes],
        )

    def test_continuous_sustain_preserves_unvoiced_and_long_rests(self):
        unvoiced = [
            NoteEvent(0.0, 0.4, 35, 84),
            NoteEvent(0.8, 1.2, 38, 88),
        ]
        long_rest = [
            NoteEvent(0.0, 0.4, 35, 84),
            NoteEvent(2.0, 2.4, 38, 88),
        ]
        evidence = _BassSustainEvidence(
            frame_seconds=0.1,
            rms_active=(True,) * 30,
            voiced=(False,) * 30,
            pitches=(None,) * 30,
        )

        with patch(
            "sunofriend.transcribe_pitched._bass_sustain_evidence",
            return_value=evidence,
        ):
            self.assertEqual(
                repair_bass_sustain("bass.wav", unvoiced, bpm=120.0),
                unvoiced,
            )
            self.assertEqual(
                repair_bass_sustain("bass.wav", long_rest, bpm=120.0),
                long_rest,
            )

    def test_continuous_sustain_does_not_cross_a_real_pitch_change(self):
        notes = [
            NoteEvent(0.0, 0.4, 35, 84),
            NoteEvent(0.8, 1.2, 38, 88),
        ]
        evidence = _BassSustainEvidence(
            frame_seconds=0.1,
            rms_active=(True,) * 16,
            voiced=(True,) * 16,
            pitches=(35,) * 4 + (38,) * 12,
        )

        with patch(
            "sunofriend.transcribe_pitched._bass_sustain_evidence",
            return_value=evidence,
        ):
            got = repair_bass_sustain("bass.wav", notes, bpm=120.0)

        self.assertEqual(got, notes)

    def test_pyin_agreement_beats_a_louder_subharmonic(self):
        basic = [
            NoteEvent(0.0, 0.45, 24, 110),
            NoteEvent(0.0, 0.45, 36, 88),
        ]
        pyin = [NoteEvent(0.01, 0.44, 36, 76)]

        got = select_bass_contour(basic, pyin)

        self.assertEqual([note.pitch for note in got], [36])

    def test_global_path_prefers_continuous_walking_contour(self):
        contour = [36, 38, 40, 41]
        basic: list[NoteEvent] = []
        pyin: list[NoteEvent] = []
        for index, pitch in enumerate(contour):
            start = index * 0.5
            basic.extend(
                [
                    NoteEvent(start, start + 0.45, pitch - 12, 102),
                    NoteEvent(start, start + 0.45, pitch, 88),
                ]
            )
            pyin.append(NoteEvent(start + 0.01, start + 0.44, pitch, 74))

        got = select_bass_contour(basic, pyin)

        self.assertEqual([note.pitch for note in got], contour)
        self.assertLessEqual(max(abs(a.pitch - b.pitch) for a, b in zip(got, got[1:])), 2)

    def test_single_engine_octave_error_is_folded_into_the_contour(self):
        # The second event has the right D pitch class but only a D3 hypothesis.
        # A line-level decoder should prefer nearby D2 over an unsupported leap.
        basic = [
            NoteEvent(0.0, 0.45, 36, 90),
            NoteEvent(0.5, 0.95, 50, 90),
        ]

        got = select_bass_contour(basic, [])

        self.assertEqual([note.pitch for note in got], [36, 38])

    def test_two_engine_agreement_can_confirm_a_real_octave_leap(self):
        basic = [
            NoteEvent(0.0, 0.45, 36, 86),
            NoteEvent(0.5, 0.95, 48, 88),
        ]
        pyin = [
            NoteEvent(0.01, 0.44, 36, 78),
            NoteEvent(0.51, 0.94, 48, 80),
        ]

        got = select_bass_contour(basic, pyin)

        self.assertEqual([note.pitch for note in got], [36, 48])

    def test_pyin_is_a_graceful_fallback_when_ml_is_unavailable(self):
        pyin = [NoteEvent(0.0, 0.5, 35, 80)]

        with patch(
            "sunofriend.transcribe_pitched._basic_pitch_notes",
            side_effect=ImportError("basic-pitch unavailable"),
        ), patch("sunofriend.transcribe_pitched._pyin_notes", return_value=pyin):
            got = transcribe_pitched_stem("synthetic.wav", kind="bass")

        self.assertEqual(got, pyin)


class KeysRoleTests(unittest.TestCase):
    def test_register_bank_keeps_low_evidence_and_labels_octave_interpretations(self):
        low_a = NoteEvent(0.0, 0.8, 45, 70)
        high_a = NoteEvent(0.01, 0.4, 69, 100)
        low_b = NoteEvent(0.5, 1.0, 47, 75)
        high_b = NoteEvent(0.51, 0.9, 74, 95)

        variants = build_keys_register_hypotheses(
            [low_a, high_a, low_b, high_b],
            [high_a, high_b],
        )

        self.assertEqual(variants["lowest_line"], [low_a, low_b])
        self.assertEqual(
            [note.pitch for note in variants["melody_down_12"]],
            [57, 62],
        )
        self.assertEqual(
            [note.pitch for note in variants["melody_down_24"]],
            [45, 50],
        )
        self.assertEqual(
            variants["low_with_upper_additions"],
            [low_a, high_a, low_b, high_b],
        )

    def test_chart_constrains_accompaniment_but_not_melody(self):
        segment = ChordSegment(0.0, 2.0, "C", (0, 4, 7))
        chord = [
            NoteEvent(0.0, 1.5, 60, 60),
            NoteEvent(0.0, 1.5, 64, 58),
            NoteEvent(0.0, 1.5, 67, 62),
        ]
        # D5 is deliberately outside the C triad: a chart must not erase or
        # snap an independently salient melody/passing tone.
        first_melody = NoteEvent(0.01, 0.40, 74, 110)
        uncertain_chromatic = NoteEvent(0.02, 0.80, 61, 30)
        second_melody = NoteEvent(0.50, 0.90, 76, 90)

        roles = separate_keys_roles(
            chord + [first_melody, uncertain_chromatic, second_melody],
            [segment],
        )

        self.assertEqual(roles.melody, [first_melody, second_melody])
        self.assertEqual(roles.accompaniment, chord)
        self.assertEqual(roles.uncertain, [uncertain_chromatic])
        self.assertEqual(roles.melody[0].pitch, 74)

    def test_equal_salience_chord_is_not_forced_into_a_melody(self):
        chord = [
            NoteEvent(0.0, 1.0, 60, 60),
            NoteEvent(0.0, 1.0, 64, 60),
            NoteEvent(0.0, 1.0, 67, 60),
        ]

        roles = separate_keys_roles(chord)

        self.assertEqual(roles.melody, [])
        self.assertEqual(roles.accompaniment, chord)
        self.assertEqual(roles.uncertain, [])


if __name__ == "__main__":
    unittest.main()
