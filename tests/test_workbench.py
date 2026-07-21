from __future__ import annotations

import http.client
import hashlib
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog, public_catalog
from sunofriend.workbench_artifacts import WorkbenchArtifacts, selected_candidates
from sunofriend.workbench_server import _display_candidates, create_workbench_server
from sunofriend.workbench_store import WorkbenchStore


class WorkbenchCatalogTests(unittest.TestCase):
    def test_discovers_bounded_role_candidates_and_path_free_public_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Test Song-B minor-113bpm-440hz"
            candidates = root / "candidate-runs"
            project.mkdir()
            source = project / "Test Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-source-audio")

            for index, directory_name in enumerate(
                ("bass-baseline", "bass-muscriptor", "bass-hybrid", "bass-cleanup"),
                start=1,
            ):
                directory = candidates / directory_name
                directory.mkdir(parents=True)
                midi = directory / (
                    "bass_listened.mid" if index == 1 else "candidate.mid"
                )
                _write_midi(midi, pitch=35 + index)
                if index == 1:
                    midi.with_suffix(".preview.wav").write_bytes(b"RIFF-preview")

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
            )

            self.assertEqual(catalog["setup"]["bpm"], 113.0)
            self.assertEqual(catalog["setup"]["key"], "B minor")
            self.assertEqual(catalog["setup"]["tuning_hz"], 440.0)
            self.assertEqual(len(catalog["stems"]), 1)
            stem = catalog["stems"][0]
            self.assertEqual(stem["role"], "bass")
            self.assertEqual(stem["candidate_count"], 4)
            self.assertEqual(sum(item["primary"] for item in stem["candidates"]), 3)
            self.assertEqual(stem["candidates"][0]["process"], "sunofriend-specialist")
            self.assertIsNotNone(stem["candidates"][0]["preview"])

            public = public_catalog(catalog)
            rendered = json.dumps(public)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("source_path", rendered)
            self.assertNotIn("midi_path", rendered)

    def test_byte_identical_stems_keep_distinct_review_state_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "Duplicate Song-D minor-120bpm-440hz"
            project.mkdir()
            payload = b"RIFF-identical-silence"
            (project / "Duplicate Song-bass-D minor-120bpm-440hz.wav").write_bytes(
                payload
            )
            (project / "Duplicate Song-keys-D minor-120bpm-440hz.wav").write_bytes(
                payload
            )

            catalog = build_workbench_catalog(project)
            ids = {stem["stem_id"] for stem in catalog["stems"]}
            self.assertEqual(len(ids), 2)
            self.assertEqual({stem["role"] for stem in catalog["stems"]}, {"bass", "keys"})

    def test_automatic_discovery_rejects_symlinks_outside_explicit_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Symlink Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            outside = root / "outside"
            project.mkdir()
            candidates.mkdir()
            outside.mkdir()
            (project / "Symlink Song-bass-D minor-120bpm-440hz.wav").write_bytes(
                b"RIFF-source"
            )
            outside_midi = outside / "bass.mid"
            _write_midi(outside_midi, pitch=38)
            linked_midi = candidates / "bass.mid"
            linked_midi.symlink_to(outside_midi)

            with self.assertRaisesRegex(ValueError, "MIDI symlink escapes"):
                build_workbench_catalog(project, candidate_roots=[candidates])

            linked_midi.unlink()
            _write_midi(linked_midi, pitch=38)
            outside_preview = outside / "bass.preview.wav"
            outside_preview.write_bytes(b"RIFF-outside-preview")
            (candidates / "bass.preview.wav").symlink_to(outside_preview)
            with self.assertRaisesRegex(ValueError, "preview symlink escapes"):
                build_workbench_catalog(project, candidate_roots=[candidates])

    def test_explicit_catalog_requires_candidates_inside_named_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-E major-125bpm-440hz"
            candidate_root = root / "outputs"
            project.mkdir()
            candidate_root.mkdir()
            source = project / "Song-keys-E major-125bpm-440hz.wav"
            source.write_bytes(b"RIFF-source")
            midi = candidate_root / "keys.mid"
            _write_midi(midi, pitch=64)
            preview = candidate_root / "keys.wav"
            preview.write_bytes(b"RIFF-preview")
            document = root / "catalog.json"
            document.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "role": "keys",
                                "candidates": [
                                    {
                                        "midi": str(midi),
                                        "preview": str(preview),
                                        "label": "Neutral keys candidate",
                                        "process": "test-process",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "outside the explicit local"):
                build_workbench_catalog(project, catalog_path=document)

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )
            self.assertEqual(
                catalog["stems"][0]["candidates"][0]["label"],
                "Neutral keys candidate",
            )

    def test_explicit_review_guidance_is_preserved_in_public_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Guided Song-B minor-113bpm-440hz"
            candidate_root = root / "outputs"
            project.mkdir()
            candidate_root.mkdir()
            source = project / "Guided Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-mixed-bass")
            midi = candidate_root / "requested-label.mid"
            _write_midi(midi, pitch=38)
            document = root / "catalog.json"
            document.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "label": "Bass body review",
                                "role": "bass body",
                                "review_question": (
                                    "Does this MIDI follow the deep bass body?"
                                ),
                                "listening_focus": [
                                    "recognisable bass line",
                                    "pluck leakage",
                                    "missing or extra notes",
                                ],
                                "candidates": [{"midi": str(midi)}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )
            public = public_catalog(catalog)
            stem = public["stems"][0]
            self.assertEqual(
                stem["review_question"],
                "Does this MIDI follow the deep bass body?",
            )
            self.assertEqual(
                stem["listening_focus"],
                [
                    "recognisable bass line",
                    "pluck leakage",
                    "missing or extra notes",
                ],
            )
            expected_context = {
                "review_question": "Does this MIDI follow the deep bass body?",
                "listening_focus": [
                    "recognisable bass line",
                    "pluck leakage",
                    "missing or extra notes",
                ],
            }
            self.assertEqual(
                stem["review_context_sha256"],
                hashlib.sha256(
                    json.dumps(
                        expected_context,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )
            self.assertNotIn(str(root), json.dumps(public))

    def test_review_prompt_changes_stem_identity_without_changing_legacy_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Prompt Song-B minor-113bpm-440hz"
            candidates = root / "outputs"
            project.mkdir()
            candidates.mkdir()
            source = project / "Prompt Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-prompt-source")
            midi = candidates / "bass.mid"
            _write_midi(midi, pitch=38)

            legacy = build_workbench_catalog(project, candidate_roots=[candidates])
            legacy_stem = legacy["stems"][0]
            legacy_identity = "\0".join(
                [
                    legacy_stem["source"]["sha256"],
                    "bass",
                    source.name.casefold(),
                ]
            ).encode("utf-8")
            self.assertEqual(
                legacy_stem["stem_id"],
                "stem-" + hashlib.sha256(legacy_identity).hexdigest()[:20],
            )

            document = root / "catalog.json"
            base_document = {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "bass",
                        "review_question": "Does this preserve the bass body?",
                        "listening_focus": ["body", "missing notes"],
                        "candidates": [{"midi": str(midi)}],
                    }
                ],
            }
            document.write_text(json.dumps(base_document), encoding="utf-8")
            first = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
                catalog_path=document,
            )
            first_stem = first["stems"][0]
            self.assertNotEqual(first_stem["stem_id"], legacy_stem["stem_id"])

            base_document["stems"][0]["review_question"] = (
                "Does this preserve the plucked line?"
            )
            document.write_text(json.dumps(base_document), encoding="utf-8")
            second = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
                catalog_path=document,
            )
            second_stem = second["stems"][0]
            self.assertNotEqual(first_stem["stem_id"], second_stem["stem_id"])
            self.assertNotEqual(
                first_stem["review_context_sha256"],
                second_stem["review_context_sha256"],
            )

    def test_verified_ai_label_split_keeps_complement_advanced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Split Song-B minor-113bpm-440hz"
            candidate_root = root / "label-split"
            project.mkdir()
            source = project / "Split Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-mixed-bass")
            _write_ai_label_split_fixture(
                candidate_root,
                label="synth_bass",
                selected_pitches=(35, 38),
                complement_pitches=(59,),
            )
            document = _write_explicit_split_catalog(
                root / "catalog.json",
                source=source,
                candidate_root=candidate_root,
                role="bass body",
            )

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )
            stem = catalog["stems"][0]
            by_name = {
                candidate["midi"]["name"]: candidate
                for candidate in stem["candidates"]
            }
            selected = by_name["requested-label.mid"]
            complement = by_name["unexpected-label-complement.mid"]

            self.assertTrue(selected["primary"])
            self.assertFalse(selected["diagnostic_only"])
            self.assertFalse(selected["audition_blocked"])
            self.assertEqual(selected["ai_diagnostics"]["note_count"], 2)
            self.assertEqual(selected["ai_diagnostics"]["model_size"], "small")
            self.assertEqual(
                selected["ai_diagnostics"]["requested_labels"], ["synth_bass"]
            )
            expected_origin = hashlib.sha256(b"fixture-source-audio").hexdigest()
            self.assertEqual(
                selected["ai_diagnostics"]["source_audio_sha256"], expected_origin
            )
            self.assertEqual(
                selected["ai_diagnostics"]["derivative"]["partition"],
                "selected",
            )
            self.assertFalse(complement["primary"])
            self.assertTrue(complement["diagnostic_only"])
            self.assertFalse(complement["audition_blocked"])
            self.assertEqual(complement["ai_diagnostics"]["note_count"], 1)
            self.assertEqual(
                complement["ai_diagnostics"]["detected_labels"],
                ["clean_electric_guitar"],
            )
            self.assertEqual(
                complement["ai_diagnostics"]["source_audio_sha256"],
                expected_origin,
            )
            self.assertEqual(
                complement["ai_diagnostics"]["derivative"]["partition"],
                "complement",
            )
            self.assertEqual(stem["primary_candidate_count"], 1)

    def test_zero_note_ai_label_split_target_cannot_be_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Missing Role Song-B minor-113bpm-440hz"
            candidate_root = root / "label-split"
            project.mkdir()
            source = project / "Missing Role Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-mixed-bass")
            _write_ai_label_split_fixture(
                candidate_root,
                label="synth_bass",
                selected_pitches=(),
                complement_pitches=(59, 62),
            )
            document = _write_explicit_split_catalog(
                root / "catalog.json",
                source=source,
                candidate_root=candidate_root,
                role="bass body",
            )

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )
            stem = catalog["stems"][0]
            target = next(
                candidate
                for candidate in stem["candidates"]
                if candidate["midi"]["name"] == "requested-label.mid"
            )
            self.assertTrue(target["audition_blocked"])
            self.assertTrue(target["diagnostic_only"])
            self.assertFalse(target["primary"])
            self.assertEqual(target["ai_diagnostics"]["note_count"], 0)
            self.assertIn(
                "no-note-evidence", target["ai_diagnostics"]["block_reasons"]
            )

            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for decision in ("main", "optional"):
                with self.subTest(decision=decision), self.assertRaisesRegex(
                    ValueError, "diagnostic-only"
                ):
                    store.append(
                        catalog,
                        {
                            "event_type": "candidate_decision",
                            "stem_id": stem["stem_id"],
                            "candidate_id": target["candidate_id"],
                            "decision": decision,
                            "context": "solo",
                            "problem_tags": [],
                        },
                    )

    def test_ai_label_split_cross_artifact_tampering_is_rejected(self) -> None:
        cases = (
            "partition-label",
            "partition-note",
            "source-candidate-sha",
            "evidence-indices",
            "partition-flags",
            "effects",
            "bpm",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                project = root / "Tampered Split-B minor-113bpm-440hz"
                candidate_root = root / "label-split"
                project.mkdir()
                source = project / "Tampered Split-bass-B minor-113bpm-440hz.wav"
                source.write_bytes(b"RIFF-private-mixed-bass")
                _write_ai_label_split_fixture(
                    candidate_root,
                    label="synth_bass",
                    selected_pitches=(35, 38),
                    complement_pitches=(59,),
                )
                report = _read_split_report(candidate_root)
                partition = _read_split_partition(candidate_root)
                if case == "partition-label":
                    partition["label"] = "electric_bass"
                elif case == "partition-note":
                    partition["selected"][0]["note"]["pitch"] += 12.0
                elif case == "source-candidate-sha":
                    partition["source_candidate_sha256"] = "0" * 64
                elif case == "evidence-indices":
                    report["evidence"]["selected_source_indices"] = [1, 0]
                elif case == "partition-flags":
                    partition["partition"]["exhaustive"] = False
                elif case == "effects":
                    report["effects"]["automatic_promotion"] = True
                elif case == "bpm":
                    report["bpm"] = 114.0
                _rewrite_split_documents(
                    candidate_root,
                    report=report,
                    partition=partition,
                )
                document = _write_explicit_split_catalog(
                    root / "catalog.json",
                    source=source,
                    candidate_root=candidate_root,
                    role="bass body",
                )

                with self.assertRaisesRegex(ValueError, "adjacent AI label"):
                    build_workbench_catalog(
                        project,
                        candidate_roots=[candidate_root],
                        catalog_path=document,
                    )

    def test_ai_label_split_same_count_different_midi_note_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Wrong Notes-B minor-113bpm-440hz"
            candidate_root = root / "label-split"
            project.mkdir()
            source = project / "Wrong Notes-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-mixed-bass")
            _write_ai_label_split_fixture(
                candidate_root,
                label="synth_bass",
                selected_pitches=(35, 38),
                complement_pitches=(59,),
            )
            partition = _read_split_partition(candidate_root)
            changed_rows = json.loads(json.dumps(partition["selected"]))
            for row in changed_rows:
                row["note"]["pitch"] += 12.0
            selected_midi = candidate_root / "requested-label.mid"
            _write_partition_midi(selected_midi, changed_rows)
            report = _read_split_report(candidate_root)
            report["artifacts"][selected_midi.name] = _record(
                selected_midi, relative=True
            )
            _rewrite_split_documents(
                candidate_root,
                report=report,
                partition=partition,
            )
            document = _write_explicit_split_catalog(
                root / "catalog.json",
                source=source,
                candidate_root=candidate_root,
                role="bass body",
            )

            with self.assertRaisesRegex(ValueError, "MIDI notes disagree"):
                build_workbench_catalog(
                    project,
                    candidate_roots=[candidate_root],
                    catalog_path=document,
                )

    def test_ai_label_split_severe_burst_remains_audition_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Burst Split-B minor-113bpm-440hz"
            candidate_root = root / "label-split"
            project.mkdir()
            source = project / "Burst Split-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-mixed-bass")
            _write_ai_label_split_fixture(
                candidate_root,
                label="synth_bass",
                selected_pitches=tuple(range(20, 100)),
                complement_pitches=(),
                simultaneous=True,
            )
            document = _write_explicit_split_catalog(
                root / "catalog.json",
                source=source,
                candidate_root=candidate_root,
                role="bass body",
            )

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )
            target = next(
                candidate
                for candidate in catalog["stems"][0]["candidates"]
                if candidate["midi"]["name"] == "requested-label.mid"
            )
            self.assertEqual(target["ai_diagnostics"]["note_count"], 80)
            self.assertTrue(target["audition_blocked"])
            self.assertTrue(target["diagnostic_only"])
            self.assertFalse(target["primary"])
            self.assertIn(
                "extreme-onset-burst",
                target["ai_diagnostics"]["severe_codes"],
            )
            self.assertIn(
                "extreme-polyphony",
                target["ai_diagnostics"]["block_reasons"],
            )

    def test_one_source_can_hold_two_independently_selected_role_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Two Role Song-B minor-113bpm-440hz"
            candidate_root = root / "outputs"
            project.mkdir()
            candidate_root.mkdir()
            source = project / "Two Role Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-one-mixed-role-source")
            body_midi = candidate_root / "bass-body.mid"
            pluck_midi = candidate_root / "bass-pluck.mid"
            _write_midi(body_midi, pitch=35)
            _write_midi(pluck_midi, pitch=59)
            document = root / "catalog.json"
            document.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "role": "bass body",
                                "review_question": "Does this follow the bass body?",
                                "candidates": [{"midi": str(body_midi)}],
                            },
                            {
                                "source": str(source),
                                "role": "pluck",
                                "review_question": "Does this follow the plucked line?",
                                "candidates": [{"midi": str(pluck_midi)}],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )

            self.assertEqual(len(catalog["stems"]), 2)
            self.assertEqual(
                len({stem["stem_id"] for stem in catalog["stems"]}), 2
            )
            self.assertEqual(
                len({stem["source"]["sha256"] for stem in catalog["stems"]}), 1
            )
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for stem in catalog["stems"]:
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "solo",
                        "problem_tags": [],
                    },
                )

            state = store.current_state(catalog)
            for stem in catalog["stems"]:
                stem_state = state["stems"][stem["stem_id"]]
                self.assertEqual(
                    stem_state["main_candidate_id"],
                    stem["candidates"][0]["candidate_id"],
                )
            selected = selected_candidates(catalog, state)
            self.assertEqual(len(selected), 2)
            self.assertEqual(
                {row["role"] for row in selected}, {"bass body", "pluck"}
            )

    def test_ai_run_diagnostics_are_path_free_and_block_only_severe_bursts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "AI Song-B minor-119bpm-440hz"
            run_dir = root / "bass-muscriptor" / "run"
            project.mkdir()
            run_dir.mkdir(parents=True)
            source = project / "AI Song-bass-B minor-119bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-source")
            checkpoint = root / "model.safetensors"
            checkpoint.write_bytes(b"checkpoint")
            config = root / "config.json"
            config.write_text(
                '{"model_type":"muscriptor","variant":"small"}',
                encoding="utf-8",
            )
            worker = root / "worker.py"
            worker.write_text("# pinned worker\n", encoding="utf-8")
            checkpoint_hash = _record(checkpoint)["sha256"]
            config_hash = _record(config)["sha256"]
            midi = run_dir / "candidate.mid"
            _write_midi(midi, pitch=40)
            request = {
                "schema": "sunofriend.ai-transcription-request.v1",
                "audio_path": str(source.resolve()),
                "backend": "muscriptor",
                "roles": [],
                "start_seconds": 0.0,
                "end_seconds": 15.0,
                "options": {
                    "model_sha256": checkpoint_hash,
                    "model_config_sha256": config_hash,
                },
            }
            notes = [
                {
                    "start_seconds": 8.54,
                    "end_seconds": 8.55,
                    "pitch": 36.0,
                    "confidence": None,
                    "instrument": "drums",
                    "velocity": None,
                    "source_event_id": str(index),
                }
                for index in range(80)
            ]
            candidate = {
                "schema": "sunofriend.ai-transcription-candidate.v1",
                "backend": "muscriptor",
                "model_version": "muscriptor-test-small",
                "notes": notes,
                "warnings": [],
                "raw_artifacts": [],
                "metadata": {
                    "checkpoint_sha256": checkpoint_hash,
                    "excerpt": {"duration_seconds": 15.0},
                },
            }
            (run_dir / "request.json").write_text(
                json.dumps(request), encoding="utf-8"
            )
            (run_dir / "candidate.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            (run_dir / "candidate.raw.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            # Deliberately benign stored metrics prove the Workbench recomputes
            # its safety gate from the verified candidate instead of trusting it.
            (run_dir / "candidate.quality.json").write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.ai-candidate-quality.v1",
                        "status": "pass",
                        "promotion_allowed": True,
                        "metrics": {"note_count": len(notes)},
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            artifacts = {
                name: _record(run_dir / name, relative=True)
                for name in (
                    "request.json",
                    "candidate.raw.json",
                    "candidate.json",
                    "candidate.quality.json",
                    "candidate.mid",
                )
            }
            execution = {
                "model_config_sha256": config_hash,
                "model_size": "small",
                "diagnostic": {
                    "cwd": str(root / "private-working-directory"),
                    "safe_value": "retained",
                    "cache": str(root / "model-cache" / "weights.safetensors"),
                },
                "command": [str(root / "private-python"), "worker.py"],
            }
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.ai-bakeoff-run.v1",
                        "status": "complete",
                        "run_id": "severe-fixture",
                        "backend": "muscriptor",
                        "elapsed_seconds": 2.5,
                        "note_count": len(notes),
                        "source": _record(source),
                        "worker": _record(worker),
                        "request": request,
                        "execution": execution,
                        "checkpoint": {
                            **_record(checkpoint),
                            "variant": "small",
                            "config": _record(config),
                        },
                        "artifacts": artifacts,
                    }
                ),
                encoding="utf-8",
            )

            catalog = build_workbench_catalog(project, candidate_roots=[run_dir.parent])
            discovered = catalog["stems"][0]["candidates"][0]
            self.assertTrue(discovered["audition_blocked"])
            self.assertTrue(discovered["diagnostic_only"])
            self.assertIn(
                "extreme-onset-burst", discovered["ai_diagnostics"]["severe_codes"]
            )
            self.assertFalse(discovered["ai_diagnostics"]["audition_safe"])
            self.assertEqual(
                discovered["ai_diagnostics"]["source_audio_sha256"],
                _record(source)["sha256"],
            )
            rendered = json.dumps(public_catalog(catalog))
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("cwd", rendered)
            self.assertNotIn("private-python", rendered)
            self.assertEqual(
                discovered["ai_diagnostics"]["execution"]["diagnostic"],
                {"safe_value": "retained"},
            )
            self.assertIn(
                "AI transcription diagnostics",
                Path("src/sunofriend/workbench.html").read_text(encoding="utf-8"),
            )

            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            with self.assertRaisesRegex(ValueError, "diagnostic-only"):
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": discovered["candidate_id"],
                        "decision": "main",
                        "context": "solo",
                        "problem_tags": [],
                    },
                )

            legacy_state = {
                "stems": {
                    stem["stem_id"]: {
                        "main_candidate_id": discovered["candidate_id"],
                        "candidates": {
                            discovered["candidate_id"]: {"decision": "main"}
                        },
                    }
                }
            }
            workbench_artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            with self.assertRaisesRegex(ValueError, "diagnostic-only"):
                workbench_artifacts.render_arrangement(catalog, legacy_state)

            run_path = run_dir / "run.json"
            run_document = json.loads(run_path.read_text(encoding="utf-8"))
            decoy_candidate = run_dir / "candidate-decoy.json"
            decoy_candidate.write_bytes((run_dir / "candidate.json").read_bytes())
            run_document["artifacts"]["candidate.json"] = _record(
                decoy_candidate, relative=True
            )
            run_path.write_text(json.dumps(run_document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact path disagrees"):
                build_workbench_catalog(project, candidate_roots=[run_dir.parent])

            run_document["artifacts"]["candidate.json"] = _record(
                run_dir / "candidate.json", relative=True
            )
            del run_document["artifacts"]["candidate.json"]
            run_path.write_text(json.dumps(run_document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not pin candidate.json"):
                build_workbench_catalog(project, candidate_roots=[run_dir.parent])

    def test_catalog_reports_only_verified_application_cache_miss_and_hit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Cache Song-B minor-120bpm-440hz"
            candidates = root / "candidate-runs"
            project.mkdir()
            candidates.mkdir()
            (project / "Cache Song-bass-B minor-120bpm-440hz.wav").write_bytes(
                b"RIFF-project-source"
            )
            miss_dir = candidates / "bass-cache-miss"
            hit_dir = candidates / "bass-cache-hit"
            _write_workbench_ai_run(
                miss_dir, source_payload=b"RIFF-cache-source", velocity=70
            )
            _add_workbench_cache_evidence(miss_dir, hit=False)
            _write_workbench_ai_run(
                hit_dir, source_payload=b"RIFF-cache-source", velocity=71
            )
            _add_workbench_cache_evidence(hit_dir, hit=True)

            catalog = build_workbench_catalog(project, candidate_roots=[candidates])
            diagnostics = {
                candidate["ai_diagnostics"]["run_id"]: candidate["ai_diagnostics"]
                for candidate in catalog["stems"][0]["candidates"]
            }
            miss = diagnostics["origin-fixture-70"]
            self.assertEqual(miss["application_cache_status"], "miss-stored")
            self.assertFalse(miss["application_cache_hit"])
            self.assertEqual(miss["runtime_semantics"], "pipeline")
            self.assertEqual(miss["worker_execution_mode"], "fresh-subprocess")
            self.assertTrue(miss["worker_process_started_for_run"])
            self.assertTrue(miss["inference_executed_for_run"])
            self.assertTrue(miss["model_loaded_for_run"])

            hit = diagnostics["origin-fixture-71"]
            self.assertEqual(hit["application_cache_status"], "verified-hit")
            self.assertTrue(hit["application_cache_hit"])
            self.assertEqual(hit["runtime_semantics"], "pipeline-not-inference")
            self.assertEqual(
                hit["worker_execution_mode"], "application-cache-hit"
            )
            self.assertFalse(hit["worker_process_started_for_run"])
            self.assertFalse(hit["inference_executed_for_run"])
            self.assertFalse(hit["model_loaded_for_run"])

    def test_catalog_rejects_tampered_application_cache_hit_evidence(self) -> None:
        for tamper in ("summary-hit-flag", "event-inference-flag"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                project = root / "Cache Song-B minor-120bpm-440hz"
                candidates = root / "candidate-runs"
                project.mkdir()
                candidates.mkdir()
                (project / "Cache Song-bass-B minor-120bpm-440hz.wav").write_bytes(
                    b"RIFF-project-source"
                )
                run_dir = candidates / "bass-cache-hit"
                _write_workbench_ai_run(
                    run_dir, source_payload=b"RIFF-cache-source", velocity=72
                )
                _add_workbench_cache_evidence(run_dir, hit=True)

                if tamper == "summary-hit-flag":
                    run_path = run_dir / "run.json"
                    run = json.loads(run_path.read_text(encoding="utf-8"))
                    run["application_cache"]["application_cache_hit"] = False
                    run_path.write_text(json.dumps(run), encoding="utf-8")
                else:
                    event_path = run_dir / "cache.performance.json"
                    event = json.loads(event_path.read_text(encoding="utf-8"))
                    event["inference_executed_for_run"] = True
                    event_path.write_text(json.dumps(event), encoding="utf-8")
                    _refresh_workbench_run_artifact(
                        run_dir, "cache.performance.json"
                    )

                with self.assertRaisesRegex(ValueError, "application-cache"):
                    build_workbench_catalog(project, candidate_roots=[candidates])


class WorkbenchStoreTests(unittest.TestCase):
    def test_events_are_append_only_restore_state_and_redact_contribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            database = root / "state" / "workbench.sqlite3"
            store = WorkbenchStore(database)
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            first = store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": ["missing_notes"],
                    "notes": "private note that must not be contributed",
                },
            )

            reopened = WorkbenchStore(database)
            state = reopened.current_state(catalog)
            saved = state["stems"][stem["stem_id"]]["candidates"][
                candidate["candidate_id"]
            ]
            self.assertEqual(saved["decision"], "main")
            self.assertEqual(
                state["stems"][stem["stem_id"]]["main_candidate_id"],
                candidate["candidate_id"],
            )
            self.assertEqual(state["event_count"], 1)

            reopened.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "needs_correction",
                    "context": "full_mix",
                    "problem_tags": ["wrong_pitch_or_octave"],
                    "notes": "second private note",
                },
            )
            events = reopened.events(catalog["project_id"])
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_id"], first["event_id"])
            self.assertEqual(events[0]["payload"]["decision"], "main")
            latest = reopened.current_state(catalog)["stems"][stem["stem_id"]]
            self.assertEqual(
                latest["candidates"][candidate["candidate_id"]]["decision"],
                "needs_correction",
            )
            self.assertIsNone(latest["main_candidate_id"])

            review = reopened.export_review(catalog)
            preview = json.dumps(review["contribution_preview"])
            self.assertNotIn(str(root), preview)
            self.assertNotIn("private note", preview)
            self.assertFalse(review["contribution_preview"]["submission_enabled"])
            self.assertEqual(
                review["contribution_preview"]["decision_event_count"], 2
            )

    def test_terminal_outcome_suppresses_prior_selection_without_deleting_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _two_candidate_catalog(root)
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            first, second = stem["candidates"]

            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": first["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": second["candidate_id"],
                    "decision": "optional",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "stem_outcome",
                    "stem_id": stem["stem_id"],
                    "outcome": "none_usable",
                    "context": "solo",
                },
            )

            current = store.current_state(catalog)
            stem_state = current["stems"][stem["stem_id"]]

            self.assertEqual(len(store.events(catalog["project_id"])), 3)
            self.assertEqual(stem_state["outcome"]["value"], "none_usable")
            self.assertIsNone(stem_state["main_candidate_id"])
            self.assertFalse(
                stem_state["candidates"][first["candidate_id"]]["selection_active"]
            )
            self.assertFalse(
                stem_state["candidates"][second["candidate_id"]]["selection_active"]
            )
            self.assertEqual(selected_candidates(catalog, current), [])
            plan = WorkbenchArtifacts(root / "state" / "artifacts").garageband_pack_plan(
                catalog, current
            )
            self.assertEqual(plan["block_reasons"], ["no-selected-midi"])

    def test_only_later_explicit_selection_crosses_terminal_outcome_barrier(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _two_candidate_catalog(root)
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            first, second = stem["candidates"]

            for request in (
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": second["candidate_id"],
                    "decision": "optional",
                    "context": "solo",
                    "problem_tags": [],
                },
                {
                    "event_type": "stem_outcome",
                    "stem_id": stem["stem_id"],
                    "outcome": "cannot_tell",
                    "context": "solo",
                },
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": first["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                },
            ):
                store.append(catalog, request)

            current = store.current_state(catalog)
            state = current["stems"][stem["stem_id"]]
            selected = selected_candidates(catalog, current)

            self.assertIsNone(state["outcome"])
            self.assertTrue(
                state["candidates"][first["candidate_id"]]["selection_active"]
            )
            self.assertFalse(
                state["candidates"][second["candidate_id"]]["selection_active"]
            )
            self.assertEqual(
                [(row["candidate_id"], row["decision"]) for row in selected],
                [(first["candidate_id"], "main")],
            )

    def test_reject_does_not_clear_terminal_outcome_but_equivalent_keeps_selection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _two_candidate_catalog(root)
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            first, second = stem["candidates"]

            store.append(
                catalog,
                {
                    "event_type": "stem_outcome",
                    "stem_id": stem["stem_id"],
                    "outcome": "none_usable",
                    "context": "solo",
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": second["candidate_id"],
                    "decision": "reject",
                    "context": "solo",
                    "problem_tags": ["none_match"],
                },
            )
            rejected = store.current_state(catalog)
            self.assertEqual(
                rejected["stems"][stem["stem_id"]]["outcome"]["value"],
                "none_usable",
            )
            self.assertEqual(selected_candidates(catalog, rejected), [])

            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": first["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "stem_outcome",
                    "stem_id": stem["stem_id"],
                    "outcome": "equivalent",
                    "context": "solo",
                },
            )
            equivalent = store.current_state(catalog)
            self.assertEqual(
                equivalent["stems"][stem["stem_id"]]["outcome"]["value"],
                "equivalent",
            )
            self.assertEqual(len(selected_candidates(catalog, equivalent)), 1)

    def test_review_context_is_private_pinned_and_prompt_change_hides_old_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Context Song-B minor-113bpm-440hz"
            candidates = root / "outputs"
            project.mkdir()
            candidates.mkdir()
            source = project / "Context Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-context-source")
            midi = candidates / "bass.mid"
            _write_midi(midi, pitch=38)
            document = root / "catalog.json"

            def catalog_for(question: str) -> dict:
                document.write_text(
                    json.dumps(
                        {
                            "schema": "sunofriend.workbench-catalog.v1",
                            "stems": [
                                {
                                    "source": str(source),
                                    "role": "bass",
                                    "review_question": question,
                                    "listening_focus": [
                                        "recognisable bass line",
                                        "pluck leakage",
                                    ],
                                    "candidates": [{"midi": str(midi)}],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return build_workbench_catalog(
                    project,
                    candidate_roots=[candidates],
                    catalog_path=document,
                )

            first = catalog_for("Does this preserve the bass body?")
            first_stem = first["stems"][0]
            candidate = first_stem["candidates"][0]
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            event = store.append(
                first,
                {
                    "event_type": "candidate_decision",
                    "stem_id": first_stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                },
            )
            self.assertEqual(
                event["payload"]["review_context"],
                {
                    "sha256": first_stem["review_context_sha256"],
                    "review_question": "Does this preserve the bass body?",
                    "listening_focus": [
                        "recognisable bass line",
                        "pluck leakage",
                    ],
                },
            )
            private = store.export_review(first)
            self.assertEqual(
                private["project"]["review_contexts"],
                [
                    {
                        "stem_id": first_stem["stem_id"],
                        "review_context_sha256": first_stem[
                            "review_context_sha256"
                        ],
                        "review_question": "Does this preserve the bass body?",
                        "listening_focus": [
                            "recognisable bass line",
                            "pluck leakage",
                        ],
                    }
                ],
            )
            contribution = json.dumps(private["contribution_preview"])
            self.assertNotIn("Does this preserve", contribution)
            self.assertNotIn("recognisable bass line", contribution)
            self.assertNotIn("pluck leakage", contribution)

            changed = catalog_for("Does this preserve the plucked line?")
            changed_stem = changed["stems"][0]
            self.assertNotEqual(first_stem["stem_id"], changed_stem["stem_id"])
            changed_state = store.current_state(changed)
            self.assertEqual(changed_state["event_count"], 0)
            self.assertEqual(
                changed_state["stems"][changed_stem["stem_id"]]["candidates"],
                {},
            )
            changed_review = store.export_review(changed)
            self.assertEqual(changed_review["status"], "in_progress")
            self.assertEqual(
                changed_review["contribution_preview"]["decision_event_count"],
                0,
            )


class WorkbenchServerTests(unittest.TestCase):
    def test_candidate_display_identity_is_primary_first_and_never_reused(self) -> None:
        candidates = [
            {"candidate_id": "diagnostic", "primary": False},
            {"candidate_id": "primary-1", "primary": True},
            {"candidate_id": "primary-2", "primary": True},
            {"candidate_id": "primary-3", "primary": True},
            *(
                {"candidate_id": f"advanced-{index}", "primary": False}
                for index in range(23)
            ),
        ]

        displayed = _display_candidates(candidates)

        self.assertEqual(
            [candidate["candidate_id"] for candidate in displayed[:4]],
            ["primary-1", "primary-2", "primary-3", "diagnostic"],
        )
        self.assertEqual(
            [candidate["display_letter"] for candidate in displayed[:4]],
            ["A", "B", "C", "D"],
        )
        self.assertEqual(displayed[25]["display_letter"], "Z")
        self.assertEqual(displayed[26]["display_letter"], "AA")
        self.assertNotIn("display_letter", candidates[0])

    def test_static_ui_explains_overlap_confirmation_and_export_gate(self) -> None:
        page = Path("src/sunofriend/workbench.html").read_text(encoding="utf-8")

        self.assertIn("Possible doubled musical line", page)
        self.assertIn("intentional layering, thickening or flamming", page)
        self.assertIn("Confirm intentional layer", page)
        self.assertIn(
            "Handoff is blocked until every substantially overlapping selected part",
            page,
        )
        self.assertIn("function handoffOverlapBlocked()", page)
        self.assertIn("project.selected_midi_overlap?.pairs||[]", page)
        self.assertIn("No reviewable stems found.", page)
        self.assertIn("No parts are selected yet.", page)
        self.assertIn("Multiple methods, one musical decision.", page)
        self.assertIn("Visual result explorer", page)
        self.assertIn("never ranks, selects, merges or repairs", page)
        self.assertIn("/api/timeline?", page)
        self.assertIn("candidate_id=${encodeURIComponent(id)}", page)
        self.assertIn("Array.isArray(source.tracks)", page)
        self.assertIn("Displaying a lane is not recorded as feedback.", page)
        self.assertIn("function drawTimeline(stem,timeline)", page)
        self.assertIn("function seekTimeline(canvas,clientX)", page)
        self.assertIn("function updateTimelinePlayhead()", page)
        self.assertIn("function timelineNoteCountLabel(candidate)", page)
        self.assertIn("note count unavailable", page)
        self.assertIn("candidate?.display_letter", page)
        self.assertIn("candidateCard(stem,candidate,state)", page)
        self.assertIn("playhead=start}updateTimelinePlayhead()", page)
        self.assertNotIn("playhead=start}drawActiveTimeline()", page)
        self.assertIn("Alignment boundary:", page)
        self.assertIn("not proof that a candidate is aligned", page)
        self.assertIn("Selected arrangement explorer", page)
        self.assertIn("Visual and temporary audition controls only.", page)
        self.assertIn("/api/arrangement-timeline", page)
        self.assertIn("function drawArrangementTimeline(timeline)", page)
        self.assertIn("function arrangementSelectionMatches(timeline)", page)
        self.assertIn("requestId!==arrangementTimelineRequest", page)
        self.assertIn("arrangementTimeline=null;", page)
        self.assertIn("clearArrangementTimeline('Loading hash-verified", page)
        self.assertIn("changed in another Workbench tab", page)
        self.assertIn("function mixerEffectiveTracks()", page)
        self.assertIn("mixerFailedTracks.has(track.key)", page)
        self.assertIn("function mixerTrackFailed(track,error)", page)
        self.assertIn("Playback failed; press Play or reapply a preset", page)
        self.assertIn(
            "function applyMixerPreset(name){mixerFailedTracks.clear()",
            page,
        )
        self.assertIn(
            "function playMixer(){mixerFailedTracks.clear();updateMixerControls()",
            page,
        )
        self.assertIn(
            "find(audio=>audio&&!audio.paused&&!audio.ended)",
            page,
        )
        self.assertIn("function applyMixerPreset(name)", page)
        self.assertIn("function prepareMixerTracks(button)", page)
        self.assertIn("Source stems", page)
        self.assertIn("Selected MIDI", page)
        self.assertIn("Hybrid", page)
        self.assertIn("Main MIDI only", page)
        self.assertIn("are not sample-accurate", page)
        self.assertIn("Save after listening", page)
        self.assertIn("Compare methods", page)
        mixer_code = page.split("function arrangementExplorerPanel", 1)[1].split(
            "function renderArrangement()", 1
        )[0]
        self.assertNotIn("/api/events", mixer_code)
        self.assertNotIn("save(", mixer_code)
        self.assertIn("context:'full_mix'", page)

    def test_loopback_token_range_and_decision_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            server = create_workbench_server(
                catalog,
                state_dir=root / "state",
                token="test-token",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", "/api/project?token=wrong")
                self.assertEqual(connection.getresponse().status, 403)
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", "/?token=test-token")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                page = response.read().decode("utf-8")
                self.assertIn("Precise short-loop comparison", page)
                self.assertIn("Build GarageBand handoff", page)
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", "/api/project?token=test-token")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read())
                self.assertEqual(
                    payload["home"]["schema"], "sunofriend.workbench-home.v1"
                )
                self.assertEqual(
                    payload["home"]["next_step"]["action"], "compare-stem"
                )
                self.assertFalse(payload["home"]["effects"]["feedback_recorded"])
                self.assertNotIn(str(root), json.dumps(payload["home"]))
                overlap = payload["selected_midi_overlap"]
                self.assertEqual(
                    overlap["schema"],
                    "sunofriend.workbench-selected-midi-overlap.v1",
                )
                self.assertEqual(overlap["same_candidate_origin_pair_count"], 0)
                self.assertEqual(overlap["pairs"], [])
                stem = payload["stems"][0]
                candidate = stem["candidates"][0]
                self.assertEqual(candidate["display_letter"], "A")
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET", "/api/arrangement-timeline?token=test-token"
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                empty_arrangement_timeline = json.loads(response.read())
                self.assertEqual(
                    empty_arrangement_timeline["schema"],
                    "sunofriend.workbench-arrangement-timeline.v1",
                )
                self.assertEqual(
                    empty_arrangement_timeline["selected_midi_lane_count"], 0
                )
                self.assertEqual(empty_arrangement_timeline["source_lane_count"], 1)
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET",
                    "/api/timeline?stem_id="
                    + stem["stem_id"]
                    + "&token=test-token",
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                timeline = json.loads(response.read())
                self.assertEqual(
                    timeline["schema"], "sunofriend.workbench-timeline.v1"
                )
                self.assertEqual(timeline["stem_id"], stem["stem_id"])
                self.assertEqual(timeline["source"]["status"], "unavailable")
                self.assertEqual(timeline["candidates"][0]["note_count"], 1)
                self.assertEqual(
                    timeline["candidate_scope"]["mode"], "primary-default"
                )
                self.assertNotIn(str(root), json.dumps(timeline))
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET",
                    "/api/timeline?stem_id="
                    + stem["stem_id"]
                    + "&candidate_id="
                    + candidate["candidate_id"]
                    + "&token=test-token",
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                explicit_timeline = json.loads(response.read())
                self.assertEqual(
                    explicit_timeline["candidate_scope"]["mode"], "explicit"
                )
                self.assertEqual(
                    explicit_timeline["candidate_scope"]["source_projection"],
                    "reference-only",
                )
                self.assertEqual(
                    explicit_timeline["source"]["status"], "reference-only"
                )
                self.assertEqual(
                    explicit_timeline["candidates"][0]["candidate_id"],
                    candidate["candidate_id"],
                )
                connection.close()

                selection_body = json.dumps(
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "optional",
                        "context": "solo",
                        "problem_tags": [],
                    }
                )
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "POST",
                    "/api/events?token=test-token",
                    body=selection_body,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 201)
                response.read()
                connection.close()

                event_count = server.store.current_state(catalog)["event_count"]
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET", "/api/arrangement-timeline?token=test-token"
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                arrangement_timeline = json.loads(response.read())
                self.assertEqual(arrangement_timeline["selected_midi_lane_count"], 1)
                self.assertEqual(arrangement_timeline["midi_lanes"][0]["note_count"], 1)
                self.assertFalse(arrangement_timeline["effects"]["feedback_recorded"])
                self.assertNotIn(str(root), json.dumps(arrangement_timeline))
                self.assertEqual(
                    server.store.current_state(catalog)["event_count"], event_count
                )
                connection.close()

                role_body = json.dumps(
                    {
                        "event_type": "role_tag",
                        "stem_id": stem["stem_id"],
                        "role": "synth bass body",
                    }
                )
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "POST",
                    "/api/events?token=test-token",
                    body=role_body,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 201)
                role_saved = json.loads(response.read())
                self.assertEqual(
                    role_saved["home"]["stems"][0]["heard_role"],
                    "synth bass body",
                )
                self.assertNotIn(str(root), json.dumps(role_saved["home"]))
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET",
                    stem["source_url"],
                    headers={"Range": "bytes=0-3"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b"RIFF")
                connection.close()

                Path(catalog["stems"][0]["source_path"]).write_bytes(
                    b"RIFF-source-edited-after-launch"
                )
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", stem["source_url"])
                response = connection.getresponse()
                self.assertEqual(response.status, 409)
                self.assertIn("changed after it was catalogued", response.read().decode())
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET",
                    "/api/timeline?stem_id="
                    + stem["stem_id"]
                    + "&token=test-token",
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 409)
                self.assertIn("changed after it was catalogued", response.read().decode())
                connection.close()

                body = json.dumps(
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "optional",
                        "context": "full_mix",
                        "problem_tags": [],
                    }
                )
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "POST",
                    "/api/events?token=test-token",
                    body=body,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 201)
                saved = json.loads(response.read())
                self.assertEqual(saved["home"]["next_step"]["action"], "compose-pack")
                self.assertEqual(saved["home"]["counts"]["selected_part_count"], 1)
                self.assertEqual(
                    saved["state"]["stems"][stem["stem_id"]]["candidates"][
                        candidate["candidate_id"]
                    ]["decision"],
                    "optional",
                )
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


class WorkbenchArtifactTests(unittest.TestCase):
    def test_different_verified_ai_origins_in_one_review_row_do_not_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Origin Song-D minor-120bpm-440hz"
            runs = root / "runs"
            project.mkdir()
            runs.mkdir()
            review_source = project / "Origin Song-bass-D minor-120bpm-440hz.wav"
            review_source.write_bytes(b"RIFF-review-row-source")
            first_midi, first_origin = _write_workbench_ai_run(
                runs / "first-run",
                source_payload=b"RIFF-first-ai-source",
                velocity=80,
            )
            second_midi, second_origin = _write_workbench_ai_run(
                runs / "second-run",
                source_payload=b"RIFF-second-ai-source",
                velocity=81,
            )
            document = root / "catalog.json"
            document.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(review_source),
                                "role": "bass",
                                "candidates": [
                                    {"midi": str(first_midi)},
                                    {"midi": str(second_midi)},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[runs],
                catalog_path=document,
            )
            stem = catalog["stems"][0]
            first, second = stem["candidates"]
            self.assertEqual(
                first["ai_diagnostics"]["source_audio_sha256"], first_origin
            )
            self.assertEqual(
                second["ai_diagnostics"]["source_audio_sha256"], second_origin
            )
            self.assertNotEqual(first_origin, second_origin)
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for candidate, decision in ((first, "main"), (second, "optional")):
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": decision,
                        "context": "solo",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            selected = selected_candidates(catalog, current)

            self.assertEqual(
                {
                    item["candidate_origin_source_audio_sha256"]
                    for item in selected
                },
                {first_origin, second_origin},
            )
            self.assertEqual(
                {
                    item["candidate_origin_source_audio_sha256_basis"]
                    for item in selected
                },
                {"verified-ai-source"},
            )
            overlap = WorkbenchArtifacts(
                root / "state" / "artifacts"
            ).selected_midi_overlap(catalog, current)
            self.assertEqual(overlap["same_candidate_origin_pair_count"], 0)
            self.assertEqual(overlap["pairs"], [])

    def test_catalogued_midi_drift_blocks_preview_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                },
            )
            midi = Path(candidate["midi_path"])
            midi.write_bytes(midi.read_bytes() + b"changed")
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            with self.assertRaisesRegex(ValueError, "changed after it was catalogued"):
                artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            with self.assertRaisesRegex(ValueError, "changed after it was catalogued"):
                artifacts.build_garageband_handoff(
                    catalog, store.current_state(catalog)
                )

    def test_neutral_preview_is_cached_and_never_changes_original_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            original = Path(candidate["midi_path"]).read_bytes()
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as renderer:
                first = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
                second = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )

            self.assertEqual(renderer.call_count, 1)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["preview"]["sha256"], second["preview"]["sha256"])
            self.assertEqual(Path(candidate["midi_path"]).read_bytes(), original)
            cached = artifacts.cached_candidate_preview(
                catalog, stem["stem_id"], candidate["candidate_id"]
            )
            self.assertIsNotNone(cached)
            self.assertEqual(cached["policy"], "role-neutral-general-midi-v1")
            different_soundfont = root / "different.sf2"
            different_soundfont.write_bytes(b"different-test-soundfont")
            other_renderer = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=different_soundfont
            )
            self.assertIsNone(
                other_renderer.cached_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            )
            Path(second["preview"]["path"]).write_bytes(b"corrupt-cache")
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as recovery_renderer:
                recovered = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            self.assertEqual(recovery_renderer.call_count, 1)
            self.assertFalse(recovered["cache_hit"])
            self.assertEqual(recovered["preview"]["bytes"], 2052)

            soundfont.write_bytes(b"changed-soundfont")
            with self.assertRaisesRegex(ValueError, "SoundFont changed"):
                artifacts.cached_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            with self.assertRaisesRegex(ValueError, "SoundFont changed"):
                artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )

    def test_arrangement_and_handoff_include_only_explicit_usable_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _multi_stem_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            bass_stem = next(stem for stem in catalog["stems"] if stem["role"] == "bass")
            keys_stem = next(stem for stem in catalog["stems"] if stem["role"] == "keys")
            bass = bass_stem["candidates"][0]
            keys_optional = keys_stem["candidates"][0]
            keys_rejected = keys_stem["candidates"][1]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": bass_stem["stem_id"],
                    "candidate_id": bass["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                    "notes": "private bass note",
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": keys_stem["stem_id"],
                    "candidate_id": keys_optional["candidate_id"],
                    "decision": "optional",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": keys_stem["stem_id"],
                    "candidate_id": keys_rejected["candidate_id"],
                    "decision": "reject",
                    "context": "full_mix",
                    "problem_tags": ["extra_notes"],
                    "notes": "private rejected note",
                },
            )
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            current = store.current_state(catalog)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as renderer:
                arrangement = artifacts.render_arrangement(catalog, current)
                handoff = artifacts.build_garageband_handoff(catalog, current)
                repeated = artifacts.build_garageband_handoff(catalog, current)

            self.assertEqual(renderer.call_count, 1)
            self.assertEqual(arrangement["track_count"], 2)
            self.assertEqual(len(arrangement["selection"]), 2)
            self.assertEqual(
                arrangement["selected_midi_overlap"][
                    "same_candidate_origin_pair_count"
                ],
                0,
            )
            self.assertEqual(
                handoff["selected_midi_overlap"][
                    "same_candidate_origin_pair_count"
                ],
                0,
            )
            self.assertTrue(repeated["cache_hit"])
            with zipfile.ZipFile(handoff["zip"]["path"]) as archive:
                names = set(archive.namelist())
                self.assertIn("MIDI/01-bass-main.mid", names)
                self.assertIn("MIDI/02-keys-optional.mid", names)
                self.assertNotIn("MIDI/03-keys-reject.mid", names)
                self.assertEqual(
                    archive.read("MIDI/01-bass-main.mid"),
                    Path(bass["midi_path"]).read_bytes(),
                )
                self.assertEqual(
                    archive.read("MIDI/02-keys-optional.mid"),
                    Path(keys_optional["midi_path"]).read_bytes(),
                )
                manifest = archive.read(
                    "sunofriend-garageband-handoff.json"
                ).decode("utf-8")
                self.assertNotIn(str(root), manifest)
                self.assertNotIn("private bass note", manifest)
                self.assertNotIn("private rejected note", manifest)
                self.assertIn('"original_midi_mutated": false', manifest)

    def test_same_source_high_overlap_is_diagnostic_and_keeps_arrangement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _same_source_overlap_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stems = catalog["stems"]
            for stem in stems:
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "solo",
                        "problem_tags": [],
                        "notes": "private overlap review note",
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ):
                arrangement = artifacts.render_arrangement(catalog, current)

            diagnostic = arrangement["selected_midi_overlap"]
            self.assertEqual(
                diagnostic["schema"],
                "sunofriend.workbench-selected-midi-overlap.v1",
            )
            self.assertEqual(
                diagnostic["heuristic"]["policy"],
                "greedy-earliest-compatible-exact-pitch-onset-v1",
            )
            self.assertEqual(diagnostic["heuristic"]["onset_tolerance_ms"], 80)
            self.assertEqual(diagnostic["same_candidate_origin_pair_count"], 1)
            self.assertEqual(diagnostic["substantial_overlap_pair_count"], 1)
            pair = diagnostic["pairs"][0]
            self.assertEqual(pair["left_note_count"], 10)
            self.assertEqual(pair["right_note_count"], 10)
            self.assertEqual(pair["matched_note_count"], 10)
            self.assertEqual(pair["left_overlap_ratio"], 1.0)
            self.assertEqual(pair["right_overlap_ratio"], 1.0)
            self.assertTrue(pair["substantial_overlap"])
            self.assertFalse(pair["both_decisions_confirmed_in_full_mix"])
            self.assertEqual(pair["left"]["decision_context"], "solo")
            self.assertEqual(pair["right"]["decision_context"], "solo")
            self.assertEqual(
                pair["candidate_origin_source_audio_sha256"],
                stems[0]["source"]["sha256"],
            )
            selected = selected_candidates(catalog, current)
            self.assertEqual(len(selected), 2)
            self.assertEqual(
                {
                    item["candidate_origin_source_audio_sha256"]
                    for item in selected
                },
                {stems[0]["source"]["sha256"]},
            )
            self.assertEqual(
                {
                    item["candidate_origin_source_audio_sha256_basis"]
                    for item in selected
                },
                {"review-stem-source-fallback"},
            )
            self.assertEqual(
                {
                    item["candidate_origin_source_audio_sha256_basis"]
                    for item in arrangement["selection"]
                },
                {"review-stem-source-fallback"},
            )
            manifest_path = Path(arrangement["midi"]["path"]).parent / "manifest.json"
            manifest = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), manifest)
            self.assertNotIn("private overlap review note", manifest)
            self.assertNotIn("overlap-source.wav", manifest)

    def test_handoff_overlap_gate_requires_both_latest_full_mix_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _same_source_overlap_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            first_stem, second_stem = catalog["stems"]
            first_candidate = first_stem["candidates"][0]
            second_candidate = second_stem["candidates"][0]
            for stem, candidate, context in (
                (first_stem, first_candidate, "solo"),
                (second_stem, second_candidate, "full_mix"),
            ):
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": context,
                        "problem_tags": [],
                    },
                )
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ):
                solo_arrangement = artifacts.render_arrangement(
                    catalog, store.current_state(catalog)
                )
                with self.assertRaisesRegex(
                    ValueError, "review and save both choices in full_mix context"
                ):
                    artifacts.build_garageband_handoff(
                        catalog, store.current_state(catalog)
                    )

                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": first_stem["stem_id"],
                        "candidate_id": first_candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
                full_mix_state = store.current_state(catalog)
                full_mix_arrangement = artifacts.render_arrangement(
                    catalog, full_mix_state
                )
                handoff = artifacts.build_garageband_handoff(
                    catalog, full_mix_state
                )
                manifest_path = Path(handoff["zip"]["path"]).parent / "manifest.json"
                first_manifest = manifest_path.read_bytes()
                repeated_arrangement = artifacts.render_arrangement(
                    catalog, full_mix_state
                )
                repeated_handoff = artifacts.build_garageband_handoff(
                    catalog, full_mix_state
                )

            self.assertNotEqual(
                solo_arrangement["cache_key"], full_mix_arrangement["cache_key"]
            )
            self.assertTrue(repeated_arrangement["cache_hit"])
            self.assertTrue(repeated_handoff["cache_hit"])
            self.assertEqual(
                repeated_arrangement["cache_key"], full_mix_arrangement["cache_key"]
            )
            self.assertEqual(repeated_handoff["cache_key"], handoff["cache_key"])
            self.assertEqual(manifest_path.read_bytes(), first_manifest)
            diagnostic = handoff["selected_midi_overlap"]
            self.assertEqual(
                diagnostic["unconfirmed_substantial_overlap_pair_count"], 0
            )
            self.assertTrue(
                diagnostic["pairs"][0]["both_decisions_confirmed_in_full_mix"]
            )
            with zipfile.ZipFile(handoff["zip"]["path"]) as archive:
                portable_manifest = archive.read(
                    "sunofriend-garageband-handoff.json"
                ).decode("utf-8")
                self.assertNotIn(str(root), portable_manifest)
                self.assertIn(
                    '"both_decisions_confirmed_in_full_mix": true',
                    portable_manifest,
                )


def _write_explicit_split_catalog(
    path: Path,
    *,
    source: Path,
    candidate_root: Path,
    role: str,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": role,
                        "review_question": f"Does this MIDI isolate the {role}?",
                        "listening_focus": [
                            "recognisable line",
                            "leakage from the other role",
                        ],
                        "candidates": [
                            {"midi": str(candidate_root / "requested-label.mid")},
                            {
                                "midi": str(
                                    candidate_root
                                    / "unexpected-label-complement.mid"
                                )
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_ai_label_split_fixture(
    root: Path,
    *,
    label: str,
    selected_pitches: tuple[int, ...],
    complement_pitches: tuple[int, ...],
    simultaneous: bool = False,
) -> None:
    root.mkdir()
    selected_rows = _partition_rows(
        selected_pitches,
        instrument=label,
        first_source_index=0,
    )
    complement_rows = _partition_rows(
        complement_pitches,
        instrument="clean_electric_guitar",
        first_source_index=len(selected_rows),
    )
    if simultaneous:
        for row in [*selected_rows, *complement_rows]:
            row["note"]["start_seconds"] = 0.1
            row["note"]["end_seconds"] = 0.11
    selected_midi = root / "requested-label.mid"
    complement_midi = root / "unexpected-label-complement.mid"
    control_midi = root / "unchanged-full-candidate.mid"
    _write_partition_midi(selected_midi, selected_rows)
    _write_partition_midi(complement_midi, complement_rows)
    _write_partition_midi(control_midi, [*selected_rows, *complement_rows])
    source_request = root / "source-request.json"
    source_request.write_text(
        json.dumps(
            {
                "schema": "sunofriend.ai-transcription-request.v1",
                "audio_path": "/private/fixture-source.wav",
                "backend": "muscriptor",
                "roles": [label],
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "options": {},
            }
        ),
        encoding="utf-8",
    )
    source_candidate = root / "source-candidate.json"
    source_candidate.write_text(
        json.dumps(
            {
                "schema": "sunofriend.ai-transcription-candidate.v1",
                "backend": "muscriptor",
                "model_version": "muscriptor-test-small",
                "notes": [
                    row["note"] for row in [*selected_rows, *complement_rows]
                ],
                "warnings": [],
                "raw_artifacts": [],
                "metadata": {"excerpt": {"duration_seconds": 2.0}},
            }
        ),
        encoding="utf-8",
    )
    request_record = _record(source_request, relative=True)
    candidate_record = _record(source_candidate, relative=True)
    source_sha = hashlib.sha256(b"fixture-source-audio").hexdigest()
    candidate_midi_record = _record(control_midi, relative=True)
    embedded_bpm = 60_000_000.0 / round(60_000_000.0 / 113.0)
    render_contract = {
        "policy": "deterministic-midi-audition-v1",
        "purpose": "audition-only; label-partition.json is the exact event record",
        "ticks_per_beat": 480,
        "tempo_input_bpm": 113.0,
        "embedded_bpm": embedded_bpm,
        "pitch_quantization": (
            "nearest integer via Python round (ties to even), clamped 0..127"
        ),
        "time_quantization": (
            "nearest 1/480 quarter-note tick via Python round (ties to even)"
        ),
        "minimum_duration_ticks": 1,
        "duplicate_onset_policy": (
            "same track/channel/pitch/tick collapses to longest end and greatest velocity"
        ),
        "same_pitch_overlap_policy": (
            "an earlier note ends at the next onset on the same track/channel/pitch"
        ),
        "velocity_policy": "fixed-fixture-velocity",
    }
    partition = {
        "schema": "sunofriend.ai-label-partition.v1",
        "source_request_sha256": request_record["sha256"],
        "source_candidate_sha256": candidate_record["sha256"],
        "source_candidate_midi_sha256": candidate_midi_record["sha256"],
        "source_audio_sha256": source_sha,
        "label": label,
        "velocity_policy": "fixed-fixture-velocity",
        "render_contract": render_contract,
        "source_note_count": len(selected_rows) + len(complement_rows),
        "selected": selected_rows,
        "complement": complement_rows,
        "partition": {
            "disjoint": True,
            "exhaustive": True,
            "source_indices_changed": 0,
            "source_events_deleted": 0,
            "source_events_duplicated": 0,
        },
    }
    partition_path = root / "label-partition.json"
    partition_path.write_text(json.dumps(partition), encoding="utf-8")
    detected_counts = {
        name: count
        for name, count in (
            (label, len(selected_rows)),
            ("clean_electric_guitar", len(complement_rows)),
        )
        if count
    }
    report = {
        "schema": "sunofriend.ai-label-split.v1",
        "status": "review-required" if selected_rows else "no-evidence",
        "operation": "ai-label-split",
        "label": label,
        "bpm": 113.0,
        "source_run": {
            "run_id": "verified-label-split-fixture",
            "backend": "muscriptor",
            "model_version": "muscriptor-test-small",
            "source": {"bytes": 20, "sha256": source_sha},
            "checkpoint": {"sha256": "fixture-checkpoint-sha256"},
            "execution": {"model_size": "small", "beam_size": 1},
            "request": {
                "roles": [label],
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "sha256": request_record["sha256"],
            },
            "candidate": {
                "bytes": candidate_record["bytes"],
                "sha256": candidate_record["sha256"],
            },
            "candidate_midi": {
                "bytes": candidate_midi_record["bytes"],
                "sha256": candidate_midi_record["sha256"],
            },
            "duration_seconds": 2.0,
        },
        "evidence": {
            "detected_label_counts": detected_counts,
            "selected_note_count": len(selected_rows),
            "complement_note_count": len(complement_rows),
            "selected_source_indices": [
                row["source_index"] for row in selected_rows
            ],
            "complement_source_indices": [
                row["source_index"] for row in complement_rows
            ],
            "selection_policy": "exact-model-reported-instrument-label",
            "physical_instrument_identified": False,
        },
        "artifacts": {
            control_midi.name: candidate_midi_record,
            source_candidate.name: candidate_record,
            source_request.name: request_record,
            selected_midi.name: _record(selected_midi, relative=True),
            complement_midi.name: _record(complement_midi, relative=True),
            partition_path.name: _record(partition_path, relative=True),
        },
        "effects": {
            "automatic_promotion": False,
            "model_rerun": False,
            "source_run_mutated": False,
            "raw_candidate_mutated": False,
            "source_midi_mutated": False,
            "source_partition_events_deleted": 0,
            "source_partition_events_duplicated": 0,
            "source_request_control_byte_identical": True,
            "source_candidate_control_byte_identical": True,
            "unchanged_control_byte_identical": True,
            "selected_audition_velocities_written": len(selected_rows),
            "midi_rendering": {
                selected_midi.name: _fixture_render_summary(
                    selected_midi, selected_rows, bpm=113.0
                ),
                complement_midi.name: _fixture_render_summary(
                    complement_midi, complement_rows, bpm=113.0
                ),
            },
        },
        "warnings": [
            "The split follows model-reported labels only and requires listening."
        ],
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (root / "ai_label_split.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def _fixture_render_summary(path: Path, rows: list[dict], *, bpm: float) -> dict:
    from sunofriend.clip import read_midi_clips

    seconds_per_tick = 60.0 / (bpm * 480.0)
    onset_quantized = end_quantized = duration_quantized = 0
    for row in rows:
        note = row["note"]
        start_tick = round(float(note["start_seconds"]) * bpm * 480.0 / 60.0)
        end_tick = round(float(note["end_seconds"]) * bpm * 480.0 / 60.0)
        if abs(start_tick * seconds_per_tick - note["start_seconds"]) > 1e-12:
            onset_quantized += 1
        if abs(end_tick * seconds_per_tick - note["end_seconds"]) > 1e-12:
            end_quantized += 1
        if (
            abs(
                (end_tick - start_tick) * seconds_per_tick
                - (note["end_seconds"] - note["start_seconds"])
            )
            > 1e-12
        ):
            duration_quantized += 1
    clips = read_midi_clips(path)
    rendered_signatures = [
        {
            "track_index": owner,
            "channel": clip.instrument.channel,
            "start_tick": round(note.start_beat * 480),
            "end_tick": round(note.end_beat * 480),
            "pitch": note.pitch,
            "velocity": note.velocity,
        }
        for owner, clip in enumerate(clips)
        for note in clip.notes
    ]
    rendered_count = len(rendered_signatures)
    pitch_quantized = sum(
        float(round(row["note"]["pitch"])) != row["note"]["pitch"]
        for row in rows
    )
    minimum_extended = sum(
        round(row["note"]["end_seconds"] * bpm * 480.0 / 60.0)
        <= round(row["note"]["start_seconds"] * bpm * 480.0 / 60.0)
        for row in rows
    )
    keys = [
        (
            round(row["note"]["pitch"]),
            round(row["note"]["start_seconds"] * bpm * 480.0 / 60.0),
        )
        for row in rows
    ]
    duplicate_collapsed = len(keys) - len(set(keys))
    overlap_truncated = 0
    by_pitch: dict[int, list[tuple[int, int]]] = {}
    for row in rows:
        note = row["note"]
        pitch = round(note["pitch"])
        by_pitch.setdefault(pitch, []).append(
            (
                round(note["start_seconds"] * bpm * 480.0 / 60.0),
                max(
                    round(note["end_seconds"] * bpm * 480.0 / 60.0),
                    round(note["start_seconds"] * bpm * 480.0 / 60.0) + 1,
                ),
            )
        )
    for events in by_pitch.values():
        unique = {}
        for start, end in events:
            unique[start] = max(unique.get(start, end), end)
        ordered = sorted(unique.items())
        overlap_truncated += sum(
            left_end > right_start
            for (_, left_end), (right_start, _) in zip(ordered, ordered[1:])
        )
    changed = any(
        (
            pitch_quantized,
            onset_quantized,
            end_quantized,
            duration_quantized,
            minimum_extended,
            duplicate_collapsed,
            overlap_truncated,
        )
    )
    return {
        "source_event_count": len(rows),
        "rendered_midi_note_count": rendered_count,
        "rendered_midi_note_signatures": rendered_signatures,
        "integer_pitch_quantized_event_count": pitch_quantized,
        "onset_tick_quantized_event_count": onset_quantized,
        "end_tick_quantized_event_count": end_quantized,
        "duration_tick_quantized_event_count": duration_quantized,
        "minimum_duration_extended_event_count": minimum_extended,
        "duplicate_same_pitch_tick_onset_collapsed_event_count": duplicate_collapsed,
        "same_pitch_overlap_truncated_event_count": overlap_truncated,
        "source_event_to_midi_note_count_delta": rendered_count - len(rows),
        "lossless_event_render": not changed,
    }


def _read_split_report(root: Path) -> dict:
    return json.loads((root / "ai_label_split.json").read_text(encoding="utf-8"))


def _read_split_partition(root: Path) -> dict:
    return json.loads((root / "label-partition.json").read_text(encoding="utf-8"))


def _rewrite_split_documents(
    root: Path, *, report: dict, partition: dict
) -> None:
    partition_path = root / "label-partition.json"
    partition_path.write_text(json.dumps(partition), encoding="utf-8")
    report["artifacts"][partition_path.name] = _record(
        partition_path, relative=True
    )
    report.pop("report_sha256", None)
    report["report_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (root / "ai_label_split.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def _partition_rows(
    pitches: tuple[int, ...],
    *,
    instrument: str,
    first_source_index: int,
) -> list[dict]:
    rows = []
    for offset, pitch in enumerate(pitches):
        source_index = first_source_index + offset
        start = 0.1 + source_index * 0.35
        rows.append(
            {
                "source_index": source_index,
                "source_event_id": f"fixture-{source_index}",
                "note": {
                    "start_seconds": start,
                    "end_seconds": start + 0.25,
                    "pitch": float(pitch),
                    "confidence": None,
                    "instrument": instrument,
                    "velocity": None,
                    "source_event_id": f"fixture-{source_index}",
                },
                "audition_velocity": 90,
            }
        )
    return rows


def _write_partition_midi(path: Path, rows: list[dict]) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name="Label split fixture",
                channel=0,
                program=38,
                notes=[
                    NoteEvent(
                        start=float(row["note"]["start_seconds"]),
                        end=float(row["note"]["end_seconds"]),
                        pitch=int(row["note"]["pitch"]),
                        velocity=int(row["audition_velocity"]),
                    )
                    for row in rows
                ],
            )
        ],
        bpm=113.0,
    )


def _small_catalog(root: Path) -> dict:
    project = root / "Small Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    (project / "Small Song-bass-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-source-audio"
    )
    midi = candidates / "bass_listened.mid"
    _write_midi(midi, pitch=38)
    midi.with_suffix(".preview.wav").write_bytes(b"RIFF-preview-audio")
    return build_workbench_catalog(project, candidate_roots=[candidates])


def _two_candidate_catalog(root: Path) -> dict:
    project = root / "Barrier Song-D minor-120bpm-440hz"
    candidates = root / "barrier-candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Barrier Song-bass-D minor-120bpm-440hz.wav"
    source.write_bytes(b"RIFF-barrier-source")
    first = candidates / "bass-first.mid"
    second = candidates / "bass-second.mid"
    _write_midi(first, pitch=38)
    _write_midi(second, pitch=41)
    document = root / "barrier-catalog.json"
    document.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "bass",
                        "candidates": [
                            {"midi": str(first)},
                            {"midi": str(second)},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return build_workbench_catalog(
        project,
        candidate_roots=[candidates],
        catalog_path=document,
    )


def _write_midi(path: Path, *, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name="Bass",
                channel=0,
                program=38,
                notes=[NoteEvent(start=0.0, end=0.5, pitch=pitch, velocity=90)],
            )
        ],
        bpm=120.0,
    )


def _multi_stem_catalog(root: Path) -> dict:
    project = root / "Multi Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    (project / "Multi Song-bass-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-bass-source"
    )
    (project / "Multi Song-keys-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-keys-source"
    )
    _write_midi(candidates / "bass_listened.mid", pitch=38)
    _write_midi(candidates / "keys_listened.mid", pitch=60)
    _write_midi(candidates / "keys_cleanup.mid", pitch=64)
    return build_workbench_catalog(project, candidate_roots=[candidates])


def _same_source_overlap_catalog(root: Path) -> dict:
    project = root / "Overlap Song-D minor-120bpm-440hz"
    candidates = root / "overlap-candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "overlap-source.wav"
    source.write_bytes(b"RIFF-one-shared-source")
    body_midi = candidates / "bass-body.mid"
    pluck_midi = candidates / "pluck-line.mid"
    _write_overlap_midi(body_midi, onset_shift=0.0)
    _write_overlap_midi(pluck_midi, onset_shift=0.04)
    catalog_path = root / "overlap-catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "bass body",
                        "candidates": [{"midi": str(body_midi)}],
                    },
                    {
                        "source": str(source),
                        "role": "pluck",
                        "candidates": [{"midi": str(pluck_midi)}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return build_workbench_catalog(
        project,
        candidate_roots=[candidates],
        catalog_path=catalog_path,
    )


def _write_overlap_midi(path: Path, *, onset_shift: float) -> None:
    notes = []
    for index in range(10):
        start = 0.2 + index * 0.25 + onset_shift
        notes.append(
            NoteEvent(
                start=start,
                end=start + 0.12,
                pitch=38 + index % 3,
                velocity=80 + index,
            )
        )
    write_midi_file(
        path,
        [MidiTrack(name="Overlap fixture", channel=0, program=38, notes=notes)],
        bpm=120.0,
    )


def _write_workbench_ai_run(
    run_dir: Path,
    *,
    source_payload: bytes,
    velocity: int,
) -> tuple[Path, str]:
    run_dir.mkdir()
    source = run_dir / "origin-source.wav"
    source.write_bytes(source_payload)
    checkpoint = run_dir / "model.safetensors"
    checkpoint.write_bytes(b"fixture-checkpoint")
    config = run_dir / "config.json"
    config.write_text(
        '{"model_type":"muscriptor","variant":"small"}', encoding="utf-8"
    )
    worker = run_dir / "worker.py"
    worker.write_text("# fixture worker\n", encoding="utf-8")
    checkpoint_hash = _record(checkpoint)["sha256"]
    config_hash = _record(config)["sha256"]
    midi = run_dir / "candidate.mid"
    notes = [
        NoteEvent(
            start=0.2 + index * 0.25,
            end=0.32 + index * 0.25,
            pitch=38 + index % 3,
            velocity=velocity,
        )
        for index in range(10)
    ]
    write_midi_file(
        midi,
        [MidiTrack(name="AI origin fixture", channel=0, program=38, notes=notes)],
        bpm=120.0,
    )
    request = {
        "schema": "sunofriend.ai-transcription-request.v1",
        "audio_path": str(source.resolve()),
        "backend": "muscriptor",
        "roles": ["electric_bass"],
        "start_seconds": 0.0,
        "end_seconds": 3.0,
        "options": {
            "model_sha256": checkpoint_hash,
            "model_config_sha256": config_hash,
        },
    }
    candidate = {
        "schema": "sunofriend.ai-transcription-candidate.v1",
        "backend": "muscriptor",
        "model_version": "muscriptor-test-small",
        "notes": [
            {
                "start_seconds": note.start,
                "end_seconds": note.end,
                "pitch": float(note.pitch),
                "confidence": None,
                "instrument": "electric_bass",
                "velocity": None,
                "source_event_id": str(index),
            }
            for index, note in enumerate(notes)
        ],
        "warnings": [],
        "raw_artifacts": [],
        "metadata": {
            "checkpoint_sha256": checkpoint_hash,
            "excerpt": {"duration_seconds": 3.0},
        },
    }
    (run_dir / "request.json").write_text(
        json.dumps(request), encoding="utf-8"
    )
    for name in ("candidate.json", "candidate.raw.json"):
        (run_dir / name).write_text(json.dumps(candidate), encoding="utf-8")
    artifact_names = (
        "request.json",
        "candidate.raw.json",
        "candidate.json",
        "candidate.mid",
    )
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": "sunofriend.ai-bakeoff-run.v1",
                "status": "complete",
                "run_id": f"origin-fixture-{velocity}",
                "backend": "muscriptor",
                "elapsed_seconds": 1.0,
                "note_count": len(notes),
                "source": _record(source),
                "worker": _record(worker),
                "request": request,
                "checkpoint": {
                    **_record(checkpoint),
                    "variant": "small",
                    "config": _record(config),
                },
                "artifacts": {
                    name: _record(run_dir / name, relative=True)
                    for name in artifact_names
                },
            }
        ),
        encoding="utf-8",
    )
    return midi, _record(source)["sha256"]


def _add_workbench_cache_evidence(run_dir: Path, *, hit: bool) -> None:
    for name in ("candidate.json", "candidate.raw.json"):
        path = run_dir / name
        candidate = json.loads(path.read_text(encoding="utf-8"))
        candidate["raw_artifacts"] = ["muscriptor.performance.json"]
        path.write_text(json.dumps(candidate), encoding="utf-8")

    performance_path = run_dir / "muscriptor.performance.json"
    performance_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.muscriptor-performance.v1",
                "measurement_mode": "fresh-process",
                "timings_seconds": {"worker_total": 0.4},
            }
        ),
        encoding="utf-8",
    )
    key_sha256 = hashlib.sha256(b"workbench-cache-key").hexdigest()
    scope = "exact-muscriptor-raw-worker-result-v1"
    entry_path = run_dir / "cache.entry.json"
    entry_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.ai-transcription-cache-entry.v1",
                "status": "complete",
                "scope": scope,
                "key_sha256": key_sha256,
                "artifacts": {
                    "candidate.raw.json": _record(
                        run_dir / "candidate.raw.json", relative=True
                    ),
                    "muscriptor.performance.json": _record(
                        performance_path, relative=True
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    status = "verified-hit" if hit else "miss-stored"
    published = not hit
    worker_ran = not hit
    timings = {
        "identity_and_preflight": 0.05,
        "lookup": 0.02,
        "materialise": 0.03 if hit else None,
        "worker_subprocess": None if hit else 0.4,
        "store": None if hit else 0.03,
        "postprocess": 0.1,
        "pipeline_before_final_evidence": 0.3 if hit else 0.75,
    }
    entry_record = _record(entry_path, relative=True)
    event = {
        "schema": "sunofriend.ai-transcription-cache-event.v1",
        "status": "complete",
        "application_cache_status": status,
        "scope": scope,
        "key_sha256": key_sha256,
        "entry_manifest_sha256": entry_record["sha256"],
        "entry_manifest_bytes": entry_record["bytes"],
        "application_cache_hit": hit,
        "entry_published_by_run": published,
        "inference_executed_for_run": worker_ran,
        "worker_process_started_for_run": worker_ran,
        "model_loaded_for_run": worker_ran,
        "model_reused_from_prior_request": False,
        "fallback_to_inference_on_invalid_entry": False,
        "timings_seconds": timings,
        "run_origin_performance_matches_entry": True,
        "muscriptor_performance_is_current_run_inference": worker_ran,
        "error": None,
    }
    event_path = run_dir / "cache.performance.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")

    run_path = run_dir / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run.update(
        {
            "command": [] if hit else ["fixture-python", "worker.py"],
            "worker_execution_mode": (
                "application-cache-hit" if hit else "fresh-subprocess"
            ),
            "worker_process_started_for_run": worker_ran,
            "inference_executed_for_run": worker_ran,
            "model_loaded_for_run": worker_ran,
            "model_reused_from_prior_request": False,
            "worker_transport": None,
            "exit_code": None if hit else 0,
            "worker_subprocess_elapsed_seconds": None if hit else 0.4,
            "worker_request_elapsed_seconds": None,
            "application_cache": {
                name: event[name]
                for name in (
                    "schema",
                    "application_cache_status",
                    "scope",
                    "key_sha256",
                    "entry_manifest_sha256",
                    "application_cache_hit",
                    "entry_published_by_run",
                    "fallback_to_inference_on_invalid_entry",
                    "muscriptor_performance_is_current_run_inference",
                    "run_origin_performance_matches_entry",
                )
            },
        }
    )
    artifact_names = (
        "request.json",
        "candidate.raw.json",
        "candidate.json",
        "candidate.mid",
        "muscriptor.performance.json",
        "cache.entry.json",
        "cache.performance.json",
    )
    run["artifacts"] = {
        name: _record(run_dir / name, relative=True) for name in artifact_names
    }
    run_path.write_text(json.dumps(run), encoding="utf-8")


def _refresh_workbench_run_artifact(run_dir: Path, name: str) -> None:
    run_path = run_dir / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["artifacts"][name] = _record(run_dir / name, relative=True)
    run_path.write_text(json.dumps(run), encoding="utf-8")


def _fake_render(midi_path, wav_path, **_kwargs):
    del midi_path
    destination = Path(wav_path)
    destination.write_bytes(b"RIFF" + b"\0" * 2048)
    return destination


def _record(path: Path, *, relative: bool = False) -> dict:
    return {
        "path": path.name if relative else str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    unittest.main()
