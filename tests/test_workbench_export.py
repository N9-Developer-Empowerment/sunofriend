from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend.cli import main
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_server import run_workbench
from sunofriend.workbench_store import WorkbenchStore


class WorkbenchReviewExportTests(unittest.TestCase):
    def test_in_progress_export_is_private_atomic_and_never_binds_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            state_dir = root / "chosen-state"
            output = root / "archives" / "in-progress.json"

            with patch(
                "sunofriend.workbench_server.create_workbench_server",
                side_effect=AssertionError("export must not create a server"),
            ):
                report = run_workbench(
                    project,
                    candidate_roots=[candidates],
                    state_dir=state_dir,
                    export_review_path=output,
                )

            payload = output.read_bytes()
            review = json.loads(payload)
            self.assertEqual(report["status"], "exported")
            self.assertEqual(report["review_status"], "in_progress")
            self.assertEqual(report["event_count"], 0)
            self.assertEqual(report["applied_event_count"], 0)
            self.assertFalse(report["server_started"])
            self.assertTrue(report["private_artifact"])
            self.assertIn("absolute paths", report["privacy_notice"])
            self.assertEqual(report["output"]["path"], str(output.resolve()))
            self.assertEqual(report["output"]["bytes"], len(payload))
            self.assertEqual(
                report["output"]["sha256"], hashlib.sha256(payload).hexdigest()
            )
            self.assertEqual(review["status"], "in_progress")
            self.assertEqual(review["events"], [])
            self.assertEqual(review["project"]["root"], str(project.resolve()))
            self.assertTrue((state_dir / "workbench.sqlite3").is_file())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(list(output.parent.glob(".*.tmp")), [])

    def test_cli_restores_reviewed_state_and_exports_private_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            state_dir = root / "chosen-state"
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store = WorkbenchStore(state_dir / "workbench.sqlite3")
            saved = store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                    "notes": "private listening note",
                },
            )
            output = root / "reviewed.json"
            stdout = io.StringIO()

            with (
                patch(
                    "sunofriend.workbench_server.create_workbench_server",
                    side_effect=AssertionError("export must not create a server"),
                ),
                redirect_stdout(stdout),
            ):
                result = main(
                    [
                        "workbench",
                        str(project),
                        "--candidate-root",
                        str(candidates),
                        "--state-dir",
                        str(state_dir),
                        "--export-review",
                        str(output),
                    ]
                )

            self.assertEqual(result, 0)
            report = json.loads(stdout.getvalue())
            review = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["review_status"], "reviewed")
            self.assertEqual(report["event_count"], 1)
            self.assertEqual(report["applied_event_count"], 1)
            self.assertEqual(review["status"], "reviewed")
            self.assertEqual(review["events"][0]["event_id"], saved["event_id"])
            self.assertEqual(
                review["events"][0]["payload"]["notes"],
                "private listening note",
            )
            restored = WorkbenchStore(state_dir / "workbench.sqlite3")
            self.assertEqual(
                [event["event_id"] for event in restored.events(catalog["project_id"])],
                [saved["event_id"]],
            )
            review_hash = review.pop("review_sha256")
            canonical = json.dumps(
                review, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            self.assertEqual(review_hash, hashlib.sha256(canonical).hexdigest())

    def test_existing_destination_is_rejected_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            output = root / "existing.json"
            output.write_bytes(b"keep-this-exactly")

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                run_workbench(
                    project,
                    candidate_roots=[candidates],
                    state_dir=root / "state",
                    export_review_path=output,
                )

            self.assertEqual(output.read_bytes(), b"keep-this-exactly")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_broken_symlink_destination_is_rejected_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            redirected_target = root / "redirected" / "private-review.json"
            output = root / "review.json"
            output.symlink_to(redirected_target)

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                run_workbench(
                    project,
                    candidate_roots=[candidates],
                    state_dir=root / "state",
                    export_review_path=output,
                )

            self.assertTrue(output.is_symlink())
            self.assertFalse(redirected_target.exists())

    def test_racing_destination_creation_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            output = root / "review.json"
            real_link = os.link

            def create_competing_destination(source: Path, target: Path) -> None:
                Path(target).write_bytes(b"competing-writer")
                real_link(source, target)

            with (
                patch(
                    "sunofriend.workbench_server.os.link",
                    side_effect=create_competing_destination,
                ),
                self.assertRaisesRegex(FileExistsError, "already exists"),
            ):
                run_workbench(
                    project,
                    candidate_roots=[candidates],
                    state_dir=root / "state",
                    export_review_path=output,
                )

            self.assertEqual(output.read_bytes(), b"competing-writer")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_export_rejects_inspect_and_open_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            output = root / "review.json"

            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "workbench",
                        str(project),
                        "--candidate-root",
                        str(candidates),
                        "--inspect",
                        "--export-review",
                        str(output),
                    ]
                )
            self.assertEqual(raised.exception.code, 2)

            with (
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                main(
                    [
                        "workbench",
                        str(project),
                        "--candidate-root",
                        str(candidates),
                        "--open",
                        "--export-review",
                        str(output),
                    ]
                )
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())


def _fixture(root: Path) -> tuple[Path, Path]:
    project = root / "Archive Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    (project / "Archive Song-bass-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-private-source"
    )
    write_midi_file(
        candidates / "bass_listened.mid",
        [
            MidiTrack(
                "Bass",
                0,
                33,
                [NoteEvent(start=0.0, end=0.5, pitch=38, velocity=90)],
            )
        ],
        bpm=120.0,
    )
    return project, candidates


if __name__ == "__main__":
    unittest.main()
