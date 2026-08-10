#!/usr/bin/env python3
"""Serve the private source-visible provider synth review on localhost."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_synth_provider_review import (  # noqa: E402
    build_provider_review_server,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8773, type=int)
    args = parser.parse_args()
    server = build_provider_review_server(
        args.root,
        host=args.host,
        port=args.port,
    )
    print(
        f"Serving private provider synth review at http://{args.host}:{args.port}/",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
