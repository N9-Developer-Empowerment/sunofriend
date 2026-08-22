#!/usr/bin/env python3
"""Plan or explicitly render one exact dry, uncorrected vocal comp."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_comp_render import (
    create_dry_vocal_comp_plan,
    create_dry_vocal_render_authorization,
    render_dry_vocal_comp,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--musical-state", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--render-authorization", type=Path)
    parser.add_argument(
        "--render-scope",
        required=True,
        choices=(
            "phrase_only",
            "reviewed_phrase_excerpt",
            "complete_state_timeline",
        ),
    )
    parser.add_argument("--phrase-id")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--authorization-out", type=Path)
    parser.add_argument("--confirm-dry-uncorrected-scope", action="store_true")
    parser.add_argument("--confirm-complete-intended-vocal-roster", action="store_true")
    parser.add_argument("--confirm-authorised-ai-fallback-render", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--confirm-dry-uncorrected-render", action="store_true")
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def main() -> int:
    args = _arguments()
    source_map = _read_json(args.source_map)
    if args.authorize:
        authorization = create_dry_vocal_render_authorization(
            args.musical_state,
            source_map,
            render_scope=args.render_scope,
            phrase_id=args.phrase_id,
            confirm_dry_uncorrected_scope=args.confirm_dry_uncorrected_scope,
            confirm_complete_intended_vocal_roster=(
                args.confirm_complete_intended_vocal_roster
            ),
            confirm_authorised_ai_fallback_render=(
                args.confirm_authorised_ai_fallback_render
            ),
        )
        if args.authorization_out is None:
            raise ValueError("--authorize requires --authorization-out")
        args.authorization_out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            args.authorization_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(authorization))
        print(
            json.dumps(
                {"authorization_document_sha256": authorization["document_sha256"]},
                sort_keys=True,
            )
        )
        return 0
    if args.render_authorization is None:
        raise ValueError("planning and execution require --render-authorization")
    authorization = _read_json(args.render_authorization)
    plan = create_dry_vocal_comp_plan(
        args.musical_state,
        source_map,
        authorization,
        render_scope=args.render_scope,
        phrase_id=args.phrase_id,
    )
    if not args.execute:
        print(canonical_json_bytes(plan).decode("utf-8"), end="")
        return 0
    if args.out_dir is None:
        raise ValueError("--execute requires --out-dir")
    if args.expected_plan_sha256 != plan["document_sha256"]:
        raise ValueError("--execute requires the exact current --expected-plan-sha256")
    result = render_dry_vocal_comp(
        args.musical_state,
        source_map,
        authorization,
        plan,
        out_dir=args.out_dir,
        confirm_dry_uncorrected_render=args.confirm_dry_uncorrected_render,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "render_scope": result["render_scope"],
                "result_document_sha256": result["document_sha256"],
                "review": str(args.out_dir / "REVIEW/dry-vocal-comp-review.html"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
