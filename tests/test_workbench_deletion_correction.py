from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import (
    ChordEvent,
    ClipNote,
    Instrument,
    KeySignature,
    MidiClip,
    Provenance,
    TempoMap,
    TempoPoint,
    TimeSignature,
    TransformRecipe,
    write_clip_midi,
)
from sunofriend.library import ClipLibrary
from sunofriend.workbench_clips import WorkbenchClipService
from sunofriend.workbench_correction import (
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionService,
)
from sunofriend.workbench_deletion import (
    CLIP_NOTE_DELETION_PREVIEW_SCHEMA,
    CLIP_NOTE_DELETION_RESULT_SCHEMA,
    CLIP_NOTE_DELETION_SUMMARY_SCHEMA,
    CLIP_NOTE_DELETION_WINDOW_SCHEMA,
    _BLOCK_REASONS,
    _DELETION_EFFECT_KEYS,
    _derive_correction_summary,
    _horizons,
    _normalized_intervals,
    _parse_correction,
)


_NOTE_ROW_KEYS = {
    "note_ref",
    "editable",
    "edit_block_reason",
    "export_note_on_group_size",
    "channel",
    "pitch",
    "velocity",
    "release_velocity",
    "start_tick",
    "end_tick",
    "start_beat",
    "duration_beats",
    "source_start_seconds",
    "source_end_seconds",
    "articulation",
}
_CHANGE_ROW_KEYS = {
    "note_ref",
    "channel",
    "start_tick",
    "end_tick",
    "start_beat",
    "duration_beats",
    "source_start_seconds",
    "source_end_seconds",
    "pitch",
    "velocity",
    "release_velocity",
    "articulation",
}
_DIFF_KEYS = {
    "kind",
    "changed_note_count",
    "changes",
    "note_count_before",
    "note_count_after",
    "normalized_midi_note_count_before",
    "normalized_midi_note_count_after",
    "pitch_range_before",
    "pitch_range_after",
    "duration_beats_before",
    "duration_beats_after",
    "duration_seconds_before",
    "duration_seconds_after",
    "retained_normalized_notes_changed",
    "unchanged",
}
_FRESH_TRUE_EFFECTS = {
    "library_mutated",
    "child_clip_created",
    "correction_applied",
    "note_deleted",
    "note_count_changed",
}


class WorkbenchDeletionCorrectionTests(unittest.TestCase):
    def test_capability_window_shape_block_reasons_and_drum_support(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _):
                capability = corrections.capability()
                self.assertEqual(
                    capability["corrections"]["note_delete_patch"],
                    {"enabled": True, "drum_family": True},
                )
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                self.assertEqual(window["schema"], CLIP_NOTE_DELETION_WINDOW_SCHEMA)
                self.assertEqual(window["operation"], "clip-note-deletion-window")
                self.assertEqual(window["correction_kind"], "note_delete_patch")
                self.assertEqual(
                    set(window),
                    {
                        "schema",
                        "operation",
                        "correction_kind",
                        "library",
                        "parent",
                        "window",
                        "timing",
                        "notes",
                        "visible_note_count",
                        "editable_note_count",
                        "blocked_note_count",
                        "blocked_reason_counts",
                        "chords",
                        "policies",
                        "effects",
                        "window_sha256",
                    },
                )
                self.assertTrue(all(set(row) == _NOTE_ROW_KEYS for row in window["notes"]))
                self.assertEqual(set(window["blocked_reason_counts"]), set(_BLOCK_REASONS))
                self.assertEqual(
                    window["blocked_reason_counts"],
                    {
                        "context-note-on-outside-window": 1,
                        "duplicate-export-note-on": 2,
                        "retained-note-lifetime-would-change": 1,
                        "clip-horizon-would-change": 0,
                        "only-note-in-clip": 0,
                    },
                )
                self.assertEqual(window["visible_note_count"], 6)
                self.assertEqual(window["editable_note_count"], 2)
                self.assertEqual(window["blocked_note_count"], 4)
                self.assertTrue(all(value is False for value in window["effects"].values()))
                self.assertEqual(set(window["effects"]), _DELETION_EFFECT_KEYS)
                self._assert_path_free(root, window)

            horizon = self._horizon_parent()
            horizon_root = root / "horizon-library"
            ClipLibrary(horizon_root).add(horizon)
            with self._services(
                root / "horizon",
                library_root=horizon_root,
                parent_id=horizon.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 960)
                )
                last = next(row for row in window["notes"] if row["pitch"] == 64)
                self.assertEqual(last["edit_block_reason"], "clip-horizon-would-change")

            only = self._single_note_parent()
            only_root = root / "only-library"
            ClipLibrary(only_root).add(only)
            with self._services(
                root / "only",
                library_root=only_root,
                parent_id=only.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 480)
                )
                self.assertEqual(
                    window["notes"][0]["edit_block_reason"], "only-note-in-clip"
                )

            drums = self._drum_parent()
            drum_root = root / "drum-library"
            ClipLibrary(drum_root).add(drums)
            with self._services(
                root / "drums",
                library_root=drum_root,
                parent_id=drums.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 960)
                )
                editable = next(row for row in window["notes"] if row["editable"])
                preview = corrections.preview(
                    self._preview_request(window, [editable["note_ref"]])
                )
                self.assertEqual(preview["diff"]["changes"][0]["channel"], 9)

    def test_preview_create_replay_restart_and_exact_survivors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (
                clip_service,
                corrections,
                parent,
                library_root,
            ):
                parent_bytes = parent.canonical_bytes()
                before_normalized = _normalized_intervals(parent)
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                editable = [row for row in window["notes"] if row["editable"]]
                request = self._preview_request(
                    window,
                    [editable[-1]["note_ref"], editable[0]["note_ref"]],
                )
                preview = corrections.preview(request)
                self.assertEqual(preview["schema"], CLIP_NOTE_DELETION_PREVIEW_SCHEMA)
                self.assertEqual(preview["status"], "previewed")
                self.assertEqual(
                    preview["operation"],
                    "clip-note-deletion-correction-preview",
                )
                self.assertEqual(
                    set(preview),
                    {
                        "schema",
                        "status",
                        "operation",
                        "intent_sha256",
                        "library",
                        "window",
                        "correction",
                        "parent",
                        "child",
                        "diff",
                        "warnings",
                        "effects",
                        "projection_sha256",
                    },
                )
                self.assertEqual(
                    preview["correction"]["changes"],
                    sorted(
                        preview["correction"]["changes"],
                        key=lambda row: row["note_ref"],
                    ),
                )
                diff = preview["diff"]
                self.assertEqual(set(diff), _DIFF_KEYS)
                self.assertEqual(diff["kind"], "note_delete_patch")
                self.assertEqual(diff["changed_note_count"], 2)
                self.assertEqual(diff["note_count_before"], 6)
                self.assertEqual(diff["note_count_after"], 4)
                self.assertEqual(diff["retained_normalized_notes_changed"], 0)
                self.assertTrue(all(set(row) == _CHANGE_ROW_KEYS for row in diff["changes"]))
                self.assertTrue(all(diff["unchanged"].values()))
                self.assertTrue(all(value is False for value in preview["effects"].values()))
                self._assert_path_free(root, preview)

                result = corrections.create(self._create_request(preview, request))
                self.assertEqual(result["schema"], CLIP_NOTE_DELETION_RESULT_SCHEMA)
                self.assertEqual(result["status"], "created")
                self.assertEqual(
                    result["operation"],
                    "clip-note-deletion-correction-create",
                )
                self.assertEqual(
                    {key for key, value in result["effects"].items() if value},
                    _FRESH_TRUE_EFFECTS,
                )
                self.assertEqual(set(result["effects"]), _DELETION_EFFECT_KEYS)
                library = ClipLibrary(library_root, read_only=True)
                self.assertEqual(
                    library.get(parent.clip_id).canonical_bytes(), parent_bytes
                )
                child = library.get(result["child"]["clip_id"])
                self.assertIsNotNone(child.transform_recipe)
                assert child.transform_recipe is not None
                self.assertEqual(child.transform_recipe.operation, "delete_clip_notes")
                self.assertEqual(
                    child.notes,
                    tuple(note for note in parent.notes if note.pitch not in {65, 67}),
                )
                for retained in child.notes:
                    self.assertIn(retained, parent.notes)
                self.assertEqual(parent.duration_beats, child.duration_beats)
                self.assertEqual(
                    _normalized_intervals(child),
                    [
                        row
                        for row in before_normalized
                        if row.pitch not in {65, 67}
                    ],
                )
                parent_midi = root / "parent.mid"
                child_midi = root / "child.mid"
                child_repeat_midi = root / "child-repeat.mid"
                write_clip_midi(parent_midi, parent)
                write_clip_midi(child_midi, child)
                write_clip_midi(child_repeat_midi, child)
                self.assertEqual(
                    child_midi.read_bytes(), child_repeat_midi.read_bytes()
                )
                deleted_export_keys = {
                    (row["channel"], row["start_tick"], row["pitch"])
                    for row in diff["changes"]
                }
                parent_events = _midi_note_intervals(parent_midi)
                child_events = _midi_note_intervals(child_midi)
                self.assertEqual(
                    child_events,
                    [
                        row
                        for row in parent_events
                        if (row[0], row[1], row[2]) not in deleted_export_keys
                    ],
                )

                summary = corrections.correction_summary(child.clip_id)
                assert summary is not None
                self.assertEqual(summary["schema"], CLIP_NOTE_DELETION_SUMMARY_SCHEMA)
                self.assertEqual(summary["operation"], "delete_clip_notes")
                self.assertEqual(summary["changed_note_count"], 2)
                self.assertEqual(set(summary["changes"][0]), _CHANGE_ROW_KEYS)
                self.assertTrue(all(summary["unchanged"].values()))
                self.assertTrue(all(value is False for value in summary["effects"].values()))

                replay = corrections.create(self._create_request(preview, request))
                self.assertEqual(replay["status"], "replayed")
                self.assertTrue(replay["replayed"])
                self.assertTrue(all(value is False for value in replay["effects"].values()))
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list(limit=10_000)),
                    2,
                )

            with self._services(
                root / "restart",
                library_root=library_root,
                parent_id=child.clip_id,
            ) as (_clip_service, restarted, _child, _):
                restarted_summary = restarted.correction_summary(child.clip_id)
                assert restarted_summary is not None
                self.assertEqual(restarted_summary["changes"], summary["changes"])
                self.assertEqual(
                    restarted_summary["child"]["object_sha256"],
                    result["child"]["object_sha256"],
                )
                self._assert_path_free(root, restarted_summary)

    def test_public_articulation_is_path_free_but_private_recipe_stays_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private_articulation = "/Users/alice/private/sample.wav"
            parent = self._parent()
            notes = list(parent.notes)
            notes[4] = replace(notes[4], articulation=private_articulation)
            parent = replace(
                parent,
                clip_id="private-articulation-parent",
                notes=tuple(notes),
            )
            library_root = root / "library"
            ClipLibrary(library_root).add(parent)

            with self._services(
                root / "service",
                library_root=library_root,
                parent_id=parent.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 1920)
                )
                private_note = next(row for row in window["notes"] if row["pitch"] == 65)
                self.assertTrue(private_note["editable"])
                self.assertEqual(private_note["articulation"], "private articulation")

                request = self._preview_request(window, [private_note["note_ref"]])
                preview = corrections.preview(request)
                self.assertEqual(
                    preview["diff"]["changes"][0]["articulation"],
                    "private articulation",
                )
                result = corrections.create(self._create_request(preview, request))
                self.assertEqual(
                    result["diff"]["changes"][0]["articulation"],
                    "private articulation",
                )
                summary = corrections.correction_summary(result["child"]["clip_id"])
                assert summary is not None
                self.assertEqual(
                    summary["changes"][0]["articulation"],
                    "private articulation",
                )
                self._assert_path_free(root, window)
                self._assert_path_free(root, preview)
                self._assert_path_free(root, result)
                self._assert_path_free(root, summary)
                public = json.dumps((window, preview, result, summary), sort_keys=True)
                self.assertNotIn(private_articulation, public)

                child = ClipLibrary(library_root, read_only=True).get(
                    result["child"]["clip_id"]
                )
                assert child.transform_recipe is not None
                retained = child.transform_recipe.parameters_dict["changes"][0]
                self.assertEqual(
                    retained["before"]["articulation"],
                    private_articulation,
                )

    def test_rejects_blocked_context_duplicate_lifetime_and_horizon_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _):
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                for row in window["notes"]:
                    reason = row["edit_block_reason"]
                    if reason is None:
                        continue
                    with self.subTest(reason=reason), self.assertRaisesRegex(
                        WorkbenchClipCorrectionError,
                        reason,
                    ):
                        corrections.preview(
                            self._preview_request(window, [row["note_ref"]])
                        )

            horizon = self._horizon_parent()
            horizon_root = root / "horizon-library"
            ClipLibrary(horizon_root).add(horizon)
            with self._services(
                root / "horizon",
                library_root=horizon_root,
                parent_id=horizon.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 960)
                )
                blocked = next(
                    row
                    for row in window["notes"]
                    if row["edit_block_reason"] == "clip-horizon-would-change"
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "clip-horizon-would-change",
                ):
                    corrections.preview(
                        self._preview_request(window, [blocked["note_ref"]])
                    )

    def test_beat_export_and_source_horizon_guards_each_block_independently(
        self,
    ) -> None:
        constant = TempoMap.constant(120)
        fixtures = (
            (
                "beat",
                MidiClip(
                    title="Beat horizon",
                    tempo_map=TempoMap(
                        (TempoPoint(0, 120), TempoPoint(4, 120))
                    ),
                    time_signature=TimeSignature(),
                    instrument=Instrument("keys", 4, 0),
                    notes=(
                        ClipNote(3, 1, 60, 70, 1.5, 2.0),
                        ClipNote(1, 1, 62, 71, 2.5, 3.0),
                    ),
                    clip_id="beat-horizon-parent",
                ),
                0,
            ),
            (
                "export",
                MidiClip(
                    title="Export horizon",
                    tempo_map=constant,
                    time_signature=TimeSignature(),
                    instrument=Instrument("keys", 4, 0),
                    notes=(
                        ClipNote(
                            3,
                            1,
                            60,
                            70,
                            1.5,
                            2.0,
                            end_microtiming_seconds=0.1,
                        ),
                        ClipNote(3, 1, 62, 71, 2.5, 3.0),
                    ),
                    clip_id="export-horizon-parent",
                ),
                1,
            ),
            (
                "source",
                MidiClip(
                    title="Source horizon",
                    tempo_map=constant,
                    time_signature=TimeSignature(),
                    instrument=Instrument("keys", 4, 0),
                    notes=(
                        ClipNote(0, 1, 60, 70, 0.0, 4.0),
                        ClipNote(3, 1, 62, 71, 1.5, 2.0),
                    ),
                    clip_id="source-horizon-parent",
                ),
                2,
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label, parent, changed_horizon_index in fixtures:
                with self.subTest(horizon=label):
                    library_root = root / f"{label}-library"
                    ClipLibrary(library_root).add(parent)
                    target_index = next(
                        index
                        for index, note in enumerate(parent.notes)
                        if note.pitch == 60
                    )
                    simulated = replace(
                        parent,
                        notes=tuple(
                            note
                            for index, note in enumerate(parent.notes)
                            if index != target_index
                        ),
                    )
                    before_horizons = _horizons(parent)
                    after_horizons = _horizons(simulated)
                    self.assertNotEqual(
                        before_horizons[changed_horizon_index],
                        after_horizons[changed_horizon_index],
                    )
                    for index in set(range(3)) - {changed_horizon_index}:
                        self.assertEqual(before_horizons[index], after_horizons[index])

                    with self._services(
                        root / label,
                        library_root=library_root,
                        parent_id=parent.clip_id,
                    ) as (clip_service, corrections, loaded, _):
                        window = corrections.window(
                            self._window_request(clip_service, loaded, 0, 2400)
                        )
                        target = next(
                            row for row in window["notes"] if row["pitch"] == 60
                        )
                        self.assertEqual(
                            target["edit_block_reason"],
                            "clip-horizon-would-change",
                        )

            cascade = MidiClip(
                title="Normalized export horizon",
                tempo_map=constant,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(
                    ClipNote.from_beats(0, 10, 60, 70, constant),
                    ClipNote.from_beats(4, 4, 62, 71, constant),
                    ClipNote.from_beats(5, 1, 60, 72, constant),
                ),
                clip_id="normalized-export-horizon-parent",
            )
            cascade_root = root / "normalized-export-library"
            ClipLibrary(cascade_root).add(cascade)
            without_pitch_62 = replace(
                cascade,
                notes=tuple(note for note in cascade.notes if note.pitch != 62),
            )
            self.assertEqual(cascade.duration_beats, without_pitch_62.duration_beats)
            self.assertEqual(
                _horizons(cascade)[1],
                8 * 480,
            )
            self.assertEqual(
                _horizons(without_pitch_62)[1],
                6 * 480,
            )
            with self._services(
                root / "normalized-export",
                library_root=cascade_root,
                parent_id=cascade.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 4800)
                )
                target = next(row for row in window["notes"] if row["pitch"] == 62)
                self.assertEqual(
                    target["edit_block_reason"],
                    "clip-horizon-would-change",
                )

    def test_patch_level_horizon_gate_stale_cas_and_exact_request_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tied = self._tied_horizon_parent()
            tied_root = root / "tied-library"
            ClipLibrary(tied_root).add(tied)
            with self._services(
                root / "tied",
                library_root=tied_root,
                parent_id=tied.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 960)
                )
                self.assertTrue(all(row["editable"] for row in window["notes"]))
                horizon_notes = [
                    row for row in window["notes"] if row["pitch"] in {60, 64}
                ]
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "horizon",
                ):
                    corrections.preview(
                        self._preview_request(
                            window,
                            [row["note_ref"] for row in horizon_notes],
                        )
                    )

            with self._services(root / "cas") as (
                clip_service,
                corrections,
                parent,
                library_root,
            ):
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                editable = [row for row in window["notes"] if row["editable"]]
                first_request = self._preview_request(window, [editable[0]["note_ref"]])
                second_request = self._preview_request(window, [editable[1]["note_ref"]])
                first = corrections.preview(first_request)
                second = corrections.preview(second_request)
                corrections.create(self._create_request(first, first_request))
                with self.assertRaises(WorkbenchClipCorrectionConflictError):
                    corrections.create(self._create_request(second, second_request))
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list(limit=10_000)),
                    2,
                )

                unknown_window = self._window_request(clip_service, parent, 0, 480)
                unknown_window["correction_kind"] = "expression_patch"
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "exact contract"):
                    corrections.window(unknown_window)

                top_level_forgery = dict(first_request)
                top_level_forgery["correction_kind"] = "note_delete_patch"
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "exact contract"):
                    corrections.preview(top_level_forgery)

                unknown_preview = dict(first_request)
                unknown_preview["correction"] = {
                    "kind": "expression_patch",
                    "changes": [{"note_ref": editable[0]["note_ref"]}],
                }
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "unknown"):
                    corrections.preview(unknown_preview)

    def test_change_bounds_and_forged_recipe_or_child_are_rejected(self) -> None:
        changes = [
            {"note_ref": hashlib.sha256(f"delete-{index}".encode()).hexdigest()}
            for index in range(65)
        ]
        parsed = _parse_correction(
            {"kind": "note_delete_patch", "changes": changes[:64]}
        )
        self.assertEqual(len(parsed["changes"]), 64)
        self.assertEqual(
            parsed["changes"],
            sorted(parsed["changes"], key=lambda row: row["note_ref"]),
        )
        with self.assertRaisesRegex(WorkbenchClipCorrectionError, "1 to 64"):
            _parse_correction({"kind": "note_delete_patch", "changes": changes})
        with self.assertRaisesRegex(WorkbenchClipCorrectionError, "unique note refs"):
            _parse_correction(
                {"kind": "note_delete_patch", "changes": [changes[0], changes[0]]}
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (
                clip_service,
                corrections,
                parent,
                library_root,
            ):
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                editable = next(row for row in window["notes"] if row["editable"])
                request = self._preview_request(window, [editable["note_ref"]])
                preview = corrections.preview(request)
                corrections.create(self._create_request(preview, request))
                child = ClipLibrary(library_root, read_only=True).get(
                    preview["child"]["clip_id"]
                )
                assert child.transform_recipe is not None
                parameters = child.transform_recipe.parameters_dict
                parameters["changes"][0]["before"]["velocity"] += 1
                forged_recipe = replace(
                    child,
                    transform_recipe=TransformRecipe.create(
                        "delete_clip_notes", **parameters
                    ),
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "before-note|exact retained edit diff",
                ):
                    _derive_correction_summary(parent, forged_recipe)

                signed_zero_parameters = child.transform_recipe.parameters_dict
                signed_zero_parameters["changes"][0]["before"][
                    "microtiming_seconds"
                ] = -0.0
                signed_zero_before_forgery = replace(
                    child,
                    transform_recipe=TransformRecipe.create(
                        "delete_clip_notes", **signed_zero_parameters
                    ),
                )
                self.assertEqual(signed_zero_before_forgery, child)
                self.assertNotEqual(
                    signed_zero_before_forgery.canonical_bytes(),
                    child.canonical_bytes(),
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "before-note",
                ):
                    _derive_correction_summary(parent, signed_zero_before_forgery)

                forged_notes = list(child.notes)
                forged_notes[0] = replace(
                    forged_notes[0], velocity=forged_notes[0].velocity + 1
                )
                forged_child = replace(child, notes=tuple(forged_notes))
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "exact retained edit diff|retained note",
                ):
                    _derive_correction_summary(parent, forged_child)

                signed_zero_notes = list(child.notes)
                signed_zero_notes[0] = replace(
                    signed_zero_notes[0], start_beat=-0.0
                )
                signed_zero_forgery = replace(
                    child,
                    notes=tuple(signed_zero_notes),
                )
                self.assertEqual(signed_zero_forgery, child)
                self.assertNotEqual(
                    signed_zero_forgery.canonical_bytes(), child.canonical_bytes()
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "exact retained edit diff|retained note",
                ):
                    _derive_correction_summary(parent, signed_zero_forgery)

    @contextmanager
    def _services(
        self,
        root: Path,
        *,
        library_root: Path | None = None,
        parent_id: str = "deletion-parent",
    ):
        root.mkdir(parents=True, exist_ok=True)
        if library_root is None:
            library_root = root / "library"
            ClipLibrary(library_root).add(self._parent())
        parent = ClipLibrary(library_root, read_only=True).get(parent_id)
        pack, result = self._acceptance(root, parent_id)
        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            clip_service = WorkbenchClipService.open(
                acceptance_result_path=result,
                garageband_pack_path=pack,
                library_root=library_root,
                cache_root=root / f"cache-{parent_id}",
            )
            corrections = WorkbenchClipCorrectionService.open(
                clip_service=clip_service,
                library_root=library_root,
            )
            yield clip_service, corrections, parent, library_root

    @staticmethod
    def _parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Private deletion parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 4, 0, ("Private patch",)),
            notes=(
                ClipNote.from_beats(0, 4, 60, 70, tempo, release_velocity=1),
                ClipNote.from_beats(1, 1, 60, 71, tempo, release_velocity=2),
                ClipNote.from_beats(2, 0.5, 62, 72, tempo, release_velocity=3),
                ClipNote.from_beats(2.0001, 0.75, 62, 73, tempo, release_velocity=4),
                ClipNote.from_beats(3, 0.5, 65, 74, tempo, release_velocity=5),
                ClipNote.from_beats(3.5, 0.5, 67, 75, tempo, release_velocity=6),
            ),
            key=KeySignature("C", "major"),
            chords=(
                ChordEvent(0, 4, "C", 0.0, 2.0),
                ChordEvent(4, 4, "C", 2.0, 4.0),
            ),
            provenance=Provenance(
                source_uri="/Users/private/deletion.wav",
                source_stem="/Users/private/deletion.wav",
                converter="test",
                details={"timing_mode": "musical"},
            ),
            clip_id="deletion-parent",
        )

    @staticmethod
    def _horizon_parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Horizon deletion parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 4, 0),
            notes=(
                ClipNote.from_beats(0, 1, 60, 70, tempo),
                ClipNote.from_beats(1, 1, 64, 71, tempo),
            ),
            clip_id="horizon-deletion-parent",
        )

    @staticmethod
    def _tied_horizon_parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Tied horizon deletion parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 4, 0),
            notes=(
                ClipNote.from_beats(0, 0.5, 55, 69, tempo),
                ClipNote.from_beats(0, 2, 60, 70, tempo),
                ClipNote.from_beats(1, 1, 64, 71, tempo),
            ),
            clip_id="tied-horizon-deletion-parent",
        )

    @staticmethod
    def _single_note_parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Single deletion parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("lead", 80, 0),
            notes=(ClipNote.from_beats(0, 0.5, 60, 90, tempo),),
            clip_id="single-deletion-parent",
        )

    @staticmethod
    def _drum_parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Drum deletion parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("kick", 0, 9),
            notes=(
                ClipNote.from_beats(0, 0.25, 36, 100, tempo),
                ClipNote.from_beats(1, 0.25, 36, 105, tempo),
            ),
            chords=(ChordEvent(0, 4, "C", 0.0, 2.0),),
            clip_id="drum-deletion-parent",
        )

    @staticmethod
    def _window_request(
        service: WorkbenchClipService,
        parent: MidiClip,
        start_tick: int,
        end_tick: int,
    ) -> dict:
        detail = service.detail(parent.clip_id)
        return {
            "parent_clip_id": parent.clip_id,
            "parent_object_sha256": detail["clip"]["object_sha256"],
            "library_state_sha256": detail["library_state_sha256"],
            "window": {"start_tick": start_tick, "end_tick": end_tick},
            "correction_kind": "note_delete_patch",
        }

    @staticmethod
    def _preview_request(window: dict, note_refs: list[str]) -> dict:
        return {
            "parent_clip_id": window["parent"]["clip_id"],
            "parent_object_sha256": window["parent"]["object_sha256"],
            "library_state_sha256": window["library"]["state_sha256"],
            "window": {
                "start_tick": window["window"]["start_tick"],
                "end_tick": window["window"]["end_tick"],
            },
            "window_sha256": window["window_sha256"],
            "correction": {
                "kind": "note_delete_patch",
                "changes": [{"note_ref": note_ref} for note_ref in note_refs],
            },
        }

    @staticmethod
    def _create_request(preview: dict, request: dict) -> dict:
        return {
            "action": "create",
            **request,
            "projection_sha256": preview["projection_sha256"],
        }

    @staticmethod
    def _assert_path_free(root: Path, value: object) -> None:
        encoded = json.dumps(value, sort_keys=True)
        if str(root) in encoded or "/Users/private" in encoded:
            raise AssertionError("public deletion response contains a local path")

    @staticmethod
    def _acceptance(root: Path, suffix: str) -> tuple[Path, Path]:
        pack = root / f"accepted-{suffix}.zip"
        pack.write_bytes(f"accepted {suffix}".encode())
        result = root / f"acceptance-{suffix}.json"
        result.write_text(
            json.dumps(
                {
                    "schema": "sunofriend.workbench-garageband-pack-acceptance-result.v1",
                    "operation": "garageband-pack-acceptance-resolve",
                    "status": "passed",
                    "phase6_read_only_clip_entry_ready": True,
                    "explicit_hybrid_construction_ready": False,
                    "pack": {
                        "name": "accepted.zip",
                        "bytes": pack.stat().st_size,
                        "sha256": hashlib.sha256(pack.read_bytes()).hexdigest(),
                    },
                    "developer_evidence": {"code_binding_sha256": "a" * 64},
                    "tutorial": {"completed": True, "slide_count": 8},
                    "quiz": {
                        "question_count": 10,
                        "score": 10,
                        "pass_score": 10,
                        "passed": True,
                    },
                    "acceptance_checks": [
                        {
                            "check_id": "garageband-pack",
                            "outcome": "passed",
                            "pass_count": 6,
                            "issue_count": 0,
                            "cannot_tell_count": 0,
                        },
                        {
                            "check_id": "local-usability",
                            "outcome": "passed",
                            "pass_count": 6,
                            "issue_count": 0,
                            "cannot_tell_count": 0,
                        },
                    ],
                    "remaining_local_studio_acceptance_gates": [],
                    "effects": {
                        "tutorial_changed_project": False,
                        "quiz_selected_candidate": False,
                        "feedback_recorded": False,
                        "musical_selection_changed": False,
                        "pack_basket_changed": False,
                        "midi_mutated": False,
                        "candidate_promoted": False,
                        "default_changed": False,
                        "data_submitted": False,
                        "phase6_started_automatically": False,
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return pack, result

def _midi_note_intervals(path: Path) -> list[tuple[int, int, int, int, int, int]]:
    import mido

    intervals: list[tuple[int, int, int, int, int, int]] = []
    for track in mido.MidiFile(path).tracks:
        tick = 0
        active: dict[tuple[int, int], tuple[int, int]] = {}
        for message in track:
            tick += int(message.time)
            if message.type == "note_on" and int(message.velocity) > 0:
                active[(int(message.channel), int(message.note))] = (
                    tick,
                    int(message.velocity),
                )
            elif message.type in {"note_off", "note_on"}:
                key = (int(message.channel), int(message.note))
                started = active.pop(key, None)
                if started is not None:
                    intervals.append(
                        (
                            key[0],
                            started[0],
                            key[1],
                            tick,
                            started[1],
                            int(message.velocity),
                        )
                    )
        if active:
            raise AssertionError("test MIDI contains an unterminated note")
    return sorted(intervals, key=lambda row: (row[1], row[0], row[2], row[3]))


if __name__ == "__main__":
    unittest.main()
