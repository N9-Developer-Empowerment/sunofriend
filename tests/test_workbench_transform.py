from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import (
    ClipNote,
    Instrument,
    KeySignature,
    MidiClip,
    Provenance,
    TempoMap,
    TimeSignature,
)
from sunofriend.library import ClipLibrary
from sunofriend.workbench_clips import WorkbenchClipService
from sunofriend.workbench_transform import (
    WorkbenchClipTransformConflictError,
    WorkbenchClipTransformError,
    WorkbenchClipTransformNotFoundError,
    WorkbenchClipTransformService,
)


class WorkbenchClipTransformTests(unittest.TestCase):
    def test_capability_and_key_preview_are_deterministic_path_free_and_zero_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, transforms, parent, library_root):
                before = self._inventory(library_root)
                request = self._request(clip_service, parent, key="E minor")
                first = transforms.preview(request)
                second = transforms.preview(request)
                capability = transforms.capability()

                self.assertEqual(first, second)
                self.assertEqual(first["transform"], {
                    "kind": "key",
                    "target_key": "E minor",
                    "direction": "nearest",
                })
                self.assertEqual(first["parent"]["key"], "D minor")
                self.assertEqual(first["child"]["key"], "E minor")
                self.assertEqual(first["child"]["parent_clip_id"], parent.clip_id)
                self.assertEqual(first["parent"]["pitch_range"], {"minimum": 50, "maximum": 53})
                self.assertEqual(first["child"]["pitch_range"], {"minimum": 52, "maximum": 55})
                self.assertEqual(first["parent"]["chord_count"], 0)
                self.assertEqual(first["child"]["chord_count"], 0)
                self.assertEqual(first["diff"]["semitones"], 2)
                self.assertEqual(first["diff"]["note_pitches_changed"], 2)
                self.assertTrue(all(value is False for value in first["effects"].values()))
                self.assertTrue(capability["actions"]["preview"])
                self.assertTrue(capability["actions"]["create"])
                self.assertFalse(capability["transforms"]["same_mode_key"]["cross_mode"])
                self.assertNotIn(str(root), json.dumps(first))
                self.assertEqual(self._inventory(library_root), before)

    def test_exact_create_appends_one_child_adopts_state_and_replays_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, transforms, parent, library_root):
                parent_bytes = parent.canonical_bytes()
                preview = transforms.preview(
                    self._request(clip_service, parent, key="E minor", direction="up")
                )
                create_request = self._create_request(preview)
                result = transforms.create(create_request)

                self.assertEqual(result["status"], "created")
                self.assertFalse(result["replayed"])
                self.assertTrue(result["effects"]["library_mutated"])
                self.assertTrue(result["effects"]["child_clip_created"])
                self.assertTrue(result["effects"]["transform_applied"])
                self.assertFalse(result["effects"]["source_clip_mutated"])
                self.assertEqual(ClipLibrary(library_root, read_only=True).get(parent.clip_id).canonical_bytes(), parent_bytes)
                child = ClipLibrary(library_root, read_only=True).get(result["child"]["clip_id"])
                self.assertEqual(child.parent_clip_id, parent.clip_id)
                self.assertEqual(child.key, KeySignature("E", "minor"))
                self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 2)

                # The read-only browser adopts only this proven append and is
                # immediately usable without a restart.
                self.assertEqual(clip_service.detail(child.clip_id)["clip"]["key"], "E minor")
                replay = transforms.create(create_request)
                self.assertEqual(replay["status"], "replayed")
                self.assertTrue(replay["replayed"])
                self.assertTrue(all(value is False for value in replay["effects"].values()))
                self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 2)

    def test_stale_second_projection_conflicts_and_does_not_create_a_second_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, transforms, parent, library_root):
                first = transforms.preview(self._request(clip_service, parent, key="E minor"))
                second = transforms.preview(
                    self._request(clip_service, parent, bpm=100, timing_mode="musical")
                )
                transforms.create(self._create_request(first))
                before = self._inventory(library_root)

                with self.assertRaises(WorkbenchClipTransformConflictError):
                    transforms.create(self._create_request(second))
                self.assertEqual(self._inventory(library_root), before)
                self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 2)

    def test_bpm_previews_make_musical_and_stem_locked_semantics_explicit(self):
        for timing_mode, beats_changed, seconds_changed in (
            ("musical", False, True),
            ("stem_locked", True, False),
        ):
            with self.subTest(timing_mode=timing_mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self._services(root) as (clip_service, transforms, parent, _library_root):
                    preview = transforms.preview(
                        self._request(
                            clip_service,
                            parent,
                            bpm=100,
                            timing_mode=timing_mode,
                        )
                    )
                    self.assertEqual(preview["diff"]["bpm_before"], 120)
                    self.assertEqual(preview["diff"]["bpm_after"], 100)
                    self.assertIs(preview["diff"]["beat_positions_changed"], beats_changed)
                    self.assertIs(preview["diff"]["source_seconds_changed"], seconds_changed)
                    self.assertFalse(preview["diff"]["pitch_changed"])
                    self.assertIn("reuse placements", " ".join(preview["warnings"]))

    def test_rejects_cross_mode_drum_unkeyed_noop_ranges_and_wrong_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, transforms, parent, library_root):
                for target in ("E major", "D minor"):
                    with self.subTest(target=target), self.assertRaises(WorkbenchClipTransformError):
                        transforms.preview(self._request(clip_service, parent, key=target))
                for bpm in (120, 19, 401, 29, "100", True, float("nan")):
                    with self.subTest(bpm=bpm), self.assertRaises(WorkbenchClipTransformError):
                        transforms.preview(self._request(clip_service, parent, bpm=bpm))

                bad_hash = self._request(clip_service, parent, key="E minor")
                bad_hash["parent_object_sha256"] = "f" * 64
                with self.assertRaises(WorkbenchClipTransformConflictError):
                    transforms.preview(bad_hash)
                missing = dict(self._request(clip_service, parent, key="E minor"))
                missing["parent_clip_id"] = "missing"
                with self.assertRaises(WorkbenchClipTransformNotFoundError):
                    transforms.preview(missing)

                writable = ClipLibrary(library_root)
                drum = replace(
                    parent,
                    clip_id="kick-family",
                    parent_clip_id=None,
                    revision=1,
                    instrument=Instrument("kick", 0, 0),
                )
                unkeyed = replace(
                    parent,
                    clip_id="unkeyed",
                    parent_clip_id=None,
                    revision=1,
                    key=None,
                )
                writable.add(drum)
                writable.add(unkeyed)
                # Deliberate external writes invalidate the existing read-only
                # service; reopening is required before either Clip is usable.
            with self._services(
                root,
                library_root=library_root,
                parent_id="kick-family",
            ) as (clip_service, transforms, drum, _):
                with self.assertRaisesRegex(WorkbenchClipTransformError, "Drum-family"):
                    transforms.preview(self._request(clip_service, drum, key="E minor"))
                unkeyed = ClipLibrary(library_root, read_only=True).get("unkeyed")
                with self.assertRaisesRegex(WorkbenchClipTransformError, "keyed parent"):
                    transforms.preview(self._request(clip_service, unkeyed, key="E minor"))

    def test_exact_request_and_projection_contract_fail_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self._services(root) as (clip_service, transforms, parent, library_root):
                request = self._request(clip_service, parent, key="E minor")
                preview = transforms.preview(request)
                before = self._inventory(library_root)

                with self.assertRaisesRegex(WorkbenchClipTransformError, "exact contract"):
                    transforms.preview({**request, "extra": True})
                wrong_projection = self._create_request(preview)
                wrong_projection["projection_sha256"] = "0" * 64
                with self.assertRaises(WorkbenchClipTransformConflictError):
                    transforms.create(wrong_projection)
                wrong_action = self._create_request(preview)
                wrong_action["action"] = "confirm"
                with self.assertRaisesRegex(WorkbenchClipTransformError, "action"):
                    transforms.create(wrong_action)
                self.assertEqual(self._inventory(library_root), before)

    def test_existing_writer_stale_cas_leaves_catalog_and_objects_byte_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root = root / "library"
            parent = self._parent()
            library = ClipLibrary(library_root)
            summary = library.add(parent)
            writer = ClipLibrary.open_existing_writer(library_root)
            before_files = self._file_inventory(library_root)
            with self._services(root, library_root=library_root) as (
                clip_service,
                transforms,
                _parent,
                _library_root,
            ):
                projection = transforms.preview(
                    self._request(clip_service, parent, key="E minor")
                )
            child = replace(
                parent,
                clip_id=projection["child"]["clip_id"],
                parent_clip_id=parent.clip_id,
                revision=2,
            )
            with self.assertRaisesRegex(RuntimeError, "catalog state conflict"):
                writer.append_version_if_state(
                    parent.clip_id,
                    child,
                    expected_state_sha256="0" * 64,
                    expected_parent_object_hash=summary.object_hash,
                )
            self.assertEqual(self._file_inventory(library_root), before_files)

    def test_existing_writer_rejects_symlink_object_shard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root = root / "library"
            parent = self._parent()
            library = ClipLibrary(library_root)
            summary = library.add(parent)
            writer = ClipLibrary.open_existing_writer(library_root)
            child = replace(
                parent,
                clip_id="child-with-new-object",
                parent_clip_id=parent.clip_id,
                revision=2,
            )
            child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
            shard = library_root / "objects" / child_hash[:2]
            attempt = 0
            while shard.exists():
                attempt += 1
                child = replace(child, clip_id=f"child-with-new-object-{attempt}")
                child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
                shard = library_root / "objects" / child_hash[:2]
            outside = root / "outside"
            outside.mkdir()
            shard.symlink_to(outside, target_is_directory=True)
            before_outside = tuple(outside.iterdir())
            with self.assertRaisesRegex(RuntimeError, "shard"):
                writer.append_version_if_state(
                    parent.clip_id,
                    child,
                    expected_state_sha256=writer.catalog_state_sha256(),
                    expected_parent_object_hash=summary.object_hash,
                )
            self.assertEqual(tuple(outside.iterdir()), before_outside)
            self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 1)

    def test_existing_writer_rolls_back_catalog_trigger_side_effect_and_child_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root = root / "library"
            parent = self._parent()
            library = ClipLibrary(library_root)
            summary = library.add(parent)
            writer = ClipLibrary.open_existing_writer(library_root)
            child = replace(
                parent,
                clip_id="triggered-child",
                parent_clip_id=parent.clip_id,
                revision=2,
                key=KeySignature("E", "minor"),
            )
            child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
            before_objects = self._object_inventory(library_root)
            with sqlite3.connect(library_root / "catalog.sqlite3") as connection:
                connection.execute(
                    """
                    CREATE TRIGGER mutate_parent_after_child_insert
                    AFTER INSERT ON clips
                    WHEN NEW.parent_clip_id IS NOT NULL
                    BEGIN
                        UPDATE clips
                        SET title = 'MUTATED BY TRIGGER'
                        WHERE clip_id = NEW.parent_clip_id;
                    END
                    """
                )

            with self.assertRaisesRegex(
                RuntimeError, "Existing Clip metadata changed during transform append"
            ):
                writer.append_version_if_state(
                    parent.clip_id,
                    child,
                    expected_state_sha256=writer.catalog_state_sha256(),
                    expected_parent_object_hash=summary.object_hash,
                )

            rows = ClipLibrary(library_root, read_only=True).list(limit=10_000)
            self.assertEqual([(row.clip_id, row.title) for row in rows], [
                (parent.clip_id, parent.title)
            ])
            self.assertFalse(ClipLibrary(library_root).object_path(child_hash).exists())
            self.assertEqual(self._object_inventory(library_root), before_objects)

    def test_existing_writer_enforces_maximum_count_inside_transaction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root = root / "library"
            parent = self._parent()
            library = ClipLibrary(library_root)
            summary = library.add(parent)
            writer = ClipLibrary.open_existing_writer(library_root)
            child = replace(
                parent,
                clip_id="over-capacity-child",
                parent_clip_id=parent.clip_id,
                revision=2,
            )
            child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()

            with patch("sunofriend.library.MAXIMUM_CLIP_COUNT", 1), self.assertRaisesRegex(
                RuntimeError, "maximum clip count reached"
            ):
                writer.append_version_if_state(
                    parent.clip_id,
                    child,
                    expected_state_sha256=writer.catalog_state_sha256(),
                    expected_parent_object_hash=summary.object_hash,
                )

            self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 1)
            self.assertFalse(ClipLibrary(library_root).object_path(child_hash).exists())

    def test_orphan_cleanup_holds_writer_lock_until_unlink_before_concurrent_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root = root / "library"
            parent = self._parent()
            library = ClipLibrary(library_root)
            summary = library.add(parent)
            cleanup_writer = ClipLibrary.open_existing_writer(library_root)
            append_writer = ClipLibrary.open_existing_writer(library_root)
            child = replace(
                parent,
                clip_id="concurrent-cleanup-child",
                parent_clip_id=parent.clip_id,
                revision=2,
            )
            payload = child.canonical_bytes()
            object_hash = hashlib.sha256(payload).hexdigest()
            object_path = library.object_path(object_hash)
            object_path.parent.mkdir(exist_ok=True)
            object_path.write_bytes(payload)
            expected_state = append_writer.catalog_state_sha256()

            unlink_entered = threading.Event()
            release_unlink = threading.Event()
            append_begin_attempted = threading.Event()
            append_done = threading.Event()
            errors: list[BaseException] = []
            receipts = []
            original_unlink = Path.unlink
            original_connect = append_writer._connect

            class BeginSignalConnection:
                def __init__(self, connection):
                    self._connection = connection

                def execute(self, statement, *args):
                    if statement.strip().upper() == "BEGIN IMMEDIATE":
                        append_begin_attempted.set()
                    return self._connection.execute(statement, *args)

                def __getattr__(self, name):
                    return getattr(self._connection, name)

            def blocking_unlink(path: Path, *args, **kwargs):
                if path == object_path:
                    unlink_entered.set()
                    if not release_unlink.wait(timeout=5):
                        raise RuntimeError("Timed out waiting to release orphan unlink")
                return original_unlink(path, *args, **kwargs)

            def cleanup() -> None:
                try:
                    cleanup_writer._remove_unreferenced_object(object_hash)
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            def append() -> None:
                try:
                    receipts.append(
                        append_writer.append_version_if_state(
                            parent.clip_id,
                            child,
                            expected_state_sha256=expected_state,
                            expected_parent_object_hash=summary.object_hash,
                        )
                    )
                except BaseException as exc:  # pragma: no cover - asserted below
                    errors.append(exc)
                finally:
                    append_done.set()

            def connected_with_begin_signal():
                return BeginSignalConnection(original_connect())

            with (
                patch.object(Path, "unlink", blocking_unlink),
                patch.object(
                    append_writer,
                    "_connect",
                    side_effect=connected_with_begin_signal,
                ),
            ):
                cleanup_thread = threading.Thread(target=cleanup)
                append_thread = threading.Thread(target=append)
                cleanup_thread.start()
                self.assertTrue(unlink_entered.wait(timeout=5))
                append_thread.start()
                self.assertTrue(append_begin_attempted.wait(timeout=5))
                completed_while_cleanup_held = append_done.wait(timeout=0.25)
                release_unlink.set()
                cleanup_thread.join(timeout=5)
                append_thread.join(timeout=5)

            self.assertFalse(cleanup_thread.is_alive())
            self.assertFalse(append_thread.is_alive())
            self.assertFalse(completed_while_cleanup_held)
            self.assertEqual(errors, [])
            self.assertEqual(len(receipts), 1)
            self.assertFalse(receipts[0].replayed)
            self.assertEqual(object_path.read_bytes(), payload)
            self.assertEqual(
                ClipLibrary(library_root, read_only=True).get(child.clip_id),
                child,
            )

    def test_preview_is_unavailable_at_the_accepted_inventory_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("sunofriend.workbench_clips._MAX_LIBRARY_CLIPS", 1):
                with self._services(root) as (
                    clip_service,
                    transforms,
                    parent,
                    library_root,
                ):
                    before = self._inventory(library_root)
                    capability = transforms.capability()
                    self.assertFalse(capability["actions"]["preview"])
                    self.assertFalse(capability["actions"]["create"])
                    with self.assertRaisesRegex(
                        WorkbenchClipTransformError, "10000 Clip transform limit"
                    ):
                        transforms.preview(
                            self._request(clip_service, parent, key="E minor")
                        )
                    self.assertEqual(self._inventory(library_root), before)

    def test_existing_writer_never_initializes_missing_or_unrelated_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "missing"
            with self.assertRaises(FileNotFoundError):
                ClipLibrary.open_existing_writer(missing)
            self.assertFalse(missing.exists())

            unrelated = root / "unrelated"
            (unrelated / "objects").mkdir(parents=True)
            database = unrelated / "catalog.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
            with self.assertRaisesRegex(RuntimeError, "schema is missing"):
                ClipLibrary.open_existing_writer(unrelated)
            with sqlite3.connect(database) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertEqual(tables, {"unrelated"})

    @contextmanager
    def _services(
        self,
        root: Path,
        *,
        library_root: Path | None = None,
        parent_id: str = "parent-clip",
    ):
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
            transforms = WorkbenchClipTransformService.open(
                clip_service=clip_service,
                library_root=library_root,
            )
            yield clip_service, transforms, parent, library_root

    @staticmethod
    def _parent() -> MidiClip:
        tempo = TempoMap.constant(120)
        return MidiClip(
            title="Private parent",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("bass", 38, 0),
            notes=(
                ClipNote.from_beats(0, 1, 50, 90, tempo),
                ClipNote.from_beats(2, 1, 53, 100, tempo),
            ),
            key=KeySignature("D", "minor"),
            provenance=Provenance(
                source_uri="/Users/alice/private.wav",
                details={"timing_mode": "stem_locked", "garageband_bpm": 120},
            ),
            clip_id="parent-clip",
        )

    @staticmethod
    def _request(
        service: WorkbenchClipService,
        parent: MidiClip,
        *,
        key: str | None = None,
        direction: str = "nearest",
        bpm: float | None = None,
        timing_mode: str = "musical",
    ) -> dict:
        detail = service.detail(parent.clip_id)
        if key is not None:
            transform = {"kind": "key", "target_key": key, "direction": direction}
        else:
            transform = {
                "kind": "bpm",
                "target_bpm": bpm,
                "timing_mode": timing_mode,
            }
        return {
            "parent_clip_id": parent.clip_id,
            "parent_object_sha256": detail["clip"]["object_sha256"],
            "library_state_sha256": detail["library_state_sha256"],
            "transform": transform,
        }

    @staticmethod
    def _create_request(preview: dict) -> dict:
        return {
            "action": "create",
            "parent_clip_id": preview["parent"]["clip_id"],
            "parent_object_sha256": preview["parent"]["object_sha256"],
            "library_state_sha256": preview["library"]["state_sha256"],
            "projection_sha256": preview["projection_sha256"],
            "transform": dict(preview["transform"]),
        }

    @staticmethod
    def _inventory(library_root: Path) -> tuple[tuple[str, str], ...]:
        library = ClipLibrary(library_root, read_only=True)
        return tuple(
            sorted((row.clip_id, row.object_hash) for row in library.list(limit=10_000))
        )

    @staticmethod
    def _file_inventory(library_root: Path) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (
                    str(path.relative_to(library_root)),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in library_root.rglob("*")
                if path.is_file()
            )
        )

    @staticmethod
    def _object_inventory(library_root: Path) -> tuple[tuple[str, str], ...]:
        objects = library_root / "objects"
        return tuple(
            sorted(
                (
                    str(path.relative_to(objects)),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in objects.rglob("*")
                if path.is_file()
            )
        )

    @staticmethod
    def _acceptance(root: Path, *, suffix: str) -> tuple[Path, Path]:
        pack = root / f"accepted-{suffix}.zip"
        pack.write_bytes(f"exact pack {suffix}".encode())
        pack_hash = hashlib.sha256(pack.read_bytes()).hexdigest()
        result = root / f"acceptance-{suffix}.json"
        result.write_text(json.dumps({
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
        }, sort_keys=True))
        return pack, result


if __name__ == "__main__":
    unittest.main()
