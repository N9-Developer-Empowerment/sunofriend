#!/usr/bin/env python3
"""Plan or create one no-MIDI audio-native Musical State v0 project."""

from __future__ import annotations

import argparse
import json

from sunofriend.musical_state import (
    create_vocal_musical_state,
    plan_vocal_musical_state,
)
from sunofriend.source_project import RIGHTS_CATEGORIES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("take_dir")
    parser.add_argument("--lyrics", required=True)
    parser.add_argument("--phrase-timeline", required=True)
    parser.add_argument("--reference-vocal")
    parser.add_argument("--bpm", type=float)
    parser.add_argument("--tuning-hz", type=float, default=440.0)
    parser.add_argument("--rights-category", required=True, choices=sorted(RIGHTS_CATEGORIES))
    parser.add_argument(
        "--processing-chain",
        required=True,
        choices=("dry", "same-gentle-chain"),
    )
    parser.add_argument("--confirm-common-recorded-zero", action="store_true")
    parser.add_argument("--confirm-timeline-reviewed", action="store_true")
    parser.add_argument("--out-dir")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create the fresh private project; otherwise print a read-only plan",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    keyword = {
        "lyrics": args.lyrics,
        "phrase_timeline": args.phrase_timeline,
        "reference_vocal": args.reference_vocal,
        "bpm": args.bpm,
        "tuning_hz": args.tuning_hz,
        "rights_category": args.rights_category,
        "processing_chain": args.processing_chain,
        "confirm_common_recorded_zero": args.confirm_common_recorded_zero,
        "confirm_timeline_reviewed": args.confirm_timeline_reviewed,
    }
    if args.execute:
        if not args.out_dir:
            raise SystemExit("--out-dir is required with --execute")
        result = create_vocal_musical_state(
            args.take_dir, out_dir=args.out_dir, **keyword
        )
    else:
        result = plan_vocal_musical_state(args.take_dir, **keyword)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
