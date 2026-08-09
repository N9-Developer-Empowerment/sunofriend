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
