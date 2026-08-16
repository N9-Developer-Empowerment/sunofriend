from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.vocal_comp_stt import VOCAL_COMP_STT_RUN_SCHEMA, run_vocal_comp_stt


class VocalCompSttTests(unittest.TestCase):
    def test_runner_requires_existing_checkpoint_and_writes_path_free_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "voice.wav"
            soundfile.write(audio, np.zeros(8_000), 8_000, subtype="PCM_24")
            checkpoint = root / "small.en.pt"
            checkpoint.write_bytes(b"fixed-test-checkpoint")
            python = root / "python"
            python.write_bytes(b"fixed-test-runtime")
            os.chmod(python, 0o700)
            output = root / "stt-run"

            def worker(command, **_keyword):
                transcript = Path(command[command.index("--out") + 1])
                transcript.write_text(
                    json.dumps(
                        {
                            "schema": "sunofriend.vocal-comp-stt-candidate.v1",
                            "status": "complete_unreviewed",
                            "engine": "openai-whisper",
                            "engine_version": "test",
                            "model": "small.en",
                            "language": "en",
                            "text": "hello oh world",
                            "segments": [
                                {
                                    "start": 0.0,
                                    "end": 0.9,
                                    "text": "hello oh world",
                                    "words": [
                                        {"word": "hello", "start": 0.0, "end": 0.2, "probability": 0.9},
                                        {"word": "oh", "start": 0.2, "end": 0.4, "probability": 0.7},
                                        {"word": "world", "start": 0.4, "end": 0.8, "probability": 0.9},
                                    ],
                                }
                            ],
                            "canonical_lyrics_prompted": False,
                            "condition_on_previous_text": False,
                            "word_timestamps": True,
                            "network_used": False,
                        }
                    ),
                    encoding="utf-8",
                )
                return CompletedProcess(command, 0, "", "")

            with patch("sunofriend.vocal_comp_stt.subprocess.run", side_effect=worker) as run:
                result = run_vocal_comp_stt(
                    audio,
                    checkpoint=checkpoint,
                    python=python,
                    model_label="small.en",
                    source_id="take-001",
                    out_dir=output,
                )

            durable_text = (output / "run.json").read_text(encoding="utf-8")
            durable = json.loads(durable_text)
            environment = run.call_args.kwargs["env"]
            self.assertEqual(durable["schema"], VOCAL_COMP_STT_RUN_SCHEMA)
            self.assertEqual(durable["transcript"]["word_count"], 3)
            self.assertFalse(durable["canonical_lyrics_prompted"])
            self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
            self.assertEqual(environment["TRANSFORMERS_OFFLINE"], "1")
            self.assertNotIn(str(root), durable_text)
            self.assertFalse(result["automatic_selection"])

    def test_runner_never_accepts_a_model_name_as_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "voice.wav"
            soundfile.write(audio, np.zeros(8_000), 8_000)
            python = root / "python"
            python.write_bytes(b"runtime")
            os.chmod(python, 0o700)

            with self.assertRaisesRegex(ValueError, "checkpoint"):
                run_vocal_comp_stt(
                    audio,
                    checkpoint="small.en",
                    python=python,
                    model_label="small.en",
                    source_id="take-001",
                    out_dir=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
