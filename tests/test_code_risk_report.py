from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from devtools.architecture_viewer.analyzer import analyse_source_tree
from devtools.architecture_viewer.overlays import build_overlay_bundle
from devtools.code_risk import (
    ComplexityFunction,
    build_parser,
    build_code_risk_document,
    build_coverage_binding_document,
    collect_complexities,
    generate_code_risk_report,
    serialize_report,
    write_fresh_report,
)


def _fixture(repository: Path) -> tuple[Path, dict[str, object]]:
    package = repository / "src" / "riskpkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "risk.py").write_text(
        """def outer(flag: bool) -> int:
    def inner(value: bool) -> int:
        if value:
            return 1
        return 0
    return inner(flag)

class API:
    def run(self, value: int) -> int:
        return value
""",
        encoding="utf-8",
    )
    architecture = analyse_source_tree(package, repository_root=repository)
    return package, architecture


def _summary(*, covered_lines: int, statements: int, covered_branches: int, branches: int):
    return {
        "covered_lines": covered_lines,
        "num_statements": statements,
        "covered_branches": covered_branches,
        "num_branches": branches,
    }


def _coverage(architecture: dict[str, object]) -> dict[str, object]:
    module = architecture["modules"]["riskpkg.risk"]
    definitions = {
        item["qualified_name"]: item for item in module["function_definitions"]
    }
    return {
        "meta": {"format": 3, "version": "7.fixture", "branch_coverage": True},
        "files": {
            module["path"]: {
                "functions": {
                    "outer": {
                        "start_line": definitions["outer"]["line"],
                        "summary": _summary(
                            covered_lines=0,
                            statements=2,
                            covered_branches=0,
                            branches=0,
                        ),
                    },
                    "outer.inner": {
                        "start_line": definitions["outer.inner"]["line"],
                        "summary": _summary(
                            covered_lines=3,
                            statements=3,
                            covered_branches=2,
                            branches=2,
                        ),
                    },
                    "API.run": {
                        "start_line": definitions["API.run"]["line"],
                        "summary": _summary(
                            covered_lines=1,
                            statements=1,
                            covered_branches=0,
                            branches=0,
                        ),
                    },
                }
            }
        },
    }


def _radon_blocks(source: str):
    if "def outer" not in source:
        return []
    inner = SimpleNamespace(
        is_method=False,
        lineno=2,
        endline=5,
        complexity=2,
        closures=[],
    )
    outer = SimpleNamespace(
        is_method=False,
        lineno=1,
        endline=6,
        complexity=7,
        closures=[inner],
    )
    method = SimpleNamespace(
        is_method=True,
        lineno=9,
        endline=10,
        complexity=1,
        closures=[],
    )
    class_block = SimpleNamespace(methods=[method])
    return [outer, class_block, method]


def test_report_is_nested_source_bound_branch_aware_and_deterministic(tmp_path: Path) -> None:
    package, architecture = _fixture(tmp_path)
    coverage = _coverage(architecture)
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")

    report = generate_code_risk_report(
        repository_root=tmp_path,
        source_root=package,
        coverage_json=coverage_path,
        visitor=_radon_blocks,
        radon_version="6.fixture",
    )
    repeated_report = generate_code_risk_report(
        repository_root=tmp_path,
        source_root=package,
        coverage_json=coverage_path,
        visitor=_radon_blocks,
        radon_version="6.fixture",
    )

    assert report["status"] == "advisory_complete"
    assert report["summary"] == {
        "function_count": 3,
        "measured_count": 3,
        "unmeasured_count": 0,
        "not_applicable_count": 0,
        "warning_count": 1,
        "crap_load": "26.000000",
    }
    assert report["functions"][0]["target"]["qualified_name"] == "outer"
    assert report["functions"][0]["crap_score"] == "56.000000"
    assert report["functions"][1]["target"]["qualified_name"] == "outer.inner"
    assert report["functions"][1]["coverage"]["percentage"] == "100.000"
    assert serialize_report(report) == serialize_report(repeated_report)
    assert serialize_report(report) == serialize_report(deepcopy(report))
    rendered = serialize_report(report).decode("utf-8")
    assert str(tmp_path) not in rendered
    assert "timestamp" not in rendered

    output = tmp_path / "quality" / "code-risk.json"
    write_fresh_report(output, report)
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError, match="already exists"):
        write_fresh_report(output, report)


def test_cli_accepts_an_explicit_comparison_repository_root(tmp_path: Path) -> None:
    repository = tmp_path / "base-tree"
    source = repository / "src" / "sunofriend"
    coverage = tmp_path / "coverage.json"
    output = tmp_path / "code-risk.json"

    args = build_parser().parse_args(
        [
            "--repository-root",
            str(repository),
            "--source-root",
            str(source),
            "--coverage-json",
            str(coverage),
            "--out",
            str(output),
        ]
    )

    assert args.repository_root == repository
    assert args.source_root == source


def test_nested_function_report_attaches_to_architecture_overlay(tmp_path: Path) -> None:
    _, architecture = _fixture(tmp_path)
    module = architecture["modules"]["riskpkg.risk"]
    nested = next(
        item
        for item in module["function_definitions"]
        if item["qualified_name"] == "outer.inner"
    )
    report = build_code_risk_document(
        architecture,
        _coverage(architecture),
        [
            ComplexityFunction(
                path=module["path"],
                qualified_name="outer.inner",
                line=nested["line"],
                end_line=nested["end_line"],
                complexity=2,
                source_sha256="a" * 64,
            )
        ],
        radon_version="6.fixture",
    )
    report_path = tmp_path / "risk.json"
    report_path.write_bytes(serialize_report(report))

    bundle = build_overlay_bundle(architecture, risk_report=report_path)

    record = bundle["documents"][0]["records"][0]
    assert record["qualified_name"] == "outer.inner"
    assert record["attachment"] == "current"


def test_report_rejects_line_only_coverage_and_unsafe_paths(tmp_path: Path) -> None:
    _, architecture = _fixture(tmp_path)
    module = architecture["modules"]["riskpkg.risk"]
    definition = module["function_definitions"][0]
    complexity = ComplexityFunction(
        path=module["path"],
        qualified_name=definition["qualified_name"],
        line=definition["line"],
        end_line=definition["end_line"],
        complexity=2,
        source_sha256="a" * 64,
    )
    coverage = _coverage(architecture)
    coverage["meta"]["branch_coverage"] = False
    with pytest.raises(ValueError, match="branch coverage is required"):
        build_code_risk_document(
            architecture,
            coverage,
            [complexity],
            radon_version="6.fixture",
        )

    coverage = _coverage(architecture)
    record = coverage["files"].pop(module["path"])
    coverage["files"]["/private/song/project.py"] = record
    with pytest.raises(ValueError, match="repository-relative"):
        build_code_risk_document(
            architecture,
            coverage,
            [complexity],
            radon_version="6.fixture",
        )


def test_coverage_binding_requires_an_unchanged_exact_source_tree(tmp_path: Path) -> None:
    _, architecture = _fixture(tmp_path)
    coverage = _coverage(architecture)
    raw = (json.dumps(coverage, sort_keys=True) + "\n").encode()

    binding = build_coverage_binding_document(
        architecture,
        coverage,
        raw,
        source_tree_sha256_before=architecture["source_tree_sha256"],
    )

    module = architecture["modules"]["riskpkg.risk"]
    assert binding == {
        "schema": "sunofriend-coverage-binding.v1",
        "coverage_json_sha256": hashlib.sha256(raw).hexdigest(),
        "source_tree_sha256_before": architecture["source_tree_sha256"],
        "source_tree_sha256_after": architecture["source_tree_sha256"],
        "files": {module["path"]: module["source_sha256"]},
    }
    with pytest.raises(ValueError, match="source tree changed"):
        build_coverage_binding_document(
            architecture,
            coverage,
            raw,
            source_tree_sha256_before="f" * 64,
        )


def test_report_marks_missing_function_region_incomplete(tmp_path: Path) -> None:
    _, architecture = _fixture(tmp_path)
    module = architecture["modules"]["riskpkg.risk"]
    definition = module["function_definitions"][0]
    coverage = _coverage(architecture)
    coverage["files"][module["path"]]["functions"].pop("outer")

    report = build_code_risk_document(
        architecture,
        coverage,
        [
            ComplexityFunction(
                path=module["path"],
                qualified_name=definition["qualified_name"],
                line=definition["line"],
                end_line=definition["end_line"],
                complexity=2,
                source_sha256="a" * 64,
            )
        ],
        radon_version="6.fixture",
    )

    assert report["status"] == "incomplete"
    assert report["summary"]["unmeasured_count"] == 1
    assert report["functions"][0]["unmeasured_reason"].startswith("matching coverage")


def test_zero_opportunity_declaration_is_explicitly_not_applicable(
    tmp_path: Path,
) -> None:
    _, architecture = _fixture(tmp_path)
    module = architecture["modules"]["riskpkg.risk"]
    definition = next(
        item
        for item in module["function_definitions"]
        if item["qualified_name"] == "API.run"
    )
    coverage = _coverage(architecture)
    coverage["files"][module["path"]]["functions"]["API.run"]["summary"] = _summary(
        covered_lines=0,
        statements=0,
        covered_branches=0,
        branches=0,
    )
    report = build_code_risk_document(
        architecture,
        coverage,
        [
            ComplexityFunction(
                path=module["path"],
                qualified_name="API.run",
                line=definition["line"],
                end_line=definition["end_line"],
                complexity=1,
                source_sha256="a" * 64,
            )
        ],
        radon_version="6.fixture",
    )

    assert report["status"] == "advisory_complete"
    assert report["summary"] == {
        "function_count": 1,
        "measured_count": 0,
        "unmeasured_count": 0,
        "not_applicable_count": 1,
        "warning_count": 0,
        "crap_load": "0.000000",
    }
    assert report["functions"][0]["status"] == "not_applicable"
    report_path = tmp_path / "risk.json"
    report_path.write_bytes(serialize_report(report))
    overlay = build_overlay_bundle(architecture, risk_report=report_path)
    assert overlay["documents"][0]["records"][0]["status"] == "not_applicable"


def test_complexity_falls_back_to_each_definition_for_nested_class_methods(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src" / "riskpkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "nested.py").write_text(
        """def build():
    class Handler:
        def serve(self, ready: bool):
            if ready:
                return 1
            return 0
    return Handler
""",
        encoding="utf-8",
    )
    architecture = analyse_source_tree(package, repository_root=tmp_path)

    outer = SimpleNamespace(
        is_method=False,
        lineno=1,
        endline=8,
        complexity=1,
        closures=[],
    )

    def whole_file_visitor(source: str):
        return [outer] if "def build" in source else []

    def definition_visitor(source: str):
        assert source.startswith("def serve")
        return [
            SimpleNamespace(
                is_method=False,
                lineno=1,
                endline=5,
                complexity=2,
                closures=[],
            )
        ]

    complexities = collect_complexities(
        architecture,
        repository_root=tmp_path,
        visitor=whole_file_visitor,
        definition_visitor=definition_visitor,
    )

    assert [
        (item.qualified_name, item.line, item.complexity) for item in complexities
    ] == [("build", 1, 1), ("build.Handler.serve", 3, 2)]


def test_complexity_still_fails_closed_when_definition_fallback_omits_a_function(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src" / "riskpkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "nested.py").write_text(
        """def build():
    class Handler:
        def serve(self):
            return 1
    return Handler
""",
        encoding="utf-8",
    )
    architecture = analyse_source_tree(package, repository_root=tmp_path)
    outer = SimpleNamespace(
        is_method=False,
        lineno=1,
        endline=5,
        complexity=1,
        closures=[],
    )

    with pytest.raises(ValueError, match="Radon omitted 1 functions"):
        collect_complexities(
            architecture,
            repository_root=tmp_path,
            visitor=lambda source: [outer] if "def build" in source else [],
            definition_visitor=lambda source: [],
        )
