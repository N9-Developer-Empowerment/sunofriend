#!/usr/bin/env python3
"""Run one exact, offline C0 synthetic canary request on the CUDA worker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.gpu_canary import run_c0_canary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = run_c0_canary(request, out_dir=args.out_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
