#!/usr/bin/env python3
"""Describe comparison coverage in one sealed private separation index."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_corpus_coverage import (
    _assess_private_separation_corpus_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_index")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _assess_private_separation_corpus_coverage(
        args.evidence_index,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "catalogue_summary": result["catalogue_summary"],
                "coverage_summary": result["coverage_summary"],
                "publication_gate": result["publication_gate"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
