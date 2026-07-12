"""Align stem-derived MIDI to a straight musical bar grid.

The normal Sunofriend output deliberately follows source seconds so that it
matches the original audio in GarageBand.  That is the right contract for
fortifying one recording, but two independently performed songs carry two
different tempo-wander shapes.  This module uses each song's metronome stem as
a warp map, then writes note positions onto one exact target-BPM grid.

The aligned copy is intentionally note-centric: track names, channels, initial
programs, note-on velocities and within-beat placement survive. It rebuilds at
480 PPQ and discards bank/program changes after initialization, controllers,
sustain, SysEx, pitch bend, aftertouch, release velocity, key/chord metadata,
lyrics, markers and later time-signature changes; overlapping same-pitch notes
may be normalized for safe playback. With pitch offsets removed it assumes the
receiving instrument is tuned to A=440; MIDI itself cannot enforce that tuning.
This makes the copy useful for creative experiments, not archival round trips.
Use :mod:`sunofriend.midi_transform` when byte-preserving groove retiming is
required instead.
"""

from __future__ import annotations

import math
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .beatgrid import Grid, grid_from_metronome
from .clip import MidiClip, read_midi_clips
from .midi import MidiTrack, write_midi_file
from .midi_tempo import MIDI_SUFFIXES, SOURCE_BPM_TOLERANCE
from .models import NoteEvent


@dataclass(frozen=True)
class MidiAlignmentChange:
    """Auditable description of one grid-aligned MIDI file."""

    source_bpm: float
    target_bpm: float
    detected_grid_bpm: float
    semitones: int
    count_in_beats: float
    source_downbeat_beat: int
    track_count: int
    note_count: int
    first_note_beat: float | None
    last_note_beat: float | None
    pitch_low: int | None
    pitch_high: int | None
    drum_notes_preserved: int
    note_only_rebuild: bool = True
    assumes_receiver_a_hz: float = 440.0


@dataclass(frozen=True)
class MidiAlignmentFileResult:
    input_path: Path
    output_path: Path
    change: MidiAlignmentChange

    def to_dict(self) -> dict:
        result = asdict(self.change)
        result["input"] = str(self.input_path)
        result["output"] = str(self.output_path)
        return result


def align_midi_path(
    input_path: str | Path,
    *,
    metronome_path: str | Path | None = None,
    source_bpm: float,
    target_bpm: float,
    semitones: int = 0,
    count_in_bars: float = 1.0,
    beats_per_bar: int = 4,
    source_downbeat_beat: int = 0,
    output_path: str | Path | None = None,
    overwrite: bool = False,
    grid: Grid | None = None,
) -> list[MidiAlignmentFileResult]:
    """Map one MIDI file or a directory onto the metronome's exact bar grid.

    ``source_downbeat_beat`` identifies the detected grid beat that is the
    first real bar downbeat; it can differ from zero when click extraction
    begins on a pickup. ``count_in_bars`` moves that downbeat later in the
    output. One bar is a useful default because it preserves pickup notes and
    places the first downbeat at the start of bar two.
    A precomputed ``grid`` can be supplied by tests or programmatic callers;
    command-line use supplies ``metronome_path`` instead.
    """

    source = Path(input_path)
    source_tempo = _positive_number(source_bpm, "source_bpm")
    target_tempo = _positive_number(target_bpm, "target_bpm", require_encodable=True)
    shift = _integer(semitones, "semitones")
    if isinstance(beats_per_bar, bool) or int(beats_per_bar) != beats_per_bar:
        raise ValueError("beats_per_bar must be the integer 4")
    beats_per_bar = int(beats_per_bar)
    if beats_per_bar != 4:
        raise ValueError(
            "only 4 beats per bar are currently supported because the output MIDI "
            "declares a 4/4 time signature"
        )
    count_in_bars = float(count_in_bars)
    if not math.isfinite(count_in_bars) or count_in_bars < 0:
        raise ValueError("count_in_bars must be a finite non-negative number")
    count_in_beats = count_in_bars * beats_per_bar
    source_downbeat = _integer(source_downbeat_beat, "source_downbeat_beat")

    if grid is None:
        if metronome_path is None:
            raise ValueError("metronome_path is required when grid is not supplied")
        metronome = Path(metronome_path)
        if not metronome.is_file():
            raise ValueError(f"metronome does not exist: {metronome}")
        grid = grid_from_metronome(
            str(metronome), nominal_bpm=source_tempo, beats_per_bar=beats_per_bar
        )
    if not grid.is_warped:
        raise ValueError("bar alignment requires a metronome with a detected warped grid")
    if int(grid.beats_per_bar) != beats_per_bar:
        raise ValueError(
            "detected grid meter does not match the supported 4/4 output contract"
        )

    pairs, output_root = _input_output_pairs(source, output_path, target_tempo)
    output_root_resolved = output_root.resolve()
    resolved_outputs: set[Path] = set()
    for input_file, output_file in pairs:
        _validate_destination(input_file, output_file, overwrite=overwrite)
        resolved_output = output_file.resolve()
        if resolved_output in resolved_outputs:
            raise ValueError(f"multiple inputs resolve to the same output: {output_file}")
        resolved_outputs.add(resolved_output)
        if source.is_dir() and not _path_is_within(
            resolved_output, output_root_resolved
        ):
            raise ValueError(
                f"output path escapes the selected output directory: {output_file}"
            )
        _validate_output_parents(output_file.parent, stop=output_root)

    prepared: list[tuple[Path, Path, list[MidiTrack], MidiAlignmentChange]] = []
    for input_file, output_file in pairs:
        clips = read_midi_clips(input_file)
        if not clips:
            raise ValueError(f"no notes found in MIDI file: {input_file}")
        detected_tempos = {round(clip.bpm, 9) for clip in clips}
        if any(
            abs(detected - source_tempo) > SOURCE_BPM_TOLERANCE
            for detected in detected_tempos
        ):
            values = ", ".join(f"{value:.6g}" for value in sorted(detected_tempos))
            raise ValueError(
                f"embedded source tempo for {input_file} is {values} BPM, not "
                f"the requested {source_tempo:.6g} BPM"
            )
        tracks, change = _aligned_tracks(
            clips,
            grid=grid,
            source_bpm=source_tempo,
            target_bpm=target_tempo,
            semitones=shift,
            count_in_beats=count_in_beats,
            source_downbeat_beat=source_downbeat,
        )
        prepared.append((input_file, output_file, tracks, change))

    # Create every output parent before publishing the first MIDI, so a blocked
    # late path cannot leave an earlier file behind.
    for parent in sorted(
        {output_file.parent for _, output_file, _, _ in prepared},
        key=lambda path: (len(path.parts), str(path)),
    ):
        parent.mkdir(parents=True, exist_ok=True)

    # Render every temporary file before publishing the first destination. A
    # late serialization/disk-write failure therefore leaves no partial batch;
    # final replacements remain individually atomic.
    results: list[MidiAlignmentFileResult] = []
    staged: list[
        tuple[Path, Path, Path, MidiAlignmentChange]
    ] = []
    try:
        for input_file, output_file, tracks, change in prepared:
            temporary = output_file.with_name(
                f".{output_file.name}.{uuid.uuid4().hex}.tmp"
            )
            staged.append((input_file, output_file, temporary, change))
            write_midi_file(temporary, tracks, bpm=target_tempo)
        for input_file, output_file, temporary, change in staged:
            os.replace(temporary, output_file)
            results.append(
                MidiAlignmentFileResult(input_file, output_file, change)
            )
    finally:
        for _, _, temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return results


def _aligned_tracks(
    clips: tuple[MidiClip, ...],
    *,
    grid: Grid,
    source_bpm: float,
    target_bpm: float,
    semitones: int,
    count_in_beats: float,
    source_downbeat_beat: int,
) -> tuple[list[MidiTrack], MidiAlignmentChange]:
    tracks: list[MidiTrack] = []
    output_notes: list[NoteEvent] = []
    drum_notes = 0
    first_beat: float | None = None
    last_beat: float | None = None
    for clip in clips:
        notes: list[NoteEvent] = []
        # MIDI channel 10 (zero-based 9) is the portable GM percussion
        # contract. A melodic channel is still pitched even if its title says
        # "drums".
        is_drums = clip.instrument.channel == 9
        for note in clip.notes:
            start_beat = (
                grid.beat_of(note.source_start_seconds)
                - source_downbeat_beat
                + count_in_beats
            )
            end_beat = (
                grid.beat_of(note.source_end_seconds)
                - source_downbeat_beat
                + count_in_beats
            )
            if start_beat < -1e-9:
                needed = -start_beat / grid.beats_per_bar
                raise ValueError(
                    "a pickup note would occur before MIDI beat zero; increase "
                    f"--count-in-bars by at least {needed:.3f}"
                )
            start_beat = max(0.0, start_beat)
            end_beat = max(start_beat + 1.0 / 480.0, end_beat)
            pitch = note.pitch if is_drums else note.pitch + semitones
            if not 0 <= pitch <= 127:
                raise ValueError(
                    f"transposition moves MIDI note {note.pitch} outside 0..127 "
                    f"in track {clip.title!r}"
                )
            mapped = NoteEvent(
                start=start_beat * 60.0 / target_bpm,
                end=end_beat * 60.0 / target_bpm,
                pitch=pitch,
                velocity=note.velocity,
            )
            notes.append(mapped)
            output_notes.append(mapped)
            if is_drums:
                drum_notes += 1
            first_beat = start_beat if first_beat is None else min(first_beat, start_beat)
            last_beat = end_beat if last_beat is None else max(last_beat, end_beat)
        tracks.append(
            MidiTrack(
                clip.title,
                clip.instrument.channel,
                clip.instrument.program,
                notes,
            )
        )

    pitches = [note.pitch for note in output_notes]
    change = MidiAlignmentChange(
        source_bpm=source_bpm,
        target_bpm=target_bpm,
        detected_grid_bpm=float(grid.bpm),
        semitones=semitones,
        count_in_beats=count_in_beats,
        source_downbeat_beat=source_downbeat_beat,
        track_count=len(tracks),
        note_count=len(output_notes),
        first_note_beat=None if first_beat is None else round(first_beat, 6),
        last_note_beat=None if last_beat is None else round(last_beat, 6),
        pitch_low=min(pitches, default=None),
        pitch_high=max(pitches, default=None),
        drum_notes_preserved=drum_notes,
    )
    return tracks, change


def _input_output_pairs(
    source: Path, output_path: str | Path | None, target_bpm: float
) -> tuple[list[tuple[Path, Path]], Path]:
    if not source.exists():
        raise ValueError(f"input does not exist: {source}")
    token = f"{target_bpm:.6f}".rstrip("0").rstrip(".")
    if source.is_file():
        if source.suffix.lower() not in MIDI_SUFFIXES:
            raise ValueError("file input must end in .mid or .midi")
        output = (
            Path(output_path)
            if output_path is not None
            else source.with_name(f"{source.stem}-bar-aligned-{token}bpm{source.suffix}")
        )
        if output.exists() and output.is_dir():
            raise ValueError("a file input requires a MIDI file output path")
        return [(source, output)], output.parent
    if not source.is_dir():
        raise ValueError(f"input must be a MIDI file or directory: {source}")
    default_source = source.resolve() if source.name in {"", ".", ".."} else source
    output = (
        Path(output_path)
        if output_path is not None
        else default_source.with_name(
            f"{default_source.name}-bar-aligned-{token}bpm"
        )
    )
    source_resolved = source.resolve()
    output_resolved = output.resolve()
    if output_resolved == source_resolved or source_resolved in output_resolved.parents:
        raise ValueError("output directory must not be the input directory or inside it")
    inputs = sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() in MIDI_SUFFIXES
        ),
        key=lambda path: str(path.relative_to(source)).casefold(),
    )
    if not inputs:
        raise ValueError(f"no .mid or .midi files found under: {source}")
    return [(path, output / path.relative_to(source)) for path in inputs], output


def _validate_destination(input_file: Path, output_file: Path, *, overwrite: bool) -> None:
    if input_file.resolve() == output_file.resolve():
        raise ValueError(f"input and output must be different: {input_file}")
    if output_file.is_symlink():
        raise ValueError(f"output must not be a symbolic link: {output_file}")
    if output_file.exists() and output_file.is_dir():
        raise ValueError(f"output MIDI path is a directory: {output_file}")
    if output_file.exists() and not overwrite:
        raise ValueError(
            f"output already exists: {output_file} (use --overwrite to replace it)"
        )


def _path_is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _validate_output_parents(parent: Path, *, stop: Path) -> None:
    if stop != parent and stop not in parent.parents:
        raise ValueError(f"output path is not under the selected output: {parent}")
    current = parent
    while True:
        if current.is_symlink():
            raise ValueError(f"output parent must not be a symbolic link: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"output parent is not a directory: {current}")
        if current == stop:
            break
        current = current.parent


def _positive_number(
    value: float, label: str, *, require_encodable: bool = False
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number greater than zero")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number greater than zero") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be a finite number greater than zero")
    if require_encodable:
        microseconds = int(round(60_000_000.0 / result))
        if not 1 <= microseconds <= 0xFFFFFF:
            raise ValueError(
                f"{label} {result:.6g} cannot be represented by a three-byte "
                "MIDI tempo event"
            )
    return result


def _integer(value: int, label: str) -> int:
    if isinstance(value, bool) or int(value) != value:
        raise ValueError(f"{label} must be an integer")
    return int(value)


__all__ = [
    "MidiAlignmentChange",
    "MidiAlignmentFileResult",
    "align_midi_path",
]
