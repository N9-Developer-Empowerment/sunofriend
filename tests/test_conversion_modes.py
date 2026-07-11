from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.cli import _publish_single_result, build_parser, main
from sunofriend.conversion import (
    NoteProvenance,
    provenance_for_notes,
    partition_cross_stem_leakage,
    partition_uncertain_families,
    retarget_note_provenance,
    validate_conversion_mode,
    write_note_provenance,
)
from sunofriend.listen_all import (
    _retarget_published_role_provenance,
    run_listen_all,
)
from sunofriend.library import ClipLibrary
from sunofriend.clip import read_midi_clips
from sunofriend.loop import (
    RefineResult,
    _apply_edits_drums_preserve_observed,
    _drum_hit_provenance,
    _seed_pitched_v2,
)
from sunofriend.compare import DrumDiff, Onset
from sunofriend.transcribe_drums import DrumHit
from sunofriend.transcribe_pitched import KeysRoleSeparation
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.note_safety import normalize_note_events


class ConversionModeTests(unittest.TestCase):
    def test_mode_validation_is_explicit(self):
        self.assertEqual(validate_conversion_mode(" REPAIR "), "repair")
        with self.assertRaisesRegex(ValueError, "exact, repair, reconstruct"):
            validate_conversion_mode("automatic")

    def test_note_provenance_validates_confidence(self):
        note = NoteEvent(1.0, 1.1, 36, 100)
        with self.assertRaisesRegex(ValueError, "confidence"):
            NoteProvenance.from_note(note, origin="observed", confidence=1.1)

    def test_sidecar_distinguishes_observed_repaired_and_inferred(self):
        notes = [
            NoteEvent(0.0, 0.1, 36, 100),
            NoteEvent(0.5, 0.6, 35, 70),
            NoteEvent(1.0, 1.1, 36, 55),
        ]
        records = [
            NoteProvenance.from_note(
                notes[0], origin="observed", confidence=0.98, family="kick_deep"
            ),
            NoteProvenance.from_note(
                notes[1], origin="repaired", confidence=0.72, tier="possible"
            ),
            NoteProvenance.from_note(
                notes[2],
                origin="inferred",
                confidence=0.55,
                tier="uncertain",
                confidence_basis="policy",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "kick.provenance.json"
            write_note_provenance(
                output,
                records,
                conversion_mode="reconstruct",
                source_stem="kick.wav",
                variant="kick_reconstruct",
            )
            document = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(document["conversion_mode"], "reconstruct")
        self.assertEqual(document["counts"]["observed"], 1)
        self.assertEqual(document["counts"]["repaired"], 1)
        self.assertEqual(document["counts"]["inferred"], 1)
        self.assertEqual(document["counts"]["policy_confidence"], 1)
        self.assertEqual(document["counts"]["possible"], 1)
        self.assertEqual(document["notes"][0]["family"], "kick_deep")

    def test_bulk_provenance_keeps_note_timing(self):
        notes = [NoteEvent(0.125, 0.25, 42, 80)]
        records = provenance_for_notes(
            notes,
            origin="observed",
            confidence=0.9,
            sources=("stereo_onset", "spectral_family"),
        )
        self.assertEqual(records[0].start, 0.125)
        self.assertEqual(records[0].sources, ("stereo_onset", "spectral_family"))

    def test_piano_role_keeps_keys_engine_explicit_in_provenance(self):
        note = NoteEvent(0.0, 0.5, 60, 80)
        source = NoteProvenance.from_note(
            note,
            origin="observed",
            confidence=0.9,
            family="keys_melody",
            sources=("stem", "listen-keys"),
            details={"voice": "upper"},
        )

        record = _retarget_published_role_provenance(
            [source],
            name="piano",
            kind="keys",
        )[0]

        self.assertEqual(record.family, "piano_melody")
        self.assertEqual(
            record.sources,
            ("stem", "listen-piano", "processing-engine:keys"),
        )
        self.assertEqual(record.details["voice"], "upper")
        self.assertEqual(record.details["published_role"], "piano")
        self.assertEqual(record.details["processing_kind"], "keys")

    def test_variant_provenance_follows_normalized_midi_intervals(self):
        raw = [
            NoteEvent(0.0, 1.0, 60, 80),
            NoteEvent(0.5, 1.5, 60, 90),
        ]
        records = provenance_for_notes(
            raw,
            origin="observed",
            confidence=0.8,
        )

        normalized = normalize_note_events(raw)
        retargeted = retarget_note_provenance(normalized, records)

        self.assertEqual(normalized[0].end, 0.5)
        self.assertEqual(retargeted[0].end, 0.5)
        self.assertEqual(
            [(note.start, note.end, note.pitch) for note in normalized],
            [(item.start, item.end, item.pitch) for item in retargeted],
        )

    def test_cli_exposes_modes_for_single_and_batch_conversion(self):
        parser = build_parser()
        one = parser.parse_args(
            [
                "listen",
                "kick.wav",
                "--kind",
                "kick",
                "--bpm",
                "120",
                "--out-dir",
                "out",
                "--conversion-mode",
                "exact",
            ]
        )
        batch = parser.parse_args(
            [
                "listen-all",
                "stems",
                "--out-dir",
                "out",
                "--conversion-mode",
                "reconstruct",
            ]
        )
        self.assertEqual(one.conversion_mode, "exact")
        self.assertEqual(batch.conversion_mode, "reconstruct")

    def test_non_default_mode_is_isolated_from_repair_outputs(self):
        notes = [NoteEvent(0.0, 0.1, 36, 100)]

        def fake_refine(**kwargs):
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            midi = work / "kick_listened.mid"
            write_midi_file(midi, [MidiTrack("Kick", 9, 0, notes)], bpm=120)
            (work / "kick_iterations.json").write_text("[]", encoding="utf-8")
            return RefineResult(notes, 1.0, [], midi)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stems = root / "Example-C major-120bpm-440hz"
            stems.mkdir()
            (stems / "Example-kick-C major-120bpm-440hz.wav").touch()
            out = root / "out"
            out.mkdir()
            legacy = out / "listen_all_summary.json"
            legacy.write_text("repair golden", encoding="utf-8")
            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=fake_refine
            ):
                summary = run_listen_all(
                    stems,
                    out,
                    conversion_mode="exact",
                    progress=lambda _message: None,
                )

            self.assertEqual(legacy.read_text(encoding="utf-8"), "repair golden")
            self.assertEqual(summary["conversion_mode"], "exact")
            self.assertEqual(Path(summary["summary"]), out / "mode_exact/listen_all_summary.json")
            self.assertEqual(Path(summary["arrangement"]), out / "mode_exact/full_arrangement.mid")

    def test_single_stem_modes_publish_sidecars_and_do_not_overwrite_each_other(self):
        main_note = NoteEvent(0.0, 0.1, 42, 80)
        inferred = NoteProvenance.from_note(
            main_note,
            origin="inferred",
            confidence=0.6,
            confidence_basis="policy",
            family="hat_closed",
        )

        def fake_refine(**kwargs):
            out = Path(kwargs["out_dir"])
            out.mkdir(parents=True, exist_ok=True)
            midi = out / "hat_listened.mid"
            write_midi_file(midi, [MidiTrack("Hat", 9, 0, [main_note])], bpm=120)
            return RefineResult(
                notes=[main_note],
                score=0.8,
                history=[],
                midi_path=midi,
                variants={"possible": [NoteEvent(0.5, 0.55, 42, 50)]},
                note_provenance=[inferred],
            )

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            with patch("sunofriend.render.is_available", return_value=True), patch(
                "sunofriend.loop.refine_stem", side_effect=fake_refine
            ):
                status = main(
                    [
                        "listen",
                        "hat.wav",
                        "--kind",
                        "hat",
                        "--bpm",
                        "120",
                        "--out-dir",
                        str(out),
                        "--conversion-mode",
                        "reconstruct",
                        "--no-evaluate",
                    ]
                )

            mode = out / "mode_reconstruct"
            self.assertEqual(status, 0)
            self.assertFalse((out / "hat_listened.mid").exists())
            self.assertTrue((mode / "hat_listened.mid").is_file())
            self.assertTrue((mode / "hat_provenance.json").is_file())
            self.assertTrue((mode / "variants/hat-possible.mid").is_file())
            document = json.loads(
                (mode / "hat_provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(document["counts"]["inferred"], 1)

    def test_single_stem_publisher_exposes_normalized_variant_intervals(self):
        main_note = NoteEvent(0.0, 0.1, 42, 80)
        raw_variant = [
            NoteEvent(0.0, 1.0, 60, 80),
            NoteEvent(0.5, 1.5, 60, 90),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            midi = root / "keys_listened.mid"
            write_midi_file(
                midi,
                [MidiTrack("Keys", 1, 7, [main_note])],
                bpm=120,
            )
            stem = root / "keys.wav"
            stem.touch()
            result = RefineResult(
                notes=[main_note],
                score=0.8,
                history=[],
                midi_path=midi,
                variants={"overlap": raw_variant},
            )

            _publish_single_result(
                result,
                stem=stem,
                kind="keys",
                bpm=120,
                conversion_mode="repair",
                out_dir=root,
            )

            self.assertEqual(
                result.variants["overlap"],
                normalize_note_events(raw_variant),
            )

    def test_cross_stem_leakage_quarantines_only_dominated_weak_hit(self):
        weak = NoteEvent(1.000, 1.12, 45, 42)
        strong_tom = NoteEvent(2.000, 2.12, 48, 100)
        records = [
            NoteProvenance.from_note(
                weak,
                origin="observed",
                confidence=0.42,
                family="tom_low",
                details={
                    "dominant_hz": 62.0,
                    "spectral_centroid_hz": 180.0,
                    "low_ratio": 0.82,
                    "mid_ratio": 0.16,
                    "high_ratio": 0.02,
                },
            ),
            NoteProvenance.from_note(
                strong_tom, origin="observed", confidence=0.86, family="tom_mid"
            ),
        ]
        hat = NoteEvent(1.008, 1.05, 42, 110)
        references = {
            "hat": [
                NoteProvenance.from_note(
                    hat,
                    origin="observed",
                    confidence=0.91,
                    family="kick_deep",
                    details={
                        "dominant_hz": 61.0,
                        "spectral_centroid_hz": 185.0,
                        "low_ratio": 0.80,
                        "mid_ratio": 0.17,
                        "high_ratio": 0.03,
                    },
                )
            ]
        }

        main, _, uncertain, uncertain_records = partition_cross_stem_leakage(
            [weak, strong_tom], records, references
        )

        self.assertEqual(main, [strong_tom])
        self.assertEqual(uncertain, [weak])
        self.assertEqual(uncertain_records[0].tier, "uncertain")
        self.assertEqual(
            uncertain_records[0].details["possible_leakage"]["stem"], "hat"
        )

    def test_simultaneous_but_spectrally_different_hit_stays_main(self):
        tom = NoteEvent(1.0, 1.12, 45, 50)
        tom_record = NoteProvenance.from_note(
            tom,
            origin="observed",
            confidence=0.4,
            family="tom_low",
            details={
                "dominant_hz": 130.0,
                "spectral_centroid_hz": 500.0,
                "low_ratio": 0.25,
                "mid_ratio": 0.70,
                "high_ratio": 0.05,
            },
        )
        hat = NoteEvent(1.005, 1.05, 42, 110)
        hat_record = NoteProvenance.from_note(
            hat,
            origin="observed",
            confidence=0.95,
            family="hat_closed",
            details={
                "dominant_hz": 7000.0,
                "spectral_centroid_hz": 6500.0,
                "low_ratio": 0.01,
                "mid_ratio": 0.05,
                "high_ratio": 0.94,
            },
        )

        main, _, uncertain, _ = partition_cross_stem_leakage(
            [tom], [tom_record], {"hat": [hat_record]}
        )

        self.assertEqual(main, [tom])
        self.assertEqual(uncertain, [])

    def test_unknown_other_kit_family_is_retained_separately(self):
        known = NoteEvent(0.0, 0.08, 36, 90)
        unknown = NoteEvent(0.5, 0.58, 39, 60)
        records = [
            NoteProvenance.from_note(
                known, origin="observed", confidence=0.8, family="kick_deep"
            ),
            NoteProvenance.from_note(
                unknown, origin="observed", confidence=0.7, family="unknown"
            ),
        ]

        main, _, uncertain, uncertain_records = partition_uncertain_families(
            [known, unknown], records
        )

        self.assertEqual(main, [known])
        self.assertEqual(uncertain, [unknown])
        self.assertEqual(uncertain_records[0].tier, "uncertain")

    def test_batch_publishes_variants_and_quarantines_tom_leakage(self):
        kick = NoteEvent(1.008, 1.098, 36, 110)
        weak_tom = NoteEvent(1.000, 1.120, 45, 42)
        strong_tom = NoteEvent(2.000, 2.120, 48, 100)

        def fake_refine(**kwargs):
            kind = kwargs["kind"]
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            if kind == "kick":
                notes = [kick]
                records = [
                    NoteProvenance.from_note(
                        kick,
                        origin="observed",
                        confidence=0.94,
                        family="kick_deep",
                        details={
                            "dominant_hz": 61.0,
                            "spectral_centroid_hz": 180.0,
                            "low_ratio": 0.82,
                            "mid_ratio": 0.16,
                            "high_ratio": 0.02,
                        },
                    )
                ]
            else:
                notes = [weak_tom, strong_tom]
                records = [
                    NoteProvenance.from_note(
                        weak_tom,
                        origin="observed",
                        confidence=0.40,
                        family="tom_low",
                        details={
                            "dominant_hz": 62.0,
                            "spectral_centroid_hz": 185.0,
                            "low_ratio": 0.80,
                            "mid_ratio": 0.17,
                            "high_ratio": 0.03,
                        },
                    ),
                    NoteProvenance.from_note(
                        strong_tom,
                        origin="observed",
                        confidence=0.90,
                        family="tom_mid",
                    ),
                ]
            midi = work / f"{kind}_listened.mid"
            write_midi_file(midi, [MidiTrack(kind.title(), 9, 0, notes)], bpm=120)
            (work / f"{kind}_iterations.json").write_text("[]", encoding="utf-8")
            return RefineResult(
                notes=notes,
                score=0.9,
                history=[],
                midi_path=midi,
                note_provenance=records,
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stems = root / "Example-C major-120bpm-440hz"
            stems.mkdir()
            (stems / "Example-kick-C major-120bpm-440hz.wav").touch()
            (stems / "Example-toms-C major-120bpm-440hz.wav").touch()
            out = root / "out"
            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=fake_refine
            ):
                summary = run_listen_all(
                    stems,
                    out,
                    conversion_mode="repair",
                    evaluate_outputs=False,
                    library=root / "library",
                    progress=lambda _message: None,
                )

            toms = summary["parts"]["toms"]
            self.assertEqual(toms["notes"], 1)
            uncertain = toms["variants"]["leakage_uncertain"]
            self.assertEqual(uncertain["notes"], 1)
            self.assertTrue(Path(uncertain["midi"]).is_file())
            self.assertIn("library_clip_id", uncertain)
            archived = ClipLibrary(root / "library").get(uncertain["library_clip_id"])
            self.assertEqual(archived.instrument.role, "toms")
            self.assertEqual(
                archived.provenance.details_dict["related_primary_clip_id"],
                toms["library_clip_id"],
            )
            self.assertNotIn("score", archived.provenance.details_dict)
            self.assertEqual(
                archived.provenance.details_dict["score_scope"],
                "not_scored_variant",
            )
            sidecar = json.loads(Path(uncertain["provenance"]).read_text(encoding="utf-8"))
            self.assertEqual(sidecar["counts"]["uncertain"], 1)

    def test_reconstruct_arrangement_uses_keys_melody_and_pads_without_strings_doubling(self):
        melody = NoteEvent(0.0, 0.5, 84, 100)
        accompaniment = NoteEvent(0.0, 1.0, 48, 70)
        string_chord = NoteEvent(0.0, 1.0, 60, 75)
        string_texture = NoteEvent(1.0, 2.0, 67, 65)
        pad_chord = NoteEvent(0.0, 1.0, 64, 75)

        def fake_refine(**kwargs):
            work = Path(kwargs["out_dir"])
            work.mkdir(parents=True, exist_ok=True)
            part = work.name.removeprefix(".").removesuffix("_work")
            kind = kwargs["kind"]
            if part == "keys":
                notes = [melody, accompaniment]
                variants = {
                    "melody": [melody],
                    "accompaniment": [accompaniment],
                }
                variant_provenance = {}
            elif part == "strings":
                notes = [string_chord]
                variants = {"texture": [string_texture]}
                variant_provenance = {
                    "texture": [
                        NoteProvenance.from_note(
                            string_texture,
                            origin="inferred",
                            confidence=0.6,
                            confidence_basis="policy",
                            family="pads",
                            sources=("stem", "listen-pads", "mode:reconstruct"),
                        )
                    ]
                }
            else:
                notes = [pad_chord]
                variants = {}
                variant_provenance = {}
            midi = work / f"{kind}_listened.mid"
            write_midi_file(midi, [MidiTrack(part.title(), 0, 0, notes)], bpm=120)
            (work / f"{kind}_iterations.json").write_text("[]", encoding="utf-8")
            provenance = []
            if part == "strings":
                provenance = [
                    NoteProvenance.from_note(
                        string_chord,
                        origin="inferred",
                        confidence=0.7,
                        confidence_basis="policy",
                        family="pads",
                        sources=("stem", "listen-pads", "mode:reconstruct"),
                    )
                ]
            return RefineResult(
                notes,
                0.8,
                [],
                midi,
                variants=variants,
                note_provenance=provenance,
                variant_provenance=variant_provenance,
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stems = root / "Example-C major-120bpm-440hz"
            stems.mkdir()
            (stems / "Example-keys-C major-120bpm-440hz.wav").touch()
            (stems / "Example-strings-C major-120bpm-440hz.wav").touch()
            out = root / "out"
            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=fake_refine
            ):
                summary = run_listen_all(
                    stems,
                    out,
                    conversion_mode="reconstruct",
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            clips = read_midi_clips(summary["arrangement"])
            pitches = sorted(note.pitch for clip in clips for note in clip.notes)
            self.assertEqual(pitches, [64, 84])
            self.assertEqual(
                summary["parts"]["keys"]["arrangement_role"],
                "melody_only_with_chart_pads",
            )
            self.assertEqual(
                summary["parts"]["strings"]["arrangement_role"],
                "audition_only_avoids_chart_doubling",
            )
            strings_sidecar = json.loads(
                Path(summary["parts"]["strings"]["provenance"]).read_text(
                    encoding="utf-8"
                )
            )
            string_record = strings_sidecar["notes"][0]
            self.assertEqual(string_record["family"], "strings")
            self.assertIn("listen-strings", string_record["sources"])
            self.assertIn("processing-engine:pads", string_record["sources"])
            self.assertNotIn("listen-pads", string_record["sources"])
            self.assertEqual(string_record["details"]["published_role"], "strings")
            self.assertEqual(string_record["details"]["processing_kind"], "pads")
            strings_variant = json.loads(
                Path(
                    summary["parts"]["strings"]["variants"]["texture"]["provenance"]
                ).read_text(encoding="utf-8")
            )["notes"][0]
            self.assertEqual(strings_variant["family"], "strings")
            self.assertIn("listen-strings", strings_variant["sources"])
            self.assertIn("processing-engine:pads", strings_variant["sources"])

    def test_repair_mode_does_not_invent_missing_pads_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stems = root / "Example-C major-120bpm-440hz"
            stems.mkdir()
            (stems / "Example-keys-C major-120bpm-440hz.wav").touch()
            with patch("sunofriend.listen_all._is_silent", return_value=True):
                summary = run_listen_all(
                    stems,
                    root / "out",
                    conversion_mode="repair",
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            self.assertEqual(
                summary["parts"]["pads"]["status"],
                "skipped: no observed pads stem in repair mode",
            )

    def test_exact_keys_quarantines_role_uncertainty_from_main(self):
        melody = NoteEvent(0.0, 0.5, 76, 100)
        accompaniment = NoteEvent(0.0, 1.0, 52, 70)
        uncertain = NoteEvent(0.1, 0.2, 61, 35)
        evidence = [melody, accompaniment, uncertain]
        roles = KeysRoleSeparation([melody], [accompaniment], [uncertain])

        with patch(
            "sunofriend.transcribe_pitched.transcribe_pitched_stem",
            return_value=evidence,
        ), patch(
            "sunofriend.verify.verify_notes"
        ) as verify, patch(
            "sunofriend.transcribe_pitched.separate_keys_roles",
            return_value=roles,
        ):
            verify.return_value.kept = evidence
            selected, variants, provenance, variant_provenance = _seed_pitched_v2(
                "keys.wav",
                "keys",
                120.0,
                None,
                "C major",
                None,
                None,
                "exact",
            )

        self.assertEqual(
            selected,
            sorted([melody, accompaniment], key=lambda note: (note.start, note.pitch, note.end)),
        )
        self.assertEqual(variants["uncertain"], [uncertain])
        self.assertTrue(all(record.tier == "main" for record in provenance))
        self.assertEqual(variant_provenance["uncertain"][0].tier, "uncertain")

    def test_drum_preview_refinement_cannot_delete_or_invent_observed_hits(self):
        notes = [
            NoteEvent(0.5, 0.59, 35, 80),
            NoteEvent(1.0, 1.09, 36, 90),
        ]
        diff = DrumDiff(
            missed=[Onset(1.0, 0.8), Onset(1.5, 0.7)],
            extra=[0.5],
            matched=[(0.5, 0.52)],
        )

        got = _apply_edits_drums_preserve_observed(notes, diff)

        self.assertEqual(len(got), 2)
        self.assertEqual({note.pitch for note in got}, {35, 36})
        self.assertFalse(any(abs(note.start - 1.5) < 0.03 for note in got))

    def test_inferred_hat_provenance_does_not_claim_audio_evidence(self):
        note = NoteEvent(1.0, 1.045, 42, 70)
        hit = DrumHit(
            time=1.0,
            gm_pitch=42,
            velocity=70,
            strength=0.0,
            family="hat_closed",
            provenance="inferred",
        )

        record = _drum_hit_provenance([hit], [note])[0]

        self.assertEqual(record.sources, ("beat-grid", "recurring-pattern"))
        self.assertNotIn("stereo-onset", record.sources)


if __name__ == "__main__":
    unittest.main()
