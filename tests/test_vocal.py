from __future__ import annotations

import importlib.util
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sunofriend.models import NoteEvent
from sunofriend.vocal import (
    PitchFrame,
    VocalCandidate,
    VocalConfig,
    extract_pitch_frames,
    fractional_midi_to_hz,
    gentle_quantize_notes,
    hz_to_fractional_midi,
    phase_safe_downmix,
    select_backing_vocal_variants,
    simplify_vocal_notes,
    transcribe_vocal_frames,
    transcribe_vocal_melody,
)


AUDIO_STACK_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("librosa", "numpy", "soundfile")
)


def _frames(
    midis: list[float | None],
    *,
    tuning_hz: float = 440.0,
    hop: float = 0.01,
    rms: float | list[float] = 0.1,
    onsets: dict[int, float] | None = None,
    voiced_probability: float = 0.95,
) -> list[PitchFrame]:
    levels = [float(rms)] * len(midis) if isinstance(rms, (int, float)) else rms
    return [
        PitchFrame(
            time=index * hop,
            f0_hz=(
                fractional_midi_to_hz(midi, tuning_hz)
                if midi is not None
                else None
            ),
            voiced_probability=voiced_probability if midi is not None else 0.0,
            rms=levels[index],
            onset_strength=(onsets or {}).get(index, 0.0),
            source="synthetic-f0",
        )
        for index, midi in enumerate(midis)
    ]


class VocalContourTests(unittest.TestCase):
    def test_explicit_429_tuning_prevents_near_boundary_semitone_flip(self) -> None:
        # This is intended MIDI 68.9 in an A=429 recording.  Treating the same
        # frequency as A=440 moves it below the half-semitone boundary.
        frequency = fractional_midi_to_hz(68.9, 429.0)

        tuned = hz_to_fractional_midi(frequency, 429.0)
        wrong_reference = hz_to_fractional_midi(frequency, 440.0)

        self.assertAlmostEqual(tuned, 68.9, places=8)
        self.assertEqual(math.floor(tuned + 0.5), 69)
        self.assertEqual(math.floor(wrong_reference + 0.5), 68)

    def test_vibrato_remains_one_discrete_note(self) -> None:
        contour = [
            69.0 + 0.40 * math.sin(2.0 * math.pi * 5.5 * index * 0.01)
            for index in range(120)
        ]

        result = transcribe_vocal_frames(
            _frames(contour), config=VocalConfig(bpm=120.0)
        )

        self.assertEqual(
            [note.pitch for note in result.variants["contour_clean"]], [69]
        )

    def test_slide_uses_stable_endpoints_not_a_chromatic_staircase(self) -> None:
        contour = [60.0] * 50
        contour += [60.0 + 4.0 * index / 20.0 for index in range(20)]
        contour += [64.0] * 50

        result = transcribe_vocal_frames(
            _frames(contour), config=VocalConfig(bpm=120.0)
        )
        notes = result.variants["contour_clean"]

        self.assertEqual([note.pitch for note in notes], [60, 64])
        self.assertGreaterEqual(notes[1].start, 0.60)
        self.assertLessEqual(notes[1].start, 0.72)

    def test_same_pitch_consonant_reattack_remains_two_notes(self) -> None:
        contour: list[float | None] = [69.0] * 40 + [None] * 4 + [69.0] * 40

        result = transcribe_vocal_frames(
            _frames(contour, onsets={44: 0.9}),
            config=VocalConfig(bpm=120.0),
        )

        self.assertEqual(
            [note.pitch for note in result.variants["contour_clean"]], [69, 69]
        )

    def test_tiny_unvoiced_gap_without_reattack_is_bridged(self) -> None:
        contour: list[float | None] = [69.0] * 40 + [None] * 3 + [69.0] * 40

        result = transcribe_vocal_frames(
            _frames(contour), config=VocalConfig(bpm=120.0)
        )

        self.assertEqual(
            [note.pitch for note in result.variants["contour_clean"]], [69]
        )

    def test_unvoiced_breath_noise_emits_no_notes(self) -> None:
        frames = [
            PitchFrame(index * 0.01, None, 0.05, 0.2, onset_strength=0.8)
            for index in range(100)
        ]

        result = transcribe_vocal_frames(frames, config=VocalConfig())

        self.assertEqual(result.notes, [])
        self.assertIn(
            "No sufficiently voiced pitch frames were found.",
            result.diagnostics.warnings,
        )

    def test_velocity_uses_voiced_loudness_not_a_single_attack_peak(self) -> None:
        contour: list[float | None] = [60.0] * 40 + [None] * 10 + [62.0] * 40
        levels = [0.02] * 40 + [0.0] * 10 + [0.20] * 40
        levels[0] = 0.9  # consonant/attack outlier in the quiet phrase

        result = transcribe_vocal_frames(
            _frames(contour, rms=levels, onsets={0: 1.0, 50: 0.8}),
            config=VocalConfig(),
        )
        notes = result.variants["contour_clean"]

        self.assertEqual([note.pitch for note in notes], [60, 62])
        self.assertGreater(notes[1].velocity, notes[0].velocity)

    def test_variants_have_one_provenance_record_per_note(self) -> None:
        result = transcribe_vocal_frames(
            _frames([60.0] * 40 + [None] * 8 + [62.0] * 40),
            config=VocalConfig(tuning_hz=429.0, tuning_source="folder"),
        )

        for name, notes in result.variants.items():
            self.assertEqual(len(result.provenance[name]), len(notes))
            for record in result.provenance[name]:
                self.assertEqual(record.details["tuning_hz"], 429.0)
        self.assertAlmostEqual(
            result.diagnostics.garageband_fine_tune_cents,
            -43.831051,
            places=5,
        )


class VocalVariantTests(unittest.TestCase):
    def test_instrument_simple_removes_a_short_between_note_ornament(self) -> None:
        config = VocalConfig(simple_ornament_ms=100.0)
        notes = [
            NoteEvent(0.0, 0.5, 60, 80),
            NoteEvent(0.5, 0.57, 61, 72),
            NoteEvent(0.57, 1.0, 62, 84),
        ]

        simplified = simplify_vocal_notes(notes, config=config)

        self.assertEqual([note.pitch for note in simplified], [60, 62])
        self.assertEqual(simplified[1].start, 0.5)

    def test_instrument_simple_does_not_bridge_an_ornament_across_silence(self) -> None:
        config = VocalConfig(simple_ornament_ms=100.0, simple_gap_ms=40.0)
        notes = [
            NoteEvent(0.0, 0.5, 60, 80),
            NoteEvent(5.0, 5.07, 61, 72),
            NoteEvent(10.0, 10.5, 62, 84),
        ]

        simplified = simplify_vocal_notes(notes, config=config)

        self.assertEqual(simplified, notes)

    def test_gentle_quantize_obeys_maximum_shift(self) -> None:
        config = VocalConfig(
            bpm=120.0,
            quantize_subdivision=4,
            quantize_max_shift_ms=55.0,
        )
        notes = [
            NoteEvent(0.03, 0.49, 60, 80),
            NoteEvent(0.561, 0.94, 62, 80),
        ]

        quantized = gentle_quantize_notes(notes, config=config)

        self.assertAlmostEqual(quantized[0].start, 0.0)
        self.assertAlmostEqual(quantized[0].end, 0.5)
        self.assertAlmostEqual(quantized[1].start, 0.561)

    def test_gentle_quantize_never_collapses_a_note_onto_one_grid_line(self) -> None:
        config = VocalConfig(
            bpm=120.0,
            min_note_ms=65.0,
            quantize_subdivision=4,
            quantize_max_shift_ms=55.0,
        )
        note = NoteEvent(0.095, 0.160, 60, 80)

        quantized = gentle_quantize_notes([note], config=config)

        self.assertAlmostEqual(quantized[0].start, note.start)
        self.assertAlmostEqual(quantized[0].end, note.end)
        self.assertGreaterEqual(quantized[0].end - quantized[0].start, 0.065)

    def test_gentle_quantize_does_not_create_cross_pitch_overlap(self) -> None:
        config = VocalConfig(
            bpm=120.0,
            min_note_ms=65.0,
            quantize_subdivision=4,
            quantize_max_shift_ms=55.0,
        )
        notes = [
            NoteEvent(0.03, 0.59, 60, 80),
            NoteEvent(0.54, 0.90, 62, 82),
        ]

        quantized = gentle_quantize_notes(notes, config=config)

        self.assertLessEqual(quantized[0].end, quantized[1].start)
        self.assertTrue(
            all(note.end - note.start >= 0.065 for note in quantized)
        )

    def test_backing_variants_select_dominant_top_and_full_stack(self) -> None:
        candidates: list[VocalCandidate] = []
        for start, pitches in ((0.0, (60, 64, 67)), (1.0, (62, 65, 69))):
            for pitch, confidence, velocity in zip(
                pitches,
                (0.72, 0.96, 0.80),
                (70, 112, 82),
            ):
                candidates.append(
                    VocalCandidate(
                        NoteEvent(start, start + 0.8, pitch, velocity),
                        confidence=confidence,
                        spectral_support=confidence,
                    )
                )

        result = select_backing_vocal_variants(
            candidates,
            config=VocalConfig(role="backing"),
        )

        self.assertEqual(
            [note.pitch for note in result.variants["dominant_line"]], [64, 65]
        )
        self.assertEqual(
            [note.pitch for note in result.variants["top_line"]], [67, 69]
        )
        self.assertEqual(len(result.variants["harmony_stack"]), 6)
        self.assertEqual(result.diagnostics.estimated_voice_count, 3)

    def test_selected_backing_lines_clip_small_candidate_overlaps(self) -> None:
        candidates = [
            VocalCandidate(NoteEvent(0.0, 0.80, 60, 90), 0.90),
            VocalCandidate(NoteEvent(0.77, 1.40, 62, 92), 0.92),
        ]

        result = select_backing_vocal_variants(
            candidates,
            config=VocalConfig(role="backing"),
        )
        dominant = result.variants["dominant_line"]

        self.assertEqual(len(dominant), 2)
        self.assertLessEqual(dominant[0].end, dominant[1].start)
        self.assertEqual(len(result.variants["harmony_stack"]), 2)
        self.assertGreater(
            result.variants["harmony_stack"][0].end,
            result.variants["harmony_stack"][1].start,
        )

    def test_weak_octave_formant_ghost_is_quarantined(self) -> None:
        candidates = [
            VocalCandidate(NoteEvent(0.0, 0.8, 60, 105), 0.92, 0.8),
            VocalCandidate(NoteEvent(0.0, 0.8, 72, 45), 0.40, 0.1),
        ]

        result = select_backing_vocal_variants(
            candidates,
            config=VocalConfig(role="backing"),
        )

        self.assertEqual(
            [note.pitch for note in result.variants["harmony_stack"]], [60]
        )
        self.assertEqual(
            [note.pitch for note in result.variants["uncertain"]], [72]
        )

    def test_empty_backing_evidence_is_explicit(self) -> None:
        result = select_backing_vocal_variants(
            [], config=VocalConfig(role="backing")
        )

        self.assertEqual(result.notes, [])
        self.assertIn(
            "No supported backing-vocal pitch evidence was found.",
            result.diagnostics.warnings,
        )


@unittest.skipUnless(AUDIO_STACK_AVAILABLE, "optional audio stack is unavailable")
class VocalAudioAdapterTests(unittest.TestCase):
    def test_phase_safe_downmix_preserves_antiphase_signal(self) -> None:
        import numpy as np

        left = np.sin(np.linspace(0.0, 20.0 * math.pi, 2000))
        stereo = np.column_stack((left, -left))

        mono = phase_safe_downmix(stereo)

        self.assertGreater(float(np.sqrt(np.mean(mono * mono))), 0.6)

    def test_pyin_extracts_pitch_from_antiphase_stereo_wav(self) -> None:
        sample_rate = 22_050
        duration = 0.9
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "antiphase-vocal.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                payload = bytearray()
                for index in range(int(duration * sample_rate)):
                    envelope = min(1.0, index / 500.0, (duration * sample_rate - index) / 500.0)
                    value = int(
                        0.45
                        * envelope
                        * 32767
                        * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)
                    )
                    payload.extend(struct.pack("<hh", value, -value))
                handle.writeframes(bytes(payload))

            frames = extract_pitch_frames(path, config=VocalConfig())

        frequencies = [
            frame.f0_hz
            for frame in frames
            if frame.f0_hz is not None and frame.voiced_probability >= 0.75
        ]
        self.assertGreater(len(frequencies), 20)
        self.assertAlmostEqual(float(sorted(frequencies)[len(frequencies) // 2]), 440.0, delta=4.0)

    def test_absolute_gate_rejects_low_level_separator_dither_before_ml(self) -> None:
        sample_rate = 22_050
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty-backing-vocals.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                payload = bytearray()
                # Roughly 0.0004 peak: above digital zero, but safely below the
                # absolute stem-evidence floor and comparable to separator dither.
                for index in range(sample_rate):
                    value = 13 if index % 2 else -13
                    payload.extend(struct.pack("<hh", value, -value))
                handle.writeframes(bytes(payload))

            with patch("sunofriend.vocal.extract_pitch_frames") as f0_tracker, patch(
                "sunofriend.vocal.extract_backing_candidates"
            ) as polyphonic_tracker:
                result = transcribe_vocal_melody(
                    path,
                    config=VocalConfig(role="backing"),
                )
                f0_tracker.assert_not_called()
                polyphonic_tracker.assert_not_called()

        self.assertEqual(result.notes, [])
        self.assertTrue(all(not notes for notes in result.variants.values()))
        self.assertTrue(
            any(
                "below the absolute vocal evidence floor" in warning
                for warning in result.diagnostics.warnings
            )
        )

    def test_backing_fallback_keeps_notes_when_provenance_is_short(self) -> None:
        fallback_notes = [
            NoteEvent(0.0, 0.4, 60, 80),
            NoteEvent(0.5, 0.9, 62, 82),
        ]
        fallback = SimpleNamespace(
            notes=fallback_notes,
            provenance={"contour_clean": []},
        )

        with patch(
            "sunofriend.vocal.vocal_signal_stats", return_value=(0.5, 0.1)
        ), patch(
            "sunofriend.vocal.extract_pitch_frames", return_value=_frames([60.0])
        ), patch(
            "sunofriend.vocal.extract_backing_candidates", return_value=[]
        ), patch(
            "sunofriend.vocal.transcribe_vocal_frames", return_value=fallback
        ):
            result = transcribe_vocal_melody(
                "backing.wav",
                config=VocalConfig(role="backing"),
            )

        self.assertEqual(result.variants["dominant_line"], fallback_notes)
        self.assertEqual(result.variants["harmony_stack"], fallback_notes)


if __name__ == "__main__":
    unittest.main()
