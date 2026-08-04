from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile

from sunofriend._separation_authorised_excerpt import _sha256
from sunofriend._separation_candidate_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    _build_candidate,
    _verify_candidate,
    _worker_plan_document,
)


SAMPLE_RATE = 44_100


def test_worker_adapter_binds_review_plan_without_claiming_candidate_assembly() -> None:
    plan, plan_snapshot, context, _, _ = _candidate_fixture()

    document = _worker_plan_document(
        plan, plan_snapshot=plan_snapshot, context=context
    )

    assert document["bindings"]["candidate_remediation_plan_sha256"] == "a" * 64
    assert document["summary"] == {
        "planned_model_call_count": 2,
        "candidate_assembly_delegated": False,
        "worker_only_adapter": True,
    }
    assert document["effects"] and all(
        value is False for value in document["effects"].values()
    )
    assert all(value is False for value in document["permissions"].values())


def test_candidate_builder_changes_only_named_v2_regions(tmp_path: Path) -> None:
    plan, plan_snapshot, context, worker_state, worker_audio = _candidate_fixture()
    worker_root = tmp_path / "workers"
    for index, roles in worker_audio.items():
        attempt = worker_root / f"attempt-{index}" / "staging/quarantine/STEMS"
        attempt.mkdir(parents=True, mode=0o700)
        outputs: dict[str, Any] = {}
        for role, samples in roles.items():
            path = attempt / f"{role}.wav"
            soundfile.write(
                path,
                samples.astype("float64") / 2_147_483_648.0,
                SAMPLE_RATE,
                subtype="PCM_24",
            )
            path.chmod(0o600)
            outputs[role] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "frames": len(samples),
            }
        worker_state["windows"][index - 1]["attempts"][0]["outputs"] = outputs
    worker_root.chmod(0o700)
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir(mode=0o700)

    document = _build_candidate(
        candidate_root,
        plan=plan,
        plan_snapshot=plan_snapshot,
        context=context,
        worker_root=worker_root,
        worker_state=worker_state,
    )
    verified = _verify_candidate(
        candidate_root,
        plan=plan,
        plan_snapshot=plan_snapshot,
        context=context,
        worker_root=worker_root,
        worker_state=worker_state,
    )

    assert verified == document
    assert (candidate_root / CANDIDATE_REPORT_NAME).is_file()
    assert document["summary"]["patched_boundary_role_pair_count"] == 3
    assert document["summary"]["v2_candidate_hashes_unchanged"] is True
    vocals, _ = soundfile.read(
        candidate_root / "vocals.wav", dtype="int32", always_2d=True
    )
    instrumental, _ = soundfile.read(
        candidate_root / "instrumental.wav", dtype="int32", always_2d=True
    )
    base_vocals = context["v2_audio"]["vocals"]["samples"]
    base_instrumental = context["v2_audio"]["instrumental"]["samples"]
    vocal_mask = np.ones(len(vocals), dtype=bool)
    vocal_mask[20:28] = False
    vocal_mask[60:68] = False
    instrumental_mask = np.ones(len(instrumental), dtype=bool)
    instrumental_mask[60:68] = False
    np.testing.assert_array_equal(vocals[vocal_mask], base_vocals[vocal_mask])
    np.testing.assert_array_equal(
        instrumental[instrumental_mask], base_instrumental[instrumental_mask]
    )
    assert np.count_nonzero(vocals[20:28] != base_vocals[20:28]) > 0
    assert np.count_nonzero(
        instrumental[60:68] != base_instrumental[60:68]
    ) > 0
    assert document["readiness"]["candidate_review_complete"] is False
    assert document["readiness"]["publication_ready"] is False


def _candidate_fixture() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[int, dict[str, np.ndarray]],
]:
    frames = 100
    base_vocals = np.zeros((frames, 2), dtype="int32")
    base_instrumental = np.zeros((frames, 2), dtype="int32")
    plan = {
        "clock": {
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": frames,
        },
        "protocol": {
            "edge_blend_frames": 2,
            "patch_duration_frames": 8,
        },
        "windows": [
            {
                "window_index": 1,
                "boundary_index": 1,
                "source_start_frame": 14,
                "source_end_frame": 34,
                "patch_start_frame": 20,
                "patch_end_frame": 28,
                "patch_target_roles": ["vocals"],
            },
            {
                "window_index": 2,
                "boundary_index": 2,
                "source_start_frame": 54,
                "source_end_frame": 74,
                "patch_start_frame": 60,
                "patch_end_frame": 68,
                "patch_target_roles": ["vocals", "instrumental"],
            },
        ],
        "document_sha256": "b" * 64,
    }
    plan_snapshot = {"sha256": "a" * 64}
    context = {
        "stitch_snapshot": {"sha256": "c" * 64},
        "stitch": {
            "document_sha256": "d" * 64,
            "bindings": {
                "plan_document_sha256": "e" * 64,
                "execution_state_sha256": "f" * 64,
            },
            "artifacts": {
                role: {"sha256": character * 64}
                for role, character in (
                    ("source", "1"),
                    ("vocals", "2"),
                    ("instrumental", "3"),
                    ("reconstruction", "4"),
                )
            },
        },
        "v2_snapshot": {"sha256": "5" * 64},
        "v2_report": {"document_sha256": "6" * 64},
        "v2_audio": {
            "vocals": {"samples": base_vocals, "sha256": "7" * 64},
            "instrumental": {
                "samples": base_instrumental,
                "sha256": "8" * 64,
            },
        },
    }
    worker_state = {
        "state_sha256": "9" * 64,
        "windows": [
            {
                "window_index": index,
                "selected_attempt": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "verified_complete",
                        "path": f"attempt-{index}",
                        "outputs": {},
                    }
                ],
            }
            for index in (1, 2)
        ],
    }
    first_vocal = np.full((20, 2), 536_870_912, dtype="int32")
    second_vocal = np.full((20, 2), 268_435_456, dtype="int32")
    second_instrumental = np.full((20, 2), -268_435_456, dtype="int32")
    worker_audio = {
        1: {"vocals": first_vocal, "instrumental": first_vocal},
        2: {"vocals": second_vocal, "instrumental": second_instrumental},
    }
    return plan, plan_snapshot, context, worker_state, worker_audio
