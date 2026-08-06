"""Local-only web approval form for the bounded core-four preview."""

from __future__ import annotations

from collections.abc import Mapping
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


APPROVAL_SCHEMA = "sunofriend.core-four-preview-approval.v1"
PROFILE_ID = "scnet-large-musdb-release-v1"
SCOPE_ID = "core-four-stems-v1"
SOURCE_REVISION = "6236f8c559778dc271e1aea9baa3993ae655e905"
WEIGHTS_SHA256 = (
    "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
)
CONFIG_SHA256 = (
    "629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0"
)
RIGHTS_CATEGORIES = {
    "owned",
    "licensed",
    "authorised_private_use",
    "statutory_exception",
}
MACHINE_DECISIONS = {
    "keep_16_gib_requirement",
    "verify_36_gib_first",
}
PUBLICATION_DECISIONS = {
    "local_only",
    "draft_pr_no_deploy",
    "pr_and_deploy_after_verification",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def approval_binding() -> dict[str, Any]:
    """Return the immutable profile and evidence identity shown in the form."""

    return {
        "schema": APPROVAL_SCHEMA,
        "scope_id": SCOPE_ID,
        "profile_id": PROFILE_ID,
        "model": "official SCNet-large MUSDB checkpoint",
        "source_revision": SOURCE_REVISION,
        "weights_sha256": WEIGHTS_SHA256,
        "config_sha256": CONFIG_SHA256,
        "synthetic_evidence": {
            "same_configuration_runs": 3,
            "duration_seconds_each": 60.0,
            "worker_elapsed_seconds": [
                69.96541137504391,
                70.19936337508261,
                71.18379291682504,
            ],
            "peak_resident_set_bytes": [
                6_581_846_016,
                6_719_586_304,
                6_588_547_072,
            ],
            "all_persisted_audio_hashes_identical": True,
            "maximum_reconstruction_error_lsb": 0,
            "network_denied": True,
            "machine": "Apple M3 Max with 36 GB unified memory",
            "verified_16_gib_benchmark": False,
            "known_limitation": (
                "The mathematical vocal estimate was extremely quiet and "
                "vocal reference content remained mainly in grouped other."
            ),
        },
    }


def render_core_four_approval_html(
    *,
    synthetic_root: str | Path | None = None,
    audio_url_prefix: str | None = None,
) -> str:
    """Render a self-contained page that downloads, but never uploads, JSON."""

    root = (
        Path(synthetic_root).expanduser().absolute()
        if synthetic_root is not None
        else None
    )
    audio = _audio_sections(root, audio_url_prefix=audio_url_prefix)
    binding_json = _safe_script_json(approval_binding())
    rights_json = _safe_script_json(sorted(RIGHTS_CATEGORIES))
    template = _HTML_TEMPLATE
    return (
        template.replace("__BINDING_JSON__", binding_json)
        .replace("__RIGHTS_JSON__", rights_json)
        .replace("__AUDIO_SECTIONS__", audio)
    )


def write_core_four_approval_page(
    output: str | Path,
    *,
    synthetic_root: str | Path | None = None,
    open_browser: bool = False,
) -> Path:
    """Write one fresh private approval page and optionally open it on macOS."""

    target = Path(output).expanduser().absolute()
    if os.path.lexists(target):
        raise FileExistsError(f"approval page output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_core_four_approval_html(synthetic_root=synthetic_root),
        encoding="utf-8",
    )
    if open_browser:
        subprocess.run(["open", str(target)], check=True)
    return target


def build_core_four_approval_server(
    synthetic_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Build a localhost-only server exposing only the form and exact audio."""

    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("core-four approval server must bind to localhost")
    root = Path(synthetic_root).expanduser().resolve(strict=True)
    audio_paths = _required_audio_paths(root)
    missing = [route for route, path in audio_paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"core-four approval audio is missing: {', '.join(missing)}"
        )
    page = render_core_four_approval_html(
        synthetic_root=root,
        audio_url_prefix="/audio",
    ).encode("utf-8")

    class ApprovalHandler(BaseHTTPRequestHandler):
        server_version = "SunofriendApproval/1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._serve(send_body=True)

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
            self._serve(send_body=False)

        def do_POST(self) -> None:  # noqa: N802 - explicit no-upload boundary
            self.send_error(405, "This local page accepts no submissions")

        def _serve(self, *, send_body: bool) -> None:
            route = self.path.partition("?")[0]
            if route in {"/", "/index.html"}:
                self._headers(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    content_length=len(page),
                )
                if send_body:
                    self.wfile.write(page)
                return
            if route == "/healthz":
                body = b'{"status":"ok","network_scope":"localhost_only"}\n'
                self._headers(
                    status=200,
                    content_type="application/json; charset=utf-8",
                    content_length=len(body),
                )
                if send_body:
                    self.wfile.write(body)
                return
            audio_route = route.removeprefix("/audio/")
            path = audio_paths.get(audio_route) if route.startswith("/audio/") else None
            if path is None:
                self.send_error(404, "Not found")
                return
            self._serve_audio(path, send_body=send_body)

        def _serve_audio(self, path: Path, *, send_body: bool) -> None:
            size = path.stat().st_size
            start = 0
            end = size - 1
            status = 200
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if match is None or (not match.group(1) and not match.group(2)):
                    self.send_error(416, "Invalid byte range")
                    return
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else end
                else:
                    suffix = int(match.group(2))
                    start = max(0, size - suffix)
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206
            length = end - start + 1
            self._headers(
                status=status,
                content_type="audio/wav",
                content_length=length,
                content_range=(f"bytes {start}-{end}/{size}" if status == 206 else None),
            )
            if not send_body:
                return
            with path.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining:
                    chunk = source.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _headers(
            self,
            *,
            status: int,
            content_type: str,
            content_length: int,
            content_range: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Accept-Ranges", "bytes")
            if content_range is not None:
                self.send_header("Content-Range", content_range)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), ApprovalHandler)


def validate_core_four_approval_document(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a completed browser export before treating it as authority."""

    if document.get("schema") != APPROVAL_SCHEMA:
        raise ValueError("unsupported core-four approval schema")
    approval_id = document.get("approval_id")
    if (
        not isinstance(approval_id, str)
        or not approval_id.strip()
        or len(approval_id) > 200
    ):
        raise ValueError("core-four approval ID is missing or invalid")
    profile = document.get("profile")
    expected_profile = {
        key: approval_binding()[key]
        for key in (
            "scope_id",
            "profile_id",
            "source_revision",
            "weights_sha256",
            "config_sha256",
        )
    }
    if profile != expected_profile:
        raise ValueError("core-four approval profile binding differs")
    if not _SHA256.fullmatch(str(profile["weights_sha256"])):
        raise ValueError("core-four approval weights identity is invalid")
    if document.get("evidence_acknowledged") != approval_binding()[
        "synthetic_evidence"
    ]:
        raise ValueError("core-four acknowledged evidence differs")
    approved_by = document.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip() or len(approved_by) > 200:
        raise ValueError("core-four approver identity is missing or invalid")
    approvals = document.get("approvals")
    if not isinstance(approvals, Mapping):
        raise ValueError("core-four approvals mapping is missing")

    listen = approvals.get("synthetic_listen")
    if not isinstance(listen, Mapping) or listen.get("completed") is not True:
        raise ValueError("synthetic catastrophic listen is incomplete")
    if listen.get("result") not in {
        "no_catastrophic_defect",
        "catastrophic_defect_reported",
    }:
        raise ValueError("synthetic catastrophic result is missing or invalid")
    details = listen.get("details")
    if not isinstance(details, str) or len(details) > 5_000:
        raise ValueError("synthetic listen details are invalid")
    if listen["result"] == "catastrophic_defect_reported" and not details.strip():
        raise ValueError("reported catastrophic defect requires details")

    canaries = approvals.get("full_song_canaries")
    songs = canaries.get("songs") if isinstance(canaries, Mapping) else None
    if (
        not isinstance(canaries, Mapping)
        or canaries.get("offline_processing_authorized") is not True
        or not isinstance(songs, list)
        or len(songs) != 3
    ):
        raise ValueError("full-song canary approval is incomplete")
    expected_coverage = {"vocal_forward", "dense_electronic", "acoustic_mixed"}
    observed_coverage: set[str] = set()
    observed_paths: set[str] = set()
    for song in songs:
        if not isinstance(song, Mapping):
            raise ValueError("full-song canary entry is invalid")
        coverage = song.get("coverage_id")
        path = song.get("absolute_path")
        rights = song.get("rights_category")
        if coverage not in expected_coverage:
            raise ValueError("full-song canary coverage is invalid")
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError(f"full-song path is not absolute for {coverage}")
        if rights not in RIGHTS_CATEGORIES:
            raise ValueError(f"full-song rights category is invalid for {coverage}")
        observed_coverage.add(str(coverage))
        observed_paths.add(path)
    if observed_coverage != expected_coverage or len(observed_paths) != 3:
        raise ValueError("full-song canaries must be coverage- and path-disjoint")

    machine = approvals.get("supported_machine")
    if not isinstance(machine, Mapping) or machine.get("decision") not in MACHINE_DECISIONS:
        raise ValueError("supported-machine decision is missing or invalid")
    machine_details = machine.get("machine_details")
    if not isinstance(machine_details, str) or len(machine_details) > 2_000:
        raise ValueError("supported-machine details are invalid")
    if machine["decision"] == "keep_16_gib_requirement" and not machine_details.strip():
        raise ValueError("16 GiB requirement needs access details")
    expected_claim_effect = (
        "36 GB M3 Max becomes first verified class; 16 GiB remains accessible "
        "but unverified"
        if machine["decision"] == "verify_36_gib_first"
        else "16 GiB remains required and must be tested on the described machine"
    )
    if machine.get("claim_effect") != expected_claim_effect:
        raise ValueError("supported-machine claim effect differs")

    if approvals.get("conditional_public_activation") is not True:
        raise ValueError("conditional public activation is not approved")
    if approvals.get("repository_publication") not in PUBLICATION_DECISIONS:
        raise ValueError("repository publication decision is missing or invalid")
    if approvals.get("downstream_midi_requires_later_approval") is not True:
        raise ValueError("downstream MIDI boundary is not acknowledged")

    boundaries = document.get("boundaries")
    expected_boundaries = {
        "local_processing_only_for_canaries": True,
        "network_model_resolution": False,
        "audio_upload": False,
        "automatic_midi_or_create": False,
        "hosted_conversion_service": False,
        "maintainer_email_required_for_local_preview": False,
    }
    if boundaries != expected_boundaries:
        raise ValueError("core-four approval boundaries differ")
    if document.get("audio_included") is not False:
        raise ValueError("approval JSON must not include audio")
    if document.get("browser_telemetry_included") is not False:
        raise ValueError("approval JSON must not include browser telemetry")
    missing = document.get("missing_fields")
    if not isinstance(missing, list) or missing:
        raise ValueError("core-four approval remains incomplete")
    exported_at = document.get("exported_at")
    if not isinstance(exported_at, str) or not exported_at:
        raise ValueError("core-four approval export time is missing")
    publication = approvals["repository_publication"]
    defect_reported = listen["result"] == "catastrophic_defect_reported"
    expected_status = (
        "stop_ship_reported"
        if defect_reported
        else "approvals_complete_local_only"
        if publication == "local_only"
        else "approvals_complete_draft_pr_no_deploy"
        if publication == "draft_pr_no_deploy"
        else "approvals_complete_for_verified_delivery"
    )
    if document.get("status") != expected_status:
        raise ValueError("core-four approval status differs from its decisions")
    expected_remaining = []
    if publication == "local_only":
        expected_remaining.append("commit_push_pr_and_deployment_not_authorized")
    elif publication == "draft_pr_no_deploy":
        expected_remaining.append("website_deployment_not_authorized")
    if defect_reported:
        expected_remaining.append(
            "catastrophic_synthetic_finding_requires_resolution"
        )
    if document.get("remaining_approval_blockers") != expected_remaining:
        raise ValueError("remaining approval blockers differ from the decisions")
    return dict(document)


def resolve_core_four_approved_songs(
    document: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Resolve approved local song paths without broad or fuzzy path guessing.

    A browser paste can accidentally repeat one absolute path back-to-back.  The
    only accepted correction is two byte-identical path halves where the single
    half is an existing regular file.  Both values remain in the returned
    receipt so this normalization cannot be mistaken for a different approval.
    """

    validated = validate_core_four_approval_document(document)
    songs = validated["approvals"]["full_song_canaries"]["songs"]
    resolved: list[dict[str, Any]] = []
    for song in songs:
        approved_path = str(song["absolute_path"])
        candidate = Path(approved_path)
        normalization: dict[str, Any] | None = None
        if not candidate.is_file():
            halfway = len(approved_path) // 2
            single = approved_path[:halfway]
            if (
                len(approved_path) % 2 == 0
                and approved_path == single + single
                and Path(single).is_absolute()
                and Path(single).is_file()
            ):
                candidate = Path(single)
                normalization = {
                    "applied": True,
                    "policy": "identical_absolute_path_halves_v1",
                    "reason": "user_confirmed_accidental_duplicate_paste",
                }
            else:
                raise FileNotFoundError(
                    "approved full-song source is missing and has no exact "
                    f"receipt-safe normalization: {approved_path}"
                )
        resolved.append(
            {
                "coverage_id": song["coverage_id"],
                "rights_category": song["rights_category"],
                "approved_absolute_path": approved_path,
                "resolved_absolute_path": str(candidate.absolute()),
                "path_normalization": normalization
                or {"applied": False, "policy": None, "reason": None},
            }
        )
    if len({item["resolved_absolute_path"] for item in resolved}) != 3:
        raise ValueError("resolved full-song canaries must remain path-disjoint")
    return resolved


def _safe_script_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("<", "\\u003c")


def _required_audio_paths(root: Path) -> dict[str, Path]:
    return {
        "source.wav": root / "SOURCE/source-reference.wav",
        "vocals.wav": root / "STEMS/vocals.wav",
        "drums.wav": root / "STEMS/drums.wav",
        "bass.wav": root / "STEMS/bass.wav",
        "other.wav": root / "STEMS/other.wav",
        "reconstruction.wav": root / "AUDIO/reconstruction-check.wav",
    }


def _audio_sections(
    root: Path | None,
    *,
    audio_url_prefix: str | None = None,
) -> str:
    if root is None:
        return (
            '<p class="muted">No synthetic listening bundle was attached to '
            "this form. Open the separately supplied local evidence bundle.</p>"
        )
    paths = _required_audio_paths(root)
    items = (
        ("Source reference", "source.wav"),
        ("Vocals estimate", "vocals.wav"),
        ("Drums estimate", "drums.wav"),
        ("Bass estimate", "bass.wav"),
        ("Grouped other estimate", "other.wav"),
        ("Reconstruction check", "reconstruction.wav"),
    )
    sections: list[str] = []
    for label, route in items:
        path = paths[route]
        escaped_label = html.escape(label)
        if not path.is_file():
            sections.append(
                f'<article class="audio-card missing"><h3>{escaped_label}</h3>'
                "<p>Local file not found.</p></article>"
            )
            continue
        uri = (
            f"{audio_url_prefix.rstrip('/')}/{route}"
            if audio_url_prefix is not None
            else path.as_uri()
        )
        uri = html.escape(uri, quote=True)
        sections.append(
            f'<article class="audio-card"><h3>{escaped_label}</h3>'
            f'<audio controls preload="metadata" src="{uri}"></audio></article>'
        )
    return "".join(sections)


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; img-src data:; media-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Sunofriend core-four approval</title>
<style>
:root{--ink:#f6f8fb;--muted:#aeb9c8;--night:#07101c;--panel:#101d2c;--panel2:#14263a;--line:#2b465f;--cyan:#4fe2ee;--yellow:#ffd666;--green:#71e49b;--red:#ff7f8d;--blue:#1877a4}*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#050b13 0%,#0b1725 55%,#07101c 100%);color:var(--ink);font:17px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1120px;margin:auto;padding:28px 20px 80px}.hero{padding:34px 0 20px}.eyebrow{color:var(--cyan);font-weight:800;letter-spacing:.13em;text-transform:uppercase}.hero h1{font-size:clamp(2.5rem,8vw,5.5rem);line-height:.95;margin:.25em 0}.lede{max-width:800px;color:#dce6f2;font-size:1.2rem}.badges{display:flex;flex-wrap:wrap;gap:9px;margin:20px 0}.badge{background:#153047;border:1px solid #2a5a79;border-radius:999px;padding:6px 11px;font-size:.9rem}.layout{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:20px;align-items:start}.stack{display:grid;gap:18px}.card,.summary{background:rgba(16,29,44,.97);border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:0 18px 45px rgba(0,0,0,.18)}.summary{position:sticky;top:18px}.number{color:var(--cyan);font-weight:800;font-size:.85rem;letter-spacing:.12em}.card h2,.summary h2{margin:.15em 0 .6em;font-size:1.45rem}.card h3{font-size:1rem;margin:.2em 0 .4em}.warning{border-left:5px solid var(--yellow);padding:12px 14px;background:#2a281c}.stop{border-left-color:var(--red);background:#301d27}.good{border-left-color:var(--green);background:#173025}.muted{color:var(--muted)}.small{font-size:.9rem}label{display:block;margin:14px 0;font-weight:650}input[type=text],textarea,select{display:block;width:100%;margin-top:6px;background:#08131f;color:var(--ink);border:1px solid #3a5872;border-radius:9px;padding:12px;font:inherit}textarea{min-height:92px;resize:vertical}input[type=checkbox],input[type=radio]{width:1.15rem;height:1.15rem;vertical-align:-.17rem;margin-right:.45rem}.choice{display:block;background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:13px;margin:10px 0;font-weight:500}.song{border-top:1px solid var(--line);padding-top:16px;margin-top:18px}.song:first-of-type{border-top:0;padding-top:0}.audio-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.audio-card{background:#091522;border:1px solid var(--line);border-radius:12px;padding:13px}.audio-card audio{width:100%}.audio-card.missing{color:var(--red)}button{border:0;border-radius:9px;padding:12px 16px;font:inherit;font-weight:750;cursor:pointer;margin:6px 7px 6px 0}.primary{background:var(--cyan);color:#04202b}.secondary{background:#20435e;color:white}.danger{background:#63313a;color:white}button:disabled{opacity:.45;cursor:not-allowed}.status{border-radius:12px;padding:14px;margin:12px 0;background:#1a2a3c;border:1px solid var(--line)}.status.ready{border-color:#3c8d5b;background:#173025}.status.blocked{border-color:#8f7134;background:#2a281c}.status.stop{border-color:#a44a5b;background:#301d27}.missing-list{padding-left:20px}.json-preview{width:100%;min-height:260px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre}.privacy{font-size:.9rem;color:var(--muted);border-top:1px solid var(--line);padding-top:14px;margin-top:18px}@media(max-width:820px){.layout{grid-template-columns:1fr}.summary{position:static}.audio-grid{grid-template-columns:1fr}}
</style></head><body><main>
<header class="hero"><div class="eyebrow">Sunofriend · local approval record</div><h1>Approve the next core-four steps clearly.</h1><p class="lede">This page records your decisions for the exact installed SCNet profile. It does not run a model, inspect your song files, upload anything, change profile status, commit code or deploy a website.</p><div class="badges"><span class="badge">Local-only form</span><span class="badge">No network requests</span><span class="badge">No audio in JSON</span><span class="badge">Poor quality is not a veto</span></div></header>
<div class="layout"><form id="approval-form" class="stack" novalidate>
<section class="card"><div class="number">01 · IDENTITY</div><h2>What this approval is bound to</h2><p><b>Profile:</b> <code>scnet-large-musdb-release-v1</code><br><b>Scope:</b> vocals, drums, bass and grouped other<br><b>Checkpoint:</b> <code>719e5abb…3070</code></p><p class="warning">The repository MIT record and official README-linked checkpoint are already accepted for this local preview. No maintainer email is outstanding. Hosted conversion is not authorized here.</p></section>
<section class="card"><div class="number">02 · WHO</div><h2>Who is granting this approval?</h2><label>Your name or project-owner identity<input id="approved-by" type="text" maxlength="200" autocomplete="name" placeholder="For example: Errol Elliott"></label><p class="muted small">This stays in the downloaded JSON. Do not upload the JSON publicly because it also contains local song paths.</p></section>
<section class="card"><div class="number">03 · LISTEN</div><h2>Complete the catastrophic-output listen</h2><p>Listen only for corruption, mislabelling, silence across all roles or gross timing. The known weak synthetic vocal result is a musical limitation, not automatically catastrophic.</p><div class="audio-grid">__AUDIO_SECTIONS__</div><label class="choice"><input id="listen-complete" type="checkbox">I listened to the source, all four estimates and the reconstruction check.</label><label>Catastrophic result<select id="listen-result"><option value="">Choose…</option><option value="no_catastrophic_defect">No catastrophic defect found</option><option value="catastrophic_defect_reported">A catastrophic defect was found</option></select></label><label>Details<textarea id="listen-details" maxlength="5000" placeholder="Required if a catastrophic defect was found; otherwise optional."></textarea></label></section>
<section class="card"><div class="number">04 · SONG RIGHTS</div><h2>Authorize three disjoint full-song canaries</h2><p>Paste absolute local paths. The browser does not read or upload these files. Each song must be one you may process.</p>
<div class="song" data-song="vocal_forward"><h3>Vocal-forward song</h3><label>Absolute local path<input class="song-path" type="text" placeholder="/Users/you/Music/song.wav"></label><label>Rights category<select class="song-rights"><option value="">Choose…</option><option value="owned">Owned</option><option value="licensed">Licensed</option><option value="authorised_private_use">Authorised private use</option><option value="statutory_exception">Documented statutory exception</option></select></label></div>
<div class="song" data-song="dense_electronic"><h3>Dense or electronic song</h3><label>Absolute local path<input class="song-path" type="text" placeholder="/Users/you/Music/song.wav"></label><label>Rights category<select class="song-rights"><option value="">Choose…</option><option value="owned">Owned</option><option value="licensed">Licensed</option><option value="authorised_private_use">Authorised private use</option><option value="statutory_exception">Documented statutory exception</option></select></label></div>
<div class="song" data-song="acoustic_mixed"><h3>Acoustic or mixed-material song</h3><label>Absolute local path<input class="song-path" type="text" placeholder="/Users/you/Music/song.wav"></label><label>Rights category<select class="song-rights"><option value="">Choose…</option><option value="owned">Owned</option><option value="licensed">Licensed</option><option value="authorised_private_use">Authorised private use</option><option value="statutory_exception">Documented statutory exception</option></select></label></div>
<label class="choice"><input id="song-authority" type="checkbox">I authorize offline, network-denied SCNet processing of these three files into fresh local evidence folders. No uploads and no automatic MIDI/Create use.</label></section>
<section class="card"><div class="number">05 · MACHINE CLASS</div><h2>Choose the honest support claim</h2><label class="choice"><input type="radio" name="machine" value="keep_16_gib_requirement">Keep 16 GiB as the required verified class. I will provide access details below.</label><label class="choice"><input type="radio" name="machine" value="verify_36_gib_first">Use the tested 36 GB M3 Max as the first verified preview class. Keep 16 GiB and other Apple-silicon Macs accessible but unverified, supervised and warned.</label><label>16 GiB access details, when keeping that requirement<textarea id="machine-details" maxlength="2000" placeholder="Machine location, owner or how the benchmark can be run."></textarea></label><p class="warning">Approval cannot turn a 36 GB run into 16 GiB evidence. The second choice changes the initial support claim instead.</p></section>
<section class="card"><div class="number">06 · CONDITIONAL ACTIVATION</div><h2>Approve rollout after objective gates</h2><label class="choice"><input id="activation" type="checkbox">If the three song canaries pass licensing, privacy, integrity, clock, reconstruction, crash and declared-resource gates, approve changing this profile from <code>blocked</code> to <code>public_opt_in</code>, enabling the explicit core-four command, publishing known limitations and keeping two-stem separation as default. Poor or mixed musical feedback must not disable the profile.</label></section>
<section class="card"><div class="number">07 · PUBLICATION</div><h2>Choose how far repository delivery may go</h2><label class="choice"><input type="radio" name="publication" value="local_only">Implement locally only. Do not commit, push or deploy.</label><label class="choice"><input type="radio" name="publication" value="draft_pr_no_deploy">Commit and push the coherent changes and open a draft PR. Do not deploy.</label><label class="choice"><input type="radio" name="publication" value="pr_and_deploy_after_verification">Commit, push, open a PR and deploy the public website after verification.</label></section>
<section class="card"><div class="number">08 · DOWNSTREAM BOUNDARY</div><h2>Keep separation and MIDI decisions separate</h2><label class="choice"><input id="midi-boundary" type="checkbox">Separated stems must not enter MIDI/Create automatically. I will approve that separately after listening.</label><p class="muted">This form never approves a hosted conversion service, audio uploads, model mutation or automatic model selection.</p></section>
</form>
<aside class="summary"><div class="number">LIVE SUMMARY</div><h2>Approval status</h2><div id="status" class="status blocked" aria-live="polite"></div><div id="missing-wrap"><h3>Still needed</h3><ul id="missing" class="missing-list"></ul></div><button id="save" class="primary" type="button">Download approval JSON</button><button id="copy" class="secondary" type="button">Copy JSON</button><button id="reset" class="danger" type="button">Clear form</button><p id="action-status" class="muted small" aria-live="polite"></p><details><summary>Preview JSON</summary><textarea id="json-preview" class="json-preview" readonly></textarea></details><p class="privacy"><b>Privacy:</b> the page makes no network requests and stores no draft in browser storage. Downloaded JSON includes the paths you type but no audio, telemetry or file contents. Return its local path to your coding agent; do not attach it to a public issue.</p></aside></div>
<script>
const binding=__BINDING_JSON__;const validRights=new Set(__RIGHTS_JSON__);const form=document.getElementById('approval-form');const approvalId=(globalThis.crypto&&crypto.randomUUID)?crypto.randomUUID():'approval-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);const byId=id=>document.getElementById(id);const checked=name=>document.querySelector('input[name="'+name+'"]:checked')?.value||'';const clean=value=>value.trim();
function songValues(){return [...document.querySelectorAll('[data-song]')].map(node=>({coverage_id:node.dataset.song,absolute_path:clean(node.querySelector('.song-path').value),rights_category:node.querySelector('.song-rights').value}));}
function evaluate(){const missing=[];const approvedBy=clean(byId('approved-by').value);if(!approvedBy)missing.push('Approver identity');const listenComplete=byId('listen-complete').checked;const listenResult=byId('listen-result').value;const listenDetails=clean(byId('listen-details').value);if(!listenComplete)missing.push('Complete synthetic listen');if(!listenResult)missing.push('Choose catastrophic-listen result');if(listenResult==='catastrophic_defect_reported'&&!listenDetails)missing.push('Describe the catastrophic defect');const songs=songValues();for(const song of songs){const label=song.coverage_id.replaceAll('_',' ');if(!song.absolute_path.startsWith('/'))missing.push('Absolute path for '+label);if(!validRights.has(song.rights_category))missing.push('Rights category for '+label);}if(new Set(songs.map(song=>song.absolute_path).filter(Boolean)).size!==3)missing.push('Three distinct song paths');const songAuthority=byId('song-authority').checked;if(!songAuthority)missing.push('Authorize offline full-song canaries');const machine=checked('machine');const machineDetails=clean(byId('machine-details').value);if(!machine)missing.push('Supported-machine decision');if(machine==='keep_16_gib_requirement'&&!machineDetails)missing.push('16 GiB access details');const activation=byId('activation').checked;if(!activation)missing.push('Conditional public activation');const publication=checked('publication');if(!publication)missing.push('Repository publication decision');const midi=byId('midi-boundary').checked;if(!midi)missing.push('Separate MIDI/Create boundary');const stopShip=listenResult==='catastrophic_defect_reported';const approvalComplete=missing.length===0;let status='incomplete';if(approvalComplete&&stopShip)status='stop_ship_reported';else if(approvalComplete&&publication==='local_only')status='approvals_complete_local_only';else if(approvalComplete&&publication==='draft_pr_no_deploy')status='approvals_complete_draft_pr_no_deploy';else if(approvalComplete)status='approvals_complete_for_verified_delivery';const remainingApprovalBlockers=[];if(publication==='local_only')remainingApprovalBlockers.push('commit_push_pr_and_deployment_not_authorized');if(publication==='draft_pr_no_deploy')remainingApprovalBlockers.push('website_deployment_not_authorized');if(stopShip)remainingApprovalBlockers.push('catastrophic_synthetic_finding_requires_resolution');return {schema:binding.schema,status,approval_id:approvalId,profile:{scope_id:binding.scope_id,profile_id:binding.profile_id,source_revision:binding.source_revision,weights_sha256:binding.weights_sha256,config_sha256:binding.config_sha256},evidence_acknowledged:binding.synthetic_evidence,approved_by:approvedBy,approvals:{synthetic_listen:{completed:listenComplete,result:listenResult,details:listenDetails},full_song_canaries:{offline_processing_authorized:songAuthority,songs},supported_machine:{decision:machine,machine_details:machineDetails,claim_effect:machine==='verify_36_gib_first'?'36 GB M3 Max becomes first verified class; 16 GiB remains accessible but unverified':'16 GiB remains required and must be tested on the described machine'},conditional_public_activation:activation,repository_publication:publication,downstream_midi_requires_later_approval:midi},boundaries:{local_processing_only_for_canaries:true,network_model_resolution:false,audio_upload:false,automatic_midi_or_create:false,hosted_conversion_service:false,maintainer_email_required_for_local_preview:false},remaining_approval_blockers:remainingApprovalBlockers,remaining_objective_work:['run and verify three authorised song-disjoint canaries','complete required resource evidence for the selected machine policy','record catastrophic-output listening for each full-song canary'],missing_fields:missing,audio_included:false,browser_telemetry_included:false,exported_at:new Date().toISOString()};}
function render(){const value=evaluate();const status=byId('status');status.className='status '+(value.status==='stop_ship_reported'?'stop':value.missing_fields.length?'blocked':'ready');status.textContent=value.status==='stop_ship_reported'?'Approval recorded a stop-ship finding. Do not activate.':value.missing_fields.length?value.missing_fields.length+' approval item'+(value.missing_fields.length===1?'':'s')+' still required.':'Approvals are complete. Objective runs and their evidence must still be completed.';const list=byId('missing');list.replaceChildren(...value.missing_fields.map(item=>{const li=document.createElement('li');li.textContent=item;return li;}));byId('missing-wrap').hidden=value.missing_fields.length===0;byId('json-preview').value=JSON.stringify(value,null,2);return value;}
function download(){const value=render();const suffix=value.missing_fields.length?'draft':value.status==='stop_ship_reported'?'stop-ship':'approved';const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='sunofriend-core-four-approval-'+suffix+'.json';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);byId('action-status').textContent=value.missing_fields.length?'Draft JSON downloaded. It does not clear every blocker yet.':'Approval JSON downloaded. Return its local path to your coding agent.';}
async function copyJson(){const value=render();try{await navigator.clipboard.writeText(JSON.stringify(value,null,2)+'\n');byId('action-status').textContent='JSON copied. It contains private local paths; do not paste it publicly.';}catch(error){byId('action-status').textContent='Clipboard access was unavailable. Use Download approval JSON instead.';}}
form.addEventListener('input',render);form.addEventListener('change',render);byId('save').addEventListener('click',download);byId('copy').addEventListener('click',copyJson);byId('reset').addEventListener('click',()=>{if(confirm('Clear every answer on this local form?')){form.reset();render();}});render();
</script></main></body></html>'''


__all__ = [
    "APPROVAL_SCHEMA",
    "CONFIG_SHA256",
    "PROFILE_ID",
    "SCOPE_ID",
    "SOURCE_REVISION",
    "WEIGHTS_SHA256",
    "approval_binding",
    "build_core_four_approval_server",
    "render_core_four_approval_html",
    "resolve_core_four_approved_songs",
    "validate_core_four_approval_document",
    "write_core_four_approval_page",
]
