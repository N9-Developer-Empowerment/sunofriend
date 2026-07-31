from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend._separation_demucs_demo_fixture import (
    _create_private_demucs_demo_fixture,
    _document_sha256,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_is_copyright_safe_exact_and_deterministic() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = _create_private_demucs_demo_fixture(root / "first")
        second = _create_private_demucs_demo_fixture(root / "second")

        assert first["geometry"] == {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 352_800,
            "duration_seconds": 8.0,
        }
        assert (
            "no recordings, samples, lyrics or third-party audio"
            in first["source_kind"]
        )
        assert first["mapping"] == {
            "drums": ["kick", "snare", "hat"],
            "bass": ["bass"],
            "other": ["keys", "lead"],
            "vocals": [],
        }
        assert first["references"]["vocals"]["rms"] == 0.0
        assert first["references"]["vocals"]["silence_fraction"] == 1.0
        assert first["mixture"]["clipped_samples"] == 0
        assert first["mixture"]["sha256"] == second["mixture"]["sha256"]
        for role in ("bass", "drums", "other", "vocals"):
            assert (
                first["references"][role]["sha256"]
                == second["references"][role]["sha256"]
            )

        mixture, rate = soundfile.read(
            first["mixture_path"], dtype="float32", always_2d=True
        )
        reference_sum = np.zeros_like(mixture)
        for path in first["reference_paths"].values():
            reference, reference_rate = soundfile.read(
                path, dtype="float32", always_2d=True
            )
            assert reference_rate == rate
            reference_sum += reference
        error = mixture.astype("float64") - reference_sum.astype("float64")
        assert float(np.max(np.abs(error))) <= 2.0 / (1 << 23)
        persisted = json.loads(Path(first["manifest"]).read_text())
        assert persisted["document_sha256"] == _document_sha256(persisted)
        assert (Path(first["root"]).stat().st_mode & 0o777) == 0o700


def test_fixture_requires_a_fresh_root() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "fixture"
        _create_private_demucs_demo_fixture(root)
        with pytest.raises(FileExistsError, match="already exists"):
            _create_private_demucs_demo_fixture(root)


def test_fixture_manifest_hashes_every_persisted_reference() -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = _create_private_demucs_demo_fixture(Path(directory) / "fixture")
        assert result["mixture"]["sha256"] == _sha256(Path(result["mixture_path"]))
        for role, path in result["reference_paths"].items():
            assert result["references"][role]["sha256"] == _sha256(Path(path))
