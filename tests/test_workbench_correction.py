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
    read_midi_clip,
    write_clip_midi,
)
from sunofriend.library import ClipLibrary
from sunofriend.workbench_clips import WorkbenchClipService
from sunofriend.workbench_correction import (
    CLIP_CORRECTION_PREVIEW_SCHEMA,
    CLIP_CORRECTION_SUMMARY_SCHEMA,
    CLIP_CORRECTION_WINDOW_SCHEMA,
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionNotFoundError,
    WorkbenchClipCorrectionService,
    _child_from_recipe,
    _derive_correction_summary,
    _document_hash,
    _intent_document,
    _note_payload,
    _note_ref,
    _validate_parent_bounds,
)


class WorkbenchClipCorrectionTests(unittest.TestCase):
    def test_window_is_deterministic_path_free_zero_effect_and_refs_distinguish_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                request = self._window_request(clip_service, parent, 0, 1440)
                before = self._inventory(library_root)
                first = corrections.window(request)
                second = corrections.window(request)

                self.assertEqual(first, second)
                self.assertEqual(first["schema"], CLIP_CORRECTION_WINDOW_SCHEMA)
                self.assertEqual(first["window"]["ticks_per_beat"], 480)
                self.assertEqual(first["window"]["duration_seconds"], 1.5)
                self.assertEqual(first["visible_note_count"], 3)
                self.assertEqual(first["editable_note_count"], 3)
                self.assertEqual(len(first["chords"]), 1)
                self.assertEqual(first["chords"][0]["symbol"], "Dm")
                refs = [row["note_ref"] for row in first["notes"]]
                self.assertEqual(len(refs), len(set(refs)))
                self.assertNotEqual(refs[0], refs[1])
                self.assertTrue(all(value is False for value in first["effects"].values()))
                encoded = json.dumps(first, sort_keys=True)
                self.assertNotIn(str(root), encoded)
                self.assertNotIn("private-source.wav", encoded)
                self.assertEqual(self._inventory(library_root), before)

    def test_window_uses_exact_auto_export_ticks_for_musical_and_stem_locked_notes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            musical_tempo = TempoMap.constant(120)
            musical = MidiClip(
                title="Musical ticks",
                tempo_map=musical_tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(
                    ClipNote.from_beats(
                        1,
                        1,
                        60,
                        90,
                        musical_tempo,
                        microtiming_seconds=0.01,
                    ),
                ),
                clip_id="musical-parent",
            )
            library_root = root / "library-musical"
            ClipLibrary(library_root).add(musical)
            with self._services(
                root,
                library_root=library_root,
                parent_id=musical.clip_id,
            ) as (clip_service, corrections, parent, _):
                window = corrections.window(
                    self._window_request(clip_service, parent, 480, 960)
                )
                self.assertEqual(window["notes"][0]["start_tick"], 490)
                self.assertEqual(window["timing"]["resolved_mode"], "musical")

            stem_tempo = TempoMap.constant(120)
            stem_locked = MidiClip(
                title="Stem ticks",
                tempo_map=stem_tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("bass", 38, 0),
                notes=(ClipNote(100, 1, 48, 90, 0.5, 1.0),),
                provenance=Provenance(
                    details={"timing_mode": "stem_locked", "garageband_bpm": 120}
                ),
                clip_id="stem-parent",
            )
            library_root = root / "library-stem"
            ClipLibrary(library_root).add(stem_locked)
            with self._services(
                root,
                library_root=library_root,
                parent_id=stem_locked.clip_id,
            ) as (clip_service, corrections, parent, _):
                window = corrections.window(
                    self._window_request(clip_service, parent, 480, 960)
                )
                self.assertEqual(window["notes"][0]["start_tick"], 480)
                self.assertEqual(window["notes"][0]["end_tick"], 960)
                self.assertEqual(window["timing"]["resolved_mode"], "stem_locked")

    def test_preview_changes_only_named_pitches_and_reports_advisory_harmony(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                before = self._inventory(library_root)
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                preview = corrections.preview(
                    self._preview_request(
                        window,
                        [
                            (window["notes"][0]["note_ref"], 53),
                            (window["notes"][2]["note_ref"], 54),
                        ],
                    )
                )

                self.assertEqual(preview["schema"], CLIP_CORRECTION_PREVIEW_SCHEMA)
                self.assertEqual(preview["diff"]["changed_note_count"], 2)
                self.assertEqual(preview["diff"]["note_count_before"], 4)
                self.assertEqual(preview["diff"]["note_count_after"], 4)
                self.assertEqual(
                    preview["diff"]["pitch_range_before"],
                    {"minimum": 50, "maximum": 55},
                )
                self.assertEqual(
                    preview["diff"]["pitch_range_after"],
                    {"minimum": 50, "maximum": 55},
                )
                changes = preview["diff"]["changes"]
                self.assertEqual([row["before_pitch"] for row in changes], [50, 53])
                self.assertEqual([row["after_pitch"] for row in changes], [53, 54])
                self.assertEqual(changes[0]["key_relation_after"], "in-key")
                self.assertEqual(changes[0]["chord_relation_after"], "chord-tone")
                self.assertEqual(changes[1]["key_relation_after"], "chromatic")
                self.assertEqual(changes[1]["chord_relation_after"], "non-chord-tone")
                self.assertTrue(all(preview["diff"]["unchanged"].values()))
                self.assertTrue(all(value is False for value in preview["effects"].values()))
                self.assertNotIn("_resolved_changes", preview)
                self.assertEqual(self._inventory(library_root), before)

    def test_create_appends_one_exact_child_replays_and_summary_survives_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                parent_bytes = parent.canonical_bytes()
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                preview_request = self._preview_request(
                    window,
                    [
                        (window["notes"][0]["note_ref"], 52),
                        (window["notes"][2]["note_ref"], 54),
                    ],
                )
                preview = corrections.preview(preview_request)
                create_request = self._create_request(preview, preview_request)
                result = corrections.create(create_request)

                self.assertEqual(result["status"], "created")
                true_effects = {
                    key for key, value in result["effects"].items() if value is True
                }
                self.assertEqual(
                    true_effects,
                    {
                        "library_mutated",
                        "child_clip_created",
                        "correction_applied",
                        "note_pitch_changed",
                    },
                )
                library = ClipLibrary(library_root, read_only=True)
                self.assertEqual(library.get(parent.clip_id).canonical_bytes(), parent_bytes)
                child = library.get(result["child"]["clip_id"])
                self.assertEqual(child.parent_clip_id, parent.clip_id)
                self.assertEqual(child.revision, parent.revision + 1)
                self.assertEqual(child.transform_recipe.operation, "correct_note_pitches")
                self.assertEqual(sorted(note.pitch for note in child.notes), [50, 52, 54, 55])
                self._assert_non_pitch_fields_equal(parent, child)

                summary = corrections.correction_summary(child.clip_id)
                self.assertEqual(summary["schema"], CLIP_CORRECTION_SUMMARY_SCHEMA)
                self.assertEqual(summary["changed_note_count"], 2)
                self.assertTrue(all(value is False for value in summary["effects"].values()))
                self._assert_path_free(root, preview, result, summary)
                replay = corrections.create(create_request)
                self.assertEqual(replay["status"], "replayed")
                self.assertTrue(all(value is False for value in replay["effects"].values()))
                self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 2)

            with self._services(
                root,
                library_root=library_root,
                parent_id=child.clip_id,
            ) as (_clip_service, restarted, _child, _):
                restarted_summary = restarted.correction_summary(child.clip_id)
                self._assert_path_free(root, restarted_summary)
                self.assertEqual(restarted_summary["changes"], summary["changes"])
                self.assertEqual(
                    restarted_summary["child"]["object_sha256"],
                    result["child"]["object_sha256"],
                )
                restarted_replay = restarted.create(create_request)
                self.assertEqual(restarted_replay["status"], "replayed")
                self.assertTrue(
                    all(value is False for value in restarted_replay["effects"].values())
                )
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list()), 2
                )

    def test_stale_projection_conflicts_without_second_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                first_request = self._preview_request(
                    window, [(window["notes"][0]["note_ref"], 52)]
                )
                second_request = self._preview_request(
                    window, [(window["notes"][2]["note_ref"], 54)]
                )
                first = corrections.preview(first_request)
                second = corrections.preview(second_request)
                corrections.create(self._create_request(first, first_request))
                before = self._inventory(library_root)

                with self.assertRaises(WorkbenchClipCorrectionConflictError):
                    corrections.create(self._create_request(second, second_request))
                self.assertEqual(self._inventory(library_root), before)
                self.assertEqual(len(before), 2)

    def test_rejects_new_same_pitch_overlap_or_same_onset_collapse(self):
        for second_start in (0.0, 0.5):
            with self.subTest(second_start=second_start), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                tempo = TempoMap.constant(120)
                parent = MidiClip(
                    title="Collision parent",
                    tempo_map=tempo,
                    time_signature=TimeSignature(),
                    instrument=Instrument("keys", 4, 0),
                    notes=(
                        ClipNote.from_beats(0, 1, 60, 90, tempo),
                        ClipNote.from_beats(second_start, 1, 62, 90, tempo),
                    ),
                    clip_id="collision-parent",
                )
                library_root = root / "library"
                ClipLibrary(library_root).add(parent)
                with self._services(
                    root,
                    library_root=library_root,
                    parent_id=parent.clip_id,
                ) as (clip_service, corrections, loaded, _):
                    window = corrections.window(
                        self._window_request(clip_service, loaded, 0, 960)
                    )
                    first = next(row for row in window["notes"] if row["pitch"] == 60)
                    request = self._preview_request(
                        window, [(first["note_ref"], 62)]
                    )
                    with self.assertRaisesRegex(
                        WorkbenchClipCorrectionError,
                        "same-pitch MIDI overlap or collapse",
                    ):
                        corrections.preview(request)

    def test_existing_duplicate_collision_may_be_resolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _):
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 480)
                )
                duplicate = window["notes"][0]
                preview = corrections.preview(
                    self._preview_request(window, [(duplicate["note_ref"], 52)])
                )
                self.assertEqual(preview["diff"]["new_export_collisions"], 0)

    def test_rejects_drum_family_noneditable_invalid_pitch_and_exact_contract_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tempo = TempoMap.constant(120)
            drum = MidiClip(
                title="Kick",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("kick", 0, 0),
                notes=(ClipNote.from_beats(0, 0.25, 36, 100, tempo),),
                clip_id="kick-parent",
            )
            drum_root = root / "drum-library"
            ClipLibrary(drum_root).add(drum)
            with self._services(
                root,
                library_root=drum_root,
                parent_id=drum.clip_id,
            ) as (clip_service, corrections, parent, _):
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "Drum-family"):
                    corrections.window(
                        self._window_request(clip_service, parent, 0, 480)
                    )

            with self._services(root / "pitched") as (
                clip_service,
                corrections,
                parent,
                _,
            ):
                full = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                ref = full["notes"][0]["note_ref"]
                cases = (
                    [(ref, 50)],
                    [(ref, 75)],
                    [(ref, True)],
                    [(ref, 128)],
                    [(ref, 52), (ref, 53)],
                )
                for changes in cases:
                    with self.subTest(changes=changes), self.assertRaises(
                        WorkbenchClipCorrectionError
                    ):
                        corrections.preview(self._preview_request(full, changes))

                context = corrections.window(
                    self._window_request(clip_service, parent, 240, 480)
                )
                locked = next(row for row in context["notes"] if not row["editable"])
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "outside the editable window"
                ):
                    corrections.preview(
                        self._preview_request(context, [(locked["note_ref"], 52)])
                    )

                request = self._window_request(clip_service, parent, 0, 480)
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "exact contract"
                ):
                    corrections.window({**request, "extra": False})
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionConflictError, "library state"
                ):
                    corrections.window(
                        {**request, "library_state_sha256": "0" * 64}
                    )
                with self.assertRaises(WorkbenchClipCorrectionNotFoundError):
                    corrections.window({**request, "parent_clip_id": "missing"})

    def test_window_enforces_tick_seconds_note_and_chord_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _):
                base = self._window_request(clip_service, parent, 0, 480)
                for window in (
                    {"start_tick": -1, "end_tick": 480},
                    {"start_tick": 480, "end_tick": 480},
                    {"start_tick": 0, "end_tick": 32 * 480 + 1},
                    {"start_tick": 0.0, "end_tick": 480},
                    {"start_tick": False, "end_tick": 480},
                    {"start_tick": 10**100, "end_tick": 10**100 + 480},
                ):
                    with self.subTest(window=window), self.assertRaises(
                        WorkbenchClipCorrectionError
                    ):
                        corrections.window({**base, "window": window})
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "15 export seconds"):
                    corrections.window(
                        {**base, "window": {"start_tick": 0, "end_tick": 32 * 480}}
                    )
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "export horizon"):
                    corrections.window(
                        {**base, "window": {"start_tick": 3841, "end_tick": 4321}}
                    )

            dense_root = root / "dense-library"
            tempo = TempoMap.constant(240)
            dense = MidiClip(
                title="Dense",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=tuple(
                    ClipNote.from_beats(index / 1024, 1, 36 + (index % 80), 90, tempo)
                    for index in range(513)
                ),
                clip_id="dense-parent",
            )
            ClipLibrary(dense_root).add(dense)
            with self._services(
                root,
                library_root=dense_root,
                parent_id=dense.clip_id,
            ) as (clip_service, corrections, parent, _):
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "512 visible-note"):
                    corrections.window(
                        self._window_request(clip_service, parent, 0, 480)
                    )

            editable_root = root / "editable-library"
            editable = MidiClip(
                title="Too many editable notes",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=tuple(
                    ClipNote.from_beats(index / 512, 1 / 1024, 60, 90, tempo)
                    for index in range(257)
                ),
                clip_id="editable-parent",
            )
            ClipLibrary(editable_root).add(editable)
            with self._services(
                root,
                library_root=editable_root,
                parent_id=editable.clip_id,
            ) as (clip_service, corrections, parent, _):
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "256 editable-note"
                ):
                    corrections.window(
                        self._window_request(clip_service, parent, 0, 480)
                    )

            chord_root = root / "chord-library"
            chord_parent = MidiClip(
                title="Many chords",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
                chords=tuple(
                    ChordEvent(index / 128, 1, "C") for index in range(65)
                ),
                clip_id="chord-parent",
            )
            ClipLibrary(chord_root).add(chord_parent)
            with self._services(
                root,
                library_root=chord_root,
                parent_id=chord_parent.clip_id,
            ) as (clip_service, corrections, parent, _):
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "64 chord"):
                    corrections.window(
                        self._window_request(clip_service, parent, 0, 480)
                    )

            long_chord_root = root / "long-chord-library"
            long_chord = MidiClip(
                title="Long chord metadata",
                tempo_map=TempoMap.constant(120),
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(ClipNote.from_beats(0, 1, 60, 90, TempoMap.constant(120)),),
                chords=(ChordEvent(0, 3000, "C"),),
                clip_id="long-chord-parent",
            )
            ClipLibrary(long_chord_root).add(long_chord)
            with self._services(
                root,
                library_root=long_chord_root,
                parent_id=long_chord.clip_id,
            ) as (clip_service, corrections, parent, _):
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "20 minute"):
                    corrections.window(
                        self._window_request(clip_service, parent, 0, 480)
                    )

    def test_maximum_smf_tick_correction_round_trips_and_next_tick_is_rejected(self):
        maximum_tick = 0x0FFFFFFF
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bpm = maximum_tick * 60.0 / (480.0 * 1199.0)
            tempo = TempoMap.constant(bpm)
            parent = MidiClip(
                title="Maximum SMF tick",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(
                    ClipNote.from_beats(
                        (maximum_tick - 1) / 480,
                        1 / 480,
                        60,
                        90,
                        tempo,
                    ),
                ),
                clip_id="maximum-tick-parent",
            )
            library_root = root / "maximum-library"
            ClipLibrary(library_root).add(parent)
            with self._services(
                root,
                library_root=library_root,
                parent_id=parent.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(
                        clip_service, loaded, maximum_tick - 1, maximum_tick
                    )
                )
                request = self._preview_request(
                    window, [(window["notes"][0]["note_ref"], 61)]
                )
                preview = corrections.preview(request)
                result = corrections.create(self._create_request(preview, request))
                child = ClipLibrary(library_root, read_only=True).get(
                    result["child"]["clip_id"]
                )
                midi = root / "maximum-tick.mid"
                write_clip_midi(midi, child)
                imported = read_midi_clip(midi, role="keys")
                self.assertEqual(len(imported.notes), 1)
                self.assertEqual(imported.notes[0].pitch, 61)
                self.assertEqual(
                    round(imported.notes[0].end_beat * 480), maximum_tick
                )

            beyond_tempo = TempoMap.constant(30_000)
            cases = (
                (
                    "note",
                    MidiClip(
                        title="Note beyond SMF",
                        tempo_map=beyond_tempo,
                        time_signature=TimeSignature(),
                        instrument=Instrument("keys", 4, 0),
                        notes=(
                            ClipNote.from_beats(
                                maximum_tick / 480,
                                1 / 480,
                                60,
                                90,
                                beyond_tempo,
                            ),
                        ),
                        clip_id="note-beyond-parent",
                    ),
                ),
                (
                    "chord",
                    MidiClip(
                        title="Chord beyond SMF",
                        tempo_map=beyond_tempo,
                        time_signature=TimeSignature(),
                        instrument=Instrument("keys", 4, 0),
                        notes=(ClipNote.from_beats(0, 1, 60, 90, beyond_tempo),),
                        chords=(
                            ChordEvent((maximum_tick + 1) / 480, 1, "C"),
                        ),
                        clip_id="chord-beyond-parent",
                    ),
                ),
                (
                    "tempo",
                    MidiClip(
                        title="Tempo event beyond SMF",
                        tempo_map=TempoMap(
                            (
                                TempoPoint(0, 30_000),
                                TempoPoint((maximum_tick + 1) / 480, 30_000),
                            )
                        ),
                        time_signature=TimeSignature(),
                        instrument=Instrument("keys", 4, 0),
                        notes=(ClipNote.from_beats(0, 1, 60, 90, beyond_tempo),),
                        clip_id="tempo-beyond-parent",
                    ),
                ),
            )
            for label, invalid in cases:
                with self.subTest(label=label), self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "four-byte SMF VLQ"
                ):
                    _validate_parent_bounds(invalid)

    def test_parent_exportability_rejects_tempo_metadata_and_inventory_overflow(self):
        for bpm in (3.0, 120_000_000.0):
            with self.subTest(bpm=bpm):
                tempo = TempoMap.constant(bpm)
                clip = MidiClip(
                    title="Unencodable tempo",
                    tempo_map=tempo,
                    time_signature=TimeSignature(),
                    instrument=Instrument("keys", 4, 0),
                    notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "three-byte SMF tempo"
                ):
                    _validate_parent_bounds(clip)

        tempo = TempoMap.constant(120)
        for signature in (
            TimeSignature(256, 4),
            TimeSignature(4.5, 4),
            TimeSignature(4, 1 << 256),
        ):
            with self.subTest(signature=signature), self.assertRaisesRegex(
                WorkbenchClipCorrectionError, "time signature"
            ):
                _validate_parent_bounds(
                    MidiClip(
                        title="Unencodable signature",
                        tempo_map=tempo,
                        time_signature=signature,
                        instrument=Instrument("keys", 4, 0),
                        notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
                    )
                )

        with patch("sunofriend.workbench_correction._MAX_META_PAYLOAD_BYTES", 3):
            for label, clip in (
                (
                    "track title",
                    MidiClip(
                        title="Four",
                        tempo_map=tempo,
                        time_signature=TimeSignature(),
                        instrument=Instrument("keys", 4, 0),
                        notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
                    ),
                ),
                (
                    "chord symbol",
                    MidiClip(
                        title="One",
                        tempo_map=tempo,
                        time_signature=TimeSignature(),
                        instrument=Instrument("keys", 4, 0),
                        notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
                        chords=(ChordEvent(0, 1, "Cmaj"),),
                    ),
                ),
            ):
                with self.subTest(label=label), self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, label
                ):
                    _validate_parent_bounds(clip)

        two_chords = MidiClip(
            title="Chord inventory",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("keys", 4, 0),
            notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
            chords=(ChordEvent(0, 1, "C"), ChordEvent(1, 1, "G")),
        )
        with patch("sunofriend.workbench_correction._MAX_CHORDS", 1):
            with self.assertRaisesRegex(WorkbenchClipCorrectionError, "chord limit"):
                _validate_parent_bounds(two_chords)

    def test_patch_accepts_exactly_64_changes_and_rejects_65(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tempo = TempoMap.constant(240)
            parent = MidiClip(
                title="Sixty-five short notes",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=tuple(
                    ClipNote.from_beats(index / 128, 1 / 256, 60, 90, tempo)
                    for index in range(65)
                ),
                clip_id="change-count-parent",
            )
            library_root = root / "library"
            ClipLibrary(library_root).add(parent)
            with self._services(
                root,
                library_root=library_root,
                parent_id=parent.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 480)
                )
                changes = [(row["note_ref"], 61) for row in window["notes"]]
                preview = corrections.preview(
                    self._preview_request(window, changes[:64])
                )
                self.assertEqual(preview["diff"]["changed_note_count"], 64)
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, "1 to 64"):
                    corrections.preview(self._preview_request(window, changes))

    def test_chord_advisory_uses_stem_locked_export_onset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tempo = TempoMap.constant(120)
            parent = MidiClip(
                title="Divergent source and grid onset",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(ClipNote(0, 1, 54, 90, 2.5, 3.0),),
                chords=(
                    ChordEvent(0, 4, "Dm", 0.0, 2.0),
                    ChordEvent(4, 4, "Gm", 2.0, 4.0),
                ),
                provenance=Provenance(
                    details={"timing_mode": "stem_locked", "garageband_bpm": 120}
                ),
                clip_id="timeline-parent",
            )
            library_root = root / "library"
            ClipLibrary(library_root).add(parent)
            with self._services(
                root,
                library_root=library_root,
                parent_id=parent.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 2400, 2880)
                )
                self.assertEqual(window["chords"][0]["symbol"], "Gm")
                preview = corrections.preview(
                    self._preview_request(
                        window, [(window["notes"][0]["note_ref"], 55)]
                    )
                )
                change = preview["diff"]["changes"][0]
                self.assertEqual(change["chord_symbol"], "Gm")
                self.assertEqual(change["chord_relation_after"], "chord-tone")

    def test_restart_summary_reapplies_boundary_and_verifies_intent_digest(self):
        tempo = TempoMap.constant(60)
        for role, window, expected in (
            ("kick", {"start_tick": 0, "end_tick": 480}, "Drum-family"),
            ("keys", {"start_tick": 0, "end_tick": 32 * 480}, "15 export seconds"),
        ):
            with self.subTest(role=role):
                parent = MidiClip(
                    title="Forged correction parent",
                    tempo_map=tempo,
                    time_signature=TimeSignature(),
                    instrument=Instrument(role, 4, 0),
                    notes=(ClipNote.from_beats(0, 1, 60, 90, tempo),),
                    clip_id=f"{role}-forged-parent",
                )
                child = self._correction_child(parent, window=window, target_pitch=61)
                with self.assertRaisesRegex(WorkbenchClipCorrectionError, expected):
                    _derive_correction_summary(parent, child)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 480)
                )
                request = self._preview_request(
                    window, [(window["notes"][0]["note_ref"], 52)]
                )
                preview = corrections.preview(request)
                result = corrections.create(self._create_request(preview, request))
                child = ClipLibrary(library_root, read_only=True).get(
                    result["child"]["clip_id"]
                )
                parameters = child.transform_recipe.parameters_dict
                parameters["intent_sha256"] = "b" * 64
                forged = replace(
                    child,
                    clip_id=f"sf-correction-{'b' * 64}",
                    transform_recipe=TransformRecipe.create(
                        "correct_note_pitches", **parameters
                    ),
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "intent digest"
                ):
                    _derive_correction_summary(parent, forged)

                window_parameters = child.transform_recipe.parameters_dict
                window_parameters["window_sha256"] = "c" * 64
                window_parameters["intent_sha256"] = _document_hash(
                    _intent_document(
                        parent_clip_id=parent.clip_id,
                        parent_object_sha256=window_parameters[
                            "parent_object_sha256"
                        ],
                        library_state_sha256=window_parameters[
                            "library_state_sha256"
                        ],
                        window=window_parameters["window"],
                        window_sha256=window_parameters["window_sha256"],
                        correction=window_parameters["correction"],
                    )
                )
                forged_window = replace(
                    child,
                    clip_id=f"sf-correction-{window_parameters['intent_sha256']}",
                    transform_recipe=TransformRecipe.create(
                        "correct_note_pitches", **window_parameters
                    ),
                )
                self.assertEqual(
                    _derive_correction_summary(parent, forged_window)[
                        "child_clip_id"
                    ],
                    forged_window.clip_id,
                )
                forged_root = root / "forged-window-library"
                ClipLibrary(forged_root).add(parent)
                ClipLibrary(forged_root).add(forged_window)
                with self._services(
                    root / "forged-window-service",
                    library_root=forged_root,
                    parent_id=forged_window.clip_id,
                ) as (_clip_service, forged_service, _child, _library_root):
                    with self.assertRaisesRegex(
                        WorkbenchClipCorrectionError, "window evidence"
                    ):
                        forged_service.correction_summary(forged_window.clip_id)

    def test_summary_rejects_forged_child_and_ordinary_clip_returns_none(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, library_root):
                self.assertIsNone(corrections.correction_summary(parent.clip_id))
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                preview_request = self._preview_request(
                    window, [(window["notes"][0]["note_ref"], 52)]
                )
                preview = corrections.preview(preview_request)
                result = corrections.create(
                    self._create_request(preview, preview_request)
                )
                child = ClipLibrary(library_root, read_only=True).get(
                    result["child"]["clip_id"]
                )
                forged = replace(child, key=KeySignature("C", "major"))
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "exact retained edit diff"
                ):
                    _derive_correction_summary(parent, forged)
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "recognized"
                ):
                    _derive_correction_summary(parent, parent)

    @contextmanager
    def _services(
        self,
        root: Path,
        *,
        library_root: Path | None = None,
        parent_id: str = "parent-clip",
    ):
        root.mkdir(parents=True, exist_ok=True)
        if library_root is None:
            library_root = root / "library"
            ClipLibrary(library_root).add(self._parent())
        parent = ClipLibrary(library_root, read_only=True).get(parent_id)
        pack, result = self._acceptance(root, suffix=parent_id)
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
        duplicate_a = ClipNote.from_beats(0, 1, 50, 90, tempo)
        duplicate_b = ClipNote.from_beats(0, 1, 50, 90, tempo)
        return MidiClip(
            title="Private parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("bass", 38, 0, ("Fingered Bass",)),
            notes=(
                duplicate_a,
                duplicate_b,
                ClipNote.from_beats(2, 1, 53, 100, tempo),
                ClipNote.from_beats(4, 1, 55, 88, tempo),
            ),
            key=KeySignature("D", "minor"),
            chords=(
                ChordEvent(0, 4, "Dm", 0.0, 2.0),
                ChordEvent(4, 4, "Gm", 2.0, 4.0),
            ),
            provenance=Provenance(
                source_uri="/Users/alice/private-source.wav",
                source_stem="/Users/alice/private-source.wav",
                converter="test",
                details={"timing_mode": "stem_locked", "garageband_bpm": 120},
            ),
            clip_id="parent-clip",
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
                "kind": "pitch_patch",
                "changes": [
                    {"note_ref": note_ref, "target_pitch": target_pitch}
                    for note_ref, target_pitch in changes
                ],
            },
        }

    @staticmethod
    def _create_request(preview: dict, preview_request: dict) -> dict:
        return {
            "action": "create",
            **preview_request,
            "projection_sha256": preview["projection_sha256"],
        }

    @staticmethod
    def _correction_child(
        parent: MidiClip,
        *,
        window: dict[str, int],
        target_pitch: int,
    ) -> MidiClip:
        parent_hash = hashlib.sha256(parent.canonical_bytes()).hexdigest()
        note = parent.notes[0]
        note_ref = _note_ref(parent_hash, 0, note)
        correction = {
            "kind": "pitch_patch",
            "changes": [{"note_ref": note_ref, "target_pitch": target_pitch}],
        }
        library_state_sha256 = "a" * 64
        window_sha256 = "b" * 64
        intent_sha256 = _document_hash(
            _intent_document(
                parent_clip_id=parent.clip_id,
                parent_object_sha256=parent_hash,
                library_state_sha256=library_state_sha256,
                window=window,
                window_sha256=window_sha256,
                correction=correction,
            )
        )
        before = _note_payload(note)
        after = {**before, "pitch": target_pitch}
        return _child_from_recipe(
            parent,
            intent_sha256=intent_sha256,
            parent_object_sha256=parent_hash,
            library_state_sha256=library_state_sha256,
            window_sha256=window_sha256,
            window=window,
            correction=correction,
            recipe_changes=(
                {
                    "note_ref": note_ref,
                    "parent_note_index": 0,
                    "before": before,
                    "after": after,
                },
            ),
        )

    @staticmethod
    def _assert_path_free(root: Path, *documents: dict) -> None:
        encoded = json.dumps(documents, sort_keys=True)
        if str(root) in encoded or "private-source.wav" in encoded:
            raise AssertionError("public correction response contains a local path")

    @staticmethod
    def _assert_non_pitch_fields_equal(parent: MidiClip, child: MidiClip) -> None:
        for field in (
            "title",
            "tempo_map",
            "time_signature",
            "key",
            "chords",
            "instrument",
            "provenance",
            "engine_version",
            "tags",
            "schema_version",
        ):
            if getattr(parent, field) != getattr(child, field):
                raise AssertionError(field)
        parent_without_pitch = sorted(
            (replace(note, pitch=0) for note in parent.notes),
            key=repr,
        )
        child_without_pitch = sorted(
            (replace(note, pitch=0) for note in child.notes),
            key=repr,
        )
        if parent_without_pitch != child_without_pitch:
            raise AssertionError("non-pitch note fields")

    @staticmethod
    def _inventory(library_root: Path) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (row.clip_id, row.object_hash)
                for row in ClipLibrary(library_root, read_only=True).list(limit=10_000)
            )
        )

    @staticmethod
    def _acceptance(root: Path, *, suffix: str) -> tuple[Path, Path]:
        pack = root / f"accepted-{suffix}.zip"
        pack.write_bytes(f"exact pack {suffix}".encode())
        pack_hash = hashlib.sha256(pack.read_bytes()).hexdigest()
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
                        "name": "sunofriend-garageband-pack.zip",
                        "bytes": pack.stat().st_size,
                        "sha256": pack_hash,
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
