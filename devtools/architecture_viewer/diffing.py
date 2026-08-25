"""Hash-bound comparisons and ratchets for architecture snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .analyzer import calculate_architecture_sha256


DIFF_SCHEMA = "sunofriend-architecture-diff.v1"
SUPPORTED_ARCHITECTURE_SCHEMAS = {
    "sunofriend-architecture-viewer.v1",
    "sunofriend-architecture-viewer.v2",
}


def load_architecture_snapshot(path: Path) -> dict[str, Any]:
    if path.is_dir():
        path = path / "architecture.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") not in SUPPORTED_ARCHITECTURE_SCHEMAS:
        raise ValueError(f"unsupported architecture snapshot: {path}")
    if not isinstance(document.get("modules"), dict):
        raise ValueError("architecture snapshot has no module map")
    if document.get("schema") == "sunofriend-architecture-viewer.v2":
        supplied_hash = document.get("architecture_sha256")
        calculated_hash = calculate_architecture_sha256(document)
        if supplied_hash != calculated_hash:
            raise ValueError("architecture snapshot integrity hash differs")
    return document


def _identity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": document.get("schema"),
        "package": document.get("package"),
        "source_root": document.get("source_root"),
        "source_tree_sha256": document.get("source_tree_sha256"),
        "group_configuration_sha256": document.get("group_configuration_sha256"),
        "contracts_sha256": document.get("contracts_sha256"),
        "architecture_sha256": document.get("architecture_sha256"),
    }


def _dependencies(document: Mapping[str, Any]) -> set[tuple[str, str]]:
    return {
        (source, str(dependency["module"]))
        for source, module in document["modules"].items()
        for dependency in module.get("imports", [])
    }


def _dependency_map(
    document: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (source, str(dependency["module"])): dependency
        for source, module in document["modules"].items()
        for dependency in module.get("imports", [])
    }


def _dependency_record(
    identity: tuple[str, str],
    dependency: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source": identity[0],
        "target": identity[1],
        "symbols": list(dependency.get("symbols", [])),
        "occurrences": list(dependency.get("occurrences", [])),
    }


def _surface(module: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()

    def add(definition: Mapping[str, Any]) -> None:
        result.add(
            (
                str(definition.get("qualified_name", definition.get("name", ""))),
                str(definition.get("kind", "")),
                str(definition.get("signature", "")),
            )
        )
        for member in definition.get("members", []):
            if isinstance(member, Mapping) and bool(member.get("public", True)):
                add(member)

    for definition in module.get("public_interface", []):
        if isinstance(definition, Mapping):
            add(definition)
    return result


def _cycles(document: Mapping[str, Any]) -> set[tuple[str, ...]]:
    return {tuple(sorted(str(item) for item in component)) for component in document.get("cycles", [])}


def _violations(document: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (str(item.get("contract", "")), str(item.get("source", "")), str(item.get("target", "")))
        for item in document.get("violations", [])
    }


def _group_metrics(document: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    return {
        str(group["id"]): {
            "module_count": int(group.get("module_count", len(group.get("modules", [])))),
            "line_count": int(group.get("line_count", 0)),
            "public_definition_count": int(group.get("public_definition_count", 0)),
        }
        for group in document.get("groups", [])
    }


def _module_metrics(document: Mapping[str, Any], name: str) -> dict[str, int]:
    module = document["modules"][name]
    return {
        "fan_in": len(module.get("imported_by", [])),
        "fan_out": len(module.get("imports", [])),
        "public_definitions": len(module.get("public_interface", [])),
        "implementation_definitions": len(module.get("implementation", [])),
        "line_count": int(module.get("line_count", 0)),
    }


def compare_architectures(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic semantic comparison without inferring renames."""

    if before.get("package") != after.get("package"):
        raise ValueError("architecture snapshots describe different packages")
    if before.get("source_root") != after.get("source_root"):
        raise ValueError("architecture snapshots describe different source roots")
    old_modules = before["modules"]
    new_modules = after["modules"]
    old_names = set(old_modules)
    new_names = set(new_modules)
    common = old_names & new_names
    added_modules = sorted(new_names - old_names)
    removed_modules = sorted(old_names - new_names)
    changed_modules = sorted(
        name
        for name in common
        if old_modules[name].get("source_sha256") != new_modules[name].get("source_sha256")
    )
    moved_modules = [
        {
            "module": name,
            "before_group": old_modules[name].get("group"),
            "after_group": new_modules[name].get("group"),
        }
        for name in sorted(common)
        if old_modules[name].get("group") != new_modules[name].get("group")
    ]
    public_changes: list[dict[str, Any]] = []
    for name in sorted(common):
        old_surface = _surface(old_modules[name])
        new_surface = _surface(new_modules[name])
        added = sorted(new_surface - old_surface)
        removed = sorted(old_surface - new_surface)
        if added or removed:
            public_changes.append(
                {
                    "module": name,
                    "added": [
                        {"qualified_name": item[0], "kind": item[1], "signature": item[2]}
                        for item in added
                    ],
                    "removed": [
                        {"qualified_name": item[0], "kind": item[1], "signature": item[2]}
                        for item in removed
                    ],
                }
            )
    old_dependency_map = _dependency_map(before)
    new_dependency_map = _dependency_map(after)
    old_dependencies = set(old_dependency_map)
    new_dependencies = set(new_dependency_map)
    retained_dependencies = old_dependencies & new_dependencies
    old_cycles = _cycles(before)
    new_cycles = _cycles(after)
    old_violations = _violations(before)
    new_violations = _violations(after)
    old_group_metrics = _group_metrics(before)
    new_group_metrics = _group_metrics(after)
    group_metric_changes = [
        {
            "group": group,
            "before": old_group_metrics.get(group),
            "after": new_group_metrics.get(group),
        }
        for group in sorted(set(old_group_metrics) | set(new_group_metrics))
        if old_group_metrics.get(group) != new_group_metrics.get(group)
    ]
    module_metric_changes = [
        {
            "module": name,
            "before": _module_metrics(before, name),
            "after": _module_metrics(after, name),
        }
        for name in sorted(common)
        if _module_metrics(before, name) != _module_metrics(after, name)
    ]
    document = {
        "schema": DIFF_SCHEMA,
        "before": _identity(before),
        "after": _identity(after),
        "modules": {
            "added": added_modules,
            "removed": removed_modules,
            "added_details": [
                {
                    "module": name,
                    "path": new_modules[name].get("path"),
                    "group": new_modules[name].get("group"),
                }
                for name in added_modules
            ],
            "removed_details": [
                {
                    "module": name,
                    "path": old_modules[name].get("path"),
                    "group": old_modules[name].get("group"),
                }
                for name in removed_modules
            ],
            "source_changed": changed_modules,
            "moved": moved_modules,
        },
        "public_interfaces": public_changes,
        "group_metrics": group_metric_changes,
        "module_metrics": module_metric_changes,
        "dependencies": {
            "added": [
                _dependency_record(identity, new_dependency_map[identity])
                for identity in sorted(new_dependencies - old_dependencies)
            ],
            "removed": [
                _dependency_record(identity, old_dependency_map[identity])
                for identity in sorted(old_dependencies - new_dependencies)
            ],
            "changed": [
                {
                    "source": identity[0],
                    "target": identity[1],
                    "before": {
                        "symbols": list(old_dependency_map[identity].get("symbols", [])),
                        "occurrences": list(
                            old_dependency_map[identity].get("occurrences", [])
                        ),
                    },
                    "after": {
                        "symbols": list(new_dependency_map[identity].get("symbols", [])),
                        "occurrences": list(
                            new_dependency_map[identity].get("occurrences", [])
                        ),
                    },
                }
                for identity in sorted(retained_dependencies)
                if (
                    old_dependency_map[identity].get("symbols", []),
                    old_dependency_map[identity].get("occurrences", []),
                )
                != (
                    new_dependency_map[identity].get("symbols", []),
                    new_dependency_map[identity].get("occurrences", []),
                )
            ],
        },
        "cycles": {
            "added": [list(value) for value in sorted(new_cycles - old_cycles)],
            "removed": [list(value) for value in sorted(old_cycles - new_cycles)],
        },
        "violations": {
            "added": [
                {"contract": value[0], "source": value[1], "target": value[2]}
                for value in sorted(new_violations - old_violations)
            ],
            "resolved": [
                {"contract": value[0], "source": value[1], "target": value[2]}
                for value in sorted(old_violations - new_violations)
            ],
        },
    }
    document["summary"] = {
        "modules_added": len(added_modules),
        "modules_removed": len(removed_modules),
        "modules_source_changed": len(changed_modules),
        "modules_moved": len(moved_modules),
        "public_interfaces_changed": len(public_changes),
        "group_metrics_changed": len(group_metric_changes),
        "module_metrics_changed": len(module_metric_changes),
        "dependencies_added": len(document["dependencies"]["added"]),
        "dependencies_removed": len(document["dependencies"]["removed"]),
        "dependencies_changed": len(document["dependencies"]["changed"]),
        "cycles_added": len(document["cycles"]["added"]),
        "cycles_removed": len(document["cycles"]["removed"]),
        "violations_added": len(document["violations"]["added"]),
        "violations_resolved": len(document["violations"]["resolved"]),
    }
    return document


def assess_ratchet(diff: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for violation in diff["violations"]["added"]:
        failures.append({"kind": "new_contract_violation", **violation})
    for cycle in diff["cycles"]["added"]:
        failures.append({"kind": "new_static_cycle", "modules": list(cycle)})
    if int(current.get("stats", {}).get("parse_error_count", 0)):
        failures.append(
            {
                "kind": "parse_errors",
                "count": int(current["stats"]["parse_error_count"]),
            }
        )
    if int(current.get("stats", {}).get("test_parse_error_count", 0)):
        failures.append(
            {
                "kind": "test_parse_errors",
                "count": int(current["stats"]["test_parse_error_count"]),
            }
        )
    return failures
