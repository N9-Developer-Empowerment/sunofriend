"""Private lease-bound executor for the deterministic Darwin fake worker.

This is a development proof, not source separation.  It can run only the
fixed process-creation-free worker, which hashes but never deserializes one
already-retained checkpoint and emits code-owned two-frame PCM24 fixtures.
No public command imports this module.
"""

from __future__ import annotations

import errno
import os
import re
import stat
import threading
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_checkpoint_launch_v2_records import (
    _SeparationLaunchPlanV2Record,
    _validate_blocked_separation_launch_plan_v2_record_shape,
)
from ._separation_checkpoint_transport_records import (
    SeparationWorkerRequestV2Record,
    _validate_separation_worker_request_v2_record_shape,
)
from ._separation_fake_execution_protocol import (
    _FAKE_EXECUTION_ENVELOPE_SCHEMA,
    _REQUEST_MAGIC_V2,
    _decode_fake_execution_request_frame,
    _encode_frame,
)
from ._separation_fake_execution_quarantine import (
    _SeparationFakeExecutionQuarantineV2Observation,
    _validate_fake_execution_quarantine_v2_observation,
    _verify_fake_execution_quarantine_v2,
)
from ._separation_fake_execution_records import (
    _FAKE_EXECUTION_POLICY_ID,
    _SeparationFakeLaunchPlanV3Record,
    _SeparationFakeWorkerResultV2Record,
    _validate_prepared_separation_fake_launch_plan_v3_record_shape,
    _validate_separation_fake_worker_result_v2_record_shape,
)
from ._separation_fake_launch_v2_records import (
    _SeparationFakeLaunchPlanV2Record,
    _validate_blocked_separation_fake_launch_plan_v2_record_shape,
)
from ._separation_fake_transport_records import (
    _FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
    _validate_fake_launch_plan_shape,
    _validate_fake_worker_request_shape,
)
from ._separation_worker_request_v2_values import _validate_path_free
from ._separation_native_session_darwin import (
    _VerifiedNativeLauncherExecutionObservation,
    _VerifiedNativeLauncherSession,
    _VerifiedNativeLauncherSessionObservation,
    _execute_verified_native_fake_worker,
    _validate_verified_native_launcher_session_observation,
)


__all__: tuple[str, ...] = ()

_TERMINAL_SCHEMA = "sunofriend.separation-fake-execution-terminal.v1"
_TERMINAL_POLICY_ID = "private-lease-bound-fake-execution-v1"
_MATERIALIZATION_SCHEMA = (
    "sunofriend.separation-fake-exclusive-materialization.v1"
)
_EXECUTION_LOCK = threading.RLock()
_REGISTRY_LOCK = threading.RLock()
_USED_NONCES: set[str] = set()
_MAXIMUM_USED_NONCES = 1_024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_NONCE_RE = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_FIELDS = {
    "schema",
    "policy_id",
    "status",
    "evidence_scope",
    "run_nonce",
    "backend_scope",
    "bindings",
    "process",
    "checkpoint",
    "outputs",
    "effects",
    "limitations",
    "receipt_sha256",
}
_TERMINAL_BINDING_FIELDS = {
    "fake_worker_request_v1_sha256",
    "fake_launch_plan_v1_sha256",
    "blocked_fake_launch_plan_v2_sha256",
    "fake_launch_plan_v3_sha256",
    "fake_worker_result_v2_sha256",
    "native_execution_observation_sha256",
    "lease_terminal_receipt_sha256",
    "materialization_observation_sha256",
    "quarantine_verification_sha256",
}


class _SeparationFakeExecutionAdmission:
    """Opaque single-use authority minted only inside the locked bridge."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("fake execution admissions are parent-issued only")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("fake execution admissions cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("fake execution admissions cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("fake execution admissions cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("fake execution admissions cannot be serialized")


@dataclass
class _AdmissionState:
    owner_pid: int
    trusted_session: _VerifiedNativeLauncherSession
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record
    run_nonce: str
    status: str


@dataclass(frozen=True)
class _FakeExecutionCore:
    fake_worker_request: _SeparationFakeWorkerRequestRecord
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record
    fake_worker_result_v2: _SeparationFakeWorkerResultV2Record
    native_execution: _VerifiedNativeLauncherExecutionObservation
    private_root_descriptor: int
    private_root_identity: tuple[int, int]
    private_root_finalizer: weakref.finalize = field(
        init=False,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True, init=False)
class _SeparationFakeExecutionMaterializationObservation(
    Mapping[str, Any]
):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class _SeparationFakeExecutionTerminalReceipt(Mapping[str, Any]):
    """Path-free whole-run evidence; never publication authority."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


_ADMISSIONS: weakref.WeakKeyDictionary[
    _SeparationFakeExecutionAdmission, _AdmissionState
] = weakref.WeakKeyDictionary()


def _execute_reserved_fake_worker(
    *,
    trusted_lease: Any,
    trusted_reservation: Any,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: Any,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    trusted_native_session: _VerifiedNativeLauncherSession,
    native_session_observation: _VerifiedNativeLauncherSessionObservation,
    private_root: str | Path,
) -> _SeparationFakeExecutionTerminalReceipt:
    """Run one exact fake chain through the lease module's locked bridge."""

    root = _fresh_absolute_path(private_root)
    with _EXECUTION_LOCK:
        from . import separation_checkpoint_descriptor_lease as _lease_module

        try:
            core, lease_receipt = (
                _lease_module._execute_reserved_fake_worker_under_lock(
                    trusted_lease=trusted_lease,
                    trusted_reservation=trusted_reservation,
                    trusted_worker_request_v2=trusted_worker_request_v2,
                    current_lease_observation=current_lease_observation,
                    fake_worker_request=fake_worker_request,
                    fake_launch_plan_v1=fake_launch_plan_v1,
                    blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
                    fake_launch_plan_v3=fake_launch_plan_v3,
                    trusted_native_session=trusted_native_session,
                    native_session_observation=native_session_observation,
                    private_root=root,
                )
            )
        except _lease_module._FakeExecutionLeaseFailure as failure:
            failed_core = failure.core
            if type(failed_core) is _FakeExecutionCore:
                try:
                    _close_core_private_root_strict(failed_core)
                except BaseException as cleanup_error:
                    failure._record_cleanup(
                        "private_root_descriptor_close",
                        cleanup_error,
                    )
                else:
                    failure.core = None
            raise
        try:
            materialization, quarantine = (
                _materialize_validated_fake_result_v2(core)
            )
            return _terminal_receipt(
                core=core,
                lease_receipt=lease_receipt,
                materialization=materialization,
                quarantine=quarantine,
            )
        finally:
            _close_core_private_root_strict(core)


def _execute_admitted_fake_worker_under_lease(
    *,
    lease_bridge_authority: Any,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: Any,
    expected_blocked_launch_v2: _SeparationLaunchPlanV2Record,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    trusted_native_session: _VerifiedNativeLauncherSession,
    native_session_observation: _VerifiedNativeLauncherSessionObservation,
    checkpoint_descriptor: int,
    private_root: Path,
) -> _FakeExecutionCore:
    """Called only while the exact lease and global execution locks are held."""

    _validate_execution_chain(
        trusted_worker_request_v2=trusted_worker_request_v2,
        current_lease_observation=current_lease_observation,
        expected_blocked_launch_v2=expected_blocked_launch_v2,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
        fake_launch_plan_v3=fake_launch_plan_v3,
        trusted_native_session=trusted_native_session,
        native_session_observation=native_session_observation,
    )
    admission = _issue_admission(
        lease_bridge_authority=lease_bridge_authority,
        trusted_worker_request_v2=trusted_worker_request_v2,
        current_lease_observation=current_lease_observation,
        trusted_session=trusted_native_session,
        fake_launch_plan_v3=fake_launch_plan_v3,
    )
    descriptors: dict[int, tuple[int, int]] = {}
    try:
        frame = _admitted_request_frame(
            admission,
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
            fake_launch_plan_v3=fake_launch_plan_v3,
        )
        (
            root_descriptor,
            request_descriptor,
            result_write_descriptor,
            result_read_descriptor,
        ) = _prepare_transport(private_root, frame)
        descriptors.update(
            {
                descriptor: _descriptor_object_identity(descriptor)
                for descriptor in (
                    root_descriptor,
                    request_descriptor,
                    result_write_descriptor,
                    result_read_descriptor,
                )
            }
        )
        if (
            type(checkpoint_descriptor) is not int
            or checkpoint_descriptor < 3
            or checkpoint_descriptor in descriptors
        ):
            raise ValueError("live checkpoint descriptor is invalid")
        result, native_execution = _execute_verified_native_fake_worker(
            trusted_native_session,
            trusted_admission=admission,
            fake_launch_plan_v3=fake_launch_plan_v3,
            request_descriptor=request_descriptor,
            owned_result_write_descriptor=result_write_descriptor,
            result_read_descriptor=result_read_descriptor,
            checkpoint_descriptor=checkpoint_descriptor,
        )
        descriptors.pop(result_write_descriptor)
        _finish_admission(admission, expected_status="consumed")
        root_identity = descriptors[root_descriptor]
        core = _new_fake_execution_core(
            fake_worker_request=fake_worker_request,
            fake_launch_plan_v1=fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
            fake_launch_plan_v3=fake_launch_plan_v3,
            fake_worker_result_v2=result,
            native_execution=native_execution,
            private_root_descriptor=root_descriptor,
            private_root_identity=root_identity,
        )
        descriptors.pop(root_descriptor)
        return core
    except BaseException:
        _finish_admission(admission, expected_status=None)
        raise
    finally:
        for descriptor, expected_identity in reversed(
            list(descriptors.items())
        ):
            _close_descriptor_if_same(descriptor, expected_identity)


def _consume_native_start_admission(
    value: Any,
    *,
    trusted_session: _VerifiedNativeLauncherSession,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> None:
    """Consume the exact executor-issued admission immediately before spawn."""

    if type(value) is not _SeparationFakeExecutionAdmission:
        raise ValueError("native start requires an exact fake admission")
    with _REGISTRY_LOCK:
        state = _ADMISSIONS.get(value)
        if (
            type(state) is not _AdmissionState
            or state.owner_pid != os.getpid()
            or state.status != "issued"
            or state.trusted_session is not trusted_session
            or state.fake_launch_plan_v3 is not fake_launch_plan_v3
            or state.run_nonce != fake_launch_plan_v3["run_nonce"]
        ):
            raise ValueError("native start fake admission is invalid")
        state.status = "consumed"


def _validate_execution_chain(
    *,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: Any,
    expected_blocked_launch_v2: _SeparationLaunchPlanV2Record,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    trusted_native_session: _VerifiedNativeLauncherSession,
    native_session_observation: _VerifiedNativeLauncherSessionObservation,
) -> None:
    request_v2 = _validate_separation_worker_request_v2_record_shape(
        trusted_worker_request_v2
    )
    checkpoint_launch = _validate_blocked_separation_launch_plan_v2_record_shape(
        expected_blocked_launch_v2
    )
    request = _validate_fake_worker_request_shape(fake_worker_request)
    launch_v1 = _validate_fake_launch_plan_shape(fake_launch_plan_v1)
    launch_v2 = _validate_blocked_separation_fake_launch_plan_v2_record_shape(
        blocked_fake_launch_plan_v2,
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
    )
    plan = _validate_prepared_separation_fake_launch_plan_v3_record_shape(
        fake_launch_plan_v3,
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
    )
    session_observation = (
        _validate_verified_native_launcher_session_observation(
            trusted_native_session,
            native_session_observation,
        )
    )
    observation = _plain(current_lease_observation)
    bindings = _plain(request["bindings"])
    if (
        checkpoint_launch["bindings"]["worker_request_v2_sha256"]
        != request_v2["request_sha256"]
        or request["historical_design"]["worker_request_v2_sha256"]
        != request_v2["request_sha256"]
        or request["historical_design"]["blocked_launch_plan_v2_sha256"]
        != checkpoint_launch["plan_sha256"]
        or bindings["lease_observation_sha256"]
        != observation["observation_sha256"]
        or bindings["checkpoint_sha256"]
        != observation["bindings"]["checkpoint_sha256"]
        or bindings["checkpoint_bytes"]
        != observation["bindings"]["checkpoint_bytes"]
        or bindings["checkpoint_file_identity_sha256"]
        != observation["bindings"]["checkpoint_file_identity_sha256"]
    ):
        raise ValueError("fake execution checkpoint binding is invalid")
    native = _plain(session_observation["bindings"])
    expected_native_bindings = {
        "native_launcher_sha256": native["native_launcher"]["sha256"],
        "native_launcher_bytes": native["native_launcher"]["bytes"],
        "native_launcher_stat_identity_sha256": native["native_launcher"][
            "stat_identity_sha256"
        ],
        "runtime_executable_sha256": native["runtime_executable"]["sha256"],
        "runtime_executable_bytes": native["runtime_executable"]["bytes"],
        "runtime_executable_stat_identity_sha256": native[
            "runtime_executable"
        ]["stat_identity_sha256"],
        "fake_worker_sha256": native["fake_worker"]["sha256"],
        "fake_worker_bytes": native["fake_worker"]["bytes"],
        "fake_worker_stat_identity_sha256": native["fake_worker"][
            "stat_identity_sha256"
        ],
        "native_build_receipt_sha256": native[
            "native_build_receipt_sha256"
        ],
    }
    if any(
        plan["bindings"][key] != value
        for key, value in expected_native_bindings.items()
    ):
        raise ValueError("fake execution native binding is invalid")


def _issue_admission(
    *,
    lease_bridge_authority: Any,
    trusted_worker_request_v2: SeparationWorkerRequestV2Record,
    current_lease_observation: Any,
    trusted_session: _VerifiedNativeLauncherSession,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> _SeparationFakeExecutionAdmission:
    nonce = fake_launch_plan_v3["run_nonce"]
    from . import separation_checkpoint_descriptor_lease as _lease_module

    _lease_module._consume_fake_execution_lease_bridge(
        lease_bridge_authority,
        trusted_worker_request_v2=trusted_worker_request_v2,
        current_lease_observation=current_lease_observation,
    )
    with _REGISTRY_LOCK:
        if nonce in _USED_NONCES:
            raise ValueError("fake execution run nonce was already consumed")
        if len(_USED_NONCES) >= _MAXIMUM_USED_NONCES:
            raise RuntimeError("fake execution nonce registry is full")
        admission = object.__new__(_SeparationFakeExecutionAdmission)
        state = _AdmissionState(
            owner_pid=os.getpid(),
            trusted_session=trusted_session,
            fake_launch_plan_v3=fake_launch_plan_v3,
            run_nonce=nonce,
            status="issued",
        )
        _ADMISSIONS[admission] = state
        _USED_NONCES.add(nonce)
    return admission


def _finish_admission(
    admission: _SeparationFakeExecutionAdmission,
    *,
    expected_status: str | None,
) -> None:
    with _REGISTRY_LOCK:
        state = _ADMISSIONS.get(admission)
        if type(state) is not _AdmissionState:
            return
        if expected_status is not None and state.status != expected_status:
            raise RuntimeError("fake execution admission was not consumed")
        state.status = "terminal"
        del _ADMISSIONS[admission]


def _admitted_request_frame(
    admission: _SeparationFakeExecutionAdmission,
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
) -> bytes:
    with _REGISTRY_LOCK:
        state = _ADMISSIONS.get(admission)
        if type(state) is not _AdmissionState or state.status != "issued":
            raise ValueError("fake execution admission is unavailable")
    payload = {
        "schema": _FAKE_EXECUTION_ENVELOPE_SCHEMA,
        "policy_id": _FAKE_EXECUTION_POLICY_ID,
        "evidence_scope": "private_development",
        "status": "admitted",
        "backend_scope": "deterministic_transport_fixture_only",
        "test_only_execution_permitted": True,
        "real_separation_permitted": False,
        "run_nonce": fake_launch_plan_v3["run_nonce"],
        "fake_launch_plan_v3_sha256": fake_launch_plan_v3["plan_sha256"],
        "serialized_envelope_is_parent_authority": False,
        "fake_launch_plan_v3": _plain(fake_launch_plan_v3),
    }
    envelope = {**payload, "envelope_sha256": _hash(payload)}
    frame = _encode_frame(
        envelope,
        magic=_REQUEST_MAGIC_V2,
        maximum_frame_bytes=_FAKE_REQUEST_MAXIMUM_FRAME_BYTES,
        label="fake execution request",
    )
    checked = _decode_fake_execution_request_frame(
        frame,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
    )
    if checked["plan_sha256"] != fake_launch_plan_v3["plan_sha256"]:
        raise ValueError("fake execution admitted envelope changed")
    return frame


def _prepare_transport(
    private_root: Path,
    request_frame: bytes,
) -> tuple[int, int, int, int]:
    os.mkdir(private_root, 0o700)
    os.chmod(private_root, 0o700)
    root_descriptor = _open_directory(private_root)
    transport_descriptor: int | None = None
    request_descriptor: int | None = None
    result_write_descriptor: int | None = None
    result_read_descriptor: int | None = None
    try:
        os.mkdir("transport", 0o700, dir_fd=root_descriptor)
        os.chmod(
            "transport",
            0o700,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        transport_descriptor = _open_directory_at(
            root_descriptor,
            "transport",
        )
        request_write = _create_file_at(
            transport_descriptor,
            "request.frame",
        )
        try:
            _write_all(request_write, request_frame)
            os.fsync(request_write)
        finally:
            os.close(request_write)
        request_descriptor = _open_read_at(
            transport_descriptor,
            "request.frame",
        )
        result_write_descriptor = _create_file_at(
            transport_descriptor,
            "result.frame",
        )
        result_read_descriptor = _open_read_at(
            transport_descriptor,
            "result.frame",
        )
        result = (
            root_descriptor,
            request_descriptor,
            result_write_descriptor,
            result_read_descriptor,
        )
        root_descriptor = None
        request_descriptor = None
        result_write_descriptor = None
        result_read_descriptor = None
        return result
    finally:
        _close_descriptors_strict(
            descriptor
            for descriptor in (
                result_read_descriptor,
                result_write_descriptor,
                request_descriptor,
                transport_descriptor,
                root_descriptor,
            )
            if descriptor is not None
        )


def _materialize_validated_fake_result_v2(
    core: _FakeExecutionCore,
) -> tuple[
    _SeparationFakeExecutionMaterializationObservation,
    _SeparationFakeExecutionQuarantineV2Observation,
]:
    result = _validate_separation_fake_worker_result_v2_record_shape(
        core.fake_worker_result_v2,
        fake_launch_plan_v3=core.fake_launch_plan_v3,
    )
    root_descriptor = core.private_root_descriptor
    if (
        _descriptor_object_identity(root_descriptor)
        != core.private_root_identity
    ):
        raise ValueError("fake execution private root identity changed")
    root_facts = os.fstat(root_descriptor)
    if (
        not stat.S_ISDIR(root_facts.st_mode)
        or root_facts.st_uid != os.geteuid()
        or stat.S_IMODE(root_facts.st_mode) & 0o077
    ):
        raise ValueError("fake execution private root ownership changed")
    quarantine_descriptor: int | None = None
    readable: dict[str, int] = {}
    try:
        os.mkdir("quarantine", 0o700, dir_fd=root_descriptor)
        os.chmod(
            "quarantine",
            0o700,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        quarantine_descriptor = _open_directory_at(
            root_descriptor,
            "quarantine",
        )
        created: list[dict[str, Any]] = []
        for output in result["outputs"]:
            slot_id = output["slot_id"]
            name = f"{slot_id}.wav"
            payload = bytes.fromhex(output["payload_hex"])
            descriptor = _create_file_at(quarantine_descriptor, name)
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            readable[slot_id] = _open_read_at(quarantine_descriptor, name)
            facts = os.fstat(readable[slot_id])
            created.append(
                {
                    "slot_id": slot_id,
                    "sha256": output["sha256"],
                    "bytes": output["bytes"],
                    "file_identity_sha256": _stat_identity_sha256(facts),
                }
            )
        quarantine = _verify_fake_execution_quarantine_v2(
            fake_worker_request=core.fake_worker_request,
            fake_launch_plan_v1=core.fake_launch_plan_v1,
            blocked_fake_launch_plan_v2=core.blocked_fake_launch_plan_v2,
            fake_launch_plan_v3=core.fake_launch_plan_v3,
            fake_worker_result_v2=result,
            quarantine_directory_descriptor=quarantine_descriptor,
            readable_descriptors=readable,
        )
        payload = {
            "schema": _MATERIALIZATION_SCHEMA,
            "status": "exclusive_parent_creation_verified",
            "run_nonce": core.fake_launch_plan_v3["run_nonce"],
            "fake_worker_result_v2_sha256": result["result_sha256"],
            "quarantine_verification_sha256": quarantine[
                "verification_sha256"
            ],
            "fresh_private_root_created_exclusively": True,
            "fresh_quarantine_created_exclusively": True,
            "output_files_created_exclusively": True,
            "output_files_created_by_parent": True,
            "worker_created_output_files": False,
            "owner_only_permissions": True,
            "read_only_reopen_verified": True,
            "publication_permitted": False,
            "selection_permitted": False,
            "outputs": created,
        }
        observation = _materialization_observation(
            _freeze(
                {
                    **payload,
                    "observation_sha256": _hash(payload),
                }
            )
        )
        return observation, quarantine
    finally:
        _close_descriptors_strict(
            (
                *readable.values(),
                *(
                    ()
                    if quarantine_descriptor is None
                    else (quarantine_descriptor,)
                ),
            )
        )


def _terminal_receipt(
    *,
    core: _FakeExecutionCore,
    lease_receipt: Mapping[str, Any],
    materialization: _SeparationFakeExecutionMaterializationObservation,
    quarantine: _SeparationFakeExecutionQuarantineV2Observation,
) -> _SeparationFakeExecutionTerminalReceipt:
    result = _validate_separation_fake_worker_result_v2_record_shape(
        core.fake_worker_result_v2,
        fake_launch_plan_v3=core.fake_launch_plan_v3,
    )
    checked_quarantine = _validate_fake_execution_quarantine_v2_observation(
        quarantine,
        fake_launch_plan_v3=core.fake_launch_plan_v3,
        fake_worker_result_v2=result,
    )
    if (
        lease_receipt["status"] != "closed"
        or lease_receipt["cleanup"]["status"] != "complete"
        or core.native_execution["status"] != "verified_after_exact_reap"
        or core.native_execution["wait"]["kind"] != "exited"
        or core.native_execution["wait"]["exit_code"] != 0
    ):
        raise RuntimeError("fake execution terminal prerequisites are invalid")
    bindings = {
        "fake_worker_request_v1_sha256": core.fake_worker_request[
            "request_sha256"
        ],
        "fake_launch_plan_v1_sha256": core.fake_launch_plan_v1["plan_sha256"],
        "blocked_fake_launch_plan_v2_sha256": (
            core.blocked_fake_launch_plan_v2["plan_sha256"]
        ),
        "fake_launch_plan_v3_sha256": core.fake_launch_plan_v3["plan_sha256"],
        "fake_worker_result_v2_sha256": result["result_sha256"],
        "native_execution_observation_sha256": core.native_execution[
            "observation_sha256"
        ],
        "lease_terminal_receipt_sha256": lease_receipt["receipt_sha256"],
        "materialization_observation_sha256": materialization[
            "observation_sha256"
        ],
        "quarantine_verification_sha256": checked_quarantine[
            "verification_sha256"
        ],
    }
    payload = {
        "schema": _TERMINAL_SCHEMA,
        "policy_id": _TERMINAL_POLICY_ID,
        "status": "complete",
        "evidence_scope": "private_deterministic_transport_execution",
        "run_nonce": core.fake_launch_plan_v3["run_nonce"],
        "backend_scope": "deterministic_transport_fixture_only",
        "bindings": bindings,
        "process": {
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
        },
        "checkpoint": {
            "remeasured_before_start": True,
            "fixed_worker_result_reports_checkpoint_remeasured": True,
            "fixed_worker_result_reports_deserialized": False,
            "deserialization_absence_at_exec_proven": False,
            "remeasured_after_reap": True,
            "lease_closed": True,
        },
        "outputs": {
            "worker_payloads_validated": True,
            "worker_created_files": False,
            "parent_created_files_exclusively": True,
            "private_quarantine_verified": True,
            "publication_permitted": False,
            "selection_permitted": False,
        },
        "effects": {
            "filesystem_accessed": True,
            "process_started": True,
            "worker_started": True,
            "fixed_worker_result_reports_checkpoint_remeasured_in_child": True,
            "fixed_worker_result_reports_checkpoint_deserialized": False,
            "fixed_worker_result_reports_model_imported": False,
            "fixed_worker_result_reports_inference_started": False,
            "fixed_worker_result_reports_network_used": False,
            "fixed_worker_result_reports_source_audio_read": False,
            "runtime_and_worker_identity_at_exec_proven": False,
            "output_payloads_generated": True,
            "output_files_created_by_parent": True,
            "quarantine_created": True,
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
        "limitations": [
            "deterministic_code_owned_fixture_only",
            "no_source_audio_model_inference_or_real_separation",
            "runtime_exec_and_worker_script_path_toctou_not_eliminated",
            "lease_receipt_effects_are_checkpoint_scope_not_whole_run_scope",
            "ordinary_quarantine_files_can_change_after_verification",
            "no_public_cli_tui_selection_or_publication_route",
        ],
    }
    return _validate_fake_execution_terminal_receipt(
        _terminal_wrapper(
            _freeze({**payload, "receipt_sha256": _hash(payload)})
        )
    )


def _validate_fake_execution_terminal_receipt(
    value: Any,
) -> _SeparationFakeExecutionTerminalReceipt:
    """Validate one whole-run receipt without granting further authority."""

    if type(value) is not _SeparationFakeExecutionTerminalReceipt:
        raise ValueError("fake execution terminal receipt type is invalid")
    document = _plain(value)
    if set(document) != _TERMINAL_FIELDS:
        raise ValueError("fake execution terminal receipt fields are invalid")
    _validate_path_free(document, "fake execution terminal receipt")
    if (
        document["schema"] != _TERMINAL_SCHEMA
        or document["policy_id"] != _TERMINAL_POLICY_ID
        or document["status"] != "complete"
        or document["evidence_scope"]
        != "private_deterministic_transport_execution"
        or document["backend_scope"]
        != "deterministic_transport_fixture_only"
        or not isinstance(document["run_nonce"], str)
        or _RUN_NONCE_RE.fullmatch(document["run_nonce"]) is None
    ):
        raise ValueError("fake execution terminal receipt policy is invalid")
    bindings = document["bindings"]
    if (
        not isinstance(bindings, dict)
        or set(bindings) != _TERMINAL_BINDING_FIELDS
        or any(
            not isinstance(item, str)
            or _SHA256_RE.fullmatch(item) is None
            for item in bindings.values()
        )
    ):
        raise ValueError("fake execution terminal bindings are invalid")
    if document["process"] != {
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
    }:
        raise ValueError("fake execution terminal process evidence is invalid")
    if document["checkpoint"] != {
        "remeasured_before_start": True,
        "fixed_worker_result_reports_checkpoint_remeasured": True,
        "fixed_worker_result_reports_deserialized": False,
        "deserialization_absence_at_exec_proven": False,
        "remeasured_after_reap": True,
        "lease_closed": True,
    }:
        raise ValueError(
            "fake execution terminal checkpoint evidence is invalid"
        )
    if document["outputs"] != {
        "worker_payloads_validated": True,
        "worker_created_files": False,
        "parent_created_files_exclusively": True,
        "private_quarantine_verified": True,
        "publication_permitted": False,
        "selection_permitted": False,
    }:
        raise ValueError("fake execution terminal output evidence is invalid")
    if document["effects"] != {
        "filesystem_accessed": True,
        "process_started": True,
        "worker_started": True,
        "fixed_worker_result_reports_checkpoint_remeasured_in_child": True,
        "fixed_worker_result_reports_checkpoint_deserialized": False,
        "fixed_worker_result_reports_model_imported": False,
        "fixed_worker_result_reports_inference_started": False,
        "fixed_worker_result_reports_network_used": False,
        "fixed_worker_result_reports_source_audio_read": False,
        "runtime_and_worker_identity_at_exec_proven": False,
        "output_payloads_generated": True,
        "output_files_created_by_parent": True,
        "quarantine_created": True,
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }:
        raise ValueError("fake execution terminal effects are invalid")
    if document["limitations"] != [
        "deterministic_code_owned_fixture_only",
        "no_source_audio_model_inference_or_real_separation",
        "runtime_exec_and_worker_script_path_toctou_not_eliminated",
        "lease_receipt_effects_are_checkpoint_scope_not_whole_run_scope",
        "ordinary_quarantine_files_can_change_after_verification",
        "no_public_cli_tui_selection_or_publication_route",
    ]:
        raise ValueError(
            "fake execution terminal limitations are invalid"
        )
    receipt_sha256 = document["receipt_sha256"]
    if (
        not isinstance(receipt_sha256, str)
        or _SHA256_RE.fullmatch(receipt_sha256) is None
    ):
        raise ValueError("fake execution terminal hash is invalid")
    payload = dict(document)
    payload.pop("receipt_sha256")
    if receipt_sha256 != _hash(payload):
        raise ValueError("fake execution terminal hash is invalid")
    return value


def _fresh_absolute_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("fake execution private root must be absolute")
    parent = path.parent.resolve(strict=True)
    result = parent / path.name
    if result.exists() or result.is_symlink():
        raise FileExistsError("fake execution private root already exists")
    return result


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    os.set_inheritable(descriptor, False)
    facts = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(facts.st_mode)
        or facts.st_uid != os.geteuid()
        or stat.S_IMODE(facts.st_mode) & 0o077
    ):
        os.close(descriptor)
        raise ValueError("fake execution directory ownership is invalid")
    return descriptor


def _open_directory_at(parent_descriptor: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    os.set_inheritable(descriptor, False)
    return descriptor


def _create_file_at(directory_descriptor: int, name: str) -> int:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
    )
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_descriptor)
    os.set_inheritable(descriptor, False)
    os.fchmod(descriptor, 0o600)
    return descriptor


def _open_read_at(directory_descriptor: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    os.set_inheritable(descriptor, False)
    return descriptor


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("fake execution write did not progress")
        offset += written


def _stat_identity_sha256(value: os.stat_result) -> str:
    return _hash(
        {
            "device": value.st_dev,
            "inode": value.st_ino,
            "mode": value.st_mode,
            "links": value.st_nlink,
            "owner": value.st_uid,
            "group": value.st_gid,
            "bytes": value.st_size,
            "modified_ns": value.st_mtime_ns,
            "changed_ns": value.st_ctime_ns,
        }
    )


def _descriptor_object_identity(descriptor: int) -> tuple[int, int]:
    facts = os.fstat(descriptor)
    return facts.st_dev, facts.st_ino


def _close_descriptor_if_same(
    descriptor: int,
    expected_identity: tuple[int, int],
) -> None:
    try:
        facts = os.fstat(descriptor)
    except OSError as exc:
        if exc.errno == errno.EBADF:
            return
        raise
    if (facts.st_dev, facts.st_ino) != expected_identity:
        raise RuntimeError("owned fake execution descriptor identity changed")
    os.close(descriptor)


def _finalize_root_descriptor(
    descriptor: int,
    expected_identity: tuple[int, int],
) -> None:
    """Best-effort leak backstop; never accepted as terminal evidence."""

    try:
        facts = os.fstat(descriptor)
        if (facts.st_dev, facts.st_ino) == expected_identity:
            os.close(descriptor)
    except BaseException:
        pass


def _new_fake_execution_core(
    **values: Any,
) -> _FakeExecutionCore:
    core = _FakeExecutionCore(**values)
    object.__setattr__(
        core,
        "private_root_finalizer",
        weakref.finalize(
            core,
            _finalize_root_descriptor,
            core.private_root_descriptor,
            core.private_root_identity,
        ),
    )
    return core


def _close_core_private_root_strict(core: _FakeExecutionCore) -> None:
    if (
        type(core) is not _FakeExecutionCore
        or not hasattr(core, "private_root_finalizer")
        or not core.private_root_finalizer.alive
    ):
        raise RuntimeError("fake execution private root owner is unavailable")
    _close_descriptor_if_same(
        core.private_root_descriptor,
        core.private_root_identity,
    )
    core.private_root_finalizer.detach()


def _close_descriptors_strict(descriptors: Any) -> None:
    failures: list[OSError] = []
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                failures.append(exc)
    if failures:
        raise RuntimeError(
            "fake execution descriptor cleanup failed"
        ) from failures[0]


def _materialization_observation(
    document: Mapping[str, Any],
) -> _SeparationFakeExecutionMaterializationObservation:
    value = object.__new__(_SeparationFakeExecutionMaterializationObservation)
    object.__setattr__(value, "_document", document)
    return value


def _terminal_wrapper(
    document: Mapping[str, Any],
) -> _SeparationFakeExecutionTerminalReceipt:
    value = object.__new__(_SeparationFakeExecutionTerminalReceipt)
    object.__setattr__(value, "_document", document)
    return value
