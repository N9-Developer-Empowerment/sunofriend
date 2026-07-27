from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.tui_model import (
    TUI_MIDI_MAP_SCHEMA,
    TUI_PROJECT_SCHEMA,
    TuiProjectConfig,
    build_tui_midi_map,
    candidate_roots_field,
    format_tui_midi_map,
    load_tui_project,
    parse_candidate_roots,
    safe_activity_line,
    workbench_command,
)
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_store import WorkbenchStore


class TuiModelTests(unittest.TestCase):
    def test_load_is_path_free_read_only_and_does_not_create_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, candidate_root = _project_fixture(Path(temporary))
            state = Path(temporary) / "not-created-state"
            config = TuiProjectConfig.create(
                project,
                candidate_roots=[candidate_root],
                state_dir=state,
            )

            snapshot = load_tui_project(config)

            self.assertEqual(snapshot.document["schema"], TUI_PROJECT_SCHEMA)
            product = snapshot.document["product_contract"]
            self.assertEqual(
                [row["output_id"] for row in product["required_outputs"]],
                [
                    "evaluated_editable_midi",
                    "midi_derived_song_interpretation_wav",
                ],
            )
            self.assertFalse(
                product["source_evidence"][
                    "mixed_into_song_interpretation_wav"
                ]
            )
            self.assertEqual(snapshot.document["counts"]["stem_count"], 2)
            self.assertEqual(
                snapshot.document["counts"]["midi_ready_stem_count"],
                2,
            )
            self.assertEqual(
                snapshot.document["counts"]["missing_midi_stem_count"],
                0,
            )
            self.assertEqual(
                snapshot.document["review_scope"],
                {
                    "existing_results_only": True,
                    "conversion_jobs_run": False,
                    "conversion_available": True,
                    "source_stem_count": 2,
                    "midi_ready_stem_count": 2,
                    "missing_midi_stem_count": 0,
                },
            )
            self.assertEqual(
                sum(row["candidate_count"] for row in snapshot.document["stems"]),
                2,
            )
            self.assertFalse(snapshot.decision_store_exists)
            self.assertFalse(state.exists())
            self.assertFalse(any(snapshot.document["effects"].values()))
            rendered = json.dumps(snapshot.document)
            self.assertNotIn(str(Path(temporary)), rendered)
            self.assertNotIn("midi_path", rendered)
            self.assertNotIn("source_path", rendered)

    def test_existing_explicit_decision_is_summarised_without_new_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidate_root = _project_fixture(root)
            state = root / "state"
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
            )
            bass = next(row for row in catalog["stems"] if row["role"] == "bass")
            candidate = bass["candidates"][0]
            store = WorkbenchStore(state / "workbench.sqlite3")
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": bass["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                    "notes": None,
                },
            )
            before = len(store.events(catalog["project_id"]))
            state_before = {
                path.relative_to(state): path.read_bytes()
                for path in state.rglob("*")
                if path.is_file()
            }

            snapshot = load_tui_project(
                TuiProjectConfig.create(
                    project,
                    candidate_roots=[candidate_root],
                    state_dir=state,
                )
            )

            bass_row = next(
                row for row in snapshot.document["stems"] if row["role"] == "bass"
            )
            self.assertTrue(snapshot.decision_store_exists)
            self.assertTrue(bass_row["decision_recorded"])
            self.assertEqual(bass_row["selected_part_count"], 1)
            self.assertEqual(bass_row["attention_code"], "ready-for-pack")
            state_after = {
                path.relative_to(state): path.read_bytes()
                for path in state.rglob("*")
                if path.is_file()
            }
            self.assertEqual(state_after, state_before)
            self.assertEqual(len(store.events(catalog["project_id"])), before)
            self.assertFalse(any(snapshot.document["effects"].values()))

    def test_midi_map_compares_primary_lanes_without_recording_preference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, candidate_root = _project_fixture(Path(temporary))
            snapshot = load_tui_project(
                TuiProjectConfig.create(project, candidate_roots=[candidate_root])
            )
            bass = next(
                row for row in snapshot.document["stems"] if row["role"] == "bass"
            )

            document = build_tui_midi_map(
                snapshot,
                bass["stem_id"],
                width=32,
            )

            self.assertEqual(document["schema"], TUI_MIDI_MAP_SCHEMA)
            self.assertEqual(document["lane_count"], 1)
            lane = document["lanes"][0]
            self.assertEqual(lane["status"], "available")
            self.assertEqual(len(lane["pitch_graph"]), 32)
            self.assertEqual(len(lane["density_graph"]), 32)
            self.assertEqual(lane["note_count"], 4)
            self.assertFalse(any(document["effects"].values()))
            rendered = format_tui_midi_map(document)
            self.assertIn("contour above, note activity below", rendered)
            self.assertIn("Sunofriend specialist", rendered)
            self.assertIn("4 notes", rendered)
            self.assertIn("C2–C3", rendered)

    def test_midi_map_explains_a_stem_with_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, candidate_root = _project_fixture(Path(temporary))
            (
                project
                / "TUI Demo-backing-vocals-B minor-113bpm-440hz.wav"
            ).write_bytes(b"RIFF-vocal-source")
            snapshot = load_tui_project(
                TuiProjectConfig.create(project, candidate_roots=[candidate_root])
            )
            empty = next(
                row
                for row in snapshot.document["stems"]
                if row["candidate_count"] == 0
            )

            document = build_tui_midi_map(snapshot, empty["stem_id"], width=32)

            self.assertEqual(document["lane_count"], 0)
            self.assertFalse(any(document["effects"].values()))
            self.assertEqual(
                snapshot.document["counts"]["midi_ready_stem_count"],
                2,
            )
            self.assertEqual(
                snapshot.document["counts"]["missing_midi_stem_count"],
                1,
            )
            self.assertIn(
                "No primary MIDI candidates are available",
                format_tui_midi_map(document),
            )

    def test_workbench_bridge_uses_existing_cli_and_hides_runtime_token(self) -> None:
        config = TuiProjectConfig.create(
            "/tmp/project",
            candidate_roots=["/tmp/results one", "/tmp/results two"],
            catalog_path="/tmp/catalog.json",
            state_dir="/tmp/state",
            soundfont_path="/tmp/sound.sf2",
            developer_inspector=True,
        )

        command = workbench_command(config)

        self.assertEqual(command[1:4], ("-m", "sunofriend", "workbench"))
        self.assertIn("--developer-inspector", command)
        self.assertEqual(command[-1], "--open")
        self.assertEqual(command.count("--candidate-root"), 2)
        self.assertEqual(
            safe_activity_line(
                "http://127.0.0.1:1234/#token=PRIVATEsTOKEN&view=overview"
            ),
            "http://127.0.0.1:1234/#token=<hidden>&view=overview",
        )
        self.assertEqual(
            safe_activity_line("Decisions: /Users/private/state.sqlite3"),
            "Decision store: local and private",
        )

    def test_candidate_root_field_round_trips_spaces(self) -> None:
        roots = ("/tmp/results one", "/tmp/results two")
        self.assertEqual(
            parse_candidate_roots(candidate_roots_field(roots)),
            roots,
        )


def _project_fixture(root: Path) -> tuple[Path, Path]:
    project = root / "TUI Demo-B minor-113bpm-440hz"
    candidates = root / "midi-results"
    project.mkdir()
    (project / "TUI Demo-bass-B minor-113bpm-440hz.wav").write_bytes(
        b"RIFF-bass-source"
    )
    (project / "TUI Demo-keys-B minor-113bpm-440hz.wav").write_bytes(
        b"RIFF-keys-source"
    )
    bass = candidates / "bass-specialist" / "bass_listened.mid"
    keys = candidates / "keys-specialist" / "keys_listened.mid"
    _write_midi(bass, pitches=(36, 40, 43, 48))
    _write_midi(keys, pitches=(59, 62, 66, 71))
    return project, candidates


def _write_midi(path: Path, *, pitches: tuple[int, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notes = [
        NoteEvent(
            index * 0.5,
            index * 0.5 + 0.4,
            pitch=pitch,
            velocity=80 + index,
        )
        for index, pitch in enumerate(pitches)
    ]
    write_midi_file(
        path,
        [MidiTrack(path.stem, 0, 32, notes)],
        bpm=113.0,
    )
