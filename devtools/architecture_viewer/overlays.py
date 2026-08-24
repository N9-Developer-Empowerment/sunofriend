"""Normalize optional, source-bound architecture overlays without executing tools."""

from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


OVERLAYS_SCHEMA = "sunofriend-architecture-overlays.v1"
MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 250_000
MUTATION_STATES = {
    "killed",
    "survived",
    "suspicious",
    "timeout",
    "untested",
    "skipped",
    "error",
}


def _string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return list(value)


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _read_document(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError(f"overlay report exceeds {MAX_REPORT_BYTES} bytes: {path.name}")
    document = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_duplicate_safe_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(document, dict):
        raise ValueError(f"overlay report must be an object: {path.name}")
    return document, raw


def _relative_path(value: Any) -> str:
    path = str(value or "")
    pure = PurePosixPath(path.replace("\\", "/"))
    if not path or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"overlay path must be repository-relative: {path!r}")
    return pure.as_posix()


def _module_lookup(architecture: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    by_path: dict[str, str] = {}
    by_short: dict[str, str] = {}
    for name, module in architecture["modules"].items():
        by_path[str(module["path"])] = name
        by_short[str(module["short_name"])] = name
    return by_path, by_short


def _target_module(
    target: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> str | None:
    by_path, by_short = _module_lookup(architecture)
    module_name = target.get("module")
    if isinstance(module_name, str):
        if module_name in architecture["modules"]:
            return module_name
        if module_name in by_short:
            return by_short[module_name]
    if target.get("path") is not None:
        return by_path.get(_relative_path(target["path"]))
    return None


def _attachment(
    target: Mapping[str, Any],
    *,
    document_tree_hash: str | None,
    architecture: Mapping[str, Any],
    intent_only: bool = False,
) -> tuple[str, str | None]:
    module_name = _target_module(target, architecture)
    if module_name is None:
        return "orphaned", None
    if intent_only:
        return "current", module_name
    supplied_hash = target.get("source_sha256")
    if not isinstance(supplied_hash, str) or not supplied_hash:
        return "unbound", module_name
    if supplied_hash != architecture["modules"][module_name]["source_sha256"]:
        return "source_stale", module_name
    if document_tree_hash != architecture.get("source_tree_sha256"):
        return "snapshot_stale", module_name
    return "current", module_name


def _definitions(module: Mapping[str, Any]) -> dict[tuple[str, int, int], Mapping[str, Any]]:
    result: dict[tuple[str, int, int], Mapping[str, Any]] = {}

    def add(definition: Mapping[str, Any]) -> None:
        identity = (
            str(definition.get("qualified_name", definition.get("name", ""))),
            int(definition.get("line", 0)),
            int(definition.get("end_line", definition.get("line", 0))),
        )
        result[identity] = definition
        for member in definition.get("members", []):
            if isinstance(member, Mapping):
                add(member)

    for definition in [
        *module.get("public_interface", []),
        *module.get("implementation", []),
        *module.get("function_definitions", []),
    ]:
        if isinstance(definition, Mapping):
            add(definition)
    return result


def _function_attachment(
    target: Mapping[str, Any],
    *,
    document_tree_hash: str | None,
    architecture: Mapping[str, Any],
) -> tuple[str, str | None]:
    state, module_name = _attachment(
        target,
        document_tree_hash=document_tree_hash,
        architecture=architecture,
    )
    if state != "current" or module_name is None:
        return state, module_name
    qualified_name = str(target.get("qualified_name", ""))
    line = int(target.get("line", 0))
    end_line = int(target.get("end_line", line))
    if (qualified_name, line, end_line) not in _definitions(
        architecture["modules"][module_name]
    ):
        return "symbol_stale_or_missing", module_name
    return state, module_name


def _normalize_system(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nodes": [], "relationships": []}
    if not isinstance(value, Mapping):
        raise ValueError("semantic system must be an object")
    raw_nodes = value.get("nodes", [])
    raw_relationships = value.get("relationships", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_relationships, list):
        raise ValueError("semantic system nodes and relationships must be lists")
    if len(raw_nodes) > 1_000 or len(raw_relationships) > 10_000:
        raise ValueError("semantic system exceeds bounded record limits")
    nodes: list[dict[str, str]] = []
    node_ids: set[str] = set()
    for node in raw_nodes:
        if not isinstance(node, Mapping):
            raise ValueError("semantic system nodes must be objects")
        node_id = str(node.get("id", "")).strip()
        if not node_id or node_id in node_ids:
            raise ValueError("semantic system node ids must be non-empty and unique")
        node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "type": str(node.get("type", "unspecified")),
                "label": str(node.get("label", node_id)),
                "description": str(node.get("description", "")),
            }
        )
    relationships: list[dict[str, str]] = []
    for relationship in raw_relationships:
        if not isinstance(relationship, Mapping):
            raise ValueError("semantic system relationships must be objects")
        source = str(relationship.get("source", ""))
        target = str(relationship.get("target", ""))
        if source not in node_ids or target not in node_ids:
            raise ValueError("semantic system relationships must reference known nodes")
        relationships.append(
            {
                "source": source,
                "target": target,
                "label": str(relationship.get("label", "")),
            }
        )
    return {
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "relationships": sorted(
            relationships,
            key=lambda item: (item["source"], item["target"], item["label"]),
        ),
    }


def _base(architecture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "architecture_schema": architecture.get("schema"),
        "package": architecture.get("package"),
        "source_root": architecture.get("source_root"),
        "source_tree_sha256": architecture.get("source_tree_sha256"),
        "architecture_sha256": architecture.get("architecture_sha256"),
    }


def _normalize_semantics(
    document: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> dict[str, Any]:
    if document.get("schema") != "sunofriend-architecture-semantics.v1":
        raise ValueError("unsupported semantic annotations schema")
    raw_records = document.get("modules", [])
    if not isinstance(raw_records, list) or len(raw_records) > MAX_RECORDS:
        raise ValueError("semantic modules must be a bounded list")
    tree_hash = document.get("binding", {}).get("source_tree_sha256") if isinstance(document.get("binding"), Mapping) else None
    records: list[dict[str, Any]] = []
    for record in raw_records:
        if not isinstance(record, Mapping) or not isinstance(record.get("target"), Mapping):
            raise ValueError("semantic records require a target")
        claim_kind = str(record.get("claim_kind", "intent"))
        if claim_kind not in {"intent", "source_observation"}:
            raise ValueError("semantic claim_kind must be intent or source_observation")
        state, module_name = _attachment(
            record["target"],
            document_tree_hash=tree_hash,
            architecture=architecture,
            intent_only=claim_kind == "intent",
        )
        records.append(
            {
                "module": module_name or str(record["target"].get("module", "unknown")),
                "attachment": state,
                "claim_kind": claim_kind,
                "roles": sorted(_string_list(record.get("roles"), field="semantic roles")),
                "surface": str(record.get("surface", "unspecified")),
                "stability": str(record.get("stability", "unspecified")),
                "responsibility": str(record.get("responsibility", "")),
                "supported_entry_points": _string_list(
                    record.get("supported_entry_points"),
                    field="semantic supported_entry_points",
                ),
                "inputs": _string_list(record.get("inputs"), field="semantic inputs"),
                "outputs": _string_list(record.get("outputs"), field="semantic outputs"),
                "knowledge_owned": _string_list(
                    record.get("knowledge_owned"), field="semantic knowledge_owned"
                ),
                "caller_obligations": _string_list(
                    record.get("caller_obligations"), field="semantic caller_obligations"
                ),
                "side_effects": _string_list(
                    record.get("side_effects"), field="semantic side_effects"
                ),
                "errors": _string_list(record.get("errors"), field="semantic errors"),
                "schemas": _string_list(record.get("schemas"), field="semantic schemas"),
                "authority_boundary": str(record.get("authority_boundary", "")),
            }
        )
    return {
        "schema": str(document["schema"]),
        "kind": "semantics",
        "lane": str(document.get("lane", "maintained-intent")),
        "records": sorted(records, key=lambda item: (item["module"], item["claim_kind"])),
        "system": _normalize_system(document.get("system")),
    }


def _normalize_runtime_effects(
    document: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> dict[str, Any]:
    if document.get("schema") != "sunofriend-architecture-effects.v1":
        raise ValueError("unsupported runtime effects schema")
    records = document.get("records", [])
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ValueError("runtime effect records must be a bounded list")
    binding = document.get("binding", {})
    tree_hash = binding.get("source_tree_sha256") if isinstance(binding, Mapping) else None
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("target"), Mapping):
            raise ValueError("runtime effect records require a target")
        state, module_name = _attachment(
            record["target"],
            document_tree_hash=tree_hash,
            architecture=architecture,
        )
        normalized.append(
            {
                "module": module_name or str(record["target"].get("module", "unknown")),
                "attachment": state,
                "phase": str(record.get("phase", "unknown")),
                "declared_policy": record.get("declared_policy", []),
                "observations": record.get("observations", []),
            }
        )
    return {
        "schema": str(document["schema"]),
        "kind": "runtime_effects",
        "lane": str(document.get("lane", "maintained-effects")),
        "records": sorted(normalized, key=lambda item: (item["module"], item["phase"])),
    }


def _normalize_risk(
    document: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> dict[str, Any]:
    if document.get("schema") != "sunofriend-code-risk.v1":
        raise ValueError("unsupported code-risk schema")
    functions = document.get("functions", [])
    if not isinstance(functions, list) or len(functions) > MAX_RECORDS:
        raise ValueError("code-risk functions must be a bounded list")
    binding = document.get("binding", {})
    tree_hash = binding.get("source_tree_sha256") if isinstance(binding, Mapping) else None
    formula = document.get("formula", {})
    threshold = Decimal(str(formula.get("threshold", 30))) if isinstance(formula, Mapping) else Decimal(30)
    records: list[dict[str, Any]] = []
    identities: set[tuple[str, str, int]] = set()
    for record in functions:
        if not isinstance(record, Mapping) or not isinstance(record.get("target"), Mapping):
            raise ValueError("code-risk records require a target")
        target = record["target"]
        state, module_name = _function_attachment(
            target,
            document_tree_hash=tree_hash,
            architecture=architecture,
        )
        qualified_name = str(target.get("qualified_name", ""))
        line = int(target.get("line", 0))
        identity = (module_name or str(target.get("module", "")), qualified_name, line)
        if identity in identities:
            raise ValueError(f"duplicate code-risk function identity: {identity}")
        identities.add(identity)
        complexity = int(record.get("complexity", 0))
        coverage = record.get("coverage", {})
        if complexity < 1 or not isinstance(coverage, Mapping):
            raise ValueError("code-risk complexity and coverage are invalid")
        covered = int(coverage.get("covered_opportunities", 0))
        possible = int(coverage.get("possible_opportunities", 0))
        if covered < 0 or possible < 0 or covered > possible:
            raise ValueError("code-risk coverage opportunities are invalid")
        if possible == 0:
            score: Decimal | None = None
            status = "unmeasured"
            percentage: Decimal | None = None
        else:
            with localcontext() as context:
                context.prec = 40
                fraction = Decimal(covered) / Decimal(possible)
                score = Decimal(complexity * complexity) * (Decimal(1) - fraction) ** 3 + Decimal(complexity)
                percentage = fraction * Decimal(100)
            status = "warning" if score > threshold else "ok"
        records.append(
            {
                "module": module_name or str(target.get("module", "unknown")),
                "attachment": state,
                "qualified_name": qualified_name,
                "line": line,
                "end_line": int(target.get("end_line", line)),
                "complexity": complexity,
                "covered_opportunities": covered,
                "possible_opportunities": possible,
                "coverage_percentage": None if percentage is None else format(percentage.quantize(Decimal("0.001")), "f"),
                "crap_score": None if score is None else format(score.quantize(Decimal("0.000001")), "f"),
                "threshold": format(threshold, "f"),
                "status": status,
            }
        )
    return {
        "schema": str(document["schema"]),
        "kind": "risk",
        "lane": str(document.get("lane", "code-risk")),
        "formula": {
            "id": str(formula.get("id", "crap1")) if isinstance(formula, Mapping) else "crap1",
            "threshold": format(threshold, "f"),
        },
        "records": sorted(
            records,
            key=lambda item: (
                -(Decimal(item["crap_score"]) if item["crap_score"] is not None else Decimal(-1)),
                item["module"],
                item["qualified_name"],
            ),
        ),
    }


def _normalize_mutation(
    document: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> dict[str, Any]:
    if document.get("schema") != "sunofriend-mutation-report.v1":
        raise ValueError("unsupported mutation report schema")
    mutants = document.get("mutants", [])
    if not isinstance(mutants, list) or len(mutants) > MAX_RECORDS:
        raise ValueError("mutation records must be a bounded list")
    binding = document.get("binding", {})
    before_hash = binding.get("source_tree_sha256_before") if isinstance(binding, Mapping) else None
    after_hash = binding.get("source_tree_sha256_after") if isinstance(binding, Mapping) else None
    run_status = str(document.get("run_status", "incomplete"))
    if before_hash != after_hash:
        run_status = "invalid_source_not_restored"
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mutant in mutants:
        if not isinstance(mutant, Mapping) or not isinstance(mutant.get("target"), Mapping):
            raise ValueError("mutation records require a target")
        mutant_id = str(mutant.get("id", ""))
        if not mutant_id or mutant_id in seen:
            raise ValueError("mutation ids must be non-empty and unique")
        seen.add(mutant_id)
        status = str(mutant.get("status", ""))
        if status not in MUTATION_STATES:
            raise ValueError(f"unsupported mutation status: {status!r}")
        state, module_name = _function_attachment(
            mutant["target"],
            document_tree_hash=before_hash,
            architecture=architecture,
        )
        normalized.append(
            {
                "id": mutant_id,
                "module": module_name or str(mutant["target"].get("module", "unknown")),
                "attachment": state,
                "qualified_name": str(mutant["target"].get("qualified_name", "")),
                "line": int(mutant.get("line", mutant["target"].get("line", 0))),
                "operator": str(mutant.get("operator", "unknown")),
                "status": status,
                "equivalence": mutant.get("equivalence", {"classification": "not_reviewed"}),
            }
        )
    counts = {state: sum(item["status"] == state for item in normalized) for state in sorted(MUTATION_STATES)}
    return {
        "schema": str(document["schema"]),
        "kind": "mutation",
        "lane": str(document.get("lane", "mutation")),
        "run_status": run_status,
        "counts": counts,
        "records": sorted(normalized, key=lambda item: (item["module"], item["line"], item["id"])),
    }


def _safe_context(value: str) -> str:
    if (
        len(value) > 240
        or any(ord(character) < 32 for character in value)
        or re.search(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|private)/|https?://)", value)
    ):
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"redacted-context-{digest}"
    return value


def _normalize_coverage(
    document: Mapping[str, Any],
    raw: bytes,
    architecture: Mapping[str, Any],
    binding_document: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(document.get("meta"), Mapping) or not isinstance(document.get("files"), Mapping):
        raise ValueError("coverage report is not coverage.py JSON")
    binding_valid = False
    tree_hash: str | None = None
    file_hashes: Mapping[str, Any] = {}
    if binding_document is not None:
        if binding_document.get("schema") != "sunofriend-coverage-binding.v1":
            raise ValueError("unsupported coverage binding schema")
        if binding_document.get("coverage_json_sha256") != hashlib.sha256(raw).hexdigest():
            raise ValueError("coverage binding artifact digest differs")
        before = binding_document.get("source_tree_sha256_before")
        after = binding_document.get("source_tree_sha256_after")
        if before != after:
            raise ValueError("coverage source changed during measurement")
        tree_hash = str(before)
        file_hashes = binding_document.get("files", {})
        if not isinstance(file_hashes, Mapping):
            raise ValueError("coverage binding files must be an object")
        binding_valid = True
    by_path, _ = _module_lookup(architecture)
    records: list[dict[str, Any]] = []
    for raw_path, value in sorted(document["files"].items()):
        path = _relative_path(raw_path)
        if not isinstance(value, Mapping):
            raise ValueError("coverage file record must be an object")
        module_name = by_path.get(path)
        summary = value.get("summary", {})
        if not isinstance(summary, Mapping):
            raise ValueError("coverage summary must be an object")
        target: dict[str, Any] = {"path": path, "module": module_name or "unknown"}
        if binding_valid and path in file_hashes:
            target["source_sha256"] = str(file_hashes[path])
        state, resolved = _attachment(
            target,
            document_tree_hash=tree_hash,
            architecture=architecture,
        )
        contexts = value.get("contexts", {})
        normalized_contexts = {
            str(line): sorted({_safe_context(str(item)) for item in labels})
            for line, labels in contexts.items()
            if isinstance(labels, list)
        } if isinstance(contexts, Mapping) else {}
        records.append(
            {
                "module": resolved or module_name or "unknown",
                "path": path,
                "attachment": state,
                "summary": {
                    key: summary.get(key)
                    for key in (
                        "covered_lines",
                        "num_statements",
                        "percent_covered",
                        "covered_branches",
                        "num_branches",
                    )
                    if key in summary
                },
                "contexts": normalized_contexts,
                "functions": value.get("functions", {}),
            }
        )
    return {
        "schema": "sunofriend-coverage-overlay.v1",
        "kind": "coverage",
        "lane": "coverage.py",
        "producer": {
            "name": "coverage.py",
            "version": str(document["meta"].get("version", "unknown")),
            "format": document["meta"].get("format"),
            "branch_coverage": bool(document["meta"].get("branch_coverage", False)),
        },
        "binding": "hash_bound" if binding_valid else "unbound",
        "records": records,
    }


def build_overlay_bundle(
    architecture: Mapping[str, Any],
    *,
    semantic_annotations: Path | None = None,
    runtime_effects: Path | None = None,
    risk_report: Path | None = None,
    mutation_report: Path | None = None,
    coverage_json: Path | None = None,
    coverage_binding: Path | None = None,
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    if semantic_annotations is not None:
        value, _ = _read_document(semantic_annotations)
        documents.append(_normalize_semantics(value, architecture))
    if runtime_effects is not None:
        value, _ = _read_document(runtime_effects)
        documents.append(_normalize_runtime_effects(value, architecture))
    if risk_report is not None:
        value, _ = _read_document(risk_report)
        documents.append(_normalize_risk(value, architecture))
    if mutation_report is not None:
        value, _ = _read_document(mutation_report)
        documents.append(_normalize_mutation(value, architecture))
    if coverage_binding is not None and coverage_json is None:
        raise ValueError("--coverage-binding requires --coverage-json")
    if coverage_json is not None:
        value, raw = _read_document(coverage_json)
        binding = _read_document(coverage_binding)[0] if coverage_binding is not None else None
        documents.append(_normalize_coverage(value, raw, architecture, binding))
    identities: set[tuple[str, str]] = set()
    for document in documents:
        identity = (str(document["kind"]), str(document["lane"]))
        if identity in identities:
            raise ValueError(f"duplicate overlay kind/lane: {identity}")
        identities.add(identity)
    documents.sort(key=lambda item: (item["kind"], item["lane"]))
    return {
        "schema": OVERLAYS_SCHEMA,
        "base": _base(architecture),
        "documents": documents,
        "diagnostics": [],
    }
