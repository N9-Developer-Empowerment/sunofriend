#!/usr/bin/env python3
"""Create a private MIDI/WAV validation from one activated reviewed separation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sunofriend._separation_reviewed_output_midi_validation import (
    _validate_reviewed_output_midi_and_interpretation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--import-assessment", required=True, type=Path)
    parser.add_argument("--review-equivalence", required=True, type=Path)
    parser.add_argument("--reviewed-export", required=True, type=Path)
    parser.add_argument("--reviewed-package-dir", required=True, type=Path)
    parser.add_argument("--candidate-package-report", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--soundfont", default=None, type=Path)
    parser.add_argument("--max-iterations", default=8, type=int)
    parser.add_argument(
        "--confirm-reviewed-stems-useful",
        required=True,
        action="store_true",
    )
    parser.add_argument(
        "--confirm-private-midi-validation",
        required=True,
        action="store_true",
    )
    args = parser.parse_args()
    result = asyncio.run(
        _validate_reviewed_output_midi_and_interpretation(
            args.project_root,
            assessment_path=args.import_assessment,
            equivalence_path=args.review_equivalence,
            reviewed_export_path=args.reviewed_export,
            reviewed_package_dir=args.reviewed_package_dir,
            candidate_package_report_path=args.candidate_package_report,
            out_dir=args.out_dir,
            soundfont_path=args.soundfont,
            max_iterations=args.max_iterations,
            confirm_reviewed_stems_useful=args.confirm_reviewed_stems_useful,
            confirm_private_midi_validation=args.confirm_private_midi_validation,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
