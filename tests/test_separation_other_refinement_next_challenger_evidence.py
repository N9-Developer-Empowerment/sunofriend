from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import zipfile

import pytest

import sunofriend.separation_other_refinement_next_challenger_evidence as evidence_module
from sunofriend.separation_other_refinement_next_challenger_evidence import (
    inspect_mega53_artifact_evidence,
    validate_mega53_artifact_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def _checkpoint(path: Path, payload: object) -> bytes:
    pickle_data = pickle.dumps(payload, protocol=2)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("archive/data.pkl", pickle_data)
        archive.writestr("archive/data/0", b"tensor bytes are not inspected")
    return path.read_bytes()


def _config(path: Path) -> bytes:
    contents = b"instruments: [synth, wind, guitar]\nmodel: static-test\n"
    path.write_bytes(contents)
    return contents


def _patch_expected(
    monkeypatch: pytest.MonkeyPatch, checkpoint: bytes, config: bytes
) -> None:
    monkeypatch.setattr(evidence_module, "CHECKPOINT_BYTES", len(checkpoint))
    monkeypatch.setattr(
        evidence_module, "CHECKPOINT_SHA256", hashlib.sha256(checkpoint).hexdigest()
    )
    monkeypatch.setattr(evidence_module, "CONFIG_BYTES", len(config))
    monkeypatch.setattr(
        evidence_module, "CONFIG_SHA256", hashlib.sha256(config).hexdigest()
    )


def test_static_evidence_hashes_both_artifacts_without_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint_path = tmp_path / evidence_module.CHECKPOINT_FILE
    config_path = tmp_path / evidence_module.CONFIG_FILE
    checkpoint = _checkpoint(checkpoint_path, {"state_dict": {"weight": [1, 2, 3]}})
    config = _config(config_path)
    _patch_expected(monkeypatch, checkpoint, config)

    result = inspect_mega53_artifact_evidence(
        checkpoint_path,
        config_path,
        expected_checkpoint_bytes=len(checkpoint),
        expected_checkpoint_sha256=hashlib.sha256(checkpoint).hexdigest(),
        expected_config_bytes=len(config),
        expected_config_sha256=hashlib.sha256(config).hexdigest(),
    )

    assert result["status"] == "artifacts_verified_statically_not_loaded"
    assert result["checkpoint_archive"]["member_count"] == 2
    assert result["checkpoint_archive"]["non_pickle_member_payloads_read"] is False
    assert result["checkpoint_pickle"]["opcode_count"] > 0
    assert result["config_structure"]["yaml_constructed"] is False
    assert result["effects"]["checkpoint_deserialized"] is False
    assert result["effects"]["torch_load_called"] is False
    assert result["effects"]["model_imported"] is False
    assert result["effects"]["inference_runs"] == 0
    assert validate_mega53_artifact_evidence(result) == result


def test_static_evidence_rejects_wrong_checkpoint_hash(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / evidence_module.CHECKPOINT_FILE
    config_path = tmp_path / evidence_module.CONFIG_FILE
    checkpoint = _checkpoint(checkpoint_path, {"state_dict": {}})
    config = _config(config_path)

    with pytest.raises(ValueError, match="checkpoint SHA-256 differs"):
        inspect_mega53_artifact_evidence(
            checkpoint_path,
            config_path,
            expected_checkpoint_bytes=len(checkpoint),
            expected_checkpoint_sha256="0" * 64,
            expected_config_bytes=len(config),
            expected_config_sha256=hashlib.sha256(config).hexdigest(),
        )


def test_static_evidence_validation_rejects_authority_expansion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint_path = tmp_path / evidence_module.CHECKPOINT_FILE
    config_path = tmp_path / evidence_module.CONFIG_FILE
    checkpoint = _checkpoint(checkpoint_path, {"state_dict": {}})
    config = _config(config_path)
    _patch_expected(monkeypatch, checkpoint, config)
    result = inspect_mega53_artifact_evidence(
        checkpoint_path,
        config_path,
        expected_checkpoint_bytes=len(checkpoint),
        expected_checkpoint_sha256=hashlib.sha256(checkpoint).hexdigest(),
        expected_config_bytes=len(config),
        expected_config_sha256=hashlib.sha256(config).hexdigest(),
    )
    changed = json.loads(json.dumps(result))
    changed["effects"]["model_constructed"] = True

    with pytest.raises(ValueError, match="hash differs"):
        validate_mega53_artifact_evidence(changed)


def test_setup_is_capped_non_loading_and_network_denied() -> None:
    setup = (
        ROOT
        / "scripts"
        / "setup-separation-other-refinement-next-challenger-macos.sh"
    ).read_text(encoding="utf-8")
    artifact_route = setup[
        setup.index('if [ "$ACCEPTED_PROVISIONAL_TERMS" != true ]') :
    ]

    assert "MAX_DOWNLOAD_BYTES=1610612736" in setup
    assert "EXPECTED_TOTAL_BYTES=1368924071" in setup
    assert "ulimit -f 3145728" in setup
    assert '--max-filesize "$MAX_DOWNLOAD_BYTES"' in setup
    assert "(deny network*)" in setup
    assert "--evidence-only" in setup
    assert "--accept-provisional-local-noncommercial-terms" in setup
    assert " -m pip" not in artifact_route
    assert "torch.load" not in artifact_route
    assert "--install-runtime" not in artifact_route
