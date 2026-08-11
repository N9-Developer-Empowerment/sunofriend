from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request

import pytest

from sunofriend.separation_fine_stem_full_song_execution_contract import (
    ARTIFACT_ROLES,
    REPORT_SCHEMA,
    REPORT_STATUS,
    build_execution_request,
    execution_request_sha256,
    full_song_forward_budget,
    mega53_chunk_starts,
    report_sha256,
    scnet_forward_calls,
    sw_forward_calls,
    validate_execution_request,
    validate_full_song_report,
)
from sunofriend.separation_fine_stem_full_song_execution_review import (
    build_full_song_review_seed,
    build_full_song_review_server,
    render_full_song_review,
    validate_full_song_review,
)
from sunofriend.separation_fine_stem_full_song_plan_contract import (
    FULL_SONG_PLAN_SCHEMA,
    FULL_SONG_PLAN_STATUS,
    full_song_plan_document_sha256,
    full_song_profile_contracts,
    validate_fine_stem_full_song_plan,
)
from sunofriend.separation_fine_stem_integration_plan import PERSISTED_ROLES


def _target(role: str, *, index: int) -> dict:
    return {
        "case_id": f"presence-{index}-{role}",
        "target_id": "synth_keyboard" if role == "synth" else "guitar",
        "target_role": role,
        "window_seconds": [index * 10, index * 10 + 15],
        "human_decision": "present",
        "listened_before_model_scoring": True,
        "provider_label_used_as_truth": False,
        "source_excerpt": {
            "bytes": 3_969_044,
            "sha256": f"{index + 30:064x}",
            "sample_rate_hz": 44_100,
            "channels": 2,
            "frames": 661_500,
            "subtype": "PCM_24",
        },
    }


def _case(
    slot: str,
    track_id: str,
    *,
    frames: int,
    roles: list[str],
    index: int,
) -> dict:
    absolute = f"/private/{track_id}.wav"
    return {
        "slot": slot,
        "track_id": track_id,
        "title": track_id.replace("-", " ").title(),
        "rights_category": "owned",
        "scored_target_roles": roles,
        "unscored_target_roles": [
            role for role in ("synth", "guitar") if role not in roles
        ],
        "confirmed_present_targets": [
            _target(role, index=index + target_index)
            for target_index, role in enumerate(roles)
        ],
        "full_song_source": {
            "absolute_path": absolute,
            "relative_path": f"{track_id}.wav",
            "bytes": 10_000 + index,
            "sha256": f"{index + 1:064x}",
            "sample_rate_hz": 48_000,
            "channels": 2,
            "frames": frames,
            "expected_canonical_sample_rate_hz": 44_100,
            "expected_canonical_channels": 2,
            "expected_canonical_frames": frames,
            "expected_canonical_subtype": "PCM_24",
        },
        "planning_observation": {
            "absolute_path": absolute,
            "regular_file": True,
            "observed_bytes": 10_000 + index,
            "content_opened": False,
        },
        "unconfirmed_target_absence_is_model_failure": False,
    }


def _plan() -> dict:
    plan = {
        "schema": FULL_SONG_PLAN_SCHEMA,
        "document_sha256": "",
        "status": FULL_SONG_PLAN_STATUS,
        "cases": [
            _case(
                "both_targets",
                "both",
                frames=1_000_000,
                roles=["guitar", "synth"],
                index=0,
            ),
            _case(
                "synth",
                "synth-only",
                frames=2_000_000,
                roles=["synth"],
                index=1,
            ),
            _case(
                "guitar",
                "guitar-only",
                frames=3_000_000,
                roles=["guitar"],
                index=2,
            ),
        ],
        "profiles": full_song_profile_contracts(),
        "execution_contract": {
            "execution_authorized": False,
            "source_files": 3,
            "canonicalization_attempts": 3,
            "model_loads": 3,
            "models_run_sequentially": True,
            "profile_inference_attempts": {
                "core_four": 3,
                "synth": 3,
                "guitar": 3,
                "total": 9,
            },
            "automatic_retry": False,
            "network_denied": True,
            "writer_count": 1,
            "maximum_elapsed_seconds_per_song": 900,
            "maximum_total_elapsed_seconds": 2700,
            "maximum_peak_unified_memory_bytes": 30 * 1024**3,
        },
        "output_contract": {
            "persisted_roles": list(PERSISTED_ROLES),
            "projection": {
                "method": "fixed grouped-other-constrained three-way Wiener mask",
                "components": ["raw synth", "raw guitar", "raw residual"],
                "residual_other_constructed_last": True,
            },
        },
        "admission_policy": {
            "subjective_feedback_is_execution_veto": False,
            "minimum_usefulness_rating": None,
            "poor_feedback_disables_core_four": False,
        },
        "review_contract": {
            "playback_recorded_automatically": True,
            "listened_checkbox": False,
            "score_only_confirmed_present_target_roles": True,
            "minimum_usefulness_for_private_package": None,
            "review_selects_source_or_midi": False,
        },
        "next_approval": {
            "required": True,
            "received": False,
            "bind_document_sha256_in_approval": True,
            "exact_text_template": "approve [PLAN_SHA256]",
        },
        "effects": {},
        "boundaries": {
            "plan_only": True,
            "source_content_opened": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_run": False,
            "private_audio_written": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
    }
    plan["document_sha256"] = full_song_plan_document_sha256(plan)
    return validate_fine_stem_full_song_plan(plan)


def _artifact(track_id: str, role: str, frames: int, index: int) -> dict:
    return {
        "relative_path": f"CASES/{track_id}/{role}.wav",
        "bytes": 1_000 + index,
        "sha256": f"{100 + index:064x}",
        "sample_rate_hz": 44_100,
        "channels": 2,
        "frames": frames,
        "subtype": "PCM_24",
    }


def _report(plan: dict) -> dict:
    budget = full_song_forward_budget(plan)
    synth_calls = budget["mega53_forward_calls"]
    guitar_calls = budget["sw_forward_calls"]
    report = {
        "schema": REPORT_SCHEMA,
        "report_sha256": "",
        "status": REPORT_STATUS,
        "plan_sha256": plan["document_sha256"],
        "approved_plan_sha256": plan["document_sha256"],
        "release_tier": "private_studio_challenger",
        "profiles": plan["profiles"],
        "forward_budget": budget,
        "runtime": {
            "network_denied_by_parent_sandbox": True,
            "models_run_sequentially": True,
            "writer_count": 1,
        },
        "workers": {
            role: {
                "profile_id": plan["profiles"][role]["profile_id"],
                "model_loads": 1,
                "profile_inference_attempts": 3,
                "internal_forward_calls": (
                    synth_calls
                    if role == "synth"
                    else guitar_calls
                    if role == "guitar"
                    else budget["scnet_forward_calls"]
                ),
                "network_attempts": 0,
                "runtime": {"network_denied": True},
            }
            for role in ("core_four", "synth", "guitar")
        },
        "cases": [],
        "resources": {
            "within_ceilings": True,
            "elapsed_seconds": 100.0,
            "peak_memory_bytes": 1_000_000,
        },
        "accounting": {
            "projection": plan["output_contract"]["projection"],
            "maximum_reconstruction_error_lsb": 0,
            "reconstruction_accounting_is_separation_accuracy": False,
        },
        "effects": {
            "model_loads": 3,
            "profile_inference_attempts": 9,
            "source_files": 3,
            "canonicalization_attempts": 3,
            "audio_writes": 24,
            "network_attempts": 0,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
    }
    for case_index, planned in enumerate(plan["cases"]):
        frames = planned["full_song_source"]["expected_canonical_frames"]
        report["cases"].append(
            {
                "track_id": planned["track_id"],
                "title": planned["title"],
                "rights_category": planned["rights_category"],
                "scored_target_roles": planned["scored_target_roles"],
                "unscored_target_roles": planned["unscored_target_roles"],
                "confirmed_present_targets": planned["confirmed_present_targets"],
                "source_input": {
                    "bytes": planned["full_song_source"]["bytes"],
                    "sha256": planned["full_song_source"]["sha256"],
                },
                "elapsed_seconds": 30.0,
                "projection": {
                    "method": "fixed grouped-other-constrained three-way Wiener mask"
                },
                "maximum_reconstruction_error_lsb": 0,
                "artifacts": {
                    role: _artifact(
                        planned["track_id"],
                        role,
                        frames,
                        case_index * len(ARTIFACT_ROLES) + role_index,
                    )
                    for role_index, role in enumerate(ARTIFACT_ROLES)
                },
            }
        )
    report["report_sha256"] = report_sha256(report)
    return validate_full_song_report(report, plan)


def test_forward_budgets_cover_exact_clock_without_unbounded_search() -> None:
    assert mega53_chunk_starts(881_664) == (0,)
    assert mega53_chunk_starts(881_665) == (0, 440_832)
    assert sw_forward_calls(100) == 1
    assert sw_forward_calls(1_000_000) == 6
    assert scnet_forward_calls(1_000_000) == 3
    budget = full_song_forward_budget(_plan())
    assert budget["profile_attempts"] == 9
    assert budget["mega53_forward_calls"] == 12
    assert budget["sw_forward_calls"] == 28


def test_execution_request_is_path_light_and_has_no_effects() -> None:
    plan = _plan()
    request = build_execution_request(plan, proposed_output="/private/output")

    assert request["status"] == "explicit_exact_hash_approval_required"
    assert request["plan_sha256"] == plan["document_sha256"]
    assert request["effects"]["source_content_reads"] == 0
    assert request["effects"]["model_loads"] == 0
    assert request["effects"]["inference_attempts"] == 0
    assert "absolute_path" not in json.dumps(request)


def test_no_effects_cli_neither_opens_sources_nor_creates_output(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "private-output"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    completed = subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts/run-fine-stem-full-song-six-role.py"
            ),
            "--plan",
            str(plan_path),
            "--out",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    request = json.loads(completed.stdout)
    assert request["effects"]["source_content_reads"] == 0
    assert request["effects"]["audio_writes"] == 0
    assert not output.exists()


def test_execution_request_rejects_rehashed_permission_drift() -> None:
    plan = _plan()
    request = build_execution_request(plan, proposed_output="/private/output")
    request["effects"]["inference_attempts"] = 9
    request["document_sha256"] = execution_request_sha256(request)

    with pytest.raises(ValueError, match="effects"):
        validate_execution_request(request, plan)


def test_report_rejects_specialist_forward_or_source_drift() -> None:
    plan = _plan()
    report = _report(plan)
    changed = copy.deepcopy(report)
    changed["workers"]["synth"]["internal_forward_calls"] += 1
    changed["report_sha256"] = report_sha256(changed)
    with pytest.raises(ValueError, match="forward accounting"):
        validate_full_song_report(changed, plan)

    changed = copy.deepcopy(report)
    changed["cases"][0]["source_input"]["sha256"] = "f" * 64
    changed["report_sha256"] = report_sha256(changed)
    with pytest.raises(ValueError, match="case contract"):
        validate_full_song_report(changed, plan)


def test_poor_review_completes_without_disabling_core_four() -> None:
    plan = _plan()
    report = _report(plan)
    review = build_full_song_review_seed(report, plan)
    for row, case in zip(review["cases"], report["cases"]):
        row["played_items"] = list(ARTIFACT_ROLES)
        row["listened"] = True
        row["confirmed_windows_played"] = [
            f"{target['target_role']}:{target['window_seconds'][0]}-{target['window_seconds'][1]}"
            for target in case["confirmed_present_targets"]
        ]
        row["confirmed_windows_replayed"] = True
        row["catastrophic_result"] = "no_catastrophic_defect"
        row["overall_usefulness"] = "not_useful"
        row["role_usefulness"] = {role: "not_useful" for role in row["role_usefulness"]}
        row["issues"] = {
            role: {field: "severe" for field in ratings}
            for role, ratings in row["issues"].items()
        }
    review["status"] = "human_listening_complete_no_selection"

    validated = validate_full_song_review(review, report, plan)

    assert validated["status"] == "human_listening_complete_no_selection"
    assert validated["boundaries"]["poor_feedback_disables_core_four"] is False


def test_review_renders_auto_playback_and_no_listened_checkbox() -> None:
    page = render_full_song_review(_report(_plan()), _plan())

    assert "Playback recorded automatically" in page
    assert 'type="checkbox"' not in page
    assert "confirmed-present source window" in page
    assert "Download saved JSON" in page
    assert "No source choice or MIDI is made here" in page


def test_review_rejects_private_metadata_injection() -> None:
    plan = _plan()
    report = _report(plan)
    review = build_full_song_review_seed(report, plan)
    review["source_path"] = "/private/song.wav"

    with pytest.raises(ValueError, match="unexpected metadata"):
        validate_full_song_review(review, report, plan)


def test_review_server_saves_and_downloads_bound_json(tmp_path: Path) -> None:
    plan = _plan()
    report = _report(plan)
    package = tmp_path / "package"
    for case in report["cases"]:
        for role, artifact in case["artifacts"].items():
            path = package / artifact["relative_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"audio:{case['track_id']}:{role}".encode())
            artifact["bytes"] = path.stat().st_size
            artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    report["report_sha256"] = report_sha256(report)
    technical = package / "TECHNICAL"
    technical.mkdir()
    (package / "REVIEW").mkdir()
    (technical / "FULL-SONG-SIX-ROLE-REPORT.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    server = build_full_song_review_server(package, plan_path=plan_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            assert "Download saved JSON" in response.read().decode()
        audio_route = report["cases"][0]["artifacts"]["reference"]["relative_path"]
        audio_request = urllib.request.Request(
            base + "/" + audio_route, headers={"Range": "bytes=0-3"}
        )
        with urllib.request.urlopen(audio_request, timeout=5) as response:
            assert response.status == 206
            assert response.read() == b"audi"
        seed = build_full_song_review_seed(report, plan)
        request = urllib.request.Request(
            base + "/save-review",
            data=json.dumps(seed).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            saved = json.loads(response.read())
        assert saved["report_sha256"] == report["report_sha256"]
        assert saved["document_sha256"]
        with urllib.request.urlopen(base + "/download-review", timeout=5) as response:
            downloaded = json.loads(response.read())
            assert "attachment" in response.headers["Content-Disposition"]
        assert downloaded == saved
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
