"""Playback-only hidden A/B audition for a verified remix source-delta render.

This module owns the local transport, anonymous presentation order and
continuous artifact verification for one already-authorised render.  It has no
mutation route: playback cannot create a review, preference or training label.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import secrets
import tempfile
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse
import webbrowser

from .remix_source_delta import verify_remix_source_delta_result
from .remix_source_delta_presentation import (
    resolve_remix_source_delta_display_variants,
)
from .separation_review_transport import parse_file_range
from .source_receipt import canonical_json_bytes


REMIX_SOURCE_DELTA_AUDITION_SCHEMA = (
    "sunofriend.remix-source-delta-ab-audition-session.v0"
)


class RemixSourceDeltaAuditionServer(ThreadingHTTPServer):
    """Owner-only, read-only server for one exact source-delta render."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        render_root: str | Path,
        title: str,
        token: str,
        presentation_seed: int,
    ) -> None:
        if isinstance(presentation_seed, bool) or not isinstance(
            presentation_seed, int
        ):
            raise ValueError("presentation seed must be an integer")
        root = Path(render_root).expanduser().resolve(strict=True)
        self.verified_result = verify_remix_source_delta_result(root)
        self.render_root = root
        self.title = str(title).strip() or "Private remix A/B audition"
        self.token = token
        self.presentation_seed = presentation_seed

        candidates = self.verified_result["artifacts"]["candidates"]
        self.display_variant_ids = resolve_remix_source_delta_display_variants(
            self.verified_result, presentation_seed
        )

        rows = {row["variant_id"]: row for row in candidates}
        original = self.verified_result["artifacts"]["original"]
        records = {
            "control": original,
            "a": rows[self.display_variant_ids["a"]],
            "b": rows[self.display_variant_ids["b"]],
        }
        self.media_capabilities: dict[str, Mapping[str, Any]] = {}
        self.media_urls: dict[str, str] = {}
        for display_id, record in records.items():
            capability = secrets.token_urlsafe(24)
            self.media_capabilities[capability] = record
            self.media_urls[display_id] = f"/media/{capability}?token={self.token}"
        super().__init__(address, _RemixSourceDeltaAuditionHandler)

    def browser_state(self) -> dict[str, Any]:
        """Return the path-free, explicitly non-authoritative browser state."""

        return {
            "schema": REMIX_SOURCE_DELTA_AUDITION_SCHEMA,
            "status": "private_hidden_ab_audition_only",
            "title": self.title,
            "render_sha256": self.verified_result["document_sha256"],
            "media": {
                name: {"label": label, "media_url": self.media_urls[name]}
                for name, label in (
                    ("control", "Unchanged control"),
                    ("a", "Version A"),
                    ("b", "Version B"),
                )
            },
            "authority": {
                "playback_creates_review": False,
                "preference_can_be_saved": False,
                "training_label_created": False,
                "training_execution_authorized": False,
                "product_selection_authorized": False,
            },
        }


class _RemixSourceDeltaAuditionHandler(BaseHTTPRequestHandler):
    server: RemixSourceDeltaAuditionServer

    def do_GET(self) -> None:  # noqa: N802
        self._read(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._read(head_only=True)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorised(parsed):
            return
        self._error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "audition-only session cannot save a review or training label",
        )

    def _read(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if not self._authorised(parsed):
            return
        if parsed.path.startswith("/media/"):
            capability = unquote(parsed.path.removeprefix("/media/"))
            record = self.server.media_capabilities.get(capability)
            if record is None:
                self._error(HTTPStatus.NOT_FOUND, "remix audition media not found")
                return
            self._media(record, head_only=head_only)
            return
        if parsed.path == "/":
            self._html(head_only=head_only)
            return
        assets = {
            "/remix_source_delta_audition.js": (
                "remix_source_delta_audition.js",
                "text/javascript; charset=utf-8",
            ),
            "/remix_source_delta_audition.css": (
                "remix_source_delta_audition.css",
                "text/css; charset=utf-8",
            ),
        }
        if parsed.path in assets:
            self._asset(*assets[parsed.path], head_only=head_only)
            return
        if parsed.path == "/api/session":
            self._json(HTTPStatus.OK, self.server.browser_state(), head_only=head_only)
            return
        self._error(HTTPStatus.NOT_FOUND, "remix audition route not found")

    def _html(self, *, head_only: bool) -> None:
        payload = (
            Path(__file__)
            .with_name("remix_source_delta_audition.html")
            .read_text(encoding="utf-8")
        )
        token = quote(self.server.token, safe="")
        payload = payload.replace(
            'href="/remix_source_delta_audition.css"',
            f'href="/remix_source_delta_audition.css?token={token}"',
        ).replace(
            'src="/remix_source_delta_audition.js"',
            f'src="/remix_source_delta_audition.js?token={token}"',
        )
        self._bytes(
            HTTPStatus.OK,
            payload.encode("utf-8"),
            "text/html; charset=utf-8",
            head_only=head_only,
        )

    def _authorised(self, parsed: Any) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"} or self.client_address[0] not in {
            "127.0.0.1",
            "::1",
        }:
            self._error(HTTPStatus.FORBIDDEN, "remix audition is loopback-only")
            return False
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        if not hmac.compare_digest(supplied, self.server.token):
            self._error(HTTPStatus.FORBIDDEN, "remix audition token is invalid")
            return False
        return True

    def _asset(self, name: str, content_type: str, *, head_only: bool) -> None:
        payload = Path(__file__).with_name(name).read_bytes()
        self._bytes(HTTPStatus.OK, payload, content_type, head_only=head_only)

    def _media(self, record: Mapping[str, Any], *, head_only: bool) -> None:
        path = self.server.render_root / str(record["path"])
        try:
            snapshot = tempfile.TemporaryFile(mode="w+b")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    snapshot.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise ValueError("authorised remix audio changed after launch")
            snapshot.seek(0)
        except (OSError, ValueError) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        with closing(snapshot):
            try:
                selected = parse_file_range(self.headers.get("Range"), size=size)
            except ValueError as exc:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self._security_headers()
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                if not head_only:
                    self.wfile.write(str(exc).encode())
                return
            status = HTTPStatus.PARTIAL_CONTENT if selected.partial else HTTPStatus.OK
            self.send_response(status)
            self._security_headers()
            self.send_header(
                "Content-Type", mimetypes.guess_type(path.name)[0] or "audio/wav"
            )
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(selected.length))
            if selected.partial:
                self.send_header(
                    "Content-Range", f"bytes {selected.start}-{selected.end}/{size}"
                )
            self.end_headers()
            if head_only:
                return
            snapshot.seek(selected.start)
            remaining = selected.length
            while remaining:
                chunk = snapshot.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _json(
        self,
        status: HTTPStatus,
        value: Mapping[str, Any],
        *,
        head_only: bool = False,
    ) -> None:
        self._bytes(
            status,
            canonical_json_bytes(value),
            "application/json; charset=utf-8",
            head_only=head_only,
        )

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": message})

    def _bytes(
        self,
        status: HTTPStatus,
        payload: bytes,
        content_type: str,
        *,
        head_only: bool,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; media-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def create_remix_source_delta_audition_server(
    render_root: str | Path,
    *,
    title: str = "Private remix A/B audition",
    port: int = 0,
    token: str | None = None,
    presentation_seed: int | None = None,
) -> RemixSourceDeltaAuditionServer:
    """Create, but do not start, one verified playback-only A/B server."""

    if token is None:
        token = secrets.token_urlsafe(32)
    if len(token) < 32:
        raise ValueError("remix audition token must contain at least 32 characters")
    if presentation_seed is None:
        presentation_seed = secrets.randbits(63)
    return RemixSourceDeltaAuditionServer(
        ("127.0.0.1", port),
        render_root=render_root,
        title=title,
        token=token,
        presentation_seed=presentation_seed,
    )


def run_remix_source_delta_audition_server(
    server: RemixSourceDeltaAuditionServer, *, open_browser: bool = True
) -> None:
    """Run the supplied local read-only server until interrupted."""

    url = f"http://127.0.0.1:{server.server_port}/?token={server.token}"
    if open_browser:
        webbrowser.open(url)
    print(url, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
