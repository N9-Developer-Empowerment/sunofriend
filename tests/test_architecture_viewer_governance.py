from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools.architecture_viewer.analyzer import analyse_source_tree
from devtools.architecture_viewer.contracts import evaluate_contracts
from devtools.architecture_viewer.diffing import (
    assess_ratchet,
    compare_architectures,
    load_architecture_snapshot,
)
from devtools.architecture_viewer.queries import (
    dependency_path_query,
    module_query,
    neighbourhood_query,
    violations_query,
)
from devtools.architecture_viewer.renderer import build_architecture_viewer


def _write_package(repository: Path, *, ignores: list[dict[str, str]] | None = None) -> tuple[Path, Path]:
    package = repository / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("\"\"\"Example.\"\"\"\n", encoding="utf-8")
    (package / "a.py").write_text(
        '''"""Core module."""
import importlib
from typing import TYPE_CHECKING
from .b import B

if TYPE_CHECKING:
    from .d import D

try:
    from .e import E
except ImportError:
    E = None

def delayed():
    from .c import C
    return C()

def dynamic():
    return importlib.import_module(".f", __package__)
''',
        encoding="utf-8",
    )
    for name in "bcdef":
        (package / f"{name}.py").write_text(
            f'class {name.upper()}:\n    pass\n', encoding="utf-8"
        )
    contracts: list[dict[str, object]] = [
        {
            "id": "core-does-not-import-support",
            "type": "forbidden",
            "source": {"groups": ["core"]},
            "target": {"groups": ["support"]},
        }
    ]
    if ignores is not None:
        contracts[0]["ignores"] = ignores
    groups = repository / "groups.json"
    groups.write_text(
        json.dumps(
            {
                "schema": "sunofriend-architecture-groups.v2",
                "default_group": "support",
                "groups": [
                    {
                        "id": "system",
                        "label": "System",
                        "children": [
                            {
                                "id": "core",
                                "label": "Core",
                                "modules": ["a", "b"],
                            },
                            {
                                "id": "support",
                                "label": "Support",
                            },
                            {
                                "id": "empty",
                                "label": "Empty but visible",
                            },
                        ],
                    }
                ],
                "contracts": contracts,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return package, groups


def test_nested_groups_and_import_provenance_are_exact(tmp_path: Path) -> None:
    package, groups = _write_package(tmp_path)

    document = analyse_source_tree(package, repository_root=tmp_path, groups_path=groups)

    assert document["top_level_groups"] == ["system"]
    assert next(group for group in document["groups"] if group["id"] == "empty")[
        "module_count"
    ] == 0
    assert document["modules"]["example.a"]["group_path"] == ["system", "core"]
    assert document["modules"]["example.c"]["group_path"] == ["system", "support"]
    dependencies = {
        item["module"]: item["occurrences"][0]
        for item in document["modules"]["example.a"]["imports"]
    }
    assert dependencies["example.b"]["runtime"] == "module"
    assert dependencies["example.c"] == {
        "line": 15,
        "end_line": 15,
        "kind": "from",
        "requested": ".c",
        "symbols": ["C"],
        "confidence": "exact",
        "scope": "function:delayed",
        "runtime": "deferred",
        "guard": "none",
    }
    assert dependencies["example.d"]["guard"] == "type_checking"
    assert dependencies["example.e"]["guard"] == "try"
    assert dependencies["example.f"]["kind"] == "dynamic"
    assert dependencies["example.f"]["confidence"] == "literal_dynamic"
    assert len(document["violations"]) == 4
    assert all(item["occurrences"] for item in document["violations"])


def test_static_effect_candidates_resolve_aliases_and_keyword_open_mode(tmp_path: Path) -> None:
    package = tmp_path / "src" / "effectpkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "effects.py").write_text(
        '''import requests as rq
import subprocess as sp

def actions():
    sp.run(["true"])
    rq.get("https://invalid.example")
    open("artifact", mode="w")
''',
        encoding="utf-8",
    )

    document = analyse_source_tree(package, repository_root=tmp_path)

    effects = document["modules"]["effectpkg.effects"]["effects"]
    assert [(item["operation"], item["kind"]) for item in effects] == [
        ("subprocess.run", "process"),
        ("requests.get", "network"),
        ("open", "filesystem_write"),
    ]


def test_contract_ignore_requires_a_review_boundary(tmp_path: Path) -> None:
    package, groups = _write_package(
        tmp_path,
        ignores=[
            {
                "source": "example.a",
                "target": "example.c",
                "reason": "Temporary fixture exception.",
            }
        ],
    )

    with pytest.raises(ValueError, match="until date or review_condition"):
        analyse_source_tree(package, repository_root=tmp_path, groups_path=groups)


@pytest.mark.parametrize(
    ("contract", "source", "target"),
    [
        (
            {
                "id": "allowed-targets",
                "type": "allowed",
                "source": {"groups": ["left"]},
                "target": {"modules": ["pkg.allowed"]},
            },
            "pkg.left",
            "pkg.right",
        ),
        (
            {
                "id": "independent-sides",
                "type": "independence",
                "members": [{"groups": ["left"]}, {"groups": ["right"]}],
            },
            "pkg.left",
            "pkg.right",
        ),
        (
            {
                "id": "layer-direction",
                "type": "layers",
                "layers": [
                    {"id": "upper", "selector": {"groups": ["left"]}},
                    {"id": "lower", "selector": {"groups": ["right"]}},
                ],
            },
            "pkg.right",
            "pkg.left",
        ),
    ],
)
def test_edge_contract_types_retain_exact_occurrences(
    contract: dict[str, object],
    source: str,
    target: str,
) -> None:
    occurrence = {"line": 7, "kind": "from"}
    architecture: dict[str, object] = {
        "modules": {
            "pkg.left": {
                "short_name": "left",
                "group": "left",
                "imports": [],
            },
            "pkg.right": {
                "short_name": "right",
                "group": "right",
                "imports": [],
            },
            "pkg.allowed": {
                "short_name": "allowed",
                "group": "right",
                "imports": [],
            },
        },
        "groups": [
            {"id": "left", "path": ["left"]},
            {"id": "right", "path": ["right"]},
        ],
        "cycles": [],
        "stats": {},
    }
    architecture["modules"][source]["imports"] = [
        {"module": target, "occurrences": [occurrence]}
    ]

    evaluate_contracts(architecture, [contract])

    assert architecture["violations"] == [
        {
            "contract": contract["id"],
            "contract_type": contract["type"],
            "severity": "error",
            "source": source,
            "target": target,
            "chain": [source, target],
            "message": architecture["violations"][0]["message"],
            "occurrences": [occurrence],
        }
    ]


def test_acyclic_contract_reports_each_cyclic_edge_with_source_evidence(tmp_path: Path) -> None:
    package = tmp_path / "src" / "cycle"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text("from .b import B\nclass A: pass\n", encoding="utf-8")
    (package / "b.py").write_text("from .a import A\nclass B: pass\n", encoding="utf-8")
    groups = tmp_path / "groups.json"
    groups.write_text(
        json.dumps(
            {
                "schema": "sunofriend-architecture-groups.v2",
                "default_group": "domain",
                "groups": [{"id": "domain", "label": "Domain"}],
                "contracts": [
                    {
                        "id": "domain-is-acyclic",
                        "type": "acyclic",
                        "selector": {"groups": ["domain"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = analyse_source_tree(package, repository_root=tmp_path, groups_path=groups)

    assert [(item["source"], item["target"]) for item in document["violations"]] == [
        ("cycle.a", "cycle.b"),
        ("cycle.b", "cycle.a"),
    ]
    assert all(item["chain"][0] == item["chain"][-1] for item in document["violations"])
    assert all(item["occurrences"][0]["line"] == 1 for item in document["violations"])


def test_diff_ratchet_and_agent_queries_are_bounded(tmp_path: Path) -> None:
    package = tmp_path / "src" / "querypkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text("from .b import B\nclass A: pass\n", encoding="utf-8")
    (package / "b.py").write_text("class B: pass\n", encoding="utf-8")
    before = analyse_source_tree(package, repository_root=tmp_path)
    (package / "b.py").write_text(
        "from .a import A\nclass B: pass\ndef exposed(): return A()\n",
        encoding="utf-8",
    )
    (package / "c.py").write_text("class C: pass\n", encoding="utf-8")
    after = analyse_source_tree(package, repository_root=tmp_path)

    comparison = compare_architectures(before, after)

    assert comparison["modules"]["added"] == ["querypkg.c"]
    assert comparison["dependencies"]["added"][0]["source"] == "querypkg.b"
    assert comparison["dependencies"]["added"][0]["target"] == "querypkg.a"
    assert comparison["dependencies"]["added"][0]["occurrences"][0]["line"] == 1
    assert comparison["cycles"]["added"] == [["querypkg.a", "querypkg.b"]]
    assert comparison["summary"]["group_metrics_changed"] == 1
    assert comparison["summary"]["module_metrics_changed"] == 2
    assert assess_ratchet(comparison, after) == [
        {"kind": "new_static_cycle", "modules": ["querypkg.a", "querypkg.b"]}
    ]
    after["stats"]["test_parse_error_count"] = 1
    assert assess_ratchet(comparison, after)[-1] == {
        "kind": "test_parse_errors",
        "count": 1,
    }
    assert module_query(after, "a")["module"]["name"] == "querypkg.a"
    assert neighbourhood_query(after, "querypkg.a", depth=1)["subject"] == "querypkg.a"
    assert dependency_path_query(after, "querypkg.b", "querypkg.a")["chain"] == [
        "querypkg.b",
        "querypkg.a",
    ]
    assert violations_query(after)["violations"] == []
    with pytest.raises(ValueError, match="between 0 and 8"):
        neighbourhood_query(after, "querypkg.a", depth=9)


def test_snapshot_integrity_and_public_method_surface_are_compared(tmp_path: Path) -> None:
    package = tmp_path / "src" / "surfacepkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    module = package / "api.py"
    module.write_text(
        "class API:\n    def run(self, value: int) -> int:\n        return value\n",
        encoding="utf-8",
    )
    before = analyse_source_tree(package, repository_root=tmp_path)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(before), encoding="utf-8")
    assert load_architecture_snapshot(snapshot)["architecture_sha256"] == before["architecture_sha256"]
    tampered = json.loads(snapshot.read_text(encoding="utf-8"))
    tampered["modules"]["surfacepkg.api"]["path"] = "outside.py"
    snapshot.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity hash differs"):
        load_architecture_snapshot(snapshot)

    module.write_text(
        "class API:\n    def run(self, value: int, mode: str = 'plain') -> int:\n        return value\n",
        encoding="utf-8",
    )
    after = analyse_source_tree(package, repository_root=tmp_path)
    comparison = compare_architectures(before, after)
    assert comparison["summary"]["public_interfaces_changed"] == 1
    change = comparison["public_interfaces"][0]
    assert change["removed"][0]["qualified_name"] == "API.run"
    assert change["added"][0]["qualified_name"] == "API.run"


def test_code_pages_are_collision_safe_and_renderer_rejects_path_tampering(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src" / "pagepkg"
    nested = package / "a"
    nested.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a--b.py").write_text("value = 1\n", encoding="utf-8")
    (nested / "__init__.py").write_text("", encoding="utf-8")
    (nested / "b.py").write_text("value = 2\n", encoding="utf-8")
    document = analyse_source_tree(package, repository_root=tmp_path)
    pages = [module["code_page"] for module in document["modules"].values()]
    assert len(pages) == len(set(pages))

    document["modules"]["pagepkg.a--b"]["path"] = "outside.py"
    with pytest.raises(ValueError, match="integrity hash differs"):
        build_architecture_viewer(
            document,
            source_root=package,
            repository_root=tmp_path,
            output_root=tmp_path / "viewer",
        )


def test_test_tree_symlink_escape_fails_closed(tmp_path: Path) -> None:
    package = tmp_path / "src" / "linkpkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    outside = tmp_path / "outside_test.py"
    outside.write_text("import linkpkg\n", encoding="utf-8")
    link = tests / "test_link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(ValueError, match="outside test root"):
        analyse_source_tree(
            package,
            repository_root=tmp_path,
            test_root=tests,
        )
