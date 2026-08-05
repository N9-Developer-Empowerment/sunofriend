from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_song_disjoint_private_pilot_handoff as handoff
from sunofriend._separation_authorised_excerpt import _document_sha256


def test_handoff_copies_exact_reviewed_two_stems_and_keeps_routes_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _fake_context(tmp_path, monkeypatch)
    output = context["output_parent"] / "handoff"

    result = handoff._prepare_private_song_disjoint_pilot_handoff(
        context["review_result"],
        reviewed_export_path=context["review_export"],
        pilot_evidence_path=context["pilot_evidence"],
        package_dir=context["package"],
        out_dir=output,
    )

    assert result["status"] == handoff.STATUS
    assert result["handoff"]["kind"] == "two_stem_vocals_and_instrumental"
    assert result["handoff"]["source_audio_included"] is False
    assert (output / "STEMS/vocals.wav").read_bytes() == b"vocals-pcm24"
    assert (output / "STEMS/instrumental.wav").read_bytes() == b"instrumental-pcm24"
    assert (output / "DIAGNOSTIC/reconstruction.wav").read_bytes() == b"reconstruction-pcm24"
    assert not (output / "SOURCE").exists()
    assert result["permissions"]["bounded_private_pilot_output_use"] is True
    assert result["permissions"]["publication_permitted"] is False
    assert result["effects"]["audio_bytes_copied"] is True
    assert result["effects"]["audio_sample_values_mutated"] is False
    assert result["effects"]["separator_accepted"] is False
    assert os.stat(output).st_mode & 0o777 == 0o700
    for path in (
        output / "STEMS/vocals.wav",
        output / "STEMS/instrumental.wav",
        output / "DIAGNOSTIC/reconstruction.wav",
        output / handoff.REPORT_NAME,
    ):
        assert os.stat(path).st_mode & 0o777 == 0o600
    persisted = (output / handoff.REPORT_NAME).read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    assert "private note" not in persisted
    document = json.loads(persisted)
    assert document["document_sha256"] == _document_sha256(document)


def test_handoff_rejects_unapproved_review_before_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _fake_context(tmp_path, monkeypatch, authorized=False)
    output = context["output_parent"] / "handoff"

    with pytest.raises(ValueError, match="not authorized"):
        handoff._prepare_private_song_disjoint_pilot_handoff(
            context["review_result"],
            reviewed_export_path=context["review_export"],
            pilot_evidence_path=context["pilot_evidence"],
            package_dir=context["package"],
            out_dir=output,
        )

    assert not output.exists()


def test_handoff_rejects_changed_resolved_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _fake_context(tmp_path, monkeypatch)
    document = json.loads(context["review_result"].read_text(encoding="utf-8"))
    document["marker"] = "changed"
    document["document_sha256"] = _document_sha256(document)
    _write_private_json(context["review_result"], document)

    with pytest.raises(ValueError, match="review result differs"):
        handoff._prepare_private_song_disjoint_pilot_handoff(
            context["review_result"],
            reviewed_export_path=context["review_export"],
            pilot_evidence_path=context["pilot_evidence"],
            package_dir=context["package"],
            out_dir=context["output_parent"] / "handoff",
        )


def _fake_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    authorized: bool = True,
) -> dict[str, Path]:
    os.chmod(tmp_path, 0o700)
    package = _private_dir(tmp_path / "package")
    stems = _private_dir(package / "STEMS")
    source = _private_dir(package / "SOURCE")
    _private_file(stems / "vocals.wav", b"vocals-pcm24")
    _private_file(stems / "instrumental.wav", b"instrumental-pcm24")
    _private_file(stems / "reconstruction.wav", b"reconstruction-pcm24")
    _private_file(source / "source-44100.wav", b"source-pcm24")
    stitch_path = _private_file(package / "private-separation-full-song-stitch.json", b"stitch\n")
    stitch = _stitch(package)
    pilot_evidence = _private_file(tmp_path / "pilot.json", b"pilot\n")
    review_export = _private_file(tmp_path / "reviewed.json", b"review\n")
    output_parent = _private_dir(tmp_path / "outputs")
    pilot_document = {
        "document_sha256": "a" * 64,
        "source_distinction": {
            "pilot_track_id": "track-one",
            "pilot_track_title": "Track One",
        },
        "automatic_execution": {"clock": deepcopy(stitch["clock"])},
    }
    pilot_snapshot = {
        "path": pilot_evidence,
        "sha256": "b" * 64,
        "document": pilot_document,
    }
    review_document = _review_document(
        pilot_snapshot=pilot_snapshot,
        stitch_path=stitch_path,
        stitch=stitch,
        authorized=authorized,
    )
    review_result = tmp_path / handoff.REVIEW_RESULT_NAME
    _write_private_json(review_result, review_document)

    monkeypatch.setattr(
        handoff,
        "_resolve_private_song_disjoint_pilot_review",
        lambda *args, **kwargs: {**deepcopy(review_document), "report": str(kwargs["out"])},
    )
    monkeypatch.setattr(
        handoff,
        "_load_verified_song_disjoint_private_pilot_evidence",
        lambda value: deepcopy(pilot_snapshot),
    )
    monkeypatch.setattr(handoff, "_load_stitch_report", lambda value: deepcopy(stitch))
    monkeypatch.setattr(handoff, "_verify_stitch_audio", lambda *args: None)
    return {
        "package": package,
        "pilot_evidence": pilot_evidence,
        "review_export": review_export,
        "review_result": review_result,
        "output_parent": output_parent,
    }


def _review_document(
    *,
    pilot_snapshot: dict[str, object],
    stitch_path: Path,
    stitch: dict[str, object],
    authorized: bool,
) -> dict[str, object]:
    status = (
        handoff.RESULT_STATUS_AUTHORIZED
        if authorized
        else "bounded_private_pilot_output_use_not_authorized"
    )
    document: dict[str, object] = {
        "schema": handoff.REVIEW_RESULT_SCHEMA,
        "status": status,
        "bindings": {
            "pilot_evidence_sha256": pilot_snapshot["sha256"],
            "pilot_evidence_document_sha256": pilot_snapshot["document"]["document_sha256"],
            "pilot_stitch_sha256": _sha256(stitch_path),
            "pilot_stitch_document_sha256": stitch["document_sha256"],
            "review_export_sha256": "c" * 64,
        },
        "review_summary": {
            "full_song_ratings": {
                "vocals": "useful" if authorized else "noticeable_problems",
                "instrumental": "useful",
                "reconstruction": "useful",
            },
            "reviewed_boundary_count": 2,
            "audible_join_boundaries_by_role": {
                "vocals": [1],
                "instrumental": [],
                "reconstruction": [],
            },
            "cannot_tell_boundaries_by_role": {
                "vocals": [],
                "instrumental": [2],
                "reconstruction": [],
            },
        },
        "readiness": {
            "bounded_private_pilot_output_use_permitted": authorized,
        },
        "permissions": {
            "bounded_private_pilot_output_use": authorized,
        },
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _stitch(package: Path) -> dict[str, object]:
    geometry = {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 10,
        "sample_width_bytes": 3,
    }
    artifacts = {
        "source": _artifact(package / "SOURCE/source-44100.wav", "SOURCE/source-44100.wav", geometry),
        "vocals": _artifact(package / "STEMS/vocals.wav", "STEMS/vocals.wav", geometry),
        "instrumental": _artifact(package / "STEMS/instrumental.wav", "STEMS/instrumental.wav", geometry),
        "reconstruction": _artifact(package / "STEMS/reconstruction.wav", "STEMS/reconstruction.wav", geometry),
    }
    return {
        "document_sha256": "d" * 64,
        "clock": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 10,
            "duration_seconds": 10 / 44_100,
            "chunk_count": 3,
            "boundary_count": 2,
            "gap_frames": 0,
            "overlap_frames": 0,
            "crossfade_frames": 0,
        },
        "artifacts": artifacts,
    }


def _artifact(path: Path, relative: str, geometry: dict[str, int]) -> dict[str, object]:
    return {
        "path": relative,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "geometry": deepcopy(geometry),
    }


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _private_file(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _write_private_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
