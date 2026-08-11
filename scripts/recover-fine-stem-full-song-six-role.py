#!/usr/bin/env python3
"""Plan or execute one exact no-model full-song six-role recovery."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_full_song_plan_contract import (  # noqa: E402
    validate_fine_stem_full_song_plan,
)
from sunofriend.separation_fine_stem_full_song_recovery import (  # noqa: E402
    NETWORK_SANDBOX_ENV,
    build_recovery_request,
    execute_recovery,
    validate_recovery_report,
)


EVIDENCE = Path.home() / ".local/share/sunofriend/separation/evidence"
DEFAULT_PLAN = (
    EVIDENCE
    / "fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json"
)
DEFAULT_FAILED = (
    EVIDENCE / "fine-stem-full-song-six-role-canary-replacement-v1-FAILED"
)
DEFAULT_PRIOR_FAILED = EVIDENCE / "fine-stem-full-song-six-role-canary-v1-FAILED"
DEFAULT_OUT = EVIDENCE / "fine-stem-full-song-six-role-recovery-v1"


def _json(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("full-song recovery JSON must be an object")
    return value


def _sandbox_reexec() -> int:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise RuntimeError("macOS sandbox-exec is required for network denial")
    environment = os.environ.copy()
    environment[NETWORK_SANDBOX_ENV] = "1"
    return subprocess.run(
        [
            str(sandbox),
            "-p",
            "(version 1)(allow default)(deny network*)",
            sys.executable,
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
        env=environment,
        check=False,
    ).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--failed-root", type=Path, default=DEFAULT_FAILED)
    parser.add_argument(
        "--prior-failed-root", type=Path, default=DEFAULT_PRIOR_FAILED
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--approved-recovery-sha256")
    parser.add_argument("--confirm-rights", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-report", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    plan = validate_fine_stem_full_song_plan(_json(args.plan))
    if args.validate_report is not None:
        report_path = args.validate_report.resolve(strict=True)
        request_path = report_path.parent / "RECOVERY-REQUEST.json"
        report = validate_recovery_report(
            _json(report_path), plan, _json(request_path)
        )
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.execute and os.environ.get(NETWORK_SANDBOX_ENV) != "1":
        return _sandbox_reexec()
    request = build_recovery_request(
        plan,
        args.failed_root,
        proposed_output=args.out,
        prior_failed_root_value=args.prior_failed_root,
    )
    if not args.execute:
        print(json.dumps(request, indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.approved_recovery_sha256 is None:
        raise SystemExit("execution requires --approved-recovery-sha256")
    report = execute_recovery(
        plan,
        request,
        approved_recovery_sha256=args.approved_recovery_sha256,
        confirm_rights=args.confirm_rights,
        network_sandbox_verified=True,
    )
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
