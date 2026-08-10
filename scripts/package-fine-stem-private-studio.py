#!/usr/bin/env python3
"""Package reviewed six-role excerpts for private Studio audio audition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_studio_package import (  # noqa: E402
    build_private_studio_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("integration_root", type=Path)
    parser.add_argument("integration_outcome", type=Path)
    parser.add_argument("midi_canary_root", type=Path)
    parser.add_argument("midi_outcome", type=Path)
    parser.add_argument("provider_synth_midi_outcome", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = build_private_studio_package(
        args.integration_root,
        args.integration_outcome,
        args.midi_canary_root,
        args.midi_outcome,
        args.provider_synth_midi_outcome,
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "document_sha256": result["document_sha256"],
                "case_count": result["case_count"],
                "audio_files_copied": result["effects"]["private_audio_files_copied"],
                "source_selected": bool(result["effects"]["source_selections"]),
                "midi_created": bool(result["effects"]["midi_files_written"]),
                "public_activation": bool(result["effects"]["public_activations"]),
                "output": str(args.out.expanduser().absolute()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
