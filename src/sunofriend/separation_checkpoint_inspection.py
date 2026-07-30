"""Descriptor-pinned static inspection of one private separation checkpoint.

The inspector reads only the exact checkpoint bound into a fully validated
parent worker request.  It hashes the already-open descriptor, validates a
bounded ZIP inventory and parses pickle *opcodes* with :mod:`pickletools`.
It never invokes pickle deserialization, imports a model runtime, starts a
process, uses a network service, reads audio or writes a file.

Static pickle evidence is deliberately conservative.  V1 recognizes only the
exact registered HTDemucs hash and its exact bounded opcode/global profile as
a Torch ZIP pickle model package.  Even a mapping-prefix, tensor-rebuild and
persistent-storage signature remains unknown until a later parser can model
pickle stack, memo and persistent-ID semantics.  No classification in this
module authorizes loading or execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickletools
import re
import stat
import struct
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping, Sequence

from .separation_worker_contract import (
    SeparationRuntimeArtifactIdentity,
    validate_separation_worker_request,
)


SEPARATION_CHECKPOINT_INSPECTION_SCHEMA = (
    "sunofriend.separation-checkpoint-inspection.v1"
)
SEPARATION_CHECKPOINT_INSPECTION_ID = (
    "private-static-checkpoint-inspection-v1"
)
CHECKPOINT_STATIC_INSPECTION_EXECUTION_SUPPORTED = False

MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024 * 1024
MAX_PATH_BYTES = 4096
MAX_PATH_DEPTH = 64
MAX_ZIP_MEMBERS = 4096
MAX_ZIP_MEMBER_NAME_BYTES = 1024
MAX_ZIP_MEMBER_DEPTH = 32
MAX_ZIP_MEMBER_BYTES = 4 * 1024 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_ZIP_CENTRAL_DIRECTORY_BYTES = 16 * 1024 * 1024
MAX_ZIP_LOCAL_EXTRA_BYTES = 4096
MAX_PICKLE_BYTES = 32 * 1024 * 1024
MAX_PICKLE_OPCODES = 1_000_000
MAX_PICKLE_GLOBALS = 4096
MAX_PICKLE_GLOBAL_BYTES = 512

_AUTHORITY = object()
_INSPECTION_AUTHORITY = object()
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:-]{0,191}$")
_PYTHON_COMPONENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")
_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_ZIP_SIGNATURE = b"PK\x03\x04"
_OBJECT_CONSTRUCTION_OPCODES = frozenset(
    {"INST", "NEWOBJ", "NEWOBJ_EX", "OBJ", "REDUCE"}
)
_FORBIDDEN_STATE_DICT_OPCODES = frozenset(
    {"EXT1", "EXT2", "EXT4", "INST", "NEWOBJ", "NEWOBJ_EX", "OBJ", "PERSID"}
)
_TENSOR_REBUILD_GLOBALS = frozenset(
    {
        "torch._utils._rebuild_meta_tensor_no_storage",
        "torch._utils._rebuild_parameter",
        "torch._utils._rebuild_qtensor",
        "torch._utils._rebuild_sparse_tensor",
        "torch._utils._rebuild_tensor",
        "torch._utils._rebuild_tensor_v2",
        "torch._utils._rebuild_tensor_v3",
    }
)
_STORAGE_GLOBALS = frozenset(
    {
        f"torch.{prefix}Storage"
        for prefix in (
            "BFloat16",
            "Bool",
            "Byte",
            "Char",
            "ComplexDouble",
            "ComplexFloat",
            "Double",
            "Float",
            "Half",
            "Int",
            "Long",
            "QInt32",
            "QInt8",
            "QUInt4x2",
            "QUInt8",
            "Short",
        )
    }
)
_STATE_DICT_GLOBALS = frozenset(
    {
        "collections.OrderedDict",
        "torch.Tensor",
        *_TENSOR_REBUILD_GLOBALS,
        *_STORAGE_GLOBALS,
    }
)
_EOCD = struct.Struct("<4s4H2LH")
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_CENTRAL_HEADER = struct.Struct("<4s6H3L5H2L")
_LOCAL_HEADER = struct.Struct("<4s5H3L2H")
_DATA_DESCRIPTOR = struct.Struct("<4s3L")
_TORCH_ZIP_FLAGS = 0x0808
_HTDEMUCS_GLOBAL = "demucs.htdemucs.HTDemucs"
_HTDEMUCS_CHECKPOINT_SHA256 = (
    "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
)
_HTDEMUCS_PICKLE_GLOBALS_SHA256 = (
    "421acdf2045675551d98c87fa6625b064ef993a50a0c2044c60f3ce43d2acfcf"
)
_HTDEMUCS_PICKLE_OPCODE_STREAM_SHA256 = (
    "e6576ee1885c9dc48404f216ed8ac4f4573a14a2c37f3d19898f99005415082a"
)
_HTDEMUCS_PICKLE_OPCODE_COUNT = 18_523


@dataclass(frozen=True, init=False)
class SeparationCheckpointInspectionRequest:
    """Parent-issued binding to one fully validated worker checkpoint."""

    worker_request: Mapping[str, Any]
    request_sha256: str
    preflight_sha256: str
    acceptance_artifact_sha256: str
    checkpoint_path: Path
    checkpoint_id: str
    declared_format: str
    checkpoint_sha256: str
    checkpoint_bytes: int
    _authority: object = field(repr=False, compare=False)


@dataclass(frozen=True, init=False)
class SeparationCheckpointInspection(Mapping[str, Any]):
    """Deeply immutable, private-local, static inspection evidence."""

    _document: Mapping[str, Any]
    _request: SeparationCheckpointInspectionRequest
    _authority: object = field(repr=False, compare=False)

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True)
class _PinnedCheckpoint:
    descriptor: int
    path: Path
    before: tuple[int, int, int, int, int, int, int, int]
    leaf_name: str
    ancestor_descriptors: tuple[int, ...]
    ancestor_facts: tuple[tuple[int, int, int], ...]
    ancestor_components: tuple[str, ...]


@dataclass(frozen=True)
class _PickleEvidence:
    protocol: int | None
    opcode_count: int
    opcode_stream_sha256: str
    globals: tuple[str, ...]
    globals_sha256: str
    unresolved_stack_globals: int
    mapping_root_prefix_observed: bool
    has_tensor_rebuild: bool
    has_persistent_storage: bool
    object_construction_opcodes: tuple[str, ...]
    forbidden_state_dict_opcodes: tuple[str, ...]
    application_globals: tuple[str, ...]
    trailing_bytes: int


@dataclass(frozen=True)
class _CentralMember:
    name: str
    name_bytes: bytes
    crc32: int
    compressed_bytes: int
    uncompressed_bytes: int
    local_header_offset: int
    record_end_offset: int


def bind_separation_checkpoint_inspection_request(
    worker_request: Mapping[str, Any],
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationCheckpointInspectionRequest:
    """Issue the exact parent-owned checkpoint binding used by inspection."""

    request = _validated_request(
        worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    checkpoint = request["identities"]["checkpoint"]
    if checkpoint["format"] == "none":
        raise ValueError("static checkpoint inspection requires a checkpoint")
    if checkpoint["bytes"] > MAX_CHECKPOINT_BYTES:
        raise ValueError("checkpoint exceeds static inspection byte limit")
    value = object.__new__(SeparationCheckpointInspectionRequest)
    object.__setattr__(value, "worker_request", request)
    object.__setattr__(value, "request_sha256", request["request_sha256"])
    object.__setattr__(
        value, "preflight_sha256", request["preflight"]["preflight_sha256"]
    )
    object.__setattr__(
        value,
        "acceptance_artifact_sha256",
        request["preflight"]["bindings"]["acceptance_artifact_sha256"],
    )
    object.__setattr__(
        value, "checkpoint_path", Path(request["paths"]["checkpoint_path"])
    )
    object.__setattr__(value, "checkpoint_id", checkpoint["checkpoint_id"])
    object.__setattr__(value, "declared_format", checkpoint["format"])
    object.__setattr__(value, "checkpoint_sha256", checkpoint["sha256"])
    object.__setattr__(value, "checkpoint_bytes", checkpoint["bytes"])
    object.__setattr__(value, "_authority", _AUTHORITY)
    return value


def inspect_separation_checkpoint(
    worker_request: Mapping[str, Any],
    *,
    trusted_request: SeparationCheckpointInspectionRequest,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationCheckpointInspection:
    """Inspect one request-bound checkpoint without loading any model."""

    bound = _trusted_request(
        trusted_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    request = _validated_request(
        worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    if (
        request["request_sha256"] != bound.request_sha256
        or _plain(request) != _plain(bound.worker_request)
    ):
        raise ValueError("worker request was substituted after parent binding")

    pinned = _open_pinned_checkpoint(bound.checkpoint_path)
    archive_parsed = False
    pickle_parsed = False
    try:
        digest, byte_count, header = _hash_descriptor(
            pinned.descriptor,
            maximum_bytes=min(MAX_CHECKPOINT_BYTES, bound.checkpoint_bytes + 1),
        )
        if byte_count != bound.checkpoint_bytes:
            raise ValueError("checkpoint size does not bind parent request")
        if digest != bound.checkpoint_sha256:
            raise ValueError("checkpoint hash does not bind parent request")
        classification, archive, pickle = _inspect_container(
            pinned.descriptor,
            file_bytes=byte_count,
            header=header,
            checkpoint_sha256=digest,
            declared_format=bound.declared_format,
        )
        archive_parsed = archive["archive_metadata_parsed"]
        pickle_parsed = archive["pickle_metadata_parsed"]
        _recheck_pinned_checkpoint(pinned)
    finally:
        _close_pinned_checkpoint(pinned)

    evidence_payload = {
        "request_sha256": bound.request_sha256,
        "preflight_sha256": bound.preflight_sha256,
        "acceptance_artifact_sha256": bound.acceptance_artifact_sha256,
        "checkpoint_sha256": digest,
        "checkpoint_bytes": byte_count,
        "file_identity": _file_identity_document(pinned.before),
        "archive": archive,
        "pickle": pickle,
        "classification": classification,
    }
    classification_evidence_sha256 = _hash(evidence_payload)
    payload = {
        "schema": SEPARATION_CHECKPOINT_INSPECTION_SCHEMA,
        "inspection_id": SEPARATION_CHECKPOINT_INSPECTION_ID,
        "status": "inspected_not_loaded",
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "public_redacted_projection_available": False,
        "evidence_authority": "parent_issued_static_observation",
        "execution_supported": CHECKPOINT_STATIC_INSPECTION_EXECUTION_SUPPORTED,
        "execution_permitted": False,
        "bindings": {
            "worker_request_sha256": bound.request_sha256,
            "preflight_sha256": bound.preflight_sha256,
            "acceptance_artifact_sha256": (
                bound.acceptance_artifact_sha256
            ),
        },
        "checkpoint": {
            "checkpoint_id": bound.checkpoint_id,
            "declared_format": bound.declared_format,
            "sha256": digest,
            "bytes": byte_count,
            "file_identity": _file_identity_document(pinned.before),
        },
        "archive": archive,
        "pickle": pickle,
        "classification": {
            **classification,
            "classification_evidence_sha256": (
                classification_evidence_sha256
            ),
            "authorizes_loading": False,
            "authorizes_execution": False,
        },
        "limitations": [
            "checkpoint_descriptor_not_carried_to_loader",
            "checkpoint_path_to_loader_toctou_unresolved",
            "checkpoint_filesystem_mount_locality_not_proven",
            "static_pickle_opcode_analysis_does_not_deserialize",
        ],
        "effects": {
            "filesystem_accessed": True,
            "checkpoint_opened": True,
            "checkpoint_bytes_read": True,
            "checkpoint_descriptor_closed": True,
            "archive_metadata_parsed": archive_parsed,
            "pickle_opcodes_parsed": pickle_parsed,
            "checkpoint_loaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "network_used": False,
            "audio_read": False,
            "files_written": False,
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
    }
    _path_free(payload, "checkpoint inspection")
    document = {**payload, "inspection_sha256": _hash(payload)}
    return _new_inspection(document, bound)


def validate_separation_checkpoint_inspection(
    value: SeparationCheckpointInspection,
    *,
    trusted_request: SeparationCheckpointInspectionRequest,
) -> SeparationCheckpointInspection:
    """Validate one already-issued immutable inspection without rereading."""

    request = _issued_request(trusted_request)
    if type(value) is not SeparationCheckpointInspection:
        raise ValueError("inspection must be an exact parent-issued record")
    if getattr(value, "_authority", None) is not _INSPECTION_AUTHORITY:
        raise ValueError("inspection lacks parent observation authority")
    if value._request is not request:
        raise ValueError("inspection does not bind the exact parent request")
    return _new_inspection(_plain(value), request)


def separation_checkpoint_inspection_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash one inspection excluding only its self-hash."""

    value = _json_object(document, "checkpoint inspection")
    value.pop("inspection_sha256", None)
    return _hash(value)


def _trusted_request(
    value: Any,
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationCheckpointInspectionRequest:
    issued = _issued_request(value)
    request = _validated_request(
        issued.worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    checkpoint = request["identities"]["checkpoint"]
    expected = (
        request["request_sha256"],
        request["preflight"]["preflight_sha256"],
        request["preflight"]["bindings"]["acceptance_artifact_sha256"],
        Path(request["paths"]["checkpoint_path"]),
        checkpoint["checkpoint_id"],
        checkpoint["format"],
        checkpoint["sha256"],
        checkpoint["bytes"],
    )
    observed = (
        issued.request_sha256,
        issued.preflight_sha256,
        issued.acceptance_artifact_sha256,
        issued.checkpoint_path,
        issued.checkpoint_id,
        issued.declared_format,
        issued.checkpoint_sha256,
        issued.checkpoint_bytes,
    )
    if expected != observed or _plain(request) != _plain(issued.worker_request):
        raise ValueError("parent checkpoint binding was changed or resigned")
    return issued


def _issued_request(value: Any) -> SeparationCheckpointInspectionRequest:
    if type(value) is not SeparationCheckpointInspectionRequest:
        raise ValueError("trusted request must be an exact parent-issued record")
    if getattr(value, "_authority", None) is not _AUTHORITY:
        raise ValueError("trusted request lacks parent-process authority")
    return value


def _validated_request(
    document: Mapping[str, Any],
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> Mapping[str, Any]:
    return validate_separation_worker_request(
        document,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )


def _open_pinned_checkpoint(path: Path) -> _PinnedCheckpoint:
    canonical = PurePosixPath(str(path))
    if (
        not canonical.is_absolute()
        or ".." in canonical.parts
        or str(canonical) != str(path)
    ):
        raise ValueError("checkpoint path must be canonical absolute")
    encoded = str(canonical).encode("utf-8")
    if len(encoded) > MAX_PATH_BYTES or len(canonical.parts) > MAX_PATH_DEPTH:
        raise ValueError("checkpoint path exceeds inspection limits")
    parts = canonical.parts[1:]
    if not parts:
        raise ValueError("checkpoint path cannot be the filesystem root")

    try:
        close_on_exec = os.O_CLOEXEC
        directory_only = os.O_DIRECTORY
        no_follow = os.O_NOFOLLOW
        nonblocking = os.O_NONBLOCK
    except AttributeError as exc:
        raise ValueError(
            "checkpoint descriptor safety flags are unavailable"
        ) from exc
    directory_flags = (
        os.O_RDONLY
        | close_on_exec
        | directory_only
        | no_follow
        | nonblocking
    )
    file_flags = os.O_RDONLY | close_on_exec | no_follow | nonblocking
    directories: list[int] = []
    ancestor_facts: list[tuple[int, int, int]] = []
    ancestor_components: list[str] = []
    descriptor: int | None = None
    try:
        current = os.open("/", directory_flags)
        directories.append(current)
        root = os.fstat(current)
        ancestor_facts.append(_directory_identity(root))
        for component in parts[:-1]:
            _safe_path_component(component)
            before = os.stat(component, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise ValueError(
                    "checkpoint ancestor must be a real directory"
                )
            child = os.open(component, directory_flags, dir_fd=current)
            opened = os.fstat(child)
            if _directory_identity(opened) != _directory_identity(before):
                os.close(child)
                raise ValueError(
                    "checkpoint ancestor changed during descriptor pin"
                )
            directories.append(child)
            ancestor_facts.append(_directory_identity(opened))
            ancestor_components.append(component)
            current = child

        leaf = parts[-1]
        _safe_path_component(leaf)
        before = os.stat(leaf, dir_fd=current, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("checkpoint must be a regular file")
        if before.st_nlink != 1:
            raise ValueError("checkpoint must not have hardlink aliases")
        descriptor = os.open(leaf, file_flags, dir_fd=current)
        opened = os.fstat(descriptor)
        if _file_identity(opened) != _file_identity(before):
            raise ValueError("checkpoint changed during descriptor open")
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValueError("checkpoint descriptor is not an unaliased file")
        if opened.st_size <= 0 or opened.st_size > MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint size exceeds inspection limits")
        return _PinnedCheckpoint(
            descriptor=descriptor,
            path=path,
            before=_file_identity(opened),
            leaf_name=leaf,
            ancestor_descriptors=tuple(directories),
            ancestor_facts=tuple(ancestor_facts),
            ancestor_components=tuple(ancestor_components),
        )
    except OSError as exc:
        _close_descriptor_sequence(
            (
                *((descriptor,) if descriptor is not None else ()),
                *reversed(directories),
            ),
            raise_on_error=False,
        )
        raise ValueError("checkpoint descriptor pin failed") from exc
    except Exception:
        _close_descriptor_sequence(
            (
                *((descriptor,) if descriptor is not None else ()),
                *reversed(directories),
            ),
            raise_on_error=False,
        )
        raise


def _recheck_pinned_checkpoint(value: _PinnedCheckpoint) -> None:
    _recheck_ancestor_attachments(value)
    if _file_identity(os.fstat(value.descriptor)) != value.before:
        raise ValueError("checkpoint changed during static inspection")
    pinned_parent = value.ancestor_descriptors[-1]
    try:
        pinned_leaf = os.stat(
            value.leaf_name,
            dir_fd=pinned_parent,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValueError(
            "checkpoint leaf changed under pinned parent"
        ) from exc
    if _file_identity(pinned_leaf) != value.before:
        raise ValueError("checkpoint leaf changed under pinned parent")
    if len(value.ancestor_descriptors) != len(value.ancestor_facts):
        raise ValueError("checkpoint ancestor binding is incomplete")
    for descriptor, expected in zip(
        value.ancestor_descriptors,
        value.ancestor_facts,
    ):
        if _directory_identity(os.fstat(descriptor)) != expected:
            raise ValueError("checkpoint ancestor identity changed")
    _recheck_ancestor_attachments(value)
    try:
        after = value.path.lstat()
    except OSError as exc:
        raise ValueError("checkpoint path changed during inspection") from exc
    if _file_identity(after) != value.before:
        raise ValueError("checkpoint path changed during inspection")
    _recheck_ancestor_attachments(value)


def _recheck_ancestor_attachments(value: _PinnedCheckpoint) -> None:
    if (
        len(value.ancestor_facts) != len(value.ancestor_descriptors)
        or len(value.ancestor_components)
        != (len(value.ancestor_descriptors) - 1)
    ):
        raise ValueError("checkpoint ancestor attachment binding is incomplete")
    for index, component in enumerate(value.ancestor_components):
        parent = value.ancestor_descriptors[index]
        expected = value.ancestor_facts[index + 1]
        try:
            attached = os.stat(
                component,
                dir_fd=parent,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                "checkpoint ancestor attachment changed"
            ) from exc
        if (
            not stat.S_ISDIR(attached.st_mode)
            or _directory_identity(attached) != expected
        ):
            raise ValueError("checkpoint ancestor attachment changed")


def _close_pinned_checkpoint(value: _PinnedCheckpoint) -> None:
    _close_descriptor_sequence(
        (
            value.descriptor,
            *reversed(value.ancestor_descriptors),
        ),
        raise_on_error=True,
    )


def _close_descriptor_sequence(
    descriptors: Sequence[int],
    *,
    raise_on_error: bool,
) -> None:
    errors: list[OSError] = []
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError as exc:
            errors.append(exc)
    if errors and raise_on_error:
        raise ValueError("checkpoint descriptor cleanup failed") from errors[0]


def _hash_descriptor(
    descriptor: int,
    *,
    maximum_bytes: int,
) -> tuple[str, int, bytes]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    count = 0
    header = b""
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - count))
        if not chunk:
            break
        if len(header) < 4:
            header += chunk[: 4 - len(header)]
        count += len(chunk)
        if count > maximum_bytes:
            raise ValueError("checkpoint exceeds request-bound byte limit")
        digest.update(chunk)
    return digest.hexdigest(), count, header


def _inspect_container(
    descriptor: int,
    *,
    file_bytes: int,
    header: bytes,
    checkpoint_sha256: str,
    declared_format: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    if header != _ZIP_SIGNATURE:
        if declared_format == "torch-state-dict":
            raise ValueError(
                "declared Torch checkpoint lacks a byte-zero local ZIP header"
            )
        classification = {
            "container_kind": "unknown",
            "confidence": "not_classified",
            "reason_codes": ["container_not_supported_by_static_inspector"],
        }
        archive = {
            "kind": "unknown-non-torch-zip",
            "archive_metadata_parsed": False,
            "pickle_metadata_parsed": False,
            "member_count": 0,
            "inventory_sha256": None,
            "total_compressed_bytes": 0,
            "total_uncompressed_bytes": 0,
            "data_pickle_bytes": None,
            "data_pickle_sha256": None,
            "all_member_payload_crc_verified": False,
        }
        return classification, archive, None

    duplicate = os.dup(descriptor)
    try:
        with os.fdopen(duplicate, "rb", closefd=True) as stream:
            duplicate = -1
            return _inspect_torch_zip(
                stream,
                file_bytes=file_bytes,
                checkpoint_sha256=checkpoint_sha256,
            )
    finally:
        if duplicate >= 0:
            os.close(duplicate)


def _inspect_torch_zip(
    stream: BinaryIO,
    *,
    file_bytes: int,
    checkpoint_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    descriptor = stream.fileno()
    members, central_sha256, redundant_zip64 = _validate_torch_zip_dialect(
        descriptor,
        file_bytes=file_bytes,
    )
    pickle_member_name, tensor_member_count = _validate_torch_member_layout(
        members
    )
    try:
        archive = zipfile.ZipFile(stream, mode="r", allowZip64=False)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("checkpoint ZIP metadata is invalid") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) != len(members) or archive.comment:
            raise ValueError("checkpoint ZIP parser disagrees with bounded inventory")
        inventory: list[dict[str, Any]] = []
        pickle_infos: list[zipfile.ZipInfo] = []
        compressed_total = 0
        uncompressed_total = 0
        tensor_data_members = 0
        for info, member in zip(infos, members):
            safe_name = member.name
            if (
                info.filename != safe_name
                or info.flag_bits != _TORCH_ZIP_FLAGS
                or info.compress_type != zipfile.ZIP_STORED
                or info.CRC != member.crc32
                or info.compress_size != member.compressed_bytes
                or info.file_size != member.uncompressed_bytes
                or info.header_offset != member.local_header_offset
                or info.extra
                or info.comment
                or info.volume != 0
                or info.internal_attr != 0
                or info.external_attr != 0
            ):
                raise ValueError(
                    "checkpoint ZIP parsers disagree on member metadata"
                )
            compressed_total += info.compress_size
            uncompressed_total += info.file_size
            if safe_name == pickle_member_name:
                pickle_infos.append(info)
            if _torch_tensor_member_index(
                safe_name,
                root=PurePosixPath(pickle_member_name).parts[0],
            ) is not None:
                tensor_data_members += 1
            inventory.append(
                {
                    "name_sha256": _sha_text(safe_name),
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": info.file_size,
                    "compression": info.compress_type,
                    "crc32": f"{info.CRC:08x}",
                    "local_header_offset": info.header_offset,
                    "record_end_offset": member.record_end_offset,
                }
            )
        if len(pickle_infos) != 1:
            raise ValueError("checkpoint ZIP data.pkl binding changed")
        if tensor_data_members != tensor_member_count:
            raise ValueError("checkpoint ZIP tensor member inventory changed")
        inventory.sort(key=lambda item: item["local_header_offset"])
        inventory_sha256 = _hash(inventory)

        info = pickle_infos[0]
        data = _read_zip_member(archive, info)
        data_pickle_sha256 = hashlib.sha256(data).hexdigest()
        data_pickle_bytes = len(data)
        pickle_evidence = _inspect_pickle_opcodes(data)

        classification = _classify_pickle(
            pickle_evidence,
            tensor_data_members=tensor_data_members,
            checkpoint_sha256=checkpoint_sha256,
        )
        archive_document = {
            "kind": "torch-zip-v1-stored",
            "archive_metadata_parsed": True,
            "pickle_metadata_parsed": True,
            "member_count": len(infos),
            "inventory_sha256": inventory_sha256,
            "central_directory_sha256": central_sha256,
            "redundant_single_disk_zip64_terminal_validated": (
                redundant_zip64
            ),
            "total_compressed_bytes": compressed_total,
            "total_uncompressed_bytes": uncompressed_total,
            "tensor_data_member_count": tensor_data_members,
            "data_pickle_bytes": data_pickle_bytes,
            "data_pickle_sha256": data_pickle_sha256,
            "all_member_payload_crc_verified": False,
        }
        pickle_document = _pickle_document(pickle_evidence)
        return classification, archive_document, pickle_document


def _validate_torch_zip_dialect(
    descriptor: int,
    *,
    file_bytes: int,
) -> tuple[tuple[_CentralMember, ...], str, bool]:
    """Validate the narrow stored-only PyTorch ZIP dialect before zipfile."""

    if file_bytes < _EOCD.size + _LOCAL_HEADER.size:
        raise ValueError("checkpoint ZIP is too small")
    eocd_offset = file_bytes - _EOCD.size
    eocd = _pread_exact(descriptor, _EOCD.size, eocd_offset)
    (
        signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_bytes,
        central_offset,
        comment_bytes,
    ) = _EOCD.unpack(eocd)
    if signature != b"PK\x05\x06":
        raise ValueError("checkpoint ZIP lacks an exact terminal EOCD")
    if (
        disk_number != 0
        or central_disk != 0
        or disk_entries != total_entries
        or not 0 < total_entries <= MAX_ZIP_MEMBERS
        or total_entries == 0xFFFF
        or central_bytes == 0xFFFFFFFF
        or central_offset == 0xFFFFFFFF
        or comment_bytes != 0
        or central_bytes > MAX_ZIP_CENTRAL_DIRECTORY_BYTES
    ):
        raise ValueError(
            "checkpoint ZIP is not the supported single-disk bounded dialect"
        )
    central_end = central_offset + central_bytes
    if central_end > eocd_offset:
        raise ValueError("checkpoint ZIP central directory exceeds EOCD")
    redundant_zip64 = _validate_redundant_zip64_terminal(
        descriptor,
        central_end=central_end,
        eocd_offset=eocd_offset,
        disk_entries=disk_entries,
        total_entries=total_entries,
        central_bytes=central_bytes,
        central_offset=central_offset,
    )
    central = _pread_exact(descriptor, central_bytes, central_offset)
    cursor = 0
    aliases: set[str] = set()
    names: set[str] = set()
    members: list[_CentralMember] = []
    total_uncompressed = 0
    for _index in range(total_entries):
        if cursor + _CENTRAL_HEADER.size > len(central):
            raise ValueError("checkpoint ZIP central directory is truncated")
        fields = _CENTRAL_HEADER.unpack_from(central, cursor)
        (
            central_signature,
            made_version,
            needed_version,
            flags,
            compression,
            _modified_time,
            _modified_date,
            crc32,
            compressed_bytes,
            uncompressed_bytes,
            name_bytes,
            extra_bytes,
            member_comment_bytes,
            member_disk,
            internal_attr,
            external_attr,
            local_offset,
        ) = fields
        if central_signature != b"PK\x01\x02":
            raise ValueError("checkpoint ZIP central member signature is invalid")
        if (
            made_version != 0
            or needed_version != 0
            or flags != _TORCH_ZIP_FLAGS
            or compression != zipfile.ZIP_STORED
            or not 0 < name_bytes <= MAX_ZIP_MEMBER_NAME_BYTES
            or extra_bytes != 0
            or member_comment_bytes != 0
            or member_disk != 0
            or internal_attr != 0
            or external_attr != 0
            or compressed_bytes == 0xFFFFFFFF
            or uncompressed_bytes == 0xFFFFFFFF
            or local_offset == 0xFFFFFFFF
            or compressed_bytes != uncompressed_bytes
            or uncompressed_bytes > MAX_ZIP_MEMBER_BYTES
        ):
            raise ValueError(
                "checkpoint ZIP member is outside the stored Torch dialect"
            )
        start = cursor + _CENTRAL_HEADER.size
        end = start + name_bytes
        if end > len(central):
            raise ValueError("checkpoint ZIP central member name is truncated")
        raw_name = central[start:end]
        try:
            decoded_name = raw_name.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("checkpoint ZIP member name is not UTF-8") from exc
        safe_name = _safe_zip_name(decoded_name)
        if safe_name in names:
            raise ValueError("checkpoint ZIP contains duplicate member names")
        names.add(safe_name)
        alias = unicodedata.normalize("NFC", safe_name).casefold()
        if alias in aliases:
            raise ValueError("checkpoint ZIP contains a name alias")
        aliases.add(alias)
        total_uncompressed += uncompressed_bytes
        if total_uncompressed > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError(
                "checkpoint ZIP declared content exceeds byte limit"
            )
        record_end = _validate_local_torch_member(
            descriptor,
            file_bytes=file_bytes,
            central_offset=central_offset,
            name=raw_name,
            flags=flags,
            compression=compression,
            crc32=crc32,
            compressed_bytes=compressed_bytes,
            uncompressed_bytes=uncompressed_bytes,
            local_offset=local_offset,
        )
        members.append(
            _CentralMember(
                name=safe_name,
                name_bytes=raw_name,
                crc32=crc32,
                compressed_bytes=compressed_bytes,
                uncompressed_bytes=uncompressed_bytes,
                local_header_offset=local_offset,
                record_end_offset=record_end,
            )
        )
        cursor = end
    if cursor != len(central):
        raise ValueError("checkpoint ZIP central directory has trailing bytes")
    ordered = sorted(members, key=lambda item: item.local_header_offset)
    expected_offset = 0
    for member in ordered:
        if member.local_header_offset != expected_offset:
            raise ValueError(
                "checkpoint ZIP local records have a prefix, gap or overlap"
            )
        expected_offset = member.record_end_offset
    if expected_offset != central_offset:
        raise ValueError(
            "checkpoint ZIP local records do not end at central directory"
        )
    return (
        tuple(members),
        hashlib.sha256(central).hexdigest(),
        redundant_zip64,
    )


def _validate_redundant_zip64_terminal(
    descriptor: int,
    *,
    central_end: int,
    eocd_offset: int,
    disk_entries: int,
    total_entries: int,
    central_bytes: int,
    central_offset: int,
) -> bool:
    if central_end == eocd_offset:
        return False
    if eocd_offset - central_end != (
        _ZIP64_EOCD.size + _ZIP64_LOCATOR.size
    ):
        raise ValueError("checkpoint ZIP has unsupported terminal records")
    zip64 = _ZIP64_EOCD.unpack(
        _pread_exact(descriptor, _ZIP64_EOCD.size, central_end)
    )
    (
        signature,
        record_bytes,
        _made_version,
        needed_version,
        disk_number,
        central_disk,
        zip64_disk_entries,
        zip64_total_entries,
        zip64_central_bytes,
        zip64_central_offset,
    ) = zip64
    if (
        signature != b"PK\x06\x06"
        or record_bytes != 44
        or needed_version != 45
        or disk_number != 0
        or central_disk != 0
        or zip64_disk_entries != disk_entries
        or zip64_total_entries != total_entries
        or zip64_central_bytes != central_bytes
        or zip64_central_offset != central_offset
    ):
        raise ValueError("checkpoint ZIP redundant ZIP64 EOCD disagrees")
    locator_offset = central_end + _ZIP64_EOCD.size
    locator = _ZIP64_LOCATOR.unpack(
        _pread_exact(descriptor, _ZIP64_LOCATOR.size, locator_offset)
    )
    if locator != (b"PK\x06\x07", 0, central_end, 1):
        raise ValueError("checkpoint ZIP redundant ZIP64 locator disagrees")
    return True


def _validate_torch_member_layout(
    members: Sequence[_CentralMember],
) -> tuple[str, int]:
    roots = {
        PurePosixPath(member.name).parts[0]
        for member in members
        if PurePosixPath(member.name).parts
    }
    if len(roots) != 1:
        raise ValueError("checkpoint Torch ZIP must use one archive root")
    root = next(iter(roots))
    pickle_name = f"{root}/data.pkl"
    version_name = f"{root}/version"
    names = {member.name for member in members}
    if pickle_name not in names or version_name not in names:
        raise ValueError(
            "checkpoint Torch ZIP lacks required data.pkl or version member"
        )
    allowed_metadata = {
        pickle_name,
        version_name,
        f"{root}/byteorder",
        f"{root}/.data/serialization_id",
    }
    indices: list[int] = []
    for name in names:
        index = _torch_tensor_member_index(name, root=root)
        if index is not None:
            indices.append(index)
        elif name not in allowed_metadata:
            raise ValueError(
                "checkpoint Torch ZIP member is outside the narrow layout"
            )
    if not indices or sorted(indices) != list(range(len(indices))):
        raise ValueError(
            "checkpoint Torch ZIP tensor members must be contiguous decimals"
        )
    return pickle_name, len(indices)


def _torch_tensor_member_index(value: str, *, root: str) -> int | None:
    prefix = f"{root}/data/"
    if not value.startswith(prefix):
        return None
    suffix = value[len(prefix) :]
    if not suffix or not suffix.isascii() or not suffix.isdecimal():
        return None
    if suffix != "0" and suffix.startswith("0"):
        return None
    return int(suffix)


def _validate_local_torch_member(
    descriptor: int,
    *,
    file_bytes: int,
    central_offset: int,
    name: bytes,
    flags: int,
    compression: int,
    crc32: int,
    compressed_bytes: int,
    uncompressed_bytes: int,
    local_offset: int,
) -> int:
    if (
        local_offset < 0
        or local_offset + _LOCAL_HEADER.size >= central_offset
        or local_offset >= file_bytes
    ):
        raise ValueError("checkpoint ZIP local member offset is invalid")
    header = _pread_exact(descriptor, _LOCAL_HEADER.size, local_offset)
    (
        signature,
        needed_version,
        local_flags,
        local_compression,
        _modified_time,
        _modified_date,
        local_crc,
        local_compressed,
        local_uncompressed,
        local_name_bytes,
        local_extra_bytes,
    ) = _LOCAL_HEADER.unpack(header)
    if (
        signature != b"PK\x03\x04"
        or needed_version != 0
        or local_flags != flags
        or local_compression != compression
        or local_crc != 0
        or local_compressed != 0
        or local_uncompressed != 0
        or local_name_bytes != len(name)
        or local_extra_bytes > MAX_ZIP_LOCAL_EXTRA_BYTES
    ):
        raise ValueError(
            "checkpoint ZIP local and central headers disagree"
        )
    variable = _pread_exact(
        descriptor,
        local_name_bytes + local_extra_bytes,
        local_offset + _LOCAL_HEADER.size,
    )
    if variable[:local_name_bytes] != name:
        raise ValueError("checkpoint ZIP local member name disagrees")
    _validate_torch_alignment_extra(variable[local_name_bytes:])
    data_offset = (
        local_offset
        + _LOCAL_HEADER.size
        + local_name_bytes
        + local_extra_bytes
    )
    if data_offset % 64 != 0:
        raise ValueError("checkpoint ZIP member payload is not 64-byte aligned")
    descriptor_offset = data_offset + compressed_bytes
    record_end = descriptor_offset + _DATA_DESCRIPTOR.size
    if record_end > central_offset or record_end > file_bytes:
        raise ValueError("checkpoint ZIP member data exceeds local region")
    data_descriptor = _DATA_DESCRIPTOR.unpack(
        _pread_exact(descriptor, _DATA_DESCRIPTOR.size, descriptor_offset)
    )
    if data_descriptor != (
        b"PK\x07\x08",
        crc32,
        compressed_bytes,
        uncompressed_bytes,
    ):
        raise ValueError("checkpoint ZIP data descriptor disagrees")
    return record_end


def _validate_torch_alignment_extra(value: bytes) -> None:
    if not value:
        return
    if len(value) < 4:
        raise ValueError("checkpoint ZIP local extra field is truncated")
    identifier, body_bytes = struct.unpack_from("<2H", value)
    body = value[4:]
    if identifier != 0x4246 or body_bytes != len(body) or set(body) - {0x5A}:
        raise ValueError("checkpoint ZIP local padding field is unsupported")


def _pread_exact(descriptor: int, size: int, offset: int) -> bytes:
    if size < 0 or offset < 0:
        raise ValueError("checkpoint ZIP bounded read is invalid")
    chunks: list[bytes] = []
    count = 0
    while count < size:
        try:
            chunk = os.pread(descriptor, size - count, offset + count)
        except OSError as exc:
            raise ValueError("checkpoint ZIP bounded read failed") from exc
        if not chunk:
            raise ValueError("checkpoint ZIP bounded read is truncated")
        chunks.append(chunk)
        count += len(chunk)
    return b"".join(chunks)


def _read_zip_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > MAX_PICKLE_BYTES:
        raise ValueError("checkpoint data.pkl exceeds inspection byte limit")
    chunks: list[bytes] = []
    count = 0
    try:
        with archive.open(info, mode="r") as member:
            while True:
                chunk = member.read(min(1024 * 1024, MAX_PICKLE_BYTES + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_PICKLE_BYTES:
                    raise ValueError(
                        "checkpoint data.pkl exceeds inspection byte limit"
                    )
                chunks.append(chunk)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError("checkpoint data.pkl failed bounded read") from exc
    if count != info.file_size:
        raise ValueError("checkpoint data.pkl size changed during read")
    return b"".join(chunks)


def _inspect_pickle_opcodes(data: bytes) -> _PickleEvidence:
    opcode_count = 0
    protocol: int | None = None
    globals_found: set[str] = set()
    unresolved_stack_globals = 0
    opcode_digest = hashlib.sha256()
    opcode_names: set[str] = set()
    application_globals: set[str] = set()
    stop_position: int | None = None
    first_semantic: tuple[str, Any] | None = None
    try:
        for opcode, argument, position in pickletools.genops(data):
            opcode_count += 1
            if opcode_count > MAX_PICKLE_OPCODES:
                raise ValueError("checkpoint pickle opcode count exceeds limit")
            name = opcode.name
            opcode_names.add(name)
            opcode_digest.update(f"{position}:{name}\n".encode("ascii"))
            if name == "PROTO":
                if isinstance(argument, int):
                    protocol = argument
                continue
            if name == "FRAME":
                continue
            if first_semantic is None:
                first_semantic = (name, argument)
            if name == "GLOBAL":
                global_name = _pickle_global(argument)
                globals_found.add(global_name)
                if len(globals_found) > MAX_PICKLE_GLOBALS:
                    raise ValueError(
                        "checkpoint pickle global count exceeds limit"
                    )
                if _is_application_global(global_name):
                    application_globals.add(global_name)
                    if len(application_globals) > MAX_PICKLE_GLOBALS:
                        raise ValueError(
                            "checkpoint pickle application-global count "
                            "exceeds limit"
                        )
            elif name == "STACK_GLOBAL":
                unresolved_stack_globals += 1
            if name == "STOP":
                stop_position = position
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("checkpoint pickle opcode stream is invalid") from exc
    if stop_position is None:
        raise ValueError("checkpoint pickle has no STOP opcode")
    trailing_bytes = len(data) - (stop_position + 1)
    if trailing_bytes:
        raise ValueError("checkpoint pickle contains trailing bytes")
    global_list = tuple(sorted(globals_found))
    application_list = tuple(sorted(application_globals))
    mapping_root_prefix_observed = bool(
        first_semantic is not None
        and (
            first_semantic[0] == "EMPTY_DICT"
            or (
                first_semantic[0] == "GLOBAL"
                and _pickle_global(first_semantic[1])
                == "collections.OrderedDict"
            )
        )
    )
    return _PickleEvidence(
        protocol=protocol,
        opcode_count=opcode_count,
        opcode_stream_sha256=opcode_digest.hexdigest(),
        globals=global_list,
        globals_sha256=_hash(list(global_list)),
        unresolved_stack_globals=unresolved_stack_globals,
        mapping_root_prefix_observed=mapping_root_prefix_observed,
        has_tensor_rebuild=bool(
            set(global_list).intersection(_TENSOR_REBUILD_GLOBALS)
        ),
        has_persistent_storage="BINPERSID" in opcode_names,
        object_construction_opcodes=tuple(
            sorted(opcode_names.intersection(_OBJECT_CONSTRUCTION_OPCODES))
        ),
        forbidden_state_dict_opcodes=tuple(
            sorted(opcode_names.intersection(_FORBIDDEN_STATE_DICT_OPCODES))
        ),
        application_globals=application_list,
        trailing_bytes=trailing_bytes,
    )


def _classify_pickle(
    evidence: _PickleEvidence | None,
    *,
    tensor_data_members: int,
    checkpoint_sha256: str,
) -> dict[str, Any]:
    if evidence is None:
        return {
            "container_kind": "unknown",
            "confidence": "not_classified",
            "reason_codes": ["torch_zip_data_pickle_missing"],
        }
    exact_htdemucs_profile = bool(
        checkpoint_sha256 == _HTDEMUCS_CHECKPOINT_SHA256
        and _HTDEMUCS_GLOBAL in evidence.application_globals
        and evidence.globals_sha256 == _HTDEMUCS_PICKLE_GLOBALS_SHA256
        and evidence.opcode_stream_sha256
        == _HTDEMUCS_PICKLE_OPCODE_STREAM_SHA256
        and evidence.opcode_count == _HTDEMUCS_PICKLE_OPCODE_COUNT
        and evidence.protocol == 2
        and set(evidence.object_construction_opcodes).intersection(
            _OBJECT_CONSTRUCTION_OPCODES
        )
    )
    if exact_htdemucs_profile:
        return {
            "container_kind": "torch-zip-pickle-model-package",
            "confidence": "strong_static_evidence",
            "reason_codes": [
                "exact_htdemucs_hash_global_and_construction_profile_observed"
            ],
        }
    state_globals_only = set(evidence.globals).issubset(_STATE_DICT_GLOBALS)
    reasons = {
        "abstract_pickle_stack_and_memo_semantics_not_implemented",
        "static_pickle_semantics_not_proven",
    }
    if evidence.unresolved_stack_globals:
        reasons.add("stack_globals_unresolved")
    if evidence.application_globals:
        reasons.add("application_global_profile_not_exactly_registered")
    if not evidence.mapping_root_prefix_observed:
        reasons.add("mapping_root_prefix_not_observed")
    if not evidence.has_tensor_rebuild:
        reasons.add("tensor_rebuild_not_observed")
    if not evidence.has_persistent_storage:
        reasons.add("persistent_storage_not_observed")
    if tensor_data_members == 0:
        reasons.add("tensor_data_members_missing")
    if not state_globals_only:
        reasons.add("globals_outside_narrow_state_dict_set")
    if evidence.forbidden_state_dict_opcodes:
        reasons.add("object_or_extension_opcode_observed")
    if (
        evidence.mapping_root_prefix_observed
        and evidence.has_tensor_rebuild
        and evidence.has_persistent_storage
        and tensor_data_members > 0
        and state_globals_only
        and not evidence.unresolved_stack_globals
        and not evidence.forbidden_state_dict_opcodes
    ):
        reasons.add("state_dict_structural_signature_observed_not_proven")
    return {
        "container_kind": "unknown",
        "confidence": "not_classified",
        "reason_codes": sorted(reasons),
    }


def _pickle_document(value: _PickleEvidence) -> dict[str, Any]:
    return {
        "protocol": value.protocol,
        "opcode_count": value.opcode_count,
        "opcode_stream_sha256": value.opcode_stream_sha256,
        "global_count": len(value.globals),
        "globals_sha256": value.globals_sha256,
        "unresolved_stack_globals": value.unresolved_stack_globals,
        "mapping_root_prefix_observed": (
            value.mapping_root_prefix_observed
        ),
        "has_tensor_rebuild": value.has_tensor_rebuild,
        "has_persistent_storage": value.has_persistent_storage,
        "object_construction_opcodes": list(
            value.object_construction_opcodes
        ),
        "forbidden_state_dict_opcodes": list(
            value.forbidden_state_dict_opcodes
        ),
        "application_global_count": len(value.application_globals),
        "application_globals_sha256": _hash(
            list(value.application_globals)
        ),
        "known_htdemucs_application_global_observed": (
            _HTDEMUCS_GLOBAL in value.application_globals
        ),
        "trailing_bytes": value.trailing_bytes,
    }


def _pickle_global(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("checkpoint pickle GLOBAL argument is invalid")
    if len(value.encode("utf-8")) > MAX_PICKLE_GLOBAL_BYTES:
        raise ValueError("checkpoint pickle GLOBAL exceeds text limit")
    parts = value.split(" ")
    if len(parts) != 2:
        raise ValueError("checkpoint pickle GLOBAL is not canonical")
    module, name = parts
    module_parts = module.split(".")
    name_parts = name.split(".")
    if (
        not module_parts
        or not name_parts
        or any(not _PYTHON_COMPONENT_RE.fullmatch(item) for item in module_parts)
        or any(not _PYTHON_COMPONENT_RE.fullmatch(item) for item in name_parts)
    ):
        raise ValueError("checkpoint pickle GLOBAL identifier is invalid")
    return f"{module}.{name}"


def _is_application_global(value: str) -> bool:
    module = value.rsplit(".", 1)[0]
    return not (
        module == "builtins"
        or module == "collections"
        or module.startswith("collections.")
        or module == "torch"
        or module.startswith("torch.")
        or module == "numpy"
        or module.startswith("numpy.")
        or module == "_codecs"
        or module == "fractions"
    )


def _safe_zip_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("checkpoint ZIP member name must be text")
    encoded = value.encode("utf-8")
    if (
        not value
        or len(encoded) > MAX_ZIP_MEMBER_NAME_BYTES
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or _WINDOWS_RE.match(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise ValueError("checkpoint ZIP member name is unsafe")
    path = PurePosixPath(value)
    if (
        ".." in path.parts
        or "." in path.parts
        or len(path.parts) > MAX_ZIP_MEMBER_DEPTH
        or any(not item for item in path.parts)
    ):
        raise ValueError("checkpoint ZIP member name is unsafe")
    return value


def _safe_path_component(value: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\x00" in value
        or len(value.encode("utf-8")) > 255
    ):
        raise ValueError("checkpoint path component is unsafe")


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
    )


def _file_identity_document(
    value: tuple[int, int, int, int, int, int, int, int],
) -> dict[str, int]:
    return {
        "device": value[0],
        "inode": value[1],
        "mode": value[2],
        "links": value[3],
        "bytes": value[4],
        "mtime_ns": value[5],
        "ctime_ns": value[6],
        "uid": value[7],
    }


def _directory_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode)


def _new_inspection(
    document: Mapping[str, Any],
    request: SeparationCheckpointInspectionRequest,
) -> SeparationCheckpointInspection:
    value = _json_object(document, "checkpoint inspection")
    if value.get("schema") != SEPARATION_CHECKPOINT_INSPECTION_SCHEMA:
        raise ValueError("unsupported checkpoint inspection schema")
    if value.get("inspection_sha256") != (
        separation_checkpoint_inspection_sha256(value)
    ):
        raise ValueError("checkpoint inspection hash is invalid")
    if (
        value.get("status") != "inspected_not_loaded"
        or value.get("execution_supported") is not False
        or value.get("execution_permitted") is not False
        or value.get("classification", {}).get("authorizes_loading") is not False
        or value.get("classification", {}).get("authorizes_execution") is not False
    ):
        raise ValueError("checkpoint inspection cannot authorize execution")
    effects = value.get("effects")
    if (
        not isinstance(effects, dict)
        or effects.get("filesystem_accessed") is not True
        or effects.get("checkpoint_opened") is not True
        or effects.get("checkpoint_bytes_read") is not True
        or effects.get("checkpoint_descriptor_closed") is not True
    ):
        raise ValueError("checkpoint read effects must be recorded")
    for key in (
        "checkpoint_loaded",
        "checkpoint_deserialized",
        "model_imported",
        "process_started",
        "network_used",
        "audio_read",
        "files_written",
        "publication_permitted",
        "selection_permitted",
        "acceptance_eligible",
        "promotion_eligible",
    ):
        if effects.get(key) is not False:
            raise ValueError("checkpoint execution effects must remain false")
    if (
        value.get("bindings", {}).get("worker_request_sha256")
        != request.request_sha256
        or value.get("bindings", {}).get("preflight_sha256")
        != request.preflight_sha256
        or value.get("bindings", {}).get("acceptance_artifact_sha256")
        != request.acceptance_artifact_sha256
        or value.get("checkpoint", {}).get("checkpoint_id")
        != request.checkpoint_id
        or value.get("checkpoint", {}).get("declared_format")
        != request.declared_format
        or value.get("checkpoint", {}).get("sha256")
        != request.checkpoint_sha256
        or value.get("checkpoint", {}).get("bytes")
        != request.checkpoint_bytes
    ):
        raise ValueError("checkpoint inspection does not bind parent request")
    _path_free(value, "checkpoint inspection")
    record = object.__new__(SeparationCheckpointInspection)
    object.__setattr__(record, "_document", _freeze(value))
    object.__setattr__(record, "_request", request)
    object.__setattr__(record, "_authority", _INSPECTION_AUTHORITY)
    return record


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    plain = _plain(value)
    if not isinstance(plain, dict) or any(
        not isinstance(key, str) for key in plain
    ):
        raise ValueError(f"{label} must be a string-keyed object")
    _canonical_json(plain)
    return plain


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ValueError("checkpoint inspection is not canonical JSON") from exc


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _path_free(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} keys must be text")
            _path_free(item, label)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _path_free(item, label)
        return
    if isinstance(value, str):
        if (
            "\x00" in value
            or _URL_RE.search(value)
            or _WINDOWS_RE.match(value)
            or value.startswith(("/", "~/", "../", "./"))
            or "/../" in value
            or "/./" in value
        ):
            raise ValueError(f"{label} must be path- and URL-free")


__all__ = [
    "CHECKPOINT_STATIC_INSPECTION_EXECUTION_SUPPORTED",
    "MAX_CHECKPOINT_BYTES",
    "MAX_PICKLE_BYTES",
    "MAX_PICKLE_GLOBALS",
    "MAX_PICKLE_OPCODES",
    "MAX_ZIP_MEMBERS",
    "SEPARATION_CHECKPOINT_INSPECTION_ID",
    "SEPARATION_CHECKPOINT_INSPECTION_SCHEMA",
    "SeparationCheckpointInspection",
    "SeparationCheckpointInspectionRequest",
    "bind_separation_checkpoint_inspection_request",
    "inspect_separation_checkpoint",
    "separation_checkpoint_inspection_sha256",
    "validate_separation_checkpoint_inspection",
]
