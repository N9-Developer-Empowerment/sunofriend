#!/usr/bin/env python3
"""Fixed private MelRoFormer worker for synthetic or authorised evaluation."""

from __future__ import annotations

import argparse
import errno
import json
import os
import socket
import sys
from pathlib import Path

import numpy as np

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
)
from sunofriend._separation_melroformer_real_bridge import (
    _infer_private_melroformer_excerpt,
    _load_private_authorised_excerpt,
    _load_private_melroformer_model,
)
from sunofriend._separation_melroformer_worker_sandbox import (
    WORKER_RELATIVE_PATH,
    _synthetic_arrays,
)
from sunofriend._separation_python_import_closure import (
    _capture_python_import_closure_claim,
    _mark_python_import_closure_stable,
    _melroformer_python_import_roots,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--synthetic-canary", action="store_true")
    action.add_argument("--authorised-excerpt", type=Path, metavar="REPORT")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--outside-write-canary", type=Path, required=True)
    parser.add_argument("--authorisation-report-sha256")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--companion-root", type=Path)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--bind-python-import-closure", action="store_true")
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()

    real_values = (
        args.authorisation_report_sha256,
        args.source_root,
        args.checkpoint,
        args.companion_root,
    )
    if args.authorised_excerpt and any(value is None for value in real_values):
        parser.error(
            "--authorised-excerpt requires --authorisation-report-sha256, "
            "--source-root, --checkpoint and --companion-root"
        )
    if args.synthetic_canary and any(value is not None for value in real_values):
        parser.error("real-model arguments are invalid with --synthetic-canary")
    if args.bind_python_import_closure and (
        args.synthetic_canary or args.repository_root is None
    ):
        parser.error(
            "--bind-python-import-closure requires an authorised excerpt and "
            "--repository-root"
        )
    if not args.bind_python_import_closure and args.repository_root is not None:
        parser.error("--repository-root requires --bind-python-import-closure")

    network = _network_canary()
    fork = _fork_canary()
    outside_write = _outside_write_canary(args.outside_write_canary)
    if any(value != errno.EPERM for value in (network, fork, outside_write)):
        raise RuntimeError("MelRoFormer worker isolation canary did not return EPERM")

    if args.synthetic_canary:
        source, vocals, instrumental = _synthetic_arrays(np)
        schema = "sunofriend.private-melroformer-synthetic-worker-child.v1"
        model_evidence = None
    else:
        handle = _load_private_melroformer_model(
            source_root=args.source_root,
            checkpoint_path=args.checkpoint,
            companion_root=args.companion_root,
            device=args.device,
        )
        source, authorisation = _load_private_authorised_excerpt(
            handle,
            report_path=args.authorised_excerpt,
            expected_report_sha256=args.authorisation_report_sha256,
        )
        observation = _infer_private_melroformer_excerpt(
            handle,
            source,
            sample_rate=44_100,
        )
        vocals = observation.vocals
        instrumental = observation.instrumental
        schema = "sunofriend.private-melroformer-authorised-worker-child.v1"
        model_evidence = {
            "authorisation": plain(authorisation),
            "bridge": plain(handle.evidence),
            "inference": plain(observation.evidence),
        }
    quarantine = _materialize_private_melroformer_pcm24_quarantine(
        destination=args.destination,
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
    )
    result = {
        "schema": schema,
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
    if model_evidence is not None:
        result["model"] = model_evidence
    closure = None
    if args.bind_python_import_closure:
        main_module = sys.modules["__main__"]
        main_module.__file__ = str(
            (args.repository_root / WORKER_RELATIVE_PATH).resolve(strict=True)
        )
        roots = _melroformer_python_import_roots(
            repository_root=args.repository_root,
            source_root=args.source_root,
            runtime_environment_root=sys.prefix,
            base_runtime_root=sys.base_prefix,
        )
        closure = _capture_python_import_closure_claim(roots=roots)
        result["schema"] = (
            "sunofriend.private-melroformer-authorised-worker-import-closure-child.v1"
        )
        result["import_closure"] = plain(closure)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if closure is not None:
        stable = _mark_python_import_closure_stable(closure)
        result["import_closure"] = plain(stable)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    print(encoded)
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
