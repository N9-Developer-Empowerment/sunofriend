from __future__ import annotations

import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import sunofriend._separation_fake_execution_protocol as protocol

from sunofriend._separation_fake_execution_protocol import (
    _decode_fake_execution_request_frame,
    _decode_fake_execution_result_frame,
    _encode_fake_execution_result_frame,
    _expected_fake_execution_request_frame_bytes,
    _expected_fake_execution_result_frame_bytes,
)
from sunofriend._separation_fake_execution_records import (
    _EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    _EXPECTED_FAKE_WORKER_SOURCE_SHA256,
    _FAKE_LAUNCH_V3_SCHEMA,
    _FAKE_RESULT_V2_SCHEMA,
    _SeparationFakeLaunchPlanV3Record,
    _SeparationFakeWorkerResultV2Record,
    _build_prepared_separation_fake_launch_plan_v3_record,
    _build_separation_fake_worker_result_v2,
    _expected_outputs,
    _expected_post_cpython_signal_report,
    _validate_prepared_separation_fake_launch_plan_v3_record_shape,
    _validate_separation_fake_worker_result_v2_record_shape,
)
from sunofriend._separation_fake_launch_v2_records import (
    _build_blocked_separation_fake_launch_plan_v2_record,
)
from sunofriend._separation_fake_transport_records import (
    _build_separation_fake_launch_plan,
    _complete_descriptor_report,
)
from tests.test_separation_fake_transport_records import _records


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _stat_identity(
    *,
    inode: int,
    byte_count: int,
    executable: bool = False,
) -> dict[str, int]:
    return {
        "device": 10,
        "inode": inode,
        "mode": stat.S_IFREG | (0o755 if executable else 0o600),
        "links": 1,
        "owner": 501,
        "group": 20,
        "bytes": byte_count,
        "modified_ns": 1_000_000 + inode,
        "changed_ns": 2_000_000 + inode,
    }


def _execution_records(tmp_path: Path):
    historical = _records(tmp_path)
    request = historical[5]
    historical_launch_v1 = historical[6]
    launch_v1 = _build_separation_fake_launch_plan(
        fake_worker_request=request,
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        fake_worker_sha256=_EXPECTED_FAKE_WORKER_SOURCE_SHA256,
        fake_worker_bytes=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    )
    launch_v2 = _build_blocked_separation_fake_launch_plan_v2_record(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        native_launcher_sha256="3" * 64,
        native_launcher_bytes=2_048,
        native_launcher_stat_identity=_stat_identity(
            inode=101,
            byte_count=2_048,
        ),
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        runtime_executable_stat_identity=_stat_identity(
            inode=102,
            byte_count=4_096,
            executable=True,
        ),
        fake_worker_sha256=_EXPECTED_FAKE_WORKER_SOURCE_SHA256,
        fake_worker_bytes=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
        fake_worker_stat_identity=_stat_identity(
            inode=103,
            byte_count=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
        ),
    )
    launch_v3 = _build_prepared_separation_fake_launch_plan_v3_record(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
        native_build_receipt_sha256="4" * 64,
    )
    checkpoint = launch_v3["bindings"]
    result = _build_separation_fake_worker_result_v2(
        fake_launch_plan_v3=launch_v3,
        status="complete",
        process_report={
            "pid": 123,
            "pgid": 123,
            "pgid_equals_pid": True,
            "process_creation_attempted_by_worker": False,
            "reported_identifiers_are_signal_authority": False,
        },
        signal_report=_expected_post_cpython_signal_report(),
        descriptor_report=_complete_descriptor_report(),
        checkpoint_report={
            "sha256": checkpoint["checkpoint_sha256"],
            "bytes": checkpoint["checkpoint_bytes"],
            "file_identity_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "identity_before_hash_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "identity_after_hash_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "unchanged": True,
            "full_hash_verified": True,
            "deserialized": False,
        },
        outputs=_expected_outputs(launch_v3),
        error=None,
    )
    return (
        request,
        historical_launch_v1,
        launch_v1,
        launch_v2,
        launch_v3,
        result,
    )


def test_v3_is_prepared_but_never_serialized_authority(
    tmp_path: Path,
) -> None:
    request, historical_v1, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )

    assert type(launch_v3) is _SeparationFakeLaunchPlanV3Record
    assert type(result) is _SeparationFakeWorkerResultV2Record
    assert launch_v3["schema"] == _FAKE_LAUNCH_V3_SCHEMA
    assert result["schema"] == _FAKE_RESULT_V2_SCHEMA
    assert launch_v3["status"] == "prepared"
    assert launch_v3["run_status"] == "not_run"
    assert launch_v3["test_only_worker_start_supported"] is True
    assert launch_v3["test_only_worker_start_permitted"] is False
    assert launch_v3["authority"][
        "serialized_plan_is_execution_authority"
    ] is False
    assert launch_v3["real_separation_permitted"] is False
    assert launch_v3["capabilities"]["model_import_supported"] is False
    assert launch_v3["historical_bindings"] == {
        "fake_worker_request_v1_sha256": request["request_sha256"],
        "fake_launch_plan_v1_sha256": launch_v1["plan_sha256"],
        "blocked_fake_launch_plan_v2_sha256": launch_v2["plan_sha256"],
        "historical_records_are_execution_authority": False,
    }
    assert historical_v1["test_only_worker_start_permitted"] is False
    assert launch_v1["test_only_worker_start_permitted"] is False
    assert launch_v2["test_only_worker_start_permitted"] is False
    assert launch_v2["status"] == "blocked"
    assert all(item is False for item in launch_v3["effects"].values())


def test_v3_and_result_are_deeply_immutable_and_exact(
    tmp_path: Path,
) -> None:
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )

    assert _validate_prepared_separation_fake_launch_plan_v3_record_shape(
        launch_v3,
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
    ) is launch_v3
    assert _validate_separation_fake_worker_result_v2_record_shape(
        result,
        fake_launch_plan_v3=launch_v3,
    ) is result
    with pytest.raises(TypeError):
        launch_v3["bindings"]["checkpoint_bytes"] = 1
    with pytest.raises(TypeError):
        result["outputs"][0]["payload_hex"] = "00"
    with pytest.raises(ValueError, match="exact validated"):
        _validate_prepared_separation_fake_launch_plan_v3_record_shape(
            _plain(launch_v3),
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
            blocked_fake_launch_plan_v2=launch_v2,
        )
    with pytest.raises(ValueError, match="exact validated"):
        _validate_separation_fake_worker_result_v2_record_shape(
            _plain(result),
            fake_launch_plan_v3=launch_v3,
        )


def test_v3_requires_the_pinned_worker_source(tmp_path: Path) -> None:
    historical = _records(tmp_path)
    request = historical[5]
    wrong_launch = historical[6]
    wrong_v2 = _build_blocked_separation_fake_launch_plan_v2_record(
        fake_worker_request=request,
        fake_launch_plan_v1=wrong_launch,
        native_launcher_sha256="3" * 64,
        native_launcher_bytes=2_048,
        native_launcher_stat_identity=_stat_identity(
            inode=101,
            byte_count=2_048,
        ),
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        runtime_executable_stat_identity=_stat_identity(
            inode=102,
            byte_count=4_096,
            executable=True,
        ),
        fake_worker_sha256="2" * 64,
        fake_worker_bytes=8_192,
        fake_worker_stat_identity=_stat_identity(
            inode=103,
            byte_count=8_192,
        ),
    )
    with pytest.raises(ValueError, match="pinned worker source"):
        _build_prepared_separation_fake_launch_plan_v3_record(
            fake_worker_request=request,
            fake_launch_plan_v1=wrong_launch,
            blocked_fake_launch_plan_v2=wrong_v2,
            native_build_receipt_sha256="4" * 64,
        )


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("process_report", "pgid", 124),
        ("signal_report", "main_thread_mask_empty", False),
        ("checkpoint_report", "full_hash_verified", False),
        ("outputs", "payload_hex", "00"),
    ],
)
def test_result_v2_rejects_tampering(
    tmp_path: Path,
    section: str,
    key: str,
    value: Any,
) -> None:
    *_, launch_v3, result = _execution_records(tmp_path)
    document = _plain(result)
    document.pop("result_sha256")
    if section == "outputs":
        document[section][0][key] = value
    else:
        document[section][key] = value
    from sunofriend._separation_checkpoint_canonical import canonical_sha256
    from sunofriend._separation_fake_execution_records import (
        _new_separation_fake_worker_result_v2_record,
    )

    document["result_sha256"] = canonical_sha256(document)
    with pytest.raises(ValueError):
        _new_separation_fake_worker_result_v2_record(
            document,
            fake_launch_plan_v3=launch_v3,
        )


def test_result_v2_requires_dedicated_process_group_and_complete_only(
    tmp_path: Path,
) -> None:
    *_, launch_v3, result = _execution_records(tmp_path)
    document = _plain(result)
    document["process_report"]["pgid"] = 124
    document["process_report"]["pgid_equals_pid"] = False
    document.pop("result_sha256")
    from sunofriend._separation_checkpoint_canonical import canonical_sha256
    from sunofriend._separation_fake_execution_records import (
        _new_separation_fake_worker_result_v2_record,
    )

    document["result_sha256"] = canonical_sha256(document)
    with pytest.raises(ValueError, match="process report"):
        _new_separation_fake_worker_result_v2_record(
            document,
            fake_launch_plan_v3=launch_v3,
        )
    with pytest.raises(ValueError, match="complete evidence only"):
        _build_separation_fake_worker_result_v2(
            fake_launch_plan_v3=launch_v3,
            status="failed",
            process_report=result["process_report"],
            signal_report=result["signal_report"],
            descriptor_report=result["descriptor_report"],
            checkpoint_report=result["checkpoint_report"],
            outputs=(),
            error={
                "code": "request_invalid",
                "message": "request invalid",
                "retryable": False,
            },
        )


def _test_only_admitted_envelope_frame(
    launch_v3: _SeparationFakeLaunchPlanV3Record,
) -> bytes:
    """Make protocol bytes in tests; product code intentionally has no issuer."""

    from sunofriend._separation_checkpoint_canonical import canonical_sha256

    payload = {
        "schema": protocol._FAKE_EXECUTION_ENVELOPE_SCHEMA,
        "policy_id": launch_v3["policy_id"],
        "evidence_scope": "private_development",
        "status": "admitted",
        "backend_scope": "deterministic_transport_fixture_only",
        "test_only_execution_permitted": True,
        "real_separation_permitted": False,
        "run_nonce": launch_v3["run_nonce"],
        "fake_launch_plan_v3_sha256": launch_v3["plan_sha256"],
        "serialized_envelope_is_parent_authority": False,
        "fake_launch_plan_v3": _plain(launch_v3),
    }
    return protocol._encode_frame(
        {**payload, "envelope_sha256": canonical_sha256(payload)},
        magic=protocol._REQUEST_MAGIC_V2,
        maximum_frame_bytes=65_536,
        label="test-only fake execution request",
    )


def test_v2_frames_are_magic_separated_but_have_no_product_admission_issuer(
    tmp_path: Path,
) -> None:
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )
    assert not hasattr(protocol, "_issue_fake_execution_admission")
    assert not hasattr(protocol, "_encode_fake_execution_request_frame")
    request_frame = _test_only_admitted_envelope_frame(launch_v3)
    result_frame = _encode_fake_execution_result_frame(
        result,
        fake_launch_plan_v3=launch_v3,
    )

    decoded_plan = _decode_fake_execution_request_frame(
        request_frame,
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
    )
    decoded_result = _decode_fake_execution_result_frame(
        result_frame,
        fake_launch_plan_v3=launch_v3,
    )
    assert dict(decoded_plan) == dict(launch_v3)
    assert dict(decoded_result) == dict(result)
    assert _expected_fake_execution_request_frame_bytes(
        request_frame[:16]
    ) == len(request_frame)
    assert _expected_fake_execution_result_frame_bytes(
        result_frame[:16]
    ) == len(result_frame)
def test_v2_frame_magics_do_not_decode_as_historical_v1(
    tmp_path: Path,
) -> None:
    request, _historical, launch_v1, launch_v2, launch_v3, _result = (
        _execution_records(tmp_path)
    )
    frame = _test_only_admitted_envelope_frame(launch_v3)
    from sunofriend._separation_fake_worker_protocol import (
        _decode_fake_worker_request_frame,
    )

    with pytest.raises(ValueError, match="magic"):
        _decode_fake_worker_request_frame(frame)
