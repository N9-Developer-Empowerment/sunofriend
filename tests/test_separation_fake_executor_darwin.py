from __future__ import annotations

import copy
import json
import os
import pickle
import platform
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import sunofriend
import sunofriend._separation_fake_executor_darwin as executor_module
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

    def fail_release(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic release cleanup failure")

    try:
        monkeypatch.setattr(
            lease_module,
            "_release_separation_checkpoint_descriptor_fd5",
            fail_release,
        )
        with pytest.raises(
            lease_module._FakeExecutionLeaseFailure
        ) as captured:
            lease_module._execute_reserved_fake_worker_under_lock(
                trusted_lease=lease,
                trusted_reservation=reservation,
                trusted_worker_request_v2=worker_v2,
                current_lease_observation=observation,
                fake_worker_request=object(),
                fake_launch_plan_v1=object(),
                blocked_fake_launch_plan_v2=object(),
                fake_launch_plan_v3=object(),
                trusted_native_session=object(),
                native_session_observation=object(),
                private_root=tmp_path / "unused",
            )
        failure = captured.value
        assert isinstance(failure.primary_error, ValueError)
        assert len(failure.cleanup_errors) == 2
        assert isinstance(failure.cleanup_errors[0], RuntimeError)
        assert isinstance(failure.cleanup_errors[1], ValueError)
    finally:
        monkeypatch.setattr(
            lease_module,
            "_release_separation_checkpoint_descriptor_fd5",
            original_release,
        )
        original_release(lease, reservation)
        assert lease_module.close_separation_checkpoint_descriptor_lease(
            lease
        )["status"] == "closed"
        assert fixture["checkpoint"].exists()


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
