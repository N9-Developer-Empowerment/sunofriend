"""Extract a deterministic architecture model without importing source code."""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ARCHITECTURE_SCHEMA = "sunofriend-architecture-viewer.v2"
GROUPS_SCHEMAS = {
    "sunofriend-architecture-groups.v1",
    "sunofriend-architecture-groups.v2",
}


@dataclass(frozen=True)
class GroupRule:
    id: str
    label: str
    description: str
    modules: tuple[str, ...]
    prefixes: tuple[str, ...]
    patterns: tuple[str, ...]
    parent: str | None
    order: int


@dataclass(frozen=True)
class GroupConfiguration:
    groups: tuple[GroupRule, ...]
    default_group: GroupRule
    contracts: tuple[Mapping[str, Any], ...]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def calculate_architecture_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical integrity digest for an architecture document."""

    unhashed = dict(document)
    unhashed.pop("architecture_sha256", None)
    return _sha256_bytes(
        json.dumps(
            unhashed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def _source_name(module_name: str, package_name: str) -> str:
    if module_name == package_name:
        return "__init__"
    return module_name[len(package_name) + 1 :]


def _module_name(path: Path, source_root: Path, package_name: str) -> str:
    relative = path.relative_to(source_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join([package_name, *parts]) if parts else package_name


def _literal_string_sequence(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for item in node.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return None
            values.append(item.value)
        return tuple(values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_string_sequence(node.left)
        right = _literal_string_sequence(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _declared_all(tree: ast.Module) -> tuple[str, ...] | None:
    current: tuple[str, ...] | None = None
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: Sequence[ast.expr]
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            else:
                targets = (node.target,)
                value = node.value
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                current = _literal_string_sequence(value) if value is not None else None
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
            and isinstance(node.op, ast.Add)
        ):
            addition = _literal_string_sequence(node.value)
            if current is not None and addition is not None:
                current += addition
            else:
                current = None
    return current


def _has_declared_all(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in node.targets
            ):
                return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "__all__":
                return True
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "__all__":
                return True
    return False


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return ""


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        result = f"{prefix}{node.name}({_unparse(node.args)})"
        if node.returns is not None:
            result += f" -> {_unparse(node.returns)}"
        return result
    if isinstance(node, ast.ClassDef):
        bases = [_unparse(value) for value in node.bases]
        bases.extend(
            f"{keyword.arg}={_unparse(keyword.value)}"
            for keyword in node.keywords
            if keyword.arg
        )
        suffix = f"({', '.join(bases)})" if bases else ""
        return f"class {node.name}{suffix}"
    return ""


def _definition(node: ast.AST, *, qualified_name: str | None = None) -> dict[str, Any]:
    name = getattr(node, "name")
    if isinstance(node, ast.ClassDef):
        kind = "class"
    elif isinstance(node, ast.AsyncFunctionDef):
        kind = "async function"
    else:
        kind = "function"
    document = ast.get_docstring(node, clean=True) or ""
    result: dict[str, Any] = {
        "name": name,
        "qualified_name": qualified_name or name,
        "kind": kind,
        "signature": _signature(node),
        "line": int(getattr(node, "lineno", 1)),
        "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
        "summary": document.splitlines()[0] if document else "",
        "public": not name.startswith("_"),
    }
    if isinstance(node, ast.ClassDef):
        result["members"] = [
            _definition(child, qualified_name=f"{name}.{child.name}")
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    return result


def _exported_binding(tree: ast.Module, name: str) -> dict[str, Any]:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local_name = alias.asname or alias.name
                if local_name == name:
                    source = "." * node.level + (node.module or "")
                    return {
                        "name": name,
                        "qualified_name": name,
                        "kind": "re-export",
                        "signature": name,
                        "line": int(node.lineno),
                        "end_line": int(getattr(node, "end_lineno", node.lineno)),
                        "summary": f"Re-exported from {source or 'the package' }.",
                        "public": True,
                    }
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                if local_name == name:
                    return {
                        "name": name,
                        "qualified_name": name,
                        "kind": "re-export",
                        "signature": name,
                        "line": int(node.lineno),
                        "end_line": int(getattr(node, "end_lineno", node.lineno)),
                        "summary": f"Re-exported from {alias.name}.",
                        "public": True,
                    }
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return {
                    "name": name,
                    "qualified_name": name,
                    "kind": "exported value",
                    "signature": name,
                    "line": int(node.lineno),
                    "end_line": int(getattr(node, "end_lineno", node.lineno)),
                    "summary": "Exported module value.",
                    "public": True,
                }
    return {
        "name": name,
        "qualified_name": name,
        "kind": "unresolved export",
        "signature": name,
        "line": 1,
        "end_line": 1,
        "summary": "Listed in __all__, but its binding is dynamic or not statically visible.",
        "public": True,
    }


def _definitions(
    tree: ast.Module,
    declared_all: tuple[str, ...] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    exported = set(declared_all) if declared_all is not None else {
        node.name for node in nodes if not node.name.startswith("_")
    }
    interface: list[dict[str, Any]] = []
    implementation: list[dict[str, Any]] = []
    for node in nodes:
        value = _definition(node)
        if node.name in exported:
            interface.append(value)
        else:
            implementation.append(value)
    if declared_all is not None:
        visible = {item["name"] for item in interface}
        interface.extend(
            _exported_binding(tree, name)
            for name in declared_all
            if name not in visible
        )
    return interface, implementation


def _longest_known_module(name: str, known_modules: set[str]) -> str | None:
    value = name
    while value:
        if value in known_modules:
            return value
        if "." not in value:
            return None
        value = value.rsplit(".", 1)[0]
    return None


def _relative_base(
    current_module: str,
    *,
    current_is_package: bool,
    level: int,
    imported_module: str | None,
) -> str:
    if level == 0:
        return imported_module or ""
    package_parts = current_module.split(".")
    if not current_is_package:
        package_parts.pop()
    ascend = level - 1
    if ascend > len(package_parts):
        return ""
    if ascend:
        package_parts = package_parts[:-ascend]
    if imported_module:
        package_parts.extend(imported_module.split("."))
    return ".".join(package_parts)


def _contains_type_checking(node: ast.AST) -> bool:
    return any(
        (isinstance(value, ast.Name) and value.id == "TYPE_CHECKING")
        or (isinstance(value, ast.Attribute) and value.attr == "TYPE_CHECKING")
        for value in ast.walk(node)
    )


class _ImportCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        current_module: str,
        current_is_package: bool,
        package_name: str,
        known_modules: set[str],
    ) -> None:
        self.current_module = current_module
        self.current_is_package = current_is_package
        self.package_name = package_name
        self.known_modules = known_modules
        self.internal: dict[str, dict[str, Any]] = {}
        self.external: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.scope: list[str] = []
        self.guards: list[str] = []

    def _context(self) -> dict[str, str]:
        guard = "none"
        for candidate in ("type_checking", "try", "conditional"):
            if candidate in self.guards:
                guard = candidate
                break
        return {
            "scope": "module" if not self.scope else ".".join(self.scope),
            "runtime": "module" if not self.scope or self.scope[-1].startswith("class:") else "deferred",
            "guard": guard,
        }

    def _occurrence(
        self,
        node: ast.AST,
        *,
        kind: str,
        requested: str,
        symbols: Iterable[str] = (),
        confidence: str = "exact",
    ) -> dict[str, Any]:
        return {
            "line": int(getattr(node, "lineno", 1)),
            "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
            "kind": kind,
            "requested": requested,
            "symbols": sorted(set(symbols)),
            "confidence": confidence,
            **self._context(),
        }

    def _add_internal(
        self,
        target: str,
        node: ast.AST,
        *,
        kind: str,
        requested: str,
        symbols: Iterable[str] = (),
        confidence: str = "exact",
    ) -> None:
        if target == self.current_module:
            return
        record = self.internal.setdefault(target, {"symbols": set(), "occurrences": []})
        record["symbols"].update(symbols)
        record["occurrences"].append(
            self._occurrence(
                node,
                kind=kind,
                requested=requested,
                symbols=symbols,
                confidence=confidence,
            )
        )

    def _add_external(
        self,
        root: str,
        node: ast.AST,
        *,
        kind: str,
        requested: str,
        symbols: Iterable[str] = (),
        confidence: str = "exact",
    ) -> None:
        self.external[root].append(
            self._occurrence(
                node,
                kind=kind,
                requested=requested,
                symbols=symbols,
                confidence=confidence,
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(f"function:{node.name}")
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(f"class:{node.name}")
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        self.guards.append("type_checking" if _contains_type_checking(node.test) else "conditional")
        for child in node.body:
            self.visit(child)
        self.guards.pop()
        if node.orelse:
            self.guards.append("conditional")
            for child in node.orelse:
                self.visit(child)
            self.guards.pop()

    def visit_Try(self, node: ast.Try) -> None:
        self.guards.append("try")
        for child in [*node.body, *node.handlers, *node.orelse, *node.finalbody]:
            self.visit(child)
        self.guards.pop()

    visit_TryStar = visit_Try

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            target = _longest_known_module(alias.name, self.known_modules)
            if target is not None:
                self._add_internal(target, node, kind="import", requested=alias.name)
            else:
                self._add_external(
                    alias.name.split(".", 1)[0],
                    node,
                    kind="import",
                    requested=alias.name,
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = _relative_base(
            self.current_module,
            current_is_package=self.current_is_package,
            level=node.level,
            imported_module=node.module,
        )
        unresolved_symbols: list[str] = []
        for alias in node.names:
            if alias.name == "*":
                unresolved_symbols.append(alias.name)
                continue
            candidate = f"{base}.{alias.name}" if base else alias.name
            target = _longest_known_module(candidate, self.known_modules)
            if target == candidate:
                self._add_internal(
                    target,
                    node,
                    kind="from",
                    requested=candidate,
                )
            else:
                unresolved_symbols.append(alias.name)
        if not unresolved_symbols:
            return
        target = _longest_known_module(base, self.known_modules)
        requested = "." * node.level + (node.module or "")
        if target is not None:
            self._add_internal(
                target,
                node,
                kind="from",
                requested=requested,
                symbols=unresolved_symbols,
            )
        elif base and not base.startswith(self.package_name + ".") and base != self.package_name:
            self._add_external(
                base.split(".", 1)[0],
                node,
                kind="from",
                requested=requested,
                symbols=unresolved_symbols,
            )

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name in {"__import__", "importlib.import_module"} and node.args:
            value = node.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                requested = value.value
                resolved = requested
                if requested.startswith("."):
                    level = len(requested) - len(requested.lstrip("."))
                    resolved = _relative_base(
                        self.current_module,
                        current_is_package=self.current_is_package,
                        level=level,
                        imported_module=requested[level:] or None,
                    )
                target = _longest_known_module(resolved, self.known_modules)
                if target is not None:
                    self._add_internal(
                        target,
                        node,
                        kind="dynamic",
                        requested=requested,
                        confidence="literal_dynamic",
                    )
                elif resolved:
                    self._add_external(
                        resolved.split(".", 1)[0],
                        node,
                        kind="dynamic",
                        requested=requested,
                        confidence="literal_dynamic",
                    )
        self.generic_visit(node)


def _imports(
    tree: ast.Module,
    *,
    current_module: str,
    current_is_package: bool,
    package_name: str,
    known_modules: set[str],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    collector = _ImportCollector(
        current_module=current_module,
        current_is_package=current_is_package,
        package_name=package_name,
        known_modules=known_modules,
    )
    collector.visit(tree)
    internal = [
        {
            "module": module,
            "symbols": sorted(record["symbols"]),
            "occurrences": sorted(
                record["occurrences"],
                key=lambda item: (item["line"], item["requested"], item["kind"]),
            ),
        }
        for module, record in sorted(collector.internal.items())
    ]
    details = [
        {"root": root, "occurrences": sorted(values, key=lambda item: item["line"])}
        for root, values in sorted(collector.external.items())
    ]
    return internal, sorted(collector.external), details


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


_EFFECT_CALLS = {
    "open": "filesystem",
    "Path.open": "filesystem",
    "Path.read_text": "filesystem_read",
    "Path.read_bytes": "filesystem_read",
    "Path.write_text": "filesystem_write",
    "Path.write_bytes": "filesystem_write",
    "Path.mkdir": "filesystem_write",
    "Path.unlink": "filesystem_write",
    "Path.rename": "filesystem_write",
    "Path.replace": "filesystem_write",
    "os.remove": "filesystem_write",
    "os.unlink": "filesystem_write",
    "os.rename": "filesystem_write",
    "os.replace": "filesystem_write",
    "os.mkdir": "filesystem_write",
    "os.makedirs": "filesystem_write",
    "shutil.copy": "filesystem_write",
    "shutil.copy2": "filesystem_write",
    "shutil.copytree": "filesystem_write",
    "shutil.move": "filesystem_write",
    "shutil.rmtree": "filesystem_write",
    "subprocess.run": "process",
    "subprocess.Popen": "process",
    "subprocess.call": "process",
    "subprocess.check_call": "process",
    "subprocess.check_output": "process",
    "os.system": "process",
}
_NETWORK_ROOTS = {"socket", "requests", "urllib", "urllib3", "httpx", "aiohttp"}


class _EffectCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.aliases: dict[str, str] = {}
        self.effects: list[dict[str, Any]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".", 1)[0]
            self.aliases[local] = alias.name if alias.asname else local

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            return
        for alias in node.names:
            if alias.name != "*":
                self.aliases[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}" if node.module else alias.name
                )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        parts = name.split(".")
        if parts and parts[0] in self.aliases:
            name = ".".join([self.aliases[parts[0]], *parts[1:]])
        short_name = ".".join(name.split(".")[-2:])
        kind = _EFFECT_CALLS.get(name) or _EFFECT_CALLS.get(short_name)
        if kind is None and name.split(".", 1)[0] in _NETWORK_ROOTS:
            kind = "network"
        if name in {"__import__", "importlib.import_module"}:
            kind = "dynamic_import"
        if kind is not None:
            if name == "open":
                mode = node.args[1] if len(node.args) > 1 else next(
                    (keyword.value for keyword in node.keywords if keyword.arg == "mode"),
                    None,
                )
                if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                    kind = "filesystem_write" if any(flag in mode.value for flag in "wax+") else "filesystem_read"
            self.effects.append(
                {
                    "kind": kind,
                    "operation": name,
                    "line": int(getattr(node, "lineno", 1)),
                    "scope": ".".join(self.scope) if self.scope else "module",
                    "confidence": "static_call_candidate",
                }
            )
        self.generic_visit(node)


def _effects(tree: ast.Module) -> list[dict[str, Any]]:
    collector = _EffectCollector()
    collector.visit(tree)
    return sorted(collector.effects, key=lambda item: (item["line"], item["operation"]))


def load_group_configuration(path: Path | None) -> GroupConfiguration:
    if path is None:
        default = GroupRule(
            id="all",
            label="All modules",
            description="No architecture grouping configuration was supplied.",
            modules=(),
            prefixes=(),
            patterns=(),
            parent=None,
            order=0,
        )
        return GroupConfiguration(groups=(default,), default_group=default, contracts=())
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") not in GROUPS_SCHEMAS:
        raise ValueError(f"unsupported group configuration schema: {document.get('schema')!r}")
    raw_groups = document.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ValueError("group configuration must contain a non-empty groups list")
    rules: list[GroupRule] = []
    ids: set[str] = set()

    def add_group(value: Any, parent: str | None = None) -> None:
        if not isinstance(value, Mapping):
            raise ValueError("each group must be an object")
        group_id = str(value.get("id", ""))
        label = str(value.get("label", ""))
        if not group_id or not label or group_id in ids:
            raise ValueError("group ids and labels must be non-empty and ids unique")
        ids.add(group_id)
        rules.append(
            GroupRule(
                id=group_id,
                label=label,
                description=str(value.get("description", "")),
                modules=tuple(str(item) for item in value.get("modules", [])),
                prefixes=tuple(str(item) for item in value.get("prefixes", [])),
                patterns=tuple(str(item) for item in value.get("patterns", [])),
                parent=parent if parent is not None else (
                    str(value["parent"]) if value.get("parent") is not None else None
                ),
                order=len(rules),
            )
        )
        children = value.get("children", [])
        if not isinstance(children, list):
            raise ValueError("group children must be a list")
        for child in children:
            add_group(child, group_id)

    for value in raw_groups:
        add_group(value)

    known_ids = {rule.id for rule in rules}
    for rule in rules:
        if rule.parent is not None and rule.parent not in known_ids:
            raise ValueError(f"group {rule.id!r} has unknown parent {rule.parent!r}")
        seen = {rule.id}
        parent = rule.parent
        while parent is not None:
            if parent in seen:
                raise ValueError("group hierarchy must not contain a cycle")
            seen.add(parent)
            parent = next(item.parent for item in rules if item.id == parent)
    default_id = str(document.get("default_group", ""))
    matching = [rule for rule in rules if rule.id == default_id]
    if len(matching) != 1:
        raise ValueError("default_group must identify exactly one configured group")
    default = matching[0]
    raw_contracts = document.get("contracts", [])
    if not isinstance(raw_contracts, list):
        raise ValueError("contracts must be a list")
    contract_ids: set[str] = set()
    contracts: list[Mapping[str, Any]] = []
    for contract in raw_contracts:
        if not isinstance(contract, Mapping):
            raise ValueError("each contract must be an object")
        contract_id = str(contract.get("id", ""))
        if not contract_id or contract_id in contract_ids:
            raise ValueError("contract ids must be non-empty and unique")
        contract_ids.add(contract_id)
        contracts.append(dict(contract))
    return GroupConfiguration(
        groups=tuple(rules),
        default_group=default,
        contracts=tuple(contracts),
    )


def _group_depth(rule: GroupRule, rules: Mapping[str, GroupRule]) -> int:
    depth = 0
    parent = rule.parent
    while parent is not None:
        depth += 1
        parent = rules[parent].parent
    return depth


def _assign_group(
    source_name: str,
    configuration: GroupConfiguration,
) -> tuple[GroupRule, str]:
    by_id = {rule.id: rule for rule in configuration.groups}

    def matches(rule: GroupRule, kind: str) -> bool:
        if kind == "exact":
            return source_name in rule.modules
        if kind == "pattern":
            return any(fnmatch.fnmatchcase(source_name, pattern) for pattern in rule.patterns)
        return any(source_name.startswith(prefix) for prefix in rule.prefixes)

    def inside_ancestor_scopes(rule: GroupRule) -> bool:
        parent = rule.parent
        while parent is not None:
            ancestor = by_id[parent]
            has_selector = bool(ancestor.modules or ancestor.patterns or ancestor.prefixes)
            if has_selector and not any(matches(ancestor, kind) for kind in ("exact", "pattern", "prefix")):
                return False
            parent = ancestor.parent
        return True

    candidates = sorted(
        (rule for rule in configuration.groups if rule.id != configuration.default_group.id),
        key=lambda rule: (-_group_depth(rule, by_id), rule.order),
    )
    for kind in ("exact", "pattern", "prefix"):
        for rule in candidates:
            if inside_ancestor_scopes(rule) and matches(rule, kind):
                return rule, kind
    return configuration.default_group, "default"


def _strongly_connected_components(graph: Mapping[str, Iterable[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        low_links[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, ()):
            if target not in indices:
                visit(target)
                low_links[node] = min(low_links[node], low_links[target])
            elif target in on_stack:
                low_links[node] = min(low_links[node], indices[target])
        if low_links[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            target = stack.pop()
            on_stack.remove(target)
            component.append(target)
            if target == node:
                break
        components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return components


def _import_bindings(
    tree: ast.Module,
    *,
    current_module: str,
    current_is_package: bool,
    known_modules: set[str],
) -> dict[str, tuple[str, str | None]]:
    bindings: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _longest_known_module(alias.name, known_modules)
                if target is not None:
                    local = alias.asname or alias.name.split(".", 1)[0]
                    bindings[local] = (target, None)
        elif isinstance(node, ast.ImportFrom):
            base = _relative_base(
                current_module,
                current_is_package=current_is_package,
                level=node.level,
                imported_module=node.module,
            )
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = f"{base}.{alias.name}" if base else alias.name
                child = _longest_known_module(candidate, known_modules)
                local = alias.asname or alias.name
                if child == candidate:
                    bindings[local] = (child, None)
                else:
                    target = _longest_known_module(base, known_modules)
                    if target is not None:
                        bindings[local] = (target, alias.name)
    return bindings


def _resolve_bound_reference(
    node: ast.AST,
    bindings: Mapping[str, tuple[str, str | None]],
) -> tuple[str, str | None] | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if not isinstance(node, ast.Attribute):
        return None
    parts: list[str] = []
    value: ast.AST = node
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if not isinstance(value, ast.Name) or value.id not in bindings:
        return None
    module, symbol = bindings[value.id]
    suffix = list(reversed(parts))
    if symbol:
        suffix.insert(0, symbol)
    return module, ".".join(suffix) if suffix else None


class _RelationCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        current_module: str,
        bindings: Mapping[str, tuple[str, str | None]],
        symbol_kinds: Mapping[tuple[str, str], str],
        local_symbols: Mapping[str, str],
    ) -> None:
        self.current_module = current_module
        self.bindings = bindings
        self.symbol_kinds = symbol_kinds
        self.local_symbols = local_symbols
        self.scope: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.types: list[dict[str, Any]] = []

    def _scope_name(self) -> str:
        return ".".join(self.scope) if self.scope else "<module>"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            resolved = _resolve_bound_reference(base, self.bindings)
            if resolved is None and isinstance(base, ast.Name) and base.id in self.local_symbols:
                resolved = (self.current_module, base.id)
            if resolved is not None:
                self.types.append(
                    {
                        "source_symbol": node.name,
                        "target_module": resolved[0],
                        "target_symbol": resolved[1],
                        "kind": "inherits",
                        "line": int(getattr(base, "lineno", node.lineno)),
                        "confidence": "static_name_resolution",
                    }
                )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        resolved = _resolve_bound_reference(node.func, self.bindings)
        if resolved is None and isinstance(node.func, ast.Name) and node.func.id in self.local_symbols:
            resolved = (self.current_module, node.func.id)
        if resolved is not None:
            target_module, target_symbol = resolved
            top_symbol = (target_symbol or "").split(".", 1)[0]
            target_kind = self.symbol_kinds.get((target_module, top_symbol), "unknown")
            self.calls.append(
                {
                    "source_definition": self._scope_name(),
                    "target_module": target_module,
                    "target_symbol": target_symbol,
                    "kind": "constructs" if target_kind == "class" else "calls",
                    "line": int(getattr(node, "lineno", 1)),
                    "confidence": "static_name_resolution",
                }
            )
        self.generic_visit(node)


def _attach_static_relations(
    architecture: dict[str, Any],
    trees: Mapping[str, ast.Module],
) -> None:
    modules = architecture["modules"]
    known_modules = set(modules)
    symbol_kinds: dict[tuple[str, str], str] = {}
    for module_name, module in modules.items():
        for definition in [*module["public_interface"], *module["implementation"]]:
            symbol_kinds[(module_name, definition["name"])] = definition["kind"]
    for module_name, tree in trees.items():
        module = modules[module_name]
        bindings = _import_bindings(
            tree,
            current_module=module_name,
            current_is_package=Path(module["path"]).name == "__init__.py",
            known_modules=known_modules,
        )
        local_symbols = {
            definition["name"]: definition["kind"]
            for definition in [*module["public_interface"], *module["implementation"]]
        }
        collector = _RelationCollector(
            current_module=module_name,
            bindings=bindings,
            symbol_kinds=symbol_kinds,
            local_symbols=local_symbols,
        )
        collector.visit(tree)
        module["calls"] = sorted(
            {json.dumps(item, sort_keys=True): item for item in collector.calls}.values(),
            key=lambda item: (item["line"], item["target_module"], item.get("target_symbol") or ""),
        )
        module["types"] = sorted(
            {json.dumps(item, sort_keys=True): item for item in collector.types}.values(),
            key=lambda item: (item["line"], item["target_module"], item.get("target_symbol") or ""),
        )
    architecture["stats"]["static_call_relation_count"] = sum(
        len(module["calls"]) for module in modules.values()
    )
    architecture["stats"]["static_type_relation_count"] = sum(
        len(module["types"]) for module in modules.values()
    )


def _attach_test_relations(
    architecture: dict[str, Any],
    *,
    test_root: Path,
    repository_root: Path,
) -> None:
    test_root = test_root.resolve()
    try:
        test_root.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("test root must be inside repository root") from error
    if not test_root.is_dir():
        architecture["tests"] = {"root": None, "files": [], "parse_errors": []}
        architecture["stats"]["test_dependency_count"] = 0
        return
    modules = architecture["modules"]
    known_modules = set(modules)
    files: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    relation_count = 0
    for path in sorted(test_root.rglob("*.py")):
        try:
            path.resolve().relative_to(test_root)
            path.resolve().relative_to(repository_root)
        except ValueError as error:
            raise ValueError(f"test file resolves outside test root: {path}") from error
        relative = path.relative_to(repository_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative, type_comments=True)
        except (SyntaxError, UnicodeDecodeError) as error:
            parse_errors.append({"path": relative, "error": str(error)})
            continue
        targets: dict[str, set[int]] = defaultdict(set)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _longest_known_module(alias.name, known_modules)
                    if target is not None:
                        targets[target].add(int(node.lineno))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                for alias in node.names:
                    candidate = f"{base}.{alias.name}" if base else alias.name
                    target = _longest_known_module(candidate, known_modules)
                    if target is None:
                        target = _longest_known_module(base, known_modules)
                    if target is not None:
                        targets[target].add(int(node.lineno))
        if not targets:
            continue
        test_functions = sorted(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test")
        )
        files.append(
            {
                "path": relative,
                "test_functions": test_functions,
                "targets": [
                    {"module": target, "lines": sorted(lines)}
                    for target, lines in sorted(targets.items())
                ],
            }
        )
        for target, lines in targets.items():
            modules[target]["tested_by"].append(
                {
                    "path": relative,
                    "lines": sorted(lines),
                    "test_function_count": len(test_functions),
                }
            )
            relation_count += 1
    architecture["tests"] = {
        "root": test_root.relative_to(repository_root).as_posix(),
        "files": files,
        "parse_errors": parse_errors,
    }
    architecture["stats"]["test_dependency_count"] = relation_count
    architecture["stats"]["test_parse_error_count"] = len(parse_errors)


def analyse_source_tree(
    source_root: Path,
    *,
    repository_root: Path,
    groups_path: Path | None = None,
    test_root: Path | None = None,
) -> dict[str, Any]:
    """Return a path-safe architecture document for one Python package tree."""

    source_root = source_root.resolve()
    repository_root = repository_root.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"source root does not exist: {source_root}")
    try:
        relative_source_root = source_root.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("source root must be inside repository root") from error
    package_name = source_root.name
    paths = sorted(source_root.rglob("*.py"))
    known_by_path = {
        path: _module_name(path, source_root, package_name)
        for path in paths
        if "__pycache__" not in path.parts
    }
    identities = list(known_by_path.values())
    if len(identities) != len(set(identities)):
        duplicates = sorted({name for name in identities if identities.count(name) > 1})
        raise ValueError(f"duplicate Python module identities: {', '.join(duplicates)}")
    for path in known_by_path:
        try:
            path.resolve().relative_to(source_root)
        except ValueError as error:
            raise ValueError(f"source file resolves outside source root: {path}") from error
    known_modules = set(known_by_path.values())
    configuration = load_group_configuration(groups_path)
    modules: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    trees: dict[str, ast.Module] = {}

    for path, module_name in sorted(known_by_path.items(), key=lambda item: item[1]):
        source_bytes = path.read_bytes()
        source = source_bytes.decode("utf-8")
        relative_path = path.relative_to(repository_root).as_posix()
        source_name = _source_name(module_name, package_name)
        group, assignment_source = _assign_group(source_name, configuration)
        try:
            tree = ast.parse(source, filename=relative_path, type_comments=True)
        except SyntaxError as error:
            errors.append(
                {
                    "module": module_name,
                    "path": relative_path,
                    "error": f"{error.msg} at line {error.lineno}",
                }
            )
            modules[module_name] = {
                "name": module_name,
                "short_name": source_name,
                "path": relative_path,
                "group": group.id,
                "group_assignment": assignment_source,
                "summary": "",
                "source_sha256": _sha256_bytes(source_bytes),
                "line_count": len(source.splitlines()),
                "interface_source": "parse_error",
                "public_interface": [],
                "implementation": [],
                "imports": [],
                "external_imports": [],
                "external_import_details": [],
                "imported_by": [],
                "effects": [],
                "calls": [],
                "types": [],
                "tested_by": [],
                "parse_error": errors[-1]["error"],
            }
            continue
        trees[module_name] = tree
        declared_all = _declared_all(tree)
        has_declared_all = _has_declared_all(tree)
        interface, implementation = _definitions(tree, declared_all)
        internal_imports, external_imports, external_import_details = _imports(
            tree,
            current_module=module_name,
            current_is_package=path.name == "__init__.py",
            package_name=package_name,
            known_modules=known_modules,
        )
        document = ast.get_docstring(tree, clean=True) or ""
        modules[module_name] = {
            "name": module_name,
            "short_name": source_name,
            "path": relative_path,
            "group": group.id,
            "group_assignment": assignment_source,
            "summary": document.splitlines()[0] if document else "",
            "source_sha256": _sha256_bytes(source_bytes),
            "line_count": len(source.splitlines()),
            "interface_source": (
                "__all__"
                if declared_all is not None
                else "dynamic___all___with_public_name_fallback"
                if has_declared_all
                else "public_name_convention"
            ),
            "declared_all": list(declared_all) if declared_all is not None else None,
            "public_interface": interface,
            "implementation": implementation,
            "imports": internal_imports,
            "external_imports": external_imports,
            "external_import_details": external_import_details,
            "imported_by": [],
            "effects": _effects(tree),
            "calls": [],
            "types": [],
            "tested_by": [],
            "parse_error": None,
        }

    for module_name, module in modules.items():
        for dependency in module["imports"]:
            target = dependency["module"]
            if target in modules:
                modules[target]["imported_by"].append(module_name)
        page_digest = hashlib.sha256(module_name.encode("utf-8")).hexdigest()[:12]
        module["code_page"] = (
            "code/" + module_name.replace(".", "--") + f"-{page_digest}.html"
        )
    for module in modules.values():
        module["imported_by"].sort()

    graph = {
        name: [item["module"] for item in module["imports"]]
        for name, module in modules.items()
    }
    cyclic_components = [
        component
        for component in _strongly_connected_components(graph)
        if len(component) > 1
        or (len(component) == 1 and component[0] in graph.get(component[0], ()))
    ]
    cycle_by_module = {
        module: index + 1
        for index, component in enumerate(cyclic_components)
        for module in component
    }
    for name, module in modules.items():
        module["cycle"] = cycle_by_module.get(name)

    all_rules = list(configuration.groups)
    groups: list[dict[str, Any]] = []
    group_edges: dict[tuple[str, str], int] = defaultdict(int)
    for source, module in modules.items():
        for dependency in module["imports"]:
            target = dependency["module"]
            if target not in modules:
                continue
            source_group = module["group"]
            target_group = modules[target]["group"]
            if source_group != target_group:
                group_edges[(source_group, target_group)] += 1
    by_rule_id = {rule.id: rule for rule in all_rules}

    def descendant_ids(group_id: str) -> set[str]:
        result = {group_id}
        changed = True
        while changed:
            changed = False
            for candidate in all_rules:
                if candidate.parent in result and candidate.id not in result:
                    result.add(candidate.id)
                    changed = True
        return result

    for rule in all_rules:
        descendants = descendant_ids(rule.id)
        direct_members = sorted(
            name for name, module in modules.items() if module["group"] == rule.id
        )
        members = sorted(
            name for name, module in modules.items() if module["group"] in descendants
        )
        children = [candidate.id for candidate in all_rules if candidate.parent == rule.id]
        path: list[str] = [rule.id]
        parent = rule.parent
        while parent is not None:
            path.append(parent)
            parent = by_rule_id[parent].parent
        path.reverse()
        groups.append(
            {
                "id": rule.id,
                "label": rule.label,
                "description": rule.description,
                "parent": rule.parent,
                "children": children,
                "path": path,
                "depth": len(path) - 1,
                "direct_modules": direct_members,
                "modules": members,
                "module_count": len(members),
                "line_count": sum(modules[name]["line_count"] for name in members),
                "public_definition_count": sum(
                    len(modules[name]["public_interface"]) for name in members
                ),
            }
        )

    group_paths = {group["id"]: list(group["path"]) for group in groups}
    for module in modules.values():
        module["group_path"] = group_paths.get(module["group"], [module["group"]])

    repository_hash = hashlib.sha256()
    for name in sorted(modules):
        repository_hash.update(name.encode("utf-8"))
        repository_hash.update(modules[name]["source_sha256"].encode("ascii"))
    document: dict[str, Any] = {
        "schema": ARCHITECTURE_SCHEMA,
        "package": package_name,
        "source_root": relative_source_root.as_posix(),
        "source_tree_sha256": repository_hash.hexdigest(),
        "group_configuration_sha256": (
            _sha256_bytes(groups_path.read_bytes()) if groups_path is not None else None
        ),
        "contracts_sha256": _sha256_bytes(
            json.dumps(
                list(configuration.contracts),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ),
        "stats": {
            "module_count": len(modules),
            "line_count": sum(module["line_count"] for module in modules.values()),
            "internal_dependency_count": sum(len(module["imports"]) for module in modules.values()),
            "internal_import_occurrence_count": sum(
                len(dependency.get("occurrences", []))
                for module in modules.values()
                for dependency in module["imports"]
            ),
            "external_package_count": len(
                {value for module in modules.values() for value in module["external_imports"]}
            ),
            "cycle_count": len(cyclic_components),
            "parse_error_count": len(errors),
            "effect_candidate_count": sum(len(module["effects"]) for module in modules.values()),
        },
        "groups": groups,
        "top_level_groups": [group["id"] for group in groups if group["parent"] is None],
        "group_edges": [
            {"source": source, "target": target, "count": count}
            for (source, target), count in sorted(group_edges.items())
        ],
        "cycles": cyclic_components,
        "parse_errors": errors,
        "modules": modules,
    }
    _attach_static_relations(document, trees)
    if test_root is not None:
        _attach_test_relations(
            document,
            test_root=test_root,
            repository_root=repository_root,
        )
    from .contracts import evaluate_contracts

    evaluate_contracts(document, configuration.contracts)
    document["architecture_sha256"] = calculate_architecture_sha256(document)
    return document
