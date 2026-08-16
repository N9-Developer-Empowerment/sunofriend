"""Explicit human review boundary for automatic vocal-comp input drafts."""

from __future__ import annotations

import html
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .render import render_midi_to_wav
from .vocal_comp import (
    VOCAL_COMP_TIMELINE_SCHEMA,
    _copy_private,
    _document_sha256,
    _file,
    _file_record,
    _find_words,
    _read_json,
    _read_midi_notes,
    _safe_relative,
    _sha256,
    _validated_phrase_rows,
    _verify_file_record,
    _words,
    _write_excerpt,
    _write_json,
    _zero_effects,
)


VOCAL_COMP_DRAFT_REVIEW_SCHEMA = "sunofriend.vocal-comp-draft-review.v1"
VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA = (
    "sunofriend.vocal-comp-draft-review-result.v1"
)
VOCAL_COMP_REVIEWED_INPUTS_SCHEMA = "sunofriend.vocal-comp-reviewed-inputs.v1"
VOCAL_COMP_DRAFT_FEEDBACK_SCHEMA = "sunofriend.vocal-comp-draft-feedback.v1"


def build_vocal_comp_draft_review(
    *,
    lyrics: str | Path,
    target_midi: str | Path,
    phrase_timeline: str | Path,
    target_vocal: str | Path,
    out_dir: str | Path,
    bpm: float,
    tuning_hz: float,
) -> dict[str, Any]:
    """Create a local listening page that grants no review authority itself."""

    lyrics_path = _file(lyrics, "draft lyrics")
    midi_path = _file(target_midi, "draft target MIDI")
    timeline_path = _file(phrase_timeline, "draft phrase timeline")
    vocal_path = _file(target_vocal, "target vocal")
    canonical_lyrics = lyrics_path.read_text(encoding="utf-8")
    timeline = _read_json(timeline_path)
    if timeline.get("schema") != VOCAL_COMP_TIMELINE_SCHEMA:
        raise ValueError(
            f"draft phrase timeline schema must be {VOCAL_COMP_TIMELINE_SCHEMA}"
        )
    if timeline.get("status") != "automatic_unreviewed":
        raise ValueError("draft phrase timeline must have status automatic_unreviewed")
    phrases = _validated_phrase_rows(timeline)
    _validate_lyric_order(canonical_lyrics, phrases)
    notes = _read_midi_notes(midi_path)
    for phrase in phrases:
        if not any(
            note.end > phrase["start_seconds"]
            and note.start < phrase["end_seconds"]
            for note in notes
        ):
            raise ValueError(
                f"draft target MIDI has no notes in {phrase['phrase_id']}"
            )
    if not float(bpm) > 0 or not float(tuning_hz) > 0:
        raise ValueError("bpm and tuning_hz must be positive")

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"draft review output already exists: {destination}")
    for source in (lyrics_path, midi_path, timeline_path, vocal_path):
        if source.parent in destination.parents:
            raise ValueError("draft review output must be outside every source tree")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        source_dir = temporary / "SOURCE"
        audio_dir = temporary / "AUDIO"
        for directory in (source_dir, audio_dir):
            directory.mkdir()
            os.chmod(directory, 0o700)
        copied_lyrics = source_dir / "automatic-lyrics.txt"
        copied_midi = source_dir / "automatic-target.mid"
        copied_timeline = source_dir / "automatic-phrase-timeline.json"
        copied_vocal = source_dir / "ai-reference-vocal.wav"
        for source, copied in (
            (lyrics_path, copied_lyrics),
            (midi_path, copied_midi),
            (timeline_path, copied_timeline),
            (vocal_path, copied_vocal),
        ):
            _copy_private(source, copied)
            if _sha256(source) != _sha256(copied):
                raise ValueError(f"draft source changed during copy: {source.name}")

        target_preview = audio_dir / "automatic-target-midi.wav"
        render_midi_to_wav(copied_midi, target_preview)
        os.chmod(target_preview, 0o600)
        review_phrases: list[dict[str, Any]] = []
        for phrase in phrases:
            phrase_id = phrase["phrase_id"]
            vocal_excerpt = audio_dir / f"{phrase_id}-ai-reference.wav"
            midi_excerpt = audio_dir / f"{phrase_id}-target-midi.wav"
            _write_excerpt(
                copied_vocal,
                vocal_excerpt,
                phrase["start_seconds"],
                phrase["end_seconds"],
            )
            _write_excerpt(
                target_preview,
                midi_excerpt,
                phrase["start_seconds"],
                phrase["end_seconds"],
            )
            review_phrases.append(
                {
                    **phrase,
                    "ai_reference_audition": str(vocal_excerpt.relative_to(temporary)),
                    "target_midi_audition": str(midi_excerpt.relative_to(temporary)),
                }
            )

        source_records = {
            "lyrics": _file_record(copied_lyrics, relative_to=temporary),
            "target_midi": _file_record(copied_midi, relative_to=temporary),
            "phrase_timeline": _file_record(copied_timeline, relative_to=temporary),
            "target_vocal": _file_record(copied_vocal, relative_to=temporary),
        }
        seed = {
            "schema": VOCAL_COMP_DRAFT_REVIEW_SCHEMA,
            "status": "automatic_unreviewed",
            "bpm": float(bpm),
            "tuning_hz": float(tuning_hz),
            "sources": source_records,
            "phrases": review_phrases,
            "review_contract": {
                "all_phrases_require_lyrics_and_timing_confirmation": True,
                "all_phrases_require_target_melody_confirmation": True,
                "playback_creates_decision": False,
                "visible_default_creates_decision": False,
            },
            "network_used": False,
            "effects": _zero_effects(),
        }
        seed["draft_sha256"] = _document_sha256(seed)
        seed_path = temporary / "vocal-comp-draft-review.json"
        _write_json(seed_path, seed)
        html_path = temporary / "vocal-comp-draft-review.html"
        html_path.write_text(_review_html(seed), encoding="utf-8")
        os.chmod(html_path, 0o600)
        manifest = {
            "schema": "sunofriend.vocal-comp-draft-review-package.v1",
            "status": "complete_unreviewed",
            "draft_sha256": seed["draft_sha256"],
            "seed": _file_record(seed_path, relative_to=temporary),
            "html": _file_record(html_path, relative_to=temporary),
            "artifacts": {
                str(path.relative_to(temporary)): _file_record(
                    path, relative_to=temporary
                )
                for path in sorted(temporary.rglob("*"))
                if path.is_file()
            },
            "effects": _zero_effects(),
        }
        manifest["package_sha256"] = _document_sha256(manifest)
        _write_json(temporary / "vocal-comp-draft-review-package.json", manifest)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **manifest,
        "output_directory": str(destination),
        "review_html": str(destination / "vocal-comp-draft-review.html"),
        "review_seed": str(destination / "vocal-comp-draft-review.json"),
    }


def resolve_vocal_comp_draft_review(
    package: str | Path,
    review: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Promote exact drafts only from an explicit complete human review JSON."""

    package_root = Path(package).expanduser().absolute()
    if package_root.is_file():
        package_manifest_path = package_root
        package_root = package_root.parent
    else:
        package_manifest_path = package_root / "vocal-comp-draft-review-package.json"
    package_manifest = _read_json(package_manifest_path)
    _verify_package(package_root, package_manifest)
    seed_path = package_root / package_manifest["seed"]["path"]
    seed = _read_json(seed_path)
    if seed.get("draft_sha256") != package_manifest.get("draft_sha256"):
        raise ValueError("draft review seed does not match package")
    review_path = _file(review, "reviewed vocal-comp draft JSON")
    if review_path.stat().st_size > 256 * 1024:
        raise ValueError("reviewed vocal-comp draft JSON must be no larger than 256 KiB")
    decision = _read_json(review_path)
    _validate_review(seed, decision)

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"reviewed-input output already exists: {destination}")
    if package_root in destination.parents:
        raise ValueError("reviewed inputs must be outside the review package")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        source = seed["sources"]
        lyrics = temporary / "reviewed-lyrics.txt"
        midi = temporary / "reviewed-target.mid"
        vocal = temporary / "ai-reference-vocal.wav"
        for record, copied in (
            (source["lyrics"], lyrics),
            (source["target_midi"], midi),
            (source["target_vocal"], vocal),
        ):
            original = package_root / _safe_relative(record["path"])
            _verify_file_record(original, record)
            _copy_private(original, copied)
        reviewed_timeline = {
            "schema": VOCAL_COMP_TIMELINE_SCHEMA,
            "status": "reviewed",
            "review": {
                "schema": VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA,
                "draft_sha256": seed["draft_sha256"],
                "reviewed_at": decision["reviewed_at"],
                "authority": "explicit_human_review_export",
            },
            "phrases": [
                {
                    "phrase_id": phrase["phrase_id"],
                    "start_seconds": phrase["start_seconds"],
                    "end_seconds": phrase["end_seconds"],
                    "lyrics": phrase["lyrics"],
                }
                for phrase in seed["phrases"]
            ],
        }
        timeline = temporary / "reviewed-phrase-timeline.json"
        _write_json(timeline, reviewed_timeline)
        copied_review = temporary / "draft-review.reviewed.json"
        review_sha256 = _sha256(review_path)
        _copy_private(review_path, copied_review)
        if _sha256(review_path) != review_sha256 or _sha256(copied_review) != review_sha256:
            raise ValueError("review JSON changed while it was being copied")
        result = {
            "schema": VOCAL_COMP_REVIEWED_INPUTS_SCHEMA,
            "status": "reviewed",
            "draft_sha256": seed["draft_sha256"],
            "lyrics": _file_record(lyrics, relative_to=temporary),
            "target_midi": _file_record(midi, relative_to=temporary),
            "phrase_timeline": _file_record(timeline, relative_to=temporary),
            "target_vocal": _file_record(vocal, relative_to=temporary),
            "review": _file_record(copied_review, relative_to=temporary),
            "human_decision_created": True,
            "selection_created": False,
            "audio_comp_rendered": False,
            "pitch_correction_applied": False,
            "network_used": False,
        }
        result["reviewed_inputs_sha256"] = _document_sha256(result)
        _write_json(temporary / "vocal-comp-reviewed-inputs.json", result)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **result,
        "output_directory": str(destination),
        "lyrics_path": str(destination / result["lyrics"]["path"]),
        "target_midi_path": str(destination / result["target_midi"]["path"]),
        "phrase_timeline_path": str(
            destination / result["phrase_timeline"]["path"]
        ),
        "target_vocal_path": str(destination / result["target_vocal"]["path"]),
    }


def record_vocal_comp_draft_feedback(
    package: str | Path,
    review: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Bind an unresolved human review without promoting any draft input."""

    package_root = Path(package).expanduser().absolute()
    if package_root.is_file():
        package_manifest_path = package_root
        package_root = package_root.parent
    else:
        package_manifest_path = package_root / "vocal-comp-draft-review-package.json"
    package_manifest = _read_json(package_manifest_path)
    _verify_package(package_root, package_manifest)
    seed = _read_json(package_root / package_manifest["seed"]["path"])
    review_path = _file(review, "vocal-comp draft feedback JSON")
    if review_path.stat().st_size > 256 * 1024:
        raise ValueError("vocal-comp draft feedback must be no larger than 256 KiB")
    decision = _read_json(review_path)
    if decision.get("schema") != VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA:
        raise ValueError("unsupported vocal-comp draft feedback schema")
    if decision.get("draft_sha256") != seed.get("draft_sha256"):
        raise ValueError("feedback does not bind this exact draft")
    if decision.get("status") != "unresolved":
        raise ValueError("feedback recorder accepts only unresolved reviews")
    expected_ids = [phrase["phrase_id"] for phrase in seed["phrases"]]
    rows = decision.get("phrases")
    if not isinstance(rows, list) or [row.get("phrase_id") for row in rows] != expected_ids:
        raise ValueError("feedback phrase roster does not match the draft")
    allowed = {"approved", "needs_change", "not_reviewed"}
    for row in rows:
        if row.get("lyrics_and_timing") not in allowed:
            raise ValueError("unsupported lyrics/timing feedback value")
        if row.get("target_melody") not in allowed:
            raise ValueError("unsupported target-melody feedback value")
        if not isinstance(row.get("notes", ""), str):
            raise ValueError("feedback notes must be text")
    if decision.get("effects") != {
        "automatic_selection": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
    }:
        raise ValueError("feedback effect declaration is missing or unsupported")

    destination = Path(out).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"vocal-comp draft feedback output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    reason_counts: dict[str, int] = {}
    for row in rows:
        for field in ("lyrics_and_timing", "target_melody"):
            key = f"{field}:{row[field]}"
            reason_counts[key] = reason_counts.get(key, 0) + 1
    document = {
        "schema": VOCAL_COMP_DRAFT_FEEDBACK_SCHEMA,
        "status": "recorded_unresolved",
        "draft_sha256": seed["draft_sha256"],
        "review_source": {
            "bytes": review_path.stat().st_size,
            "sha256": _sha256(review_path),
        },
        "phrase_count": len(rows),
        "reason_counts": dict(sorted(reason_counts.items())),
        "phrases": rows,
        "reviewed_inputs_created": False,
        "automatic_selection": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
        "network_used": False,
    }
    document["feedback_sha256"] = _document_sha256(document)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-", dir=destination.parent
    )
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        _write_json(temporary, document)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {**document, "output": str(destination)}


def _validate_lyric_order(
    canonical_lyrics: str,
    phrases: list[Mapping[str, Any]],
) -> None:
    canonical = _words(canonical_lyrics)
    position = 0
    for phrase in phrases:
        words = _words(str(phrase["lyrics"])).copy()
        found = _find_words(canonical, words, position)
        if found is None:
            raise ValueError(
                f"draft phrase {phrase['phrase_id']} is not in lyric order"
            )
        position = found + len(words)
    if position != len(canonical):
        raise ValueError("draft lyrics contain text outside the reviewed phrase roster")


def _verify_package(root: Path, manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != "sunofriend.vocal-comp-draft-review-package.v1":
        raise ValueError("unsupported vocal-comp draft review package")
    expected = manifest.get("package_sha256")
    payload = dict(manifest)
    payload.pop("package_sha256", None)
    if expected != _document_sha256(payload):
        raise ValueError("draft review package manifest hash does not match")
    for relative, record in manifest.get("artifacts", {}).items():
        _verify_file_record(root / _safe_relative(relative), record)


def _validate_review(seed: Mapping[str, Any], review: Mapping[str, Any]) -> None:
    if review.get("schema") != VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA:
        raise ValueError("unsupported vocal-comp draft review result")
    if review.get("draft_sha256") != seed.get("draft_sha256"):
        raise ValueError("review does not bind this exact draft")
    if review.get("status") != "reviewed" or not review.get("reviewed_at"):
        raise ValueError("draft review is incomplete")
    if not isinstance(review.get("reviewed_at"), str):
        raise ValueError("reviewed_at must be a non-empty string")
    if review.get("effects") != {
        "automatic_selection": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
    }:
        raise ValueError("draft review effect declaration is missing or unsupported")
    expected = [phrase["phrase_id"] for phrase in seed["phrases"]]
    rows = review.get("phrases")
    if not isinstance(rows, list) or [row.get("phrase_id") for row in rows] != expected:
        raise ValueError("review phrase roster does not match the draft")
    for row in rows:
        if row.get("lyrics_and_timing") != "approved":
            raise ValueError(f"lyrics/timing are not approved for {row.get('phrase_id')}")
        if row.get("target_melody") != "approved":
            raise ValueError(f"target melody is not approved for {row.get('phrase_id')}")


def _review_html(seed: Mapping[str, Any]) -> str:
    cards: list[str] = []
    for phrase in seed["phrases"]:
        phrase_id = html.escape(phrase["phrase_id"])
        cards.append(
            f'<section class="card" data-phrase="{phrase_id}">'
            f"<h2>{phrase_id}: {phrase['start_seconds']:.2f}-"
            f"{phrase['end_seconds']:.2f}s</h2>"
            f"<p class=lyrics>{html.escape(phrase['lyrics'])}</p>"
            "<div class=auditions><label>AI reference vocal"
            f'<audio controls preload="none" src="{html.escape(phrase["ai_reference_audition"])}"></audio></label>'
            "<label>Automatic target MIDI proxy"
            f'<audio controls preload="none" src="{html.escape(phrase["target_midi_audition"])}"></audio></label></div>'
            '<fieldset><legend>Do the displayed lyrics and phrase boundaries match what you hear?</legend>'
            '<label><input type=radio name="lt-'
            + phrase_id
            + '" value=approved> Approve</label><label><input type=radio name="lt-'
            + phrase_id
            + '" value=needs_change> Needs change</label></fieldset>'
            '<fieldset><legend>Is this target MIDI close enough to the intended sung melody for comp comparison?</legend>'
            '<label><input type=radio name="tm-'
            + phrase_id
            + '" value=approved> Approve</label><label><input type=radio name="tm-'
            + phrase_id
            + '" value=needs_change> Needs change</label></fieldset>'
            f'<label>Private note (optional)<textarea id="note-{phrase_id}"></textarea></label></section>'
        )
    payload = json.dumps(
        {
            "schema": VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA,
            "draft_sha256": seed["draft_sha256"],
            "phrase_ids": [phrase["phrase_id"] for phrase in seed["phrases"]],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width"><title>Vocal comp input review</title><style>
body{{font-family:system-ui,sans-serif;background:#10131a;color:#eef2ff;max-width:1050px;margin:2rem auto;padding:0 1rem}}.card,.intro{{background:#1b2030;border:1px solid #343c55;border-radius:12px;padding:1rem;margin:1rem 0}}.warning{{color:#ffd58a}}.lyrics{{font-size:1.1rem}}.auditions{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}audio{{display:block;width:100%;margin-top:.4rem}}fieldset{{margin:1rem 0;border:1px solid #46516f}}fieldset label{{margin-right:1.2rem}}textarea{{display:block;width:100%;min-height:4rem;background:#0e1118;color:#fff}}button{{padding:.7rem 1rem;background:#69d2ad;border:0;border-radius:8px;font-weight:700}}#fallback{{width:100%;min-height:10rem}}@media(max-width:700px){{.auditions{{grid-template-columns:1fr}}}}
</style></head><body><section class=intro><h1>Review automatic vocal-comp inputs</h1><p class=warning>Nothing on this page is reviewed yet. Playback records no preference. Approve only after hearing every phrase in both forms.</p><p>The AI vocal establishes the intended words and phrasing; the dry MIDI proxy exposes the automatic target notes. “Needs change” is a valid result and will keep the draft unresolved.</p></section>{''.join(cards)}<section class=intro><button id=export>Export review JSON</button><p id=status></p><textarea id=fallback readonly></textarea></section><script>
const binding={payload};
function selected(name){{return document.querySelector('input[name="'+name+'"]:checked')?.value||'not_reviewed'}}
document.getElementById('export').onclick=()=>{{const phrases=binding.phrase_ids.map(id=>({{phrase_id:id,lyrics_and_timing:selected('lt-'+id),target_melody:selected('tm-'+id),notes:document.getElementById('note-'+id).value}}));const complete=phrases.every(row=>row.lyrics_and_timing==='approved'&&row.target_melody==='approved');const value={{schema:binding.schema,draft_sha256:binding.draft_sha256,status:complete?'reviewed':'unresolved',reviewed_at:complete?new Date().toISOString():null,phrases,effects:{{automatic_selection:false,audio_comp_rendered:false,pitch_correction_applied:false}}}};const text=JSON.stringify(value,null,2)+'\\n';document.getElementById('fallback').value=text;document.getElementById('status').textContent=complete?'Complete reviewed JSON requested for download.':'Unresolved JSON requested; change the draft before promotion.';const blob=new Blob([text],{{type:'application/json'}}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=complete?'vocal-comp-draft.reviewed.json':'vocal-comp-draft.unresolved.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}};
</script></body></html>"""


__all__ = [
    "VOCAL_COMP_DRAFT_REVIEW_RESULT_SCHEMA",
    "VOCAL_COMP_DRAFT_REVIEW_SCHEMA",
    "VOCAL_COMP_DRAFT_FEEDBACK_SCHEMA",
    "VOCAL_COMP_REVIEWED_INPUTS_SCHEMA",
    "build_vocal_comp_draft_review",
    "record_vocal_comp_draft_feedback",
    "resolve_vocal_comp_draft_review",
]
