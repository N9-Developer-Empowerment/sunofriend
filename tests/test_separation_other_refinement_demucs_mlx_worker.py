from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sunofriend.separation_demucs_mlx_worker import PCM24_SCALE
from sunofriend.separation_other_refinement_demucs_mlx_run import (
    _document_sha256,
    _render_review,
    execute_installed_other_refinement,
    plan_installed_other_refinement,
)
from sunofriend.separation_other_refinement import (
    create_other_refinement_synthetic_fixture,
)
from sunofriend.separation_other_refinement_demucs_mlx_worker import (
    persist_target_and_residual,
)


def test_target_plus_residual_reconstructs_exact_pcm24(tmp_path: Path) -> None:
    frames = 512
    source = np.column_stack(
        (
            np.linspace(-0.4, 0.4, frames, dtype=np.float32),
            np.linspace(0.3, -0.3, frames, dtype=np.float32),
        )
    )
    target = source * np.float32(0.2)

    result = persist_target_and_residual(
        source=source,
        target=target,
        target_id="guitar",
        destination=tmp_path,
        np=np,
    )

    assert result["additive_accounting"]["maximum_absolute_error_lsb"] == 0
    assert result["additive_accounting"]["passed"] is True
    assert result["target_diagnostics"]["used_for_automatic_musical_selection"] is False
    assert (tmp_path / "PARENT/other.wav").is_file()
    assert (tmp_path / "STEMS/guitar.wav").is_file()
    assert (tmp_path / "STEMS/other-residual.wav").is_file()


def test_unrepresentable_exact_residual_is_an_objective_failure(tmp_path: Path) -> None:
    source = np.full((32, 2), -0.99, dtype=np.float32)
    target = np.full((32, 2), 0.99, dtype=np.float32)

    with pytest.raises(ValueError, match="residual is outside PCM24"):
        persist_target_and_residual(
            source=source,
            target=target,
            target_id="keys",
            destination=tmp_path,
            np=np,
        )


def test_installed_plan_binds_sealed_scnet_parent_without_execution(
    tmp_path: Path,
) -> None:
    from sunofriend.separation_demucs_mlx_worker import write_pcm24_integers

    parent = tmp_path / "parent"
    other = parent / "STEMS/other.wav"
    values = np.rint(np.full((441, 2), 0.1, dtype=np.float64) * PCM24_SCALE).astype(
        np.int32
    )
    identity = write_pcm24_integers(other, values, np=np)
    report = {
        "schema": "sunofriend.experimental-separation-alpha.v1",
        "separator": {
            "scope_id": "core-four-stems-v1",
            "profile_id": "scnet-large-musdb-release-v1",
            "profile_status": "public_opt_in",
            "worker": {"outputs": {"other": identity}},
        },
        "rights": {
            "category": "owned",
            "confirmed_before_execution": True,
        },
    }
    report["document_sha256"] = _document_sha256(report)
    technical = parent / "TECHNICAL"
    technical.mkdir()
    (technical / "separation-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    plan = plan_installed_other_refinement(
        parent,
        target_id="keys",
        output=tmp_path / "candidate",
    )

    assert plan["status"] == "ready_plan_only_no_effects"
    assert plan["rights_category"] == "owned"
    assert plan["contract"]["request"]["target_id"] == "keys"
    assert plan["contract"]["parent"]["audio_sha256"] == identity["sha256"]
    assert not any(plan["effects"].values())


def test_execution_refuses_a_known_historically_blocked_plan(tmp_path: Path) -> None:
    fixture = create_other_refinement_synthetic_fixture(tmp_path / "fixture")
    contract = json.loads(Path(fixture["plan"]).read_text(encoding="utf-8"))
    contract["blockers"] = [
        "The first target-separation candidate is pinned, but dependency and checkpoint installation still require explicit approval.",
        "The one allowed in-memory fractional-segment remediation has not passed installed-artifact compatibility under network denial.",
        "No candidate has passed offline model construction, resource and output-contract gates.",
        "Studio can describe and compare future candidates, but no refinement runner is exposed.",
    ]
    seed = dict(contract)
    seed.pop("document_sha256")
    seed.pop("plan_id")
    contract["plan_id"] = "sha256:" + _document_sha256(seed)
    contract["document_sha256"] = _document_sha256(contract)

    with pytest.raises(RuntimeError, match="historically blocked plan"):
        execute_installed_other_refinement(
            {
                "schema": "sunofriend.other-refinement-installed-run-plan.v1",
                "contract": contract,
                "output": str(tmp_path / "must-not-exist"),
            },
            confirm_rights=True,
        )

    assert not (tmp_path / "must-not-exist").exists()


def test_review_uses_existing_relative_audio_and_private_feedback_fields(
    tmp_path: Path,
) -> None:
    fixture = create_other_refinement_synthetic_fixture(tmp_path / "fixture")
    result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))

    html = _render_review(result)

    assert 'src="../PARENT/other.wav"' in html
    assert 'src="../STEMS/guitar.wav"' in html
    assert 'src="../STEMS/other-residual.wav"' in html
    assert "Download listening JSON" in html
    assert "Copy text-only feedback" in html
    assert "missing_content" in html
    assert "downstream_midi" in html
    assert "uploaded automatically" in html
