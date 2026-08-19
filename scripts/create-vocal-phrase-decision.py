#!/usr/bin/env python3
"""Create path-free human vocal decisions and an optional source map."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_phrase_decision import (
    create_phrase_decision,
    create_vocal_source_map,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--musical-state", type=Path, required=True)
    parser.add_argument("--phrase-id", required=True)
    parser.add_argument(
        "--outcome",
        required=True,
        choices=(
            "human_take",
            "ai_fallback",
            "record_again",
            "no_acceptable_candidate",
        ),
    )
    parser.add_argument("--source-id")
    parser.add_argument("--reviewed-at")
    parser.add_argument("--review-evidence", type=Path)
    parser.add_argument("--notes")
    parser.add_argument("--decision-out", type=Path, required=True)
    parser.add_argument("--source-map-out", type=Path)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(document))


def main() -> int:
    args = _arguments()
    state = _read_json(args.musical_state)
    evidence_sha = (
        _file_sha256(args.review_evidence) if args.review_evidence is not None else None
    )
    decision = create_phrase_decision(
        state,
        args.phrase_id,
        args.outcome,
        source_id=args.source_id,
        notes=args.notes,
        reviewed_at=args.reviewed_at,
        review_evidence_sha256=evidence_sha,
    )
    _write_new_json(args.decision_out, decision)
    if args.source_map_out is not None:
        source_map = create_vocal_source_map(state, [decision])
        _write_new_json(args.source_map_out, source_map)
    print(
        json.dumps(
            {
                "decision_document_sha256": decision["document_sha256"],
                "source_map_written": args.source_map_out is not None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
