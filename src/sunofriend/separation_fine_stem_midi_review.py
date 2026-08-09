"""Local review page for the private fine-stem downstream-MIDI canary."""

from __future__ import annotations

import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_midi_canary import (
    validate_fine_stem_midi_canary,
)


REVIEW_SCHEMA = "sunofriend.fine-stem-downstream-midi-listening.v1"
_USEFULNESS = {
    "not_tested",
    "cannot_tell",
    "not_useful",
    "partly_useful",
    "useful",
}
_WORKLOAD = {
    "not_tested",
    "cannot_tell",
    "low",
    "moderate",
    "high",
    "not_salvageable",
}
_COMPARISON = {
    "not_tested",
    "cannot_tell",
    "candidate_better",
    "control_better",
    "same",
}


def review_document_sha256(value: Mapping[str, Any]) -> str:
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


def build_midi_review_seed(report: Mapping[str, Any]) -> dict[str, Any]:
    objective = validate_fine_stem_midi_canary(report)
    return {
        "schema": REVIEW_SCHEMA,
        "document_sha256": "",
        "status": "human_listening_incomplete_no_selection",
        "canary_document_sha256": objective["document_sha256"],
        "plan_document_sha256": objective["plan"]["document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "played_items": [],
                "listened": False,
                "recognisable_notes": "not_tested",
                "timing_usefulness": "not_tested",
                "edit_workload": "not_tested",
                "candidate_vs_control": "not_tested",
                "notes": "",
            }
            for case in objective["cases"]
        ],
        "boundaries": {
            "review_selects_source": False,
            "review_starts_new_midi": False,
            "review_activates_profile": False,
            "poor_feedback_disables_six_role_evidence": False,
            "cannot_tell_is_valid": True,
            "not_tested_is_valid": True,
            "audio_included": False,
            "paths_or_filenames_included": False,
            "telemetry_included": False,
        },
    }


def validate_midi_review(
    value: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    objective = validate_fine_stem_midi_canary(report)
    seed = build_midi_review_seed(objective)
    document = json.loads(json.dumps(value, allow_nan=False))
    for key in (
        "schema",
        "canary_document_sha256",
        "plan_document_sha256",
        "boundaries",
    ):
        if document.get(key) != seed[key]:
            raise ValueError("fine-stem MIDI review binding differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 8:
        raise ValueError("fine-stem MIDI review cases differ")
    expected = {case["case_id"] for case in objective["cases"]}
    seen: set[str] = set()
    complete = True
    for case in cases:
        case_id = case.get("case_id")
        if case_id not in expected or case_id in seen:
            raise ValueError("fine-stem MIDI review case identity differs")
        seen.add(str(case_id))
        played = case.get("played_items")
        if (
            not isinstance(played, list)
            or len(played) != len(set(played))
            or not set(played).issubset({"A", "B"})
        ):
            raise ValueError("fine-stem MIDI review playback evidence differs")
        listened = set(played) == {"A", "B"}
        if case.get("listened") is not listened:
            raise ValueError("fine-stem MIDI review listened state differs")
        if case.get("recognisable_notes") not in _USEFULNESS:
            raise ValueError("fine-stem MIDI recognisable-note rating differs")
        if case.get("timing_usefulness") not in _USEFULNESS:
            raise ValueError("fine-stem MIDI timing rating differs")
        if case.get("edit_workload") not in _WORKLOAD:
            raise ValueError("fine-stem MIDI edit-workload rating differs")
        if case.get("candidate_vs_control") not in _COMPARISON:
            raise ValueError("fine-stem MIDI comparison rating differs")
        notes = case.get("notes")
        if not isinstance(notes, str) or len(notes) > 5000:
            raise ValueError("fine-stem MIDI review notes differ")
        complete = complete and listened and all(
            case[field] != "not_tested"
            for field in (
                "recognisable_notes",
                "timing_usefulness",
                "edit_workload",
                "candidate_vs_control",
            )
        )
    expected_status = (
        "human_listening_complete_no_selection"
        if complete
        else "human_listening_incomplete_no_selection"
    )
    if document.get("status") != expected_status:
        raise ValueError("fine-stem MIDI review status differs")
    expected_hash = review_document_sha256(document)
    if document.get("document_sha256") not in {"", expected_hash}:
        raise ValueError("fine-stem MIDI review hash differs")
    document["document_sha256"] = expected_hash
    return document


def _select(attribute: str, values: tuple[tuple[str, str], ...]) -> str:
    return f"<select {attribute}>" + "".join(
        f'<option value="{value}">{html.escape(label)}</option>'
        for value, label in values
    ) + "</select>"


def _review_script() -> str:
    return r'''
const seed = JSON.parse(document.getElementById('seed').textContent);
const cards = [...document.querySelectorAll('.case[data-index]')];
const key = `sunofriend-fine-midi-${seed.canary_document_sha256}`;
let base = structuredClone(seed);
let ready = false;
let timer = null;
let running = false;
let queued = false;

function playback(card) {
  const players = [...card.querySelectorAll('audio')];
  const played = players
    .filter(player => player.dataset.played === 'true')
    .map(player => player.dataset.playerId);
  card.querySelector('[data-playback]').textContent = played.length === 2
    ? 'Playback recorded automatically: both MIDI previews played.'
    : `Playback recorded automatically: ${played.length} of 2 previews played.`;
  return played;
}

function comparisonValue(card) {
  const display = card.querySelector('[data-field="display_preference"]').value;
  if (!['a_better', 'b_better'].includes(display)) return display;
  const chosen = display === 'a_better' ? card.dataset.aKind : card.dataset.bKind;
  return chosen === 'candidate' ? 'candidate_better' : 'control_better';
}

function displayValue(card, stored) {
  if (!['candidate_better', 'control_better'].includes(stored)) return stored || 'not_tested';
  const chosen = stored === 'candidate_better' ? 'candidate' : 'control';
  return card.dataset.aKind === chosen ? 'a_better' : 'b_better';
}

function collect() {
  const out = structuredClone(base);
  cards.forEach((card, index) => {
    const row = out.cases[index];
    row.played_items = playback(card);
    row.listened = row.played_items.length === 2;
    for (const field of ['recognisable_notes', 'timing_usefulness', 'edit_workload', 'notes']) {
      row[field] = card.querySelector(`[data-field="${field}"]`).value;
    }
    row.candidate_vs_control = comparisonValue(card);
  });
  out.status = out.cases.every(row => row.listened && [
    row.recognisable_notes,
    row.timing_usefulness,
    row.edit_workload,
    row.candidate_vs_control,
  ].every(value => value !== 'not_tested'))
    ? 'human_listening_complete_no_selection'
    : 'human_listening_incomplete_no_selection';
  out.document_sha256 = '';
  out.saved_at = new Date().toISOString();
  document.getElementById('fallback').value = `${JSON.stringify(out, null, 2)}\n`;
  try {
    localStorage.setItem(key, JSON.stringify(out));
  } catch (_error) {
    // The visible fallback remains available if browser storage is disabled.
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
    for (const field of ['recognisable_notes', 'timing_usefulness', 'edit_workload', 'notes']) {
      card.querySelector(`[data-field="${field}"]`).value = row[field] || '';
    }
    card.querySelector('[data-field="display_preference"]').value = displayValue(
      card,
      row.candidate_vs_control,
    );
    playback(card);
  });
}

function loadLocal() {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value?.canary_document_sha256 === seed.canary_document_sha256 ? value : null;
  } catch (_error) {
    return null;
  }
}

function newer(left, right) {
  if (!left) return right;
  if (!right) return left;
  return (Date.parse(left.saved_at || '') || 0) >= (Date.parse(right.saved_at || '') || 0)
    ? left
    : right;
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
      ? 'Saved locally; all eight comparisons are complete.'
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
  while (running) await new Promise(resolve => setTimeout(resolve, 50));
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
  link.download = 'sunofriend-fine-stem-midi-listening.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
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
'''.strip()


def render_midi_canary_review(report: Mapping[str, Any]) -> str:
    objective = validate_fine_stem_midi_canary(report)
    seed = build_midi_review_seed(objective)
    usefulness = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("not_useful", "Not useful"),
        ("partly_useful", "Partly useful"),
        ("useful", "Useful"),
    )
    workload = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("low", "Low"),
        ("moderate", "Moderate"),
        ("high", "High"),
        ("not_salvageable", "Not salvageable"),
    )
    comparison = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("a_better", "MIDI A is better"),
        ("b_better", "MIDI B is better"),
        ("same", "About the same"),
    )
    cards = []
    for index, case in enumerate(objective["cases"]):
        order = case["blind_order"]
        players = []
        if len(order) != 2:
            raise ValueError("fine-stem MIDI blind order differs")
        for display, kind in zip(("A", "B"), order):
            output = case["outputs"][kind]
            preview = output["preview"]["relative_path"]
            midi = output["midi"]["relative_path"]
            players.append(
                f'<section class="player"><h3>MIDI {display}</h3>'
                f'<audio controls preload="metadata" data-player-id="{display}" '
                f'src="/{html.escape(preview)}"></audio>'
                f'<p>{output["note_count"]} notes · '
                f'<a href="/{html.escape(midi)}" download>Download MIDI {display}</a></p>'
                "</section>"
            )
        cards.append(
            f'''<section class="case" data-index="{index}" data-a-kind="{order[0]}" data-b-kind="{order[1]}"><p class="eyebrow">{html.escape(case["confirmed_present_target_role"])} · private MIDI comparison</p><h2>{html.escape(case["title"])}</h2><p>{case["metadata"]["bpm"]:g} BPM · {html.escape(case["metadata"]["key"])} · frozen {case["window_seconds"][0]}–{case["window_seconds"][1]} seconds.</p><div class="players">{''.join(players)}</div><p class="playback" data-playback>Playback recorded automatically: 0 of 2 previews played.</p><p>Rate the isolated {html.escape(case["confirmed_present_target_role"])} MIDI. Then compare it with the same-transcriber grouped-other control. A dry General MIDI sound is only a neutral note/timing proxy.</p><div class="fields"><label>Recognisable notes{_select('data-field="recognisable_notes"', usefulness)}</label><label>Timing usefulness{_select('data-field="timing_usefulness"', usefulness)}</label><label>Expected edit workload{_select('data-field="edit_workload"', workload)}</label><label>Blind comparison{_select('data-field="display_preference"', comparison)}</label></div><label>Notes<textarea data-field="notes" rows="3"></textarea></label></section>'''
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunofriend fine-stem MIDI review</title><style>:root{{color-scheme:dark;background:#06101e;color:#f7f8fb;font:17px system-ui,sans-serif}}body{{max-width:1200px;margin:auto;padding:30px}}.notice,.case{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.fields{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}.player{{background:#091827;border:1px solid #294965;border-radius:14px;padding:16px}}label{{display:grid;gap:8px;margin:12px 0;font-weight:700}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button{{font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e}}button.secondary{{background:#2a5576;color:white}}a{{color:#75e4f1}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback,#status{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}</style></head><body><p>Sunofriend Studio evidence · local private review</p><h1>Does an isolated synth or guitar stem improve editable MIDI?</h1><div class="notice"><b>There is no pass rating.</b> Poor, mixed, cannot-tell and not-tested outcomes are valid. Playback is recorded automatically; there is no listened checkbox. Saving never selects a source or activates a profile.</div>{''.join(cards)}<section class="case"><h2>Local review record</h2><p>No audio, filenames, paths or telemetry enter this JSON.</p><button id="save">Save review locally</button><button class="secondary" id="download">Download saved JSON</button><p id="status"></p><label>Always-available fallback JSON<textarea id="fallback" readonly></textarea></label></section><script id="seed" type="application/json">{seed_json}</script><script>{_review_script()}</script></body></html>'''


def _regular_artifact(root: Path, evidence: Mapping[str, Any]) -> Path:
    relative = str(evidence.get("relative_path", ""))
    if not relative or Path(relative).is_absolute():
        raise ValueError("fine-stem MIDI review artifact path differs")
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("fine-stem MIDI review artifact escapes root") from error
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError("fine-stem MIDI review artifact is not regular")
    if (
        path.stat().st_size != evidence.get("bytes")
        or file_sha256(path) != evidence.get("sha256")
    ):
        raise ValueError("fine-stem MIDI review artifact identity differs")
    return path


def build_midi_review_server(
    root: str | Path, *, host: str = "127.0.0.1", port: int = 8772
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("fine-stem MIDI review must bind to localhost")
    package = Path(root).resolve(strict=True)
    report = validate_fine_stem_midi_canary(
        json.loads(
            (package / "TECHNICAL/MIDI-CANARY-REPORT.json").read_text(
                encoding="utf-8"
            )
        )
    )
    page = render_midi_canary_review(report).encode("utf-8")
    result_path = package / "REVIEW/MIDI-LISTENING.json"
    routes: dict[str, tuple[Path, str]] = {}
    for case in report["cases"]:
        for output in case["outputs"].values():
            preview = _regular_artifact(package, output["preview"])
            midi = _regular_artifact(package, output["midi"])
            routes["/" + output["preview"]["relative_path"]] = (
                preview,
                "audio/wav",
            )
            routes["/" + output["midi"]["relative_path"]] = (
                midi,
                "audio/midi",
            )

    class Handler(BaseHTTPRequestHandler):
        server_version = "SunofriendFineStemMidiReview/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/REVIEW/midi_review.html"}:
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
                    'attachment; filename="sunofriend-fine-stem-midi-listening.json"',
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif route in routes:
                path, content_type = routes[route]
                self._file(path, content_type)
            else:
                self.send_error(404)

        def do_HEAD(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in routes:
                path, content_type = routes[route]
                self._file(path, content_type, body=False)
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
                value = validate_midi_review(
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

        def _file(
            self, path: Path, content_type: str, *, body: bool = True
        ) -> None:
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
            self.send_header("Content-Type", content_type)
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


__all__ = [
    "REVIEW_SCHEMA",
    "build_midi_review_seed",
    "build_midi_review_server",
    "render_midi_canary_review",
    "review_document_sha256",
    "validate_midi_review",
]
