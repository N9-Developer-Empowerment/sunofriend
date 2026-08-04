from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile

from sunofriend._separation_candidate_followup_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    _build_candidates,
    _verify_candidates,
    _worker_adapter_plan,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _read_pcm24_snapshot,
)


SAMPLE_RATE = 44_100


def test_worker_adapter_excludes_control_only_role() -> None:
    plan = _plan()

    adapter = _worker_adapter_plan(plan)

    assert len(adapter["windows"]) == 2
    assert adapter["windows"][1]["patch_target_roles"] == ["instrumental"]
    assert all(
        window["source_start_frame"]
        != next(
            item["unshifted_source_start_frame"]
            for item in plan["windows"]
            if item["window_index"] == window["window_index"]
        )
        for window in adapter["windows"]
    )


def test_builds_two_unranked_variants_and_exactly_restores_v2(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    plan = _plan()
    inputs = _inputs(tmp_path)
    worker_root, worker_state = _workers(tmp_path)
    root = tmp_path / "candidates"
    root.mkdir(mode=0o700)

    document = _build_candidates(
        root,
        plan=plan,
        plan_snapshot={"sha256": "a" * 64},
        inputs=inputs,
        worker_root=worker_root,
        worker_state=worker_state,
    )
    verified = _verify_candidates(
        root,
        plan=plan,
        plan_snapshot={"sha256": "a" * 64},
        inputs=inputs,
        worker_root=worker_root,
        worker_state=worker_state,
    )

    assert verified == document
    assert (root / CANDIDATE_REPORT_NAME).is_file()
    assert document["summary"]["candidate_variant_count"] == 2
    assert document["summary"]["automatic_winner_selected"] is False
    assert all(item["selected"] is False for item in document["variants"])
    standard, _ = soundfile.read(
        root / "shifted-context-standard-edge/vocals.wav",
        dtype="int32",
        always_2d=True,
    )
    preserved, _ = soundfile.read(
        root / "preserved-centre-extended-edge/vocals.wav",
        dtype="int32",
        always_2d=True,
    )
    base, _ = soundfile.read(
        inputs["candidate_paths"]["vocals"], dtype="int32", always_2d=True
    )
    v2, _ = soundfile.read(
        inputs["v2_paths"]["vocals"], dtype="int32", always_2d=True
    )
    np.testing.assert_array_equal(standard[60:68], v2[60:68])
    np.testing.assert_array_equal(preserved[60:68], v2[60:68])
    np.testing.assert_array_equal(standard[:20], base[:20])
    np.testing.assert_array_equal(preserved[:20], base[:20])
    assert np.count_nonzero(standard[20:28] != preserved[20:28]) > 0
    assert document["readiness"]["candidate_review_complete"] is False
    assert document["readiness"]["publication_ready"] is False


def _plan() -> dict[str, Any]:
    return {
        "clock": {"sample_rate": SAMPLE_RATE, "channels": 2, "frames": 100},
        "protocol": {
            "candidate_variants": [
                {
                    "variant_id": "shifted-context-standard-edge",
                    "reinference_source": "shifted_context_worker",
                    "failed_edge_source": "shifted_context_worker",
                    "failed_edge_blend_frames": 2,
                },
                {
                    "variant_id": "preserved-centre-extended-edge",
                    "reinference_source": "shifted_context_worker",
                    "failed_edge_source": "exact_followup_candidate_patch",
                    "failed_edge_blend_frames": 3,
                },
            ]
        },
        "windows": [
            {
                "window_index": 1,
                "boundary_index": 1,
                "source_start_frame": 14,
                "source_end_frame": 34,
                "unshifted_source_start_frame": 12,
                "role_actions": {
                    "vocals": {
                        "action": "edge_aware_reinference_and_blend_search",
                        "model_call_required": True,
                        "patch_start_frame": 20,
                        "patch_end_frame": 28,
                        "edge_blend_frames": 2,
                    }
                },
            },
            {
                "window_index": 2,
                "boundary_index": 2,
                "source_start_frame": 54,
                "source_end_frame": 74,
                "unshifted_source_start_frame": 52,
                "role_actions": {
                    "instrumental": {
                        "action": "reinfer_role_boundary",
                        "model_call_required": True,
                        "patch_start_frame": 60,
                        "patch_end_frame": 68,
                        "edge_blend_frames": 2,
                    },
                    "vocals": {
                        "action": "revert_patch_to_v2_control",
                        "model_call_required": False,
                        "patch_start_frame": 60,
                        "patch_end_frame": 68,
                        "edge_blend_frames": 2,
                    },
                },
            },
        ],
        "summary": {"planned_model_call_count": 2},
        "document_sha256": "b" * 64,
    }


def _write_audio(path: Path, samples: np.ndarray) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    soundfile.write(
        path,
        samples.astype("float64") / 2_147_483_648.0,
        SAMPLE_RATE,
        subtype="PCM_24",
    )
    path.chmod(0o600)
    snapshot = _read_pcm24_snapshot(
        path, None, expected_frames=len(samples), label="test follow-up input"
    )
    return {
        "path": path.name,
        "sha256": snapshot["sha256"],
        "bytes": snapshot["bytes"],
        "geometry": {
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": len(samples),
            "sample_width_bytes": 3,
        },
        "pcm24_int32_sequence_sha256": snapshot[
            "pcm24_int32_sequence_sha256"
        ],
    }


def _inputs(tmp_path: Path) -> dict[str, Any]:
    base_root = tmp_path / "base"
    v2_root = tmp_path / "v2"
    base_vocals = np.zeros((100, 2), dtype="int32")
    base_vocals[20:28] = 268_435_456
    base_vocals[60:68] = 134_217_728
    base_instrumental = np.zeros((100, 2), dtype="int32")
    base_instrumental[60:68] = -134_217_728
    zeros = np.zeros((100, 2), dtype="int32")
    base_paths = {
        "vocals": base_root / "vocals.wav",
        "instrumental": base_root / "instrumental.wav",
    }
    v2_paths = {
        "vocals": v2_root / "vocals.wav",
        "instrumental": v2_root / "instrumental.wav",
    }
    base_claims = {
        role: _write_audio(base_paths[role], samples)
        for role, samples in (
            ("vocals", base_vocals),
            ("instrumental", base_instrumental),
        )
    }
    v2_claims = {
        role: _write_audio(v2_paths[role], zeros) for role in v2_paths
    }
    return {
        "candidate": {
            "clock": {"frames": 100},
            "artifacts": base_claims,
        },
        "v2": {"clock": {"frames": 100}, "artifacts": v2_claims},
        "candidate_paths": base_paths,
        "v2_paths": v2_paths,
        "candidate_snapshot": {"sha256": "c" * 64},
        "v2_snapshot": {"sha256": "d" * 64},
    }


def _workers(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "workers"
    windows: list[dict[str, Any]] = []
    for index, value in ((1, 536_870_912), (2, -536_870_912)):
        attempt = root / f"attempt-{index}/staging/quarantine/STEMS"
        samples = np.full((20, 2), value, dtype="int32")
        outputs: dict[str, Any] = {}
        for role in ("vocals", "instrumental"):
            path = attempt / f"{role}.wav"
            claim = _write_audio(path, samples)
            outputs[role] = {
                "sha256": claim["sha256"],
                "bytes": claim["bytes"],
                "frames": 20,
            }
        windows.append(
            {
                "window_index": index,
                "selected_attempt": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "verified_complete",
                        "path": f"attempt-{index}",
                        "outputs": outputs,
                    }
                ],
            }
        )
    root.chmod(0o700)
    return root, {"state_sha256": "e" * 64, "windows": windows}
