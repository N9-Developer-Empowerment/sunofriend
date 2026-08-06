#!/usr/bin/env python3
"""Record an explicit completed no-failure SCNet canary listen."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from sunofriend.separation_scnet_full_song_canaries import (
    record_no_failure_canary_listen,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--explicit-statement", required=True)
    parser.add_argument("--all-no-catastrophic-failures", action="store_true")
    args = parser.parse_args(argv)
    if args.all_no_catastrophic_failures is not True:
        parser.error("recording requires --all-no-catastrophic-failures")
    result = record_no_failure_canary_listen(
        args.root,
        args.out,
        reviewed_by=args.reviewed_by,
        explicit_statement=args.explicit_statement,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
