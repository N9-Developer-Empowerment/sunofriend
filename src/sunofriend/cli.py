from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import run_remake

_COMMANDS = {"remake", "listen", "listen-all"}


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
    listen.add_argument("--bpm", type=float, required=True, help="Track BPM (from Suno/Moises metadata)")
    listen.add_argument("--out-dir", required=True, help="Output directory")
    listen.add_argument("--max-iterations", type=int, default=30)
    listen.add_argument("--keep-workdir", action="store_true", help="Keep per-iteration MIDI/WAV files")
    listen.add_argument(
        "--chords-pdf",
        default=None,
        help="Moises chords PDF: enables theory-constrained 'imagine' mode for bass/lead/synth "
        "(compose in-key, on-grid, chord-aware; stem supplies rhythm + pitch hints)",
    )
    listen.add_argument("--key", default=None, help='Key override, e.g. "C minor" (default: from chords PDF)')
    listen.add_argument("--metronome", default=None, help="Metronome stem WAV: derive the true beat grid from clicks")

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
    listen_all.add_argument("--max-iterations", type=int, default=8)
    return parser


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
            "  macOS: brew install fluidsynth && download FluidR3_GM.sf2, then\n"
            "         export SUNOFRIEND_SF2=/path/to/FluidR3_GM.sf2",
            file=sys.stderr,
        )
        return 2

    result = refine_stem(
        stem_path=args.stem,
        kind=args.kind,
        bpm=args.bpm,
        out_dir=args.out_dir,
        max_iterations=args.max_iterations,
        keep_workdir=args.keep_workdir,
        chords_pdf=args.chords_pdf,
        key=args.key,
        metronome=args.metronome,
    )
    print(f"final score: {result.score:.4f} after {len(result.history)} iteration(s)")
    for record in result.history:
        print(f"  iter {record.iteration:>3}  score={record.score:<8} notes={record.note_count:<5} {record.detail}")
    print(result.midi_path)
    return 0


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
    )
    if "bpm_true" in summary:
        print(f"true bpm: {summary['bpm_true']} (downbeat at {summary['downbeat_offset']}s)")
    if summary.get("arrangement"):
        print(summary["arrangement"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
