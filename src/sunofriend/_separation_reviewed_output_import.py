"""Import one reviewed private separation as inactive source lineage.

This private-development boundary creates a fresh prepared project.  Its
original full mix remains the only active source.  Reviewed vocals and the
broad instrumental remainder are copied byte-for-byte into the project and
appended as one complete but inactive refinement group.  Activation is a
separate future reviewed operation.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import secrets
import shutil
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import _write_json_exclusive
from ._separation_private_developer_review_package import _FALSE_PERMISSIONS
from ._separation_private_render_review_equivalence import (
    _load_candidate_package,
    _require_output_disjoint,
)
from ._separation_reviewed_output_import_assessment import (
    _load_verified_reviewed_output_import_assessment,
)
from .audio_formats import file_sha256
from .derived_source_receipt import (
    build_derived_source_receipt,
    validate_derived_source_receipt_files,
    write_derived_source_receipt,
)
from .source_import import (
    _open_destination_parent,
    _publish_directory_no_replace,
    execute_source_import,
    inspect_pcm24_wav,
    plan_source_import,
)
from .source_lineage import (
    SourceGraphAsset,
    build_source_graph_node,
    build_source_graph_revision,
    build_source_refinement_group,
    load_source_graph,
    resolve_active_sources,
    write_source_graph_revision,
)


SCHEMA = "sunofriend.private-separation-reviewed-output-import.v1"
STATUS = "reviewed_stems_imported_inactive_original_mix_active"
POLICY_ID = "fresh-prepared-project-inactive-reviewed-two-stem-lineage-v1"
REPORT_RELATIVE_PATH = Path(
    "PRIVATE-SEPARATION/private-separation-reviewed-output-import.json"
)
DERIVED_DIRECTORY = Path("DERIVED/reviewed-separation-v1")
_PROCESS = "private-reviewed-two-stem-separation-import-v1"
_ROLES = ("vocals", "instrumental")
_PERMISSIONS = {
    **_FALSE_PERMISSIONS,
    "private_reviewed_output_import_completed": True,
}


def _import_reviewed_output(
    assessment_path: str | Path,
    *,
    equivalence_path: str | Path,
    reviewed_export_path: str | Path,
    reviewed_package_dir: str | Path,
    candidate_package_report_path: str | Path,
    ffmpeg: str | Path,
    ffprobe: str | Path,
    out_dir: str | Path,
    rights_category: str = "authorised_private_use",
    title: str | None = None,
    key: str | None = None,
    bpm: float | None = None,
    tuning_hz: float | None = None,
    chord_document: str | Path | None = None,
) -> dict[str, Any]:
    """Create one fresh private project with an unchanged active mix frontier."""

    assessment = _load_verified_reviewed_output_import_assessment(
        assessment_path,
        equivalence_path=equivalence_path,
        reviewed_export_path=reviewed_export_path,
        reviewed_package_dir=reviewed_package_dir,
        candidate_package_report_path=candidate_package_report_path,
    )
    candidate = _load_candidate_package(candidate_package_report_path)
    _verify_import_bindings(assessment["document"], candidate=candidate)

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"reviewed-output import destination exists: {destination}")
    _require_private_directory(destination.parent, "reviewed-output import parent")
    _require_output_disjoint(
        destination,
        reviewed_export=Path(reviewed_export_path).expanduser().absolute(),
        reviewed_package=Path(reviewed_package_dir).expanduser().absolute(),
        candidate_stitch_root=candidate["stitch_root"],
    )

    staging = _reserve_staging_path(destination)
    try:
        source_artifact = candidate["stitch"]["artifacts"]["source"]
        source_audio = candidate["stitch_root"] / source_artifact["path"]
        plan = plan_source_import(
            source_audio,
            staging,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            role="mix",
            key=key,
            bpm=bpm,
            tuning_hz=tuning_hz,
            chord_document=chord_document,
            discover_chords=False,
            rights_category=rights_category,
            title=title or "Reviewed private separation",
        )
        imported = execute_source_import(plan)
        if imported.root != staging:
            raise RuntimeError("source import published an unexpected project root")
        result = _append_inactive_reviewed_stems(
            staging,
            assessment=assessment,
            candidate=candidate,
        )
        parent_fd = _open_destination_parent(destination.parent)
        try:
            _publish_directory_no_replace(staging, destination, parent_fd=parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        if staging.exists() and not staging.is_symlink():
            _make_tree_owner_writable(staging)
            shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        **result,
        "root": str(destination),
        "report": str(destination / REPORT_RELATIVE_PATH),
    }


def _verify_import_bindings(
    assessment: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
) -> None:
    if (
        assessment.get("readiness", {}).get("private_import_implementation_eligible")
        is not True
        or assessment.get("future_import_contract", {}).get("initial_activation_mode")
        != "unchanged"
        or assessment.get("future_import_contract", {}).get("automatic_activation_permitted")
        is not False
        or assessment.get("bindings", {}).get("candidate_package_report_sha256")
        != candidate["sha256"]
        or assessment.get("bindings", {}).get("candidate_package_document_sha256")
        != candidate["document"]["document_sha256"]
        or assessment.get("bindings", {}).get("source_audio_sha256")
        != candidate["stitch"]["artifacts"]["source"]["sha256"]
    ):
        raise ValueError("reviewed-output import assessment binding differs")


def _append_inactive_reviewed_stems(
    root: Path,
    *,
    assessment: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    before = load_source_graph(root)
    active_before = resolve_active_sources(before, project_root=root)
    if len(active_before) != 1 or active_before[0].role != "mix":
        raise ValueError("reviewed-output import requires one active original mix")
    parent = active_before[0]
    assessment_document = assessment["document"]
    assessment_sha256 = assessment["sha256"]
    evidence_id = f"sha256:{assessment_document['document_sha256']}"
    expected_assets = {
        item["candidate_role"]: item
        for item in assessment_document["reviewed_assets"]
    }
    if set(expected_assets) != set(_ROLES):
        raise ValueError("reviewed-output import asset set differs")

    nodes = []
    copied_assets = []
    for role in _ROLES:
        expected = expected_assets[role]
        source_artifact = candidate["stitch"]["artifacts"][role]
        source = candidate["stitch_root"] / source_artifact["path"]
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"reviewed {role} asset is missing or unsafe")
        if file_sha256(source) != expected["audio_sha256"]:
            raise ValueError(f"reviewed {role} asset hash differs")

        suffix = expected["audio_sha256"][:16]
        relative_audio = DERIVED_DIRECTORY / f"{role}-{suffix}.wav"
        relative_receipt = DERIVED_DIRECTORY / f"{role}-{suffix}.receipt.json"
        target = root / relative_audio
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as source_handle, target.open("xb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        if file_sha256(target) != expected["audio_sha256"]:
            raise RuntimeError(f"copied reviewed {role} asset differs")
        geometry = inspect_pcm24_wav(target)
        expected_geometry = expected["geometry"]
        for field in ("sample_rate", "channels", "frames", "sample_width_bytes"):
            if geometry[field] != expected_geometry[field]:
                raise ValueError(f"reviewed {role} geometry differs")

        derivation = {
            "process": _PROCESS,
            "evidence_id": evidence_id,
            "candidate_role": role,
            "reviewed_evidence_status": "prior_human_review_bound_by_pcm24_equivalence",
            "assessment_report_sha256": assessment_sha256,
            "assessment_document_sha256": assessment_document["document_sha256"],
            "review_equivalence_document_sha256": assessment_document["bindings"][
                "review_equivalence_document_sha256"
            ],
            "candidate_package_document_sha256": candidate["document"][
                "document_sha256"
            ],
            "source_audio_sha256": candidate["stitch"]["artifacts"]["source"][
                "sha256"
            ],
        }
        receipt = build_derived_source_receipt(
            canonical_path=relative_audio.as_posix(),
            canonical_sha256=expected["audio_sha256"],
            canonical_bytes=target.stat().st_size,
            sample_rate=geometry["sample_rate"],
            channels=geometry["channels"],
            frames=geometry["frames"],
            parent_node_id=parent.node_id,
            parent_asset_id=parent.asset.asset_id,
            derivation=derivation,
        )
        receipt_path = root / relative_receipt
        write_derived_source_receipt(receipt_path, receipt)
        validate_derived_source_receipt_files(receipt, root=root)
        node = build_source_graph_node(
            parent_node_id=parent.node_id,
            role=expected["source_role"],
            declared_role=expected["declared_role"],
            shape=expected["shape"],
            origin=expected["origin"],
            asset=SourceGraphAsset(
                asset_id=receipt["asset_id"],
                canonical_path=relative_audio.as_posix(),
                receipt_path=relative_receipt.as_posix(),
            ),
            derivation=derivation,
        )
        nodes.append(node)
        copied_assets.append(
            {
                "candidate_role": role,
                "source_role": node.role,
                "declared_role": node.declared_role,
                "node_id": node.node_id,
                "asset_id": node.asset.asset_id,
                "canonical_path": node.asset.canonical_path,
                "receipt_path": node.asset.receipt_path,
                "audio_sha256": expected["audio_sha256"],
                "bytes": target.stat().st_size,
                "geometry": {
                    "sample_rate": geometry["sample_rate"],
                    "channels": geometry["channels"],
                    "frames": geometry["frames"],
                    "sample_width_bytes": geometry["sample_width_bytes"],
                },
                "active": False,
            }
        )
        target.chmod(0o444)
        receipt_path.chmod(0o444)

    group = build_source_refinement_group(
        parent_node_id=parent.node_id,
        child_node_ids=[node.node_id for node in nodes],
        evidence_id=evidence_id,
        coverage="complete",
    )
    revision = build_source_graph_revision(
        before,
        append_nodes=nodes,
        append_refinement_groups=(group,),
    )
    write_result = write_source_graph_revision(
        root,
        revision,
        expected_current_graph_id=before.graph_id,
    )
    after = load_source_graph(root)
    active_after = resolve_active_sources(after, project_root=root)
    if after.graph_id != revision.graph_id or active_after != active_before:
        raise RuntimeError("inactive reviewed stems changed the active source frontier")

    document = _import_document(
        assessment=assessment,
        candidate=candidate,
        parent=parent,
        before=before,
        after=after,
        group_id=group.group_id,
        assets=copied_assets,
        graph_object_created=write_result.object_created,
        graph_pointer_changed=write_result.pointer_changed,
    )
    report = root / REPORT_RELATIVE_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    _write_json_exclusive(report, document)
    report.chmod(0o444)
    return document


def _import_document(
    *,
    assessment: Mapping[str, Any],
    candidate: Mapping[str, Any],
    parent: Any,
    before: Any,
    after: Any,
    group_id: str,
    assets: list[dict[str, Any]],
    graph_object_created: bool,
    graph_pointer_changed: bool,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "assessment_report_sha256": assessment["sha256"],
            "assessment_document_sha256": assessment["document"]["document_sha256"],
            "review_equivalence_document_sha256": assessment["document"]["bindings"][
                "review_equivalence_document_sha256"
            ],
            "candidate_package_report_sha256": candidate["sha256"],
            "candidate_package_document_sha256": candidate["document"][
                "document_sha256"
            ],
            "source_audio_sha256": candidate["stitch"]["artifacts"]["source"][
                "sha256"
            ],
        },
        "source_graph": {
            "project_id": after.project_id,
            "before_graph_id": before.graph_id,
            "after_graph_id": after.graph_id,
            "revision": after.revision,
            "refinement_group_id": group_id,
            "coverage": "complete",
            "activation_mode": "unchanged",
            "active_node_ids": list(after.active_node_ids),
            "active_parent": {
                "node_id": parent.node_id,
                "role": parent.role,
                "asset_id": parent.asset.asset_id,
            },
            "imported_node_ids": [asset["node_id"] for asset in assets],
            "graph_object_created": graph_object_created,
            "graph_pointer_changed": graph_pointer_changed,
        },
        "reviewed_assets": deepcopy(assets),
        "rollback": {
            "original_mix_retained": True,
            "original_mix_remains_active": True,
            "reviewed_stems_are_inactive": True,
            "external_path_dependencies": False,
        },
        "readiness": {
            "private_reviewed_output_import_complete": True,
            "immutable_lineage_complete": True,
            "original_mix_rollback_complete": True,
            "reviewed_activation_required": True,
            "source_graph_activation_permitted": False,
            "midi_conversion_of_imported_stems_permitted": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "next_action": "design_and_review_separate_private_source_graph_activation",
        "permissions": dict(_PERMISSIONS),
        "effects": {
            "fresh_prepared_project_created": True,
            "audio_copied_byte_for_byte": True,
            "source_graph_revision_appended": True,
            "active_source_frontier_changed": False,
            "candidate_selected_or_accepted": False,
            "product_contract_mutated": False,
        },
        "limitations": [
            "The imported stems remain inactive and are not visible to Simple, Studio or the TUI.",
            "The instrumental remainder is role other with declared role instrumental.",
            "Reconstruction remains diagnostic and was not imported as an independent stem.",
            "A separate reviewed activation must verify this exact project and graph revision.",
            "One reviewed private song does not establish general separator accuracy or public readiness.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _reserve_staging_path(destination: Path) -> Path:
    for _attempt in range(100):
        candidate = destination.with_name(
            f".{destination.name}.reviewed-importing-{secrets.token_hex(8)}"
        )
        if not os.path.lexists(candidate):
            return candidate
    raise FileExistsError("could not reserve a reviewed-output import staging path")


def _make_tree_owner_writable(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            if not path.is_symlink():
                path.chmod(0o700 if path.is_dir() else 0o600)
        except OSError:
            pass
    try:
        root.chmod(0o700)
    except OSError:
        pass


__all__: tuple[str, ...] = ()
