from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

import numpy as np
import pytest

from sunofriend._separation_melroformer_control_comparison import (
    _compare_private_melroformer_vocals,
)
from sunofriend._separation_melroformer_real_bridge import (
    _PrivateMelRoFormerHandle,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_compares_candidate_with_four_sealed_controls_without_ranking(
    tmp_path: Path,
) -> None:
    report, report_sha256, source, candidate, authorisation = _fixture(tmp_path)

    evidence = _compare_private_melroformer_vocals(
        _handle(),
        source=source,
        candidate_vocals=candidate,
        source_authorisation=authorisation,
        control_report_path=report,
        expected_control_report_sha256=report_sha256,
    )

    assert evidence["status"] == "descriptive_review_required_no_winner"
    assert tuple(evidence["controls"]) == (
        "local-htdemucs",
        "moises",
        "suno-a",
        "suno-b",
    )
    assert evidence["candidate_vs_controls"]["local-htdemucs"][
        "evidence_similarity"
    ] == pytest.approx(1.0, abs=1e-5)
    assert evidence["interpretation"]["automatic_ranking_performed"] is False
    assert evidence["interpretation"]["winner_selected"] is False
    assert evidence["effects"]["filesystem_written"] is False
    assert "path" not in repr(evidence).lower()


def test_rejects_control_report_source_or_permission_drift(tmp_path: Path) -> None:
    report, _report_sha256, source, candidate, authorisation = _fixture(tmp_path)
    document = json.loads(report.read_text())
    document["source_excerpt"]["track_id"] = "different"
    report_sha256 = _write_report(report, document)
    with pytest.raises(ValueError, match="binding differs"):
        _compare_private_melroformer_vocals(
            _handle(),
            source=source,
            candidate_vocals=candidate,
            source_authorisation=authorisation,
            control_report_path=report,
            expected_control_report_sha256=report_sha256,
        )

    document["source_excerpt"]["track_id"] = "owned-example"
    document["permissions"]["public_result"] = True
    report_sha256 = _write_report(report, document)
    with pytest.raises(ValueError, match="product permissions differ"):
        _compare_private_melroformer_vocals(
            _handle(),
            source=source,
            candidate_vocals=candidate,
            source_authorisation=authorisation,
            control_report_path=report,
            expected_control_report_sha256=report_sha256,
        )


def test_private_comparison_has_no_public_route() -> None:
    assert "private-melroformer-control-comparison" not in PUBLIC_COMMANDS
    assert "private-melroformer-control-comparison" not in DIRECT_TUI_COMMANDS


def _fixture(
    root: Path,
) -> tuple[Path, str, np.ndarray, np.ndarray, dict[str, object]]:
    timeline = np.arange(4_096, dtype=np.float32) / np.float32(44_100.0)
    mono = (0.25 * np.sin(2 * np.pi * 220 * timeline)).astype(np.float32)
    candidate = np.stack([mono, mono * np.float32(0.95)], axis=1)
    source = np.clip(candidate * np.float32(1.5), -1.0, 1.0).astype(np.float32)
    artifacts: dict[str, dict[str, object]] = {}
    controls = {
        "local-htdemucs": candidate,
        "moises": candidate * np.float32(0.9),
        "suno-a": candidate * np.float32(0.8),
        "suno-b": candidate * np.float32(0.7),
    }
    for identity, audio in controls.items():
        relative = f"ROLE-GROUPS/{identity}/vocals.wav"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_pcm24(path, audio)
        artifacts[relative] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    source_report_sha256 = "1" * 64
    document = {
        "schema": "sunofriend.private-authorised-role-mapping.v1",
        "status": "complete_review_required",
        "evidence_scope": "private_development_only",
        "source_excerpt": {
            "track_id": "owned-example",
            "report_sha256": source_report_sha256,
            "start_seconds": 10.0,
            "end_seconds": 10.0 + 4_096 / 44_100,
        },
        "policy": {
            "common_sample_rate": 44_100,
            "roles": ["bass", "drums", "other", "vocals"],
            "similarity_is_descriptive_not_acceptance": True,
            "provider_names_propose_but_do_not_prove_groups": True,
        },
        "permissions": {
            "accepted": False,
            "automatic_promotion": False,
            "automatic_selection": False,
            "production_eligible": False,
            "public_result": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "artifacts": artifacts,
    }
    report = root / "authorised-role-mapping.json"
    report_sha256 = _write_report(report, document)
    authorisation: dict[str, object] = {
        "track_id": "owned-example",
        "report_sha256": source_report_sha256,
        "source_start_seconds": 10.0,
        "source_end_seconds": 10.0 + 4_096 / 44_100,
    }
    return report, report_sha256, source, candidate, authorisation


def _handle() -> _PrivateMelRoFormerHandle:
    return _PrivateMelRoFormerHandle(
        model=None,
        mx=None,
        np=np,
        device="gpu",
        config=None,
        sanitized_weight_keys=(),
        expected_model_keys=(),
        dropped_raw_weight_keys=(),
        evidence={},
    )


def _write_pcm24(path: Path, values: np.ndarray) -> None:
    quantized = np.clip(np.rint(values * 8_388_608.0), -8_388_608, 8_388_607)
    unsigned = quantized.astype(np.int32) & 0xFFFFFF
    packed = np.empty((unsigned.size, 3), dtype=np.uint8)
    flat = unsigned.reshape(-1)
    packed[:, 0] = flat & 0xFF
    packed[:, 1] = (flat >> 8) & 0xFF
    packed[:, 2] = (flat >> 16) & 0xFF
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(packed.tobytes())


def _write_report(path: Path, document: dict[str, object]) -> str:
    document.pop("document_sha256", None)
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    document["document_sha256"] = hashlib.sha256(payload).hexdigest()
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()
