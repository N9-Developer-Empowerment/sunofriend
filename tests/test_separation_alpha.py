from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.separation_alpha import (
    PLAN_SCHEMA,
    SeparationProfile,
    build_parser,
    resolve_profile,
    separation_doctor,
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
        self.assertTrue(executed.execute)
        self.assertTrue(executed.confirm_rights)
        self.assertTrue(executed.open_review)

    def test_default_profile_is_public_data_root_not_private_work_evidence(self) -> None:
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
