"""Loopback-only HTTP server for the local Sunofriend Workbench."""

from __future__ import annotations

import errno
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

from .workbench_catalog import (
    build_workbench_catalog,
    media_files,
    public_catalog,
)
from .workbench_artifacts import (
    WorkbenchArtifacts,
    WorkbenchPackConflictError,
    canonical_garageband_pack_basket,
    selected_candidates,
)
from .workbench_store import (
    WorkbenchPackStateConflictError,
    WorkbenchStore,
    default_workbench_state_dir,
)
from .workbench_home import build_workbench_home
from .workbench_privacy import path_free_browser_state
from .workbench_timeline import (
    TimelineArtifactChangedError,
    build_arrangement_timeline,
    build_stem_timeline,
)


_MAX_REQUEST_BYTES = 64 * 1024


def _read_verified_immutable_bytes(handle: Any, record: Mapping[str, Any]) -> bytes:
    """Read one pinned response into bytes that cannot drift while served."""

    payload = handle.read()
    if len(payload) != record.get("bytes") or hashlib.sha256(
        payload
    ).hexdigest() != str(record.get("sha256", "")):
        raise ValueError("pinned file bytes changed")
    return payload


def _require_exact_request_keys(
    request: Mapping[str, Any],
    expected: set[str],
    *,
    label: str = "GarageBand pack",
) -> None:
    actual = set(request)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError(f"invalid {label} request: " + "; ".join(details))


def _display_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return one stable primary-first display identity for every UI surface."""

    ordered = [candidate for candidate in candidates if candidate.get("primary")]
    ordered.extend(
        candidate for candidate in candidates if not candidate.get("primary")
    )
    return [
        {**candidate, "display_letter": _display_letter(index)}
        for index, candidate in enumerate(ordered)
    ]


def _display_letter(index: int) -> str:
    """Return A..Z, AA..AZ and so on without reusing a visible identity."""

    value = int(index) + 1
    if value <= 0:
        raise ValueError("candidate display index must not be negative")
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _phrase_review_capabilities(
    catalog: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[str, str]]]:
    """Register only validated phrase-review files behind per-launch secrets."""

    capabilities: dict[str, dict[str, Any]] = {}
    by_stem: dict[str, tuple[str, str]] = {}
    for stem in catalog.get("stems", []):
        link = stem.get("_phrase_review_link")
        if link is None:
            continue
        if not isinstance(link, Mapping):
            raise ValueError("Workbench phrase-review link is invalid")
        entrypoint = link.get("entrypoint")
        files = link.get("files")
        if (
            not isinstance(entrypoint, str)
            or not entrypoint
            or not isinstance(files, Mapping)
            or entrypoint not in files
        ):
            raise ValueError("Workbench phrase-review package is incomplete")
        copied_files: dict[str, dict[str, Any]] = {}
        for relative_path, record in files.items():
            if not isinstance(relative_path, str) or not isinstance(record, Mapping):
                raise ValueError("Workbench phrase-review file record is invalid")
            copied_files[relative_path] = dict(record)
        capability = secrets.token_urlsafe(32)
        while capability in capabilities:  # pragma: no cover - cryptographic collision
            capability = secrets.token_urlsafe(32)
        stem_id = str(stem["stem_id"])
        if stem_id in by_stem:
            raise ValueError("Workbench phrase-review stem ids must be unique")
        capabilities[capability] = {"files": copied_files}
        by_stem[stem_id] = (capability, entrypoint)
    return capabilities, by_stem


class WorkbenchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        catalog: Mapping[str, Any],
        store: WorkbenchStore,
        artifacts: WorkbenchArtifacts,
        token: str,
    ) -> None:
        self.catalog = catalog
        self.store = store
        self.artifacts = artifacts
        self.token = token
        self.media = media_files(catalog)
        (
            self.phrase_review_capabilities,
            self.phrase_review_capability_by_stem,
        ) = _phrase_review_capabilities(catalog)
        self.state_lock = threading.RLock()
        super().__init__(address, _WorkbenchHandler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/?token={self.token}"


def create_workbench_server(
    catalog: Mapping[str, Any],
    *,
    state_dir: str | Path | None = None,
    port: int = 0,
    token: str | None = None,
    soundfont_path: str | Path | None = None,
) -> WorkbenchHTTPServer:
    """Create, but do not start, a loopback-only Workbench server."""

    if not 0 <= int(port) <= 65535:
        raise ValueError("workbench port must be between 0 and 65535")
    destination = (
        Path(state_dir).expanduser().resolve()
        if state_dir is not None
        else default_workbench_state_dir(catalog)
    )
    destination.mkdir(parents=True, exist_ok=True)
    store = WorkbenchStore(destination / "workbench.sqlite3")
    artifacts = WorkbenchArtifacts(
        destination / "artifacts", soundfont_path=soundfont_path
    )
    session_token = token or secrets.token_urlsafe(32)
    return WorkbenchHTTPServer(
        ("127.0.0.1", int(port)),
        catalog=catalog,
        store=store,
        artifacts=artifacts,
        token=session_token,
    )


def run_workbench(
    project_root: str | Path,
    *,
    candidate_roots: Sequence[str | Path] = (),
    catalog_path: str | Path | None = None,
    state_dir: str | Path | None = None,
    port: int = 0,
    open_browser: bool = False,
    inspect_only: bool = False,
    export_review_path: str | Path | None = None,
    soundfont_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a catalogue and inspect, export, or serve the local workbench."""

    if export_review_path is not None and (inspect_only or open_browser):
        raise ValueError("--export-review cannot be combined with --inspect or --open")

    catalog = build_workbench_catalog(
        project_root,
        candidate_roots=candidate_roots,
        catalog_path=catalog_path,
    )
    if inspect_only:
        return {
            "status": "inspected",
            "catalog": public_catalog(catalog),
            "server_started": False,
        }
    if export_review_path is not None:
        return export_workbench_review(
            catalog,
            state_dir=state_dir,
            output_path=export_review_path,
        )
    server = create_workbench_server(
        catalog,
        state_dir=state_dir,
        port=port,
        soundfont_path=soundfont_path,
    )
    print("Sunofriend Workbench")
    print("Local — nothing is being uploaded")
    print(server.url, flush=True)
    print(f"Decisions: {server.store.path}", flush=True)
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {
        "status": "stopped",
        "url": server.url,
        "database": str(server.store.path),
        "server_started": True,
    }


def export_workbench_review(
    catalog: Mapping[str, Any],
    *,
    state_dir: str | Path | None = None,
    output_path: str | Path,
) -> dict[str, Any]:
    """Export the current private review state without creating an HTTP server."""

    state = (
        Path(state_dir).expanduser().resolve()
        if state_dir is not None
        else default_workbench_state_dir(catalog)
    )
    store = WorkbenchStore(state / "workbench.sqlite3")
    review = store.export_review(catalog)
    # Match the existing /api/review representation byte-for-byte for the
    # document returned by WorkbenchStore.export_review.
    payload = json.dumps(review, indent=2, sort_keys=True).encode("utf-8")
    destination = _write_fresh_atomic(output_path, payload)
    return {
        "status": "exported",
        "review_status": review["status"],
        "event_count": len(review["events"]),
        "applied_event_count": review["current"]["event_count"],
        "output": {
            "path": str(destination),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "private_artifact": True,
        "privacy_notice": (
            "Keep private: this exact local review archive may contain absolute "
            "paths and free-text notes."
        ),
        "server_started": False,
    }


def _write_fresh_atomic(output_path: str | Path, payload: bytes) -> Path:
    """Publish complete bytes atomically while refusing to replace a path."""

    expanded = Path(output_path).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    # Resolve only the parent: resolving the final component would follow an
    # existing broken symlink and could create its target instead of rejecting
    # the already-occupied requested path.
    destination = absolute.parent.resolve() / absolute.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        raise FileExistsError(f"review export already exists: {destination}")
    temporary = destination.with_name(
        f".{destination.name}.{secrets.token_hex(12)}.tmp"
    )
    published = False
    try:
        descriptor: int | None = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            else:  # pragma: no cover - Windows compatibility
                os.chmod(temporary, 0o600)
            handle = os.fdopen(descriptor, "wb")
            descriptor = None
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor is not None:
                os.close(descriptor)
        try:
            os.link(temporary, destination)
            published = True
        except FileExistsError as exc:
            raise FileExistsError(
                f"review export already exists: {destination}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    if published:
        _fsync_directory(destination.parent)
    return destination


def _fsync_directory(directory: Path) -> None:
    """Durably record a published directory entry when the platform permits."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EPERM, errno.EINVAL, errno.ENOTSUP}:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in {
                errno.EBADF,
                errno.EINVAL,
                errno.ENOTSUP,
            }:
                raise
    finally:
        os.close(descriptor)


class _WorkbenchHandler(BaseHTTPRequestHandler):
    server: WorkbenchHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_local_request():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/workbench-transport.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_transport_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path.startswith("/phrase-review/"):
            self._serve_phrase_review(parsed.path)
            return
        if not self._authorised(parsed):
            self._error(HTTPStatus.FORBIDDEN, "invalid workbench session token")
            return
        if parsed.path == "/":
            self._bytes(
                HTTPStatus.OK,
                _workbench_html_bytes(),
                "text/html; charset=utf-8",
            )
            return
        if parsed.path == "/api/project":
            self._json(HTTPStatus.OK, self._project_payload())
            return
        if parsed.path == "/api/timeline":
            timeline_query = parse_qs(parsed.query, keep_blank_values=True)
            stem_id = timeline_query.get("stem_id", [""])[0]
            candidate_ids = timeline_query.get("candidate_id")
            try:
                timeline = build_stem_timeline(
                    self.server.catalog,
                    stem_id,
                    candidate_ids=candidate_ids,
                    include_source=candidate_ids is None,
                )
            except TimelineArtifactChangedError as exc:
                self._error(HTTPStatus.CONFLICT, str(exc))
                return
            except (OSError, RuntimeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, timeline)
            return
        if parsed.path == "/api/arrangement-timeline":
            try:
                current = self.server.store.current_state(self.server.catalog)
                timeline = build_arrangement_timeline(
                    self.server.catalog,
                    selected_candidates(self.server.catalog, current),
                )
            except TimelineArtifactChangedError as exc:
                self._error(HTTPStatus.CONFLICT, str(exc))
                return
            except (OSError, RuntimeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, timeline)
            return
        if parsed.path == "/api/garageband-pack-plan":
            try:
                with self.server.state_lock:
                    plan = self._garageband_pack_plan_payload()
            except WorkbenchPackConflictError as exc:
                self._error(HTTPStatus.CONFLICT, str(exc))
                return
            except (OSError, RuntimeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, {"plan": plan})
            return
        if parsed.path == "/api/review":
            self._json(
                HTTPStatus.OK,
                self.server.store.export_review(self.server.catalog),
                filename="sunofriend-workbench-review.json",
            )
            return
        if parsed.path.startswith("/media/"):
            media_id = parsed.path[len("/media/") :]
            self._serve_media(media_id)
            return
        self._error(HTTPStatus.NOT_FOUND, "workbench route not found")

    def do_POST(self) -> None:  # noqa: N802
        if not self._valid_local_request():
            return
        parsed = urlparse(self.path)
        if not self._authorised(parsed):
            self._error(HTTPStatus.FORBIDDEN, "invalid workbench session token")
            return
        if parsed.path not in {
            "/api/events",
            "/api/render-preview",
            "/api/decoded-loop",
            "/api/arrangement",
            "/api/garageband-export",
            "/api/garageband-pack-basket",
            "/api/garageband-pack",
        }:
            self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
            return
        try:
            request = self._request_json()
            if parsed.path == "/api/events":
                with self.server.state_lock:
                    event = self.server.store.append(self.server.catalog, request)
                    state = self.server.store.current_state(self.server.catalog)
                self._json(
                    HTTPStatus.CREATED,
                    {
                        "event": event,
                        "state": path_free_browser_state(state),
                        "home": build_workbench_home(self.server.catalog, state),
                    },
                )
                return
            if parsed.path == "/api/render-preview":
                artifact = self.server.artifacts.render_candidate_preview(
                    self.server.catalog,
                    str(request.get("stem_id", "")),
                    str(request.get("candidate_id", "")),
                )
                self._json(
                    HTTPStatus.OK,
                    {"preview": self._public_artifact(artifact)},
                )
                return
            if parsed.path == "/api/decoded-loop":
                _require_exact_request_keys(
                    request,
                    {
                        "stem_id",
                        "candidate_ids",
                        "start_seconds",
                        "end_seconds",
                    },
                    label="decoded loop",
                )
                artifact = self.server.artifacts.prepare_decoded_stem_loop(
                    self.server.catalog,
                    str(request.get("stem_id", "")),
                    request.get("candidate_ids"),
                    request.get("start_seconds"),
                    request.get("end_seconds"),
                )
                self._json(
                    HTTPStatus.OK,
                    {"loop": self._public_decoded_loop(artifact)},
                )
                return
            if parsed.path == "/api/garageband-pack-basket":
                _require_exact_request_keys(
                    request,
                    {
                        "plan_sha256",
                        "basket_scope_sha256",
                        "expected_revision",
                        "included_item_ids",
                        "source_audio_opt_in",
                    },
                )
                with self.server.state_lock:
                    current = self.server.store.current_state(self.server.catalog)
                    plan = self.server.artifacts.garageband_pack_plan(
                        self.server.catalog, current
                    )
                    if request.get("plan_sha256") != plan["plan_sha256"]:
                        raise WorkbenchPackConflictError(
                            "the GarageBand pack plan changed; reload its contents"
                        )
                    if (
                        request.get("basket_scope_sha256")
                        != plan["basket_scope_sha256"]
                    ):
                        raise WorkbenchPackConflictError(
                            "the GarageBand pack selection changed; reload its contents"
                        )
                    basket = canonical_garageband_pack_basket(
                        plan,
                        request.get("included_item_ids"),
                        request.get("source_audio_opt_in"),
                    )
                    saved = self.server.store.save_pack_selection(
                        str(self.server.catalog["project_id"]),
                        basket,
                        plan_sha256=str(plan["plan_sha256"]),
                        expected_revision=request.get("expected_revision"),
                    )
                    saved["plan_current"] = True
                self._json(HTTPStatus.OK, {"basket": saved})
                return
            if parsed.path == "/api/garageband-pack":
                _require_exact_request_keys(
                    request,
                    {"plan_sha256", "basket_sha256"},
                )
                with self.server.state_lock:
                    plan = self._garageband_pack_plan_payload()
                    if request.get("plan_sha256") != plan["plan_sha256"]:
                        raise WorkbenchPackConflictError(
                            "the GarageBand pack plan changed; reload its contents"
                        )
                    basket = plan["basket"]
                    if not basket.get("saved") or not basket.get("plan_current"):
                        raise WorkbenchPackConflictError(
                            "save the GarageBand pack contents for the current plan before building"
                        )
                    if request.get("basket_sha256") != basket.get("basket_sha256"):
                        raise WorkbenchPackConflictError(
                            "the saved GarageBand pack contents changed; reload them"
                        )
                    current = self.server.store.current_state(self.server.catalog)
                    artifact = self.server.artifacts.build_garageband_pack(
                        self.server.catalog,
                        current,
                        plan_sha256=str(plan["plan_sha256"]),
                        basket=basket,
                    )
                self._json(
                    HTTPStatus.OK,
                    {"pack": self._public_artifact(artifact)},
                )
                return
            current = self.server.store.current_state(self.server.catalog)
            if parsed.path == "/api/arrangement":
                artifact = self.server.artifacts.render_arrangement(
                    self.server.catalog, current
                )
                self._json(
                    HTTPStatus.OK,
                    {"arrangement": self._public_artifact(artifact)},
                )
                return
            artifact = self.server.artifacts.build_garageband_handoff(
                self.server.catalog, current
            )
            self._json(
                HTTPStatus.OK,
                {"handoff": self._public_artifact(artifact)},
            )
        except (WorkbenchPackConflictError, WorkbenchPackStateConflictError) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def _garageband_pack_plan_payload(self) -> dict[str, Any]:
        current = self.server.store.current_state(self.server.catalog)
        plan = self.server.artifacts.garageband_pack_plan(self.server.catalog, current)
        default = dict(plan["default_basket"])
        saved = self.server.store.current_pack_selection(
            str(self.server.catalog["project_id"]),
            str(plan["basket_scope_sha256"]),
        )
        if saved is None:
            basket = {
                **default,
                "revision": 0,
                "saved": False,
                "saved_at": None,
                "saved_plan_sha256": None,
                "plan_current": True,
            }
            plan["basket_restore_status"] = "safe-default"
        else:
            try:
                canonical = canonical_garageband_pack_basket(
                    plan,
                    saved.get("included_item_ids"),
                    saved.get("source_audio_opt_in"),
                )
                if canonical["basket_sha256"] != saved.get("basket_sha256"):
                    raise ValueError("saved basket hash disagrees")
            except (TypeError, ValueError):
                basket = {
                    **default,
                    "revision": saved["revision"],
                    "saved": False,
                    "saved_at": saved.get("saved_at"),
                    "saved_plan_sha256": saved.get("saved_plan_sha256"),
                    "plan_current": False,
                }
                plan["basket_restore_status"] = "invalid-saved-state-defaulted"
            else:
                basket = {
                    **canonical,
                    "revision": saved["revision"],
                    "saved": True,
                    "saved_at": saved.get("saved_at"),
                    "saved_plan_sha256": saved.get("saved_plan_sha256"),
                    "plan_current": (
                        saved.get("saved_plan_sha256") == plan["plan_sha256"]
                    ),
                }
                plan["basket_restore_status"] = (
                    "saved-current-plan"
                    if basket["plan_current"]
                    else "saved-choices-current-plan-not-confirmed"
                )
        plan["basket"] = basket
        return plan

    def _project_payload(self) -> dict[str, Any]:
        payload = public_catalog(self.server.catalog)
        for stem in payload["stems"]:
            phrase_capability = self.server.phrase_review_capability_by_stem.get(
                str(stem["stem_id"])
            )
            phrase_link = stem.get("phrase_review_link")
            if phrase_capability and isinstance(phrase_link, dict):
                capability, entrypoint = phrase_capability
                phrase_link["review_url"] = f"/phrase-review/{capability}/{entrypoint}"
            stem["candidates"] = _display_candidates(stem["candidates"])
            stem["source_url"] = self._media_url(stem["source_media_id"])
            source = stem.get("source")
            if isinstance(source, dict):
                source.pop("path", None)
            for candidate in stem["candidates"]:
                candidate["midi_url"] = self._media_url(candidate["midi_media_id"])
                candidate["preview_url"] = (
                    self._media_url(candidate["preview_media_id"])
                    if candidate.get("preview_media_id")
                    else None
                )
                for record_name in ("midi", "preview"):
                    record = candidate.get(record_name)
                    if isinstance(record, dict):
                        record.pop("path", None)
                cached = self.server.artifacts.cached_candidate_preview(
                    self.server.catalog,
                    str(stem["stem_id"]),
                    str(candidate["candidate_id"]),
                )
                candidate["neutral_preview"] = (
                    self._public_artifact(cached) if cached else None
                )
        state = self.server.store.current_state(self.server.catalog)
        review = self.server.store.export_review(self.server.catalog)
        payload["state"] = path_free_browser_state(state)
        payload["home"] = build_workbench_home(self.server.catalog, state)
        payload["contribution_preview"] = review["contribution_preview"]
        payload["review_status"] = review["status"]
        payload["review_url"] = f"/api/review?token={self.server.token}"
        payload["selected_midi_overlap"] = self.server.artifacts.selected_midi_overlap(
            self.server.catalog,
            state,
        )
        arrangement = self.server.artifacts.cached_arrangement(
            self.server.catalog, state
        )
        payload["arrangement"] = (
            self._public_artifact(arrangement) if arrangement else None
        )
        return payload

    def _request_json(self) -> Mapping[str, Any]:
        length_value = self.headers.get("Content-Length")
        try:
            length = int(length_value or "0")
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > _MAX_REQUEST_BYTES:
            raise ValueError("invalid workbench request size")
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(request, Mapping):
            raise ValueError("workbench request must be an object")
        return request

    def _public_artifact(self, artifact: Mapping[str, Any]) -> dict[str, Any]:
        public = {
            key: value
            for key, value in artifact.items()
            if key not in {"midi", "preview", "zip"}
        }
        for key, prefix in (
            ("midi", "artifact-midi"),
            ("preview", "artifact-preview"),
            ("zip", "artifact-zip"),
        ):
            record = artifact.get(key)
            if not isinstance(record, Mapping):
                continue
            media_id = f"{prefix}-{str(record['sha256'])[:24]}"
            self.server.media[media_id] = dict(record)
            public[key] = {
                item_key: item_value
                for item_key, item_value in record.items()
                if item_key != "path"
            }
            public[f"{key}_url"] = self._media_url(media_id)
        return public

    def _public_decoded_loop(self, artifact: Mapping[str, Any]) -> dict[str, Any]:
        """Register bounded private loop WAVs and return no local paths."""

        public = {
            key: artifact[key]
            for key in (
                "schema",
                "stem_id",
                "candidate_ids",
                "start_seconds",
                "end_seconds",
                "duration_seconds",
                "cache_hit",
                "effects",
            )
            if key in artifact
        }
        tracks = []
        for track in artifact.get("tracks", []):
            if not isinstance(track, Mapping):
                raise ValueError("decoded loop track is invalid")
            record = track.get("audio")
            if not isinstance(record, Mapping):
                raise ValueError("decoded loop track audio is invalid")
            media_id = f"decoded-loop-{str(record['sha256'])[:24]}"
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            self.server.media[media_id] = private_record
            public_track = {
                key: track[key]
                for key in (
                    "track_id",
                    "kind",
                    "candidate_id",
                    "sample_rate",
                    "channels",
                    "frames",
                    "start_frame",
                    "silence_padded_frames",
                )
                if key in track
            }
            public_track["audio"] = {
                key: record[key]
                for key in ("name", "bytes", "sha256")
                if key in record
            }
            public_track["audio_url"] = self._media_url(media_id)
            tracks.append(public_track)
        public["tracks"] = tracks
        return public

    def _serve_media(self, media_id: str) -> None:
        record = self.server.media.get(media_id)
        if not isinstance(record, Mapping):
            self._error(HTTPStatus.NOT_FOUND, "workbench media not found")
            return
        self._serve_file_record(
            record,
            freeze_verified=bool(record.get("_freeze_on_serve")),
        )

    def _serve_phrase_review(self, request_path: str) -> None:
        parts = request_path.split("/", 3)
        if len(parts) != 4 or parts[:2] != ["", "phrase-review"]:
            self._error(HTTPStatus.NOT_FOUND, "phrase review file not found")
            return
        capability = parts[2]
        try:
            relative_path = unquote(parts[3], errors="strict")
        except UnicodeDecodeError:
            self._error(HTTPStatus.NOT_FOUND, "phrase review file not found")
            return
        package = self.server.phrase_review_capabilities.get(capability)
        if not isinstance(package, Mapping):
            self._error(HTTPStatus.NOT_FOUND, "phrase review file not found")
            return
        files = package.get("files")
        record = files.get(relative_path) if isinstance(files, Mapping) else None
        if not isinstance(record, Mapping):
            self._error(HTTPStatus.NOT_FOUND, "phrase review file not found")
            return
        self._serve_file_record(record, phrase_review=True)

    def _serve_file_record(
        self,
        record: Mapping[str, Any],
        *,
        phrase_review: bool = False,
        freeze_verified: bool = False,
    ) -> None:
        path = Path(str(record.get("path", "")))
        try:
            handle = path.open("rb")
        except OSError:
            self._error(HTTPStatus.NOT_FOUND, "workbench media not found")
            return
        with handle:
            frozen_payload: bytes | None = None
            if phrase_review or freeze_verified:
                try:
                    frozen_payload = _read_verified_immutable_bytes(handle, record)
                except ValueError:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "workbench media changed after it was catalogued; restart the Workbench",
                    )
                    return
                size = len(frozen_payload)
                verified = True
            else:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(0)
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                actual_sha256 = digest.hexdigest()
                verified = size == record.get("bytes") and actual_sha256 == str(
                    record.get("sha256", "")
                )
            if not verified:
                self._error(
                    HTTPStatus.CONFLICT,
                    "workbench media changed after it was catalogued; restart the Workbench",
                )
                return
            start, end = 0, size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header:
                try:
                    start, end = _parse_byte_range(range_header, size)
                except ValueError as exc:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self._security_headers(phrase_review=phrase_review)
                    payload = str(exc).encode("utf-8")
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                status = HTTPStatus.PARTIAL_CONTENT
            content_type = (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            self.send_response(status)
            self._security_headers(phrase_review=phrase_review)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            disposition = (
                "attachment"
                if path.suffix.lower() == ".zip" and not phrase_review
                else "inline"
            )
            self.send_header(
                "Content-Disposition",
                f'{disposition}; filename="{_safe_filename(path.name)}"',
            )
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                if frozen_payload is not None:
                    self.wfile.write(frozen_payload[start : end + 1])
                    return
                handle.seek(start)
                remaining = max(0, end - start + 1)
                while remaining:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                # Browsers routinely cancel an initial media request after reading
                # metadata and issue a narrower Range request. That is not a server
                # failure and should not dump a traceback into the CLI.
                return

    def _media_url(self, media_id: str) -> str:
        return f"/media/{media_id}?token={self.server.token}"

    def _authorised(self, parsed: Any) -> bool:
        supplied = parse_qs(parsed.query).get("token", [""])[0]
        return hmac.compare_digest(supplied, self.server.token)

    def _valid_local_request(self) -> bool:
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        if host not in {"127.0.0.1", "localhost"}:
            self._error(
                HTTPStatus.FORBIDDEN, "workbench accepts loopback requests only"
            )
            return False
        client = self.client_address[0]
        if client not in {"127.0.0.1", "::1"}:
            self._error(HTTPStatus.FORBIDDEN, "workbench accepts loopback clients only")
            return False
        return True

    def _json(
        self,
        status: HTTPStatus,
        value: Mapping[str, Any],
        *,
        filename: str | None = None,
    ) -> None:
        payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
        headers = {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        self._bytes(status, payload, "application/json; charset=utf-8", headers=headers)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": message})

    def _bytes(
        self,
        status: HTTPStatus,
        payload: bytes,
        content_type: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _security_headers(self, *, phrase_review: bool = False) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if phrase_review:
            self.send_header("Permissions-Policy", "autoplay=()")
        connect_source = "'none'" if phrase_review else "'self'"
        # The existing review uses alert() for incomplete exports, so retain
        # modals while withholding forms, popups and top-level navigation.
        sandbox = (
            "; sandbox allow-scripts allow-same-origin allow-downloads allow-modals; "
            "form-action 'none'"
            if phrase_review
            else ""
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
            f"media-src 'self'; connect-src {connect_source}; img-src 'self' data:; "
            f"object-src 'none'; base-uri 'none'; frame-ancestors 'none'{sandbox}",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def _parse_byte_range(value: str, size: int) -> tuple[int, int]:
    if size <= 0 or not value.startswith("bytes=") or "," in value:
        raise ValueError("unsupported byte range")
    spec = value[len("bytes=") :].strip()
    if "-" not in spec:
        raise ValueError("invalid byte range")
    start_text, end_text = spec.split("-", 1)
    if not start_text:
        length = int(end_text)
        if length <= 0:
            raise ValueError("invalid byte range")
        return max(0, size - length), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError("byte range outside media")
    return start, min(end, size - 1)


def _safe_filename(value: str) -> str:
    return (
        "".join(
            character
            for character in value
            if character.isalnum() or character in "._- "
        )
        or "media"
    )


def _workbench_html_bytes() -> bytes:
    """Load the single packaged UI source and fail clearly if packaging is broken."""

    path = Path(__file__).with_name("workbench.html")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"packaged Workbench UI is unavailable: {path}") from exc


def _workbench_transport_bytes() -> bytes:
    """Load the non-sensitive shared transport used by the local Workbench."""

    path = Path(__file__).with_name("workbench_transport.js")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"packaged Workbench transport is unavailable: {path}"
        ) from exc


_REMOVED_EMBEDDED_WORKBENCH_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend Workbench</title>
<style>
:root{color-scheme:dark;--bg:#0c1118;--panel:#151e29;--panel2:#1b2734;--line:#34475a;--text:#eff6fc;--muted:#a9bac8;--gold:#ffc94a;--blue:#70c9ff;--green:#65db9a;--red:#ff8b8b}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 system-ui,-apple-system,sans-serif}button,select,input,textarea{font:inherit}.local{position:sticky;top:0;z-index:5;background:#153927;color:#bdffd7;padding:.65rem 1.2rem;border-bottom:1px solid #2a6749;font-weight:700}.layout{display:grid;grid-template-columns:300px 1fr;min-height:calc(100vh - 45px)}aside{border-right:1px solid var(--line);padding:1.2rem;background:#101720}main{padding:1.5rem;max-width:1150px;width:100%;margin:auto}h1{font-size:2rem;margin:.2rem 0}.muted{color:var(--muted)}.setup,.card,.controls,.stem-row,.preview{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1rem;margin:1rem 0}.steps{padding-left:1.2rem;color:var(--muted)}.steps li{margin:.65rem 0}.stem-list{display:grid;gap:.5rem}.stem-link{display:block;width:100%;text-align:left;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:.8rem;cursor:pointer}.stem-link.active{border-color:var(--gold)}.badge{display:inline-block;border-radius:999px;padding:.18rem .55rem;background:#26384a;color:var(--blue);font-size:.82rem}.progress{color:var(--gold);font-weight:700}.candidate-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}.card{margin:0}.card.chosen{border-color:var(--green)}audio{width:100%;margin:.6rem 0}.actions{display:flex;flex-wrap:wrap;gap:.45rem}.actions button,.primary{border:1px solid #47708d;background:#234a66;color:white;border-radius:8px;padding:.55rem .7rem;cursor:pointer}.actions button[data-decision=reject]{background:#512f36}.actions button[data-decision=needs_correction]{background:#5a4926}.actions button.selected{outline:3px solid var(--gold)}label{display:block;margin:.55rem 0}#role{margin-left:.5rem;padding:.45rem;background:#0f1720;color:var(--text);border:1px solid var(--line);border-radius:8px}textarea{width:100%;background:#0f1720;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:.5rem}.problems{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));font-size:.9rem}.problems label{margin:.2rem}.loop{display:flex;gap:.7rem;align-items:end;flex-wrap:wrap}.loop input{width:90px;background:#0f1720;color:var(--text);border:1px solid var(--line);padding:.4rem}.outcomes{display:flex;gap:.5rem;flex-wrap:wrap}.outcomes button{background:#26384a;color:var(--text);border:1px solid var(--line);padding:.55rem;border-radius:8px}.outcomes button.selected{outline:3px solid var(--gold)}details{margin-top:.7rem}pre{white-space:pre-wrap;overflow:auto;max-height:420px;background:#081018;padding:1rem;border-radius:8px}.notice{border-left:4px solid var(--gold);padding:.7rem 1rem;background:#2a261a}.error{color:var(--red)}a{color:var(--blue)}@media(max-width:800px){.layout{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid var(--line)}main{padding:1rem}}
</style></head><body><div class="local">● Local — nothing is being uploaded</div><div class="layout"><aside><h1>Sunofriend</h1><p class="muted">MIDI decision workbench</p><ol class="steps"><li>Check song setup</li><li><strong>Choose MIDI parts</strong></li><li>Hear arrangement <span class="badge">later</span></li><li>Choose instruments <span class="badge">later</span></li><li>Export</li></ol><p id="progress" class="progress">Loading…</p><div id="stem-list" class="stem-list"></div><hr><p><a id="export" href="#">Export review JSON</a></p><button id="preview-share" class="primary">Preview possible contribution</button></aside><main id="main"><p>Loading local project…</p></main></div>
<script>
const token=new URLSearchParams(location.search).get('token')||'';let project=null;let activeStem=null;let playhead=0;const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,options={}){const join=path.includes('?')?'&':'?';const response=await fetch(path+join+'token='+encodeURIComponent(token),{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});if(!response.ok){let body={};try{body=await response.json()}catch{}throw new Error(body.error||`Request failed: ${response.status}`)}return response.json()}
function stateFor(stem){return project.state.stems[stem.stem_id]||{candidates:{}}}function reviewed(stem){const s=stateFor(stem);return !!s.outcome||Object.keys(s.candidates||{}).length>0}
function renderNav(){const reviewable=project.stems.filter(s=>s.candidate_count);const done=reviewable.filter(reviewed).length;document.querySelector('#progress').textContent=`Reviewed ${done} of ${reviewable.length} stems`;document.querySelector('#stem-list').innerHTML=project.stems.map(s=>`<button class="stem-link ${activeStem===s.stem_id?'active':''}" data-stem="${esc(s.stem_id)}"><b>${esc(s.role)}</b><br><span class="muted">${s.candidate_count} candidate${s.candidate_count===1?'':'s'} · ${s.candidate_count?(reviewed(s)?'decision saved':'not reviewed'):'no result yet'}</span></button>`).join('');document.querySelectorAll('[data-stem]').forEach(b=>b.onclick=()=>{activeStem=b.dataset.stem;render()})}
function setupText(){const s=project.setup;return `<section class="setup"><h2>1. Check song setup</h2><p><b>${esc(project.name)}</b></p><p>BPM: <b>${esc(s.bpm??'not inferred')}</b> · Key: <b>${esc(s.key??'not inferred')}</b> · Tuning: <b>${esc(s.tuning_hz?s.tuning_hz+' Hz':'not inferred')}</b> · Downbeat: <b>${esc(s.downbeat??'not confirmed')}</b></p><p class="muted">Confirm these values in GarageBand. Sunofriend does not treat an unconfirmed first click as the downbeat.</p></section>`}
function render(){renderNav();const stem=project.stems.find(s=>s.stem_id===activeStem)||project.stems[0];activeStem=stem?.stem_id;if(!stem){document.querySelector('#main').innerHTML=setupText()+'<p>No reviewable stems found.</p>';return}const state=stateFor(stem);const primary=stem.candidates.filter(c=>c.primary),advanced=stem.candidates.filter(c=>!c.primary);document.querySelector('#main').innerHTML=setupText()+`<section><h2>2. Choose a MIDI part</h2><p><span class="badge">${esc(stem.role)}</span> ${esc(stem.label)}</p><label>What musical role do you hear?<input id="role" value="${esc(state.role||stem.role)}" maxlength="80"> <button id="save-role" class="primary">Save role</button></label><div class="controls"><h3>Source reference</h3><audio id="source-audio" controls preload="metadata" src="${esc(stem.source_url)}"></audio><div class="loop"><label>Loop start (seconds)<input id="loop-start" type="number" min="0" step="0.1" value="0"></label><label>Loop end (blank = end)<input id="loop-end" type="number" min="0" step="0.1"></label><button class="primary" id="play-source">Play source from shared position</button></div></div>${stem.candidate_count?`<p class="notice">Listen for recognisable notes, rhythm and musical usefulness. The first three are deliberately distinct choices. Existing preview files are <b>not assumed to be level-matched</b>; use one neutral renderer before treating loudness as a preference.</p><div class="candidate-grid">${primary.map((c,i)=>candidateCard(stem,c,i,state)).join('')}</div>${advanced.length?`<details><summary>Advanced alternatives (${advanced.length})</summary><div class="candidate-grid">${advanced.map((c,i)=>candidateCard(stem,c,i+primary.length,state)).join('')}</div></details>`:''}<section class="controls"><h3>If no single candidate describes the result</h3><div class="outcomes">${[['clear_choice','There is a clear choice'],['equivalent','Equivalent'],['none_usable','None are usable'],['cannot_tell','I cannot tell']].map(([v,l])=>`<button data-outcome="${v}" class="${state.outcome?.value===v?'selected':''}">${l}</button>`).join('')}</div></section>`:'<p class="notice">No MIDI candidates were discovered for this role. Add a narrow <code>--candidate-root</code> or an explicit Workbench catalog.</p>'}<section class="setup"><h2>Next steps</h2><p>Whole-arrangement audition, complete instrument checks and one-click GarageBand pack export are intentionally shown as later increments. This first slice saves real per-stem decisions without hiding them in a web-only format.</p></section></section>`;wire(stem)}
function candidateCard(stem,c,index,state){const saved=state.candidates?.[c.candidate_id];const activeMain=state.main_candidate_id===c.candidate_id;const letter=String.fromCharCode(65+(index%26));return `<article class="card ${saved?'chosen':''}" data-card="${esc(c.candidate_id)}"><h3>Candidate ${letter}</h3>${c.preview_url?`<audio id="audio-${esc(c.candidate_id)}" controls preload="metadata" src="${esc(c.preview_url)}"></audio><button class="primary audition" data-candidate="${esc(c.candidate_id)}">Audition from shared position</button>`:`<p class="muted">No audio preview was found. Listen in GarageBand or render this MIDI through the same neutral sound as the other candidates.</p>`}<p><a href="${esc(c.midi_url)}" download>Download MIDI</a></p><details><summary>Reveal description and technical details</summary><p><b>${esc(c.label)}</b></p><p>${esc(c.description)}</p><p class="muted">Process: ${esc(c.process)}<br>MIDI SHA-256: ${esc(c.midi.sha256.slice(0,16))}…<br>Preview policy: ${esc(c.preview_policy)}</p>${c.warnings?.length?`<p class="error">${c.warnings.map(esc).join('<br>')}</p>`:''}</details><h4>Use in this project</h4><div class="actions">${[['main','Use as main'],['optional','Keep optional'],['needs_correction','Needs correction'],['reject','Reject']].map(([v,l])=>`<button data-decision="${v}" data-candidate="${esc(c.candidate_id)}" class="${v==='main'?(activeMain?'selected':''):(saved?.decision===v?'selected':'')}">${l}</button>`).join('')}</div><details ${saved?.decision==='needs_correction'?'open':''}><summary>Problem details</summary><div class="problems">${[['missing_notes','Missing notes'],['extra_notes','Extra notes'],['wrong_pitch_or_octave','Wrong pitch/octave'],['starts_early_or_late','Starts early/late'],['ends_early_or_late','Ends early/late'],['mixed_roles','Melody/accompaniment mixed'],['poor_timing','Poor timing'],['none_match','None match what I hear']].map(([v,l])=>`<label><input type="checkbox" value="${v}" ${saved?.problem_tags?.includes(v)?'checked':''}> ${l}</label>`).join('')}</div><label>Private listening note<textarea rows="3">${esc(saved?.notes||'')}</textarea></label></details><p class="muted saved">${saved?`Saved: ${esc(saved.decision)} (${esc(saved.context)})${saved.decision==='main'&&!activeMain?' — superseded by a later main choice':''}`:''}</p></article>`}
function loopBounds(){const start=Math.max(0,Number(document.querySelector('#loop-start')?.value||0));const raw=document.querySelector('#loop-end')?.value;const end=raw?Number(raw):Infinity;return{start,end:end>start?end:Infinity}}
function playAudio(audio){if(!audio)return;document.querySelectorAll('audio').forEach(a=>{if(a!==audio)a.pause()});const {start,end}=loopBounds();audio.currentTime=Math.max(start,playhead||start);audio.ontimeupdate=()=>{playhead=audio.currentTime;if(audio.currentTime>=end){audio.pause();audio.currentTime=start;playhead=start}};audio.play().catch(showError)}
function wire(stem){document.querySelector('#save-role').onclick=()=>save({event_type:'role_tag',stem_id:stem.stem_id,role:document.querySelector('#role').value});document.querySelector('#play-source').onclick=()=>playAudio(document.querySelector('#source-audio'));document.querySelectorAll('.audition').forEach(b=>b.onclick=async()=>{playAudio(document.querySelector('#audio-'+CSS.escape(b.dataset.candidate)));await save({event_type:'candidate_auditioned',stem_id:stem.stem_id,candidate_id:b.dataset.candidate,context:'solo'},false)});document.querySelectorAll('[data-decision]').forEach(b=>b.onclick=()=>{const card=b.closest('[data-card]');const tags=[...card.querySelectorAll('.problems input:checked')].map(i=>i.value);save({event_type:'candidate_decision',stem_id:stem.stem_id,candidate_id:b.dataset.candidate,decision:b.dataset.decision,context:'solo',problem_tags:tags,notes:card.querySelector('textarea').value})});document.querySelectorAll('[data-outcome]').forEach(b=>b.onclick=()=>save({event_type:'stem_outcome',stem_id:stem.stem_id,outcome:b.dataset.outcome,context:'solo'}))}
async function save(event,rerender=true){try{const response=await api('/api/events',{method:'POST',body:JSON.stringify(event)});project.state=response.state;if(rerender)render();else renderNav()}catch(error){showError(error)}}function showError(error){const main=document.querySelector('#main');main.insertAdjacentHTML('afterbegin',`<p class="error">${esc(error.message||error)}</p>`)}
document.querySelector('#export').onclick=e=>{e.preventDefault();location.href=`/api/review?token=${encodeURIComponent(token)}`};document.querySelector('#preview-share').onclick=()=>{if(!project)return;document.querySelector('#main').innerHTML=`<section class="preview"><h2>Possible contribution — disabled</h2><p>No submission endpoint exists. If a later opt-in is enabled, these are the exact metadata-only fields proposed to leave this machine:</p><pre>${esc(JSON.stringify(project.contribution_preview,null,2))}</pre><button class="primary" id="back">Back to project</button></section>`;document.querySelector('#back').onclick=render};
api('/api/project').then(value=>{project=value;activeStem=(project.stems.find(s=>s.candidate_count)||project.stems[0])?.stem_id;document.querySelector('#export').href=project.review_url;render()}).catch(showError);
</script></body></html>"""
