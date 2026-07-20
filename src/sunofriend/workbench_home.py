"""Path-free Project Overview projection for the local Workbench."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .workbench_privacy import path_free_role
from .workbench_semantics import (
    TERMINAL_NO_SELECTION_OUTCOMES,
    terminal_no_selection_outcome,
)


WORKBENCH_HOME_SCHEMA = "sunofriend.workbench-home.v1"


def build_workbench_home(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Summarise explicit workflow state without making a musical decision.

    The projection deliberately excludes paths, private notes, process metrics and
    candidate labels.  Its one next state/action is derived only from append-only
    decisions already present in ``current``; any offered action is navigation.
    """

    current_stems = current.get("stems", {})
    if not isinstance(current_stems, Mapping):
        current_stems = {}

    rows: list[dict[str, Any]] = []
    for stem in catalog.get("stems", []):
        if not isinstance(stem, Mapping):
            continue
        stem_id = str(stem.get("stem_id", ""))
        state = current_stems.get(stem_id, {})
        if not isinstance(state, Mapping):
            state = {}
        rows.append(_stem_row(stem, state))

    candidate_rows = [row for row in rows if row["candidate_count"] > 0]
    selected_part_count = sum(row["selected_part_count"] for row in rows)
    decision_recorded_count = sum(
        bool(row["decision_recorded"]) for row in candidate_rows
    )
    needs_full_mix_count = sum(
        row["selected_needing_full_mix_count"] for row in rows
    )
    next_step = _next_step(
        rows,
        selected_part_count=selected_part_count,
        needs_full_mix_count=needs_full_mix_count,
    )

    return {
        "schema": WORKBENCH_HOME_SCHEMA,
        "project_id": str(catalog.get("project_id", "")),
        "counts": {
            "stem_count": len(rows),
            "candidate_stem_count": len(candidate_rows),
            "decision_recorded_stem_count": decision_recorded_count,
            "selected_part_count": selected_part_count,
            "selected_main_count": sum(row["selected_main_count"] for row in rows),
            "selected_optional_count": sum(
                row["selected_optional_count"] for row in rows
            ),
            "selected_needing_full_mix_count": needs_full_mix_count,
        },
        "stems": rows,
        "next_step": next_step,
        "temporary_state_restored": False,
        "temporary_state_not_restored": [
            "playhead",
            "loop",
            "mixer visibility",
            "mute",
            "solo",
            "level",
        ],
        "effects": {
            "feedback_recorded": False,
            "musical_selection_changed": False,
            "pack_selection_changed": False,
            "midi_mutated": False,
            "audio_mutated": False,
        },
    }


def _stem_row(stem: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in stem.get("candidates", [])
        if isinstance(candidate, Mapping)
    ]
    display_letters = _candidate_display_letters(candidates)
    saved_candidates = state.get("candidates", {})
    if not isinstance(saved_candidates, Mapping):
        saved_candidates = {}

    outcome = state.get("outcome")
    outcome_value = outcome.get("value") if isinstance(outcome, Mapping) else None
    terminal_outcome = terminal_no_selection_outcome(outcome_value)
    main_candidate_id = state.get("main_candidate_id")
    main: dict[str, str] | None = None
    optional: list[dict[str, str]] = []
    decision_counts = {
        "main": 0,
        "optional": 0,
        "needs_correction": 0,
        "reject": 0,
    }
    selected_contexts: list[str] = []
    matching_decision_recorded = False
    blocked_selected_count = 0
    inactive_selected_count = 0
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id", ""))
        saved = saved_candidates.get(candidate_id)
        if not isinstance(saved, Mapping):
            continue
        decision = saved.get("decision")
        if decision in decision_counts:
            decision_counts[str(decision)] += 1
            matching_decision_recorded = True
        summary = {
            "candidate_id": candidate_id,
            "display_letter": display_letters[candidate_id],
        }
        selected_decision = decision in {"main", "optional"}
        selection_active = (
            selected_decision
            and not terminal_outcome
            and saved.get("selection_active") is not False
        )
        if selected_decision and not selection_active:
            inactive_selected_count += 1
        if candidate.get("audition_blocked"):
            if selected_decision:
                blocked_selected_count += 1
            continue
        if (
            selection_active
            and decision == "main"
            and candidate_id == main_candidate_id
        ):
            main = summary
            selected_contexts.append(str(saved.get("context") or "solo"))
        elif selection_active and decision == "optional":
            optional.append(summary)
            selected_contexts.append(str(saved.get("context") or "solo"))

    decision_recorded = matching_decision_recorded or outcome_value is not None
    selected_part_count = int(main is not None) + len(optional)
    needs_full_mix = sum(context != "full_mix" for context in selected_contexts)
    attention_code = _attention_code(
        candidate_count=len(candidates),
        decision_recorded=decision_recorded,
        selected_part_count=selected_part_count,
        needs_full_mix_count=needs_full_mix,
        outcome=outcome_value,
    )

    heard_role, heard_role_redacted = path_free_role(
        state.get("role") or stem.get("role") or "unclassified"
    )
    return {
        "stem_id": str(stem.get("stem_id", "")),
        "heard_role": heard_role,
        "heard_role_redacted": heard_role_redacted,
        "candidate_count": len(candidates),
        "decision_recorded": decision_recorded,
        "main": main,
        "optional": optional,
        "decision_counts": decision_counts,
        "outcome": outcome_value,
        "selected_main_count": int(main is not None),
        "selected_optional_count": len(optional),
        "selected_part_count": selected_part_count,
        "selected_needing_full_mix_count": needs_full_mix,
        "blocked_selected_count": blocked_selected_count,
        "inactive_selected_count": inactive_selected_count,
        "attention_code": attention_code,
    }


def _attention_code(
    *,
    candidate_count: int,
    decision_recorded: bool,
    selected_part_count: int,
    needs_full_mix_count: int,
    outcome: Any,
) -> str:
    if candidate_count <= 0:
        return "no-candidates"
    if not decision_recorded:
        return "compare-candidates"
    if selected_part_count <= 0:
        if outcome == "none_usable":
            return "no-usable-selection"
        if outcome == "cannot_tell":
            return "listening-inconclusive"
        return "no-active-selection"
    if needs_full_mix_count:
        return "hear-in-arrangement"
    return "ready-for-pack"


def _next_step(
    rows: Sequence[Mapping[str, Any]],
    *,
    selected_part_count: int,
    needs_full_mix_count: int,
) -> dict[str, Any]:
    compare = next(
        (row for row in rows if row.get("attention_code") == "compare-candidates"),
        None,
    )
    if compare is not None:
        return {
            "action": "compare-stem",
            "reason_code": "unreviewed-candidate-stem",
            "stem_id": compare["stem_id"],
        }
    unresolved = next(
        (row for row in rows if row.get("attention_code") == "no-active-selection"),
        None,
    )
    if unresolved is not None:
        return {
            "action": "compare-stem",
            "reason_code": "no-active-selection",
            "stem_id": unresolved["stem_id"],
        }
    if selected_part_count <= 0:
        has_terminal_outcome = any(
            row.get("outcome") in TERMINAL_NO_SELECTION_OUTCOMES for row in rows
        )
        return {
            "action": "no-results",
            "reason_code": (
                "explicit-no-selection-outcomes"
                if has_terminal_outcome
                else "no-selected-midi"
            ),
        }
    if needs_full_mix_count:
        return {
            "action": "hear-arrangement",
            "reason_code": "selected-parts-need-full-mix-listening",
        }
    return {
        "action": "compose-pack",
        "reason_code": "selected-parts-confirmed-in-full-mix",
    }


def _candidate_display_letters(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    ordered = [candidate for candidate in candidates if candidate.get("primary")]
    ordered.extend(candidate for candidate in candidates if not candidate.get("primary"))
    return {
        str(candidate.get("candidate_id", "")): _display_letter(index)
        for index, candidate in enumerate(ordered)
    }


def _display_letter(index: int) -> str:
    value = index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
