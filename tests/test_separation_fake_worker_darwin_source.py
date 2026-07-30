from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from sunofriend._separation_fake_execution_records import (
    _EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    _EXPECTED_FAKE_WORKER_SOURCE_SHA256,
)
from sunofriend._separation_fake_transport_records import _fixture_wav_bytes


REPOSITORY = Path(__file__).resolve().parents[1]
WORKER = (
    REPOSITORY
    / "src"
    / "sunofriend"
    / "_separation_fake_worker_darwin.py"
)


def _source() -> tuple[bytes, str, ast.Module]:
    payload = WORKER.read_bytes()
    text = payload.decode("utf-8")
    return payload, text, ast.parse(text)


def test_worker_source_is_exactly_pinned_and_not_public() -> None:
    payload, _text, _tree = _source()
    assert len(payload) == _EXPECTED_FAKE_WORKER_SOURCE_BYTES
    assert hashlib.sha256(payload).hexdigest() == (
        _EXPECTED_FAKE_WORKER_SOURCE_SHA256
    )

    package = (REPOSITORY / "src" / "sunofriend" / "__init__.py").read_text()
    cli = (REPOSITORY / "src" / "sunofriend" / "cli.py").read_text()
    assert "_separation_fake_worker_darwin" not in package
    assert "_separation_fake_worker_darwin" not in cli


def test_worker_main_hardens_fd345_before_any_other_action() -> None:
    _payload, _text, tree = _source()
    effectful = [
        node
        for node in tree.body
        if not isinstance(
            node,
            (
                ast.Expr,
                ast.Import,
                ast.ImportFrom,
                ast.Assign,
                ast.AnnAssign,
                ast.FunctionDef,
            ),
        )
    ]
    assert isinstance(effectful[0], ast.For)
    assert ast.unparse(effectful[0]) == (
        "for _transport_descriptor in (3, 4, 5):\n"
        "    os.set_inheritable(_transport_descriptor, False)"
    )

    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    first = main.body[0]
    assert isinstance(first, ast.Expr)
    assert isinstance(first.value, ast.Call)
    assert isinstance(first.value.func, ast.Name)
    assert first.value.func.id == "_harden_transport_descriptors"

    harden = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_harden_transport_descriptors"
    )
    assert "os.set_inheritable(descriptor, False)" in ast.unparse(harden)
    assert "_TRANSPORT_FDS = (3, 4, 5)" in _text


def test_worker_has_only_the_fixed_stdlib_and_no_expansive_surface() -> None:
    _payload, text, tree = _source()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            imports.add(node.module)
    assert imports == {
        "__future__",
        "errno",
        "fcntl",
        "hashlib",
        "json",
        "os",
        "resource",
        "stat",
        "struct",
        "typing",
    }
    forbidden = (
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "http",
        "pathlib",
        "pickle",
        "torch",
        "tensorflow",
        "importlib",
        "multiprocessing",
        "threading",
        "os.open",
        "open(",
        "os.fork",
        "os.exec",
        "os.spawn",
        "eval(",
        "exec(",
        "__import__",
    )
    for token in forbidden:
        assert token not in text
    assert "sunofriend" not in "\n".join(
        line
        for line in text.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    )


def test_worker_descriptor_io_and_fixture_are_narrow() -> None:
    _payload, text, tree = _source()
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    ]
    call_names = {node.func.attr for node in calls}
    assert call_names <= {
        "fstat",
        "fsync",
        "ftruncate",
        "get_inheritable",
        "geteuid",
        "getpgrp",
        "getpid",
        "pread",
        "pwrite",
        "set_inheritable",
    }
    assert "os.ftruncate(_RESULT_FD, 0)" in text
    assert "os.pwrite(_RESULT_FD" in text
    pread_sources = {
        ast.unparse(node.args[0])
        for node in calls
        if node.func.attr == "pread"
    }
    assert pread_sources == {"_CHECKPOINT_FD", "descriptor"}
    assert "_pread_exact(_REQUEST_FD" in text
    assert "_fixture_wav_bytes(role: str)" in text

    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_fixture_wav_bytes"
    )
    function_module = ast.fix_missing_locations(
        ast.Module(body=[function], type_ignores=[])
    )
    namespace: dict[str, object] = {
        "hashlib": __import__("hashlib"),
        "struct": __import__("struct"),
    }
    exec(compile(function_module, str(WORKER), "exec"), namespace)
    worker_fixture = namespace["_fixture_wav_bytes"]
    for role in ("bass", "drums", "keys", "vocals"):
        assert worker_fixture(role) == _fixture_wav_bytes(role)
