from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import soundfile

from sunofriend.ausampler import write_ausampler_preset
from sunofriend.instrument_catalog import (
    GM_PROGRAM_NAMES,
    SamplerInstrumentPreset,
    inventory_instruments,
    list_audio_unit_instruments,
    program_candidates,
)
from sunofriend.instrument_match import (
    _estimate_sample_tuning,
    _related_sampler_presets,
    build_sample_pack,
    match_instruments,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.render import RenderError, find_fluidsynth, render_midi_to_wav
from sunofriend.soundfont import SoundFontZone, inspect_soundfont, write_soundfont


SAMPLE_RATE = 16_000


def _tone(frequency: float, seconds: float, *, decay: float = 0.0) -> np.ndarray:
    times = np.arange(round(seconds * SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    envelope = np.ones_like(times)
    if decay:
        envelope = np.exp(-times * decay)
    return (0.4 * envelope * np.sin(2.0 * np.pi * frequency * times)).astype(np.float32)


class InstrumentCatalogTests(unittest.TestCase):
    def test_general_midi_catalog_and_role_candidates_are_valid(self):
        self.assertEqual(len(GM_PROGRAM_NAMES), 128)
        self.assertEqual(program_candidates("bass"), tuple(range(32, 40)))
        self.assertEqual(
            program_candidates("unknown", all_programs=True), tuple(range(128))
        )

    @mock.patch(
        "sunofriend.instrument_catalog.shutil.which", return_value="/usr/bin/auval"
    )
    @mock.patch("sunofriend.instrument_catalog.subprocess.run")
    def test_audio_unit_inventory_keeps_music_devices_only(self, run, _which):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=(
                "aumu dls  appl - Apple: DLSMusicDevice\n"
                "aumu VTL1 VtlA - Vital Audio: Vital\n"
                "aufx grr7 NIxx - Native Instruments: Guitar Rig 7\n"
            ),
        )

        result = list_audio_unit_instruments()

        self.assertEqual(
            [item.display_name for item in result], ["DLSMusicDevice", "Vital"]
        )
        self.assertTrue(result[0].built_in)
        self.assertFalse(result[1].built_in)

    def test_inventory_is_compact_but_keeps_representative_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sampler = root / "sampler" / "Grand Piano"
            drums = root / "drums" / "Studio Kit"
            garageband_presets = root / "garageband-presets" / "Bass"
            logic_presets = root / "logic-presets" / "Keys"
            sampler.mkdir(parents=True)
            drums.mkdir(parents=True)
            garageband_presets.mkdir(parents=True)
            logic_presets.mkdir(parents=True)
            for index in range(7):
                soundfile.write(
                    sampler / f"piano-C{index}.wav", _tone(220, 0.05), SAMPLE_RATE
                )
            soundfile.write(drums / "Kick.wav", _tone(80, 0.05), SAMPLE_RATE)
            (garageband_presets / "Picked Bass.exs").write_bytes(b"EXS fixture")
            (logic_presets / "Warm Piano.exs").write_bytes(b"EXS fixture")

            result = inventory_instruments(
                garageband_sampler_root=root / "sampler",
                logic_drum_root=root / "drums",
                garageband_instrument_root=root / "garageband-presets",
                logic_instrument_root=root / "logic-presets",
                include_audio_units=False,
            ).to_dict()

            self.assertEqual(result["factory_sampler_asset_count"], 1)
            self.assertEqual(result["drum_kit_asset_count"], 1)
            self.assertEqual(result["sampler_instrument_preset_count"], 2)
            self.assertEqual(
                {item["name"] for item in result["sampler_instrument_presets"]},
                {"Picked Bass", "Warm Piano"},
            )
            self.assertEqual(result["factory_sampler_assets"][0]["sample_count"], 7)
            self.assertEqual(
                len(result["factory_sampler_assets"][0]["representative_sample_files"]),
                5,
            )
            self.assertNotIn("sample_files", result["factory_sampler_assets"][0])


class InstrumentMatchTests(unittest.TestCase):
    def test_related_presets_use_distinctive_words_and_deduplicate_names(self):
        presets = [
            SamplerInstrumentPreset("Bass 1", "Organ", "logic", "/Bass 1.exs"),
            SamplerInstrumentPreset(
                "Picked Rock Bass", "Bass", "logic", "/Logic/Picked.exs"
            ),
            SamplerInstrumentPreset(
                "Picked Rock Bass",
                "Bass",
                "garageband_sampler_instrument",
                "/GarageBand/Picked.exs",
            ),
        ]

        result = _related_sampler_presets("Picked Electric Bass", presets)

        self.assertEqual([item["name"] for item in result], ["Picked Rock Bass"])
        self.assertEqual(result[0]["source"], "garageband_sampler_instrument")

    def test_sound_match_ranks_similar_factory_asset_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._write_source(root)
            matching = root / "factory" / "Warm Tone"
            different = root / "factory" / "Noise"
            matching.mkdir(parents=True)
            different.mkdir(parents=True)
            soundfile.write(matching / "sample-C4.wav", _tone(261.63, 0.5), SAMPLE_RATE)
            random = np.random.default_rng(7)
            soundfile.write(
                different / "sample-C4.wav",
                (random.standard_normal(SAMPLE_RATE // 2) * 0.12).astype(np.float32),
                SAMPLE_RATE,
            )
            output = root / "match"

            report = match_instruments(
                stem,
                midi,
                kind="lead",
                out_dir=output,
                top=2,
                garageband_sampler_root=root / "factory",
                logic_drum_root=root / "missing-drums",
                include_gm=False,
                max_source_segments=4,
                max_samples_per_asset=2,
            )

            self.assertEqual(
                report["garageband_factory_matches"][0]["asset_name"], "Warm Tone"
            )
            self.assertTrue((output / "instrument_matches.json").is_file())
            self.assertTrue((output / "GARAGEBAND_AUDITION.md").is_file())
            self.assertTrue((output / "timbre_profiles.svg").is_file())
            saved = json.loads((output / "instrument_matches.json").read_text())
            self.assertEqual(saved["artifacts"]["profile_graph"], "timbre_profiles.svg")
            self.assertEqual(saved["track"]["selected_index"], 0)

    def test_sample_pack_extracts_unique_isolated_pitches_and_sfz_zones(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stem, midi = self._write_source(root)
            output = root / "sample-pack"

            report = build_sample_pack(
                stem,
                midi,
                kind="lead",
                out_dir=output,
                max_samples=8,
                instrument_name="Fixture Lead",
                render_preview=False,
            )

            self.assertEqual(report["sample_count"], 2)
            self.assertEqual(len(list((output / "samples").glob("*.wav"))), 2)
            sfz = (output / "sunofriend-instrument.sfz").read_text()
            self.assertIn("pitch_keycenter=60", sfz)
            self.assertIn("pitch_keycenter=64", sfz)
            self.assertIn("tune=", sfz)
            self.assertTrue((output / "sunofriend-instrument.sf2").is_file())
            if sys.platform == "darwin" and shutil.which("swift"):
                self.assertTrue(
                    (output / "sunofriend-instrument.aupreset").is_file()
                )
            self.assertTrue((output / "garageband-audition.mid").is_file())
            self.assertFalse((output / "garageband-audition.wav").exists())
            saved = json.loads((output / "sample_pack.json").read_text())
            self.assertEqual(saved["format_version"], 2)
            self.assertEqual(saved["instrument_name"], "Fixture Lead")
            self.assertEqual(saved["soundfont"]["zone_count"], 2)
            self.assertEqual(saved["artifacts"]["samples"], "samples")
            self.assertEqual(
                saved["artifacts"]["soundfont"], "sunofriend-instrument.sf2"
            )
            if sys.platform == "darwin" and shutil.which("swift"):
                self.assertEqual(
                    saved["artifacts"]["ausampler_preset"],
                    "sunofriend-instrument.aupreset",
                )
            self.assertIsNone(saved["artifacts"]["audition_wav"])
            self.assertTrue(all(item["isolated"] for item in saved["samples"]))
            self.assertEqual(saved["samples"][0]["low_key"], 54)
            self.assertEqual(saved["samples"][0]["high_key"], 62)
            self.assertEqual(saved["samples"][1]["low_key"], 63)
            self.assertEqual(saved["samples"][1]["high_key"], 70)

    @staticmethod
    def _write_source(root: Path) -> tuple[Path, Path]:
        duration = 1.3
        audio = np.zeros(round(duration * SAMPLE_RATE), dtype=np.float32)
        first = _tone(261.63, 0.35)
        second = _tone(329.63, 0.35, decay=1.0)
        start_one = round(0.10 * SAMPLE_RATE)
        start_two = round(0.70 * SAMPLE_RATE)
        audio[start_one : start_one + len(first)] = first
        audio[start_two : start_two + len(second)] = second
        stem = root / "lead.wav"
        midi = root / "lead.mid"
        soundfile.write(stem, audio, SAMPLE_RATE)
        write_midi_file(
            midi,
            [
                MidiTrack(
                    "Lead",
                    channel=0,
                    program=0,
                    notes=[
                        NoteEvent(0.10, 0.45, 60, 100),
                        NoteEvent(0.70, 1.05, 64, 96),
                    ],
                )
            ],
            bpm=120,
        )
        return stem, midi


class SoundFontTests(unittest.TestCase):
    @unittest.skipUnless(
        sys.platform == "darwin" and shutil.which("swift"),
        "AUSampler preset generation requires macOS and Swift",
    )
    def test_writes_garageband_selectable_ausampler_preset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "A3.wav"
            soundfile.write(sample, _tone(220.0, 0.3), SAMPLE_RATE)
            soundfont_path = root / "instrument.sf2"
            write_soundfont(
                soundfont_path,
                [SoundFontZone(sample, root_key=57, low_key=51, high_key=63)],
                name="Preset Fixture",
            )
            preset_path = root / "instrument.aupreset"

            summary = write_ausampler_preset(soundfont_path, preset_path)

            self.assertEqual(summary["path"], "instrument.aupreset")
            with preset_path.open("rb") as handle:
                state = plistlib.load(handle)
            self.assertEqual(state["type"], 1635085685)
            self.assertEqual(state["subtype"], 1935764848)
            self.assertIn(str(soundfont_path.resolve()), state["file-references"].values())

    def test_tuning_estimate_corrects_a_stably_sharp_sample(self):
        sharp_hz = 440.0 * 2.0 ** (18.0 / 1200.0)

        result = _estimate_sample_tuning(
            _tone(sharp_hz, 0.8), SAMPLE_RATE, 69, enabled=True
        )

        self.assertEqual(result["status"], "applied")
        self.assertAlmostEqual(result["offset_cents"], 18.0, delta=3.0)
        self.assertAlmostEqual(result["pitch_correction_cents"], -18, delta=3)

    def test_tuning_estimate_can_be_disabled(self):
        result = _estimate_sample_tuning(
            _tone(440.0, 0.2), SAMPLE_RATE, 69, enabled=False
        )

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["pitch_correction_cents"], 0)

    def test_writes_self_contained_multizone_soundfont(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            low = root / "C3.wav"
            high = root / "G3.wav"
            soundfile.write(low, _tone(130.81, 0.25), SAMPLE_RATE)
            soundfile.write(high, _tone(196.00, 0.25), SAMPLE_RATE)
            output = root / "instrument.sf2"

            summary = write_soundfont(
                output,
                [
                    SoundFontZone(low, root_key=48, low_key=0, high_key=54),
                    SoundFontZone(high, root_key=55, low_key=55, high_key=127),
                ],
                name="Fixture Bass",
            )

            self.assertEqual(summary.zone_count, 2)
            self.assertEqual(summary.sample_rates, (SAMPLE_RATE,))
            self.assertGreater(
                summary.byte_size, low.stat().st_size + high.stat().st_size
            )
            structure = inspect_soundfont(output)
            self.assertEqual(structure["format"], "SoundFont 2.01")
            self.assertEqual(structure["preset_count"], 1)
            self.assertEqual(structure["instrument_count"], 1)
            self.assertEqual(structure["sample_count"], 2)

    @unittest.skipUnless(
        sys.platform == "darwin" and shutil.which("swift"),
        "Apple AVAudioUnitSampler validation requires macOS and Swift",
    )
    def test_generated_soundfont_loads_in_apple_sampler(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "A3.wav"
            soundfile.write(sample, _tone(220.0, 0.3), SAMPLE_RATE)
            soundfont_path = root / "instrument.sf2"
            write_soundfont(
                soundfont_path,
                [SoundFontZone(sample, root_key=57, low_key=51, high_key=63)],
                name="Apple Fixture",
            )
            script = """
import AVFoundation
let sampler = AVAudioUnitSampler()
let url = URL(fileURLWithPath: CommandLine.arguments[1])
try sampler.loadSoundBankInstrument(
    at: url,
    program: 0,
    bankMSB: UInt8(kAUSampler_DefaultMelodicBankMSB),
    bankLSB: UInt8(kAUSampler_DefaultBankLSB)
)
print("loaded")
"""

            result = subprocess.run(
                [str(shutil.which("swift")), "-e", script, str(soundfont_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertIn("loaded", result.stdout)

    def test_generated_soundfont_renders_through_fluidsynth_when_available(self):
        try:
            find_fluidsynth()
        except RenderError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "A3.wav"
            soundfile.write(sample, _tone(220.0, 0.3), SAMPLE_RATE)
            soundfont_path = root / "instrument.sf2"
            write_soundfont(
                soundfont_path,
                [SoundFontZone(sample, root_key=57, low_key=0, high_key=127)],
                name="Render Fixture",
            )
            midi = root / "audition.mid"
            write_midi_file(
                midi,
                [MidiTrack("Audition", 0, 0, [NoteEvent(0.0, 0.25, 57, 100)])],
                bpm=120,
            )

            rendered = render_midi_to_wav(
                midi, root / "audition.wav", soundfont_path=soundfont_path
            )

            self.assertGreater(rendered.stat().st_size, 1024)
            audio, _ = soundfile.read(rendered, dtype="float32")
            self.assertGreater(float(np.max(np.abs(audio))), 0.01)


if __name__ == "__main__":
    unittest.main()
