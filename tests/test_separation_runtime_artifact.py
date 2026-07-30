from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import stat
from pathlib import Path
from typing import Any

import pytest
import sunofriend.separation_runtime_artifact as runtime_artifact_module

from sunofriend.separation_backend_preflight import (
    SEPARATION_PACKAGE_SOURCE_HASH_ALGORITHM,
)
from sunofriend.separation_runtime_artifact import (
    SEPARATION_RUNTIME_ARTIFACT_STATUS,
    SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM,
    SeparationRuntimeArtifactParentEvidence,
    build_separation_runtime_artifact,
    separation_runtime_artifact_sha256,
    separation_runtime_launcher_chain_sha256,
    separation_runtime_measurements_sha256,
    validate_separation_runtime_artifact,
)
from sunofriend.separation_worker_contract import (
    SeparationRuntimeArtifactIdentity,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_runtime_stability_digest_has_a_distinct_algorithm_domain() -> None:
    assert (
        SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM
        == "runtime-site-tree-stability-sha256-v1"
    )
    assert (
        SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM
        != SEPARATION_PACKAGE_SOURCE_HASH_ALGORITHM
    )


def _facts(
    *,
    inode: int,
    mode: int,
    size: int,
    mtime_ns: int = 1_000_000,
) -> dict[str, int]:
    return {
        "device": 17,
        "inode": inode,
        "mode": mode,
        "size": size,
        "mtime_ns": mtime_ns,
        "ctime_ns": mtime_ns + 1,
    }


def _ancestor_facts(*, inode: int) -> dict[str, int]:
    return {
        "device": 17,
        "inode": inode,
        "mode": stat.S_IFDIR | 0o755,
        "size": 0,
        "mtime_ns": 0,
        "ctime_ns": 0,
    }


def _file(
    path: str,
    label: str,
    *,
    inode: int,
    size: int,
    executable: bool = False,
) -> dict[str, Any]:
    return {
        "path": path,
        "kind": "native_executable" if executable else "regular_file",
        "sha256": _sha(label),
        "bytes": size,
        "lstat": _facts(
            inode=inode,
            mode=stat.S_IFREG | (0o755 if executable else 0o644),
            size=size,
        ),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _inputs(*, multichain: bool = False) -> dict[str, Any]:
    launcher = "/private/tmp/sunofriend/.venv/bin/python"
    if multichain:
        middle = "/private/tmp/sunofriend/.venv/bin/python3"
        final_path = "/private/tmp/sunofriend/.venv/bin/python3.12"
        chain = [
            {
                "canonical_path": launcher,
                "kind": "symlink",
                "lstat": _facts(
                    inode=101,
                    mode=stat.S_IFLNK | 0o777,
                    size=len("python3"),
                ),
                "raw_target": "python3",
                "canonical_resolved_target": middle,
            },
            {
                "canonical_path": middle,
                "kind": "symlink",
                "lstat": _facts(
                    inode=102,
                    mode=stat.S_IFLNK | 0o777,
                    size=len("python3.12"),
                ),
                "raw_target": "python3.12",
                "canonical_resolved_target": final_path,
            },
            {
                "canonical_path": final_path,
                "kind": "native_executable",
                "lstat": _facts(
                    inode=103,
                    mode=stat.S_IFREG | 0o755,
                    size=8192,
                ),
                "raw_target": None,
                "canonical_resolved_target": final_path,
            },
        ]
    else:
        final_path = "/opt/homebrew/Cellar/python@3.12/3.12.10/bin/python3.12"
        chain = [
            {
                "canonical_path": launcher,
                "kind": "symlink",
                "lstat": _facts(
                    inode=101,
                    mode=stat.S_IFLNK | 0o777,
                    size=len(final_path),
                ),
                "raw_target": final_path,
                "canonical_resolved_target": final_path,
            },
            {
                "canonical_path": final_path,
                "kind": "native_executable",
                "lstat": _facts(
                    inode=102,
                    mode=stat.S_IFREG | 0o755,
                    size=8192,
                ),
                "raw_target": None,
                "canonical_resolved_target": final_path,
            },
        ]
    final = _file(
        final_path,
        "native executable",
        inode=chain[-1]["lstat"]["inode"],
        size=8192,
        executable=True,
    )
    final["lstat"] = copy.deepcopy(chain[-1]["lstat"])
    chain_hash = separation_runtime_launcher_chain_sha256(chain)
    identity = SeparationRuntimeArtifactIdentity(
        path=Path(launcher),
        sha256=final["sha256"],
        bytes=final["bytes"],
        verified_launcher_chain_sha256=chain_hash,
    )
    site_path = "/private/tmp/sunofriend/.venv/lib/python3.12/site-packages"
    inputs = {
        "launcher_chain": chain,
        "final_native_executable": final,
        "pyvenv_config": _file(
            "/private/tmp/sunofriend/.venv/pyvenv.cfg",
            "pyvenv config",
            inode=201,
            size=144,
        ),
        "site_packages": {
            "path": site_path,
            "kind": "directory",
            "lstat": _facts(
                inode=202,
                mode=stat.S_IFDIR | 0o755,
                size=256,
            ),
            "package_tree_algorithm": (SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM),
            "package_tree_sha256": _sha("installed package tree"),
        },
        "worker": _file(
            "/private/tmp/sunofriend/source/separation_worker.py",
            "worker",
            inode=301,
            size=4096,
        ),
        "dependency_lock": _file(
            "/private/tmp/sunofriend/source/ai-lock.txt",
            "dependency lock",
            inode=302,
            size=1024,
        ),
        "worker_request_sha256": _sha("worker request"),
        "preflight_sha256": _sha("preflight"),
        "trusted_runtime_artifact": identity,
    }
    logical_paths = [
        *(item["canonical_path"] for item in chain),
        inputs["pyvenv_config"]["path"],
        inputs["site_packages"]["path"],
        inputs["worker"]["path"],
        inputs["dependency_lock"]["path"],
    ]
    ancestor_paths: set[str] = set()
    for leaf in logical_paths:
        parent = Path(leaf).parent
        while True:
            ancestor_paths.add(parent.as_posix())
            if parent == Path("/"):
                break
            parent = parent.parent
    inputs["ancestor_directories"] = [
        {
            "canonical_path": path,
            "kind": "directory",
            "lstat": _ancestor_facts(inode=1000 + index),
            "canonical_resolved_path": path,
        }
        for index, path in enumerate(
            sorted(
                ancestor_paths,
                key=lambda item: (len(Path(item).parts), item),
            )
        )
    ]
    measurements_hash = separation_runtime_measurements_sha256(
        launcher_chain=inputs["launcher_chain"],
        ancestor_directories=inputs["ancestor_directories"],
        final_native_executable=inputs["final_native_executable"],
        pyvenv_config=inputs["pyvenv_config"],
        site_packages=inputs["site_packages"],
        worker=inputs["worker"],
        dependency_lock=inputs["dependency_lock"],
    )
    inputs["trusted_parent_evidence"] = SeparationRuntimeArtifactParentEvidence(
        worker_request_sha256=inputs["worker_request_sha256"],
        preflight_sha256=inputs["preflight_sha256"],
        measurements_sha256=measurements_hash,
    )
    return inputs


def _build(inputs: dict[str, Any]) -> Any:
    return build_separation_runtime_artifact(**inputs)


def _trusted(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "trusted_runtime_artifact": inputs["trusted_runtime_artifact"],
        "trusted_parent_evidence": inputs["trusted_parent_evidence"],
        "trusted_worker_request_sha256": inputs["worker_request_sha256"],
        "trusted_preflight_sha256": inputs["preflight_sha256"],
    }


def _rehash(document: dict[str, Any]) -> None:
    document["artifact_sha256"] = separation_runtime_artifact_sha256(document)


def test_builds_realistic_private_venv_artifact_and_freezes_deeply() -> None:
    inputs = _inputs()
    artifact = _build(inputs)

    assert artifact["status"] == SEPARATION_RUNTIME_ARTIFACT_STATUS
    assert artifact["acceptance_eligible"] is False
    assert artifact["registration"]["runtime_artifact_sha256_registered"] is False
    assert artifact["registration"]["evidence_kind"] == (
        "parent_asserted_contract_evidence"
    )
    assert artifact["registration"]["execution_proven"] is False
    assert artifact["registration"]["toctou_closed"] is False
    assert artifact["registration"]["remeasure_before_exec_required"] is True
    assert artifact["runtime"]["launcher_chain"][0]["raw_target"].startswith(
        "/opt/homebrew/"
    )
    assert artifact["bindings"]["worker_request_sha256"] == _sha("worker request")
    assert artifact["artifact_sha256"] == separation_runtime_artifact_sha256(artifact)
    with pytest.raises(TypeError):
        artifact["runtime"]["pyvenv_config"]["sha256"] = _sha("changed")  # type: ignore[index]
    with pytest.raises(TypeError):
        artifact["runtime"]["launcher_chain"][0]["lstat"]["mtime_ns"] = 9  # type: ignore[index]


def test_relative_multi_link_chain_resolves_to_exact_next_entries() -> None:
    inputs = _inputs(multichain=True)
    artifact = _build(inputs)

    assert len(artifact["runtime"]["launcher_chain"]) == 3
    assert artifact["runtime"]["launcher_chain"][1]["raw_target"] == ("python3.12")
    assert artifact["runtime"]["final_native_executable"]["path"].endswith(
        "/.venv/bin/python3.12"
    )


def test_runtime_contract_is_pure_and_never_touches_path_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("pure contract attempted filesystem access")

    for method in (
        "exists",
        "is_dir",
        "is_file",
        "is_symlink",
        "lstat",
        "open",
        "read_bytes",
        "read_text",
        "resolve",
        "stat",
    ):
        monkeypatch.setattr(Path, method, fail)

    _build(_inputs(multichain=True))


def test_runtime_contract_ast_has_no_io_process_network_or_dynamic_execution() -> None:
    tree = ast.parse(inspect.getsource(runtime_artifact_module))
    forbidden_imports = {
        "asyncio",
        "http",
        "importlib",
        "multiprocessing",
        "os",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "getattr",
        "open",
        "setattr",
    }
    forbidden_attributes = {
        "exists",
        "is_dir",
        "is_file",
        "is_symlink",
        "iterdir",
        "lstat",
        "open",
        "read_bytes",
        "read_text",
        "resolve",
        "stat",
        "walk",
        "write_bytes",
        "write_text",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".", 1)[0] not in forbidden_imports
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attributes


def test_parent_evidence_requires_exact_parent_owned_type() -> None:
    inputs = _inputs()
    artifact = _build(inputs)
    trusted = _trusted(inputs)
    evidence = trusted["trusted_parent_evidence"]
    trusted["trusted_parent_evidence"] = {
        "worker_request_sha256": evidence.worker_request_sha256,
        "preflight_sha256": evidence.preflight_sha256,
        "measurements_sha256": evidence.measurements_sha256,
    }

    with pytest.raises(ValueError, match="parent-owned exact identity"):
        validate_separation_runtime_artifact(artifact, **trusted)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["launcher_chain"].__setitem__(
                8, copy.deepcopy(value["launcher_chain"][-1])
            ),
            "between 1 and 8",
        ),
        (
            lambda value: value["launcher_chain"][0].__setitem__(
                "canonical_path",
                "//private/tmp/sunofriend/.venv/bin/python",
            ),
            "canonical absolute",
        ),
        (
            lambda value: value["launcher_chain"][0].__setitem__(
                "raw_target", "//opt/homebrew/python"
            ),
            "unsafe",
        ),
        (
            lambda value: value["launcher_chain"][0].__setitem__(
                "raw_target", "../../outside/python"
            ),
            "upward escape",
        ),
        (
            lambda value: value["launcher_chain"][0].__setitem__(
                "raw_target", "bin/./python3"
            ),
            "path alias",
        ),
        (
            lambda value: value["launcher_chain"][0].__setitem__(
                "canonical_resolved_target",
                "/opt/homebrew/other-python",
            ),
            "raw target does not match",
        ),
        (
            lambda value: value["pyvenv_config"].__setitem__(
                "path", "/private/tmp/sunofriend/pyvenv.cfg"
            ),
            "escapes",
        ),
        (
            lambda value: value["site_packages"].__setitem__(
                "path", "/private/tmp/other/lib/python3.12/site-packages"
            ),
            "escapes",
        ),
    ],
)
def test_rejects_oversize_double_slash_and_path_escapes(
    mutation: Any, message: str
) -> None:
    inputs = _inputs()
    if message == "between 1 and 8":
        final = copy.deepcopy(inputs["launcher_chain"][-1])
        # Nine distinct synthetic entries are enough to exercise the bound;
        # target relationships are deliberately irrelevant because size is
        # checked first.
        inputs["launcher_chain"] = [
            {
                **copy.deepcopy(final),
                "canonical_path": (f"/private/tmp/sunofriend/.venv/bin/python{index}"),
            }
            for index in range(9)
        ]
    else:
        mutation(inputs)

    with pytest.raises(ValueError, match=message):
        _build(inputs)


def test_rejects_cycles_and_casefold_or_nfc_aliases() -> None:
    cycle = _inputs(multichain=True)
    cycle["launcher_chain"][1]["canonical_path"] = cycle["launcher_chain"][0][
        "canonical_path"
    ]
    cycle["launcher_chain"][0]["canonical_resolved_target"] = cycle["launcher_chain"][
        0
    ]["canonical_path"]
    cycle["launcher_chain"][0]["raw_target"] = cycle["launcher_chain"][0][
        "canonical_path"
    ]
    with pytest.raises(ValueError, match="cycle or NFC/casefold"):
        _build(cycle)

    alias = _inputs(multichain=True)
    alias["launcher_chain"][1]["canonical_path"] = (
        "/private/tmp/sunofriend/.VENV/bin/PYTHON"
    )
    alias["launcher_chain"][0]["canonical_resolved_target"] = alias["launcher_chain"][
        1
    ]["canonical_path"]
    alias["launcher_chain"][0]["raw_target"] = (
        "/private/tmp/sunofriend/.VENV/bin/PYTHON"
    )
    alias["launcher_chain"][1]["raw_target"] = alias["launcher_chain"][1][
        "canonical_resolved_target"
    ]
    with pytest.raises(ValueError, match="cycle or NFC/casefold"):
        _build(alias)

    decomposed = _inputs()
    decomposed["worker"]["path"] = "/private/tmp/sunofriend/source/cafe\u0301-worker.py"
    with pytest.raises(ValueError, match="canonical absolute"):
        _build(decomposed)


def test_rejects_changed_or_resigned_chain_facts_and_final_identity() -> None:
    inputs = _inputs()
    artifact = _plain(_build(inputs))
    artifact["runtime"]["launcher_chain"][0]["lstat"]["mtime_ns"] += 1
    artifact["runtime"]["launcher_chain_sha256"] = (
        separation_runtime_launcher_chain_sha256(artifact["runtime"]["launcher_chain"])
    )
    _rehash(artifact)
    with pytest.raises(ValueError, match="trusted runtime identity"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))

    artifact = _plain(_build(inputs))
    artifact["runtime"]["final_native_executable"]["sha256"] = _sha(
        "resigned executable"
    )
    artifact["bindings"]["trusted_runtime_identity"]["sha256"] = _sha(
        "resigned executable"
    )
    _rehash(artifact)
    with pytest.raises(ValueError, match="resigned runtime identity"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))


def test_rejects_resigned_request_or_preflight_binding() -> None:
    inputs = _inputs()
    artifact = _plain(_build(inputs))
    artifact["bindings"]["worker_request_sha256"] = _sha("substituted request")
    _rehash(artifact)
    with pytest.raises(ValueError, match="trusted request and preflight"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))

    artifact = _plain(_build(inputs))
    artifact["bindings"]["preflight_sha256"] = _sha("substituted preflight")
    _rehash(artifact)
    with pytest.raises(ValueError, match="trusted request and preflight"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))


@pytest.mark.parametrize(
    "component",
    ["worker", "dependency_lock"],
)
def test_rejects_self_signed_component_substitution(component: str) -> None:
    inputs = _inputs()
    artifact = _plain(_build(inputs))
    replacement = artifact["files"][component]
    replacement["path"] = f"/private/tmp/sunofriend/source/{component}-replacement.bin"
    replacement["sha256"] = _sha(f"replacement {component}")
    replacement["bytes"] = 2048
    replacement["lstat"] = _facts(
        inode=9001 if component == "worker" else 9002,
        mode=stat.S_IFREG | 0o644,
        size=2048,
    )
    _rehash(artifact)

    with pytest.raises(ValueError, match="changed or resigned"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))


def test_rejects_self_signed_config_and_package_tree_substitution() -> None:
    inputs = _inputs()
    artifact = _plain(_build(inputs))
    artifact["runtime"]["pyvenv_config"]["sha256"] = _sha("substituted config")
    artifact["runtime"]["site_packages"]["package_tree_sha256"] = _sha(
        "substituted tree"
    )
    _rehash(artifact)

    with pytest.raises(ValueError, match="changed or resigned"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))


def test_rejects_hardlink_alias_and_incomplete_or_resolved_ancestor() -> None:
    hardlink = _inputs()
    hardlink["dependency_lock"]["lstat"]["device"] = hardlink["worker"]["lstat"][
        "device"
    ]
    hardlink["dependency_lock"]["lstat"]["inode"] = hardlink["worker"]["lstat"]["inode"]
    with pytest.raises(ValueError, match="hardlink, firmlink or inode alias"):
        _build(hardlink)

    incomplete = _inputs()
    incomplete["ancestor_directories"].pop()
    with pytest.raises(ValueError, match="incomplete or contains extras"):
        _build(incomplete)

    resolved_alias = _inputs()
    resolved_alias["ancestor_directories"][1]["canonical_resolved_path"] = (
        "/private-resolved"
    )
    with pytest.raises(ValueError, match="symlink or resolved alias"):
        _build(resolved_alias)


def test_ancestor_evidence_requires_stable_identity_projection() -> None:
    inputs = _inputs()
    inputs["ancestor_directories"][0]["lstat"]["mtime_ns"] = 1

    with pytest.raises(ValueError, match="stable projection"):
        _build(inputs)


def test_final_facts_and_file_sizes_cannot_drift_inside_document() -> None:
    inputs = _inputs()
    artifact = _plain(_build(inputs))
    artifact["runtime"]["final_native_executable"]["lstat"]["ctime_ns"] += 1
    _rehash(artifact)
    with pytest.raises(ValueError, match="facts changed"):
        validate_separation_runtime_artifact(artifact, **_trusted(inputs))

    inputs = _inputs()
    inputs["worker"]["lstat"]["size"] += 1
    with pytest.raises(ValueError, match="bytes do not match"):
        _build(inputs)
