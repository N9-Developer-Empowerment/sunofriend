#!/usr/bin/env python3
"""Construct and strictly load Mega-53 under the no-inference evidence gate."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
import torch
import yaml

from sunofriend.separation_other_refinement_next_execution_guard import (
    Mega53RestrictedExecutionGuard,
)
from sunofriend.separation_other_refinement_next_model_load_contract import (
    CHECKPOINT,
    CONFIG,
    EXPECTED_EFFECTS,
    MODEL_LOAD_REPORT_SCHEMA,
    MODEL_LOAD_REPORT_STATUS,
    PROFILE_ID,
    RUNTIME,
    SOURCE,
    model_load_report_sha256,
)
from sunofriend.separation_other_refinement_next_model_loading import (
    load_mega53_model,
)
from sunofriend.separation_other_refinement_next_source_evidence import (
    validate_source_evidence,
    verify_extracted_source_tree,
)


class _ConfigLoader(yaml.SafeLoader):
    """Safe YAML loader extended only for the upstream tuple tag."""


_ConfigLoader.add_constructor(
    "tag:yaml.org,2002:python/tuple",
    lambda loader, node: tuple(loader.construct_sequence(node)),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_file(path: Path, expected: dict[str, Any], label: str) -> None:
    if path.name != expected["file"]:
        raise RuntimeError(f"Mega-53 {label} filename differs")
    if path.stat().st_size != expected["bytes"] or _sha256(path) != expected["sha256"]:
        raise RuntimeError(f"Mega-53 {label} identity differs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    config = args.config.resolve()
    source_root = args.source_root.resolve()
    source_evidence_path = args.source_evidence.resolve()

    _verify_file(checkpoint, CHECKPOINT, "checkpoint")
    _verify_file(config, CONFIG, "config")
    source_evidence = validate_source_evidence(
        json.loads(source_evidence_path.read_text(encoding="utf-8"))
    )
    tree = verify_extracted_source_tree(source_evidence, source_root)
    if source_evidence["archive"]["sha256"] != SOURCE["archive_sha256"]:
        raise RuntimeError("Mega-53 source archive identity differs")
    if source_evidence["evidence_sha256"] != SOURCE["evidence_sha256"]:
        raise RuntimeError("Mega-53 source evidence identity differs")
    if tree != {
        "file_count": SOURCE["file_count"],
        "logical_bytes": SOURCE["logical_bytes"],
        "inventory_matches": True,
    }:
        raise RuntimeError("Mega-53 source tree inventory differs")

    config_document = yaml.load(config.read_text(encoding="utf-8"), Loader=_ConfigLoader)
    if not isinstance(config_document, dict):
        raise RuntimeError("Mega-53 config is not a mapping")

    guard = Mega53RestrictedExecutionGuard(checkpoint)
    guard.install()
    loaded = load_mega53_model(
        checkpoint=checkpoint,
        config_document=config_document,
        source_root=source_root,
    )
    guard.assert_complete()

    runtime = {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "mlx": version("mlx"),
        "mlx-spectro": version("mlx-spectro"),
        "pyyaml": version("pyyaml"),
    }
    if runtime != RUNTIME:
        raise RuntimeError(f"Mega-53 runtime identity differs: {runtime!r}")

    report: dict[str, Any] = {
        "schema": MODEL_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": MODEL_LOAD_REPORT_STATUS,
        "profile_id": PROFILE_ID,
        "checkpoint": CHECKPOINT,
        "config": CONFIG,
        "source": SOURCE,
        "runtime": runtime,
        "model": loaded.evidence,
        "guards": guard.report(),
        "effects": EXPECTED_EFFECTS,
    }
    report["report_sha256"] = model_load_report_sha256(report)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
