from __future__ import annotations

import dataclasses
import io
import math
import os
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sunofriend.cli import main
from sunofriend.midi_tempo import retime_midi_bytes


TICKS_PER_BEAT = 480


def _varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("a MIDI delta cannot be negative")
    output = [value & 0x7F]
    value >>= 7
    while value:
        output.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(output)


def _event(delta: int, payload: bytes) -> bytes:
    return _varlen(delta) + payload


def _meta(kind: int, payload: bytes) -> bytes:
    return bytes((0xFF, kind)) + _varlen(len(payload)) + payload


def _tempo_payload(bpm: float) -> bytes:
    micros = int(round(60_000_000.0 / bpm))
    return _meta(0x51, micros.to_bytes(3, "big"))


def _track(*events: bytes) -> bytes:
    body = b"".join(events) + _event(0, _meta(0x2F, b""))
    return b"MTrk" + struct.pack(">I", len(body)) + body


def _midi(
    *tracks: bytes,
    midi_format: int = 1,
    division: int = TICKS_PER_BEAT,
) -> bytes:
    header = b"MThd" + struct.pack(">IHHH", 6, midi_format, len(tracks), division)
    return header + b"".join(tracks)


def _conductor_track(*, tempos: tuple[tuple[int, float], ...] = ((0, 113.0),)) -> bytes:
    events = [
        _event(0, _meta(0x03, b"Conductor")),
        _event(0, _meta(0x02, b"Sunofriend test")),
        _event(0, _meta(0x01, b"tempo preservation")),
        _event(0, _meta(0x58, bytes((4, 2, 24, 8)))),
        _event(0, _meta(0x59, bytes((5, 0)))),  # B major
        _event(0, _meta(0x7F, b"\x01\x02\x03")),
    ]
    previous_tick = 0
    for tick, bpm in tempos:
        events.append(_event(tick - previous_tick, _tempo_payload(bpm)))
        previous_tick = tick
    events.append(_event(480, _meta(0x06, b"B")))
    return _track(*events)


def _multitrack_fixture(*, tempos: tuple[tuple[int, float], ...] = ((0, 113.0),)) -> bytes:
    # The bass uses running status for its note-off-equivalent note-on event.
    # This catches implementations that unnecessarily decode and rewrite the
    # whole MIDI stream instead of changing the tempo payloads in place.
    drums = _track(
        _event(0, _meta(0x03, b"Drums")),
        _event(0, bytes((0xB9, 7, 100))),
        _event(0, bytes((0xA9, 36, 50))),
        _event(0, bytes((0xD9, 40))),
        _event(0, bytes((0x99, 36, 110))),
        _event(120, bytes((0x89, 36, 64))),
        _event(360, bytes((0x99, 38, 105))),
        _event(120, bytes((0x89, 38, 32))),
    )
    bass = _track(
        _event(0, _meta(0x03, b"Bass")),
        _event(0, bytes((0xB0, 0, 1))),
        _event(0, bytes((0xC0, 38))),
        _event(0, bytes((0xB0, 7, 101))),
        _event(0, bytes((0xB0, 64, 127))),
        _event(0, bytes((0xE0, 0, 64))),
        _event(240, bytes((0x90, 47, 96))),
        _event(360, bytes((47, 0))),  # running-status note-on with velocity zero
    )
    keys = _track(
        _event(0, _meta(0x03, b"Keys")),
        _event(0, _meta(0x06, b"Verse")),
        _event(0, _meta(0x05, b"la")),
        _event(0, b"\xf0\x03\x7d\x01\xf7"),  # non-commercial SysEx payload
        _event(0, bytes((0xC1, 4))),
        _event(480, bytes((0x91, 71, 88))),
        _event(480, bytes((0x81, 71, 45))),
    )
    return _midi(_conductor_track(tempos=tempos), drums, bass, keys)


def _no_tempo_fixture() -> bytes:
    conductor = _track(
        _event(0, _meta(0x03, b"Conductor")),
        _event(0, _meta(0x58, bytes((4, 2, 24, 8)))),
    )
    notes = _track(
        _event(0, _meta(0x03, b"Lead")),
        _event(0, bytes((0xC2, 80))),
        _event(480, bytes((0x92, 72, 100))),
        _event(480, bytes((0x82, 72, 64))),
    )
    return _midi(conductor, notes)


def _read_varlen(data: bytes | bytearray, position: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if position >= len(data):
            raise ValueError("truncated variable-length MIDI value")
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position
    raise ValueError("invalid variable-length MIDI value")


@dataclasses.dataclass(frozen=True)
class _ParsedEvent:
    track: int
    tick: int
    category: str
    status: int
    payload: bytes
    payload_start: int
    payload_end: int


def _parse_events(data: bytes) -> tuple[int, int, int, list[_ParsedEvent]]:
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File")
    header_length = struct.unpack(">I", data[4:8])[0]
    midi_format, track_count, division = struct.unpack(">HHH", data[8:14])
    position = 8 + header_length
    parsed: list[_ParsedEvent] = []
    for track_index in range(track_count):
        if data[position:position + 4] != b"MTrk":
            raise ValueError("missing track chunk")
        length = struct.unpack(">I", data[position + 4:position + 8])[0]
        cursor = position + 8
        track_end = cursor + length
        tick = 0
        running_status: int | None = None
        while cursor < track_end:
            delta, cursor = _read_varlen(data, cursor)
            tick += delta
            first = data[cursor]
            if first >= 0x80:
                cursor += 1
                status = first
                first_data: int | None = None
            else:
                if running_status is None:
                    raise ValueError("running status without a channel status")
                status = running_status
                first_data = first
                cursor += 1
            if status == 0xFF:
                running_status = None
                kind = data[cursor]
                cursor += 1
                size, cursor = _read_varlen(data, cursor)
                payload_start = cursor
                cursor += size
                parsed.append(
                    _ParsedEvent(
                        track_index,
                        tick,
                        "meta",
                        kind,
                        data[payload_start:cursor],
                        payload_start,
                        cursor,
                    )
                )
                continue
            if status in {0xF0, 0xF7}:
                running_status = None
                size, cursor = _read_varlen(data, cursor)
                payload_start = cursor
                cursor += size
                parsed.append(
                    _ParsedEvent(
                        track_index,
                        tick,
                        "sysex",
                        status,
                        data[payload_start:cursor],
                        payload_start,
                        cursor,
                    )
                )
                continue
            if status < 0x80 or status >= 0xF0:
                raise ValueError(f"unsupported status byte: {status:#x}")
            running_status = status
            size = 1 if status & 0xF0 in {0xC0, 0xD0} else 2
            payload_start = cursor - (1 if first_data is not None else 0)
            values = ([] if first_data is None else [first_data])
            remaining = size - len(values)
            values.extend(data[cursor:cursor + remaining])
            cursor += remaining
            parsed.append(
                _ParsedEvent(
                    track_index,
                    tick,
                    "channel",
                    status,
                    bytes(values),
                    payload_start,
                    cursor,
                )
            )
        if cursor != track_end:
            raise ValueError("event extends beyond its track")
        position = track_end
    if position != len(data):
        raise ValueError("unexpected data after final track")
    return midi_format, track_count, division, parsed


def _tempo_events(data: bytes) -> list[tuple[int, int, int]]:
    return [
        (event.track, event.tick, int.from_bytes(event.payload, "big"))
        for event in _parse_events(data)[3]
        if event.category == "meta" and event.status == 0x51
    ]


def _semantic_non_tempo_events(data: bytes) -> list[tuple[int, int, str, int, bytes]]:
    return [
        (event.track, event.tick, event.category, event.status, event.payload)
        for event in _parse_events(data)[3]
        if not (event.category == "meta" and event.status == 0x51)
    ]


def _mask_tempo_payloads(data: bytes) -> bytes:
    masked = bytearray(data)
    for event in _parse_events(data)[3]:
        if event.category == "meta" and event.status == 0x51:
            masked[event.payload_start:event.payload_end] = b"\x00" * len(event.payload)
    return bytes(masked)


def _assert_result_contract(
    test: unittest.TestCase,
    result: object,
    *,
    source_bpm: float,
    target_bpm: float,
) -> None:
    test.assertTrue(dataclasses.is_dataclass(result))
    # These values are the useful public result contract; additional reporting
    # fields are deliberately not prescribed by this test.
    test.assertAlmostEqual(getattr(result, "source_bpm"), source_bpm, places=3)
    test.assertAlmostEqual(getattr(result, "target_bpm"), target_bpm, places=6)
    test.assertAlmostEqual(getattr(result, "speed_ratio"), target_bpm / source_bpm, places=6)
    test.assertAlmostEqual(getattr(result, "duration_ratio"), source_bpm / target_bpm, places=6)


class MidiTempoByteTransformTests(unittest.TestCase):
    def test_113_to_125_changes_only_tempo_payload_and_reports_ratios(self) -> None:
        source = _multitrack_fixture()

        transformed, result = retime_midi_bytes(
            source,
            source_bpm=113,
            target_bpm=125,
        )

        self.assertEqual(_tempo_events(transformed), [(0, 0, 480_000)])
        self.assertEqual(_mask_tempo_payloads(transformed), _mask_tempo_payloads(source))
        self.assertEqual(_semantic_non_tempo_events(transformed), _semantic_non_tempo_events(source))
        _assert_result_contract(self, result, source_bpm=113, target_bpm=125)
        self.assertAlmostEqual(result.duration_ratio, 0.904, places=9)

    def test_source_bpm_is_inferred_from_tick_zero_tempo(self) -> None:
        source = _multitrack_fixture()

        transformed, result = retime_midi_bytes(source, target_bpm=125)

        self.assertEqual(_tempo_events(transformed), [(0, 0, 480_000)])
        self.assertAlmostEqual(result.source_bpm, 113, places=3)

    def test_slowdown_preserves_note_ticks_and_increases_elapsed_duration(self) -> None:
        source = _multitrack_fixture(tempos=((0, 125),))

        transformed, result = retime_midi_bytes(
            source,
            source_bpm=125,
            target_bpm=100,
        )

        self.assertEqual(_tempo_events(transformed), [(0, 0, 600_000)])
        self.assertEqual(_mask_tempo_payloads(transformed), _mask_tempo_payloads(source))
        self.assertAlmostEqual(result.speed_ratio, 0.8)
        self.assertAlmostEqual(result.duration_ratio, 1.25)

    def test_variable_tempo_map_is_scaled_at_unchanged_ticks(self) -> None:
        source = _multitrack_fixture(tempos=((0, 113), (1_920, 90)))

        transformed, result = retime_midi_bytes(
            source,
            source_bpm=113,
            target_bpm=125,
        )

        self.assertEqual(
            _tempo_events(transformed),
            [(0, 0, 480_000), (0, 1_920, 602_667)],
        )
        self.assertEqual(_mask_tempo_payloads(transformed), _mask_tempo_payloads(source))
        self.assertEqual(getattr(result, "tempo_events_changed"), 2)

    def test_multitrack_channels_programs_controllers_and_running_status_are_unchanged(self) -> None:
        source = _multitrack_fixture()
        before_format, before_tracks, before_division, before_events = _parse_events(source)

        transformed, _ = retime_midi_bytes(source, source_bpm=113, target_bpm=125)
        after_format, after_tracks, after_division, after_events = _parse_events(transformed)

        self.assertEqual((after_format, after_tracks, after_division), (1, 4, TICKS_PER_BEAT))
        self.assertEqual(
            [(event.track, event.tick, event.status, event.payload) for event in after_events if event.category == "channel"],
            [(event.track, event.tick, event.status, event.payload) for event in before_events if event.category == "channel"],
        )
        self.assertEqual(_mask_tempo_payloads(transformed), _mask_tempo_payloads(source))

    def test_format_zero_is_supported(self) -> None:
        combined = _track(
            _event(0, _tempo_payload(113)),
            _event(0, bytes((0xC0, 38))),
            _event(480, bytes((0x90, 47, 90))),
            _event(480, bytes((0x80, 47, 50))),
        )
        source = _midi(combined, midi_format=0)

        transformed, _ = retime_midi_bytes(source, source_bpm=113, target_bpm=125)

        self.assertEqual(_parse_events(transformed)[:3], (0, 1, TICKS_PER_BEAT))
        self.assertEqual(_tempo_events(transformed), [(0, 0, 480_000)])
        self.assertEqual(_mask_tempo_payloads(transformed), _mask_tempo_payloads(source))

    def test_no_tempo_uses_smf_default_or_explicit_daw_tempo_and_inserts_target(self) -> None:
        source = _no_tempo_fixture()

        inferred, default_result = retime_midi_bytes(source, target_bpm=125)
        self.assertEqual(_tempo_events(inferred), [(0, 0, 480_000)])
        _assert_result_contract(
            self,
            default_result,
            source_bpm=120,
            target_bpm=125,
        )

        transformed, result = retime_midi_bytes(
            source,
            source_bpm=113,
            target_bpm=125,
        )
        self.assertEqual(_tempo_events(transformed), [(0, 0, 480_000)])
        self.assertEqual(_semantic_non_tempo_events(transformed), _semantic_non_tempo_events(source))
        _assert_result_contract(self, result, source_bpm=113, target_bpm=125)

    def test_later_tempo_map_gets_target_at_zero_and_scales_from_smf_default(self) -> None:
        source = _multitrack_fixture(tempos=((1_920, 90),))

        transformed, result = retime_midi_bytes(source, target_bpm=125)

        self.assertEqual(
            _tempo_events(transformed),
            [(0, 0, 480_000), (0, 1_920, 640_000)],
        )
        self.assertAlmostEqual(result.source_bpm, 120)
        self.assertTrue(result.tempo_event_inserted)

    def test_explicit_source_must_match_embedded_tick_zero_tempo(self) -> None:
        with self.assertRaises(ValueError):
            retime_midi_bytes(
                _multitrack_fixture(),
                source_bpm=120,
                target_bpm=125,
            )

    def test_explicit_nominal_source_still_writes_the_exact_target_tempo(self) -> None:
        source = _multitrack_fixture(tempos=((0, 113.04),))

        transformed, result = retime_midi_bytes(
            source,
            source_bpm=113,
            target_bpm=125,
        )

        self.assertEqual(_tempo_events(transformed), [(0, 0, 480_000)])
        _assert_result_contract(self, result, source_bpm=113, target_bpm=125)

    def test_conflicting_tick_zero_tempos_are_rejected(self) -> None:
        source = _multitrack_fixture(tempos=((0, 113), (0, 120)))

        with self.assertRaises(ValueError):
            retime_midi_bytes(source, target_bpm=125)

        near_conflict = _multitrack_fixture(tempos=((0, 113), (0, 113.04)))
        with self.assertRaises(ValueError):
            retime_midi_bytes(near_conflict, target_bpm=125)

    def test_malformed_tempo_meta_event_is_rejected(self) -> None:
        conductor = _track(_event(0, _meta(0x51, b"\x07\xa1")))
        source = _midi(conductor)

        with self.assertRaises(ValueError):
            retime_midi_bytes(source, source_bpm=120, target_bpm=125)

    def test_smpte_division_and_format_two_are_rejected(self) -> None:
        with self.subTest("SMPTE division"):
            source = _midi(_conductor_track(), division=0xE728)
            with self.assertRaises(ValueError):
                retime_midi_bytes(source, source_bpm=113, target_bpm=125)
        with self.subTest("format two"):
            source = _midi(_conductor_track(), midi_format=2)
            with self.assertRaises(ValueError):
                retime_midi_bytes(source, source_bpm=113, target_bpm=125)

    def test_invalid_or_unrepresentable_target_bpm_is_rejected(self) -> None:
        source = _multitrack_fixture()
        for invalid in (0, -1, math.nan, math.inf, -math.inf, 1, 1_000_000_000):
            with self.subTest(target_bpm=invalid), self.assertRaises(ValueError):
                retime_midi_bytes(source, source_bpm=113, target_bpm=invalid)


class MidiTempoCliTests(unittest.TestCase):
    def _assert_cli_error(self, arguments: list[str]) -> tuple[str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(arguments)
        self.assertEqual(raised.exception.code, 2)
        return stdout.getvalue(), stderr.getvalue()

    def test_single_file_supports_long_and_short_bpm_option_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song.mid"
            first = root / "song-125bpm.mid"
            second = root / "song-100bpm.mid"
            source.write_bytes(_multitrack_fixture())

            with redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "midi-tempo",
                        str(source),
                        "--source-bpm",
                        "113",
                        "--target-bpm",
                        "125",
                        "--out",
                        str(first),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(_tempo_events(first.read_bytes()), [(0, 0, 480_000)])

            with redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "midi-tempo",
                        str(first),
                        "--from-bpm",
                        "125",
                        "--to-bpm",
                        "100",
                        "--out",
                        str(second),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(_tempo_events(second.read_bytes()), [(0, 0, 600_000)])

    def test_single_file_default_is_a_sibling_named_for_target_bpm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song-113bpm.mid"
            source.write_bytes(_multitrack_fixture())

            with redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "midi-tempo",
                        str(source),
                        "--source-bpm",
                        "113",
                        "--target-bpm",
                        "125",
                    ]
                )

            self.assertEqual(result, 0)
            output = root / "song-125bpm.mid"
            self.assertTrue(output.is_file())
            self.assertEqual(_tempo_events(output.read_bytes()), [(0, 0, 480_000)])

    def test_directory_batch_is_recursive_preserves_relative_paths_and_ignores_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song-113bpm"
            nested = source / "variants" / "bass"
            nested.mkdir(parents=True)
            (source / "arrangement.mid").write_bytes(_multitrack_fixture())
            (nested / "part.MIDI").write_bytes(_multitrack_fixture())
            (source / "notes.txt").write_text("do not copy", encoding="utf-8")
            output = root / "rendered"

            with redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "midi-tempo",
                        str(source),
                        "--source-bpm",
                        "113",
                        "--target-bpm",
                        "125",
                        "--out",
                        str(output),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(_tempo_events((output / "arrangement.mid").read_bytes()), [(0, 0, 480_000)])
            self.assertEqual(_tempo_events((output / "variants" / "bass" / "part.MIDI").read_bytes()), [(0, 0, 480_000)])
            self.assertFalse((output / "notes.txt").exists())

    def test_directory_default_is_a_sibling_named_for_target_bpm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song-113bpm"
            source.mkdir()
            (source / "bass.mid").write_bytes(_multitrack_fixture())

            with redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "midi-tempo",
                        str(source),
                        "--source-bpm",
                        "113",
                        "--target-bpm",
                        "125",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertTrue((root / "song-125bpm" / "bass.mid").is_file())

    def test_directory_default_handles_current_directory_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-113bpm"
            source.mkdir()
            (source / "bass.mid").write_bytes(_multitrack_fixture())
            previous = Path.cwd()
            try:
                os.chdir(source)
                with redirect_stdout(io.StringIO()):
                    result = main(
                        [
                            "midi-tempo",
                            ".",
                            "--source-bpm",
                            "113",
                            "--target-bpm",
                            "125",
                        ]
                    )
            finally:
                os.chdir(previous)

            self.assertEqual(result, 0)
            self.assertTrue((root / "source-125bpm" / "bass.mid").is_file())

    def test_existing_output_is_rejected_before_write_and_overwrite_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mid"
            output = root / "output.mid"
            source_bytes = _multitrack_fixture()
            source.write_bytes(source_bytes)
            output.write_bytes(b"keep me")
            arguments = [
                "midi-tempo",
                str(source),
                "--source-bpm",
                "113",
                "--target-bpm",
                "125",
                "--out",
                str(output),
            ]

            self._assert_cli_error(arguments)
            self.assertEqual(output.read_bytes(), b"keep me")
            with redirect_stdout(io.StringIO()):
                result = main(arguments + ["--overwrite"])
            self.assertEqual(result, 0)
            self.assertEqual(_tempo_events(output.read_bytes()), [(0, 0, 480_000)])
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_input_and_output_must_not_be_the_same_even_with_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mid"
            source_bytes = _multitrack_fixture()
            source.write_bytes(source_bytes)

            self._assert_cli_error(
                [
                    "midi-tempo",
                    str(source),
                    "--source-bpm",
                    "113",
                    "--target-bpm",
                    "125",
                    "--out",
                    str(source),
                    "--overwrite",
                ]
            )
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_batch_preflight_prevents_partial_output_for_invalid_midi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a-good.mid").write_bytes(_multitrack_fixture())
            (source / "z-bad.mid").write_bytes(b"not MIDI")

            self._assert_cli_error(
                [
                    "midi-tempo",
                    str(source),
                    "--source-bpm",
                    "113",
                    "--target-bpm",
                    "125",
                    "--out",
                    str(output),
                ]
            )
            self.assertFalse((output / "a-good.mid").exists())
            self.assertFalse((output / "z-bad.mid").exists())

    def test_batch_collision_is_preflighted_before_any_output_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            output.mkdir()
            (source / "a.mid").write_bytes(_multitrack_fixture())
            (source / "b.mid").write_bytes(_multitrack_fixture())
            (output / "b.mid").write_bytes(b"existing")

            self._assert_cli_error(
                [
                    "midi-tempo",
                    str(source),
                    "--source-bpm",
                    "113",
                    "--target-bpm",
                    "125",
                    "--out",
                    str(output),
                ]
            )
            self.assertFalse((output / "a.mid").exists())
            self.assertEqual((output / "b.mid").read_bytes(), b"existing")

    def test_blocked_parent_and_directory_leaf_are_preflighted_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            (source / "nested").mkdir(parents=True)
            output.mkdir()
            (source / "a.mid").write_bytes(_multitrack_fixture())
            (source / "nested" / "b.mid").write_bytes(_multitrack_fixture())
            (output / "nested").write_text("blocks directory", encoding="utf-8")

            arguments = [
                "midi-tempo",
                str(source),
                "--source-bpm",
                "113",
                "--target-bpm",
                "125",
                "--out",
                str(output),
            ]
            self._assert_cli_error(arguments)
            self.assertFalse((output / "a.mid").exists())

            (output / "nested").unlink()
            (output / "nested" / "b.mid").mkdir(parents=True)
            self._assert_cli_error(arguments + ["--overwrite"])
            self.assertFalse((output / "a.mid").exists())

    def test_output_parent_symlink_is_rejected_without_writing_outside_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            outside = root / "outside"
            (source / "nested").mkdir(parents=True)
            output.mkdir()
            outside.mkdir()
            (source / "nested" / "part.mid").write_bytes(_multitrack_fixture())
            try:
                (output / "nested").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")

            self._assert_cli_error(
                [
                    "midi-tempo",
                    str(source),
                    "--source-bpm",
                    "113",
                    "--target-bpm",
                    "125",
                    "--out",
                    str(output),
                ]
            )
            self.assertFalse((outside / "part.mid").exists())

    def test_batch_with_mixed_inferred_source_tempos_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "at-113.mid").write_bytes(_multitrack_fixture(tempos=((0, 113),)))
            (source / "at-120.mid").write_bytes(_multitrack_fixture(tempos=((0, 120),)))

            self._assert_cli_error(
                [
                    "midi-tempo",
                    str(source),
                    "--target-bpm",
                    "125",
                    "--out",
                    str(output),
                ]
            )
            self.assertFalse((output / "at-113.mid").exists())
            self.assertFalse((output / "at-120.mid").exists())

    def test_empty_directory_and_output_nested_inside_input_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty"
            empty.mkdir()
            self._assert_cli_error(
                ["midi-tempo", str(empty), "--source-bpm", "113", "--target-bpm", "125"]
            )

            source = root / "source"
            source.mkdir()
            (source / "part.mid").write_bytes(_multitrack_fixture())
            nested_output = source / "transformed"
            self._assert_cli_error(
                [
                    "midi-tempo",
                    str(source),
                    "--source-bpm",
                    "113",
                    "--target-bpm",
                    "125",
                    "--out",
                    str(nested_output),
                ]
            )
            self.assertFalse((nested_output / "part.mid").exists())


if __name__ == "__main__":
    unittest.main()
