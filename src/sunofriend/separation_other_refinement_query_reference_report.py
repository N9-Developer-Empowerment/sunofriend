"""Objective report, private review page and localhost server for the canary."""

from __future__ import annotations

import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import parse_qs


QUERY_REFERENCE_REPORT_SCHEMA = (
    "sunofriend.other-refinement-query-reference-canary-report.v1"
)
QUERY_REFERENCE_REVIEW_SCHEMA = (
    "sunofriend.other-refinement-query-reference-listening.v1"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def query_reference_report_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_query_reference_report(
    *,
    plan_sha256: str,
    input_contract_sha256: str,
    runtime: Mapping[str, str],
    model: Mapping[str, Any],
    cases: list[dict[str, Any]],
    guards: Mapping[str, Any],
    elapsed_seconds: float,
    peak_resident_set_bytes: int,
) -> dict[str, Any]:
    maximum_lsb = max(case["accounting"]["maximum_reconstruction_error_lsb"] for case in cases)
    gates = {
        "exact_model_checkpoint_corpus_and_input_hashes": True,
        "zero_network_attempts": guards.get("network_attempts") == 0,
        "nine_exact_song_disjoint_inference_attempts": len(cases) == 9,
        "matching_output_shape_and_clock": all(
            case["geometry"] == {
                "sample_rate_hz": 44_100,
                "channels": 2,
                "frames": 661_500,
            }
            for case in cases
        ),
        "finite_target_and_residual_samples": all(
            case["accounting"]["finite"] for case in cases
        ),
        "tensor_reconstruction_passed": all(
            case["accounting"]["maximum_tensor_reconstruction_error"]
            <= 1e-6
            for case in cases
        ),
        "persisted_reconstruction_within_two_lsb": maximum_lsb <= 2,
        "elapsed_within_180_seconds": elapsed_seconds <= 180.0,
        "peak_memory_within_12_gib": peak_resident_set_bytes <= 12_884_901_888,
        "exclusive_atomic_publication_available": True,
    }
    status = (
        "objective_execution_complete_listening_pending_no_selection"
        if all(gates.values())
        else "retained_objective_failure_no_retry"
    )
    report: dict[str, Any] = {
        "schema": QUERY_REFERENCE_REPORT_SCHEMA,
        "document_sha256": "",
        "status": status,
        "scope_id": "other-query-refinement-v1",
        "profile_id": "query-bandit-ev-pre-aug-v1",
        "release_tier": "studio_challenger",
        "registered": False,
        "plan_document_sha256": plan_sha256,
        "input_contract_document_sha256": input_contract_sha256,
        "runtime": dict(runtime),
        "model": dict(model),
        "cases": cases,
        "guards": dict(guards),
        "resources": {
            "elapsed_seconds": elapsed_seconds,
            "peak_resident_set_bytes": peak_resident_set_bytes,
            "maximum_elapsed_seconds": 180.0,
            "maximum_peak_resident_set_bytes": 12_884_901_888,
        },
        "objective_gates": gates,
        "objective_summary": {
            "inference_attempts": len(cases),
            "configuration_count": 1,
            "query_count": 3,
            "mixture_count": 3,
            "maximum_persisted_reconstruction_error_lsb": maximum_lsb,
            "reconstruction_accounting_is_separation_accuracy": False,
            "musical_usefulness_established": False,
        },
        "rights_and_privacy": {
            "rights_category": "owned",
            "owner_credit": "Music by Ezzye — https://soundcloud.com/ezzye-1",
            "provider_stems_are_truth": False,
            "local_processing_only": True,
            "audio_uploaded": False,
            "telemetry": False,
        },
        "boundaries": {
            "public_activation": False,
            "source_selected": False,
            "source_graph_mutated": False,
            "midi_created": False,
            "hosted_conversion": False,
            "checkpoint_redistributed": False,
            "commercial_default": False,
            "automatic_retry": False,
            "human_listening_pending": True,
        },
    }
    report["document_sha256"] = query_reference_report_sha256(report)
    return report


def validate_query_reference_report(value: Mapping[str, Any]) -> dict[str, Any]:
    report = dict(value)
    if report.get("schema") != QUERY_REFERENCE_REPORT_SCHEMA:
        raise ValueError("query reference report schema differs")
    if report.get("document_sha256") != query_reference_report_sha256(report):
        raise ValueError("query reference report hash differs")
    if report.get("status") != (
        "objective_execution_complete_listening_pending_no_selection"
    ):
        raise ValueError("query reference report is not an objective pass")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        raise ValueError("query reference report must contain nine cases")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(set(case_ids)) != 9:
        raise ValueError("query reference case identities differ")
    if not all(report.get("objective_gates", {}).values()):
        raise ValueError("query reference objective gate failed")
    if report.get("guards", {}).get("restricted_torch_load_calls") != 2:
        raise ValueError("query reference model load count differs")
    if report.get("guards", {}).get("network_attempts") != 0:
        raise ValueError("query reference network boundary differs")
    boundaries = report.get("boundaries")
    if not isinstance(boundaries, dict) or any(
        boundaries.get(key) is not False
        for key in (
            "public_activation",
            "source_selected",
            "source_graph_mutated",
            "midi_created",
            "hosted_conversion",
            "checkpoint_redistributed",
            "commercial_default",
            "automatic_retry",
        )
    ):
        raise ValueError("query reference activation boundary differs")
    for case in cases:
        artifacts = case.get("artifacts")
        if not isinstance(artifacts, dict) or set(artifacts) != {
            "source_reference",
            "query_reference",
            "target",
            "residual",
        }:
            raise ValueError("query reference artifacts differ")
        for role, artifact in artifacts.items():
            expected_frames = 441_000 if role == "query_reference" else 661_500
            if (
                artifact.get("subtype") != "PCM_24"
                or artifact.get("sample_rate_hz") != 44_100
                or artifact.get("channels") != 2
                or artifact.get("frames") != expected_frames
                or _SHA256.fullmatch(str(artifact.get("sha256"))) is None
            ):
                raise ValueError("query reference audio artifact differs")
    return report


def _review_seed(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": QUERY_REFERENCE_REVIEW_SCHEMA,
        "scope_id": report["scope_id"],
        "profile_id": report["profile_id"],
        "report_sha256": report["document_sha256"],
        "status": "human_listening_pending_no_selection",
        "cases": [
            {
                "case_id": case["case_id"],
                "track_id": case["track_id"],
                "target_id": case["target_id"],
                "listened": False,
                "usefulness": "not_tested",
                "issues": {
                    "bleed": "not_tested",
                    "missing_content": "not_tested",
                    "artefacts": "not_tested",
                    "timing": "not_tested",
                },
                "notes": "",
            }
            for case in report["cases"]
        ],
        "boundaries": {
            "provider_stems_are_truth": False,
            "review_selects_source": False,
            "review_starts_midi": False,
            "audio_included": False,
            "filenames_included": False,
            "telemetry_included": False,
        },
    }


def render_query_reference_review(report: Mapping[str, Any]) -> str:
    validated = validate_query_reference_report(report)
    seed = _review_seed(validated)
    cards: list[str] = []
    for index, case in enumerate(validated["cases"]):
        audio = case["artifacts"]
        players = "".join(
            (
                f"<label>{html.escape(label.replace('_', ' ').title())}"
                f"<audio controls preload=\"metadata\" "
                f"src=\"../{html.escape(audio[key]['relative_path'])}\"></audio></label>"
            )
            for key, label in (
                ("source_reference", "source reference"),
                ("query_reference", "query estimate hint"),
                ("target", "Banquet target"),
                ("residual", "reconstruction residual"),
            )
        )
        cards.append(
            f"""
<section class="case" data-index="{index}">
  <h2>{html.escape(case['track_id'])} · {html.escape(case['target_id'])}</h2>
  <p>The provider query is an estimate and listening hint, not truth.</p>
  <div class="players">{players}</div>
  <label class="check"><input type="checkbox" data-field="listened"> I listened to all four files.</label>
  <label>Target usefulness<select data-field="usefulness">
    <option value="not_tested">Not tested</option><option value="cannot_tell">Cannot tell</option>
    <option value="not_useful">Not useful</option><option value="partly_useful">Partly useful</option>
    <option value="useful">Useful</option>
  </select></label>
  <div class="issues">{''.join(f'<label>{name.replace("_", " ").title()}<select data-issue="{name}"><option value="not_tested">Not tested</option><option value="cannot_tell">Cannot tell</option><option value="absent">Absent</option><option value="minor">Minor</option><option value="major">Major</option></select></label>' for name in ('bleed','missing_content','artefacts','timing'))}</div>
  <label>Notes<textarea data-field="notes" rows="3"></textarea></label>
</section>"""
        )
    seed_json = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend Banquet reference-query review</title>
<style>
:root{{color-scheme:dark;background:#06101e;color:#f6f7fb;font:17px system-ui,sans-serif}}body{{max-width:1200px;margin:auto;padding:32px}}h1{{font-size:2.3rem}}.notice,.case{{background:#102033;border:1px solid #31516e;border-radius:18px;padding:22px;margin:20px 0}}.players,.issues{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}label{{display:grid;gap:7px;margin:12px 0;font-weight:650}}audio,select,textarea{{width:100%}}audio{{height:54px}}select,textarea{{font:inherit;padding:10px}}button{{font:inherit;font-weight:750;border:0;border-radius:999px;padding:14px 22px;margin:8px;background:#53d7e8;color:#06101e}}button.secondary{{background:#2a5576;color:white}}#fallback{{min-height:180px;font:13px ui-monospace,monospace}}.status{{min-height:1.5em;color:#82e7b3}}
</style></head><body>
<p>Sunofriend Studio challenger · local private review</p><h1>Guitar, keyboard and synth reference-query canary</h1>
<div class="notice"><strong>What this review can decide:</strong> musical usefulness and limitations. Reconstruction only proves additive accounting. It does not prove correct separation. Poor, mixed, cannot-tell and not-tested feedback are valid and do not disable the public core-four profile.</div>
{''.join(cards)}
<section class="case"><h2>Export local feedback</h2><p>No audio, paths, filenames or telemetry are included. This review does not select a source or start MIDI.</p>
<button id="download">Download review JSON</button><button class="secondary" id="copy">Copy text-only feedback</button>
<p class="status" id="status"></p><label>Always-available JSON fallback<textarea id="fallback" readonly></textarea></label>
</section>
<script id="seed" type="application/json">{seed_json}</script><script>
const seed=JSON.parse(document.getElementById('seed').textContent);
const cards=[...document.querySelectorAll('.case[data-index]')];
function collect(){{const out=structuredClone(seed);cards.forEach((card,i)=>{{const row=out.cases[i];row.listened=card.querySelector('[data-field=listened]').checked;row.usefulness=card.querySelector('[data-field=usefulness]').value;row.notes=card.querySelector('[data-field=notes]').value.trim();card.querySelectorAll('[data-issue]').forEach(el=>row.issues[el.dataset.issue]=el.value);}});out.status=out.cases.every(x=>x.listened)?'human_listening_complete_no_selection':'human_listening_incomplete_no_selection';out.exported_at=new Date().toISOString();return out;}}
function text(){{const value=JSON.stringify(collect(),null,2)+'\\n';document.getElementById('fallback').value=value;return value;}}
document.addEventListener('input',text);text();
document.getElementById('download').addEventListener('click',()=>{{const value=text();if(location.protocol.startsWith('http')){{const form=document.createElement('form');form.method='POST';form.action='/download-review';const field=document.createElement('input');field.type='hidden';field.name='payload';field.value=value;form.appendChild(field);document.body.appendChild(form);form.submit();form.remove();document.getElementById('status').textContent='The local server sent the JSON download. The same JSON remains below.';return;}}const blob=new Blob([value],{{type:'application/json'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='banquet-reference-query-review.json';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000);document.getElementById('status').textContent='Download requested. The same JSON remains below if the browser blocks it.';}});
document.getElementById('copy').addEventListener('click',async()=>{{const out=collect();const lines=['Sunofriend Banquet reference-query feedback',`Profile: ${{out.profile_id}}`,`Report: ${{out.report_sha256}}`,...out.cases.map(x=>`${{x.case_id}}: ${{x.usefulness}}; listened=${{x.listened}}; issues=${{JSON.stringify(x.issues)}}${{x.notes?`; notes=${{x.notes}}`:''}}`)];const value=lines.join('\\n');let ok=false;try{{await navigator.clipboard.writeText(value);ok=true;}}catch(_e){{const box=document.getElementById('fallback');box.value=value;box.focus();box.select();ok=document.execCommand('copy');text();}}document.getElementById('status').textContent=ok?'Text-only feedback copied.':'Copy was blocked; select it from the fallback box.';}});
</script></body></html>"""


def _validate_review_download(payload: str, report: Mapping[str, Any]) -> bytes:
    if len(payload.encode("utf-8")) > 1_000_000:
        raise ValueError("review download is too large")
    value = json.loads(payload)
    seed = _review_seed(report)
    if not isinstance(value, dict) or any(
        value.get(key) != seed[key]
        for key in ("schema", "scope_id", "profile_id", "report_sha256", "boundaries")
    ):
        raise ValueError("review download binding differs")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        raise ValueError("review download cases differ")
    expected = {case["case_id"] for case in seed["cases"]}
    if {case.get("case_id") for case in cases if isinstance(case, dict)} != expected:
        raise ValueError("review download case identities differ")
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_query_reference_review_server(
    root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8767,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("query review server must bind to localhost")
    package = Path(root).resolve(strict=True)
    report_path = package / "TECHNICAL/REFERENCE-REPORT.json"
    report = validate_query_reference_report(
        json.loads(report_path.read_text(encoding="utf-8"))
    )
    page = (package / "REVIEW/review.html").read_bytes()
    routes: dict[str, Path] = {}
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = (package / artifact["relative_path"]).resolve(strict=True)
            if package not in path.parents:
                raise ValueError("query review artifact escapes its package")
            if (
                not path.is_file()
                or path.stat().st_size != artifact["bytes"]
                or _file_sha256(path) != artifact["sha256"]
            ):
                raise ValueError("query review artifact identity differs")
            route = "/" + artifact["relative_path"]
            if route in routes:
                raise ValueError("query review audio routes must be unique")
            routes[route] = path

    class Handler(BaseHTTPRequestHandler):
        server_version = "SunofriendQueryReferenceReview/1"

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            if route in {"/", "/review.html", "/REVIEW/review.html"}:
                self._send(200, "text/html; charset=utf-8", page)
                return
            if route == "/healthz":
                self._send(200, "application/json", b'{"status":"ok"}\n')
                return
            path = routes.get(route)
            if path is None:
                self.send_error(404)
                return
            self._audio(path)

        def do_HEAD(self) -> None:  # noqa: N802
            route = self.path.partition("?")[0]
            path = routes.get(route)
            if path is None:
                self.send_error(404)
                return
            self._audio(path, body=False)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/download-review":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_100_000:
                self.send_error(413)
                return
            try:
                fields = parse_qs(self.rfile.read(length).decode("utf-8"))
                payload = fields.get("payload", [""])[0]
                body = _validate_review_download(payload, report)
            except (UnicodeError, ValueError, json.JSONDecodeError):
                self.send_error(400, "Invalid review")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="banquet-reference-query-review.json"',
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

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
                    remaining = length
                    while remaining:
                        block = handle.read(min(1024 * 1024, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


__all__ = [
    "QUERY_REFERENCE_REPORT_SCHEMA",
    "QUERY_REFERENCE_REVIEW_SCHEMA",
    "build_query_reference_report",
    "build_query_reference_review_server",
    "query_reference_report_sha256",
    "render_query_reference_review",
    "validate_query_reference_report",
]
