"""Pitched stem (keys / synth / bass) -> MIDI notes.

Primary engine: Spotify basic-pitch (polyphonic, ML). Fallback for monophonic
bass: librosa pyin f0 tracking. Output is plain NoteEvent lists in seconds.
"""
from __future__ import annotations

import numpy as np

from .models import NoteEvent

# Sensible per-kind ranges (Hz) to stop octave errors / rumble artifacts.
_KIND_FREQS = {
    "bass": (30.0, 500.0),
    "keys": (60.0, 2500.0),
    "synth": (40.0, 3000.0),
}


def transcribe_pitched_stem(
    path: str,
    kind: str = "keys",
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_ms: float = 60.0,
) -> list[NoteEvent]:
    try:
        return _basic_pitch_notes(path, kind, onset_threshold, frame_threshold, min_note_ms)
    except ImportError:
        if kind == "bass":
            return _pyin_notes(path)
        raise


def _basic_pitch_notes(
    path: str, kind: str, onset_threshold: float, frame_threshold: float, min_note_ms: float
) -> list[NoteEvent]:
    from basic_pitch.inference import predict

    fmin, fmax = _KIND_FREQS.get(kind, (30.0, 3000.0))
    _, _, note_events = predict(
        path,
        model_or_model_path=_model_path(),
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=min_note_ms,
        minimum_frequency=fmin,
        maximum_frequency=fmax,
        melodia_trick=True,
        multiple_pitch_bends=False,
    )
    notes = [
        NoteEvent(
            start=float(start),
            end=float(end),
            pitch=int(pitch),
            velocity=max(1, min(127, int(round(float(amplitude) * 127)))),
        )
        for start, end, pitch, amplitude, *_ in note_events
    ]
    notes.sort(key=lambda n: (n.start, n.pitch))
    notes = _drop_octave_ghosts(notes)
    notes = _merge_split_notes(notes)
    if kind == "bass":
        notes = _keep_lowest_voice(notes)
    return notes


def _merge_split_notes(notes: list[NoteEvent], max_gap: float = 0.06, fragment_len: float = 0.25) -> list[NoteEvent]:
    """Join same-pitch notes separated by a tiny gap (transcription splits).

    Only merges when one side is a short fragment — a re-struck sustained note
    (e.g. a common tone across two chords) is a real musical event, not a split.
    """
    merged: list[NoteEvent] = []
    for note in sorted(notes, key=lambda n: (n.pitch, n.start)):
        is_fragment = (note.end - note.start) < fragment_len or (
            merged and merged[-1].pitch == note.pitch and (merged[-1].end - merged[-1].start) < fragment_len
        )
        if (
            merged
            and merged[-1].pitch == note.pitch
            and note.start - merged[-1].end <= max_gap
            and is_fragment
        ):
            prev = merged.pop()
            merged.append(
                NoteEvent(prev.start, max(prev.end, note.end), prev.pitch, max(prev.velocity, note.velocity))
            )
        else:
            merged.append(note)
    return sorted(merged, key=lambda n: (n.start, n.pitch))


def _drop_octave_ghosts(notes: list[NoteEvent], ratio: float = 0.72) -> list[NoteEvent]:
    """Drop notes that are octave duplicates of a much louder simultaneous note.

    Sub-octave and first-harmonic ghosts are the dominant basic-pitch error on
    synth/keys stems. Genuine octave doublings survive because their levels
    are comparable (velocity ratio above `ratio`).
    """
    drop: set[int] = set()
    for i, a in enumerate(notes):
        for j, b in enumerate(notes):
            if i == j or j in drop:
                continue
            if abs(a.pitch - b.pitch) not in (12, 24):
                continue
            overlap = min(a.end, b.end) - max(a.start, b.start)
            if overlap < 0.6 * (a.end - a.start):
                continue
            if a.velocity < b.velocity * ratio:
                drop.add(i)
                break
    return [n for i, n in enumerate(notes) if i not in drop]


def _model_path():
    """Prefer the ONNX model (loads everywhere); fall back to the default."""
    from basic_pitch import ICASSP_2022_MODEL_PATH

    try:
        import onnxruntime  # noqa: F401
        from basic_pitch import build_icassp_2022_model_path, FilenameSuffix

        return build_icassp_2022_model_path(FilenameSuffix.onnx)
    except Exception:
        return ICASSP_2022_MODEL_PATH


def _keep_lowest_voice(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Bass stems are monophonic in practice: drop overlapping higher notes."""
    kept: list[NoteEvent] = []
    for note in notes:
        overlapping = [k for k in kept if k.end > note.start + 0.02]
        if overlapping and all(k.pitch <= note.pitch for k in overlapping):
            continue
        kept = [k for k in kept if not (k.start >= note.start - 0.02 and k.pitch > note.pitch and k.end > note.start)]
        kept.append(note)
    return sorted(kept, key=lambda n: n.start)


def _pyin_notes(path: str, sr: int = 22050, hop: int = 256) -> list[NoteEvent]:
    """Monophonic fallback (no ML): pyin f0 track segmented into notes."""
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True)
    if y.size == 0:
        return []
    f0, voiced, _ = librosa.pyin(
        y, fmin=30.0, fmax=500.0, sr=sr, hop_length=hop, fill_na=np.nan
    )
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.times_like(f0, sr=sr, hop_length=hop)

    notes: list[NoteEvent] = []
    current_pitch: int | None = None
    start_time = 0.0
    strengths: list[float] = []

    def flush(end_time: float) -> None:
        nonlocal current_pitch, strengths
        if current_pitch is not None and end_time - start_time >= 0.06:
            peak = max(strengths) if strengths else 0.1
            vel = max(30, min(127, int(round(peak / (np.max(rms) + 1e-9) * 127))))
            notes.append(NoteEvent(start=start_time, end=end_time, pitch=current_pitch, velocity=vel))
        current_pitch = None
        strengths = []

    for i, t in enumerate(times):
        pitch = None
        if voiced is not None and i < len(voiced) and voiced[i] and not np.isnan(f0[i]):
            pitch = int(round(librosa.hz_to_midi(float(f0[i]))))
        if pitch != current_pitch:
            flush(t)
            if pitch is not None:
                current_pitch = pitch
                start_time = t
        if pitch is not None and i < len(rms):
            strengths.append(float(rms[i]))
    flush(float(times[-1]) if len(times) else 0.0)
    return notes
