import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.audio import analyze_stem_activity
from sunofriend.imagine import _filter_notes_by_activity
from sunofriend.models import NoteEvent


class AudioAnalysisTests(unittest.TestCase):
    def test_analyze_stem_activity_detects_pulses_on_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "kick.wav"
            self._write_pulse_wav(wav_path, pulse_seconds=[0.0, 0.8, 1.6], duration=2.4)

            result = analyze_stem_activity(wav_path, bpm=150, grid_subdiv=4)

        self.assertEqual(result.sample_rate, 8000)
        self.assertEqual(result.duration_seconds, 2.4)
        self.assertEqual([round(hit.beat, 2) for hit in result.events[:3]], [0.0, 2.0, 4.0])
        self.assertGreater(result.peak_rms, 0)

    def test_sparse_lead_activity_gate_rejects_low_level_full_song_bleed(self):
        try:
            import librosa  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"optional audio dependencies are unavailable: {exc}")

        sample_rate = 22050
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse-lead.wav"
            samples = []
            for index in range(sample_rate * 3):
                time = index / sample_rate
                amplitude = 8000 if 1.0 <= time < 1.35 else 5
                samples.append(int(amplitude * math.sin(2 * math.pi * 440 * time)))
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))

            bleed = NoteEvent(0.2, 0.5, 69, 70)
            audible = NoteEvent(1.05, 1.3, 69, 90)
            kept = _filter_notes_by_activity(str(path), [bleed, audible])

            all_bleed_path = Path(tmp) / "all-bleed.wav"
            quiet = [
                int(8 * math.sin(2 * math.pi * 440 * (index / sample_rate)))
                for index in range(sample_rate)
            ]
            with wave.open(str(all_bleed_path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                handle.writeframes(b"".join(struct.pack("<h", value) for value in quiet))
            all_bleed = _filter_notes_by_activity(
                str(all_bleed_path), [NoteEvent(0.1, 0.8, 69, 70)]
            )

        self.assertEqual(kept, [audible])
        self.assertEqual(all_bleed, [])

    @staticmethod
    def _write_pulse_wav(path: Path, pulse_seconds: list[float], duration: float) -> None:
        sample_rate = 8000
        total_frames = int(duration * sample_rate)
        pulse_frames = int(0.04 * sample_rate)
        samples = [0] * total_frames
        for pulse in pulse_seconds:
            start = int(pulse * sample_rate)
            for index in range(start, min(total_frames, start + pulse_frames)):
                samples[index] = 12000

        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))


if __name__ == "__main__":
    unittest.main()
