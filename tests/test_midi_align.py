from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend.cli import main
from sunofriend.beatgrid import Grid
from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.midi_align import align_midi_path
from sunofriend.models import NoteEvent

try:
    import numpy  # noqa: F401

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


class _FakeWarpedGrid:
    bpm = 59.5
    beats_per_bar = 4
    is_warped = True

    @staticmethod
    def beat_of(seconds: float) -> float:
        # The detected downbeat is at source second 0.5.
        return float(seconds) - 0.5


class _ThreeFourGrid(_FakeWarpedGrid):
    beats_per_bar = 3


class MidiAlignTests(unittest.TestCase):
    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is part of the optional audio stack")
    def test_irregular_warp_maps_note_boundaries_non_linearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "aligned.mid"
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(1.0, 2.5, 60, 90)])],
                bpm=60,
            )
            align_midi_path(
                source,
                source_bpm=60,
                target_bpm=90,
                output_path=output,
                grid=Grid(
                    bpm=60,
                    beat_times=[0.5, 1.5, 3.5],
                    beats_per_bar=4,
                ),
            )
            note = read_midi_clips(output)[0].notes[0]

        self.assertAlmostEqual(note.start_beat, 4.5)
        self.assertAlmostEqual(note.duration_beats, 1.0)

    def test_cli_reports_grid_contract_and_garageband_tempo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            metronome = root / "metronome.wav"
            output = root / "aligned.mid"
            metronome.write_bytes(b"test fixture")
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            stdout = io.StringIO()
            with (
                patch(
                    "sunofriend.midi_align.grid_from_metronome",
                    return_value=_FakeWarpedGrid(),
                ),
                redirect_stdout(stdout),
            ):
                result = main(
                    [
                        "midi-align",
                        str(source),
                        "--metronome",
                        str(metronome),
                        "--source-bpm",
                        "60",
                        "--target-bpm",
                        "93",
                        "--semitones",
                        "-5",
                        "--out",
                        str(output),
                    ]
                )

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(report["operation"], "midi-align")
        self.assertEqual(report["set_garageband_tempo_to"], 93.0)
        self.assertEqual(report["semitones"], -5)
        self.assertTrue(report["note_only_rebuild"])
        self.assertEqual(report["assumes_receiver_a_hz"], 440.0)

    def test_aligns_tracks_transposes_melody_and_preserves_drums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "aligned.mid"
            write_midi_file(
                source,
                [
                    MidiTrack(
                        "Bass",
                        0,
                        38,
                        [NoteEvent(0.5, 1.5, 60, 100)],
                        pitch_bend_cents=-43.831,
                    ),
                    MidiTrack(
                        "Drums",
                        9,
                        0,
                        [NoteEvent(0.5, 0.6, 36, 110)],
                    ),
                ],
                bpm=60,
            )

            results = align_midi_path(
                source,
                source_bpm=60,
                target_bpm=120,
                semitones=-5,
                count_in_bars=1,
                output_path=output,
                grid=_FakeWarpedGrid(),
            )
            clips = read_midi_clips(output)
            output_bytes = output.read_bytes()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].change.note_count, 2)
        self.assertEqual(results[0].change.drum_notes_preserved, 1)
        self.assertTrue(results[0].change.note_only_rebuild)
        self.assertEqual(results[0].change.assumes_receiver_a_hz, 440.0)
        self.assertAlmostEqual(clips[0].bpm, 120.0, places=3)
        by_title = {clip.title: clip for clip in clips}
        self.assertEqual(by_title["Bass"].notes[0].pitch, 55)
        self.assertEqual(by_title["Drums"].notes[0].pitch, 36)
        self.assertAlmostEqual(by_title["Bass"].notes[0].start_beat, 4.0)
        self.assertAlmostEqual(by_title["Bass"].notes[0].end_beat, 5.0)
        self.assertEqual(by_title["Bass"].instrument.program, 38)
        # The A=429 source bend/RPN setup is deliberately absent in the
        # note-centric A=440 aligned copy.
        self.assertNotIn(b"\xe0\x00", output_bytes)

    def test_directory_alignment_preserves_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            nested = source / "variants"
            nested.mkdir(parents=True)
            for path in (source / "main.mid", nested / "alt.midi"):
                write_midi_file(
                    path,
                    [MidiTrack("Lead", 2, 80, [NoteEvent(0.5, 1.0, 72, 90)])],
                    bpm=60,
                )
            output = root / "output"

            results = align_midi_path(
                source,
                source_bpm=60,
                target_bpm=90,
                output_path=output,
                grid=_FakeWarpedGrid(),
            )

            self.assertEqual(len(results), 2)
            self.assertTrue((output / "main.mid").is_file())
            self.assertTrue((output / "variants" / "alt.midi").is_file())

    def test_source_downbeat_phase_places_pickup_before_bar_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "aligned.mid"
            write_midi_file(
                source,
                [
                    MidiTrack(
                        "Lead",
                        0,
                        0,
                        [
                            NoteEvent(0.5, 0.75, 60, 90),
                            NoteEvent(1.5, 1.75, 62, 90),
                        ],
                    )
                ],
                bpm=60,
            )

            result = align_midi_path(
                source,
                source_bpm=60,
                target_bpm=90,
                source_downbeat_beat=1,
                count_in_bars=1,
                output_path=output,
                grid=_FakeWarpedGrid(),
            )[0]
            notes = read_midi_clips(output)[0].notes

        self.assertEqual(result.change.source_downbeat_beat, 1)
        self.assertAlmostEqual(notes[0].start_beat, 3.0)
        self.assertAlmostEqual(notes[1].start_beat, 4.0)

    def test_rejects_pickup_before_zero_without_enough_count_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.0, 0.25, 60, 90)])],
                bpm=60,
            )

            with self.assertRaisesRegex(ValueError, "pickup note"):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    count_in_bars=0,
                    output_path=root / "aligned.mid",
                    grid=_FakeWarpedGrid(),
                )

    def test_rejects_embedded_source_tempo_mismatch_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "aligned.mid"
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=61,
            )

            with self.assertRaisesRegex(ValueError, "embedded source tempo"):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    output_path=output,
                    grid=_FakeWarpedGrid(),
                )
            self.assertFalse(output.exists())

    def test_directory_preflight_rejects_blocked_late_parent_before_midi_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            write_midi_file(
                source / "a" / "first.mid",
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            write_midi_file(
                source / "z" / "last.mid",
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 62, 90)])],
                bpm=60,
            )
            output.mkdir()
            (output / "z").write_text("blocked", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not a directory"):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    output_path=output,
                    grid=_FakeWarpedGrid(),
                )
            self.assertFalse((output / "a" / "first.mid").exists())

    def test_directory_stages_all_serialized_files_before_first_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            for name, pitch in (("a.mid", 60), ("b.mid", 62)):
                write_midi_file(
                    source / name,
                    [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, pitch, 90)])],
                    bpm=60,
                )
            real_writer = write_midi_file
            calls = 0

            def failing_second_write(path, tracks, bpm, ticks_per_beat=480):
                nonlocal calls
                calls += 1
                if calls == 2:
                    Path(path).write_bytes(b"partial temporary")
                    raise OSError("disk full")
                return real_writer(path, tracks, bpm, ticks_per_beat)

            with (
                patch(
                    "sunofriend.midi_align.write_midi_file",
                    side_effect=failing_second_write,
                ),
                self.assertRaisesRegex(OSError, "disk full"),
            ):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    output_path=output,
                    grid=_FakeWarpedGrid(),
                )
            self.assertFalse((output / "a.mid").exists())
            self.assertFalse((output / "b.mid").exists())
            self.assertEqual(list(output.rglob("*.tmp")), [])

    def test_directory_preflight_rejects_nested_output_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            outside = root / "outside"
            outside.mkdir()
            write_midi_file(
                source / "variants" / "part.mid",
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            output.mkdir()
            (output / "variants").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "escapes|symbolic link"):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    output_path=output,
                    grid=_FakeWarpedGrid(),
                )
            self.assertFalse((outside / "part.mid").exists())

    def test_rejects_non_four_four_until_writer_can_declare_other_meter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            with self.assertRaisesRegex(ValueError, "only 4 beats per bar"):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    beats_per_bar=3,
                    output_path=root / "aligned.mid",
                    grid=_FakeWarpedGrid(),
                )

    def test_only_channel_ten_is_exempt_from_transposition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "aligned.mid"
            write_midi_file(
                source,
                [
                    MidiTrack(
                        "Drums but melodic",
                        0,
                        0,
                        [NoteEvent(0.5, 1.0, 60, 90)],
                    )
                ],
                bpm=60,
            )
            align_midi_path(
                source,
                source_bpm=60,
                target_bpm=90,
                semitones=2,
                output_path=output,
                grid=_FakeWarpedGrid(),
            )

            self.assertEqual(read_midi_clips(output)[0].notes[0].pitch, 62)

    def test_rejects_target_tempo_outside_three_byte_midi_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            for target in (1.0, 1_000_000_000.0):
                output = root / f"aligned-{target}.mid"
                with self.subTest(target=target), self.assertRaisesRegex(
                    ValueError, "three-byte MIDI tempo"
                ):
                    align_midi_path(
                        source,
                        source_bpm=60,
                        target_bpm=target,
                        output_path=output,
                        grid=_FakeWarpedGrid(),
                    )
                self.assertFalse(output.exists())

    def test_current_directory_default_output_is_named_as_a_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            write_midi_file(
                source / "part.mid",
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            previous = Path.cwd()
            try:
                os.chdir(source)
                results = align_midi_path(
                    ".",
                    source_bpm=60,
                    target_bpm=90,
                    grid=_FakeWarpedGrid(),
                )
            finally:
                os.chdir(previous)

            self.assertEqual(len(results), 1)
            self.assertTrue((root / "source-bar-aligned-90bpm" / "part.mid").is_file())

    def test_supplied_grid_meter_must_match_four_four_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            write_midi_file(
                source,
                [MidiTrack("Lead", 0, 0, [NoteEvent(0.5, 1.0, 60, 90)])],
                bpm=60,
            )
            with self.assertRaisesRegex(ValueError, "grid meter"):
                align_midi_path(
                    source,
                    source_bpm=60,
                    target_bpm=90,
                    output_path=root / "aligned.mid",
                    grid=_ThreeFourGrid(),
                )


if __name__ == "__main__":
    unittest.main()
