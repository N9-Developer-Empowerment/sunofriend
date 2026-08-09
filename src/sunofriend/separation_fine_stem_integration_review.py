"""Local, report-bound listening review for the private six-role canary."""

from __future__ import annotations

import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_integration_report import (
    ARTIFACT_ROLES,
    validate_fine_stem_integration_report,
)


REVIEW_SCHEMA = "sunofriend.fine-stem-six-role-integration-listening.v1"
_CATASTROPHIC = {"not_tested", "no_catastrophic_defect", "catastrophic_defect", "cannot_tell"}
_USEFULNESS = {"not_tested", "cannot_tell", "not_useful", "partly_useful", "useful"}
_ISSUES = {"not_tested", "cannot_tell", "none", "some", "severe"}


def review_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key not in {"document_sha256", "saved_at"}}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def build_integration_review_seed(report: Mapping[str, Any]) -> dict[str, Any]:
    objective = validate_fine_stem_integration_report(report)
    return {
        "schema": REVIEW_SCHEMA,
        "document_sha256": "",
        "status": "human_listening_incomplete_no_selection",
        "report_sha256": objective["report_sha256"],
        "plan_sha256": objective["plan_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "played_items": [],
                "listened": False,
                "catastrophic_result": "not_tested",
                "catastrophic_details": "",
                "usefulness": {"synth": "not_tested", "guitar": "not_tested"},
                "issues": {
                    role: {
                        "bleed": "not_tested",
                        "missing_content": "not_tested",
                        "artefacts": "not_tested",
                        "timing_or_join_problems": "not_tested",
                    }
                    for role in ("synth", "guitar")
                },
                "notes": "",
            }
            for case in objective["cases"]
        ],
        "boundaries": {
            "review_selects_source": False,
            "review_starts_midi": False,
            "review_activates_profile": False,
            "poor_feedback_disables_core_four": False,
            "secondary_target_absence_is_valid": True,
            "audio_included": False,
            "paths_or_filenames_included": False,
            "telemetry_included": False,
        },
    }


def validate_integration_review(value: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    objective = validate_fine_stem_integration_report(report)
    seed = build_integration_review_seed(objective)
    document = json.loads(json.dumps(value, allow_nan=False))
    for key in ("schema", "report_sha256", "plan_sha256", "boundaries"):
        if document.get(key) != seed[key]:
            raise ValueError("fine-stem integration review binding differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 8:
        raise ValueError("fine-stem integration review cases differ")
    expected = {case["case_id"] for case in objective["cases"]}
    seen: set[str] = set()
    complete = True
    for case in cases:
        case_id = case.get("case_id")
        if case_id not in expected or case_id in seen:
            raise ValueError("fine-stem integration review case identity differs")
        seen.add(case_id)
        played = case.get("played_items")
        if (
            not isinstance(played, list)
            or len(played) != len(set(played))
            or not set(played).issubset(ARTIFACT_ROLES)
        ):
            raise ValueError("fine-stem integration playback evidence differs")
        listened = set(played) == set(ARTIFACT_ROLES)
        if case.get("listened") is not listened:
            raise ValueError("fine-stem integration listened state differs")
        catastrophic = case.get("catastrophic_result")
        if catastrophic not in _CATASTROPHIC:
            raise ValueError("fine-stem integration catastrophic result differs")
        details = case.get("catastrophic_details")
        notes = case.get("notes")
        if not isinstance(details, str) or len(details) > 5000 or not isinstance(notes, str) or len(notes) > 5000:
            raise ValueError("fine-stem integration review notes differ")
        if catastrophic == "catastrophic_defect" and not details.strip():
            raise ValueError("fine-stem integration catastrophic defect needs details")
        usefulness = case.get("usefulness")
        if set(usefulness or {}) != {"synth", "guitar"} or any(value not in _USEFULNESS for value in usefulness.values()):
            raise ValueError("fine-stem integration usefulness differs")
        issues = case.get("issues")
        if set(issues or {}) != {"synth", "guitar"}:
            raise ValueError("fine-stem integration issue roles differ")
        for role in ("synth", "guitar"):
            if set(issues[role]) != {"bleed", "missing_content", "artefacts", "timing_or_join_problems"} or any(value not in _ISSUES for value in issues[role].values()):
                raise ValueError("fine-stem integration issue ratings differ")
        complete = complete and listened and catastrophic != "not_tested"
    expected_status = "human_listening_complete_no_selection" if complete else "human_listening_incomplete_no_selection"
    if document.get("status") != expected_status:
        raise ValueError("fine-stem integration review status differs")
    expected_hash = review_document_sha256(document)
    if document.get("document_sha256") not in {"", expected_hash}:
        raise ValueError("fine-stem integration review hash differs")
    document["document_sha256"] = expected_hash
    return document


def _select(attribute: str, values: tuple[tuple[str, str], ...]) -> str:
    return f'<select {attribute}>' + "".join(
        f'<option value="{value}">{html.escape(label)}</option>' for value, label in values
    ) + "</select>"


def _render_review_script(role_count: int) -> str:
    """Return readable JavaScript without Python escape or brace coupling."""

    return r'''
const seed = JSON.parse(document.getElementById('seed').textContent);
const cards = [...document.querySelectorAll('.case[data-index]')];
const key = `sunofriend-six-role-${seed.report_sha256}`;
let base = structuredClone(seed);
let ready = false;
let timer = null;
let running = false;
let queued = false;

function playback(card) {
  const all = [...card.querySelectorAll('audio')];
  const played = all
    .filter(player => player.dataset.played === 'true')
    .map(player => player.dataset.playerId);
  card.querySelector('[data-playback]').textContent = played.length === all.length
    ? `Playback recorded automatically: all ${all.length} items played.`
    : `Playback recorded automatically: ${played.length} of ${all.length} items played.`;
  return played;
}

function collect() {
  const out = structuredClone(base);
  cards.forEach((card, index) => {
    const row = out.cases[index];
    row.played_items = playback(card);
    row.listened = row.played_items.length === __ROLE_COUNT__;
    for (const field of ['catastrophic_result', 'catastrophic_details', 'notes']) {
      row[field] = card.querySelector(`[data-field="${field}"]`).value;
    }
    card.querySelectorAll('[data-usefulness]').forEach(control => {
      row.usefulness[control.dataset.usefulness] = control.value;
    });
    card.querySelectorAll('[data-issue]').forEach(control => {
      row.issues[control.dataset.issueRole][control.dataset.issue] = control.value;
    });
  });
  out.status = out.cases.every(row => row.listened && row.catastrophic_result !== 'not_tested')
    ? 'human_listening_complete_no_selection'
    : 'human_listening_incomplete_no_selection';
  out.document_sha256 = '';
  out.saved_at = new Date().toISOString();
  document.getElementById('fallback').value = `${JSON.stringify(out, null, 2)}\n`;
  try {
    localStorage.setItem(key, JSON.stringify(out));
  } catch (_error) {
    // The visible fallback remains available when browser storage is disabled.
  }
  return out;
}

function hydrate(out) {
  if (!out?.cases) return;
  base = structuredClone(out);
  out.cases.forEach((row, index) => {
    const card = cards[index];
    const played = new Set(row.played_items || []);
    card.querySelectorAll('audio').forEach(player => {
      player.dataset.played = played.has(player.dataset.playerId) ? 'true' : 'false';
    });
    for (const field of ['catastrophic_result', 'catastrophic_details', 'notes']) {
      card.querySelector(`[data-field="${field}"]`).value = row[field] || '';
    }
    card.querySelectorAll('[data-usefulness]').forEach(control => {
      control.value = row.usefulness?.[control.dataset.usefulness] || 'not_tested';
    });
    card.querySelectorAll('[data-issue]').forEach(control => {
      control.value = row.issues?.[control.dataset.issueRole]?.[control.dataset.issue] || 'not_tested';
    });
  });
}

function loadLocal() {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value?.report_sha256 === seed.report_sha256 ? value : null;
  } catch (_error) {
    return null;
  }
}

function newer(left, right) {
  if (!left) return right;
  if (!right) return left;
  const leftTime = Date.parse(left.saved_at || '') || 0;
  const rightTime = Date.parse(right.saved_at || '') || 0;
  return leftTime >= rightTime ? left : right;
}

async function save() {
  if (!ready) return;
  if (running) {
    queued = true;
    return;
  }
  running = true;
  try {
    const response = await fetch('/save-review', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(collect()),
    });
    const value = await response.json();
    if (!response.ok) throw Error(value.error || 'save failed');
    base = structuredClone(value);
    document.getElementById('status').textContent = value.status === 'human_listening_complete_no_selection'
      ? 'Saved locally; all playback and catastrophic checks complete.'
      : 'Progress saved locally automatically.';
  } catch (error) {
    document.getElementById('status').textContent = `Save failed: ${error.message}. The JSON remains below.`;
  } finally {
    running = false;
    if (queued) {
      queued = false;
      save();
    }
  }
}

function schedule() {
  if (!ready) return;
  clearTimeout(timer);
  timer = setTimeout(save, 400);
}

async function waitForSave() {
  while (running) {
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}

async function download() {
  if (!ready) return;
  await waitForSave();
  await save();
  await waitForSave();
  const response = await fetch('/download-review', {cache: 'no-store'});
  if (!response.ok) {
    document.getElementById('status').textContent = 'Download failed; the saved JSON remains below.';
    return;
  }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await response.blob());
  link.download = 'sunofriend-six-role-listening.json';
  link.click();
  URL.revokeObjectURL(link.href);
  document.getElementById('status').textContent = 'Saved review JSON downloaded.';
}

function recordPlayback(player) {
  if (player.dataset.played === 'true') return;
  player.dataset.played = 'true';
  collect();
  schedule();
}

cards.forEach(card => card.querySelectorAll('audio').forEach(player => {
  player.addEventListener('play', () => recordPlayback(player));
  player.addEventListener('playing', () => recordPlayback(player));
  player.addEventListener('timeupdate', () => {
    if (player.currentTime > 0) recordPlayback(player);
  });
}));
document.addEventListener('input', () => {
  collect();
  schedule();
});

const local = loadLocal();
fetch('/saved-result', {cache: 'no-store'})
  .then(response => response.ok ? response.json() : null)
  .then(saved => hydrate(newer(local, saved)))
  .catch(() => hydrate(local))
  .finally(() => {
    ready = true;
    collect();
    schedule();
  });

document.getElementById('save').onclick = save;
document.getElementById('download').onclick = download;
document.getElementById('copy').onclick = async () => {
  const out = collect();
  const value = [
    'Sunofriend private six-role integration feedback',
    `Report: ${out.report_sha256}`,
    ...out.cases.map(row => `${row.case_id}: catastrophic=${row.catastrophic_result}; synth=${row.usefulness.synth}; guitar=${row.usefulness.guitar}; notes=${row.notes}`),
  ].join('\n');
  try {
    await navigator.clipboard.writeText(value);
    document.getElementById('status').textContent = 'Text-only feedback copied.';
  } catch (_error) {
    const box = document.getElementById('fallback');
    box.value = value;
    box.select();
    document.execCommand('copy');
  }
};
'''.replace("__ROLE_COUNT__", str(role_count)).strip()


def render_integration_review(report: Mapping[str, Any]) -> str:
    objective = validate_fine_stem_integration_report(report)
    seed = build_integration_review_seed(objective)
    cards = []
    problem_options = (("not_tested", "Not tested"), ("cannot_tell", "Cannot tell"), ("none", "None"), ("some", "Some"), ("severe", "Severe"))
    for index, case in enumerate(objective["cases"]):
        players = "".join(
            f'<label>{html.escape(role.replace("_", " ").title())}<audio controls preload="metadata" data-player-id="{role}" src="/{html.escape(case["artifacts"][role]["relative_path"])}"></audio></label>'
            for role in ARTIFACT_ROLES
        )
        fine_fields = []
        for role in ("synth", "guitar"):
            issue_parts = []
            for field, label in (
                ("bleed", "Bleed"),
                ("missing_content", "Missing content"),
                ("artefacts", "Artefacts"),
                ("timing_or_join_problems", "Timing or joins"),
            ):
                attribute = 'data-issue-role="{}" data-issue="{}"'.format(
                    role, field
                )
                issue_parts.append(
                    f"<label>{html.escape(label)}"
                    f"{_select(attribute, problem_options)}</label>"
                )
            issue_fields = "".join(issue_parts)
            usefulness_attribute = 'data-usefulness="{}"'.format(role)
            fine_fields.append(
                f'<fieldset><legend>{role.title()}</legend><label>Usefulness'
                f'{_select(usefulness_attribute, (("not_tested", "Not tested"), ("cannot_tell", "Cannot tell"), ("not_useful", "Not useful"), ("partly_useful", "Partly useful"), ("useful", "Useful")))}</label><div class="issues">{issue_fields}</div></fieldset>'
            )
        cards.append(f'''<section class="case" data-index="{index}"><p class="eyebrow">Six-role private integration · {html.escape(case["reused_primary_role"])} reused</p><h2>{html.escape(case["title"])}</h2><p>Frozen window: {case["window_seconds"][0]}–{case["window_seconds"][1]} seconds. The complementary {html.escape(case["new_complementary_role"])} estimate was newly run.</p><div class="players">{players}</div><p class="playback" data-playback>Playback recorded automatically: 0 of {len(ARTIFACT_ROLES)} items played.</p><p>Exact reconstruction proves accounting only, not separation quality. A missing complementary target is valid feedback for this window.</p><label>Catastrophic-output check{_select('data-field="catastrophic_result"', (("not_tested", "Not tested"), ("no_catastrophic_defect", "No catastrophic defect"), ("catastrophic_defect", "Catastrophic defect"), ("cannot_tell", "Cannot tell")))}</label><label>Catastrophic details<textarea data-field="catastrophic_details" rows="2"></textarea></label>{''.join(fine_fields)}<label>Notes<textarea data-field="notes" rows="3"></textarea></label></section>''')
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    review_script = _render_review_script(len(ARTIFACT_ROLES))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunofriend six-role review</title><style>:root{{color-scheme:dark;background:#06101e;color:#f7f8fb;font:17px system-ui,sans-serif}}body{{max-width:1200px;margin:auto;padding:30px}}.notice,.case,fieldset{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.issues{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}label{{display:grid;gap:8px;margin:12px 0;font-weight:700}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button,a.button{{display:inline-block;font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e;text-decoration:none}}button.secondary,a.secondary{{background:#2a5576;color:white}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback,#status{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}</style></head><body><p>Sunofriend Studio challenger · local private review</p><h1>Vocals, drums, bass, synth, guitar and residual other</h1><div class="notice"><b>Poor or mixed feedback is valid and will not disable core-four.</b> There is no usefulness threshold for recording this canary. Playback is recorded automatically—there is no listened checkbox.</div>{''.join(cards)}<section class="case"><h2>Local feedback</h2><p>No audio, filenames, paths or telemetry enter the review JSON. Saving activates nothing and starts no MIDI.</p><button id="save">Save review locally</button><button class="secondary" id="download">Download saved JSON</button><button class="secondary" id="copy">Copy text-only feedback</button><p id="status"></p><label>Always-available fallback<textarea id="fallback" readonly></textarea></label></section><script id="seed" type="application/json">{seed_json}</script><script>{review_script}</script></body></html>'''


def build_integration_review_server(root: str | Path, *, host: str = "127.0.0.1", port: int = 8770) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("fine-stem integration review must bind to localhost")
    package = Path(root).resolve(strict=True)
    report = validate_fine_stem_integration_report(json.loads((package / "TECHNICAL/INTEGRATION-REPORT.json").read_text()))
    page = render_integration_review(report).encode("utf-8")
    result_path = package / "REVIEW/SIX-ROLE-LISTENING.json"
    routes: dict[str, Path] = {}
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = (package / artifact["relative_path"]).resolve(strict=True)
            if package not in path.parents or path.stat().st_size != artifact["bytes"] or file_sha256(path) != artifact["sha256"]:
                raise ValueError("fine-stem integration review audio identity differs")
            routes["/" + artifact["relative_path"]] = path

    class Handler(BaseHTTPRequestHandler):
        server_version = "SunofriendSixRoleReview/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/REVIEW/six_role_review.html"}:
                self._send(200, "text/html; charset=utf-8", page)
            elif route == "/healthz":
                self._send(200, "application/json", b'{"status":"ok"}\n')
            elif route == "/saved-result" and result_path.is_file():
                self._send(200, "application/json", result_path.read_bytes())
            elif route == "/download-review" and result_path.is_file():
                body = result_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="sunofriend-six-role-listening.json"',
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif route in routes:
                self._audio(routes[route])
            else:
                self.send_error(404)

        def do_HEAD(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in routes:
                self._audio(routes[route], body=False)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/save-review":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                self.send_error(413)
                return
            try:
                value = validate_integration_review(
                    json.loads(self.rfile.read(length)), report
                )
                payload = (
                    json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
                    + "\n"
                ).encode()
                temporary = result_path.with_suffix(".json.tmp")
                temporary.write_bytes(payload)
                temporary.chmod(0o600)
                temporary.replace(result_path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                self._send(
                    400,
                    "application/json",
                    json.dumps({"error": str(error)}).encode(),
                )
                return
            self._send(200, "application/json", payload)

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _audio(self, path: Path, *, body: bool = True) -> None:
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range")
            if header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
                if match is None or (not match.group(1) and not match.group(2)):
                    self.send_error(416)
                    return
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else end
                else:
                    start = max(0, size - int(match.group(2)))
                if start >= size or end < start:
                    self.send_error(416)
                    return
                end, status = min(end, size - 1), 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                with path.open("rb") as handle:
                    handle.seek(start)
                    self.wfile.write(handle.read(length))

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


__all__ = ["REVIEW_SCHEMA", "build_integration_review_seed", "build_integration_review_server", "render_integration_review", "review_document_sha256", "validate_integration_review"]
