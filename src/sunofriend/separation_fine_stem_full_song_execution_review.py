"""Report-bound local review for the private full-song six-role canary."""

from __future__ import annotations

import hashlib
import html
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, Mapping

from .separation_fine_stem_full_song_execution_contract import (
    ARTIFACT_ROLES,
    validate_full_song_report,
)
from .separation_fine_stem_full_song_plan_contract import (
    validate_fine_stem_full_song_plan,
)
from .separation_review_transport import (
    LocalReviewRequestHandler,
    atomic_write_private_json,
)


REVIEW_SCHEMA = "sunofriend.fine-stem-full-song-six-role-listening.v1"
_CATASTROPHIC = {
    "not_tested",
    "no_catastrophic_defect",
    "catastrophic_defect",
    "cannot_tell",
}
_USEFULNESS = {
    "not_tested",
    "cannot_tell",
    "not_useful",
    "partly_useful",
    "useful",
}
_ISSUES = {"not_tested", "cannot_tell", "none", "some", "severe"}
_ISSUE_FIELDS = (
    "bleed",
    "missing_content",
    "artefacts",
    "timing_or_join_problems",
)
_CORE_REVIEW_ROLES = ("vocals", "drums", "bass", "other")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _presence_ids(case: Mapping[str, Any]) -> list[str]:
    return [
        f"{target['target_role']}:{target['window_seconds'][0]}-{target['window_seconds'][1]}"
        for target in case["confirmed_present_targets"]
    ]


def _review_roles(case: Mapping[str, Any]) -> list[str]:
    return [*_CORE_REVIEW_ROLES, *case["scored_target_roles"]]


def build_full_song_review_seed(
    report: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    objective = validate_full_song_report(report, plan)
    return {
        "schema": REVIEW_SCHEMA,
        "document_sha256": "",
        "status": "human_listening_incomplete_no_selection",
        "report_sha256": objective["report_sha256"],
        "plan_sha256": objective["plan_sha256"],
        "cases": [
            {
                "track_id": case["track_id"],
                "played_items": [],
                "listened": False,
                "confirmed_windows_played": [],
                "confirmed_windows_replayed": False,
                "catastrophic_result": "not_tested",
                "catastrophic_details": "",
                "overall_usefulness": "not_tested",
                "role_usefulness": {role: "not_tested" for role in _review_roles(case)},
                "issues": {
                    role: {field: "not_tested" for field in _ISSUE_FIELDS}
                    for role in _review_roles(case)
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
            "unconfirmed_specialist_roles_scored": False,
            "audio_included": False,
            "paths_or_filenames_included": False,
            "telemetry_included": False,
        },
    }


def validate_full_song_review(
    value: Mapping[str, Any],
    report: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    objective = validate_full_song_report(report, plan)
    seed = build_full_song_review_seed(objective, plan)
    document = json.loads(json.dumps(value, allow_nan=False))
    if set(document) - {
        "schema",
        "document_sha256",
        "status",
        "report_sha256",
        "plan_sha256",
        "cases",
        "boundaries",
        "saved_at",
    }:
        raise ValueError("full-song review contains unexpected metadata")
    if "saved_at" in document and (
        not isinstance(document["saved_at"], str) or len(document["saved_at"]) > 100
    ):
        raise ValueError("full-song review save time differs")
    for key in ("schema", "report_sha256", "plan_sha256", "boundaries"):
        if document.get(key) != seed[key]:
            raise ValueError("full-song review binding differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("full-song review cases differ")
    objective_by_track = {case["track_id"]: case for case in objective["cases"]}
    seen: set[str] = set()
    complete = True
    for case in cases:
        if set(case) != {
            "track_id",
            "played_items",
            "listened",
            "confirmed_windows_played",
            "confirmed_windows_replayed",
            "catastrophic_result",
            "catastrophic_details",
            "overall_usefulness",
            "role_usefulness",
            "issues",
            "notes",
        }:
            raise ValueError("full-song review case contains unexpected metadata")
        track_id = case.get("track_id")
        if track_id not in objective_by_track or track_id in seen:
            raise ValueError("full-song review track identity differs")
        seen.add(track_id)
        expected = objective_by_track[track_id]
        played = case.get("played_items")
        if (
            not isinstance(played, list)
            or len(played) != len(set(played))
            or not set(played).issubset(ARTIFACT_ROLES)
        ):
            raise ValueError("full-song review playback evidence differs")
        listened = set(played) == set(ARTIFACT_ROLES)
        if case.get("listened") is not listened:
            raise ValueError("full-song review listened state differs")
        expected_presence = set(_presence_ids(expected))
        presence = case.get("confirmed_windows_played")
        if (
            not isinstance(presence, list)
            or len(presence) != len(set(presence))
            or not set(presence).issubset(expected_presence)
        ):
            raise ValueError("full-song review presence replay differs")
        replayed = set(presence) == expected_presence
        if case.get("confirmed_windows_replayed") is not replayed:
            raise ValueError("full-song review presence state differs")
        catastrophic = case.get("catastrophic_result")
        if catastrophic not in _CATASTROPHIC:
            raise ValueError("full-song catastrophic result differs")
        details = case.get("catastrophic_details")
        notes = case.get("notes")
        if (
            not isinstance(details, str)
            or len(details) > 5000
            or not isinstance(notes, str)
            or len(notes) > 5000
        ):
            raise ValueError("full-song review notes differ")
        if catastrophic == "catastrophic_defect" and not details.strip():
            raise ValueError("full-song catastrophic defect needs details")
        if case.get("overall_usefulness") not in _USEFULNESS:
            raise ValueError("full-song overall usefulness differs")
        roles = set(_review_roles(expected))
        usefulness = case.get("role_usefulness")
        issues = case.get("issues")
        if (
            set(usefulness or {}) != roles
            or any(result not in _USEFULNESS for result in usefulness.values())
            or set(issues or {}) != roles
        ):
            raise ValueError("full-song per-role review differs")
        for role in roles:
            if set(issues[role]) != set(_ISSUE_FIELDS) or any(
                result not in _ISSUES for result in issues[role].values()
            ):
                raise ValueError("full-song issue rating differs")
        complete = complete and listened and replayed and catastrophic != "not_tested"
    expected_status = (
        "human_listening_complete_no_selection"
        if complete
        else "human_listening_incomplete_no_selection"
    )
    if document.get("status") != expected_status:
        raise ValueError("full-song review status differs")
    expected_hash = review_document_sha256(document)
    if document.get("document_sha256") not in {"", expected_hash}:
        raise ValueError("full-song review hash differs")
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
const key = `sunofriend-full-song-six-role-${seed.report_sha256}`;
let base = structuredClone(seed);
let ready = false;
let timer = null;
let running = false;
let queued = false;

function unique(values) { return [...new Set(values)]; }
function played(card, selector, attribute) {
  return unique([...card.querySelectorAll(selector)]
    .filter(player => player.dataset.played === 'true')
    .map(player => player.dataset[attribute]));
}
function updatePlayback(card) {
  const full = played(card, 'audio[data-player-id]', 'playerId');
  const windows = played(card, 'audio[data-presence-id]', 'presenceId');
  const expectedFull = card.querySelectorAll('audio[data-player-id]').length;
  const expectedWindows = card.querySelectorAll('audio[data-presence-id]').length;
  card.querySelector('[data-playback]').textContent =
    `Playback recorded automatically: ${full.length} of ${expectedFull} full-song roles and ${windows.length} of ${expectedWindows} confirmed windows played.`;
  return {full, windows, expectedFull, expectedWindows};
}
function collect() {
  const out = structuredClone(base);
  cards.forEach((card, index) => {
    const row = out.cases[index];
    const state = updatePlayback(card);
    row.played_items = state.full;
    row.listened = state.full.length === state.expectedFull;
    row.confirmed_windows_played = state.windows;
    row.confirmed_windows_replayed = state.windows.length === state.expectedWindows;
    for (const field of ['catastrophic_result', 'catastrophic_details', 'overall_usefulness', 'notes']) {
      row[field] = card.querySelector(`[data-field="${field}"]`).value;
    }
    card.querySelectorAll('[data-role-usefulness]').forEach(control => {
      row.role_usefulness[control.dataset.roleUsefulness] = control.value;
    });
    card.querySelectorAll('[data-issue]').forEach(control => {
      row.issues[control.dataset.issueRole][control.dataset.issue] = control.value;
    });
  });
  out.status = out.cases.every(row => row.listened && row.confirmed_windows_replayed && row.catastrophic_result !== 'not_tested')
    ? 'human_listening_complete_no_selection'
    : 'human_listening_incomplete_no_selection';
  out.document_sha256 = '';
  out.saved_at = new Date().toISOString();
  const text = `${JSON.stringify(out, null, 2)}\n`;
  document.getElementById('fallback').value = text;
  try { localStorage.setItem(key, JSON.stringify(out)); } catch (_error) {}
  return out;
}
function hydrate(out) {
  if (!out?.cases) return;
  base = structuredClone(out);
  out.cases.forEach((row, index) => {
    const card = cards[index];
    const full = new Set(row.played_items || []);
    const windows = new Set(row.confirmed_windows_played || []);
    card.querySelectorAll('audio[data-player-id]').forEach(player => {
      player.dataset.played = full.has(player.dataset.playerId) ? 'true' : 'false';
    });
    card.querySelectorAll('audio[data-presence-id]').forEach(player => {
      player.dataset.played = windows.has(player.dataset.presenceId) ? 'true' : 'false';
    });
    for (const field of ['catastrophic_result', 'catastrophic_details', 'overall_usefulness', 'notes']) {
      card.querySelector(`[data-field="${field}"]`).value = row[field] || '';
    }
    card.querySelectorAll('[data-role-usefulness]').forEach(control => {
      control.value = row.role_usefulness?.[control.dataset.roleUsefulness] || 'not_tested';
    });
    card.querySelectorAll('[data-issue]').forEach(control => {
      control.value = row.issues?.[control.dataset.issueRole]?.[control.dataset.issue] || 'not_tested';
    });
    updatePlayback(card);
  });
}
function localValue() {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value?.report_sha256 === seed.report_sha256 ? value : null;
  } catch (_error) { return null; }
}
function newer(left, right) {
  if (!left) return right;
  if (!right) return left;
  return (Date.parse(left.saved_at || '') || 0) >= (Date.parse(right.saved_at || '') || 0) ? left : right;
}
async function save() {
  if (!ready) return;
  if (running) { queued = true; return; }
  running = true;
  try {
    const response = await fetch('/save-review', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(collect()),
    });
    const value = await response.json();
    if (!response.ok) throw Error(value.error || 'save failed');
    base = structuredClone(value);
    document.getElementById('status').textContent = value.status === 'human_listening_complete_no_selection'
      ? 'Saved locally; all required playback and catastrophic checks are recorded.'
      : 'Progress saved locally automatically.';
  } catch (error) {
    document.getElementById('status').textContent = `Save failed: ${error.message}. The JSON remains below.`;
  } finally {
    running = false;
    if (queued) { queued = false; save(); }
  }
}
function schedule() { if (ready) { clearTimeout(timer); timer = setTimeout(save, 400); } }
async function waitForSave() { while (running) await new Promise(resolve => setTimeout(resolve, 50)); }
async function download() {
  if (!ready) return;
  await waitForSave(); await save(); await waitForSave();
  const response = await fetch('/download-review', {cache: 'no-store'});
  if (!response.ok) { document.getElementById('status').textContent = 'Download failed; the saved JSON remains below.'; return; }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await response.blob());
  link.download = 'sunofriend-full-song-six-role-listening.json';
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  document.getElementById('status').textContent = 'Saved review JSON downloaded.';
}
function record(player) {
  if (player.dataset.played !== 'true') { player.dataset.played = 'true'; collect(); schedule(); }
}
cards.forEach(card => card.querySelectorAll('audio').forEach(player => {
  for (const event of ['play', 'playing']) player.addEventListener(event, () => record(player));
  player.addEventListener('timeupdate', () => { if (player.currentTime > 0) record(player); });
  if (player.dataset.start) {
    player.addEventListener('loadedmetadata', () => {
      const start = Number(player.dataset.start); if (player.currentTime < start) player.currentTime = start;
    });
    player.addEventListener('timeupdate', () => {
      const end = Number(player.dataset.end); if (player.currentTime >= end) player.pause();
    });
  }
}));
document.addEventListener('input', () => { collect(); schedule(); });
fetch('/saved-result', {cache: 'no-store'})
  .then(response => response.ok ? response.json() : null)
  .then(saved => hydrate(newer(localValue(), saved)))
  .catch(() => hydrate(localValue()))
  .finally(() => { ready = true; collect(); schedule(); });
document.getElementById('save').onclick = save;
document.getElementById('download').onclick = download;
document.getElementById('copy').onclick = async () => {
  const out = collect();
  const text = ['Sunofriend private full-song six-role feedback', `Report: ${out.report_sha256}`,
    ...out.cases.map(row => `${row.track_id}: catastrophic=${row.catastrophic_result}; overall=${row.overall_usefulness}; roles=${JSON.stringify(row.role_usefulness)}; notes=${row.notes}`)].join('\n');
  try { await navigator.clipboard.writeText(text); document.getElementById('status').textContent = 'Text-only feedback copied.'; }
  catch (_error) { const box = document.getElementById('fallback'); box.value = text; box.select(); document.execCommand('copy'); }
};
""".strip()


def render_full_song_review(report: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    objective = validate_full_song_report(report, plan)
    seed = build_full_song_review_seed(objective, plan)
    cards = []
    usefulness_options = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("not_useful", "Not useful"),
        ("partly_useful", "Partly useful"),
        ("useful", "Useful"),
    )
    issue_options = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("none", "None"),
        ("some", "Some"),
        ("severe", "Severe"),
    )
    for index, case in enumerate(objective["cases"]):
        players = "".join(
            f"<label>{html.escape(role.replace('_', ' ').title())}"
            f'<audio controls preload="metadata" data-player-id="{role}" '
            f'src="/{html.escape(case["artifacts"][role]["relative_path"])}"></audio></label>'
            for role in ARTIFACT_ROLES
        )
        reference = case["artifacts"]["reference"]["relative_path"]
        presence_players = "".join(
            f"<label>{html.escape(target['target_role'].title())} confirmed-present source window "
            f"{target['window_seconds'][0]}–{target['window_seconds'][1]} seconds"
            f'<audio controls preload="metadata" data-presence-id="{html.escape(presence_id)}" '
            f'data-start="{target["window_seconds"][0]}" data-end="{target["window_seconds"][1]}" '
            f'src="/{html.escape(reference)}#t={target["window_seconds"][0]},{target["window_seconds"][1]}"></audio></label>'
            for target, presence_id in zip(
                case["confirmed_present_targets"], _presence_ids(case)
            )
        )
        role_fields = []
        for role in _review_roles(case):
            issue_parts = []
            for field, label in (
                ("bleed", "Bleed"),
                ("missing_content", "Missing content"),
                ("artefacts", "Artefacts"),
                ("timing_or_join_problems", "Timing or joins"),
            ):
                attributes = f'data-issue-role="{role}" data-issue="{field}"'
                issue_parts.append(
                    f"<label>{html.escape(label)}"
                    f"{_select(attributes, issue_options)}</label>"
                )
            issue_fields = "".join(issue_parts)
            usefulness_attribute = f'data-role-usefulness="{role}"'
            role_fields.append(
                f"<fieldset><legend>{html.escape(role.title())}</legend><label>Usefulness"
                f"{_select(usefulness_attribute, usefulness_options)}</label>"
                f'<div class="issues">{issue_fields}</div></fieldset>'
            )
        cards.append(
            f'''<section class="case" data-index="{index}"><p class="eyebrow">Private full-song six-role evidence</p><h2>{html.escape(case["title"])}</h2><p>Score specialist roles only where source presence was confirmed: {html.escape(", ".join(case["scored_target_roles"]))}. Unconfirmed specialist absence is not model failure.</p><div class="players">{players}</div><h3>Confirmed-present source windows</h3><div class="presence">{presence_players}</div><p class="playback" data-playback></p><p>Exact reconstruction proves accounting only, not separation quality.</p><label>Catastrophic-output check{_select('data-field="catastrophic_result"', (("not_tested", "Not tested"), ("no_catastrophic_defect", "No catastrophic defect"), ("catastrophic_defect", "Catastrophic defect"), ("cannot_tell", "Cannot tell")))}</label><label>Catastrophic details<textarea data-field="catastrophic_details" rows="2"></textarea></label><label>Overall usefulness{_select('data-field="overall_usefulness"', usefulness_options)}</label>{"".join(role_fields)}<label>Notes<textarea data-field="notes" rows="3"></textarea></label></section>'''
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunofriend full-song six-role review</title><style>:root{{color-scheme:dark;background:#06101e;color:#f7f8fb;font:17px system-ui,sans-serif}}body{{max-width:1380px;margin:auto;padding:30px}}.notice,.case,fieldset{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.issues{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}.presence{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}}label{{display:grid;gap:8px;margin:12px 0;font-weight:700}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button{{font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e}}button.secondary{{background:#2a5576;color:white}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback,#status{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}</style></head><body><p>Sunofriend Studio challenger · local private review</p><h1>Full-song vocals, drums, bass, synth, guitar and residual other</h1><div class="notice"><b>Poor or mixed feedback is valid and will not disable core-four.</b> There is no usefulness threshold. Playback is recorded automatically; there is no listened checkbox. No source choice or MIDI is made here.</div>{"".join(cards)}<section class="case"><h2>Local feedback</h2><p>No audio, filenames, paths or telemetry enter the review JSON.</p><button id="save">Save review locally</button><button class="secondary" id="download">Download saved JSON</button><button class="secondary" id="copy">Copy text-only feedback</button><p id="status"></p><label>Always-available fallback<textarea id="fallback" readonly></textarea></label></section><script id="seed" type="application/json">{seed_json}</script><script>{_review_script()}</script></body></html>"""


def build_full_song_review_server(
    root: str | Path,
    *,
    plan_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8772,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("full-song review must bind to localhost")
    package = Path(root).resolve(strict=True)
    plan = validate_fine_stem_full_song_plan(
        json.loads(Path(plan_path).resolve(strict=True).read_text(encoding="utf-8"))
    )
    report = validate_full_song_report(
        json.loads(
            (package / "TECHNICAL/FULL-SONG-SIX-ROLE-REPORT.json").read_text(
                encoding="utf-8"
            )
        ),
        plan,
    )
    page = render_full_song_review(report, plan).encode("utf-8")
    result_path = package / "REVIEW/FULL-SONG-SIX-ROLE-LISTENING.json"
    routes: dict[str, Path] = {}
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = (package / artifact["relative_path"]).resolve(strict=True)
            if (
                package not in path.parents
                or path.stat().st_size != artifact["bytes"]
                or _file_sha256(path) != artifact["sha256"]
            ):
                raise ValueError("full-song review audio identity differs")
            routes["/" + artifact["relative_path"]] = path

    class Handler(LocalReviewRequestHandler):
        server_version = "SunofriendFullSongSixRoleReview/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/REVIEW/full_song_six_role_review.html"}:
                self.send_no_store(200, "text/html; charset=utf-8", page)
            elif route == "/healthz":
                self.send_no_store(200, "application/json", b'{"status":"ok"}\n')
            elif route == "/saved-result" and result_path.is_file():
                self.send_no_store(200, "application/json", result_path.read_bytes())
            elif route == "/download-review" and result_path.is_file():
                self.send_attachment(
                    result_path.read_bytes(),
                    filename="sunofriend-full-song-six-role-listening.json",
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
                value = validate_full_song_review(self.read_review_json(), report, plan)
                payload = atomic_write_private_json(result_path, value)
            except (OSError, UnicodeError, ValueError) as error:
                self.send_review_error(error)
                return
            self.send_no_store(200, "application/json", payload)

    return ThreadingHTTPServer((host, port), Handler)


__all__ = [
    "REVIEW_SCHEMA",
    "build_full_song_review_seed",
    "build_full_song_review_server",
    "render_full_song_review",
    "review_document_sha256",
    "validate_full_song_review",
]
