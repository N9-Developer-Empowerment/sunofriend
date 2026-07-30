from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from types import MappingProxyType

import pytest
import sunofriend._separation_checkpoint_canonical as canonical_module
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
import sunofriend.separation_checkpoint_inspection as inspection_module

from sunofriend._separation_checkpoint_canonical import (
    canonical_json_bytes,
    canonical_sha256,
    deep_freeze,
    plain,
)


def test_canonical_json_bytes_and_hash_match_v1_encoding() -> None:
    value = {"z": [1, True, None], "a": "é"}
    expected = b'{"a":"\\u00e9","z":[1,true,null]}'

    assert canonical_json_bytes(value) == expected
    assert canonical_sha256(value) == hashlib.sha256(expected).hexdigest()


@pytest.mark.parametrize(
    ("value", "native_type"),
    [
        ({"bad": object()}, TypeError),
        ({"bad": float("nan")}, ValueError),
    ],
)
def test_canonical_json_preserves_native_or_custom_error_contract(
    value: dict[str, object],
    native_type: type[Exception],
) -> None:
    with pytest.raises(native_type) as native:
        canonical_json_bytes(value)
    assert native.value.__cause__ is None

    with pytest.raises(ValueError) as wrapped:
        canonical_json_bytes(value, error_message="custom canonical error")
    assert str(wrapped.value) == "custom canonical error"
    assert type(wrapped.value.__cause__) is native_type

    with pytest.raises(native_type) as lease_error:
        lease_module._hash(value)  # noqa: SLF001
    assert str(lease_error.value) == str(native.value)
    assert lease_error.value.__cause__ is None
    with pytest.raises(
        ValueError,
        match="^checkpoint inspection is not canonical JSON$",
    ):
        inspection_module._hash(value)  # noqa: SLF001


def test_plain_and_deep_freeze_recursively_copy_json_containers() -> None:
    original = MappingProxyType({"nested": ({"value": [1, 2]},)})

    copied = plain(original)
    assert copied == {"nested": [{"value": [1, 2]}]}
    assert isinstance(copied, dict)
    assert isinstance(copied["nested"], list)

    frozen = deep_freeze(copied)
    assert isinstance(frozen, MappingProxyType)
    assert isinstance(frozen["nested"], tuple)
    assert isinstance(frozen["nested"][0], MappingProxyType)
    assert frozen["nested"][0]["value"] == (1, 2)
    with pytest.raises(TypeError):
        frozen["new"] = "blocked"


def test_canonical_helper_has_no_io_model_process_or_network_api() -> None:
    source = Path(canonical_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed_import_roots = {
        "__future__",
        "hashlib",
        "json",
        "types",
        "typing",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "open",
        "Path.open",
        "Path.read_bytes",
        "Path.read_text",
        "Path.write_bytes",
        "Path.write_text",
    }

    def qualified_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = qualified_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {
                alias.name.split(".", 1)[0] for alias in node.names
            } <= allowed_import_roots
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] in allowed_import_roots
        elif isinstance(node, ast.Call):
            assert qualified_name(node.func) not in forbidden_calls
