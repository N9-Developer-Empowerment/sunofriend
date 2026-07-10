"""Drum stem -> MIDI notes via onset detection + per-hit spectral classification.

Works on separated stems (kick.wav, snare.wav, ...) so the caller tells us the
kit piece ("kind"); classification only picks the GM variant within that piece
(closed vs open hat, low vs high tom, crash vs ride).

Unlike the legacy RMS/grid detector, onsets are located at ~6 ms resolution and
are NOT force-quantized here; velocities come from per-hit peak energy.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import NoteEvent

SR = 22050
HOP = 128  # ~5.8 ms at 22050 Hz

GM = {
    "kick": 36,
    "snare": 38,
    "hat_closed": 42,
    "hat_open": 46,
    "tom_floor": 41,
    "tom_low": 45,
    "tom_mid": 48,
    "tom_high": 50,
    "crash": 49,
    "ride": 51,
    "perc": 39,  # hand clap as generic fallback
}

_NOTE_DURATION = {"hat": 0.045, "cymbals": 0.4, "kick": 0.09, "snare": 0.09, "toms": 0.12, "other_kit": 0.08}


@dataclass(frozen=True)
class DrumHit:
    time: float
    gm_pitch: int
    velocity: int
    strength: float


def transcribe_drum_stem(path: str, kind: str, delta: float = 0.18) -> list[NoteEvent]:
    """kind: kick | snare | hat | cymbals | toms | other_kit"""
    import librosa

    y, sr = librosa.load(path, sr=SR, mono=True)
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-4:
        return []
    y = y / float(np.max(np.abs(y)))
    # Pad with silence so a hit at t=0 still produces a detectable onset rise.
    pad = int(0.05 * sr)
    y = np.pad(y, (pad, 0))

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    onset_env = _clip_envelope_spikes(onset_env)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=HOP,
        backtrack=False,
        delta=delta,
        pre_max=6,
        post_max=6,
        pre_avg=12,
        post_avg=12,
        wait=4,  # >= ~23 ms between hits
    )
    times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=HOP) - (pad / sr)
    times = np.maximum(times, 0.0)

    hits: list[DrumHit] = []
    for t in times:
        window = _hit_window(y, sr, t)
        if window is None:
            continue
        peak = float(np.max(np.abs(window)))
        pitch = _classify(kind, window, sr, y, t)
        hits.append(DrumHit(time=float(t), gm_pitch=pitch, velocity=_velocity(peak), strength=peak))

    duration = _NOTE_DURATION.get(kind, 0.08)
    return [
        NoteEvent(start=h.time, end=h.time + duration, pitch=h.gm_pitch, velocity=h.velocity)
        for h in hits
    ]


def _clip_envelope_spikes(env: np.ndarray, percentile: float = 95.0) -> np.ndarray:
    """librosa peak-picking normalizes by the envelope max; one outlier spike
    (e.g. first hit after silence) would otherwise drown every other peak."""
    nonzero = env[env > 0.01]
    if nonzero.size == 0:
        return env
    return np.clip(env, 0.0, float(np.percentile(nonzero, percentile)))


def _hit_window(y: np.ndarray, sr: int, t: float, length: float = 0.08) -> np.ndarray | None:
    start = int(t * sr)
    end = min(len(y), start + int(length * sr))
    if end - start < 32:
        return None
    return y[start:end]


def _velocity(peak: float) -> int:
    # perceptual-ish mapping: full-scale peak -> 127, -30 dB -> ~35
    db = 20.0 * np.log10(max(peak, 1e-4))
    vel = int(round(127 + (db * 3.0)))
    return max(30, min(127, vel))


def _decay_seconds(y: np.ndarray, sr: int, t: float, drop_db: float = 20.0) -> float:
    """Time for the hit to decay by drop_db from its peak."""
    start = int(t * sr)
    seg = np.abs(y[start : min(len(y), start + sr)])
    if seg.size < 64:
        return 0.0
    peak = float(np.max(seg))
    if peak <= 0:
        return 0.0
    threshold = peak * (10 ** (-drop_db / 20.0))
    hop = 256
    for i in range(0, len(seg) - hop, hop):
        if float(np.max(seg[i : i + hop])) < threshold:
            return i / sr
    return len(seg) / sr


def _dominant_hz(window: np.ndarray, sr: int) -> float:
    spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
    freqs = np.fft.rfftfreq(len(window), 1.0 / sr)
    if spectrum.sum() <= 0:
        return 0.0
    return float(freqs[int(np.argmax(spectrum))])


def _classify(kind: str, window: np.ndarray, sr: int, y: np.ndarray, t: float) -> int:
    if kind == "kick":
        return GM["kick"]
    if kind == "snare":
        return GM["snare"]
    if kind == "hat":
        return GM["hat_open"] if _decay_seconds(y, sr, t) > 0.14 else GM["hat_closed"]
    if kind == "cymbals":
        # rides keep energy narrow/tonal; crashes are broadband with long decay
        return GM["crash"] if _decay_seconds(y, sr, t, drop_db=15.0) > 0.5 else GM["ride"]
    if kind == "toms":
        hz = _dominant_hz(window, sr)
        if hz < 95:
            return GM["tom_floor"]
        if hz < 140:
            return GM["tom_low"]
        if hz < 200:
            return GM["tom_mid"]
        return GM["tom_high"]
    return GM["perc"]
