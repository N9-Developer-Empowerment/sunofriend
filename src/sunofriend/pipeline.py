from __future__ import annotations

import json
from pathlib import Path

from .audio import analyze_stem_activity
from .chords import extract_chords_from_moises_pdf, generate_pad_notes, make_chord_segments, write_chord_csv
from .generate import bass_notes_from_activity, drum_notes_from_analysis
from .metadata import infer_project_metadata
from .midi import MidiTrack, write_midi_file
from .models import PipelineResult, StemAnalysis


def run_remake(
    input_folder: str | Path,
    out_dir: str | Path,
    style: str = "edm",
    bpm: float | None = None,
    key: str | None = None,
) -> PipelineResult:
    folder = Path(input_folder)
    if not folder.is_dir():
        raise ValueError(f"Input folder does not exist: {folder}")

    metadata = infer_project_metadata(folder)
    bpm = bpm or metadata.bpm
    key = key or metadata.key
    if bpm is None:
        raise ValueError("BPM was not provided and could not be inferred from the folder name")

    chart_path = _find_chord_pdf(folder)
    chart = extract_chords_from_moises_pdf(chart_path)
    key = key or chart.key

    drum_parts = ["kick", "snare", "hat", "cymbals", "toms", "other_kit"]
    stems = {part: _find_stem(folder, part) for part in drum_parts + ["bass"]}
    analyses: dict[str, StemAnalysis] = {}
    for part, path in stems.items():
        if path:
            ratio = 0.16 if part in {"hat", "cymbals"} else 0.22
            gap = 0.25 if part in {"hat", "cymbals"} else 0.5
            analyses[part] = analyze_stem_activity(path, bpm=bpm, threshold_ratio=ratio, min_gap_beats=gap)

    duration = _duration_from_analyses(analyses)
    segments = make_chord_segments(chart.chords, duration_seconds=duration, bpm=bpm)

    drum_part_notes = {
        part: drum_notes_from_analysis(part, analyses[part], duration=0.045 if part in {"hat", "cymbals"} else 0.075)
        for part in drum_parts
        if part in analyses
    }
    drum_notes = sorted(
        [note for part_notes in drum_part_notes.values() for note in part_notes],
        key=lambda note: (note.start, note.pitch),
    )

    bass_notes = bass_notes_from_activity(
        bass=analyses.get("bass"),
        kick=analyses.get("kick"),
        chords=segments,
        bpm=bpm,
    )
    pad_notes = generate_pad_notes(segments)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tracks = {
        "drums_clean.mid": [MidiTrack("Clean Drums", channel=9, program=0, notes=drum_notes)],
        "bass_clean.mid": [MidiTrack("Clean Bass", channel=0, program=38, notes=bass_notes)],
        "pads_chords.mid": [MidiTrack("Pads Chords", channel=1, program=89, notes=pad_notes)],
        "full_arrangement.mid": [
            MidiTrack("Clean Drums", channel=9, program=0, notes=drum_notes),
            MidiTrack("Clean Bass", channel=0, program=38, notes=bass_notes),
            MidiTrack("Pads Chords", channel=1, program=89, notes=pad_notes),
        ],
    }
    part_filenames = {
        "kick": "kick_clean.mid",
        "snare": "snare_clean.mid",
        "hat": "hats_clean.mid",
        "cymbals": "cymbals_clean.mid",
        "toms": "toms_clean.mid",
        "other_kit": "other_kit_clean.mid",
    }
    for part, part_notes in drum_part_notes.items():
        tracks[part_filenames[part]] = [
            MidiTrack(part.replace("_", " ").title(), channel=9, program=0, notes=part_notes)
        ]

    files: list[Path] = []
    for filename, midi_tracks in tracks.items():
        output = out_dir / filename
        write_midi_file(output, midi_tracks, bpm=bpm)
        files.append(output)

    chord_csv = out_dir / "chords_extracted.csv"
    write_chord_csv(chord_csv, segments)
    files.append(chord_csv)

    report_notes = {**drum_part_notes, "bass": bass_notes, "pads": pad_notes}
    report = _build_report(metadata_key=metadata.key, metadata_bpm=metadata.bpm, metadata_tuning=metadata.tuning_hz, key=key, bpm=bpm, style=style, analyses=analyses, segments=segments, notes=report_notes)
    report_path = out_dir / "quality_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    files.append(report_path)

    return PipelineResult(files=sorted(files, key=lambda path: path.name), report=report)


def _find_chord_pdf(folder: Path) -> Path:
    candidates = sorted(folder.glob("*chords*.pdf"))
    if not candidates:
        raise ValueError(f"No Moises chord PDF found in {folder}")
    return candidates[0]


def _find_stem(folder: Path, part: str) -> Path | None:
    for path in sorted(folder.glob("*.wav")):
        name = path.name.lower()
        if f"-{part}-" in name or f"_{part}-" in name:
            return path
    return None


def _duration_from_analyses(analyses: dict[str, StemAnalysis]) -> float:
    if not analyses:
        raise ValueError("At least one usable WAV stem is required")
    return max(analysis.duration_seconds for analysis in analyses.values())


def _build_report(
    metadata_key: str | None,
    metadata_bpm: float | None,
    metadata_tuning: float | None,
    key: str | None,
    bpm: float,
    style: str,
    analyses: dict[str, StemAnalysis],
    segments,
    notes: dict[str, list],
) -> dict:
    return {
        "metadata": {"key": key or metadata_key, "bpm": bpm or metadata_bpm, "tuning_hz": metadata_tuning},
        "style": style,
        "duration_seconds": max((analysis.duration_seconds for analysis in analyses.values()), default=0),
        "chord_count": len(segments),
        "analysis": {
            part: {
                "file": str(analysis.path),
                "duration_seconds": analysis.duration_seconds,
                "peak_rms": round(analysis.peak_rms, 5),
                "events": len(analysis.events),
            }
            for part, analysis in analyses.items()
        },
        "scores": {
            "drum_events": sum(len(value) for key, value in notes.items() if key not in {"bass", "pads"}),
            "bass_notes": len(notes["bass"]),
            "pad_notes": len(notes["pads"]),
            "kick_events": len(notes.get("kick", [])),
            "snare_events": len(notes.get("snare", [])),
            "hat_events": len(notes.get("hat", [])),
            "cymbal_events": len(notes.get("cymbals", [])),
            "tom_events": len(notes.get("toms", [])),
            "other_kit_events": len(notes.get("other_kit", [])),
            "chord_coverage": 1.0 if segments and notes["pads"] else 0.0,
        },
        "notes": [
            "Drums are detected from separated percussion stems, quantized to the BPM grid, and exported as clean MIDI.",
            "Bass MIDI follows bass/kick rhythmic activity and uses the current chord root rather than noisy pitch recovery.",
            "Pad MIDI is generated from Moises chord names with smooth voicings.",
        ],
    }
