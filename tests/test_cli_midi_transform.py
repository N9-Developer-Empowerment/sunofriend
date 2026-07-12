from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from sunofriend.cli import main
from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class MidiTransformCliTests(unittest.TestCase):
    def test_unmatched_expressive_pitch_bend_is_preserved_and_not_claimed_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "expressive.mid"
            output = root / "output.mid"
            bend = 9000
            track = (
                b"\x00\xff\x51\x03" + int(round(60_000_000 / 85)).to_bytes(3, "big")
                + b"\x00\xe0" + bytes((bend & 0x7F, bend >> 7))
                + b"\x00\x90\x3c\x64"
                + b"\x83\x60\x80\x3c\x00"
                + b"\x00\xff\x2f\x00"
            )
            payload = (
                b"MThd"
                + struct.pack(">IHHH", 6, 0, 1, 480)
                + b"MTrk"
                + struct.pack(">I", len(track))
                + track
            )
            source.write_bytes(payload)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "midi-transform",
                        str(source),
                        "--out",
                        str(output),
                        "--concert-pitch",
                    ]
                )
            report = json.loads(stdout.getvalue())
            output_bytes = output.read_bytes()

        self.assertEqual(result, 0)
        self.assertTrue(report["concert_pitch_cleanup_requested"])
        self.assertEqual(report["tuning_setups_removed"], 0)
        self.assertEqual(output_bytes, payload)

    def test_transposes_retunes_retimes_and_reports_complete_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "air.mid"
            output = root / "air-g-89.mid"
            write_midi_file(
                source,
                [
                    MidiTrack(
                        "Lead",
                        2,
                        80,
                        [NoteEvent(1.0, 2.0, 72, 96)],
                        pitch_bend_cents=-43.831051,
                    ),
                    MidiTrack("Drums", 9, 0, [NoteEvent(1.0, 1.1, 36, 110)]),
                ],
                bpm=85,
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "midi-transform",
                        str(source),
                        "--out",
                        str(output),
                        "--semitones",
                        "-5",
                        "--source-bpm",
                        "85",
                        "--target-bpm",
                        "89",
                        "--concert-pitch",
                    ]
                )
            report = json.loads(stdout.getvalue())
            clips = {clip.title: clip for clip in read_midi_clips(output)}

        self.assertEqual(result, 0)
        self.assertEqual(report["operation"], "midi-transform")
        self.assertEqual(report["file_count"], 1)
        self.assertEqual(report["set_garageband_tempo_to"], 89.0)
        self.assertTrue(report["concert_pitch_cleanup_requested"])
        self.assertEqual(report["tuning_setups_removed"], 1)
        self.assertEqual(report["files"][0]["tuning_setups_removed"], 1)
        self.assertEqual(clips["Lead"].notes[0].pitch, 67)
        self.assertEqual(clips["Drums"].notes[0].pitch, 36)
        self.assertAlmostEqual(clips["Lead"].bpm, 89.0, places=3)
        self.assertAlmostEqual(clips["Lead"].notes[0].start_beat, 85.0 / 60.0)

    def test_recursive_directory_command_preserves_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            for path in (source / "main.mid", source / "variants" / "alt.mid"):
                write_midi_file(
                    path,
                    [MidiTrack("Lead", 0, 0, [NoteEvent(0.0, 0.5, 60, 90)])],
                    bpm=93,
                )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "midi-transform",
                        str(source),
                        "--out",
                        str(output),
                        "--target-bpm",
                        "89",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(stdout.getvalue())["file_count"], 2)
            self.assertTrue((output / "main.mid").is_file())
            self.assertTrue((output / "variants" / "alt.mid").is_file())


if __name__ == "__main__":
    unittest.main()
