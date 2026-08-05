"""Bind one authorised song plan to the sealed private separation adapter.

The request is path-free and model-free.  It reuses an already prepared,
verified, gap-free full-song plan and grants no execution permission.  A later
developer-only executor gate must reconstruct every binding before it may run
the model.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import (
    _load_verified_plan,
    _require_private_directory,
)
from ._separation_full_song_join_remediation_review_result import (
    _write_json_exclusive,
)
from ._separation_full_song_plan import (
    MAXIMUM_SONG_SECONDS,
    MAXIMUM_SOURCE_BYTES,
    POLICY_ID as PLAN_POLICY_ID,
)
from ._separation_private_backend_adapter_contract import (
    _load_verified_private_separation_backend_adapter_contract,
)


SCHEMA = "sunofriend.private-separation-execution-request.v1"
STATUS = "private_execution_request_prepared_no_model_run"
POLICY_ID = "authorized-plan-bound-private-separation-request-v1"
REPORT_NAME = "private-separation-execution-request.json"
_ROLES = ("vocals", "instrumental", "reconstruction")
_PLAN_PERMISSIONS = {
    "accepted": False,
    "automatic_promotion": False,
    "automatic_selection": False,
    "production_eligible": False,
    "public_result": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}
_PLAN_EFFECTS = {
    "authorisation_chunks_created": True,
    "canonical_chunk_audio_created": True,
    "model_run": False,
    "product_contract_mutated": False,
    "separator_output_created": False,
    "source_audio_mutated": False,
    "source_graph_mutated": False,
}
_FALSE_PERMISSIONS = {
    "automatic_selection": False,
    "private_model_execution_permitted": False,
    "private_output_import_permitted": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}
_EFFECTS = {
    "adapter_or_plan_mutated": False,
    "audio_created_or_mutated": False,
    "execution_request_created": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _build_private_separation_execution_request(
    adapter_report_path: str | Path,
    *,
    design_report_path: str | Path,
    coverage_report_path: str | Path,
    plan_report_path: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str,
    out: str | Path,
) -> dict[str, Any]:
    """Write one exact source-and-backend request without running a model."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("private separation request device must be gpu or cpu")
    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private separation request filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private separation request exists: {output}")
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "private separation request root")

    adapter = _load_adapter(
        adapter_report_path,
        design_report_path=design_report_path,
        coverage_report_path=coverage_report_path,
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    _validate_plan(plan)
    _require_output_disjoint(output, adapter=adapter, plan_path=plan_path)
    document = _request_document(
        adapter,
        plan=plan,
        plan_sha256=plan_sha256,
        device=device,
    )
    document["document_sha256"] = _document_sha256(document)

    rechecked_adapter = _load_adapter(
        adapter_report_path,
        design_report_path=design_report_path,
        coverage_report_path=coverage_report_path,
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    rechecked_plan_path, rechecked_plan, rechecked_plan_sha256 = (
        _load_verified_plan(plan_report_path)
    )
    if (
        rechecked_adapter["sha256"] != adapter["sha256"]
        or rechecked_adapter["document"]["document_sha256"]
        != adapter["document"]["document_sha256"]
        or rechecked_plan_path != plan_path
        or rechecked_plan_sha256 != plan_sha256
        or rechecked_plan != plan
    ):
        raise ValueError("private separation request inputs changed")
    _write_json_exclusive(output, document)
    return {**document, "report": str(output), "plan_report": str(plan_path)}


def _load_adapter(
    value: str | Path,
    **kwargs: str | Path,
) -> dict[str, Any]:
    return _load_verified_private_separation_backend_adapter_contract(
        value,
        **kwargs,
    )


def _validate_plan(plan: Mapping[str, Any]) -> None:
    corpus = plan.get("corpus")
    source = plan.get("source")
    canonical = plan.get("canonical_clock")
    chunking = plan.get("chunking")
    readiness = plan.get("readiness")
    if not all(
        isinstance(item, Mapping)
        for item in (corpus, source, canonical, chunking, readiness)
    ):
        raise ValueError("private separation plan fields differ")
    assert isinstance(corpus, Mapping)
    assert isinstance(source, Mapping)
    assert isinstance(canonical, Mapping)
    assert isinstance(chunking, Mapping)
    assert isinstance(readiness, Mapping)
    if (
        corpus.get("rights_authority")
        not in {
            "creator_and_copyright_holder",
            "user_authorised_private_local_evaluation",
        }
        or not _is_sha256(corpus.get("manifest_sha256"))
        or not _nonempty(corpus.get("track_id"))
        or not _nonempty(corpus.get("track_title"))
        or plan.get("policy_id") != PLAN_POLICY_ID
        or plan.get("permissions") != _PLAN_PERMISSIONS
        or plan.get("effects") != _PLAN_EFFECTS
        or source.get("bytes", MAXIMUM_SOURCE_BYTES + 1) > MAXIMUM_SOURCE_BYTES
        or not _is_sha256(source.get("sha256"))
        or canonical.get("sample_rate") != 44_100
        or canonical.get("channels") != 2
        or not _is_sha256(canonical.get("pcm24_int32_sequence_sha256"))
        or canonical.get("duration_seconds", MAXIMUM_SONG_SECONDS + 1)
        > MAXIMUM_SONG_SECONDS
        or chunking.get("gap_frames") != 0
        or chunking.get("overlap_frames") != 0
        or chunking.get("contiguous_exact_frame_coverage") is not True
        or readiness
        != {
            "chunk_authorisations_ready": True,
            "worker_runs_complete": False,
            "stitched_outputs_complete": False,
            "boundary_listening_complete": False,
            "full_song_duration_and_alignment_gate_passed": False,
            "resource_envelope_gate_passed": False,
            "publication_ready": False,
        }
    ):
        raise ValueError("private separation plan policy differs")


def _request_document(
    adapter: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
    device: str,
) -> dict[str, Any]:
    backend = adapter["document"]["backend"]
    environment = backend["execution_environment"]
    checkpoint = environment["checkpoint"]
    canonical = plan["canonical_clock"]
    chunking = plan["chunking"]
    source = plan["source"]
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "backend_adapter_sha256": adapter["sha256"],
            "backend_adapter_document_sha256": adapter["document"][
                "document_sha256"
            ],
            "route_design_sha256": adapter["design"]["sha256"],
            "route_design_document_sha256": adapter["design"]["document"][
                "document_sha256"
            ],
            "coverage_report_sha256": adapter["design"]["coverage"]["sha256"],
            "coverage_document_sha256": adapter["design"]["coverage"]["document"][
                "document_sha256"
            ],
            "plan_report_sha256": plan_sha256,
            "plan_document_sha256": plan["document_sha256"],
            "corpus_manifest_sha256": plan["corpus"]["manifest_sha256"],
            "source_audio_sha256": source["sha256"],
            "canonical_pcm24_int32_sequence_sha256": canonical[
                "pcm24_int32_sequence_sha256"
            ],
            "checkpoint_sha256": checkpoint["sha256"],
        },
        "request": {
            "track_id": plan["corpus"]["track_id"],
            "track_title": plan["corpus"]["track_title"],
            "rights_authority": plan["corpus"]["rights_authority"],
            "candidate_id": backend["candidate_id"],
            "device": device,
            "primary_roles": ["vocals", "instrumental"],
            "diagnostic_roles": ["reconstruction"],
            "source": {
                "bytes": source["bytes"],
                "extension": source["extension"],
                "geometry": deepcopy(source["geometry"]),
            },
            "canonical_clock": {
                "sample_rate": canonical["sample_rate"],
                "channels": canonical["channels"],
                "frames": canonical["frames"],
                "duration_seconds": canonical["duration_seconds"],
            },
            "chunking": {
                "chunk_count": chunking["chunk_count"],
                "maximum_chunk_frames": chunking["maximum_chunk_frames"],
                "maximum_chunk_seconds": chunking["maximum_chunk_seconds"],
                "gap_frames": chunking["gap_frames"],
                "overlap_frames": chunking["overlap_frames"],
            },
        },
        "future_execution_policy": {
            "explicit_developer_invocation_required": True,
            "fresh_owner_only_output_root_required": True,
            "overwrite_permitted": False,
            "implicit_network_or_download_permitted": False,
            "runtime_checkpoint_source_and_companions_must_be_reverified": True,
            "request_bound_resumable_chunks_required": True,
            "incomplete_attempts_are_diagnostic_only": True,
            "exact_stitch_and_alignment_required": True,
            "complete_song_and_boundary_review_required_before_handoff": True,
        },
        "mode_isolation": deepcopy(adapter["document"]["mode_isolation"]),
        "readiness": {
            "route_design_verified": True,
            "backend_adapter_verified": True,
            "authorized_full_song_plan_verified": True,
            "source_and_canonical_pcm_identity_bound": True,
            "private_execution_request_complete": True,
            "next_stage": "implement_separate_developer_only_execution_gate",
            "private_model_execution_permitted": False,
            "human_review_complete": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "permissions": deepcopy(_FALSE_PERMISSIONS),
        "effects": deepcopy(_EFFECTS),
        "limitations": [
            "This request reuses an existing canonical chunk plan and creates no audio.",
            "The request does not authorize model execution or name an execution output path.",
            "A later execution gate must reconstruct every evidence and environment binding.",
            "Separator output remains unreviewed private staging until exact listening review is complete.",
            "No Simple, Studio, TUI, public CLI, source-graph or download route can discover this request.",
        ],
    }


def _require_output_disjoint(
    output: Path,
    *,
    adapter: Mapping[str, Any],
    plan_path: Path,
) -> None:
    evidence_paths = {
        adapter["path"],
        adapter["design"]["path"],
        adapter["design"]["coverage"]["path"],
        plan_path,
    }
    if output in evidence_paths or plan_path.parent == output or plan_path.parent in output.parents:
        raise ValueError("private separation request output overlaps evidence")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__: tuple[str, ...] = ()
