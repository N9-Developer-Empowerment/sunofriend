import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.audio import analyze_stem_activity


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
