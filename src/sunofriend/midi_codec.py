"""Lossless inspection and bounded rewriting of Standard MIDI Files.

The musical :mod:`sunofriend.clip` model deliberately interprets notes.  This
module serves a different boundary: it retains the original byte stream,
exposes exact chunk and event spans, and rewrites only caller-selected bytes.
Unedited header extensions, running-status encodings, track padding and
trailing bytes therefore remain unchanged.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Iterable


_SYSTEM_EVENT_LENGTHS = {
    0xF1: 1,
    0xF2: 2,
    0xF3: 1,
    0xF6: 0,
    0xF8: 0,
    0xFA: 0,
    0xFB: 0,
    0xFC: 0,
    0xFE: 0,
}
_CHANNEL_EVENT_TYPES = {0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0}


@dataclass(frozen=True)
class MidiHeader:
    """Fields from a structurally complete SMF header chunk."""

    midi_format: int
    track_count: int
    division: int
    header_length: int


@dataclass(frozen=True)
class MidiEvent:
    """One parsed event whose offsets refer to the unchanged source bytes."""

    track_index: int
    tick: int
    delta: int
    raw_start: int
    raw_end: int
    status: int
    explicit_status: bool
    category: str
    data_start: int
    data_end: int
    meta_type: int | None = None

    @property
    def data_length(self) -> int:
        return self.data_end - self.data_start


@dataclass(frozen=True)
class MidiTrack:
    """One track chunk and the events parsed before its optional padding."""

    index: int
    header_offset: int
    data_offset: int
    length: int
    events: tuple[MidiEvent, ...]

    @property
    def data_end(self) -> int:
        return self.data_offset + self.length


@dataclass(frozen=True)
class MidiDocument:
    """A source-bound, lossless Standard MIDI File inspection."""

    source: bytes
    source_sha256: str
    midi_format: int
    division: int
    header_length: int
    tracks: tuple[MidiTrack, ...]
    trailing_offset: int


@dataclass(frozen=True)
class MidiEdit:
    """One typed, source-bound event-data replacement or track-prefix insert."""

    track_index: int
    start: int
    end: int
    replacement: bytes
    source_sha256: str
    _kind: str

    @classmethod
    def replace_event_data(
        cls,
        document: MidiDocument,
        event: MidiEvent,
        replacement: bytes,
    ) -> MidiEdit:
        """Replace one event's data bytes without changing their encoded width."""

        value = bytes(replacement)
        _require_document_event(document, event)
        if len(value) != event.data_length:
            raise ValueError("MIDI event-data replacements must preserve byte length")
        _validate_event_data(event, value)
        return cls(
            track_index=event.track_index,
            start=event.data_start,
            end=event.data_end,
            replacement=value,
            source_sha256=document.source_sha256,
            _kind="event_data",
        )

    @classmethod
    def insert_track_event(
        cls,
        document: MidiDocument,
        track: MidiTrack,
        encoded_event: bytes,
    ) -> MidiEdit:
        """Insert one self-contained event before a track's existing bytes."""

        value = bytes(encoded_event)
        _require_document_track(document, track)
        _validate_inserted_event(value)
        return cls(
            track_index=track.index,
            start=track.data_offset,
            end=track.data_offset,
            replacement=value,
            source_sha256=document.source_sha256,
            _kind="track_event",
        )


def inspect_midi_header(data: bytes) -> MidiHeader:
    """Validate and return header fields before any track event is parsed."""

    header = _inspect_midi_header_structure(data)
    _validate_document_header(header)
    return header


def _inspect_midi_header_structure(data: bytes) -> MidiHeader:
    """Return complete header fields without selecting a document policy.

    This private seam lets a compatibility adapter preserve its own validation
    order before the strict public inspection and event parser are applied.
    """

    source = bytes(data)
    if len(source) < 14 or source[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File")
    header_length = struct.unpack(">I", source[4:8])[0]
    if header_length < 6 or len(source) < 8 + header_length:
        raise ValueError("invalid or truncated MIDI header")
    midi_format, track_count, division = struct.unpack(">HHH", source[8:14])
    return MidiHeader(midi_format, track_count, division, header_length)


def _validate_document_header(header: MidiHeader) -> None:
    if header.midi_format not in {0, 1, 2}:
        raise ValueError("only Standard MIDI File format 0, 1 and 2 are supported")
    if header.track_count < 1:
        raise ValueError("MIDI file contains no tracks")
    if header.division == 0:
        raise ValueError("MIDI division must be greater than zero")


def parse_midi(data: bytes) -> MidiDocument:
    """Strictly inspect an SMF without normalising or discarding source bytes."""

    return _parse_midi_document(data, validate_tempo=True)


def _parse_midi_structure(data: bytes) -> MidiDocument:
    """Inspect structure for legacy adapters that own event-specific policy."""

    return _parse_midi_document(data, validate_tempo=False)


def _parse_midi_document(data: bytes, *, validate_tempo: bool) -> MidiDocument:
    """Build the shared source-bound representation under one validation mode."""

    source = bytes(data)
    header = inspect_midi_header(source)

    position = 8 + header.header_length
    tracks = []
    for track_index in range(header.track_count):
        track, position = _parse_track_chunk(
            source,
            position,
            track_index,
            validate_tempo=validate_tempo,
        )
        tracks.append(track)
    return MidiDocument(
        source=source,
        source_sha256=hashlib.sha256(source).hexdigest(),
        midi_format=header.midi_format,
        division=header.division,
        header_length=header.header_length,
        tracks=tuple(tracks),
        trailing_offset=position,
    )


def rewrite_midi(document: MidiDocument, edits: Iterable[MidiEdit]) -> bytes:
    """Apply bounded track edits while preserving every unedited source byte."""

    prepared = tuple(_validated_edit(document, edit) for edit in edits)
    if not prepared:
        return document.source
    _validate_non_overlapping_edits(prepared)

    track_deltas = [0] * len(document.tracks)
    for edit in prepared:
        track_deltas[edit.track_index] += len(edit.replacement) - (edit.end - edit.start)

    length_edits = []
    for track, delta in zip(document.tracks, track_deltas):
        if delta == 0:
            continue
        length = track.length + delta
        if not 0 <= length <= 0xFFFFFFFF:
            raise ValueError(f"MIDI track {track.index} is too large to rewrite")
        length_edits.append(
            MidiEdit(
                track_index=track.index,
                start=track.header_offset + 4,
                end=track.header_offset + 8,
                replacement=struct.pack(">I", length),
                source_sha256=document.source_sha256,
                _kind="track_length",
            )
        )

    output = bytearray(document.source)
    for edit in sorted(
        (*prepared, *length_edits),
        key=lambda item: (item.start, item.end),
        reverse=True,
    ):
        output[edit.start : edit.end] = edit.replacement
    rewritten = bytes(output)
    parse_midi(rewritten)
    return rewritten


def _parse_track_chunk(
    source: bytes,
    position: int,
    track_index: int,
    *,
    validate_tempo: bool,
) -> tuple[MidiTrack, int]:
    if position + 8 > len(source) or source[position : position + 4] != b"MTrk":
        raise ValueError(f"missing or truncated MIDI track {track_index}")
    length = struct.unpack(">I", source[position + 4 : position + 8])[0]
    data_offset = position + 8
    data_end = data_offset + length
    if data_end > len(source):
        raise ValueError(f"truncated MIDI track {track_index}")
    events = _parse_track_events(
        source,
        data_offset,
        data_end,
        track_index,
        validate_tempo=validate_tempo,
    )
    return (
        MidiTrack(track_index, position, data_offset, length, events),
        data_end,
    )


def _parse_track_events(
    source: bytes,
    data_offset: int,
    data_end: int,
    track_index: int,
    *,
    validate_tempo: bool,
) -> tuple[MidiEvent, ...]:
    position = data_offset
    tick = 0
    running_status: int | None = None
    events = []
    while position < data_end:
        event, position, running_status = _parse_event(
            source,
            position,
            data_end,
            track_index,
            tick,
            running_status,
            validate_tempo=validate_tempo,
        )
        tick = event.tick
        events.append(event)
        if event.category == "meta" and event.meta_type == 0x2F:
            break
    return tuple(events)


def _parse_event(
    source: bytes,
    position: int,
    data_end: int,
    track_index: int,
    prior_tick: int,
    running_status: int | None,
    *,
    validate_tempo: bool,
) -> tuple[MidiEvent, int, int | None]:
    raw_start = position
    delta, position = _read_varlen(source, position, limit=data_end)
    tick = prior_tick + delta
    if position >= data_end:
        raise ValueError(f"truncated event in MIDI track {track_index}")

    status_byte = source[position]
    explicit_status = bool(status_byte & 0x80)
    if explicit_status:
        status = status_byte
        position += 1
        if status < 0xF0:
            running_status = status
    else:
        if running_status is None:
            raise ValueError(
                f"running status used before a status byte in MIDI track {track_index}"
            )
        status = running_status

    common = (track_index, tick, delta, raw_start, status, explicit_status)
    if status == 0xFF:
        return _parse_meta_event(
            source,
            position,
            data_end,
            common,
            validate_tempo=validate_tempo,
        )
    if status in {0xF0, 0xF7}:
        return _parse_sysex_event(source, position, data_end, common)
    if status >= 0xF0:
        return _parse_system_event(source, position, data_end, common, running_status)
    return _parse_channel_event(
        source,
        position,
        data_end,
        common,
        running_status,
    )


def _parse_meta_event(
    source: bytes,
    position: int,
    data_end: int,
    common: tuple[int, int, int, int, int, bool],
    *,
    validate_tempo: bool,
) -> tuple[MidiEvent, int, None]:
    track_index, tick, delta, raw_start, status, explicit_status = common
    if position >= data_end:
        raise ValueError(f"truncated meta event in MIDI track {track_index}")
    meta_type = source[position]
    length, data_start = _read_varlen(source, position + 1, limit=data_end)
    event_end = data_start + length
    if event_end > data_end:
        raise ValueError(f"truncated meta payload in MIDI track {track_index}")
    if meta_type == 0x51:
        _validate_tempo_event(
            source[data_start:event_end],
            validate=validate_tempo,
        )
    return (
        MidiEvent(
            track_index,
            tick,
            delta,
            raw_start,
            event_end,
            status,
            explicit_status,
            "meta",
            data_start,
            event_end,
            meta_type,
        ),
        event_end,
        None,
    )


def _validate_tempo_event(payload: bytes, *, validate: bool) -> None:
    if not validate:
        return
    if len(payload) != 3:
        raise ValueError("Set Tempo meta event must contain exactly three bytes")
    if int.from_bytes(payload, "big") == 0:
        raise ValueError("Set Tempo meta event cannot be zero")


def _parse_sysex_event(
    source: bytes,
    position: int,
    data_end: int,
    common: tuple[int, int, int, int, int, bool],
) -> tuple[MidiEvent, int, None]:
    track_index, tick, delta, raw_start, status, explicit_status = common
    length, data_start = _read_varlen(source, position, limit=data_end)
    event_end = data_start + length
    if event_end > data_end:
        raise ValueError(f"truncated SysEx event in MIDI track {track_index}")
    return (
        MidiEvent(
            track_index,
            tick,
            delta,
            raw_start,
            event_end,
            status,
            explicit_status,
            "sysex",
            data_start,
            event_end,
        ),
        event_end,
        None,
    )


def _parse_system_event(
    source: bytes,
    position: int,
    data_end: int,
    common: tuple[int, int, int, int, int, bool],
    running_status: int | None,
) -> tuple[MidiEvent, int, int | None]:
    track_index, tick, delta, raw_start, status, explicit_status = common
    if status not in _SYSTEM_EVENT_LENGTHS:
        raise ValueError(f"unsupported MIDI system event 0x{status:02x}")
    event_end = position + _SYSTEM_EVENT_LENGTHS[status]
    if event_end > data_end:
        raise ValueError(f"truncated system event in MIDI track {track_index}")
    retained_status = running_status if status >= 0xF8 else None
    return (
        MidiEvent(
            track_index,
            tick,
            delta,
            raw_start,
            event_end,
            status,
            explicit_status,
            "system",
            position,
            event_end,
        ),
        event_end,
        retained_status,
    )


def _parse_channel_event(
    source: bytes,
    position: int,
    data_end: int,
    common: tuple[int, int, int, int, int, bool],
    running_status: int | None,
) -> tuple[MidiEvent, int, int | None]:
    track_index, tick, delta, raw_start, status, explicit_status = common
    event_type = status & 0xF0
    if event_type not in _CHANNEL_EVENT_TYPES:
        raise ValueError(f"unsupported channel event 0x{status:02x}")
    event_end = position + (1 if event_type in {0xC0, 0xD0} else 2)
    if event_end > data_end:
        raise ValueError(f"truncated channel event in MIDI track {track_index}")
    if any(byte & 0x80 for byte in source[position:event_end]):
        raise ValueError(f"invalid channel-event data in MIDI track {track_index}")
    return (
        MidiEvent(
            track_index,
            tick,
            delta,
            raw_start,
            event_end,
            status,
            explicit_status,
            "channel",
            position,
            event_end,
        ),
        event_end,
        running_status,
    )


def _read_varlen(data: bytes, position: int, *, limit: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if position >= limit:
            raise ValueError("truncated MIDI variable-length value")
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position
    raise ValueError("MIDI variable-length value is too long")


def _validated_edit(document: MidiDocument, edit: MidiEdit) -> MidiEdit:
    if not isinstance(edit, MidiEdit):
        raise TypeError("MIDI rewrites require MidiEdit values")
    if edit.source_sha256 != document.source_sha256:
        raise ValueError("MIDI edit belongs to a different source document")
    if not 0 <= edit.track_index < len(document.tracks):
        raise ValueError(f"MIDI edit has invalid track index {edit.track_index}")
    track = document.tracks[edit.track_index]
    if not track.data_offset <= edit.start <= edit.end <= track.data_end:
        raise ValueError(
            f"MIDI edit must stay inside track {edit.track_index} data bytes"
        )
    if edit._kind == "event_data":
        if len(edit.replacement) != edit.end - edit.start:
            raise ValueError("MIDI event-data replacements must preserve byte length")
        event = next(
            (
                event
                for event in track.events
                if event.data_start == edit.start and event.data_end == edit.end
            ),
            None,
        )
        if event is None:
            raise ValueError("MIDI event-data replacement must match one parsed event")
        _validate_event_data(event, edit.replacement)
    elif edit._kind == "track_event":
        if edit.start != track.data_offset or edit.end != track.data_offset:
            raise ValueError("MIDI event insertion must be at the start of its track")
        _validate_inserted_event(edit.replacement)
    else:
        raise ValueError("MIDI rewrite has an unsupported edit kind")
    return MidiEdit(
        track_index=edit.track_index,
        start=edit.start,
        end=edit.end,
        replacement=bytes(edit.replacement),
        source_sha256=edit.source_sha256,
        _kind=edit._kind,
    )


def _validate_non_overlapping_edits(edits: tuple[MidiEdit, ...]) -> None:
    ordered = sorted(edits, key=lambda item: (item.start, item.end))
    for previous, current in zip(ordered, ordered[1:]):
        if current.start == previous.start or current.start < previous.end:
            raise ValueError("MIDI edits must not overlap or share an insertion point")


def _validate_inserted_event(encoded_event: bytes) -> None:
    if not encoded_event:
        raise ValueError("MIDI event insertion cannot be empty")
    event, position, _ = _parse_event(
        encoded_event,
        0,
        len(encoded_event),
        0,
        0,
        None,
        validate_tempo=True,
    )
    if position != len(encoded_event):
        raise ValueError("MIDI insertion must contain exactly one complete event")
    if not event.explicit_status:
        raise ValueError("MIDI inserted event must contain an explicit status byte")
    if event.delta != 0:
        raise ValueError("MIDI track-prefix event must have a zero delta")
    if event.category == "meta" and event.meta_type == 0x2F:
        raise ValueError("MIDI End Of Track cannot be inserted before track content")


def _require_document_track(document: MidiDocument, track: MidiTrack) -> None:
    if not 0 <= track.index < len(document.tracks):
        raise ValueError("MIDI track belongs to a different source document")
    if document.tracks[track.index] is not track:
        raise ValueError("MIDI track belongs to a different source document")


def _require_document_event(document: MidiDocument, event: MidiEvent) -> None:
    if not 0 <= event.track_index < len(document.tracks):
        raise ValueError("MIDI event belongs to a different source document")
    if not any(
        candidate is event
        for candidate in document.tracks[event.track_index].events
    ):
        raise ValueError("MIDI event belongs to a different source document")


def _validate_event_data(event: MidiEvent, replacement: bytes) -> None:
    if event.category in {"channel", "system"} and any(
        byte & 0x80 for byte in replacement
    ):
        raise ValueError("MIDI channel and system data bytes must be seven-bit values")
    if event.category == "meta" and event.meta_type == 0x51:
        if len(replacement) != 3:
            raise ValueError("Set Tempo meta event must contain exactly three bytes")
        if int.from_bytes(replacement, "big") == 0:
            raise ValueError("Set Tempo meta event cannot be zero")
