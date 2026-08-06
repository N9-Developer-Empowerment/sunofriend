from __future__ import annotations

import hashlib
import tempfile
import wave
from pathlib import Path

from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.simple_instruments import build_simple_instrument_handoff
from sunofriend.workbench_artifacts import build_arrangement_tracks


def test_sound_handoff_keeps_sources_and_assigns_shared_drum_and_keys_sounds() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "AUTOMATIC-SONG"
        output.mkdir()
        drum_midi = root / "kick.mid"
        keys_midi = root / "keys.mid"
        drum_preview = root / "kick.wav"
        keys_preview = root / "keys.wav"
        write_midi_file(
            drum_midi,
            [MidiTrack("Kick", 9, 0, [NoteEvent(0.2, 0.3, 36, 100)])],
            bpm=120,
        )
        write_midi_file(
            keys_midi,
            [MidiTrack("Keys", 0, 7, [NoteEvent(0.1, 0.6, 60, 90)])],
            bpm=120,
        )
        _write_wav(drum_preview, sample=800)
        _write_wav(keys_preview, sample=1_200)
        selection = [
            _selection(1, "kick", drum_midi),
            _selection(2, "keys", keys_midi),
        ]
        lanes = [
            {"preview_path": str(drum_preview)},
            {"preview_path": str(keys_preview)},
        ]
        combined = build_arrangement_tracks(selection)
        source_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (drum_midi, keys_midi)
        }

        result = build_simple_instrument_handoff(
            selection,
            lanes,
            combined,
            root=output,
            bpm=120,
        )

        rows = result["plan"]["tracks"]
        assert rows[0]["starter_sound"]["name"] == "Standard Drum Kit"
        assert rows[0]["starter_sound"]["combined_midi_channel_one_based"] == 10
        assert rows[1]["starter_sound"]["name"] == "Electric Piano 1"
        assert rows[1]["starter_sound"]["program_zero_based"] == 4
        assert rows[1]["starter_sound"]["general_midi_number"] == 5
        drum_proxy = output / rows[0]["starter_sound_midi"]["archive_path"]
        keys_proxy = output / rows[1]["starter_sound_midi"]["archive_path"]
        assert read_midi_clips(drum_proxy)[0].instrument.channel == 9
        assert read_midi_clips(keys_proxy)[0].instrument.program == 4
        assert all(
            (output / row["starter_sound_preview"]["archive_path"]).is_file()
            for row in rows
        )
        assert result["plan"]["effects"]["source_midi_mutated"] is False
        assert result["plan"]["effects"]["automatic_factory_match_selection"] is False
        assert source_hashes == {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (drum_midi, keys_midi)
        }


def _selection(index: int, role: str, midi: Path) -> dict:
    return {
        "selection_index": index,
        "role": role,
        "decision": "automatic-baseline",
        "midi_path": str(midi),
        "midi": {
            "sha256": hashlib.sha256(midi.read_bytes()).hexdigest(),
            "bytes": midi.stat().st_size,
        },
        "garageband_pack_archive_member": (
            f"MIDI/{index:02d}-{role}-automatic-primary.mid"
        ),
    }


def _write_wav(path: Path, *, sample: int) -> None:
    frame = int(sample).to_bytes(2, "little", signed=True)
    with wave.open(str(path), mode="wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(frame * 44_100)
