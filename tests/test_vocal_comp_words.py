from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.vocal_comp_words import (
    VOCAL_COMP_WORD_ALIGNMENT_POLICY,
    VOCAL_COMP_WORD_ALIGNMENT_SCHEMA,
    _canonical_words,
    align_vocal_comp_transcripts,
    align_word_sequences,
)


def _observed(*words: str) -> list[dict[str, object]]:
    return [
        {
            "observed_index": index,
            "text": word,
            "normalized": word.casefold(),
            "start_seconds": float(index - 1),
            "end_seconds": float(index) - 0.1,
            "probability": 0.9,
        }
        for index, word in enumerate(words, 1)
    ]


class VocalCompWordAlignmentTests(unittest.TestCase):
    def test_alignment_retains_adlib_omission_and_substitution(self) -> None:
        canonical = _canonical_words("The heart sees what it wants")

        operations = align_word_sequences(
            canonical,
            _observed("the", "heart", "oh", "sees", "whatever", "wants"),
        )

        kinds = [row["operation"] for row in operations]
        self.assertIn("insertion_adlib_candidate", kinds)
        self.assertIn("omission_candidate", kinds)
        self.assertIn("substitution_candidate", kinds)
        self.assertEqual(
            [row["operation_index"] for row in operations],
            list(range(1, len(operations) + 1)),
        )

    def test_canonical_sections_are_skipped_but_line_identity_is_retained(self) -> None:
        words = _canonical_words("[Verse 1]\nThe heart sees\n\nWhat it wants\n")

        self.assertEqual([row["text"] for row in words], ["The", "heart", "sees", "What", "it", "wants"])
        self.assertEqual([row["line_index"] for row in words], [1, 1, 1, 2, 2, 2])
        self.assertEqual(words[0]["physical_line_index"], 2)

    def test_unanchored_adlib_is_not_paired_to_an_omitted_lyric_line(self) -> None:
        canonical = _canonical_words(
            "If we were the last two people on Earth\nYou would talk to me\n"
        )

        operations = align_word_sequences(
            canonical,
            _observed(
                "tell",
                "me",
                "are",
                "you",
                "mine",
                "you",
                "would",
                "talk",
                "to",
                "me",
            ),
        )

        first_line = [
            row
            for row in operations
            if row["canonical"] is not None
            and row["canonical"]["line_index"] == 1
        ]
        self.assertEqual(
            {row["operation"] for row in first_line}, {"omission_candidate"}
        )
        self.assertEqual(
            [
                row["observed"]["normalized"]
                for row in operations
                if row["operation"] == "insertion_adlib_candidate"
            ],
            ["tell", "me", "are", "you", "mine"],
        )

    def test_project_binds_transcript_to_audio_and_claims_no_syllable_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lyrics = root / "lyrics.txt"
            lyrics.write_text("The heart sees\n", encoding="utf-8")
            audio = root / "voice.wav"
            soundfile.write(
                audio,
                np.zeros(16_000, dtype=np.float32),
                8_000,
                subtype="PCM_24",
            )
            transcript = root / "transcript.json"
            transcript.write_text(
                json.dumps(
                    {
                        "engine": "whisper",
                        "model": "small.en",
                        "language": "en",
                        "segments": [
                            {
                                "words": [
                                    {"word": "The", "start": 0.1, "end": 0.3, "probability": 0.9},
                                    {"word": "heart", "start": 0.3, "end": 0.7, "probability": 0.8},
                                    {"word": "oh", "start": 0.7, "end": 0.9, "probability": 0.7},
                                    {"word": "sees", "start": 0.9, "end": 1.2, "probability": 0.9},
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "alignment"

            result = align_vocal_comp_transcripts(
                lyrics,
                transcripts={"ai-reference": transcript},
                audio={"ai-reference": audio},
                out_dir=output,
            )

            durable_text = (output / "vocal-comp-word-alignment.json").read_text(
                encoding="utf-8"
            )
            durable = json.loads(durable_text)
            source = durable["sources"]["ai-reference"]
            self.assertEqual(durable["schema"], VOCAL_COMP_WORD_ALIGNMENT_SCHEMA)
            self.assertEqual(
                durable["alignment_policy"], VOCAL_COMP_WORD_ALIGNMENT_POLICY
            )
            self.assertEqual(source["adlib_candidate_count"], 1)
            self.assertEqual(source["syllable_alignment"]["status"], "unavailable")
            self.assertFalse(durable["interpretation"]["syllable_timing_claimed"])
            self.assertNotIn(str(root), durable_text)
            self.assertFalse(result["automatic_selection"])
            self.assertFalse(result["audio_comp_rendered"])


if __name__ == "__main__":
    unittest.main()
