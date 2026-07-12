"""Tuning-aware vocal melody extraction primitives.

Vocals are not ordinary pitched-instrument stems.  Their fundamental
frequency is continuous, consonants are frequently unvoiced, and vibrato or
portamento must not turn into a chromatic staircase of short MIDI notes.  This
module therefore keeps frame-level pitch evidence separate from the eventual
discrete :class:`~sunofriend.models.NoteEvent` values.

The deterministic frame/candidate APIs are deliberately independent of the
optional audio/ML stack.  ``extract_pitch_frames`` and
``extract_backing_candidates`` import librosa, NumPy, SoundFile, and Basic
Pitch lazily; callers can unit-test or use the decoder with evidence supplied
by another pitch tracker.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Literal, Sequence

from .conversion import NoteProvenance
from .models import NoteEvent


VocalRole = Literal["lead", "backing"]
VOCAL_EVIDENCE_PEAK = 0.005
VOCAL_EVIDENCE_RMS = 5e-4


@dataclass(frozen=True)
class VocalConfig:
    """Stable public policy for contour-to-note conversion."""

    role: VocalRole = "lead"
    tuning_hz: float = 440.0
    tuning_source: str = "default"
    bpm: float | None = None
    fmin_hz: float = 55.0
    fmax_hz: float = 1200.0
    hop_length: int = 256
    strict_voicing: float = 0.82
    clean_voicing: float = 0.55
    uncertain_voicing: float = 0.30
    smooth_frames: int = 5
    switch_margin_cents: float = 18.0
    stable_pitch_ms: float = 70.0
    min_note_ms: float = 65.0
    bridge_gap_ms: float = 45.0
    reattack_onset: float = 0.28
    simple_ornament_ms: float = 95.0
    simple_gap_ms: float = 40.0
    quantize_subdivision: int = 4
    quantize_max_shift_ms: float = 55.0
    max_backing_voices: int = 4

    def __post_init__(self) -> None:
        if self.role not in {"lead", "backing"}:
            raise ValueError("role must be 'lead' or 'backing'")
        if not math.isfinite(self.tuning_hz) or self.tuning_hz <= 0:
            raise ValueError("tuning_hz must be finite and positive")
        if not 0 < self.fmin_hz < self.fmax_hz:
            raise ValueError("fmin_hz must be positive and below fmax_hz")
        if self.hop_length <= 0:
            raise ValueError("hop_length must be positive")
        for name in ("strict_voicing", "clean_voicing", "uncertain_voicing"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if not self.strict_voicing >= self.clean_voicing >= self.uncertain_voicing:
            raise ValueError("voicing thresholds must be strict >= clean >= uncertain")
        if self.smooth_frames <= 0 or self.smooth_frames % 2 == 0:
            raise ValueError("smooth_frames must be a positive odd number")
        for name in (
            "switch_margin_cents",
            "stable_pitch_ms",
            "min_note_ms",
            "bridge_gap_ms",
            "simple_ornament_ms",
            "simple_gap_ms",
            "quantize_max_shift_ms",
        ):
            if not math.isfinite(float(getattr(self, name))) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.quantize_subdivision <= 0:
            raise ValueError("quantize_subdivision must be positive")
        if self.max_backing_voices <= 0:
            raise ValueError("max_backing_voices must be positive")


@dataclass(frozen=True)
class PitchFrame:
    """One short-time vocal observation.

    ``f0_hz`` is ``None`` for an unvoiced frame.  ``onset_strength`` is a
    normalized, timbre-independent hint used to retain repeated syllables at
    the same pitch; it is not itself evidence of a note pitch.
    """

    time: float
    f0_hz: float | None
    voiced_probability: float
    rms: float
    onset_strength: float = 0.0
    source: str = "pyin"

    def __post_init__(self) -> None:
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("frame time must be finite and non-negative")
        if self.f0_hz is not None and (
            not math.isfinite(self.f0_hz) or self.f0_hz <= 0
        ):
            raise ValueError("f0_hz must be positive when present")
        if not 0.0 <= self.voiced_probability <= 1.0:
            raise ValueError("voiced_probability must be between zero and one")
        if not math.isfinite(self.rms) or self.rms < 0:
            raise ValueError("rms must be finite and non-negative")
        if not math.isfinite(self.onset_strength) or self.onset_strength < 0:
            raise ValueError("onset_strength must be finite and non-negative")

    def fractional_midi(self, tuning_hz: float) -> float | None:
        if self.f0_hz is None:
            return None
        return hz_to_fractional_midi(self.f0_hz, tuning_hz)


@dataclass(frozen=True)
class VocalCandidate:
    """Polyphonic note hypothesis used by the backing-vocal voice selector."""

    note: NoteEvent
    confidence: float
    spectral_support: float = 0.0
    sources: tuple[str, ...] = ("basic-pitch",)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("candidate confidence must be between zero and one")
        if not math.isfinite(self.spectral_support) or self.spectral_support < 0:
            raise ValueError("spectral_support must be finite and non-negative")
        object.__setattr__(self, "sources", tuple(str(value) for value in self.sources))


@dataclass(frozen=True)
class VocalNoteEvidence:
    """Auditable frame evidence summarized for one emitted MIDI note."""

    note: NoteEvent
    confidence: float
    median_f0_hz: float | None
    median_midi_float: float | None
    pitch_mad_cents: float | None
    median_voiced_probability: float
    voiced_fraction: float
    onset_strength: float
    boundary_reasons: tuple[str, ...] = ()
    sources: tuple[str, ...] = ("vocal-contour",)

    def details(self, config: VocalConfig) -> dict[str, Any]:
        return {
            "tuning_hz": round(config.tuning_hz, 6),
            "tuning_source": config.tuning_source,
            "median_f0_hz": (
                round(self.median_f0_hz, 6) if self.median_f0_hz is not None else None
            ),
            "median_midi_float": (
                round(self.median_midi_float, 6)
                if self.median_midi_float is not None
                else None
            ),
            "pitch_mad_cents": (
                round(self.pitch_mad_cents, 3)
                if self.pitch_mad_cents is not None
                else None
            ),
            "median_voiced_probability": round(
                self.median_voiced_probability, 6
            ),
            "voiced_fraction": round(self.voiced_fraction, 6),
            "onset_strength": round(self.onset_strength, 6),
            "boundary_reasons": list(self.boundary_reasons),
        }


@dataclass(frozen=True)
class VocalDiagnostics:
    role: VocalRole
    tuning_hz: float
    tuning_source: str
    garageband_fine_tune_cents: float
    duration_seconds: float
    frame_count: int
    voiced_frame_count: int
    detected_low_midi: int | None
    detected_high_midi: int | None
    estimated_voice_count: int
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["warnings"] = list(self.warnings)
        return value


@dataclass
class VocalTranscription:
    """One recommended result plus explicitly auditionable alternatives."""

    primary_variant: str
    variants: dict[str, list[NoteEvent]]
    provenance: dict[str, list[NoteProvenance]]
    contour: list[PitchFrame]
    diagnostics: VocalDiagnostics
    descriptions: dict[str, str] = field(default_factory=dict)

    @property
    def notes(self) -> list[NoteEvent]:
        return self.variants.get(self.primary_variant, [])


def hz_to_fractional_midi(frequency_hz: float, tuning_hz: float = 440.0) -> float:
    """Map frequency to MIDI space using an explicit concert-A reference."""

    if not math.isfinite(frequency_hz) or frequency_hz <= 0:
        raise ValueError("frequency_hz must be finite and positive")
    if not math.isfinite(tuning_hz) or tuning_hz <= 0:
        raise ValueError("tuning_hz must be finite and positive")
    return 69.0 + 12.0 * math.log2(frequency_hz / tuning_hz)


def fractional_midi_to_hz(midi: float, tuning_hz: float = 440.0) -> float:
    if not math.isfinite(midi):
        raise ValueError("midi must be finite")
    if not math.isfinite(tuning_hz) or tuning_hz <= 0:
        raise ValueError("tuning_hz must be finite and positive")
    return tuning_hz * (2.0 ** ((midi - 69.0) / 12.0))


def transcribe_vocal_frames(
    frames: Sequence[PitchFrame],
    *,
    config: VocalConfig,
    grid: Any | None = None,
) -> VocalTranscription:
    """Decode precomputed monophonic F0 frames into lead-vocal variants."""

    ordered = _validate_frames(frames)
    strict_notes, strict_evidence = _decode_frame_variant(
        ordered,
        config,
        voiced_threshold=config.strict_voicing,
        bridge_gap_seconds=0.0,
    )
    clean_notes, clean_evidence = _decode_frame_variant(
        ordered,
        config,
        voiced_threshold=config.clean_voicing,
        bridge_gap_seconds=config.bridge_gap_ms / 1000.0,
    )
    simple_notes = simplify_vocal_notes(clean_notes, config=config)
    simple_evidence = _evidence_for_notes(simple_notes, ordered, config)
    quantized_notes = gentle_quantize_notes(
        clean_notes,
        config=config,
        grid=grid,
    )
    quantized_evidence = _evidence_for_notes(quantized_notes, ordered, config)

    lenient_notes, lenient_evidence = _decode_frame_variant(
        ordered,
        config,
        voiced_threshold=config.uncertain_voicing,
        bridge_gap_seconds=0.0,
    )
    uncertain_notes: list[NoteEvent] = []
    uncertain_evidence: list[VocalNoteEvidence] = []
    for note, evidence in zip(lenient_notes, lenient_evidence):
        if _note_is_explained(note, clean_notes):
            continue
        uncertain_notes.append(note)
        uncertain_evidence.append(evidence)

    variants = {
        "observed_strict": strict_notes,
        "contour_clean": clean_notes,
        "instrument_simple": simple_notes,
        "gentle_quantized": quantized_notes,
    }
    evidence_by_variant = {
        "observed_strict": strict_evidence,
        "contour_clean": clean_evidence,
        "instrument_simple": simple_evidence,
        "gentle_quantized": quantized_evidence,
    }
    if uncertain_notes:
        variants["uncertain"] = uncertain_notes
        evidence_by_variant["uncertain"] = uncertain_evidence

    provenance = {
        name: _provenance_from_evidence(
            values,
            config,
            variant=name,
            origin="observed" if name == "observed_strict" else "repaired",
            tier="uncertain" if name == "uncertain" else "main",
        )
        for name, values in evidence_by_variant.items()
    }
    diagnostics = _diagnostics_from_frames(
        ordered,
        config,
        estimated_voice_count=1 if clean_notes else 0,
    )
    return VocalTranscription(
        primary_variant="contour_clean",
        variants=variants,
        provenance=provenance,
        contour=list(ordered),
        diagnostics=diagnostics,
        descriptions={
            "observed_strict": "High-confidence voiced evidence with natural source timing.",
            "contour_clean": "Recommended stable intended-note contour; vibrato and slides are not chromatic staircases.",
            "instrument_simple": "Short ornaments are reduced for a simpler instrumental melody.",
            "gentle_quantized": "Only boundaries close to the beat subdivision are moved.",
            "uncertain": "Low-confidence voiced material quarantined for audition.",
        },
    )


def select_backing_vocal_variants(
    candidates: Sequence[VocalCandidate],
    *,
    config: VocalConfig,
    reference_notes: Sequence[NoteEvent] | None = None,
    contour: Sequence[PitchFrame] = (),
) -> VocalTranscription:
    """Separate polyphonic backing-vocal hypotheses into useful choices.

    ``dominant_line`` is the strongest continuous monophonic voice and is the
    recommended backing melody.  ``top_line`` is useful when the recognizable
    harmony sits above it.  ``harmony_stack`` retains every supported voice.
    No chord-derived notes are invented.
    """

    supported, uncertain = _prepare_backing_candidates(candidates, config)
    voices = _assign_backing_voices(supported, config.max_backing_voices)
    references = list(reference_notes or ())
    if voices:
        dominant_index = max(
            range(len(voices)),
            key=lambda index: (
                _backing_voice_score(voices[index], references),
                -index,
            ),
        )
        ordered_by_register = sorted(
            range(len(voices)), key=lambda index: _median_voice_pitch(voices[index])
        )
        top_index = ordered_by_register[-1]
        dominant_candidates = _make_backing_voice_monophonic(
            voices[dominant_index]
        )
        top_candidates = _make_backing_voice_monophonic(voices[top_index])
        dominant = [candidate.note for candidate in dominant_candidates]
        top = [candidate.note for candidate in top_candidates]
    else:
        dominant_candidates = []
        top_candidates = []
        dominant = []
        top = []

    harmony = sorted(
        [candidate.note for candidate in supported],
        key=lambda note: (note.start, note.pitch, note.end),
    )
    variants: dict[str, list[NoteEvent]] = {
        "dominant_line": dominant,
        "top_line": top,
        "harmony_stack": harmony,
    }
    if uncertain:
        variants["uncertain"] = [candidate.note for candidate in uncertain]

    by_note = {
        _note_key(candidate.note): candidate
        for candidate in [
            *supported,
            *uncertain,
            *dominant_candidates,
            *top_candidates,
        ]
    }
    provenance: dict[str, list[NoteProvenance]] = {}
    for variant, notes in variants.items():
        records: list[NoteProvenance] = []
        for note in notes:
            candidate = by_note.get(_note_key(note))
            confidence = candidate.confidence if candidate else 0.4
            support = candidate.spectral_support if candidate else 0.0
            sources = candidate.sources if candidate else ("backing-voice-selector",)
            records.append(
                NoteProvenance.from_note(
                    note,
                    origin="observed" if variant == "harmony_stack" else "repaired",
                    confidence=max(0.0, min(1.0, confidence)),
                    tier="uncertain" if variant == "uncertain" else "main",
                    confidence_basis="measured",
                    family="backing_vocals",
                    sources=(*sources, "backing-voice-selector", variant),
                    details={
                        "tuning_hz": round(config.tuning_hz, 6),
                        "tuning_source": config.tuning_source,
                        "spectral_support": round(support, 6),
                        "reference_melody_used_for_selection": bool(references),
                    },
                )
            )
        provenance[variant] = records

    diagnostics = _diagnostics_from_frames(
        list(contour),
        replace(config, role="backing"),
        estimated_voice_count=len(voices),
        extra_warnings=("No supported backing-vocal pitch evidence was found.",)
        if not harmony
        else (),
    )
    return VocalTranscription(
        primary_variant="dominant_line",
        variants=variants,
        provenance=provenance,
        contour=list(contour),
        diagnostics=diagnostics,
        descriptions={
            "dominant_line": "Recommended strongest continuous monophonic backing voice.",
            "top_line": "Highest continuous backing voice.",
            "harmony_stack": "All supported backing voices as a polyphonic track.",
            "uncertain": "Weak or excess hypotheses quarantined for audition.",
        },
    )


def transcribe_vocal_melody(
    path: str | Path,
    *,
    config: VocalConfig,
    grid: Any | None = None,
    reference_notes: Sequence[NoteEvent] | None = None,
) -> VocalTranscription:
    """Audio adapter around the deterministic lead/backing APIs.

    Missing optional dependencies or a tracker failure yields a no-evidence
    result with an explicit warning, rather than fabricated melody notes.
    """

    warnings: list[str] = []
    try:
        peak, rms = vocal_signal_stats(path)
    except Exception as exc:
        peak = rms = None
        warnings.append(
            f"Absolute vocal evidence gate unavailable: {type(exc).__name__}: {exc}"
        )
    if peak is not None and rms is not None and (
        peak <= VOCAL_EVIDENCE_PEAK or rms <= VOCAL_EVIDENCE_RMS
    ):
        warning = (
            "Source is below the absolute vocal evidence floor "
            f"(peak={peak:.6g}, rms={rms:.6g}); no melody was inferred."
        )
        if config.role == "lead":
            result = transcribe_vocal_frames([], config=config, grid=grid)
        else:
            result = select_backing_vocal_variants([], config=config)
        result.diagnostics = replace(
            result.diagnostics,
            warnings=tuple([*result.diagnostics.warnings, *warnings, warning]),
        )
        return result

    try:
        frames = extract_pitch_frames(path, config=config)
    except Exception as exc:  # optional audio stack must fail soft at this API
        frames = []
        warnings.append(f"F0 extraction unavailable: {type(exc).__name__}: {exc}")

    if config.role == "lead":
        result = transcribe_vocal_frames(frames, config=config, grid=grid)
    else:
        try:
            candidates = extract_backing_candidates(path, config=config)
        except Exception as exc:  # Basic Pitch is optional
            candidates = []
            warnings.append(
                f"Polyphonic backing extraction unavailable: {type(exc).__name__}: {exc}"
            )
        if not candidates and frames:
            fallback = transcribe_vocal_frames(
                frames, config=replace(config, role="lead"), grid=grid
            )
            fallback_records = fallback.provenance.get("contour_clean", [])
            candidates = [
                VocalCandidate(
                    note,
                    confidence=record.confidence if index < len(fallback_records) else 0.55,
                    sources=("pyin", "monophonic-fallback"),
                )
                for index, (note, record) in enumerate(
                    zip(fallback.notes, fallback_records)
                )
            ]
            if candidates:
                warnings.append(
                    "Backing stem fell back to a monophonic dominant contour; harmony voices were not recovered."
                )
        result = select_backing_vocal_variants(
            candidates,
            config=config,
            reference_notes=reference_notes,
            contour=frames,
        )

    if warnings:
        result.diagnostics = replace(
            result.diagnostics,
            warnings=tuple([*result.diagnostics.warnings, *warnings]),
        )
    return result


def phase_safe_downmix(values: Any, cancellation_ratio: float = 0.80) -> Any:
    """Return arithmetic mono unless it materially cancels stereo evidence."""

    if not 0.0 < cancellation_ratio <= 1.0:
        raise ValueError("cancellation_ratio must be between zero and one")
    import numpy as np

    channels = np.asarray(values, dtype=np.float64)
    if channels.ndim == 1:
        return channels
    if channels.ndim != 2 or channels.shape[1] == 0:
        raise ValueError("audio must be one-dimensional or frames-by-channels")
    if channels.shape[1] == 1:
        return channels[:, 0]
    mono = np.mean(channels, axis=1)
    mono_rms = math.sqrt(float(np.mean(mono * mono))) if len(mono) else 0.0
    channel_rms = np.sqrt(np.mean(channels * channels, axis=0))
    strongest = int(np.argmax(channel_rms)) if len(channel_rms) else 0
    strongest_rms = float(channel_rms[strongest]) if len(channel_rms) else 0.0
    if strongest_rms > 0.0 and mono_rms < strongest_rms * cancellation_ratio:
        return channels[:, strongest]
    return mono


def load_audio_phase_safe(
    path: str | Path,
    *,
    target_sample_rate: int = 22_050,
) -> tuple[Any, int]:
    """Load a WAV using the vocal pipeline's phase-safe mono policy."""

    if target_sample_rate <= 0:
        raise ValueError("target_sample_rate must be positive")
    import soundfile

    values, sample_rate = soundfile.read(
        str(path), dtype="float64", always_2d=True
    )
    mono = phase_safe_downmix(values)
    if int(sample_rate) != target_sample_rate and len(mono):
        import librosa

        mono = librosa.resample(
            mono,
            orig_sr=int(sample_rate),
            target_sr=target_sample_rate,
        )
        sample_rate = target_sample_rate
    return mono, int(sample_rate)


def vocal_signal_stats(path: str | Path) -> tuple[float, float]:
    """Return absolute peak/RMS across all source channels, without downmix.

    Looking at channels before mixing makes the gate immune to stereo phase
    cancellation.  The absolute floor intentionally runs before pYIN or Basic
    Pitch so a nearly empty separator output cannot be normalized into a
    plausible-looking melody.
    """

    import numpy as np
    import soundfile

    peak = 0.0
    square_sum = 0.0
    sample_count = 0
    with soundfile.SoundFile(str(path)) as handle:
        for block in handle.blocks(blocksize=1 << 20, dtype="float32"):
            if not block.size:
                continue
            peak = max(peak, float(np.max(np.abs(block))))
            values = block.astype("float64", copy=False)
            square_sum += float(np.sum(values * values))
            sample_count += int(values.size)
    rms = math.sqrt(square_sum / sample_count) if sample_count else 0.0
    return peak, rms


def extract_pitch_frames(
    path: str | Path,
    *,
    config: VocalConfig,
    sample_rate: int = 22_050,
) -> list[PitchFrame]:
    """Extract a phase-safe pYIN contour plus boundary/dynamics evidence."""

    import librosa
    import numpy as np

    audio, sample_rate = load_audio_phase_safe(
        path, target_sample_rate=sample_rate
    )
    if len(audio) == 0:
        return []
    peak = float(np.max(np.abs(audio)))
    rms_level = math.sqrt(float(np.mean(np.asarray(audio) ** 2)))
    if peak <= VOCAL_EVIDENCE_PEAK or rms_level <= VOCAL_EVIDENCE_RMS:
        return []
    fmax = min(config.fmax_hz, sample_rate * 0.49)
    f0, voiced, voiced_probability = librosa.pyin(
        audio,
        fmin=config.fmin_hz,
        fmax=fmax,
        sr=sample_rate,
        hop_length=config.hop_length,
        fill_na=np.nan,
    )
    rms = librosa.feature.rms(
        y=audio,
        frame_length=2048,
        hop_length=config.hop_length,
    )[0]
    onset = librosa.onset.onset_strength(
        y=audio,
        sr=sample_rate,
        hop_length=config.hop_length,
    )
    onset_peak = float(np.max(onset)) if len(onset) else 0.0
    if onset_peak > 0:
        onset = onset / onset_peak
    times = librosa.times_like(
        f0,
        sr=sample_rate,
        hop_length=config.hop_length,
    )
    count = len(f0)
    result: list[PitchFrame] = []
    for index in range(count):
        frequency = float(f0[index]) if np.isfinite(f0[index]) else None
        probability = (
            float(voiced_probability[index])
            if voiced_probability is not None
            and index < len(voiced_probability)
            and np.isfinite(voiced_probability[index])
            else (1.0 if voiced is not None and bool(voiced[index]) else 0.0)
        )
        result.append(
            PitchFrame(
                time=float(times[index]),
                f0_hz=frequency,
                voiced_probability=max(0.0, min(1.0, probability)),
                rms=float(rms[min(index, len(rms) - 1)]) if len(rms) else 0.0,
                onset_strength=(
                    float(onset[min(index, len(onset) - 1)]) if len(onset) else 0.0
                ),
                source="pyin",
            )
        )
    return result


def extract_backing_candidates(
    path: str | Path,
    *,
    config: VocalConfig,
) -> list[VocalCandidate]:
    """Run Basic Pitch as a lazy, fail-soft polyphonic vocal hypothesis source."""

    peak, rms = vocal_signal_stats(path)
    if peak <= VOCAL_EVIDENCE_PEAK or rms <= VOCAL_EVIDENCE_RMS:
        return []

    from basic_pitch.inference import predict
    from .transcribe_pitched import _model_path

    _, _, events = predict(
        str(path),
        model_or_model_path=_model_path(),
        onset_threshold=0.35,
        frame_threshold=0.22,
        minimum_note_length=max(45.0, config.min_note_ms),
        minimum_frequency=config.fmin_hz,
        maximum_frequency=config.fmax_hz,
        melodia_trick=False,
        multiple_pitch_bends=False,
    )
    candidates: list[VocalCandidate] = []
    for start, end, pitch, amplitude, *_ in events:
        note = NoteEvent(
            start=max(0.0, float(start)),
            end=max(float(start) + 0.03, float(end)),
            pitch=max(0, min(127, int(pitch))),
            velocity=max(1, min(127, int(round(float(amplitude) * 127)))),
        )
        candidates.append(
            VocalCandidate(
                note=note,
                confidence=max(0.0, min(1.0, float(amplitude))),
                sources=("basic-pitch", "polyphonic-vocal-hypothesis"),
            )
        )
    return sorted(candidates, key=lambda value: (value.note.start, value.note.pitch))


def simplify_vocal_notes(
    notes: Sequence[NoteEvent], *, config: VocalConfig
) -> list[NoteEvent]:
    """Reduce short ornaments without changing the longer melodic anchors."""

    values = sorted(notes, key=lambda note: (note.start, note.pitch, note.end))
    threshold = config.simple_ornament_ms / 1000.0
    gap_limit = config.simple_gap_ms / 1000.0
    index = 0
    while index < len(values):
        note = values[index]
        if note.end - note.start >= threshold or len(values) == 1:
            index += 1
            continue
        previous = values[index - 1] if index > 0 else None
        following = values[index + 1] if index + 1 < len(values) else None
        previous_is_close = bool(
            previous is not None
            and 0.0 <= note.start - previous.end <= gap_limit
        )
        following_is_close = bool(
            following is not None
            and 0.0 <= following.start - note.end <= gap_limit
        )
        if (
            previous is not None
            and following is not None
            and previous_is_close
            and following_is_close
            and previous.pitch == following.pitch
        ):
            values[index - 1] = NoteEvent(
                previous.start,
                following.end,
                previous.pitch,
                max(previous.velocity, following.velocity),
            )
            del values[index : index + 2]
            continue
        prefer_previous = bool(
            previous is not None
            and previous_is_close
            and (
                following is None
                or not following_is_close
                or abs(note.pitch - previous.pitch)
                < abs(note.pitch - following.pitch)
            )
        )
        if previous is not None and prefer_previous:
            values[index - 1] = NoteEvent(
                previous.start,
                max(previous.end, note.end),
                previous.pitch,
                max(previous.velocity, note.velocity),
            )
            del values[index]
            continue
        if following is not None and following_is_close:
            values[index + 1] = NoteEvent(
                note.start,
                following.end,
                following.pitch,
                max(note.velocity, following.velocity),
            )
            del values[index]
            continue
        index += 1

    merged: list[NoteEvent] = []
    for note in values:
        if (
            merged
            and merged[-1].pitch == note.pitch
            and 0.0 <= note.start - merged[-1].end <= gap_limit
        ):
            previous = merged.pop()
            merged.append(
                NoteEvent(
                    previous.start,
                    note.end,
                    note.pitch,
                    max(previous.velocity, note.velocity),
                )
            )
        else:
            if merged and merged[-1].end > note.start:
                previous = merged[-1]
                merged[-1] = NoteEvent(
                    previous.start,
                    max(previous.start + 1e-6, note.start),
                    previous.pitch,
                    previous.velocity,
                )
            merged.append(note)
    return merged


def gentle_quantize_notes(
    notes: Sequence[NoteEvent],
    *,
    config: VocalConfig,
    grid: Any | None = None,
) -> list[NoteEvent]:
    """Move only already-near grid boundaries; never force source alignment."""

    maximum = config.quantize_max_shift_ms / 1000.0

    def snapped(value: float) -> float:
        if grid is not None:
            target = float(grid.snap(value, config.quantize_subdivision))
        elif config.bpm is not None and config.bpm > 0:
            step = 60.0 / config.bpm / config.quantize_subdivision
            target = round(value / step) * step
        else:
            return value
        return target if abs(target - value) <= maximum else value

    result: list[NoteEvent] = []
    minimum = config.min_note_ms / 1000.0
    for note in sorted(notes, key=lambda item: (item.start, item.pitch)):
        start = max(0.0, snapped(note.start))
        end = snapped(note.end)
        # Two nearby boundaries can snap onto the same grid line. Preserve the
        # source interval rather than publishing a click-sized MIDI event.
        if end - start + 1e-9 < minimum:
            start, end = note.start, note.end
        end = max(start + minimum, end)
        if result and result[-1].end > start:
            previous = result[-1]
            preferred = (previous.end + start) / 2.0
            lower = previous.start + minimum
            upper = end - minimum
            boundary = max(lower, min(upper, preferred))
            if lower > upper:
                # The original decoder is monophonic. If there is not enough
                # room to share the snapped overlap safely, retain the source
                # boundary rather than manufacturing overlapping notes.
                boundary = max(previous.start + minimum, note.start)
                boundary = min(boundary, end - minimum)
            result[-1] = NoteEvent(
                previous.start,
                boundary,
                previous.pitch,
                previous.velocity,
            )
            start = boundary
        result.append(NoteEvent(start, end, note.pitch, note.velocity))
    return result


def _decode_frame_variant(
    frames: Sequence[PitchFrame],
    config: VocalConfig,
    *,
    voiced_threshold: float,
    bridge_gap_seconds: float,
) -> tuple[list[NoteEvent], list[VocalNoteEvidence]]:
    if not frames:
        return [], []
    hop = _frame_hop(frames)
    midis = _smoothed_midis(frames, config, voiced_threshold)
    states: list[int | None] = []
    current: int | None = None
    pending_pitch: int | None = None
    pending_indices: list[int] = []
    pending_values: list[float] = []
    last_voiced_time: float | None = None
    stable_seconds = config.stable_pitch_ms / 1000.0

    for index, value in enumerate(midis):
        if value is None:
            states.append(None)
            pending_pitch = None
            pending_indices = []
            pending_values = []
            if (
                last_voiced_time is not None
                and frames[index].time - last_voiced_time > max(0.25, bridge_gap_seconds)
            ):
                current = None
            continue
        last_voiced_time = frames[index].time
        target = _nearest_midi(value)
        if current is None:
            current = target
            states.append(current)
            continue
        if target == current:
            states.append(current)
            pending_pitch = None
            pending_indices = []
            pending_values = []
            continue
        improvement = (abs(value - current) - abs(value - target)) * 100.0
        if improvement < config.switch_margin_cents:
            states.append(current)
            pending_pitch = None
            pending_indices = []
            pending_values = []
            continue
        if pending_pitch != target:
            pending_pitch = target
            pending_indices = []
            pending_values = []
        pending_indices.append(index)
        pending_values.append(value)
        states.append(current)
        pending_duration = (
            frames[pending_indices[-1]].time
            - frames[pending_indices[0]].time
            + hop
        )
        stable = _median_absolute_deviation(pending_values) <= 0.22
        if pending_duration + 1e-9 >= stable_seconds and stable:
            current = target
            for pending_index in pending_indices:
                states[pending_index] = current
            pending_pitch = None
            pending_indices = []
            pending_values = []

    if bridge_gap_seconds > 0:
        states = _bridge_unvoiced_runs(
            frames,
            states,
            hop=hop,
            maximum_gap=bridge_gap_seconds,
            reattack_threshold=config.reattack_onset,
        )
    runs = _state_runs(frames, states, config, hop)
    notes, evidence = _notes_from_runs(runs, frames, config, hop)
    return notes, evidence


def _smoothed_midis(
    frames: Sequence[PitchFrame],
    config: VocalConfig,
    threshold: float,
) -> list[float | None]:
    raw = [
        frame.fractional_midi(config.tuning_hz)
        if frame.f0_hz is not None and frame.voiced_probability >= threshold
        else None
        for frame in frames
    ]
    radius = config.smooth_frames // 2
    result: list[float | None] = []
    for index, value in enumerate(raw):
        if value is None:
            result.append(None)
            continue
        window = [
            raw[position]
            for position in range(max(0, index - radius), min(len(raw), index + radius + 1))
            if raw[position] is not None
        ]
        result.append(float(median(window)) if window else value)
    return result


def _bridge_unvoiced_runs(
    frames: Sequence[PitchFrame],
    states: Sequence[int | None],
    *,
    hop: float,
    maximum_gap: float,
    reattack_threshold: float,
) -> list[int | None]:
    result = list(states)
    index = 0
    while index < len(result):
        if result[index] is not None:
            index += 1
            continue
        start = index
        while index < len(result) and result[index] is None:
            index += 1
        end = index
        before = result[start - 1] if start > 0 else None
        after = result[end] if end < len(result) else None
        duration = frames[end - 1].time - frames[start].time + hop
        onset = frames[end].onset_strength if end < len(frames) else 0.0
        if (
            before is not None
            and before == after
            and duration <= maximum_gap + 1e-9
            and onset < reattack_threshold
        ):
            for position in range(start, end):
                result[position] = before
    return result


def _state_runs(
    frames: Sequence[PitchFrame],
    states: Sequence[int | None],
    config: VocalConfig,
    hop: float,
) -> list[tuple[int, int, int, tuple[str, ...]]]:
    base: list[tuple[int, int, int]] = []
    index = 0
    while index < len(states):
        if states[index] is None:
            index += 1
            continue
        start = index
        pitch = int(states[index])
        index += 1
        while index < len(states) and states[index] == pitch:
            index += 1
        base.append((start, index, pitch))

    split: list[tuple[int, int, int]] = []
    minimum = config.min_note_ms / 1000.0
    for start, end, pitch in base:
        boundaries = [start]
        for position in range(start + 2, end - 1):
            frame = frames[position]
            if frame.onset_strength < config.reattack_onset:
                continue
            before = frames[max(start, position - 4) : position]
            local_floor = min((value.rms for value in before), default=frame.rms)
            level = max(frame.rms, 1e-12)
            if local_floor > level * 0.55:
                continue
            if (
                frames[position].time - frames[boundaries[-1]].time >= minimum
                and frames[end - 1].time - frames[position].time + hop >= minimum
            ):
                boundaries.append(position)
        boundaries.append(end)
        split.extend(
            (left, right, pitch)
            for left, right in zip(boundaries, boundaries[1:])
        )

    result: list[tuple[int, int, int, tuple[str, ...]]] = []
    for index, (start, end, pitch) in enumerate(split):
        reasons: list[str] = []
        if start == 0 or states[start - 1] is None:
            reasons.append("voicing_start")
        elif int(states[start - 1]) != pitch:
            reasons.append("pitch_change")
        else:
            reasons.append("reattack")
        if index and split[index - 1][2] == pitch and split[index - 1][1] < start:
            reasons.append("same_pitch_after_gap")
        result.append((start, end, pitch, tuple(reasons)))
    return result


def _notes_from_runs(
    runs: Sequence[tuple[int, int, int, tuple[str, ...]]],
    frames: Sequence[PitchFrame],
    config: VocalConfig,
    hop: float,
) -> tuple[list[NoteEvent], list[VocalNoteEvidence]]:
    voiced_logs = [
        math.log(max(frame.rms, 1e-9))
        for frame in frames
        if frame.f0_hz is not None and frame.voiced_probability >= config.uncertain_voicing
    ]
    low = _percentile(voiced_logs, 10.0) if voiced_logs else 0.0
    high = _percentile(voiced_logs, 90.0) if voiced_logs else 0.0
    notes: list[NoteEvent] = []
    evidence: list[VocalNoteEvidence] = []
    minimum = config.min_note_ms / 1000.0
    for start_index, end_index, pitch, reasons in runs:
        start = frames[start_index].time
        end = frames[end_index - 1].time + hop
        if end - start + 1e-9 < minimum:
            continue
        region = frames[start_index:end_index]
        level_values = [math.log(max(frame.rms, 1e-9)) for frame in region]
        level = float(median(level_values)) if level_values else low
        normalized = 0.58 if high <= low + 1e-9 else (level - low) / (high - low)
        velocity = max(35, min(112, int(round(45 + 67 * max(0.0, min(1.0, normalized))))))
        note = NoteEvent(start, end, max(0, min(127, pitch)), velocity)
        item = _summarize_note_evidence(note, region, config, reasons)
        notes.append(note)
        evidence.append(item)
    return notes, evidence


def _summarize_note_evidence(
    note: NoteEvent,
    frames: Sequence[PitchFrame],
    config: VocalConfig,
    reasons: Sequence[str] = (),
) -> VocalNoteEvidence:
    voiced = [frame for frame in frames if frame.f0_hz is not None]
    frequencies = [float(frame.f0_hz) for frame in voiced if frame.f0_hz is not None]
    midis = [hz_to_fractional_midi(value, config.tuning_hz) for value in frequencies]
    probabilities = [frame.voiced_probability for frame in frames]
    median_probability = float(median(probabilities)) if probabilities else 0.0
    voiced_fraction = len(voiced) / len(frames) if frames else 0.0
    pitch_mad = _median_absolute_deviation(midis) * 100.0 if midis else None
    stability = 0.0 if pitch_mad is None else max(0.0, 1.0 - pitch_mad / 65.0)
    onset = max((frame.onset_strength for frame in frames), default=0.0)
    confidence = (
        0.55 * median_probability
        + 0.22 * stability
        + 0.13 * voiced_fraction
        + 0.10 * min(1.0, onset)
    )
    return VocalNoteEvidence(
        note=note,
        confidence=max(0.0, min(1.0, confidence)),
        median_f0_hz=float(median(frequencies)) if frequencies else None,
        median_midi_float=float(median(midis)) if midis else None,
        pitch_mad_cents=pitch_mad,
        median_voiced_probability=median_probability,
        voiced_fraction=voiced_fraction,
        onset_strength=onset,
        boundary_reasons=tuple(reasons),
        sources=tuple(sorted({frame.source for frame in frames} | {"vocal-contour"})),
    )


def _evidence_for_notes(
    notes: Sequence[NoteEvent],
    frames: Sequence[PitchFrame],
    config: VocalConfig,
) -> list[VocalNoteEvidence]:
    result: list[VocalNoteEvidence] = []
    for note in notes:
        region = [
            frame
            for frame in frames
            if note.start - 1e-9 <= frame.time < note.end + 1e-9
        ]
        result.append(
            _summarize_note_evidence(note, region, config, ("variant_transform",))
        )
    return result


def _provenance_from_evidence(
    evidence: Sequence[VocalNoteEvidence],
    config: VocalConfig,
    *,
    variant: str,
    origin: str,
    tier: str,
) -> list[NoteProvenance]:
    return [
        NoteProvenance.from_note(
            item.note,
            origin=origin,  # type: ignore[arg-type]
            confidence=item.confidence,
            tier=tier,  # type: ignore[arg-type]
            confidence_basis="measured",
            family="vocals" if config.role == "lead" else "backing_vocals",
            sources=(*item.sources, "vocal-decoder", variant),
            details=item.details(config),
        )
        for item in evidence
    ]


def _prepare_backing_candidates(
    candidates: Sequence[VocalCandidate], config: VocalConfig
) -> tuple[list[VocalCandidate], list[VocalCandidate]]:
    valid = [
        value
        for value in candidates
        if value.note.end > value.note.start
        and 0 <= value.note.pitch <= 127
        and value.confidence >= 0.20
    ]
    valid.sort(key=lambda value: (value.note.start, value.note.pitch, -value.confidence))
    dropped: set[int] = set()
    for left_index, left in enumerate(valid):
        if left_index in dropped:
            continue
        for right_index in range(left_index + 1, len(valid)):
            right = valid[right_index]
            if abs(right.note.pitch - left.note.pitch) not in {12, 24}:
                continue
            overlap = min(left.note.end, right.note.end) - max(left.note.start, right.note.start)
            shorter = min(
                left.note.end - left.note.start,
                right.note.end - right.note.start,
            )
            if shorter <= 0 or overlap < 0.70 * shorter:
                continue
            weaker_index, stronger_index = (
                (left_index, right_index)
                if left.confidence < right.confidence
                else (right_index, left_index)
            )
            weaker, stronger = valid[weaker_index], valid[stronger_index]
            if (
                weaker.confidence < 0.55
                and stronger.confidence >= weaker.confidence + 0.20
                and weaker.note.velocity < stronger.note.velocity * 0.78
            ):
                dropped.add(weaker_index)
    supported = [
        value
        for index, value in enumerate(valid)
        if index not in dropped and value.confidence >= 0.35
    ]
    uncertain = [
        value
        for index, value in enumerate(valid)
        if index in dropped or value.confidence < 0.35
    ]
    return supported, uncertain


def _assign_backing_voices(
    candidates: Sequence[VocalCandidate], maximum_voices: int
) -> list[list[VocalCandidate]]:
    groups: list[list[VocalCandidate]] = []
    anchor = 0.0
    for candidate in sorted(candidates, key=lambda value: (value.note.start, value.note.pitch)):
        if not groups or candidate.note.start - anchor > 0.09:
            groups.append([candidate])
            anchor = candidate.note.start
        else:
            groups[-1].append(candidate)

    voices: list[list[VocalCandidate]] = []
    for group in groups:
        used: set[int] = set()
        for candidate in sorted(group, key=lambda value: (value.note.pitch, -value.confidence)):
            choices: list[tuple[float, int]] = []
            for voice_index, voice in enumerate(voices):
                if voice_index in used:
                    continue
                previous = voice[-1].note
                if previous.end > candidate.note.start + 0.04:
                    continue
                gap = max(0.0, candidate.note.start - previous.end)
                if gap > 3.0:
                    continue
                cost = abs(candidate.note.pitch - previous.pitch) + min(6.0, gap * 1.5)
                choices.append((cost, voice_index))
            if choices:
                _, voice_index = min(choices, key=lambda value: (value[0], value[1]))
                voices[voice_index].append(candidate)
                used.add(voice_index)
            elif len(voices) < maximum_voices:
                voices.append([candidate])
                used.add(len(voices) - 1)
            else:
                # Preserve the strongest evidence in the nearest available
                # voice only when it does not overlap.  Excess simultaneous
                # hypotheses remain represented in harmony_stack even though
                # they do not define another named voice.
                choices = [
                    (abs(voice[-1].note.pitch - candidate.note.pitch), index)
                    for index, voice in enumerate(voices)
                    if index not in used
                    and voice[-1].note.end <= candidate.note.start + 0.04
                ]
                if choices:
                    _, voice_index = min(choices)
                    voices[voice_index].append(candidate)
                    used.add(voice_index)
    return [voice for voice in voices if voice]


def _make_backing_voice_monophonic(
    voice: Sequence[VocalCandidate],
    *,
    minimum_seconds: float = 0.03,
) -> list[VocalCandidate]:
    """Resolve small Basic Pitch overlaps inside one selected vocal voice."""

    result: list[VocalCandidate] = []
    for candidate in sorted(
        voice, key=lambda value: (value.note.start, value.note.pitch)
    ):
        current = candidate
        if result and result[-1].note.end > current.note.start:
            previous = result[-1]
            if current.note.start - previous.note.start >= minimum_seconds:
                result[-1] = replace(
                    previous,
                    note=NoteEvent(
                        previous.note.start,
                        current.note.start,
                        previous.note.pitch,
                        previous.note.velocity,
                    ),
                )
            elif current.note.end - previous.note.end >= minimum_seconds:
                current = replace(
                    current,
                    note=NoteEvent(
                        previous.note.end,
                        current.note.end,
                        current.note.pitch,
                        current.note.velocity,
                    ),
                )
            elif current.confidence > previous.confidence:
                result.pop()
            else:
                continue
        result.append(current)
    return result


def _backing_voice_score(
    voice: Sequence[VocalCandidate], references: Sequence[NoteEvent]
) -> float:
    score = 0.0
    for candidate in voice:
        note = candidate.note
        duration = max(0.0, note.end - note.start)
        score += duration * candidate.confidence * (0.65 + note.velocity / 254.0)
        if references:
            matching = any(
                abs(reference.pitch - note.pitch) in {0, 12}
                and min(reference.end, note.end) - max(reference.start, note.start) > 0.04
                for reference in references
            )
            if matching:
                score += duration * 0.45
    if len(voice) > 1:
        intervals = [
            abs(right.note.pitch - left.note.pitch)
            for left, right in zip(voice, voice[1:])
        ]
        score -= sum(max(0, interval - 12) * 0.02 for interval in intervals)
    return score


def _median_voice_pitch(voice: Sequence[VocalCandidate]) -> float:
    return float(median(candidate.note.pitch for candidate in voice))


def _diagnostics_from_frames(
    frames: Sequence[PitchFrame],
    config: VocalConfig,
    *,
    estimated_voice_count: int,
    extra_warnings: Sequence[str] = (),
) -> VocalDiagnostics:
    hop = _frame_hop(frames)
    duration = frames[-1].time + hop if frames else 0.0
    midis = [
        frame.fractional_midi(config.tuning_hz)
        for frame in frames
        if frame.f0_hz is not None and frame.voiced_probability >= config.uncertain_voicing
    ]
    pitches = [_nearest_midi(value) for value in midis if value is not None]
    warnings = list(extra_warnings)
    fine_tune = 1200.0 * math.log2(config.tuning_hz / 440.0)
    if abs(fine_tune) >= 15.0:
        warnings.append(
            f"Standard A=440 playback must be fine-tuned by {fine_tune:+.2f} cents to match the source tuning."
        )
    if frames and not pitches:
        warnings.append("No sufficiently voiced pitch frames were found.")
    return VocalDiagnostics(
        role=config.role,
        tuning_hz=config.tuning_hz,
        tuning_source=config.tuning_source,
        garageband_fine_tune_cents=round(fine_tune, 6),
        duration_seconds=round(duration, 6),
        frame_count=len(frames),
        voiced_frame_count=len(pitches),
        detected_low_midi=min(pitches) if pitches else None,
        detected_high_midi=max(pitches) if pitches else None,
        estimated_voice_count=estimated_voice_count,
        warnings=tuple(warnings),
    )


def _validate_frames(frames: Sequence[PitchFrame]) -> list[PitchFrame]:
    values = list(frames)
    if any(right.time <= left.time for left, right in zip(values, values[1:])):
        raise ValueError("pitch frames must have strictly increasing times")
    return values


def _frame_hop(frames: Sequence[PitchFrame]) -> float:
    gaps = [right.time - left.time for left, right in zip(frames, frames[1:])]
    return float(median(gaps)) if gaps else 256.0 / 22_050.0


def _nearest_midi(value: float) -> int:
    return int(math.floor(value + 0.5))


def _median_absolute_deviation(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    centre = float(median(values))
    return float(median(abs(value - centre) for value in values))


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = max(0.0, min(100.0, percentile)) / 100.0 * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _note_key(note: NoteEvent) -> tuple[float, float, int]:
    return (round(note.start, 6), round(note.end, 6), note.pitch)


def _note_is_explained(note: NoteEvent, references: Sequence[NoteEvent]) -> bool:
    for reference in references:
        if reference.pitch != note.pitch:
            continue
        overlap = min(note.end, reference.end) - max(note.start, reference.start)
        shorter = min(note.end - note.start, reference.end - reference.start)
        if shorter > 0 and overlap >= 0.55 * shorter:
            return True
        if abs(note.start - reference.start) <= 0.08:
            return True
    return False


__all__ = [
    "PitchFrame",
    "VocalCandidate",
    "VocalConfig",
    "VocalDiagnostics",
    "VocalNoteEvidence",
    "VocalTranscription",
    "extract_backing_candidates",
    "extract_pitch_frames",
    "fractional_midi_to_hz",
    "gentle_quantize_notes",
    "hz_to_fractional_midi",
    "load_audio_phase_safe",
    "phase_safe_downmix",
    "select_backing_vocal_variants",
    "simplify_vocal_notes",
    "transcribe_vocal_frames",
    "transcribe_vocal_melody",
    "vocal_signal_stats",
]
