"""Bounded objective admission and non-blocking feedback policy for profiles."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


ROLLOUT_POLICY_ID = "core-four-public-preview-rollout-v1"
CANARY_CATEGORIES = {"vocal_forward", "dense_or_electronic", "acoustic_or_mixed"}
STOP_SHIP_GATES = {
    "licence_and_hash_consistent",
    "inference_network_denied",
    "source_unchanged_and_private",
    "all_roles_present_and_finite",
    "clocks_match",
    "reconstruction_accounting_passed",
    "supported_machine_no_reproducible_crash_or_oom",
}
MAXIMUM_SECONDS_PER_AUDIO_MINUTE = 120.0
MAXIMUM_SECONDS_PER_SONG = 900.0
MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES = 12 * 1024**3


def evaluate_preview_admission(record: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate only objective gates; usefulness scores are intentionally ignored."""

    failures: list[str] = []
    if record.get("policy_id") != ROLLOUT_POLICY_ID:
        failures.append("policy_id")
    if record.get("baseline_configuration_count") != 1:
        failures.append("baseline_configuration_count")
    remediation = record.get("remediation_cycles")
    if not isinstance(remediation, int) or isinstance(remediation, bool) or not 0 <= remediation <= 1:
        failures.append("remediation_cycles")

    gates = record.get("objective_gates")
    if not isinstance(gates, Mapping) or set(gates) != STOP_SHIP_GATES:
        failures.append("objective_gates")
    elif any(gates[name] is not True for name in STOP_SHIP_GATES):
        failures.extend(sorted(name for name in STOP_SHIP_GATES if gates[name] is not True))

    synthetic = record.get("synthetic_demo")
    if not isinstance(synthetic, Mapping) or synthetic.get("passed") is not True:
        failures.append("synthetic_demo")

    canaries = record.get("authorised_song_canaries")
    if not isinstance(canaries, Sequence) or isinstance(canaries, (str, bytes)) or len(canaries) != 3:
        failures.append("authorised_song_canaries")
    else:
        categories = {item.get("category") for item in canaries if isinstance(item, Mapping)}
        hashes = {item.get("source_sha256") for item in canaries if isinstance(item, Mapping)}
        if categories != CANARY_CATEGORIES or len(hashes) != 3:
            failures.append("song_disjoint_coverage")
        for index, canary in enumerate(canaries):
            if (
                not isinstance(canary, Mapping)
                or canary.get("authorised") is not True
                or canary.get("catastrophic_listen_complete") is not True
                or canary.get("mislabelled_corrupt_silent_or_mistimed") is not False
                or not _resource_run_passes(canary)
            ):
                failures.append(f"canary_{index + 1}")

    repeats = record.get("repeat_resource_runs")
    if not isinstance(repeats, Sequence) or isinstance(repeats, (str, bytes)) or len(repeats) != 3:
        failures.append("repeat_resource_runs")
    else:
        machine_ids = set()
        source_hashes = set()
        for index, run in enumerate(repeats):
            if not isinstance(run, Mapping):
                failures.append(f"repeat_{index + 1}")
                continue
            machine_ids.add(run.get("machine_id"))
            source_hashes.add(run.get("source_sha256"))
            if (
                not isinstance(run.get("machine_memory_bytes"), int)
                or run["machine_memory_bytes"] < 16 * 1024**3
                or not _resource_run_passes(run)
            ):
                failures.append(f"repeat_{index + 1}")
        if len(machine_ids) != 1 or len(source_hashes) != 1:
            failures.append("repeat_resource_identity")

    unique_failures = sorted(set(failures))
    objective_passed = not unique_failures
    if objective_passed:
        decision = "admit_public_opt_in"
    elif remediation == 0:
        decision = "one_remediation_cycle_available"
    else:
        decision = "switch_to_fallback_backend"
    return {
        "policy_id": ROLLOUT_POLICY_ID,
        "objective_gates_passed": objective_passed,
        "decision": decision,
        "failures": unique_failures,
        "subjective_feedback_considered_for_admission": False,
        "minimum_usefulness_rating": None,
        "pre_release_configuration_limit": 1,
        "pre_release_remediation_cycle_limit": 1,
    }


def feedback_rollout_action(
    *,
    days_since_activation: int,
    valid_report_count: int,
    repeated_poor_musical_feedback: bool,
    objectively_qualified_replacement_exists: bool,
) -> dict[str, Any]:
    if min(days_since_activation, valid_report_count) < 0:
        raise ValueError("feedback review counters cannot be negative")
    review_due = days_since_activation >= 30 or valid_report_count >= 10
    poor_action = review_due and repeated_poor_musical_feedback
    demotion_permitted = poor_action and objectively_qualified_replacement_exists
    return {
        "review_due": review_due,
        "trigger": "30_days_or_10_valid_reports_whichever_first",
        "development_continues_if_ten_reports_never_arrive": True,
        "baseline_remains_accessible": not demotion_permitted,
        "publish_known_limitation": poor_action,
        "run_one_bounded_challenger": poor_action,
        "demotion_permitted": demotion_permitted,
        "automatic_model_choice_written": False,
    }


def _resource_run_passes(run: Mapping[str, Any]) -> bool:
    duration = run.get("duration_seconds")
    elapsed = run.get("elapsed_seconds")
    memory = run.get("peak_unified_memory_bytes")
    if (
        type(duration) not in (int, float)
        or type(elapsed) not in (int, float)
        or not isinstance(memory, int)
        or not math.isfinite(float(duration))
        or not math.isfinite(float(elapsed))
        or float(duration) <= 0
        or float(elapsed) < 0
    ):
        return False
    limit = min(
        MAXIMUM_SECONDS_PER_SONG,
        float(duration) * MAXIMUM_SECONDS_PER_AUDIO_MINUTE / 60.0,
    )
    return float(elapsed) <= limit and memory <= MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES


__all__ = [
    "CANARY_CATEGORIES",
    "MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES",
    "MAXIMUM_SECONDS_PER_AUDIO_MINUTE",
    "MAXIMUM_SECONDS_PER_SONG",
    "ROLLOUT_POLICY_ID",
    "STOP_SHIP_GATES",
    "evaluate_preview_admission",
    "feedback_rollout_action",
]
