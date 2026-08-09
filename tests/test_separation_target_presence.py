from __future__ import annotations

import json
from pathlib import Path
import threading
from urllib.request import Request, urlopen

import numpy as np
import pytest

from sunofriend.separation_target_presence_plan import (
    TARGET_PRESENCE_PACKAGE_NAME,
    build_target_presence_plan,
    validate_target_presence_plan,
)
from sunofriend.separation_target_presence_addition_plan import (
    TARGET_PRESENCE_ADDITION_PACKAGE_NAME,
    build_target_presence_addition_plan,
    validate_target_presence_addition_plan,
)
from sunofriend.separation_target_presence_replacement_plan import (
    TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME,
    build_target_presence_replacement_plan,
    validate_target_presence_replacement_plan,
)
import sunofriend.separation_target_presence_review as review_module
from sunofriend.separation_target_presence_review import (
    PRESENCE_MANIFEST_SCHEMA,
    attest_completed_presence_listening,
    build_presence_review_server,
    presence_document_sha256,
    render_presence_review,
    select_consensus_window,
    validate_presence_result,
)


def _manifest(tmp_path: Path) -> dict[str, object]:
    cases = []
    for target in ("synth_keyboard", "guitar"):
        case_id = f"track--{target}"
        case_root = tmp_path / "CASES" / case_id
        case_root.mkdir(parents=True)
        source = case_root / "source.wav"
        hint = case_root / "provider-hint-1.wav"
        source.write_bytes(b"source-audio")
        hint.write_bytes(b"hint-audio")
        cases.append(
            {
                "case_id": case_id,
                "track_id": "track",
                "title": "Track",
                "target_id": target,
                "window_seconds": [5, 20],
                "selection_score": 1.0,
                "selection_used_separator_output": False,
                "provider_estimates_are_truth": False,
                "source_input": {},
                "hint_inputs": [{}],
                "artifacts": {
                    "source": {
                        "relative_path": source.relative_to(tmp_path).as_posix(),
                        "bytes": source.stat().st_size,
                        "sha256": "0" * 64,
                    },
                    "hints": [
                        {
                            "relative_path": hint.relative_to(tmp_path).as_posix(),
                            "bytes": hint.stat().st_size,
                            "sha256": "0" * 64,
                        }
                    ],
                },
            }
        )
    manifest: dict[str, object] = {
        "schema": PRESENCE_MANIFEST_SCHEMA,
        "document_sha256": "",
        "status": "source_presence_pending_no_model_inference",
        "plan_sha256": "1" * 64,
        "targets": build_target_presence_plan()["targets"],
        "cases": cases,
        "input_count": 3,
        "effects": build_target_presence_plan()["effects"],
    }
    manifest["document_sha256"] = presence_document_sha256(manifest)
    technical = tmp_path / "TECHNICAL"
    review = tmp_path / "REVIEW"
    technical.mkdir()
    review.mkdir()
    (technical / "PRESENCE-MANIFEST.json").write_text(json.dumps(manifest))
    (review / "presence.html").write_text(render_presence_review(manifest))
    return manifest


def _result(manifest: dict[str, object], *, complete: bool) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "sunofriend.fine-stem-target-presence-result.v1",
        "document_sha256": "",
        "status": (
            "presence_review_complete_no_model_inference"
            if complete
            else "presence_review_incomplete_no_model_inference"
        ),
        "manifest_sha256": manifest["document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "track_id": case["track_id"],
                "target_id": case["target_id"],
                "window_seconds": case["window_seconds"],
                "listened": complete,
                "decision": "present" if complete else "",
                "notes": "",
            }
            for case in manifest["cases"]  # type: ignore[index]
        ],
        "boundaries": {
            "provider_estimates_are_truth": False,
            "model_inference_started": False,
            "source_selected": False,
            "midi_created": False,
            "audio_uploaded": False,
            "telemetry": False,
        },
    }
    return value


def test_presence_plan_is_four_tracks_two_targets_and_no_model_effects() -> None:
    plan = validate_target_presence_plan(build_target_presence_plan())
    assert plan["package_name"] == TARGET_PRESENCE_PACKAGE_NAME
    assert len(plan["tracks"]) == 4
    assert set(plan["targets"]) == {"synth_keyboard", "guitar"}
    assert all(set(track["hints"]) == set(plan["targets"]) for track in plan["tracks"])
    assert plan["selection"]["present_required_before_model_inference"] is True
    assert plan["selection"]["absent_or_cannot_tell_counts_as_model_failure"] is False
    assert plan["effects"]["checkpoint_opened"] is False
    assert plan["effects"]["model_constructed"] is False
    assert plan["effects"]["inference_attempts"] == 0


def test_replacement_plan_is_frozen_song_disjoint_and_model_free() -> None:
    plan = validate_target_presence_replacement_plan(
        build_target_presence_replacement_plan()
    )
    assert plan["package_name"] == TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME
    assert len(plan["cases"]) == 8
    for target_id in plan["targets"]:
        cases = [case for case in plan["cases"] if case["target_id"] == target_id]
        assert len(cases) == 4
        assert len({case["track_id"] for case in cases}) == 4
        assert all(case["window_seconds"][1] - case["window_seconds"][0] == 15 for case in cases)
    assert plan["selection"]["model_output_used"] is False
    assert plan["selection"]["automatic_retry"] is False
    assert plan["effects"]["checkpoint_opened"] is False
    assert plan["effects"]["inference_attempts"] == 0


def test_addition_plan_needs_one_new_song_per_target_and_no_model() -> None:
    plan = validate_target_presence_addition_plan(
        build_target_presence_addition_plan()
    )
    assert plan["package_name"] == TARGET_PRESENCE_ADDITION_PACKAGE_NAME
    assert {case["target_id"] for case in plan["cases"]} == set(plan["targets"])
    assert len({case["track_id"] for case in plan["cases"]}) == 2
    assert all(case["hint_sha256"] for case in plan["cases"])
    assert plan["selection"]["model_output_used"] is False
    assert plan["effects"]["checkpoint_opened"] is False
    assert plan["effects"]["inference_attempts"] == 0


def test_consensus_selection_uses_provider_energy_and_stable_earliest_tie() -> None:
    first = np.zeros(50)
    second = np.zeros(50)
    first[12:27] = 1.0
    second[12:27] = 2.0
    start, score = select_consensus_window(
        [first, second], source_duration_seconds=50
    )
    assert start == 12
    assert score == pytest.approx(1.0)
    tied_start, _ = select_consensus_window(
        [np.ones(50), np.ones(50)], source_duration_seconds=50
    )
    assert tied_start == 5


def test_presence_result_requires_exact_binding_and_supports_absent() -> None:
    plan = build_target_presence_plan()
    manifest: dict[str, object] = {
        "schema": PRESENCE_MANIFEST_SCHEMA,
        "document_sha256": "2" * 64,
        "status": "source_presence_pending_no_model_inference",
        "targets": plan["targets"],
        "cases": [
            {
                "case_id": "track--synth_keyboard",
                "track_id": "track",
                "target_id": "synth_keyboard",
                "window_seconds": [5, 20],
            }
        ],
    }
    value = _result(manifest, complete=True)
    value["cases"][0]["decision"] = "absent"  # type: ignore[index]
    validated = validate_presence_result(value, manifest)  # type: ignore[arg-type]
    assert validated["status"] == "presence_review_complete_no_model_inference"
    assert validated["cases"][0]["decision"] == "absent"
    assert validated["document_sha256"] == presence_document_sha256(validated)


def test_explicit_completion_attestation_preserves_decisions_and_notes(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    value = _result(manifest, complete=False)
    for case in value["cases"]:  # type: ignore[index]
        case["decision"] = "present"
        case["notes"] = "remembered decision"
        case["played_items"] = ["source"]
    value["document_sha256"] = ""
    validated = validate_presence_result(value, manifest)

    attested = attest_completed_presence_listening(
        validated, manifest, recorded_at="2026-08-09T16:55:00+00:00"
    )

    assert attested["status"] == "presence_review_complete_no_model_inference"
    assert all(case["listened"] for case in attested["cases"])
    assert all(case["decision"] == "present" for case in attested["cases"])
    assert all(case["notes"] == "remembered decision" for case in attested["cases"])
    assert attested["listen_attestation"]["source"] == (
        "explicit_user_review_completion_statement"
    )


def test_presence_page_and_server_save_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(review_module, "file_sha256", lambda _path: "0" * 64)
    page = (tmp_path / "REVIEW/presence.html").read_text()
    assert "No separator output exists" in page
    assert "/save-presence" in page
    assert "Provider attention hints" in page
    assert 'type="checkbox"' not in page
    assert "addEventListener('play'" in page
    assert "scheduleSave" in page
    assert "localStorage.setItem" in page
    assert "localStorage.getItem" in page
    assert 'data-player-id="source"' in page
    server = build_presence_review_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz") as response:
            assert response.status == 200
        payload = json.dumps(_result(manifest, complete=True)).encode()
        request = Request(
            f"http://127.0.0.1:{port}/save-presence",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            saved = json.loads(response.read())
        assert saved["status"] == "presence_review_complete_no_model_inference"
        assert (tmp_path / "PRESENCE-RESULT.json").exists()
        with urlopen(f"http://127.0.0.1:{port}/download-presence") as response:
            assert "attachment" in response.headers["Content-Disposition"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
