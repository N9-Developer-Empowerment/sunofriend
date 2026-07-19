from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.timbre_resynthesis import create_timbre_resynthesis


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TimbreResynthesisTests(unittest.TestCase):
    def _fixtures(self, root: Path, *, polyphonic: bool = False):
        sample_rate = 44100
        midi = root / "bass.mid"
        notes = [
            NoteEvent(0.1, 0.5, 36, 88),
            NoteEvent(0.5, 1.0, 40, 92),
            NoteEvent(1.0, 1.55, 43, 96),
        ]
        if polyphonic:
            notes.append(NoteEvent(1.2, 1.45, 48, 80))
        write_midi_file(
            midi,
            [MidiTrack("bass", 0, 33, notes)],
            bpm=120,
        )

        audio = np.zeros((sample_rate * 2, 2), dtype=np.float32)
        for note in notes[:3]:
            start = int(note.start * sample_rate)
            end = int(note.end * sample_rate)
            time = np.arange(end - start) / sample_rate
            frequency = 440.0 * 2.0 ** ((note.pitch - 69) / 12.0)
            envelope = np.minimum(1.0, time / 0.008) * np.exp(-time * 0.7)
            signal = envelope * (
                0.72 * np.sin(2 * math.pi * frequency * time)
                + 0.20 * np.sin(2 * math.pi * frequency * 2 * time + 0.3)
                + 0.08 * np.sin(2 * math.pi * frequency * 3 * time + 0.7)
            )
            audio[start:end, 0] += signal.astype(np.float32) * 0.35
            audio[start:end, 1] += signal.astype(np.float32) * 0.35
        source = root / "source.wav"
        soundfile.write(source, audio, sample_rate, subtype="PCM_24")
        soundfont = root / "source.sf2"
        soundfont.write_bytes(b"RIFF-test-soundfont")
        return source, midi, soundfont

    @staticmethod
    def _fake_render(midi_path, wav_path, sample_rate=44100, **_kwargs):
        clips = read_midi_clips(Path(midi_path))
        frame_count = sample_rate * 2
        audio = np.zeros((frame_count, 2), dtype=np.float32)
        for note in clips[0].notes:
            start = int(note.source_start_seconds * sample_rate)
            end = min(frame_count, int(note.source_end_seconds * sample_rate))
            time = np.arange(end - start) / sample_rate
            frequency = 440.0 * 2.0 ** ((note.pitch - 69) / 12.0)
            signal = 0.2 * np.sin(2 * math.pi * frequency * time)
            audio[start:end] += signal[:, np.newaxis]
        soundfile.write(wav_path, audio, sample_rate, subtype="PCM_24")
        return Path(wav_path)

    def test_fixed_midi_candidates_are_audible_and_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, midi, soundfont = self._fixtures(root)
            source_hash = _sha256(source)
            midi_hash = _sha256(midi)

            with patch(
                "sunofriend.render.render_midi_to_wav",
                side_effect=self._fake_render,
            ):
                first = create_timbre_resynthesis(
                    source,
                    midi,
                    out_dir=root / "first",
                    source_soundfont_path=soundfont,
                )
                create_timbre_resynthesis(
                    source,
                    midi,
                    out_dir=root / "second",
                    source_soundfont_path=soundfont,
                )

            self.assertEqual(first["status"], "review-required")
            self.assertFalse(first["neural_model_used"])
            self.assertEqual(first["midi"]["note_count"], 3)
            self.assertGreater(first["profile"]["fitted_note_count"], 0)
            self.assertEqual(
                first["candidates"]["harmonic_noise_resynthesis"]["audibility"][
                    "silent_note_count"
                ],
                0,
            )
            self.assertEqual(
                first["candidates"]["source_sampler"]["audibility"][
                    "silent_note_count"
                ],
                0,
            )
            self.assertEqual(first["effects"]["midi_notes_changed"], 0)
            self.assertEqual(_sha256(source), source_hash)
            self.assertEqual(_sha256(midi), midi_hash)
            self.assertEqual(
                _sha256(root / "first" / "harmonic-noise-resynthesis.wav"),
                _sha256(root / "second" / "harmonic-noise-resynthesis.wav"),
            )
            self.assertEqual(
                _sha256(root / "first" / "timbre_profile.json"),
                _sha256(root / "second" / "timbre_profile.json"),
            )

            seed = json.loads(
                (root / "first" / "timbre_resynthesis_review.json").read_text()
            )
            self.assertEqual(seed["status"], "unreviewed")
            self.assertEqual(len(seed["choices"]), 3)
            self.assertTrue(all(not row["reviewed"] for row in seed["choices"]))
            page = (root / "first" / "timbre_resynthesis_review.html").read_text()
            self.assertIn("Fixed-MIDI timbre review", page)
            self.assertIn("Export review JSON", page)

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                create_timbre_resynthesis(
                    source,
                    midi,
                    out_dir=root / "first",
                )

    def test_polyphonic_performance_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, midi, _ = self._fixtures(root, polyphonic=True)

            with self.assertRaisesRegex(ValueError, "monophonic"):
                create_timbre_resynthesis(
                    source,
                    midi,
                    out_dir=root / "rejected",
                )
            self.assertFalse((root / "rejected").exists())


if __name__ == "__main__":
    unittest.main()
