from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from importlib import metadata as importlib_metadata
from pathlib import Path

from .pipeline import run_remake

_COMMANDS = {
    "remake", "listen", "listen-all", "evaluate", "doctor", "preview", "midi-ports", "play",
    "midi-tempo",
    "garageband-info", "clip-import", "clip-list", "clip-show", "clip-export",
    "clip-transform", "clip-instrument",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sunofriend",
        description="Clean GarageBand-ready MIDI from AI-generated stems.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    remake = sub.add_parser("remake", help="Legacy grid-based remake of a Moises/Suno export folder")
    remake.add_argument("input_folder", help="Folder containing Moises stems and a chords PDF")
    remake.add_argument("--out-dir", required=True, help="Output directory for MIDI files and report")
    remake.add_argument("--style", default="edm", choices=["edm", "house", "trap", "hiphop"])
    remake.add_argument("--bpm", type=float, default=None, help="Override BPM if it cannot be inferred")
    remake.add_argument("--key", default=None, help='Override key, e.g. "G major"')

    listen = sub.add_parser(
        "listen",
        help="Transcribe a stem by listening: transcribe -> render (FluidSynth GM proxy) -> compare -> refine",
    )
    listen.add_argument("stem", help="Path to a stem WAV file")
    listen.add_argument(
        "--kind",
        required=True,
        choices=["kick", "snare", "hat", "cymbals", "toms", "other_kit", "keys", "piano", "synth", "lead", "pads", "bass"],
        help="What instrument the stem contains",
    )
    listen.add_argument(
        "--no-evaluate",
        action="store_true",
        help="Skip the independent stem-to-MIDI semantic report",
    )
    listen.add_argument(
        "--evaluate-variants",
        action="store_true",
        help="Also compare every audition variant with the source stem",
    )
    listen.add_argument("--bpm", type=float, required=True, help="Track BPM (from Suno/Moises metadata)")
    listen.add_argument("--out-dir", required=True, help="Output directory")
    listen.add_argument("--max-iterations", type=int, default=30)
    listen.add_argument("--keep-workdir", action="store_true", help="Keep per-iteration MIDI/WAV files")
    listen.add_argument(
        "--chords-pdf",
        default=None,
        help="Moises chords PDF: enables theory-constrained 'imagine' mode for bass/lead/synth/pads "
        "(compose in-key, on-grid, chord-aware; stem supplies rhythm + pitch hints)",
    )
    listen.add_argument("--key", default=None, help='Key override, e.g. "C minor" (default: from chords PDF)')
    listen.add_argument("--metronome", default=None, help="Metronome stem WAV: derive the true beat grid from clicks")
    listen.add_argument(
        "--conversion-mode",
        choices=["exact", "repair", "reconstruct"],
        default="repair",
        help=(
            "exact=strong observed evidence only; repair=confidence-backed corrections; "
            "reconstruct=allow clearly-labelled musical inference"
        ),
    )

    listen_all = sub.add_parser(
        "listen-all",
        help="Process a whole Suno/Moises export folder: all stems -> MIDI + combined arrangement",
    )
    listen_all.add_argument("input_folder", help="Export folder with stems (+ chords PDF, metronome)")
    listen_all.add_argument("--out-dir", required=True, help="Output directory")
    listen_all.add_argument("--bpm", type=float, default=None, help="Override BPM (default: from folder name)")
    listen_all.add_argument("--key", default=None, help="Override key (default: from folder name / chords PDF)")
    listen_all.add_argument(
        "--parts",
        default=None,
        help="Comma-separated subset, e.g. kick,snare,bass,pads (default: everything found)",
    )
    listen_all.add_argument(
        "--no-evaluate",
        action="store_true",
        help="Skip independent semantic reports for generated parts",
    )
    listen_all.add_argument(
        "--evaluate-variants",
        action="store_true",
        help="Also compare every audition variant with its source stem",
    )
    listen_all.add_argument("--max-iterations", type=int, default=8)
    listen_all.add_argument(
        "--conversion-mode",
        choices=["exact", "repair", "reconstruct"],
        default="repair",
        help=(
            "exact=strong observed evidence only; repair=confidence-backed corrections; "
            "reconstruct=allow clearly-labelled musical inference"
        ),
    )
    listen_all.add_argument(
        "--library",
        default=None,
        help="Archive successful parts as Clip v1 assets in this local library",
    )

    evaluate = sub.add_parser(
        "evaluate",
        help="Independently compare a stem WAV with an existing MIDI file",
    )
    evaluate.add_argument("stem", help="Source stem WAV")
    evaluate.add_argument("midi", help="Candidate MIDI file")
    evaluate.add_argument(
        "--kind",
        required=True,
        choices=[
            "kick", "snare", "hat", "cymbals", "toms", "other_kit",
            "keys", "piano", "synth", "lead", "pads", "bass",
        ],
    )
    evaluate.add_argument(
        "--out",
        default=None,
        help="JSON report path (default: beside MIDI as *.evaluation.json)",
    )

    sub.add_parser("doctor", help="Check the audio, ML, SoundFont, and CoreMIDI setup")

    preview = sub.add_parser("preview", help="Render a MIDI file to WAV with FluidSynth")
    preview.add_argument("midi", help="MIDI file to render")
    preview.add_argument("--out", default=None, help="Output WAV (default: beside the MIDI file)")

    sub.add_parser("midi-ports", help="List CoreMIDI outputs, including enabled IAC buses")
    play = sub.add_parser("play", help="Play MIDI to GarageBand or hardware through CoreMIDI")
    play.add_argument("midi", help="MIDI file to play")
    play.add_argument("--port", default=None, help="Exact name or unique part of a MIDI output name")

    midi_tempo = sub.add_parser(
        "midi-tempo",
        help="Speed up or slow down complete MIDI files while preserving bars and tracks",
    )
    midi_tempo.add_argument(
        "input",
        help="One .mid/.midi file, or a directory to process recursively",
    )
    midi_tempo.add_argument(
        "--source-bpm",
        "--from-bpm",
        dest="source_bpm",
        type=float,
        default=None,
        help=(
            "Expected starting BPM, or the DAW tempo for tempo-less MIDI; "
            "otherwise inferred at tick zero (SMF default: 120)"
        ),
    )
    midi_tempo.add_argument(
        "--target-bpm",
        "--to-bpm",
        dest="target_bpm",
        type=float,
        required=True,
        help="New musical tempo, e.g. 125",
    )
    midi_tempo.add_argument(
        "--out",
        default=None,
        help=(
            "Output MIDI path for a file, or output directory for a directory; "
            "default: a sibling name ending in -<target>bpm"
        ),
    )
    midi_tempo.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing destination MIDI files",
    )

    garageband = sub.add_parser(
        "garageband-info", help="Read tempo/key/instrument evidence from a .band project"
    )
    garageband.add_argument("project", help="Path to a GarageBand .band bundle")

    clip_import = sub.add_parser("clip-import", help="Import MIDI tracks into a Clip v1 library")
    clip_import.add_argument("midi", help="MIDI file to import")
    _add_library_argument(clip_import)
    clip_import.add_argument("--key", default=None, help='Key override, e.g. "D minor"')
    clip_import.add_argument("--role", default=None, help="Instrument role override")
    clip_import.add_argument("--suggest", action="append", default=[], help="Instrument suggestion")
    clip_import.add_argument("--tag", action="append", default=[], help="Searchable tag")
    clip_import.add_argument("--track-index", type=int, default=None, help="Import only this note track")
    clip_import.add_argument("--title", default=None, help="Title override (or prefix for multiple tracks)")

    clip_list = sub.add_parser("clip-list", help="Search/list the local Clip v1 library")
    _add_library_argument(clip_list)
    clip_list.add_argument("--text", default=None)
    clip_list.add_argument("--key", default=None)
    clip_list.add_argument("--role", default=None)
    clip_list.add_argument("--bpm", type=float, default=None)
    clip_list.add_argument("--bpm-tolerance", type=float, default=0.5)
    clip_list.add_argument("--tag", action="append", default=[])
    clip_list.add_argument("--limit", type=int, default=100)

    clip_show = sub.add_parser("clip-show", help="Show one Clip v1 JSON document")
    clip_show.add_argument("clip_id")
    _add_library_argument(clip_show)

    clip_export = sub.add_parser("clip-export", help="Export one library clip as GarageBand MIDI")
    clip_export.add_argument("clip_id")
    clip_export.add_argument("--out", required=True)
    clip_export.add_argument(
        "--timing-mode",
        choices=["auto", "musical", "stem_locked"],
        default="auto",
        help="Export beat timing or exact source-second timing (default: clip contract)",
    )
    clip_export.add_argument(
        "--garageband-bpm",
        type=float,
        default=None,
        help="Tempo to enter in GarageBand for a stem-locked export",
    )
    _add_library_argument(clip_export)

    clip_transform = sub.add_parser(
        "clip-transform", help="Create a versioned key and/or BPM variant"
    )
    clip_transform.add_argument("clip_id")
    _add_library_argument(clip_transform)
    key_change = clip_transform.add_mutually_exclusive_group()
    key_change.add_argument("--target-key", default=None, help='Target such as "G major"')
    key_change.add_argument("--semitones", type=int, default=None)
    clip_transform.add_argument("--direction", choices=["nearest", "up", "down"], default="nearest")
    clip_transform.add_argument("--target-bpm", type=float, default=None)
    clip_transform.add_argument(
        "--timing-mode", choices=["musical", "stem_locked"], default="musical"
    )
    clip_transform.add_argument("--out", default=None, help="Also export the final version to MIDI")

    clip_instrument = sub.add_parser(
        "clip-instrument", help="Version a clip with chosen GarageBand instrument metadata"
    )
    clip_instrument.add_argument("clip_id")
    _add_library_argument(clip_instrument)
    clip_instrument.add_argument("--role", default=None)
    clip_instrument.add_argument("--program", type=int, default=None)
    clip_instrument.add_argument("--channel", type=int, default=None)
    clip_instrument.add_argument(
        "--suggest", action="append", default=None,
        help="GarageBand patch suggestion (repeat in preference order)",
    )
    return parser


def _add_library_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--library",
        default=None,
        help="Library directory (default: SUNOFRIEND_LIBRARY or ~/.local/share/sunofriend/library)",
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Backward compatibility: `sunofriend <folder> --out-dir ...` still works.
    if argv and argv[0] not in _COMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "remake")

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "listen":
            return _run_listen(args)
        if args.command == "listen-all":
            return _run_listen_all(args)
        if args.command == "evaluate":
            return _run_evaluate(args)
        if args.command == "doctor":
            return _run_doctor()
        if args.command == "preview":
            return _run_preview(args)
        if args.command == "midi-ports":
            return _run_midi_ports()
        if args.command == "play":
            return _run_play(args)
        if args.command == "midi-tempo":
            return _run_midi_tempo(args)
        if args.command == "garageband-info":
            return _run_garageband_info(args)
        if args.command == "clip-import":
            return _run_clip_import(args)
        if args.command == "clip-list":
            return _run_clip_list(args)
        if args.command == "clip-show":
            return _run_clip_show(args)
        if args.command == "clip-export":
            return _run_clip_export(args)
        if args.command == "clip-transform":
            return _run_clip_transform(args)
        if args.command == "clip-instrument":
            return _run_clip_instrument(args)
        result = run_remake(
            input_folder=Path(args.input_folder),
            out_dir=Path(args.out_dir),
            style=args.style,
            bpm=args.bpm,
            key=args.key,
        )
    except Exception as exc:
        parser.exit(2, f"sunofriend: {exc}\n")
    for path in result.files:
        print(path)
    return 0


def _run_listen(args) -> int:
    from .loop import refine_stem
    from .render import is_available

    if not is_available():
        print(
            "sunofriend: FluidSynth or a GM SoundFont is missing.\n"
            "  macOS: brew install fluid-synth && install GeneralUser-GS.sf2, then\n"
            "         run `sunofriend doctor` (see README for the default path)",
            file=sys.stderr,
        )
        return 2

    mode_out = Path(args.out_dir) / f"mode_{args.conversion_mode}"
    result = refine_stem(
        stem_path=args.stem,
        kind=args.kind,
        bpm=args.bpm,
        out_dir=mode_out,
        max_iterations=args.max_iterations,
        keep_workdir=args.keep_workdir,
        chords_pdf=args.chords_pdf,
        key=args.key,
        metronome=args.metronome,
        conversion_mode=args.conversion_mode,
    )
    print(f"final score: {result.score:.4f} after {len(result.history)} iteration(s)")
    for record in result.history:
        print(f"  iter {record.iteration:>3}  score={record.score:<8} notes={record.note_count:<5} {record.detail}")
    publication = _publish_single_result(
        result,
        stem=Path(args.stem),
        kind=args.kind,
        bpm=args.bpm,
        conversion_mode=args.conversion_mode,
        out_dir=mode_out,
    )
    print(result.midi_path)
    if not args.no_evaluate:
        try:
            from .evaluate import evaluate_stem_midi, v2_pitch_family_map

            report = evaluate_stem_midi(
                args.stem,
                result.notes,
                kind=args.kind,
                pitch_family_map=v2_pitch_family_map(args.kind),
            )
            report_path = mode_out / f"{args.kind}_evaluation.json"
            report_path.write_text(report.to_json() + "\n", encoding="utf-8")
            publication["evaluation"] = str(report_path)
            print(report_path)
            if args.evaluate_variants:
                for variant_name, details in publication["variants"].items():
                    variant_notes = result.variants[variant_name]
                    variant_report = evaluate_stem_midi(
                        args.stem,
                        variant_notes,
                        kind=args.kind,
                        pitch_family_map=v2_pitch_family_map(args.kind),
                    )
                    variant_path = mode_out / "variants" / (
                        f"{args.kind}-{variant_name.replace('_', '-')}.evaluation.json"
                    )
                    variant_path.write_text(
                        variant_report.to_json() + "\n",
                        encoding="utf-8",
                    )
                    details["evaluation"] = str(variant_path)
        except Exception as exc:
            publication["evaluation_warning"] = str(exc)
            print(f"evaluation warning: {exc}", file=sys.stderr)
    summary_path = mode_out / f"{args.kind}_conversion_summary.json"
    summary_path.write_text(json.dumps(publication, indent=2), encoding="utf-8")
    print(summary_path)
    return 0


def _publish_single_result(
    result,
    *,
    stem: Path,
    kind: str,
    bpm: float,
    conversion_mode: str,
    out_dir: Path,
) -> dict:
    """Publish one conversion with the same provenance/variant contract as batch."""

    from .conversion import (
        NoteProvenance,
        provenance_for_notes,
        retarget_note_provenance,
        write_note_provenance,
    )
    from .listen_all import CHANNELS, _remove_generated_part_artifacts, _safe_token
    from .midi import MidiTrack, write_midi_file
    from .note_safety import normalize_note_events

    out_dir.mkdir(parents=True, exist_ok=True)
    _remove_generated_part_artifacts(out_dir, kind, include_primary=False)
    records = [
        value for value in result.note_provenance if isinstance(value, NoteProvenance)
    ]
    if not records:
        origin = {
            "exact": "observed",
            "repair": "repaired",
            "reconstruct": "inferred",
        }[conversion_mode]
        records = provenance_for_notes(
            result.notes,
            origin=origin,
            confidence=max(0.0, min(1.0, float(result.score))),
            confidence_basis="aggregate",
            sources=("stem", f"listen-{kind}", f"mode:{conversion_mode}"),
            family=kind,
        )
    provenance_path = out_dir / f"{kind}_provenance.json"
    write_note_provenance(
        provenance_path,
        records,
        conversion_mode=conversion_mode,
        source_stem=stem,
        variant=kind,
    )

    variants: dict[str, dict] = {}
    variants_dir = out_dir / "variants"
    channel, program = CHANNELS.get(kind, (5, 0))
    for variant_name, raw_notes in sorted(result.variants.items()):
        notes = normalize_note_events(raw_notes)
        # Evaluation and callers must see the same intervals that the MIDI
        # writer and provenance sidecar receive, including shortened
        # same-pitch retriggers.
        result.variants[variant_name] = notes
        if not notes or variant_name in {"main", kind}:
            continue
        variant_path = variants_dir / f"{_safe_token(kind)}-{_safe_token(variant_name)}.mid"
        write_midi_file(
            variant_path,
            [MidiTrack(f"{kind.title()} {variant_name}", channel, program, notes)],
            bpm=bpm,
        )
        variant_records = [
            value
            for value in result.variant_provenance.get(variant_name, [])
            if isinstance(value, NoteProvenance)
        ]
        if variant_records:
            variant_records = retarget_note_provenance(notes, variant_records)
        else:
            variant_records = provenance_for_notes(
                notes,
                origin="observed" if "raw" in variant_name else "repaired",
                confidence=max(0.0, min(1.0, float(result.score))),
                confidence_basis="aggregate",
                tier="uncertain" if "uncertain" in variant_name else "main",
                sources=("stem", "variant", variant_name),
                family=variant_name,
            )
        variant_provenance = variants_dir / (
            f"{_safe_token(kind)}-{_safe_token(variant_name)}.provenance.json"
        )
        write_note_provenance(
            variant_provenance,
            variant_records,
            conversion_mode=conversion_mode,
            source_stem=stem,
            variant=variant_name,
        )
        variants[variant_name] = {
            "notes": len(notes),
            "midi": str(variant_path),
            "provenance": str(variant_provenance),
        }
    return {
        "conversion_mode": conversion_mode,
        "stem": str(stem),
        "kind": kind,
        "midi": str(result.midi_path),
        "provenance": str(provenance_path),
        "notes": len(result.notes),
        "variants": variants,
    }


def _run_listen_all(args) -> int:
    from .listen_all import run_listen_all
    from .render import is_available

    if not is_available():
        print("sunofriend: FluidSynth or a GM SoundFont is missing (see README).", file=sys.stderr)
        return 2
    parts = [p.strip() for p in args.parts.split(",")] if args.parts else None
    summary = run_listen_all(
        folder=args.input_folder,
        out_dir=args.out_dir,
        bpm=args.bpm,
        key=args.key,
        parts=parts,
        max_iterations=args.max_iterations,
        library=args.library,
        conversion_mode=args.conversion_mode,
        evaluate_outputs=not args.no_evaluate,
        evaluate_variants=args.evaluate_variants,
    )
    if "bpm_true" in summary:
        print(f"detected average bpm: {summary['bpm_true']} (downbeat at {summary['downbeat_offset']}s)")
    print(f"set GarageBand tempo to: {summary['set_garageband_tempo_to']}")
    if summary.get("arrangement"):
        print(summary["arrangement"])
    if summary.get("status") in {"failed", "no-output"}:
        return 2
    if summary.get("status") == "partial":
        return 1
    return 0


def _run_evaluate(args) -> int:
    from .evaluate import evaluate_stem_midi, v2_pitch_family_map

    report = evaluate_stem_midi(
        args.stem,
        args.midi,
        kind=args.kind,
        pitch_family_map=v2_pitch_family_map(args.kind),
    )
    midi = Path(args.midi)
    output = Path(args.out) if args.out else midi.with_suffix(".evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_json() + "\n", encoding="utf-8")
    print(
        "strong onset F1: "
        f"{report.onsets.strong.f1:.4f}; possible onset F1: "
        f"{report.onsets.possible.f1:.4f}; timing p95: "
        f"{report.onsets.timing.absolute_error_p95_ms} ms"
    )
    print(output)
    return 0


def _library_path(value: str | None) -> Path:
    configured = value or os.environ.get("SUNOFRIEND_LIBRARY")
    return Path(configured or "~/.local/share/sunofriend/library").expanduser()


def _run_doctor() -> int:
    from .playback import PlaybackError, list_output_ports
    from .render import RenderError, find_fluidsynth, find_soundfont

    result: dict = {"python": sys.version.split()[0], "packages": {}}
    for package in (
        "numpy", "librosa", "soundfile", "basic-pitch", "onnxruntime",
        "scikit-learn", "coremltools", "setuptools", "mido", "python-rtmidi",
    ):
        try:
            result["packages"][package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            result["packages"][package] = None
    try:
        result["fluidsynth"] = find_fluidsynth()
        result["soundfont"] = find_soundfont()
        from tempfile import TemporaryDirectory

        from .midi import MidiTrack, write_midi_file
        from .models import NoteEvent
        from .render import render_midi_to_wav

        with TemporaryDirectory(prefix="sunofriend_doctor_") as directory:
            midi = Path(directory) / "probe.mid"
            wav = Path(directory) / "probe.wav"
            write_midi_file(
                midi,
                [MidiTrack("Doctor", 0, 0, [NoteEvent(0.0, 0.1, 60, 90)])],
                bpm=120.0,
            )
            render_midi_to_wav(midi, wav)
            result["render_smoke_bytes"] = wav.stat().st_size
        result["render_ready"] = True
    except RenderError as exc:
        result["render_ready"] = False
        result["audio_error"] = str(exc)
    required = ("numpy", "librosa", "soundfile", "basic-pitch", "onnxruntime")
    result["missing_listen_packages"] = [
        package for package in required if result["packages"][package] is None
    ]
    result["listen_ready"] = result["render_ready"] and not result["missing_listen_packages"]
    try:
        result["midi_outputs"] = list_output_ports()
        result["midi_ready"] = bool(result["midi_outputs"])
        if not result["midi_ready"]:
            result["midi_error"] = (
                "No CoreMIDI outputs found. Enable an IAC Driver bus in Audio MIDI Setup."
            )
    except PlaybackError as exc:
        result["midi_outputs"] = []
        result["midi_ready"] = False
        result["midi_error"] = str(exc)
    result["ready"] = result["listen_ready"] and result["midi_ready"]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


def _run_preview(args) -> int:
    from .render import render_midi_to_wav

    midi = Path(args.midi)
    output = Path(args.out) if args.out else midi.with_suffix(".preview.wav")
    print(render_midi_to_wav(midi, output))
    return 0


def _run_midi_ports() -> int:
    from .playback import list_output_ports

    ports = list_output_ports()
    if not ports:
        print("No CoreMIDI outputs found. Enable the IAC Driver in Audio MIDI Setup.")
        return 1
    for port in ports:
        print(port)
    return 0


def _run_play(args) -> int:
    from .playback import play_midi

    try:
        port = play_midi(args.midi, args.port)
    except KeyboardInterrupt:
        print("MIDI playback stopped", file=sys.stderr)
        return 130
    print(f"played to: {port}")
    return 0


def _run_midi_tempo(args) -> int:
    from .midi_tempo import retime_midi_path

    results = retime_midi_path(
        args.input,
        target_bpm=args.target_bpm,
        source_bpm=args.source_bpm,
        output_path=args.out,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "operation": "midi-tempo",
                "file_count": len(results),
                "target_bpm": float(args.target_bpm),
                "set_garageband_tempo_to": float(args.target_bpm),
                "files": [result.to_dict() for result in results],
                "source_audio_alignment": (
                    "The retimed MIDI intentionally no longer matches the original "
                    "audio stems unless those stems are time-stretched by the same ratio."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_garageband_info(args) -> int:
    from .garageband import inspect_project

    print(json.dumps(inspect_project(args.project).to_dict(), indent=2, sort_keys=True))
    return 0


def _run_clip_import(args) -> int:
    from .clip import read_midi_clips
    from .library import ClipLibrary

    clips = list(
        read_midi_clips(args.midi, key=args.key, role=args.role, suggestions=args.suggest)
    )
    if not clips:
        raise ValueError("MIDI contains no note-bearing tracks")
    if args.track_index is not None:
        try:
            clips = [clips[args.track_index]]
        except IndexError as exc:
            raise ValueError(f"MIDI contains {len(clips)} note-bearing tracks") from exc
    library = ClipLibrary(_library_path(args.library))
    summaries = []
    for clip in clips:
        title = clip.title
        if args.title:
            title = args.title if len(clips) == 1 else f"{args.title} - {clip.title}"
        clip = replace(clip, title=title, tags=tuple(set(clip.tags) | set(args.tag))).with_content_id()
        summaries.append(asdict(library.add(clip)))
    print(json.dumps(summaries, indent=2, sort_keys=True))
    return 0


def _run_clip_list(args) -> int:
    from .library import ClipLibrary

    library = ClipLibrary(_library_path(args.library))
    rows = library.search(
        text=args.text,
        key=args.key,
        bpm=args.bpm,
        bpm_tolerance=args.bpm_tolerance,
        role=args.role,
        tags=args.tag,
        limit=args.limit,
    )
    print(json.dumps([asdict(row) for row in rows], indent=2, sort_keys=True))
    return 0


def _run_clip_show(args) -> int:
    from .library import ClipLibrary

    clip = ClipLibrary(_library_path(args.library)).get(args.clip_id)
    print(clip.to_json(indent=2))
    return 0


def _run_clip_export(args) -> int:
    from .clip import resolve_export_timing, write_clip_midi
    from .library import ClipLibrary

    clip = ClipLibrary(_library_path(args.library)).get(args.clip_id)
    timing_mode, export_bpm = resolve_export_timing(
        clip,
        timing_mode=args.timing_mode,
        garageband_bpm=args.garageband_bpm,
    )
    write_clip_midi(
        args.out,
        clip,
        timing_mode=args.timing_mode,
        garageband_bpm=args.garageband_bpm,
    )
    print(Path(args.out))
    print(f"timing mode: {timing_mode}")
    if timing_mode == "stem_locked":
        print(f"set GarageBand tempo to: {export_bpm:g}")
    else:
        print(f"musical tempo starts at: {export_bpm:g} BPM")
    return 0


def _run_clip_transform(args) -> int:
    from .clip import KeySignature, write_clip_midi
    from .library import ClipLibrary
    from .transform import remap_mode, retime_bpm, transpose, transpose_same_mode

    library = ClipLibrary(_library_path(args.library))
    clip = library.get(args.clip_id)
    staged_versions = []

    def stage(child):
        nonlocal clip
        staged_versions.append((clip.clip_id, child))
        clip = child

    if args.semitones is not None:
        stage(transpose(clip, args.semitones))
    elif args.target_key is not None:
        target = KeySignature.parse(args.target_key)
        if target is None or clip.key is None:
            raise ValueError("A target-key transformation requires source and target keys")
        if target.mode == clip.key.mode:
            stage(transpose_same_mode(clip, target.tonic, direction=args.direction))
        else:
            stage(remap_mode(clip, target.mode, target_tonic=target.tonic))
    if args.target_bpm is not None:
        stage(retime_bpm(clip, args.target_bpm, mode=args.timing_mode))
    if not staged_versions:
        raise ValueError("Choose --target-key, --semitones, and/or --target-bpm")

    # Build and validate the complete transform chain, then verify the optional
    # deliverable can be written, before committing any immutable versions.  A
    # bad later transform or an unwritable MIDI path must not leave half of the
    # requested history in the library.
    if args.out:
        write_clip_midi(args.out, clip)
    for parent_clip_id, child in staged_versions:
        library.add_version(parent_clip_id, child)
    print(json.dumps({"clip_id": clip.clip_id, "revision": clip.revision, "midi": args.out}, indent=2))
    return 0


def _run_clip_instrument(args) -> int:
    from .clip import Instrument, TransformRecipe
    from .library import ClipLibrary

    library = ClipLibrary(_library_path(args.library))
    clip = library.get(args.clip_id)
    current = clip.instrument
    if all(value is None for value in (args.role, args.program, args.channel, args.suggest)):
        raise ValueError("Choose --role, --program, --channel, and/or --suggest")
    instrument = Instrument(
        role=args.role or current.role,
        program=current.program if args.program is None else args.program,
        channel=current.channel if args.channel is None else args.channel,
        suggestions=current.suggestions if args.suggest is None else tuple(args.suggest),
    )
    recipe = TransformRecipe.create(
        "instrument_profile",
        previous_role=current.role,
        previous_program=current.program,
        previous_channel=current.channel,
        previous_suggestions=list(current.suggestions),
        role=instrument.role,
        program=instrument.program,
        channel=instrument.channel,
        suggestions=list(instrument.suggestions),
        source="user/GarageBand audition",
    )
    child = clip.child(recipe=recipe, instrument=instrument)
    library.add_version(clip.clip_id, child)
    print(json.dumps({"clip_id": child.clip_id, "revision": child.revision}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
