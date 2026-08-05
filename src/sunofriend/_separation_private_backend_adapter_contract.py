"""Bind the private route design to one exact local backend environment.

The contract audits the existing Kim Vocal 2 runtime, checkpoint, companion
files and coordinator code.  It creates JSON only.  It accepts no song,
creates no audio, grants no execution permission and is unreachable from all
user-facing Sunofriend modes.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_plan import (
    MAXIMUM_SONG_SECONDS,
    MAXIMUM_SOURCE_BYTES,
    TARGET_SAMPLE_RATE,
)
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES
from ._separation_private_route_design import (
    _load_verified_private_separation_route_design,
)
from ._separation_song_disjoint_private_pilot_request import (
    _execution_environment_document,
    _measure_request_execution_environment,
)


SCHEMA = "sunofriend.private-separation-backend-adapter-contract.v1"
STATUS = "sealed_backend_adapter_contract_complete_no_model_run"
POLICY_ID = "private-kim-backend-adapter-contract-v1"
REPORT_NAME = "private-separation-backend-adapter-contract.json"
_FALSE_PERMISSIONS = {
    "additional_model_run": False,
    "automatic_selection": False,
    "checkpoint_distribution": False,
    "private_execution_request_available": False,
    "private_route_execution_available": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}
_EFFECTS = {
    "adapter_contract_created": True,
    "audio_created_or_mutated": False,
    "checkpoint_tensor_values_observed": False,
    "design_or_coverage_evidence_mutated": False,
    "filesystem_inputs_measured": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _build_private_separation_backend_adapter_contract(
    design_report_path: str | Path,
    *,
    coverage_report_path: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Audit one exact backend configuration and seal a model-free contract."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(
            f"private separation backend adapter filename must be {REPORT_NAME}"
        )
    if os.path.lexists(output):
        raise FileExistsError(f"private separation backend adapter exists: {output}")
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(
        output.parent,
        "private separation backend adapter root",
    )

    design = _load_verified_private_separation_route_design(
        design_report_path,
        coverage_report_path=coverage_report_path,
    )
    measured = _measure_request_execution_environment(
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    _require_output_disjoint(output, design=design, measured=measured)
    environment = measured.get("execution_environment") or (
        _execution_environment_document(measured)
    )
    document = _contract_document(design, environment=environment)
    document["document_sha256"] = _document_sha256(document)

    rechecked_design = _load_verified_private_separation_route_design(
        design_report_path,
        coverage_report_path=coverage_report_path,
    )
    rechecked_measured = _measure_request_execution_environment(
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    rechecked_environment = rechecked_measured.get("execution_environment") or (
        _execution_environment_document(rechecked_measured)
    )
    if (
        rechecked_design["sha256"] != design["sha256"]
        or rechecked_design["document"]["document_sha256"]
        != design["document"]["document_sha256"]
        or rechecked_environment != environment
    ):
        raise ValueError("private separation backend adapter inputs changed")
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _load_verified_private_separation_backend_adapter_contract(
    value: str | Path,
    *,
    design_report_path: str | Path,
    coverage_report_path: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
) -> dict[str, Any]:
    """Reconstruct one adapter contract from its evidence and environment."""

    snapshot = _load_private_json_snapshot(
        value,
        "private separation backend adapter contract",
    )
    design = _load_verified_private_separation_route_design(
        design_report_path,
        coverage_report_path=coverage_report_path,
    )
    measured = _measure_request_execution_environment(
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    environment = measured.get("execution_environment") or (
        _execution_environment_document(measured)
    )
    expected = _contract_document(design, environment=environment)
    expected["document_sha256"] = _document_sha256(expected)
    if snapshot["path"].name != REPORT_NAME or snapshot["document"] != expected:
        raise ValueError("private separation backend adapter contract differs")
    return {**snapshot, "design": design, "measured": measured}


def _contract_document(
    design: Mapping[str, Any],
    *,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    checkpoint = environment.get("checkpoint")
    audited_source = environment.get("audited_source")
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("tensor_values_observed") is not False
        or checkpoint.get("tensor_library_imported") is not False
        or not isinstance(audited_source, Mapping)
        or audited_source.get("status") != "verified_not_imported"
        or environment.get("offline_environment_required") is not True
    ):
        raise ValueError("private separation backend environment differs")
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "route_design_sha256": design["sha256"],
            "route_design_document_sha256": design["document"]["document_sha256"],
            "coverage_report_sha256": design["coverage"]["sha256"],
            "coverage_document_sha256": design["coverage"]["document"][
                "document_sha256"
            ],
        },
        "backend": {
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "role_contract": {
                "primary": ["vocals", "instrumental"],
                "diagnostic": ["reconstruction"],
            },
            "execution_environment": deepcopy(dict(environment)),
            "checkpoint_redistribution_authorized": False,
            "automatic_backend_fallback_permitted": False,
        },
        "future_request_contract": {
            "one_authorized_local_source_required": True,
            "source_sha256_required": True,
            "canonical_pcm24_identity_required": True,
            "checkpoint_sha256_required": True,
            "backend_environment_binding_required": True,
            "fresh_owner_only_output_required": True,
            "explicit_device_required": True,
            "implicit_network_or_download_permitted": False,
            "maximum_source_bytes": MAXIMUM_SOURCE_BYTES,
            "maximum_source_seconds": MAXIMUM_SONG_SECONDS,
            "target_sample_rate": TARGET_SAMPLE_RATE,
            "target_channels": 2,
            "maximum_chunk_frames": MAXIMUM_EXCERPT_FRAMES,
            "maximum_chunk_seconds": MAXIMUM_EXCERPT_FRAMES / TARGET_SAMPLE_RATE,
            "chunk_gap_frames": 0,
            "chunk_overlap_frames": 0,
        },
        "execution_boundary": {
            "adapter_may_validate_future_request": True,
            "adapter_may_construct_future_worker_invocations": True,
            "this_contract_is_an_execution_request": False,
            "this_contract_authorizes_model_execution": False,
            "this_contract_contains_source_audio": False,
            "this_contract_contains_model_tensor_values": False,
            "unreviewed_output_may_enter_source_graph": False,
            "reviewed_output_import_is_implemented": False,
        },
        "mode_isolation": deepcopy(design["document"]["mode_isolation"]),
        "readiness": {
            "coverage_and_route_design_verified": True,
            "exact_local_backend_environment_verified": True,
            "stage_1_sealed_backend_adapter_contract_complete": True,
            "next_stage": "implement_private_execution_request_builder",
            "private_execution_request_implemented": False,
            "private_model_execution_available": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "permissions": deepcopy(_FALSE_PERMISSIONS),
        "effects": deepcopy(_EFFECTS),
        "limitations": [
            "This record audits one exact local backend environment; it is not a song request.",
            "The checkpoint remains private evaluation material and is not redistributed.",
            "No checkpoint tensor values are read and no model library is imported by this contract builder.",
            "The next request-builder stage must separately bind an authorized source and fresh output root.",
            "No existing Simple, Studio, TUI, CLI, source-graph or download route can invoke this adapter.",
        ],
    }


def _require_output_disjoint(
    output: Path,
    *,
    design: Mapping[str, Any],
    measured: Mapping[str, Any],
) -> None:
    evidence_paths = {
        design["path"],
        design["coverage"]["path"],
        measured["checkpoint_path"],
        measured["runtime_launcher_path"],
    }
    evidence_roots = {
        measured["source_root"],
        measured["companion_root"],
    }
    if output in evidence_paths or any(root == output or root in output.parents for root in evidence_roots):
        raise ValueError("private separation backend adapter output overlaps evidence")


__all__: tuple[str, ...] = ()
