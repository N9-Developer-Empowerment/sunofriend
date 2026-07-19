"""Fixed-MIDI harmonic-plus-noise timbre resynthesis experiments.

The workflow deliberately separates note choice from sound choice.  It fits one
interpretable harmonic profile and amplitude envelope to an aligned monophonic
source excerpt, renders the unchanged MIDI through that profile, and compares
it with complete SoundFont instruments.  It is a deterministic DSP baseline
for later DDSP or neural timbre work, not a learned model or an instrument
identity claim.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any, Sequence

from .clip import ClipNote, MidiClip, read_midi_clips
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent


TIMBRE_RESYNTHESIS_SCHEMA = "sunofriend.timbre-resynthesis.v1"
TIMBRE_RESYNTHESIS_REVIEW_SCHEMA = "sunofriend.timbre-resynthesis-review.v1"
MAXIMUM_EXCERPT_SECONDS = 60.0
AUDIBLE_NOTE_RMS_DBFS = -60.0


def create_timbre_resynthesis(
    source_audio_path: str | Path,
    midi_path: str | Path,
    *,
    out_dir: str | Path,
    gm_program: int = 39,
    source_soundfont_path: str | Path | None = None,
    source_soundfont_program: int = 0,
    harmonics: int = 16,
    attack_seconds: float = 0.008,
    release_seconds: float = 0.045,
) -> dict[str, Any]:
    """Build one level-matched, fixed-note timbre listening experiment."""

    import numpy as np
    import soundfile

    source_audio = _required_file(source_audio_path, "Source audio")
    source_midi = _required_file(midi_path, "Performance MIDI")
    source_soundfont = (
        _required_file(source_soundfont_path, "Source SoundFont")
        if source_soundfont_path is not None
        else None
    )
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise FileExistsError(f"Output directory already exists: {destination}")
    _validate_parameters(
        gm_program=gm_program,
        source_soundfont_program=source_soundfont_program,
        harmonics=harmonics,
        attack_seconds=attack_seconds,
        release_seconds=release_seconds,
    )

    clips = read_midi_clips(source_midi)
    if len(clips) != 1:
        raise ValueError("Timbre resynthesis requires exactly one note-bearing track")
    clip = clips[0]
    if len(clip.tempo_map.tempo_points) != 1:
        raise ValueError("Timbre resynthesis v1 requires one constant MIDI tempo")
    notes = tuple(clip.notes)
    if not notes:
        raise ValueError("Performance MIDI contains no notes")
    if _maximum_simultaneous_notes(notes) > 1:
        raise ValueError("Timbre resynthesis v1 requires a monophonic MIDI performance")

    source, sample_rate = soundfile.read(
        source_audio, dtype="float32", always_2d=True
    )
    if not len(source) or not np.all(np.isfinite(source)):
        raise ValueError("Source audio contains no finite samples")
    duration_seconds = len(source) / sample_rate
    if duration_seconds > MAXIMUM_EXCERPT_SECONDS:
        raise ValueError(
            "Timbre resynthesis is a focused listening experiment; choose an "
            f"excerpt of at most {MAXIMUM_EXCERPT_SECONDS:g} seconds"
        )
    if max(note.source_end_seconds for note in notes) > duration_seconds + 1 / sample_rate:
        raise ValueError("Performance MIDI extends beyond the source audio")

    source_hash_before = _sha256(source_audio)
    midi_hash_before = _sha256(source_midi)
    mono = np.mean(source, axis=1, dtype=np.float64)
    profile = _fit_timbre_profile(mono, int(sample_rate), notes, harmonics)
    seed = int(
        hashlib.sha256(
            f"{source_hash_before}:{midi_hash_before}".encode("ascii")
        ).hexdigest()[:16],
        16,
    )
    resynth = _render_harmonic_noise(
        notes,
        frame_count=len(source),
        sample_rate=int(sample_rate),
        channels=source.shape[1],
        profile=profile,
        attack_seconds=attack_seconds,
        release_seconds=release_seconds,
        seed=seed,
    )
    active_mask = _active_frame_mask(notes, len(source), int(sample_rate))
    source_active_rms = _rms(source[active_mask])
    if source_active_rms <= 1e-7:
        raise ValueError("Source audio is silent over the aligned MIDI notes")
    resynth, resynth_level = _level_match(
        resynth, active_mask, source_active_rms
    )

    work = destination.parent / f".{destination.name}.building-{uuid.uuid4().hex}"
    work.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir()
    try:
        shutil.copyfile(source_audio, work / "source-reference.wav")
        shutil.copyfile(source_midi, work / "performance.mid")
        soundfile.write(
            work / "harmonic-noise-resynthesis.wav",
            resynth,
            int(sample_rate),
            subtype="PCM_24",
        )

        gm_midi = work / "gm-complete-patch.mid"
        _write_program_variant(clip, gm_midi, int(gm_program), "GM complete patch")
        _assert_same_notes(source_midi, gm_midi)
        from .render import render_midi_to_wav

        gm_raw = work / "gm-complete-patch-raw.wav"
        render_midi_to_wav(gm_midi, gm_raw, sample_rate=int(sample_rate))
        gm_audio = _load_rendered_candidate(
            gm_raw, len(source), int(sample_rate), source.shape[1]
        )
        gm_audio, gm_level = _level_match(gm_audio, active_mask, source_active_rms)
        soundfile.write(
            work / "gm-complete-patch.wav",
            gm_audio,
            int(sample_rate),
            subtype="PCM_24",
        )

        source_sampler = None
        if source_soundfont is not None:
            sampler_midi = work / "source-sampler.mid"
            _write_program_variant(
                clip,
                sampler_midi,
                int(source_soundfont_program),
                "Source-derived sampler",
            )
            _assert_same_notes(source_midi, sampler_midi)
            sampler_raw = work / "source-sampler-raw.wav"
            render_midi_to_wav(
                sampler_midi,
                sampler_raw,
                sample_rate=int(sample_rate),
                soundfont_path=source_soundfont,
            )
            sampler_audio = _load_rendered_candidate(
                sampler_raw, len(source), int(sample_rate), source.shape[1]
            )
            sampler_audio, sampler_level = _level_match(
                sampler_audio, active_mask, source_active_rms
            )
            soundfile.write(
                work / "source-sampler.wav",
                sampler_audio,
                int(sample_rate),
                subtype="PCM_24",
            )
            source_sampler = {
                "soundfont": _file_record(source_soundfont),
                "program": int(source_soundfont_program),
                "level_match": sampler_level,
                "audibility": _audibility_report(
                    sampler_audio, notes, int(sample_rate)
                ),
            }

        profile_document = {
            "schema": "sunofriend.harmonic-noise-profile.v1",
            "status": "complete",
            "sample_rate": int(sample_rate),
            "harmonic_amplitudes": profile["harmonic_amplitudes"],
            "harmonic_count": int(harmonics),
            "noise_mix": profile["noise_mix"],
            "sustain_ratio": profile["sustain_ratio"],
            "fitted_note_count": profile["fitted_note_count"],
            "rejected_short_note_count": profile["rejected_short_note_count"],
            "harmonic_brightness": profile["harmonic_brightness"],
            "method": (
                "Duration/RMS-weighted spectral harmonic distribution plus "
                "a deterministic attack-noise component; no neural model."
            ),
        }
        _write_json(work / "timbre_profile.json", profile_document)

        artifacts = {}
        artifact_names = [
            "source-reference.wav",
            "performance.mid",
            "harmonic-noise-resynthesis.wav",
            "gm-complete-patch.mid",
            "gm-complete-patch-raw.wav",
            "gm-complete-patch.wav",
            "timbre_profile.json",
        ]
        if source_sampler is not None:
            artifact_names.extend(
                [
                    "source-sampler.mid",
                    "source-sampler-raw.wav",
                    "source-sampler.wav",
                ]
            )
        for name in artifact_names:
            artifacts[name] = _relative_file_record(work / name, work)

        report: dict[str, Any] = {
            "schema": TIMBRE_RESYNTHESIS_SCHEMA,
            "operation": "timbre-resynthesis",
            "status": "review-required",
            "purpose": (
                "Fixed-MIDI 44.1-kHz-capable harmonic-plus-noise baseline for "
                "later local DDSP/neural timbre comparison."
            ),
            "automatic_promotion": False,
            "neural_model_used": False,
            "physical_instrument_identified": False,
            "source": {
                **_file_record(source_audio),
                "sample_rate": int(sample_rate),
                "channels": int(source.shape[1]),
                "frames": int(len(source)),
                "duration_seconds": round(duration_seconds, 9),
            },
            "midi": {
                **_file_record(source_midi),
                "title": clip.title,
                "bpm": clip.bpm,
                "note_count": len(notes),
                "unique_pitches": sorted({int(note.pitch) for note in notes}),
                "pitch_range": [
                    min(int(note.pitch) for note in notes),
                    max(int(note.pitch) for note in notes),
                ],
                "maximum_simultaneous_notes": 1,
            },
            "profile": profile_document,
            "candidates": {
                "gm_complete_patch": {
                    "program": int(gm_program),
                    "label": "General MIDI Synth Bass 2 complete patch"
                    if int(gm_program) == 39
                    else f"General MIDI program {int(gm_program)} complete patch",
                    "level_match": gm_level,
                    "audibility": _audibility_report(
                        gm_audio, notes, int(sample_rate)
                    ),
                },
                "source_sampler": source_sampler,
                "harmonic_noise_resynthesis": {
                    "label": "Source-fitted harmonic-plus-noise resynthesis",
                    "level_match": resynth_level,
                    "audibility": _audibility_report(
                        resynth, notes, int(sample_rate)
                    ),
                },
            },
            "effects": {
                "source_audio_mutated": False,
                "source_midi_mutated": False,
                "midi_notes_changed": 0,
                "midi_pitches_changed": 0,
                "midi_onsets_changed": 0,
                "midi_durations_changed": 0,
                "midi_velocities_changed": 0,
                "automatic_instrument_selection": False,
                "generated_audio_promoted": False,
            },
            "audibility_policy": {
                "threshold_rms_dbfs": AUDIBLE_NOTE_RMS_DBFS,
                "purpose": "Functional silence check, not a musical-quality score.",
            },
            "artifacts": artifacts,
            "research_context": {
                "ddsp_code_license": "Apache-2.0",
                "ddsp_project": "https://github.com/magenta/ddsp",
                "midi_ddsp_project": "https://github.com/magenta/midi-ddsp",
                "midi_ddsp_direct_use": False,
                "reason": (
                    "The official MIDI-DDSP repository is archived and states "
                    "that its TensorFlow package cannot be installed on M1 Mac."
                ),
            },
            "warnings": [
                "The fitted profile is deterministic DSP, not a trained DDSP model.",
                "Level matching makes listening fairer but does not prove timbre similarity.",
                "The resynthesized WAV is not yet a GarageBand-playable instrument.",
                "Choose a final complete GarageBand patch by ear in the full mix.",
            ],
        }
        review_seed = _review_seed(report, source_sampler is not None)
        _write_json(work / "timbre_resynthesis_review.json", review_seed)
        (work / "timbre_resynthesis_review.html").write_text(
            _review_html(review_seed), encoding="utf-8"
        )
        report["artifacts"]["timbre_resynthesis_review.json"] = (
            _relative_file_record(work / "timbre_resynthesis_review.json", work)
        )
        report["artifacts"]["timbre_resynthesis_review.html"] = (
            _relative_file_record(work / "timbre_resynthesis_review.html", work)
        )
        _write_json(work / "timbre_resynthesis.json", report)

        if _sha256(source_audio) != source_hash_before:
            raise RuntimeError("Source audio changed during timbre resynthesis")
        if _sha256(source_midi) != midi_hash_before:
            raise RuntimeError("Source MIDI changed during timbre resynthesis")
        work.rename(destination)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise

    final = json.loads(
        (destination / "timbre_resynthesis.json").read_text(encoding="utf-8")
    )
    final["report"] = str(destination / "timbre_resynthesis.json")
    final["review_html"] = str(destination / "timbre_resynthesis_review.html")
    return final


def _fit_timbre_profile(
    source: Any,
    sample_rate: int,
    notes: Sequence[ClipNote],
    harmonic_count: int,
) -> dict[str, Any]:
    import numpy as np

    rows = []
    weights = []
    off_harmonic_ratios = []
    sustain_ratios = []
    rejected = 0
    for note in notes:
        duration = float(note.source_end_seconds - note.source_start_seconds)
        f0 = _midi_frequency(note.pitch)
        minimum_duration = max(0.12, 5.0 / f0)
        if duration < minimum_duration:
            rejected += 1
            continue
        trim = min(0.04, duration * 0.18)
        start = int(round((note.source_start_seconds + trim) * sample_rate))
        end = int(round((note.source_end_seconds - trim * 0.5) * sample_rate))
        segment = np.asarray(source[start:end], dtype=np.float64)
        if len(segment) < 512:
            rejected += 1
            continue
        if len(segment) > 16384:
            offset = (len(segment) - 16384) // 2
            segment = segment[offset : offset + 16384]
        segment = segment - float(np.mean(segment))
        segment_rms = _rms(segment)
        if segment_rms <= 1e-7:
            rejected += 1
            continue
        n_fft = min(32768, max(8192, _next_power_of_two(len(segment))))
        spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment)), n=n_fft))
        bin_hz = sample_rate / n_fft
        amplitudes = []
        harmonic_mask = np.zeros(len(spectrum), dtype=bool)
        for harmonic in range(1, harmonic_count + 1):
            frequency = harmonic * f0
            if frequency >= sample_rate / 2:
                amplitudes.append(0.0)
                continue
            center = int(round(frequency / bin_hz))
            radius = max(2, int(round(frequency * 0.04 / bin_hz)))
            low = max(0, center - radius)
            high = min(len(spectrum), center + radius + 1)
            amplitudes.append(float(np.max(spectrum[low:high])))
            harmonic_mask[low:high] = True
        amplitude_sum = sum(amplitudes)
        if amplitude_sum <= 0:
            rejected += 1
            continue
        rows.append(np.asarray(amplitudes, dtype=np.float64) / amplitude_sum)
        weights.append(segment_rms * math.sqrt(duration))
        power = np.square(spectrum)
        total_power = float(np.sum(power))
        harmonic_power = float(np.sum(power[harmonic_mask]))
        if total_power > 0:
            off_harmonic_ratios.append(
                max(0.0, min(1.0, 1.0 - harmonic_power / total_power))
            )
        early = source[
            int((note.source_start_seconds + duration * 0.15) * sample_rate) :
            int((note.source_start_seconds + duration * 0.35) * sample_rate)
        ]
        late = source[
            int((note.source_start_seconds + duration * 0.65) * sample_rate) :
            int((note.source_start_seconds + duration * 0.85) * sample_rate)
        ]
        early_rms = _rms(early)
        if early_rms > 1e-7:
            sustain_ratios.append(_rms(late) / early_rms)

    if rows:
        weight_array = np.asarray(weights, dtype=np.float64)
        distribution = np.average(np.stack(rows), axis=0, weights=weight_array)
    else:
        distribution = 1.0 / np.arange(1, harmonic_count + 1, dtype=np.float64)
    distribution = np.maximum(distribution, 0.0)
    distribution /= float(np.sum(distribution))
    off_ratio = float(np.median(off_harmonic_ratios)) if off_harmonic_ratios else 0.25
    noise_mix = max(0.02, min(0.18, 0.02 + 0.16 * off_ratio))
    sustain_ratio = (
        max(0.2, min(1.0, float(np.median(sustain_ratios))))
        if sustain_ratios
        else 0.65
    )
    brightness = float(
        np.sum(distribution * np.arange(1, harmonic_count + 1, dtype=np.float64))
    )
    return {
        "harmonic_amplitudes": [round(float(value), 9) for value in distribution],
        "noise_mix": round(noise_mix, 9),
        "sustain_ratio": round(sustain_ratio, 9),
        "harmonic_brightness": round(brightness, 9),
        "fitted_note_count": len(rows),
        "rejected_short_note_count": rejected,
    }


def _render_harmonic_noise(
    notes: Sequence[ClipNote],
    *,
    frame_count: int,
    sample_rate: int,
    channels: int,
    profile: dict[str, Any],
    attack_seconds: float,
    release_seconds: float,
    seed: int,
):
    import numpy as np

    output = np.zeros(frame_count, dtype=np.float64)
    harmonic_amplitudes = np.asarray(
        profile["harmonic_amplitudes"], dtype=np.float64
    )
    harmonic_rms = math.sqrt(float(np.sum(np.square(harmonic_amplitudes))) / 2.0)
    if harmonic_rms <= 0:
        raise ValueError("Fitted harmonic profile is silent")
    harmonic_amplitudes /= harmonic_rms
    noise_mix = float(profile["noise_mix"])
    sustain_ratio = float(profile["sustain_ratio"])
    rng = np.random.default_rng(seed)
    phases = rng.uniform(0.0, 2.0 * math.pi, len(harmonic_amplitudes))

    for note in notes:
        start = max(0, int(round(note.source_start_seconds * sample_rate)))
        end = min(frame_count, int(round(note.source_end_seconds * sample_rate)))
        release_end = min(frame_count, end + int(round(release_seconds * sample_rate)))
        if end <= start:
            continue
        length = release_end - start
        note_length = end - start
        time = np.arange(length, dtype=np.float64) / sample_rate
        f0 = _midi_frequency(note.pitch)
        harmonic = np.zeros(length, dtype=np.float64)
        for index, amplitude in enumerate(harmonic_amplitudes, start=1):
            if index * f0 >= sample_rate / 2 or amplitude == 0:
                continue
            harmonic += amplitude * np.sin(
                2.0 * math.pi * index * f0 * time + phases[index - 1]
            )

        envelope = np.full(length, sustain_ratio, dtype=np.float64)
        attack_frames = min(
            max(1, int(round(attack_seconds * sample_rate))),
            max(1, note_length // 3),
        )
        envelope[:attack_frames] = np.sin(
            np.linspace(0.0, math.pi / 2.0, attack_frames, endpoint=True)
        ) ** 2
        decay_frames = min(
            max(1, int(round(min(0.12, note_length / sample_rate * 0.4) * sample_rate))),
            max(1, note_length - attack_frames),
        )
        decay_end = min(note_length, attack_frames + decay_frames)
        if decay_end > attack_frames:
            envelope[attack_frames:decay_end] = np.linspace(
                1.0, sustain_ratio, decay_end - attack_frames, endpoint=True
            )
        if release_end > end:
            envelope[note_length:] = np.linspace(
                sustain_ratio, 0.0, release_end - end, endpoint=True
            )

        noise = rng.standard_normal(length)
        noise = np.concatenate(([noise[0]], np.diff(noise)))
        noise /= max(_rms(noise), 1e-9)
        noise_envelope = np.exp(-time / 0.028) * envelope
        velocity = (max(1, int(note.velocity)) / 127.0) ** 1.35
        signal = velocity * (
            (1.0 - noise_mix) * harmonic * envelope
            + noise_mix * noise * noise_envelope
        )
        output[start:release_end] += signal

    if channels == 1:
        return output[:, np.newaxis].astype("float32")
    return np.repeat(output[:, np.newaxis], channels, axis=1).astype("float32")


def _write_program_variant(
    clip: MidiClip, output: Path, program: int, title: str
) -> None:
    notes = [
        NoteEvent(
            start=note.source_start_seconds,
            end=note.source_end_seconds,
            pitch=note.pitch,
            velocity=note.velocity,
        )
        for note in clip.notes
    ]
    write_midi_file(
        output,
        [MidiTrack(title, clip.instrument.channel, program, notes)],
        bpm=clip.bpm,
    )


def _assert_same_notes(source: Path, candidate: Path) -> None:
    source_notes = _note_signatures(read_midi_clips(source))
    candidate_notes = _note_signatures(read_midi_clips(candidate))
    if source_notes != candidate_notes:
        raise RuntimeError("Timbre candidate changed the fixed MIDI notes")


def _note_signatures(clips: Sequence[MidiClip]) -> list[tuple[float, float, int, int]]:
    return sorted(
        (
            round(note.start_beat, 9),
            round(note.duration_beats, 9),
            int(note.pitch),
            int(note.velocity),
        )
        for clip in clips
        for note in clip.notes
    )


def _load_rendered_candidate(
    path: Path, frame_count: int, sample_rate: int, channels: int
):
    import numpy as np
    import soundfile

    audio, rendered_rate = soundfile.read(path, dtype="float32", always_2d=True)
    if int(rendered_rate) != int(sample_rate):
        raise ValueError("Rendered candidate sample rate does not match the source")
    if audio.shape[1] == 1 and channels > 1:
        audio = np.repeat(audio, channels, axis=1)
    elif audio.shape[1] != channels:
        audio = np.repeat(np.mean(audio, axis=1, keepdims=True), channels, axis=1)
    if len(audio) < frame_count:
        audio = np.pad(audio, ((0, frame_count - len(audio)), (0, 0)))
    return np.asarray(audio[:frame_count], dtype="float32")


def _level_match(candidate: Any, active_mask: Any, target_rms: float):
    import numpy as np

    candidate = np.asarray(candidate, dtype=np.float64)
    before_rms = _rms(candidate[active_mask])
    if before_rms <= 1e-9:
        raise ValueError("A timbre candidate rendered silence")
    scale = target_rms / before_rms if target_rms > 0 else 1.0
    peak_before = float(np.max(np.abs(candidate)))
    limited = False
    if peak_before * scale > 0.95:
        scale = 0.95 / peak_before
        limited = True
    matched = (candidate * scale).astype("float32")
    return matched, {
        "source_active_rms": round(target_rms, 9),
        "candidate_active_rms_before": round(before_rms, 9),
        "candidate_active_rms_after": round(_rms(matched[active_mask]), 9),
        "linear_scale": round(float(scale), 9),
        "peak_limited": limited,
        "peak_after": round(float(np.max(np.abs(matched))), 9),
    }


def _active_frame_mask(notes: Sequence[ClipNote], frame_count: int, sample_rate: int):
    import numpy as np

    mask = np.zeros(frame_count, dtype=bool)
    for note in notes:
        start = max(0, int(round(note.source_start_seconds * sample_rate)))
        end = min(frame_count, int(round(note.source_end_seconds * sample_rate)))
        mask[start:end] = True
    return mask


def _audibility_report(audio: Any, notes: Sequence[ClipNote], sample_rate: int):
    import numpy as np

    levels = []
    silent_indices = []
    for index, note in enumerate(notes):
        start = int(round(note.source_start_seconds * sample_rate))
        end = int(round(note.source_end_seconds * sample_rate))
        margin = min(int(0.01 * sample_rate), max(0, (end - start) // 5))
        segment = audio[start + margin : max(start + margin + 1, end - margin)]
        level = _dbfs(_rms(segment))
        levels.append(level)
        if level < AUDIBLE_NOTE_RMS_DBFS:
            silent_indices.append(index)
    return {
        "policy_threshold_rms_dbfs": AUDIBLE_NOTE_RMS_DBFS,
        "note_count": len(notes),
        "audible_note_count": len(notes) - len(silent_indices),
        "silent_note_count": len(silent_indices),
        "silent_note_indices": silent_indices,
        "minimum_note_rms_dbfs": round(min(levels), 6),
        "median_note_rms_dbfs": round(float(np.median(levels)), 6),
        "all_notes_functionally_audible": not silent_indices,
    }


def _review_seed(report: dict[str, Any], has_source_sampler: bool) -> dict[str, Any]:
    choices = [
        _review_choice(
            "gm_complete_patch",
            report["candidates"]["gm_complete_patch"]["label"],
            "gm-complete-patch.wav",
            "A dependable full-range SoundFont control using exactly the fixed MIDI.",
        )
    ]
    if has_source_sampler:
        choices.append(
            _review_choice(
                "source_sampler",
                "Earlier source-derived sample instrument",
                "source-sampler.wav",
                "The previous extracted-sample approach, now playing the same fixed MIDI.",
            )
        )
    choices.append(
        _review_choice(
            "harmonic_noise_resynthesis",
            "Source-fitted harmonic-plus-noise resynthesis",
            "harmonic-noise-resynthesis.wav",
            "One consistent synthesized timbre fitted from the source excerpt; no copied note samples.",
        )
    )
    return {
        "schema": TIMBRE_RESYNTHESIS_REVIEW_SCHEMA,
        "status": "unreviewed",
        "automatic_promotion": False,
        "experiment": {
            "source_sha256": report["source"]["sha256"],
            "midi_sha256": report["midi"]["sha256"],
            "bpm": report["midi"]["bpm"],
            "candidate_sha256": {
                choice["id"]: report["artifacts"][choice["audio"]]["sha256"]
                for choice in choices
            },
        },
        "overall_decision": None,
        "overall_notes": "",
        "choices": choices,
    }


def _review_choice(identifier: str, title: str, audio: str, purpose: str):
    return {
        "id": identifier,
        "title": title,
        "audio": audio,
        "purpose": purpose,
        "tone_match": "",
        "consistency": "",
        "usefulness": "",
        "notes": "",
        "reviewed": False,
    }


def _review_html(seed: dict[str, Any]) -> str:
    cards = []
    for choice in seed["choices"]:
        cards.append(
            f"""
<section class="card" data-choice="{html.escape(choice['id'])}">
  <h2>{html.escape(choice['title'])}</h2>
  <p>{html.escape(choice['purpose'])}</p>
  <audio controls preload="metadata" src="{html.escape(choice['audio'])}"></audio>
  <div class="grid">
    <label>Tone compared with the source
      <select class="tone"><option value="">Choose…</option><option value="close">Close</option><option value="ballpark">In the ballpark</option><option value="far">Far away</option></select>
    </label>
    <label>Note-to-note consistency
      <select class="consistency"><option value="">Choose…</option><option value="complete">Every note clear and consistent</option><option value="uneven">Audible but uneven</option><option value="missing">Missing or effectively silent notes</option></select>
    </label>
    <label>Musical usefulness
      <select class="usefulness"><option value="">Choose…</option><option value="main">Usable main instrument</option><option value="texture">Useful texture/layer</option><option value="diagnostic">Diagnostic only</option><option value="reject">Reject</option></select>
    </label>
  </div>
  <label>What did you hear?<textarea class="notes" rows="3" placeholder="Tone, attack, sustain, missing notes, realism, musical feel…"></textarea></label>
  <label class="reviewed"><input type="checkbox" class="reviewed-box"> Reviewed this candidate</label>
</section>"""
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    decisions = [
        '<option value="">Choose…</option>',
        '<option value="prefer_gm">Prefer the complete Synth Bass patch</option>',
    ]
    if any(choice["id"] == "source_sampler" for choice in seed["choices"]):
        decisions.append(
            '<option value="prefer_source_sampler">Prefer the source-derived sampler</option>'
        )
    decisions.extend(
        [
            '<option value="prefer_resynthesis">Prefer harmonic resynthesis</option>',
            '<option value="equivalent">Musically equivalent</option>',
            '<option value="none">None is good enough</option>',
        ]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend fixed-MIDI timbre review</title>
<style>
body{{margin:0;background:#0f151c;color:#edf4fb;font:17px/1.45 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:36px 24px 80px}}h1{{font-size:clamp(2.2rem,6vw,4rem);margin:.1em 0}}.intro,.controls,.card,.reference{{background:#18232e;border:1px solid #385064;border-radius:18px;padding:24px;margin:22px 0}}audio{{width:100%;margin:10px 0 18px}}label{{display:block;font-weight:650}}select,textarea{{box-sizing:border-box;width:100%;margin-top:7px;background:#0f151c;color:#edf4fb;border:1px solid #56748b;border-radius:8px;padding:10px;font:inherit}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}button{{background:#2f6288;color:white;border:1px solid #7ab9e8;border-radius:10px;padding:12px 18px;font:inherit;margin:5px}}.reviewed{{margin-top:15px}}.reviewed input{{width:auto}}.count{{color:#ffd166;font-size:1.2rem}}code{{color:#9bdcff}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Fixed-MIDI timbre review</h1>
<div class="intro"><p><strong>Question:</strong> can a source-fitted, consistent harmonic-plus-noise sound beat dependable complete patches when every candidate plays exactly the same reviewed MIDI?</p><p>This tests sound only. It does not change or improve the notes. Listen for every note being audible, a stable identity across pitches, attack and sustain, and whether the result works musically. The synthesized result is a deterministic DDSP-style baseline, not a neural model and not yet a GarageBand instrument.</p></div>
<section class="reference"><h2>Source reference</h2><p>This is the aligned reference audio used to fit the synthesized profile. Use it as the tone and musical-feel reference, not as a candidate.</p><audio controls preload="metadata" src="source-reference.wav"></audio></section>
<div class="controls"><p class="count" id="count">Reviewed 0 of {len(seed['choices'])} candidates</p><button id="mark">Mark all current choices reviewed</button><button id="export">Export review JSON</button><label>Overall decision<select id="decision">{''.join(decisions)}</select></label><label>Overall notes<textarea id="overall" rows="4"></textarea></label></div>
{''.join(cards)}
<script>
const seed={seed_json};const cards=[...document.querySelectorAll('.card')];
function update(){{const n=cards.filter(c=>c.querySelector('.reviewed-box').checked).length;document.getElementById('count').textContent=`Reviewed ${{n}} of ${{cards.length}} candidates`;}}
cards.forEach(c=>c.querySelector('.reviewed-box').addEventListener('change',update));
document.getElementById('mark').onclick=()=>{{cards.forEach(c=>c.querySelector('.reviewed-box').checked=true);update();}};
document.getElementById('export').onclick=()=>{{
 const choices=cards.map(c=>{{const old=seed.choices.find(x=>x.id===c.dataset.choice);return{{...old,tone_match:c.querySelector('.tone').value,consistency:c.querySelector('.consistency').value,usefulness:c.querySelector('.usefulness').value,notes:c.querySelector('.notes').value.trim(),reviewed:c.querySelector('.reviewed-box').checked}};}});
 const decision=document.getElementById('decision').value;
 if(!decision||choices.some(c=>!c.reviewed||!c.tone_match||!c.consistency||!c.usefulness)){{alert('Review every candidate, complete all three fields, and select an overall decision.');return;}}
 const output={{...seed,status:'reviewed',reviewed_at:new Date().toISOString(),overall_decision:decision,overall_notes:document.getElementById('overall').value.trim(),choices}};
 const blob=new Blob([JSON.stringify(output,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='timbre_resynthesis_review.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}};
</script></main></body></html>"""


def _validate_parameters(
    *,
    gm_program: int,
    source_soundfont_program: int,
    harmonics: int,
    attack_seconds: float,
    release_seconds: float,
) -> None:
    if not 0 <= int(gm_program) <= 127:
        raise ValueError("gm_program must be from 0 to 127")
    if not 0 <= int(source_soundfont_program) <= 127:
        raise ValueError("source_soundfont_program must be from 0 to 127")
    if not 1 <= int(harmonics) <= 64:
        raise ValueError("harmonics must be from 1 to 64")
    if not 0.001 <= float(attack_seconds) <= 0.2:
        raise ValueError("attack_seconds must be from 0.001 to 0.2")
    if not 0.0 <= float(release_seconds) <= 1.0:
        raise ValueError("release_seconds must be from 0 to 1")


def _maximum_simultaneous_notes(notes: Sequence[ClipNote]) -> int:
    events = []
    for note in notes:
        events.append((float(note.source_start_seconds), 1))
        events.append((float(note.source_end_seconds), -1))
    active = maximum = 0
    for _, delta in sorted(events, key=lambda row: (row[0], row[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def _midi_frequency(pitch: int) -> float:
    return 440.0 * 2.0 ** ((int(pitch) - 69) / 12.0)


def _next_power_of_two(value: int) -> int:
    return 1 << max(0, int(value - 1).bit_length())


def _rms(values: Any) -> float:
    import numpy as np

    array = np.asarray(values, dtype=np.float64)
    if not array.size:
        return 0.0
    return float(np.sqrt(np.mean(np.square(array))))


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def _required_file(path: str | Path | None, label: str) -> Path:
    if path is None:
        raise ValueError(f"{label} path is missing")
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ValueError(f"{label} not found: {candidate}")
    return candidate.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _relative_file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


__all__ = [
    "TIMBRE_RESYNTHESIS_REVIEW_SCHEMA",
    "TIMBRE_RESYNTHESIS_SCHEMA",
    "create_timbre_resynthesis",
]
