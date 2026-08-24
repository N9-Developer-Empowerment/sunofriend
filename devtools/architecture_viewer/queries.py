"""Small, deterministic architecture queries for humans and fresh-context agents."""

from __future__ import annotations

from collections import deque
from typing import Any, Mapping


QUERY_SCHEMA = "sunofriend-architecture-query.v1"


def _base(architecture: Mapping[str, Any], kind: str) -> dict[str, Any]:
    return {
        "schema": QUERY_SCHEMA,
        "kind": kind,
        "package": architecture.get("package"),
        "source_tree_sha256": architecture.get("source_tree_sha256"),
        "architecture_sha256": architecture.get("architecture_sha256"),
    }


def module_query(architecture: Mapping[str, Any], name: str) -> dict[str, Any]:
    modules = architecture["modules"]
    if name not in modules:
        matching = [module_name for module_name, value in modules.items() if value.get("short_name") == name]
        if len(matching) != 1:
            raise ValueError(f"unknown or ambiguous module: {name}")
        name = matching[0]
    return {**_base(architecture, "module"), "module": modules[name]}


def neighbourhood_query(
    architecture: Mapping[str, Any],
    name: str,
    *,
    depth: int = 1,
) -> dict[str, Any]:
    if depth < 0 or depth > 8:
        raise ValueError("neighbourhood depth must be between 0 and 8")
    resolved = module_query(architecture, name)["module"]["name"]
    modules = architecture["modules"]
    seen = {resolved}
    queue: deque[tuple[str, int]] = deque([(resolved, 0)])
    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        neighbours = {
            str(item["module"]) for item in modules[current].get("imports", [])
        } | set(str(item) for item in modules[current].get("imported_by", []))
        for neighbour in sorted(neighbours):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append((neighbour, current_depth + 1))
    edges = [
        {
            "source": source,
            "target": str(dependency["module"]),
            "symbols": list(dependency.get("symbols", [])),
            "occurrences": list(dependency.get("occurrences", [])),
        }
        for source in sorted(seen)
        for dependency in modules[source].get("imports", [])
        if dependency["module"] in seen
    ]
    return {
        **_base(architecture, "neighbourhood"),
        "subject": resolved,
        "depth": depth,
        "modules": [
            {
                "name": module_name,
                "path": modules[module_name]["path"],
                "group_path": modules[module_name].get("group_path", [modules[module_name]["group"]]),
                "summary": modules[module_name].get("summary", ""),
            }
            for module_name in sorted(seen)
        ],
        "dependencies": edges,
    }


def violations_query(architecture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_base(architecture, "violations"),
        "contracts": architecture.get("contracts", []),
        "violations": architecture.get("violations", []),
        "ignored": architecture.get("ignored_violations", []),
    }


def cycles_query(architecture: Mapping[str, Any]) -> dict[str, Any]:
    cycles = architecture.get("cycles", [])
    modules = architecture["modules"]
    evidence = []
    for index, component in enumerate(cycles, start=1):
        members = set(component)
        evidence.append(
            {
                "cycle": index,
                "modules": list(component),
                "dependencies": [
                    {
                        "source": source,
                        "target": dependency["module"],
                        "symbols": dependency.get("symbols", []),
                        "occurrences": dependency.get("occurrences", []),
                    }
                    for source in component
                    for dependency in modules[source].get("imports", [])
                    if dependency["module"] in members
                ],
            }
        )
    return {**_base(architecture, "cycles"), "cycles": cycles, "evidence": evidence}


def dependency_path_query(
    architecture: Mapping[str, Any],
    source: str,
    target: str,
) -> dict[str, Any]:
    modules = architecture["modules"]
    source = module_query(architecture, source)["module"]["name"]
    target = module_query(architecture, target)["module"]["name"]
    queue: deque[str] = deque([source])
    previous: dict[str, str | None] = {source: None}
    while queue and target not in previous:
        current = queue.popleft()
        for dependency in sorted(
            str(item["module"]) for item in modules[current].get("imports", [])
        ):
            if dependency not in previous:
                previous[dependency] = current
                queue.append(dependency)
    chain: list[str] | None = None
    if target in previous:
        chain = []
        current: str | None = target
        while current is not None:
            chain.append(current)
            current = previous[current]
        chain.reverse()
    evidence: list[dict[str, Any]] = []
    if chain:
        for left, right in zip(chain, chain[1:]):
            dependency = next(item for item in modules[left]["imports"] if item["module"] == right)
            evidence.append(
                {
                    "source": left,
                    "target": right,
                    "symbols": dependency.get("symbols", []),
                    "occurrences": dependency.get("occurrences", []),
                }
            )
    return {
        **_base(architecture, "dependency_path"),
        "source": source,
        "target": target,
        "found": chain is not None,
        "chain": chain,
        "evidence": evidence,
    }
