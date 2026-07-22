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
    TimeSignature,
    TransformRecipe,
)
from sunofriend.library import ClipLibrary
from sunofriend.workbench_clips import WorkbenchClipService
from sunofriend.workbench_correction import (
    CLIP_CORRECTION_CAPABILITY_SCHEMA,
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionService,
)
from sunofriend.workbench_velocity import (
    CLIP_ATTACK_VELOCITY_PREVIEW_SCHEMA,
    CLIP_ATTACK_VELOCITY_RESULT_SCHEMA,
    CLIP_ATTACK_VELOCITY_SUMMARY_SCHEMA,
    CLIP_ATTACK_VELOCITY_WINDOW_SCHEMA,
    _derive_correction_summary,
    _normalized_intervals,
    _parse_correction,
)


class WorkbenchVelocityCorrectionTests(unittest.TestCase):
    def test_capability_and_window_are_velocity_specific_and_allow_drums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _):
                capability = corrections.capability()
                self.assertEqual(
                    capability["schema"],
                    "sunofriend.workbench-clip-correction-capability.v2",
                )
                self.assertEqual(
                    capability["schema"], CLIP_CORRECTION_CAPABILITY_SCHEMA
                )
                self.assertEqual(
                    capability["corrections"]["pitch_patch"],
                    {"enabled": True, "drum_family": False},
                )
                self.assertEqual(
                    capability["corrections"]["attack_velocity_patch"],
                    {"enabled": True, "drum_family": True},
                )
                request = self._window_request(clip_service, parent, 0, 1440)
                window = corrections.window(request)
                self.assertEqual(window["schema"], CLIP_ATTACK_VELOCITY_WINDOW_SCHEMA)
                self.assertEqual(window["correction_kind"], "attack_velocity_patch")
                self.assertEqual(window["blocked_duplicate_note_on_count"], 2)
                duplicate_rows = [
                    row
                    for row in window["notes"]
                    if row["edit_block_reason"] == "duplicate-export-note-on"
                ]
                self.assertEqual(len(duplicate_rows), 2)
                self.assertTrue(all(not row["editable"] for row in duplicate_rows))
                self.assertTrue(
                    all(row["export_note_on_group_size"] == 2 for row in duplicate_rows)
                )
                self.assertTrue(
                    all(value is False for value in window["effects"].values())
                )
                self._assert_path_free(root, window)

            drum = self._parent(role="kick", channel=9, clip_id="drum-parent")
            drum_root = root / "drum-library"
            ClipLibrary(drum_root).add(drum)
            with self._services(
                root / "drums",
                library_root=drum_root,
                parent_id=drum.clip_id,
            ) as (clip_service, corrections, loaded, _):
                window = corrections.window(
                    self._window_request(clip_service, loaded, 0, 480)
                )
                self.assertTrue(window["notes"][0]["editable"])
                preview = corrections.preview(
                    self._preview_request(
                        window,
                        [(window["notes"][0]["note_ref"], 127)],
                    )
                )
                self.assertEqual(preview["diff"]["changes"][0]["after_velocity"], 127)

    def test_preview_create_replay_restart_and_normalized_midi_delta(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (
                clip_service,
                corrections,
                parent,
                library_root,
            ):
                parent_bytes = parent.canonical_bytes()
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                editable = [row for row in window["notes"] if row["editable"]]
                request = self._preview_request(
                    window,
                    [
                        (editable[0]["note_ref"], 1),
                        (editable[-1]["note_ref"], 127),
                    ],
                )
                preview = corrections.preview(request)
                self.assertEqual(preview["schema"], CLIP_ATTACK_VELOCITY_PREVIEW_SCHEMA)
                self.assertEqual(preview["diff"]["changed_note_count"], 2)
                self.assertEqual(
                    preview["diff"]["velocity_range_after"],
                    {"minimum": 1, "maximum": 127},
                )
                self.assertTrue(
                    all(value is False for value in preview["effects"].values())
                )
                result = corrections.create(self._create_request(preview, request))
                self.assertEqual(result["schema"], CLIP_ATTACK_VELOCITY_RESULT_SCHEMA)
                self.assertEqual(result["status"], "created")
                self.assertEqual(
                    {key for key, value in result["effects"].items() if value},
                    {
                        "library_mutated",
                        "child_clip_created",
                        "correction_applied",
                        "note_attack_velocity_changed",
                    },
                )
                library = ClipLibrary(library_root, read_only=True)
                self.assertEqual(
                    library.get(parent.clip_id).canonical_bytes(), parent_bytes
                )
                child = library.get(result["child"]["clip_id"])
                self.assertEqual(
                    child.transform_recipe.operation,
                    "correct_note_attack_velocities",
                )
                self._assert_only_expected_velocities_changed(
                    parent, child, {0: 1, 4: 127}
                )

                parent_events = _normalized_intervals(parent)
                child_events = _normalized_intervals(child)
                self.assertEqual(len(parent_events), len(child_events))
                changed = [
                    (before, after)
                    for before, after in zip(parent_events, child_events)
                    if before != after
                ]
                self.assertEqual(len(changed), 2)
                for before, after in changed:
                    self.assertEqual(
                        replace(before, velocity=after.velocity),
                        after,
                    )

                summary = corrections.correction_summary(child.clip_id)
                self.assertEqual(summary["schema"], CLIP_ATTACK_VELOCITY_SUMMARY_SCHEMA)
                self.assertEqual(summary["changed_note_count"], 2)
                self.assertTrue(
                    all(value is False for value in summary["effects"].values())
                )
                replay = corrections.create(self._create_request(preview, request))
                self.assertEqual(replay["status"], "replayed")
                self.assertTrue(
                    all(value is False for value in replay["effects"].values())
                )
                self.assertEqual(len(library.list(limit=10_000)), 2)

            with self._services(
                root / "restart",
                library_root=library_root,
                parent_id=child.clip_id,
            ) as (_clip_service, restarted, _child, _):
                restarted_summary = restarted.correction_summary(child.clip_id)
                self.assertEqual(restarted_summary["changes"], summary["changes"])
                self.assertEqual(
                    restarted_summary["child"]["object_sha256"],
                    result["child"]["object_sha256"],
                )

    def test_rejects_bad_values_noops_duplicates_context_and_ambiguous_note_ons(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, corrections, parent, _):
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                editable = next(row for row in window["notes"] if row["editable"])
                bad_targets = (0, 128, True, 64.0, "64", editable["velocity"])
                for target in bad_targets:
                    with (
                        self.subTest(target=target),
                        self.assertRaises(WorkbenchClipCorrectionError),
                    ):
                        corrections.preview(
                            self._preview_request(
                                window,
                                [(editable["note_ref"], target)],
                            )
                        )

                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "unique note refs"
                ):
                    corrections.preview(
                        self._preview_request(
                            window,
                            [
                                (editable["note_ref"], 1),
                                (editable["note_ref"], 127),
                            ],
                        )
                    )

                duplicate = next(
                    row
                    for row in window["notes"]
                    if row["edit_block_reason"] == "duplicate-export-note-on"
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "ambiguous duplicate exported Note On"
                ):
                    corrections.preview(
                        self._preview_request(window, [(duplicate["note_ref"], 100)])
                    )

                context = corrections.window(
                    self._window_request(clip_service, parent, 120, 240)
                )
                context_note = next(
                    row for row in context["notes"] if not row["editable"]
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "outside the editable window"
                ):
                    corrections.preview(
                        self._preview_request(
                            context, [(context_note["note_ref"], 100)]
                        )
                    )

                pitch_spelling = dict(
                    self._window_request(clip_service, parent, 0, 480)
                )
                pitch_spelling["correction_kind"] = "pitch_patch"
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "exact contract"
                ):
                    corrections.window(pitch_spelling)

                unknown = dict(self._window_request(clip_service, parent, 0, 480))
                unknown["correction_kind"] = "expression_patch"
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError, "exact contract"
                ):
                    corrections.window(unknown)

    def test_stale_projection_conflicts_and_forged_recipe_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (
                clip_service,
                corrections,
                parent,
                library_root,
            ):
                window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                editable = [row for row in window["notes"] if row["editable"]]
                first_request = self._preview_request(
                    window, [(editable[0]["note_ref"], 1)]
                )
                second_request = self._preview_request(
                    window, [(editable[-1]["note_ref"], 127)]
                )
                first = corrections.preview(first_request)
                second = corrections.preview(second_request)
                corrections.create(self._create_request(first, first_request))
                with self.assertRaises(WorkbenchClipCorrectionConflictError):
                    corrections.create(self._create_request(second, second_request))

                child = ClipLibrary(library_root, read_only=True).get(
                    first["child"]["clip_id"]
                )
                parameters = child.transform_recipe.parameters_dict
                parameters["changes"][0]["after"]["release_velocity"] = 99
                forged = replace(
                    child,
                    transform_recipe=TransformRecipe.create(
                        "correct_note_attack_velocities", **parameters
                    ),
                )
                with self.assertRaisesRegex(
                    WorkbenchClipCorrectionError,
                    "velocity only|exact retained edit diff",
                ):
                    _derive_correction_summary(parent, forged)

    def test_quantized_duplicate_is_blocked_but_different_onset_overlap_is_editable(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tempo = TempoMap.constant(120)
            parent = MidiClip(
                title="Quantized velocity identity",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("keys", 4, 0),
                notes=(
                    ClipNote.from_beats(0, 2, 60, 70, tempo),
                    ClipNote.from_beats(0.0001, 0.5, 62, 71, tempo),
                    ClipNote.from_beats(0.0002, 0.75, 62, 72, tempo),
                    ClipNote.from_beats(1, 1, 60, 73, tempo),
                ),
                clip_id="quantized-velocity-parent",
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
                quantized = [row for row in window["notes"] if row["pitch"] == 62]
                self.assertEqual(
                    [row["edit_block_reason"] for row in quantized],
                    ["duplicate-export-note-on", "duplicate-export-note-on"],
                )
                overlaps = [row for row in window["notes"] if row["pitch"] == 60]
                self.assertEqual(len(overlaps), 2)
                self.assertTrue(all(row["editable"] for row in overlaps))
                preview = corrections.preview(
                    self._preview_request(
                        window,
                        [(overlaps[-1]["note_ref"], 100)],
                    )
                )
                self.assertEqual(preview["diff"]["changed_note_count"], 1)
                self.assertEqual(preview["diff"]["changes"][0]["after_velocity"], 100)

    def test_patch_change_count_is_bounded_at_64(self):
        changes = [
            {
                "note_ref": hashlib.sha256(f"note-{index}".encode()).hexdigest(),
                "target_velocity": 1 + (index % 127),
            }
            for index in range(65)
        ]
        parsed = _parse_correction(
            {"kind": "attack_velocity_patch", "changes": changes[:64]}
        )
        self.assertEqual(len(parsed["changes"]), 64)
        with self.assertRaisesRegex(WorkbenchClipCorrectionError, "1 to 64"):
            _parse_correction({"kind": "attack_velocity_patch", "changes": changes})

    def test_pitch_and_velocity_children_share_the_same_library_cas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (
                clip_service,
                corrections,
                parent,
                library_root,
            ):
                velocity_window = corrections.window(
                    self._window_request(clip_service, parent, 0, 1440)
                )
                velocity_note = next(
                    row for row in velocity_window["notes"] if row["editable"]
                )
                velocity_request = self._preview_request(
                    velocity_window, [(velocity_note["note_ref"], 1)]
                )
                velocity_preview = corrections.preview(velocity_request)

                detail = clip_service.detail(parent.clip_id)
                pitch_window_request = {
                    "parent_clip_id": parent.clip_id,
                    "parent_object_sha256": detail["clip"]["object_sha256"],
                    "library_state_sha256": detail["library_state_sha256"],
                    "window": {"start_tick": 0, "end_tick": 1440},
                }
                pitch_window = corrections.window(pitch_window_request)
                pitch_note = next(
                    row for row in pitch_window["notes"] if row["pitch"] == 67
                )
                pitch_request = {
                    **pitch_window_request,
                    "window_sha256": pitch_window["window_sha256"],
                    "correction": {
                        "kind": "pitch_patch",
                        "changes": [
                            {
                                "note_ref": pitch_note["note_ref"],
                                "target_pitch": 68,
                            }
                        ],
                    },
                }
                pitch_preview = corrections.preview(pitch_request)
                corrections.create(
                    {
                        "action": "create",
                        **pitch_request,
                        "projection_sha256": pitch_preview["projection_sha256"],
                    }
                )
                with self.assertRaises(WorkbenchClipCorrectionConflictError):
                    corrections.create(
                        self._create_request(velocity_preview, velocity_request)
                    )
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list(limit=10_000)),
                    2,
                )

    @contextmanager
    def _services(
        self,
        root: Path,
        *,
        library_root: Path | None = None,
        parent_id: str = "velocity-parent",
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
    def _parent(
        *,
        role: str = "keys",
        channel: int = 0,
        clip_id: str = "velocity-parent",
    ) -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Private velocity parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument(role, 4, channel, ("Private patch",)),
            notes=(
                ClipNote.from_beats(0, 0.5, 60, 64, tempo, release_velocity=7),
                ClipNote.from_beats(1, 0.5, 62, 50, tempo, release_velocity=8),
                ClipNote.from_beats(1, 0.75, 62, 90, tempo, release_velocity=9),
                ClipNote.from_beats(2, 1.5, 60, 80, tempo, release_velocity=10),
                ClipNote.from_beats(2.5, 0.5, 67, 91, tempo, release_velocity=11),
            ),
            key=KeySignature("C", "major"),
            chords=(ChordEvent(0, 4, "C", 0.0, 2.0),),
            provenance=Provenance(
                source_uri="/Users/private/velocity.wav",
                source_stem="/Users/private/velocity.wav",
                converter="test",
                details={"timing_mode": "musical"},
            ),
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
            "correction_kind": "attack_velocity_patch",
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
                "kind": "attack_velocity_patch",
                "changes": [
                    {"note_ref": note_ref, "target_velocity": target}
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
    def _assert_only_expected_velocities_changed(
        parent: MidiClip,
        child: MidiClip,
        expected: dict[int, int],
    ) -> None:
        for index, (before, after) in enumerate(zip(parent.notes, child.notes)):
            expected_velocity = expected.get(index, before.velocity)
            if after != replace(before, velocity=expected_velocity):
                raise AssertionError(f"unexpected note change at {index}")
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

    @staticmethod
    def _assert_path_free(root: Path, value: object) -> None:
        encoded = json.dumps(value, sort_keys=True)
        if str(root) in encoded or "/Users/private" in encoded:
            raise AssertionError("public velocity response contains a local path")

    @staticmethod
    def _acceptance(root: Path, suffix: str) -> tuple[Path, Path]:
        pack = root / f"accepted-{suffix}.zip"
        pack.write_bytes(f"accepted {suffix}".encode())
        pack_hash = hashlib.sha256(pack.read_bytes()).hexdigest()
        result = root / f"acceptance-{suffix}.json"
        result.write_text(
            json.dumps(
                {
                    "schema": (
                        "sunofriend.workbench-garageband-pack-acceptance-result.v1"
                    ),
                    "operation": "garageband-pack-acceptance-resolve",
                    "status": "passed",
                    "phase6_read_only_clip_entry_ready": True,
                    "explicit_hybrid_construction_ready": False,
                    "pack": {
                        "name": "accepted.zip",
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
