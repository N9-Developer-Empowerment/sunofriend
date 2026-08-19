#!/usr/bin/env python3
"""Launch the private, loopback-only Sunofriend Vocal Session page."""

from __future__ import annotations

import argparse
from pathlib import Path

from sunofriend.vocal_session_server import run_vocal_session


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open a private Sunofriend Vocal Session from a Musical State"
    )
    parser.add_argument("musical_state", type=Path)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--title", default="Vocal comp session")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    run_vocal_session(
        args.musical_state,
        state_dir=args.state_dir,
        title=args.title,
        port=args.port,
        open_browser=args.open,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
