from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

from . import __version__
from .ai_runtime import AI_REQUIREMENTS
from .diagnostics import CAPABILITIES
from .phrase_guide import GUIDE_KINDS
from .pipeline import run_remake

_COMMANDS = {
    "remake",
    "listen",
    "listen-all",
    "vocal-melody",
    "vocal-trackers",
    "melody-review",
    "melody-profile",
    "melody-guide",
    "melody-apply",
    "evaluate",
    "doctor",
    "ai-doctor",
    "ai-transcribe",
    "ai-matrix",
    "ai-cleanup",
    "midi-mask",
    "midi-role-split",
    "midi-role-split-resolve",
    "timbre-resynthesis",
    "preview",
    "midi-ports",
    "play",
    "midi-tempo",
    "midi-transform",
    "midi-anchor",
    "midi-align",
    "garageband-info",
    "instrument-inventory",
    "instrument-match",
    "sample-pack",
    "sample-pack-review",
    "sample-pack-apply",
    "sample-pack-boundary-review",
    "sample-pack-boundary-apply",
    "sample-pack-ab-review",
    "sample-pack-ab-resolve",
    "instrument-feedback",
    "instrument-profile",
    "instrument-bundle",
    "workbench",
    "clip-import",
    "clip-list",
    "clip-show",
    "clip-export",
    "clip-transform",
    "clip-instrument",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sunofriend",
        description="Clean GarageBand-ready MIDI from AI-generated stems.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    remake = sub.add_parser(
        "remake", help="Legacy grid-based remake of a Moises/Suno export folder"
    )
    remake.add_argument(
        "input_folder", help="Folder containing Moises stems and a chords PDF"
    )
    remake.add_argument(
        "--out-dir", required=True, help="Output directory for MIDI files and report"
    )
    remake.add_argument(
        "--style", default="edm", choices=["edm", "house", "trap", "hiphop"]
    )
    remake.add_argument(
        "--bpm", type=float, default=None, help="Override BPM if it cannot be inferred"
    )
    remake.add_argument("--key", default=None, help='Override key, e.g. "G major"')

    listen = sub.add_parser(
        "listen",
        help="Transcribe a stem by listening: transcribe -> render (FluidSynth GM proxy) -> compare -> refine",
    )
    listen.add_argument("stem", help="Path to a stem WAV file")
    listen.add_argument(
        "--kind",
        required=True,
        choices=[
            "kick",
            "snare",
            "hat",
            "cymbals",
            "toms",
            "other_kit",
            "keys",
            "piano",
            "synth",
            "lead",
            "pads",
            "bass",
        ],
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
    listen.add_argument(
        "--bpm", type=float, required=True, help="Track BPM (from Suno/Moises metadata)"
    )
    listen.add_argument("--out-dir", required=True, help="Output directory")
    listen.add_argument("--max-iterations", type=int, default=30)
    listen.add_argument(
        "--keep-workdir", action="store_true", help="Keep per-iteration MIDI/WAV files"
    )
    listen.add_argument(
        "--chords-pdf",
        default=None,
        help="Moises chords PDF: enables theory-constrained 'imagine' mode for bass/lead/synth/pads "
        "(compose in-key, on-grid, chord-aware; stem supplies rhythm + pitch hints)",
    )
    listen.add_argument(
        "--key",
        default=None,
        help='Key override, e.g. "C minor" (default: from chords PDF)',
    )
    listen.add_argument(
        "--metronome",
        default=None,
        help="Metronome stem WAV: derive the true beat grid from clicks",
    )
    listen.add_argument(
        "--conversion-mode",
        choices=["exact", "repair", "reconstruct"],
        default="repair",
        help=(
            "exact=strong observed evidence only; repair=confidence-backed corrections; "
            "reconstruct=allow clearly-labelled musical inference"
        ),
    )

    vocal = sub.add_parser(
        "vocal-melody",
        help="Extract an instrument-playable melody from lead or backing vocals",
    )
    vocal.add_argument("stem", help="Lead- or backing-vocal WAV stem")
    vocal.add_argument(
        "--role",
        required=True,
        choices=["lead", "backing"],
        help="Lead uses a continuous monophonic F0 contour; backing also tracks polyphonic voices",
    )
    vocal.add_argument("--out-dir", required=True, help="Output directory")
    vocal.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="GarageBand/export BPM (default: inferred from the parent folder)",
    )
    vocal.add_argument(
        "--tuning-hz",
        type=float,
        default=None,
        help="Concert A of the source, e.g. 429 (default: inferred from the parent folder, else 440)",
    )
    vocal.add_argument(
        "--key", default=None, help="Project key recorded in diagnostics"
    )
    vocal.add_argument(
        "--chords-pdf",
        default=None,
        help="Chord chart recorded in diagnostics; v1 does not force observed vocal notes onto it",
    )
    vocal.add_argument(
        "--metronome",
        default=None,
        help="Metronome stem for the gentle-quantized audition variant (auto-discovered when omitted)",
    )
    vocal.add_argument("--fmin", type=float, default=65.4, help="Lowest vocal F0 in Hz")
    vocal.add_argument(
        "--fmax", type=float, default=1046.5, help="Highest vocal F0 in Hz"
    )
    vocal.add_argument(
        "--tracker-mode",
        choices=["consensus", "pyin"],
        default="consensus",
        help="Fuse pYIN with Basic Pitch when available, or use pYIN alone",
    )
    vocal.add_argument(
        "--no-phrase-repair",
        action="store_true",
        help="Do not promote weak source notes supported by repeated phrases",
    )
    vocal.add_argument(
        "--muscriptor",
        action="store_true",
        help=(
            "Also run the optional local MuScriptor worker and publish its raw "
            "voice transcription as a separate GarageBand-ready variant"
        ),
    )
    vocal.add_argument(
        "--muscriptor-checkpoint",
        default=None,
        help=(
            "Existing accepted MuScriptor .safetensors checkpoint; defaults to "
            "SUNOFRIEND_MUSCRIPTOR_MODEL or the standard local small model"
        ),
    )
    vocal.add_argument(
        "--muscriptor-device",
        choices=("auto", "cpu", "mps"),
        default="cpu",
        help="MuScriptor inference device (default: cpu for short small-model clips)",
    )
    vocal.add_argument(
        "--muscriptor-python",
        default=None,
        help="AI interpreter (default: SUNOFRIEND_AI_PYTHON or .venv-ai)",
    )
    vocal.add_argument(
        "--muscriptor-timeout-seconds",
        type=float,
        default=1800.0,
        help="Kill the isolated MuScriptor worker after this many seconds",
    )
    vocal.add_argument(
        "--game",
        action="store_true",
        help=(
            "Also run the optional local GAME vocal worker and publish its "
            "seeded note-boundary transcription as a separate variant"
        ),
    )
    vocal.add_argument(
        "--game-model",
        default=None,
        help=(
            "Existing GAME ONNX bundle; defaults to SUNOFRIEND_GAME_MODEL or "
            "the pinned local v1.0.3 small bundle"
        ),
    )
    vocal.add_argument(
        "--game-language",
        choices=("auto", "en", "ja", "yue", "zh"),
        default="auto",
        help="GAME vocal language hint (default: universal/auto)",
    )
    vocal.add_argument(
        "--game-seed",
        type=int,
        default=0,
        help="GAME diffusion seed for reproducible boundaries (default: 0)",
    )
    vocal.add_argument(
        "--game-boundary-threshold",
        type=float,
        default=0.2,
        help="GAME note-boundary threshold (default: official 0.2)",
    )
    vocal.add_argument(
        "--game-boundary-radius-ms",
        type=float,
        default=20.0,
        help="GAME local boundary radius in milliseconds (default: 20)",
    )
    vocal.add_argument(
        "--game-presence-threshold",
        type=float,
        default=0.2,
        help="GAME voiced-note threshold (default: official 0.2)",
    )
    vocal.add_argument(
        "--game-steps",
        type=int,
        default=8,
        help="GAME D3PM segmentation steps (default: official 8)",
    )
    vocal.add_argument(
        "--game-python",
        default=None,
        help="AI interpreter (default: SUNOFRIEND_AI_PYTHON or .venv-ai)",
    )
    vocal.add_argument(
        "--game-timeout-seconds",
        type=float,
        default=1800.0,
        help="Kill the isolated GAME worker after this many seconds",
    )
    guide_input = vocal.add_mutually_exclusive_group()
    guide_input.add_argument(
        "--guide",
        default=None,
        help="Optional roughly hummed WAV guide recorded against the same song",
    )
    guide_input.add_argument(
        "--guide-snippet",
        action="append",
        nargs=3,
        default=[],
        metavar=("REFERENCE_WAV", "HUM_WAV", "START_SECONDS"),
        help=(
            "Repeatable short reference excerpt, matching hum, and the excerpt's "
            "start time in the full song"
        ),
    )
    vocal.add_argument(
        "--guide-offset-seconds",
        type=float,
        default=None,
        help="Known guide-to-song offset; otherwise Sunofriend searches ±8 seconds",
    )
    vocal.add_argument(
        "--prefer-guide",
        action="store_true",
        help=(
            "Publish the source-supported full guide, or the automatic melody "
            "patched by accepted snippets, as the primary MIDI"
        ),
    )
    vocal.add_argument(
        "--no-correction-report",
        action="store_true",
        help="Skip the local interactive HTML/JSON melody correction artifacts",
    )

    vocal_trackers = sub.add_parser(
        "vocal-trackers",
        help=(
            "Publish immutable pYIN and Basic Pitch evidence, scores, and an "
            "optional RMVPE consensus/agreed-F0 boundary repair"
        ),
    )
    vocal_trackers.add_argument("stem", help="Lead- or backing-vocal WAV stem")
    vocal_trackers.add_argument(
        "--role",
        required=True,
        choices=("lead", "backing"),
        help="Vocal role used for GarageBand channel and patch defaults",
    )
    vocal_trackers.add_argument(
        "--out-dir",
        required=True,
        help="Parent directory for a fresh immutable tracker run",
    )
    vocal_trackers.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="GarageBand BPM (default: inferred from the parent folder)",
    )
    vocal_trackers.add_argument(
        "--tuning-hz",
        type=float,
        default=None,
        help="Source concert A (default: parent-folder value, else 440)",
    )
    vocal_trackers.add_argument(
        "--fmin", type=float, default=65.4, help="Lowest vocal F0 in Hz"
    )
    vocal_trackers.add_argument(
        "--fmax", type=float, default=1046.5, help="Highest vocal F0 in Hz"
    )
    vocal_trackers.add_argument(
        "--rmvpe-frames",
        default=None,
        help=(
            "Existing rmvpe.frames.json from an immutable ai-transcribe run; "
            "when supplied, create an experimental three-tracker consensus"
        ),
    )
    vocal_trackers.add_argument(
        "--game-candidate",
        default=None,
        help=(
            "Existing GAME candidate.json from the exact same WAV; use its note "
            "boundaries only where pYIN and RMVPE agree on pitch"
        ),
    )
    vocal_trackers.add_argument(
        "--run-id",
        default=None,
        help="Optional unique reproducible test label; an existing run is never replaced",
    )

    melody_review = sub.add_parser(
        "melody-review",
        help="Build a local phrase-by-phrase audition and correction package",
    )
    melody_review.add_argument(
        "tracker_run",
        help="Completed lead vocal-trackers run directory or its run.json",
    )
    melody_review.add_argument(
        "--out-dir",
        required=True,
        help="Fresh output directory for HTML, MIDI, audio and evaluation files",
    )
    melody_review.add_argument(
        "--source-stem",
        default=None,
        help="Moved source WAV; its SHA-256 must match the tracker run",
    )
    melody_review.add_argument(
        "--padding-seconds",
        type=float,
        default=0.25,
        help="Context before and after each review unit, from 0 to 2 seconds",
    )
    melody_review.add_argument(
        "--minimum-bars",
        type=int,
        default=2,
        help="Preferred minimum review-unit length in bars (default: 2)",
    )
    melody_review.add_argument(
        "--maximum-bars",
        type=int,
        default=8,
        help="Maximum review-unit length before a cluster boundary (default: 8)",
    )
    melody_review.add_argument(
        "--beats-per-bar",
        type=int,
        default=4,
        help="Beats used to calculate bar duration; does not assert a downbeat",
    )
    melody_review.add_argument(
        "--ranking-profile",
        default=None,
        help="Optional local melody-profile JSON; advisory and never auto-selects",
    )

    melody_profile = sub.add_parser(
        "melody-profile",
        help="Build a local advisory profile from explicitly reviewed choices",
    )
    melody_profile.add_argument(
        "corrections",
        nargs="+",
        help="One or more melody-corrections-reviewed.json files",
    )
    melody_profile.add_argument(
        "--out",
        required=True,
        help="Fresh profile JSON path; existing files are never replaced",
    )

    melody_guide = sub.add_parser(
        "melody-guide",
        help="Add a source-supported short guide to one melody review unit",
    )
    melody_guide.add_argument(
        "review_package",
        help="Existing melody-review directory or its phrase_review.json",
    )
    melody_guide.add_argument(
        "--unit",
        type=int,
        required=True,
        help="One-based review-unit number to refine",
    )
    melody_guide.add_argument(
        "--guide",
        required=True,
        help="Short matching WAV: hum, whistle, contour, single note or taps",
    )
    melody_guide.add_argument(
        "--guide-kind",
        choices=GUIDE_KINDS,
        default="hum",
        help="How to interpret the short guide (default: hum)",
    )
    melody_guide.add_argument(
        "--search-seconds",
        type=float,
        default=0.75,
        help="Local timing-offset search radius from 0 to 2 seconds",
    )
    melody_guide.add_argument(
        "--out-dir",
        required=True,
        help="Fresh output directory; the parent review remains unchanged",
    )

    melody_apply = sub.add_parser(
        "melody-apply",
        help="Turn an edited Sunofriend melody-correction JSON file into MIDI",
    )
    melody_apply.add_argument("corrections", help="Exported correction JSON")
    melody_apply.add_argument("--out", required=True, help="New corrected MIDI file")

    listen_all = sub.add_parser(
        "listen-all",
        help="Process a whole Suno/Moises export folder: all stems -> MIDI + combined arrangement",
    )
    listen_all.add_argument(
        "input_folder", help="Export folder with stems (+ chords PDF, metronome)"
    )
    listen_all.add_argument("--out-dir", required=True, help="Output directory")
    listen_all.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Override BPM (default: from folder name)",
    )
    listen_all.add_argument(
        "--key",
        default=None,
        help="Override key (default: from folder name / chords PDF)",
    )
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
            "kick",
            "snare",
            "hat",
            "cymbals",
            "toms",
            "other_kit",
            "keys",
            "piano",
            "synth",
            "lead",
            "pads",
            "bass",
        ],
    )
    evaluate.add_argument(
        "--out",
        default=None,
        help="JSON report path (default: beside MIDI as *.evaluation.json)",
    )

    doctor = sub.add_parser(
        "doctor", help="Check the audio, ML, SoundFont, and CoreMIDI setup"
    )
    doctor.add_argument(
        "--require",
        choices=CAPABILITIES,
        default="all",
        help="Exit successfully when this capability is ready (default: all)",
    )

    ai_doctor = sub.add_parser(
        "ai-doctor",
        help="Check the isolated Python/PyTorch AI transcription and cleanup environment",
    )
    ai_doctor.add_argument(
        "--python",
        default=None,
        help=(
            "AI worker interpreter (default: SUNOFRIEND_AI_PYTHON or "
            ".venv-ai/bin/python)"
        ),
    )
    ai_doctor.add_argument(
        "--require",
        choices=AI_REQUIREMENTS,
        default="runtime",
        help="Exit successfully when this AI capability is ready (default: runtime)",
    )

    ai_transcribe = sub.add_parser(
        "ai-transcribe",
        help="Run an isolated local AI transcription and preserve an immutable record",
    )
    ai_transcribe.add_argument("audio", help="Source WAV or other local audio file")
    ai_transcribe.add_argument(
        "--backend",
        choices=("muscriptor", "game", "rmvpe", "pesto"),
        default="muscriptor",
        help="Optional local AI backend (default: muscriptor)",
    )
    ai_transcribe.add_argument(
        "--checkpoint",
        default=None,
        help=(
            "Existing local checkpoint, GAME bundle, RMVPE ONNX model or PESTO "
            "checkpoint; defaults to the backend's SUNOFRIEND_*_MODEL or "
            "standard local model"
        ),
    )
    ai_transcribe.add_argument(
        "--out-dir", required=True, help="Parent directory for a fresh immutable run"
    )
    ai_transcribe.add_argument(
        "--bpm", required=True, type=float, help="Tempo written into candidate.mid"
    )
    ai_transcribe.add_argument(
        "--instrument",
        action="append",
        default=[],
        help="Model role/instrument name (repeat where the backend supports it)",
    )
    ai_transcribe.add_argument(
        "--start-seconds", type=float, default=0.0, help="Optional excerpt start"
    )
    ai_transcribe.add_argument(
        "--end-seconds", type=float, default=None, help="Optional excerpt end"
    )
    ai_transcribe.add_argument(
        "--device",
        choices=("auto", "cpu", "mps"),
        default="auto",
        help="Inference device (default: MPS when available, otherwise CPU)",
    )
    ai_transcribe.add_argument(
        "--beam-size", type=int, default=1, help="MuScriptor decoding beam size"
    )
    ai_transcribe.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="MuScriptor inference batch size (default: pinned safe value 1)",
    )
    ai_transcribe.add_argument(
        "--cfg-coef",
        type=float,
        default=1.0,
        help="MuScriptor classifier-free guidance coefficient (default: 1.0)",
    )
    ai_transcribe.add_argument(
        "--model-size",
        choices=("auto", "small", "medium", "large"),
        default="auto",
        help="Validate the MuScriptor checkpoint variant (default: infer from config)",
    )
    ai_transcribe.add_argument(
        "--prelude-forcing",
        action="store_true",
        help=(
            "Request cross-chunk prelude forcing; rejected by the pinned "
            "MuScriptor 0.2.1 runtime, which does not support it"
        ),
    )
    ai_transcribe.add_argument(
        "--language",
        choices=("auto", "en", "ja", "yue", "zh"),
        default="auto",
        help="GAME vocal language hint (default: universal/auto)",
    )
    ai_transcribe.add_argument(
        "--boundary-threshold",
        type=float,
        default=0.2,
        help="GAME note-boundary threshold (default: official 0.2)",
    )
    ai_transcribe.add_argument(
        "--boundary-radius-ms",
        type=float,
        default=20.0,
        help="GAME local boundary radius in milliseconds (default: 20)",
    )
    ai_transcribe.add_argument(
        "--presence-threshold",
        type=float,
        default=0.2,
        help="GAME voiced-note threshold (default: official 0.2)",
    )
    ai_transcribe.add_argument(
        "--game-steps",
        type=int,
        default=8,
        help="GAME D3PM segmentation steps (default: official 8)",
    )
    ai_transcribe.add_argument(
        "--seed",
        type=int,
        default=0,
        help="GAME diffusion seed for reproducible boundaries (default: 0)",
    )
    ai_transcribe.add_argument(
        "--confidence-threshold",
        type=float,
        default=None,
        help=("Frame voiced-confidence threshold (default: RMVPE 0.03; PESTO 0.2)"),
    )
    ai_transcribe.add_argument(
        "--minimum-note-ms",
        type=float,
        default=80.0,
        help="F0 decoder minimum note length in milliseconds (default: 80)",
    )
    ai_transcribe.add_argument(
        "--maximum-gap-ms",
        type=float,
        default=50.0,
        help="F0 decoder maximum same-pitch unvoiced gap to bridge (default: 50)",
    )
    ai_transcribe.add_argument(
        "--pitch-change-semitones",
        type=float,
        default=0.75,
        help="F0 decoder pitch-change hysteresis in semitones (default: 0.75)",
    )
    ai_transcribe.add_argument(
        "--pesto-step-ms",
        type=float,
        default=10.0,
        help="PESTO frame step in milliseconds (default: 10)",
    )
    ai_transcribe.add_argument(
        "--pesto-reduction",
        choices=("alwa", "argmax", "mean"),
        default="alwa",
        help="PESTO pitch decoder (default: alwa)",
    )
    ai_transcribe.add_argument(
        "--pesto-chunks",
        type=int,
        default=1,
        help="PESTO inference chunks; increase to reduce memory (default: 1)",
    )
    ai_transcribe.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Kill the isolated worker after this many seconds (default: 1800)",
    )
    ai_transcribe.add_argument(
        "--python",
        default=None,
        help="AI interpreter (default: SUNOFRIEND_AI_PYTHON or .venv-ai)",
    )

    ai_cleanup = sub.add_parser(
        "ai-cleanup",
        help="Run a pinned local learned target/residual cleanup challenger",
    )
    ai_cleanup.add_argument("audio", help="Unchanged source stem WAV")
    ai_cleanup.add_argument(
        "--target",
        choices=("bass", "drums", "other", "vocals"),
        required=True,
        help="Broad htdemucs source family to isolate",
    )
    ai_cleanup.add_argument(
        "--checkpoint",
        default=None,
        help=(
            "Existing pinned htdemucs .th checkpoint (default: "
            "SUNOFRIEND_DEMUCS_MODEL or standard local model)"
        ),
    )

    ai_matrix = sub.add_parser(
        "ai-matrix",
        help="Build a deterministic Phase 5 report from immutable AI run directories",
    )
    ai_matrix.add_argument(
        "--lane",
        action="append",
        required=True,
        metavar="LANE=RUN_DIR",
        help=(
            "Explicit matrix lane and completed immutable run; repeat for M0, "
            "M1, M2, M3-role and other planned lanes"
        ),
    )
    ai_matrix.add_argument(
        "--out", required=True, help="Fresh path for the path-free matrix JSON report"
    )
    ai_matrix.add_argument(
        "--boundary-tolerance-ms",
        type=float,
        default=80.0,
        help="Window around each local five-second chunk boundary (default: 80ms)",
    )
    ai_matrix.add_argument(
        "--overlap-tolerance-ms",
        type=float,
        default=80.0,
        help="Onset tolerance for cross-lane same-pitch diagnostics (default: 80ms)",
    )
    ai_cleanup.add_argument(
        "--out-dir", required=True, help="Fresh immutable experiment directory"
    )
    ai_cleanup.add_argument(
        "--start-seconds", type=float, default=0.0, help="Excerpt start in source time"
    )
    ai_cleanup.add_argument(
        "--end-seconds",
        type=float,
        default=None,
        help="Excerpt end in source time; excerpts are limited to 60 seconds",
    )
    ai_cleanup.add_argument(
        "--overlap",
        type=float,
        default=0.25,
        help="Demucs split overlap from 0 up to (not including) 1 (default: 0.25)",
    )
    ai_cleanup.add_argument(
        "--timeout-seconds",
        type=float,
        default=1800.0,
        help="Kill the isolated worker after this many seconds (default: 1800)",
    )
    ai_cleanup.add_argument(
        "--python",
        default=None,
        help="AI interpreter (default: SUNOFRIEND_AI_PYTHON or .venv-ai)",
    )

    midi_mask = sub.add_parser(
        "midi-mask",
        help="Build an experimental MIDI-guided target/residual audio excerpt",
    )
    midi_mask.add_argument("audio", help="Unchanged source stem WAV")
    midi_mask.add_argument("midi", help="Aligned note-bearing guide MIDI")
    midi_mask.add_argument(
        "--track-index",
        type=int,
        default=None,
        help="Zero-based note-bearing track index; required for multi-track MIDI",
    )
    midi_mask.add_argument(
        "--start-seconds", type=float, default=0.0, help="Excerpt start in source time"
    )
    midi_mask.add_argument(
        "--end-seconds",
        type=float,
        default=None,
        help="Excerpt end in source time; excerpts are limited to 60 seconds",
    )
    midi_mask.add_argument(
        "--harmonics",
        type=int,
        default=8,
        help="Number of guide-note harmonics from 1 to 32 (default: 8)",
    )
    midi_mask.add_argument(
        "--bandwidth-cents",
        type=float,
        default=55.0,
        help="Gaussian width around each harmonic from 10 to 200 cents (default: 55)",
    )
    midi_mask.add_argument(
        "--attack-seconds",
        type=float,
        default=0.06,
        help="Mask fade-in before each guide note from 0 to 1 second",
    )
    midi_mask.add_argument(
        "--release-seconds",
        type=float,
        default=0.12,
        help="Mask fade-out after each guide note from 0 to 2 seconds",
    )
    midi_mask.add_argument(
        "--transient-ms",
        type=float,
        default=0.0,
        help="Optional broadband window after guide onsets from 0 to 250 ms",
    )
    midi_mask.add_argument(
        "--transient-strength",
        type=float,
        default=0.35,
        help="Broadband transient-mask level from 0 to 1 (default: 0.35)",
    )
    midi_mask.add_argument(
        "--n-fft",
        type=int,
        default=4096,
        help="Power-of-two FFT size from 512 to 8192 (default: 4096)",
    )
    midi_mask.add_argument(
        "--hop-length",
        type=int,
        default=512,
        help="STFT hop in samples, no larger than n-fft (default: 512)",
    )
    midi_mask.add_argument(
        "--out-dir", required=True, help="Fresh output directory; never overwritten"
    )

    midi_role_split = sub.add_parser(
        "midi-role-split",
        help="Build reviewable body/pluck MIDI tracks from explicit event-cluster evidence",
    )
    midi_role_split.add_argument("primary_midi", help="Accepted primary note-bearing MIDI")
    midi_role_split.add_argument(
        "clusters", help="Matching source_event_clusters.json from instrument-match"
    )
    midi_role_split.add_argument(
        "--body-cluster",
        required=True,
        help="Explicit retained body cluster, e.g. I1; never selected automatically",
    )
    midi_role_split.add_argument(
        "--secondary-midi",
        default=None,
        help="Optional independently transcribed residual/pluck MIDI",
    )
    midi_role_split.add_argument(
        "--secondary-audio",
        default=None,
        help="Optional secondary audio copied into the local listening review",
    )
    midi_role_split.add_argument(
        "--cleanup-review",
        default=None,
        help="Optional explicitly reviewed ai-cleanup JSON to pin as provenance",
    )
    midi_role_split.add_argument(
        "--body-name", default="Synth Bass Body", help="Body MIDI track name"
    )
    midi_role_split.add_argument(
        "--body-program",
        type=int,
        default=39,
        help="Zero-based GM body audition program (default: 39, Synth Bass 2)",
    )
    midi_role_split.add_argument(
        "--pluck-name",
        default="Plucked Bass Challenger",
        help="Pluck MIDI track name",
    )
    midi_role_split.add_argument(
        "--pluck-program",
        type=int,
        default=28,
        help="Zero-based GM pluck audition program (default: 28, Muted Guitar)",
    )
    midi_role_split.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip FluidSynth WAV rendering; MIDI and review evidence are still written",
    )
    midi_role_split.add_argument(
        "--out-dir", required=True, help="Fresh output directory; never overwritten"
    )

    midi_role_split_resolve = sub.add_parser(
        "midi-role-split-resolve",
        help="Resolve a complete user-exported role-split review",
    )
    midi_role_split_resolve.add_argument(
        "review", help="Reviewed midi_role_split_review JSON exported by the page"
    )
    midi_role_split_resolve.add_argument(
        "role_split_dir", help="Unchanged source midi-role-split directory"
    )
    midi_role_split_resolve.add_argument(
        "--out-dir", required=True, help="Fresh resolution directory"
    )

    timbre_resynthesis = sub.add_parser(
        "timbre-resynthesis",
        help="Compare one fixed monophonic MIDI through consistent timbres",
    )
    timbre_resynthesis.add_argument(
        "source_audio", help="Aligned source/reference WAV excerpt"
    )
    timbre_resynthesis.add_argument(
        "midi", help="Accepted fixed monophonic MIDI for every candidate"
    )
    timbre_resynthesis.add_argument(
        "--gm-program",
        type=int,
        default=39,
        help="Zero-based complete GM control program (default: 39, Synth Bass 2)",
    )
    timbre_resynthesis.add_argument(
        "--source-soundfont",
        default=None,
        help="Optional earlier source-derived SF2 comparison",
    )
    timbre_resynthesis.add_argument(
        "--source-soundfont-program",
        type=int,
        default=0,
        help="Zero-based preset in the source-derived SF2 (default: 0)",
    )
    timbre_resynthesis.add_argument(
        "--harmonics",
        type=int,
        default=16,
        help="Fitted harmonic count from 1 to 64 (default: 16)",
    )
    timbre_resynthesis.add_argument(
        "--attack-ms",
        type=float,
        default=8.0,
        help="Consistent synthesized attack in milliseconds (default: 8)",
    )
    timbre_resynthesis.add_argument(
        "--release-ms",
        type=float,
        default=45.0,
        help="Consistent synthesized release in milliseconds (default: 45)",
    )
    timbre_resynthesis.add_argument(
        "--out-dir", required=True, help="Fresh review directory; never overwritten"
    )

    preview = sub.add_parser(
        "preview", help="Render a MIDI file to WAV with FluidSynth"
    )
    preview.add_argument("midi", help="MIDI file to render")
    preview.add_argument(
        "--out", default=None, help="Output WAV (default: beside the MIDI file)"
    )
    preview.add_argument(
        "--soundfont",
        default=None,
        help=(
            "Optional local SF2 bank, including a Sunofriend sample instrument "
            "(default: configured General MIDI SoundFont)"
        ),
    )

    sub.add_parser(
        "midi-ports", help="List CoreMIDI outputs, including enabled IAC buses"
    )
    play = sub.add_parser(
        "play", help="Play MIDI to GarageBand or hardware through CoreMIDI"
    )
    play.add_argument("midi", help="MIDI file to play")
    play.add_argument(
        "--port", default=None, help="Exact name or unique part of a MIDI output name"
    )

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

    midi_transform = sub.add_parser(
        "midi-transform",
        help="Transpose and retime complete MIDI files without rebuilding their events",
    )
    midi_transform.add_argument(
        "input",
        help="One .mid/.midi file, or a directory to process recursively",
    )
    midi_transform.add_argument(
        "--out",
        required=True,
        help="Output MIDI path for a file, or output directory for a directory",
    )
    midi_transform.add_argument(
        "--semitones",
        type=int,
        default=0,
        help="Transpose pitched channels; General MIDI drum channel 10 is unchanged",
    )
    midi_transform.add_argument(
        "--source-bpm",
        "--from-bpm",
        dest="source_bpm",
        type=float,
        default=None,
        help="Optional safety check for the embedded starting tempo",
    )
    midi_transform.add_argument(
        "--target-bpm",
        "--to-bpm",
        dest="target_bpm",
        type=float,
        default=None,
        help="New exact musical tempo; unchanged when omitted",
    )
    midi_transform.add_argument(
        "--concert-pitch",
        action="store_true",
        help="Remove a safely recognised Sunofriend source-tuning bend for A=440 use",
    )
    midi_transform.add_argument(
        "--max-tuning-cents",
        type=float,
        default=100.0,
        help="Largest constant bend eligible for concert-pitch cleanup (default: 100)",
    )
    midi_transform.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing destination MIDI files",
    )

    midi_anchor = sub.add_parser(
        "midi-anchor",
        help="Put a song downbeat on a common bar while preserving all tempo wander",
    )
    midi_anchor.add_argument(
        "input",
        help="One .mid/.midi file, or a directory to process recursively",
    )
    midi_anchor.add_argument(
        "--out",
        required=True,
        help="Output MIDI path for a file, or output directory for a directory",
    )
    midi_anchor.add_argument(
        "--source-downbeat-seconds",
        type=float,
        required=True,
        help="Time of the source song's confirmed first downbeat",
    )
    midi_anchor.add_argument(
        "--source-bpm",
        "--from-bpm",
        dest="source_bpm",
        type=float,
        required=True,
        help="BPM embedded in the source MIDI",
    )
    midi_anchor.add_argument(
        "--target-bpm",
        "--to-bpm",
        dest="target_bpm",
        type=float,
        required=True,
        help="Exact output tempo to use in GarageBand",
    )
    midi_anchor.add_argument(
        "--target-downbeat-beat",
        type=float,
        default=4.0,
        help="Output beat for the downbeat (default: 4, start of bar 2 in 4/4)",
    )
    midi_anchor.add_argument(
        "--semitones",
        type=int,
        default=0,
        help="Transpose pitched channels; General MIDI drum channel 10 is unchanged",
    )
    midi_anchor.add_argument(
        "--concert-pitch",
        action="store_true",
        help="Remove a safely recognised Sunofriend source-tuning bend for A=440 use",
    )
    midi_anchor.add_argument(
        "--max-tuning-cents",
        type=float,
        default=100.0,
        help="Largest constant bend eligible for concert-pitch cleanup (default: 100)",
    )
    midi_anchor.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing destination MIDI files",
    )

    midi_align = sub.add_parser(
        "midi-align",
        help="Map stem-derived MIDI onto an exact straight bar grid for mashups",
    )
    midi_align.add_argument(
        "input",
        help="One .mid/.midi file, or a directory to process recursively",
    )
    midi_align.add_argument(
        "--metronome",
        required=True,
        help="Source song's metronome WAV, used as the tempo-wander map",
    )
    midi_align.add_argument(
        "--source-bpm",
        "--from-bpm",
        dest="source_bpm",
        type=float,
        required=True,
        help="BPM embedded in the source MIDI",
    )
    midi_align.add_argument(
        "--target-bpm",
        "--to-bpm",
        dest="target_bpm",
        type=float,
        required=True,
        help="Exact output tempo to use in GarageBand",
    )
    midi_align.add_argument(
        "--semitones",
        type=int,
        default=0,
        help="Transpose pitched channels; General MIDI drum channel 10 is unchanged",
    )
    midi_align.add_argument(
        "--count-in-bars",
        type=float,
        default=1.0,
        help="Bars before the detected first downbeat (default: 1, preserving pickups)",
    )
    midi_align.add_argument(
        "--beats-per-bar",
        type=int,
        default=4,
        help="Time-signature numerator (currently must be 4)",
    )
    midi_align.add_argument(
        "--source-downbeat-beat",
        type=int,
        default=0,
        help=(
            "Detected grid-beat number of the first true downbeat (default: 0); "
            "use this when the metronome begins with pickup clicks"
        ),
    )
    midi_align.add_argument(
        "--out",
        default=None,
        help="Output MIDI path for a file, or output directory for a directory",
    )
    midi_align.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing destination MIDI files",
    )

    garageband = sub.add_parser(
        "garageband-info",
        help="Read tempo/key/instrument evidence from a .band project",
    )
    garageband.add_argument("project", help="Path to a GarageBand .band bundle")

    instrument_inventory = sub.add_parser(
        "instrument-inventory",
        help="List installed GarageBand factory assets and Audio Unit instruments",
    )
    instrument_inventory.add_argument(
        "--out", default=None, help="Also write the inventory to a new JSON file"
    )
    instrument_inventory.add_argument(
        "--garageband-root",
        default=None,
        help="Override the GarageBand sampler-assets directory",
    )
    instrument_inventory.add_argument(
        "--drum-root",
        default=None,
        help="Override the GarageBand/Logic drum-samples directory",
    )
    instrument_inventory.add_argument(
        "--garageband-instrument-root",
        default=None,
        help="Override the GarageBand sampler-instrument definitions directory",
    )
    instrument_inventory.add_argument(
        "--logic-instrument-root",
        default=None,
        help="Override the Logic sampler-instrument definitions directory",
    )
    instrument_inventory.add_argument(
        "--no-audio-units",
        action="store_true",
        help="Skip macOS Audio Unit discovery through auval",
    )

    instrument_match = sub.add_parser(
        "instrument-match",
        help="Compare a stem with installed sounds and rendered instrument auditions",
    )
    instrument_match.add_argument("stem", help="Source stem WAV")
    instrument_match.add_argument("midi", help="Aligned note-bearing MIDI")
    instrument_match.add_argument(
        "--kind",
        required=True,
        choices=[
            "kick",
            "snare",
            "hat",
            "cymbals",
            "toms",
            "other_kit",
            "drums",
            "keys",
            "piano",
            "synth",
            "lead",
            "pads",
            "strings",
            "bass",
            "vocal",
            "vocals",
            "backing",
            "backing_vocals",
        ],
    )
    instrument_match.add_argument(
        "--out-dir", required=True, help="New directory for reports and auditions"
    )
    instrument_match.add_argument(
        "--top", type=int, default=5, help="Matches to retain per evidence path"
    )
    instrument_match.add_argument(
        "--track-index", type=int, default=None, help="Note-bearing MIDI track index"
    )
    instrument_match.add_argument(
        "--garageband-root",
        default=None,
        help="Override factory sampler-assets directory",
    )
    instrument_match.add_argument(
        "--drum-root",
        default=None,
        help="Override GarageBand/Logic drum-samples directory",
    )
    instrument_match.add_argument(
        "--no-factory",
        action="store_true",
        help="Skip installed factory-sample comparison",
    )
    instrument_match.add_argument(
        "--no-gm", action="store_true", help="Skip FluidSynth General MIDI auditions"
    )
    instrument_match.add_argument(
        "--all-programs",
        action="store_true",
        help="Render all 128 GM programs instead of a role-specific shortlist",
    )
    instrument_match.add_argument(
        "--max-source-segments",
        type=int,
        default=24,
        help="MIDI-aligned stem excerpts to profile",
    )
    instrument_match.add_argument(
        "--max-samples-per-asset",
        type=int,
        default=8,
        help="Factory samples to profile per asset",
    )
    instrument_match.add_argument(
        "--embedding-model",
        default=None,
        help=(
            "Optional local hash-pinned OpenL3 ONNX model for source-event clusters "
            "and a separate pitched-GM ranking; never downloads a model"
        ),
    )

    sample_pack = sub.add_parser(
        "sample-pack",
        help="Build a self-contained GarageBand SF2 instrument from aligned stem notes",
    )
    sample_pack.add_argument("stem", help="Source stem WAV you may legally sample")
    sample_pack.add_argument("midi", help="Aligned note-bearing MIDI")
    sample_pack.add_argument(
        "--kind",
        required=True,
        choices=[
            "kick",
            "snare",
            "hat",
            "cymbals",
            "toms",
            "other_kit",
            "drums",
            "keys",
            "piano",
            "synth",
            "lead",
            "pads",
            "strings",
            "bass",
            "vocal",
            "vocals",
            "backing",
            "backing_vocals",
        ],
    )
    sample_pack.add_argument(
        "--out-dir", required=True, help="New sample-pack directory"
    )
    sample_pack.add_argument(
        "--name",
        default=None,
        help="Instrument name embedded in the generated SoundFont",
    )
    sample_pack.add_argument(
        "--track-index", type=int, default=None, help="Note-bearing MIDI track index"
    )
    sample_pack.add_argument(
        "--max-samples", type=int, default=12, help="Maximum unique-pitch samples"
    )
    sample_pack.add_argument(
        "--tail-ms",
        type=float,
        default=120.0,
        help="Natural decay retained after each MIDI note",
    )
    sample_pack.add_argument(
        "--max-transpose",
        type=int,
        default=6,
        help="Maximum semitones each melodic sample may cover (default: 6)",
    )
    sample_pack.add_argument(
        "--allow-polyphonic",
        action="store_true",
        help="Allow zones containing overlapping notes (normally rejected)",
    )
    sample_pack.add_argument(
        "--no-preview",
        action="store_true",
        help="Create the SF2 and audition MIDI without rendering an audition WAV",
    )
    sample_pack.add_argument(
        "--no-auto-tune",
        action="store_true",
        help="Do not measure and correct stable sample pitch in the SF2",
    )
    sample_pack.add_argument(
        "--embedding-model",
        default=None,
        help=(
            "Optional local hash-pinned OpenL3 ONNX model for advisory source-event "
            "timbre clustering; never removes a sample automatically"
        ),
    )

    sample_pack_review = sub.add_parser(
        "sample-pack-review",
        help="Create a local listening review for v2 layer/alternate candidates",
    )
    sample_pack_review.add_argument(
        "sample_pack", help="Existing unchanged Sample Instrument v2 directory"
    )
    sample_pack_review.add_argument(
        "--out-dir", required=True, help="New unreviewed listening-review directory"
    )

    sample_pack_apply = sub.add_parser(
        "sample-pack-apply",
        help="Build a separate reviewed Sample Instrument v3 experiment",
    )
    sample_pack_apply.add_argument(
        "review", help="Explicitly reviewed JSON exported by sample-pack-review"
    )
    sample_pack_apply.add_argument(
        "--out-dir", required=True, help="New Sample Instrument v3 directory"
    )
    sample_pack_apply.add_argument(
        "--name", default=None, help="Instrument name embedded in generated banks"
    )
    sample_pack_apply.add_argument(
        "--no-preview",
        action="store_true",
        help="Build banks and audition MIDI without rendering A/B WAVs",
    )

    sample_boundary_review = sub.add_parser(
        "sample-pack-boundary-review",
        help="Compare single-sample and layered mappings without changing v3",
    )
    sample_boundary_review.add_argument(
        "sample_pack_v3", help="Existing completed Sample Instrument v3 directory"
    )
    sample_boundary_review.add_argument(
        "--out-dir", required=True, help="New unreviewed mapping-listening directory"
    )

    sample_boundary_apply = sub.add_parser(
        "sample-pack-boundary-apply",
        help="Regenerate v3 from an explicitly reviewed velocity-mapping export",
    )
    sample_boundary_apply.add_argument(
        "review", help="Reviewed JSON exported by sample-pack-boundary-review"
    )
    sample_boundary_apply.add_argument(
        "--out-dir", required=True, help="New mapping-reviewed v3 directory"
    )
    sample_boundary_apply.add_argument(
        "--name", default=None, help="Instrument name embedded in generated banks"
    )
    sample_boundary_apply.add_argument(
        "--no-preview",
        action="store_true",
        help="Build banks and audition MIDI without rendering A/B WAVs",
    )

    sample_ab_review = sub.add_parser(
        "sample-pack-ab-review",
        help="Create a blinded v2/v3 performance review for completed packs",
    )
    sample_ab_review.add_argument(
        "sample_pack_v3",
        nargs="+",
        help="One or more completed Sample Instrument v3 directories",
    )
    sample_ab_review.add_argument(
        "--out-dir", required=True, help="New blinded listening-review directory"
    )

    sample_ab_resolve = sub.add_parser(
        "sample-pack-ab-resolve",
        help="Resolve an explicitly reviewed blind export against its pinned key",
    )
    sample_ab_resolve.add_argument(
        "review", help="Reviewed JSON exported by sample-pack-ab-review"
    )
    sample_ab_resolve.add_argument(
        "--out", required=True, help="Fresh resolved Phase 3 result JSON"
    )

    instrument_feedback = sub.add_parser(
        "instrument-feedback",
        help="Record one explicit GarageBand/DAW patch listening decision",
    )
    instrument_feedback.add_argument(
        "bundle", help="Instrument Bundle v1 directory or instrument_bundle.json"
    )
    instrument_feedback.add_argument(
        "--patch", required=True, help="Exact patch name heard in the DAW"
    )
    instrument_feedback.add_argument(
        "--patch-source",
        choices=(
            "garageband-library",
            "audio-unit",
            "general-midi",
            "source-instrument",
            "other",
        ),
        default="garageband-library",
        help="Where the patch came from (default: garageband-library)",
    )
    instrument_feedback.add_argument(
        "--decision",
        choices=("preferred", "acceptable", "rejected"),
        default="preferred",
        help="Explicit listening decision (default: preferred)",
    )
    instrument_feedback.add_argument(
        "--context",
        choices=("full-mix", "solo"),
        default="full-mix",
        help="Listening context (default: full-mix)",
    )
    instrument_feedback.add_argument(
        "--compared-with",
        action="append",
        default=[],
        help="Patch or source instrument compared against; repeat as needed",
    )
    instrument_feedback.add_argument(
        "--notes", default=None, help="Optional concise listening notes"
    )
    instrument_feedback.add_argument(
        "--out", required=True, help="Fresh reviewed feedback JSON path"
    )

    instrument_profile = sub.add_parser(
        "instrument-profile",
        help="Build a local advisory patch profile from explicit feedback",
    )
    instrument_profile.add_argument(
        "feedback", nargs="+", help="One or more reviewed instrument-feedback JSONs"
    )
    instrument_profile.add_argument(
        "--out", required=True, help="Fresh profile JSON path"
    )

    instrument_bundle = sub.add_parser(
        "instrument-bundle",
        help="Package MIDI, carried source sound, match evidence, and A/B previews",
    )
    instrument_bundle.add_argument(
        "stem", help="Source stem WAV you may legally sample"
    )
    instrument_bundle.add_argument("midi", help="Aligned note-bearing MIDI")
    instrument_bundle.add_argument(
        "--kind",
        required=True,
        choices=[
            "kick",
            "snare",
            "hat",
            "cymbals",
            "toms",
            "other_kit",
            "drums",
            "keys",
            "piano",
            "synth",
            "lead",
            "pads",
            "strings",
            "bass",
            "vocal",
            "vocals",
            "backing",
            "backing_vocals",
        ],
    )
    instrument_bundle.add_argument("--out-dir", required=True)
    instrument_bundle.add_argument("--name", default=None)
    instrument_bundle.add_argument("--track-index", type=int, default=None)
    instrument_bundle.add_argument("--top", type=int, default=5)
    instrument_bundle.add_argument("--garageband-root", default=None)
    instrument_bundle.add_argument("--drum-root", default=None)
    instrument_bundle.add_argument("--max-samples", type=int, default=12)
    instrument_bundle.add_argument("--tail-ms", type=float, default=120.0)
    instrument_bundle.add_argument("--max-transpose", type=int, default=6)
    instrument_bundle.add_argument("--no-factory", action="store_true")
    instrument_bundle.add_argument("--no-gm", action="store_true")
    instrument_bundle.add_argument("--no-source-audio", action="store_true")
    instrument_bundle.add_argument("--no-source-instrument", action="store_true")
    instrument_bundle.add_argument("--no-preview", action="store_true")
    instrument_bundle.add_argument("--allow-polyphonic", action="store_true")
    instrument_bundle.add_argument("--no-auto-tune", action="store_true")
    instrument_bundle.add_argument(
        "--embedding-model",
        default=None,
        help="Optional local hash-pinned OpenL3 ONNX model for match evidence",
    )
    instrument_bundle.add_argument(
        "--preference-profile",
        default=None,
        help=(
            "Optional local instrument-profile JSON; advisory and never "
            "auto-selects or bypasses playability"
        ),
    )

    workbench = sub.add_parser(
        "workbench",
        help="Open the local, offline MIDI candidate decision workbench",
    )
    workbench.add_argument(
        "project", help="Directory containing top-level source audio stems"
    )
    workbench.add_argument(
        "--candidate-root",
        action="append",
        default=[],
        help=(
            "Narrow local directory containing existing MIDI/preview alternatives; "
            "repeat as needed"
        ),
    )
    workbench.add_argument(
        "--catalog",
        default=None,
        help="Optional explicit sunofriend.workbench-catalog.v1 JSON",
    )
    workbench.add_argument(
        "--state-dir",
        default=None,
        help=(
            "Local SQLite state directory (default: "
            "~/.local/share/sunofriend/workbench/PROJECT_ID)"
        ),
    )
    workbench.add_argument(
        "--port", type=int, default=0, help="Loopback port; 0 chooses a free port"
    )
    workbench.add_argument(
        "--open", action="store_true", help="Open the workbench in the default browser"
    )
    workbench.add_argument(
        "--soundfont",
        default=None,
        help=(
            "Optional GM SoundFont for cached neutral previews and arrangement "
            "auditions (default: SUNOFRIEND_SF2 or installed GeneralUser-GS)"
        ),
    )
    workbench.add_argument(
        "--inspect",
        action="store_true",
        help="Print the discovered path-free project catalog without starting a server",
    )

    clip_import = sub.add_parser(
        "clip-import", help="Import MIDI tracks into a Clip v1 library"
    )
    clip_import.add_argument("midi", help="MIDI file to import")
    _add_library_argument(clip_import)
    clip_import.add_argument("--key", default=None, help='Key override, e.g. "D minor"')
    clip_import.add_argument("--role", default=None, help="Instrument role override")
    clip_import.add_argument(
        "--suggest", action="append", default=[], help="Instrument suggestion"
    )
    clip_import.add_argument(
        "--tag", action="append", default=[], help="Searchable tag"
    )
    clip_import.add_argument(
        "--track-index", type=int, default=None, help="Import only this note track"
    )
    clip_import.add_argument(
        "--title", default=None, help="Title override (or prefix for multiple tracks)"
    )

    clip_list = sub.add_parser(
        "clip-list", help="Search/list the local Clip v1 library"
    )
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

    clip_export = sub.add_parser(
        "clip-export", help="Export one library clip as GarageBand MIDI"
    )
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
    key_change.add_argument(
        "--target-key", default=None, help='Target such as "G major"'
    )
    key_change.add_argument("--semitones", type=int, default=None)
    clip_transform.add_argument(
        "--direction", choices=["nearest", "up", "down"], default="nearest"
    )
    clip_transform.add_argument("--target-bpm", type=float, default=None)
    clip_transform.add_argument(
        "--timing-mode", choices=["musical", "stem_locked"], default="musical"
    )
    clip_transform.add_argument(
        "--out", default=None, help="Also export the final version to MIDI"
    )

    clip_instrument = sub.add_parser(
        "clip-instrument",
        help="Version a clip with chosen GarageBand instrument metadata",
    )
    clip_instrument.add_argument("clip_id")
    _add_library_argument(clip_instrument)
    clip_instrument.add_argument("--role", default=None)
    clip_instrument.add_argument("--program", type=int, default=None)
    clip_instrument.add_argument("--channel", type=int, default=None)
    clip_instrument.add_argument(
        "--suggest",
        action="append",
        default=None,
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
        if args.command == "vocal-melody":
            return _run_vocal_melody(args)
        if args.command == "vocal-trackers":
            return _run_vocal_trackers(args)
        if args.command == "melody-review":
            return _run_melody_review(args)
        if args.command == "melody-profile":
            return _run_melody_profile(args)
        if args.command == "melody-guide":
            return _run_melody_guide(args)
        if args.command == "melody-apply":
            return _run_melody_apply(args)
        if args.command == "evaluate":
            return _run_evaluate(args)
        if args.command == "doctor":
            return _run_doctor(args)
        if args.command == "ai-doctor":
            return _run_ai_doctor(args)
        if args.command == "ai-transcribe":
            return _run_ai_transcribe(args)
        if args.command == "ai-matrix":
            return _run_ai_matrix(args)
        if args.command == "ai-cleanup":
            return _run_ai_cleanup(args)
        if args.command == "midi-mask":
            return _run_midi_mask(args)
        if args.command == "midi-role-split":
            return _run_midi_role_split(args)
        if args.command == "midi-role-split-resolve":
            return _run_midi_role_split_resolve(args)
        if args.command == "timbre-resynthesis":
            return _run_timbre_resynthesis(args)
        if args.command == "preview":
            return _run_preview(args)
        if args.command == "midi-ports":
            return _run_midi_ports()
        if args.command == "play":
            return _run_play(args)
        if args.command == "midi-tempo":
            return _run_midi_tempo(args)
        if args.command == "midi-transform":
            return _run_midi_transform(args)
        if args.command == "midi-anchor":
            return _run_midi_anchor(args)
        if args.command == "midi-align":
            return _run_midi_align(args)
        if args.command == "garageband-info":
            return _run_garageband_info(args)
        if args.command == "instrument-inventory":
            return _run_instrument_inventory(args)
        if args.command == "instrument-match":
            return _run_instrument_match(args)
        if args.command == "sample-pack":
            return _run_sample_pack(args)
        if args.command == "sample-pack-review":
            return _run_sample_pack_review(args)
        if args.command == "sample-pack-apply":
            return _run_sample_pack_apply(args)
        if args.command == "sample-pack-boundary-review":
            return _run_sample_pack_boundary_review(args)
        if args.command == "sample-pack-boundary-apply":
            return _run_sample_pack_boundary_apply(args)
        if args.command == "sample-pack-ab-review":
            return _run_sample_pack_ab_review(args)
        if args.command == "sample-pack-ab-resolve":
            return _run_sample_pack_ab_resolve(args)
        if args.command == "instrument-feedback":
            return _run_instrument_feedback(args)
        if args.command == "instrument-profile":
            return _run_instrument_profile(args)
        if args.command == "instrument-bundle":
            return _run_instrument_bundle(args)
        if args.command == "workbench":
            return _run_workbench(args)
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
        print(
            f"  iter {record.iteration:>3}  score={record.score:<8} notes={record.note_count:<5} {record.detail}"
        )
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
                    variant_path = (
                        mode_out
                        / "variants"
                        / (
                            f"{args.kind}-{variant_name.replace('_', '-')}.evaluation.json"
                        )
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


def _run_vocal_melody(args) -> int:
    """Extract vocal pitch without treating words or vibrato as MIDI notes."""

    from .beatgrid import Grid, grid_from_metronome
    from .metadata import infer_project_metadata
    from .vocal import VocalConfig, transcribe_vocal_melody

    stem = Path(args.stem)
    if not stem.is_file():
        raise ValueError(f"Vocal stem does not exist: {stem}")
    metadata = infer_project_metadata(stem.parent)
    bpm = float(args.bpm if args.bpm is not None else (metadata.bpm or 0.0))
    if not bpm > 0:
        raise ValueError(
            "BPM was not provided and could not be inferred from the parent folder"
        )
    if args.tuning_hz is not None:
        tuning_hz = float(args.tuning_hz)
        tuning_source = "command-line"
    elif metadata.tuning_hz is not None:
        tuning_hz = float(metadata.tuning_hz)
        tuning_source = "parent-folder"
    else:
        tuning_hz = 440.0
        tuning_source = "default-a440"
    if not tuning_hz > 0:
        raise ValueError("tuning-hz must be positive")
    key = args.key or metadata.key

    metronome = (
        Path(args.metronome)
        if args.metronome
        else _find_exact_stem(stem.parent, "metronome")
    )
    if metronome is not None and not metronome.is_file():
        raise ValueError(f"Metronome stem does not exist: {metronome}")
    grid = (
        grid_from_metronome(str(metronome), nominal_bpm=bpm)
        if metronome is not None
        else Grid(bpm=bpm)
    )
    chords_pdf = (
        Path(args.chords_pdf)
        if args.chords_pdf
        else next(iter(sorted(stem.parent.glob("*chords*.pdf"))), None)
    )
    if chords_pdf is not None and not chords_pdf.is_file():
        raise ValueError(f"Chord PDF does not exist: {chords_pdf}")

    config = VocalConfig(
        role=args.role,
        tuning_hz=tuning_hz,
        tuning_source=tuning_source,
        bpm=bpm,
        fmin_hz=float(args.fmin),
        fmax_hz=float(args.fmax),
        tracker_mode=args.tracker_mode,
        phrase_repair=not args.no_phrase_repair,
    )
    result = transcribe_vocal_melody(stem, config=config, grid=grid)
    guide_alignment = None
    has_guide = bool(args.guide or args.guide_snippet)
    if args.prefer_guide and not has_guide:
        raise ValueError("--prefer-guide requires --guide or --guide-snippet")
    if args.guide_offset_seconds is not None and not args.guide:
        raise ValueError("--guide-offset-seconds requires --guide")
    if args.guide:
        from .melody_correction import add_hummed_guide_variant

        result, guide_alignment = add_hummed_guide_variant(
            result,
            args.guide,
            config=config,
            grid=grid,
            offset_seconds=args.guide_offset_seconds,
            prefer_guide=args.prefer_guide,
        )
    elif args.guide_snippet:
        from .melody_correction import add_hummed_snippet_variants

        snippets = []
        for reference, hum, start_value in args.guide_snippet:
            try:
                start_seconds = float(start_value)
            except ValueError as exc:
                raise ValueError(
                    "--guide-snippet START_SECONDS must be a number"
                ) from exc
            snippets.append((reference, hum, start_seconds))
        result, guide_alignment = add_hummed_snippet_variants(
            result,
            snippets,
            config=config,
            grid=grid,
            prefer_guide=args.prefer_guide,
        )
    summary = _publish_vocal_result(
        result,
        stem=stem,
        role=args.role,
        bpm=bpm,
        key=key,
        chords_pdf=chords_pdf,
        metronome=metronome,
        grid=grid,
        out_dir=Path(args.out_dir),
    )
    ai_challengers = {}
    if args.muscriptor:
        challenger = _publish_muscriptor_vocal_challenger(
            result=result,
            stem=stem,
            role=args.role,
            bpm=bpm,
            out_dir=Path(args.out_dir),
            checkpoint=args.muscriptor_checkpoint,
            device=args.muscriptor_device,
            python=args.muscriptor_python,
            timeout_seconds=args.muscriptor_timeout_seconds,
        )
        ai_challengers["muscriptor"] = challenger
        summary["variants"]["muscriptor"] = challenger
    if args.game:
        challenger = _publish_game_vocal_challenger(
            result=result,
            stem=stem,
            role=args.role,
            bpm=bpm,
            out_dir=Path(args.out_dir),
            model=args.game_model,
            language=args.game_language,
            seed=args.game_seed,
            boundary_threshold=args.game_boundary_threshold,
            boundary_radius_ms=args.game_boundary_radius_ms,
            presence_threshold=args.game_presence_threshold,
            steps=args.game_steps,
            python=args.game_python,
            timeout_seconds=args.game_timeout_seconds,
        )
        ai_challengers["game"] = challenger
        summary["variants"]["game"] = challenger
    if ai_challengers:
        summary["ai_challengers"] = ai_challengers
    if not args.no_correction_report:
        from .melody_correction import write_melody_correction_artifacts

        correction = write_melody_correction_artifacts(
            stem,
            result,
            out_dir=Path(args.out_dir),
            bpm=bpm,
            key=key,
            role=args.role,
            primary_midi=summary.get("primary_midi"),
            guide_alignment=guide_alignment,
        )
        summary["correction"] = correction
    if guide_alignment is not None:
        summary["guide_alignment"] = guide_alignment
    summary_path = Path(args.out_dir) / "vocal_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_vocal_trackers(args) -> int:
    """Preserve raw trackers before opt-in consensus and boundary repair."""

    from .metadata import infer_project_metadata
    from .vocal_trackers import run_vocal_tracker_bakeoff

    stem = Path(args.stem)
    if not stem.is_file():
        raise ValueError(f"Vocal stem does not exist: {stem}")
    metadata = infer_project_metadata(stem.parent)
    bpm = float(args.bpm if args.bpm is not None else (metadata.bpm or 0.0))
    if not bpm > 0:
        raise ValueError(
            "BPM was not provided and could not be inferred from the parent folder"
        )
    tuning_hz = float(
        args.tuning_hz if args.tuning_hz is not None else (metadata.tuning_hz or 440.0)
    )
    result = run_vocal_tracker_bakeoff(
        audio_path=stem,
        out_dir=args.out_dir,
        bpm=bpm,
        role=args.role,
        tuning_hz=tuning_hz,
        fmin_hz=float(args.fmin),
        fmax_hz=float(args.fmax),
        rmvpe_frames_path=args.rmvpe_frames,
        game_candidate_path=args.game_candidate,
        run_id=args.run_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_melody_review(args) -> int:
    """Publish a fresh recognition-first phrase review package."""

    from .phrase_review import build_melody_phrase_review

    result = build_melody_phrase_review(
        args.tracker_run,
        out_dir=args.out_dir,
        source_stem=args.source_stem,
        padding_seconds=args.padding_seconds,
        minimum_bars=args.minimum_bars,
        maximum_bars=args.maximum_bars,
        beats_per_bar=args.beats_per_bar,
        ranking_profile=args.ranking_profile,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_melody_profile(args) -> int:
    """Build a fresh local preference profile from explicit review choices."""

    from .melody_profile import build_personal_melody_profile

    result = build_personal_melody_profile(
        args.corrections,
        out_path=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_melody_guide(args) -> int:
    """Publish a fresh review package with one short-guide alternative."""

    from .phrase_review import build_guided_melody_phrase_review

    result = build_guided_melody_phrase_review(
        args.review_package,
        unit=args.unit,
        guide_path=args.guide,
        out_dir=args.out_dir,
        guide_kind=args.guide_kind,
        search_seconds=args.search_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _publish_muscriptor_vocal_challenger(
    *,
    result,
    stem: Path,
    role: str,
    bpm: float,
    out_dir: Path,
    checkpoint: str | None,
    device: str,
    python: str | None,
    timeout_seconds: float,
) -> dict:
    """Run MuScriptor as an explicit model-neutral vocal challenger."""

    from .ai_runtime import resolve_muscriptor_checkpoint

    return _publish_ai_vocal_challenger(
        result=result,
        stem=stem,
        role=role,
        bpm=bpm,
        out_dir=out_dir,
        backend="muscriptor",
        display_name="MuScriptor",
        model_path=resolve_muscriptor_checkpoint(checkpoint),
        options={"device": device, "beam_size": 1},
        python=python,
        timeout_seconds=timeout_seconds,
        description=(
            "MuScriptor voice challenger with a separate source-energy velocity "
            "layer, source-tuned for GarageBand."
        ),
    )


def _publish_game_vocal_challenger(
    *,
    result,
    stem: Path,
    role: str,
    bpm: float,
    out_dir: Path,
    model: str | None,
    language: str,
    seed: int,
    boundary_threshold: float,
    boundary_radius_ms: float,
    presence_threshold: float,
    steps: int,
    python: str | None,
    timeout_seconds: float,
) -> dict:
    """Run seeded GAME as an explicit vocal note-boundary challenger."""

    from .ai_runtime import resolve_game_model

    return _publish_ai_vocal_challenger(
        result=result,
        stem=stem,
        role=role,
        bpm=bpm,
        out_dir=out_dir,
        backend="game",
        display_name="GAME",
        model_path=resolve_game_model(model),
        options={
            "device": "cpu",
            "language": language,
            "seed": seed,
            "boundary_threshold": boundary_threshold,
            "boundary_radius_ms": boundary_radius_ms,
            "presence_threshold": presence_threshold,
            "game_steps": steps,
        },
        python=python,
        timeout_seconds=timeout_seconds,
        description=(
            "Seeded GAME singing-note boundary and floating-pitch challenger "
            "with a separate source-energy velocity layer, source-tuned for "
            "GarageBand."
        ),
    )


def _publish_ai_vocal_challenger(
    *,
    result,
    stem: Path,
    role: str,
    bpm: float,
    out_dir: Path,
    backend: str,
    display_name: str,
    model_path: Path,
    options: dict,
    python: str | None,
    timeout_seconds: float,
    description: str,
) -> dict:
    """Publish one isolated AI candidate without changing the primary melody."""

    from .ai_bakeoff import run_ai_transcription
    from .ai_runtime import AITranscriptionCandidate
    from .conversion import (
        NoteProvenance,
        retarget_note_provenance,
        write_note_provenance,
    )
    from .midi import MidiTrack, write_midi_file
    from .models import NoteEvent
    from .note_safety import normalize_note_events

    run_parent = out_dir / "ai-runs" / backend
    manifest = run_ai_transcription(
        audio_path=stem,
        out_dir=run_parent,
        checkpoint_path=model_path,
        bpm=bpm,
        backend=backend,
        roles=("voice",),
        options=options,
        python=python,
        timeout_seconds=timeout_seconds,
    )
    run_dir = run_parent / manifest["run_id"]
    candidate_path = run_dir / "candidate.json"
    candidate = AITranscriptionCandidate.from_dict(
        json.loads(candidate_path.read_text(encoding="utf-8"))
    )
    quality_path = run_dir / "candidate.quality.json"
    quality_document = (
        json.loads(quality_path.read_text(encoding="utf-8"))
        if quality_path.is_file()
        else None
    )
    expression_path = run_dir / "candidate.expression.json"
    expression_midi_path = run_dir / "candidate.expression.mid"
    expression_document = None
    expression_note_records: list[dict] = []
    recovered_velocities: list[int] | None = None
    if expression_path.is_file():
        from .ai_expression import expression_velocities

        expression_document = json.loads(expression_path.read_text(encoding="utf-8"))
        if expression_document.get("status") in {"complete", "no-evidence"}:
            recovered_velocities = expression_velocities(
                expression_document,
                expected_notes=len(candidate.notes),
            )
            expression_note_records = sorted(
                expression_document["notes"],
                key=lambda note: int(note["candidate_index"]),
            )
    raw_notes = [
        NoteEvent(
            start=float(note.start_seconds),
            end=float(note.end_seconds),
            pitch=int(round(note.pitch)),
            velocity=(
                recovered_velocities[index]
                if recovered_velocities is not None
                else (int(round(note.velocity)) if note.velocity is not None else 88)
            ),
        )
        for index, note in enumerate(candidate.notes)
    ]
    notes = normalize_note_events(raw_notes)
    token = "lead_vocal" if role == "lead" else "backing_vocal"
    variants_dir = out_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    midi_path = variants_dir / f"{token}-{backend}.mid"
    provenance_path = variants_dir / f"{token}-{backend}.provenance.json"
    channel, program = (2, 73) if role == "lead" else (3, 65)
    tuning_cents = float(result.diagnostics.garageband_fine_tune_cents)
    write_midi_file(
        midi_path,
        [
            MidiTrack(
                f"{role.title()} Vocal {display_name}",
                channel,
                program,
                notes,
                pitch_bend_cents=tuning_cents,
            )
        ],
        bpm=bpm,
    )
    records = []
    for index, (note, source) in enumerate(zip(raw_notes, candidate.notes)):
        expression_note = (
            expression_note_records[index]
            if index < len(expression_note_records)
            else None
        )
        records.append(
            NoteProvenance.from_note(
                note,
                origin="observed",
                confidence=(
                    float(source.confidence) if source.confidence is not None else 0.5
                ),
                confidence_basis=(
                    "measured" if source.confidence is not None else "policy"
                ),
                family="voice",
                sources=(backend,),
                details={
                    "source_event_id": source.source_event_id,
                    "model_instrument": source.instrument,
                    "raw_pitch": source.pitch,
                    "raw_velocity": source.velocity,
                    "recovered_velocity": (
                        expression_note.get("velocity") if expression_note else None
                    ),
                    "velocity_source": (
                        expression_note.get("velocity_source")
                        if expression_note
                        else "neutral-fallback"
                    ),
                    "run_id": manifest["run_id"],
                },
            )
        )
    write_note_provenance(
        provenance_path,
        retarget_note_provenance(
            notes,
            records,
            mark_changed_as_repaired=True,
        ),
        conversion_mode="repair",
        source_stem=stem,
        variant=backend,
    )
    published_status = "ok" if notes else "no-evidence"
    if quality_document and quality_document.get("status") == "review-required":
        published_status = "review-required"
    published = {
        "status": published_status,
        "backend": backend,
        "model_version": candidate.model_version,
        "model_metadata": dict(candidate.metadata),
        "notes": len(notes),
        "midi": str(midi_path) if notes else None,
        "provenance": str(provenance_path),
        "raw_candidate": str(candidate_path),
        "candidate_quality": str(quality_path) if quality_path.is_file() else None,
        "quality_status": (
            quality_document.get("status") if quality_document else None
        ),
        "quality_warnings": (
            quality_document.get("warnings", []) if quality_document else []
        ),
        "raw_midi": str(run_dir / "candidate.mid"),
        "source_expression": (
            str(expression_path) if expression_path.is_file() else None
        ),
        "source_expression_midi": (
            str(expression_midi_path) if expression_midi_path.is_file() else None
        ),
        "velocity_summary": (
            expression_document.get("velocity_summary") if expression_document else None
        ),
        "run_manifest": str(run_dir / "run.json"),
        "run_id": manifest["run_id"],
        "checkpoint_sha256": manifest["checkpoint"]["sha256"],
        "description": (
            description
            + " The raw model candidate remains untouched and the deterministic "
            "Sunofriend primary is unchanged."
        ),
        "selection_policy": "explicit challenger; never automatic primary",
        "metrics": _vocal_variant_metrics(
            notes,
            result.contour,
            result.diagnostics.tuning_hz,
        ),
    }
    analysis_path = out_dir / "vocal_analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["variants"][backend] = published
    analysis_path.write_text(
        json.dumps(analysis, indent=2, sort_keys=True), encoding="utf-8"
    )
    return published


def _run_melody_apply(args) -> int:
    from .melody_correction import apply_melody_corrections

    report = apply_melody_corrections(args.corrections, out_path=args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _find_exact_stem(folder: Path, token: str) -> Path | None:
    """Find an exact stem token without confusing vocals with backing_vocals."""

    marker = f"-{token}-"
    return next(
        (path for path in sorted(folder.glob("*.wav")) if marker in path.name.lower()),
        None,
    )


def _publish_vocal_result(
    result,
    *,
    stem: Path,
    role: str,
    bpm: float,
    key: str | None,
    chords_pdf: Path | None,
    metronome: Path | None,
    grid,
    out_dir: Path,
) -> dict:
    """Publish vocal variants, contour evidence, provenance, and diagnostics."""

    import csv

    from .conversion import retarget_note_provenance, write_note_provenance
    from .midi import MidiTrack, pitch_bend_value, write_midi_file
    from .note_safety import normalize_note_events

    token = "lead_vocal" if role == "lead" else "backing_vocal"
    out_dir.mkdir(parents=True, exist_ok=True)
    variants_dir = out_dir / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    for path in [
        out_dir / f"{token}_melody.mid",
        out_dir / f"{token}_provenance.json",
        out_dir / "vocal_contour.csv",
        out_dir / "vocal_analysis.json",
        out_dir / "vocal_summary.json",
    ]:
        path.unlink(missing_ok=True)
    for path in variants_dir.glob(f"{token}-*"):
        if path.is_file():
            path.unlink()

    contour_path = out_dir / "vocal_contour.csv"
    with contour_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "time_seconds",
                "f0_hz",
                "fractional_midi",
                "voiced_probability",
                "rms",
                "onset_strength",
                "source",
            ]
        )
        for frame in result.contour:
            midi_float = frame.fractional_midi(result.diagnostics.tuning_hz)
            writer.writerow(
                [
                    f"{frame.time:.6f}",
                    "" if frame.f0_hz is None else f"{frame.f0_hz:.6f}",
                    "" if midi_float is None else f"{midi_float:.6f}",
                    f"{frame.voiced_probability:.6f}",
                    f"{frame.rms:.9f}",
                    f"{frame.onset_strength:.6f}",
                    frame.source,
                ]
            )

    tuning_cents = float(result.diagnostics.garageband_fine_tune_cents)
    channel, program = (2, 73) if role == "lead" else (3, 65)
    published: dict[str, dict] = {}
    normalized_variants: dict[str, list] = {}
    for name, raw_notes in result.variants.items():
        notes = normalize_note_events(raw_notes)
        normalized_variants[name] = notes
        if not notes:
            published[name] = {
                "status": "no-evidence",
                "notes": 0,
                "description": result.descriptions.get(name),
            }
            continue
        midi_path = variants_dir / f"{token}-{name.replace('_', '-')}.mid"
        write_midi_file(
            midi_path,
            [
                MidiTrack(
                    f"{role.title()} Vocal {name.replace('_', ' ').title()}",
                    channel,
                    program,
                    notes,
                    pitch_bend_cents=tuning_cents,
                )
            ],
            bpm=bpm,
        )
        records = retarget_note_provenance(
            notes,
            result.provenance.get(name, []),
            mark_changed_as_repaired=True,
        )
        provenance_path = (
            variants_dir / f"{token}-{name.replace('_', '-')}.provenance.json"
        )
        mode = (
            "exact"
            if name in {"observed_strict", "harmony_stack", "uncertain"}
            else "repair"
        )
        write_note_provenance(
            provenance_path,
            records,
            conversion_mode=mode,
            source_stem=stem,
            variant=name,
        )
        published[name] = {
            "status": "ok",
            "notes": len(notes),
            "midi": str(midi_path),
            "provenance": str(provenance_path),
            "description": result.descriptions.get(name),
            "metrics": _vocal_variant_metrics(
                notes, result.contour, result.diagnostics.tuning_hz
            ),
        }

    primary_notes = normalized_variants.get(result.primary_variant, [])
    primary_midi = out_dir / f"{token}_melody.mid"
    primary_provenance = out_dir / f"{token}_provenance.json"
    if primary_notes:
        write_midi_file(
            primary_midi,
            [
                MidiTrack(
                    f"{role.title()} Vocal Melody",
                    channel,
                    program,
                    primary_notes,
                    pitch_bend_cents=tuning_cents,
                )
            ],
            bpm=bpm,
        )
        primary_records = retarget_note_provenance(
            primary_notes,
            result.provenance.get(result.primary_variant, []),
            mark_changed_as_repaired=True,
        )
        write_note_provenance(
            primary_provenance,
            primary_records,
            conversion_mode="repair",
            source_stem=stem,
            variant=result.primary_variant,
        )
        concert_path = variants_dir / f"{token}-concert-pitch.mid"
        write_midi_file(
            concert_path,
            [
                MidiTrack(
                    f"{role.title()} Vocal Concert Pitch",
                    channel,
                    program,
                    primary_notes,
                )
            ],
            bpm=bpm,
        )
        concert_provenance = variants_dir / f"{token}-concert-pitch.provenance.json"
        write_note_provenance(
            concert_provenance,
            primary_records,
            conversion_mode="repair",
            source_stem=stem,
            variant="concert_pitch",
        )
        published["concert_pitch"] = {
            "status": "ok",
            "notes": len(primary_notes),
            "midi": str(concert_path),
            "provenance": str(concert_provenance),
            "description": "The primary notes without source-tuning pitch bend.",
            "metrics": _vocal_variant_metrics(
                primary_notes, result.contour, result.diagnostics.tuning_hz
            ),
        }

    diagnostics = result.diagnostics.to_dict()
    diagnostics.update(
        {
            "source_stem": str(stem),
            "key": key,
            "bpm_nominal": bpm,
            "grid_bpm": float(grid.bpm),
            "grid_warped": bool(grid.is_warped),
            "metronome": str(metronome) if metronome else None,
            "chords_pdf": str(chords_pdf) if chords_pdf else None,
            "chord_policy": "recorded for audit; observed vocal notes are not forced onto an untimed chart",
            "pitch_bend_range_semitones": 2,
            "pitch_bend_14bit": pitch_bend_value(tuning_cents, 2),
        }
    )
    analysis_path = out_dir / "vocal_analysis.json"
    analysis_path.write_text(
        json.dumps(
            {"diagnostics": diagnostics, "variants": published},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    summary = {
        "status": "complete" if primary_notes else "no-evidence",
        "role": role,
        "source_stem": str(stem),
        "bpm": bpm,
        "set_garageband_tempo_to": bpm,
        "tuning_hz": result.diagnostics.tuning_hz,
        "garageband_fine_tune_cents": tuning_cents,
        "primary_variant": result.primary_variant,
        "primary_midi": str(primary_midi) if primary_notes else None,
        "primary_provenance": str(primary_provenance) if primary_notes else None,
        "contour": str(contour_path),
        "analysis": str(analysis_path),
        "variants": published,
        "warnings": list(result.diagnostics.warnings),
    }
    summary_path = out_dir / "vocal_summary.json"
    summary["summary"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def _vocal_variant_metrics(notes, frames, tuning_hz: float) -> dict:
    """Compare discrete note rectangles with the continuous source contour."""

    voiced = [
        frame
        for frame in frames
        if frame.f0_hz is not None and frame.voiced_probability >= 0.30
    ]
    residuals: list[float] = []
    covered = 0
    for frame in voiced:
        active = [note for note in notes if note.start <= frame.time < note.end]
        if not active:
            continue
        covered += 1
        source_midi = frame.fractional_midi(tuning_hz)
        if source_midi is not None:
            residuals.append(
                min(abs(source_midi - note.pitch) * 100.0 for note in active)
            )
    all_times = [frame.time for frame in frames]
    active_frames = sum(
        any(note.start <= time < note.end for note in notes) for time in all_times
    )
    voiced_times = {frame.time for frame in voiced}
    active_voiced = sum(
        time in voiced_times and any(note.start <= time < note.end for note in notes)
        for time in all_times
    )
    return {
        "note_count": len(notes),
        "pitch_low": min((note.pitch for note in notes), default=None),
        "pitch_high": max((note.pitch for note in notes), default=None),
        "total_note_seconds": round(sum(note.end - note.start for note in notes), 6),
        "voiced_contour_coverage": round(covered / len(voiced), 6) if voiced else 0.0,
        "active_frame_voiced_precision": round(active_voiced / active_frames, 6)
        if active_frames
        else 0.0,
        "absolute_pitch_error_p50_cents": _numeric_percentile(residuals, 50.0),
        "absolute_pitch_error_p90_cents": _numeric_percentile(residuals, 90.0),
        "pitch_within_50_cents": round(
            sum(value <= 50.0 for value in residuals) / len(residuals), 6
        )
        if residuals
        else 0.0,
        "monophonic": _notes_are_monophonic(notes),
    }


def _numeric_percentile(values, percentile: float) -> float | None:
    import math

    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = max(0.0, min(100.0, percentile)) / 100.0 * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return round(ordered[low], 6)
    weight = position - low
    return round(ordered[low] * (1.0 - weight) + ordered[high] * weight, 6)


def _notes_are_monophonic(notes) -> bool:
    ordered = sorted(notes, key=lambda note: (note.start, note.end, note.pitch))
    return all(
        right.start >= left.end - 1e-6 for left, right in zip(ordered, ordered[1:])
    )


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
        variant_path = (
            variants_dir / f"{_safe_token(kind)}-{_safe_token(variant_name)}.mid"
        )
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
        print(
            "sunofriend: FluidSynth or a GM SoundFont is missing (see README).",
            file=sys.stderr,
        )
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
        print(
            f"detected average bpm: {summary['bpm_true']} (downbeat at {summary['downbeat_offset']}s)"
        )
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


def _run_doctor(args) -> int:
    from .diagnostics import capability_ready, collect_diagnostics

    result = collect_diagnostics()
    result["required_capability"] = args.require
    result["requirement_ready"] = capability_ready(result, args.require)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["requirement_ready"] else 1


def _run_ai_doctor(args) -> int:
    from .ai_runtime import ai_requirement_ready, collect_ai_diagnostics

    result = collect_ai_diagnostics(args.python)
    result["required_capability"] = args.require
    result["requirement_ready"] = ai_requirement_ready(result, args.require)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["requirement_ready"] else 1


def _run_ai_transcribe(args) -> int:
    from .ai_bakeoff import run_ai_transcription
    from .ai_runtime import (
        resolve_game_model,
        resolve_muscriptor_checkpoint,
        resolve_pesto_model,
        resolve_rmvpe_model,
    )

    if args.backend == "game":
        checkpoint = resolve_game_model(args.checkpoint)
        options = {
            "device": args.device,
            "language": args.language,
            "boundary_threshold": args.boundary_threshold,
            "boundary_radius_ms": args.boundary_radius_ms,
            "presence_threshold": args.presence_threshold,
            "game_steps": args.game_steps,
            "seed": args.seed,
        }
    elif args.backend == "rmvpe":
        checkpoint = resolve_rmvpe_model(args.checkpoint)
        options = {
            "device": args.device,
            "confidence_threshold": (
                0.03 if args.confidence_threshold is None else args.confidence_threshold
            ),
            "minimum_note_ms": args.minimum_note_ms,
            "maximum_gap_ms": args.maximum_gap_ms,
            "pitch_change_semitones": args.pitch_change_semitones,
        }
    elif args.backend == "pesto":
        checkpoint = resolve_pesto_model(args.checkpoint)
        options = {
            "device": args.device,
            "confidence_threshold": (
                0.2 if args.confidence_threshold is None else args.confidence_threshold
            ),
            "minimum_note_ms": args.minimum_note_ms,
            "maximum_gap_ms": args.maximum_gap_ms,
            "pitch_change_semitones": args.pitch_change_semitones,
            "step_size_ms": args.pesto_step_ms,
            "reduction": args.pesto_reduction,
            "num_chunks": args.pesto_chunks,
        }
    else:
        checkpoint = resolve_muscriptor_checkpoint(args.checkpoint)
        options = {
            "device": args.device,
            "beam_size": args.beam_size,
            "batch_size": args.batch_size,
            "cfg_coef": args.cfg_coef,
            "model_size": args.model_size,
            "prelude_forcing": args.prelude_forcing,
        }
    result = run_ai_transcription(
        audio_path=args.audio,
        out_dir=args.out_dir,
        checkpoint_path=checkpoint,
        bpm=args.bpm,
        backend=args.backend,
        roles=args.instrument,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        options=options,
        python=args.python,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_ai_matrix(args) -> int:
    from .ai_matrix import write_ai_candidate_matrix

    lanes = []
    for value in args.lane:
        if "=" not in value:
            raise ValueError("--lane must use LANE=RUN_DIR")
        lane, run_dir = value.split("=", 1)
        if not lane or not run_dir:
            raise ValueError("--lane must use non-empty LANE=RUN_DIR values")
        lanes.append((lane, run_dir))
    report = write_ai_candidate_matrix(
        lanes,
        args.out,
        boundary_tolerance_ms=args.boundary_tolerance_ms,
        overlap_tolerance_ms=args.overlap_tolerance_ms,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "output": str(Path(args.out).expanduser().absolute()),
                "schema": report["schema"],
                "lane_count": report["lane_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_ai_cleanup(args) -> int:
    from .ai_cleanup import run_ai_cleanup
    from .ai_runtime import resolve_demucs_model

    result = run_ai_cleanup(
        args.audio,
        out_dir=args.out_dir,
        checkpoint_path=resolve_demucs_model(args.checkpoint),
        target=args.target,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        overlap=args.overlap,
        python=args.python,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 1


def _run_midi_mask(args) -> int:
    from .midi_mask import create_midi_mask

    result = create_midi_mask(
        args.audio,
        args.midi,
        out_dir=args.out_dir,
        track_index=args.track_index,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        harmonics=args.harmonics,
        bandwidth_cents=args.bandwidth_cents,
        attack_seconds=args.attack_seconds,
        release_seconds=args.release_seconds,
        transient_seconds=args.transient_ms / 1000.0,
        transient_strength=args.transient_strength,
        n_fft=args.n_fft,
        hop_length=args.hop_length,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 1


def _run_midi_role_split(args) -> int:
    from .midi_role_split import create_midi_role_split

    result = create_midi_role_split(
        args.primary_midi,
        args.clusters,
        out_dir=args.out_dir,
        body_cluster=args.body_cluster,
        secondary_midi_path=args.secondary_midi,
        secondary_audio_path=args.secondary_audio,
        cleanup_review_path=args.cleanup_review,
        body_name=args.body_name,
        body_program=args.body_program,
        pluck_name=args.pluck_name,
        pluck_program=args.pluck_program,
        render_preview=not args.no_preview,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "review-required" else 1


def _run_midi_role_split_resolve(args) -> int:
    from .midi_role_split import resolve_midi_role_split

    result = resolve_midi_role_split(
        args.review,
        args.role_split_dir,
        out_dir=args.out_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_timbre_resynthesis(args) -> int:
    from .timbre_resynthesis import create_timbre_resynthesis

    result = create_timbre_resynthesis(
        args.source_audio,
        args.midi,
        out_dir=args.out_dir,
        gm_program=args.gm_program,
        source_soundfont_path=args.source_soundfont,
        source_soundfont_program=args.source_soundfont_program,
        harmonics=args.harmonics,
        attack_seconds=args.attack_ms / 1000.0,
        release_seconds=args.release_ms / 1000.0,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "review-required" else 1


def _run_preview(args) -> int:
    from .render import render_midi_to_wav

    midi = Path(args.midi)
    output = Path(args.out) if args.out else midi.with_suffix(".preview.wav")
    print(render_midi_to_wav(midi, output, soundfont_path=args.soundfont))
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


def _run_midi_transform(args) -> int:
    from .midi_transform import transform_midi_path

    results = transform_midi_path(
        args.input,
        args.out,
        semitones=args.semitones,
        target_bpm=args.target_bpm,
        source_bpm=args.source_bpm,
        concert_pitch=args.concert_pitch,
        max_tuning_cents=args.max_tuning_cents,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "operation": "midi-transform",
                "file_count": len(results),
                "semitones": int(args.semitones),
                "source_bpm": args.source_bpm,
                "target_bpm": args.target_bpm,
                "set_garageband_tempo_to": args.target_bpm,
                "concert_pitch_cleanup_requested": bool(args.concert_pitch),
                "tuning_setups_removed": sum(
                    result.change.tuning_setups_removed for result in results
                ),
                "files": [result.to_dict() for result in results],
                "timing_contract": (
                    "Every MIDI tick and groove offset is preserved; changing tempo "
                    "scales elapsed playback time. The result no longer matches untreated "
                    "source audio when tempo or pitch changes. Concert-pitch cleanup "
                    "removes only recognised Sunofriend tuning setups; unrelated or "
                    "expressive pitch bends are deliberately preserved."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_midi_anchor(args) -> int:
    from .midi_anchor import anchor_midi_path

    results = anchor_midi_path(
        args.input,
        args.out,
        source_downbeat_seconds=args.source_downbeat_seconds,
        source_bpm=args.source_bpm,
        target_bpm=args.target_bpm,
        target_downbeat_beat=args.target_downbeat_beat,
        semitones=args.semitones,
        concert_pitch=args.concert_pitch,
        max_tuning_cents=args.max_tuning_cents,
        overwrite=args.overwrite,
    )
    first = results[0].change
    print(
        json.dumps(
            {
                "operation": "midi-anchor",
                "file_count": len(results),
                "semitones": int(args.semitones),
                "source_bpm": float(args.source_bpm),
                "target_bpm": float(args.target_bpm),
                "source_downbeat_seconds": float(args.source_downbeat_seconds),
                "source_downbeat_tick": first.source_downbeat_tick,
                "target_downbeat_beat": float(args.target_downbeat_beat),
                "target_downbeat_tick": first.target_downbeat_tick,
                "shift_ticks": first.shift_ticks,
                "set_garageband_tempo_to": float(args.target_bpm),
                "concert_pitch_cleanup_requested": bool(args.concert_pitch),
                "tuning_setups_removed": sum(
                    result.change.transform.tuning_setups_removed for result in results
                ),
                "files": [result.to_dict() for result in results],
                "timing_contract": (
                    "All musical events receive one constant tick offset, so the "
                    "confirmed downbeat is shared while the source performance's "
                    "tempo wander and microtiming remain intact."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_midi_align(args) -> int:
    from .midi_align import align_midi_path

    results = align_midi_path(
        args.input,
        metronome_path=args.metronome,
        source_bpm=args.source_bpm,
        target_bpm=args.target_bpm,
        semitones=args.semitones,
        count_in_bars=args.count_in_bars,
        beats_per_bar=args.beats_per_bar,
        source_downbeat_beat=args.source_downbeat_beat,
        output_path=args.out,
        overwrite=args.overwrite,
    )
    first = results[0].change
    print(
        json.dumps(
            {
                "operation": "midi-align",
                "file_count": len(results),
                "source_bpm": float(args.source_bpm),
                "target_bpm": float(args.target_bpm),
                "detected_grid_bpm": first.detected_grid_bpm,
                "semitones": int(args.semitones),
                "count_in_bars": float(args.count_in_bars),
                "source_downbeat_beat": int(args.source_downbeat_beat),
                "set_garageband_tempo_to": float(args.target_bpm),
                "note_only_rebuild": True,
                "assumes_receiver_a_hz": 440.0,
                "discarded_by_rebuild": [
                    "controller and sustain automation",
                    "bank and later program changes",
                    "pitch bend and aftertouch",
                    "SysEx",
                    "release velocity",
                    "key, chord, lyric and marker metadata",
                    "later time-signature changes",
                ],
                "files": [result.to_dict() for result in results],
                "timing_contract": (
                    "The source metronome's tempo wander has been mapped to a straight "
                    "bar grid; within-beat placement is retained. This creative copy "
                    "does not remain aligned to untreated source audio."
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


def _run_instrument_inventory(args) -> int:
    from .instrument_catalog import inventory_instruments

    inventory = inventory_instruments(
        garageband_sampler_root=args.garageband_root,
        logic_drum_root=args.drum_root,
        garageband_instrument_root=args.garageband_instrument_root,
        logic_instrument_root=args.logic_instrument_root,
        include_audio_units=not args.no_audio_units,
    ).to_dict()
    rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    if args.out:
        output = Path(args.out).expanduser()
        if output.exists():
            raise ValueError(f"Output file already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


def _run_instrument_match(args) -> int:
    from .instrument_match import match_instruments

    report = match_instruments(
        args.stem,
        args.midi,
        kind=args.kind,
        out_dir=args.out_dir,
        top=args.top,
        track_index=args.track_index,
        garageband_sampler_root=args.garageband_root,
        logic_drum_root=args.drum_root,
        include_factory=not args.no_factory,
        include_gm=not args.no_gm,
        all_programs=args.all_programs,
        max_source_segments=args.max_source_segments,
        max_samples_per_asset=args.max_samples_per_asset,
        embedding_model_path=args.embedding_model,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack(args) -> int:
    from .instrument_match import build_sample_pack

    report = build_sample_pack(
        args.stem,
        args.midi,
        kind=args.kind,
        out_dir=args.out_dir,
        track_index=args.track_index,
        max_samples=args.max_samples,
        tail_ms=args.tail_ms,
        allow_polyphonic=args.allow_polyphonic,
        instrument_name=args.name,
        render_preview=not args.no_preview,
        max_transpose=args.max_transpose,
        auto_tune=not args.no_auto_tune,
        embedding_model_path=args.embedding_model,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack_review(args) -> int:
    from .sample_review import create_sample_pack_review

    report = create_sample_pack_review(args.sample_pack, out_dir=args.out_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack_apply(args) -> int:
    from .sample_review import apply_sample_pack_review

    report = apply_sample_pack_review(
        args.review,
        out_dir=args.out_dir,
        render_preview=not args.no_preview,
        instrument_name=args.name,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack_boundary_review(args) -> int:
    from .sample_review import create_sample_boundary_review

    report = create_sample_boundary_review(
        args.sample_pack_v3, out_dir=args.out_dir
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack_boundary_apply(args) -> int:
    from .sample_review import apply_sample_boundary_review

    report = apply_sample_boundary_review(
        args.review,
        out_dir=args.out_dir,
        render_preview=not args.no_preview,
        instrument_name=args.name,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack_ab_review(args) -> int:
    from .sample_ab_review import create_sample_ab_review

    report = create_sample_ab_review(args.sample_pack_v3, out_dir=args.out_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_sample_pack_ab_resolve(args) -> int:
    from .sample_ab_review import resolve_sample_ab_review

    report = resolve_sample_ab_review(args.review, out=args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_instrument_bundle(args) -> int:
    from .instrument_bundle import build_instrument_bundle

    report = build_instrument_bundle(
        args.stem,
        args.midi,
        kind=args.kind,
        out_dir=args.out_dir,
        track_index=args.track_index,
        top=args.top,
        garageband_sampler_root=args.garageband_root,
        logic_drum_root=args.drum_root,
        include_factory=not args.no_factory,
        include_gm=not args.no_gm,
        include_source_audio=not args.no_source_audio,
        build_source_instrument=not args.no_source_instrument,
        render_preview=not args.no_preview,
        allow_polyphonic=args.allow_polyphonic,
        max_samples=args.max_samples,
        tail_ms=args.tail_ms,
        max_transpose=args.max_transpose,
        auto_tune=not args.no_auto_tune,
        instrument_name=args.name,
        embedding_model_path=args.embedding_model,
        preference_profile_path=args.preference_profile,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_instrument_feedback(args) -> int:
    from .instrument_preference import record_instrument_patch_feedback

    report = record_instrument_patch_feedback(
        args.bundle,
        patch_name=args.patch,
        out_path=args.out,
        patch_source=args.patch_source,
        decision=args.decision,
        listening_context=args.context,
        compared_with=args.compared_with,
        notes=args.notes,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_instrument_profile(args) -> int:
    from .instrument_preference import build_personal_instrument_profile

    report = build_personal_instrument_profile(args.feedback, out_path=args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_workbench(args) -> int:
    from .workbench_server import run_workbench

    report = run_workbench(
        args.project,
        candidate_roots=args.candidate_root,
        catalog_path=args.catalog,
        state_dir=args.state_dir,
        port=args.port,
        open_browser=args.open,
        inspect_only=args.inspect,
        soundfont_path=args.soundfont,
    )
    if args.inspect:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_clip_import(args) -> int:
    from .clip import read_midi_clips
    from .library import ClipLibrary

    clips = list(
        read_midi_clips(
            args.midi, key=args.key, role=args.role, suggestions=args.suggest
        )
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
        clip = replace(
            clip, title=title, tags=tuple(set(clip.tags) | set(args.tag))
        ).with_content_id()
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
            raise ValueError(
                "A target-key transformation requires source and target keys"
            )
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
    print(
        json.dumps(
            {"clip_id": clip.clip_id, "revision": clip.revision, "midi": args.out},
            indent=2,
        )
    )
    return 0


def _run_clip_instrument(args) -> int:
    from .clip import Instrument, TransformRecipe
    from .library import ClipLibrary

    library = ClipLibrary(_library_path(args.library))
    clip = library.get(args.clip_id)
    current = clip.instrument
    if all(
        value is None for value in (args.role, args.program, args.channel, args.suggest)
    ):
        raise ValueError("Choose --role, --program, --channel, and/or --suggest")
    instrument = Instrument(
        role=args.role or current.role,
        program=current.program if args.program is None else args.program,
        channel=current.channel if args.channel is None else args.channel,
        suggestions=current.suggestions
        if args.suggest is None
        else tuple(args.suggest),
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
