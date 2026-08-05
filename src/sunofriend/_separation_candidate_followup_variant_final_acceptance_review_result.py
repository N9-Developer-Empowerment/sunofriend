"""Verify and resolve independent final-acceptance review exports.

Every eligible variant has its own whole-song page.  This module requires the
complete emitted review set and maps browser exports by their immutable package
commitments, not by filename or caller order.  It records explicit private-
pilot acceptance independently for each variant without ranking, selecting,
activating or publishing a separator.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_followup_variant_final_acceptance_review import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
    REVIEW_HTML_NAME,
    REVIEW_SCHEMA,
    REVIEW_SEED_NAME,
    REVIEW_STATUS,
    SCHEMA as PACKAGE_SCHEMA,
    STATUS as PACKAGE_STATUS,
    _PACKAGE_EFFECTS,
    _QUESTION_SPECS,
    _REVIEW_EFFECTS,
    _ROLES,
    _eligible_variant_ids,
    _review_html,
    _review_seed,
    _verified_exact_readiness,
    _verified_full_song_package,
    _verified_full_song_result,
)
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _browser_json_equal,
    _load_private_json_snapshot,
    _write_json_exclusive,
)


STATUS_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "final-acceptance-review-status.v1"
)
RESULT_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "final-acceptance-review-result.v1"
)
RESULT_STATUS = "complete_independent_final_acceptance_reviews_no_activation"
_MAXIMUM_NOTES_CHARACTERS = 2_000
_PACKAGE_READINESS = {
    "final_human_acceptance_review_package_complete": True,
    "final_human_acceptance_reviews_complete": False,
    "variant_selected": False,
    "separator_accepted": False,
    "original_audible_joins_resolved": False,
    "product_route_enabled": False,
    "publication_ready": False,
}
_ITEM_READINESS = {
    "independent_final_acceptance_review_complete": False,
    "selected": False,
    "accepted": False,
    "product_route_enabled": False,
    "publication_ready": False,
}
_PACKAGE_INTERPRETATION = {
    "every_eligible_variant_included": True,
    "reviews_are_independent_not_comparative": True,
    "package_order_is_preference": False,
    "automatic_winner_selected": False,
    "package_creation_is_acceptance": False,
}
_PACKAGE_LIMITATIONS = [
    "Each eligible variant is reviewed independently; this package is not a ranking exercise.",
    "The source and candidate audio are exact private copies of previously verified PCM24 evidence.",
    "Package creation records no human answer and accepts or selects no variant.",
    "Even a later private-pilot acceptance cannot by itself enable a product route or publication.",
    "Keep every evidence tree quiescent because JSON and WAV inputs are not one atomic snapshot.",
]
_STATUS_EFFECTS = {
    "acceptance_record_created": False,
    "audio_created_or_mutated": False,
    "candidate_accepted_for_private_pilot": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_graph_mutated": False,
}


def _status_private_candidate_followup_variant_final_acceptance_reviews(
    reviewed_export_paths: Sequence[str | Path], **kwargs: Any
) -> dict[str, Any]:
    """Verify every required reviewed export without writing a result."""

    context = _load_completed_reviews(reviewed_export_paths, **kwargs)
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_set_verified_no_activation",
        "evidence_scope": "private_development_only",
        "bindings": _result_bindings(context),
        "reviewed_variant_ids": list(context["eligible_variant_ids"]),
        "reviewed_variant_count": len(context["completed_reviews"]),
        "required_review_count": context["package_report"]["required_review_count"],
        "answered_questions_by_variant": {
            item["variant_id"]: item["review_snapshot"]["document"]["summary"][
                "answered_questions"
            ]
            for item in context["completed_reviews"]
        },
        "answer_interpretation_performed": False,
        "automatic_winner_selected": False,
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_STATUS_EFFECTS),
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_candidate_followup_variant_final_acceptance_reviews(
    reviewed_export_paths: Sequence[str | Path],
    *,
    out: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Write a fresh private result for the complete independent review set."""

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private final acceptance review result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(
            f"private final acceptance review result already exists: {output}"
        )
    context = _load_completed_reviews(reviewed_export_paths, **kwargs)
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["package_root"],
            context["alignment_root"],
            context["full_song_root"],
            context["variant_review_root"],
            context["execution_root"],
            context["v2_execution_root"],
            context["variant_execution_root"],
            context["stitch_root"],
        ),
        evidence_paths=(
            context["readiness_snapshot"]["path"],
            context["full_song_result_snapshot"]["path"],
            context["full_song_package_snapshot"]["path"],
            context["package_snapshot"]["path"],
            context["variant_review_result_path"],
            context["variant_reviewed_export_path"],
            context["plan_path"],
            *(Path(path).expanduser().absolute() for path in context["full_song_exports"]),
            *(item["review_snapshot"]["path"] for item in context["completed_reviews"]),
        ),
    )
    result = _resolved_result_document(context)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        _reverify_completed_reviews(context)
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _resolved_result_document(context: Mapping[str, Any]) -> dict[str, Any]:
    variant_results: list[dict[str, Any]] = []
    accepted_ids: list[str] = []
    for item in context["completed_reviews"]:
        review = item["review_snapshot"]["document"]
        ratings = deepcopy(review["ratings"])
        negative = [
            question["id"]
            for question in _QUESTION_SPECS
            if ratings[question["id"]] in {"no", "needs_more_work"}
        ]
        uncertain = [
            question["id"]
            for question in _QUESTION_SPECS
            if ratings[question["id"]] == "cannot_tell"
        ]
        accepted = (
            ratings["vocals_useful_for_melody_workflow"] == "yes"
            and ratings["instrumental_useful_for_midi_workflow"] == "yes"
            and ratings["reconstruction_continuous_and_synchronised"] == "yes"
            and ratings["candidate_suitable_for_private_pilot"]
            == "accept_private_pilot"
        )
        if accepted:
            accepted_ids.append(item["variant_id"])
        variant_results.append(
            {
                "review_id": item["package_item"]["review_id"],
                "variant_id": item["variant_id"],
                "heard": deepcopy(review["heard"]),
                "ratings": ratings,
                "notes": review["notes"],
                "decision_evidence": {
                    "accepted_for_private_pilot": accepted,
                    "negative_answer_ids": negative,
                    "uncertain_answer_ids": uncertain,
                    "all_required_answers_affirmative": accepted,
                },
                "readiness": {
                    "independent_final_acceptance_review_complete": True,
                    "accepted_for_private_pilot": accepted,
                    "selected": False,
                    "separator_activated": False,
                    "original_audible_joins_resolved": False,
                    "product_route_enabled": False,
                    "publication_ready": False,
                },
            }
        )
    any_accepted = bool(accepted_ids)
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": _result_bindings(context),
        "clock": deepcopy(context["package_report"]["clock"]),
        "reviewed_variant_ids": list(context["eligible_variant_ids"]),
        "reviewed_variant_count": len(variant_results),
        "variant_results": variant_results,
        "private_pilot_acceptance": {
            "accepted_variant_ids": accepted_ids,
            "accepted_variant_count": len(accepted_ids),
            "zero_one_or_multiple_acceptances_allowed": True,
            "variant_selected": False,
            "separator_accepted_as_product_default": False,
            "original_audible_joins_resolved": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
        "next_action": (
            "reassess_private_separation_publication_readiness_without_product_activation"
            if any_accepted
            else "return_to_bounded_remediation"
        ),
        "interpretation": {
            "answers_are_explicit_human_private_pilot_evidence": True,
            "negative_and_uncertain_answers_preserved": True,
            "variants_remain_independent": True,
            "package_order_is_preference": False,
            "automatic_winner_selected": False,
            "private_pilot_acceptance_is_product_activation": False,
            "private_pilot_acceptance_is_publication_permission": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            **dict(_STATUS_EFFECTS),
            "acceptance_record_created": True,
            "candidate_accepted_for_private_pilot": any_accepted,
        },
        "limitations": [
            "Each decision applies only to the exact independently reviewed private candidate.",
            "No accepted candidate is ranked above or selected instead of another candidate.",
            "Private-pilot acceptance does not resolve publication readiness or enable Simple, Studio, CLI, TUI or source-graph separation.",
            "Keep every evidence tree quiescent because JSON and WAV inputs are not one atomic snapshot.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    return result


def _load_completed_reviews(
    reviewed_export_paths: Sequence[str | Path],
    **kwargs: Any,
) -> dict[str, Any]:
    if isinstance(reviewed_export_paths, (str, bytes, Path)):
        raise TypeError("reviewed_export_paths must be the complete review sequence")
    supplied = list(reviewed_export_paths)
    if not supplied:
        raise ValueError("no final acceptance reviews supplied")
    context = _load_verified_package(**kwargs)
    if len(supplied) != len(context["eligible_variant_ids"]):
        raise ValueError("complete final acceptance review set is required")

    by_commitment: dict[str, dict[str, Any]] = {}
    for item in context["package_items"]:
        commitment = item["seed_snapshot"]["document"]["package_commitment"]
        if commitment in by_commitment:
            raise ValueError("final acceptance package commitment is duplicated")
        by_commitment[commitment] = item

    completed_by_variant: dict[str, dict[str, Any]] = {}
    seen_paths: set[Path] = set()
    for value in supplied:
        snapshot = _load_private_json_snapshot(
            value, "reviewed final acceptance export"
        )
        if snapshot["path"] in seen_paths:
            raise ValueError("final acceptance review export is duplicated")
        seen_paths.add(snapshot["path"])
        review = snapshot["document"]
        matched = by_commitment.get(review.get("package_commitment"))
        if matched is None:
            raise ValueError("final acceptance review export does not belong to package")
        variant_id = matched["variant_id"]
        if variant_id in completed_by_variant:
            raise ValueError("final acceptance review export is duplicated")
        seed = matched["seed_snapshot"]["document"]
        if not _browser_json_equal(
            _immutable_review(review), _immutable_review(seed)
        ):
            raise ValueError("final acceptance review changed immutable evidence")
        _validate_completed_review(review)
        completed_by_variant[variant_id] = {
            **matched,
            "review_snapshot": snapshot,
        }
    if set(completed_by_variant) != set(context["eligible_variant_ids"]):
        raise ValueError("complete final acceptance review set is required")
    context["completed_reviews"] = [
        completed_by_variant[variant_id]
        for variant_id in context["eligible_variant_ids"]
    ]
    _reverify_completed_reviews(context)
    return context


def _load_verified_package(
    *,
    review_package_dir: str | Path,
    readiness_result_path: str | Path,
    full_song_review_result_path: str | Path,
    alignment_package_dir: str | Path,
    full_song_review_export_paths: Sequence[str | Path],
    full_song_review_package_dir: str | Path,
    variant_review_result_path: str | Path,
    variant_reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
) -> dict[str, Any]:
    import soundfile

    if isinstance(full_song_review_export_paths, (str, bytes, Path)):
        raise TypeError(
            "full_song_review_export_paths must be the complete review sequence"
        )
    full_song_exports = list(full_song_review_export_paths)
    if not full_song_exports:
        raise ValueError("no eligible-variant full-song reviews supplied")
    package_root = Path(review_package_dir).expanduser().absolute()
    alignment_root = Path(alignment_package_dir).expanduser().absolute()
    full_song_root = Path(full_song_review_package_dir).expanduser().absolute()
    variant_review_root = Path(variant_review_package_dir).expanduser().absolute()
    execution_root = Path(execution_dir).expanduser().absolute()
    v2_execution_root = Path(v2_execution_dir).expanduser().absolute()
    variant_execution_root = Path(variant_execution_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    for root, label in (
        (package_root, "private final acceptance review package"),
        (alignment_root, "private eligible-variant alignment package"),
        (full_song_root, "private eligible-variant full-song review package"),
        (variant_review_root, "private follow-up variant review package"),
    ):
        _require_private_directory(root, label)

    reassessment_kwargs = {
        "alignment_package_dir": alignment_root,
        "full_song_review_export_paths": full_song_exports,
        "full_song_review_package_dir": full_song_root,
        "variant_review_result_path": variant_review_result_path,
        "variant_reviewed_export_path": variant_reviewed_export_path,
        "variant_review_package_dir": variant_review_root,
        "plan_path": plan_path,
        "execution_dir": execution_root,
        "v2_execution_dir": v2_execution_root,
        "variant_execution_dir": variant_execution_root,
        "stitch_package_dir": stitch_root,
    }
    readiness_snapshot, readiness = _verified_exact_readiness(
        readiness_result_path,
        full_song_review_result_path=full_song_review_result_path,
        reassessment_kwargs=reassessment_kwargs,
    )
    eligible_ids = _eligible_variant_ids(readiness)
    full_song_result_snapshot, full_song_result = _verified_full_song_result(
        full_song_review_result_path, readiness=readiness
    )
    full_song_package_snapshot, full_song_package = _verified_full_song_package(
        full_song_root,
        readiness=readiness,
        full_song_result=full_song_result,
        soundfile=soundfile,
    )
    package_snapshot = _load_private_json_snapshot(
        package_root / PACKAGE_REPORT_NAME,
        "private final acceptance review package report",
    )
    package_report = package_snapshot["document"]
    package_items = _verify_package(
        package_root,
        package_report,
        readiness=readiness,
        readiness_snapshot=readiness_snapshot,
        full_song_result=full_song_result,
        full_song_package=full_song_package,
        full_song_package_snapshot=full_song_package_snapshot,
        eligible_ids=eligible_ids,
    )
    return {
        "package_root": package_root,
        "alignment_root": alignment_root,
        "full_song_root": full_song_root,
        "variant_review_root": variant_review_root,
        "execution_root": execution_root,
        "v2_execution_root": v2_execution_root,
        "variant_execution_root": variant_execution_root,
        "stitch_root": stitch_root,
        "readiness_snapshot": readiness_snapshot,
        "readiness": readiness,
        "full_song_result_snapshot": full_song_result_snapshot,
        "full_song_result": full_song_result,
        "full_song_package_snapshot": full_song_package_snapshot,
        "full_song_package": full_song_package,
        "package_snapshot": package_snapshot,
        "package_report": package_report,
        "package_items": package_items,
        "eligible_variant_ids": eligible_ids,
        "full_song_exports": full_song_exports,
        "variant_review_result_path": Path(variant_review_result_path)
        .expanduser()
        .absolute(),
        "variant_reviewed_export_path": Path(variant_reviewed_export_path)
        .expanduser()
        .absolute(),
        "plan_path": Path(plan_path).expanduser().absolute(),
        "verification_kwargs": {
            "review_package_dir": package_root,
            "readiness_result_path": readiness_snapshot["path"],
            "full_song_review_result_path": full_song_result_snapshot["path"],
            "alignment_package_dir": alignment_root,
            "full_song_review_export_paths": full_song_exports,
            "full_song_review_package_dir": full_song_root,
            "variant_review_result_path": variant_review_result_path,
            "variant_reviewed_export_path": variant_reviewed_export_path,
            "variant_review_package_dir": variant_review_root,
            "plan_path": plan_path,
            "execution_dir": execution_root,
            "v2_execution_dir": v2_execution_root,
            "variant_execution_dir": variant_execution_root,
            "stitch_package_dir": stitch_root,
        },
    }


def _verify_package(
    package_root: Path,
    report: Mapping[str, Any],
    *,
    readiness: Mapping[str, Any],
    readiness_snapshot: Mapping[str, Any],
    full_song_result: Mapping[str, Any],
    full_song_package: Mapping[str, Any],
    full_song_package_snapshot: Mapping[str, Any],
    eligible_ids: list[str],
) -> list[dict[str, Any]]:
    expected_bindings = {
        "readiness_result_sha256": readiness_snapshot["sha256"],
        "readiness_result_document_sha256": readiness["document_sha256"],
        "variant_full_song_review_result_sha256": readiness["bindings"][
            "variant_full_song_review_result_sha256"
        ],
        "variant_alignment_package_sha256": readiness["bindings"][
            "variant_alignment_package_sha256"
        ],
        "full_song_review_package_sha256": full_song_package_snapshot["sha256"],
        "full_song_review_package_document_sha256": full_song_package[
            "document_sha256"
        ],
    }
    if (
        report.get("schema") != PACKAGE_SCHEMA
        or report.get("status") != PACKAGE_STATUS
        or report.get("evidence_scope") != "private_development_only"
        or report.get("bindings") != expected_bindings
        or report.get("clock") != readiness.get("clock")
        or report.get("eligible_variant_ids") != eligible_ids
        or report.get("eligible_variant_count") != len(eligible_ids)
        or report.get("required_review_count") != len(eligible_ids)
        or report.get("readiness") != _PACKAGE_READINESS
        or report.get("next_action")
        != "complete_every_independent_final_acceptance_review"
        or report.get("interpretation") != _PACKAGE_INTERPRETATION
        or report.get("permissions") != _FALSE_PERMISSIONS
        or report.get("effects") != _PACKAGE_EFFECTS
        or report.get("limitations") != _PACKAGE_LIMITATIONS
        or report.get("document_sha256") != _document_sha256(report)
        or full_song_result.get("reviewed_variant_ids")
        != readiness.get("reviewed_variant_ids")
    ):
        raise ValueError("private final acceptance review package differs")
    raw_items = report.get("reviews")
    if not isinstance(raw_items, list) or len(raw_items) != len(eligible_ids):
        raise ValueError("private final acceptance review inventory differs")
    full_song_by_variant = {
        item["variant_id"]: item for item in full_song_package["variant_packages"]
    }
    verified: list[dict[str, Any]] = []
    expected_items: list[dict[str, Any]] = []
    for index, (item, variant_id) in enumerate(zip(raw_items, eligible_ids), start=1):
        if not isinstance(item, Mapping):
            raise ValueError("private final acceptance review inventory differs")
        review_root = package_root / f"candidate-{index:02d}"
        _require_private_directory(review_root, "private final acceptance review root")
        source_item = full_song_by_variant.get(variant_id)
        if source_item is None:
            raise ValueError("private final acceptance review inventory differs")
        expected_audio: dict[str, Any] = {}
        for role in _ROLES:
            source = source_item["artifacts"][role]
            record = {
                "path": f"audio/{role}.wav",
                "sha256": source["sha256"],
                "bytes": source["bytes"],
                "geometry": dict(source["geometry"]),
                "pcm24_int32_sequence_sha256": source[
                    "pcm24_int32_sequence_sha256"
                ],
            }
            _read_pcm24_snapshot(
                review_root / record["path"],
                record,
                expected_frames=int(report["clock"]["frames"]),
                label=f"private final acceptance packaged {role} audio",
            )
            expected_audio[role] = record
        expected_seed_runtime = _review_seed(
            review_id=f"final-acceptance-{index:02d}",
            candidate_label=f"Candidate {index} of {len(eligible_ids)}",
            audio=expected_audio,
            bindings={
                "readiness_result_sha256": readiness_snapshot["sha256"],
                "readiness_result_document_sha256": readiness["document_sha256"],
                "full_song_review_package_sha256": full_song_package_snapshot[
                    "sha256"
                ],
                "full_song_review_package_document_sha256": full_song_package[
                    "document_sha256"
                ],
                "variant_full_song_review_result_sha256": readiness["bindings"][
                    "variant_full_song_review_result_sha256"
                ],
                "variant_alignment_package_sha256": readiness["bindings"][
                    "variant_alignment_package_sha256"
                ],
            },
        )
        expected_seed = json.loads(json.dumps(expected_seed_runtime))
        seed_snapshot = _load_private_json_snapshot(
            review_root / REVIEW_SEED_NAME,
            "private final acceptance review seed",
        )
        html_path = review_root / REVIEW_HTML_NAME
        _require_private_regular(html_path, "private final acceptance review page")
        expected_page = _review_html(expected_seed_runtime)
        if seed_snapshot["document"] != expected_seed:
            differing = sorted(
                key
                for key in set(seed_snapshot["document"]) | set(expected_seed)
                if seed_snapshot["document"].get(key) != expected_seed.get(key)
            )
            raise ValueError(
                "private final acceptance review seed differs: "
                + ", ".join(differing)
            )
        if seed_snapshot["sha256"] != _sha256(seed_snapshot["path"]):
            raise ValueError("private final acceptance review seed hash differs")
        if html_path.read_text(encoding="utf-8") != expected_page:
            raise ValueError("private final acceptance review page differs")
        if variant_id in expected_page:
            raise ValueError("private final acceptance review reveals variant identity")
        expected_item = {
            "review_id": expected_seed["review_id"],
            "variant_id": variant_id,
            "candidate_label": expected_seed["candidate_label"],
            "directory": f"candidate-{index:02d}",
            "seed": {
                "path": REVIEW_SEED_NAME,
                "sha256": seed_snapshot["sha256"],
                "bytes": seed_snapshot["bytes"],
                "document_sha256": expected_seed["document_sha256"],
                "package_commitment": expected_seed["package_commitment"],
            },
            "html": {
                "path": REVIEW_HTML_NAME,
                "sha256": _sha256(html_path),
                "bytes": html_path.stat().st_size,
            },
            "audio": expected_audio,
            "readiness": dict(_ITEM_READINESS),
        }
        expected_items.append(expected_item)
        verified.append(
            {
                "variant_id": variant_id,
                "package_item": expected_item,
                "review_root": review_root,
                "seed_snapshot": seed_snapshot,
            }
        )
    expected_report = {
        "schema": PACKAGE_SCHEMA,
        "status": PACKAGE_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": expected_bindings,
        "clock": dict(readiness["clock"]),
        "eligible_variant_ids": eligible_ids,
        "eligible_variant_count": len(eligible_ids),
        "required_review_count": len(eligible_ids),
        "reviews": expected_items,
        "readiness": dict(_PACKAGE_READINESS),
        "next_action": "complete_every_independent_final_acceptance_review",
        "interpretation": dict(_PACKAGE_INTERPRETATION),
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_PACKAGE_EFFECTS),
        "limitations": list(_PACKAGE_LIMITATIONS),
    }
    expected_report["document_sha256"] = _document_sha256(expected_report)
    if report != expected_report:
        raise ValueError("private final acceptance review package differs")
    return verified


def _immutable_review(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    result["status"] = REVIEW_STATUS
    result["heard"] = {role: False for role in _ROLES}
    result["ratings"] = {item["id"]: None for item in _QUESTION_SPECS}
    result["notes"] = ""
    result["summary"] = {"complete": False, "answered_questions": 0}
    return result


def _validate_completed_review(review: Mapping[str, Any]) -> None:
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "reviewed"
        or review.get("heard") != {role: True for role in _ROLES}
        or review.get("summary") != {"complete": True, "answered_questions": 4}
        or review.get("permissions") != _FALSE_PERMISSIONS
        or review.get("effects") != _REVIEW_EFFECTS
        or not isinstance(review.get("notes"), str)
        or len(review["notes"]) > _MAXIMUM_NOTES_CHARACTERS
    ):
        raise ValueError("final acceptance review is incomplete")
    ratings = review.get("ratings")
    if not isinstance(ratings, Mapping) or set(ratings) != {
        item["id"] for item in _QUESTION_SPECS
    }:
        raise ValueError("final acceptance review is incomplete")
    for question in _QUESTION_SPECS:
        if ratings[question["id"]] not in question["choices"]:
            raise ValueError("final acceptance review is incomplete")


def _reverify_completed_reviews(context: Mapping[str, Any]) -> None:
    current = _load_verified_package(**context["verification_kwargs"])
    for key in (
        "readiness_snapshot",
        "full_song_result_snapshot",
        "full_song_package_snapshot",
        "package_snapshot",
    ):
        if (
            current[key]["sha256"] != context[key]["sha256"]
            or current[key]["document"] != context[key]["document"]
        ):
            raise ValueError("private final acceptance review evidence changed")
    for item in context.get("completed_reviews", []):
        snapshot = _load_private_json_snapshot(
            item["review_snapshot"]["path"], "reviewed final acceptance export"
        )
        if (
            snapshot["sha256"] != item["review_snapshot"]["sha256"]
            or snapshot["document"] != item["review_snapshot"]["document"]
        ):
            raise ValueError("reviewed final acceptance export changed")


def _result_bindings(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "final_acceptance_review_package_report_sha256": context[
            "package_snapshot"
        ]["sha256"],
        "final_acceptance_review_package_document_sha256": context[
            "package_report"
        ]["document_sha256"],
        "readiness_result_sha256": context["readiness_snapshot"]["sha256"],
        "readiness_result_document_sha256": context["readiness"][
            "document_sha256"
        ],
        "variant_full_song_review_result_sha256": context[
            "full_song_result_snapshot"
        ]["sha256"],
        "variant_alignment_package_sha256": context["readiness"]["bindings"][
            "variant_alignment_package_sha256"
        ],
        "review_exports": [
            {
                "review_id": item["package_item"]["review_id"],
                "variant_id": item["variant_id"],
                "review_seed_sha256": item["seed_snapshot"]["sha256"],
                "review_export_sha256": item["review_snapshot"]["sha256"],
                "package_commitment": item["seed_snapshot"]["document"][
                    "package_commitment"
                ],
            }
            for item in context["completed_reviews"]
        ],
    }


__all__: tuple[str, ...] = ()
