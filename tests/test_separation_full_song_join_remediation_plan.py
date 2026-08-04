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
    SCHEMA as ALIGNMENT_SCHEMA,
    STATUS as ALIGNMENT_STATUS,
)
from sunofriend._separation_full_song_join_remediation_plan import (
    POLICY_ID,
    REPORT_NAME as REMEDIATION_REPORT_NAME,
    SCHEMA,
    _plan_private_separation_full_song_join_remediation,
)
from sunofriend._separation_full_song_review import (
    SCHEMA as REVIEW_SCHEMA,
    STATUS as REVIEW_STATUS,
)
from sunofriend._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_NAME,
    REVIEW_SCHEMA as REVIEW_SEED_SCHEMA,
    SCHEMA as STITCH_SCHEMA,
    STATUS as STITCH_STATUS,
    _FALSE_PERMISSIONS,
)


SAMPLE_RATE = 44_100
FRAMES = 20 * SAMPLE_RATE


def test_join_remediation_plan_deduplicates_worker_windows_and_keeps_raw_control(
    tmp_path: Path,
) -> None:
    package, review, alignment = _evidence(tmp_path)
    output = tmp_path / REMEDIATION_REPORT_NAME

    result = _plan_private_separation_full_song_join_remediation(
        package,
        review,
        alignment,
        out=output,
    )

    assert result["schema"] == SCHEMA
    assert result["policy_id"] == POLICY_ID
    assert result["summary"] == {
        "human_rated_audible_role_join_count": 3,
        "unique_boundary_count": 2,
        "planned_model_call_count": 2,
        "target_roles": ["vocals", "instrumental"],
        "private_listener_notes_copied": False,
        "raw_control_count": 1,
        "repaired_candidate_count": 0,
    }
    assert [window["patch_target_roles"] for window in result["windows"]] == [
        ["vocals", "instrumental"],
        ["vocals"],
    ]
    assert [
        (window["source_start_frame"], window["source_end_frame"])
        for window in result["windows"]
    ] == [(0, 661_500), (220_500, 882_000)]
    assert [
        (window["patch_start_frame"], window["patch_end_frame"])
        for window in result["windows"]
    ] == [(264_600, 352_800), (573_300, 661_500)]
    assert result["required_future_review"] == {
        "blind_original_versus_repaired_boundary_role_pairs": 3,
        "repaired_patch_edge_role_checks": 6,
        "complete_song_roles": ["vocals", "instrumental", "reconstruction"],
        "automatic_preference_inference": False,
        "review_result_required_before_readiness_reassessment": True,
    }
    assert result["readiness"]["targeted_remediation_plan_ready"] is True
    assert result["readiness"]["repaired_candidates_created"] is False
    assert result["readiness"]["publication_ready"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    persisted = output.read_text(encoding="utf-8")
    assert str(package) not in persisted
    assert "listener note" not in persisted
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    document = json.loads(persisted)
    assert document["document_sha256"] == _document_sha256(document)
    assert "report" not in document


def test_join_remediation_plan_rejects_alignment_that_did_not_pass(
    tmp_path: Path,
) -> None:
    package, review, alignment = _evidence(tmp_path)
    document = json.loads(alignment.read_text(encoding="utf-8"))
    document["readiness"]["alignment_gate_passed"] = False
    document["document_sha256"] = _document_sha256(document)
    _write_private_json(alignment, document)

    with pytest.raises(ValueError, match="did not pass"):
        _plan_private_separation_full_song_join_remediation(
            package,
            review,
            alignment,
            out=tmp_path / "remediation.json",
        )


def test_join_remediation_plan_rejects_unexplained_reconstruction_join(
    tmp_path: Path,
) -> None:
    package, review, alignment = _evidence(tmp_path)
    document = json.loads(review.read_text(encoding="utf-8"))
    document["boundaries"][0]["ratings"]["reconstruction"] = "audible_join"
    document["boundary_summary"]["audible_join_boundaries_by_role"][
        "reconstruction"
    ] = [1]
    document["boundary_summary"]["rating_counts_by_role"]["reconstruction"] = {
        "audible_join": 1,
        "cannot_tell": 0,
        "clean": 1,
    }
    document["document_sha256"] = _document_sha256(document)
    _write_private_json(review, document)

    with pytest.raises(ValueError, match="require diagnosis"):
        _plan_private_separation_full_song_join_remediation(
            package,
            review,
            alignment,
            out=tmp_path / "remediation.json",
        )


def test_join_remediation_plan_rejects_changed_raw_audio(tmp_path: Path) -> None:
    package, review, alignment = _evidence(tmp_path)
    vocals = package / "STEMS/vocals.wav"
    vocals.write_bytes(vocals.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="artifact changed"):
        _plan_private_separation_full_song_join_remediation(
            package,
            review,
            alignment,
            out=tmp_path / "remediation.json",
        )


def _evidence(tmp_path: Path) -> tuple[Path, Path, Path]:
    package = tmp_path / "stitch"
    source_dir = package / "SOURCE"
    stems_dir = package / "STEMS"
    review_dir = package / "BOUNDARY-REVIEW"
    source_dir.mkdir(parents=True, mode=0o700)
    stems_dir.mkdir(mode=0o700)
    review_dir.mkdir(mode=0o700)

    time = np.arange(FRAMES, dtype=np.float64) / SAMPLE_RATE
    mono = 0.12 * np.sin(2.0 * np.pi * 220.0 * time)
    source = np.column_stack((mono, mono))
    arrays = {
        "source": source,
        "vocals": 0.35 * source,
        "instrumental": 0.65 * source,
        "reconstruction": source,
    }
    paths = {
        "source": source_dir / "source-44100.wav",
        "vocals": stems_dir / "vocals.wav",
        "instrumental": stems_dir / "instrumental.wav",
        "reconstruction": stems_dir / "reconstruction.wav",
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

    boundaries = [7 * SAMPLE_RATE, 14 * SAMPLE_RATE]
    commitment = hashlib.sha256(b"review-package").hexdigest()
    seed = {
        "schema": REVIEW_SEED_SCHEMA,
        "status": "unreviewed",
        "evidence_scope": "private_development_only",
        "package_commitment": commitment,
        "units": [
            {
                "boundary_index": index,
                "frame": frame,
                "seconds": frame / SAMPLE_RATE,
            }
            for index, frame in enumerate(boundaries, start=1)
        ],
        "permissions": dict(_FALSE_PERMISSIONS),
    }
    seed_path = review_dir / REVIEW_NAME
    _write_private_json(seed_path, seed)

    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": FRAMES,
        "duration_seconds": FRAMES / SAMPLE_RATE,
        "chunk_count": 3,
        "boundary_count": 2,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    stitch = {
        "schema": STITCH_SCHEMA,
        "status": STITCH_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_document_sha256": hashlib.sha256(b"plan").hexdigest(),
            "execution_state_sha256": hashlib.sha256(b"execution").hexdigest(),
        },
        "clock": clock,
        "artifacts": artifacts,
        "boundary_review": {
            "boundary_count": 2,
            "seed_sha256": _sha256(seed_path),
            "package_commitment": commitment,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
    }
    stitch["document_sha256"] = _document_sha256(stitch)
    stitch_path = package / STITCH_REPORT_NAME
    _write_private_json(stitch_path, stitch)

    ratings = [
        {
            "vocals": "audible_join",
            "instrumental": "audible_join",
            "reconstruction": "clean",
        },
        {
            "vocals": "audible_join",
            "instrumental": "clean",
            "reconstruction": "clean",
        },
    ]
    review = {
        "schema": REVIEW_SCHEMA,
        "status": REVIEW_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "review_seed_sha256": _sha256(seed_path),
            "package_commitment": commitment,
            "plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "execution_state_sha256": stitch["bindings"]["execution_state_sha256"],
        },
        "clock": clock,
        "boundary_summary": {
            "reviewed_boundaries": 2,
            "audible_join_boundaries_by_role": {
                "vocals": [1, 2],
                "instrumental": [1],
                "reconstruction": [],
            },
            "rating_counts_by_role": {
                "vocals": {"audible_join": 2, "cannot_tell": 0, "clean": 0},
                "instrumental": {
                    "audible_join": 1,
                    "cannot_tell": 0,
                    "clean": 1,
                },
                "reconstruction": {
                    "audible_join": 0,
                    "cannot_tell": 0,
                    "clean": 2,
                },
            },
        },
        "boundaries": [
            {
                "boundary_index": index,
                "frame": frame,
                "seconds": frame / SAMPLE_RATE,
                "ratings": rating,
                "notes": "listener note is private",
            }
            for index, (frame, rating) in enumerate(
                zip(boundaries, ratings),
                start=1,
            )
        ],
        "readiness": {
            "exact_duration_and_frame_count_verified": True,
            "full_song_and_boundary_listening_complete": True,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {"separator_selected": False},
    }
    review["document_sha256"] = _document_sha256(review)
    review_path = tmp_path / "review-result.json"
    _write_private_json(review_path, review)

    alignment = {
        "schema": ALIGNMENT_SCHEMA,
        "status": ALIGNMENT_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": artifacts["source"]["sha256"],
            "reconstruction_audio_sha256": artifacts["reconstruction"]["sha256"],
            "plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "execution_state_sha256": stitch["bindings"]["execution_state_sha256"],
        },
        "clock": clock,
        "readiness": {
            "alignment_gate_passed": True,
            "source_to_reconstruction_alignment_verified": True,
            "drift_acceptance_complete": True,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {"audio_created_or_mutated": False},
    }
    alignment["document_sha256"] = _document_sha256(alignment)
    alignment_path = tmp_path / "alignment-result.json"
    _write_private_json(alignment_path, alignment)

    package.chmod(0o700)
    os.chmod(tmp_path, stat.S_IMODE(tmp_path.stat().st_mode) & ~0o077)
    return package, review_path, alignment_path


def _write_private_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
