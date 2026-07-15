from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend.ai_runtime import (
    AI_CANDIDATE_SCHEMA,
    AI_MODEL_MANIFESTS,
    AI_REQUEST_SCHEMA,
    AI_RUNTIME_SCHEMA,
    AITranscriptionCandidate,
    AITranscriptionNote,
    AITranscriptionRequest,
    ai_requirement_ready,
    collect_ai_diagnostics,
    resolve_ai_python,
)
from sunofriend.cli import main


class AIProtocolTests(unittest.TestCase):
    def test_manifests_keep_code_and_weight_licences_separate(self) -> None:
        muscriptor = AI_MODEL_MANIFESTS["muscriptor"]
        self.assertEqual(muscriptor.code_license, "MIT")
        self.assertEqual(muscriptor.weights_license, "CC-BY-NC-4.0")
        self.assertIn("never bundle", muscriptor.distribution_policy)

    def test_request_requires_absolute_existing_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "clip.wav"
            audio.touch()
            request = AITranscriptionRequest(
                audio_path=str(audio),
                backend="game",
                roles=("lead-vocal",),
                start_seconds=1.0,
                end_seconds=3.0,
            )
            request.validate()
            self.assertEqual(request.to_dict()["schema"], AI_REQUEST_SCHEMA)

        relative = AITranscriptionRequest(audio_path="clip.wav", backend="game")
        with self.assertRaisesRegex(ValueError, "must be absolute"):
            relative.validate(require_audio=False)

    def test_candidate_validates_raw_float_pitch_and_confidence(self) -> None:
        candidate = AITranscriptionCandidate(
            backend="game",
            model_version="1.0.3/checkpoint-sha256",
            notes=(
                AITranscriptionNote(
                    start_seconds=0.1,
                    end_seconds=0.4,
                    pitch=60.25,
                    confidence=0.8,
                    instrument="lead-vocal",
                ),
            ),
            warnings=("raw candidate; not yet repaired",),
        )
        document = candidate.to_dict()
        self.assertEqual(document["schema"], AI_CANDIDATE_SCHEMA)
        self.assertEqual(document["notes"][0]["pitch"], 60.25)
        self.assertEqual(document["manifest"]["backend"], "game")

    def test_invalid_note_is_rejected(self) -> None:
        note = AITranscriptionNote(1.0, 0.5, 200.0, confidence=2.0)
        with self.assertRaisesRegex(ValueError, "positive duration"):
            note.validate()


class AIRuntimeTests(unittest.TestCase):
    def test_resolver_preserves_virtual_environment_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "python"
            launcher.symlink_to(sys.executable)
            self.assertEqual(resolve_ai_python(launcher), launcher.absolute())

    def test_explicit_missing_python_does_not_fall_back_silently(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "AI Python was not found"):
            resolve_ai_python("/definitely/missing/sunofriend-ai-python")

    def test_missing_runtime_is_machine_readable(self) -> None:
        report = collect_ai_diagnostics("/definitely/missing/sunofriend-ai-python")
        self.assertEqual(report["schema"], AI_RUNTIME_SCHEMA)
        self.assertFalse(report["runtime_ready"])
        self.assertIn("run scripts/setup-ai-runtime.sh", report["runtime_error"])
        self.assertFalse(ai_requirement_ready(report, "runtime"))

    def test_requirement_checks_distinguish_runtime_and_models(self) -> None:
        report = {
            "runtime_ready": True,
            "torch_ready": True,
            "backends": {
                "muscriptor": {"software_ready": True},
                "game": {"software_ready": False},
                "rmvpe": {"software_ready": False},
            },
        }
        self.assertTrue(ai_requirement_ready(report, "torch"))
        self.assertTrue(ai_requirement_ready(report, "muscriptor"))
        self.assertFalse(ai_requirement_ready(report, "game"))
        self.assertFalse(ai_requirement_ready(report, "all"))

    @patch("sunofriend.ai_runtime.collect_ai_diagnostics")
    def test_ai_doctor_prints_json_and_honours_requirement(self, mocked) -> None:
        mocked.return_value = {
            "schema": AI_RUNTIME_SCHEMA,
            "runtime_ready": True,
            "torch_ready": True,
            "backends": {
                "muscriptor": {"software_ready": True},
                "game": {"software_ready": False},
                "rmvpe": {"software_ready": False},
            },
        }
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(["ai-doctor", "--require", "torch"])
        document = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(document["required_capability"], "torch")
        self.assertTrue(document["requirement_ready"])


if __name__ == "__main__":
    unittest.main()
