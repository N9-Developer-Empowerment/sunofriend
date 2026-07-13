"""Process a whole Suno/Moises export folder in one command.

Discovers stems, the chords PDF, and the metronome; infers BPM/key from the
folder name; skips near-silent stems; runs the listen/refine loop per stem
(imagine mode for bass/lead, chord-mode pads from the keys stem); and merges
everything into one GarageBand-ready multitrack MIDI.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

from .metadata import infer_project_metadata
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent

DRUM_PARTS = ["kick", "snare", "hat", "cymbals", "toms", "other_kit"]
PITCHED_PARTS = {  # stem token -> processing kind
    "bass": "bass",
    "lead": "lead",
    "synth": "synth",
    "keys": "keys",
    "piano": "keys",
    "strings": "pads",  # sustained chords: chart voicings + stem dynamics beat transcription
}
CHANNELS = {  # part -> (channel, GM program)
    "kick": (9, 0), "snare": (9, 0), "hat": (9, 0), "cymbals": (9, 0),
    "toms": (9, 0), "other_kit": (9, 0),
    "bass": (0, 38), "keys": (1, 7), "pads": (6, 89), "piano": (3, 0),
    "strings": (4, 48), "lead": (2, 81), "synth": (5, 81),
}
SILENCE_PEAK = 0.005
SILENCE_RMS = 5e-4
SPARSE_SIGNAL_PEAK = 0.02
INSTRUMENT_SUGGESTIONS = {
    "kick": ("Modern 909", "Electronic Drum Kit"),
    "snare": ("Modern 909", "Electronic Drum Kit"),
    "hat": ("Modern 909", "Electronic Drum Kit"),
    "cymbals": ("Modern 909", "Electronic Drum Kit"),
    "toms": ("Modern 909", "Electronic Drum Kit"),
    "other_kit": ("Modern 909", "Electronic Drum Kit"),
    "bass": ("Upright Jazz Bass", "Sub Bass"),
    "keys": ("Different Phases Clav", "Grand Piano"),
    "piano": ("Grand Piano", "Electric Piano"),
    "pads": ("Warm Pad", "Strings"),
    "strings": ("Strings", "Warm Pad"),
    "lead": ("Flow Synth Lead", "Synth Lead"),
    "synth": ("Flow Synth Pluck", "Synth Lead"),
}


def run_listen_all(
    folder: str | Path,
    out_dir: str | Path,
    bpm: float | None = None,
    key: str | None = None,
    parts: list[str] | None = None,
    max_iterations: int = 8,
    library: str | Path | None = None,
    conversion_mode: str = "repair",
    evaluate_outputs: bool = True,
    evaluate_variants: bool = False,
    progress=print,
) -> dict:
    from .loop import refine_stem
    from .conversion import validate_conversion_mode

    conversion_mode = validate_conversion_mode(conversion_mode)

    folder = Path(folder)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = infer_project_metadata(folder)
    bpm = bpm or metadata.bpm
    if bpm is None:
        raise ValueError("BPM not provided and not inferable from folder name")
    key = key or metadata.key

    chords_pdf = next(iter(sorted(folder.glob("*chords*.pdf"))), None)
    metronome = _find_stem(folder, "metronome")
    keys_stem = _find_stem(folder, "keys")

    summary: dict = {
        "folder": str(folder),
        "bpm_nominal": bpm,
        "key": key,
        "chords_pdf": str(chords_pdf) if chords_pdf else None,
        "metronome": bool(metronome),
        "run_scope": "selection" if parts else "full",
        "requested_parts": sorted(set(parts)) if parts else None,
        "conversion_mode": conversion_mode,
        "parts": {},
    }
    if library is not None:
        from .library import ClipLibrary

        clip_library = ClipLibrary(library)
        summary["library"] = str(clip_library.root)
    else:
        clip_library = None

    from .beatgrid import Grid

    grid = Grid(bpm=bpm)
    daw_bpm = float(round(bpm))
    if metronome:
        from .beatgrid import grid_from_metronome

        grid = grid_from_metronome(str(metronome), nominal_bpm=bpm)
        summary["bpm_true"] = grid.bpm
        summary["downbeat_offset"] = round(grid.time_of(0), 4)
        summary["beat_wander"] = grid.is_warped
        daw_bpm = float(round(grid.bpm))
    # Preserve the proven GarageBand contract: notes remain in absolute source
    # seconds and the user sets the project to this explicit export tempo.
    summary["set_garageband_tempo_to"] = daw_bpm

    jobs: list[tuple[str, Path, str]] = []  # (output name, stem path, kind)
    wanted = set(parts) if parts else None
    selection_suffix = "-".join(_safe_token(part) for part in sorted(wanted or ()))
    # V2 never overwrites a legacy/golden root layout.  Every semantic policy,
    # including the default repair mode, owns an explicit directory.
    mode_root = out_dir / f"mode_{conversion_mode}"
    publish_dir = mode_root / f"selected_{selection_suffix}" if wanted else mode_root
    publish_dir.mkdir(parents=True, exist_ok=True)
    for part in DRUM_PARTS:
        stem = _find_stem(folder, part)
        if stem and (wanted is None or part in wanted):
            jobs.append((part, stem, part))
    for token, kind in PITCHED_PARTS.items():
        stem = _find_stem(folder, token)
        if stem and (wanted is None or token in wanted):
            jobs.append((token, stem, kind))
    if keys_stem and (wanted is None or "pads" in wanted):
        if conversion_mode != "reconstruct":
            # There is no pads stem: the usual pads part is intentionally
            # composed from the chart and keys activity.  Exact mode must not
            # disguise that reconstruction as an observed conversion.
            summary["parts"]["pads"] = {
                "status": f"skipped: no observed pads stem in {conversion_mode} mode"
            }
        else:
            jobs.append(("pads", keys_stem, "pads"))

    arrangement_name = (
        f"selected_arrangement_{selection_suffix}.mid" if wanted else "full_arrangement.mid"
    )
    arrangement = mode_root / arrangement_name
    # A run scope is a replaceable build product.  Clear only its generated
    # artifacts before processing so a vanished/failed stem—or a no-output
    # rerun—cannot leave an old MIDI or arrangement looking current.  Other
    # selected scopes and all legacy/golden root files remain untouched.
    _reset_generated_run_scope(publish_dir, arrangement)

    seen = set()
    merged_tracks: list[MidiTrack] = []
    drum_context: dict[str, list] = {}
    for name, stem, kind in jobs:
        if name in seen:
            continue
        seen.add(name)
        if _is_silent(stem):
            # A full/selected rerun may revisit an output directory that once
            # contained a usable version of this part.  Once current source
            # analysis classifies it as separation residue, remove only that
            # run scope's stale generated artifacts so they cannot be mistaken
            # for members of the new arrangement.
            _remove_generated_part_artifacts(publish_dir, name, include_primary=True)
            summary["parts"][name] = {"status": "skipped: near-silent stem"}
            progress(f"{name}: skipped (near-silent)")
            continue
        started = time.time()
        try:
            part_dir = publish_dir / f".{name}_work"
            result = refine_stem(
                stem_path=stem,
                kind=kind,
                bpm=bpm,
                output_bpm=daw_bpm,
                out_dir=part_dir,
                max_iterations=max_iterations,
                chords_pdf=chords_pdf,
                key=key,
                metronome=metronome,
                align_audio=keys_stem if kind in {"bass", "lead", "synth", "pads"} else None,
                conversion_mode=conversion_mode,
            )
            if kind in DRUM_PARTS:
                from .conversion import (
                    NoteProvenance,
                    partition_cross_stem_leakage,
                    partition_uncertain_families,
                )

                records = [
                    value
                    for value in result.note_provenance
                    if isinstance(value, NoteProvenance)
                ]
                if name == "toms" and records and drum_context:
                    main, main_records, uncertain, uncertain_records = (
                        partition_cross_stem_leakage(
                            result.notes,
                            records,
                            drum_context,
                        )
                    )
                    if uncertain:
                        result.notes = main
                        result.note_provenance = main_records
                        result.variants["leakage_uncertain"] = uncertain
                        result.variant_provenance["leakage_uncertain"] = uncertain_records
                elif name == "other_kit" and records:
                    main, main_records, uncertain, uncertain_records = (
                        partition_uncertain_families(result.notes, records)
                    )
                    (
                        main,
                        main_records,
                        leakage,
                        leakage_records,
                    ) = partition_cross_stem_leakage(
                        main,
                        main_records,
                        drum_context,
                    )
                    uncertain.extend(leakage)
                    uncertain_records.extend(leakage_records)
                    if uncertain:
                        result.notes = main
                        result.note_provenance = main_records
                        result.variants.pop("unknown", None)
                        result.variant_provenance.pop("unknown", None)
                        result.variants["uncertain"] = uncertain
                        result.variant_provenance["uncertain"] = uncertain_records
                _refresh_drum_family_variants(result)
                drum_context[name] = [
                    value
                    for value in result.note_provenance
                    if isinstance(value, NoteProvenance)
                ]
            # The processing kind and published role are not always the same
            # (piano uses the keys engine; strings uses the pad engine).  Write
            # the public part with its GarageBand-facing channel/program.
            published_channel, published_program = CHANNELS.get(name, (5, 0))
            write_midi_file(
                result.midi_path,
                [
                    MidiTrack(
                        name.title(),
                        published_channel,
                        published_program,
                        result.notes,
                    )
                ],
                bpm=daw_bpm,
            )
            # refine writes <kind>_listened.mid inside part_dir; publish under the part name
            # (copy instead of rename: some mounted filesystems forbid rename)
            import shutil

            _remove_generated_part_artifacts(publish_dir, name, include_primary=False)
            final = publish_dir / f"{name}_listened.mid"
            shutil.copyfile(result.midi_path, final)
            iterations_src = part_dir / f"{kind}_iterations.json"
            if iterations_src.exists():
                shutil.copyfile(iterations_src, publish_dir / f"{name}_iterations.json")
            from .conversion import (
                NoteProvenance,
                provenance_for_notes,
                retarget_note_provenance,
                write_note_provenance,
            )
            from .note_safety import normalize_note_events

            provenance_records = [
                record for record in result.note_provenance
                if isinstance(record, NoteProvenance)
            ]
            if not provenance_records:
                provenance_records = _default_note_provenance(
                    result.notes,
                    name=name,
                    kind=kind,
                    conversion_mode=conversion_mode,
                    score=result.score,
                )
            provenance_records = _retarget_published_role_provenance(
                provenance_records,
                name=name,
                kind=kind,
            )
            provenance_path = publish_dir / f"{name}_provenance.json"
            write_note_provenance(
                provenance_path,
                provenance_records,
                conversion_mode=conversion_mode,
                source_stem=stem,
                variant=name,
            )

            variants: dict[str, dict] = {}
            if result.variants:
                variants_dir = publish_dir / "variants"
                variants_dir.mkdir(parents=True, exist_ok=True)
                channel, program = CHANNELS.get(name, (5, 0))
                for variant_name, variant_notes in sorted(result.variants.items()):
                    variant_notes = normalize_note_events(variant_notes)
                    result.variants[variant_name] = variant_notes
                    if not variant_notes or variant_name in {"main", name}:
                        continue
                    token = _safe_token(variant_name)
                    variant_path = variants_dir / f"{_safe_token(name)}-{token}.mid"
                    write_midi_file(
                        variant_path,
                        [
                            MidiTrack(
                                f"{name.title()} {variant_name.replace('_', ' ').title()}",
                                channel=channel,
                                program=program,
                                notes=variant_notes,
                            )
                        ],
                        bpm=daw_bpm,
                    )
                    records = [
                        record
                        for record in result.variant_provenance.get(variant_name, [])
                        if isinstance(record, NoteProvenance)
                    ]
                    if records:
                        records = retarget_note_provenance(variant_notes, records)
                    if not records:
                        records = provenance_for_notes(
                            variant_notes,
                            origin=_variant_origin(variant_name),
                            confidence=max(0.0, min(1.0, float(result.score))),
                            tier="uncertain" if "uncertain" in variant_name else "main",
                            confidence_basis="aggregate",
                            sources=("stem", "variant", variant_name),
                        )
                    records = _retarget_published_role_provenance(
                        records,
                        name=name,
                        kind=kind,
                    )
                    variant_provenance_path = variants_dir / f"{_safe_token(name)}-{token}.provenance.json"
                    write_note_provenance(
                        variant_provenance_path,
                        records,
                        conversion_mode=conversion_mode,
                        source_stem=stem,
                        variant=variant_name,
                    )
                    variants[variant_name] = {
                        "notes": len(variant_notes),
                        "midi": str(variant_path),
                        "provenance": str(variant_provenance_path),
                    }
            shutil.rmtree(part_dir, ignore_errors=True)
            summary["parts"][name] = {
                "status": "ok",
                "score": round(result.score, 4),
                "score_scope": "render_proxy_before_semantic_filtering",
                "notes": len(result.notes),
                "iterations": len(result.history),
                "seconds": round(time.time() - started, 1),
                "midi": str(final),
                "provenance": str(provenance_path),
                "stem": str(stem),
                "instrument_suggestions": list(
                    INSTRUMENT_SUGGESTIONS.get(name, ())
                ),
                "instrument_match_command": [
                    "sunofriend",
                    "instrument-match",
                    str(stem),
                    str(final),
                    "--kind",
                    name,
                    "--out-dir",
                    str(publish_dir / "instrument_matches" / name),
                ],
            }
            if variants:
                summary["parts"][name]["variants"] = variants
            if evaluate_outputs:
                try:
                    from .evaluate import evaluate_stem_midi, v2_pitch_family_map

                    evaluation = evaluate_stem_midi(
                        stem,
                        result.notes,
                        kind=kind,
                        pitch_family_map=v2_pitch_family_map(kind),
                    )
                    evaluation_path = publish_dir / f"{name}_evaluation.json"
                    _write_json_atomic(evaluation_path, evaluation.to_dict())
                    summary["parts"][name]["evaluation"] = str(evaluation_path)
                    summary["parts"][name]["semantic_metrics"] = _evaluation_headline(
                        evaluation
                    )
                    if evaluate_variants:
                        for variant_name, variant_details in variants.items():
                            try:
                                variant_report = evaluate_stem_midi(
                                    stem,
                                    result.variants[variant_name],
                                    kind=kind,
                                    pitch_family_map=v2_pitch_family_map(kind),
                                )
                                variant_evaluation = Path(
                                    variant_details["midi"]
                                ).with_suffix(".evaluation.json")
                                _write_json_atomic(
                                    variant_evaluation,
                                    variant_report.to_dict(),
                                )
                                variant_details["evaluation"] = str(
                                    variant_evaluation
                                )
                                variant_details["semantic_metrics"] = (
                                    _evaluation_headline(variant_report)
                                )
                            except Exception as exc:
                                variant_details["evaluation_warning"] = str(exc)
                except Exception as exc:
                    summary["parts"][name]["evaluation_warning"] = str(exc)
            if clip_library is not None:
                try:
                    clip = _make_library_clip(
                        title=f"{folder.name} - {name}",
                        name=name,
                        kind=kind,
                        stem=stem,
                        midi=final,
                        notes=result.notes,
                        score=result.score,
                        key=key,
                        grid=grid,
                        daw_bpm=daw_bpm,
                        conversion_mode=conversion_mode,
                        provenance_path=provenance_path,
                    )
                    catalog_entry = clip_library.add(clip)
                    summary["parts"][name]["library_clip_id"] = catalog_entry.clip_id
                    variant_library_errors = {}
                    for variant_name, variant_details in variants.items():
                        try:
                            variant_notes = result.variants[variant_name]
                            variant_path = Path(variant_details["midi"])
                            variant_clip = _make_library_clip(
                                title=(
                                    f"{folder.name} - {name} - "
                                    f"{variant_name.replace('_', ' ')}"
                                ),
                                name=name,
                                kind=kind,
                                stem=stem,
                                midi=variant_path,
                                notes=variant_notes,
                                score=None,
                                key=key,
                                grid=grid,
                                daw_bpm=daw_bpm,
                                conversion_mode=conversion_mode,
                                provenance_path=Path(variant_details["provenance"]),
                                variant=variant_name,
                                related_clip_id=catalog_entry.clip_id,
                            )
                            variant_entry = clip_library.add(variant_clip)
                            variant_details["library_clip_id"] = variant_entry.clip_id
                        except Exception as exc:
                            variant_library_errors[variant_name] = str(exc)
                    if variant_library_errors:
                        summary["parts"][name]["variant_library_errors"] = (
                            variant_library_errors
                        )
                except Exception as exc:
                    summary["parts"][name]["library_error"] = str(exc)
            channel, program = CHANNELS.get(name, (5, 0))
            arrangement_notes = result.notes
            arrangement_role = "primary"
            if conversion_mode == "reconstruct" and name == "keys":
                arrangement_notes = result.variants.get("melody", [])
                arrangement_role = "melody_only_with_chart_pads"
            elif conversion_mode == "reconstruct" and name == "strings":
                arrangement_notes = []
                arrangement_role = "audition_only_avoids_chart_doubling"
            summary["parts"][name]["arrangement_role"] = arrangement_role
            if arrangement_notes:
                merged_tracks.append(
                    MidiTrack(
                        name.title(),
                        channel=channel,
                        program=program,
                        notes=arrangement_notes,
                    )
                )
            progress(f"{name}: ok score={summary['parts'][name]['score']} notes={len(result.notes)}")
        except Exception as exc:  # keep going; one bad stem shouldn't kill the batch
            summary["parts"][name] = {"status": f"error: {exc}"}
            progress(f"{name}: ERROR {exc}")

    successful = sum(1 for item in summary["parts"].values() if item["status"] == "ok")
    failed = sum(1 for item in summary["parts"].values() if item["status"].startswith("error:"))
    library_failed = sum(
        1
        for item in summary["parts"].values()
        if "library_error" in item or "variant_library_errors" in item
    )
    if (failed or library_failed) and successful:
        summary["status"] = "partial"
    elif failed:
        summary["status"] = "failed"
    elif successful:
        summary["status"] = "complete"
    else:
        summary["status"] = "no-output"
    summary["successful_parts"] = successful
    summary["failed_parts"] = failed
    summary["library_failed_parts"] = library_failed

    if merged_tracks:
        write_midi_file(arrangement, merged_tracks, bpm=daw_bpm)
        summary["arrangement"] = str(arrangement)
    summary_name = (
        f"listen_all_summary_{selection_suffix}.json" if wanted else "listen_all_summary.json"
    )
    summary_path = mode_root / summary_name
    summary["summary"] = str(summary_path)
    _write_json_atomic(summary_path, summary)
    return summary


def _find_stem(folder: Path, part: str) -> Path | None:
    for path in sorted(folder.glob("*.wav")):
        name = path.name.lower()
        if f"-{part}-" in name or f"_{part}-" in name:
            return path
    return None


def _is_silent(
    path: Path,
    peak_threshold: float = SILENCE_PEAK,
    rms_threshold: float = SILENCE_RMS,
    sparse_signal_peak: float = SPARSE_SIGNAL_PEAK,
) -> bool:
    """Detect empty/separation-bleed stems without losing audible sparse parts.

    Peak-only gating lets a single tiny click make an otherwise noise-floor
    stem look usable.  Clearly audible peaks return quickly; borderline files
    are scanned fully and must also clear a conservative whole-file RMS floor.
    """

    import numpy as np
    import soundfile

    peak = 0.0
    square_sum = 0.0
    sample_count = 0
    with soundfile.SoundFile(str(path)) as handle:
        for block in handle.blocks(blocksize=1 << 20, dtype="float32"):
            peak = max(peak, float(np.max(np.abs(block))))
            if peak >= sparse_signal_peak:
                return False
            values = block.astype("float64", copy=False)
            square_sum += float(np.sum(values * values))
            sample_count += values.size
    rms = (square_sum / sample_count) ** 0.5 if sample_count else 0.0
    return peak <= peak_threshold or rms <= rms_threshold


def _safe_token(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "-" for character in value.lower())
    return "-".join(part for part in cleaned.split("-") if part) or "part"


def _remove_generated_part_artifacts(
    publish_dir: Path,
    name: str,
    *,
    include_primary: bool,
) -> None:
    """Remove only stale generated files owned by one part/run scope."""

    if include_primary:
        for suffix in ("_listened.mid", "_iterations.json"):
            (publish_dir / f"{name}{suffix}").unlink(missing_ok=True)
    for suffix in ("_provenance.json", "_evaluation.json"):
        (publish_dir / f"{name}{suffix}").unlink(missing_ok=True)
    variants_dir = publish_dir / "variants"
    prefix = f"{_safe_token(name)}-"
    if variants_dir.is_dir():
        for path in variants_dir.iterdir():
            if path.is_file() and path.name.startswith(prefix):
                path.unlink(missing_ok=True)


def _reset_generated_run_scope(publish_dir: Path, arrangement: Path) -> None:
    """Remove generated artifacts owned by exactly one full/selected build."""

    import shutil

    for pattern in (
        "*_listened.mid",
        "*_iterations.json",
        "*_provenance.json",
        "*_evaluation.json",
    ):
        for path in publish_dir.glob(pattern):
            if path.is_file():
                path.unlink(missing_ok=True)
    variants_dir = publish_dir / "variants"
    if variants_dir.is_dir():
        shutil.rmtree(variants_dir)
    for work_dir in publish_dir.glob(".*_work"):
        if work_dir.is_dir():
            shutil.rmtree(work_dir, ignore_errors=True)
    arrangement.unlink(missing_ok=True)


def _variant_origin(variant_name: str):
    text = variant_name.lower()
    if any(token in text for token in ("raw", "observed", "evidence", "exact")):
        return "observed"
    if any(token in text for token in ("root", "pad", "reconstruct", "inferred")):
        return "inferred"
    return "repaired"


def _default_note_provenance(
    notes: list[NoteEvent],
    *,
    name: str,
    kind: str,
    conversion_mode: str,
    score: float | None,
):
    from .conversion import provenance_for_notes

    if (kind == "pads" and conversion_mode == "reconstruct") or conversion_mode == "reconstruct":
        origin = "inferred"
    elif conversion_mode == "repair" and kind in {"bass", "lead", "synth"}:
        origin = "repaired"
    else:
        origin = "observed"
    confidence = max(0.0, min(1.0, float(score)))
    return provenance_for_notes(
        notes,
        origin=origin,
        confidence=confidence,
        confidence_basis="aggregate",
        sources=("stem", f"listen-{kind}", f"mode:{conversion_mode}"),
        family=name,
    )


def _retarget_published_role_provenance(
    records,
    *,
    name: str,
    kind: str,
):
    """Label engine output with its public musical role without hiding the engine.

    Some published parts deliberately reuse a transcription engine: strings
    use the pads engine and piano uses the keys engine.  Their MIDI channel and
    program already follow the published role, so the sidecar must do the same.
    The processing kind remains explicit for reproducibility.
    """

    values = list(records)
    if name == kind:
        return values

    engine_source = f"listen-{kind}"
    published_source = f"listen-{name}"
    engine_marker = f"processing-engine:{kind}"
    result = []
    for record in values:
        family = record.family
        if family == kind:
            family = name
        elif family and family.startswith(f"{kind}_"):
            family = f"{name}{family[len(kind):]}"

        sources = tuple(
            published_source if source == engine_source else source
            for source in record.sources
        )
        if published_source not in sources:
            sources += (published_source,)
        if engine_marker not in sources:
            sources += (engine_marker,)

        details = dict(record.details)
        details["published_role"] = name
        details["processing_kind"] = kind
        result.append(
            replace(
                record,
                family=family,
                sources=sources,
                details=details,
            )
        )
    return result


def _evaluation_headline(report) -> dict:
    result = {
        "strong_onset_f1": report.onsets.strong.f1,
        "possible_onset_f1": report.onsets.possible.f1,
        "timing_p50_ms": report.onsets.timing.absolute_error_p50_ms,
        "timing_p95_ms": report.onsets.timing.absolute_error_p95_ms,
        "drift_ms": report.onsets.timing.drift_ms,
    }
    if report.pitched is not None:
        result.update(
            {
                "chroma_similarity": report.pitched.chroma_similarity,
                "pitch_support": report.pitched.mean_pitch_support,
                "octave_accuracy": report.pitched.octave_accuracy,
                "contour_direction_accuracy": report.pitched.contour_direction_accuracy,
                "polyphony_mean": report.pitched.candidate_polyphony_mean,
            }
        )
    if report.drums is not None:
        result["families"] = report.drums.family_counts
    return result


def _refresh_drum_family_variants(result) -> None:
    """Make family audition tracks reflect the post-quarantine main MIDI."""

    from .conversion import NoteProvenance

    from .evaluate import V2_DRUM_PITCH_FAMILIES

    family_names = set(V2_DRUM_PITCH_FAMILIES.values())
    for name in list(result.variants):
        if name in family_names:
            result.variants.pop(name, None)
            result.variant_provenance.pop(name, None)
    records = [
        value for value in result.note_provenance if isinstance(value, NoteProvenance)
    ]
    grouped_notes: dict[str, list[NoteEvent]] = {}
    grouped_records: dict[str, list[NoteProvenance]] = {}
    available = list(result.notes)
    for record in records:
        if record.family in {None, "unknown"} or not available:
            continue
        index = min(
            range(len(available)),
            key=lambda item: (
                available[item].pitch != record.pitch,
                abs(available[item].start - record.start),
            ),
        )
        note = available.pop(index)
        grouped_notes.setdefault(record.family, []).append(note)
        grouped_records.setdefault(record.family, []).append(record)
    for family, notes in grouped_notes.items():
        result.variants[family] = notes
        result.variant_provenance[family] = grouped_records[family]


def _write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def _make_library_clip(
    *,
    title: str,
    name: str,
    kind: str,
    stem: Path,
    midi: Path,
    notes: list[NoteEvent],
    score: float,
    key: str | None,
    grid,
    daw_bpm: float,
    conversion_mode: str = "repair",
    provenance_path: Path | None = None,
    variant: str | None = None,
    related_clip_id: str | None = None,
):
    from .clip import (
        ClipNote,
        Instrument,
        KeySignature,
        MidiClip,
        Provenance,
        TempoMap,
        TempoPoint,
        TimeSignature,
        WarpPoint,
    )
    from .note_safety import normalize_note_events

    bpm = float(grid.bpm)
    warp_points = ()
    if grid.is_warped:
        warp_points = tuple(
            WarpPoint(grid.first_beat_index + index, source_second)
            for index, source_second in enumerate(grid.beat_times)
        )
    tempo_map = TempoMap(
        (TempoPoint(0.0, bpm),),
        warp_points,
        offset_seconds=grid.time_of(0),
    )
    clip_notes = []
    for note in normalize_note_events(notes):
        start_beat = grid.beat_of(note.start)
        end_beat = grid.beat_of(note.end)
        clip_notes.append(
            ClipNote(
                start_beat=start_beat,
                duration_beats=max(1.0 / 480.0, end_beat - start_beat),
                pitch=note.pitch,
                velocity=note.velocity,
                source_start_seconds=note.start,
                source_end_seconds=note.end,
            )
        )
    channel, program = CHANNELS.get(name, (5, 0))
    digest = hashlib.sha256(midi.read_bytes()).hexdigest()
    provenance_digest = (
        hashlib.sha256(provenance_path.read_bytes()).hexdigest()
        if provenance_path is not None and provenance_path.is_file()
        else None
    )
    provenance_details = {
        "garageband_bpm": daw_bpm,
        "timing_mode": "stem_locked",
        "midi_sha256": digest,
        "conversion_mode": conversion_mode,
        "variant": variant or "primary",
    }
    if score is None:
        provenance_details["score_scope"] = "not_scored_variant"
    else:
        provenance_details["score"] = round(float(score), 6)
        provenance_details["score_scope"] = "render_proxy_before_semantic_filtering"
    if provenance_digest is not None:
        provenance_details["note_provenance_sha256"] = provenance_digest
    if related_clip_id is not None:
        provenance_details["related_primary_clip_id"] = related_clip_id
    tags = ["match", "stem-conversion", f"mode:{conversion_mode}"]
    if variant:
        tags.append(f"variant:{_safe_token(variant)}")
    clip = MidiClip(
        title=title,
        tempo_map=tempo_map,
        time_signature=TimeSignature(4, 4),
        instrument=Instrument(
            role=name,
            program=program,
            channel=channel,
            suggestions=INSTRUMENT_SUGGESTIONS.get(name, ()),
        ),
        notes=tuple(clip_notes),
        key=KeySignature.parse(key),
        provenance=Provenance(
            source_uri=str(stem.parent.resolve()),
            source_stem=str(stem.resolve()),
            converter=f"sunofriend.listen-{kind}",
            details=provenance_details,
        ),
        tags=tuple(tags),
    )
    return clip.with_content_id()


__all__ = ["run_listen_all", "NoteEvent"]
