from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any

import pytest

import sunofriend._separation_fake_worker_protocol as protocol
from sunofriend._separation_fake_transport_records import (
    _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    _build_separation_fake_launch_plan,
    _build_separation_fake_worker_request,
    _build_separation_fake_worker_result,
    _complete_descriptor_report,
    _expected_fixture_outputs,
)
from sunofriend._separation_fake_worker_protocol import (
    _decode_fake_worker_request_frame,
    _decode_fake_worker_result_frame,
    _encode_fake_worker_request_frame,
    _encode_fake_worker_result_frame,
    _expected_fake_worker_request_frame_bytes,
    _expected_fake_worker_result_frame_bytes,
    _verify_fake_worker_quarantine,
)
from sunofriend.separation_checkpoint_descriptor_lease import (
    _release_separation_checkpoint_descriptor_fd5,
    close_separation_checkpoint_descriptor_lease,
)
from tests.test_separation_launch_v2_facade import _issue, _prepared


@pytest.fixture
def fake_records(tmp_path: Path):
    records_root = tmp_path / "records"
    records_root.mkdir(mode=0o700)
    fixture, lease, _observation, v2, reservation = _prepared(records_root)
    try:
        blocked_launch = _issue(lease, reservation, v2)
        request = _build_separation_fake_worker_request(
            worker_request_v2=v2,
            blocked_launch_plan_v2=blocked_launch,
            run_nonce="ab" * 32,
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
        yield request, launch, result
    finally:
        _release_separation_checkpoint_descriptor_fd5(lease, reservation)
        close_separation_checkpoint_descriptor_lease(lease)
        assert fixture["checkpoint"].exists()


def test_request_envelope_and_result_frames_bind_exact_records(
    fake_records: tuple[Any, Any, Any],
) -> None:
    request, launch, result = fake_records
    request_frame = _encode_fake_worker_request_frame(request, launch)
    decoded_request, decoded_launch = _decode_fake_worker_request_frame(
        request_frame
    )
    result_frame = _encode_fake_worker_result_frame(
        result,
        fake_worker_request=request,
        fake_launch_plan=launch,
    )
    decoded_result = _decode_fake_worker_result_frame(
        result_frame,
        fake_worker_request=request,
        fake_launch_plan=launch,
    )

    assert dict(decoded_request) == dict(request)
    assert dict(decoded_launch) == dict(launch)
    assert dict(decoded_result) == dict(result)
    assert decoded_request is not request
    assert decoded_launch is not launch
    assert decoded_result is not result
    assert _expected_fake_worker_request_frame_bytes(
        request_frame[:16]
    ) == len(request_frame)
    assert _expected_fake_worker_result_frame_bytes(
        result_frame[:16]
    ) == len(result_frame)
    with pytest.raises(ValueError, match="magic"):
        _decode_fake_worker_result_frame(
            request_frame,
            fake_worker_request=request,
            fake_launch_plan=launch,
        )


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda value: value[:-1], "truncated or has trailing"),
        (lambda value: value + b"x", "truncated or has trailing"),
        (
            lambda value: value[:8] + struct.pack(">Q", 0) + value[16:],
            "length exceeds bounds",
        ),
        (
            lambda value: value[:8]
            + struct.pack(">Q", _FAKE_REQUEST_MAXIMUM_FRAME_BYTES)
            + value[16:],
            "length exceeds bounds",
        ),
    ],
)
def test_frame_boundaries_fail_closed(
    fake_records: tuple[Any, Any, Any],
    mutator: Any,
    message: str,
) -> None:
    request, launch, _result = fake_records
    frame = _encode_fake_worker_request_frame(request, launch)
    with pytest.raises(ValueError, match=message):
        _decode_fake_worker_request_frame(mutator(frame))


def test_frame_rejects_noncanonical_duplicate_and_nonfinite_json() -> None:
    payloads = [
        b'{ "schema": "request.v1" }',
        b'{"schema":"request.v1","schema":"other"}',
        b'{"schema":"request.v1","value":NaN}',
    ]
    for payload in payloads:
        frame = protocol._FRAME_HEADER.pack(
            protocol._REQUEST_MAGIC, len(payload)
        ) + payload
        with pytest.raises(ValueError):
            _decode_fake_worker_request_frame(frame)


def test_frame_depth_limit_is_enforced() -> None:
    nested: object = "leaf"
    for _ in range(protocol._MAXIMUM_JSON_DEPTH + 1):
        nested = [nested]
    with pytest.raises(ValueError, match="structure exceeds bounds"):
        protocol._encode_frame(
            {"schema": "request.v1", "nested": nested},
            magic=protocol._REQUEST_MAGIC,
            maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
            label="fake-worker request",
        )


def test_parent_observes_bound_pcm24_quarantine_without_publication(
    tmp_path: Path,
    fake_records: tuple[Any, Any, Any],
) -> None:
    request, launch, result = fake_records
    quarantine, directory_descriptor, descriptors = _quarantine(
        tmp_path, result
    )
    try:
        evidence = _verify_fake_worker_quarantine(
            fake_worker_request=request,
            fake_launch_plan=launch,
            fake_worker_result=result,
            quarantine_directory_descriptor=directory_descriptor,
            readable_descriptors=descriptors,
        )
        assert evidence["status"] == "verified"
        assert evidence["run_nonce"] == request["run_nonce"]
        assert evidence["publication_permitted"] is False
        assert evidence["selection_permitted"] is False
        assert evidence["ordinary_file_immutable_backing_proven"] is False
        assert evidence["output_count"] == len(result["outputs"])
        assert result["effects"]["output_payloads_generated"] is True
        assert result["effects"]["output_files_created"] is False
        assert all(
            item["pcm24_geometry_verified"]
            and item["code_owned_fixture_bytes_matched"]
            for item in evidence["outputs"]
        )
        assert evidence["parent_outputs"] == tuple(
            {
                key: item[key]
                for key in (
                    "role",
                    "slot_id",
                    "artifact_kind",
                    "sha256",
                    "bytes",
                    "geometry",
                )
            }
            for item in result["outputs"]
        )
        serialized = json.dumps(protocol._plain(evidence))
        assert str(quarantine) not in serialized
        assert "exact_tree_verified" not in evidence
        assert "fresh_quarantine_proven" not in evidence
    finally:
        _close_quarantine(directory_descriptor, descriptors)


def test_quarantine_rejects_missing_extra_corrupt_and_aliased_outputs(
    tmp_path: Path,
    fake_records: tuple[Any, Any, Any],
) -> None:
    request, launch, result = fake_records
    quarantine, directory_descriptor, descriptors = _quarantine(
        tmp_path, result
    )
    try:
        missing = dict(descriptors)
        missing.pop(next(iter(missing)))
        with pytest.raises(ValueError, match="cover every exact output slot"):
            _verify(request, launch, result, directory_descriptor, missing)

        extra = quarantine / "extra.wav"
        extra.write_bytes(b"not allowed")
        extra.chmod(0o600)
        with pytest.raises(ValueError, match="entry observation"):
            _verify(request, launch, result, directory_descriptor, descriptors)
        extra.unlink()

        first = result["outputs"][0]["slot_id"]
        outside_link = tmp_path / "outside-link.wav"
        os.link(quarantine / f"{first}.wav", outside_link)
        with pytest.raises(ValueError, match="ownership is invalid"):
            _verify(request, launch, result, directory_descriptor, descriptors)
        outside_link.unlink()

        with open(quarantine / f"{first}.wav", "r+b") as handle:
            handle.seek(44)
            handle.write(b"\x00")
        with pytest.raises(ValueError, match="hash does not match"):
            _verify(request, launch, result, directory_descriptor, descriptors)
    finally:
        _close_quarantine(directory_descriptor, descriptors)


def test_quarantine_rejects_writable_or_inheritable_descriptor(
    tmp_path: Path,
    fake_records: tuple[Any, Any, Any],
) -> None:
    request, launch, result = fake_records
    quarantine, directory_descriptor, descriptors = _quarantine(
        tmp_path, result
    )
    first = result["outputs"][0]["slot_id"]
    try:
        os.close(descriptors[first])
        descriptors[first] = os.open(
            quarantine / f"{first}.wav", os.O_RDWR | os.O_CLOEXEC
        )
        with pytest.raises(ValueError, match="read-only"):
            _verify(request, launch, result, directory_descriptor, descriptors)
        os.close(descriptors[first])
        descriptors[first] = os.open(
            quarantine / f"{first}.wav", os.O_RDONLY | os.O_CLOEXEC
        )
        os.set_inheritable(descriptors[first], True)
        with pytest.raises(ValueError, match="non-inheritable"):
            _verify(request, launch, result, directory_descriptor, descriptors)
    finally:
        _close_quarantine(directory_descriptor, descriptors)


def test_quarantine_hashing_keeps_offsets_unchanged(
    tmp_path: Path,
    fake_records: tuple[Any, Any, Any],
) -> None:
    request, launch, result = fake_records
    _quarantine_path, directory_descriptor, descriptors = _quarantine(
        tmp_path, result
    )
    try:
        for descriptor in descriptors.values():
            os.lseek(descriptor, 4, os.SEEK_SET)
        _verify(request, launch, result, directory_descriptor, descriptors)
        assert all(
            os.lseek(descriptor, 0, os.SEEK_CUR) == 4
            for descriptor in descriptors.values()
        )
    finally:
        _close_quarantine(directory_descriptor, descriptors)


def test_protocol_module_contains_no_process_model_or_receipt_surface() -> None:
    source = Path(protocol.__file__).read_text(encoding="utf-8")
    forbidden = (
        "posix_spawn",
        "subprocess",
        "waitpid",
        "killpg",
        "torch",
        "muscriptor",
        "pickle.loads",
        "terminal_receipt",
    )
    assert all(value not in source for value in forbidden)
    assert protocol.__all__ == []


def _quarantine(
    root: Path,
    result: Any,
) -> tuple[Path, int, dict[str, int]]:
    quarantine = root / "quarantine"
    quarantine.mkdir(mode=0o700)
    descriptors: dict[str, int] = {}
    for output in result["outputs"]:
        path = quarantine / f"{output['slot_id']}.wav"
        path.write_bytes(bytes.fromhex(output["payload_hex"]))
        path.chmod(0o600)
        descriptors[output["slot_id"]] = os.open(
            path, os.O_RDONLY | os.O_CLOEXEC
        )
    directory = os.open(
        quarantine, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    )
    return quarantine, directory, descriptors


def _verify(
    request: Any,
    launch: Any,
    result: Any,
    directory: int,
    descriptors: dict[str, int],
) -> Any:
    return _verify_fake_worker_quarantine(
        fake_worker_request=request,
        fake_launch_plan=launch,
        fake_worker_result=result,
        quarantine_directory_descriptor=directory,
        readable_descriptors=descriptors,
    )


def _close_quarantine(directory: int, descriptors: dict[str, int]) -> None:
    os.close(directory)
    for descriptor in set(descriptors.values()):
        try:
            os.close(descriptor)
        except OSError:
            pass
