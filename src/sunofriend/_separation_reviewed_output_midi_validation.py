"""Validate one activated reviewed separation through MIDI and interpretation.

This is a private-development orchestration boundary, not a product route.  It
re-verifies the exact reviewed-output activation, runs the established
production transcription components against only the active source frontier,
and creates an explicitly unreviewed MIDI-derived interpretation in a fresh
owner-only directory.  It never enables separation in Simple, Studio or TUI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _write_json_exclusive,
)
from ._separation_reviewed_output_activation import (
    POLICY_ID as ACTIVATION_POLICY_ID,
    _activate_reviewed_output,
)
from .audio_formats import file_sha256
from .automatic_selection import plan_automatic_selection
from .simple_result import SIMPLE_RESULT_DIRECTORY, build_simple_result
from .source_lineage import load_source_graph, resolve_active_sources
from .tui_conversion import create_full_conversion_runner
from .tui_conversion_contract import FullConversionRequest
from .tui_model import TuiProjectConfig, load_tui_project


SCHEMA = "sunofriend.private-separation-midi-interpretation-validation.v1"
STATUS = "private_midi_interpretation_created_review_required"
PARTIAL_STATUS = "private_midi_interpretation_partial_diagnostic"
POLICY_ID = "activated-reviewed-stems-production-components-private-validation-v1"
REPORT_RELATIVE_PATH = Path(
    "PRIVATE-SEPARATION/private-midi-interpretation-validation.json"
)
_EXPECTED_ACTIVE_ROLES = frozenset({"vocals", "other"})


async def _validate_reviewed_output_midi_and_interpretation(
    project_root: str | Path,
    *,
    assessment_path: str | Path,
    equivalence_path: str | Path,
    reviewed_export_path: str | Path,
    reviewed_package_dir: str | Path,
    candidate_package_report_path: str | Path,
    out_dir: str | Path,
    soundfont_path: str | Path | None = None,
    max_iterations: int = 8,
    confirm_reviewed_stems_useful: bool,
    confirm_private_midi_validation: bool,
) -> dict[str, Any]:
    """Create one fresh private MIDI/WAV result from the active reviewed stems."""

    if confirm_private_midi_validation is not True:
        raise ValueError(
            "private MIDI validation requires explicit execution confirmation"
        )
    root = Path(project_root).expanduser().absolute()
    _require_private_directory(root, "reviewed-output prepared project")
    activation = _activate_reviewed_output(
        root,
        assessment_path=assessment_path,
        equivalence_path=equivalence_path,
        reviewed_export_path=reviewed_export_path,
        reviewed_package_dir=reviewed_package_dir,
        candidate_package_report_path=candidate_package_report_path,
        confirm_reviewed_stems_useful=confirm_reviewed_stems_useful,
    )
    if (
        activation.get("policy_id") != ACTIVATION_POLICY_ID
        or activation.get("readiness", {}).get(
            "bounded_private_midi_validation_permitted"
        )
        is not True
        or activation.get("readiness", {}).get("product_integration_permitted")
        is not False
    ):
        raise ValueError("reviewed-output activation does not permit validation")

    before = load_source_graph(root)
    active_before = resolve_active_sources(before, project_root=root)
    if (
        before.graph_id != activation.get("graph_id")
        or {node.role for node in active_before} != _EXPECTED_ACTIVE_ROLES
        or {node.origin for node in active_before} != {"derived"}
    ):
        raise ValueError("private MIDI validation active source frontier differs")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"private MIDI validation destination exists: {destination}"
        )
    _require_private_directory(
        destination.parent,
        "private MIDI validation parent",
    )
    _require_disjoint(destination, root)

    request = FullConversionRequest.create(
        root,
        destination,
        conversion_mode="repair",
        evaluate_variants=True,
        max_iterations=max_iterations,
        include_vocals=True,
    )
    progress_rows: list[dict[str, Any]] = []

    def progress(item: Any) -> None:
        progress_rows.append(
            {
                "completed": int(getattr(item, "completed", 0)),
                "total": int(getattr(item, "total", 0)),
                "phase": str(getattr(item, "phase", "unknown"))[:100],
                "current_role": (
                    str(getattr(item, "current_role"))[:100]
                    if getattr(item, "current_role", None) is not None
                    else None
                ),
            }
        )

    conversion = await create_full_conversion_runner().run(
        request,
        on_progress=progress,
    )
    if not conversion.succeeded or not conversion.summary_paths:
        raise RuntimeError(
            "private MIDI validation produced no verified conversion summaries"
        )

    snapshot = load_tui_project(
        TuiProjectConfig.create(
            root,
            candidate_roots=conversion.candidate_roots,
            soundfont_path=soundfont_path,
        )
    )
    selection = plan_automatic_selection(
        snapshot.catalog,
        conversion.summary_paths,
        result_root=destination,
    )
    result = build_simple_result(
        snapshot.catalog,
        selection,
        destination=destination / SIMPLE_RESULT_DIRECTORY,
        artifact_cache_root=destination / ".private-artifact-cache",
        soundfont_path=soundfont_path,
    )

    after = load_source_graph(root)
    active_after = resolve_active_sources(after, project_root=root)
    if after.graph_id != before.graph_id or active_after != active_before:
        raise RuntimeError("private MIDI validation changed the source graph")

    document = _validation_document(
        activation=activation,
        graph=after,
        active=active_after,
        conversion=conversion,
        selection=selection,
        result=result,
        destination=destination,
        progress_rows=progress_rows,
    )
    report = destination / REPORT_RELATIVE_PATH
    report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_json_exclusive(report, document)
    report.chmod(0o400)
    return {
        **document,
        "root": str(destination),
        "report": str(report),
        "listen_first": str(result.balanced_wav_path),
        "combined_midi": str(result.combined_midi_path),
        "starter_zip": str(result.zip_path),
    }


def _validation_document(
    *,
    activation: Mapping[str, Any],
    graph: Any,
    active: tuple[Any, ...],
    conversion: Any,
    selection: Any,
    result: Any,
    destination: Path,
    progress_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    complete = (
        conversion.status == "complete"
        and not conversion.failed_roles
        and not conversion.skipped_roles
        and not selection.omitted
    )
    selected = [
        {
            "selection_index": int(item["selection_index"]),
            "stem_id": str(item["stem_id"]),
            "candidate_id": str(item["candidate_id"]),
            "role": str(item["role"]),
            "process": item.get("process"),
            "source_sha256": str(item["source"]["sha256"]),
            "midi_sha256": str(item["midi"]["sha256"]),
            "review_status": "not_reviewed",
        }
        for item in selection.selected
    ]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS if complete else PARTIAL_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "project_id": graph.project_id,
            "source_graph_id": graph.graph_id,
            "source_graph_revision": graph.revision,
            "activation_policy_id": activation["policy_id"],
            "activation_refinement_group_id": activation["refinement_group_id"],
        },
        "active_source_frontier": [
            {
                "node_id": node.node_id,
                "role": node.role,
                "declared_role": node.declared_role,
                "origin": node.origin,
                "asset_id": node.asset.asset_id,
            }
            for node in active
        ],
        "conversion": {
            "status": conversion.status,
            "converted_roles": list(conversion.converted_roles),
            "skipped_roles": list(conversion.skipped_roles),
            "failed_roles": list(conversion.failed_roles),
            "proxy_roles": list(conversion.proxy_roles),
            "warnings": list(conversion.warnings),
            "source_stem_count": conversion.source_stem_count,
            "midi_ready_stem_count": conversion.midi_ready_stem_count,
            "candidate_count": conversion.candidate_count,
            "progress": progress_rows[-32:],
        },
        "interpretation": {
            "automatic": True,
            "review_status": "not_reviewed",
            "review_recommended": True,
            "source_audio_mixed_into_wav": False,
            "release_master": False,
            "selected": selected,
            "omitted": list(selection.omitted),
            "result_manifest_sha256": result.manifest_sha256,
            "outputs": {
                "balanced_wav": _relative_record(
                    result.balanced_wav_path,
                    destination,
                ),
                "combined_midi": _relative_record(
                    result.combined_midi_path,
                    destination,
                ),
                "starter_zip": _relative_record(result.zip_path, destination),
                "result_manifest": _relative_record(
                    result.manifest_path,
                    destination,
                ),
            },
        },
        "readiness": {
            "private_listening_review_required": True,
            "private_midi_and_interpretation_created": complete,
            "partial_diagnostic_created": not complete,
            "cross_song_validation_required": True,
            "simple_mode_separation_available": False,
            "studio_separation_available": False,
            "tui_separation_available": False,
            "public_release_permitted": False,
        },
        "effects": {
            "fresh_private_validation_output_created": True,
            "source_graph_mutated": False,
            "source_audio_mutated": False,
            "human_decision_events_created": 0,
            "feedback_recorded": False,
            "separator_selected_or_accepted_globally": False,
            "product_contract_mutated": False,
        },
        "next_action": (
            "listen_to_private_midi_interpretation_and_assess_usefulness"
            if complete
            else "inspect_partial_diagnostic_and_retry_into_fresh_output"
        ),
        "limitations": [
            "The instrumental remainder uses the conservative other-to-synth transcription proxy.",
            "Automatic MIDI and the WAV are unreviewed musical interpretations, not source reconstruction.",
            "One successful song cannot establish a separator default or public readiness.",
        ],
    }
    return {**payload, "document_sha256": _document_sha256(payload)}


def _relative_record(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError("private validation output escaped its result root") from exc
    if not resolved.is_file():
        raise RuntimeError("private validation output is missing")
    return {
        "path": relative.as_posix(),
        "sha256": file_sha256(resolved),
        "bytes": resolved.stat().st_size,
    }


def _require_disjoint(destination: Path, source: Path) -> None:
    resolved_destination = destination.resolve()
    resolved_source = source.resolve()
    if (
        resolved_destination == resolved_source
        or resolved_source in resolved_destination.parents
        or resolved_destination in resolved_source.parents
    ):
        raise ValueError(
            "private MIDI validation output must be disjoint from the source project"
        )


__all__: tuple[str, ...] = ()
