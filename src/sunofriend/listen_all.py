"""Process a whole Suno/Moises export folder in one command.

Discovers stems, the chords PDF, and the metronome; infers BPM/key from the
folder name; skips near-silent stems; runs the listen/refine loop per stem
(imagine mode for bass/lead, chord-mode pads from the keys stem); and merges
everything into one GarageBand-ready multitrack MIDI.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .metadata import infer_project_metadata
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent

DRUM_PARTS = ["kick", "snare", "hat", "cymbals", "toms", "other_kit"]
PITCHED_PARTS = {  # stem token -> processing kind
    "bass": "bass",
    "lead": "lead",
    "keys": "keys",
    "piano": "keys",
    "strings": "pads",  # sustained chords: chart voicings + stem dynamics beat transcription
}
CHANNELS = {  # part -> (channel, GM program)
    "kick": (9, 0), "snare": (9, 0), "hat": (9, 0), "cymbals": (9, 0),
    "toms": (9, 0), "other_kit": (9, 0),
    "bass": (0, 38), "keys": (1, 89), "pads": (1, 89), "piano": (3, 0),
    "strings": (4, 48), "lead": (2, 81),
}
SILENCE_PEAK = 0.005


def run_listen_all(
    folder: str | Path,
    out_dir: str | Path,
    bpm: float | None = None,
    key: str | None = None,
    parts: list[str] | None = None,
    max_iterations: int = 8,
    progress=print,
) -> dict:
    from .loop import refine_stem

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
        "parts": {},
    }
    daw_bpm = float(round(bpm))
    if metronome:
        from .beatgrid import grid_from_metronome

        grid = grid_from_metronome(str(metronome), nominal_bpm=bpm)
        summary["bpm_true"] = grid.bpm
        summary["downbeat_offset"] = grid.offset
        summary["beat_wander"] = grid.is_warped
        daw_bpm = float(round(grid.bpm))
    # All output MIDI is written at an INTEGER tempo GarageBand can reproduce
    # exactly. Note times are absolute seconds, so at this exact project tempo
    # every note lines up with the audio stems sample-accurately.
    summary["set_garageband_tempo_to"] = daw_bpm

    jobs: list[tuple[str, Path, str]] = []  # (output name, stem path, kind)
    wanted = set(parts) if parts else None
    for part in DRUM_PARTS:
        stem = _find_stem(folder, part)
        if stem and (wanted is None or part in wanted):
            jobs.append((part, stem, part))
    for token, kind in PITCHED_PARTS.items():
        stem = _find_stem(folder, token)
        if stem and (wanted is None or token in wanted):
            jobs.append((token, stem, kind))
    if keys_stem and (wanted is None or "pads" in wanted):
        jobs.append(("pads", keys_stem, "pads"))

    seen = set()
    merged_tracks: list[MidiTrack] = []
    for name, stem, kind in jobs:
        if name in seen:
            continue
        seen.add(name)
        if _is_silent(stem):
            summary["parts"][name] = {"status": "skipped: near-silent stem"}
            progress(f"{name}: skipped (near-silent)")
            continue
        started = time.time()
        try:
            part_dir = out_dir / f".{name}_work"
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
            )
            # refine writes <kind>_listened.mid inside part_dir; publish under the part name
            # (copy instead of rename: some mounted filesystems forbid rename)
            import shutil

            final = out_dir / f"{name}_listened.mid"
            shutil.copyfile(result.midi_path, final)
            iterations_src = part_dir / f"{kind}_iterations.json"
            if iterations_src.exists():
                shutil.copyfile(iterations_src, out_dir / f"{name}_iterations.json")
            shutil.rmtree(part_dir, ignore_errors=True)
            summary["parts"][name] = {
                "status": "ok",
                "score": round(result.score, 4),
                "notes": len(result.notes),
                "iterations": len(result.history),
                "seconds": round(time.time() - started, 1),
                "midi": str(final),
            }
            channel, program = CHANNELS.get(name, (5, 0))
            merged_tracks.append(
                MidiTrack(name.title(), channel=channel, program=program, notes=result.notes)
            )
            progress(f"{name}: ok score={summary['parts'][name]['score']} notes={len(result.notes)}")
        except Exception as exc:  # keep going; one bad stem shouldn't kill the batch
            summary["parts"][name] = {"status": f"error: {exc}"}
            progress(f"{name}: ERROR {exc}")

    if merged_tracks:
        arrangement = out_dir / "full_arrangement.mid"
        write_midi_file(arrangement, merged_tracks, bpm=daw_bpm)
        summary["arrangement"] = str(arrangement)
    (out_dir / "listen_all_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _find_stem(folder: Path, part: str) -> Path | None:
    for path in sorted(folder.glob("*.wav")):
        name = path.name.lower()
        if f"-{part}-" in name or f"_{part}-" in name:
            return path
    return None


def _is_silent(path: Path, peak_threshold: float = SILENCE_PEAK) -> bool:
    import numpy as np
    import soundfile

    peak = 0.0
    with soundfile.SoundFile(str(path)) as handle:
        for block in handle.blocks(blocksize=1 << 20, dtype="float32"):
            peak = max(peak, float(np.max(np.abs(block))))
            if peak > peak_threshold:
                return False
    return peak <= peak_threshold


__all__ = ["run_listen_all", "NoteEvent"]
