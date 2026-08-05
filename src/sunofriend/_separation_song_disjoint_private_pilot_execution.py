"""Execute one sealed v2 song-disjoint private-pilot request.

This private-development adapter remeasures every execution input before each
invocation and binds the immutable request to the resumable full-song state.
It does not stitch, select, accept, publish, or expose separated audio through
any product route.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
    _execute_private_separation_full_song_queue,
    _require_private_regular,
)
from ._separation_song_disjoint_private_pilot_request import (
    POLICY_ID as REQUEST_POLICY_ID,
    SCHEMA as REQUEST_SCHEMA,
    _load_verified_song_disjoint_private_pilot_request,
    _measure_request_execution_environment,
)


SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-execution.v1"
STATUS = "request_bound_worker_execution_complete_human_review_pending"
REPORT_NAME = "private-separation-song-disjoint-pilot-execution.json"
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
QueueExecutor = Callable[..., Mapping[str, Any]]


def _execute_song_disjoint_private_pilot_request(
    request_report_path: str | Path,
    *,
    out_dir: str | Path | None,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str = "gpu",
    maximum_chunks: int | None = 1,
    preflight: bool = False,
    queue_executor: QueueExecutor = _execute_private_separation_full_song_queue,
) -> dict[str, Any]:
    """Remeasure, then preflight or execute the exact sealed request."""

    loaded = _load_verified_song_disjoint_private_pilot_request(
        request_report_path
    )
    document = loaded["document"]
    if (
        document.get("schema") != REQUEST_SCHEMA
        or document.get("policy_id") != REQUEST_POLICY_ID
    ):
        raise ValueError(
            "legacy private pilot request must be regenerated before execution"
        )
    if device != document.get("pilot", {}).get("device"):
        raise ValueError("private pilot request device differs")
    measured = _measure_request_execution_environment(
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    observed_environment = measured["execution_environment"]
    if observed_environment != document.get("execution_environment"):
        raise ValueError("private pilot request execution environment changed")
    binding = _private_pilot_request_binding(loaded)
    readiness = {
        "request_verified": True,
        "plan_verified": True,
        "execution_environment_reverified": True,
        "request_bound_execution_ready": True,
        "model_run_started_this_invocation": False,
        "all_worker_runs_complete": False,
        "human_review_complete": False,
        "separator_selected_or_accepted": False,
        "publication_ready": False,
    }
    if preflight:
        return {
            "schema": SCHEMA,
            "status": "request_bound_preflight_complete_no_model_run",
            "request_binding": binding,
            "readiness": readiness,
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {
                "execution_root_created": False,
                "model_run": False,
                "request_mutated": False,
                "review_mutated": False,
            },
        }
    if out_dir is None:
        raise ValueError("private pilot execution output directory is required")

    result = dict(
        queue_executor(
            loaded["plan_path"],
            out_dir=out_dir,
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
    readiness["model_run_started_this_invocation"] = (
        result.get("chunks_executed_this_invocation", 0) > 0
    )
    readiness["all_worker_runs_complete"] = result.get("summary", {}).get(
        "all_worker_runs_complete"
    ) is True
    final_report: str | None = None
    if readiness["all_worker_runs_complete"]:
        final_report = str(
            _write_or_verify_completion_binding(
                Path(out_dir).expanduser().absolute(),
                loaded=loaded,
                request_binding=binding,
                execution_state=result,
            )
        )
    elif os.path.lexists(Path(out_dir).expanduser().absolute() / REPORT_NAME):
        raise ValueError("private pilot completion binding exists before completion")
    return {
        "schema": SCHEMA,
        "status": result["status"],
        "request_binding": binding,
        "execution": result,
        "completion_binding_report": final_report,
        "readiness": readiness,
        "permissions": dict(_FALSE_PERMISSIONS),
    }


def _private_pilot_request_binding(
    loaded: Mapping[str, Any],
) -> dict[str, Any]:
    document = loaded["document"]
    environment = document["execution_environment"]
    return {
        "request_schema": document["schema"],
        "request_policy_id": document["policy_id"],
        "request_report_sha256": loaded["sha256"],
        "request_document_sha256": document["document_sha256"],
        "checkpoint_sha256": environment["checkpoint"]["sha256"],
        "source_manifest_sha256": environment["audited_source"][
            "manifest_sha256"
        ],
        "companion_manifest_sha256": environment[
            "companion_manifest_sha256"
        ],
        "worker_source_sha256": environment["worker_source"]["sha256"],
    }


def _load_verified_song_disjoint_private_pilot_completion_binding(
    value: str | Path,
    *,
    loaded_request: Mapping[str, Any],
    execution_report_path: str | Path,
) -> dict[str, Any]:
    """Load one complete request-to-execution binding without replaying it."""

    path = Path(value).expanduser().absolute()
    _require_private_regular(path, "private pilot completion binding")
    if path.name != REPORT_NAME:
        raise ValueError("private pilot completion binding filename differs")
    execution_report = Path(execution_report_path).expanduser().absolute()
    _require_private_regular(
        execution_report,
        "request-bound private full-song execution report",
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        execution_state = json.loads(execution_report.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private pilot completion binding JSON differs") from error
    expected_bindings = {
        **_private_pilot_request_binding(loaded_request),
        "plan_report_sha256": loaded_request["plan_sha256"],
        "plan_document_sha256": loaded_request["plan"]["document_sha256"],
        "execution_report_sha256": _sha256(execution_report),
        "execution_state_sha256": execution_state.get("state_sha256"),
    }
    if (
        not isinstance(document, dict)
        or document.get("schema") != SCHEMA
        or document.get("status") != STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("bindings") != expected_bindings
        or document.get("summary") != execution_state.get("summary")
        or document.get("summary", {}).get("all_worker_runs_complete") is not True
        or document.get("summary", {}).get("remaining_chunks") != 0
        or document.get("readiness")
        != {
            "request_bound_worker_runs_complete": True,
            "stitch_complete": False,
            "human_review_complete": False,
            "separator_selected_or_accepted": False,
            "publication_ready": False,
        }
        or document.get("permissions") != _FALSE_PERMISSIONS
    ):
        raise ValueError("private pilot completion binding differs")
    return {
        "path": path,
        "sha256": _sha256(path),
        "document": document,
        "execution_path": execution_report,
        "execution_sha256": _sha256(execution_report),
        "execution_document": execution_state,
    }


def _write_or_verify_completion_binding(
    root: Path,
    *,
    loaded: Mapping[str, Any],
    request_binding: Mapping[str, Any],
    execution_state: Mapping[str, Any],
) -> Path:
    execution_report = root / EXECUTION_REPORT_NAME
    _require_private_regular(
        execution_report,
        "request-bound private full-song execution report",
    )
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            **request_binding,
            "plan_report_sha256": loaded["plan_sha256"],
            "plan_document_sha256": loaded["plan"]["document_sha256"],
            "execution_report_sha256": _sha256(execution_report),
            "execution_state_sha256": execution_state["state_sha256"],
        },
        "summary": dict(execution_state["summary"]),
        "readiness": {
            "request_bound_worker_runs_complete": True,
            "stitch_complete": False,
            "human_review_complete": False,
            "separator_selected_or_accepted": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "limitations": [
            "This proves request and execution identity, not separator quality.",
            "Stitching, alignment checks and fresh song-specific listening remain required.",
            "No Simple, Studio, TUI, source-graph, download or publication route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    report = root / REPORT_NAME
    if os.path.lexists(report):
        _require_private_regular(report, "private pilot completion binding")
        try:
            persisted = json.loads(report.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("private pilot completion binding JSON differs") from error
        if persisted != document:
            raise ValueError("private pilot completion binding changed")
        return report
    payload = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
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
