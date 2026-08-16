from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.vocal_comp_review import (
    VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA,
    VOCAL_COMP_REVIEWED_INPUTS_SCHEMA,
    build_vocal_comp_draft_review,
    record_vocal_comp_draft_feedback,
    resolve_vocal_comp_draft_review,
)


def _write_audio(path: Path) -> None:
    sample_rate = 8_000
    time = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
    soundfile.write(
        path,
        0.1 * np.sin(2.0 * np.pi * 261.625565 * time),
        sample_rate,
        subtype="PCM_24",
    )


def _fixture(root: Path) -> dict[str, Path]:
    source = root / "source"
    source.mkdir()
    lyrics = source / "lyrics.txt"
    lyrics.write_text("The heart sees clearly\n", encoding="utf-8")
    target_vocal = source / "target-vocal.wav"
    _write_audio(target_vocal)
    target_midi = source / "target.mid"
    write_midi_file(
        target_midi,
        [
            MidiTrack(
                "Automatic target",
                0,
                53,
                [NoteEvent(0.2, 1.2, 60, 90)],
            )
        ],
        120.0,
    )
    timeline = source / "timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": "sunofriend.vocal-comp-timeline.v1",
                "status": "automatic_unreviewed",
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
    return {
        "lyrics": lyrics,
        "target_vocal": target_vocal,
        "target_midi": target_midi,
        "timeline": timeline,
    }


def _fake_render(_midi: Path, destination: Path) -> Path:
    _write_audio(destination)
    return destination


class VocalCompDraftReviewTests(unittest.TestCase):
    def test_review_package_is_private_path_free_and_zero_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            destination = root / "review"

            with patch(
                "sunofriend.vocal_comp_review.render_midi_to_wav",
                side_effect=_fake_render,
            ):
                result = build_vocal_comp_draft_review(
                    lyrics=paths["lyrics"],
                    target_midi=paths["target_midi"],
                    phrase_timeline=paths["timeline"],
                    target_vocal=paths["target_vocal"],
                    out_dir=destination,
                    bpm=120.0,
                    tuning_hz=440.0,
                )

            seed_text = (destination / "vocal-comp-draft-review.json").read_text(
                encoding="utf-8"
            )
            seed = json.loads(seed_text)
            self.assertEqual(seed["status"], "automatic_unreviewed")
            self.assertFalse(seed["effects"]["human_decision_created"])
            self.assertNotIn(str(root), seed_text)
            self.assertTrue(Path(result["review_html"]).is_file())

    def test_resolver_rejects_unresolved_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            package = root / "review"
            with patch(
                "sunofriend.vocal_comp_review.render_midi_to_wav",
                side_effect=_fake_render,
            ):
                built = build_vocal_comp_draft_review(
                    lyrics=paths["lyrics"],
                    target_midi=paths["target_midi"],
                    phrase_timeline=paths["timeline"],
                    target_vocal=paths["target_vocal"],
                    out_dir=package,
                    bpm=120.0,
                    tuning_hz=440.0,
                )
            review = root / "unresolved.json"
            review.write_text(
                json.dumps(
                    {
                        "schema": VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA,
                        "draft_sha256": built["draft_sha256"],
                        "status": "unresolved",
                        "reviewed_at": None,
                        "phrases": [
                            {
                                "phrase_id": "verse-01",
                                "lyrics_and_timing": "needs_change",
                                "target_melody": "needs_change",
                                "notes": "The timing is wrong.",
                            }
                        ],
                        "effects": {
                            "automatic_selection": False,
                            "audio_comp_rendered": False,
                            "pitch_correction_applied": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "incomplete"):
                resolve_vocal_comp_draft_review(
                    package,
                    review,
                    out_dir=root / "resolved",
                )

            output = root / "feedback.json"
            recorded = record_vocal_comp_draft_feedback(
                package,
                review,
                out=output,
            )
            self.assertEqual(recorded["status"], "recorded_unresolved")
            self.assertFalse(recorded["reviewed_inputs_created"])
            self.assertFalse(recorded["automatic_selection"])
            self.assertTrue(output.is_file())

    def test_complete_explicit_review_creates_fresh_reviewed_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            package = root / "review"
            with patch(
                "sunofriend.vocal_comp_review.render_midi_to_wav",
                side_effect=_fake_render,
            ):
                built = build_vocal_comp_draft_review(
                    lyrics=paths["lyrics"],
                    target_midi=paths["target_midi"],
                    phrase_timeline=paths["timeline"],
                    target_vocal=paths["target_vocal"],
                    out_dir=package,
                    bpm=120.0,
                    tuning_hz=440.0,
                )
            review = root / "reviewed.json"
            review.write_text(
                json.dumps(
                    {
                        "schema": VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA,
                        "draft_sha256": built["draft_sha256"],
                        "status": "reviewed",
                        "reviewed_at": "2026-08-12T22:30:00Z",
                        "effects": {
                            "automatic_selection": False,
                            "audio_comp_rendered": False,
                            "pitch_correction_applied": False,
                        },
                        "phrases": [
                            {
                                "phrase_id": "verse-01",
                                "lyrics_and_timing": "approved",
                                "target_melody": "approved",
                                "notes": "",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            destination = root / "resolved"

            result = resolve_vocal_comp_draft_review(
                package,
                review,
                out_dir=destination,
            )

            timeline = json.loads(
                (destination / "reviewed-phrase-timeline.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(result["schema"], VOCAL_COMP_REVIEWED_INPUTS_SCHEMA)
            self.assertEqual(timeline["status"], "reviewed")
            self.assertTrue(result["human_decision_created"])
            self.assertFalse(result["selection_created"])
            self.assertFalse(result["audio_comp_rendered"])
            self.assertEqual(
                (destination / "reviewed-target.mid").read_bytes(),
                paths["target_midi"].read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
