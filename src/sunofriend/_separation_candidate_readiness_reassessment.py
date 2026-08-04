"""Combine fresh v2 candidate evidence without accepting the separator.

The targeted join review, complete-song listening result and nine-window
alignment result are independent evidence planes.  This module verifies and
binds all three, then records whether a separate final human-acceptance review
is eligible.  It cannot select, accept, publish or expose a separator.
"""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_full_song_alignment import (
    POLICY_ID as ALIGNMENT_POLICY_ID,
    SCHEMA as ALIGNMENT_SCHEMA,
    STATUS as ALIGNMENT_STATUS,
    _FALSE_EFFECTS as ALIGNMENT_FALSE_EFFECTS,
)
from ._separation_candidate_full_song_review import (
    _require_review_result_unchanged,
    _verify_passing_v2_review_result,
)
from ._separation_candidate_full_song_review_result import (
    RESULT_SCHEMA as REVIEW_RESULT_SCHEMA,
    RESULT_STATUS as REVIEW_RESULT_STATUS,
    _RESULT_EFFECTS as REVIEW_RESULT_EFFECTS,
)
from ._separation_full_song_alignment import (
    FEATURE_FRAME_MILLISECONDS,
    FEATURE_HOP_MILLISECONDS,
    MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
    MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
    MAXIMUM_SEARCH_LAG_MILLISECONDS,
    MAXIMUM_WINDOW_SECONDS,
    MINIMUM_ACCEPTED_WINDOW_CORRELATION,
    MINIMUM_ACTIVE_RMS_DBFS,
    WINDOW_COUNT,
    _song_third,
    _window_start_frames,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_v2 import (
    _load_review_inputs,
    _reverify_inputs,
)


SCHEMA = "sunofriend.private-separation-candidate-readiness-reassessment.v1"
STATUS = "evidence_complete_final_human_acceptance_required"
REPORT_NAME = "private-separation-candidate-readiness-reassessment.json"
_CANDIDATE_IDENTITY = "v2_expanded_context_join_remediation"
_ROLES = ("vocals", "instrumental", "reconstruction")
_BOUNDARY_RATINGS = ("audible_join", "cannot_tell", "clean")
_FULL_SONG_RATINGS = {
    "useful",
    "noticeable_problems",
    "not_useful",
    "cannot_tell",
}
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "readiness_record_created": True,
    "source_graph_mutated": False,
}
_REVIEW_RESULT_KEYS = {
    "schema",
    "status",
    "evidence_scope",
    "candidate_identity",
    "bindings",
    "clock",
    "full_song",
    "boundary_summary",
    "boundaries",
    "readiness_evidence",
    "interpretation",
    "permissions",
    "effects",
    "document_sha256",
}
_REVIEW_BINDING_KEYS = {
    "candidate_review_package_report_sha256",
    "candidate_review_package_document_sha256",
    "candidate_review_seed_sha256",
    "candidate_review_export_sha256",
    "candidate_review_package_commitment",
    "v2_review_result_sha256",
    "v2_review_result_document_sha256",
    "v2_execution_report_sha256",
    "v2_execution_document_sha256",
}
_ALIGNMENT_RESULT_KEYS = {
    "schema",
    "status",
    "evidence_scope",
    "policy_id",
    "candidate_identity",
    "bindings",
    "clock",
    "protocol",
    "thresholds",
    "windows",
    "summary",
    "readiness_evidence",
    "interpretation",
    "permissions",
    "effects",
    "limitations",
    "document_sha256",
}
_ALIGNMENT_BINDING_KEYS = {
    "v2_review_result_sha256",
    "v2_review_result_document_sha256",
    "v2_execution_report_sha256",
    "v2_execution_document_sha256",
    "stitch_report_sha256",
    "stitch_document_sha256",
    "source_audio_sha256",
    "source_pcm24_int32_sequence_sha256",
    "reconstruction_audio_sha256",
    "reconstruction_pcm24_int32_sequence_sha256",
}
_ALIGNMENT_WINDOW_KEYS = {
    "window_index",
    "song_third",
    "start_frame",
    "end_frame",
    "start_seconds",
    "end_seconds",
    "source_rms_dbfs",
    "reconstruction_rms_dbfs",
    "eligible",
    "best_lag_milliseconds",
    "peak_normalized_correlation",
}
_ALIGNMENT_LIMITATIONS = [
    "This report measures only the exact v2 source-to-reconstruction clock and drift.",
    "The earlier candidate's alignment result is not inherited.",
    "A synchronized reconstruction can still contain bleed, omissions or artefacts.",
    "Fresh candidate-bound full-song and boundary listening remains separate evidence.",
]


def _reassess_private_candidate_readiness(
    v2_review_result_path: str | Path,
    *,
    candidate_review_result_path: str | Path,
    candidate_alignment_result_path: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one non-activating readiness reassessment for the exact candidate."""

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private candidate readiness result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(f"private candidate readiness result exists: {output}")

    context = _load_review_inputs(
        v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    v2_snapshot = _load_private_json_snapshot(
        v2_review_result_path, "private resolved v2 join review result"
    )
    _verify_passing_v2_review_result(v2_snapshot, context=context)
    review_snapshot = _load_private_json_snapshot(
        candidate_review_result_path,
        "private candidate full-song review result",
    )
    alignment_snapshot = _load_private_json_snapshot(
        candidate_alignment_result_path,
        "private candidate full-song alignment result",
    )
    _verify_candidate_review_result(
        review_snapshot["document"],
        v2_snapshot=v2_snapshot,
        context=context,
    )
    _verify_candidate_alignment_result(
        alignment_snapshot["document"],
        v2_snapshot=v2_snapshot,
        context=context,
    )
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(context["v1_root"], context["v2_root"], context["stitch_root"]),
        evidence_paths=(
            v2_snapshot["path"],
            review_snapshot["path"],
            alignment_snapshot["path"],
            context["v2_snapshot"]["path"],
            context["v2_plan_snapshot"]["path"],
            context["stitch_snapshot"]["path"],
            context["v1_execution_snapshot"]["path"],
            context["v1_candidate_snapshot"]["path"],
            *context["authority_paths"],
        ),
    )

    review = review_snapshot["document"]
    alignment = alignment_snapshot["document"]
    all_boundaries_clean = review["readiness_evidence"][
        "all_candidate_boundaries_clean"
    ]
    all_roles_useful = review["readiness_evidence"][
        "all_candidate_full_song_roles_useful"
    ]
    alignment_passed = alignment["readiness_evidence"]["alignment_gate_passed"]
    prerequisites_met = bool(
        all_boundaries_clean and all_roles_useful and alignment_passed
    )
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": _CANDIDATE_IDENTITY,
        "bindings": {
            "v2_review_result_sha256": v2_snapshot["sha256"],
            "v2_review_result_document_sha256": v2_snapshot["document"][
                "document_sha256"
            ],
            "candidate_review_result_sha256": review_snapshot["sha256"],
            "candidate_review_result_document_sha256": review["document_sha256"],
            "candidate_alignment_result_sha256": alignment_snapshot["sha256"],
            "candidate_alignment_result_document_sha256": alignment["document_sha256"],
            "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
            "v2_execution_document_sha256": context["v2_report"]["document_sha256"],
            "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
            "stitch_document_sha256": context["stitch"]["document_sha256"],
        },
        "clock": deepcopy(context["stitch"]["clock"]),
        "evidence": {
            "targeted_v2_absolute_cleanliness_pass": True,
            "candidate_full_song_review_complete": True,
            "all_candidate_boundaries_clean": all_boundaries_clean,
            "all_candidate_full_song_roles_useful": all_roles_useful,
            "candidate_alignment_complete": True,
            "candidate_alignment_gate_passed": alignment_passed,
            "technical_and_listening_prerequisites_met": prerequisites_met,
        },
        "readiness": {
            "reassessment_complete": True,
            "final_human_acceptance_review_eligible": prerequisites_met,
            "final_human_acceptance_review_complete": False,
            "original_audible_joins_resolved": False,
            "separator_selected": False,
            "separator_accepted": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
        "next_action": (
            "run_explicit_final_candidate_acceptance_review"
            if prerequisites_met
            else "remediate_failed_candidate_evidence"
        ),
        "interpretation": {
            "clean_boundaries_are_separator_accuracy": False,
            "alignment_gate_pass_is_separator_acceptance": False,
            "useful_full_song_roles_are_publication_approval": False,
            "prerequisites_met_is_final_acceptance": False,
            "automatic_winner_selected": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This report combines evidence; it does not add listening evidence.",
            "Boundary cleanliness, overall usefulness and alignment remain distinct claims.",
            "A separate explicit human acceptance review must resolve the original audible-join gate.",
            "No separator is selected, accepted, published or exposed to a product route.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        _reverify_all(v2_snapshot, review_snapshot, alignment_snapshot, context)
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _verify_candidate_review_result(
    document: Mapping[str, Any],
    *,
    v2_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    if (
        set(document) != _REVIEW_RESULT_KEYS
        or document.get("schema") != REVIEW_RESULT_SCHEMA
        or document.get("status") != REVIEW_RESULT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("candidate_identity") != _CANDIDATE_IDENTITY
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("clock") != context["stitch"]["clock"]
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != REVIEW_RESULT_EFFECTS
    ):
        raise ValueError("private candidate full-song review result differs")
    bindings = document.get("bindings")
    if (
        not isinstance(bindings, Mapping)
        or set(bindings) != _REVIEW_BINDING_KEYS
        or not all(_is_sha256(bindings[key]) for key in _REVIEW_BINDING_KEYS)
        or bindings.get("v2_review_result_sha256") != v2_snapshot["sha256"]
        or bindings.get("v2_review_result_document_sha256")
        != v2_snapshot["document"]["document_sha256"]
        or bindings.get("v2_execution_report_sha256")
        != context["v2_snapshot"]["sha256"]
        or bindings.get("v2_execution_document_sha256")
        != context["v2_report"]["document_sha256"]
    ):
        raise ValueError("private candidate full-song review bindings differ")

    full_song = document.get("full_song")
    boundaries = document.get("boundaries")
    summary = document.get("boundary_summary")
    full_song_ratings = (
        full_song.get("ratings") if isinstance(full_song, Mapping) else None
    )
    if (
        not isinstance(full_song, Mapping)
        or full_song.get("heard_all") is not True
        or not isinstance(full_song_ratings, Mapping)
        or set(full_song_ratings) != set(_ROLES)
        or any(value not in _FULL_SONG_RATINGS for value in full_song_ratings.values())
        or not _bounded_notes(full_song.get("notes"))
        or not isinstance(boundaries, list)
        or len(boundaries) != context["stitch"]["clock"]["boundary_count"]
        or not isinstance(summary, Mapping)
    ):
        raise ValueError("private candidate full-song review evidence differs")
    counts = {role: {rating: 0 for rating in _BOUNDARY_RATINGS} for role in _ROLES}
    audible = {role: [] for role in _ROLES}
    sample_rate = context["stitch"]["clock"]["sample_rate"]
    for index, boundary in enumerate(boundaries, start=1):
        ratings = boundary.get("ratings") if isinstance(boundary, Mapping) else None
        if (
            not isinstance(boundary, Mapping)
            or set(boundary)
            != {"boundary_index", "frame", "seconds", "ratings", "notes"}
            or boundary.get("boundary_index") != index
            or type(boundary.get("frame")) is not int
            or not isinstance(boundary.get("seconds"), (int, float))
            or isinstance(boundary.get("seconds"), bool)
            or not math.isclose(
                float(boundary["seconds"]),
                boundary["frame"] / sample_rate,
                abs_tol=1.0e-6,
            )
            or not isinstance(ratings, Mapping)
            or set(ratings) != set(_ROLES)
            or any(value not in _BOUNDARY_RATINGS for value in ratings.values())
            or not _bounded_notes(boundary.get("notes"))
        ):
            raise ValueError("private candidate full-song boundary evidence differs")
        for role in _ROLES:
            rating = ratings[role]
            counts[role][rating] += 1
            if rating == "audible_join":
                audible[role].append(index)
    all_clean = all(counts[role]["clean"] == len(boundaries) for role in _ROLES)
    all_useful = all(full_song_ratings[role] == "useful" for role in _ROLES)
    expected_summary = {
        "reviewed_boundaries": len(boundaries),
        "rating_counts_by_role": counts,
        "audible_join_boundaries_by_role": audible,
        "all_candidate_boundaries_clean": all_clean,
    }
    expected_readiness = {
        "targeted_v2_absolute_cleanliness_pass": True,
        "new_candidate_full_song_review_complete": True,
        "all_candidate_boundaries_clean": all_clean,
        "all_candidate_full_song_roles_useful": all_useful,
        "fresh_candidate_bound_alignment_review_eligible": True,
        "new_candidate_alignment_complete": False,
        "original_audible_joins_resolved": False,
        "publication_ready": False,
    }
    if (
        summary != expected_summary
        or document.get("readiness_evidence") != expected_readiness
        or document.get("interpretation")
        != {
            "ratings_are_human_listening_evidence": True,
            "full_song_review_completion_is_candidate_acceptance": False,
            "clean_boundaries_are_separator_accuracy": False,
            "alignment_still_requires_fresh_review": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        }
    ):
        raise ValueError("private candidate full-song review claims differ")


def _verify_candidate_alignment_result(
    document: Mapping[str, Any],
    *,
    v2_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    if (
        set(document) != _ALIGNMENT_RESULT_KEYS
        or document.get("schema") != ALIGNMENT_SCHEMA
        or document.get("status") != ALIGNMENT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != ALIGNMENT_POLICY_ID
        or document.get("candidate_identity") != _CANDIDATE_IDENTITY
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("clock") != context["stitch"]["clock"]
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != ALIGNMENT_FALSE_EFFECTS
        or document.get("limitations") != _ALIGNMENT_LIMITATIONS
    ):
        raise ValueError("private candidate alignment result differs")
    bindings = document.get("bindings")
    if (
        not isinstance(bindings, Mapping)
        or set(bindings) != _ALIGNMENT_BINDING_KEYS
        or not all(_is_sha256(bindings[key]) for key in _ALIGNMENT_BINDING_KEYS)
        or bindings.get("v2_review_result_sha256") != v2_snapshot["sha256"]
        or bindings.get("v2_review_result_document_sha256")
        != v2_snapshot["document"]["document_sha256"]
        or bindings.get("v2_execution_report_sha256")
        != context["v2_snapshot"]["sha256"]
        or bindings.get("v2_execution_document_sha256")
        != context["v2_report"]["document_sha256"]
        or bindings.get("stitch_report_sha256") != context["stitch_snapshot"]["sha256"]
        or bindings.get("stitch_document_sha256")
        != context["stitch"]["document_sha256"]
    ):
        raise ValueError("private candidate alignment bindings differ")
    clock = context["stitch"]["clock"]
    sample_rate = clock["sample_rate"]
    window_seconds = min(MAXIMUM_WINDOW_SECONDS, clock["duration_seconds"] / 12.0)
    window_frames = max(1, int(round(window_seconds * sample_rate)))
    expected_protocol = {
        "comparison": "canonical source versus diagnostic reconstruction",
        "feature": "log spectral-band energy",
        "window_count": WINDOW_COUNT,
        "window_seconds": round(window_frames / sample_rate, 6),
        "feature_frame_milliseconds": FEATURE_FRAME_MILLISECONDS,
        "feature_hop_milliseconds": FEATURE_HOP_MILLISECONDS,
        "maximum_search_lag_milliseconds": MAXIMUM_SEARCH_LAG_MILLISECONDS,
        "lag_sign": "positive means reconstruction is later than source",
        "source_and_reconstruction_gain_normalized_for_timing": True,
    }
    expected_thresholds = {
        "minimum_active_rms_dbfs": MINIMUM_ACTIVE_RMS_DBFS,
        "minimum_eligible_window_count": WINDOW_COUNT,
        "all_song_thirds_required": True,
        "maximum_absolute_lag_milliseconds": MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
        "maximum_lag_spread_milliseconds": MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
        "minimum_window_normalized_correlation": MINIMUM_ACCEPTED_WINDOW_CORRELATION,
    }
    windows = document.get("windows")
    starts = _window_start_frames(
        total_frames=clock["frames"], window_frames=window_frames
    )
    if (
        document.get("protocol") != expected_protocol
        or document.get("thresholds") != expected_thresholds
        or not isinstance(windows, list)
        or len(windows) != WINDOW_COUNT
    ):
        raise ValueError("private candidate alignment protocol differs")
    eligible = []
    for index, (window, start) in enumerate(zip(windows, starts), start=1):
        if (
            not isinstance(window, Mapping)
            or set(window) != _ALIGNMENT_WINDOW_KEYS
            or window.get("window_index") != index
            or window.get("song_third") != _song_third(index)
            or window.get("start_frame") != start
            or window.get("end_frame") != start + window_frames
            or not _finite_number(window.get("start_seconds"))
            or not math.isclose(
                float(window["start_seconds"]),
                round(start / sample_rate, 6),
                abs_tol=1.0e-9,
            )
            or not _finite_number(window.get("end_seconds"))
            or not math.isclose(
                float(window["end_seconds"]),
                round((start + window_frames) / sample_rate, 6),
                abs_tol=1.0e-9,
            )
            or not _finite_number(window.get("source_rms_dbfs"))
            or not _finite_number(window.get("reconstruction_rms_dbfs"))
            or type(window.get("eligible")) is not bool
        ):
            raise ValueError("private candidate alignment window differs")
        if window["eligible"]:
            if not all(
                _finite_number(window.get(key))
                for key in (
                    "best_lag_milliseconds",
                    "peak_normalized_correlation",
                )
            ):
                raise ValueError("private candidate alignment measurement differs")
            eligible.append(window)
        elif (
            window.get("best_lag_milliseconds") is not None
            or window.get("peak_normalized_correlation") is not None
        ):
            raise ValueError("private candidate ineligible alignment window differs")
    lags = [float(window["best_lag_milliseconds"]) for window in eligible]
    correlations = [float(window["peak_normalized_correlation"]) for window in eligible]
    coverage = len(eligible) == WINDOW_COUNT and {
        window["song_third"] for window in eligible
    } == {"early", "middle", "late"}
    maximum_lag = max((abs(value) for value in lags), default=math.inf)
    spread = max(lags) - min(lags) if lags else math.inf
    minimum_correlation = min(correlations, default=-1.0)
    summary = {
        "eligible_window_count": len(eligible),
        "maximum_absolute_lag_milliseconds": (
            round(maximum_lag, 6) if math.isfinite(maximum_lag) else None
        ),
        "lag_spread_milliseconds": (
            round(spread, 6) if math.isfinite(spread) else None
        ),
        "minimum_window_normalized_correlation": round(minimum_correlation, 6),
        "early_middle_late_coverage_complete": coverage,
    }
    gate = bool(
        coverage
        and maximum_lag <= MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS
        and spread <= MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS
        and minimum_correlation >= MINIMUM_ACCEPTED_WINDOW_CORRELATION
    )
    expected_readiness = {
        "targeted_v2_absolute_cleanliness_pass": True,
        "new_candidate_alignment_complete": True,
        "source_to_reconstruction_alignment_verified": gate,
        "drift_acceptance_complete": gate,
        "alignment_gate_passed": gate,
        "new_candidate_full_song_review_complete": False,
        "original_audible_joins_resolved": False,
        "separator_accuracy_established": False,
        "publication_ready": False,
    }
    if (
        document.get("summary") != summary
        or document.get("readiness_evidence") != expected_readiness
        or document.get("interpretation")
        != {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        }
    ):
        raise ValueError("private candidate alignment claims differ")


def _reverify_all(
    v2_snapshot: Mapping[str, Any],
    review_snapshot: Mapping[str, Any],
    alignment_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    _require_review_result_unchanged(v2_snapshot)
    _reverify_inputs(context)
    for snapshot, label in (
        (review_snapshot, "private candidate full-song review result"),
        (alignment_snapshot, "private candidate full-song alignment result"),
    ):
        current = _load_private_json_snapshot(snapshot["path"], label)
        if (
            current["sha256"] != snapshot["sha256"]
            or current["document"] != snapshot["document"]
        ):
            raise ValueError(f"{label} changed")


def _bounded_notes(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 2_000


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


__all__: tuple[str, ...] = ()
