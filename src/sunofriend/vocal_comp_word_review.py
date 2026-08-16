"""Private listening review for auxiliary vocal-comp word alignment."""

from __future__ import annotations

import html
import json
import os
import shutil
import tempfile
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from .vocal_comp import (
    _copy_private,
    _document_sha256,
    _file,
    _file_record,
    _sha256,
    _write_json,
    _zero_effects,
)
from .vocal_comp_words import VOCAL_COMP_WORD_ALIGNMENT_SCHEMA


VOCAL_COMP_WORD_REVIEW_SCHEMA = "sunofriend.vocal-comp-word-review.v1"
VOCAL_COMP_WORD_REVIEW_PACKAGE_SCHEMA = (
    "sunofriend.vocal-comp-word-review-package.v1"
)
VOCAL_COMP_WORD_REVIEW_RESULT_SCHEMA = (
    "sunofriend.vocal-comp-word-review-result.v1"
)
_CONTEXT_SECONDS = 0.65


def build_vocal_comp_word_review(
    alignment: str | Path,
    *,
    lyrics: str | Path,
    audio: Mapping[str, str | Path],
    out_dir: str | Path,
) -> dict[str, Any]:
    """Build a hash-bound local page; playback and drafts have zero effects."""

    alignment_path = _file(alignment, "word alignment")
    lyrics_path = _file(lyrics, "canonical lyrics")
    document = _read_json(alignment_path)
    if document.get("schema") != VOCAL_COMP_WORD_ALIGNMENT_SCHEMA:
        raise ValueError(
            f"word alignment schema must be {VOCAL_COMP_WORD_ALIGNMENT_SCHEMA}"
        )
    if document.get("status") != "complete_unreviewed":
        raise ValueError("word alignment must remain complete_unreviewed")
    if any(
        document.get(field) is not False
        for field in (
            "automatic_selection",
            "audio_comp_rendered",
            "pitch_correction_applied",
        )
    ):
        raise ValueError("word alignment contains unsupported downstream effects")
    _verify_document_hash(document, "alignment_sha256")
    if _sha256(lyrics_path) != document.get("canonical_lyrics", {}).get("sha256"):
        raise ValueError("canonical lyrics do not match the word alignment")
    if lyrics_path.stat().st_size != document.get("canonical_lyrics", {}).get("bytes"):
        raise ValueError("canonical lyric byte count does not match")
    sources = document.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("word alignment contains no sources")
    if set(audio) != set(sources):
        raise ValueError("review audio source IDs must match the alignment exactly")
    audio_paths: dict[str, Path] = {}
    for source_id in sorted(sources):
        path = _file(audio[source_id], f"{source_id} review audio")
        identity = sources[source_id].get("audio", {})
        if path.stat().st_size != identity.get("bytes") or _sha256(path) != identity.get(
            "sha256"
        ):
            raise ValueError(f"{source_id} audio does not match the alignment")
        audio_paths[source_id] = path

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"word-review output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        source_dir = temporary / "SOURCE"
        audio_dir = temporary / "AUDIO"
        source_dir.mkdir(mode=0o700)
        audio_dir.mkdir(mode=0o700)
        copied_alignment = source_dir / "word-alignment.json"
        copied_lyrics = source_dir / "canonical-lyrics.txt"
        _copy_private(alignment_path, copied_alignment)
        _copy_private(lyrics_path, copied_lyrics)

        lines = _line_records(document)
        line_windows = _line_windows(lines, sources)
        leading = {
            source_id: _leading_insertions(source["operations"])
            for source_id, source in sources.items()
        }
        adlib_window = _adlib_window(leading, audio_paths)
        review_sources: list[dict[str, Any]] = []
        for source_id in sorted(sources, key=_source_sort_key):
            source_audio_dir = audio_dir / source_id
            source_audio_dir.mkdir(mode=0o700)
            full_audio = source_audio_dir / "full.wav"
            _copy_private(audio_paths[source_id], full_audio)
            adlib_audio = source_audio_dir / "adlib-context.wav"
            _write_exact_excerpt(
                audio_paths[source_id], adlib_audio, *adlib_window
            )
            source = sources[source_id]
            source_lines: list[dict[str, Any]] = []
            for line in lines:
                line_index = line["line_index"]
                window = line_windows[line_index]
                excerpt = source_audio_dir / f"line-{line_index:02d}.wav"
                _write_exact_excerpt(audio_paths[source_id], excerpt, *window)
                operations = [
                    row
                    for row in source["operations"]
                    if isinstance(row.get("canonical"), Mapping)
                    and row["canonical"].get("line_index") == line_index
                ]
                observed = _unique_observed(operations)
                source_lines.append(
                    {
                        "line_index": line_index,
                        "audio": str(excerpt.relative_to(temporary)),
                        "recognized_text": _heard_text(observed),
                        "automatic_state": _automatic_line_state(operations),
                        "operation_counts": _counts(
                            str(row["operation"]) for row in operations
                        ),
                        "differences": _differences(operations),
                    }
                )
            transcript_words = _unique_observed(source["operations"])
            review_sources.append(
                {
                    "source_id": source_id,
                    "display_name": _display_name(source_id),
                    "kind": (
                        "ai_reference" if source_id == "ai-reference" else "human_take"
                    ),
                    "full_audio": str(full_audio.relative_to(temporary)),
                    "full_transcript": _heard_text(transcript_words),
                    "observed_word_count": source["observed_word_count"],
                    "exact_canonical_coverage": source["exact_canonical_coverage"],
                    "candidate_canonical_coverage": source[
                        "candidate_canonical_coverage"
                    ],
                    "adlib": {
                        "audio": str(adlib_audio.relative_to(temporary)),
                        "recognized_text": _heard_text(leading[source_id]),
                        "automatic_presence": bool(leading[source_id]),
                    },
                    "lines": source_lines,
                }
            )

        seed = {
            "schema": VOCAL_COMP_WORD_REVIEW_SCHEMA,
            "status": "automatic_unreviewed",
            "alignment": _file_record(copied_alignment, relative_to=temporary),
            "alignment_sha256": document["alignment_sha256"],
            "alignment_policy": document.get("alignment_policy"),
            "canonical_lyrics": _file_record(copied_lyrics, relative_to=temporary),
            "canonical_text": lyrics_path.read_text(encoding="utf-8"),
            "lines": [
                {
                    **line,
                    "review_window_start_seconds": line_windows[line["line_index"]][0],
                    "review_window_end_seconds": line_windows[line["line_index"]][1],
                }
                for line in lines
            ],
            "adlib": {
                "candidate_text": _adlib_candidate_text(leading),
                "review_window_start_seconds": adlib_window[0],
                "review_window_end_seconds": adlib_window[1],
                "canonical_lyrics_mutated": False,
            },
            "sources": review_sources,
            "review_contract": {
                "playback_creates_decision": False,
                "visible_default_creates_decision": False,
                "browser_draft_creates_review": False,
                "export_required_for_feedback": True,
                "review_does_not_select_a_take": True,
                "review_does_not_approve_target_melody": True,
                "cannot_tell_is_valid": True,
            },
            "result_schema": VOCAL_COMP_WORD_REVIEW_RESULT_SCHEMA,
            "effects": _zero_effects(),
            "network_used": False,
        }
        seed["review_seed_sha256"] = _document_sha256(seed)
        seed_path = temporary / "vocal-comp-word-review.json"
        _write_json(seed_path, seed)
        html_path = temporary / "vocal-comp-word-review.html"
        html_path.write_text(_review_html(seed), encoding="utf-8")
        os.chmod(html_path, 0o600)
        artifacts = {
            str(path.relative_to(temporary)): _file_record(
                path, relative_to=temporary
            )
            for path in sorted(temporary.rglob("*"))
            if path.is_file()
        }
        package = {
            "schema": VOCAL_COMP_WORD_REVIEW_PACKAGE_SCHEMA,
            "status": "complete_unreviewed",
            "review_seed_sha256": seed["review_seed_sha256"],
            "seed": _file_record(seed_path, relative_to=temporary),
            "html": _file_record(html_path, relative_to=temporary),
            "artifacts": artifacts,
            "effects": _zero_effects(),
            "network_used": False,
        }
        package["package_sha256"] = _document_sha256(package)
        _write_json(temporary / "vocal-comp-word-review-package.json", package)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **package,
        "output_directory": str(destination),
        "review_html": str(destination / "vocal-comp-word-review.html"),
        "review_seed": str(destination / "vocal-comp-word-review.json"),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def _verify_document_hash(document: Mapping[str, Any], field: str) -> None:
    expected = document.get(field)
    payload = dict(document)
    payload.pop(field, None)
    if expected != _document_sha256(payload):
        raise ValueError(f"{field} does not match the document")


def _line_records(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for word in document.get("canonical_words", []):
        grouped.setdefault(int(word["line_index"]), []).append(word)
    if not grouped:
        raise ValueError("alignment contains no canonical lyric lines")
    return [
        {
            "line_index": line_index,
            "canonical_text": " ".join(str(word["text"]) for word in words),
            "canonical_word_count": len(words),
        }
        for line_index, words in sorted(grouped.items())
    ]


def _line_windows(
    lines: Sequence[Mapping[str, Any]], sources: Mapping[str, Any]
) -> dict[int, tuple[float, float]]:
    result: dict[int, tuple[float, float]] = {}
    for line in lines:
        starts: list[float] = []
        ends: list[float] = []
        for source in sources.values():
            for row in source["operations"]:
                canonical = row.get("canonical")
                observed = row.get("observed")
                if (
                    isinstance(canonical, Mapping)
                    and canonical.get("line_index") == line["line_index"]
                    and isinstance(observed, Mapping)
                ):
                    starts.append(float(observed["start_seconds"]))
                    ends.append(float(observed["end_seconds"]))
        if not starts:
            raise ValueError(f"lyric line {line['line_index']} has no timed evidence")
        start = max(0.0, min(starts) - _CONTEXT_SECONDS)
        end = max(ends) + _CONTEXT_SECONDS
        result[int(line["line_index"])] = (round(start, 6), round(end, 6))
    return result


def _leading_insertions(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in operations:
        if isinstance(row.get("canonical"), Mapping):
            break
        if row.get("operation") == "insertion_adlib_candidate" and isinstance(
            row.get("observed"), Mapping
        ):
            result.append(dict(row["observed"]))
    return result


def _adlib_window(
    leading: Mapping[str, Sequence[Mapping[str, Any]]],
    audio_paths: Mapping[str, Path],
) -> tuple[float, float]:
    starts = [float(word["start_seconds"]) for words in leading.values() for word in words]
    ends = [float(word["end_seconds"]) for words in leading.values() for word in words]
    if not starts:
        raise ValueError("alignment contains no leading ad-lib candidate")
    maximum_duration = min(_audio_duration(path) for path in audio_paths.values())
    return (
        round(max(0.0, min(starts) - 0.9), 6),
        round(min(maximum_duration, max(ends) + 0.9), 6),
    )


def _audio_duration(path: Path) -> float:
    import soundfile

    info = soundfile.info(path)
    if info.frames <= 0 or info.samplerate <= 0:
        raise ValueError(f"audio contains no samples: {path.name}")
    return info.frames / info.samplerate


def _write_exact_excerpt(
    source: Path, destination: Path, start: float, end: float
) -> None:
    import soundfile

    with soundfile.SoundFile(source) as handle:
        sample_rate = int(handle.samplerate)
        first = max(0, int(round(start * sample_rate)))
        final = min(len(handle), int(round(end * sample_rate)))
        if final <= first:
            raise ValueError("review excerpt has no samples")
        handle.seek(first)
        values = handle.read(final - first, dtype="float64", always_2d=True)
    soundfile.write(destination, values, sample_rate, subtype="PCM_24")
    os.chmod(destination, 0o600)


def _unique_observed(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for row in operations:
        observed = row.get("observed")
        if isinstance(observed, Mapping):
            indexed[int(observed["observed_index"])] = dict(observed)
    return [indexed[index] for index in sorted(indexed)]


def _heard_text(observed: Sequence[Mapping[str, Any]]) -> str:
    return " ".join(str(word["text"]).strip() for word in observed).strip()


def _automatic_line_state(operations: Sequence[Mapping[str, Any]]) -> str:
    kinds = [str(row["operation"]) for row in operations]
    if kinds and all(kind == "match" for kind in kinds):
        return "exact_stt_candidate"
    if kinds and all(kind == "omission_candidate" for kind in kinds):
        return "no_timed_words_candidate"
    return "difference_candidate"


def _differences(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "operation": row["operation"],
            "canonical": (
                row["canonical"]["text"]
                if isinstance(row.get("canonical"), Mapping)
                else None
            ),
            "observed": (
                row["observed"]["text"]
                if isinstance(row.get("observed"), Mapping)
                else None
            ),
            "probability": (
                row["observed"].get("probability")
                if isinstance(row.get("observed"), Mapping)
                else None
            ),
        }
        for row in operations
        if row.get("operation") != "match"
    ]


def _counts(values: Sequence[str] | Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _adlib_candidate_text(
    leading: Mapping[str, Sequence[Mapping[str, Any]]]
) -> str:
    candidates = [_heard_text(words) for words in leading.values() if words]
    if not candidates:
        return ""
    lengths = [len(value.split()) for value in candidates]
    target_length = int(median(lengths))
    return next(
        value for value in candidates if len(value.split()) == target_length
    )


def _source_sort_key(source_id: str) -> tuple[int, str]:
    return (0 if source_id == "ai-reference" else 1, source_id)


def _display_name(source_id: str) -> str:
    if source_id == "ai-reference":
        return "AI reference"
    if source_id.startswith("take-"):
        return "Take " + source_id.removeprefix("take-")
    return source_id.replace("-", " ").title()


def _review_html(seed: Mapping[str, Any]) -> str:
    payload = json.dumps(seed, ensure_ascii=False).replace("</", "<\\/")
    source_options = "".join(
        f'<option value="{html.escape(source["source_id"])}">'
        f'{html.escape(source["display_name"])}</option>'
        for source in seed["sources"]
    )
    full_players = "".join(
        _full_source_html(source) for source in seed["sources"]
    )
    adlib_rows = "".join(_adlib_source_html(source) for source in seed["sources"])
    line_sections = "".join(
        _line_review_html(line, seed["sources"]) for line in seed["lines"]
    )
    line_nav = "".join(
        f'<a href="#line-{line["line_index"]}">{line["line_index"]}</a>'
        for line in seed["lines"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Heart Sees — word and phrase review</title>
<style>
:root{{--bg:#0b1020;--panel:#121a2d;--panel2:#19233a;--ink:#f5f7ff;--muted:#aeb9d3;--line:#354462;--accent:#7ee0c4;--warn:#ffd27a;--bad:#ff9a9a;--good:#96e6ac;--focus:#a8c7ff}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:linear-gradient(145deg,#09101d,#11182b 45%,#0b1020);color:var(--ink);font:16px/1.48 system-ui,-apple-system,sans-serif}}
main{{max-width:1440px;margin:auto;padding:1.2rem}}h1{{font-size:clamp(1.8rem,4vw,3rem);margin:.3rem 0}}h2{{margin:.2rem 0 1rem}}h3{{margin:.2rem 0}}p{{max-width:85ch}}a{{color:var(--accent)}}.card{{background:rgba(18,26,45,.96);border:1px solid var(--line);border-radius:16px;padding:1rem;margin:1rem 0;box-shadow:0 12px 30px #0004}}.hero{{border-color:#4e6989}}.warning{{border-left:5px solid var(--warn);padding-left:1rem}}.fine{{color:var(--muted);font-size:.91rem}}.pill{{display:inline-flex;padding:.2rem .55rem;border:1px solid var(--line);border-radius:999px;margin:.15rem;color:var(--muted)}}.pill.flag{{color:var(--warn);border-color:#8b6b30}}.pill.exact{{color:var(--good);border-color:#38744a}}audio{{width:100%;margin:.35rem 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.8rem}}.source-full{{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:.8rem}}blockquote{{margin:.5rem 0;color:#dce4fa}}.sticky{{position:sticky;top:0;z-index:20;background:#0b1020ee;backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:.65rem 0}}.toolbar{{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}}.progress{{height:10px;min-width:180px;flex:1;background:#26324a;border-radius:99px;overflow:hidden}}.progress>span{{display:block;height:100%;width:0;background:linear-gradient(90deg,#4ac7a4,#91eacb)}}button,select,input[type=number],textarea{{font:inherit}}button{{background:#293956;color:var(--ink);border:1px solid #506589;border-radius:9px;padding:.55rem .8rem;cursor:pointer}}button.primary{{background:#168766;border-color:#66d8b8;font-weight:700}}button.danger{{background:#552d38}}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{{outline:3px solid var(--focus);outline-offset:2px}}.line-card{{scroll-margin-top:90px}}.line-head{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:1rem}}.canonical{{font-size:1.25rem;font-weight:700}}.window{{color:var(--muted)}}.source-row{{display:grid;grid-template-columns:minmax(170px,.72fr) minmax(250px,1.2fr) minmax(300px,1.7fr);gap:.8rem;background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:.85rem;margin:.75rem 0}}.source-row.flagged{{border-color:#8b6b30}}.source-row.exact{{border-color:#356547}}.recognized{{background:#0d1425;border-radius:8px;padding:.55rem;min-height:3rem}}.difference{{color:var(--warn)}}fieldset{{border:0;padding:0;margin:.45rem 0}}legend{{font-weight:650;margin-bottom:.3rem}}.choices{{display:flex;flex-wrap:wrap;gap:.35rem}}.choices label{{border:1px solid var(--line);border-radius:8px;padding:.34rem .5rem;cursor:pointer;color:#d8e0f3}}.choices label:has(input:checked){{background:#315b53;border-color:var(--accent);color:#fff}}.choices input{{margin-right:.25rem}}textarea{{width:100%;min-height:3.5rem;background:#0d1425;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:.55rem}}input[type=number],select{{background:#0d1425;color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:.4rem}}.boundary-adjust{{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}}.review-meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem}}.review-meta>div{{min-width:0}}.review-meta code{{overflow-wrap:anywhere;word-break:break-all}}.navlinks a{{display:inline-flex;align-items:center;justify-content:center;width:2.1rem;height:2.1rem;border:1px solid var(--line);border-radius:50%;text-decoration:none;margin:.15rem}}.hidden-by-filter{{display:none}}#status{{min-height:1.5rem;color:var(--warn)}}#exportText{{width:100%;min-height:12rem}}@media(max-width:920px){{.source-row{{grid-template-columns:1fr}}.sticky{{position:static}}}}
</style></head><body><main>
<section class="card hero"><p class="pill">Private local review</p><p class="pill flag">Automatic STT — not truth</p><h1>The Heart Sees: words, ad-lib and phrase boundaries</h1><p>This page is designed to produce development evidence before any melody ranking. Listen for <strong>what was actually sung</strong>, whether Whisper represented it correctly, and whether each shared lyric-line window is useful. Do not judge pitch here unless it prevents you understanding the words.</p><p class="warning"><strong>Nothing is selected or approved by playback.</strong> Browser draft saving only protects your form work. Sunofriend receives feedback only when you explicitly export the JSON and provide it for recording.</p><div class="review-meta"><div><strong>Alignment</strong><br><code>{html.escape(str(seed['alignment_sha256']))}</code></div><div><strong>Known lyrics</strong><br>{len(seed['lines'])} lines; canonical and unchanged</div><div><strong>Sources</strong><br>{len(seed['sources'])}: one AI reference and five human takes</div></div></section>
<div class="sticky"><div class="toolbar"><strong id="progressText">0 reviewed</strong><div class="progress" aria-label="Review progress"><span id="progressBar"></span></div><label>Show <select id="rowFilter"><option value="all">all source rows</option><option value="flagged">automatic differences only</option><option value="incomplete">unanswered rows only</option></select></label><label>Source <select id="sourceFilter"><option value="all">all sources</option>{source_options}</select></label><button id="saveDraft">Save browser draft</button></div></div>
<section class="card"><h2>1. Establish the canonical intent</h2><div class="grid"><fieldset><legend>Are the seven supplied lyric lines the intended words?</legend>{_choices('overview-canonical','canonical_lyrics_status',(('canonical_correct','Yes, canonical'),('needs_change','Needs change'),('cannot_tell','Cannot tell')), required=True)}</fieldset><fieldset><legend>Is the STT evidence clear enough to review phrase mapping?</legend>{_choices('overview-evidence','evidence_usability',(('usable','Yes'),('partly_usable','Partly'),('not_usable','No'),('cannot_tell','Cannot tell')), required=True)}</fieldset></div><label>Overall lyric/STT notes<textarea id="overview-notes" data-field="overview_notes" placeholder="Recurring misrecognitions, pronunciation, accent, recording issues…"></textarea></label></section>
<section class="card"><h2>Full-source context</h2><p class="fine">Use these to hear continuity and punch-ins. Only one player runs at a time. Playback changes no answer.</p><div class="grid">{full_players}</div></section>
<section class="card" id="adlib"><h2>2. Review the non-canonical opening phrase</h2><p class="canonical">Automatic candidate: “{html.escape(seed['adlib']['candidate_text'])}”</p><p class="window">Shared window {seed['adlib']['review_window_start_seconds']:.2f}–{seed['adlib']['review_window_end_seconds']:.2f} seconds. This phrase is not in the supplied lyrics.</p><div class="grid"><fieldset><legend>What words are actually sung?</legend>{_choices('adlib-text','adlib_text_status',(('confirmed','Candidate text is correct'),('partly_correct','Partly correct'),('wrong','Wrong'),('cannot_tell','Cannot tell')), required=True)}</fieldset><fieldset><legend>What should this phrase do in the intended song?</legend>{_choices('adlib-role','adlib_intended_role',(('keep_ai','Keep as AI'),('keep_human','Keep as human'),('duet_candidate','Explore as duet'),('remove','Remove'),('cannot_decide','Cannot decide yet')), required=True)}</fieldset><fieldset><legend>Is its shared comparison window suitable?</legend>{_choices('adlib-window','adlib_window_status',(('good','Good'),('needs_adjustment','Needs adjustment'),('cannot_tell','Cannot tell')), required=True)}</fieldset></div><div class="boundary-adjust"><label>Preferred start <input type="number" step="0.01" min="0" id="adlib-start" data-field="adlib_start_seconds" placeholder="seconds"></label><label>Preferred end <input type="number" step="0.01" min="0" id="adlib-end" data-field="adlib_end_seconds" placeholder="seconds"></label></div><label>Ad-lib notes<textarea id="adlib-notes" data-field="adlib_notes" placeholder="Exact wording, who should sing it, overlap, breath or timing observations…"></textarea></label><h3>Source-by-source ad-lib evidence</h3>{adlib_rows}</section>
<section class="card"><h2>3. Review every canonical lyric line</h2><p>For each source, separate three questions: what was sung relative to the canonical line; whether Whisper represented it correctly; and whether it should proceed to later melody review. “Proceed” is eligibility feedback, <strong>not take selection</strong>.</p><nav class="navlinks" aria-label="Lyric line links">{line_nav}</nav></section>
{line_sections}
<section class="card" id="finish"><h2>4. Export explicit feedback</h2><p>Complete export requires every radio group. Notes and adjusted times are optional, but add them wherever an answer needs explanation. “Cannot tell” is a valid completed answer.</p><div class="toolbar"><button id="exportDraft">Export current draft JSON</button><button class="primary" id="completeExport">Complete review and export JSON</button><button class="danger" id="clearDraft">Clear browser draft</button></div><p id="status" role="status"></p><textarea id="exportText" readonly aria-label="Exported review JSON"></textarea></section>
</main><script>
const seed={payload};
const storageKey='sunofriend-word-review:'+seed.review_seed_sha256;
const requiredNames=[...new Set([...document.querySelectorAll('input[data-required="true"]')].map(x=>x.name))];
function checked(name){{return document.querySelector(`input[name="${{CSS.escape(name)}}"]:checked`)?.value||'not_reviewed'}}
function field(id){{const el=document.getElementById(id);return el?el.value:''}}
function sourceReview(sourceId,prefix){{return {{source_id:sourceId,heard_content_status:checked(prefix+'-content'),stt_accuracy:checked(prefix+'-stt'),later_melody_review_eligibility:checked(prefix+'-eligible'),notes:field(prefix+'-notes')}}}}
function buildResult(forceComplete=false){{const lineReviews=seed.lines.map(line=>({{line_index:line.line_index,canonical_text:line.canonical_text,window_status:checked('line-'+line.line_index+'-window'),preferred_start_seconds:field('line-'+line.line_index+'-start')||null,preferred_end_seconds:field('line-'+line.line_index+'-end')||null,line_notes:field('line-'+line.line_index+'-notes'),sources:seed.sources.map(source=>sourceReview(source.source_id,'line-'+line.line_index+'-'+source.source_id))}}));const result={{schema:seed.result_schema,review_seed_sha256:seed.review_seed_sha256,alignment_sha256:seed.alignment_sha256,status:'unresolved',completed_at:null,overview:{{canonical_lyrics_status:checked('overview-canonical'),evidence_usability:checked('overview-evidence'),notes:field('overview-notes')}},adlib:{{candidate_text:seed.adlib.candidate_text,text_status:checked('adlib-text'),intended_role:checked('adlib-role'),window_status:checked('adlib-window'),preferred_start_seconds:field('adlib-start')||null,preferred_end_seconds:field('adlib-end')||null,notes:field('adlib-notes'),sources:seed.sources.map(source=>sourceReview(source.source_id,'adlib-'+source.source_id))}},lines:lineReviews,effects:{{automatic_selection:false,audio_comp_rendered:false,pitch_correction_applied:false,canonical_lyrics_mutated:false,target_melody_approved:false}}}};const missing=requiredNames.filter(name=>checked(name)==='not_reviewed');if(forceComplete&&missing.length===0){{result.status='completed_review';result.completed_at=new Date().toISOString()}}return {{result,missing}}}}
function formState(){{const values={{}};document.querySelectorAll('input,textarea,select').forEach(el=>{{if(!el.id&&!el.name)return;if(el.type==='radio'){{if(el.checked)values['radio:'+el.name]=el.value}}else if(!['rowFilter','sourceFilter'].includes(el.id)) values['field:'+(el.id||el.name)]=el.value}});return values}}
function restore(values){{Object.entries(values||{{}}).forEach(([key,value])=>{{if(key.startsWith('radio:')){{const el=document.querySelector(`input[name="${{CSS.escape(key.slice(6))}}"]`+`[value="${{CSS.escape(value)}}"]`);if(el)el.checked=true}}else if(key.startsWith('field:')){{const el=document.getElementById(key.slice(6));if(el)el.value=value}}}});updateProgress();applyFilters()}}
function saveDraft(silent=false){{localStorage.setItem(storageKey,JSON.stringify(formState()));if(!silent)document.getElementById('status').textContent='Draft saved only in this browser. No review JSON was recorded.'}}
function updateProgress(){{const done=requiredNames.filter(name=>checked(name)!=='not_reviewed').length;document.getElementById('progressText').textContent=`${{done}} of ${{requiredNames.length}} required decisions`;document.getElementById('progressBar').style.width=(requiredNames.length?100*done/requiredNames.length:0)+'%'}}
function applyFilters(){{const mode=field('rowFilter'),source=field('sourceFilter');document.querySelectorAll('.source-row').forEach(row=>{{let show=source==='all'||row.dataset.source===source;if(mode==='flagged')show=show&&row.dataset.automatic!=='exact_stt_candidate';if(mode==='incomplete'){{const names=[...row.querySelectorAll('input[type=radio]')].map(x=>x.name);show=show&&names.some(name=>checked(name)==='not_reviewed')}}row.classList.toggle('hidden-by-filter',!show)}})}}
function download(result,name){{const text=JSON.stringify(result,null,2)+'\\n';document.getElementById('exportText').value=text;const blob=new Blob([text],{{type:'application/json'}}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}}
document.addEventListener('change',event=>{{if(event.target.matches('input,textarea')){{saveDraft(true);updateProgress();applyFilters()}}}});document.addEventListener('input',event=>{{if(event.target.matches('textarea,input[type=number]'))saveDraft(true)}});document.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{{if(other!==player)other.pause()}})));document.getElementById('rowFilter').onchange=applyFilters;document.getElementById('sourceFilter').onchange=applyFilters;document.getElementById('saveDraft').onclick=()=>saveDraft(false);document.getElementById('exportDraft').onclick=()=>{{const {{result,missing}}=buildResult(false);download(result,'vocal-comp-word-review.unresolved.json');document.getElementById('status').textContent=`Draft exported with ${{missing.length}} required decisions unanswered. It has zero downstream effects.`}};document.getElementById('completeExport').onclick=()=>{{const {{result,missing}}=buildResult(true);if(missing.length){{document.getElementById('status').textContent=`Complete ${{missing.length}} remaining required decisions first. “Cannot tell” is valid.`;document.querySelector(`input[name="${{CSS.escape(missing[0])}}"]`)?.scrollIntoView({{behavior:'smooth',block:'center'}});return}}download(result,'vocal-comp-word-review.completed.json');document.getElementById('status').textContent='Completed review JSON exported. It remains feedback only until explicitly recorded.'}};document.getElementById('clearDraft').onclick=()=>{{if(confirm('Clear only the browser-saved form draft? Audio and evidence are unchanged.')){{localStorage.removeItem(storageKey);document.querySelectorAll('input[type=radio]').forEach(x=>x.checked=false);document.querySelectorAll('textarea,input[type=number]').forEach(x=>x.value='');updateProgress();applyFilters();document.getElementById('status').textContent='Browser draft cleared. Evidence files were not changed.'}}}};try{{restore(JSON.parse(localStorage.getItem(storageKey)||'{{}}'))}}catch(_error){{updateProgress()}}
</script></body></html>"""


def _full_source_html(source: Mapping[str, Any]) -> str:
    coverage = 100.0 * float(source["exact_canonical_coverage"])
    return (
        f'<article class="source-full"><h3>{html.escape(source["display_name"])}</h3>'
        f'<span class="pill">{source["observed_word_count"]} heard words</span>'
        f'<span class="pill">{coverage:.1f}% exact STT coverage</span>'
        f'<audio controls preload="metadata" src="{html.escape(source["full_audio"])}"></audio>'
        f'<details><summary>Automatic full transcript</summary><blockquote>{html.escape(source["full_transcript"])}</blockquote></details></article>'
    )


def _adlib_source_html(source: Mapping[str, Any]) -> str:
    prefix = f'adlib-{source["source_id"]}'
    state = "flagged" if source["adlib"]["automatic_presence"] else "exact"
    heard = source["adlib"]["recognized_text"] or "No leading words recognized"
    decisions = _source_decisions(
        prefix,
        content_legend="What was sung vs ad-lib candidate?",
    )
    return f"""<article class="source-row {state}" data-source="{html.escape(source['source_id'])}" data-automatic="{'difference_candidate' if source['adlib']['automatic_presence'] else 'no_timed_words_candidate'}"><div><h3>{html.escape(source['display_name'])}</h3><span class="pill {'flag' if source['adlib']['automatic_presence'] else ''}">{'STT heard ad-lib' if source['adlib']['automatic_presence'] else 'STT heard none'}</span><audio controls preload="metadata" src="{html.escape(source['adlib']['audio'])}"></audio></div><div><strong>Automatic text</strong><div class="recognized">{html.escape(heard)}</div></div><div>{decisions}<textarea id="{prefix}-notes" placeholder="Exact words, timing, confidence or delivery notes…"></textarea></div></article>"""


def _line_review_html(
    line: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]
) -> str:
    line_index = line["line_index"]
    rows = "".join(
        _line_source_html(line_index, source) for source in sources
    )
    return f"""<section class="card line-card" id="line-{line_index}"><div class="line-head"><div><span class="pill">Line {line_index}</span><h2 class="canonical">{html.escape(line['canonical_text'])}</h2></div><div class="window">Shared window<br><strong>{line['review_window_start_seconds']:.2f}–{line['review_window_end_seconds']:.2f}s</strong></div></div><fieldset><legend>Is this shared line window suitable across the available takes?</legend>{_choices(f'line-{line_index}-window','window_status',(('good','Good'),('needs_adjustment','Needs adjustment'),('cannot_tell','Cannot tell')),required=True)}</fieldset><div class="boundary-adjust"><label>Preferred start <input type="number" step="0.01" min="0" id="line-{line_index}-start" placeholder="seconds"></label><label>Preferred end <input type="number" step="0.01" min="0" id="line-{line_index}-end" placeholder="seconds"></label></div><label>Line-level notes<textarea id="line-{line_index}-notes" placeholder="Boundary, shared pronunciation or lyric-unit notes…"></textarea></label>{rows}<p><a href="#finish">Go to export</a> · <a href="#line-{max(1,line_index-1)}">Previous line</a></p></section>"""


def _line_source_html(line_index: int, source: Mapping[str, Any]) -> str:
    item = next(row for row in source["lines"] if row["line_index"] == line_index)
    prefix = f'line-{line_index}-{source["source_id"]}'
    state = item["automatic_state"]
    class_name = "exact" if state == "exact_stt_candidate" else "flagged"
    label = {
        "exact_stt_candidate": "Exact STT candidate",
        "no_timed_words_candidate": "No words timed",
        "difference_candidate": "STT difference",
    }[state]
    differences = "".join(_difference_html(row) for row in item["differences"])
    differences = differences or "<li>None automatically flagged</li>"
    heard = item["recognized_text"] or "No words aligned to this canonical line"
    return f"""<article class="source-row {class_name}" data-source="{html.escape(source['source_id'])}" data-automatic="{state}"><div><h3>{html.escape(source['display_name'])}</h3><span class="pill {'exact' if class_name=='exact' else 'flag'}">{label}</span><audio controls preload="metadata" src="{html.escape(item['audio'])}"></audio></div><div><strong>Words assigned by STT</strong><div class="recognized">{html.escape(heard)}</div><details><summary>Automatic differences</summary><ul>{differences}</ul></details></div><div>{_source_decisions(prefix)}<textarea id="{prefix}-notes" placeholder="Correct words, misrecognition, punch-in gap or eligibility reason…"></textarea></div></article>"""


def _difference_html(row: Mapping[str, Any]) -> str:
    probability = row.get("probability")
    probability_text = (
        f" ({100 * float(probability):.0f}% ASR probability)"
        if probability is not None
        else ""
    )
    operation = str(row["operation"]).replace("_candidate", "").replace("_", " ")
    canonical = str(row.get("canonical") or "—")
    observed = str(row.get("observed") or "—")
    return (
        f'<li><span class="difference">{html.escape(operation)}</span>: '
        f"{html.escape(canonical)} → {html.escape(observed)}"
        f"{probability_text}</li>"
    )


def _source_decisions(
    prefix: str,
    *,
    content_legend: str = "What was sung vs canonical?",
) -> str:
    return (
        f"<fieldset><legend>{html.escape(content_legend)}</legend>"
        + _choices(
            f"{prefix}-content",
            "content",
            (
                ("matches", "Matches"),
                ("word_changes", "Word changes"),
                ("incomplete", "Incomplete"),
                ("absent", "Absent"),
                ("cannot_tell", "Cannot tell"),
            ),
            required=True,
        )
        + "</fieldset><fieldset><legend>Was the STT text accurate?</legend>"
        + _choices(
            f"{prefix}-stt",
            "stt",
            (
                ("accurate", "Accurate"),
                ("partly_accurate", "Partly"),
                ("inaccurate", "Inaccurate"),
                ("cannot_tell", "Cannot tell"),
            ),
            required=True,
        )
        + "</fieldset><fieldset><legend>Proceed to later melody review?</legend>"
        + _choices(
            f"{prefix}-eligible",
            "eligible",
            (
                ("yes", "Yes"),
                ("no", "No"),
                ("pickup_needed", "Pickup needed"),
                ("cannot_tell", "Cannot tell"),
            ),
            required=True,
        )
        + "</fieldset>"
    )


def _choices(
    name: str,
    _field: str,
    options: Sequence[tuple[str, str]],
    *,
    required: bool,
) -> str:
    required_value = "true" if required else "false"
    return '<div class="choices">' + "".join(
        f'<label><input type="radio" name="{html.escape(name)}" '
        f'value="{html.escape(value)}" data-required="{required_value}"> '
        f'{html.escape(label)}</label>'
        for value, label in options
    ) + "</div>"


__all__ = [
    "VOCAL_COMP_WORD_REVIEW_PACKAGE_SCHEMA",
    "VOCAL_COMP_WORD_REVIEW_RESULT_SCHEMA",
    "VOCAL_COMP_WORD_REVIEW_SCHEMA",
    "build_vocal_comp_word_review",
]
