#!/usr/bin/env python3
"""Open one verified remix source-delta render as a read-only hidden A/B."""

from __future__ import annotations

import argparse

from sunofriend.remix_source_delta_audition import (
    create_remix_source_delta_audition_server,
    run_remix_source_delta_audition_server,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open a private playback-only A/B for one source-delta render."
    )
    parser.add_argument("render_root")
    parser.add_argument("--title", default="Private remix A/B audition")
    parser.add_argument("--port", type=int, default=8781)
    parser.add_argument("--presentation-seed", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_remix_source_delta_audition_server(
        args.render_root,
        title=args.title,
        port=args.port,
        presentation_seed=args.presentation_seed,
    )
    run_remix_source_delta_audition_server(
        server, open_browser=not args.no_browser
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
