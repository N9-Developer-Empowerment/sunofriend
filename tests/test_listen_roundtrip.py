"""Synthetic round-trip tests for the listen/refine pipeline.

Ground truth MIDI -> FluidSynth render -> transcribe -> compare with truth.
Skipped automatically when fluidsynth / librosa / basic-pitch are unavailable
(e.g. plain CI without audio deps).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


def _audio_ready() -> bool:
    try:
        import librosa  # noqa: F401

        from sunofriend.render import is_available

        return is_available()
    except Exception:
        return False


def _basic_pitch_ready() -> bool:
    try:
        import basic_pitch  # noqa: F401

        return True
    except Exception:
        return False


AUDIO = _audio_ready()


@unittest.skipUnless(AUDIO, "fluidsynth/librosa not available")
class DrumRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sunofriend.render import render_midi_to_wav

        cls.dir = Path(tempfile.mkdtemp(prefix="sf_rt_"))
        cls.cases = {
            "kick": (36, [t * 0.5 for t in range(0, 16, 2)]),
            "snare": (38, [t * 0.5 for t in range(2, 16, 4)]),
            "hat": (42, [t * 0.25 for t in range(0, 32)]),
        }
        for kind, (pitch, times) in cls.cases.items():
            notes = [NoteEvent(t, t + 0.08, pitch, 100) for t in times]
            midi = cls.dir / f"{kind}.mid"
            write_midi_file(midi, [MidiTrack(kind, 9, 0, notes)], bpm=120)
            render_midi_to_wav(midi, cls.dir / f"{kind}.wav")

    def test_all_hits_recovered(self):
        from sunofriend.transcribe_drums import transcribe_drum_stem

        for kind, (pitch, times) in self.cases.items():
            with self.subTest(kind=kind):
                got = transcribe_drum_stem(str(self.dir / f"{kind}.wav"), kind)
                self.assertEqual(len(got), len(times), f"{kind}: wrong hit count")
                matched = sum(
                    1 for t in times if any(abs(g.start - t) < 0.035 for g in got)
                )
                self.assertEqual(matched, len(times), f"{kind}: mistimed hits")
                self.assertTrue(all(g.pitch == pitch for g in got))

    def test_refine_loop_converges(self):
        from sunofriend.loop import refine_stem

        result = refine_stem(
            self.dir / "hat.wav", kind="hat", bpm=120, out_dir=self.dir / "out",
            max_iterations=6,
        )
        self.assertGreater(result.score, 0.9)
        self.assertTrue(result.midi_path.exists())
        # timing should tighten after iteration 0
        self.assertLessEqual(
            result.history[-1].detail.get("mean_abs_offset_ms", 99),
            result.history[0].detail.get("mean_abs_offset_ms", 0) + 0.01,
        )


@unittest.skipUnless(AUDIO and _basic_pitch_ready(), "basic-pitch not available")
class PitchedRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sunofriend.render import render_midi_to_wav

        cls.dir = Path(tempfile.mkdtemp(prefix="sf_rtp_"))
        cls.chords = [
            (0.0, [60, 64, 67]),
            (2.4, [57, 60, 64]),
            (4.8, [53, 57, 60]),
            (7.2, [55, 59, 62]),
        ]
        notes = [
            NoteEvent(t, t + 2.4, p, 90) for t, chord in cls.chords for p in chord
        ]
        midi = cls.dir / "keys.mid"
        write_midi_file(midi, [MidiTrack("keys", 0, 0, notes)], bpm=100)
        render_midi_to_wav(midi, cls.dir / "keys.wav")

    def test_chords_recovered_exactly(self):
        from sunofriend.transcribe_pitched import transcribe_pitched_stem

        got = transcribe_pitched_stem(str(self.dir / "keys.wav"), kind="keys")
        self.assertEqual(len(got), 12, "expected exactly 4 triads x 3 notes")
        for t, chord in self.chords:
            found = sorted(g.pitch for g in got if abs(g.start - t) < 0.2)
            self.assertEqual(found, sorted(chord), f"chord at t={t}")


if __name__ == "__main__":
    unittest.main()
