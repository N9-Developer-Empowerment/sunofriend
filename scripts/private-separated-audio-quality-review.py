#!/usr/bin/env python3
"""Create or resolve the private cross-song vocal-audio quality review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import webbrowser

from sunofriend._separation_audio_quality_review import (
    AudioQualityInput,
    _create_private_separated_audio_quality_review,
    _resolve_private_separated_audio_quality_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--create", action="store_true")
    action.add_argument("--resolve", type=Path, metavar="REVIEWED_JSON")
    parser.add_argument(
        "--case",
        action="append",
        nargs=5,
        metavar=(
            "TRACK_ID",
            "AUTHORISED_EXCERPT",
            "CANDIDATE_EVALUATION",
            "ROLE_MAPPING",
            "PROVIDER_ID",
        ),
        help="repeat for each source-bound song case",
    )
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    if args.create:
        if not args.case or args.out_dir is None:
            parser.error("--create requires at least two --case values and --out-dir")
        if args.package_dir is not None or args.out is not None:
            parser.error("--package-dir and --out are only valid with --resolve")
        result = _create_private_separated_audio_quality_review(
            [
                AudioQualityInput(
                    track_id=track_id,
                    authorised_excerpt=Path(excerpt),
                    candidate_midi_evaluation=Path(candidate),
                    role_mapping=Path(mapping),
                    provider_id=provider,
                )
                for track_id, excerpt, candidate, mapping, provider in args.case
            ],
            out_dir=args.out_dir,
        )
        if args.open:
            webbrowser.open(Path(result["html"]).as_uri())
    else:
        if args.package_dir is None or args.out is None:
            parser.error("--resolve requires --package-dir and --out")
        if args.case is not None or args.out_dir is not None or args.open:
            parser.error("--case, --out-dir and --open are only valid with --create")
        result = _resolve_private_separated_audio_quality_review(
            args.resolve,
            package_dir=args.package_dir,
            out=args.out,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
