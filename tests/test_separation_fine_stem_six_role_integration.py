from __future__ import annotations

import http.client
import json
from pathlib import Path
import threading

import numpy as np

from sunofriend.separation_fine_stem_canary_audio import file_sha256
from sunofriend.separation_fine_stem_integration_audio import (
    persist_six_roles,
    quantize_six_roles,
)
from sunofriend.separation_fine_stem_integration_completion_plan import (
    load_completed_worker_receipt,
)
from sunofriend.separation_fine_stem_integration_report import (
    ARTIFACT_ROLES,
    REPORT_SCHEMA,
    REPORT_STATUS,
    integration_report_sha256,
    validate_fine_stem_integration_report,
)
from sunofriend.separation_fine_stem_integration_outcome import (
    build_fine_stem_integration_outcome,
    validate_fine_stem_integration_outcome,
)
from sunofriend.separation_fine_stem_midi_plan import (
    MIDI_PLAN_STATUS,
    TRACK_METADATA,
    build_fine_stem_midi_plan,
    validate_fine_stem_midi_plan,
)
from sunofriend.separation_fine_stem_midi_canary import (
    execute_fine_stem_midi_canary,
    validate_fine_stem_midi_canary,
)
from sunofriend.separation_fine_stem_midi_review import (
    build_midi_review_seed,
    build_midi_review_server,
    render_midi_canary_review,
    validate_midi_review,
)
from sunofriend.separation_fine_stem_midi_outcome import (
    build_fine_stem_midi_outcome,
    midi_outcome_document_sha256,
    validate_fine_stem_midi_outcome,
)
from sunofriend.separation_fine_stem_synth_bottleneck_plan import (
    SYNTH_BOTTLENECK_PLAN_STATUS,
    build_fine_stem_synth_bottleneck_plan,
    validate_fine_stem_synth_bottleneck_plan,
)
from sunofriend.separation_fine_stem_integration_review import (
    build_integration_review_seed,
    build_integration_review_server,
    render_integration_review,
    validate_integration_review,
)
from sunofriend.separation_fine_stem_canary_guard import (
    FineStemCanaryExecutionGuard,
)


def _report() -> dict:
    cases = []
    for index in range(8):
        artifacts = {
            role: {
                "relative_path": f"CASES/case-{index}/{role}.wav",
                "bytes": 10,
                "sha256": "0" * 64,
                "sample_rate_hz": 44_100,
                "channels": 2,
                "frames": 661_500,
                "subtype": "PCM_24",
            }
            for role in ARTIFACT_ROLES
        }
        cases.append(
            {
                "case_id": f"case-{index}",
                "track_id": f"track-{index}",
                "title": f"Track {index}",
                "window_seconds": [0, 15],
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
        "profiles": {},
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


def test_six_role_persistence_reconstructs_pcm24_exactly(tmp_path: Path) -> None:
    frames = 4096
    clock = np.arange(frames, dtype=np.float64) / 44_100
    source = np.column_stack((0.3 * np.sin(2 * np.pi * 220 * clock),) * 2)
    roles = {
        role: source * fraction
        for role, fraction in {
            "vocals": 0.2,
            "drums": 0.15,
            "bass": 0.1,
            "synth": 0.2,
            "guitar": 0.15,
        }.items()
    }
    quantized = quantize_six_roles(reference=source, **roles)
    persisted = persist_six_roles(tmp_path, case_id="one", quantized=quantized)
    assert set(persisted["artifacts"]) == set(ARTIFACT_ROLES)
    assert persisted["maximum_reconstruction_error_lsb"] == 0


def test_six_role_report_and_checkbox_free_review_are_bound() -> None:
    report = validate_fine_stem_integration_report(_report())
    page = render_integration_review(report)
    assert "Playback recorded automatically" in page
    assert "timeupdate" in page
    assert "currentTime > 0" in page
    assert "const local = loadLocal();" in page
    assert page.index("const local = loadLocal();") < page.index(
        "fetch('/saved-result'"
    )
    assert "${JSON.stringify(out, null, 2)}\\n" in page
    assert ".join('\\n')" in page
    assert 'id="download"' in page
    assert "await save();" in page
    assert "fetch('/download-review'" in page
    assert "listened checkbox" in page
    assert 'type="checkbox"' not in page
    seed = build_integration_review_seed(report)
    for case in seed["cases"]:
        case["played_items"] = list(ARTIFACT_ROLES)
        case["listened"] = True
        case["catastrophic_result"] = "no_catastrophic_defect"
    seed["status"] = "human_listening_complete_no_selection"
    validated = validate_integration_review(seed, report)
    assert validated["status"] == "human_listening_complete_no_selection"
    assert validated["boundaries"]["review_activates_profile"] is False


def test_completed_six_role_review_reduces_only_present_role_cohorts() -> None:
    report = validate_fine_stem_integration_report(_report())
    review = build_integration_review_seed(report)
    for index, case in enumerate(review["cases"]):
        role = report["cases"][index]["reused_primary_role"]
        complement = report["cases"][index]["new_complementary_role"]
        case["played_items"] = list(ARTIFACT_ROLES)
        case["listened"] = True
        case["catastrophic_result"] = "no_catastrophic_defect"
        case["usefulness"][role] = "partly_useful" if index in {0, 1} else "useful"
        case["usefulness"][complement] = "not_useful"
        case["issues"][role] = {
            "bleed": "none",
            "missing_content": "some" if index in {0, 1} else "none",
            "artefacts": "none",
            "timing_or_join_problems": "none",
        }
    review["status"] = "human_listening_complete_no_selection"

    outcome = validate_fine_stem_integration_outcome(
        build_fine_stem_integration_outcome(report=report, review=review)
    )

    assert outcome["status"] == "private_six_role_integration_qualified"
    assert outcome["qualified_for_private_six_role_integration"] is True
    assert all(
        target["success_fraction_all_present"] == 1.0 for target in outcome["targets"]
    )
    assert outcome["targets"][0]["usefulness_counts"] == {
        "partly_useful": 2,
        "useful": 2,
    }
    assert not any(outcome["effects"].values())
    assert outcome["boundaries"]["public_activation"] is False


def _qualified_outcome(report: dict) -> dict:
    review = build_integration_review_seed(report)
    for index, case in enumerate(review["cases"]):
        role = report["cases"][index]["reused_primary_role"]
        case["played_items"] = list(ARTIFACT_ROLES)
        case["listened"] = True
        case["catastrophic_result"] = "no_catastrophic_defect"
        case["usefulness"][role] = "useful"
    review["status"] = "human_listening_complete_no_selection"
    return build_fine_stem_integration_outcome(report=report, review=review)


def test_downstream_midi_plan_binds_cases_without_opening_audio() -> None:
    report = _report()
    track_ids = list(TRACK_METADATA)
    for index, case in enumerate(report["cases"]):
        case["track_id"] = track_ids[index % len(track_ids)]
    report["report_sha256"] = integration_report_sha256(report)
    plan = validate_fine_stem_midi_plan(
        build_fine_stem_midi_plan(
            report=report,
            outcome=_qualified_outcome(report),
        )
    )

    assert plan["status"] == MIDI_PLAN_STATUS
    assert len(plan["cases"]) == 8
    assert not any(plan["effects"].values())
    assert plan["boundaries"]["plan_only"] is True
    assert plan["boundaries"]["midi_created"] is False
    assert (
        plan["review_schema"]["minimum_usefulness_rating_for_profile_retention"] is None
    )
    assert plan["review_schema"]["negative_feedback_disables_six_role_profile"] is False
    synth = plan["cases"][0]
    guitar = plan["cases"][4]
    assert synth["transcription"]["processing_kind"] == "synth"
    assert guitar["transcription"]["processing_kind"] == "keys"
    assert guitar["transcription"]["public_role"] == "guitar"
    assert all(case["metadata"]["guessed"] is False for case in plan["cases"])
    assert all(
        [item["role"] for item in case["grouped_other_control_inputs"]]
        == ["synth", "guitar", "other"]
        for case in plan["cases"]
    )


def test_downstream_midi_plan_rejects_wrong_outcome_binding() -> None:
    report = _report()
    track_ids = list(TRACK_METADATA)
    for index, case in enumerate(report["cases"]):
        case["track_id"] = track_ids[index % len(track_ids)]
    report["report_sha256"] = integration_report_sha256(report)
    outcome = _qualified_outcome(report)
    outcome["report_sha256"] = "f" * 64
    from sunofriend.separation_fine_stem_integration_outcome import (
        integration_outcome_document_sha256,
    )

    outcome["document_sha256"] = integration_outcome_document_sha256(outcome)
    try:
        build_fine_stem_midi_plan(report=report, outcome=outcome)
    except ValueError as error:
        assert "outcome/report binding" in str(error)
    else:
        raise AssertionError("wrong integration outcome binding was accepted")


def _execute_test_midi_canary(
    tmp_path: Path,
) -> tuple[Path, dict, list[tuple[str, str]]]:
    import soundfile as sf

    root = tmp_path / "integration"
    inputs = root / "INPUTS"
    technical = root / "TECHNICAL"
    inputs.mkdir(parents=True)
    technical.mkdir()
    clock = np.arange(661_500, dtype=np.float64) / 44_100
    artifacts = {}
    for role, amplitude, frequency in (
        ("synth", 0.025, 220.0),
        ("guitar", 0.020, 330.0),
        ("other", 0.015, 440.0),
    ):
        path = inputs / f"{role}.wav"
        mono = amplitude * np.sin(2 * np.pi * frequency * clock)
        sf.write(path, np.column_stack((mono, mono)), 44_100, subtype="PCM_24")
        artifacts[role] = {
            "relative_path": f"INPUTS/{role}.wav",
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            "sample_rate_hz": 44_100,
            "channels": 2,
            "frames": 661_500,
            "subtype": "PCM_24",
        }
    reference_path = inputs / "reference.wav"
    reference_audio = sum(
        sf.read(inputs / f"{role}.wav", dtype="float64", always_2d=True)[0]
        for role in ("synth", "guitar", "other")
    )
    sf.write(reference_path, reference_audio, 44_100, subtype="PCM_24")
    reference_artifact = {
        "relative_path": "INPUTS/reference.wav",
        "bytes": reference_path.stat().st_size,
        "sha256": file_sha256(reference_path),
        "sample_rate_hz": 44_100,
        "channels": 2,
        "frames": 661_500,
        "subtype": "PCM_24",
    }

    report = _report()
    track_ids = list(TRACK_METADATA)
    for index, case in enumerate(report["cases"]):
        case["track_id"] = track_ids[index % len(track_ids)]
        for role in ("synth", "guitar", "other"):
            case["artifacts"][role] = dict(artifacts[role])
        case["artifacts"]["reference"] = dict(reference_artifact)
    report["report_sha256"] = integration_report_sha256(report)
    (technical / "INTEGRATION-REPORT.json").write_text(json.dumps(report))
    plan = validate_fine_stem_midi_plan(
        build_fine_stem_midi_plan(
            report=report,
            outcome=_qualified_outcome(report),
        )
    )
    plan_path = tmp_path / "MIDI-PLAN.json"
    plan_path.write_text(json.dumps(plan))
    calls: list[tuple[str, str]] = []

    def transcribe(path: str, *, kind: str, **parameters: float) -> list:
        assert parameters == {
            "onset_threshold": 0.5,
            "frame_threshold": 0.3,
            "min_note_ms": 60.0,
        }
        calls.append((Path(path).name, kind))
        from sunofriend.models import NoteEvent

        return [NoteEvent(0.25, 0.75, 60 + len(calls) % 5, 90)]

    def render(_midi: Path, wav: Path) -> None:
        tone = 0.02 * np.sin(2 * np.pi * 440 * np.arange(44_100) / 44_100)
        sf.write(wav, np.column_stack((tone, tone)), 44_100, subtype="PCM_16")

    destination = tmp_path / "midi-canary"
    result = execute_fine_stem_midi_canary(
        plan_path,
        root,
        out_dir=destination,
        expected_plan_sha256=plan["document_sha256"],
        transcribe=transcribe,
        render=render,
        network_observation=lambda: {
            "os_network_denial_enforced": True,
            "python_network_attempts": 0,
        },
    )
    return destination, result, calls


def test_downstream_midi_canary_runs_exact_budget_and_reconstructs_control(
    tmp_path: Path,
) -> None:
    import soundfile as sf

    destination, result, calls = _execute_test_midi_canary(tmp_path)
    validated = validate_fine_stem_midi_canary(result)
    assert len(calls) == 16
    assert [row["attempt_number"] for row in validated["attempts"]] == list(
        range(1, 17)
    )
    assert validated["effects"]["private_audio_input_identities"] == 24
    assert validated["effects"]["separator_inference_attempts"] == 0
    assert validated["effects"]["source_selected"] is False
    for case in validated["cases"]:
        control = (
            destination / case["grouped_other_control"]["artifact"]["relative_path"]
        )
        persisted = sf.read(control, dtype="float64", always_2d=True)[0]
        source_sum = sum(
            sf.read(
                destination.parent / "integration" / "INPUTS" / f"{role}.wav",
                dtype="float64",
                always_2d=True,
            )[0]
            for role in ("synth", "guitar", "other")
        )
        assert np.array_equal(
            np.rint(persisted * 2**23).astype(np.int64),
            np.rint(source_sum * 2**23).astype(np.int64),
        )
        assert case["grouped_other_control"]["maximum_reconstruction_error_lsb"] == 0
        assert set(case["blind_order"]) == {"candidate", "control"}


def test_downstream_midi_review_is_checkbox_free_bound_and_saved(
    tmp_path: Path,
) -> None:
    destination, report, _calls = _execute_test_midi_canary(tmp_path)
    page = render_midi_canary_review(report)
    assert "Source reference" in page
    assert "Original 15-second mix window" in page
    assert "audio[data-player-id]" in page
    assert "Playback recorded automatically" in page
    assert "currentTime > 0" in page
    assert 'type="checkbox"' not in page
    assert "await save();" in page
    assert "fetch('/download-review'" in page
    seed = build_midi_review_seed(report)
    for case in seed["cases"]:
        case["played_items"] = ["A", "B"]
        case["listened"] = True
        case["recognisable_notes"] = "partly_useful"
        case["timing_usefulness"] = "useful"
        case["edit_workload"] = "moderate"
        case["candidate_vs_control"] = "candidate_better"
    seed["status"] = "human_listening_complete_no_selection"
    validated = validate_midi_review(seed, report)
    assert validated["status"] == "human_listening_complete_no_selection"
    assert validated["boundaries"]["review_selects_source"] is False

    server = build_midi_review_server(
        destination,
        integration_root=destination.parent / "integration",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        route = (
            "/" + report["cases"][0]["outputs"]["candidate"]["preview"]["relative_path"]
        )
        connection.request("GET", route, headers={"Range": "bytes=1-4"})
        response = connection.getresponse()
        assert response.status == 206
        assert len(response.read()) == 4
        reference_route = f"/reference/{report['cases'][0]['case_id']}.wav"
        connection.request("GET", reference_route, headers={"Range": "bytes=2-5"})
        reference_response = connection.getresponse()
        assert reference_response.status == 206
        assert len(reference_response.read()) == 4
        connection.request(
            "POST",
            "/save-review",
            body=json.dumps(seed),
            headers={"Content-Type": "application/json"},
        )
        saved = connection.getresponse()
        assert saved.status == 200
        assert (
            json.loads(saved.read())["document_sha256"] == validated["document_sha256"]
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _completed_midi_review(report: dict) -> dict:
    review = build_midi_review_seed(report)
    for index, case in enumerate(review["cases"]):
        role = report["cases"][index]["confirmed_present_target_role"]
        case["played_items"] = ["A", "B"]
        case["listened"] = True
        case["recognisable_notes"] = (
            "partly_useful" if role == "synth" else "not_useful"
        )
        case["timing_usefulness"] = "partly_useful"
        case["edit_workload"] = "moderate"
        case["candidate_vs_control"] = "same" if role == "synth" else "candidate_better"
    review["status"] = "human_listening_complete_no_selection"
    return review


def test_downstream_midi_outcome_records_source_omission_without_authority(
    tmp_path: Path,
) -> None:
    _destination, report, _calls = _execute_test_midi_canary(tmp_path)
    outcome = validate_fine_stem_midi_outcome(
        build_fine_stem_midi_outcome(
            report=report,
            review=_completed_midi_review(report),
            source_reference_present_during_completed_review=False,
            repaired_page_source_reference_present=True,
        )
    )

    assert outcome["status"] == (
        "private_midi_evidence_recorded_source_reference_limited"
    )
    assert outcome["decisions"]["synth"]["status"] == (
        "bottleneck_attribution_required"
    )
    assert outcome["targets"][0]["candidate_better_case_count"] == 0
    assert outcome["targets"][1]["candidate_better_case_count"] == 4
    assert not any(outcome["effects"].values())
    assert outcome["boundaries"]["source_selected"] is False

    outcome["boundaries"]["source_selected"] = True
    outcome["document_sha256"] = midi_outcome_document_sha256(outcome)
    try:
        validate_fine_stem_midi_outcome(outcome)
    except ValueError as error:
        assert "grants permission" in str(error)
    else:
        raise AssertionError("permission-granting MIDI outcome was accepted")


def test_synth_bottleneck_request_binds_source_present_three_arm_cohort(
    tmp_path: Path,
) -> None:
    destination, report, _calls = _execute_test_midi_canary(tmp_path)
    review = _completed_midi_review(report)
    outcome = build_fine_stem_midi_outcome(
        report=report,
        review=review,
        source_reference_present_during_completed_review=False,
        repaired_page_source_reference_present=True,
    )
    integration_report = json.loads(
        (
            destination.parent / "integration/TECHNICAL/INTEGRATION-REPORT.json"
        ).read_text()
    )
    provider_corpus = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "status": "local_audio_not_committed",
        "checked_on": "2026-07-31",
        "tracks": [
            {
                "id": track_id,
                "directory": track_id,
                "suno": {"packs": 1},
                "moises": {"files": 17},
            }
            for track_id in list(TRACK_METADATA)[:3]
        ],
    }
    plan = validate_fine_stem_synth_bottleneck_plan(
        build_fine_stem_synth_bottleneck_plan(
            midi_report=report,
            midi_outcome=outcome,
            integration_report=integration_report,
            provider_corpus=provider_corpus,
        )
    )

    assert plan["status"] == SYNTH_BOTTLENECK_PLAN_STATUS
    assert len(plan["cases"]) == 4
    assert plan["provider_corpus"]["catalogued_track_count"] == 3
    assert (
        plan["required_inputs_before_execution_plan"]["missing_exact_artifact_count"]
        == 4
    )
    assert plan["future_execution_contract"]["midi_transcription_attempt_budget"] == 12
    assert all(
        case["target_presence"]["status"]
        == "human_reviewed_present_before_separator_canary"
        for case in plan["cases"]
    )
    assert plan["boundaries"]["ready_for_execution"] is False
    assert not any(plan["effects"].values())


def test_downstream_midi_runner_requires_sandbox_and_one_worker_call() -> None:
    source = (
        Path(__file__).parents[1] / "scripts/run-fine-stem-downstream-midi-canary.py"
    ).read_text()
    assert source.count("subprocess.run(") == 1
    assert '"(version 1)(deny network*)(allow default)"' in source
    assert '"--network-denial-enforced"' in source
    assert (
        "the single downstream-MIDI canary attempt failed; no retry was run" in source
    )


def test_six_role_review_server_ranges_and_saves(tmp_path: Path) -> None:
    report = _report()
    payload = b"RIFF-six-role-test"
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = tmp_path / artifact["relative_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            artifact["bytes"] = len(payload)
            artifact["sha256"] = file_sha256(path)
    report["report_sha256"] = integration_report_sha256(report)
    technical = tmp_path / "TECHNICAL"
    review = tmp_path / "REVIEW"
    technical.mkdir()
    review.mkdir()
    (technical / "INTEGRATION-REPORT.json").write_text(json.dumps(report))
    server = build_integration_review_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        route = "/" + report["cases"][0]["artifacts"]["synth"]["relative_path"]
        connection.request("GET", route, headers={"Range": "bytes=1-4"})
        response = connection.getresponse()
        assert response.status == 206
        assert response.read() == payload[1:5]
        seed = build_integration_review_seed(report)
        connection.request(
            "POST",
            "/save-review",
            body=json.dumps(seed),
            headers={"Content-Type": "application/json"},
        )
        saved = connection.getresponse()
        assert saved.status == 200
        assert json.loads(saved.read())["report_sha256"] == report["report_sha256"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_runner_binds_exact_approved_plan_and_three_worker_modes() -> None:
    source = (
        Path(__file__).parents[1] / "scripts/run-fine-stem-six-role-integration.py"
    ).read_text()
    assert "9507d1ef182a0060270033a770a823b758ba024e75cc42e768117e66893f1dec" in source
    assert source.count("_run_worker(") == 4  # definition plus three sequential calls
    assert 'mode="scnet"' in source
    assert 'mode="mega53-synth"' in source
    assert 'mode="sw-guitar"' in source
    assert "automatic_retry" in source
    assert "str(python.resolve" not in source
    assert "Preserve the virtual-environment entry path" in source
    assert 'verified_source_package = Path(request["source_root"])' in source
    assert 'environment["PYTHONPATH"] = os.pathsep.join' in source


def test_partial_receipt_remaps_atomically_renamed_staging_path(
    tmp_path: Path,
) -> None:
    partial = tmp_path / "canary-FAILED"
    output = partial / "TEMP/scnet/case/vocals.npy"
    output.parent.mkdir(parents=True)
    with output.open("wb") as handle:
        np.save(handle, np.zeros((4, 2), dtype=np.float32), allow_pickle=False)
    stale = tmp_path / ".canary-staging/TEMP/scnet/case/vocals.npy"
    receipt = {
        "cases": [
            {
                "case_id": "case",
                "outputs": {
                    "vocals": {
                        "path": str(stale),
                        "bytes": output.stat().st_size,
                        "sha256": file_sha256(output),
                    }
                },
            }
        ]
    }
    receipt_path = partial / "TEMP/scnet-result.json"
    receipt_path.write_text(json.dumps(receipt))
    loaded = load_completed_worker_receipt(partial, "TEMP/scnet-result.json")
    assert loaded["cases"][0]["outputs"]["vocals"]["path"] == str(output.resolve())


def test_guard_distinguishes_local_socket_construction_from_network(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "model.ckpt"
    source = tmp_path / "source.wav"
    guard = FineStemCanaryExecutionGuard(
        checkpoint,
        audio_inputs=[source],
        audio_outputs=[],
        expected_forward_calls=1,
    )
    guard._audit("socket.__new__", ())
    assert guard.report()["local_socket_constructions"] == 1
    assert guard.report()["network_attempts"] == 0
    try:
        guard._audit("socket.connect", ())
    except RuntimeError as error:
        assert "network operation forbidden" in str(error)
    else:
        raise AssertionError("socket connection was not denied")
    assert guard.report()["network_attempts"] == 1
