from __future__ import annotations

import json
import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from sunofriend.beatgrid import Grid
from sunofriend.cli import main
from sunofriend.listen_all import (
    CHANNELS,
    CONSERVATIVE_ROLE_ENGINES,
    INSTRUMENT_SUGGESTIONS,
    _is_silent,
    run_listen_all,
)
from sunofriend.listen_all import _make_library_clip
from sunofriend.clip import KeySignature, read_midi_clips
from sunofriend.conversion import NoteProvenance
from sunofriend.library import ClipLibrary
from sunofriend.loop import RefineResult
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_store import WorkbenchStore


class ListenAllContractTests(unittest.TestCase):
    def test_keys_and_pads_use_distinct_preview_channels_and_programs(self):
        self.assertEqual(CHANNELS["keys"], (1, 7))
        self.assertEqual(CHANNELS["pads"], (6, 89))

    def test_broad_separator_roles_have_disclosed_engines_and_distinct_patches(self):
        self.assertEqual(
            CONSERVATIVE_ROLE_ENGINES,
            {
                "wind": "lead",
                "rhythm": "keys",
                "other": "synth",
            },
        )
        self.assertEqual(CHANNELS["wind"], (7, 71))
        self.assertEqual(CHANNELS["rhythm"], (8, 27))
        self.assertEqual(CHANNELS["other"], (10, 81))
        self.assertEqual(
            INSTRUMENT_SUGGESTIONS["wind"],
            ("Clarinet", "Brass Section"),
        )
        self.assertEqual(
            INSTRUMENT_SUGGESTIONS["rhythm"],
            ("Electric Guitar (clean)", "Acoustic Guitar (steel)"),
        )
        self.assertEqual(
            INSTRUMENT_SUGGESTIONS["other"],
            ("Flow Synth Pluck", "Synth Lead"),
        )

    def test_composite_drums_publishes_reviewable_channel_ten_family_midi_only(self):
        calls: list[tuple[str, str]] = []

        def fake_refine(**kwargs):
            stem = Path(kwargs["stem_path"])
            kind = kwargs["kind"]
            calls.append((stem.name, kind))
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            notes = [
                NoteEvent(0.0, 0.08, 36, 100),
                NoteEvent(0.5, 0.58, 38, 92),
            ]
            midi = work / f"{kind}_listened.mid"
            write_midi_file(
                midi,
                [MidiTrack(kind.title(), 9, 0, notes)],
                bpm=119,
            )
            provenance = [
                NoteProvenance.from_note(
                    notes[0],
                    origin="observed",
                    confidence=0.9,
                    family="kick_deep",
                    sources=("stem", "listen-other_kit"),
                ),
                NoteProvenance.from_note(
                    notes[1],
                    origin="observed",
                    confidence=0.85,
                    family="snare_body",
                    sources=("stem", "listen-other_kit"),
                ),
            ]
            return RefineResult(
                notes=notes,
                score=0.9,
                history=[],
                midi_path=midi,
                note_provenance=provenance,
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Composite-B major-119bpm-440hz"
            folder.mkdir()
            source = folder / "Composite-drums-B major-119bpm-440hz.wav"
            source.touch()
            out = root / "out"

            with patch(
                "sunofriend.listen_all._is_silent",
                return_value=False,
            ), patch(
                "sunofriend.loop.refine_stem",
                side_effect=fake_refine,
            ):
                summary = run_listen_all(
                    folder,
                    out,
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            self.assertEqual(calls, [(source.name, "other_kit")])
            self.assertEqual(summary["shadowed_roles"], [])
            self.assertEqual(
                summary["drum_role_policy"]["precedence"],
                "composite-review-required",
            )
            part = summary["parts"]["drums"]
            self.assertEqual(part["published_role"], "drums")
            self.assertEqual(part["processing_kind"], "other_kit")
            self.assertEqual(part["classifier_alias"], "other_kit")
            self.assertTrue(part["review_required"])
            self.assertTrue(part["midi_family_variants_only"])
            self.assertFalse(part["audio_children_created"])
            self.assertIn("dominant drum family", part["classification_limitations"][0])
            primary = read_midi_clips(part["midi"], role="drums")[0]
            self.assertEqual(primary.instrument.channel, 9)
            self.assertEqual({note.pitch for note in primary.notes}, {36, 38})
            self.assertEqual(
                set(part["variants"]),
                {"kick_deep", "snare_body"},
            )
            self.assertTrue(
                all(
                    Path(item["midi"]).suffix == ".mid"
                    for item in part["variants"].values()
                )
            )
            self.assertEqual(list(folder.glob("*.wav")), [source])

            sidecar = json.loads(
                Path(part["provenance"]).read_text(encoding="utf-8")
            )
            self.assertTrue(
                all(
                    note["details"]["published_role"] == "drums"
                    and note["details"]["processing_kind"] == "other_kit"
                    for note in sidecar["notes"]
                )
            )
            catalog = build_workbench_catalog(folder, candidate_roots=[out])
            self.assertEqual(catalog["shadowed_roles"], [])
            stem = next(
                row for row in catalog["stems"] if row["role"] == "drums"
            )
            self.assertEqual(stem["candidate_count"], 3)
            self.assertTrue(stem["review_required"])
            self.assertEqual(stem["source_shape"], "composite")
            self.assertTrue(
                all(
                    candidate["role"] == "drums"
                    for candidate in stem["candidates"]
                )
            )

    def test_explicit_drum_leaf_shadows_composite_only_in_automatic_arrangement(self):
        def fake_refine(**kwargs):
            stem = Path(kwargs["stem_path"])
            kind = kwargs["kind"]
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            pitch = 36 if "-kick-" in stem.name.lower() else 38
            note = NoteEvent(0.0, 0.08, pitch, 100)
            midi = work / f"{kind}_listened.mid"
            write_midi_file(
                midi,
                [MidiTrack(kind.title(), 9, 0, [note])],
                bpm=119,
            )
            provenance = NoteProvenance.from_note(
                note,
                origin="observed",
                confidence=0.9,
                family="kick_deep" if pitch == 36 else "snare_body",
                sources=("stem", f"listen-{kind}"),
            )
            return RefineResult(
                notes=[note],
                score=0.9,
                history=[],
                midi_path=midi,
                note_provenance=[provenance],
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Composite-B major-119bpm-440hz"
            folder.mkdir()
            (folder / "Composite-kick-B major-119bpm-440hz.wav").touch()
            (folder / "Composite-drums-B major-119bpm-440hz.wav").touch()
            out = root / "out"

            with patch(
                "sunofriend.listen_all._is_silent",
                return_value=False,
            ), patch(
                "sunofriend.loop.refine_stem",
                side_effect=fake_refine,
            ):
                summary = run_listen_all(
                    folder,
                    out,
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            self.assertEqual(summary["shadowed_roles"], ["drums"])
            self.assertEqual(
                summary["drum_role_policy"]["explicit_leaf_roles"],
                ["kick"],
            )
            self.assertEqual(
                summary["parts"]["drums"]["automatic_arrangement_status"],
                "shadowed_by_explicit_drum_leaves",
            )
            self.assertEqual(
                summary["parts"]["drums"]["arrangement_role"],
                "shadowed_by_explicit_drum_leaves",
            )
            self.assertTrue(Path(summary["parts"]["drums"]["midi"]).is_file())
            arrangement = read_midi_clips(summary["arrangement"])
            self.assertEqual(
                {
                    note.pitch
                    for clip in arrangement
                    for note in clip.notes
                },
                {36},
            )

            catalog = build_workbench_catalog(folder, candidate_roots=[out])
            self.assertEqual(catalog["shadowed_roles"], ["drums"])
            broad = next(
                row for row in catalog["stems"] if row["role"] == "drums"
            )
            self.assertGreater(broad["candidate_count"], 0)
            self.assertEqual(
                broad["automatic_arrangement_status"],
                "shadowed_by_explicit_drum_leaves",
            )

    def test_silent_explicit_leaf_falls_back_to_viable_composite_drums(self):
        def fake_refine(**kwargs):
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            note = NoteEvent(0.0, 0.08, 38, 100)
            midi = work / "other_kit_listened.mid"
            write_midi_file(
                midi,
                [MidiTrack("Drums", 9, 0, [note])],
                bpm=119,
            )
            provenance = NoteProvenance.from_note(
                note,
                origin="observed",
                confidence=0.9,
                family="snare_body",
                sources=("stem", "listen-other_kit"),
            )
            return RefineResult(
                notes=[note],
                score=0.9,
                history=[],
                midi_path=midi,
                note_provenance=[provenance],
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Composite-B major-119bpm-440hz"
            folder.mkdir()
            kick = folder / "Composite-kick-B major-119bpm-440hz.wav"
            drums = folder / "Composite-drums-B major-119bpm-440hz.wav"
            kick.touch()
            drums.touch()

            with patch(
                "sunofriend.listen_all._is_silent",
                side_effect=lambda path: Path(path).name == kick.name,
            ), patch(
                "sunofriend.loop.refine_stem",
                side_effect=fake_refine,
            ):
                summary = run_listen_all(
                    folder,
                    root / "out",
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            self.assertEqual(summary["shadowed_roles"], [])
            self.assertEqual(
                summary["drum_role_policy"]["precedence"],
                "composite-review-required",
            )
            self.assertEqual(
                summary["parts"]["drums"]["arrangement_role"],
                "primary",
            )
            self.assertTrue(
                any(
                    "automatic arrangement fallback" in warning
                    for warning in summary["warnings"]
                )
            )
            arrangement = read_midi_clips(summary["arrangement"])
            self.assertEqual(
                {
                    note.pitch
                    for clip in arrangement
                    for note in clip.notes
                },
                {38},
            )

    def test_full_run_publishes_broad_roles_without_selecting_them(self):
        engines = {
            "wind": "lead",
            "rhythm": "keys",
            "other": "synth",
        }
        pitches = {"wind": 71, "rhythm": 55, "other": 67}
        calls: list[tuple[str, str]] = []

        def fake_refine(**kwargs):
            stem = Path(kwargs["stem_path"])
            role = next(
                role for role in engines if f"-{role}-" in stem.name.lower()
            )
            kind = kwargs["kind"]
            calls.append((role, kind))
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            note = NoteEvent(0.0, 0.5, pitches[role], 88)
            midi = work / f"{kind}_listened.mid"
            write_midi_file(
                midi,
                [MidiTrack(kind.title(), 0, 0, [note])],
                bpm=119,
            )
            provenance = NoteProvenance.from_note(
                note,
                origin="observed",
                confidence=0.9,
                family=f"{kind}_melody",
                sources=("stem", f"listen-{kind}"),
            )
            return RefineResult(
                notes=[note],
                score=0.9,
                history=[],
                midi_path=midi,
                note_provenance=[provenance],
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Pupsies-B major-119bpm-440hz"
            folder.mkdir()
            for role in engines:
                (folder / f"Pupsies-{role}-B major-119bpm-440hz.wav").touch()
            out = root / "out"

            with patch(
                "sunofriend.listen_all._is_silent",
                return_value=False,
            ), patch(
                "sunofriend.loop.refine_stem",
                side_effect=fake_refine,
            ):
                summary = run_listen_all(
                    folder,
                    out,
                    evaluate_outputs=False,
                    library=root / "library",
                    progress=lambda _message: None,
                )

            self.assertEqual(calls, list(engines.items()))
            self.assertEqual(summary["status"], "complete")
            for role, kind in engines.items():
                with self.subTest(role=role):
                    part = summary["parts"][role]
                    self.assertEqual(part["status"], "ok")
                    self.assertEqual(part["published_role"], role)
                    self.assertEqual(part["processing_kind"], kind)
                    self.assertEqual(
                        part["instrument_suggestions"],
                        list(INSTRUMENT_SUGGESTIONS[role]),
                    )
                    command_kind = part["instrument_match_command"][
                        part["instrument_match_command"].index("--kind") + 1
                    ]
                    self.assertEqual(command_kind, kind)

                    clip = read_midi_clips(part["midi"], role=role)[0]
                    self.assertEqual(
                        (clip.instrument.channel, clip.instrument.program),
                        CHANNELS[role],
                    )
                    sidecar = json.loads(
                        Path(part["provenance"]).read_text(encoding="utf-8")
                    )
                    record = sidecar["notes"][0]
                    self.assertEqual(record["family"], f"{role}_melody")
                    self.assertIn(f"listen-{role}", record["sources"])
                    self.assertIn(
                        f"processing-engine:{kind}",
                        record["sources"],
                    )
                    self.assertNotIn(f"listen-{kind}", record["sources"])
                    self.assertEqual(record["details"]["published_role"], role)
                    self.assertEqual(record["details"]["processing_kind"], kind)

                    archived = ClipLibrary(root / "library").get(
                        part["library_clip_id"]
                    )
                    self.assertEqual(archived.instrument.role, role)
                    self.assertEqual(
                        (archived.instrument.channel, archived.instrument.program),
                        CHANNELS[role],
                    )
                    self.assertEqual(
                        archived.instrument.suggestions,
                        INSTRUMENT_SUGGESTIONS[role],
                    )
                    self.assertEqual(
                        archived.provenance.details_dict["published_role"],
                        role,
                    )
                    self.assertEqual(
                        archived.provenance.details_dict["processing_kind"],
                        kind,
                    )

            catalog = build_workbench_catalog(folder, candidate_roots=[out])
            by_role = {stem["role"]: stem for stem in catalog["stems"]}
            self.assertEqual(
                {role: by_role[role]["candidate_count"] for role in engines},
                {"wind": 1, "rhythm": 1, "other": 1},
            )
            state = WorkbenchStore(root / "state/workbench.sqlite3").current_state(
                catalog
            )
            self.assertEqual(state["event_count"], 0)
            self.assertTrue(
                all(
                    not stem["candidates"] and stem["main_candidate_id"] is None
                    for stem in state["stems"].values()
                )
            )

    def test_near_silent_broad_roles_remain_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Pupsies-B major-119bpm-440hz"
            folder.mkdir()
            for role in CONSERVATIVE_ROLE_ENGINES:
                (folder / f"Pupsies-{role}-B major-119bpm-440hz.wav").touch()

            with patch(
                "sunofriend.listen_all._is_silent",
                return_value=True,
            ), patch("sunofriend.loop.refine_stem") as refine:
                summary = run_listen_all(
                    folder,
                    root / "out",
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            refine.assert_not_called()
            self.assertEqual(summary["status"], "no-output")
            for role in CONSERVATIVE_ROLE_ENGINES:
                self.assertEqual(
                    summary["parts"][role]["status"],
                    "skipped: near-silent stem",
                )
            self.assertNotIn("arrangement", summary)

    def test_borderline_peak_with_negligible_rms_is_treated_as_bleed(self):
        try:
            import numpy  # noqa: F401
            import soundfile  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"optional audio dependencies are unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bleed = root / "bleed.wav"
            audible = root / "audible.wav"
            samples = [0] * 8000
            samples[4000] = 190  # ~0.0058 peak, effectively zero whole-file RMS
            self._write_pcm16(bleed, samples)
            loud = [0] * 8000
            loud[4000:4080] = [3000] * 80  # sparse but clearly audible peak
            self._write_pcm16(audible, loud)

            self.assertTrue(_is_silent(bleed))
            self.assertFalse(_is_silent(audible))

    @staticmethod
    def _write_pcm16(path: Path, samples: list[int]) -> None:
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(
                b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)
            )

    def test_selected_run_does_not_overwrite_any_full_run_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-D minor-120bpm-440hz"
            out = root / "out"
            folder.mkdir()
            (folder / "Example-kick-D minor-120bpm-440hz.wav").touch()
            out.mkdir()
            existing_manifest = out / "listen_all_summary.json"
            existing_arrangement = out / "full_arrangement.mid"
            existing_part = out / "kick_listened.mid"
            existing_iterations = out / "kick_iterations.json"
            existing_manifest.write_text("golden", encoding="utf-8")
            existing_arrangement.write_bytes(b"golden")
            existing_part.write_bytes(b"golden part")
            existing_iterations.write_text("golden iterations", encoding="utf-8")

            notes = [NoteEvent(0.0, 0.08, 36, 100)]

            def fake_refine(**kwargs):
                work = Path(kwargs["out_dir"])
                work.mkdir(parents=True, exist_ok=True)
                midi = work / "kick_listened.mid"
                write_midi_file(midi, [MidiTrack("Kick", 9, 0, notes)], bpm=120)
                (work / "kick_iterations.json").write_text("[]", encoding="utf-8")
                return RefineResult(notes=notes, score=1.0, history=[], midi_path=midi)

            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=fake_refine
            ):
                summary = run_listen_all(
                    folder,
                    out,
                    parts=["kick"],
                    library=root / "library",
                    progress=lambda _: None,
                )

            self.assertEqual(existing_manifest.read_text(encoding="utf-8"), "golden")
            self.assertEqual(existing_arrangement.read_bytes(), b"golden")
            self.assertEqual(existing_part.read_bytes(), b"golden part")
            self.assertEqual(
                existing_iterations.read_text(encoding="utf-8"), "golden iterations"
            )
            self.assertEqual(summary["status"], "complete")
            mode_root = out / "mode_repair"
            self.assertTrue((mode_root / "listen_all_summary_kick.json").is_file())
            self.assertTrue((mode_root / "selected_arrangement_kick.mid").is_file())
            selected_part = mode_root / "selected_kick" / "kick_listened.mid"
            selected_iterations = mode_root / "selected_kick" / "kick_iterations.json"
            self.assertTrue(selected_part.is_file())
            self.assertTrue(selected_iterations.is_file())
            self.assertEqual(Path(summary["parts"]["kick"]["midi"]), selected_part)
            clip_id = summary["parts"]["kick"]["library_clip_id"]
            clip = ClipLibrary(root / "library").get(clip_id)
            self.assertEqual(clip.instrument.role, "kick")
            self.assertEqual(clip.key, KeySignature("D", "minor"))
            self.assertEqual(clip.notes[0].source_start_seconds, 0.0)

    def test_full_rerun_removes_stale_artifacts_for_newly_silent_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-B major-119bpm-440hz"
            out = root / "out"
            folder.mkdir()
            out.mkdir()
            (folder / "Example-lead-B major-119bpm-440hz.wav").touch()
            mode_root = out / "mode_repair"
            mode_root.mkdir()
            stale_midi = mode_root / "lead_listened.mid"
            stale_iterations = mode_root / "lead_iterations.json"
            stale_provenance = mode_root / "lead_provenance.json"
            stale_evaluation = mode_root / "lead_evaluation.json"
            variants = mode_root / "variants"
            variants.mkdir()
            stale_variant = variants / "lead-uncertain.mid"
            stale_midi.write_bytes(b"old lead")
            stale_iterations.write_text("old iterations", encoding="utf-8")
            stale_provenance.write_text("old provenance", encoding="utf-8")
            stale_evaluation.write_text("old evaluation", encoding="utf-8")
            stale_variant.write_bytes(b"old variant")

            with patch("sunofriend.listen_all._is_silent", return_value=True):
                summary = run_listen_all(folder, out, progress=lambda _: None)

            self.assertEqual(summary["parts"]["lead"]["status"], "skipped: near-silent stem")
            self.assertFalse(stale_midi.exists())
            self.assertFalse(stale_iterations.exists())
            self.assertFalse(stale_provenance.exists())
            self.assertFalse(stale_evaluation.exists())
            self.assertFalse(stale_variant.exists())

    def test_no_output_rerun_removes_stale_selected_part_and_arrangement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-B major-119bpm-440hz"
            folder.mkdir()
            mode_root = root / "out/mode_repair"
            publish_dir = mode_root / "selected_kick"
            variants = publish_dir / "variants"
            variants.mkdir(parents=True)
            stale_part = publish_dir / "kick_listened.mid"
            stale_sidecar = publish_dir / "kick_provenance.json"
            stale_variant = variants / "kick-possible.mid"
            stale_arrangement = mode_root / "selected_arrangement_kick.mid"
            stale_part.write_bytes(b"stale")
            stale_sidecar.write_text("stale", encoding="utf-8")
            stale_variant.write_bytes(b"stale")
            stale_arrangement.write_bytes(b"stale")

            summary = run_listen_all(
                folder,
                root / "out",
                parts=["kick"],
                progress=lambda _: None,
            )

            self.assertEqual(summary["status"], "no-output")
            self.assertFalse(stale_part.exists())
            self.assertFalse(stale_sidecar.exists())
            self.assertFalse(stale_variant.exists())
            self.assertFalse(stale_arrangement.exists())

    def test_failed_full_rerun_does_not_leave_previous_public_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-B major-119bpm-440hz"
            folder.mkdir()
            (folder / "Example-kick-B major-119bpm-440hz.wav").touch()
            mode_root = root / "out/mode_repair"
            mode_root.mkdir(parents=True)
            stale_part = mode_root / "kick_listened.mid"
            stale_arrangement = mode_root / "full_arrangement.mid"
            stale_part.write_bytes(b"stale")
            stale_arrangement.write_bytes(b"stale")

            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=RuntimeError("conversion failed")
            ):
                summary = run_listen_all(
                    folder,
                    root / "out",
                    progress=lambda _: None,
                )

            self.assertEqual(summary["status"], "failed")
            self.assertFalse(stale_part.exists())
            self.assertFalse(stale_arrangement.exists())

    def test_library_archive_id_covers_all_immutable_clip_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stem = root / "kick.wav"
            midi = root / "kick.mid"
            stem.touch()
            notes = [NoteEvent(0.0, 0.08, 36, 100)]
            write_midi_file(midi, [MidiTrack("Kick", 9, 0, notes)], bpm=120)
            arguments = {
                "title": "Example - kick",
                "name": "kick",
                "kind": "kick",
                "stem": stem,
                "midi": midi,
                "notes": notes,
                "key": "D minor",
                "grid": Grid(120),
                "daw_bpm": 120,
            }

            first = _make_library_clip(score=1.0, **arguments)
            repeated = _make_library_clip(score=1.0, **arguments)
            rescored = _make_library_clip(score=0.9, **arguments)
            library = ClipLibrary(root / "library")

            self.assertEqual(first.clip_id, repeated.clip_id)
            self.assertNotEqual(first.clip_id, rescored.clip_id)
            library.add(first)
            library.add(repeated)
            library.add(rescored)
            self.assertEqual(len(library.list()), 2)

    def test_cli_returns_failure_when_listen_all_produces_no_output(self):
        summary = {"status": "no-output", "set_garageband_tempo_to": 120.0}
        stdout = StringIO()
        with patch("sunofriend.render.is_available", return_value=True), patch(
            "sunofriend.listen_all.run_listen_all", return_value=summary
        ), redirect_stdout(stdout):
            result = main(["listen-all", "unused", "--out-dir", "unused"])

        self.assertEqual(result, 2)
        self.assertIn("set GarageBand tempo to: 120.0", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
