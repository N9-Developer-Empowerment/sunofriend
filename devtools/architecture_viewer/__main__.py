"""Build, check, compare or query a fresh local Sunofriend architecture model."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

from .analyzer import analyse_source_tree
from .diffing import assess_ratchet, compare_architectures, load_architecture_snapshot
from .overlays import build_overlay_bundle
from .queries import (
    cycles_query,
    dependency_path_query,
    module_query,
    neighbourhood_query,
    violations_query,
)
from .renderer import build_architecture_viewer


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPOSITORY_ROOT / "src" / "sunofriend",
        help="Python package root to analyse (default: src/sunofriend)",
    )
    parser.add_argument(
        "--groups",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "architecture-viewer-groups.json",
        help="Hierarchy and architecture-contract configuration",
    )
    parser.add_argument(
        "--test-root",
        type=Path,
        default=REPOSITORY_ROOT / "tests",
        help="Optional Python test tree used for static test-to-module links",
    )
    parser.add_argument("--no-tests", action="store_true", help="Do not scan test imports")
    parser.add_argument(
        "--semantic-annotations",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "architecture-viewer-semantics.json",
        help="Optional maintained semantic and system-context annotations",
    )
    parser.add_argument("--runtime-effects", type=Path, help="Optional bounded runtime-effect report")
    parser.add_argument("--risk-report", type=Path, help="Optional source-bound CRAP report")
    parser.add_argument("--mutation-report", type=Path, help="Optional neutral mutation report")
    parser.add_argument("--coverage-json", type=Path, help="Optional coverage.py JSON report")
    parser.add_argument("--coverage-binding", type=Path, help="Hash binding for coverage.py JSON")
    parser.add_argument("--out", type=Path, help="Fresh output directory for the static explorer")
    parser.add_argument("--snapshot-out", type=Path, help="Fresh owner-only architecture JSON file")
    parser.add_argument("--plan", action="store_true", help="Analyse and print a no-write summary")
    parser.add_argument("--check", action="store_true", help="Fail on parse errors or contract violations")
    parser.add_argument("--diff", type=Path, metavar="SNAPSHOT", help="Compare a snapshot with current source")
    parser.add_argument(
        "--ratchet",
        type=Path,
        metavar="SNAPSHOT",
        help="Fail only on new cycles, contract violations or current parse errors",
    )
    queries = parser.add_mutually_exclusive_group()
    queries.add_argument("--module", metavar="MODULE", help="Print one module record")
    queries.add_argument("--neighbourhood", metavar="MODULE", help="Print a bounded module neighbourhood")
    queries.add_argument("--violations", action="store_true", help="Print contract results and violations")
    queries.add_argument("--cycles", action="store_true", help="Print static import cycles")
    queries.add_argument(
        "--why-dependency",
        nargs=2,
        metavar=("SOURCE", "TARGET"),
        help="Print the shortest deterministic dependency chain",
    )
    parser.add_argument("--depth", type=int, default=1, help="Neighbourhood depth (default: 1)")
    return parser


def _print(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _write_private_fresh(path: Path, value: Mapping[str, Any]) -> None:
    path = path.resolve()
    if path.exists():
        raise FileExistsError(f"snapshot output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        temporary.chmod(0o600)
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _next_fresh_output_root(requested: Path) -> Path:
    """Return *requested* or the first numbered sibling that does not exist.

    Architecture snapshots are immutable evidence. Repeating a documented
    build command therefore chooses a new sibling instead of deleting or
    replacing the earlier snapshot.
    """

    requested = requested.resolve()
    if not requested.exists() and not requested.is_symlink():
        return requested
    for suffix in range(2, 10_001):
        candidate = requested.with_name(f"{requested.name}-{suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise FileExistsError(
        f"could not find a fresh output name after 10,000 candidates for: {requested}"
    )


def _check_document(architecture: Mapping[str, Any]) -> dict[str, Any]:
    violations = architecture.get("violations", [])
    parse_errors = architecture.get("parse_errors", [])
    test_parse_errors = architecture.get("tests", {}).get("parse_errors", [])
    return {
        "schema": "sunofriend-architecture-check.v1",
        "package": architecture.get("package"),
        "source_tree_sha256": architecture.get("source_tree_sha256"),
        "architecture_sha256": architecture.get("architecture_sha256"),
        "status": "failed" if violations or parse_errors or test_parse_errors else "passed",
        "contracts": architecture.get("contracts", []),
        "violations": violations,
        "ignored_violations": architecture.get("ignored_violations", []),
        "parse_errors": parse_errors,
        "test_parse_errors": test_parse_errors,
    }


def _query(args: argparse.Namespace, architecture: Mapping[str, Any]) -> dict[str, Any] | None:
    if args.module:
        return module_query(architecture, args.module)
    if args.neighbourhood:
        return neighbourhood_query(architecture, args.neighbourhood, depth=args.depth)
    if args.violations:
        return violations_query(architecture)
    if args.cycles:
        return cycles_query(architecture)
    if args.why_dependency:
        return dependency_path_query(architecture, *args.why_dependency)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    query_count = sum(
        value is not None and value is not False
        for value in (
            args.module,
            args.neighbourhood,
            args.violations,
            args.cycles,
            args.why_dependency,
        )
    )
    primary_count = sum(
        value is not None and value is not False
        for value in (args.plan, args.check, args.diff, args.ratchet)
    ) + query_count
    if primary_count > 1:
        parser.error("choose only one of --plan, --check, --diff, --ratchet or a query")
    if (args.plan or args.check or args.ratchet is not None or query_count) and (
        args.out is not None or args.snapshot_out is not None
    ):
        parser.error("this read-only operation cannot be combined with an output option")
    has_read_operation = any(
        (
            args.plan,
            args.check,
            args.diff is not None,
            args.ratchet is not None,
            args.module is not None,
            args.neighbourhood is not None,
            args.violations,
            args.cycles,
            args.why_dependency is not None,
        )
    )
    if args.out is None and args.snapshot_out is None and not has_read_operation:
        parser.error("--out, --snapshot-out or a read-only operation is required")
    architecture = analyse_source_tree(
        args.source_root,
        repository_root=REPOSITORY_ROOT,
        groups_path=args.groups,
        test_root=None if args.no_tests else args.test_root,
    )
    semantic_path = args.semantic_annotations
    if semantic_path is not None and not semantic_path.is_file():
        semantic_path = None
    overlays = build_overlay_bundle(
        architecture,
        semantic_annotations=semantic_path,
        runtime_effects=args.runtime_effects,
        risk_report=args.risk_report,
        mutation_report=args.mutation_report,
        coverage_json=args.coverage_json,
        coverage_binding=args.coverage_binding,
    )
    comparison = None
    comparison_path = args.ratchet or args.diff
    if comparison_path is not None:
        comparison = compare_architectures(
            load_architecture_snapshot(comparison_path),
            architecture,
        )
    check = _check_document(architecture)

    if args.plan:
        _print(
            {
                "status": "ready_to_build_architecture_viewer",
                "schema": architecture["schema"],
                "source_root": architecture["source_root"],
                "source_tree_sha256": architecture["source_tree_sha256"],
                "architecture_sha256": architecture["architecture_sha256"],
                "stats": architecture["stats"],
                "group_count": len(architecture["groups"]),
                "overlay_document_count": len(overlays["documents"]),
                "comparison": comparison["summary"] if comparison else None,
                "effects": {
                    "source_imports": 0,
                    "source_execution": 0,
                    "subprocesses": 0,
                    "network": [],
                    "writes": [],
                },
            }
        )
        return 0

    query = _query(args, architecture)
    if query is not None:
        _print(query)
        return 0

    if args.check:
        _print(check)
        return 1 if check["status"] == "failed" else 0

    if args.ratchet is not None:
        assert comparison is not None
        failures = assess_ratchet(comparison, architecture)
        _print(
            {
                "schema": "sunofriend-architecture-ratchet.v1",
                "status": "failed" if failures else "passed",
                "baseline": comparison["before"],
                "current": comparison["after"],
                "failures": failures,
                "summary": comparison["summary"],
            }
        )
        return 1 if failures else 0

    if args.diff is not None and args.out is None and args.snapshot_out is None:
        assert comparison is not None
        _print(comparison)
        return 0

    if args.snapshot_out is not None:
        _write_private_fresh(args.snapshot_out, architecture)
        print(args.snapshot_out.resolve())
    if args.out is not None:
        requested_output = args.out.resolve()
        output_root = _next_fresh_output_root(requested_output)
        if output_root != requested_output:
            print(
                f"output root already exists; preserving it and using: {output_root}",
                file=sys.stderr,
            )
        output = build_architecture_viewer(
            architecture,
            source_root=args.source_root,
            repository_root=REPOSITORY_ROOT,
            output_root=output_root,
            overlays=overlays,
            comparison=comparison,
            check=check,
        )
        print(output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
