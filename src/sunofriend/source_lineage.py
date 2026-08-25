"""Immutable source-graph overlays for prepared source projects.

``INPUT/source-project.json`` remains the stable, minimal import receipt.  This
module adds a separate append-only graph that can describe later refinements
without changing that v1 document or its content-derived ``project_id``.

The graph store is deliberately lazy.  A project without ``SOURCE-GRAPH`` is
represented by a deterministic in-memory revision whose active nodes are the
original project sources.  Reading that state creates no file or directory.
Explicit writes use content-addressed objects plus a small compare-and-swap
``current.json`` pointer.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

try:
    import fcntl as _fcntl
except ImportError:  # Windows
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:  # POSIX
    _msvcrt = None

from .audio_formats import file_sha256
from .derived_source_receipt import (
    DERIVED_SOURCE_RECEIPT_SCHEMA,
    validate_derived_source_receipt_document,
)
from .source_project import (
    SOURCE_PROJECT_RELATIVE_PATH,
    load_source_project,
    validate_source_project_document,
)
from .source_receipt import (
    SOURCE_IMPORT_SCHEMA,
    canonical_json_bytes,
    document_sha256,
    validate_source_receipt_document,
)
from .source_roles import (
    flat_v1_repeatable_source_role_ids,
    prepared_source_role_ids,
)


SOURCE_GRAPH_SCHEMA = "sunofriend.source-graph.v1"
SOURCE_GRAPH_POINTER_SCHEMA = "sunofriend.source-graph-current.v1"
SOURCE_GRAPH_RELATIVE_DIRECTORY = PurePosixPath("SOURCE-GRAPH")
SOURCE_GRAPH_OBJECTS_RELATIVE_DIRECTORY = PurePosixPath(
    "SOURCE-GRAPH/objects"
)
SOURCE_GRAPH_CURRENT_RELATIVE_PATH = PurePosixPath(
    "SOURCE-GRAPH/current.json"
)

_MAXIMUM_GRAPH_BYTES = 16 * 1024 * 1024
_MAXIMUM_NODES = 4096
_MAXIMUM_REFINEMENT_GROUPS = 4096
_MAXIMUM_REVISIONS = 4096
_MAXIMUM_EVIDENCE_RECEIPT_BYTES = 4 * 1024 * 1024
_GRAPH_FIELDS = frozenset(
    {
        "schema",
        "graph_id",
        "project_id",
        "revision",
        "previous_graph_id",
        "nodes",
        "refinement_groups",
        "active_node_ids",
        "activation",
    }
)
_NODE_FIELDS = frozenset(
    {
        "node_id",
        "parent_node_id",
        "role",
        "declared_role",
        "shape",
        "origin",
        "asset",
        "derivation",
    }
)
_ASSET_FIELDS = frozenset(
    {"asset_id", "canonical_path", "receipt_path"}
)
_GROUP_FIELDS = frozenset(
    {
        "group_id",
        "parent_node_id",
        "child_node_ids",
        "evidence_id",
        "coverage",
        "residual_node_id",
    }
)
_ACTIVATION_FIELDS = frozenset(
    {"mode", "group_id", "reviewed", "selected_node_ids"}
)
_POINTER_FIELDS = frozenset(
    {"schema", "project_id", "graph_id", "revision"}
)
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_NODE_ID_RE = re.compile(r"^node:[0-9a-f]{64}$")
_GROUP_ID_RE = re.compile(r"^group:[0-9a-f]{64}$")
# The source-role registry describes roles which *may* be composite.  The flat
# source-project.v1 receipt, however, proves composite shape only for its
# established broad drums role.  Vocals and ``other`` remain leaves until a
# later graph node explicitly records otherwise.
_ROOT_COMPOSITE_ROLES = frozenset({"drums"})
_REPEATABLE_ACTIVE_ROLES = flat_v1_repeatable_source_role_ids()
_PREPARED_ACTIVE_ROLES = prepared_source_role_ids()
_COVERAGE_VALUES = frozenset({"complete", "partial", "unknown"})
_ORIGIN_VALUES = frozenset({"original", "derived", "view"})
_SHAPE_VALUES = frozenset({"leaf", "composite"})
_ACTIVATION_MODES = frozenset(
    {
        "project_sources",
        "unchanged",
        "automatic_complete",
        "reviewed",
    }
)
_PREVIOUS_UNSET = object()


class SourceGraphError(RuntimeError):
    """Base class for source-graph evidence failures."""


class SourceGraphConflictError(SourceGraphError):
    """The expected graph pointer no longer identifies current state."""


@dataclass(frozen=True)
class SourceGraphAsset:
    """One immutable audio/reference identity used by a graph node."""

    asset_id: str
    canonical_path: str
    receipt_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "canonical_path": self.canonical_path,
            "receipt_path": self.receipt_path,
        }


@dataclass(frozen=True)
class SourceGraphNode:
    """One append-only musical source or source view."""

    node_id: str
    parent_node_id: str | None
    role: str
    declared_role: str | None
    shape: str
    origin: str
    asset: SourceGraphAsset
    derivation: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "role": self.role,
            "declared_role": self.declared_role,
            "shape": self.shape,
            "origin": self.origin,
            "asset": self.asset.to_dict(),
            "derivation": (
                _json_copy(self.derivation)
                if self.derivation is not None
                else None
            ),
        }


@dataclass(frozen=True)
class SourceRefinementGroup:
    """Children produced together as one bounded refinement alternative."""

    group_id: str
    parent_node_id: str
    child_node_ids: tuple[str, ...]
    evidence_id: str
    coverage: str
    residual_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "parent_node_id": self.parent_node_id,
            "child_node_ids": list(self.child_node_ids),
            "evidence_id": self.evidence_id,
            "coverage": self.coverage,
            "residual_node_id": self.residual_node_id,
        }


@dataclass(frozen=True)
class SourceGraphRevision:
    """One immutable source-graph revision."""

    graph_id: str
    project_id: str
    revision: int
    previous_graph_id: str | None
    nodes: tuple[SourceGraphNode, ...]
    refinement_groups: tuple[SourceRefinementGroup, ...]
    active_node_ids: tuple[str, ...]
    activation: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SOURCE_GRAPH_SCHEMA,
            "graph_id": self.graph_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "previous_graph_id": self.previous_graph_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "refinement_groups": [
                group.to_dict() for group in self.refinement_groups
            ],
            "active_node_ids": list(self.active_node_ids),
            "activation": _json_copy(self.activation),
        }


@dataclass(frozen=True)
class SourceGraphWriteResult:
    """Effects of one source-graph compare-and-swap write."""

    graph: SourceGraphRevision
    object_path: Path | None
    pointer_path: Path | None
    replayed: bool
    object_created: bool
    pointer_changed: bool


def build_source_graph_node(
    *,
    parent_node_id: str,
    role: str,
    declared_role: str | None,
    shape: str,
    origin: str,
    asset: SourceGraphAsset | Mapping[str, Any],
    derivation: Mapping[str, Any],
) -> SourceGraphNode:
    """Build one canonically identified derived source-graph node.

    Original nodes remain owned by ``source-project.v1`` synthesis so their
    long-standing identities cannot be reinterpreted by callers.
    """

    if origin not in {"derived", "view"}:
        raise ValueError(
            "source-graph node constructor accepts only derived or view origins"
        )
    asset_value = _coerce_asset(asset)
    derivation_value = _json_copy(derivation)
    provisional = SourceGraphNode(
        node_id=f"node:{'0' * 64}",
        parent_node_id=parent_node_id,
        role=role,
        declared_role=declared_role,
        shape=shape,
        origin=origin,
        asset=asset_value,
        derivation=derivation_value,
    )
    node = SourceGraphNode(
        node_id=_canonical_nonoriginal_node_id(provisional),
        parent_node_id=provisional.parent_node_id,
        role=provisional.role,
        declared_role=provisional.declared_role,
        shape=provisional.shape,
        origin=provisional.origin,
        asset=provisional.asset,
        derivation=provisional.derivation,
    )
    _validate_node(node)
    return node


def build_source_refinement_group(
    *,
    parent_node_id: str,
    child_node_ids: Sequence[str],
    evidence_id: str,
    coverage: str,
    residual_node_id: str | None = None,
) -> SourceRefinementGroup:
    """Build one canonically ordered and content-identified refinement group."""

    parent = _node_id(parent_node_id, "refinement parent_node_id")
    children = tuple(
        sorted(
            _node_id(value, "refinement child_node_id")
            for value in child_node_ids
        )
    )
    if not children:
        raise ValueError("refinement group must contain child nodes")
    if len(children) != len(set(children)):
        raise ValueError("refinement child node IDs must be unique")
    evidence = _sha256_id(evidence_id, "refinement evidence_id")
    if coverage not in _COVERAGE_VALUES:
        raise ValueError("refinement coverage is invalid")
    residual = (
        None
        if residual_node_id is None
        else _node_id(residual_node_id, "refinement residual_node_id")
    )
    if residual is not None and residual not in children:
        raise ValueError(
            "refinement residual node must be one of the group children"
        )
    provisional = SourceRefinementGroup(
        group_id=f"group:{'0' * 64}",
        parent_node_id=parent,
        child_node_ids=children,
        evidence_id=evidence,
        coverage=coverage,
        residual_node_id=residual,
    )
    return SourceRefinementGroup(
        group_id=_canonical_refinement_group_id(provisional),
        parent_node_id=provisional.parent_node_id,
        child_node_ids=provisional.child_node_ids,
        evidence_id=provisional.evidence_id,
        coverage=provisional.coverage,
        residual_node_id=provisional.residual_node_id,
    )


def synthesize_source_graph(
    source_project: Mapping[str, Any] | str | Path,
) -> SourceGraphRevision:
    """Return the deterministic flat revision implied by source-project v1.

    This is a pure operation.  Passing a project root or manifest path reads
    the existing manifest but never creates ``SOURCE-GRAPH``.
    """

    document = _source_project_document(source_project)
    graph = _synthesize_source_graph_unvalidated(document)
    validate_source_graph_revision(graph, previous=None)
    return graph


def _synthesize_source_graph_unvalidated(
    document: Mapping[str, Any],
) -> SourceGraphRevision:
    project_id = str(document["project_id"])
    nodes: list[SourceGraphNode] = []
    for index, source_value in enumerate(document["sources"]):
        if not isinstance(source_value, Mapping):  # guarded by v1 validation
            raise ValueError("source-project source must be an object")
        source = dict(source_value)
        node_seed = {
            "schema": "sunofriend.source-graph-node-seed.v1",
            "project_id": project_id,
            "source_index": index,
            "source_id": source["source_id"],
            "canonical_path": source["canonical_path"],
            "receipt_path": source["receipt_path"],
        }
        node_id = f"node:{document_sha256(node_seed)}"
        role = _nonempty_text(source.get("role"), "source role")
        nodes.append(
            SourceGraphNode(
                node_id=node_id,
                parent_node_id=None,
                role=role,
                declared_role=role,
                shape=(
                    "composite"
                    if role in _ROOT_COMPOSITE_ROLES
                    else "leaf"
                ),
                origin="original",
                asset=SourceGraphAsset(
                    asset_id=_sha256_id(
                        source.get("source_id"),
                        "source asset_id",
                    ),
                    canonical_path=str(
                        _safe_relative_path(
                            source.get("canonical_path"),
                            "source canonical_path",
                        )
                    ),
                    receipt_path=str(
                        _safe_relative_path(
                            source.get("receipt_path"),
                            "source receipt_path",
                        )
                    ),
                ),
                derivation=None,
            )
        )
    seed = {
        "schema": SOURCE_GRAPH_SCHEMA,
        "project_id": project_id,
        "revision": 1,
        "previous_graph_id": None,
        "nodes": [node.to_dict() for node in nodes],
        "refinement_groups": [],
        "active_node_ids": [node.node_id for node in nodes],
        "activation": {
            "mode": "project_sources",
            "group_id": None,
            "reviewed": False,
            "selected_node_ids": [node.node_id for node in nodes],
        },
    }
    return _graph_from_seed(seed)


def load_source_graph(project_root: str | Path) -> SourceGraphRevision:
    """Load and verify current graph state, synthesizing v1 when absent.

    Every referenced revision is verified back to the deterministic v1 root.
    Absence of ``SOURCE-GRAPH/current.json`` is not an error and performs no
    write.
    """

    root, project = _load_project_root(project_root)
    synthesized = synthesize_source_graph(project)
    pointer_path = _project_path(
        root,
        SOURCE_GRAPH_CURRENT_RELATIVE_PATH,
        label="source-graph current pointer",
        require_exists=False,
    )
    if not pointer_path.exists():
        if pointer_path.is_symlink():
            raise SourceGraphError(
                "source-graph current pointer must not be a symbolic link"
            )
        _validate_optional_graph_store(root)
        return synthesized

    pointer = _load_current_pointer(pointer_path)
    if pointer["project_id"] != project["project_id"]:
        raise SourceGraphError(
            "source-graph current pointer is pinned to another project"
        )
    current = _load_graph_object(root, pointer["graph_id"])
    if current.revision != pointer["revision"]:
        raise SourceGraphError(
            "source-graph current pointer revision does not match its object"
        )
    _validate_revision_chain(
        root,
        current=current,
        synthesized=synthesized,
        source_project=project,
    )
    return current


def resolve_active_sources(
    graph: SourceGraphRevision | Mapping[str, Any],
    *,
    project_root: str | Path | None = None,
) -> tuple[SourceGraphNode, ...]:
    """Return the active frontier in its declared stable order.

    When ``project_root`` is supplied, every active canonical and receipt path
    is also confined to that pinned project and checked as a regular,
    non-symlink file.  The function never writes or changes activation.
    """

    revision = _coerce_graph(graph)
    validate_source_graph_revision(revision)
    if project_root is not None:
        root, project = _load_project_root(project_root)
        if revision.project_id != project["project_id"]:
            raise SourceGraphError(
                "source graph is pinned to another source project"
            )
        _validate_active_source_evidence(root, revision)
    by_id = {node.node_id: node for node in revision.nodes}
    return tuple(by_id[node_id] for node_id in revision.active_node_ids)


def build_source_graph_revision(
    previous: SourceGraphRevision | Mapping[str, Any],
    *,
    append_nodes: Sequence[SourceGraphNode | Mapping[str, Any]] = (),
    append_refinement_groups: Sequence[
        SourceRefinementGroup | Mapping[str, Any]
    ] = (),
    active_node_ids: Sequence[str] | None = None,
    activation: Mapping[str, Any] | None = None,
) -> SourceGraphRevision:
    """Build one append-only revision without touching the filesystem.

    ``automatic_complete`` may replace one active parent with all children
    only when that group's coverage is ``complete``.  ``partial`` and
    ``unknown`` groups can change the frontier only through ``reviewed`` with
    ``reviewed=true`` and an explicit selected subset.
    """

    prior = _coerce_graph(previous)
    validate_source_graph_revision(prior)
    new_nodes = tuple(
        sorted(
            (_coerce_node(value) for value in append_nodes),
            key=lambda node: node.node_id,
        )
    )
    new_groups = tuple(
        sorted(
            (
                _canonical_group(_coerce_group(value))
                for value in append_refinement_groups
            ),
            key=lambda group: group.group_id,
        )
    )
    old_node_ids = {node.node_id for node in prior.nodes}
    old_group_ids = {group.group_id for group in prior.refinement_groups}
    if any(node.node_id in old_node_ids for node in new_nodes):
        raise ValueError("source-graph nodes are append-only")
    if any(group.group_id in old_group_ids for group in new_groups):
        raise ValueError("source-graph refinement groups are append-only")
    if len({node.node_id for node in new_nodes}) != len(new_nodes):
        raise ValueError("appended source-graph node IDs must be unique")
    if len({group.group_id for group in new_groups}) != len(new_groups):
        raise ValueError("appended refinement group IDs must be unique")

    supplied_active = (
        prior.active_node_ids
        if active_node_ids is None
        else tuple(
            _node_id(value, "active_node_ids item")
            for value in active_node_ids
        )
    )
    if len(supplied_active) != len(set(supplied_active)):
        raise ValueError("active source-graph node IDs must be unique")
    activation_value: Mapping[str, Any]
    if activation is None:
        if set(supplied_active) != set(prior.active_node_ids):
            raise ValueError(
                "a changed active frontier requires explicit activation"
            )
        requested_active = prior.active_node_ids
        activation_value = {
            "mode": "unchanged",
            "group_id": None,
            "reviewed": False,
            "selected_node_ids": [],
        }
    else:
        activation_value = _activation_dict(activation)
        activation_value["selected_node_ids"] = sorted(
            activation_value["selected_node_ids"]
        )
        if activation_value["mode"] == "unchanged":
            requested_active = prior.active_node_ids
        else:
            groups_by_id = {
                group.group_id: group
                for group in (*prior.refinement_groups, *new_groups)
            }
            group_id = activation_value["group_id"]
            group = groups_by_id.get(str(group_id))
            if group is None:
                raise ValueError(
                    "activation refinement group does not exist"
                )
            requested_active = _ordered_frontier_after_activation(
                prior.active_node_ids,
                group=group,
                mode=str(activation_value["mode"]),
                selected_node_ids=activation_value["selected_node_ids"],
            )
        if set(supplied_active) != set(requested_active):
            raise ValueError(
                "active frontier does not match the refinement decision"
            )

    if (
        not new_nodes
        and not new_groups
        and set(requested_active) == set(prior.active_node_ids)
    ):
        raise ValueError("source-graph revision would have no effect")

    seed = {
        "schema": SOURCE_GRAPH_SCHEMA,
        "project_id": prior.project_id,
        "revision": prior.revision + 1,
        "previous_graph_id": prior.graph_id,
        "nodes": [
            node.to_dict() for node in (*prior.nodes, *new_nodes)
        ],
        "refinement_groups": [
            group.to_dict()
            for group in (*prior.refinement_groups, *new_groups)
        ],
        "active_node_ids": list(requested_active),
        "activation": _json_copy(activation_value),
    }
    graph = _graph_from_seed(seed)
    validate_source_graph_revision(graph, previous=prior)
    return graph


def write_source_graph_revision(
    project_root: str | Path,
    graph: SourceGraphRevision | Mapping[str, Any],
    *,
    expected_current_graph_id: str,
) -> SourceGraphWriteResult:
    """Publish one graph object and advance ``current.json`` with CAS.

    Retrying the exact same graph with its original expected predecessor is an
    idempotent replay.  A different current graph raises
    :class:`SourceGraphConflictError`.
    """

    target = _coerce_graph(graph)
    expected = _sha256_id(
        expected_current_graph_id,
        "expected_current_graph_id",
    )
    root, project = _load_project_root(project_root)
    if target.project_id != project["project_id"]:
        raise SourceGraphError(
            "source graph is pinned to another source project"
        )
    synthesized = synthesize_source_graph(project)
    validate_source_graph_revision(target, source_project=project)

    graph_root = _prepare_graph_store(root)
    with _exclusive_graph_lock(graph_root):
        current = load_source_graph(root)
        object_path = _object_path(graph_root, target.graph_id)
        pointer_path = graph_root / "current.json"

        if current.graph_id == target.graph_id:
            if expected not in {
                target.graph_id,
                target.previous_graph_id,
            }:
                raise SourceGraphConflictError(
                    "source-graph current pointer changed"
                )
            _validate_active_source_evidence(root, target)
            if pointer_path.exists():
                _verify_existing_object(object_path, target)
                _verify_pointer_matches(pointer_path, target)
                return SourceGraphWriteResult(
                    graph=target,
                    object_path=object_path,
                    pointer_path=pointer_path,
                    replayed=True,
                    object_created=False,
                    pointer_changed=False,
                )
            # The deterministic synthesized root is intentionally virtual.
            if target.graph_id != synthesized.graph_id:
                raise SourceGraphError(
                    "source-graph object is current without a pointer"
                )
            return SourceGraphWriteResult(
                graph=target,
                object_path=None,
                pointer_path=None,
                replayed=True,
                object_created=False,
                pointer_changed=False,
            )

        if current.graph_id != expected:
            raise SourceGraphConflictError(
                "source-graph current pointer changed"
            )
        validate_source_graph_revision(
            target,
            source_project=project,
            previous=current,
        )
        if target.previous_graph_id != current.graph_id:
            raise SourceGraphConflictError(
                "source-graph revision does not extend current state"
            )

        _validate_active_source_evidence(root, target)
        object_created = _write_graph_object(object_path, target)
        pointer = {
            "schema": SOURCE_GRAPH_POINTER_SCHEMA,
            "project_id": target.project_id,
            "graph_id": target.graph_id,
            "revision": target.revision,
        }
        _write_current_pointer(pointer_path, pointer)
        return SourceGraphWriteResult(
            graph=target,
            object_path=object_path,
            pointer_path=pointer_path,
            replayed=False,
            object_created=object_created,
            pointer_changed=True,
        )


def validate_source_graph_revision(
    graph: SourceGraphRevision | Mapping[str, Any],
    *,
    source_project: Mapping[str, Any] | None = None,
    previous: SourceGraphRevision | Mapping[str, Any] | None | object = (
        _PREVIOUS_UNSET
    ),
) -> None:
    """Validate one graph and, optionally, its project and predecessor pins."""

    revision = _coerce_graph_unvalidated(graph)
    document = revision.to_dict()
    if set(document) != _GRAPH_FIELDS:
        raise ValueError("source-graph document fields are invalid")
    if len(canonical_json_bytes(document)) > _MAXIMUM_GRAPH_BYTES:
        raise ValueError("source-graph document exceeds its byte limit")
    _sha256_id(revision.project_id, "source-graph project_id")
    if (
        isinstance(revision.revision, bool)
        or not isinstance(revision.revision, int)
        or revision.revision < 1
        or revision.revision > _MAXIMUM_REVISIONS
    ):
        raise ValueError("source-graph revision is invalid")
    if revision.previous_graph_id is not None:
        _sha256_id(
            revision.previous_graph_id,
            "source-graph previous_graph_id",
        )
    graph_seed = {
        key: value
        for key, value in document.items()
        if key != "graph_id"
    }
    if revision.graph_id != f"sha256:{document_sha256(graph_seed)}":
        raise ValueError("source-graph graph_id does not match its content")

    if not revision.nodes or len(revision.nodes) > _MAXIMUM_NODES:
        raise ValueError("source graph has an invalid node count")
    if len(revision.refinement_groups) > _MAXIMUM_REFINEMENT_GROUPS:
        raise ValueError("source graph has too many refinement groups")
    node_ids: list[str] = []
    for index, node in enumerate(revision.nodes):
        _validate_node(node)
        if node.origin == "original":
            expected_node_id = _canonical_original_node_id(
                project_id=revision.project_id,
                source_index=index,
                node=node,
            )
            if node.node_id != expected_node_id:
                raise ValueError(
                    "original source-graph node_id does not match "
                    "source-project identity"
                )
        node_ids.append(node.node_id)
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("source-graph node IDs must be unique")
    by_node = {node.node_id: node for node in revision.nodes}
    _validate_parent_graph(by_node)

    group_ids: list[str] = []
    grouped_children: set[str] = set()
    for group in revision.refinement_groups:
        _validate_group(group, by_node)
        if group.child_node_ids != tuple(sorted(group.child_node_ids)):
            raise ValueError(
                "refinement child node IDs must be in canonical order"
            )
        group_ids.append(group.group_id)
        overlap = grouped_children.intersection(group.child_node_ids)
        if overlap:
            raise ValueError(
                "one child node cannot belong to several refinement groups"
            )
        grouped_children.update(group.child_node_ids)
    if len(group_ids) != len(set(group_ids)):
        raise ValueError("refinement group IDs must be unique")

    if not revision.active_node_ids:
        raise ValueError("source graph must have an active frontier")
    for node_id in revision.active_node_ids:
        _node_id(node_id, "active_node_ids item")
        if node_id not in by_node:
            raise ValueError("active source-graph node does not exist")
    if len(revision.active_node_ids) != len(set(revision.active_node_ids)):
        raise ValueError("active source-graph node IDs must be unique")
    _validate_active_antichain(revision.active_node_ids, by_node)
    _validate_active_role_uniqueness(revision.active_node_ids, by_node)
    _validate_activation(revision)

    if source_project is not None:
        validate_source_project_document(source_project)
        if revision.project_id != source_project["project_id"]:
            raise ValueError(
                "source graph is pinned to another source project"
            )

    if previous is _PREVIOUS_UNSET:
        return
    prior = _coerce_graph(previous) if previous is not None else None
    if prior is None:
        if revision.revision != 1 or revision.previous_graph_id is not None:
            raise ValueError(
                "source-graph root must be revision 1 without a predecessor"
            )
        if revision.activation["mode"] != "project_sources":
            raise ValueError(
                "source-graph root must activate project sources"
            )
        if source_project is not None:
            synthesized = _synthesize_source_graph_unvalidated(
                source_project
            )
            if revision.to_dict() != synthesized.to_dict():
                raise ValueError(
                    "source-graph root does not match source-project v1"
                )
        return

    if prior.project_id != revision.project_id:
        raise ValueError("source-graph project pin changed")
    if revision.revision != prior.revision + 1:
        raise ValueError("source-graph revision is not consecutive")
    if revision.previous_graph_id != prior.graph_id:
        raise ValueError("source-graph predecessor linkage is invalid")
    if revision.nodes[: len(prior.nodes)] != prior.nodes:
        raise ValueError("existing source-graph nodes changed")
    if revision.refinement_groups[
        : len(prior.refinement_groups)
    ] != prior.refinement_groups:
        raise ValueError("existing refinement groups changed")
    if len(revision.nodes) < len(prior.nodes):
        raise ValueError("source-graph nodes cannot be removed")
    if any(
        node.origin == "original"
        for node in revision.nodes[len(prior.nodes) :]
    ):
        raise ValueError(
            "new original sources cannot be appended outside source-project v1"
        )
    appended_node_ids = tuple(
        node.node_id for node in revision.nodes[len(prior.nodes) :]
    )
    if appended_node_ids != tuple(sorted(appended_node_ids)):
        raise ValueError(
            "appended source-graph nodes must be in canonical order"
        )
    if len(revision.refinement_groups) < len(prior.refinement_groups):
        raise ValueError("refinement groups cannot be removed")
    appended_group_ids = tuple(
        group.group_id
        for group in revision.refinement_groups[
            len(prior.refinement_groups) :
        ]
    )
    if appended_group_ids != tuple(sorted(appended_group_ids)):
        raise ValueError(
            "appended refinement groups must be in canonical order"
        )
    _validate_activation_transition(prior, revision)


def _source_project_document(
    value: Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        document = _json_copy(value)
        validate_source_project_document(document)
        return document
    path = Path(value).expanduser().absolute()
    if path.is_dir():
        path = path.joinpath(*SOURCE_PROJECT_RELATIVE_PATH.parts)
    if path.is_symlink():
        raise ValueError("source-project manifest must not be a symbolic link")
    return load_source_project(path)


def _load_project_root(
    project_root: str | Path,
) -> tuple[Path, dict[str, Any]]:
    root = Path(project_root).expanduser().absolute()
    if (
        not root.exists()
        or not root.is_dir()
        or root.is_symlink()
    ):
        raise SourceGraphError(
            "source-graph project root must be a real existing directory"
        )
    manifest = _project_path(
        root,
        SOURCE_PROJECT_RELATIVE_PATH,
        label="source-project manifest",
        require_exists=True,
        require_file=True,
    )
    return root, load_source_project(manifest)


def _graph_from_seed(seed: Mapping[str, Any]) -> SourceGraphRevision:
    graph_id = f"sha256:{document_sha256(seed)}"
    return _coerce_graph_unvalidated({**dict(seed), "graph_id": graph_id})


def _canonical_original_node_id(
    *,
    project_id: str,
    source_index: int,
    node: SourceGraphNode,
) -> str:
    seed = {
        "schema": "sunofriend.source-graph-node-seed.v1",
        "project_id": project_id,
        "source_index": source_index,
        "source_id": node.asset.asset_id,
        "canonical_path": node.asset.canonical_path,
        "receipt_path": node.asset.receipt_path,
    }
    return f"node:{document_sha256(seed)}"


def _canonical_nonoriginal_node_id(node: SourceGraphNode) -> str:
    seed = {
        "schema": "sunofriend.source-graph-derived-node-seed.v1",
        "parent_node_id": node.parent_node_id,
        "role": node.role,
        "declared_role": node.declared_role,
        "shape": node.shape,
        "origin": node.origin,
        "asset": node.asset.to_dict(),
        "derivation": (
            _json_copy(node.derivation)
            if node.derivation is not None
            else None
        ),
    }
    return f"node:{document_sha256(seed)}"


def _canonical_refinement_group_id(
    group: SourceRefinementGroup,
) -> str:
    seed = {
        "schema": "sunofriend.source-refinement-group-seed.v1",
        "parent_node_id": group.parent_node_id,
        "child_node_ids": list(sorted(group.child_node_ids)),
        "evidence_id": group.evidence_id,
        "coverage": group.coverage,
        "residual_node_id": group.residual_node_id,
    }
    return f"group:{document_sha256(seed)}"


def _coerce_graph(
    value: SourceGraphRevision | Mapping[str, Any],
) -> SourceGraphRevision:
    graph = _coerce_graph_unvalidated(value)
    validate_source_graph_revision(graph)
    return graph


def _coerce_graph_unvalidated(
    value: SourceGraphRevision | Mapping[str, Any],
) -> SourceGraphRevision:
    if isinstance(value, SourceGraphRevision):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("source graph must be an object")
    if set(value) != _GRAPH_FIELDS or value.get("schema") != SOURCE_GRAPH_SCHEMA:
        raise ValueError("unsupported source-graph schema or fields")
    if not isinstance(value.get("graph_id"), str):
        raise ValueError("source-graph graph_id must be a string")
    if not isinstance(value.get("project_id"), str):
        raise ValueError("source-graph project_id must be a string")
    revision_value = value.get("revision")
    if isinstance(revision_value, bool) or not isinstance(
        revision_value,
        int,
    ):
        raise ValueError("source-graph revision must be an integer")
    nodes_value = value.get("nodes")
    groups_value = value.get("refinement_groups")
    active_value = value.get("active_node_ids")
    activation_value = value.get("activation")
    if not isinstance(nodes_value, list):
        raise ValueError("source-graph nodes must be a list")
    if not isinstance(groups_value, list):
        raise ValueError("source-graph refinement_groups must be a list")
    if not isinstance(active_value, list):
        raise ValueError("source-graph active_node_ids must be a list")
    if not all(isinstance(item, str) for item in active_value):
        raise ValueError(
            "source-graph active_node_ids must contain strings"
        )
    if not isinstance(activation_value, Mapping):
        raise ValueError("source-graph activation must be an object")
    previous_value = value.get("previous_graph_id")
    if previous_value is not None and not isinstance(previous_value, str):
        raise ValueError("source-graph previous_graph_id is invalid")
    return SourceGraphRevision(
        graph_id=value["graph_id"],
        project_id=value["project_id"],
        revision=revision_value,
        previous_graph_id=previous_value,
        nodes=tuple(_coerce_node(node) for node in nodes_value),
        refinement_groups=tuple(
            _coerce_group(group) for group in groups_value
        ),
        active_node_ids=tuple(active_value),
        activation=_activation_dict(activation_value),
    )


def _coerce_node(
    value: SourceGraphNode | Mapping[str, Any],
) -> SourceGraphNode:
    if isinstance(value, SourceGraphNode):
        return value
    if not isinstance(value, Mapping) or set(value) != _NODE_FIELDS:
        raise ValueError("source-graph node fields are invalid")
    for field in ("node_id", "role", "shape", "origin"):
        if not isinstance(value.get(field), str):
            raise ValueError(
                f"source-graph node {field} must be a string"
            )
    asset_value = _coerce_asset(value.get("asset"))
    derivation = value.get("derivation")
    if derivation is not None and not isinstance(derivation, Mapping):
        raise ValueError("source-graph derivation must be an object or null")
    parent = value.get("parent_node_id")
    declared = value.get("declared_role")
    if parent is not None and not isinstance(parent, str):
        raise ValueError(
            "source-graph node parent_node_id must be a string or null"
        )
    if declared is not None and not isinstance(declared, str):
        raise ValueError(
            "source-graph node declared_role must be a string or null"
        )
    return SourceGraphNode(
        node_id=value["node_id"],
        parent_node_id=parent,
        role=value["role"],
        declared_role=declared,
        shape=value["shape"],
        origin=value["origin"],
        asset=asset_value,
        derivation=(
            None if derivation is None else _json_copy(derivation)
        ),
    )


def _coerce_asset(value: Any) -> SourceGraphAsset:
    if isinstance(value, SourceGraphAsset):
        return value
    if not isinstance(value, Mapping) or set(value) != _ASSET_FIELDS:
        raise ValueError("source-graph node asset fields are invalid")
    for field in _ASSET_FIELDS:
        if not isinstance(value.get(field), str):
            raise ValueError(
                f"source-graph node asset {field} must be a string"
            )
    return SourceGraphAsset(
        asset_id=value["asset_id"],
        canonical_path=value["canonical_path"],
        receipt_path=value["receipt_path"],
    )


def _coerce_group(
    value: SourceRefinementGroup | Mapping[str, Any],
) -> SourceRefinementGroup:
    if isinstance(value, SourceRefinementGroup):
        return value
    if not isinstance(value, Mapping) or set(value) != _GROUP_FIELDS:
        raise ValueError("source-graph refinement group fields are invalid")
    for field in (
        "group_id",
        "parent_node_id",
        "evidence_id",
        "coverage",
    ):
        if not isinstance(value.get(field), str):
            raise ValueError(f"refinement {field} must be a string")
    children = value.get("child_node_ids")
    if not isinstance(children, list):
        raise ValueError("refinement child_node_ids must be a list")
    if not all(isinstance(item, str) for item in children):
        raise ValueError(
            "refinement child_node_ids must contain strings"
        )
    residual = value.get("residual_node_id")
    if residual is not None and not isinstance(residual, str):
        raise ValueError(
            "refinement residual_node_id must be a string or null"
        )
    return SourceRefinementGroup(
        group_id=value["group_id"],
        parent_node_id=value["parent_node_id"],
        child_node_ids=tuple(children),
        evidence_id=value["evidence_id"],
        coverage=value["coverage"],
        residual_node_id=residual,
    )


def _canonical_group(
    group: SourceRefinementGroup,
) -> SourceRefinementGroup:
    return SourceRefinementGroup(
        group_id=group.group_id,
        parent_node_id=group.parent_node_id,
        child_node_ids=tuple(sorted(group.child_node_ids)),
        evidence_id=group.evidence_id,
        coverage=group.coverage,
        residual_node_id=group.residual_node_id,
    )


def _validate_node(node: SourceGraphNode) -> None:
    if set(node.to_dict()) != _NODE_FIELDS:
        raise ValueError("source-graph node fields are invalid")
    _node_id(node.node_id, "source-graph node_id")
    if node.parent_node_id is not None:
        _node_id(node.parent_node_id, "source-graph parent_node_id")
    _nonempty_text(node.role, "source-graph node role")
    if node.declared_role is not None:
        _nonempty_text(
            node.declared_role,
            "source-graph declared_role",
        )
    if node.shape not in _SHAPE_VALUES:
        raise ValueError("source-graph node shape is invalid")
    if node.origin not in _ORIGIN_VALUES:
        raise ValueError("source-graph node origin is invalid")
    _sha256_id(node.asset.asset_id, "source-graph asset_id")
    _safe_relative_path(
        node.asset.canonical_path,
        "source-graph canonical_path",
    )
    _safe_relative_path(
        node.asset.receipt_path,
        "source-graph receipt_path",
    )
    if node.origin == "original":
        if node.parent_node_id is not None or node.derivation is not None:
            raise ValueError(
                "original source-graph nodes cannot have derivation parents"
            )
    else:
        if node.parent_node_id is None or node.derivation is None:
            raise ValueError(
                "derived source-graph nodes need a parent and derivation"
            )
        _validate_derivation(node.derivation)
        if node.node_id != _canonical_nonoriginal_node_id(node):
            raise ValueError(
                "derived source-graph node_id does not match its content"
            )


def _validate_derivation(value: Mapping[str, Any]) -> None:
    if not value:
        raise ValueError("source-graph derivation must not be empty")
    _validate_json_value(value, label="source-graph derivation")
    process = value.get("process")
    evidence_id = value.get("evidence_id")
    if not isinstance(process, str) or not process.strip():
        raise ValueError(
            "source-graph derivation.process must be a non-empty string"
        )
    _sha256_id(evidence_id, "source-graph derivation.evidence_id")


def _validate_group(
    group: SourceRefinementGroup,
    nodes: Mapping[str, SourceGraphNode],
) -> None:
    if set(group.to_dict()) != _GROUP_FIELDS:
        raise ValueError("source-graph refinement group fields are invalid")
    _group_id(group.group_id, "refinement group_id")
    if group.group_id != _canonical_refinement_group_id(group):
        raise ValueError(
            "refinement group_id does not match its content"
        )
    _node_id(group.parent_node_id, "refinement parent_node_id")
    _sha256_id(group.evidence_id, "refinement evidence_id")
    if group.coverage not in _COVERAGE_VALUES:
        raise ValueError("refinement coverage is invalid")
    if not group.child_node_ids:
        raise ValueError("refinement group must contain child nodes")
    if len(group.child_node_ids) != len(set(group.child_node_ids)):
        raise ValueError("refinement child node IDs must be unique")
    parent = nodes.get(group.parent_node_id)
    if parent is None:
        raise ValueError("refinement parent node does not exist")
    for child_id in group.child_node_ids:
        _node_id(child_id, "refinement child_node_id")
        child = nodes.get(child_id)
        if child is None:
            raise ValueError("refinement child node does not exist")
        if child.parent_node_id != group.parent_node_id:
            raise ValueError(
                "refinement child does not name the group parent"
            )
        if (
            child.derivation is None
            or child.derivation.get("evidence_id") != group.evidence_id
        ):
            raise ValueError(
                "refinement child derivation evidence does not match its group"
            )
    if group.residual_node_id is not None:
        _node_id(group.residual_node_id, "refinement residual_node_id")
        if group.residual_node_id not in group.child_node_ids:
            raise ValueError(
                "refinement residual node must be one of the group children"
            )


def _validate_parent_graph(
    nodes: Mapping[str, SourceGraphNode],
) -> None:
    for node in nodes.values():
        if (
            node.parent_node_id is not None
            and node.parent_node_id not in nodes
        ):
            raise ValueError("source-graph parent node does not exist")
        seen: set[str] = set()
        current = node
        while current.parent_node_id is not None:
            if current.node_id in seen:
                raise ValueError("source-graph parent cycle detected")
            seen.add(current.node_id)
            current = nodes[current.parent_node_id]


def _validate_active_antichain(
    active_node_ids: Sequence[str],
    nodes: Mapping[str, SourceGraphNode],
) -> None:
    active = set(active_node_ids)
    for node_id in active_node_ids:
        current = nodes[node_id]
        while current.parent_node_id is not None:
            if current.parent_node_id in active:
                raise ValueError(
                    "active source frontier must be an antichain"
                )
            current = nodes[current.parent_node_id]


def _validate_active_role_uniqueness(
    active_node_ids: Sequence[str],
    nodes: Mapping[str, SourceGraphNode],
) -> None:
    by_role: dict[str, list[SourceGraphNode]] = {}
    for node_id in active_node_ids:
        node = nodes[node_id]
        by_role.setdefault(node.role, []).append(node)
    for role, matching in by_role.items():
        if len(matching) < 2 or role in _REPEATABLE_ACTIVE_ROLES:
            continue
        # source-project.v1 did not historically reject repeated opaque
        # provider roles. Preserve those unknown labels, which production does
        # not address by role, but fail closed for every prepared role that the
        # current conversion paths would otherwise silently truncate.
        if (
            role not in _PREPARED_ACTIVE_ROLES
            and all(node.origin == "original" for node in matching)
        ):
            continue
        raise ValueError(
            f"active source role {role!r} is not repeatable"
        )


def _validate_activation(revision: SourceGraphRevision) -> None:
    activation = _activation_dict(revision.activation)
    mode = activation["mode"]
    if mode not in _ACTIVATION_MODES:
        raise ValueError("source-graph activation mode is invalid")
    selected = activation["selected_node_ids"]
    for node_id in selected:
        _node_id(node_id, "activation selected_node_id")
    if len(selected) != len(set(selected)):
        raise ValueError("activation selected node IDs must be unique")
    if (
        revision.revision > 1
        and selected != sorted(selected)
    ):
        raise ValueError(
            "activation selected node IDs must be in canonical order"
        )
    groups = {
        group.group_id: group for group in revision.refinement_groups
    }
    group_id = activation["group_id"]
    reviewed = activation["reviewed"]
    if mode == "project_sources":
        if (
            group_id is not None
            or reviewed is not False
            or tuple(selected) != revision.active_node_ids
        ):
            raise ValueError("project_sources activation is invalid")
        return
    if mode == "unchanged":
        if group_id is not None or reviewed is not False or selected:
            raise ValueError("unchanged activation is invalid")
        return
    if not isinstance(group_id, str):
        raise ValueError("refinement activation requires group_id")
    _group_id(group_id, "activation group_id")
    group = groups.get(group_id)
    if group is None:
        raise ValueError("activation refinement group does not exist")
    allowed = {group.parent_node_id, *group.child_node_ids}
    if not selected or not set(selected).issubset(allowed):
        raise ValueError("activation selection is outside its refinement")
    if mode == "automatic_complete":
        if (
            reviewed is not False
            or group.coverage != "complete"
            or tuple(selected) != group.child_node_ids
        ):
            raise ValueError(
                "automatic activation requires every child of a complete refinement"
            )
    elif mode == "reviewed":
        if reviewed is not True:
            raise ValueError(
                "reviewed activation requires reviewed=true"
            )


def _validate_activation_transition(
    previous: SourceGraphRevision,
    current: SourceGraphRevision,
) -> None:
    activation = current.activation
    mode = activation["mode"]
    before = set(previous.active_node_ids)
    after = set(current.active_node_ids)
    if mode == "unchanged":
        if previous.active_node_ids != current.active_node_ids:
            raise ValueError(
                "unchanged activation changed or reordered the frontier"
            )
        return
    if mode == "project_sources":
        raise ValueError(
            "project_sources activation is valid only for revision 1"
        )
    groups = {
        group.group_id: group for group in current.refinement_groups
    }
    group = groups[activation["group_id"]]
    affected = {group.parent_node_id, *group.child_node_ids}
    before_affected = before.intersection(affected)
    if not before_affected:
        raise ValueError(
            "refinement activation does not intersect the active frontier"
        )
    selected = set(activation["selected_node_ids"])
    if mode == "automatic_complete":
        if before_affected != {group.parent_node_id}:
            raise ValueError(
                "automatic refinement requires its parent to be active"
            )
        removed = {group.parent_node_id}
    else:
        removed = affected
    expected = (before - removed) | selected
    if after != expected:
        raise ValueError(
            "active frontier does not match the refinement decision"
        )
    expected_order = _ordered_frontier_after_activation(
        previous.active_node_ids,
        group=group,
        mode=mode,
        selected_node_ids=activation["selected_node_ids"],
    )
    if current.active_node_ids != expected_order:
        raise ValueError(
            "active frontier order does not match the refinement decision"
        )
    if mode == "automatic_complete" and group.coverage != "complete":
        raise ValueError(
            "partial or unknown refinement cannot activate automatically"
        )


def _ordered_frontier_after_activation(
    previous_node_ids: Sequence[str],
    *,
    group: SourceRefinementGroup,
    mode: str,
    selected_node_ids: Sequence[str],
) -> tuple[str, ...]:
    """Replace one active refinement span without reordering other sources."""

    selected = set(selected_node_ids)
    ordered_selected: tuple[str, ...]
    ordered_selected = (
        *((group.parent_node_id,) if group.parent_node_id in selected else ()),
        *(
            node_id
            for node_id in group.child_node_ids
            if node_id in selected
        ),
    )
    removed = (
        {group.parent_node_id}
        if mode == "automatic_complete"
        else {group.parent_node_id, *group.child_node_ids}
    )
    output: list[str] = []
    inserted = False
    for node_id in previous_node_ids:
        if node_id in removed:
            if not inserted:
                output.extend(ordered_selected)
                inserted = True
            continue
        output.append(node_id)
    if not inserted:
        # Structural validation reports that this refinement did not intersect
        # the frontier.  Retaining the selection here gives that validation a
        # deterministic candidate rather than reflecting caller order.
        output.extend(ordered_selected)
    return tuple(output)


def _activation_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ACTIVATION_FIELDS:
        raise ValueError("source-graph activation fields are invalid")
    mode = value.get("mode")
    group_id = value.get("group_id")
    reviewed = value.get("reviewed")
    selected = value.get("selected_node_ids")
    if not isinstance(mode, str):
        raise ValueError("source-graph activation mode must be a string")
    if group_id is not None and not isinstance(group_id, str):
        raise ValueError(
            "source-graph activation group_id must be a string or null"
        )
    if not isinstance(reviewed, bool):
        raise ValueError(
            "source-graph activation reviewed must be boolean"
        )
    if not isinstance(selected, list):
        raise ValueError(
            "source-graph activation selected_node_ids must be a list"
        )
    if not all(isinstance(item, str) for item in selected):
        raise ValueError(
            "source-graph activation selected_node_ids must contain strings"
        )
    return {
        "mode": mode,
        "group_id": group_id,
        "reviewed": reviewed,
        "selected_node_ids": list(selected),
    }


def _validate_revision_chain(
    root: Path,
    *,
    current: SourceGraphRevision,
    synthesized: SourceGraphRevision,
    source_project: Mapping[str, Any],
) -> None:
    graph = current
    seen: set[str] = set()
    for _ in range(_MAXIMUM_REVISIONS):
        if graph.graph_id in seen:
            raise SourceGraphError("source-graph revision cycle detected")
        seen.add(graph.graph_id)
        validate_source_graph_revision(
            graph,
            source_project=source_project,
        )
        if graph.graph_id == synthesized.graph_id:
            if graph.to_dict() != synthesized.to_dict():
                raise SourceGraphError(
                    "source-graph root does not match source-project v1"
                )
            return
        if graph.revision <= 1 or graph.previous_graph_id is None:
            raise SourceGraphError(
                "source-graph chain does not reach source-project v1"
            )
        if graph.previous_graph_id == synthesized.graph_id:
            previous = synthesized
        else:
            previous = _load_graph_object(root, graph.previous_graph_id)
        validate_source_graph_revision(
            graph,
            source_project=source_project,
            previous=previous,
        )
        graph = previous
    raise SourceGraphError("source-graph revision chain exceeds its limit")


def _validate_active_source_evidence(
    root: Path,
    revision: SourceGraphRevision,
) -> None:
    """Attest active source-import receipts and their immutable file hashes."""

    active = set(revision.active_node_ids)
    nodes_by_id = {node.node_id: node for node in revision.nodes}
    for node in revision.nodes:
        if node.node_id not in active:
            continue
        canonical_relative = _safe_relative_path(
            node.asset.canonical_path,
            "active source canonical_path",
        )
        canonical_path = _project_path(
            root,
            canonical_relative,
            label="active source canonical asset",
            require_exists=True,
            require_file=True,
        )
        receipt_relative = _safe_relative_path(
            node.asset.receipt_path,
            "active source receipt_path",
        )
        receipt_path = _project_path(
            root,
            receipt_relative,
            label="active source receipt",
            require_exists=True,
            require_file=True,
        )
        receipt, encoded = _load_json_object(
            receipt_path,
            label="active source receipt",
            maximum_bytes=_MAXIMUM_EVIDENCE_RECEIPT_BYTES,
        )
        if encoded != canonical_json_bytes(receipt):
            raise SourceGraphError(
                "active source receipt is not in canonical JSON form"
            )
        schema = receipt.get("schema")
        try:
            if schema == SOURCE_IMPORT_SCHEMA:
                validate_source_receipt_document(receipt)
            elif schema == DERIVED_SOURCE_RECEIPT_SCHEMA:
                validate_derived_source_receipt_document(receipt)
            else:
                raise ValueError("unsupported active source receipt schema")
        except ValueError as exc:
            raise SourceGraphError("active source receipt is invalid") from exc
        identity = (
            receipt.get("source_id")
            if schema == SOURCE_IMPORT_SCHEMA
            else receipt.get("asset_id")
        )
        if identity != node.asset.asset_id:
            raise SourceGraphError(
                "active source receipt identity does not match its graph node"
            )
        canonical = receipt["canonical"]
        receipt_canonical = _safe_relative_path(
            canonical.get("path"),
            "active source receipt canonical.path",
        )
        if receipt_canonical != canonical_relative:
            raise SourceGraphError(
                "active source canonical path does not match its receipt"
            )
        if file_sha256(canonical_path) != canonical.get("sha256"):
            raise SourceGraphError(
                "active source canonical asset hash does not match its receipt"
            )
        if schema == DERIVED_SOURCE_RECEIPT_SCHEMA:
            parent = receipt["parent"]
            parent_node = nodes_by_id.get(str(node.parent_node_id))
            if (
                parent.get("node_id") != node.parent_node_id
                or parent_node is None
                or parent.get("asset_id") != parent_node.asset.asset_id
                or node.derivation is None
                or receipt["derivation"] != node.derivation
            ):
                raise SourceGraphError(
                    "active derived-source receipt lineage does not match its graph node"
                )
            continue
        original = receipt["original"]
        original_path = _project_path(
            root,
            _safe_relative_path(
                original.get("path"),
                "active source receipt original.path",
            ),
            label="active source original asset",
            require_exists=True,
            require_file=True,
        )
        if file_sha256(original_path) != original.get("sha256"):
            raise SourceGraphError(
                "active source original asset hash does not match its receipt"
            )


def _load_graph_object(root: Path, graph_id: str) -> SourceGraphRevision:
    graph_root = _graph_root(root, require_exists=True)
    object_path = _object_path(graph_root, graph_id)
    document, encoded = _load_json_object(
        object_path,
        label="source-graph object",
        maximum_bytes=_MAXIMUM_GRAPH_BYTES,
    )
    try:
        graph = _coerce_graph(document)
    except (TypeError, ValueError) as exc:
        raise SourceGraphError("source-graph object is invalid") from exc
    if graph.graph_id != graph_id:
        raise SourceGraphError(
            "source-graph object filename does not match graph_id"
        )
    if encoded != canonical_json_bytes(graph.to_dict()):
        raise SourceGraphError(
            "source-graph object is not in canonical JSON form"
        )
    return graph


def _load_current_pointer(path: Path) -> dict[str, Any]:
    document, encoded = _load_json_object(
        path,
        label="source-graph current pointer",
        maximum_bytes=4096,
    )
    if set(document) != _POINTER_FIELDS:
        raise SourceGraphError(
            "source-graph current pointer fields are invalid"
        )
    if document.get("schema") != SOURCE_GRAPH_POINTER_SCHEMA:
        raise SourceGraphError(
            "unsupported source-graph current pointer schema"
        )
    try:
        project_id = _sha256_id(
            document.get("project_id"),
            "source-graph pointer project_id",
        )
        graph_id = _sha256_id(
            document.get("graph_id"),
            "source-graph pointer graph_id",
        )
    except ValueError as exc:
        raise SourceGraphError(
            "source-graph current pointer identity is invalid"
        ) from exc
    revision = document.get("revision")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or revision > _MAXIMUM_REVISIONS
    ):
        raise SourceGraphError(
            "source-graph pointer revision is invalid"
        )
    pointer = {
        "schema": SOURCE_GRAPH_POINTER_SCHEMA,
        "project_id": project_id,
        "graph_id": graph_id,
        "revision": revision,
    }
    if encoded != canonical_json_bytes(pointer):
        raise SourceGraphError(
            "source-graph current pointer is not canonical JSON"
        )
    return pointer


def _load_json_object(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[dict[str, Any], bytes]:
    _require_regular_nonsymlink(path, label)
    size = path.stat().st_size
    if size < 2 or size > maximum_bytes:
        raise SourceGraphError(f"{label} has an invalid byte size")
    encoded = path.read_bytes()
    if len(encoded) != size:
        raise SourceGraphError(f"{label} changed while being read")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise SourceGraphError(f"{label} has duplicate JSON keys")
            result[key] = value
        return result

    try:
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda constant: (_raise_invalid_constant(
                constant,
                label=label,
            )),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceGraphError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SourceGraphError(f"{label} must contain a JSON object")
    return value, encoded


def _raise_invalid_constant(value: str, *, label: str) -> Any:
    raise SourceGraphError(f"{label} contains invalid JSON constant {value}")


def _prepare_graph_store(root: Path) -> Path:
    graph_root = root.joinpath(*SOURCE_GRAPH_RELATIVE_DIRECTORY.parts)
    if graph_root.is_symlink():
        raise SourceGraphError(
            "source-graph directory must not be a symbolic link"
        )
    graph_root.mkdir(mode=0o700, exist_ok=True)
    if not graph_root.is_dir() or graph_root.is_symlink():
        raise SourceGraphError("source-graph directory is invalid")
    os.chmod(graph_root, 0o700)
    objects = graph_root / "objects"
    if objects.is_symlink():
        raise SourceGraphError(
            "source-graph objects directory must not be a symbolic link"
        )
    objects.mkdir(mode=0o700, exist_ok=True)
    if not objects.is_dir() or objects.is_symlink():
        raise SourceGraphError("source-graph objects directory is invalid")
    os.chmod(objects, 0o700)
    return graph_root


def _validate_optional_graph_store(root: Path) -> None:
    graph_root = root.joinpath(*SOURCE_GRAPH_RELATIVE_DIRECTORY.parts)
    if not graph_root.exists():
        if graph_root.is_symlink():
            raise SourceGraphError(
                "source-graph directory must not be a symbolic link"
            )
        return
    if not graph_root.is_dir() or graph_root.is_symlink():
        raise SourceGraphError("source-graph directory is invalid")
    objects = graph_root / "objects"
    if objects.exists() and (not objects.is_dir() or objects.is_symlink()):
        raise SourceGraphError("source-graph objects directory is invalid")
    if objects.is_symlink():
        raise SourceGraphError(
            "source-graph objects directory must not be a symbolic link"
        )
    lock = graph_root / ".lock"
    if lock.exists():
        _require_regular_nonsymlink(lock, "source-graph writer lock")
    elif lock.is_symlink():
        raise SourceGraphError(
            "source-graph writer lock must not be a symbolic link"
        )


def _graph_root(root: Path, *, require_exists: bool) -> Path:
    graph_root = _project_path(
        root,
        SOURCE_GRAPH_RELATIVE_DIRECTORY,
        label="source-graph directory",
        require_exists=require_exists,
    )
    if require_exists and not graph_root.is_dir():
        raise SourceGraphError("source-graph directory is invalid")
    objects = graph_root / "objects"
    if (
        not objects.exists()
        or not objects.is_dir()
        or objects.is_symlink()
    ):
        raise SourceGraphError("source-graph objects directory is invalid")
    return graph_root


@contextmanager
def _exclusive_graph_lock(graph_root: Path) -> Iterable[None]:
    lock_path = graph_root / ".lock"
    if lock_path.is_symlink():
        raise SourceGraphError(
            "source-graph writer lock must not be a symbolic link"
        )
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise SourceGraphError(
            "source-graph writer lock is unavailable"
        ) from exc
    locked = False
    try:
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode):
                raise SourceGraphError(
                    "source-graph writer lock must be a regular file"
                )
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            if _fcntl is not None:
                _fcntl.flock(descriptor, _fcntl.LOCK_EX)
            elif _msvcrt is not None:
                # ``msvcrt.locking`` locks a byte range rather than the whole
                # file. Ensure the shared lock byte exists, then acquire it
                # from offset 0.
                if status.st_size < 1:
                    os.write(descriptor, b"\0")
                    os.fsync(descriptor)
                os.lseek(descriptor, 0, os.SEEK_SET)
                _msvcrt.locking(descriptor, _msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - supported platforms have one backend
                raise SourceGraphError(
                    "source-graph writer lock is unsupported on this platform"
                )
            locked = True
        except OSError as exc:
            raise SourceGraphError(
                "source-graph writer lock is unavailable"
            ) from exc
        yield
    finally:
        if locked:
            try:
                if _fcntl is not None:
                    _fcntl.flock(descriptor, _fcntl.LOCK_UN)
                elif _msvcrt is not None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    _msvcrt.locking(descriptor, _msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        os.close(descriptor)


def _object_path(graph_root: Path, graph_id: str) -> Path:
    digest = _sha256_id(graph_id, "source-graph graph_id").split(":", 1)[1]
    return graph_root / "objects" / f"{digest}.json"


def _write_graph_object(
    path: Path,
    graph: SourceGraphRevision,
) -> bool:
    encoded = canonical_json_bytes(graph.to_dict())
    if path.exists():
        _verify_existing_object(path, graph)
        return False
    if path.is_symlink():
        raise SourceGraphError(
            "source-graph object path must not be a symbolic link"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".source-graph-object-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
            created = True
        except FileExistsError:
            _verify_existing_object(path, graph)
            created = False
        _fsync_directory(path.parent)
        return created
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _verify_existing_object(
    path: Path,
    graph: SourceGraphRevision,
) -> None:
    _document, encoded = _load_json_object(
        path,
        label="source-graph object",
        maximum_bytes=_MAXIMUM_GRAPH_BYTES,
    )
    if encoded != canonical_json_bytes(graph.to_dict()):
        raise SourceGraphError(
            "existing source-graph object does not match its identity"
        )


def _write_current_pointer(
    path: Path,
    pointer: Mapping[str, Any],
) -> None:
    if path.is_symlink():
        raise SourceGraphError(
            "source-graph current pointer must not be a symbolic link"
        )
    encoded = canonical_json_bytes(pointer)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".source-graph-current-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _verify_pointer_matches(
    path: Path,
    graph: SourceGraphRevision,
) -> None:
    pointer = _load_current_pointer(path)
    if (
        pointer["project_id"] != graph.project_id
        or pointer["graph_id"] != graph.graph_id
        or pointer["revision"] != graph.revision
    ):
        raise SourceGraphConflictError(
            "source-graph current pointer changed"
        )


def _project_path(
    root: Path,
    relative: PurePosixPath,
    *,
    label: str,
    require_exists: bool,
    require_file: bool = False,
) -> Path:
    safe = _safe_relative_path(relative, label)
    current = root
    for part in safe.parts:
        current /= part
        if current.is_symlink():
            raise SourceGraphError(
                f"{label} path must not contain symbolic links"
            )
    if require_exists and not current.exists():
        raise SourceGraphError(f"{label} does not exist")
    if require_file and (
        not current.is_file() or current.is_symlink()
    ):
        raise SourceGraphError(f"{label} must be a regular file")
    try:
        current.resolve(strict=require_exists).relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise SourceGraphError(
            f"{label} escapes the source project"
        ) from exc
    return current


def _require_regular_nonsymlink(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise SourceGraphError(f"{label} must be a regular non-symlink file")


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    text = str(value or "")
    path = PurePosixPath(text)
    if (
        not text
        or "\\" in text
        or "\x00" in text
        or path.is_absolute()
        or ".." in path.parts
        or str(path) in {"", "."}
    ):
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return path


def _sha256_id(value: Any, label: str) -> str:
    text = str(value or "")
    if not _SHA256_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a sha256: identity")
    return text


def _node_id(value: Any, label: str) -> str:
    text = str(value or "")
    if not _NODE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a node: identity")
    return text


def _group_id(value: Any, label: str) -> str:
    text = str(value or "")
    if not _GROUP_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a group: identity")
    return text


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{label} must be a bounded non-empty string")
    return value


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    _validate_json_value(value, label="JSON object")
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        )
    )


def _validate_json_value(
    value: Any,
    *,
    label: str,
    depth: int = 0,
) -> None:
    if depth > 12:
        raise ValueError(f"{label} is nested too deeply")
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError(f"{label} contains an oversized string")
        if isinstance(value, float) and (
            value != value or value in {float("inf"), float("-inf")}
        ):
            raise ValueError(f"{label} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        if len(value) > 128:
            raise ValueError(f"{label} contains too many object fields")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 200:
                raise ValueError(f"{label} contains an invalid object key")
            _validate_json_value(item, label=label, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > 4096:
            raise ValueError(f"{label} contains an oversized list")
        for item in value:
            _validate_json_value(item, label=label, depth=depth + 1)
        return
    raise ValueError(f"{label} contains a non-JSON value")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        # Windows does not permit opening directories through ``os.open``.
        # File handles are already flushed before each atomic replacement.
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "SOURCE_GRAPH_CURRENT_RELATIVE_PATH",
    "SOURCE_GRAPH_OBJECTS_RELATIVE_DIRECTORY",
    "SOURCE_GRAPH_POINTER_SCHEMA",
    "SOURCE_GRAPH_RELATIVE_DIRECTORY",
    "SOURCE_GRAPH_SCHEMA",
    "SourceGraphAsset",
    "SourceGraphConflictError",
    "SourceGraphError",
    "SourceGraphNode",
    "SourceGraphRevision",
    "SourceGraphWriteResult",
    "SourceRefinementGroup",
    "build_source_graph_node",
    "build_source_graph_revision",
    "build_source_refinement_group",
    "load_source_graph",
    "resolve_active_sources",
    "synthesize_source_graph",
    "validate_source_graph_revision",
    "write_source_graph_revision",
]
