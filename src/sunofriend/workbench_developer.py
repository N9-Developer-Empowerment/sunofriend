"""Read-only, path-free developer inspection for the local Workbench.

This is deliberately an application-level trace, not a Python debugger.  It
records only explicit operation checkpoints and derives a small safe state
projection.  It never captures request bodies, headers, exception messages,
stack frames, local variables, filesystem locations or private listening
notes.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any, Mapping, Sequence

from .workbench_privacy import contains_local_path, path_free_role
from .workbench_store import fold_workbench_events


WORKBENCH_DEVELOPER_SNAPSHOT_SCHEMA = (
    "sunofriend.workbench-developer-snapshot.v1"
)
_MAX_COMPLETED_OPERATIONS = 128
_MAX_ACTIVE_OPERATIONS = 32
_MAX_FRAMES_PER_OPERATION = 8
_MAX_STEMS = 256
_MAX_DECISIONS = 1024
_MAX_REPLAY_FRAMES = 128
_MAX_CACHE_ENTRIES_PER_FAMILY = 4096
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CACHE_FAMILIES = (
    "previews",
    "decoded-stem-loops",
    "decoded-arrangement-loops",
    "decoded-arrangement-streams",
    "decoded-arrangement-chunks",
    "arrangements",
    "handoffs",
    "packs",
)
_DECISIONS = frozenset({"main", "optional", "needs_correction", "reject"})
_CONTEXTS = frozenset({"solo", "full_mix"})
_OUTCOMES = frozenset(
    {"equivalent", "none_usable", "cannot_tell", "clear_choice"}
)
_PROBLEM_TAGS = frozenset(
    {
        "missing_notes",
        "extra_notes",
        "wrong_pitch_or_octave",
        "starts_early_or_late",
        "ends_early_or_late",
        "mixed_roles",
        "poor_timing",
        "none_match",
    }
)

_ROUTE_OPERATIONS = {
    "/api/project": "project.read",
    "/api/timeline": "timeline.read",
    "/api/arrangement-timeline": "arrangement_timeline.read",
    "/api/garageband-pack-plan": "pack.plan",
    "/api/review": "review.export",
    "/api/events": "decision.append",
    "/api/render-preview": "preview.render",
    "/api/decoded-loop": "stem_loop.prepare",
    "/api/decoded-arrangement-loop": "arrangement_loop.prepare",
    "/api/decoded-arrangement-stream": "arrangement_stream.prepare",
    "/api/decoded-arrangement-chunk": "arrangement_chunk.prepare",
    "/api/arrangement": "arrangement.render",
    "/api/garageband-export": "handoff.build",
    "/api/garageband-pack-basket": "pack_basket.save",
    "/api/garageband-pack": "pack.build",
    "/api/clips": "clip_library.browse",
    "/api/clips/{clip_id}": "clip_library.detail",
    "/api/clip-artifact": "clip_library.artifact",
    "/api/clip-reuse-plan": "clip_reuse.read",
    "/api/clip-reuse-action": "clip_reuse.change",
    "/api/clip-transform-projection": "clip_transform.preview",
    "/api/clip-transform-action": "clip_transform.create",
    "/api/clip-note-correction-window": "clip_correction.window",
    "/api/clip-note-correction-projection": "clip_correction.preview",
    "/api/clip-note-correction-action": "clip_correction.create",
}

_ROUTE_CODE_STEPS = {
    "/api/project": "project.read",
    "/api/timeline": "timeline.read",
    "/api/arrangement-timeline": "arrangement_timeline.read",
    "/api/review": "review.export",
    "/api/events": "decision.append",
    "/api/render-preview": "preview.render",
    "/api/decoded-loop": "stem_loop.prepare",
    "/api/decoded-arrangement-loop": "arrangement_loop.prepare",
    "/api/decoded-arrangement-stream": "arrangement_stream.prepare",
    "/api/decoded-arrangement-chunk": "arrangement_chunk.prepare",
    "/api/arrangement": "arrangement.render",
    "/api/garageband-export": "handoff.build",
    "/api/garageband-pack-plan": "pack.plan",
    "/api/garageband-pack-basket": "pack_basket.save",
    "/api/garageband-pack": "pack.build",
    "/api/clips": "clip_library.browse",
    "/api/clips/{clip_id}": "clip_library.detail",
    "/api/clip-artifact": "clip_library.artifact",
    "/api/clip-reuse-plan": "clip_reuse.read",
    "/api/clip-reuse-action": "clip_reuse.change",
    "/api/clip-transform-projection": "clip_transform.preview",
    "/api/clip-transform-action": "clip_transform.create",
    "/api/clip-note-correction-window": "clip_correction.window",
    "/api/clip-note-correction-projection": "clip_correction.preview",
    "/api/clip-note-correction-action": "clip_correction.create",
}

_CODE_MAP = {
    "request.get": {
        "module": "sunofriend.workbench_server",
        "symbol": "_WorkbenchHandler.do_GET",
    },
    "request.post": {
        "module": "sunofriend.workbench_server",
        "symbol": "_WorkbenchHandler.do_POST",
    },
    "validate": {
        "module": "sunofriend.workbench_server",
        "symbol": "_WorkbenchHandler._request_json",
    },
    "decision.append": {
        "module": "sunofriend.workbench_store",
        "symbol": "WorkbenchStore.append",
    },
    "state.derive": {
        "module": "sunofriend.workbench_store",
        "symbol": "WorkbenchStore.current_state",
    },
    "project.read": {
        "module": "sunofriend.workbench_server",
        "symbol": "_WorkbenchHandler._project_payload",
    },
    "timeline.read": {
        "module": "sunofriend.workbench_timeline",
        "symbol": "build_stem_timeline",
    },
    "arrangement_timeline.read": {
        "module": "sunofriend.workbench_timeline",
        "symbol": "build_arrangement_timeline",
    },
    "review.export": {
        "module": "sunofriend.workbench_store",
        "symbol": "WorkbenchStore.export_review",
    },
    "preview.render": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.render_candidate_preview",
    },
    "arrangement.select": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.decoded_arrangement_selection_manifest",
    },
    "stem_loop.prepare": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.prepare_decoded_stem_loop",
    },
    "arrangement_loop.prepare": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.prepare_decoded_arrangement_loop",
    },
    "arrangement_stream.prepare": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.prepare_decoded_arrangement_stream",
    },
    "arrangement_chunk.prepare": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.prepare_decoded_arrangement_chunk",
    },
    "arrangement.render": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.render_arrangement",
    },
    "handoff.build": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.build_garageband_handoff",
    },
    "artifact.prepare": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts",
    },
    "pack.plan": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.garageband_pack_plan",
    },
    "pack_basket.save": {
        "module": "sunofriend.workbench_store",
        "symbol": "WorkbenchStore.save_pack_selection",
    },
    "pack.build": {
        "module": "sunofriend.workbench_artifacts",
        "symbol": "WorkbenchArtifacts.build_garageband_pack",
    },
    "clip_library.browse": {
        "module": "sunofriend.workbench_clips",
        "symbol": "WorkbenchClipService.browse",
    },
    "clip_library.detail": {
        "module": "sunofriend.workbench_clips",
        "symbol": "WorkbenchClipService.detail",
    },
    "clip_library.artifact": {
        "module": "sunofriend.workbench_clips",
        "symbol": "WorkbenchClipService.prepare_artifact",
    },
    "clip_reuse.read": {
        "module": "sunofriend.workbench_reuse",
        "symbol": "WorkbenchClipReuseService.plan",
    },
    "clip_reuse.change": {
        "module": "sunofriend.workbench_reuse",
        "symbol": "WorkbenchClipReuseService.apply",
    },
    "clip_transform.preview": {
        "module": "sunofriend.workbench_transform",
        "symbol": "WorkbenchClipTransformService.preview",
    },
    "clip_transform.create": {
        "module": "sunofriend.workbench_transform",
        "symbol": "WorkbenchClipTransformService.create",
    },
    "clip_correction.window": {
        "module": "sunofriend.workbench_correction",
        "symbol": "WorkbenchClipCorrectionService.window",
    },
    "clip_correction.preview": {
        "module": "sunofriend.workbench_correction",
        "symbol": "WorkbenchClipCorrectionService.preview",
    },
    "clip_correction.create": {
        "module": "sunofriend.workbench_correction",
        "symbol": "WorkbenchClipCorrectionService.create",
    },
    "clip_version.append": {
        "module": "sunofriend.library",
        "symbol": "ClipLibrary.append_version_if_state",
    },
    "publish": {
        "module": "sunofriend.workbench_server",
        "symbol": "_WorkbenchHandler._json",
    },
}

_OPERATION_LABELS = {
    "project.read": "Load the path-free project projection",
    "timeline.read": "Build bounded source and MIDI visual evidence",
    "arrangement_timeline.read": "Derive the selected arrangement timeline",
    "pack.plan": "Derive the exact eligible GarageBand pack plan",
    "review.export": "Export the full private local review",
    "decision.append": "Validate and append one durable review event",
    "preview.render": "Render or reuse a neutral MIDI preview",
    "stem_loop.prepare": "Prepare one exact short comparison loop",
    "arrangement_loop.prepare": "Prepare one-clock arrangement presets",
    "arrangement_stream.prepare": "Freeze a bounded full-song stream plan",
    "arrangement_chunk.prepare": "Verify and decode one bounded stream chunk",
    "arrangement.render": "Render or reuse the selected arrangement proxy",
    "handoff.build": "Build the compatibility GarageBand handoff",
    "pack_basket.save": "Save a separate export-basket revision",
    "pack.build": "Build and verify an exact local ZIP",
    "clip_library.browse": "Browse verified immutable Clip objects",
    "clip_library.detail": "Inspect one Clip and its version lineage",
    "clip_library.artifact": "Reconstruct deterministic MIDI or a dry proxy",
    "clip_reuse.read": "Read the separate explicit Clip reuse proposal",
    "clip_reuse.change": "Append one explicit Clip placement or removal",
    "clip_transform.preview": "Preview one immutable Clip version without writing",
    "clip_transform.create": "Append one explicitly confirmed immutable Clip version",
    "clip_correction.window": "Read one bounded immutable Clip note window",
    "clip_correction.preview": "Preview an exact pitch correction without writing",
    "clip_correction.create": "Append one explicitly confirmed corrected Clip version",
}

_CODE_FLOW_NODES = (
    {
        "id": "browser",
        "label": "Browser intent",
        "explanation": (
            "The Workbench sends an allow-listed route plus stable IDs or hashes; "
            "temporary play, zoom, mute and level controls stay in the tab."
        ),
        "symbols": ["workbench.html::api"],
        "invariant": "Browser state is not a musical decision or pack-basket revision.",
    },
    {
        "id": "boundary",
        "label": "Loopback trust boundary",
        "explanation": (
            "The server checks loopback origin, the launch token, route and request "
            "shape before application code runs."
        ),
        "symbols": [
            "sunofriend.workbench_server._WorkbenchHandler.do_GET",
            "sunofriend.workbench_server._WorkbenchHandler.do_POST",
        ],
        "invariant": "The browser cannot submit a local path or arbitrary track roster.",
    },
    {
        "id": "state",
        "label": "Append or derive state",
        "explanation": (
            "Explicit decisions append immutable SQLite events. Current musical state "
            "is rebuilt by replaying those events through one pure reducer."
        ),
        "symbols": [
            "sunofriend.workbench_store.WorkbenchStore.append",
            "sunofriend.workbench_store.fold_workbench_events",
            "sunofriend.workbench_reuse.WorkbenchClipReuseStore",
            "sunofriend.library.ClipLibrary.append_version_if_state",
        ],
        "invariant": (
            "Pack choices and Clip reuse proposals remain separate from musical "
            "decision events."
        ),
    },
    {
        "id": "artifact",
        "label": "Derive or build artifact",
        "explanation": (
            "Selection, preview, transport and pack operations are derived from the "
            "catalog plus current state and use verified content identities."
        ),
        "symbols": [
            "sunofriend.workbench_artifacts.WorkbenchArtifacts",
            "sunofriend.workbench_clips.WorkbenchClipService",
            "sunofriend.workbench_transform.WorkbenchClipTransformService",
            "sunofriend.workbench_correction.WorkbenchClipCorrectionService",
        ],
        "invariant": "Original candidate MIDI is copied or rendered without mutation.",
    },
    {
        "id": "publish",
        "label": "Publish safe response",
        "explanation": (
            "Only an explicit path-free projection or a capability-protected local "
            "artifact is returned to the browser."
        ),
        "symbols": ["sunofriend.workbench_server._WorkbenchHandler._json"],
        "invariant": "Developer snapshots omit paths, notes, bodies, tokens and errors.",
    },
)


def developer_operation_for_route(route: str) -> str | None:
    """Return the fixed operation identity for an allow-listed API route."""

    return _ROUTE_OPERATIONS.get(_normalise_route(route))


def developer_code_step_for_route(route: str) -> str:
    """Return a fixed application symbol group for one allow-listed route."""

    return _ROUTE_CODE_STEPS.get(_normalise_route(route), "artifact.prepare")


def _normalise_route(route: str) -> str:
    if route.startswith("/api/clips/"):
        return "/api/clips/{clip_id}"
    return route


class WorkbenchDeveloperTrace:
    """A bounded, memory-only operation trace for one opted-in server launch."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._next_sequence = 1
        self._active: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._completed: deque[dict[str, Any]] = deque(
            maxlen=_MAX_COMPLETED_OPERATIONS
        )
        self._dropped_completed = 0
        self._dropped_active = 0

    def begin(self, method: str, operation: str) -> int | None:
        if method not in {"GET", "POST"} or operation not in set(
            _ROUTE_OPERATIONS.values()
        ):
            return None
        with self._lock:
            if len(self._active) >= _MAX_ACTIVE_OPERATIONS:
                self._dropped_active += 1
                return None
            sequence = self._next_sequence
            self._next_sequence += 1
            now = time.monotonic_ns()
            record = {
                "sequence": sequence,
                "operation": operation,
                "label": _OPERATION_LABELS[operation],
                "method": method,
                "status": "running",
                "durable_effect_possible": operation
                in {
                    "decision.append",
                    "pack_basket.save",
                    "clip_reuse.change",
                    "clip_transform.create",
                    "clip_correction.create",
                },
                "symbols": _operation_symbols(operation),
                "started_ns": now,
                "frames": [],
            }
            self._active[sequence] = record
            request_step = "request.get" if method == "GET" else "request.post"
            self._checkpoint_locked(record, "request", request_step, {})
            return sequence

    def checkpoint(
        self,
        sequence: int | None,
        stage: str,
        code_step: str,
        facts: Mapping[str, Any] | None = None,
    ) -> None:
        if sequence is None:
            return
        with self._lock:
            record = self._active.get(sequence)
            if record is None:
                return
            self._checkpoint_locked(record, stage, code_step, facts or {})

    def complete(
        self,
        sequence: int | None,
        http_status: int,
        facts: Mapping[str, Any] | None = None,
    ) -> None:
        if sequence is None:
            return
        with self._lock:
            record = self._active.pop(sequence, None)
            if record is None:
                return
            result = _safe_trace_facts(facts or {})
            if result:
                self._checkpoint_locked(record, "publish", "publish", result)
            ended = time.monotonic_ns()
            record["status"] = _status_name(http_status)
            record["http_status"] = int(http_status)
            record["duration_ms"] = round(
                max(0, ended - int(record.pop("started_ns"))) / 1_000_000,
                3,
            )
            if len(self._completed) == self._completed.maxlen:
                self._dropped_completed += 1
            self._completed.append(_copy_operation(record, active=False))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic_ns()
            active = []
            for record in self._active.values():
                copied = _copy_operation(record, active=True)
                copied["duration_ms"] = round(
                    max(0, now - int(record["started_ns"])) / 1_000_000,
                    3,
                )
                active.append(copied)
            return {
                "active_operations": active,
                "recent_operations": [dict(row) for row in self._completed],
                "first_retained_sequence": (
                    self._completed[0]["sequence"] if self._completed else None
                ),
                "last_sequence": self._next_sequence - 1,
                "dropped_completed_count": self._dropped_completed,
                "dropped_active_count": self._dropped_active,
                "completed_limit": _MAX_COMPLETED_OPERATIONS,
                "active_limit": _MAX_ACTIVE_OPERATIONS,
                "frame_limit": _MAX_FRAMES_PER_OPERATION,
            }

    def _checkpoint_locked(
        self,
        record: dict[str, Any],
        stage: str,
        code_step: str,
        facts: Mapping[str, Any],
    ) -> None:
        frames = record["frames"]
        if len(frames) >= _MAX_FRAMES_PER_OPERATION:
            return
        safe_code_step = code_step if code_step in _CODE_MAP else "artifact.prepare"
        frame = {
            "index": len(frames),
            "stage": _bounded_plain(stage, fallback="step", maximum=40),
            "code_step": safe_code_step,
            "label": _frame_label(stage),
            "explanation": _frame_explanation(stage),
            "symbol": _code_symbol(safe_code_step),
            "elapsed_ms": round(
                max(0, time.monotonic_ns() - int(record["started_ns"]))
                / 1_000_000,
                3,
            ),
            "facts": _safe_trace_facts(facts),
        }
        frames.append(frame)


def build_developer_snapshot(
    catalog: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    events: Sequence[Mapping[str, Any]],
    arrangement_selection: Mapping[str, Any] | None,
    pack_plan: Mapping[str, Any] | None,
    clip_reuse_plan: Mapping[str, Any] | None = None,
    trace: Mapping[str, Any],
    runtime: Mapping[str, Any],
    cache: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a strict projection with no private text or filesystem locations."""

    state = _developer_state(catalog, current)
    snapshot = {
        "schema": WORKBENCH_DEVELOPER_SNAPSHOT_SCHEMA,
        "mode": {
            "enabled": True,
            "read_only": True,
            "scope": "this_server_launch",
            "granularity": "explicit_operation_checkpoints",
            "persisted": False,
        },
        "code_flow": {
            "nodes": [
                {**node, "symbols": list(node["symbols"])}
                for node in _CODE_FLOW_NODES
            ],
            "stages": [
                "catalog",
                "validate",
                "append_or_derive",
                "cache_or_build",
                "verify",
                "publish",
            ],
            "code_map": {key: dict(value) for key, value in _CODE_MAP.items()},
        },
        "current": {
            "catalog": _catalog_summary(catalog),
            "durable_state": {
                "decision_event_count": int(current.get("event_count", 0) or 0),
                "pack_basket": _pack_summary(pack_plan),
                "clip_reuse_plan": _reuse_plan_summary(clip_reuse_plan),
            },
            "derived_state": state,
            "arrangement_selection": _selection_summary(arrangement_selection),
        },
        "state_replay": _state_replay(catalog, events),
        "runtime": {
            **_safe_runtime(runtime),
            "trace": dict(trace),
        },
        "cache": dict(cache),
        "privacy": {
            "local_locations_included": False,
            "private_notes_included": False,
            "request_payloads_included": False,
            "headers_or_session_secrets_included": False,
            "exception_text_included": False,
        },
        "effects": {
            "workbench_event_appended": False,
            "musical_selection_changed": False,
            "pack_selection_changed": False,
            "clip_reuse_plan_changed": False,
            "clip_version_appended": False,
            "artifact_built": False,
            "midi_mutated": False,
            "audio_mutated": False,
        },
    }
    _assert_safe_snapshot(snapshot)
    return snapshot


def artifact_cache_summary(root: Path, *, verified_stream_entries: int) -> dict[str, Any]:
    """Count only allow-listed cache directories without returning their names."""

    families = []
    for family in _CACHE_FAMILIES:
        parent = root / family
        completed = 0
        building = 0
        ignored = 0
        visited = 0
        truncated = False
        try:
            entries = parent.iterdir() if parent.is_dir() and not parent.is_symlink() else ()
            for entry in entries:
                visited += 1
                if visited > _MAX_CACHE_ENTRIES_PER_FAMILY:
                    truncated = True
                    break
                try:
                    usable_directory = entry.is_dir() and not entry.is_symlink()
                except OSError:
                    ignored += 1
                    continue
                if not usable_directory:
                    ignored += 1
                elif _SHA256.fullmatch(entry.name):
                    completed += 1
                elif entry.name.startswith(".") and ".building-" in entry.name:
                    building += 1
                else:
                    ignored += 1
        except OSError:
            ignored += 1
        families.append(
            {
                "family": family,
                "completed_entry_count": completed,
                "building_entry_count": building,
                "ignored_entry_count": ignored,
                "scan_truncated": truncated,
            }
        )
    return {
        "families": families,
        "verified_stream_memory_entry_count": max(0, int(verified_stream_entries)),
        "entry_scan_limit_per_family": _MAX_CACHE_ENTRIES_PER_FAMILY,
        "contains_entry_names": False,
    }


def trace_response_facts(route: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Select a few safe result facts; never copy an API response wholesale."""

    route = _normalise_route(route)
    if "error" in value:
        return {}
    if route == "/api/events":
        event = value.get("event", {})
        state = value.get("state", {})
        return {
            "event_type": event.get("event_type"),
            "decision_event_count": state.get("event_count"),
        }
    if route == "/api/project":
        return {
            "stem_count": len(value.get("stems", [])),
            "decision_event_count": value.get("state", {}).get("event_count"),
        }
    if route == "/api/garageband-pack-plan":
        plan = value.get("plan", {})
        return {
            "schema": plan.get("schema"),
            "item_count": len(plan.get("items", [])),
            "build_blocked": plan.get("build_blocked"),
        }
    if route == "/api/clips":
        page = value.get("page", {})
        return {
            "schema": value.get("schema"),
            "item_count": page.get("returned"),
        }
    if route == "/api/clips/{clip_id}":
        return {"schema": value.get("schema"), "item_count": 1}
    if route in {"/api/clip-reuse-plan", "/api/clip-reuse-action"}:
        plan = value.get("plan", {})
        if not isinstance(plan, Mapping):
            return {}
        placements = plan.get("placements", [])
        return {
            "schema": plan.get("schema"),
            "plan_revision": plan.get("revision"),
            "active_placement_count": (
                len(placements) if isinstance(placements, list) else None
            ),
        }
    if route in {
        "/api/clip-transform-projection",
        "/api/clip-transform-action",
        "/api/clip-note-correction-window",
        "/api/clip-note-correction-projection",
        "/api/clip-note-correction-action",
    }:
        if route.endswith("window"):
            wrapper = "window"
        elif route.endswith("projection"):
            wrapper = "projection"
        else:
            wrapper = "result"
        document = value.get(wrapper, {})
        if not isinstance(document, Mapping):
            return {}
        effects = document.get("effects", {})
        if not isinstance(effects, Mapping):
            effects = {}
        return {
            "schema": document.get("schema"),
            "clip_version_appended": effects.get("library_mutated", False),
        }
    wrapper_by_route = {
        "/api/render-preview": "preview",
        "/api/decoded-loop": "loop",
        "/api/decoded-arrangement-loop": "loop",
        "/api/decoded-arrangement-stream": "stream",
        "/api/decoded-arrangement-chunk": "chunk",
        "/api/arrangement": "arrangement",
        "/api/garageband-export": "handoff",
        "/api/garageband-pack": "pack",
        "/api/garageband-pack-basket": "basket",
        "/api/clip-artifact": "artifact",
    }
    key = wrapper_by_route.get(route)
    row = value.get(key, {}) if key else value
    if not isinstance(row, Mapping):
        return {}
    return {
        "schema": row.get("schema"),
        "cache_hit": row.get("cache_hit"),
        "track_count": len(row.get("tracks", [])) if "tracks" in row else None,
    }


def _state_replay(
    catalog: Mapping[str, Any], events: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a bounded, note-free replay through the production reducer."""

    rows = list(events)
    retained_event_count = min(len(rows), _MAX_REPLAY_FRAMES - 1)
    first_event_index = len(rows) - retained_event_count
    baseline = fold_workbench_events(catalog, rows[:first_event_index])
    frames = [
        {
            "frame_index": 0,
            "event_index": first_event_index,
            "event": {
                "event_type": "replay_baseline",
                "omitted_prior_event_count": first_event_index,
            },
            "before": None,
            "after": _replay_state_summary(catalog, baseline, None),
            "diff": [],
        }
    ]
    previous = baseline
    for event_index in range(first_event_index, len(rows)):
        event = rows[event_index]
        current = fold_workbench_events(catalog, rows[: event_index + 1])
        stem_id = str(event.get("stem_id", ""))
        before = _replay_stem(catalog, previous, stem_id)
        after = _replay_stem(catalog, current, stem_id)
        frames.append(
            {
                "frame_index": len(frames),
                "event_index": event_index + 1,
                "event": _safe_replay_event(event),
                "before": _replay_state_summary(catalog, previous, stem_id),
                "after": _replay_state_summary(catalog, current, stem_id),
                "diff": _top_level_diff(before, after),
            }
        )
        previous = current
    return {
        "schema": "sunofriend.workbench-state-replay.v1",
        "shared_reducer": "sunofriend.workbench_store.fold_workbench_events",
        "frames": frames,
        "total_event_count": len(rows),
        "retained_event_count": retained_event_count,
        "omitted_event_count": first_event_index,
        "frame_limit": _MAX_REPLAY_FRAMES,
    }


def _safe_replay_event(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type = event.get("event_type")
    result: dict[str, Any] = {
        "event_type": event_type if event_type in {
            "candidate_decision",
            "stem_outcome",
            "role_tag",
            "candidate_auditioned",
        } else "unknown",
        "stem_id": _safe_identifier(str(event.get("stem_id", ""))),
    }
    candidate_id = event.get("candidate_id")
    if candidate_id is not None:
        result["candidate_id"] = _safe_identifier(str(candidate_id))
    payload = event.get("payload", {})
    if not isinstance(payload, Mapping):
        return result
    context = payload.get("context")
    if context in _CONTEXTS:
        result["context"] = context
    if event_type == "candidate_decision":
        decision = payload.get("decision")
        result["decision"] = decision if decision in _DECISIONS else None
        result["problem_tags"] = sorted(
            tag for tag in payload.get("problem_tags", []) if tag in _PROBLEM_TAGS
        )
    elif event_type == "stem_outcome":
        outcome = payload.get("outcome")
        result["outcome"] = outcome if outcome in _OUTCOMES else None
    elif event_type == "role_tag":
        role, redacted = path_free_role(payload.get("role"))
        result["role"] = role
        result["role_redacted"] = redacted
    return result


def _replay_stem(
    catalog: Mapping[str, Any], state: Mapping[str, Any], stem_id: str
) -> dict[str, Any] | None:
    for row in _developer_state(catalog, state)["stems"]:
        if row["stem_id"] == _safe_identifier(stem_id):
            saved = row["saved_candidates"]
            return {
                "stem_id": row["stem_id"],
                "role": row["role"],
                "role_redacted": row["role_redacted"],
                "outcome": row["outcome"],
                "main_candidate_id": row["main_candidate_id"],
                "saved_candidate_count": len(saved),
                "active_selected_candidate_count": sum(
                    1 for candidate in saved if candidate["selection_active"]
                ),
                "auditioned_candidate_count": row["auditioned_candidate_count"],
            }
    return None


def _replay_state_summary(
    catalog: Mapping[str, Any], state: Mapping[str, Any], stem_id: str | None
) -> dict[str, Any]:
    projection = _developer_state(catalog, state)
    active_selected_count = sum(
        1
        for stem in projection["stems"]
        for candidate in stem["saved_candidates"]
        if candidate["selection_active"]
    )
    return {
        "event_count": max(0, int(state.get("event_count", 0) or 0)),
        "active_selected_candidate_count": active_selected_count,
        "changed_stem": _replay_stem(catalog, state, stem_id) if stem_id else None,
    }


def _top_level_diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> list[str]:
    before_row = before or {}
    after_row = after or {}
    return sorted(
        key
        for key in set(before_row) | set(after_row)
        if before_row.get(key) != after_row.get(key)
    )


def _developer_state(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    current_stems = current.get("stems", {})
    if not isinstance(current_stems, Mapping):
        current_stems = {}
    rows = []
    decision_count = 0
    stem_truncated_count = 0
    decision_truncated_count = 0
    for stem_index, stem in enumerate(catalog.get("stems", [])):
        if stem_index >= _MAX_STEMS:
            stem_truncated_count += 1
            continue
        if not isinstance(stem, Mapping):
            continue
        original_stem_id = str(stem.get("stem_id", ""))
        state = current_stems.get(original_stem_id, {})
        if not isinstance(state, Mapping):
            state = {}
        known_candidates = {
            str(candidate.get("candidate_id", ""))
            for candidate in stem.get("candidates", [])
            if isinstance(candidate, Mapping)
        }
        saved = state.get("candidates", {})
        if not isinstance(saved, Mapping):
            saved = {}
        candidates = []
        for candidate_id in known_candidates:
            decision = saved.get(candidate_id)
            if not isinstance(decision, Mapping):
                continue
            if decision_count >= _MAX_DECISIONS:
                decision_truncated_count += 1
                continue
            decision_count += 1
            value = decision.get("decision")
            context = decision.get("context")
            candidates.append(
                {
                    "candidate_id": _safe_identifier(candidate_id),
                    "decision": value if value in _DECISIONS else None,
                    "context": context if context in _CONTEXTS else None,
                    "problem_tags": sorted(
                        {
                            tag
                            for tag in decision.get("problem_tags", [])
                            if tag in _PROBLEM_TAGS
                        }
                    ),
                    "selection_active": decision.get("selection_active") is True,
                }
            )
        candidates.sort(key=lambda row: row["candidate_id"])
        outcome = state.get("outcome")
        outcome_value = outcome.get("value") if isinstance(outcome, Mapping) else None
        role, role_redacted = path_free_role(state.get("role") or stem.get("role"))
        rows.append(
            {
                "stem_id": _safe_identifier(original_stem_id),
                "role": role,
                "role_redacted": role_redacted,
                "outcome": outcome_value if outcome_value in _OUTCOMES else None,
                "main_candidate_id": (
                    _safe_identifier(str(state.get("main_candidate_id")))
                    if state.get("main_candidate_id") is not None
                    else None
                ),
                "saved_candidates": candidates,
                "auditioned_candidate_count": len(
                    state.get("auditioned_candidates", [])
                    if isinstance(state.get("auditioned_candidates"), list)
                    else []
                ),
            }
        )
    total_stems = len(catalog.get("stems", []))
    if total_stems > _MAX_STEMS:
        stem_truncated_count = total_stems - _MAX_STEMS
    return {
        "stems": rows,
        "shown_stem_count": len(rows),
        "shown_saved_candidate_count": decision_count,
        "truncated_stem_count": stem_truncated_count,
        "truncated_saved_candidate_count": decision_truncated_count,
    }


def _catalog_summary(catalog: Mapping[str, Any]) -> dict[str, Any]:
    stems = [stem for stem in catalog.get("stems", []) if isinstance(stem, Mapping)]
    setup = catalog.get("setup", {})
    if not isinstance(setup, Mapping):
        setup = {}
    return {
        "schema": catalog.get("schema"),
        "project_id": _safe_identifier(str(catalog.get("project_id", ""))),
        "stem_count": len(stems),
        "candidate_count": sum(len(stem.get("candidates", [])) for stem in stems),
        "setup": {
            "bpm": _finite_number(setup.get("bpm")),
            "key": _bounded_plain(setup.get("key"), fallback=None, maximum=40),
            "tuning_hz": _finite_number(setup.get("tuning_hz")),
            "downbeat_known": setup.get("downbeat") is not None,
        },
    }


def _selection_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"available": False}
    groups = value.get("groups", {})
    if not isinstance(groups, Mapping):
        groups = {}
    return {
        "available": True,
        "schema": value.get("schema"),
        "selection_manifest_sha256": _safe_sha256(
            value.get("selection_manifest_sha256")
        ),
        "source_track_count": len(value.get("sources", [])),
        "selected_midi_track_count": len(value.get("selected_midi", [])),
        "preset_track_counts": {
            preset: len(groups.get(preset, []))
            for preset in ("source-only", "selected-midi", "hybrid", "main-only")
        },
    }


def _pack_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"available": False}
    basket = value.get("basket", {})
    if not isinstance(basket, Mapping):
        basket = {}
    kind_counts: dict[str, int] = {}
    for item in value.get("items", []):
        if not isinstance(item, Mapping):
            continue
        kind = item.get("kind")
        if kind in {"selected_midi", "arrangement_proxy", "source_audio"}:
            kind_counts[str(kind)] = kind_counts.get(str(kind), 0) + 1
    return {
        "available": True,
        "schema": value.get("schema"),
        "plan_sha256": _safe_sha256(value.get("plan_sha256")),
        "basket_scope_sha256": _safe_sha256(value.get("basket_scope_sha256")),
        "item_counts": kind_counts,
        "build_blocked": value.get("build_blocked") is True,
        "block_reasons": [
            reason
            for reason in value.get("block_reasons", [])
            if reason
            in {
                "no-selected-midi",
                "selected-midi-overlap-needs-full-mix-confirmation",
            }
        ],
        "basket": {
            "revision": max(0, int(basket.get("revision", 0) or 0)),
            "saved": basket.get("saved") is True,
            "plan_current": basket.get("plan_current") is not False,
            "included_item_count": len(basket.get("included_item_ids", [])),
            "source_audio_opt_in": basket.get("source_audio_opt_in") is True,
        },
    }


def _reuse_plan_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return only bounded proposal identity/count facts for the Inspector."""

    if not isinstance(value, Mapping):
        return {
            "enabled": False,
            "proposal_only": True,
            "revision": 0,
            "active_placement_count": 0,
        }
    placements = value.get("placements", [])
    if not isinstance(placements, list):
        placements = []
    revision = value.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int):
        revision = 0
    restore_status = value.get("restore_status")
    if restore_status not in {
        "empty-uninitialised",
        "empty-new-scope",
        "restored-exact-scope",
    }:
        restore_status = "unavailable"
    return {
        "enabled": True,
        "proposal_only": value.get("proposal_only") is True,
        "plan_id": _safe_identifier(value.get("plan_id")),
        "binding_sha256": _safe_sha256(value.get("binding_sha256")),
        "plan_sha256": _safe_sha256(value.get("plan_sha256")),
        "revision": max(0, revision),
        "active_placement_count": min(len(placements), 64),
        "restore_status": restore_status,
    }


def _safe_runtime(value: Mapping[str, Any]) -> dict[str, Any]:
    integer_keys = {
        "catalog_media_capability_count",
        "generated_media_capability_count",
        "generated_media_capability_limit",
        "decoded_stream_plan_count",
        "decoded_stream_plan_limit",
        "clip_library_clip_count",
        "clip_reuse_plan_revision",
        "clip_reuse_active_placement_count",
    }
    return {
        **{
            key: max(0, int(value.get(key, 0) or 0))
            for key in integer_keys
        },
        "clip_library_enabled": value.get("clip_library_enabled") is True,
        "clip_reuse_plan_enabled": value.get("clip_reuse_plan_enabled") is True,
        "clip_transforms_enabled": value.get("clip_transforms_enabled") is True,
        "clip_corrections_enabled": value.get("clip_corrections_enabled") is True,
    }


def _safe_trace_facts(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema",
        "event_type",
        "decision_event_count",
        "stem_count",
        "item_count",
        "track_count",
        "build_blocked",
        "cache_hit",
        "plan_revision",
        "active_placement_count",
        "clip_version_appended",
    }
    result = {}
    for key in allowed:
        item = value.get(key)
        if item is None:
            continue
        if key in {
            "build_blocked",
            "cache_hit",
            "clip_version_appended",
        } and isinstance(item, bool):
            result[key] = item
        elif key in {
            "decision_event_count",
            "stem_count",
            "item_count",
            "track_count",
            "plan_revision",
            "active_placement_count",
        } and isinstance(item, int) and not isinstance(item, bool):
            result[key] = max(0, item)
        elif key == "event_type" and item in {
            "candidate_decision",
            "stem_outcome",
            "role_tag",
            "candidate_auditioned",
        }:
            result[key] = item
        elif key == "schema" and isinstance(item, str) and len(item) <= 100:
            result[key] = item
    return result


def _operation_symbols(operation: str) -> list[str]:
    operation_step = operation if operation in _CODE_MAP else "artifact.prepare"
    steps = ["request.get", "request.post"]
    if operation.startswith("decision"):
        steps.extend(["validate", "decision.append", "state.derive"])
    elif operation == "pack.plan":
        steps.extend(["state.derive", "pack.plan"])
    elif operation == "pack_basket.save":
        steps.extend(["validate", "pack_basket.save"])
    elif operation == "pack.build":
        steps.extend(["validate", "pack.plan", "pack.build"])
    elif operation == "clip_reuse.change":
        steps.extend(["validate", "clip_reuse.change"])
    elif operation == "clip_transform.preview":
        steps.extend(["validate", "clip_transform.preview"])
    elif operation == "clip_transform.create":
        steps.extend(
            ["validate", "clip_transform.create", "clip_version.append"]
        )
    elif operation in {
        "clip_correction.window",
        "clip_correction.preview",
    }:
        steps.extend(["validate", operation_step])
    elif operation == "clip_correction.create":
        steps.extend(
            ["validate", "clip_correction.create", "clip_version.append"]
        )
    else:
        steps.append(operation_step)
    steps.append("publish")
    return [_code_symbol(step) for step in steps]


def _code_symbol(code_step: str) -> str:
    record = _CODE_MAP.get(code_step, _CODE_MAP["artifact.prepare"])
    return f"{record['module']}.{record['symbol']}"


def _frame_label(stage: str) -> str:
    return {
        "request": "Request accepted by the operation trace",
        "validate": "Bounded request shape validated",
        "result": "Application result projected",
        "publish": "Response completed",
    }.get(stage, "Application checkpoint")


def _frame_explanation(stage: str) -> str:
    return {
        "request": (
            "The trace records only a fixed operation name and method, never the "
            "query, secret, headers or payload."
        ),
        "validate": (
            "The production handler accepted the bounded JSON object before "
            "calling application code."
        ),
        "result": (
            "Only allow-listed counts, schema and cache facts were copied into "
            "the diagnostic trace."
        ),
        "publish": (
            "The response status and elapsed time completed this memory-only "
            "operation record."
        ),
    }.get(stage, "A fixed application boundary was reached.")


def _copy_operation(record: Mapping[str, Any], *, active: bool) -> dict[str, Any]:
    result = {
        "sequence": record["sequence"],
        "operation": record["operation"],
        "label": record["label"],
        "method": record["method"],
        "status": "running" if active else record["status"],
        "durable_effect_possible": record["durable_effect_possible"],
        "symbols": list(record["symbols"]),
        "frames": [
            {**frame, "facts": dict(frame.get("facts", {}))}
            for frame in record.get("frames", [])
        ],
    }
    if not active:
        result["http_status"] = record["http_status"]
        result["duration_ms"] = record["duration_ms"]
    return result


def _status_name(status: int) -> str:
    if 200 <= int(status) < 300:
        return "completed"
    if int(status) == 409:
        return "conflict"
    if 400 <= int(status) < 500:
        return "rejected"
    return "failed"


def _safe_identifier(value: str) -> str:
    text = value.strip()
    if _SAFE_IDENTIFIER.fullmatch(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"redacted-{digest}"


def _safe_sha256(value: Any) -> str | None:
    text = str(value or "")
    return text if _SHA256.fullmatch(text) else None


def _bounded_plain(value: Any, *, fallback: Any, maximum: int) -> Any:
    if value is None:
        return fallback
    text = str(value).strip()
    if (
        not text
        or len(text) > maximum
        or any(ord(character) < 32 for character in text)
        or contains_local_path(text)
    ):
        return fallback
    return text


def _finite_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not (-1e12 < number < 1e12):
        return None
    return value


def _assert_safe_snapshot(value: Any) -> None:
    forbidden_keys = {
        "path",
        "paths",
        "root",
        "token",
        "notes",
        "body",
        "headers",
        "query",
        "exception",
        "message",
        "url",
    }

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if str(key).lower() in forbidden_keys:
                    raise ValueError("developer snapshot contains a forbidden field")
                visit(child)
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for child in item:
                visit(child)
        elif isinstance(item, str) and contains_local_path(item):
            raise ValueError("developer snapshot contains a local location")

    visit(value)
