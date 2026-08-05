from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile

import sunofriend._separation_private_render_review_equivalence as equivalence
from sunofriend._separation_authorised_excerpt import _document_sha256


def test_binds_prior_review_to_one_lsb_equivalent_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    result = _run(context)

    assert result["status"] == equivalence.STATUS
    assert result["prior_human_review"]["fresh_audition_of_candidate_exact_bytes"] is False
    assert result["prior_human_review"]["review_evidence_applies_under_equivalence_policy"] is True
    assert result["readiness"]["candidate_review_evidence_available"] is True
    assert result["readiness"]["private_output_import_permitted"] is False
    assert result["permissions"]["prior_review_evidence_may_be_considered"] is True
    assert result["permissions"]["source_graph_activation"] is False
    assert result["effects"]["model_run"] is False
    assert context["output"].stat().st_mode & 0o777 == 0o600


def test_rejects_more_than_one_lsb_without_writing_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    monkeypatch.setattr(
        equivalence,
        "_compare_pcm24_audio",
        lambda *_args: {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 100,
            "sample_subtype": "PCM_24",
            "total_sample_values": 200,
            "different_sample_values": 1,
            "different_sample_fraction": 0.005,
            "maximum_absolute_pcm24_lsb_difference": 2,
            "rms_pcm24_lsb_difference": 0.1,
        },
    )

    with pytest.raises(ValueError, match="exceeds policy"):
        _run(context)

    assert not context["output"].exists()


def test_pcm24_comparator_counts_one_lsb_difference(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    left = tmp_path / "left.wav"
    right = tmp_path / "right.wav"
    values = np.array([[0, 256], [512, -512]], dtype=np.int32)
    changed = values.copy()
    changed[1, 0] += 256
    soundfile.write(left, values, 44_100, subtype="PCM_24")
    soundfile.write(right, changed, 44_100, subtype="PCM_24")
    left.chmod(0o600)
    right.chmod(0o600)

    result = equivalence._compare_pcm24_audio(left, right)

    assert result["total_sample_values"] == 4
    assert result["different_sample_values"] == 1
    assert result["maximum_absolute_pcm24_lsb_difference"] == 1
    assert result["rms_pcm24_lsb_difference"] == 0.5


def _run(context: dict[str, Path]) -> dict[str, object]:
    return equivalence._bind_private_separation_render_review_equivalence(
        context["reviewed_export"],
        reviewed_package_dir=context["reviewed_package"],
        candidate_package_report_path=context["candidate_report"],
        out=context["output"],
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    os.chmod(tmp_path, 0o700)
    reviewed = _private_dir(tmp_path / "reviewed")
    candidate_root = _private_dir(tmp_path / "candidate")
    candidate_stitch_root = _private_dir(candidate_root / equivalence.STITCH_DIRECTORY)
    output_root = _private_dir(candidate_root / "REVIEW-EQUIVALENCE")
    paths = {
        "reviewed_export": _private_file(tmp_path / "reviewed.json"),
        "reviewed_package": reviewed,
        "reviewed_stitch": _private_file(reviewed / equivalence.STITCH_REPORT_NAME),
        "candidate_report": _private_file(candidate_root / equivalence.PACKAGE_REPORT_NAME),
        "candidate_stitch": _private_file(candidate_stitch_root / equivalence.STITCH_REPORT_NAME),
        "output": output_root / equivalence.REPORT_NAME,
    }
    clock = {"sample_rate": 44_100, "channels": 2, "frames": 100, "boundary_count": 1}
    artifacts = {
        "source": {"path": "SOURCE/source.wav", "sha256": "1" * 64, "bytes": 1000},
        "vocals": {"path": "STEMS/vocals.wav", "sha256": "2" * 64, "bytes": 1000},
        "instrumental": {"path": "STEMS/instrumental.wav", "sha256": "3" * 64, "bytes": 1000},
        "reconstruction": {"path": "STEMS/reconstruction.wav", "sha256": "4" * 64, "bytes": 1000},
    }
    reviewed_stitch = {
        "document_sha256": "5" * 64,
        "clock": clock,
        "artifacts": artifacts,
    }
    candidate_stitch = deepcopy(reviewed_stitch)
    candidate_stitch["document_sha256"] = "6" * 64
    for role, sha in zip(("vocals", "instrumental", "reconstruction"), ("7", "8", "9")):
        candidate_stitch["artifacts"][role]["sha256"] = sha * 64
    package_document = {
        "schema": equivalence.PACKAGE_SCHEMA,
        "status": equivalence.PACKAGE_STATUS,
        "bindings": {
            "stitch_report_sha256": "a" * 64,
            "stitch_document_sha256": "6" * 64,
            "review_seed_sha256": "b" * 64,
            "review_package_commitment": "c" * 64,
        },
        "readiness": {
            "playable_review_package_complete": True,
            "human_review_complete": False,
        },
        "permissions": equivalence._FALSE_PERMISSIONS,
    }
    package_document["document_sha256"] = _document_sha256(package_document)
    candidate_snapshot = {
        "path": paths["candidate_report"],
        "sha256": "d" * 64,
        "document": package_document,
    }
    prior_review = {
        "document_sha256": "e" * 64,
        "full_song": {"heard_all": True, "ratings": {role: "useful" for role in equivalence._ROLES}, "notes": ""},
        "boundary_summary": {"reviewed_boundaries": 1},
        "boundaries": [{"boundary_index": 1, "ratings": {role: "clean" for role in equivalence._ROLES}}],
    }
    monkeypatch.setattr(
        equivalence,
        "_load_private_json_snapshot",
        lambda *_args, **_kwargs: deepcopy(candidate_snapshot),
    )
    monkeypatch.setattr(
        equivalence,
        "_load_stitch_report",
        lambda path: deepcopy(candidate_stitch if Path(path) == paths["candidate_stitch"] else reviewed_stitch),
    )
    monkeypatch.setattr(equivalence, "_verify_stitch_audio", lambda *_args: None)
    monkeypatch.setattr(
        equivalence,
        "_load_verified_unreviewed_seed",
        lambda *_args: ({"package_commitment": "c" * 64}, "b" * 64),
    )
    monkeypatch.setattr(
        equivalence,
        "_resolve_private_separation_full_song_review",
        lambda *_args, **_kwargs: {**deepcopy(prior_review), "report": "temporary"},
    )
    monkeypatch.setattr(
        equivalence,
        "_compare_pcm24_audio",
        lambda *_args: {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 100,
            "sample_subtype": "PCM_24",
            "total_sample_values": 200,
            "different_sample_values": 2,
            "different_sample_fraction": 0.01,
            "maximum_absolute_pcm24_lsb_difference": 1,
            "rms_pcm24_lsb_difference": 0.1,
        },
    )
    monkeypatch.setattr(
        equivalence,
        "_sha256",
        lambda path: "a" * 64 if Path(path) == paths["candidate_stitch"] else "f" * 64,
    )
    return paths


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def _private_file(path: Path) -> Path:
    path.write_bytes(b"{}\n")
    path.chmod(0o600)
    return path
