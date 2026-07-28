from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.automatic_selection import (
    AUTOMATIC_SELECTION_POLICY,
    AutomaticSelectionError,
    plan_automatic_selection,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class AutomaticSelectionTests(unittest.TestCase):
    def test_exact_summary_primary_is_selected_without_human_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-B minor-113bpm-440hz"
            result = root / "result"
            project.mkdir()
            result.mkdir()
            source = project / "Song-bass-B minor-113bpm-440hz.wav"
            primary = result / "bass_listened.mid"
            variant = result / "bass_variant.mid"
            _write_wav(source)
            _write_midi(primary, pitch=38)
            _write_midi(variant, pitch=41)
            summary = result / "listen_all_summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "parts": {
                            "bass": {
                                "status": "ok",
                                "midi": str(primary),
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            catalog = _catalog(
                project,
                source,
                [
                    _candidate(primary, primary=True),
                    _candidate(variant, primary=True),
                ],
            )

            plan = plan_automatic_selection(
                catalog,
                (summary,),
                result_root=result,
            )

            self.assertEqual(len(plan.selected), 1)
            self.assertEqual(plan.selected[0]["midi_path"], primary.resolve())
            self.assertEqual(
                plan.receipt["policy"],
                AUTOMATIC_SELECTION_POLICY,
            )
            self.assertEqual(plan.receipt["review_status"], "not_reviewed")
            self.assertTrue(plan.receipt["effects"]["automatic_selection"])
            self.assertEqual(plan.receipt["effects"]["human_decision_events"], 0)
            self.assertNotIn(str(project), json.dumps(plan.receipt))
            self.assertFalse((root / "workbench.sqlite3").exists())

    def test_vocal_summary_source_pairing_is_exact_for_duplicate_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-C major-100bpm-440hz"
            result = root / "result"
            project.mkdir()
            result.mkdir()
            first_source = project / "Song-vocals-1-C major-100bpm-440hz.wav"
            second_source = project / "Song-vocals-2-C major-100bpm-440hz.wav"
            primary = result / "lead_vocal_melody.mid"
            _write_wav(first_source)
            _write_wav(second_source)
            _write_midi(primary, pitch=64)
            summary = result / "vocal_summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "role": "lead",
                        "source_stem": str(second_source),
                        "primary_midi": str(primary),
                    }
                ),
                encoding="utf-8",
            )
            candidate = _candidate(primary, primary=True)
            catalog = {
                "project_id": "project-vocals",
                "setup": {"bpm": 100.0, "key": "C major", "tuning_hz": 440.0},
                "stems": [
                    _stem("first", "vocals", first_source, [candidate]),
                    _stem("second", "vocals", second_source, [candidate]),
                ],
            }

            plan = plan_automatic_selection(
                catalog,
                (summary,),
                result_root=result,
            )

            self.assertEqual(len(plan.selected), 1)
            self.assertEqual(plan.selected[0]["stem_id"], "second")
            self.assertTrue(
                any(
                    row.get("stem_id") == "first"
                    and row["reason"] == "no_published_primary"
                    for row in plan.omitted
                )
            )

    def test_diagnostic_primary_is_not_silently_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-D minor-120bpm-440hz"
            result = root / "result"
            project.mkdir()
            result.mkdir()
            source = project / "Song-keys-D minor-120bpm-440hz.wav"
            midi = result / "keys_listened.mid"
            _write_wav(source)
            _write_midi(midi, pitch=60)
            summary = result / "listen_all_summary.json"
            summary.write_text(
                json.dumps(
                    {"parts": {"keys": {"status": "ok", "midi": str(midi)}}}
                ),
                encoding="utf-8",
            )
            candidate = _candidate(midi, primary=True)
            candidate["diagnostic_only"] = True
            catalog = _catalog(project, source, [candidate], role="keys")

            with self.assertRaisesRegex(
                AutomaticSelectionError,
                "no (exact )?primary|no published primary",
            ):
                plan_automatic_selection(
                    catalog,
                    (summary,),
                    result_root=result,
                )

    def test_summary_outside_result_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = root / "result"
            result.mkdir()
            summary = root / "outside.json"
            summary.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(
                AutomaticSelectionError,
                "outside",
            ):
                plan_automatic_selection(
                    {"project_id": "p", "setup": {}, "stems": []},
                    (summary,),
                    result_root=result,
                )


def _catalog(
    project: Path,
    source: Path,
    candidates: list[dict],
    *,
    role: str = "bass",
) -> dict:
    return {
        "project_id": "project-one",
        "name": project.name,
        "setup": {"bpm": 113.0, "key": "B minor", "tuning_hz": 440.0},
        "stems": [_stem("stem-one", role, source, candidates)],
    }


def _stem(
    stem_id: str,
    role: str,
    source: Path,
    candidates: list[dict],
) -> dict:
    return {
        "stem_id": stem_id,
        "label": role.title(),
        "role": role,
        "source_path": str(source.resolve()),
        "source": _record(source),
        "candidates": candidates,
    }


def _candidate(path: Path, *, primary: bool) -> dict:
    return {
        "candidate_id": "candidate-" + _sha256(path)[:16],
        "label": path.stem,
        "process": "sunofriend-specialist",
        "primary": primary,
        "diagnostic_only": False,
        "audition_blocked": False,
        "midi_path": str(path.resolve()),
        "midi": _record(path),
    }


def _record(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_midi(path: Path, *, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                "Part",
                0,
                0,
                [NoteEvent(0.0, 0.5, pitch, 90)],
            )
        ],
        bpm=113.0,
    )


def _write_wav(path: Path) -> None:
    with wave.open(str(path), mode="wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes((b"\x00\x01" * 4_410))


if __name__ == "__main__":
    unittest.main()
