"""Align a chord chart to the audio it describes.

The Moises PDF gives the chord *sequence* but not reliable timing. Spreading
chords evenly across the song drifts as soon as any section length varies.
Here we align the sequence to beat-synchronous chroma of a harmonic stem
(keys/pads) with monotonic dynamic programming: each chord occupies 1..24
whole beats, chords stay in order, the whole song is covered, and we pick
the segmentation whose chroma best matches the chord templates.
"""
from __future__ import annotations

import numpy as np

from .beatgrid import Grid
from .chords import parse_chord_name
from .models import ChordSegment

# Moises emits chord changes rather than fixed-size cells. Intro harmony and
# held chords can therefore span substantially more than two 4/4 bars; keep a
# finite bound for the dynamic program while accommodating six-bar holds.
MAX_BEATS_PER_CHORD = 24


def align_chords_to_audio(
    chords: list[str],
    audio_path: str,
    grid: Grid,
    duration: float,
) -> list[ChordSegment]:
    """Returns ChordSegments with boundaries on actual beats of the grid."""
    import librosa

    parsed = [(name, parse_chord_name(name)) for name in chords]
    parsed = [(name, pcs) for name, pcs in parsed if pcs]
    if not parsed:
        raise ValueError("No parseable chords to align")

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    hop = 512
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop)

    # beat-synchronous chroma
    first_beat = int(np.ceil(grid.beat_of(0.0)))
    last_beat = int(np.floor(grid.beat_of(duration)))
    n_beats = last_beat - first_beat
    if n_beats < len(parsed):
        return _uniform_fallback(parsed, duration, grid)

    beat_chroma = np.zeros((12, n_beats))
    for b in range(n_beats):
        t0, t1 = grid.time_of(first_beat + b), grid.time_of(first_beat + b + 1)
        mask = (frame_times >= t0) & (frame_times < t1)
        if np.any(mask):
            beat_chroma[:, b] = chroma[:, mask].mean(axis=1)
    norms = np.linalg.norm(beat_chroma, axis=0, keepdims=True)
    beat_chroma = beat_chroma / (norms + 1e-9)

    # chord templates (root slightly emphasized)
    templates = np.zeros((len(parsed), 12))
    for i, (_, pcs) in enumerate(parsed):
        for pc in pcs:
            templates[i, pc] = 1.0
        templates[i, pcs[0]] = 1.5
        templates[i] /= np.linalg.norm(templates[i])

    sim = templates @ beat_chroma                       # (n_chords, n_beats)
    cum = np.concatenate([np.zeros((len(parsed), 1)), np.cumsum(sim, axis=1)], axis=1)

    n = len(parsed)
    NEG = -1e9
    best = np.full((n + 1, n_beats + 1), NEG)
    back = np.zeros((n + 1, n_beats + 1), dtype=int)
    best[0, 0] = 0.0
    for i in range(n):
        rem = n - 1 - i  # chords remaining after this one
        valid = np.where(best[i, : n_beats + 1] > NEG / 2)[0]
        for b in valid:
            max_d = min(MAX_BEATS_PER_CHORD, n_beats - b - rem)
            for d in range(1, max_d + 1):
                score = best[i, b] + (cum[i, b + d] - cum[i, b])
                if score > best[i + 1, b + d]:
                    best[i + 1, b + d] = score
                    back[i + 1, b + d] = d

    if best[n, n_beats] <= NEG / 2:
        return _uniform_fallback(parsed, duration, grid)

    # backtrack
    durations = []
    b = n_beats
    for i in range(n, 0, -1):
        d = back[i, b]
        durations.append(d)
        b -= d
    durations.reverse()

    segments: list[ChordSegment] = []
    beat = first_beat
    for (name, pcs), d in zip(parsed, durations):
        start = max(0.0, grid.time_of(beat))
        end = min(duration, grid.time_of(beat + d))
        segments.append(ChordSegment(start=start, end=end, name=name, pitch_classes=tuple(pcs)))
        beat += d
    return segments


def _uniform_fallback(parsed, duration: float, grid: Grid) -> list[ChordSegment]:
    step = duration / len(parsed)
    return [
        ChordSegment(start=i * step, end=(i + 1) * step, name=name, pitch_classes=tuple(pcs))
        for i, (name, pcs) in enumerate(parsed)
    ]
