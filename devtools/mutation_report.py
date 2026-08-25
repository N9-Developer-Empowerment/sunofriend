"""Build a deterministic, source-bound report from mutmut 3 metadata."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import importlib.metadata
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from devtools.architecture_viewer.analyzer import analyse_source_tree


REPORT_SCHEMA = "sunofriend-mutation-report.v1"
CLASSIFICATION_SCHEMA = "sunofriend-mutation-classifications.v1"
MAX_META_BYTES = 16 * 1024 * 1024
MAX_MUTANTS = 250_000
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MUTANT_SUFFIX = re.compile(r"__mutmut_[0-9]+$")


STATUS_BY_EXIT_CODE: dict[int | None, str] = {
    0: "survived",
    1: "killed",
    2: "error",
    3: "killed",
    5: "untested",
    24: "timeout",
    33: "untested",
    34: "skipped",
    35: "suspicious",
    36: "timeout",
    37: "killed",
    152: "timeout",
    255: "timeout",
    -24: "timeout",
    -11: "error",
    -9: "error",
    None: "untested",
}

NON_SURVIVOR_CLASSIFICATIONS = {
    "killed": {
        "classification": "not_applicable",
        "rationale": "the selected tests detected this mutation",
    },
    "untested": {
        "classification": "test_selection_gap",
        "rationale": "the selected tests did not execute this mutation",
    },
    "timeout": {
        "classification": "timeout_unresolved",
        "rationale": "the mutation exceeded the bounded test duration",
    },
    "skipped": {
        "classification": "explicitly_skipped",
        "rationale": "the mutation tool skipped this mutation",
    },
    "suspicious": {
        "classification": "suspicious_result",
        "rationale": "the mutation tool returned an unrecognized test outcome",
    },
    "error": {
        "classification": "tool_error",
        "rationale": "the mutation run ended with an error or signal",
    },
}


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(path: Path, *, limit: int = MAX_META_BYTES) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError(f"mutation input exceeds {limit} bytes: {path.name}")
    document = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_duplicate_safe_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(document, dict):
        raise ValueError(f"mutation input must be an object: {path.name}")
    return document


def _qualified_name(encoded: str) -> str:
    if not encoded.startswith("x") or MUTANT_SUFFIX.search(encoded) is None:
        raise ValueError(f"unsupported mutmut function identity: {encoded!r}")
    function = MUTANT_SUFFIX.sub("", encoded[1:])
    if function.startswith("\u01c1"):
        function = function[1:]
    elif function.startswith("_"):
        function = function[1:]
    function = function.replace("\u01c1", ".")
    if not function:
        raise ValueError(f"empty mutmut function identity: {encoded!r}")
    return function


def _mutant_identity(
    mutant_id: str,
    modules: Mapping[str, Any],
) -> tuple[str, str]:
    matches = [name for name in modules if mutant_id.startswith(name + ".")]
    if not matches:
        raise ValueError(f"mutant does not name a current module: {mutant_id}")
    module_name = max(matches, key=len)
    return module_name, _qualified_name(mutant_id[len(module_name) + 1 :])


def _definitions(module: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    definitions: dict[str, Mapping[str, Any]] = {}
    for definition in module.get("function_definitions", []):
        if not isinstance(definition, Mapping):
            continue
        name = str(definition.get("qualified_name", ""))
        if not name or name in definitions:
            raise ValueError(f"ambiguous source function identity: {name!r}")
        definitions[name] = definition
    return definitions


def _load_classifications(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    document = _read_json(path)
    if document.get("schema") != CLASSIFICATION_SCHEMA:
        raise ValueError("unsupported mutation classification schema")
    default = document.get("default_survivor")
    rules = document.get("rules", [])
    if not isinstance(default, Mapping) or not isinstance(rules, list):
        raise ValueError("mutation classifications require a default and rules")
    default_record = {
        "classification": str(default.get("classification", "")).strip(),
        "rationale": str(default.get("rationale", "")).strip(),
    }
    if not all(default_record.values()):
        raise ValueError("default survivor classification must be complete")
    normalized_rules: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for rule in rules:
        if not isinstance(rule, Mapping):
            raise ValueError("mutation classification rules must be objects")
        normalized = {
            "module": str(rule.get("module", "")).strip(),
            "qualified_name": str(rule.get("qualified_name", "")).strip(),
            "classification": str(rule.get("classification", "")).strip(),
            "rationale": str(rule.get("rationale", "")).strip(),
        }
        if not all(normalized.values()):
            raise ValueError("mutation classification rules must be complete")
        identity = (normalized["module"], normalized["qualified_name"])
        if identity in seen:
            raise ValueError(f"duplicate mutation classification rule: {identity}")
        seen.add(identity)
        normalized_rules.append(normalized)
    return default_record, normalized_rules


def _classification(
    *,
    status: str,
    module: str,
    qualified_name: str,
    default_survivor: Mapping[str, str],
    rules: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    if status != "survived":
        return dict(NON_SURVIVOR_CLASSIFICATIONS[status])
    for rule in rules:
        if rule["module"] == module and rule["qualified_name"] == qualified_name:
            return {
                "classification": rule["classification"],
                "rationale": rule["rationale"],
            }
    return dict(default_survivor)


def build_mutation_report(
    *,
    architecture: Mapping[str, Any],
    mutants_root: Path,
    classifications_path: Path,
    source_tree_sha256_before: str,
    mutmut_version: str,
    selected_modules: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Bind completed mutmut metadata to exact current source functions."""

    if SHA256_PATTERN.fullmatch(source_tree_sha256_before) is None:
        raise ValueError("pre-run source-tree SHA-256 must be 64 lowercase hex characters")
    source_tree_sha256_after = str(architecture.get("source_tree_sha256", ""))
    if source_tree_sha256_before != source_tree_sha256_after:
        raise ValueError("source tree changed during mutation measurement")
    if not mutmut_version.strip():
        raise ValueError("mutmut version is required")
    selected = None
    if selected_modules is not None:
        selected = frozenset(module.strip() for module in selected_modules)
        if not selected or "" in selected:
            raise ValueError("selected mutation modules must be non-empty")
        unknown = selected.difference(architecture["modules"])
        if unknown:
            raise ValueError(
                f"selected mutation modules are absent from current source: "
                f"{', '.join(sorted(unknown))}"
            )
    default_survivor, rules = _load_classifications(classifications_path)
    meta_paths = sorted(mutants_root.glob("src/**/*.py.meta"))
    if not meta_paths:
        raise ValueError("no mutmut metadata files found")

    raw_results: dict[str, int | None] = {}
    for meta_path in meta_paths:
        metadata = _read_json(meta_path)
        results = metadata.get("exit_code_by_key")
        if not isinstance(results, Mapping):
            raise ValueError(f"mutmut metadata has no result map: {meta_path.name}")
        for mutant_id, exit_code in results.items():
            if mutant_id in raw_results:
                raise ValueError(f"duplicate mutant id: {mutant_id}")
            if exit_code is not None and (
                isinstance(exit_code, bool) or not isinstance(exit_code, int)
            ):
                raise ValueError(f"invalid mutmut exit code for {mutant_id}")
            if exit_code not in STATUS_BY_EXIT_CODE:
                raise ValueError(f"unsupported mutmut exit code {exit_code} for {mutant_id}")
            raw_results[str(mutant_id)] = exit_code
    if len(raw_results) > MAX_MUTANTS:
        raise ValueError(f"mutation result exceeds {MAX_MUTANTS} records")

    definitions_by_module = {
        name: _definitions(module)
        for name, module in architecture["modules"].items()
    }
    mutants: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    survivor_classifications: Counter[str] = Counter()
    for mutant_id, exit_code in sorted(raw_results.items()):
        module_name, qualified_name = _mutant_identity(
            mutant_id, architecture["modules"]
        )
        if selected is not None and module_name not in selected:
            continue
        definition = definitions_by_module[module_name].get(qualified_name)
        if definition is None:
            raise ValueError(
                f"mutant function is absent from current source: "
                f"{module_name}::{qualified_name}"
            )
        module = architecture["modules"][module_name]
        status = STATUS_BY_EXIT_CODE[exit_code]
        equivalence = _classification(
            status=status,
            module=module_name,
            qualified_name=qualified_name,
            default_survivor=default_survivor,
            rules=rules,
        )
        status_counts[status] += 1
        if status == "survived":
            survivor_classifications[equivalence["classification"]] += 1
        mutants.append(
            {
                "id": mutant_id,
                "target": {
                    "module": module_name,
                    "path": str(module["path"]),
                    "source_sha256": str(module["source_sha256"]),
                    "qualified_name": qualified_name,
                    "line": int(definition["line"]),
                    "end_line": int(definition["end_line"]),
                },
                "line": int(definition["line"]),
                "operator": f"mutmut {mutmut_version} generated mutation",
                "status": status,
                "equivalence": equivalence,
            }
        )

    if not mutants:
        raise ValueError("no mutation results matched the selected modules")

    unfinished = status_counts["untested"] + status_counts["error"]
    run_status = "advisory_complete" if unfinished == 0 else "incomplete"
    document = {
        "schema": REPORT_SCHEMA,
        "lane": "three-module-pilot" if selected is None else "selected-module-pilot",
        "run_status": run_status,
        "binding": {
            "source_tree_sha256_before": source_tree_sha256_before,
            "source_tree_sha256_after": source_tree_sha256_after,
        },
        "tools": {"mutmut": mutmut_version},
        "policy": {
            "score_gate": "none",
            "survivors_are_advisory": True,
            "timeouts_are_unresolved": True,
        },
        "summary": {
            "mutant_count": len(mutants),
            "status_counts": dict(sorted(status_counts.items())),
            "survivor_classifications": dict(
                sorted(survivor_classifications.items())
            ),
        },
        "mutants": mutants,
    }
    if selected is not None:
        document["selection"] = {"modules": sorted(selected)}
    return document


def serialize_report(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def write_fresh_report(path: Path, document: Mapping[str, Any]) -> None:
    path = path.resolve()
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"mutation report output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=path.parent
    )
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


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutants-root", type=Path, required=True)
    parser.add_argument("--classifications", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--source-root", type=Path, default=repository_root / "src" / "sunofriend"
    )
    parser.add_argument("--source-tree-sha256-before", required=True)
    parser.add_argument("--mutmut-version")
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Include one exact module from a bounded mutmut run (repeatable)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    try:
        source_root = args.source_root.resolve()
        mutants_root = args.mutants_root.resolve()
        output = args.out.resolve()
        for path, label in (
            (source_root, "source root"),
            (mutants_root, "mutants root"),
            (args.classifications.resolve(), "classifications"),
        ):
            try:
                path.relative_to(repository_root)
            except ValueError as error:
                raise ValueError(f"{label} must be inside repository root") from error
        try:
            output.relative_to(source_root)
        except ValueError:
            pass
        else:
            raise ValueError("mutation report output must be outside the source tree")
        architecture = analyse_source_tree(
            source_root, repository_root=repository_root
        )
        version = args.mutmut_version or importlib.metadata.version("mutmut")
        document = build_mutation_report(
            architecture=architecture,
            mutants_root=mutants_root,
            classifications_path=args.classifications.resolve(),
            source_tree_sha256_before=args.source_tree_sha256_before,
            mutmut_version=version,
            selected_modules=args.modules,
        )
        write_fresh_report(output, document)
    except (FileExistsError, importlib.metadata.PackageNotFoundError, ValueError) as error:
        parser.exit(2, f"mutation report blocked: {error}\n")
    print(output)
    summary = document["summary"]
    print(
        f"{document['run_status']}: {summary['mutant_count']} mutants; "
        f"{summary['status_counts']}"
    )
    print(f"survivors: {summary['survivor_classifications']}")
    return 1 if document["run_status"] == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
