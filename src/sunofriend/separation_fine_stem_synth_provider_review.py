"""Source-visible local review for four qualified provider synth estimates."""

from __future__ import annotations

import hashlib
import html
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import stat
from typing import Any, Mapping
from urllib.parse import quote

from .separation_fine_stem_canary_audio import file_sha256
from .separation_review_transport import LocalReviewApplication
from .separation_fine_stem_synth_provider_qualification import (
    validate_fine_stem_synth_provider_qualification,
)


REVIEW_SCHEMA = "sunofriend.fine-stem-synth-provider-presence-review.v1"
_PRESENCE = {"not_tested", "present", "absent", "cannot_tell"}
_BREADTH = {
    "not_tested",
    "synth_only",
    "synth_or_keyboard_family",
    "mixed_or_broader",
    "cannot_tell",
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


def build_provider_review_seed(report: Mapping[str, Any]) -> dict[str, Any]:
    objective = validate_fine_stem_synth_provider_qualification(report)
    return {
        "schema": REVIEW_SCHEMA,
        "document_sha256": "",
        "status": "human_provider_presence_review_incomplete_no_selection",
        "qualification_document_sha256": objective["document_sha256"],
        "request_document_sha256": objective["request_document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "played_items": [],
                "listened": False,
                "provider_target_presence": "not_tested",
                "provider_role_breadth": "not_tested",
                "notes": "",
            }
            for case in objective["cases"]
        ],
        "boundaries": {
            "review_selects_source": False,
            "review_starts_midi": False,
            "review_activates_profile": False,
            "poor_feedback_disables_core_four": False,
            "provider_estimate_is_ground_truth": False,
            "cannot_tell_is_valid": True,
            "audio_included": False,
            "paths_or_filenames_included": False,
            "telemetry_included": False,
        },
    }


def validate_provider_review(
    value: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    objective = validate_fine_stem_synth_provider_qualification(report)
    seed = build_provider_review_seed(objective)
    document = json.loads(json.dumps(value, allow_nan=False))
    for key in (
        "schema",
        "qualification_document_sha256",
        "request_document_sha256",
        "boundaries",
    ):
        if document.get(key) != seed[key]:
            raise ValueError("provider presence review binding differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("provider presence review cases differ")
    expected = {case["case_id"] for case in objective["cases"]}
    seen: set[str] = set()
    complete = True
    for case in cases:
        case_id = case.get("case_id")
        if case_id not in expected or case_id in seen:
            raise ValueError("provider presence review case identity differs")
        seen.add(str(case_id))
        played = case.get("played_items")
        if (
            not isinstance(played, list)
            or len(played) != len(set(played))
            or not set(played).issubset({"source", "provider_synth"})
        ):
            raise ValueError("provider presence playback evidence differs")
        listened = set(played) == {"source", "provider_synth"}
        if case.get("listened") is not listened:
            raise ValueError("provider presence listened state differs")
        if case.get("provider_target_presence") not in _PRESENCE:
            raise ValueError("provider target-presence decision differs")
        if case.get("provider_role_breadth") not in _BREADTH:
            raise ValueError("provider role-breadth decision differs")
        notes = case.get("notes")
        if not isinstance(notes, str) or len(notes) > 5000:
            raise ValueError("provider presence notes differ")
        complete = (
            complete and listened and case["provider_target_presence"] != "not_tested"
        )
    expected_status = (
        "human_provider_presence_review_complete_no_selection"
        if complete
        else "human_provider_presence_review_incomplete_no_selection"
    )
    if document.get("status") != expected_status:
        raise ValueError("provider presence review status differs")
    expected_hash = review_document_sha256(document)
    if document.get("document_sha256") not in {"", expected_hash}:
        raise ValueError("provider presence review hash differs")
    document["document_sha256"] = expected_hash
    return document


def _select(attribute: str, values: tuple[tuple[str, str], ...]) -> str:
    return (
        f"<select {attribute}>"
        + "".join(
            f'<option value="{value}">{html.escape(label)}</option>'
            for value, label in values
        )
        + "</select>"
    )


def _review_script() -> str:
    return r"""
const seed = JSON.parse(document.getElementById('seed').textContent);
const cards = [...document.querySelectorAll('.case[data-index]')];
const key = `sunofriend-provider-synth-${seed.qualification_document_sha256}`;
let base = structuredClone(seed);
let ready = false;
let timer = null;
let running = false;
let queued = false;

function playback(card) {
  const played = [...card.querySelectorAll('audio[data-player-id]')]
    .filter(player => player.dataset.played === 'true')
    .map(player => player.dataset.playerId);
  card.querySelector('[data-playback]').textContent = played.length === 2
    ? 'Playback recorded automatically: source and provider estimate played.'
    : `Playback recorded automatically: ${played.length} of 2 items played.`;
  return played;
}

function collect() {
  const out = structuredClone(base);
  cards.forEach((card, index) => {
    const row = out.cases[index];
    row.played_items = playback(card);
    row.listened = row.played_items.length === 2;
    for (const field of ['provider_target_presence', 'provider_role_breadth', 'notes']) {
      row[field] = card.querySelector(`[data-field="${field}"]`).value;
    }
  });
  out.status = out.cases.every(row =>
    row.listened && row.provider_target_presence !== 'not_tested'
  )
    ? 'human_provider_presence_review_complete_no_selection'
    : 'human_provider_presence_review_incomplete_no_selection';
  out.document_sha256 = '';
  out.saved_at = new Date().toISOString();
  document.getElementById('fallback').value = `${JSON.stringify(out, null, 2)}\n`;
  try { localStorage.setItem(key, JSON.stringify(out)); } catch (_error) {}
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
    for (const field of ['provider_target_presence', 'provider_role_breadth', 'notes']) {
      card.querySelector(`[data-field="${field}"]`).value = row[field] || '';
    }
    playback(card);
  });
}

function loadLocal() {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value?.qualification_document_sha256 === seed.qualification_document_sha256
      ? value : null;
  } catch (_error) { return null; }
}

function newer(left, right) {
  if (!left) return right;
  if (!right) return left;
  return (Date.parse(left.saved_at || '') || 0) >= (Date.parse(right.saved_at || '') || 0)
    ? left : right;
}

async function save() {
  if (!ready) return;
  if (running) { queued = true; return; }
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
    document.getElementById('status').textContent =
      value.status === 'human_provider_presence_review_complete_no_selection'
        ? 'Saved locally; all four source/provider checks are complete.'
        : 'Progress saved locally automatically.';
  } catch (error) {
    document.getElementById('status').textContent =
      `Save failed: ${error.message}. The fallback JSON remains below.`;
  } finally {
    running = false;
    if (queued) { queued = false; save(); }
  }
}

function schedule() {
  if (!ready) return;
  clearTimeout(timer);
  timer = setTimeout(save, 250);
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
    document.getElementById('status').textContent =
      'Download failed; the review is still saved on this Mac and visible below.';
    return;
  }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await response.blob());
  link.download = 'sunofriend-provider-synth-presence-review.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  document.getElementById('status').textContent = 'Saved review JSON downloaded.';
}

function recordPlayback(player) {
  if (player.dataset.played === 'true') return;
  player.dataset.played = 'true';
  collect();
  schedule();
}

cards.forEach(card => card.querySelectorAll('audio[data-player-id]').forEach(player => {
  player.addEventListener('play', () => recordPlayback(player));
  player.addEventListener('playing', () => recordPlayback(player));
  player.addEventListener('timeupdate', () => {
    if (player.currentTime > 0) recordPlayback(player);
  });
  player.addEventListener('pause', () => {
    if (player.currentTime > 0) recordPlayback(player);
  });
  player.addEventListener('ended', () => recordPlayback(player));
}));
document.addEventListener('input', () => { collect(); schedule(); });
document.addEventListener('change', () => { collect(); schedule(); });

const local = loadLocal();
fetch('/saved-result', {cache: 'no-store'})
  .then(response => response.ok ? response.json() : null)
  .then(saved => hydrate(newer(local, saved)))
  .catch(() => hydrate(local))
  .finally(() => { ready = true; collect(); schedule(); });

document.getElementById('save').onclick = save;
document.getElementById('download').onclick = download;
""".strip()


def render_provider_review(report: Mapping[str, Any]) -> str:
    objective = validate_fine_stem_synth_provider_qualification(report)
    seed = build_provider_review_seed(objective)
    presence = (
        ("not_tested", "Not tested"),
        ("present", "Synth or keyboard content is present"),
        ("absent", "The target is absent"),
        ("cannot_tell", "Cannot tell"),
    )
    breadth = (
        ("not_tested", "Not tested (valid)"),
        ("synth_only", "Predominantly synth"),
        ("synth_or_keyboard_family", "Broader synth / keyboard family"),
        ("mixed_or_broader", "Mixed with other instruments"),
        ("cannot_tell", "Cannot tell"),
    )
    cards = []
    for index, case in enumerate(objective["cases"]):
        case_id = quote(case["case_id"], safe="")
        cards.append(
            f'''<section class="case" data-index="{index}"><p class="eyebrow">provider synth qualification · exact source visible</p><h2>{html.escape(case["title"])}</h2><p>Frozen {case["window_seconds"][0]}–{case["window_seconds"][1]} seconds. The provider label is a proposal, not truth.</p><div class="players"><section class="player"><h3>Source reference</h3><audio controls preload="metadata" data-player-id="source" src="/audio/{case_id}/reference.wav"></audio><p>The exact 15-second mix used by the current separator test.</p></section><section class="player"><h3>Suno provider estimate: Synth</h3><audio controls preload="metadata" data-player-id="provider_synth" src="/audio/{case_id}/provider_synth.wav"></audio><p>Private comparison estimate; it may include broader keyboard or other content.</p></section></div><p class="playback" data-playback>Playback recorded automatically: 0 of 2 items played.</p><div class="fields"><label>Does this estimate contain synth or keyboard content audible in the source?{_select('data-field="provider_target_presence"', presence)}</label><label>Optional role breadth{_select('data-field="provider_role_breadth"', breadth)}</label></div><label>Notes<textarea data-field="notes" rows="3"></textarea></label></section>'''
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunofriend provider synth review</title><style>:root{{color-scheme:dark;background:#06101e;color:#f7f8fb;font:17px system-ui,sans-serif}}body{{max-width:1200px;margin:auto;padding:30px}}.notice,.case{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.fields{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}}.player{{background:#091827;border:1px solid #294965;border-radius:14px;padding:16px}}label{{display:grid;gap:8px;margin:12px 0;font-weight:700}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button{{font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e}}button.secondary{{background:#2a5576;color:white}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback,#status{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}</style></head><body><p>Sunofriend Studio evidence · local private review</p><h1>Do the four provider estimates actually contain the missing synth target?</h1><div class="notice"><b>This is a presence check, not a pass/fail quality gate.</b> Listen to the source and its provider estimate. Playback is recorded automatically; there is no listened checkbox. Absent and cannot-tell results are valid and never disable core-four separation.</div>{"".join(cards)}<section class="case"><h2>Local review record</h2><p>No audio, paths, filenames or telemetry enter the saved review JSON. Progress is saved on this Mac after every playback or answer.</p><button id="save">Save review locally</button><button class="secondary" id="download">Download saved JSON</button><p id="status"></p><label>Always-available fallback JSON<textarea id="fallback" readonly></textarea></label></section><script id="seed" type="application/json">{seed_json}</script><script>{_review_script()}</script></body></html>"""


def _regular_artifact(root: Path, evidence: Mapping[str, Any]) -> Path:
    relative = str(evidence.get("relative_path", ""))
    if not relative or Path(relative).is_absolute():
        raise ValueError("provider review artifact path differs")
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("provider review artifact escapes root") from error
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError("provider review artifact is not regular")
    if path.stat().st_size != evidence.get("bytes") or file_sha256(
        path
    ) != evidence.get("sha256"):
        raise ValueError("provider review artifact identity differs")
    return path


def build_provider_review_server(
    root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8773,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("provider review must bind to localhost")
    package = Path(root).resolve(strict=True)
    report = validate_fine_stem_synth_provider_qualification(
        json.loads(
            (package / "TECHNICAL/PROVIDER-QUALIFICATION.json").read_text(
                encoding="utf-8"
            )
        )
    )
    page = render_provider_review(report).encode("utf-8")
    result_path = package / "REVIEW/PROVIDER-PRESENCE.json"
    routes: dict[str, tuple[Path, str]] = {}
    for case in report["cases"]:
        encoded = quote(case["case_id"], safe="")
        for role in ("reference", "provider_synth"):
            routes[f"/audio/{encoded}/{role}.wav"] = (
                _regular_artifact(package, case["artifacts"][role]),
                "audio/wav",
            )

    application = LocalReviewApplication(
        server_version="SunofriendProviderSynthReview/1",
        page=page,
        page_path="/REVIEW/provider_review.html",
        result_path=result_path,
        download_filename="sunofriend-provider-synth-presence-review.json",
        media_routes=routes,
        validate_review=lambda value: validate_provider_review(value, report),
    )
    return application.build_server(host=host, port=port)


__all__ = [
    "REVIEW_SCHEMA",
    "build_provider_review_seed",
    "build_provider_review_server",
    "render_provider_review",
    "review_document_sha256",
    "validate_provider_review",
]
