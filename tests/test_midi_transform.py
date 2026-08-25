from __future__ import annotations

import math
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.midi import pitch_bend_value
from sunofriend.midi_tempo import retime_midi_bytes
from sunofriend.midi_transform import (
    _parse_midi,
    transform_midi_bytes,
    transform_midi_file,
    transform_midi_path,
)


TICKS_PER_BEAT = 480


def _varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative MIDI delta")
    result = [value & 0x7F]
    value >>= 7
    while value:
        result.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(result)


def _event(delta: int, payload: bytes) -> bytes:
    return _varlen(delta) + payload


def _meta(kind: int, payload: bytes) -> bytes:
    return bytes((0xFF, kind)) + _varlen(len(payload)) + payload


def _track(*events: bytes) -> bytes:
    body = b"".join(events) + _event(0, _meta(0x2F, b""))
    return b"MTrk" + struct.pack(">I", len(body)) + body


def _midi(*tracks: bytes, midi_format: int = 1) -> bytes:
    return b"MThd" + struct.pack(">IHHH", 6, midi_format, len(tracks), TICKS_PER_BEAT) + b"".join(tracks)


def _tempo(bpm: float) -> bytes:
    micros = int(round(60_000_000 / bpm))
    return _meta(0x51, micros.to_bytes(3, "big"))


def _conductor(bpm: float = 113.0) -> bytes:
    return _track(
        _event(0, _meta(0x03, b"Conductor")),
        _event(0, _meta(0x58, bytes((4, 2, 24, 8)))),
        _event(0, _meta(0x59, bytes((1, 0)))),
        _event(0, _tempo(bpm)),
        _event(1_920, _meta(0x06, b"Verse")),
    )


def _multitrack_fixture(shift: int = 0, bpm: float = 113.0) -> bytes:
    drums = _track(
        _event(0, _meta(0x03, b"Drums")),
        _event(0, bytes((0xB9, 7, 100))),
        _event(120, bytes((0x99, 36, 110))),
        _event(120, bytes((0x89, 36, 64))),
    )
    # The second bass event uses running status and velocity zero as note-off.
    bass_pitch = 47 + shift
    bass = _track(
        _event(0, _meta(0x03, b"Bass")),
        _event(0, bytes((0xC0, 38))),
        _event(0, bytes((0xB0, 7, 101))),
        _event(0, bytes((0xE0, 0, 64))),
        _event(240, bytes((0x90, bass_pitch, 96))),
        _event(360, bytes((bass_pitch, 0))),
    )
    keys_pitch = 71 + shift
    keys = _track(
        _event(0, _meta(0x03, b"Keys")),
        _event(0, b"\xf0\x03\x7d\x01\xf7"),
        _event(0, bytes((0xC1, 4))),
        _event(480, bytes((0x91, keys_pitch, 88))),
        _event(480, bytes((0x81, keys_pitch, 45))),
    )
    return _midi(_conductor(bpm), drums, bass, keys)


def _tuned_fixture(*, include_setup: bool = True, later_bend: bool = False) -> bytes:
    events = [
        _event(0, _meta(0x03, b"Vocal melody")),
        _event(0, bytes((0xC2, 73))),
    ]
    if include_setup:
        status = 0xB2
        events.extend(
            [
                _event(0, bytes((status, 101, 0))),
                _event(0, bytes((status, 100, 0))),
                _event(0, bytes((status, 6, 2))),
                _event(0, bytes((status, 38, 0))),
                _event(0, bytes((status, 101, 127))),
                _event(0, bytes((status, 100, 127))),
            ]
        )
        bend = pitch_bend_value(3.930158, 2)
        events.append(_event(0, bytes((0xE2, bend & 0x7F, bend >> 7))))
    events.extend(
        [
            _event(480, bytes((0x92, 57, 100))),
            _event(480, bytes((0x82, 57, 64))),
        ]
    )
    if later_bend:
        events.append(_event(120, bytes((0xE2, 0, 64))))
    return _midi(_conductor(93), _track(*events))


class MidiTransformCodecAdapterTests(unittest.TestCase):
    def test_parser_projection_preserves_events_offsets_padding_and_trailing_bytes(self) -> None:
        body = b"".join(
            (
                _event(0, _meta(0x7F, b"\x01\x02")),
                _event(120, bytes((0x90, 60, 90))),
                _event(0, bytes((0xF8,))),
                _event(120, bytes((60, 0))),
                _event(0, bytes((0xF2, 1, 2))),
                _event(0, b"\xf0\x03\x7d\xf7\x01"),
                _event(0, _meta(0x2F, b"")),
            )
        )
        padding = b"\xde\xad\x00\x90\x3c"
        track_payload = body + padding
        track = b"MTrk" + struct.pack(">I", len(track_payload)) + track_payload
        source = (
            b"MThd"
            + struct.pack(">IHHH", 8, 1, 1, TICKS_PER_BEAT)
            + b"\xaa\xbb"
            + track
            + b"TAIL"
        )

        layout = _parse_midi(source)

        self.assertEqual((layout.midi_format, layout.ticks_per_beat), (1, 480))
        self.assertEqual(len(layout.tracks), 1)
        parsed_track = layout.tracks[0]
        self.assertEqual(parsed_track.header_offset, 16)
        self.assertEqual(parsed_track.data_offset, 24)
        self.assertEqual(parsed_track.length, len(track_payload))
        self.assertEqual(
            [event.category for event in parsed_track.events],
            ["meta", "channel", "system", "channel", "system", "sysex", "meta"],
        )
        meta, note_on, realtime, running_note, common, sysex, end = parsed_track.events
        self.assertEqual(meta.data, (0x7F,))
        self.assertEqual(meta.data_offsets, ())
        self.assertEqual((note_on.tick, running_note.tick), (120, 240))
        self.assertEqual(note_on.data, (60, 90))
        self.assertEqual(
            tuple(source[offset] for offset in note_on.data_offsets),
            note_on.data,
        )
        self.assertEqual(realtime.data, ())
        self.assertFalse(running_note.explicit_status)
        self.assertEqual(running_note.status, 0x90)
        self.assertEqual(common.data, (1, 2))
        self.assertEqual(len(common.data_offsets), 2)
        self.assertEqual(sysex.data, ())
        self.assertEqual(end.data, (0x2F,))
        self.assertEqual(source[end.raw_end : parsed_track.data_offset + parsed_track.length], padding)
        self.assertTrue(source.endswith(b"TAIL"))

    def test_transform_header_policy_and_error_precedence_remain_compatible(self) -> None:
        valid_track = _track(_event(0, bytes((0x90, 60, 90))))
        no_tracks = b"MThd" + struct.pack(">IHHH", 6, 1, 0, 0xE728)
        cases = (
            (
                _midi(valid_track, midi_format=2),
                "only Standard MIDI File format 0 and 1 are supported",
            ),
            (
                b"MThd" + struct.pack(">IHHH", 6, 2, 0, 0xE728),
                "only Standard MIDI File format 0 and 1 are supported",
            ),
            (no_tracks, "MIDI file contains no tracks"),
            (
                b"MThd" + struct.pack(">IHHH", 6, 1, 1, 0xE728) + valid_track,
                "SMPTE-time MIDI is not supported",
            ),
            (
                b"MThd" + struct.pack(">IHHH", 6, 1, 1, 0) + valid_track,
                "MIDI ticks per beat must be greater than zero",
            ),
        )
        for source, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError,
                message,
            ):
                _parse_midi(source)

    def test_transpose_only_retains_legacy_tempo_tolerance_but_retime_is_strict(self) -> None:
        for payload, message in (
            (b"\x07\xa1", "exactly three bytes"),
            (b"\x00\x00\x00", "cannot be zero"),
        ):
            source = _midi(
                _track(
                    _event(0, _meta(0x51, payload)),
                    _event(120, bytes((0x90, 60, 90))),
                    _event(120, bytes((60, 0))),
                )
            )
            layout = _parse_midi(source)
            note_events = [
                event
                for event in layout.tracks[0].events
                if event.category == "channel" and event.event_type in {0x80, 0x90}
            ]
            expected = bytearray(source)
            for event in note_events:
                expected[event.data_offsets[0]] += 1

            with self.subTest(payload=payload):
                transformed, _ = transform_midi_bytes(source, semitones=1)
                self.assertEqual(transformed, bytes(expected))
                with self.assertRaisesRegex(ValueError, message):
                    transform_midi_bytes(source, target_bpm=125)


class MidiTransformByteTests(unittest.TestCase):
    def test_transpose_patches_only_melodic_note_bytes_and_preserves_running_status(self) -> None:
        source = _multitrack_fixture()

        transformed, change = transform_midi_bytes(source, semitones=2)

        self.assertEqual(transformed, _multitrack_fixture(shift=2))
        self.assertEqual(change.semitones, 2)
        self.assertEqual(change.note_events_transposed, 4)
        self.assertEqual(change.drum_note_events_preserved, 2)
        self.assertIsNone(change.tempo_change)

    def test_noop_is_byte_identical(self) -> None:
        source = _multitrack_fixture()

        transformed, change = transform_midi_bytes(source)

        self.assertEqual(transformed, source)
        self.assertEqual(change.note_events_transposed, 0)
        self.assertEqual(change.tuning_setups_removed, 0)

    def test_out_of_range_transposition_rejects_instead_of_clipping(self) -> None:
        high = _track(
            _event(0, bytes((0x90, 127, 100))),
            _event(480, bytes((0x80, 127, 64))),
        )
        source = _midi(high, midi_format=0)

        with self.assertRaisesRegex(ValueError, "outside MIDI 0..127"):
            transform_midi_bytes(source, semitones=1)

    def test_tempo_and_transposition_compose_without_moving_ticks(self) -> None:
        source = _multitrack_fixture()
        shifted = _multitrack_fixture(shift=5)
        expected, _ = retime_midi_bytes(shifted, source_bpm=113, target_bpm=125)

        transformed, change = transform_midi_bytes(
            source,
            semitones=5,
            source_bpm=113,
            target_bpm=125,
        )

        self.assertEqual(transformed, expected)
        self.assertEqual(change.note_events_transposed, 4)
        self.assertIsNotNone(change.tempo_change)
        self.assertAlmostEqual(change.tempo_change.source_bpm, 113, places=3)
        self.assertAlmostEqual(change.tempo_change.target_bpm, 125)
        self.assertAlmostEqual(change.tempo_change.speed_ratio, 125 / 113)

    def test_concert_pitch_removes_only_complete_constant_tuning_setup(self) -> None:
        source = _tuned_fixture()

        transformed, change = transform_midi_bytes(source, concert_pitch=True)

        self.assertEqual(transformed, _tuned_fixture(include_setup=False))
        self.assertEqual(change.tuning_setups_removed, 1)
        self.assertEqual(change.tuning_events_removed, 7)
        removal = change.tuning_removals[0]
        self.assertEqual((removal.track_index, removal.channel, removal.tick), (1, 2, 0))
        # The 14-bit pitch wheel quantises the requested +3.930158 cents.
        self.assertAlmostEqual(removal.tuning_cents, 3.9302, delta=0.002)

    def test_concert_pitch_rejects_channel_with_later_expressive_bend(self) -> None:
        source = _tuned_fixture(later_bend=True)

        with self.assertRaisesRegex(ValueError, "expressive pitch bends"):
            transform_midi_bytes(source, concert_pitch=True)

    def test_validation_is_explicit(self) -> None:
        source = _multitrack_fixture()
        with self.subTest("source without target"), self.assertRaisesRegex(
            ValueError, "source_bpm requires target_bpm"
        ):
            transform_midi_bytes(source, source_bpm=113)
        for invalid in (True, 1.5, "2"):
            with self.subTest(semitones=invalid), self.assertRaisesRegex(
                ValueError, "semitones must be an integer"
            ):
                transform_midi_bytes(source, semitones=invalid)
        for invalid in (0, -1, math.nan, math.inf):
            with self.subTest(max_tuning_cents=invalid), self.assertRaises(ValueError):
                transform_midi_bytes(source, max_tuning_cents=invalid)


class MidiTransformPathTests(unittest.TestCase):
    def test_rejects_missing_and_unsupported_input_shapes_before_transform_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.mid"
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(missing, root / "output.mid", semitones=True)
            self.assertEqual(str(caught.exception), f"input does not exist: {missing}")

            text = root / "notes.txt"
            text.write_text("not MIDI", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(text, root / "output.mid")
            self.assertEqual(str(caught.exception), "file input must end in .mid or .midi")

            if hasattr(os, "mkfifo"):
                fifo = root / "input.mid"
                os.mkfifo(fifo)
                with self.assertRaises(ValueError) as caught:
                    transform_midi_path(fifo, root / "fifo-output.mid")
                self.assertEqual(
                    str(caught.exception),
                    f"input must be a MIDI file or directory: {fifo}",
                )

    def test_rejects_file_and_directory_output_shape_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_file = root / "source.MIDI"
            source_file.write_bytes(_multitrack_fixture())
            output_directory = root / "file-output"
            output_directory.mkdir()

            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source_file, output_directory)
            self.assertEqual(
                str(caught.exception),
                "a file input requires a MIDI file output path",
            )

            source_directory = root / "source-tree"
            source_directory.mkdir()
            (source_directory / "song.mid").write_bytes(_multitrack_fixture())
            output_file = root / "directory-output.mid"
            output_file.write_bytes(b"occupied")

            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source_directory, output_file)
            self.assertEqual(
                str(caught.exception),
                "a directory input requires a directory output path",
            )

    def test_directory_plan_rejects_nested_output_and_empty_midi_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()

            nested_output = source / "generated"
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, nested_output)
            self.assertEqual(
                str(caught.exception),
                "output directory must not be the input directory or inside it",
            )

            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, root / "outside")
            self.assertEqual(
                str(caught.exception),
                f"no .mid or .midi files found under: {source}",
            )

    def test_output_preflight_rejects_same_path_symlinks_and_invalid_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            source.write_bytes(_multitrack_fixture())

            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, source, overwrite=True)
            self.assertEqual(
                str(caught.exception),
                f"input and output must be different: {source}",
            )

            symlink_target = root / "symlink-target.mid"
            symlink_target.write_bytes(b"untouched")
            symlink_output = root / "symlink-output.mid"
            symlink_output.symlink_to(symlink_target)
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, symlink_output, overwrite=True)
            self.assertEqual(
                str(caught.exception),
                f"output must not be a symbolic link: {symlink_output}",
            )
            self.assertEqual(symlink_target.read_bytes(), b"untouched")

            real_parent = root / "real-parent"
            real_parent.mkdir()
            symlink_parent = root / "symlink-parent"
            symlink_parent.symlink_to(real_parent, target_is_directory=True)
            child_output = symlink_parent / "child.mid"
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, child_output)
            self.assertEqual(
                str(caught.exception),
                f"output parent must not be a symbolic link: {symlink_parent}",
            )

            file_parent = root / "not-a-directory"
            file_parent.write_text("occupied", encoding="utf-8")
            invalid_child = file_parent / "child.mid"
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, invalid_child)
            self.assertEqual(
                str(caught.exception),
                f"output parent is not a directory: {file_parent}",
            )

    def test_batch_preflight_rejects_existing_directory_and_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "first.mid").write_bytes(_multitrack_fixture())
            (source / "second.mid").write_bytes(_multitrack_fixture())
            output = root / "output"
            output.mkdir()
            (output / "first.mid").mkdir()

            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, output)
            self.assertEqual(
                str(caught.exception),
                f"output MIDI path is a directory: {output / 'first.mid'}",
            )

            (output / "first.mid").rmdir()
            occupied = output / "second.mid"
            occupied.write_bytes(b"untouched")
            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, output)
            self.assertEqual(
                str(caught.exception),
                f"output already exists: {occupied}",
            )
            self.assertEqual(occupied.read_bytes(), b"untouched")
            self.assertFalse((output / "first.mid").exists())

    def test_duplicate_resolved_outputs_are_rejected_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "first.mid").write_bytes(_multitrack_fixture())
            (source / "second.mid").write_bytes(_multitrack_fixture())
            output = root / "output"
            canonical = root / "canonical.mid"
            real_resolve = Path.resolve

            def resolve_with_collision(path: Path, *args, **kwargs) -> Path:
                if path.parent == output and path.suffix.lower() in {".mid", ".midi"}:
                    return canonical
                return real_resolve(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolve_with_collision):
                with self.assertRaises(ValueError) as caught:
                    transform_midi_path(source, output)

            self.assertEqual(
                str(caught.exception),
                f"multiple inputs resolve to the same output: {output / 'second.mid'}",
            )
            self.assertFalse(output.exists())

    def test_all_output_collisions_are_checked_before_decoding_any_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "a-invalid.mid").write_bytes(b"not MIDI")
            (source / "z-valid.mid").write_bytes(_multitrack_fixture())
            output = root / "output"
            output.mkdir()
            occupied = output / "z-valid.mid"
            occupied.write_bytes(b"untouched")

            with self.assertRaises(ValueError) as caught:
                transform_midi_path(source, output)

            self.assertEqual(
                str(caught.exception),
                f"output already exists: {occupied}",
            )
            self.assertEqual(occupied.read_bytes(), b"untouched")
            self.assertFalse((output / "a-invalid.mid").exists())

    def test_directory_results_are_casefold_sorted_and_overwrite_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            (source / "nested").mkdir(parents=True)
            for relative in ("z.mid", "A.MIDI", "nested/b.mid"):
                (source / relative).write_bytes(_multitrack_fixture())
            output = root / "output"
            output.mkdir()
            existing = output / "z.mid"
            existing.write_bytes(b"replace me")

            results = transform_midi_path(source, output, semitones=1, overwrite=True)

            self.assertEqual(
                [result.input_path.relative_to(source).as_posix() for result in results],
                ["A.MIDI", "nested/b.mid", "z.mid"],
            )
            self.assertEqual(
                [result.output_path.relative_to(output).as_posix() for result in results],
                ["A.MIDI", "nested/b.mid", "z.mid"],
            )
            self.assertEqual(existing.read_bytes(), _multitrack_fixture(shift=1))
            self.assertFalse(any(path.name.endswith(".tmp") for path in output.rglob("*")))

    def test_recursive_batch_preserves_paths_and_ignores_non_midi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            nested = source / "variants" / "bass"
            nested.mkdir(parents=True)
            (source / "arrangement.mid").write_bytes(_multitrack_fixture())
            (nested / "part.MIDI").write_bytes(_multitrack_fixture())
            (source / "notes.txt").write_text("do not copy", encoding="utf-8")
            output = root / "output"

            results = transform_midi_path(
                source,
                output,
                semitones=-2,
                source_bpm=113,
                target_bpm=125,
            )

            expected_shifted = _multitrack_fixture(shift=-2)
            expected, _ = retime_midi_bytes(
                expected_shifted,
                source_bpm=113,
                target_bpm=125,
            )
            self.assertEqual(len(results), 2)
            self.assertEqual((output / "arrangement.mid").read_bytes(), expected)
            self.assertEqual((output / "variants" / "bass" / "part.MIDI").read_bytes(), expected)
            self.assertFalse((output / "notes.txt").exists())

    def test_file_wrapper_is_atomic_and_reports_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            # The path facade deliberately does not impose an output suffix.
            output = root / "requested-output.bin"
            source.write_bytes(_multitrack_fixture())

            result = transform_midi_file(source, output, semitones=1)

            self.assertEqual(result.input_path, source)
            self.assertEqual(result.output_path, output)
            self.assertEqual(output.read_bytes(), _multitrack_fixture(shift=1))
            report = result.to_dict()
            self.assertEqual(
                set(report),
                {
                    "semitones",
                    "note_events_transposed",
                    "drum_note_events_preserved",
                    "tempo_change",
                    "tuning_removals",
                    "midi_format",
                    "ticks_per_beat",
                    "track_count",
                    "tuning_setups_removed",
                    "tuning_events_removed",
                    "input",
                    "output",
                },
            )
            self.assertEqual(report["semitones"], 1)
            self.assertEqual(report["input"], str(source))
            self.assertEqual(report["output"], str(output))

    def test_batch_preflights_every_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "good.mid").write_bytes(_multitrack_fixture())
            high = _track(
                _event(0, bytes((0x90, 127, 100))),
                _event(480, bytes((0x80, 127, 64))),
            )
            (source / "z-bad.mid").write_bytes(_midi(high, midi_format=0))
            output = root / "output"

            with self.assertRaises(ValueError):
                transform_midi_path(source, output, semitones=1)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
