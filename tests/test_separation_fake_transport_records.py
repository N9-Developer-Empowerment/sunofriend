from __future__ import annotations

import ast
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import sunofriend._separation_fake_transport_records as records_module

from sunofriend._separation_checkpoint_launch_v2_records import (
    _SEPARATION_LAUNCH_PLAN_V2_SCHEMA,
)
from sunofriend._separation_checkpoint_transport_records import (
    SEPARATION_WORKER_REQUEST_V2_SCHEMA,
)
from sunofriend._separation_fake_transport_records import (
    _FAKE_LAUNCH_SCHEMA,
    _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    _FAKE_REQUEST_SCHEMA,
    _FAKE_RESULT_MAXIMUM_FRAME_BYTES,
    _FAKE_RESULT_SCHEMA,
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
    _SeparationFakeWorkerResultRecord,
    _build_separation_fake_launch_plan,
    _build_separation_fake_worker_request,
    _build_separation_fake_worker_result,
    _complete_descriptor_report,
    _expected_fixture_outputs,
    _validate_fake_launch_plan_shape,
    _validate_fake_worker_request_shape,
    _validate_fake_worker_result_shape,
)
from sunofriend.separation_checkpoint_descriptor_lease import (
    _release_separation_checkpoint_descriptor_fd5,
    close_separation_checkpoint_descriptor_lease,
)
from tests.test_separation_launch_v2_facade import _issue, _prepared


_RUN_NONCE = "a" * 64


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _records(tmp_path: Path):
    fixture, lease, _observation, v2, reservation = _prepared(tmp_path)
    try:
        blocked_launch = _issue(lease, reservation, v2)
        request = _build_separation_fake_worker_request(
            worker_request_v2=v2,
            blocked_launch_plan_v2=blocked_launch,
            run_nonce=_RUN_NONCE,
        )
        launch = _build_separation_fake_launch_plan(
            fake_worker_request=request,
            runtime_executable_sha256="1" * 64,
            runtime_executable_bytes=4_096,
            fake_worker_sha256="2" * 64,
            fake_worker_bytes=8_192,
        )
        checkpoint = request["bindings"]
        result = _build_separation_fake_worker_result(
            fake_worker_request=request,
            fake_launch_plan=launch,
            status="complete",
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
            outputs=_expected_fixture_outputs(request),
            error=None,
        )
        return (
            fixture,
            lease,
            reservation,
            v2,
            blocked_launch,
            request,
            launch,
            result,
        )
    finally:
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
        close_separation_checkpoint_descriptor_lease(lease)


def test_fake_records_are_parseable_but_never_execution_authority(
    tmp_path: Path,
) -> None:
    _fixture, _lease, _reservation, v2, blocked, request, launch, result = (
        _records(tmp_path)
    )

    assert request["schema"] == _FAKE_REQUEST_SCHEMA
    assert launch["schema"] == _FAKE_LAUNCH_SCHEMA
    assert result["schema"] == _FAKE_RESULT_SCHEMA
    assert request["schema"] != SEPARATION_WORKER_REQUEST_V2_SCHEMA
    assert launch["schema"] != _SEPARATION_LAUNCH_PLAN_V2_SCHEMA
    assert v2["execution_permitted"] is False
    assert blocked["execution_permitted"] is False
    assert request["historical_design"]["blocked_v2_is_execution_authority"] is False
    assert request["test_only_execution_supported"] is False
    assert request["test_only_execution_permitted"] is False
    assert launch["test_only_worker_start_supported"] is False
    assert launch["test_only_worker_start_permitted"] is False
    assert launch["status"] == "blocked"
    assert launch["run_status"] == "not_run"
    assert request["real_separation_permitted"] is False
    assert launch["real_separation_permitted"] is False


def test_request_is_path_free_frozen_and_carries_exact_nonce(
    tmp_path: Path,
) -> None:
    *_, v2, blocked, request, _launch, _result = _records(tmp_path)

    assert type(request) is _SeparationFakeWorkerRequestRecord
    assert _validate_fake_worker_request_shape(request) is request
    assert request["run_nonce"] == _RUN_NONCE
    assert request["historical_design"] == {
        "worker_request_v2_sha256": v2["request_sha256"],
        "blocked_launch_plan_v2_sha256": blocked["plan_sha256"],
        "blocked_v2_is_execution_authority": False,
        "purpose": "design_hash_continuity_only",
    }
    assert [
        row["logical_descriptor"] for row in request["descriptor_requirements"]
    ] == [3, 4, 5]
    assert request["descriptor_requirements"][0]["purpose"] == (
        "canonical_fake_transport_envelope"
    )
    assert request["fixture"]["generation"] == (
        "code_owned_two_frame_pcm24_per_role"
    )
    assert all(value is False for value in request["effects"].values())
    assert "/" not in str(_plain(request))
    with pytest.raises(TypeError):
        request["roles"][0] = "keys"


@pytest.mark.parametrize("run_nonce", ["", "a" * 63, "a" * 65, "G" * 64])
def test_request_rejects_noncanonical_run_nonce(
    tmp_path: Path,
    run_nonce: str,
) -> None:
    _fixture, lease, _observation, v2, reservation = _prepared(tmp_path)
    try:
        blocked = _issue(lease, reservation, v2)
        with pytest.raises(ValueError, match="64 lowercase hex"):
            _build_separation_fake_worker_request(
                worker_request_v2=v2,
                blocked_launch_plan_v2=blocked,
                run_nonce=run_nonce,
            )
    finally:
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
        close_separation_checkpoint_descriptor_lease(lease)


def test_plain_copies_are_not_exact_records(tmp_path: Path) -> None:
    *_, request, launch, result = _records(tmp_path)[5:]

    for value, validator in (
        (_plain(request), _validate_fake_worker_request_shape),
        (_plain(launch), _validate_fake_launch_plan_shape),
    ):
        with pytest.raises(ValueError, match="exact validated"):
            validator(value)

    with pytest.raises(ValueError, match="exact validated"):
        _validate_fake_worker_result_shape(
            _plain(result),
            request=request,
            launch=launch,
        )


def test_launch_records_unimplemented_close_all_boundary(
    tmp_path: Path,
) -> None:
    *_, request, launch, _result = _records(tmp_path)[5:]

    assert type(launch) is _SeparationFakeLaunchPlanRecord
    assert launch["run_nonce"] == request["run_nonce"] == _RUN_NONCE
    descriptor = launch["descriptor_policy"]
    assert descriptor["parent_descriptor_table_mutation_forbidden"] is True
    assert descriptor["child_only_mapping_required"] is True
    assert descriptor["child_only_mapping_proven"] is False
    assert descriptor["inherit_unlisted_descriptors_required"] is False
    assert descriptor["inherit_unlisted_descriptors_proven"] is False
    assert descriptor["raw_descriptor_values_serialized"] is False
    process = launch["process_policy"]
    assert process["process_api_required"] == "native_close_all_launcher"
    assert process["process_api_implemented"] is False
    assert process["native_close_all_launcher_required"] is True
    assert process["native_close_all_launcher_implemented"] is False
    assert process["fixed_worker_fd_hygiene_required"] is True
    assert process["fixed_worker_fd_hygiene_proven"] is False
    assert process["preexec_callback"] is False
    assert process["argv_serialized"] is False
    assert launch["decision"]["status"] == "blocked"
    assert "native_close_all_launcher_not_implemented" in (
        launch["decision"]["blockers"]
    )
    assert "unlisted_descriptor_closure_not_proven" in (
        launch["decision"]["blockers"]
    )
    assert "fresh_parent_run_nonce_not_proven" in (
        launch["decision"]["blockers"]
    )
    assert "fake_launch_v1_is_permanently_non_executable" in (
        launch["limitations"]
    )
    assert "/" not in str(_plain(launch))


def test_complete_result_is_worker_report_only_and_two_frame_pcm24(
    tmp_path: Path,
) -> None:
    *_, request, launch, result = _records(tmp_path)[5:]

    assert type(result) is _SeparationFakeWorkerResultRecord
    assert result["run_nonce"] == request["run_nonce"] == launch["run_nonce"]
    assert result["evidence_authority"] == "worker_report_only"
    assert result["checkpoint_report"]["full_hash_verified"] is True
    assert result["checkpoint_report"]["deserialized"] is False
    assert result["outputs"] == tuple(_expected_fixture_outputs(request))
    for item in result["outputs"]:
        payload = bytes.fromhex(item["payload_hex"])
        assert item["payload_encoding"] == "lowercase_hex"
        assert payload[:4] == b"RIFF"
        assert struct.unpack("<I", payload[40:44])[0] == 6
        assert len(payload[44:]) == 6
        assert item["geometry"] == {
            "sample_rate": 8_000,
            "channels": 1,
            "frames": 2,
            "duration_seconds": 0.00025,
        }
    assert result["effects"]["output_payloads_generated"] is True
    assert result["effects"]["output_files_created"] is False
    assert result["effects"]["network_used"] is False

    tampered = _plain(result)
    tampered["outputs"][0]["payload_hex"] = "00"
    with pytest.raises(ValueError, match="payload identity|deterministic"):
        records_module._new_result(tampered, request=request, launch=launch)


def test_failed_result_has_no_output_and_never_deserializes_checkpoint(
    tmp_path: Path,
) -> None:
    *_, request, launch, _result = _records(tmp_path)[5:]
    checkpoint = request["bindings"]
    failed = _build_separation_fake_worker_result(
        fake_worker_request=request,
        fake_launch_plan=launch,
        status="failed",
        descriptor_report={
            key: False if key != "unexpected_open_descriptors" else 0
            for key in _complete_descriptor_report()
        },
        checkpoint_report={
            "sha256": checkpoint["checkpoint_sha256"],
            "bytes": checkpoint["checkpoint_bytes"],
            "file_identity_sha256": checkpoint[
                "checkpoint_file_identity_sha256"
            ],
            "identity_before_hash_sha256": None,
            "identity_after_hash_sha256": None,
            "unchanged": False,
            "full_hash_verified": False,
            "deserialized": False,
        },
        outputs=[],
        error={
            "code": "checkpoint_mismatch",
            "message": "Checkpoint evidence did not match",
            "retryable": False,
        },
    )

    assert failed["status"] == "failed"
    assert failed["outputs"] == ()
    assert failed["checkpoint_report"]["deserialized"] is False
    assert failed["effects"]["output_payloads_generated"] is False
    assert failed["effects"]["output_files_created"] is False


@pytest.mark.parametrize(
    ("record_name", "hash_name"),
    (
        ("request", "request_sha256"),
        ("launch", "plan_sha256"),
        ("result", "result_sha256"),
    ),
)
def test_self_hash_tampering_fails(
    tmp_path: Path,
    record_name: str,
    hash_name: str,
) -> None:
    request, launch, result = _records(tmp_path)[5:]
    value = {"request": request, "launch": launch, "result": result}[record_name]
    document = _plain(value)
    document[hash_name] = "0" * 64
    with pytest.raises(ValueError, match="hash is invalid"):
        if record_name == "request":
            records_module._new_request(document)
        elif record_name == "launch":
            records_module._new_launch(document)
        else:
            records_module._new_result(document, request=request, launch=launch)


def test_total_frame_limits_include_sibling_protocol_header(
    tmp_path: Path,
) -> None:
    *_, request, launch, result = _records(tmp_path)[5:]

    assert _FAKE_REQUEST_MAXIMUM_FRAME_BYTES == 65_536
    assert _FAKE_RESULT_MAXIMUM_FRAME_BYTES == 1_048_576
    assert launch["process_policy"]["request_maximum_bytes"] == 65_536
    assert launch["process_policy"]["result_maximum_bytes"] == 1_048_576
    assert len(records_module._canonical_json(_plain(request))) + 16 <= 65_536
    assert len(records_module._canonical_json(_plain(result))) + 16 <= 1_048_576


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_record_module_has_no_effectful_surface_or_terminal_receipt() -> None:
    source = Path(records_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "asyncio",
        "ctypes",
        "fcntl",
        "http",
        "importlib",
        "multiprocessing",
        "onnxruntime",
        "os",
        "pickle",
        "requests",
        "runpy",
        "safetensors",
        "socket",
        "subprocess",
        "torch",
        "urllib",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "dup",
        "dup2",
        "eval",
        "exec",
        "fork",
        "load",
        "loads",
        "open",
        "popen",
        "posix_spawn",
        "posix_spawnp",
        "set_inheritable",
        "spawn",
        "system",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            } & forbidden_imports
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        elif isinstance(node, ast.Call):
            qualified = _qualified_name(node.func)
            assert (
                qualified.rsplit(".", 1)[-1] not in forbidden_calls
                or qualified == "re.compile"
            )

    assert "TerminalReceipt" not in source
    assert "terminal_receipt" not in source
    assert records_module.__all__ == []
