#!/usr/bin/env python3
"""Run one approved, local-only MelRoFormer excerpt under the fixed sandbox."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import resource
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    parser.add_argument("--authorised-excerpt", type=Path, required=True)
    parser.add_argument("--authorisation-report-sha256", required=True)
    parser.add_argument("--staging-directory", type=Path, required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--bind-python-import-closure", action="store_true")
    parser.add_argument("--observe-outbound-attempts", action="store_true")
    parser.add_argument("--bind-native-image-inventory", action="store_true")
    parser.add_argument("--bind-real-worker-supervision", action="store_true")
    args = parser.parse_args()

    outer_open_descriptors = (
        _open_descriptors() if args.bind_real_worker_supervision else None
    )
    from sunofriend._separation_checkpoint_canonical import plain
    from sunofriend._separation_melroformer_authorised_worker import (
        _run_private_melroformer_authorised_worker,
    )

    evidence = _run_private_melroformer_authorised_worker(
        repository_root=args.repository_root,
        runtime_path=args.runtime,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        authorisation_report_path=args.authorised_excerpt,
        expected_authorisation_report_sha256=args.authorisation_report_sha256,
        staging_directory=args.staging_directory,
        device=args.device,
        bind_python_import_closure=args.bind_python_import_closure,
        observe_outbound_attempts=args.observe_outbound_attempts,
        bind_native_image_inventory=args.bind_native_image_inventory,
        bind_real_worker_supervision=args.bind_real_worker_supervision,
        outer_supervisor_open_descriptors=outer_open_descriptors,
    )
    document = plain(evidence)
    _write_private_observation(
        args.staging_directory / "authorised-worker-observation.json",
        document,
    )
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


def _open_descriptors() -> list[int]:
    """Observe the launcher's descriptor boundary before Sunofriend imports."""

    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    limit = 1_048_576 if soft_limit == resource.RLIM_INFINITY else int(soft_limit)
    descriptors: list[int] = []
    for descriptor in range(limit):
        try:
            fcntl.fcntl(descriptor, fcntl.F_GETFD)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        descriptors.append(descriptor)
    return descriptors


def _write_private_observation(path: Path, document: object) -> None:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if path.stat().st_mode & 0o777 != 0o600 or path.read_bytes() != payload:
        raise RuntimeError("MelRoFormer worker observation persistence differs")


if __name__ == "__main__":
    raise SystemExit(main())
