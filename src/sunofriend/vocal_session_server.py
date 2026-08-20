"""Private loopback browser for one path-free Vocal Session projection."""

from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path, PurePosixPath
import secrets
import tempfile
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from .musical_state import validate_musical_state
from .separation_review_transport import parse_file_range
from .vocal_phrase_decision import create_phrase_decision
from .vocal_session import VocalSessionDraftConflictError, VocalSessionStore


_MAXIMUM_JSON_REQUEST_BYTES = 64 * 1024


class VocalSessionHTTPServer(ThreadingHTTPServer):
    """Loopback-only server whose browser projection contains no local paths."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        musical_state_path: str | Path,
        state_dir: str | Path,
        title: str,
        token: str,
    ) -> None:
        state_path = Path(musical_state_path).expanduser().resolve(strict=True)
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("musical state must be readable JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("musical state must be a JSON object")
        self.musical_state = validate_musical_state(value)
        self.musical_state_root = state_path.parent
        self.store = VocalSessionStore(state_dir)
        self.title = str(title).strip() or "Vocal comp session"
        self.token = token
        self.media = _authorised_media(self.musical_state, self.musical_state_root)
        self.media_capabilities = {
            secrets.token_urlsafe(24): record for record in self.media.values()
        }
        self.media_capability_by_source = {
            record["source_id"]: capability
            for capability, record in self.media_capabilities.items()
        }
        super().__init__(address, _VocalSessionHandler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/?token={self.token}"

    def browser_state(self) -> dict[str, Any]:
        session = self.store.current_session(self.musical_state)
        draft = self.store.load_draft(session)
        sources = []
        human_index = 0
        phrase_capture_index = 0
        for source in session["sources"]:
            capability = self.media_capability_by_source[source["source_id"]]
            if source["source_class"] == "human_vocal_take":
                human_index += 1
            elif source["source_class"] == "human_vocal_phrase_capture":
                phrase_capture_index += 1
            media = self.media[source["source_id"]]
            sources.append(
                {
                    **source,
                    "display_label": (
                        "AI reference"
                        if source["source_class"] == "authorised_ai_vocal_reference"
                        else (
                            f"Attempt {human_index}"
                            if source["source_class"] == "human_vocal_take"
                            else source.get(
                                "label", f"Phrase attempt {phrase_capture_index}"
                            )
                        )
                    ),
                    "media_url": f"/media/{capability}",
                    "playback_start_seconds": media.get("playback_start_seconds"),
                    "playback_end_seconds": media.get("playback_end_seconds"),
                }
            )
        return {
            "title": self.title,
            "session": session,
            "draft": draft,
            "sources": sources,
            "recording": {
                "available": False,
                "reason": "A hash-bound backing or reference cue is required before recording.",
            },
            "privacy": {
                "local_only": True,
                "uploads_available": False,
                "playback_creates_decision": False,
            },
        }


def create_vocal_session_server(
    musical_state_path: str | Path,
    *,
    state_dir: str | Path,
    title: str = "Vocal comp session",
    port: int = 0,
    token: str | None = None,
) -> VocalSessionHTTPServer:
    """Create, but do not start, a private loopback Vocal Session server."""

    if not 0 <= int(port) <= 65535:
        raise ValueError("vocal session port must be between 0 and 65535")
    return VocalSessionHTTPServer(
        ("127.0.0.1", int(port)),
        musical_state_path=musical_state_path,
        state_dir=state_dir,
        title=title,
        token=token or secrets.token_urlsafe(32),
    )


def run_vocal_session(
    musical_state_path: str | Path,
    *,
    state_dir: str | Path,
    title: str = "Vocal comp session",
    port: int = 0,
    open_browser: bool = False,
) -> None:
    """Run the Vocal Session until interrupted."""

    server = create_vocal_session_server(
        musical_state_path,
        state_dir=state_dir,
        title=title,
        port=port,
    )
    print(f"Private vocal session: {server.url}")
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    finally:
        server.server_close()


class _VocalSessionHandler(BaseHTTPRequestHandler):
    server: VocalSessionHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        self._read_request(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._read_request(head_only=True)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._begin(parsed, mutation=True):
            return
        if parsed.path != "/api/draft":
            self._error(HTTPStatus.NOT_FOUND, "vocal session route not found")
            return
        try:
            request = self._request_json()
            session = self.server.store.current_session(self.server.musical_state)
            saved = self.server.store.save_draft(
                session,
                _mapping(request.get("draft"), "draft"),
                expected_revision=_integer(
                    request.get("expected_revision"), "expected_revision"
                ),
            )
        except VocalSessionDraftConflictError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except (ValueError, OSError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json(HTTPStatus.OK, {"draft": saved})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._begin(parsed, mutation=True):
            return
        if parsed.path != "/api/decision":
            self._error(HTTPStatus.NOT_FOUND, "vocal session route not found")
            return
        try:
            request = self._request_json()
            session = self.server.store.current_session(self.server.musical_state)
            phrase_id = _text(request.get("phrase_id"), "phrase_id", 256)
            existing = next(
                (
                    row["decision"]
                    for row in session["phrases"]
                    if row["phrase_id"] == phrase_id
                ),
                None,
            )
            if existing is not None:
                self._error(
                    HTTPStatus.CONFLICT,
                    "this phrase already has an explicit decision",
                )
                return
            outcome = _text(request.get("outcome"), "outcome", 64)
            source_id = request.get("source_id")
            if source_id is not None:
                source_id = _text(source_id, "source_id", 256)
            notes = request.get("notes")
            if notes is not None:
                notes = _text(notes, "notes", 2000, allow_empty=True)
            decision = create_phrase_decision(
                self.server.musical_state,
                phrase_id,
                outcome,
                source_id=source_id,
                notes=notes,
            )
            event = self.server.store.append(
                session, {"event_type": "phrase_decision", "decision": decision}
            )
        except (ValueError, OSError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json(
            HTTPStatus.CREATED,
            {
                "event": event,
                "state": self.server.browser_state(),
            },
        )

    def _read_request(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/vocal_session.js":
            if not self._valid_local_request():
                return
            self._asset("vocal_session.js", "text/javascript; charset=utf-8", head_only)
            return
        if parsed.path == "/vocal_session.css":
            if not self._valid_local_request():
                return
            self._asset("vocal_session.css", "text/css; charset=utf-8", head_only)
            return
        if parsed.path.startswith("/media/"):
            if not self._valid_local_request():
                return
            capability = unquote(parsed.path.removeprefix("/media/"))
            record = self.server.media_capabilities.get(capability)
            if record is None:
                self._error(HTTPStatus.NOT_FOUND, "vocal session media not found")
                return
            self._media(record, head_only=head_only)
            return
        if not self._begin(parsed, mutation=False):
            return
        if parsed.path == "/":
            self._asset("vocal_session.html", "text/html; charset=utf-8", head_only)
            return
        if parsed.path == "/api/session":
            self._json(HTTPStatus.OK, self.server.browser_state(), head_only=head_only)
            return
        self._error(HTTPStatus.NOT_FOUND, "vocal session route not found")

    def _begin(self, parsed: Any, *, mutation: bool) -> bool:
        if not self._valid_local_request():
            return False
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        if not hmac.compare_digest(supplied, self.server.token):
            self._error(HTTPStatus.FORBIDDEN, "vocal session token is invalid")
            return False
        if mutation:
            origin = self.headers.get("Origin")
            expected = {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
            if origin not in expected:
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "vocal session changes require the same browser origin",
                )
                return False
        return True

    def _valid_local_request(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"}:
            self._error(HTTPStatus.FORBIDDEN, "vocal session is loopback-only")
            return False
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._error(HTTPStatus.FORBIDDEN, "vocal session is loopback-only")
            return False
        return True

    def _asset(self, name: str, content_type: str, head_only: bool) -> None:
        payload = Path(__file__).with_name(name).read_bytes()
        self._bytes(HTTPStatus.OK, payload, content_type, head_only=head_only)

    def _media(self, record: Mapping[str, Any], *, head_only: bool) -> None:
        path = Path(str(record["private_path"]))
        try:
            snapshot = tempfile.TemporaryFile(mode="w+b")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    snapshot.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if (
                size != record["audio_bytes"]
                or digest.hexdigest() != record["audio_sha256"]
            ):
                raise ValueError("authorised vocal audio changed after launch")
            snapshot.seek(0)
        except (OSError, ValueError) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        with closing(snapshot):
            try:
                selected = parse_file_range(self.headers.get("Range"), size=size)
            except ValueError as exc:
                payload = str(exc).encode("utf-8")
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self._security_headers()
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if not head_only:
                    self.wfile.write(payload)
                return
            status = HTTPStatus.PARTIAL_CONTENT if selected.partial else HTTPStatus.OK
            self.send_response(status)
            self._security_headers()
            self.send_header(
                "Content-Type",
                mimetypes.guess_type(path.name)[0] or "audio/wav",
            )
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(selected.length))
            if selected.partial:
                self.send_header(
                    "Content-Range",
                    f"bytes {selected.start}-{selected.end}/{size}",
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

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("request Content-Length is invalid") from exc
        if not 0 < length <= _MAXIMUM_JSON_REQUEST_BYTES:
            raise ValueError("request JSON must be between 1 byte and 64 KiB")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type != "application/json":
            raise ValueError("request Content-Type must be application/json")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        return _mapping(value, "request")

    def _json(
        self,
        status: HTTPStatus,
        value: Mapping[str, Any],
        *,
        head_only: bool = False,
    ) -> None:
        payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
        self._bytes(
            status,
            payload,
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
        head_only: bool = False,
    ) -> None:
        try:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "microphone=(), autoplay=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "media-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def _authorised_media(
    musical_state: Mapping[str, Any], root: Path
) -> dict[str, dict[str, Any]]:
    vocal = musical_state["vocal_performance_state"]
    sources = list(vocal["takes"])
    sources.extend(vocal.get("phrase_captures", []))
    reference = vocal.get("reference")
    if isinstance(reference, Mapping):
        sources.insert(0, reference)
    authorised: dict[str, dict[str, Any]] = {}
    for source in sources:
        audio = source["audio"]
        relative = PurePosixPath(str(audio["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("vocal session audio path must stay inside its state root")
        path = (root / Path(*relative.parts)).resolve(strict=True)
        if root not in path.parents or not path.is_file():
            raise ValueError("vocal session audio path escaped its state root")
        size = path.stat().st_size
        digest = _file_sha256(path)
        if size != audio["bytes"] or digest != audio["sha256"]:
            raise ValueError("vocal session audio does not match its Musical State")
        authorised[source["source_id"]] = {
            "source_id": source["source_id"],
            "audio_bytes": size,
            "audio_sha256": digest,
            "private_path": str(path),
            **(
                {
                    "playback_start_seconds": source["placement"][
                        "source_phrase_start_frame"
                    ]
                    / source["audio_properties"]["sample_rate"],
                    "playback_end_seconds": source["placement"][
                        "source_phrase_end_frame"
                    ]
                    / source["audio_properties"]["sample_rate"],
                }
                if source.get("source_class") == "human_vocal_phrase_capture"
                else {}
            ),
        }
    return authorised


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _text(value: Any, label: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{label} must be text no longer than {maximum} characters")
    if not allow_empty and not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


__all__ = [
    "VocalSessionHTTPServer",
    "create_vocal_session_server",
    "run_vocal_session",
]
