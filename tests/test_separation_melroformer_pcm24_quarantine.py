from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
    _validate_private_melroformer_pcm24_quarantine,
    _verify_private_melroformer_pcm24_quarantine,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_materializes_deterministic_owner_only_pcm24_and_verifies_sum(
    tmp_path: Path,
) -> None:
    source, vocals, instrumental = _arrays()
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = _materialize_private_melroformer_pcm24_quarantine(
        destination=first_root,
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
    )
    second = _materialize_private_melroformer_pcm24_quarantine(
        destination=second_root,
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
    )

    assert first == second
    assert first["status"] == "verified_quarantine_not_worker_bound"
    assert first["additive_reconstruction"]["maximum_integer_error_lsb"] <= 1
    assert first["boundary"]["outside_write_denial_proven"] is False
    assert first["boundary"]["bound_to_worker"] is False
    assert all(value is False for value in first["permissions"].values())
    for role in ("instrumental", "vocals"):
        path = first_root / "STEMS" / f"{role}.wav"
        assert path.stat().st_mode & 0o777 == 0o600
        assert hashlib.sha256(path.read_bytes()).hexdigest() == next(
            item["sha256"] for item in first["outputs"] if item["role"] == role
        )
    assert first_root.stat().st_mode & 0o777 == 0o700
    assert (first_root / "STEMS").stat().st_mode & 0o777 == 0o700
    assert "/Users/" not in repr(first)


def test_existing_destination_and_non_additive_or_out_of_range_arrays_fail(
    tmp_path: Path,
) -> None:
    source, vocals, instrumental = _arrays()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        _materialize_private_melroformer_pcm24_quarantine(
            destination=existing,
            source=source,
            vocals=vocals,
            instrumental=instrumental,
            np=np,
        )

    broken = instrumental.copy()
    broken[0, 0] += np.float32(0.01)
    with pytest.raises(ValueError, match="additive accounting"):
        _materialize_private_melroformer_pcm24_quarantine(
            destination=tmp_path / "non-additive",
            source=source,
            vocals=vocals,
            instrumental=broken,
            np=np,
        )

    loud = vocals.copy()
    loud[0, 0] = np.float32(1.0)
    with pytest.raises(ValueError, match="vocals array is invalid"):
        _materialize_private_melroformer_pcm24_quarantine(
            destination=tmp_path / "out-of-range",
            source=source,
            vocals=loud,
            instrumental=instrumental,
            np=np,
        )


def test_parent_reverification_rejects_modified_output(tmp_path: Path) -> None:
    source, vocals, instrumental = _arrays()
    root = tmp_path / "quarantine"
    evidence = _materialize_private_melroformer_pcm24_quarantine(
        destination=root,
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
    )
    claims = {
        item["role"]: {
            key: item[key]
            for key in ("role", "relative_path", "bytes", "sha256", "geometry")
        }
        for item in evidence["outputs"]
    }
    path = root / "STEMS" / "vocals.wav"
    contents = bytearray(path.read_bytes())
    contents[-1] ^= 1
    path.write_bytes(contents)
    os.chmod(path, 0o600)

    with pytest.raises(ValueError, match="hash differs"):
        _verify_private_melroformer_pcm24_quarantine(
            destination=root,
            source=source,
            claims=claims,
            np=np,
        )


def test_full_fifteen_second_geometry_fits_fixed_file_bound(tmp_path: Path) -> None:
    source = np.zeros((661_500, 2), dtype=np.float32)
    evidence = _materialize_private_melroformer_pcm24_quarantine(
        destination=tmp_path / "full-excerpt",
        source=source,
        vocals=source.copy(),
        instrumental=source.copy(),
        np=np,
    )

    assert evidence["source"]["frames"] == 661_500
    assert evidence["additive_reconstruction"]["maximum_integer_error_lsb"] == 0
    assert all(item["bytes"] == 3_969_044 for item in evidence["outputs"])


def test_resigned_permission_drift_is_rejected(tmp_path: Path) -> None:
    source, vocals, instrumental = _arrays()
    evidence = plain(
        _materialize_private_melroformer_pcm24_quarantine(
            destination=tmp_path / "quarantine",
            source=source,
            vocals=vocals,
            instrumental=instrumental,
            np=np,
        )
    )
    evidence["permissions"]["publication_permitted"] = True
    unsigned = dict(evidence)
    unsigned.pop("evidence_sha256")
    from sunofriend.separation_contract import _canonical_json_bytes

    evidence["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()
    with pytest.raises(ValueError, match="grants a permission"):
        _validate_private_melroformer_pcm24_quarantine(evidence)


def test_private_pcm24_quarantine_has_no_public_route() -> None:
    assert "private-melroformer-pcm24-quarantine" not in PUBLIC_COMMANDS
    assert "private-melroformer-pcm24-quarantine" not in DIRECT_TUI_COMMANDS


def _arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frames = 4_096
    timeline = np.arange(frames, dtype=np.float32) / np.float32(44_100.0)
    left = (0.3 * np.sin(2 * np.pi * 220 * timeline)).astype(np.float32)
    right = (0.25 * np.sin(2 * np.pi * 330 * timeline)).astype(np.float32)
    source = np.stack([left, right], axis=1)
    vocals = (source * np.float32(0.41)).astype(np.float32)
    instrumental = (source - vocals).astype(np.float32)
    return source, vocals, instrumental
