from __future__ import annotations

import json
import math
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from sunofriend.cli import main
from sunofriend.musical_metadata import (
    MUSICAL_METADATA_SCHEMA,
    analyze_musical_metadata,
    load_musical_metadata_analysis,
    resolve_metadata_precedence,
    validate_musical_metadata_analysis,
)


class MusicalMetadataTests(unittest.TestCase):
    def test_analysis_is_path_free_local_self_hashed_and_reviewable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private song name.wav"
            _write_click_chord(source)

            first = analyze_musical_metadata(source)
            second = analyze_musical_metadata(source)

            self.assertEqual(first, second)
            self.assertEqual(first["schema"], MUSICAL_METADATA_SCHEMA)
            self.assertFalse(first["network_used"])
            self.assertEqual(first["review"]["status"], "not_reviewed")
            self.assertNotIn(str(source), json.dumps(first))
            self.assertNotIn(source.name, json.dumps(first))
            self.assertGreater(first["estimates"]["tempo"]["selected_bpm"], 0)
            self.assertTrue(first["estimates"]["key"]["selected_key"])
            self.assertIsNotNone(first["estimates"]["tempo"]["half_time_bpm"])
            validate_musical_metadata_analysis(first)

    def test_precedence_never_replaces_explicit_or_filename_metadata(self) -> None:
        analysis = _analysis_fixture(
            key="Ab major", bpm=144, key_confidence="high", bpm_confidence="high"
        )

        effective, resolution = resolve_metadata_precedence(
            analysis,
            explicit_key="D minor",
            explicit_bpm=None,
            explicit_tuning_hz=None,
            inferred_key="C major",
            inferred_bpm=90.0,
            inferred_tuning_hz=440.0,
        )

        self.assertEqual(
            effective,
            {"key": "D minor", "bpm": 90.0, "tuning_hz": 440.0},
        )
        self.assertEqual(resolution["provenance"]["key"], "explicit_cli")
        self.assertEqual(
            resolution["provenance"]["bpm"], "filename_or_folder"
        )
        self.assertFalse(resolution["automatic_overrode_existing_metadata"])

    def test_only_high_confidence_key_and_bpm_fill_missing_values(self) -> None:
        high = _analysis_fixture(
            key="Ab major", bpm=144, key_confidence="high", bpm_confidence="high"
        )
        low = _analysis_fixture(
            key="Ab major", bpm=144, key_confidence="medium", bpm_confidence="low"
        )

        high_effective, high_resolution = resolve_metadata_precedence(
            high,
            explicit_key=None,
            explicit_bpm=None,
            explicit_tuning_hz=None,
            inferred_key=None,
            inferred_bpm=None,
            inferred_tuning_hz=None,
        )
        low_effective, _ = resolve_metadata_precedence(
            low,
            explicit_key=None,
            explicit_bpm=None,
            explicit_tuning_hz=None,
            inferred_key=None,
            inferred_bpm=None,
            inferred_tuning_hz=None,
        )

        self.assertEqual(high_effective["key"], "Ab major")
        self.assertEqual(high_effective["bpm"], 144)
        self.assertIsNone(high_effective["tuning_hz"])
        self.assertEqual(
            high_resolution["provenance"]["key"],
            "high_confidence_automatic",
        )
        self.assertIsNone(low_effective["key"])
        self.assertIsNone(low_effective["bpm"])

    def test_cli_can_write_fresh_evidence_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            output = root / "evidence.json"
            _write_click_chord(source)
            before = source.read_bytes()

            status = main(
                ["musical-metadata", str(source), "--out", str(output)]
            )

            self.assertEqual(status, 0)
            self.assertEqual(source.read_bytes(), before)
            document = load_musical_metadata_analysis(output)
            self.assertEqual(document["schema"], MUSICAL_METADATA_SCHEMA)


def _analysis_fixture(
    *, key: str, bpm: float, key_confidence: str, bpm_confidence: str
) -> dict:
    return {
        "schema": MUSICAL_METADATA_SCHEMA,
        "status": "complete_unreviewed",
        "network_used": False,
        "source": {"sha256": "a" * 64, "bytes": 1, "duration_seconds": 1.0},
        "algorithm": {"id": "fixture"},
        "estimates": {
            "key": {"selected_key": key, "confidence": key_confidence},
            "tempo": {"selected_bpm": bpm, "confidence": bpm_confidence},
            "tuning": {"concert_a_hz": 440.0, "confidence": "review_recommended"},
        },
        "suggested_metadata": {"key": key, "bpm": bpm, "tuning_hz": 440.0},
        "review": {"status": "not_reviewed", "review_recommended": True},
        "effects": {"source_audio_mutated": False},
    }


def _write_click_chord(path: Path, *, sample_rate: int = 22_050) -> None:
    duration = 12.0
    frames = int(duration * sample_rate)
    time = np.arange(frames, dtype=np.float64) / sample_rate
    chord = sum(
        np.sin(2.0 * math.pi * frequency * time)
        for frequency in (261.6256, 329.6276, 391.9954)
    ) / 9.0
    click = np.zeros(frames, dtype=np.float64)
    for start in range(0, frames, sample_rate // 2):
        count = min(256, frames - start)
        click[start : start + count] += 0.7 * np.hanning(count)
    audio = np.clip(chord + click, -1.0, 1.0)
    pcm = (audio * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


if __name__ == "__main__":
    unittest.main()
