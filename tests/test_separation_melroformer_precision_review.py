from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from sunofriend._separation_melroformer_inference_parity import (
    PARITY_FRAMES,
    SAMPLE_RATE,
)
from sunofriend._separation_melroformer_precision_review import (
    RESULT_SCHEMA,
    REVIEW_SCHEMA,
    _create_private_melroformer_precision_review,
    _resolve_private_melroformer_precision_review,
)


def _arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    timeline = np.arange(PARITY_FRAMES, dtype=np.float32) / np.float32(SAMPLE_RATE)
    source = np.stack(
        [
            0.18 * np.sin(2 * np.pi * 220 * timeline),
            0.18 * np.sin(2 * np.pi * 220 * timeline + 0.1),
        ],
        axis=1,
    ).astype(np.float32)
    original = np.stack(
        [
            0.11 * np.sin(2 * np.pi * 330 * timeline),
            0.11 * np.sin(2 * np.pi * 330 * timeline + 0.05),
        ],
        axis=1,
    ).astype(np.float32)
    published = (
        original * np.float32(0.92)
        + np.float32(0.002) * np.sin(2 * np.pi * 990 * timeline)[:, None]
    ).astype(np.float32)
    return source, original, published


def _create(root: Path) -> dict[str, object]:
    source, original, published = _arrays()
    with patch(
        "sunofriend._separation_melroformer_precision_review.secrets.token_bytes",
        return_value=b"p" * 32,
    ):
        return _create_private_melroformer_precision_review(
            source=source,
            original_fp32=original,
            published_bf16=published,
            out_dir=root / "review",
            authorisation={
                "track_id": "authorised-test",
                "source_start_seconds": 12.0,
                "source_window_seconds": 8.0,
                "report_sha256": "a" * 64,
                "source_pcm24_sha256": "b" * 64,
            },
            runtime_versions={"torch": "test", "mlx": "test"},
            timings={"pytorch_original_fp32_seconds": 1.0, "mlx_bf16_seconds": 1.0},
            runtime_parity_sdr_db=117.0,
        )


def test_creates_owner_only_blind_equal_level_review_and_resolves(
    tmp_path: Path,
) -> None:
    result = _create(tmp_path)
    package = Path(str(result["out_dir"]))
    seed = json.loads(Path(str(result["seed"])).read_text())
    answer = json.loads(Path(str(result["answer_key"])).read_text())
    html = Path(str(result["html"])).read_text()

    assert result["schema"] == REVIEW_SCHEMA
    assert seed["status"] == "unreviewed"
    assert seed["summary"] == {"unit_count": 1, "reviewed_unit_count": 0}
    assert seed["policy"]["candidate_level_method"] == (
        "pairwise-fixed-window-rms-attenuation-plus-common-peak-guard-v1"
    )
    unit = seed["units"][0]
    assert (
        abs(unit["candidate_a"]["rms_dbfs"] - unit["candidate_b"]["rms_dbfs"]) <= 0.05
    )
    assert "original FP32 PyTorch checkpoint" not in html
    assert "published BF16 MLX checkpoint" not in html
    assert (
        answer["mapping"]["candidate_a"]["precision"]
        != answer["mapping"]["candidate_b"]["precision"]
    )
    assert package.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o077 == 0 for path in package.rglob("*"))

    reviewed = json.loads(json.dumps(seed))
    reviewed["status"] = "reviewed"
    reviewed["summary"]["reviewed_unit_count"] = 1
    reviewed["units"][0]["heard"] = {
        "source": True,
        "candidate_a": True,
        "candidate_b": True,
    }
    reviewed["units"][0]["choice"] = "candidate_a"
    reviewed["units"][0]["notes"] = "Clearer consonants."
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(json.dumps(reviewed))
    resolution = _resolve_private_melroformer_precision_review(
        reviewed_path,
        package_dir=package,
        out=tmp_path / "resolved.json",
    )

    assert resolution["schema"] == RESULT_SCHEMA
    assert resolution["choice"] == "candidate_a"
    assert (
        resolution["resolved_precision"]
        == answer["mapping"]["candidate_a"]["precision"]
    )
    assert resolution["decision_required_after_review"] is True
    assert not any(bool(value) for value in resolution["effects"].values())


def test_rejects_changed_review_audio_and_incomplete_export(tmp_path: Path) -> None:
    result = _create(tmp_path)
    seed = json.loads(Path(str(result["seed"])).read_text())
    reviewed_path = tmp_path / "incomplete.json"
    reviewed_path.write_text(json.dumps(seed))
    with pytest.raises(ValueError, match="incomplete"):
        _resolve_private_melroformer_precision_review(
            reviewed_path,
            package_dir=result["out_dir"],
            out=tmp_path / "must-not-exist.json",
        )

    candidate = Path(str(result["out_dir"])) / seed["units"][0]["candidate_a"]["audio"]
    candidate.write_bytes(candidate.read_bytes() + b"changed")
    reviewed = json.loads(json.dumps(seed))
    reviewed["status"] = "reviewed"
    reviewed["summary"]["reviewed_unit_count"] = 1
    reviewed["units"][0]["heard"] = {
        "source": True,
        "candidate_a": True,
        "candidate_b": True,
    }
    reviewed["units"][0]["choice"] = "equivalent"
    reviewed_path.write_text(json.dumps(reviewed))
    with pytest.raises(ValueError, match="audio changed"):
        _resolve_private_melroformer_precision_review(
            reviewed_path,
            package_dir=result["out_dir"],
            out=tmp_path / "still-must-not-exist.json",
        )


def test_requires_fresh_exact_eight_second_geometry(tmp_path: Path) -> None:
    source, original, published = _arrays()
    with pytest.raises(ValueError, match="eight-second"):
        _create_private_melroformer_precision_review(
            source=source[:-1],
            original_fp32=original[:-1],
            published_bf16=published[:-1],
            out_dir=tmp_path / "review",
            authorisation={"source_window_seconds": 8.0},
            runtime_versions={},
            timings={},
            runtime_parity_sdr_db=117.0,
        )
