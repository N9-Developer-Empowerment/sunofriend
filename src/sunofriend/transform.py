"""Non-destructive musical transforms for :class:`sunofriend.clip.MidiClip`."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Literal

from .chords import parse_chord_name
from .clip import (
    ChordEvent,
    ClipNote,
    KeySignature,
    MidiClip,
    TempoMap,
    TempoPoint,
    TransformRecipe,
    WarpPoint,
    normalize_note_name,
    note_name_for_pc,
    pitch_class,
)


MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)
_TRIAD_QUALITIES = {
    "major": ("major", "minor", "minor", "major", "major", "minor", "diminished"),
    "minor": ("minor", "diminished", "major", "minor", "minor", "major", "major"),
}
_CHORD_RE = re.compile(r"^([A-Ga-g])([#b]?)([^/]*?)(?:/([A-Ga-g])([#b]?))?$")


def transpose(
    clip: MidiClip,
    semitones: int,
    *,
    engine_version: str | None = None,
) -> MidiClip:
    """Transpose pitches and harmonic metadata by an exact semitone amount.

    MIDI channel 10 and clips marked as drums/percussion retain their pitches.
    This is important because a drum pitch names an instrument, not a note.
    """

    if isinstance(semitones, bool) or int(semitones) != semitones:
        raise ValueError("semitones must be an integer")
    semitones = int(semitones)
    if clip.instrument.is_drums:
        notes = clip.notes
    else:
        notes = tuple(replace(note, pitch=_checked_pitch(note.pitch + semitones)) for note in clip.notes)
    key = None
    if clip.key is not None:
        key = KeySignature(
            note_name_for_pc(clip.key.tonic_pc + semitones, "b" in clip.key.tonic),
            clip.key.mode,
        )
    chords = tuple(replace(chord, symbol=_transpose_chord(chord.symbol, semitones)) for chord in clip.chords)
    recipe = TransformRecipe.create("transpose", semitones=semitones, drum_pitches_preserved=clip.instrument.is_drums)
    return clip.child(
        recipe=recipe,
        notes=notes,
        key=key,
        chords=chords,
        engine_version=engine_version,
    )


def transpose_same_mode(
    clip: MidiClip,
    target_tonic: str,
    *,
    direction: Literal["nearest", "up", "down"] = "nearest",
    engine_version: str | None = None,
) -> MidiClip:
    """Move a keyed clip to another tonic without changing major/minor mode."""

    if clip.key is None:
        raise ValueError("Same-mode transposition requires a source key")
    target = normalize_note_name(target_tonic)
    raw = (pitch_class(target) - clip.key.tonic_pc) % 12
    if direction == "up":
        semitones = raw
    elif direction == "down":
        semitones = raw - 12 if raw else 0
    elif direction == "nearest":
        semitones = raw - 12 if raw > 6 else raw
    else:
        raise ValueError("direction must be 'nearest', 'up', or 'down'")
    result = transpose(clip, semitones, engine_version=engine_version)
    # Preserve the spelling the caller selected (for example, Bb rather than A#).
    recipe = TransformRecipe.create(
        "transpose_same_mode",
        source_key=str(clip.key),
        target_key=f"{target} {clip.key.mode}",
        semitones=semitones,
        direction=direction,
        drum_pitches_preserved=clip.instrument.is_drums,
    )
    chords = tuple(
        replace(
            chord,
            symbol=_transpose_chord(chord.symbol, semitones, prefer_flats="b" in target),
        )
        for chord in clip.chords
    )
    return replace(
        result,
        key=KeySignature(target, clip.key.mode),
        chords=chords,
        transform_recipe=recipe,
    )


def remap_mode(
    clip: MidiClip,
    target_mode: Literal["major", "minor"],
    *,
    target_tonic: str | None = None,
    chord_aware: bool = True,
    engine_version: str | None = None,
) -> MidiClip:
    """Map scale degrees and chord tones between major and natural minor.

    This is deliberately not a one-semitone blanket shift.  Notes keep their
    melodic scale degree, while simple diatonic chord qualities are rebuilt in
    the target mode (for example C major -> C minor and G major -> G minor).
    Borrowed/chromatic notes retain their chromatic relationship to the tonic.
    """

    if clip.key is None:
        raise ValueError("Mode remapping requires a source key")
    target_mode = str(target_mode).lower()
    if target_mode not in {"major", "minor"}:
        raise ValueError("target_mode must be 'major' or 'minor'")
    target_tonic = normalize_note_name(target_tonic or clip.key.tonic)
    target_key = KeySignature(target_tonic, target_mode)
    source_scale = _scale(clip.key.mode)
    target_scale = _scale(target_mode)
    mapped_chords = tuple(
        replace(
            chord,
            symbol=_remap_chord_symbol(
                chord.symbol,
                clip.key,
                target_key,
                source_scale,
                target_scale,
            ),
        )
        for chord in clip.chords
    )
    if clip.instrument.is_drums:
        notes = clip.notes
    else:
        notes = tuple(
            replace(
                note,
                pitch=_remap_note_pitch(
                    note,
                    clip,
                    mapped_chords,
                    target_key,
                    source_scale,
                    target_scale,
                    chord_aware,
                ),
            )
            for note in clip.notes
        )
    recipe = TransformRecipe.create(
        "remap_mode",
        source_key=str(clip.key),
        target_key=str(target_key),
        chord_aware=bool(chord_aware),
        drum_pitches_preserved=clip.instrument.is_drums,
    )
    return clip.child(
        recipe=recipe,
        key=target_key,
        chords=mapped_chords,
        notes=notes,
        engine_version=engine_version,
    )


def retime_bpm(
    clip: MidiClip,
    new_bpm: float,
    *,
    mode: Literal["musical", "stem_locked"] = "musical",
    engine_version: str | None = None,
) -> MidiClip:
    """Create a BPM variant with one of two explicit timing semantics.

    ``musical`` keeps bar/beat positions and changes elapsed time.  Tempo-warp
    shape and microtiming are proportionally scaled, so groove survives.

    ``stem_locked`` keeps every source second unchanged and moves the MIDI beat
    positions to compensate for the new DAW tempo.  It intentionally emits a
    straight tempo map because the absolute source positions are the authority.
    """

    new_bpm = float(new_bpm)
    if new_bpm <= 0:
        raise ValueError("new_bpm must be greater than zero")
    if mode not in {"musical", "stem_locked"}:
        raise ValueError("mode must be 'musical' or 'stem_locked'")
    ratio = new_bpm / clip.bpm

    if mode == "musical":
        tempo_map = TempoMap(
            tuple(TempoPoint(point.beat, point.bpm * ratio) for point in clip.tempo_map.tempo_points),
            tuple(
                WarpPoint(point.beat, point.source_second / ratio)
                for point in clip.tempo_map.warp_points
            ),
            clip.tempo_map.offset_seconds / ratio,
        )
        notes = tuple(_musically_retimed_note(note, tempo_map, ratio) for note in clip.notes)
        chords = tuple(_musically_retimed_chord(chord, tempo_map) for chord in clip.chords)
    else:
        tempo_map = TempoMap.constant(new_bpm)
        notes = tuple(_stem_locked_note(note, tempo_map) for note in clip.notes)
        chords = tuple(_stem_locked_chord(chord, clip.tempo_map, tempo_map) for chord in clip.chords)

    recipe = TransformRecipe.create(
        "retime_bpm",
        source_bpm=clip.bpm,
        target_bpm=new_bpm,
        timing_mode=mode,
    )
    # Export semantics must survive later key/instrument versions.  Keeping the
    # active contract in provenance means ``write_clip_midi(..., auto)`` does
    # not have to walk the library lineage to discover whether the last BPM
    # operation was musical or stem-locked.
    provenance_details = clip.provenance.details_dict
    provenance_details.update(
        {
            "timing_mode": mode,
            "garageband_bpm": new_bpm,
        }
    )
    return clip.child(
        recipe=recipe,
        tempo_map=tempo_map,
        notes=notes,
        chords=chords,
        provenance=replace(clip.provenance, details=provenance_details),
        engine_version=engine_version,
    )


def _musically_retimed_note(note: ClipNote, tempo_map: TempoMap, ratio: float) -> ClipNote:
    microtiming = note.microtiming_seconds / ratio
    end_microtiming = note.end_microtiming_seconds / ratio
    return replace(
        note,
        source_start_seconds=tempo_map.source_seconds_at(note.start_beat) + microtiming,
        source_end_seconds=tempo_map.source_seconds_at(note.end_beat) + end_microtiming,
        microtiming_seconds=microtiming,
        end_microtiming_seconds=end_microtiming,
    )


def _musically_retimed_chord(chord: ChordEvent, tempo_map: TempoMap) -> ChordEvent:
    return replace(
        chord,
        source_start_seconds=tempo_map.source_seconds_at(chord.start_beat),
        source_end_seconds=tempo_map.source_seconds_at(chord.end_beat),
    )


def _stem_locked_note(note: ClipNote, tempo_map: TempoMap) -> ClipNote:
    start = tempo_map.beat_at_musical_seconds(note.source_start_seconds)
    end = tempo_map.beat_at_musical_seconds(note.source_end_seconds)
    return replace(
        note,
        start_beat=start,
        duration_beats=max(1e-9, end - start),
        microtiming_seconds=0.0,
        end_microtiming_seconds=0.0,
    )


def _stem_locked_chord(chord: ChordEvent, old_map: TempoMap, new_map: TempoMap) -> ChordEvent:
    source_start = (
        chord.source_start_seconds
        if chord.source_start_seconds is not None
        else old_map.source_seconds_at(chord.start_beat)
    )
    source_end = (
        chord.source_end_seconds
        if chord.source_end_seconds is not None
        else old_map.source_seconds_at(chord.end_beat)
    )
    start = new_map.beat_at_musical_seconds(source_start)
    end = new_map.beat_at_musical_seconds(source_end)
    return replace(
        chord,
        start_beat=start,
        duration_beats=max(1e-9, end - start),
        source_start_seconds=source_start,
        source_end_seconds=source_end,
    )


def _remap_note_pitch(
    note: ClipNote,
    source_clip: MidiClip,
    target_chords: tuple[ChordEvent, ...],
    target_key: KeySignature,
    source_scale: tuple[int, ...],
    target_scale: tuple[int, ...],
    chord_aware: bool,
) -> int:
    source_key = source_clip.key
    assert source_key is not None
    source_pc = note.pitch % 12
    target_pc: int | None = None

    if chord_aware:
        source_chord = _chord_at(source_clip.chords, note.start_beat)
        target_chord = _chord_at(target_chords, note.start_beat)
        if source_chord is not None and target_chord is not None:
            source_pcs = parse_chord_name(source_chord.symbol) or []
            target_pcs = parse_chord_name(target_chord.symbol) or []
            if source_pc in source_pcs and target_pcs:
                chord_degree = source_pcs.index(source_pc)
                target_pc = target_pcs[min(chord_degree, len(target_pcs) - 1)]

    if target_pc is None:
        relative = (source_pc - source_key.tonic_pc) % 12
        if relative in source_scale:
            degree = source_scale.index(relative)
            target_pc = (target_key.tonic_pc + target_scale[degree]) % 12
        else:
            # A borrowed/chromatic note keeps its chromatic tonic relationship.
            target_pc = (target_key.tonic_pc + relative) % 12

    tonic_shift = _nearest_signed_interval(source_key.tonic_pc, target_key.tonic_pc)
    return _nearest_pitch(target_pc, note.pitch + tonic_shift)


def _remap_chord_symbol(
    symbol: str,
    source_key: KeySignature,
    target_key: KeySignature,
    source_scale: tuple[int, ...],
    target_scale: tuple[int, ...],
) -> str:
    match = _CHORD_RE.match(symbol.strip())
    if not match:
        return symbol
    root = normalize_note_name(match.group(1) + match.group(2))
    suffix = match.group(3) or ""
    bass = normalize_note_name(match.group(4) + match.group(5)) if match.group(4) else None
    relative = (pitch_class(root) - source_key.tonic_pc) % 12
    if relative in source_scale:
        degree = source_scale.index(relative)
        target_root_pc = (target_key.tonic_pc + target_scale[degree]) % 12
        if suffix.lower() in {"", "m", "min", "dim", "o", "°"}:
            quality = _TRIAD_QUALITIES[target_key.mode][degree]
            suffix = {"major": "", "minor": "m", "diminished": "dim"}[quality]
    else:
        target_root_pc = (target_key.tonic_pc + relative) % 12
    prefer_flats = "b" in target_key.tonic or "b" in root
    output = note_name_for_pc(target_root_pc, prefer_flats) + suffix
    if bass is not None:
        bass_relative = (pitch_class(bass) - source_key.tonic_pc) % 12
        if bass_relative in source_scale:
            bass_degree = source_scale.index(bass_relative)
            target_bass = target_key.tonic_pc + target_scale[bass_degree]
        else:
            target_bass = target_key.tonic_pc + bass_relative
        output += "/" + note_name_for_pc(target_bass, prefer_flats)
    return output


def _transpose_chord(
    symbol: str, semitones: int, prefer_flats: bool | None = None
) -> str:
    match = _CHORD_RE.match(symbol.strip())
    if not match:
        return symbol
    root = normalize_note_name(match.group(1) + match.group(2))
    root_prefer_flats = "b" in root if prefer_flats is None else prefer_flats
    result = note_name_for_pc(pitch_class(root) + semitones, root_prefer_flats) + (match.group(3) or "")
    if match.group(4):
        bass = normalize_note_name(match.group(4) + match.group(5))
        bass_prefer_flats = "b" in bass if prefer_flats is None else prefer_flats
        result += "/" + note_name_for_pc(pitch_class(bass) + semitones, bass_prefer_flats)
    return result


def _chord_at(chords: tuple[ChordEvent, ...], beat: float) -> ChordEvent | None:
    for chord in chords:
        if chord.start_beat <= beat < chord.end_beat:
            return chord
    return None


def _scale(mode: str) -> tuple[int, ...]:
    return MINOR_SCALE if mode == "minor" else MAJOR_SCALE


def _nearest_signed_interval(source_pc: int, target_pc: int) -> int:
    interval = (target_pc - source_pc) % 12
    return interval - 12 if interval > 6 else interval


def _nearest_pitch(pc: int, reference: int) -> int:
    candidates = [pitch for pitch in range(128) if pitch % 12 == pc % 12]
    return min(candidates, key=lambda pitch: (abs(pitch - reference), pitch))


def _checked_pitch(pitch: int) -> int:
    if not 0 <= pitch <= 127:
        raise ValueError(f"Transposition moves MIDI pitch outside 0..127: {pitch}")
    return pitch


# More explicit aliases for callers that prefer verb-noun names.
transpose_semitones = transpose
remap_major_minor = remap_mode


__all__ = [
    "MAJOR_SCALE",
    "MINOR_SCALE",
    "remap_major_minor",
    "remap_mode",
    "retime_bpm",
    "transpose",
    "transpose_same_mode",
    "transpose_semitones",
]
