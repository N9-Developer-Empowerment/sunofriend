from __future__ import annotations

import dataclasses
import hashlib
import math
import struct
import wave
from pathlib import Path

import pytest

import sunofriend.separation_quality as separation_quality
from sunofriend.separation_contract import (
    SEPARATION_RESIDUAL_DEFINITION,
)
from sunofriend.separation_quality import (
    RECONSTRUCTION_THRESHOLD_POLICY,
    evaluate_target_residual_reconstruction,
    inspect_pcm_wav,
)


def _pcm_bytes(samples: list[int], sample_width_bytes: int) -> bytes:
    if sample_width_bytes == 1:
        return bytes(samples)
    if sample_width_bytes == 2:
        return struct.pack(f"<{len(samples)}h", *samples)
    if sample_width_bytes == 3:
        return b"".join(
            value.to_bytes(3, "little", signed=True) for value in samples
        )
    if sample_width_bytes == 4:
        return struct.pack(f"<{len(samples)}i", *samples)
    raise AssertionError("test helper received an unsupported sample width")


def _write_pcm_wav(
    path: Path,
    samples: list[int],
    *,
    sample_width_bytes: int = 2,
    channels: int = 1,
    sample_rate: int = 8_000,
) -> Path:
    assert samples
    assert len(samples) % channels == 0
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width_bytes)
        writer.setframerate(sample_rate)
        writer.writeframes(_pcm_bytes(samples, sample_width_bytes))
    return path


def _write_extensible_pcm_wav(
    path: Path,
    samples: list[int],
    *,
    sample_width_bytes: int,
    channels: int,
    sample_rate: int,
) -> Path:
    """Write a real WAVE_FORMAT_EXTENSIBLE packed integer-PCM fixture."""

    assert samples
    assert sample_width_bytes in {2, 3}
    assert channels in {1, 2}
    assert len(samples) % channels == 0
    data = _pcm_bytes(samples, sample_width_bytes)
    block_align = channels * sample_width_bytes
    bits_per_sample = sample_width_bytes * 8
    pcm_subformat = bytes.fromhex("0100000000001000800000aa00389b71")
    channel_mask = 0x4 if channels == 1 else 0x3
    format_data = (
        struct.pack(
            "<HHIIHHH",
            0xFFFE,
            channels,
            sample_rate,
            sample_rate * block_align,
            block_align,
            bits_per_sample,
            22,
        )
        + struct.pack("<HI", bits_per_sample, channel_mask)
        + pcm_subformat
    )
    format_chunk = (
        b"fmt " + struct.pack("<I", len(format_data)) + format_data
    )
    data_chunk = b"data" + struct.pack("<I", len(data)) + data
    if len(data) % 2:
        data_chunk += b"\x00"
    riff_payload = b"WAVE" + format_chunk + data_chunk
    path.write_bytes(
        b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload
    )
    return path


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_inspect_pcm16_is_immutable_and_builds_contract_artifacts(
    tmp_path: Path,
) -> None:
    source = _write_pcm_wav(
        tmp_path / "source.wav",
        [0, 16_384, -32_768, 32_767],
    )

    inspection = inspect_pcm_wav(source)

    assert inspection.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert inspection.geometry.to_dict() == {
        "sample_rate": 8_000,
        "channels": 1,
        "frames": 4,
        "duration_seconds": 0.0005,
    }
    assert inspection.sample_width_bytes == 2
    assert inspection.peak == 1.0
    assert inspection.rms == pytest.approx(
        math.sqrt(
            0**2 + 16_384**2 + (-32_768) ** 2 + 32_767**2
        )
        / 2
        / 32_768
    )
    assert inspection.silence_fraction == 0.25
    assert inspection.clipped_samples == 2
    assert all(
        math.isfinite(value)
        for value in (
            inspection.peak,
            inspection.rms,
            inspection.silence_fraction,
        )
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        inspection.peak = 0.0  # type: ignore[misc]

    target_artifact = inspection.to_artifact_dict(
        "bass",
        "STEMS/bass-target.wav",
    )
    assert target_artifact == {
        "role": "bass",
        "path": "STEMS/bass-target.wav",
        "sha256": inspection.sha256,
        "geometry": inspection.geometry.to_dict(),
        "peak": inspection.peak,
        "rms": inspection.rms,
        "silence_fraction": inspection.silence_fraction,
        "clipped_samples": inspection.clipped_samples,
    }
    residual_artifact = inspection.to_artifact_dict(
        "bass",
        "STEMS/bass-residual.wav",
        "a" * 64,
    )
    assert residual_artifact["target_sha256"] == "a" * 64
    assert (
        residual_artifact["definition"]
        == SEPARATION_RESIDUAL_DEFINITION
    )


def test_inspect_pcm24_stereo_has_exact_geometry_and_finite_metrics(
    tmp_path: Path,
) -> None:
    samples = [0, 4_194_304, -8_388_608, 8_388_607, 12_345, -54_321]
    source = _write_pcm_wav(
        tmp_path / "stereo-24.wav",
        samples,
        sample_width_bytes=3,
        channels=2,
        sample_rate=48_000,
    )

    inspection = inspect_pcm_wav(source)

    assert inspection.geometry.sample_rate == 48_000
    assert inspection.geometry.channels == 2
    assert inspection.geometry.frames == 3
    assert inspection.geometry.duration_seconds == 3 / 48_000
    assert inspection.sample_width_bytes == 3
    assert inspection.peak == 1.0
    assert inspection.rms == pytest.approx(
        math.sqrt(sum(value * value for value in samples) / len(samples))
        / 8_388_608
    )
    assert inspection.silence_fraction == 1 / 6
    assert inspection.clipped_samples == 2
    assert all(
        math.isfinite(value)
        for value in (
            inspection.peak,
            inspection.rms,
            inspection.silence_fraction,
        )
    )


def test_inspect_classic_pcm24_mono_accepts_terminal_odd_data_chunk(
    tmp_path: Path,
) -> None:
    source = _write_pcm_wav(
        tmp_path / "classic-mono-24.wav",
        [123_456],
        sample_width_bytes=3,
        channels=1,
        sample_rate=8_000,
    )
    # Python 3.9's wave writer leaves a terminal odd-sized PCM chunk
    # unpadded, so this is an important compatibility fixture.
    assert len(source.read_bytes()) % 2 == 1

    inspection = inspect_pcm_wav(source)

    assert inspection.geometry.frames == 1
    assert inspection.geometry.channels == 1
    assert inspection.sample_width_bytes == 3
    assert inspection.peak == 123_456 / 8_388_608


@pytest.mark.parametrize(
    ("sample_width_bytes", "channels", "samples"),
    [
        (2, 1, [0, 16_384, -32_768, 32_767]),
        (
            3,
            2,
            [0, 4_194_304, -8_388_608, 8_388_607, 12_345, -54_321],
        ),
    ],
)
def test_inspect_real_wave_format_extensible_pcm16_and_pcm24(
    tmp_path: Path,
    sample_width_bytes: int,
    channels: int,
    samples: list[int],
) -> None:
    source = _write_extensible_pcm_wav(
        tmp_path / f"extensible-{sample_width_bytes}-{channels}.wav",
        samples,
        sample_width_bytes=sample_width_bytes,
        channels=channels,
        sample_rate=48_000,
    )
    assert source.read_bytes()[20:22] == b"\xfe\xff"

    inspection = inspect_pcm_wav(source)

    assert inspection.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert inspection.geometry.sample_rate == 48_000
    assert inspection.geometry.channels == channels
    assert inspection.geometry.frames == len(samples) // channels
    assert inspection.sample_width_bytes == sample_width_bytes
    scale = 1 << (8 * sample_width_bytes - 1)
    assert inspection.peak == max(abs(value) for value in samples) / scale
    assert inspection.rms == pytest.approx(
        math.sqrt(sum(value * value for value in samples) / len(samples))
        / scale
    )


def test_exact_target_plus_residual_reconstruction_passes(
    tmp_path: Path,
) -> None:
    source = _write_pcm_wav(
        tmp_path / "source.wav",
        [1_000, -1_000, 32_767, -32_768],
    )
    target = _write_pcm_wav(
        tmp_path / "target.wav",
        [400, -600, 16_000, -16_000],
    )
    residual = _write_pcm_wav(
        tmp_path / "residual.wav",
        [600, -400, 16_767, -16_768],
    )

    result = evaluate_target_residual_reconstruction(
        source,
        [("bass", target, residual)],
    )

    assert result.maximum_absolute_error == 0.0
    assert result.rms_error == 0.0
    assert result.threshold == 2 / 32_768
    assert result.passed is True
    assert len(result.per_role) == 1
    evidence = result.per_role[0]
    assert evidence.role == "bass"
    assert evidence.maximum_absolute_error == 0.0
    assert evidence.rms_error == 0.0
    assert evidence.threshold == 2 / 32_768
    assert evidence.passed is True
    assert evidence.samples_compared == 4
    assert evidence.quantization_step == 1 / 32_768
    assert evidence.threshold_policy == RECONSTRUCTION_THRESHOLD_POLICY
    assert evidence.source_sha256 == inspect_pcm_wav(source).sha256
    assert evidence.target_sha256 == inspect_pcm_wav(target).sha256
    assert evidence.residual_sha256 == inspect_pcm_wav(residual).sha256
    assert evidence.geometry == inspect_pcm_wav(source).geometry
    assert evidence.sample_width_bytes == 2
    document = result.to_dict()
    assert document["maximum_absolute_error"] == 0.0
    assert document["rms_error"] == 0.0
    assert document["threshold"] == 2 / 32_768
    assert document["passed"] is True
    assert document["per_role"]["bass"] == evidence.to_dict()
    assert "leakage" not in document


def test_extensible_stereo_pcm24_reconstruction_binds_exact_samples(
    tmp_path: Path,
) -> None:
    source_samples = [
        1_000_000,
        -1_000_000,
        8_388_607,
        -8_388_608,
        123_456,
        -654_321,
    ]
    target_samples = [
        400_000,
        -600_000,
        4_000_000,
        -4_000_000,
        100_000,
        -600_000,
    ]
    residual_samples = [
        source - target
        for source, target in zip(source_samples, target_samples)
    ]
    source = _write_extensible_pcm_wav(
        tmp_path / "source-extensible.wav",
        source_samples,
        sample_width_bytes=3,
        channels=2,
        sample_rate=48_000,
    )
    target = _write_extensible_pcm_wav(
        tmp_path / "target-extensible.wav",
        target_samples,
        sample_width_bytes=3,
        channels=2,
        sample_rate=48_000,
    )
    residual = _write_extensible_pcm_wav(
        tmp_path / "residual-extensible.wav",
        residual_samples,
        sample_width_bytes=3,
        channels=2,
        sample_rate=48_000,
    )

    result = evaluate_target_residual_reconstruction(
        source,
        [("bass", target, residual)],
    )

    assert result.maximum_absolute_error == 0.0
    assert result.rms_error == 0.0
    assert result.threshold == 2 / 8_388_608
    assert result.passed is True
    assert result.per_role[0].samples_compared == len(source_samples)
    assert result.per_role[0].sample_width_bytes == 3
    assert result.per_role[0].geometry.channels == 2
    assert result.per_role[0].source_sha256 == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


def test_quantization_threshold_is_explicit_and_aggregate_is_conservative(
    tmp_path: Path,
) -> None:
    source = _write_pcm_wav(tmp_path / "source.wav", [100, -100, 0])
    target = _write_pcm_wav(tmp_path / "target.wav", [100, -100, 0])
    two_step_residual = _write_pcm_wav(
        tmp_path / "two-step.wav",
        [-2, -2, -2],
    )
    three_step_residual = _write_pcm_wav(
        tmp_path / "three-step.wav",
        [-3, -3, -3],
    )

    result = evaluate_target_residual_reconstruction(
        source,
        [
            ("keys", target, two_step_residual),
            ("bass", target, three_step_residual),
        ],
    )

    assert [item.role for item in result.per_role] == ["bass", "keys"]
    assert result.per_role[0].maximum_absolute_error == 3 / 32_768
    assert result.per_role[0].passed is False
    assert result.per_role[1].maximum_absolute_error == 2 / 32_768
    assert result.per_role[1].passed is True
    assert result.maximum_absolute_error == 3 / 32_768
    assert result.rms_error == pytest.approx(
        math.sqrt((3 * 3**2 + 3 * 2**2) / 6) / 32_768
    )
    assert result.threshold == 2 / 32_768
    assert result.passed is False
    assert "quantization" in result.per_role[0].threshold_policy


@pytest.mark.parametrize(
    ("target_options", "match"),
    [
        ({"sample_rate": 16_000}, "geometry"),
        ({"channels": 2}, "geometry"),
        ({"samples": [1, 2]}, "geometry"),
        ({"sample_width_bytes": 3}, "sample width"),
    ],
)
def test_reconstruction_requires_exact_geometry_and_sample_width(
    tmp_path: Path,
    target_options: dict,
    match: str,
) -> None:
    source = _write_pcm_wav(tmp_path / "source.wav", [1, 2, 3, 4])
    options = {
        "samples": [1, 2, 3, 4],
        "sample_width_bytes": 2,
        "channels": 1,
        "sample_rate": 8_000,
    }
    options.update(target_options)
    target = _write_pcm_wav(tmp_path / "target.wav", **options)
    residual_samples = [0] * (
        len(options["samples"]) // options["channels"]
    )
    residual = _write_pcm_wav(
        tmp_path / "residual.wav",
        residual_samples,
        sample_width_bytes=options["sample_width_bytes"],
        channels=1,
        sample_rate=options["sample_rate"],
    )

    with pytest.raises(ValueError, match=match):
        evaluate_target_residual_reconstruction(
            source,
            [("bass", target, residual)],
        )


@pytest.mark.parametrize("sample_width_bytes", [1, 4])
def test_inspection_rejects_unsupported_pcm_widths(
    tmp_path: Path,
    sample_width_bytes: int,
) -> None:
    source = _write_pcm_wav(
        tmp_path / f"pcm-{sample_width_bytes}.wav",
        [0, 1],
        sample_width_bytes=sample_width_bytes,
    )

    with pytest.raises(ValueError, match="16-bit or 24-bit"):
        inspect_pcm_wav(source)


def test_inspection_rejects_malformed_compressed_truncated_and_unsafe_files(
    tmp_path: Path,
) -> None:
    random_file = tmp_path / "random.wav"
    random_file.write_bytes(b"not a wave file")
    with pytest.raises(ValueError, match="unsupported or malformed"):
        inspect_pcm_wav(random_file)

    float_tag = _write_pcm_wav(tmp_path / "float-tag.wav", [0, 1])
    contents = bytearray(float_tag.read_bytes())
    contents[20:22] = b"\x03\x00"
    float_tag.write_bytes(contents)
    with pytest.raises(ValueError, match="unsupported"):
        inspect_pcm_wav(float_tag)

    truncated = _write_pcm_wav(tmp_path / "truncated.wav", [1, 2, 3])
    truncated.write_bytes(truncated.read_bytes()[:-1])
    with pytest.raises(ValueError, match="incomplete|truncated"):
        inspect_pcm_wav(truncated)

    with pytest.raises(ValueError, match="regular file"):
        inspect_pcm_wav(tmp_path)

    empty = tmp_path / "empty.wav"
    empty.touch()
    with pytest.raises(ValueError, match="must not be empty"):
        inspect_pcm_wav(empty)

    target = _write_pcm_wav(tmp_path / "symlink-target.wav", [0, 1])
    link = tmp_path / "symlink.wav"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    with pytest.raises(ValueError, match="symbolic link"):
        inspect_pcm_wav(link)


def test_hard_file_frame_channel_and_sample_rate_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_pcm_wav(tmp_path / "source.wav", [1, 2, 3])

    monkeypatch.setattr(
        separation_quality,
        "MAX_PCM_WAV_FILE_BYTES",
        source.stat().st_size - 1,
    )
    with pytest.raises(ValueError, match="file-size bound"):
        inspect_pcm_wav(source)
    monkeypatch.setattr(
        separation_quality,
        "MAX_PCM_WAV_FILE_BYTES",
        2 * 1024**3,
    )

    monkeypatch.setattr(separation_quality, "MAX_PCM_WAV_FRAMES", 2)
    with pytest.raises(ValueError, match="frame count"):
        inspect_pcm_wav(source)
    monkeypatch.setattr(
        separation_quality,
        "MAX_PCM_WAV_FRAMES",
        100_000_000,
    )

    monkeypatch.setattr(
        separation_quality,
        "MAX_PCM_WAV_SAMPLE_RATE",
        7_999,
    )
    with pytest.raises(ValueError, match="sample rate"):
        inspect_pcm_wav(source)
    monkeypatch.setattr(
        separation_quality,
        "MAX_PCM_WAV_SAMPLE_RATE",
        768_000,
    )

    three_channel = _write_pcm_wav(
        tmp_path / "three-channel.wav",
        [0, 0, 0],
        channels=3,
    )
    with pytest.raises(ValueError, match="mono or stereo"):
        inspect_pcm_wav(three_channel)


def test_reconstruction_rejects_invalid_pair_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_pcm_wav(tmp_path / "source.wav", [0, 1])
    target = _write_pcm_wav(tmp_path / "target.wav", [0, 1])
    residual = _write_pcm_wav(tmp_path / "residual.wav", [0, 0])

    with pytest.raises(ValueError, match="pair count"):
        evaluate_target_residual_reconstruction(source, [])
    with pytest.raises(ValueError, match="triple"):
        evaluate_target_residual_reconstruction(
            source,
            [("bass", target)],  # type: ignore[list-item]
        )
    with pytest.raises(ValueError, match="prepared canonical"):
        evaluate_target_residual_reconstruction(
            source,
            [("Bass", target, residual)],
        )
    for invalid_role in ("pads", "mix", "unclassified", "not_a_role"):
        with pytest.raises(ValueError, match="prepared canonical"):
            evaluate_target_residual_reconstruction(
                source,
                [(invalid_role, target, residual)],
            )
    with pytest.raises(ValueError, match="unique"):
        evaluate_target_residual_reconstruction(
            source,
            [
                ("bass", target, residual),
                ("bass", target, residual),
            ],
        )
    monkeypatch.setattr(separation_quality, "MAX_RECONSTRUCTION_ROLES", 1)
    with pytest.raises(ValueError, match="pair count"):
        evaluate_target_residual_reconstruction(
            source,
            [
                ("bass", target, residual),
                ("drums", target, residual),
            ],
        )


def test_artifact_validation_rejects_unsafe_paths_and_invalid_hashes(
    tmp_path: Path,
) -> None:
    inspection = inspect_pcm_wav(
        _write_pcm_wav(tmp_path / "source.wav", [0, 1])
    )

    unsafe_paths = (
        "../private.wav",
        " STEMS/bass.wav",
        "STEMS/bass.wav ",
        r"STEMS\bass.wav",
        "STEMS//bass.wav",
        "STEMS/./bass.wav",
        "STEMS/../bass.wav",
        "STEMS/~/bass.wav",
        "STEMS/cafe\u0301.wav",
        "https://example.invalid/bass.wav",
    )
    for unsafe_path in unsafe_paths:
        with pytest.raises(ValueError, match="safe relative WAV"):
            inspection.to_artifact_dict("bass", unsafe_path)
    with pytest.raises(ValueError, match="prepared canonical"):
        inspection.to_artifact_dict("Bass", "STEMS/bass.wav")
    with pytest.raises(ValueError, match="prepared canonical"):
        inspection.to_artifact_dict("pads", "STEMS/pads.wav")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        inspection.to_artifact_dict(
            "bass",
            "STEMS/bass.wav",
            "A" * 64,
        )


def test_reconstruction_rejects_path_replacement_after_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_pcm_wav(tmp_path / "source.wav", [100, -100, 0])
    target = _write_pcm_wav(tmp_path / "target.wav", [40, -60, 0])
    residual = _write_pcm_wav(tmp_path / "residual.wav", [60, -40, 0])
    replacement = _write_pcm_wav(
        tmp_path / "replacement.wav",
        [999, 999, 999],
    )
    original_target_hash = hashlib.sha256(target.read_bytes()).hexdigest()

    def replace_target_path() -> None:
        replacement.replace(target)

    monkeypatch.setattr(
        separation_quality,
        "_after_reconstruction_inputs_inspected",
        replace_target_path,
    )

    with pytest.raises(ValueError, match="changed or was replaced"):
        evaluate_target_residual_reconstruction(
            source,
            [("bass", target, residual)],
        )
    assert hashlib.sha256(target.read_bytes()).hexdigest() != original_target_hash


def test_inspection_and_reconstruction_do_not_persist_or_mutate_files(
    tmp_path: Path,
) -> None:
    source = _write_pcm_wav(tmp_path / "source.wav", [100, -100, 0])
    target = _write_pcm_wav(tmp_path / "target.wav", [40, -60, 0])
    residual = _write_pcm_wav(
        tmp_path / "residual.wav",
        [60, -40, 0],
    )
    before = _tree_bytes(tmp_path)

    inspect_pcm_wav(source)
    evaluate_target_residual_reconstruction(
        source,
        [("bass", target, residual)],
    )

    assert _tree_bytes(tmp_path) == before
