from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.vocal import PitchFrame, VocalCandidate, fractional_midi_to_hz
from sunofriend.vocal_comp import (
    VOCAL_COMP_CANDIDATES_SCHEMA,
    VOCAL_COMP_PROJECT_SCHEMA,
    _measure_phrase,
    analyze_vocal_comp_project,
    create_vocal_comp_project,
    plan_vocal_comp_project,
)


def _write_wav(path: Path, *, amplitude: float = 0.1) -> None:
    sample_rate = 8_000
    times = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
    values = amplitude * np.sin(2.0 * np.pi * 261.625565 * times)
    soundfile.write(path, values, sample_rate, subtype="PCM_24")


def _fixture(root: Path, *, with_reference: bool = False) -> dict[str, Path]:
    takes = root / "takes"
    takes.mkdir()
    _write_wav(takes / "first.wav")
    _write_wav(takes / "second.wav")
    lyrics = root / "lyrics.txt"
    lyrics.write_text("The heart sees clearly\n", encoding="utf-8")
    target = root / "target.mid"
    write_midi_file(
        target,
        [
            MidiTrack(
                name="Reviewed vocal target",
                channel=0,
                program=53,
                notes=[NoteEvent(0.2, 1.2, 60, 90)],
            )
        ],
        bpm=120.0,
    )
    timeline = root / "timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": "sunofriend.vocal-comp-timeline.v1",
                "status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": "verse-01",
                        "start_seconds": 0.1,
                        "end_seconds": 1.4,
                        "lyrics": "The heart sees clearly",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = {
        "takes": takes,
        "lyrics": lyrics,
        "target": target,
        "timeline": timeline,
    }
    if with_reference:
        reference = root / "ai-reference.wav"
        _write_wav(reference)
        result["reference"] = reference
    return result


def _project_keyword(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "lyrics": paths["lyrics"],
        "target_midi": paths["target"],
        "phrase_timeline": paths["timeline"],
        "target_vocal": paths.get("reference"),
        "bpm": 120.0,
        "tuning_hz": 440.0,
        "rights_category": "owned",
        "processing_chain": "dry",
        "confirm_common_recorded_zero": True,
        "confirm_target_reviewed": True,
    }


def _good_frames() -> list[PitchFrame]:
    return [
        PitchFrame(
            time=index / 100.0,
            f0_hz=fractional_midi_to_hz(60.0),
            voiced_probability=0.95,
            rms=0.1,
            source="pyin",
        )
        for index in range(20, 121)
    ]


def _unvoiced_frames() -> list[PitchFrame]:
    return [
        PitchFrame(
            time=index / 100.0,
            f0_hz=None,
            voiced_probability=0.0,
            rms=0.0,
            source="pyin",
        )
        for index in range(20, 121)
    ]


class VocalCompTests(unittest.TestCase):
    def test_plan_requires_explicit_recorded_zero_and_review_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture(Path(tmp))
            keyword = _project_keyword(paths)
            keyword["confirm_common_recorded_zero"] = False

            with self.assertRaisesRegex(ValueError, "common_recorded_zero"):
                plan_vocal_comp_project(paths["takes"], **keyword)

    def test_create_preserves_exact_sources_in_private_path_free_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root, with_reference=True)
            source_bytes = {
                path.name: path.read_bytes() for path in paths["takes"].glob("*.wav")
            }
            destination = root / "project"

            result = create_vocal_comp_project(
                paths["takes"],
                out_dir=destination,
                **_project_keyword(paths),
            )

            manifest_path = destination / "vocal-comp-project.json"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["schema"], VOCAL_COMP_PROJECT_SCHEMA)
            self.assertNotIn(str(root), manifest_text)
            self.assertFalse(manifest["effects"]["selection_created"])
            self.assertFalse(manifest["effects"]["audio_comp_rendered"])
            self.assertFalse(manifest["effects"]["pitch_correction_applied"])
            self.assertEqual(os.stat(destination).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(manifest_path).st_mode & 0o777, 0o600)
            self.assertEqual(result["status"], "complete")
            for path in paths["takes"].glob("*.wav"):
                self.assertEqual(path.read_bytes(), source_bytes[path.name])

    def test_phrase_measurement_separates_attempt_state_from_quality(self) -> None:
        phrase = {
            "phrase_id": "p1",
            "start_seconds": 0.1,
            "end_seconds": 1.4,
            "lyrics": "The heart sees clearly",
        }
        frames = _good_frames()
        audit = [
            {"time_seconds": frame.time, "classification": "agreement"}
            for frame in frames
        ]
        signal = {
            "rms_linear": 0.1,
            "full_scale_sample_count": 0,
        }

        good = _measure_phrase(
            phrase,
            target_notes=[NoteEvent(0.2, 1.2, 60, 90)],
            frames=frames,
            audit=audit,
            signal=signal,
            tuning_hz=440.0,
        )
        absent = _measure_phrase(
            phrase,
            target_notes=[NoteEvent(0.2, 1.2, 60, 90)],
            frames=_unvoiced_frames(),
            audit=[],
            signal=signal,
            tuning_hz=440.0,
        )

        self.assertEqual(good["state"], "eligible")
        self.assertTrue(good["acceptable"])
        self.assertEqual(absent["state"], "not_attempted")
        self.assertFalse(absent["acceptable"])

    def test_analysis_publishes_ranked_evidence_without_a_comp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            project = root / "project"
            output = root / "analysis"
            create_vocal_comp_project(
                paths["takes"],
                out_dir=project,
                **_project_keyword(paths),
            )
            candidates = [
                VocalCandidate(NoteEvent(0.2, 1.2, 60, 90), confidence=0.95)
            ]

            with patch(
                "sunofriend.vocal_comp.extract_pitch_frames",
                return_value=_good_frames(),
            ), patch(
                "sunofriend.vocal_comp.extract_backing_candidates",
                return_value=candidates,
            ):
                result = analyze_vocal_comp_project(project, out_dir=output)

            document_text = (output / "phrase-candidates.json").read_text(
                encoding="utf-8"
            )
            document = json.loads(document_text)
            take_analysis = json.loads(
                (output / "EVIDENCE" / "take-001.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(document["schema"], VOCAL_COMP_CANDIDATES_SCHEMA)
            self.assertEqual(document["phrases"][0]["status"], "ranked_human_candidates")
            self.assertEqual(document["phrases"][0]["top_three_candidate_ids"], ["take-001", "take-002"])
            self.assertIn("independent_evidence", take_analysis)
            self.assertFalse(result["automatic_selection"])
            self.assertFalse(result["audio_rendered"])
            self.assertFalse(result["correction_applied"])
            self.assertNotIn(str(root), document_text)
            self.assertTrue((output / "vocal-comp-report.html").is_file())
            self.assertFalse(any(path.name.endswith("comp.wav") for path in output.rglob("*")))

    def test_no_acceptable_human_creates_pickup_and_ai_fallback_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root, with_reference=True)
            project = root / "project"
            output = root / "analysis"
            create_vocal_comp_project(
                paths["takes"],
                out_dir=project,
                **_project_keyword(paths),
            )

            with patch(
                "sunofriend.vocal_comp.extract_pitch_frames",
                return_value=_unvoiced_frames(),
            ), patch(
                "sunofriend.vocal_comp.extract_backing_candidates",
                return_value=[],
            ):
                analyze_vocal_comp_project(project, out_dir=output)

            candidates = json.loads(
                (output / "phrase-candidates.json").read_text(encoding="utf-8")
            )
            pickups = json.loads(
                (output / "pickup-plan.json").read_text(encoding="utf-8")
            )
            phrase = candidates["phrases"][0]
            self.assertEqual(phrase["status"], "no_acceptable_candidate")
            self.assertEqual(phrase["ai_fallback"]["policy"], "fallback_only_after_no_acceptable_human_candidate")
            self.assertEqual(pickups["pickup_count"], 1)
            self.assertFalse(candidates["automatic_selection"])


if __name__ == "__main__":
    unittest.main()
