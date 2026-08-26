#!/usr/bin/env python3
"""Create an owner-only resumable vocal session from exact decision documents."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from typing import Any

from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_session import VocalSessionStore, build_vocal_session


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--musical-state", type=Path, required=True)
    parser.add_argument("--decision", type=Path, action="append", default=[])
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def main() -> int:
    args = _arguments()
    destination = args.out_dir.expanduser().resolve()
    if destination.exists():
        raise ValueError(f"vocal session output already exists: {destination}")
    destination.mkdir(parents=True, mode=0o700)
    os.chmod(destination, 0o700)
    try:
        state = _read_json(args.musical_state)
        decisions = [_read_json(path) for path in args.decision]
        session = build_vocal_session(state)
        store = VocalSessionStore(destination / "STATE")
        for decision in decisions:
            store.append(
                session,
                {"event_type": "phrase_decision", "decision": decision},
            )
        current = store.current_session(state)
        session_path = destination / "vocal-session.json"
        descriptor = os.open(session_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(current))
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    print(
        json.dumps(
            {
                "session_id": current["session_id"],
                "status": current["status"],
                "decision_count": current["coverage"]["decision_count"],
                "remaining_phrase_count": current["coverage"]["remaining_phrase_count"],
                "document_sha256": current["document_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
