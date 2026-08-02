#!/usr/bin/env python3
"""Fixed fd3-fd7 native Kim Vocal 2 worker entrypoint."""

# ruff: noqa: E402

from __future__ import annotations

import os


# This is the first effectful user-code action. CPython and site initialisation
# have already run; the separately measured native launcher owns the mapping.
for _transport_descriptor in (3, 4, 5, 6, 7):
    os.set_inheritable(_transport_descriptor, False)
del _transport_descriptor

import sys
from pathlib import Path


_WORKER_PATH = Path(__file__).resolve(strict=True)
_REPOSITORY_ROOT = _WORKER_PATH.parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))

from sunofriend._separation_melroformer_native_worker import (
    _run_private_melroformer_native_worker,
)


def main() -> int:
    try:
        return _run_private_melroformer_native_worker(
            worker_path=_WORKER_PATH,
            repository_root=_REPOSITORY_ROOT,
        )
    except BaseException:
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
