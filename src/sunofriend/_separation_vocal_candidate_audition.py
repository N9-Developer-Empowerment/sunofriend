"""Private loopback audition for sealed vocal MIDI candidate inventories.

This module deliberately has no public CLI, TUI, Simple, Studio or Workbench
route.  It resolves already-sealed audio artifacts only in memory, serves them
through a per-launch loopback capability and records no playback activity.
Only a browser-exported, explicitly completed review can be verified later.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _excerpt_document_sha256,
)
from ._separation_authorised_midi_comparison import (
    _artifact_path,
    _document_sha256,
    _regular_json,
    _sha256,
    _verify_artifacts,
    _write_json,
)
from ._separation_authorised_role_mapping import _safe_token
from ._separation_authorised_vocal_leaves import _require_private_inactive
from ._separation_vocal_candidate_set import (
    SCHEMA as CANDIDATE_SET_SCHEMA,
    _build_document as _build_candidate_set_document,
    _load_inputs as _load_candidate_inputs,
)
from ._separation_vocal_phrase_completeness import _REGISTER_HYPOTHESES


REVIEW_SCHEMA = "sunofriend.private-vocal-candidate-review.v1"
RESOLUTION_SCHEMA = "sunofriend.private-vocal-candidate-review-resolution.v1"
_MAX_MEDIA_BYTES = 64 * 1024 * 1024
_MAX_REVIEW_BYTES = 256 * 1024
_MAX_FOCUS_CHARACTERS = 180
_MAX_NOTE_CHARACTERS = 1_000
_DISPOSITIONS = frozenset(("useful_for_focus", "not_useful_for_focus", "cannot_tell"))


@dataclass(frozen=True)
class _VerifiedMedia:
    root: Path
    relative_path: str
    sha256: str
    size: int
    label: str


@dataclass(frozen=True)
class _AuditionContext:
    candidate_set_path: Path
    candidate_set_file_sha256: str
    candidate_set: Mapping[str, Any]
    excerpt_path: Path
    excerpt_file_sha256: str
    excerpt: Mapping[str, Any]
    focus: str
    seed: Mapping[str, Any]
    candidate_media: Mapping[
        str, tuple[_VerifiedMedia | None, _VerifiedMedia | None]
    ]


def _load_audition_context(
    candidate_set_path: str | Path,
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
    phrase_completeness_path: str | Path,
    excerpt_path: str | Path,
    *,
    focus: str,
) -> _AuditionContext:
    """Revalidate the complete sealed chain and resolve media in memory."""

    focus = _review_focus(focus)
    inventory_path = _regular_json(candidate_set_path, "vocal candidate set")
    if inventory_path.stat().st_size > _MAX_REVIEW_BYTES:
        raise ValueError("vocal candidate set is too large")
    inventory_file_sha256 = _sha256(inventory_path)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if (
        not isinstance(inventory, dict)
        or inventory.get("schema") != CANDIDATE_SET_SCHEMA
        or inventory.get("document_sha256") != _document_sha256(inventory)
    ):
        raise ValueError("vocal candidate set differs")
    _require_private_inactive(inventory, "vocal candidate set")

    inputs = _load_candidate_inputs(
        melroformer_evaluation_path,
        vocal_leaf_evaluation_path,
        phrase_completeness_path,
    )
    expected_inventory = _build_candidate_set_document(inputs)
    expected_inventory["document_sha256"] = _document_sha256(expected_inventory)
    if inventory != expected_inventory:
        raise ValueError("vocal candidate set is not the exact sealed inventory")

    source_path = _regular_json(excerpt_path, "authorised source excerpt")
    if source_path.stat().st_size > _MAX_REVIEW_BYTES * 8:
        raise ValueError("authorised source excerpt report is too large")
    source_file_sha256 = _sha256(source_path)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if (
        not isinstance(source, dict)
        or source.get("schema") != AUTHORISED_EXCERPT_SCHEMA
        or source.get("document_sha256") != _excerpt_document_sha256(source)
    ):
        raise ValueError("authorised source excerpt differs")
    _require_private_inactive(source, "authorised source excerpt")
    _verify_artifacts(source_path.parent, source.get("artifacts"))
    leaf_inputs = inputs["leaf"].get("inputs", {})
    if (
        leaf_inputs.get("excerpt_sha256") != source_file_sha256
        or leaf_inputs.get("excerpt_document_sha256") != source.get("document_sha256")
    ):
        raise ValueError("authorised source excerpt is not bound to vocal leaves")

    candidate_media = _resolve_candidate_media(inputs, source_path.parent, source)
    _require_exact_candidate_media(inventory, candidate_media)
    seed = _review_seed(
        inventory,
        candidate_set_file_sha256=inventory_file_sha256,
        excerpt=source,
        excerpt_file_sha256=source_file_sha256,
        focus=focus,
        candidate_media=candidate_media,
    )
    _reverify_audition_inputs(
        inventory_path=inventory_path,
        inventory_sha256=inventory_file_sha256,
        inputs=inputs,
        excerpt_path=source_path,
        excerpt_sha256=source_file_sha256,
    )
    return _AuditionContext(
        candidate_set_path=inventory_path,
        candidate_set_file_sha256=inventory_file_sha256,
        candidate_set=inventory,
        excerpt_path=source_path,
        excerpt_file_sha256=source_file_sha256,
        excerpt=source,
        focus=focus,
        seed=seed,
        candidate_media=candidate_media,
    )


def _resolve_candidate_media(
    inputs: Mapping[str, Any], excerpt_root: Path, excerpt: Mapping[str, Any]
) -> dict[str, tuple[_VerifiedMedia | None, _VerifiedMedia | None]]:
    original = _media_from_artifact(
        excerpt_root,
        excerpt.get("original", {}).get("excerpt"),
        "original mixed source excerpt",
    )
    result: dict[str, tuple[_VerifiedMedia | None, _VerifiedMedia | None]] = {}

    mel = inputs["melroformer"]
    mel_root = inputs["melroformer_root"]
    raw = mel.get("candidate", {})
    result["kim/primary"] = (
        _media_from_artifact(
            mel_root, raw.get("primary", {}).get("render"), "Kim primary preview"
        ),
        original,
    )
    variants = raw.get("register_hypotheses", {}).get("variants", {})
    for variant in sorted(_REGISTER_HYPOTHESES):
        candidate = variants.get(variant, {}).get("candidate", {})
        candidate_id = f"kim/register/{_safe_token(variant)}"
        preview = (
            _media_from_artifact(
                mel_root,
                candidate.get("render"),
                f"Kim {variant} preview",
            )
            if candidate.get("render") is not None
            else None
        )
        if preview is not None:
            result[candidate_id] = (preview, original)
        else:
            result[candidate_id] = (None, None)

    leaf_document = inputs["leaf"]
    leaf_root = inputs["leaf_root"]
    leaves = leaf_document.get("leaves", {})
    for provider_id, provider_leaves in sorted(leaves.items()):
        for leaf_id, leaf in sorted(provider_leaves.items()):
            source_reference = _media_from_artifact(
                excerpt_root,
                leaf.get("source_excerpt"),
                f"{provider_id} {leaf_id} vocal source reference",
            )
            for adapter_id, adapter in sorted(leaf.get("adapters", {}).items()):
                variant = adapter.get("primary_variant")
                candidate = adapter.get("variants", {}).get(variant, {}).get("candidate", {})
                candidate_id = (
                    f"provider/{_safe_token(provider_id)}/{_safe_token(leaf_id)}/"
                    f"{_safe_token(adapter_id)}/{_safe_token(str(variant))}"
                )
                preview = (
                    _media_from_artifact(
                        leaf_root,
                        candidate.get("render"),
                        f"{candidate_id} preview",
                    )
                    if candidate.get("render") is not None
                    else None
                )
                if preview is not None:
                    result[candidate_id] = (preview, source_reference)
                else:
                    result[candidate_id] = (None, None)
    return result


def _media_from_artifact(root: Path, raw: Any, label: str) -> _VerifiedMedia:
    path = _artifact_path(root, raw, label)
    assert isinstance(raw, Mapping)
    size = raw.get("bytes")
    sha256 = raw.get("sha256")
    relative = raw.get("path")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= _MAX_MEDIA_BYTES
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or not isinstance(relative, str)
    ):
        raise ValueError(f"{label} media identity differs")
    path.relative_to(root.resolve(strict=True))
    return _VerifiedMedia(
        root=root.resolve(strict=True),
        relative_path=relative,
        sha256=sha256,
        size=size,
        label=label,
    )


def _require_exact_candidate_media(
    inventory: Mapping[str, Any],
    media: Mapping[str, tuple[_VerifiedMedia | None, _VerifiedMedia | None]],
) -> None:
    candidates = inventory.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("vocal candidate inventory is empty")
    expected_ids = {str(candidate.get("candidate_id", "")) for candidate in candidates}
    if expected_ids != set(media):
        raise ValueError("vocal candidate media membership differs")
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        preview, reference = media[candidate_id]
        expected = candidate.get("artifacts", {}).get("render")
        if candidate.get("audition_state") == "available":
            if preview is None or reference is None or not isinstance(expected, Mapping):
                raise ValueError("auditionable vocal candidate media differs")
            if expected != {"sha256": preview.sha256, "bytes": preview.size}:
                raise ValueError("vocal candidate preview identity differs")
        else:
            if reference is not None or expected is not None:
                raise ValueError("zero-note vocal candidate media differs")


def _review_seed(
    inventory: Mapping[str, Any],
    *,
    candidate_set_file_sha256: str,
    excerpt: Mapping[str, Any],
    excerpt_file_sha256: str,
    focus: str,
    candidate_media: Mapping[
        str, tuple[_VerifiedMedia | None, _VerifiedMedia | None]
    ],
) -> dict[str, Any]:
    choices = []
    for candidate in inventory["candidates"]:
        candidate_id = candidate["candidate_id"]
        preview, reference = candidate_media[candidate_id]
        available = candidate["audition_state"] == "available"
        if available and (preview is None or reference is None):
            raise ValueError("auditionable vocal candidate media differs")
        choices.append(
            {
                "candidate_id": candidate_id,
                "family": candidate["family"],
                "provider_group": candidate.get("provider_group"),
                "leaf_id": candidate.get("leaf_id"),
                "adapter": candidate.get("adapter"),
                "variant": candidate["variant"],
                "note_count": candidate["note_count"],
                "audition_state": candidate["audition_state"],
                "candidate_render": (
                    {"sha256": preview.sha256, "bytes": preview.size}
                    if available
                    else None
                ),
                "source_reference": (
                    {
                        "kind": (
                            "provider_vocal_leaf"
                            if candidate["family"] == "provider_leaf"
                            else "original_mixed_excerpt"
                        ),
                        "sha256": reference.sha256,
                        "bytes": reference.size,
                    }
                    if reference is not None
                    else None
                ),
                "heard_reference": False,
                "heard_candidate": False,
                "disposition": "unavailable" if not available else "",
                "notes": "",
            }
        )
    seed = {
        "schema": REVIEW_SCHEMA,
        "status": "unreviewed",
        "reviewed_at": None,
        "evidence_scope": "private_development_only",
        "inputs": {
            "candidate_set_sha256": candidate_set_file_sha256,
            "candidate_set_document_sha256": inventory["document_sha256"],
            "authorised_excerpt_sha256": excerpt_file_sha256,
            "authorised_excerpt_document_sha256": excerpt["document_sha256"],
        },
        "focus": focus,
        "policy": {
            "ordering_has_rank_semantics": False,
            "playback_is_feedback": False,
            "multiple_useful_candidates_allowed": True,
            "winner_required": False,
            "automatic_selection": False,
            "automatic_merge": False,
            "automatic_repair": False,
            "singer_identity_inferred": False,
            "audio_or_midi_copied": False,
            "server_side_review_write": False,
        },
        "summary": dict(inventory["summary"]),
        "choices": choices,
        "effects": {
            "audio_created": False,
            "candidate_selected": False,
            "midi_created_or_mutated": False,
            "review_recorded_by_playback": False,
            "source_graph_mutated": False,
            "studio_or_simple_route_enabled": False,
        },
    }
    seed["document_sha256"] = _document_sha256(seed)
    return seed


def _review_focus(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ValueError("review focus must be text")
    value = raw.strip()
    if not value or len(value) > _MAX_FOCUS_CHARACTERS or "\x00" in value:
        raise ValueError("review focus must contain 1-180 safe characters")
    if "\n" in value or "\r" in value:
        raise ValueError("review focus must stay on one line")
    return value


def _verify_review_document(
    seed: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    if review.get("schema") != REVIEW_SCHEMA or review.get("status") != "reviewed":
        raise ValueError("vocal candidate review is not complete")
    reviewed_at = review.get("reviewed_at")
    if not isinstance(reviewed_at, str) or len(reviewed_at) > 64:
        raise ValueError("vocal candidate review timestamp differs")
    try:
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("vocal candidate review timestamp differs") from error
    if timestamp.tzinfo is None:
        raise ValueError("vocal candidate review timestamp must include a timezone")

    rows = review.get("choices")
    seed_rows = seed.get("choices")
    if not isinstance(rows, list) or not isinstance(seed_rows, list):
        raise ValueError("vocal candidate review choices differ")
    if len(rows) != len(seed_rows):
        raise ValueError("vocal candidate review membership differs")
    total_notes = 0
    useful: list[str] = []
    not_useful: list[str] = []
    cannot_tell: list[str] = []
    for expected, row in zip(seed_rows, rows):
        if not isinstance(row, Mapping):
            raise ValueError("vocal candidate review choice differs")
        candidate_id = expected["candidate_id"]
        if row.get("candidate_id") != candidate_id:
            raise ValueError("vocal candidate review order or identity differs")
        notes = row.get("notes")
        if not isinstance(notes, str) or len(notes) > _MAX_NOTE_CHARACTERS:
            raise ValueError("vocal candidate review notes differ")
        total_notes += len(notes)
        if expected["audition_state"] == "available":
            if row.get("heard_reference") is not True or row.get("heard_candidate") is not True:
                raise ValueError("every auditionable candidate must be heard with its reference")
            disposition = row.get("disposition")
            if disposition not in _DISPOSITIONS:
                raise ValueError("every auditionable candidate needs one disposition")
            if disposition == "useful_for_focus":
                useful.append(candidate_id)
            elif disposition == "not_useful_for_focus":
                not_useful.append(candidate_id)
            else:
                cannot_tell.append(candidate_id)
        elif (
            row.get("heard_reference") is not False
            or row.get("heard_candidate") is not False
            or row.get("disposition") != "unavailable"
            or notes
        ):
            raise ValueError("no-note candidate review state differs")
    if total_notes > 16_000:
        raise ValueError("vocal candidate review notes are too large")

    sanitized = json.loads(json.dumps(review))
    sanitized["status"] = "unreviewed"
    sanitized["reviewed_at"] = None
    for expected, row in zip(seed_rows, sanitized["choices"]):
        row["heard_reference"] = expected["heard_reference"]
        row["heard_candidate"] = expected["heard_candidate"]
        row["disposition"] = expected["disposition"]
        row["notes"] = expected["notes"]
    if sanitized != seed:
        raise ValueError("vocal candidate review changed immutable evidence")
    return {
        "useful_for_focus": useful,
        "not_useful_for_focus": not_useful,
        "cannot_tell": cannot_tell,
    }


def _resolve_vocal_candidate_review(
    review_path: str | Path,
    candidate_set_path: str | Path,
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
    phrase_completeness_path: str | Path,
    excerpt_path: str | Path,
    *,
    focus: str,
    out: str | Path,
) -> dict[str, Any]:
    context = _load_audition_context(
        candidate_set_path,
        melroformer_evaluation_path,
        vocal_leaf_evaluation_path,
        phrase_completeness_path,
        excerpt_path,
        focus=focus,
    )
    path = _regular_json(review_path, "reviewed vocal candidate export")
    if path.stat().st_size > _MAX_REVIEW_BYTES:
        raise ValueError("reviewed vocal candidate export is too large")
    review_file_sha256 = _sha256(path)
    review = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(review, Mapping):
        raise ValueError("reviewed vocal candidate export differs")
    results = _verify_review_document(context.seed, review)
    resolution = {
        "schema": RESOLUTION_SCHEMA,
        "status": "complete_review_no_activation",
        "evidence_scope": "private_development_only",
        "inputs": {
            "review_sha256": review_file_sha256,
            "review_seed_document_sha256": context.seed["document_sha256"],
            "candidate_set_sha256": context.candidate_set_file_sha256,
            "candidate_set_document_sha256": context.candidate_set["document_sha256"],
            "authorised_excerpt_sha256": context.excerpt_file_sha256,
            "authorised_excerpt_document_sha256": context.excerpt["document_sha256"],
        },
        "focus": context.focus,
        "results": {
            "useful_for_focus_count": len(results["useful_for_focus"]),
            "useful_for_focus": results["useful_for_focus"],
            "not_useful_for_focus_count": len(results["not_useful_for_focus"]),
            "not_useful_for_focus": results["not_useful_for_focus"],
            "cannot_tell_count": len(results["cannot_tell"]),
            "cannot_tell": results["cannot_tell"],
        },
        "policy": {
            "human_dispositions_verified": True,
            "multiple_useful_candidates_allowed": True,
            "winner_selected": False,
            "automatic_selection": False,
            "automatic_merge": False,
            "automatic_repair": False,
            "singer_identity_inferred": False,
            "production_eligible": False,
        },
        "effects": {
            "audio_created": False,
            "candidate_selected": False,
            "default_changed": False,
            "midi_created_or_mutated": False,
            "source_graph_mutated": False,
            "studio_or_simple_route_enabled": False,
        },
        "limitations": [
            "Useful means useful for the exact written listening focus, not ground truth, accuracy or singer identity.",
            "The review keeps multiple useful candidates and does not choose, merge, repair, promote or activate any of them.",
            "Candidate MIDI renders use one neutral proxy sound and do not evaluate final GarageBand instrumentation.",
        ],
    }
    resolution["document_sha256"] = _document_sha256(resolution)
    _reverify_context(context)
    _write_fresh_private_json(Path(out), resolution)
    resolution["report"] = str(Path(out).expanduser().absolute())
    return resolution


def _write_fresh_private_json(destination: Path, document: Mapping[str, Any]) -> None:
    destination = destination.expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"review resolution already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        staged = temporary / destination.name
        _write_json(staged, document)
        staged.chmod(0o600)
        if os.path.lexists(destination):
            raise FileExistsError("review resolution appeared during publication")
        os.rename(staged, destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


class _VocalCandidateAuditionServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, context: _AuditionContext, *, port: int = 0) -> None:
        self.context = context
        self.token = secrets.token_urlsafe(32)
        self.media: dict[str, _VerifiedMedia] = {}
        self.candidate_urls: dict[str, dict[str, str | None]] = {}
        identity_to_id: dict[tuple[str, int], str] = {}
        for candidate_id, (preview, reference) in context.candidate_media.items():
            urls: dict[str, str | None] = {"candidate": None, "reference": None}
            if preview is not None and reference is not None:
                urls["candidate"] = self._register_media(preview, identity_to_id)
                urls["reference"] = self._register_media(reference, identity_to_id)
            self.candidate_urls[candidate_id] = urls
        super().__init__(("127.0.0.1", int(port)), _VocalCandidateAuditionHandler)

    def _register_media(
        self,
        media: _VerifiedMedia,
        identities: dict[tuple[str, int], str],
    ) -> str:
        key = (media.sha256, media.size)
        media_id = identities.get(key)
        if media_id is None:
            media_id = secrets.token_urlsafe(18)
            identities[key] = media_id
            self.media[media_id] = media
        return f"/media/{media_id}?token={self.token}"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/?token={self.token}"


class _VocalCandidateAuditionHandler(BaseHTTPRequestHandler):
    server: _VocalCandidateAuditionServer

    def do_GET(self) -> None:  # noqa: N802
        self._serve(head=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(head=True)

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _serve(self, *, head: bool) -> None:
        if not self._local_request():
            return
        parsed = urlparse(self.path)
        if not self._authorised(parsed.query):
            self._error(HTTPStatus.FORBIDDEN, "invalid private audition token")
            return
        if parsed.path == "/":
            body = _audition_html(self.server.context, self.server.candidate_urls)
            self._bytes(
                HTTPStatus.OK,
                body,
                "text/html; charset=utf-8",
                head=head,
                content_security_policy=True,
            )
            return
        prefix = "/media/"
        if parsed.path.startswith(prefix):
            media_id = parsed.path[len(prefix) :]
            media = self.server.media.get(media_id)
            if media is None:
                self._error(HTTPStatus.NOT_FOUND, "private audition media not found")
                return
            try:
                descriptor = _open_verified_media(media)
            except (OSError, ValueError):
                self._error(
                    HTTPStatus.CONFLICT,
                    "private audition evidence changed; restart the audition",
                )
                return
            try:
                self._audio(descriptor, media.size, head=head)
            finally:
                os.close(descriptor)
            return
        self._error(HTTPStatus.NOT_FOUND, "private audition route not found")

    def _authorised(self, query: str) -> bool:
        supplied = parse_qs(query).get("token", [""])[0]
        return hmac.compare_digest(supplied, self.server.token)

    def _local_request(self) -> bool:
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"}:
            self._error(HTTPStatus.FORBIDDEN, "private audition is loopback only")
            return False
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._error(HTTPStatus.FORBIDDEN, "private audition is loopback only")
            return False
        return True

    def _audio(self, descriptor: int, size: int, *, head: bool) -> None:
        start, end = 0, size - 1
        status = HTTPStatus.OK
        raw_range = self.headers.get("Range")
        if raw_range:
            parsed = _single_byte_range(raw_range, size)
            if parsed is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self._common_headers()
                self.end_headers()
                return
            start, end = parsed
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self._common_headers()
        self.end_headers()
        if head:
            return
        os.lseek(descriptor, start, os.SEEK_SET)
        remaining = length
        try:
            while remaining:
                block = os.read(descriptor, min(128 * 1024, remaining))
                if not block:
                    raise OSError("audition media ended early")
                self.wfile.write(block)
                remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        head: bool,
        content_security_policy: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if content_security_policy:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; media-src 'self'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
            )
        self._common_headers()
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _method_not_allowed(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self._common_headers()
        self.end_headers()

    def _error(self, status: HTTPStatus, message: str) -> None:
        body = (message + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._common_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")


def _open_verified_media(media: _VerifiedMedia) -> int:
    parts = PurePosixPath(media.relative_path).parts
    if (
        not parts
        or PurePosixPath(media.relative_path).is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("private audition media path differs")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(media.root, directory_flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(parts[-1], file_flags, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    try:
        details = os.fstat(file_descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size != media.size:
            raise ValueError("private audition media geometry differs")
        digest = hashlib.sha256()
        while True:
            block = os.read(file_descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        if digest.hexdigest() != media.sha256:
            raise ValueError("private audition media hash differs")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        return file_descriptor
    except BaseException:
        os.close(file_descriptor)
        raise


def _single_byte_range(raw: str, size: int) -> tuple[int, int] | None:
    if not raw.startswith("bytes=") or "," in raw:
        return None
    value = raw[6:].strip()
    if "-" not in value:
        return None
    first, last = value.split("-", 1)
    try:
        if not first:
            suffix = int(last)
            if suffix <= 0:
                return None
            start = max(0, size - suffix)
            return start, size - 1
        start = int(first)
        end = size - 1 if not last else int(last)
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


def _audition_html(
    context: _AuditionContext, candidate_urls: Mapping[str, Mapping[str, str | None]]
) -> bytes:
    payload = {
        "seed": context.seed,
        "urls": candidate_urls,
        "dispositions": [
            {"value": "", "label": "Choose after listening…"},
            {"value": "useful_for_focus", "label": "Useful for this focus"},
            {"value": "not_useful_for_focus", "label": "Not useful for this focus"},
            {"value": "cannot_tell", "label": "Cannot tell"},
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend private vocal candidate audition</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#071018;color:#ecf6ff}body{margin:0}.local{padding:12px 24px;background:#123d2b;color:#baffd1;font-weight:700}.wrap{max-width:1100px;margin:auto;padding:28px}.hero,.transport,.card{background:#111e2a;border:1px solid #2b4052;border-radius:14px;padding:20px;margin-bottom:16px}.warning{border-left:4px solid #ffbf3f;padding:10px 14px;background:#332a13}.muted{color:#9fb2c2}.focus{color:#75dcff;font-size:1.12rem}.transport{position:sticky;top:0;z-index:3}audio{width:100%;margin:10px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.card h3{margin-top:0}.meta{font-family:ui-monospace,monospace;color:#a8c5d8}.actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center}button,select,textarea{font:inherit}button,select{padding:9px 12px;border-radius:8px;border:1px solid #4a718e;background:#17344a;color:#fff}button.primary{background:#0b6b7d}button:disabled{opacity:.45}textarea{box-sizing:border-box;width:100%;margin-top:8px;border-radius:8px;background:#0b1620;color:#fff;border:1px solid #3b5367;padding:9px}.unavailable{opacity:.65}.status{font-weight:700;color:#ffca53}.complete{color:#76f0a9}@media(max-width:760px){.grid{grid-template-columns:1fr}.wrap{padding:16px}}
</style></head><body><div class="local">● Private local developer audition — no audio or review is uploaded</div><main class="wrap"><section class="hero"><h1>Vocal MIDI candidate audition</h1><p class="focus" id="focus"></p><p>This page preserves every sealed hypothesis. It does not rank candidates, infer a singer, or require one winner. More than one candidate may be useful.</p><p class="warning"><strong>What you hear:</strong> the reference is the original mixed excerpt for Kim candidates and the exact provider vocal leaf for provider candidates. The candidate is a dry neutral MIDI render. Tone is only a proxy; judge whether the notes and phrase follow the written focus.</p><p class="muted">The order below is canonical serialization only, not a recommendation. Zero-note evidence remains visible but cannot be reviewed as audio.</p></section><section class="transport"><strong id="now">Nothing loaded</strong><audio id="player" controls preload="metadata"></audio><label><input id="loop" type="checkbox"> Loop current audio</label><p class="muted">Playback, seeking, looping and dwell time stay in this tab and are not feedback.</p></section><div id="cards"></div><section class="hero"><p id="status" class="status">Unreviewed</p><div class="actions"><button id="complete" class="primary">Mark explicit review complete</button><button id="export" disabled>Export reviewed JSON</button></div><p class="muted">Completion requires both heard boxes and one disposition for every playable candidate. Export is a browser download; the local server writes nothing.</p></section></main><script>
const payload=__PAYLOAD__;const seed=structuredClone(payload.seed);let review=structuredClone(seed);const player=document.getElementById('player');const root=document.getElementById('cards');const status=document.getElementById('status');const exportButton=document.getElementById('export');document.getElementById('focus').textContent='Listening focus: '+review.focus;player.onended=()=>{if(document.getElementById('loop').checked){player.currentTime=0;player.play()}};
function label(row){if(row.family==='kim_primary')return 'Kim separator primary';if(row.family==='kim_register')return 'Kim register hypothesis: '+row.variant.replaceAll('_',' ');return `${row.provider_group} · ${row.leaf_id} · ${row.adapter} adapter · ${row.variant.replaceAll('_',' ')}`}
function play(url,title){const t=Number.isFinite(player.currentTime)?player.currentTime:0;player.pause();player.src=url;document.getElementById('now').textContent=title;const start=()=>{const end=Number.isFinite(player.duration)?Math.max(0,player.duration-0.01):t;try{player.currentTime=Math.min(t,end)}catch(_){}player.play().catch(()=>{})};if(player.readyState>=1){start()}else{player.addEventListener('loadedmetadata',start,{once:true})}}
function invalidate(){review.status='unreviewed';review.reviewed_at=null;status.className='status';status.textContent=`Unreviewed · ${completedCount()} of ${review.summary.audition_available_count} candidates complete`;exportButton.disabled=true}
function completedCount(){return review.choices.filter(x=>x.audition_state==='available'&&x.heard_reference&&x.heard_candidate&&x.disposition).length}
function render(){root.innerHTML='';review.choices.forEach((row,index)=>{const card=document.createElement('section');card.className='card '+(row.audition_state==='available'?'':'unavailable');const title=document.createElement('h3');title.textContent=label(row);card.appendChild(title);const meta=document.createElement('p');meta.className='meta';meta.textContent=`${row.note_count} MIDI notes · ${row.audition_state.replaceAll('_',' ')}`;card.appendChild(meta);if(row.audition_state!=='available'){const p=document.createElement('p');p.textContent='No note evidence: retained as a diagnostic, with no audio choice required.';card.appendChild(p);root.appendChild(card);return}const actions=document.createElement('div');actions.className='actions';const ref=document.createElement('button');ref.textContent=row.source_reference.kind==='provider_vocal_leaf'?'Play source vocal leaf':'Play mixed source excerpt';ref.onclick=()=>play(payload.urls[row.candidate_id].reference,ref.textContent+' — '+label(row));const candidate=document.createElement('button');candidate.textContent='Play candidate MIDI';candidate.onclick=()=>play(payload.urls[row.candidate_id].candidate,candidate.textContent+' — '+label(row));actions.append(ref,candidate);card.appendChild(actions);const checks=document.createElement('div');checks.className='actions';['heard_reference','heard_candidate'].forEach((key)=>{const lab=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.checked=row[key];input.onchange=()=>{row[key]=input.checked;invalidate()};lab.append(input,document.createTextNode(key==='heard_reference'?' I heard the reference':' I heard the candidate'));checks.appendChild(lab)});const select=document.createElement('select');payload.dispositions.forEach(option=>{const node=document.createElement('option');node.value=option.value;node.textContent=option.label;select.appendChild(node)});select.value=row.disposition;select.onchange=()=>{row.disposition=select.value;invalidate()};checks.appendChild(select);card.appendChild(checks);const notes=document.createElement('textarea');notes.maxLength=1000;notes.rows=2;notes.placeholder='Optional private notes about melody, register, timing or role';notes.value=row.notes;notes.oninput=()=>{row.notes=notes.value;invalidate()};card.appendChild(notes);root.appendChild(card)});invalidate()}
document.getElementById('complete').onclick=()=>{const complete=review.choices.filter(x=>x.audition_state==='available').every(x=>x.heard_reference&&x.heard_candidate&&x.disposition);if(!complete){alert('Hear the reference and candidate, then choose a disposition for every playable candidate.');return}review.status='reviewed';review.reviewed_at=new Date().toISOString();status.className='status complete';status.textContent='Explicit review complete · ready to export';exportButton.disabled=false};
exportButton.onclick=()=>{if(review.status!=='reviewed'){return}const blob=new Blob([JSON.stringify(review,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='vocal_candidate_review.reviewed.json';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)};render();
</script></body></html>""".replace("__PAYLOAD__", encoded)
    return html.encode("utf-8")


def _reverify_audition_inputs(
    *,
    inventory_path: Path,
    inventory_sha256: str,
    inputs: Mapping[str, Any],
    excerpt_path: Path,
    excerpt_sha256: str,
) -> None:
    if _sha256(inventory_path) != inventory_sha256:
        raise ValueError("vocal candidate set changed during audition preparation")
    if _sha256(excerpt_path) != excerpt_sha256:
        raise ValueError("authorised source excerpt changed during audition preparation")
    for label in ("melroformer", "leaf", "phrase"):
        if _sha256(inputs[f"{label}_path"]) != inputs[f"{label}_sha256"]:
            raise ValueError(f"{label} evidence changed during audition preparation")
        artifacts = inputs[label].get("artifacts")
        if artifacts is not None:
            _verify_artifacts(inputs[f"{label}_root"], artifacts)


def _reverify_context(context: _AuditionContext) -> None:
    if _sha256(context.candidate_set_path) != context.candidate_set_file_sha256:
        raise ValueError("vocal candidate set changed during review verification")
    if _sha256(context.excerpt_path) != context.excerpt_file_sha256:
        raise ValueError("authorised source excerpt changed during review verification")
    seen: set[tuple[str, int]] = set()
    for preview, reference in context.candidate_media.values():
        for media in (preview, reference):
            if media is None or (media.sha256, media.size) in seen:
                continue
            seen.add((media.sha256, media.size))
            descriptor = _open_verified_media(media)
            os.close(descriptor)


__all__: Sequence[str] = ()
