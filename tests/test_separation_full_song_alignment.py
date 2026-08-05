from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_full_song_alignment import (
    POLICY_ID,
    SCHEMA,
    _measure_private_separation_full_song_alignment,
)
from sunofriend._separation_full_song_stitch import (
    REPORT_NAME,
    SCHEMA as STITCH_SCHEMA,
    STATUS as STITCH_STATUS,
    _FALSE_PERMISSIONS,
)


SAMPLE_RATE = 44_100
FRAMES = 6 * SAMPLE_RATE


def test_alignment_report_passes_exact_clock_reconstruction(tmp_path: Path) -> None:
    package = _package(tmp_path, shift_frames=0)

    result = _measure_private_separation_full_song_alignment(
        package,
        out=tmp_path / "alignment.json",
    )

    assert result["schema"] == SCHEMA
    assert result["policy_id"] == POLICY_ID
    assert len(result["windows"]) == 9
    assert result["summary"]["eligible_window_count"] == 9
    assert result["summary"]["maximum_absolute_lag_milliseconds"] == 0.0
    assert result["summary"]["lag_spread_milliseconds"] == 0.0
    assert result["readiness"] == {
        "exact_source_and_reconstruction_clock_verified": True,
        "source_to_reconstruction_alignment_verified": True,
        "drift_acceptance_complete": True,
        "alignment_gate_passed": True,
        "separator_accuracy_established": False,
        "publication_ready": False,
    }
    assert result["interpretation"]["alignment_is_separator_quality"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert stat.S_IMODE((tmp_path / "alignment.json").stat().st_mode) == 0o600
    persisted = (tmp_path / "alignment.json").read_text(encoding="utf-8")
    assert str(package) not in persisted


def test_alignment_report_fails_declared_lag_threshold(tmp_path: Path) -> None:
    package = _package(tmp_path, shift_frames=int(0.05 * SAMPLE_RATE))

    result = _measure_private_separation_full_song_alignment(
        package,
        out=tmp_path / "alignment.json",
    )

    assert result["summary"]["eligible_window_count"] == 9
    assert result["summary"]["maximum_absolute_lag_milliseconds"] >= 40.0
    assert result["readiness"]["source_to_reconstruction_alignment_verified"] is False
    assert result["readiness"]["drift_acceptance_complete"] is False
    assert result["readiness"]["alignment_gate_passed"] is False


def test_alignment_report_rejects_changed_bound_audio(tmp_path: Path) -> None:
    package = _package(tmp_path, shift_frames=0)
    reconstruction = package / "STEMS/reconstruction.wav"
    reconstruction.write_bytes(reconstruction.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="artifact changed"):
        _measure_private_separation_full_song_alignment(
            package,
            out=tmp_path / "alignment.json",
        )


def test_alignment_report_creates_owner_only_fresh_parent(tmp_path: Path) -> None:
    package = _package(tmp_path, shift_frames=0)
    output = tmp_path / "private-alignment" / "alignment.json"

    _measure_private_separation_full_song_alignment(package, out=output)

    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_alignment_report_rejects_existing_shared_parent(tmp_path: Path) -> None:
    package = _package(tmp_path, shift_frames=0)
    output_root = tmp_path / "shared-alignment"
    output_root.mkdir(mode=0o755)

    with pytest.raises(ValueError, match="not an owner-only directory"):
        _measure_private_separation_full_song_alignment(
            package,
            out=output_root / "alignment.json",
        )


def _package(tmp_path: Path, *, shift_frames: int) -> Path:
    package = tmp_path / "stitch"
    source_dir = package / "SOURCE"
    stems_dir = package / "STEMS"
    source_dir.mkdir(parents=True, mode=0o700)
    stems_dir.mkdir(mode=0o700)
    time = np.arange(FRAMES, dtype=np.float64) / SAMPLE_RATE
    carrier = np.sin(2.0 * np.pi * (110.0 * time + 15.0 * time * time))
    movement = 0.6 + 0.3 * np.sin(2.0 * np.pi * 1.7 * time)
    accents = np.where((time % 0.71) < 0.08, 0.25, 0.0)
    mono = 0.22 * carrier * movement + accents * np.sin(2.0 * np.pi * 880.0 * time)
    source = np.column_stack((mono, 0.93 * mono))
    if shift_frames:
        reconstruction = np.zeros_like(source)
        reconstruction[shift_frames:] = source[:-shift_frames]
    else:
        reconstruction = 0.82 * source
    vocals = 0.35 * reconstruction
    instrumental = reconstruction - vocals
    paths = {
        "source": source_dir / "source-44100.wav",
        "vocals": stems_dir / "vocals.wav",
        "instrumental": stems_dir / "instrumental.wav",
        "reconstruction": stems_dir / "reconstruction.wav",
    }
    arrays = {
        "source": source,
        "vocals": vocals,
        "instrumental": instrumental,
        "reconstruction": reconstruction,
    }
    artifacts = {}
    for role, path in paths.items():
        soundfile.write(path, arrays[role], SAMPLE_RATE, subtype="PCM_24")
        path.chmod(0o600)
        artifacts[role] = {
            "path": path.relative_to(package).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "frames": FRAMES,
                "sample_width_bytes": 3,
            },
        }
    document = {
        "schema": STITCH_SCHEMA,
        "status": STITCH_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_document_sha256": hashlib.sha256(b"plan").hexdigest(),
            "execution_state_sha256": hashlib.sha256(b"execution").hexdigest(),
        },
        "clock": {
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": FRAMES,
            "duration_seconds": FRAMES / SAMPLE_RATE,
            "chunk_count": 2,
            "boundary_count": 1,
            "gap_frames": 0,
            "overlap_frames": 0,
            "crossfade_frames": 0,
        },
        "artifacts": artifacts,
        "boundary_review": {"boundary_count": 1},
        "permissions": dict(_FALSE_PERMISSIONS),
    }
    document["document_sha256"] = _document_sha256(document)
    report = package / REPORT_NAME
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report.chmod(0o600)
    package.chmod(0o700)
    os.chmod(tmp_path, stat.S_IMODE(tmp_path.stat().st_mode) & ~0o077)
    return package
