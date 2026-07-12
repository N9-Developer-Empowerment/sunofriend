from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from sunofriend.cli import main
from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class MidiAnchorCliTests(unittest.TestCase):
    def test_places_confirmed_downbeat_at_bar_two_and_reports_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "anchored.mid"
            write_midi_file(
                source,
                [
                    MidiTrack(
                        "Lead",
                        0,
                        0,
                        [NoteEvent(1.0, 1.5, 60, 90)],
                        pitch_bend_cents=-43.831051,
                    )
                ],
                bpm=60,
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "midi-anchor",
                        str(source),
                        "--out",
                        str(output),
                        "--source-downbeat-seconds",
                        "1.0",
                        "--source-bpm",
                        "60",
                        "--target-bpm",
                        "90",
                        "--target-downbeat-beat",
                        "4",
                        "--semitones",
                        "2",
                        "--concert-pitch",
                    ]
                )
            report = json.loads(stdout.getvalue())
            clip = read_midi_clips(output)[0]

        self.assertEqual(result, 0)
        self.assertEqual(report["operation"], "midi-anchor")
        self.assertEqual(report["source_downbeat_tick"], 480)
        self.assertEqual(report["target_downbeat_tick"], 1920)
        self.assertEqual(report["shift_ticks"], 1440)
        self.assertEqual(report["set_garageband_tempo_to"], 90.0)
        self.assertEqual(report["tuning_setups_removed"], 1)
        self.assertAlmostEqual(clip.bpm, 90.0, places=3)
        self.assertAlmostEqual(clip.notes[0].start_beat, 4.0)
        self.assertEqual(clip.notes[0].pitch, 62)


if __name__ == "__main__":
    unittest.main()
