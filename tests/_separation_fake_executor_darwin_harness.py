from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import resource
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
sys.path.insert(0, str(REPOSITORY))

def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _open_descriptors() -> list[int]:
    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit == resource.RLIM_INFINITY or soft_limit > 1_048_576:
        raise RuntimeError("outer supervisor descriptor limit is unbounded")
    descriptors: list[int] = []
    for descriptor in range(int(soft_limit)):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        descriptors.append(descriptor)
    return descriptors


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _bound_supervision_report(
    receipt: Mapping[str, Any],
    *,
    outer_open_descriptors: list[int],
) -> dict[str, Any]:
    if outer_open_descriptors != [0, 1, 2]:
        raise RuntimeError(
            "outer supervisor inherited unexpected descriptors: "
            f"{outer_open_descriptors!r}"
        )
    payload = {
        "schema": "sunofriend.separation-fake-supervision-boundary.v1",
        "status": "bound_complete",
        "evidence_scope": "private_deterministic_transport_execution",
        "outer_supervisor": {
            "observation_point": "harness_main_before_execution_setup",
            "open_descriptors": outer_open_descriptors,
            "only_standard_descriptors_open": True,
            "raw_descriptor_identities_retained": False,
        },
        "exact_worker_execution": {
            "terminal_receipt_sha256": receipt["receipt_sha256"],
            "fake_worker_result_v2_sha256": receipt["bindings"][
                "fake_worker_result_v2_sha256"
            ],
            "worker_post_cpython_signal_state_bound": receipt["signal"][
                "worker_post_cpython_state_bound"
            ],
            "normal_zero_exit": (
                receipt["process"]["normal_exit"] is True
                and receipt["process"]["exit_code"] == 0
            ),
            "signal_termination_observed": receipt["signal"][
                "worker_signal_termination_observed"
            ],
            "exact_reap": receipt["process"]["exact_reap"],
            "raw_pid_or_pgid_retained": False,
        },
        "terminal_receipt": _plain(receipt),
        "limitations": [
            "post_cpython_state_does_not_reconstruct_pre_exec_signal_instant",
            "deterministic_fixture_only_not_real_model_evidence",
            "outer_observation_occurs_after_cpython_module_imports",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
        "effects": {
            "real_separation_enabled": False,
            "model_executed": False,
            "public_route_enabled": False,
            "selection_changed": False,
            "publication_permitted": False,
        },
    }
    return {**payload, "report_sha256": _canonical_hash(payload)}


def main() -> int:
    if len(sys.argv) != 2:
        return 64
    outer_open_descriptors = _open_descriptors()
    import secrets

    from sunofriend._separation_fake_execution_records import (
        _build_prepared_separation_fake_launch_plan_v3_record,
    )
    from sunofriend._separation_fake_executor_darwin import (
        _validate_fake_execution_terminal_receipt,
    )
    from sunofriend._separation_fake_launch_v2_records import (
        _build_blocked_separation_fake_launch_plan_v2_record,
    )
    from sunofriend._separation_fake_transport_records import (
        _build_separation_fake_launch_plan,
        _build_separation_fake_worker_request,
    )
    from sunofriend._separation_native_session_darwin import (
        _open_verified_native_launcher_session,
    )
    from sunofriend.separation_checkpoint_descriptor_lease import (
        _execute_reserved_separation_fake_worker_darwin,
    )
    from tests.test_separation_launch_v2_facade import _issue, _prepared

    scratch = Path(sys.argv[1]).resolve(strict=True)
    session, native_observation = _open_verified_native_launcher_session(
        cache_root=scratch / "native-builds"
    )
    fixture, lease, lease_observation, worker_v2, reservation = _prepared(
        scratch / "checkpoint"
    )
    checkpoint_launch = _issue(lease, reservation, worker_v2)
    fake_request = _build_separation_fake_worker_request(
        worker_request_v2=worker_v2,
        blocked_launch_plan_v2=checkpoint_launch,
        run_nonce=secrets.token_hex(32),
    )
    native = native_observation["bindings"]
    fake_launch_v1 = _build_separation_fake_launch_plan(
        fake_worker_request=fake_request,
        runtime_executable_sha256=native["runtime_executable"]["sha256"],
        runtime_executable_bytes=native["runtime_executable"]["bytes"],
        fake_worker_sha256=native["fake_worker"]["sha256"],
        fake_worker_bytes=native["fake_worker"]["bytes"],
    )
    blocked_fake_v2 = _build_blocked_separation_fake_launch_plan_v2_record(
        fake_worker_request=fake_request,
        fake_launch_plan_v1=fake_launch_v1,
        native_launcher_sha256=native["native_launcher"]["sha256"],
        native_launcher_bytes=native["native_launcher"]["bytes"],
        native_launcher_stat_identity=native["native_launcher"][
            "stat_identity"
        ],
        runtime_executable_sha256=native["runtime_executable"]["sha256"],
        runtime_executable_bytes=native["runtime_executable"]["bytes"],
        runtime_executable_stat_identity=native["runtime_executable"][
            "stat_identity"
        ],
        fake_worker_sha256=native["fake_worker"]["sha256"],
        fake_worker_bytes=native["fake_worker"]["bytes"],
        fake_worker_stat_identity=native["fake_worker"]["stat_identity"],
    )
    fake_launch_v3 = _build_prepared_separation_fake_launch_plan_v3_record(
        fake_worker_request=fake_request,
        fake_launch_plan_v1=fake_launch_v1,
        blocked_fake_launch_plan_v2=blocked_fake_v2,
        native_build_receipt_sha256=native[
            "native_build_receipt_sha256"
        ],
    )
    receipt = _execute_reserved_separation_fake_worker_darwin(
        lease,
        trusted_reservation=reservation,
        trusted_worker_request_v2=worker_v2,
        current_lease_observation=lease_observation,
        fake_worker_request=fake_request,
        fake_launch_plan_v1=fake_launch_v1,
        blocked_fake_launch_plan_v2=blocked_fake_v2,
        fake_launch_plan_v3=fake_launch_v3,
        trusted_native_session=session,
        native_session_observation=native_observation,
        private_root=scratch / "execution",
    )
    if _validate_fake_execution_terminal_receipt(receipt) is not receipt:
        raise RuntimeError("terminal receipt validator changed object identity")
    document = _bound_supervision_report(
        receipt,
        outer_open_descriptors=outer_open_descriptors,
    )
    if not fixture["checkpoint"].exists():
        raise RuntimeError("checkpoint source was not preserved")
    print(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
