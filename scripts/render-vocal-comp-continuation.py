#!/usr/bin/env python3
"""Plan, authorize or render one exact carried-base vocal continuation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from sunofriend.musical_state import validate_musical_state
from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_comp_continuation import (
    create_vocal_continuation_plan,
    create_vocal_continuation_render_authorization,
    render_vocal_continuation,
)
from sunofriend.vocal_session import VocalSessionStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-binding", type=Path, required=True)
    parser.add_argument("--musical-state", type=Path, required=True)
    parser.add_argument("--session-state-dir", type=Path, required=True)
    parser.add_argument("--phrase-id", required=True)
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--confirm-dry-uncorrected-preview", action="store_true")
    parser.add_argument("--authorization-out", type=Path)
    parser.add_argument("--render-authorization", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--confirm-dry-uncorrected-render", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()

    state_path = args.musical_state.expanduser().resolve(strict=True)
    state = validate_musical_state(state_path, root=state_path.parent)
    decisions = VocalSessionStore(args.session_state_dir).current_decisions(state)
    matches = [row for row in decisions if row["phrase"]["phrase_id"] == args.phrase_id]
    if len(matches) != 1:
        raise ValueError("exactly one active phrase decision is required")
    decision = matches[0]
    plan = create_vocal_continuation_plan(args.base_binding, state_path, decision)
    if args.plan_out is not None:
        _write_private_json(args.plan_out, plan)

    if args.authorize:
        if args.authorization_out is None:
            raise ValueError("--authorize requires --authorization-out")
        authorization = create_vocal_continuation_render_authorization(
            plan,
            confirm_dry_uncorrected_preview=args.confirm_dry_uncorrected_preview,
        )
        _write_private_json(args.authorization_out, authorization)
        print(json.dumps(authorization, indent=2, sort_keys=True))
        return 0

    if args.execute:
        if (
            args.render_authorization is None
            or args.expected_plan_sha256 is None
            or args.out_dir is None
        ):
            raise ValueError(
                "--execute requires --render-authorization, "
                "--expected-plan-sha256 and --out-dir"
            )
        authorization = _read_json(args.render_authorization)
        verification = render_vocal_continuation(
            args.base_binding,
            state_path,
            decision,
            plan,
            authorization,
            out_dir=args.out_dir,
            expected_plan_sha256=args.expected_plan_sha256,
            confirm_dry_uncorrected_render=args.confirm_dry_uncorrected_render,
        )
        print(json.dumps(verification, indent=2, sort_keys=True))
        return 0

    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    if target.exists():
        raise ValueError(f"output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == "__main__":
    raise SystemExit(main())
