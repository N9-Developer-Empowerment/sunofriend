from __future__ import annotations

import hashlib
import io
import json
import os
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from sunofriend._separation_melroformer_real_bridge import (
    MAXIMUM_EXCERPT_FRAMES,
    NOMINAL_CHUNK_FRAMES,
    NOMINAL_HOP_FRAMES,
    _PrivateMelRoFormerHandle,
    _chunk_crossfade_weights,
    _load_private_authorised_excerpt,
    _load_private_authorised_excerpt_pcm24,
    _load_private_melroformer_model,
    _plan_excerpt_chunks,
    _transform_checkpoint_keys,
    _validate_weight_inventory,
    _verified_checkpoint_descriptor_stream,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


@dataclass(frozen=True)
class _Array:
    shape: tuple[int, ...]
    dtype: str = "mlx.core.bfloat16"


def test_reproduces_every_audited_sanitizer_key_transformation() -> None:
    transformed, dropped = _transform_checkpoint_keys(
        (
            "layers.0.time.to_qkv.weight",
            "layers.0.time.to_out.0.weight",
            "layers.0.time.norm.gamma",
            "layers.0.time.rotary_embed.freqs",
            "mask_estimators.0.to_freqs.4.0.2.bias",
            "plain.weight",
        )
    )

    assert transformed == (
        "layers.0.time.norm.weight",
        "layers.0.time.to_k.weight",
        "layers.0.time.to_out.weight",
        "layers.0.time.to_q.weight",
        "layers.0.time.to_v.weight",
        "mask_estimators.0.to_freqs.4.1.0.bias",
        "plain.weight",
    )
    assert dropped == ("layers.0.time.rotary_embed.freqs",)


def test_accepts_only_complete_key_shape_and_dtype_coverage() -> None:
    raw = {
        "layer.to_qkv.weight": _Array((6, 2)),
        "layer.rotary_embed.freqs": _Array((2,)),
        "norm.gamma": _Array((2,)),
    }
    sanitized = {
        "layer.to_q.weight": _Array((2, 2)),
        "layer.to_k.weight": _Array((2, 2)),
        "layer.to_v.weight": _Array((2, 2)),
        "norm.weight": _Array((2,)),
    }
    expected = dict(sanitized)

    result = _validate_weight_inventory(raw=raw, sanitized=sanitized, expected=expected)

    assert result["raw_checkpoint_key_count"] == 3
    assert result["sanitized_key_count"] == 4
    assert result["expected_model_key_count"] == 4
    assert result["dropped_raw_weight_keys"] == ["layer.rotary_embed.freqs"]
    assert result["complete"] is True


def test_rejects_sanitizer_drift_shape_drift_and_dtype_drift() -> None:
    raw = {"plain.weight": _Array((2,))}
    expected = {"plain.weight": _Array((2,))}
    with pytest.raises(ValueError, match="sanitizer mapping"):
        _validate_weight_inventory(
            raw=raw,
            sanitized={"other.weight": _Array((2,))},
            expected=expected,
        )
    with pytest.raises(ValueError, match="tensor shapes"):
        _validate_weight_inventory(
            raw=raw,
            sanitized={"plain.weight": _Array((3,))},
            expected=expected,
        )
    with pytest.raises(ValueError, match="runtime dtype"):
        _validate_weight_inventory(
            raw={"plain.weight": _Array((2,), dtype="mlx.core.float32")},
            sanitized={"plain.weight": _Array((2,), dtype="mlx.core.float32")},
            expected=expected,
        )


def test_private_bridge_has_no_public_cli_or_tui_route() -> None:
    assert "private-melroformer-bridge" not in PUBLIC_COMMANDS
    assert "private-melroformer-bridge" not in DIRECT_TUI_COMMANDS


def test_private_loader_rejects_unpinned_device_before_artifact_access() -> None:
    with pytest.raises(ValueError, match="device must be gpu or cpu"):
        _load_private_melroformer_model(
            source_root="missing",
            checkpoint_path="missing",
            companion_root="missing",
            device="auto",
        )


def test_descriptor_stream_hashes_and_yields_exact_bound_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sunofriend._separation_melroformer_real_bridge as bridge

    contents = b"descriptor-native-kim-checkpoint"
    path = tmp_path / "model.safetensors"
    path.write_bytes(contents)
    monkeypatch.setattr(bridge, "CONVERSION_CHECKPOINT_BYTES", len(contents))
    monkeypatch.setattr(
        bridge,
        "CONVERSION_CHECKPOINT_SHA256",
        hashlib.sha256(contents).hexdigest(),
    )
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.set_inheritable(descriptor, False)
        os.lseek(descriptor, 7, os.SEEK_SET)

        with _verified_checkpoint_descriptor_stream(descriptor) as stream:
            assert stream.read() == contents

        assert os.get_inheritable(descriptor) is False
        assert os.fstat(descriptor).st_size == len(contents)
    finally:
        os.close(descriptor)


def test_descriptor_stream_rejects_inheritable_fd_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sunofriend._separation_melroformer_real_bridge as bridge

    contents = b"descriptor-native-kim-checkpoint"
    path = tmp_path / "model.safetensors"
    path.write_bytes(contents)
    monkeypatch.setattr(bridge, "CONVERSION_CHECKPOINT_BYTES", len(contents))
    monkeypatch.setattr(
        bridge,
        "CONVERSION_CHECKPOINT_SHA256",
        hashlib.sha256(contents).hexdigest(),
    )
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.set_inheritable(descriptor, True)
        with pytest.raises(ValueError, match="descriptor identity differs"):
            with _verified_checkpoint_descriptor_stream(descriptor):
                raise AssertionError("inheritable checkpoint was yielded")
    finally:
        os.close(descriptor)


def test_plans_nominal_half_overlap_for_full_initial_excerpt() -> None:
    assert _plan_excerpt_chunks(NOMINAL_CHUNK_FRAMES) == ((0, NOMINAL_CHUNK_FRAMES),)
    assert _plan_excerpt_chunks(MAXIMUM_EXCERPT_FRAMES) == (
        (0, 352_800),
        (176_400, 529_200),
        (352_800, 661_500),
    )


def test_crossfade_pair_has_unit_weight_through_overlap() -> None:
    first = _chunk_crossfade_weights(
        NOMINAL_CHUNK_FRAMES,
        fade_in=False,
        fade_out=True,
        np=np,
    )
    second = _chunk_crossfade_weights(
        NOMINAL_CHUNK_FRAMES,
        fade_in=True,
        fade_out=False,
        np=np,
    )

    np.testing.assert_allclose(
        first[-NOMINAL_HOP_FRAMES:] + second[:NOMINAL_HOP_FRAMES],
        1.0,
        rtol=0.0,
        atol=1e-12,
    )


@pytest.mark.parametrize("frames", [0, MAXIMUM_EXCERPT_FRAMES + 1])
def test_rejects_excerpt_plan_outside_initial_bound(frames: int) -> None:
    with pytest.raises(ValueError, match="outside bounds"):
        _plan_excerpt_chunks(frames)


def test_loads_only_report_bound_private_pcm24_excerpt(tmp_path: Path) -> None:
    report, report_sha256 = _authorised_excerpt(tmp_path)
    handle = _PrivateMelRoFormerHandle(
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

    audio, evidence = _load_private_authorised_excerpt(
        handle,
        report_path=report,
        expected_report_sha256=report_sha256,
    )

    assert audio.shape == (4_096, 2)
    assert audio.dtype == np.float32
    assert np.count_nonzero(audio) == 0
    assert evidence["track_id"] == "owned-example"
    assert evidence["audio_persisted_by_bridge"] is False
    assert "path" not in repr(evidence).lower()

    model_free_audio, model_free_evidence = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=report,
        expected_report_sha256=report_sha256,
    )
    np.testing.assert_array_equal(model_free_audio, audio)
    assert model_free_evidence == evidence


def test_loads_track_specific_private_reference_excerpt(tmp_path: Path) -> None:
    report, _ = _authorised_excerpt(tmp_path)
    document = json.loads(report.read_text())
    document["corpus"] = {
        "artist": None,
        "authority_scope": "track-specific private local evaluation only",
        "manifest_schema": "sunofriend.private-reference-separation-corpus.v1",
        "preferred_credit": None,
        "track_id": "private-example",
        "track_title": "Private example",
        "permission": {
            "public_demo_use": False,
            "recorded_on": "2026-07-31",
            "repository_distribution": False,
            "scope": "private_local_evaluation_only",
            "status": "user_authorised",
        },
    }
    _write_self_hashed_report(report, document)
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()

    audio, evidence = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=report,
        expected_report_sha256=report_sha256,
    )

    assert audio.shape == (4_096, 2)
    assert evidence["track_id"] == "private-example"
    assert evidence["rights_authority"] == (
        "user_authorised_private_local_evaluation"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "not_recorded_in_manifest"),
        ("scope", "private_research"),
        ("repository_distribution", True),
        ("public_demo_use", True),
        ("recorded_on", ""),
    ],
)
def test_rejects_incomplete_or_broadened_private_reference_authority(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    report, _ = _authorised_excerpt(tmp_path)
    document = json.loads(report.read_text())
    document["corpus"] = {
        "artist": None,
        "authority_scope": "track-specific private local evaluation only",
        "manifest_schema": "sunofriend.private-reference-separation-corpus.v1",
        "preferred_credit": None,
        "track_id": "private-example",
        "track_title": "Private example",
        "permission": {
            "public_demo_use": False,
            "recorded_on": "2026-07-31",
            "repository_distribution": False,
            "scope": "private_local_evaluation_only",
            "status": "user_authorised",
        },
    }
    document["corpus"]["permission"][field] = value
    _write_self_hashed_report(report, document)
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="authorisation scope differs"):
        _load_private_authorised_excerpt_pcm24(
            np,
            report_path=report,
            expected_report_sha256=report_sha256,
        )


def test_authorised_excerpt_rejects_report_hash_or_product_permission(
    tmp_path: Path,
) -> None:
    report, report_sha256 = _authorised_excerpt(tmp_path)
    handle = _PrivateMelRoFormerHandle(
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
    with pytest.raises(ValueError, match="hash differs"):
        _load_private_authorised_excerpt(
            handle,
            report_path=report,
            expected_report_sha256="0" * 64,
        )

    document = json.loads(report.read_text())
    document["permissions"]["public_result"] = True
    _write_self_hashed_report(report, document)
    changed_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="product permissions differ"):
        _load_private_authorised_excerpt(
            handle,
            report_path=report,
            expected_report_sha256=changed_sha256,
        )


def _authorised_excerpt(root: Path) -> tuple[Path, str]:
    audio_directory = root / "LOCAL-MODEL-INPUT"
    audio_directory.mkdir()
    audio_path = audio_directory / "source-44100.wav"
    payload = io.BytesIO()
    with wave.open(payload, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(b"\0" * 4_096 * 2 * 3)
    audio_path.write_bytes(payload.getvalue())
    audio_sha256 = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    duration = 4_096 / 44_100
    document = {
        "schema": "sunofriend.private-authorised-separation-excerpt.v1",
        "status": "complete_review_required",
        "evidence_scope": "private_development_only",
        "corpus": {
            "track_id": "owned-example",
            "track_title": "Owned example",
            "permission": {
                "authority": "creator_and_copyright_holder",
                "allowed_use": "download, study, transform and reuse",
            },
        },
        "excerpt": {"start_seconds": 10.0, "end_seconds": 10.0 + duration},
        "original": {
            "local_model_input": {
                "artifact": {
                    "path": "LOCAL-MODEL-INPUT/source-44100.wav",
                    "bytes": audio_path.stat().st_size,
                    "sha256": audio_sha256,
                },
                "geometry": {
                    "channels": 2,
                    "duration_seconds": duration,
                    "frames": 4_096,
                    "sample_rate": 44_100,
                },
            }
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
    }
    report = root / "authorised-separation-excerpt.json"
    _write_self_hashed_report(report, document)
    return report, hashlib.sha256(report.read_bytes()).hexdigest()


def _write_self_hashed_report(path: Path, document: dict[str, object]) -> None:
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
