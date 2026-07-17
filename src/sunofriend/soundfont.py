"""Write small, self-contained SoundFont 2 instruments.

Sample Pack v2 and explicitly reviewed Sample Instrument v3 experiments use
SF2 as their direct GarageBand handoff. Apple's sampler can load SF2 banks, the
samples travel inside one file, and FluidSynth can validate and audition the
same artifact without automating GarageBand's private patch format.

The writer intentionally implements a narrow SoundFont 2.01 subset: one bank,
one preset, one instrument, mono PCM16 samples, key/velocity zones, optional
forward loops, and per-sample root-key/tuning metadata.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class SoundFontZone:
    sample_path: Path
    root_key: int
    low_key: int
    high_key: int
    low_velocity: int = 0
    high_velocity: int = 127
    pitch_correction_cents: int = 0
    loop_start: int | None = None
    loop_end: int | None = None

    def validate(self) -> None:
        if not self.sample_path.is_file():
            raise ValueError(f"SoundFont sample not found: {self.sample_path}")
        for name, value in (
            ("root_key", self.root_key),
            ("low_key", self.low_key),
            ("high_key", self.high_key),
            ("low_velocity", self.low_velocity),
            ("high_velocity", self.high_velocity),
        ):
            if not isinstance(value, int) or not 0 <= value <= 127:
                raise ValueError(f"{name} must be an integer from 0 to 127")
        if self.low_key > self.high_key:
            raise ValueError("low_key cannot exceed high_key")
        if self.low_velocity > self.high_velocity:
            raise ValueError("low_velocity cannot exceed high_velocity")
        if not -99 <= self.pitch_correction_cents <= 99:
            raise ValueError("pitch_correction_cents must be from -99 to 99")
        if (self.loop_start is None) != (self.loop_end is None):
            raise ValueError("loop_start and loop_end must be supplied together")
        if self.loop_start is not None and (
            self.loop_start < 0 or self.loop_end <= self.loop_start
        ):
            raise ValueError("SoundFont loop points must define a positive range")


@dataclass(frozen=True)
class SoundFontSummary:
    path: str
    name: str
    preset: int
    bank: int
    zone_count: int
    sample_frames: int
    sample_rates: tuple[int, ...]
    looped_zone_count: int
    byte_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "preset": self.preset,
            "bank": self.bank,
            "zone_count": self.zone_count,
            "sample_frames": self.sample_frames,
            "sample_rates": list(self.sample_rates),
            "looped_zone_count": self.looped_zone_count,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True)
class _SampleRecord:
    name: str
    pcm: bytes
    frames: int
    sample_rate: int
    start: int
    end: int
    loop_start: int
    loop_end: int
    original_pitch: int
    pitch_correction: int
    looped: bool


def write_soundfont(
    path: str | Path,
    zones: Sequence[SoundFontZone],
    *,
    name: str,
    preset: int = 0,
    bank: int = 0,
    software: str = "Sunofriend Sample Instrument v2",
) -> SoundFontSummary:
    """Write and structurally validate a one-instrument SoundFont 2.01 bank."""

    output = Path(path)
    if not zones:
        raise ValueError("At least one SoundFont zone is required")
    if not isinstance(preset, int) or not 0 <= preset <= 127:
        raise ValueError("preset must be an integer from 0 to 127")
    if not isinstance(bank, int) or not 0 <= bank <= 128:
        raise ValueError("bank must be an integer from 0 to 128")
    display_name = _display_name(name)
    records: list[_SampleRecord] = []
    sample_cursor = 0
    for index, zone in enumerate(zones, 1):
        zone.validate()
        pcm, frames, sample_rate = _read_pcm16_mono(zone.sample_path)
        if frames < 32:
            raise ValueError(f"SoundFont sample is too short: {zone.sample_path}")
        if zone.loop_start is not None and zone.loop_end > frames:
            raise ValueError(
                f"Loop exceeds sample length ({frames} frames): {zone.sample_path}"
            )
        start = sample_cursor
        end = start + frames
        looped = zone.loop_start is not None
        # Loop headers must still describe a valid interior range even when the
        # zone does not enable looping. Keeping eight frames on both sides also
        # satisfies stricter SoundFont readers such as Apple's DLS bank parser.
        loop_start = start + (zone.loop_start if looped else 8)
        loop_end = start + (zone.loop_end if looped else frames - 8)
        records.append(
            _SampleRecord(
                name=_sample_name(zone.sample_path, index),
                pcm=pcm,
                frames=frames,
                sample_rate=sample_rate,
                start=start,
                end=end,
                loop_start=loop_start,
                loop_end=loop_end,
                original_pitch=zone.root_key,
                pitch_correction=zone.pitch_correction_cents,
                looped=looped,
            )
        )
        # SoundFont 2 requires at least 46 zero sample data points after every
        # sample. Their positions are not included in the sample header range.
        sample_cursor = end + 46

    info = _list_chunk(
        b"INFO",
        [
            _chunk(b"ifil", struct.pack("<HH", 2, 1)),
            _chunk(b"isng", _info_string("EMU8000")),
            _chunk(b"INAM", _info_string(display_name)),
            _chunk(
                b"ICMT",
                _info_string(
                    "Generated locally from authorised source audio by Sunofriend"
                ),
            ),
            _chunk(b"ISFT", _info_string(software)),
        ],
    )
    sample_data = b"".join(record.pcm + (b"\x00\x00" * 46) for record in records)
    sdta = _list_chunk(b"sdta", [_chunk(b"smpl", sample_data)])
    pdta = _pdta_chunk(display_name, zones, records, preset=preset, bank=bank)
    payload = b"sfbk" + info + sdta + pdta
    binary = b"RIFF" + struct.pack("<I", len(payload)) + payload
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(binary)

    structure = inspect_soundfont(output)
    if structure["preset_count"] != 1 or structure["sample_count"] != len(zones):
        raise ValueError("Generated SoundFont failed its structural validation")
    return SoundFontSummary(
        path=str(output),
        name=display_name,
        preset=preset,
        bank=bank,
        zone_count=len(zones),
        sample_frames=sum(record.frames for record in records),
        sample_rates=tuple(sorted({record.sample_rate for record in records})),
        looped_zone_count=sum(record.looped for record in records),
        byte_size=output.stat().st_size,
    )


def inspect_soundfont(path: str | Path) -> dict[str, Any]:
    """Return structural counts from a SoundFont without loading sample data."""

    source = Path(path)
    data = source.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"sfbk":
        raise ValueError(f"Not a SoundFont RIFF bank: {source}")
    declared = struct.unpack_from("<I", data, 4)[0]
    if declared + 8 != len(data):
        raise ValueError("SoundFont RIFF length does not match the file size")
    lists = _top_level_lists(data[12:])
    missing_lists = {b"INFO", b"sdta", b"pdta"} - set(lists)
    if missing_lists:
        names = ", ".join(value.decode("ascii") for value in sorted(missing_lists))
        raise ValueError(f"SoundFont is missing required LIST sections: {names}")
    info_chunks = _child_chunks(lists[b"INFO"])
    for tag in (b"isng", b"INAM", b"ICMT", b"ISFT"):
        if tag in info_chunks and len(info_chunks[tag]) % 2:
            raise ValueError(
                f"SoundFont INFO string {tag.decode('ascii')} is not word-sized"
            )
    sdta_chunks = _child_chunks(lists[b"sdta"])
    if b"smpl" not in sdta_chunks or not sdta_chunks[b"smpl"]:
        raise ValueError("SoundFont has no PCM sample data")
    pdta_chunks = _child_chunks(lists[b"pdta"])
    required = {
        b"phdr",
        b"pbag",
        b"pmod",
        b"pgen",
        b"inst",
        b"ibag",
        b"imod",
        b"igen",
        b"shdr",
    }
    missing = required - set(pdta_chunks)
    if missing:
        names = ", ".join(value.decode("ascii") for value in sorted(missing))
        raise ValueError(f"SoundFont pdta is missing: {names}")
    record_sizes = {
        b"phdr": 38,
        b"pbag": 4,
        b"pmod": 10,
        b"pgen": 4,
        b"inst": 22,
        b"ibag": 4,
        b"imod": 10,
        b"igen": 4,
        b"shdr": 46,
    }
    for tag, size in record_sizes.items():
        if len(pdta_chunks[tag]) < size or len(pdta_chunks[tag]) % size:
            raise ValueError(
                f"SoundFont table {tag.decode('ascii')} has invalid record sizes"
            )
    for tag, size in ((b"pmod", 10), (b"pgen", 4), (b"imod", 10), (b"igen", 4)):
        if any(pdta_chunks[tag][-size:]):
            raise ValueError(
                f"SoundFont table {tag.decode('ascii')} has no zero terminal record"
            )
    if any(pdta_chunks[b"shdr"][-26:]):
        raise ValueError("SoundFont sample table has an invalid terminal record")
    preset_records = len(pdta_chunks[b"phdr"]) // 38
    sample_records = len(pdta_chunks[b"shdr"]) // 46
    if preset_records < 2 or sample_records < 2:
        raise ValueError("SoundFont is missing terminal preset or sample records")
    return {
        "path": str(source),
        "byte_size": len(data),
        "preset_count": preset_records - 1,
        "instrument_count": len(pdta_chunks[b"inst"]) // 22 - 1,
        "sample_count": sample_records - 1,
        "format": "SoundFont 2.01",
    }


def _pdta_chunk(
    name: str,
    zones: Sequence[SoundFontZone],
    records: Sequence[_SampleRecord],
    *,
    preset: int,
    bank: int,
) -> bytes:
    phdr = b"".join(
        [
            struct.pack(
                "<20sHHHIII",
                _fixed_name(name),
                preset,
                bank,
                0,
                0,
                0,
                0,
            ),
            struct.pack("<20sHHHIII", _fixed_name("EOP"), 0, 0, 1, 0, 0, 0),
        ]
    )
    pbag = struct.pack("<HHHH", 0, 0, 1, 0)
    pmod = b"\x00" * 10
    pgen = _generator(41, 0) + (b"\x00" * 4)  # instrument index + terminal

    inst = b"".join(
        [
            struct.pack("<20sH", _fixed_name(name), 0),
            struct.pack("<20sH", _fixed_name("EOI"), len(zones)),
        ]
    )
    ibag_rows = []
    igen_rows = []
    generator_index = 0
    for sample_index, (zone, record) in enumerate(zip(zones, records)):
        ibag_rows.append(struct.pack("<HH", generator_index, 0))
        zone_generators = [
            _range_generator(43, zone.low_key, zone.high_key),
            _range_generator(44, zone.low_velocity, zone.high_velocity),
            _generator(58, zone.root_key),  # overridingRootKey
        ]
        if record.looped:
            zone_generators.append(_generator(54, 1))  # continuous loop
        zone_generators.append(_generator(53, sample_index))  # sampleID must be last
        igen_rows.extend(zone_generators)
        generator_index += len(zone_generators)
    ibag_rows.append(struct.pack("<HH", generator_index, 0))
    imod = b"\x00" * 10
    igen_rows.append(b"\x00" * 4)  # required terminal generator record

    shdr_rows = []
    for record in records:
        shdr_rows.append(
            struct.pack(
                "<20sIIIIIBbHH",
                _fixed_name(record.name),
                record.start,
                record.end,
                record.loop_start,
                record.loop_end,
                record.sample_rate,
                record.original_pitch,
                record.pitch_correction,
                0,
                1,  # monoSample
            )
        )
    shdr_rows.append(
        struct.pack(
            "<20sIIIIIBbHH",
            _fixed_name("EOS"),
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
    )
    return _list_chunk(
        b"pdta",
        [
            _chunk(b"phdr", phdr),
            _chunk(b"pbag", pbag),
            _chunk(b"pmod", pmod),
            _chunk(b"pgen", pgen),
            _chunk(b"inst", inst),
            _chunk(b"ibag", b"".join(ibag_rows)),
            _chunk(b"imod", imod),
            _chunk(b"igen", b"".join(igen_rows)),
            _chunk(b"shdr", b"".join(shdr_rows)),
        ],
    )


def _read_pcm16_mono(path: Path) -> tuple[bytes, int, int]:
    import numpy as np
    import soundfile

    values, sample_rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    if not len(values):
        raise ValueError(f"Cannot put an empty sample in a SoundFont: {path}")
    mono = np.mean(values, axis=1, dtype=np.float32)
    mono = np.nan_to_num(mono, copy=False)
    pcm = np.round(np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2")
    return pcm.tobytes(), len(pcm), int(sample_rate)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    if len(tag) != 4:
        raise ValueError("RIFF chunk identifiers must contain four bytes")
    padding = b"\x00" if len(payload) % 2 else b""
    return tag + struct.pack("<I", len(payload)) + payload + padding


def _list_chunk(kind: bytes, chunks: Sequence[bytes]) -> bytes:
    return _chunk(b"LIST", kind + b"".join(chunks))


def _generator(operator: int, amount: int) -> bytes:
    return struct.pack("<HH", operator, amount & 0xFFFF)


def _range_generator(operator: int, low: int, high: int) -> bytes:
    return _generator(operator, low | (high << 8))


def _info_string(value: str) -> bytes:
    """Encode an INFO string as a null-terminated, word-sized payload."""

    payload = value.encode("ascii", errors="replace") + b"\x00"
    return payload + (b"\x00" if len(payload) % 2 else b"")


def _display_name(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("SoundFont name cannot be empty")
    ascii_name = cleaned.encode("ascii", errors="replace").decode("ascii")
    return ascii_name[:19]


def _fixed_name(value: str) -> bytes:
    return value.encode("ascii", errors="replace")[:20].ljust(20, b"\x00")


def _sample_name(path: Path, index: int) -> str:
    token = path.stem.encode("ascii", errors="ignore").decode("ascii")
    token = "".join(character if character.isalnum() else "_" for character in token)
    return (token or f"sample_{index}")[:20]


def _top_level_lists(payload: bytes) -> dict[bytes, bytes]:
    result = {}
    for tag, value in _iter_chunks(payload):
        if tag == b"LIST" and len(value) >= 4:
            result[value[:4]] = value[4:]
    return result


def _child_chunks(payload: bytes) -> dict[bytes, bytes]:
    return {tag: value for tag, value in _iter_chunks(payload)}


def _iter_chunks(payload: bytes):
    offset = 0
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("Truncated RIFF chunk header")
        tag = payload[offset : offset + 4]
        size = struct.unpack_from("<I", payload, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(payload):
            raise ValueError("Truncated RIFF chunk payload")
        yield tag, payload[start:end]
        offset = end + (size % 2)
    if offset != len(payload):
        raise ValueError("Invalid RIFF padding")


__all__ = [
    "SoundFontSummary",
    "SoundFontZone",
    "inspect_soundfont",
    "write_soundfont",
]
