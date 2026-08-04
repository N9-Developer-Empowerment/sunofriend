#!/usr/bin/env python3
"""Create or resolve one private multi-candidate vocal-event review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import webbrowser

from sunofriend._separation_vocal_focus_review import (
    VocalFocusInput,
    _create_private_separated_vocal_focus_review,
    _resolve_private_separated_vocal_focus_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--create", action="store_true")
    action.add_argument("--resolve", type=Path, metavar="REVIEWED_JSON")
    parser.add_argument("--track-id")
    parser.add_argument("--authorised-excerpt", type=Path)
    parser.add_argument("--candidate-evaluation", type=Path)
    parser.add_argument("--role-mapping", type=Path)
    parser.add_argument("--provider", action="append", default=[])
    parser.add_argument("--focus")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    create_values = (
        args.track_id,
        args.authorised_excerpt,
        args.candidate_evaluation,
        args.role_mapping,
        args.focus,
        args.out_dir,
    )
    if args.create:
        if not all(create_values) or not args.provider:
            parser.error(
                "--create requires --track-id, --authorised-excerpt, "
                "--candidate-evaluation, --role-mapping, at least one --provider, "
                "--focus and --out-dir"
            )
        if args.package_dir is not None or args.out is not None:
            parser.error("--package-dir and --out are only valid with --resolve")
        result = _create_private_separated_vocal_focus_review(
            VocalFocusInput(
                track_id=args.track_id,
                authorised_excerpt=args.authorised_excerpt,
                candidate_midi_evaluation=args.candidate_evaluation,
                role_mapping=args.role_mapping,
                provider_ids=tuple(args.provider),
            ),
            focus=args.focus,
            out_dir=args.out_dir,
        )
        if args.open:
            webbrowser.open(Path(result["html"]).as_uri())
    else:
        if args.package_dir is None or args.out is None:
            parser.error("--resolve requires --package-dir and --out")
        if any(create_values) or args.provider or args.open:
            parser.error("create-only options are not valid with --resolve")
        result = _resolve_private_separated_vocal_focus_review(
            args.resolve,
            package_dir=args.package_dir,
            out=args.out,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
