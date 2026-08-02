from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from unittest.mock import patch

import pytest

from sunofriend._separation_safetensors_inspection import (
    MAX_HEADER_BYTES,
    _inspect_private_safetensors,
    _inspect_private_safetensors_descriptor,
)


def _container(header: dict[str, object], data: bytes) -> bytes:
    encoded = json.dumps(header, separators=(",", ":")).encode()
    return struct.pack("<Q", len(encoded)) + encoded + data


def _inspect(path: Path, contents: bytes) -> dict[str, object]:
    path.write_bytes(contents)
    return _inspect_private_safetensors(
        path.absolute(),
        expected_bytes=len(contents),
        expected_sha256=hashlib.sha256(contents).hexdigest(),
    )


def test_validates_header_and_hash_without_tensor_runtime(tmp_path: Path) -> None:
    contents = _container(
        {
            "weight": {"dtype": "BF16", "shape": [2, 2], "data_offsets": [0, 8]},
            "bias": {"dtype": "F32", "shape": [1], "data_offsets": [8, 12]},
            "__metadata__": {"format": "mlx"},
        },
        bytes(range(12)),
    )
    path = tmp_path / "model.safetensors"
    with (
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        result = _inspect(path, contents)

    assert result["status"] == "verified_header_only_not_deserialized"
    assert result["tensor_count"] == 2
    assert result["dtype_counts"] == {"BF16": 1, "F32": 1}
    assert result["metadata_keys"] == ["format"]
    assert result["metadata_encoding"] == "string_to_string_map"
    assert result["metadata_spec_conformant"] is True
    assert result["mlx_null_metadata_compatibility_applied"] is False
    assert result["metadata_values_observed"] is False
    assert result["tensor_values_observed"] is False
    assert "descriptor_pinned" not in result
    assert "path_retained" not in result
    assert result["authorises_loading"] is False
    assert result["effects"] == {
        "filesystem_accessed": True,
        "filesystem_written": False,
        "network_used": False,
        "package_installed": False,
        "tensor_deserialized": False,
        "model_imported": False,
        "process_started": False,
    }


def test_descriptor_inspection_is_path_free_and_offset_neutral(
    tmp_path: Path,
) -> None:
    contents = _container(
        {
            "weight": {"dtype": "BF16", "shape": [2, 2], "data_offsets": [0, 8]},
            "__metadata__": None,
        },
        bytes(range(8)),
    )
    path = tmp_path / "model.safetensors"
    path.write_bytes(contents)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.set_inheritable(descriptor, False)
        os.lseek(descriptor, 3, os.SEEK_SET)

        result = _inspect_private_safetensors_descriptor(
            descriptor,
            expected_bytes=len(contents),
            expected_sha256=hashlib.sha256(contents).hexdigest(),
        )

        assert os.lseek(descriptor, 0, os.SEEK_CUR) == 3
        assert result["descriptor_pinned"] is True
        assert result["path_retained"] is False
        assert "path" not in result
        assert str(path) not in repr(result)
        assert result["tensor_count"] == 1
    finally:
        os.close(descriptor)


def test_descriptor_inspection_rejects_inheritable_or_writable_descriptor(
    tmp_path: Path,
) -> None:
    contents = _container({}, b"")
    path = tmp_path / "model.safetensors"
    path.write_bytes(contents)
    digest = hashlib.sha256(contents).hexdigest()

    inheritable = os.open(path, os.O_RDONLY)
    try:
        os.set_inheritable(inheritable, True)
        with pytest.raises(ValueError, match="non-inheritable read-only"):
            _inspect_private_safetensors_descriptor(
                inheritable,
                expected_bytes=len(contents),
                expected_sha256=digest,
            )
    finally:
        os.close(inheritable)

    writable = os.open(path, os.O_RDWR)
    try:
        os.set_inheritable(writable, False)
        with pytest.raises(ValueError, match="non-inheritable read-only"):
            _inspect_private_safetensors_descriptor(
                writable,
                expected_bytes=len(contents),
                expected_sha256=digest,
            )
    finally:
        os.close(writable)


def test_accepts_scalar_empty_tensor_and_space_padding(tmp_path: Path) -> None:
    encoded = (
        b'{"scalar":{"dtype":"U8","shape":[],"data_offsets":[0,1]},'
        b'"empty":{"dtype":"F32","shape":[0],"data_offsets":[1,1]}}   '
    )
    contents = struct.pack("<Q", len(encoded)) + encoded + b"x"
    result = _inspect(tmp_path / "model.safetensors", contents)
    assert result["tensor_count"] == 2
    assert result["data_bytes"] == 1


def test_reports_mlx_null_metadata_as_noncanonical_compatibility(
    tmp_path: Path,
) -> None:
    contents = _container(
        {
            "weight": {"dtype": "BF16", "shape": [2], "data_offsets": [0, 4]},
            "__metadata__": None,
        },
        b"1234",
    )

    result = _inspect(tmp_path / "model.safetensors", contents)

    assert result["metadata_keys"] == []
    assert result["metadata_encoding"] == (
        "json_null_treated_as_empty_for_mlx_compatibility"
    )
    assert result["metadata_spec_conformant"] is False
    assert result["mlx_null_metadata_compatibility_applied"] is True


@pytest.mark.parametrize(
    ("header", "data", "message"),
    [
        (
            {"x": {"dtype": "F32", "shape": [1], "data_offsets": [1, 5]}},
            b"12345",
            "hole or overlap",
        ),
        (
            {
                "x": {"dtype": "U8", "shape": [2], "data_offsets": [0, 2]},
                "y": {"dtype": "U8", "shape": [2], "data_offsets": [1, 3]},
            },
            b"123",
            "hole or overlap",
        ),
        (
            {"x": {"dtype": "F32", "shape": [2], "data_offsets": [0, 4]}},
            b"1234",
            "disagree",
        ),
        (
            {"x": {"dtype": "OBJECT", "shape": [1], "data_offsets": [0, 1]}},
            b"1",
            "dtype is unsupported",
        ),
        (
            {"x": {"dtype": "F4", "shape": [1], "data_offsets": [0, 1]}},
            b"1",
            "disagree",
        ),
        (
            {"x": {"dtype": "U8", "shape": [1], "data_offsets": [0, 1]}},
            b"12",
            "not entirely indexed",
        ),
        ({"__metadata__": {"bad": 1}}, b"", "map strings to strings or be null"),
        ({"__metadata__": "bad"}, b"", "map strings to strings or be null"),
    ],
)
def test_rejects_invalid_tensor_inventory(
    tmp_path: Path, header: dict[str, object], data: bytes, message: str
) -> None:
    contents = _container(header, data)
    with pytest.raises(ValueError, match=message):
        _inspect(tmp_path / "model.safetensors", contents)


def test_rejects_duplicate_keys_and_non_space_padding(tmp_path: Path) -> None:
    encoded = (
        b'{"x":{"dtype":"U8","shape":[1],"data_offsets":[0,1]},'
        b'"x":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}'
    )
    contents = struct.pack("<Q", len(encoded)) + encoded + b"x"
    with pytest.raises(ValueError, match="duplicate key"):
        _inspect(tmp_path / "duplicate.safetensors", contents)

    encoded = b"{}\n"
    contents = struct.pack("<Q", len(encoded)) + encoded
    with pytest.raises(ValueError, match="trailing whitespace"):
        _inspect(tmp_path / "newline.safetensors", contents)


def test_rejects_oversize_header_before_reading_it(tmp_path: Path) -> None:
    contents = struct.pack("<Q", MAX_HEADER_BYTES + 1) + b"{}"
    with pytest.raises(ValueError, match="header size exceeds"):
        _inspect(tmp_path / "oversize.safetensors", contents)


def test_rejects_wrong_identity_and_symlink(tmp_path: Path) -> None:
    contents = _container({}, b"")
    path = tmp_path / "model.safetensors"
    path.write_bytes(contents)
    with pytest.raises(ValueError, match="SHA-256 differs"):
        _inspect_private_safetensors(
            path.absolute(), expected_bytes=len(contents), expected_sha256="0" * 64
        )

    link = tmp_path / "link.safetensors"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="single-link regular file"):
        _inspect_private_safetensors(
            link.absolute(),
            expected_bytes=len(contents),
            expected_sha256=hashlib.sha256(contents).hexdigest(),
        )


def test_rejects_relative_path_and_boolean_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        _inspect_private_safetensors(
            Path("model.safetensors"), expected_bytes=9, expected_sha256="0" * 64
        )
    with pytest.raises(ValueError, match="byte count"):
        _inspect_private_safetensors(
            (tmp_path / "model.safetensors").absolute(),
            expected_bytes=True,
            expected_sha256="0" * 64,
        )
