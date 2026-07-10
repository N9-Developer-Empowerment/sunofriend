"""Beat grid derived from the metronome stem (or nominal BPM as fallback).

Suno/Moises exports include a metronome track whose clicks are beat-tracked
from the song itself. Two truths hide in it:

  1. The average tempo usually differs from the labeled BPM (124 -> 124.538).
  2. The beat positions WANDER around the ideal straight grid (hundreds of ms
     over a song) — the track breathes like a human performance.

A Grid therefore carries an optional warp map (the actual click times per
integer beat). beat_of/time_of/snap interpolate through it, so quantized
notes land on the song's real beats, not an idealized ruler's.
"""
from __future__ import annotations


class Grid:
    def __init__(
        self,
        bpm: float,
        offset: float = 0.0,
        beats_per_bar: int = 4,
        beat_times: "list[float] | None" = None,
        first_beat_index: int = 0,
    ):
        self.bpm = bpm
        self.offset = offset
        self.beats_per_bar = beats_per_bar
        self.beat_times = list(beat_times) if beat_times else None
        self.first_beat_index = first_beat_index

    @property
    def beat_seconds(self) -> float:
        return 60.0 / self.bpm

    @property
    def is_warped(self) -> bool:
        return self.beat_times is not None and len(self.beat_times) >= 2

    # --- linear <-> warped mapping -------------------------------------
    def beat_of(self, time: float) -> float:
        if self.is_warped:
            import numpy as np

            beats = np.arange(len(self.beat_times)) + self.first_beat_index
            return float(np.interp(time, self.beat_times, beats)) if (
                self.beat_times[0] <= time <= self.beat_times[-1]
            ) else self._beat_of_linear_edge(time)
        return (time - self.offset) / self.beat_seconds

    def _beat_of_linear_edge(self, time: float) -> float:
        # extrapolate past the first/last click with the average tempo
        if time < self.beat_times[0]:
            return self.first_beat_index + (time - self.beat_times[0]) / self.beat_seconds
        return (
            self.first_beat_index
            + len(self.beat_times)
            - 1
            + (time - self.beat_times[-1]) / self.beat_seconds
        )

    def time_of(self, beat: float) -> float:
        if self.is_warped:
            import numpy as np

            beats = np.arange(len(self.beat_times)) + self.first_beat_index
            if beats[0] <= beat <= beats[-1]:
                return float(np.interp(beat, beats, self.beat_times))
            if beat < beats[0]:
                return self.beat_times[0] + (beat - beats[0]) * self.beat_seconds
            return self.beat_times[-1] + (beat - beats[-1]) * self.beat_seconds
        return self.offset + beat * self.beat_seconds

    def snap(self, time: float, subdiv: int = 4) -> float:
        """Snap to the nearest 1/subdiv beat position of the (warped) grid."""
        beat = self.beat_of(time)
        snapped_beat = round(beat * subdiv) / subdiv
        return round(self.time_of(snapped_beat), 4)

    def is_strong(self, time: float, tolerance_beats: float = 0.08) -> bool:
        beat = self.beat_of(time)
        return abs(beat - round(beat)) < tolerance_beats


def grid_from_metronome(path: str, nominal_bpm: float | None = None, beats_per_bar: int = 4) -> Grid:
    """Fit a warped Grid to metronome clicks.

    Clicks are assigned integer beat indices (tolerating missed clicks), the
    average tempo comes from a least-squares fit, and the full per-beat time
    map is rebuilt with gaps interpolated. Downbeats are inferred from the
    click accent pattern when one exists.
    """
    import numpy as np

    from .compare import extract_onsets

    onsets = extract_onsets(path, delta=0.1)
    times = np.array([o.time for o in onsets])
    strengths = np.array([o.strength for o in onsets])
    if len(times) < 8:
        if nominal_bpm is None:
            raise ValueError(f"Too few metronome clicks in {path} and no nominal BPM given")
        return Grid(bpm=nominal_bpm, offset=0.0, beats_per_bar=beats_per_bar)

    intervals = np.diff(times)
    beat = float(np.median(intervals))
    if nominal_bpm:
        # metronome may click on half/quarter beats; pick the multiple closest to nominal
        nominal_beat = 60.0 / nominal_bpm
        for factor in (0.25, 0.5, 1.0, 2.0, 4.0):
            if abs(beat * factor - nominal_beat) < 0.25 * nominal_beat:
                beat = beat * factor
                break

    # cumulative index assignment tolerant of missed/extra clicks AND wander:
    # each interval advances by its own rounded beat count (>=1)
    steps = np.maximum(1, np.round(intervals / beat)).astype(int)
    indices = np.concatenate([[0], np.cumsum(steps)])

    a = np.vstack([indices, np.ones_like(indices)]).T
    (beat_fit, offset_fit), *_ = np.linalg.lstsq(a, times, rcond=None)
    bpm = 60.0 / float(beat_fit)

    # full warp map: one time per integer beat, gaps filled by interpolation
    full = np.arange(indices[-1] + 1)
    beat_times = np.interp(full, indices, times)

    # downbeat: find the accent phase if clicks alternate strong/weak
    first_beat_index = 0
    phases = indices % beats_per_bar
    means = [float(strengths[phases == p].mean()) if np.any(phases == p) else 0.0 for p in range(beats_per_bar)]
    best = int(np.argmax(means))
    if means[best] > 1.15 * (sum(means) - means[best]) / max(1, beats_per_bar - 1):
        # shift beat numbering so downbeats fall on multiples of beats_per_bar
        first_beat_index = -best

    return Grid(
        bpm=round(bpm, 3),
        offset=round(float(offset_fit), 4),
        beats_per_bar=beats_per_bar,
        beat_times=[round(float(t), 5) for t in beat_times],
        first_beat_index=first_beat_index,
    )
