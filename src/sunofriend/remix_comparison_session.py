"""Owner-only loopback review for one exact controlled remix comparison.

This surface is deliberately review-only. Playback, drafts and saved reviews do
not create a learning label, select a product result or authorize training. The
session accepts the audio-native remix source/identity v1 evidence directly; it
does not project that evidence into the legacy Musical State renderer.
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
import re
import secrets
import stat
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from .remix_delta import inspect_remix_audio
from .remix_source_anchor import (
    validate_remix_source_anchor_confirmation,
    validate_remix_source_anchor_preflight,
    validate_remix_source_identity_state,
    validate_remix_source_owner_registry,
)
from .remix_source_state import validate_remix_source_state
from .separation_review_transport import parse_file_range
from .source_receipt import canonical_json_bytes, document_sha256


REMIX_COMPARISON_SESSION_SCHEMA = "sunofriend.remix-comparison-session.v0"
REMIX_COMPARISON_REVIEW_SCHEMA = "sunofriend.remix-comparison-review.v0"
REMIX_COMPARISON_REOPEN_SCHEMA = "sunofriend.remix-comparison-reopen.v0"
_MAXIMUM_JSON_REQUEST_BYTES = 32 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_OUTCOMES = frozenset({"a", "b", "equivalent", "neither", "cannot_tell"})
_IDENTITY = frozenset({"preserved", "partly_preserved", "lost", "cannot_tell"})
_USEFULNESS = frozenset(
    {"useful", "not_useful", "equivalent_to_original", "cannot_tell"}
)
_REASONS = frozenset(
    {
        "musical_change",
        "identity_retention",
        "energy_shape",
        "groove_fit",
        "arrangement_fit",
        "balance",
        "artifact",
        "change_inaudible",
        "both_unusable",
        "unable_to_compare",
        "other",
    }
)
_REOPEN_REASONS = frozenset(
    {"listen_again", "change_answer", "audio_issue", "compare_new_context", "other"}
)


class RemixComparisonHTTPServer(ThreadingHTTPServer):
    """Private review session for original context and one hidden A/B pair."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        source_state: Mapping[str, Any],
        anchor_preflight: Mapping[str, Any],
        identity_state: Mapping[str, Any],
        owner_registry: Mapping[str, Any],
        anchor_confirmation: Mapping[str, Any],
        original_audio: str | Path,
        candidate_audio: Mapping[str, str | Path],
        state_dir: str | Path,
        title: str,
        goal: str,
        token: str,
        presentation_seed: int | None,
    ) -> None:
        self.source_state = validate_remix_source_state(source_state)
        self.anchor_preflight = validate_remix_source_anchor_preflight(
            anchor_preflight, self.source_state
        )
        self.identity_state = validate_remix_source_identity_state(
            identity_state, self.source_state
        )
        self.owner_registry = validate_remix_source_owner_registry(
            owner_registry, self.source_state, self.identity_state
        )
        self.anchor_confirmation = validate_remix_source_anchor_confirmation(
            anchor_confirmation,
            self.anchor_preflight,
            self.source_state,
            self.identity_state,
            self.owner_registry,
        )
        self.title = _bounded_line(title, "title", 120)
        self.goal = _bounded_line(goal, "goal", 240)
        self.token = token
        self.state_dir = _owner_directory(state_dir)
        self.reviews_dir = _owner_subdirectory(self.state_dir / "REVIEWS")
        self.history_dir = _owner_subdirectory(self.state_dir / "HISTORY")

        original_path = _regular_file(original_audio, "original context")
        original = inspect_remix_audio(original_path)
        if original != self.source_state["source_control"]:
            raise ValueError("original context audio does not match the source state")
        if len(candidate_audio) != 2:
            raise ValueError(
                "controlled remix comparison requires exactly two candidates"
            )
        candidates: dict[str, dict[str, Any]] = {}
        for candidate_id, value in candidate_audio.items():
            checked_id = _safe_id(candidate_id, "candidate ID")
            path = _regular_file(value, f"candidate {checked_id}")
            record = inspect_remix_audio(path)
            if record["geometry"] != original["geometry"]:
                raise ValueError("candidate audio clock differs from original context")
            candidates[checked_id] = {**record, "private_path": str(path)}
        if len(candidates) != 2:
            raise ValueError("candidate IDs must be unique")

        self.comparison = _comparison_document(
            source_state=self.source_state,
            identity_state=self.identity_state,
            owner_registry=self.owner_registry,
            anchor_confirmation=self.anchor_confirmation,
            original=original,
            candidates=candidates,
            title=self.title,
            goal=self.goal,
        )
        session = self._load_or_create_session(candidates, presentation_seed)
        self.session = session
        self.display_candidate_ids = dict(session["hidden_mapping"])
        self.media_capabilities: dict[str, dict[str, Any]] = {}
        self.media_urls: dict[str, str] = {}
        records = {
            "original": {**original, "private_path": str(original_path)},
            "a": candidates[self.display_candidate_ids["a"]],
            "b": candidates[self.display_candidate_ids["b"]],
        }
        for display_id, record in records.items():
            capability = secrets.token_urlsafe(24)
            self.media_capabilities[capability] = record
            self.media_urls[display_id] = f"/media/{capability}?token={self.token}"
        super().__init__(address, _RemixComparisonHandler)

    def browser_state(self) -> dict[str, Any]:
        reviews = self._reviews()
        reopen_events = self._reopen_events()
        open_revision = len(reviews) == 0 or len(reopen_events) >= len(reviews)
        revision = len(reviews) + 1
        draft = self._load_draft(revision) if open_revision else None
        anchors = [row["owner_label"] for row in self.identity_state["owner_anchors"]]
        return {
            "schema": REMIX_COMPARISON_SESSION_SCHEMA,
            "status": "open_for_review" if open_revision else "review_saved",
            "title": self.title,
            "goal": self.goal,
            "anchors": anchors,
            "comparison_sha256": self.comparison["document_sha256"],
            "mapping_commitment": self.session["mapping_commitment"],
            "revision": revision if open_revision else len(reviews),
            "media": {
                name: {"label": label, "media_url": self.media_urls[name]}
                for name, label in (
                    ("original", "Original context"),
                    ("a", "Version A"),
                    ("b", "Version B"),
                )
            },
            "choices": {
                "outcomes": sorted(_OUTCOMES),
                "identity_retention": sorted(_IDENTITY),
                "goal_usefulness": sorted(_USEFULNESS),
                "reason_codes": sorted(_REASONS),
                "reopen_reasons": sorted(_REOPEN_REASONS),
            },
            "draft": draft,
            "saved_review": _review_summary(reviews[-1]) if reviews else None,
            "history": [
                {
                    "revision": row["revision"],
                    "reviewed_at": row["reviewed_at"],
                    "document_sha256": row["document_sha256"],
                }
                for row in reviews
            ],
            "authority": _no_authority(),
            "effects": _no_effects(),
        }

    def save_draft(self, request: Mapping[str, Any]) -> dict[str, Any]:
        state = self.browser_state()
        if state["status"] != "open_for_review":
            raise FileExistsError("this review is saved; reopen it before editing")
        answers = _validate_answers_request(request, allow_incomplete=True)
        if request["expected_comparison_sha256"] != self.comparison["document_sha256"]:
            raise ValueError("comparison identity changed")
        revision = state["revision"]
        draft = {
            "schema": "sunofriend.remix-comparison-draft.v0",
            "status": "local_draft_no_authority",
            "comparison_sha256": self.comparison["document_sha256"],
            "revision": revision,
            "answers": answers,
            "updated_at": _now(),
            "authority": _no_authority(),
            "effects": _no_effects(),
        }
        draft["document_sha256"] = document_sha256(draft)
        _replace_owner_file(self.state_dir / "DRAFT.json", canonical_json_bytes(draft))
        return draft

    def save_review(self, request: Mapping[str, Any]) -> dict[str, Any]:
        state = self.browser_state()
        if state["status"] != "open_for_review":
            raise FileExistsError("this review is already saved")
        answers = _validate_answers_request(request, allow_incomplete=False)
        if request["expected_comparison_sha256"] != self.comparison["document_sha256"]:
            raise ValueError("comparison identity changed")
        revision = state["revision"]
        mapping = self.session["hidden_mapping"]
        candidates = self.comparison["candidates"]
        by_id = {row["candidate_id"]: row["audio"] for row in candidates}
        review: dict[str, Any] = {
            "schema": REMIX_COMPARISON_REVIEW_SCHEMA,
            "status": "complete_owner_review_no_downstream_authority",
            "revision": revision,
            "binding": {
                "source_state_sha256": self.source_state["document_sha256"],
                "identity_state_sha256": self.identity_state["document_sha256"],
                "owner_registry_sha256": self.owner_registry["document_sha256"],
                "anchor_confirmation_sha256": self.anchor_confirmation[
                    "document_sha256"
                ],
                "comparison_sha256": self.comparison["document_sha256"],
                "mapping_commitment": self.session["mapping_commitment"],
            },
            "presentation": {
                name: {"candidate_id": mapping[name], "audio": by_id[mapping[name]]}
                for name in ("a", "b")
            },
            "answers": answers,
            "reviewed_at": _now(),
            "authority": _no_authority(),
            "effects": _no_effects(),
        }
        review["document_sha256"] = document_sha256(review)
        destination = self.reviews_dir / (
            f"{revision:04d}-{review['document_sha256']}.json"
        )
        _create_owner_file(destination, canonical_json_bytes(review))
        return review

    def reopen_review(self, request: Mapping[str, Any]) -> dict[str, Any]:
        state = self.browser_state()
        if state["status"] != "review_saved" or not state["saved_review"]:
            raise ValueError("there is no closed review to reopen")
        if set(request) != {
            "expected_comparison_sha256",
            "expected_review_sha256",
            "reason_code",
        }:
            raise ValueError("reopen request fields changed")
        if request["expected_comparison_sha256"] != self.comparison["document_sha256"]:
            raise ValueError("comparison identity changed")
        previous = self._reviews()[-1]
        if request["expected_review_sha256"] != previous["document_sha256"]:
            raise ValueError("saved review identity changed")
        reason = request["reason_code"]
        if reason not in _REOPEN_REASONS:
            raise ValueError("choose one supported reason for reopening")
        event: dict[str, Any] = {
            "schema": REMIX_COMPARISON_REOPEN_SCHEMA,
            "status": "review_reopened_no_downstream_authority",
            "comparison_sha256": self.comparison["document_sha256"],
            "previous_review_sha256": previous["document_sha256"],
            "from_revision": previous["revision"],
            "to_revision": previous["revision"] + 1,
            "reason_code": reason,
            "reopened_at": _now(),
            "authority": _no_authority(),
            "effects": _no_effects(),
        }
        event["document_sha256"] = document_sha256(event)
        destination = self.history_dir / (
            f"{event['to_revision']:04d}-{event['document_sha256']}.json"
        )
        _create_owner_file(destination, canonical_json_bytes(event))
        seed = {
            "expected_comparison_sha256": self.comparison["document_sha256"],
            **previous["answers"],
        }
        self.save_draft(seed)
        return event

    def _load_or_create_session(
        self, candidates: Mapping[str, Mapping[str, Any]], seed: int | None
    ) -> dict[str, Any]:
        destination = self.state_dir / "SESSION.json"
        if destination.exists():
            value = json.loads(destination.read_text(encoding="utf-8"))
            if (
                set(value)
                != {
                    "schema",
                    "status",
                    "comparison_sha256",
                    "presentation_seed",
                    "hidden_mapping",
                    "mapping_commitment",
                    "authority",
                    "effects",
                    "document_sha256",
                }
                or value.get("schema") != REMIX_COMPARISON_SESSION_SCHEMA
                or value.get("status") != "stable_hidden_mapping_no_authority"
                or value.get("comparison_sha256") != self.comparison["document_sha256"]
                or document_sha256(
                    {k: v for k, v in value.items() if k != "document_sha256"}
                )
                != value.get("document_sha256")
                or value.get("authority") != _no_authority()
                or value.get("effects") != _no_effects()
            ):
                raise ValueError("saved comparison session does not match these inputs")
            mapping = value.get("hidden_mapping")
            if (
                not isinstance(mapping, Mapping)
                or set(mapping) != {"a", "b"}
                or set(mapping.values()) != set(candidates)
            ):
                raise ValueError("saved hidden comparison mapping changed")
            expected_commitment = document_sha256(
                {
                    "comparison_sha256": self.comparison["document_sha256"],
                    "presentation_seed": value["presentation_seed"],
                    "hidden_mapping": dict(mapping),
                }
            )
            if value["mapping_commitment"] != expected_commitment:
                raise ValueError("saved hidden comparison commitment changed")
            return value
        if seed is None:
            seed = secrets.randbits(63)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("presentation seed must be an integer")
        ordered = sorted(candidates)
        digest = hashlib.sha256(
            f"{seed}:{self.comparison['document_sha256']}".encode()
        ).digest()
        if digest[0] & 1:
            ordered.reverse()
        mapping = {"a": ordered[0], "b": ordered[1]}
        commitment = document_sha256(
            {
                "comparison_sha256": self.comparison["document_sha256"],
                "presentation_seed": seed,
                "hidden_mapping": mapping,
            }
        )
        value: dict[str, Any] = {
            "schema": REMIX_COMPARISON_SESSION_SCHEMA,
            "status": "stable_hidden_mapping_no_authority",
            "comparison_sha256": self.comparison["document_sha256"],
            "presentation_seed": seed,
            "hidden_mapping": mapping,
            "mapping_commitment": commitment,
            "authority": _no_authority(),
            "effects": _no_effects(),
        }
        value["document_sha256"] = document_sha256(value)
        _create_owner_file(destination, canonical_json_bytes(value))
        return value

    def _reviews(self) -> list[dict[str, Any]]:
        reviews = [
            self._validate_review(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self.reviews_dir.glob("*.json"))
        ]
        if [row["revision"] for row in reviews] != list(range(1, len(reviews) + 1)):
            raise ValueError("saved comparison review revision history changed")
        return reviews

    def _reopen_events(self) -> list[dict[str, Any]]:
        reviews = self._reviews()
        events = [
            self._validate_reopen(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self.history_dir.glob("*.json"))
        ]
        for index, event in enumerate(events):
            if (
                event["from_revision"] != index + 1
                or event["to_revision"] != index + 2
                or index >= len(reviews)
                or event["previous_review_sha256"] != reviews[index]["document_sha256"]
            ):
                raise ValueError("comparison reopen history changed")
        return events

    def _load_draft(self, revision: int) -> dict[str, Any] | None:
        path = self.state_dir / "DRAFT.json"
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            set(value)
            != {
                "schema",
                "status",
                "comparison_sha256",
                "revision",
                "answers",
                "updated_at",
                "authority",
                "effects",
                "document_sha256",
            }
            or value.get("schema") != "sunofriend.remix-comparison-draft.v0"
            or value.get("status") != "local_draft_no_authority"
            or value.get("comparison_sha256") != self.comparison["document_sha256"]
            or value.get("revision") != revision
            or value.get("authority") != _no_authority()
            or value.get("effects") != _no_effects()
            or document_sha256(
                {key: item for key, item in value.items() if key != "document_sha256"}
            )
            != value.get("document_sha256")
        ):
            raise ValueError("saved comparison draft changed")
        request = {
            "expected_comparison_sha256": self.comparison["document_sha256"],
            **value["answers"],
        }
        if (
            _validate_answers_request(request, allow_incomplete=True)
            != value["answers"]
        ):
            raise ValueError("saved comparison draft answers changed")
        return value

    def _validate_review(self, value: Mapping[str, Any]) -> dict[str, Any]:
        document = dict(value)
        if set(document) != {
            "schema",
            "status",
            "revision",
            "binding",
            "presentation",
            "answers",
            "reviewed_at",
            "authority",
            "effects",
            "document_sha256",
        }:
            raise ValueError("saved comparison review fields changed")
        expected_binding = {
            "source_state_sha256": self.source_state["document_sha256"],
            "identity_state_sha256": self.identity_state["document_sha256"],
            "owner_registry_sha256": self.owner_registry["document_sha256"],
            "anchor_confirmation_sha256": self.anchor_confirmation["document_sha256"],
            "comparison_sha256": self.comparison["document_sha256"],
            "mapping_commitment": self.session["mapping_commitment"],
        }
        mapping = self.session["hidden_mapping"]
        by_id = {
            row["candidate_id"]: row["audio"] for row in self.comparison["candidates"]
        }
        expected_presentation = {
            name: {"candidate_id": mapping[name], "audio": by_id[mapping[name]]}
            for name in ("a", "b")
        }
        revision = document["revision"]
        if (
            document["schema"] != REMIX_COMPARISON_REVIEW_SCHEMA
            or document["status"] != "complete_owner_review_no_downstream_authority"
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision <= 0
            or document["binding"] != expected_binding
            or document["presentation"] != expected_presentation
            or document["authority"] != _no_authority()
            or document["effects"] != _no_effects()
            or document_sha256(
                {
                    key: item
                    for key, item in document.items()
                    if key != "document_sha256"
                }
            )
            != document["document_sha256"]
        ):
            raise ValueError("saved comparison review evidence changed")
        request = {
            "expected_comparison_sha256": self.comparison["document_sha256"],
            **document["answers"],
        }
        if (
            _validate_answers_request(request, allow_incomplete=False)
            != document["answers"]
        ):
            raise ValueError("saved comparison review answers changed")
        _bounded_line(document["reviewed_at"], "reviewed_at", 80)
        return document

    def _validate_reopen(self, value: Mapping[str, Any]) -> dict[str, Any]:
        document = dict(value)
        if set(document) != {
            "schema",
            "status",
            "comparison_sha256",
            "previous_review_sha256",
            "from_revision",
            "to_revision",
            "reason_code",
            "reopened_at",
            "authority",
            "effects",
            "document_sha256",
        }:
            raise ValueError("comparison reopen fields changed")
        if (
            document["schema"] != REMIX_COMPARISON_REOPEN_SCHEMA
            or document["status"] != "review_reopened_no_downstream_authority"
            or document["comparison_sha256"] != self.comparison["document_sha256"]
            or document["reason_code"] not in _REOPEN_REASONS
            or document["authority"] != _no_authority()
            or document["effects"] != _no_effects()
            or document_sha256(
                {
                    key: item
                    for key, item in document.items()
                    if key != "document_sha256"
                }
            )
            != document["document_sha256"]
        ):
            raise ValueError("comparison reopen evidence changed")
        _bounded_line(document["reopened_at"], "reopened_at", 80)
        return document


class _RemixComparisonHandler(BaseHTTPRequestHandler):
    server: RemixComparisonHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        self._read(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._read(head_only=True)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._begin(parsed, mutation=True):
            return
        try:
            request = self._request_json()
            if parsed.path == "/api/draft":
                result = {"draft": self.server.save_draft(request)}
                status = HTTPStatus.OK
            elif parsed.path == "/api/review":
                result = {"review": _review_summary(self.server.save_review(request))}
                status = HTTPStatus.CREATED
            elif parsed.path == "/api/reopen":
                result = {"reopen": self.server.reopen_review(request)}
                status = HTTPStatus.CREATED
            else:
                self._error(HTTPStatus.NOT_FOUND, "comparison route not found")
                return
        except FileExistsError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except (OSError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        result["state"] = self.server.browser_state()
        self._json(status, result)

    def _read(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            if not self._begin(parsed, mutation=False):
                return
            capability = unquote(parsed.path.removeprefix("/media/"))
            record = self.server.media_capabilities.get(capability)
            if record is None:
                self._error(HTTPStatus.NOT_FOUND, "comparison audio not found")
                return
            self._media(record, head_only=head_only)
            return
        if not self._begin(parsed, mutation=False):
            return
        assets = {
            "/": ("remix_comparison_session.html", "text/html; charset=utf-8"),
            "/remix_comparison_session.js": (
                "remix_comparison_session.js",
                "text/javascript; charset=utf-8",
            ),
            "/remix_comparison_session.css": (
                "remix_comparison_session.css",
                "text/css; charset=utf-8",
            ),
        }
        if parsed.path in assets:
            self._asset(*assets[parsed.path], head_only=head_only)
        elif parsed.path == "/api/session":
            self._json(HTTPStatus.OK, self.server.browser_state(), head_only=head_only)
        else:
            self._error(HTTPStatus.NOT_FOUND, "comparison route not found")

    def _begin(self, parsed: Any, *, mutation: bool) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"} or self.client_address[0] not in {
            "127.0.0.1",
            "::1",
        }:
            self._error(HTTPStatus.FORBIDDEN, "comparison session is loopback-only")
            return False
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        if not hmac.compare_digest(supplied, self.server.token):
            self._error(HTTPStatus.FORBIDDEN, "comparison token is invalid")
            return False
        if mutation:
            expected = {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
            if self.headers.get("Origin") not in expected:
                self._error(HTTPStatus.FORBIDDEN, "changes require the same local page")
                return False
        return True

    def _asset(self, name: str, content_type: str, *, head_only: bool) -> None:
        self._bytes(
            HTTPStatus.OK,
            Path(__file__).with_name(name).read_bytes(),
            content_type,
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
                raise ValueError("authorised comparison audio changed after launch")
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
        self, status: HTTPStatus, value: Mapping[str, Any], *, head_only: bool = False
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
        self, status: HTTPStatus, payload: bytes, content_type: str, *, head_only: bool
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


def create_remix_comparison_server(
    source_state: Mapping[str, Any],
    anchor_preflight: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
    anchor_confirmation: Mapping[str, Any],
    *,
    original_audio: str | Path,
    candidate_audio: Mapping[str, str | Path],
    state_dir: str | Path,
    title: str = "Controlled remix review",
    goal: str = "Make the remix more useful while keeping the song recognisable.",
    port: int = 0,
    token: str | None = None,
    presentation_seed: int | None = None,
) -> RemixComparisonHTTPServer:
    """Create but do not start one exact, review-only comparison server."""

    if token is None:
        token = secrets.token_urlsafe(32)
    if len(token) < 32:
        raise ValueError("comparison token must contain at least 32 characters")
    return RemixComparisonHTTPServer(
        ("127.0.0.1", port),
        source_state=source_state,
        anchor_preflight=anchor_preflight,
        identity_state=identity_state,
        owner_registry=owner_registry,
        anchor_confirmation=anchor_confirmation,
        original_audio=original_audio,
        candidate_audio=candidate_audio,
        state_dir=state_dir,
        title=title,
        goal=goal,
        token=token,
        presentation_seed=presentation_seed,
    )


def run_remix_comparison_server(
    server: RemixComparisonHTTPServer, *, open_browser: bool = True
) -> None:
    """Run the local comparison page until interrupted."""

    url = f"http://127.0.0.1:{server.server_port}/?token={server.token}"
    if open_browser:
        webbrowser.open(url)
    print(url, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _comparison_document(
    *,
    source_state: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
    anchor_confirmation: Mapping[str, Any],
    original: Mapping[str, Any],
    candidates: Mapping[str, Mapping[str, Any]],
    title: str,
    goal: str,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "sunofriend.remix-comparison-package.v0",
        "status": "complete_exact_audio_review_package_no_renderer_claim",
        "binding": {
            "source_state_sha256": source_state["document_sha256"],
            "identity_state_sha256": identity_state["document_sha256"],
            "owner_registry_sha256": owner_registry["document_sha256"],
            "anchor_confirmation_sha256": anchor_confirmation["document_sha256"],
        },
        "title": title,
        "goal": goal,
        "original": dict(original),
        "candidates": [
            {
                "candidate_id": candidate_id,
                "audio": {
                    key: value[key]
                    for key in ("audio_sha256", "audio_bytes", "geometry")
                },
            }
            for candidate_id, value in sorted(candidates.items())
        ],
        "provenance_boundary": {
            "legacy_v0_renderer_claimed": False,
            "v1_renderer_claimed": False,
            "candidate_generation_method_claimed": False,
        },
        "authority": _no_authority(),
        "effects": _no_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _validate_answers_request(
    request: Mapping[str, Any], *, allow_incomplete: bool
) -> dict[str, Any]:
    expected = {
        "expected_comparison_sha256",
        "explicitly_heard",
        "outcome",
        "identity_retention",
        "goal_usefulness",
        "reason_codes",
    }
    if set(request) != expected:
        raise ValueError("review answer fields changed")
    expected_hash = request["expected_comparison_sha256"]
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("comparison identity is invalid")
    heard = request["explicitly_heard"]
    if not isinstance(heard, Mapping) or set(heard) != {"original", "a", "b"}:
        raise ValueError("listening confirmation fields changed")
    if any(not isinstance(value, bool) for value in heard.values()):
        raise ValueError("listening confirmations must be explicit")
    outcome = str(request["outcome"])
    identity, usefulness = _answer_pair_fields(request)
    reasons = _answer_reason_codes(request["reason_codes"])
    _validate_answer_completion(
        allow_incomplete=allow_incomplete,
        heard=heard,
        outcome=outcome,
        identity=identity,
        usefulness=usefulness,
        reasons=reasons,
    )
    return {
        "explicitly_heard": dict(heard),
        "outcome": outcome,
        "identity_retention": dict(identity),
        "goal_usefulness": dict(usefulness),
        "reason_codes": list(reasons),
    }


def _answer_pair_fields(
    request: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Validate the paired identity and usefulness answer shapes."""

    identity = request["identity_retention"]
    usefulness = request["goal_usefulness"]
    if not isinstance(identity, Mapping) or set(identity) != {"a", "b"}:
        raise ValueError("identity answer fields changed")
    if not isinstance(usefulness, Mapping) or set(usefulness) != {"a", "b"}:
        raise ValueError("usefulness answer fields changed")
    return identity, usefulness


def _answer_reason_codes(value: Any) -> list[str]:
    """Validate the bounded, distinct review-reason vocabulary."""

    reasons = value
    if (
        not isinstance(reasons, list)
        or len(reasons) != len(set(reasons))
        or len(reasons) > 4
    ):
        raise ValueError("choose no more than four different reasons")
    if any(reason not in _REASONS for reason in reasons):
        raise ValueError("reason is unsupported")
    return reasons


def _validate_answer_completion(
    *,
    allow_incomplete: bool,
    heard: Mapping[str, Any],
    outcome: str,
    identity: Mapping[str, Any],
    usefulness: Mapping[str, Any],
    reasons: list[str],
) -> None:
    """Route draft and completed answers through their distinct policies."""

    if allow_incomplete:
        _validate_incomplete_answers(
            outcome=outcome, identity=identity, usefulness=usefulness
        )
    else:
        _validate_complete_answers(
            heard=heard,
            outcome=outcome,
            identity=identity,
            usefulness=usefulness,
            reasons=reasons,
        )


def _validate_incomplete_answers(
    *, outcome: str, identity: Mapping[str, Any], usefulness: Mapping[str, Any]
) -> None:
    if outcome and outcome not in _OUTCOMES:
        raise ValueError("comparison outcome is unsupported")
    if any(value and value not in _IDENTITY for value in identity.values()):
        raise ValueError("identity answer is unsupported")
    if any(value and value not in _USEFULNESS for value in usefulness.values()):
        raise ValueError("usefulness answer is unsupported")


def _validate_complete_answers(
    *,
    heard: Mapping[str, Any],
    outcome: str,
    identity: Mapping[str, Any],
    usefulness: Mapping[str, Any],
    reasons: Sequence[str],
) -> None:
    if heard != {"original": True, "a": True, "b": True}:
        raise ValueError("explicitly confirm hearing original context, A and B")
    if outcome not in _OUTCOMES:
        raise ValueError("choose one comparison result")
    if any(value not in _IDENTITY for value in identity.values()):
        raise ValueError("answer both identity questions")
    if any(value not in _USEFULNESS for value in usefulness.values()):
        raise ValueError("answer both usefulness questions")
    if not reasons:
        raise ValueError("choose one to four reasons")


def _review_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": value["status"],
        "revision": value["revision"],
        "reviewed_at": value["reviewed_at"],
        "document_sha256": value["document_sha256"],
    }


def _no_authority() -> dict[str, bool]:
    return {
        "playback_selects_candidate": False,
        "review_selects_product_result": False,
        "pairwise_training_label_created": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
    }


def _no_effects() -> dict[str, bool]:
    return {
        "audio_mutated": False,
        "remix_rendered": False,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_id(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} is not a safe identifier")
    return text


def _bounded_line(value: Any, label: str, maximum: int) -> str:
    text = str(value).strip()
    if not text or len(text) > maximum or "\n" in text or "\r" in text:
        raise ValueError(f"{label} must be one bounded line")
    return text


def _owner_directory(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("comparison state directory must be a regular directory")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("comparison state directory must be owner-only")
    return path


def _owner_subdirectory(path: Path) -> Path:
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)
    return path


def _regular_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    return path.resolve(strict=True)


def _create_owner_file(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to replace existing evidence: {path.name}")
    _write_owner_file(path, payload, replace=False)


def _replace_owner_file(path: Path, payload: bytes) -> None:
    _write_owner_file(path, payload, replace=True)


def _write_owner_file(path: Path, payload: bytes, *, replace: bool) -> None:
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
        if not replace and path.exists():
            raise FileExistsError(f"refusing to replace existing evidence: {path.name}")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "REMIX_COMPARISON_REOPEN_SCHEMA",
    "REMIX_COMPARISON_REVIEW_SCHEMA",
    "REMIX_COMPARISON_SESSION_SCHEMA",
    "RemixComparisonHTTPServer",
    "create_remix_comparison_server",
    "run_remix_comparison_server",
]
