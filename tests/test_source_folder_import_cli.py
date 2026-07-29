from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from sunofriend.cli import (
    _load_source_folder_role_map,
    build_parser,
    main,
)


class SourceFolderImportCliTests(unittest.TestCase):
    def test_parser_exposes_explicit_folder_preparation_contract(self) -> None:
        args = build_parser().parse_args(
            [
                "source-import-folder",
                "separate-parts",
                "--out-dir",
                "fresh-prepared-stems",
                "--ffmpeg",
                "/tools/ffmpeg",
                "--ffprobe",
                "/tools/ffprobe",
                "--role-map",
                "roles.json",
                "--key",
                "B minor",
                "--bpm",
                "113",
                "--tuning-hz",
                "440",
                "--chords",
                "chords.pdf",
                "--no-discover-chords",
                "--rights-category",
                "owned",
                "--title",
                "Prepared song",
                "--accept-unconfirmed-origin",
                "--allow-conditional-format",
                "--plan",
            ]
        )

        self.assertEqual(args.source_folder, "separate-parts")
        self.assertEqual(args.out_dir, "fresh-prepared-stems")
        self.assertEqual(args.ffmpeg, "/tools/ffmpeg")
        self.assertEqual(args.ffprobe, "/tools/ffprobe")
        self.assertEqual(args.role_map, "roles.json")
        self.assertEqual(args.key, "B minor")
        self.assertEqual(args.bpm, 113.0)
        self.assertEqual(args.tuning_hz, 440.0)
        self.assertEqual(args.chords, "chords.pdf")
        self.assertTrue(args.no_discover_chords)
        self.assertEqual(args.rights_category, "owned")
        self.assertEqual(args.title, "Prepared song")
        self.assertTrue(args.accept_unconfirmed_origin)
        self.assertTrue(args.allow_conditional_format)
        self.assertTrue(args.plan)

    @patch("sunofriend.source_folder_import.plan_source_folder_import")
    def test_plan_is_read_only_and_forwards_exact_role_map(
        self,
        plan_source_folder_import: Mock,
    ) -> None:
        plan = Mock()
        plan.to_dict.return_value = {
            "schema": "sunofriend.source-folder-import-plan.v1",
            "read_only": True,
            "network_used": False,
            "executable": True,
        }
        plan_source_folder_import.return_value = plan
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temporary:
            role_map = Path(temporary) / "roles.json"
            role_map.write_text(
                json.dumps(
                    {
                        "Drum Stem.flac": "drums",
                        "Low Part.m4a": "bass",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "sunofriend.source_folder_import."
                    "execute_source_folder_import"
                ) as execute,
                redirect_stdout(stdout),
            ):
                result = main(
                    [
                        "source-import-folder",
                        "separate-parts",
                        "--out-dir",
                        "fresh-prepared-stems",
                        "--role-map",
                        str(role_map),
                        "--key",
                        "B minor",
                        "--bpm",
                        "113",
                        "--tuning-hz",
                        "440",
                        "--rights-category",
                        "licensed",
                        "--accept-unconfirmed-origin",
                        "--plan",
                    ]
                )

        self.assertEqual(result, 0)
        self.assertTrue(json.loads(stdout.getvalue())["read_only"])
        execute.assert_not_called()
        plan_source_folder_import.assert_called_once()
        call = plan_source_folder_import.call_args
        self.assertEqual(
            call.args,
            ("separate-parts", "fresh-prepared-stems"),
        )
        self.assertEqual(
            call.kwargs["role_map"],
            {
                "Drum Stem.flac": "drums",
                "Low Part.m4a": "bass",
            },
        )
        self.assertEqual(call.kwargs["key"], "B minor")
        self.assertEqual(call.kwargs["bpm"], 113.0)
        self.assertEqual(call.kwargs["tuning_hz"], 440.0)
        self.assertEqual(call.kwargs["rights_category"], "licensed")
        self.assertTrue(call.kwargs["accept_unconfirmed_origin"])

    @patch("sunofriend.source_folder_import.execute_source_folder_import")
    @patch("sunofriend.source_folder_import.plan_source_folder_import")
    def test_execution_prints_structured_local_result(
        self,
        plan_source_folder_import: Mock,
        execute_source_folder_import: Mock,
    ) -> None:
        plan = Mock()
        bass_part = Mock()
        bass_part.import_plan.role = "bass"
        vocal_part = Mock()
        vocal_part.import_plan.role = "vocals"
        plan.parts = (bass_part, vocal_part)
        plan_source_folder_import.return_value = plan
        execute_source_folder_import.return_value = Mock(
            root=Path("/result"),
            canonicals=(
                Path("/result/song-bass-canonical.wav"),
                Path("/result/song-vocals-canonical.wav"),
            ),
            originals=(
                Path("/result/INPUT/original/Bass.flac"),
                Path("/result/INPUT/original/Vocals.m4a"),
            ),
            receipts=(
                Path("/result/INPUT/receipts/Bass.flac.source-import.json"),
                Path(
                    "/result/INPUT/receipts/"
                    "Vocals.m4a.source-import.json"
                ),
            ),
            aggregate_receipt=Path(
                "/result/INPUT/source-folder-import.json"
            ),
            source_project=Path("/result/INPUT/source-project.json"),
            chord_document=None,
            source_ids=("sha256:bass", "sha256:vocals"),
            origin_status="compatible",
        )
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "source-import-folder",
                    "separate-parts",
                    "--out-dir",
                    "fresh-prepared-stems",
                ]
            )

        self.assertEqual(result, 0)
        document = json.loads(stdout.getvalue())
        self.assertEqual(
            document["schema"],
            "sunofriend.source-folder-import-result.v1",
        )
        self.assertEqual(document["status"], "complete")
        self.assertEqual(document["source_count"], 2)
        self.assertEqual(document["origin_status"], "compatible")
        self.assertEqual(document["roles"], ["bass", "vocals"])
        self.assertEqual(
            document["parts"],
            [
                {
                    "role": "bass",
                    "canonical": "/result/song-bass-canonical.wav",
                },
                {
                    "role": "vocals",
                    "canonical": "/result/song-vocals-canonical.wav",
                },
            ],
        )
        self.assertEqual(
            document["source_ids"],
            ["sha256:bass", "sha256:vocals"],
        )
        self.assertFalse(document["network_used"])
        self.assertFalse(document["normalised"])
        self.assertFalse(document["audio_normalised"])
        self.assertFalse(document["alignment_corrected"])
        execute_source_folder_import.assert_called_once_with(plan)

    def test_role_map_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "roles.json"
            path.write_text(
                '{"Bass.flac":"bass","Bass.flac":"keys"}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate key"):
                _load_source_folder_role_map(str(path))

    def test_role_map_loader_rejects_non_object_and_non_string_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            array_path = root / "array.json"
            array_path.write_text('["bass"]', encoding="utf-8")
            value_path = root / "value.json"
            value_path.write_text('{"Bass.flac": 1}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                _load_source_folder_role_map(str(array_path))
            with self.assertRaisesRegex(ValueError, "must be strings"):
                _load_source_folder_role_map(str(value_path))

    def test_role_map_loader_rejects_non_utf8_oversize_and_symlink(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "invalid.json"
            invalid.write_bytes(b"\xff")
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (64 * 1024 + 1))
            valid = root / "valid.json"
            valid.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(valid)

            with self.assertRaisesRegex(ValueError, "UTF-8"):
                _load_source_folder_role_map(str(invalid))
            with self.assertRaisesRegex(ValueError, "65536-byte"):
                _load_source_folder_role_map(str(oversized))
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                _load_source_folder_role_map(str(link))


if __name__ == "__main__":
    unittest.main()
