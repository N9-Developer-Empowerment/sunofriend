"""Summarise reviewed private separation pilots without enabling a product route.

The pragmatic reference authorization and every source-distinct pilot already
carry their own human and automatic evidence.  This module verifies those
sealed contracts, exact private handoffs and distinct source hashes, then
writes one path-free coverage ledger.  It deliberately does not score, rank,
select or accept a separator.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_cross_song_evidence_index import _ID_PATTERN
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_stitch import _FALSE_PERMISSIONS
from ._separation_pragmatic_private_pilot import (
    _load_verified_pragmatic_private_pilot,
)
from ._separation_song_disjoint_private_pilot import (
    _load_verified_song_disjoint_private_pilot_evidence,
)
from ._separation_song_disjoint_private_pilot_handoff import (
    POLICY_ID as HANDOFF_POLICY_ID,
    REPORT_NAME as HANDOFF_REPORT_NAME,
    SCHEMA as HANDOFF_SCHEMA,
    STATUS as HANDOFF_STATUS,
)
from ._separation_song_disjoint_private_pilot_review import (
    POLICY_ID as REVIEW_POLICY_ID,
    REPORT_NAME as REVIEW_REPORT_NAME,
    RESULT_SCHEMA as REVIEW_SCHEMA,
    RESULT_STATUS_AUTHORIZED,
)


SCHEMA = "sunofriend.private-separation-multi-song-private-pilot-coverage.v1"
STATUS = "bounded_multi_song_private_pilot_evidence_complete_publication_blocked"
POLICY_ID = "distinct-source-reviewed-private-pilot-coverage-v1"
REPORT_NAME = "private-separation-multi-song-private-pilot-coverage.json"
_ROLES = ("vocals", "instrumental", "reconstruction")
_PRIMARY_ROLES = ("vocals", "instrumental")
_RATINGS = ("audible_join", "cannot_tell", "clean")
_REVIEW_PERMISSIONS = {
    **dict(_FALSE_PERMISSIONS),
    "bounded_private_pilot_output_use": True,
}
_REVIEW_EFFECTS = {
    "audio_created_or_mutated": False,
    "bounded_private_pilot_output_authorized": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_result_created": True,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}
_HANDOFF_PERMISSIONS = dict(_REVIEW_PERMISSIONS)
_HANDOFF_EFFECTS = {
    "audio_bytes_copied": True,
    "audio_sample_values_mutated": False,
    "handoff_created": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _build_multi_song_private_pilot_coverage(
    pragmatic_authorization_path: str | Path,
    *,
    pilots: Sequence[tuple[str | Path, str | Path, str | Path]],
    out: str | Path,
) -> dict[str, Any]:
    """Write one owner-only coverage ledger for one or more reviewed pilots."""

    if not pilots:
        raise ValueError("at least one song-disjoint private pilot is required")
    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"multi-song private pilot filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"multi-song private pilot coverage exists: {output}")
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "multi-song private pilot coverage root")

    context = _load_context(pragmatic_authorization_path, pilots=pilots)
    _require_output_disjoint(output, context=context)
    document = _coverage_document(context)
    document["document_sha256"] = _document_sha256(document)

    rechecked = _load_context(pragmatic_authorization_path, pilots=pilots)
    if _context_identity(rechecked) != _context_identity(context):
        raise ValueError("multi-song private pilot evidence changed")
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _load_context(
    pragmatic_authorization_path: str | Path,
    *,
    pilots: Sequence[tuple[str | Path, str | Path, str | Path]],
) -> dict[str, Any]:
    authorization = _load_verified_pragmatic_private_pilot(
        pragmatic_authorization_path
    )
    loaded = [
        _load_pilot_case(
            evidence_path,
            review_result_path=review_result_path,
            handoff_dir=handoff_dir,
            authorization=authorization,
        )
        for evidence_path, review_result_path, handoff_dir in pilots
    ]
    track_ids = [case["track_id"] for case in loaded]
    reference_hashes = {
        case["reference_source_audio_sha256"] for case in loaded
    }
    if len(reference_hashes) != 1:
        raise ValueError("song-disjoint pilots use different reference sources")
    source_hashes = [
        loaded[0]["reference_source_audio_sha256"],
        *(case["source_audio_sha256"] for case in loaded),
    ]
    if len(set(track_ids)) != len(track_ids):
        raise ValueError("song-disjoint private pilot track IDs are duplicated")
    if len(set(source_hashes)) != len(source_hashes):
        raise ValueError("multi-song private pilot sources are not all distinct")
    loaded.sort(key=lambda case: case["track_id"])
    return {"authorization": authorization, "pilots": loaded}


def _load_pilot_case(
    evidence_path: str | Path,
    *,
    review_result_path: str | Path,
    handoff_dir: str | Path,
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = _load_verified_song_disjoint_private_pilot_evidence(evidence_path)
    evidence_document = evidence["document"]
    evidence_bindings = evidence_document["bindings"]
    if (
        evidence_bindings["pragmatic_authorization_sha256"]
        != authorization["sha256"]
        or evidence_bindings["pragmatic_authorization_document_sha256"]
        != authorization["document"]["document_sha256"]
    ):
        raise ValueError("song-disjoint pilot uses a different authorization")

    review = _load_review_result(review_result_path, evidence=evidence)
    handoff = _load_handoff(
        handoff_dir,
        evidence=evidence,
        review=review,
    )
    distinction = evidence_document["source_distinction"]
    return {
        "evidence": evidence,
        "review": review,
        "handoff": handoff,
        "track_id": distinction["pilot_track_id"],
        "track_title": distinction["pilot_track_title"],
        "reference_source_audio_sha256": distinction[
            "reference_source_audio_sha256"
        ],
        "source_audio_sha256": distinction["pilot_source_audio_sha256"],
    }


def _load_review_result(
    value: str | Path,
    *,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _load_private_json_snapshot(
        value,
        "song-disjoint private pilot review result",
    )
    document = snapshot["document"]
    evidence_document = evidence["document"]
    evidence_bindings = evidence_document["bindings"]
    bindings = _mapping(document.get("bindings"), "private pilot review bindings")
    summary = _mapping(document.get("review_summary"), "private pilot review summary")
    assessment = _mapping(
        document.get("private_pilot_assessment"),
        "private pilot assessment",
    )
    readiness = _mapping(document.get("readiness"), "private pilot readiness")
    if (
        snapshot["path"].name != REVIEW_REPORT_NAME
        or document.get("schema") != REVIEW_SCHEMA
        or document.get("status") != RESULT_STATUS_AUTHORIZED
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != REVIEW_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _REVIEW_PERMISSIONS
        or document.get("effects") != _REVIEW_EFFECTS
        or bindings.get("pilot_evidence_sha256") != evidence["sha256"]
        or bindings.get("pilot_evidence_document_sha256")
        != evidence_document["document_sha256"]
        or bindings.get("pilot_stitch_sha256")
        != evidence_bindings["pilot_stitch_sha256"]
        or bindings.get("pilot_stitch_document_sha256")
        != evidence_bindings["pilot_stitch_document_sha256"]
        or bindings.get("pilot_review_seed_sha256")
        != evidence_bindings["pilot_review_seed_sha256"]
        or bindings.get("pilot_review_package_commitment")
        != evidence_bindings["pilot_review_package_commitment"]
        or document.get("clock") != evidence_document["automatic_execution"]["clock"]
        or assessment.get("all_generated_full_song_roles_useful") is not True
        or assessment.get("bounded_private_pilot_output_use_permitted") is not True
        or assessment.get("selection_scope")
        != "this_exact_reviewed_private_output_only"
        or assessment.get("boundary_findings_retained_as_diagnostics") is not True
        or assessment.get("boundary_findings_are_an_automatic_veto") is not False
        or assessment.get("model_run_required") is not False
        or assessment.get("next_action")
        != "continue_bounded_multi_song_private_evaluation"
        or readiness.get("automatic_pilot_evidence_complete") is not True
        or readiness.get("human_full_song_and_boundary_review_complete") is not True
        or readiness.get("whole_song_utility_conclusion_ready") is not True
        or readiness.get("bounded_private_pilot_output_use_permitted") is not True
        or readiness.get("separator_accuracy_ground_truth_established") is not False
        or readiness.get("public_product_acceptance_complete") is not False
        or readiness.get("publication_ready") is not False
    ):
        raise ValueError("song-disjoint private pilot review result differs")
    _validate_review_summary(summary)
    return snapshot


def _validate_review_summary(summary: Mapping[str, Any]) -> None:
    expected_keys = {
        "full_song_heard_all",
        "full_song_ratings",
        "reviewed_boundary_count",
        "boundary_rating_counts_by_role",
        "audible_join_boundaries_by_role",
        "cannot_tell_boundaries_by_role",
        "all_boundaries_clean",
        "listener_notes_copied",
    }
    ratings = _mapping(summary.get("full_song_ratings"), "full-song ratings")
    counts_by_role = _mapping(
        summary.get("boundary_rating_counts_by_role"),
        "boundary rating counts",
    )
    audible_by_role = _mapping(
        summary.get("audible_join_boundaries_by_role"),
        "audible join boundaries",
    )
    uncertain_by_role = _mapping(
        summary.get("cannot_tell_boundaries_by_role"),
        "uncertain boundaries",
    )
    boundary_count = summary.get("reviewed_boundary_count")
    if (
        set(summary) != expected_keys
        or summary.get("full_song_heard_all") is not True
        or set(ratings) != set(_ROLES)
        or any(ratings.get(role) != "useful" for role in _ROLES)
        or isinstance(boundary_count, bool)
        or not isinstance(boundary_count, int)
        or boundary_count < 1
        or set(counts_by_role) != set(_ROLES)
        or set(audible_by_role) != set(_ROLES)
        or set(uncertain_by_role) != set(_ROLES)
        or summary.get("listener_notes_copied") is not False
    ):
        raise ValueError("song-disjoint private pilot review summary differs")
    all_clean = True
    for role in _ROLES:
        counts = _mapping(counts_by_role[role], f"{role} boundary counts")
        audible = audible_by_role[role]
        uncertain = uncertain_by_role[role]
        if (
            set(counts) != set(_RATINGS)
            or any(
                isinstance(counts.get(rating), bool)
                or not isinstance(counts.get(rating), int)
                or counts[rating] < 0
                for rating in _RATINGS
            )
            or sum(counts.values()) != boundary_count
            or not _valid_boundary_indexes(
                audible,
                count=counts["audible_join"],
                maximum=boundary_count,
            )
            or not _valid_boundary_indexes(
                uncertain,
                count=counts["cannot_tell"],
                maximum=boundary_count,
            )
            or set(audible) & set(uncertain)
        ):
            raise ValueError("song-disjoint private pilot review summary differs")
        all_clean = all_clean and counts["clean"] == boundary_count
    if summary.get("all_boundaries_clean") is not all_clean:
        raise ValueError("song-disjoint private pilot review summary differs")


def _load_handoff(
    value: str | Path,
    *,
    evidence: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(value).expanduser().absolute()
    _require_private_directory(root, "song-disjoint private pilot handoff")
    report = root / HANDOFF_REPORT_NAME
    snapshot = _load_private_json_snapshot(report, "private pilot handoff manifest")
    document = snapshot["document"]
    evidence_document = evidence["document"]
    review_document = review["document"]
    bindings = _mapping(document.get("bindings"), "private pilot handoff bindings")
    handoff = _mapping(document.get("handoff"), "private pilot handoff policy")
    readiness = _mapping(document.get("readiness"), "private pilot handoff readiness")
    track = _mapping(document.get("track"), "private pilot handoff track")
    artifacts = _mapping(document.get("artifacts"), "private pilot handoff artifacts")
    expected_inventory = {"STEMS", "DIAGNOSTIC", HANDOFF_REPORT_NAME}
    if (
        set(path.name for path in root.iterdir()) != expected_inventory
        or document.get("schema") != HANDOFF_SCHEMA
        or document.get("status") != HANDOFF_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != HANDOFF_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _HANDOFF_PERMISSIONS
        or document.get("effects") != _HANDOFF_EFFECTS
        or bindings.get("pilot_evidence_sha256") != evidence["sha256"]
        or bindings.get("pilot_evidence_document_sha256")
        != evidence_document["document_sha256"]
        or bindings.get("review_result_sha256") != review["sha256"]
        or bindings.get("review_result_document_sha256")
        != review_document["document_sha256"]
        or bindings.get("review_export_sha256")
        != review_document["bindings"]["review_export_sha256"]
        or bindings.get("source_audio_sha256")
        != evidence_document["source_distinction"]["pilot_source_audio_sha256"]
        or bindings.get("stitch_report_sha256")
        != evidence_document["bindings"]["pilot_stitch_sha256"]
        or bindings.get("stitch_document_sha256")
        != evidence_document["bindings"]["pilot_stitch_document_sha256"]
        or document.get("clock") != review_document["clock"]
        or track.get("track_id")
        != evidence_document["source_distinction"]["pilot_track_id"]
        or track.get("track_title")
        != evidence_document["source_distinction"]["pilot_track_title"]
        or _ID_PATTERN.fullmatch(str(track.get("track_id"))) is None
        or not isinstance(track.get("track_title"), str)
        or not track["track_title"].strip()
        or handoff.get("kind") != "two_stem_vocals_and_instrumental"
        or handoff.get("primary_roles") != list(_PRIMARY_ROLES)
        or handoff.get("diagnostic_roles") != ["reconstruction"]
        or handoff.get("source_audio_included") is not False
        or handoff.get("audio_sample_values_changed") is not False
        or handoff.get("all_copies_match_reviewed_stitch_sha256") is not True
        or handoff.get("private_pilot_scope")
        != "this_exact_reviewed_output_only"
        or readiness.get("automatic_pilot_evidence_complete") is not True
        or readiness.get("human_review_complete") is not True
        or readiness.get("exact_output_authorized_for_bounded_private_pilot")
        is not True
        or readiness.get("two_stem_handoff_complete") is not True
        or readiness.get("separator_selected_or_accepted") is not False
        or readiness.get("public_product_acceptance_complete") is not False
        or readiness.get("publication_ready") is not False
        or set(artifacts) != set(_ROLES)
    ):
        raise ValueError("song-disjoint private pilot handoff differs")
    if document.get("human_review") != {
        "full_song_ratings": review_document["review_summary"]["full_song_ratings"],
        "reviewed_boundary_count": review_document["review_summary"][
            "reviewed_boundary_count"
        ],
        "audible_join_boundaries_by_role": review_document["review_summary"][
            "audible_join_boundaries_by_role"
        ],
        "cannot_tell_boundaries_by_role": review_document["review_summary"][
            "cannot_tell_boundaries_by_role"
        ],
        "listener_notes_copied": False,
    }:
        raise ValueError("song-disjoint private pilot handoff review differs")
    _verify_handoff_artifacts(root, artifacts=artifacts, clock=document["clock"])
    return {"root": root, **snapshot}


def _verify_handoff_artifacts(
    root: Path,
    *,
    artifacts: Mapping[str, Any],
    clock: Mapping[str, Any],
) -> None:
    expected_geometry = {
        "channels": clock.get("channels"),
        "frames": clock.get("frames"),
        "sample_rate": clock.get("sample_rate"),
        "sample_width_bytes": 3,
    }
    expected_paths = {
        "vocals": "STEMS/vocals.wav",
        "instrumental": "STEMS/instrumental.wav",
        "reconstruction": "DIAGNOSTIC/reconstruction.wav",
    }
    _require_private_directory(root / "STEMS", "private pilot handoff STEMS")
    _require_private_directory(
        root / "DIAGNOSTIC",
        "private pilot handoff DIAGNOSTIC",
    )
    if (
        set(path.name for path in (root / "STEMS").iterdir())
        != {"vocals.wav", "instrumental.wav"}
        or set(path.name for path in (root / "DIAGNOSTIC").iterdir())
        != {"reconstruction.wav"}
    ):
        raise ValueError("song-disjoint private pilot handoff inventory differs")
    for role in _ROLES:
        record = _mapping(artifacts[role], f"private pilot {role} artifact")
        relative = _safe_relative_path(record.get("path"), role=role)
        path = root.joinpath(*relative.parts)
        _require_private_regular(path, f"private pilot handoff {role}")
        if (
            record.get("path") != expected_paths[role]
            or record.get("geometry") != expected_geometry
            or record.get("copied_byte_identically") is not True
            or record.get("sample_values_changed") is not False
            or isinstance(record.get("bytes"), bool)
            or not isinstance(record.get("bytes"), int)
            or record["bytes"] <= 0
            or path.stat().st_size != record["bytes"]
            or _sha256(path) != record.get("sha256")
        ):
            raise ValueError("song-disjoint private pilot handoff artifact differs")


def _coverage_document(context: Mapping[str, Any]) -> dict[str, Any]:
    authorization = context["authorization"]
    authorization_document = authorization["document"]
    pilots = context["pilots"]
    reference_hash = pilots[0]["reference_source_audio_sha256"]
    cases = [
        {
            "case_kind": "pragmatic_reference",
            "source_audio_sha256": reference_hash,
            "authorization_sha256": authorization["sha256"],
            "authorization_document_sha256": authorization_document[
                "document_sha256"
            ],
            "selected_candidate_identity": authorization_document[
                "selected_candidate"
            ]["identity"],
            "available_roles": list(_ROLES),
            "pragmatic_whole_song_utility_gate_passed": True,
            "role_specific_full_song_review_supplied": False,
            "exact_two_stem_handoff_supplied": False,
        }
    ]
    total_boundaries = 0
    rating_totals = {rating: 0 for rating in _RATINGS}
    for case in pilots:
        evidence = case["evidence"]
        review = case["review"]
        handoff = case["handoff"]
        summary = review["document"]["review_summary"]
        total_boundaries += summary["reviewed_boundary_count"]
        for role in _ROLES:
            for rating in _RATINGS:
                rating_totals[rating] += summary["boundary_rating_counts_by_role"][
                    role
                ][rating]
        cases.append(
            {
                "case_kind": "reviewed_song_disjoint_pilot",
                "track_id": case["track_id"],
                "track_title": case["track_title"],
                "source_audio_sha256": case["source_audio_sha256"],
                "evidence_sha256": evidence["sha256"],
                "evidence_document_sha256": evidence["document"][
                    "document_sha256"
                ],
                "review_result_sha256": review["sha256"],
                "review_result_document_sha256": review["document"][
                    "document_sha256"
                ],
                "handoff_manifest_sha256": handoff["sha256"],
                "handoff_manifest_document_sha256": handoff["document"][
                    "document_sha256"
                ],
                "duration_seconds": review["document"]["clock"][
                    "duration_seconds"
                ],
                "reviewed_boundary_count": summary["reviewed_boundary_count"],
                "full_song_ratings": deepcopy(summary["full_song_ratings"]),
                "audible_join_boundaries_by_role": deepcopy(
                    summary["audible_join_boundaries_by_role"]
                ),
                "cannot_tell_boundaries_by_role": deepcopy(
                    summary["cannot_tell_boundaries_by_role"]
                ),
                "exact_two_stem_handoff_complete": True,
                "audio_sample_values_changed_in_handoff": False,
            }
        )

    pilot_count = len(pilots)
    private_route_design_checkpoint = pilot_count >= 2
    next_action = (
        "assess_a_separately_bounded_private_only_integration_design"
        if private_route_design_checkpoint
        else "run_and_review_at_least_one_additional_song_disjoint_private_pilot"
    )
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "coverage": {
            "reference_case_count": 1,
            "song_disjoint_pilot_count": pilot_count,
            "distinct_source_count": pilot_count + 1,
            "all_source_hashes_distinct": True,
            "all_song_disjoint_pilots_automatic_chain_verified": True,
            "all_song_disjoint_pilots_full_song_reviewed": True,
            "all_song_disjoint_pilots_full_song_roles_useful": True,
            "all_song_disjoint_pilots_two_stem_handoff_complete": True,
            "reviewed_song_disjoint_boundary_count": total_boundaries,
            "reviewed_role_boundary_judgement_count": total_boundaries
            * len(_ROLES),
            "boundary_rating_totals": rating_totals,
        },
        "cases": cases,
        "private_evaluation_checkpoint": {
            "two_distinct_source_evidence_checkpoint_met": True,
            "minimum_song_disjoint_pilots_before_private_route_design": 2,
            "private_route_design_checkpoint_met": private_route_design_checkpoint,
            "next_action": next_action,
        },
        "interpretation": {
            "two_distinct_sources_are_general_separator_acceptance": False,
            "useful_full_song_ratings_are_ground_truth_accuracy": False,
            "boundary_counts_are_a_quality_score": False,
            "inferential_statistics_permitted_for_this_small_nonrandom_set": False,
            "handoff_completion_is_product_integration": False,
            "separator_selected_or_accepted": False,
        },
        "permissions": {
            "additional_model_run": False,
            "automatic_selection": False,
            "product_route_permitted": False,
            "publication_permitted": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
            "tui_route_available": False,
        },
        "effects": {
            "audio_created_or_mutated": False,
            "coverage_report_created": True,
            "human_review_completed_or_mutated": False,
            "model_run": False,
            "product_contract_mutated": False,
            "publication_state_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This report verifies existing private evidence and exact handoffs; it does not inspect musical quality independently.",
            "The pragmatic reference and song-disjoint review use related but intentionally different human-review contracts.",
            "Two distinct owned songs demonstrate repeatability only for this bounded private evidence, not general separator accuracy.",
            "Boundary totals are descriptive counts from one listener, not normally distributed measurements or confidence intervals.",
            (
                "The current evidence has not yet reached the two-song-disjoint-pilot checkpoint required before designing even a private-only product route."
                if not private_route_design_checkpoint
                else "Reaching the private-route design checkpoint does not itself authorize or implement a private product route."
            ),
            "Public CLI, TUI, Simple, Studio, source-graph, download and publication routes remain disabled.",
        ],
    }


def _context_identity(context: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        context["authorization"]["sha256"],
        context["authorization"]["document"]["document_sha256"],
        tuple(
            (
                case["track_id"],
                case["source_audio_sha256"],
                case["evidence"]["sha256"],
                case["review"]["sha256"],
                case["handoff"]["sha256"],
            )
            for case in context["pilots"]
        ),
    )


def _require_output_disjoint(
    output: Path,
    *,
    context: Mapping[str, Any],
) -> None:
    evidence_paths = [context["authorization"]["path"]]
    handoff_roots = []
    for case in context["pilots"]:
        evidence_paths.extend(
            (
                case["evidence"]["path"],
                case["review"]["path"],
                case["handoff"]["path"],
            )
        )
        handoff_roots.append(case["handoff"]["root"])
    if any(output == Path(path).resolve(strict=True) for path in evidence_paths):
        raise ValueError("multi-song private pilot output overlaps evidence")
    if any(root == output or root in output.parents for root in handoff_roots):
        raise ValueError("multi-song private pilot output overlaps handoff")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} differs")
    return value


def _valid_boundary_indexes(value: Any, *, count: int, maximum: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == count
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
        and value == sorted(set(value))
        and all(1 <= item <= maximum for item in value)
    )


def _safe_relative_path(value: Any, *, role: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ValueError(f"private pilot {role} artifact path differs")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ValueError(f"private pilot {role} artifact path differs")
    return relative


__all__: tuple[str, ...] = ()
