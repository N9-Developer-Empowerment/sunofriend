from __future__ import annotations

import hashlib
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import Instrument, read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.role_semantics import is_drum_role, normalize_role
from sunofriend.workbench_artifacts import (
    WorkbenchArtifacts,
    _arrangement_tracks,
)
from sunofriend.workbench_mix import is_drum_role as mix_is_drum_role
from sunofriend.workbench_timeline import build_stem_timeline
from sunofriend.workbench_transform import _is_drum_family


class RoleSemanticsTests(unittest.TestCase):
    def test_canonical_and_descriptive_drum_roles_are_recognised(self) -> None:
        roles = (
            "drums",
            "percussion",
            "kick drum",
            "electronic drums",
            "acoustic drums",
            "floor tom",
            "ride cymbal",
            "closed hi-hat",
            "other_kit",
            "otherkit",
            "drumkit",
            "drumset",
            "hihat",
            "kit",
            "shaker",
            "hand clap",
            "tambourine",
            "congas",
            "bongos",
            "cowbell",
            "maracas",
            "woodblock",
            "cabasa",
            "triangle",
        )

        for role in roles:
            with self.subTest(role=role):
                self.assertTrue(is_drum_role(role))
                self.assertTrue(Instrument(role, channel=0).is_drums)
                self.assertTrue(mix_is_drum_role(role))

    def test_pitched_and_substring_false_positives_remain_melodic(self) -> None:
        roles = (
            "steel drums",
            "steel drum",
            "tool kit",
            "tomorrow lead",
            "kickoff synth",
            "hatred vocals",
            "drumless mix",
            "percussive keys",
            "whatever",
            "keys",
        )

        for role in roles:
            with self.subTest(role=role):
                self.assertFalse(is_drum_role(role))
                instrument = Instrument(role, channel=0)
                self.assertFalse(instrument.is_drums)
                self.assertFalse(mix_is_drum_role(role))

    def test_explicit_midi_percussion_channel_remains_authoritative(self) -> None:
        self.assertTrue(Instrument("steel drums", channel=9).is_drums)

    def test_normalization_is_case_and_separator_stable(self) -> None:
        self.assertEqual(normalize_role("  Closed_HI-HAT!  "), "closed hi hat")

    def test_workbench_transform_uses_the_same_role_contract(self) -> None:
        drum_clip = _read_single_clip("kick drum")
        pitched_clip = _read_single_clip("steel drums")

        self.assertTrue(_is_drum_family(drum_clip))
        self.assertFalse(_is_drum_family(pitched_clip))

    def test_neutral_renderer_dry_proxy_balance_and_timeline_agree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            catalog = _role_catalog(root, ("percussion", "kick drum"))
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            rendered_channels: list[int] = []

            def fake_render(midi_path, wav_path, **_kwargs):
                channels = {
                    clip.instrument.channel for clip in read_midi_clips(midi_path)
                }
                self.assertEqual(channels, {9})
                rendered_channels.append(next(iter(channels)))
                Path(wav_path).write_bytes(b"RIFF" + b"\0" * 64)
                return Path(wav_path)

            previews = []
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=fake_render,
            ):
                for stem in catalog["stems"]:
                    candidate = stem["candidates"][0]
                    preview = artifacts.render_candidate_preview(
                        catalog,
                        stem["stem_id"],
                        candidate["candidate_id"],
                    )
                    previews.append(preview)
                    timeline = build_stem_timeline(
                        catalog,
                        stem["stem_id"],
                        waveform_bins=64,
                    )
                    self.assertTrue(mix_is_drum_role(stem["role"]))
                    self.assertEqual(
                        timeline["candidates"][0]["display_mode"],
                        "drum-grid",
                    )
                    self.assertEqual(
                        {
                            track["display_mode"]
                            for track in timeline["candidates"][0]["tracks"]
                        },
                        {"drum-grid"},
                    )

            self.assertEqual(rendered_channels, [9, 9])
            self.assertEqual(
                {preview["policy"] for preview in previews},
                {"role-neutral-general-midi-v2"},
            )
            self.assertEqual({preview["channel"] for preview in previews}, {9})

            selection = [
                {
                    "stem_id": stem["stem_id"],
                    "candidate_id": stem["candidates"][0]["candidate_id"],
                    "midi_path": stem["candidates"][0]["midi_path"],
                    "role": stem["role"],
                    "decision": "main",
                }
                for stem in catalog["stems"]
            ]
            dry_proxy_tracks = _arrangement_tracks(selection)
            self.assertEqual(len(dry_proxy_tracks), 1)
            self.assertEqual(dry_proxy_tracks[0].channel, 9)
            self.assertEqual(len(dry_proxy_tracks[0].notes), 2)


def _read_single_clip(role: str):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "role.mid"
        _write_midi(path, pitch=60)
        return read_midi_clips(path, role=role)[0]


def _role_catalog(root: Path, roles: tuple[str, ...]) -> dict:
    stems = []
    for index, role in enumerate(roles):
        source = root / f"source-{index}.wav"
        _write_pcm_wav(source)
        midi = root / f"candidate-{index}.mid"
        _write_midi(midi, pitch=36 + index)
        stems.append(
            {
                "stem_id": f"stem-{index}",
                "role": role,
                "source": _record(source),
                "candidates": [
                    {
                        "candidate_id": f"candidate-{index}",
                        "midi_path": str(midi.resolve()),
                        "midi": _record(midi),
                        "primary": True,
                        "diagnostic_only": False,
                        "audition_blocked": False,
                    }
                ],
            }
        )
    return {
        "project_id": "role-semantics-test",
        "setup": {"bpm": 120.0},
        "stems": stems,
    }


def _write_midi(path: Path, *, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name="Role fixture",
                channel=0,
                program=0,
                notes=[
                    NoteEvent(
                        start=0.0,
                        end=0.5,
                        pitch=pitch,
                        velocity=90,
                    )
                ],
            )
        ],
        bpm=120.0,
    )


def _write_pcm_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\0\0" * 8_000)


def _record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


if __name__ == "__main__":
    unittest.main()
