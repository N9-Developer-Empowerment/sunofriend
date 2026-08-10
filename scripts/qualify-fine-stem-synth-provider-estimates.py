#!/usr/bin/env python3
"""Qualify four exact private provider synth estimates for local review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_synth_provider_qualification import (  # noqa: E402
    qualify_fine_stem_synth_provider_estimates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_root", type=Path)
    parser.add_argument("integration_root", type=Path)
    parser.add_argument("provider_inputs", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    request_root = args.request_root.resolve(strict=True)
    integration_root = args.integration_root.resolve(strict=True)
    provider_inputs_path = args.provider_inputs.resolve(strict=True)
    out = args.out.resolve()
    if out.name != "fine-stem-synth-provider-qualification-v1":
        raise RuntimeError("exact provider qualification output root name is required")
    request = json.loads(
        (request_root / "SYNTH-BOTTLENECK-REQUEST.json").read_text(encoding="utf-8")
    )
    integration = json.loads(
        (integration_root / "TECHNICAL/INTEGRATION-REPORT.json").read_text(
            encoding="utf-8"
        )
    )
    result = qualify_fine_stem_synth_provider_estimates(
        request=request,
        integration_report=integration,
        integration_root=integration_root,
        provider_inputs=json.loads(provider_inputs_path.read_text(encoding="utf-8")),
        out_dir=out,
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
