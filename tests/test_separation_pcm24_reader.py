from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

from sunofriend.separation_demucs_mlx_worker import (
    PCM24_SCALE,
    pack_pcm24,
    read_canonical_source,
)


PCM_SUBFORMAT_GUID = bytes.fromhex("0100000000001000800000aa00389b71")
FLOAT_SUBFORMAT_GUID = bytes.fromhex("0300000000001000800000aa00389b71")


def _write_extensible_pcm24(
    path: Path,
    samples: np.ndarray,
    *,
    sample_rate: int = 44_100,
    channels: int = 2,
    block_align: Optional[int] = None,
    valid_bits: int = 24,
    subformat: bytes = PCM_SUBFORMAT_GUID,
) -> Path:
    payload = pack_pcm24(samples, np=np)
    encoded_block_align = block_align if block_align is not None else channels * 3
    format_data = (
        struct.pack(
            "<HHIIHHH",
            0xFFFE,
            channels,
            sample_rate,
            sample_rate * encoded_block_align,
            encoded_block_align,
            24,
            22,
        )
        + struct.pack("<HI", valid_bits, 0x3 if channels == 2 else 0x4)
        + subformat
    )
    # The odd-sized JUNK chunk exercises RIFF padding used by real encoders.
    junk_chunk = b"JUNK" + struct.pack("<I", 3) + b"abc\x00"
    format_chunk = b"fmt " + struct.pack("<I", len(format_data)) + format_data
    data_chunk = b"data" + struct.pack("<I", len(payload)) + payload
    if len(payload) % 2:
        data_chunk += b"\x00"
    riff_payload = b"WAVE" + junk_chunk + format_chunk + data_chunk
    path.write_bytes(b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload)
    return path


def test_reader_accepts_exact_extensible_pcm24_with_extra_chunk(
    tmp_path: Path,
) -> None:
    samples = np.array(
        [
            [-8_388_608, 8_388_607],
            [-1, 0],
            [1, -4_194_304],
            [1_234_567, -7_654_321],
        ],
        dtype=np.int32,
    )
    source = _write_extensible_pcm24(tmp_path / "extensible.wav", samples)

    decoded = read_canonical_source(source, np=np)

    restored = np.rint(decoded * PCM24_SCALE).astype(np.int32)
    np.testing.assert_array_equal(restored, samples)


def test_reader_keeps_classic_pcm24_compatibility(tmp_path: Path) -> None:
    samples = np.array([[0, 1], [-1, 2_000_000]], dtype=np.int32)
    source = tmp_path / "classic.wav"
    with wave.open(str(source), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(pack_pcm24(samples, np=np))

    decoded = read_canonical_source(source, np=np)

    np.testing.assert_array_equal(
        np.rint(decoded * PCM24_SCALE).astype(np.int32), samples
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"subformat": FLOAT_SUBFORMAT_GUID}, "subformat"),
        ({"valid_bits": 20}, "valid bits"),
        ({"sample_rate": 48_000}, "44.1 kHz"),
        ({"channels": 1}, "stereo"),
        ({"block_align": 5}, "block alignment"),
    ],
)
def test_reader_rejects_noncanonical_extensible_sources(
    tmp_path: Path,
    changes: dict[str, object],
    message: str,
) -> None:
    samples = np.array([[0, 1], [-1, 2]], dtype=np.int32)
    source = _write_extensible_pcm24(tmp_path / "invalid.wav", samples, **changes)

    with pytest.raises(ValueError, match=message):
        read_canonical_source(source, np=np)


def test_reader_rejects_truncated_extensible_payload(tmp_path: Path) -> None:
    samples = np.array([[0, 1], [-1, 2]], dtype=np.int32)
    source = _write_extensible_pcm24(tmp_path / "truncated.wav", samples)
    source.write_bytes(source.read_bytes()[:-1])

    with pytest.raises(ValueError, match="truncated"):
        read_canonical_source(source, np=np)
