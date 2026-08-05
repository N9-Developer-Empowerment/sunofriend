#!/usr/bin/env python3
"""Authorize a reviewed separation control for one bounded private pilot."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_pragmatic_private_pilot import (
    _authorize_pragmatic_private_pilot,
)


def _yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    raise argparse.ArgumentTypeError("expected yes or no")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant-review-result", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--variant-review-package-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--variant-execution-dir", required=True)
    parser.add_argument(
        "--overall-audio-quality", required=True, choices=("good", "good_enough", "good_or_good_enough")
    )
    parser.add_argument(
        "--listener-assessed-separator-accuracy", required=True, choices=("good", "good_enough", "good_or_good_enough")
    )
    parser.add_argument("--joins-generally-noticeable", required=True, type=_yes_no)
    parser.add_argument(
        "--joins-detectable-when-cued-with-concentrated-headphones",
        required=True,
        type=_yes_no,
    )
    parser.add_argument("--joins-reduce-musical-usefulness", required=True, type=_yes_no)
    parser.add_argument("--patch-edge-beat-ambiguity-present", required=True, type=_yes_no)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _authorize_pragmatic_private_pilot(
        args.variant_review_result,
        reviewed_export_path=args.reviewed_export,
        variant_review_package_dir=args.variant_review_package_dir,
        plan_path=args.plan,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        variant_execution_dir=args.variant_execution_dir,
        overall_audio_quality=args.overall_audio_quality,
        listener_assessed_separator_accuracy=args.listener_assessed_separator_accuracy,
        joins_generally_noticeable=args.joins_generally_noticeable,
        joins_detectable_when_cued_with_concentrated_headphones=(
            args.joins_detectable_when_cued_with_concentrated_headphones
        ),
        joins_reduce_musical_usefulness=args.joins_reduce_musical_usefulness,
        patch_edge_beat_ambiguity_present=args.patch_edge_beat_ambiguity_present,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
