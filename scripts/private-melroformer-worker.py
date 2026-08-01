#!/usr/bin/env python3
"""Fixed private MelRoFormer worker; currently synthetic canary only."""

from __future__ import annotations

import argparse
import errno
import json
import os
import socket
from pathlib import Path

import numpy as np

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
)
from sunofriend._separation_melroformer_worker_sandbox import _synthetic_arrays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-canary", action="store_true", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--outside-write-canary", type=Path, required=True)
    args = parser.parse_args()

    network = _network_canary()
    fork = _fork_canary()
    outside_write = _outside_write_canary(args.outside_write_canary)
    if any(value != errno.EPERM for value in (network, fork, outside_write)):
        raise RuntimeError("synthetic worker isolation canary did not return EPERM")
    source, vocals, instrumental = _synthetic_arrays(np)
    quarantine = _materialize_private_melroformer_pcm24_quarantine(
        destination=args.destination,
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
    )
    result = {
        "schema": "sunofriend.private-melroformer-synthetic-worker-child.v1",
        "status": "complete",
        "canaries": {
            "network_connect_ex": network,
            "network_errno_name": errno.errorcode[network],
            "process_fork_errno": fork,
            "process_fork_errno_name": errno.errorcode[fork],
            "outside_write_errno": outside_write,
            "outside_write_errno_name": errno.errorcode[outside_write],
        },
        "quarantine": plain(quarantine),
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def _network_canary() -> int:
    attached = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        return attached.connect_ex(("127.0.0.1", 9))
    finally:
        attached.close()


def _fork_canary() -> int:
    try:
        child = os.fork()
    except OSError as error:
        return error.errno or 0
    if child == 0:
        os._exit(97)
    os.waitpid(child, 0)
    return 0


def _outside_write_canary(path: Path) -> int:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        return error.errno or 0
    else:
        os.close(descriptor)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
