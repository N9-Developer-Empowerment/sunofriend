"""Append-only local decisions for the Sunofriend Workbench."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


WORKBENCH_EVENT_SCHEMA = "sunofriend.workbench-event.v1"
WORKBENCH_REVIEW_SCHEMA = "sunofriend.workbench-review.v1"
WORKBENCH_PACK_SELECTION_SCHEMA = "sunofriend.workbench-pack-selection.v1"
WORKBENCH_PACK_BASKET_SCHEMA = "sunofriend.workbench-garageband-pack-basket.v1"
_PACK_BASKET_FIELDS = frozenset(
    {
        "schema",
        "project_id",
        "basket_scope_sha256",
        "included_item_ids",
        "source_audio_opt_in",
        "basket_sha256",
    }
)
_EVENT_TYPES = {
    "candidate_decision",
    "stem_outcome",
    "role_tag",
    "candidate_auditioned",
}


class WorkbenchPackStateConflictError(RuntimeError):
    """Raised when a Pack Composer save uses a stale basket revision."""

    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            "Pack Composer basket revision conflict: "
            f"expected {expected_revision}, current revision is {current_revision}"
        )


_CANDIDATE_DECISIONS = {"main", "optional", "needs_correction", "reject"}
_STEM_OUTCOMES = {"equivalent", "none_usable", "cannot_tell", "clear_choice"}
_LISTENING_CONTEXTS = {"solo", "full_mix"}
_PROBLEM_TAGS = {
    "missing_notes",
    "extra_notes",
    "wrong_pitch_or_octave",
    "starts_early_or_late",
    "ends_early_or_late",
    "mixed_roles",
    "poor_timing",
    "none_match",
}


class WorkbenchStore:
    """A small SQLite event store; existing rows are never updated or deleted."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def append(
        self, project: Mapping[str, Any], request: Mapping[str, Any]
    ) -> dict[str, Any]:
        event = _validated_event(project, request)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO decision_events (
                    event_id, schema_name, created_at, project_id, stem_id,
                    candidate_id, event_type, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["schema"],
                    event["created_at"],
                    event["project_id"],
                    event["stem_id"],
                    event.get("candidate_id"),
                    event["event_type"],
                    json.dumps(event["payload"], sort_keys=True, separators=(",", ":")),
                ),
            )
        return event

    def events(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, schema_name, created_at, project_id, stem_id,
                       candidate_id, event_type, payload_json
                FROM decision_events
                WHERE project_id = ?
                ORDER BY sequence ASC
                """,
                (project_id,),
            ).fetchall()
        return [
            {
                "event_id": row[0],
                "schema": row[1],
                "created_at": row[2],
                "project_id": row[3],
                "stem_id": row[4],
                "candidate_id": row[5],
                "event_type": row[6],
                "payload": json.loads(row[7]),
            }
            for row in rows
        ]

    def current_state(self, project: Mapping[str, Any]) -> dict[str, Any]:
        states: dict[str, dict[str, Any]] = {}
        for stem in project.get("stems", []):
            states[str(stem["stem_id"])] = {
                "role": stem.get("role"),
                "review_context_sha256": stem.get("review_context_sha256"),
                "outcome": None,
                "candidates": {},
                "main_candidate_id": None,
                "auditioned_candidates": [],
            }
        applied_event_count = 0
        for event in self.events(str(project["project_id"])):
            stem = states.get(event["stem_id"])
            if stem is None:
                continue
            applied_event_count += 1
            payload = event["payload"]
            review_context = payload.get("review_context", {})
            review_context_sha256 = review_context.get("sha256")
            if event["event_type"] == "candidate_decision":
                stem["candidates"][event["candidate_id"]] = {
                    "decision": payload["decision"],
                    "context": payload["context"],
                    "problem_tags": list(payload.get("problem_tags", [])),
                    "notes": payload.get("notes"),
                    "review_context_sha256": review_context_sha256,
                    "event_id": event["event_id"],
                    "created_at": event["created_at"],
                }
                if payload["decision"] == "main":
                    stem["main_candidate_id"] = event["candidate_id"]
                elif stem["main_candidate_id"] == event["candidate_id"]:
                    stem["main_candidate_id"] = None
            elif event["event_type"] == "stem_outcome":
                stem["outcome"] = {
                    "value": payload["outcome"],
                    "context": payload["context"],
                    "review_context_sha256": review_context_sha256,
                    "event_id": event["event_id"],
                    "created_at": event["created_at"],
                }
            elif event["event_type"] == "role_tag":
                stem["role"] = payload["role"]
            elif event["event_type"] == "candidate_auditioned":
                candidate_id = event.get("candidate_id")
                if candidate_id and candidate_id not in stem["auditioned_candidates"]:
                    stem["auditioned_candidates"].append(candidate_id)
        return {"stems": states, "event_count": applied_event_count}

    def export_review(self, project: Mapping[str, Any]) -> dict[str, Any]:
        project_id = str(project["project_id"])
        events = self.events(project_id)
        current = self.current_state(project)
        local_project = {
            "project_id": project_id,
            "name": project.get("name"),
            "root": project.get("root"),
            "setup": project.get("setup"),
            "catalog_source": project.get("catalog_source"),
            "review_contexts": [
                {
                    "stem_id": stem.get("stem_id"),
                    "review_context_sha256": stem.get("review_context_sha256"),
                    "review_question": stem.get("review_question"),
                    "listening_focus": list(stem.get("listening_focus", [])),
                }
                for stem in project.get("stems", [])
            ],
        }
        review = {
            "schema": WORKBENCH_REVIEW_SCHEMA,
            "status": "reviewed"
            if _review_complete(project, current)
            else "in_progress",
            "exported_at": _utc_now(),
            "project": local_project,
            "current": current,
            "events": events,
        }
        review["contribution_preview"] = contribution_preview(project, current, events)
        review["review_sha256"] = _document_hash(review)
        return review

    def save_pack_selection(
        self,
        project_id: str,
        basket: Mapping[str, Any],
        plan_sha256: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Append one explicit Pack Composer basket revision.

        Pack selections are deliberately isolated from musical decision events.
        The caller supplies the revision it last observed; a stale save fails
        rather than overwriting or merging another browser's basket.
        """

        validated_project_id = _pack_identifier(project_id, label="project_id")
        validated_basket = _validated_pack_basket(validated_project_id, basket)
        validated_plan_sha256 = _sha256_text(plan_sha256, label="plan_sha256")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")

        basket_scope_sha256 = str(validated_basket["basket_scope_sha256"])
        event_id = str(uuid.uuid4())
        saved_at = _utc_now()
        basket_json = json.dumps(
            validated_basket, sort_keys=True, separators=(",", ":")
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT revision
                FROM pack_selection_events
                WHERE project_id = ? AND basket_scope_sha256 = ?
                ORDER BY revision DESC, sequence DESC
                LIMIT 1
                """,
                (validated_project_id, basket_scope_sha256),
            ).fetchone()
            current_revision = int(row[0]) if row is not None else 0
            if current_revision != expected_revision:
                raise WorkbenchPackStateConflictError(
                    expected_revision=expected_revision,
                    current_revision=current_revision,
                )
            revision = current_revision + 1
            connection.execute(
                """
                INSERT INTO pack_selection_events (
                    event_id, schema_name, saved_at, project_id,
                    basket_scope_sha256, revision, saved_plan_sha256,
                    basket_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    WORKBENCH_PACK_SELECTION_SCHEMA,
                    saved_at,
                    validated_project_id,
                    basket_scope_sha256,
                    revision,
                    validated_plan_sha256,
                    basket_json,
                ),
            )

        return {
            **validated_basket,
            "revision": revision,
            "event_id": event_id,
            "saved_at": saved_at,
            "saved_plan_sha256": validated_plan_sha256,
            "saved": True,
        }

    def current_pack_selection(
        self, project_id: str, basket_scope_sha256: str
    ) -> dict[str, Any] | None:
        """Return the latest saved basket for one project/scope, if any."""

        validated_project_id = _pack_identifier(project_id, label="project_id")
        validated_scope_sha256 = _sha256_text(
            basket_scope_sha256, label="basket_scope_sha256"
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT event_id, saved_at, revision, saved_plan_sha256,
                       basket_json
                FROM pack_selection_events
                WHERE project_id = ? AND basket_scope_sha256 = ?
                ORDER BY revision DESC, sequence DESC
                LIMIT 1
                """,
                (validated_project_id, validated_scope_sha256),
            ).fetchone()
        if row is None:
            return None
        basket = json.loads(row[4])
        if not isinstance(basket, dict):
            raise RuntimeError("saved Pack Composer basket is invalid")
        return {
            **basket,
            "revision": int(row[2]),
            "event_id": str(row[0]),
            "saved_at": str(row[1]),
            "saved_plan_sha256": str(row[3]),
            "saved": True,
        }

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    schema_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    stem_id TEXT NOT NULL,
                    candidate_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS decision_events_project_sequence
                ON decision_events (project_id, sequence)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pack_selection_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    schema_name TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    basket_scope_sha256 TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    saved_plan_sha256 TEXT NOT NULL,
                    basket_json TEXT NOT NULL,
                    UNIQUE (project_id, basket_scope_sha256, revision)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS pack_selection_events_project_scope
                ON pack_selection_events (
                    project_id, basket_scope_sha256, revision
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def default_workbench_state_dir(project: Mapping[str, Any]) -> Path:
    import os

    configured = os.environ.get("SUNOFRIEND_WORKBENCH_HOME")
    base = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "share" / "sunofriend" / "workbench"
    )
    return (base / str(project["project_id"])).resolve()


def contribution_preview(
    project: Mapping[str, Any],
    current: Mapping[str, Any],
    events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the exact metadata-only fields eligible for a later opt-in share."""

    stems = []
    current_stems = current.get("stems", {})
    current_stem_ids = {str(stem["stem_id"]) for stem in project.get("stems", [])}
    for stem in project.get("stems", []):
        stem_id = str(stem["stem_id"])
        state = current_stems.get(stem_id, {})
        candidates = []
        for candidate in stem.get("candidates", []):
            candidate_id = str(candidate["candidate_id"])
            decision = state.get("candidates", {}).get(candidate_id)
            if decision is None:
                continue
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "midi_sha256": candidate["midi"]["sha256"],
                    "preview_sha256": (
                        candidate.get("preview", {}).get("sha256")
                        if candidate.get("preview")
                        else None
                    ),
                    "process": candidate.get("process"),
                    "decision": decision.get("decision"),
                    "context": decision.get("context"),
                    "problem_tags": list(decision.get("problem_tags", [])),
                }
            )
        if candidates or state.get("outcome"):
            stems.append(
                {
                    "stem_id": stem_id,
                    "source_sha256": stem["source"]["sha256"],
                    "role": state.get("role") or stem.get("role"),
                    "outcome": state.get("outcome"),
                    "candidates": candidates,
                }
            )
    return {
        "schema": "sunofriend.workbench-contribution-preview.v1",
        "project": {
            "project_id": project.get("project_id"),
            "bpm": project.get("setup", {}).get("bpm"),
            "key": project.get("setup", {}).get("key"),
            "tuning_hz": project.get("setup", {}).get("tuning_hz"),
        },
        "stems": stems,
        "decision_event_count": sum(
            event.get("event_type") != "candidate_auditioned"
            and event.get("stem_id") in current_stem_ids
            for event in events
        ),
        "excluded": [
            "audio",
            "midi files",
            "absolute paths",
            "free-text notes",
            "review questions and listening-focus text",
            "play counts and dwell time",
        ],
        "submission_enabled": False,
    }


def _validated_event(
    project: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    event_type = request.get("event_type")
    if event_type not in _EVENT_TYPES:
        raise ValueError("unsupported workbench event type")
    stem_id = _bounded_text(request.get("stem_id"), label="stem_id", maximum=128)
    stems = {str(stem["stem_id"]): stem for stem in project.get("stems", [])}
    if stem_id not in stems:
        raise ValueError("unknown workbench stem_id")
    stem = stems[stem_id]
    candidates = {
        str(candidate["candidate_id"]): candidate
        for candidate in stem.get("candidates", [])
    }
    candidate_id = request.get("candidate_id")
    if candidate_id is not None:
        candidate_id = _bounded_text(candidate_id, label="candidate_id", maximum=128)
        if candidate_id not in candidates:
            raise ValueError("candidate_id does not belong to the selected stem")

    if (
        event_type in {"candidate_decision", "candidate_auditioned"}
        and not candidate_id
    ):
        raise ValueError(f"{event_type} requires candidate_id")
    payload: dict[str, Any]
    if event_type == "candidate_decision":
        decision = request.get("decision")
        if decision not in _CANDIDATE_DECISIONS:
            raise ValueError("unsupported candidate decision")
        if decision in {"main", "optional"} and candidates[str(candidate_id)].get(
            "audition_blocked"
        ):
            raise ValueError(
                "this candidate is diagnostic-only because it contains no playable "
                "notes or an extreme AI decoder burst; choose needs correction or reject"
            )
        context = request.get("context", "solo")
        if context not in _LISTENING_CONTEXTS:
            raise ValueError("unsupported listening context")
        problem_tags = request.get("problem_tags", [])
        if not isinstance(problem_tags, list) or any(
            tag not in _PROBLEM_TAGS for tag in problem_tags
        ):
            raise ValueError("unsupported problem tag")
        notes = request.get("notes")
        if notes is not None:
            notes = (
                _bounded_text(notes, label="notes", maximum=2000, allow_empty=True)
                or None
            )
        payload = {
            "decision": decision,
            "context": context,
            "problem_tags": sorted(set(problem_tags)),
            "notes": notes,
        }
    elif event_type == "stem_outcome":
        outcome = request.get("outcome")
        if outcome not in _STEM_OUTCOMES:
            raise ValueError("unsupported stem outcome")
        context = request.get("context", "solo")
        if context not in _LISTENING_CONTEXTS:
            raise ValueError("unsupported listening context")
        payload = {"outcome": outcome, "context": context}
    elif event_type == "role_tag":
        payload = {"role": _bounded_text(request.get("role"), label="role", maximum=80)}
        candidate_id = None
    else:
        context = request.get("context", "solo")
        if context not in _LISTENING_CONTEXTS:
            raise ValueError("unsupported listening context")
        payload = {"context": context}

    review_context_sha256 = stem.get("review_context_sha256")
    if (
        not isinstance(review_context_sha256, str)
        or len(review_context_sha256) != 64
        or any(
            character not in "0123456789abcdef" for character in review_context_sha256
        )
    ):
        raise ValueError("workbench stem has no valid review context hash")
    payload["review_context"] = {
        "sha256": review_context_sha256,
        "review_question": stem.get("review_question"),
        "listening_focus": list(stem.get("listening_focus", [])),
    }

    return {
        "event_id": str(uuid.uuid4()),
        "schema": WORKBENCH_EVENT_SCHEMA,
        "created_at": _utc_now(),
        "project_id": str(project["project_id"]),
        "stem_id": stem_id,
        "candidate_id": candidate_id,
        "event_type": event_type,
        "payload": payload,
    }


def _review_complete(project: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    states = current.get("stems", {})
    for stem in project.get("stems", []):
        if stem.get("candidate_count", 0) <= 0:
            continue
        state = states.get(str(stem["stem_id"]), {})
        if not state.get("outcome") and not state.get("candidates"):
            return False
    return True


def _bounded_text(
    value: Any, *, label: str, maximum: int, allow_empty: bool = False
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    if len(text) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return text


def _validated_pack_basket(
    project_id: str, basket: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(basket, Mapping):
        raise ValueError("Pack Composer basket must be an object")
    if set(basket) != _PACK_BASKET_FIELDS:
        raise ValueError(
            "Pack Composer basket must contain exactly schema, project_id, "
            "basket_scope_sha256, included_item_ids, source_audio_opt_in and "
            "basket_sha256"
        )
    if basket.get("schema") != WORKBENCH_PACK_BASKET_SCHEMA:
        raise ValueError("unsupported Pack Composer basket schema")
    basket_project_id = _pack_identifier(
        basket.get("project_id"), label="basket project_id"
    )
    if basket_project_id != project_id:
        raise ValueError("Pack Composer basket project_id does not match")
    basket_scope_sha256 = _sha256_text(
        basket.get("basket_scope_sha256"), label="basket_scope_sha256"
    )
    basket_sha256 = _sha256_text(basket.get("basket_sha256"), label="basket_sha256")
    included_item_ids = basket.get("included_item_ids")
    if not isinstance(included_item_ids, list):
        raise ValueError("included_item_ids must be a list")
    validated_item_ids = [
        _pack_identifier(value, label="included_item_ids entry", maximum=512)
        for value in included_item_ids
    ]
    if len(set(validated_item_ids)) != len(validated_item_ids):
        raise ValueError("included_item_ids must not contain duplicates")
    source_audio_opt_in = basket.get("source_audio_opt_in")
    if not isinstance(source_audio_opt_in, bool):
        raise ValueError("source_audio_opt_in must be boolean")

    # Preserve the canonical basket fields and the caller's item order exactly.
    # In particular, the store does not sort, deduplicate, add, or remove items.
    return {
        "schema": WORKBENCH_PACK_BASKET_SCHEMA,
        "project_id": basket_project_id,
        "basket_scope_sha256": basket_scope_sha256,
        "included_item_ids": list(validated_item_ids),
        "source_audio_opt_in": source_audio_opt_in,
        "basket_sha256": basket_sha256,
    }


def _pack_identifier(value: Any, *, label: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if not value or not value.strip():
        raise ValueError(f"{label} must not be empty")
    if value != value.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    if len(value) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return value


def _sha256_text(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()
