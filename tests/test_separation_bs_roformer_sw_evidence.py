from __future__ import annotations

import hashlib
from pathlib import Path
import pickle
import zipfile

import pytest

import sunofriend.separation_bs_roformer_sw_evidence as evidence_module
from sunofriend.separation_bs_roformer_sw_evidence import (
    inspect_sw_artifact_evidence,
    validate_sw_artifact_evidence,
)


def _checkpoint(path: Path) -> bytes:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "archive/data.pkl", pickle.dumps({"state_dict": {}}, protocol=2)
        )
        archive.writestr("archive/data/0", b"not read")
    return path.read_bytes()


def test_sw_static_evidence_is_hash_bound_and_non_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint_path = tmp_path / "BS-Rofo-SW-Fixed.ckpt"
    config_path = tmp_path / "BS-Rofo-SW-Fixed.yaml"
    checkpoint = _checkpoint(checkpoint_path)
    config = b"training:\n  instruments: [bass, drums, other, vocals, guitar, piano]\n"
    config_path.write_bytes(config)
    patched_checkpoint = {
        "file": checkpoint_path.name,
        "bytes": len(checkpoint),
        "sha256": hashlib.sha256(checkpoint).hexdigest(),
    }
    patched_config = {
        "file": config_path.name,
        "bytes": len(config),
        "sha256": hashlib.sha256(config).hexdigest(),
    }
    monkeypatch.setattr(evidence_module, "SW_CHECKPOINT", patched_checkpoint)
    monkeypatch.setattr(evidence_module, "SW_CONFIG", patched_config)
    result = inspect_sw_artifact_evidence(
        checkpoint_path,
        config_path,
        expected_checkpoint_bytes=len(checkpoint),
        expected_checkpoint_sha256=patched_checkpoint["sha256"],
        expected_config_bytes=len(config),
        expected_config_sha256=patched_config["sha256"],
    )
    assert result["checkpoint_archive"]["non_pickle_member_payloads_read"] is False
    assert result["effects"]["torch_load_called"] is False
    assert validate_sw_artifact_evidence(result) == result


def test_sw_static_evidence_rejects_hash_mismatch(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "BS-Rofo-SW-Fixed.ckpt"
    config_path = tmp_path / "BS-Rofo-SW-Fixed.yaml"
    checkpoint = _checkpoint(checkpoint_path)
    config_path.write_bytes(b"config")
    with pytest.raises(ValueError, match="checkpoint SHA-256 differs"):
        inspect_sw_artifact_evidence(
            checkpoint_path,
            config_path,
            expected_checkpoint_bytes=len(checkpoint),
            expected_checkpoint_sha256="0" * 64,
            expected_config_bytes=6,
            expected_config_sha256=hashlib.sha256(b"config").hexdigest(),
        )
