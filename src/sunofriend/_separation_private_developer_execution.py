"""Preflight or explicitly execute one sealed private separation request.

This is a developer-only gate.  Preflight is the default and is read-only.
Model execution requires the caller to choose the execute action explicitly;
results remain unreviewed owner-only staging and cannot enter any product
route.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping

from ._separation_full_song_executor import (
    _execute_private_separation_full_song_queue,
)
from ._separation_private_execution_request import (
    _load_verified_private_separation_execution_request,
)


SCHEMA = "sunofriend.private-separation-developer-execution.v1"
PREFLIGHT_STATUS = "private_execution_preflight_complete_no_model_run"
EXECUTION_STATUS = "private_request_bound_execution_incomplete_review_required"
COMPLETE_STATUS = "private_request_bound_execution_complete_review_required"
_ROUTE_PERMISSIONS = {
    "bounded_private_execution_for_exact_request": True,
    "automatic_selection": False,
    "private_output_import_permitted": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}
QueueExecutor = Callable[..., Mapping[str, Any]]


def _run_private_separation_developer_execution(
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
    out_dir: str | Path,
    device: str,
    maximum_chunks: int | None = 1,
    execute: bool = False,
    queue_executor: QueueExecutor = _execute_private_separation_full_song_queue,
) -> dict[str, Any]:
    """Reconstruct the request, then preflight or execute bounded chunks."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("private separation execution device must be gpu or cpu")
    if maximum_chunks is not None and (
        isinstance(maximum_chunks, bool)
        or not isinstance(maximum_chunks, int)
        or maximum_chunks < 1
    ):
        raise ValueError("private separation maximum chunks must be positive or None")
    loaded = _load_verified_private_separation_execution_request(
        request_report_path,
        adapter_report_path=adapter_report_path,
        design_report_path=design_report_path,
        coverage_report_path=coverage_report_path,
        plan_report_path=plan_report_path,
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    requested_device = loaded["document"]["request"]["device"]
    if device != requested_device:
        raise ValueError("private separation execution device differs from request")
    output = Path(out_dir).expanduser().absolute()
    _require_output_disjoint(output, loaded=loaded)
    binding = _request_binding(loaded)
    readiness = {
        "request_and_upstream_evidence_verified": True,
        "execution_environment_reverified": True,
        "explicit_execution_action_received": execute,
        "model_run_started_this_invocation": False,
        "all_worker_runs_complete": False,
        "stitch_complete": False,
        "alignment_complete": False,
        "human_review_complete": False,
        "private_output_import_permitted": False,
        "product_integration_permitted": False,
        "public_release_permitted": False,
    }
    if not execute:
        if os.path.lexists(output):
            raise FileExistsError(
                f"private separation preflight output must be fresh: {output}"
            )
        return {
            "schema": SCHEMA,
            "status": PREFLIGHT_STATUS,
            "evidence_scope": "private_development_only",
            "request_binding": binding,
            "proposed_output": str(output),
            "readiness": readiness,
            "permissions": dict(_ROUTE_PERMISSIONS),
            "effects": {
                "execution_root_created_or_mutated": False,
                "model_run": False,
                "request_or_evidence_mutated": False,
                "source_graph_mutated": False,
            },
        }

    result = dict(
        queue_executor(
            loaded["plan_path"],
            out_dir=output,
            repository_root=repository_root,
            runtime_launcher_path=runtime_launcher_path,
            source_root=source_root,
            checkpoint_path=checkpoint_path,
            companion_root=companion_root,
            device=device,
            maximum_chunks=maximum_chunks,
            private_pilot_request_binding=binding,
        )
    )
    executed = result.get("chunks_executed_this_invocation", 0)
    if isinstance(executed, bool) or not isinstance(executed, int) or executed < 0:
        raise ValueError("private separation execution result differs")
    complete = result.get("summary", {}).get("all_worker_runs_complete") is True
    readiness["model_run_started_this_invocation"] = executed > 0
    readiness["all_worker_runs_complete"] = complete
    return {
        "schema": SCHEMA,
        "status": COMPLETE_STATUS if complete else EXECUTION_STATUS,
        "evidence_scope": "private_development_only",
        "request_binding": binding,
        "execution": result,
        "readiness": readiness,
        "permissions": dict(_ROUTE_PERMISSIONS),
    }


def _request_binding(loaded: Mapping[str, Any]) -> dict[str, Any]:
    document = loaded["document"]
    environment = loaded["adapter"]["document"]["backend"][
        "execution_environment"
    ]
    return {
        "request_schema": document["schema"],
        "request_policy_id": document["policy_id"],
        "request_report_sha256": loaded["sha256"],
        "request_document_sha256": document["document_sha256"],
        "checkpoint_sha256": document["bindings"]["checkpoint_sha256"],
        "source_manifest_sha256": environment["audited_source"][
            "manifest_sha256"
        ],
        "companion_manifest_sha256": environment["companion_manifest_sha256"],
        "worker_source_sha256": environment["worker_source"]["sha256"],
    }


def _require_output_disjoint(
    output: Path,
    *,
    loaded: Mapping[str, Any],
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
    }
    if output in evidence_paths or any(
        root == output or root in output.parents for root in evidence_roots
    ):
        raise ValueError("private separation execution output overlaps evidence")


__all__: tuple[str, ...] = ()
