#!/usr/bin/env python3
"""Serve one exact SCNet full-song canary review bundle on localhost."""

from __future__ import annotations

import argparse
from typing import Sequence

from sunofriend.separation_scnet_full_song_canaries import (
    build_canary_review_server,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    server = build_canary_review_server(args.root, port=args.port)
    host, port = server.server_address
    print(f"http://{host}:{port}/", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
