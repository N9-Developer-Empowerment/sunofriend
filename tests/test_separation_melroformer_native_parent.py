from __future__ import annotations

from typing import Any

import pytest

import sunofriend._separation_melroformer_native_parent as parent
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
    _build_private_melroformer_native_result,
    _encode_private_melroformer_native_result,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


def _request():
    return _build_private_melroformer_native_request(
        run_nonce="a" * 64,
        paths={
            "repository_root": "/private/tmp/repository",
            "source_root": "/private/tmp/source",
            "checkpoint_path": "/private/tmp/checkpoint.safetensors",
            "companion_root": "/private/tmp/companions",
            "authorisation_report_path": "/private/tmp/authorisation.json",
            "staging_directory": "/private/tmp/staging",
        },
        identities={
            "worker_source_sha256": "1" * 64,
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": "2" * 64,
            "source_manifest_sha256": "3" * 64,
            "companion_manifest_sha256": "4" * 64,
        },
        device="cpu",
    )


class _OwnedSpawnChild:
    __slots__ = (
        "_matched",
        "_wait_status",
        "start_state",
        "leader_exit_observed",
        "leader_reaped",
        "group_empty",
        "ownership_released",
        "ownership_lost",
    )

    def __init__(self) -> None:
        self._matched = False
        self._wait_status = 0
        self.start_state = "started_owned"
        self.leader_exit_observed = False
        self.leader_reaped = False
        self.group_empty = False
        self.ownership_released = False
        self.ownership_lost = False

    def matches_pid_and_pgid(self, pid: int, pgid: int) -> bool:
        self._matched = pid == 7171 and pgid == 7171
        return self._matched

    def wait_nohang(self) -> int:
        return self._wait_status


def _live_observation() -> dict[str, Any]:
    return {
        "process_image_observation_sha256": "5" * 64,
        "network_observation_sha256": "6" * 64,
        "native_image_inventory_sha256": "7" * 64,
        "ready_release_completed": True,
        "raw_pid_or_pgid_retained": False,
        "paths_retained": False,
    }


def _staging_verification() -> dict[str, Any]:
    return {
        "python_import_closure_evidence_sha256": "8" * 64,
        "quarantine_evidence_sha256": "9" * 64,
        "worker_inputs_unchanged": True,
        "private_artifacts_independently_verified": True,
        "paths_retained": False,
    }


def _terminal(owner: _OwnedSpawnChild) -> dict[str, Any]:
    owner.leader_exit_observed = True
    owner.leader_reaped = True
    owner.group_empty = True
    owner.ownership_released = True
    return {
        "wait": {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "leader_exit_observed": True,
        "leader_reaped": True,
        "group_empty": True,
        "ownership_released": True,
        "ownership_lost": False,
    }


def _result_frame(request):
    result = _build_private_melroformer_native_result(
        request=request,
        private_process_identity={"pid": 7171, "pgid": 7171},
        child_result={
            "schema": "test-child.v1",
            "status": "complete",
            "quarantine": {"outputs": ["vocals", "instrumental"]},
        },
    )
    return _encode_private_melroformer_native_result(result, request=request)


def test_dependency_substituted_parent_exercises_exact_safe_order() -> None:
    request = _request()
    owner = _OwnedSpawnChild()
    calls: list[str] = []

    def spawn():
        calls.append("spawn")
        return owner

    def observe(value):
        assert value is owner
        assert value.ownership_released is False
        calls.append("observe_and_release")
        return _live_observation()

    def supervise(value):
        assert value is owner
        calls.append("supervise")
        return _terminal(value)

    def read():
        calls.append("read_result")
        return _result_frame(request)

    def verify(checked_request, child):
        assert checked_request["request_sha256"] == request["request_sha256"]
        assert child["status"] == "complete"
        calls.append("verify_staging")
        return _staging_verification()

    evidence = parent._exercise_dependency_substituted_parent_lifecycle(
        request=request,
        expected_owner_type=_OwnedSpawnChild,
        native_session_observation_sha256="b" * 64,
        spawn_native=spawn,
        observe_and_release=observe,
        supervise_owner=supervise,
        read_result_frame=read,
        verify_private_staging=verify,
    )

    assert calls == [
        "spawn",
        "observe_and_release",
        "supervise",
        "read_result",
        "verify_staging",
    ]
    assert owner._matched is True
    assert evidence["status"] == "dependency_substituted_lifecycle_complete"
    assert evidence["effects"] == {
        "real_native_process_started": False,
        "checkpoint_opened": False,
        "model_imported": False,
        "audio_read": False,
        "filesystem_written": False,
        "network_used": False,
    }
    assert all(value is False for value in evidence["permissions"].values())
    encoded = repr(plain(evidence))
    assert "/private/" not in encoded
    assert "7171" not in encoded
    assert "'pid'" not in encoded
    assert "'pgid'" not in encoded


def test_observer_failure_still_exact_reaps_before_failure() -> None:
    request = _request()
    owner = _OwnedSpawnChild()
    calls: list[str] = []

    def observe(_value):
        calls.append("observe")
        raise RuntimeError("synthetic observer failure")

    def supervise(value):
        calls.append("supervise")
        return _terminal(value)

    with pytest.raises(
        parent._PrivateMelroformerParentLifecycleFailure
    ) as captured:
        parent._exercise_dependency_substituted_parent_lifecycle(
            request=request,
            expected_owner_type=_OwnedSpawnChild,
            native_session_observation_sha256="b" * 64,
            spawn_native=lambda: owner,
            observe_and_release=observe,
            supervise_owner=supervise,
            read_result_frame=lambda: _result_frame(request),
            verify_private_staging=lambda *_args: _staging_verification(),
        )

    assert calls == ["observe", "supervise"]
    assert captured.value.terminal_cleanup_complete is True
    assert isinstance(captured.value.primary_error, RuntimeError)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update(paths_retained=True),
        lambda value: value.update(ready_release_completed=False),
        lambda value: value.update(network_observation_sha256="not-a-hash"),
    ],
)
def test_live_observation_is_fail_closed_and_still_reaped(mutator) -> None:
    request = _request()
    owner = _OwnedSpawnChild()
    reaped: list[bool] = []

    def observe(_value):
        value = _live_observation()
        mutator(value)
        return value

    def supervise(value):
        reaped.append(True)
        return _terminal(value)

    with pytest.raises(parent._PrivateMelroformerParentLifecycleFailure):
        parent._exercise_dependency_substituted_parent_lifecycle(
            request=request,
            expected_owner_type=_OwnedSpawnChild,
            native_session_observation_sha256="b" * 64,
            spawn_native=lambda: owner,
            observe_and_release=observe,
            supervise_owner=supervise,
            read_result_frame=lambda: _result_frame(request),
            verify_private_staging=lambda *_args: _staging_verification(),
        )

    assert reaped == [True]


def test_staging_verification_and_worker_identity_are_mandatory() -> None:
    request = _request()
    owner = _OwnedSpawnChild()
    bad = _staging_verification()
    bad["private_artifacts_independently_verified"] = False

    with pytest.raises(ValueError, match="staging verification is incomplete"):
        parent._exercise_dependency_substituted_parent_lifecycle(
            request=request,
            expected_owner_type=_OwnedSpawnChild,
            native_session_observation_sha256="b" * 64,
            spawn_native=lambda: owner,
            observe_and_release=lambda _owner: _live_observation(),
            supervise_owner=lambda value: _terminal(value),
            read_result_frame=lambda: _result_frame(request),
            verify_private_staging=lambda *_args: bad,
        )

    owner = _OwnedSpawnChild()
    original = _result_frame(request)
    assert original

    def wrong_identity_frame():
        result = _build_private_melroformer_native_result(
            request=request,
            private_process_identity={"pid": 8181, "pgid": 8181},
            child_result={"schema": "test-child.v1", "status": "complete"},
        )
        return _encode_private_melroformer_native_result(result, request=request)

    with pytest.raises(ValueError, match="does not match"):
        parent._exercise_dependency_substituted_parent_lifecycle(
            request=request,
            expected_owner_type=_OwnedSpawnChild,
            native_session_observation_sha256="b" * 64,
            spawn_native=lambda: owner,
            observe_and_release=lambda _owner: _live_observation(),
            supervise_owner=lambda value: _terminal(value),
            read_result_frame=wrong_identity_frame,
            verify_private_staging=lambda *_args: _staging_verification(),
        )
