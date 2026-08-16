from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sunofriend.cli import main
from sunofriend.song_generation import (
    BackendCandidate,
    BackendRun,
    SONG_GENERATION_CANDIDATE_COUNT,
    SONG_GENERATION_PLAN_SCHEMA,
    SONG_GENERATION_RECEIPT_SCHEMA,
    SONG_GENERATION_REQUEST_SCHEMA,
    SongGenerationExecutionError,
    execute_song_generation,
    plan_song_generation,
)
from sunofriend.song_generation_ace_step import AceStepApiBackend


class _SuccessfulBackend:
    backend_id = "ace-step-api"

    def generate(self, plan, root: Path) -> BackendRun:
        candidates_dir = root / "candidates"
        candidates_dir.mkdir()
        candidates = []
        for index in range(1, SONG_GENERATION_CANDIDATE_COUNT + 1):
            path = candidates_dir / f"candidate-{index:02d}.wav"
            path.write_bytes(b"RIFF" + bytes([index]) * 32)
            candidates.append(
                BackendCandidate(
                    path=path,
                    metadata={"seed_value": str(1000 + index)},
                )
            )
        return BackendRun(
            backend_id=self.backend_id,
            candidates=tuple(candidates),
            request_mapping={"api": "fake", "parameters": {"batch_size": 2}},
            execution_evidence={"task_id": "fake-task"},
            exact_reproduction_available=True,
        )


class _FailingBackend:
    backend_id = "ace-step-api"

    def generate(self, plan, root: Path) -> BackendRun:
        raise RuntimeError("model service unavailable")


class SongGenerationTests(unittest.TestCase):
    def test_cli_defaults_to_a_read_only_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "song-generate",
                        str(reference),
                        "--lyrics",
                        str(lyrics),
                        "--style",
                        "raw guitar pop",
                        "--reference-strength",
                        "0.4",
                        "--style-strength",
                        "0.6",
                        "--out-dir",
                        str(root / "cli-output"),
                    ]
                )

            document = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(document["read_only"])
            self.assertFalse((root / "cli-output").exists())
            self.assertEqual(
                document["execution_requires"], ["--execute", "--confirm-rights"]
            )

    def test_cli_execution_requires_rights_confirmation_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            stderr = io.StringIO()

            with redirect_stderr(stderr), self.assertRaises(SystemExit) as context:
                main(
                    [
                        "song-generate",
                        str(reference),
                        "--lyrics",
                        str(lyrics),
                        "--style",
                        "raw guitar pop",
                        "--reference-strength",
                        "0.4",
                        "--style-strength",
                        "0.6",
                        "--out-dir",
                        str(root / "cli-output"),
                        "--execute",
                    ]
                )

            self.assertEqual(context.exception.code, 2)
            self.assertIn("--confirm-rights", stderr.getvalue())
            self.assertFalse((root / "cli-output").exists())

    def test_plan_is_read_only_hash_bound_and_request_is_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.wav"
            reference.write_bytes(b"reference-audio")
            lyrics = root / "lyrics.txt"
            lyrics.write_text(
                "[verse]\nA new beginning\n[chorus]\nSing it again\n",
                encoding="utf-8",
            )

            plan = plan_song_generation(
                reference,
                lyrics,
                root / "output",
                style_description="warm British guitar pop with a full-band chorus",
                reference_strength=0.35,
                style_strength=0.8,
            )

            self.assertFalse((root / "output").exists())
            document = plan.to_dict()
            request = plan.request_document()
            self.assertEqual(document["schema"], SONG_GENERATION_PLAN_SCHEMA)
            self.assertTrue(document["read_only"])
            self.assertEqual(request["schema"], SONG_GENERATION_REQUEST_SCHEMA)
            self.assertEqual(request["controls"]["candidate_count"], 2)
            self.assertEqual(request["controls"]["reference_strength"], 0.35)
            self.assertEqual(
                request["controls"]["style_description_strength"], 0.8
            )
            self.assertEqual(
                request["backend"]["strength_mapping"][
                    "style_description_strength"
                ]["value"],
                8.2,
            )
            self.assertNotIn(str(root), json.dumps(request, sort_keys=True))

    def test_plan_rejects_invalid_strength_rights_and_turbo_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            common = {
                "style_description": "indie rock",
                "reference_strength": 0.5,
                "style_strength": 0.5,
            }
            with self.assertRaisesRegex(ValueError, "reference strength"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "strength",
                    **{**common, "reference_strength": 1.1},
                )
            with self.assertRaisesRegex(ValueError, "authorised_private_use"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "rights",
                    **common,
                    rights_category="owned",
                )
            with self.assertRaisesRegex(ValueError, "Base model"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "turbo",
                    **common,
                    model="acestep-v15-turbo",
                )
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "remote-http",
                    **common,
                    api_base_url="http://music.example.test:8001",
                )

    def test_ace_step_payload_maps_both_strengths_and_exact_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "mapped",
                style_description="bright orchestral pop with urgent drums",
                reference_strength=0.25,
                style_strength=0.75,
                seed=71,
            )

            payload = AceStepApiBackend().request_payload(plan)

            self.assertEqual(payload["prompt"], plan.style_description)
            self.assertEqual(payload["lyrics"], plan.lyrics)
            self.assertEqual(payload["reference_audio_path"], str(plan.reference))
            self.assertEqual(payload["audio_cover_strength"], 0.25)
            self.assertEqual(payload["guidance_scale"], 7.75)
            self.assertEqual(payload["batch_size"], 2)
            self.assertEqual(payload["inference_steps"], 32)
            self.assertEqual(payload["seed"], 71)
            self.assertFalse(payload["use_random_seed"])
            self.assertEqual(payload["task_type"], "text2music")

    def test_execution_retains_two_candidates_and_reproducibility_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "result",
                style_description="soulful electronic pop",
                reference_strength=0.4,
                style_strength=0.7,
                seed=1234,
            )

            result = execute_song_generation(
                plan,
                confirm_rights=True,
                backend=_SuccessfulBackend(),
            )

            self.assertEqual(result.status, "complete")
            self.assertEqual(len(result.candidates), 2)
            request = json.loads(result.request.read_text(encoding="utf-8"))
            receipt = json.loads(result.receipt.read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], SONG_GENERATION_RECEIPT_SCHEMA)
            self.assertEqual(receipt["status"], "complete")
            self.assertEqual(receipt["request_sha256"], request["request_sha256"])
            self.assertEqual(receipt["candidate_count"], 2)
            self.assertTrue(receipt["reproduction"]["exact_available"])
            self.assertEqual(receipt["reproduction"]["requested_seed"], 1234)
            self.assertTrue(
                receipt["authority"][
                    "confirmed_for_private_personal_processing"
                ]
            )
            self.assertFalse(receipt["effects"]["candidate_selected"])
            self.assertEqual(
                [item["path"] for item in receipt["candidates"]],
                ["candidates/candidate-01.wav", "candidates/candidate-02.wav"],
            )
            for item in receipt["candidates"]:
                self.assertEqual(len(item["sha256"]), 64)
                self.assertGreater(item["bytes"], 0)

    def test_execution_failure_retains_a_durable_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "failed",
                style_description="dream pop",
                reference_strength=0.2,
                style_strength=0.6,
            )

            with self.assertRaises(SongGenerationExecutionError) as context:
                execute_song_generation(
                    plan,
                    confirm_rights=True,
                    backend=_FailingBackend(),
                )

            receipt_path = context.exception.receipt
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["candidate_count"], 0)
            self.assertEqual(receipt["error"]["type"], "RuntimeError")
            self.assertIn("model service unavailable", receipt["error"]["message"])

    def test_execution_rechecks_reference_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "changed",
                style_description="acoustic folk",
                reference_strength=0.3,
                style_strength=0.4,
            )
            reference.write_bytes(b"changed-reference")

            with self.assertRaisesRegex(ValueError, "reference audio changed"):
                execute_song_generation(
                    plan,
                    confirm_rights=True,
                    backend=_SuccessfulBackend(),
                )
            self.assertFalse((root / "changed").exists())

    def test_library_execution_requires_explicit_rights_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "unconfirmed",
                style_description="acoustic folk",
                reference_strength=0.3,
                style_strength=0.4,
            )

            with self.assertRaisesRegex(ValueError, "rights confirmation"):
                execute_song_generation(plan, backend=_SuccessfulBackend())
            self.assertFalse((root / "unconfirmed").exists())


def _inputs(root: Path) -> tuple[Path, Path]:
    reference = root / "reference.wav"
    reference.write_bytes(b"reference")
    lyrics = root / "lyrics.txt"
    lyrics.write_text("[verse]\nHello\n[chorus]\nAgain\n", encoding="utf-8")
    return reference, lyrics


if __name__ == "__main__":
    unittest.main()
