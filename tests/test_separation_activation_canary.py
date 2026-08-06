from __future__ import annotations

import json
from pathlib import Path
import wave
from unittest.mock import patch

import numpy as np
import pytest

from sunofriend.separation_activation_canary import (
    BASELINE_REMEDIATION_EXHAUSTED,
    CANARY_SCHEMA,
    FALLBACK_FAILURE_ID,
    FALLBACK_REMEDIATION_EXHAUSTED,
    execute_synthetic_canary,
    plan_synthetic_canary,
)
from sunofriend.separation_core_four_fixture import (
    FIXTURE_POLICY_ID,
    FRAMES,
    ROLES,
    SAMPLE_RATE,
    create_core_four_synthetic_fixture,
)
from sunofriend.separation_demucs_mlx_worker import decode_pcm24
from sunofriend.separation_review import render_review_html
from sunofriend.separation_scopes import FULL_STEM_SCOPE_ID, separation_scope


def _read_pcm24(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as reader:
        assert reader.getnchannels() == 2
        assert reader.getsampwidth() == 3
        assert reader.getframerate() == SAMPLE_RATE
        assert reader.getnframes() == FRAMES
        return decode_pcm24(reader.readframes(FRAMES), np=np)


def test_active_synthetic_fixture_is_exact_and_copyright_safe(tmp_path: Path) -> None:
    fixture = create_core_four_synthetic_fixture(tmp_path / "fixture")

    assert fixture["policy_id"] == FIXTURE_POLICY_ID
    assert fixture["roles"] == list(ROLES)
    assert fixture["all_roles_active"] is True
    assert "no recordings, samples, lyrics or third-party audio" in fixture[
        "source_kind"
    ]
    source = _read_pcm24(Path(fixture["source_path"]))
    reconstructed = np.zeros_like(source, dtype=np.float64)
    for role in ROLES:
        value = _read_pcm24(Path(fixture["ground_truth_paths"][role]))
        assert np.any(value)
        reconstructed += value
    error_lsb = np.max(np.abs((source - reconstructed) * (1 << 23)))
    assert error_lsb <= 1
    persisted = json.loads(Path(fixture["manifest"]).read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == fixture["document_sha256"]


def test_synthetic_canary_plan_is_read_only_and_changes_no_profile(
    tmp_path: Path,
) -> None:
    doctor = {
        "ready": True,
        "checks": {
            "machine_class": {
                "verified_16_gib_class": False,
                "warning": "accessible but unverified",
            }
        },
    }
    with patch(
        "sunofriend.separation_activation_canary.separation_doctor",
        return_value=doctor,
    ):
        plan = plan_synthetic_canary(tmp_path / "fresh")

    assert plan["schema"] == CANARY_SCHEMA
    assert BASELINE_REMEDIATION_EXHAUSTED is True
    assert FALLBACK_REMEDIATION_EXHAUSTED is True
    assert plan["status"] == "blocked_objective_remediation_exhausted"
    assert plan["execution_enabled"] is False
    assert plan["execution_confirmation"] is None
    assert plan["profile_id"] == "demucs-infer-htdemucs-fallback-v1"
    assert plan["objective_failure"]["failure_id"] == FALLBACK_FAILURE_ID
    assert plan["objective_failure"]["remediation_cycles"] == 1
    assert plan["objective_failure"]["maximum_remediation_cycles"] == 1
    assert plan["objective_failure"]["published_output"] is False
    assert plan["objective_failure"]["human_listen_reached"] is False
    assert plan["objective_failure"]["observed_native_segment_type"] == "Fraction"
    assert plan["profile_status_change"] is False
    assert plan["public_access_change"] is False
    assert plan["effects_if_executed"]["network"] == []
    assert not (tmp_path / "fresh").exists()


def test_synthetic_canary_execution_is_disabled_after_fallback_failure(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="activation retries are disabled"):
        execute_synthetic_canary(
            tmp_path / "fresh",
            confirm_synthetic=True,
        )

    assert not (tmp_path / "fresh").exists()


def test_activation_review_adds_ground_truth_without_a_quality_threshold() -> None:
    scope = separation_scope(FULL_STEM_SCOPE_ID)
    truth = {
        role: {
            "path": f"GROUND-TRUTH/{role}.wav",
            "bytes": 1,
            "sha256": role.ljust(64, "0"),
        }
        for role in ROLES
    }
    report = {
        "source": {"name": "core-four-synthetic-demo.wav"},
        "separator": {
            "scope_id": FULL_STEM_SCOPE_ID,
            "profile_id": "demucs-mlx-htdemucs-v1",
            "role_details": [role.to_dict() for role in scope.roles],
            "worker": {
                "activation_ground_truth": {
                    "roles": truth,
                    "automatic_quality_threshold": None,
                }
            },
        },
        "feedback": {"public_report_url": "https://example.test"},
        "document_sha256": "a" * 64,
    }

    page = render_review_html(report)

    assert "I heard all 10 tracks" in page
    assert "Synthetic ground truth: Vocals" in page
    assert "../GROUND-TRUTH/other.wav" in page
    assert "not a required quality target" in page
