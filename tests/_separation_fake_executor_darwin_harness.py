from __future__ import annotations

import json
import secrets
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))
sys.path.insert(0, str(REPOSITORY))

from sunofriend._separation_fake_execution_records import (  # noqa: E402
    _build_prepared_separation_fake_launch_plan_v3_record,
)
from sunofriend._separation_fake_executor_darwin import (  # noqa: E402
    _validate_fake_execution_terminal_receipt,
)
from sunofriend._separation_fake_launch_v2_records import (  # noqa: E402
    _build_blocked_separation_fake_launch_plan_v2_record,
)
from sunofriend._separation_fake_transport_records import (  # noqa: E402
    _build_separation_fake_launch_plan,
    _build_separation_fake_worker_request,
)
from sunofriend._separation_native_session_darwin import (  # noqa: E402
    _open_verified_native_launcher_session,
)
from sunofriend.separation_checkpoint_descriptor_lease import (  # noqa: E402
    _execute_reserved_separation_fake_worker_darwin,
)
from tests.test_separation_launch_v2_facade import _issue, _prepared  # noqa: E402


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def main() -> int:
    if len(sys.argv) != 2:
        return 64
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
    document = _plain(receipt)
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
