"""Canonical, versionable MIDI clips for Sunofriend.

The existing transcription pipeline works in seconds because its first job is
to line up with an audio stem.  Creative editing works in beats.  ``MidiClip``
keeps both representations instead of forcing either use case to throw useful
timing information away.

This module deliberately has no third-party dependencies.  Its small Standard
MIDI File reader/writer is sufficient for Sunofriend clips and for files made
by :mod:`sunofriend.midi`, while accepting the common format-0 and format-1
channel events found in DAW exports.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

from .note_safety import MidiNoteInterval, normalize_midi_intervals


SCHEMA_VERSION = 1
DEFAULT_TICKS_PER_BEAT = 480
_JSON_OBJECT = "__sunofriend_frozen_json_object__"

_NOTE_TO_PC = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "FB": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
    "CB": 11,
}
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


def pitch_class(note_name: str) -> int:
    """Return a pitch class for a note name such as ``C#`` or ``Bb``."""

    normalized = normalize_note_name(note_name).upper()
    try:
        return _NOTE_TO_PC[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown note name: {note_name!r}") from exc


def normalize_note_name(note_name: str) -> str:
    text = str(note_name).strip()
    if not text:
        raise ValueError("A note name is required")
    letter = text[0].upper()
    if letter not in "ABCDEFG":
        raise ValueError(f"Unknown note name: {note_name!r}")
    accidental = text[1:]
    if accidental not in {"", "#", "b", "B"}:
        raise ValueError(f"Unknown note name: {note_name!r}")
    return letter + ("b" if accidental in {"b", "B"} else accidental)


def note_name_for_pc(pc: int, prefer_flats: bool = False) -> str:
    names = _FLAT_NAMES if prefer_flats else _SHARP_NAMES
    return names[int(pc) % 12]


def _finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _freeze_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Recipe values must be finite JSON values")
        return value
    if isinstance(value, Mapping):
        return (
            _JSON_OBJECT,
            tuple(
                (str(key), _freeze_json(item))
                for key, item in sorted(value.items(), key=lambda item: str(item[0]))
            ),
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError(f"Not a JSON-compatible immutable value: {type(value).__name__}")


def _thaw_json(value: Any, mapping: bool = False) -> Any:
    if isinstance(value, tuple):
        if len(value) == 2 and value[0] == _JSON_OBJECT and isinstance(value[1], tuple):
            return {key: _thaw_json(item) for key, item in value[1]}
        if mapping:
            return {key: _thaw_json(item) for key, item in value}
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class KeySignature:
    tonic: str
    mode: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tonic", normalize_note_name(self.tonic))
        mode = self.mode.strip().lower()
        aliases = {"maj": "major", "min": "minor", "m": "minor"}
        mode = aliases.get(mode, mode)
        if mode not in {"major", "minor"}:
            raise ValueError("mode must be 'major' or 'minor'")
        object.__setattr__(self, "mode", mode)

    @property
    def tonic_pc(self) -> int:
        return pitch_class(self.tonic)

    @classmethod
    def parse(cls, value: str | None) -> "KeySignature | None":
        if value is None:
            return None
        pieces = str(value).strip().split()
        if len(pieces) != 2:
            raise ValueError(f"Expected a key such as 'D minor', got {value!r}")
        return cls(pieces[0], pieces[1])

    def __str__(self) -> str:
        return f"{self.tonic} {self.mode}"


@dataclass(frozen=True)
class TimeSignature:
    numerator: int = 4
    denominator: int = 4

    def __post_init__(self) -> None:
        if self.numerator <= 0:
            raise ValueError("time-signature numerator must be positive")
        if self.denominator <= 0 or self.denominator & (self.denominator - 1):
            raise ValueError("time-signature denominator must be a power of two")


@dataclass(frozen=True, order=True)
class TempoPoint:
    beat: float
    bpm: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "beat", _finite(self.beat, "tempo beat"))
        object.__setattr__(self, "bpm", _finite(self.bpm, "bpm"))
        if self.bpm <= 0:
            raise ValueError("bpm must be greater than zero")


@dataclass(frozen=True, order=True)
class WarpPoint:
    beat: float
    source_second: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "beat", _finite(self.beat, "warp beat"))
        object.__setattr__(self, "source_second", _finite(self.source_second, "source second"))


@dataclass(frozen=True)
class TempoMap:
    """Piecewise-constant musical tempo plus optional audio warp anchors."""

    tempo_points: tuple[TempoPoint, ...] = (TempoPoint(0.0, 120.0),)
    warp_points: tuple[WarpPoint, ...] = ()
    offset_seconds: float = 0.0

    def __post_init__(self) -> None:
        tempo_points = tuple(sorted(self.tempo_points, key=lambda point: point.beat))
        warp_points = tuple(sorted(self.warp_points, key=lambda point: point.beat))
        if not tempo_points:
            raise ValueError("A tempo map needs at least one tempo point")
        if abs(tempo_points[0].beat) > 1e-9:
            raise ValueError("The first tempo point must start at beat 0")
        if len({point.beat for point in tempo_points}) != len(tempo_points):
            raise ValueError("Tempo points cannot share a beat")
        if len({point.beat for point in warp_points}) != len(warp_points):
            raise ValueError("Warp points cannot share a beat")
        if any(right.source_second <= left.source_second for left, right in zip(warp_points, warp_points[1:])):
            raise ValueError("Warp source seconds must increase with beats")
        object.__setattr__(self, "tempo_points", tempo_points)
        object.__setattr__(self, "warp_points", warp_points)
        object.__setattr__(self, "offset_seconds", _finite(self.offset_seconds, "offset_seconds"))

    @classmethod
    def constant(cls, bpm: float, offset_seconds: float = 0.0) -> "TempoMap":
        return cls((TempoPoint(0.0, bpm),), (), offset_seconds)

    @property
    def bpm(self) -> float:
        return self.tempo_points[0].bpm

    def bpm_at(self, beat: float) -> float:
        selected = self.tempo_points[0]
        for point in self.tempo_points[1:]:
            if point.beat > beat:
                break
            selected = point
        return selected.bpm

    def musical_seconds_at(self, beat: float) -> float:
        """Map a beat through tempo events, ignoring the audio warp map."""

        beat = _finite(beat, "beat")
        first = self.tempo_points[0]
        if beat <= 0:
            return self.offset_seconds + beat * 60.0 / first.bpm
        seconds = self.offset_seconds
        previous_beat = 0.0
        previous_bpm = first.bpm
        for point in self.tempo_points[1:]:
            if beat <= point.beat:
                return seconds + (beat - previous_beat) * 60.0 / previous_bpm
            seconds += (point.beat - previous_beat) * 60.0 / previous_bpm
            previous_beat = point.beat
            previous_bpm = point.bpm
        return seconds + (beat - previous_beat) * 60.0 / previous_bpm

    def beat_at_musical_seconds(self, seconds: float) -> float:
        seconds = _finite(seconds, "seconds")
        if seconds <= self.offset_seconds:
            return (seconds - self.offset_seconds) * self.tempo_points[0].bpm / 60.0
        elapsed = seconds - self.offset_seconds
        previous_beat = 0.0
        previous_bpm = self.tempo_points[0].bpm
        for point in self.tempo_points[1:]:
            segment_seconds = (point.beat - previous_beat) * 60.0 / previous_bpm
            if elapsed <= segment_seconds:
                return previous_beat + elapsed * previous_bpm / 60.0
            elapsed -= segment_seconds
            previous_beat = point.beat
            previous_bpm = point.bpm
        return previous_beat + elapsed * previous_bpm / 60.0

    def source_seconds_at(self, beat: float) -> float:
        """Map a beat to its exact position in the source stem."""

        if not self.warp_points:
            return self.musical_seconds_at(beat)
        if len(self.warp_points) == 1:
            anchor = self.warp_points[0]
            musical_delta = self.musical_seconds_at(beat) - self.musical_seconds_at(anchor.beat)
            return anchor.source_second + musical_delta
        points = self.warp_points
        if beat <= points[0].beat:
            left, right = points[0], points[1]
        elif beat >= points[-1].beat:
            left, right = points[-2], points[-1]
        else:
            for left, right in zip(points, points[1:]):
                if left.beat <= beat <= right.beat:
                    break
        proportion = (beat - left.beat) / (right.beat - left.beat)
        return left.source_second + proportion * (right.source_second - left.source_second)

    def beat_at_source_seconds(self, seconds: float) -> float:
        if not self.warp_points:
            return self.beat_at_musical_seconds(seconds)
        if len(self.warp_points) == 1:
            anchor = self.warp_points[0]
            target = self.musical_seconds_at(anchor.beat) + (seconds - anchor.source_second)
            return self.beat_at_musical_seconds(target)
        points = self.warp_points
        if seconds <= points[0].source_second:
            left, right = points[0], points[1]
        elif seconds >= points[-1].source_second:
            left, right = points[-2], points[-1]
        else:
            for left, right in zip(points, points[1:]):
                if left.source_second <= seconds <= right.source_second:
                    break
        proportion = (seconds - left.source_second) / (right.source_second - left.source_second)
        return left.beat + proportion * (right.beat - left.beat)

    def seconds_delta_to_beats(self, seconds: float, at_beat: float) -> float:
        return float(seconds) * self.bpm_at(at_beat) / 60.0


@dataclass(frozen=True)
class ClipNote:
    """A note with a musical grid position and exact audio-source position.

    ``start_beat`` and ``duration_beats`` describe the editable musical note.
    Microtiming is stored separately and is included in MIDI export.  Source
    seconds preserve the alignment evidence used by stem-locked transforms.
    """

    start_beat: float
    duration_beats: float
    pitch: int
    velocity: int
    source_start_seconds: float
    source_end_seconds: float
    microtiming_seconds: float = 0.0
    end_microtiming_seconds: float = 0.0
    release_velocity: int = 0
    articulation: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_beat", _finite(self.start_beat, "start_beat"))
        object.__setattr__(self, "duration_beats", _finite(self.duration_beats, "duration_beats"))
        object.__setattr__(
            self, "source_start_seconds", _finite(self.source_start_seconds, "source_start_seconds")
        )
        object.__setattr__(self, "source_end_seconds", _finite(self.source_end_seconds, "source_end_seconds"))
        object.__setattr__(self, "microtiming_seconds", _finite(self.microtiming_seconds, "microtiming_seconds"))
        object.__setattr__(
            self, "end_microtiming_seconds", _finite(self.end_microtiming_seconds, "end_microtiming_seconds")
        )
        if self.duration_beats <= 0:
            raise ValueError("duration_beats must be greater than zero")
        if not 0 <= int(self.pitch) <= 127:
            raise ValueError("MIDI pitch must be between 0 and 127")
        if not 1 <= int(self.velocity) <= 127:
            raise ValueError("MIDI velocity must be between 1 and 127")
        if not 0 <= int(self.release_velocity) <= 127:
            raise ValueError("MIDI release velocity must be between 0 and 127")
        if self.source_end_seconds <= self.source_start_seconds:
            raise ValueError("source_end_seconds must be after source_start_seconds")
        object.__setattr__(self, "pitch", int(self.pitch))
        object.__setattr__(self, "velocity", int(self.velocity))
        object.__setattr__(self, "release_velocity", int(self.release_velocity))

    @property
    def end_beat(self) -> float:
        return self.start_beat + self.duration_beats

    @classmethod
    def from_beats(
        cls,
        start_beat: float,
        duration_beats: float,
        pitch: int,
        velocity: int,
        tempo_map: TempoMap,
        microtiming_seconds: float = 0.0,
        end_microtiming_seconds: float = 0.0,
        **kwargs: Any,
    ) -> "ClipNote":
        source_start = tempo_map.source_seconds_at(start_beat) + microtiming_seconds
        source_end = tempo_map.source_seconds_at(start_beat + duration_beats) + end_microtiming_seconds
        return cls(
            start_beat,
            duration_beats,
            pitch,
            velocity,
            source_start,
            source_end,
            microtiming_seconds,
            end_microtiming_seconds,
            **kwargs,
        )


@dataclass(frozen=True)
class ChordEvent:
    start_beat: float
    duration_beats: float
    symbol: str
    source_start_seconds: float | None = None
    source_end_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_beat", _finite(self.start_beat, "chord start_beat"))
        object.__setattr__(self, "duration_beats", _finite(self.duration_beats, "chord duration_beats"))
        if self.duration_beats <= 0:
            raise ValueError("Chord duration must be greater than zero")
        if not str(self.symbol).strip():
            raise ValueError("Chord symbol cannot be empty")
        object.__setattr__(self, "symbol", str(self.symbol).strip())
        if (self.source_start_seconds is None) != (self.source_end_seconds is None):
            raise ValueError("Chord source start and end must either both be set or both be omitted")
        if self.source_start_seconds is not None:
            start = _finite(self.source_start_seconds, "chord source start")
            end = _finite(self.source_end_seconds, "chord source end")
            if end <= start:
                raise ValueError("Chord source end must be after its start")
            object.__setattr__(self, "source_start_seconds", start)
            object.__setattr__(self, "source_end_seconds", end)

    @property
    def end_beat(self) -> float:
        return self.start_beat + self.duration_beats


@dataclass(frozen=True)
class Instrument:
    role: str
    program: int = 0
    channel: int = 0
    suggestions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        role = str(self.role).strip().lower()
        if not role:
            raise ValueError("An instrument role is required")
        if not 0 <= int(self.program) <= 127:
            raise ValueError("MIDI program must be between 0 and 127")
        if not 0 <= int(self.channel) <= 15:
            raise ValueError("MIDI channel must be between 0 and 15")
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "program", int(self.program))
        object.__setattr__(self, "channel", int(self.channel))
        object.__setattr__(self, "suggestions", tuple(str(item) for item in self.suggestions))

    @property
    def is_drums(self) -> bool:
        return self.channel == 9 or self.role in {"drum", "drums", "percussion"}


@dataclass(frozen=True)
class Provenance:
    source_uri: str | None = None
    source_stem: str | None = None
    converter: str | None = None
    captured_at: str | None = None
    details: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        details: Any = self.details
        if isinstance(details, Mapping):
            details = tuple(details.items())
        frozen = tuple(
            (str(key), _freeze_json(value))
            for key, value in sorted(details, key=lambda item: str(item[0]))
        )
        object.__setattr__(self, "details", frozen)

    @property
    def details_dict(self) -> dict[str, Any]:
        return {key: _thaw_json(value) for key, value in self.details}


@dataclass(frozen=True)
class TransformRecipe:
    operation: str
    parameters: tuple[tuple[str, Any], ...] = ()
    seed: int | None = None

    def __post_init__(self) -> None:
        operation = str(self.operation).strip()
        if not operation:
            raise ValueError("A transform operation is required")
        parameters: Any = self.parameters
        if isinstance(parameters, Mapping):
            parameters = tuple(parameters.items())
        frozen = tuple(
            (str(key), _freeze_json(value))
            for key, value in sorted(parameters, key=lambda item: str(item[0]))
        )
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "parameters", frozen)

    @classmethod
    def create(cls, operation: str, seed: int | None = None, **parameters: Any) -> "TransformRecipe":
        return cls(operation, tuple(parameters.items()), seed)

    @property
    def parameters_dict(self) -> dict[str, Any]:
        return {key: _thaw_json(value) for key, value in self.parameters}


@dataclass(frozen=True)
class MidiClip:
    title: str
    tempo_map: TempoMap
    time_signature: TimeSignature
    instrument: Instrument
    notes: tuple[ClipNote, ...]
    key: KeySignature | None = None
    chords: tuple[ChordEvent, ...] = ()
    provenance: Provenance = field(default_factory=Provenance)
    clip_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_clip_id: str | None = None
    revision: int = 1
    transform_recipe: TransformRecipe | None = None
    engine_version: str = "sunofriend-clip-v1"
    tags: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported clip schema version: {self.schema_version}")
        if not str(self.title).strip():
            raise ValueError("A clip title is required")
        if not str(self.clip_id).strip():
            raise ValueError("A clip_id is required")
        if int(self.revision) < 1:
            raise ValueError("revision must be at least 1")
        if self.parent_clip_id == self.clip_id:
            raise ValueError("A clip cannot be its own parent")
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "clip_id", str(self.clip_id))
        object.__setattr__(self, "revision", int(self.revision))
        object.__setattr__(self, "notes", tuple(sorted(self.notes, key=lambda n: (n.start_beat, n.pitch, n.duration_beats))))
        object.__setattr__(self, "chords", tuple(sorted(self.chords, key=lambda chord: chord.start_beat)))
        object.__setattr__(self, "tags", tuple(sorted({str(tag).strip() for tag in self.tags if str(tag).strip()})))
        object.__setattr__(self, "engine_version", str(self.engine_version))

    @property
    def bpm(self) -> float:
        return self.tempo_map.bpm

    @property
    def duration_beats(self) -> float:
        note_end = max((note.end_beat for note in self.notes), default=0.0)
        chord_end = max((chord.end_beat for chord in self.chords), default=0.0)
        return max(note_end, chord_end)

    def child(
        self,
        *,
        recipe: TransformRecipe,
        title: str | None = None,
        engine_version: str | None = None,
        **changes: Any,
    ) -> "MidiClip":
        """Create an immutable child version while preserving provenance."""

        return replace(
            self,
            clip_id=str(uuid.uuid4()),
            parent_clip_id=self.clip_id,
            revision=self.revision + 1,
            transform_recipe=recipe,
            title=title or self.title,
            engine_version=engine_version or self.engine_version,
            **changes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "clip_id": self.clip_id,
            "parent_clip_id": self.parent_clip_id,
            "revision": self.revision,
            "title": self.title,
            "key": None if self.key is None else {"tonic": self.key.tonic, "mode": self.key.mode},
            "tempo_map": {
                "offset_seconds": self.tempo_map.offset_seconds,
                "tempo_points": [
                    {"beat": point.beat, "bpm": point.bpm} for point in self.tempo_map.tempo_points
                ],
                "warp_points": [
                    {"beat": point.beat, "source_second": point.source_second}
                    for point in self.tempo_map.warp_points
                ],
            },
            "time_signature": {
                "numerator": self.time_signature.numerator,
                "denominator": self.time_signature.denominator,
            },
            "instrument": {
                "role": self.instrument.role,
                "program": self.instrument.program,
                "channel": self.instrument.channel,
                "suggestions": list(self.instrument.suggestions),
            },
            "notes": [
                {
                    "start_beat": note.start_beat,
                    "duration_beats": note.duration_beats,
                    "pitch": note.pitch,
                    "velocity": note.velocity,
                    "source_start_seconds": note.source_start_seconds,
                    "source_end_seconds": note.source_end_seconds,
                    "microtiming_seconds": note.microtiming_seconds,
                    "end_microtiming_seconds": note.end_microtiming_seconds,
                    "release_velocity": note.release_velocity,
                    "articulation": note.articulation,
                }
                for note in self.notes
            ],
            "chords": [
                {
                    "start_beat": chord.start_beat,
                    "duration_beats": chord.duration_beats,
                    "symbol": chord.symbol,
                    "source_start_seconds": chord.source_start_seconds,
                    "source_end_seconds": chord.source_end_seconds,
                }
                for chord in self.chords
            ],
            "provenance": {
                "source_uri": self.provenance.source_uri,
                "source_stem": self.provenance.source_stem,
                "converter": self.provenance.converter,
                "captured_at": self.provenance.captured_at,
                "details": self.provenance.details_dict,
            },
            "transform_recipe": None
            if self.transform_recipe is None
            else {
                "operation": self.transform_recipe.operation,
                "parameters": self.transform_recipe.parameters_dict,
                "seed": self.transform_recipe.seed,
            },
            "engine_version": self.engine_version,
            "tags": list(self.tags),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        separators = None if indent is not None else (",", ":")
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent, separators=separators, ensure_ascii=False)

    def canonical_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def with_content_id(self) -> "MidiClip":
        """Return the same root clip with an ID derived from all import metadata.

        This makes repeated imports idempotent while allowing the same MIDI file
        to be catalogued deliberately with different titles, tags, roles, keys,
        or instrument suggestions.
        """
        if self.parent_clip_id is not None or self.revision != 1:
            raise ValueError("Content-derived IDs are only valid for root clips")
        document = self.to_dict()
        document["clip_id"] = ""
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return replace(self, clip_id=hashlib.sha256(payload).hexdigest())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MidiClip":
        version = int(data.get("schema_version", 0))
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported clip schema version: {version}")
        tempo_data = data["tempo_map"]
        tempo_map = TempoMap(
            tuple(TempoPoint(point["beat"], point["bpm"]) for point in tempo_data["tempo_points"]),
            tuple(
                WarpPoint(point["beat"], point["source_second"])
                for point in tempo_data.get("warp_points", ())
            ),
            tempo_data.get("offset_seconds", 0.0),
        )
        key_data = data.get("key")
        recipe_data = data.get("transform_recipe")
        provenance_data = data.get("provenance") or {}
        instrument_data = data["instrument"]
        signature_data = data.get("time_signature") or {}
        return cls(
            title=data["title"],
            tempo_map=tempo_map,
            time_signature=TimeSignature(
                signature_data.get("numerator", 4), signature_data.get("denominator", 4)
            ),
            instrument=Instrument(
                instrument_data["role"],
                instrument_data.get("program", 0),
                instrument_data.get("channel", 0),
                tuple(instrument_data.get("suggestions", ())),
            ),
            notes=tuple(ClipNote(**item) for item in data.get("notes", ())),
            key=None if key_data is None else KeySignature(key_data["tonic"], key_data["mode"]),
            chords=tuple(ChordEvent(**item) for item in data.get("chords", ())),
            provenance=Provenance(
                provenance_data.get("source_uri"),
                provenance_data.get("source_stem"),
                provenance_data.get("converter"),
                provenance_data.get("captured_at"),
                provenance_data.get("details", {}),
            ),
            clip_id=data["clip_id"],
            parent_clip_id=data.get("parent_clip_id"),
            revision=data.get("revision", 1),
            transform_recipe=None
            if recipe_data is None
            else TransformRecipe(
                recipe_data["operation"], recipe_data.get("parameters", {}), recipe_data.get("seed")
            ),
            engine_version=data.get("engine_version", "sunofriend-clip-v1"),
            tags=tuple(data.get("tags", ())),
            schema_version=version,
        )

    @classmethod
    def from_json(cls, value: str | bytes) -> "MidiClip":
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("A clip JSON document must be an object")
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Standard MIDI File export


def write_clip_midi(
    path: str | Path,
    clip: MidiClip,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
    *,
    timing_mode: Literal["auto", "musical", "stem_locked"] = "auto",
    garageband_bpm: float | None = None,
) -> None:
    """Write a deterministic format-1 MIDI file for a single clip.

    ``musical`` writes the editable beat positions and tempo map.  In
    ``stem_locked`` mode the note/chord source seconds are authoritative: they
    are converted to ticks at one exact, GarageBand-enterable tempo.  ``auto``
    selects the timing contract stored in the clip provenance and otherwise
    falls back to musical timing.

    The distinction matters for analysed audio.  A warped beat grid can start
    after time zero (for example, the Move Your Body downbeat is roughly 175
    ms into the stems); exporting only its beat positions would silently erase
    that lead-in and move every note early.
    """

    if ticks_per_beat <= 0 or ticks_per_beat > 0x7FFF:
        raise ValueError("ticks_per_beat must be between 1 and 32767")
    resolved_mode, resolved_bpm = resolve_export_timing(
        clip, timing_mode=timing_mode, garageband_bpm=garageband_bpm
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tempo_chunk = _tempo_track_chunk(
        clip,
        ticks_per_beat,
        stem_locked_bpm=resolved_bpm if resolved_mode == "stem_locked" else None,
    )
    note_chunk = _note_track_chunk(
        clip,
        ticks_per_beat,
        timing_mode=resolved_mode,
        stem_locked_bpm=resolved_bpm,
    )
    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, ticks_per_beat)
    path.write_bytes(header + tempo_chunk + note_chunk)


def resolve_export_timing(
    clip: MidiClip,
    *,
    timing_mode: Literal["auto", "musical", "stem_locked"],
    garageband_bpm: float | None,
) -> tuple[Literal["musical", "stem_locked"], float]:
    """Resolve a clip's effective MIDI timing contract and reference BPM."""
    if timing_mode not in {"auto", "musical", "stem_locked"}:
        raise ValueError("timing_mode must be 'auto', 'musical', or 'stem_locked'")

    details = clip.provenance.details_dict
    if timing_mode == "auto":
        stored_mode = details.get("timing_mode")
        resolved_mode: Literal["musical", "stem_locked"] = (
            stored_mode if stored_mode in {"musical", "stem_locked"} else "musical"
        )
    else:
        resolved_mode = timing_mode

    if garageband_bpm is not None and resolved_mode != "stem_locked":
        raise ValueError("garageband_bpm is only valid for a stem_locked export")
    if garageband_bpm is not None:
        resolved_bpm = _finite(garageband_bpm, "garageband_bpm")
    elif resolved_mode == "stem_locked" and details.get("garageband_bpm") is not None:
        resolved_bpm = _finite(details["garageband_bpm"], "garageband_bpm")
    else:
        resolved_bpm = clip.bpm
    if resolved_bpm <= 0:
        raise ValueError("garageband_bpm must be greater than zero")
    return resolved_mode, resolved_bpm


def _tempo_track_chunk(
    clip: MidiClip,
    ticks_per_beat: int,
    *,
    stem_locked_bpm: float | None = None,
) -> bytes:
    events: list[tuple[int, int, bytes]] = [(0, 0, _meta(0x03, b"Tempo"))]
    signature = clip.time_signature
    denominator_power = int(math.log2(signature.denominator))
    events.append((0, 1, _meta(0x58, bytes((signature.numerator, denominator_power, 24, 8)))))
    if clip.key is not None:
        sf, minor = _midi_key_signature(clip.key)
        events.append((0, 2, _meta(0x59, bytes((sf & 0xFF, minor)))))
    tempo_points = (
        (TempoPoint(0.0, stem_locked_bpm),)
        if stem_locked_bpm is not None
        else clip.tempo_map.tempo_points
    )
    for point in tempo_points:
        tick = max(0, int(round(point.beat * ticks_per_beat)))
        micros = int(round(60_000_000.0 / point.bpm))
        events.append((tick, 3, _meta(0x51, micros.to_bytes(3, "big"))))
    return _make_track(events)


def _note_track_chunk(
    clip: MidiClip,
    ticks_per_beat: int,
    *,
    timing_mode: Literal["musical", "stem_locked"],
    stem_locked_bpm: float,
) -> bytes:
    channel = clip.instrument.channel
    events: list[tuple[int, int, bytes]] = [(0, 0, _meta(0x03, clip.title.encode("utf-8")))]
    if channel != 9:
        events.append((0, 1, bytes((0xC0 | channel, clip.instrument.program))))
    for chord in clip.chords:
        if timing_mode == "stem_locked":
            source_start = (
                chord.source_start_seconds
                if chord.source_start_seconds is not None
                else clip.tempo_map.source_seconds_at(chord.start_beat)
            )
            tick = _source_seconds_to_tick(source_start, stem_locked_bpm, ticks_per_beat)
        else:
            tick = max(0, int(round(chord.start_beat * ticks_per_beat)))
        events.append((tick, 2, _meta(0x06, chord.symbol.encode("utf-8"))))
    raw_notes: list[MidiNoteInterval] = []
    for note in clip.notes:
        if timing_mode == "stem_locked":
            start_tick = _source_seconds_to_tick(
                note.source_start_seconds, stem_locked_bpm, ticks_per_beat
            )
            end_tick = _source_seconds_to_tick(
                note.source_end_seconds, stem_locked_bpm, ticks_per_beat
            )
        else:
            start_beat = note.start_beat + clip.tempo_map.seconds_delta_to_beats(
                note.microtiming_seconds, note.start_beat
            )
            grid_end = note.start_beat + note.duration_beats
            end_beat = grid_end + clip.tempo_map.seconds_delta_to_beats(
                note.end_microtiming_seconds, grid_end
            )
            start_tick = int(round(start_beat * ticks_per_beat))
            end_tick = int(round(end_beat * ticks_per_beat))
        raw_notes.append(
            MidiNoteInterval(
                owner=0,
                channel=channel,
                start_tick=start_tick,
                end_tick=end_tick,
                pitch=note.pitch,
                velocity=note.velocity,
                release_velocity=note.release_velocity,
            )
        )
    for note in normalize_midi_intervals(raw_notes):
        events.append(
            (note.start_tick, 4, bytes((0x90 | channel, note.pitch, note.velocity)))
        )
        events.append(
            (
                note.end_tick,
                3,
                bytes((0x80 | channel, note.pitch, note.release_velocity)),
            )
        )
    return _make_track(events)


def _source_seconds_to_tick(seconds: float, bpm: float, ticks_per_beat: int) -> int:
    return int(round(float(seconds) * float(bpm) * ticks_per_beat / 60.0))


def _midi_key_signature(key: KeySignature) -> tuple[int, int]:
    # MIDI's key signature stores the number of sharps/flats, not the tonic.
    major = {"Cb": -7, "Gb": -6, "Db": -5, "Ab": -4, "Eb": -3, "Bb": -2, "F": -1,
             "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7}
    minor = {"Ab": -7, "Eb": -6, "Bb": -5, "F": -4, "C": -3, "G": -2, "D": -1,
             "A": 0, "E": 1, "B": 2, "F#": 3, "C#": 4, "G#": 5, "D#": 6, "A#": 7}
    table = minor if key.mode == "minor" else major
    tonic = key.tonic
    if tonic not in table:
        # Pick the enharmonic spelling that MIDI can express.
        tonic_pc = key.tonic_pc
        candidates = [name for name in table if pitch_class(name) == tonic_pc]
        tonic = min(candidates, key=lambda name: abs(table[name]))
    return table[tonic], int(key.mode == "minor")


def _meta(kind: int, payload: bytes) -> bytes:
    return bytes((0xFF, kind)) + _write_varlen(len(payload)) + payload


def _make_track(events: Sequence[tuple[int, int, bytes]]) -> bytes:
    ordered = sorted(events, key=lambda item: (item[0], item[1], item[2]))
    data = bytearray()
    previous = 0
    for tick, _, payload in ordered:
        if tick < previous:
            raise ValueError("MIDI events must be in chronological order")
        data.extend(_write_varlen(tick - previous))
        data.extend(payload)
        previous = tick
    data.extend(_write_varlen(0))
    data.extend(b"\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def _write_varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("MIDI variable-length values cannot be negative")
    output = [value & 0x7F]
    value >>= 7
    while value:
        output.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(output)


# ---------------------------------------------------------------------------
# Standard MIDI File import


@dataclass
class _ParsedTrack:
    name: str
    programs: dict[int, int]
    notes: list[tuple[int, int, int, int, int, int]]
    chords: list[tuple[int, str]]


class MidiNoteLimitError(ValueError):
    """Raised before MIDI import materializes more note-ons than allowed."""

    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self.minimum_count = self.limit + 1
        super().__init__(f"MIDI contains more than {self.limit} note-on events")


def read_midi_clips(
    path: str | Path,
    *,
    key: KeySignature | str | None = None,
    role: str | None = None,
    suggestions: Iterable[str] = (),
    max_notes: int | None = None,
) -> tuple[MidiClip, ...]:
    """Read every note-bearing track/channel from a format-0 or format-1 file."""

    path = Path(path)
    if max_notes is not None:
        if isinstance(max_notes, bool) or not isinstance(max_notes, int) or max_notes < 1:
            raise ValueError("max_notes must be a positive integer")
    raw = path.read_bytes()
    if len(raw) < 14 or raw[:4] != b"MThd":
        raise ValueError(f"Not a Standard MIDI File: {path}")
    header_length = struct.unpack(">I", raw[4:8])[0]
    if header_length < 6 or len(raw) < 8 + header_length:
        raise ValueError("Invalid MIDI header")
    midi_format, track_count, division = struct.unpack(">HHH", raw[8:14])
    if midi_format not in {0, 1}:
        raise ValueError(f"Unsupported MIDI format: {midi_format}")
    if division & 0x8000:
        raise ValueError("SMPTE-time MIDI files are not supported")
    ticks_per_beat = division
    position = 8 + header_length
    tracks: list[_ParsedTrack] = []
    tempos: list[tuple[int, float]] = []
    signatures: list[tuple[int, TimeSignature]] = []
    keys: list[tuple[int, KeySignature]] = []
    global_chords: list[tuple[int, str]] = []
    note_on_count = 0
    for _ in range(track_count):
        if raw[position:position + 4] != b"MTrk" or position + 8 > len(raw):
            raise ValueError("Missing or truncated MIDI track")
        length = struct.unpack(">I", raw[position + 4:position + 8])[0]
        start = position + 8
        end = start + length
        if end > len(raw):
            raise ValueError("Truncated MIDI track")
        try:
            parsed, metadata = _parse_track(
                raw[start:end],
                max_note_ons=(
                    None if max_notes is None else max_notes - note_on_count
                ),
            )
        except MidiNoteLimitError as exc:
            raise MidiNoteLimitError(max_notes) from exc
        note_on_count += int(metadata["note_on_count"])
        tracks.append(parsed)
        tempos.extend(metadata["tempos"])
        signatures.extend(metadata["signatures"])
        keys.extend(metadata["keys"])
        global_chords.extend(parsed.chords)
        position = end

    tempo_map = _tempo_map_from_midi(tempos, ticks_per_beat)
    time_signature = min(signatures, key=lambda item: item[0])[1] if signatures else TimeSignature()
    if isinstance(key, str):
        key = KeySignature.parse(key)
    detected_key = min(keys, key=lambda item: item[0])[1] if keys else None
    key_signature = key or detected_key
    digest = hashlib.sha256(raw).hexdigest()
    clips: list[MidiClip] = []
    for track_number, track in enumerate(tracks):
        channels = sorted({note[2] for note in track.notes})
        for channel in channels:
            channel_notes = [note for note in track.notes if note[2] == channel]
            title = track.name or path.stem
            if len(channels) > 1:
                title = f"{title} ch {channel + 1}"
            instrument_role = role or ("drums" if channel == 9 else _infer_role(title))
            instrument_suggestions = tuple(suggestions) or _infer_suggestions(
                title, instrument_role
            )
            program = track.programs.get(channel, 0)
            clip_notes = []
            for start_tick, end_tick, _, pitch, velocity, release_velocity in channel_notes:
                start_beat = start_tick / ticks_per_beat
                end_beat = end_tick / ticks_per_beat
                clip_notes.append(
                    ClipNote(
                        start_beat=start_beat,
                        duration_beats=max(1.0 / ticks_per_beat, end_beat - start_beat),
                        pitch=pitch,
                        velocity=velocity,
                        source_start_seconds=tempo_map.musical_seconds_at(start_beat),
                        source_end_seconds=tempo_map.musical_seconds_at(end_beat),
                        release_velocity=release_velocity,
                    )
                )
            last_beat = max((note.end_beat for note in clip_notes), default=0.0)
            chord_markers = sorted(set(global_chords), key=lambda item: (item[0], item[1]))
            chords = []
            for marker_index, (tick, symbol) in enumerate(chord_markers):
                start_beat = tick / ticks_per_beat
                if marker_index + 1 < len(chord_markers):
                    end_beat = chord_markers[marker_index + 1][0] / ticks_per_beat
                else:
                    end_beat = max(last_beat, start_beat + 1.0)
                if end_beat > start_beat:
                    chords.append(
                        ChordEvent(
                            start_beat,
                            end_beat - start_beat,
                            symbol,
                            tempo_map.musical_seconds_at(start_beat),
                            tempo_map.musical_seconds_at(end_beat),
                        )
                    )
            clip_id = hashlib.sha256(
                f"midi:{digest}:{track_number}:{channel}".encode("utf-8")
            ).hexdigest()
            clips.append(
                MidiClip(
                    title=title,
                    tempo_map=tempo_map,
                    time_signature=time_signature,
                    instrument=Instrument(instrument_role, program, channel, instrument_suggestions),
                    notes=tuple(clip_notes),
                    key=key_signature,
                    chords=tuple(chords),
                    provenance=Provenance(
                        source_uri=str(path.resolve()), converter="sunofriend.midi-import"
                    ),
                    clip_id=clip_id,
                )
            )
    return tuple(clips)


def read_midi_clip(
    path: str | Path,
    *,
    track_index: int = 0,
    key: KeySignature | str | None = None,
    role: str | None = None,
    suggestions: Iterable[str] = (),
) -> MidiClip:
    clips = read_midi_clips(path, key=key, role=role, suggestions=suggestions)
    if not clips:
        raise ValueError(f"No notes found in MIDI file: {path}")
    try:
        return clips[track_index]
    except IndexError as exc:
        raise IndexError(f"MIDI contains {len(clips)} note-bearing tracks/channels") from exc


def _parse_track(
    data: bytes, *, max_note_ons: int | None = None
) -> tuple[_ParsedTrack, dict[str, Any]]:
    position = 0
    tick = 0
    running_status: int | None = None
    name = ""
    programs: dict[int, int] = {}
    chords: list[tuple[int, str]] = []
    notes: list[tuple[int, int, int, int, int, int]] = []
    active: dict[tuple[int, int], list[tuple[int, int]]] = {}
    tempos: list[tuple[int, float]] = []
    signatures: list[tuple[int, TimeSignature]] = []
    keys: list[tuple[int, KeySignature]] = []
    note_on_count = 0

    while position < len(data):
        delta, position = _read_varlen(data, position)
        tick += delta
        if position >= len(data):
            raise ValueError("Truncated MIDI event")
        status_byte = data[position]
        if status_byte & 0x80:
            status = status_byte
            position += 1
            if status < 0xF0:
                running_status = status
        else:
            if running_status is None:
                raise ValueError("MIDI running status used before a status byte")
            status = running_status

        if status == 0xFF:
            if position >= len(data):
                raise ValueError("Truncated MIDI meta event")
            kind = data[position]
            position += 1
            length, position = _read_varlen(data, position)
            payload = data[position:position + length]
            if len(payload) != length:
                raise ValueError("Truncated MIDI meta payload")
            position += length
            if kind == 0x03:
                name = payload.decode("utf-8", errors="replace")
            elif kind == 0x06:
                chords.append((tick, payload.decode("utf-8", errors="replace")))
            elif kind == 0x51 and length == 3:
                micros = int.from_bytes(payload, "big")
                if micros:
                    tempos.append((tick, 60_000_000.0 / micros))
            elif kind == 0x58 and length >= 2:
                signatures.append((tick, TimeSignature(payload[0], 2 ** payload[1])))
            elif kind == 0x59 and length >= 2:
                sf = payload[0] - 256 if payload[0] > 127 else payload[0]
                keys.append((tick, _key_from_midi(sf, bool(payload[1]))))
            if kind == 0x2F:
                break
            continue
        if status in {0xF0, 0xF7}:
            length, position = _read_varlen(data, position)
            position += length
            if position > len(data):
                raise ValueError("Truncated MIDI SysEx event")
            continue
        if status >= 0xF0:
            lengths = {0xF1: 1, 0xF2: 2, 0xF3: 1, 0xF6: 0, 0xF8: 0, 0xFA: 0, 0xFB: 0, 0xFC: 0, 0xFE: 0}
            if status not in lengths:
                raise ValueError(f"Unsupported MIDI system event 0x{status:02x}")
            position += lengths[status]
            continue

        event_type = status & 0xF0
        channel = status & 0x0F
        length = 1 if event_type in {0xC0, 0xD0} else 2
        payload = data[position:position + length]
        if len(payload) != length:
            raise ValueError("Truncated MIDI channel event")
        position += length
        if event_type == 0xC0:
            programs.setdefault(channel, payload[0])
        elif event_type == 0x90 and payload[1] > 0:
            note_on_count += 1
            if max_note_ons is not None and note_on_count > max_note_ons:
                raise MidiNoteLimitError(max(0, max_note_ons))
            active.setdefault((channel, payload[0]), []).append((tick, payload[1]))
        elif event_type == 0x80 or (event_type == 0x90 and payload[1] == 0):
            stack = active.get((channel, payload[0]))
            if stack:
                start_tick, velocity = stack.pop(0)
                if tick > start_tick:
                    notes.append((start_tick, tick, channel, payload[0], velocity, payload[1]))

    notes.sort(key=lambda item: (item[0], item[3], item[1], item[2]))
    return _ParsedTrack(name, programs, notes, chords), {
        "tempos": tempos,
        "signatures": signatures,
        "keys": keys,
        "note_on_count": note_on_count,
    }


def _tempo_map_from_midi(events: Sequence[tuple[int, float]], ticks_per_beat: int) -> TempoMap:
    by_tick: dict[int, float] = {}
    for tick, bpm in events:
        by_tick[tick] = bpm
    if 0 not in by_tick:
        by_tick[0] = 120.0
    points = tuple(TempoPoint(tick / ticks_per_beat, bpm) for tick, bpm in sorted(by_tick.items()))
    return TempoMap(points)


def _key_from_midi(sf: int, minor: bool) -> KeySignature:
    sf = max(-7, min(7, sf))
    major = ("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#")
    minor_names = ("Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#")
    return KeySignature((minor_names if minor else major)[sf + 7], "minor" if minor else "major")


def _read_varlen(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if position >= len(data):
            raise ValueError("Truncated MIDI variable-length value")
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position
    raise ValueError("MIDI variable-length value is too long")


def _infer_role(title: str) -> str:
    lower = title.lower()
    for role in (
        "bass", "drums", "piano", "keys", "synth", "guitar", "strings",
        "pad", "lead", "organ", "brass", "wind", "vocal",
    ):
        if role in lower:
            return role
    return "instrument"


def _infer_suggestions(title: str, role: str) -> tuple[str, ...]:
    lower = title.lower()
    if role == "drums":
        return ("Modern 909", "Electronic Drum Kit")
    suggestions = {
        "bass": ("Upright Jazz Bass", "Sub Bass"),
        "keys": ("Different Phases Clav", "Grand Piano"),
        "piano": ("Grand Piano", "Electric Piano"),
        "pad": ("Warm Pad", "Strings"),
        "strings": ("Strings", "Warm Pad"),
        "lead": ("Flow Synth Lead", "Synth Lead"),
        "synth": ("Flow Synth Pluck", "Synth Lead"),
    }
    if "other_kit" in lower:
        return ("Modern 909", "Electronic Drum Kit")
    return suggestions.get(role, ())


__all__ = [
    "SCHEMA_VERSION",
    "ChordEvent",
    "ClipNote",
    "Instrument",
    "KeySignature",
    "MidiNoteLimitError",
    "MidiClip",
    "Provenance",
    "TempoMap",
    "TempoPoint",
    "TimeSignature",
    "TransformRecipe",
    "WarpPoint",
    "normalize_note_name",
    "note_name_for_pc",
    "pitch_class",
    "read_midi_clip",
    "read_midi_clips",
    "resolve_export_timing",
    "write_clip_midi",
]
