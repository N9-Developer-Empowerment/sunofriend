from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from devtools.architecture_viewer.analyzer import analyse_source_tree
from devtools.architecture_viewer.overlays import build_overlay_bundle
from devtools.code_risk import (
    ComplexityFunction,
    build_code_risk_document,
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
            )
        ],
        radon_version="6.fixture",
    )

    assert report["status"] == "incomplete"
    assert report["summary"]["unmeasured_count"] == 1
    assert report["functions"][0]["unmeasured_reason"].startswith("matching coverage")
