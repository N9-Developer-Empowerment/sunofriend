from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_artifacts import selected_candidates
from sunofriend.workbench_catalog import build_workbench_catalog, public_catalog
from sunofriend.workbench_privacy import (
    path_free_browser_state,
    path_free_role,
    validated_role,
)
from sunofriend.workbench_store import WorkbenchStore, contribution_preview


_PATH_ROLES = (
    "/Users/alice/ROLE_SENTINEL/song.wav",
    "source=/Users/alice/ROLE_SENTINEL/song.wav",
    "(/Users/alice/ROLE_SENTINEL/song.wav)",
    "file:///Users/alice/ROLE_SENTINEL/song.wav",
    "~/Music/ROLE_SENTINEL.wav",
    r"C:\Users\Alice\ROLE_SENTINEL.wav",
    r"\\server\share\ROLE_SENTINEL.wav",
    "../private/ROLE_SENTINEL.wav",
    "source=./private/ROLE_SENTINEL.wav",
    "private/ROLE_SENTINEL/song.wav",
    "Users/alice/Music/ROLE_SENTINEL.wav",
    "file:private/ROLE_SENTINEL.mid",
    "~alice/Music/ROLE_SENTINEL.wav",
    r"private\ROLE_SENTINEL\song.wav",
    "Secret ROLE_SENTINEL.wav",
    "C:private-ROLE_SENTINEL.mid",
    "Source ROLE_SENTINEL.wav: lead",
    "Source ROLE_SENTINEL.mid.",
    "Source ROLE_SENTINEL.sf2?",
)


class WorkbenchPrivacyTests(unittest.TestCase):
    def test_path_free_role_covers_local_path_forms_without_hiding_musical_slash(
        self,
    ) -> None:
        for role in _PATH_ROLES:
            with self.subTest(role=role):
                self.assertEqual(path_free_role(role), ("custom role", True))
                with self.assertRaisesRegex(ValueError, "local path"):
                    validated_role(role)

        self.assertEqual(path_free_role("bass / pluck"), ("bass / pluck", False))
        self.assertEqual(validated_role("bass / pluck"), "bass / pluck")
        self.assertEqual(
            path_free_role("bass / pluck / harmony"),
            ("bass / pluck / harmony", False),
        )

    def test_role_validation_rejects_multiline_empty_and_excessive_text(self) -> None:
        for role in ("", "bass\nprivate", "x" * 81):
            with self.subTest(role=role):
                with self.assertRaises(ValueError):
                    validated_role(role)

        for legacy_role in ({"path": "/private"}, "bass\nprivate", "x" * 81):
            with self.subTest(legacy_role=legacy_role):
                self.assertEqual(path_free_role(legacy_role), ("custom role", True))
        self.assertEqual(path_free_role(None), ("unclassified", False))

    def test_browser_state_redacts_role_without_mutating_private_state(self) -> None:
        current = {
            "stems": {
                "stem-a": {
                    "role": "source=/Users/alice/ROLE_SENTINEL/song.wav",
                    "candidates": {"a": {"notes": "private listening note"}},
                }
            },
            "event_count": 1,
        }

        projected = path_free_browser_state(current)

        self.assertEqual(projected["stems"]["stem-a"]["role"], "custom role")
        self.assertTrue(projected["stems"]["stem-a"]["role_redacted"])
        self.assertEqual(
            projected["stems"]["stem-a"]["candidates"]["a"]["notes"],
            "private listening note",
        )
        self.assertIn("ROLE_SENTINEL", current["stems"]["stem-a"]["role"])

    def test_path_like_role_is_removed_from_contribution_and_selection(self) -> None:
        catalog = _legacy_catalog("bass")
        stem = catalog["stems"][0]
        candidate = stem["candidates"][0]
        current = {
            "stems": {
                stem["stem_id"]: {
                    "role": "/Users/alice/ROLE_SENTINEL/song.wav",
                    "outcome": None,
                    "main_candidate_id": candidate["candidate_id"],
                    "candidates": {
                        candidate["candidate_id"]: {
                            "decision": "main",
                            "context": "full_mix",
                            "problem_tags": [],
                            "selection_active": True,
                        }
                    },
                }
            },
            "event_count": 1,
        }

        preview = contribution_preview(catalog, current, [])
        selected = selected_candidates(catalog, current)

        self.assertEqual(preview["stems"][0]["role"], "custom role")
        self.assertEqual(selected[0]["role"], "custom role")
        payload = json.dumps({"preview": preview, "selected": selected})
        self.assertNotIn("ROLE_SENTINEL", payload)
        self.assertNotIn("/Users/alice", payload)

    def test_public_catalog_redacts_legacy_configured_roles(self) -> None:
        catalog = _legacy_catalog("/Users/alice/ROLE_SENTINEL/song.wav")
        catalog["stems"][0]["candidates"][0]["role"] = (
            "source=/Users/alice/ROLE_SENTINEL/candidate.mid"
        )

        public = public_catalog(catalog)

        self.assertEqual(public["stems"][0]["role"], "custom role")
        self.assertEqual(public["stems"][0]["candidates"][0]["role"], "custom role")
        self.assertNotIn("ROLE_SENTINEL", json.dumps(public))

    def test_explicit_catalog_rejects_a_path_like_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Privacy Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            source = project / "Privacy Song-bass-D minor-120bpm-440hz.wav"
            source.write_bytes(b"RIFF-source")
            midi = candidates / "bass.mid"
            write_midi_file(
                midi,
                [
                    MidiTrack(
                        "Bass",
                        0,
                        33,
                        [NoteEvent(0.0, 0.5, 38, 90)],
                    )
                ],
                bpm=120.0,
            )
            document = root / "catalog.json"
            document.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "role": "/Users/alice/ROLE_SENTINEL/song.wav",
                                "candidates": [{"midi": str(midi)}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "local path"):
                build_workbench_catalog(
                    project,
                    candidate_roots=[candidates],
                    catalog_path=document,
                )

            catalog_document = json.loads(document.read_text(encoding="utf-8"))
            catalog_document["stems"][0]["role"] = "bass"
            document.write_text(json.dumps(catalog_document), encoding="utf-8")
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
                catalog_path=document,
            )
            stem = catalog["stems"][0]
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            with self.assertRaisesRegex(ValueError, "local path"):
                store.append(
                    catalog,
                    {
                        "event_type": "role_tag",
                        "stem_id": stem["stem_id"],
                        "role": "source=/Users/alice/ROLE_SENTINEL/song.wav",
                    },
                )
            self.assertEqual(store.events(catalog["project_id"]), [])


def _legacy_catalog(role: str) -> dict:
    return {
        "schema": "sunofriend.workbench-catalog.v1",
        "project_id": "privacy-project",
        "name": "Privacy fixture",
        "setup": {"bpm": 120.0, "key": "D minor", "tuning_hz": 440.0},
        "privacy": {"mode": "local"},
        "stems": [
            {
                "stem_id": "stem-a",
                "role": role,
                "source": {
                    "path": "/private/source.wav",
                    "sha256": "a" * 64,
                    "bytes": 10,
                },
                "candidates": [
                    {
                        "candidate_id": "candidate-a",
                        "role": role,
                        "midi_path": "/private/candidate.mid",
                        "midi": {
                            "path": "/private/candidate.mid",
                            "sha256": "b" * 64,
                            "bytes": 10,
                        },
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
