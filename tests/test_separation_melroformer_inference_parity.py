from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from sunofriend._separation_melroformer_conversion_parity import _document_sha256
from sunofriend._separation_melroformer_inference_parity import (
    EVIDENCE_SHA256,
    PARITY_FRAMES,
    RUNTIME_VERSIONS,
    _build_inference_parity_report,
    _verify_tracked_inference_parity_evidence,
    _verify_runtime_versions,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _report(*, original_error: float, rounded_error: float) -> dict[str, object]:
    rng = np.random.default_rng(7)
    audio = rng.normal(0.0, 0.1, size=(PARITY_FRAMES, 2)).astype(np.float32)
    original = audio * np.float32(0.7)
    rounded = original + np.float32(original_error)
    converted = rounded + np.float32(rounded_error)
    return _build_inference_parity_report(
        audio=audio,
        original=original,
        rounded=rounded,
        converted=converted,
        runtime_versions=RUNTIME_VERSIONS,
        authorisation={
            "track_id": "fixture",
            "source_start_seconds": 0.0,
            "source_window_seconds": 8.0,
            "report_sha256": "1" * 64,
            "source_pcm24_sha256": "2" * 64,
        },
        timings={
            "pytorch_original_fp32_seconds": 1.0,
            "pytorch_bf16_roundtrip_seconds": 1.0,
            "mlx_bf16_seconds": 1.0,
            "mlx_peak_memory_bytes": 1,
        },
    )


def test_distinguishes_bf16_runtime_parity_from_source_precision_delta() -> None:
    result = _report(original_error=0.005, rounded_error=0.000001)

    assert result["status"] == (
        "verified_bf16_runtime_parity_source_precision_delta_recorded"
    )
    assert result["claims"][
        "converted_bf16_runtime_output_parity_above_threshold"
    ] is True
    assert result["claims"][
        "original_fp32_source_to_converted_mlx_output_above_threshold"
    ] is False
    assert result["claims"]["upstream_reported_66_08_db_independently_reproduced"] is False
    assert result["document_sha256"] == _document_sha256(result)
    assert all(value is False for value in result["permissions"].values())


def test_reports_below_threshold_and_rejects_bad_geometry() -> None:
    result = _report(original_error=0.005, rounded_error=0.01)
    assert result["status"] == "bf16_runtime_parity_below_threshold"

    with pytest.raises(ValueError, match="geometry differs"):
        _build_inference_parity_report(
            audio=np.zeros((100, 2), dtype=np.float32),
            original=np.zeros((100, 2), dtype=np.float32),
            rounded=np.zeros((100, 2), dtype=np.float32),
            converted=np.zeros((100, 2), dtype=np.float32),
            runtime_versions=RUNTIME_VERSIONS,
            authorisation={},
            timings={},
        )


def test_runtime_version_check_is_exact() -> None:
    with patch(
        "importlib.metadata.version",
        side_effect=lambda name: RUNTIME_VERSIONS[name],
    ):
        assert _verify_runtime_versions() == RUNTIME_VERSIONS
    with patch("importlib.metadata.version", return_value="0"):
        with pytest.raises(RuntimeError, match="runtime differs"):
            _verify_runtime_versions()


def test_private_inference_parity_has_no_product_route_or_answer_key_access() -> None:
    assert "private-melroformer-inference-parity" not in PUBLIC_COMMANDS
    assert "private-melroformer-inference-parity" not in DIRECT_TUI_COMMANDS
    source = Path(__file__).resolve().parents[1] / "src" / "sunofriend"
    implementation = (
        source / "_separation_melroformer_inference_parity.py"
    ).read_text()
    assert "midi_ab_answer_key" not in implementation
    assert "/Users/" not in implementation
    assert "winner_selected\": False" in implementation
    assert json.dumps(RUNTIME_VERSIONS)


def test_tracked_real_observation_records_both_parity_results() -> None:
    repository = Path(__file__).resolve().parents[1]
    evidence = _verify_tracked_inference_parity_evidence(repository)

    assert evidence["document_sha256"] == _document_sha256(evidence)
    comparisons = evidence["comparisons"]
    assert (
        comparisons["pytorch_bf16_roundtrip_vs_mlx_published_bf16"]["sdr_db"]
        > 100.0
    )
    assert (
        comparisons["pytorch_original_fp32_vs_mlx_published_bf16"]["sdr_db"]
        < 40.0
    )
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in json.dumps(evidence)
    assert len(EVIDENCE_SHA256) == 64
