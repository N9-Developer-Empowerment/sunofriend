"""Drum stem -> MIDI notes with confidence and per-hit timbre provenance.

The legacy :func:`transcribe_drum_stem` API deliberately remains conservative:
it returns only ``main`` (strongly observed) hits as ``NoteEvent`` objects.  New
callers can use :func:`transcribe_drum_stem_detailed` to inspect weaker onset
candidates, absolute source level, relative performance velocity, drum family,
and whether a note was observed, repaired, or inferred.

Detection and classification use different coordinate spaces on purpose.  A
50 ms prefix is used only while detecting first-frame onsets.  Feature windows
are always read from the original, unpadded, multi-channel audio at the final
un-padded timestamp.  Keeping that boundary explicit avoids the old 50 ms
classification-window error.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Iterable, Literal, Sequence

import numpy as np

from .models import NoteEvent

SR = 22050
HOP = 128  # ~5.8 ms at 22050 Hz

GM = {
    # Two useful GM variants for the two common families found in separated
    # kick/snare stems.  The names describe the source timbre, not a tuned note.
    "kick_deep": 36,
    "kick_high": 35,
    "kick": 36,
    "snare_body": 38,
    "snare_bright": 40,
    "snare": 38,
    "hat_closed": 42,
    "hat_open": 46,
    "tom_floor": 41,
    "tom_low": 45,
    "tom_mid": 48,
    "tom_high": 50,
    "crash": 49,
    "ride": 51,
    "unknown": 39,
    "perc": 39,  # hand clap remains the backwards-compatible fallback
}

_NOTE_DURATION = {
    "hat": 0.045,
    "cymbals": 0.4,
    "kick": 0.09,
    "snare": 0.09,
    "toms": 0.12,
    "other_kit": 0.08,
}
_OPEN_HAT_DECAY_SECONDS = 0.25

ConfidenceTier = Literal["main", "possible"]
HitProvenance = Literal["observed", "repaired", "inferred"]


@dataclass(frozen=True)
class DrumHitFeatures:
    """Audio evidence measured at a hit's unpadded source timestamp.

    ``peak_dbfs`` and ``rms_dbfs`` remain absolute source measurements.  MIDI
    velocity is calculated separately from a stem-relative level distribution,
    so turning an otherwise identical stem up or down does not flatten its
    performance dynamics.
    """

    peak_dbfs: float
    rms_dbfs: float
    absolute_confidence: float
    onset_strength: float
    dominant_hz: float
    spectral_centroid_hz: float
    spectral_flatness: float
    low_ratio: float
    mid_ratio: float
    high_ratio: float
    decay_seconds: float
    strongest_channel: int


@dataclass(frozen=True)
class DrumHit:
    # The first four fields retain the shape of the original public dataclass.
    time: float
    gm_pitch: int
    velocity: int
    strength: float
    family: str = "unknown"
    tier: ConfidenceTier = "main"
    provenance: HitProvenance = "observed"
    features: DrumHitFeatures | None = None
    source_time: float | None = None

    @property
    def peak_dbfs(self) -> float:
        return self.features.peak_dbfs if self.features is not None else -120.0

    @property
    def absolute_confidence(self) -> float:
        return self.features.absolute_confidence if self.features is not None else 0.0


@dataclass(frozen=True)
class DrumTranscription:
    """Detailed transcription with conservative and auditionable hit tiers."""

    kind: str
    sample_rate: int
    main_hits: tuple[DrumHit, ...]
    possible_hits: tuple[DrumHit, ...]

    @property
    def hits(self) -> tuple[DrumHit, ...]:
        return tuple(sorted((*self.main_hits, *self.possible_hits), key=lambda hit: hit.time))

    def to_notes(self, include_possible: bool = False) -> list[NoteEvent]:
        hits: Iterable[DrumHit] = self.hits if include_possible else self.main_hits
        duration = _NOTE_DURATION.get(self.kind, 0.08)
        return [
            NoteEvent(
                start=hit.time,
                end=hit.time + duration,
                pitch=hit.gm_pitch,
                velocity=hit.velocity,
            )
            for hit in sorted(hits, key=lambda item: item.time)
        ]


@dataclass(frozen=True)
class _Candidate:
    time: float
    frame: int
    tier: ConfidenceTier
    onset_strength: float
    raw_peak: float
    relative_peak: float
    features: DrumHitFeatures


def transcribe_drum_stem(path: str, kind: str, delta: float = 0.18) -> list[NoteEvent]:
    """Return conservative observed notes for a separated drum stem.

    ``kind`` is normally one of ``kick``, ``snare``, ``hat``, ``cymbals``,
    ``toms``, or ``other_kit``.  This is the backwards-compatible entry point;
    lower-confidence candidates are available from
    :func:`transcribe_drum_stem_detailed` but are never silently added here.
    """

    return transcribe_drum_stem_detailed(path, kind, delta=delta).to_notes()


def transcribe_drum_stem_detailed(
    path: str,
    kind: str,
    delta: float = 0.18,
    *,
    possible_delta: float | None = None,
) -> DrumTranscription:
    """Transcribe a stem and retain classification/confidence provenance.

    ``main_hits`` use the caller's conservative ``delta``.  ``possible_hits``
    are additional candidates from a lower threshold and are intentionally not
    included by the legacy API.  Part-specific multiband flux is used so a
    narrow low-frequency kick and a hit present in only one stereo channel can
    still contribute evidence.
    """

    import librosa

    source, sr = librosa.load(path, sr=SR, mono=False)
    channels = _as_channels(source)
    if channels.size == 0 or float(np.max(np.abs(channels))) < 1e-4:
        return DrumTranscription(kind, sr, (), ())

    source_peak = float(np.max(np.abs(channels)))
    detection_audio = channels / source_peak
    pad = int(0.05 * sr)
    padded = np.pad(detection_audio, ((0, 0), (pad, 0)))

    broadband_env = _clip_envelope_spikes(_broadband_onset_envelope(padded, sr))
    part_env = _clip_envelope_spikes(_part_onset_envelope(padded, sr, kind))
    onset_env = _combine_onset_evidence(broadband_env, part_env)
    if broadband_env.size == 0 or float(np.max(broadband_env)) <= 0.0:
        return DrumTranscription(kind, sr, (), ())

    # Main output retains the conservative broadband contract.  Part-specific
    # bands contribute to the possible pass, where a narrow low kick or a
    # one-channel event can be auditioned without flooding the default MIDI.
    main_frames = _detect_frames(broadband_env, sr, kind, delta)
    lower_delta = possible_delta if possible_delta is not None else max(0.045, delta * 0.48)
    possible_frames = _detect_frames(onset_env, sr, kind, min(lower_delta, delta))

    candidates = _make_candidates(
        channels,
        sr,
        kind,
        onset_env,
        main_frames,
        possible_frames,
        pad,
        source_peak,
    )
    if not candidates:
        return DrumTranscription(kind, sr, (), ())

    main_peak_reference = [
        candidate.raw_peak for candidate in candidates if candidate.tier == "main"
    ]
    velocities = _relative_velocities(
        [candidate.raw_peak for candidate in candidates],
        reference_peaks=main_peak_reference or None,
    )
    hits: list[DrumHit] = []
    for candidate, velocity in zip(candidates, velocities):
        family, pitch = _classify_features(kind, candidate.features)
        hits.append(
            DrumHit(
                time=candidate.time,
                gm_pitch=pitch,
                velocity=velocity,
                strength=candidate.relative_peak,
                family=family,
                tier=candidate.tier,
                provenance="observed",
                features=candidate.features,
                source_time=candidate.time,
            )
        )

    main_hits = tuple(hit for hit in hits if hit.tier == "main")
    possible_hits = tuple(hit for hit in hits if hit.tier == "possible")
    return DrumTranscription(kind, sr, main_hits, possible_hits)


def complete_hat_pattern(
    transcription: DrumTranscription,
    *,
    bpm: float,
    mode: Literal["exact", "repair", "reconstruct"] = "exact",
    downbeat: float = 0.0,
    snap: Callable[[float], float] | None = None,
    beat_of: Callable[[float], float] | None = None,
    time_of: Callable[[float], float] | None = None,
    beats_per_bar: int = 4,
    nearby_bars: int = 2,
) -> DrumTranscription:
    """Optionally complete a recurring sixteenth-note hat pattern.

    ``exact`` returns the observed tiers unchanged.  ``repair`` promotes only
    *existing possible audio candidates* when the same sixteenth slot is
    strongly observed in at least three nearby bars.  ``reconstruct`` additionally
    fills locally recurring slots (at least three supporting nearby bars), with
    ``provenance='inferred'`` so generated notes can never be mistaken for audio
    evidence.  No completion mode is enabled by the legacy transcription API.
    """

    if transcription.kind != "hat":
        raise ValueError("hat pattern completion requires a hat transcription")
    if bpm <= 0:
        raise ValueError("bpm must be positive")
    if mode not in {"exact", "repair", "reconstruct"}:
        raise ValueError("mode must be exact, repair, or reconstruct")
    if mode == "exact" or not transcription.hits:
        return transcription

    sixteenth = 60.0 / bpm / 4.0
    slots_per_bar = beats_per_bar * 4

    if (beat_of is None) != (time_of is None):
        raise ValueError("beat_of and time_of must be supplied together")

    def slot_for(time: float) -> tuple[int, int, float]:
        if beat_of is not None and time_of is not None:
            absolute_slot = int(round(beat_of(time) * 4.0))
            snapped = time_of(absolute_slot / 4.0)
        else:
            snapped = snap(time) if snap is not None else (
                downbeat + round((time - downbeat) / sixteenth) * sixteenth
            )
            absolute_slot = int(round((snapped - downbeat) / sixteenth))
        bar, slot = divmod(absolute_slot, slots_per_bar)
        return bar, slot, snapped

    observed_main = [hit for hit in transcription.main_hits if hit.provenance == "observed"]
    support: dict[int, set[int]] = {}
    for hit in observed_main:
        bar, slot, _ = slot_for(hit.time)
        support.setdefault(slot, set()).add(bar)

    def nearby_support(bar: int, slot: int) -> int:
        return sum(1 for other in support.get(slot, ()) if 0 < abs(other - bar) <= nearby_bars)

    occupied = {(slot_for(hit.time)[0], slot_for(hit.time)[1]) for hit in transcription.main_hits}
    possible_by_slot: dict[tuple[int, int], list[tuple[DrumHit, float]]] = {}
    for hit in transcription.possible_hits:
        bar, slot, snapped = slot_for(hit.time)
        possible_by_slot.setdefault((bar, slot), []).append((hit, snapped))

    promoted: list[DrumHit] = []
    remaining_possible: list[DrumHit] = []
    for (bar, slot), values in sorted(possible_by_slot.items()):
        strongest, snapped = max(
            values,
            key=lambda value: (
                value[0].absolute_confidence,
                value[0].strength,
                value[0].velocity,
            ),
        )
        eligible = (
            (bar, slot) not in occupied
            and nearby_support(bar, slot) >= 3
            and _credible_hat_candidate(strongest)
        )
        if eligible:
            # A weak candidate whose tail overlaps another hit cannot safely
            # establish an open articulation.  Closed is the conservative
            # repair; the original family remains in the possible sidecar.
            family = strongest.family
            if family == "hat_open" and _next_hit_gap(
                strongest.time, transcription.hits
            ) < _OPEN_HAT_DECAY_SECONDS:
                family = "hat_closed"
            promoted.append(
                replace(
                    strongest,
                    time=snapped,
                    gm_pitch=GM[family],
                    family=family,
                    tier="main",
                    provenance="repaired",
                    source_time=strongest.source_time or strongest.time,
                )
            )
            occupied.add((bar, slot))
            remaining_possible.extend(hit for hit, _ in values if hit is not strongest)
        else:
            remaining_possible.extend(hit for hit, _ in values)

    main = sorted((*transcription.main_hits, *promoted), key=lambda item: item.time)
    if mode == "repair":
        return DrumTranscription("hat", transcription.sample_rate, tuple(main), tuple(remaining_possible))

    # Reconstruct only within the already-observed bar span, and require local
    # section support rather than extrapolating a global song-wide pattern.
    observed_bars = [slot_for(hit.time)[0] for hit in observed_main]
    if not observed_bars:
        return DrumTranscription("hat", transcription.sample_rate, tuple(main), tuple(remaining_possible))
    first_bar, last_bar = min(observed_bars), max(observed_bars)
    existing_slots = {(slot_for(hit.time)[0], slot_for(hit.time)[1]) for hit in main}
    inferred: list[DrumHit] = []
    for bar in range(first_bar, last_bar + 1):
        for slot in range(slots_per_bar):
            if (bar, slot) in existing_slots or nearby_support(bar, slot) < 3:
                continue
            absolute_beat = (bar * slots_per_bar + slot) / 4.0
            if time_of is not None:
                time = time_of(absolute_beat)
            else:
                time = downbeat + ((bar * slots_per_bar + slot) * sixteenth)
                if snap is not None:
                    time = snap(time)
            family = _supported_hat_family(observed_main, slot_for, slot, bar, nearby_bars)
            pitch = GM[family]
            velocity = _supported_hat_velocity(observed_main, slot_for, slot, bar, nearby_bars)
            inferred.append(
                DrumHit(
                    time=time,
                    gm_pitch=pitch,
                    velocity=velocity,
                    strength=0.0,
                    family=family,
                    tier="main",
                    provenance="inferred",
                    features=None,
                    source_time=None,
                )
            )
    main.extend(inferred)
    main.sort(key=lambda item: item.time)
    return DrumTranscription("hat", transcription.sample_rate, tuple(main), tuple(remaining_possible))


def _credible_hat_candidate(hit: DrumHit) -> bool:
    """Require actual high-frequency hat evidence before pattern promotion."""

    features = hit.features
    if features is None:  # deterministic/manual test fixtures
        return True
    return bool(
        features.absolute_confidence >= 0.35
        and features.spectral_centroid_hz >= 1800.0
        and features.high_ratio >= 0.35
    )


def _next_hit_gap(time: float, hits: Sequence[DrumHit]) -> float:
    later = [hit.time - time for hit in hits if hit.time > time + 1e-6]
    return min(later) if later else float("inf")


def _supported_hat_family(
    hits: Sequence[DrumHit],
    slot_for: Callable[[float], tuple[int, int, float]],
    slot: int,
    bar: int,
    nearby_bars: int,
) -> str:
    families = [
        hit.family
        for hit in hits
        if slot_for(hit.time)[1] == slot and abs(slot_for(hit.time)[0] - bar) <= nearby_bars
    ]
    return "hat_open" if families.count("hat_open") > families.count("hat_closed") else "hat_closed"


def _supported_hat_velocity(
    hits: Sequence[DrumHit],
    slot_for: Callable[[float], tuple[int, int, float]],
    slot: int,
    bar: int,
    nearby_bars: int,
) -> int:
    values = [
        hit.velocity
        for hit in hits
        if slot_for(hit.time)[1] == slot and abs(slot_for(hit.time)[0] - bar) <= nearby_bars
    ]
    return int(round(float(np.median(values)))) if values else 70


def _as_channels(audio: np.ndarray) -> np.ndarray:
    values = np.asarray(audio, dtype=np.float64)
    if values.ndim == 1:
        values = values[np.newaxis, :]
    elif values.ndim != 2:
        values = values.reshape((-1, values.shape[-1]))
    return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)


def _part_onset_envelope(audio: np.ndarray, sr: int, kind: str) -> np.ndarray:
    """Return max-pooled stereo/multiband positive spectral flux."""

    import librosa

    n_fft = 1024
    bands = _bands_for_kind(kind, sr)
    envelopes: list[np.ndarray] = []
    for channel in _as_channels(audio):
        spectrum = np.abs(
            librosa.stft(channel, n_fft=n_fft, hop_length=HOP, center=True)
        )
        frequencies = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
        log_spectrum = np.log1p(20.0 * spectrum)
        for low_hz, high_hz, weight in bands:
            mask = (frequencies >= low_hz) & (frequencies < high_hz)
            if not np.any(mask):
                continue
            band = log_spectrum[mask]
            # Mean flux is intentionally used instead of a broadband median:
            # a narrow resonant kick should not disappear merely because most
            # high-frequency bins are silent.
            delta = np.maximum(np.diff(band, axis=1, prepend=band[:, :1]), 0.0)
            env = np.mean(delta, axis=0)
            if env.size >= 3:
                env = np.convolve(env, np.array([0.15, 0.7, 0.15]), mode="same")
            positive = env[env > 1e-9]
            if positive.size:
                scale = float(np.percentile(positive, 95.0))
                if scale > 0:
                    env = np.clip(env / scale, 0.0, 2.5) * weight
            envelopes.append(env)
    if not envelopes:
        return np.zeros(0, dtype=float)
    length = min(len(env) for env in envelopes)
    return np.max(np.vstack([env[:length] for env in envelopes]), axis=0)


def _broadband_onset_envelope(audio: np.ndarray, sr: int) -> np.ndarray:
    """Conservative broadband flux, max-pooled without stereo cancellation."""

    import librosa

    envelopes = [
        librosa.onset.onset_strength(
            y=channel,
            sr=sr,
            hop_length=HOP,
            aggregate=np.median,
        )
        for channel in _as_channels(audio)
    ]
    if not envelopes:
        return np.zeros(0, dtype=float)
    length = min(len(env) for env in envelopes)
    return np.max(np.vstack([env[:length] for env in envelopes]), axis=0)


def _combine_onset_evidence(
    broadband: np.ndarray,
    part_specific: np.ndarray,
    part_weight: float = 0.12,
) -> np.ndarray:
    """Blend aligned band evidence into the lower-confidence detector.

    ``librosa.onset_strength`` compensates for its centred analysis window,
    while the explicit spectral-flux helper does not.  Seven frames aligns the
    two 1024/128 analyses empirically and in the synthetic timing regression.
    The low weight is deliberate: band-only evidence can cross the lower
    possible threshold, but cannot by itself enter the conservative main tier.
    """

    if broadband.size == 0:
        return broadband
    full = broadband / max(float(np.max(broadband)), 1e-9)
    if part_specific.size == 0:
        return full
    band = part_specific / max(float(np.max(part_specific)), 1e-9)
    aligned = np.pad(band, (7, 0))
    length = min(len(full), len(aligned))
    combined = np.maximum(full[:length], part_weight * aligned[:length])
    return combined


def _bands_for_kind(kind: str, sr: int) -> tuple[tuple[float, float, float], ...]:
    nyquist = sr / 2.0
    high = min(10000.0, nyquist)
    if kind == "kick":
        return ((25.0, min(240.0, high), 1.0), (25.0, min(1800.0, high), 0.82))
    if kind == "snare":
        return ((100.0, min(2200.0, high), 0.9), (1200.0, high, 1.0))
    if kind in {"hat", "cymbals"}:
        return ((1800.0, high, 1.0), (500.0, high, 0.72))
    if kind == "toms":
        return ((40.0, min(500.0, high), 1.0), (40.0, min(2200.0, high), 0.75))
    # A mixed other-kit stem must give low, mid, and high events independent
    # opportunities instead of collapsing them through one broadband median.
    return (
        (25.0, min(240.0, high), 1.0),
        (120.0, min(2200.0, high), 0.9),
        (1800.0, high, 1.0),
    )


def _detect_frames(env: np.ndarray, sr: int, kind: str, delta: float) -> np.ndarray:
    import librosa

    wait = {"hat": 2, "cymbals": 5}.get(kind, 4)
    return np.asarray(
        librosa.onset.onset_detect(
            onset_envelope=env,
            sr=sr,
            hop_length=HOP,
            backtrack=False,
            normalize=True,
            delta=max(0.0, float(delta)),
            pre_max=6,
            post_max=6,
            pre_avg=12,
            post_avg=12,
            wait=wait,
        ),
        dtype=int,
    )


def _make_candidates(
    source: np.ndarray,
    sr: int,
    kind: str,
    onset_env: np.ndarray,
    main_frames: np.ndarray,
    possible_frames: np.ndarray,
    pad: int,
    source_peak: float,
) -> list[_Candidate]:
    import librosa

    duration = source.shape[1] / sr
    main = {int(frame) for frame in main_frames}
    all_frames = sorted(main | {int(frame) for frame in possible_frames})
    candidates: list[_Candidate] = []
    # The hi-hat detector is intentionally sensitive to short high-frequency
    # transients, but the flux envelope can ring three frames after one strike.
    # At normal song tempi a 30 ms retrigger is not a useful separate hat note
    # (even 1/32 notes at 200 BPM are 37.5 ms), so retain only the stronger
    # evidence in that window.  Keep the smaller two-frame merge for the other
    # kit pieces so genuine snare flams are not silently collapsed.
    merge_seconds = max(2.0 * HOP / sr, 0.030 if kind == "hat" else 0.0)
    for frame in all_frames:
        padded_time = float(librosa.frames_to_time(frame, sr=sr, hop_length=HOP))
        time = max(0.0, padded_time - (pad / sr))
        if time >= duration:
            continue
        window = _hit_window(source, sr, time)
        if window is None:
            continue
        raw_peak = float(np.max(np.abs(window)))
        # Spectral flux can ring after a short sample has already decayed to
        # digital silence.  Such a frame contains no source evidence at its own
        # aligned timestamp and should not become even a possible MIDI hit.
        if source_peak <= 0.0 or raw_peak / source_peak < 1e-4:
            continue
        features = _measure_features(source, sr, time, onset_env[min(frame, len(onset_env) - 1)])
        tier: ConfidenceTier = "main" if _near_any_frame(frame, main, radius=1) else "possible"
        candidate = _Candidate(
            time=time,
            frame=frame,
            tier=tier,
            onset_strength=float(onset_env[min(frame, len(onset_env) - 1)]),
            raw_peak=raw_peak,
            relative_peak=(raw_peak / source_peak) if source_peak > 0 else 0.0,
            features=features,
        )
        # The lower-threshold pass can place its local maximum one frame away
        # from a main hit.  Keep one aligned candidate, preferring the main tier.
        if candidates and abs(candidate.time - candidates[-1].time) < merge_seconds:
            previous = candidates[-1]
            if previous.tier == "possible" and candidate.tier == "main":
                candidates[-1] = candidate
            elif previous.tier == candidate.tier and (
                candidate.raw_peak > previous.raw_peak
                or candidate.onset_strength > previous.onset_strength * 1.08
            ):
                candidates[-1] = candidate
            continue
        candidates.append(candidate)
    return candidates


def _near_any_frame(frame: int, frames: set[int], radius: int) -> bool:
    return any((frame + offset) in frames for offset in range(-radius, radius + 1))


def _measure_features(
    source: np.ndarray,
    sr: int,
    time: float,
    onset_strength: float,
) -> DrumHitFeatures:
    window = _hit_window(source, sr, time, length=0.09)
    assert window is not None
    channels = _as_channels(window)
    per_channel_rms = np.sqrt(np.mean(np.square(channels), axis=1))
    strongest_channel = int(np.argmax(per_channel_rms))
    peak = float(np.max(np.abs(channels)))
    rms = float(np.sqrt(np.mean(np.square(channels))))

    n = channels.shape[1]
    taper = np.hanning(n)
    spectra = np.fft.rfft(channels * taper[np.newaxis, :], axis=1)
    power = np.sum(np.square(np.abs(spectra)), axis=0)
    frequencies = np.fft.rfftfreq(n, 1.0 / sr)
    total = float(np.sum(power))
    if total <= 1e-20:
        dominant = centroid = flatness = 0.0
        low_ratio = mid_ratio = high_ratio = 0.0
    else:
        dominant = float(frequencies[int(np.argmax(power))])
        centroid = float(np.sum(frequencies * power) / total)
        positive = np.maximum(power, 1e-20)
        flatness = float(np.exp(np.mean(np.log(positive))) / np.mean(positive))
        low_ratio = float(np.sum(power[(frequencies >= 20.0) & (frequencies < 200.0)]) / total)
        mid_ratio = float(np.sum(power[(frequencies >= 200.0) & (frequencies < 2000.0)]) / total)
        high_ratio = float(np.sum(power[frequencies >= 2000.0]) / total)

    peak_dbfs = _dbfs(peak)
    return DrumHitFeatures(
        peak_dbfs=peak_dbfs,
        rms_dbfs=_dbfs(rms),
        absolute_confidence=float(np.clip((peak_dbfs + 72.0) / 60.0, 0.0, 1.0)),
        onset_strength=float(onset_strength),
        dominant_hz=dominant,
        spectral_centroid_hz=centroid,
        spectral_flatness=flatness,
        low_ratio=low_ratio,
        mid_ratio=mid_ratio,
        high_ratio=high_ratio,
        decay_seconds=_decay_seconds(source, sr, time),
        strongest_channel=strongest_channel,
    )


def _classify_features(kind: str, features: DrumHitFeatures) -> tuple[str, int]:
    if kind == "kick":
        family = "kick_deep" if features.dominant_hz < 82.0 else "kick_high"
        return family, GM[family]
    if kind == "snare":
        # Broadband/noisy attacks with a high centroid form the bright family.
        family = "snare_bright" if (
            features.spectral_centroid_hz > 2200.0 and features.high_ratio > 0.18
        ) else "snare_body"
        return family, GM[family]
    if kind == "hat":
        # Separated stems often retain the following sixteenth or low-level
        # cymbal wash.  Requiring a quarter-second sustained decay avoids
        # turning ordinary closed hats into open hats merely because of that
        # overlap, while preserving a clear second articulation family.
        family = (
            "hat_open"
            if features.decay_seconds > _OPEN_HAT_DECAY_SECONDS
            else "hat_closed"
        )
        return family, GM[family]
    if kind == "cymbals":
        family = "crash" if features.decay_seconds > 0.5 else "ride"
        return family, GM[family]
    if kind == "toms":
        family = _tom_family(features.dominant_hz)
        return family, GM[family]
    if kind == "other_kit":
        return _classify_other_kit(features)
    return "unknown", GM["unknown"]


def _classify_other_kit(features: DrumHitFeatures) -> tuple[str, int]:
    # Long, bright broadband events are cymbals; short ones are hats.
    if features.high_ratio > 0.48 and features.spectral_centroid_hz > 2500.0:
        family = "crash" if features.decay_seconds > 0.42 else (
            "hat_open"
            if features.decay_seconds > _OPEN_HAT_DECAY_SECONDS
            else "hat_closed"
        )
        return family, GM[family]
    # A resonant low-frequency transient is kick-like.
    if features.low_ratio > 0.58 and features.spectral_centroid_hz < 320.0:
        family = "kick_deep" if features.dominant_hz < 82.0 else "kick_high"
        return family, GM[family]
    # Tonal low/mid resonances are toms.  This precedes the noise/snare rule.
    if (
        48.0 <= features.dominant_hz <= 330.0
        and (features.low_ratio + features.mid_ratio) > 0.72
        and features.spectral_flatness < 0.08
    ):
        family = _tom_family(features.dominant_hz)
        return family, GM[family]
    if features.spectral_centroid_hz > 700.0 and (
        features.mid_ratio + features.high_ratio
    ) > 0.45:
        family = "snare_bright" if features.spectral_centroid_hz > 2200.0 else "snare_body"
        return family, GM[family]
    return "unknown", GM["unknown"]


def _tom_family(hz: float) -> str:
    if hz < 95.0:
        return "tom_floor"
    if hz < 140.0:
        return "tom_low"
    if hz < 200.0:
        return "tom_mid"
    return "tom_high"


def _clip_envelope_spikes(env: np.ndarray, percentile: float = 95.0) -> np.ndarray:
    """Prevent one outlier transient from drowning all later local peaks."""

    nonzero = env[env > 0.01]
    if nonzero.size == 0:
        return env
    return np.clip(env, 0.0, float(np.percentile(nonzero, percentile)))


def _hit_window(
    y: np.ndarray,
    sr: int,
    t: float,
    length: float = 0.08,
) -> np.ndarray | None:
    """Read an aligned window from unpadded mono or multi-channel audio."""

    channels = _as_channels(y)
    start = max(0, int(round(t * sr)))
    end = min(channels.shape[1], start + int(length * sr))
    if end - start < 32:
        return None
    return channels[:, start:end]


def _relative_velocities(
    peaks: Sequence[float],
    *,
    reference_peaks: Sequence[float] | None = None,
) -> list[int]:
    """Map within-stem dynamics to MIDI independently of absolute source gain.

    The main tier is the default reference distribution.  Consequently asking
    the extended API to search for more possible hits cannot change velocities
    in the conservative legacy output.
    """

    if not peaks:
        return []
    db = np.asarray([_dbfs(value) for value in peaks], dtype=float)
    reference = np.asarray(
        [_dbfs(value) for value in (reference_peaks or peaks)], dtype=float
    )
    if len(reference) == 1 or float(np.max(reference) - np.min(reference)) < 0.5:
        values = 100.0 + ((db - float(np.median(reference))) * 3.0)
        return [int(round(value)) for value in np.clip(values, 30.0, 120.0)]
    low = float(np.percentile(reference, 10.0))
    high = float(np.percentile(reference, 95.0))
    span = max(3.0, high - low)
    values = 42.0 + (np.clip((db - low) / span, 0.0, 1.0) * 78.0)
    return [int(round(value)) for value in values]


def _dbfs(value: float) -> float:
    return 20.0 * float(np.log10(max(float(value), 1e-6)))


def _decay_seconds(
    y: np.ndarray,
    sr: int,
    t: float,
    drop_db: float = 20.0,
) -> float:
    """Time for the post-onset multi-channel envelope to fall by ``drop_db``."""

    channels = _as_channels(y)
    start = max(0, int(round(t * sr)))
    segment = np.max(
        np.abs(channels[:, start : min(channels.shape[1], start + sr)]), axis=0
    )
    if segment.size < 64:
        return 0.0
    # Search for the attack peak only near this onset.  Looking across the full
    # second lets the next sixteenth-note hat (or leaked snare) become the peak,
    # which makes a closed hat look artificially open.
    attack_samples = min(len(segment), max(64, int(0.060 * sr)))
    peak_index = int(np.argmax(segment[:attack_samples]))
    peak = float(segment[peak_index])
    if peak <= 0:
        return 0.0
    threshold = peak * (10 ** (-drop_db / 20.0))
    hop = 128
    hold = max(1, int(0.012 * sr / hop))
    tail = segment[peak_index:]
    block_count = len(tail) // hop
    if block_count:
        block_peaks = np.max(tail[: block_count * hop].reshape(block_count, hop), axis=1)
        below = block_peaks < threshold
        if hold == 1:
            matches = np.flatnonzero(below)
        else:
            matches = np.flatnonzero(
                np.convolve(below.astype(np.int8), np.ones(hold, dtype=np.int8), mode="valid")
                == hold
            )
        if matches.size:
            # Match the former semantics: return the start of the final block
            # in the first sustained-below run.
            block = int(matches[0]) + hold - 1
            return max(0.0, (block * hop) / sr)
    return max(0.0, (len(segment) - peak_index) / sr)


def _dominant_hz(window: np.ndarray, sr: int) -> float:
    """Backwards-compatible helper using non-cancelling channel power."""

    channels = _as_channels(window)
    taper = np.hanning(channels.shape[1])
    spectra = np.fft.rfft(channels * taper[np.newaxis, :], axis=1)
    power = np.sum(np.square(np.abs(spectra)), axis=0)
    frequencies = np.fft.rfftfreq(channels.shape[1], 1.0 / sr)
    return float(frequencies[int(np.argmax(power))]) if float(np.sum(power)) > 0 else 0.0


def _velocity(peak: float) -> int:
    """Retained for callers of the old internal helper.

    Full transcription uses :func:`_relative_velocities`; this function keeps
    the former absolute one-hit mapping semantics for compatibility.
    """

    velocity = int(round(127 + (_dbfs(peak) * 3.0)))
    return max(30, min(127, velocity))


def _classify(kind: str, window: np.ndarray, sr: int, y: np.ndarray, t: float) -> int:
    """Compatibility wrapper around the aligned feature classifier."""

    features = _measure_features(_as_channels(y), sr, t, 0.0)
    return _classify_features(kind, features)[1]
