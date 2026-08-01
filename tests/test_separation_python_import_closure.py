from __future__ import annotations

import types
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from sunofriend._separation_python_import_closure import (
    _capture_python_import_closure_claim,
    _mark_python_import_closure_stable,
    _validate_verified_python_import_closure,
    _verify_python_import_closure_claim,
)


ROOT_IDS = (
    "source_overlay",
    "runtime_environment",
    "repository",
    "base_runtime",
    "system_library",
    "system_usr_lib",
)


def test_child_capture_and_parent_reopen_bind_path_free_module_closure(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    module_path = roots["repository"] / "src" / "fixture.py"
    module_path.parent.mkdir()
    module_path.write_text("VALUE = 42\n", encoding="utf-8")
    modules = _modules(module_path)

    claim = _capture_python_import_closure_claim(roots=roots, modules=modules)
    stable = _mark_python_import_closure_stable(claim, modules=modules)
    verified = _verify_python_import_closure_claim(stable, roots=roots)
    _validate_verified_python_import_closure(verified)

    assert verified["python_sys_modules_closure_bound"] is True
    assert verified["native_non_module_loads_bound"] is False
    assert verified["hash_before_exec_path_toctou_closed"] is False
    assert verified["module_count"] == 3
    assert verified["file_count"] == 1
    assert verified["files"][0]["relative_path"] == "src/fixture.py"
    assert "/Users/" not in repr(verified)


def test_parent_rejects_module_file_changed_after_child_claim(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    module_path = roots["repository"] / "fixture.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    modules = _modules(module_path)
    claim = _capture_python_import_closure_claim(roots=roots, modules=modules)
    stable = _mark_python_import_closure_stable(claim, modules=modules)

    module_path.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="file identity differs"):
        _verify_python_import_closure_claim(stable, roots=roots)


def test_capture_rejects_unclassified_memory_module(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    module = types.ModuleType("fixture_memory")

    with pytest.raises(ValueError, match="unclassified no-file module"):
        _capture_python_import_closure_claim(
            roots=roots, modules={"fixture_memory": module}
        )


def _roots(tmp_path: Path) -> MappingProxyType[str, Path]:
    result = {}
    for name in ROOT_IDS:
        path = tmp_path / name
        path.mkdir()
        result[name] = path
    return MappingProxyType(result)


def _modules(module_path: Path) -> dict[str, types.ModuleType]:
    file_module = types.ModuleType("fixture.file")
    file_module.__file__ = str(module_path)
    built_in = types.ModuleType("fixture_builtin")
    built_in.__spec__ = SimpleNamespace(origin="built-in")
    namespace = types.ModuleType("fixture_namespace")
    namespace.__path__ = []
    return {
        "fixture.file": file_module,
        "fixture_builtin": built_in,
        "fixture_namespace": namespace,
    }
