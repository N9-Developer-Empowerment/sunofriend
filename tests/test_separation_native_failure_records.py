from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    deep_freeze,
    plain,
)
from sunofriend import _separation_native_failure_records as records


def _observation() -> (
    records._VerifiedNativeLauncherFailedTerminalObservation
):
    return records._build_exact_reap_failure_observation(
        native_session_observation_sha256="1" * 64,
        fake_launch_plan_v3_sha256="2" * 64,
        failure_stage="worker_exit",
        wait={
            "kind": "exited",
            "exit_code": 7,
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


def _replace(
    value: Mapping[str, Any],
    key: str,
    replacement: Any,
) -> records._VerifiedNativeLauncherFailedTerminalObservation:
    document = plain(value)
    document[key] = replacement
    return records._wrapper(deep_freeze(document))


def test_exact_reap_failure_observation_is_path_free_and_self_hashed() -> None:
    observation = _observation()
    document = plain(observation)
    observation_sha256 = document.pop("observation_sha256")

    assert records.__all__ == ()
    assert document["status"] == "failed_after_exact_reap"
    assert document["failure_stage"] == "worker_exit"
    assert document["process"]["state"] == "started_exact_reaped"
    assert document["process"]["leader_reaped"] is True
    assert document["process"]["raw_pid_in_observation"] is False
    assert document["result"]["validated"] is False
    assert document["permissions"]["publication_permitted"] is False
    assert observation_sha256 == canonical_sha256(document)
    assert not any(
        isinstance(item, str)
        and (
            item.startswith(("/", "~/", "../", "./"))
            or "://" in item
        )
        for item in _values(document)
    )


def test_failure_observation_rejects_unproven_or_tampered_terminality() -> None:
    observation = _observation()
    process = plain(observation["process"])
    process["leader_reaped"] = False
    tampered = _replace(observation, "process", process)

    with pytest.raises(ValueError, match="process evidence"):
        records._validate_exact_reap_failure_observation(tampered)
    with pytest.raises(ValueError, match="stage|policy"):
        records._build_exact_reap_failure_observation(
            native_session_observation_sha256="1" * 64,
            fake_launch_plan_v3_sha256="2" * 64,
            failure_stage="spawn_unproven",
            wait={
                "kind": "exited",
                "exit_code": 1,
                "signal": None,
                "core_dumped": False,
            },
            timed_out=False,
            term_sent=False,
            kill_sent=False,
            fake_worker_result_v2_sha256=None,
            worker_reported_identity_matched=None,
            post_reap_remeasurement_complete=False,
        )


def test_failure_observation_binds_validated_result_without_exposing_pid() -> None:
    observation = records._build_exact_reap_failure_observation(
        native_session_observation_sha256="3" * 64,
        fake_launch_plan_v3_sha256="4" * 64,
        failure_stage="worker_identity",
        wait={
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        timed_out=False,
        term_sent=False,
        kill_sent=False,
        fake_worker_result_v2_sha256="5" * 64,
        worker_reported_identity_matched=False,
        post_reap_remeasurement_complete=True,
    )

    assert observation["result"] == {
        "validated": True,
        "fake_worker_result_v2_sha256": "5" * 64,
        "private_result_frame_contains_worker_pid": True,
        "worker_reported_identity_matched": False,
    }
    process = plain(observation["process"])
    assert "pid" not in process
    assert "pgid" not in process


def test_no_start_observation_is_separate_path_free_and_self_hashed() -> None:
    observation = records._build_no_start_failure_observation(
        native_session_observation_sha256="6" * 64,
        fake_launch_plan_v3_sha256="7" * 64,
        failure_stage="posix_spawn",
        post_attempt_remeasurement_complete=True,
    )
    document = plain(observation)
    observation_sha256 = document.pop("observation_sha256")

    assert type(observation) is records._VerifiedNativeLauncherNoStartObservation
    assert document["schema"] == records._NO_START_SCHEMA
    assert document["status"] == "failed_without_child_start"
    assert document["process"] == {
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
    }
    assert document["result"]["validated"] is False
    assert observation_sha256 == canonical_sha256(document)
    assert not any(
        isinstance(item, str)
        and (
            item.startswith(("/", "~/", "../", "./"))
            or "://" in item
        )
        for item in _values(document)
    )


def test_no_start_observation_rejects_unknown_stage_and_process_mutation() -> None:
    with pytest.raises(ValueError, match="policy"):
        records._build_no_start_failure_observation(
            native_session_observation_sha256="6" * 64,
            fake_launch_plan_v3_sha256="7" * 64,
            failure_stage="child_exit",
            post_attempt_remeasurement_complete=False,
        )

    observation = records._build_no_start_failure_observation(
        native_session_observation_sha256="6" * 64,
        fake_launch_plan_v3_sha256="7" * 64,
        failure_stage="attributes",
        post_attempt_remeasurement_complete=False,
    )
    document = plain(observation)
    document["process"]["child_created"] = True
    document.pop("observation_sha256")
    document["observation_sha256"] = canonical_sha256(document)
    tampered = records._no_start_wrapper(deep_freeze(document))

    with pytest.raises(ValueError, match="process evidence"):
        records._validate_no_start_failure_observation(tampered)


def test_exact_reap_and_no_start_observation_types_are_not_interchangeable() -> None:
    no_start = records._build_no_start_failure_observation(
        native_session_observation_sha256="6" * 64,
        fake_launch_plan_v3_sha256="7" * 64,
        failure_stage="file_actions_init",
        post_attempt_remeasurement_complete=True,
    )

    with pytest.raises(ValueError, match="type"):
        records._validate_exact_reap_failure_observation(no_start)
    with pytest.raises(ValueError, match="type"):
        records._validate_no_start_failure_observation(_observation())


def _values(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [
            item
            for nested in value.values()
            for item in [nested, *_values(nested)]
        ]
    if isinstance(value, (tuple, list)):
        return [item for nested in value for item in _values(nested)]
    return [value]
