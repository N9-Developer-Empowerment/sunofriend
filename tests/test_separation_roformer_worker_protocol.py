from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import patch

import pytest

from sunofriend import _separation_roformer_challenger_plan as challenger
from sunofriend._separation_roformer_worker_protocol import (
    ROFORMER_WORKER_MAXIMUM_FRAMES,
    ROFORMER_WORKER_MAXIMUM_SOURCE_BYTES,
    ROFORMER_WORKER_OUTPUT_ALLOWLIST,
    ROFORMER_WORKER_PROTOCOL_SCHEMA,
    ROFORMER_WORKER_ROLES,
    _build_private_roformer_worker_protocol,
    _validate_private_roformer_worker_protocol,
    private_roformer_worker_protocol_sha256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case(case_id: str, *, frames: int = 661_500) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "source_id": f"source-{case_id}",
        "source_sha256": _sha(f"source-{case_id}"),
        "canonical_sha256": _sha(f"canonical-{case_id}"),
        "bytes": frames * 2 * 3 + 44,
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": frames,
            "duration_seconds": frames / 44_100,
        },
    }


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def test_protocol_is_bounded_immutable_path_free_and_non_executable() -> None:
    cases = [_case("case-a"), _case("case-b", frames=441_000)]
    with (
        patch("builtins.open", side_effect=AssertionError("filesystem")),
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        first = _build_private_roformer_worker_protocol(cases=cases)
        second = _build_private_roformer_worker_protocol(cases=cases)

    assert first == second
    assert first["schema"] == ROFORMER_WORKER_PROTOCOL_SCHEMA
    assert first["status"] == "protocol_defined_worker_absent"
    assert first["batch"]["case_count"] == 2
    assert first["batch"]["maximum_cases"] == 2
    assert first["batch"]["maximum_parallel_cases"] == 1
    assert first["batch"]["model_reuse_between_cases"] is False
    assert tuple(first["request_shape"]["roles"]) == ROFORMER_WORKER_ROLES
    assert tuple(first["request_shape"]["output_allowlist"]) == (
        ROFORMER_WORKER_OUTPUT_ALLOWLIST
    )
    assert first["request_shape"]["materialisation_status"] == "blocked"
    assert first["result_shape"]["exact_source_frame_horizon_required"] is True
    assert all(value is False for value in first["permissions"].values())
    assert all(value is False for value in first["effects"].values())
    assert private_roformer_worker_protocol_sha256(first) == (first["protocol_sha256"])
    assert not any(
        text.startswith(("/", "~")) for text in _all_strings(_plain(first["cases"]))
    )
    with pytest.raises(TypeError):
        first["permissions"]["worker_start_permitted"] = True  # type: ignore[index]


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _all_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _all_strings(item)]
    return []


def test_protocol_bindings_match_registered_candidate_and_are_not_public() -> None:
    protocol = _build_private_roformer_worker_protocol(cases=[_case("case-a")])

    assert protocol["bindings"]["config_sha256"] == challenger.CONFIG_SHA256
    assert protocol["bindings"]["dependency_lock_sha256"] == (
        challenger.RUNTIME_DEPENDENCY_LOCK_SHA256
    )
    assert protocol["bindings"]["checkpoint_asset_id"] == (
        challenger.CHECKPOINT_ASSET_ID
    )
    assert protocol["bindings"]["checkpoint_published_sha256"] is None
    assert "private-roformer-worker" not in PUBLIC_COMMANDS
    assert "private-roformer-worker" not in DIRECT_TUI_COMMANDS


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        ([], "one or two cases"),
        (
            [_case("case-a"), _case("case-b"), _case("case-c")],
            "one or two cases",
        ),
        ([_case("case-b"), _case("case-a")], "sorted and unique"),
        ([_case("../private")], "case_id is invalid"),
    ],
)
def test_protocol_rejects_invalid_case_sets(
    cases: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _build_private_roformer_worker_protocol(cases=cases)


def test_protocol_rejects_duplicate_audio_identity() -> None:
    first, second = _case("case-a"), _case("case-b")
    second["canonical_sha256"] = first["canonical_sha256"]
    with pytest.raises(ValueError, match="distinct canonical audio"):
        _build_private_roformer_worker_protocol(cases=[first, second])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sample_rate", 48_000, "stereo 44.1 kHz"),
        ("channels", 1, "stereo 44.1 kHz"),
        ("frames", ROFORMER_WORKER_MAXIMUM_FRAMES + 1, "stereo 44.1 kHz"),
    ],
)
def test_protocol_rejects_audio_outside_exact_geometry(
    field: str, value: int, message: str
) -> None:
    case = _case("case-a")
    case["geometry"][field] = value
    if field in {"sample_rate", "frames"}:
        case["geometry"]["duration_seconds"] = (
            case["geometry"]["frames"] / case["geometry"]["sample_rate"]
        )
    with pytest.raises(ValueError, match=message):
        _build_private_roformer_worker_protocol(cases=[case])


def test_protocol_rejects_oversize_or_boolean_byte_count() -> None:
    oversize = _case("case-a")
    oversize["bytes"] = ROFORMER_WORKER_MAXIMUM_SOURCE_BYTES + 1
    with pytest.raises(ValueError, match="bytes are outside bounds"):
        _build_private_roformer_worker_protocol(cases=[oversize])

    boolean = _case("case-a")
    boolean["bytes"] = True
    with pytest.raises(ValueError, match="must be an integer"):
        _build_private_roformer_worker_protocol(cases=[boolean])


def test_protocol_validation_rejects_permission_or_hash_tampering() -> None:
    protocol = _plain(_build_private_roformer_worker_protocol(cases=[_case("case-a")]))
    protocol["permissions"]["worker_start_permitted"] = True
    with pytest.raises(ValueError, match="differs from fixed policy"):
        _validate_private_roformer_worker_protocol(protocol)

    protocol = _plain(_build_private_roformer_worker_protocol(cases=[_case("case-a")]))
    protocol["protocol_sha256"] = _sha("tampered")
    with pytest.raises(ValueError, match="hash is invalid"):
        _validate_private_roformer_worker_protocol(protocol)
