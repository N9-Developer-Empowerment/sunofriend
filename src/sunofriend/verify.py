"""Per-note spectral verification against the original stem.

A constant-Q transform (a Fourier transform with one bin per semitone) lets us
ask, for every candidate MIDI note: does the stem actually contain energy at
this pitch, during this time, above the noise floor — and is that pitch at
least somewhat prominent among what's sounding? Notes with no such support are
transcription ghosts; they are the main reason dense parts sound random.

Two measures per note, both cheap:
  energy    - median CQT magnitude at the note's semitone bin (plus a small
              octave-harmonic bonus) over the note's duration, relative to the
              track's loud reference level.
  dominance - that magnitude relative to the strongest bin sounding at the
              same time (a chord tone scores ~1/3..1; a ghost scores ~0).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import NoteEvent

SR = 22050
HOP = 512
FMIN_MIDI = 24          # C1
N_BINS = 84             # C1..B7


@dataclass
class VerifyResult:
    kept: list[NoteEvent]
    dropped: list[NoteEvent]
    support: list[float]  # support score per input note, same order


class StemSpectrum:
    """CQT of a stem, reusable across verification calls."""

    def __init__(self, path: str):
        import librosa

        y, sr = librosa.load(path, sr=SR, mono=True)
        cqt = np.abs(
            librosa.cqt(y=y, sr=sr, hop_length=HOP, n_bins=N_BINS,
                        bins_per_octave=12, fmin=librosa.midi_to_hz(FMIN_MIDI))
        )
        self.cqt = cqt
        self.frame_seconds = HOP / SR
        # loud reference: 95th percentile of per-frame peak magnitude
        frame_peaks = cqt.max(axis=0)
        self.reference = float(np.percentile(frame_peaks[frame_peaks > 0], 95)) if np.any(frame_peaks > 0) else 1.0

    def note_support(self, note: NoteEvent) -> float:
        """0..1-ish score combining energy and dominance for one note."""
        bin_index = note.pitch - FMIN_MIDI
        if not (0 <= bin_index < N_BINS):
            return 0.0
        f0 = int(note.start / self.frame_seconds)
        f1 = max(f0 + 1, int(note.end / self.frame_seconds))
        f0 = min(f0, self.cqt.shape[1] - 1)
        f1 = min(f1, self.cqt.shape[1])
        window = self.cqt[:, f0:f1]
        if window.size == 0:
            return 0.0

        band = window[bin_index].astype(float)
        if bin_index + 12 < N_BINS:  # first harmonic bonus helps low notes
            band = band + 0.33 * window[bin_index + 12]

        energy = float(np.median(band)) / (self.reference + 1e-9)
        peaks = window.max(axis=0).astype(float)
        dominance = float(np.median(band / (peaks + 1e-9)))
        # geometric-ish blend: both must be non-trivial
        return float(np.sqrt(max(energy, 0.0) * max(dominance, 0.0)))


def verify_notes(
    stem_path: str,
    notes: list[NoteEvent],
    threshold: float = 0.08,
    spectrum: StemSpectrum | None = None,
) -> VerifyResult:
    """Split notes into spectrally supported vs ghosts."""
    if not notes:
        return VerifyResult(kept=[], dropped=[], support=[])
    spectrum = spectrum or StemSpectrum(stem_path)
    support = [spectrum.note_support(n) for n in notes]
    kept, dropped = [], []
    for note, score in zip(notes, support):
        (kept if score >= threshold else dropped).append(note)
    return VerifyResult(kept=kept, dropped=dropped, support=support)
