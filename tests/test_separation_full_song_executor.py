from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping
import wave

import numpy as np
import pytest
import soundfile

from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_full_song_executor import (
    REPORT_NAME,
    SCHEMA,
    __all__,
    _execute_private_separation_full_song_queue,
)
from sunofriend._separation_full_song_plan import (
    REPORT_NAME as PLAN_REPORT_NAME,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_full_song_stitch import (
    REVIEW_HTML_NAME,
    _stitch_private_separation_full_song,
)
from sunofriend._separation_full_song_review import (
    SCHEMA as REVIEW_RESULT_SCHEMA,
    _resolve_private_separation_full_song_review,
)
from sunofriend._separation_full_song_resource import (
    SCHEMA as RESOURCE_SCHEMA,
    _native_resource_observation,
    _observe_private_separation_full_song_resources,
    _timing_observation,
    _worker_resource_observation,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _plan(tmp_path: Path) -> Path:
    track = tmp_path / "corpus" / "song"
    original = track / "ORIGINAL" / "song.wav"
    original.parent.mkdir(parents=True)
    frames = 18_000
    time = np.arange(frames, dtype=np.float64) / 44_100
    tone = (np.sin(2 * np.pi * 220 * time) * 0.1).astype("float32")
    soundfile.write(original, np.column_stack((tone, tone)), 44_100, subtype="PCM_24")
    corpus = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {
            "name": "Owner",
            "soundcloud_profile": "https://example.test/owner",
        },
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "study",
            "condition": "credit Owner",
            "recorded_on": "2026-08-04",
        },
        "tracks": [
            {
                "id": "song",
                "title": "Song",
                "directory": "song",
                "evaluation_state": "ready_for_excerpt_selection",
            }
        ],
    }
    corpus_path = tmp_path / "corpus" / "corpus.json"
    corpus_path.write_text(json.dumps(corpus) + "\n", encoding="utf-8")
    out = tmp_path / "plan"
    _prepare_private_separation_full_song_plan(
        corpus_path,
        "song",
        out_dir=out,
        maximum_chunk_frames=9_000,
    )
    return out / PLAN_REPORT_NAME


def _runtime_arguments(tmp_path: Path) -> dict[str, Path]:
    values = {
        "repository_root": tmp_path / "repository",
        "runtime_launcher_path": tmp_path / "python",
        "source_root": tmp_path / "source",
        "checkpoint_path": tmp_path / "model.safetensors",
        "companion_root": tmp_path / "companions",
    }
    for key in ("repository_root", "source_root", "companion_root"):
        values[key].mkdir()
    values["runtime_launcher_path"].write_text("runtime", encoding="utf-8")
    values["checkpoint_path"].write_text("checkpoint", encoding="utf-8")
    return values


def _hash_document(document: dict[str, Any], key: str) -> dict[str, Any]:
    payload = dict(document)
    payload.pop(key, None)
    document[key] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return document


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _write_pcm24(path: Path, frames: int) -> dict[str, Any]:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    current = path.parent
    while current.name not in {"ATTEMPTS", ""}:
        current.chmod(0o700)
        current = current.parent
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(b"\0" * frames * 2 * 3)
    path.chmod(0o600)
    contents = path.read_bytes()
    return {
        "bytes": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest(),
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "sample_width_bytes": 3,
            "frames": frames,
        },
    }


def _fake_runner(
    calls: list[int],
    *,
    include_worker_resources: bool = False,
    include_native_resources: bool = False,
):
    def run(**kwargs: Any) -> Mapping[str, Any]:
        report = json.loads(Path(kwargs["authorisation_report_path"]).read_text())
        frames = report["original"]["local_model_input"]["geometry"]["frames"]
        attempt = Path(kwargs["attempt_directory"])
        attempt.mkdir(mode=0o700)
        stems = attempt / "staging/quarantine/STEMS"
        outputs = []
        for role in ("instrumental", "vocals"):
            claim = _write_pcm24(stems / f"{role}.wav", frames)
            outputs.append({"role": role, **claim})
        request_sha = hashlib.sha256(kwargs["run_nonce"].encode("ascii")).hexdigest()
        receipt_payload = {
                "schema": "sunofriend.private-melroformer-native-coordinator.v1",
                "status": "private_native_worker_complete_and_terminal",
                "request_sha256": request_sha,
                "worker_result_sha256": hashlib.sha256(
                    f"worker:{request_sha}".encode("ascii")
                ).hexdigest(),
                "child_result_sha256": hashlib.sha256(
                    f"child:{request_sha}".encode("ascii")
                ).hexdigest(),
                "permissions": {
                    "automatic_selection_permitted": False,
                    "product_route_permitted": False,
                },
            }
        if include_worker_resources:
            resource_payload = {
                "schema": (
                    "sunofriend.private-melroformer-worker-resource-projection.v1"
                ),
                "status": "worker_measurement_projected_not_benchmark",
                "candidate_id": "mlx-melroformer-kim-vocal-2",
                "bindings": {
                    "request_sha256": request_sha,
                    "worker_result_sha256": receipt_payload[
                        "worker_result_sha256"
                    ],
                    "child_result_sha256": receipt_payload["child_result_sha256"],
                },
                "device": "gpu",
                "frames": frames,
                "chunk_count": 1,
                "inference_seconds": 0.75 + len(calls) * 0.25,
                "peak_mlx_allocator_memory_bytes": 2_500_000_000
                + len(calls) * 100_000_000,
                "semantics": {
                    "inference_time_scope": "worker_model_calls_only",
                    "memory_scope": "mlx_allocator_peak_not_process_rss",
                    "benchmark": False,
                },
            }
            receipt_payload["worker_resource_projection"] = _hash_document(
                resource_payload,
                "projection_sha256",
            )
        if include_native_resources:
            native_payload = {
                "schema": (
                    "sunofriend.private-melroformer-native-resource-projection.v1"
                ),
                "status": "exact_reap_process_resources_projected_not_benchmark",
                "bindings": {
                    "request_sha256": request_sha,
                    "worker_result_sha256": receipt_payload[
                        "worker_result_sha256"
                    ],
                    "child_result_sha256": receipt_payload["child_result_sha256"],
                },
                "peak_process_rss_bytes": 3_000_000_000
                + len(calls) * 100_000_000,
                "peak_total_unified_memory_bytes": 3_200_000_000
                + len(calls) * 100_000_000,
                "peak_neural_footprint_bytes": 200_000_000
                + len(calls) * 10_000_000,
                "semantics": {
                    "process_rss": "wait4_ru_maxrss_darwin_bytes",
                    "total_unified_memory": (
                        "proc_pid_rusage_v6_lifetime_max_phys_footprint"
                    ),
                    "scope": "exact_owned_worker_process_lifetime",
                    "pid_retained": False,
                    "benchmark": False,
                },
            }
            receipt_payload["native_process_resource_projection"] = _hash_document(
                native_payload,
                "projection_sha256",
            )
        receipt = _hash_document(receipt_payload, "receipt_sha256")
        evidence = _hash_document(
            {
                "schema": "sunofriend.private-kim-native-attempt-evidence.v1",
                "status": "private_native_attempt_verified_not_selected",
                "bindings": {
                    "request_sha256": request_sha,
                    "terminal_receipt_sha256": receipt["receipt_sha256"],
                    "authorisation_report_sha256": kwargs[
                        "authorisation_report_sha256"
                    ],
                    "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
                    "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
                },
                "outputs": outputs,
                "permissions": {"accepted": False, "product_route_permitted": False},
            },
            "evidence_sha256",
        )
        timing = _hash_document(
            {
                "schema": "sunofriend.private-kim-native-attempt-timing.v1",
                "status": "private_runtime_observation_not_benchmark",
                "evidence_scope": "private_local_coarse_stage_timing_only",
                "bindings": {
                    "request_sha256": request_sha,
                    "terminal_receipt_sha256": receipt["receipt_sha256"],
                    "output_evidence_sha256": evidence["evidence_sha256"],
                },
                "observed_total_through_output_evidence_seconds": 1.5,
                "stage_order": ["input", "native_one_shot"],
                "stage_seconds": {"input": 0.25, "native_one_shot": 1.0},
                "longest_stage": {"name": "native_one_shot", "seconds": 1.0},
                "permissions": {
                    "benchmark_claim": False,
                    "performance_acceptance": False,
                },
            },
            "timing_sha256",
        )
        _write_json(attempt / "native-attempt-receipt.json", receipt)
        _write_json(attempt / "native-attempt-evidence.json", evidence)
        _write_json(attempt / "native-attempt-timing.json", timing)
        calls.append(frames)
        return receipt

    return run


def test_full_song_executor_runs_one_then_resumes_all(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    out = tmp_path / "execution"
    calls: list[int] = []

    first = _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        attempt_runner=_fake_runner(calls),
    )
    assert __all__ == ()
    assert first["schema"] == SCHEMA
    assert first["chunks_executed_this_invocation"] == 1
    assert first["summary"]["verified_chunks"] == 1
    assert first["summary"]["remaining_chunks"] == 1
    assert first["summary"]["stitched_outputs_complete"] is False
    assert all(value is False for value in first["permissions"].values())

    complete = _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner(calls),
    )
    assert complete["chunks_executed_this_invocation"] == 1
    assert complete["summary"]["verified_chunks"] == 2
    assert complete["summary"]["all_worker_runs_complete"] is True
    assert complete["status"] == "private_chunk_execution_complete_not_selected"
    assert calls == [9_000, 9_000]
    persisted = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert persisted["state_sha256"]
    assert stat.S_IMODE((out / REPORT_NAME).stat().st_mode) == 0o600


def test_full_song_executor_preserves_failed_attempt_and_retries(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    out = tmp_path / "execution"

    def fail(**kwargs: Any) -> Mapping[str, Any]:
        Path(kwargs["attempt_directory"]).mkdir(mode=0o700)
        raise RuntimeError("substituted interruption")

    with pytest.raises(RuntimeError, match="substituted interruption"):
        _execute_private_separation_full_song_queue(
            plan,
            out_dir=out,
            **runtime,
            attempt_runner=fail,
        )
    failed_state = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert failed_state["chunks"][0]["attempts"][0]["status"] == "preserved_incomplete"

    calls: list[int] = []
    result = _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        attempt_runner=_fake_runner(calls),
    )
    assert result["chunks"][0]["selected_attempt"] == 2
    assert [item["status"] for item in result["chunks"][0]["attempts"]] == [
        "preserved_incomplete",
        "verified_complete",
    ]


def test_full_song_executor_rejects_changed_completed_output(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    out = tmp_path / "execution"
    calls: list[int] = []
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        attempt_runner=_fake_runner(calls),
    )
    vocal = out / "ATTEMPTS/chunk-0000-attempt-001/staging/quarantine/STEMS/vocals.wav"
    vocal.write_bytes(vocal.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="output binding differs"):
        _execute_private_separation_full_song_queue(
            plan,
            out_dir=out,
            **runtime,
            attempt_runner=_fake_runner(calls),
        )


def test_full_song_executor_is_not_publicly_routed() -> None:
    assert not any("full-song-execute" in command for command in PUBLIC_COMMANDS)
    assert not any("full-song-execute" in command for command in DIRECT_TUI_COMMANDS)


def test_full_song_stitch_preserves_clock_and_prepares_review(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=execution,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner([]),
    )

    result = _stitch_private_separation_full_song(
        plan,
        execution / REPORT_NAME,
        out_dir=tmp_path / "stitch",
    )

    assert result["clock"]["frames"] == 18_000
    assert result["clock"]["boundary_count"] == 1
    assert result["clock"]["crossfade_frames"] == 0
    assert result["readiness"]["stitched_outputs_complete"] is True
    assert result["readiness"]["boundary_listening_complete"] is False
    assert result["reconstruction"]["quality_established"] is False
    assert all(value is False for value in result["permissions"].values())
    review = tmp_path / "stitch/BOUNDARY-REVIEW" / REVIEW_HTML_NAME
    assert review.is_file()
    review_html = review.read_text(encoding="utf-8")
    assert "complete song outputs" in review_html
    assert "every exact chunk join" in review_html
    assert "JSON.stringify(review,null,2)+'\\n'" in review_html
    assert "<audio controls" in review_html
    review_seed = json.loads(
        (tmp_path / "stitch/BOUNDARY-REVIEW/separation_boundary_review.json").read_text()
    )
    assert review_seed["full_song"]["heard_all"] is False
    assert set(review_seed["full_song"]["audio"]) == {
        "source",
        "vocals",
        "instrumental",
        "reconstruction",
    }


def _completed_full_song_review(seed_path: Path, output: Path) -> Path:
    review = json.loads(seed_path.read_text(encoding="utf-8"))
    review["status"] = "reviewed"
    review["full_song"]["heard_all"] = True
    review["full_song"]["ratings"] = {
        "vocals": "noticeable_problems",
        "instrumental": "useful",
        "reconstruction": "useful",
    }
    review["full_song"]["notes"] = "Broad listening note."
    for unit in review["units"]:
        unit["heard_all"] = True
        unit["ratings"] = {
            "vocals": "audible_join",
            "instrumental": "clean",
            "reconstruction": "cannot_tell",
        }
        unit["notes"] = "Exact join note."
    review["summary"]["full_song_reviewed"] = True
    review["summary"]["reviewed_boundaries"] = len(review["units"])
    _write_json(output, review)
    return output


def _stitched_fixture(tmp_path: Path) -> Path:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=execution,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner([]),
    )
    stitch = tmp_path / "stitch"
    _stitch_private_separation_full_song(
        plan,
        execution / REPORT_NAME,
        out_dir=stitch,
    )
    return stitch


def test_full_song_review_resolver_records_exact_human_evidence(tmp_path: Path) -> None:
    stitch = _stitched_fixture(tmp_path)
    reviewed = _completed_full_song_review(
        stitch / "BOUNDARY-REVIEW/separation_boundary_review.json",
        tmp_path / "reviewed.json",
    )

    result = _resolve_private_separation_full_song_review(
        reviewed,
        package_dir=stitch,
        out=tmp_path / "result.json",
    )

    assert result["schema"] == REVIEW_RESULT_SCHEMA
    assert result["status"] == "complete_review_no_activation"
    assert result["readiness"]["full_song_and_boundary_listening_complete"] is True
    assert result["readiness"]["full_song_quality_accepted"] is False
    assert result["boundary_summary"]["audible_join_boundaries_by_role"] == {
        "vocals": [1],
        "instrumental": [],
        "reconstruction": [],
    }
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert result["document_sha256"]
    assert stat.S_IMODE((tmp_path / "result.json").stat().st_mode) == 0o600


def test_full_song_review_resolver_rejects_incomplete_or_changed_review(
    tmp_path: Path,
) -> None:
    stitch = _stitched_fixture(tmp_path)
    seed = stitch / "BOUNDARY-REVIEW/separation_boundary_review.json"
    incomplete = tmp_path / "incomplete.json"
    _write_json(incomplete, json.loads(seed.read_text(encoding="utf-8")))
    with pytest.raises(ValueError, match="incomplete"):
        _resolve_private_separation_full_song_review(
            incomplete,
            package_dir=stitch,
            out=tmp_path / "incomplete-result.json",
        )

    changed = _completed_full_song_review(seed, tmp_path / "changed.json")
    changed_document = json.loads(changed.read_text(encoding="utf-8"))
    changed_document["question"] = "A different question"
    _write_json(changed, changed_document)
    with pytest.raises(ValueError, match="changed immutable evidence"):
        _resolve_private_separation_full_song_review(
            changed,
            package_dir=stitch,
            out=tmp_path / "changed-result.json",
        )


def test_full_song_review_resolver_rejects_changed_audio(tmp_path: Path) -> None:
    stitch = _stitched_fixture(tmp_path)
    reviewed = _completed_full_song_review(
        stitch / "BOUNDARY-REVIEW/separation_boundary_review.json",
        tmp_path / "reviewed.json",
    )
    vocal = stitch / "STEMS/vocals.wav"
    vocal.write_bytes(vocal.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="artifact changed"):
        _resolve_private_separation_full_song_review(
            reviewed,
            package_dir=stitch,
            out=tmp_path / "result.json",
        )


def test_full_song_resource_observation_is_coarse_and_non_accepting(
    tmp_path: Path,
) -> None:
    stitch = _stitched_fixture(tmp_path)
    result = _observe_private_separation_full_song_resources(
        tmp_path / "plan" / PLAN_REPORT_NAME,
        tmp_path / "execution" / REPORT_NAME,
        stitch / "private-separation-full-song-stitch.json",
        out=tmp_path / "resource.json",
    )

    assert result["schema"] == RESOURCE_SCHEMA
    assert result["execution_observation"]["benchmark"] is False
    assert result["execution_observation"]["selected_attempt_count"] == 2
    assert result["execution_observation"]["summed_observed_seconds"] == 3.0
    assert result["coverage"]["coarse_monotonic_timing_observed"] is True
    assert result["coverage"]["worker_model_inference_time_observed"] is False
    assert result["coverage"]["peak_mlx_allocator_memory_observed"] is False
    assert result["coverage"]["peak_process_rss_observed"] is False
    assert result["coverage"]["peak_accelerator_memory_observed"] is False
    assert result["readiness"]["resource_envelope_accepted"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert stat.S_IMODE((tmp_path / "resource.json").stat().st_mode) == 0o600


def test_full_song_resource_observation_retains_worker_inference_and_mlx_memory(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=execution,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner([], include_worker_resources=True),
    )
    stitch = tmp_path / "stitch"
    _stitch_private_separation_full_song(
        plan,
        execution / REPORT_NAME,
        out_dir=stitch,
    )

    result = _observe_private_separation_full_song_resources(
        plan,
        execution / REPORT_NAME,
        stitch / "private-separation-full-song-stitch.json",
        out=tmp_path / "resource.json",
    )

    resources = result["execution_observation"]["worker_resources"]
    assert resources["complete_for_selected_attempts"] is True
    assert resources["observed_attempt_count"] == 2
    assert resources["missing_attempt_count"] == 0
    assert resources["summed_inference_seconds"] == 1.75
    assert resources["maximum_peak_mlx_allocator_memory_bytes"] == 2_600_000_000
    assert resources["peak_process_rss_observed"] is False
    assert result["coverage"]["worker_model_inference_time_observed"] is True
    assert result["coverage"]["peak_mlx_allocator_memory_observed"] is True
    assert result["coverage"]["peak_accelerator_memory_observed"] is False
    assert result["coverage"]["peak_process_rss_observed"] is False
    assert result["readiness"]["resource_envelope_accepted"] is False


def test_full_song_resource_observation_retains_exact_reap_process_memory(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=execution,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner(
            [],
            include_worker_resources=True,
            include_native_resources=True,
        ),
    )
    stitch = tmp_path / "stitch"
    _stitch_private_separation_full_song(
        plan,
        execution / REPORT_NAME,
        out_dir=stitch,
    )

    result = _observe_private_separation_full_song_resources(
        plan,
        execution / REPORT_NAME,
        stitch / "private-separation-full-song-stitch.json",
        out=tmp_path / "resource.json",
    )

    resources = result["execution_observation"]["native_process_resources"]
    assert resources["complete_for_selected_attempts"] is True
    assert resources["observed_attempt_count"] == 2
    assert resources["missing_attempt_count"] == 0
    assert resources["maximum_peak_process_rss_bytes"] == 3_100_000_000
    assert resources["maximum_peak_total_unified_memory_bytes"] == 3_300_000_000
    assert resources["maximum_peak_neural_footprint_bytes"] == 210_000_000
    assert resources["pid_retained"] is False
    assert result["coverage"]["peak_process_rss_observed"] is True
    assert result["coverage"]["peak_total_unified_memory_observed"] is True
    assert result["readiness"]["resource_envelope_accepted"] is False


def test_worker_resource_observation_rejects_unbound_projection() -> None:
    receipt = {
        "request_sha256": "1" * 64,
        "worker_result_sha256": "2" * 64,
        "child_result_sha256": "3" * 64,
    }
    payload = {
        "schema": "sunofriend.private-melroformer-worker-resource-projection.v1",
        "status": "worker_measurement_projected_not_benchmark",
        "candidate_id": "mlx-melroformer-kim-vocal-2",
        "bindings": {
            "request_sha256": "1" * 64,
            "worker_result_sha256": "4" * 64,
            "child_result_sha256": "3" * 64,
        },
        "device": "gpu",
        "frames": 661_500,
        "chunk_count": 1,
        "inference_seconds": 8.0,
        "peak_mlx_allocator_memory_bytes": 2_500_000_000,
        "semantics": {
            "inference_time_scope": "worker_model_calls_only",
            "memory_scope": "mlx_allocator_peak_not_process_rss",
            "benchmark": False,
        },
    }
    projection = _hash_document(payload, "projection_sha256")

    with pytest.raises(ValueError, match="resource projection differs"):
        _worker_resource_observation(0, receipt, projection)


def test_native_resource_observation_rejects_unbound_projection() -> None:
    receipt = {
        "request_sha256": "1" * 64,
        "worker_result_sha256": "2" * 64,
        "child_result_sha256": "3" * 64,
    }
    payload = {
        "schema": "sunofriend.private-melroformer-native-resource-projection.v1",
        "status": "exact_reap_process_resources_projected_not_benchmark",
        "bindings": {
            "request_sha256": "1" * 64,
            "worker_result_sha256": "4" * 64,
            "child_result_sha256": "3" * 64,
        },
        "peak_process_rss_bytes": 3_000_000_000,
        "peak_total_unified_memory_bytes": 3_200_000_000,
        "peak_neural_footprint_bytes": 200_000_000,
        "semantics": {
            "process_rss": "wait4_ru_maxrss_darwin_bytes",
            "total_unified_memory": (
                "proc_pid_rusage_v6_lifetime_max_phys_footprint"
            ),
            "scope": "exact_owned_worker_process_lifetime",
            "pid_retained": False,
            "benchmark": False,
        },
    }
    projection = _hash_document(payload, "projection_sha256")

    with pytest.raises(ValueError, match="native resource projection differs"):
        _native_resource_observation(0, receipt, projection)


def test_full_song_resource_observation_rejects_changed_timing_semantics(
    tmp_path: Path,
) -> None:
    timing = {
        "schema": "sunofriend.private-kim-native-attempt-timing.v1",
        "status": "claimed_benchmark",
        "evidence_scope": "private_local_coarse_stage_timing_only",
        "observed_total_through_output_evidence_seconds": 1.5,
        "stage_order": ["input", "native_one_shot"],
        "stage_seconds": {"input": 0.25, "native_one_shot": 1.0},
        "longest_stage": {"name": "native_one_shot", "seconds": 1.0},
        "permissions": {"benchmark_claim": False},
    }
    with pytest.raises(ValueError, match="timing observation differs"):
        _timing_observation(0, timing)
