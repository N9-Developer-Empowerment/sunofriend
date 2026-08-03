#!/usr/bin/env python3
"""Serve or verify a private sealed-vocal-candidate listening review."""

from __future__ import annotations

import argparse
import json
import webbrowser

from sunofriend._separation_vocal_candidate_audition import (
    _VocalCandidateAuditionServer,
    _load_audition_context,
    _resolve_vocal_candidate_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-set", required=True)
    parser.add_argument("--melroformer-evaluation", required=True)
    parser.add_argument("--vocal-leaf-evaluation", required=True)
    parser.add_argument("--phrase-completeness", required=True)
    parser.add_argument("--authorised-excerpt", required=True)
    parser.add_argument("--focus", required=True)
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Exact candidate ID from the sealed inventory; repeat to review a subset",
    )
    parser.add_argument("--review")
    parser.add_argument("--out")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if bool(args.review) != bool(args.out):
        parser.error("--review and --out must be supplied together")
    if bool(args.start_seconds is not None) != bool(args.end_seconds is not None):
        parser.error("--start-seconds and --end-seconds must be supplied together")
    if args.review:
        if args.open or args.port:
            parser.error("--open and --port are serve-only options")
        result = _resolve_vocal_candidate_review(
            args.review,
            args.candidate_set,
            args.melroformer_evaluation,
            args.vocal_leaf_evaluation,
            args.phrase_completeness,
            args.authorised_excerpt,
            focus=args.focus,
            start_seconds=args.start_seconds,
            end_seconds=args.end_seconds,
            candidate_ids=args.candidate,
            out=args.out,
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "report": result["report"],
                    "results": result["results"],
                    "policy": result["policy"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    context = _load_audition_context(
        args.candidate_set,
        args.melroformer_evaluation,
        args.vocal_leaf_evaluation,
        args.phrase_completeness,
        args.authorised_excerpt,
        focus=args.focus,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        candidate_ids=args.candidate,
    )
    server = _VocalCandidateAuditionServer(context, port=args.port)
    print(
        json.dumps(
            {
                "status": "private_loopback_audition_ready",
                "url": server.url,
                "candidate_count": context.seed["summary"]["candidate_count"],
                "audition_available_count": context.seed["summary"][
                    "audition_available_count"
                ],
                "scope": context.seed["scope"],
                "server_writes_review": False,
                "audio_or_midi_copied": False,
                "stop": "Press Ctrl-C",
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.open:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
