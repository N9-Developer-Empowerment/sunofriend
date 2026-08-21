#!/usr/bin/env python3
"""Create one path-free, owner-only remix source-state document."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_source_state import create_remix_source_state
from sunofriend.source_receipt import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-control", required=True)
    parser.add_argument("--state-id", required=True)
    parser.add_argument("--composition-id", required=True)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--source-start-seconds", type=float, required=True)
    parser.add_argument("--source-end-seconds", type=float, required=True)
    parser.add_argument("--rights-category", choices=("owned",), required=True)
    parser.add_argument("--confirm-owner-local-training", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source = Path(args.source_control).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError("source control must be a regular local file")
    document = create_remix_source_state(
        state_id=args.state_id,
        composition_id=args.composition_id,
        group_id=args.group_id,
        source_control=inspect_remix_audio(source),
        rights_category=args.rights_category,
        source_start_seconds=args.source_start_seconds,
        source_end_seconds=args.source_end_seconds,
        owner_local_training_approved=args.confirm_owner_local_training,
    )
    destination = Path(args.out).expanduser().absolute()
    if destination.exists():
        raise ValueError("remix source-state output already exists")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())
    destination.chmod(0o600)
    print(
        json.dumps(
            {"out": str(destination), "document_sha256": document["document_sha256"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
