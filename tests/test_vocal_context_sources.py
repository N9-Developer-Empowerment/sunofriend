from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend.vocal_context_sources import admit_vocal_context_sources


def _wav(path: Path, frequency: float = 220.0) -> Path:
    sample_rate = 8_000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    soundfile.write(
        path,
        (0.05 * np.sin(2.0 * np.pi * frequency * time)).astype(np.float32),
        sample_rate,
        subtype="PCM_24",
    )
    return path


def test_context_admission_is_explicit_distinct_and_path_free(tmp_path: Path) -> None:
    context = admit_vocal_context_sources(
        original_mix_audio=_wav(tmp_path / "mix.wav"),
        backing_audio=_wav(tmp_path / "backing.wav", 164.81),
    )

    media = context.media_records()
    capabilities = {source_id: f"cap-{index}" for index, source_id in enumerate(media)}
    browser = context.browser_sources(capabilities)

    assert [row["source_class"] for row in browser] == [
        "authorised_original_mix",
        "authorised_instrumental_backing",
    ]
    assert all(row["authority"] == "audition_only" for row in browser)
    assert all(row["media_url"].startswith("/media/") for row in browser)
    assert str(tmp_path) not in json.dumps(browser)
    assert {row["audio_sha256"] for row in browser} == {
        row["audio_sha256"] for row in media.values()
    }


def test_context_admission_rejects_same_audio_for_both_roles(tmp_path: Path) -> None:
    shared = _wav(tmp_path / "shared.wav")

    with pytest.raises(ValueError, match="must be distinct"):
        admit_vocal_context_sources(
            original_mix_audio=shared,
            backing_audio=shared,
        )


def test_context_admission_rejects_symlink(tmp_path: Path) -> None:
    target = _wav(tmp_path / "target.wav")
    linked = tmp_path / "linked.wav"
    linked.symlink_to(target)

    with pytest.raises(ValueError, match="ordinary file"):
        admit_vocal_context_sources(
            original_mix_audio=linked,
            backing_audio=None,
        )
