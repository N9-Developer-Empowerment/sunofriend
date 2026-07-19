from __future__ import annotations

import io
import json
import plistlib
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend.cli import main
from sunofriend.garageband import inspect_project
from sunofriend.playback import PlaybackError, choose_output_port, list_output_ports
from sunofriend.render import RenderError, find_fluidsynth, find_soundfont


class PlaybackTests(unittest.TestCase):
    def test_port_selection_prefers_unique_iac_and_supports_substring(self):
        ports = ["External Keyboard", "IAC Driver Bus 1"]
        self.assertEqual(choose_output_port(None, ports), "IAC Driver Bus 1")
        self.assertEqual(choose_output_port("keyboard", ports), "External Keyboard")

    def test_port_selection_reports_ambiguity_and_no_ports(self):
        with self.assertRaises(PlaybackError):
            choose_output_port("bus", ["IAC Bus 1", "IAC Bus 2"])
        with self.assertRaisesRegex(PlaybackError, "Audio MIDI Setup"):
            choose_output_port(None, [])

    def test_backend_initialisation_error_is_reported_as_playback_error(self):
        try:
            import mido  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"optional mido dependency is unavailable: {exc}")
        with patch("mido.get_output_names", side_effect=RuntimeError("rtmidi missing")):
            with self.assertRaisesRegex(PlaybackError, "CoreMIDI backend"):
                list_output_ports()

    def test_doctor_fails_when_no_coremidi_destination_is_available(self):
        stdout = io.StringIO()
        with patch("sunofriend.diagnostics.importlib_metadata.version", return_value="1.0"), patch(
            "sunofriend.render.find_fluidsynth", return_value="/bin/true"
        ), patch(
            "sunofriend.render.find_soundfont", return_value="/tmp/test.sf2"
        ), patch("sunofriend.render.render_midi_to_wav") as render, patch(
            "sunofriend.playback.list_output_ports", return_value=[]
        ) as list_ports, redirect_stdout(stdout):
            render.side_effect = lambda _midi, wav: Path(wav).write_bytes(b"RIFF" * 300)
            result = main(["doctor"])

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 1)
        self.assertTrue(report["listen_ready"])
        self.assertFalse(report["midi_ready"])
        self.assertFalse(report["ready"])
        self.assertEqual(report["required_capability"], "all")
        self.assertFalse(report["midi_check_skipped"])
        list_ports.assert_called_once_with()

    def test_doctor_can_require_conversion_without_a_midi_destination(self):
        stdout = io.StringIO()
        with patch(
            "sunofriend.diagnostics.importlib_metadata.version", return_value="1.0"
        ), patch(
            "sunofriend.render.find_fluidsynth", return_value="/bin/true"
        ), patch(
            "sunofriend.render.find_soundfont", return_value="/tmp/test.sf2"
        ), patch("sunofriend.render.render_midi_to_wav") as render, patch(
            "sunofriend.playback.list_output_ports"
        ) as list_ports, redirect_stdout(stdout):
            render.side_effect = lambda _midi, wav: Path(wav).write_bytes(b"RIFF" * 300)
            result = main(["doctor", "--require", "convert"])

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(report["convert_ready"])
        self.assertFalse(report["playback_ready"])
        self.assertTrue(report["requirement_ready"])
        self.assertTrue(report["midi_check_skipped"])
        list_ports.assert_not_called()

    def test_doctor_preview_requirement_does_not_initialise_coremidi(self):
        stdout = io.StringIO()
        with patch(
            "sunofriend.diagnostics.importlib_metadata.version", return_value="1.0"
        ), patch(
            "sunofriend.render.find_fluidsynth", return_value="/bin/true"
        ), patch(
            "sunofriend.render.find_soundfont", return_value="/tmp/test.sf2"
        ), patch("sunofriend.render.render_midi_to_wav") as render, patch(
            "sunofriend.playback.list_output_ports"
        ) as list_ports, redirect_stdout(stdout):
            render.side_effect = lambda _midi, wav: Path(wav).write_bytes(b"RIFF" * 300)
            result = main(["doctor", "--require", "preview"])

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(report["preview_ready"])
        self.assertTrue(report["requirement_ready"])
        self.assertTrue(report["midi_check_skipped"])
        self.assertFalse(report["playback_ready"])
        list_ports.assert_not_called()

    def test_doctor_playback_requirement_still_initialises_coremidi(self):
        stdout = io.StringIO()
        with patch(
            "sunofriend.diagnostics.importlib_metadata.version", return_value="1.0"
        ), patch(
            "sunofriend.render.find_fluidsynth", return_value="/bin/true"
        ), patch(
            "sunofriend.render.find_soundfont", return_value="/tmp/test.sf2"
        ), patch("sunofriend.render.render_midi_to_wav") as render, patch(
            "sunofriend.playback.list_output_ports", return_value=["IAC Driver Bus 1"]
        ) as list_ports, redirect_stdout(stdout):
            render.side_effect = lambda _midi, wav: Path(wav).write_bytes(b"RIFF" * 300)
            result = main(["doctor", "--require", "playback"])

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(report["playback_ready"])
        self.assertTrue(report["requirement_ready"])
        self.assertFalse(report["midi_check_skipped"])
        list_ports.assert_called_once_with()

    def test_doctor_can_require_transcription_without_fluidsynth(self):
        stdout = io.StringIO()
        with patch(
            "sunofriend.diagnostics.importlib_metadata.version", return_value="1.0"
        ), patch(
            "sunofriend.render.find_fluidsynth",
            side_effect=RenderError("fluidsynth unavailable"),
        ), patch("sunofriend.playback.list_output_ports") as list_ports, redirect_stdout(
            stdout
        ):
            result = main(["doctor", "--require", "transcribe"])

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(report["transcribe_ready"])
        self.assertFalse(report["convert_ready"])
        self.assertFalse(report["preview_ready"])
        self.assertTrue(report["requirement_ready"])
        self.assertTrue(report["midi_check_skipped"])
        list_ports.assert_not_called()

    def test_invalid_render_overrides_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {"SUNOFRIEND_FLUIDSYNTH": directory, "SUNOFRIEND_SF2": directory},
            clear=False,
        ):
            with self.assertRaisesRegex(RenderError, "executable file"):
                find_fluidsynth()
            with self.assertRaisesRegex(RenderError, "SoundFont file"):
                find_soundfont()


class GarageBandInspectorTests(unittest.TestCase):
    def test_reads_supported_bundle_metadata_without_projectdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "Golden.band"
            resources = bundle / "Resources"
            alternative = bundle / "Alternatives" / "000"
            resources.mkdir(parents=True)
            alternative.mkdir(parents=True)
            with (resources / "ProjectInformation.plist").open("wb") as handle:
                plistlib.dump({"LastSavedFrom": "GarageBand 10.4.13 (6514)"}, handle)
            with (alternative / "MetaData.plist").open("wb") as handle:
                plistlib.dump(
                    {
                        "BeatsPerMinute": 130,
                        "SongKey": "D",
                        "SongGenderKey": "minor",
                        "SongSignatureNumerator": 4,
                        "SongSignatureDenominator": 4,
                        "SampleRate": 44100,
                        "NumberOfTracks": 61,
                        "AudioFiles": ["Audio Files/kick.wav"],
                        "SamplerInstrumentsFiles": [
                            "/Library/Logic/Modern 909/Kick_1_Modern909.aif",
                            "/Library/GarageBand/Upright Jazz Bass/sample",
                        ],
                    },
                    handle,
                )

            result = inspect_project(bundle)

        self.assertEqual(result.bpm, 130.0)
        self.assertEqual((result.key, result.mode), ("D", "minor"))
        self.assertEqual(result.time_signature, "4/4")
        self.assertEqual(result.track_count, 61)
        self.assertEqual(result.instrument_assets, ("Modern 909", "Upright Jazz Bass"))


if __name__ == "__main__":
    unittest.main()
