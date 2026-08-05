#!/usr/bin/env python3
"""Advance one v2 private pilot through automatic evidence, then stop."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_song_disjoint_private_pilot_pipeline import (
    _run_song_disjoint_private_pilot_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight or resume request-bound worker chunks, exact stitching, "
            "alignment and automatic evidence. The command stops before human "
            "review and enables no product route."
        )
    )
    parser.add_argument("--request", required=True)
    parser.add_argument("--pragmatic-authorization", required=True)
    parser.add_argument("--reference-v2-execution", required=True)
    parser.add_argument("--out-dir")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--preflight", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true")
    group.add_argument("--maximum-chunks", type=int, default=1)
    args = parser.parse_args()
    if not args.preflight and not args.out_dir:
        parser.error("--out-dir is required unless --preflight is used")
    if args.preflight and args.all:
        parser.error("--all cannot be combined with --preflight")
    result = _run_song_disjoint_private_pilot_pipeline(
        args.request,
        pragmatic_authorization_path=args.pragmatic_authorization,
        reference_v2_execution_path=args.reference_v2_execution,
        out_dir=args.out_dir,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        device=args.device,
        maximum_chunks=None if args.all else args.maximum_chunks,
        preflight=args.preflight,
    )
    summary = {
        "schema": result["schema"],
        "status": result["status"],
        "stages": result["stages"],
        "permissions": result["permissions"],
    }
    for key in ("report", "review_html", "readiness"):
        if key in result:
            summary[key] = result[key]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
