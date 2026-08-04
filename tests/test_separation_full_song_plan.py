from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_full_song_plan import (
    POLICY_ID,
    REPORT_NAME,
    SCHEMA,
    STATUS,
    __all__,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_melroformer_real_bridge import (
    _load_private_authorised_excerpt_pcm24,
)


def _corpus(
    root: Path,
    *,
    channels: int = 2,
    frames: int = 18_000,
    sample_rate: int = 44_100,
) -> Path:
    track = root / "corpus" / "example-song"
    source = track / "ORIGINAL" / "song.wav"
    source.parent.mkdir(parents=True)
    time = np.arange(frames, dtype=np.float64) / sample_rate
    base = (0.25 * np.sin(2.0 * np.pi * 220.0 * time)).astype("float32")
    audio = np.column_stack([base] * channels)
    soundfile.write(source, audio, sample_rate, subtype="PCM_24")
    document = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {
            "name": "Owner",
            "soundcloud_profile": "https://example.test/owner",
        },
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "download, study, transform and reuse",
            "condition": "credit Owner",
            "recorded_on": "2026-08-04",
        },
        "tracks": [
            {
                "id": "example",
                "title": "Example",
                "directory": "example-song",
                "evaluation_state": "ready_for_excerpt_selection",
            }
        ],
    }
    manifest = root / "corpus" / "corpus.json"
    manifest.write_text(json.dumps(document) + "\n", encoding="utf-8")
    return manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_corpus(root: Path) -> Path:
    manifest = _corpus(root, frames=12_000)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["schema"] = "sunofriend.private-reference-separation-corpus.v1"
    document.pop("artist")
    document["permission"] = {
        "status": "not_recorded_in_manifest",
        "directory_presence_is_not_processing_authority": True,
        "repository_distribution": False,
        "public_demo_use": False,
    }
    track = document["tracks"][0]
    track["display_name"] = track.pop("title")
    track["evaluation_state"] = "ready_for_private_excerpt_selection"
    track["private_processing_authority"] = {
        "status": "user_authorised",
        "scope": "private_local_evaluation_only",
        "recorded_on": "2026-08-04",
        "repository_distribution": False,
        "public_demo_use": False,
    }
    manifest.write_text(json.dumps(document) + "\n", encoding="utf-8")
    return manifest


def test_full_song_plan_is_gap_free_and_worker_compatible(tmp_path: Path) -> None:
    manifest = _corpus(tmp_path)
    out = tmp_path / "plan"

    result = _prepare_private_separation_full_song_plan(
        manifest,
        "example",
        out_dir=out,
        maximum_chunk_frames=9_000,
    )

    assert __all__ == ()
    assert result["schema"] == SCHEMA
    assert result["status"] == STATUS
    assert result["policy_id"] == POLICY_ID
    assert result["chunking"] == {
        "maximum_chunk_frames": 9_000,
        "maximum_chunk_seconds": 9_000 / 44_100,
        "chunk_count": 2,
        "coverage_start_frame": 0,
        "coverage_end_frame": 18_000,
        "gap_frames": 0,
        "overlap_frames": 0,
        "contiguous_exact_frame_coverage": True,
        "independent_worker_invocations_required": 2,
        "stitching_not_yet_run": True,
    }
    assert [
        (chunk["start_frame"], chunk["end_frame"])
        for chunk in result["chunks"]
    ] == [(0, 9_000), (9_000, 18_000)]
    assert result["readiness"]["full_song_duration_and_alignment_gate_passed"] is False
    assert result["effects"]["model_run"] is False
    assert result["effects"]["separator_output_created"] is False
    assert all(value is False for value in result["permissions"].values())
    assert Path(result["report"]) == out / REPORT_NAME
    persisted = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert "report" not in persisted
    assert "output_directory" not in persisted

    arrays = []
    for chunk in result["chunks"]:
        report = out / chunk["authorisation_report"]["path"]
        assert _sha256(report) == chunk["authorisation_report"]["sha256"]
        audio, evidence = _load_private_authorised_excerpt_pcm24(
            np,
            report_path=report,
            expected_report_sha256=chunk["authorisation_report"]["sha256"],
        )
        arrays.append(audio)
        assert evidence["track_id"] == "example"
        assert evidence["frames"] == 9_000
        assert evidence["rights_authority"] == "creator_and_copyright_holder"
    combined = np.concatenate(arrays, axis=0)
    assert combined.shape == (18_000, 2)
    # The plan hashes exact PCM24 integer samples rather than float amplitudes.
    int_arrays = [
        soundfile.read(
            out / chunk["audio_artifact"]["path"],
            dtype="int32",
            always_2d=True,
        )[0]
        for chunk in result["chunks"]
    ]
    integer_digest = hashlib.sha256(
        np.concatenate(int_arrays, axis=0).astype("<i4").tobytes()
    ).hexdigest()
    assert integer_digest == result["canonical_clock"]["pcm24_int32_sequence_sha256"]


def test_full_song_plan_duplicates_mono_without_running_model(tmp_path: Path) -> None:
    manifest = _corpus(tmp_path, channels=1, frames=12_000)
    result = _prepare_private_separation_full_song_plan(
        manifest,
        "example",
        out_dir=tmp_path / "mono-plan",
        maximum_chunk_frames=12_000,
    )

    assert result["source"]["geometry"]["channels"] == 1
    assert result["canonical_clock"]["channels"] == 2
    assert (
        result["canonical_clock"]["derivation"]["channel_policy"]
        == "mono duplicated to left and right"
    )
    assert result["chunking"]["chunk_count"] == 1
    assert result["readiness"]["worker_runs_complete"] is False


def test_full_song_plan_resamples_the_complete_clock_before_partitioning(
    tmp_path: Path,
) -> None:
    manifest = _corpus(tmp_path, frames=24_000, sample_rate=48_000)
    result = _prepare_private_separation_full_song_plan(
        manifest,
        "example",
        out_dir=tmp_path / "resampled-plan",
        maximum_chunk_frames=12_000,
    )

    assert result["source"]["geometry"]["frames"] == 24_000
    assert result["canonical_clock"]["frames"] == 22_050
    assert result["canonical_clock"]["duration_seconds"] == 0.5
    assert result["canonical_clock"]["end_error_seconds"] == 0.0
    assert result["chunking"]["chunk_count"] == 2
    assert [chunk["frames"] for chunk in result["chunks"]] == [11_025, 11_025]
    assert result["canonical_clock"]["derivation"]["algorithm"].startswith(
        "scipy.signal.resample_poly"
    )


def test_full_song_plan_preserves_track_specific_private_authority(
    tmp_path: Path,
) -> None:
    manifest = _private_corpus(tmp_path)
    out = tmp_path / "private-plan"
    result = _prepare_private_separation_full_song_plan(
        manifest,
        "example",
        out_dir=out,
        maximum_chunk_frames=12_000,
    )

    assert (
        result["corpus"]["rights_authority"]
        == "user_authorised_private_local_evaluation"
    )
    chunk = result["chunks"][0]
    audio, evidence = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=out / chunk["authorisation_report"]["path"],
        expected_report_sha256=chunk["authorisation_report"]["sha256"],
    )
    assert audio.shape == (12_000, 2)
    assert (
        evidence["rights_authority"]
        == "user_authorised_private_local_evaluation"
    )


def test_full_song_plan_rejects_existing_output_and_surround_source(tmp_path: Path) -> None:
    manifest = _corpus(tmp_path)
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        _prepare_private_separation_full_song_plan(
            manifest,
            "example",
            out_dir=out,
        )

    surround_manifest = _corpus(tmp_path / "surround", channels=3)
    with pytest.raises(ValueError, match="mono or stereo"):
        _prepare_private_separation_full_song_plan(
            surround_manifest,
            "example",
            out_dir=tmp_path / "surround-plan",
        )


@pytest.mark.parametrize("value", [True, 8_191, 661_501])
def test_full_song_plan_rejects_chunk_bounds(tmp_path: Path, value: int) -> None:
    manifest = _corpus(tmp_path)
    with pytest.raises(ValueError, match="worker bound"):
        _prepare_private_separation_full_song_plan(
            manifest,
            "example",
            out_dir=tmp_path / f"bad-{value}",
            maximum_chunk_frames=value,
        )
