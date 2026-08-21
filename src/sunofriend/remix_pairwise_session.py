"""Private loopback A/B review for controlled deterministic remix variants.

Playback is deliberately non-authoritative.  The only mutation route creates
one exact, explicit owner pairwise label through ``remix_learning_contract``.
The page never selects a remix for the product and never starts training.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
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
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from .musical_state import validate_musical_state
from .remix_delta import inspect_remix_audio
from .remix_identity import validate_remix_identity_state
from .remix_learning_contract import (
    create_remix_pairwise_label,
    validate_remix_controlled_variant_set,
    validate_remix_owner_registry,
)
from .separation_review_transport import parse_file_range
from .source_receipt import canonical_json_bytes


REMIX_PAIRWISE_SESSION_SCHEMA = "sunofriend.remix-pairwise-review-session.v0"
_MAXIMUM_JSON_REQUEST_BYTES = 32 * 1024
_OUTCOMES = frozenset({"a", "b", "equivalent", "neither", "cannot_tell"})
_IDENTITY_RELATIONSHIPS = frozenset(
    {"preserved", "partly_preserved", "lost", "cannot_tell"}
)
_REASON_CODES = frozenset(
    {
        "change_more_useful",
        "identity_better_preserved",
        "separation_artifact",
        "change_inaudible",
        "both_unusable",
        "unable_to_compare",
        "energy_shape",
        "groove_fit",
        "arrangement_fit",
        "other",
    }
)


class RemixPairwiseHTTPServer(ThreadingHTTPServer):
    """Owner-only localhost server for one exact controlled variant pair."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        musical_state: Mapping[str, Any],
        owner_registry: Mapping[str, Any],
        variant_set: Mapping[str, Any],
        identity_state: Mapping[str, Any],
        control_audio: str | Path,
        variant_audio: Mapping[str, str | Path],
        state_dir: str | Path,
        title: str,
        token: str,
        presentation_seed: int,
    ) -> None:
        checked_state = validate_musical_state(musical_state)
        self.identity_state = validate_remix_identity_state(
            identity_state, checked_state
        )
        self.owner_registry = validate_remix_owner_registry(
            owner_registry,
            musical_states=[checked_state],
            identity_states=[self.identity_state],
        )
        self.variant_set = validate_remix_controlled_variant_set(
            variant_set, self.owner_registry, self.identity_state
        )
        variants = self.variant_set["variants"]
        if len(variants) != 2:
            raise ValueError("first remix A/B session requires exactly two variants")
        if isinstance(presentation_seed, bool) or not isinstance(
            presentation_seed, int
        ):
            raise ValueError("presentation seed must be an integer")
        self.presentation_seed = presentation_seed
        self.title = str(title).strip() or "Remix A/B review"
        self.token = token
        self.state_dir = _owner_directory(state_dir)
        self.labels_dir = self.state_dir / "LABELS"
        self.labels_dir.mkdir(mode=0o700, exist_ok=True)
        self.labels_dir.chmod(0o700)

        expected_ids = {row["variant_id"] for row in variants}
        if set(variant_audio) != expected_ids:
            raise ValueError(
                "variant audio roster does not match the exact variant set"
            )
        control_path = _regular_file(control_audio, "source control")
        if inspect_remix_audio(control_path) != self.variant_set["source_control"]:
            raise ValueError("source control audio does not match the variant set")
        media_by_variant: dict[str, dict[str, Any]] = {}
        for row in variants:
            variant_id = row["variant_id"]
            path = _regular_file(variant_audio[variant_id], f"variant {variant_id}")
            expected = row["remix_result"]["output"]
            if inspect_remix_audio(path) != expected:
                raise ValueError(
                    f"variant {variant_id} audio does not match its result"
                )
            media_by_variant[variant_id] = {**expected, "private_path": str(path)}
        self.control_media = {
            **self.variant_set["source_control"],
            "private_path": str(control_path),
        }

        ordered_ids = sorted(expected_ids)
        digest = hashlib.sha256(
            f"{presentation_seed}:{self.variant_set['document_sha256']}".encode()
        ).digest()
        if digest[0] & 1:
            ordered_ids.reverse()
        self.display_variant_ids = {"a": ordered_ids[0], "b": ordered_ids[1]}
        self.media_capabilities: dict[str, dict[str, Any]] = {}
        self.media_urls: dict[str, str] = {}
        for display_id, record in {
            "control": self.control_media,
            "a": media_by_variant[ordered_ids[0]],
            "b": media_by_variant[ordered_ids[1]],
        }.items():
            capability = secrets.token_urlsafe(24)
            self.media_capabilities[capability] = record
            self.media_urls[display_id] = f"/media/{capability}?token={self.token}"
        super().__init__(address, _RemixPairwiseHandler)

    def browser_state(self) -> dict[str, Any]:
        anchors = [
            {
                "anchor_id": row["anchor_id"],
                "owner_label": row["owner_label"],
            }
            for row in self.identity_state["owner_anchors"]
        ]
        return {
            "schema": REMIX_PAIRWISE_SESSION_SCHEMA,
            "status": "awaiting_explicit_owner_label",
            "title": self.title,
            "variant_set_sha256": self.variant_set["document_sha256"],
            "variant_family_id": self.variant_set["variant_family"][
                "variant_family_id"
            ],
            "anchors": anchors,
            "media": {
                name: {"label": label, "media_url": self.media_urls[name]}
                for name, label in (
                    ("control", "Unchanged control"),
                    ("a", "Version A"),
                    ("b", "Version B"),
                )
            },
            "choices": {
                "outcomes": sorted(_OUTCOMES),
                "identity_relationships": sorted(_IDENTITY_RELATIONSHIPS),
                "reason_codes": sorted(_REASON_CODES),
            },
            "authority": {
                "playback_creates_label": False,
                "automatic_preference": False,
                "selected_for_product": False,
                "training_execution_authorized": False,
                "checkpoint_promotion_authorized": False,
            },
            "saved_label": self._saved_summary(),
        }

    def create_label(self, request: Mapping[str, Any]) -> dict[str, Any]:
        expected_keys = {
            "expected_variant_set_sha256",
            "explicitly_heard",
            "outcome",
            "identity_relationships",
            "reason_codes",
            "admit_owner_local_training",
        }
        if set(request) != expected_keys:
            raise ValueError("remix A/B label request fields changed")
        if (
            request.get("expected_variant_set_sha256")
            != self.variant_set["document_sha256"]
        ):
            raise ValueError("remix A/B variant-set identity changed")
        if request.get("explicitly_heard") != {
            "control": True,
            "a": True,
            "b": True,
        }:
            raise ValueError("explicitly confirm hearing control, A and B")
        outcome = request.get("outcome")
        if outcome not in _OUTCOMES:
            raise ValueError("choose one supported A/B outcome")
        identities = request.get("identity_relationships")
        if not isinstance(identities, Mapping) or set(identities) != {"a", "b"}:
            raise ValueError("identity relationship fields changed")
        if any(value not in _IDENTITY_RELATIONSHIPS for value in identities.values()):
            raise ValueError("choose an identity relationship for A and B")
        reasons = request.get("reason_codes")
        if (
            not isinstance(reasons, list)
            or not 1 <= len(reasons) <= 4
            or len(reasons) != len(set(reasons))
            or any(reason not in _REASON_CODES for reason in reasons)
        ):
            raise ValueError("choose one to four supported reasons")
        if request.get("admit_owner_local_training") is not True:
            raise ValueError("local-training admission must be an explicit action")
        if self._saved_labels():
            raise FileExistsError("this exact A/B pair already has a saved label")

        label = create_remix_pairwise_label(
            self.owner_registry,
            self.variant_set,
            self.identity_state,
            left_variant_id=self.display_variant_ids["a"],
            right_variant_id=self.display_variant_ids["b"],
            heard_control=True,
            heard_left=True,
            heard_right=True,
            outcome={"a": "left", "b": "right"}.get(outcome, outcome),
            left_identity_relationship=str(identities["a"]),
            right_identity_relationship=str(identities["b"]),
            reason_codes=reasons,
            training_admission="explicit_owner_local_training",
            presentation_seed=self.presentation_seed,
            reviewed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        destination = self.labels_dir / f"{label['document_sha256']}.json"
        _atomic_owner_file(destination, canonical_json_bytes(label))
        return {
            "schema": label["schema"],
            "status": label["status"],
            "document_sha256": label["document_sha256"],
            "training_eligible": False,
            "training_execution_authorized": False,
            "selected_for_product": False,
        }

    def _saved_labels(self) -> list[Path]:
        return sorted(self.labels_dir.glob("*.json"))

    def _saved_summary(self) -> dict[str, Any] | None:
        labels = self._saved_labels()
        if not labels:
            return None
        try:
            value = json.loads(labels[0].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"status": "saved_label_unreadable"}
        return {
            "status": value.get("status"),
            "document_sha256": value.get("document_sha256"),
        }


class _RemixPairwiseHandler(BaseHTTPRequestHandler):
    server: RemixPairwiseHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        self._read(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._read(head_only=True)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._begin(parsed, mutation=True):
            return
        if parsed.path != "/api/label":
            self._error(HTTPStatus.NOT_FOUND, "remix A/B route not found")
            return
        try:
            label = self.server.create_label(self._request_json())
        except FileExistsError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except (OSError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json(
            HTTPStatus.CREATED, {"label": label, "state": self.server.browser_state()}
        )

    def _read(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            if not self._begin(parsed, mutation=False):
                return
            capability = unquote(parsed.path.removeprefix("/media/"))
            record = self.server.media_capabilities.get(capability)
            if record is None:
                self._error(HTTPStatus.NOT_FOUND, "remix A/B media not found")
                return
            self._media(record, head_only=head_only)
            return
        if not self._begin(parsed, mutation=False):
            return
        assets = {
            "/": ("remix_pairwise_session.html", "text/html; charset=utf-8"),
            "/remix_pairwise_session.js": (
                "remix_pairwise_session.js",
                "text/javascript; charset=utf-8",
            ),
            "/remix_pairwise_session.css": (
                "remix_pairwise_session.css",
                "text/css; charset=utf-8",
            ),
        }
        if parsed.path in assets:
            self._asset(*assets[parsed.path], head_only=head_only)
            return
        if parsed.path == "/api/session":
            self._json(HTTPStatus.OK, self.server.browser_state(), head_only=head_only)
            return
        self._error(HTTPStatus.NOT_FOUND, "remix A/B route not found")

    def _begin(self, parsed: Any, *, mutation: bool) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"} or self.client_address[0] not in {
            "127.0.0.1",
            "::1",
        }:
            self._error(HTTPStatus.FORBIDDEN, "remix A/B session is loopback-only")
            return False
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        if not hmac.compare_digest(supplied, self.server.token):
            self._error(HTTPStatus.FORBIDDEN, "remix A/B token is invalid")
            return False
        if mutation:
            expected = {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
            if self.headers.get("Origin") not in expected:
                self._error(
                    HTTPStatus.FORBIDDEN, "remix A/B changes require same origin"
                )
                return False
        return True

    def _asset(self, name: str, content_type: str, *, head_only: bool) -> None:
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

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("request Content-Length is invalid") from exc
        if not 0 < length <= _MAXIMUM_JSON_REQUEST_BYTES:
            raise ValueError("request JSON must be between 1 byte and 32 KiB")
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


def create_remix_pairwise_review_server(
    musical_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
    variant_set: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    control_audio: str | Path,
    variant_audio: Mapping[str, str | Path],
    state_dir: str | Path,
    title: str = "Remix A/B review",
    port: int = 0,
    token: str | None = None,
    presentation_seed: int | None = None,
) -> RemixPairwiseHTTPServer:
    """Create but do not start one private, exact pairwise review server."""

    if token is None:
        token = secrets.token_urlsafe(32)
    if len(token) < 32:
        raise ValueError("remix A/B token must contain at least 32 characters")
    if presentation_seed is None:
        presentation_seed = secrets.randbits(63)
    return RemixPairwiseHTTPServer(
        ("127.0.0.1", port),
        musical_state=musical_state,
        owner_registry=owner_registry,
        variant_set=variant_set,
        identity_state=identity_state,
        control_audio=control_audio,
        variant_audio=variant_audio,
        state_dir=state_dir,
        title=title,
        token=token,
        presentation_seed=presentation_seed,
    )


def run_remix_pairwise_review_server(
    server: RemixPairwiseHTTPServer, *, open_browser: bool = True
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
        raise ValueError("remix A/B state directory must be a regular directory")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("remix A/B state directory must be owner-only")
    return path


def _regular_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    return path.resolve(strict=True)


def _atomic_owner_file(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to replace existing label: {path.name}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "REMIX_PAIRWISE_SESSION_SCHEMA",
    "RemixPairwiseHTTPServer",
    "create_remix_pairwise_review_server",
    "run_remix_pairwise_review_server",
]
