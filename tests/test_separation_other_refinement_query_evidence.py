from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import zipfile

import pytest

import sunofriend.separation_other_refinement_query_evidence as evidence_module
from sunofriend.separation_other_refinement_query_evidence import (
    inspect_query_checkpoint_evidence,
    validate_query_checkpoint_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def _checkpoint(path: Path, payload: object) -> bytes:
    pickle_data = pickle.dumps(payload, protocol=2)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("archive/data.pkl", pickle_data)
        archive.writestr("archive/data/0", b"tensor bytes are not inspected")
    return path.read_bytes()


def test_static_evidence_hashes_and_parses_without_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "checkpoint.ckpt"
    contents = _checkpoint(checkpoint, {"state_dict": {"weight": [1, 2, 3]}})
    monkeypatch.setattr(evidence_module, "EXPECTED_CHECKPOINT_BYTES", len(contents))
    monkeypatch.setattr(
        evidence_module,
        "EXPECTED_CHECKPOINT_MD5",
        hashlib.md5(contents, usedforsecurity=False).hexdigest(),
    )

    result = inspect_query_checkpoint_evidence(
        checkpoint,
        expected_bytes=len(contents),
        expected_md5=hashlib.md5(contents, usedforsecurity=False).hexdigest(),
    )

    assert result["status"] == "statically_inspected_not_loaded"
    assert result["checkpoint"]["sha256"] == hashlib.sha256(contents).hexdigest()
    assert result["archive"]["member_count"] == 2
    assert result["archive"]["non_pickle_member_payloads_read"] is False
    assert result["pickle"]["opcode_count"] > 0
    assert result["effects"]["checkpoint_deserialized"] is False
    assert result["effects"]["model_imported"] is False
    assert result["effects"]["inference_runs"] == 0
    assert validate_query_checkpoint_evidence(result) == result


def test_static_evidence_rejects_wrong_published_hash(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.ckpt"
    contents = _checkpoint(checkpoint, {"state_dict": {}})

    with pytest.raises(ValueError, match="MD5 differs"):
        inspect_query_checkpoint_evidence(
            checkpoint,
            expected_bytes=len(contents),
            expected_md5="0" * 32,
        )


def test_static_evidence_validation_rejects_authority_expansion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "checkpoint.ckpt"
    contents = _checkpoint(checkpoint, {"state_dict": {}})
    md5 = hashlib.md5(contents, usedforsecurity=False).hexdigest()
    monkeypatch.setattr(evidence_module, "EXPECTED_CHECKPOINT_BYTES", len(contents))
    monkeypatch.setattr(evidence_module, "EXPECTED_CHECKPOINT_MD5", md5)
    result = inspect_query_checkpoint_evidence(
        checkpoint, expected_bytes=len(contents), expected_md5=md5
    )
    changed = json.loads(json.dumps(result))
    changed["effects"]["model_constructed"] = True

    with pytest.raises(ValueError, match="hash differs"):
        validate_query_checkpoint_evidence(changed)


def test_setup_is_capped_evidence_only_and_inspection_is_network_denied() -> None:
    setup = (
        ROOT
        / "scripts"
        / "setup-separation-other-refinement-query-challenger-macos.sh"
    ).read_text(encoding="utf-8")

    assert "MAX_BYTES=734003200" in setup
    assert "ulimit -f 1433600" in setup
    assert "--max-filesize \"$MAX_BYTES\"" in setup
    assert "(deny network*)" in setup
    assert "--evidence-only" in setup
    assert "pip install" not in setup
    assert "torch.load" not in setup
    assert "--install" not in setup
