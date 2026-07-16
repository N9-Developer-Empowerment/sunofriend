"""Local phrase-by-phrase review of immutable vocal tracker alternatives.

The review package is deliberately downstream of ``vocal-trackers``. It
verifies the source and evidence hashes, renders short neutral-instrument
auditions, and exports the existing melody-correction format. Raw tracker
artifacts are never edited and backing harmony is not reduced to one line.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .melody_correction import CORRECTION_FORMAT
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .vocal_boundary import VOCAL_BOUNDARY_REPAIR_SCHEMA


PHRASE_REVIEW_SCHEMA = "sunofriend.melody-phrase-review.v1"


def build_melody_phrase_review(
    tracker_run: str | Path,
    *,
    out_dir: str | Path,
    source_stem: str | Path | None = None,
    padding_seconds: float = 0.25,
) -> dict[str, Any]:
    """Build a fresh local phrase-review package from one lead tracker run."""

    padding = float(padding_seconds)
    if not math.isfinite(padding) or not 0 <= padding <= 2.0:
        raise ValueError("padding_seconds must be finite and between 0 and 2")
    run_path = _run_manifest_path(tracker_run)
    run_dir = run_path.parent
    run = _read_json(run_path)
    if run.get("status") != "complete":
        raise ValueError("tracker run must be complete")
    if run.get("schema") != "sunofriend.vocal-tracker-run.v1":
        raise ValueError("unsupported vocal tracker run schema")
    if run.get("role") != "lead":
        raise ValueError(
            "melody-review currently supports lead vocals only; retain backing "
            "harmony and polyphonic evidence"
        )
    if not run.get("boundary_repair_created"):
        raise ValueError("tracker run does not contain agreed-F0 boundary repair")

    source_record = run.get("source")
    if not isinstance(source_record, Mapping) or not source_record.get("sha256"):
        raise ValueError("tracker run is missing its source record")
    stem = _resolve_source(source_stem or source_record.get("path"), run_dir)
    _verify_file_record(stem, source_record, label="source WAV")
    source_record = {**source_record, "path": str(stem)}

    boundary_path = run_dir / "boundary-repair.evidence.json"
    basic_path = run_dir / "basic-pitch.evidence.json"
    combined_midi_path = run_dir / "boundary-repair.candidate.mid"
    _verify_run_artifact(run, boundary_path)
    _verify_run_artifact(run, basic_path)
    _verify_run_artifact(run, combined_midi_path)
    boundary = _read_json(boundary_path)
    basic = _read_json(basic_path)
    if boundary.get("schema") != VOCAL_BOUNDARY_REPAIR_SCHEMA:
        raise ValueError("unsupported boundary-repair evidence schema")
    if basic.get("schema") != "sunofriend.vocal-tracker-evidence.v1":
        raise ValueError("unsupported Basic Pitch evidence schema")
    for label, document in (("boundary repair", boundary), ("Basic Pitch", basic)):
        recorded = document.get("source", {})
        if recorded.get("sha256") != source_record["sha256"]:
            raise ValueError(f"{label} source hash does not match the tracker run")

    phrase_records = boundary.get("phrases", {}).get("combined", [])
    if not isinstance(phrase_records, list) or not phrase_records:
        raise ValueError("boundary repair contains no combined lead phrases")
    variants = boundary.get("variants", {})
    sources = {
        "basic-pitch": _notes_from_document(basic.get("notes", [])),
        "game-boundary": _notes_from_document(variants.get("game", [])),
        "combined": _notes_from_document(variants.get("combined", [])),
    }
    if not sources["combined"]:
        raise ValueError("boundary repair contains no combined notes")

    bpm = float(run.get("bpm", 0.0))
    tuning_hz = float(run.get("tuning_hz", 440.0))
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("tracker run BPM must be finite and positive")
    if not math.isfinite(tuning_hz) or tuning_hz <= 0:
        raise ValueError("tracker run tuning must be finite and positive")

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"phrase-review output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=str(destination.parent),
        )
    )
    try:
        package = _write_review_package(
            temporary,
            stem=stem,
            source_record=dict(source_record),
            run_path=run_path,
            run=run,
            boundary_path=boundary_path,
            boundary=boundary,
            basic_path=basic_path,
            combined_midi_path=combined_midi_path,
            phrase_records=phrase_records,
            note_sources=sources,
            bpm=bpm,
            tuning_hz=tuning_hz,
            padding_seconds=padding,
        )
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _relocate_paths(package, destination)


def _write_review_package(
    destination: Path,
    *,
    stem: Path,
    source_record: dict[str, Any],
    run_path: Path,
    run: Mapping[str, Any],
    boundary_path: Path,
    boundary: Mapping[str, Any],
    basic_path: Path,
    combined_midi_path: Path,
    phrase_records: Sequence[Mapping[str, Any]],
    note_sources: Mapping[str, Sequence[NoteEvent]],
    bpm: float,
    tuning_hz: float,
    padding_seconds: float,
) -> dict[str, Any]:
    import soundfile

    audio, sample_rate = soundfile.read(
        str(stem), dtype="float32", always_2d=True
    )
    source_info = soundfile.info(str(stem))
    duration = len(audio) / sample_rate if sample_rate else 0.0
    if duration <= 0:
        raise ValueError("source WAV contains no audio")

    (destination / "audio").mkdir()
    (destination / "midi").mkdir()
    (destination / "evaluation").mkdir()
    total_phrases = len(phrase_records)
    phrase_documents: list[dict[str, Any]] = []
    tuning_cents = 1200.0 * math.log2(tuning_hz / 440.0)
    for phrase in sorted(
        phrase_records,
        key=lambda value: (int(value["phrase_index"]), float(value["start_seconds"])),
    ):
        phrase_index = int(phrase["phrase_index"])
        start = float(phrase["start_seconds"])
        end = float(phrase["end_seconds"])
        if not 0 <= start < end <= duration + 0.05:
            raise ValueError(f"phrase {phrase_index} falls outside the source WAV")
        window_start = max(0.0, start - padding_seconds)
        window_end = min(duration, end + padding_seconds)
        token = f"phrase-{phrase_index + 1:02d}"
        source_rel = Path("audio") / f"{token}-source.wav"
        _write_excerpt(
            destination / source_rel,
            audio,
            sample_rate=sample_rate,
            start_seconds=window_start,
            end_seconds=window_end,
            subtype=source_info.subtype,
        )
        alternatives: dict[str, Any] = {}
        for name in ("basic-pitch", "game-boundary", "combined"):
            absolute_notes = _phrase_notes(
                note_sources[name],
                start_seconds=start,
                end_seconds=end,
            )
            local_notes = [
                NoteEvent(
                    note.start - window_start,
                    note.end - window_start,
                    note.pitch,
                    note.velocity,
                )
                for note in absolute_notes
            ]
            midi_rel = Path("midi") / f"{token}-{name}.mid"
            audio_rel = Path("audio") / f"{token}-{name}.wav"
            overlay_rel = Path("audio") / f"{token}-{name}-source-plus-midi.wav"
            evaluation_rel = Path("evaluation") / f"{token}-{name}.json"
            _write_phrase_midi(
                destination / midi_rel,
                local_notes,
                bpm=bpm,
                tuning_cents=tuning_cents,
                name=name,
            )
            if local_notes:
                from .render import render_midi_to_wav

                render_midi_to_wav(
                    destination / midi_rel,
                    destination / audio_rel,
                    sample_rate=sample_rate,
                )
            else:
                _write_silence(
                    destination / audio_rel,
                    duration_seconds=window_end - window_start,
                    sample_rate=sample_rate,
                )
            _mix_source_and_candidate(
                destination / source_rel,
                destination / audio_rel,
                destination / overlay_rel,
            )
            evaluation = _evaluate_alternative(
                destination / source_rel,
                destination / midi_rel,
            )
            _write_json(destination / evaluation_rel, evaluation)
            alternatives[name] = {
                "label": _alternative_label(name),
                "notes": [_note_dict(note) for note in absolute_notes],
                "note_count": len(absolute_notes),
                "midi": midi_rel.as_posix(),
                "audio": audio_rel.as_posix(),
                "overlay_audio": overlay_rel.as_posix(),
                "evaluation": evaluation_rel.as_posix(),
                "metrics": _headline(evaluation),
            }
        confidence_rank = int(phrase["confidence_rank"])
        phrase_documents.append(
            {
                "phrase_index": phrase_index,
                "confidence_rank": confidence_rank,
                "review_priority": total_phrases - confidence_rank + 1,
                "start_seconds": start,
                "end_seconds": end,
                "window_start_seconds": window_start,
                "window_end_seconds": window_end,
                "mean_agreement_ratio": float(phrase["mean_agreement_ratio"]),
                "mean_selection_score": float(phrase["mean_selection_score"]),
                "providers": list(phrase.get("providers", [])),
                "source_audio": source_rel.as_posix(),
                "default_alternative": "combined",
                "alternatives": alternatives,
            }
        )

    correction = {
        "format": CORRECTION_FORMAT,
        "format_version": 1,
        "source_stem": str(stem),
        "source_stem_sha256": source_record["sha256"],
        "source_midi": str(combined_midi_path),
        "source_variant": "agreed-f0-boundary-repair-combined",
        "bpm": bpm,
        "key": None,
        "role": "lead",
        "tuning_hz": tuning_hz,
        "garageband_fine_tune_cents": tuning_cents,
        "channel": 2,
        "program": 73,
        "guide_alignment": None,
        "review": {
            "format": PHRASE_REVIEW_SCHEMA,
            "status": "unreviewed",
            "source_review_manifest": "phrase_review.json",
            "tracker_run_id": run.get("run_id"),
            "tracker_run_sha256": _sha256(run_path),
            "raw_candidates_mutated": False,
            "choices": [
                {
                    "phrase_index": phrase["phrase_index"],
                    "selected": "combined",
                    "reviewed": False,
                }
                for phrase in phrase_documents
            ],
        },
        "notes": [_note_dict(note) for note in note_sources["combined"]],
    }
    correction_path = destination / "melody_corrections_unreviewed.json"
    _write_json(correction_path, correction)

    browser_phrases = sorted(
        phrase_documents,
        key=lambda phrase: (phrase["review_priority"], phrase["start_seconds"]),
    )
    html_path = destination / "melody_phrase_review.html"
    html_path.write_text(
        _phrase_review_html(correction, browser_phrases),
        encoding="utf-8",
    )

    manifest = {
        "schema": PHRASE_REVIEW_SCHEMA,
        "status": "review-required",
        "selection_policy": (
            "human phrase choice; raw Basic Pitch and agreed-F0 boundary "
            "candidates remain unchanged"
        ),
        "source": source_record,
        "tracker_run": _file_record(run_path),
        "inputs": {
            "boundary_repair": _file_record(boundary_path),
            "basic_pitch": _file_record(basic_path),
            "combined_midi": _file_record(combined_midi_path),
            "boundary_policy": boundary.get("policy"),
        },
        "bpm": bpm,
        "tuning_hz": tuning_hz,
        "role": "lead",
        "padding_seconds": padding_seconds,
        "phrase_count": len(phrase_documents),
        "alternative_names": ["basic-pitch", "game-boundary", "combined"],
        "phrases": phrase_documents,
        "correction_seed": correction_path.name,
        "html": html_path.name,
        "raw_candidates_mutated": False,
    }
    manifest["artifacts"] = {
        path.relative_to(destination).as_posix(): _file_record(
            path, relative_to=destination
        )
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    manifest_path = destination / "phrase_review.json"
    _write_json(manifest_path, manifest)
    return {
        "status": "review-required",
        "manifest": str(manifest_path),
        "html": str(html_path),
        "correction_seed": str(correction_path),
        "phrase_count": len(phrase_documents),
        "alternative_names": manifest["alternative_names"],
        "raw_candidates_mutated": False,
    }


def _run_manifest_path(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_dir():
        path = path / "run.json"
    if not path.is_file():
        raise ValueError(f"tracker run manifest not found: {path}")
    return path


def _resolve_source(value: Any, run_dir: Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("source WAV path is missing; supply --source-stem")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    path = path.absolute()
    if not path.is_file():
        raise ValueError(f"source WAV not found: {path}")
    return path


def _verify_run_artifact(run: Mapping[str, Any], path: Path) -> None:
    artifacts = run.get("artifacts", {})
    record = artifacts.get(path.name) if isinstance(artifacts, Mapping) else None
    if not isinstance(record, Mapping):
        raise ValueError(f"tracker manifest does not record {path.name}")
    _verify_file_record(path, record, label=path.name)


def _verify_file_record(
    path: Path,
    record: Mapping[str, Any],
    *,
    label: str,
) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    if record.get("sha256") != _sha256(path):
        raise ValueError(f"{label} hash does not match its immutable record")
    if record.get("bytes") is not None and int(record["bytes"]) != path.stat().st_size:
        raise ValueError(f"{label} size does not match its immutable record")


def _notes_from_document(values: Any) -> list[NoteEvent]:
    if not isinstance(values, list):
        raise ValueError("candidate notes must be a list")
    notes: list[NoteEvent] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("candidate note must be an object")
        try:
            start = float(value["start_seconds"])
            end = float(value["end_seconds"])
            pitch = int(value["pitch"])
            velocity = int(value.get("velocity", 90))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("candidate note has invalid values") from exc
        if not all(math.isfinite(number) for number in (start, end)):
            raise ValueError("candidate note times must be finite")
        if start < 0 or end <= start or not 0 <= pitch <= 127:
            raise ValueError("candidate note has invalid time or pitch")
        notes.append(NoteEvent(start, end, pitch, max(1, min(127, velocity))))
    return sorted(notes, key=lambda note: (note.start, note.pitch, note.end))


def _phrase_notes(
    notes: Sequence[NoteEvent],
    *,
    start_seconds: float,
    end_seconds: float,
) -> list[NoteEvent]:
    selected: list[NoteEvent] = []
    for note in notes:
        if note.end <= start_seconds or note.start >= end_seconds:
            continue
        start = max(start_seconds, note.start)
        end = min(end_seconds, note.end)
        if end - start >= 0.03:
            selected.append(NoteEvent(start, end, note.pitch, note.velocity))
    return selected


def _write_excerpt(
    path: Path,
    audio: Any,
    *,
    sample_rate: int,
    start_seconds: float,
    end_seconds: float,
    subtype: str,
) -> None:
    import soundfile

    start = max(0, int(round(start_seconds * sample_rate)))
    end = min(len(audio), int(round(end_seconds * sample_rate)))
    soundfile.write(path, audio[start:end], sample_rate, subtype=subtype)


def _write_phrase_midi(
    path: Path,
    notes: Sequence[NoteEvent],
    *,
    bpm: float,
    tuning_cents: float,
    name: str,
) -> None:
    # A silent candidate still needs a valid MIDI file for an honest audition.
    write_midi_file(
        path,
        [
            MidiTrack(
                f"Lead phrase: {_alternative_label(name)}",
                2,
                73,
                list(notes),
                pitch_bend_cents=tuning_cents,
            )
        ],
        bpm=bpm,
    )


def _write_silence(
    path: Path,
    *,
    duration_seconds: float,
    sample_rate: int,
) -> None:
    import numpy as np
    import soundfile

    frames = max(1, int(round(duration_seconds * sample_rate)))
    soundfile.write(path, np.zeros(frames, dtype=np.float32), sample_rate)


def _mix_source_and_candidate(source: Path, candidate: Path, output: Path) -> None:
    import numpy as np
    import soundfile

    source_audio, source_rate = soundfile.read(
        source, dtype="float32", always_2d=True
    )
    candidate_audio, candidate_rate = soundfile.read(
        candidate, dtype="float32", always_2d=True
    )
    if candidate_rate != source_rate:
        raise ValueError("rendered phrase sample rate does not match source excerpt")
    channels = source_audio.shape[1]
    if candidate_audio.shape[1] != channels:
        mono = np.mean(candidate_audio, axis=1, keepdims=True)
        candidate_audio = np.repeat(mono, channels, axis=1)
    aligned = np.zeros_like(source_audio)
    count = min(len(source_audio), len(candidate_audio))
    aligned[:count] = candidate_audio[:count]
    mixed = 0.68 * source_audio + 0.32 * aligned
    peak = float(np.max(np.abs(mixed))) if len(mixed) else 0.0
    if peak > 0.98:
        mixed *= 0.98 / peak
    soundfile.write(output, mixed, source_rate)


def _evaluate_alternative(source: Path, midi: Path) -> dict[str, Any]:
    from .evaluate import evaluate_stem_midi

    document = evaluate_stem_midi(source, midi, kind="lead").to_dict()
    # Evaluations are created in a temporary directory and then atomically
    # published. Never leak that random private path into immutable evidence.
    for key in ("stem_path", "midi_path", "candidate_path", "source_path"):
        if document.get(key):
            document[key] = Path(str(document[key])).name
    return document


def _headline(report: Mapping[str, Any]) -> dict[str, Any]:
    onsets = report.get("onsets", {})
    strong = onsets.get("strong", {})
    possible = onsets.get("possible", {})
    timing = onsets.get("timing", {})
    pitched = report.get("pitched") or {}
    return {
        "strong_onset_f1": strong.get("f1"),
        "possible_onset_f1": possible.get("f1"),
        "timing_p95_ms": timing.get("absolute_error_p95_ms"),
        "chroma_similarity": pitched.get("chroma_similarity"),
        "supported_note_ratio": pitched.get("supported_note_ratio"),
    }


def _alternative_label(name: str) -> str:
    return {
        "basic-pitch": "Raw Basic Pitch",
        "game-boundary": "GAME boundaries on agreed pitch",
        "combined": "Combined agreed-F0 repair",
    }[name]


def _phrase_review_html(
    correction: Mapping[str, Any],
    phrases: Sequence[Mapping[str, Any]],
) -> str:
    payload = json.dumps(
        {"correction": correction, "phrases": phrases},
        separators=(",", ":"),
    ).replace("</", "<\\/")
    cards = []
    for phrase in phrases:
        phrase_index = int(phrase["phrase_index"])
        source_audio = html.escape(str(phrase["source_audio"]), quote=True)
        alternatives = []
        for name in ("basic-pitch", "game-boundary", "combined"):
            candidate = phrase["alternatives"][name]
            audio_path = html.escape(str(candidate["audio"]), quote=True)
            overlay_path = html.escape(
                str(candidate["overlay_audio"]), quote=True
            )
            metrics = candidate["metrics"]
            alternatives.append(
                f"""<label class="candidate">
<span><input type="radio" name="phrase-{phrase_index}" value="{name}"
 {'checked' if name == 'combined' else ''}> <strong>{html.escape(candidate['label'])}</strong></span>
<span>{candidate['note_count']} notes · strong F1 {_metric(metrics.get('strong_onset_f1'))} · possible F1 {_metric(metrics.get('possible_onset_f1'))} · chroma {_metric(metrics.get('chroma_similarity'))}</span>
<span>MIDI only</span><audio controls preload="none" src="{audio_path}"></audio>
<span>Source + MIDI</span><audio controls preload="none" src="{overlay_path}"></audio>
<canvas class="mini" data-phrase="{phrase_index}" data-alternative="{name}" width="420" height="90"></canvas>
</label>"""
            )
        cards.append(
            f"""<section class="phrase" id="phrase-{phrase_index}">
<h2>Review priority {phrase['review_priority']} · {phrase['start_seconds']:.2f}–{phrase['end_seconds']:.2f}s</h2>
<p>Confidence rank {phrase['confidence_rank']} of {len(phrases)} · agreement {phrase['mean_agreement_ratio']:.3f}. Listen to the source, then choose the closest playable melody.</p>
<audio class="source" controls preload="none" src="{source_audio}"></audio>
<div class="candidates">{''.join(alternatives)}</div>
</section>"""
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend Phrase Review</title>
<style>
body{{font:15px system-ui,sans-serif;margin:0;background:#10151b;color:#eef3f7}}
main{{max-width:1260px;margin:auto;padding:20px}} h1{{margin-bottom:6px}}
.toolbar,.phrase,.roll-panel{{background:#19222c;border:1px solid #334252;border-radius:10px;padding:14px;margin:14px 0}}
.toolbar{{position:sticky;top:0;z-index:4}} button{{padding:8px 12px;background:#275174;color:white;border:1px solid #6c91ad;border-radius:6px;margin-right:6px}}
.progress{{color:#ffd34e}} .candidates{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}
.candidate{{display:flex;flex-direction:column;gap:7px;background:#111922;border:1px solid #405267;border-radius:8px;padding:10px}}
.candidate:has(input:checked){{border-color:#ffd34e;box-shadow:0 0 0 1px #ffd34e}}
audio{{width:100%}} canvas{{width:100%;background:#0b1015;border-radius:6px}}
#roll{{height:360px}} code{{color:#9ed9ff}} @media(max-width:850px){{.candidates{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Sunofriend phrase review</h1>
<p>Weakest phrases are shown first. Choose by recognition, not by the score alone. Every raw tracker artifact remains unchanged.</p>
<div class="toolbar"><span class="progress" id="progress"></span><br><br>
<button id="accept">Mark all current choices reviewed</button>
<button id="export">Export reviewed correction JSON</button>
<span>Then run <code>sunofriend melody-apply FILE --out reviewed-lead.mid</code>.</span></div>
{''.join(cards)}
<div class="roll-panel"><h2>Selected full melody</h2><canvas id="roll" width="1200" height="360"></canvas></div>
<script>const DATA={payload};
let doc=structuredClone(DATA.correction), choices=new Map(doc.review.choices.map(x=>[x.phrase_index,x]));
function phrase(i){{return DATA.phrases.find(x=>x.phrase_index===i)}}
function rebuild(){{let notes=[];for(const [i,c] of choices){{let p=phrase(i);notes.push(...p.alternatives[c.selected].notes)}}doc.notes=notes.sort((a,b)=>a.start-b.start||a.pitch-b.pitch||a.end-b.end);doc.review.choices=[...choices.values()].sort((a,b)=>a.phrase_index-b.phrase_index);drawRoll();progress()}}
document.querySelectorAll('input[type=radio]').forEach(x=>x.onchange=()=>{{let i=Number(x.name.split('-')[1]),c=choices.get(i);c.selected=x.value;c.reviewed=true;rebuild()}});
function progress(){{let n=[...choices.values()].filter(x=>x.reviewed).length;document.getElementById('progress').textContent=`Reviewed ${{n}} of ${{choices.size}} phrases`;}}
document.getElementById('accept').onclick=()=>{{for(const c of choices.values())c.reviewed=true;rebuild()}};
document.getElementById('export').onclick=()=>{{if([...choices.values()].some(x=>!x.reviewed)){{alert('Review every phrase or use “Mark all current choices reviewed” first.');return}}doc.review.status='reviewed';doc.review.reviewed_at=new Date().toISOString();rebuild();let b=new Blob([JSON.stringify(doc,null,2)],{{type:'application/json'}}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='melody-corrections-reviewed.json';a.click();URL.revokeObjectURL(u)}};
function mini(canvas){{let p=phrase(Number(canvas.dataset.phrase)),ns=p.alternatives[canvas.dataset.alternative].notes,ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);if(!ns.length)return;let lo=Math.min(...ns.map(n=>n.pitch))-1,hi=Math.max(...ns.map(n=>n.pitch))+1,d=Math.max(.1,p.end_seconds-p.start_seconds);ctx.fillStyle='#38c172';for(const n of ns){{let x=(n.start-p.start_seconds)/d*canvas.width,w=(n.end-n.start)/d*canvas.width,y=(hi-n.pitch)/(hi-lo)*canvas.height;ctx.fillRect(x,y-3,Math.max(2,w),6)}}}}
document.querySelectorAll('.mini').forEach(mini);
function drawRoll(){{let c=document.getElementById('roll'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);if(!doc.notes.length)return;let d=Math.max(...doc.notes.map(n=>n.end)),lo=Math.min(...doc.notes.map(n=>n.pitch))-2,hi=Math.max(...doc.notes.map(n=>n.pitch))+2;ctx.strokeStyle='#22303d';for(let t=0;t<d;t+=60/doc.bpm){{let x=t/d*c.width;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,c.height);ctx.stroke()}}ctx.fillStyle='#ffd34e';for(const n of doc.notes){{let x=n.start/d*c.width,w=(n.end-n.start)/d*c.width,y=(hi-n.pitch)/(hi-lo)*c.height;ctx.fillRect(x,y-4,Math.max(2,w),8)}}}}
rebuild();</script></main></body></html>"""


def _metric(value: Any) -> str:
    return "—" if value is None else f"{float(value):.3f}"


def _note_dict(note: NoteEvent) -> dict[str, Any]:
    return {
        "start": round(note.start, 6),
        "end": round(note.end, 6),
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_record(
    path: Path,
    *,
    relative_to: Path | None = None,
) -> dict[str, Any]:
    label = path.relative_to(relative_to) if relative_to else path
    return {
        "path": str(label),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return document


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _relocate_paths(result: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    relocated = dict(result)
    for key, name in (
        ("manifest", "phrase_review.json"),
        ("html", "melody_phrase_review.html"),
        ("correction_seed", "melody_corrections_unreviewed.json"),
    ):
        relocated[key] = str(destination / name)
    return relocated


__all__ = [
    "PHRASE_REVIEW_SCHEMA",
    "build_melody_phrase_review",
]
