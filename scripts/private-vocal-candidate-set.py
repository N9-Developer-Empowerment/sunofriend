#!/usr/bin/env python3
"""Inventory sealed private vocal MIDI candidates without choosing one."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_vocal_candidate_set import _build_vocal_candidate_set


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--melroformer-evaluation", required=True)
    parser.add_argument("--vocal-leaf-evaluation", required=True)
    parser.add_argument("--phrase-completeness", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _build_vocal_candidate_set(
        args.melroformer_evaluation,
        args.vocal_leaf_evaluation,
        args.phrase_completeness,
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "summary": result["summary"],
                "next": result["next"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
