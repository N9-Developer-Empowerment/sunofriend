"""Explicit, append-only Clip placement proposals for the local Workbench.

The first Phase 6 reuse slice deliberately stops at a proposal.  It records
where an immutable Clip could be placed on a fixed 4/4, TPQ-480 planning grid;
it does not render, transform, merge, export, or alter source/library state.

The store is separate from the Workbench review database and is lazy: reading
an empty plan does not create a directory or SQLite file.  The first explicit
``place`` or ``remove`` action creates an owner-only database and appends one
event.  Events are never updated or deleted.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import stat
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REUSE_CAPABILITY_SCHEMA = "sunofriend.workbench-clip-reuse-capability.v1"
REUSE_PLAN_SCHEMA = "sunofriend.workbench-clip-reuse-plan.v1"
REUSE_EVENT_SCHEMA = "sunofriend.workbench-clip-reuse-event.v1"
_POLICY_VERSION = "sunofriend.clip-reuse-proposal-policy.v1"
_GRID_VERSION = "sunofriend.recorded-zero-4-4-tpq480.v1"
_TICKS_PER_BEAT = 480
_BEATS_PER_BAR = 4
_MAXIMUM_ACTIVE_PLACEMENTS = 64
_MAXIMUM_EVENTS_PER_PLAN = 512
_MAXIMUM_CLIP_NOTE_COUNT = 20_000
_MAXIMUM_TOTAL_NOTE_COUNT = 40_000
_MAXIMUM_END_SECONDS = 20 * 60
_MAXIMUM_EVENT_JSON_BYTES = 256 * 1024

_TARGET_GRID = {
    "numerator": 4,
    "denominator": 4,
    "beats_per_bar": _BEATS_PER_BAR,
    "ticks_per_beat": _TICKS_PER_BEAT,
    "origin": "recorded-zero",
    "downbeat_status": "unconfirmed",
    "tick_in_beat_supported": False,
}
_LIMITS = {
    "maximum_active_placements": _MAXIMUM_ACTIVE_PLACEMENTS,
    "maximum_events_per_plan": _MAXIMUM_EVENTS_PER_PLAN,
    "maximum_clip_note_count": _MAXIMUM_CLIP_NOTE_COUNT,
    "maximum_total_note_count": _MAXIMUM_TOTAL_NOTE_COUNT,
    "maximum_end_seconds": _MAXIMUM_END_SECONDS,
}
_EFFECT_KEYS = (
    "reuse_plan_changed",
    "placement_added",
    "placement_removed",
    "library_changed",
    "clip_changed",
    "midi_changed",
    "transform_applied",
    "decisions_changed",
    "current_arrangement_changed",
    "pack_changed",
    "feedback_changed",
    "audition_preference_recorded",
    "submission_changed",
)


class WorkbenchClipReuseError(RuntimeError):
    """Base class for safe Clip reuse failures."""


class WorkbenchClipReuseConflictError(WorkbenchClipReuseError):
    """The submitted plan/object pins no longer describe current state."""


class WorkbenchClipReuseNotFoundError(WorkbenchClipReuseError):
    """A requested immutable Clip or active placement does not exist."""

    def __init__(self, kind: str) -> None:
        if kind not in {"clip", "placement"}:
            raise ValueError("reuse not-found kind must be clip or placement")
        self.kind = kind
        super().__init__(f"Clip reuse {kind} was not found")


class WorkbenchClipReuseEvidenceError(WorkbenchClipReuseError):
    """Pinned project, acceptance, library, or store evidence drifted."""


class WorkbenchClipReuseStore:
    """One lazy, append-only SQLite event store for reuse proposals."""

    def __init__(self, path: str | Path) -> None:
        self.path = _unresolved_absolute(path)
        self._lock = threading.RLock()

    def initialized(self) -> bool:
        """Return whether the lazy database exists, without creating it."""

        if not self.path.exists():
            if self.path.is_symlink():
                raise WorkbenchClipReuseEvidenceError(
                    "Clip reuse database path must not be a symlink"
                )
            return False
        _require_regular_nonsymlink(self.path, "Clip reuse database")
        return True

    def events(
        self,
        *,
        project_id: str,
        plan_id: str,
        binding_sha256: str,
    ) -> list[dict[str, Any]]:
        """Load and validate all events for one exact evidence binding."""

        with self._lock:
            if not self.path.exists():
                if self.path.is_symlink():
                    raise WorkbenchClipReuseEvidenceError(
                        "Clip reuse database path must not be a symlink"
                    )
                return []
            _require_regular_nonsymlink(self.path, "Clip reuse database")
            try:
                with self._connect(read_only=True) as connection:
                    rows = connection.execute(
                        """
                        SELECT event_id, schema_name, created_at, project_id, plan_id,
                               binding_sha256, revision, event_type,
                               placement_id, previous_plan_sha256,
                               resulting_plan_sha256, payload_json
                        FROM clip_reuse_events
                        WHERE plan_id = ? AND binding_sha256 = ?
                        ORDER BY revision
                        """,
                        (plan_id, binding_sha256),
                    ).fetchall()
            except (OSError, sqlite3.Error) as exc:
                raise WorkbenchClipReuseEvidenceError(
                    "Clip reuse event store is unavailable"
                ) from exc
            finally:
                self._chmod_store_files()
        return _event_rows(
            rows,
            project_id=project_id,
            plan_id=plan_id,
            binding_sha256=binding_sha256,
        )

    def append(
        self,
        *,
        project_id: str,
        plan_id: str,
        binding_sha256: str,
        expected_revision: int,
        expected_plan_sha256: str,
        event_type: str,
        placement_id: str,
        payload: Mapping[str, Any],
        resulting_plan_sha256: str,
    ) -> dict[str, Any]:
        """Atomically append one event if the caller still owns the plan head."""

        if event_type not in {"place", "remove"}:
            raise ValueError("invalid Clip reuse event type")
        revision = expected_revision + 1
        if revision > _MAXIMUM_EVENTS_PER_PLAN:
            raise ValueError("Clip reuse plan event limit reached")
        event_id = "reuse-event-" + uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        encoded_payload = _canonical_bytes(payload)
        if len(encoded_payload) > _MAXIMUM_EVENT_JSON_BYTES:
            raise ValueError("Clip reuse event is too large")

        with self._lock:
            self._prepare_for_write()
            try:
                with self._connect(read_only=False) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    latest = connection.execute(
                        """
                        SELECT revision, resulting_plan_sha256
                        FROM clip_reuse_events
                        WHERE plan_id = ? AND binding_sha256 = ?
                        ORDER BY revision DESC
                        LIMIT 1
                        """,
                        (plan_id, binding_sha256),
                    ).fetchone()
                    current_revision = 0 if latest is None else int(latest["revision"])
                    current_sha256 = (
                        expected_plan_sha256
                        if latest is None
                        else str(latest["resulting_plan_sha256"])
                    )
                    if (
                        current_revision != expected_revision
                        or current_sha256 != expected_plan_sha256
                    ):
                        raise WorkbenchClipReuseConflictError(
                            "Clip reuse plan head changed"
                        )
                    connection.execute(
                        """
                        INSERT INTO clip_reuse_events (
                            event_id, schema_name, created_at, project_id,
                            plan_id, binding_sha256, revision, event_type,
                            placement_id, previous_plan_sha256,
                            resulting_plan_sha256, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            REUSE_EVENT_SCHEMA,
                            created_at,
                            project_id,
                            plan_id,
                            binding_sha256,
                            revision,
                            event_type,
                            placement_id,
                            expected_plan_sha256,
                            resulting_plan_sha256,
                            encoded_payload.decode("utf-8"),
                        ),
                    )
                    connection.commit()
            except WorkbenchClipReuseConflictError:
                raise
            except sqlite3.IntegrityError as exc:
                raise WorkbenchClipReuseConflictError(
                    "Clip reuse plan head changed"
                ) from exc
            except (OSError, sqlite3.Error) as exc:
                raise WorkbenchClipReuseEvidenceError(
                    "Clip reuse event could not be appended"
                ) from exc
            finally:
                self._chmod_store_files()

        return {
            "event_id": event_id,
            "created_at": created_at,
            "project_id": project_id,
            "plan_id": plan_id,
            "binding_sha256": binding_sha256,
            "revision": revision,
            "event_type": event_type,
            "placement_id": placement_id,
            "previous_plan_sha256": expected_plan_sha256,
            "resulting_plan_sha256": resulting_plan_sha256,
            "payload": json.loads(encoded_payload),
        }

    def _prepare_for_write(self) -> None:
        parent = self.path.parent
        if parent.is_symlink():
            raise WorkbenchClipReuseEvidenceError(
                "Clip reuse state directory must not be a symlink"
            )
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent.is_dir() or parent.is_symlink():
            raise WorkbenchClipReuseEvidenceError(
                "Clip reuse state directory is invalid"
            )
        os.chmod(parent, 0o700)
        if self.path.exists():
            _require_regular_nonsymlink(self.path, "Clip reuse database")
        elif self.path.is_symlink():
            raise WorkbenchClipReuseEvidenceError(
                "Clip reuse database path must not be a symlink"
            )
        try:
            with self._connect(read_only=False) as connection:
                connection.executescript(
                    """
                    PRAGMA journal_mode = WAL;
                    PRAGMA foreign_keys = ON;
                    CREATE TABLE IF NOT EXISTS clip_reuse_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        schema_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL,
                        binding_sha256 TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision > 0),
                        event_type TEXT NOT NULL CHECK (
                            event_type IN ('place', 'remove')
                        ),
                        placement_id TEXT NOT NULL,
                        previous_plan_sha256 TEXT NOT NULL,
                        resulting_plan_sha256 TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        UNIQUE (plan_id, binding_sha256, revision)
                    );
                    CREATE INDEX IF NOT EXISTS idx_clip_reuse_plan_revision
                    ON clip_reuse_events(plan_id, binding_sha256, revision);
                    CREATE TRIGGER IF NOT EXISTS clip_reuse_events_no_update
                    BEFORE UPDATE ON clip_reuse_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Clip reuse events are append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS clip_reuse_events_no_delete
                    BEFORE DELETE ON clip_reuse_events
                    BEGIN
                        SELECT RAISE(ABORT, 'Clip reuse events are append-only');
                    END;
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise WorkbenchClipReuseEvidenceError(
                "Clip reuse event store could not be initialized"
            ) from exc
        self._chmod_store_files()

    def _chmod_store_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            _chmod_if_regular(Path(f"{self.path}{suffix}"), 0o600)

    def _connect(self, *, read_only: bool) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro",
                timeout=30.0,
                uri=True,
            )
        else:
            connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if read_only:
            connection.execute("PRAGMA query_only = ON")
        return connection


class WorkbenchClipReuseService:
    """Evidence-pinned, proposal-only placement service."""

    def __init__(
        self,
        *,
        clip_service: Any,
        catalog: Mapping[str, Any],
        store: WorkbenchClipReuseStore,
        binding_document: Mapping[str, Any],
    ) -> None:
        self._clip_service = clip_service
        self._catalog = catalog
        self._store = store
        self._binding_document = _json_copy(binding_document)
        self._binding_sha256 = _document_hash(self._binding_document)
        self._plan_id = "reuse-plan-" + self._binding_sha256
        self._target_project = _json_copy(self._binding_document["target_project"])
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        *,
        clip_service: Any,
        catalog: Mapping[str, Any],
        store_path: str | Path,
    ) -> "WorkbenchClipReuseService":
        if clip_service is None:
            raise ValueError("Clip reuse requires the gated Clip service")
        binding = _binding_document(clip_service, catalog)
        return cls(
            clip_service=clip_service,
            catalog=catalog,
            store=WorkbenchClipReuseStore(store_path),
            binding_document=binding,
        )

    def capability(self) -> dict[str, Any]:
        """Describe the opt-in proposal boundary without creating state."""

        with self._lock:
            self._require_stable_binding()
            return {
                "schema": REUSE_CAPABILITY_SCHEMA,
                "enabled": True,
                "proposal_only": True,
                "explicit_opt_in": True,
                "source_clips_read_only": True,
                "target_project": _json_copy(self._target_project),
                "target_grid": dict(_TARGET_GRID),
                "actions": {"place": True, "remove": True},
                "limits": dict(_LIMITS),
                "warnings": _planning_warnings(
                    self._target_project.get("downbeat")
                ),
                "effects": _effects(),
            }

    def compatibility(self, clip_id: str) -> dict[str, Any]:
        """Return only bounded, informational placement compatibility facts."""

        with self._lock:
            self._require_stable_binding()
            detail = self._clip_detail(clip_id)
            facts = _clip_facts(detail)
            comparison, warnings = self._compatibility(facts)
            placement_ready = self._placement_ready(facts)
            return {
                "proposal_enabled": True,
                "placement_ready": placement_ready,
                "target_project": _json_copy(self._target_project),
                "target_grid": dict(_TARGET_GRID),
                "clip": {
                    "clip_id": facts["clip_id"],
                    "object_sha256": facts["object_sha256"],
                    "key": facts["key"],
                    "bpm": facts["bpm"],
                },
                "comparison": comparison,
                "warnings": warnings,
                "transform_applied": False,
            }

    def plan(self) -> dict[str, Any]:
        """Read the current proposal; an empty read creates no state."""

        with self._lock:
            self._require_stable_binding()
            events = self._store.events(
                project_id=str(self._target_project["project_id"]),
                plan_id=self._plan_id,
                binding_sha256=self._binding_sha256,
            )
            return self._fold(events)

    def apply(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Append one explicit place/remove action with optimistic pins."""

        if not isinstance(request, Mapping):
            raise TypeError("Clip reuse action must be an object")
        action = request.get("action")
        if action == "place":
            expected_keys = {
                "action",
                "plan_id",
                "plan_sha256",
                "expected_revision",
                "clip_id",
                "clip_object_sha256",
                "target",
            }
        elif action == "remove":
            expected_keys = {
                "action",
                "plan_id",
                "plan_sha256",
                "expected_revision",
                "placement_id",
            }
        else:
            raise ValueError("Clip reuse action must be place or remove")
        _require_exact_keys(request, expected_keys, "Clip reuse action")
        plan_id = _identifier(request["plan_id"], "plan_id")
        plan_sha256 = _sha256(request["plan_sha256"], "plan_sha256")
        expected_revision = _nonnegative_exact_int(
            request["expected_revision"], "expected_revision"
        )

        with self._lock:
            self._require_stable_binding()
            events = self._store.events(
                project_id=str(self._target_project["project_id"]),
                plan_id=self._plan_id,
                binding_sha256=self._binding_sha256,
            )
            current = self._fold(events)
            if (
                plan_id != current["plan_id"]
                or plan_sha256 != current["plan_sha256"]
                or expected_revision != current["revision"]
            ):
                raise WorkbenchClipReuseConflictError(
                    "Clip reuse plan pins are stale"
                )
            if current["event_count"] >= _MAXIMUM_EVENTS_PER_PLAN:
                raise ValueError("Clip reuse plan event limit reached")

            if action == "place":
                placement = self._place_projection(request, current)
                placement_id = placement["placement_id"]
                payload: dict[str, Any] = {"placement": placement}
                projected_placements = [*current["placements"], placement]
            else:
                placement_id = _identifier(request["placement_id"], "placement_id")
                if not any(
                    item["placement_id"] == placement_id
                    for item in current["placements"]
                ):
                    raise WorkbenchClipReuseNotFoundError("placement")
                payload = {"placement_id": placement_id}
                projected_placements = [
                    item
                    for item in current["placements"]
                    if item["placement_id"] != placement_id
                ]

            resulting_revision = current["revision"] + 1
            resulting_sha256 = _plan_hash(
                plan_id=self._plan_id,
                binding_sha256=self._binding_sha256,
                revision=resulting_revision,
                placements=projected_placements,
            )
            self._require_stable_binding()
            self._store.append(
                project_id=str(self._target_project["project_id"]),
                plan_id=self._plan_id,
                binding_sha256=self._binding_sha256,
                expected_revision=current["revision"],
                expected_plan_sha256=current["plan_sha256"],
                event_type=action,
                placement_id=placement_id,
                payload=payload,
                resulting_plan_sha256=resulting_sha256,
            )
            self._require_stable_binding()
            result_plan = self._fold(
                self._store.events(
                    project_id=str(self._target_project["project_id"]),
                    plan_id=self._plan_id,
                    binding_sha256=self._binding_sha256,
                )
            )
            return {
                "operation": action,
                "plan": result_plan,
                "effects": _effects(
                    reuse_plan_changed=True,
                    placement_added=action == "place",
                    placement_removed=action == "remove",
                ),
            }

    def _place_projection(
        self,
        request: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        if len(current["placements"]) >= _MAXIMUM_ACTIVE_PLACEMENTS:
            raise ValueError("Clip reuse active placement limit reached")
        clip_id = _identifier(request["clip_id"], "clip_id")
        requested_object_sha256 = _sha256(
            request["clip_object_sha256"], "clip_object_sha256"
        )
        detail = self._clip_detail(clip_id)
        facts = _clip_facts(detail)
        if facts["object_sha256"] != requested_object_sha256:
            raise WorkbenchClipReuseConflictError("Clip object pin is stale")
        if facts["note_count"] > _MAXIMUM_CLIP_NOTE_COUNT:
            raise ValueError("Clip exceeds the placement note limit")
        total_notes = facts["note_count"] + sum(
            int(item["clip"]["note_count"]) for item in current["placements"]
        )
        if total_notes > _MAXIMUM_TOTAL_NOTE_COUNT:
            raise ValueError("Clip reuse plan exceeds the note instance limit")

        target = _target(request["target"])
        start_tick = (
            ((target["bar"] - 1) * _BEATS_PER_BAR) + (target["beat"] - 1)
        ) * _TICKS_PER_BEAT
        duration_ticks = _duration_ticks(facts["duration_beats"])
        nominal_end_tick = start_tick + duration_ticks
        bpm = float(self._target_project["bpm"])
        bpm_numerator, bpm_denominator = bpm.as_integer_ratio()
        if (
            nominal_end_tick * 60 * bpm_denominator
            > _MAXIMUM_END_SECONDS * _TICKS_PER_BEAT * bpm_numerator
        ):
            raise ValueError("Clip reuse placement exceeds the 20 minute bound")
        try:
            start_beat = start_tick / _TICKS_PER_BEAT
            nominal_end_beat = nominal_end_tick / _TICKS_PER_BEAT
        except OverflowError as exc:
            raise ValueError("Clip reuse target exceeds the planning grid") from exc
        if not math.isfinite(start_beat) or not math.isfinite(nominal_end_beat):
            raise ValueError("Clip reuse target exceeds the planning grid")
        comparison, warnings = self._compatibility(facts)
        overlap_count = sum(
            1
            for item in current["placements"]
            if start_tick < int(item["target"]["nominal_end_tick"])
            and int(item["target"]["start_tick"]) < nominal_end_tick
        )
        if overlap_count:
            warnings.append(
                _warning(
                    "placement-overlap",
                    (
                        "This proposed time range overlaps "
                        f"{overlap_count} active placement"
                        f"{'s' if overlap_count != 1 else ''}; no merge or mix is applied."
                    ),
                )
            )
        if not self._placement_ready(facts):
            raise ValueError("Clip is not ready for bounded placement")
        placement_revision = int(current["revision"]) + 1
        placement_seed = {
            "plan_id": self._plan_id,
            "placed_revision": placement_revision,
            "nonce": uuid.uuid4().hex,
        }
        placement_id = "reuse-placement-" + _document_hash(placement_seed)
        return {
            "placement_id": placement_id,
            "placed_revision": placement_revision,
            "clip": {
                "clip_id": facts["clip_id"],
                "object_sha256": facts["object_sha256"],
                "lineage_id": facts["lineage_id"],
                "revision": facts["revision"],
                "title": facts["title"],
                "role": facts["role"],
                "key": facts["key"],
                "bpm": facts["bpm"],
                "export_bpm": facts["export_bpm"],
                "note_count": facts["note_count"],
                "chord_count": facts["chord_count"],
                "duration_beats": facts["duration_beats"],
                "duration_ticks": duration_ticks,
                "timing_mode": facts["timing_mode"],
                "time_signature": dict(facts["time_signature"]),
                "instrument": dict(facts["instrument"]),
            },
            "target": {
                **target,
                "start_tick": start_tick,
                "start_beat": start_beat,
                "nominal_end_tick": nominal_end_tick,
                "nominal_end_beat": nominal_end_beat,
            },
            "compatibility": {
                "comparison": comparison,
                "warnings": warnings,
                "transform_applied": False,
                "render_ready": False,
            },
        }

    def _fold(self, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        placements: list[dict[str, Any]] = []
        revision = 0
        previous_sha256 = _plan_hash(
            plan_id=self._plan_id,
            binding_sha256=self._binding_sha256,
            revision=0,
            placements=(),
        )
        for event in events:
            if event["revision"] != revision + 1:
                raise WorkbenchClipReuseEvidenceError(
                    "Clip reuse event revisions are not contiguous"
                )
            if event["previous_plan_sha256"] != previous_sha256:
                raise WorkbenchClipReuseEvidenceError(
                    "Clip reuse event hash chain is invalid"
                )
            payload = event["payload"]
            if event["event_type"] == "place":
                if set(payload) != {"placement"} or not isinstance(
                    payload["placement"], Mapping
                ):
                    raise WorkbenchClipReuseEvidenceError(
                        "Stored Clip reuse placement is invalid"
                    )
                placement = _json_copy(payload["placement"])
                if placement.get("placement_id") != event["placement_id"]:
                    raise WorkbenchClipReuseEvidenceError(
                        "Stored Clip reuse placement identity is invalid"
                    )
                if any(
                    item["placement_id"] == placement["placement_id"]
                    for item in placements
                ):
                    raise WorkbenchClipReuseEvidenceError(
                        "Stored Clip reuse placement identity is duplicated"
                    )
                placements.append(placement)
                placements.sort(key=_placement_sort_key)
            else:
                if set(payload) != {"placement_id"} or payload.get(
                    "placement_id"
                ) != event["placement_id"]:
                    raise WorkbenchClipReuseEvidenceError(
                        "Stored Clip reuse removal is invalid"
                    )
                matching = [
                    item
                    for item in placements
                    if item["placement_id"] == event["placement_id"]
                ]
                if len(matching) != 1:
                    raise WorkbenchClipReuseEvidenceError(
                        "Stored Clip reuse removal has no active placement"
                    )
                placements = [
                    item
                    for item in placements
                    if item["placement_id"] != event["placement_id"]
                ]
                placements.sort(key=_placement_sort_key)
            revision = int(event["revision"])
            computed = _plan_hash(
                plan_id=self._plan_id,
                binding_sha256=self._binding_sha256,
                revision=revision,
                placements=placements,
            )
            if event["resulting_plan_sha256"] != computed:
                raise WorkbenchClipReuseEvidenceError(
                    "Stored Clip reuse result hash is invalid"
                )
            previous_sha256 = computed

        ordered = sorted(placements, key=_placement_sort_key)
        return {
            "schema": REUSE_PLAN_SCHEMA,
            "status": "empty" if not ordered else "proposed",
            "proposal_only": True,
            "restore_status": (
                "restored-exact-scope"
                if events
                else (
                    "empty-new-scope"
                    if self._store.initialized()
                    else "empty-uninitialised"
                )
            ),
            "plan_id": self._plan_id,
            "binding_sha256": self._binding_sha256,
            "plan_sha256": previous_sha256,
            "revision": revision,
            "event_count": len(events),
            "active_placement_count": len(ordered),
            "target_project": _json_copy(self._target_project),
            "target_grid": dict(_TARGET_GRID),
            "limits": dict(_LIMITS),
            "placements": ordered,
            "warnings": _planning_warnings(self._target_project.get("downbeat")),
            "effects": _effects(),
        }

    def _clip_detail(self, clip_id: Any) -> Mapping[str, Any]:
        requested = _identifier(clip_id, "clip_id")
        try:
            detail = self._clip_service.detail(requested)
        except KeyError as exc:
            raise WorkbenchClipReuseNotFoundError("clip") from exc
        if not isinstance(detail, Mapping):
            raise WorkbenchClipReuseEvidenceError("Clip detail is invalid")
        return detail

    def _compatibility(
        self, facts: Mapping[str, Any]
    ) -> tuple[dict[str, str], list[dict[str, str]]]:
        project_key = self._target_project.get("key")
        clip_key = facts.get("key")
        key_status = _comparison_status(project_key, clip_key, numeric=False)
        bpm_status = _comparison_status(
            self._target_project.get("bpm"), facts.get("bpm"), numeric=True
        )
        warnings: list[dict[str, str]] = []
        if key_status == "unknown":
            warnings.append(
                _warning(
                    "key-comparison-unavailable",
                    "The Clip and project do not both declare a comparable key.",
                )
            )
        elif key_status == "different":
            warnings.append(
                _warning(
                    "clip-key-differs",
                    "The Clip key differs from the project; no transposition is applied.",
                )
            )
        if bpm_status == "unknown":
            warnings.append(
                _warning(
                    "bpm-comparison-unavailable",
                    "The Clip and project do not both declare a comparable BPM.",
                )
            )
        elif bpm_status == "different":
            warnings.append(
                _warning(
                    "clip-bpm-differs",
                    "The Clip BPM differs from the project; no tempo transform is applied.",
                )
            )
        signature = facts["time_signature"]
        if signature != {"numerator": 4, "denominator": 4}:
            warnings.append(
                _warning(
                    "clip-time-signature-differs",
                    "The Clip time signature differs from the fixed 4/4 planning grid.",
                )
            )
        if facts["timing_mode"] == "stem_locked":
            warnings.append(
                _warning(
                    "clip-stem-locked-timing",
                    "This Clip requires its stated GarageBand tempo for source alignment.",
                )
            )
        if facts["note_count"] > _MAXIMUM_CLIP_NOTE_COUNT:
            warnings.append(
                _warning(
                    "clip-note-limit-exceeded",
                    "This Clip exceeds the proposal note-count limit.",
                )
            )
        warnings.extend(
            [
                _project_downbeat_warning(self._target_project.get("downbeat")),
                _warning(
                    "project-time-signature-unconfirmed",
                    "The 4/4 project grid is a planning assumption, not confirmed meter evidence.",
                ),
                _warning(
                    "instrument-not-attached",
                    "The proposal carries MIDI instrument metadata only; no playable instrument is attached.",
                ),
            ]
        )
        return {"key_status": key_status, "bpm_status": bpm_status}, warnings

    def _placement_ready(self, facts: Mapping[str, Any]) -> bool:
        bpm = self._target_project.get("bpm")
        if not _is_positive_finite(bpm):
            return False
        if int(facts["note_count"]) > _MAXIMUM_CLIP_NOTE_COUNT:
            return False
        duration_ticks = _duration_ticks(float(facts["duration_beats"]))
        return (
            duration_ticks / _TICKS_PER_BEAT * 60.0 / float(bpm)
            <= _MAXIMUM_END_SECONDS + 1e-9
        )

    def _require_stable_binding(self) -> None:
        try:
            current = _binding_document(self._clip_service, self._catalog)
        except WorkbenchClipReuseEvidenceError:
            raise
        except Exception as exc:
            raise WorkbenchClipReuseEvidenceError(
                "Clip reuse evidence is unavailable"
            ) from exc
        if _document_hash(current) != self._binding_sha256:
            raise WorkbenchClipReuseEvidenceError(
                "Clip reuse evidence changed; restart required"
            )


def _binding_document(
    clip_service: Any,
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(catalog, Mapping):
        raise ValueError("Workbench catalog must be an object")
    project_id = _identifier(catalog.get("project_id"), "project_id")
    setup = catalog.get("setup")
    if not isinstance(setup, Mapping):
        raise ValueError("Workbench project setup is missing")
    bpm = _positive_finite(setup.get("bpm"), "project BPM")
    key = _optional_bounded_text(setup.get("key"), "project key")
    tuning_hz = _optional_positive_finite(setup.get("tuning_hz"), "tuning_hz")
    downbeat = setup.get("downbeat")
    if downbeat is not None:
        downbeat = _nonnegative_finite(downbeat, "downbeat")

    stems = catalog.get("stems")
    if not isinstance(stems, Sequence) or isinstance(stems, (str, bytes)):
        raise ValueError("Workbench stems must be a list")
    setup_files = setup.get("files", [])
    if not isinstance(setup_files, Sequence) or isinstance(
        setup_files, (str, bytes)
    ):
        raise ValueError("Workbench setup files must be a list")
    setup_facts: list[dict[str, Any]] = []
    for record in setup_files:
        if not isinstance(record, Mapping):
            raise ValueError("Workbench setup file evidence is invalid")
        setup_sha256 = _sha256(record.get("sha256"), "setup file sha256")
        setup_bytes = _nonnegative_exact_int(
            record.get("bytes"), "setup file bytes"
        )
        path = record.get("path")
        if path is None:
            raise ValueError("Workbench setup file path is missing")
        _verify_source_file(path, setup_sha256, setup_bytes)
        setup_facts.append(
            {"sha256": setup_sha256, "bytes": setup_bytes}
        )
    setup_facts.sort(key=lambda item: (item["sha256"], item["bytes"]))

    source_facts: list[dict[str, Any]] = []
    for stem in stems:
        if not isinstance(stem, Mapping):
            raise ValueError("Workbench stem is invalid")
        stem_id = _identifier(stem.get("stem_id"), "stem_id")
        source = stem.get("source")
        if not isinstance(source, Mapping):
            raise ValueError("Workbench stem source evidence is missing")
        source_sha256 = _sha256(source.get("sha256"), "source sha256")
        source_bytes = _nonnegative_exact_int(source.get("bytes"), "source bytes")
        path = source.get("path") or stem.get("source_path")
        if path is None:
            raise ValueError("Workbench stem source path is missing")
        _verify_source_file(path, source_sha256, source_bytes)
        source_facts.append(
            {
                "stem_id": stem_id,
                "source_sha256": source_sha256,
                "source_bytes": source_bytes,
            }
        )
    source_facts.sort(key=lambda item: item["stem_id"])
    if len({item["stem_id"] for item in source_facts}) != len(source_facts):
        raise ValueError("Workbench stem ids must be unique")

    capability = clip_service.capability()
    if not isinstance(capability, Mapping):
        raise WorkbenchClipReuseEvidenceError("Clip capability is invalid")
    acceptance = capability.get("acceptance")
    library = capability.get("library")
    if not isinstance(acceptance, Mapping) or not isinstance(library, Mapping):
        raise WorkbenchClipReuseEvidenceError("Clip capability evidence is incomplete")
    if acceptance.get("status") != "passed":
        raise WorkbenchClipReuseEvidenceError("Phase 5 acceptance is not passed")
    return {
        "schema": "sunofriend.workbench-clip-reuse-binding.v1",
        "policy_version": _POLICY_VERSION,
        "grid_version": _GRID_VERSION,
        "target_project": {
            "project_id": project_id,
            "bpm": bpm,
            "key": key,
            "tuning_hz": tuning_hz,
            "downbeat": downbeat,
        },
        "setup_evidence": setup_facts,
        "source_evidence": source_facts,
        "acceptance": {
            "result_sha256": _sha256(
                acceptance.get("result_sha256"), "acceptance result sha256"
            ),
            "pack_sha256": _sha256(
                acceptance.get("pack_sha256"), "accepted pack sha256"
            ),
        },
        "library": {
            "state_sha256": _sha256(
                library.get("state_sha256"), "library state sha256"
            )
        },
        "grid": dict(_TARGET_GRID),
        "limits": dict(_LIMITS),
    }


def _clip_facts(detail: Mapping[str, Any]) -> dict[str, Any]:
    clip = detail.get("clip")
    if not isinstance(clip, Mapping):
        raise WorkbenchClipReuseEvidenceError("Clip detail has no Clip")
    timing = clip.get("timing_contract")
    duration = clip.get("duration")
    instrument = clip.get("instrument")
    if not all(isinstance(value, Mapping) for value in (timing, duration, instrument)):
        raise WorkbenchClipReuseEvidenceError("Clip detail musical facts are incomplete")
    signature = timing.get("time_signature")
    if not isinstance(signature, Mapping):
        raise WorkbenchClipReuseEvidenceError("Clip time signature is missing")
    facts = {
        "clip_id": _identifier(clip.get("clip_id"), "clip_id"),
        "object_sha256": _sha256(
            clip.get("object_sha256"), "clip object sha256"
        ),
        "lineage_id": _identifier(clip.get("lineage_id"), "lineage_id"),
        "revision": _positive_exact_int(clip.get("revision"), "clip revision"),
        "title": _bounded_text(clip.get("title"), "clip title", maximum=120),
        "role": _bounded_text(clip.get("role"), "clip role", maximum=80),
        "key": _optional_bounded_text(clip.get("key"), "clip key"),
        "bpm": _positive_finite(clip.get("bpm"), "clip bpm"),
        "export_bpm": _positive_finite(
            timing.get("export_bpm"), "clip export bpm"
        ),
        "note_count": _nonnegative_exact_int(
            clip.get("note_count"), "clip note_count"
        ),
        "chord_count": _nonnegative_exact_int(
            clip.get("chord_count"), "clip chord_count"
        ),
        "duration_beats": _nonnegative_finite(
            duration.get("beats"), "clip duration beats"
        ),
        "timing_mode": _bounded_text(
            timing.get("resolved_mode"), "clip timing mode", maximum=40
        ),
        "time_signature": {
            "numerator": _positive_exact_int(
                signature.get("numerator"), "time-signature numerator"
            ),
            "denominator": _positive_exact_int(
                signature.get("denominator"), "time-signature denominator"
            ),
        },
        "instrument": {
            "program": _program(instrument.get("program")),
            "channel": _channel(instrument.get("channel")),
            "is_drums": _boolean(instrument.get("is_drums"), "is_drums"),
        },
    }
    return facts


def _event_rows(
    rows: Sequence[sqlite3.Row],
    *,
    project_id: str,
    plan_id: str,
    binding_sha256: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if (
            row["schema_name"] != REUSE_EVENT_SCHEMA
            or row["project_id"] != project_id
            or row["plan_id"] != plan_id
            or row["binding_sha256"] != binding_sha256
            or row["event_type"] not in {"place", "remove"}
        ):
            raise WorkbenchClipReuseEvidenceError("Stored Clip reuse binding is invalid")
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError) as exc:
            raise WorkbenchClipReuseEvidenceError(
                "Stored Clip reuse event JSON is invalid"
            ) from exc
        if not isinstance(payload, Mapping):
            raise WorkbenchClipReuseEvidenceError(
                "Stored Clip reuse event payload is invalid"
            )
        result.append(
            {
                "event_id": str(row["event_id"]),
                "created_at": str(row["created_at"]),
                "project_id": str(row["project_id"]),
                "plan_id": str(row["plan_id"]),
                "binding_sha256": str(row["binding_sha256"]),
                "revision": int(row["revision"]),
                "event_type": str(row["event_type"]),
                "placement_id": str(row["placement_id"]),
                "previous_plan_sha256": _sha256(
                    row["previous_plan_sha256"], "previous plan sha256"
                ),
                "resulting_plan_sha256": _sha256(
                    row["resulting_plan_sha256"], "resulting plan sha256"
                ),
                "payload": dict(payload),
            }
        )
    return result


def _plan_hash(
    *,
    plan_id: str,
    binding_sha256: str,
    revision: int,
    placements: Sequence[Mapping[str, Any]],
) -> str:
    return _document_hash(
        {
            "schema": REUSE_PLAN_SCHEMA,
            "policy_version": _POLICY_VERSION,
            "plan_id": plan_id,
            "binding_sha256": binding_sha256,
            "revision": revision,
            "placements": sorted(placements, key=_placement_sort_key),
        }
    )


def _placement_sort_key(value: Mapping[str, Any]) -> tuple[int, int, str]:
    try:
        target = value["target"]
        return (
            int(target["start_tick"]),
            int(value["placed_revision"]),
            str(value["placement_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkbenchClipReuseEvidenceError(
            "Stored Clip reuse placement ordering facts are invalid"
        ) from exc


def _planning_warnings(downbeat: Any) -> list[dict[str, str]]:
    return [
        _warning(
            "planning-grid-assumes-4-4",
            "Placement uses a fixed 4/4 planning grid in this first reuse slice.",
        ),
        _project_downbeat_warning(downbeat),
    ]


def _project_downbeat_warning(downbeat: Any) -> dict[str, str]:
    if downbeat is None:
        return _warning(
            "project-downbeat-unconfirmed",
            "Bar 1 starts at recorded zero because no project downbeat is confirmed.",
        )
    return _warning(
        "project-downbeat-not-applied",
        (
            "Project downbeat evidence exists, but reuse v1 does not apply it; "
            "bar 1 starts at recorded zero."
        ),
    )


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _effects(**changes: bool) -> dict[str, bool]:
    if set(changes) - set(_EFFECT_KEYS):
        raise ValueError("unknown Clip reuse effect")
    result = {key: False for key in _EFFECT_KEYS}
    result.update(changes)
    return result


def _target(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("Clip reuse target must be an object")
    _require_exact_keys(value, {"bar", "beat", "tick_in_beat"}, "target")
    bar = _positive_exact_int(value["bar"], "target bar")
    beat = _positive_exact_int(value["beat"], "target beat")
    tick = _nonnegative_exact_int(value["tick_in_beat"], "target tick_in_beat")
    if beat > _BEATS_PER_BAR:
        raise ValueError("target beat must be between 1 and 4")
    if tick != 0:
        raise ValueError("tick_in_beat must be zero in reuse v1")
    return {"bar": bar, "beat": beat, "tick_in_beat": tick}


def _comparison_status(left: Any, right: Any, *, numeric: bool) -> str:
    if left is None or right is None:
        return "unknown"
    if numeric:
        try:
            return "match" if abs(float(left) - float(right)) <= 0.01 else "different"
        except (TypeError, ValueError):
            return "unknown"
    return "match" if str(left).casefold() == str(right).casefold() else "different"


def _duration_ticks(duration_beats: float) -> int:
    value = _nonnegative_finite(duration_beats, "clip duration beats")
    return max(0, int(math.ceil(value * _TICKS_PER_BEAT - 1e-9)))


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} has unexpected or missing fields")


def _identifier(value: Any, label: str) -> str:
    return _bounded_text(value, label, maximum=200)


def _bounded_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text or len(text) > maximum or any(ord(character) < 32 for character in text):
        raise ValueError(f"{label} is invalid")
    return text


def _optional_bounded_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, label, maximum=120)


def _sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 value")
    return value


def _exact_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _nonnegative_exact_int(value: Any, label: str) -> int:
    result = _exact_int(value, label)
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _positive_exact_int(value: Any, label: str) -> int:
    result = _exact_int(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_finite(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _optional_positive_finite(value: Any, label: str) -> float | None:
    return None if value is None else _positive_finite(value, label)


def _nonnegative_finite(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _is_positive_finite(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _program(value: Any) -> int:
    result = _exact_int(value, "instrument program")
    if not 0 <= result <= 127:
        raise ValueError("instrument program must be between 0 and 127")
    return result


def _channel(value: Any) -> int:
    result = _exact_int(value, "instrument channel")
    if not 0 <= result <= 15:
        raise ValueError("instrument channel must be between 0 and 15")
    return result


def _verify_source_file(path_value: Any, sha256: str, byte_count: int) -> None:
    if not isinstance(path_value, (str, os.PathLike)):
        raise ValueError("Workbench source path is invalid")
    path = _unresolved_absolute(path_value)
    _require_regular_nonsymlink(path, "Workbench source")
    digest = hashlib.sha256()
    count = 0
    try:
        with path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                count += len(block)
                digest.update(block)
    except OSError as exc:
        raise WorkbenchClipReuseEvidenceError(
            "Workbench source evidence is unavailable"
        ) from exc
    if count != byte_count or digest.hexdigest() != sha256:
        raise WorkbenchClipReuseEvidenceError(
            "Workbench source evidence changed; restart required"
        )


def _require_regular_nonsymlink(path: Path, label: str) -> None:
    try:
        status = path.lstat()
    except OSError as exc:
        raise WorkbenchClipReuseEvidenceError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise WorkbenchClipReuseEvidenceError(f"{label} must be a regular file")


def _chmod_if_regular(path: Path, mode: int) -> None:
    try:
        status = path.lstat()
        if stat.S_ISREG(status.st_mode):
            os.chmod(path, mode)
    except OSError:
        return


def _unresolved_absolute(value: str | Path | os.PathLike[str]) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Clip reuse value must be finite JSON") from exc


def _document_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical_bytes(value))
