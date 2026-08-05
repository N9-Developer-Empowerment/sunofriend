#!/usr/bin/env python3
"""Preflight or execute one exact v2 song-disjoint private pilot request."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_song_disjoint_private_pilot_execution import (
    _execute_song_disjoint_private_pilot_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Remeasure the exact runtime, source, checkpoint, companions and "
            "worker code sealed by a v2 private-pilot request, then preflight "
            "or resume its request-bound chunk queue. No result is selected."
        )
    )
    parser.add_argument("--request", required=True)
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
    result = _execute_song_disjoint_private_pilot_request(
        args.request,
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
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
