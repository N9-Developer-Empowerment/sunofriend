#!/usr/bin/env python3
"""Execute sealed private join-remediation windows and build candidates."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_join_remediation_executor import (
    _execute_private_separation_full_song_join_remediation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume exact private join-remediation windows. Once every worker "
            "result verifies, create separate candidate stems without changing "
            "the raw stitch."
        )
    )
    parser.add_argument("plan", help="sealed join-remediation plan JSON")
    parser.add_argument("--package-dir", required=True, help="unchanged stitch package")
    parser.add_argument("--source-plan", required=True, help="unchanged full-song plan JSON")
    parser.add_argument("--out-dir", required=True, help="fresh or resumable owner-only root")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument(
        "--all",
        action="store_true",
        help="run all remaining windows instead of only the next one",
    )
    args = parser.parse_args()
    result = _execute_private_separation_full_song_join_remediation(
        args.plan,
        package_dir=args.package_dir,
        source_plan_path=args.source_plan,
        out_dir=args.out_dir,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        device=args.device,
        maximum_windows=None if args.all else 1,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "candidate_report": result["candidate_report_path"],
                "summary": result["summary"],
                "windows_executed_this_invocation": result[
                    "windows_executed_this_invocation"
                ],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
