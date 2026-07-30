from __future__ import annotations

import ast
from pathlib import Path


SOURCE = (
    Path(__file__).parents[1]
    / "src"
    / "sunofriend"
    / "separation_launch_contract.py"
)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_launch_contract_has_no_execution_or_dynamic_import_surface() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden_imports = {
        "asyncio",
        "ctypes",
        "importlib",
        "multiprocessing",
        "os",
        "runpy",
        "socket",
        "subprocess",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "fork",
        "forkpty",
        "lstat",
        "mkdir",
        "open",
        "popen",
        "posix_spawn",
        "posix_spawnp",
        "read_bytes",
        "read_text",
        "rename",
        "replace",
        "resolve",
        "rmdir",
        "stat",
        "system",
        "unlink",
        "write_bytes",
        "write_text",
    }
    forbidden_call_prefixes = ("exec", "spawn")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            } & forbidden_imports
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
            if node.level:
                assert node.module in {
                    "separation_runtime_artifact",
                    "separation_worker_contract",
                }
        elif isinstance(node, ast.Call):
            qualified = _qualified_name(node.func)
            name = qualified.rsplit(".", 1)[-1]
            assert name not in forbidden_calls or qualified == "re.compile"
            assert not name.startswith(forbidden_call_prefixes)


def test_public_functions_accept_no_provider_launcher_callback_or_runner() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden_surface_words = {
        "callback",
        "executor",
        "factory",
        "launcher",
        "provider",
        "runner",
        "spawner",
    }
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        arguments = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        assert not {
            word
            for argument in arguments
            for word in forbidden_surface_words
            if word in argument.arg.casefold()
        }


def test_execution_support_is_literal_false_and_no_async_functions_exist() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    assignments = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    value = assignments["REAL_WORKER_EXECUTION_SUPPORTED"]
    assert isinstance(value, ast.Constant)
    assert value.value is False
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
