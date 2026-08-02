from __future__ import annotations

import hashlib
import json
import os
import signal


_TRANSPORT_FDS = (3, 4, 5)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
        + b"\n"
    )


def _harden_transport_descriptors() -> None:
    for descriptor in _TRANSPORT_FDS:
        os.set_inheritable(descriptor, False)


def main() -> int:
    _harden_transport_descriptors()
    descendant = os.fork()
    if descendant == 0:
        for descriptor in _TRANSPORT_FDS:
            os.close(descriptor)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            signal.pause()

    request = os.pread(3, 65_536, 0)
    checkpoint = os.pread(5, 65_536, 0)
    document = {
        "schema": "sunofriend.native-spawn-descendant-canary.v1",
        "ok": True,
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "descendant_started": descendant > 0,
        "request_sha256": hashlib.sha256(request).hexdigest(),
        "checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(),
    }
    payload = _canonical_bytes(document)
    os.pwrite(4, payload, 0)
    os.ftruncate(4, len(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
