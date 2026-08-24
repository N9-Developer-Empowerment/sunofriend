"""Evaluate deterministic dependency contracts over an architecture document."""

from __future__ import annotations

import fnmatch
from typing import Any, Iterable, Mapping, Sequence


SUPPORTED_CONTRACT_TYPES = {"forbidden", "allowed", "independence", "layers", "acyclic"}


def _names(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"contract selector {field} must be a list of strings")
    return tuple(value)


def _selector(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("contract selector must be an object")
    for field in ("groups", "modules", "prefixes", "patterns"):
        _names(value.get(field), field=field)
    return value


def _matches(
    module_name: str,
    module: Mapping[str, Any],
    selector: Mapping[str, Any],
    group_paths: Mapping[str, Sequence[str]],
) -> bool:
    short_name = str(module.get("short_name", module_name))
    groups = set(_names(selector.get("groups"), field="groups"))
    if groups and groups.intersection(group_paths.get(str(module.get("group")), ())):
        return True
    configured_modules = set(_names(selector.get("modules"), field="modules"))
    if module_name in configured_modules or short_name in configured_modules:
        return True
    if any(
        module_name.startswith(prefix) or short_name.startswith(prefix)
        for prefix in _names(selector.get("prefixes"), field="prefixes")
    ):
        return True
    return any(
        fnmatch.fnmatchcase(module_name, pattern) or fnmatch.fnmatchcase(short_name, pattern)
        for pattern in _names(selector.get("patterns"), field="patterns")
    )


def _ignored(
    contract: Mapping[str, Any],
    source: str,
    target: str,
) -> Mapping[str, Any] | None:
    ignores = contract.get("ignores", [])
    if not isinstance(ignores, list):
        raise ValueError("contract ignores must be a list")
    for ignore in ignores:
        if not isinstance(ignore, Mapping):
            raise ValueError("each contract ignore must be an object")
        if ignore.get("source") == source and ignore.get("target") == target:
            reason = str(ignore.get("reason", "")).strip()
            if not reason:
                raise ValueError("contract ignores require a reason")
            until = str(ignore.get("until", "")).strip()
            review_condition = str(ignore.get("review_condition", "")).strip()
            if not until and not review_condition:
                raise ValueError(
                    "contract ignores require an until date or review_condition"
                )
            return ignore
    return None


def _violation(
    contract: Mapping[str, Any],
    source: str,
    target: str,
    dependency: Mapping[str, Any],
    *,
    message: str,
) -> dict[str, Any]:
    return {
        "contract": str(contract["id"]),
        "contract_type": str(contract["type"]),
        "severity": str(contract.get("severity", "error")),
        "source": source,
        "target": target,
        "chain": [source, target],
        "message": message,
        "occurrences": list(dependency.get("occurrences", [])),
    }


def _edge_violations(
    architecture: Mapping[str, Any],
    contract: Mapping[str, Any],
    group_paths: Mapping[str, Sequence[str]],
) -> Iterable[dict[str, Any]]:
    modules = architecture["modules"]
    contract_type = str(contract["type"])
    source_selector: Mapping[str, Any] | None = None
    target_selector: Mapping[str, Any] | None = None
    members: list[Mapping[str, Any]] = []
    layers: list[Mapping[str, Any]] = []
    if contract_type in {"forbidden", "allowed"}:
        source_selector = _selector(contract.get("source"))
        target_selector = _selector(contract.get("target"))
    elif contract_type == "independence":
        raw_members = contract.get("members")
        if not isinstance(raw_members, list) or len(raw_members) < 2:
            raise ValueError("independence contracts require at least two member selectors")
        members = [_selector(item) for item in raw_members]
    elif contract_type == "layers":
        raw_layers = contract.get("layers")
        if not isinstance(raw_layers, list) or len(raw_layers) < 2:
            raise ValueError("layers contracts require at least two layer selectors")
        for layer in raw_layers:
            if not isinstance(layer, Mapping) or not str(layer.get("id", "")):
                raise ValueError("each layer requires an id and selector")
            layers.append({"id": str(layer["id"]), "selector": _selector(layer.get("selector"))})
    else:
        return

    for source, module in sorted(modules.items()):
        for dependency in module.get("imports", []):
            target = str(dependency["module"])
            if target not in modules:
                continue
            target_module = modules[target]
            message = ""
            if contract_type == "forbidden":
                assert source_selector is not None and target_selector is not None
                if _matches(source, module, source_selector, group_paths) and _matches(
                    target, target_module, target_selector, group_paths
                ):
                    message = "forbidden dependency"
            elif contract_type == "allowed":
                assert source_selector is not None and target_selector is not None
                if _matches(source, module, source_selector, group_paths) and not _matches(
                    target, target_module, target_selector, group_paths
                ):
                    message = "dependency is outside the allowed target set"
            elif contract_type == "independence":
                source_members = {
                    index
                    for index, selector in enumerate(members)
                    if _matches(source, module, selector, group_paths)
                }
                target_members = {
                    index
                    for index, selector in enumerate(members)
                    if _matches(target, target_module, selector, group_paths)
                }
                if source_members and target_members and source_members.isdisjoint(target_members):
                    message = "independent areas depend on one another"
            elif contract_type == "layers":
                source_layers = [
                    index
                    for index, layer in enumerate(layers)
                    if _matches(source, module, layer["selector"], group_paths)
                ]
                target_layers = [
                    index
                    for index, layer in enumerate(layers)
                    if _matches(target, target_module, layer["selector"], group_paths)
                ]
                if source_layers and target_layers and min(target_layers) < min(source_layers):
                    message = (
                        f"lower layer {layers[min(source_layers)]['id']} imports upper layer "
                        f"{layers[min(target_layers)]['id']}"
                    )
            if message:
                yield _violation(contract, source, target, dependency, message=message)


def _selected_components(
    architecture: Mapping[str, Any],
    selected: set[str],
) -> list[list[str]]:
    """Return deterministic strongly connected components in an induced graph."""

    modules = architecture["modules"]
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(name: str) -> None:
        nonlocal index
        indices[name] = index
        low_links[name] = index
        index += 1
        stack.append(name)
        on_stack.add(name)
        for neighbour in sorted(
            str(dependency["module"])
            for dependency in modules[name].get("imports", [])
            if str(dependency["module"]) in selected
        ):
            if neighbour not in indices:
                visit(neighbour)
                low_links[name] = min(low_links[name], low_links[neighbour])
            elif neighbour in on_stack:
                low_links[name] = min(low_links[name], indices[neighbour])
        if low_links[name] != indices[name]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == name:
                break
        components.append(sorted(component))

    for name in sorted(selected):
        if name not in indices:
            visit(name)
    return sorted(components, key=lambda item: item[0])


def _path(
    architecture: Mapping[str, Any],
    source: str,
    target: str,
    allowed: set[str],
) -> list[str]:
    pending: list[tuple[str, list[str]]] = [(source, [source])]
    seen = {source}
    while pending:
        current, chain = pending.pop(0)
        if current == target:
            return chain
        for neighbour in sorted(
            str(item["module"])
            for item in architecture["modules"][current].get("imports", [])
            if str(item["module"]) in allowed
        ):
            if neighbour not in seen:
                seen.add(neighbour)
                pending.append((neighbour, [*chain, neighbour]))
    raise ValueError("strongly connected component has no expected return path")


def _acyclic_violations(
    architecture: Mapping[str, Any],
    contract: Mapping[str, Any],
    group_paths: Mapping[str, Sequence[str]],
) -> Iterable[dict[str, Any]]:
    selector = _selector(contract.get("selector"))
    modules = architecture["modules"]
    selected = {
        name
        for name, module in modules.items()
        if _matches(name, module, selector, group_paths)
    }
    for component in _selected_components(architecture, selected):
        members = set(component)
        cyclic = len(component) > 1 or any(
            dependency["module"] == component[0]
            for dependency in modules[component[0]].get("imports", [])
        )
        if not cyclic:
            continue
        for source in component:
            for dependency in modules[source].get("imports", []):
                target = str(dependency["module"])
                if target not in members:
                    continue
                return_path = _path(architecture, target, source, members)
                yield {
                    "contract": str(contract["id"]),
                    "contract_type": "acyclic",
                    "severity": str(contract.get("severity", "error")),
                    "source": source,
                    "target": target,
                    "chain": [source, *return_path],
                    "message": "selected dependency participates in a static import cycle",
                    "occurrences": list(dependency.get("occurrences", [])),
                }


def evaluate_contracts(
    architecture: dict[str, Any],
    configured_contracts: Sequence[Mapping[str, Any]],
) -> None:
    """Attach checked contract results to ``architecture`` in deterministic order."""

    group_paths = {
        str(group["id"]): tuple(str(value) for value in group.get("path", [group["id"]]))
        for group in architecture.get("groups", [])
    }
    violations: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for contract in configured_contracts:
        contract_id = str(contract.get("id", ""))
        contract_type = str(contract.get("type", ""))
        if not contract_id:
            raise ValueError("contract id must be non-empty")
        if contract_type not in SUPPORTED_CONTRACT_TYPES:
            raise ValueError(f"unsupported contract type: {contract_type!r}")
        candidates = list(
            _acyclic_violations(architecture, contract, group_paths)
            if contract_type == "acyclic"
            else _edge_violations(architecture, contract, group_paths)
        )
        accepted: list[dict[str, Any]] = []
        ignored_for_contract: list[dict[str, Any]] = []
        for violation in candidates:
            ignore = _ignored(contract, violation["source"], violation["target"])
            if ignore is None:
                accepted.append(violation)
            else:
                ignored_for_contract.append(
                    {
                        **violation,
                        "ignore_reason": str(ignore["reason"]),
                        "ignore_until": ignore.get("until"),
                        "ignore_review_condition": ignore.get("review_condition"),
                    }
                )
        violations.extend(accepted)
        ignored.extend(ignored_for_contract)
        summaries.append(
            {
                "id": contract_id,
                "type": contract_type,
                "description": str(contract.get("description", "")),
                "severity": str(contract.get("severity", "error")),
                "status": "violated" if accepted else "passed",
                "violation_count": len(accepted),
                "ignored_count": len(ignored_for_contract),
            }
        )
    violations.sort(key=lambda item: (item["contract"], item["source"], item["target"]))
    ignored.sort(key=lambda item: (item["contract"], item["source"], item["target"]))
    for module in architecture["modules"].values():
        module["contract_violations"] = []
    for violation in violations:
        architecture["modules"][violation["source"]]["contract_violations"].append(violation)
    architecture["contracts"] = summaries
    architecture["violations"] = violations
    architecture["ignored_violations"] = ignored
    architecture["stats"]["contract_count"] = len(summaries)
    architecture["stats"]["contract_violation_count"] = len(violations)
    architecture["stats"]["ignored_contract_violation_count"] = len(ignored)
