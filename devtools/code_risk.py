"""Build a deterministic, path-free CRAP1 report from source and coverage data."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from devtools.architecture_viewer.analyzer import analyse_source_tree


REPORT_SCHEMA = "sunofriend-code-risk.v1"
MAX_INPUT_BYTES = 64 * 1024 * 1024
DEFAULT_THRESHOLD = Decimal("30")


@dataclass(frozen=True)
class ComplexityFunction:
    path: str
    qualified_name: str
    line: int
    end_line: int
    complexity: int


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def read_coverage_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"coverage JSON exceeds {MAX_INPUT_BYTES} bytes")
    document = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_duplicate_safe_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(document, dict):
        raise ValueError("coverage JSON must be an object")
    return document, raw


def _relative_path(value: Any) -> str:
    text = str(value or "")
    path = PurePosixPath(text.replace("\\", "/"))
    if not text or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"coverage path must be repository-relative: {text!r}")
    return path.as_posix()


def _integer(summary: Mapping[str, Any], name: str) -> int:
    value = summary.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"coverage summary {name} must be a non-negative integer")
    return value


def _crap_score(complexity: int, covered: int, possible: int) -> Decimal | None:
    if possible == 0:
        return None
    with localcontext() as context:
        context.prec = 40
        coverage = Decimal(covered) / Decimal(possible)
        return Decimal(complexity * complexity) * (Decimal(1) - coverage) ** 3 + Decimal(
            complexity
        )


def _coverage_region(
    file_record: Mapping[str, Any] | None,
    function: ComplexityFunction,
) -> tuple[int, int, str | None]:
    if file_record is None:
        return 0, 0, "source file is absent from coverage JSON"
    regions = file_record.get("functions")
    if not isinstance(regions, Mapping):
        return 0, 0, "coverage JSON has no per-function regions"
    region = regions.get(function.qualified_name)
    if not isinstance(region, Mapping) or int(region.get("start_line", -1)) != function.line:
        matches = [
            value
            for name, value in regions.items()
            if name
            and isinstance(value, Mapping)
            and int(value.get("start_line", -1)) == function.line
        ]
        if len(matches) != 1:
            return 0, 0, "matching coverage function region is absent or ambiguous"
        region = matches[0]
    summary = region.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("coverage function region has no summary")
    statements = _integer(summary, "num_statements")
    covered_lines = _integer(summary, "covered_lines")
    branches = _integer(summary, "num_branches")
    covered_branches = _integer(summary, "covered_branches")
    if covered_lines > statements or covered_branches > branches:
        raise ValueError("covered opportunities exceed possible opportunities")
    covered = covered_lines + covered_branches
    possible = statements + branches
    if possible == 0:
        return 0, 0, "coverage region has no measurable opportunities"
    return covered, possible, None


def _format_decimal(value: Decimal, places: str) -> str:
    if not value.is_finite():
        raise ValueError("code-risk calculation produced a non-finite value")
    return format(value.quantize(Decimal(places)), "f")


def build_code_risk_document(
    architecture: Mapping[str, Any],
    coverage: Mapping[str, Any],
    complexities: Sequence[ComplexityFunction],
    *,
    radon_version: str,
    threshold: Decimal = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Combine exact Radon functions with coverage.py format-3 regions."""

    if not threshold.is_finite() or threshold <= 0:
        raise ValueError("CRAP threshold must be a finite positive number")
    meta = coverage.get("meta")
    files = coverage.get("files")
    if not isinstance(meta, Mapping) or not isinstance(files, Mapping):
        raise ValueError("coverage JSON requires meta and files objects")
    if int(meta.get("format", 0)) < 3:
        raise ValueError("coverage JSON format 3 or later is required for function regions")
    if meta.get("branch_coverage") is not True:
        raise ValueError("branch coverage is required for CRAP measurement")
    coverage_version = str(meta.get("version", "")).strip()
    if not coverage_version or not radon_version.strip():
        raise ValueError("coverage.py and Radon versions must be recorded")
    normalized_files: dict[str, Mapping[str, Any]] = {}
    for raw_path, record in files.items():
        path = _relative_path(raw_path)
        if path in normalized_files or not isinstance(record, Mapping):
            raise ValueError(f"invalid or duplicate coverage file: {path}")
        normalized_files[path] = record

    modules_by_path = {
        str(module["path"]): (name, module)
        for name, module in architecture["modules"].items()
    }
    seen: set[tuple[str, str, int]] = set()
    functions: list[dict[str, Any]] = []
    warning_count = 0
    unmeasured_count = 0
    crap_load = Decimal(0)
    for function in complexities:
        identity = (function.path, function.qualified_name, function.line)
        if identity in seen:
            raise ValueError(f"duplicate function identity: {identity}")
        seen.add(identity)
        if function.complexity < 1 or function.line < 1 or function.end_line < function.line:
            raise ValueError(f"invalid Radon function record: {identity}")
        module_entry = modules_by_path.get(function.path)
        if module_entry is None:
            raise ValueError(f"Radon function is outside the analysed package: {function.path}")
        module_name, module = module_entry
        definitions = {
            (str(item["qualified_name"]), int(item["line"]), int(item["end_line"]))
            for item in module.get("function_definitions", [])
        }
        definition_identity = (
            function.qualified_name,
            function.line,
            function.end_line,
        )
        if definition_identity not in definitions:
            raise ValueError(f"Radon function does not match source AST: {identity}")
        covered, possible, reason = _coverage_region(
            normalized_files.get(function.path), function
        )
        score = _crap_score(function.complexity, covered, possible)
        if score is None:
            status = "unmeasured"
            unmeasured_count += 1
        elif score > threshold:
            status = "warning"
            warning_count += 1
            crap_load += score - threshold
        else:
            status = "ok"
        record: dict[str, Any] = {
            "target": {
                "module": module_name,
                "path": function.path,
                "source_sha256": str(module["source_sha256"]),
                "qualified_name": function.qualified_name,
                "line": function.line,
                "end_line": function.end_line,
            },
            "complexity": function.complexity,
            "coverage": {
                "covered_opportunities": covered,
                "possible_opportunities": possible,
                "percentage": (
                    None
                    if possible == 0
                    else _format_decimal(Decimal(covered) * Decimal(100) / Decimal(possible), "0.001")
                ),
            },
            "crap_score": None if score is None else _format_decimal(score, "0.000001"),
            "threshold": format(threshold, "f"),
            "status": status,
        }
        if reason is not None:
            record["unmeasured_reason"] = reason
        functions.append(record)

    def sort_key(record: Mapping[str, Any]) -> tuple[Decimal, str, str, int]:
        score = record.get("crap_score")
        return (
            -(Decimal(str(score)) if score is not None else Decimal(-1)),
            str(record["target"]["path"]),
            str(record["target"]["qualified_name"]),
            int(record["target"]["line"]),
        )

    functions.sort(key=sort_key)
    return {
        "schema": REPORT_SCHEMA,
        "status": "incomplete" if unmeasured_count else "advisory_complete",
        "binding": {
            "source_tree_sha256": architecture["source_tree_sha256"],
        },
        "tools": {
            "coverage": coverage_version,
            "radon": radon_version,
        },
        "formula": {
            "id": "crap1",
            "expression": "complexity^2 * (1 - coverage_fraction)^3 + complexity",
            "coverage_opportunities": "statements_plus_branches",
            "threshold": format(threshold, "f"),
        },
        "summary": {
            "function_count": len(functions),
            "measured_count": len(functions) - unmeasured_count,
            "unmeasured_count": unmeasured_count,
            "warning_count": warning_count,
            "crap_load": _format_decimal(crap_load, "0.000001"),
        },
        "functions": functions,
    }


def _flatten_radon_blocks(blocks: Iterable[Any]) -> list[Any]:
    functions: dict[int, Any] = {}

    def visit(block: Any) -> None:
        if hasattr(block, "is_method"):
            line = int(block.lineno)
            existing = functions.get(line)
            if existing is not None and int(existing.complexity) != int(block.complexity):
                raise ValueError(f"Radon returned conflicting functions at line {line}")
            functions[line] = block
            for closure in getattr(block, "closures", ()):
                visit(closure)
        else:
            for method in getattr(block, "methods", ()):
                visit(method)

    for block in blocks:
        visit(block)
    return [functions[line] for line in sorted(functions)]


def collect_complexities(
    architecture: Mapping[str, Any],
    *,
    repository_root: Path,
    visitor: Callable[[str], Iterable[Any]],
) -> list[ComplexityFunction]:
    result: list[ComplexityFunction] = []
    for module in sorted(architecture["modules"].values(), key=lambda item: item["path"]):
        source_path = repository_root / str(module["path"])
        source = source_path.read_text(encoding="utf-8")
        definitions_by_line = {
            int(item["line"]): item for item in module.get("function_definitions", [])
        }
        measured_lines: set[int] = set()
        for block in _flatten_radon_blocks(visitor(source)):
            line = int(block.lineno)
            definition = definitions_by_line.get(line)
            if definition is None:
                raise ValueError(f"Radon function has no source definition: {module['path']}:{line}")
            measured_lines.add(line)
            result.append(
                ComplexityFunction(
                    path=str(module["path"]),
                    qualified_name=str(definition["qualified_name"]),
                    line=line,
                    end_line=int(definition["end_line"]),
                    complexity=int(block.complexity),
                )
            )
        missing = sorted(set(definitions_by_line) - measured_lines)
        if missing:
            raise ValueError(
                f"Radon omitted {len(missing)} functions in {module['path']}: {missing[:5]}"
            )
    return result


def _radon_backend() -> tuple[str, Callable[[str], Iterable[Any]]]:
    try:
        from radon.complexity import cc_visit
    except ImportError as error:
        raise RuntimeError(
            "Radon is not installed; the quality dependency gate requires explicit approval"
        ) from error
    return importlib.metadata.version("radon"), cc_visit


def generate_code_risk_report(
    *,
    repository_root: Path,
    source_root: Path,
    coverage_json: Path,
    threshold: Decimal = DEFAULT_THRESHOLD,
    visitor: Callable[[str], Iterable[Any]] | None = None,
    radon_version: str | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source_root = source_root.resolve()
    try:
        source_root.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("source root must be inside repository root") from error
    coverage, _ = read_coverage_json(coverage_json)
    architecture = analyse_source_tree(source_root, repository_root=repository_root)
    if visitor is None:
        radon_version, visitor = _radon_backend()
    if not radon_version:
        raise ValueError("Radon version is required")
    complexities = collect_complexities(
        architecture,
        repository_root=repository_root,
        visitor=visitor,
    )
    return build_code_risk_document(
        architecture,
        coverage,
        complexities,
        radon_version=radon_version,
        threshold=threshold,
    )


def serialize_report(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def write_fresh_report(path: Path, document: Mapping[str, Any]) -> None:
    path = path.resolve()
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"code-risk output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(serialize_report(document))
        temporary.chmod(0o600)
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _print_summary(document: Mapping[str, Any], *, limit: int) -> None:
    summary = document["summary"]
    print(
        f"{document['status']}: {summary['measured_count']}/{summary['function_count']} "
        f"functions measured; {summary['warning_count']} above CRAP {document['formula']['threshold']}"
    )
    print("CRAP       complexity  coverage   function")
    for record in document["functions"][:limit]:
        score = record["crap_score"] or "unmeasured"
        coverage = record["coverage"]["percentage"]
        target = record["target"]
        print(
            f"{score:>10}  {record['complexity']:>10}  "
            f"{(coverage + '%') if coverage is not None else 'unmeasured':>10}   "
            f"{target['path']}::{target['qualified_name']}"
        )


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Fresh path-free JSON report")
    parser.add_argument("--source-root", type=Path, default=repository_root / "src" / "sunofriend")
    parser.add_argument("--threshold", type=Decimal, default=DEFAULT_THRESHOLD)
    parser.add_argument("--top", type=int, default=25, help="Rows to print (default: 25)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.top < 0 or args.top > 1_000:
        parser.error("--top must be between 0 and 1000")
    repository_root = Path(__file__).resolve().parents[1]
    try:
        document = generate_code_risk_report(
            repository_root=repository_root,
            source_root=args.source_root,
            coverage_json=args.coverage_json,
            threshold=args.threshold,
        )
        output = args.out.resolve()
        try:
            output.relative_to(args.source_root.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("code-risk output must be outside the source tree")
        write_fresh_report(output, document)
    except (FileExistsError, RuntimeError, ValueError) as error:
        parser.exit(2, f"code-risk report blocked: {error}\n")
    print(output)
    _print_summary(document, limit=args.top)
    return 1 if document["status"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
