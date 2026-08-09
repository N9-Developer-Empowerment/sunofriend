#!/usr/bin/env python3
"""Construct and strictly load the exact SW MLX model without inference."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import torch
import yaml

from sunofriend.separation_bs_roformer_sw_evidence import (
    validate_sw_artifact_evidence,
)
from sunofriend.separation_bs_roformer_sw_load_contract import (
    EXPECTED_EFFECTS,
    SW_LOAD_REPORT_SCHEMA,
    SW_LOAD_REPORT_STATUS,
    SW_PROFILE_ID,
    sw_load_report_sha256,
    validate_sw_load_report,
)
from sunofriend.separation_bs_roformer_sw_loading import load_sw_model
from sunofriend.separation_fine_stem_canary_audio import file_sha256
from sunofriend.separation_fine_stem_canary_contract import SW_CHECKPOINT, SW_CONFIG
from sunofriend.separation_other_refinement_next_execution_guard import (
    Mega53RestrictedExecutionGuard,
)
from sunofriend.separation_other_refinement_next_model_load_contract import (
    RUNTIME,
    SOURCE,
)
from sunofriend.separation_other_refinement_next_source_evidence import (
    validate_source_evidence,
    verify_extracted_source_tree,
)


def _verify(path: Path, expected: dict[str, object], label: str) -> None:
    if (
        path.name != expected["file"]
        or path.stat().st_size != expected["bytes"]
        or file_sha256(path) != expected["sha256"]
    ):
        raise RuntimeError(f"BS-RoFormer-SW {label} identity differs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--static-evidence", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve(strict=True)
    config = args.config.resolve(strict=True)
    _verify(checkpoint, SW_CHECKPOINT, "checkpoint")
    _verify(config, SW_CONFIG, "packaged config")
    validate_sw_artifact_evidence(json.loads(args.static_evidence.read_text()))
    source_evidence = validate_source_evidence(
        json.loads(args.source_evidence.resolve(strict=True).read_text())
    )
    tree = verify_extracted_source_tree(
        source_evidence, args.source_root.resolve(strict=True)
    )
    if (
        source_evidence["archive"]["sha256"] != SOURCE["archive_sha256"]
        or source_evidence["evidence_sha256"] != SOURCE["evidence_sha256"]
        or tree
        != {
            "file_count": SOURCE["file_count"],
            "logical_bytes": SOURCE["logical_bytes"],
            "inventory_matches": True,
        }
    ):
        raise RuntimeError("BS-RoFormer-SW verified source identity differs")
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("BS-RoFormer-SW config is not a mapping")
    guard = Mega53RestrictedExecutionGuard(checkpoint)
    guard.install()
    loaded = load_sw_model(
        checkpoint=checkpoint,
        config_document=document,
        source_root=args.source_root.resolve(strict=True),
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
        raise RuntimeError(f"BS-RoFormer-SW runtime identity differs: {runtime!r}")
    report = {
        "schema": SW_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": SW_LOAD_REPORT_STATUS,
        "profile_id": SW_PROFILE_ID,
        "checkpoint": SW_CHECKPOINT,
        "config": SW_CONFIG,
        "source": SOURCE,
        "runtime": runtime,
        "model": loaded.evidence,
        "guards": guard.report(),
        "effects": EXPECTED_EFFECTS,
    }
    report["report_sha256"] = sw_load_report_sha256(report)
    validate_sw_load_report(report)
    if args.out.exists():
        raise FileExistsError("BS-RoFormer-SW load report must be fresh")
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.out.chmod(0o600)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
