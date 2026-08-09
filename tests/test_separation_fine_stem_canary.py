from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import threading
from types import ModuleType

import numpy as np
import pytest

from sunofriend.separation_bs_roformer_mlx_runtime import (
    compare_exact_mlx_state,
    install_verified_source_package,
    tensor_inventory,
)
import sunofriend.separation_fine_stem_canary_audio as audio_module
from sunofriend.separation_fine_stem_canary_audio import (
    PCM24_MAX,
    PCM24_MIN,
    persist_target_and_residual,
)
from sunofriend.separation_fine_stem_canary_contract import (
    CANARY_REPORT_SCHEMA,
    PROFILE_CONTRACTS,
    build_fine_stem_canary_plan,
    canary_document_sha256,
    validate_fine_stem_canary_plan,
    validate_fine_stem_canary_report,
)
from sunofriend.separation_fine_stem_canary_review import (
    build_fine_stem_review_server,
    build_fine_stem_canary_review_seed,
    render_fine_stem_review,
    validate_fine_stem_canary_review,
)
from sunofriend.separation_fine_stem_canary_outcome import (
    build_fine_stem_portfolio_outcome,
    validate_fine_stem_portfolio_outcome,
)
from sunofriend.separation_fine_stem_integration_audio import (
    project_within_grouped_other,
    quantize_six_roles,
)
from sunofriend.separation_fine_stem_integration_plan import (
    build_fine_stem_six_role_integration_plan,
    validate_fine_stem_six_role_integration_plan,
)
from sunofriend.separation_target_presence_review import (
    PRESENCE_MANIFEST_SCHEMA,
    presence_document_sha256,
)


def _presence(decision: str, *, complete: bool = True) -> tuple[dict, dict]:
    targets = {
        "synth_keyboard": {"label": "Synth", "definition": "Synth"},
        "guitar": {"label": "Guitar", "definition": "Guitar"},
    }
    cases = []
    results = []
    for target in targets:
        for index in range(4):
            case_id = f"track-{index}--{target}"
            cases.append(
                {
                    "case_id": case_id,
                    "track_id": f"track-{index}",
                    "title": f"Track {index}",
                    "target_id": target,
                    "window_seconds": [5, 20],
                    "artifacts": {
                        "source": {
                            "relative_path": f"CASES/{case_id}/source.wav",
                            "bytes": 123,
                            "sha256": str(index) * 64,
                        }
                    },
                }
            )
            results.append(
                {
                    "case_id": case_id,
                    "track_id": f"track-{index}",
                    "target_id": target,
                    "window_seconds": [5, 20],
                    "listened": complete,
                    "decision": decision if complete else "",
                    "notes": "",
                }
            )
    manifest = {
        "schema": PRESENCE_MANIFEST_SCHEMA,
        "document_sha256": "",
        "status": "source_presence_pending_no_model_inference",
        "targets": targets,
        "cases": cases,
    }
    manifest["document_sha256"] = presence_document_sha256(manifest)
    result = {
        "schema": "sunofriend.fine-stem-target-presence-result.v1",
        "document_sha256": "",
        "status": (
            "presence_review_complete_no_model_inference"
            if complete
            else "presence_review_incomplete_no_model_inference"
        ),
        "manifest_sha256": manifest["document_sha256"],
        "cases": results,
        "boundaries": {
            "provider_estimates_are_truth": False,
            "model_inference_started": False,
            "source_selected": False,
            "midi_created": False,
            "audio_uploaded": False,
            "telemetry": False,
        },
    }
    return manifest, result


def _objective_report(
    profile_id: str = "bs-roformer-mega-53-synth-v1",
) -> dict:
    manifest, present = _presence("present")
    plan = build_fine_stem_canary_plan(
        profile_id,
        manifest,
        present,
        checkpoint_available=True,
        config_available=True,
    )
    target_role = PROFILE_CONTRACTS[profile_id]["target_role"]
    cases = []
    for planned in plan["cases"]:
        artifacts = {}
        for role in ("reference", "target", "residual"):
            artifacts[role] = {
                "relative_path": f"CASES/{planned['case_id']}/{role}.wav",
                "bytes": 1,
                "sha256": "0" * 64,
                "sample_rate_hz": 44100,
                "channels": 2,
                "frames": 661500,
                "subtype": "PCM_24",
            }
        cases.append(
            {
                "case_id": planned["case_id"],
                "track_id": planned["track_id"],
                "title": planned["title"],
                "window_seconds": planned["window_seconds"],
                "target_role": target_role,
                "source_input_sha256": planned["source_artifact"]["sha256"],
                "all_samples_finite": True,
                "maximum_reconstruction_error_lsb": 0,
                "artifacts": artifacts,
            }
        )
    report = {
        "schema": CANARY_REPORT_SCHEMA,
        "report_sha256": "",
        "status": "objective_execution_complete_review_required",
        "profile_id": profile_id,
        "target_role": target_role,
        "plan": plan,
        "cases": cases,
        "guards": {
            "network_attempts": 0,
            "forbidden_audio_attempts": 0,
            "external_checkpoint_attempts": 0,
            "approved_audio_open_events": 12,
            "restricted_torch_load_calls": 1,
            "forward_calls": plan["execution"]["model_forward_calls"],
            "expected_forward_calls": plan["execution"]["model_forward_calls"],
            "os_network_denial_required": True,
        },
        "resource": {
            "elapsed_seconds": 1.0,
            "peak_mlx_memory_bytes": 1024,
            "elapsed_ceiling_seconds": 900,
            "memory_ceiling_bytes": 30 * 1024**3,
        },
        "effects": {
            "checkpoint_loads": 1,
            "model_constructions": 1,
            "inference_attempts": 4,
            "audio_reads": 4,
            "audio_writes": 12,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "automatic_retry": False,
            "human_review_recorded": False,
        },
    }
    report["report_sha256"] = canary_document_sha256(report)
    return report


def test_canary_plan_requires_four_confirmed_present_cases() -> None:
    manifest, incomplete = _presence("", complete=False)
    plan = build_fine_stem_canary_plan(
        "bs-roformer-mega-53-synth-v1",
        manifest,
        incomplete,
        checkpoint_available=True,
        config_available=True,
    )
    assert plan["status"] == "blocked_target_presence_review_incomplete"
    assert plan["effects"]["inference_attempts"] == 0

    manifest, absent = _presence("absent")
    plan = build_fine_stem_canary_plan(
        "bs-roformer-sw-guitar-v1",
        manifest,
        absent,
        checkpoint_available=True,
        config_available=True,
    )
    assert plan["status"] == "blocked_replacement_target_presence_required"
    assert plan["presence_binding"]["absent_or_cannot_tell_is_model_failure"] is False

    manifest, present = _presence("present")
    plan = validate_fine_stem_canary_plan(
        build_fine_stem_canary_plan(
            "bs-roformer-sw-guitar-v1",
            manifest,
            present,
            checkpoint_available=True,
            config_available=True,
        )
    )
    assert plan["status"] == "ready_for_bounded_private_execution"
    assert len(plan["cases"]) == 4
    assert plan["execution"]["model_forward_calls"] == 20
    assert plan["execution"]["automatic_retry"] is False


def test_each_profile_only_waits_for_its_own_presence_decisions() -> None:
    manifest, result = _presence("present")
    for case in result["cases"]:
        if case["target_id"] == "guitar":
            case["listened"] = False
            case["decision"] = ""
    result["status"] = "presence_review_incomplete_no_model_inference"
    synth = build_fine_stem_canary_plan(
        "bs-roformer-mega-53-synth-v1",
        manifest,
        result,
        checkpoint_available=True,
        config_available=True,
    )
    guitar = build_fine_stem_canary_plan(
        "bs-roformer-sw-guitar-v1",
        manifest,
        result,
        checkpoint_available=True,
        config_available=True,
    )
    assert synth["status"] == "ready_for_bounded_private_execution"
    assert guitar["status"] == "blocked_target_presence_review_incomplete"


def test_missing_sw_checkpoint_is_an_objective_plan_block_not_an_inference() -> None:
    manifest, present = _presence("present")
    plan = build_fine_stem_canary_plan(
        "bs-roformer-sw-guitar-v1",
        manifest,
        present,
        checkpoint_available=False,
        config_available=True,
    )
    assert plan["status"] == "blocked_verified_profile_artifact_missing"
    assert plan["artifact_availability"] == {"checkpoint": False, "config": True}
    assert not any(plan["effects"].values())


def test_pcm24_target_and_residual_reconstruct_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audio_module, "WINDOW_FRAMES", 64)
    source = np.linspace(-0.9, 0.9, 128, dtype=np.float64).reshape(64, 2)
    target = np.linspace(-1.4, 1.4, 128, dtype=np.float64).reshape(64, 2)
    result = persist_target_and_residual(
        tmp_path,
        case_id="case",
        source=source,
        native_target=target,
        target_role="synth",
    )
    assert result["maximum_reconstruction_error_lsb"] == 0
    assert 0 < result["shared_attenuation"] < 1
    import soundfile as sf

    values = {}
    for name, artifact in result["artifacts"].items():
        path = tmp_path / artifact["relative_path"]
        values[name] = np.rint(sf.read(path, dtype="float64")[0] * 2**23).astype(
            np.int64
        )
        assert values[name].min() >= PCM24_MIN
        assert values[name].max() <= PCM24_MAX
    assert np.array_equal(values["target"] + values["residual"], values["reference"])


def test_report_validator_keeps_review_and_activation_separate() -> None:
    report = _objective_report()
    validated = validate_fine_stem_canary_report(report)
    assert validated["effects"]["human_review_recorded"] is False
    review = build_fine_stem_canary_review_seed(validated)
    for case in review["cases"]:
        case["played_items"] = ["reference", "target", "residual"]
        case["listened"] = True
        case["catastrophic_result"] = "no_catastrophic_defect"
        case["usefulness"] = "cannot_tell"
    review["status"] = "human_listening_complete_no_selection"
    review = validate_fine_stem_canary_review(review, validated)
    assert review["document_sha256"]
    page = render_fine_stem_review(validated)
    assert page.count("Reference mix") == 4
    assert "/save-review" in page and "/download-review" in page
    assert "Copy text-only feedback" in page
    assert 'type="checkbox"' not in page
    assert "addEventListener('play'" in page
    assert "scheduleSave" in page
    assert "localStorage.setItem" in page
    assert "localStorage.getItem" in page
    assert "JSON.stringify(out,null,2)+'\\n'" in page
    assert "lines.join('\\n')" in page
    assert 'data-player-id="reference"' in page
    review["cases"][0]["catastrophic_result"] = "catastrophic_defect"
    review["cases"][0]["catastrophic_details"] = ""
    review["document_sha256"] = ""
    with pytest.raises(ValueError, match="needs details"):
        validate_fine_stem_canary_review(review, validated)
    report["effects"]["source_selection"] = True
    report["report_sha256"] = canary_document_sha256(report)
    with pytest.raises(ValueError, match="expanded authority"):
        validate_fine_stem_canary_report(report)


def test_completed_portfolio_qualifies_both_targets_without_activation() -> None:
    reports = {
        "synth": _objective_report("bs-roformer-mega-53-synth-v1"),
        "guitar": _objective_report("bs-roformer-sw-guitar-v1"),
    }
    reviews = {}
    for role, report in reports.items():
        review = build_fine_stem_canary_review_seed(report)
        for index, case in enumerate(review["cases"]):
            case["played_items"] = ["reference", "target", "residual"]
            case["listened"] = True
            case["catastrophic_result"] = "no_catastrophic_defect"
            case["usefulness"] = "useful" if index == 0 else "partly_useful"
            case["issues"] = {
                "bleed": "none",
                "missing_content": "none" if index == 0 else "some",
                "artefacts": "none",
                "timing_or_join_problems": "none",
            }
        review["status"] = "human_listening_complete_no_selection"
        reviews[role] = validate_fine_stem_canary_review(review, report)

    outcome = validate_fine_stem_portfolio_outcome(
        build_fine_stem_portfolio_outcome(
            synth_report=reports["synth"],
            synth_review=reviews["synth"],
            guitar_report=reports["guitar"],
            guitar_review=reviews["guitar"],
        )
    )

    assert outcome["both_targets_qualified"] is True
    assert all(
        target["success_fraction_all_present"] == 1.0
        for target in outcome["targets"]
    )
    assert not any(outcome["effects"].values())
    assert outcome["boundaries"]["public_activation"] is False


def test_qualified_portfolio_prepares_no_effects_six_role_plan() -> None:
    reports = {
        "synth": _objective_report("bs-roformer-mega-53-synth-v1"),
        "guitar": _objective_report("bs-roformer-sw-guitar-v1"),
    }
    reviews = {}
    for role, report in reports.items():
        review = build_fine_stem_canary_review_seed(report)
        for case in review["cases"]:
            case["played_items"] = ["reference", "target", "residual"]
            case["listened"] = True
            case["catastrophic_result"] = "no_catastrophic_defect"
            case["usefulness"] = "partly_useful"
        review["status"] = "human_listening_complete_no_selection"
        reviews[role] = validate_fine_stem_canary_review(review, report)
    outcome = build_fine_stem_portfolio_outcome(
        synth_report=reports["synth"],
        synth_review=reviews["synth"],
        guitar_report=reports["guitar"],
        guitar_review=reviews["guitar"],
    )
    plan = validate_fine_stem_six_role_integration_plan(
        build_fine_stem_six_role_integration_plan(
            portfolio_outcome=outcome,
            synth_report=reports["synth"],
            synth_review=reviews["synth"],
            guitar_report=reports["guitar"],
            guitar_review=reviews["guitar"],
        )
    )
    assert plan["integration_contract"]["persisted_roles"] == [
        "vocals",
        "drums",
        "bass",
        "synth",
        "guitar",
        "other",
    ]
    assert len(plan["cases"]) == 8
    assert plan["execution_contract"]["new_synth_inference_attempts"] == 4
    assert plan["execution_contract"]["new_guitar_inference_attempts"] == 4
    assert plan["next_approval"]["required"] is True
    assert not any(plan["effects"].values())


def test_grouped_other_projection_and_six_role_pcm24_are_exact() -> None:
    frames = 12_288
    clock = np.arange(frames, dtype=np.float64) / 44_100
    vocals = np.column_stack(
        (0.04 * np.sin(2 * np.pi * 220 * clock),) * 2
    )
    drums = np.column_stack(
        (0.03 * np.sign(np.sin(2 * np.pi * 4 * clock)),) * 2
    )
    bass = np.column_stack(
        (0.05 * np.sin(2 * np.pi * 55 * clock),) * 2
    )
    native_synth = np.column_stack(
        (0.07 * np.sin(2 * np.pi * 880 * clock),) * 2
    )
    native_guitar = np.column_stack(
        (0.06 * np.sin(2 * np.pi * 330 * clock),) * 2
    )
    native_other = np.column_stack(
        (0.02 * np.sin(2 * np.pi * 510 * clock),) * 2
    )
    grouped_other = native_synth + native_guitar + native_other
    reference = vocals + drums + bass + grouped_other
    projected = project_within_grouped_other(
        grouped_other,
        native_synth + 0.01 * vocals,
        native_guitar + 0.01 * drums,
    )
    assert projected["accounting"]["maximum_float_reconstruction_error"] < 1e-12
    quantized = quantize_six_roles(
        reference=reference,
        vocals=vocals,
        drums=drums,
        bass=bass,
        synth=projected["synth"],
        guitar=projected["guitar"],
    )
    assert quantized["maximum_reconstruction_error_lsb"] == 0
    assert set(quantized["roles"]) == {
        "vocals",
        "drums",
        "bass",
        "synth",
        "guitar",
        "other",
    }
    assert all(
        value.min() >= PCM24_MIN and value.max() <= PCM24_MAX
        for value in quantized["roles"].values()
    )


def test_review_server_ranges_audio_and_saves_bound_json(tmp_path: Path) -> None:
    report = _objective_report()
    payload = b"RIFF-private-test-audio"
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = tmp_path / artifact["relative_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            artifact["bytes"] = len(payload)
            artifact["sha256"] = audio_module.file_sha256(path)
    report["report_sha256"] = canary_document_sha256(report)
    technical = tmp_path / "TECHNICAL"
    review_root = tmp_path / "REVIEW"
    technical.mkdir()
    review_root.mkdir()
    (technical / "CANARY-REPORT.json").write_text(json.dumps(report))
    (review_root / "fine_stem_review.html").write_text(
        render_fine_stem_review(report)
    )
    server = build_fine_stem_review_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        route = "/" + report["cases"][0]["artifacts"]["target"]["relative_path"]
        connection.request("GET", route, headers={"Range": "bytes=1-4"})
        response = connection.getresponse()
        assert response.status == 206
        assert response.getheader("Accept-Ranges") == "bytes"
        assert response.read() == payload[1:5]
        seed = build_fine_stem_canary_review_seed(report)
        body = json.dumps(seed)
        connection.request(
            "POST",
            "/save-review",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        saved = json.loads(response.read())
        assert saved["report_sha256"] == report["report_sha256"]
        connection.request("GET", "/download-review")
        response = connection.getresponse()
        assert response.status == 200
        assert "attachment" in response.getheader("Content-Disposition")
        assert json.loads(response.read())["document_sha256"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_shared_state_helpers_are_strict_and_path_independent() -> None:
    first = {"a": np.zeros((2, 3), dtype=np.float32)}
    second = {"a": np.zeros((2, 3), dtype=np.float32)}
    compare_exact_mlx_state(first, second)
    inventory = tensor_inventory(first)
    assert inventory["key_count"] == 1
    assert inventory["total_numel"] == 6
    with pytest.raises(RuntimeError, match="keys differ"):
        compare_exact_mlx_state(first, {"b": second["a"]})


def test_verified_source_install_purges_previously_imported_bs_roformer(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src/bs_roformer"
    package.mkdir(parents=True)
    stale = ModuleType("bs_roformer.stale")
    sys.modules["bs_roformer.stale"] = stale
    try:
        install_verified_source_package(tmp_path)
        assert "bs_roformer.stale" not in sys.modules
        assert sys.modules["bs_roformer"].__path__ == [str(package)]
    finally:
        for name in tuple(sys.modules):
            if name == "bs_roformer" or name.startswith("bs_roformer."):
                del sys.modules[name]


def test_runner_has_no_download_fallback_and_preserves_private_boundaries() -> None:
    source = (Path(__file__).parents[1] / "scripts/run-fine-stem-canary.py").read_text()
    assert "sandbox-exec" in source and "(deny network*)" in source
    assert "ensure_model_assets" not in source
    assert "download" not in source.lower()
    assert '"automatic_retry": False' in source
    assert '"source_selection": False' in source
    assert '"midi_created": False' in source
    assert set(PROFILE_CONTRACTS) == {
        "bs-roformer-mega-53-synth-v1",
        "bs-roformer-sw-guitar-v1",
    }
