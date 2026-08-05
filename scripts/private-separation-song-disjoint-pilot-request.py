#!/usr/bin/env python3
"""Prepare one exact local song-disjoint separation pilot request and plan."""

from __future__ import annotations

import argparse
import json
import shlex

from sunofriend._separation_song_disjoint_private_pilot_request import (
    _prepare_song_disjoint_private_pilot_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one authorised new song, the pragmatic reference and the "
            "exact local Kim runtime, then prepare a gap-free private worker "
            "queue. This runs no model and enables no product route."
        )
    )
    parser.add_argument("--pragmatic-authorization", required=True)
    parser.add_argument("--reference-v2-execution", required=True)
    parser.add_argument("--reference-stitch-package-dir", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    result = _prepare_song_disjoint_private_pilot_request(
        args.pragmatic_authorization,
        reference_v2_execution_path=args.reference_v2_execution,
        reference_stitch_package_dir=args.reference_stitch_package_dir,
        corpus_manifest_path=args.corpus,
        track_id=args.track_id,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        out_dir=args.out_dir,
        device=args.device,
    )
    execution = result["execution_inputs"]
    next_command = shlex.join(
        [
            "./.venv/bin/python",
            "scripts/private-separation-song-disjoint-pilot-execute.py",
            "--request",
            result["report"],
            "--out-dir",
            "$FRESH_PRIVATE_EXECUTION_ROOT",
            "--repository-root",
            execution["repository_root"],
            "--runtime-launcher",
            execution["runtime_launcher"],
            "--source-root",
            execution["source_root"],
            "--checkpoint",
            execution["checkpoint"],
            "--companion-root",
            execution["companion_root"],
            "--device",
            execution["device"],
            "--all",
        ]
    )
    next_command = next_command.replace(
        "'$FRESH_PRIVATE_EXECUTION_ROOT'",
        '"$FRESH_PRIVATE_EXECUTION_ROOT"',
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "plan_report": result["plan_report"],
                "track": result["pilot"],
                "source_distinction": result["source_distinction"],
                "plan": result["plan"],
                "readiness": result["readiness"],
                "next_command": f"PYTHONPATH=src {next_command}",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
