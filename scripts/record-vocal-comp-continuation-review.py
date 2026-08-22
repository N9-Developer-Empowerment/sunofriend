#!/usr/bin/env python3
"""Record one exact owner review of a dry vocal continuation preview."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_comp_continuation import create_vocal_continuation_review


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--phrase-outcome",
        choices=("usable", "not_usable", "cannot_tell"),
        required=True,
    )
    parser.add_argument(
        "--join-outcome",
        choices=("natural", "audible", "cannot_tell"),
        required=True,
    )
    parser.add_argument("--heard-full-preview", action="store_true")
    parser.add_argument("--notes")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    review = create_vocal_continuation_review(
        args.render_root,
        _read_json(args.plan),
        phrase_outcome=args.phrase_outcome,
        join_outcome=args.join_outcome,
        heard_full_preview=args.heard_full_preview,
        notes=args.notes,
    )
    _write_private_json(args.out, review)
    print(json.dumps(review, indent=2, sort_keys=True))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    if target.exists():
        raise ValueError(f"review output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == "__main__":
    raise SystemExit(main())
