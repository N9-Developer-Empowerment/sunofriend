from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.vocal_comp import _document_sha256, _sha256
from sunofriend.vocal_comp_word_review import (
    VOCAL_COMP_WORD_REVIEW_PACKAGE_SCHEMA,
    VOCAL_COMP_WORD_REVIEW_RESULT_SCHEMA,
    VOCAL_COMP_WORD_REVIEW_SCHEMA,
    build_vocal_comp_word_review,
)
from sunofriend.vocal_comp_words import (
    VOCAL_COMP_WORD_ALIGNMENT_POLICY,
    VOCAL_COMP_WORD_ALIGNMENT_SCHEMA,
    _canonical_words,
    align_word_sequences,
)


def _observed(*words: tuple[str, float, float]) -> list[dict[str, object]]:
    return [
        {
            "observed_index": index,
            "text": word,
            "normalized": word.casefold(),
            "start_seconds": start,
            "end_seconds": end,
            "probability": 0.9,
        }
        for index, (word, start, end) in enumerate(words, 1)
    ]


class VocalCompWordReviewTests(unittest.TestCase):
    def test_builds_bound_detailed_zero_effect_review_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lyrics = root / "lyrics.txt"
            lyrics.write_text("The heart\nSees clearly\n", encoding="utf-8")
            ai = root / "ai.wav"
            take = root / "take.wav"
            for path in (ai, take):
                soundfile.write(path, np.zeros(32_000), 8_000, subtype="PCM_24")
            canonical = _canonical_words(lyrics.read_text(encoding="utf-8"))
            ai_words = _observed(
                ("oh", 0.2, 0.4),
                ("the", 0.9, 1.1),
                ("heart", 1.1, 1.5),
                ("sees", 2.0, 2.3),
                ("clearly", 2.3, 2.8),
            )
            take_words = _observed(
                ("the", 0.9, 1.1),
                ("heart", 1.1, 1.5),
                ("sees", 2.0, 2.3),
                ("nearly", 2.3, 2.8),
            )
            alignment = {
                "schema": VOCAL_COMP_WORD_ALIGNMENT_SCHEMA,
                "alignment_policy": VOCAL_COMP_WORD_ALIGNMENT_POLICY,
                "status": "complete_unreviewed",
                "canonical_lyrics": {
                    "bytes": lyrics.stat().st_size,
                    "sha256": _sha256(lyrics),
                },
                "canonical_word_count": len(canonical),
                "canonical_words": canonical,
                "source_count": 2,
                "sources": {
                    "ai-reference": _source(ai, canonical, ai_words),
                    "take-001": _source(take, canonical, take_words),
                },
                "interpretation": {
                    "known_lyrics_are_canonical": True,
                    "syllable_timing_claimed": False,
                },
                "automatic_selection": False,
                "audio_comp_rendered": False,
                "pitch_correction_applied": False,
                "network_used": False,
            }
            alignment["alignment_sha256"] = _document_sha256(alignment)
            alignment_path = root / "alignment.json"
            alignment_path.write_text(
                json.dumps(alignment, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            output = root / "review"

            result = build_vocal_comp_word_review(
                alignment_path,
                lyrics=lyrics,
                audio={"ai-reference": ai, "take-001": take},
                out_dir=output,
            )

            package = json.loads(
                (output / "vocal-comp-word-review-package.json").read_text()
            )
            seed_text = (output / "vocal-comp-word-review.json").read_text()
            seed = json.loads(seed_text)
            page = (output / "vocal-comp-word-review.html").read_text()
            self.assertEqual(package["schema"], VOCAL_COMP_WORD_REVIEW_PACKAGE_SCHEMA)
            self.assertEqual(seed["schema"], VOCAL_COMP_WORD_REVIEW_SCHEMA)
            self.assertEqual(seed["result_schema"], VOCAL_COMP_WORD_REVIEW_RESULT_SCHEMA)
            self.assertEqual(seed["adlib"]["candidate_text"], "oh")
            self.assertEqual(len(seed["lines"]), 2)
            self.assertEqual(len(seed["sources"]), 2)
            self.assertIn("Full-source context", page)
            self.assertIn("Source-by-source ad-lib evidence", page)
            self.assertIn("What was sung vs ad-lib candidate?", page)
            self.assertIn("What was sung vs canonical?", page)
            self.assertIn("Complete review and export JSON", page)
            self.assertIn("cannot_tell", page)
            self.assertIn("automatic_selection:false", page)
            self.assertFalse(result["effects"]["selection_created"])
            self.assertFalse(result["effects"]["audio_comp_rendered"])
            self.assertNotIn(str(root), seed_text)
            self.assertEqual(
                stat.S_IMODE((output / "vocal-comp-word-review.html").stat().st_mode),
                0o600,
            )
            for source_id in ("ai-reference", "take-001"):
                self.assertTrue((output / "AUDIO" / source_id / "full.wav").is_file())
                self.assertTrue(
                    (output / "AUDIO" / source_id / "adlib-context.wav").is_file()
                )
                self.assertTrue(
                    (output / "AUDIO" / source_id / "line-01.wav").is_file()
                )

    def test_rejects_audio_that_does_not_match_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lyrics = root / "lyrics.txt"
            lyrics.write_text("The heart\n", encoding="utf-8")
            audio = root / "audio.wav"
            wrong = root / "wrong.wav"
            soundfile.write(audio, np.zeros(16_000), 8_000)
            soundfile.write(wrong, np.ones(16_000) * 0.1, 8_000)
            canonical = _canonical_words("The heart\n")
            words = _observed(
                ("oh", 0.1, 0.2), ("the", 0.5, 0.7), ("heart", 0.7, 1.0)
            )
            document = {
                "schema": VOCAL_COMP_WORD_ALIGNMENT_SCHEMA,
                "status": "complete_unreviewed",
                "canonical_lyrics": {
                    "bytes": lyrics.stat().st_size,
                    "sha256": _sha256(lyrics),
                },
                "canonical_words": canonical,
                "sources": {"ai-reference": _source(audio, canonical, words)},
                "automatic_selection": False,
                "audio_comp_rendered": False,
                "pitch_correction_applied": False,
            }
            document["alignment_sha256"] = _document_sha256(document)
            path = root / "alignment.json"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match"):
                build_vocal_comp_word_review(
                    path,
                    lyrics=lyrics,
                    audio={"ai-reference": wrong},
                    out_dir=root / "review",
                )


def _source(
    audio: Path,
    canonical: list[dict[str, object]],
    observed: list[dict[str, object]],
) -> dict[str, object]:
    operations = align_word_sequences(canonical, observed)
    matches = sum(row["operation"] == "match" for row in operations)
    substitutions = sum(
        row["operation"] == "substitution_candidate" for row in operations
    )
    return {
        "audio": {"bytes": audio.stat().st_size, "sha256": _sha256(audio)},
        "observed_word_count": len(observed),
        "exact_canonical_coverage": matches / len(canonical),
        "candidate_canonical_coverage": (matches + substitutions) / len(canonical),
        "operations": operations,
    }


if __name__ == "__main__":
    unittest.main()
