from __future__ import annotations

from copy import deepcopy

from sunofriend.separation_rollout import (
    ROLLOUT_POLICY_ID,
    STOP_SHIP_GATES,
    evaluate_preview_admission,
    feedback_rollout_action,
)


def _passing_record() -> dict:
    canaries = []
    for index, category in enumerate(
        ("vocal_forward", "dense_or_electronic", "acoustic_or_mixed")
    ):
        canaries.append(
            {
                "category": category,
                "source_sha256": f"{index + 1:064x}",
                "authorised": True,
                "catastrophic_listen_complete": True,
                "mislabelled_corrupt_silent_or_mistimed": False,
                "duration_seconds": 180.0,
                "elapsed_seconds": 300.0,
                "peak_unified_memory_bytes": 8 * 1024**3,
                "subjective_usefulness": "not_useful",
            }
        )
    repeats = [
        {
            "machine_id": "first-supported-16-gib-class",
            "machine_memory_bytes": 16 * 1024**3,
            "source_sha256": canaries[0]["source_sha256"],
            "duration_seconds": 180.0,
            "elapsed_seconds": 320.0 + index,
            "peak_unified_memory_bytes": 9 * 1024**3,
        }
        for index in range(3)
    ]
    return {
        "policy_id": ROLLOUT_POLICY_ID,
        "baseline_configuration_count": 1,
        "remediation_cycles": 0,
        "objective_gates": {name: True for name in STOP_SHIP_GATES},
        "synthetic_demo": {"passed": True},
        "authorised_song_canaries": canaries,
        "repeat_resource_runs": repeats,
    }


def test_poor_subjective_canaries_do_not_block_objective_preview_admission() -> None:
    result = evaluate_preview_admission(_passing_record())

    assert result["objective_gates_passed"] is True
    assert result["decision"] == "admit_public_opt_in"
    assert result["subjective_feedback_considered_for_admission"] is False
    assert result["minimum_usefulness_rating"] is None


def test_objective_failure_allows_one_remediation_then_switches_backend() -> None:
    record = _passing_record()
    record["objective_gates"]["inference_network_denied"] = False

    first = evaluate_preview_admission(record)
    record["remediation_cycles"] = 1
    second = evaluate_preview_admission(record)

    assert first["decision"] == "one_remediation_cycle_available"
    assert second["decision"] == "switch_to_fallback_backend"
    assert "inference_network_denied" in second["failures"]


def test_resource_ceiling_is_an_objective_stop_ship_gate() -> None:
    record = deepcopy(_passing_record())
    record["authorised_song_canaries"][1]["elapsed_seconds"] = 901.0

    result = evaluate_preview_admission(record)

    assert result["objective_gates_passed"] is False
    assert "canary_2" in result["failures"]


def test_feedback_review_never_demotes_last_functioning_profile() -> None:
    early = feedback_rollout_action(
        days_since_activation=7,
        valid_report_count=3,
        repeated_poor_musical_feedback=True,
        objectively_qualified_replacement_exists=False,
    )
    due = feedback_rollout_action(
        days_since_activation=30,
        valid_report_count=2,
        repeated_poor_musical_feedback=True,
        objectively_qualified_replacement_exists=False,
    )
    replaceable = feedback_rollout_action(
        days_since_activation=12,
        valid_report_count=10,
        repeated_poor_musical_feedback=True,
        objectively_qualified_replacement_exists=True,
    )

    assert early["review_due"] is False
    assert due["baseline_remains_accessible"] is True
    assert due["publish_known_limitation"] is True
    assert due["run_one_bounded_challenger"] is True
    assert replaceable["demotion_permitted"] is True
