from __future__ import annotations

import struct
import unittest

from sunofriend.midi_codec import (
    MidiEdit,
    _inspect_midi_header_structure,
    _parse_midi_structure,
    inspect_midi_header,
    parse_midi,
    rewrite_midi,
)
from sunofriend.midi_tempo import retime_midi_bytes


def _varlen(value: int) -> bytes:
    encoded = [value & 0x7F]
    value >>= 7
    while value:
        encoded.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(encoded)


def _event(delta: int, payload: bytes) -> bytes:
    return _varlen(delta) + payload


def _meta(kind: int, payload: bytes) -> bytes:
    return bytes((0xFF, kind)) + _varlen(len(payload)) + payload


def _track(body: bytes, *, padding: bytes = b"") -> bytes:
    payload = body + _event(0, _meta(0x2F, b"")) + padding
    return b"MTrk" + struct.pack(">I", len(payload)) + payload


def _midi(
    *tracks: bytes,
    midi_format: int = 1,
    division: int = 480,
    header_extension: bytes = b"",
    trailing: bytes = b"",
) -> bytes:
    header_length = 6 + len(header_extension)
    header = b"MThd" + struct.pack(">IHHH", header_length, midi_format, len(tracks), division)
    return header + header_extension + b"".join(tracks) + trailing


def _lossless_fixture() -> bytes:
    body = b"".join(
        (
            _event(0, _meta(0x7F, b"\x01\x02")),
            _event(0, bytes((0xB9, 7, 100))),
            _event(0, bytes((0xE9, 0, 64))),
            _event(0, bytes((0xF8,))),
            _event(0, bytes((1, 64))),
            _event(0, b"\xf0\x03\x7d\xf7\x01"),
            _event(0, bytes((0x99, 36, 110))),
            _event(128, bytes((36, 0))),
        )
    )
    return _midi(
        _track(body, padding=b"\xde\xad"),
        header_extension=b"\xaa\xbb",
        trailing=b"TAIL",
    )


class MidiCodecInspectionTests(unittest.TestCase):
    def test_private_header_structure_leaves_policy_to_compatibility_callers(self) -> None:
        source = b"MThd" + struct.pack(">IHHH", 6, 3, 0, 0)

        header = _inspect_midi_header_structure(source)

        self.assertEqual(
            (header.midi_format, header.track_count, header.division),
            (3, 0, 0),
        )
        with self.assertRaisesRegex(ValueError, "format 0, 1 and 2"):
            inspect_midi_header(source)
        with self.assertRaisesRegex(ValueError, "format 0, 1 and 2"):
            parse_midi(source)
        no_tracks_smpte = b"MThd" + struct.pack(">IHHH", 6, 1, 0, 0xE728)
        with self.assertRaisesRegex(ValueError, "MIDI file contains no tracks"):
            retime_midi_bytes(no_tracks_smpte, target_bpm=125)

    def test_inspection_retains_extended_header_padding_trailing_and_event_spans(self) -> None:
        source = _lossless_fixture()

        document = parse_midi(source)

        self.assertEqual(document.source, source)
        self.assertEqual(len(document.source_sha256), 64)
        self.assertEqual(document.header_length, 8)
        self.assertEqual(document.midi_format, 1)
        self.assertEqual(document.division, 480)
        self.assertEqual(document.trailing_offset, len(source) - len(b"TAIL"))
        self.assertEqual(source[document.trailing_offset :], b"TAIL")
        self.assertEqual(len(document.tracks), 1)
        track = document.tracks[0]
        self.assertEqual(source[track.data_end - 2 : track.data_end], b"\xde\xad")
        self.assertEqual(
            [event.category for event in track.events],
            [
                "meta",
                "channel",
                "channel",
                "system",
                "channel",
                "sysex",
                "channel",
                "channel",
                "meta",
            ],
        )
        self.assertEqual(track.events[0].meta_type, 0x7F)
        self.assertEqual(source[track.events[0].data_start : track.events[0].data_end], b"\x01\x02")
        self.assertFalse(track.events[4].explicit_status)
        self.assertFalse(track.events[7].explicit_status)
        self.assertEqual(track.events[7].delta, 128)
        self.assertEqual(track.events[7].tick, 128)
        self.assertEqual(rewrite_midi(document, ()), source)

    def test_all_smf_formats_and_smpte_division_are_inspected_without_reencoding(self) -> None:
        source = _midi(
            _track(_event(0, bytes((0x90, 60, 90)))),
            midi_format=2,
            division=0xE728,
        )

        document = parse_midi(source)

        self.assertEqual(document.midi_format, 2)
        self.assertEqual(document.division, 0xE728)
        self.assertEqual(rewrite_midi(document, []), source)
        with self.assertRaisesRegex(ValueError, "format 0 and 1"):
            retime_midi_bytes(source, target_bpm=125)

        smpte_format_one = _midi(
            _track(_event(0, bytes((0x90, 60, 90)))),
            division=0xE728,
        )
        with self.assertRaisesRegex(ValueError, "SMPTE-time MIDI"):
            retime_midi_bytes(smpte_format_one, target_bpm=125)

        invalid_tempo = _track(_event(0, _meta(0x51, b"\x07\xa1")))
        with self.assertRaisesRegex(ValueError, "format 0 and 1"):
            retime_midi_bytes(_midi(invalid_tempo, midi_format=2), target_bpm=125)
        with self.assertRaisesRegex(ValueError, "SMPTE-time MIDI"):
            retime_midi_bytes(
                _midi(invalid_tempo, division=0xE728),
                target_bpm=125,
            )

    def test_structural_and_event_failures_remain_fail_closed(self) -> None:
        valid_track = _track(_event(0, bytes((0x90, 60, 90))))
        cases = {
            "signature": b"not MIDI",
            "short header": b"MThd\x00\x00\x00\x06",
            "short extension": b"MThd" + struct.pack(">IHHH", 8, 1, 1, 480),
            "format three": _midi(valid_track, midi_format=3),
            "no tracks": b"MThd" + struct.pack(">IHHH", 6, 1, 0, 480),
            "zero division": _midi(valid_track, division=0),
            "missing track": b"MThd" + struct.pack(">IHHH", 6, 1, 1, 480),
            "truncated track": (
                b"MThd"
                + struct.pack(">IHHH", 6, 1, 1, 480)
                + b"MTrk"
                + struct.pack(">I", 3)
                + b"\x00"
            ),
            "running status first": _midi(_track(_event(0, bytes((60, 90))))),
            "truncated delta": _midi(b"MTrk" + struct.pack(">I", 1) + b"\x81"),
            "long delta": _midi(b"MTrk" + struct.pack(">I", 5) + b"\x81\x80\x80\x80\x00"),
            "truncated meta": _midi(b"MTrk" + struct.pack(">I", 2) + b"\x00\xff"),
            "truncated meta payload": _midi(
                b"MTrk" + struct.pack(">I", 4) + b"\x00\xff\x01\x02"
            ),
            "truncated sysex": _midi(
                b"MTrk" + struct.pack(">I", 3) + b"\x00\xf0\x02"
            ),
            "unsupported system": _midi(
                b"MTrk" + struct.pack(">I", 2) + b"\x00\xf4"
            ),
            "truncated system": _midi(
                b"MTrk" + struct.pack(">I", 2) + b"\x00\xf2"
            ),
            "truncated channel": _midi(
                b"MTrk" + struct.pack(">I", 3) + b"\x00\x90\x3c"
            ),
            "invalid channel data": _midi(
                b"MTrk" + struct.pack(">I", 4) + b"\x00\x90\x80\x00"
            ),
        }
        for label, source in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                parse_midi(source)

    def test_invalid_tempo_precedes_a_later_malformed_event(self) -> None:
        body = _event(0, _meta(0x51, b"\x07\xa1")) + b"\x00\x90"
        source = _midi(b"MTrk" + struct.pack(">I", len(body)) + body)

        with self.assertRaisesRegex(
            ValueError,
            "Set Tempo meta event must contain exactly three bytes",
        ):
            parse_midi(source)

    def test_tempo_validation_can_be_deferred_to_a_compatibility_adapter(self) -> None:
        for payload in (b"\x07\xa1", b"\x00\x00\x00"):
            source = _midi(_track(_event(0, _meta(0x51, payload))))
            with self.subTest(payload=payload):
                document = _parse_midi_structure(source)
                tempo = document.tracks[0].events[0]
                self.assertEqual(tempo.meta_type, 0x51)
                self.assertEqual(
                    source[tempo.data_start : tempo.data_end],
                    payload,
                )
                with self.assertRaises(ValueError):
                    parse_midi(source)


class MidiCodecRewriteTests(unittest.TestCase):
    def test_replacement_changes_only_the_selected_payload(self) -> None:
        source = _midi(
            _track(_event(0, _meta(0x51, b"\x07\xa1\x20"))),
            header_extension=b"\xaa\xbb",
            trailing=b"TAIL",
        )
        document = parse_midi(source)
        tempo = next(event for event in document.tracks[0].events if event.meta_type == 0x51)

        output = rewrite_midi(
            document,
            (
                MidiEdit.replace_event_data(document, tempo, b"\x07\x53\x00"),
            ),
        )

        self.assertEqual(
            output,
            source[: tempo.data_start] + b"\x07\x53\x00" + source[tempo.data_end :],
        )

    def test_insertions_repair_each_affected_track_length_once(self) -> None:
        first = _track(_event(0, _meta(0x03, b"Conductor")), padding=b"\xaa")
        second = _track(_event(0, bytes((0x90, 60, 90))), padding=b"\xbb")
        source = _midi(first, second, header_extension=b"\x11\x22", trailing=b"TAIL")
        document = parse_midi(source)
        first_insert = b"\x00\xff\x51\x03\x07\xa1\x20"
        second_insert = b"\x00\xc0\x05"

        output = rewrite_midi(
            document,
            (
                MidiEdit.insert_track_event(document, document.tracks[0], first_insert),
                MidiEdit.insert_track_event(document, document.tracks[1], second_insert),
            ),
        )

        rewritten = parse_midi(output)
        self.assertEqual(rewritten.tracks[0].length, document.tracks[0].length + len(first_insert))
        self.assertEqual(rewritten.tracks[1].length, document.tracks[1].length + len(second_insert))
        self.assertEqual(output[14:16], b"\x11\x22")
        self.assertTrue(output.endswith(b"TAIL"))
        self.assertIn(b"\xaa", output)
        self.assertIn(b"\xbbTAIL", output)
        self.assertEqual(rewritten.tracks[0].events[0].meta_type, 0x51)
        self.assertEqual(rewritten.tracks[1].events[0].status, 0xC0)

    def test_rewrites_reject_invalid_tracks_escaping_spans_and_ambiguity(self) -> None:
        source = _midi(_track(_event(0, bytes((0x90, 60, 90)))))
        document = parse_midi(source)
        track = document.tracks[0]
        event = track.events[0]
        cases = (
            (
                MidiEdit(
                    1,
                    track.data_offset,
                    track.data_offset,
                    b"\x00\xf8",
                    document.source_sha256,
                    "track_event",
                ),
            ),
            (
                MidiEdit(
                    0,
                    track.header_offset,
                    track.data_offset,
                    b"x",
                    document.source_sha256,
                    "event_data",
                ),
            ),
            (
                MidiEdit.replace_event_data(document, event, b"\x3c\x5a"),
                MidiEdit.replace_event_data(document, event, b"\x3d\x5b"),
            ),
            (
                MidiEdit(
                    0,
                    event.data_start,
                    event.data_end,
                    b"x",
                    document.source_sha256,
                    "event_data",
                ),
            ),
            (
                MidiEdit(
                    0,
                    event.data_start,
                    event.data_end,
                    b"xx",
                    document.source_sha256,
                    "unknown",
                ),
            ),
        )
        for edits in cases:
            with self.subTest(edits), self.assertRaises(ValueError):
                rewrite_midi(document, edits)
        with self.assertRaisesRegex(ValueError, "preserve byte length"):
            MidiEdit.replace_event_data(document, event, b"x")
        with self.assertRaisesRegex(ValueError, "seven-bit"):
            MidiEdit.replace_event_data(document, event, b"\x80\x00")
        invalid_insertions = (
            b"",
            b"\x00\x3c\x40",
            b"\x00\xff\x2f\x00",
            b"\x00\xf8\x00\xf8",
            b"\x01\xc0\x05",
        )
        for encoded in invalid_insertions:
            with self.subTest(encoded), self.assertRaises(ValueError):
                MidiEdit.insert_track_event(document, track, encoded)
        with self.assertRaises(TypeError):
            rewrite_midi(document, (object(),))  # type: ignore[arg-type]

    def test_edits_cannot_be_replayed_against_a_different_source(self) -> None:
        first = parse_midi(_midi(_track(_event(0, bytes((0x90, 60, 90))))))
        second = parse_midi(_midi(_track(_event(0, bytes((0x90, 61, 91))))))
        with self.assertRaisesRegex(ValueError, "different source document"):
            MidiEdit.replace_event_data(
                second,
                first.tracks[0].events[0],
                b"\x3e\x5c",
            )
        with self.assertRaisesRegex(ValueError, "different source document"):
            MidiEdit.insert_track_event(
                second,
                first.tracks[0],
                b"\x00\xc0\x05",
            )
        edit = MidiEdit.replace_event_data(
            first,
            first.tracks[0].events[0],
            b"\x3e\x5c",
        )

        with self.assertRaisesRegex(ValueError, "different source document"):
            rewrite_midi(second, (edit,))

    def test_tempo_replacement_cannot_encode_zero(self) -> None:
        document = parse_midi(
            _midi(_track(_event(0, _meta(0x51, b"\x07\xa1\x20"))))
        )
        tempo = next(
            event for event in document.tracks[0].events if event.meta_type == 0x51
        )

        with self.assertRaisesRegex(ValueError, "cannot be zero"):
            MidiEdit.replace_event_data(document, tempo, b"\x00\x00\x00")


class MidiTempoCodecMigrationTests(unittest.TestCase):
    def test_tempo_rewrite_preserves_header_padding_trailing_and_other_track_bytes(self) -> None:
        conductor = _track(_event(0, _meta(0x03, b"Conductor")), padding=b"\xaa\xbb")
        notes = _track(
            b"".join(
                (
                    _event(240, _meta(0x51, b"\x0a\x2c\x2b")),
                    _event(0, bytes((0x99, 36, 110))),
                    _event(120, bytes((36, 0))),
                )
            ),
            padding=b"\xcc",
        )
        source = _midi(
            conductor,
            notes,
            header_extension=b"\x11\x22",
            trailing=b"TAIL",
        )

        output, change = retime_midi_bytes(source, target_bpm=125)

        before = parse_midi(source)
        after = parse_midi(output)
        self.assertTrue(change.tempo_event_inserted)
        self.assertEqual(change.tempo_events_changed, 1)
        self.assertEqual(after.header_length, before.header_length)
        self.assertEqual(after.tracks[0].length, before.tracks[0].length + 7)
        self.assertEqual(after.tracks[1].length, before.tracks[1].length)
        self.assertEqual(output[14:16], b"\x11\x22")
        self.assertTrue(output.endswith(b"TAIL"))
        self.assertIn(b"\xaa\xbb", output)
        self.assertIn(b"\xccTAIL", output)
        tempo_payloads = [
            output[event.data_start : event.data_end]
            for track in after.tracks
            for event in track.events
            if event.meta_type == 0x51
        ]
        self.assertEqual(tempo_payloads, [b"\x07\x53\x00", b"\x09\xc4\x00"])


if __name__ == "__main__":
    unittest.main()
