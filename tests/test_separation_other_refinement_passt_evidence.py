from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import zipfile

import pytest

import sunofriend.separation_other_refinement_passt_evidence as evidence_module
from sunofriend.separation_other_refinement_passt_evidence import (
    inspect_passt_checkpoint_evidence,
    validate_passt_checkpoint_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def _checkpoint(path: Path, payload: object) -> bytes:
    pickle_data = pickle.dumps(payload, protocol=2)
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("archive/data.pkl", pickle_data)
        archive.writestr("archive/data/0", b"tensor bytes are not inspected")
    return path.read_bytes()


def test_passt_evidence_hashes_without_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "passt.pt"
    contents = _checkpoint(checkpoint, {"state_dict": {"weight": [1, 2, 3]}})
    monkeypatch.setattr(
        evidence_module, "EXPECTED_PASST_CHECKPOINT_BYTES", len(contents)
    )

    result = inspect_passt_checkpoint_evidence(
        checkpoint,
        expected_bytes=len(contents),
    )

    assert result["checkpoint"]["sha256"] == hashlib.sha256(contents).hexdigest()
    assert result["archive"]["member_count"] == 2
    assert result["archive"]["non_pickle_member_payloads_read"] is False
    assert result["pickle"]["opcode_count"] > 0
    assert result["effects"]["checkpoint_deserialized"] is False
    assert result["effects"]["model_imported"] is False
    assert result["effects"]["inference_runs"] == 0
    assert validate_passt_checkpoint_evidence(result) == result


def test_passt_evidence_rejects_wrong_release_size(tmp_path: Path) -> None:
    checkpoint = tmp_path / "passt.pt"
    contents = _checkpoint(checkpoint, {"state_dict": {}})

    with pytest.raises(ValueError, match="byte count differs"):
        inspect_passt_checkpoint_evidence(
            checkpoint,
            expected_bytes=len(contents) + 1,
        )


def test_passt_evidence_validation_rejects_authority_expansion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "passt.pt"
    contents = _checkpoint(checkpoint, {"state_dict": {}})
    monkeypatch.setattr(
        evidence_module, "EXPECTED_PASST_CHECKPOINT_BYTES", len(contents)
    )
    result = inspect_passt_checkpoint_evidence(
        checkpoint,
        expected_bytes=len(contents),
    )
    changed = json.loads(json.dumps(result))
    changed["effects"]["model_constructed"] = True

    with pytest.raises(ValueError, match="hash differs"):
        validate_passt_checkpoint_evidence(changed)


def test_passt_setup_is_capped_evidence_only_and_network_denied() -> None:
    setup = (
        ROOT
        / "scripts"
        / "setup-separation-other-refinement-query-runtime-macos.sh"
    ).read_text(encoding="utf-8")

    assert "MAX_BYTES=393216000" in setup
    assert "ulimit -f 768000" in setup
    assert '--max-filesize "$MAX_BYTES"' in setup
    assert "(deny network*)" in setup
    assert "--passt-evidence-only" in setup
    passt_evidence_route = setup[setup.index('if [ "$ACCEPTED_TERMS" != true ]') :]
    assert "pip install" not in passt_evidence_route
    assert "torch.load" not in passt_evidence_route
