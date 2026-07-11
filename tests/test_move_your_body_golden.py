"""Read-only regression checks for the released ``Move Your Body`` project.

The source stems and generated MIDI live under ``work/`` and are deliberately
not checked into git.  These tests therefore skip with a useful reason on a
clean CI checkout, while becoming a permanent timing/DAW regression whenever
the local golden assets are present.

No FluidSynth or SoundFont is needed for the structural checks.  The final
kick-to-stem timing check uses librosa through Sunofriend's production onset
extractor and skips independently when the optional audio dependencies are not
installed.
"""
from __future__ import annotations

import json
import plistlib
import statistics
import struct
import tempfile
import unittest
import wave
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "work" / "Move Your Body-D minor-130bpm-440hz"
OUTPUT_DIR = REPO_ROOT / "work" / "move-your-body"
SUMMARY_PATH = OUTPUT_DIR / "listen_all_summary.json"
ARRANGEMENT_PATH = OUTPUT_DIR / "full_arrangement.mid"
KICK_STEM = SOURCE_DIR / "Move Your Body-kick-D minor-130bpm-440hz.wav"
KICK_MIDI = OUTPUT_DIR / "kick_listened.mid"
BASS_STEM = SOURCE_DIR / "Move Your Body-bass-D minor-130bpm-440hz.wav"
BASS_MIDI = OUTPUT_DIR / "bass_listened.mid"
METRONOME_STEM = SOURCE_DIR / "Move Your Body-metronome-D minor-130bpm-440hz.wav"
CHORDS_PDF = SOURCE_DIR / "Move_Your_Body_chords.pdf"

# This is an optional second golden: the GarageBand session used for the
# released mix.  It is outside the repository and is only ever read.
GARAGEBAND_BUNDLE = Path.home() / "Music" / "GarageBand" / "Move your body.band"
GARAGEBAND_METADATA = GARAGEBAND_BUNDLE / "Alternatives" / "000" / "MetaData.plist"
GARAGEBAND_PROJECT_INFO = GARAGEBAND_BUNDLE / "Resources" / "ProjectInformation.plist"

EXPECTED_PARTS = (
    "Kick",
    "Snare",
    "Hat",
    "Cymbals",
    "Toms",
    "Other_Kit",
    "Bass",
    "Keys",
    "Pads",
    "Lead",
    "Strings",
    "Piano",
)

DRUM_PITCHES = {
    "Kick": {36},
    "Snare": {38},
    "Hat": {42, 46},
    "Cymbals": {49, 51},
    "Toms": {41, 45, 48, 50},
    "Other_Kit": {39},
}


@dataclass(frozen=True)
class MidiNote:
    start_tick: int
    end_tick: int
    channel: int
    pitch: int
    velocity: int


@dataclass
class MidiTrackData:
    name: str | None = None
    notes: list[MidiNote] = field(default_factory=list)
    tempo_events: list[tuple[int, int]] = field(default_factory=list)
    time_signatures: list[tuple[int, int, int]] = field(default_factory=list)
    programs: list[tuple[int, int, int]] = field(default_factory=list)
    has_end_of_track: bool = False


@dataclass
class MidiFileData:
    format: int
    ticks_per_beat: int
    declared_tracks: int
    tracks: list[MidiTrackData]

    @property
    def tempo_events(self) -> list[tuple[int, int]]:
        return sorted(event for track in self.tracks for event in track.tempo_events)

    def tick_to_seconds(self, tick: int) -> float:
        """Convert an absolute tick using the file's (possibly changing) tempo."""
        current_tick = 0
        current_tempo = 500_000  # Standard MIDI default: 120 BPM.
        seconds = 0.0
        for event_tick, micros_per_quarter in self.tempo_events:
            if event_tick > tick:
                break
            seconds += (
                (event_tick - current_tick)
                * current_tempo
                / 1_000_000
                / self.ticks_per_beat
            )
            current_tick = event_tick
            current_tempo = micros_per_quarter
        seconds += (
            (tick - current_tick)
            * current_tempo
            / 1_000_000
            / self.ticks_per_beat
        )
        return seconds


def _read_variable_length(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("truncated MIDI variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise ValueError("invalid MIDI variable-length quantity")


def _parse_track(data: bytes) -> MidiTrackData:
    track = MidiTrackData()
    tick = 0
    offset = 0
    running_status: int | None = None
    active: dict[tuple[int, int], deque[tuple[int, int]]] = defaultdict(deque)

    while offset < len(data):
        delta, offset = _read_variable_length(data, offset)
        tick += delta
        if offset >= len(data):
            raise ValueError("truncated MIDI event")

        status = data[offset]
        if status & 0x80:
            offset += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise ValueError("MIDI running status used before a channel status")

        if status == 0xFF:
            if offset >= len(data):
                raise ValueError("truncated MIDI meta event")
            meta_type = data[offset]
            offset += 1
            length, offset = _read_variable_length(data, offset)
            payload = data[offset : offset + length]
            if len(payload) != length:
                raise ValueError("truncated MIDI meta payload")
            offset += length
            if meta_type == 0x03:
                track.name = payload.decode("utf-8", errors="replace")
            elif meta_type == 0x51:
                if length != 3:
                    raise ValueError("tempo meta event must contain three bytes")
                track.tempo_events.append((tick, int.from_bytes(payload, "big")))
            elif meta_type == 0x58:
                if length != 4:
                    raise ValueError("time-signature event must contain four bytes")
                track.time_signatures.append((tick, payload[0], 2 ** payload[1]))
            elif meta_type == 0x2F:
                if length:
                    raise ValueError("end-of-track event must be empty")
                track.has_end_of_track = True
            continue

        if status in (0xF0, 0xF7):
            length, offset = _read_variable_length(data, offset)
            offset += length
            if offset > len(data):
                raise ValueError("truncated MIDI SysEx event")
            running_status = None
            continue

        event_type = status & 0xF0
        channel = status & 0x0F
        payload_length = 1 if event_type in (0xC0, 0xD0) else 2
        payload = data[offset : offset + payload_length]
        if len(payload) != payload_length:
            raise ValueError("truncated MIDI channel event")
        if any(byte & 0x80 for byte in payload):
            raise ValueError("invalid high bit in MIDI channel data")
        offset += payload_length

        if event_type == 0xC0:
            track.programs.append((tick, channel, payload[0]))
        elif event_type == 0x90 and payload[1] > 0:
            active[(channel, payload[0])].append((tick, payload[1]))
        elif event_type == 0x80 or (event_type == 0x90 and payload[1] == 0):
            key = (channel, payload[0])
            if not active[key]:
                raise ValueError(f"note-off without note-on at tick {tick}: {key}")
            start_tick, velocity = active[key].popleft()
            if tick <= start_tick:
                raise ValueError(f"non-positive MIDI note duration at tick {tick}: {key}")
            track.notes.append(MidiNote(start_tick, tick, channel, payload[0], velocity))
        elif event_type not in (0xA0, 0xB0, 0xD0, 0xE0):
            raise ValueError(f"unsupported MIDI status byte: 0x{status:02x}")

    dangling = {key: list(starts) for key, starts in active.items() if starts}
    if dangling:
        raise ValueError(f"MIDI track has dangling note-ons: {dangling}")
    if not track.has_end_of_track:
        raise ValueError("MIDI track has no end-of-track event")
    track.notes.sort(key=lambda note: (note.start_tick, note.pitch, note.end_tick))
    return track


def parse_midi(path: Path) -> MidiFileData:
    """Parse the SMF features used by the golden without a third-party package."""
    data = path.read_bytes()
    if data[:4] != b"MThd" or len(data) < 14:
        raise ValueError(f"not a Standard MIDI file: {path}")
    header_length = int.from_bytes(data[4:8], "big")
    if header_length < 6 or len(data) < 8 + header_length:
        raise ValueError(f"invalid MIDI header: {path}")
    midi_format, track_count, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("SMPTE MIDI time division is not supported by this golden")

    tracks: list[MidiTrackData] = []
    offset = 8 + header_length
    for _ in range(track_count):
        if data[offset : offset + 4] != b"MTrk" or offset + 8 > len(data):
            raise ValueError(f"missing MIDI track chunk in {path}")
        length = int.from_bytes(data[offset + 4 : offset + 8], "big")
        start = offset + 8
        end = start + length
        if end > len(data):
            raise ValueError(f"truncated MIDI track chunk in {path}")
        tracks.append(_parse_track(data[start:end]))
        offset = end
    if offset != len(data):
        raise ValueError(f"unexpected trailing bytes in {path}")
    return MidiFileData(midi_format, division, track_count, tracks)


def _manifest_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _require_paths(*paths: Path) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise unittest.SkipTest(
            "local Move Your Body golden assets are absent (work/ is intentionally "
            "git-ignored): " + ", ".join(missing)
        )


def _track_by_name(midi: MidiFileData, name: str) -> MidiTrackData:
    matches = [track for track in midi.tracks if track.name == name]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name!r} track, found {len(matches)}")
    return matches[0]


def _assert_constant_130_bpm(test: unittest.TestCase, midi: MidiFileData) -> None:
    test.assertEqual(len(midi.tempo_events), 1)
    tick, micros_per_quarter = midi.tempo_events[0]
    test.assertEqual(tick, 0)
    test.assertAlmostEqual(60_000_000 / micros_per_quarter, 130.0, delta=0.001)


class MoveYourBodyMidiGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _require_paths(SOURCE_DIR, SUMMARY_PATH, ARRANGEMENT_PATH, KICK_STEM, KICK_MIDI)
        cls.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        cls.arrangement = parse_midi(ARRANGEMENT_PATH)

    def test_manifest_preserves_the_released_project_settings(self) -> None:
        self.assertEqual(self.summary["bpm_nominal"], 130.0)
        self.assertEqual(self.summary["set_garageband_tempo_to"], 130.0)
        self.assertAlmostEqual(self.summary["bpm_true"], 130.016, delta=0.05)
        self.assertEqual(self.summary["key"], "D minor")
        self.assertTrue(self.summary["metronome"])
        self.assertTrue(self.summary["beat_wander"])
        self.assertEqual(_manifest_path(self.summary["folder"]).resolve(), SOURCE_DIR.resolve())
        self.assertEqual(
            _manifest_path(self.summary["arrangement"]).resolve(),
            ARRANGEMENT_PATH.resolve(),
        )
        self.assertTrue(_manifest_path(self.summary["chords_pdf"]).is_file())

        # The historical summary contains only the parts from its last partial
        # run.  Validate every entry it does claim without pretending it is a
        # complete arrangement manifest.
        self.assertGreater(len(self.summary["parts"]), 0)
        for part, entry in self.summary["parts"].items():
            with self.subTest(part=part):
                self.assertEqual(entry["status"], "ok")
                midi_path = _manifest_path(entry["midi"])
                self.assertTrue(midi_path.is_file())
                midi = parse_midi(midi_path)
                note_count = sum(len(track.notes) for track in midi.tracks)
                self.assertEqual(note_count, entry["notes"])

    def test_arrangement_is_valid_garageband_midi(self) -> None:
        midi = self.arrangement
        self.assertEqual(midi.format, 1)
        self.assertEqual(midi.ticks_per_beat, 480)
        self.assertEqual(midi.declared_tracks, len(midi.tracks))
        self.assertEqual(midi.declared_tracks, 1 + len(EXPECTED_PARTS))
        self.assertEqual(midi.tracks[0].name, "Tempo")
        self.assertEqual(midi.tracks[0].time_signatures, [(0, 4, 4)])
        _assert_constant_130_bpm(self, midi)

        musical_tracks = midi.tracks[1:]
        self.assertEqual(tuple(track.name for track in musical_tracks), EXPECTED_PARTS)
        self.assertTrue(all(track.has_end_of_track for track in midi.tracks))

        with wave.open(str(KICK_STEM), "rb") as source:
            source_duration = source.getnframes() / source.getframerate()

        all_notes = [note for track in musical_tracks for note in track.notes]
        self.assertGreater(len(all_notes), 3_000)
        self.assertGreater(max(midi.tick_to_seconds(note.end_tick) for note in all_notes), 160.0)
        self.assertLessEqual(
            max(midi.tick_to_seconds(note.end_tick) for note in all_notes),
            source_duration + 0.5,
        )

        for name, allowed_pitches in DRUM_PITCHES.items():
            with self.subTest(track=name):
                track = _track_by_name(midi, name)
                self.assertGreater(len(track.notes), 0)
                self.assertEqual({note.channel for note in track.notes}, {9})
                self.assertLessEqual({note.pitch for note in track.notes}, allowed_pitches)

        for name in set(EXPECTED_PARTS) - set(DRUM_PITCHES):
            with self.subTest(track=name):
                track = _track_by_name(midi, name)
                self.assertGreater(len(track.notes), 0)
                self.assertNotIn(9, {note.channel for note in track.notes})
                self.assertTrue(all(0 <= note.pitch <= 127 for note in track.notes))
                self.assertTrue(all(1 <= note.velocity <= 127 for note in track.notes))

    def test_standalone_parts_are_parseable_and_kick_matches_arrangement(self) -> None:
        expected_files = {
            part.lower(): OUTPUT_DIR / f"{part.lower()}_listened.mid"
            for part in EXPECTED_PARTS
        }
        for part, path in expected_files.items():
            with self.subTest(part=part):
                self.assertTrue(path.is_file(), f"missing standalone MIDI: {path}")
                midi = parse_midi(path)
                self.assertEqual(midi.format, 1)
                self.assertEqual(midi.ticks_per_beat, 480)
                self.assertEqual(midi.declared_tracks, 2)
                self.assertEqual(len(midi.tracks), 2)
                self.assertGreater(len(midi.tracks[1].notes), 0)
                _assert_constant_130_bpm(self, midi)

        arrangement_kick = _track_by_name(self.arrangement, "Kick").notes
        standalone_kick = parse_midi(KICK_MIDI).tracks[1].notes
        self.assertEqual(len(standalone_kick), 299)
        self.assertEqual(arrangement_kick, standalone_kick)


class MoveYourBodyAudioTimingGoldenTests(unittest.TestCase):
    """Slower source-audio check; independent of FluidSynth and SoundFonts."""

    @classmethod
    def setUpClass(cls) -> None:
        _require_paths(KICK_STEM, KICK_MIDI)
        try:
            # Imports NumPy at module import and librosa only when called.
            from sunofriend.compare import Onset, diff_drums, extract_onsets

            import librosa

            # librosa exposes much of its API lazily; touching ``load`` here
            # catches a half-installed stack (for example a missing resampy or
            # pkg_resources) before the test body starts.
            getattr(librosa, "load")
        except Exception as exc:
            raise unittest.SkipTest(
                f"optional librosa/NumPy audio dependencies are unavailable: {exc}"
            ) from exc
        cls.Onset = Onset
        cls.diff_drums = staticmethod(diff_drums)
        cls.extract_onsets = staticmethod(extract_onsets)

    def test_kick_has_low_timing_error_and_no_drift_against_source_stem(self) -> None:
        midi = parse_midi(KICK_MIDI)
        _assert_constant_130_bpm(self, midi)
        kick_notes = midi.tracks[1].notes
        midi_onsets = [self.Onset(midi.tick_to_seconds(note.start_tick), 1.0) for note in kick_notes]
        source_onsets = self.extract_onsets(str(KICK_STEM), delta=0.18)
        difference = self.diff_drums(source_onsets, midi_onsets, tolerance=0.05)

        signed_offsets = [candidate - reference for reference, candidate in difference.matched]
        absolute_offsets = sorted(abs(offset) for offset in signed_offsets)
        p95_index = max(0, int(0.95 * len(absolute_offsets)) - 1)

        with wave.open(str(KICK_STEM), "rb") as source:
            duration = source.getnframes() / source.getframerate()
        segment_medians_ms: list[float] = []
        segment_counts: list[int] = []
        for segment in range(4):
            start = segment * duration / 4
            end = (segment + 1) * duration / 4
            offsets = [
                candidate - reference
                for reference, candidate in difference.matched
                if start <= reference < end
            ]
            self.assertGreater(len(offsets), 20, f"too few matched kicks in segment {segment + 1}")
            segment_counts.append(len(offsets))
            segment_medians_ms.append(statistics.median(offsets) * 1_000)

        segment_drift_ms = max(segment_medians_ms) - min(segment_medians_ms)
        precision = len(difference.matched) / max(
            1, len(difference.matched) + len(difference.extra)
        )
        recall = len(difference.matched) / max(
            1, len(difference.matched) + len(difference.missed)
        )
        metrics = {
            "source_onsets": len(source_onsets),
            "midi_onsets": len(midi_onsets),
            "matched": len(difference.matched),
            "missed": len(difference.missed),
            "extra": len(difference.extra),
            "precision": round(precision, 5),
            "recall": round(recall, 5),
            "f_measure": round(difference.f_measure, 5),
            "median_abs_offset_ms": round(statistics.median(absolute_offsets) * 1_000, 3),
            "p95_abs_offset_ms": round(absolute_offsets[p95_index] * 1_000, 3),
            "segment_counts": segment_counts,
            "segment_median_signed_offset_ms": [round(value, 3) for value in segment_medians_ms],
            "segment_drift_ms": round(segment_drift_ms, 3),
        }
        print("Move Your Body kick timing: " + json.dumps(metrics, sort_keys=True), flush=True)

        # The direct MIDI precedes the stem transient slightly to compensate
        # for sampler attack.  Absolute alignment may therefore have a stable
        # offset; low segment-to-segment spread is the important drift guard.
        # Baseline observed on the released files: precision/recall 1.0,
        # median 17.474 ms, p95 17.944 ms, and four-segment drift 0.206 ms.
        # These bounds leave headroom for library/platform variation while
        # still failing a musically relevant regression.
        self.assertGreaterEqual(precision, 0.995, metrics)
        self.assertGreaterEqual(recall, 0.995, metrics)
        self.assertLessEqual(statistics.median(absolute_offsets), 0.025, metrics)
        self.assertLessEqual(absolute_offsets[p95_index], 0.030, metrics)
        self.assertLessEqual(segment_drift_ms, 2.0, metrics)


class MoveYourBodyGeneratedPipelineRegressionTests(unittest.TestCase):
    """Fast guards for generated-part safety and Clip v1 round-tripping."""

    def test_theory_locked_bass_does_not_gain_a_transcribed_high_note(self) -> None:
        _require_paths(BASS_STEM, BASS_MIDI, CHORDS_PDF)
        try:
            import numpy as np
        except Exception as exc:
            raise unittest.SkipTest(f"optional NumPy dependency is unavailable: {exc}") from exc

        from unittest.mock import patch

        from sunofriend.compare import PitchedNoteEvidence, PitchedReference
        from sunofriend.loop import refine_stem
        from sunofriend.models import NoteEvent

        bass = parse_midi(BASS_MIDI)
        source_note = bass.tracks[1].notes[0]
        seed = NoteEvent(
            bass.tick_to_seconds(source_note.start_tick),
            bass.tick_to_seconds(source_note.end_tick),
            source_note.pitch,
            source_note.velocity,
        )
        # This deliberately satisfies the generic three-signal addition gate,
        # but is three octaves above an actual Move Your Body bass note.  A
        # theory-generated bass must keep its composed note structure instead
        # of absorbing a raw transcription hypothesis during refinement.
        unsafe_note = NoteEvent(
            seed.start,
            seed.end,
            seed.pitch + 36,
            seed.velocity,
        )
        evidence = PitchedNoteEvidence(
            note=unsafe_note,
            confidence=0.96,
            spectral_support=0.4,
            onset_strength=0.9,
            sources=("transcription", "spectrum", "onset"),
        )

        class UniformSpectrum:
            @staticmethod
            def note_support(note: NoteEvent) -> float:
                return 0.4

        reference = PitchedReference(notes=[evidence], spectrum=UniformSpectrum())
        unit_chroma = np.full((12, 256), 1.0 / np.sqrt(12.0))

        def fake_render(_midi_path, wav_path) -> None:
            Path(wav_path).touch()

        with tempfile.TemporaryDirectory() as directory, patch(
            "sunofriend.loop._seed_pitched", return_value=[seed]
        ), patch(
            "sunofriend.loop.render_midi_to_wav", side_effect=fake_render
        ), patch(
            "sunofriend.compare.extract_onsets", return_value=[]
        ), patch(
            "sunofriend.compare.chroma_matrix", return_value=unit_chroma
        ), patch(
            "sunofriend.compare.analyze_pitched_reference", return_value=reference
        ):
            result = refine_stem(
                BASS_STEM,
                kind="bass",
                bpm=130.0,
                out_dir=directory,
                max_iterations=2,
                chords_pdf=CHORDS_PDF,
                key="D minor",
                output_bpm=130.0,
            )

        self.assertEqual(result.notes, [seed])

    def test_stem_locked_archive_export_keeps_move_your_body_note_times(self) -> None:
        _require_paths(KICK_STEM, KICK_MIDI, METRONOME_STEM)
        try:
            from sunofriend.beatgrid import grid_from_metronome

            grid = grid_from_metronome(str(METRONOME_STEM), nominal_bpm=130.0)
        except Exception as exc:
            raise unittest.SkipTest(
                f"optional metronome-analysis dependencies are unavailable: {exc}"
            ) from exc

        from sunofriend.clip import write_clip_midi
        from sunofriend.listen_all import _make_library_clip
        from sunofriend.models import NoteEvent

        source_midi = parse_midi(KICK_MIDI)
        source_notes = source_midi.tracks[1].notes[:32]
        notes = [
            NoteEvent(
                source_midi.tick_to_seconds(note.start_tick),
                source_midi.tick_to_seconds(note.end_tick),
                note.pitch,
                note.velocity,
            )
            for note in source_notes
        ]
        clip = _make_library_clip(
            title="Move Your Body kick timing regression",
            name="kick",
            kind="kick",
            stem=KICK_STEM,
            midi=KICK_MIDI,
            notes=notes,
            score=1.0,
            key="D minor",
            grid=grid,
            daw_bpm=130.0,
        )
        self.assertEqual(clip.provenance.details_dict["timing_mode"], "stem_locked")
        self.assertGreater(grid.time_of(0), 0.15)

        with tempfile.TemporaryDirectory() as directory:
            exported_path = Path(directory) / "kick-from-library.mid"
            # Default/auto export must honor the stem-locked provenance and
            # use the source-second positions, including the intro offset.
            write_clip_midi(exported_path, clip)
            exported = parse_midi(exported_path)

        actual_starts = [
            exported.tick_to_seconds(note.start_tick) for note in exported.tracks[1].notes
        ]
        expected_starts = [note.start for note in notes]
        errors = [actual - expected for actual, expected in zip(actual_starts, expected_starts)]
        self.assertEqual(len(actual_starts), len(expected_starts))
        # At 130 BPM/480 PPQ one tick is 0.962 ms.  This permits one tick of
        # rounding but decisively catches the historical ~175 ms displacement.
        self.assertLessEqual(max(abs(error) for error in errors), 0.001)
        self.assertLessEqual(abs(statistics.median(errors)), 0.0005)


class MoveYourBodyGarageBandGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [
            str(path)
            for path in (GARAGEBAND_METADATA, GARAGEBAND_PROJECT_INFO)
            if not path.is_file()
        ]
        if missing:
            raise unittest.SkipTest(
                "local released GarageBand bundle is unavailable: " + ", ".join(missing)
            )
        with GARAGEBAND_METADATA.open("rb") as handle:
            cls.metadata = plistlib.load(handle)
        with GARAGEBAND_PROJECT_INFO.open("rb") as handle:
            cls.project_info = plistlib.load(handle)

    def test_released_garageband_session_matches_sunofriend_project(self) -> None:
        self.assertEqual(self.metadata["BeatsPerMinute"], 130.0)
        self.assertEqual(self.metadata["SongKey"], "D")
        self.assertEqual(self.metadata["SongGenderKey"], "minor")
        self.assertEqual(self.metadata["SongSignatureNumerator"], 4)
        self.assertEqual(self.metadata["SongSignatureDenominator"], 4)
        self.assertEqual(self.metadata["SampleRate"], 44_100)
        self.assertEqual(self.metadata["NumberOfTracks"], 61)
        self.assertIn("GarageBand 10.4.13", self.project_info["LastSavedFrom"])

        sampler_files = "\n".join(self.metadata["SamplerInstrumentsFiles"])
        self.assertIn("Modern 909", sampler_files)
        self.assertIn("Upright Jazz Bass", sampler_files)
        self.assertIn("Different Phases Clav", sampler_files)
        self.assertIn("Strings_consolidated", sampler_files)
        self.assertTrue(
            any("Move Your Body-kick-D minor-130bpm-440hz.wav" in path for path in self.metadata["AudioFiles"])
        )


if __name__ == "__main__":
    unittest.main()
