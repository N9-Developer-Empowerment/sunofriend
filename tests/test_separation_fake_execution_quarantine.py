from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterator

import pytest

import sunofriend
import sunofriend._separation_fake_execution_quarantine as quarantine_module
from sunofriend._separation_checkpoint_canonical import canonical_sha256
from sunofriend._separation_fake_execution_quarantine import (
    _QUARANTINE_V2_SCHEMA,
    _verify_fake_execution_quarantine_v2,
)
from tests.test_separation_fake_execution_records import _execution_records


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = (
    REPOSITORY
    / "src"
    / "sunofriend"
    / "_separation_fake_execution_quarantine.py"
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _records_and_tree(tmp_path: Path):
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )
    directory = tmp_path / "quarantine-v2"
    directory.mkdir(mode=0o700)
    for output in result["outputs"]:
        path = directory / f"{output['slot_id']}.wav"
        path.write_bytes(bytes.fromhex(output["payload_hex"]))
        path.chmod(0o600)
    return request, launch_v1, launch_v2, launch_v3, result, directory


def _opened_tree(
    directory: Path,
    slot_ids: list[str],
) -> Iterator[tuple[int, dict[str, int]]]:
    directory_descriptor = os.open(directory, os.O_RDONLY)
    os.set_inheritable(directory_descriptor, False)
    descriptors: dict[str, int] = {}
    try:
        for slot_id in slot_ids:
            descriptor = os.open(directory / f"{slot_id}.wav", os.O_RDONLY)
            os.set_inheritable(descriptor, False)
            descriptors[slot_id] = descriptor
        yield directory_descriptor, descriptors
    finally:
        for descriptor in descriptors.values():
            os.close(descriptor)
        os.close(directory_descriptor)


def _verify(records: tuple[Any, ...], directory: Path):
    request, launch_v1, launch_v2, launch_v3, result = records
    slot_ids = [item["slot_id"] for item in launch_v3["output_slots"]]
    context = _opened_tree(directory, slot_ids)
    directory_descriptor, descriptors = next(context)
    try:
        return _verify_fake_execution_quarantine_v2(
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
            blocked_fake_launch_plan_v2=launch_v2,
            fake_launch_plan_v3=launch_v3,
            fake_worker_result_v2=result,
            quarantine_directory_descriptor=directory_descriptor,
            readable_descriptors=descriptors,
        )
    finally:
        try:
            next(context)
        except StopIteration:
            pass


def test_v2_quarantine_verifier_is_private_distinct_and_process_free() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert quarantine_module.__all__ == ()
    assert not hasattr(sunofriend, "_verify_fake_execution_quarantine_v2")
    assert "_verify_fake_worker_quarantine(" not in source
    assert "subprocess" not in source
    assert "Popen" not in source
    assert "fork" not in source
    assert "spawn" not in source
    assert "payload_hex" not in source
    assert "write(" not in source
    assert "pwrite(" not in source


def test_v2_quarantine_verifies_exact_tree_hashes_geometry_and_policy(
    tmp_path: Path,
) -> None:
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )
    directory = tmp_path / "quarantine-v2"
    directory.mkdir(mode=0o700)
    for output in result["outputs"]:
        path = directory / f"{output['slot_id']}.wav"
        path.write_bytes(bytes.fromhex(output["payload_hex"]))
        path.chmod(0o600)

    verified = _verify(
        (request, launch_v1, launch_v2, launch_v3, result),
        directory,
    )
    document = _plain(verified)
    verification_sha256 = document.pop("verification_sha256")

    assert verification_sha256 == canonical_sha256(document)
    assert document["schema"] == _QUARANTINE_V2_SCHEMA
    assert document["status"] == "verified"
    assert document["run_nonce"] == launch_v3["run_nonce"]
    assert document["fake_launch_plan_v3_sha256"] == launch_v3["plan_sha256"]
    assert (
        document["fake_worker_result_v2_sha256"] == result["result_sha256"]
    )
    assert document["worker_created_output_files"] is False
    assert document["output_files_observed_by_parent"] is True
    assert document["publication_permitted"] is False
    assert document["selection_permitted"] is False
    assert document["effects"]["files_created"] is False
    assert document["output_count"] == len(result["outputs"])
    assert document["total_bytes"] == sum(
        item["bytes"] for item in result["outputs"]
    )
    assert all(
        item["pcm24_geometry_verified"] is True
        and item["code_owned_fixture_bytes_matched"] is True
        for item in document["outputs"]
    )
    assert not any(
        isinstance(item, str) and item.startswith("/")
        for item in _walk(document)
    )


@pytest.mark.parametrize("mutation", ("extra", "corrupt", "hardlink"))
def test_v2_quarantine_rejects_tree_and_payload_tampering(
    tmp_path: Path,
    mutation: str,
) -> None:
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )
    directory = tmp_path / "quarantine-v2"
    directory.mkdir(mode=0o700)
    paths: list[Path] = []
    for output in result["outputs"]:
        path = directory / f"{output['slot_id']}.wav"
        path.write_bytes(bytes.fromhex(output["payload_hex"]))
        path.chmod(0o600)
        paths.append(path)
    if mutation == "extra":
        (directory / "extra.wav").write_bytes(b"unexpected")
    elif mutation == "corrupt":
        paths[0].write_bytes(b"corrupt")
    else:
        alias = directory / f"{result['outputs'][1]['slot_id']}.wav"
        alias.unlink()
        os.link(paths[0], alias)

    with pytest.raises(ValueError):
        _verify(
            (request, launch_v1, launch_v2, launch_v3, result),
            directory,
        )


def test_v2_quarantine_rejects_inheritable_and_nonexact_descriptors(
    tmp_path: Path,
) -> None:
    request, launch_v1, launch_v2, launch_v3, result, directory = (
        _records_and_tree(tmp_path)
    )
    slot_ids = [item["slot_id"] for item in launch_v3["output_slots"]]
    context = _opened_tree(directory, slot_ids)
    directory_descriptor, descriptors = next(context)
    try:
        os.set_inheritable(descriptors[slot_ids[0]], True)
        with pytest.raises(ValueError, match="non-inheritable"):
            _verify_fake_execution_quarantine_v2(
                fake_worker_request=request,
                fake_launch_plan_v1=launch_v1,
                blocked_fake_launch_plan_v2=launch_v2,
                fake_launch_plan_v3=launch_v3,
                fake_worker_result_v2=result,
                quarantine_directory_descriptor=directory_descriptor,
                readable_descriptors=descriptors,
            )
        os.set_inheritable(descriptors[slot_ids[0]], False)
        with pytest.raises(ValueError, match="exact dictionary"):
            _verify_fake_execution_quarantine_v2(
                fake_worker_request=request,
                fake_launch_plan_v1=launch_v1,
                blocked_fake_launch_plan_v2=launch_v2,
                fake_launch_plan_v3=launch_v3,
                fake_worker_result_v2=result,
                quarantine_directory_descriptor=directory_descriptor,
                readable_descriptors=MappingProxy(descriptors),
            )
    finally:
        try:
            next(context)
        except StopIteration:
            pass


def test_v2_quarantine_rejects_cross_family_and_plain_record_substitution(
    tmp_path: Path,
) -> None:
    first = _execution_records(tmp_path / "first")
    second_root = tmp_path / "second"
    second_root.mkdir()
    second = _execution_records(second_root)
    request, _historical, launch_v1, launch_v2, launch_v3, result = first
    second_request, _second_historical, second_launch_v1, second_launch_v2, *_ = (
        second
    )
    directory = tmp_path / "quarantine-v2"
    directory.mkdir(mode=0o700)
    for output in result["outputs"]:
        path = directory / f"{output['slot_id']}.wav"
        path.write_bytes(bytes.fromhex(output["payload_hex"]))
        path.chmod(0o600)
    slot_ids = [item["slot_id"] for item in launch_v3["output_slots"]]
    context = _opened_tree(directory, slot_ids)
    directory_descriptor, descriptors = next(context)
    try:
        with pytest.raises(ValueError):
            _verify_fake_execution_quarantine_v2(
                fake_worker_request=second_request,
                fake_launch_plan_v1=second_launch_v1,
                blocked_fake_launch_plan_v2=second_launch_v2,
                fake_launch_plan_v3=launch_v3,
                fake_worker_result_v2=result,
                quarantine_directory_descriptor=directory_descriptor,
                readable_descriptors=descriptors,
            )
        with pytest.raises(ValueError, match="exact validated"):
            _verify_fake_execution_quarantine_v2(
                fake_worker_request=request,
                fake_launch_plan_v1=launch_v1,
                blocked_fake_launch_plan_v2=launch_v2,
                fake_launch_plan_v3=_plain(launch_v3),
                fake_worker_result_v2=result,
                quarantine_directory_descriptor=directory_descriptor,
                readable_descriptors=descriptors,
            )
        with pytest.raises(ValueError, match="exact validated"):
            _verify_fake_execution_quarantine_v2(
                fake_worker_request=request,
                fake_launch_plan_v1=launch_v1,
                blocked_fake_launch_plan_v2=launch_v2,
                fake_launch_plan_v3=launch_v3,
                fake_worker_result_v2=_plain(result),
                quarantine_directory_descriptor=directory_descriptor,
                readable_descriptors=descriptors,
            )
    finally:
        try:
            next(context)
        except StopIteration:
            pass


def test_v2_quarantine_rejects_missing_duplicate_and_writable_descriptors(
    tmp_path: Path,
) -> None:
    request, launch_v1, launch_v2, launch_v3, result, directory = (
        _records_and_tree(tmp_path)
    )
    slot_ids = [item["slot_id"] for item in launch_v3["output_slots"]]
    context = _opened_tree(directory, slot_ids)
    directory_descriptor, descriptors = next(context)
    arguments = {
        "fake_worker_request": request,
        "fake_launch_plan_v1": launch_v1,
        "blocked_fake_launch_plan_v2": launch_v2,
        "fake_launch_plan_v3": launch_v3,
        "fake_worker_result_v2": result,
        "quarantine_directory_descriptor": directory_descriptor,
    }
    writable = -1
    try:
        missing = dict(descriptors)
        missing.pop(slot_ids[0])
        with pytest.raises(ValueError, match="every exact output slot"):
            _verify_fake_execution_quarantine_v2(
                **arguments,
                readable_descriptors=missing,
            )
        duplicate = dict(descriptors)
        duplicate[slot_ids[1]] = duplicate[slot_ids[0]]
        with pytest.raises(ValueError, match="distinct"):
            _verify_fake_execution_quarantine_v2(
                **arguments,
                readable_descriptors=duplicate,
            )
        writable = os.open(
            directory / f"{slot_ids[0]}.wav",
            os.O_RDWR,
        )
        os.set_inheritable(writable, False)
        wrong_access = dict(descriptors)
        wrong_access[slot_ids[0]] = writable
        with pytest.raises(ValueError, match="read-only"):
            _verify_fake_execution_quarantine_v2(
                **arguments,
                readable_descriptors=wrong_access,
            )
    finally:
        if writable >= 0:
            os.close(writable)
        try:
            next(context)
        except StopIteration:
            pass


def test_v2_quarantine_rejects_symlink_and_inheritable_directory(
    tmp_path: Path,
) -> None:
    request, launch_v1, launch_v2, launch_v3, result, directory = (
        _records_and_tree(tmp_path)
    )
    slot_ids = [item["slot_id"] for item in launch_v3["output_slots"]]
    target = tmp_path / "external.wav"
    first_path = directory / f"{slot_ids[0]}.wav"
    first_path.replace(target)
    first_path.symlink_to(target)
    context = _opened_tree(directory, slot_ids)
    directory_descriptor, descriptors = next(context)
    arguments = {
        "fake_worker_request": request,
        "fake_launch_plan_v1": launch_v1,
        "blocked_fake_launch_plan_v2": launch_v2,
        "fake_launch_plan_v3": launch_v3,
        "fake_worker_result_v2": result,
        "quarantine_directory_descriptor": directory_descriptor,
        "readable_descriptors": descriptors,
    }
    try:
        with pytest.raises(ValueError, match="exact entry"):
            _verify_fake_execution_quarantine_v2(**arguments)
        first_path.unlink()
        target.replace(first_path)
        os.set_inheritable(directory_descriptor, True)
        with pytest.raises(ValueError, match="directory descriptor"):
            _verify_fake_execution_quarantine_v2(**arguments)
    finally:
        os.set_inheritable(directory_descriptor, False)
        try:
            next(context)
        except StopIteration:
            pass


def test_v2_quarantine_full_hash_preserves_file_descriptor_offsets(
    tmp_path: Path,
) -> None:
    request, launch_v1, launch_v2, launch_v3, result, directory = (
        _records_and_tree(tmp_path)
    )
    slot_ids = [item["slot_id"] for item in launch_v3["output_slots"]]
    context = _opened_tree(directory, slot_ids)
    directory_descriptor, descriptors = next(context)
    offsets = {}
    try:
        for index, (slot_id, descriptor) in enumerate(descriptors.items(), 1):
            offsets[slot_id] = os.lseek(descriptor, index, os.SEEK_SET)
        _verify_fake_execution_quarantine_v2(
            fake_worker_request=request,
            fake_launch_plan_v1=launch_v1,
            blocked_fake_launch_plan_v2=launch_v2,
            fake_launch_plan_v3=launch_v3,
            fake_worker_result_v2=result,
            quarantine_directory_descriptor=directory_descriptor,
            readable_descriptors=descriptors,
        )
        assert {
            slot_id: os.lseek(descriptor, 0, os.SEEK_CUR)
            for slot_id, descriptor in descriptors.items()
        } == offsets
    finally:
        try:
            next(context)
        except StopIteration:
            pass


class MappingProxy(Mapping[str, int]):
    def __init__(self, value: Mapping[str, int]) -> None:
        self._value = dict(value)

    def __getitem__(self, key: str) -> int:
        return self._value[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)


def _walk(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [
            item
            for key, nested in value.items()
            for item in (key, nested, *_walk(nested))
        ]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in (nested, *_walk(nested))]
    return [value]
