from __future__ import annotations

import copy
import errno
import json
import os
import pickle
import platform
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

import sunofriend
import sunofriend._separation_fake_executor_darwin as executor_module
import sunofriend._separation_fake_failure_records as failure_records
import sunofriend._separation_native_failure_records as native_failure_records
import sunofriend._separation_native_session_darwin as session_module
import sunofriend.separation_checkpoint_descriptor_lease as lease_module
from sunofriend._separation_native_session_darwin import (
    _normalise_owned_wait_status,
)


REPOSITORY = Path(__file__).resolve().parents[1]
HARNESS = REPOSITORY / "tests" / "_separation_fake_executor_darwin_harness.py"
EXECUTOR_SOURCE = (
    REPOSITORY
    / "src"
    / "sunofriend"
    / "_separation_fake_executor_darwin.py"
)
_MAXIMUM_STREAM_BYTES = 65_536
_HELPER_TIMEOUT_SECONDS = 40.0


def _direct_children(process_id: int) -> tuple[int, ...]:
    result = subprocess.run(
        ["/usr/bin/pgrep", "-P", str(process_id)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=1,
        env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
    )
    if len(result.stdout) > 4_096:
        raise RuntimeError("fake executor child inventory is too large")
    children: list[int] = []
    for line in result.stdout.splitlines():
        child = int(line)
        if child <= 1:
            raise RuntimeError("fake executor child inventory is invalid")
        children.append(child)
    if len(children) > 64 or len(set(children)) != len(children):
        raise RuntimeError("fake executor child inventory is invalid")
    return tuple(children)


def _kill_helper_tree(process: subprocess.Popen[bytes]) -> None:
    cleanup_errors: list[str] = []
    descendants: list[int] = []
    pending = [process.pid]
    try:
        while pending and len(descendants) <= 64:
            parent = pending.pop()
            try:
                children = _direct_children(parent)
            except (
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                ValueError,
            ) as exc:
                cleanup_errors.append(
                    f"could not inventory children of {parent}: {exc}"
                )
                children = ()
            descendants.extend(children)
            pending.extend(children)
        if pending:
            cleanup_errors.append(
                "fake executor child inventory traversal exceeded 64 entries"
            )
    finally:
        for child in reversed(descendants):
            try:
                os.killpg(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as group_error:
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as direct_error:
                    cleanup_errors.append(
                        "could not kill discovered helper child "
                        f"{child}: group={group_error}; direct={direct_error}"
                    )
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as group_error:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError as direct_error:
                cleanup_errors.append(
                    "could not kill fake executor helper: "
                    f"group={group_error}; direct={direct_error}"
                )
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            cleanup_errors.append("fake executor helper could not be reaped")
    if cleanup_errors:
        raise RuntimeError(
            "fake executor helper cleanup was incomplete: "
            + " | ".join(cleanup_errors)
        )


def _run_bounded_helper(command: list[str]) -> tuple[int, bytes, bytes]:
    process = subprocess.Popen(
        command,
        cwd="/",
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        pass_fds=(),
        start_new_session=True,
        env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
    )
    if process.stdout is None or process.stderr is None:
        _kill_helper_tree(process)
        raise AssertionError("fake executor helper pipes are unavailable")
    streams = {
        process.stdout.fileno(): bytearray(),
        process.stderr.fileno(): bytearray(),
    }
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + _HELPER_TIMEOUT_SECONDS
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("isolated fake executor timed out")
            for key, _events in selector.select(min(0.1, remaining)):
                chunk = os.read(key.fd, 16_384)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = streams[key.fd]
                target.extend(chunk)
                if len(target) > _MAXIMUM_STREAM_BYTES:
                    raise RuntimeError(
                        "isolated fake executor output is too large"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("isolated fake executor did not exit in time")
        return_code = process.wait(timeout=remaining)
        return (
            return_code,
            bytes(streams[process.stdout.fileno()]),
            bytes(streams[process.stderr.fileno()]),
        )
    finally:
        selector.close()
        if process.poll() is None:
            _kill_helper_tree(process)
        process.stdout.close()
        process.stderr.close()


def _decode_canonical_document(payload: bytes) -> dict[str, object]:
    if (
        not payload
        or len(payload) > _MAXIMUM_STREAM_BYTES
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
    ):
        raise AssertionError("fake executor report framing is invalid")

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise AssertionError("fake executor report has duplicate fields")
            result[key] = value
        return result

    document = json.loads(
        payload.decode("ascii"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError(f"fake executor report contains {value}")
        ),
    )
    if not isinstance(document, dict):
        raise AssertionError("fake executor report must be an object")
    canonical = (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )
    if canonical != payload:
        raise AssertionError("fake executor report is not canonical JSON")
    return document


def test_helper_cleanup_kills_root_when_child_inventory_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
        env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
    )

    def fail_inventory(_process_id: int) -> tuple[int, ...]:
        raise RuntimeError("synthetic inventory failure")

    monkeypatch.setattr(
        sys.modules[__name__],
        "_direct_children",
        fail_inventory,
    )
    try:
        with pytest.raises(
            RuntimeError,
            match="synthetic inventory failure",
        ):
            _kill_helper_tree(process)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)


def test_executor_is_private_fake_only_and_does_not_widen_public_lease() -> None:
    source = EXECUTOR_SOURCE.read_text(encoding="utf-8")

    assert executor_module.__all__ == ()
    assert lease_module.CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED is False
    assert "_execute_reserved_separation_fake_worker_darwin" not in (
        lease_module.__all__
    )
    assert not hasattr(sunofriend, "_execute_reserved_fake_worker")
    assert "_separation_fake_executor_darwin" not in (
        REPOSITORY / "src" / "sunofriend" / "cli.py"
    ).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "socket" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "model_imported\": False" in source
    assert "source_audio_read\": False" in source


def test_admission_is_nonconstructible_noncopyable_and_nonserializable() -> None:
    admission_type = executor_module._SeparationFakeExecutionAdmission

    with pytest.raises(TypeError, match="parent-issued"):
        admission_type()
    value = object.__new__(admission_type)
    assert repr(value) == "_SeparationFakeExecutionAdmission()"
    with pytest.raises(TypeError, match="copied"):
        copy.copy(value)
    with pytest.raises(TypeError, match="copied"):
        copy.deepcopy(value)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(value)
    with pytest.raises(ValueError, match="exact fake admission|invalid"):
        executor_module._consume_native_start_admission(
            value,
            trusted_session=object(),  # type: ignore[arg-type]
            fake_launch_plan_v3=object(),  # type: ignore[arg-type]
        )


def test_finish_admission_terminalizes_before_reporting_status_mismatch() -> (
    None
):
    admission = object.__new__(
        executor_module._SeparationFakeExecutionAdmission
    )
    executor_module._ADMISSIONS[admission] = executor_module._AdmissionState(
        owner_pid=os.getpid(),
        trusted_session=object(),  # type: ignore[arg-type]
        fake_launch_plan_v3=object(),  # type: ignore[arg-type]
        run_nonce="a" * 64,
        status="issued",
    )

    with pytest.raises(RuntimeError, match="was not consumed"):
        executor_module._finish_admission(
            admission,
            expected_status="consumed",
        )

    assert admission not in executor_module._ADMISSIONS


def test_admitted_failure_preserves_primary_and_attempts_every_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptors = tuple(
        os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY) for _index in range(4)
    )
    for descriptor in descriptors:
        os.set_inheritable(descriptor, False)
    root, request, result_write, result_read = descriptors
    identities = {
        descriptor: executor_module._descriptor_object_identity(descriptor)
        for descriptor in descriptors
    }
    attempted: list[int] = []
    original_primary = ValueError("synthetic native primary")

    monkeypatch.setattr(
        executor_module,
        "_validate_execution_chain",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        executor_module,
        "_issue_admission",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        executor_module,
        "_admitted_request_frame",
        lambda *_args, **_kwargs: b"frame",
    )
    monkeypatch.setattr(
        executor_module,
        "_prepare_transport",
        lambda *_args, **_kwargs: descriptors,
    )

    def fail_native(*_args: object, **_kwargs: object) -> object:
        raise original_primary

    monkeypatch.setattr(
        executor_module,
        "_execute_verified_native_fake_worker",
        fail_native,
    )
    monkeypatch.setattr(
        executor_module,
        "_finish_admission",
        lambda *_args, **_kwargs: None,
    )

    def close_with_two_failures(
        descriptor: int,
        expected_identity: tuple[int, int],
    ) -> None:
        assert expected_identity == identities[descriptor]
        attempted.append(descriptor)
        if descriptor in {result_read, root}:
            raise RuntimeError(f"synthetic close failure {descriptor}")
        os.close(descriptor)

    monkeypatch.setattr(
        executor_module,
        "_close_descriptor_if_same",
        close_with_two_failures,
    )

    with pytest.raises(
        executor_module._FakeExecutionAdmittedFailure
    ) as captured:
        executor_module._execute_admitted_fake_worker_under_lease(
            lease_bridge_authority=object(),
            trusted_worker_request_v2=object(),  # type: ignore[arg-type]
            current_lease_observation=object(),
            expected_blocked_launch_v2=object(),  # type: ignore[arg-type]
            fake_worker_request=object(),  # type: ignore[arg-type]
            fake_launch_plan_v1=object(),  # type: ignore[arg-type]
            blocked_fake_launch_plan_v2=object(),  # type: ignore[arg-type]
            fake_launch_plan_v3=object(),  # type: ignore[arg-type]
            trusted_native_session=object(),  # type: ignore[arg-type]
            native_session_observation=object(),  # type: ignore[arg-type]
            checkpoint_descriptor=99,
            private_root=tmp_path / "unused",
        )

    failure = captured.value
    assert failure.primary_error is original_primary
    assert attempted == [result_read, result_write, request, root]
    assert failure.cleanup_stages == (
        "result_read_descriptor_close",
        "private_root_descriptor_close",
    )
    assert len(failure.cleanup_errors) == 2
    assert len(failure.descriptor_owners) == 2
    assert failure.private_root_owner is failure.descriptor_owners[1]
    assert all(owner.finalizer.alive for owner in failure.descriptor_owners)
    for owner in failure.descriptor_owners:
        owner.finalizer()
        assert owner.finalizer.alive is False
    for descriptor in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF


def test_authenticated_root_clear_rejects_replaced_admitted_owner() -> None:
    authenticated_owner = executor_module._OwnedDescriptorCleanupBackstop(
        descriptor=41,
        identity=(1, 41),
        stage="private_root_descriptor_close",
    )
    replacement_owner = executor_module._OwnedDescriptorCleanupBackstop(
        descriptor=42,
        identity=(1, 42),
        stage="private_root_descriptor_close",
    )
    admitted = executor_module._FakeExecutionAdmittedFailure(
        primary_error=ValueError("synthetic native primary"),
        cleanup_failures=(),
        private_root_owner=replacement_owner,
        descriptor_owners=(replacement_owner,),
    )
    failure = lease_module._FakeExecutionLeaseFailure(
        primary_error=admitted,
        cleanup_failures=(),
        lease_receipt=None,
        core=None,
    )

    with pytest.raises(RuntimeError, match="owner changed"):
        executor_module._clear_private_root_owner_from_lease_failure(
            failure,
            authenticated_owner,
        )

    assert admitted.private_root_owner is replacement_owner


def test_descriptor_backstop_allocation_must_complete_before_native_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptors = tuple(
        os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY) for _index in range(4)
    )
    for descriptor in descriptors:
        os.set_inheritable(descriptor, False)
    identities = {
        descriptor: executor_module._descriptor_object_identity(descriptor)
        for descriptor in descriptors
    }
    attempted: list[int] = []
    native_started = False
    owner_error = RuntimeError("synthetic root owner allocation failure")

    monkeypatch.setattr(
        executor_module,
        "_validate_execution_chain",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        executor_module,
        "_issue_admission",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        executor_module,
        "_admitted_request_frame",
        lambda *_args, **_kwargs: b"frame",
    )
    monkeypatch.setattr(
        executor_module,
        "_prepare_transport",
        lambda *_args, **_kwargs: descriptors,
    )

    def fail_owner(**_kwargs: object) -> object:
        raise owner_error

    monkeypatch.setattr(
        executor_module,
        "_new_owned_descriptor_cleanup_backstop",
        fail_owner,
    )

    def record_native(*_args: object, **_kwargs: object) -> object:
        nonlocal native_started
        native_started = True
        raise AssertionError("native execution must not start")

    monkeypatch.setattr(
        executor_module,
        "_execute_verified_native_fake_worker",
        record_native,
    )
    monkeypatch.setattr(
        executor_module,
        "_finish_admission",
        lambda *_args, **_kwargs: None,
    )

    def close_all(
        descriptor: int,
        expected_identity: tuple[int, int],
    ) -> None:
        assert expected_identity == identities[descriptor]
        attempted.append(descriptor)
        os.close(descriptor)

    monkeypatch.setattr(
        executor_module,
        "_close_descriptor_if_same",
        close_all,
    )

    with pytest.raises(
        executor_module._FakeExecutionAdmittedFailure
    ) as captured:
        executor_module._execute_admitted_fake_worker_under_lease(
            lease_bridge_authority=object(),
            trusted_worker_request_v2=object(),  # type: ignore[arg-type]
            current_lease_observation=object(),
            expected_blocked_launch_v2=object(),  # type: ignore[arg-type]
            fake_worker_request=object(),  # type: ignore[arg-type]
            fake_launch_plan_v1=object(),  # type: ignore[arg-type]
            blocked_fake_launch_plan_v2=object(),  # type: ignore[arg-type]
            fake_launch_plan_v3=object(),  # type: ignore[arg-type]
            trusted_native_session=object(),  # type: ignore[arg-type]
            native_session_observation=object(),  # type: ignore[arg-type]
            checkpoint_descriptor=99,
            private_root=tmp_path / "unused",
        )

    failure = captured.value
    assert failure.primary_error is owner_error
    assert failure.cleanup_stages == ()
    assert failure.private_root_owner is None
    assert failure.descriptor_owners == ()
    assert native_started is False
    assert attempted == list(reversed(descriptors))
    for descriptor in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF


def test_prearmed_root_survives_later_backstop_allocation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptors = tuple(
        os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY) for _index in range(4)
    )
    for descriptor in descriptors:
        os.set_inheritable(descriptor, False)
    root, _request, _result_write, _result_read = descriptors
    identities = {
        descriptor: executor_module._descriptor_object_identity(descriptor)
        for descriptor in descriptors
    }
    attempted: list[int] = []
    native_started = False
    owner_error = RuntimeError("synthetic later owner allocation failure")
    root_close_error = RuntimeError("synthetic root close failure")

    monkeypatch.setattr(
        executor_module,
        "_validate_execution_chain",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        executor_module,
        "_issue_admission",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        executor_module,
        "_admitted_request_frame",
        lambda *_args, **_kwargs: b"frame",
    )
    monkeypatch.setattr(
        executor_module,
        "_prepare_transport",
        lambda *_args, **_kwargs: descriptors,
    )
    original_new_owner = (
        executor_module._new_owned_descriptor_cleanup_backstop
    )
    owner_calls = 0

    def fail_second_owner(**kwargs: object) -> object:
        nonlocal owner_calls
        owner_calls += 1
        if owner_calls == 2:
            raise owner_error
        return original_new_owner(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        executor_module,
        "_new_owned_descriptor_cleanup_backstop",
        fail_second_owner,
    )

    def record_native(*_args: object, **_kwargs: object) -> object:
        nonlocal native_started
        native_started = True
        raise AssertionError("native execution must not start")

    monkeypatch.setattr(
        executor_module,
        "_execute_verified_native_fake_worker",
        record_native,
    )
    monkeypatch.setattr(
        executor_module,
        "_finish_admission",
        lambda *_args, **_kwargs: None,
    )

    def fail_root_close(
        descriptor: int,
        expected_identity: tuple[int, int],
    ) -> None:
        assert expected_identity == identities[descriptor]
        attempted.append(descriptor)
        if descriptor == root:
            raise root_close_error
        os.close(descriptor)

    monkeypatch.setattr(
        executor_module,
        "_close_descriptor_if_same",
        fail_root_close,
    )

    with pytest.raises(
        executor_module._FakeExecutionAdmittedFailure
    ) as captured:
        executor_module._execute_admitted_fake_worker_under_lease(
            lease_bridge_authority=object(),
            trusted_worker_request_v2=object(),  # type: ignore[arg-type]
            current_lease_observation=object(),
            expected_blocked_launch_v2=object(),  # type: ignore[arg-type]
            fake_worker_request=object(),  # type: ignore[arg-type]
            fake_launch_plan_v1=object(),  # type: ignore[arg-type]
            blocked_fake_launch_plan_v2=object(),  # type: ignore[arg-type]
            fake_launch_plan_v3=object(),  # type: ignore[arg-type]
            trusted_native_session=object(),  # type: ignore[arg-type]
            native_session_observation=object(),  # type: ignore[arg-type]
            checkpoint_descriptor=99,
            private_root=tmp_path / "unused",
        )

    failure = captured.value
    assert failure.primary_error is owner_error
    assert failure.cleanup_stages == ("private_root_descriptor_close",)
    assert failure.cleanup_errors == (root_close_error,)
    assert native_started is False
    assert attempted == list(reversed(descriptors))
    assert len(failure.descriptor_owners) == 1
    root_owner = failure.descriptor_owners[0]
    assert failure.private_root_owner is root_owner
    assert root_owner.descriptor == root
    assert root_owner.finalizer.alive is True
    root_owner.finalizer()
    assert root_owner.finalizer.alive is False
    for descriptor in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF


def test_admitted_success_cleanup_failure_retains_completed_core_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptors = tuple(
        os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY) for _index in range(4)
    )
    for descriptor in descriptors:
        os.set_inheritable(descriptor, False)
    root, request, result_write, result_read = descriptors
    identities = {
        descriptor: executor_module._descriptor_object_identity(descriptor)
        for descriptor in descriptors
    }

    monkeypatch.setattr(
        executor_module,
        "_validate_execution_chain",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        executor_module,
        "_issue_admission",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        executor_module,
        "_admitted_request_frame",
        lambda *_args, **_kwargs: b"frame",
    )
    monkeypatch.setattr(
        executor_module,
        "_prepare_transport",
        lambda *_args, **_kwargs: descriptors,
    )

    def succeed_native(*_args: object, **_kwargs: object) -> object:
        os.close(result_write)
        return object(), object()

    monkeypatch.setattr(
        executor_module,
        "_execute_verified_native_fake_worker",
        succeed_native,
    )
    monkeypatch.setattr(
        executor_module,
        "_finish_admission",
        lambda *_args, **_kwargs: None,
    )

    def fail_result_reader_close(
        descriptor: int,
        expected_identity: tuple[int, int],
    ) -> None:
        assert expected_identity == identities[descriptor]
        if descriptor == result_read:
            raise RuntimeError("synthetic result reader close failure")
        os.close(descriptor)

    monkeypatch.setattr(
        executor_module,
        "_close_descriptor_if_same",
        fail_result_reader_close,
    )

    with pytest.raises(
        executor_module._FakeExecutionAdmittedFailure
    ) as captured:
        executor_module._execute_admitted_fake_worker_under_lease(
            lease_bridge_authority=object(),
            trusted_worker_request_v2=object(),  # type: ignore[arg-type]
            current_lease_observation=object(),
            expected_blocked_launch_v2=object(),  # type: ignore[arg-type]
            fake_worker_request=object(),  # type: ignore[arg-type]
            fake_launch_plan_v1=object(),  # type: ignore[arg-type]
            blocked_fake_launch_plan_v2=object(),  # type: ignore[arg-type]
            fake_launch_plan_v3=object(),  # type: ignore[arg-type]
            trusted_native_session=object(),  # type: ignore[arg-type]
            native_session_observation=object(),  # type: ignore[arg-type]
            checkpoint_descriptor=99,
            private_root=tmp_path / "unused",
        )

    failure = captured.value
    assert failure.primary_error is None
    assert failure.cleanup_stages == ("result_read_descriptor_close",)
    assert (
        type(failure.private_root_owner) is executor_module._FakeExecutionCore
    )
    assert failure.private_root_owner.private_root_finalizer.alive is True
    assert len(failure.descriptor_owners) == 1
    failure.descriptor_owners[0].finalizer()
    failure.private_root_owner.private_root_finalizer()
    for descriptor in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF


def test_lease_bridge_is_nonconstructible_noncopyable_and_nonserializable() -> None:
    bridge_type = lease_module._FakeExecutionLeaseBridgeAuthority

    with pytest.raises(TypeError, match="parent-issued"):
        bridge_type()
    value = object.__new__(bridge_type)
    assert repr(value) == "_FakeExecutionLeaseBridgeAuthority()"
    with pytest.raises(TypeError, match="copied"):
        copy.copy(value)
    with pytest.raises(TypeError, match="copied"):
        copy.deepcopy(value)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(value)
    with pytest.raises(ValueError, match="not registered"):
        lease_module._consume_fake_execution_lease_bridge(
            value,
            trusted_worker_request_v2=object(),  # type: ignore[arg-type]
            current_lease_observation=object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("raw_status", "kind", "exit_code", "signal_number"),
    (
        (0, "exited", 0, None),
        (70 << 8, "exited", 70, None),
        (int(signal.SIGTERM), "signaled", None, int(signal.SIGTERM)),
        (int(signal.SIGKILL), "signaled", None, int(signal.SIGKILL)),
    ),
)
def test_wait_status_normalisation(
    raw_status: int,
    kind: str,
    exit_code: int | None,
    signal_number: int | None,
) -> None:
    result = _normalise_owned_wait_status(raw_status)

    assert result["kind"] == kind
    assert result["exit_code"] == exit_code
    assert result["signal"] == signal_number


@pytest.mark.parametrize("raw_status", [True, -1, 0x1_0000, 0xFFFF])
def test_wait_status_rejects_nonterminal_or_invalid_values(
    raw_status: int,
) -> None:
    with pytest.raises(ValueError):
        _normalise_owned_wait_status(raw_status)


class _FakeNativeOwner:
    def __init__(self) -> None:
        self.signals: list[int] = []
        self.ownership_lost = False
        self.leader_reaped = False
        self.ownership_released = False

    def signal_owned_group(self, signal_number: int) -> None:
        self.signals.append(signal_number)


def test_supervision_escalates_through_term_kill_and_exact_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _FakeNativeOwner()
    observations = iter((None, None, 0))
    monkeypatch.setattr(
        session_module,
        "_poll_native_owner_until",
        lambda _owner, _deadline: next(observations),
    )

    assert session_module._supervise_native_owner(
        owner,
        timeout_ns=0,
        term_grace_ns=0,
        kill_reap_ns=0,
    ) == (0, True, True, True)
    assert owner.signals == [int(signal.SIGTERM), int(signal.SIGKILL)]


def test_supervision_refuses_terminal_claim_when_reap_never_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _FakeNativeOwner()
    monkeypatch.setattr(
        session_module,
        "_poll_native_owner_until",
        lambda _owner, _deadline: None,
    )

    with pytest.raises(RuntimeError, match="did not exact-reap"):
        session_module._supervise_native_owner(
            owner,
            timeout_ns=0,
            term_grace_ns=0,
            kill_reap_ns=0,
        )
    assert owner.signals == [int(signal.SIGTERM), int(signal.SIGKILL)]


def test_supervision_rejects_stolen_child_ownership() -> None:
    owner = _FakeNativeOwner()
    owner.ownership_lost = True

    def reject(_signal_number: int) -> None:
        raise RuntimeError("ownership lost")

    owner.signal_owned_group = reject  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="ownership was lost"):
        session_module._signal_native_owner(owner, signal.SIGKILL)


def test_private_root_must_be_fresh_and_not_a_symlink(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        executor_module._fresh_absolute_path(existing)

    target = tmp_path / "target"
    link = tmp_path / "link"
    target.mkdir()
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(FileExistsError, match="already exists"):
        executor_module._fresh_absolute_path(link)


def test_result_reader_rejects_truncated_or_unframed_data(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.frame"
    result_path.write_bytes(b"not-a-frame")
    descriptor = os.open(result_path, os.O_RDONLY)
    os.set_inheritable(descriptor, False)
    try:
        with pytest.raises(ValueError, match="invalid|truncated"):
            session_module._read_fake_result_v2(
                descriptor,
                fake_launch_plan_v3=object(),  # type: ignore[arg-type]
            )
    finally:
        os.close(descriptor)


def test_lease_bridge_preserves_primary_and_all_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_separation_launch_v2_facade import _prepared

    fixture, lease, observation, worker_v2, reservation = _prepared(tmp_path)
    original_release = (
        lease_module._release_separation_checkpoint_descriptor_fd5
    )
    original_finish = lease_module._finish_fake_execution_lease_bridge

    def fail_release(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic release cleanup failure")

    def fail_finish(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic bridge cleanup failure")

    try:
        monkeypatch.setattr(
            lease_module,
            "_release_separation_checkpoint_descriptor_fd5",
            fail_release,
        )
        monkeypatch.setattr(
            lease_module,
            "_finish_fake_execution_lease_bridge",
            fail_finish,
        )
        with pytest.raises(
            lease_module._FakeExecutionLeaseFailure
        ) as captured:
            lease_module._execute_reserved_fake_worker_under_lock(
                trusted_lease=lease,
                trusted_reservation=reservation,
                trusted_worker_request_v2=worker_v2,
                current_lease_observation=observation,
                fake_worker_request={"request_sha256": "1" * 64},
                fake_launch_plan_v1={"plan_sha256": "2" * 64},
                blocked_fake_launch_plan_v2={"plan_sha256": "3" * 64},
                fake_launch_plan_v3={"plan_sha256": "4" * 64},
                trusted_native_session=object(),
                native_session_observation=object(),
                private_root=tmp_path / "unused",
            )
        failure = captured.value
        assert isinstance(failure.primary_error, ValueError)
        assert failure.cleanup_stages == (
            "lease_bridge_finish",
            "fd5_reservation_release",
        )
        assert len(failure.cleanup_errors) == 2
        assert isinstance(failure.cleanup_errors[0], RuntimeError)
        assert isinstance(failure.cleanup_errors[1], RuntimeError)
        assert failure.lease_receipt is not None
        assert failure.lease_receipt["status"] == "closed"
        assert failure.lease_receipt["cleanup"]["status"] == "complete"
        assert failure.core is None
        assert (
            lease_module.close_separation_checkpoint_descriptor_lease(lease)[
                "receipt_sha256"
            ]
            == failure.lease_receipt["receipt_sha256"]
        )
    finally:
        monkeypatch.setattr(
            lease_module,
            "_release_separation_checkpoint_descriptor_fd5",
            original_release,
        )
        monkeypatch.setattr(
            lease_module,
            "_finish_fake_execution_lease_bridge",
            original_finish,
        )
        assert fixture["checkpoint"].exists()


def test_outer_executor_never_closes_unissued_failure_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    os.set_inheritable(root_descriptor, False)
    root_identity = executor_module._descriptor_object_identity(
        root_descriptor
    )
    core = executor_module._new_fake_execution_core(
        fake_worker_request=object(),  # type: ignore[arg-type]
        fake_launch_plan_v1=object(),  # type: ignore[arg-type]
        blocked_fake_launch_plan_v2=object(),  # type: ignore[arg-type]
        fake_launch_plan_v3=object(),  # type: ignore[arg-type]
        fake_worker_result_v2=object(),  # type: ignore[arg-type]
        native_execution=object(),  # type: ignore[arg-type]
        private_root_descriptor=root_descriptor,
        private_root_identity=root_identity,
    )
    failure = lease_module._FakeExecutionLeaseFailure(
        primary_error=ValueError("synthetic primary"),
        cleanup_failures=(),
        lease_receipt=None,
        core=core,
    )

    def fail_under_lock(**_kwargs: object) -> object:
        raise failure

    close_attempted = False

    def fail_before_close(_core: object) -> None:
        nonlocal close_attempted
        close_attempted = True
        raise RuntimeError("synthetic root close failure")

    monkeypatch.setattr(
        lease_module,
        "_execute_reserved_fake_worker_under_lock",
        fail_under_lock,
    )
    monkeypatch.setattr(
        executor_module,
        "_close_core_private_root_strict",
        fail_before_close,
    )
    with pytest.raises(lease_module._FakeExecutionLeaseFailure) as captured:
        executor_module._execute_reserved_fake_worker(
            trusted_lease=object(),
            trusted_reservation=object(),
            trusted_worker_request_v2=object(),  # type: ignore[arg-type]
            current_lease_observation=object(),
            fake_worker_request=object(),  # type: ignore[arg-type]
            fake_launch_plan_v1=object(),  # type: ignore[arg-type]
            blocked_fake_launch_plan_v2=object(),  # type: ignore[arg-type]
            fake_launch_plan_v3=object(),  # type: ignore[arg-type]
            trusted_native_session=object(),  # type: ignore[arg-type]
            native_session_observation=object(),  # type: ignore[arg-type]
            private_root=tmp_path / "unused-root",
        )
    assert captured.value is failure
    assert failure.core is core
    assert failure.cleanup_stages == ()
    assert failure.cleanup_errors == ()
    assert close_attempted is False
    assert os.fstat(root_descriptor).st_ino == root_identity[1]
    assert core.private_root_finalizer.alive is True
    core.private_root_finalizer()
    assert core.private_root_finalizer.alive is False
    with pytest.raises(OSError) as closed:
        os.fstat(root_descriptor)
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize(
    "native_kind",
    ["exact_reap", "no_start", "no_start_bad_plan"],
)
def test_outer_executor_seals_whole_run_native_failure(
    native_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sunofriend._separation_fake_execution_records import (
        _EXPECTED_FAKE_WORKER_SOURCE_BYTES,
        _EXPECTED_FAKE_WORKER_SOURCE_SHA256,
        _build_prepared_separation_fake_launch_plan_v3_record,
    )
    from sunofriend._separation_fake_launch_v2_records import (
        _build_blocked_separation_fake_launch_plan_v2_record,
    )
    from sunofriend._separation_fake_transport_records import (
        _build_separation_fake_launch_plan,
        _build_separation_fake_worker_request,
    )
    from tests.test_separation_launch_v2_facade import _issue, _prepared

    fixture, lease, observation, worker_v2, reservation = _prepared(
        tmp_path / "lease"
    )
    checkpoint_launch = _issue(
        lease,
        reservation,
        worker_v2,
    )
    fake_worker_request = _build_separation_fake_worker_request(
        worker_request_v2=worker_v2,
        blocked_launch_plan_v2=checkpoint_launch,
        run_nonce="a" * 64,
    )
    fake_launch_plan_v1 = _build_separation_fake_launch_plan(
        fake_worker_request=fake_worker_request,
        runtime_executable_sha256="1" * 64,
        runtime_executable_bytes=4_096,
        fake_worker_sha256=_EXPECTED_FAKE_WORKER_SOURCE_SHA256,
        fake_worker_bytes=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
    )

    def stat_identity(
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

    blocked_fake_launch_plan_v2 = (
        _build_blocked_separation_fake_launch_plan_v2_record(
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            native_launcher_sha256="3" * 64,
            native_launcher_bytes=2_048,
            native_launcher_stat_identity=stat_identity(
                inode=101,
                byte_count=2_048,
                executable=True,
            ),
            runtime_executable_sha256="1" * 64,
            runtime_executable_bytes=4_096,
            runtime_executable_stat_identity=stat_identity(
                inode=102,
                byte_count=4_096,
                executable=True,
            ),
            fake_worker_sha256=_EXPECTED_FAKE_WORKER_SOURCE_SHA256,
            fake_worker_bytes=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
            fake_worker_stat_identity=stat_identity(
                inode=103,
                byte_count=_EXPECTED_FAKE_WORKER_SOURCE_BYTES,
            ),
        )
    )
    fake_launch_plan_v3 = (
        _build_prepared_separation_fake_launch_plan_v3_record(
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
            native_build_receipt_sha256="4" * 64,
        )
    )
    if native_kind == "exact_reap":
        native_observation = (
            native_failure_records._build_exact_reap_failure_observation(
                native_session_observation_sha256="1" * 64,
                fake_launch_plan_v3_sha256=fake_launch_plan_v3[
                    "plan_sha256"
                ],
                failure_stage="result_decode",
                wait={
                    "kind": "exited",
                    "exit_code": 0,
                    "signal": None,
                    "core_dumped": False,
                },
                timed_out=False,
                term_sent=False,
                kill_sent=False,
                fake_worker_result_v2_sha256=None,
                worker_reported_identity_matched=None,
                post_reap_remeasurement_complete=True,
            )
        )
    else:
        observed_plan_sha256 = (
            "f" * 64
            if native_kind == "no_start_bad_plan"
            else fake_launch_plan_v3["plan_sha256"]
        )
        native_observation = (
            native_failure_records._build_no_start_failure_observation(
                native_session_observation_sha256="1" * 64,
                fake_launch_plan_v3_sha256=observed_plan_sha256,
                failure_stage="posix_spawn",
                post_attempt_remeasurement_complete=False,
            )
        )
    original_primary = ValueError("synthetic private primary text")
    native_cleanup = RuntimeError("synthetic native cleanup text")
    admitted_cleanup = RuntimeError("synthetic admitted cleanup text")
    lease_cleanup = RuntimeError("synthetic lease cleanup text")
    if native_kind == "exact_reap":
        native_cleanup_stage = "native_final_supervision"
        native_failure = (
            session_module._VerifiedNativeLauncherExecutionFailure(
                primary_error=original_primary,
                observation=native_observation,  # type: ignore[arg-type]
                cleanup_failures=((native_cleanup_stage, native_cleanup),),
            )
        )
    else:
        class FakeNoStartOutcome:
            pass

        native_cleanup_stage = "native_no_start_remeasurement"
        native_failure = session_module._VerifiedNativeLauncherNoStartFailure(
            native_outcome=FakeNoStartOutcome(),
            no_start_stage="posix_spawn",
            native_status=2,
            observation=native_observation,  # type: ignore[arg-type]
            cleanup_failures=((native_cleanup_stage, native_cleanup),),
        )
    expected_primary = native_failure.primary_error
    root_owner = None
    if native_kind == "no_start":
        root_descriptor = os.open(
            tmp_path,
            os.O_RDONLY | os.O_DIRECTORY,
        )
        os.set_inheritable(root_descriptor, False)
        root_owner = executor_module._new_owned_descriptor_cleanup_backstop(
            descriptor=root_descriptor,
            identity=executor_module._descriptor_object_identity(
                root_descriptor
            ),
            stage="private_root_descriptor_close",
        )
    admitted_failure = executor_module._FakeExecutionAdmittedFailure(
        primary_error=native_failure,
        cleanup_failures=(("request_descriptor_close", admitted_cleanup),),
        private_root_owner=root_owner,
        descriptor_owners=(() if root_owner is None else (root_owner,)),
    )
    original_finish = lease_module._finish_fake_execution_lease_bridge

    def fail_admitted(**kwargs: object) -> object:
        lease_module._consume_fake_execution_lease_bridge(
            kwargs["lease_bridge_authority"],
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
        )
        raise admitted_failure

    monkeypatch.setattr(
        executor_module,
        "_execute_admitted_fake_worker_under_lease",
        fail_admitted,
    )

    def finish_then_fail(authority: object) -> None:
        original_finish(authority)
        raise lease_cleanup

    monkeypatch.setattr(
        lease_module,
        "_finish_fake_execution_lease_bridge",
        finish_then_fail,
    )
    replacement_observation = None
    replacement_primary = None
    if native_kind == "no_start":
        original_close_owner = (
            executor_module._close_private_root_owner_strict
        )
        replacement_observation = (
            native_failure_records._build_no_start_failure_observation(
                native_session_observation_sha256="1" * 64,
                fake_launch_plan_v3_sha256=fake_launch_plan_v3[
                    "plan_sha256"
                ],
                failure_stage="attributes",
                post_attempt_remeasurement_complete=False,
            )
        )
        replacement_primary = RuntimeError(
            "synthetic re-entrant replacement primary"
        )

        def mutate_native_then_close(owner: object) -> None:
            native_failure.observation = replacement_observation
            native_failure.primary_error = replacement_primary
            original_close_owner(owner)  # type: ignore[arg-type]

        monkeypatch.setattr(
            executor_module,
            "_close_private_root_owner_strict",
            mutate_native_then_close,
        )
    expected_failure_type = (
        lease_module._FakeExecutionLeaseFailure
        if native_kind == "no_start_bad_plan"
        else executor_module._SeparationFakeExecutionFailed
    )
    with pytest.raises(expected_failure_type) as captured:
        executor_module._execute_reserved_fake_worker(
            trusted_lease=lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_v2,
            current_lease_observation=observation,
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
            fake_launch_plan_v3=fake_launch_plan_v3,
            trusted_native_session=object(),  # type: ignore[arg-type]
            native_session_observation=object(),  # type: ignore[arg-type]
            private_root=tmp_path / "unused-root",
        )
    failure = captured.value
    if native_kind == "no_start_bad_plan":
        assert type(failure) is lease_module._FakeExecutionLeaseFailure
        assert type(failure._lease_failure_authority) is (
            lease_module._FakeExecutionLeaseFailureAuthority
        )
        assert fixture["checkpoint"].exists()
        return
    assert failure.primary_error is expected_primary
    assert failure.cleanup_stages == (
        native_cleanup_stage,
        "request_descriptor_close",
        "lease_bridge_finish",
    )
    assert failure.cleanup_errors == (
        native_cleanup,
        admitted_cleanup,
        lease_cleanup,
    )
    assert failure.private_root_owner is None
    assert failure.descriptor_owners == (
        () if root_owner is None else (root_owner,)
    )
    assert failure.native_failure_observation is native_observation
    assert failure.lease_terminal_receipt["status"] == "closed"
    assert failure.lease_terminal_receipt["cleanup"]["status"] == "complete"
    if native_kind == "exact_reap":
        receipt = failure_records._validate_failed_terminal_receipt(
            failure.receipt
        )
        assert receipt["status"] == "failed_terminal_with_cleanup_failures"
        assert receipt["process"]["leader_reaped"] is True
    else:
        receipt = (
            failure_records._validate_no_start_failed_terminal_receipt(
                failure.receipt
            )
        )
        assert receipt["status"] == (
            "failed_no_start_with_cleanup_failures"
        )
        assert receipt["process"]["state"] == "not_started"
        assert receipt["process"]["child_created"] is False
        assert receipt["failure"]["primary"]["stage"] == "posix_spawn"
        assert admitted_failure.private_root_owner is None
        assert root_owner is not None
        assert root_owner.finalizer.alive is False
        assert native_failure.observation is replacement_observation
        assert native_failure.primary_error is replacement_primary
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        native_cleanup_stage,
        "request_descriptor_close",
        "lease_bridge_finish",
    ]
    assert receipt["lease"]["status"] == "closed"
    assert "synthetic" not in repr(receipt)
    assert fixture["checkpoint"].exists()


@pytest.mark.trusted_local
@pytest.mark.skipif(
    sys.platform != "darwin" or platform.system() != "Darwin",
    reason="live fake execution requires the audited Darwin launcher",
)
def test_isolated_live_fake_executor_completes_once(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-I",
        "-B",
        str(HARNESS),
        str(tmp_path),
    ]
    return_code, stdout, stderr = _run_bounded_helper(command)

    assert return_code == 0, stderr.decode("utf-8", errors="replace")
    assert stderr == b""
    document = _decode_canonical_document(stdout)
    assert document["status"] == "complete"
    assert document["process"] == {
        "started": True,
        "worker_started": True,
        "exact_owned_child": True,
        "exact_reap": True,
        "normal_exit": True,
        "exit_code": 0,
        "worker_reported_identity_matched": True,
        "timed_out": False,
        "raw_pid_in_terminal_receipt": False,
        "private_result_frame_contains_worker_pid": True,
        "signal_authority_exposed": False,
    }
    assert document["checkpoint"] == {
        "remeasured_before_start": True,
        "fixed_worker_result_reports_checkpoint_remeasured": True,
        "fixed_worker_result_reports_deserialized": False,
        "deserialization_absence_at_exec_proven": False,
        "remeasured_after_reap": True,
        "lease_closed": True,
    }
    assert document["outputs"]["private_quarantine_verified"] is True
    assert document["outputs"]["parent_created_files_exclusively"] is True
    assert (
        document["effects"]["fixed_worker_result_reports_model_imported"]
        is False
    )
    assert (
        document["effects"]["fixed_worker_result_reports_source_audio_read"]
        is False
    )
    assert (
        document["effects"]["fixed_worker_result_reports_network_used"]
        is False
    )
    assert (
        document["effects"]["runtime_and_worker_identity_at_exec_proven"]
        is False
    )
    assert document["effects"]["publication_permitted"] is False
    receipt_payload = dict(document)
    receipt_sha256 = receipt_payload.pop("receipt_sha256")
    assert receipt_sha256 == executor_module._hash(receipt_payload)
    report_text = stdout.decode("ascii")
    assert str(tmp_path) not in report_text
    assert str(REPOSITORY) not in report_text

    execution = tmp_path / "execution"
    transport = execution / "transport"
    quarantine = execution / "quarantine"
    for directory in (execution, transport, quarantine):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700
    for name in ("request.frame", "result.frame"):
        target = transport / name
        assert target.is_file()
        assert target.stat().st_mode & 0o777 == 0o600
        assert target.stat().st_size > 0
    outputs = sorted(quarantine.glob("*.wav"))
    assert outputs
    assert all(
        target.stem.startswith("stem-") and target.stem[5:].isdigit()
        for target in outputs
    )
    for target in outputs:
        assert target.stat().st_mode & 0o777 == 0o600
        assert target.stat().st_size > 44
