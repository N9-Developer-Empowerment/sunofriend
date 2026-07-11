from __future__ import annotations

import json
import math
import tempfile
import unittest
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:  # optional audio dependency
    np = None

from sunofriend.evaluate import (
    FamilyAnnotation,
    evaluate_stem_midi,
    v2_pitch_family_map,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


@unittest.skipIf(np is None, "semantic audio evaluation requires NumPy")
class SemanticEvaluationTests(unittest.TestCase):
    def test_v2_family_map_is_consistent_for_all_entry_points(self) -> None:
        mapping = v2_pitch_family_map("other_kit")
        self.assertEqual(mapping[35], "kick_high")
        self.assertEqual(mapping[36], "kick_deep")
        self.assertEqual(mapping[39], "unknown")
        self.assertIsNone(v2_pitch_family_map("bass"))

    def test_independent_evaluator_does_not_cancel_antiphase_stereo_hit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / "antiphase.wav"
            sample_rate = 16_000
            left = np.zeros(sample_rate * 2, dtype=np.float64)
            start = int(0.5 * sample_rate)
            length = int(0.08 * sample_rate)
            time = np.arange(length, dtype=np.float64) / sample_rate
            left[start : start + length] = 0.8 * np.sin(
                2.0 * math.pi * 60.0 * time
            ) * np.exp(-time * 45.0)
            self._write_stereo_wav(stem, left, -left, sample_rate)

            report = evaluate_stem_midi(
                stem,
                [NoteEvent(0.5, 0.58, 36, 100)],
                kind="kick",
                pitch_family_map=v2_pitch_family_map("kick"),
            )

            self.assertGreaterEqual(report.onsets.possible.matched, 1)

    def test_independent_reference_catches_missed_extra_and_mistimed_hits(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / "drums.wav"
            self._write_drum_stem(stem)
            candidate = [
                NoteEvent(0.500, 0.580, 36, 110),
                NoteEvent(1.025, 1.105, 36, 100),  # matched, but detectably late
                # The strong hit near 1.5 seconds is deliberately missing.
                NoteEvent(2.000, 2.080, 36, 65),  # lower-confidence WAV hit
                NoteEvent(2.500, 2.580, 36, 90),  # definitely extra
            ]

            report = evaluate_stem_midi(
                stem,
                candidate,
                kind="kick",
                onset_tolerance=0.040,
                segment_seconds=1.0,
            )

            self.assertEqual(report.onsets.reference_strong_count, 3)
            self.assertEqual(report.onsets.reference_possible_count, 1)
            self.assertEqual(report.onsets.strong.matched, 2)
            self.assertEqual(report.onsets.strong.missed, 1)
            self.assertEqual(report.onsets.strong.extra, 2)
            self.assertLess(report.onsets.strong.f1, 1.0)
            # The possible/inclusive view accepts the quiet fourth source hit,
            # but still exposes the omitted strong hit and invented late hit.
            self.assertEqual(report.onsets.possible.matched, 3)
            self.assertEqual(report.onsets.possible.missed, 1)
            self.assertEqual(report.onsets.possible.extra, 1)
            self.assertGreater(report.onsets.timing.absolute_error_p95_ms, 20.0)
            self.assertGreaterEqual(len(report.onsets.timing.segments), 3)

    def test_drum_family_distribution_and_annotation_accuracy(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / "drums.wav"
            self._write_drum_stem(stem)
            notes = [
                NoteEvent(0.500, 0.580, 35, 110),
                NoteEvent(1.000, 1.080, 36, 100),
                NoteEvent(1.500, 1.580, 36, 95),
            ]
            annotations = [
                FamilyAnnotation(0.500, "kick_high"),
                FamilyAnnotation(1.000, "kick_deep"),
                FamilyAnnotation(1.500, "kick_high"),  # intentional mismatch
            ]

            report = evaluate_stem_midi(
                stem,
                notes,
                kind="kick",
                annotations=annotations,
                pitch_family_map={35: "kick_high", 36: "kick_deep"},
            )

            drums = report.drums
            self.assertIsNotNone(drums)
            self.assertEqual(drums.pitch_counts, {"35": 1, "36": 2})
            self.assertEqual(drums.family_counts, {"kick_deep": 2, "kick_high": 1})
            self.assertEqual(drums.annotated_matched, 3)
            self.assertAlmostEqual(drums.annotated_family_accuracy, 2.0 / 3.0, places=6)
            self.assertEqual(drums.family_confusion["kick_high"]["kick_deep"], 1)

    def test_midi_path_input_and_report_are_json_serializable(self) -> None:
        try:
            import mido  # noqa: F401
        except ImportError:
            self.skipTest("MIDI path evaluation requires optional mido")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stem = root / "drums.wav"
            midi = root / "candidate.mid"
            self._write_drum_stem(stem)
            write_midi_file(
                midi,
                [
                    MidiTrack(
                        "Kick",
                        channel=9,
                        program=0,
                        notes=[
                            NoteEvent(0.500, 0.580, 36, 110),
                            NoteEvent(1.000, 1.080, 36, 100),
                            NoteEvent(1.500, 1.580, 36, 95),
                        ],
                    )
                ],
                bpm=120.0,
            )

            report = evaluate_stem_midi(stem, midi, kind="kick")
            restored = json.loads(report.to_json())

            self.assertEqual(report.note_count, 3)
            self.assertEqual(restored["note_count"], 3)
            self.assertEqual(restored["drums"]["pitch_counts"], {"36": 3})
            self.assertIsInstance(restored["onsets"]["references"], list)

    def test_pitched_metrics_separate_chroma_octave_and_contour_failures(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            stem = Path(folder) / "melody.wav"
            correct = self._write_melody_stem(stem)
            wrong_octave = [
                NoteEvent(note.start, note.end, note.pitch + 12, note.velocity)
                for note in correct
            ]
            reversed_contour = [
                NoteEvent(note.start, note.end, pitch, note.velocity)
                for note, pitch in zip(correct, (67, 64, 60))
            ]

            correct_report = evaluate_stem_midi(stem, correct, kind="keys")
            octave_report = evaluate_stem_midi(stem, wrong_octave, kind="keys")
            contour_report = evaluate_stem_midi(stem, reversed_contour, kind="keys")

            good = correct_report.pitched
            octave = octave_report.pitched
            contour = contour_report.pitched
            self.assertIsNotNone(good)
            self.assertIsNotNone(octave)
            self.assertIsNotNone(contour)
            # Pitch-class chroma alone cannot see an octave error.
            self.assertGreater(good.chroma_similarity, 0.99)
            self.assertAlmostEqual(good.chroma_similarity, octave.chroma_similarity, places=6)
            self.assertGreater(good.mean_pitch_support, octave.mean_pitch_support + 0.8)
            self.assertEqual(good.octave_accuracy, 1.0)
            self.assertEqual(octave.octave_accuracy, 0.0)
            # The same three pitch classes in reverse order retain global chroma
            # while failing the melodic direction comparison.
            self.assertGreater(contour.chroma_similarity, 0.99)
            self.assertEqual(good.contour_direction_accuracy, 1.0)
            self.assertEqual(contour.contour_direction_accuracy, 0.0)
            self.assertLess(contour.contour_pitch_correlation, -0.9)
            self.assertEqual(good.candidate_polyphony_max, 1)
            self.assertAlmostEqual(good.onset_density_ratio, 1.0, places=6)

    @staticmethod
    def _write_drum_stem(path: Path, sample_rate: int = 16_000) -> None:
        duration = 3.0
        values = np.zeros(int(duration * sample_rate), dtype=np.float64)
        generator = np.random.default_rng(7)
        for time, amplitude in ((0.5, 1.0), (1.0, 0.85), (1.5, 0.70), (2.0, 0.25)):
            length = int(0.060 * sample_rate)
            position = np.arange(length, dtype=np.float64) / sample_rate
            burst = amplitude * np.exp(-position * 55.0) * (
                np.sin(2.0 * math.pi * 65.0 * position)
                + 0.25 * generator.standard_normal(length)
            )
            start = int(time * sample_rate)
            values[start : start + length] += burst
        SemanticEvaluationTests._write_wav(path, values, sample_rate)

    @staticmethod
    def _write_melody_stem(path: Path, sample_rate: int = 16_000) -> list[NoteEvent]:
        values = np.zeros(int(2.7 * sample_rate), dtype=np.float64)
        notes = [
            NoteEvent(0.25, 0.75, 60, 90),
            NoteEvent(1.00, 1.50, 64, 90),
            NoteEvent(1.75, 2.25, 67, 90),
        ]
        fade = int(0.020 * sample_rate)
        for note in notes:
            start = int(note.start * sample_rate)
            end = int(note.end * sample_rate)
            position = np.arange(end - start, dtype=np.float64) / sample_rate
            frequency = 440.0 * 2.0 ** ((note.pitch - 69) / 12.0)
            envelope = np.ones(end - start, dtype=np.float64)
            envelope[:fade] = np.linspace(0.0, 1.0, fade)
            envelope[-fade:] = np.linspace(1.0, 0.0, fade)
            values[start:end] += 0.70 * envelope * np.sin(
                2.0 * math.pi * frequency * position
            )
        SemanticEvaluationTests._write_wav(path, values, sample_rate)
        return notes

    @staticmethod
    def _write_wav(path: Path, values, sample_rate: int) -> None:
        pcm = (np.clip(values, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(pcm.tobytes())

    @staticmethod
    def _write_stereo_wav(path: Path, left, right, sample_rate: int) -> None:
        stereo = np.column_stack((left, right))
        pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(pcm.tobytes())


if __name__ == "__main__":
    unittest.main()
