#!/usr/bin/env python3
"""Create one path-free private MusicFM feature-extraction request."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_private_features import (  # noqa: E402
    create_musicfm_private_feature_request,
)
from sunofriend.source_receipt import canonical_json_bytes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training_snapshot", type=Path)
    parser.add_argument("setup_receipt", type=Path)
    parser.add_argument("--label-sha256", required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.training_snapshot.read_text(encoding="utf-8"))
    receipt = args.setup_receipt.read_bytes()
    request = create_musicfm_private_feature_request(
        repository_commit=args.repository_commit,
        setup_receipt_sha256=hashlib.sha256(receipt).hexdigest(),
        setup_receipt_bytes=len(receipt),
        training_snapshot=snapshot,
        label_document_sha256=args.label_sha256,
    )
    args.out.write_bytes(canonical_json_bytes(request))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
