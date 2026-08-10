from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import sunofriend.separation_fine_stem_studio_package as package_module
from sunofriend.separation_fine_stem_canary_audio import file_sha256
from sunofriend.separation_fine_stem_integration_outcome import (
    build_fine_stem_integration_outcome,
)
from sunofriend.separation_fine_stem_integration_report import (
    ARTIFACT_ROLES,
    REPORT_SCHEMA,
    REPORT_STATUS,
    integration_report_sha256,
)
from sunofriend.separation_fine_stem_integration_review import (
    build_integration_review_seed,
    validate_integration_review,
)
from sunofriend.separation_fine_stem_midi_canary import (
    CANARY_SCHEMA,
    CANARY_STATUS,
    canary_document_sha256,
)
from sunofriend.separation_fine_stem_midi_outcome import (
    build_fine_stem_midi_outcome,
)
from sunofriend.separation_fine_stem_midi_review import (
    build_midi_review_seed,
    validate_midi_review,
)
from sunofriend.separation_fine_stem_studio_package import (
    MIDI_CONTROL_CATALOG_NAME,
    PACKAGE_DIRECTORY_NAME,
    PACKAGE_MANIFEST_NAME,
    SIX_ROLE_CATALOG_NAME,
    build_private_studio_package,
    verify_private_studio_package,
)
from sunofriend.separation_fine_stem_synth_provider_midi_outcome import (
    OUTCOME_SCHEMA,
    OUTCOME_STATUS,
    outcome_document_sha256,
)
from sunofriend.separation_fine_stem_synth_provider_midi_plan import ARM_IDS


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


def _write_audio(path: Path, *, value: float = 0.0) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.full((128, 2), value, dtype=np.float32)
    sf.write(path, samples, 44_100, subtype="PCM_24")
    info = sf.info(path)
    return {
        "relative_path": "",
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "subtype": info.subtype,
    }


def _integration_report(root: Path) -> dict:
    cases = []
    for index in range(8):
        case_id = f"case-{index:02d}"
        artifacts = {}
        for role_index, role in enumerate(ARTIFACT_ROLES):
            path = root / "CASES" / case_id / f"{role}.wav"
            record = _write_audio(path, value=(role_index + 1) / 1000)
            record["relative_path"] = path.relative_to(root).as_posix()
            artifacts[role] = record
        cases.append(
            {
                "case_id": case_id,
                "track_id": f"track-{index:02d}",
                "title": f"Track {index}",
                "window_seconds": [index * 15, index * 15 + 15],
                "reused_primary_role": "synth" if index < 4 else "guitar",
                "new_complementary_role": "guitar" if index < 4 else "synth",
                "source_input": {},
                "reused_primary_input": {},
                "scnet_native_other_correction": {
                    "rms": 0.0,
                    "peak": 0.0,
                    "used_for_separation_accuracy_claim": False,
                },
                "projection": {
                    "method": "fixed grouped-other-constrained three-way Wiener mask",
                    "maximum_float_reconstruction_error": 0.0,
                    "raw_to_projected_correction": {},
                },
                "artifacts": artifacts,
                "shared_attenuation": 1.0,
                "maximum_reconstruction_error_lsb": 0,
            }
        )
    report = {
        "schema": REPORT_SCHEMA,
        "report_sha256": "",
        "status": REPORT_STATUS,
        "plan_sha256": "a" * 64,
        "approved_plan_sha256": "a" * 64,
        "release_tier": "private_studio_challenger",
        "profiles": {
            "core_four": "core",
            "synth": "synth",
            "guitar": "guitar",
        },
        "runtime": {},
        "workers": {},
        "resources": {},
        "cases": cases,
        "accounting": {},
        "effects": {
            "model_loads": 3,
            "inference_attempts": 16,
            "source_artifacts": 8,
            "reused_primary_artifacts": 8,
            "model_audio_reads": 16,
            "coordinator_audio_reads": 16,
            "audio_read_operations": 32,
            "audio_writes": 64,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
    }
    report["report_sha256"] = integration_report_sha256(report)
    return report


def _provider_outcome(synth_case_ids: list[str]) -> dict:
    ratings = {
        arm: {
            "recognisable_notes": "useful",
            "timing_usefulness": "useful",
            "edit_workload": "low",
        }
        for arm in ARM_IDS
    }
    document = {
        "schema": OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": OUTCOME_STATUS,
        "canary_document_sha256": "c" * 64,
        "plan_document_sha256": "d" * 64,
        "review_document_sha256": "e" * 64,
        "methodology": {
            "source_reference_present_during_completed_review": True,
            "blind_display_order": True,
            "same_transcriber_parameters_for_all_arms": True,
            "result_can_promote_or_select_a_source": False,
        },
        "cases": [
            {
                "case_id": case_id,
                "ratings_by_arm": ratings,
                "best_arm": "grouped_other_control",
                "current_vs_provider_recognisable": "tie",
                "notes_recorded": False,
            }
            for case_id in synth_case_ids
        ],
        "arm_aggregates": [
            {
                "arm_id": arm,
                "best_case_count": 4 if arm == "grouped_other_control" else 0,
                "recognisable_notes_counts": {"useful": 4},
                "timing_usefulness_counts": {"useful": 4},
                "edit_workload_counts": {"low": 4},
            }
            for arm in ARM_IDS
        ],
        "summary": {
            "reviewed_case_count": 4,
            "grouped_other_best_case_count": 4,
            "isolated_arm_best_case_count": 0,
            "current_vs_provider_recognisable_counts": {"tie": 4},
            "result": "no_isolated_synth_midi_advantage_over_grouped_other_observed",
        },
        "decisions": {
            "audio_stem_evidence": {"status": "retain_private_six_role_audio_evidence"},
            "midi": {"status": "retain_grouped_other_control_no_automatic_choice"},
            "next_step": {
                "status": "separate_audio_stem_admission_from_midi_method_choice"
            },
        },
        "boundaries": {
            "outcome_only": True,
            "audio_opened": False,
            "separator_model_loaded": False,
            "transcriber_run": False,
            "midi_created": False,
            "source_selected": False,
            "public_activation": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
        "effects": {
            "audio_reads": 0,
            "audio_writes": 0,
            "checkpoint_loads": 0,
            "midi_transcription_attempts": 0,
            "midi_writes": 0,
            "model_constructions": 0,
            "network_attempts": 0,
            "public_activations": 0,
            "separator_inference_attempts": 0,
            "source_selections": 0,
        },
    }
    document["document_sha256"] = outcome_document_sha256(document)
    return document


def _fixture(tmp_path: Path) -> dict[str, Path]:
    integration_root = tmp_path / "integration"
    report = _integration_report(integration_root)
    report_path = _write_json(
        integration_root / "TECHNICAL" / "INTEGRATION-REPORT.json", report
    )
    review = build_integration_review_seed(report)
    for index, case in enumerate(review["cases"]):
        target = report["cases"][index]["reused_primary_role"]
        case["played_items"] = list(ARTIFACT_ROLES)
        case["listened"] = True
        case["catastrophic_result"] = "no_catastrophic_defect"
        case["usefulness"][target] = "useful"
        case["issues"][target] = {
            "bleed": "none",
            "missing_content": "none",
            "artefacts": "none",
            "timing_or_join_problems": "none",
        }
    review["status"] = "human_listening_complete_no_selection"
    review = validate_integration_review(review, report)
    _write_json(integration_root / "REVIEW" / "SIX-ROLE-LISTENING.json", review)
    integration_outcome = build_fine_stem_integration_outcome(
        report=report, review=review
    )
    integration_outcome_path = _write_json(
        tmp_path / "integration-outcome.json", integration_outcome
    )

    midi_root = tmp_path / "midi-canary"
    midi_cases = []
    for case in report["cases"]:
        case_id = case["case_id"]
        path = midi_root / "CASES" / case_id / "grouped-other-control.wav"
        record = _write_audio(path, value=0.02)
        record["relative_path"] = path.relative_to(midi_root).as_posix()
        midi_cases.append(
            {
                "case_id": case_id,
                "confirmed_present_target_role": case["reused_primary_role"],
                "grouped_other_control": {
                    "artifact": record,
                    "construction": (
                        "sample-exact PCM24 sum of persisted synth, guitar and "
                        "residual-other estimates"
                    ),
                    "maximum_reconstruction_error_lsb": 0,
                },
            }
        )
    midi_report = {
        "schema": CANARY_SCHEMA,
        "document_sha256": "",
        "status": CANARY_STATUS,
        "plan": {"document_sha256": "b" * 64},
        "integration": {"report_sha256": report["report_sha256"]},
        "cases": midi_cases,
        "attempts": [{"attempt_number": number} for number in range(1, 17)],
        "network": {"python_network_attempts": 0},
        "effects": {"source_selected": False, "separator_inference_attempts": 0},
    }
    midi_report["document_sha256"] = canary_document_sha256(midi_report)
    _write_json(midi_root / "TECHNICAL" / "MIDI-CANARY-REPORT.json", midi_report)
    midi_review = build_midi_review_seed(midi_report)
    for index, case in enumerate(midi_review["cases"]):
        case["played_items"] = ["A", "B"]
        case["listened"] = True
        case["recognisable_notes"] = "partly_useful"
        case["timing_usefulness"] = "partly_useful"
        case["edit_workload"] = "moderate"
        case["candidate_vs_control"] = "same" if index < 4 else "candidate_better"
    midi_review["status"] = "human_listening_complete_no_selection"
    midi_review = validate_midi_review(midi_review, midi_report)
    midi_outcome = build_fine_stem_midi_outcome(
        report=midi_report,
        review=midi_review,
        source_reference_present_during_completed_review=False,
        repaired_page_source_reference_present=True,
    )
    midi_outcome_path = _write_json(tmp_path / "midi-outcome.json", midi_outcome)
    provider_path = _write_json(
        tmp_path / "provider-midi-outcome.json",
        _provider_outcome([case["case_id"] for case in report["cases"][:4]]),
    )
    assert report_path.is_file()
    return {
        "integration_root": integration_root,
        "integration_outcome": integration_outcome_path,
        "midi_root": midi_root,
        "midi_outcome": midi_outcome_path,
        "provider_outcome": provider_path,
    }


def _build(inputs: dict[str, Path], output: Path) -> dict:
    return build_private_studio_package(
        inputs["integration_root"],
        inputs["integration_outcome"],
        inputs["midi_root"],
        inputs["midi_outcome"],
        inputs["provider_outcome"],
        out_dir=output,
    )


def test_private_studio_package_keeps_audio_and_midi_control_separate(
    tmp_path: Path,
) -> None:
    inputs = _fixture(tmp_path)
    output = tmp_path / PACKAGE_DIRECTORY_NAME

    document = _build(inputs, output)
    verified = verify_private_studio_package(output)

    assert verified == document
    assert document["case_count"] == 8
    assert document["effects"]["private_audio_files_copied"] == 72
    assert document["effects"]["midi_files_written"] == 0
    assert document["boundaries"]["source_selection"] is False
    assert output.stat().st_mode & 0o077 == 0
    assert (output / PACKAGE_MANIFEST_NAME).stat().st_mode & 0o077 == 0
    assert not list(output.rglob("*.mid"))
    for case in document["cases"]:
        case_root = output / "CASES" / case["case_id"]
        assert (case_root / SIX_ROLE_CATALOG_NAME).is_file()
        assert (case_root / MIDI_CONTROL_CATALOG_NAME).is_file()
        assert set(case["six_role_stems"]) == {
            "vocals",
            "drums",
            "bass",
            "synth",
            "guitar",
            "other",
        }
        assert case["studio"]["initial_source_selection"] is None
        assert case["studio"]["initial_midi_selection"] is None


def test_private_studio_package_rejects_changed_source_audio(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    grouped = inputs["midi_root"] / "CASES" / "case-00" / "grouped-other-control.wav"
    grouped.write_bytes(grouped.read_bytes() + b"changed")
    output = tmp_path / PACKAGE_DIRECTORY_NAME

    with pytest.raises(ValueError, match="byte count differs"):
        _build(inputs, output)

    assert not output.exists()


def test_private_studio_package_rejects_changed_midi_policy(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    provider = json.loads(inputs["provider_outcome"].read_text())
    provider["decisions"]["midi"]["status"] = "select_provider"
    provider["document_sha256"] = outcome_document_sha256(provider)
    _write_json(inputs["provider_outcome"], provider)
    output = tmp_path / PACKAGE_DIRECTORY_NAME

    with pytest.raises(ValueError, match="provider MIDI decision differs"):
        _build(inputs, output)

    assert not output.exists()


def test_private_studio_package_verifier_rejects_tampering(tmp_path: Path) -> None:
    inputs = _fixture(tmp_path)
    output = tmp_path / PACKAGE_DIRECTORY_NAME
    document = _build(inputs, output)
    stem = output / document["cases"][0]["six_role_stems"]["synth"]["relative_path"]
    stem.write_bytes(stem.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="byte count differs"):
        verify_private_studio_package(output)


def test_private_studio_package_removes_new_destination_if_final_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _fixture(tmp_path)
    output = tmp_path / PACKAGE_DIRECTORY_NAME

    def fail_final_check(_root: str | Path) -> dict:
        raise ValueError("forced final verification failure")

    monkeypatch.setattr(
        package_module,
        "verify_private_studio_package",
        fail_final_check,
    )
    with pytest.raises(ValueError, match="forced final verification failure"):
        _build(inputs, output)

    assert not output.exists()
