"""Feature-space comparison between an original stem and a rendered candidate.

Raw waveforms are never compared directly (GM SoundFont timbre != stem timbre).
Instead:
  drums  -> onset lists (time + strength), matched within a tolerance window
  pitched-> chroma similarity + onset match

The diff (missed / extra / mistimed) is what drives the refinement loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SR = 22050
HOP = 128


@dataclass(frozen=True)
class Onset:
    time: float
    strength: float


@dataclass
class DrumDiff:
    matched: list[tuple[float, float]] = field(default_factory=list)  # (ref_time, cand_time)
    missed: list[Onset] = field(default_factory=list)                 # in ref, not in render
    extra: list[float] = field(default_factory=list)                  # in render, not in ref
    f_measure: float = 0.0
    mean_abs_offset: float = 0.0

    @property
    def score(self) -> float:
        timing_penalty = min(self.mean_abs_offset / 0.05, 1.0) * 0.15
        return max(0.0, self.f_measure - timing_penalty)


@dataclass
class PitchedDiff:
    chroma_similarity: float = 0.0
    onset_f_measure: float = 0.0
    spurious_notes: list[int] = field(default_factory=list)  # indices into candidate notes

    @property
    def score(self) -> float:
        return 0.7 * self.chroma_similarity + 0.3 * self.onset_f_measure


def extract_onsets(path: str, delta: float = 0.18) -> list[Onset]:
    import librosa

    y, sr = librosa.load(path, sr=SR, mono=True)
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-4:
        return []
    y = y / float(np.max(np.abs(y)))
    pad = int(0.05 * sr)
    y = np.pad(y, (pad, 0))
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    from .transcribe_drums import _clip_envelope_spikes

    env = _clip_envelope_spikes(env)
    frames = librosa.onset.onset_detect(
        onset_envelope=env, sr=sr, hop_length=HOP, backtrack=False,
        delta=delta, pre_max=6, post_max=6, pre_avg=12, post_avg=12, wait=4,
    )
    times = np.maximum(librosa.frames_to_time(frames, sr=sr, hop_length=HOP) - (pad / sr), 0.0)
    peak_env = float(np.max(env)) if env.size else 1.0
    return [Onset(time=float(t), strength=float(env[f]) / (peak_env + 1e-9)) for t, f in zip(times, frames)]


def diff_drums(ref: list[Onset], rendered: list[Onset], tolerance: float = 0.035) -> DrumDiff:
    diff = DrumDiff()
    used = [False] * len(rendered)
    for r in ref:
        best_j, best_d = -1, tolerance
        for j, c in enumerate(rendered):
            if used[j]:
                continue
            d = abs(c.time - r.time)
            if d <= best_d:
                best_j, best_d = j, d
        if best_j >= 0:
            used[best_j] = True
            diff.matched.append((r.time, rendered[best_j].time))
        else:
            diff.missed.append(r)
    diff.extra = [c.time for j, c in enumerate(rendered) if not used[j]]

    tp = len(diff.matched)
    precision = tp / max(1, tp + len(diff.extra))
    recall = tp / max(1, tp + len(diff.missed))
    diff.f_measure = 0.0 if tp == 0 else 2 * precision * recall / (precision + recall)
    diff.mean_abs_offset = (
        float(np.mean([abs(a - b) for a, b in diff.matched])) if diff.matched else 0.0
    )
    return diff


def chroma_matrix(path: str) -> np.ndarray:
    import librosa

    y, sr = librosa.load(path, sr=SR, mono=True)
    if y.size == 0:
        return np.zeros((12, 1))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    return chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)


def diff_pitched(
    ref_path: str,
    rendered_path: str,
    candidate_notes,
    tolerance: float = 0.05,
    ref_chroma: np.ndarray | None = None,
    ref_onsets: list[Onset] | None = None,
) -> PitchedDiff:
    if ref_chroma is None:
        ref_chroma = chroma_matrix(ref_path)
    cand_chroma = chroma_matrix(rendered_path)
    frames = min(ref_chroma.shape[1], cand_chroma.shape[1])
    similarity = float(
        np.mean(np.sum(ref_chroma[:, :frames] * cand_chroma[:, :frames], axis=0))
    ) if frames else 0.0

    if ref_onsets is None:
        ref_onsets = extract_onsets(ref_path, delta=0.12)
    cand_onsets = extract_onsets(rendered_path, delta=0.12)
    onset_f = diff_drums(ref_onsets, cand_onsets, tolerance=tolerance).f_measure

    spurious = _spurious_note_indices(ref_chroma, candidate_notes)
    return PitchedDiff(chroma_similarity=similarity, onset_f_measure=onset_f, spurious_notes=spurious)


def _spurious_note_indices(ref_chroma: np.ndarray, notes, frame_seconds: float = 512 / SR) -> list[int]:
    """Candidate notes whose pitch class has almost no energy in the stem while sounding."""
    spurious = []
    total_frames = ref_chroma.shape[1]
    for i, note in enumerate(notes):
        start_frame = int(note.start / frame_seconds)
        end_frame = min(total_frames, max(start_frame + 1, int(note.end / frame_seconds)))
        if start_frame >= total_frames:
            continue
        pc = note.pitch % 12
        energy = float(np.mean(ref_chroma[pc, start_frame:end_frame]))
        if energy < 0.08:
            spurious.append(i)
    return spurious
