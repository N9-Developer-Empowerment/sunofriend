"""Source-visible blind review for the private three-arm synth MIDI canary."""

from __future__ import annotations

import copy
import hashlib
import html
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from .separation_fine_stem_synth_provider_midi_canary import (
    validate_fine_stem_synth_provider_midi_canary,
)
from .separation_midi_comparison import verify_audio_identity
from .separation_review_transport import (
    LocalReviewRequestHandler,
    atomic_write_private_json,
)


REVIEW_SCHEMA = "sunofriend.fine-stem-synth-provider-midi-listening.v1"
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
_BEST = {"not_tested", "cannot_tell", "A", "B", "C", "tie_or_multiple"}
_PLAYER_IDS = {"source", "A", "B", "C"}


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


def build_provider_synth_midi_review_seed(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    objective = validate_fine_stem_synth_provider_midi_canary(report)
    return {
        "schema": REVIEW_SCHEMA,
        "document_sha256": "",
        "status": "human_three_arm_listening_incomplete_no_selection",
        "canary_document_sha256": objective["document_sha256"],
        "plan_document_sha256": objective["plan"]["document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "played_items": [],
                "listened": False,
                "ratings": {
                    display_id: {
                        "recognisable_notes": "not_tested",
                        "timing_usefulness": "not_tested",
                        "edit_workload": "not_tested",
                    }
                    for display_id in ("A", "B", "C")
                },
                "best_display": "not_tested",
                "notes": "",
            }
            for case in objective["cases"]
        ],
        "boundaries": {
            "review_is_blind": True,
            "arm_identities_included": False,
            "review_selects_source": False,
            "review_activates_profile": False,
            "poor_feedback_disables_core_four": False,
            "cannot_tell_and_not_tested_valid": True,
            "audio_included": False,
            "paths_or_filenames_included": False,
            "telemetry_included": False,
        },
    }


def validate_provider_synth_midi_review(
    value: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    objective = validate_fine_stem_synth_provider_midi_canary(report)
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != REVIEW_SCHEMA
        or document.get("canary_document_sha256") != objective["document_sha256"]
        or document.get("plan_document_sha256")
        != objective["plan"]["document_sha256"]
    ):
        raise ValueError("provider synth MIDI review binding differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("provider synth MIDI review cases differ")
    expected_ids = [case["case_id"] for case in objective["cases"]]
    if [case.get("case_id") for case in cases] != expected_ids:
        raise ValueError("provider synth MIDI review case order differs")
    for case in cases:
        played = case.get("played_items")
        if (
            not isinstance(played, list)
            or len(played) != len(set(played))
            or not set(played).issubset(_PLAYER_IDS)
            or case.get("listened") is not (set(played) == _PLAYER_IDS)
        ):
            raise ValueError("provider synth MIDI review playback differs")
        ratings = case.get("ratings")
        if not isinstance(ratings, dict) or set(ratings) != {"A", "B", "C"}:
            raise ValueError("provider synth MIDI review ratings differ")
        for rating in ratings.values():
            if (
                not isinstance(rating, dict)
                or set(rating)
                != {"recognisable_notes", "timing_usefulness", "edit_workload"}
                or rating["recognisable_notes"] not in _USEFULNESS
                or rating["timing_usefulness"] not in _USEFULNESS
                or rating["edit_workload"] not in _WORKLOAD
            ):
                raise ValueError("provider synth MIDI review rating value differs")
        if case.get("best_display") not in _BEST or not isinstance(
            case.get("notes"), str
        ):
            raise ValueError("provider synth MIDI review decision differs")
    complete = all(case["listened"] for case in cases)
    expected_status = (
        "human_three_arm_listening_complete_no_selection"
        if complete
        else "human_three_arm_listening_incomplete_no_selection"
    )
    if document.get("status") != expected_status:
        raise ValueError("provider synth MIDI review status differs")
    boundaries = document.get("boundaries", {})
    if (
        boundaries.get("review_is_blind") is not True
        or boundaries.get("arm_identities_included") is not False
        or boundaries.get("review_selects_source") is not False
        or boundaries.get("review_activates_profile") is not False
        or boundaries.get("audio_included") is not False
        or boundaries.get("paths_or_filenames_included") is not False
        or boundaries.get("telemetry_included") is not False
    ):
        raise ValueError("provider synth MIDI review grants authority or leaks metadata")
    expected_hash = review_document_sha256(document)
    if document.get("document_sha256") not in {"", expected_hash}:
        raise ValueError("provider synth MIDI review hash differs")
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
const storageKey = `sunofriend-provider-synth-midi-${seed.canary_document_sha256}`;
let base = structuredClone(seed);
let ready = false;
let timer = null;
let running = false;
let queued = false;

function playback(card) {
  const played = [...card.querySelectorAll('audio[data-player-id]')]
    .filter(player => player.dataset.played === 'true')
    .map(player => player.dataset.playerId);
  card.querySelector('[data-playback]').textContent = played.length === 4
    ? 'Playback recorded automatically: source and all three MIDI previews played.'
    : `Playback recorded automatically: ${played.length} of 4 items played.`;
  return played;
}

function collect() {
  const out = structuredClone(base);
  cards.forEach((card, index) => {
    const row = out.cases[index];
    row.played_items = playback(card);
    row.listened = row.played_items.length === 4;
    for (const display of ['A', 'B', 'C']) {
      for (const field of ['recognisable_notes', 'timing_usefulness', 'edit_workload']) {
        row.ratings[display][field] = card.querySelector(
          `[data-display="${display}"][data-field="${field}"]`
        ).value;
      }
    }
    row.best_display = card.querySelector('[data-field="best_display"]').value;
    row.notes = card.querySelector('[data-field="notes"]').value;
  });
  out.status = out.cases.every(row => row.listened)
    ? 'human_three_arm_listening_complete_no_selection'
    : 'human_three_arm_listening_incomplete_no_selection';
  out.document_sha256 = '';
  out.saved_at = new Date().toISOString();
  document.getElementById('fallback').value = `${JSON.stringify(out, null, 2)}\n`;
  try { localStorage.setItem(storageKey, JSON.stringify(out)); } catch (_error) {}
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
    for (const display of ['A', 'B', 'C']) {
      for (const field of ['recognisable_notes', 'timing_usefulness', 'edit_workload']) {
        card.querySelector(`[data-display="${display}"][data-field="${field}"]`).value =
          row.ratings?.[display]?.[field] || 'not_tested';
      }
    }
    card.querySelector('[data-field="best_display"]').value = row.best_display || 'not_tested';
    card.querySelector('[data-field="notes"]').value = row.notes || '';
    playback(card);
  });
}

function localValue() {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey));
    return value?.canary_document_sha256 === seed.canary_document_sha256 ? value : null;
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
    document.getElementById('status').textContent = value.status.includes('_complete_')
      ? 'Saved locally; all source and A/B/C playback is complete.'
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
      'Download failed; the review remains saved on this Mac and visible below.';
    return;
  }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await response.blob());
  link.download = 'sunofriend-provider-synth-midi-listening.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
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

const local = localValue();
fetch('/saved-result', {cache: 'no-store'})
  .then(response => response.ok ? response.json() : null)
  .then(saved => hydrate(newer(local, saved)))
  .catch(() => hydrate(local))
  .finally(() => { ready = true; collect(); schedule(); });

document.getElementById('save').onclick = save;
document.getElementById('download').onclick = download;
""".strip()


def render_provider_synth_midi_review(report: Mapping[str, Any]) -> str:
    objective = validate_fine_stem_synth_provider_midi_canary(report)
    seed = build_provider_synth_midi_review_seed(objective)
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
    best = (
        ("not_tested", "Not tested"),
        ("cannot_tell", "Cannot tell"),
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("tie_or_multiple", "Tie or multiple"),
    )
    cards = []
    for index, case in enumerate(objective["cases"]):
        case_id = quote(case["case_id"], safe="")
        players = [
            f'<section class="player"><h3>Source reference</h3><audio controls preload="metadata" data-player-id="source" src="/source/{case_id}.wav"></audio></section>'
        ]
        rating_fields = []
        for display_id in ("A", "B", "C"):
            players.append(
                f'<section class="player"><h3>MIDI {display_id}</h3><audio controls preload="metadata" data-player-id="{display_id}" src="/preview/{case_id}/{display_id}.wav"></audio></section>'
            )
            recognisable_attribute = (
                f'data-display="{display_id}" data-field="recognisable_notes"'
            )
            timing_attribute = (
                f'data-display="{display_id}" data-field="timing_usefulness"'
            )
            workload_attribute = (
                f'data-display="{display_id}" data-field="edit_workload"'
            )
            rating_fields.append(
                f'<fieldset><legend>MIDI {display_id}</legend>'
                f"<label>Recognisable notes"
                f"{_select(recognisable_attribute, usefulness)}</label>"
                f"<label>Timing usefulness"
                f"{_select(timing_attribute, usefulness)}</label>"
                f"<label>Expected edit workload"
                f"{_select(workload_attribute, workload)}</label></fieldset>"
            )
        cards.append(
            f'''<section class="case" data-index="{index}"><p class="eyebrow">private three-arm synth MIDI comparison · source visible</p><h2>{html.escape(case["title"])}</h2><p>{case["metadata"]["bpm"]:g} BPM · {html.escape(case["metadata"]["key"])} · frozen {case["window_seconds"][0]}–{case["window_seconds"][1]} seconds.</p><div class="players">{''.join(players)}</div><p class="playback" data-playback>Playback recorded automatically: 0 of 4 items played.</p><p>A, B and C are the same transcriber applied to three bound audio inputs. Display order does not reveal which input is current separation, provider synth or grouped other. Not tested and cannot tell are valid.</p><div class="ratings">{''.join(rating_fields)}</div><label>Most useful display{_select('data-field="best_display"', best)}</label><label>Notes<textarea data-field="notes" rows="3"></textarea></label></section>'''
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunofriend provider synth MIDI review</title><style>:root{{color-scheme:dark;background:#06101e;color:#f7f8fb;font:17px system-ui,sans-serif}}body{{max-width:1300px;margin:auto;padding:30px}}.notice,.case,fieldset{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.ratings{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}.player{{background:#091827;border:1px solid #294965;border-radius:14px;padding:16px}}label{{display:grid;gap:8px;margin:12px 0;font-weight:700}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button{{font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e}}button.secondary{{background:#2a5576;color:white}}.eyebrow{{color:#53d7e8;font-weight:800;text-transform:uppercase;letter-spacing:.08em}}.playback,#status{{color:#82e7b3;font-weight:700}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}</style></head><body><p>Sunofriend Studio evidence · local private review</p><h1>Which synth input gives the most editable MIDI?</h1><div class="notice"><b>There is no required winner.</b> Poor, mixed, not-tested and cannot-tell outcomes are valid. Playback is recorded automatically; there is no listened checkbox. Saving never selects a source or activates a profile.</div>{''.join(cards)}<section class="case"><h2>Local review record</h2><p>No audio, paths, filenames, arm identities or telemetry enter this JSON.</p><button id="save">Save review locally</button><button class="secondary" id="download">Download saved JSON</button><p id="status"></p><label>Always-available fallback JSON<textarea id="fallback" readonly></textarea></label></section><script id="seed" type="application/json">{seed_json}</script><script>{_review_script()}</script></body></html>'''


def build_provider_synth_midi_review_server(
    root: str | Path,
    *,
    provider_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 8775,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("provider synth MIDI review must bind to localhost")
    package = Path(root).resolve(strict=True)
    provider_package = Path(provider_root).resolve(strict=True)
    report = validate_fine_stem_synth_provider_midi_canary(
        json.loads(
            (package / "TECHNICAL/PROVIDER-SYNTH-MIDI-CANARY.json").read_text(
                encoding="utf-8"
            )
        )
    )
    page = render_provider_synth_midi_review(report).encode("utf-8")
    result_path = package / "REVIEW/PROVIDER-SYNTH-MIDI-LISTENING.json"
    routes: dict[str, Path] = {}
    for case in report["cases"]:
        case_id = quote(case["case_id"], safe="")
        source = case["source_reference"]
        routes[f"/source/{case_id}.wav"] = verify_audio_identity(
            provider_package,
            source["artifact"],
            f"{case['case_id']} source reference",
        )
        for display_id, output in case["outputs"].items():
            routes[f"/preview/{case_id}/{display_id}.wav"] = verify_audio_identity(
                package,
                output["preview"],
                f"{case['case_id']} display {display_id} preview",
            )

    class Handler(LocalReviewRequestHandler):
        server_version = "SunofriendProviderSynthMidiReview/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/REVIEW/provider_synth_midi_review.html"}:
                self.send_no_store(200, "text/html; charset=utf-8", page)
            elif route == "/healthz":
                self.send_no_store(200, "application/json", b'{"status":"ok"}\n')
            elif route == "/saved-result" and result_path.is_file():
                self.send_no_store(200, "application/json", result_path.read_bytes())
            elif route == "/download-review" and result_path.is_file():
                self.send_attachment(
                    result_path.read_bytes(),
                    filename="sunofriend-provider-synth-midi-listening.json",
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
                value = validate_provider_synth_midi_review(
                    self.read_review_json(), report
                )
                payload = atomic_write_private_json(result_path, value)
            except (OSError, UnicodeError, ValueError) as error:
                self.send_review_error(error)
                return
            self.send_no_store(200, "application/json", payload)

    return ThreadingHTTPServer((host, port), Handler)


__all__ = [
    "REVIEW_SCHEMA",
    "build_provider_synth_midi_review_seed",
    "build_provider_synth_midi_review_server",
    "render_provider_synth_midi_review",
    "review_document_sha256",
    "validate_provider_synth_midi_review",
]
