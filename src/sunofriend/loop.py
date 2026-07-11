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
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from . import compare
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .note_safety import normalize_note_events
from .render import render_midi_to_wav

DRUM_KINDS = {"kick", "snare", "hat", "cymbals", "toms", "other_kit"}
PITCHED_KINDS = {"keys", "synth", "bass", "piano", "lead", "pads"}
THEORY_GENERATED_KINDS = {"bass", "lead", "synth", "pads"}

_GM_PROGRAM = {"keys": 7, "piano": 0, "synth": 81, "lead": 81, "pads": 89, "bass": 38}
_THEORY_CONTEXT_CACHE: dict[tuple, tuple] = {}


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
    variants: dict[str, list[NoteEvent]] = field(default_factory=dict)
    note_provenance: list[Any] = field(default_factory=list)
    variant_provenance: dict[str, list[Any]] = field(default_factory=dict)


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
    conversion_mode: str | None = None,
) -> RefineResult:
    from .conversion import validate_conversion_mode

    extended_conversion = conversion_mode is not None
    conversion_mode = validate_conversion_mode(conversion_mode or "repair")
    stem_path = str(stem_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    is_drum = kind in DRUM_KINDS
    theory_locked = bool(chords_pdf and kind in THEORY_GENERATED_KINDS)
    # Dense keyboard stems frequently contain several voices or instruments.
    # Generic pitch evidence cannot decide which role owns a proposed note, so
    # additions are quarantined into role-aware variants instead of silently
    # growing the principal track.  Existing notes can still receive
    # evidence-backed timing, duration, pitch and velocity repairs.
    allow_pitched_additions = False

    variants: dict[str, list[NoteEvent]] = {}
    note_provenance: list[Any] = []
    variant_provenance: dict[str, list[Any]] = {}

    if is_drum and extended_conversion:
        (
            notes,
            ref_onsets,
            variants,
            note_provenance,
            variant_provenance,
        ) = _seed_drums_v2(
            stem_path,
            kind,
            bpm=bpm,
            conversion_mode=conversion_mode,
            metronome=metronome,
        )
    elif is_drum:
        from .transcribe_drums import transcribe_drum_stem

        notes = transcribe_drum_stem(stem_path, kind)
        ref_onsets = compare.extract_onsets(stem_path)
    elif extended_conversion:
        (
            notes,
            variants,
            note_provenance,
            variant_provenance,
        ) = _seed_pitched_v2(
            stem_path,
            kind,
            bpm,
            chords_pdf,
            key,
            metronome,
            align_audio,
            conversion_mode,
        )
        ref_onsets = compare.extract_onsets(stem_path, delta=0.12)
        ref_chroma = compare.chroma_matrix(stem_path)
        pitched_reference = compare.analyze_pitched_reference(stem_path, kind, ref_onsets)
    else:
        notes = _seed_pitched(stem_path, kind, bpm, chords_pdf, key, metronome, align_audio)
        ref_onsets = compare.extract_onsets(stem_path, delta=0.12)
        ref_chroma = compare.chroma_matrix(stem_path)
        pitched_reference = compare.analyze_pitched_reference(stem_path, kind, ref_onsets)

    notes = normalize_note_events(notes)

    workdir = Path(tempfile.mkdtemp(prefix=f"sunofriend_{kind}_"))
    history: list[IterationRecord] = []
    best_notes, best_score = list(notes), -1.0
    best_issue_count = 1_000_000_000
    stale = 0

    iteration_limit = 1 if extended_conversion and conversion_mode == "exact" else max_iterations
    for iteration in range(iteration_limit):
        midi_path = workdir / f"iter_{iteration:03d}.mid"
        wav_path = workdir / f"iter_{iteration:03d}.wav"
        _write_candidate(midi_path, notes, kind, bpm)
        render_midi_to_wav(midi_path, wav_path)

        if is_drum:
            rendered = compare.extract_onsets(str(wav_path))
            diff = compare.diff_drums(ref_onsets, rendered)
            issue_count = len(diff.missed) + len(diff.extra)
            score, detail = diff.score, {
                "f_measure": round(diff.f_measure, 4),
                "missed": len(diff.missed),
                "extra": len(diff.extra),
                "mean_abs_offset_ms": round(diff.mean_abs_offset * 1000, 1),
            }
        else:
            diff = compare.diff_pitched(
                stem_path,
                str(wav_path),
                notes,
                ref_chroma=ref_chroma,
                ref_onsets=ref_onsets,
                ref_evidence=pitched_reference,
                allow_additions=allow_pitched_additions,
                preserve_structure=theory_locked,
            )
            issue_count = len(diff.spurious_notes) + len(diff.edits)
            score, detail = diff.score, {
                "chroma_similarity": round(diff.chroma_similarity, 4),
                "onset_f_measure": round(diff.onset_f_measure, 4),
                "spurious": len(diff.spurious_notes),
                "evidence_notes": diff.evidence_count,
                "proposed_repairs": sum(edit.action == "repair" for edit in diff.edits),
                "proposed_additions": sum(edit.action == "add" for edit in diff.edits),
                "proposed_edits": compare.pitched_edit_detail(diff),
                "edit_policy": "theory_locked" if theory_locked else "transcription",
                "automatic_additions": allow_pitched_additions,
            }
            if diff.evidence_error:
                detail["evidence_warning"] = diff.evidence_error

        history.append(IterationRecord(iteration, round(score, 4), len(notes), detail))

        score_improved = score > best_score + plateau_epsilon
        # A repair may leave chroma/onset scores numerically identical (most
        # often duration or velocity).  Prefer the candidate with fewer
        # evidence-backed issues only when its feature score did not regress.
        issue_tiebreak = (
            not is_drum
            and score + 1e-9 >= best_score
            and issue_count < best_issue_count
        )
        if score_improved or issue_tiebreak:
            best_notes, best_score = list(notes), score
            best_issue_count = issue_count
            stale = 0
        else:
            stale += 1
            if stale >= plateau_patience:
                break

        edited = (
            _apply_edits_drums_preserve_observed(notes, diff)
            if is_drum and extended_conversion
            else _apply_edits_drums(notes, diff, kind)
            if is_drum
            else _apply_edits_pitched(notes, diff)
        )
        if not is_drum and edited == notes:
            break
        notes = normalize_note_events(edited)
        if not notes:
            break

    best_notes = normalize_note_events(best_notes)
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
    note_provenance = _sync_note_provenance(best_notes, note_provenance)
    return RefineResult(
        notes=best_notes,
        score=best_score,
        history=history,
        midi_path=final_midi,
        variants=variants,
        note_provenance=note_provenance,
        variant_provenance=variant_provenance,
    )


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
        from .imagine import imagine_bass, imagine_lead, imagine_pads

        grid, segments, key_name = _load_theory_context(
            stem_path,
            bpm,
            chords_pdf,
            key,
            metronome,
            align_audio,
        )
        if kind == "bass":
            return imagine_bass(stem_path, grid=grid, segments=segments, key_name=key_name)
        if kind == "pads":
            return imagine_pads(stem_path, grid=grid, segments=segments, key_name=key_name)
        return imagine_lead(stem_path, grid=grid, segments=segments, key_name=key_name)

    from .transcribe_pitched import transcribe_pitched_stem
    from .verify import verify_notes

    notes = transcribe_pitched_stem(stem_path, kind=kind)
    return verify_notes(stem_path, notes, threshold=0.10).kept


def _load_theory_context(
    stem_path: str,
    bpm: float,
    chords_pdf: str | Path,
    key: str | None,
    metronome: str | Path | None,
    align_audio: str | Path | None,
):
    import soundfile

    from .beatgrid import Grid, grid_from_metronome
    from .chords import extract_chords_from_moises_pdf, make_chord_segments
    from .harmony import align_chords_to_audio

    duration = soundfile.info(stem_path).duration
    evidence_path = Path(align_audio or stem_path)
    chart_path = Path(chords_pdf)
    metronome_path = Path(metronome) if metronome else None
    cache_key = (
        str(chart_path.resolve()),
        chart_path.stat().st_mtime_ns,
        round(float(duration), 3),
        round(float(bpm), 6),
        key,
        str(evidence_path.resolve()),
        evidence_path.stat().st_mtime_ns,
        str(metronome_path.resolve()) if metronome_path else None,
        metronome_path.stat().st_mtime_ns if metronome_path else None,
    )
    cached = _THEORY_CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    chart = extract_chords_from_moises_pdf(chords_pdf)
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
        segments = make_chord_segments(
            chart.chords,
            duration_seconds=duration,
            bpm=grid.bpm,
        )
    result = (grid, segments, key or chart.key)
    _THEORY_CONTEXT_CACHE[cache_key] = result
    return result


def _seed_pitched_v2(
    stem_path: str,
    kind: str,
    bpm: float,
    chords_pdf: str | Path | None,
    key: str | None,
    metronome: str | Path | None,
    align_audio: str | Path | None,
    conversion_mode: str,
):
    """Return a mode-selected pitched seed plus auditionable alternatives."""

    from .conversion import provenance_for_notes

    variants: dict[str, list[NoteEvent]] = {}
    variant_provenance: dict[str, list[Any]] = {}

    if kind == "bass" and chords_pdf:
        from .imagine import imagine_bass_variants

        grid, segments, key_name = _load_theory_context(
            stem_path,
            bpm,
            chords_pdf,
            key,
            metronome,
            align_audio,
        )
        bass_variants = imagine_bass_variants(
            stem_path,
            grid=grid,
            segments=segments,
            key_name=key_name,
        )
        selected_name = {
            "exact": "raw_verified",
            "repair": "contour_clean",
            "reconstruct": "root_safe",
        }[conversion_mode]
        selected = bass_variants[selected_name]
        variants = {
            name: notes
            for name, notes in bass_variants.items()
            if name != selected_name
        }
        origins = {
            "raw_verified": "observed",
            "contour_clean": "repaired",
            "root_safe": "inferred",
        }
        for name, notes in bass_variants.items():
            sources = ["basic-pitch", "pyin", "spectral-verification"]
            if name in {"contour_clean", "root_safe"}:
                sources.extend(("beat-grid", "key", "chord-chart"))
            sources.append(name)
            records = provenance_for_notes(
                notes,
                origin=origins[name],
                confidence=0.82 if name != "root_safe" else 0.68,
                confidence_basis="policy",
                sources=sources,
                family="bass",
            )
            if name == selected_name:
                selected_provenance = records
            else:
                variant_provenance[name] = records
        return selected, variants, selected_provenance, variant_provenance

    # Exact mode bypasses chart composition for lead/synth/pad-like stems.  It
    # emits only spectrally verified notes heard in the source.
    if (
        conversion_mode == "exact" and kind in THEORY_GENERATED_KINDS
    ) or (
        kind == "pads" and conversion_mode != "reconstruct"
    ):
        from .transcribe_pitched import transcribe_pitched_stem
        from .verify import verify_notes

        transcribe_kind = "keys" if kind == "pads" else ("synth" if kind == "lead" else kind)
        evidence = transcribe_pitched_stem(stem_path, kind=transcribe_kind)
        selected = verify_notes(stem_path, evidence, threshold=0.10).kept
    else:
        selected = _seed_pitched(
            stem_path,
            kind,
            bpm,
            chords_pdf,
            key,
            metronome,
            align_audio,
        )

    if kind in {"keys", "piano"}:
        from .transcribe_pitched import separate_keys_roles

        segments = None
        if chords_pdf:
            _, segments, _ = _load_theory_context(
                stem_path,
                bpm,
                chords_pdf,
                key,
                metronome,
                align_audio,
            )
        roles = separate_keys_roles(selected, segments)
        full_evidence = list(selected)
        repaired = sorted(
            [*roles.melody, *roles.accompaniment],
            key=lambda note: (note.start, note.pitch, note.end),
        )
        # Exact means strong observed role evidence, not every raw hypothesis.
        # The complete union remains available as full_evidence, while notes
        # that cannot be assigned safely stay in the uncertain variant.
        selected = repaired
        variants = {
            "full_evidence": full_evidence,
            "melody": roles.melody,
            "accompaniment": roles.accompaniment,
            "uncertain": roles.uncertain,
        }
        for name, notes in variants.items():
            variant_provenance[name] = provenance_for_notes(
                notes,
                origin="observed",
                confidence=0.8 if name != "uncertain" else 0.45,
                tier="uncertain" if name == "uncertain" else "main",
                confidence_basis="policy",
                sources=("basic-pitch", "spectral-verification", f"keys-role:{name}"),
                family=name,
            )

    if kind == "pads" and conversion_mode == "reconstruct":
        origin = "inferred"
        confidence = 0.7
    elif kind in {"keys", "piano", "pads"}:
        origin = "observed"
        confidence = 0.8
    else:
        origin = "observed" if conversion_mode == "exact" else "repaired"
        confidence = 0.8
    selected_provenance = provenance_for_notes(
        selected,
        origin=origin,
        confidence=confidence,
        confidence_basis="policy",
        sources=("stem", f"listen-{kind}", f"mode:{conversion_mode}"),
        family=kind,
    )
    return selected, variants, selected_provenance, variant_provenance


def _seed_drums_v2(
    stem_path: str,
    kind: str,
    *,
    bpm: float,
    conversion_mode: str,
    metronome: str | Path | None,
):
    from .transcribe_drums import (
        DrumTranscription,
        complete_hat_pattern,
        transcribe_drum_stem_detailed,
    )

    transcription = transcribe_drum_stem_detailed(stem_path, kind)
    if kind == "hat" and conversion_mode in {"repair", "reconstruct"}:
        downbeat = 0.0
        snap = None
        if metronome:
            from .beatgrid import grid_from_metronome

            grid = grid_from_metronome(str(metronome), nominal_bpm=bpm)
            downbeat = grid.time_of(0)
            snap = lambda value: grid.snap(value, 4)
            beat_of = grid.beat_of
            time_of = grid.time_of
        else:
            beat_of = None
            time_of = None
        transcription = complete_hat_pattern(
            transcription,
            bpm=bpm,
            mode=conversion_mode,
            downbeat=downbeat,
            snap=snap,
            beat_of=beat_of,
            time_of=time_of,
        )

    primary_hits = list(transcription.main_hits)
    notes = transcription.to_notes(include_possible=False)
    ref_onsets = [
        compare.Onset(
            time=hit.time,
            strength=max(0.01, min(1.0, hit.absolute_confidence or hit.strength)),
        )
        for hit in primary_hits
    ]
    variants: dict[str, list[NoteEvent]] = {}
    variant_provenance: dict[str, list[Any]] = {}
    if transcription.possible_hits:
        possible = DrumTranscription(
            kind,
            transcription.sample_rate,
            tuple(transcription.possible_hits),
            (),
        )
        variants["possible"] = possible.to_notes()
        variant_provenance["possible"] = _drum_hit_provenance(
            list(transcription.possible_hits),
            variants["possible"],
        )

    families: dict[str, list[Any]] = {}
    for hit in primary_hits:
        families.setdefault(hit.family, []).append(hit)
    for family, hits in sorted(families.items()):
        family_transcription = DrumTranscription(
            kind,
            transcription.sample_rate,
            tuple(hits),
            (),
        )
        family_notes = family_transcription.to_notes()
        variants[family] = family_notes
        variant_provenance[family] = _drum_hit_provenance(hits, family_notes)

    provenance = _drum_hit_provenance(primary_hits, notes)
    return notes, ref_onsets, variants, provenance, variant_provenance


def _drum_hit_provenance(hits: list[Any], notes: list[NoteEvent]):
    from .conversion import NoteProvenance

    records = []
    for hit, note in zip(sorted(hits, key=lambda item: item.time), notes):
        features = asdict(hit.features) if hit.features is not None else {}
        confidence = hit.absolute_confidence if hit.features is not None else 0.55
        if hit.source_time is not None:
            features["source_time"] = hit.source_time
            features["grid_offset_ms"] = round(
                (hit.time - hit.source_time) * 1000.0,
                3,
            )
        if hit.provenance == "inferred":
            sources = ("beat-grid", "recurring-pattern")
        elif hit.provenance == "repaired":
            sources = (
                "stereo-onset",
                "multiband",
                "spectral-family",
                "beat-grid",
                "recurring-pattern",
            )
        else:
            sources = ("stereo-onset", "multiband", "spectral-family")
        records.append(
            NoteProvenance.from_note(
                note,
                origin=hit.provenance,
                confidence=max(0.0, min(1.0, confidence)),
                tier=hit.tier,
                confidence_basis="measured" if hit.features is not None else "policy",
                family=hit.family,
                sources=sources,
                details=features,
            )
        )
    return records


def _sync_note_provenance(notes: list[NoteEvent], records: list[Any]) -> list[Any]:
    """Retarget seed provenance to final repaired note timing/velocity."""

    if not records:
        return []
    from .conversion import NoteProvenance, retarget_note_provenance

    available = [record for record in records if isinstance(record, NoteProvenance)]
    return retarget_note_provenance(
        notes,
        available,
        mark_changed_as_repaired=True,
    )


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
            # Preserve the locally active articulation/family.  Copying the
            # first note in the song collapsed every later repaired variant to
            # one GM pitch.
            template = (
                min(edited, key=lambda note: abs(note.start - onset.time))
                if edited
                else NoteEvent(0.0, 0.08, _default_drum_pitch(kind), 90)
            )
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


def _apply_edits_drums_preserve_observed(
    notes: list[NoteEvent],
    diff: compare.DrumDiff,
    tol: float = 0.035,
) -> list[NoteEvent]:
    """Refine rendering without deleting source-observed semantic events.

    A SoundFont sample can create extra envelope peaks or hide a quiet attack;
    that is evidence about the preview patch, not evidence that the source hit
    was false.  V2 therefore permits local velocity/timing correction only.
    Possible and leakage events are handled explicitly before this stage.
    """

    edited = list(notes)
    for onset in diff.missed:
        near = [i for i, note in enumerate(edited) if abs(note.start - onset.time) <= tol]
        if near:
            index = min(near, key=lambda item: abs(edited[item].start - onset.time))
            edited[index] = replace(
                edited[index],
                velocity=min(127, edited[index].velocity + 12),
            )
    for ref_time, candidate_time in diff.matched:
        offset = ref_time - candidate_time
        if abs(offset) <= 0.008:
            continue
        near = [i for i, note in enumerate(edited) if abs(note.start - candidate_time) <= tol]
        if near:
            index = min(near, key=lambda item: abs(edited[item].start - candidate_time))
            note = edited[index]
            start = max(0.0, note.start + offset)
            edited[index] = replace(
                note,
                start=start,
                end=start + (note.end - note.start),
            )
    return sorted(edited, key=lambda note: (note.start, note.pitch))


def _default_drum_pitch(kind: str) -> int:
    return {
        "kick": 36,
        "snare": 38,
        "hat": 42,
        "cymbals": 49,
        "toms": 45,
        "other_kit": 39,
    }.get(kind, 39)


def _apply_edits_pitched(notes: list[NoteEvent], diff: compare.PitchedDiff) -> list[NoteEvent]:
    """Apply only explicit stem-evidence edits, deterministically.

    A repair wins over the older chroma-only spurious-note decision because a
    wrong pitch/octave naturally has little energy at its original pitch
    class.  Additions are de-duplicated, making the operation stable if the
    same proposal is encountered again.
    """
    spurious = set(diff.spurious_notes)
    repairs = {
        edit.note_index: edit
        for edit in diff.edits
        if edit.action == "repair" and edit.note_index is not None
    }
    edited: list[NoteEvent] = []
    for index, note in enumerate(notes):
        repair = repairs.get(index)
        if repair is not None:
            edited.append(repair.after)
        elif index not in spurious:
            edited.append(note)

    for edit in diff.edits:
        if edit.action != "add":
            continue
        proposed = edit.after
        duplicate = any(
            note.pitch == proposed.pitch
            and abs(note.start - proposed.start) <= 0.02
            and min(note.end, proposed.end) - max(note.start, proposed.start) > 0.0
            for note in edited
        )
        if not duplicate:
            edited.append(proposed)

    return sorted(edited, key=lambda note: (note.start, note.pitch, note.end))
