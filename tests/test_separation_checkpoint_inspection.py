from __future__ import annotations

import ast
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import sunofriend.separation_checkpoint_inspection as inspection_module

from sunofriend.separation_checkpoint_inspection import (
    SeparationCheckpointInspection,
    SeparationCheckpointInspectionRequest,
    inspect_separation_checkpoint,
    separation_checkpoint_inspection_sha256,
    validate_separation_checkpoint_inspection,
)
from tests._separation_checkpoint_fixtures import (
    TORCH_ZIP_FLAGS as _FLAGS,
)
from tests._separation_checkpoint_fixtures import (
    canonical_sha256 as _canonical_sha256,
)
from tests._separation_checkpoint_fixtures import (
    checkpoint_fixture as _fixture,
)
from tests._separation_checkpoint_fixtures import (
    inspect_checkpoint as _inspect,
)
from tests._separation_checkpoint_fixtures import (
    inspection_kwargs as _kwargs,
)
from tests._separation_checkpoint_fixtures import model_pickle as _model_pickle
from tests._separation_checkpoint_fixtures import torch_zip as _torch_zip


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict) or hasattr(value, "items"):
        return [
            text
            for key, item in value.items()
            for text in [str(key), *_strings(item)]
        ]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def _assert_inspection_characterization(
    fixture: dict[str, Any],
    result: SeparationCheckpointInspection,
) -> None:
    document = _plain(result)
    assert set(document) == {
        "schema",
        "inspection_id",
        "status",
        "evidence_scope",
        "publication_scope",
        "public_redacted_projection_available",
        "evidence_authority",
        "execution_supported",
        "execution_permitted",
        "bindings",
        "checkpoint",
        "archive",
        "pickle",
        "classification",
        "limitations",
        "effects",
        "inspection_sha256",
    }
    assert set(document["bindings"]) == {
        "worker_request_sha256",
        "preflight_sha256",
        "acceptance_artifact_sha256",
    }
    assert set(document["checkpoint"]) == {
        "checkpoint_id",
        "declared_format",
        "sha256",
        "bytes",
        "file_identity",
    }
    assert set(document["checkpoint"]["file_identity"]) == {
        "device",
        "inode",
        "mode",
        "links",
        "bytes",
        "mtime_ns",
        "ctime_ns",
        "uid",
    }
    assert set(document["archive"]) == {
        "kind",
        "archive_metadata_parsed",
        "pickle_metadata_parsed",
        "member_count",
        "inventory_sha256",
        "central_directory_sha256",
        "redundant_single_disk_zip64_terminal_validated",
        "total_compressed_bytes",
        "total_uncompressed_bytes",
        "tensor_data_member_count",
        "data_pickle_bytes",
        "data_pickle_sha256",
        "all_member_payload_crc_verified",
    }
    assert set(document["pickle"]) == {
        "protocol",
        "opcode_count",
        "opcode_stream_sha256",
        "global_count",
        "globals_sha256",
        "unresolved_stack_globals",
        "mapping_root_prefix_observed",
        "has_tensor_rebuild",
        "has_persistent_storage",
        "object_construction_opcodes",
        "forbidden_state_dict_opcodes",
        "application_global_count",
        "application_globals_sha256",
        "known_htdemucs_application_global_observed",
        "trailing_bytes",
    }
    assert set(document["classification"]) == {
        "container_kind",
        "confidence",
        "reason_codes",
        "classification_evidence_sha256",
        "authorizes_loading",
        "authorizes_execution",
    }
    assert set(document["effects"]) == {
        "filesystem_accessed",
        "checkpoint_opened",
        "checkpoint_bytes_read",
        "checkpoint_descriptor_closed",
        "archive_metadata_parsed",
        "pickle_opcodes_parsed",
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
    }

    inspection_sha256 = document.pop("inspection_sha256")
    assert inspection_sha256 == _canonical_sha256(document)

    classification = dict(document["classification"])
    classification_sha256 = classification.pop("classification_evidence_sha256")
    assert classification.pop("authorizes_loading") is False
    assert classification.pop("authorizes_execution") is False
    request = fixture["trusted_request"]
    assert document["bindings"] == {
        "worker_request_sha256": request.request_sha256,
        "preflight_sha256": request.preflight_sha256,
        "acceptance_artifact_sha256": request.acceptance_artifact_sha256,
    }
    assert classification_sha256 == _canonical_sha256(
        {
            "request_sha256": request.request_sha256,
            "preflight_sha256": request.preflight_sha256,
            "acceptance_artifact_sha256": (request.acceptance_artifact_sha256),
            "checkpoint_sha256": document["checkpoint"]["sha256"],
            "checkpoint_bytes": document["checkpoint"]["bytes"],
            "file_identity": document["checkpoint"]["file_identity"],
            "archive": document["archive"],
            "pickle": document["pickle"],
            "classification": classification,
        }
    )


def test_inspects_narrow_torch_zip_as_private_non_authorising_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip(pickle_data=_model_pickle()))
    result = _inspect(fixture)

    assert type(result) is SeparationCheckpointInspection
    assert (
        type(fixture["trusted_request"])
        is SeparationCheckpointInspectionRequest
    )
    assert result["status"] == "inspected_not_loaded"
    assert result["evidence_scope"] == "private_development"
    assert result["publication_scope"] == "private_local_contract_evidence"
    assert result["execution_supported"] is False
    assert result["execution_permitted"] is False
    assert result["archive"]["kind"] == "torch-zip-v1-stored"
    assert result["archive"]["member_count"] == 3
    assert result["archive"]["tensor_data_member_count"] == 1
    assert result["archive"]["all_member_payload_crc_verified"] is False
    assert (
        result["classification"]["container_kind"]
        == "unknown"
    )
    assert (
        "application_global_profile_not_exactly_registered"
        in result["classification"]["reason_codes"]
    )
    assert result["classification"]["authorizes_loading"] is False
    assert result["classification"]["authorizes_execution"] is False
    assert result["effects"]["checkpoint_descriptor_closed"] is True
    assert (
        "checkpoint_filesystem_mount_locality_not_proven"
        in result["limitations"]
    )
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
        assert result["effects"][key] is False
    exposed = _strings(result)
    assert str(tmp_path) not in exposed
    assert not any("demucs.htdemucs" in text for text in exposed)
    assert not any("archive/data.pkl" in text for text in exposed)
    assert "has_mapping_root" not in result["pickle"]
    assert result["pickle"]["mapping_root_prefix_observed"] is False


def test_inspection_and_validated_copy_are_deeply_immutable_and_hash_bound(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    result = _inspect(fixture)
    validated = validate_separation_checkpoint_inspection(
        result,
        trusted_inspection=result,
        trusted_request=fixture["trusted_request"],
    )

    assert type(validated) is SeparationCheckpointInspection
    assert _plain(validated) == _plain(result)
    assert result["inspection_sha256"] == (
        separation_checkpoint_inspection_sha256(result)
    )
    _assert_inspection_characterization(fixture, result)
    assert result["pickle"]["mapping_root_prefix_observed"] is True
    assert "has_mapping_root" not in result["pickle"]
    with pytest.raises(TypeError):
        result["status"] = "loaded"  # type: ignore[index]
    with pytest.raises(TypeError):
        result["effects"]["checkpoint_loaded"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        result["classification"]["reason_codes"] += ("changed",)  # type: ignore[index,operator]


def test_serialized_mappings_and_forged_records_have_no_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    result = _inspect(fixture)

    with pytest.raises(ValueError, match="exact trusted parent observation"):
        validate_separation_checkpoint_inspection(
            _plain(result),  # type: ignore[arg-type]
            trusted_inspection=result,
            trusted_request=fixture["trusted_request"],
        )
    forged = object.__new__(SeparationCheckpointInspectionRequest)
    for name in (
        "worker_request",
        "request_sha256",
        "preflight_sha256",
        "acceptance_artifact_sha256",
        "checkpoint_path",
        "checkpoint_id",
        "declared_format",
        "checkpoint_sha256",
        "checkpoint_bytes",
    ):
        object.__setattr__(
            forged,
            name,
            getattr(fixture["trusted_request"], name),
        )
    kwargs = _kwargs(fixture)
    kwargs["trusted_request"] = forged
    with pytest.raises(ValueError, match="lacks parent-process authority"):
        inspect_separation_checkpoint(fixture["worker_request"], **kwargs)


def test_request_and_preflight_cross_binding_rejects_substitution(
    tmp_path: Path,
) -> None:
    first = _fixture(tmp_path / "first", _torch_zip())
    second = _fixture(
        tmp_path / "second",
        _torch_zip(pickle_data=_model_pickle()),
    )
    kwargs = _kwargs(second)
    kwargs["trusted_request"] = first["trusted_request"]

    with pytest.raises(ValueError):
        inspect_separation_checkpoint(second["worker_request"], **kwargs)


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("bindings", "preflight_sha256", "0" * 64),
        ("checkpoint", "checkpoint_id", "substituted-checkpoint"),
        ("checkpoint", "declared_format", "onnx"),
    ],
)
def test_validator_rejects_rehashed_binding_and_identity_tampering(
    tmp_path: Path,
    section: str,
    field: str,
    replacement: str,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    result = _inspect(fixture)
    document = _plain(result)
    document[section][field] = replacement
    document["inspection_sha256"] = (
        separation_checkpoint_inspection_sha256(document)
    )
    forged = object.__new__(SeparationCheckpointInspection)
    object.__setattr__(forged, "_document", document)
    object.__setattr__(forged, "_request", result._request)  # noqa: SLF001
    object.__setattr__(  # noqa: SLF001
        forged,
        "_authority",
        result._authority,  # noqa: SLF001
    )

    with pytest.raises(ValueError, match="exact trusted parent observation"):
        validate_separation_checkpoint_inspection(
            forged,
            trusted_inspection=result,
            trusted_request=fixture["trusted_request"],
        )


@pytest.mark.parametrize("replacement", ["symlink", "directory", "fifo"])
def test_rejects_symlink_directory_and_fifo_checkpoint_replacements(
    tmp_path: Path,
    replacement: str,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    checkpoint = fixture["checkpoint"]
    original = checkpoint.with_name("original-checkpoint.pt")
    checkpoint.replace(original)
    if replacement == "symlink":
        checkpoint.symlink_to(original.name)
    elif replacement == "directory":
        checkpoint.mkdir()
    else:
        os.mkfifo(checkpoint)

    with pytest.raises(ValueError, match="regular file"):
        _inspect(fixture)


def test_rejects_hardlink_alias(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    os.link(fixture["checkpoint"], fixture["checkpoint"].with_name("alias.pt"))

    with pytest.raises(ValueError, match="hardlink aliases"):
        _inspect(fixture)


def test_rejects_ancestor_replaced_by_same_tree_symlink_after_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    original_inspect = inspection_module._inspect_container  # noqa: SLF001
    parent = fixture["checkpoint"].parent
    moved = parent.with_name(f"{parent.name}-moved")
    changed = False

    def replacing_ancestor(*args: Any, **kwargs: Any) -> Any:
        nonlocal changed
        result = original_inspect(*args, **kwargs)
        parent.replace(moved)
        parent.symlink_to(moved.name, target_is_directory=True)
        changed = True
        return result

    monkeypatch.setattr(
        inspection_module,
        "_inspect_container",
        replacing_ancestor,
    )
    with pytest.raises(ValueError, match="ancestor attachment changed"):
        _inspect(fixture)
    assert changed


@pytest.mark.parametrize(
    "flag",
    ["O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"],
)
def test_missing_required_descriptor_safety_flag_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    monkeypatch.delattr(inspection_module.os, flag)

    with pytest.raises(ValueError, match="safety flags are unavailable"):
        _inspect(fixture)


def test_directory_descriptor_opens_include_nonblocking_defence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    original_open = inspection_module.os.open
    directory_flags: list[int] = []

    def recording_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if flags & os.O_DIRECTORY:
            directory_flags.append(flags)
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(inspection_module.os, "open", recording_open)
    _inspect(fixture)
    assert directory_flags
    required = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    assert all(flags & required == required for flags in directory_flags)


@pytest.mark.parametrize("mutation", ["hash", "size"])
def test_rejects_request_bound_hash_and_size_mismatch(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    data = fixture["checkpoint"].read_bytes()
    if mutation == "hash":
        fixture["checkpoint"].write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        expected = "hash"
    else:
        fixture["checkpoint"].write_bytes(data + b"x")
        expected = "size"

    with pytest.raises(ValueError, match=expected):
        _inspect(fixture)


@pytest.mark.parametrize(
    ("archive", "expected"),
    [
        (
            _torch_zip(
                members=[
                    (b"archive/data.pkl", b"\x80\x02}."),
                    (b"archive/data.pkl", b"\x80\x02}."),
                    (b"archive/version", b"3\n"),
                    (b"archive/data/0", b"x"),
                ]
            ),
            "duplicate",
        ),
        (
            _torch_zip(
                members=[
                    (b"archive/data.pkl", b"\x80\x02}."),
                    (b"archive/version", b"3\n"),
                    (b"archive/../data/0", b"x"),
                ]
            ),
            "unsafe",
        ),
        (
            _torch_zip(
                members=[
                    (b"archive/data.pkl", b"\x80\x02}."),
                    (b"archive/version", b"3\n"),
                    (b"archive/data/0", b"x"),
                    (b"ARCHIVE/DATA/0", b"x"),
                ]
            ),
            "name alias",
        ),
        (
            _torch_zip(
                members=[
                    (b"archive/data.pkl", b"\x80\x02}."),
                    (b"archive/version", b"3\n"),
                    (b"archive/data/0", b"x"),
                    ("archive/caf\u00e9".encode(), b"x"),
                    ("archive/cafe\u0301".encode(), b"x"),
                ]
            ),
            "unsafe",
        ),
        (
            _torch_zip(
                members=[
                    (b"archive/data.pkl", b"\x80\x02}."),
                    (b"archive/version", b"3\n"),
                    (b"archive/data/0", b"x"),
                ],
                local_names=[
                    b"archive/DATA.pkl",
                    b"archive/version",
                    b"archive/data/0",
                ],
            ),
            "name disagrees",
        ),
    ],
)
def test_rejects_duplicate_traversal_alias_and_header_name_disagreement(
    tmp_path: Path,
    archive: bytes,
    expected: str,
) -> None:
    fixture = _fixture(tmp_path, archive)
    with pytest.raises(ValueError, match=expected):
        _inspect(fixture)


@pytest.mark.parametrize(
    ("archive", "expected"),
    [
        (_torch_zip(prefix=b"x"), "declared Torch checkpoint"),
        (_torch_zip(gap_before_central=b"x"), "do not end"),
        (_torch_zip(trailer=b"x"), "terminal EOCD"),
        (_torch_zip(eocd_comment=b"x"), "terminal EOCD"),
        (_torch_zip(flags=_FLAGS | 1), "outside the stored Torch dialect"),
        (_torch_zip(compression=8), "outside the stored Torch dialect"),
        (
            _torch_zip(central_extra=b"x"),
            "outside the stored Torch dialect",
        ),
        (
            _torch_zip(central_comment=b"x"),
            "outside the stored Torch dialect",
        ),
        (
            _torch_zip(external_attr=1),
            "outside the stored Torch dialect",
        ),
        (
            _torch_zip(descriptor_signature=b"BAD!"),
            "data descriptor disagrees",
        ),
        (
            _torch_zip(local_crc=1),
            "local and central headers disagree",
        ),
        (
            _torch_zip(local_sizes=(1, 1)),
            "local and central headers disagree",
        ),
    ],
)
def test_rejects_prefix_gaps_trailers_comments_encryption_and_metadata(
    tmp_path: Path,
    archive: bytes,
    expected: str,
) -> None:
    fixture = _fixture(tmp_path, archive)
    with pytest.raises(ValueError, match=expected):
        _inspect(fixture)


def test_accepts_exact_redundant_zip64_and_rejects_bad_locator(
    tmp_path: Path,
) -> None:
    valid = _fixture(tmp_path / "valid", _torch_zip(zip64=True))
    result = _inspect(valid)
    assert (
        result["archive"][
            "redundant_single_disk_zip64_terminal_validated"
        ]
        is True
    )

    invalid = _fixture(
        tmp_path / "invalid",
        _torch_zip(zip64=True, bad_zip64=True),
    )
    with pytest.raises(ValueError, match="locator disagrees"):
        _inspect(invalid)


@pytest.mark.parametrize(
    ("pickle_data", "field", "expected"),
    [
        (
            b"\x80\x04\x8c\x08builtins\x8c\x04dict\x93.",
            "unresolved_stack_globals",
            1,
        ),
        (
            b"\x80\x02\x82\x01.",
            "forbidden_state_dict_opcodes",
            ("EXT1",),
        ),
    ],
)
def test_stack_global_and_extension_opcodes_remain_non_authorising(
    tmp_path: Path,
    pickle_data: bytes,
    field: str,
    expected: Any,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip(pickle_data=pickle_data))
    result = _inspect(fixture)

    assert result["classification"]["container_kind"] == "unknown"
    assert result["classification"]["authorizes_loading"] is False
    assert result["pickle"][field] == expected


def test_rejects_pickle_trailing_bytes_and_bounded_pickle_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trailing = _fixture(
        tmp_path / "trailing",
        _torch_zip(pickle_data=b"\x80\x02}.x"),
    )
    with pytest.raises(ValueError, match="trailing bytes"):
        _inspect(trailing)

    pickle_data = b"\x80\x02}."
    oversized = _fixture(
        tmp_path / "oversized",
        _torch_zip(pickle_data=pickle_data),
    )
    monkeypatch.setattr(inspection_module, "MAX_PICKLE_BYTES", len(pickle_data) - 1)
    with pytest.raises(ValueError, match="exceeds inspection byte limit"):
        _inspect(oversized)


def test_pickle_global_limit_is_enforced_during_opcode_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inspection_module, "MAX_PICKLE_GLOBALS", 2)
    many_globals = (
        b"\x80\x02"
        b"capplication_one\nFactory\n0"
        b"capplication_two\nFactory\n0"
        b"capplication_three\nFactory\n."
    )

    with pytest.raises(ValueError, match="global count exceeds limit"):
        inspection_module._inspect_pickle_opcodes(many_globals)  # noqa: SLF001


def test_known_htdemucs_static_profile_is_classified_only_for_exact_hash() -> None:
    observed = inspection_module._inspect_pickle_opcodes(  # noqa: SLF001
        _model_pickle()
    )
    evidence = replace(
        observed,
        globals_sha256=inspection_module._HTDEMUCS_PICKLE_GLOBALS_SHA256,  # noqa: SLF001
        opcode_stream_sha256=(  # noqa: SLF001
            inspection_module._HTDEMUCS_PICKLE_OPCODE_STREAM_SHA256
        ),
        opcode_count=inspection_module._HTDEMUCS_PICKLE_OPCODE_COUNT,  # noqa: SLF001
    )
    exact = inspection_module._classify_pickle(  # noqa: SLF001
        evidence,
        tensor_data_members=1,
        checkpoint_sha256=inspection_module._HTDEMUCS_CHECKPOINT_SHA256,  # noqa: SLF001
    )
    other = inspection_module._classify_pickle(  # noqa: SLF001
        evidence,
        tensor_data_members=1,
        checkpoint_sha256="0" * 64,
    )

    assert exact == {
        "container_kind": "torch-zip-pickle-model-package",
        "confidence": "strong_static_evidence",
        "reason_codes": [
            "exact_htdemucs_hash_global_and_construction_profile_observed"
        ],
    }
    assert other["container_kind"] == "unknown"


def test_all_descriptors_close_when_archive_or_pickle_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        _torch_zip(pickle_data=b"\x80\x02}.trailing"),
    )
    opened: list[int] = []
    original = inspection_module._open_pinned_checkpoint  # noqa: SLF001

    def recording_open(path: Path) -> Any:
        value = original(path)
        opened.extend([value.descriptor, *value.ancestor_descriptors])
        return value

    monkeypatch.setattr(
        inspection_module,
        "_open_pinned_checkpoint",
        recording_open,
    )
    with pytest.raises(ValueError, match="trailing bytes"):
        _inspect(fixture)
    assert opened
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_cleanup_attempts_every_descriptor_after_one_close_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, _torch_zip())
    pinned = inspection_module._open_pinned_checkpoint(  # noqa: SLF001
        fixture["checkpoint"]
    )
    expected = [
        pinned.descriptor,
        *reversed(pinned.ancestor_descriptors),
    ]
    original_close = inspection_module.os.close
    attempted: list[int] = []
    failed = expected[0]

    def failing_once(descriptor: int) -> None:
        attempted.append(descriptor)
        if descriptor == failed:
            raise OSError("synthetic close failure")
        original_close(descriptor)

    monkeypatch.setattr(inspection_module.os, "close", failing_once)
    try:
        with pytest.raises(ValueError, match="cleanup failed"):
            inspection_module._close_pinned_checkpoint(pinned)  # noqa: SLF001
        assert attempted == expected
        for descriptor in expected[1:]:
            with pytest.raises(OSError):
                os.fstat(descriptor)
    finally:
        original_close(failed)


def test_static_inspector_source_has_no_model_load_process_network_or_write_api(
) -> None:
    source = Path(inspection_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "asyncio",
        "ctypes",
        "http",
        "importlib",
        "multiprocessing",
        "onnxruntime",
        "requests",
        "runpy",
        "safetensors",
        "socket",
        "subprocess",
        "torch",
        "urllib",
    }
    forbidden_calls = {
        "compile",
        "eval",
        "exec",
        "__import__",
        "os.execl",
        "os.execle",
        "os.execlp",
        "os.execlpe",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.fork",
        "os.forkpty",
        "os.posix_spawn",
        "os.posix_spawnp",
        "os.system",
        "pickle.load",
        "pickle.loads",
        "torch.jit.load",
        "torch.load",
        "Path.write_bytes",
        "Path.write_text",
    }

    def call_name(node: ast.Call) -> str:
        parts: list[str] = []
        value: ast.expr = node.func
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            }.intersection(forbidden_import_roots)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in (
                forbidden_import_roots
            )
        elif isinstance(node, ast.Call):
            assert call_name(node) not in forbidden_calls
            if call_name(node) in {"open", "Path.open"}:
                pytest.fail("checkpoint inspector must use descriptor reads")
