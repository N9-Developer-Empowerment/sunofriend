"""Approachable developer-only entry to the reviewed two-stem route.

This module deliberately remains outside the public CLI.  It replaces a long
list of repeated evidence/runtime arguments with one locally verified profile,
then composes the existing plan, request, guarded execution and review-package
services without changing any of their safety or review boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    _load_verified_plan,
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_plan import (
    REPORT_NAME as PLAN_REPORT_NAME,
    _prepare_private_separation_full_song_plan,
)
from ._separation_private_backend_adapter_contract import (
    _load_verified_private_separation_backend_adapter_contract,
)
from ._separation_private_developer_execution import (
    COMPLETE_STATUS as EXECUTION_COMPLETE_STATUS,
    _run_private_separation_developer_execution,
)
from ._separation_private_developer_review_package import (
    REPORT_NAME as REVIEW_REPORT_NAME,
    _prepare_private_separation_developer_review_package,
)
from ._separation_private_execution_request import (
    REPORT_NAME as REQUEST_REPORT_NAME,
    _build_private_separation_execution_request,
    _load_verified_private_separation_execution_request,
)


SCHEMA = "sunofriend.private-separation-local-start.v1"
DOCTOR_STATUS = "private_two_stem_local_profile_ready"
PREPARED_STATUS = "private_two_stem_request_ready_explicit_execution_required"
INCOMPLETE_STATUS = "private_two_stem_execution_incomplete_resume_required"
REVIEW_STATUS = "private_two_stem_review_ready_human_listening_required"
REPORT_NAME = "private-separation-local-start.json"
PLAN_DIRECTORY = "PLAN"
REQUEST_DIRECTORY = "REQUEST"
EXECUTION_DIRECTORY = "EXECUTION"
REVIEW_DIRECTORY = "REVIEW"

_FALSE_PRODUCT_PERMISSIONS = {
    "automatic_selection": False,
    "private_output_import_permitted": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}


@dataclass(frozen=True)
class PrivateSeparationLocalProfile:
    repository_root: Path
    adapter_report: Path
    design_report: Path
    coverage_report: Path
    runtime_launcher: Path
    source_root: Path
    checkpoint: Path
    companion_root: Path


ProfileChecker = Callable[[PrivateSeparationLocalProfile], Mapping[str, Any]]
PlanBuilder = Callable[..., Mapping[str, Any]]
PlanLoader = Callable[..., tuple[Path, dict[str, Any], str]]
RequestBuilder = Callable[..., Mapping[str, Any]]
RequestLoader = Callable[..., Mapping[str, Any]]
ExecutionRunner = Callable[..., Mapping[str, Any]]
ReviewBuilder = Callable[..., Mapping[str, Any]]


def _resolve_private_separation_local_profile(
    repository_root: str | Path,
) -> PrivateSeparationLocalProfile:
    """Resolve the one accepted local Kim profile without scanning the Mac."""

    root = Path(repository_root).expanduser().absolute()
    private_model = (
        Path.home() / ".local/share/sunofriend/private-evaluation/kim-vocal-2-mlx-v1"
    )
    return PrivateSeparationLocalProfile(
        repository_root=root,
        adapter_report=(
            root / "work/separation-bakeoff/"
            "private-separation-backend-adapter-contract-v2-py313/"
            "private-separation-backend-adapter-contract.json"
        ),
        design_report=(
            root / "work/separation-bakeoff/private-separation-route-design-v1/"
            "private-separation-route-design.json"
        ),
        coverage_report=(
            root / "work/separation-bakeoff/multi-song-private-pilot-coverage-v3/"
            "private-separation-multi-song-private-pilot-coverage.json"
        ),
        runtime_launcher=root / "work/private-runtime-python313/venv/bin/python",
        source_root=private_model / "mlx-audio-source",
        checkpoint=private_model / "model.safetensors",
        companion_root=private_model / "checkpoint-directory",
    )


def _check_private_separation_local_profile(
    profile: PrivateSeparationLocalProfile,
    *,
    adapter_loader: Callable[..., Mapping[str, Any]] = (
        _load_verified_private_separation_backend_adapter_contract
    ),
) -> dict[str, Any]:
    """Deeply reverify the installed backend profile without writing files."""

    if not profile.repository_root.is_dir():
        raise FileNotFoundError(
            f"Sunofriend repository root is missing: {profile.repository_root}"
        )
    adapter = dict(
        adapter_loader(
            profile.adapter_report,
            design_report_path=profile.design_report,
            coverage_report_path=profile.coverage_report,
            repository_root=profile.repository_root,
            runtime_launcher_path=profile.runtime_launcher,
            source_root=profile.source_root,
            checkpoint_path=profile.checkpoint,
            companion_root=profile.companion_root,
        )
    )
    document = adapter["document"]
    backend = document["backend"]
    return {
        "schema": SCHEMA,
        "status": DOCTOR_STATUS,
        "candidate_id": backend["candidate_id"],
        "primary_roles": ["vocals", "instrumental"],
        "diagnostic_roles": ["reconstruction"],
        "adapter": {
            "sha256": adapter["sha256"],
            "document_sha256": document["document_sha256"],
        },
        "runtime": {
            "python": str(profile.runtime_launcher),
            "checkpoint": str(profile.checkpoint),
            "device_options": ["gpu", "cpu"],
        },
        "readiness": {
            "accepted_private_profile_verified": True,
            "offline_after_installed_profile_verified": True,
            "finished_mix_to_two_stem_execution_available": True,
            "human_review_required_before_downstream_use": True,
            "public_multi_stem_separator_available": False,
        },
        "permissions": dict(_FALSE_PRODUCT_PERMISSIONS),
        "effects": {
            "filesystem_write": False,
            "model_run": False,
            "product_contract_mutated": False,
        },
    }


def _start_private_separation_local_workflow(
    corpus_manifest_path: str | Path,
    track_id: str,
    *,
    out_dir: str | Path,
    repository_root: str | Path,
    device: str = "gpu",
    execute: bool = False,
    maximum_chunks: int | None = 1,
    profile_checker: ProfileChecker = _check_private_separation_local_profile,
    plan_builder: PlanBuilder = _prepare_private_separation_full_song_plan,
    plan_loader: PlanLoader = _load_verified_plan,
    request_builder: RequestBuilder = _build_private_separation_execution_request,
    request_loader: RequestLoader = (
        _load_verified_private_separation_execution_request
    ),
    execution_runner: ExecutionRunner = _run_private_separation_developer_execution,
    review_builder: ReviewBuilder = _prepare_private_separation_developer_review_package,
) -> dict[str, Any]:
    """Prepare, explicitly execute, and package one two-stem listening review."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("private local separation device must be gpu or cpu")
    if not isinstance(track_id, str) or not track_id.strip():
        raise ValueError("private local separation track ID must be non-empty")
    if maximum_chunks is not None and (
        isinstance(maximum_chunks, bool)
        or not isinstance(maximum_chunks, int)
        or maximum_chunks < 1
    ):
        raise ValueError("private local separation maximum chunks must be positive")

    profile = _resolve_private_separation_local_profile(repository_root)
    doctor = dict(profile_checker(profile))
    if doctor.get("status") != DOCTOR_STATUS:
        raise ValueError("private local separation profile is not ready")

    corpus = Path(corpus_manifest_path).expanduser().absolute()
    _require_private_regular(corpus, "private local separation corpus manifest")
    root = Path(out_dir).expanduser().absolute()
    _prepare_or_reuse_root(root)
    plan_path = root / PLAN_DIRECTORY / PLAN_REPORT_NAME
    request_path = root / REQUEST_DIRECTORY / REQUEST_REPORT_NAME
    execution_root = root / EXECUTION_DIRECTORY
    review_root = root / REVIEW_DIRECTORY

    created = {"plan": False, "request": False, "review_package": False}
    if not os.path.lexists(plan_path):
        plan_builder(corpus, track_id.strip(), out_dir=plan_path.parent)
        created["plan"] = True
    _, plan, plan_sha256 = plan_loader(plan_path)
    _require_plan_matches_source(
        plan,
        corpus_sha256=_sha256(corpus),
        track_id=track_id.strip(),
    )

    backend_kwargs = _backend_kwargs(profile)
    if not os.path.lexists(request_path):
        request_builder(
            profile.adapter_report,
            plan_report_path=plan_path,
            device=device,
            out=request_path,
            **backend_kwargs,
        )
        created["request"] = True
    request = dict(
        request_loader(
            request_path,
            plan_report_path=plan_path,
            adapter_report_path=profile.adapter_report,
            **backend_kwargs,
        )
    )
    if request["document"]["request"]["device"] != device:
        raise ValueError(
            "private local separation device differs from prepared request"
        )

    if not execute:
        preflight = None
        if not os.path.lexists(execution_root):
            preflight = dict(
                execution_runner(
                    request_path,
                    plan_report_path=plan_path,
                    out_dir=execution_root,
                    device=device,
                    maximum_chunks=maximum_chunks,
                    execute=False,
                    adapter_report_path=profile.adapter_report,
                    **backend_kwargs,
                )
            )
        return {
            "schema": SCHEMA,
            "status": PREPARED_STATUS,
            "root": str(root),
            "plan_report": str(plan_path),
            "request_report": str(request_path),
            "execution_root": str(execution_root),
            "created_this_invocation": created,
            "execution_preflight": preflight,
            "next_action": "repeat_with_explicit_execute",
            "permissions": dict(_FALSE_PRODUCT_PERMISSIONS),
        }

    execution = dict(
        execution_runner(
            request_path,
            plan_report_path=plan_path,
            out_dir=execution_root,
            device=device,
            maximum_chunks=maximum_chunks,
            execute=True,
            adapter_report_path=profile.adapter_report,
            **backend_kwargs,
        )
    )
    if execution.get("status") != EXECUTION_COMPLETE_STATUS:
        return {
            "schema": SCHEMA,
            "status": INCOMPLETE_STATUS,
            "root": str(root),
            "plan_report": str(plan_path),
            "request_report": str(request_path),
            "execution_root": str(execution_root),
            "created_this_invocation": created,
            "execution": execution,
            "next_action": "repeat_with_explicit_execute",
            "permissions": dict(_FALSE_PRODUCT_PERMISSIONS),
        }

    review_existed = os.path.lexists(review_root / REVIEW_REPORT_NAME)
    review = dict(
        review_builder(
            request_path,
            plan_report_path=plan_path,
            execution_dir=execution_root,
            out_dir=review_root,
            adapter_report_path=profile.adapter_report,
            **backend_kwargs,
        )
    )
    created["review_package"] = not review_existed
    document = _start_document(
        doctor=doctor,
        corpus=corpus,
        track_id=track_id.strip(),
        device=device,
        plan_path=plan_path,
        plan=plan,
        plan_sha256=plan_sha256,
        request_path=request_path,
        request=request,
        execution=execution,
        review=review,
    )
    report = _write_or_verify_start_report(root, document=document)
    return {
        **document,
        "report": str(report),
        "root": str(root),
        "plan_report": str(plan_path),
        "request_report": str(request_path),
        "execution_root": str(execution_root),
        "review_package": str(review_root),
        "review_html": review["review_html"],
        "created_this_invocation": created,
        "next_action": "complete_full_song_and_every_boundary_review",
    }


def _backend_kwargs(profile: PrivateSeparationLocalProfile) -> dict[str, Path]:
    return {
        "design_report_path": profile.design_report,
        "coverage_report_path": profile.coverage_report,
        "repository_root": profile.repository_root,
        "runtime_launcher_path": profile.runtime_launcher,
        "source_root": profile.source_root,
        "checkpoint_path": profile.checkpoint,
        "companion_root": profile.companion_root,
    }


def _prepare_or_reuse_root(root: Path) -> None:
    if not os.path.lexists(root):
        root.mkdir(parents=True, mode=0o700)
        root.chmod(0o700)
    _require_private_directory(root, "private local separation root")


def _require_plan_matches_source(
    plan: Mapping[str, Any],
    *,
    corpus_sha256: str,
    track_id: str,
) -> None:
    corpus = plan.get("corpus")
    if (
        not isinstance(corpus, Mapping)
        or corpus.get("manifest_sha256") != corpus_sha256
        or corpus.get("track_id") != track_id
    ):
        raise ValueError("private local separation plan source differs")


def _start_document(
    *,
    doctor: Mapping[str, Any],
    corpus: Path,
    track_id: str,
    device: str,
    plan_path: Path,
    plan: Mapping[str, Any],
    plan_sha256: str,
    request_path: Path,
    request: Mapping[str, Any],
    execution: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    review_report = Path(review["report"]).expanduser().absolute()
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": REVIEW_STATUS,
        "evidence_scope": "private_development_only",
        "track": {
            "track_id": track_id,
            "track_title": plan["corpus"]["track_title"],
            "device": device,
            "primary_roles": ["vocals", "instrumental"],
            "diagnostic_roles": ["reconstruction"],
        },
        "bindings": {
            "corpus_manifest_sha256": _sha256(corpus),
            "adapter_report_sha256": doctor["adapter"]["sha256"],
            "plan_report_sha256": plan_sha256,
            "plan_document_sha256": plan["document_sha256"],
            "request_report_sha256": _sha256(request_path),
            "request_document_sha256": request["document"]["document_sha256"],
            "review_package_report_sha256": _sha256(review_report),
            "review_package_document_sha256": review["document_sha256"],
        },
        "stages": {
            "local_profile": "verified",
            "full_song_plan": "complete",
            "execution_request": "complete",
            "worker_execution": "complete",
            "stitch_and_alignment": "complete",
            "human_review": "pending",
            "reviewed_stem_import": "not_run",
            "midi_wav_zip": "not_run",
        },
        "readiness": {
            "playable_review_page_ready": True,
            "human_review_complete": False,
            "finish_workflow_eligible": False,
            "public_multi_stem_separator_available": False,
        },
        "permissions": dict(_FALSE_PRODUCT_PERMISSIONS),
        "effects": {
            "model_run": True,
            "product_contract_mutated": False,
            "separator_selected_or_accepted": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This is an experimental local vocals-plus-instrumental route, not full multi-stem separation.",
            "The complete song and every chunk boundary require explicit human listening.",
            "No source graph, MIDI, WAV interpretation or ZIP is created until the separate finish workflow.",
            "Simple, Studio, TUI, public CLI and publication routes remain disabled for separation.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _write_or_verify_start_report(
    root: Path,
    *,
    document: Mapping[str, Any],
) -> Path:
    report = root / REPORT_NAME
    if os.path.lexists(report):
        _require_private_regular(report, "private local separation start report")
        try:
            persisted = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("private local separation start report differs") from error
        if persisted != document:
            raise ValueError("private local separation start report changed")
        return report
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(report, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.unlink(report)
        except FileNotFoundError:
            pass
        raise
    return report


__all__: tuple[str, ...] = ()
