"""Bind, save and serve private fine-stem canary listening feedback."""

from __future__ import annotations

import hashlib
import html
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, Mapping

from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_canary_contract import validate_fine_stem_canary_report
from .separation_review_transport import (
    LocalReviewRequestHandler,
    atomic_write_private_json,
)


CANARY_REVIEW_SCHEMA = "sunofriend.fine-stem-canary-listening.v1"
_CATASTROPHIC_RESULTS = frozenset(
    {"not_tested", "no_catastrophic_defect", "catastrophic_defect", "cannot_tell"}
)
_USEFULNESS = frozenset(
    {"not_tested", "cannot_tell", "not_useful", "partly_useful", "useful"}
)
_PROBLEMS = frozenset({"not_tested", "cannot_tell", "none", "some", "severe"})
_MIDI = frozenset({"not_tested", "cannot_tell", "improved", "no_change", "worse"})


def canary_review_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"document_sha256", "saved_at"}
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_fine_stem_canary_review_seed(
    report: Mapping[str, Any]
) -> dict[str, Any]:
    """Build an inert, report-bound browser review document."""

    report = validate_fine_stem_canary_report(report)
    return {
        "schema": CANARY_REVIEW_SCHEMA,
        "document_sha256": "",
        "status": "human_listening_incomplete_no_selection",
        "profile_id": report["profile_id"],
        "report_sha256": report["report_sha256"],
        "target_role": report["target_role"],
        "cases": [
            {
                "case_id": case["case_id"],
                "target_role": report["target_role"],
                "played_items": [],
                "listened": False,
                "catastrophic_result": "not_tested",
                "catastrophic_details": "",
                "usefulness": "not_tested",
                "issues": {
                    "bleed": "not_tested",
                    "missing_content": "not_tested",
                    "artefacts": "not_tested",
                    "timing_or_join_problems": "not_tested",
                },
                "downstream_midi": "not_tested",
                "notes": "",
            }
            for case in report["cases"]
        ],
        "boundaries": {
            "review_selects_source": False,
            "review_starts_midi": False,
            "review_changes_profile_status": False,
            "poor_feedback_disables_core_four": False,
            "audio_included": False,
            "filenames_included": False,
            "telemetry_included": False,
        },
    }


def validate_fine_stem_canary_review(
    value: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate feedback against one exact immutable objective report."""

    objective = validate_fine_stem_canary_report(report)
    seed = build_fine_stem_canary_review_seed(objective)
    document = json.loads(json.dumps(value, allow_nan=False))
    if not isinstance(document, dict) or any(
        document.get(key) != seed[key]
        for key in (
            "schema",
            "profile_id",
            "report_sha256",
            "target_role",
            "boundaries",
        )
    ):
        raise ValueError("fine-stem canary review binding differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != len(seed["cases"]):
        raise ValueError("fine-stem canary review cases differ")
    expected = {case["case_id"]: case for case in seed["cases"]}
    complete = True
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or case.get("case_id") not in expected:
            raise ValueError("fine-stem canary review case identity differs")
        case_id = case["case_id"]
        if case_id in seen or case.get("target_role") != expected[case_id]["target_role"]:
            raise ValueError("fine-stem canary review case binding differs")
        seen.add(case_id)
        if not isinstance(case.get("listened"), bool):
            raise ValueError("fine-stem canary listened value differs")
        allowed_playback = ["reference", "target", "residual"]
        played_items = case.get(
            "played_items", allowed_playback if case["listened"] else []
        )
        if (
            not isinstance(played_items, list)
            or any(not isinstance(item, str) for item in played_items)
            or len(played_items) != len(set(played_items))
            or not set(played_items).issubset(allowed_playback)
            or case["listened"] != (set(played_items) == set(allowed_playback))
        ):
            raise ValueError("fine-stem canary playback evidence differs")
        case["played_items"] = played_items
        catastrophic = case.get("catastrophic_result")
        if catastrophic not in _CATASTROPHIC_RESULTS:
            raise ValueError("fine-stem catastrophic result differs")
        details = case.get("catastrophic_details")
        notes = case.get("notes")
        if (
            not isinstance(details, str)
            or len(details) > 5_000
            or not isinstance(notes, str)
            or len(notes) > 5_000
        ):
            raise ValueError("fine-stem canary review notes differ")
        if catastrophic == "catastrophic_defect" and not details.strip():
            raise ValueError("fine-stem catastrophic defect needs details")
        if case.get("usefulness") not in _USEFULNESS:
            raise ValueError("fine-stem canary usefulness differs")
        issues = case.get("issues")
        if (
            not isinstance(issues, dict)
            or set(issues)
            != {
                "bleed",
                "missing_content",
                "artefacts",
                "timing_or_join_problems",
            }
            or any(item not in _PROBLEMS for item in issues.values())
        ):
            raise ValueError("fine-stem canary issue ratings differ")
        if case.get("downstream_midi") not in _MIDI:
            raise ValueError("fine-stem downstream MIDI result differs")
        complete = complete and case["listened"] and catastrophic != "not_tested"
    expected_status = (
        "human_listening_complete_no_selection"
        if complete
        else "human_listening_incomplete_no_selection"
    )
    if document.get("status") != expected_status:
        raise ValueError("fine-stem canary review status differs")
    expected_hash = canary_review_document_sha256(document)
    if document.get("document_sha256") not in {"", expected_hash}:
        raise ValueError("fine-stem canary review hash differs")
    document["document_sha256"] = expected_hash
    return document


def _select(field: str, options: tuple[tuple[str, str], ...]) -> str:
    return f'<select data-field="{field}">' + "".join(
        f'<option value="{value}">{html.escape(label)}</option>'
        for value, label in options
    ) + "</select>"


def render_fine_stem_review(report: Mapping[str, Any]) -> str:
    """Render a bound local review with server-backed save and download."""

    objective = validate_fine_stem_canary_report(report)
    seed = build_fine_stem_canary_review_seed(objective)
    role = objective["target_role"]
    cards: list[str] = []
    problem_options = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("none", "None"),
        ("some", "Some"),
        ("severe", "Severe"),
    )
    for index, case in enumerate(objective["cases"]):
        artifacts = case["artifacts"]
        players = "".join(
            f'<label>{html.escape(label)}<audio controls preload="metadata" '
            f'data-player-id="{key}" '
            f'src="/{html.escape(artifacts[key]["relative_path"])}"></audio></label>'
            for key, label in (
                ("reference", "Reference mix"),
                ("target", role.title() + " estimate"),
                ("residual", "Residual after estimate"),
            )
        )
        issue_fields = "".join(
            f"<label>{html.escape(label)}{_select(field, problem_options)}</label>"
            for field, label in (
                ("bleed", "Bleed"),
                ("missing_content", "Missing target content"),
                ("artefacts", "Artefacts"),
                ("timing_or_join_problems", "Timing or join problems"),
            )
        ).replace('data-field="', 'data-issue="')
        cards.append(
            f"""
<section class="case" data-index="{index}">
  <p class="eyebrow">{html.escape(role)} · confirmed-present source case</p>
  <h2>{html.escape(case['title'])}</h2>
  <p>Frozen window: {case['window_seconds'][0]}–{case['window_seconds'][1]} seconds.</p>
  <div class="players">{players}</div>
  <p>Target plus residual reconstructs the reference at the persisted PCM24 clock. That proves accounting, not correct separation.</p>
  <p class="playback" data-playback>Playback recorded automatically: 0 items played.</p>
  <label>Catastrophic-output check{_select('catastrophic_result', (("not_tested", "Not tested"), ("no_catastrophic_defect", "No catastrophic defect"), ("catastrophic_defect", "Catastrophic defect"), ("cannot_tell", "Cannot tell")))}</label>
  <label>Catastrophic details (required only for a defect)<textarea data-field="catastrophic_details" rows="2"></textarea></label>
  <label>Musical usefulness{_select('usefulness', (("not_tested", "Not tested"), ("cannot_tell", "Cannot tell"), ("not_useful", "Not useful"), ("partly_useful", "Partly useful"), ("useful", "Useful")))}</label>
  <div class="issues">{issue_fields}</div>
  <label>Did downstream MIDI improve?{_select('downstream_midi', (("not_tested", "Not tested"), ("cannot_tell", "Cannot tell"), ("improved", "Improved"), ("no_change", "No change"), ("worse", "Worse")))}</label>
  <label>Optional private note<textarea data-field="notes" rows="3"></textarea></label>
</section>"""
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunofriend fine-stem canary review</title><style>
:root{{color-scheme:dark;background:#06101e;color:#f7f8fb;font:17px system-ui,sans-serif}}body{{max-width:1120px;margin:auto;padding:30px}}h1{{font-size:2.3rem}}.notice,.case{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.issues{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}label{{display:grid;gap:8px;margin:12px 0;font-weight:700}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button,a.button{{display:inline-block;font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e;text-decoration:none}}button.secondary,a.secondary{{background:#2a5576;color:white}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}#status{{min-height:1.5em;color:#82e7b3}}
</style></head><body><p>Sunofriend Studio challenger · local private review</p><h1>{html.escape(role.title())} canary review</h1>
<div class="notice"><b>No usefulness threshold blocks this evidence.</b> Poor, mixed, cannot-tell and not-tested musical feedback stays valid and does not disable core-four. Only the explicit catastrophic-output field records an objective stop-ship observation.</div>
{''.join(cards)}
<section class="case"><h2>Save local feedback</h2><p>No audio, paths, filenames or telemetry enter the JSON. Saving selects no source and starts no MIDI.</p>
<button id="save" type="button">Save review locally</button><a class="button secondary" href="/download-review">Download saved JSON</a><button class="secondary" id="copy" type="button">Copy text-only feedback</button>
<p id="status"></p><label>Always-available JSON/text fallback<textarea id="fallback" readonly></textarea></label></section>
<script id="seed" type="application/json">{seed_json}</script><script>
const seed=JSON.parse(document.getElementById('seed').textContent),cards=[...document.querySelectorAll('.case[data-index]')],storageKey=`sunofriend-fine-stem-${{seed.report_sha256}}`;let base=structuredClone(seed);
let ready=false,saveTimer=null,saveRunning=false,saveQueued=false;
function playbackState(card){{const players=[...card.querySelectorAll('audio')],played=players.filter(player=>player.dataset.played==='true').map(player=>player.dataset.playerId);card.querySelector('[data-playback]').textContent=played.length===players.length?`Playback recorded automatically: all ${{players.length}} items played.`:`Playback recorded automatically: ${{played.length}} of ${{players.length}} items played.`;return{{played,complete:players.length>0&&played.length===players.length}};}}
function collect(){{const out=structuredClone(base);cards.forEach((card,i)=>{{const row=out.cases[i],playback=playbackState(card);row.played_items=playback.played;row.listened=playback.complete;for(const field of ['catastrophic_result','catastrophic_details','usefulness','downstream_midi','notes'])row[field]=card.querySelector(`[data-field="${{field}}"]`).value;card.querySelectorAll('[data-issue]').forEach(el=>row.issues[el.dataset.issue]=el.value);}});out.status=out.cases.every(x=>x.listened&&x.catastrophic_result!=='not_tested')?'human_listening_complete_no_selection':'human_listening_incomplete_no_selection';out.document_sha256='';out.saved_at=new Date().toISOString();document.getElementById('fallback').value=JSON.stringify(out,null,2)+'\\n';try{{localStorage.setItem(storageKey,JSON.stringify(out));}}catch(error){{}}return out;}}
function hydrate(out){{if(!out||!Array.isArray(out.cases))return;base=structuredClone(out);out.cases.forEach((row,i)=>{{const card=cards[i];if(!card)return;const players=[...card.querySelectorAll('audio')],played=new Set(row.listened?players.map(player=>player.dataset.playerId):(row.played_items||[]));players.forEach(player=>player.dataset.played=played.has(player.dataset.playerId)?'true':'false');for(const field of ['catastrophic_result','catastrophic_details','usefulness','downstream_midi','notes'])card.querySelector(`[data-field="${{field}}"]`).value=row[field]||'';card.querySelectorAll('[data-issue]').forEach(el=>el.value=row.issues?.[el.dataset.issue]||'not_tested');}});collect();}}
async function saveNow(){{if(!ready)return;if(saveRunning){{saveQueued=true;return;}}saveRunning=true;const status=document.getElementById('status');status.textContent='Saving locally…';try{{const response=await fetch('/save-review',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(collect())}}),value=await response.json();if(!response.ok)throw new Error(value.error||'save failed');base=structuredClone(value);status.textContent=value.status==='human_listening_complete_no_selection'?'Saved locally. All catastrophic-output checks are complete.':'Progress saved locally automatically; play every item and complete each catastrophic-output check.';}}catch(error){{status.textContent=`Automatic save failed: ${{error.message}}. The same JSON remains below.`;}}finally{{saveRunning=false;if(saveQueued){{saveQueued=false;saveNow();}}}}}}
function scheduleSave(){{if(!ready)return;clearTimeout(saveTimer);saveTimer=setTimeout(saveNow,400);}}
cards.forEach(card=>card.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>{{player.dataset.played='true';collect();scheduleSave();}})));
document.addEventListener('input',()=>{{collect();scheduleSave();}});collect();let localValue=null;try{{localValue=JSON.parse(localStorage.getItem(storageKey));}}catch(error){{}}if(localValue)hydrate(localValue);fetch('/saved-result',{{cache:'no-store'}}).then(r=>r.ok?r.json():null).then(value=>{{if(value)hydrate(value);}}).catch(()=>{{}}).finally(()=>{{ready=true;collect();scheduleSave();}});
document.getElementById('save').onclick=saveNow;
document.getElementById('copy').onclick=async()=>{{const out=collect(),lines=[`Sunofriend ${{out.target_role}} canary feedback`,`Profile: ${{out.profile_id}}`,`Report: ${{out.report_sha256}}`,...out.cases.map(x=>`${{x.case_id}}: catastrophic=${{x.catastrophic_result}}; usefulness=${{x.usefulness}}; issues=${{JSON.stringify(x.issues)}}; MIDI=${{x.downstream_midi}}${{x.notes?`; notes=${{x.notes}}`:''}}`)],value=lines.join('\\n');let ok=false;try{{await navigator.clipboard.writeText(value);ok=true;}}catch(_e){{const box=document.getElementById('fallback');box.value=value;box.focus();box.select();ok=document.execCommand('copy');}}document.getElementById('status').textContent=ok?'Text-only feedback copied.':'Copy was blocked; select the text below.';}};
</script></body></html>"""


def build_fine_stem_review_server(
    root: str | Path, *, host: str = "127.0.0.1", port: int = 8769
) -> ThreadingHTTPServer:
    """Serve verified private artifacts and atomically save bound feedback."""

    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("fine-stem review server must bind to localhost")
    package = Path(root).resolve(strict=True)
    report = validate_fine_stem_canary_report(
        json.loads((package / "TECHNICAL/CANARY-REPORT.json").read_text())
    )
    # Render from the validated report so a repaired local server cannot serve
    # stale JavaScript embedded when the package was first published.
    page = render_fine_stem_review(report).encode("utf-8")
    result_path = package / "REVIEW/FINE-STEM-LISTENING.json"
    routes: dict[str, Path] = {}
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = (package / artifact["relative_path"]).resolve(strict=True)
            if (
                package not in path.parents
                or path.stat().st_size != artifact["bytes"]
                or file_sha256(path) != artifact["sha256"]
            ):
                raise ValueError("fine-stem review audio identity differs")
            routes["/" + artifact["relative_path"]] = path

    class Handler(LocalReviewRequestHandler):
        server_version = "SunofriendFineStemReview/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/REVIEW/fine_stem_review.html"}:
                self.send_no_store(200, "text/html; charset=utf-8", page)
            elif route == "/healthz":
                self.send_no_store(200, "application/json", b'{"status":"ok"}\n')
            elif route == "/saved-result":
                if result_path.is_file():
                    self.send_no_store(200, "application/json", result_path.read_bytes())
                else:
                    self.send_error(404)
            elif route == "/download-review":
                if not result_path.is_file():
                    self.send_error(404, "Save the review first")
                    return
                self.send_attachment(
                    result_path.read_bytes(),
                    filename="sunofriend-fine-stem-listening.json",
                    content_type="application/json; charset=utf-8",
                )
            elif route in routes:
                self.send_ranged_file(routes[route], "audio/wav")
            else:
                self.send_error(404)

        def do_HEAD(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in routes:
                self.send_ranged_file(routes[route], "audio/wav", body=False)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/save-review":
                self.send_error(404)
                return
            try:
                raw = self.read_review_json()
                value = validate_fine_stem_canary_review(raw, report)
                payload = atomic_write_private_json(result_path, value)
            except (OSError, UnicodeError, ValueError) as error:
                self.send_review_error(error)
                return
            self.send_no_store(200, "application/json", payload)

    return ThreadingHTTPServer((host, port), Handler)


__all__ = [
    "CANARY_REVIEW_SCHEMA",
    "build_fine_stem_canary_review_seed",
    "build_fine_stem_review_server",
    "canary_review_document_sha256",
    "render_fine_stem_review",
    "validate_fine_stem_canary_review",
]
