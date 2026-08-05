"""Verify and resolve every eligible-variant full-song boundary review.

The parent package may contain one or two independently reviewable variants.
This module requires the complete emitted review set, matches each browser
export by its immutable package commitment and records each listener result
without selecting between variants.  Alignment, acceptance, activation and
publication remain separate later gates.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_candidate_followup_variant_full_song_review import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
    SCHEMA as PACKAGE_SCHEMA,
    STATUS as PACKAGE_STATUS,
    _CANDIDATE_ROLES,
    _LIMITATIONS as PACKAGE_LIMITATIONS,
    _PACKAGE_EFFECTS,
    _PACKAGE_READINESS,
    _ROLES,
    _eligible_variant_ids,
    _reverify_inputs,
    _verified_exact_variant_result,
    _verify_parent_package,
    _verify_stitch_bound_to_v2,
)
from ._separation_candidate_followup_variant_review import (
    _input_bindings,
    _load_verified_variant_inputs,
)
from ._separation_candidate_full_song_review import (
    _verified_original_boundary_evidence,
)
from ._separation_full_song_executor import (
    _require_private_directory,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _browser_json_equal,
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _validate_completed_review,
    _verify_review_audio,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_HALF_WINDOW_FRAMES,
    REVIEW_NAME,
    REVIEW_SCHEMA,
    _immutable_review,
)


STATUS_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "full-song-review-status.v1"
)
RESULT_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "full-song-review-result.v1"
)
RESULT_STATUS = "complete_independent_variant_reviews_no_activation"
_RATED_ROLES = ("vocals", "instrumental", "reconstruction")
_BOUNDARY_RATINGS = ("audible_join", "cannot_tell", "clean")
_VARIANT_READINESS = {
    "complete_song_review_complete": True,
    "all_original_boundaries_review_complete": True,
    "fresh_alignment_review_eligible": True,
    "alignment_complete": False,
    "selected": False,
    "accepted": False,
    "original_audible_joins_resolved": False,
    "publication_ready": False,
}
_RESULT_EFFECTS = {
    "candidate_accepted": False,
    "candidate_selected": False,
    "package_audio_mutated": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_record_created": True,
    "source_audio_mutated": False,
    "source_graph_mutated": False,
}


def _status_private_candidate_followup_variant_full_song_reviews(
    review_paths: Sequence[str | Path], **kwargs: Any
) -> dict[str, Any]:
    """Verify the complete review set without writing a result."""

    context = _load_completed_reviews(review_paths, **kwargs)
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_set_verified_no_activation",
        "evidence_scope": "private_development_only",
        "bindings": _result_bindings(context),
        "reviewed_variant_ids": list(context["eligible_variant_ids"]),
        "reviewed_variant_count": len(context["eligible_variant_ids"]),
        "required_review_count": context["package_report"]["required_review_count"],
        "reviewed_boundaries_per_variant": {
            item["variant_id"]: len(item["review_snapshot"]["document"]["units"])
            for item in context["completed_reviews"]
        },
        "rating_counts_by_variant": {
            item["variant_id"]: _boundary_counts(
                item["review_snapshot"]["document"]
            )
            for item in context["completed_reviews"]
        },
        "automatic_winner_selected": False,
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {**dict(_RESULT_EFFECTS), "review_record_created": False},
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_candidate_followup_variant_full_song_reviews(
    review_paths: Sequence[str | Path], *, out: str | Path, **kwargs: Any
) -> dict[str, Any]:
    """Write one no-overwrite result containing every independent review."""

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private eligible-variant full-song review result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(
            "private eligible-variant full-song review result already exists: "
            f"{output}"
        )
    context = _load_completed_reviews(review_paths, **kwargs)
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["package"],
            context["variant_review_package"],
            context["base_root"],
            context["v2_root"],
            context["variant_root"],
            context["stitch_root"],
        ),
        evidence_paths=(
            context["package_snapshot"]["path"],
            context["variant_result_snapshot"]["path"],
            context["reviewed_variant_export"],
            context["plan_snapshot"]["path"],
            context["execution_snapshot"]["path"],
            context["candidates_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
            context["stitch_snapshot"]["path"],
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
    variant_results = []
    for item in context["completed_reviews"]:
        review = item["review_snapshot"]["document"]
        counts = _boundary_counts(review)
        audible = {
            role: [
                unit["boundary_index"]
                for unit in review["units"]
                if unit["ratings"][role] == "audible_join"
            ]
            for role in _RATED_ROLES
        }
        all_clean = all(
            counts[role]["clean"] == len(review["units"])
            for role in _RATED_ROLES
        )
        all_useful = all(
            review["full_song"]["ratings"][role] == "useful"
            for role in _RATED_ROLES
        )
        variant_results.append(
            {
                "review_id": item["package_item"]["review_id"],
                "variant_id": item["variant_id"],
                "full_song": {
                    "heard_all": True,
                    "ratings": deepcopy(review["full_song"]["ratings"]),
                    "notes": review["full_song"]["notes"],
                },
                "boundary_summary": {
                    "reviewed_boundaries": len(review["units"]),
                    "rating_counts_by_role": counts,
                    "audible_join_boundaries_by_role": audible,
                    "all_boundaries_clean": all_clean,
                },
                "boundaries": [
                    {
                        "boundary_index": unit["boundary_index"],
                        "frame": unit["frame"],
                        "seconds": unit["seconds"],
                        "ratings": deepcopy(unit["ratings"]),
                        "notes": unit["notes"],
                    }
                    for unit in review["units"]
                ],
                "readiness_evidence": {
                    **dict(_VARIANT_READINESS),
                    "all_full_song_roles_useful": all_useful,
                    "all_boundaries_clean": all_clean,
                },
            }
        )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": "eligible_remediation_variants_reviewed_independently",
        "bindings": _result_bindings(context),
        "clock": deepcopy(context["package_report"]["clock"]),
        "reviewed_variant_ids": list(context["eligible_variant_ids"]),
        "reviewed_variant_count": len(variant_results),
        "variant_results": variant_results,
        "readiness_evidence": {
            "variant_targeted_review_complete": True,
            "all_eligible_variant_full_song_reviews_complete": True,
            "eligible_variant_alignments_complete": False,
            "variant_selected": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "variants_remain_independent": True,
            "package_order_is_preference": False,
            "review_completion_is_candidate_acceptance": False,
            "clean_boundaries_are_separator_accuracy": False,
            "fresh_alignment_still_required_for_each_variant": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_RESULT_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    return result


def _load_completed_reviews(
    review_paths: Sequence[str | Path],
    *,
    review_package_dir: str | Path,
    variant_review_result_path: str | Path,
    variant_reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
) -> dict[str, Any]:
    import numpy as np
    import soundfile

    if isinstance(review_paths, (str, bytes, Path)):
        raise TypeError("review_paths must be the complete review sequence")
    supplied = list(review_paths)
    if not supplied:
        raise ValueError("no eligible-variant full-song reviews supplied")
    package = Path(review_package_dir).expanduser().absolute()
    variant_review_package = Path(variant_review_package_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    for path, label in (
        (package, "private eligible-variant full-song review package"),
        (variant_review_package, "private follow-up variant review package"),
        (stitch_root, "private original stitch root"),
    ):
        _require_private_directory(path, label)

    inputs = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    variant_result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=variant_reviewed_export_path,
        variant_review_package_dir=variant_review_package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    eligible_ids = _eligible_variant_ids(variant_result, context=inputs)
    if len(supplied) != len(eligible_ids):
        raise ValueError("complete eligible-variant review set is required")

    variant_result_snapshot = _load_private_json_snapshot(
        variant_review_result_path, "private follow-up variant review result"
    )
    stitch_snapshot = _load_private_json_snapshot(
        stitch_root / STITCH_REPORT_NAME, "private original stitch report"
    )
    stitch = _load_stitch_report(stitch_snapshot["path"])
    _verify_stitch_audio(stitch_root, stitch)
    _verify_stitch_bound_to_v2(stitch_snapshot, inputs=inputs["inputs"])
    boundary_evidence = _verified_original_boundary_evidence(
        {"stitch": stitch, "stitch_root": stitch_root}
    )
    package_snapshot = _load_private_json_snapshot(
        package / PACKAGE_REPORT_NAME,
        "private eligible-variant full-song review package report",
    )
    package_report = package_snapshot["document"]
    _verify_package_report(
        package,
        package_report,
        inputs=inputs,
        variant_result=variant_result,
        variant_result_snapshot=variant_result_snapshot,
        eligible_ids=eligible_ids,
        stitch=stitch,
        stitch_snapshot=stitch_snapshot,
        boundary_evidence=boundary_evidence,
        soundfile=soundfile,
        np=np,
    )

    package_by_commitment: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(package_report["variant_packages"], start=1):
        package_root = package / item["directory"]
        _require_private_directory(
            package_root, "private eligible-variant full-song review root"
        )
        seed_snapshot = _load_private_json_snapshot(
            package_root / item["boundary_review"]["seed"],
            "private eligible-variant full-song review seed",
        )
        _verify_seed(
            package_root,
            item=item,
            index=index,
            variant_count=len(eligible_ids),
            seed_snapshot=seed_snapshot,
            boundary_evidence=boundary_evidence,
            expected_frames=int(stitch["clock"]["frames"]),
            soundfile=soundfile,
            np=np,
        )
        commitment = seed_snapshot["document"]["package_commitment"]
        if commitment in package_by_commitment:
            raise ValueError("eligible-variant review commitment is duplicated")
        package_by_commitment[commitment] = {
            "variant_id": item["variant_id"],
            "package_item": item,
            "package_root": package_root,
            "seed_snapshot": seed_snapshot,
        }

    completed_by_variant: dict[str, dict[str, Any]] = {}
    seen_paths: set[Path] = set()
    for review_path in supplied:
        review_snapshot = _load_private_json_snapshot(
            review_path, "reviewed eligible-variant full-song export"
        )
        if review_snapshot["path"] in seen_paths:
            raise ValueError("eligible-variant review export is duplicated")
        seen_paths.add(review_snapshot["path"])
        review = review_snapshot["document"]
        commitment = review.get("package_commitment")
        matched = package_by_commitment.get(commitment)
        if matched is None:
            raise ValueError("eligible-variant review export does not belong to package")
        variant_id = matched["variant_id"]
        if variant_id in completed_by_variant:
            raise ValueError("eligible-variant review export is duplicated")
        seed = matched["seed_snapshot"]["document"]
        if not _browser_json_equal(_immutable_review(review), _immutable_review(seed)):
            raise ValueError("eligible-variant review export changed immutable evidence")
        _validate_completed_review(
            review, boundary_count=int(package_report["clock"]["boundary_count"])
        )
        _verify_review_audio(matched["package_root"], review)
        completed_by_variant[variant_id] = {
            **matched,
            "review_snapshot": review_snapshot,
        }
    if set(completed_by_variant) != set(eligible_ids):
        raise ValueError("complete eligible-variant review set is required")

    context: dict[str, Any] = {
        **inputs,
        "package": package,
        "variant_review_package": variant_review_package,
        "stitch_root": stitch_root,
        "reviewed_variant_export": Path(variant_reviewed_export_path)
        .expanduser()
        .absolute(),
        "variant_result": variant_result,
        "variant_result_snapshot": variant_result_snapshot,
        "stitch": stitch,
        "stitch_snapshot": stitch_snapshot,
        "boundary_evidence": boundary_evidence,
        "package_snapshot": package_snapshot,
        "package_report": package_report,
        "eligible_variant_ids": eligible_ids,
        "completed_reviews": [completed_by_variant[item] for item in eligible_ids],
        "plan_path": Path(plan_path).expanduser().absolute(),
        "execution_dir": Path(execution_dir).expanduser().absolute(),
        "v2_execution_dir": Path(v2_execution_dir).expanduser().absolute(),
        "variant_execution_dir": Path(variant_execution_dir).expanduser().absolute(),
    }
    _reverify_completed_reviews(context)
    return context


def _verify_package_report(
    package: Path,
    report: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
    variant_result: Mapping[str, Any],
    variant_result_snapshot: Mapping[str, Any],
    eligible_ids: list[str],
    stitch: Mapping[str, Any],
    stitch_snapshot: Mapping[str, Any],
    boundary_evidence: Mapping[str, Any],
    soundfile: Any,
    np: Any,
) -> None:
    expected_bindings = {
        **_input_bindings(inputs),
        "variant_review_result_sha256": variant_result_snapshot["sha256"],
        "variant_review_result_document_sha256": variant_result["document_sha256"],
        "variant_review_export_sha256": variant_result["bindings"][
            "review_export_sha256"
        ],
        "stitch_report_sha256": stitch_snapshot["sha256"],
        "stitch_document_sha256": stitch["document_sha256"],
    }
    expected_clock = {
        **dict(stitch["clock"]),
        "boundary_count": len(boundary_evidence["boundaries"]),
    }
    if (
        report.get("schema") != PACKAGE_SCHEMA
        or report.get("status") != PACKAGE_STATUS
        or report.get("evidence_scope") != "private_development_only"
        or report.get("document_sha256") != _document_sha256(report)
        or report.get("bindings") != expected_bindings
        or report.get("clock") != expected_clock
        or report.get("eligible_variant_ids") != eligible_ids
        or report.get("eligible_variant_count") != len(eligible_ids)
        or report.get("required_review_count") != len(eligible_ids)
        or report.get("readiness") != _PACKAGE_READINESS
        or report.get("permissions") != _FALSE_PERMISSIONS
        or report.get("effects") != _PACKAGE_EFFECTS
        or report.get("limitations") != PACKAGE_LIMITATIONS
        or report.get("interpretation")
        != {
            "every_eligible_variant_included": True,
            "eligible_variants_may_be_multiple": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        }
    ):
        raise ValueError("private eligible-variant full-song review package differs")
    packages = report.get("variant_packages")
    if not isinstance(packages, list) or len(packages) != len(eligible_ids):
        raise ValueError("private eligible-variant review inventory differs")
    variants = {item["variant_id"]: item for item in inputs["candidates"]["variants"]}
    for index, (item, variant_id) in enumerate(zip(packages, eligible_ids), start=1):
        if (
            not isinstance(item, Mapping)
            or set(item)
            != {
                "review_id",
                "variant_id",
                "directory",
                "artifacts",
                "boundary_review",
                "readiness",
            }
            or item.get("review_id") != f"eligible-variant-{index:02d}"
            or item.get("variant_id") != variant_id
            or item.get("directory") != f"variant-{index:02d}"
            or item.get("readiness")
            != {
                "eligible_for_fresh_all_boundary_review": True,
                "complete_song_review_complete": False,
                "all_original_boundaries_review_complete": False,
                "alignment_complete": False,
                "selected": False,
                "accepted": False,
            }
        ):
            raise ValueError("private eligible-variant review inventory differs")
        expected = {
            "source": stitch["artifacts"]["source"],
            **variants[variant_id]["artifacts"],
        }
        _verify_artifact_bindings(item["artifacts"], expected=expected)
    _verify_parent_package(package, report, soundfile=soundfile)


def _verify_artifact_bindings(
    artifacts: object, *, expected: Mapping[str, Any]
) -> None:
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(_ROLES):
        raise ValueError("private eligible-variant audio inventory differs")
    for role in _ROLES:
        record = artifacts[role]
        source = expected[role]
        if (
            not isinstance(record, Mapping)
            or record.get("path")
            != (
                "SOURCE/source-44100.wav"
                if role == "source"
                else f"STEMS/{role}.wav"
            )
            or any(
                record.get(key) != source.get(key)
                for key in (
                    "sha256",
                    "bytes",
                    "geometry",
                    "pcm24_int32_sequence_sha256",
                )
            )
        ):
            raise ValueError("private eligible-variant audio binding differs")


def _verify_seed(
    package_root: Path,
    *,
    item: Mapping[str, Any],
    index: int,
    variant_count: int,
    seed_snapshot: Mapping[str, Any],
    boundary_evidence: Mapping[str, Any],
    expected_frames: int,
    soundfile: Any,
    np: Any,
) -> None:
    seed = seed_snapshot["document"]
    claim = item["boundary_review"]
    expected_title = (
        f"{boundary_evidence['title']} - eligible remediation variant "
        f"{index} of {variant_count}"
    )
    expected_policy = {
        "maximum_window_seconds": 4.0,
        "maximum_join_at_window_seconds": 2.0,
        "ratings": ["clean", "audible_join", "cannot_tell"],
        "review_every_boundary": True,
        "source_is_context_not_a_rated_separator_output": True,
        "full_song_ratings": [
            "useful",
            "noticeable_problems",
            "not_useful",
            "cannot_tell",
        ],
    }
    if (
        set(seed)
        != {
            "schema",
            "status",
            "evidence_scope",
            "title",
            "question",
            "policy",
            "full_song",
            "units",
            "summary",
            "permissions",
            "package_commitment",
        }
        or
        seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != "unreviewed"
        or seed.get("evidence_scope") != "private_development_only"
        or claim.get("status") != "unreviewed"
        or claim.get("seed") != f"BOUNDARY-REVIEW/{REVIEW_NAME}"
        or claim.get("html")
        != "BOUNDARY-REVIEW/separation_boundary_review.html"
        or seed_snapshot["sha256"] != claim.get("seed_sha256")
        or seed.get("package_commitment") != claim.get("package_commitment")
        or seed.get("package_commitment")
        != hashlib.sha256(canonical_json_bytes(_immutable_review(seed))).hexdigest()
        or seed.get("title") != expected_title
        or seed.get("question")
        != "Can you hear a click, cut, level jump or tone change at the centre join?"
        or seed.get("policy") != expected_policy
        or seed.get("permissions") != _FALSE_PERMISSIONS
        or claim.get("boundary_count") != len(boundary_evidence["boundaries"])
    ):
        raise ValueError("private eligible-variant full-song review seed differs")
    full_song = seed.get("full_song")
    expected_full_audio = {
        role: {
            "path": (
                "../SOURCE/source-44100.wav"
                if role == "source"
                else f"../STEMS/{role}.wav"
            ),
            "sha256": item["artifacts"][role]["sha256"],
            "bytes": item["artifacts"][role]["bytes"],
        }
        for role in _ROLES
    }
    if (
        not isinstance(full_song, Mapping)
        or set(full_song) != {"audio", "heard_all", "ratings", "notes"}
        or full_song.get("audio") != expected_full_audio
        or full_song.get("heard_all") is not False
        or full_song.get("ratings")
        != {role: "unreviewed" for role in _RATED_ROLES}
        or full_song.get("notes") != ""
        or seed.get("summary")
        != {
            "full_song_reviewed": False,
            "reviewed_boundaries": 0,
            "boundary_count": len(boundary_evidence["boundaries"]),
        }
    ):
        raise ValueError("private eligible-variant full-song review seed differs")
    units = seed.get("units")
    if not isinstance(units, list) or len(units) != len(boundary_evidence["boundaries"]):
        raise ValueError("private eligible-variant boundary inventory differs")
    for index, (unit, frame) in enumerate(
        zip(units, boundary_evidence["boundaries"]), start=1
    ):
        half = min(REVIEW_HALF_WINDOW_FRAMES, frame, expected_frames - frame)
        if (
            not isinstance(unit, Mapping)
            or set(unit)
            != {
                "boundary_index",
                "frame",
                "seconds",
                "window_seconds",
                "join_at_window_seconds",
                "audio",
                "heard_all",
                "ratings",
                "notes",
            }
            or unit.get("boundary_index") != index
            or unit.get("frame") != frame
            or unit.get("seconds") != frame / 44_100
            or unit.get("window_seconds")
            != [(frame - half) / 44_100, (frame + half) / 44_100]
            or unit.get("join_at_window_seconds") != half / 44_100
            or unit.get("heard_all") is not False
            or unit.get("ratings")
            != {role: "unreviewed" for role in _RATED_ROLES}
            or unit.get("notes") != ""
            or not isinstance(unit.get("audio"), Mapping)
            or set(unit["audio"]) != set(_ROLES)
            or any(
                unit["audio"][role].get("path")
                != f"audio/boundary-{index:02d}-{role}.wav"
                for role in _ROLES
            )
        ):
            raise ValueError("private eligible-variant boundary inventory differs")
    _verify_review_audio(package_root, seed)
    _verify_boundary_audio_content(
        package_root,
        seed=seed,
        soundfile=soundfile,
        np=np,
    )


def _verify_boundary_audio_content(
    package_root: Path, *, seed: Mapping[str, Any], soundfile: Any, np: Any
) -> None:
    full_paths = {
        "source": package_root / "SOURCE/source-44100.wav",
        **{role: package_root / f"STEMS/{role}.wav" for role in _CANDIDATE_ROLES},
    }
    for unit in seed["units"]:
        start = round(unit["window_seconds"][0] * 44_100)
        end = round(unit["window_seconds"][1] * 44_100)
        for role in _ROLES:
            expected, expected_rate = soundfile.read(
                full_paths[role], start=start, stop=end, dtype="int32", always_2d=True
            )
            observed, observed_rate = soundfile.read(
                package_root / "BOUNDARY-REVIEW" / unit["audio"][role]["path"],
                dtype="int32",
                always_2d=True,
            )
            if (
                int(expected_rate) != 44_100
                or int(observed_rate) != 44_100
                or expected.shape != observed.shape
                or not np.array_equal(expected, observed)
            ):
                raise ValueError("private eligible-variant boundary audio differs")


def _reverify_completed_reviews(context: Mapping[str, Any]) -> None:
    import numpy as np
    import soundfile

    for snapshot, label in (
        (context["variant_result_snapshot"], "private follow-up variant review result"),
        (context["plan_snapshot"], "private follow-up variant plan"),
        (context["execution_snapshot"], "private follow-up variant execution"),
        (context["candidates_snapshot"], "private follow-up variant candidates"),
        (context["inputs"]["execution_snapshot"], "private follow-up control execution"),
        (context["inputs"]["candidate_snapshot"], "private follow-up control candidate"),
        (context["inputs"]["v2_snapshot"], "private v2 execution"),
        (context["stitch_snapshot"], "private original stitch report"),
        (context["package_snapshot"], "private eligible-variant full-song package"),
    ):
        current = _load_private_json_snapshot(snapshot["path"], label)
        if current["sha256"] != snapshot["sha256"] or current["document"] != snapshot["document"]:
            raise ValueError(f"{label} changed")
    for item in context["completed_reviews"]:
        for snapshot, label in (
            (item["seed_snapshot"], "private eligible-variant review seed"),
            (item["review_snapshot"], "reviewed eligible-variant full-song export"),
        ):
            current = _load_private_json_snapshot(snapshot["path"], label)
            if current["sha256"] != snapshot["sha256"] or current["document"] != snapshot["document"]:
                raise ValueError(f"{label} changed")
        _verify_review_audio(
            item["package_root"], item["review_snapshot"]["document"]
        )
        _verify_boundary_audio_content(
            item["package_root"],
            seed=item["seed_snapshot"]["document"],
            soundfile=soundfile,
            np=np,
        )
    _verify_stitch_audio(context["stitch_root"], context["stitch"])
    _verify_stitch_bound_to_v2(context["stitch_snapshot"], inputs=context["inputs"])
    _reverify_inputs(
        result=context["variant_result"],
        variant_review_result_path=context["variant_result_snapshot"]["path"],
        reviewed_export_path=context["reviewed_variant_export"],
        variant_review_package_dir=context["variant_review_package"],
        plan_path=context["plan_path"],
        execution_dir=context["execution_dir"],
        v2_execution_dir=context["v2_execution_dir"],
        variant_execution_dir=context["variant_execution_dir"],
        context=context,
        stitch_snapshot=context["stitch_snapshot"],
        stitch_root=context["stitch_root"],
        boundary_evidence=context["boundary_evidence"],
    )
    _verify_package_report(
        context["package"],
        context["package_report"],
        inputs=context,
        variant_result=context["variant_result"],
        variant_result_snapshot=context["variant_result_snapshot"],
        eligible_ids=context["eligible_variant_ids"],
        stitch=context["stitch"],
        stitch_snapshot=context["stitch_snapshot"],
        boundary_evidence=context["boundary_evidence"],
        soundfile=soundfile,
        np=np,
    )


def _boundary_counts(review: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    return {
        role: {
            rating: sum(unit["ratings"][role] == rating for unit in review["units"])
            for rating in _BOUNDARY_RATINGS
        }
        for role in _RATED_ROLES
    }


def _result_bindings(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "variant_full_song_review_package_report_sha256": context[
            "package_snapshot"
        ]["sha256"],
        "variant_full_song_review_package_document_sha256": context[
            "package_report"
        ]["document_sha256"],
        "variant_review_result_sha256": context["variant_result_snapshot"]["sha256"],
        "variant_review_result_document_sha256": context["variant_result"][
            "document_sha256"
        ],
        "variant_review_export_sha256": context["variant_result"]["bindings"][
            "review_export_sha256"
        ],
        "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
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
