#!/usr/bin/env python3
"""Stage and locally separate one authorised real-song excerpt."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_authorised_excerpt import (
    _run_authorised_separation_excerpt,
)
from sunofriend.ai_runtime import resolve_ai_python, resolve_demucs_model


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the excerpt declared in an owner-authorised corpus or a "
            "track-specifically authorised private-reference corpus, "
            "measure provider-pack alignment and run the existing private "
            "hash-pinned HTDemucs experiment. No result is activated."
        )
    )
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--python")
    args = parser.parse_args()

    result = _run_authorised_separation_excerpt(
        args.corpus,
        args.track_id,
        out_dir=args.out,
        checkpoint_path=resolve_demucs_model(args.checkpoint),
        python=resolve_ai_python(args.python),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "track": result["corpus"]["track_title"],
                "excerpt": result["excerpt"],
                "provider_alignment": {
                    pack: evidence["pack_sum_alignment"]
                    for pack, evidence in result["provider_packs"].items()
                },
                "local_separator": result["local_separator"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
