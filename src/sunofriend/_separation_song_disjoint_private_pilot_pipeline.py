"""Resume one sealed private pilot through automatic evidence preparation.

This developer-only coordinator composes the request-bound executor, exact
clock stitcher, source-clock alignment measurement and automatic evidence
binder.  It deliberately stops before human review and exposes no product
route.
"""

from __future__ import annotations

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
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    _stitch_private_separation_full_song,
)
from ._separation_full_song_review import _load_stitch_report, _verify_stitch_audio
from ._separation_song_disjoint_private_pilot import (
    REPORT_NAME as EVIDENCE_REPORT_NAME,
    _bind_song_disjoint_private_pilot_evidence,
    _context_identity,
    _load_context,
    _load_verified_alignment,
    _load_verified_execution,
    _load_verified_song_disjoint_private_pilot_evidence,
    _verify_stitch_chain,
)
from ._separation_song_disjoint_private_pilot_execution import (
    REPORT_NAME as COMPLETION_REPORT_NAME,
    _execute_song_disjoint_private_pilot_request,
    _private_pilot_request_binding,
)
from ._separation_song_disjoint_private_pilot_request import (
    _load_verified_song_disjoint_private_pilot_request,
)


SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-pipeline.v1"
STATUS = "automatic_pipeline_complete_human_review_pending"
REPORT_NAME = "private-separation-song-disjoint-pilot-pipeline.json"
EXECUTION_DIRECTORY = "EXECUTION"
STITCH_DIRECTORY = "STITCH"
ALIGNMENT_DIRECTORY = "ALIGNMENT"
EVIDENCE_DIRECTORY = "EVIDENCE"
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_separation_available": False,
}

ExecutionRunner = Callable[..., Mapping[str, Any]]
StitchRunner = Callable[..., Mapping[str, Any]]
AlignmentRunner = Callable[..., Mapping[str, Any]]
EvidenceRunner = Callable[..., Mapping[str, Any]]


def _run_song_disjoint_private_pilot_pipeline(
    request_report_path: str | Path,
    *,
    pragmatic_authorization_path: str | Path,
    reference_v2_execution_path: str | Path,
    out_dir: str | Path | None,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str = "gpu",
    maximum_chunks: int | None = 1,
    preflight: bool = False,
    execution_runner: ExecutionRunner = _execute_song_disjoint_private_pilot_request,
    stitch_runner: StitchRunner = _stitch_private_separation_full_song,
    alignment_runner: AlignmentRunner = _measure_private_separation_full_song_alignment,
    evidence_runner: EvidenceRunner = _bind_song_disjoint_private_pilot_evidence,
) -> dict[str, Any]:
    """Preflight or advance the fixed automatic stages of one v2 request."""

    preflight_result = dict(
        execution_runner(
            request_report_path,
            out_dir=None,
            repository_root=repository_root,
            runtime_launcher_path=runtime_launcher_path,
            source_root=source_root,
            checkpoint_path=checkpoint_path,
            companion_root=companion_root,
            device=device,
            maximum_chunks=maximum_chunks,
            preflight=True,
        )
    )
    if preflight:
        return {
            "schema": SCHEMA,
            "status": "automatic_pipeline_preflight_complete_no_model_run",
            "request_binding": preflight_result["request_binding"],
            "stages": {
                "request_and_environment": "verified",
                "worker_execution": "not_run",
                "stitch": "not_run",
                "alignment": "not_run",
                "automatic_evidence": "not_run",
                "human_review": "not_run",
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {
                "filesystem_write": False,
                "human_review_mutated": False,
                "model_run": False,
                "product_contract_mutated": False,
                "separator_selected_or_accepted": False,
            },
        }
    if out_dir is None:
        raise ValueError("private pilot pipeline output directory is required")

    root = Path(out_dir).expanduser().absolute()
    _prepare_private_pipeline_root(root)
    execution_root = root / EXECUTION_DIRECTORY
    execution = dict(
        execution_runner(
            request_report_path,
            out_dir=execution_root,
            repository_root=repository_root,
            runtime_launcher_path=runtime_launcher_path,
            source_root=source_root,
            checkpoint_path=checkpoint_path,
            companion_root=companion_root,
            device=device,
            maximum_chunks=maximum_chunks,
            preflight=False,
        )
    )
    if execution.get("readiness", {}).get("all_worker_runs_complete") is not True:
        return {
            "schema": SCHEMA,
            "status": "worker_execution_incomplete_resume_required",
            "request_binding": preflight_result["request_binding"],
            "execution": execution,
            "stages": {
                "request_and_environment": "verified",
                "worker_execution": "incomplete",
                "stitch": "not_run",
                "alignment": "not_run",
                "automatic_evidence": "not_run",
                "human_review": "not_run",
            },
            "permissions": dict(_FALSE_PERMISSIONS),
        }

    request = _load_verified_song_disjoint_private_pilot_request(
        request_report_path
    )
    plan_path = request["plan_path"]
    execution_path = execution_root / EXECUTION_REPORT_NAME
    completion_path = execution_root / COMPLETION_REPORT_NAME
    stitch_root = root / STITCH_DIRECTORY
    alignment_path = root / ALIGNMENT_DIRECTORY / ALIGNMENT_REPORT_NAME
    evidence_path = root / EVIDENCE_DIRECTORY / EVIDENCE_REPORT_NAME
    created = {
        "stitch": False,
        "alignment": False,
        "automatic_evidence": False,
    }

    if not os.path.lexists(stitch_root):
        stitch_runner(plan_path, execution_path, out_dir=stitch_root)
        created["stitch"] = True
    _verify_automatic_stage_chain(
        request=request,
        execution_report_path=execution_path,
        stitch_package_dir=stitch_root,
    )
    if not os.path.lexists(alignment_path):
        alignment_runner(stitch_root, out=alignment_path)
        created["alignment"] = True
    _verify_automatic_stage_chain(
        request=request,
        execution_report_path=execution_path,
        stitch_package_dir=stitch_root,
        alignment_result_path=alignment_path,
    )
    if not os.path.lexists(evidence_path):
        evidence_runner(
            pragmatic_authorization_path,
            reference_v2_execution_path=reference_v2_execution_path,
            pilot_request_path=request_report_path,
            plan_report_path=plan_path,
            execution_report_path=execution_path,
            request_completion_binding_path=completion_path,
            stitch_package_dir=stitch_root,
            alignment_result_path=alignment_path,
            out=evidence_path,
        )
        created["automatic_evidence"] = True

    verified = _verify_completed_pipeline(
        pragmatic_authorization_path=pragmatic_authorization_path,
        reference_v2_execution_path=reference_v2_execution_path,
        request_report_path=request_report_path,
        plan_report_path=plan_path,
        execution_report_path=execution_path,
        request_completion_binding_path=completion_path,
        stitch_package_dir=stitch_root,
        alignment_result_path=alignment_path,
        evidence_path=evidence_path,
    )
    pipeline_report = _write_or_verify_pipeline_report(root, verified=verified)
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "report": str(pipeline_report),
        "review_html": str(verified["review_html"]),
        "execution": execution,
        "stages_created_this_invocation": created,
        "stages": {
            "request_and_environment": "verified",
            "worker_execution": "complete",
            "stitch": "complete",
            "alignment": "complete",
            "automatic_evidence": "complete",
            "human_review": "pending",
        },
        "readiness": dict(verified["readiness"]),
        "permissions": dict(_FALSE_PERMISSIONS),
    }


def _prepare_private_pipeline_root(root: Path) -> None:
    if not os.path.lexists(root):
        root.mkdir(parents=True, mode=0o700)
        root.chmod(0o700)
    _require_private_directory(root, "private pilot pipeline root")


def _verify_automatic_stage_chain(
    *,
    request: Mapping[str, Any],
    execution_report_path: str | Path,
    stitch_package_dir: str | Path,
    alignment_result_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify each persisted automatic stage before advancing past it."""

    request_binding = _private_pilot_request_binding(request)
    execution = _load_verified_execution(
        execution_report_path,
        plan=request["plan"],
        plan_sha256=request["plan_sha256"],
        request_binding=request_binding,
    )
    stitch_package = Path(stitch_package_dir).expanduser().absolute()
    _require_private_directory(stitch_package, "private pilot pipeline stitch")
    stitch_path = stitch_package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(stitch_package, stitch)
    stitch_sha256 = _sha256(stitch_path)
    _verify_stitch_chain(
        stitch,
        plan=request["plan"],
        plan_sha256=request["plan_sha256"],
        execution=execution["document"],
        execution_sha256=execution["sha256"],
        request_binding=request_binding,
    )
    alignment = None
    if alignment_result_path is not None:
        alignment = _load_verified_alignment(
            alignment_result_path,
            stitch=stitch,
            stitch_sha256=stitch_sha256,
        )
    return {
        "execution": execution,
        "stitch": stitch,
        "stitch_sha256": stitch_sha256,
        "alignment": alignment,
    }


def _verify_completed_pipeline(
    *,
    pragmatic_authorization_path: str | Path,
    reference_v2_execution_path: str | Path,
    request_report_path: str | Path,
    plan_report_path: str | Path,
    execution_report_path: str | Path,
    request_completion_binding_path: str | Path,
    stitch_package_dir: str | Path,
    alignment_result_path: str | Path,
    evidence_path: str | Path,
) -> dict[str, Any]:
    context = _load_context(
        pragmatic_authorization_path,
        reference_v2_execution_path=reference_v2_execution_path,
        pilot_request_path=request_report_path,
        plan_report_path=plan_report_path,
        execution_report_path=execution_report_path,
        request_completion_binding_path=request_completion_binding_path,
        stitch_package_dir=stitch_package_dir,
        alignment_result_path=alignment_result_path,
    )
    evidence = _load_verified_song_disjoint_private_pilot_evidence(evidence_path)
    bindings = evidence["document"]["bindings"]
    expected = {
        "pragmatic_authorization_sha256": context["authorization"]["sha256"],
        "reference_v2_execution_sha256": context["reference"]["sha256"],
        "pilot_request_sha256": context["request"]["sha256"],
        "pilot_plan_sha256": context["plan_sha256"],
        "pilot_execution_sha256": context["execution"]["sha256"],
        "pilot_completion_binding_sha256": context["completion"]["sha256"],
        "pilot_stitch_sha256": context["stitch_sha256"],
        "pilot_alignment_sha256": context["alignment"]["sha256"],
        "pilot_review_seed_sha256": context["review_seed_sha256"],
    }
    if any(bindings.get(key) != value for key, value in expected.items()):
        raise ValueError("private pilot pipeline evidence binding differs")
    identity = _context_identity(context)
    if len(identity) != 9 or any(not isinstance(value, str) for value in identity):
        raise ValueError("private pilot pipeline context identity differs")
    evidence_document = evidence["document"]
    return {
        "bindings": {
            **expected,
            "automatic_evidence_sha256": evidence["sha256"],
            "automatic_evidence_document_sha256": evidence_document[
                "document_sha256"
            ],
        },
        "clock": dict(context["stitch"]["clock"]),
        "alignment_summary": dict(context["alignment"]["document"]["summary"]),
        "human_review": dict(evidence_document["human_review"]),
        "readiness": dict(evidence_document["readiness"]),
        "review_html": (
            context["stitch_package"]
            / context["stitch"]["boundary_review"]["html"]
        ),
    }


def _write_or_verify_pipeline_report(
    root: Path,
    *,
    verified: Mapping[str, Any],
) -> Path:
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": dict(verified["bindings"]),
        "stages": {
            "request_and_environment": "verified",
            "worker_execution": "complete",
            "stitch": "complete",
            "alignment": "complete",
            "automatic_evidence": "complete",
            "human_review": "pending",
        },
        "clock": dict(verified["clock"]),
        "alignment_summary": dict(verified["alignment_summary"]),
        "human_review": dict(verified["human_review"]),
        "readiness": dict(verified["readiness"]),
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "automatic_evidence_created": True,
            "human_review_completed_or_mutated": False,
            "private_stitched_audio_created": True,
            "product_contract_mutated": False,
            "separator_selected_or_accepted": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "The automatic pipeline proves request, execution, stitch and alignment identity, not separator quality.",
            "Human complete-song and every-boundary listening remain pending.",
            "No Simple, Studio, TUI, source-graph, download or publication route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    report = root / REPORT_NAME
    if os.path.lexists(report):
        _require_private_regular(report, "private pilot pipeline report")
        try:
            persisted = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("private pilot pipeline report differs") from error
        if persisted != document:
            raise ValueError("private pilot pipeline report changed")
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


__all__: tuple[str, ...] = ()
