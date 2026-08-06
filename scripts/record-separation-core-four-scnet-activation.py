#!/usr/bin/env python3
"""Record the finite SCNet public-opt-in activation decision."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from sunofriend.separation_scnet_activation import (
    record_scnet_public_opt_in_activation,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-song-root", required=True)
    parser.add_argument("--listen", required=True)
    parser.add_argument("--synthetic-root", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = record_scnet_public_opt_in_activation(
        args.full_song_root,
        args.listen,
        args.synthetic_root,
        args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
