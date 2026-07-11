import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.beatgrid import Grid
from sunofriend.clip import (
    ClipNote,
    Instrument,
    MidiClip,
    Provenance,
    TempoMap,
    TimeSignature,
    read_midi_clips,
    write_clip_midi,
)
from sunofriend.listen_all import _make_library_clip
from sunofriend.loop import refine_stem
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.note_safety import normalize_note_events


def _same_pitch_does_not_overlap(notes, pitch):
    voice = sorted(
        (note for note in notes if note.pitch == pitch),
        key=lambda note: note.source_start_seconds,
    )
    return all(
        earlier.source_end_seconds <= later.source_start_seconds
        for earlier, later in zip(voice, voice[1:])
    )


class NoteSafetyTests(unittest.TestCase):
    def test_seconds_normalization_preserves_onsets_and_distinct_pitch_polyphony(self):
        notes = [
            NoteEvent(0.0, 1.0, 60, 70),
            NoteEvent(0.25, 1.25, 64, 80),
            NoteEvent(0.5, 1.5, 60, 75),
            NoteEvent(0.5, 1.0, 60, 99),
        ]

        got = normalize_note_events(reversed(notes))

        self.assertEqual(
            got,
            [
                NoteEvent(0.0, 0.5, 60, 70),
                NoteEvent(0.25, 1.25, 64, 80),
                NoteEvent(0.5, 1.5, 60, 99),
            ],
        )

    def test_refine_stem_returns_and_writes_normalized_notes(self):
        seed = [
            NoteEvent(0.0, 1.0, 60, 70),
            NoteEvent(0.25, 1.25, 64, 80),
            NoteEvent(0.5, 1.5, 60, 75),
        ]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "sunofriend.loop._seed_pitched", return_value=seed
        ), patch("sunofriend.compare.extract_onsets", return_value=[]), patch(
            "sunofriend.compare.chroma_matrix", return_value=[]
        ), patch(
            "sunofriend.compare.analyze_pitched_reference", return_value=[]
        ):
            result = refine_stem(
                "unused.wav", "keys", 120, tmp, max_iterations=0
            )
            restored = read_midi_clips(result.midi_path)[0]

        self.assertEqual(result.notes[0], NoteEvent(0.0, 0.5, 60, 70))
        self.assertEqual(
            [(note.start, note.pitch) for note in result.notes],
            [(0.0, 60), (0.25, 64), (0.5, 60)],
        )
        self.assertTrue(_same_pitch_does_not_overlap(restored.notes, 60))

    def test_legacy_writer_normalizes_per_track_without_consuming_same_channel_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "overlap.mid"
            write_midi_file(
                output,
                [
                    MidiTrack(
                        "First",
                        channel=0,
                        program=0,
                        notes=[
                            NoteEvent(0.0, 1.0, 60, 70),
                            NoteEvent(0.25, 1.25, 64, 80),
                            NoteEvent(0.5001, 1.0, 60, 99),
                        ],
                    ),
                    MidiTrack(
                        "Second",
                        channel=0,
                        program=0,
                        notes=[NoteEvent(0.5, 1.5, 60, 75)],
                    ),
                ],
                bpm=120,
            )
            clips = read_midi_clips(output)

        self.assertEqual(len(clips), 2)
        first_c = sorted(
            (note for note in clips[0].notes if note.pitch == 60),
            key=lambda note: note.source_start_seconds,
        )
        second_c = [note for note in clips[1].notes if note.pitch == 60]
        self.assertEqual(len(first_c), 2)
        self.assertEqual(len(second_c), 1)
        self.assertAlmostEqual(first_c[0].source_start_seconds, 0.0, places=6)
        self.assertAlmostEqual(first_c[0].source_end_seconds, 0.5, places=6)
        self.assertAlmostEqual(first_c[1].source_start_seconds, 0.5, places=6)
        self.assertAlmostEqual(first_c[1].source_end_seconds, 1.0, places=6)
        self.assertEqual(first_c[1].velocity, 99)
        self.assertAlmostEqual(second_c[0].source_start_seconds, 0.5, places=6)
        self.assertAlmostEqual(second_c[0].source_end_seconds, 1.5, places=6)
        self.assertEqual(second_c[0].velocity, 75)
        e_note = next(note for note in clips[0].notes if note.pitch == 64)
        self.assertAlmostEqual(e_note.source_start_seconds, 0.25, places=6)
        self.assertAlmostEqual(e_note.source_end_seconds, 1.25, places=6)

    def test_clip_writer_guards_overlapping_stem_locked_clip(self):
        tempo_map = TempoMap.constant(120)
        clip = MidiClip(
            title="Overlapping keys",
            tempo_map=tempo_map,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 0, 0),
            notes=(
                ClipNote(0.0, 2.0, 60, 70, 0.0, 1.0),
                ClipNote(0.5, 2.0, 64, 80, 0.25, 1.25),
                ClipNote(1.0, 2.0, 60, 75, 0.5, 1.5),
                ClipNote(1.0, 1.0, 60, 99, 0.5, 1.0),
            ),
            provenance=Provenance(
                details={"timing_mode": "stem_locked", "garageband_bpm": 120}
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "clip.mid"
            write_clip_midi(output, clip)
            restored = read_midi_clips(output)[0]

        self.assertEqual([note.pitch for note in restored.notes], [60, 64, 60])
        self.assertTrue(_same_pitch_does_not_overlap(restored.notes, 60))
        c_notes = [note for note in restored.notes if note.pitch == 60]
        self.assertAlmostEqual(c_notes[0].source_end_seconds, 0.5, places=6)
        self.assertAlmostEqual(c_notes[1].source_end_seconds, 1.5, places=6)
        self.assertEqual(c_notes[1].velocity, 99)

    def test_listen_all_archive_matches_normalized_clip_export_durations(self):
        source_notes = [
            NoteEvent(0.0, 1.0, 60, 70),
            NoteEvent(0.25, 1.25, 64, 80),
            NoteEvent(0.5, 1.5, 60, 75),
            NoteEvent(0.5, 1.0, 60, 99),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stem = root / "keys.wav"
            midi = root / "keys.mid"
            stem.write_bytes(b"stem provenance only")
            midi.write_bytes(b"midi provenance only")
            clip = _make_library_clip(
                title="Pupsies keys",
                name="keys",
                kind="keys",
                stem=stem,
                midi=midi,
                notes=source_notes,
                score=0.9,
                key="B major",
                grid=Grid(bpm=120),
                daw_bpm=120,
            )
            exported = root / "exported.mid"
            write_clip_midi(exported, clip)
            restored = read_midi_clips(exported)[0]

        self.assertEqual(len(clip.notes), 3)
        self.assertTrue(_same_pitch_does_not_overlap(clip.notes, 60))
        self.assertTrue(_same_pitch_does_not_overlap(restored.notes, 60))
        expected = sorted(
            (note.source_end_seconds - note.source_start_seconds, note.pitch)
            for note in clip.notes
        )
        actual = sorted(
            (note.source_end_seconds - note.source_start_seconds, note.pitch)
            for note in restored.notes
        )
        tick_seconds = 60.0 / (120.0 * 480.0)
        for (expected_duration, expected_pitch), (actual_duration, actual_pitch) in zip(
            expected, actual
        ):
            self.assertEqual(actual_pitch, expected_pitch)
            self.assertAlmostEqual(actual_duration, expected_duration, delta=tick_seconds)


if __name__ == "__main__":
    unittest.main()
