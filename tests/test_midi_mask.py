from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.cli import build_parser, main
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.midi_mask import MIDI_MASK_SCHEMA, create_midi_mask
from sunofriend.models import NoteEvent


class MidiMaskTests(unittest.TestCase):
    def _fixture(self, directory: str, *, two_tracks: bool = False) -> tuple[Path, Path]:
        root = Path(directory)
        sample_rate = 16_000
        seconds = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
        c4 = 0.25 * np.sin(2.0 * np.pi * 261.625565 * seconds)
        e4 = 0.25 * np.sin(2.0 * np.pi * 329.627557 * seconds)
        stereo = np.column_stack((c4 + e4, 0.8 * c4 + 1.2 * e4)).astype("float32")
        audio = root / "mixed-keys.wav"
        soundfile.write(audio, stereo, sample_rate, subtype="FLOAT")

        tracks = [
            MidiTrack(
                "electric_piano",
                channel=0,
                program=4,
                notes=[NoteEvent(0.25, 1.75, 60, 100)],
            )
        ]
        if two_tracks:
            tracks.append(
                MidiTrack(
                    "synth_lead",
                    channel=1,
                    program=81,
                    notes=[NoteEvent(0.25, 1.75, 64, 100)],
                )
            )
        midi = root / "guide.mid"
        write_midi_file(midi, tracks, bpm=120.0)
        return audio, midi

    def test_extracts_guide_pitch_and_persists_exact_target_residual_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, midi = self._fixture(directory)
            output = Path(directory) / "mask"

            report = create_midi_mask(
                audio,
                midi,
                out_dir=output,
                start_seconds=0.0,
                end_seconds=2.0,
                harmonics=1,
                bandwidth_cents=35.0,
                attack_seconds=0.02,
                release_seconds=0.02,
                transient_seconds=0.04,
                transient_strength=0.4,
                n_fft=2048,
                hop_length=256,
            )

            self.assertEqual(report["schema"], MIDI_MASK_SCHEMA)
            self.assertEqual(report["status"], "complete")
            self.assertTrue(report["reconstruction"]["passed"])
            self.assertLessEqual(
                report["reconstruction"]["maximum_absolute_error"], 1e-6
            )
            self.assertEqual(report["guide_midi"]["excerpt_note_count"], 1)
            self.assertEqual(report["guide_midi"]["excerpt_pitches"], [60])
            self.assertEqual(report["parameters"]["transient_seconds"], 0.04)
            self.assertEqual(report["parameters"]["transient_strength"], 0.4)
            self.assertFalse(report["effects"]["source_audio_mutated"])
            self.assertFalse(report["effects"]["guide_midi_mutated"])
            self.assertEqual(report["effects"]["midi_notes_mutated"], 0)

            source, sample_rate = soundfile.read(
                output / "source-excerpt.wav", dtype="float32", always_2d=True
            )
            target, _ = soundfile.read(
                output / "target.wav", dtype="float32", always_2d=True
            )
            residual, _ = soundfile.read(
                output / "residual.wav", dtype="float32", always_2d=True
            )
            np.testing.assert_allclose(target + residual, source, atol=1e-6)
            self.assertGreater(
                self._tone_energy(target, sample_rate, 261.625565),
                self._tone_energy(target, sample_rate, 329.627557) * 5.0,
            )
            self.assertGreater(
                self._tone_energy(residual, sample_rate, 329.627557),
                self._tone_energy(residual, sample_rate, 261.625565) * 4.0,
            )
            saved = json.loads((output / "midi_mask.json").read_text())
            self.assertEqual(saved["artifacts"]["target"]["path"], "target.wav")
            self.assertEqual(len(saved["artifacts"]["target"]["sha256"]), 64)
            self.assertEqual(
                saved["artifacts"]["guide_excerpt_midi"]["path"],
                "guide-excerpt.mid",
            )
            self.assertEqual((output / "guide-excerpt.mid").read_bytes()[:4], b"MThd")
            self.assertEqual(saved["guide_midi"]["excerpt_midi_bpm"], 120.0)

    def test_requires_explicit_track_and_fresh_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio, midi = self._fixture(directory, two_tracks=True)
            with self.assertRaisesRegex(ValueError, "choose --track-index"):
                create_midi_mask(
                    audio,
                    midi,
                    out_dir=Path(directory) / "ambiguous",
                    end_seconds=2.0,
                )

            output = Path(directory) / "selected"
            report = create_midi_mask(
                audio,
                midi,
                out_dir=output,
                track_index=1,
                end_seconds=2.0,
                harmonics=1,
                n_fft=1024,
                hop_length=256,
            )
            self.assertEqual(report["guide_midi"]["selected_track"], "synth_lead")
            self.assertEqual(report["guide_midi"]["excerpt_pitches"], [64])
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                create_midi_mask(
                    audio,
                    midi,
                    out_dir=output,
                    track_index=1,
                    end_seconds=2.0,
                )

    def test_cli_exposes_short_midi_mask_parameters(self) -> None:
        args = build_parser().parse_args(
            [
                "midi-mask",
                "keys.wav",
                "roles.mid",
                "--track-index",
                "2",
                "--start-seconds",
                "200",
                "--end-seconds",
                "216",
                "--harmonics",
                "10",
                "--transient-ms",
                "45",
                "--transient-strength",
                "0.4",
                "--out-dir",
                "work/mask",
            ]
        )

        self.assertEqual(args.command, "midi-mask")
        self.assertEqual(args.track_index, 2)
        self.assertEqual(args.start_seconds, 200.0)
        self.assertEqual(args.end_seconds, 216.0)
        self.assertEqual(args.harmonics, 10)
        self.assertEqual(args.transient_ms, 45.0)
        self.assertEqual(args.transient_strength, 0.4)
        self.assertEqual(args.out_dir, "work/mask")

        stdout = io.StringIO()
        with patch(
            "sunofriend.midi_mask.create_midi_mask",
            return_value={"status": "complete", "report": "work/mask/midi_mask.json"},
        ) as create, redirect_stdout(stdout):
            result = main(
                [
                    "midi-mask",
                    "keys.wav",
                    "roles.mid",
                    "--track-index",
                    "2",
                    "--start-seconds",
                    "200",
                    "--end-seconds",
                    "216",
                    "--transient-ms",
                    "45",
                    "--transient-strength",
                    "0.4",
                    "--out-dir",
                    "work/mask",
                ]
            )

        self.assertEqual(result, 0)
        create.assert_called_once_with(
            "keys.wav",
            "roles.mid",
            out_dir="work/mask",
            track_index=2,
            start_seconds=200.0,
            end_seconds=216.0,
            harmonics=8,
            bandwidth_cents=55.0,
            attack_seconds=0.06,
            release_seconds=0.12,
            transient_seconds=0.045,
            transient_strength=0.4,
            n_fft=4096,
            hop_length=512,
        )
        self.assertIn('"status": "complete"', stdout.getvalue())

    @staticmethod
    def _tone_energy(values: np.ndarray, sample_rate: int, frequency: float) -> float:
        mono = np.mean(values[int(0.5 * sample_rate) : int(1.5 * sample_rate)], axis=1)
        spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
        frequencies = np.fft.rfftfreq(len(mono), 1.0 / sample_rate)
        index = int(np.argmin(np.abs(frequencies - frequency)))
        return float(np.max(spectrum[max(0, index - 1) : index + 2]))


if __name__ == "__main__":
    unittest.main()
