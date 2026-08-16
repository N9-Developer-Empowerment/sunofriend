from __future__ import annotations

import json
import stat
import sys
import tempfile
import unittest
import wave
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sunofriend.audio_formats import file_sha256
from sunofriend.drum_roles import DRUM_ROLE_POLICY_SCHEMA
from sunofriend.source_folder_import import (
    execute_source_folder_import,
    plan_source_folder_import,
    validate_source_folder_receipt_document,
    validate_source_folder_receipt_files,
)
from sunofriend.source_project import load_source_project
from sunofriend.source_receipt import (
    document_sha256,
    validate_source_receipt_files,
)


class SourceFolderImportTests(unittest.TestCase):
    def test_original_mix_metadata_evidence_fills_missing_key_and_bpm(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "parts"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            original_mix = root / "original mix.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            _write_pcm24_wav(original_mix, sample=3)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )

            with patch(
                "sunofriend.source_folder_import.analyze_musical_metadata",
                return_value=_automatic_analysis_fixture(),
            ):
                plan = plan_source_folder_import(
                    folder,
                    root / "prepared",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    metadata_source=original_mix,
                    discover_chords=False,
                )

            self.assertEqual(plan.metadata.key, "Ab major")
            self.assertEqual(plan.metadata.bpm, 144)
            self.assertIsNone(plan.metadata.tuning_hz)
            self.assertEqual(plan.metadata_source, original_mix.resolve())
            self.assertEqual(
                plan.musical_metadata_analysis["resolution"]["provenance"][
                    "key"
                ],
                "high_confidence_automatic",
            )

    def test_folder_requires_two_to_sixty_four_top_level_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            too_few = root / "too-few"
            _write_pcm24_wav(too_few / "bass.wav", sample=1)
            with self.assertRaisesRegex(ValueError, "at least two"):
                plan_source_folder_import(
                    too_few,
                    root / "few-output",
                    ffmpeg=root / "not-needed",
                    ffprobe=root / "not-needed-either",
                    discover_chords=False,
                )

            too_many = root / "too-many"
            too_many.mkdir()
            for index in range(65):
                (too_many / f"part-{index:02d}.wav").write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "maximum is 64"):
                plan_source_folder_import(
                    too_many,
                    root / "many-output",
                    ffmpeg=root / "not-needed",
                    ffprobe=root / "not-needed-either",
                    discover_chords=False,
                )

    def test_plan_and_execute_publish_one_atomic_multi_source_project(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_folder = root / "Song-B major-119bpm-440hz"
            bass = source_folder / "Song-bass.wav"
            kick = source_folder / "Song-kick.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            chord = source_folder / "Song_chords.pdf"
            chord.write_bytes(b"%PDF-1.4\nchords\n")
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )
            destination = root / "prepared"

            plan = plan_source_folder_import(
                source_folder,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )

            self.assertFalse(destination.exists())
            self.assertEqual(plan.origin_status, "compatible")
            self.assertEqual(plan.origin_tolerance_seconds, 0.01)
            self.assertEqual(
                [part.import_plan.role for part in plan.parts],
                ["bass", "kick"],
            )
            self.assertTrue(plan.to_dict()["executable"])

            result = execute_source_folder_import(plan)

            self.assertEqual(len(result.canonicals), 2)
            self.assertTrue(all(path.parent == result.root for path in result.canonicals))
            self.assertTrue(all(path.is_file() for path in result.canonicals))
            self.assertTrue(
                any("-bass-" in path.name for path in result.canonicals)
            )
            self.assertTrue(
                any("-kick-" in path.name for path in result.canonicals)
            )
            project = load_source_project(result.source_project)
            self.assertEqual(project["schema"], "sunofriend.source-project.v1")
            self.assertEqual(project["metadata"]["key"], "B major")
            self.assertEqual(project["metadata"]["bpm"], 119.0)
            self.assertEqual(project["metadata"]["tuning_hz"], 440.0)
            self.assertEqual(
                [source["role"] for source in project["sources"]],
                ["bass", "kick"],
            )
            self.assertEqual(
                project["chord_document"]["sha256"], file_sha256(chord)
            )
            aggregate = json.loads(
                result.aggregate_receipt.read_text(encoding="utf-8")
            )
            self.assertEqual(
                aggregate["schema"], "sunofriend.source-folder-import.v2"
            )
            self.assertEqual(
                aggregate["alignment"]["origin_status"], "compatible"
            )
            self.assertFalse(
                aggregate["alignment"]["alignment_corrected"]
            )
            self.assertFalse(aggregate["normalised"])
            self.assertFalse(aggregate["network_used"])
            validate_source_folder_receipt_files(
                aggregate, root=result.root
            )
            for receipt_path in result.receipts:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                validate_source_receipt_files(receipt, root=result.root)
            for path in (
                *result.canonicals,
                *result.originals,
                *result.receipts,
                result.aggregate_receipt,
                result.source_project,
                result.chord_document,
            ):
                assert path is not None
                self.assertFalse(path.stat().st_mode & stat.S_IWUSR)

    def test_repeated_folder_imports_have_identical_receipts_and_project(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )
            first = execute_source_folder_import(
                plan_source_folder_import(
                    folder,
                    root / "first",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )
            )
            second = execute_source_folder_import(
                plan_source_folder_import(
                    folder,
                    root / "second",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )
            )

            self.assertEqual(
                first.aggregate_receipt.read_bytes(),
                second.aggregate_receipt.read_bytes(),
            )
            self.assertEqual(
                first.source_project.read_bytes(),
                second.source_project.read_bytes(),
            )
            self.assertEqual(
                [path.read_bytes() for path in first.receipts],
                [path.read_bytes() for path in second.receipts],
            )

    def test_role_map_is_exact_and_hat_uses_production_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            mystery = folder / "track one.wav"
            hats = folder / "Song-hi hats.wav"
            _write_pcm24_wav(mystery, sample=1)
            _write_pcm24_wav(hats, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    mystery.name: _probe_document(),
                    hats.name: _probe_document(),
                },
            )

            with self.assertRaisesRegex(ValueError, "exact filename"):
                plan_source_folder_import(
                    folder,
                    root / "no-map",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )
            with self.assertRaisesRegex(ValueError, "exactly match"):
                plan_source_folder_import(
                    folder,
                    root / "wrong-map",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    role_map={"TRACK ONE.WAV": "keys"},
                    discover_chords=False,
                )

            plan = plan_source_folder_import(
                folder,
                root / "mapped",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                role_map={mystery.name: "keys"},
                discover_chords=False,
            )

            self.assertEqual(
                [part.import_plan.role for part in plan.parts],
                ["hat", "keys"],
            )
            keys_part = next(
                part
                for part in plan.parts
                if part.import_plan.role == "keys"
            )
            self.assertIn(
                "-keys-canonical.wav",
                keys_part.import_plan.canonical_relative_path,
            )

    def test_multi_role_filename_and_unknown_mapped_role_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            ambiguous = folder / "bass and keys.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(ambiguous, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    ambiguous.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )
            with self.assertRaisesRegex(ValueError, "ambiguous stem role"):
                plan_source_folder_import(
                    folder,
                    root / "ambiguous",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )
            with self.assertRaisesRegex(
                ValueError, "unsupported prepared source role"
            ):
                plan_source_folder_import(
                    folder,
                    root / "unknown",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    role_map={ambiguous.name: "banana"},
                    discover_chords=False,
                )
            mapped = plan_source_folder_import(
                folder,
                root / "mapped",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                role_map={ambiguous.name: "bass"},
                discover_chords=False,
            )
            self.assertEqual(
                [part.import_plan.role for part in mapped.parts],
                ["bass", "kick"],
            )

    def test_duplicate_non_vocal_roles_fail_but_vocals_may_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            first = folder / "bass one.wav"
            second = folder / "bass two.wav"
            _write_pcm24_wav(first, sample=1)
            _write_pcm24_wav(second, sample=2)
            probes = {
                first.name: _probe_document(),
                second.name: _probe_document(),
            }
            ffmpeg, ffprobe = _fake_toolchain(root, probes)

            with self.assertRaisesRegex(ValueError, "duplicate role"):
                plan_source_folder_import(
                    folder,
                    root / "duplicate-bass",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )

            plan = plan_source_folder_import(
                folder,
                root / "two-vocals",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                role_map={
                    first.name: "vocals",
                    second.name: "vocals",
                },
                discover_chords=False,
            )
            self.assertEqual(
                [part.import_plan.role for part in plan.parts],
                ["vocals", "vocals"],
            )
            self.assertTrue(
                all(
                    (
                        part.shape,
                        part.refinement_status,
                        part.conversion_status,
                    )
                    == ("leaf", "not-requested", "vocal-specialist")
                    for part in plan.parts
                )
            )

            result = execute_source_folder_import(plan)
            aggregate = json.loads(
                result.aggregate_receipt.read_text(encoding="utf-8")
            )
            validate_source_folder_receipt_document(aggregate)
            for field, value in (
                ("shape", "composite"),
                ("refinement_status", "pending"),
                ("conversion_status", "supported"),
            ):
                with self.subTest(vocal_semantic=field):
                    mutated = deepcopy(aggregate)
                    mutated["parts"][0][field] = value
                    _rehash_folder_receipt(mutated)
                    with self.assertRaisesRegex(
                        ValueError,
                        "processing semantics",
                    ):
                        validate_source_folder_receipt_document(mutated)

    def test_duplicate_original_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, sample=3)
            kick.write_bytes(bass.read_bytes())
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )

            with self.assertRaisesRegex(ValueError, "duplicate original"):
                plan_source_folder_import(
                    folder,
                    root / "prepared",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )

    def test_unconfirmed_origin_requires_explicit_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(start_time=None),
                    kick.name: _probe_document(),
                },
            )
            plan = plan_source_folder_import(
                folder,
                root / "blocked",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )
            self.assertEqual(plan.origin_status, "unconfirmed")
            self.assertFalse(plan.to_dict()["executable"])
            with self.assertRaisesRegex(ValueError, "explicitly accept"):
                execute_source_folder_import(plan)
            self.assertFalse((root / "blocked").exists())

            accepted = plan_source_folder_import(
                folder,
                root / "accepted",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
                accept_unconfirmed_origin=True,
            )
            result = execute_source_folder_import(accepted)
            aggregate = json.loads(
                result.aggregate_receipt.read_text(encoding="utf-8")
            )
            self.assertTrue(
                aggregate["alignment"]["unconfirmed_origin_accepted"]
            )

    def test_concrete_origin_conflict_cannot_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(start_time=0.0),
                    kick.name: _probe_document(start_time=0.0201),
                },
            )
            plan = plan_source_folder_import(
                folder,
                root / "conflict",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
                accept_unconfirmed_origin=True,
            )
            self.assertEqual(plan.origin_status, "conflicting")
            self.assertFalse(plan.to_dict()["executable"])
            tampered = replace(plan, origin_status="compatible")
            with self.assertRaisesRegex(
                ValueError,
                "alignment evidence changed",
            ):
                execute_source_folder_import(tampered)
            with self.assertRaisesRegex(ValueError, "conflicting"):
                execute_source_folder_import(plan)
            self.assertFalse((root / "conflict").exists())

    def test_execution_rejects_modified_relative_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )
            plan = plan_source_folder_import(
                folder,
                root / "prepared",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )
            first = plan.parts[0]
            changed_import = replace(
                first.import_plan,
                canonical_relative_path="../escaped.wav",
            )
            changed_part = replace(first, import_plan=changed_import)
            tampered = replace(
                plan,
                parts=(changed_part, *plan.parts[1:]),
            )

            with self.assertRaisesRegex(
                ValueError,
                "canonical output path changed",
            ):
                execute_source_folder_import(tampered)

            self.assertFalse((root / "prepared").exists())
            self.assertFalse((root / "escaped.wav").exists())

    def test_horizon_difference_warns_but_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, frame_count=80, sample=1)
            _write_pcm24_wav(kick, frame_count=880, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(frame_count=80),
                    kick.name: _probe_document(frame_count=880),
                },
            )
            plan = plan_source_folder_import(
                folder,
                root / "different-horizons",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )
            self.assertEqual(plan.origin_status, "compatible")
            self.assertTrue(any("horizons differ" in row for row in plan.warnings))

            result = execute_source_folder_import(plan)
            aggregate = json.loads(
                result.aggregate_receipt.read_text(encoding="utf-8")
            )
            self.assertTrue(
                aggregate["alignment"]["different_horizons"]
            )

    def test_source_mutation_and_decode_failure_leave_no_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            snare = folder / "snare.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(snare, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    snare.name: _probe_document(),
                },
            )
            mutated_plan = plan_source_folder_import(
                folder,
                root / "mutated",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )
            _write_pcm24_wav(bass, sample=4)
            with self.assertRaisesRegex(ValueError, "changed after planning"):
                execute_source_folder_import(mutated_plan)
            self.assertFalse((root / "mutated").exists())

            _write_pcm24_wav(bass, sample=1)
            failing_ffmpeg, failing_ffprobe = _fake_toolchain(
                root / "failing-tools",
                {
                    bass.name: _probe_document(),
                    snare.name: _probe_document(),
                },
                fail_name=snare.name,
            )
            failing_plan = plan_source_folder_import(
                folder,
                root / "decode-failure",
                ffmpeg=failing_ffmpeg,
                ffprobe=failing_ffprobe,
                discover_chords=False,
            )
            with self.assertRaisesRegex(RuntimeError, "decode failed"):
                execute_source_folder_import(failing_plan)
            self.assertFalse((root / "decode-failure").exists())
            self.assertEqual(
                list(root.glob(".decode-failure.importing-*")), []
            )

    def test_source_set_and_destination_boundaries_are_rechecked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            bass = folder / "bass.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(bass, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    bass.name: _probe_document(),
                    kick.name: _probe_document(),
                    "snare.wav": _probe_document(),
                },
            )
            with self.assertRaisesRegex(ValueError, "outside"):
                plan_source_folder_import(
                    folder,
                    folder / "prepared",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    discover_chords=False,
                )
            plan = plan_source_folder_import(
                folder,
                root / "prepared",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )
            _write_pcm24_wav(folder / "snare.wav", sample=3)
            with self.assertRaisesRegex(ValueError, "set changed"):
                execute_source_folder_import(plan)
            self.assertFalse((root / "prepared").exists())

    def test_composite_drums_are_supported_but_require_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            drums = folder / "drums.wav"
            bass = folder / "bass.wav"
            _write_pcm24_wav(drums, sample=1)
            _write_pcm24_wav(bass, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    drums.name: _probe_document(),
                    bass.name: _probe_document(),
                },
            )
            plan = plan_source_folder_import(
                folder,
                root / "prepared",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )
            drum_part = next(
                part
                for part in plan.parts
                if part.import_plan.role == "drums"
            )
            self.assertEqual(drum_part.shape, "composite")
            self.assertEqual(
                drum_part.refinement_status,
                "not-run-midi-family-variants-only",
            )
            self.assertEqual(
                drum_part.conversion_status,
                "supported-review-required",
            )
            plan_document = plan.to_dict()
            self.assertEqual(
                plan_document["schema"],
                "sunofriend.source-folder-import-plan.v2",
            )
            self.assertEqual(plan_document["shadowed_roles"], [])
            self.assertTrue(plan_document["drum_role_policy"]["warnings"])
            self.assertEqual(
                plan_document["drum_role_policy"]["schema"],
                DRUM_ROLE_POLICY_SCHEMA,
            )

            result = execute_source_folder_import(plan)
            aggregate = json.loads(
                result.aggregate_receipt.read_text(encoding="utf-8")
            )
            self.assertEqual(
                aggregate["schema"], "sunofriend.source-folder-import.v2"
            )
            self.assertEqual(aggregate["shadowed_roles"], [])
            self.assertEqual(
                aggregate["drum_role_policy"]["schema"],
                DRUM_ROLE_POLICY_SCHEMA,
            )
            validate_source_folder_receipt_document(aggregate)

            older_warning_wording = deepcopy(aggregate)
            older_warning_wording["drum_role_policy"]["warnings"] = [
                "Earlier composite-drum review wording."
            ]
            older_warning_wording["warnings"] = [
                "Earlier composite-drum review wording."
            ]
            older_warning_wording["alignment"]["warnings"] = [
                "Earlier composite-drum review wording."
            ]
            _rehash_folder_receipt(older_warning_wording)
            validate_source_folder_receipt_document(older_warning_wording)

            for field, value in (
                ("schema", "sunofriend.drum-role-policy.v999"),
                ("classifier_alias", "kick"),
                ("precedence", "always-combine"),
                ("shadowed_roles", ["drums"]),
                ("audio_children_created", True),
            ):
                with self.subTest(policy_field=field):
                    mutated = deepcopy(aggregate)
                    mutated["drum_role_policy"][field] = value
                    _rehash_folder_receipt(mutated)
                    with self.assertRaisesRegex(
                        ValueError,
                        "drum role policy",
                    ):
                        validate_source_folder_receipt_document(mutated)

            extra_policy_field = deepcopy(aggregate)
            extra_policy_field["drum_role_policy"]["future"] = None
            _rehash_folder_receipt(extra_policy_field)
            with self.assertRaisesRegex(ValueError, "policy fields"):
                validate_source_folder_receipt_document(extra_policy_field)

            for field, value in (
                ("shape", "leaf"),
                ("refinement_status", "not-requested"),
                ("conversion_status", "supported"),
            ):
                with self.subTest(drum_semantic=field):
                    mutated = deepcopy(aggregate)
                    mutated_drum = next(
                        part
                        for part in mutated["parts"]
                        if part["role"] == "drums"
                    )
                    mutated_drum[field] = value
                    _rehash_folder_receipt(mutated)
                    with self.assertRaisesRegex(
                        ValueError,
                        "processing semantics",
                    ):
                        validate_source_folder_receipt_document(mutated)

            for field, value in (
                ("shape", "composite"),
                ("refinement_status", "pending"),
                ("conversion_status", "vocal-specialist"),
            ):
                with self.subTest(leaf_semantic=field):
                    mutated = deepcopy(aggregate)
                    mutated_bass = next(
                        part
                        for part in mutated["parts"]
                        if part["role"] == "bass"
                    )
                    mutated_bass[field] = value
                    _rehash_folder_receipt(mutated)
                    with self.assertRaisesRegex(
                        ValueError,
                        "processing semantics",
                    ):
                        validate_source_folder_receipt_document(mutated)

            extra_aggregate_field = deepcopy(aggregate)
            extra_aggregate_field["future"] = {}
            _rehash_folder_receipt(extra_aggregate_field)
            with self.assertRaisesRegex(ValueError, "aggregate fields"):
                validate_source_folder_receipt_document(
                    extra_aggregate_field
                )

            missing_aggregate_field = deepcopy(aggregate)
            missing_aggregate_field.pop("warnings")
            _rehash_folder_receipt(missing_aggregate_field)
            with self.assertRaisesRegex(ValueError, "aggregate fields"):
                validate_source_folder_receipt_document(
                    missing_aggregate_field
                )

            extra_part_field = deepcopy(aggregate)
            extra_part_field["parts"][0]["future"] = None
            _rehash_folder_receipt(extra_part_field)
            with self.assertRaisesRegex(ValueError, "part 0 fields"):
                validate_source_folder_receipt_document(extra_part_field)

            missing_part_field = deepcopy(aggregate)
            missing_part_field["parts"][0].pop("original_name")
            _rehash_folder_receipt(missing_part_field)
            with self.assertRaisesRegex(ValueError, "part 0 fields"):
                validate_source_folder_receipt_document(missing_part_field)

            legacy = deepcopy(aggregate)
            legacy["schema"] = "sunofriend.source-folder-import.v1"
            legacy.pop("drum_role_policy")
            legacy.pop("shadowed_roles")
            legacy.pop("warnings")
            legacy_drum = next(
                part for part in legacy["parts"] if part["role"] == "drums"
            )
            legacy_drum["refinement_status"] = "pending-s2-refinement"
            legacy_drum["conversion_status"] = (
                "unsupported-pending-s2-refinement"
            )
            _rehash_folder_receipt(legacy)
            validate_source_folder_receipt_document(legacy)

    def test_explicit_drum_leaves_shadow_composite_in_automatic_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sources"
            drums = folder / "drums.wav"
            kick = folder / "kick.wav"
            _write_pcm24_wav(drums, sample=1)
            _write_pcm24_wav(kick, sample=2)
            ffmpeg, ffprobe = _fake_toolchain(
                root,
                {
                    drums.name: _probe_document(),
                    kick.name: _probe_document(),
                },
            )

            plan = plan_source_folder_import(
                folder,
                root / "prepared",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                discover_chords=False,
            )

            plan_document = plan.to_dict()
            self.assertEqual(plan_document["shadowed_roles"], ["drums"])
            self.assertEqual(
                plan_document["drum_role_policy"]["precedence"],
                "explicit-leaves-over-composite",
            )
            self.assertTrue(
                any(
                    "prevents doubled drum hits" in warning
                    for warning in plan_document["warnings"]
                )
            )

            result = execute_source_folder_import(plan)
            aggregate = json.loads(
                result.aggregate_receipt.read_text(encoding="utf-8")
            )
            self.assertEqual(aggregate["shadowed_roles"], ["drums"])
            self.assertFalse(
                aggregate["drum_role_policy"]["audio_children_created"]
            )


def _write_pcm24_wav(
    path: Path,
    *,
    frame_count: int = 80,
    sample: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = int(sample).to_bytes(3, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(3)
        handle.setframerate(8000)
        handle.writeframes(value * frame_count)


def _rehash_folder_receipt(document: dict) -> None:
    seed = {
        key: value
        for key, value in document.items()
        if key != "folder_import_id"
    }
    document["folder_import_id"] = f"sha256:{document_sha256(seed)}"


def _probe_document(
    *,
    frame_count: int = 80,
    start_time: float | None = 0.0,
) -> dict:
    duration = frame_count / 8000
    stream = {
        "index": 0,
        "codec_name": "pcm_s24le",
        "codec_type": "audio",
        "sample_fmt": "s32",
        "sample_rate": "8000",
        "channels": 1,
        "channel_layout": "mono",
        "time_base": "1/8000",
        "duration_ts": frame_count,
        "duration": f"{duration:.9f}",
        "initial_padding": 0,
        "trailing_padding": 0,
    }
    format_row = {
        "format_name": "wav",
        "duration": f"{duration:.9f}",
    }
    if start_time is not None:
        stream["start_pts"] = round(start_time * 8000)
        stream["start_time"] = f"{start_time:.9f}"
        format_row["start_time"] = f"{start_time:.9f}"
    return {"streams": [stream], "format": format_row}


def _fake_toolchain(
    root: Path,
    probe_documents: dict[str, dict],
    *,
    fail_name: str | None = None,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    ffmpeg = root / "ffmpeg-folder-fake"
    ffprobe = root / "ffprobe-folder-fake"
    ffmpeg.write_text(
        f"""#!{sys.executable}
import pathlib
import shutil
import sys
if "-version" in sys.argv:
    print("ffmpeg version sunofriend-folder-test")
elif "-formats" in sys.argv:
    print(" D  wav")
elif "-codecs" in sys.argv:
    print(" DEAI.S pcm_s24le PCM signed 24-bit little-endian")
else:
    source = pathlib.Path(sys.argv[sys.argv.index("-i") + 1])
    if {fail_name!r} is not None and source.name == {fail_name!r}:
        print("planned decode failure", file=sys.stderr)
        sys.exit(12)
    shutil.copyfile(source, sys.argv[-1])
""",
        encoding="utf-8",
    )
    ffprobe.write_text(
        f"""#!{sys.executable}
import json
import pathlib
import sys
documents = json.loads({json.dumps(json.dumps(probe_documents))})
if "-version" in sys.argv:
    print("ffprobe version sunofriend-folder-test")
else:
    print(json.dumps(documents[pathlib.Path(sys.argv[-1]).name]))
""",
        encoding="utf-8",
    )
    ffmpeg.chmod(0o755)
    ffprobe.chmod(0o755)
    return ffmpeg, ffprobe


def _automatic_analysis_fixture() -> dict:
    return {
        "schema": "sunofriend.musical-metadata-analysis.v1",
        "status": "complete_unreviewed",
        "network_used": False,
        "source": {
            "sha256": "a" * 64,
            "bytes": 1,
            "duration_seconds": 1.0,
        },
        "algorithm": {"id": "fixture"},
        "estimates": {
            "key": {"selected_key": "Ab major", "confidence": "high"},
            "tempo": {"selected_bpm": 144, "confidence": "high"},
            "tuning": {
                "concert_a_hz": 449.505,
                "confidence": "review_recommended",
            },
        },
        "suggested_metadata": {
            "key": "Ab major",
            "bpm": 144,
            "tuning_hz": 449.505,
        },
        "review": {"status": "not_reviewed", "review_recommended": True},
        "effects": {"source_audio_mutated": False},
    }


if __name__ == "__main__":
    unittest.main()
