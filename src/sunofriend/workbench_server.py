"""Loopback-only HTTP server for the local Sunofriend Workbench."""

from __future__ import annotations

import errno
import hashlib
import hmac
import json
import math
import mimetypes
import os
import secrets
import tempfile
import threading
import webbrowser
from collections import OrderedDict
from contextlib import ExitStack
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

from .product_contract import (
    build_product_output_status,
    product_contract_document,
)
from .workbench_catalog import (
    build_workbench_catalog,
    media_files,
    public_catalog,
)
from .workbench_artifacts import (
    BALANCED_ARRANGEMENT_SCHEMA,
    WorkbenchArtifacts,
    WorkbenchPackConflictError,
    canonical_garageband_pack_basket,
    selected_candidates,
)
from .workbench_listening_master import (
    WORKBENCH_LISTENING_MASTER_SCHEMA,
    WorkbenchListeningMasterService,
)
from .workbench_master_review import (
    BALANCED_CONTROL,
    CANDIDATE_A,
    CANDIDATE_B,
    LISTENING_MASTER,
    MASTER_REVIEW_PROBLEM_TAGS,
    MAXIMUM_NOTES_CHARACTERS,
    MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE,
    WorkbenchMasterReviewConflictError,
    WorkbenchMasterReviewRevisionConflictError,
    WorkbenchMasterReviewService,
)
from .workbench_master_readiness import (
    WorkbenchMasterReadinessConflictError,
    WorkbenchMasterReadinessGateError,
    WorkbenchMasterReadinessService,
)
from .workbench_instrument_review import (
    CANDIDATE_A as INSTRUMENT_CANDIDATE_A,
    CANDIDATE_B as INSTRUMENT_CANDIDATE_B,
    INSTRUMENT_REVIEW_PROBLEM_TAGS,
    MAXIMUM_NOTES_CHARACTERS as INSTRUMENT_MAXIMUM_NOTES_CHARACTERS,
    MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE as INSTRUMENT_MAXIMUM_PROBLEM_TAGS,
    SOURCE_REFERENCE,
    WorkbenchInstrumentReviewConflictError,
    WorkbenchInstrumentReviewRevisionConflictError,
    WorkbenchInstrumentReviewService,
)
from .workbench_instrument_coverage import (
    PROBE_BPM,
    keys_coverage_contract,
    validate_keys_coverage_report,
)
from .workbench_instrument_policy import (
    complete_instrument_programs,
    complete_instrument_roles,
)
from .workbench_clips import (
    WorkbenchClipService,
    public_artifact as public_clip_artifact,
)
from .workbench_correction import (
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionNotFoundError,
    WorkbenchClipCorrectionService,
)
from .workbench_reuse import (
    WorkbenchClipReuseConflictError,
    WorkbenchClipReuseNotFoundError,
    WorkbenchClipReuseService,
)
from .workbench_transform import (
    WorkbenchClipTransformConflictError,
    WorkbenchClipTransformNotFoundError,
    WorkbenchClipTransformService,
)
from .workbench_store import (
    WorkbenchPackStateConflictError,
    WorkbenchStore,
    default_workbench_state_dir,
    fold_workbench_events,
)
from .workbench_home import build_workbench_home
from .workbench_privacy import path_free_browser_state, path_free_role
from .workbench_developer import (
    WorkbenchDeveloperTrace,
    artifact_cache_summary,
    build_developer_snapshot,
    developer_code_step_for_route,
    developer_operation_for_route,
    trace_response_facts,
)
from .workbench_timeline import (
    TimelineArtifactChangedError,
    build_arrangement_timeline,
    build_stem_timeline,
)


_MAX_REQUEST_BYTES = 64 * 1024
_MAX_GENERATED_MEDIA_RECORDS = 768
_MAX_DECODED_STREAM_PLANS = 16
_MAX_INSTRUMENT_REVIEW_CONTEXTS = 128
_INSTRUMENT_REVIEW_ROLES = frozenset(complete_instrument_roles())
_MAX_DEVELOPER_SNAPSHOT_BYTES = 512 * 1024
_CLIP_CORRECTION_ROUTES = frozenset(
    {
        "/api/clip-note-correction-window",
        "/api/clip-note-correction-projection",
        "/api/clip-note-correction-action",
    }
)


class WorkbenchSelectionConflictError(ValueError):
    """The requested artifact no longer matches saved Workbench choices."""


def _read_verified_immutable_bytes(handle: Any, record: Mapping[str, Any]) -> bytes:
    """Read one pinned response into bytes that cannot drift while served."""

    payload = handle.read()
    if len(payload) != record.get("bytes") or hashlib.sha256(
        payload
    ).hexdigest() != str(record.get("sha256", "")):
        raise ValueError("pinned file bytes changed")
    return payload


def _freeze_verified_immutable_file(
    handle: Any,
    record: Mapping[str, Any],
) -> Any:
    """Copy verified bytes to a disk-backed anonymous snapshot for serving.

    Balanced auditions can be hundreds of MiB. A TemporaryFile keeps the
    post-verification response immutable without loading the full WAV into
    memory, and Range requests seek only within that frozen snapshot.
    """

    snapshot = tempfile.TemporaryFile(mode="w+b")
    digest = hashlib.sha256()
    size = 0
    try:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            snapshot.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        if size != record.get("bytes") or digest.hexdigest() != str(
            record.get("sha256", "")
        ):
            raise ValueError("pinned file bytes changed")
        snapshot.seek(0)
        return snapshot
    except Exception:
        snapshot.close()
        raise


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


def _require_lowercase_sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 value")
    return value


def _workbench_master_reviewer_key(project_id: Any) -> str:
    """Derive one stable local Workbench reviewer key without browser storage."""

    if not isinstance(project_id, str) or not project_id:
        raise ValueError("Workbench project identity is invalid")
    payload = (
        f"sunofriend.workbench-listening-master-reviewer.v1\0{project_id}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _workbench_instrument_reviewer_key(project_id: Any) -> str:
    """Derive a separate stable local reviewer key for instrument feedback."""

    if not isinstance(project_id, str) or not project_id:
        raise ValueError("Workbench project identity is invalid")
    payload = (f"sunofriend.workbench-instrument-reviewer.v1\0{project_id}").encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _clip_browse_query(query_string: str) -> dict[str, Any]:
    """Decode one bounded, path-free Clip search query."""

    if len(query_string.encode("utf-8")) > 8192:
        raise ValueError("Clip search query is too large")
    parsed = parse_qs(
        query_string,
        keep_blank_values=True,
        max_num_fields=64,
    )
    allowed = {
        "token",
        "text",
        "role",
        "key",
        "bpm",
        "bpm_tolerance",
        "tag",
        "limit",
        "offset",
    }
    if set(parsed) - allowed:
        raise ValueError("unexpected Clip search field")
    for key, values in parsed.items():
        if key != "tag" and len(values) != 1:
            raise ValueError("duplicate Clip search field")

    def optional_text(name: str) -> str | None:
        value = parsed.get(name, [""])[0].strip()
        return value or None

    def optional_float(name: str) -> float | None:
        value = optional_text(name)
        return None if value is None else float(value)

    def integer(name: str, default: int) -> int:
        value = optional_text(name)
        if value is None:
            return default
        if value.startswith("+") or not value.isdigit():
            raise ValueError("Clip paging values must be decimal integers")
        return int(value)

    tags = tuple(value.strip() for value in parsed.get("tag", []) if value.strip())
    if len(tags) != len(parsed.get("tag", [])):
        raise ValueError("Clip tags must not be empty")
    if len(tags) > 32:
        raise ValueError("Clip tag filter is too large")
    tolerance = optional_float("bpm_tolerance")
    return {
        "text": optional_text("text"),
        "role": optional_text("role"),
        "key": optional_text("key"),
        "bpm": optional_float("bpm"),
        "bpm_tolerance": 0.01 if tolerance is None else tolerance,
        "tags": tags,
        "limit": integer("limit", 50),
        "offset": integer("offset", 0),
    }


def _mapping_contains_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(
            _mapping_contains_key(item, key) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_mapping_contains_key(item, key) for item in value)
    return False


def _current_stem_role(
    catalog: Mapping[str, Any], current: Mapping[str, Any], stem_id: str
) -> str:
    """Resolve one server-owned path-free role from a saved-state snapshot."""

    catalog_stem = next(
        (
            stem
            for stem in catalog.get("stems", [])
            if isinstance(stem, Mapping) and str(stem.get("stem_id")) == stem_id
        ),
        None,
    )
    if catalog_stem is None:
        raise ValueError("unknown workbench stem_id")
    states = current.get("stems", {})
    state = states.get(stem_id, {}) if isinstance(states, Mapping) else {}
    saved_role = state.get("role") if isinstance(state, Mapping) else None
    return path_free_role(saved_role or catalog_stem.get("role"))[0]


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
        listening_masters: WorkbenchListeningMasterService,
        master_reviews: WorkbenchMasterReviewService,
        master_readiness: WorkbenchMasterReadinessService,
        instrument_reviews: WorkbenchInstrumentReviewService,
        token: str,
        developer_inspector: bool = False,
        clip_service: WorkbenchClipService | None = None,
        clip_reuse_service: WorkbenchClipReuseService | None = None,
        clip_transform_service: WorkbenchClipTransformService | None = None,
        clip_correction_service: WorkbenchClipCorrectionService | None = None,
    ) -> None:
        self.catalog = catalog
        self.store = store
        self.artifacts = artifacts
        self.listening_masters = listening_masters
        self.master_reviews = master_reviews
        self.master_readiness = master_readiness
        self.instrument_reviews = instrument_reviews
        self.token = token
        self.developer_inspector = bool(developer_inspector)
        self.clip_service = clip_service
        self.clip_reuse_service = clip_reuse_service
        self.clip_transform_service = clip_transform_service
        self.clip_correction_service = clip_correction_service
        self.developer_trace = (
            WorkbenchDeveloperTrace() if self.developer_inspector else None
        )
        self.media = media_files(catalog)
        self.catalog_media_ids = frozenset(self.media)
        self.generated_media_ids: OrderedDict[str, None] = OrderedDict()
        self.decoded_stream_plans: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.instrument_review_contexts: OrderedDict[str, dict[str, str]] = (
            OrderedDict()
        )
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
    developer_inspector: bool = False,
    clip_library_path: str | Path | None = None,
    phase6_acceptance_path: str | Path | None = None,
    phase6_pack_path: str | Path | None = None,
    enable_clip_reuse_plan: bool = False,
    enable_clip_transforms: bool = False,
    enable_clip_corrections: bool = False,
) -> WorkbenchHTTPServer:
    """Create, but do not start, a loopback-only Workbench server."""

    if not 0 <= int(port) <= 65535:
        raise ValueError("workbench port must be between 0 and 65535")
    destination = (
        Path(state_dir).expanduser().resolve()
        if state_dir is not None
        else default_workbench_state_dir(catalog)
    )
    phase6_values = (
        clip_library_path,
        phase6_acceptance_path,
        phase6_pack_path,
    )
    if any(value is not None for value in phase6_values) and not all(
        value is not None for value in phase6_values
    ):
        raise ValueError(
            "--clip-library, --phase6-acceptance and --phase6-pack must be supplied together"
        )
    if enable_clip_reuse_plan and not all(value is not None for value in phase6_values):
        raise ValueError(
            "--enable-clip-reuse-plan requires --clip-library, "
            "--phase6-acceptance and --phase6-pack"
        )
    if enable_clip_transforms and not all(value is not None for value in phase6_values):
        raise ValueError(
            "--enable-clip-transforms requires --clip-library, "
            "--phase6-acceptance and --phase6-pack"
        )
    if enable_clip_corrections and not all(
        value is not None for value in phase6_values
    ):
        raise ValueError(
            "--enable-clip-corrections requires --clip-library, "
            "--phase6-acceptance and --phase6-pack"
        )
    if enable_clip_reuse_plan and enable_clip_transforms:
        raise ValueError(
            "--enable-clip-reuse-plan and --enable-clip-transforms are mutually exclusive"
        )
    if enable_clip_corrections and (enable_clip_reuse_plan or enable_clip_transforms):
        raise ValueError(
            "--enable-clip-corrections, --enable-clip-reuse-plan and "
            "--enable-clip-transforms are mutually exclusive"
        )
    clip_service = None
    if all(value is not None for value in phase6_values):
        clip_service = WorkbenchClipService.open(
            acceptance_result_path=phase6_acceptance_path,
            garageband_pack_path=phase6_pack_path,
            library_root=clip_library_path,
            cache_root=destination / "phase6-clip-cache",
            soundfont_path=soundfont_path,
        )
    destination.mkdir(parents=True, exist_ok=True)
    store = WorkbenchStore(destination / "workbench.sqlite3")
    artifacts = WorkbenchArtifacts(
        destination / "artifacts", soundfont_path=soundfont_path
    )
    listening_masters = WorkbenchListeningMasterService(destination / "artifacts")
    master_reviews = WorkbenchMasterReviewService(
        destination / "listening-master-reviews"
    )
    master_readiness = WorkbenchMasterReadinessService(
        destination / "listening-master-readiness",
        master_reviews,
    )
    instrument_reviews = WorkbenchInstrumentReviewService(
        destination / "instrument-reviews"
    )
    clip_reuse_service = (
        WorkbenchClipReuseService.open(
            clip_service=clip_service,
            catalog=catalog,
            store_path=destination / "phase6-reuse" / "reuse.sqlite3",
        )
        if enable_clip_reuse_plan and clip_service is not None
        else None
    )
    clip_transform_service = (
        WorkbenchClipTransformService.open(
            clip_service=clip_service,
            library_root=clip_library_path,
        )
        if enable_clip_transforms and clip_service is not None
        else None
    )
    clip_correction_service = (
        WorkbenchClipCorrectionService.open(
            clip_service=clip_service,
            library_root=clip_library_path,
        )
        if enable_clip_corrections and clip_service is not None
        else None
    )
    session_token = token or secrets.token_urlsafe(32)
    return WorkbenchHTTPServer(
        ("127.0.0.1", int(port)),
        catalog=catalog,
        store=store,
        artifacts=artifacts,
        listening_masters=listening_masters,
        master_reviews=master_reviews,
        master_readiness=master_readiness,
        instrument_reviews=instrument_reviews,
        token=session_token,
        developer_inspector=developer_inspector,
        clip_service=clip_service,
        clip_reuse_service=clip_reuse_service,
        clip_transform_service=clip_transform_service,
        clip_correction_service=clip_correction_service,
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
    developer_inspector: bool = False,
    clip_library_path: str | Path | None = None,
    phase6_acceptance_path: str | Path | None = None,
    phase6_pack_path: str | Path | None = None,
    enable_clip_reuse_plan: bool = False,
    enable_clip_transforms: bool = False,
    enable_clip_corrections: bool = False,
) -> dict[str, Any]:
    """Build a catalogue and inspect, export, or serve the local workbench."""

    if export_review_path is not None and (inspect_only or open_browser):
        raise ValueError("--export-review cannot be combined with --inspect or --open")
    phase6_values = (
        clip_library_path,
        phase6_acceptance_path,
        phase6_pack_path,
    )
    if any(value is not None for value in phase6_values) and not all(
        value is not None for value in phase6_values
    ):
        raise ValueError(
            "--clip-library, --phase6-acceptance and --phase6-pack must be supplied together"
        )
    if enable_clip_reuse_plan and not all(value is not None for value in phase6_values):
        raise ValueError(
            "--enable-clip-reuse-plan requires --clip-library, "
            "--phase6-acceptance and --phase6-pack"
        )
    if enable_clip_transforms and not all(value is not None for value in phase6_values):
        raise ValueError(
            "--enable-clip-transforms requires --clip-library, "
            "--phase6-acceptance and --phase6-pack"
        )
    if enable_clip_corrections and not all(
        value is not None for value in phase6_values
    ):
        raise ValueError(
            "--enable-clip-corrections requires --clip-library, "
            "--phase6-acceptance and --phase6-pack"
        )
    if enable_clip_reuse_plan and enable_clip_transforms:
        raise ValueError(
            "--enable-clip-reuse-plan and --enable-clip-transforms are mutually exclusive"
        )
    if enable_clip_corrections and (enable_clip_reuse_plan or enable_clip_transforms):
        raise ValueError(
            "--enable-clip-corrections, --enable-clip-reuse-plan and "
            "--enable-clip-transforms are mutually exclusive"
        )
    if any(value is not None for value in phase6_values) and (
        inspect_only or export_review_path is not None
    ):
        raise ValueError(
            "Phase 6 Clip Library options require the live loopback Workbench"
        )

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
        developer_inspector=developer_inspector,
        clip_library_path=clip_library_path,
        phase6_acceptance_path=phase6_acceptance_path,
        phase6_pack_path=phase6_pack_path,
        enable_clip_reuse_plan=enable_clip_reuse_plan,
        enable_clip_transforms=enable_clip_transforms,
        enable_clip_corrections=enable_clip_corrections,
    )
    print("Sunofriend Workbench")
    print("Local — nothing is being uploaded")
    print(server.url, flush=True)
    print(f"Decisions: {server.store.path}", flush=True)
    if developer_inspector:
        print("Developer Inspector: enabled (read-only, memory-only trace)", flush=True)
    if server.clip_service is not None:
        print(
            (
                "Phase 6 Clip Library: enabled (verified; source Clips immutable)"
                if (
                    server.clip_transform_service is not None
                    or server.clip_correction_service is not None
                )
                else "Phase 6 Clip Library: enabled (verified, read-only, no transforms)"
            ),
            flush=True,
        )
    if server.clip_reuse_service is not None:
        print(
            "Phase 6 Clip reuse plan: enabled (separate proposal, explicit writes only)",
            flush=True,
        )
    if server.clip_transform_service is not None:
        print(
            "Phase 6 Clip transforms: enabled (preview first, immutable versions only)",
            flush=True,
        )
    if server.clip_correction_service is not None:
        print(
            "Phase 6 Clip corrections: enabled (pitch, attack velocity, exact note deletion, bounded note-onset shift, or bounded note-end/duration; preview first, immutable versions only)",
            flush=True,
        )
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
        if parsed.path == "/workbench-visualization.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_visualization_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path == "/workbench-transport.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_transport_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path == "/workbench-clips.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_clips_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path == "/workbench-developer.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_developer_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path == "/workbench-master-review.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_master_review_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path == "/workbench-instrument-review.js":
            self._bytes(
                HTTPStatus.OK,
                _workbench_instrument_review_bytes(),
                "text/javascript; charset=utf-8",
            )
            return
        if parsed.path.startswith("/phrase-review/"):
            self._serve_phrase_review(parsed.path)
            return
        if not self._authorised(parsed):
            self._error(HTTPStatus.FORBIDDEN, "invalid workbench session token")
            return
        if parsed.path == "/api/developer-snapshot":
            if not self.server.developer_inspector:
                self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                return
            try:
                self._json(HTTPStatus.OK, self._developer_snapshot_payload())
            except (OSError, RuntimeError, ValueError):
                # Do not place private exception text in this diagnostic surface.
                self._error(
                    HTTPStatus.BAD_REQUEST,
                    "developer snapshot is temporarily unavailable",
                )
            return
        self._start_developer_trace("GET", parsed.path)
        if parsed.path == "/":
            self._bytes(
                HTTPStatus.OK,
                _workbench_html_bytes(),
                "text/html; charset=utf-8",
            )
            return
        if parsed.path == "/api/project":
            try:
                self._json(HTTPStatus.OK, self._project_payload())
            except (OSError, RuntimeError, ValueError):
                self._error(
                    HTTPStatus.CONFLICT,
                    "Workbench evidence changed or is unavailable; restart the Workbench",
                )
            return
        if parsed.path == "/api/clips":
            service = self.server.clip_service
            if service is None:
                self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                return
            try:
                query = _clip_browse_query(parsed.query)
                self._json(HTTPStatus.OK, service.browse(**query))
            except (TypeError, ValueError):
                self._error(HTTPStatus.BAD_REQUEST, "invalid Clip Library search")
            except (OSError, RuntimeError):
                self._error(
                    HTTPStatus.CONFLICT,
                    "Clip Library evidence changed or is unavailable; restart the Workbench",
                )
            return
        if parsed.path.startswith("/api/clips/"):
            service = self.server.clip_service
            if service is None:
                self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                return
            encoded_clip_id = parsed.path[len("/api/clips/") :]
            try:
                clip_id = unquote(encoded_clip_id, errors="strict")
                if not clip_id or "/" in clip_id:
                    raise ValueError("invalid clip identity")
                with self.server.state_lock:
                    detail = service.detail(clip_id)
                    reuse_service = self.server.clip_reuse_service
                    if reuse_service is not None:
                        detail = {
                            **detail,
                            "reuse_compatibility": reuse_service.compatibility(clip_id),
                        }
                    correction_service = self.server.clip_correction_service
                    if correction_service is not None:
                        correction_summary = correction_service.correction_summary(
                            clip_id
                        )
                        if correction_summary is not None:
                            detail = {
                                **detail,
                                "correction_summary": correction_summary,
                            }
                self._json(HTTPStatus.OK, detail)
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "Clip not found")
            except WorkbenchClipCorrectionNotFoundError:
                self._error(HTTPStatus.NOT_FOUND, "Clip not found")
            except WorkbenchClipCorrectionConflictError:
                self._error(
                    HTTPStatus.CONFLICT,
                    "Clip correction evidence changed or is unavailable; restart the Workbench",
                )
            except WorkbenchClipCorrectionError:
                self._error(
                    HTTPStatus.CONFLICT,
                    "Clip correction lineage is invalid or unavailable; restart the Workbench",
                )
            except (TypeError, UnicodeDecodeError, ValueError):
                self._error(HTTPStatus.BAD_REQUEST, "invalid Clip identity")
            except (OSError, RuntimeError):
                self._error(
                    HTTPStatus.CONFLICT,
                    "Clip Library evidence changed or is unavailable; restart the Workbench",
                )
            return
        if parsed.path == "/api/clip-reuse-plan":
            service = self.server.clip_reuse_service
            if service is None:
                self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                return
            try:
                self._json(HTTPStatus.OK, {"plan": service.plan()})
            except (OSError, RuntimeError):
                self._error(
                    HTTPStatus.CONFLICT,
                    "Clip reuse evidence changed or is unavailable; restart the Workbench",
                )
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
        if parsed.path == "/api/instrument-review-plan":
            try:
                with self.server.state_lock:
                    plan = self._instrument_review_plan()
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
        if parsed.path == "/api/listening-master-review-export":
            query = parse_qs(parsed.query, keep_blank_values=True)
            kind = query.get("kind", [""])[0]
            review_id = query.get("review_id", [""])[0]
            try:
                if kind == "review":
                    document = self.server.master_reviews.review(review_id)
                    filename = "sunofriend-listening-master-blind-review.json"
                elif kind == "result":
                    document = self.server.master_reviews.resolution(review_id)
                    if document is None:
                        raise ValueError(
                            "Listening Master review identities have not been resolved"
                        )
                    filename = "sunofriend-listening-master-review-result.json"
                else:
                    raise ValueError("Listening Master review download kind is invalid")
            except (OSError, RuntimeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, document, filename=filename)
            return
        if parsed.path == "/api/listening-master-readiness-export":
            query = parse_qs(parsed.query, keep_blank_values=True)
            readiness_review_id = query.get("readiness_review_id", [""])[0]
            try:
                document = self.server.master_readiness.review(readiness_review_id)
            except (OSError, RuntimeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(
                HTTPStatus.OK,
                document,
                filename="sunofriend-listening-master-native-readiness-review.json",
            )
            return
        if parsed.path == "/api/instrument-review-export":
            try:
                query = parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                    max_num_fields=8,
                )
                if set(query) != {"token", "kind", "review_id"} or any(
                    len(values) != 1 for values in query.values()
                ):
                    raise ValueError("instrument review export query is invalid")
                kind = query["kind"][0]
                review_id = _require_lowercase_sha256(
                    query["review_id"][0],
                    label="instrument review export review_id",
                )
                if kind == "review":
                    document = self.server.instrument_reviews.review(review_id)
                    filename = "sunofriend-instrument-blind-review.json"
                elif kind == "result":
                    document = self.server.instrument_reviews.resolution(review_id)
                    if document is None:
                        raise ValueError(
                            "instrument review identities have not been resolved"
                        )
                    filename = "sunofriend-instrument-review-result.json"
                else:
                    raise ValueError("instrument review export kind is invalid")
                if _mapping_contains_key(document, "path"):
                    raise ValueError("instrument review export exposed a private path")
            except (OSError, RuntimeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(HTTPStatus.OK, document, filename=filename)
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
            "/api/decoded-arrangement-loop",
            "/api/decoded-arrangement-stream",
            "/api/decoded-arrangement-chunk",
            "/api/arrangement",
            "/api/balanced-arrangement",
            "/api/listening-master",
            "/api/listening-master-review/prepare",
            "/api/listening-master-review",
            "/api/listening-master-review/resolve",
            "/api/listening-master-readiness/prepare",
            "/api/listening-master-readiness",
            "/api/instrument-review/prepare",
            "/api/instrument-review",
            "/api/instrument-review/resolve",
            "/api/garageband-export",
            "/api/garageband-pack-basket",
            "/api/garageband-pack",
            "/api/clip-artifact",
            "/api/clip-reuse-action",
            "/api/clip-transform-projection",
            "/api/clip-transform-action",
            "/api/clip-note-correction-window",
            "/api/clip-note-correction-projection",
            "/api/clip-note-correction-action",
        }:
            self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
            return
        self._start_developer_trace("POST", parsed.path)
        if (
            parsed.path
            in {
                "/api/clip-transform-projection",
                "/api/clip-transform-action",
            }
            and self.server.clip_transform_service is None
        ):
            self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
            return
        if (
            parsed.path in _CLIP_CORRECTION_ROUTES
            and self.server.clip_correction_service is None
        ):
            self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
            return
        try:
            try:
                request = self._request_json()
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                if parsed.path in {
                    "/api/clip-transform-projection",
                    "/api/clip-transform-action",
                }:
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Clip transform request",
                    )
                    return
                if parsed.path in _CLIP_CORRECTION_ROUTES:
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Clip note correction request",
                    )
                    return
                if parsed.path == "/api/clip-reuse-action":
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Clip reuse action",
                    )
                    return
                raise
            self._developer_checkpoint("validate", "validate")
            if parsed.path in _CLIP_CORRECTION_ROUTES:
                service = self.server.clip_correction_service
                if service is None:
                    self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                    return
                try:
                    self._developer_application_invoked = True
                    with self.server.state_lock:
                        if parsed.path == "/api/clip-note-correction-window":
                            document = service.window(request)
                            response_key = "window"
                            status = HTTPStatus.OK
                        elif parsed.path == "/api/clip-note-correction-projection":
                            document = service.preview(request)
                            response_key = "projection"
                            status = HTTPStatus.OK
                        else:
                            document = service.create(request)
                            response_key = "result"
                            status = HTTPStatus.CREATED
                    self._json(status, {response_key: document})
                except WorkbenchClipCorrectionNotFoundError:
                    self._error(HTTPStatus.NOT_FOUND, "Clip or note not found")
                except WorkbenchClipCorrectionConflictError:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip correction evidence changed; load the note window and preview again",
                    )
                except (OverflowError, TypeError, ValueError):
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Clip note correction request",
                    )
                except (OSError, RuntimeError):
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip correction evidence changed or is unavailable; restart the Workbench",
                    )
                return
            if parsed.path in {
                "/api/clip-transform-projection",
                "/api/clip-transform-action",
            }:
                service = self.server.clip_transform_service
                if service is None:
                    self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                    return
                try:
                    with self.server.state_lock:
                        if parsed.path == "/api/clip-transform-projection":
                            projection = service.preview(request)
                        else:
                            result = service.create(request)
                    if parsed.path == "/api/clip-transform-projection":
                        self._json(HTTPStatus.OK, {"projection": projection})
                    else:
                        self._json(HTTPStatus.CREATED, {"result": result})
                except WorkbenchClipTransformNotFoundError:
                    self._error(HTTPStatus.NOT_FOUND, "Clip not found")
                except WorkbenchClipTransformConflictError:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip transform preview changed; preview again before creating a version",
                    )
                except (OverflowError, TypeError, ValueError):
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Clip transform request",
                    )
                except (OSError, RuntimeError):
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip transform evidence changed or is unavailable; restart the Workbench",
                    )
                return
            if parsed.path == "/api/clip-reuse-action":
                service = self.server.clip_reuse_service
                if service is None:
                    self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                    return
                try:
                    with self.server.state_lock:
                        result = service.apply(request)
                    self._json(HTTPStatus.CREATED, result)
                except WorkbenchClipReuseNotFoundError as exc:
                    self._error(
                        HTTPStatus.NOT_FOUND,
                        "Clip not found"
                        if exc.kind == "clip"
                        else "Clip reuse placement not found",
                    )
                except WorkbenchClipReuseConflictError:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip reuse plan changed; reload the proposal before trying again",
                    )
                except (OverflowError, TypeError, ValueError):
                    self._error(HTTPStatus.BAD_REQUEST, "invalid Clip reuse action")
                except (OSError, RuntimeError):
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip reuse evidence changed or is unavailable; restart the Workbench",
                    )
                return
            if parsed.path == "/api/clip-artifact":
                service = self.server.clip_service
                if service is None:
                    self._error(HTTPStatus.NOT_FOUND, "workbench route not found")
                    return
                try:
                    _require_exact_request_keys(
                        request,
                        {"clip_id", "include_preview"},
                        label="Clip artifact",
                    )
                    artifact = service.prepare_artifact(
                        request.get("clip_id"),
                        include_preview=request.get("include_preview"),
                    )
                    self._json(
                        HTTPStatus.OK,
                        {"artifact": self._public_clip_artifact(artifact)},
                    )
                except KeyError:
                    self._error(HTTPStatus.NOT_FOUND, "Clip not found")
                except (TypeError, ValueError):
                    self._error(HTTPStatus.BAD_REQUEST, "invalid Clip artifact request")
                except (OSError, RuntimeError):
                    self._error(
                        HTTPStatus.CONFLICT,
                        "Clip evidence changed or the local renderer is unavailable",
                    )
                return
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
                stem_id = str(request.get("stem_id", ""))
                candidate_id = str(request.get("candidate_id", ""))
                with self.server.state_lock:
                    initial_state = self.server.store.current_state(self.server.catalog)
                    initial_role = _current_stem_role(
                        self.server.catalog, initial_state, stem_id
                    )
                artifact = self.server.artifacts.render_candidate_preview(
                    self.server.catalog,
                    stem_id,
                    candidate_id,
                    role_override=initial_role,
                )
                with self.server.state_lock:
                    final_state = self.server.store.current_state(self.server.catalog)
                    final_role = _current_stem_role(
                        self.server.catalog, final_state, stem_id
                    )
                    if final_role != initial_role:
                        raise WorkbenchSelectionConflictError(
                            "the stem role changed while its neutral preview was "
                            "being prepared; reload and retry"
                        )
                    public_preview = self._public_artifact(artifact)
                self._json(
                    HTTPStatus.OK,
                    {"preview": public_preview},
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
            if parsed.path == "/api/decoded-arrangement-loop":
                _require_exact_request_keys(
                    request,
                    {
                        "selection_manifest_sha256",
                        "start_seconds",
                        "end_seconds",
                    },
                    label="decoded arrangement loop",
                )
                requested_manifest_sha256 = _require_lowercase_sha256(
                    request.get("selection_manifest_sha256"),
                    label="decoded arrangement selection_manifest_sha256",
                )
                with self.server.state_lock:
                    initial_state = self.server.store.current_state(self.server.catalog)
                    initial_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            initial_state,
                        )
                    )
                    if (
                        requested_manifest_sha256
                        != initial_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed; reload it before "
                            "preparing a precise loop"
                        )
                artifact = self.server.artifacts.prepare_decoded_arrangement_loop(
                    self.server.catalog,
                    initial_state,
                    requested_manifest_sha256,
                    request.get("start_seconds"),
                    request.get("end_seconds"),
                )
                # Rendering missing neutral sounds can take long enough for another
                # local tab to save a new decision. Register no stale media tokens.
                with self.server.state_lock:
                    final_state = self.server.store.current_state(self.server.catalog)
                    final_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            final_state,
                        )
                    )
                    if (
                        requested_manifest_sha256
                        != final_manifest["selection_manifest_sha256"]
                        or artifact.get("selection_manifest_sha256")
                        != requested_manifest_sha256
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed while its precise loop "
                            "was being prepared; reload and retry"
                        )
                    public_loop = self._public_decoded_arrangement_loop(artifact)
                self._json(HTTPStatus.OK, {"loop": public_loop})
                return
            if parsed.path == "/api/decoded-arrangement-stream":
                _require_exact_request_keys(
                    request,
                    {"selection_manifest_sha256", "preset"},
                    label="decoded arrangement stream",
                )
                requested_manifest_sha256 = _require_lowercase_sha256(
                    request.get("selection_manifest_sha256"),
                    label="decoded arrangement selection_manifest_sha256",
                )
                preset = request.get("preset")
                if preset not in {
                    "source-only",
                    "selected-midi",
                    "hybrid",
                    "main-only",
                }:
                    raise ValueError(
                        "decoded arrangement preset must be exactly source-only, "
                        "selected-midi, hybrid, or main-only"
                    )
                with self.server.state_lock:
                    initial_state = self.server.store.current_state(self.server.catalog)
                    initial_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            initial_state,
                        )
                    )
                    if (
                        requested_manifest_sha256
                        != initial_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed; reload it before "
                            "preparing full-song playback"
                        )
                try:
                    artifact = self.server.artifacts.prepare_decoded_arrangement_stream(
                        self.server.catalog,
                        initial_state,
                        requested_manifest_sha256,
                        str(preset),
                    )
                except ValueError as exc:
                    with self.server.state_lock:
                        failed_state = self.server.store.current_state(
                            self.server.catalog
                        )
                        failed_manifest = self.server.artifacts.decoded_arrangement_selection_manifest(  # noqa: E501
                            self.server.catalog,
                            failed_state,
                        )
                    if (
                        requested_manifest_sha256
                        != failed_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed while full-song "
                            "playback was being prepared; reload and retry"
                        ) from exc
                    raise
                with self.server.state_lock:
                    final_state = self.server.store.current_state(self.server.catalog)
                    final_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            final_state,
                        )
                    )
                    if (
                        requested_manifest_sha256
                        != final_manifest["selection_manifest_sha256"]
                        or artifact.get("selection_manifest_sha256")
                        != requested_manifest_sha256
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed while full-song "
                            "playback was being prepared; reload and retry"
                        )
                    public_stream = self._public_decoded_arrangement_stream(artifact)
                    self._register_decoded_stream_plan(public_stream)
                self._json(HTTPStatus.OK, {"stream": public_stream})
                return
            if parsed.path == "/api/decoded-arrangement-chunk":
                _require_exact_request_keys(
                    request,
                    {"stream_sha256", "chunk_index"},
                    label="decoded arrangement chunk",
                )
                stream_sha256 = _require_lowercase_sha256(
                    request.get("stream_sha256"),
                    label="decoded arrangement stream_sha256",
                )
                chunk_index = request.get("chunk_index")
                if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
                    raise ValueError(
                        "decoded arrangement chunk_index must be an integer"
                    )
                with self.server.state_lock:
                    plan = self.server.decoded_stream_plans.get(stream_sha256)
                    if not isinstance(plan, Mapping):
                        raise ValueError(
                            "decoded arrangement stream is not active; prepare its "
                            "full-song preset again"
                        )
                    plan = dict(plan)
                    initial_state = self.server.store.current_state(self.server.catalog)
                    initial_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            initial_state,
                        )
                    )
                    if (
                        plan.get("selection_manifest_sha256")
                        != initial_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed; reload it before "
                            "continuing full-song playback"
                        )
                try:
                    artifact = self.server.artifacts.prepare_decoded_arrangement_chunk(
                        self.server.catalog,
                        initial_state,
                        stream_sha256,
                        chunk_index,
                    )
                except ValueError as exc:
                    with self.server.state_lock:
                        failed_state = self.server.store.current_state(
                            self.server.catalog
                        )
                        failed_manifest = self.server.artifacts.decoded_arrangement_selection_manifest(  # noqa: E501
                            self.server.catalog,
                            failed_state,
                        )
                    if (
                        plan.get("selection_manifest_sha256")
                        != failed_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed while the next "
                            "full-song chunk was being prepared; reload and retry"
                        ) from exc
                    raise
                with self.server.state_lock:
                    final_state = self.server.store.current_state(self.server.catalog)
                    final_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            final_state,
                        )
                    )
                    if (
                        plan.get("selection_manifest_sha256")
                        != final_manifest["selection_manifest_sha256"]
                        or artifact.get("stream_sha256") != stream_sha256
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed while the next "
                            "full-song chunk was being prepared; reload and retry"
                        )
                    self._refresh_decoded_stream_plan(stream_sha256, plan)
                    public_chunk = self._public_decoded_arrangement_chunk(artifact)
                self._json(HTTPStatus.OK, {"chunk": public_chunk})
                return
            if parsed.path == "/api/instrument-review/prepare":
                _require_exact_request_keys(
                    request,
                    {
                        "selection_manifest_sha256",
                        "stem_id",
                        "candidate_id",
                        "midi_sha256",
                        "start_seconds",
                        "end_seconds",
                    },
                    label="instrument review preparation",
                )
                with self.server.state_lock:
                    initial_context = self._instrument_review_context(request)
                prepared = self.server.instrument_reviews.prepare(
                    context=initial_context,
                    start_seconds=request.get("start_seconds"),
                    end_seconds=request.get("end_seconds"),
                    reviewer_session_key=_workbench_instrument_reviewer_key(
                        self.server.catalog["project_id"]
                    ),
                )
                # Rendering can outlive another tab's selection change. Only
                # publish/register media after the exact lane pins still resolve.
                with self.server.state_lock:
                    final_context = self._instrument_review_context(request)
                    self._require_same_instrument_review_context(
                        initial_context,
                        final_context,
                    )
                    public_review = self._public_instrument_review(
                        prepared,
                        context=final_context,
                    )
                    self._remember_instrument_review_context(
                        str(public_review["comparison_sha256"]),
                        final_context,
                    )
                self._json(
                    HTTPStatus.OK,
                    {"comparison": public_review},
                )
                return
            if parsed.path == "/api/instrument-review":
                _require_exact_request_keys(
                    request,
                    {
                        "comparison_sha256",
                        "expected_revision",
                        "heard",
                        "choice",
                        "problem_tags",
                        "notes",
                    },
                    label="instrument review",
                )
                comparison_sha256 = _require_lowercase_sha256(
                    request.get("comparison_sha256"),
                    label="instrument review comparison_sha256",
                )
                with self.server.state_lock:
                    context = self._instrument_review_context_for_comparison(
                        comparison_sha256
                    )
                    completed = self.server.instrument_reviews.complete(
                        context=context,
                        comparison_sha256=comparison_sha256,
                        reviewer_session_key=_workbench_instrument_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                        expected_revision=request.get("expected_revision"),
                        heard=request.get("heard"),
                        choice=request.get("choice"),
                        problem_tags=request.get("problem_tags"),
                        notes=request.get("notes"),
                    )
                    prepared = self.server.instrument_reviews.current(
                        context=context,
                        comparison_sha256=comparison_sha256,
                        reviewer_session_key=_workbench_instrument_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                    )
                    current_review = prepared.get("current_review")
                    if not isinstance(current_review, Mapping) or current_review.get(
                        "review_id"
                    ) != completed.get("review_id"):
                        raise RuntimeError("instrument review publication changed")
                    public_review = self._public_instrument_review(
                        prepared,
                        context=context,
                    )
                self._json(
                    HTTPStatus.OK,
                    {"comparison": public_review},
                )
                return
            if parsed.path == "/api/instrument-review/resolve":
                _require_exact_request_keys(
                    request,
                    {
                        "comparison_sha256",
                        "review_id",
                        "review_sha256",
                    },
                    label="instrument review resolution",
                )
                comparison_sha256 = _require_lowercase_sha256(
                    request.get("comparison_sha256"),
                    label="instrument review comparison_sha256",
                )
                review_id = _require_lowercase_sha256(
                    request.get("review_id"),
                    label="instrument review review_id",
                )
                review_sha256 = _require_lowercase_sha256(
                    request.get("review_sha256"),
                    label="instrument review review_sha256",
                )
                with self.server.state_lock:
                    context = self._instrument_review_context_for_comparison(
                        comparison_sha256
                    )
                    stored_review = self.server.instrument_reviews.review(review_id)
                    if (
                        stored_review.get("comparison_sha256") != comparison_sha256
                        or stored_review.get("review_sha256") != review_sha256
                    ):
                        raise WorkbenchInstrumentReviewConflictError(
                            "the completed instrument review changed"
                        )
                    result = self.server.instrument_reviews.resolve(
                        context=context,
                        comparison_sha256=comparison_sha256,
                        review_id=review_id,
                        review_sha256=review_sha256,
                    )
                    prepared = self.server.instrument_reviews.current(
                        context=context,
                        comparison_sha256=comparison_sha256,
                        reviewer_session_key=_workbench_instrument_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                    )
                    public_review = self._public_instrument_review(
                        prepared,
                        context=context,
                        resolution=result,
                    )
                self._json(
                    HTTPStatus.OK,
                    {"comparison": public_review},
                )
                return
            if parsed.path == "/api/listening-master-review/prepare":
                _require_exact_request_keys(
                    request,
                    {
                        "selection_manifest_sha256",
                        "balanced_arrangement_manifest_sha256",
                        "listening_master_manifest_sha256",
                        "start_seconds",
                        "end_seconds",
                    },
                    label="Listening Master blind-review preparation",
                )
                with self.server.state_lock:
                    initial = self._master_review_inputs()
                    self._require_master_review_hashes(request, *initial)
                prepared = self.server.master_reviews.prepare(
                    project_id=str(self.server.catalog["project_id"]),
                    balanced=initial[1],
                    listening_master=initial[2],
                    start_seconds=request.get("start_seconds"),
                    end_seconds=request.get("end_seconds"),
                    reviewer_session_key=_workbench_master_reviewer_key(
                        self.server.catalog["project_id"]
                    ),
                )
                with self.server.state_lock:
                    final = self._master_review_inputs()
                    self._require_master_review_hashes(request, *final)
                    public_review = self._public_master_review(
                        prepared,
                        selection=final[0],
                        balanced=final[1],
                        listening_master=final[2],
                    )
                self._json(
                    HTTPStatus.OK,
                    {"comparison": public_review},
                )
                return
            if parsed.path == "/api/listening-master-review":
                _require_exact_request_keys(
                    request,
                    {
                        "comparison_sha256",
                        "expected_revision",
                        "heard",
                        "choice",
                        "problem_tags",
                        "notes",
                    },
                    label="Listening Master blind review",
                )
                comparison_sha256 = _require_lowercase_sha256(
                    request.get("comparison_sha256"),
                    label="Listening Master review comparison_sha256",
                )
                with self.server.state_lock:
                    current = self._master_review_inputs()
                    completed = self.server.master_reviews.complete(
                        project_id=str(self.server.catalog["project_id"]),
                        balanced=current[1],
                        listening_master=current[2],
                        comparison_sha256=comparison_sha256,
                        reviewer_session_key=_workbench_master_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                        expected_revision=request.get("expected_revision"),
                        heard=request.get("heard"),
                        choice=request.get("choice"),
                        problem_tags=request.get("problem_tags"),
                        notes=request.get("notes"),
                    )
                    prepared = self.server.master_reviews.current(
                        project_id=str(self.server.catalog["project_id"]),
                        balanced=current[1],
                        listening_master=current[2],
                        comparison_sha256=comparison_sha256,
                        reviewer_session_key=_workbench_master_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                    )
                    if prepared.get("review_state", {}).get(
                        "review_id"
                    ) != completed.get("review_id"):
                        raise RuntimeError(
                            "Listening Master review publication changed"
                        )
                    public_review = self._public_master_review(
                        prepared,
                        selection=current[0],
                        balanced=current[1],
                        listening_master=current[2],
                    )
                self._json(
                    HTTPStatus.OK,
                    {"comparison": public_review},
                )
                return
            if parsed.path == "/api/listening-master-review/resolve":
                _require_exact_request_keys(
                    request,
                    {
                        "comparison_sha256",
                        "review_id",
                        "review_sha256",
                    },
                    label="Listening Master blind-review resolution",
                )
                comparison_sha256 = _require_lowercase_sha256(
                    request.get("comparison_sha256"),
                    label="Listening Master review comparison_sha256",
                )
                review_id = _require_lowercase_sha256(
                    request.get("review_id"),
                    label="Listening Master review review_id",
                )
                review_sha256 = _require_lowercase_sha256(
                    request.get("review_sha256"),
                    label="Listening Master review review_sha256",
                )
                with self.server.state_lock:
                    current = self._master_review_inputs()
                    stored_review = self.server.master_reviews.review(review_id)
                    if (
                        stored_review.get("comparison_sha256") != comparison_sha256
                        or stored_review.get("review_sha256") != review_sha256
                    ):
                        raise WorkbenchMasterReviewConflictError(
                            "the completed Listening Master review changed"
                        )
                    result = self.server.master_reviews.resolve(
                        project_id=str(self.server.catalog["project_id"]),
                        balanced=current[1],
                        listening_master=current[2],
                        review_id=review_id,
                    )
                    public_result = dict(result)
                    public_result["result_url"] = (
                        "/api/listening-master-review-export?kind=result"
                        f"&review_id={review_id}&token={self.server.token}"
                    )
                    response = {
                        "schema": result.get("schema"),
                        "status": "resolved",
                        "blind": False,
                        "comparison_sha256": comparison_sha256,
                        "selection_manifest_sha256": current[0].get(
                            "selection_manifest_sha256"
                        ),
                        "balanced_arrangement_manifest_sha256": current[1].get(
                            "manifest_sha256"
                        ),
                        "listening_master_manifest_sha256": current[2].get(
                            "manifest_sha256"
                        ),
                        "review": {
                            "review_id": review_id,
                            "review_sha256": review_sha256,
                            "revision": stored_review.get("revision"),
                            "response": stored_review.get("response"),
                            "choice": stored_review.get("response", {}).get("choice"),
                            "review_url": (
                                "/api/listening-master-review-export?kind=review"
                                f"&review_id={review_id}"
                                f"&token={self.server.token}"
                            ),
                        },
                        "result": public_result,
                        "effects": result.get("effects"),
                    }
                self._json(HTTPStatus.OK, {"comparison": response})
                return
            if parsed.path == "/api/listening-master-readiness/prepare":
                _require_exact_request_keys(
                    request,
                    {
                        "quality_review_id",
                        "quality_review_sha256",
                        "quality_result_sha256",
                    },
                    label="Listening Master native-level readiness preparation",
                )
                anchors = self._master_readiness_anchors(request)
                with self.server.state_lock:
                    initial = self._master_review_inputs()
                prepared = self.server.master_readiness.prepare(
                    project_id=str(self.server.catalog["project_id"]),
                    balanced=initial[1],
                    listening_master=initial[2],
                    reviewer_session_key=_workbench_master_reviewer_key(
                        self.server.catalog["project_id"]
                    ),
                    **anchors,
                )
                with self.server.state_lock:
                    final = self._master_review_inputs()
                    self._require_same_master_review_inputs(initial, final)
                    self._require_latest_master_readiness_review(anchors)
                    public_readiness = self._public_master_readiness(
                        prepared,
                        selection=final[0],
                        balanced=final[1],
                        listening_master=final[2],
                    )
                self._json(HTTPStatus.OK, {"readiness": public_readiness})
                return
            if parsed.path == "/api/listening-master-readiness":
                _require_exact_request_keys(
                    request,
                    {
                        "comparison_sha256",
                        "quality_review_id",
                        "quality_review_sha256",
                        "quality_result_sha256",
                        "heard",
                        "choice",
                        "problem_tags",
                        "notes",
                    },
                    label="Listening Master native-level readiness review",
                )
                comparison_sha256 = _require_lowercase_sha256(
                    request.get("comparison_sha256"),
                    label="native-level readiness comparison_sha256",
                )
                anchors = self._master_readiness_anchors(request)
                with self.server.state_lock:
                    current = self._master_review_inputs()
                    completed = self.server.master_readiness.complete(
                        project_id=str(self.server.catalog["project_id"]),
                        balanced=current[1],
                        listening_master=current[2],
                        comparison_sha256=comparison_sha256,
                        reviewer_session_key=_workbench_master_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                        heard=request.get("heard"),
                        choice=request.get("choice"),
                        problem_tags=request.get("problem_tags"),
                        notes=request.get("notes"),
                        **anchors,
                    )
                    prepared = self.server.master_readiness.prepare(
                        project_id=str(self.server.catalog["project_id"]),
                        balanced=current[1],
                        listening_master=current[2],
                        reviewer_session_key=_workbench_master_reviewer_key(
                            self.server.catalog["project_id"]
                        ),
                        **anchors,
                    )
                    if prepared.get(
                        "comparison_sha256"
                    ) != comparison_sha256 or prepared.get("review", {}).get(
                        "readiness_review_id"
                    ) != completed.get("readiness_review_id"):
                        raise WorkbenchMasterReadinessConflictError(
                            "native-level readiness publication changed"
                        )
                    public_readiness = self._public_master_readiness(
                        prepared,
                        selection=current[0],
                        balanced=current[1],
                        listening_master=current[2],
                    )
                    # This response is the result of the explicit completion
                    # operation, not another cache-only preparation. Preserve
                    # the stored review's two truthful durable-feedback effects
                    # while every product, selection and artifact effect stays
                    # false.
                    public_readiness["effects"] = dict(completed.get("effects", {}))
                self._json(HTTPStatus.OK, {"readiness": public_readiness})
                return
            if parsed.path == "/api/balanced-arrangement":
                _require_exact_request_keys(
                    request,
                    {"selection_manifest_sha256"},
                    label="balanced arrangement",
                )
                requested_manifest_sha256 = _require_lowercase_sha256(
                    request.get("selection_manifest_sha256"),
                    label="balanced arrangement selection_manifest_sha256",
                )
                with self.server.state_lock:
                    initial_state = self.server.store.current_state(self.server.catalog)
                    initial_manifest = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            initial_state,
                        )
                    )
                    if (
                        requested_manifest_sha256
                        != initial_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed; reload it before "
                            "creating the MIDI-derived song interpretation"
                        )
                try:
                    artifact = self.server.artifacts.render_balanced_arrangement(
                        self.server.catalog,
                        initial_state,
                        requested_manifest_sha256,
                        promote_cache=False,
                    )
                except ValueError as exc:
                    with self.server.state_lock:
                        failed_state = self.server.store.current_state(
                            self.server.catalog
                        )
                        failed_manifest = self.server.artifacts.decoded_arrangement_selection_manifest(  # noqa: E501
                            self.server.catalog,
                            failed_state,
                        )
                    if (
                        requested_manifest_sha256
                        != failed_manifest["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed while the balanced "
                            "song interpretation was being created; reload and retry"
                        ) from exc
                    raise
                cache_key = str(artifact.get("cache_key", ""))
                deferred_claim = artifact.get("_deferred_cache_claim")
                claim_token = (
                    str(deferred_claim) if isinstance(deferred_claim, str) else None
                )
                try:
                    with self.server.state_lock:
                        final_state = self.server.store.current_state(
                            self.server.catalog
                        )
                        final_manifest = self.server.artifacts.decoded_arrangement_selection_manifest(  # noqa: E501
                            self.server.catalog,
                            final_state,
                        )
                        final_home = build_workbench_home(
                            self.server.catalog,
                            final_state,
                        )
                        if (
                            requested_manifest_sha256
                            != final_manifest["selection_manifest_sha256"]
                            or artifact.get("selection_manifest_sha256")
                            != requested_manifest_sha256
                        ):
                            raise WorkbenchSelectionConflictError(
                                "the selected arrangement changed while the balanced "
                                "song interpretation was being created; reload "
                                "and retry"
                            )
                        promoted = self.server.artifacts.promote_balanced_arrangement(
                            cache_key,
                            claim_token=claim_token,
                        )
                        # Promotion consumes the private claim. From here onward
                        # the verified cache is adopted even if response
                        # serialization or delivery fails.
                        claim_token = None
                        promoted["cache_hit"] = artifact.get("cache_hit") is True
                        public_artifact = self._public_artifact(promoted)
                        cached_master = self.server.listening_masters.cached(promoted)
                        public_master = (
                            self._public_artifact(cached_master)
                            if cached_master
                            else None
                        )
                except Exception:
                    if claim_token is not None:
                        try:
                            self.server.artifacts.discard_deferred_balanced_arrangement(
                                cache_key,
                                claim_token,
                            )
                        except Exception:
                            # Cleanup is best effort. It must never replace the
                            # truthful conflict or primary rendering error.
                            pass
                    raise
                self._json(
                    HTTPStatus.OK,
                    {
                        "balanced_arrangement": public_artifact,
                        "listening_master": public_master,
                        "listening_master_review": None,
                        "product_outputs": build_product_output_status(
                            final_manifest,
                            public_artifact,
                            public_master,
                            full_mix_review_complete=bool(
                                final_home["counts"]["selected_part_count"]
                                and not final_home["counts"][
                                    "selected_needing_full_mix_count"
                                ]
                            ),
                        ),
                    },
                )
                return
            if parsed.path == "/api/listening-master":
                _require_exact_request_keys(
                    request,
                    {
                        "selection_manifest_sha256",
                        "balanced_arrangement_manifest_sha256",
                    },
                    label="listening master",
                )
                requested_selection_sha256 = _require_lowercase_sha256(
                    request.get("selection_manifest_sha256"),
                    label="listening master selection_manifest_sha256",
                )
                requested_balanced_sha256 = _require_lowercase_sha256(
                    request.get("balanced_arrangement_manifest_sha256"),
                    label=("listening master balanced_arrangement_manifest_sha256"),
                )
                with self.server.state_lock:
                    initial_state = self.server.store.current_state(self.server.catalog)
                    initial_selection = (
                        self.server.artifacts.decoded_arrangement_selection_manifest(
                            self.server.catalog,
                            initial_state,
                        )
                    )
                    if (
                        requested_selection_sha256
                        != initial_selection["selection_manifest_sha256"]
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement changed; reload it before "
                            "creating the comparative listening master"
                        )
                    initial_balanced = (
                        self.server.artifacts.cached_balanced_arrangement(
                            self.server.catalog,
                            initial_state,
                        )
                    )
                    if initial_balanced is None:
                        raise WorkbenchSelectionConflictError(
                            "the current song-interpretation WAV is unavailable; "
                            "create it before the comparative listening master"
                        )
                    if requested_balanced_sha256 != initial_balanced.get(
                        "manifest_sha256"
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the balanced song interpretation changed; reload it "
                            "before creating the comparative listening master"
                        )
                try:
                    prepared = self.server.listening_masters.prepare(initial_balanced)
                except (OSError, RuntimeError, ValueError) as exc:
                    with self.server.state_lock:
                        failed_state = self.server.store.current_state(
                            self.server.catalog
                        )
                        failed_selection = self.server.artifacts.decoded_arrangement_selection_manifest(  # noqa: E501
                            self.server.catalog,
                            failed_state,
                        )
                        failed_balanced = (
                            self.server.artifacts.cached_balanced_arrangement(
                                self.server.catalog,
                                failed_state,
                            )
                        )
                    if (
                        requested_selection_sha256
                        != failed_selection["selection_manifest_sha256"]
                        or failed_balanced is None
                        or requested_balanced_sha256
                        != failed_balanced.get("manifest_sha256")
                    ):
                        raise WorkbenchSelectionConflictError(
                            "the selected arrangement or balanced song "
                            "interpretation changed while the comparative "
                            "listening master was being created; reload and retry"
                        ) from exc
                    raise
                cache_key = str(prepared.get("cache_key", ""))
                pending_token_value = prepared.get("_pending_token")
                pending_token = (
                    str(pending_token_value)
                    if isinstance(pending_token_value, str)
                    else None
                )
                try:
                    with self.server.state_lock:
                        final_state = self.server.store.current_state(
                            self.server.catalog
                        )
                        final_selection = self.server.artifacts.decoded_arrangement_selection_manifest(  # noqa: E501
                            self.server.catalog,
                            final_state,
                        )
                        final_balanced = (
                            self.server.artifacts.cached_balanced_arrangement(
                                self.server.catalog,
                                final_state,
                            )
                        )
                        if (
                            requested_selection_sha256
                            != final_selection["selection_manifest_sha256"]
                            or final_balanced is None
                            or requested_balanced_sha256
                            != final_balanced.get("manifest_sha256")
                            or prepared.get("selection_manifest_sha256")
                            != requested_selection_sha256
                            or prepared.get("balanced_arrangement_manifest_sha256")
                            != requested_balanced_sha256
                        ):
                            raise WorkbenchSelectionConflictError(
                                "the selected arrangement or balanced song "
                                "interpretation changed while the comparative "
                                "listening master was being created; reload "
                                "and retry"
                            )
                        if pending_token is None:
                            promoted = self.server.listening_masters.cached(
                                final_balanced
                            )
                            if promoted is None:
                                raise RuntimeError(
                                    "verified listening-master cache disappeared"
                                )
                        else:
                            promoted = self.server.listening_masters.promote(
                                cache_key,
                                pending_token,
                            )
                            pending_token = None
                        promoted["cache_hit"] = prepared.get("cache_hit") is True
                        public_master = self._public_artifact(promoted)
                        final_home = build_workbench_home(
                            self.server.catalog,
                            final_state,
                        )
                except Exception:
                    if pending_token is not None:
                        try:
                            self.server.listening_masters.discard(
                                cache_key,
                                pending_token,
                            )
                        except Exception:
                            # Best-effort cleanup must not replace a truthful
                            # selection conflict or mastering failure.
                            pass
                    raise
                self._json(
                    HTTPStatus.OK,
                    {
                        "listening_master": public_master,
                        "listening_master_review": None,
                        "product_outputs": build_product_output_status(
                            final_selection,
                            final_balanced,
                            public_master,
                            full_mix_review_complete=bool(
                                final_home["counts"]["selected_part_count"]
                                and not final_home["counts"][
                                    "selected_needing_full_mix_count"
                                ]
                            ),
                        ),
                    },
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
        except (
            WorkbenchPackConflictError,
            WorkbenchPackStateConflictError,
            WorkbenchMasterReviewConflictError,
            WorkbenchMasterReviewRevisionConflictError,
            WorkbenchMasterReadinessConflictError,
            WorkbenchMasterReadinessGateError,
            WorkbenchInstrumentReviewConflictError,
            WorkbenchInstrumentReviewRevisionConflictError,
            WorkbenchSelectionConflictError,
        ) as exc:
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
        state = self.server.store.current_state(self.server.catalog)
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
                    role_override=str(
                        state.get("stems", {}).get(str(stem["stem_id"]), {}).get("role")
                        or stem.get("role")
                        or "unclassified"
                    ),
                )
                candidate["neutral_preview"] = (
                    self._public_artifact(cached) if cached else None
                )
        review = self.server.store.export_review(self.server.catalog)
        payload["state"] = path_free_browser_state(state)
        home = build_workbench_home(self.server.catalog, state)
        payload["home"] = home
        payload["contribution_preview"] = review["contribution_preview"]
        payload["review_status"] = review["status"]
        payload["review_url"] = f"/api/review?token={self.server.token}"
        payload["selected_midi_overlap"] = self.server.artifacts.selected_midi_overlap(
            self.server.catalog,
            state,
        )
        decoded_arrangement_selection = (
            self.server.artifacts.decoded_arrangement_selection_manifest(
                self.server.catalog, state
            )
        )
        payload["decoded_arrangement_selection"] = decoded_arrangement_selection
        arrangement = self.server.artifacts.cached_arrangement(
            self.server.catalog, state
        )
        payload["arrangement"] = (
            self._public_artifact(arrangement) if arrangement else None
        )
        balanced_arrangement = self.server.artifacts.cached_balanced_arrangement(
            self.server.catalog, state
        )
        public_balanced_arrangement = (
            self._public_artifact(balanced_arrangement)
            if balanced_arrangement
            else None
        )
        payload["balanced_arrangement"] = public_balanced_arrangement
        listening_master = (
            self.server.listening_masters.cached(balanced_arrangement)
            if balanced_arrangement
            else None
        )
        public_listening_master = (
            self._public_artifact(listening_master) if listening_master else None
        )
        payload["listening_master"] = public_listening_master
        # Project loading must not guess a review window or silently restore a
        # feedback workflow.  The server derives the private project-scoped
        # reviewer identity only when the user explicitly prepares a review.
        payload["listening_master_review"] = None
        payload["product_contract"] = product_contract_document()
        payload["product_outputs"] = build_product_output_status(
            decoded_arrangement_selection,
            public_balanced_arrangement,
            public_listening_master,
            full_mix_review_complete=bool(
                home["counts"]["selected_part_count"]
                and not home["counts"]["selected_needing_full_mix_count"]
            ),
        )
        payload["developer"] = {
            "enabled": self.server.developer_inspector,
            "snapshot_endpoint": (
                "/api/developer-snapshot" if self.server.developer_inspector else None
            ),
            "read_only": True,
        }
        payload["clip_library"] = (
            self.server.clip_service.capability()
            if self.server.clip_service is not None
            else {
                "enabled": False,
                "read_only": True,
                "reason": "Phase 6 Clip Library options were not supplied for this launch",
            }
        )
        payload["clip_reuse_plan"] = (
            self.server.clip_reuse_service.capability()
            if self.server.clip_reuse_service is not None
            else {
                "enabled": False,
                "proposal_only": True,
                "reason": (
                    "Clip reuse planning was not explicitly enabled for this launch"
                ),
            }
        )
        transform_service = self.server.clip_transform_service
        if transform_service is None:
            payload["clip_transforms"] = {
                "enabled": False,
                "immutable_versions_only": True,
                "reason": (
                    "Clip transforms were not explicitly enabled for this launch"
                ),
            }
        else:
            with self.server.state_lock:
                payload["clip_transforms"] = transform_service.capability()
        correction_service = self.server.clip_correction_service
        if correction_service is None:
            payload["clip_corrections"] = {
                "enabled": False,
                "immutable_versions_only": True,
                "reason": (
                    "Clip note corrections were not explicitly enabled for this launch"
                ),
            }
        else:
            with self.server.state_lock:
                payload["clip_corrections"] = correction_service.capability()
        return payload

    def _developer_snapshot_payload(self) -> dict[str, Any]:
        trace = self.server.developer_trace
        if not self.server.developer_inspector or trace is None:
            raise ValueError("developer inspector is disabled")
        with self.server.state_lock:
            events = self.server.store.events(str(self.server.catalog["project_id"]))
            current = fold_workbench_events(self.server.catalog, events)
            arrangement_selection = (
                self.server.artifacts.decoded_arrangement_selection_manifest(
                    self.server.catalog,
                    current,
                )
            )
            pack_plan = self._garageband_pack_plan_payload()
            clip_capability = (
                self.server.clip_service.capability()
                if self.server.clip_service is not None
                else None
            )
            clip_reuse_plan = (
                self.server.clip_reuse_service.plan()
                if self.server.clip_reuse_service is not None
                else None
            )
            clip_transform_capability = (
                self.server.clip_transform_service.capability()
                if self.server.clip_transform_service is not None
                else None
            )
            clip_correction_capability = (
                self.server.clip_correction_service.capability()
                if self.server.clip_correction_service is not None
                else None
            )
            runtime = {
                "catalog_media_capability_count": len(self.server.catalog_media_ids),
                "generated_media_capability_count": len(
                    self.server.generated_media_ids
                ),
                "generated_media_capability_limit": _MAX_GENERATED_MEDIA_RECORDS,
                "decoded_stream_plan_count": len(self.server.decoded_stream_plans),
                "decoded_stream_plan_limit": _MAX_DECODED_STREAM_PLANS,
                "clip_library_enabled": clip_capability is not None,
                "clip_library_clip_count": (
                    0
                    if clip_capability is None
                    else int(clip_capability["library"]["clip_count"])
                ),
                "clip_reuse_plan_enabled": clip_reuse_plan is not None,
                "clip_reuse_plan_revision": (
                    0
                    if clip_reuse_plan is None
                    else int(clip_reuse_plan.get("revision", 0))
                ),
                "clip_reuse_active_placement_count": (
                    0
                    if clip_reuse_plan is None
                    else len(clip_reuse_plan.get("placements", []))
                ),
                "clip_transforms_enabled": clip_transform_capability is not None,
                "clip_corrections_enabled": clip_correction_capability is not None,
            }
            trace_snapshot = trace.snapshot()
        cache = artifact_cache_summary(
            self.server.artifacts.root,
            verified_stream_entries=(
                self.server.artifacts.developer_verified_stream_entry_count()
            ),
        )
        payload = build_developer_snapshot(
            self.server.catalog,
            current,
            events=events,
            arrangement_selection=arrangement_selection,
            pack_plan=pack_plan,
            clip_reuse_plan=clip_reuse_plan,
            trace=trace_snapshot,
            runtime=runtime,
            cache=cache,
        )
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_DEVELOPER_SNAPSHOT_BYTES:
            raise ValueError("developer snapshot exceeds its fixed response limit")
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

    def _start_developer_trace(self, method: str, route: str) -> None:
        self._developer_application_invoked = False
        trace = self.server.developer_trace
        operation = developer_operation_for_route(route)
        if trace is None or operation is None:
            self._developer_trace_sequence = None
            self._developer_trace_route = None
            return
        self._developer_trace_sequence = trace.begin(method, operation)
        self._developer_trace_route = route

    def _developer_checkpoint(
        self,
        stage: str,
        code_step: str,
        facts: Mapping[str, Any] | None = None,
    ) -> None:
        trace = self.server.developer_trace
        if trace is None:
            return
        trace.checkpoint(
            getattr(self, "_developer_trace_sequence", None),
            stage,
            code_step,
            facts,
        )

    def _complete_developer_trace(
        self,
        status: HTTPStatus,
        facts: Mapping[str, Any] | None = None,
    ) -> None:
        trace = self.server.developer_trace
        sequence = getattr(self, "_developer_trace_sequence", None)
        if trace is None or sequence is None:
            return
        trace.complete(sequence, int(status), facts)
        self._developer_trace_sequence = None
        self._developer_trace_route = None

    def _public_artifact(self, artifact: Mapping[str, Any]) -> dict[str, Any]:
        freeze_balanced = artifact.get("schema") == BALANCED_ARRANGEMENT_SCHEMA
        freeze_listening_master = (
            artifact.get("schema") == WORKBENCH_LISTENING_MASTER_SCHEMA
        )
        private_artifact_keys = {
            "midi",
            "preview",
            "report",
            "recipe",
            "master",
            "zip",
            "acceptance_review",
            "acceptance_seed",
        }
        if freeze_listening_master:
            private_artifact_keys.add("receipt")
        public = {
            key: value
            for key, value in artifact.items()
            if not str(key).startswith("_") and key not in private_artifact_keys
        }
        for key, prefix in (
            ("midi", "artifact-midi"),
            ("preview", "artifact-preview"),
            ("report", "artifact-report"),
            ("recipe", "artifact-recipe"),
            ("master", "artifact-listening-master"),
            ("receipt", "artifact-listening-master-receipt"),
            ("zip", "artifact-zip"),
            ("acceptance_review", "artifact-acceptance-review"),
        ):
            if key == "receipt" and not freeze_listening_master:
                continue
            record = artifact.get(key)
            if not isinstance(record, Mapping):
                continue
            media_id = f"{prefix}-{str(record['sha256'])[:24]}"
            private_record = dict(record)
            if freeze_balanced or freeze_listening_master:
                private_record["_freeze_on_serve"] = True
            if key == "acceptance_review":
                private_record["_freeze_on_serve"] = True
                private_record["_review_page"] = True
            self._register_generated_media(media_id, private_record)
            public[key] = {
                item_key: item_value
                for item_key, item_value in record.items()
                if item_key != "path"
            }
            public[f"{key}_url"] = self._media_url(media_id)
        seed_record = artifact.get("acceptance_seed")
        if isinstance(seed_record, Mapping):
            public["acceptance_seed"] = {
                key: value for key, value in seed_record.items() if key != "path"
            }
        return public

    def _instrument_review_plan(self) -> dict[str, Any]:
        """Derive a path-free plan from active selected bass or keys MIDI."""

        current = self.server.store.current_state(self.server.catalog)
        manifest = self.server.artifacts.decoded_arrangement_selection_manifest(
            self.server.catalog,
            current,
        )
        selected = selected_candidates(self.server.catalog, current)
        eligible = {
            (
                str(item.get("stem_id", "")),
                str(item.get("candidate_id", "")),
                str(item.get("midi", {}).get("sha256", "")),
                str(item.get("role", "")),
            )
            for item in selected
            if item.get("role") in _INSTRUMENT_REVIEW_ROLES
            and item.get("audition_blocked") is not True
        }
        lanes: list[dict[str, Any]] = []
        role_counts = {role: 0 for role in _INSTRUMENT_REVIEW_ROLES}
        selection_sha256 = _require_lowercase_sha256(
            manifest.get("selection_manifest_sha256"),
            label="instrument review selection manifest",
        )
        for row in manifest.get("selected_midi", []):
            if (
                not isinstance(row, Mapping)
                or row.get("role") not in _INSTRUMENT_REVIEW_ROLES
            ):
                continue
            role = str(row["role"])
            pins = (
                str(row.get("stem_id", "")),
                str(row.get("candidate_id", "")),
                str(row.get("midi_sha256", "")),
                role,
            )
            if pins not in eligible:
                continue
            role_counts[role] += 1
            programs = complete_instrument_programs(role)
            lanes.append(
                {
                    "selection_manifest_sha256": selection_sha256,
                    "stem_id": pins[0],
                    "candidate_id": pins[1],
                    "midi_sha256": pins[2],
                    "role": role,
                    "label": (f"Selected {role} MIDI {role_counts[role]}"),
                    "coverage_preflight": (
                        "required" if role == "keys" else "not_required"
                    ),
                    "pair": {
                        "description": (
                            "The exact selected MIDI through two complete "
                            f"server-owned General MIDI {role} programs."
                        ),
                        "control": {"label": programs["control"]["label"]},
                        "challenger": {"label": programs["challenger"]["label"]},
                    },
                }
            )
        if len(lanes) > 64:
            raise ValueError("instrument review plan exceeds its fixed lane limit")
        plan = {
            "schema": "sunofriend.workbench-instrument-review-plan.v1",
            "selection_manifest_sha256": selection_sha256,
            "eligible_lanes": lanes,
            "effects": {
                "midi_changed": False,
                "instrument_default_changed": False,
                "pack_changed": False,
                "mix_changed": False,
                "feedback_recorded": False,
            },
        }
        if _mapping_contains_key(plan, "path"):
            raise ValueError("instrument review plan exposed a private path")
        return plan

    def _instrument_review_context(
        self,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Resolve browser lane pins to one trusted private current context."""

        selection_sha256 = _require_lowercase_sha256(
            request.get("selection_manifest_sha256"),
            label="instrument review selection_manifest_sha256",
        )
        midi_sha256 = _require_lowercase_sha256(
            request.get("midi_sha256"),
            label="instrument review midi_sha256",
        )
        identifiers: dict[str, str] = {}
        for key in ("stem_id", "candidate_id"):
            value = request.get(key)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ValueError(f"instrument review {key} is invalid")
            identifiers[key] = value

        current = self.server.store.current_state(self.server.catalog)
        manifest = self.server.artifacts.decoded_arrangement_selection_manifest(
            self.server.catalog,
            current,
        )
        if manifest.get("selection_manifest_sha256") != selection_sha256:
            raise WorkbenchSelectionConflictError(
                "the selected arrangement changed; reload the instrument review"
            )
        matches = [
            row
            for row in manifest.get("selected_midi", [])
            if isinstance(row, Mapping)
            and row.get("stem_id") == identifiers["stem_id"]
            and row.get("candidate_id") == identifiers["candidate_id"]
            and row.get("midi_sha256") == midi_sha256
            and row.get("role") in _INSTRUMENT_REVIEW_ROLES
        ]
        if len(matches) != 1:
            raise WorkbenchSelectionConflictError(
                "the selected bass or keys MIDI changed; reload the instrument review"
            )
        role = str(matches[0]["role"])
        active = [
            row
            for row in selected_candidates(self.server.catalog, current)
            if row.get("stem_id") == identifiers["stem_id"]
            and row.get("candidate_id") == identifiers["candidate_id"]
            and row.get("midi", {}).get("sha256") == midi_sha256
            and row.get("role") == role
            and row.get("audition_blocked") is not True
        ]
        if len(active) != 1:
            raise WorkbenchSelectionConflictError(
                f"the selected {role} MIDI is no longer eligible for review"
            )
        context = self.server.artifacts.instrument_review_context(
            self.server.catalog,
            current,
            str(matches[0]["track_id"]),
            selection_sha256,
        )
        track = context.get("track")
        if (
            not isinstance(track, Mapping)
            or track.get("stem_id") != identifiers["stem_id"]
            or track.get("candidate_id") != identifiers["candidate_id"]
            or track.get("role") != role
            or track.get("midi", {}).get("sha256") != midi_sha256
        ):
            raise WorkbenchSelectionConflictError(
                "instrument review lane evidence changed"
            )
        return context

    def _remember_instrument_review_context(
        self,
        comparison_sha256: str,
        context: Mapping[str, Any],
    ) -> None:
        track = context.get("track")
        if not isinstance(track, Mapping):
            raise ValueError("instrument review context track is invalid")
        pins = {
            "selection_manifest_sha256": _require_lowercase_sha256(
                context.get("selection_manifest_sha256"),
                label="instrument review selection manifest",
            ),
            "stem_id": str(track.get("stem_id", "")),
            "candidate_id": str(track.get("candidate_id", "")),
            "midi_sha256": _require_lowercase_sha256(
                track.get("midi", {}).get("sha256"),
                label="instrument review MIDI",
            ),
        }
        contexts = self.server.instrument_review_contexts
        contexts.pop(comparison_sha256, None)
        contexts[comparison_sha256] = pins
        while len(contexts) > _MAX_INSTRUMENT_REVIEW_CONTEXTS:
            contexts.popitem(last=False)

    def _instrument_review_context_for_comparison(
        self,
        comparison_sha256: str,
    ) -> dict[str, Any]:
        contexts = self.server.instrument_review_contexts
        pins = contexts.get(comparison_sha256)
        if not isinstance(pins, Mapping):
            binding = self.server.instrument_reviews.comparison_binding(
                comparison_sha256
            )
            track = binding.get("track")
            if (
                binding.get("project_id") != self.server.catalog.get("project_id")
                or binding.get("role") not in _INSTRUMENT_REVIEW_ROLES
                or not isinstance(track, Mapping)
            ):
                raise WorkbenchInstrumentReviewConflictError(
                    "instrument review comparison belongs to different evidence"
                )
            pins = {
                "selection_manifest_sha256": binding.get("selection_manifest_sha256"),
                "stem_id": track.get("stem_id"),
                "candidate_id": track.get("candidate_id"),
                "midi_sha256": binding.get("selected_midi", {}).get("sha256"),
            }
            context = self._instrument_review_context(pins)
            self._remember_instrument_review_context(
                comparison_sha256,
                context,
            )
            return context
        contexts.move_to_end(comparison_sha256)
        return self._instrument_review_context(pins)

    def _require_same_instrument_review_context(
        self,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> None:
        def anchors(value: Mapping[str, Any]) -> tuple[Any, ...]:
            track = value.get("track")
            return (
                value.get("project_id"),
                value.get("selection_manifest_sha256"),
                track.get("track_id") if isinstance(track, Mapping) else None,
                track.get("stem_id") if isinstance(track, Mapping) else None,
                track.get("candidate_id") if isinstance(track, Mapping) else None,
                track.get("role") if isinstance(track, Mapping) else None,
                (
                    track.get("midi", {}).get("sha256")
                    if isinstance(track, Mapping)
                    else None
                ),
                value.get("source", {}).get("sha256"),
                value.get("soundfont", {}).get("sha256"),
            )

        if anchors(before) != anchors(after):
            raise WorkbenchSelectionConflictError(
                "the selected bass or keys MIDI changed while its instrument review "
                "was being prepared; reload and retry"
            )

    def _master_review_inputs(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Return the exact current selection, balanced control and challenger."""

        state = self.server.store.current_state(self.server.catalog)
        selection = self.server.artifacts.decoded_arrangement_selection_manifest(
            self.server.catalog,
            state,
        )
        balanced = self.server.artifacts.cached_balanced_arrangement(
            self.server.catalog,
            state,
        )
        if balanced is None:
            raise WorkbenchSelectionConflictError(
                "the current balanced song interpretation is unavailable"
            )
        listening_master = self.server.listening_masters.cached(balanced)
        if listening_master is None:
            raise WorkbenchSelectionConflictError(
                "the current Listening Master challenger is unavailable"
            )
        return selection, balanced, listening_master

    def _require_master_review_hashes(
        self,
        request: Mapping[str, Any],
        selection: Mapping[str, Any],
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
    ) -> None:
        checks = (
            (
                "selection_manifest_sha256",
                selection.get("selection_manifest_sha256"),
            ),
            (
                "balanced_arrangement_manifest_sha256",
                balanced.get("manifest_sha256"),
            ),
            (
                "listening_master_manifest_sha256",
                listening_master.get("manifest_sha256"),
            ),
        )
        for key, current in checks:
            requested = _require_lowercase_sha256(
                request.get(key),
                label=f"Listening Master review {key}",
            )
            if requested != current:
                raise WorkbenchSelectionConflictError(
                    "the selected arrangement, balanced control or Listening "
                    "Master changed; reload before continuing the blind review"
                )

    def _master_readiness_anchors(
        self,
        request: Mapping[str, Any],
    ) -> dict[str, str]:
        return {
            key: _require_lowercase_sha256(
                request.get(key),
                label=f"native-level readiness {key}",
            )
            for key in (
                "quality_review_id",
                "quality_review_sha256",
                "quality_result_sha256",
            )
        }

    def _require_latest_master_readiness_review(
        self,
        anchors: Mapping[str, str],
    ) -> None:
        """Close preparation/publication races against a newer blind response."""

        latest = self.server.master_reviews.latest_review_for_project_reviewer(
            project_id=str(self.server.catalog["project_id"]),
            reviewer_session_key=_workbench_master_reviewer_key(
                self.server.catalog["project_id"]
            ),
        )
        if (
            latest is None
            or latest.get("review_id") != anchors["quality_review_id"]
            or latest.get("review_sha256") != anchors["quality_review_sha256"]
        ):
            raise WorkbenchMasterReadinessConflictError(
                "blind quality review changed while native-level readiness "
                "was being prepared"
            )

    def _require_same_master_review_inputs(
        self,
        before: tuple[
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
        ],
        after: tuple[
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
        ],
    ) -> None:
        identities = (
            ("selection", "selection_manifest_sha256"),
            ("balanced control", "manifest_sha256"),
            ("Listening Master", "manifest_sha256"),
        )
        for (label, key), earlier, current in zip(identities, before, after):
            if earlier.get(key) != current.get(key):
                raise WorkbenchSelectionConflictError(
                    f"the {label} changed while native-level readiness audio "
                    "was being prepared; reload and retry"
                )

    def _public_instrument_review(
        self,
        prepared: Mapping[str, Any],
        *,
        context: Mapping[str, Any],
        resolution: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register frozen blind crops and expose only a safe comparison."""

        comparison_sha256 = _require_lowercase_sha256(
            prepared.get("comparison_sha256"),
            label="instrument review comparison_sha256",
        )
        comparison = prepared.get("comparison")
        track = context.get("track")
        if not isinstance(comparison, Mapping) or not isinstance(track, Mapping):
            raise ValueError("instrument review comparison is invalid")
        if (
            comparison.get("selection_manifest_sha256")
            != context.get("selection_manifest_sha256")
            or comparison.get("track", {}).get("stem_id") != track.get("stem_id")
            or comparison.get("track", {}).get("candidate_id")
            != track.get("candidate_id")
            or comparison.get("selected_midi", {}).get("sha256")
            != track.get("midi", {}).get("sha256")
            or comparison.get("role") != track.get("role")
            or comparison.get("role") not in _INSTRUMENT_REVIEW_ROLES
        ):
            raise WorkbenchInstrumentReviewConflictError(
                "instrument review comparison no longer matches its selected lane"
            )
        public_coverage = self._public_instrument_review_coverage(
            prepared,
            comparison=comparison,
            comparison_sha256=comparison_sha256,
            context=context,
        )

        audio = prepared.get("audio")
        if not isinstance(audio, Mapping):
            raise ValueError("instrument review audio is invalid")
        public_audio: dict[str, dict[str, Any]] = {}
        media_records: dict[str, tuple[str, dict[str, Any]]] = {}
        for slot in (
            SOURCE_REFERENCE,
            INSTRUMENT_CANDIDATE_A,
            INSTRUMENT_CANDIDATE_B,
        ):
            row = audio.get(slot)
            if not isinstance(row, Mapping):
                raise ValueError("instrument review audio row is invalid")
            gain = row.get("applied_gain_db")
            if (
                isinstance(gain, bool)
                or not isinstance(gain, (int, float))
                or not math.isfinite(float(gain))
                or not -60.0 <= float(gain) <= 0.0
            ):
                raise ValueError("instrument review disclosed gain is invalid")
            record = self.server.instrument_reviews.media_record(
                comparison_sha256,
                slot,
            )
            media_id = f"instrument-review-{slot}-{comparison_sha256[:24]}"
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            media_records[slot] = (media_id, private_record)
            public_audio[slot] = {
                "audio_url": self._media_url(media_id),
                "applied_gain_db": float(gain),
            }

        current_review = prepared.get("current_review")
        public_review = None
        if current_review is not None:
            if not isinstance(current_review, Mapping):
                raise ValueError("instrument review artifact is invalid")
            review_id = _require_lowercase_sha256(
                current_review.get("review_id"),
                label="instrument review identity",
            )
            review_sha256 = _require_lowercase_sha256(
                current_review.get("review_sha256"),
                label="instrument review SHA-256",
            )
            revision = current_review.get("revision")
            if (
                isinstance(revision, bool)
                or not isinstance(revision, int)
                or revision < 1
            ):
                raise ValueError("instrument review revision is invalid")
            response = current_review.get("response")
            if not isinstance(response, Mapping):
                raise ValueError("instrument review response is invalid")
            public_review = {
                "review_id": review_id,
                "review_sha256": review_sha256,
                "revision": revision,
                "review_url": (
                    "/api/instrument-review-export?kind=review"
                    f"&review_id={review_id}&token={self.server.token}"
                ),
                "response": {
                    "heard": dict(response.get("heard", {})),
                    "choice": response.get("choice"),
                    "problem_tags": {
                        slot: list(response.get("problem_tags", {}).get(slot, []))
                        for slot in (
                            INSTRUMENT_CANDIDATE_A,
                            INSTRUMENT_CANDIDATE_B,
                        )
                    },
                    "notes": {
                        slot: str(response.get("notes", {}).get(slot, ""))
                        for slot in (
                            INSTRUMENT_CANDIDATE_A,
                            INSTRUMENT_CANDIDATE_B,
                        )
                    },
                },
            }
            if resolution is None:
                resolution = self.server.instrument_reviews.resolution(review_id)

        public_result = None
        if resolution is not None:
            if public_review is None or not isinstance(resolution, Mapping):
                raise ValueError("instrument review resolution is invalid")
            if (
                resolution.get("comparison_sha256") != comparison_sha256
                or resolution.get("review_id") != public_review["review_id"]
                or resolution.get("review_sha256") != public_review["review_sha256"]
            ):
                raise WorkbenchInstrumentReviewConflictError(
                    "instrument review resolution changed"
                )
            assignment = resolution.get("assignment")
            if not isinstance(assignment, Mapping):
                raise ValueError("instrument review assignment is invalid")
            public_assignment: dict[str, dict[str, Any]] = {}
            identity_labels: dict[str, str] = {}
            for slot in (
                INSTRUMENT_CANDIDATE_A,
                INSTRUMENT_CANDIDATE_B,
            ):
                identity = assignment.get(slot)
                if not isinstance(identity, Mapping):
                    raise ValueError("instrument review assignment row is invalid")
                label = identity.get("label")
                if not isinstance(label, str) or not label:
                    raise ValueError("instrument review assignment label is invalid")
                public_assignment[slot] = {
                    "label": label,
                    "general_midi_number": identity.get("general_midi_number"),
                }
                identity_name = identity.get("identity")
                if isinstance(identity_name, str):
                    identity_labels[identity_name] = label
            resolved_choice = resolution.get("resolved_choice")
            if isinstance(resolved_choice, str):
                resolved_choice = identity_labels.get(
                    resolved_choice,
                    resolved_choice,
                )
            public_result = {
                "assignment": public_assignment,
                "resolved_choice": resolved_choice,
                "result_url": (
                    "/api/instrument-review-export?kind=result"
                    f"&review_id={public_review['review_id']}"
                    f"&token={self.server.token}"
                ),
            }

        allowed = prepared.get("allowed")
        window = comparison.get("window")
        if not isinstance(allowed, Mapping) or not isinstance(window, Mapping):
            raise ValueError("instrument review limits or window are invalid")
        status = (
            "resolved"
            if public_result is not None
            else "reviewed"
            if public_review is not None
            else "unreviewed"
        )
        public = {
            "schema": "sunofriend.workbench-instrument-review.comparison.v1",
            "status": status,
            "blind": public_result is None,
            "comparison_sha256": comparison_sha256,
            "selection_manifest_sha256": context.get("selection_manifest_sha256"),
            "stem_id": track.get("stem_id"),
            "candidate_id": track.get("candidate_id"),
            "midi_sha256": track.get("midi", {}).get("sha256"),
            "role": track.get("role"),
            "coverage_preflight": public_coverage,
            "expected_revision": (
                public_review["revision"] if public_review is not None else 0
            ),
            "window": {
                "start_seconds": window.get("start_seconds"),
                "end_seconds": window.get("end_seconds"),
            },
            "source_reference": public_audio[SOURCE_REFERENCE],
            "candidates": {
                INSTRUMENT_CANDIDATE_A: public_audio[INSTRUMENT_CANDIDATE_A],
                INSTRUMENT_CANDIDATE_B: public_audio[INSTRUMENT_CANDIDATE_B],
            },
            "allowed_problem_tags": sorted(INSTRUMENT_REVIEW_PROBLEM_TAGS),
            "limits": {
                "maximum_problem_tags_per_candidate": (INSTRUMENT_MAXIMUM_PROBLEM_TAGS),
                "maximum_notes_characters_per_candidate": (
                    INSTRUMENT_MAXIMUM_NOTES_CHARACTERS
                ),
            },
            "review": public_review,
            "result": public_result,
            "effects": {
                "midi_changed": False,
                "instrument_default_changed": False,
                "pack_changed": False,
                "mix_changed": False,
                "feedback_recorded": public_review is not None,
            },
        }
        if _mapping_contains_key(public, "path"):
            raise ValueError(
                "instrument review browser projection exposed a private path"
            )
        for media_id, record in media_records.values():
            self._register_generated_media(media_id, record)
        return public

    def _public_instrument_review_coverage(
        self,
        prepared: Mapping[str, Any],
        *,
        comparison: Mapping[str, Any],
        comparison_sha256: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Validate private probe detail and return only blind counts/floors."""

        role = comparison.get("role")
        expected_contract = keys_coverage_contract(required=role == "keys")
        comparison_contract = comparison.get("coverage_preflight")
        if comparison_contract != expected_contract:
            raise ValueError("instrument review coverage contract changed")
        coverage = prepared.get("coverage_preflight")
        if role == "bass":
            if coverage != expected_contract:
                raise ValueError(
                    "bass instrument review carried unexpected coverage evidence"
                )
            return {
                "schema": expected_contract["schema"],
                "required": False,
                "status": "not_required",
                "functional_status": "not_required",
                "quality_status": "review_required",
                "actual_review_midi_changed": False,
            }
        if role != "keys" or not isinstance(coverage, Mapping):
            raise ValueError("keys instrument review coverage is unavailable")

        exact_keys = set(expected_contract) | {
            "zone_count",
            "duration_seconds",
            "candidate_identities_hidden",
            INSTRUMENT_CANDIDATE_A,
            INSTRUMENT_CANDIDATE_B,
            "binding",
            "coverage_sha256",
        }
        if set(coverage) != exact_keys:
            raise ValueError("keys instrument review coverage shape changed")
        for key, expected in expected_contract.items():
            if key in {"status", "functional_status"}:
                continue
            if coverage.get(key) != expected:
                raise ValueError(f"keys instrument review coverage {key} changed")
        if (
            coverage.get("required") is not True
            or coverage.get("status") != "passed"
            or coverage.get("functional_status") != "passed"
            or coverage.get("quality_status") != "review_required"
            or coverage.get("candidate_identities_hidden") is not True
            or coverage.get("actual_review_midi_changed") is not False
        ):
            raise ValueError("keys instrument review coverage did not pass")

        binding = coverage.get("binding")
        selected_midi = comparison.get("selected_midi")
        soundfont = comparison.get("soundfont")
        renderer = comparison.get("renderer")
        track = context.get("track")
        if (
            not isinstance(binding, Mapping)
            or set(binding)
            != {
                "comparison_sha256",
                "selection_manifest_sha256",
                "selected_midi_sha256",
                "soundfont_sha256",
                "renderer_sha256",
                "candidate_identity_set_commitment",
            }
            or not isinstance(selected_midi, Mapping)
            or not isinstance(soundfont, Mapping)
            or not isinstance(renderer, Mapping)
            or not isinstance(track, Mapping)
            or binding.get("comparison_sha256") != comparison_sha256
            or binding.get("selection_manifest_sha256")
            != context.get("selection_manifest_sha256")
            or binding.get("selected_midi_sha256")
            != track.get("midi", {}).get("sha256")
            or binding.get("selected_midi_sha256") != selected_midi.get("sha256")
            or binding.get("soundfont_sha256") != soundfont.get("sha256")
            or binding.get("renderer_sha256") != renderer.get("sha256")
            or binding.get("candidate_identity_set_commitment")
            != comparison.get("candidate_identity_set_commitment")
        ):
            raise WorkbenchInstrumentReviewConflictError(
                "keys coverage no longer matches its selected evidence"
            )

        unsigned_coverage = {
            key: value for key, value in coverage.items() if key != "coverage_sha256"
        }
        encoded = json.dumps(
            unsigned_coverage,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if coverage.get("coverage_sha256") != hashlib.sha256(encoded).hexdigest():
            raise ValueError("keys coverage receipt changed")

        geometry: list[tuple[Any, ...]] | None = None
        summaries: dict[str, dict[str, Any]] = {}
        bucket_counts = {
            str(row["id"]): 0 for row in expected_contract["velocity_buckets"]
        }
        for slot in (
            INSTRUMENT_CANDIDATE_A,
            INSTRUMENT_CANDIDATE_B,
        ):
            report = coverage.get(slot)
            if not isinstance(report, Mapping) or set(report) != {
                "passed",
                "zone_count",
                "failed_zone_count",
                "duration_seconds",
                "summary",
                "zones",
            }:
                raise ValueError("keys coverage candidate report is invalid")
            validate_keys_coverage_report(
                {
                    **expected_contract,
                    **dict(report),
                    "probe_bpm": PROBE_BPM,
                    "status": "passed",
                    "functional_status": "passed",
                }
            )
            zones = report.get("zones")
            summary = report.get("summary")
            if (
                report.get("passed") is not True
                or report.get("failed_zone_count") != 0
                or report.get("zone_count") != coverage.get("zone_count")
                or report.get("duration_seconds") != coverage.get("duration_seconds")
                or not isinstance(zones, list)
                or not zones
                or not isinstance(summary, Mapping)
            ):
                raise ValueError("keys coverage candidate did not pass every used zone")
            current_geometry = [
                (
                    row.get("channel"),
                    row.get("pitch"),
                    row.get("velocity_bucket"),
                    row.get("tested_velocity"),
                    row.get("observed_velocity_minimum"),
                    row.get("observed_velocity_maximum"),
                    row.get("observed_note_count"),
                    row.get("start_seconds"),
                    row.get("note_end_seconds"),
                    row.get("window_end_seconds"),
                )
                for row in zones
                if isinstance(row, Mapping)
            ]
            if len(current_geometry) != len(zones):
                raise ValueError("keys coverage zone evidence is invalid")
            if geometry is None:
                geometry = current_geometry
                for row in zones:
                    bucket = str(row["velocity_bucket"])
                    if bucket not in bucket_counts:
                        raise ValueError("keys coverage velocity bucket is invalid")
                    bucket_counts[bucket] += 1
            elif current_geometry != geometry:
                raise ValueError(
                    "blind keys coverage candidates tested different zones"
                )
            numeric_summary: dict[str, float] = {}
            for key in (
                "minimum_rms_dbfs",
                "minimum_peak_dbfs",
                "minimum_active_above_pre_guard_db",
                "maximum_normalized_rms_deficit_db",
            ):
                value = summary.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise ValueError("keys coverage measurement summary is invalid")
                numeric_summary[key] = float(value)
            summaries[slot] = {
                "functional_status": "passed",
                "tested_zone_count": int(report["zone_count"]),
                "passed_zone_count": int(report["zone_count"]),
                "failed_zone_count": 0,
                **numeric_summary,
            }

        if geometry is None:
            raise ValueError("keys coverage tested no used zones")
        tested_pitch_count = len({(row[0], row[1]) for row in geometry})
        return {
            "schema": expected_contract["schema"],
            "required": True,
            "status": "passed",
            "functional_status": "passed",
            "quality_status": "review_required",
            "policy": expected_contract["policy"],
            "claim": expected_contract["claim"],
            "zone_definition": expected_contract["zone_definition"],
            "safe_pass_text": expected_contract["safe_pass_text"],
            "non_claims": list(expected_contract["non_claims"]),
            "velocity_buckets": [
                {
                    **dict(bucket),
                    "tested_zone_count": bucket_counts[str(bucket["id"])],
                    "status": (
                        "passed"
                        if bucket_counts[str(bucket["id"])]
                        else "not_exercised"
                    ),
                }
                for bucket in expected_contract["velocity_buckets"]
            ],
            "tested_zone_count": len(geometry),
            "tested_pitch_count": tested_pitch_count,
            "failed_zone_count": 0,
            "limits": dict(expected_contract["limits"]),
            "thresholds": dict(expected_contract["thresholds"]),
            "candidates": summaries,
            "candidate_identities_hidden": True,
            "actual_review_midi_changed": False,
        }

    def _public_master_review(
        self,
        prepared: Mapping[str, Any],
        *,
        selection: Mapping[str, Any],
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Register anonymous review audio and expose one path-free projection."""

        comparison_sha256 = str(prepared["comparison_sha256"])
        candidates: dict[str, Any] = {}
        for slot in (CANDIDATE_A, CANDIDATE_B):
            row = prepared.get("candidates", {}).get(slot)
            if not isinstance(row, Mapping):
                raise ValueError("Listening Master review candidate is invalid")
            record = self.server.master_reviews.media_record(
                comparison_sha256,
                slot,
            )
            media_id = f"listening-master-review-{slot}-{comparison_sha256[:24]}"
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            self._register_generated_media(media_id, private_record)
            # Do not expose candidate-specific applied gain, RMS or peak before
            # identity resolution. Those measurements can bias or partially
            # unblind the comparison even without an explicit assignment.
            candidates[slot] = {
                key: row[key]
                for key in ("sample_rate", "channels", "frames")
                if key in row
            }
            candidates[slot]["audio"] = {
                key: value for key, value in row["audio"].items() if key != "path"
            }
            candidates[slot]["audio_url"] = self._media_url(media_id)

        review_state = prepared.get("review_state", {})
        if not isinstance(review_state, Mapping):
            raise ValueError("Listening Master review state is invalid")
        review = None
        review_id = review_state.get("review_id")
        if review_state.get("reviewed") is True:
            if not isinstance(review_id, str):
                raise ValueError("Listening Master review identity is invalid")
            review = {
                "review_id": review_id,
                "review_sha256": review_state.get("review_sha256"),
                "revision": review_state.get("current_revision"),
                "response": review_state.get("response"),
                "choice": (
                    review_state.get("response", {}).get("choice")
                    if isinstance(review_state.get("response"), Mapping)
                    else None
                ),
                "review_url": (
                    "/api/listening-master-review-export?kind=review"
                    f"&review_id={review_id}&token={self.server.token}"
                ),
            }
        return {
            "schema": prepared.get("schema"),
            "status": prepared.get("status"),
            "blind": True,
            "comparison_sha256": comparison_sha256,
            "selection_manifest_sha256": selection.get("selection_manifest_sha256"),
            "balanced_arrangement_manifest_sha256": balanced.get("manifest_sha256"),
            "listening_master_manifest_sha256": listening_master.get("manifest_sha256"),
            "nonce_commitment": prepared.get("nonce_commitment"),
            "window": prepared.get("window"),
            "policy": prepared.get("policy"),
            "artifact_hashes": prepared.get("artifact_hashes"),
            "candidates": candidates,
            "allowed_problem_tags": sorted(MASTER_REVIEW_PROBLEM_TAGS),
            "maximum_problem_tags": MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE,
            "maximum_notes_characters": MAXIMUM_NOTES_CHARACTERS,
            "expected_revision": prepared.get("current_revision"),
            "review": review,
            "effects": prepared.get("effects"),
        }

    def _public_master_readiness(
        self,
        prepared: Mapping[str, Any],
        *,
        selection: Mapping[str, Any],
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Register native-level crops and expose a bounded direct projection."""

        comparison_sha256 = _require_lowercase_sha256(
            prepared.get("comparison_sha256"),
            label="native-level readiness comparison_sha256",
        )
        artifact_hashes = prepared.get("artifact_hashes")
        if (
            not isinstance(artifact_hashes, Mapping)
            or artifact_hashes.get("balanced_control_preview_sha256")
            != balanced.get("preview", {}).get("sha256")
            or artifact_hashes.get("listening_master_wav_sha256")
            != listening_master.get("master", {}).get("sha256")
            or artifact_hashes.get("listening_master_receipt_sha256")
            != listening_master.get("receipt", {}).get("sha256")
        ):
            raise WorkbenchMasterReadinessConflictError(
                "native-level readiness artifacts are no longer current"
            )

        candidates: dict[str, Any] = {}
        for identity in (BALANCED_CONTROL, LISTENING_MASTER):
            row = prepared.get("candidates", {}).get(identity)
            if not isinstance(row, Mapping):
                raise ValueError("native-level readiness candidate is invalid")
            record = self.server.master_readiness.media_record(
                comparison_sha256,
                identity,
            )
            media_id = f"listening-master-readiness-{identity}-{comparison_sha256[:24]}"
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            self._register_generated_media(media_id, private_record)
            candidates[identity] = {
                key: row[key]
                for key in (
                    "label",
                    "format",
                    "subtype",
                    "sample_rate",
                    "channels",
                    "frames",
                    "applied_gain_db",
                    "processing_applied",
                )
                if key in row
            }
            candidates[identity]["audio"] = {
                key: value
                for key, value in row.get("audio", {}).items()
                if key != "path"
            }
            candidates[identity]["audio_url"] = self._media_url(media_id)

        limits = prepared.get("limits")
        if not isinstance(limits, Mapping):
            raise ValueError("native-level readiness limits are invalid")
        review = prepared.get("review")
        public_review = None
        if review is not None:
            if not isinstance(review, Mapping):
                raise ValueError("native-level readiness review is invalid")
            readiness_review_id = _require_lowercase_sha256(
                review.get("readiness_review_id"),
                label="native-level readiness review identity",
            )
            readiness_review_sha256 = _require_lowercase_sha256(
                review.get("readiness_review_sha256"),
                label="native-level readiness review SHA-256",
            )
            public_review = {
                "readiness_review_id": readiness_review_id,
                "readiness_review_sha256": readiness_review_sha256,
                "response": review.get("response"),
                "choice": review.get("response", {}).get("choice"),
                "review_url": (
                    "/api/listening-master-readiness-export"
                    f"?readiness_review_id={readiness_review_id}"
                    f"&token={self.server.token}"
                ),
            }
        return {
            "schema": prepared.get("schema"),
            "status": prepared.get("status"),
            "identity_labelled": True,
            "native_level": True,
            "comparison_sha256": comparison_sha256,
            "selection_manifest_sha256": selection.get("selection_manifest_sha256"),
            "balanced_arrangement_manifest_sha256": balanced.get("manifest_sha256"),
            "listening_master_manifest_sha256": listening_master.get("manifest_sha256"),
            "quality_review": prepared.get("quality_review"),
            "artifact_hashes": dict(artifact_hashes),
            "window": prepared.get("window"),
            "policy": prepared.get("policy"),
            "candidates": candidates,
            "choices": prepared.get("choices"),
            "problem_tags": prepared.get("problem_tags"),
            "limits": dict(limits),
            "review": public_review,
            "effects": prepared.get("effects"),
        }

    def _public_clip_artifact(self, artifact: Mapping[str, Any]) -> dict[str, Any]:
        """Register derived Clip files and expose only capability URLs."""

        public = public_clip_artifact(artifact)
        for key, prefix in (("midi", "clip-midi"), ("preview", "clip-preview")):
            record = artifact.get(key)
            if not isinstance(record, Mapping):
                continue
            media_id = f"{prefix}-{str(record.get('sha256', ''))[:24]}"
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            self._register_generated_media(media_id, private_record)
            public_record = public.get(key)
            if not isinstance(public_record, Mapping):
                raise ValueError("Clip artifact public file record is invalid")
            public[key] = {
                **dict(public_record),
                "url": self._media_url(media_id),
            }
        if _mapping_contains_key(public, "path"):
            raise ValueError("Clip artifact exposed a private path")
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
                "audition_level",
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
            self._register_generated_media(media_id, private_record)
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
                    "audition_gain_db",
                    "audition_level",
                )
                if key in track
            }
            public_track["audio"] = {
                key: record[key] for key in ("name", "bytes", "sha256") if key in record
            }
            public_track["audio_url"] = self._media_url(media_id)
            tracks.append(public_track)
        public["tracks"] = tracks
        return public

    def _public_decoded_arrangement_loop(
        self, artifact: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Register one bounded private arrangement excerpt without paths."""

        public = {
            key: artifact[key]
            for key in (
                "schema",
                "selection_manifest_sha256",
                "start_seconds",
                "end_seconds",
                "duration_seconds",
                "cache_hit",
                "groups",
                "effects",
            )
            if key in artifact
        }
        tracks = []
        for track in artifact.get("tracks", []):
            if not isinstance(track, Mapping):
                raise ValueError("decoded arrangement track is invalid")
            record = track.get("audio")
            if not isinstance(record, Mapping):
                raise ValueError("decoded arrangement track audio is invalid")
            media_id = f"decoded-arrangement-{str(record['sha256'])[:24]}"
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            self._register_generated_media(media_id, private_record)
            public_track = {
                key: track[key]
                for key in (
                    "track_id",
                    "kind",
                    "stem_ids",
                    "roles",
                    "labels",
                    "stem_id",
                    "candidate_id",
                    "role",
                    "decision",
                    "sample_rate",
                    "channels",
                    "frames",
                    "start_frame",
                    "silence_padded_frames",
                )
                if key in track
            }
            public_track["audio"] = {
                key: record[key] for key in ("name", "bytes", "sha256") if key in record
            }
            public_track["audio_url"] = self._media_url(media_id)
            tracks.append(public_track)
        public["tracks"] = tracks
        return public

    def _public_decoded_arrangement_stream(
        self, artifact: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Return the immutable full-song plan without private snapshot paths."""

        public = {
            key: json.loads(json.dumps(artifact[key]))
            for key in (
                "schema",
                "stream_sha256",
                "selection_manifest_sha256",
                "preset",
                "preset_track_ids",
                "source_clock",
                "tracks",
                "anchor",
                "chunking",
                "policy",
                "renderer",
                "encoding",
                "resource_limits",
                "path_free_manifest",
                "private_audio",
                "effects",
                "cache_hit",
            )
            if key in artifact
        }
        if _mapping_contains_key(public, "path"):
            raise ValueError("decoded arrangement stream exposed a private path")
        return public

    def _register_decoded_stream_plan(self, plan: Mapping[str, Any]) -> None:
        """Keep only a small set of per-launch full-song capabilities."""

        stream_sha256 = str(plan.get("stream_sha256", ""))
        _require_lowercase_sha256(
            stream_sha256,
            label="decoded arrangement stream_sha256",
        )
        with self.server.state_lock:
            plans = self.server.decoded_stream_plans
            plans.pop(stream_sha256, None)
            plans[stream_sha256] = dict(plan)
            while len(plans) > _MAX_DECODED_STREAM_PLANS:
                plans.popitem(last=False)

    def _refresh_decoded_stream_plan(
        self, stream_sha256: str, expected: Mapping[str, Any]
    ) -> None:
        """Keep a successfully used stream active and fail closed after eviction."""

        with self.server.state_lock:
            plans = self.server.decoded_stream_plans
            active = plans.get(stream_sha256)
            if not isinstance(active, Mapping) or dict(active) != dict(expected):
                raise ValueError(
                    "decoded arrangement stream is not active; prepare its "
                    "full-song preset again"
                )
            plans.move_to_end(stream_sha256)

    def _public_decoded_arrangement_chunk(
        self, artifact: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Register one private chunk and return capability URLs only."""

        public = {
            key: json.loads(json.dumps(artifact[key]))
            for key in (
                "schema",
                "chunk_sha256",
                "stream_sha256",
                "selection_manifest_sha256",
                "preset",
                "chunk_index",
                "chunk_count",
                "anchor",
                "aggregate_output_bytes",
                "resource_limits",
                "effects",
                "cache_hit",
            )
            if key in artifact
        }
        tracks = []
        chunk_sha256 = str(artifact.get("chunk_sha256", ""))
        for track in artifact.get("tracks", []):
            if not isinstance(track, Mapping):
                raise ValueError("decoded arrangement chunk track is invalid")
            record = track.get("audio")
            if not isinstance(record, Mapping):
                raise ValueError("decoded arrangement chunk audio is invalid")
            media_id = (
                f"decoded-stream-{chunk_sha256[:20]}-"
                f"{str(record.get('sha256', ''))[:20]}"
            )
            private_record = dict(record)
            private_record["_freeze_on_serve"] = True
            self._register_generated_media(media_id, private_record)
            public_track = {
                key: json.loads(json.dumps(track[key]))
                for key in (
                    "track_id",
                    "kind",
                    "stem_ids",
                    "roles",
                    "stem_id",
                    "candidate_id",
                    "role",
                    "decision",
                    "sample_rate",
                    "channels",
                    "frames",
                    "start_frame",
                    "end_frame",
                    "silence_padded_frames",
                )
                if key in track
            }
            public_track["audio"] = {
                key: record[key] for key in ("name", "bytes", "sha256") if key in record
            }
            public_track["audio_url"] = self._media_url(media_id)
            tracks.append(public_track)
        public["tracks"] = tracks
        if _mapping_contains_key(public, "path"):
            raise ValueError("decoded arrangement chunk exposed a private path")
        return public

    def _register_generated_media(
        self, media_id: str, record: Mapping[str, Any]
    ) -> None:
        """Keep capability records bounded without deleting rebuildable files.

        A long decoded traversal can prepare hundreds of private chunk files.
        The filesystem cache owns their normal LRU lifecycle; this registry
        only owns per-launch URLs.  Evicting an old URL therefore produces a
        recoverable 404 and never removes project state or source evidence.
        """

        with self.server.state_lock:
            self.server.media[media_id] = dict(record)
            generated = self.server.generated_media_ids
            generated.pop(media_id, None)
            generated[media_id] = None
            while len(generated) > _MAX_GENERATED_MEDIA_RECORDS:
                expired_id, _ = generated.popitem(last=False)
                if expired_id not in self.server.catalog_media_ids:
                    self.server.media.pop(expired_id, None)

    def _serve_media(self, media_id: str) -> None:
        record = self.server.media.get(media_id)
        if not isinstance(record, Mapping):
            self._error(HTTPStatus.NOT_FOUND, "workbench media not found")
            return
        self._serve_file_record(
            record,
            phrase_review=bool(record.get("_review_page")),
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
        with handle, ExitStack() as response_stack:
            frozen_payload: bytes | None = None
            frozen_file: Any | None = None
            if phrase_review:
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
            elif freeze_verified:
                try:
                    frozen_file = _freeze_verified_immutable_file(
                        handle,
                        record,
                    )
                except ValueError:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "workbench media changed after it was catalogued; restart the Workbench",
                    )
                    return
                except OSError:
                    try:
                        self._error(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            "temporary verified media snapshot could not be created",
                        )
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                frozen_file = response_stack.enter_context(frozen_file)
                size = int(record["bytes"])
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
                    try:
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self._security_headers(phrase_review=phrase_review)
                        payload = str(exc).encode("utf-8")
                        self.send_header(
                            "Content-Type",
                            "text/plain; charset=utf-8",
                        )
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                status = HTTPStatus.PARTIAL_CONTENT
            content_type = (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            try:
                self.send_response(status)
                self._security_headers(phrase_review=phrase_review)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header(
                    "Content-Length",
                    str(max(0, end - start + 1)),
                )
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
                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{end}/{size}",
                    )
                self.end_headers()
                if frozen_payload is not None:
                    self.wfile.write(frozen_payload[start : end + 1])
                    return
                response_handle = frozen_file or handle
                response_handle.seek(start)
                remaining = max(0, end - start + 1)
                while remaining:
                    chunk = response_handle.read(min(64 * 1024, remaining))
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
        route = getattr(self, "_developer_trace_route", None)
        # Correction errors can be emitted before the application service runs
        # (for example, at an opt-in gate or while parsing JSON).  Keep those
        # traces request-only, while preserving the application checkpoint when
        # an invoked service reports a fixed 400/404/409 error envelope.
        application_invoked = getattr(self, "_developer_application_invoked", False)
        if (
            int(status) < 400
            or route not in _CLIP_CORRECTION_ROUTES
            or application_invoked
        ):
            facts = trace_response_facts(route, value) if route else {}
            self._developer_checkpoint(
                "application",
                developer_code_step_for_route(route) if route else "artifact.prepare",
                facts,
            )
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
        self._complete_developer_trace(status)
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


def _workbench_developer_bytes() -> bytes:
    """Load the optional read-only Developer Inspector browser module."""

    path = Path(__file__).with_name("workbench_developer.js")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"packaged Workbench developer module is unavailable: {path}"
        ) from exc


def _workbench_clips_bytes() -> bytes:
    """Load the optional read-only Phase 6 Clip Library browser module."""

    path = Path(__file__).with_name("workbench_clips.js")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"packaged Workbench Clip Library module is unavailable: {path}"
        ) from exc


def _workbench_master_review_bytes() -> bytes:
    """Load the bounded blind Listening Master review browser module."""

    path = Path(__file__).with_name("workbench_master_review.js")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"packaged Workbench master-review module is unavailable: {path}"
        ) from exc


def _workbench_instrument_review_bytes() -> bytes:
    """Load the bounded fixed-MIDI instrument-review browser module."""

    path = Path(__file__).with_name("workbench_instrument_review.js")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"packaged Workbench instrument-review module is unavailable: {path}"
        ) from exc


def _workbench_visualization_bytes() -> bytes:
    """Load bounded viewport helpers used by the local Workbench."""

    path = Path(__file__).with_name("workbench_visualization.js")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"packaged Workbench visualization is unavailable: {path}"
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
