from __future__ import annotations

import ast
from pathlib import Path


SOURCES = (
    Path(__file__).parents[1]
    / "src"
    / "sunofriend"
    / "separation_checkpoint_policy.py",
    Path(__file__).parents[1]
    / "src"
    / "sunofriend"
    / "separation_execution_admission.py",
)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_policy_modules_have_no_io_execution_or_deserialization_surface() -> None:
    forbidden_imports = {
        "asyncio",
        "coremltools",
        "ctypes",
        "importlib",
        "multiprocessing",
        "onnx",
        "os",
        "pathlib",
        "pickle",
        "runpy",
        "socket",
        "safetensors",
        "subprocess",
        "torch",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "deserialize",
        "eval",
        "exec",
        "fork",
        "forkpty",
        "import_module",
        "load",
        "loads",
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
    for source in SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {
                    alias.name.split(".", 1)[0] for alias in node.names
                } & forbidden_imports
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".", 1)[0] not in forbidden_imports
                if node.level:
                    assert node.module == "separation_checkpoint_policy"
            elif isinstance(node, ast.Call):
                qualified = _qualified_name(node.func)
                name = qualified.rsplit(".", 1)[-1]
                assert name not in forbidden_calls or qualified == "re.compile"
                assert not name.startswith(("exec", "spawn"))
        assert not any(
            isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree)
        )


def test_execution_capabilities_are_literal_false_and_providers_empty() -> None:
    checkpoint_tree = ast.parse(SOURCES[0].read_text(encoding="utf-8"))
    admission_tree = ast.parse(SOURCES[1].read_text(encoding="utf-8"))

    checkpoint_assignments = {
        target.id: node.value
        for node in checkpoint_tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    admission_assignments = {
        target.id: node.value
        for node in admission_tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    checkpoint_capability = checkpoint_assignments[
        "CHECKPOINT_EXECUTION_POLICY_SUPPORTED"
    ]
    assert isinstance(checkpoint_capability, ast.Constant)
    assert checkpoint_capability.value is False
    for name in (
        "REAL_SEPARATION_EXECUTION_SUPPORTED",
        "RUNTIME_CLOSURE_CAPABILITY_SUPPORTED",
        "OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED",
        "RESOURCE_LIMIT_CAPABILITY_SUPPORTED",
    ):
        value = admission_assignments[name]
        assert isinstance(value, ast.Constant)
        assert value.value is False

    for tree, names in (
        (checkpoint_tree, {"SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS"}),
        (
            admission_tree,
            {
                "SUPPORTED_DESCENDANT_POLICY_PROVIDER_IDS",
                "SUPPORTED_ISOLATION_PROVIDER_IDS",
            },
        ),
    ):
        annotations = {
            node.target.id: node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        }
        for name in names:
            value = annotations[name]
            assert isinstance(value, ast.Call)
            assert _qualified_name(value.func) == "frozenset"
            assert not value.args
            assert not value.keywords


def test_public_functions_accept_no_callback_runner_or_executor() -> None:
    forbidden_words = {
        "callback",
        "executor",
        "factory",
        "launcher",
        "runner",
        "spawner",
    }
    for source in SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
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
                for word in forbidden_words
                if word in argument.arg.casefold()
            }
