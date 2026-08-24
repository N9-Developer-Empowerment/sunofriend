from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from devtools.architecture_viewer.analyzer import analyse_source_tree
from devtools.architecture_viewer.overlays import build_overlay_bundle


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _architecture(repository: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    package = repository / "src" / "qualitypkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "risk.py").write_text(
        '''"""Risk fixture."""
def risky(value: bool) -> int:
    if value:
        return 1
    return 0
''',
        encoding="utf-8",
    )
    architecture = analyse_source_tree(package, repository_root=repository)
    module = architecture["modules"]["qualitypkg.risk"]
    definition = module["public_interface"][0]
    return package, architecture, {
        "module": "qualitypkg.risk",
        "path": module["path"],
        "source_sha256": module["source_sha256"],
        "qualified_name": definition["qualified_name"],
        "line": definition["line"],
        "end_line": definition["end_line"],
    }


def test_source_bound_semantic_quality_and_coverage_overlays(tmp_path: Path) -> None:
    _, architecture, target = _architecture(tmp_path)
    tree_hash = architecture["source_tree_sha256"]
    semantics = tmp_path / "semantics.json"
    risk = tmp_path / "risk.json"
    mutation = tmp_path / "mutation.json"
    coverage = tmp_path / "coverage.json"
    coverage_binding = tmp_path / "coverage-binding.json"
    _json(
        semantics,
        {
            "schema": "sunofriend-architecture-semantics.v1",
            "modules": [
                {
                    "target": {"module": "qualitypkg.risk"},
                    "claim_kind": "intent",
                    "roles": ["policy"],
                    "surface": "public",
                    "stability": "stable",
                    "responsibility": "Hide the branch policy.",
                    "supported_entry_points": ["risky"],
                    "inputs": ["one boolean"],
                    "outputs": ["one integer"],
                    "knowledge_owned": ["branch mapping"],
                    "caller_obligations": ["pass a boolean"],
                    "side_effects": [],
                    "errors": [],
                    "schemas": [],
                    "authority_boundary": "A quality score grants no product authority.",
                }
            ],
            "system": {
                "nodes": [
                    {"id": "person", "type": "person", "label": "Reviewer"},
                    {"id": "tool", "type": "process", "label": "Quality tool"},
                ],
                "relationships": [
                    {"source": "person", "target": "tool", "label": "reviews evidence"}
                ],
            },
        },
    )
    _json(
        risk,
        {
            "schema": "sunofriend-code-risk.v1",
            "binding": {"source_tree_sha256": tree_hash},
            "formula": {"id": "crap1", "threshold": 30},
            "functions": [
                {
                    "target": target,
                    "complexity": 4,
                    "coverage": {"covered_opportunities": 5, "possible_opportunities": 10},
                }
            ],
        },
    )
    _json(
        mutation,
        {
            "schema": "sunofriend-mutation-report.v1",
            "binding": {
                "source_tree_sha256_before": tree_hash,
                "source_tree_sha256_after": tree_hash,
            },
            "run_status": "complete",
            "mutants": [
                {
                    "id": "risk-1",
                    "target": target,
                    "line": target["line"] + 1,
                    "operator": "replace conditional",
                    "status": "survived",
                }
            ],
        },
    )
    coverage_document = {
        "meta": {"version": "7.fixture", "format": 3, "branch_coverage": True},
        "files": {
            target["path"]: {
                "summary": {
                    "covered_lines": 4,
                    "num_statements": 4,
                    "percent_covered": 100.0,
                    "covered_branches": 2,
                    "num_branches": 2,
                },
                "contexts": {
                    str(target["line"]): [
                        "tests.test_risk.test_true",
                        "/Users/private/song-name",
                    ]
                },
                "functions": {},
            }
        },
    }
    coverage_raw = (json.dumps(coverage_document, indent=2) + "\n").encode()
    coverage.write_bytes(coverage_raw)
    _json(
        coverage_binding,
        {
            "schema": "sunofriend-coverage-binding.v1",
            "coverage_json_sha256": hashlib.sha256(coverage_raw).hexdigest(),
            "source_tree_sha256_before": tree_hash,
            "source_tree_sha256_after": tree_hash,
            "files": {target["path"]: target["source_sha256"]},
        },
    )

    bundle = build_overlay_bundle(
        architecture,
        semantic_annotations=semantics,
        risk_report=risk,
        mutation_report=mutation,
        coverage_json=coverage,
        coverage_binding=coverage_binding,
    )

    assert [item["kind"] for item in bundle["documents"]] == [
        "coverage",
        "mutation",
        "risk",
        "semantics",
    ]
    documents = {item["kind"]: item for item in bundle["documents"]}
    assert documents["risk"]["records"][0]["crap_score"] == "6.000000"
    assert documents["risk"]["records"][0]["attachment"] == "current"
    assert documents["mutation"]["run_status"] == "complete"
    assert documents["mutation"]["counts"]["survived"] == 1
    assert documents["coverage"]["binding"] == "hash_bound"
    contexts = documents["coverage"]["records"][0]["contexts"][str(target["line"])]
    assert "tests.test_risk.test_true" in contexts
    assert any(item.startswith("redacted-context-") for item in contexts)
    semantic = documents["semantics"]["records"][0]
    assert semantic["stability"] == "stable"
    assert semantic["supported_entry_points"] == ["risky"]
    assert documents["semantics"]["system"]["relationships"][0]["target"] == "tool"


def test_quality_record_with_wrong_symbol_range_is_not_current(tmp_path: Path) -> None:
    _, architecture, target = _architecture(tmp_path)
    target["end_line"] += 1
    report = tmp_path / "risk.json"
    _json(
        report,
        {
            "schema": "sunofriend-code-risk.v1",
            "binding": {"source_tree_sha256": architecture["source_tree_sha256"]},
            "functions": [
                {
                    "target": target,
                    "complexity": 2,
                    "coverage": {"covered_opportunities": 1, "possible_opportunities": 1},
                }
            ],
        },
    )

    bundle = build_overlay_bundle(architecture, risk_report=report)

    assert bundle["documents"][0]["records"][0]["attachment"] == "symbol_stale_or_missing"


def test_semantic_schema_rejects_unbounded_shapes_and_unknown_system_nodes(tmp_path: Path) -> None:
    _, architecture, _ = _architecture(tmp_path)
    report = tmp_path / "semantics.json"
    _json(
        report,
        {
            "schema": "sunofriend-architecture-semantics.v1",
            "modules": [
                {
                    "target": {"module": "qualitypkg.risk"},
                    "claim_kind": "intent",
                    "roles": "not-a-list",
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="roles must be a list"):
        build_overlay_bundle(architecture, semantic_annotations=report)

    _json(
        report,
        {
            "schema": "sunofriend-architecture-semantics.v1",
            "modules": [],
            "system": {
                "nodes": [{"id": "known"}],
                "relationships": [{"source": "known", "target": "missing"}],
            },
        },
    )
    with pytest.raises(ValueError, match="known nodes"):
        build_overlay_bundle(architecture, semantic_annotations=report)
