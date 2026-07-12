from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

try:
    import mido

    MIDO_AVAILABLE = True
except ImportError:
    mido = None
    MIDO_AVAILABLE = False

from sunofriend.midi import pitch_bend_value
from sunofriend.midi_anchor import (
    anchor_midi_bytes,
    anchor_midi_file,
    anchor_midi_path,
)


PPQ = 480


def _varlen(value: int) -> bytes:
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


def _midi(*tracks: bytes) -> bytes:
    return (
        b"MThd"
        + struct.pack(">IHHH", 6, 1, len(tracks), PPQ)
        + b"".join(tracks)
    )


def _tempo(bpm: float) -> bytes:
    micros = int(round(60_000_000 / bpm))
    return _meta(0x51, micros.to_bytes(3, "big"))


def _fixture() -> bytes:
    conductor = _track(
        _event(0, _meta(0x03, b"Conductor")),
        _event(0, _meta(0x58, bytes((4, 2, 24, 8)))),
        _event(0, _meta(0x59, bytes((0, 0)))),
        _event(0, _tempo(120.0)),
        # A marker at zero is a musical location, not conductor setup.
        _event(0, _meta(0x06, b"Pickup")),
        _event(480, _meta(0x06, b"Verse")),
    )

    bend = pitch_bend_value(3.930158, 2)
    melody = _track(
        _event(0, _meta(0x03, b"Melody")),
        _event(0, bytes((0xC2, 73))),
        # Exact Sunofriend source-tuning initialization: it stays at zero.
        _event(0, bytes((0xB2, 101, 0))),
        _event(0, bytes((0xB2, 100, 0))),
        _event(0, bytes((0xB2, 6, 2))),
        _event(0, bytes((0xB2, 38, 0))),
        _event(0, bytes((0xB2, 101, 127))),
        _event(0, bytes((0xB2, 100, 127))),
        _event(0, bytes((0xE2, bend & 0x7F, bend >> 7))),
        # Ordinary controller and note at zero are musical and must move.
        _event(0, bytes((0xB2, 7, 100))),
        _event(0, bytes((0x92, 60, 100))),
        _event(120, bytes((0xB2, 11, 90))),
        _event(120, bytes((0x92, 64, 88))),
        _event(240, bytes((0x82, 60, 64))),
        # Running-status note-off for pitch 64.
        _event(0, bytes((64, 0))),
    )
    drums = _track(
        _event(0, _meta(0x03, b"Drums")),
        _event(0, bytes((0x99, 36, 110))),
        _event(120, bytes((0x89, 36, 0))),
    )
    return _midi(conductor, melody, drums)


def _absolute_messages(data: bytes) -> list[tuple[int, mido.Message | mido.MetaMessage]]:
    midi = mido.MidiFile(file=__import__("io").BytesIO(data))
    result = []
    for track in midi.tracks:
        tick = 0
        for message in track:
            tick += message.time
            result.append((tick, message))
    return result


@unittest.skipUnless(MIDO_AVAILABLE, "mido is part of the optional MIDI stack")
class MidiAnchorByteTests(unittest.TestCase):
    def test_transform_then_anchor_preserves_setup_and_moves_tick_zero_music(self) -> None:
        anchored, change = anchor_midi_bytes(
            _fixture(),
            source_downbeat_seconds=1.0,
            source_bpm=120.0,
            target_bpm=125.0,
            target_downbeat_beat=4.0,
            semitones=2,
        )
        messages = _absolute_messages(anchored)

        self.assertEqual(change.source_downbeat_tick, 960)
        self.assertEqual(change.target_downbeat_tick, 1920)
        self.assertEqual(change.shift_ticks, 960)
        self.assertEqual(change.semitones, 2)
        self.assertFalse(change.concert_pitch_cleanup_requested)
        self.assertEqual(change.transform.note_events_transposed, 4)
        self.assertEqual(change.transform.drum_note_events_preserved, 2)

        tempos = [(tick, message.tempo) for tick, message in messages if message.type == "set_tempo"]
        self.assertEqual(tempos, [(0, round(60_000_000 / 125.0))])
        self.assertTrue(
            all(
                tick == 0
                for tick, message in messages
                if message.type in {"track_name", "time_signature", "key_signature", "program_change"}
            )
        )
        tuning_cc = [
            (tick, message.control, message.value)
            for tick, message in messages
            if message.type == "control_change" and message.control in {101, 100, 6, 38}
        ]
        self.assertEqual([tick for tick, _, _ in tuning_cc], [0] * 6)
        self.assertEqual(
            [(tick, message.pitch) for tick, message in messages if message.type == "pitchwheel"],
            [(0, pitch_bend_value(3.930158, 2) - 8192)],
        )

        # Unknown CC7 and musical marker at tick zero both move.
        self.assertIn(
            (960, 7, 100),
            [
                (tick, message.control, message.value)
                for tick, message in messages
                if message.type == "control_change"
            ],
        )
        markers = [(tick, message.text) for tick, message in messages if message.type == "marker"]
        self.assertEqual(markers, [(960, "Pickup"), (1440, "Verse")])
        self.assertIn(
            (1080, 11, 90),
            [
                (tick, message.control, message.value)
                for tick, message in messages
                if message.type == "control_change"
            ],
        )

        notes = [
            (tick, message.channel, message.note, message.velocity, message.type)
            for tick, message in messages
            if message.type in {"note_on", "note_off"}
        ]
        self.assertIn((960, 2, 62, 100, "note_on"), notes)
        self.assertIn((1200, 2, 66, 88, "note_on"), notes)
        self.assertIn((1440, 2, 62, 64, "note_off"), notes)
        self.assertIn((1440, 2, 66, 0, "note_off"), notes)
        # Drum pitch is not transposed, but its tick-zero hit is anchored.
        self.assertIn((960, 9, 36, 110, "note_on"), notes)
        self.assertIn((1080, 9, 36, 0, "note_off"), notes)

    def test_source_downbeat_seconds_are_inverted_through_tempo_map(self) -> None:
        source = _midi(
            _track(
                _event(0, _tempo(120.0)),
                # The first beat lasts 0.5 seconds; the second lasts 1 second.
                _event(PPQ, _tempo(60.0)),
            ),
            _track(
                _event(PPQ * 2, bytes((0x90, 60, 100))),
                _event(PPQ, bytes((0x80, 60, 0))),
            ),
        )

        anchored, change = anchor_midi_bytes(
            source,
            source_downbeat_seconds=1.5,
            source_bpm=120,
            target_bpm=120,
            target_downbeat_beat=4,
        )

        self.assertEqual(change.source_downbeat_tick, PPQ * 2)
        self.assertEqual(change.target_downbeat_tick, PPQ * 4)
        self.assertEqual(change.shift_ticks, PPQ * 2)
        self.assertIn(
            (PPQ * 4, 60),
            [
                (tick, message.note)
                for tick, message in _absolute_messages(anchored)
                if message.type == "note_on"
            ],
        )

    def test_concert_pitch_removes_tuning_setup_before_anchor(self) -> None:
        anchored, change = anchor_midi_bytes(
            _fixture(),
            source_downbeat_seconds=1.0,
            source_bpm=120,
            target_bpm=125,
            concert_pitch=True,
        )
        messages = _absolute_messages(anchored)

        self.assertTrue(change.concert_pitch_cleanup_requested)
        self.assertEqual(change.transform.tuning_setups_removed, 1)
        self.assertFalse(any(message.type == "pitchwheel" for _, message in messages))
        self.assertFalse(
            any(
                message.type == "control_change" and message.control in {101, 100, 6, 38}
                for _, message in messages
            )
        )
        self.assertIn(
            (960, 7),
            [
                (tick, message.control)
                for tick, message in messages
                if message.type == "control_change"
            ],
        )

    def test_negative_shift_rejects_tick_zero_musical_events(self) -> None:
        with self.assertRaisesRegex(ValueError, "before MIDI tick zero"):
            anchor_midi_bytes(
                _fixture(),
                source_downbeat_seconds=4.0,
                source_bpm=120,
                target_bpm=120,
                target_downbeat_beat=1,
            )

    def test_negative_shift_is_allowed_when_all_timed_events_remain_non_negative(
        self,
    ) -> None:
        source = _midi(
            _track(_event(0, _tempo(120.0))),
            _track(
                _event(0, _meta(0x03, b"Late melody")),
                _event(PPQ * 4, bytes((0x90, 60, 100))),
                _event(PPQ, bytes((0x80, 60, 0))),
            ),
        )

        anchored, change = anchor_midi_bytes(
            source,
            source_downbeat_seconds=2.0,
            source_bpm=120,
            target_bpm=120,
            target_downbeat_beat=2,
        )

        self.assertEqual(change.shift_ticks, -PPQ * 2)
        self.assertIn(
            (PPQ * 2, 60),
            [
                (tick, message.note)
                for tick, message in _absolute_messages(anchored)
                if message.type == "note_on"
            ],
        )
        self.assertIn(
            (0, "Late melody"),
            [
                (tick, message.name)
                for tick, message in _absolute_messages(anchored)
                if message.type == "track_name"
            ],
        )

    def test_no_shift_still_applies_midi_transform_without_reencoding(self) -> None:
        anchored, change = anchor_midi_bytes(
            _fixture(),
            source_downbeat_seconds=2.0,
            source_bpm=120,
            target_bpm=125,
            target_downbeat_beat=4,
            semitones=-1,
        )
        messages = _absolute_messages(anchored)

        self.assertEqual(change.shift_ticks, 0)
        self.assertEqual(change.shifted_events, 0)
        self.assertIn(
            (0, 59),
            [
                (tick, message.note)
                for tick, message in messages
                if message.type == "note_on" and message.channel == 2
            ],
        )
        self.assertEqual(
            [message.tempo for _, message in messages if message.type == "set_tempo"],
            [round(60_000_000 / 125)],
        )


class MidiAnchorPathTests(unittest.TestCase):
    def test_recursive_directory_preserves_paths_and_ignores_non_midi(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            nested = source / "variants"
            nested.mkdir(parents=True)
            (source / "arrangement.mid").write_bytes(_fixture())
            (nested / "melody.MIDI").write_bytes(_fixture())
            (source / "notes.txt").write_text("ignore", encoding="utf-8")
            output = root / "output"

            results = anchor_midi_path(
                source,
                output,
                source_downbeat_seconds=1.0,
                source_bpm=120,
                target_bpm=125,
            )

            self.assertEqual(len(results), 2)
            self.assertTrue((output / "arrangement.mid").is_file())
            self.assertTrue((output / "variants" / "melody.MIDI").is_file())
            self.assertFalse((output / "notes.txt").exists())
            self.assertEqual(results[0].change.shift_ticks, 960)

    def test_file_wrapper_is_atomic_and_reports_audit_fields(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mid"
            output = root / "output.mid"
            source.write_bytes(_fixture())

            result = anchor_midi_file(
                source,
                output,
                source_downbeat_seconds=1.0,
                source_bpm=120,
                target_bpm=125,
                semitones=3,
            )

            audit = result.to_dict()
            self.assertTrue(output.is_file())
            self.assertEqual(audit["source_downbeat_tick"], 960)
            self.assertEqual(audit["target_downbeat_tick"], 1920)
            self.assertEqual(audit["shift_ticks"], 960)
            self.assertEqual(audit["semitones"], 3)
            self.assertEqual(audit["input"], str(source))
            self.assertEqual(audit["output"], str(output))

    def test_batch_transform_failure_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            (source / "good.mid").write_bytes(_fixture())
            (source / "z-bad.mid").write_bytes(b"not MIDI")
            output = root / "output"

            with self.assertRaises(ValueError):
                anchor_midi_path(
                    source,
                    output,
                    source_downbeat_seconds=1,
                    source_bpm=120,
                    target_bpm=125,
                )

            self.assertFalse(output.exists())

    def test_existing_collision_is_preflighted_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            (source / "a.mid").write_bytes(_fixture())
            (source / "b.mid").write_bytes(_fixture())
            output = root / "output"
            output.mkdir()
            (output / "b.mid").write_bytes(b"existing")

            with self.assertRaisesRegex(ValueError, "output already exists"):
                anchor_midi_path(
                    source,
                    output,
                    source_downbeat_seconds=1,
                    source_bpm=120,
                    target_bpm=125,
                )

            self.assertFalse((output / "a.mid").exists())
            self.assertEqual((output / "b.mid").read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
