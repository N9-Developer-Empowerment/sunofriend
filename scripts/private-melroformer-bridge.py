#!/usr/bin/env python3
"""Probe the approved private Kim Vocal 2 bridge without audio inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_melroformer_real_bridge import (
    _infer_private_melroformer_probe,
    _load_private_melroformer_model,
)
from sunofriend._separation_checkpoint_canonical import plain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--probe", action="store_true")
    action.add_argument("--synthetic-smoke", action="store_true")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    args = parser.parse_args()
    handle = _load_private_melroformer_model(
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
    )
    if args.probe:
        result = dict(handle.evidence)
    else:
        np = handle.np
        frames = 44_100
        timeline = np.arange(frames, dtype=np.float32) / np.float32(44_100.0)
        left = (
            0.18 * np.sin(2 * np.pi * 220 * timeline)
            + 0.07 * np.sin(2 * np.pi * 440 * timeline)
        ).astype(np.float32)
        right = (
            0.18 * np.sin(2 * np.pi * 220 * timeline + 0.15)
            + 0.07 * np.sin(2 * np.pi * 660 * timeline)
        ).astype(np.float32)
        source = np.stack([left, right], axis=1)
        observation = _infer_private_melroformer_probe(
            handle, source, sample_rate=44_100
        )
        result = {
            "bridge": dict(handle.evidence),
            "inference": plain(observation.evidence),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
