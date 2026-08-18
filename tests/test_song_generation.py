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
            self.assertEqual(
                request["controls"]["duration_policy"],
                "model_selected_from_lyrics_style_and_arrangement",
            )
            self.assertIsNone(request["controls"]["musical_metadata"]["bpm"])
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
            with self.assertRaisesRegex(ValueError, "song-providers"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "treblo",
                    **common,
                    backend="treblo-v3-api",
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

    def test_ace_step_payload_preserves_explicit_metadata_and_infers_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "metadata",
                style_description="bright acoustic electronic pop",
                reference_strength=0.35,
                style_strength=0.75,
                bpm=120,
                key="A Major",
                time_signature="4/4",
            )

            payload = AceStepApiBackend().request_payload(plan)
            controls = plan.request_document()["controls"]

            self.assertEqual(payload["bpm"], 120)
            self.assertEqual(payload["key_scale"], "A Major")
            self.assertEqual(payload["time_signature"], "4/4")
            self.assertNotIn("audio_duration", payload)
            self.assertEqual(controls["musical_metadata"]["bpm"], 120)
            self.assertEqual(controls["musical_metadata"]["key"], "A Major")
            self.assertEqual(
                controls["duration_policy"],
                "model_selected_from_lyrics_style_and_arrangement",
            )

    def test_native_remix_plan_maps_to_cover_and_source_locked_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            plan = plan_song_generation(
                reference,
                lyrics,
                root / "native-remix",
                style_description="new folktronica arrangement",
                reference_strength=0.2,
                style_strength=0.8,
                generation_mode="remix",
            )

            request = plan.request_document()
            payload = AceStepApiBackend().request_payload(plan)

            self.assertEqual(request["task"], "native_audio_remix")
            self.assertEqual(request["controls"]["generation_mode"], "remix")
            self.assertEqual(
                request["controls"]["duration_policy"],
                "source_locked_by_ace_step_cover",
            )
            self.assertEqual(
                request["inputs"]["reference"]["role"],
                "editable_source_audio",
            )
            self.assertEqual(payload["task_type"], "cover")
            self.assertEqual(payload["src_audio_path"], str(reference))
            self.assertNotIn("reference_audio_path", payload)

    def test_native_remix_rejects_unverifiable_musical_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)

            with self.assertRaisesRegex(ValueError, "locks duration to source"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "locked-remix",
                    style_description="new folktronica arrangement",
                    reference_strength=0.2,
                    style_strength=0.8,
                    generation_mode="remix",
                    bpm=120,
                )

    def test_plan_rejects_invalid_explicit_musical_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            common = {
                "style_description": "indie pop",
                "reference_strength": 0.35,
                "style_strength": 0.75,
            }
            with self.assertRaisesRegex(ValueError, "bpm"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "bad-bpm",
                    bpm=19,
                    **common,
                )
            with self.assertRaisesRegex(ValueError, "time_signature"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "bad-signature",
                    time_signature="common time",
                    **common,
                )
            with self.assertRaisesRegex(ValueError, "at least 10"):
                plan_song_generation(
                    reference,
                    lyrics,
                    root / "bad-duration",
                    duration_seconds=9.5,
                    **common,
                )

    def test_ace_step_accepts_current_openai_style_model_inventory(self) -> None:
        backend = AceStepApiBackend()

        backend._require_model(
            {
                "object": "list",
                "data": [
                    {
                        "id": "acestep/acestep-v15-base",
                        "name": "ACE-Step acestep-v15-base",
                    }
                ],
            },
            "acestep-v15-base",
        )

    def test_ace_step_allows_empty_inventory_during_lazy_initialisation(self) -> None:
        backend = AceStepApiBackend()

        backend._require_model(
            {"object": "list", "data": []},
            "acestep-v15-base",
        )

    def test_ace_step_rejects_a_different_current_model_inventory(self) -> None:
        backend = AceStepApiBackend()

        with self.assertRaisesRegex(RuntimeError, "acestep-v15-turbo"):
            backend._require_model(
                {
                    "object": "list",
                    "data": [{"id": "acestep/acestep-v15-turbo"}],
                },
                "acestep-v15-base",
            )

    def test_ace_step_rejects_candidate_checkpoint_substitution(self) -> None:
        backend = AceStepApiBackend()

        with self.assertRaisesRegex(RuntimeError, "substituted checkpoint"):
            backend._require_candidate_models(
                [
                    {"file": "/audio/one.wav", "dit_model": "acestep-v15-turbo"},
                    {"file": "/audio/two.wav", "dit_model": "acestep-v15-turbo"},
                ],
                "acestep-v15-base",
            )

    def test_ace_step_rejects_missing_candidate_checkpoint_evidence(self) -> None:
        backend = AceStepApiBackend()

        with self.assertRaisesRegex(RuntimeError, "omitted dit_model"):
            backend._require_candidate_models(
                [{"file": "/audio/one.wav"}],
                "acestep-v15-base",
            )

    def test_ace_step_streams_role_correct_audio_not_absolute_path(self) -> None:
        class RecordingBackend(AceStepApiBackend):
            def __init__(self) -> None:
                super().__init__()
                self.submission = None

            def _json_request(self, base_url, method, path, *, payload=None):
                self.assert_local(base_url)
                self.assertEqual(method, "GET")
                self.assertEqual(path, "/v1/models")
                return {
                    "object": "list",
                    "data": [{"id": "acestep/acestep-v15-base"}],
                }

            def _multipart_json_request(
                self, base_url, path, *, fields, file_field, file_path
            ):
                self.assert_local(base_url)
                self.submission = (path, fields, file_field, file_path)
                return {"code": 200, "data": {"task_id": "task-1"}}

            def _wait_for_result(self, plan, base_url, task_id):
                self.assertEqual(task_id, "task-1")
                return (
                    [
                        {
                            "file": "/audio/one.wav",
                            "seed_value": "11",
                            "dit_model": "acestep-v15-base",
                        },
                        {
                            "file": "/audio/two.wav",
                            "seed_value": "12",
                            "dit_model": "acestep-v15-base",
                        },
                    ],
                    {"status": 1},
                )

            def _download(self, base_url, value, destination):
                destination.write_bytes(b"RIFF" + value.encode("utf-8"))

            def assert_local(self, base_url):
                self.assertEqual(base_url, "http://127.0.0.1:8001")

            def assertEqual(self, first, second):
                if first != second:
                    raise AssertionError(f"{first!r} != {second!r}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference, lyrics = _inputs(root)
            for generation_mode, expected_field, expected_task in (
                ("reference", "reference_audio", "text2music"),
                ("remix", "src_audio", "cover"),
            ):
                with self.subTest(generation_mode=generation_mode):
                    plan = plan_song_generation(
                        reference,
                        lyrics,
                        root / f"planned-{generation_mode}",
                        style_description="warm acoustic electronic pop",
                        reference_strength=0.35,
                        style_strength=0.75,
                        generation_mode=generation_mode,
                    )
                    execution_root = root / f"execution-{generation_mode}"
                    execution_root.mkdir()
                    backend = RecordingBackend()

                    run = backend.generate(plan, execution_root)

                    path, fields, file_field, file_path = backend.submission
                    self.assertEqual(path, "/release_task")
                    self.assertEqual(file_field, expected_field)
                    self.assertEqual(file_path, reference)
                    self.assertNotIn("reference_audio_path", fields)
                    self.assertNotIn("src_audio_path", fields)
                    self.assertEqual(fields["task_type"], expected_task)
                    self.assertEqual(fields["batch_size"], 2)
                    self.assertEqual(
                        run.request_mapping["transport"], "multipart_file_upload"
                    )
                    self.assertEqual(len(run.candidates), 2)

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
