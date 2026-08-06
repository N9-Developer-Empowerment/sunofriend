#!/usr/bin/env python3
"""Create or validate the local core-four approval web page and JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from sunofriend.core_four_approval import (
    approval_binding,
    build_core_four_approval_server,
    validate_core_four_approval_document,
    write_core_four_approval_page,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--plan", action="store_true")
    actions.add_argument("--out")
    actions.add_argument("--validate")
    actions.add_argument("--serve", action="store_true")
    parser.add_argument("--synthetic-root")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.plan:
        print(
            json.dumps(
                {
                    "status": "ready_to_create_local_page",
                    "binding": approval_binding(),
                    "effects": {
                        "network": [],
                        "uploads": [],
                        "model_runs": [],
                        "writes": [],
                    },
                    "page_behavior": {
                        "downloads_json_locally": True,
                        "browser_storage": False,
                        "audio_in_json": False,
                        "typing_paths_reads_files": False,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.validate:
        document = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        validated = validate_core_four_approval_document(document)
        print(
            json.dumps(
                {
                    "status": "valid",
                    "approval_id": validated.get("approval_id"),
                    "approval_status": validated.get("status"),
                    "approved_by": validated["approved_by"],
                    "remaining_approval_blockers": validated.get(
                        "remaining_approval_blockers", []
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.serve:
        if not args.synthetic_root:
            parser.error("--serve requires --synthetic-root")
        server = build_core_four_approval_server(
            args.synthetic_root,
            port=args.port,
        )
        host, port = server.server_address
        print(f"http://{host}:{port}/", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    target = write_core_four_approval_page(
        args.out,
        synthetic_root=args.synthetic_root,
        open_browser=args.open,
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
