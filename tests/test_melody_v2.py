from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend.melody_correction import (
    add_hummed_snippet_variants,
    align_hummed_guide,
    apply_melody_corrections,
    write_melody_correction_artifacts,
)
from sunofriend.models import NoteEvent
from sunofriend.vocal import (
    PitchFrame,
    VocalConfig,
    VocalNoteEvidence,
    consensus_pitch_frames,
    fractional_midi_to_hz,
    repair_repeated_phrases,
    transcribe_vocal_frames,
)


def _frame(
    time: float, pitch: float | None, probability: float, source: str
) -> PitchFrame:
    return PitchFrame(
        time,
        fractional_midi_to_hz(pitch) if pitch is not None else None,
        probability,
        0.2,
        source=source,
    )


def _evidence(note: NoteEvent, confidence: float = 0.7) -> VocalNoteEvidence:
    return VocalNoteEvidence(
        note=note,
        confidence=confidence,
        median_f0_hz=fractional_midi_to_hz(note.pitch),
        median_midi_float=float(note.pitch),
        pitch_mad_cents=5.0,
        median_voiced_probability=confidence,
        voiced_fraction=1.0,
        onset_strength=0.4,
        sources=("fixture",),
    )


class MelodyConsensusTests(unittest.TestCase):
    def test_tracker_agreement_is_confident_and_disagreement_is_quarantined(self):
        config = VocalConfig(
            tracker_mode="consensus",
            clean_voicing=0.55,
            uncertain_voicing=0.30,
        )
        pyin = [
            _frame(0.0, 60.02, 0.92, "pyin"),
            _frame(0.1, 62.00, 0.93, "pyin"),
            _frame(0.2, 64.01, 0.91, "pyin"),
        ]
        neural = [
            _frame(0.0, 60.00, 0.86, "basic-pitch"),
            _frame(0.1, 67.00, 0.90, "basic-pitch"),
            _frame(0.2, 64.00, 0.88, "basic-pitch"),
        ]

        got = consensus_pitch_frames(
            {"pyin": pyin, "basic-pitch": neural}, config=config
        )

        self.assertIn("basic-pitch+pyin", got[0].source)
        self.assertGreaterEqual(got[0].voiced_probability, config.clean_voicing)
        self.assertEqual(got[1].source, "consensus:pyin-disputed")
        self.assertLess(got[1].voiced_probability, config.clean_voicing)
        self.assertIn("basic-pitch+pyin", got[2].source)


class PhraseRepetitionTests(unittest.TestCase):
    def test_repeated_phrase_promotes_only_an_observed_weak_omission(self):
        first = [
            NoteEvent(0.0, 0.35, 60, 90),
            NoteEvent(0.5, 0.85, 62, 90),
            NoteEvent(1.0, 1.35, 64, 90),
            NoteEvent(1.5, 1.85, 65, 90),
        ]
        second_clean = [
            NoteEvent(4.0, 4.35, 60, 90),
            NoteEvent(5.0, 5.35, 64, 90),
            NoteEvent(5.5, 5.85, 65, 90),
        ]
        weak = NoteEvent(4.5, 4.85, 62, 70)
        clean = [*first, *second_clean]

        notes, evidence, repairs, lags = repair_repeated_phrases(
            clean,
            [_evidence(note) for note in clean],
            [weak, NoteEvent(8.0, 8.3, 71, 60)],
            [_evidence(weak, 0.32), _evidence(NoteEvent(8.0, 8.3, 71, 60), 0.32)],
            config=VocalConfig(bpm=120.0),
        )

        self.assertEqual(repairs, 1)
        self.assertEqual(lags, (4.0,))
        self.assertIn(weak, notes)
        self.assertNotIn(71, [note.pitch for note in notes])
        repaired = evidence[notes.index(weak)]
        self.assertIn("phrase-repetition", repaired.sources)
        self.assertIn("repeated_phrase_support", repaired.boundary_reasons)


class HummedGuideTests(unittest.TestCase):
    def test_short_positioned_hums_patch_the_automatic_full_song_melody(self):
        frames = []
        for index in range(81):
            time = index / 10.0
            pitch = None
            for start in (1.0, 4.0):
                if start <= time < start + 0.4:
                    pitch = 60
                elif start + 0.5 <= time < start + 0.9:
                    pitch = 62
                elif start + 1.0 <= time < start + 1.4:
                    pitch = 64
            frames.append(
                _frame(time, pitch, 0.92 if pitch is not None else 0.0, "pyin")
            )
        config = VocalConfig(
            bpm=120.0,
            tracker_mode="pyin",
            smooth_frames=3,
            stable_pitch_ms=50.0,
            min_note_ms=50.0,
        )
        result = transcribe_vocal_frames(frames, config=config)
        guide = [
            NoteEvent(0.0, 0.4, 55, 80),
            NoteEvent(0.5, 0.9, 57, 82),
            NoteEvent(1.0, 1.4, 59, 84),
        ]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for name in ("reference-1", "hum-1", "reference-2", "hum-2"):
                path = root / f"{name}.wav"
                soundfile.write(path, np.zeros(160_000, dtype=np.float32), 16_000)
                paths.append(path)
            with patch(
                "sunofriend.melody_correction._transcribe_hummed_notes",
                side_effect=[(guide, []), (guide, [])],
            ):
                updated, report = add_hummed_snippet_variants(
                    result,
                    [
                        (paths[0], paths[1], 0.7),
                        (paths[2], paths[3], 3.7),
                    ],
                    config=config,
                    prefer_guide=True,
                )

        self.assertEqual(updated.primary_variant, "snippet_patched")
        self.assertEqual(report["mode"], "snippets")
        self.assertEqual(report["accepted_snippet_count"], 2)
        self.assertEqual(report["accepted_note_count"], 6)
        self.assertAlmostEqual(
            report["snippets"][0]["alignment"]["offset_seconds"],
            1.0,
            delta=0.11,
        )
        self.assertEqual(
            [note.pitch for note in updated.variants["snippet_guides"]],
            [60, 62, 64, 60, 62, 64],
        )
        self.assertEqual(len(updated.variants["snippet_patched"]), 6)
        self.assertTrue(updated.diagnostics.guide_used)

    def test_guide_finds_time_offset_and_register_from_source_contour(self):
        frames = []
        for index in range(31):
            time = index / 10.0
            pitch = None
            if 1.0 <= time < 1.4:
                pitch = 60
            elif 1.5 <= time < 1.9:
                pitch = 62
            elif 2.0 <= time < 2.4:
                pitch = 64
            frames.append(
                _frame(time, pitch, 0.92 if pitch is not None else 0.0, "pyin")
            )
        guide = [
            NoteEvent(0.0, 0.4, 55, 80),
            NoteEvent(0.5, 0.9, 57, 82),
            NoteEvent(1.0, 1.4, 59, 84),
        ]

        notes, records, report = align_hummed_guide(
            frames,
            guide,
            config=VocalConfig(bpm=120.0, tracker_mode="pyin"),
        )

        self.assertEqual([note.pitch for note in notes], [60, 62, 64])
        self.assertAlmostEqual(report["offset_seconds"], 1.0, delta=0.11)
        self.assertEqual(report["transpose_semitones"], 5)
        self.assertEqual(len(records), 3)
        self.assertTrue(all(record.origin == "repaired" for record in records))

    def test_visual_seed_can_round_trip_to_corrected_midi(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem = root / "voice.wav"
            soundfile.write(stem, np.zeros(8_000, dtype=np.float32), 16_000)
            frames = [_frame(index * 0.02, 60, 0.9, "pyin") for index in range(30)]
            result = transcribe_vocal_frames(
                frames,
                config=VocalConfig(bpm=120.0, tracker_mode="pyin"),
            )
            output = root / "result"

            artifacts = write_melody_correction_artifacts(
                stem,
                result,
                out_dir=output,
                bpm=120.0,
                key="C major",
                role="lead",
                primary_midi=output / "lead.mid",
            )

            html_text = Path(artifacts["html"]).read_text()
            document = json.loads(Path(artifacts["json"]).read_text())
            self.assertIn("Export corrections JSON", html_text)
            self.assertEqual(document["format"], "sunofriend-melody-corrections-v1")
            self.assertTrue(document["notes"])
            corrected = root / "corrected.mid"
            audit = apply_melody_corrections(artifacts["json"], out_path=corrected)
            self.assertEqual(audit["note_count"], len(document["notes"]))
            self.assertEqual(corrected.read_bytes()[:4], b"MThd")
            self.assertTrue(corrected.with_suffix(".correction.json").is_file())


if __name__ == "__main__":
    unittest.main()
