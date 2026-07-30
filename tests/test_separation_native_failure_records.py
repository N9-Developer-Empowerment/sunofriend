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
