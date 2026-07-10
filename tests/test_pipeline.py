import json
import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.pipeline import run_remake


class PipelineTests(unittest.TestCase):
    def test_run_remake_from_folder_writes_midi_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Example-G major-150bpm-440hz"
            folder.mkdir()
            (folder / "Example_chords.pdf").write_bytes(
                b"(Key: G major) Tj\n(G    D    Am    C) Tj\n(Chords generated with Moises.ai) Tj"
            )
            for stem in ["kick", "snare", "hat", "cymbals", "toms", "other_kit", "bass"]:
                self._write_pulse_wav(folder / f"Example-{stem}-G major-150bpm-440hz.wav")

            out_dir = Path(tmp) / "out"
            result = run_remake(folder, out_dir=out_dir, style="edm")

            expected = {
                "bass_clean.mid",
                "chords_extracted.csv",
                "cymbals_clean.mid",
                "drums_clean.mid",
                "full_arrangement.mid",
                "hats_clean.mid",
                "kick_clean.mid",
                "other_kit_clean.mid",
                "pads_chords.mid",
                "quality_report.json",
                "snare_clean.mid",
                "toms_clean.mid",
            }
            self.assertEqual({path.name for path in result.files}, expected)
            report = json.loads((out_dir / "quality_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["metadata"]["key"], "G major")
        self.assertEqual(report["metadata"]["bpm"], 150.0)
        self.assertGreater(report["analysis"]["kick"]["events"], 0)
        self.assertGreater(report["analysis"]["cymbals"]["events"], 0)
        self.assertGreater(report["analysis"]["toms"]["events"], 0)
        self.assertGreater(report["analysis"]["other_kit"]["events"], 0)
        self.assertGreater(report["scores"]["drum_events"], 0)

    @staticmethod
    def _write_pulse_wav(path: Path) -> None:
        sample_rate = 8000
        total_frames = int(3.2 * sample_rate)
        samples = [0] * total_frames
        for pulse in [0.0, 0.8, 1.6, 2.4]:
            start = int(pulse * sample_rate)
            for index in range(start, min(total_frames, start + 320)):
                samples[index] = 10000

        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))


if __name__ == "__main__":
    unittest.main()
