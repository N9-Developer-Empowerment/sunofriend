from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend.ai_runtime import (
    AI_CANDIDATE_SCHEMA,
    AI_CLEANUP_MODEL_MANIFESTS,
    AI_MODEL_MANIFESTS,
    AI_REQUEST_SCHEMA,
    AI_RUNTIME_SCHEMA,
    AITranscriptionCandidate,
    AITranscriptionNote,
    AITranscriptionRequest,
    ai_requirement_ready,
    collect_ai_diagnostics,
    collect_demucs_model,
    collect_game_model,
    collect_muscriptor_checkpoint,
    collect_pesto_model,
    collect_rmvpe_model,
    resolve_ai_python,
    resolve_demucs_model,
    resolve_game_model,
    resolve_muscriptor_checkpoint,
    resolve_pesto_model,
    resolve_rmvpe_model,
)
from sunofriend.cli import main


class AIProtocolTests(unittest.TestCase):
    def test_manifests_keep_code_and_weight_licences_separate(self) -> None:
        muscriptor = AI_MODEL_MANIFESTS["muscriptor"]
        self.assertEqual(muscriptor.code_license, "MIT")
        self.assertEqual(muscriptor.weights_license, "CC-BY-NC-4.0")
        self.assertIn("never bundle", muscriptor.distribution_policy)
        rmvpe = AI_MODEL_MANIFESTS["rmvpe"]
        self.assertIn("MIT", rmvpe.code_license)
        self.assertIn("MIT-labelled", rmvpe.weights_license)
        pesto = AI_MODEL_MANIFESTS["pesto"]
        self.assertEqual(pesto.code_license, "LGPL-3.0")
        self.assertIn("pinned commit", pesto.weights_license)
        demucs = AI_CLEANUP_MODEL_MANIFESTS["demucs"]
        self.assertEqual(demucs.code_license, "MIT")
        self.assertIn("private local evaluation", demucs.weights_license)
        self.assertIn("never vendor", demucs.distribution_policy)

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
        loaded = AITranscriptionCandidate.from_dict(document)
        self.assertEqual(loaded, candidate)

    def test_request_round_trip_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "clip.wav"
            audio.touch()
            request = AITranscriptionRequest(
                audio_path=str(audio), backend="muscriptor", roles=("piano",)
            )
            self.assertEqual(
                AITranscriptionRequest.from_dict(request.to_dict()), request
            )
            invalid = request.to_dict()
            invalid["schema"] = "future-schema"
            with self.assertRaisesRegex(ValueError, "schema"):
                AITranscriptionRequest.from_dict(invalid)

    def test_invalid_note_is_rejected(self) -> None:
        note = AITranscriptionNote(1.0, 0.5, 200.0, confidence=2.0)
        with self.assertRaisesRegex(ValueError, "positive duration"):
            note.validate()

        with self.assertRaisesRegex(ValueError, "finite"):
            AITranscriptionNote(0.0, 1.0, float("nan")).validate()


class AIRuntimeTests(unittest.TestCase):
    def _game_bundle(self, root: Path) -> Path:
        bundle = root / "game-model"
        bundle.mkdir()
        (bundle / "config.json").write_text(
            '{"samplerate":44100,"timestep":0.01}', encoding="utf-8"
        )
        for name in (
            "encoder.onnx",
            "segmenter.onnx",
            "estimator.onnx",
            "dur2bd.onnx",
            "bd2dur.onnx",
        ):
            (bundle / name).write_bytes(name.encode())
        return bundle

    def test_resolver_preserves_virtual_environment_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "python"
            launcher.symlink_to(sys.executable)
            self.assertEqual(resolve_ai_python(launcher), launcher.absolute())

    def test_explicit_missing_python_does_not_fall_back_silently(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "AI Python was not found"):
            resolve_ai_python("/definitely/missing/sunofriend-ai-python")

    def test_muscriptor_checkpoint_resolves_from_environment_and_is_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.safetensors"
            checkpoint.write_bytes(b"checkpoint fixture")
            config = checkpoint.with_name("config.json")
            config.write_text(
                '{"model_type":"muscriptor","variant":"small"}',
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"SUNOFRIEND_MUSCRIPTOR_MODEL": str(checkpoint)},
            ):
                self.assertEqual(resolve_muscriptor_checkpoint(), checkpoint)
                report = collect_muscriptor_checkpoint()
            self.assertTrue(report["checkpoint_ready"])
            self.assertTrue(report["config_ready"])
            self.assertEqual(report["variant"], "small")
            self.assertEqual(len(report["checkpoint_sha256"]), 64)

    def test_muscriptor_checkpoint_rejects_invalid_adjacent_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.safetensors"
            checkpoint.write_bytes(b"checkpoint fixture")
            checkpoint.with_name("config.json").write_text(
                '{"model_type":"other","variant":"small"}', encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {"SUNOFRIEND_MUSCRIPTOR_MODEL": str(checkpoint)},
            ):
                report = collect_muscriptor_checkpoint()
            self.assertTrue(report["checkpoint_ready"])
            self.assertFalse(report["config_ready"])
            self.assertIn("model_type", report["config_error"])

    def test_explicit_missing_muscriptor_checkpoint_does_not_fall_back(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "was not found"):
            resolve_muscriptor_checkpoint(
                "/definitely/missing/muscriptor-model.safetensors"
            )

    def test_game_model_resolves_and_hashes_every_onnx_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = self._game_bundle(Path(directory))
            with patch.dict(os.environ, {"SUNOFRIEND_GAME_MODEL": str(bundle)}):
                self.assertEqual(resolve_game_model(), bundle)
                report = collect_game_model()

            self.assertTrue(report["checkpoint_ready"])
            self.assertTrue(report["config_ready"])
            self.assertEqual(len(report["checkpoint_sha256"]), 64)
            self.assertEqual(len(report["components"]), 6)

    def test_incomplete_game_model_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "incomplete"
            bundle.mkdir()
            (bundle / "config.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                resolve_game_model(bundle)

    def test_rmvpe_model_resolves_and_requires_the_pinned_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "rmvpe.onnx"
            model.write_bytes(b"not the canonical checkpoint")
            with patch.dict(os.environ, {"SUNOFRIEND_RMVPE_MODEL": str(model)}):
                self.assertEqual(resolve_rmvpe_model(), model)
                report = collect_rmvpe_model()

            self.assertFalse(report["checkpoint_ready"])
            self.assertEqual(len(report["checkpoint_sha256"]), 64)
            self.assertIn("canonical", report["checkpoint_error"])

    def test_rmvpe_rejects_non_onnx_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "rmvpe.pt"
            model.write_bytes(b"checkpoint")
            with self.assertRaisesRegex(ValueError, "onnx"):
                resolve_rmvpe_model(model)

    def test_pesto_model_resolves_and_requires_the_pinned_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "mir-1k_g7.ckpt"
            model.write_bytes(b"not the canonical checkpoint")
            with patch.dict(os.environ, {"SUNOFRIEND_PESTO_MODEL": str(model)}):
                self.assertEqual(resolve_pesto_model(), model)
                report = collect_pesto_model()

            self.assertFalse(report["checkpoint_ready"])
            self.assertEqual(len(report["checkpoint_sha256"]), 64)
            self.assertIn("mir-1k_g7", report["checkpoint_error"])

    def test_pesto_rejects_non_ckpt_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "pesto.pt"
            model.write_bytes(b"checkpoint")
            with self.assertRaisesRegex(ValueError, "ckpt"):
                resolve_pesto_model(model)

    def test_demucs_model_resolves_and_requires_the_pinned_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "955717e8-8726e21a.th"
            model.write_bytes(b"not the canonical checkpoint")
            with patch.dict(os.environ, {"SUNOFRIEND_DEMUCS_MODEL": str(model)}):
                self.assertEqual(resolve_demucs_model(), model)
                report = collect_demucs_model()

            self.assertFalse(report["checkpoint_ready"])
            self.assertEqual(len(report["checkpoint_sha256"]), 64)
            self.assertIn("official htdemucs", report["checkpoint_error"])

    def test_demucs_rejects_non_th_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "htdemucs.pt"
            model.write_bytes(b"checkpoint")
            with self.assertRaisesRegex(ValueError, r"\.th"):
                resolve_demucs_model(model)

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
                "muscriptor": {
                    "software_ready": True,
                    "checkpoint_ready": True,
                    "config_ready": True,
                },
                "game": {
                    "software_ready": True,
                    "checkpoint_ready": True,
                    "config_ready": True,
                },
                "rmvpe": {"software_ready": False},
                "pesto": {"software_ready": False},
                "demucs": {"software_ready": False},
            },
        }
        self.assertTrue(ai_requirement_ready(report, "torch"))
        self.assertTrue(ai_requirement_ready(report, "muscriptor"))
        self.assertTrue(ai_requirement_ready(report, "muscriptor-checkpoint"))
        self.assertTrue(ai_requirement_ready(report, "game"))
        self.assertFalse(ai_requirement_ready(report, "all"))
        report["backends"]["rmvpe"] = {
            "software_ready": True,
            "checkpoint_ready": True,
        }
        self.assertTrue(ai_requirement_ready(report, "rmvpe"))
        report["backends"]["pesto"] = {
            "software_ready": True,
            "checkpoint_ready": True,
        }
        self.assertTrue(ai_requirement_ready(report, "pesto"))
        report["backends"]["demucs"] = {
            "software_ready": True,
            "checkpoint_ready": True,
        }
        self.assertTrue(ai_requirement_ready(report, "demucs"))
        self.assertTrue(ai_requirement_ready(report, "all"))
        report["backends"]["muscriptor"]["config_ready"] = False
        self.assertFalse(ai_requirement_ready(report, "muscriptor-checkpoint"))
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
                "pesto": {"software_ready": False},
                "demucs": {"software_ready": False},
            },
        }
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(["ai-doctor", "--require", "torch"])
        document = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(document["required_capability"], "torch")
        self.assertTrue(document["requirement_ready"])

    @patch("sunofriend.ai_bakeoff.run_ai_transcription")
    @patch("sunofriend.ai_runtime.resolve_muscriptor_checkpoint")
    def test_ai_transcribe_routes_explicit_muscriptor_execution_controls(
        self, resolve_model, run_transcription
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "mix.wav"
            audio.touch()
            model = root / "model.safetensors"
            model.touch()
            resolve_model.return_value = model
            run_transcription.return_value = {"status": "complete"}

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "ai-transcribe",
                        str(audio),
                        "--out-dir",
                        str(root / "runs"),
                        "--bpm",
                        "119",
                        "--batch-size",
                        "2",
                        "--beam-size",
                        "3",
                        "--cfg-coef",
                        "1.25",
                        "--model-size",
                        "small",
                    ]
                )

            self.assertEqual(result, 0)
            options = run_transcription.call_args.kwargs["options"]
            self.assertEqual(options["batch_size"], 2)
            self.assertEqual(options["beam_size"], 3)
            self.assertEqual(options["cfg_coef"], 1.25)
            self.assertEqual(options["model_size"], "small")
            self.assertFalse(options["prelude_forcing"])

    @patch("sunofriend.ai_bakeoff.run_ai_transcription")
    @patch("sunofriend.ai_runtime.resolve_game_model")
    def test_ai_transcribe_routes_game_controls_to_the_isolated_runner(
        self, resolve_model, run_transcription
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "voice.wav"
            audio.touch()
            model = root / "game-model"
            model.mkdir()
            resolve_model.return_value = model
            run_transcription.return_value = {"status": "complete"}

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "ai-transcribe",
                        str(audio),
                        "--backend",
                        "game",
                        "--out-dir",
                        str(root / "runs"),
                        "--bpm",
                        "119",
                        "--language",
                        "en",
                        "--seed",
                        "17",
                    ]
                )

            self.assertEqual(result, 0)
            resolve_model.assert_called_once_with(None)
            arguments = run_transcription.call_args.kwargs
            self.assertEqual(arguments["backend"], "game")
            self.assertEqual(arguments["checkpoint_path"], model)
            self.assertEqual(arguments["options"]["language"], "en")
            self.assertEqual(arguments["options"]["seed"], 17)

    @patch("sunofriend.ai_bakeoff.run_ai_transcription")
    @patch("sunofriend.ai_runtime.resolve_rmvpe_model")
    def test_ai_transcribe_routes_rmvpe_frame_decoder_controls(
        self, resolve_model, run_transcription
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "voice.wav"
            audio.touch()
            model = root / "rmvpe.onnx"
            model.touch()
            resolve_model.return_value = model
            run_transcription.return_value = {"status": "complete"}

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "ai-transcribe",
                        str(audio),
                        "--backend",
                        "rmvpe",
                        "--out-dir",
                        str(root / "runs"),
                        "--bpm",
                        "119",
                        "--confidence-threshold",
                        "0.05",
                        "--minimum-note-ms",
                        "90",
                        "--maximum-gap-ms",
                        "40",
                        "--pitch-change-semitones",
                        "0.8",
                    ]
                )

            self.assertEqual(result, 0)
            resolve_model.assert_called_once_with(None)
            arguments = run_transcription.call_args.kwargs
            self.assertEqual(arguments["backend"], "rmvpe")
            self.assertEqual(arguments["checkpoint_path"], model)
            self.assertEqual(arguments["options"]["confidence_threshold"], 0.05)
            self.assertEqual(arguments["options"]["minimum_note_ms"], 90.0)
            self.assertEqual(arguments["options"]["maximum_gap_ms"], 40.0)
            self.assertEqual(arguments["options"]["pitch_change_semitones"], 0.8)

    @patch("sunofriend.ai_bakeoff.run_ai_transcription")
    @patch("sunofriend.ai_runtime.resolve_pesto_model")
    def test_ai_transcribe_routes_pesto_frame_decoder_controls(
        self, resolve_model, run_transcription
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "voice.wav"
            audio.touch()
            model = root / "mir-1k_g7.ckpt"
            model.touch()
            resolve_model.return_value = model
            run_transcription.return_value = {"status": "complete"}

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "ai-transcribe",
                        str(audio),
                        "--backend",
                        "pesto",
                        "--out-dir",
                        str(root / "runs"),
                        "--bpm",
                        "119",
                        "--confidence-threshold",
                        "0.25",
                        "--pesto-step-ms",
                        "20",
                        "--pesto-reduction",
                        "argmax",
                        "--pesto-chunks",
                        "2",
                    ]
                )

            self.assertEqual(result, 0)
            resolve_model.assert_called_once_with(None)
            arguments = run_transcription.call_args.kwargs
            self.assertEqual(arguments["backend"], "pesto")
            self.assertEqual(arguments["checkpoint_path"], model)
            self.assertEqual(arguments["options"]["confidence_threshold"], 0.25)
            self.assertEqual(arguments["options"]["step_size_ms"], 20.0)
            self.assertEqual(arguments["options"]["reduction"], "argmax")
            self.assertEqual(arguments["options"]["num_chunks"], 2)


if __name__ == "__main__":
    unittest.main()
