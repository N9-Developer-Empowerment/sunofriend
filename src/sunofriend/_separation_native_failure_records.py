"""Pure path-free failure records for the private Darwin fake launcher.

This module has no process, descriptor, filesystem, model or publication
authority.  It separately seals parent-observed failures after an exact
owned-child reap and code-owned native failures that prove no child started.
Unproven process state intentionally has no constructor here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_worker_request_v2_values import _validate_path_free


__all__: tuple[str, ...] = ()

_SCHEMA = "sunofriend.separation-native-launcher-failed-terminal.v1"
_POLICY_ID = "private-darwin-native-failure-v1"
_NO_START_SCHEMA = "sunofriend.separation-native-launcher-no-start.v1"
_NO_START_POLICY_ID = "private-darwin-native-no-start-v1"
_SHA256 = frozenset("0123456789abcdef")
_FAILURE_STAGES = frozenset(
    {
        "owner_terminality",
        "post_reap_remeasurement",
        "result_decode",
        "result_writer_close",
        "worker_exit",
        "worker_identity",
    }
)
_FIELDS = {
    "schema",
    "policy_id",
    "status",
    "failure_stage",
    "bindings",
    "process",
    "result",
    "post_reap_measurement",
    "permissions",
    "limitations",
    "observation_sha256",
}
_NO_START_STAGES = frozenset(
    {
        "file_actions_init",
        "file_actions",
        "attributes_init",
        "attributes",
        "posix_spawn",
    }
)
_NO_START_FIELDS = {
    "schema",
    "policy_id",
    "status",
    "failure_stage",
    "bindings",
    "process",
    "result",
    "post_attempt_measurement",
    "permissions",
    "limitations",
    "observation_sha256",
}


@dataclass(frozen=True, init=False)
class _VerifiedNativeLauncherFailedTerminalObservation(
    Mapping[str, Any]
):
    """Immutable evidence for a failed attempt with an exact owned reap."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class _VerifiedNativeLauncherNoStartObservation(Mapping[str, Any]):
    """Immutable evidence that the native launcher started no child."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_no_start_failure_observation(
    *,
    native_session_observation_sha256: str,
    fake_launch_plan_v3_sha256: str,
    failure_stage: str,
    post_attempt_remeasurement_complete: bool,
) -> _VerifiedNativeLauncherNoStartObservation:
    """Seal one code-owned native outcome that proves no child started."""

    payload = {
        "schema": _NO_START_SCHEMA,
        "policy_id": _NO_START_POLICY_ID,
        "status": "failed_without_child_start",
        "failure_stage": failure_stage,
        "bindings": {
            "native_session_observation_sha256": (
                native_session_observation_sha256
            ),
            "fake_launch_plan_v3_sha256": fake_launch_plan_v3_sha256,
        },
        "process": {
            "state": "not_started",
            "native_status_nonzero": True,
            "child_created": False,
            "wait_attempted": False,
            "signal_attempted": False,
            "leader_reaped": False,
            "ownership_released": False,
            "ownership_lost": False,
            "raw_pid_in_observation": False,
            "signal_authority_exposed": False,
        },
        "result": {
            "validated": False,
            "fake_worker_result_v2_sha256": None,
            "private_result_frame_contains_worker_pid": False,
        },
        "post_attempt_measurement": {
            "status": (
                "complete"
                if post_attempt_remeasurement_complete
                else "failed"
            ),
            "native_artifact_remeasured": (
                post_attempt_remeasurement_complete
            ),
            "runtime_remeasured": post_attempt_remeasurement_complete,
            "fake_worker_remeasured": post_attempt_remeasurement_complete,
        },
        "permissions": {
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
        "limitations": [
            "native_status_value_retained_privately_not_serialized",
            "nonzero_setup_or_posix_spawn_status_proves_no_child_started",
            "successful_spawn_followed_by_child_exit_127_is_excluded",
            "runtime_exec_and_worker_script_path_toctou_not_eliminated",
            "failure_reason_is_code_owned_stage_not_exception_text",
            "deterministic_fixture_only_no_source_audio_or_model",
        ],
    }
    return _validate_no_start_failure_observation(
        _no_start_wrapper(
            _freeze(
                {
                    **payload,
                    "observation_sha256": _hash(payload),
                }
            )
        )
    )


def _validate_no_start_failure_observation(
    value: Any,
) -> _VerifiedNativeLauncherNoStartObservation:
    """Validate one path-free native no-start observation."""

    if type(value) is not _VerifiedNativeLauncherNoStartObservation:
        raise ValueError("native no-start observation type is invalid")
    document = _plain(value)
    if set(document) != _NO_START_FIELDS:
        raise ValueError("native no-start observation fields are invalid")
    _validate_path_free(document, "native no-start observation")
    if (
        document["schema"] != _NO_START_SCHEMA
        or document["policy_id"] != _NO_START_POLICY_ID
        or document["status"] != "failed_without_child_start"
        or document["failure_stage"] not in _NO_START_STAGES
    ):
        raise ValueError("native no-start policy is invalid")
    bindings = document["bindings"]
    if (
        not isinstance(bindings, dict)
        or set(bindings)
        != {
            "native_session_observation_sha256",
            "fake_launch_plan_v3_sha256",
        }
        or any(not _valid_sha256(item) for item in bindings.values())
    ):
        raise ValueError("native no-start bindings are invalid")
    if document["process"] != {
        "state": "not_started",
        "native_status_nonzero": True,
        "child_created": False,
        "wait_attempted": False,
        "signal_attempted": False,
        "leader_reaped": False,
        "ownership_released": False,
        "ownership_lost": False,
        "raw_pid_in_observation": False,
        "signal_authority_exposed": False,
    }:
        raise ValueError("native no-start process evidence is invalid")
    if document["result"] != {
        "validated": False,
        "fake_worker_result_v2_sha256": None,
        "private_result_frame_contains_worker_pid": False,
    }:
        raise ValueError("native no-start result evidence is invalid")
    measurement = document["post_attempt_measurement"]
    if (
        not isinstance(measurement, dict)
        or set(measurement)
        != {
            "status",
            "native_artifact_remeasured",
            "runtime_remeasured",
            "fake_worker_remeasured",
        }
    ):
        raise ValueError("native no-start remeasurement evidence is invalid")
    remeasured = measurement["status"] == "complete"
    if (
        measurement["status"] not in {"complete", "failed"}
        or any(
            measurement[key] is not remeasured
            for key in (
                "native_artifact_remeasured",
                "runtime_remeasured",
                "fake_worker_remeasured",
            )
        )
    ):
        raise ValueError("native no-start remeasurement evidence is invalid")
    if document["permissions"] != {
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }:
        raise ValueError("native no-start permissions are invalid")
    if document["limitations"] != [
        "native_status_value_retained_privately_not_serialized",
        "nonzero_setup_or_posix_spawn_status_proves_no_child_started",
        "successful_spawn_followed_by_child_exit_127_is_excluded",
        "runtime_exec_and_worker_script_path_toctou_not_eliminated",
        "failure_reason_is_code_owned_stage_not_exception_text",
        "deterministic_fixture_only_no_source_audio_or_model",
    ]:
        raise ValueError("native no-start limitations are invalid")
    observation_sha256 = document["observation_sha256"]
    payload = dict(document)
    payload.pop("observation_sha256")
    if (
        not _valid_sha256(observation_sha256)
        or observation_sha256 != _hash(payload)
    ):
        raise ValueError("native no-start hash is invalid")
    return value


def _build_exact_reap_failure_observation(
    *,
    native_session_observation_sha256: str,
    fake_launch_plan_v3_sha256: str,
    failure_stage: str,
    wait: Mapping[str, Any],
    timed_out: bool,
    term_sent: bool,
    kill_sent: bool,
    fake_worker_result_v2_sha256: str | None,
    worker_reported_identity_matched: bool | None,
    post_reap_remeasurement_complete: bool,
) -> _VerifiedNativeLauncherFailedTerminalObservation:
    """Seal one failure only after the exact native owner reports terminal."""

    result_validated = fake_worker_result_v2_sha256 is not None
    payload = {
        "schema": _SCHEMA,
        "policy_id": _POLICY_ID,
        "status": "failed_after_exact_reap",
        "failure_stage": failure_stage,
        "bindings": {
            "native_session_observation_sha256": (
                native_session_observation_sha256
            ),
            "fake_launch_plan_v3_sha256": fake_launch_plan_v3_sha256,
        },
        "process": {
            "state": "started_exact_reaped",
            "wait": _plain(wait),
            "timed_out": timed_out,
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "leader_reaped": True,
            "ownership_released": True,
            "ownership_lost": False,
            "raw_pid_in_observation": False,
            "signal_authority_exposed": False,
        },
        "result": {
            "validated": result_validated,
            "fake_worker_result_v2_sha256": (
                fake_worker_result_v2_sha256
            ),
            "private_result_frame_contains_worker_pid": result_validated,
            "worker_reported_identity_matched": (
                worker_reported_identity_matched
            ),
        },
        "post_reap_measurement": {
            "status": (
                "complete"
                if post_reap_remeasurement_complete
                else "failed"
            ),
            "native_artifact_remeasured": (
                post_reap_remeasurement_complete
            ),
            "runtime_remeasured": post_reap_remeasurement_complete,
            "fake_worker_remeasured": post_reap_remeasurement_complete,
        },
        "permissions": {
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
        "limitations": [
            "runtime_exec_and_worker_script_path_toctou_not_eliminated",
            "failure_reason_is_code_owned_stage_not_exception_text",
            "result_process_identity_is_worker_report_when_present",
            "deterministic_fixture_only_no_source_audio_or_model",
        ],
    }
    return _validate_exact_reap_failure_observation(
        _wrapper(
            _freeze(
                {
                    **payload,
                    "observation_sha256": _hash(payload),
                }
            )
        )
    )


def _validate_exact_reap_failure_observation(
    value: Any,
) -> _VerifiedNativeLauncherFailedTerminalObservation:
    """Validate one path-free exact-reap failure observation."""

    if type(value) is not _VerifiedNativeLauncherFailedTerminalObservation:
        raise ValueError("native failed terminal observation type is invalid")
    document = _plain(value)
    if set(document) != _FIELDS:
        raise ValueError("native failed terminal observation fields are invalid")
    _validate_path_free(document, "native failed terminal observation")
    if (
        document["schema"] != _SCHEMA
        or document["policy_id"] != _POLICY_ID
        or document["status"] != "failed_after_exact_reap"
        or document["failure_stage"] not in _FAILURE_STAGES
    ):
        raise ValueError("native failed terminal policy is invalid")
    bindings = document["bindings"]
    if (
        not isinstance(bindings, dict)
        or set(bindings)
        != {
            "native_session_observation_sha256",
            "fake_launch_plan_v3_sha256",
        }
        or any(not _valid_sha256(item) for item in bindings.values())
    ):
        raise ValueError("native failed terminal bindings are invalid")
    process = document["process"]
    if (
        not isinstance(process, dict)
        or set(process)
        != {
            "state",
            "wait",
            "timed_out",
            "term_sent",
            "kill_sent",
            "leader_reaped",
            "ownership_released",
            "ownership_lost",
            "raw_pid_in_observation",
            "signal_authority_exposed",
        }
        or process["state"] != "started_exact_reaped"
        or any(
            type(process[key]) is not bool
            for key in ("timed_out", "term_sent", "kill_sent")
        )
        or process["leader_reaped"] is not True
        or process["ownership_released"] is not True
        or process["ownership_lost"] is not False
        or process["raw_pid_in_observation"] is not False
        or process["signal_authority_exposed"] is not False
    ):
        raise ValueError("native failed terminal process evidence is invalid")
    _validate_wait(process["wait"])
    result = document["result"]
    if not isinstance(result, dict) or set(result) != {
        "validated",
        "fake_worker_result_v2_sha256",
        "private_result_frame_contains_worker_pid",
        "worker_reported_identity_matched",
    }:
        raise ValueError("native failed terminal result evidence is invalid")
    result_hash = result["fake_worker_result_v2_sha256"]
    result_validated = result["validated"]
    identity_matched = result["worker_reported_identity_matched"]
    if (
        type(result_validated) is not bool
        or (
            result_hash is not None
            and not _valid_sha256(result_hash)
        )
        or result_validated is not (result_hash is not None)
        or result["private_result_frame_contains_worker_pid"]
        is not result_validated
        or (
            identity_matched is not None
            and type(identity_matched) is not bool
        )
        or (not result_validated and identity_matched is not None)
    ):
        raise ValueError("native failed terminal result evidence is invalid")
    measurement = document["post_reap_measurement"]
    if (
        not isinstance(measurement, dict)
        or set(measurement)
        != {
            "status",
            "native_artifact_remeasured",
            "runtime_remeasured",
            "fake_worker_remeasured",
        }
    ):
        raise ValueError(
            "native failed terminal remeasurement evidence is invalid"
        )
    remeasured = measurement["status"] == "complete"
    if (
        measurement["status"] not in {"complete", "failed"}
        or any(
            measurement[key] is not remeasured
            for key in (
                "native_artifact_remeasured",
                "runtime_remeasured",
                "fake_worker_remeasured",
            )
        )
    ):
        raise ValueError(
            "native failed terminal remeasurement evidence is invalid"
        )
    if document["permissions"] != {
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }:
        raise ValueError("native failed terminal permissions are invalid")
    if document["limitations"] != [
        "runtime_exec_and_worker_script_path_toctou_not_eliminated",
        "failure_reason_is_code_owned_stage_not_exception_text",
        "result_process_identity_is_worker_report_when_present",
        "deterministic_fixture_only_no_source_audio_or_model",
    ]:
        raise ValueError("native failed terminal limitations are invalid")
    observation_sha256 = document["observation_sha256"]
    payload = dict(document)
    payload.pop("observation_sha256")
    if (
        not _valid_sha256(observation_sha256)
        or observation_sha256 != _hash(payload)
    ):
        raise ValueError("native failed terminal hash is invalid")
    return value


def _validate_wait(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "exit_code",
        "signal",
        "core_dumped",
    }:
        raise ValueError("native failed terminal wait evidence is invalid")
    kind = value["kind"]
    exit_code = value["exit_code"]
    signal_number = value["signal"]
    if (
        type(value["core_dumped"]) is not bool
        or (
            kind == "exited"
            and (
                type(exit_code) is not int
                or exit_code < 0
                or exit_code > 255
                or signal_number is not None
                or value["core_dumped"] is not False
            )
        )
        or (
            kind == "signaled"
            and (
                exit_code is not None
                or type(signal_number) is not int
                or signal_number <= 0
                or signal_number > 255
            )
        )
        or kind not in {"exited", "signaled"}
    ):
        raise ValueError("native failed terminal wait evidence is invalid")


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256 for character in value)
    )


def _wrapper(
    document: Mapping[str, Any],
) -> _VerifiedNativeLauncherFailedTerminalObservation:
    value = object.__new__(
        _VerifiedNativeLauncherFailedTerminalObservation
    )
    object.__setattr__(value, "_document", document)
    return value


def _no_start_wrapper(
    document: Mapping[str, Any],
) -> _VerifiedNativeLauncherNoStartObservation:
    value = object.__new__(_VerifiedNativeLauncherNoStartObservation)
    object.__setattr__(value, "_document", document)
    return value
