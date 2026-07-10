"""Iterative listen -> render -> compare -> adjust refinement loop.

Flow per stem:
  1. Seed: transcribe the stem (drums: onsets; pitched: basic-pitch).
  2. Render candidate MIDI through the FluidSynth GM proxy.
  3. Compare rendered audio vs original stem in feature space.
  4. Apply edit operations (add / remove / shift / re-velocity notes).
  5. Repeat until the score plateaus or max_iterations is reached.

The final .mid (best-scoring iteration) is what goes into GarageBand.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from . import compare
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .render import render_midi_to_wav

DRUM_KINDS = {"kick", "snare", "hat", "cymbals", "toms", "other_kit"}
PITCHED_KINDS = {"keys", "synth", "bass", "piano", "lead", "pads"}

_GM_PROGRAM = {"keys": 0, "piano": 0, "synth": 81, "lead": 81, "pads": 89, "bass": 38}


@dataclass
class IterationRecord:
    iteration: int
    score: float
    note_count: int
    detail: dict


@dataclass
class RefineResult:
    notes: list[NoteEvent]
    score: float
    history: list[IterationRecord]
    midi_path: Path | None = None


def refine_stem(
    stem_path: str | Path,
    kind: str,
    bpm: float,
    out_dir: str | Path,
    max_iterations: int = 30,
    plateau_epsilon: float = 0.002,
    plateau_patience: int = 3,
    keep_workdir: bool = False,
    chords_pdf: str | Path | None = None,
    key: str | None = None,
    metronome: str | Path | None = None,
    align_audio: str | Path | None = None,
    output_bpm: float | None = None,
) -> RefineResult:
    stem_path = str(stem_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    is_drum = kind in DRUM_KINDS

    if is_drum:
        from .transcribe_drums import transcribe_drum_stem

        notes = transcribe_drum_stem(stem_path, kind)
        ref_onsets = compare.extract_onsets(stem_path)
    else:
        notes = _seed_pitched(stem_path, kind, bpm, chords_pdf, key, metronome, align_audio)
        ref_onsets = compare.extract_onsets(stem_path, delta=0.12)
        ref_chroma = compare.chroma_matrix(stem_path)

    workdir = Path(tempfile.mkdtemp(prefix=f"sunofriend_{kind}_"))
    history: list[IterationRecord] = []
    best_notes, best_score = list(notes), -1.0
    stale = 0

    for iteration in range(max_iterations):
        midi_path = workdir / f"iter_{iteration:03d}.mid"
        wav_path = workdir / f"iter_{iteration:03d}.wav"
        _write_candidate(midi_path, notes, kind, bpm)
        render_midi_to_wav(midi_path, wav_path)

        if is_drum:
            rendered = compare.extract_onsets(str(wav_path))
            diff = compare.diff_drums(ref_onsets, rendered)
            score, detail = diff.score, {
                "f_measure": round(diff.f_measure, 4),
                "missed": len(diff.missed),
                "extra": len(diff.extra),
                "mean_abs_offset_ms": round(diff.mean_abs_offset * 1000, 1),
            }
        else:
            diff = compare.diff_pitched(
                stem_path, str(wav_path), notes, ref_chroma=ref_chroma, ref_onsets=ref_onsets
            )
            score, detail = diff.score, {
                "chroma_similarity": round(diff.chroma_similarity, 4),
                "onset_f_measure": round(diff.onset_f_measure, 4),
                "spurious": len(diff.spurious_notes),
            }

        history.append(IterationRecord(iteration, round(score, 4), len(notes), detail))

        if score > best_score + plateau_epsilon:
            best_notes, best_score, stale = list(notes), score, 0
        else:
            stale += 1
            if stale >= plateau_patience:
                break

        notes = _apply_edits_drums(notes, diff, kind) if is_drum else _apply_edits_pitched(notes, diff)
        if not notes:
            break

    final_midi = out_dir / f"{kind}_listened.mid"
    # Written at output_bpm (an exact DAW-enterable tempo) when provided: note
    # times are absolute seconds, so alignment with the stems is preserved.
    _write_candidate(final_midi, best_notes, kind, output_bpm or bpm)
    (out_dir / f"{kind}_iterations.json").write_text(
        json.dumps([r.__dict__ for r in history], indent=2), encoding="utf-8"
    )
    if not keep_workdir:
        for file in workdir.glob("*"):
            file.unlink(missing_ok=True)
        workdir.rmdir()
    return RefineResult(notes=best_notes, score=best_score, history=history, midi_path=final_midi)


def _seed_pitched(
    stem_path: str,
    kind: str,
    bpm: float,
    chords_pdf: str | Path | None,
    key: str | None,
    metronome: str | Path | None = None,
    align_audio: str | Path | None = None,
) -> list[NoteEvent]:
    """Pitched seed: theory-constrained 'imagine' mode when a chord chart is
    provided and the kind benefits from it; plain transcription otherwise."""
    if chords_pdf and kind in {"bass", "lead", "synth", "pads"}:
        import soundfile

        from .beatgrid import Grid, grid_from_metronome
        from .chords import extract_chords_from_moises_pdf, make_chord_segments
        from .harmony import align_chords_to_audio
        from .imagine import imagine_bass, imagine_lead, imagine_pads

        chart = extract_chords_from_moises_pdf(chords_pdf)
        duration = soundfile.info(stem_path).duration
        grid = (
            grid_from_metronome(str(metronome), nominal_bpm=bpm)
            if metronome
            else Grid(bpm=bpm)
        )
        try:
            segments = align_chords_to_audio(
                chart.chords, str(align_audio or stem_path), grid, duration
            )
        except Exception:
            segments = make_chord_segments(chart.chords, duration_seconds=duration, bpm=grid.bpm)
        key_name = key or chart.key
        if kind == "bass":
            return imagine_bass(stem_path, grid=grid, segments=segments, key_name=key_name)
        if kind == "pads":
            return imagine_pads(stem_path, grid=grid, segments=segments, key_name=key_name)
        return imagine_lead(stem_path, grid=grid, segments=segments, key_name=key_name)

    from .transcribe_pitched import transcribe_pitched_stem
    from .verify import verify_notes

    notes = transcribe_pitched_stem(stem_path, kind=kind)
    return verify_notes(stem_path, notes, threshold=0.10).kept


def _write_candidate(path: Path, notes: list[NoteEvent], kind: str, bpm: float) -> None:
    if kind in DRUM_KINDS:
        track = MidiTrack(name=f"{kind} candidate", channel=9, program=0, notes=notes)
    else:
        track = MidiTrack(
            name=f"{kind} candidate", channel=0, program=_GM_PROGRAM.get(kind, 0), notes=notes
        )
    write_midi_file(path, [track], bpm=bpm)


def _apply_edits_drums(notes: list[NoteEvent], diff: compare.DrumDiff, kind: str, tol: float = 0.035) -> list[NoteEvent]:
    edited = list(notes)

    # 1. Missed reference onsets: bump velocity if a note exists there (render
    #    was too quiet to detect), otherwise add a new hit.
    for onset in diff.missed:
        near = [i for i, n in enumerate(edited) if abs(n.start - onset.time) <= tol]
        if near:
            i = near[0]
            edited[i] = replace(edited[i], velocity=min(127, edited[i].velocity + 18))
        else:
            template = edited[0] if edited else NoteEvent(0.0, 0.08, 38, 90)
            duration = template.end - template.start
            velocity = max(40, min(127, int(round(onset.strength * 127))))
            start = max(0.0, onset.time)
            edited.append(NoteEvent(start, start + duration, template.pitch, velocity))

    # 2. Extra rendered onsets: remove the nearest candidate note.
    for time in diff.extra:
        near = sorted(
            ((abs(n.start - time), i) for i, n in enumerate(edited)), key=lambda p: p[0]
        )
        if near and near[0][0] <= tol * 2:
            edited.pop(near[0][1])

    # 3. Matched but mistimed: shift toward the reference time.
    for ref_time, cand_time in diff.matched:
        offset = ref_time - cand_time
        if abs(offset) > 0.008:
            near = [i for i, n in enumerate(edited) if abs(n.start - cand_time) <= tol]
            if near:
                i = near[0]
                n = edited[i]
                new_start = max(0.0, n.start + offset)
                edited[i] = replace(n, start=new_start, end=new_start + (n.end - n.start))

    return sorted(edited, key=lambda n: n.start)


def _apply_edits_pitched(notes: list[NoteEvent], diff: compare.PitchedDiff) -> list[NoteEvent]:
    # Remove notes whose pitch class has no support in the stem's chroma.
    spurious = set(diff.spurious_notes)
    return [n for i, n in enumerate(notes) if i not in spurious]
