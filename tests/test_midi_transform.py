from __future__ import annotations

import math
import struct
import tempfile
import unittest
from pathlib import Path

from sunofriend.midi import pitch_bend_value
from sunofriend.midi_tempo import retime_midi_bytes
from sunofriend.midi_transform import (
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
            output = root / "output.mid"
            source.write_bytes(_multitrack_fixture())

            result = transform_midi_file(source, output, semitones=1)

            self.assertEqual(result.input_path, source)
            self.assertEqual(result.output_path, output)
            self.assertEqual(output.read_bytes(), _multitrack_fixture(shift=1))
            self.assertEqual(result.to_dict()["semitones"], 1)

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
