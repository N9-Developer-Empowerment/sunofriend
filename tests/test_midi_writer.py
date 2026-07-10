import tempfile
import unittest
from pathlib import Path

from sunofriend.midi import MidiTrack, write_midi_file
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


if __name__ == "__main__":
    unittest.main()
