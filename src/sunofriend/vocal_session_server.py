"""Private loopback browser for one path-free Vocal Session projection."""

from __future__ import annotations

import base64
import binascii
from contextlib import closing
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import secrets
import struct
import tempfile
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from .musical_state import admit_vocal_phrase_capture, validate_musical_state
from .separation_review_transport import parse_file_range
from .source_receipt import canonical_json_bytes
from .vocal_capture import create_vocal_capture
from .vocal_candidate_vault import (
    VocalCandidateVault,
    VocalCandidateVaultConflictError,
)
from .vocal_phrase_decision import create_phrase_decision
from .vocal_session import (
    VocalSessionDraftConflictError,
    VocalSessionStore,
    build_vocal_session,
    build_vocal_session_transition_request,
    create_vocal_session_transition,
)
from .vocal_working_audition import create_vocal_working_audition


_MAXIMUM_JSON_REQUEST_BYTES = 64 * 1024
_MAXIMUM_CAPTURE_REQUEST_BYTES = 10 * 1024 * 1024
_CAPTURE_GUARD_SECONDS = 0.5
_REQUESTED_MICROPHONE_PROCESSING = {
    "echo_cancellation": False,
    "noise_suppression": False,
    "automatic_gain_control": False,
}


class VocalSessionCaptureConflictError(RuntimeError):
    """Raised when a new state would strand an existing musical decision."""


class VocalSessionRequestTooLargeError(ValueError):
    """Raised before reading an over-limit browser request body."""


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
        recording_cue_source_id: str | None,
        capture_output_dir: str | Path | None,
        candidate_vault_dir: str | Path | None,
    ) -> None:
        state_path = Path(musical_state_path).expanduser().resolve(strict=True)
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("musical state must be readable JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("musical state must be a JSON object")
        self.musical_state_path = state_path
        self.musical_state = validate_musical_state(value)
        self.musical_state_root = state_path.parent
        self.store = VocalSessionStore(state_dir)
        self.title = str(title).strip() or "Vocal comp session"
        self.token = token
        capture_path, candidate_vault_path, recording_target = _recording_paths(
            capture_output_dir, candidate_vault_dir, self.musical_state_root
        )
        if (recording_cue_source_id is None) != (recording_target is None):
            raise ValueError(
                "recording cue and one capture destination must be supplied together"
            )
        self.recording_cue_source_id = recording_cue_source_id
        self.capture_output_dir = capture_path
        self.candidate_vault = _open_candidate_vault(candidate_vault_path)
        if recording_target is not None:
            self._recording_reference()
        self._refresh_media()
        super().__init__(address, _VocalSessionHandler)

    def _refresh_media(self) -> None:
        self.media = _authorised_media(self.musical_state, self.musical_state_root)
        self.media.update(self._candidate_media())
        self.media_capabilities = {
            secrets.token_urlsafe(24): record for record in self.media.values()
        }
        self.media_capability_by_source = {
            record["source_id"]: capability
            for capability, record in self.media_capabilities.items()
        }

    def _candidate_media(self) -> dict[str, dict[str, Any]]:
        if self.candidate_vault is None:
            return {}
        records = {
            record["source_id"]: record
            for record in self.candidate_vault.media_records(self.musical_state)
        }
        if set(records) & set(self.media):
            raise ValueError("candidate source identity conflicts with admitted audio")
        return records

    def _recording_reference(self) -> Mapping[str, Any]:
        reference = self.musical_state["vocal_performance_state"].get("reference")
        if (
            not isinstance(reference, Mapping)
            or reference.get("source_id") != self.recording_cue_source_id
            or reference.get("source_class") != "reference_vocal"
        ):
            raise ValueError(
                "recording cue must be the exact authorised reference vocal in the Musical State"
            )
        return reference

    def admit_capture(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Validate, admit and switch to one fresh derived Musical State."""

        if self.capture_output_dir is None or self.recording_cue_source_id is None:
            raise ValueError("vocal session recording is not configured")
        prepared = self._prepare_capture(request, require_transition=True)
        session = prepared["session"]
        phrase_id = prepared["phrase_id"]
        capture_id = prepared["capture_id"]
        wav_bytes = prepared["wav_bytes"]
        receipt = prepared["receipt"]
        transition_request = prepared["transition_request"]
        parent_decisions = prepared["parent_decisions"]
        child = self.capture_output_dir / (
            f"capture-{capture_id}-{receipt['document_sha256'][:12]}"
        )
        self.capture_output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.capture_output_dir, 0o700)
        with tempfile.TemporaryDirectory(
            prefix=".vocal-capture-", dir=self.capture_output_dir
        ) as temporary_name:
            temporary = Path(temporary_name)
            os.chmod(temporary, 0o700)
            wav_path = temporary / "capture.wav"
            receipt_path = temporary / "capture-receipt.json"
            _write_private_bytes(wav_path, wav_bytes)
            _write_private_bytes(receipt_path, canonical_json_bytes(receipt))
            admitted = admit_vocal_phrase_capture(
                self.musical_state_path,
                capture_wav=wav_path,
                capture_receipt=receipt_path,
                out_dir=child,
                label=f"Recorded attempt for {phrase_id}",
            )
        previous_session = session
        next_session = build_vocal_session(admitted)
        transition = None
        if transition_request is not None:
            transition, revalidated = create_vocal_session_transition(
                self.musical_state,
                admitted,
                parent_decisions,
                transition_request,
            )
            self.store.apply_transition(
                previous_session, next_session, transition, revalidated
            )
            next_session = self.store.current_session(admitted)
        self.musical_state_path = child / "musical-state.json"
        self.musical_state_root = child
        self.musical_state = admitted
        self._recording_reference()
        self._refresh_media()
        self.store.rebind_non_authoritative_draft(previous_session, next_session)
        result = {
            "admission": {
                "parent_musical_state_sha256": previous_session["binding"][
                    "musical_state_sha256"
                ],
                "phrase_id": phrase_id,
                "source_id": receipt["capture"]["source_id"],
                "capture_document_sha256": receipt["document_sha256"],
                "musical_state_sha256": admitted["document_sha256"],
            },
            "state": self.browser_state(),
        }
        if transition is not None:
            result["transition"] = transition
        return result

    def keep_candidate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Keep one provisional source without changing the Musical State."""

        if self.candidate_vault is None or self.recording_cue_source_id is None:
            raise ValueError("vocal candidate vault recording is not configured")
        prepared = self._prepare_capture(request, require_transition=False)
        candidate = self.candidate_vault.keep(
            self.musical_state,
            capture_receipt=prepared["receipt"],
            wav_bytes=prepared["wav_bytes"],
            label=f"Recorded attempt for {prepared['phrase_id']}",
        )
        self._refresh_media()
        return {"candidate": candidate, "state": self.browser_state()}

    def _prepare_capture(
        self, request: Mapping[str, Any], *, require_transition: bool
    ) -> dict[str, Any]:
        session = self.store.current_session(self.musical_state)
        has_decisions = bool(session["coverage"]["decision_count"])
        allowed = _capture_request_fields()
        if require_transition and has_decisions:
            allowed.add("transition")
        if set(request) != allowed:
            if require_transition and has_decisions and "transition" not in request:
                raise VocalSessionCaptureConflictError(
                    "an explicit state transition is required after phrase decisions"
                )
            raise ValueError("vocal capture request fields changed")
        phrase_id = _text(request.get("phrase_id"), "phrase_id", 128)
        if (
            request.get("expected_musical_state_sha256")
            != self.musical_state["document_sha256"]
        ):
            raise ValueError("vocal capture Musical State identity changed")
        phrase = next(
            (
                row
                for row in self.musical_state["structure"]["phrases"]
                if row["phrase_id"] == phrase_id
            ),
            None,
        )
        if phrase is None:
            raise ValueError("vocal capture phrase is unknown")
        transition_request: Mapping[str, Any] | None = None
        parent_decisions = self.store.current_decisions(self.musical_state)
        if require_transition and has_decisions:
            transition_request = _mapping(request.get("transition"), "transition")
            expected_transition = build_vocal_session_transition_request(
                session, phrase_id
            )
            if dict(transition_request) != expected_transition:
                raise VocalSessionCaptureConflictError(
                    "the explicit state transition does not match the exact current decisions"
                )
        capture_id = _text(request.get("capture_id"), "capture_id", 128)
        wav_bytes = _decode_capture_wav(request.get("audio_wav_base64"))
        geometry = _pcm24_wav_geometry(wav_bytes)
        placement = _validated_capture_placement(
            request.get("placement"), phrase=phrase, geometry=geometry
        )
        reference = self._recording_reference()
        if (
            request.get("cue_id") != reference["source_id"]
            or request.get("cue_asset_sha256") != reference["audio"]["sha256"]
        ):
            raise ValueError("vocal capture cue identity changed")
        receipt = create_vocal_capture(
            self.musical_state,
            capture_id=capture_id,
            phrase_id=phrase_id,
            cue_id=str(reference["source_id"]),
            cue_asset_sha256=str(reference["audio"]["sha256"]),
            audio_sha256=hashlib.sha256(wav_bytes).hexdigest(),
            audio_bytes=len(wav_bytes),
            sample_rate=geometry["sample_rate"],
            frame_count=geometry["frames"],
            phrase_start_frame=placement["source_phrase_start_frame"],
            phrase_end_frame=placement["source_phrase_end_frame"],
            destination_start_seconds=float(phrase["start_seconds"]),
            destination_end_seconds=float(phrase["end_seconds"]),
            pre_guard_frames=placement["pre_guard_frames"],
            post_guard_frames=placement["post_guard_frames"],
            requested_processing=_REQUESTED_MICROPHONE_PROCESSING,
            actual_processing=_mapping(
                request.get("actual_processing"), "actual_processing"
            ),
        )
        return {
            "session": session,
            "phrase_id": phrase_id,
            "capture_id": capture_id,
            "wav_bytes": wav_bytes,
            "receipt": receipt,
            "transition_request": transition_request,
            "parent_decisions": parent_decisions,
        }

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
        candidate_sources, candidate_state = self._candidate_browser_state()
        sources.extend(candidate_sources)
        return {
            "title": self.title,
            "session": session,
            "draft": draft,
            "sources": sources,
            "candidate_vault": candidate_state,
            "recording": {
                **self._recording_state(session),
            },
            "context_playback": {
                "scopes": ["phrase", "section", "song"],
                "default_scope": "phrase",
                "section_phrase_radius": 2,
                "original_source_id": next(
                    (
                        row["source_id"]
                        for row in sources
                        if row["source_class"] == "authorised_ai_vocal_reference"
                    ),
                    None,
                ),
                "song_start_seconds": 0.0,
                "song_end_seconds": max(
                    (float(row["end_seconds"]) for row in session["phrases"]),
                    default=0.0,
                ),
                "authority": "audition_only",
                "playback_creates_decision": False,
                "artifact_created": False,
            },
            # A reference-vocal cue authorises audition and guided recording only.
            # AI fallback needs its own later, explicit render-use authorisation.
            "ai_fallback_available": False,
            "privacy": {
                "local_only": True,
                "uploads_available": False,
                "playback_creates_decision": False,
            },
        }

    def _candidate_browser_state(
        self,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if self.candidate_vault is None:
            return [], {
                "available": False,
                "entries": [],
                "working_choices": None,
                "authority": "none",
            }
        projections = [
            self._candidate_browser_projection(candidate)
            for candidate in self.candidate_vault.entries(self.musical_state)
        ]
        return projections, {
            "available": True,
            "entries": projections,
            "working_choices": self.candidate_vault.load_working_choices(
                self.musical_state
            ),
            "keep_url": "/api/candidate",
            "working_choices_url": "/api/working-choices",
            "working_audition_url": "/api/working-audition",
            "authority": "none",
        }

    def working_audition_plan(
        self, *, active_phrase_id: str, scope: str
    ) -> dict[str, Any]:
        """Return one zero-authority browser schedule for current choices."""

        state = self.browser_state()
        context = state["context_playback"]
        return create_vocal_working_audition(
            state["session"],
            state["sources"],
            state["candidate_vault"]["working_choices"],
            active_phrase_id=active_phrase_id,
            scope=scope,
            section_phrase_radius=int(context["section_phrase_radius"]),
            song_start_seconds=float(context["song_start_seconds"]),
            song_end_seconds=float(context["song_end_seconds"]),
        )

    def _candidate_browser_projection(
        self, candidate: Mapping[str, Any]
    ) -> dict[str, Any]:
        source_id = candidate["source_id"]
        capability = self.media_capability_by_source[source_id]
        media = self.media[source_id]
        phrase_id = candidate["phrase"]["phrase_id"]
        return {
            "source_id": source_id,
            "source_class": candidate["source_class"],
            "label": candidate["label"],
            "display_label": candidate["label"],
            "audio_sha256": candidate["audio"]["sha256"],
            "eligible_phrase_ids": [phrase_id],
            "bound_phrase_id": phrase_id,
            "media_url": f"/media/{capability}",
            "playback_start_seconds": media["playback_start_seconds"],
            "playback_end_seconds": media["playback_end_seconds"],
            "candidate_document_sha256": candidate["document_sha256"],
        }

    def _recording_state(self, session: Mapping[str, Any]) -> dict[str, Any]:
        if self.recording_cue_source_id is None:
            return {
                "available": False,
                "reason": "A hash-bound AI/reference cue is required before recording.",
            }
        reference = self._recording_reference()
        capability = self.media_capability_by_source[str(reference["source_id"])]
        sample_rate = int(reference["audio_properties"]["sample_rate"])
        phrase_plans = []
        for phrase in session["phrases"]:
            pre_guard_frames = round(_CAPTURE_GUARD_SECONDS * sample_rate)
            phrase_frames = round(
                (phrase["end_seconds"] - phrase["start_seconds"]) * sample_rate
            )
            post_guard_frames = round(_CAPTURE_GUARD_SECONDS * sample_rate)
            phrase_plans.append(
                {
                    "phrase_id": phrase["phrase_id"],
                    "cue": {
                        "cue_id": reference["source_id"],
                        "source_id": reference["source_id"],
                        "audio_sha256": reference["audio"]["sha256"],
                        "media_url": f"/media/{capability}",
                        "playback_start_seconds": phrase["start_seconds"]
                        - _CAPTURE_GUARD_SECONDS,
                        "playback_end_seconds": phrase["end_seconds"]
                        + _CAPTURE_GUARD_SECONDS,
                    },
                    "placement": {
                        "source_phrase_start_frame": pre_guard_frames,
                        "source_phrase_end_frame": pre_guard_frames + phrase_frames,
                        "pre_guard_frames": pre_guard_frames,
                        "post_guard_frames": post_guard_frames,
                        "expected_capture_frames": pre_guard_frames
                        + phrase_frames
                        + post_guard_frames,
                        "destination_start_seconds": phrase["start_seconds"],
                        "destination_end_seconds": phrase["end_seconds"],
                    },
                    "transition": build_vocal_session_transition_request(
                        session, phrase["phrase_id"]
                    ),
                }
            )
        requires_transition = _capture_transition_required(
            self.candidate_vault, session
        )
        return {
            "available": True,
            "reason": (
                "Use headphones. The verified AI/reference vocal is a timing and phrasing "
                "cue only; Save does not choose the attempt."
                + (
                    " Saving now also requires an explicit transition: the target phrase "
                    "is reopened and only unchanged decisions are revalidated."
                    if requires_transition
                    else ""
                )
            ),
            "transition_required": requires_transition,
            "headphones_required": True,
            "headphones_message": "Wear headphones so the reference cue does not leak into the microphone.",
            "requested_processing": dict(_REQUESTED_MICROPHONE_PROCESSING),
            "encoding": {
                "format": "WAV",
                "subtype": "PCM_24",
                "channels": 1,
                "description": "deterministic_pcm24_projection_of_webaudio_float32",
            },
            "placement_authority": "intended_cue_clock_only_not_verified_microphone_latency",
            "automatic_timing_correction": False,
            "save_url": _capture_save_url(self.candidate_vault),
            "max_json_bytes": _MAXIMUM_CAPTURE_REQUEST_BYTES,
            "phrases": phrase_plans,
        }


def _recording_paths(
    capture_output_dir: str | Path | None,
    candidate_vault_dir: str | Path | None,
    musical_state_root: Path,
) -> tuple[Path | None, Path | None, Path | None]:
    if capture_output_dir is not None and candidate_vault_dir is not None:
        raise ValueError(
            "capture admission and candidate vault modes are mutually exclusive"
        )
    capture = _optional_absolute_path(capture_output_dir)
    candidate = _optional_absolute_path(candidate_vault_dir)
    target = capture or candidate
    _validate_capture_destination(target, musical_state_root)
    return capture, candidate, target


def _optional_absolute_path(value: str | Path | None) -> Path | None:
    return Path(value).expanduser().absolute() if value is not None else None


def _validate_capture_destination(
    destination: Path | None, musical_state_root: Path
) -> None:
    if destination is not None and (
        destination == musical_state_root or musical_state_root in destination.parents
    ):
        raise ValueError("capture destination must be outside the Musical State")


def _open_candidate_vault(path: Path | None) -> VocalCandidateVault | None:
    return VocalCandidateVault(path) if path is not None else None


def _capture_transition_required(
    candidate_vault: VocalCandidateVault | None, session: Mapping[str, Any]
) -> bool:
    return candidate_vault is None and bool(session["coverage"]["decision_count"])


def _capture_save_url(candidate_vault: VocalCandidateVault | None) -> str:
    return "/api/candidate" if candidate_vault is not None else "/api/capture"


def create_vocal_session_server(
    musical_state_path: str | Path,
    *,
    state_dir: str | Path,
    title: str = "Vocal comp session",
    port: int = 0,
    token: str | None = None,
    recording_cue_source_id: str | None = None,
    capture_output_dir: str | Path | None = None,
    candidate_vault_dir: str | Path | None = None,
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
        recording_cue_source_id=recording_cue_source_id,
        capture_output_dir=capture_output_dir,
        candidate_vault_dir=candidate_vault_dir,
    )


def run_vocal_session(
    musical_state_path: str | Path,
    *,
    state_dir: str | Path,
    title: str = "Vocal comp session",
    port: int = 0,
    open_browser: bool = False,
    recording_cue_source_id: str | None = None,
    capture_output_dir: str | Path | None = None,
    candidate_vault_dir: str | Path | None = None,
) -> None:
    """Run the Vocal Session until interrupted."""

    server = create_vocal_session_server(
        musical_state_path,
        state_dir=state_dir,
        title=title,
        port=port,
        recording_cue_source_id=recording_cue_source_id,
        capture_output_dir=capture_output_dir,
        candidate_vault_dir=candidate_vault_dir,
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
        if parsed.path not in {"/api/draft", "/api/working-choices"}:
            self._error(HTTPStatus.NOT_FOUND, "vocal session route not found")
            return
        try:
            payload = self._put_payload(parsed.path)
        except (
            VocalCandidateVaultConflictError,
            VocalSessionDraftConflictError,
        ) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except (ValueError, OSError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json(HTTPStatus.OK, payload)

    def _put_payload(self, path: str) -> dict[str, Any]:
        request = self._request_json()
        if path == "/api/working-choices":
            return {"working_choices": self._save_working_choices(request)}
        session = self.server.store.current_session(self.server.musical_state)
        saved = self.server.store.save_draft(
            session,
            _mapping(request.get("draft"), "draft"),
            expected_revision=_integer(
                request.get("expected_revision"), "expected_revision"
            ),
        )
        return {"draft": saved}

    def _save_working_choices(self, request: Mapping[str, Any]) -> dict[str, Any]:
        vault = self.server.candidate_vault
        if vault is None:
            raise ValueError("vocal candidate vault is not configured")
        if set(request) != {"expected_revision", "working_source_by_phrase"}:
            raise ValueError("working choice request fields changed")
        return vault.save_working_choices(
            self.server.musical_state,
            _mapping(
                request.get("working_source_by_phrase"),
                "working_source_by_phrase",
            ),
            expected_revision=_integer(
                request.get("expected_revision"), "expected_revision"
            ),
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._begin(parsed, mutation=True):
            return
        if parsed.path in {"/api/capture", "/api/candidate"}:
            self._post_recording_source(parsed.path)
            return
        if parsed.path == "/api/reopen":
            try:
                request = self._request_json()
                if set(request) != {
                    "phrase_id",
                    "expected_decision_document_sha256",
                    "reason",
                }:
                    raise ValueError("phrase reopen request fields changed")
                session = self.server.store.current_session(self.server.musical_state)
                reopened = self.server.store.reopen_phrase(
                    session,
                    phrase_id=_text(request.get("phrase_id"), "phrase_id", 256),
                    expected_decision_document_sha256=_text(
                        request.get("expected_decision_document_sha256"),
                        "expected_decision_document_sha256",
                        64,
                    ),
                    reason=_text(request.get("reason"), "reason", 64),
                )
            except (ValueError, OSError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(
                HTTPStatus.CREATED,
                {"reopen": reopened, "state": self.server.browser_state()},
            )
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

    def _post_recording_source(self, path: str) -> None:
        try:
            request = self._request_json(maximum_bytes=_MAXIMUM_CAPTURE_REQUEST_BYTES)
            operation = (
                self.server.keep_candidate
                if path == "/api/candidate"
                else self.server.admit_capture
            )
            result = operation(request)
        except (
            VocalCandidateVaultConflictError,
            VocalSessionCaptureConflictError,
        ) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except VocalSessionRequestTooLargeError as exc:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
            return
        except (ValueError, OSError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json(HTTPStatus.CREATED, result)

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
        if parsed.path == "/api/working-audition":
            try:
                query = parse_qs(parsed.query)
                if set(query) != {"token", "scope", "phrase_id"}:
                    raise ValueError("working audition query fields changed")
                plan = self.server.working_audition_plan(
                    active_phrase_id=_single_query_value(query, "phrase_id"),
                    scope=_single_query_value(query, "scope"),
                )
            except (ValueError, OSError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, plan, head_only=head_only)
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

    def _request_json(
        self, *, maximum_bytes: int = _MAXIMUM_JSON_REQUEST_BYTES
    ) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("request Content-Length is invalid") from exc
        if not 0 < length <= maximum_bytes:
            if maximum_bytes == _MAXIMUM_CAPTURE_REQUEST_BYTES:
                raise VocalSessionRequestTooLargeError(
                    "vocal capture request is larger than the 10 MiB limit"
                )
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
        microphone = "(self)" if self.server.recording_cue_source_id else "()"
        self.send_header("Permissions-Policy", f"microphone={microphone}, autoplay=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "media-src 'self' blob:; connect-src 'self'; img-src 'self' data:; "
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


def _single_query_value(query: Mapping[str, list[str]], field: str) -> str:
    values = query.get(field)
    if not isinstance(values, list) or len(values) != 1:
        raise ValueError(f"working audition {field} must occur once")
    return _text(values[0], field, 256)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _capture_request_fields() -> set[str]:
    return {
        "expected_musical_state_sha256",
        "phrase_id",
        "capture_id",
        "cue_id",
        "cue_asset_sha256",
        "audio_wav_base64",
        "placement",
        "actual_processing",
    }


def _decode_capture_wav(value: Any) -> bytes:
    encoded = _text(
        value,
        "audio_wav_base64",
        _MAXIMUM_CAPTURE_REQUEST_BYTES,
    )
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("vocal capture audio WAV base64 is invalid") from exc


def _validated_capture_placement(
    value: Any,
    *,
    phrase: Mapping[str, Any],
    geometry: Mapping[str, int],
) -> dict[str, Any]:
    placement = _mapping(value, "placement")
    expected_keys = {
        "source_phrase_start_frame",
        "source_phrase_end_frame",
        "pre_guard_frames",
        "post_guard_frames",
        "destination_start_seconds",
        "destination_end_seconds",
    }
    if set(placement) != expected_keys:
        raise ValueError("vocal capture placement fields changed")
    start = _integer(
        placement.get("source_phrase_start_frame"), "source_phrase_start_frame"
    )
    end = _integer(placement.get("source_phrase_end_frame"), "source_phrase_end_frame")
    pre_guard = _integer(placement.get("pre_guard_frames"), "pre_guard_frames")
    post_guard = _integer(placement.get("post_guard_frames"), "post_guard_frames")
    sample_rate = geometry["sample_rate"]
    expected_guard = round(_CAPTURE_GUARD_SECONDS * sample_rate)
    expected_phrase_frames = round(
        (float(phrase["end_seconds"]) - float(phrase["start_seconds"])) * sample_rate
    )
    if (
        pre_guard != expected_guard
        or post_guard != expected_guard
        or start != pre_guard
        or end != start + expected_phrase_frames
        or geometry["frames"] != end + post_guard
    ):
        raise ValueError(
            "vocal capture must match the reviewed phrase plus fixed half-second guards"
        )
    if (
        placement.get("destination_start_seconds") != phrase["start_seconds"]
        or placement.get("destination_end_seconds") != phrase["end_seconds"]
    ):
        raise ValueError("vocal capture destination geometry changed")
    return placement


def _pcm24_wav_geometry(payload: bytes) -> dict[str, int]:
    if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise ValueError("vocal capture must be a deterministic WAV")
    if payload[12:16] != b"fmt " or payload[36:40] != b"data":
        raise ValueError("vocal capture WAV chunks are unsupported")
    format_size, audio_format, channels = struct.unpack_from("<IHH", payload, 16)
    sample_rate, byte_rate, block_align, bits = struct.unpack_from("<IIHH", payload, 24)
    data_bytes = struct.unpack_from("<I", payload, 40)[0]
    if (
        format_size != 16
        or audio_format != 1
        or channels != 1
        or bits != 24
        or block_align != 3
        or byte_rate != sample_rate * 3
        or sample_rate <= 0
        or data_bytes != len(payload) - 44
        or data_bytes % 3
        or struct.unpack_from("<I", payload, 4)[0] != len(payload) - 8
    ):
        raise ValueError("vocal capture must be exact mono PCM24 WAV")
    return {"sample_rate": sample_rate, "frames": data_bytes // 3}


def _write_private_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


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
