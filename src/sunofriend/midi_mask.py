"""Experimental MIDI-informed target/residual cleanup for short audio excerpts.

This is deliberately a transparent DSP baseline, not a claimed source
separator.  A selected MIDI track opens narrow time/frequency regions around
its notes and harmonics.  The residual is then defined from the reconstructed
target in the waveform domain so target plus residual remains auditable.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any


MIDI_MASK_SCHEMA = "sunofriend.midi-mask.v1"
MAXIMUM_EXCERPT_SECONDS = 60.0


def create_midi_mask(
    audio_path: str | Path,
    midi_path: str | Path,
    *,
    out_dir: str | Path,
    track_index: int | None = None,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    harmonics: int = 8,
    bandwidth_cents: float = 55.0,
    attack_seconds: float = 0.06,
    release_seconds: float = 0.12,
    transient_seconds: float = 0.0,
    transient_strength: float = 0.35,
    n_fft: int = 4096,
    hop_length: int = 512,
) -> dict[str, Any]:
    """Write a fresh MIDI-guided target/residual experiment and its audit."""

    import librosa
    import numpy as np
    import soundfile

    audio = Path(audio_path).expanduser().absolute()
    midi = Path(midi_path).expanduser().absolute()
    destination = Path(out_dir).expanduser().absolute()
    _validate_paths(audio, midi, destination)
    _validate_parameters(
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        harmonics=harmonics,
        bandwidth_cents=bandwidth_cents,
        attack_seconds=attack_seconds,
        release_seconds=release_seconds,
        transient_seconds=transient_seconds,
        transient_strength=transient_strength,
        n_fft=n_fft,
        hop_length=hop_length,
    )

    clips = _read_guide_clips(midi)
    selected_index, clip = _select_guide_clip(clips, track_index)
    with soundfile.SoundFile(str(audio)) as handle:
        sample_rate = int(handle.samplerate)
        source_channels = int(handle.channels)
        source_frames = int(len(handle))
        source_duration = source_frames / sample_rate
        end = source_duration if end_seconds is None else float(end_seconds)
        start = float(start_seconds)
        if end > source_duration + 1.0 / sample_rate:
            raise ValueError(
                f"end_seconds exceeds the {source_duration:.6f}-second source"
            )
        duration = end - start
        if duration > MAXIMUM_EXCERPT_SECONDS:
            raise ValueError(
                "midi-mask is a short experimental workflow; choose an excerpt "
                f"of at most {MAXIMUM_EXCERPT_SECONDS:g} seconds"
            )
        start_frame = int(round(start * sample_rate))
        end_frame = min(source_frames, int(round(end * sample_rate)))
        handle.seek(start_frame)
        source = handle.read(
            end_frame - start_frame, dtype="float32", always_2d=True
        )
    if not len(source):
        raise ValueError("The requested excerpt contains no audio frames")
    if not np.all(np.isfinite(source)):
        raise ValueError("Source audio contains non-finite samples")

    notes = [
        note
        for note in clip.notes
        if note.source_end_seconds > start and note.source_start_seconds < end
    ]
    if not notes:
        raise ValueError("The selected MIDI track has no notes in this excerpt")

    spectra = np.stack(
        [
            librosa.stft(
                source[:, channel],
                n_fft=n_fft,
                hop_length=hop_length,
                win_length=n_fft,
                window="hann",
                center=True,
            )
            for channel in range(source.shape[1])
        ],
        axis=0,
    )
    frame_times = start + np.arange(spectra.shape[-1]) * hop_length / sample_rate
    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)
    mask = _guide_mask(
        frequencies,
        frame_times,
        notes,
        harmonics=harmonics,
        bandwidth_cents=bandwidth_cents,
        attack_seconds=attack_seconds,
        release_seconds=release_seconds,
        transient_seconds=transient_seconds,
        transient_strength=transient_strength,
    )
    target_spectra = spectra * mask[np.newaxis, :, :]
    target = np.stack(
        [
            librosa.istft(
                target_spectra[channel],
                hop_length=hop_length,
                win_length=n_fft,
                window="hann",
                center=True,
                length=len(source),
            )
            for channel in range(source.shape[1])
        ],
        axis=1,
    ).astype("float32")
    residual = (source - target).astype("float32")

    destination.parent.mkdir(parents=True, exist_ok=True)
    work = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    work.mkdir(parents=False, exist_ok=False)
    try:
        from .midi import MidiTrack, write_midi_file
        from .models import NoteEvent

        source_output = work / "source-excerpt.wav"
        target_output = work / "target.wav"
        residual_output = work / "residual.wav"
        guide_output = work / "guide-excerpt.mid"
        guide_notes = [
            NoteEvent(
                start=max(start, note.source_start_seconds) - start,
                end=min(end, note.source_end_seconds) - start,
                pitch=note.pitch,
                velocity=note.velocity,
            )
            for note in notes
            if min(end, note.source_end_seconds)
            > max(start, note.source_start_seconds)
        ]
        write_midi_file(
            guide_output,
            [
                MidiTrack(
                    name=f"{clip.title} guide excerpt",
                    channel=clip.instrument.channel,
                    program=clip.instrument.program,
                    notes=guide_notes,
                )
            ],
            bpm=clip.bpm,
        )
        # PCM24 is deterministic across repeat builds and imports directly in
        # GarageBand. libsndfile's float-WAV PEAK chunk embeds a changing
        # timestamp, which makes otherwise identical evidence hash differently.
        soundfile.write(source_output, source, sample_rate, subtype="PCM_24")
        soundfile.write(target_output, target, sample_rate, subtype="PCM_24")
        soundfile.write(residual_output, residual, sample_rate, subtype="PCM_24")

        persisted_source, persisted_rate = soundfile.read(
            source_output, dtype="float32", always_2d=True
        )
        persisted_target, _ = soundfile.read(
            target_output, dtype="float32", always_2d=True
        )
        persisted_residual, _ = soundfile.read(
            residual_output, dtype="float32", always_2d=True
        )
        reconstruction_error = persisted_source - (
            persisted_target + persisted_residual
        )
        maximum_error = float(np.max(np.abs(reconstruction_error)))
        rms_error = _rms(reconstruction_error)
        source_rms = _rms(persisted_source)
        target_rms = _rms(persisted_target)
        residual_rms = _rms(persisted_residual)
        reconstruction_passed = maximum_error <= 1e-6

        report: dict[str, Any] = {
            "schema": MIDI_MASK_SCHEMA,
            "status": "complete" if reconstruction_passed else "review-required",
            "operation": "midi-mask",
            "purpose": (
                "Transparent MIDI-informed DSP baseline; not a physical-instrument "
                "identification or a promoted source separation."
            ),
            "source": {
                "path": str(audio),
                "sha256": _sha256(audio),
                "sample_rate": sample_rate,
                "channels": source_channels,
                "frames": source_frames,
                "duration_seconds": round(source_duration, 9),
            },
            "guide_midi": {
                "path": str(midi),
                "sha256": _sha256(midi),
                "available_tracks": [item.title for item in clips],
                "selected_track_index": selected_index,
                "selected_track": clip.title,
                "selected_role": clip.instrument.role,
                "selected_program": clip.instrument.program,
                "selected_channel": clip.instrument.channel,
                "selected_track_note_count": len(clip.notes),
                "excerpt_note_count": len(notes),
                "excerpt_pitches": sorted({int(note.pitch) for note in notes}),
                "excerpt_midi_bpm": clip.bpm,
                "boundary_clipped_note_count": sum(
                    note.source_start_seconds < start or note.source_end_seconds > end
                    for note in notes
                ),
            },
            "excerpt": {
                "start_seconds": round(start, 9),
                "end_seconds": round(end, 9),
                "duration_seconds": round(len(source) / sample_rate, 9),
                "frames": len(source),
            },
            "parameters": {
                "harmonics": harmonics,
                "bandwidth_cents": bandwidth_cents,
                "attack_seconds": attack_seconds,
                "release_seconds": release_seconds,
                "transient_seconds": transient_seconds,
                "transient_strength": transient_strength,
                "n_fft": n_fft,
                "hop_length": hop_length,
                "maximum_excerpt_seconds": MAXIMUM_EXCERPT_SECONDS,
                "residual_definition": (
                    "source_excerpt minus reconstructed target in float32 waveform space"
                ),
            },
            "mask": {
                "minimum": round(float(np.min(mask)), 9),
                "maximum": round(float(np.max(mask)), 9),
                "mean": round(float(np.mean(mask)), 9),
                "p95": round(float(np.percentile(mask, 95.0)), 9),
                "active_bin_ratio": round(float(np.mean(mask > 0.01)), 9),
            },
            "energy": {
                "source_rms": round(source_rms, 12),
                "target_rms": round(target_rms, 12),
                "residual_rms": round(residual_rms, 12),
                "target_to_source_db": _relative_db(target_rms, source_rms),
                "residual_to_source_db": _relative_db(residual_rms, source_rms),
            },
            "reconstruction": {
                "maximum_absolute_error": round(maximum_error, 12),
                "rms_error": round(rms_error, 12),
                "threshold": 1e-6,
                "passed": reconstruction_passed,
                "persisted_pcm24_wavs_checked": True,
            },
            "artifacts": {
                "source_excerpt": _artifact(source_output),
                "target": _artifact(target_output),
                "residual": _artifact(residual_output),
                "guide_excerpt_midi": _artifact(guide_output),
                "report": "midi_mask.json",
            },
            "effects": {
                "source_audio_mutated": False,
                "guide_midi_mutated": False,
                "midi_notes_mutated": 0,
                "automatic_promotion": False,
                "target_plus_residual_reconstructs_source": reconstruction_passed,
            },
            "warnings": [
                "Harmonics shared by other simultaneous instruments can enter the target.",
                "Percussive attacks, effects, stereo ambience and unpitched energy may remain in the residual.",
                "An enabled broadband transient window can also admit simultaneous non-target attacks.",
                "Use the target and residual only as separate listening/transcription challengers.",
            ],
        }
        (work / "midi_mask.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        work.rename(destination)
        report["report"] = str(destination / "midi_mask.json")
        return report
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def _guide_mask(
    frequencies: Any,
    frame_times: Any,
    notes: list[Any],
    *,
    harmonics: int,
    bandwidth_cents: float,
    attack_seconds: float,
    release_seconds: float,
    transient_seconds: float,
    transient_strength: float,
) -> Any:
    import numpy as np

    mask = np.zeros((len(frequencies), len(frame_times)), dtype=np.float32)
    positive = frequencies > 0.0
    unique_pitches = sorted({int(note.pitch) for note in notes})
    for pitch in unique_pitches:
        spectral = np.zeros(len(frequencies), dtype=np.float32)
        fundamental = 440.0 * 2.0 ** ((pitch - 69.0) / 12.0)
        for harmonic in range(1, harmonics + 1):
            centre = fundamental * harmonic
            if centre >= frequencies[-1]:
                break
            cents = np.zeros(len(frequencies), dtype=np.float64)
            cents[positive] = 1200.0 * np.log2(frequencies[positive] / centre)
            weight = np.exp(-0.5 * (cents / bandwidth_cents) ** 2)
            weight[~positive] = 0.0
            spectral = np.maximum(spectral, weight.astype(np.float32))
        temporal = np.zeros(len(frame_times), dtype=np.float32)
        for note in notes:
            if int(note.pitch) != pitch:
                continue
            start = float(note.source_start_seconds)
            end = float(note.source_end_seconds)
            if attack_seconds > 0:
                before = (frame_times >= start - attack_seconds) & (frame_times < start)
                temporal[before] = np.maximum(
                    temporal[before],
                    ((frame_times[before] - (start - attack_seconds)) / attack_seconds).astype(
                        np.float32
                    ),
                )
            temporal[(frame_times >= start) & (frame_times <= end)] = 1.0
            if release_seconds > 0:
                after = (frame_times > end) & (frame_times <= end + release_seconds)
                temporal[after] = np.maximum(
                    temporal[after],
                    (1.0 - (frame_times[after] - end) / release_seconds).astype(
                        np.float32
                    ),
                )
        mask = np.maximum(mask, spectral[:, np.newaxis] * temporal[np.newaxis, :])
    if transient_seconds > 0.0 and transient_strength > 0.0:
        for note in notes:
            delta = frame_times - float(note.source_start_seconds)
            active = (delta >= 0.0) & (delta <= transient_seconds)
            if not np.any(active):
                continue
            envelope = transient_strength * (
                1.0 - delta[active] / transient_seconds
            )
            mask[:, active] = np.maximum(
                mask[:, active], envelope[np.newaxis, :].astype(np.float32)
            )
    return np.clip(mask, 0.0, 1.0)


def _read_guide_clips(path: Path) -> list[Any]:
    from .clip import read_midi_clips

    clips = list(read_midi_clips(path))
    if not clips:
        raise ValueError("MIDI contains no note-bearing tracks")
    return clips


def _select_guide_clip(clips: list[Any], track_index: int | None) -> tuple[int, Any]:
    if track_index is None:
        if len(clips) != 1:
            choices = ", ".join(
                f"{index}: {clip.title}" for index, clip in enumerate(clips)
            )
            raise ValueError(
                f"MIDI contains {len(clips)} note-bearing tracks; choose --track-index ({choices})"
            )
        return 0, clips[0]
    if not 0 <= track_index < len(clips):
        raise ValueError(f"track_index must be from 0 to {len(clips) - 1}")
    return track_index, clips[track_index]


def _validate_paths(audio: Path, midi: Path, destination: Path) -> None:
    if not audio.is_file():
        raise ValueError(f"Source audio does not exist: {audio}")
    if not midi.is_file():
        raise ValueError(f"Guide MIDI does not exist: {midi}")
    if destination.exists():
        raise FileExistsError(f"Output directory already exists: {destination}")


def _validate_parameters(
    *,
    start_seconds: float,
    end_seconds: float | None,
    harmonics: int,
    bandwidth_cents: float,
    attack_seconds: float,
    release_seconds: float,
    transient_seconds: float,
    transient_strength: float,
    n_fft: int,
    hop_length: int,
) -> None:
    values = {
        "start_seconds": start_seconds,
        "bandwidth_cents": bandwidth_cents,
        "attack_seconds": attack_seconds,
        "release_seconds": release_seconds,
        "transient_seconds": transient_seconds,
        "transient_strength": transient_strength,
    }
    if end_seconds is not None:
        values["end_seconds"] = end_seconds
    if any(not math.isfinite(float(value)) for value in values.values()):
        raise ValueError("All numeric parameters must be finite")
    if start_seconds < 0:
        raise ValueError("start_seconds must be zero or greater")
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("end_seconds must be after start_seconds")
    if not 1 <= int(harmonics) <= 32 or int(harmonics) != harmonics:
        raise ValueError("harmonics must be an integer from 1 to 32")
    if not 10.0 <= bandwidth_cents <= 200.0:
        raise ValueError("bandwidth_cents must be from 10 to 200")
    if not 0.0 <= attack_seconds <= 1.0:
        raise ValueError("attack_seconds must be from 0 to 1")
    if not 0.0 <= release_seconds <= 2.0:
        raise ValueError("release_seconds must be from 0 to 2")
    if not 0.0 <= transient_seconds <= 0.25:
        raise ValueError("transient_seconds must be from 0 to 0.25")
    if not 0.0 <= transient_strength <= 1.0:
        raise ValueError("transient_strength must be from 0 to 1")
    if n_fft < 512 or n_fft > 8192 or n_fft & (n_fft - 1):
        raise ValueError("n_fft must be a power of two from 512 to 8192")
    if not 1 <= hop_length <= n_fft:
        raise ValueError("hop_length must be from 1 to n_fft")


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _rms(values: Any) -> float:
    import numpy as np

    return math.sqrt(float(np.mean(np.asarray(values, dtype=np.float64) ** 2)))


def _relative_db(value: float, reference: float) -> float | None:
    if value <= 0.0 or reference <= 0.0:
        return None
    return round(20.0 * math.log10(value / reference), 6)


__all__ = ["MAXIMUM_EXCERPT_SECONDS", "MIDI_MASK_SCHEMA", "create_midi_mask"]
