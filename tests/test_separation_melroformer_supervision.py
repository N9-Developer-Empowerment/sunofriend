from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import sunofriend._separation_melroformer_supervision as supervision
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_real_worker_supervision_is_path_free_and_frozen() -> None:
    evidence = supervision._build_real_worker_supervision_observation(
        worker_signal_state=supervision._expected_post_cpython_signal_state(),
        outer_open_descriptors=[0, 1, 2],
        child_returncode=0,
    )

    assert evidence["status"] == "real_worker_supervision_bound_complete"
    assert evidence["outer_supervisor"]["open_descriptors"] == (0, 1, 2)
    assert evidence["terminal"]["exact_child_reaped"] is True
    assert evidence["terminal"]["process_group_supervision_bound"] is False
    assert evidence["scope"]["product_authority_granted"] is False
    assert "/Users/" not in repr(evidence)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("signal", "post-CPython signal state differs"),
        ("descriptor", "inherited unexpected descriptors"),
        ("returncode", "did not exit normally"),
    ],
)
def test_real_worker_supervision_rejects_boundary_drift(
    mutation: str,
    message: str,
) -> None:
    signal_state = supervision._expected_post_cpython_signal_state()
    descriptors = [0, 1, 2]
    returncode = 0
    if mutation == "signal":
        signal_state["handlers"]["SIGTERM"] = "ignored"
    elif mutation == "descriptor":
        descriptors.append(9)
    else:
        returncode = -15

    with pytest.raises(ValueError, match=message):
        supervision._build_real_worker_supervision_observation(
            worker_signal_state=signal_state,
            outer_open_descriptors=descriptors,
            child_returncode=returncode,
        )


def test_real_worker_supervision_self_hash_rejects_tampering() -> None:
    evidence = plain(
        supervision._build_real_worker_supervision_observation(
            worker_signal_state=supervision._expected_post_cpython_signal_state(),
            outer_open_descriptors=[0, 1, 2],
            child_returncode=0,
        )
    )
    evidence["terminal"]["process_group_supervision_bound"] = True
    unsigned = dict(evidence)
    unsigned.pop("observation_sha256")
    evidence["observation_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()

    with pytest.raises(ValueError, match="terminal evidence differs"):
        supervision._validate_real_worker_supervision_observation(evidence)


def test_real_worker_supervision_has_no_product_route() -> None:
    assert "private-melroformer-supervision" not in PUBLIC_COMMANDS
    assert "private-melroformer-supervision" not in DIRECT_TUI_COMMANDS


def _complete_native_terminal_projection() -> dict[str, object]:
    return {
        "schema": supervision.NATIVE_TERMINAL_PROJECTION_SCHEMA,
        "native_session_observation_sha256": "1" * 64,
        "native_execution_observation_sha256": "2" * 64,
        "worker_result_sha256": "3" * 64,
        "start_state": "started_owned",
        "wait": {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "worker_reported_identity_matched": True,
        "leader_exit_observed": True,
        "leader_reaped": True,
        "group_empty": True,
        "ownership_released": True,
        "ownership_lost": False,
        "raw_pid_retained": False,
        "raw_pgid_retained": False,
        "signal_authority_exposed": False,
    }


def test_native_real_worker_terminal_projection_requires_complete_safe_state() -> None:
    projection = supervision._validate_native_terminal_projection(
        _complete_native_terminal_projection()
    )

    assert projection["leader_exit_observed"] is True
    assert projection["group_empty"] is True
    assert projection["ownership_released"] is True
    assert projection["raw_pid_retained"] is False


def test_model_free_terminal_projection_is_derived_from_exact_owner() -> None:
    owner_type = type(
        "_OwnedSpawnChild",
        (),
        {
            "__module__": "_separation_native_spawn_darwin",
            "__slots__": (),
            "start_state": "started_owned",
            "leader_exit_observed": True,
            "leader_reaped": True,
            "group_empty": True,
            "ownership_released": True,
            "ownership_lost": False,
            "matches_pid_and_pgid": lambda self, pid, pgid: (
                pid == 123 and pgid == 123
            ),
            "wait_nohang": lambda self: 0,
        },
    )
    owner = owner_type()

    projection = supervision._derive_model_free_native_terminal_projection(
        native_owner=owner,
        expected_owner_type=owner_type,
        native_session_observation_sha256="1" * 64,
        native_execution_observation_sha256="2" * 64,
        worker_result_sha256="3" * 64,
        worker_reported_pid=123,
        worker_reported_pgid=123,
    )

    assert projection["worker_reported_identity_matched"] is True
    assert projection["leader_reaped"] is True
    assert projection["group_empty"] is True
    assert projection["raw_pid_retained"] is False
    assert projection["raw_pgid_retained"] is False


def test_model_free_terminal_projection_rejects_wrong_worker_identity() -> None:
    owner_type = type(
        "_OwnedSpawnChild",
        (),
        {
            "__module__": "_separation_native_spawn_darwin",
            "__slots__": (),
            "matches_pid_and_pgid": lambda self, pid, pgid: False,
        },
    )

    with pytest.raises(ValueError, match="identity does not match"):
        supervision._derive_model_free_native_terminal_projection(
            native_owner=owner_type(),
            expected_owner_type=owner_type,
            native_session_observation_sha256="1" * 64,
            native_execution_observation_sha256="2" * 64,
            worker_result_sha256="3" * 64,
            worker_reported_pid=123,
            worker_reported_pgid=123,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("partial", "ownership is incomplete"),
        ("lost", "safety boundary differs"),
        ("raw_pid", "safety boundary differs"),
        ("subprocess", "was not started with exact ownership"),
        ("nonzero", "terminal wait evidence differs"),
        ("hash", "projection hash differs"),
        ("extra", "projection fields differ"),
    ],
)
def test_native_real_worker_terminal_projection_rejects_unproven_claims(
    mutation: str,
    message: str,
) -> None:
    projection = _complete_native_terminal_projection()
    if mutation == "partial":
        projection["group_empty"] = False
    elif mutation == "lost":
        projection["ownership_lost"] = True
    elif mutation == "raw_pid":
        projection["raw_pid_retained"] = True
    elif mutation == "subprocess":
        projection["start_state"] = "subprocess_popen"
    elif mutation == "nonzero":
        projection["wait"]["exit_code"] = 7  # type: ignore[index]
    elif mutation == "hash":
        projection["worker_result_sha256"] = "not-a-hash"
    else:
        projection["pid"] = 1234

    with pytest.raises(ValueError, match=message):
        supervision._validate_native_terminal_projection(projection)


def test_native_real_worker_supervision_plan_is_blocked_and_path_free() -> None:
    plan = supervision._build_native_real_worker_supervision_plan()
    unsigned = plain(plan)
    digest = unsigned.pop("plan_sha256")

    assert plan["status"] == "blocked_not_run"
    assert plan["current_observation"][
        "native_process_group_supervision_bound"
    ] is False
    assert plan["required_projection"][
        "must_be_derived_from_exact_nonconstructible_native_owner"
    ] is True
    assert plan["missing_bridge"][
        "owner_bound_process_image_observer_implemented"
    ] is True
    assert plan["missing_bridge"][
        "owner_bound_network_observer_implemented"
    ] is True
    assert plan["missing_bridge"][
        "owner_bound_native_image_ready_observer_implemented"
    ] is True
    assert plan["missing_bridge"][
        "fixed_real_worker_native_entrypoint_implemented"
    ] is False
    assert plan["missing_bridge"][
        "model_free_combined_fixed_worker_bridge_implemented"
    ] is True
    assert plan["missing_bridge"][
        "model_free_terminal_projection_derived_from_live_owner"
    ] is True
    assert plan["missing_bridge"][
        "fixed_model_free_ready_release_entrypoint_implemented"
    ] is True
    assert plan["missing_bridge"][
        "existing_kim_ready_release_transport_shape_exercised"
    ] is True
    assert plan["missing_bridge"][
        "private_native_request_result_frame_contract_implemented"
    ] is True
    assert all(value is False for value in plan["effects"].values())
    assert digest == hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest()
    assert "/Users/" not in repr(plan)


def test_real_worker_observes_signal_state_before_model_loading() -> None:
    worker = (
        Path(__file__).parents[1] / "scripts" / "private-melroformer-worker.py"
    ).read_text(encoding="utf-8")

    assert 'parser.add_argument("--bind-real-worker-supervision"' in worker
    assert worker.index("signal_state = (") < worker.index(
        "_load_private_melroformer_model("
    )
