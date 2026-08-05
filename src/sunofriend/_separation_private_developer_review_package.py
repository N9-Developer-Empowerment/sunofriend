"""Prepare one request-bound private separation result for human review.

This developer-only coordinator starts after model execution has completed. It
re-verifies the sealed request and every selected worker result, creates the
exact-clock stitch, measures source-to-reconstruction alignment, and exposes
the existing full-song and boundary review page. It never runs the model,
imports stems, selects a separator, or enables a product route.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_alignment import (
    REPORT_NAME as ALIGNMENT_REPORT_NAME,
    _measure_private_separation_full_song_alignment,
)
from ._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_review import _load_stitch_report, _verify_stitch_audio
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    _stitch_private_separation_full_song,
)
from ._separation_private_developer_execution import _request_binding
from ._separation_private_execution_request import (
    _load_verified_private_separation_execution_request,
)
from ._separation_song_disjoint_private_pilot import (
    _load_verified_alignment,
    _load_verified_execution,
    _load_verified_unreviewed_seed,
    _verify_stitch_chain,
)


SCHEMA = "sunofriend.private-separation-developer-review-package.v1"
STATUS = "private_review_package_complete_human_review_pending"
REPORT_NAME = "private-separation-developer-review-package.json"
STITCH_DIRECTORY = "STITCH"
ALIGNMENT_DIRECTORY = "ALIGNMENT"
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "private_output_import_permitted": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}

StitchRunner = Callable[..., Mapping[str, Any]]
AlignmentRunner = Callable[..., Mapping[str, Any]]


def _prepare_private_separation_developer_review_package(
    request_report_path: str | Path,
    *,
    adapter_report_path: str | Path,
    design_report_path: str | Path,
    coverage_report_path: str | Path,
    plan_report_path: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    execution_dir: str | Path,
    out_dir: str | Path,
    stitch_runner: StitchRunner = _stitch_private_separation_full_song,
    alignment_runner: AlignmentRunner = _measure_private_separation_full_song_alignment,
) -> dict[str, Any]:
    """Create or resume the non-activating automatic review stages."""

    request_kwargs = {
        "adapter_report_path": adapter_report_path,
        "design_report_path": design_report_path,
        "coverage_report_path": coverage_report_path,
        "plan_report_path": plan_report_path,
        "repository_root": repository_root,
        "runtime_launcher_path": runtime_launcher_path,
        "source_root": source_root,
        "checkpoint_path": checkpoint_path,
        "companion_root": companion_root,
    }
    loaded = _load_verified_private_separation_execution_request(
        request_report_path,
        **request_kwargs,
    )
    request_binding = _request_binding(loaded)
    execution_root = Path(execution_dir).expanduser().absolute()
    _require_private_directory(execution_root, "private separation execution root")
    execution_path = execution_root / EXECUTION_REPORT_NAME
    execution = _load_verified_execution(
        execution_path,
        plan=loaded["plan"],
        plan_sha256=loaded["plan_sha256"],
        request_binding=request_binding,
    )

    root = Path(out_dir).expanduser().absolute()
    _require_output_disjoint(root, loaded=loaded, execution_root=execution_root)
    _prepare_private_root(root)
    stitch_root = root / STITCH_DIRECTORY
    alignment_path = root / ALIGNMENT_DIRECTORY / ALIGNMENT_REPORT_NAME
    created = {"stitch": False, "alignment": False}

    if not os.path.lexists(stitch_root):
        stitch_runner(loaded["plan_path"], execution_path, out_dir=stitch_root)
        created["stitch"] = True
    chain = _verify_stage_chain(
        loaded=loaded,
        execution=execution,
        request_binding=request_binding,
        stitch_root=stitch_root,
    )

    if not os.path.lexists(alignment_path):
        alignment_runner(stitch_root, out=alignment_path)
        created["alignment"] = True
    alignment = _load_verified_alignment(
        alignment_path,
        stitch=chain["stitch"],
        stitch_sha256=chain["stitch_sha256"],
    )
    seed, seed_sha256 = _load_verified_unreviewed_seed(
        stitch_root,
        chain["stitch"],
    )

    rechecked = _load_verified_private_separation_execution_request(
        request_report_path,
        **request_kwargs,
    )
    rechecked_execution = _load_verified_execution(
        execution_path,
        plan=rechecked["plan"],
        plan_sha256=rechecked["plan_sha256"],
        request_binding=_request_binding(rechecked),
    )
    if (
        _request_identity(rechecked) != _request_identity(loaded)
        or rechecked_execution["sha256"] != execution["sha256"]
        or rechecked_execution["document"].get("state_sha256")
        != execution["document"].get("state_sha256")
    ):
        raise ValueError("private separation review-package evidence changed")

    document = _report_document(
        loaded=loaded,
        execution=execution,
        stitch=chain["stitch"],
        stitch_sha256=chain["stitch_sha256"],
        alignment=alignment,
        seed=seed,
        seed_sha256=seed_sha256,
    )
    report = _write_or_verify_report(root, document=document)
    review_html = stitch_root / chain["stitch"]["boundary_review"]["html"]
    return {
        **document,
        "report": str(report),
        "review_html": str(review_html),
        "output_directory": str(root),
        "stages_created_this_invocation": created,
    }


def _verify_stage_chain(
    *,
    loaded: Mapping[str, Any],
    execution: Mapping[str, Any],
    request_binding: Mapping[str, Any],
    stitch_root: Path,
) -> dict[str, Any]:
    _require_private_directory(stitch_root, "private separation stitch package")
    stitch_path = stitch_root / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(stitch_root, stitch)
    stitch_sha256 = _sha256(stitch_path)
    _verify_stitch_chain(
        stitch,
        plan=loaded["plan"],
        plan_sha256=loaded["plan_sha256"],
        execution=execution["document"],
        execution_sha256=execution["sha256"],
        request_binding=request_binding,
    )
    return {"stitch": stitch, "stitch_sha256": stitch_sha256}


def _report_document(
    *,
    loaded: Mapping[str, Any],
    execution: Mapping[str, Any],
    stitch: Mapping[str, Any],
    stitch_sha256: str,
    alignment: Mapping[str, Any],
    seed: Mapping[str, Any],
    seed_sha256: str,
) -> dict[str, Any]:
    request = loaded["document"]
    alignment_document = alignment["document"]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "request_report_sha256": loaded["sha256"],
            "request_document_sha256": request["document_sha256"],
            "backend_adapter_sha256": request["bindings"]["backend_adapter_sha256"],
            "route_design_sha256": request["bindings"]["route_design_sha256"],
            "coverage_report_sha256": request["bindings"]["coverage_report_sha256"],
            "plan_report_sha256": loaded["plan_sha256"],
            "plan_document_sha256": loaded["plan"]["document_sha256"],
            "execution_report_sha256": execution["sha256"],
            "execution_state_sha256": execution["document"]["state_sha256"],
            "stitch_report_sha256": stitch_sha256,
            "stitch_document_sha256": stitch["document_sha256"],
            "alignment_report_sha256": alignment["sha256"],
            "alignment_document_sha256": alignment_document["document_sha256"],
            "review_seed_sha256": seed_sha256,
            "review_package_commitment": seed["package_commitment"],
        },
        "track": {
            "track_id": request["request"]["track_id"],
            "track_title": request["request"]["track_title"],
            "candidate_id": request["request"]["candidate_id"],
        },
        "clock": deepcopy(stitch["clock"]),
        "stages": {
            "sealed_request_and_backend": "verified",
            "worker_execution": "complete",
            "exact_clock_stitch": "complete",
            "source_clock_alignment": "complete",
            "full_song_and_boundary_review": "pending",
            "reviewed_stem_import": "not_run",
        },
        "alignment_summary": deepcopy(alignment_document["summary"]),
        "readiness": {
            "request_bound_worker_runs_complete": True,
            "exact_stitch_complete": True,
            "alignment_gate_passed": True,
            "playable_review_package_complete": True,
            "human_review_complete": False,
            "private_output_import_permitted": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "alignment_evidence_created": True,
            "human_review_completed_or_mutated": False,
            "model_run": False,
            "private_stitched_audio_created": True,
            "product_contract_mutated": False,
            "separator_selected_or_accepted": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This package proves request, execution, stitch and alignment identity, not separator accuracy.",
            "The complete song and every exact chunk boundary still require human listening.",
            "Audible joins remain diagnostics and are not hidden or repaired by this coordinator.",
            "No reviewed-stem import, Simple, Studio, TUI, source-graph, download or publication route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _prepare_private_root(root: Path) -> None:
    if not os.path.lexists(root):
        root.mkdir(parents=True, mode=0o700)
        root.chmod(0o700)
    _require_private_directory(root, "private separation review-package root")


def _write_or_verify_report(root: Path, *, document: Mapping[str, Any]) -> Path:
    report = root / REPORT_NAME
    if os.path.lexists(report):
        _require_private_regular(report, "private separation review-package report")
        try:
            persisted = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("private separation review-package report differs") from error
        if persisted != document:
            raise ValueError("private separation review-package report changed")
        return report
    payload = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{REPORT_NAME}.", dir=root)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.chmod(0o600)
        temporary.write_bytes(payload)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, report)
        report.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return report


def _request_identity(loaded: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(loaded["sha256"]),
        str(loaded["document"]["document_sha256"]),
        str(loaded["adapter"]["sha256"]),
        str(loaded["adapter"]["document"]["document_sha256"]),
        str(loaded["plan_sha256"]),
        str(loaded["plan"]["document_sha256"]),
    )


def _require_output_disjoint(
    output: Path,
    *,
    loaded: Mapping[str, Any],
    execution_root: Path,
) -> None:
    adapter = loaded["adapter"]
    evidence_paths = {
        loaded["path"],
        loaded["plan_path"],
        adapter["path"],
        adapter["design"]["path"],
        adapter["design"]["coverage"]["path"],
    }
    evidence_roots = {
        loaded["plan_path"].parent,
        adapter["measured"]["source_root"],
        adapter["measured"]["companion_root"],
        execution_root,
    }
    if output in evidence_paths or any(
        root == output or root in output.parents for root in evidence_roots
    ):
        raise ValueError("private separation review-package output overlaps evidence")


__all__: tuple[str, ...] = ()
