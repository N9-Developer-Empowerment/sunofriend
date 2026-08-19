from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

import mido
import numpy as np

from sunofriend.source_identity import SCHEMA, build_source_identity_scaffold


class SourceIdentityScaffoldTests(unittest.TestCase):
    def test_builds_review_gated_melody_and_pulse_primary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private-title.wav"
            provenance = root / "melody.provenance.json"
            output = root / "scaffold"
            _write_chord_click(source)
            provenance.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "variant": "contour_clean",
                        "notes": [
                            {
                                "start": 0.5,
                                "end": 1.5,
                                "pitch": 69,
                                "velocity": 80,
                            },
                            {
                                "start": 2.0,
                                "end": 3.0,
                                "pitch": 73,
                                "velocity": 76,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = build_source_identity_scaffold(
                source,
                provenance,
                output,
                bpm=120,
            )

            persisted = json.loads(
                (output / "source-identity-report.json").read_text(encoding="utf-8")
            )
            primary = mido.MidiFile(output / "source-identity-scaffold.mid")
            diagnostic = mido.MidiFile(
                output / "source-identity-scaffold-with-harmony.mid"
            )

            self.assertEqual(result["schema"], SCHEMA)
            self.assertEqual(persisted["status"], "complete_unreviewed")
            self.assertEqual(persisted["review"]["status"], "required")
            self.assertFalse(persisted["review"]["source_identity_recognised"])
            self.assertFalse(
                persisted["evidence"]["automatic_harmony_in_primary_scaffold"]
            )
            self.assertEqual(len(primary.tracks), 3)
            self.assertEqual(len(diagnostic.tracks), 5)
            self.assertNotIn(source.name, json.dumps(persisted))
            self.assertFalse(persisted["effects"]["network_used"])

    def test_requires_a_fresh_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            provenance = root / "melody.json"
            output = root / "existing"
            _write_chord_click(source)
            provenance.write_text(
                json.dumps(
                    {
                        "notes": [
                            {
                                "start": 0.0,
                                "end": 1.0,
                                "pitch": 60,
                                "velocity": 80,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output.mkdir()

            with self.assertRaisesRegex(ValueError, "must be fresh"):
                build_source_identity_scaffold(
                    source,
                    provenance,
                    output,
                    bpm=120,
                )


def _write_chord_click(path: Path, *, seconds: float = 8.0) -> None:
    sample_rate = 22_050
    frames = int(sample_rate * seconds)
    time = np.arange(frames, dtype=np.float64) / sample_rate
    audio = sum(
        0.08 * np.sin(2.0 * np.pi * frequency * time)
        for frequency in (220.0, 277.182631, 329.627557)
    )
    for start in np.arange(0.0, seconds, 0.5):
        index = int(start * sample_rate)
        count = min(220, frames - index)
        audio[index : index + count] += np.linspace(0.8, 0.0, count)
    pcm = np.clip(np.rint(audio * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm.tobytes())


if __name__ == "__main__":
    unittest.main()
