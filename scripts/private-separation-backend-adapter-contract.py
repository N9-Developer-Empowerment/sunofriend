#!/usr/bin/env python3
"""Audit and seal the private separation backend without running it."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_private_backend_adapter_contract import (
    _build_private_separation_backend_adapter_contract,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design-report", required=True)
    parser.add_argument("--coverage-report", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _build_private_separation_backend_adapter_contract(
        args.design_report,
        coverage_report_path=args.coverage_report,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "backend": {
                    "candidate_id": result["backend"]["candidate_id"],
                    "role_contract": result["backend"]["role_contract"],
                },
                "execution_boundary": result["execution_boundary"],
                "readiness": result["readiness"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
