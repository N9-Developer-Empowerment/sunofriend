"""Descriptor-bound readers for immutable private audio evidence.

The readers in this module never trust a pathname after opening it.  Every
directory component is opened with no-follow semantics, the leaf is opened
exactly once, and hashing plus decoding/loading use that one descriptor.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
import unicodedata

from .separation_quality import MAX_PCM_WAV_FILE_BYTES, read_pcm_wave_parameters


PCM24_CHANNELS = 2
PCM24_SAMPLE_RATE = 44_100
PCM24_SCALE = 8_388_608
MAX_PRIVATE_INPUT_BYTES = MAX_PCM_WAV_FILE_BYTES


@dataclass(frozen=True)
class VerifiedPrivateAudioInput:
    """Samples and identity consumed from one held regular-file descriptor."""

    samples: Any
    relative_path: str
    bytes: int
    sha256: str
    frames: int
    channels: int
    dtype: str
    file_identity: tuple[tuple[str, int], ...]
    directory_identities: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]

    def receipt(self) -> dict[str, Any]:
        """Return the neutral identity fields suitable for a local report."""

        return {
            "relative_path": self.relative_path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "shape": [self.frames, self.channels],
            "dtype": self.dtype,
            "finite": True,
            "observed_file_identity": dict(self.file_identity),
            "observed_directory_identities": {
                relative_path: dict(fields)
                for relative_path, fields in self.directory_identities
            },
        }


@dataclass(frozen=True)
class VerifiedPrivateBytes:
    """Exact bytes and identity consumed from one held private descriptor."""

    data: bytes
    relative_path: str
    bytes: int
    sha256: str
    file_identity: tuple[tuple[str, int], ...]
    directory_identities: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]

    def receipt(self) -> dict[str, Any]:
        """Return descriptor-bound evidence without duplicating the payload."""

        return {
            "relative_path": self.relative_path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "observed_file_identity": dict(self.file_identity),
            "observed_directory_identities": {
                relative_path: dict(fields)
                for relative_path, fields in self.directory_identities
            },
        }


@dataclass(frozen=True)
class _PinnedPrivateInput:
    descriptor: int
    leaf_name: str
    relative_path: str
    opened: tuple[int, ...]
    directory_descriptors: tuple[int, ...]
    directory_facts: tuple[tuple[int, ...], ...]
    attachments: tuple[tuple[int, str, tuple[int, ...]], ...]
    approved_directory_facts: tuple[tuple[str, tuple[int, ...]], ...]


def require_safe_private_basename(value: Any, *, label: str = "private name") -> str:
    """Return one canonical basename or reject path syntax and ambiguity."""

    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or len(value.encode("utf-8")) > 255
        or unicodedata.normalize("NFC", value) != value
    ):
        raise ValueError(f"{label} must be one safe basename")
    return value


def load_verified_private_pcm24(
    root: str | Path,
    identity: Mapping[str, Any],
    *,
    expected_directories: Mapping[str, Mapping[str, Any]],
    np: Any,
) -> VerifiedPrivateAudioInput:
    """Load canonical stereo 44.1 kHz PCM24 from one verified descriptor."""

    expected = _validated_expected_identity(identity)
    pinned = _pin_private_regular(
        root,
        expected,
        expected_directories=expected_directories,
    )
    try:
        digest = _hash_and_rewind(pinned.descriptor, expected["bytes"])
        if digest != expected["expected_sha256"]:
            raise ValueError("private PCM24 SHA-256 differs")
        samples = _decode_pcm24_descriptor(
            pinned.descriptor,
            file_bytes=expected["bytes"],
            expected_frames=expected["expected_frames"],
            np=np,
        )
        repeated = _hash_and_rewind(pinned.descriptor, expected["bytes"])
        if repeated != digest:
            raise ValueError("private PCM24 bytes changed while decoded")
        _recheck_pinned_private_input(pinned)
        return VerifiedPrivateAudioInput(
            samples=samples,
            relative_path=pinned.relative_path,
            bytes=expected["bytes"],
            sha256=digest,
            frames=expected["expected_frames"],
            channels=PCM24_CHANNELS,
            dtype="pcm24_float64_decode",
            file_identity=_identity_items(_file_identity_document(pinned.opened)),
            directory_identities=tuple(
                (relative_path, _identity_items(_directory_identity_document(fact)))
                for relative_path, fact in pinned.approved_directory_facts
            ),
        )
    finally:
        _close_pinned_private_input(pinned)


def read_verified_private_bytes(
    root: str | Path,
    identity: Mapping[str, Any],
    *,
    expected_directories: Mapping[str, Mapping[str, Any]],
    expected_sha256: str | None = None,
    maximum_bytes: int = MAX_PRIVATE_INPUT_BYTES,
) -> VerifiedPrivateBytes:
    """Read and hash exact approval-bound bytes from one held descriptor."""

    expected = _validated_expected_file_metadata(
        identity,
        maximum_bytes=maximum_bytes,
    )
    if expected_sha256 is not None:
        _require_sha256(expected_sha256, label="private input expected SHA-256")
    pinned = _pin_private_regular(
        root,
        expected,
        expected_directories=expected_directories,
    )
    try:
        data, digest = _read_bytes_and_hash(
            pinned.descriptor,
            expected["bytes"],
        )
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("private input SHA-256 differs")
        _recheck_pinned_private_input(pinned)
        return VerifiedPrivateBytes(
            data=data,
            relative_path=pinned.relative_path,
            bytes=expected["bytes"],
            sha256=digest,
            file_identity=_identity_items(_file_identity_document(pinned.opened)),
            directory_identities=tuple(
                (relative_path, _identity_items(_directory_identity_document(fact)))
                for relative_path, fact in pinned.approved_directory_facts
            ),
        )
    finally:
        _close_pinned_private_input(pinned)


def load_verified_private_float32_npy(
    root: str | Path,
    identity: Mapping[str, Any],
    *,
    expected_directories: Mapping[str, Mapping[str, Any]],
    np: Any,
) -> VerifiedPrivateAudioInput:
    """Load one finite frames-by-stereo float32 NPY from a verified descriptor."""

    expected = _validated_expected_identity(identity)
    pinned = _pin_private_regular(
        root,
        expected,
        expected_directories=expected_directories,
    )
    try:
        digest = _hash_and_rewind(pinned.descriptor, expected["bytes"])
        if digest != expected["expected_sha256"]:
            raise ValueError("private NPY SHA-256 differs")
        with os.fdopen(
            pinned.descriptor,
            "rb",
            buffering=0,
            closefd=False,
        ) as handle:
            samples = np.load(handle, allow_pickle=False)
        expected_shape = (expected["expected_frames"], PCM24_CHANNELS)
        if (
            not isinstance(samples, np.ndarray)
            or samples.shape != expected_shape
            or samples.dtype != np.dtype("float32")
            or not bool(np.isfinite(samples).all())
        ):
            raise ValueError("private NPY geometry, dtype or samples differ")
        repeated = _hash_and_rewind(pinned.descriptor, expected["bytes"])
        if repeated != digest:
            raise ValueError("private NPY bytes changed while loaded")
        _recheck_pinned_private_input(pinned)
        return VerifiedPrivateAudioInput(
            samples=samples,
            relative_path=pinned.relative_path,
            bytes=expected["bytes"],
            sha256=digest,
            frames=expected["expected_frames"],
            channels=PCM24_CHANNELS,
            dtype="float32",
            file_identity=_identity_items(_file_identity_document(pinned.opened)),
            directory_identities=tuple(
                (relative_path, _identity_items(_directory_identity_document(fact)))
                for relative_path, fact in pinned.approved_directory_facts
            ),
        )
    finally:
        _close_pinned_private_input(pinned)


def _validated_expected_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    expected = _validated_expected_file_metadata(
        identity,
        maximum_bytes=MAX_PRIVATE_INPUT_BYTES,
    )
    expected_frames = identity.get("expected_frames")
    if (
        not isinstance(expected_frames, int)
        or isinstance(expected_frames, bool)
        or expected_frames <= 0
    ):
        raise ValueError("private input frame count differs")
    expected["expected_frames"] = expected_frames
    expected_sha256 = identity.get("expected_sha256")
    _require_sha256(expected_sha256, label="private input expected SHA-256")
    expected["expected_sha256"] = expected_sha256
    return expected


def _validated_expected_file_metadata(
    identity: Mapping[str, Any],
    *,
    maximum_bytes: int,
) -> dict[str, Any]:
    if (
        not isinstance(maximum_bytes, int)
        or isinstance(maximum_bytes, bool)
        or maximum_bytes <= 0
        or maximum_bytes > MAX_PRIVATE_INPUT_BYTES
    ):
        raise ValueError("private input byte bound differs")
    relative_path = identity.get("relative_path")
    _relative_components(relative_path)
    expected: dict[str, Any] = {"relative_path": relative_path}
    for field in ("bytes", "device", "inode", "mtime_ns", "ctime_ns", "mode"):
        value = identity.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"private input {field} differs")
        expected[field] = value
    if not 0 < expected["bytes"] <= maximum_bytes:
        raise ValueError("private input byte count exceeds its bound")
    if expected["mode"] != 0o600:
        raise ValueError("private input approved mode differs")
    return expected


def _require_sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} differs")
    return value


def _relative_components(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError("private input relative path differs")
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or relative.as_posix() != value
        or not relative.parts
    ):
        raise ValueError("private input relative path differs")
    return tuple(
        require_safe_private_basename(component, label="private input path component")
        for component in relative.parts
    )


def _absolute_root_components(root: str | Path) -> tuple[Path, tuple[str, ...]]:
    raw = os.fspath(root)
    path = Path(raw)
    if (
        not path.is_absolute()
        or path == Path("/")
        or any(component in {".", ".."} for component in path.parts)
        or str(path) != raw
    ):
        raise ValueError("private input root must be one canonical absolute path")
    components = tuple(
        require_safe_private_basename(component, label="private root path component")
        for component in path.parts[1:]
    )
    return path, components


def _descriptor_flags(*, directory: bool) -> int:
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
    except AttributeError as error:
        raise RuntimeError("private input descriptor safety flags are unavailable") from error
    return flags


def _pin_private_regular(
    root: str | Path,
    expected: Mapping[str, Any],
    *,
    expected_directories: Mapping[str, Mapping[str, Any]],
) -> _PinnedPrivateInput:
    _root_path, root_components = _absolute_root_components(root)
    relative_components = _relative_components(expected["relative_path"])
    directory_flags = _descriptor_flags(directory=True)
    file_flags = _descriptor_flags(directory=False)
    directories: list[int] = []
    directory_facts: list[tuple[int, ...]] = []
    attachments: list[tuple[int, str, tuple[int, ...]]] = []
    approved_directory_facts: list[tuple[str, tuple[int, ...]]] = []
    leaf_descriptor: int | None = None
    try:
        current = os.open("/", directory_flags)
        os.set_inheritable(current, False)
        directories.append(current)
        directory_facts.append(_directory_identity(os.fstat(current)))
        for component in root_components:
            current = _open_directory_component(
                directories,
                directory_facts,
                attachments,
                component,
                require_private=False,
            )
        root_state = os.fstat(current)
        if (
            root_state.st_uid != os.geteuid()
            or stat.S_IMODE(root_state.st_mode) & 0o077
        ):
            raise ValueError("private input root is not owner-only")
        _require_expected_directory_metadata(
            root_state,
            expected_directories,
            ".",
        )
        approved_directory_facts.append((".", _approved_directory_identity(root_state)))
        prefix: list[str] = []
        for component in relative_components[:-1]:
            current = _open_directory_component(
                directories,
                directory_facts,
                attachments,
                component,
                require_private=True,
            )
            prefix.append(component)
            relative_directory = "/".join(prefix)
            current_state = os.fstat(current)
            _require_expected_directory_metadata(
                current_state,
                expected_directories,
                relative_directory,
            )
            approved_directory_facts.append(
                (relative_directory, _approved_directory_identity(current_state))
            )

        leaf_name = relative_components[-1]
        before = os.stat(leaf_name, dir_fd=current, follow_symlinks=False)
        _require_safe_regular_file(before)
        leaf_descriptor = os.open(leaf_name, file_flags, dir_fd=current)
        os.set_inheritable(leaf_descriptor, False)
        opened = os.fstat(leaf_descriptor)
        if _file_identity(opened) != _file_identity(before):
            raise ValueError("private input changed during descriptor open")
        _require_safe_regular_file(opened)
        _require_expected_metadata(opened, expected)
        return _PinnedPrivateInput(
            descriptor=leaf_descriptor,
            leaf_name=leaf_name,
            relative_path=expected["relative_path"],
            opened=_file_identity(opened),
            directory_descriptors=tuple(directories),
            directory_facts=tuple(directory_facts),
            attachments=tuple(attachments),
            approved_directory_facts=tuple(approved_directory_facts),
        )
    except OSError as error:
        _close_descriptor_sequence(leaf_descriptor, directories)
        raise ValueError("private input descriptor pin failed") from error
    except BaseException:
        _close_descriptor_sequence(leaf_descriptor, directories)
        raise


def _open_directory_component(
    directories: list[int],
    directory_facts: list[tuple[int, ...]],
    attachments: list[tuple[int, str, tuple[int, ...]]],
    component: str,
    *,
    require_private: bool,
) -> int:
    parent_index = len(directories) - 1
    parent = directories[parent_index]
    before = os.stat(component, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("private input ancestor must be a real directory")
    child = os.open(component, _descriptor_flags(directory=True), dir_fd=parent)
    os.set_inheritable(child, False)
    opened = os.fstat(child)
    fact = _directory_identity(opened)
    if fact != _directory_identity(before):
        os.close(child)
        raise ValueError("private input ancestor changed during descriptor open")
    if require_private and (
        opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) & 0o022
    ):
        os.close(child)
        raise ValueError("private input ancestor is not safely owned")
    directories.append(child)
    directory_facts.append(fact)
    attachments.append((parent_index, component, fact))
    return child


def _require_safe_regular_file(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) & 0o077
        or not 0 < value.st_size <= MAX_PRIVATE_INPUT_BYTES
    ):
        raise ValueError(
            "private input must be one owner-only bounded single-link regular file"
        )


def _require_expected_metadata(
    value: os.stat_result,
    expected: Mapping[str, Any],
) -> None:
    actual = {
        "bytes": value.st_size,
        "device": value.st_dev,
        "inode": value.st_ino,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
        "mode": stat.S_IMODE(value.st_mode),
    }
    if any(expected[field] != observed for field, observed in actual.items()):
        raise ValueError("private input approved metadata changed")


def _require_expected_directory_metadata(
    value: os.stat_result,
    expected_directories: Mapping[str, Mapping[str, Any]],
    relative_path: str,
) -> None:
    if not isinstance(expected_directories, Mapping):
        raise ValueError("private input approved directory inventory differs")
    expected = expected_directories.get(relative_path)
    if not isinstance(expected, Mapping):
        raise ValueError("private input approved directory identity is missing")
    actual = _directory_identity_document(_approved_directory_identity(value))
    for field, observed in actual.items():
        approved = expected.get(field)
        if (
            not isinstance(approved, int)
            or isinstance(approved, bool)
            or approved != observed
        ):
            raise ValueError("private input approved directory metadata changed")


def _hash_and_rewind(descriptor: int, expected_bytes: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    observed = 0
    while block := os.read(descriptor, min(1024 * 1024, expected_bytes + 1 - observed)):
        observed += len(block)
        if observed > expected_bytes:
            raise ValueError("private input grew while hashed")
        digest.update(block)
    if observed != expected_bytes:
        raise ValueError("private input byte count changed while hashed")
    if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
        raise ValueError("private input descriptor rewind failed")
    return digest.hexdigest()


def _read_bytes_and_hash(
    descriptor: int,
    expected_bytes: int,
) -> tuple[bytes, str]:
    if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
        raise ValueError("private input descriptor rewind failed")
    digest = hashlib.sha256()
    contents = bytearray()
    while block := os.read(
        descriptor,
        min(1024 * 1024, expected_bytes + 1 - len(contents)),
    ):
        contents.extend(block)
        if len(contents) > expected_bytes:
            raise ValueError("private input grew while read")
        digest.update(block)
    if len(contents) != expected_bytes:
        raise ValueError("private input byte count changed while read")
    if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
        raise ValueError("private input descriptor rewind failed")
    return bytes(contents), digest.hexdigest()


def _decode_pcm24_descriptor(
    descriptor: int,
    *,
    file_bytes: int,
    expected_frames: int,
    np: Any,
) -> Any:
    if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
        raise ValueError("private PCM24 descriptor rewind failed")
    with os.fdopen(descriptor, "rb", buffering=0, closefd=False) as reader:
        parameters = read_pcm_wave_parameters(reader, file_bytes=file_bytes)
        if (
            parameters.channels != PCM24_CHANNELS
            or parameters.sample_width_bytes != 3
            or parameters.sample_rate != PCM24_SAMPLE_RATE
            or parameters.frames != expected_frames
        ):
            raise ValueError("private PCM24 clock differs")
        reader.seek(parameters.data_offset)
        contents = reader.read(parameters.data_bytes)
    if len(contents) != parameters.data_bytes:
        raise ValueError("private PCM24 frames are truncated")
    packed = np.frombuffer(contents, dtype=np.uint8)
    if packed.size != expected_frames * PCM24_CHANNELS * 3:
        raise ValueError("private PCM24 packed geometry differs")
    packed = packed.reshape(-1, 3).astype(np.int32)
    unsigned = packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)
    signed = np.where(unsigned & 0x800000, unsigned - 0x1000000, unsigned)
    samples = signed.reshape(expected_frames, PCM24_CHANNELS).astype(np.float64)
    samples /= PCM24_SCALE
    if not bool(np.isfinite(samples).all()):
        raise ValueError("private PCM24 samples are non-finite")
    return samples


def _recheck_pinned_private_input(pinned: _PinnedPrivateInput) -> None:
    if _file_identity(os.fstat(pinned.descriptor)) != pinned.opened:
        raise ValueError("private input descriptor changed while consumed")
    parent = pinned.directory_descriptors[-1]
    try:
        visible_leaf = os.stat(
            pinned.leaf_name,
            dir_fd=parent,
            follow_symlinks=False,
        )
    except OSError as error:
        raise ValueError("private input leaf attachment changed") from error
    if _file_identity(visible_leaf) != pinned.opened:
        raise ValueError("private input leaf attachment changed")
    if len(pinned.directory_descriptors) != len(pinned.directory_facts):
        raise ValueError("private input directory binding is incomplete")
    for descriptor, expected in zip(
        pinned.directory_descriptors,
        pinned.directory_facts,
    ):
        if _directory_identity(os.fstat(descriptor)) != expected:
            raise ValueError("private input directory identity changed")
    for parent_index, component, expected in pinned.attachments:
        try:
            attached = os.stat(
                component,
                dir_fd=pinned.directory_descriptors[parent_index],
                follow_symlinks=False,
            )
        except OSError as error:
            raise ValueError("private input directory attachment changed") from error
        if not stat.S_ISDIR(attached.st_mode) or _directory_identity(attached) != expected:
            raise ValueError("private input directory attachment changed")
    first_approved_index = len(pinned.directory_descriptors) - len(
        pinned.approved_directory_facts
    )
    for offset, (_relative_path, expected) in enumerate(
        pinned.approved_directory_facts
    ):
        descriptor_index = first_approved_index + offset
        observed = os.fstat(pinned.directory_descriptors[descriptor_index])
        if _approved_directory_identity(observed) != expected:
            raise ValueError("private input approved directory identity changed")


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
    )


def _approved_directory_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IMODE(value.st_mode),
        value.st_uid,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _file_identity_document(value: tuple[int, ...]) -> dict[str, int]:
    return {
        "device": value[0],
        "inode": value[1],
        "mode": stat.S_IMODE(value[2]),
        "links": value[3],
        "uid": value[4],
        "gid": value[5],
        "bytes": value[6],
        "mtime_ns": value[7],
        "ctime_ns": value[8],
    }


def _directory_identity_document(value: tuple[int, ...]) -> dict[str, int]:
    return {
        "device": value[0],
        "inode": value[1],
        "mode": value[2],
        "uid": value[3],
        "mtime_ns": value[4],
        "ctime_ns": value[5],
    }


def _identity_items(value: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple(value.items())


def _close_descriptor_sequence(
    leaf_descriptor: int | None,
    directories: list[int],
) -> None:
    descriptors = (
        *((leaf_descriptor,) if leaf_descriptor is not None else ()),
        *reversed(directories),
    )
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _close_pinned_private_input(pinned: _PinnedPrivateInput) -> None:
    _close_descriptor_sequence(
        pinned.descriptor,
        list(pinned.directory_descriptors),
    )


__all__ = [
    "VerifiedPrivateAudioInput",
    "VerifiedPrivateBytes",
    "load_verified_private_float32_npy",
    "load_verified_private_pcm24",
    "read_verified_private_bytes",
    "require_safe_private_basename",
]
