#!/usr/bin/env python3
"""Run one approved, network-denied fine-stem downstream-MIDI canary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_midi_canary import (  # noqa: E402
    execute_fine_stem_midi_canary,
)


class _NetworkGuard:
    def __init__(self) -> None:
        self.attempts: list[str] = []
        self.local_socket_constructions = 0

    def _audit(self, event: str, _args: tuple[Any, ...]) -> None:
        if event == "socket.__new__":
            self.local_socket_constructions += 1
            return
        if event.startswith("socket."):
            self.attempts.append(event)
            raise RuntimeError("network operation forbidden in downstream-MIDI canary")

    def _deny(self, *_args: Any, **_kwargs: Any) -> Any:
        self.attempts.append("python_network_api")
        raise RuntimeError("network API forbidden in downstream-MIDI canary")

    def install(self) -> None:
        sys.addaudithook(self._audit)
        socket.create_connection = self._deny
        socket.getaddrinfo = self._deny
        urllib.request.urlopen = self._deny

    def report(self) -> dict[str, Any]:
        return {
            "provider": "/usr/bin/sandbox-exec",
            "profile": "(version 1)(deny network*)(allow default)",
            "os_network_denial_enforced": True,
            "python_network_attempts": len(self.attempts),
            "local_socket_constructions": self.local_socket_constructions,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("integration_root", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--network-denial-enforced", action="store_true", help=argparse.SUPPRESS
    )
    return parser


def _worker(args: argparse.Namespace) -> int:
    if not args.network_denial_enforced:
        raise RuntimeError("downstream-MIDI worker requires OS network denial")
    guard = _NetworkGuard()
    guard.install()
    from sunofriend.render import render_midi_to_wav
    from sunofriend.transcribe_pitched import transcribe_pitched_stem

    result = execute_fine_stem_midi_canary(
        args.plan,
        args.integration_root,
        out_dir=args.out,
        expected_plan_sha256=args.expected_plan_sha256,
        transcribe=transcribe_pitched_stem,
        render=render_midi_to_wav,
        network_observation=guard.report,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "document_sha256": result["document_sha256"],
                "attempts": len(result["attempts"]),
                "report": str(
                    args.out / "TECHNICAL/MIDI-CANARY-REPORT.json"
                ),
                "review": str(args.out / "REVIEW/midi_review.html"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _coordinator(args: argparse.Namespace) -> int:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise RuntimeError("macOS sandbox-exec is required for network denial")
    command = [
        str(sandbox),
        "-p",
        "(version 1)(deny network*)(allow default)",
        sys.executable,
        str(Path(__file__).resolve()),
        str(args.plan),
        str(args.integration_root),
        "--out",
        str(args.out),
        "--expected-plan-sha256",
        args.expected_plan_sha256,
        "--worker",
        "--network-denial-enforced",
    ]
    environment = dict(os.environ)
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "TF_CPP_MIN_LOG_LEVEL": "2",
        }
    )
    completed = subprocess.run(command, env=environment, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "the single downstream-MIDI canary attempt failed; no retry was run"
        )
    return 0


def main() -> int:
    args = _parser().parse_args()
    if args.worker:
        return _worker(args)
    return _coordinator(args)


if __name__ == "__main__":
    raise SystemExit(main())
