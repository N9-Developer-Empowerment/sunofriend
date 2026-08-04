from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from sunofriend._separation_authorised_midi_comparison import (
    _document_sha256,
    _sha256,
)
from sunofriend._separation_human_listening_coverage import (
    SCHEMA as HUMAN_LISTENING_SCHEMA,
)
from sunofriend._separation_full_song_resource_benchmark_result import (
    SCHEMA as RESOURCE_RESULT_SCHEMA,
    STATUS as RESOURCE_RESULT_STATUS,
)
from sunofriend._separation_full_song_review import (
    SCHEMA as FULL_SONG_REVIEW_SCHEMA,
    STATUS as FULL_SONG_REVIEW_STATUS,
)
from sunofriend._separation_full_song_alignment import (
    FEATURE_FRAME_MILLISECONDS,
    FEATURE_HOP_MILLISECONDS,
    MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
    MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
    MAXIMUM_SEARCH_LAG_MILLISECONDS,
    MINIMUM_ACCEPTED_WINDOW_CORRELATION,
    MINIMUM_ACTIVE_RMS_DBFS,
    POLICY_ID as FULL_SONG_ALIGNMENT_POLICY_ID,
    SCHEMA as FULL_SONG_ALIGNMENT_SCHEMA,
    STATUS as FULL_SONG_ALIGNMENT_STATUS,
)
from sunofriend._separation_full_song_join_remediation_review import (
    POLICY_ID as JOIN_REMEDIATION_POLICY_ID,
)
from sunofriend._separation_full_song_join_remediation_review_result import (
    RESULT_SCHEMA as JOIN_REMEDIATION_RESULT_SCHEMA,
    RESULT_STATUS as JOIN_REMEDIATION_RESULT_STATUS,
)
from sunofriend._separation_audio_quality_review import (
    POLICY_ID as AUDIO_QUALITY_POLICY_ID,
    RESULT_SCHEMA as AUDIO_QUALITY_RESULT_SCHEMA,
)
from sunofriend._separation_normalized_midi_agreement import (
    SCHEMA as AGREEMENT_SCHEMA,
)
from sunofriend._separation_publication_readiness import (
    SCHEMA,
    _project_private_separation_publication_readiness,
)


def test_projects_passed_and_open_gates_without_enabling_separation(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        out=tmp_path / "readiness.json",
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == "blocked_private_bounded_vocal_midi_evidence_only"
    assert result["readiness"] == {
        "stage": "private_bounded_vocal_research",
        "passed_gate_count": 3,
        "open_gate_count": 8,
        "required_gate_count": 11,
        "publication_ready": False,
        "experimental_studio_route_ready": False,
        "one_action_simple_route_ready": False,
    }
    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["source_bound_cross_song_downstream_midi"] == "passed"
    assert gates["source_bound_cross_song_human_listening"] == "passed"
    assert gates["separator_audio_quality_cross_song"] == "open"
    assert gates["public_cli_tui_simple_studio_route"] == "open"
    assert (
        result["interpretation"]["private_separator_derived_midi_has_useful_evidence"]
        is True
    )
    assert result["interpretation"]["human_usefulness_is_accuracy"] is False
    assert "full_song_join_remediation_assessment" not in result
    assert "full_song_join_remediation_reviewed" not in result["observed_scope"]
    assert (
        "join_remediation_preference_is_absolute_boundary_cleanliness"
        not in result["interpretation"]
    )
    assert (
        "join_remediation_review_can_close_duration_alignment_gate"
        not in result["policy"]
    )
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())

    text = (tmp_path / "readiness.json").read_text(encoding="utf-8")
    persisted = json.loads(text)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in text


def test_writes_fresh_result_in_owner_only_directory_without_overwrite(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    output = tmp_path / "private-result" / "readiness.json"

    _project_private_separation_publication_readiness(
        agreement,
        listening,
        out=output,
    )

    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.stat().st_nlink == 1
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=output,
        )
    assert output.read_bytes() == original


def test_rejects_symbolic_link_input_snapshot(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    linked_agreement = tmp_path / "linked-agreement.json"
    linked_agreement.symlink_to(agreement)

    with pytest.raises(ValueError, match="regular JSON file"):
        _project_private_separation_publication_readiness(
            linked_agreement,
            listening,
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_rejects_listening_report_bound_to_different_agreement(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["inputs"]["normalized_midi_agreement_sha256"] = "f" * 64
    listening = _write_hashed(tmp_path / "wrong-listening.json", document)

    with pytest.raises(ValueError, match="not bound to agreement"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_rejects_incomplete_human_listening_coverage(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["coverage"]["cross_song_review_coverage_complete"] = False
    listening = _write_hashed(tmp_path / "incomplete-listening.json", document)

    with pytest.raises(ValueError, match="coverage contract differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )


def test_rejects_active_input_permissions(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["permissions"]["accepted"] = True
    listening = _write_hashed(tmp_path / "active-listening.json", document)

    with pytest.raises(ValueError, match="listening permissions differ"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )


def test_rejects_forged_coverage_counts(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["coverage"]["reviewed_candidate_count"] = -1
    listening = _write_hashed(tmp_path / "forged-listening.json", document)

    with pytest.raises(ValueError, match="non-negative integer"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )


def test_closes_only_the_audio_gate_for_source_bound_minimum_usable_review(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    audio_quality = _audio_quality(tmp_path, agreement, minimum_usable=True)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        separated_audio_quality_path=audio_quality,
        out=tmp_path / "readiness-with-audio.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["separator_audio_quality_cross_song"] == "passed"
    assert gates["full_song_duration_and_alignment"] == "open"
    assert gates["public_cli_tui_simple_studio_route"] == "open"
    assert result["readiness"]["passed_gate_count"] == 4
    assert result["readiness"]["open_gate_count"] == 7
    assessment = result["separated_audio_quality_assessment"]
    assert assessment["gate_passed"] is True
    assert assessment["minimum_usable_track_count"] == 2
    assert assessment["requirements"]["provider_preference_affects_gate"] is False
    persisted = (tmp_path / "readiness-with-audio.json").read_text()
    assert "Private listening note" not in persisted
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())


def test_completed_audio_review_stays_open_when_one_kim_excerpt_is_partial(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    audio_quality = _audio_quality(tmp_path, agreement, minimum_usable=False)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        separated_audio_quality_path=audio_quality,
        out=tmp_path / "readiness-audio-open.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["separator_audio_quality_cross_song"] == "open"
    assert result["readiness"]["passed_gate_count"] == 3
    assert result["separated_audio_quality_assessment"]["gate_passed"] is False


def test_records_completed_full_song_review_but_keeps_audible_join_gate_open(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=False)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        full_song_review_result_path=full_song,
        out=tmp_path / "readiness-with-full-song.json",
    )

    gates = {gate["gate_id"]: gate for gate in result["gates"]}
    assert gates["full_song_duration_and_alignment"]["status"] == "open"
    assessment = result["full_song_duration_alignment_assessment"]
    assert assessment["exact_duration_and_frame_count_verified"] is True
    assert assessment["full_song_and_boundary_listening_complete"] is True
    assert assessment["all_full_song_outputs_useful"] is True
    assert assessment["all_role_boundaries_clean"] is False
    assert assessment["audible_join_boundaries_by_role"] == {
        "vocals": [2],
        "instrumental": [2],
        "reconstruction": [],
    }
    assert assessment["review_minimum_met"] is False
    assert assessment["gate_passed"] is False
    assert assessment["acceptance_gate_closed"] is False
    assert assessment["separator_accepted"] is False
    assert result["readiness"]["passed_gate_count"] == 3
    assert result["readiness"]["open_gate_count"] == 8
    persisted = (tmp_path / "readiness-with-full-song.json").read_text()
    assert "Private full-song note" not in persisted
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())


def test_clean_useful_full_song_review_still_cannot_claim_source_alignment(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=True)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        full_song_review_result_path=full_song,
        out=tmp_path / "readiness-clean-full-song.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["full_song_duration_and_alignment"] == "open"
    assert gates["broad_role_coverage"] == "open"
    assert gates["public_cli_tui_simple_studio_route"] == "open"
    assert result["readiness"]["passed_gate_count"] == 3
    assert result["readiness"]["open_gate_count"] == 8
    assert result["readiness"]["publication_ready"] is False
    assessment = result["full_song_duration_alignment_assessment"]
    assert assessment["review_minimum_met"] is True
    assert assessment["source_to_output_alignment_verified"] is False
    assert assessment["drift_acceptance_complete"] is False
    assert assessment["gate_passed"] is False
    assert assessment["acceptance_gate_closed"] is False
    assert (
        result["interpretation"]["full_song_gate_pass_is_separator_acceptance"] is False
    )
    assert result["policy"]["full_song_review_can_select_or_accept_separator"] is False
    assert (
        result["policy"]["full_song_review_can_close_duration_alignment_gate"] is False
    )
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())


def test_matching_review_and_alignment_close_only_full_song_milestone(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=True)
    alignment = _full_song_alignment_result(tmp_path, gate_passed=True)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        full_song_review_result_path=full_song,
        full_song_alignment_result_path=alignment,
        out=tmp_path / "readiness-with-alignment.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["full_song_duration_and_alignment"] == "passed"
    assert gates["broad_role_coverage"] == "open"
    assert gates["public_cli_tui_simple_studio_route"] == "open"
    assert result["readiness"]["passed_gate_count"] == 4
    assert result["readiness"]["open_gate_count"] == 7
    assert result["readiness"]["publication_ready"] is False
    review_assessment = result["full_song_duration_alignment_assessment"]
    assert review_assessment["review_minimum_met"] is True
    assert review_assessment["source_to_output_alignment_verified"] is True
    assert review_assessment["drift_acceptance_complete"] is True
    assert review_assessment["gate_passed"] is True
    assert review_assessment["separator_accepted"] is False
    alignment_assessment = result["full_song_alignment_assessment"]
    assert alignment_assessment["gate_passed"] is True
    assert alignment_assessment["separator_accuracy_established"] is False
    assert (
        result["policy"]["alignment_result_alone_can_close_duration_alignment_gate"]
        is False
    )
    assert (
        result["policy"][
            "matching_review_and_alignment_can_close_duration_alignment_gate"
        ]
        is True
    )


def test_alignment_alone_or_audible_joins_keep_full_song_milestone_open(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=False)
    alignment = _full_song_alignment_result(tmp_path, gate_passed=True)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        full_song_review_result_path=full_song,
        full_song_alignment_result_path=alignment,
        out=tmp_path / "readiness-audible-joins.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["full_song_duration_and_alignment"] == "open"
    assert result["full_song_alignment_assessment"]["gate_passed"] is True
    assert result["full_song_duration_alignment_assessment"]["gate_passed"] is False


def test_records_bound_join_remediation_without_closing_full_song_gate(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(
        tmp_path,
        all_boundaries_clean=False,
        audible_join_boundaries_by_role={
            "vocals": (11, 12),
            "instrumental": (11, 13),
        },
    )
    remediation = _join_remediation_review_result(tmp_path, full_song)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        full_song_review_result_path=full_song,
        full_song_join_remediation_review_result_path=remediation,
        out=tmp_path / "readiness-with-join-remediation.json",
    )

    gates = {gate["gate_id"]: gate for gate in result["gates"]}
    assert gates["full_song_duration_and_alignment"]["status"] == "open"
    assert (
        "comparative preference is not an absolute clean-boundary rating"
        in gates["full_song_duration_and_alignment"]["finding"]
    )
    assert result["readiness"]["passed_gate_count"] == 3
    assert result["readiness"]["open_gate_count"] == 8
    original = result["full_song_duration_alignment_assessment"]
    assert original["audible_join_boundaries_by_role"] == {
        "vocals": [11, 12],
        "instrumental": [11, 13],
        "reconstruction": [],
    }
    assert original["review_minimum_met"] is False
    assert original["gate_passed"] is False
    assessment = result["full_song_join_remediation_assessment"]
    assert assessment["reviewed_unit_count"] == 15
    assert assessment["candidate_preferred_boundary_role_count"] == 2
    assert assessment["equivalent_boundary_role_count"] == 2
    assert assessment["candidate_preferred_boundaries_by_role"] == {
        "vocals": [12],
        "instrumental": [11],
    }
    assert assessment["improvement_not_evidenced_boundaries_by_role"] == {
        "vocals": [11],
        "instrumental": [13],
    }
    assert assessment["no_heard_regression"] is True
    assert assessment["absolute_boundary_cleanliness_established"] is False
    assert assessment["original_audible_joins_resolved"] is False
    assert assessment["can_close_duration_alignment_gate"] is False
    assert result["readiness"]["publication_ready"] is False
    persisted = (tmp_path / "readiness-with-join-remediation.json").read_text()
    assert "Private remediation note" not in persisted


def test_join_remediation_requires_original_full_song_review(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(
        tmp_path,
        all_boundaries_clean=False,
        audible_join_boundaries_by_role={
            "vocals": (11, 12),
            "instrumental": (11, 13),
        },
    )
    remediation = _join_remediation_review_result(tmp_path, full_song)

    with pytest.raises(ValueError, match="requires a full-song review result"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            full_song_join_remediation_review_result_path=remediation,
            out=tmp_path / "rejected.json",
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "unit_set",
        "windows",
        "counts",
        "package_commitment",
        "readiness",
        "permissions",
        "effects",
        "bindings",
    ),
)
def test_rejects_altered_join_remediation_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(
        tmp_path,
        all_boundaries_clean=False,
        audible_join_boundaries_by_role={
            "vocals": (11, 12),
            "instrumental": (11, 13),
        },
    )
    remediation = _join_remediation_review_result(tmp_path, full_song)
    document = json.loads(remediation.read_text(encoding="utf-8"))
    if mutation == "unit_set":
        document["units"][9]["unit_id"] = "boundary-14-instrumental"
    elif mutation == "windows":
        for unit in document["units"]:
            if unit["source_window"] is not None:
                unit["source_window"] = {
                    "start_frame": 0,
                    "end_frame": 176_400,
                    "start_seconds": 0.0,
                    "end_seconds": 4.0,
                }
    elif mutation == "counts":
        document["overall_outcome_counts"]["equivalent"] += 1
    elif mutation == "package_commitment":
        document["package_commitment"] = "0" * 64
    elif mutation == "readiness":
        document["readiness_evidence"][
            "all_targeted_join_pairs_candidate_preferred"
        ] = True
    elif mutation == "permissions":
        document["permissions"]["accepted"] = True
    elif mutation == "effects":
        document["effects"]["readiness_gate_closed"] = True
    else:
        document["bindings"]["stitch_report_sha256"] = "f" * 64
    remediation = _write_hashed(
        tmp_path / f"altered-join-remediation-{mutation}.json", document
    )

    with pytest.raises(ValueError, match="join-remediation"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            full_song_review_result_path=full_song,
            full_song_join_remediation_review_result_path=remediation,
            out=tmp_path / f"rejected-{mutation}.json",
        )


def test_rejects_alignment_not_bound_to_full_song_review(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=True)
    alignment = _full_song_alignment_result(tmp_path, gate_passed=True)
    document = json.loads(alignment.read_text(encoding="utf-8"))
    document["bindings"]["stitch_report_sha256"] = "f" * 64
    alignment = _write_hashed(tmp_path / "wrong-alignment-binding.json", document)

    with pytest.raises(ValueError, match="binding differs from review"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            full_song_review_result_path=full_song,
            full_song_alignment_result_path=alignment,
            out=tmp_path / "rejected.json",
        )


def test_rejects_forged_full_song_quality_acceptance(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=True)
    document = json.loads(full_song.read_text(encoding="utf-8"))
    document["readiness"]["full_song_quality_accepted"] = True
    full_song = _write_hashed(tmp_path / "forged-full-song.json", document)

    with pytest.raises(ValueError, match="full-song review result differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            full_song_review_result_path=full_song,
            out=tmp_path / "rejected.json",
        )


def test_rejects_full_song_boundary_summary_that_differs_from_units(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    full_song = _full_song_review_result(tmp_path, all_boundaries_clean=False)
    document = json.loads(full_song.read_text(encoding="utf-8"))
    document["boundary_summary"]["rating_counts_by_role"]["vocals"] = {
        "audible_join": 0,
        "cannot_tell": 0,
        "clean": 2,
    }
    full_song = _write_hashed(tmp_path / "forged-summary.json", document)

    with pytest.raises(ValueError, match="full-song review result differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            full_song_review_result_path=full_song,
            out=tmp_path / "rejected.json",
        )


def test_records_controlled_development_resources_without_closing_gate(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    resources = _resource_result(tmp_path)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        resource_benchmark_result_path=resources,
        out=tmp_path / "readiness-with-resources.json",
    )

    gates = {gate["gate_id"]: gate for gate in result["gates"]}
    resource_gate = gates["resource_envelope_acceptance"]
    assert resource_gate["status"] == "open"
    assert "36 GiB" not in resource_gate["finding"]
    assert "16 GiB acceptance class was not observed" in resource_gate["finding"]
    assessment = result["resource_benchmark_assessment"]
    assert assessment["machine_class_id"] == "apple-silicon-36gib"
    assert assessment["controlled_repetitions_observed"] == 3
    assert assessment["development_machine_thresholds_met"] is True
    assert assessment["required_16_gib_acceptance_class_observed"] is False
    assert assessment["resource_envelope_accepted"] is False
    assert assessment["acceptance_gate_closed"] is False
    assert assessment["maximum_peak_total_unified_memory_gib"] == 3.812089
    assert result["readiness"]["passed_gate_count"] == 3
    assert result["readiness"]["open_gate_count"] == 8
    assert result["readiness"]["publication_ready"] is False
    assert (
        result["policy"]["development_resource_result_can_close_acceptance_gate"]
        is False
    )
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())


def test_rejects_forged_resource_acceptance_on_development_machine(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    resources = _resource_result(tmp_path)
    document = json.loads(resources.read_text(encoding="utf-8"))
    document["readiness"]["resource_envelope_accepted"] = True
    resources = _write_hashed(tmp_path / "forged-resource.json", document)

    with pytest.raises(ValueError, match="resource benchmark result differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            resource_benchmark_result_path=resources,
            out=tmp_path / "rejected.json",
        )


def test_records_mixed_repetition_thresholds_as_development_failure(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    resources = _resource_result(tmp_path)
    document = json.loads(resources.read_text(encoding="utf-8"))
    document["repetitions"][1]["within_frozen_thresholds"] = False
    document["coverage"]["development_machine_thresholds_met"] = False
    document["readiness"]["development_machine_thresholds_met"] = False
    resources = _write_hashed(tmp_path / "mixed-threshold-resources.json", document)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        resource_benchmark_result_path=resources,
        out=tmp_path / "readiness-mixed-thresholds.json",
    )

    gates = {gate["gate_id"]: gate for gate in result["gates"]}
    assert gates["resource_envelope_acceptance"]["status"] == "open"
    assert (
        result["resource_benchmark_assessment"]["development_machine_thresholds_met"]
        is False
    )
    assert result["resource_benchmark_assessment"]["acceptance_gate_closed"] is False
    assert result["readiness"]["publication_ready"] is False


def test_rejects_audio_review_bound_to_different_excerpt(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    audio_quality = _audio_quality(tmp_path, agreement, minimum_usable=True)
    document = json.loads(audio_quality.read_text(encoding="utf-8"))
    document["units"][0]["source_binding"]["authorised_excerpt_sha256"] = "f" * 64
    audio_quality = _write_hashed(tmp_path / "wrong-audio.json", document)

    with pytest.raises(ValueError, match="source binding differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            separated_audio_quality_path=audio_quality,
            out=tmp_path / "rejected.json",
        )


def _agreement(root: Path) -> Path:
    document = {
        "schema": AGREEMENT_SCHEMA,
        "status": "complete_pairwise_agreement_not_quality_or_acceptance",
        "evidence_scope": "private_development_only",
        "comparison_contract": {
            "quality_comparison_permitted": False,
            "method_ranking_permitted": False,
        },
        "cells": [
            _agreement_cell("track-a", "source-a", "a", "b", "c", "d"),
            _agreement_cell("track-b", "source-b", "e", "f", "0", "1"),
        ],
        "publication_gate": {"status": "open"},
        "permissions": _permissions(),
        "effects": _agreement_effects(),
    }
    return _write_hashed(root / "agreement.json", document)


def _agreement_cell(
    track_id: str,
    source_track_id: str,
    excerpt_file: str,
    excerpt_document: str,
    mapping_file: str,
    mapping_document: str,
) -> dict[str, object]:
    return {
        "track_id": track_id,
        "source_track_id": source_track_id,
        "source_binding": {
            "authorised_excerpt_sha256": excerpt_file * 64,
            "authorised_excerpt_document_sha256": excerpt_document * 64,
            "role_mapping_sha256": mapping_file * 64,
            "role_mapping_document_sha256": mapping_document * 64,
        },
    }


def _listening(root: Path, agreement: Path) -> Path:
    agreement_document = json.loads(agreement.read_text(encoding="utf-8"))
    document = {
        "schema": HUMAN_LISTENING_SCHEMA,
        "status": "complete_human_listening_projection_not_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "normalized_midi_agreement_sha256": _sha256(agreement),
            "normalized_midi_agreement_document_sha256": agreement_document[
                "document_sha256"
            ],
        },
        "review_windows": [
            {"track_id": "track-a"},
            {"track_id": "track-b"},
        ],
        "coverage": {
            "agreement_track_count": 2,
            "reviewed_track_count": 2,
            "review_window_count": 2,
            "reviewed_candidate_count": 7,
            "useful_for_focus_count": 3,
            "structured_focus_phrase_coverage_window_count": 2,
            "all_reviews_record_focus_phrase_coverage": True,
            "all_reviewed_tracks_are_bound_to_normalized_excerpt": True,
            "cross_song_review_coverage_complete": True,
        },
        "publication_gate": {"status": "open"},
        "permissions": _permissions(),
        "effects": {
            **_agreement_effects(),
            "review_notes_copied": False,
        },
    }
    return _write_hashed(root / "listening.json", document)


def _audio_quality(
    root: Path,
    agreement: Path,
    *,
    minimum_usable: bool,
) -> Path:
    agreement_document = json.loads(agreement.read_text(encoding="utf-8"))
    units = []
    for index, cell in enumerate(agreement_document["cells"]):
        binding = dict(cell["source_binding"])
        binding.update(
            {
                "track_id": cell["track_id"],
                "source_track_id": cell["source_track_id"],
                "provider_id": "moises",
                "start_seconds": 10.0 + index,
                "end_seconds": 10.5 + index,
                "candidate_evaluation_sha256": "2" * 64,
                "candidate_evaluation_document_sha256": "3" * 64,
                "source_audio_sha256": "4" * 64,
                "candidate_audio_sha256": "5" * 64,
                "provider_audio_sha256": "6" * 64,
            }
        )
        retention = (
            "partially_complete"
            if index == 1 and not minimum_usable
            else "substantially_complete"
        )
        units.append(
            {
                "unit_id": f"0{index + 1}-{cell['track_id']}",
                "track_id": cell["track_id"],
                "source_track_id": cell["source_track_id"],
                "source_seconds": [10.0 + index, 10.5 + index],
                "source_binding": binding,
                "candidate_a_method": "kim-vocal-2",
                "candidate_b_method": "provider-moises-broad-vocals",
                "ratings_by_method": {
                    "kim-vocal-2": {
                        "vocal_retention": retention,
                        "non_vocal_bleed": "noticeable",
                        "artefacts": "low",
                    },
                    "provider-moises-broad-vocals": {
                        "vocal_retention": "substantially_complete",
                        "non_vocal_bleed": "low",
                        "artefacts": "noticeable",
                    },
                },
                "preference": "candidate_b",
                "resolved_preference": "provider-moises-broad-vocals",
                "notes": "Private listening note",
            }
        )
    document = {
        "schema": AUDIO_QUALITY_RESULT_SCHEMA,
        "status": "complete_review_no_activation",
        "evidence_scope": "private_development_only",
        "policy_id": AUDIO_QUALITY_POLICY_ID,
        "unit_count": len(units),
        "units": units,
        "permissions": _permissions(),
        "effects": {**_agreement_effects(), "separator_selected": False},
    }
    return _write_hashed(root / "audio-quality.json", document)


def _full_song_review_result(
    root: Path,
    *,
    all_boundaries_clean: bool,
    audible_join_boundaries_by_role: dict[str, tuple[int, ...]] | None = None,
) -> Path:
    roles = ("vocals", "instrumental", "reconstruction")
    ratings = {role: "useful" for role in roles}
    if audible_join_boundaries_by_role is None:
        audible_join_boundaries_by_role = {
            "vocals": () if all_boundaries_clean else (2,),
            "instrumental": () if all_boundaries_clean else (2,),
        }
        boundary_frames = (58_800, 117_600)
        total_frames = 176_400
    else:
        assert not all_boundaries_clean
        maximum_boundary = max(
            boundary
            for boundaries in audible_join_boundaries_by_role.values()
            for boundary in boundaries
        )
        boundary_frames = tuple(
            index * 44_100 for index in range(1, maximum_boundary + 1)
        )
        total_frames = (maximum_boundary + 3) * 44_100
    boundaries = []
    for index, frame in enumerate(boundary_frames, start=1):
        boundary_ratings = {role: "clean" for role in roles}
        for role, audible_boundaries in audible_join_boundaries_by_role.items():
            if index in audible_boundaries:
                boundary_ratings[role] = "audible_join"
        boundaries.append(
            {
                "boundary_index": index,
                "frame": frame,
                "seconds": frame / 44_100,
                "ratings": boundary_ratings,
                "notes": "Private boundary note",
            }
        )
    counts = {
        role: {
            "audible_join": sum(
                boundary["ratings"][role] == "audible_join" for boundary in boundaries
            ),
            "cannot_tell": 0,
            "clean": sum(
                boundary["ratings"][role] == "clean" for boundary in boundaries
            ),
        }
        for role in roles
    }
    audible_joins = {
        role: [
            boundary["boundary_index"]
            for boundary in boundaries
            if boundary["ratings"][role] == "audible_join"
        ]
        for role in roles
    }
    document = {
        "schema": FULL_SONG_REVIEW_SCHEMA,
        "status": FULL_SONG_REVIEW_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "stitch_report_sha256": "1" * 64,
            "stitch_document_sha256": "2" * 64,
            "review_seed_sha256": "3" * 64,
            "review_export_sha256": "4" * 64,
            "package_commitment": "5" * 64,
            "plan_document_sha256": "6" * 64,
            "execution_state_sha256": "7" * 64,
        },
        "clock": {
            "boundary_count": len(boundary_frames),
            "channels": 2,
            "chunk_count": len(boundary_frames) + 1,
            "crossfade_frames": 0,
            "duration_seconds": total_frames / 44_100,
            "frames": total_frames,
            "gap_frames": 0,
            "overlap_frames": 0,
            "sample_rate": 44_100,
        },
        "full_song": {
            "heard_all": True,
            "ratings": ratings,
            "notes": "Private full-song note",
        },
        "boundary_summary": {
            "reviewed_boundaries": len(boundary_frames),
            "rating_counts_by_role": counts,
            "audible_join_boundaries_by_role": audible_joins,
        },
        "boundaries": boundaries,
        "readiness": {
            "worker_runs_complete": True,
            "stitched_outputs_complete": True,
            "exact_duration_and_frame_count_verified": True,
            "full_song_and_boundary_listening_complete": True,
            "full_song_quality_accepted": False,
            "publication_ready": False,
        },
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "clean_boundary_is_separator_accuracy": False,
            "review_completion_is_quality_acceptance": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": {
            "accepted": False,
            "automatic_selection": False,
            "product_route_permitted": False,
            "publication_permitted": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "product_contract_mutated": False,
            "publication_state_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_audio_mutated": False,
            "source_graph_mutated": False,
            "stitched_audio_mutated": False,
        },
    }
    return _write_hashed(root / "full-song-review.json", document)


def _join_remediation_review_result(root: Path, full_song_review: Path) -> Path:
    review = json.loads(full_song_review.read_text(encoding="utf-8"))
    boundary_frames = {
        boundary["boundary_index"]: boundary["frame"]
        for boundary in review["boundaries"]
    }
    targets = sorted(
        (boundary_index, role)
        for role in ("vocals", "instrumental")
        for boundary_index in review["boundary_summary"][
            "audible_join_boundaries_by_role"
        ][role]
    )
    preferred_targets = {(11, "instrumental"), (12, "vocals")}
    units: list[dict[str, object]] = []

    def add_unit(
        *,
        unit_id: str,
        kind: str,
        source_window: dict[str, int | float] | None,
        resolved_choice: str,
    ) -> None:
        units.append(
            {
                "unit_id": unit_id,
                "kind": kind,
                "title": f"Review {unit_id}",
                "focus": "Which version preserves the intended continuity?",
                "source_window": source_window,
                "blind_choice": (
                    "A" if resolved_choice == "candidate_preferred" else resolved_choice
                ),
                "candidate_a_identity": "candidate",
                "candidate_b_identity": "raw",
                "resolved_choice": resolved_choice,
                "notes": "Private remediation note",
            }
        )

    for boundary_index, role in targets:
        boundary_frame = boundary_frames[boundary_index]
        start = boundary_frame - 2 * 44_100
        end = boundary_frame + 2 * 44_100
        boundary_window = {
            "start_frame": start,
            "end_frame": end,
            "start_seconds": start / 44_100,
            "end_seconds": end / 44_100,
        }
        outcome = (
            "candidate_preferred"
            if (boundary_index, role) in preferred_targets
            else "equivalent"
        )
        add_unit(
            unit_id=f"boundary-{boundary_index:02d}-{role}",
            kind="boundary_role_pair",
            source_window=boundary_window,
            resolved_choice=outcome,
        )
        for edge, edge_start, edge_end in (
            ("start", start, boundary_frame),
            ("end", boundary_frame, end),
        ):
            edge_outcome = (
                "candidate_preferred"
                if (boundary_index, role, edge) == (11, "instrumental", "start")
                else "equivalent"
            )
            add_unit(
                unit_id=f"edge-{boundary_index:02d}-{role}-{edge}",
                kind="patch_edge_pair",
                source_window={
                    "start_frame": edge_start,
                    "end_frame": edge_end,
                    "start_seconds": edge_start / 44_100,
                    "end_seconds": edge_end / 44_100,
                },
                resolved_choice=edge_outcome,
            )
    for role in ("vocals", "instrumental", "reconstruction"):
        add_unit(
            unit_id=f"complete-song-{role}",
            kind="complete_song_pair",
            source_window=None,
            resolved_choice=(
                "candidate_preferred" if role == "instrumental" else "equivalent"
            ),
        )

    outcomes = (
        "candidate_preferred",
        "raw_preferred",
        "equivalent",
        "neither",
        "cannot_tell",
    )
    kinds = ("boundary_role_pair", "patch_edge_pair", "complete_song_pair")
    counts = {
        kind: {
            outcome: sum(
                unit["kind"] == kind and unit["resolved_choice"] == outcome
                for unit in units
            )
            for outcome in outcomes
        }
        for kind in kinds
    }
    overall = {
        outcome: sum(unit["resolved_choice"] == outcome for unit in units)
        for outcome in outcomes
    }
    bindings = {
        "answer_key_document_sha256": "a" * 64,
        "answer_key_sha256": "b" * 64,
        "audio_manifest_sha256": "c" * 64,
        "candidate_document_sha256": "d" * 64,
        "candidate_report_sha256": "e" * 64,
        "execution_report_sha256": "0" * 64,
        "execution_state_sha256": "8" * 64,
        "review_export_sha256": "9" * 64,
        "review_seed_sha256": "f" * 64,
        "stitch_document_sha256": review["bindings"]["stitch_document_sha256"],
        "stitch_report_sha256": review["bindings"]["stitch_report_sha256"],
    }
    document = {
        "schema": JOIN_REMEDIATION_RESULT_SCHEMA,
        "status": JOIN_REMEDIATION_RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": JOIN_REMEDIATION_POLICY_ID,
        "blind_review": True,
        "package_commitment": hashlib.sha256(
            f"{'b' * 64}:{'a' * 64}:{'c' * 64}".encode("ascii")
        ).hexdigest(),
        "bindings": bindings,
        "reviewed_unit_count": len(units),
        "counts_by_kind_and_outcome": counts,
        "overall_outcome_counts": overall,
        "units": units,
        "readiness_evidence": {
            "human_join_remediation_review_complete": True,
            "all_targeted_join_pairs_candidate_preferred": False,
            "all_patch_edges_candidate_or_equivalent": True,
            "all_complete_songs_candidate_or_equivalent": True,
            "readiness_reassessment_eligible": True,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "choices_are_human_listening_evidence": True,
            "candidate_preference_is_join_elimination": False,
            "candidate_preference_is_separator_accuracy": False,
            "review_completion_is_quality_acceptance": False,
            "answer_key_opened_only_after_complete_review_verified": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "verification_claims": {
            "review_seed_and_export_bounded_single_read_snapshots": True,
            "review_seed_and_export_no_symlink_follow": True,
            "review_seed_and_export_identity_stable_before_after": True,
            "review_seed_and_export_owner_only_single_link": True,
            "public_semantics_reconstructed_from_verified_sources": True,
            "short_pcm24_pairs_verified_key_blind": True,
            "complete_song_records_verified_key_blind": True,
            "identical_short_pcm24_pairs_rejected": True,
            "answer_key_bounded_single_read_snapshot_verified": True,
            "answer_key_slot_identities_and_levels_verified": True,
            "result_temp_fsynced_before_no_overwrite_publication": True,
            "result_published_by_no_overwrite_hard_link": True,
        },
        "verification_limitations": {
            "execution_candidate_and_stitch_json_snapshot_held": False,
            "wav_descriptors_snapshot_held_across_verification": False,
            "non_snapshot_private_inputs_assumed_quiescent": True,
        },
        "permissions": {
            "accepted": False,
            "automatic_selection": False,
            "product_route_permitted": False,
            "publication_permitted": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "candidate_audio_mutated": False,
            "candidate_audio_selected": False,
            "preference_inferred": False,
            "publication_state_mutated": False,
            "raw_stitch_mutated": False,
            "readiness_gate_closed": False,
            "review_evidence_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
    }
    return _write_hashed(root / "join-remediation-review-result.json", document)


def _full_song_alignment_result(root: Path, *, gate_passed: bool) -> Path:
    sample_rate = 44_100
    total_frames = 176_400
    window_frames = 14_700
    starts = [
        int(round((total_frames - window_frames) * index / 8)) for index in range(9)
    ]
    lag = 0.0 if gate_passed else 50.0
    windows = [
        {
            "window_index": index,
            "song_third": "early" if index <= 3 else "middle" if index <= 6 else "late",
            "start_frame": start,
            "end_frame": start + window_frames,
            "start_seconds": round(start / sample_rate, 6),
            "end_seconds": round((start + window_frames) / sample_rate, 6),
            "source_rms_dbfs": -12.0,
            "reconstruction_rms_dbfs": -13.0,
            "eligible": True,
            "best_lag_milliseconds": lag,
            "peak_normalized_correlation": 0.99,
        }
        for index, start in enumerate(starts, start=1)
    ]
    document = {
        "schema": FULL_SONG_ALIGNMENT_SCHEMA,
        "status": FULL_SONG_ALIGNMENT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": FULL_SONG_ALIGNMENT_POLICY_ID,
        "bindings": {
            "stitch_report_sha256": "1" * 64,
            "stitch_document_sha256": "2" * 64,
            "source_audio_sha256": "8" * 64,
            "reconstruction_audio_sha256": "9" * 64,
            "plan_document_sha256": "6" * 64,
            "execution_state_sha256": "7" * 64,
        },
        "clock": {
            "boundary_count": 2,
            "channels": 2,
            "chunk_count": 3,
            "crossfade_frames": 0,
            "duration_seconds": 4.0,
            "frames": total_frames,
            "gap_frames": 0,
            "overlap_frames": 0,
            "sample_rate": sample_rate,
        },
        "protocol": {
            "comparison": "canonical source versus diagnostic reconstruction",
            "feature": "log spectral-band energy",
            "window_count": 9,
            "window_seconds": round(window_frames / sample_rate, 6),
            "feature_frame_milliseconds": FEATURE_FRAME_MILLISECONDS,
            "feature_hop_milliseconds": FEATURE_HOP_MILLISECONDS,
            "maximum_search_lag_milliseconds": MAXIMUM_SEARCH_LAG_MILLISECONDS,
            "lag_sign": "positive means reconstruction is later than source",
            "source_and_reconstruction_gain_normalized_for_timing": True,
        },
        "thresholds": {
            "minimum_active_rms_dbfs": MINIMUM_ACTIVE_RMS_DBFS,
            "minimum_eligible_window_count": 9,
            "all_song_thirds_required": True,
            "maximum_absolute_lag_milliseconds": MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
            "maximum_lag_spread_milliseconds": MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
            "minimum_window_normalized_correlation": MINIMUM_ACCEPTED_WINDOW_CORRELATION,
        },
        "windows": windows,
        "summary": {
            "eligible_window_count": 9,
            "maximum_absolute_lag_milliseconds": abs(lag),
            "lag_spread_milliseconds": 0.0,
            "minimum_window_normalized_correlation": 0.99,
            "early_middle_late_coverage_complete": True,
        },
        "readiness": {
            "exact_source_and_reconstruction_clock_verified": True,
            "source_to_reconstruction_alignment_verified": gate_passed,
            "drift_acceptance_complete": gate_passed,
            "alignment_gate_passed": gate_passed,
            "separator_accuracy_established": False,
            "publication_ready": False,
        },
        "interpretation": {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "automatic_winner_selected": False,
        },
        "permissions": {
            "accepted": False,
            "automatic_selection": False,
            "product_route_permitted": False,
            "publication_permitted": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "audio_created_or_mutated": False,
            "product_contract_mutated": False,
            "publication_state_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
    }
    return _write_hashed(root / "full-song-alignment.json", document)


def _resource_result(root: Path) -> Path:
    summaries = {
        "parent_observed_full_song_wall_time_seconds": {
            "count": 3,
            "minimum": 172.56133,
            "median": 172.962042,
            "maximum": 173.454702,
        },
        "wall_time_seconds_per_audio_minute": {
            "count": 3,
            "minimum": 39.433576,
            "median": 39.525147,
            "maximum": 39.637729,
        },
        "summed_worker_model_call_seconds": {
            "count": 3,
            "minimum": 53.882378,
            "median": 53.944776,
            "maximum": 53.985068,
        },
        "peak_process_rss_bytes": {
            "count": 3,
            "minimum": 1_118_208_000,
            "median": 1_124_237_312,
            "maximum": 1_141_309_440,
        },
        "peak_mlx_allocator_memory_bytes": {
            "count": 3,
            "minimum": 2_324_039_502,
            "median": 2_324_039_502,
            "maximum": 2_324_039_502,
        },
        "peak_total_unified_memory_bytes": {
            "count": 3,
            "minimum": 4_089_218_536,
            "median": 4_090_595_032,
            "maximum": 4_093_199_920,
        },
    }
    repetitions = []
    for index in range(1, 4):
        repetitions.append(
            {
                "index": index,
                "report_sha256": str(index) * 64,
                "document_sha256": str(index + 3) * 64,
                "nonce_sha256": str(index + 6) * 64,
                "wall_started_unix_ns": index * 1_000_000_000,
                "wall_finished_unix_ns": index * 1_000_000_000 + 500_000_000,
                "within_frozen_thresholds": True,
            }
        )
    document = {
        "schema": RESOURCE_RESULT_SCHEMA,
        "status": RESOURCE_RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "benchmark_plan_sha256": "a" * 64,
            "benchmark_plan_document_sha256": "b" * 64,
            "plan_report_sha256": "c" * 64,
            "checkpoint_sha256": "d" * 64,
            "runtime_executable_sha256": "e" * 64,
        },
        "candidate": {
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "device": "gpu",
        },
        "machine_class": {
            "class_id": "apple-silicon-36gib",
            "architecture": "arm64",
            "hardware_family": "Apple silicon",
            "unified_memory_gib": 36,
        },
        "protocol": {
            "name": "fresh-process-resource-measurement-v1",
            "planned_repetitions": 3,
            "verified_repetitions": 3,
            "serial_non_overlapping": True,
            "distinct_process_scoped_nonces": True,
            "operating_system_cache_controlled": False,
        },
        "repetitions": repetitions,
        "aggregate": {
            **summaries,
            "maximum_peak_total_unified_memory_gib": 3.812089,
            "thermal_state_before": [{"value": 0, "name": "nominal"} for _ in range(3)],
            "thermal_state_after": [{"value": 0, "name": "nominal"} for _ in range(3)],
            "timeouts_observed": 0,
            "oom_events_observed": 0,
        },
        "coverage": {
            "controlled_repetitions_observed": 3,
            "all_required_measurements_observed": True,
            "same_plan_checkpoint_runtime_device_and_machine_observed": True,
            "serial_non_overlapping_execution_observed": True,
            "required_16_gib_acceptance_class_observed": False,
            "development_machine_thresholds_met": True,
        },
        "readiness": {
            "controlled_repeated_benchmark_complete": True,
            "development_machine_thresholds_met": True,
            "resource_envelope_accepted": False,
            "publication_ready": False,
        },
        "permissions": {"accepted": False, "publication_permitted": False},
        "effects": {"model_run_started": False, "audio_created": False},
    }
    return _write_hashed(root / "resource-result.json", document)


def _permissions() -> dict[str, bool]:
    return {
        "accepted": False,
        "automatic_promotion": False,
        "automatic_selection": False,
        "production_eligible": False,
        "public_result": False,
        "simple_mode_available": False,
        "source_graph_activation": False,
        "studio_import_available": False,
    }


def _agreement_effects() -> dict[str, bool]:
    return {
        "audio_created_or_mutated": False,
        "candidate_activated": False,
        "default_changed": False,
        "midi_created_or_mutated": False,
        "source_graph_mutated": False,
    }


def _write_hashed(path: Path, document: dict[str, object]) -> Path:
    document.pop("document_sha256", None)
    document["document_sha256"] = _document_sha256(document)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
