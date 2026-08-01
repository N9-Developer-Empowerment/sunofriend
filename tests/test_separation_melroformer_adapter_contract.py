from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from sunofriend._separation_melroformer_adapter_contract import (
    ENGINE_SCHEMA,
    REAL_ENGINE_SCHEMA,
    _RealMelRoFormerEngineResult,
    _SyntheticMelRoFormerEngineResult,
    _accept_private_melroformer_real_result,
    _exercise_private_melroformer_adapter_contract,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


NO_EFFECTS = {
    "filesystem_accessed": False,
    "filesystem_written": False,
    "network_used": False,
    "package_installed": False,
    "checkpoint_opened": False,
    "tensor_deserialized": False,
    "model_imported": False,
    "process_started": False,
}
REAL_EFFECTS = {
    "filesystem_accessed": True,
    "filesystem_written": False,
    "network_used": False,
    "package_installed": False,
    "checkpoint_opened": True,
    "tensor_deserialized": True,
    "model_imported": True,
    "process_started": False,
    "audio_inference_called": True,
}


def _source() -> list[list[float]]:
    return [[0.5, -0.25], [0.25, -0.5], [0.0, 0.125]]


def _result(**changes: object) -> _SyntheticMelRoFormerEngineResult:
    values: dict[str, object] = {
        "schema": ENGINE_SCHEMA,
        "engine_kind": "synthetic_test_double",
        "vocals": [[0.125, -0.0625], [0.0625, -0.125], [0.0, 0.03125]],
        "sanitized_weight_keys": ["mask.weight", "transformer.0.weight"],
        "expected_model_keys": ["transformer.0.weight", "mask.weight"],
        "dropped_raw_weight_keys": ["transformer.0.rotary_embed.freqs"],
        "effects": dict(NO_EFFECTS),
    }
    values.update(changes)
    return _SyntheticMelRoFormerEngineResult(**values)  # type: ignore[arg-type]


def _real_result(**changes: object) -> _RealMelRoFormerEngineResult:
    values: dict[str, object] = {
        "schema": REAL_ENGINE_SCHEMA,
        "engine_kind": "private_real_kim_vocal_2",
        "vocals": [[0.125, -0.0625], [0.0625, -0.125], [0.0, 0.03125]],
        "sanitized_weight_keys": ["mask.weight", "transformer.0.weight"],
        "expected_model_keys": ["transformer.0.weight", "mask.weight"],
        "dropped_raw_weight_keys": ["transformer.0.rotary_embed.freqs"],
        "inference_seconds": 1.25,
        "peak_memory_bytes": 2_500_000_000,
        "device": "gpu",
        "chunk_count": 1,
        "chunk_frames": 3,
        "hop_frames": 3,
        "effects": dict(REAL_EFFECTS),
    }
    values.update(changes)
    return _RealMelRoFormerEngineResult(**values)  # type: ignore[arg-type]


def test_synthetic_contract_derives_residual_and_proves_accounting() -> None:
    with (
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
        patch("pathlib.Path.open", side_effect=AssertionError("file")),
    ):
        observation = _exercise_private_melroformer_adapter_contract(
            _source(), sample_rate=44_100, engine_result=_result()
        )

    assert observation.vocals[0] == (0.125, -0.0625)
    assert observation.instrumental[0] == (0.375, -0.1875)
    evidence = observation.evidence
    assert evidence["status"] == "synthetic_contract_complete_real_worker_absent"
    assert evidence["engine"]["invoked_by_adapter"] is False
    assert evidence["geometry"]["frames"] == 3
    assert evidence["weight_coverage"]["complete"] is True
    assert evidence["weight_coverage"]["missing_model_keys"] == ()
    assert evidence["additive_accounting"]["passed"] is True
    assert evidence["additive_accounting"]["pcm24_persistence_verified"] is False
    assert evidence["permissions"]["worker_start_permitted"] is False
    assert evidence["effects"]["filesystem_accessed"] is False


def test_real_result_uses_same_validation_core_without_persisting() -> None:
    observation = _accept_private_melroformer_real_result(
        _source(), sample_rate=44_100, engine_result=_real_result()
    )

    assert observation.vocals[0] == (0.125, -0.0625)
    assert observation.instrumental[0] == (0.375, -0.1875)
    evidence = observation.evidence
    assert evidence["status"] == "private_real_single_chunk_validated_not_persisted"
    assert evidence["weight_coverage"]["complete"] is True
    assert evidence["additive_accounting"]["passed"] is True
    assert evidence["additive_accounting"]["pcm24_persistence_verified"] is False
    assert evidence["measurement"]["peak_memory_bytes"] == 2_500_000_000
    assert evidence["measurement"]["device"] == "gpu"
    assert evidence["transport"]["chunk_count"] == 1
    assert evidence["transport"]["weighted_overlap_add"] is False
    assert evidence["permissions"]["private_inference_permitted"] is True
    assert evidence["permissions"]["worker_start_permitted"] is False
    assert evidence["effects"]["audio_inference_called"] is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"engine_kind": "synthetic_test_double"}, "identity differs"),
        ({"inference_seconds": 0.0}, "duration is invalid"),
        ({"peak_memory_bytes": 0}, "peak memory is invalid"),
        ({"device": "mps"}, "device is invalid"),
        ({"chunk_count": 0}, "chunk transport is invalid"),
        ({"hop_frames": 4}, "chunk transport is invalid"),
        ({"chunk_frames": 4, "hop_frames": 4}, "single-chunk transport differs"),
        (
            {"effects": {**REAL_EFFECTS, "filesystem_written": True}},
            "effects differ",
        ),
    ],
)
def test_real_result_rejects_identity_measurement_or_effect_drift(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _accept_private_melroformer_real_result(
            _source(), sample_rate=44_100, engine_result=_real_result(**changes)
        )


def test_real_overlap_result_has_distinct_status_and_exact_transport() -> None:
    source = [[0.0, 0.0]] * 4
    with (
        patch(
            "sunofriend._separation_melroformer_adapter_contract.NOMINAL_CHUNK_FRAMES",
            3,
        ),
        patch(
            "sunofriend._separation_melroformer_adapter_contract.NOMINAL_HOP_FRAMES",
            2,
        ),
    ):
        observation = _accept_private_melroformer_real_result(
            source,
            sample_rate=44_100,
            engine_result=_real_result(
                vocals=source,
                chunk_count=2,
                chunk_frames=3,
                hop_frames=2,
            ),
        )

    assert observation.evidence["status"] == (
        "private_real_overlapped_excerpt_validated_not_persisted"
    )
    assert observation.evidence["transport"]["weighted_overlap_add"] is True


def test_observation_is_deterministic_and_path_free() -> None:
    first = _exercise_private_melroformer_adapter_contract(
        _source(), sample_rate=44_100, engine_result=_result()
    )
    second = _exercise_private_melroformer_adapter_contract(
        _source(), sample_rate=44_100, engine_result=_result()
    )
    assert first == second
    assert (
        first.evidence["outputs"]["vocals"]["sha256"]
        == (second.evidence["outputs"]["vocals"]["sha256"])
    )
    assert "path" not in repr(first.evidence).lower()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"engine_kind": "mlx"}, "only a synthetic test double"),
        (
            {"effects": {**NO_EFFECTS, "model_imported": True}},
            "effects differ",
        ),
        (
            {"sanitized_weight_keys": ["mask.weight"]},
            "model-key coverage differs",
        ),
        (
            {"sanitized_weight_keys": ["mask.weight", "mask.weight"]},
            "duplicates",
        ),
        (
            {"dropped_raw_weight_keys": ["mask.weight"]},
            "unapproved weight key",
        ),
        (
            {"expected_model_keys": ["bad/key"]},
            "weight key is invalid",
        ),
    ],
)
def test_rejects_engine_or_weight_boundary_changes(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _exercise_private_melroformer_adapter_contract(
            _source(), sample_rate=44_100, engine_result=_result(**changes)
        )


@pytest.mark.parametrize(
    ("source", "sample_rate", "result", "message"),
    [
        (_source(), 48_000, _result(), "44.1 kHz"),
        ([], 44_100, _result(), "frame count"),
        ([[0.0]], 44_100, _result(vocals=[[0.0, 0.0]]), "must be stereo"),
        (
            [[math.nan, 0.0]],
            44_100,
            _result(vocals=[[0.0, 0.0]]),
            "outside the bound",
        ),
        (
            [[1.1, 0.0]],
            44_100,
            _result(vocals=[[0.0, 0.0]]),
            "outside the bound",
        ),
        (
            [[0.0, 0.0]],
            44_100,
            _result(vocals=[[17.0, 0.0]]),
            "outside the bound",
        ),
        (
            [[0.0, 0.0], [0.0, 0.0]],
            44_100,
            _result(vocals=[[0.0, 0.0]]),
            "frame count differs",
        ),
    ],
)
def test_rejects_invalid_audio_geometry_or_samples(
    source: list[list[float]],
    sample_rate: int,
    result: _SyntheticMelRoFormerEngineResult,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _exercise_private_melroformer_adapter_contract(
            source, sample_rate=sample_rate, engine_result=result
        )


def test_remains_absent_from_public_interfaces() -> None:
    assert "private-melroformer-adapter" not in PUBLIC_COMMANDS
    assert "private-melroformer-adapter" not in DIRECT_TUI_COMMANDS
