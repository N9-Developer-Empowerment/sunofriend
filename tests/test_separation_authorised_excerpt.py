from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import (
    __all__,
    _document_sha256,
    _run_authorised_separation_excerpt,
)


def _write_wave(path: Path, value: np.ndarray, sample_rate: int = 8_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, value, sample_rate, subtype="PCM_24")


def _corpus(root: Path, *, mismatched_provider_rate: bool = False) -> Path:
    track = root / "corpus" / "example-song"
    sample_rate = 8_000
    times = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
    first = 0.2 * np.sin(2.0 * np.pi * 110.0 * times)
    second = 0.1 * np.sin(2.0 * np.pi * 220.0 * times)
    original = np.column_stack((first + second, first + second))
    _write_wave(track / "ORIGINAL" / "song.wav", original, sample_rate)
    for pack in ("PACK-A", "PACK-B"):
        rate = 8_100 if mismatched_provider_rate and pack == "PACK-B" else sample_rate
        if rate != sample_rate:
            other_times = np.arange(rate * 2, dtype=np.float64) / rate
            pack_first = 0.2 * np.sin(2.0 * np.pi * 110.0 * other_times)
            pack_second = 0.1 * np.sin(2.0 * np.pi * 220.0 * other_times)
        else:
            pack_first = first
            pack_second = second
        _write_wave(
            track / pack / "bass.wav",
            np.column_stack((pack_first, pack_first)),
            rate,
        )
        _write_wave(
            track / pack / "other.wav",
            np.column_stack((pack_second, pack_second)),
            rate,
        )
    document = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {"name": "Owner", "soundcloud_profile": "https://example.test"},
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "study",
            "condition": "credit Owner",
        },
        "tracks": [
            {
                "id": "example",
                "title": "Example",
                "directory": "example-song",
                "evaluation_state": "ready_for_excerpt_selection",
                "evaluation_excerpt": {
                    "start_seconds": 0.25,
                    "end_seconds": 1.25,
                    "selection_policy": "fixed active test interval",
                    "provider_packs": [
                        {"id": "pack-a", "directory": "PACK-A"},
                        {"id": "pack-b", "directory": "PACK-B"},
                    ],
                },
            }
        ],
    }
    path = root / "corpus" / "corpus.json"
    path.write_text(json.dumps(document) + "\n")
    return path


def _fake_separator(
    audio: Path,
    *,
    out_dir: Path,
    checkpoint_path: Path,
    start_seconds: float,
    end_seconds: float,
    python: str | Path | None,
) -> dict:
    assert Path(checkpoint_path).is_file()
    assert soundfile.info(audio).samplerate == 44_100
    assert start_seconds == 0.0
    assert end_seconds == 1.0
    assert python == "fake-python"
    root = Path(out_dir)
    root.mkdir(parents=True)
    report = root / "private-separation-experiment.json"
    report.write_text(
        json.dumps(
            {
                "schema": "test-private-separator.v1",
                "status": "complete_review_required",
                "document_sha256": "a" * 64,
            }
        )
        + "\n"
    )
    return {
        "status": "complete_review_required",
        "report": str(report),
        "estimated_stems": {},
    }


def test_authorised_excerpt_stages_aligned_packs_and_private_local_run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        result = _run_authorised_separation_excerpt(
            corpus,
            "example",
            out_dir=root / "evaluation",
            checkpoint_path=checkpoint,
            python="fake-python",
            separator_runner=_fake_separator,
        )

        assert result["status"] == "complete_review_required"
        assert result["corpus"]["track_id"] == "example"
        assert result["corpus"]["preferred_credit"] == (
            "Music by Owner — https://example.test"
        )
        assert result["excerpt"]["geometry"] == {
            "sample_rate": 8_000,
            "channels": 2,
            "frames": 8_000,
            "duration_seconds": 1.0,
        }
        assert result["effects"]["midi_created"] is False
        assert result["permissions"]["accepted"] is False
        model_input = result["original"]["local_model_input"]
        assert model_input["geometry"]["sample_rate"] == 44_100
        assert model_input["geometry"]["frames"] == 44_100
        assert "resample_poly" in model_input["derivation"]["algorithm"]
        for pack in ("pack-a", "pack-b"):
            evidence = result["provider_packs"][pack]
            assert evidence["source_count"] == 2
            assert evidence["summed_source_count"] == 2
            alignment = evidence["pack_sum_alignment"]
            assert alignment["sample_correlation_at_recorded_zero"] > 0.999999
            assert alignment["envelope_best_lag_ms"] == 0.0

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _document_sha256(persisted)
        assert persisted["local_separator"]["document_sha256"] == "a" * 64
        for relative, artifact in persisted["artifacts"].items():
            path = report.parent / relative
            assert path.is_file()
            assert path.stat().st_size == artifact["bytes"]
        for path in report.parent.rglob("*"):
            if path.is_file():
                assert (path.stat().st_mode & 0o777) == 0o600
            elif path.is_dir():
                assert (path.stat().st_mode & 0o777) == 0o700


def test_authorised_excerpt_rejects_geometry_mismatch_before_model_run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root, mismatched_provider_rate=True)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        called = False

        def separator(*_args: object, **_kwargs: object) -> dict:
            nonlocal called
            called = True
            return {}

        with pytest.raises(ValueError, match="geometry does not match"):
            _run_authorised_separation_excerpt(
                corpus,
                "example",
                out_dir=root / "evaluation",
                checkpoint_path=checkpoint,
                separator_runner=separator,
            )
        assert called is False
        assert not (root / "evaluation").exists()
        assert not list(root.glob(".evaluation.building-*"))


def test_authorised_excerpt_requires_fresh_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        destination = root / "evaluation"
        destination.mkdir()
        with pytest.raises(FileExistsError, match="already exists"):
            _run_authorised_separation_excerpt(
                corpus,
                "example",
                out_dir=destination,
                checkpoint_path=checkpoint,
                separator_runner=_fake_separator,
            )


def test_authorised_excerpt_has_no_product_import_and_exports_nothing() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/sunofriend/cli.py",
        "src/sunofriend/tui.py",
        "src/sunofriend/tui_conversion.py",
        "src/sunofriend/simple_create.py",
        "src/sunofriend/workbench_server.py",
        "src/sunofriend/__init__.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "_separation_authorised_excerpt" not in source
    assert __all__ == ()
