"""Owner-only loopback session for confirming one remix identity anchor."""

from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse
import webbrowser

from .remix_anchor_preflight import (
    REMIX_ANCHOR_KINDS,
    REMIX_ANCHOR_PRESERVATION_REQUIREMENTS,
    confirm_remix_anchor_preflight,
    create_remix_anchor_preflight_state,
)
from .remix_delta import inspect_remix_audio
from .remix_source_anchor import (
    confirm_remix_source_anchor_preflight,
    create_remix_source_anchor_preflight,
)
from .remix_source_state import (
    REMIX_SOURCE_STATE_SCHEMA,
    validate_remix_project_state,
)
from .separation_review_transport import parse_file_range
from .source_receipt import canonical_json_bytes


REMIX_ANCHOR_SESSION_SCHEMA = "sunofriend.remix-anchor-session.v1"
_MAXIMUM_JSON_REQUEST_BYTES = 16 * 1024
_DIAGNOSTIC_METADATA = {
    "vocals": {
        "label": "Vocal estimate",
        "description": "Often carries the main sung melody and phrasing.",
        "musical_functions": ["melody", "rhythm", "harmony"],
        "estimated_role": "vocal estimate",
    },
    "drums": {
        "label": "Drum estimate",
        "description": "A diagnostic view of groove, pulse and rhythmic accents.",
        "musical_functions": ["rhythm"],
        "estimated_role": "drum estimate",
    },
    "bass": {
        "label": "Bass estimate",
        "description": "May connect bass melody, groove and harmonic movement.",
        "musical_functions": ["melody", "rhythm", "harmony"],
        "estimated_role": "bass estimate",
    },
    "grouped_other": {
        "label": "Grouped accompaniment estimate",
        "description": "Usually keys, guitars, synths or strings; it may contain chords or an instrumental hook.",
        "musical_functions": ["melody", "rhythm", "harmony"],
        "estimated_role": "grouped accompaniment estimate",
    },
}


class RemixAnchorHTTPServer(ThreadingHTTPServer):
    """Loopback-only server for one exact source/estimate anchor decision."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        project_state: Mapping[str, Any],
        source_control: str | Path,
        separation_estimate: str | Path,
        source_estimate_id: str,
        estimated_role: str,
        diagnostic_estimates: Mapping[str, str | Path] | None,
        state_dir: str | Path,
        identity_state_id: str,
        registry_id: str,
        composition_id: str | None,
        group_id: str | None,
        title: str,
        token: str,
    ) -> None:
        self.project_state = validate_remix_project_state(project_state)
        self.title = str(title).strip() or "Define a remix anchor"
        self.token = token
        self.state_dir = _owner_directory(state_dir)
        self.confirmed_dir = self.state_dir / "CONFIRMED"
        if self.project_state["schema"] == REMIX_SOURCE_STATE_SCHEMA:
            for supplied, expected, label in (
                (
                    composition_id,
                    self.project_state["composition_id"],
                    "composition_id",
                ),
                (group_id, self.project_state["group_id"], "group_id"),
            ):
                if supplied is not None and str(supplied) != expected:
                    raise ValueError(f"{label} does not match the remix source state")
            composition_id = self.project_state["composition_id"]
            group_id = self.project_state["group_id"]
        elif composition_id is None or group_id is None:
            raise ValueError(
                "legacy Musical State sessions require composition and group IDs"
            )
        self.identity_values = {
            "identity_state_id": str(identity_state_id),
            "registry_id": str(registry_id),
            "composition_id": str(composition_id),
            "group_id": str(group_id),
        }
        self.source_path = _regular_file(source_control, "source control")
        self.estimate_path = _regular_file(separation_estimate, "separation estimate")
        source_audio = inspect_remix_audio(self.source_path)
        estimate_audio = inspect_remix_audio(self.estimate_path)
        if source_audio["geometry"] != estimate_audio["geometry"]:
            raise ValueError("source control and separation estimate geometry differ")
        self.source_record = {**source_audio, "private_path": str(self.source_path)}
        supplied_diagnostics = dict(diagnostic_estimates or {})
        if supplied_diagnostics:
            if set(supplied_diagnostics) - set(_DIAGNOSTIC_METADATA):
                raise ValueError("remix diagnostic estimate kind is unsupported")
            grouped_other = supplied_diagnostics.get("grouped_other")
            if (
                grouped_other is None
                or _regular_file(grouped_other, "grouped accompaniment estimate")
                != self.estimate_path
            ):
                raise ValueError(
                    "grouped accompaniment diagnostic must match the primary separation estimate"
                )
        else:
            supplied_diagnostics = {"estimate": self.estimate_path}

        self.diagnostic_records: dict[str, dict[str, Any]] = {}
        for diagnostic_id, supplied_path in supplied_diagnostics.items():
            path = _regular_file(supplied_path, f"{diagnostic_id} diagnostic estimate")
            audio = inspect_remix_audio(path)
            if audio["geometry"] != source_audio["geometry"]:
                raise ValueError(
                    f"source control and {diagnostic_id} diagnostic geometry differ"
                )
            if diagnostic_id == "estimate":
                metadata = {
                    "label": "Separated-part estimate",
                    "description": "A separator estimate used only as a diagnostic view.",
                    "musical_functions": [],
                    "estimated_role": str(estimated_role),
                }
                estimate_id = str(source_estimate_id)
            else:
                metadata = _DIAGNOSTIC_METADATA[diagnostic_id]
                estimate_id = (
                    str(source_estimate_id)
                    if diagnostic_id == "grouped_other"
                    else f"{diagnostic_id}-{audio['audio_sha256'][:16]}"
                )
            self.diagnostic_records[diagnostic_id] = {
                "diagnostic_id": diagnostic_id,
                "source_estimate_id": estimate_id,
                "estimated_role": metadata["estimated_role"],
                "label": metadata["label"],
                "description": metadata["description"],
                "musical_functions": list(metadata["musical_functions"]),
                **audio,
                "private_path": str(path),
            }
        if (
            self.project_state["schema"] == REMIX_SOURCE_STATE_SCHEMA
            and source_audio != self.project_state["source_control"]
        ):
            raise ValueError("source control does not match the remix source state")
        self.media_capabilities: dict[str, dict[str, Any]] = {}
        self.media_urls: dict[str, str] = {}
        media_records = [
            ("source", self.source_record),
            *self.diagnostic_records.items(),
        ]
        for name, record in media_records:
            capability = secrets.token_urlsafe(24)
            self.media_capabilities[capability] = record
            self.media_urls[name] = f"/media/{capability}?token={self.token}"
        super().__init__(address, _RemixAnchorHandler)

    def browser_state(self) -> dict[str, Any]:
        geometry = self.source_record["geometry"]
        return {
            "schema": REMIX_ANCHOR_SESSION_SCHEMA,
            "status": (
                "complete_explicit_owner_anchor_no_remix"
                if self.confirmed_dir.exists()
                else "awaiting_explicit_owner_anchor"
            ),
            "title": self.title,
            "project_state": {
                "schema": self.project_state["schema"],
                "document_sha256": self.project_state["document_sha256"],
            },
            "clock": {
                "sample_rate_hz": geometry["sample_rate_hz"],
                "frames": geometry["frames"],
                "duration_seconds": geometry["frames"] / geometry["sample_rate_hz"],
            },
            "media": {
                "source": {
                    "label": "Complete original mix",
                    "description": "The primary truth for what makes this excerpt recognisable.",
                    "media_url": self.media_urls["source"],
                },
                "diagnostics": [
                    {
                        "diagnostic_id": diagnostic_id,
                        "label": record["label"],
                        "description": record["description"],
                        "musical_functions": record["musical_functions"],
                        "source_estimate_id": record["source_estimate_id"],
                        "estimated_role": record["estimated_role"],
                        "media_url": self.media_urls[diagnostic_id],
                    }
                    for diagnostic_id, record in self.diagnostic_records.items()
                ],
            },
            "anchor_kinds": list(REMIX_ANCHOR_KINDS),
            "preservation_requirement": REMIX_ANCHOR_PRESERVATION_REQUIREMENTS[0],
            "saved_confirmation": self._saved_summary(),
            "authority": {
                "playback_creates_anchor": False,
                "automatic_anchor_inference": False,
                "remix_render_authorized": False,
                "pairwise_label_created": False,
                "training_execution_authorized": False,
                "product_selection_authorized": False,
            },
        }

    def confirm_anchor(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if set(request) != {
            "expected_project_state_sha256",
            "explicitly_heard",
            "owner_label",
            "anchor_kind",
            "selected_estimate_id",
            "start_frame",
            "end_frame",
            "preservation_requirement",
        }:
            raise ValueError("anchor confirmation request fields changed")
        if (
            request["expected_project_state_sha256"]
            != self.project_state["document_sha256"]
        ):
            raise ValueError("anchor confirmation project state identity changed")
        heard = request["explicitly_heard"]
        if heard != {"source_control": True, "selected_estimate": True}:
            raise ValueError("explicitly hear the original mix and selected diagnostic")
        if self.confirmed_dir.exists():
            raise FileExistsError("this exact anchor session is already confirmed")
        selected_estimate_id = str(request["selected_estimate_id"])
        selected_estimate = self.diagnostic_records.get(selected_estimate_id)
        if selected_estimate is None:
            raise ValueError("selected diagnostic estimate is unknown")
        estimate = {
            key: selected_estimate[key]
            for key in (
                "source_estimate_id",
                "estimated_role",
                "audio_sha256",
                "audio_bytes",
                "geometry",
            )
        }
        control = {
            key: self.source_record[key]
            for key in ("audio_sha256", "audio_bytes", "geometry")
        }
        keyword = {
            "separation_estimate": estimate,
            "owner_label": request["owner_label"],
            "anchor_kind": request["anchor_kind"],
            "start_frame": request["start_frame"],
            "end_frame": request["end_frame"],
            "preservation_requirement": request["preservation_requirement"],
            "heard_source": True,
            "heard_estimate": True,
        }
        if self.project_state["schema"] == REMIX_SOURCE_STATE_SCHEMA:
            pending = create_remix_source_anchor_preflight(
                self.project_state, **keyword
            )
            result = confirm_remix_source_anchor_preflight(
                pending,
                self.project_state,
                identity_state_id=self.identity_values["identity_state_id"],
                registry_id=self.identity_values["registry_id"],
            )
        else:
            pending = create_remix_anchor_preflight_state(
                self.project_state, source_control=control, **keyword
            )
            result = confirm_remix_anchor_preflight(
                pending, self.project_state, **self.identity_values
            )
        self._publish_confirmation(pending, result)
        return {
            "schema": result["confirmation"]["schema"],
            "status": result["confirmation"]["status"],
            "document_sha256": result["confirmation"]["document_sha256"],
            "remix_render_authorized": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        }

    def _publish_confirmation(
        self, pending: Mapping[str, Any], result: Mapping[str, Any]
    ) -> None:
        if self.confirmed_dir.exists():
            raise FileExistsError("this exact anchor session is already confirmed")
        staging = Path(tempfile.mkdtemp(prefix=".CONFIRMED-", dir=self.state_dir))
        staging.chmod(0o700)
        try:
            documents = {
                "anchor-preflight.json": pending,
                "remix-identity-state.json": result["identity_state"],
                "owner-registry.json": result["owner_registry"],
                "anchor-confirmation.json": result["confirmation"],
            }
            for name, document in documents.items():
                _write_owner_file(staging / name, canonical_json_bytes(document))
            os.replace(staging, self.confirmed_dir)
            self.confirmed_dir.chmod(0o700)
        finally:
            if staging.exists():
                for child in staging.iterdir():
                    child.unlink()
                staging.rmdir()

    def _saved_summary(self) -> dict[str, Any] | None:
        path = self.confirmed_dir / "anchor-confirmation.json"
        if not path.is_file() or path.is_symlink():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"status": "saved_confirmation_unreadable"}
        return {
            "status": document.get("status"),
            "document_sha256": document.get("document_sha256"),
        }


class _RemixAnchorHandler(BaseHTTPRequestHandler):
    server: RemixAnchorHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        self._read(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._read(head_only=True)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._begin(parsed, mutation=True):
            return
        if parsed.path != "/api/confirm":
            self._error(HTTPStatus.NOT_FOUND, "remix anchor route not found")
            return
        try:
            confirmation = self.server.confirm_anchor(self._request_json())
        except FileExistsError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except (OSError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json(
            HTTPStatus.CREATED,
            {"confirmation": confirmation, "state": self.server.browser_state()},
        )

    def _read(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            if not self._begin(parsed, mutation=False):
                return
            capability = unquote(parsed.path.removeprefix("/media/"))
            record = self.server.media_capabilities.get(capability)
            if record is None:
                self._error(HTTPStatus.NOT_FOUND, "remix anchor media not found")
                return
            self._media(record, head_only=head_only)
            return
        if not self._begin(parsed, mutation=False):
            return
        assets = {
            "/remix_anchor_session.js": (
                "remix_anchor_session.js",
                "text/javascript; charset=utf-8",
            ),
            "/remix_anchor_session.css": (
                "remix_anchor_session.css",
                "text/css; charset=utf-8",
            ),
        }
        if parsed.path == "/":
            self._page(head_only=head_only)
            return
        if parsed.path in assets:
            self._asset(*assets[parsed.path], head_only=head_only)
            return
        if parsed.path == "/api/session":
            self._json(HTTPStatus.OK, self.server.browser_state(), head_only=head_only)
            return
        self._error(HTTPStatus.NOT_FOUND, "remix anchor route not found")

    def _begin(self, parsed: Any, *, mutation: bool) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"} or self.client_address[0] not in {
            "127.0.0.1",
            "::1",
        }:
            self._error(HTTPStatus.FORBIDDEN, "remix anchor session is loopback-only")
            return False
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        if not hmac.compare_digest(supplied, self.server.token):
            self._error(HTTPStatus.FORBIDDEN, "remix anchor token is invalid")
            return False
        if mutation:
            expected = {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
            if self.headers.get("Origin") not in expected:
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "remix anchor changes require same origin",
                )
                return False
        return True

    def _asset(self, name: str, content_type: str, *, head_only: bool) -> None:
        payload = Path(__file__).with_name(name).read_bytes()
        self._bytes(HTTPStatus.OK, payload, content_type, head_only=head_only)

    def _page(self, *, head_only: bool) -> None:
        token = quote(self.server.token, safe="")
        payload = (
            Path(__file__)
            .with_name("remix_anchor_session.html")
            .read_text(encoding="utf-8")
            .replace(
                'href="/remix_anchor_session.css"',
                f'href="/remix_anchor_session.css?token={token}"',
            )
            .replace(
                'src="/remix_anchor_session.js"',
                f'src="/remix_anchor_session.js?token={token}"',
            )
            .encode("utf-8")
        )
        self._bytes(
            HTTPStatus.OK,
            payload,
            "text/html; charset=utf-8",
            head_only=head_only,
        )

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
                raise ValueError("authorised remix anchor audio changed after launch")
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

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("request Content-Length is invalid") from exc
        if not 0 < length <= _MAXIMUM_JSON_REQUEST_BYTES:
            raise ValueError("request JSON must be between 1 byte and 16 KiB")
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("request Content-Type must be application/json")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

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


def create_remix_anchor_server(
    project_state: Mapping[str, Any],
    *,
    source_control: str | Path,
    separation_estimate: str | Path,
    source_estimate_id: str,
    estimated_role: str,
    diagnostic_estimates: Mapping[str, str | Path] | None = None,
    state_dir: str | Path,
    identity_state_id: str,
    registry_id: str,
    composition_id: str | None = None,
    group_id: str | None = None,
    title: str = "Define a remix anchor",
    port: int = 0,
    token: str | None = None,
) -> RemixAnchorHTTPServer:
    """Create but do not start one owner-only anchor session."""

    if token is None:
        token = secrets.token_urlsafe(32)
    if len(token) < 32:
        raise ValueError("remix anchor token must contain at least 32 characters")
    return RemixAnchorHTTPServer(
        ("127.0.0.1", port),
        project_state=project_state,
        source_control=source_control,
        separation_estimate=separation_estimate,
        source_estimate_id=source_estimate_id,
        estimated_role=estimated_role,
        diagnostic_estimates=diagnostic_estimates,
        state_dir=state_dir,
        identity_state_id=identity_state_id,
        registry_id=registry_id,
        composition_id=composition_id,
        group_id=group_id,
        title=title,
        token=token,
    )


def run_remix_anchor_server(
    server: RemixAnchorHTTPServer, *, open_browser: bool = True
) -> None:
    """Run the supplied server until interrupted."""

    url = f"http://127.0.0.1:{server.server_port}/?token={server.token}"
    if open_browser:
        webbrowser.open(url)
    print(url, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _owner_directory(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("remix anchor state directory must be a regular directory")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("remix anchor state directory must be owner-only")
    return path


def _regular_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    return path.resolve(strict=True)


def _write_owner_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


__all__ = [
    "REMIX_ANCHOR_SESSION_SCHEMA",
    "RemixAnchorHTTPServer",
    "create_remix_anchor_server",
    "run_remix_anchor_server",
]
