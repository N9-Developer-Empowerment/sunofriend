from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend import __version__
from sunofriend.cli import build_parser, main


class CliBasicsTests(unittest.TestCase):
    def test_version_uses_the_package_version(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"sunofriend {__version__}")

    def test_instrument_commands_accept_an_explicit_embedding_model(self) -> None:
        parser = build_parser()
        match = parser.parse_args(
            [
                "instrument-match",
                "stem.wav",
                "part.mid",
                "--kind",
                "bass",
                "--out-dir",
                "match",
                "--embedding-model",
                "openl3.onnx",
            ]
        )
        bundle = parser.parse_args(
            [
                "instrument-bundle",
                "stem.wav",
                "part.mid",
                "--kind",
                "bass",
                "--out-dir",
                "bundle",
                "--embedding-model",
                "openl3.onnx",
            ]
        )
        sample_pack = parser.parse_args(
            [
                "sample-pack",
                "stem.wav",
                "part.mid",
                "--kind",
                "bass",
                "--out-dir",
                "samples",
                "--embedding-model",
                "openl3.onnx",
            ]
        )

        self.assertEqual(match.embedding_model, "openl3.onnx")
        self.assertEqual(bundle.embedding_model, "openl3.onnx")
        self.assertEqual(sample_pack.embedding_model, "openl3.onnx")

    def test_instrument_preference_commands_are_explicit_and_advisory(self) -> None:
        parser = build_parser()

        feedback = parser.parse_args(
            [
                "instrument-feedback",
                "bundle",
                "--patch",
                "Small Time Piano",
                "--compared-with",
                "sunofriend-instrument",
                "--out",
                "feedback.json",
            ]
        )
        profile = parser.parse_args(
            [
                "instrument-profile",
                "feedback.json",
                "--out",
                "profile.json",
            ]
        )
        bundle = parser.parse_args(
            [
                "instrument-bundle",
                "stem.wav",
                "part.mid",
                "--kind",
                "keys",
                "--out-dir",
                "bundle-v2",
                "--preference-profile",
                "profile.json",
            ]
        )

        self.assertEqual(feedback.patch, "Small Time Piano")
        self.assertEqual(feedback.decision, "preferred")
        self.assertEqual(feedback.context, "full-mix")
        self.assertEqual(profile.feedback, ["feedback.json"])
        self.assertEqual(bundle.preference_profile, "profile.json")

    def test_preview_accepts_a_source_derived_soundfont(self) -> None:
        parser = build_parser()

        preview = parser.parse_args(
            [
                "preview",
                "performance.mid",
                "--out",
                "performance.wav",
                "--soundfont",
                "sunofriend-instrument.sf2",
            ]
        )

        self.assertEqual(preview.midi, "performance.mid")
        self.assertEqual(preview.out, "performance.wav")
        self.assertEqual(preview.soundfont, "sunofriend-instrument.sf2")

        stdout = io.StringIO()
        with (
            patch(
                "sunofriend.render.render_midi_to_wav",
                return_value=Path("performance.wav"),
            ) as render,
            redirect_stdout(stdout),
        ):
            result = main(
                [
                    "preview",
                    "performance.mid",
                    "--out",
                    "performance.wav",
                    "--soundfont",
                    "sunofriend-instrument.sf2",
                ]
            )

        self.assertEqual(result, 0)
        render.assert_called_once_with(
            Path("performance.mid"),
            Path("performance.wav"),
            soundfont_path="sunofriend-instrument.sf2",
        )
        self.assertEqual(stdout.getvalue().strip(), "performance.wav")

    def test_sample_pack_review_commands_keep_review_and_apply_separate(self) -> None:
        parser = build_parser()
        review = parser.parse_args(
            [
                "sample-pack-review",
                "sample-pack-v2",
                "--out-dir",
                "review",
            ]
        )
        apply = parser.parse_args(
            [
                "sample-pack-apply",
                "reviewed.json",
                "--out-dir",
                "sample-pack-v3",
                "--name",
                "Reviewed Bass",
                "--no-preview",
            ]
        )

        self.assertEqual(review.sample_pack, "sample-pack-v2")
        self.assertEqual(review.out_dir, "review")
        self.assertEqual(apply.review, "reviewed.json")
        self.assertEqual(apply.name, "Reviewed Bass")
        self.assertTrue(apply.no_preview)

        boundary_review = parser.parse_args(
            [
                "sample-pack-boundary-review",
                "sample-pack-v3",
                "--out-dir",
                "boundary-review",
            ]
        )
        boundary_apply = parser.parse_args(
            [
                "sample-pack-boundary-apply",
                "boundary.reviewed.json",
                "--out-dir",
                "boundary-v3",
                "--name",
                "Reviewed Boundary Bass",
                "--no-preview",
            ]
        )

        self.assertEqual(boundary_review.sample_pack_v3, "sample-pack-v3")
        self.assertEqual(boundary_review.out_dir, "boundary-review")
        self.assertEqual(boundary_apply.review, "boundary.reviewed.json")
        self.assertEqual(boundary_apply.name, "Reviewed Boundary Bass")
        self.assertTrue(boundary_apply.no_preview)

        ab_review = parser.parse_args(
            [
                "sample-pack-ab-review",
                "snare-v3",
                "toms-v3",
                "--out-dir",
                "blind-review",
            ]
        )
        ab_resolve = parser.parse_args(
            [
                "sample-pack-ab-resolve",
                "blind.reviewed.json",
                "--out",
                "blind.result.json",
            ]
        )

        self.assertEqual(ab_review.sample_pack_v3, ["snare-v3", "toms-v3"])
        self.assertEqual(ab_review.out_dir, "blind-review")
        self.assertEqual(ab_resolve.review, "blind.reviewed.json")
        self.assertEqual(ab_resolve.out, "blind.result.json")


if __name__ == "__main__":
    unittest.main()
