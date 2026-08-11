#!/usr/bin/env python3
"""Serve one verified private full-song six-role review on localhost."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_full_song_execution_review import (  # noqa: E402
    build_full_song_review_server,
)


DEFAULT_PLAN = (
    Path.home()
    / ".local/share/sunofriend/separation/evidence"
    / "fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8772)
    args = parser.parse_args()
    server = build_full_song_review_server(
        args.root,
        plan_path=args.plan,
        host=args.host,
        port=args.port,
    )
    print(f"Full-song six-role review: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
