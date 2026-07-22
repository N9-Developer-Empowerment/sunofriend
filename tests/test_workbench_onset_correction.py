from __future__ import annotations

import hashlib
import json
import random
import tempfile
import time
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
    TimeSignature,
    TransformRecipe,
    write_clip_midi,
)
from sunofriend.library import ClipLibrary
from sunofriend.note_safety import normalize_midi_intervals
from sunofriend.workbench_clips import WorkbenchClipService
from sunofriend.workbench_correction import (
    CLIP_CORRECTION_CAPABILITY_SCHEMA,
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionService,
)
from sunofriend.workbench_onset import (
    CLIP_NOTE_ONSET_PREVIEW_SCHEMA,
    CLIP_NOTE_ONSET_RESULT_SCHEMA,
    CLIP_NOTE_ONSET_SUMMARY_SCHEMA,
    CLIP_NOTE_ONSET_WINDOW_SCHEMA,
    _BLOCK_REASONS,
    _EFFECT_KEYS,
    _bounded_window_content,
    _derive_correction_summary,
    _horizons,
    _normalized_intervals,
    _raw_interval,
    _source_interval_independence,
)
from sunofriend.workbench_correction import _note_ticks


_WINDOW_KEYS = {
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
}
_NOTE_KEYS = {
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
    "duration_ticks",
    "start_beat",
    "duration_beats",
    "source_start_seconds",
    "source_end_seconds",
    "microtiming_seconds",
    "end_microtiming_seconds",
    "articulation",
}
_DIFF_KEYS = {"kind", "changed_note_count", "timing_mode", "export_bpm", "changes"}
_CHANGE_KEYS = {
    "note_ref",
    "channel",
    "pitch",
    "before_start_tick",
    "after_start_tick",
    "before_end_tick",
    "after_end_tick",
    "duration_ticks",
    "tick_delta",
    "milliseconds_delta",
    "before_start_beat",
    "after_start_beat",
    "before_source_start_seconds",
    "after_source_start_seconds",
}
_FRESH_TRUE_EFFECTS = {
    "library_mutated",
    "child_clip_created",
    "correction_applied",
    "note_onset_changed",
    "note_timing_changed",
}


class WorkbenchOnsetCorrectionTests(unittest.TestCase):
    def test_dependency_precomputation_matches_reference_and_scales_once(self) -> None:
        generator = random.Random(6304)
        tempo = TempoMap.constant(120)
        for _case in range(80):
            notes = tuple(
                ClipNote.from_beats(
                    generator.randrange(0, 48) / 8,
                    generator.randrange(1, 25) / 8,
                    generator.randrange(58, 64),
                    generator.randrange(40, 120),
                    tempo,
                    release_velocity=generator.randrange(0, 8),
                )
                for _index in range(generator.randrange(1, 28))
            )
            clip = MidiClip(
                title="Dependency equivalence",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=notes,
            )
            ticks = [_note_ticks(clip, note) for note in clip.notes]
            normalized = _normalized_intervals(clip, ticks=ticks)
            expected = []
            for index, note_ticks in enumerate(ticks):
                raw = _raw_interval(clip, index, note_ticks)
                if sum(row == raw for row in normalized) != 1:
                    expected.append(False)
                    continue
                simulated = [
                    _raw_interval(clip, position, candidate_ticks)
                    for position, candidate_ticks in enumerate(ticks)
                    if position != index
                ]
                remaining = list(normalized)
                remaining.remove(raw)
                expected.append(normalize_midi_intervals(simulated) == remaining)
            self.assertEqual(
                _source_interval_independence(clip, ticks=ticks),
                tuple(expected),
            )

        long_notes = tuple(
            ClipNote.from_beats(
                index / 480,
                1 / 480,
                index % 128,
                80,
                tempo,
            )
            for index in range(5_000)
        )
        long_clip = MidiClip(
            title="Bounded long-song onset window",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 4, 0),
            notes=long_notes,
        )
        started = time.monotonic()
        window = _bounded_window_content(
            long_clip,
            hashlib.sha256(long_clip.canonical_bytes()).hexdigest(),
            {"start_tick": 0, "end_tick": 256},
        )
        elapsed = time.monotonic() - started
        self.assertEqual(len(window["notes"]), 256)
        self.assertEqual(window["editable_note_count"], 256)
        self.assertLess(elapsed, 2.0)

    def test_capability_exact_window_schema_four_block_reasons_and_drums(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _library):
                capability = corrections.capability()
                self.assertEqual(capability["schema"], CLIP_CORRECTION_CAPABILITY_SCHEMA)
                self.assertEqual(
                    capability["corrections"]["note_onset_shift_patch"],
                    {"enabled": True, "drum_family": True},
                )
                self.assertFalse(capability["corrections"]["timing"])
                self.assertEqual(capability["limits"]["maximum_onset_delta_ticks"], 480)
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                self.assertEqual(window["schema"], CLIP_NOTE_ONSET_WINDOW_SCHEMA)
                self.assertEqual(window["operation"], "clip-note-onset-window")
                self.assertEqual(window["correction_kind"], "note_onset_shift_patch")
                self.assertEqual(set(window), _WINDOW_KEYS)
                self.assertTrue(all(set(row) == _NOTE_KEYS for row in window["notes"]))
                self.assertEqual(set(window["blocked_reason_counts"]), set(_BLOCK_REASONS))
                self.assertEqual(
                    window["blocked_reason_counts"],
                    {
                        "context-note-outside-window": 1,
                        "duplicate-export-note-on": 2,
                        "normalized-lifetime-dependent": 2,
                        "unsupported-stem-locked-microtiming": 0,
                    },
                )
                self.assertEqual(window["blocked_note_count"], 5)
                self.assertEqual(window["editable_note_count"], 2)
                self.assertEqual(set(window["effects"]), _EFFECT_KEYS)
                self.assertTrue(all(value is False for value in window["effects"].values()))
                self._assert_path_free(root, window)

            stem = self._stem_parent(role="kick", channel=9)
            stem_root = root / "stem-library"
            ClipLibrary(stem_root).add(stem)
            with self._services(
                root / "stem", library_root=stem_root, parent_id=stem.clip_id
            ) as (clip_service, corrections, loaded, _library):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 1920)
                )
                blocked = next(row for row in window["notes"] if row["pitch"] == 38)
                editable = next(row for row in window["notes"] if row["pitch"] == 36)
                self.assertEqual(
                    blocked["edit_block_reason"],
                    "unsupported-stem-locked-microtiming",
                )
                self.assertTrue(editable["editable"])
                preview = corrections.preview(
                    self._preview_request(window, [(editable["note_ref"], 510)])
                )
                self.assertEqual(preview["diff"]["changes"][0]["channel"], 9)

    def test_musical_preview_moves_both_events_and_preserves_exact_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                before_inventory = self._inventory(library_root)
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                rows = [row for row in window["notes"] if row["editable"]]
                request = self._preview_request(
                    window,
                    [
                        (rows[0]["note_ref"], rows[0]["start_tick"] + 30),
                        (rows[1]["note_ref"], rows[1]["start_tick"] - 30),
                    ],
                )
                preview = corrections.preview(request)
                self.assertEqual(preview["schema"], CLIP_NOTE_ONSET_PREVIEW_SCHEMA)
                self.assertEqual(preview["status"], "previewed")
                self.assertEqual(
                    preview["operation"], "clip-note-onset-correction-preview"
                )
                self.assertEqual(set(preview["diff"]), _DIFF_KEYS)
                self.assertEqual(preview["diff"]["kind"], "note_onset_shift_patch")
                self.assertEqual(preview["diff"]["timing_mode"], "musical")
                self.assertEqual(preview["diff"]["changed_note_count"], 2)
                self.assertTrue(
                    all(set(change) == _CHANGE_KEYS for change in preview["diff"]["changes"])
                )
                self.assertEqual(
                    [change["tick_delta"] for change in preview["diff"]["changes"]],
                    [30, -30],
                )
                for change in preview["diff"]["changes"]:
                    self.assertEqual(
                        change["after_end_tick"] - change["before_end_tick"],
                        change["tick_delta"],
                    )
                    self.assertEqual(
                        change["after_start_tick"] - change["before_start_tick"],
                        change["tick_delta"],
                    )
                    self.assertEqual(
                        change["after_end_tick"] - change["after_start_tick"],
                        change["duration_ticks"],
                    )
                    self.assertAlmostEqual(
                        change["milliseconds_delta"],
                        change["tick_delta"] * 60_000.0 / (120 * 480),
                    )
                self.assertTrue(all(value is False for value in preview["effects"].values()))
                self.assertEqual(self._inventory(library_root), before_inventory)
                self._assert_path_free(root, preview)

    def test_stem_locked_positive_negative_and_signed_zero_preserve_source_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = self._stem_parent(signed_zero=True)
            library_root = root / "library"
            ClipLibrary(library_root).add(parent)
            with self._services(root, library_root=library_root, parent_id=parent.clip_id) as (
                clip_service,
                corrections,
                loaded,
                _library,
            ):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 1920)
                )
                editable = [row for row in window["notes"] if row["editable"]]
                request = self._preview_request(
                    window,
                    [
                        (editable[0]["note_ref"], editable[0]["start_tick"] + 30),
                        (editable[-1]["note_ref"], editable[-1]["start_tick"] - 30),
                    ],
                )
                preview = corrections.preview(request)
                self.assertEqual(preview["diff"]["timing_mode"], "stem_locked")
                for change in preview["diff"]["changes"]:
                    self.assertAlmostEqual(
                        change["milliseconds_delta"],
                        change["tick_delta"] * 60_000.0 / (120 * 480),
                    )
                result = corrections.create(self._create_request(preview, request))
                child = ClipLibrary(library_root, read_only=True).get(
                    result["child"]["clip_id"]
                )
                parent_by_pitch = {note.pitch: note for note in loaded.notes}
                child_by_pitch = {note.pitch: note for note in child.notes}
                for pitch in (36, 40):
                    before = parent_by_pitch[pitch]
                    after = child_by_pitch[pitch]
                    self.assertAlmostEqual(
                        before.source_end_seconds - before.source_start_seconds,
                        after.source_end_seconds - after.source_start_seconds,
                    )
                    self.assertEqual(before.pitch, after.pitch)
                    self.assertEqual(before.velocity, after.velocity)
                    self.assertEqual(before.release_velocity, after.release_velocity)
                    self.assertEqual(before.articulation, after.articulation)
                    self.assertEqual(before.microtiming_seconds, after.microtiming_seconds)
                    self.assertEqual(
                        before.end_microtiming_seconds, after.end_microtiming_seconds
                    )

    def test_validation_bounds_exact_types_counts_and_full_window_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _library):
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                row = next(item for item in window["notes"] if item["editable"])
                for target in (
                    row["start_tick"],
                    row["start_tick"] + 481,
                    row["start_tick"] - 481,
                    True,
                    float(row["start_tick"] + 1),
                    str(row["start_tick"] + 1),
                ):
                    with self.subTest(target=target), self.assertRaises(
                        WorkbenchClipCorrectionError
                    ):
                        corrections.preview(
                            self._preview_request(window, [(row["note_ref"], target)])
                        )
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "unique note refs"):
                    corrections.preview(
                        self._preview_request(
                            window,
                            [
                                (row["note_ref"], row["start_tick"] + 1),
                                (row["note_ref"], row["start_tick"] + 2),
                            ],
                        )
                    )
                context = next(
                    item
                    for item in window["notes"]
                    if item["edit_block_reason"] == "context-note-outside-window"
                )
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "blocked"):
                    corrections.preview(
                        self._preview_request(
                            window,
                            [(context["note_ref"], context["start_tick"] + 1)],
                        )
                    )
                tight = corrections.window(
                    self._window_request(clip_service, parent, 120, 1450)
                )
                safe = next(item for item in tight["notes"] if item["editable"])
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "fully inside"
                ):
                    corrections.preview(
                        self._preview_request(
                            tight,
                            [(safe["note_ref"], safe["start_tick"] + 30)],
                        )
                    )

            many = self._many_parent(65)
            many_root = root / "many-library"
            ClipLibrary(many_root).add(many)
            with self._services(
                root / "many", library_root=many_root, parent_id=many.clip_id
            ) as (clip_service, corrections, loaded, _library):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 960)
                )
                rows = [row for row in window["notes"] if row["editable"]]
                preview = corrections.preview(
                    self._preview_request(
                        window,
                        [(row["note_ref"], row["start_tick"] + 1) for row in rows[:64]],
                    )
                )
                self.assertEqual(preview["diff"]["changed_note_count"], 64)
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "1 to 64"):
                    corrections.preview(
                        self._preview_request(
                            window,
                            [
                                (row["note_ref"], row["start_tick"] + 1)
                                for row in rows[:65]
                            ],
                        )
                    )

    def test_lifetime_dependency_target_overlap_and_each_horizon_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _library):
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1920)
                )
                lifetime = [
                    row
                    for row in window["notes"]
                    if row["edit_block_reason"] == "normalized-lifetime-dependent"
                ]
                self.assertEqual({row["pitch"] for row in lifetime}, {64})
                self.assertEqual(len(lifetime), 2)
                for row in lifetime:
                    with self.assertRaisesRegex(WorkbenchClipCorrectionError, "blocked"):
                        corrections.preview(
                            self._preview_request(
                                window,
                                [(row["note_ref"], row["start_tick"] + 1)],
                            )
                        )

            overlap = self._overlap_parent()
            overlap_root = root / "overlap-library"
            ClipLibrary(overlap_root).add(overlap)
            with self._services(
                root / "overlap", library_root=overlap_root, parent_id=overlap.clip_id
            ) as (clip_service, corrections, loaded, _library):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 1920)
                )
                first = next(row for row in window["notes"] if row["start_tick"] == 480)
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "overlap"):
                    corrections.preview(
                        self._preview_request(window, [(first["note_ref"], 960)])
                    )

            for protected in ("beat", "export", "source"):
                with self.subTest(horizon=protected):
                    horizon = self._horizon_parent(protected)
                    horizon_root = root / f"{protected}-library"
                    ClipLibrary(horizon_root).add(horizon)
                    with self._services(
                        root / protected,
                        library_root=horizon_root,
                        parent_id=horizon.clip_id,
                    ) as (clip_service, corrections, loaded, _library):
                        window = corrections.window(
                            self._window_request(clip_service, loaded, 0, 1920)
                        )
                        row = next(item for item in window["notes"] if item["editable"])
                        with self.assertRaisesRegex(WorkbenchClipCorrectionError, "horizon"):
                            corrections.preview(
                                self._preview_request(
                                    window,
                                    [(row["note_ref"], row["start_tick"] - 30)],
                                )
                            )

    def test_create_replay_restart_exact_delta_forgery_and_deterministic_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                parent_bytes = parent.canonical_bytes()
                before_normalized = _normalized_intervals(parent)
                before_horizons = _horizons(parent)
                window = corrections.window(
                    self._window_request(clip_service, parent, 120, 1920)
                )
                row = next(item for item in window["notes"] if item["editable"])
                request = self._preview_request(
                    window, [(row["note_ref"], row["start_tick"] + 30)]
                )
                preview = corrections.preview(request)
                result = corrections.create(self._create_request(preview, request))
                self.assertEqual(result["schema"], CLIP_NOTE_ONSET_RESULT_SCHEMA)
                self.assertEqual(result["status"], "created")
                self.assertFalse(result["replayed"])
                self.assertEqual(
                    {key for key, value in result["effects"].items() if value},
                    _FRESH_TRUE_EFFECTS,
                )
                library = ClipLibrary(library_root, read_only=True)
                self.assertEqual(library.get(parent.clip_id).canonical_bytes(), parent_bytes)
                child = library.get(result["child"]["clip_id"])
                self.assertEqual(child.transform_recipe.operation, "shift_note_onsets")
                self.assertEqual(_horizons(child), before_horizons)
                after_normalized = _normalized_intervals(child)
                self.assertEqual(len(before_normalized), len(after_normalized))
                change = result["diff"]["changes"][0]
                before_key = (
                    parent.instrument.channel,
                    change["before_start_tick"],
                    change["pitch"],
                )
                survivors = [
                    interval
                    for interval in before_normalized
                    if (interval.channel, interval.start_tick, interval.pitch) != before_key
                ]
                replacement = next(
                    interval
                    for interval in after_normalized
                    if interval.start_tick == change["after_start_tick"]
                    and interval.pitch == change["pitch"]
                )
                expected = sorted(
                    [*survivors, replacement],
                    key=lambda note: (
                        note.start_tick,
                        note.channel,
                        note.pitch,
                        note.end_tick,
                        note.owner,
                        -note.velocity,
                    ),
                )
                self.assertEqual(after_normalized, expected)
                summary = corrections.correction_summary(child.clip_id)
                self.assertEqual(summary["schema"], CLIP_NOTE_ONSET_SUMMARY_SCHEMA)
                self.assertEqual(summary["changes"], result["diff"]["changes"])
                self.assertTrue(all(value is False for value in summary["effects"].values()))
                replay = corrections.create(self._create_request(preview, request))
                self.assertEqual(replay["status"], "replayed")
                self.assertTrue(replay["replayed"])
                self.assertTrue(all(value is False for value in replay["effects"].values()))
                self.assertEqual(len(library.list(limit=10_000)), 2)

                first_midi = root / "first.mid"
                second_midi = root / "second.mid"
                write_clip_midi(first_midi, child)
                write_clip_midi(second_midi, child)
                self.assertEqual(first_midi.read_bytes(), second_midi.read_bytes())
                self.assertEqual(
                    hashlib.sha256(first_midi.read_bytes()).hexdigest(),
                    hashlib.sha256(second_midi.read_bytes()).hexdigest(),
                )
                self._assert_path_free(root, preview, result, summary, replay)

                parameters = child.transform_recipe.parameters_dict
                forged_parameters = dict(parameters)
                forged_parameters["window_sha256"] = "f" * 64
                forged = replace(
                    child,
                    transform_recipe=TransformRecipe.create(
                        "shift_note_onsets", **forged_parameters
                    ),
                )
                with self.assertRaises(WorkbenchClipCorrectionError):
                    _derive_correction_summary(parent, forged)
                forged_child = replace(
                    child,
                    notes=(replace(child.notes[0], velocity=child.notes[0].velocity + 1),)
                    + child.notes[1:],
                )
                with self.assertRaises(WorkbenchClipCorrectionError):
                    _derive_correction_summary(parent, forged_child)

            with self._services(
                root / "restart", library_root=library_root, parent_id=child.clip_id
            ) as (_clip_service, restarted, _child, _library):
                restarted_summary = restarted.correction_summary(child.clip_id)
                self.assertEqual(restarted_summary["changes"], summary["changes"])
                self.assertTrue(
                    all(value is False for value in restarted_summary["effects"].values())
                )
                self._assert_path_free(root, restarted_summary)

    def test_crossing_note_order_and_shared_cas_identical_or_different(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = self._crossing_parent()
            library_root = root / "library"
            ClipLibrary(library_root).add(parent)
            with self._services(root / "first", library_root=library_root, parent_id=parent.clip_id) as (
                first_clips,
                first,
                first_parent,
                _library,
            ), self._services(
                root / "second", library_root=library_root, parent_id=parent.clip_id
            ) as (second_clips, second, second_parent, _library2):
                first_window = first.window(
                    self._window_request(first_clips, first_parent, 0, 1920)
                )
                second_window = second.window(
                    self._window_request(second_clips, second_parent, 0, 1920)
                )
                moving = next(row for row in first_window["notes"] if row["pitch"] == 60)
                first_request = self._preview_request(
                    first_window, [(moving["note_ref"], moving["start_tick"] + 480)]
                )
                first_preview = first.preview(first_request)
                second_moving = next(
                    row for row in second_window["notes"] if row["pitch"] == 60
                )
                identical_request = self._preview_request(
                    second_window,
                    [(second_moving["note_ref"], second_moving["start_tick"] + 480)],
                )
                identical_preview = second.preview(identical_request)
                # Moving past a different-pitch note is legal and child ordering remains canonical.
                created = first.create(self._create_request(first_preview, first_request))
                child = ClipLibrary(library_root, read_only=True).get(
                    created["child"]["clip_id"]
                )
                self.assertEqual(
                    [note.start_beat for note in child.notes],
                    sorted(note.start_beat for note in child.notes),
                )

                replay = second.create(
                    self._create_request(identical_preview, identical_request)
                )
                self.assertEqual(replay["status"], "replayed")

            stale_parent = self._crossing_parent(clip_id="stale-parent")
            stale_root = root / "stale-library"
            ClipLibrary(stale_root).add(stale_parent)
            with self._services(
                root / "stale-a", library_root=stale_root, parent_id=stale_parent.clip_id
            ) as (a_clips, a, loaded_a, _), self._services(
                root / "stale-b", library_root=stale_root, parent_id=stale_parent.clip_id
            ) as (b_clips, b, loaded_b, _):
                aw = a.window(self._window_request(a_clips, loaded_a, 0, 1920))
                bw = b.window(self._window_request(b_clips, loaded_b, 0, 1920))
                ar = next(row for row in aw["notes"] if row["pitch"] == 60)
                br = next(row for row in bw["notes"] if row["pitch"] == 60)
                areq = self._preview_request(aw, [(ar["note_ref"], ar["start_tick"] + 30)])
                breq = self._preview_request(bw, [(br["note_ref"], br["start_tick"] + 60)])
                ap = a.preview(areq)
                bp = b.preview(breq)
                a.create(self._create_request(ap, areq))
                with self.assertRaises(WorkbenchClipCorrectionConflictError):
                    b.create(self._create_request(bp, breq))
                self.assertEqual(
                    len(ClipLibrary(stale_root, read_only=True).list(limit=10_000)), 2
                )

    def test_exact_request_contract_and_stale_projection_are_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                window_request = self._window_request(
                    clip_service, parent, 120, 1920
                )
                for forged in (
                    {**window_request, "extra": True},
                    {key: value for key, value in window_request.items() if key != "window"},
                    {**window_request, "correction_kind": "pitch_patch"},
                ):
                    with self.subTest(forged=forged), self.assertRaises(
                        WorkbenchClipCorrectionError
                    ):
                        corrections.window(forged)
                window = corrections.window(window_request)
                row = next(item for item in window["notes"] if item["editable"])
                request = self._preview_request(
                    window, [(row["note_ref"], row["start_tick"] + 30)]
                )
                for forged in (
                    {**request, "extra": True},
                    {
                        **request,
                        "correction": {
                            **request["correction"],
                            "extra": True,
                        },
                    },
                    {**request, "window_sha256": "f" * 64},
                ):
                    with self.subTest(forged=forged), self.assertRaises(
                        WorkbenchClipCorrectionError
                    ):
                        corrections.preview(forged)
                preview = corrections.preview(request)
                before = self._inventory(library_root)
                bad_action = {
                    **self._create_request(preview, request),
                    "action": "preview",
                }
                with self.assertRaises(WorkbenchClipCorrectionError):
                    corrections.create(bad_action)
                stale_projection = {
                    **self._create_request(preview, request),
                    "projection_sha256": "f" * 64,
                }
                with self.assertRaises(WorkbenchClipCorrectionConflictError):
                    corrections.create(stale_projection)
                self.assertEqual(self._inventory(library_root), before)

    def test_signed_zero_intent_correction_and_recipe_payload_forgery_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = self._stem_parent(signed_zero=True)
            library_root = root / "library"
            ClipLibrary(library_root).add(parent)
            with self._services(root, library_root=library_root, parent_id=parent.clip_id) as (
                clip_service,
                corrections,
                loaded,
                _library,
            ):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 1920)
                )
                row = next(
                    item
                    for item in window["notes"]
                    if item["pitch"] == 36 and item["editable"]
                )
                request = self._preview_request(
                    window, [(row["note_ref"], row["start_tick"] + 30)]
                )
                preview = corrections.preview(request)
                result = corrections.create(self._create_request(preview, request))
                child = ClipLibrary(library_root, read_only=True).get(
                    result["child"]["clip_id"]
                )
                parameters = child.transform_recipe.parameters_dict

                for name, mutate in (
                    (
                        "intent",
                        lambda value: value.update(intent_sha256="f" * 64),
                    ),
                    (
                        "correction",
                        lambda value: value["correction"]["changes"][0].update(
                            target_start_tick=row["start_tick"] + 60
                        ),
                    ),
                    (
                        "signed-zero-after",
                        lambda value: value["changes"][0]["after"].update(
                            microtiming_seconds=0.0
                        ),
                    ),
                ):
                    forged_parameters = json.loads(json.dumps(parameters))
                    mutate(forged_parameters)
                    forged = replace(
                        child,
                        transform_recipe=TransformRecipe.create(
                            "shift_note_onsets", **forged_parameters
                        ),
                    )
                    with self.subTest(name=name), self.assertRaises(
                        WorkbenchClipCorrectionError
                    ):
                        _derive_correction_summary(loaded, forged)

    @contextmanager
    def _services(
        self,
        root: Path,
        *,
        library_root: Path | None = None,
        parent_id: str = "onset-parent",
    ):
        root.mkdir(parents=True, exist_ok=True)
        if library_root is None:
            library_root = root / "library"
            ClipLibrary(library_root).add(self._parent())
        parent = ClipLibrary(library_root, read_only=True).get(parent_id)
        pack, acceptance = self._acceptance(root, parent_id)
        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            clip_service = WorkbenchClipService.open(
                acceptance_result_path=acceptance,
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
            title="Private onset parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 4, 0, ("Private patch",)),
            notes=(
                ClipNote.from_beats(0, 0.5, 60, 70, tempo, release_velocity=1),
                ClipNote.from_beats(0.5, 0.25, 62, 71, tempo, release_velocity=2),
                ClipNote.from_beats(0.5, 0.5, 62, 72, tempo, release_velocity=3),
                ClipNote.from_beats(1, 2, 64, 73, tempo, release_velocity=4),
                ClipNote.from_beats(2, 0.5, 64, 74, tempo, release_velocity=5),
                ClipNote.from_beats(
                    2.5, 0.5, 67, 75, tempo, release_velocity=6, articulation="legato"
                ),
                ClipNote.from_beats(3, 0.25, 70, 76, tempo, release_velocity=7),
            ),
            key=KeySignature("C", "major"),
            chords=(
                ChordEvent(0, 4, "C", 0.0, 2.0),
                ChordEvent(4, 4, "G", 2.0, 4.0),
            ),
            provenance=Provenance(
                source_uri="/Users/private/onset.wav",
                source_stem="/Users/private/onset.wav",
                converter="test",
                details={"timing_mode": "musical"},
            ),
            clip_id="onset-parent",
        )

    @staticmethod
    def _stem_parent(
        *,
        role: str = "bass",
        channel: int = 0,
        signed_zero: bool = False,
    ) -> MidiClip:
        tempo = TempoMap.constant(120)
        first = ClipNote.from_beats(1, 0.5, 36, 90, tempo, release_velocity=7)
        if signed_zero:
            first = replace(
                first, microtiming_seconds=-0.0, end_microtiming_seconds=-0.0
            )
        return MidiClip(
            title="Private stem-locked parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument(role, 32, channel),
            notes=(
                first,
                ClipNote.from_beats(
                    2,
                    0.5,
                    38,
                    91,
                    tempo,
                    microtiming_seconds=0.01,
                    end_microtiming_seconds=0.01,
                ),
                ClipNote.from_beats(3, 0.25, 40, 92, tempo, release_velocity=9),
            ),
            chords=(ChordEvent(4, 4, "C", 2.0, 4.0),),
            provenance=Provenance(
                source_uri="/Users/private/stem.wav",
                source_stem="/Users/private/stem.wav",
                converter="test",
                details={"timing_mode": "stem_locked", "garageband_bpm": 120},
            ),
            clip_id="stem-parent",
        )

    @staticmethod
    def _many_parent(count: int) -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Many onset notes",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 0, 0),
            notes=tuple(
                ClipNote.from_beats(0.5, 0.25, pitch, 80, tempo)
                for pitch in range(count)
            ),
            chords=(ChordEvent(2, 2, "C", 1.0, 2.0),),
            clip_id="many-onset-parent",
        )

    @staticmethod
    def _overlap_parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Overlap onset parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 0, 0),
            notes=(
                ClipNote.from_beats(1, 0.5, 60, 80, tempo),
                ClipNote.from_beats(2, 0.5, 60, 81, tempo),
                ClipNote.from_beats(3, 0.25, 65, 82, tempo),
            ),
            chords=(ChordEvent(4, 2, "C", 2.0, 3.0),),
            clip_id="overlap-onset-parent",
        )

    @staticmethod
    def _horizon_parent(kind: str) -> MidiClip:
        tempo = TempoMap.constant(120)
        note = ClipNote.from_beats(1, 1, 60, 80, tempo)
        if kind == "beat":
            # Source/export remain held by a later tempo/chord event; only duration_beats moves.
            chords = (ChordEvent(0, 1, "C", 0.0, 0.5),)
        elif kind == "export":
            # Beat/source remain held by the long chord while the note owns export event horizon.
            chords = (ChordEvent(0, 4, "C", 0.0, 2.0),)
        elif kind == "source":
            # A retained source coordinate beyond the musical beat makes source horizon distinct.
            note = replace(note, source_start_seconds=2.0, source_end_seconds=2.5)
            chords = (ChordEvent(0, 4, "C", 0.0, 2.0),)
        else:
            raise AssertionError(kind)
        return MidiClip(
            title=f"{kind} horizon onset parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("lead", 80, 0),
            notes=(note,),
            chords=chords,
            clip_id=f"{kind}-horizon-onset-parent",
        )

    @staticmethod
    def _crossing_parent(*, clip_id: str = "crossing-onset-parent") -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Crossing onset parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 0, 0),
            notes=(
                ClipNote.from_beats(1, 0.25, 60, 80, tempo),
                ClipNote.from_beats(1.5, 0.25, 62, 81, tempo),
                ClipNote.from_beats(3, 0.25, 65, 82, tempo),
            ),
            chords=(ChordEvent(4, 2, "C", 2.0, 3.0),),
            clip_id=clip_id,
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
            "correction_kind": "note_onset_shift_patch",
        }

    @staticmethod
    def _preview_request(window: dict, changes: list[tuple[str, object]]) -> dict:
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
                "kind": "note_onset_shift_patch",
                "changes": [
                    {"note_ref": note_ref, "target_start_tick": target}
                    for note_ref, target in changes
                ],
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
    def _inventory(library_root: Path) -> tuple[tuple[str, str], ...]:
        library = ClipLibrary(library_root, read_only=True)
        return tuple(
            sorted(
                (row.clip_id, row.object_hash)
                for row in library.list(limit=10_000)
            )
        )

    @staticmethod
    def _assert_path_free(root: Path, *values: object) -> None:
        encoded = json.dumps(values, sort_keys=True)
        if str(root) in encoded or "/Users/private" in encoded:
            raise AssertionError("public onset response contains a local path")

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


if __name__ == "__main__":
    unittest.main()
