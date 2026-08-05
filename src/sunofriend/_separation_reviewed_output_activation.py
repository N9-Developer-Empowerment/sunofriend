"""Explicitly activate one exact reviewed private two-stem refinement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
)
from ._separation_private_render_review_equivalence import _load_candidate_package
from ._separation_reviewed_output_import import (
    REPORT_RELATIVE_PATH,
    SCHEMA as IMPORT_SCHEMA,
    STATUS as IMPORT_STATUS,
    _PERMISSIONS as IMPORT_PERMISSIONS,
    _verify_import_bindings,
)
from ._separation_reviewed_output_import_assessment import (
    _load_verified_reviewed_output_import_assessment,
)
from .audio_formats import file_sha256
from .derived_source_receipt import validate_derived_source_receipt_files
from .source_lineage import (
    build_source_graph_revision,
    load_source_graph,
    resolve_active_sources,
    write_source_graph_revision,
)


STATUS = "reviewed_private_stems_active_for_bounded_midi_validation"
POLICY_ID = "explicit-reviewed-complete-two-stem-activation-v1"
_EXPECTED_ROLES = frozenset({"vocals", "other"})


def _activate_reviewed_output(
    project_root: str | Path,
    *,
    assessment_path: str | Path,
    equivalence_path: str | Path,
    reviewed_export_path: str | Path,
    reviewed_package_dir: str | Path,
    candidate_package_report_path: str | Path,
    confirm_reviewed_stems_useful: bool,
) -> dict[str, Any]:
    """Activate both reviewed children together, retaining the parent rollback."""

    if confirm_reviewed_stems_useful is not True:
        raise ValueError(
            "reviewed-output activation requires explicit useful-stems confirmation"
        )
    root = Path(project_root).expanduser().absolute()
    _require_private_directory(root, "reviewed-output prepared project")
    assessment = _load_verified_reviewed_output_import_assessment(
        assessment_path,
        equivalence_path=equivalence_path,
        reviewed_export_path=reviewed_export_path,
        reviewed_package_dir=reviewed_package_dir,
        candidate_package_report_path=candidate_package_report_path,
    )
    candidate = _load_candidate_package(candidate_package_report_path)
    _verify_import_bindings(assessment["document"], candidate=candidate)
    imported = _load_import_report(root)
    _verify_import_report_bindings(
        imported["document"],
        assessment=assessment,
        candidate=candidate,
    )

    current = load_source_graph(root)
    report_graph = imported["document"]["source_graph"]
    group_id = report_graph["refinement_group_id"]
    group = next(
        (item for item in current.refinement_groups if item.group_id == group_id),
        None,
    )
    if group is None:
        raise ValueError("reviewed-output activation refinement group differs")
    if set(group.child_node_ids) != set(report_graph["imported_node_ids"]):
        raise ValueError("reviewed-output activation child set differs")
    _verify_imported_assets(root, imported["document"], current=current, candidate=candidate)

    imported_graph_id = report_graph["after_graph_id"]
    replayed = False
    if current.graph_id == imported_graph_id:
        parent = next(
            node
            for node in current.nodes
            if node.node_id == group.parent_node_id
        )
        active = resolve_active_sources(current, project_root=root)
        if active != (parent,) or parent.role != "mix":
            raise ValueError("reviewed-output activation parent frontier differs")
        activated = build_source_graph_revision(
            current,
            active_node_ids=group.child_node_ids,
            activation={
                "mode": "reviewed",
                "group_id": group.group_id,
                "reviewed": True,
                "selected_node_ids": list(group.child_node_ids),
            },
        )
        write_result = write_source_graph_revision(
            root,
            activated,
            expected_current_graph_id=current.graph_id,
        )
        if write_result.replayed:
            raise RuntimeError("fresh reviewed-output activation unexpectedly replayed")
        current = load_source_graph(root)
    elif _is_exact_activation_replay(
        current,
        imported_graph_id=imported_graph_id,
        group_id=group.group_id,
        child_node_ids=group.child_node_ids,
    ):
        replayed = True
    else:
        raise ValueError("reviewed-output project graph changed after import")

    active = resolve_active_sources(current, project_root=root)
    if {node.role for node in active} != _EXPECTED_ROLES:
        raise RuntimeError("reviewed-output activation frontier differs")
    parent = next(
        node for node in current.nodes if node.node_id == group.parent_node_id
    )
    return {
        "status": STATUS,
        "policy_id": POLICY_ID,
        "project_id": current.project_id,
        "graph_id": current.graph_id,
        "graph_revision": current.revision,
        "previous_graph_id": current.previous_graph_id,
        "refinement_group_id": group.group_id,
        "active_node_ids": list(current.active_node_ids),
        "active_roles": [node.role for node in active],
        "active_declared_roles": [node.declared_role for node in active],
        "rollback": {
            "retained_parent_node_id": parent.node_id,
            "retained_parent_role": parent.role,
            "retained_parent_asset_id": parent.asset.asset_id,
            "reviewed_parent_reactivation_supported_by_source_graph": True,
        },
        "readiness": {
            "private_reviewed_stems_active": True,
            "bounded_private_midi_validation_permitted": True,
            "simple_mode_available": False,
            "studio_import_available": False,
            "tui_route_available": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "next_action": "validate_active_reviewed_stems_through_midi_and_interpretation",
        "effects": {
            "source_graph_activation_changed": not replayed,
            "audio_created_or_mutated": False,
            "source_project_mutated": False,
            "candidate_selected_or_accepted_globally": False,
            "product_contract_mutated": False,
        },
        "replayed": replayed,
        "limitations": [
            "Activation permits only bounded private MIDI and interpretation validation.",
            "The two-stem result is not a separator default or general accuracy claim.",
            "Simple, Studio, TUI, public CLI, downloads and publication remain disabled for separation.",
        ],
    }


def _load_import_report(root: Path) -> dict[str, Any]:
    expected = root / REPORT_RELATIVE_PATH
    snapshot = _load_private_json_snapshot(expected, "reviewed-output import report")
    document = snapshot["document"]
    if (
        snapshot["path"] != expected
        or document.get("schema") != IMPORT_SCHEMA
        or document.get("status") != IMPORT_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != IMPORT_PERMISSIONS
        or document.get("readiness", {}).get("private_reviewed_output_import_complete")
        is not True
        or document.get("readiness", {}).get("source_graph_activation_permitted")
        is not False
    ):
        raise ValueError("reviewed-output import report differs")
    return snapshot


def _verify_import_report_bindings(
    document: Mapping[str, Any],
    *,
    assessment: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> None:
    bindings = document["bindings"]
    if (
        bindings.get("assessment_report_sha256") != assessment["sha256"]
        or bindings.get("assessment_document_sha256")
        != assessment["document"]["document_sha256"]
        or bindings.get("candidate_package_report_sha256") != candidate["sha256"]
        or bindings.get("candidate_package_document_sha256")
        != candidate["document"]["document_sha256"]
        or bindings.get("source_audio_sha256")
        != candidate["stitch"]["artifacts"]["source"]["sha256"]
        or document.get("rollback", {}).get("original_mix_remains_active") is not True
        or document.get("rollback", {}).get("reviewed_stems_are_inactive") is not True
    ):
        raise ValueError("reviewed-output import report binding differs")


def _verify_imported_assets(
    root: Path,
    document: Mapping[str, Any],
    *,
    current: Any,
    candidate: Mapping[str, Any],
) -> None:
    nodes = {node.node_id: node for node in current.nodes}
    if len(document["reviewed_assets"]) != 2:
        raise ValueError("reviewed-output imported asset count differs")
    for asset in document["reviewed_assets"]:
        role = asset["candidate_role"]
        node = nodes.get(asset["node_id"])
        candidate_artifact = candidate["stitch"]["artifacts"].get(role)
        if (
            node is None
            or node.origin != "derived"
            or node.role != asset["source_role"]
            or node.declared_role != asset["declared_role"]
            or node.asset.asset_id != asset["asset_id"]
            or node.asset.canonical_path != asset["canonical_path"]
            or node.asset.receipt_path != asset["receipt_path"]
            or candidate_artifact is None
            or candidate_artifact["sha256"] != asset["audio_sha256"]
        ):
            raise ValueError("reviewed-output imported asset binding differs")
        audio = root / node.asset.canonical_path
        receipt_path = root / node.asset.receipt_path
        receipt = _load_private_json_snapshot(
            receipt_path,
            f"reviewed-output {role} derived receipt",
        )["document"]
        validate_derived_source_receipt_files(receipt, root=root)
        if file_sha256(audio) != asset["audio_sha256"]:
            raise ValueError("reviewed-output imported audio differs")


def _is_exact_activation_replay(
    current: Any,
    *,
    imported_graph_id: str,
    group_id: str,
    child_node_ids: tuple[str, ...],
) -> bool:
    return (
        current.previous_graph_id == imported_graph_id
        and current.activation.get("mode") == "reviewed"
        and current.activation.get("reviewed") is True
        and current.activation.get("group_id") == group_id
        and set(current.activation.get("selected_node_ids", [])) == set(child_node_ids)
        and set(current.active_node_ids) == set(child_node_ids)
    )


__all__: tuple[str, ...] = ()
