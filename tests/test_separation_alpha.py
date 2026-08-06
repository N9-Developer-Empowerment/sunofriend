from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.audio_formats import AudioFormatDecision, AudioProbe, file_sha256
from sunofriend.separation_alpha import (
    PLAN_SCHEMA,
    SeparationPlan,
    SeparationProfile,
    build_parser,
    execute_separation,
    resolve_profile,
    separation_doctor,
)
from sunofriend.separation_scopes import (
    DEFAULT_SCOPE_ID,
    FULL_STEM_SCOPE_ID,
    separation_scope,
)
from sunofriend.separation_worker import chunk_boundaries


class SeparationAlphaTests(unittest.TestCase):
    def test_parser_keeps_plan_and_execution_explicit(self) -> None:
        parser = build_parser()
        planned = parser.parse_args(
            [
                "separate",
                "song.flac",
                "--out",
                "fresh-output",
                "--rights-category",
                "owned",
            ]
        )
        executed = parser.parse_args(
            [
                "separate",
                "song.flac",
                "--out",
                "fresh-output",
                "--rights-category",
                "owned",
                "--execute",
                "--confirm-rights",
                "--open-review",
            ]
        )

        self.assertFalse(planned.execute)
        self.assertFalse(planned.confirm_rights)
        self.assertEqual(planned.scope, DEFAULT_SCOPE_ID)
        self.assertTrue(executed.execute)
        self.assertTrue(executed.confirm_rights)
        self.assertTrue(executed.open_review)

    def test_parser_exposes_full_scope_without_enabling_it(self) -> None:
        parsed = build_parser().parse_args(
            [
                "separate",
                "song.wav",
                "--out",
                "fresh-output",
                "--rights-category",
                "owned",
                "--scope",
                FULL_STEM_SCOPE_ID,
            ]
        )

        self.assertEqual(parsed.scope, FULL_STEM_SCOPE_ID)

    def test_default_profile_is_public_data_root_not_private_work_evidence(
        self,
    ) -> None:
        with patch.dict("os.environ", {}, clear=True):
            profile = resolve_profile(root="/repo")

        self.assertEqual(profile.repository_root, Path("/repo").absolute())
        self.assertIn(".local/share/sunofriend/separation", str(profile.model_root))
        self.assertNotIn("separation-bakeoff", str(profile.model_root))
        self.assertEqual(profile.runtime_python.name, "python")

    def test_doctor_is_read_only_and_reports_setup_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = SeparationProfile(
                repository_root=root,
                runtime_python=root / "missing-python",
                model_root=root / "model",
                source_root=root / "model/source",
                checkpoint=root / "model/model.safetensors",
                companion_root=root / "model/companions",
            )
            before = list(root.iterdir())
            result = separation_doctor(profile)
            after = list(root.iterdir())

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "setup_required")
        self.assertEqual(result["effects"]["filesystem_write"], False)
        self.assertEqual(before, after)

    def test_chunk_boundaries_cover_song_and_keep_small_tail_valid(self) -> None:
        maximum = 661_500
        frames = maximum + 2_000
        boundaries = chunk_boundaries(frames)

        self.assertEqual(boundaries[0][0], 0)
        self.assertEqual(boundaries[-1][1], frames)
        self.assertEqual(boundaries[0][1], boundaries[1][0])
        self.assertGreaterEqual(boundaries[-1][1] - boundaries[-1][0], 4_096)
        self.assertLessEqual(boundaries[0][1] - boundaries[0][0], maximum)

    def test_fake_worker_publishes_role_driven_handoff_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "owned-song.wav"
            source.write_bytes(b"unchanged source evidence")
            output = root / "fresh-output"
            profile = SeparationProfile(
                repository_root=root,
                runtime_python=root / "runtime-python",
                model_root=root / "model",
                source_root=root / "model/source",
                checkpoint=root / "model/checkpoint",
                companion_root=root / "model/companions",
            )
            probe = AudioProbe(
                source=source,
                source_bytes=source.stat().st_size,
                stream_index=0,
                container_names=("wav",),
                codec="pcm_s24le",
                sample_format="s32",
                sample_rate=44_100,
                channels=2,
                channel_layout="stereo",
                duration_seconds=1.0,
                format_start_time_seconds=0.0,
                stream_start_time_seconds=0.0,
                stream_time_base="1/44100",
                stream_start_pts=0,
                stream_duration_ts=44_100,
                initial_padding_samples=0,
                trailing_padding_samples=0,
                skip_samples=0,
                discard_padding_samples=0,
                decision=AudioFormatDecision(
                    policy_name="portable-audio-v1",
                    container="wav",
                    codec="pcm_s24le",
                    lossless=True,
                    conditional=False,
                ),
            )
            plan = SeparationPlan(
                source=source,
                output=output,
                source_sha256=file_sha256(source),
                probe=probe,
                ffmpeg=root / "ffmpeg",
                ffprobe=root / "ffprobe",
                decoder={},
                profile=profile,
                scope=separation_scope(DEFAULT_SCOPE_ID),
                device="gpu",
                rights_category="owned",
                required_free_bytes=1,
                available_free_bytes=2,
            )

            def fake_worker(fake_plan: SeparationPlan, staging: Path):
                del fake_plan
                paths = {role.role_id: role.relative_path for role in plan.scope.roles}
                paths.update(
                    {
                        "source_reference": "SOURCE/source-reference.wav",
                        "reconstruction_check": "AUDIO/reconstruction-check.wav",
                    }
                )
                outputs = {}
                for role, relative in paths.items():
                    path = staging / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(f"{role} evidence".encode())
                    outputs[role] = {
                        "bytes": path.stat().st_size,
                        "sha256": file_sha256(path),
                    }
                return {"status": "complete_unreviewed", "outputs": outputs}

            doctor = {"status": "ready", "ready": True}
            with (
                patch("sunofriend.separation_alpha._run_command"),
                patch(
                    "sunofriend.separation_alpha.separation_doctor",
                    return_value=doctor,
                ),
            ):
                result = execute_separation(
                    plan,
                    confirm_rights=True,
                    worker_runner=fake_worker,
                )

            self.assertEqual(set(result["stems"]), {"vocals", "instrumental"})
            self.assertTrue((output / "START-HERE.txt").is_file())
            review = (output / "REVIEW/separation_review.html").read_text()
            report = json.loads(
                (output / "TECHNICAL/separation-report.json").read_text()
            )
            self.assertIn("experimental-separation-review.v3", review)
            self.assertEqual(report["separator"]["scope_id"], DEFAULT_SCOPE_ID)
            self.assertEqual(report["separator"]["roles"], ["vocals", "instrumental"])
            self.assertEqual(file_sha256(source), plan.source_sha256)

    def test_plan_schema_name_is_stable(self) -> None:
        self.assertEqual(PLAN_SCHEMA, "sunofriend.experimental-separation-plan.v1")

    def test_runtime_requirements_are_hash_pinned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "separation-runtime-requirements.txt").read_text()

        self.assertIn("mlx==0.31.2", text)
        self.assertIn("mlx-metal==0.31.2", text)
        self.assertIn("numpy==2.3.5", text)
        self.assertEqual(text.count("--hash=sha256:"), 6)

    def test_setup_script_uses_complete_sha256_identities(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts/setup-separation-alpha-macos.sh").read_text()
        calls = [
            line
            for line in script.splitlines()
            if line.startswith('download_verified "')
        ]

        self.assertEqual(len(calls), 9)
        for call in calls:
            fields = call.rsplit(" ", 2)
            self.assertEqual(len(fields), 3)
            self.assertEqual(len(fields[-2]), 64)
            int(fields[-2], 16)
            self.assertGreater(int(fields[-1]), 0)

    def test_agent_capability_json_will_remain_parseable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        document = json.loads(
            (root / "website/public/agent-capabilities.json").read_text()
        )
        self.assertIsInstance(document, dict)


if __name__ == "__main__":
    unittest.main()
