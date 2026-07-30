from __future__ import annotations

import ast
import copy
import gc
import os
import pickle
import runpy
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import sunofriend.separation_checkpoint_inspection as inspection_module
import sunofriend.separation_checkpoint_descriptor_lease as lease_module

from sunofriend.separation_checkpoint_descriptor_lease import (
    CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED,
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseError,
    SeparationCheckpointDescriptorLeaseObservation,
    SeparationCheckpointDescriptorLeaseTerminalReceipt,
    acquire_separation_checkpoint_descriptor_lease,
    close_separation_checkpoint_descriptor_lease,
    recheck_separation_checkpoint_descriptor_lease,
)


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict) or hasattr(value, "items"):
        return [
            text
            for key, item in value.items()
            for text in [str(key), *_strings(item)]
        ]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def _fixture(tmp_path: Path) -> dict[str, Any]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_checkpoint_inspection.py"))
    )
    checkpoint_bytes = namespace["_torch_zip"]()
    fixture = namespace["_fixture"](tmp_path, checkpoint_bytes)
    inspection = namespace["_inspect"](fixture)
    return {
        **fixture,
        "checkpoint_bytes": checkpoint_bytes,
        "checkpoint_inspection": inspection,
        "lease_kwargs": namespace["_kwargs"](fixture),
    }


def _acquire(
    fixture: dict[str, Any],
) -> tuple[
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseObservation,
]:
    return acquire_separation_checkpoint_descriptor_lease(
        fixture["worker_request"],
        checkpoint_inspection=fixture["checkpoint_inspection"],
        trusted_checkpoint_inspection=fixture["checkpoint_inspection"],
        **fixture["lease_kwargs"],
    )


def test_live_lease_is_path_free_non_authorising_and_idempotently_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)

    assert type(lease) is SeparationCheckpointDescriptorLease
    assert type(observation) is SeparationCheckpointDescriptorLeaseObservation
    assert CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED is False
    assert observation["status"] == "retained_not_loaded"
    assert observation["execution_supported"] is False
    assert observation["execution_permitted"] is False
    assert observation["selection_permitted"] is False
    assert observation["descriptor"]["retained"] is True
    assert observation["descriptor"]["raw_descriptor_exposed"] is False
    assert observation["effects"]["checkpoint_descriptor_retained"] is True
    assert observation["effects"]["checkpoint_descriptor_closed"] is False
    assert (
        fixture["checkpoint_inspection"]["effects"][
            "checkpoint_descriptor_closed"
        ]
        is True
    )
    assert str(tmp_path) not in repr(lease)
    assert str(tmp_path) not in _strings(observation)

    rechecked = recheck_separation_checkpoint_descriptor_lease(lease)
    assert _plain(rechecked) == _plain(observation)

    receipt = close_separation_checkpoint_descriptor_lease(lease)
    assert type(receipt) is SeparationCheckpointDescriptorLeaseTerminalReceipt
    assert receipt["status"] == "closed"
    assert receipt["execution_supported"] is False
    assert receipt["execution_permitted"] is False
    assert receipt["selection_permitted"] is False
    assert receipt["integrity"]["status"] == "verified_before_close_attempt"
    assert receipt["cleanup"]["status"] == "complete"
    assert receipt["cleanup"]["descriptor_close_call_succeeded"] is True
    assert receipt["effects"]["checkpoint_descriptor_retained"] is False
    assert (
        receipt["effects"]["checkpoint_descriptor_close_call_succeeded"]
        is True
    )
    assert str(tmp_path) not in _strings(receipt)

    repeated = close_separation_checkpoint_descriptor_lease(lease)
    assert _plain(repeated) == _plain(receipt)
    with pytest.raises(
        SeparationCheckpointDescriptorLeaseError,
        match="already terminal",
    ) as terminal:
        recheck_separation_checkpoint_descriptor_lease(lease)
    assert _plain(terminal.value.receipt) == _plain(receipt)


def test_lease_identity_cannot_be_copied_serialized_or_forged(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    try:
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.copy(lease)
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.deepcopy(lease)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(lease)

        forged = object.__new__(SeparationCheckpointDescriptorLease)
        with pytest.raises(ValueError, match="known registered"):
            recheck_separation_checkpoint_descriptor_lease(forged)
        with pytest.raises(ValueError, match="exact parent-issued"):
            recheck_separation_checkpoint_descriptor_lease(  # type: ignore[arg-type]
                observation
            )
    finally:
        close_separation_checkpoint_descriptor_lease(lease)


def test_path_replacement_never_substitutes_bytes_and_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    replacement = fixture["checkpoint"].with_name("replacement.pt")
    replacement.write_bytes(b"x" * len(fixture["checkpoint_bytes"]))
    os.replace(replacement, fixture["checkpoint"])

    with pytest.raises(SeparationCheckpointDescriptorLeaseError) as failure:
        recheck_separation_checkpoint_descriptor_lease(lease)
    receipt = failure.value.receipt
    assert receipt["status"] == "integrity_failed"
    assert receipt["integrity"]["status"] == "failed"
    assert receipt["integrity"]["reasons"]
    assert receipt["cleanup"]["status"] == "complete"
    assert receipt["effects"]["checkpoint_loaded"] is False
    assert _plain(close_separation_checkpoint_descriptor_lease(lease)) == (
        _plain(receipt)
    )


def test_same_size_in_place_mutation_closes_once_and_stays_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    with fixture["checkpoint"].open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 0x01]))
        stream.flush()
        os.fsync(stream.fileno())

    original_close = lease_module.os.close
    close_calls: list[int] = []

    def observed_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(lease_module.os, "close", observed_close)
    with pytest.raises(SeparationCheckpointDescriptorLeaseError) as failure:
        recheck_separation_checkpoint_descriptor_lease(lease)
    receipt = failure.value.receipt
    assert receipt["integrity"]["status"] == "failed"
    assert receipt["integrity"]["reasons"]
    assert receipt["cleanup"]["descriptor_close_call_succeeded"] is True
    assert len(close_calls) == 1

    repeated = close_separation_checkpoint_descriptor_lease(lease)
    assert _plain(repeated) == _plain(receipt)
    assert len(close_calls) == 1


def test_mutate_then_restore_is_detected_by_file_identity(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    with fixture["checkpoint"].open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 0x01]))
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        stream.write(first)
        stream.flush()
        os.fsync(stream.fileno())

    with pytest.raises(SeparationCheckpointDescriptorLeaseError) as failure:
        recheck_separation_checkpoint_descriptor_lease(lease)
    assert failure.value.receipt["integrity"]["status"] == "failed"
    assert failure.value.receipt["integrity"]["reasons"]
    close_separation_checkpoint_descriptor_lease(lease)


@pytest.mark.parametrize("operation", ["recheck", "close"])
def test_parent_pid_mismatch_terminalizes_and_closes_child_local_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    original_pid = lease_module.os.getpid()
    original_close = lease_module.os.close
    close_calls: list[int] = []

    def observed_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(lease_module.os, "close", observed_close)
    monkeypatch.setattr(lease_module.os, "getpid", lambda: original_pid + 1)
    function = (
        recheck_separation_checkpoint_descriptor_lease
        if operation == "recheck"
        else close_separation_checkpoint_descriptor_lease
    )
    with pytest.raises(SeparationCheckpointDescriptorLeaseError) as failure:
        function(lease)
    receipt = failure.value.receipt
    assert receipt["status"] == "integrity_failed"
    assert receipt["integrity"]["reasons"] == (
        "trusted_parent_pid_convention_violated",
    )
    assert receipt["cleanup"]["status"] == "complete"
    assert len(close_calls) == 1

    monkeypatch.setattr(lease_module.os, "getpid", lambda: original_pid)
    assert _plain(close_separation_checkpoint_descriptor_lease(lease)) == (
        _plain(receipt)
    )
    assert len(close_calls) == 1


def test_unconfirmed_close_is_recorded_and_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    original_close = lease_module.os.close
    attempted: list[int] = []

    def failed_close(descriptor: int) -> None:
        attempted.append(descriptor)
        raise OSError("synthetic close failure")

    monkeypatch.setattr(lease_module.os, "close", failed_close)
    with pytest.raises(SeparationCheckpointDescriptorLeaseError) as failure:
        close_separation_checkpoint_descriptor_lease(lease)
    receipt = failure.value.receipt
    assert receipt["status"] == "cleanup_failed"
    assert receipt["integrity"]["status"] == "verified_before_close_attempt"
    assert receipt["cleanup"]["status"] == "close_unconfirmed"
    assert receipt["cleanup"]["descriptor_close_attempted"] is True
    assert receipt["cleanup"]["descriptor_close_call_succeeded"] is False
    assert len(attempted) == 1

    repeated = close_separation_checkpoint_descriptor_lease(lease)
    assert _plain(repeated) == _plain(receipt)
    assert len(attempted) == 1

    monkeypatch.setattr(lease_module.os, "close", original_close)
    original_close(attempted[0])


def test_garbage_collection_finalizer_closes_owned_descriptor_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    reference = weakref.ref(lease)
    original_close = lease_module.os.close
    closed: list[int] = []

    def observed_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(lease_module.os, "close", observed_close)
    del lease
    for _attempt in range(3):
        gc.collect()
        if reference() is None:
            break

    assert reference() is None
    assert len(closed) == 1
    assert observation["status"] == "retained_not_loaded"


def test_active_cap_releases_after_close(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first, _ = _acquire(fixture)
    second, _ = _acquire(fixture)
    try:
        with pytest.raises(ValueError, match="active.*limit"):
            _acquire(fixture)
        close_separation_checkpoint_descriptor_lease(first)
        third, _ = _acquire(fixture)
        close_separation_checkpoint_descriptor_lease(third)
    finally:
        close_separation_checkpoint_descriptor_lease(first)
        close_separation_checkpoint_descriptor_lease(second)


@pytest.mark.parametrize(
    "failure_point",
    ["observation_document", "observation_wrapper"],
)
def test_post_open_acquisition_failure_closes_fd_and_releases_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    fixture = _fixture(tmp_path)
    original_target = getattr(lease_module, f"_{failure_point}")
    original_close_if_owned = lease_module._close_if_owned
    cleaned: list[int] = []

    def fail_observation(_value: Any) -> Any:
        raise RuntimeError("synthetic observation failure")

    def observed_cleanup(
        descriptor: int,
        expected_devino: tuple[int, ...],
    ) -> None:
        cleaned.append(descriptor)
        original_close_if_owned(descriptor, expected_devino)

    monkeypatch.setattr(lease_module, f"_{failure_point}", fail_observation)
    monkeypatch.setattr(lease_module, "_close_if_owned", observed_cleanup)
    with pytest.raises(RuntimeError, match="synthetic observation"):
        _acquire(fixture)
    assert len(cleaned) == 1
    with pytest.raises(OSError):
        os.fstat(cleaned[0])

    monkeypatch.setattr(lease_module, f"_{failure_point}", original_target)
    first, _ = _acquire(fixture)
    second, _ = _acquire(fixture)
    try:
        with pytest.raises(ValueError, match="active.*limit"):
            _acquire(fixture)
    finally:
        close_separation_checkpoint_descriptor_lease(first)
        close_separation_checkpoint_descriptor_lease(second)


def test_ancestor_cleanup_failure_closes_leaf_and_releases_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    original_sequence = inspection_module._close_descriptor_sequence
    original_close = inspection_module.os.close
    checkpoint_stat = fixture["checkpoint"].stat()
    checkpoint_devino = (checkpoint_stat.st_dev, checkpoint_stat.st_ino)
    closed_checkpoint_descriptors: list[int] = []

    def observed_close(descriptor: int) -> None:
        try:
            observed = os.fstat(descriptor)
        except OSError:
            observed = None
        if (
            observed is not None
            and (observed.st_dev, observed.st_ino) == checkpoint_devino
        ):
            closed_checkpoint_descriptors.append(descriptor)
        original_close(descriptor)

    def failed_ancestor_cleanup(
        descriptors: Any,
        *,
        raise_on_error: bool,
    ) -> None:
        original_sequence(descriptors, raise_on_error=False)
        raise ValueError("synthetic ancestor cleanup failure")

    monkeypatch.setattr(inspection_module.os, "close", observed_close)
    monkeypatch.setattr(
        inspection_module,
        "_close_descriptor_sequence",
        failed_ancestor_cleanup,
    )
    with pytest.raises(ValueError, match="synthetic ancestor cleanup"):
        _acquire(fixture)
    assert len(closed_checkpoint_descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(closed_checkpoint_descriptors[0])

    monkeypatch.setattr(
        inspection_module,
        "_close_descriptor_sequence",
        original_sequence,
    )
    monkeypatch.setattr(inspection_module.os, "close", original_close)
    first, _ = _acquire(fixture)
    second, _ = _acquire(fixture)
    try:
        with pytest.raises(ValueError, match="active.*limit"):
            _acquire(fixture)
    finally:
        close_separation_checkpoint_descriptor_lease(first)
        close_separation_checkpoint_descriptor_lease(second)


def test_concurrent_recheck_and_close_never_double_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    original_close = lease_module.os.close
    close_calls: list[int] = []
    call_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def observed_close(descriptor: int) -> None:
        with call_lock:
            close_calls.append(descriptor)
        original_close(descriptor)

    def invoke(name: str) -> tuple[str, str, Any]:
        barrier.wait(timeout=5)
        try:
            result = (
                recheck_separation_checkpoint_descriptor_lease(lease)
                if name == "recheck"
                else close_separation_checkpoint_descriptor_lease(lease)
            )
            return name, "ok", result
        except Exception as exc:
            return name, "error", exc

    monkeypatch.setattr(lease_module.os, "close", observed_close)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(invoke, ("recheck", "close"), timeout=10)
        )

    close_result = next(item for item in results if item[0] == "close")
    assert close_result[1] == "ok"
    assert close_result[2]["status"] == "closed"
    recheck_result = next(item for item in results if item[0] == "recheck")
    if recheck_result[1] == "error":
        assert type(recheck_result[2]) is SeparationCheckpointDescriptorLeaseError
        assert recheck_result[2].receipt["status"] == "closed"
    else:
        assert recheck_result[2]["status"] == "retained_not_loaded"
    assert len(close_calls) == 1
    close_separation_checkpoint_descriptor_lease(lease)
    assert len(close_calls) == 1


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_lease_module_has_no_path_reopen_model_process_network_or_write_api(
) -> None:
    source = Path(lease_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "asyncio",
        "ctypes",
        "http",
        "importlib",
        "multiprocessing",
        "onnxruntime",
        "pickle",
        "requests",
        "runpy",
        "safetensors",
        "socket",
        "subprocess",
        "torch",
        "urllib",
        "zipfile",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "open",
        "os.execl",
        "os.execle",
        "os.execlp",
        "os.execlpe",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.fork",
        "os.forkpty",
        "os.lstat",
        "os.open",
        "os.posix_spawn",
        "os.posix_spawnp",
        "os.stat",
        "os.system",
        "Path.open",
        "Path.read_bytes",
        "Path.read_text",
        "Path.write_bytes",
        "Path.write_text",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            }.intersection(forbidden_imports)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        elif isinstance(node, ast.Call):
            assert _qualified_name(node.func) not in forbidden_calls


def test_v1_binding_and_launch_modules_do_not_import_live_lease() -> None:
    root = Path(lease_module.__file__).parent
    for name in (
        "separation_execution_admission_binding.py",
        "separation_launch_contract.py",
        "separation_worker_contract.py",
    ):
        source = (root / name).read_text(encoding="utf-8")
        assert "separation_checkpoint_descriptor_lease" not in source
