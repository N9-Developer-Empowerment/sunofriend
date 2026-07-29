from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import sunofriend.source_lineage as source_lineage
from sunofriend.source_lineage import (
    SOURCE_GRAPH_CURRENT_RELATIVE_PATH,
    SourceGraphAsset,
    SourceGraphConflictError,
    SourceGraphError,
    SourceGraphNode,
    build_source_graph_node,
    build_source_graph_revision,
    build_source_refinement_group,
    load_source_graph,
    resolve_active_sources,
    synthesize_source_graph,
    validate_source_graph_revision,
    write_source_graph_revision,
)
from sunofriend.source_project import (
    SourceMetadata,
    SourcePart,
    build_source_project,
    write_source_project,
)
from sunofriend.source_receipt import (
    SOURCE_IMPORT_SCHEMA,
    canonical_json_bytes,
)


def _identity(character: str) -> str:
    return f"sha256:{character * 64}"


def _write_source_evidence(
    root: Path,
    *,
    original_path: str,
    canonical_path: str,
    receipt_path: str,
    content: bytes,
) -> str:
    original = root / original_path
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"original-" + content)
    canonical = root / canonical_path
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"canonical-" + content)
    original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
    canonical_sha = hashlib.sha256(canonical.read_bytes()).hexdigest()
    receipt = {
        "schema": SOURCE_IMPORT_SCHEMA,
        "source_id": f"sha256:{original_sha}",
        "original": {
            "path": original_path,
            "sha256": original_sha,
        },
        "canonical": {
            "path": canonical_path,
            "sha256": canonical_sha,
            "sample_format": "pcm_s24le",
            "sample_width_bytes": 3,
        },
        "clock": {},
        "decoder": {
            "network_protocols": ["file"],
            "arguments": [],
        },
        "limits": {},
        "normalised": False,
        "network_used": False,
    }
    receipt_file = root / receipt_path
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.write_bytes(canonical_json_bytes(receipt))
    return receipt["source_id"]


def _make_project(root: Path) -> Path:
    input_root = root / "INPUT"
    input_root.mkdir(parents=True)
    drums_id = _write_source_evidence(
        root,
        original_path="INPUT/original/drums.flac",
        canonical_path="drums-canonical.wav",
        receipt_path="INPUT/receipts/drums.json",
        content=b"drums",
    )
    bass_id = _write_source_evidence(
        root,
        original_path="INPUT/original/bass.m4a",
        canonical_path="bass-canonical.wav",
        receipt_path="INPUT/receipts/bass.json",
        content=b"bass",
    )
    sources = (
        SourcePart(
            source_id=drums_id,
            role="drums",
            original_name="drums.flac",
            original_path="INPUT/original/drums.flac",
            canonical_path="drums-canonical.wav",
            receipt_path="INPUT/receipts/drums.json",
        ),
        SourcePart(
            source_id=bass_id,
            role="bass",
            original_name="bass.m4a",
            original_path="INPUT/original/bass.m4a",
            canonical_path="bass-canonical.wav",
            receipt_path="INPUT/receipts/bass.json",
        ),
    )
    project = build_source_project(
        title="Graph test",
        metadata=SourceMetadata(
            key="B minor",
            bpm=113,
            tuning_hz=440,
        ),
        rights_category="authorised_private_use",
        sources=sources,
    )
    manifest = input_root / "source-project.json"
    write_source_project(manifest, project)
    return manifest


def _derived_node(
    *,
    character: str,
    parent_node_id: str,
    role: str,
    evidence_character: str = "e",
    root: Path | None = None,
) -> SourceGraphNode:
    canonical_path = f"REFINED/{role}-{character}.wav"
    receipt_path = f"REFINED/{role}-{character}.json"
    asset_id = (
        _write_source_evidence(
            root,
            original_path=f"REFINED/original/{role}-{character}.bin",
            canonical_path=canonical_path,
            receipt_path=receipt_path,
            content=f"{role}-{character}".encode("ascii"),
        )
        if root is not None
        else _identity(character)
    )
    return build_source_graph_node(
        parent_node_id=parent_node_id,
        role=role,
        declared_role=role,
        shape="leaf",
        origin="derived",
        asset=SourceGraphAsset(
            asset_id=asset_id,
            canonical_path=canonical_path,
            receipt_path=receipt_path,
        ),
        derivation={
            "process": "test-splitter",
            "evidence_id": _identity(evidence_character),
            "parameters_sha256": _identity("f"),
        },
    )


def _complete_drums_revision(root: Path):
    base = load_source_graph(root)
    drums = next(node for node in base.nodes if node.role == "drums")
    kick = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
        root=root,
    )
    snare = _derived_node(
        character="d",
        parent_node_id=drums.node_id,
        role="snare",
        root=root,
    )
    group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(kick.node_id, snare.node_id),
        evidence_id=_identity("e"),
        coverage="complete",
    )
    unaffected = tuple(
        node_id
        for node_id in base.active_node_ids
        if node_id != drums.node_id
    )
    revision = build_source_graph_revision(
        base,
        append_nodes=(kick, snare),
        append_refinement_groups=(group,),
        active_node_ids=(*unaffected, kick.node_id, snare.node_id),
        activation={
            "mode": "automatic_complete",
            "group_id": group.group_id,
            "reviewed": False,
            "selected_node_ids": [kick.node_id, snare.node_id],
        },
    )
    return base, revision


def test_missing_overlay_synthesizes_flat_graph_without_writing(
    tmp_path: Path,
) -> None:
    manifest = _make_project(tmp_path)
    original_manifest = manifest.read_bytes()

    first = load_source_graph(tmp_path)
    second = synthesize_source_graph(manifest)

    assert first == second
    assert first.revision == 1
    assert first.previous_graph_id is None
    assert [node.role for node in first.nodes] == ["drums", "bass"]
    assert [node.shape for node in first.nodes] == ["composite", "leaf"]
    assert all(
        node.node_id != node.asset.asset_id for node in first.nodes
    )
    assert first.active_node_ids == tuple(
        node.node_id for node in first.nodes
    )
    assert resolve_active_sources(first) == first.nodes
    assert not (tmp_path / "SOURCE-GRAPH").exists()
    assert manifest.read_bytes() == original_manifest


def test_composite_capability_does_not_change_flat_source_shape(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "INPUT"
    input_root.mkdir()
    parts = []
    for role in ("vocals", "other", "drums"):
        source_id = _write_source_evidence(
            tmp_path,
            original_path=f"INPUT/original/{role}.flac",
            canonical_path=f"{role}-canonical.wav",
            receipt_path=f"INPUT/receipts/{role}.json",
            content=role.encode("ascii"),
        )
        parts.append(
            SourcePart(
                source_id=source_id,
                role=role,
                original_name=f"{role}.flac",
                original_path=f"INPUT/original/{role}.flac",
                canonical_path=f"{role}-canonical.wav",
                receipt_path=f"INPUT/receipts/{role}.json",
            )
        )
    project = build_source_project(
        title="Shapes",
        metadata=SourceMetadata(key=None, bpm=120, tuning_hz=440),
        rights_category="owned",
        sources=tuple(parts),
    )
    write_source_project(input_root / "source-project.json", project)

    graph = load_source_graph(tmp_path)

    assert {node.role: node.shape for node in graph.nodes} == {
        "vocals": "leaf",
        "other": "leaf",
        "drums": "composite",
    }


def test_duplicate_original_prepared_roles_fail_closed(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "INPUT"
    input_root.mkdir()
    parts = []
    for index in range(2):
        source_id = _write_source_evidence(
            tmp_path,
            original_path=f"INPUT/original/bass-{index}.flac",
            canonical_path=f"bass-{index}-canonical.wav",
            receipt_path=f"INPUT/receipts/bass-{index}.json",
            content=f"bass-{index}".encode("ascii"),
        )
        parts.append(
            SourcePart(
                source_id=source_id,
                role="bass",
                original_name=f"bass-{index}.flac",
                original_path=f"INPUT/original/bass-{index}.flac",
                canonical_path=f"bass-{index}-canonical.wav",
                receipt_path=f"INPUT/receipts/bass-{index}.json",
            )
        )
    project = build_source_project(
        title="Duplicate bass",
        metadata=SourceMetadata(key=None, bpm=120, tuning_hz=440),
        rights_category="owned",
        sources=tuple(parts),
    )
    write_source_project(input_root / "source-project.json", project)

    with pytest.raises(ValueError, match="not repeatable"):
        load_source_graph(tmp_path)


def test_complete_refinement_can_replace_active_parent_automatically(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)

    assert revision.revision == 2
    assert revision.previous_graph_id == base.graph_id
    assert revision.nodes[: len(base.nodes)] == base.nodes
    assert set(node.role for node in resolve_active_sources(revision)) == {
        "bass",
        "kick",
        "snare",
    }
    bass = next(node for node in base.nodes if node.role == "bass")
    assert revision.active_node_ids == (
        *revision.refinement_groups[0].child_node_ids,
        bass.node_id,
    )
    validate_source_graph_revision(revision, previous=base)


def test_canonical_node_and_group_identities_bind_semantic_content(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    drums = next(node for node in base.nodes if node.role == "drums")
    kick = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
    )
    same_kick = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
    )
    assert same_kick == kick
    assert same_kick.node_id == kick.node_id

    group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(kick.node_id,),
        evidence_id=_identity("e"),
        coverage="partial",
    )
    same_group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=tuple(reversed(group.child_node_ids)),
        evidence_id=_identity("e"),
        coverage="partial",
    )
    assert same_group == group

    with pytest.raises(ValueError, match="node_id does not match"):
        build_source_graph_revision(
            base,
            append_nodes=(
                replace(kick, node_id=f"node:{'1' * 64}"),
            ),
        )
    with pytest.raises(ValueError, match="group_id does not match"):
        build_source_graph_revision(
            base,
            append_nodes=(kick,),
            append_refinement_groups=(
                replace(group, group_id=f"group:{'2' * 64}"),
            ),
        )


def test_refinement_group_binds_every_child_to_one_evidence_run(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    drums = next(node for node in base.nodes if node.role == "drums")
    kick = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
        evidence_character="e",
    )
    mismatched = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(kick.node_id,),
        evidence_id=_identity("f"),
        coverage="partial",
    )

    with pytest.raises(ValueError, match="evidence does not match"):
        build_source_graph_revision(
            base,
            append_nodes=(kick,),
            append_refinement_groups=(mismatched,),
        )


def test_nonrepeatable_derived_roles_cannot_be_active_together(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    drums = next(node for node in base.nodes if node.role == "drums")
    first = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
    )
    second = _derived_node(
        character="d",
        parent_node_id=drums.node_id,
        role="kick",
    )
    group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(first.node_id, second.node_id),
        evidence_id=_identity("e"),
        coverage="complete",
    )
    unaffected = tuple(
        node_id
        for node_id in base.active_node_ids
        if node_id != drums.node_id
    )

    with pytest.raises(ValueError, match="not repeatable"):
        build_source_graph_revision(
            base,
            append_nodes=(first, second),
            append_refinement_groups=(group,),
            active_node_ids=(*unaffected, first.node_id, second.node_id),
            activation={
                "mode": "automatic_complete",
                "group_id": group.group_id,
                "reviewed": False,
                "selected_node_ids": [first.node_id, second.node_id],
            },
        )


def test_revision_identity_is_independent_of_unordered_input_order(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    drums = next(node for node in base.nodes if node.role == "drums")
    bass = next(node for node in base.nodes if node.role == "bass")
    kick = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
    )
    snare = _derived_node(
        character="d",
        parent_node_id=drums.node_id,
        role="snare",
    )
    low = _derived_node(
        character="f",
        parent_node_id=bass.node_id,
        role="bass",
        evidence_character="f",
    )
    texture = _derived_node(
        character="9",
        parent_node_id=bass.node_id,
        role="synth",
        evidence_character="f",
    )
    drums_group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(snare.node_id, kick.node_id),
        evidence_id=_identity("e"),
        coverage="complete",
    )
    bass_group = build_source_refinement_group(
        parent_node_id=bass.node_id,
        child_node_ids=(low.node_id, texture.node_id),
        evidence_id=_identity("f"),
        coverage="partial",
    )

    first = build_source_graph_revision(
        base,
        append_nodes=(kick, snare, low, texture),
        append_refinement_groups=(drums_group, bass_group),
        active_node_ids=base.active_node_ids,
    )
    second = build_source_graph_revision(
        base,
        append_nodes=(texture, low, snare, kick),
        append_refinement_groups=(bass_group, drums_group),
        active_node_ids=tuple(reversed(base.active_node_ids)),
    )

    assert first == second
    assert first.graph_id == second.graph_id
    assert tuple(node.node_id for node in first.nodes[len(base.nodes) :]) == (
        tuple(
            sorted(
                node.node_id
                for node in (kick, snare, low, texture)
            )
        )
    )
    assert tuple(
        group.group_id
        for group in first.refinement_groups
    ) == tuple(sorted((drums_group.group_id, bass_group.group_id)))
    assert all(
        group.child_node_ids == tuple(sorted(group.child_node_ids))
        for group in first.refinement_groups
    )
    assert first.active_node_ids == base.active_node_ids


@pytest.mark.parametrize("coverage", ["partial", "unknown"])
def test_incomplete_refinement_requires_explicit_review(
    tmp_path: Path,
    coverage: str,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    drums = next(node for node in base.nodes if node.role == "drums")
    kick = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
    )
    group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(kick.node_id,),
        evidence_id=_identity("e"),
        coverage=coverage,
    )
    active = tuple(
        node_id
        for node_id in base.active_node_ids
        if node_id != drums.node_id
    ) + (kick.node_id,)

    with pytest.raises(ValueError, match="automatic activation"):
        build_source_graph_revision(
            base,
            append_nodes=(kick,),
            append_refinement_groups=(group,),
            active_node_ids=active,
            activation={
                "mode": "automatic_complete",
                "group_id": group.group_id,
                "reviewed": False,
                "selected_node_ids": [kick.node_id],
            },
        )

    reviewed = build_source_graph_revision(
        base,
        append_nodes=(kick,),
        append_refinement_groups=(group,),
        active_node_ids=active,
        activation={
            "mode": "reviewed",
            "group_id": group.group_id,
            "reviewed": True,
            "selected_node_ids": [kick.node_id],
        },
    )
    assert reviewed.activation["reviewed"] is True


def test_active_frontier_rejects_parent_and_descendant(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    drums = next(node for node in base.nodes if node.role == "drums")
    child = _derived_node(
        character="c",
        parent_node_id=drums.node_id,
        role="kick",
    )
    group = build_source_refinement_group(
        parent_node_id=drums.node_id,
        child_node_ids=(child.node_id,),
        evidence_id=_identity("e"),
        coverage="partial",
    )

    with pytest.raises(ValueError, match="antichain"):
        build_source_graph_revision(
            base,
            append_nodes=(child,),
            append_refinement_groups=(group,),
            active_node_ids=(*base.active_node_ids, child.node_id),
            activation={
                "mode": "reviewed",
                "group_id": group.group_id,
                "reviewed": True,
                "selected_node_ids": [drums.node_id, child.node_id],
            },
        )


def test_reviewed_revision_can_return_to_retained_parent(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    _, refined = _complete_drums_revision(tmp_path)
    group = refined.refinement_groups[0]
    unaffected = tuple(
        node_id
        for node_id in refined.active_node_ids
        if node_id not in group.child_node_ids
    )

    reverted = build_source_graph_revision(
        refined,
        active_node_ids=(*unaffected, group.parent_node_id),
        activation={
            "mode": "reviewed",
            "group_id": group.group_id,
            "reviewed": True,
            "selected_node_ids": [group.parent_node_id],
        },
    )

    assert set(node.role for node in resolve_active_sources(reverted)) == {
        "bass",
        "drums",
    }
    assert reverted.active_node_ids == (
        group.parent_node_id,
        next(node.node_id for node in refined.nodes if node.role == "bass"),
    )


def test_write_is_content_addressed_cas_and_exactly_replayable(
    tmp_path: Path,
) -> None:
    manifest = _make_project(tmp_path)
    project_before = manifest.read_bytes()
    base, revision = _complete_drums_revision(tmp_path)

    result = write_source_graph_revision(
        tmp_path,
        revision,
        expected_current_graph_id=base.graph_id,
    )

    digest = revision.graph_id.removeprefix("sha256:")
    assert result.replayed is False
    assert result.object_created is True
    assert result.pointer_changed is True
    assert result.object_path == (
        tmp_path / "SOURCE-GRAPH" / "objects" / f"{digest}.json"
    )
    assert result.object_path.read_bytes() == canonical_json_bytes(
        revision.to_dict()
    )
    assert load_source_graph(tmp_path) == revision
    assert manifest.read_bytes() == project_before

    object_before = result.object_path.read_bytes()
    pointer = tmp_path.joinpath(
        *SOURCE_GRAPH_CURRENT_RELATIVE_PATH.parts
    )
    pointer_before = pointer.read_bytes()
    replay = write_source_graph_revision(
        tmp_path,
        revision,
        expected_current_graph_id=base.graph_id,
    )
    assert replay.replayed is True
    assert replay.object_created is False
    assert replay.pointer_changed is False
    assert result.object_path.read_bytes() == object_before
    assert pointer.read_bytes() == pointer_before


def test_publication_fails_closed_when_active_canonical_hash_changed(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    active_child = next(
        node
        for node in resolve_active_sources(revision)
        if node.origin == "derived"
    )
    (tmp_path / active_child.asset.canonical_path).write_bytes(b"tampered")

    with pytest.raises(SourceGraphError, match="canonical asset hash"):
        write_source_graph_revision(
            tmp_path,
            revision,
            expected_current_graph_id=base.graph_id,
        )

    pointer = tmp_path.joinpath(*SOURCE_GRAPH_CURRENT_RELATIVE_PATH.parts)
    assert not pointer.exists()
    assert load_source_graph(tmp_path) == base


def test_publication_fails_closed_when_active_receipt_identity_changed(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    active_child = next(
        node
        for node in resolve_active_sources(revision)
        if node.origin == "derived"
    )
    receipt_path = tmp_path / active_child.asset.receipt_path
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["source_id"] = _identity("9")
    receipt["original"]["sha256"] = "9" * 64
    receipt_path.write_bytes(canonical_json_bytes(receipt))

    with pytest.raises(SourceGraphError, match="identity does not match"):
        write_source_graph_revision(
            tmp_path,
            revision,
            expected_current_graph_id=base.graph_id,
        )

    pointer = tmp_path.joinpath(*SOURCE_GRAPH_CURRENT_RELATIVE_PATH.parts)
    assert not pointer.exists()
    assert load_source_graph(tmp_path) == base


def test_stale_cas_cannot_replace_current_graph(tmp_path: Path) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    write_source_graph_revision(
        tmp_path,
        revision,
        expected_current_graph_id=base.graph_id,
    )
    extra = _derived_node(
        character="f",
        parent_node_id=revision.nodes[0].node_id,
        role="hat",
    )
    next_revision = build_source_graph_revision(
        revision,
        append_nodes=(extra,),
    )

    with pytest.raises(
        SourceGraphConflictError,
        match="current pointer changed",
    ):
        write_source_graph_revision(
            tmp_path,
            next_revision,
            expected_current_graph_id=base.graph_id,
        )
    assert load_source_graph(tmp_path) == revision


def test_oversized_graph_cannot_publish_an_unloadable_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    encoded = canonical_json_bytes(revision.to_dict())
    monkeypatch.setattr(
        source_lineage,
        "_MAXIMUM_GRAPH_BYTES",
        len(encoded) - 1,
    )

    with pytest.raises(ValueError, match="byte limit"):
        write_source_graph_revision(
            tmp_path,
            revision,
            expected_current_graph_id=base.graph_id,
        )

    assert not (tmp_path / "SOURCE-GRAPH").exists()


def test_preexisting_oversized_object_is_rejected_before_reading_or_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    encoded = canonical_json_bytes(revision.to_dict())
    maximum = len(encoded) + 32
    monkeypatch.setattr(source_lineage, "_MAXIMUM_GRAPH_BYTES", maximum)
    object_directory = tmp_path / "SOURCE-GRAPH" / "objects"
    object_directory.mkdir(parents=True)
    object_path = (
        object_directory
        / f"{revision.graph_id.removeprefix('sha256:')}.json"
    )
    object_path.write_bytes(b"x" * (maximum + 1))

    with pytest.raises(SourceGraphError, match="invalid byte size"):
        write_source_graph_revision(
            tmp_path,
            revision,
            expected_current_graph_id=base.graph_id,
        )

    pointer = tmp_path.joinpath(*SOURCE_GRAPH_CURRENT_RELATIVE_PATH.parts)
    assert not pointer.exists()


def test_load_verifies_full_revision_chain(tmp_path: Path) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    write_source_graph_revision(
        tmp_path,
        revision,
        expected_current_graph_id=base.graph_id,
    )
    reverted = build_source_graph_revision(
        revision,
        active_node_ids=(
            next(node.node_id for node in revision.nodes if node.role == "bass"),
            revision.refinement_groups[0].parent_node_id,
        ),
        activation={
            "mode": "reviewed",
            "group_id": revision.refinement_groups[0].group_id,
            "reviewed": True,
            "selected_node_ids": [
                revision.refinement_groups[0].parent_node_id
            ],
        },
    )
    write_source_graph_revision(
        tmp_path,
        reverted,
        expected_current_graph_id=revision.graph_id,
    )
    assert load_source_graph(tmp_path) == reverted

    previous_object = (
        tmp_path
        / "SOURCE-GRAPH"
        / "objects"
        / f"{revision.graph_id.removeprefix('sha256:')}.json"
    )
    previous_object.write_text("{}", encoding="utf-8")
    with pytest.raises(SourceGraphError):
        load_source_graph(tmp_path)


def test_new_original_node_cannot_bypass_source_project(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base = load_source_graph(tmp_path)
    asset = SourceGraphAsset(
        asset_id=_identity("c"),
        canonical_path="lead.wav",
        receipt_path="INPUT/receipts/lead.json",
    )
    node_seed = {
        "schema": "sunofriend.source-graph-node-seed.v1",
        "project_id": base.project_id,
        "source_index": len(base.nodes),
        "source_id": asset.asset_id,
        "canonical_path": asset.canonical_path,
        "receipt_path": asset.receipt_path,
    }
    extra = SourceGraphNode(
        node_id=f"node:{hashlib.sha256(canonical_json_bytes(node_seed)).hexdigest()}",
        parent_node_id=None,
        role="lead",
        declared_role="lead",
        shape="leaf",
        origin="original",
        asset=asset,
        derivation=None,
    )

    with pytest.raises(ValueError, match="source-project v1"):
        build_source_graph_revision(base, append_nodes=(extra,))


def test_active_paths_cannot_escape_project(tmp_path: Path) -> None:
    _make_project(tmp_path)
    graph = load_source_graph(tmp_path)
    document = graph.to_dict()
    document["nodes"][0]["asset"]["canonical_path"] = "../outside.wav"
    document.pop("graph_id")
    document["graph_id"] = (
        "sha256:"
        + hashlib.sha256(canonical_json_bytes(document)).hexdigest()
    )

    with pytest.raises(ValueError, match="safe relative POSIX path"):
        validate_source_graph_revision(document)


def test_revision_validation_rejects_mutated_existing_node(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    document = revision.to_dict()
    document["nodes"][0]["role"] = "other"
    document.pop("graph_id")
    document["graph_id"] = (
        "sha256:"
        + hashlib.sha256(canonical_json_bytes(document)).hexdigest()
    )

    with pytest.raises(ValueError, match="existing source-graph nodes"):
        validate_source_graph_revision(document, previous=base)


def test_resolve_active_sources_rejects_symlinked_asset(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    graph = load_source_graph(tmp_path)
    canonical = tmp_path / "drums-canonical.wav"
    target = tmp_path / "actual.wav"
    canonical.replace(target)
    canonical.symlink_to(target)

    with pytest.raises(SourceGraphError, match="symbolic links"):
        resolve_active_sources(graph, project_root=tmp_path)


def test_load_rejects_symlinked_current_pointer(tmp_path: Path) -> None:
    _make_project(tmp_path)
    graph_root = tmp_path / "SOURCE-GRAPH"
    graph_root.mkdir()
    target = tmp_path / "outside-current.json"
    target.write_text("{}", encoding="utf-8")
    (graph_root / "current.json").symlink_to(target)

    with pytest.raises(SourceGraphError, match="symbolic links"):
        load_source_graph(tmp_path)


def test_load_rejects_noncanonical_or_tampered_object(
    tmp_path: Path,
) -> None:
    _make_project(tmp_path)
    base, revision = _complete_drums_revision(tmp_path)
    result = write_source_graph_revision(
        tmp_path,
        revision,
        expected_current_graph_id=base.graph_id,
    )
    os.chmod(result.object_path, 0o600)
    result.object_path.write_text(
        json.dumps(revision.to_dict()),
        encoding="utf-8",
    )

    with pytest.raises(
        SourceGraphError,
        match="canonical JSON form",
    ):
        load_source_graph(tmp_path)


def test_graph_project_pin_is_enforced(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _make_project(first)
    _make_project(second)
    second_manifest = second / "INPUT" / "source-project.json"
    second_document = json.loads(second_manifest.read_text(encoding="utf-8"))
    second_document["title"] = "Different project"
    seed = {
        key: value
        for key, value in second_document.items()
        if key != "project_id"
    }
    second_document["project_id"] = (
        "sha256:"
        + hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    )
    second_manifest.write_bytes(canonical_json_bytes(second_document))
    first_graph = load_source_graph(first)

    with pytest.raises(SourceGraphError, match="another source project"):
        resolve_active_sources(first_graph, project_root=second)
