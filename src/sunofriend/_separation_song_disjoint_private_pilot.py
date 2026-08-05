"""Bind one source-distinct private separation pilot before human review.

The report joins an earlier pragmatic authorization to one fresh plan,
execution, stitch and alignment chain.  It proves that the pilot source audio
is byte-distinct from the source bound by the authorization and that the
automatic execution evidence is complete.  It deliberately leaves musical
quality, join acceptability and every public product permission unresolved.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_alignment import (
    POLICY_ID as ALIGNMENT_POLICY_ID,
    SCHEMA as ALIGNMENT_SCHEMA,
    STATUS as ALIGNMENT_STATUS,
)
from ._separation_full_song_executor import (
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    _load_verified_plan,
    _require_private_directory,
    _require_private_regular,
    _verify_completed_attempts,
    _verify_state_binding,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    REPORT_NAME as REFERENCE_EXECUTION_NAME,
    SCHEMA as REFERENCE_EXECUTION_SCHEMA,
    STATUS as REFERENCE_EXECUTION_STATUS,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_NAME,
    REVIEW_SCHEMA,
    _FALSE_PERMISSIONS,
    _immutable_review,
)
from ._separation_pragmatic_private_pilot import (
    _load_verified_pragmatic_private_pilot,
)


SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-evidence.v1"
STATUS = "automatic_pilot_evidence_complete_human_review_pending"
POLICY_ID = "source-distinct-pragmatic-private-pilot-binding-v1"
REPORT_NAME = "private-separation-song-disjoint-pilot-evidence.json"
_PLAN_POLICY_ID = "contiguous-canonical-44100-worker-chunks-v1"
_REFERENCE_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}
_EFFECTS = {
    "audio_created_or_mutated": False,
    "evidence_report_created": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _bind_song_disjoint_private_pilot_evidence(
    pragmatic_authorization_path: str | Path,
    *,
    reference_v2_execution_path: str | Path,
    plan_report_path: str | Path,
    execution_report_path: str | Path,
    stitch_package_dir: str | Path,
    alignment_result_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one path-free, no-overwrite automatic pilot evidence envelope."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"song-disjoint pilot filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"song-disjoint pilot evidence exists: {output}")
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(
        output.parent,
        "song-disjoint private pilot evidence directory",
    )

    context = _load_context(
        pragmatic_authorization_path,
        reference_v2_execution_path=reference_v2_execution_path,
        plan_report_path=plan_report_path,
        execution_report_path=execution_report_path,
        stitch_package_dir=stitch_package_dir,
        alignment_result_path=alignment_result_path,
    )
    _require_output_disjoint(output, context=context)

    authorization = context["authorization"]["document"]
    reference = context["reference"]["document"]
    plan = context["plan"]
    execution = context["execution"]["document"]
    stitch = context["stitch"]
    alignment = context["alignment"]["document"]
    seed = context["review_seed"]
    reference_source_sha256 = reference["bindings"]["source_audio_sha256"]
    pilot_source_sha256 = stitch["artifacts"]["source"]["sha256"]

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "pragmatic_authorization_sha256": context["authorization"]["sha256"],
            "pragmatic_authorization_document_sha256": authorization[
                "document_sha256"
            ],
            "reference_v2_execution_sha256": context["reference"]["sha256"],
            "reference_v2_execution_document_sha256": reference[
                "document_sha256"
            ],
            "reference_source_audio_sha256": reference_source_sha256,
            "pilot_plan_sha256": context["plan_sha256"],
            "pilot_plan_document_sha256": plan["document_sha256"],
            "pilot_execution_sha256": context["execution"]["sha256"],
            "pilot_execution_state_sha256": execution["state_sha256"],
            "pilot_stitch_sha256": context["stitch_sha256"],
            "pilot_stitch_document_sha256": stitch["document_sha256"],
            "pilot_alignment_sha256": context["alignment"]["sha256"],
            "pilot_alignment_document_sha256": alignment["document_sha256"],
            "pilot_source_audio_sha256": pilot_source_sha256,
            "pilot_review_seed_sha256": context["review_seed_sha256"],
            "pilot_review_package_commitment": seed["package_commitment"],
        },
        "authorization": {
            "policy_id": authorization["policy_id"],
            "bounded_private_pilot_ready": True,
            "selected_reference_candidate_identity": authorization[
                "selected_candidate"
            ]["identity"],
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "source_distinction": {
            "pilot_track_id": plan["corpus"]["track_id"],
            "pilot_track_title": plan["corpus"]["track_title"],
            "comparison": (
                "reference authorization source PCM24 WAV SHA-256 versus "
                "fresh pilot canonical source PCM24 WAV SHA-256"
            ),
            "reference_source_audio_sha256": reference_source_sha256,
            "pilot_source_audio_sha256": pilot_source_sha256,
            "byte_distinct": True,
            "song_disjoint_content_check_passed": True,
            "musical_identity_inferred_from_hash": False,
        },
        "automatic_execution": {
            "plan_policy_id": plan["policy_id"],
            "checkpoint_sha256": execution["bindings"]["checkpoint_sha256"],
            "chunk_count": len(plan["chunks"]),
            "verified_chunk_count": execution["summary"]["verified_chunks"],
            "worker_runs_complete": True,
            "stitch_complete": True,
            "clock": deepcopy(stitch["clock"]),
            "alignment_policy_id": alignment["policy_id"],
            "alignment_gate_passed": True,
            "alignment_summary": deepcopy(alignment["summary"]),
        },
        "human_review": {
            "status": "pending",
            "review_seed_status": seed["status"],
            "full_song_role_count": len(seed["full_song"]["audio"]) - 1,
            "boundary_count": len(seed["units"]),
            "package_commitment": seed["package_commitment"],
            "html_sha256": stitch["boundary_review"]["html_sha256"],
            "full_song_quality_conclusion_available": False,
            "boundary_acceptability_conclusion_available": False,
            "next_action": "complete_and_export_the_existing_local_review",
        },
        "readiness": {
            "authorization_bound": True,
            "source_distinct_from_authorization_reference": True,
            "automatic_execution_chain_verified": True,
            "exact_source_clock_verified": True,
            "alignment_gate_passed": True,
            "human_full_song_and_boundary_review_complete": False,
            "private_pilot_quality_conclusion_ready": False,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "interpretation": {
            "source_hash_distinction_is_musical_quality": False,
            "alignment_is_separator_accuracy": False,
            "automatic_evidence_is_human_listening": False,
            "pending_review_is_a_failed_review": False,
            "separator_selected_or_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS),
        "limitations": [
            "The hash comparison proves different bound source bytes, not musical identity or quality.",
            "Alignment proves source-clock synchronization, not vocal retention, bleed, artefact level or musical usefulness.",
            "The existing complete-song and 15-boundary listening review remains required.",
            "This report does not enable Simple, Studio, TUI, CLI, source-graph, download or publication routes.",
            "Private evidence files are rechecked serially rather than held as one atomic filesystem snapshot.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)

    rechecked = _load_context(
        pragmatic_authorization_path,
        reference_v2_execution_path=reference_v2_execution_path,
        plan_report_path=plan_report_path,
        execution_report_path=execution_report_path,
        stitch_package_dir=stitch_package_dir,
        alignment_result_path=alignment_result_path,
    )
    if _context_identity(rechecked) != _context_identity(context):
        raise ValueError("song-disjoint private pilot evidence changed")
    _write_json_exclusive(output, document)
    return {
        **document,
        "report": str(output),
        "review_html": str(
            context["stitch_package"] / stitch["boundary_review"]["html"]
        ),
    }


def _load_context(
    pragmatic_authorization_path: str | Path,
    *,
    reference_v2_execution_path: str | Path,
    plan_report_path: str | Path,
    execution_report_path: str | Path,
    stitch_package_dir: str | Path,
    alignment_result_path: str | Path,
) -> dict[str, Any]:
    authorization = _load_verified_pragmatic_private_pilot(
        pragmatic_authorization_path
    )
    reference = _load_reference_v2_execution(
        reference_v2_execution_path,
        authorization=authorization["document"],
    )
    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    if plan.get("policy_id") != _PLAN_POLICY_ID:
        raise ValueError("song-disjoint pilot plan policy differs")
    execution = _load_verified_execution(
        execution_report_path,
        plan=plan,
        plan_sha256=plan_sha256,
    )
    stitch_package = Path(stitch_package_dir).expanduser().absolute()
    _require_private_directory(stitch_package, "song-disjoint pilot stitch package")
    stitch_path = stitch_package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(stitch_package, stitch)
    _verify_stitch_chain(
        stitch,
        plan=plan,
        plan_sha256=plan_sha256,
        execution=execution["document"],
        execution_sha256=execution["sha256"],
    )
    alignment = _load_verified_alignment(
        alignment_result_path,
        stitch=stitch,
        stitch_sha256=_sha256(stitch_path),
    )
    seed, seed_sha256 = _load_verified_unreviewed_seed(stitch_package, stitch)
    reference_source = reference["document"]["bindings"].get(
        "source_audio_sha256"
    )
    pilot_source = stitch["artifacts"]["source"]["sha256"]
    if not _is_sha256(reference_source) or reference_source == pilot_source:
        raise ValueError("song-disjoint pilot source is not distinct")
    return {
        "authorization": authorization,
        "reference": reference,
        "plan_path": plan_path,
        "plan": plan,
        "plan_sha256": plan_sha256,
        "execution": execution,
        "stitch_package": stitch_package,
        "stitch_path": stitch_path,
        "stitch": stitch,
        "stitch_sha256": _sha256(stitch_path),
        "alignment": alignment,
        "review_seed": seed,
        "review_seed_sha256": seed_sha256,
    }


def _load_reference_v2_execution(
    value: str | Path,
    *,
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _load_private_json_snapshot(
        value,
        "pragmatic authorization reference v2 execution",
    )
    document = snapshot["document"]
    if (
        snapshot["path"].name != REFERENCE_EXECUTION_NAME
        or snapshot["sha256"]
        != authorization["bindings"].get("v2_execution_report_sha256")
        or document.get("schema") != REFERENCE_EXECUTION_SCHEMA
        or document.get("status") != REFERENCE_EXECUTION_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _REFERENCE_FALSE_PERMISSIONS
        or not _is_sha256(document.get("bindings", {}).get("source_audio_sha256"))
    ):
        raise ValueError("pragmatic authorization reference execution differs")
    selected = authorization["selected_candidate"]["artifacts"]
    clock = document.get("clock")
    if not isinstance(clock, Mapping) or any(
        selected[role]["geometry"].get(key) != clock.get(key)
        for role in ("vocals", "instrumental", "reconstruction")
        for key in ("sample_rate", "channels", "frames")
    ):
        raise ValueError("pragmatic authorization reference clock differs")
    return snapshot


def _load_verified_execution(
    value: str | Path,
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
) -> dict[str, Any]:
    snapshot = _load_private_json_snapshot(value, "song-disjoint pilot execution")
    document = snapshot["document"]
    if (
        snapshot["path"].name != EXECUTION_REPORT_NAME
        or document.get("schema") != EXECUTION_SCHEMA
        or document.get("status") != "private_chunk_execution_complete_not_selected"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("summary", {}).get("all_worker_runs_complete") is not True
        or document.get("summary", {}).get("remaining_chunks") != 0
        or document.get("summary", {}).get("verified_chunks") != len(plan["chunks"])
    ):
        raise ValueError("song-disjoint pilot execution differs")
    _verify_state_binding(document, plan=plan, plan_sha256=plan_sha256)
    _verify_completed_attempts(snapshot["path"].parent, document, plan)
    return snapshot


def _verify_stitch_chain(
    stitch: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
    execution: Mapping[str, Any],
    execution_sha256: str,
) -> None:
    bindings = stitch.get("bindings")
    clock = stitch.get("clock")
    if (
        not isinstance(bindings, Mapping)
        or bindings.get("plan_report_sha256") != plan_sha256
        or bindings.get("plan_document_sha256") != plan["document_sha256"]
        or bindings.get("execution_report_sha256") != execution_sha256
        or bindings.get("execution_state_sha256") != execution["state_sha256"]
        or bindings.get("canonical_pcm24_int32_sequence_sha256")
        != plan["canonical_clock"]["pcm24_int32_sequence_sha256"]
        or not isinstance(clock, Mapping)
        or clock.get("sample_rate") != plan["canonical_clock"]["sample_rate"]
        or clock.get("channels") != plan["canonical_clock"]["channels"]
        or clock.get("frames") != plan["canonical_clock"]["frames"]
        or clock.get("chunk_count") != len(plan["chunks"])
        or clock.get("boundary_count") != len(plan["chunks"]) - 1
        or clock.get("gap_frames") != 0
        or clock.get("overlap_frames") != 0
        or clock.get("crossfade_frames") != 0
    ):
        raise ValueError("song-disjoint pilot stitch binding differs")


def _load_verified_alignment(
    value: str | Path,
    *,
    stitch: Mapping[str, Any],
    stitch_sha256: str,
) -> dict[str, Any]:
    snapshot = _load_private_json_snapshot(value, "song-disjoint pilot alignment")
    document = snapshot["document"]
    bindings = document.get("bindings")
    if (
        document.get("schema") != ALIGNMENT_SCHEMA
        or document.get("status") != ALIGNMENT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != ALIGNMENT_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256") != stitch_sha256
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("source_audio_sha256")
        != stitch["artifacts"]["source"]["sha256"]
        or bindings.get("reconstruction_audio_sha256")
        != stitch["artifacts"]["reconstruction"]["sha256"]
        or bindings.get("plan_document_sha256")
        != stitch["bindings"]["plan_document_sha256"]
        or bindings.get("execution_state_sha256")
        != stitch["bindings"]["execution_state_sha256"]
        or document.get("clock") != stitch["clock"]
        or document.get("readiness", {}).get("alignment_gate_passed") is not True
        or document.get("readiness", {}).get("publication_ready") is not False
    ):
        raise ValueError("song-disjoint pilot alignment differs")
    return snapshot


def _load_verified_unreviewed_seed(
    package: Path,
    stitch: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    boundary = stitch.get("boundary_review")
    if not isinstance(boundary, Mapping):
        raise ValueError("song-disjoint pilot review binding differs")
    review_root = package / "BOUNDARY-REVIEW"
    _require_private_directory(review_root, "song-disjoint pilot review package")
    seed_path = review_root / REVIEW_NAME
    _require_private_regular(seed_path, "song-disjoint pilot review seed")
    html_path = review_root / "separation_boundary_review.html"
    _require_private_regular(html_path, "song-disjoint pilot review HTML")
    try:
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("song-disjoint pilot review seed differs") from error
    if (
        not isinstance(seed, dict)
        or seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != "unreviewed"
        or seed.get("evidence_scope") != "private_development_only"
        or seed.get("permissions") != _FALSE_PERMISSIONS
        or _sha256(seed_path) != boundary.get("seed_sha256")
        or _sha256(html_path) != boundary.get("html_sha256")
        or seed.get("package_commitment") != boundary.get("package_commitment")
        or seed.get("package_commitment")
        != hashlib.sha256(canonical_json_bytes(_immutable_review(seed))).hexdigest()
        or seed.get("summary")
        != {
            "boundary_count": stitch["clock"]["boundary_count"],
            "full_song_reviewed": False,
            "reviewed_boundaries": 0,
        }
        or not isinstance(seed.get("units"), list)
        or len(seed["units"]) != stitch["clock"]["boundary_count"]
    ):
        raise ValueError("song-disjoint pilot review seed differs")
    return seed, _sha256(seed_path)


def _context_identity(context: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        context["authorization"]["sha256"],
        context["reference"]["sha256"],
        context["plan_sha256"],
        context["execution"]["sha256"],
        context["stitch_sha256"],
        context["alignment"]["sha256"],
        context["review_seed_sha256"],
    )


def _require_output_disjoint(output: Path, *, context: Mapping[str, Any]) -> None:
    inputs = (
        context["authorization"]["path"],
        context["reference"]["path"],
        context["plan_path"],
        context["execution"]["path"],
        context["stitch_package"],
        context["alignment"]["path"],
    )
    for value in inputs:
        path = Path(value).resolve(strict=True)
        if output == path or path.is_dir() and path in output.parents:
            raise ValueError("song-disjoint pilot output overlaps private evidence")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__: tuple[str, ...] = ()
