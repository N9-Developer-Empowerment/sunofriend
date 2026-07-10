import tempfile
import unittest
from pathlib import Path

from sunofriend.chords import (
    choose_voicing,
    extract_chords_from_moises_pdf,
    make_chord_segments,
    parse_chord_name,
    parse_key,
)
from sunofriend.metadata import infer_project_metadata


class MetadataAndChordTests(unittest.TestCase):
    def test_infer_metadata_from_moises_folder_name(self):
        meta = infer_project_metadata(
            Path("/tmp/Get This Party Start_reference_24bit_44hz_target-14-G major-150bpm-440hz")
        )

        self.assertEqual(meta.key, "G major")
        self.assertEqual(meta.bpm, 150.0)
        self.assertEqual(meta.tuning_hz, 440.0)

    def test_extract_chords_from_simple_moises_pdf_stream_text(self):
        pdf_text = b"""
        (Key: G major) Tj
        (D    Gm    Dsus4    D    Am    C    G    D) Tj
        (Am    C    Cmaj7    C    G    Dm    Am    C) Tj
        (Chords generated with Moises.ai) Tj
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chords.pdf"
            path.write_bytes(pdf_text)

            chart = extract_chords_from_moises_pdf(path)

        self.assertEqual(chart.key, "G major")
        self.assertEqual(chart.chords[:8], ["D", "Gm", "Dsus4", "D", "Am", "C", "G", "D"])
        self.assertEqual(chart.chords[-1], "C")

    def test_parse_key_and_chord_names(self):
        self.assertEqual(parse_key("G major"), {7, 9, 11, 0, 2, 4, 6})
        self.assertEqual(parse_chord_name("Dsus4"), [2, 7, 9])
        self.assertEqual(parse_chord_name("Am7"), [9, 0, 4, 7])
        self.assertEqual(parse_chord_name("Cmaj7"), [0, 4, 7, 11])

    def test_choose_voicing_keeps_chords_in_playable_range(self):
        first = choose_voicing([7, 11, 2], previous=None)
        second = choose_voicing([9, 0, 4], previous=first)

        self.assertTrue(all(48 <= note <= 76 for note in first + second))
        self.assertLessEqual(max(first) - min(first), 24)
        self.assertLessEqual(max(second) - min(second), 24)

    def test_make_chord_segments_can_snap_boundaries_to_beats(self):
        segments = make_chord_segments(["G", "D", "Am"], duration_seconds=4.0, bpm=150)

        self.assertEqual([round(segment.start / 0.4, 6) for segment in segments], [0.0, 3.0, 7.0])
        self.assertAlmostEqual(segments[-1].end, 4.0)


if __name__ == "__main__":
    unittest.main()
