import tempfile
import unittest
from pathlib import Path

from sunofriend.midi import MidiTrack, pitch_bend_value, write_midi_file
from sunofriend.models import NoteEvent


class MidiWriterTests(unittest.TestCase):
    def test_write_midi_file_creates_multitrack_type_one_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "arrangement.mid"
            tracks = [
                MidiTrack("Drums", channel=9, program=0, notes=[NoteEvent(0.0, 0.08, 36, 110)]),
                MidiTrack("Bass", channel=0, program=38, notes=[NoteEvent(0.0, 0.4, 43, 95)]),
            ]

            write_midi_file(output, tracks, bpm=150)
            data = output.read_bytes()

        self.assertTrue(data.startswith(b"MThd"))
        self.assertEqual(data.count(b"MTrk"), 3)
        self.assertIn(b"Drums", data)
        self.assertIn(b"Bass", data)

    def test_track_can_embed_a_source_tuning_bend_before_its_first_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "tuned.mid"
            write_midi_file(
                output,
                [
                    MidiTrack(
                        "Vocal melody",
                        channel=2,
                        program=73,
                        notes=[NoteEvent(0.0, 0.5, 69, 96)],
                        pitch_bend_cents=-43.83,
                    )
                ],
                bpm=85,
            )
            data = output.read_bytes()

        # RPN 0 selects pitch-bend sensitivity; Data Entry sets +/-2
        # semitones; the channel-2 pitch wheel then applies about -43.8 cents.
        self.assertIn(bytes([0xB2, 101, 0]), data)
        self.assertIn(bytes([0xB2, 100, 0]), data)
        self.assertIn(bytes([0xB2, 6, 2]), data)
        bend = pitch_bend_value(-43.83)
        bend_event = bytes([0xE2, bend & 0x7F, bend >> 7])
        note_event = bytes([0x92, 69, 96])
        self.assertLess(data.index(bend_event), data.index(note_event))

    def test_pitch_bend_value_validates_range_and_endpoints(self):
        self.assertEqual(pitch_bend_value(0), 8192)
        self.assertEqual(pitch_bend_value(-200), 0)
        self.assertEqual(pitch_bend_value(200), 16383)
        with self.assertRaises(ValueError):
            pitch_bend_value(201)


if __name__ == "__main__":
    unittest.main()
