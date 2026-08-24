from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request
import wave

import numpy as np
import pytest

import sunofriend.separation_fine_stem_full_song_recovery as recovery_module
import sunofriend.separation_fine_stem_full_song_outcome as outcome_module

from sunofriend.separation_fine_stem_full_song_execution_contract import (
    ARTIFACT_ROLES,
    FAILURE_SCHEMA,
    WORKER_REQUEST_SCHEMA,
    WORKER_RESULT_SCHEMA,
    full_song_forward_budget,
    mega53_chunk_starts,
    scnet_forward_calls,
)
from sunofriend.separation_fine_stem_full_song_execution_review import (
    build_full_song_review_seed,
    build_full_song_review_server,
    validate_full_song_review,
)
from sunofriend.separation_fine_stem_full_song_outcome import (
    OUTCOME_DIRECTORY_NAME,
    OUTCOME_FILE_NAME,
    _verify_outcome_file,
    build_full_song_six_role_outcome,
    outcome_document_sha256,
    record_full_song_six_role_outcome,
    validate_full_song_six_role_outcome,
)
from sunofriend.separation_fine_stem_full_song_plan_contract import (
    FULL_SONG_PLAN_SCHEMA,
    FULL_SONG_PLAN_STATUS,
    full_song_plan_document_sha256,
    full_song_profile_contracts,
    validate_fine_stem_full_song_plan,
)
from sunofriend.separation_fine_stem_full_song_recovery import (
    NETWORK_SANDBOX_ENV,
    RECOVERY_AUDIO_WRITES,
    RECOVERY_REPORT_STATUS,
    _exclusive_publish,
    build_recovery_request,
    execute_recovery,
    recovery_request_sha256,
    recovery_report_sha256,
    validate_recovery_request,
    validate_recovery_report,
)
from sunofriend.separation_fine_stem_integration_plan import PERSISTED_ROLES


@pytest.fixture(autouse=True)
def _declared_synthetic_network_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark direct synthetic calls; production obtains this only by CLI reexec."""

    monkeypatch.setenv(NETWORK_SANDBOX_ENV, "1")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pack_pcm24(integer: np.ndarray) -> bytes:
    return b"".join(
        int(value).to_bytes(3, "little", signed=True) for value in integer.reshape(-1)
    )


def _private_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(payload)
    path.chmod(0o600)
    for parent in path.parents:
        if parent.name.startswith("test_"):
            break
        if parent.exists():
            parent.chmod(0o700)
    return path


def _write_json(path: Path, value: dict) -> Path:
    return _private_file(
        path,
        (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode(),
    )


def _presence(role: str, index: int) -> dict:
    return {
        "case_id": f"presence-{index}-{role}",
        "target_id": "synth_keyboard" if role == "synth" else "guitar",
        "target_role": role,
        "window_seconds": [0, 1],
        "human_decision": "present",
        "listened_before_model_scoring": True,
        "provider_label_used_as_truth": False,
        "source_excerpt": {
            "bytes": 100,
            "sha256": f"{index + 20:064x}",
            "sample_rate_hz": 44_100,
            "channels": 2,
            "frames": 44_100,
            "subtype": "PCM_24",
        },
    }


def _plan(frames: int) -> dict:
    cases = []
    selections = (
        ("both_targets", "both", ["guitar", "synth"]),
        ("synth", "synth", ["synth"]),
        ("guitar", "guitar", ["guitar"]),
    )
    for index, (slot, track, roles) in enumerate(selections):
        source_path = f"/private/{track}.wav"
        cases.append(
            {
                "slot": slot,
                "track_id": track,
                "title": track.title(),
                "rights_category": "owned",
                "scored_target_roles": roles,
                "unscored_target_roles": [
                    role for role in ("synth", "guitar") if role not in roles
                ],
                "confirmed_present_targets": [
                    _presence(role, index * 2 + role_index)
                    for role_index, role in enumerate(roles)
                ],
                "full_song_source": {
                    "absolute_path": source_path,
                    "relative_path": f"{track}.wav",
                    "bytes": 1_000 + index,
                    "sha256": f"{index + 1:064x}",
                    "sample_rate_hz": 44_100,
                    "channels": 2,
                    "frames": frames,
                    "expected_canonical_sample_rate_hz": 44_100,
                    "expected_canonical_channels": 2,
                    "expected_canonical_frames": frames,
                    "expected_canonical_subtype": "PCM_24",
                },
                "planning_observation": {
                    "absolute_path": source_path,
                    "regular_file": True,
                    "observed_bytes": 1_000 + index,
                    "content_opened": False,
                },
                "unconfirmed_target_absence_is_model_failure": False,
            }
        )
    plan = {
        "schema": FULL_SONG_PLAN_SCHEMA,
        "document_sha256": "",
        "status": FULL_SONG_PLAN_STATUS,
        "cases": cases,
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
        "next_approval": {"required": True, "received": False},
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


def _write_pcm24(path: Path, samples: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    integer = np.rint(samples * (2**23)).astype(np.int32)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(_pack_pcm24(integer))
    path.chmod(0o600)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
        "sample_rate_hz": 44_100,
        "channels": 2,
        "frames": len(samples),
        "subtype": "PCM_24",
    }


def _write_array(path: Path, value: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("wb") as handle:
        np.save(handle, value.astype(np.float32), allow_pickle=False)
    path.chmod(0o600)
    as_float = value.astype(np.float64)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
        "shape": list(value.shape),
        "dtype": "float32",
        "finite": True,
        "rms": float(np.sqrt(np.mean(np.square(as_float)))),
        "peak": float(np.max(np.abs(as_float), initial=0.0)),
    }


def _effects() -> dict:
    return {
        "model_loads": 1,
        "profile_inference_attempts": 3,
        "network_attempts": 0,
        "automatic_retry": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
    }


def _failed_fixture(tmp_path: Path, *, frames: int = 4096) -> tuple[dict, Path, Path]:
    plan = _plan(frames)
    failed = tmp_path / "replacement-FAILED"
    failed.mkdir(mode=0o700)
    prior = tmp_path / "first-FAILED"
    prior.mkdir(mode=0o700)
    _write_json(prior / "FAILED-REPORT.json", {"status": "retained"})
    _private_file(prior / "TEMP/canonical/reference.wav", b"retained-private-audio")
    clock = np.arange(frames, dtype=np.float32) / 44_100
    reference = np.column_stack((0.2 * np.sin(2 * np.pi * 220 * clock),) * 2)
    request_cases = []
    scnet_request_cases = []
    synth_request_cases = []
    scnet_cases = []
    synth_cases = []
    for index, planned in enumerate(plan["cases"]):
        track = planned["track_id"]
        canonical = _write_pcm24(
            failed / f"TEMP/canonical/{track}/reference.wav", reference
        )
        guitar_path = failed / f"TEMP/guitar/{track}/guitar.npy"
        request_cases.append(
            {
                "track_id": track,
                "source": canonical,
                "output": str(guitar_path),
            }
        )
        scnet_outputs = {
            role: _write_array(
                failed / f"TEMP/scnet/{track}/{role}.npy",
                reference * fraction,
            )
            for role, fraction in {
                "vocals": 0.2,
                "drums": 0.15,
                "bass": 0.1,
                "other": 0.55,
            }.items()
        }
        synth_output = _write_array(
            failed / f"TEMP/synth/{track}/synth.npy", reference * 0.2
        )
        _write_array(guitar_path, reference * 0.15)
        scnet_request_cases.append(
            {
                "track_id": track,
                "source": canonical,
                "outputs": {
                    role: str(failed / f"TEMP/scnet/{track}/{role}.npy")
                    for role in ("vocals", "drums", "bass", "other")
                },
            }
        )
        synth_request_cases.append(
            {
                "track_id": track,
                "source": canonical,
                "output": str(failed / f"TEMP/synth/{track}/synth.npy"),
            }
        )
        scnet_cases.append(
            {
                "track_id": track,
                "elapsed_seconds": 1.0,
                "forward_calls": scnet_forward_calls(frames),
                "shift_offset_frames": 0,
                "outputs": scnet_outputs,
            }
        )
        synth_cases.append(
            {
                "track_id": track,
                "elapsed_seconds": 1.0,
                "forward_calls": len(mega53_chunk_starts(frames)),
                "outputs": {"synth": synth_output},
            }
        )
    budget = full_song_forward_budget(plan)
    common = {"schema": WORKER_REQUEST_SCHEMA, "network_denied": True}
    _write_json(
        failed / "TEMP/scnet-request.json",
        {
            **common,
            "mode": "scnet",
            "expected_forward_calls": budget["scnet_forward_calls"],
            "cases": scnet_request_cases,
        },
    )
    _write_json(
        failed / "TEMP/mega53-synth-request.json",
        {
            **common,
            "mode": "mega53-synth",
            "expected_forward_calls": budget["mega53_forward_calls"],
            "cases": synth_request_cases,
        },
    )
    _write_json(
        failed / "TEMP/sw-guitar-request.json",
        {
            **common,
            "mode": "sw-guitar",
            "expected_forward_calls": budget["sw_forward_calls"],
            "cases": request_cases,
        },
    )
    for mode, profile, calls, cases, name, peak in (
        (
            "scnet",
            plan["profiles"]["core_four"]["profile_id"],
            budget["scnet_forward_calls"],
            scnet_cases,
            "scnet-result.json",
            1_000_000,
        ),
        (
            "mega53-synth",
            plan["profiles"]["synth"]["profile_id"],
            budget["mega53_forward_calls"],
            synth_cases,
            "mega53-synth-result.json",
            2_000_000,
        ),
    ):
        _write_json(
            failed / "TEMP" / name,
            {
                "schema": WORKER_RESULT_SCHEMA,
                "status": "complete_unpublished_private_temporary_estimates",
                "mode": mode,
                "runtime": {"network_denied": True},
                "model": {
                    "profile_id": profile,
                    "model_loads": 1,
                    "forward_calls": calls,
                    "peak_unified_memory_bytes": peak,
                },
                "cases": cases,
                "elapsed_seconds": 3.0,
                "effects": _effects(),
            },
        )
    _write_json(
        failed / "FAILED-REPORT.json",
        {
            "schema": FAILURE_SCHEMA,
            "status": "objective_failure_retained_no_retry",
            "plan_sha256": plan["document_sha256"],
            "approved_plan_sha256": plan["document_sha256"],
            "failure_type": "RuntimeError",
            "failure": "fine-stem canary crossed its effects boundary",
            "elapsed_seconds": 10.0,
            "automatic_retry": False,
        },
    )
    # Retain a known legacy aggregate mode and prove recovery does not mutate it.
    (failed / "TEMP/scnet").chmod(0o755)
    return plan, failed, prior


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_preflight_binds_exact_tree_and_hashes_guitar_without_writes(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    before = _tree_bytes(failed)
    output = tmp_path / "recovered"

    first = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    second = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )

    assert first == second
    assert first["document_sha256"]
    assert "src/sunofriend/_private_atomic_directory.py" in {
        item["relative_path"] for item in first["implementation"]
    }
    assert len(first["retained_tree"]["files"]) == 27
    assert first["retained_tree"]["legacy_inner_directory_modes_0755"] == 4
    guitar = [row for row in first["retained_payloads"] if row["role"] == "guitar"]
    assert all(len(row["expected_sha256"]) == 64 for row in guitar)
    assert first["effects"]["audio_payloads_opened"] == 4
    assert first["effects"]["retained_json_files_content_read"] == 6
    assert (
        first["retained_json"]["failure_report"]["observed_file_identity"]["links"] == 1
    )
    assert first["prior_failed_package"]["files_content_hashed"] == 2
    assert first["prior_failed_package"]["audio_payloads_content_hashed"] == 1
    assert not output.exists()
    assert _tree_bytes(failed) == before


@pytest.mark.parametrize(
    ("relative_path", "field_path", "replacement", "message"),
    [
        (
            "TEMP/scnet-request.json",
            ("expected_forward_calls",),
            -1,
            "forward budget",
        ),
        (
            "TEMP/scnet-request.json",
            ("cases", 0, "source", "channels"),
            1,
            "source binding",
        ),
        (
            "TEMP/scnet-request.json",
            ("cases", 0, "outputs", "vocals"),
            "TEMP/scnet/both/not-vocals.npy",
            "SCNet request paths",
        ),
        (
            "TEMP/mega53-synth-request.json",
            ("cases", 0, "output"),
            "TEMP/synth/both/not-synth.npy",
            "specialist request path",
        ),
        (
            "TEMP/sw-guitar-request.json",
            ("network_denied",),
            False,
            "worker request differs",
        ),
    ],
)
def test_preflight_rejects_each_worker_request_boundary(
    tmp_path: Path,
    relative_path: str,
    field_path: tuple[object, ...],
    replacement: object,
    message: str,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    path = failed / relative_path
    value = json.loads(path.read_text(encoding="utf-8"))
    target = value
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = replacement
    _write_json(path, value)

    with pytest.raises(ValueError, match=message):
        build_recovery_request(
            plan,
            failed,
            proposed_output=tmp_path / "recovered",
            prior_failed_root_value=prior,
        )


def test_historical_request_without_atomic_helper_remains_reviewable_only(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    current = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    legacy = copy.deepcopy(current)
    legacy["implementation"] = [
        item
        for item in legacy["implementation"]
        if item["relative_path"] != "src/sunofriend/_private_atomic_directory.py"
    ]
    legacy["document_sha256"] = recovery_request_sha256(legacy)

    assert validate_recovery_request(legacy, plan) == legacy
    with pytest.raises(RuntimeError, match="retained package changed after approval"):
        execute_recovery(
            plan,
            legacy,
            approved_recovery_sha256=legacy["document_sha256"],
            confirm_rights=True,
            network_sandbox_verified=True,
        )


def test_model_free_recovery_writes_24_pcm24_and_visible_banner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    before = _tree_bytes(failed)
    prior_before = _tree_bytes(prior)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("model-free recovery ran a subprocess"),
    )
    original_import = builtins.__import__

    def reject_model_imports(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: object = (),
        level: int = 0,
    ) -> object:
        if name == "torch" or "full_song_execution_worker" in name:
            pytest.fail(f"model-free recovery imported forbidden module {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_model_imports)

    report = execute_recovery(
        plan,
        request,
        approved_recovery_sha256=request["document_sha256"],
        confirm_rights=True,
        network_sandbox_verified=True,
    )

    assert report["status"] == RECOVERY_REPORT_STATUS
    assert report["full_objective_qualification"] is False
    assert report["workers"]["guitar"]["internal_forward_calls"] is None
    assert report["resources"]["full_resource_gate_complete"] is False
    assert report["effects"]["recovery"]["model_loads"] == 0
    assert report["effects"]["recovery"]["checkpoint_loads"] == 0
    assert report["effects"]["recovery"]["model_constructions"] == 0
    assert report["effects"]["recovery"]["model_worker_subprocesses"] == 0
    assert report["effects"]["recovery"]["current_audio_payload_file_opens"] == 21
    assert report["effects"]["recovery"]["prior_failed_audio_payload_hash_opens"] == 3
    assert (
        report["recovered_inputs"]["both"]["reference"]["observed_file_identity"][
            "links"
        ]
        == 1
    )
    assert len(list((output / "CASES").rglob("*.wav"))) == RECOVERY_AUDIO_WRITES
    assert all(
        (path.stat().st_mode & 0o777) == 0o600
        for path in output.rglob("*")
        if path.is_file()
    )
    assert all(
        (path.stat().st_mode & 0o777) == 0o700
        for path in (output, *output.rglob("*"))
        if path.is_dir()
    )
    page = (output / "REVIEW/full_song_six_role_review.html").read_text()
    assert "Recovered without rerunning any model" in page
    assert "not full objective qualification" in page
    assert _tree_bytes(failed) == before
    assert _tree_bytes(prior) == prior_before

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    server = build_full_song_review_server(output, plan_path=plan_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            assert "Recovered without rerunning any model" in response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_report_cannot_turn_unknown_guitar_peak_into_qualification(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    report = execute_recovery(
        plan,
        request,
        approved_recovery_sha256=request["document_sha256"],
        confirm_rights=True,
        network_sandbox_verified=True,
    )
    changed = json.loads(json.dumps(report))
    changed["workers"]["guitar"]["peak_memory_bytes"] = 1
    changed["full_objective_qualification"] = True
    changed["report_sha256"] = recovery_report_sha256(changed)
    with pytest.raises(ValueError, match="identity|resource"):
        validate_recovery_report(changed, plan, request)


def _completed_review_fixture(
    tmp_path: Path,
) -> tuple[dict, dict, dict, dict, dict, Path]:
    plan, failed, prior = _failed_fixture(tmp_path)
    recovery_root = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=recovery_root,
        prior_failed_root_value=prior,
    )
    report = execute_recovery(
        plan,
        request,
        approved_recovery_sha256=request["document_sha256"],
        confirm_rights=True,
        network_sandbox_verified=True,
    )
    review = build_full_song_review_seed(report, plan)
    for row, case in zip(review["cases"], report["cases"]):
        row["played_items"] = list(ARTIFACT_ROLES)
        row["listened"] = True
        row["confirmed_windows_played"] = [
            f"{target['target_role']}:{target['window_seconds'][0]}-"
            f"{target['window_seconds'][1]}"
            for target in case["confirmed_present_targets"]
        ]
        row["confirmed_windows_replayed"] = True
        row["catastrophic_result"] = "no_catastrophic_defect"
        row["overall_usefulness"] = "useful"
        row["role_usefulness"] = {role: "useful" for role in row["role_usefulness"]}
        row["issues"] = {
            role: {
                field: (
                    "some"
                    if role in {"synth", "guitar"} and field == "missing_content"
                    else "none"
                )
                for field in ratings
            }
            for role, ratings in row["issues"].items()
        }
    review["status"] = "human_listening_complete_no_selection"
    review = validate_full_song_review(review, report, plan)
    review_path = _write_json(
        recovery_root / "REVIEW/FULL-SONG-SIX-ROLE-LISTENING.json",
        review,
    )
    review_file = {
        "bytes": review_path.stat().st_size,
        "sha256": _sha(review_path),
    }
    return plan, request, report, review, review_file, recovery_root


def test_completed_review_records_self_contained_resource_incomplete_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, request, report, review, review_file, recovery_root = (
        _completed_review_fixture(tmp_path)
    )

    outcome = build_full_song_six_role_outcome(
        plan=plan,
        recovery_request=request,
        recovery_report=report,
        review=review,
        review_file=review_file,
    )

    outcome_sources = {
        "plan": plan,
        "recovery_request": request,
        "recovery_report": report,
        "review": review,
        "review_file": review_file,
    }
    assert validate_full_song_six_role_outcome(outcome, **outcome_sources) == outcome
    assert outcome["review_summary"]["played_item_count"] == 24
    assert outcome["review_summary"]["confirmed_window_replay_count"] == 4
    assert outcome["review_summary"]["all_scored_roles_useful"] is True
    assert outcome["review_summary"]["specialist_missing_content_rating_count"] == 4
    assert outcome["objective_gaps"]["guitar_peak_memory_bytes"] is None
    assert outcome["boundaries"]["profile_qualification"] is False
    assert outcome["effects"]["audio_reads"] == 0

    original_open = os.open

    def reject_audio_open(path: object, *args: object, **kwargs: object) -> int:
        if str(path).endswith((".wav", ".npy")):
            pytest.fail(f"outcome recorder opened audio payload {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", reject_audio_open)
    outcome_root = recovery_root.parent / OUTCOME_DIRECTORY_NAME
    recorded = record_full_song_six_role_outcome(
        recovery_root,
        plan_path=_write_json(tmp_path / "plan.json", plan),
        out_dir=outcome_root,
    )
    assert recorded == outcome
    assert (outcome_root.stat().st_mode & 0o777) == 0o700
    outcome_path = outcome_root / OUTCOME_FILE_NAME
    assert (outcome_path.stat().st_mode & 0o777) == 0o600
    assert json.loads(outcome_path.read_text(encoding="utf-8")) == outcome
    with pytest.raises(FileExistsError, match="fresh"):
        record_full_song_six_role_outcome(
            recovery_root,
            plan_path=tmp_path / "plan.json",
            out_dir=outcome_root,
        )
    with pytest.raises(ValueError, match="exact recovery-package sibling"):
        record_full_song_six_role_outcome(
            recovery_root,
            plan_path=tmp_path / "plan.json",
            out_dir=tmp_path / "nested" / OUTCOME_DIRECTORY_NAME,
        )

    changed = copy.deepcopy(outcome)
    changed["objective_gaps"]["full_objective_qualification"] = True
    changed["document_sha256"] = outcome_document_sha256(changed)
    with pytest.raises(ValueError, match="objective gap"):
        validate_full_song_six_role_outcome(changed, **outcome_sources)

    injected = copy.deepcopy(outcome)
    injected["review_summary"]["roles"][0]["source_path"] = "/private/song.wav"
    injected["document_sha256"] = outcome_document_sha256(injected)
    with pytest.raises(ValueError, match="role fields"):
        validate_full_song_six_role_outcome(injected, **outcome_sources)

    inconsistent = copy.deepcopy(outcome)
    inconsistent["review_summary"]["catastrophic_counts"] = {
        "not_tested": 0,
        "no_catastrophic_defect": 0,
        "catastrophic_defect": 3,
        "cannot_tell": 0,
    }
    inconsistent["document_sha256"] = outcome_document_sha256(inconsistent)
    with pytest.raises(ValueError, match="aggregate"):
        validate_full_song_six_role_outcome(inconsistent, **outcome_sources)


@pytest.mark.parametrize("mutation", ["replacement", "extra_file"])
def test_outcome_staging_verifier_rejects_child_tree_swap(
    tmp_path: Path,
    mutation: str,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    staging_descriptor = os.open(
        staging,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    payload = b'{"outcome":true}\n'
    outcome_descriptor = os.open(
        OUTCOME_FILE_NAME,
        os.O_RDWR | os.O_CREAT | os.O_EXCL,
        0o600,
        dir_fd=staging_descriptor,
    )
    try:
        assert os.write(outcome_descriptor, payload) == len(payload)
        identity = _verify_outcome_file(
            staging_descriptor,
            outcome_descriptor,
            payload,
        )
        if mutation == "replacement":
            os.unlink(OUTCOME_FILE_NAME, dir_fd=staging_descriptor)
            replacement = os.open(
                OUTCOME_FILE_NAME,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=staging_descriptor,
            )
            try:
                assert os.write(replacement, payload) == len(payload)
            finally:
                os.close(replacement)
        else:
            extra = os.open(
                "EXTRA",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=staging_descriptor,
            )
            os.close(extra)
        with pytest.raises(RuntimeError, match="staged file identity"):
            _verify_outcome_file(
                staging_descriptor,
                outcome_descriptor,
                payload,
                expected_identity=identity,
            )
    finally:
        os.close(outcome_descriptor)
        os.close(staging_descriptor)


def test_outcome_recorder_quarantines_post_rename_child_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _request, _report, _review, _review_file, recovery_root = (
        _completed_review_fixture(tmp_path)
    )
    plan_path = _write_json(tmp_path / "plan.json", plan)
    outcome_root = recovery_root.parent / OUTCOME_DIRECTORY_NAME
    original_rename = outcome_module.rename_directory_no_replace_at
    attacked = False

    def attack_before_first_rename(
        parent_descriptor: int,
        source_name: str,
        destination_name: str,
        **kwargs: object,
    ) -> None:
        nonlocal attacked
        if destination_name == OUTCOME_DIRECTORY_NAME and not attacked:
            attacked = True
            staging_descriptor = os.open(
                source_name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            try:
                os.unlink(OUTCOME_FILE_NAME, dir_fd=staging_descriptor)
                for name, payload in (
                    (OUTCOME_FILE_NAME, b'{"attacker":true}\n'),
                    ("EXTRA", b"extra"),
                ):
                    descriptor = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=staging_descriptor,
                    )
                    try:
                        assert os.write(descriptor, payload) == len(payload)
                    finally:
                        os.close(descriptor)
            finally:
                os.close(staging_descriptor)
        original_rename(
            parent_descriptor,
            source_name,
            destination_name,
            **kwargs,
        )

    monkeypatch.setattr(
        outcome_module,
        "rename_directory_no_replace_at",
        attack_before_first_rename,
    )
    with pytest.raises(RuntimeError, match="staged file identity"):
        record_full_song_six_role_outcome(
            recovery_root,
            plan_path=plan_path,
            out_dir=outcome_root,
        )

    assert not outcome_root.exists()
    quarantines = list(outcome_root.parent.glob(f"{OUTCOME_DIRECTORY_NAME}-FAILED-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / OUTCOME_FILE_NAME).read_bytes() == b'{"attacker":true}\n'
    assert (quarantines[0] / "EXTRA").read_bytes() == b"extra"


def test_retained_mutation_and_atomic_publish_race_are_rejected(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    guitar = failed / "TEMP/guitar/both/guitar.npy"
    guitar.write_bytes(guitar.read_bytes() + b"tamper")
    guitar.chmod(0o600)
    with pytest.raises(RuntimeError, match="changed after approval"):
        execute_recovery(
            plan,
            request,
            approved_recovery_sha256=request["document_sha256"],
            confirm_rights=True,
            network_sandbox_verified=True,
        )

    staging = tmp_path / "staging"
    staging.mkdir()
    staging.chmod(0o700)
    destination = tmp_path / "occupied"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        _exclusive_publish(staging, destination)
    assert staging.is_dir()
    assert destination.is_dir()


def test_cross_worker_canonical_identity_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    path = failed / "TEMP/mega53-synth-request.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["cases"][0]["source"]["sha256"] = "f" * 64
    _write_json(path, value)

    with pytest.raises(ValueError, match="canonical identities"):
        build_recovery_request(
            plan,
            failed,
            proposed_output=tmp_path / "recovered",
            prior_failed_root_value=prior,
        )


@pytest.mark.parametrize("unexpected", ["extra", "symlink"])
def test_retained_tree_rejects_extra_files_and_symlinks(
    tmp_path: Path,
    unexpected: str,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    if unexpected == "extra":
        _private_file(failed / "TEMP/unexpected.bin", b"unexpected")
    else:
        (failed / "TEMP/unexpected-link").symlink_to(failed / "FAILED-REPORT.json")

    with pytest.raises(ValueError, match="inventory|symlink"):
        build_recovery_request(
            plan,
            failed,
            proposed_output=tmp_path / "recovered",
            prior_failed_root_value=prior,
        )


def test_prior_failed_package_content_drift_is_rejected(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    _private_file(prior / "TEMP/canonical/reference.wav", b"changed-private-audio")

    with pytest.raises(RuntimeError, match="changed after approval"):
        execute_recovery(
            plan,
            request,
            approved_recovery_sha256=request["document_sha256"],
            confirm_rights=True,
            network_sandbox_verified=True,
        )
    assert not output.exists()


@pytest.mark.parametrize("failure_kind", ["non_finite", "dtype", "shape"])
def test_recovery_rejects_invalid_bound_guitar_arrays(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    frames = plan["cases"][0]["full_song_source"]["expected_canonical_frames"]
    path = failed / "TEMP/guitar/both/guitar.npy"
    if failure_kind == "non_finite":
        value = np.full((frames, 2), np.nan, dtype=np.float32)
    elif failure_kind == "dtype":
        value = np.zeros((frames, 2), dtype=np.float64)
    else:
        value = np.zeros((frames - 1, 2), dtype=np.float32)
    with path.open("wb") as handle:
        np.save(handle, value, allow_pickle=False)
    path.chmod(0o600)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )

    with pytest.raises(ValueError, match="geometry|dtype|samples"):
        execute_recovery(
            plan,
            request,
            approved_recovery_sha256=request["document_sha256"],
            confirm_rights=True,
            network_sandbox_verified=True,
        )
    failure_root = output.with_name(output.name + "-RECOVERY-FAILED")
    failure = json.loads(
        (failure_root / "RECOVERY-FAILED-REPORT.json").read_text(encoding="utf-8")
    )
    assert failure["checkpoint_loads"] == 0
    assert failure["model_constructions"] == 0
    assert failure["model_worker_subprocesses"] == 0


def test_execute_requires_declared_network_sandbox_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    monkeypatch.delenv(NETWORK_SANDBOX_ENV)

    with pytest.raises(RuntimeError, match="network-denied CLI context"):
        execute_recovery(
            plan,
            request,
            approved_recovery_sha256=request["document_sha256"],
            confirm_rights=True,
            network_sandbox_verified=True,
        )
    assert not output.exists()


def test_output_must_resolve_to_exact_failed_root_sibling(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    alias = tmp_path / "redirected-parent"
    alias.symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(ValueError, match="exact sibling"):
        build_recovery_request(
            plan,
            failed,
            proposed_output=alias / "recovered",
            prior_failed_root_value=prior,
        )


def test_report_is_bound_to_exact_recovery_request_and_zero_effects(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=tmp_path / "recovered",
        prior_failed_root_value=prior,
    )
    report = execute_recovery(
        plan,
        request,
        approved_recovery_sha256=request["document_sha256"],
        confirm_rights=True,
        network_sandbox_verified=True,
    )
    other_request = build_recovery_request(
        plan,
        failed,
        proposed_output=tmp_path / "other-recovery",
        prior_failed_root_value=prior,
    )
    with pytest.raises(ValueError, match="request binding"):
        validate_recovery_report(report, plan, other_request)

    changed = json.loads(json.dumps(report))
    changed["effects"]["recovery"]["checkpoint_loads"] = 1
    changed["report_sha256"] = recovery_report_sha256(changed)
    with pytest.raises(ValueError, match="effects"):
        validate_recovery_report(changed, plan, request)

    changed_input = json.loads(json.dumps(report))
    changed_input["recovered_inputs"]["both"]["guitar"]["sha256"] = "e" * 64
    changed_input["report_sha256"] = recovery_report_sha256(changed_input)
    with pytest.raises(ValueError, match="input request binding"):
        validate_recovery_report(changed_input, plan, request)

    changed_forward = json.loads(json.dumps(report))
    changed_forward["workers"]["synth"]["internal_forward_calls"] += 1
    changed_forward["report_sha256"] = recovery_report_sha256(changed_forward)
    with pytest.raises(ValueError, match="worker summary"):
        validate_recovery_report(changed_forward, plan, request)


def test_raced_success_destination_publishes_recovery_failure_exclusively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    original = recovery_module._exclusive_publish
    calls = 0

    def race_once(staging: Path, destination: Path, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            destination.mkdir(mode=0o700)
        original(staging, destination, **kwargs)

    monkeypatch.setattr(recovery_module, "_exclusive_publish", race_once)
    with pytest.raises(FileExistsError):
        execute_recovery(
            plan,
            request,
            approved_recovery_sha256=request["document_sha256"],
            confirm_rights=True,
            network_sandbox_verified=True,
        )
    assert output.is_dir()
    assert not any(output.iterdir())
    failed_output = output.with_name(output.name + "-RECOVERY-FAILED")
    assert (failed_output / "RECOVERY-FAILED-REPORT.json").is_file()


def test_cli_report_validation_requires_sibling_recovery_request(
    tmp_path: Path,
) -> None:
    plan, failed, prior = _failed_fixture(tmp_path)
    output = tmp_path / "recovered"
    request = build_recovery_request(
        plan,
        failed,
        proposed_output=output,
        prior_failed_root_value=prior,
    )
    execute_recovery(
        plan,
        request,
        approved_recovery_sha256=request["document_sha256"],
        confirm_rights=True,
        network_sandbox_verified=True,
    )
    plan_path = _write_json(tmp_path / "plan.json", plan)
    report_path = output / "TECHNICAL/FULL-SONG-SIX-ROLE-RECOVERY-REPORT.json"
    command = [
        sys.executable,
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/recover-fine-stem-full-song-six-role.py"
        ),
        "--plan",
        str(plan_path),
        "--validate-report",
        str(report_path),
    ]
    environment = {
        **dict(os.environ),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    valid = subprocess.run(
        command,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0, valid.stderr

    request_path = output / "TECHNICAL/RECOVERY-REQUEST.json"
    request_path.unlink()
    missing = subprocess.run(
        command,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0
