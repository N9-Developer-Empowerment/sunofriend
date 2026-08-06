from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sunofriend.separation_scnet_canary import (
    CANARY_SCHEMA,
    execute_scnet_canary,
    plan_scnet_canary,
)
from sunofriend.separation_scnet_worker import (
    OVERLAP,
    SEGMENT_FRAMES,
    SHIFT_FRAMES,
    split_offsets,
    validate_destination_staging,
)


def test_scnet_split_contract_is_fixed_and_covers_tail() -> None:
    assert OVERLAP == 0.25
    assert SEGMENT_FRAMES == 485_100
    assert SHIFT_FRAMES == 22_050
    assert split_offsets(1) == (0,)
    offsets = split_offsets(2_646_000 + SHIFT_FRAMES)
    assert offsets[0] == 0
    assert all(
        right - left == int(SEGMENT_FRAMES * 0.75)
        for left, right in zip(offsets, offsets[1:])
    )
    assert offsets[-1] < 2_646_000 + SHIFT_FRAMES
    assert offsets[-1] + SEGMENT_FRAMES >= 2_646_000 + SHIFT_FRAMES


def test_scnet_canary_plan_is_read_only_and_has_no_song_rights_gate(
    tmp_path: Path,
) -> None:
    model_root = tmp_path / "profile"
    model_root.mkdir()
    output = tmp_path / "output"

    plan = plan_scnet_canary(output, model_root=model_root)

    assert plan["schema"] == CANARY_SCHEMA
    assert plan["status"] == "ready"
    assert plan["profile_status_before"] == "public_opt_in"
    assert plan["profile_status_change"] is False
    assert plan["public_access_change"] is False
    assert plan["approvals"]["synthetic_inference_confirmation_required"] is True
    assert plan["approvals"]["personal_song_rights_confirmation_required"] is False
    assert plan["effects_if_executed"]["network"] == []
    assert plan["effects_if_executed"]["uploads"] == []
    assert not output.exists()


def test_scnet_worker_accepts_only_exact_coordinator_temp_input(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "staging"
    canonical = destination / "TEMP/source-44100-stereo-pcm24.wav"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"canonical")

    validate_destination_staging(canonical, destination)

    (canonical.parent / "extra.wav").write_bytes(b"unexpected")
    with pytest.raises(FileExistsError, match="TEMP input contract"):
        validate_destination_staging(canonical, destination)


def test_scnet_canary_requires_explicit_synthetic_confirmation(
    tmp_path: Path,
) -> None:
    with pytest.raises(PermissionError, match="confirm-synthetic"):
        execute_scnet_canary(
            tmp_path / "output",
            confirm_synthetic=False,
            model_root=tmp_path / "profile",
        )


def test_scnet_canary_rejects_missing_recorded_setup_approval(
    tmp_path: Path,
) -> None:
    model_root = tmp_path / "profile"
    (model_root / "runtime/bin").mkdir(parents=True)
    (model_root / "runtime/bin/python").write_text("", encoding="utf-8")
    (model_root / "INSTALLATION.json").write_text(
        json.dumps(
            {
                "profile_id": "scnet-large-musdb-release-v1",
                "model_terms_accepted": False,
                "checkpoint_use_accepted": True,
            }
        ),
        encoding="utf-8",
    )
    (model_root / "COMPATIBILITY.json").write_text(
        json.dumps(
            {"status": "passed", "compatibility": {"remediation_cycles": 1}}
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="approval or compatibility"):
        execute_scnet_canary(
            tmp_path / "output",
            confirm_synthetic=True,
            model_root=model_root,
        )


def test_scnet_canary_failure_preserves_partial_evidence(tmp_path: Path) -> None:
    model_root = tmp_path / "profile"
    (model_root / "runtime/bin").mkdir(parents=True)
    (model_root / "runtime/bin/python").write_text("", encoding="utf-8")
    (model_root / "INSTALLATION.json").write_text(
        json.dumps(
            {
                "profile_id": "scnet-large-musdb-release-v1",
                "model_terms_accepted": True,
                "checkpoint_use_accepted": True,
            }
        ),
        encoding="utf-8",
    )
    (model_root / "COMPATIBILITY.json").write_text(
        json.dumps(
            {"status": "passed", "compatibility": {"remediation_cycles": 1}}
        ),
        encoding="utf-8",
    )
    completed = type(
        "Completed", (), {"returncode": 2, "stderr": "objective failure", "stdout": ""}
    )()
    output = tmp_path / "output"
    with patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="objective failure"):
            execute_scnet_canary(
                output,
                confirm_synthetic=True,
                model_root=model_root,
            )

    failures = list(tmp_path.glob("output.failed.*.evidence"))
    assert len(failures) == 1
    assert (failures[0] / "GROUND-TRUTH/vocals.wav").is_file()
    assert not output.exists()
