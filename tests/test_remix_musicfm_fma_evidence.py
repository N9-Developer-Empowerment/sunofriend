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
    inspect_musicfm_fma_static_evidence,
    validate_musicfm_fma_static_evidence,
    verify_musicfm_fma_static_evidence_round_trip,
)
from sunofriend.source_receipt import document_sha256


def _plan() -> dict:
    return create_musicfm_fma_admission_plan(
        plan_id="musicfm-fma-admission-001", repository_commit="8" * 40
    )


def _fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    checkpoint = root / evidence_module.CHECKPOINT_FILE
    with zipfile.ZipFile(checkpoint, mode="w", compression=zipfile.ZIP_STORED) as file:
        file.writestr(
            "archive/data.pkl",
            pickle.dumps({"state_dict": {"weight": [1, 2, 3]}}, protocol=2),
        )
        file.writestr("archive/data/0", b"tensor bytes are deliberately not read")
    checkpoint_data = checkpoint.read_bytes()
    statistics = root / evidence_module.STATS_FILE
    statistics.write_text(
        json.dumps({"melspec_2048_mean": 1.0, "melspec_2048_std": 2.0}),
        encoding="utf-8",
    )
    config = root / evidence_module.CONFIG_FILE
    config.write_text(
        json.dumps(
            {
                "model_type": "wav2vec2-conformer",
                "hidden_size": 1024,
                "num_hidden_layers": 24,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evidence_module, "CHECKPOINT_BYTES", len(checkpoint_data))
    monkeypatch.setattr(
        evidence_module,
        "CHECKPOINT_SHA256",
        hashlib.sha256(checkpoint_data).hexdigest(),
    )
    monkeypatch.setattr(evidence_module, "STATS_BYTES", statistics.stat().st_size)
    monkeypatch.setattr(evidence_module, "CONFIG_BYTES", config.stat().st_size)
    return checkpoint, statistics, config


def test_static_evidence_is_reproducible_and_never_loads_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint, statistics, config = _fixture(tmp_path, monkeypatch)
    evidence = inspect_musicfm_fma_static_evidence(
        _plan(),
        checkpoint_path=checkpoint,
        statistics_path=statistics,
        conformer_config_path=config,
    )

    assert evidence["status"] == "artifacts_verified_statically_not_loaded"
    assert evidence["checkpoint_archive"]["non_pickle_member_payloads_read"] is False
    assert evidence["checkpoint_pickle"]["opcode_count"] > 0
    assert evidence["effects"]["checkpoint_deserialized"] is False
    assert evidence["effects"]["torch_load_called"] is False
    assert evidence["effects"]["model_imported"] is False
    assert evidence["effects"]["audio_reads"] == 0
    assert validate_musicfm_fma_static_evidence(evidence, _plan()) == evidence
    verified = verify_musicfm_fma_static_evidence_round_trip(
        tmp_path, _plan(), evidence
    )
    assert verified["status"] == "verified_static_evidence_round_trip"
    assert verified["model_loaded"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["authority"].update(model_load_authorized=True),
        lambda row: row["effects"].update(torch_load_called=True),
        lambda row: row["binding"].update(provider_id="substitute"),
        lambda row: row["artifacts"]["checkpoint"].update(sha256="0" * 64),
    ],
)
def test_static_evidence_rejects_rehashed_authority_or_identity_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate
) -> None:
    checkpoint, statistics, config = _fixture(tmp_path, monkeypatch)
    evidence = inspect_musicfm_fma_static_evidence(
        _plan(),
        checkpoint_path=checkpoint,
        statistics_path=statistics,
        conformer_config_path=config,
    )
    changed = deepcopy(evidence)
    mutate(changed)
    changed.pop("document_sha256", None)
    changed["document_sha256"] = document_sha256(changed)
    with pytest.raises(ValueError):
        validate_musicfm_fma_static_evidence(changed, _plan())


def test_round_trip_rejects_extra_file_and_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint, statistics, config = _fixture(tmp_path, monkeypatch)
    evidence = inspect_musicfm_fma_static_evidence(
        _plan(),
        checkpoint_path=checkpoint,
        statistics_path=statistics,
        conformer_config_path=config,
    )
    (tmp_path / "extra.txt").write_text("not admitted", encoding="utf-8")
    with pytest.raises(ValueError, match="roster"):
        verify_musicfm_fma_static_evidence_round_trip(tmp_path, _plan(), evidence)

    (tmp_path / "extra.txt").unlink()
    statistics.unlink()
    statistics.symlink_to(config)
    with pytest.raises(ValueError):
        verify_musicfm_fma_static_evidence_round_trip(tmp_path, _plan(), evidence)
