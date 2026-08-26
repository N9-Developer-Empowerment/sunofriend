from __future__ import annotations

import http.client
import json
from pathlib import Path
import shutil
import threading

import numpy as np

from sunofriend.models import NoteEvent
from sunofriend.separation_fine_stem_canary_audio import file_sha256
from sunofriend.separation_fine_stem_integration_report import (
    ARTIFACT_ROLES,
    REPORT_SCHEMA,
    REPORT_STATUS,
    integration_report_sha256,
)
from sunofriend.separation_fine_stem_synth_bottleneck_plan import (
    SYNTH_BOTTLENECK_PLAN_SCHEMA,
    SYNTH_BOTTLENECK_PLAN_STATUS,
    synth_bottleneck_plan_document_sha256,
)
from sunofriend.separation_fine_stem_synth_provider_qualification import (
    PROVIDER_INPUT_SCHEMA,
    QUALIFICATION_STATUS,
    qualification_document_sha256,
    qualify_fine_stem_synth_provider_estimates,
    validate_fine_stem_synth_provider_qualification,
)
from sunofriend.separation_fine_stem_synth_provider_midi_plan import (
    ARM_IDS,
    MIDI_PLAN_STATUS,
    build_fine_stem_synth_provider_midi_plan,
    validate_fine_stem_synth_provider_midi_plan,
)
from sunofriend.separation_fine_stem_synth_provider_midi_canary import (
    CANARY_STATUS,
    execute_fine_stem_synth_provider_midi_canary,
    validate_fine_stem_synth_provider_midi_canary,
)
from sunofriend.separation_fine_stem_synth_provider_midi_review import (
    build_provider_synth_midi_review_seed,
    build_provider_synth_midi_review_server,
    render_provider_synth_midi_review,
    validate_provider_synth_midi_review,
)
from sunofriend.separation_fine_stem_synth_provider_midi_outcome import (
    OUTCOME_STATUS,
    build_fine_stem_synth_provider_midi_outcome,
    validate_fine_stem_synth_provider_midi_outcome,
)
from sunofriend.separation_fine_stem_synth_provider_outcome import (
    INCOMPLETE_STATUS,
    READY_STATUS,
    build_fine_stem_synth_provider_outcome,
    validate_fine_stem_synth_provider_outcome,
)
from sunofriend.separation_fine_stem_synth_provider_review import (
    build_provider_review_seed,
    build_provider_review_server,
    render_provider_review,
    validate_provider_review,
)


SELECTION_POLICY = (
    "first unsuffixed Suno stem pack frozen before audio analysis; "
    "prefer its discrete Synth.wav estimate"
)


def _artifact(path: Path, root: Path) -> dict:
    import soundfile as sf

    info = sf.info(path)
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "subtype": info.subtype,
    }


def _fixture(tmp_path: Path) -> tuple[dict, dict, Path, dict]:
    import soundfile as sf
    from scipy.signal import resample_poly

    integration_root = tmp_path / "integration"
    case_ids = [f"synth-case-{index}" for index in range(4)]
    request_cases = []
    integration_cases = []
    input_cases = []
    for index, case_id in enumerate(case_ids):
        start = 5 + index
        duration = start + 20
        pack = tmp_path / f"pack-{index}"
        pack.mkdir()
        clock = np.arange(duration * 48_000, dtype=np.float64) / 48_000
        native_sum = np.zeros((len(clock), 2), dtype=np.float64)
        for name, frequency, amplitude in (
            ("0 Lead Vocals.wav", 180 + index, 0.04),
            ("2 Drums.wav", 320 + index, 0.03),
            ("3 Bass.wav", 95 + index, 0.025),
            ("6 Synth.wav", 440 + index, 0.05),
        ):
            mono = amplitude * np.sin(2 * np.pi * frequency * clock)
            value = np.column_stack((mono, mono * 0.97))
            sf.write(pack / name, value, 48_000, subtype="PCM_16")
            native_sum += sf.read(pack / name, dtype="float64", always_2d=True)[0]
        native_window = native_sum[start * 48_000 : (start + 15) * 48_000]
        reference = resample_poly(native_window, 147, 160, axis=0, padtype="constant")[
            :661_500
        ]
        reference_path = integration_root / "CASES" / case_id / "reference.wav"
        reference_path.parent.mkdir(parents=True)
        sf.write(reference_path, reference, 44_100, subtype="PCM_24")
        reference_artifact = _artifact(reference_path, integration_root)
        artifacts = {role: dict(reference_artifact) for role in ARTIFACT_ROLES}
        integration_cases.append(
            {
                "case_id": case_id,
                "track_id": f"track-{index}",
                "title": f"Track {index}",
                "window_seconds": [start, start + 15],
                "artifacts": artifacts,
                "maximum_reconstruction_error_lsb": 0,
                "projection": {
                    "method": "fixed grouped-other-constrained three-way Wiener mask"
                },
            }
        )
        request_cases.append(
            {
                "case_id": case_id,
                "track_id": f"track-{index}",
                "title": f"Track {index}",
                "window_seconds": [start, start + 15],
                "target_presence": {
                    "status": "human_reviewed_present_before_separator_canary"
                },
                "source_reference": {"role": "reference", **reference_artifact},
                "current_separator_estimate": {
                    "role": "synth",
                    **reference_artifact,
                },
                "grouped_other_control": {
                    "role": "grouped_other",
                    **reference_artifact,
                },
                "provider_estimate_request": {"exact_provider_artifact_bound": False},
                "frozen_transcription": {
                    "metadata": {
                        "bpm": 120.0,
                        "key": "C major",
                        "tuning_hz": 440.0,
                        "guessed": False,
                    },
                    "transcription": {
                        "processing_kind": "synth",
                        "public_role": "synth",
                        "general_midi_channel": 5,
                        "general_midi_program_zero_based": 81,
                    },
                    "parameters": {
                        "onset_threshold": 0.5,
                        "frame_threshold": 0.3,
                        "min_note_ms": 60.0,
                    },
                    "same_parameters_for_all_three_arms": True,
                },
            }
        )
        input_cases.append(
            {
                "case_id": case_id,
                "provider": "Suno",
                "provider_role_label": "Synth",
                "pack_directory": str(pack),
                "target_filename": "6 Synth.wav",
                "rights_category": "owned",
                "provider_use_boundary": "local private comparison only",
            }
        )
    for index in range(4, 8):
        integration_cases.append(
            {
                "case_id": f"dummy-case-{index}",
                "track_id": f"dummy-{index}",
                "title": f"Dummy {index}",
                "window_seconds": [0, 15],
                "artifacts": {
                    role: dict(integration_cases[0]["artifacts"]["reference"])
                    for role in ARTIFACT_ROLES
                },
                "maximum_reconstruction_error_lsb": 0,
                "projection": {
                    "method": "fixed grouped-other-constrained three-way Wiener mask"
                },
            }
        )
    integration = {
        "schema": REPORT_SCHEMA,
        "status": REPORT_STATUS,
        "report_sha256": "",
        "plan_sha256": "a" * 64,
        "approved_plan_sha256": "a" * 64,
        "cases": integration_cases,
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
    integration["report_sha256"] = integration_report_sha256(integration)
    request = {
        "schema": SYNTH_BOTTLENECK_PLAN_SCHEMA,
        "document_sha256": "",
        "status": SYNTH_BOTTLENECK_PLAN_STATUS,
        "integration_report_sha256": integration["report_sha256"],
        "cases": request_cases,
        "attribution_policy": {
            "provider_useful_current_not_useful": "separator_bottleneck_likely",
            "cannot_tell_or_not_tested": "inconclusive_no_automatic_retry",
        },
        "boundaries": {
            "request_only": True,
            "ready_for_execution": False,
            "private_audio_opened": False,
            "provider_audio_bound": False,
            "separator_model_loaded": False,
            "transcriber_run": False,
            "midi_created": False,
            "source_selected": False,
            "public_activation": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
            "training_started": False,
        },
        "effects": {
            "audio_reads": 0,
            "audio_writes": 0,
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "separator_inference_attempts": 0,
            "midi_transcription_attempts": 0,
            "midi_writes": 0,
            "network_attempts": 0,
            "source_selections": 0,
            "public_activations": 0,
            "training_attempts": 0,
        },
    }
    request["document_sha256"] = synth_bottleneck_plan_document_sha256(request)
    inputs = {
        "schema": PROVIDER_INPUT_SCHEMA,
        "request_document_sha256": request["document_sha256"],
        "selection_policy": SELECTION_POLICY,
        "selection_frozen_before_audio_analysis": True,
        "cases": input_cases,
    }
    return request, integration, integration_root, inputs


def test_provider_qualification_aligns_and_writes_review_only_artifacts(
    tmp_path: Path,
) -> None:
    request, integration, integration_root, inputs = _fixture(tmp_path)
    destination = tmp_path / "fine-stem-synth-provider-qualification-v1"
    report = validate_fine_stem_synth_provider_qualification(
        qualify_fine_stem_synth_provider_estimates(
            request=request,
            integration_report=integration,
            integration_root=integration_root,
            provider_inputs=inputs,
            out_dir=destination,
        )
    )

    assert report["status"] == QUALIFICATION_STATUS
    assert report["objective_summary"]["aligned_case_count"] == 4
    assert report["effects"]["private_audio_input_identities"] == 20
    assert report["effects"]["private_audio_writes"] == 8
    assert report["effects"]["separator_inference_attempts"] == 0
    assert report["effects"]["midi_transcription_attempts"] == 0
    assert all(case["alignment"]["passed"] for case in report["cases"])
    assert all(
        case["alignment"]["envelope_best_lag_milliseconds"] == 0
        for case in report["cases"]
    )
    assert all(
        (destination / case["artifacts"]["provider_synth"]["relative_path"]).is_file()
        for case in report["cases"]
    )
    changed = json.loads(json.dumps(report))
    changed["boundaries"]["source_selected"] = True
    changed["document_sha256"] = qualification_document_sha256(changed)
    try:
        validate_fine_stem_synth_provider_qualification(changed)
    except ValueError as error:
        assert "grants permission" in str(error)
    else:
        raise AssertionError("permission-granting provider qualification was accepted")


def test_provider_review_is_source_visible_checkbox_free_and_saved(
    tmp_path: Path,
) -> None:
    request, integration, integration_root, inputs = _fixture(tmp_path)
    destination = tmp_path / "fine-stem-synth-provider-qualification-v1"
    report = qualify_fine_stem_synth_provider_estimates(
        request=request,
        integration_report=integration,
        integration_root=integration_root,
        provider_inputs=inputs,
        out_dir=destination,
    )
    page = render_provider_review(report)
    assert "Source reference" in page
    assert "Suno provider estimate: Synth" in page
    assert "Playback recorded automatically" in page
    assert "currentTime > 0" in page
    assert "addEventListener('pause'" in page
    assert 'type="checkbox"' not in page
    assert "fetch('/download-review'" in page

    review = build_provider_review_seed(report)
    for case in review["cases"]:
        case["played_items"] = ["source", "provider_synth"]
        case["listened"] = True
        case["provider_target_presence"] = "present"
        case["provider_role_breadth"] = "synth_or_keyboard_family"
    review["status"] = "human_provider_presence_review_complete_no_selection"
    validated = validate_provider_review(review, report)
    assert validated["status"] == review["status"]
    assert validated["boundaries"]["review_starts_midi"] is False

    server = build_provider_review_server(destination, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        case_id = report["cases"][0]["case_id"]
        connection.request(
            "GET",
            f"/audio/{case_id}/provider_synth.wav",
            headers={"Range": "bytes=2-5"},
        )
        audio = connection.getresponse()
        assert audio.status == 206
        assert audio.getheader("Content-Range").startswith("bytes 2-5/")
        assert len(audio.read()) == 4
        connection.request(
            "GET",
            f"/audio/{case_id}/provider_synth.wav",
            headers={"Range": "bytes=-4"},
        )
        suffix = connection.getresponse()
        assert suffix.status == 206
        assert len(suffix.read()) == 4
        connection.request(
            "GET",
            f"/audio/{case_id}/provider_synth.wav",
            headers={"Range": "bytes=999999999-"},
        )
        invalid_range = connection.getresponse()
        assert invalid_range.status == 416
        assert invalid_range.getheader("Content-Range").startswith("bytes */")
        assert invalid_range.read() == b""
        connection.request(
            "POST",
            "/save-review",
            body=b"{",
            headers={"Content-Type": "application/json"},
        )
        invalid_json = connection.getresponse()
        assert invalid_json.status == 400
        assert "invalid review JSON" in json.loads(invalid_json.read())["error"]
        connection.request(
            "POST",
            "/save-review",
            body=json.dumps(review),
            headers={"Content-Type": "application/json"},
        )
        saved = connection.getresponse()
        assert saved.status == 200
        assert (
            json.loads(saved.read())["document_sha256"] == validated["document_sha256"]
        )
        connection.request("GET", "/download-review")
        downloaded = connection.getresponse()
        assert downloaded.status == 200
        assert "attachment" in downloaded.getheader("Content-Disposition")
        assert downloaded.getheader("Content-Type") == "application/json"
        assert json.loads(downloaded.read())["status"] == review["status"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_provider_review_rejects_non_local_bind_before_opening_root(
    tmp_path: Path,
) -> None:
    try:
        build_provider_review_server(
            tmp_path / "missing-package",
            host="0.0.0.0",
            port=0,
        )
    except ValueError as error:
        assert str(error) == "provider review must bind to localhost"
    else:
        raise AssertionError("provider review accepted a non-local bind")


def test_provider_qualification_fails_closed_on_wrong_song(tmp_path: Path) -> None:
    import soundfile as sf

    request, integration, integration_root, inputs = _fixture(tmp_path)
    first = integration["cases"][0]
    path = integration_root / first["artifacts"]["reference"]["relative_path"]
    clock = np.arange(661_500, dtype=np.float64) / 44_100
    unrelated = 0.1 * np.sin(2 * np.pi * 1_337 * clock)
    sf.write(path, np.column_stack((unrelated, unrelated)), 44_100, subtype="PCM_24")
    first["artifacts"]["reference"] = _artifact(path, integration_root)
    request["cases"][0]["source_reference"] = {
        "role": "reference",
        **first["artifacts"]["reference"],
    }
    integration["report_sha256"] = integration_report_sha256(integration)
    request["integration_report_sha256"] = integration["report_sha256"]
    request["document_sha256"] = synth_bottleneck_plan_document_sha256(request)
    inputs["request_document_sha256"] = request["document_sha256"]
    destination = tmp_path / "fine-stem-synth-provider-qualification-v1"
    try:
        qualify_fine_stem_synth_provider_estimates(
            request=request,
            integration_report=integration,
            integration_root=integration_root,
            provider_inputs=inputs,
            out_dir=destination,
        )
    except RuntimeError as error:
        assert "failed source alignment" in str(error)
    else:
        raise AssertionError("wrong-song provider pack was accepted")
    assert not destination.exists()


def test_completed_presence_review_builds_exact_no_effects_12_attempt_plan(
    tmp_path: Path,
) -> None:
    request, integration, integration_root, inputs = _fixture(tmp_path)
    destination = tmp_path / "fine-stem-synth-provider-qualification-v1"
    report = qualify_fine_stem_synth_provider_estimates(
        request=request,
        integration_report=integration,
        integration_root=integration_root,
        provider_inputs=inputs,
        out_dir=destination,
    )
    review = build_provider_review_seed(report)
    for case in review["cases"]:
        case["played_items"] = ["source", "provider_synth"]
        case["listened"] = True
        case["provider_target_presence"] = "present"
        case["provider_role_breadth"] = "synth_or_keyboard_family"
    review["status"] = "human_provider_presence_review_complete_no_selection"
    outcome = validate_fine_stem_synth_provider_outcome(
        build_fine_stem_synth_provider_outcome(report=report, review=review)
    )
    assert outcome["status"] == READY_STATUS
    assert outcome["summary"]["confirmed_present_count"] == 4
    assert not any(outcome["effects"].values())

    plan = validate_fine_stem_synth_provider_midi_plan(
        build_fine_stem_synth_provider_midi_plan(
            request=request,
            qualification=report,
            outcome=outcome,
        )
    )
    assert plan["status"] == MIDI_PLAN_STATUS
    assert len(plan["attempts"]) == 12
    assert [attempt["attempt_number"] for attempt in plan["attempts"]] == list(
        range(1, 13)
    )
    assert all(set(case["arms"]) == set(ARM_IDS) for case in plan["cases"])
    assert all(
        set(case["blind_display_order"]) == set(ARM_IDS) for case in plan["cases"]
    )
    assert plan["execution_contract"]["separator_rerun"] is False
    assert plan["review_contract"]["manual_listened_checkbox"] is False
    assert not any(plan["effects"].values())

    review["cases"][0]["provider_target_presence"] = "absent"
    incomplete = validate_fine_stem_synth_provider_outcome(
        build_fine_stem_synth_provider_outcome(report=report, review=review)
    )
    assert incomplete["status"] == INCOMPLETE_STATUS
    try:
        build_fine_stem_synth_provider_midi_plan(
            request=request,
            qualification=report,
            outcome=incomplete,
        )
    except ValueError as error:
        assert "not confirmed present" in str(error)
    else:
        raise AssertionError("incomplete provider target cohort produced a MIDI plan")


def test_plan_bound_provider_synth_midi_executor_and_review_transport(
    tmp_path: Path,
) -> None:
    import soundfile as sf

    request, integration, integration_root, inputs = _fixture(tmp_path)
    provider_root = tmp_path / "fine-stem-synth-provider-qualification-v1"
    qualification = qualify_fine_stem_synth_provider_estimates(
        request=request,
        integration_report=integration,
        integration_root=integration_root,
        provider_inputs=inputs,
        out_dir=provider_root,
    )
    presence_review = build_provider_review_seed(qualification)
    for case in presence_review["cases"]:
        case["played_items"] = ["source", "provider_synth"]
        case["listened"] = True
        case["provider_target_presence"] = "present"
        case["provider_role_breadth"] = "synth_only"
    presence_review["status"] = "human_provider_presence_review_complete_no_selection"
    outcome = build_fine_stem_synth_provider_outcome(
        report=qualification,
        review=presence_review,
    )
    plan = build_fine_stem_synth_provider_midi_plan(
        request=request,
        qualification=qualification,
        outcome=outcome,
    )

    integration_technical = integration_root / "TECHNICAL"
    integration_technical.mkdir()
    (integration_technical / "INTEGRATION-REPORT.json").write_text(
        json.dumps(integration), encoding="utf-8"
    )
    (provider_root / "TECHNICAL/PROVIDER-PRESENCE-OUTCOME.json").write_text(
        json.dumps(outcome), encoding="utf-8"
    )
    plan_path = tmp_path / "PROVIDER-SYNTH-MIDI-PLAN.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    grouped_root = tmp_path / "grouped-other"
    for case in request["cases"]:
        relative = Path(case["grouped_other_control"]["relative_path"])
        target = grouped_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(integration_root / relative, target)

    transcription_paths: list[str] = []

    def transcribe(path: str, **parameters: object) -> list[NoteEvent]:
        assert parameters == {
            "kind": "synth",
            "onset_threshold": 0.5,
            "frame_threshold": 0.3,
            "min_note_ms": 60.0,
        }
        transcription_paths.append(path)
        return [NoteEvent(start=0.1, end=0.5, pitch=60, velocity=90)]

    def render(_midi_path: Path, wav_path: Path) -> None:
        clock = np.arange(44_100, dtype=np.float64) / 44_100
        mono = 0.05 * np.sin(2 * np.pi * 440 * clock)
        sf.write(wav_path, np.column_stack((mono, mono)), 44_100)

    def network() -> dict[str, object]:
        return {
            "os_network_denial_enforced": True,
            "python_network_attempts": 0,
        }
    rejected_output = tmp_path / "wrong-hash-output"
    try:
        execute_fine_stem_synth_provider_midi_canary(
            plan_path,
            integration_root=integration_root,
            provider_root=provider_root,
            grouped_other_root=grouped_root,
            out_dir=rejected_output,
            expected_plan_sha256="0" * 64,
            transcribe=transcribe,
            render=render,
            network_observation=network,
        )
    except ValueError as error:
        assert "plan SHA-256 differs" in str(error)
    else:
        raise AssertionError("unapproved provider synth MIDI plan was executed")
    assert not rejected_output.exists()
    assert transcription_paths == []

    output = tmp_path / "provider-synth-midi-canary"
    report = validate_fine_stem_synth_provider_midi_canary(
        execute_fine_stem_synth_provider_midi_canary(
            plan_path,
            integration_root=integration_root,
            provider_root=provider_root,
            grouped_other_root=grouped_root,
            out_dir=output,
            expected_plan_sha256=plan["document_sha256"],
            transcribe=transcribe,
            render=render,
            network_observation=network,
        )
    )
    assert report["status"] == CANARY_STATUS
    assert len(transcription_paths) == 12
    assert report["effects"]["midi_transcription_attempts"] == 12
    assert report["effects"]["private_audio_input_identities"] == 16
    assert report["effects"]["separator_inference_attempts"] == 0
    assert all(
        (output / case["outputs"][display]["midi"]["relative_path"]).is_file()
        and (
            output / case["outputs"][display]["preview"]["relative_path"]
        ).is_file()
        for case in report["cases"]
        for display in ("A", "B", "C")
    )

    page = render_provider_synth_midi_review(report)
    assert "Source reference" in page
    assert "MIDI A" in page and "MIDI B" in page and "MIDI C" in page
    assert "Playback recorded automatically" in page
    assert "currentTime > 0" in page
    assert "addEventListener('pause'" in page
    assert 'type="checkbox"' not in page
    assert "current_separator_estimate" not in page
    assert "provider_synth_estimate" not in page
    assert "grouped_other_control" not in page

    review = build_provider_synth_midi_review_seed(report)
    report_by_id = {case["case_id"]: case for case in report["cases"]}
    for index, case in enumerate(review["cases"]):
        case["played_items"] = ["source", "A", "B", "C"]
        case["listened"] = True
        display_by_arm = {
            output["arm_id"]: display_id
            for display_id, output in report_by_id[case["case_id"]][
                "outputs"
            ].items()
        }
        grouped = display_by_arm["grouped_other_control"]
        current = display_by_arm["current_separator_estimate"]
        provider = display_by_arm["provider_synth_estimate"]
        case["best_display"] = grouped
        case["ratings"][grouped] = {
            "recognisable_notes": "useful",
            "timing_usefulness": "useful",
            "edit_workload": "low",
        }
        current_recognisable = ("not_useful", "partly_useful", "useful", "useful")[
            index
        ]
        provider_recognisable = ("not_useful", "not_useful", "not_useful", "useful")[
            index
        ]
        case["ratings"][current] = {
            "recognisable_notes": current_recognisable,
            "timing_usefulness": "useful",
            "edit_workload": "low",
        }
        case["ratings"][provider] = {
            "recognisable_notes": provider_recognisable,
            "timing_usefulness": "cannot_tell",
            "edit_workload": "high",
        }
    review["status"] = "human_three_arm_listening_complete_no_selection"
    validated_review = validate_provider_synth_midi_review(review, report)
    outcome = validate_fine_stem_synth_provider_midi_outcome(
        build_fine_stem_synth_provider_midi_outcome(
            report=report, review=validated_review
        )
    )
    assert outcome["status"] == OUTCOME_STATUS
    assert outcome["summary"]["grouped_other_best_case_count"] == 4
    assert outcome["summary"]["isolated_arm_best_case_count"] == 0
    assert outcome["summary"]["current_vs_provider_recognisable_counts"] == {
        "current_separator_better": 2,
        "tie": 2,
    }
    assert not any(outcome["effects"].values())
    assert outcome["boundaries"]["source_selected"] is False
    assert outcome["decisions"]["audio_stem_evidence"]["status"].startswith(
        "retain_private"
    )

    server = build_provider_synth_midi_review_server(
        output, provider_root=provider_root, port=0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        case_id = report["cases"][0]["case_id"]
        connection.request(
            "GET", f"/source/{case_id}.wav", headers={"Range": "bytes=2-5"}
        )
        source_response = connection.getresponse()
        assert source_response.status == 206
        assert len(source_response.read()) == 4
        connection.request(
            "GET", f"/preview/{case_id}/A.wav", headers={"Range": "bytes=-4"}
        )
        preview_response = connection.getresponse()
        assert preview_response.status == 206
        assert len(preview_response.read()) == 4
        connection.request(
            "POST",
            "/save-review",
            body=json.dumps(review),
            headers={"Content-Type": "application/json"},
        )
        saved = connection.getresponse()
        assert saved.status == 200
        assert (
            json.loads(saved.read())["document_sha256"]
            == validated_review["document_sha256"]
        )
        connection.request("GET", "/download-review")
        downloaded = connection.getresponse()
        assert downloaded.status == 200
        assert "attachment" in downloaded.getheader("Content-Disposition")
        assert json.loads(downloaded.read())["status"].endswith(
            "complete_no_selection"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
