#!/usr/bin/env python3
"""Construct and strictly load the two approved query-challenger models.

This is deliberately a construction/load gate, not an inference worker. It
does not accept an audio path and never calls either model. The state-compatible
Banquet topology follows the MIT-licensed pinned Query Bandit source revision
recorded in the shared pure evidence contract.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
from typing import Any
import urllib.request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
import torch
import torchaudio

from sunofriend.separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_MODEL_LOAD_REPORT_SCHEMA,
    QUERY_MODEL_LOAD_REPORT_STATUS,
    query_model_load_report_sha256,
)
from sunofriend.separation_other_refinement_query_model_loading import (
    load_query_models,
)

EXPECTED_CHECKPOINT_IDENTITIES = {
    label: {
        "filename": checkpoint["file"],
        "bytes": checkpoint["bytes"],
        "sha256": checkpoint["sha256"],
    }
    for label, checkpoint in EXPECTED_CHECKPOINTS.items()
}
AUDIO_SUFFIXES = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--banquet", type=Path, required=True)
    parser.add_argument("--passt", type=Path, required=True)
    args = parser.parse_args()
    paths = {"banquet": args.banquet.resolve(), "passt": args.passt.resolve()}
    allowed_checkpoint_paths = frozenset(paths.values())
    network_attempts: list[str] = []
    audio_open_attempts: list[str] = []
    checkpoint_open_attempts: list[str] = []
    load_calls: list[str] = []

    def audit(event: str, event_args: tuple[Any, ...]) -> None:
        if event.startswith("socket."):
            network_attempts.append(event)
            raise RuntimeError(f"network operation forbidden during model load: {event}")
        if event == "open" and event_args:
            target = event_args[0]
            if isinstance(target, (str, bytes)):
                path = Path(target).resolve()
                text = str(path).lower()
                if text.endswith(AUDIO_SUFFIXES):
                    audio_open_attempts.append(text)
                    raise RuntimeError("audio open forbidden during model load")
                if text.endswith((".ckpt", ".pt", ".pth", ".safetensors")):
                    if path not in allowed_checkpoint_paths:
                        checkpoint_open_attempts.append(text)
                        raise RuntimeError("unapproved checkpoint open during model load")

    sys.addaudithook(audit)

    def deny_network(*_args: Any, **_kwargs: Any) -> Any:
        network_attempts.append("python_network_api")
        raise RuntimeError("network API forbidden during model load")

    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    urllib.request.urlopen = deny_network

    for label, path in paths.items():
        expected = EXPECTED_CHECKPOINT_IDENTITIES[label]
        if path.name != expected["filename"]:
            raise RuntimeError(f"{label} checkpoint filename differs")
        if path.stat().st_size != expected["bytes"] or _sha256(path) != expected["sha256"]:
            raise RuntimeError(f"{label} checkpoint identity differs")

    real_torch_load = torch.load

    def restricted_torch_load(path: str | Path, *args: Any, **kwargs: Any) -> Any:
        resolved = Path(path).resolve()
        if resolved not in allowed_checkpoint_paths:
            raise RuntimeError("torch.load path is outside the two approved checkpoints")
        if args or kwargs != {"weights_only": True, "map_location": "cpu"}:
            raise RuntimeError("torch.load must use the exact weights-only CPU contract")
        load_calls.append(str(resolved))
        return real_torch_load(resolved, weights_only=True, map_location="cpu")

    torch.load = restricted_torch_load
    loaded = load_query_models(paths, load_calls)
    if network_attempts or audio_open_attempts or checkpoint_open_attempts:
        raise RuntimeError("restricted model load crossed an effects boundary")

    report: dict[str, Any] = {
        "schema": QUERY_MODEL_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": QUERY_MODEL_LOAD_REPORT_STATUS,
        "source_revision": QUERY_BANDIT_SOURCE_REVISION,
        "runtime": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "torchaudio": torchaudio.__version__,
            "numpy": np.__version__,
        },
        "checkpoints": {
            label: {
                "file": expected["filename"],
                "bytes": expected["bytes"],
                "sha256": expected["sha256"],
            }
            for label, expected in EXPECTED_CHECKPOINT_IDENTITIES.items()
        },
        "models": loaded.evidence,
        "guards": {
            "os_network_denial_required": True,
            "network_attempts": len(network_attempts),
            "audio_open_attempts": len(audio_open_attempts),
            "unapproved_checkpoint_open_attempts": len(checkpoint_open_attempts),
            "restricted_torch_load_calls": len(load_calls),
            "pretrained_network_resolution": False,
        },
        "effects": {
            "checkpoint_loaded": True,
            "model_constructed": True,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    report["report_sha256"] = query_model_load_report_sha256(report)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
