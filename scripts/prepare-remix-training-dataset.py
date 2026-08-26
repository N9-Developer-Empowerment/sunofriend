#!/usr/bin/env python3
"""Prepare one path-free real remix-training snapshot without reading audio."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sunofriend.remix_training_dataset import prepare_remix_training_dataset
from sunofriend.source_receipt import canonical_json_bytes


_MAXIMUM_EVIDENCE_BYTES = 16 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a path-free, split-safe owner-label snapshot and exact readiness "
            "report. This reads JSON evidence only and does not read audio or train."
        )
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--label", action="append", type=Path, required=True)
    parser.add_argument(
        "--owner-registry", action="append", type=Path, required=True
    )
    parser.add_argument("--variant-set", action="append", type=Path, required=True)
    parser.add_argument(
        "--split",
        action="append",
        required=True,
        metavar="COMPOSITION_ID=SPLIT",
        help="Assign an owner-confirmed composition to train, validation or test",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = prepare_remix_training_dataset(
        snapshot_id=args.snapshot_id,
        labels=[_read_json(path) for path in args.label],
        owner_registries=[_read_json(path) for path in args.owner_registry],
        variant_sets=[_read_json(path) for path in args.variant_set],
        composition_splits=_split_map(args.split),
    )
    _write_fresh_private(args.out, canonical_json_bytes(document))
    print(args.out.expanduser().absolute())
    return 0


def _read_json(value: Path) -> dict[str, Any]:
    supplied = value.expanduser().absolute()
    if supplied.is_symlink():
        raise ValueError("remix training evidence must be an ordinary JSON file")
    path = supplied.resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= _MAXIMUM_EVIDENCE_BYTES:
        raise ValueError("remix training evidence size is outside the safe bound")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("remix training evidence must be readable JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("remix training evidence must be a JSON object")
    return value


def _split_map(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        composition, separator, split = value.partition("=")
        if not separator or not composition or not split:
            raise ValueError("split must use COMPOSITION_ID=SPLIT")
        if composition in result:
            raise ValueError("composition split was supplied more than once")
        result[composition] = split
    return result


def _write_fresh_private(path_value: Path, payload: bytes) -> None:
    path = path_value.expanduser().absolute()
    if path.parent.is_symlink():
        raise ValueError("output parent must be an ordinary directory")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir() or path.exists() or path.is_symlink():
        raise ValueError("output must be a fresh file in an existing directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
