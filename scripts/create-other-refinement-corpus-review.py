#!/usr/bin/env python3
"""Prepare, serve or record the bounded private guitar/keys corpus review."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from sunofriend.separation_other_refinement_corpus import (
    build_other_refinement_corpus_review_server,
    load_other_refinement_corpus_definition,
    prepare_other_refinement_corpus_review,
    record_other_refinement_corpus_reviews,
    validate_other_refinement_corpus_authority,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--plan", action="store_true")
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--serve", action="store_true")
    actions.add_argument("--record", action="store_true")
    parser.add_argument(
        "--definition",
        default="stem_examples/other-refinement-evaluation-v1.json",
    )
    parser.add_argument("--stem-root", default="stem_examples")
    parser.add_argument("--execution-root")
    parser.add_argument("--review-root")
    parser.add_argument("--bundle")
    parser.add_argument("--out")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--port", type=int, default=8766)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.plan:
        definition = load_other_refinement_corpus_definition(args.definition)
        authorities = validate_other_refinement_corpus_authority(
            definition, stem_root=args.stem_root
        )
        print(
            json.dumps(
                {
                    "status": "fixed_corpus_plan_no_effects",
                    "schema": definition["schema"],
                    "case_count": sum(
                        len(track["cases"]) for track in definition["tracks"]
                    ),
                    "policy": definition["policy"],
                    "authorities": authorities,
                    "effects": {
                        "writes": [],
                        "model_runs": [],
                        "network": [],
                        "candidate_selection": [],
                        "source_or_midi_activation": [],
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.prepare:
        if not args.execution_root or not args.out:
            parser.error("--prepare requires --execution-root and --out")
        result = prepare_other_refinement_corpus_review(
            args.definition,
            stem_root=args.stem_root,
            execution_root=args.execution_root,
            output=args.out,
            ffmpeg=args.ffmpeg,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.serve:
        if not args.review_root:
            parser.error("--serve requires --review-root")
        server = build_other_refinement_corpus_review_server(
            args.review_root,
            port=args.port,
        )
        host, port = server.server_address
        print(f"http://{host}:{port}/", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if (
        not args.execution_root
        or not args.review_root
        or not args.bundle
        or not args.out
    ):
        parser.error(
            "--record requires --execution-root, --review-root, --bundle and --out"
        )
    result = record_other_refinement_corpus_reviews(
        args.execution_root,
        args.review_root,
        args.bundle,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
