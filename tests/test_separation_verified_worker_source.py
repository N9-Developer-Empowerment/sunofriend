from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sunofriend._separation_verified_worker_source import _verified_worker_source


def _identity(value: bytes) -> dict[str, object]:
    return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}


def test_exact_verified_descriptor_is_the_python_script_input(tmp_path: Path) -> None:
    source = b"print('descriptor-worker-ok')\n"
    worker = tmp_path / "worker.py"
    worker.write_bytes(source)

    with _verified_worker_source(worker, expected_identity=_identity(source)) as stream:
        completed = subprocess.run(
            [sys.executable, "-B", "-"],
            stdin=stream,
            check=False,
            capture_output=True,
            text=True,
        )

    assert completed.returncode == 0
    assert completed.stdout == "descriptor-worker-ok\n"
    assert completed.stderr == ""


def test_descriptor_identity_mismatch_fails_before_execution(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    worker.write_bytes(b"pass\n")

    with pytest.raises(ValueError, match="descriptor identity differs"):
        with _verified_worker_source(
            worker,
            expected_identity={"bytes": 5, "sha256": "0" * 64},
        ):
            raise AssertionError("unreachable")


def test_path_replacement_during_execution_is_detected(tmp_path: Path) -> None:
    source = b"pass\n"
    worker = tmp_path / "worker.py"
    worker.write_bytes(source)

    with pytest.raises(RuntimeError, match="changed during execution"):
        with _verified_worker_source(worker, expected_identity=_identity(source)) as stream:
            assert stream.read() == source
            replacement = tmp_path / "replacement.py"
            replacement.write_bytes(source)
            replacement.replace(worker)


def test_linked_worker_is_rejected(tmp_path: Path) -> None:
    source = b"pass\n"
    original = tmp_path / "original.py"
    original.write_bytes(source)
    linked = tmp_path / "linked.py"
    os.link(original, linked)

    with pytest.raises(ValueError, match="single-link regular file"):
        with _verified_worker_source(linked, expected_identity=_identity(source)):
            raise AssertionError("unreachable")
