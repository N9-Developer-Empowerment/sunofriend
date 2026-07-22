from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
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
    TransformRecipe,
)
from sunofriend.library import ClipLibrary
from sunofriend.workbench_clips import WorkbenchClipService, public_artifact


class WorkbenchClipServiceTests(unittest.TestCase):
    def test_gate_precedes_read_only_open_and_public_capability_is_path_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, _clip = self._library(root)
            pack, result = self._acceptance(root)
            cache = root / "cache"
            with patch(
                "sunofriend.workbench_clips.verify_garageband_pack_archive",
                return_value={"status": "verified"},
            ) as verify:
                service = WorkbenchClipService.open(
                    acceptance_result_path=result,
                    garageband_pack_path=pack,
                    library_root=library_root,
                    cache_root=cache,
                )
                capability = service.capability()

            self.assertGreaterEqual(verify.call_count, 2)
            self.assertTrue(capability["enabled"])
            self.assertTrue(capability["read_only"])
            self.assertEqual(capability["library"]["clip_count"], 2)
            self.assertEqual(capability["library"]["lineage_count"], 1)
            self.assertTrue(all(value is False for value in capability["effects"].values()))
            self.assertNotIn(str(root), json.dumps(capability))

    def test_browse_filters_pages_and_sanitizes_private_catalog_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            with self._service(root, library_root, pack, result) as service:
                page = service.browse(role="custom role", key="D minor", limit=1)
                tagged = service.browse(tags=["golden"], bpm=120, bpm_tolerance=0)
                text = service.browse(text="untitled")

                self.assertEqual(page["page"]["total"], 2)
                self.assertEqual(page["page"]["returned"], 1)
                self.assertTrue(page["page"]["has_more"])
                self.assertEqual(tagged["page"]["total"], 2)
                self.assertEqual(text["page"]["total"], 2)
                row = page["clips"][0]
                self.assertEqual(row["title"], "Untitled clip")
                self.assertTrue(row["title_redacted"])
                self.assertEqual(row["role"], "custom role")
                self.assertTrue(row["role_redacted"])
                self.assertIn("private tag", row["tags"])
                self.assertEqual(row["duration_seconds"], 1.25)
                self.assertNotIn(str(root), json.dumps(page))
                self.assertNotIn(clip.provenance.source_uri, json.dumps(page))
                with self.assertRaisesRegex(ValueError, "path-free"):
                    service.browse(text="/Users/alice/song.mid")
                with self.assertRaisesRegex(ValueError, "limit"):
                    service.browse(limit=101)

    def test_detail_has_musical_contract_and_sanitized_version_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            with self._service(root, library_root, pack, result) as service:
                detail = service.detail(clip.clip_id)

            musical = detail["clip"]
            self.assertEqual(musical["note_count"], 2)
            self.assertEqual(musical["chord_count"], 0)
            self.assertEqual(musical["pitch_range"], {"minimum": 38, "maximum": 42})
            self.assertEqual(musical["velocity_range"], {"minimum": 70, "maximum": 100})
            self.assertEqual(musical["timing_contract"]["requested_mode"], "auto")
            self.assertEqual(musical["timing_contract"]["resolved_mode"], "stem_locked")
            self.assertEqual(musical["timing_contract"]["export_bpm"], 120)
            self.assertEqual(musical["instrument"]["suggestions"], ["private suggestion"])
            self.assertEqual(detail["lineage"]["version_count"], 2)
            self.assertEqual(len(detail["lineage"]["versions"]), 2)
            self.assertTrue(
                all(
                    version["transform_parameters_exposed"] is False
                    for version in detail["lineage"]["versions"]
                )
            )
            serialised = json.dumps(detail)
            self.assertNotIn("/Users/alice", serialised)
            self.assertNotIn("secret-parameter", serialised)
            self.assertNotIn("source_uri\"", serialised)
            self.assertTrue(all(value is False for value in detail["effects"].values()))

    def test_deterministic_artifact_and_preview_use_exact_exported_midi(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            soundfont = root / "private-soundfont.sf2"
            soundfont.write_bytes(b"SF2" * 400)
            fluidsynth = root / "fluidsynth"
            fluidsynth.write_bytes(b"executable")
            fluidsynth.chmod(0o755)
            rendered_midi: list[bytes] = []

            def fake_render(midi_path, wav_path, **kwargs):
                rendered_midi.append(Path(midi_path).read_bytes())
                self.assertTrue(
                    Path(kwargs["soundfont_path"]).resolve().is_relative_to(cache.resolve())
                )
                Path(wav_path).write_bytes(b"RIFF" + b"\0" * 2048)
                return Path(wav_path)

            cache = root / "cache"
            with (
                patch(
                    "sunofriend.workbench_clips.verify_garageband_pack_archive",
                    return_value={"status": "verified"},
                ),
                patch(
                    "sunofriend.workbench_clips.render_midi_to_wav",
                    side_effect=fake_render,
                ) as render,
            ):
                service = WorkbenchClipService.open(
                    acceptance_result_path=result,
                    garageband_pack_path=pack,
                    library_root=library_root,
                    cache_root=cache,
                    soundfont_path=soundfont,
                    fluidsynth_path=fluidsynth,
                )
                first = service.prepare_artifact(clip.clip_id, include_preview=True)
                second = service.prepare_artifact(clip.clip_id, include_preview=True)

            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["artifact_id"], second["artifact_id"])
            self.assertEqual(first["midi"]["sha256"], second["midi"]["sha256"])
            self.assertEqual(render.call_count, 1)
            self.assertEqual(
                hashlib.sha256(rendered_midi[0]).hexdigest(),
                first["midi"]["sha256"],
            )
            self.assertTrue(
                Path(first["midi"]["path"]).resolve().is_relative_to(cache.resolve())
            )
            self.assertTrue(
                Path(first["preview"]["path"]).resolve().is_relative_to(cache.resolve())
            )
            public = public_artifact(first)
            self.assertFalse(self._has_key(public, "path"))
            self.assertEqual(public["midi"]["sha256"], first["midi"]["sha256"])
            self.assertEqual(public["preview"]["sha256"], first["preview"]["sha256"])
            self.assertIn("exact exported MIDI", public["interpretation"])
            self.assertTrue(all(value is False for value in public["effects"].values()))

    def test_artifact_cache_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            with self._service(root, library_root, pack, result) as service:
                artifact = service.prepare_artifact(clip.clip_id)
                Path(artifact["midi"]["path"]).write_bytes(b"tampered")
                with self.assertRaisesRegex(RuntimeError, "changed after caching"):
                    service.prepare_artifact(clip.clip_id)

    def test_acceptance_pack_and_library_drift_all_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            with self._service(root, library_root, pack, result) as service:
                result.write_text(result.read_text().replace('"status": "passed"', '"status": "incomplete"'))
                with self.assertRaisesRegex(RuntimeError, "Immutable Phase 6 evidence"):
                    service.capability()

            pack, result = self._acceptance(root, suffix="-pack-drift")
            with self._service(root, library_root, pack, result) as service:
                pack.write_bytes(b"changed exact pack")
                with self.assertRaisesRegex(RuntimeError, "Immutable Phase 6 evidence"):
                    service.browse()

            pack, result = self._acceptance(root, suffix="-library-drift")
            with self._service(root, library_root, pack, result) as service:
                library = ClipLibrary(library_root)
                extra = replace(
                    clip,
                    clip_id="extra-clip",
                    title="Extra",
                    parent_clip_id=None,
                    revision=1,
                )
                library.add(extra)
                with self.assertRaisesRegex(RuntimeError, "library changed"):
                    service.detail(clip.clip_id)

    def test_clip_object_and_acceptance_pack_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            with self._service(root, library_root, pack, result) as service:
                writable = ClipLibrary(library_root)
                summary = next(row for row in writable.list() if row.clip_id == clip.clip_id)
                writable.object_path(summary.object_hash).write_bytes(b"corrupt")
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    service.detail(clip.clip_id)

            other_pack = root / "other.zip"
            other_pack.write_bytes(b"not the accepted bytes")
            cache = root / "mismatch-cache"
            with patch(
                "sunofriend.workbench_clips.verify_garageband_pack_archive",
                return_value={"status": "verified"},
            ) as verify:
                with self.assertRaisesRegex(ValueError, "does not match"):
                    WorkbenchClipService.open(
                        acceptance_result_path=result,
                        garageband_pack_path=other_pack,
                        library_root=library_root,
                        cache_root=cache,
                    )
            verify.assert_not_called()
            self.assertFalse(cache.exists())

    def test_structural_gate_and_duration_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, clip = self._library(root)
            pack, result = self._acceptance(root)
            original = json.loads(result.read_text())
            invalid_documents = []
            for mutate in (
                lambda row: row.update(status="needs_changes"),
                lambda row: row["quiz"].update(score=9),
                lambda row: row["acceptance_checks"][0].update(issue_count=1),
                lambda row: row.update(remaining_local_studio_acceptance_gates=["open"]),
                lambda row: row["effects"].update(midi_mutated=True),
                lambda row: row.update(explicit_hybrid_construction_ready=True),
            ):
                candidate = json.loads(json.dumps(original))
                mutate(candidate)
                invalid_documents.append(candidate)
            for index, document in enumerate(invalid_documents):
                invalid = root / f"invalid-{index}.json"
                invalid.write_text(json.dumps(document))
                with (
                    patch(
                        "sunofriend.workbench_clips.verify_garageband_pack_archive",
                        return_value={"status": "verified"},
                    ),
                    self.assertRaises(ValueError),
                ):
                    WorkbenchClipService.open(
                        acceptance_result_path=invalid,
                        garageband_pack_path=pack,
                        library_root=library_root,
                        cache_root=root / f"invalid-cache-{index}",
                    )

            long_root = root / "long-library"
            tempo = TempoMap.constant(120)
            long_clip = MidiClip(
                title="Long",
                tempo_map=tempo,
                time_signature=TimeSignature(),
                instrument=Instrument("lead", 80, 0),
                notes=(ClipNote.from_beats(0, 2500, 60, 100, tempo),),
                key=KeySignature("C", "major"),
                clip_id="long-clip",
            )
            ClipLibrary(long_root).add(long_clip)
            with self._service(root, long_root, pack, result, cache_name="long-cache") as service:
                with self.assertRaisesRegex(ValueError, "20 minute"):
                    service.prepare_artifact(long_clip.clip_id)

    def test_symlink_pack_and_archive_verifier_failure_are_rejected_before_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root, _clip = self._library(root)
            pack, result = self._acceptance(root)
            linked = root / "linked-pack.zip"
            linked.symlink_to(pack)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                WorkbenchClipService.open(
                    acceptance_result_path=result,
                    garageband_pack_path=linked,
                    library_root=library_root,
                    cache_root=root / "link-cache",
                )
            self.assertFalse((root / "link-cache").exists())

            with patch(
                "sunofriend.workbench_clips.verify_garageband_pack_archive",
                side_effect=ValueError("bad receipt"),
            ):
                with self.assertRaisesRegex(ValueError, "bad receipt"):
                    WorkbenchClipService.open(
                        acceptance_result_path=result,
                        garageband_pack_path=pack,
                        library_root=library_root,
                        cache_root=root / "archive-cache",
                    )
            self.assertFalse((root / "archive-cache").exists())

    def test_library_database_objects_and_cache_final_symlinks_are_rejected(self):
        for case in ("library", "database", "objects", "cache"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                library_root, _clip = self._library(root)
                pack, result = self._acceptance(root)
                requested_library = library_root
                requested_cache = root / "cache"

                if case == "library":
                    requested_library = root / "linked-library"
                    requested_library.symlink_to(
                        library_root,
                        target_is_directory=True,
                    )
                elif case == "database":
                    database = library_root / "catalog.sqlite3"
                    target = library_root / "catalog-real.sqlite3"
                    database.rename(target)
                    database.symlink_to(target)
                elif case == "objects":
                    objects = library_root / "objects"
                    target = library_root / "objects-real"
                    objects.rename(target)
                    objects.symlink_to(target, target_is_directory=True)
                else:
                    target = root / "cache-real"
                    target.mkdir()
                    requested_cache.symlink_to(target, target_is_directory=True)

                with (
                    patch(
                        "sunofriend.workbench_clips.verify_garageband_pack_archive",
                        return_value={"status": "verified"},
                    ),
                    self.assertRaisesRegex(
                        ValueError,
                        "explicit existing directory|real directory|non-symlink",
                    ),
                ):
                    WorkbenchClipService.open(
                        acceptance_result_path=result,
                        garageband_pack_path=pack,
                        library_root=requested_library,
                        cache_root=requested_cache,
                    )

    def _library(self, root: Path) -> tuple[Path, MidiClip]:
        library_root = root / "library"
        tempo = TempoMap.constant(120)
        clip = MidiClip(
            title="/Users/alice/private-song.mid",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument(
                "/Users/alice/private-bass.wav",
                38,
                0,
                ("/Users/alice/secret-patch.aupreset",),
            ),
            notes=(
                ClipNote.from_beats(0.5, 1.0, 38, 70, tempo),
                ClipNote.from_beats(2.0, 0.5, 42, 100, tempo),
            ),
            key=KeySignature("D", "minor"),
            provenance=Provenance(
                source_uri="/Users/alice/source/private.wav",
                source_stem="/Users/alice/source/private-bass.wav",
                details={
                    "timing_mode": "stem_locked",
                    "garageband_bpm": 120.0,
                    "private": "/Users/alice/details.json",
                },
            ),
            clip_id="clip-root",
            tags=("golden", "/Users/alice/private-tag"),
        )
        child = clip.child(
            recipe=TransformRecipe.create(
                "instrument_profile",
                secret="secret-parameter",
                path="/Users/alice/recipe.json",
            )
        )
        library = ClipLibrary(library_root)
        library.add(clip)
        library.add_version(clip.clip_id, child)
        return library_root, clip

    def _acceptance(self, root: Path, suffix: str = "") -> tuple[Path, Path]:
        pack = root / f"accepted{suffix}.zip"
        pack.write_bytes(f"exact pack{suffix}".encode())
        pack_hash = hashlib.sha256(pack.read_bytes()).hexdigest()
        result = root / f"acceptance{suffix}.json"
        document = {
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
        }
        result.write_text(json.dumps(document, indent=2, sort_keys=True))
        return pack, result

    def _service(
        self,
        root: Path,
        library_root: Path,
        pack: Path,
        result: Path,
        *,
        cache_name: str = "cache",
    ):
        verifier = patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        )

        class ServiceContext:
            def __enter__(context_self):
                context_self._patch = verifier
                context_self._patch.start()
                context_self.service = WorkbenchClipService.open(
                    acceptance_result_path=result,
                    garageband_pack_path=pack,
                    library_root=library_root,
                    cache_root=root / cache_name,
                )
                return context_self.service

            def __exit__(context_self, exc_type, exc, traceback):
                context_self._patch.stop()
                return False

        return ServiceContext()

    @staticmethod
    def _has_key(value, wanted: str) -> bool:
        if isinstance(value, dict):
            return wanted in value or any(
                WorkbenchClipServiceTests._has_key(item, wanted)
                for item in value.values()
            )
        if isinstance(value, list):
            return any(
                WorkbenchClipServiceTests._has_key(item, wanted) for item in value
            )
        return False


if __name__ == "__main__":
    unittest.main()
