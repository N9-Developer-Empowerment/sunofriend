from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import struct
import wave

import numpy as np
import pytest

import sunofriend._private_verified_audio_inputs as verified_inputs


def _pack_pcm24(samples: list[int]) -> bytes:
    return b"".join(value.to_bytes(3, "little", signed=True) for value in samples)


def _write_pcm24(path: Path, samples: list[int], *, extensible: bool) -> None:
    if extensible:
        data = _pack_pcm24(samples)
        channels = 2
        sample_width = 3
        sample_rate = 44_100
        block_align = channels * sample_width
        bits_per_sample = sample_width * 8
        pcm_subformat = bytes.fromhex("0100000000001000800000aa00389b71")
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
            + struct.pack("<HI", bits_per_sample, 0x3)
            + pcm_subformat
        )
        chunks = (
            b"fmt "
            + struct.pack("<I", len(format_data))
            + format_data
            + b"data"
            + struct.pack("<I", len(data))
            + data
        )
        riff_payload = b"WAVE" + chunks
        path.write_bytes(
            b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload
        )
    else:
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(3)
            writer.setframerate(44_100)
            writer.writeframes(_pack_pcm24(samples))
    path.chmod(0o600)


def _private_path(tmp_path: Path, name: str) -> tuple[Path, Path, str]:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    first = root / "TEMP"
    first.mkdir(mode=0o700)
    parent = first / "case"
    parent.mkdir(mode=0o700)
    relative = f"TEMP/case/{name}"
    return root, parent / name, relative


def _file_identity(path: Path, relative_path: str, frames: int) -> dict[str, object]:
    details = path.stat()
    return {
        "relative_path": relative_path,
        "bytes": details.st_size,
        "device": details.st_dev,
        "inode": details.st_ino,
        "mtime_ns": details.st_mtime_ns,
        "ctime_ns": details.st_ctime_ns,
        "mode": stat.S_IMODE(details.st_mode),
        "expected_frames": frames,
        "expected_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _directory_identity(path: Path) -> dict[str, int]:
    details = path.stat()
    return {
        "device": details.st_dev,
        "inode": details.st_ino,
        "mode": stat.S_IMODE(details.st_mode),
        "uid": details.st_uid,
        "mtime_ns": details.st_mtime_ns,
        "ctime_ns": details.st_ctime_ns,
    }


def _directory_inventory(root: Path) -> dict[str, dict[str, int]]:
    return {
        ".": _directory_identity(root),
        "TEMP": _directory_identity(root / "TEMP"),
        "TEMP/case": _directory_identity(root / "TEMP/case"),
    }


@pytest.mark.parametrize("extensible", [False, True])
def test_pcm24_loads_classic_and_extensible_from_one_approved_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extensible: bool,
) -> None:
    root, path, relative = _private_path(tmp_path, "source.wav")
    integers = [-8_388_608, 8_388_607, -123_456, 123_456, -1, 1]
    _write_pcm24(path, integers, extensible=extensible)
    identity = _file_identity(path, relative, frames=3)
    directories = _directory_inventory(root)
    descriptor_ids: list[int] = []
    original_hash = verified_inputs._hash_and_rewind
    original_decode = verified_inputs._decode_pcm24_descriptor

    def record_hash(descriptor: int, expected_bytes: int) -> str:
        descriptor_ids.append(descriptor)
        return original_hash(descriptor, expected_bytes)

    def record_decode(descriptor: int, **kwargs: object) -> object:
        descriptor_ids.append(descriptor)
        return original_decode(descriptor, **kwargs)

    monkeypatch.setattr(verified_inputs, "_hash_and_rewind", record_hash)
    monkeypatch.setattr(verified_inputs, "_decode_pcm24_descriptor", record_decode)

    loaded = verified_inputs.load_verified_private_pcm24(
        root,
        identity,
        expected_directories=directories,
        np=np,
    )

    expected = np.asarray(integers, dtype=np.float64).reshape(3, 2) / 8_388_608
    assert np.array_equal(loaded.samples, expected)
    assert len(descriptor_ids) == 3
    assert len(set(descriptor_ids)) == 1
    assert loaded.receipt()["observed_file_identity"]["inode"] == path.stat().st_ino
    assert set(loaded.receipt()["observed_directory_identities"]) == {
        ".",
        "TEMP",
        "TEMP/case",
    }


def test_npy_hash_and_load_share_one_descriptor(tmp_path: Path) -> None:
    root, path, relative = _private_path(tmp_path, "guitar.npy")
    expected_samples = np.arange(12, dtype=np.float32).reshape(6, 2)
    with path.open("wb") as handle:
        np.save(handle, expected_samples, allow_pickle=False)
    path.chmod(0o600)
    identity = _file_identity(path, relative, frames=6)
    directories = _directory_inventory(root)
    descriptor_ids: list[int] = []

    class RecordingNumpy:
        ndarray = np.ndarray

        @staticmethod
        def dtype(value: object) -> np.dtype[object]:
            return np.dtype(value)

        @staticmethod
        def isfinite(value: object) -> np.ndarray:
            return np.isfinite(value)

        @staticmethod
        def load(handle: object, *, allow_pickle: bool) -> np.ndarray:
            descriptor_ids.append(handle.fileno())  # type: ignore[attr-defined]
            return np.load(handle, allow_pickle=allow_pickle)

    original_hash = verified_inputs._hash_and_rewind

    def record_hash(descriptor: int, expected_bytes: int) -> str:
        descriptor_ids.append(descriptor)
        return original_hash(descriptor, expected_bytes)

    verified_inputs._hash_and_rewind = record_hash
    try:
        loaded = verified_inputs.load_verified_private_float32_npy(
            root,
            identity,
            expected_directories=directories,
            np=RecordingNumpy,
        )
    finally:
        verified_inputs._hash_and_rewind = original_hash

    assert np.array_equal(loaded.samples, expected_samples)
    assert len(descriptor_ids) == 3
    assert len(set(descriptor_ids)) == 1


def test_verified_private_bytes_returns_exact_json_and_descriptor_hash(
    tmp_path: Path,
) -> None:
    root, path, relative = _private_path(tmp_path, "worker-result.json")
    document = {"status": "complete", "effects": {"model_loads": 1}}
    encoded = (
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    path.write_bytes(encoded)
    path.chmod(0o600)
    identity = _file_identity(path, relative, frames=1)
    directories = _directory_inventory(root)
    expected_sha256 = hashlib.sha256(encoded).hexdigest()

    loaded = verified_inputs.read_verified_private_bytes(
        root,
        identity,
        expected_directories=directories,
        expected_sha256=expected_sha256,
        maximum_bytes=1024,
    )

    assert loaded.data == encoded
    assert loaded.sha256 == hashlib.sha256(loaded.data).hexdigest()
    assert json.loads(loaded.data) == document
    assert loaded.receipt()["observed_file_identity"]["inode"] == path.stat().st_ino
    with pytest.raises(ValueError, match="SHA-256 differs"):
        verified_inputs.read_verified_private_bytes(
            root,
            identity,
            expected_directories=directories,
            expected_sha256="0" * 64,
            maximum_bytes=1024,
        )


def test_verified_private_bytes_rejects_leaf_swap_after_exact_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, path, relative = _private_path(tmp_path, "guitar.npy")
    approved = b"approval-bound-guitar-array"
    decoy = b"x" * len(approved)
    assert len(approved) == len(decoy)
    path.write_bytes(approved)
    path.chmod(0o600)
    decoy_path = tmp_path / "decoy.npy"
    decoy_path.write_bytes(decoy)
    decoy_path.chmod(0o600)
    identity = _file_identity(path, relative, frames=1)
    directories = _directory_inventory(root)
    moved = path.with_name("approved-held.npy")
    observed: list[bytes] = []
    original_read = verified_inputs._read_bytes_and_hash

    def read_then_swap(descriptor: int, expected_bytes: int) -> tuple[bytes, str]:
        data, digest = original_read(descriptor, expected_bytes)
        observed.append(data)
        path.rename(moved)
        decoy_path.rename(path)
        return data, digest

    monkeypatch.setattr(
        verified_inputs,
        "_read_bytes_and_hash",
        read_then_swap,
    )
    with pytest.raises(ValueError, match="descriptor changed|leaf attachment changed"):
        verified_inputs.read_verified_private_bytes(
            root,
            identity,
            expected_directories=directories,
            expected_sha256=hashlib.sha256(approved).hexdigest(),
        )

    assert observed == [approved]
    assert path.read_bytes() == decoy


def test_leaf_swap_cannot_change_npy_bytes_consumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, path, relative = _private_path(tmp_path, "synth.npy")
    approved_samples = np.ones((4, 2), dtype=np.float32)
    decoy_samples = np.full((4, 2), 99.0, dtype=np.float32)
    with path.open("wb") as handle:
        np.save(handle, approved_samples, allow_pickle=False)
    path.chmod(0o600)
    decoy = tmp_path / "decoy.npy"
    with decoy.open("wb") as handle:
        np.save(handle, decoy_samples, allow_pickle=False)
    decoy.chmod(0o600)
    identity = _file_identity(path, relative, frames=4)
    directories = _directory_inventory(root)
    moved = path.with_name("approved-held.npy")
    original_hash = verified_inputs._hash_and_rewind
    hash_calls = 0
    loaded_samples: list[np.ndarray] = []

    def swap_after_first_hash(descriptor: int, expected_bytes: int) -> str:
        nonlocal hash_calls
        digest = original_hash(descriptor, expected_bytes)
        hash_calls += 1
        if hash_calls == 1:
            path.rename(moved)
            decoy.rename(path)
        return digest

    class RecordingNumpy:
        ndarray = np.ndarray
        dtype = staticmethod(np.dtype)
        isfinite = staticmethod(np.isfinite)

        @staticmethod
        def load(handle: object, *, allow_pickle: bool) -> np.ndarray:
            value = np.load(handle, allow_pickle=allow_pickle)
            loaded_samples.append(value.copy())
            return value

    monkeypatch.setattr(
        verified_inputs,
        "_hash_and_rewind",
        swap_after_first_hash,
    )
    with pytest.raises(ValueError, match="descriptor changed|leaf attachment changed"):
        verified_inputs.load_verified_private_float32_npy(
            root,
            identity,
            expected_directories=directories,
            np=RecordingNumpy,
        )

    assert len(loaded_samples) == 1
    assert np.array_equal(loaded_samples[0], approved_samples)
    assert not np.array_equal(loaded_samples[0], decoy_samples)


def test_ancestor_symlink_and_changed_approved_directory_are_rejected(
    tmp_path: Path,
) -> None:
    root, path, relative = _private_path(tmp_path, "estimate.npy")
    with path.open("wb") as handle:
        np.save(handle, np.zeros((2, 2), dtype=np.float32), allow_pickle=False)
    path.chmod(0o600)
    identity = _file_identity(path, relative, frames=2)
    original_temp = root / "TEMP"
    moved_temp = root / "TEMP-held"
    original_temp.rename(moved_temp)
    original_temp.symlink_to(moved_temp.name, target_is_directory=True)
    directories = {
        ".": _directory_identity(root),
        "TEMP": _directory_identity(moved_temp),
        "TEMP/case": _directory_identity(moved_temp / "case"),
    }

    with pytest.raises(ValueError, match="real directory|descriptor pin"):
        verified_inputs.load_verified_private_float32_npy(
            root,
            identity,
            expected_directories=directories,
            np=np,
        )

    original_temp.unlink()
    moved_temp.rename(original_temp)
    directories = _directory_inventory(root)
    directories["TEMP/case"] = dict(directories["TEMP/case"])
    directories["TEMP/case"]["inode"] += 1
    with pytest.raises(ValueError, match="approved directory metadata changed"):
        verified_inputs.load_verified_private_float32_npy(
            root,
            identity,
            expected_directories=directories,
            np=np,
        )


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "../escape", "nested/name", "nested\\name", "bad\x00name"],
)
def test_safe_private_basename_rejects_path_syntax(value: str) -> None:
    with pytest.raises(ValueError, match="safe basename"):
        verified_inputs.require_safe_private_basename(value)


def test_safe_private_basename_accepts_one_canonical_component() -> None:
    assert (
        verified_inputs.require_safe_private_basename("both_targets")
        == "both_targets"
    )
