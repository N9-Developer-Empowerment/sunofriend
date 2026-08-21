from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pickle
import zipfile

import pytest

import sunofriend.remix_musicfm_fma_evidence as evidence_module
from sunofriend.remix_musicfm_fma import create_musicfm_fma_admission_plan
from sunofriend.remix_musicfm_fma_evidence import (
    assess_musicfm_fma_readiness,
    inspect_musicfm_fma_static_evidence,
)
from sunofriend.remix_musicfm_fma_runtime import (
    MUSICFM_FMA_RUNTIME_PLAN_SCHEMA,
    create_musicfm_fma_runtime_plan,
    validate_musicfm_fma_runtime_plan,
)
from sunofriend.source_receipt import document_sha256


def _evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict, dict]:
    admission = create_musicfm_fma_admission_plan(
        plan_id="musicfm-fma-admission-001", repository_commit="7" * 40
    )
    checkpoint = tmp_path / evidence_module.CHECKPOINT_FILE
    with zipfile.ZipFile(checkpoint, "w", compression=zipfile.ZIP_STORED) as file:
        file.writestr("archive/data.pkl", pickle.dumps({"state_dict": {}}, protocol=2))
        file.writestr("archive/data/0", b"not read")
    checkpoint_data = checkpoint.read_bytes()
    statistics = tmp_path / evidence_module.STATS_FILE
    statistics.write_text(
        json.dumps({"melspec_2048_mean": 1, "melspec_2048_std": 2}),
        encoding="utf-8",
    )
    config = tmp_path / evidence_module.CONFIG_FILE
    config.write_text(
        json.dumps({"model_type": "wav2vec2-conformer"}), encoding="utf-8"
    )
    monkeypatch.setattr(evidence_module, "CHECKPOINT_BYTES", len(checkpoint_data))
    monkeypatch.setattr(
        evidence_module,
        "CHECKPOINT_SHA256",
        hashlib.sha256(checkpoint_data).hexdigest(),
    )
    monkeypatch.setattr(evidence_module, "STATS_BYTES", statistics.stat().st_size)
    monkeypatch.setattr(evidence_module, "CONFIG_BYTES", config.stat().st_size)
    static = inspect_musicfm_fma_static_evidence(
        admission,
        checkpoint_path=checkpoint,
        statistics_path=statistics,
        conformer_config_path=config,
    )
    readiness = assess_musicfm_fma_readiness(admission, static)
    return admission, static, readiness


def test_runtime_plan_pins_direct_candidates_but_is_not_an_install_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission, static, readiness = _evidence(tmp_path, monkeypatch)
    plan = create_musicfm_fma_runtime_plan(
        admission, static, readiness, repository_commit="6" * 40
    )

    assert plan["schema"] == MUSICFM_FMA_RUNTIME_PLAN_SCHEMA
    assert plan["status"] == "planned_dependency_closure_unresolved_no_install"
    assert plan["isolation"]["reuse_existing_demucs_environment"] is False
    assert plan["isolation"]["fresh_environment_required"] is True
    assert len(plan["source_snapshot"]["files"]) == 7
    assert plan["source_snapshot"]["materialized"] is False
    assert [row["package"] for row in plan["direct_wheel_candidates"]["items"]] == [
        "torch",
        "torchaudio",
        "transformers",
        "einops",
    ]
    assert plan["direct_wheel_candidates"]["observed_total_bytes"] == 3_288_617_517
    assert plan["direct_wheel_candidates"]["complete_transitive_closure"] is False
    assert plan["direct_wheel_candidates"]["installable_lock"] is False
    assert plan["ready_for_dependency_download"] is False
    assert plan["ready_for_installation"] is False
    assert plan["next_gate"]["maximum_total_closure_bytes"] is None
    assert all(value is False for value in plan["authority"].values())
    assert all(value is False for value in plan["effects"].values())
    assert validate_musicfm_fma_runtime_plan(plan, admission, static, readiness) == plan


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["authority"].update(wheel_download_authorized=True),
        lambda row: row["effects"].update(dependency_installed=True),
        lambda row: row["direct_wheel_candidates"].update(installable_lock=True),
        lambda row: row["source_snapshot"]["files"][1].update(bytes=99),
        lambda row: row["required_adapter"].update(
            upstream_from_pretrained_network_call_removed=False
        ),
        lambda row: row["isolation"].update(reuse_existing_demucs_environment=True),
    ],
)
def test_runtime_plan_rejects_rehashed_authority_dependency_or_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate
) -> None:
    admission, static, readiness = _evidence(tmp_path, monkeypatch)
    plan = create_musicfm_fma_runtime_plan(
        admission, static, readiness, repository_commit="6" * 40
    )
    changed = deepcopy(plan)
    mutate(changed)
    changed.pop("document_sha256")
    changed["document_sha256"] = document_sha256(changed)
    with pytest.raises(ValueError, match="evidence or authority"):
        validate_musicfm_fma_runtime_plan(changed, admission, static, readiness)
