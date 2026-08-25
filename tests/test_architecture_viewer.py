from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools.architecture_viewer import analyse_source_tree, build_architecture_viewer


def _write_fixture(repository: Path) -> tuple[Path, Path]:
    package = repository / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '"""Example package."""\n__all__ = ["PublicA"]\nfrom .a import PublicA\n',
        encoding="utf-8",
    )
    (package / "a.py").write_text(
        '''"""Public A and its hidden implementation."""
from .b import PublicB

__all__ = ["PublicA"]

class PublicA:
    """The intentionally small public type."""

    def run(self, value: int) -> str:
        """Run through B."""
        return PublicB().render(value)

def _helper(value: str) -> str:
    return "<script>" + value
''',
        encoding="utf-8",
    )
    (package / "b.py").write_text(
        '''"""Public B."""
from .a import PublicA

class PublicB:
    def render(self, value: int) -> str:
        return str(value)
''',
        encoding="utf-8",
    )
    groups = repository / "groups.json"
    groups.write_text(
        json.dumps(
            {
                "schema": "sunofriend-architecture-groups.v1",
                "default_group": "other",
                "groups": [
                    {
                        "id": "domain",
                        "label": "Domain",
                        "description": "Fixture domain.",
                        "modules": ["a", "b"],
                        "prefixes": [],
                    },
                    {
                        "id": "other",
                        "label": "Other",
                        "description": "Unassigned fixture modules.",
                        "modules": [],
                        "prefixes": [],
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return package, groups


def test_analyser_extracts_groups_interfaces_dependencies_and_cycles(
    tmp_path: Path,
) -> None:
    package, groups = _write_fixture(tmp_path)

    document = analyse_source_tree(
        package,
        repository_root=tmp_path,
        groups_path=groups,
    )

    assert document["schema"] == "sunofriend-architecture-viewer.v2"
    assert document["stats"] == {
        "module_count": 3,
        "line_count": 23,
        "internal_dependency_count": 3,
        "internal_import_occurrence_count": 3,
        "external_package_count": 0,
        "cycle_count": 1,
        "parse_error_count": 0,
        "effect_candidate_count": 0,
        "static_call_relation_count": 1,
        "static_type_relation_count": 0,
        "contract_count": 0,
        "contract_violation_count": 0,
        "ignored_contract_violation_count": 0,
    }
    assert [group["id"] for group in document["groups"]] == ["domain", "other"]

    package_module = document["modules"]["example"]
    assert package_module["interface_source"] == "__all__"
    assert package_module["public_interface"] == [
        {
            "name": "PublicA",
            "qualified_name": "PublicA",
            "kind": "re-export",
            "signature": "PublicA",
            "line": 3,
            "end_line": 3,
            "summary": "Re-exported from .a.",
            "public": True,
        }
    ]

    module = document["modules"]["example.a"]
    assert module["group"] == "domain"
    assert module["interface_source"] == "__all__"
    assert [item["name"] for item in module["public_interface"]] == ["PublicA"]
    assert [item["name"] for item in module["implementation"]] == ["_helper"]
    assert module["public_interface"][0]["members"][0]["qualified_name"] == "PublicA.run"
    assert module["imports"] == [
        {
            "module": "example.b",
            "symbols": ["PublicB"],
            "occurrences": [
                {
                    "line": 2,
                    "end_line": 2,
                    "kind": "from",
                    "requested": ".b",
                    "symbols": ["PublicB"],
                    "confidence": "exact",
                    "scope": "module",
                    "runtime": "module",
                    "guard": "none",
                }
            ],
        }
    ]
    assert module["imported_by"] == ["example", "example.b"]
    assert module["cycle"] == 1
    assert module["calls"] == [
        {
            "source_definition": "PublicA.run",
            "target_module": "example.b",
            "target_symbol": "PublicB",
            "kind": "constructs",
            "line": 11,
            "confidence": "static_name_resolution",
        }
    ]
    assert document["cycles"] == [["example.a", "example.b"]]


def test_renderer_writes_fresh_private_offline_drill_down(tmp_path: Path) -> None:
    package, groups = _write_fixture(tmp_path)
    document = analyse_source_tree(
        package,
        repository_root=tmp_path,
        groups_path=groups,
    )
    output = tmp_path / "architecture-viewer"

    result = build_architecture_viewer(
        document,
        source_root=package,
        repository_root=tmp_path,
        output_root=output,
    )

    assert result == output
    index = (output / "index.html").read_text(encoding="utf-8")
    architecture = (output / "architecture.json").read_text(encoding="utf-8")
    source_page = (output / document["modules"]["example.a"]["code_page"]).read_text(
        encoding="utf-8"
    )
    assert "Architecture explorer" in index
    assert "default-src 'none'" in index
    assert "fetch(" not in index
    assert "XMLHttpRequest" not in index
    assert str(tmp_path) not in index
    assert str(tmp_path) not in architecture
    assert 'id="L14"' in source_page
    assert "&lt;script&gt;" in source_page
    assert "<script>" not in source_page
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "index.html").stat().st_mode & 0o777 == 0o600
    assert (output / "code").stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        build_architecture_viewer(
            document,
            source_root=package,
            repository_root=tmp_path,
            output_root=output,
        )


def test_analyser_rejects_a_source_tree_outside_the_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="inside repository root"):
        analyse_source_tree(outside, repository_root=repository)


def test_renderer_rejects_source_changed_after_analysis(tmp_path: Path) -> None:
    package, groups = _write_fixture(tmp_path)
    document = analyse_source_tree(
        package,
        repository_root=tmp_path,
        groups_path=groups,
    )
    (package / "a.py").write_text("changed = True\n", encoding="utf-8")
    output = tmp_path / "stale-viewer"

    with pytest.raises(ValueError, match="source changed after analysis"):
        build_architecture_viewer(
            document,
            source_root=package,
            repository_root=tmp_path,
            output_root=output,
        )

    assert not output.exists()


def test_renderer_rejects_source_added_after_analysis(tmp_path: Path) -> None:
    package, groups = _write_fixture(tmp_path)
    document = analyse_source_tree(
        package,
        repository_root=tmp_path,
        groups_path=groups,
    )
    (package / "new_module.py").write_text("new = True\n", encoding="utf-8")
    output = tmp_path / "stale-viewer"

    with pytest.raises(ValueError, match="source tree changed after analysis"):
        build_architecture_viewer(
            document,
            source_root=package,
            repository_root=tmp_path,
            output_root=output,
        )

    assert not output.exists()
