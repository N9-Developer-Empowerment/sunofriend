"""Fixed blocking worker for native-owner exception cleanup canaries."""

from __future__ import annotations

import os
import signal
import time


_TRANSPORT_FDS = (3, 4, 5)


def _harden_transport_descriptors() -> None:
    for descriptor in _TRANSPORT_FDS:
        os.set_inheritable(descriptor, False)


def main() -> int:
    _harden_transport_descriptors()
    marker = f"{os.getpid()}\n".encode("ascii")
    written = os.pwrite(4, marker, 0)
    if written != len(marker):
        raise RuntimeError("blocking owner-canary marker write was incomplete")
    os.ftruncate(4, len(marker))
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
