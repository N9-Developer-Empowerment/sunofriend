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
_EVENT_TYPES = {
    "candidate_decision",
    "stem_outcome",
    "role_tag",
    "candidate_auditioned",
}
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

    def append(self, project: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
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
                "outcome": None,
                "candidates": {},
                "main_candidate_id": None,
                "auditioned_candidates": [],
            }
        for event in self.events(str(project["project_id"])):
            stem = states.get(event["stem_id"])
            if stem is None:
                continue
            payload = event["payload"]
            if event["event_type"] == "candidate_decision":
                stem["candidates"][event["candidate_id"]] = {
                    "decision": payload["decision"],
                    "context": payload["context"],
                    "problem_tags": list(payload.get("problem_tags", [])),
                    "notes": payload.get("notes"),
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
                    "event_id": event["event_id"],
                    "created_at": event["created_at"],
                }
            elif event["event_type"] == "role_tag":
                stem["role"] = payload["role"]
            elif event["event_type"] == "candidate_auditioned":
                candidate_id = event.get("candidate_id")
                if candidate_id and candidate_id not in stem["auditioned_candidates"]:
                    stem["auditioned_candidates"].append(candidate_id)
        return {"stems": states, "event_count": sum(1 for _ in self.events(str(project["project_id"])))}

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
        }
        review = {
            "schema": WORKBENCH_REVIEW_SCHEMA,
            "status": "reviewed" if _review_complete(project, current) else "in_progress",
            "exported_at": _utc_now(),
            "project": local_project,
            "current": current,
            "events": events,
        }
        review["contribution_preview"] = contribution_preview(project, current, events)
        review["review_sha256"] = _document_hash(review)
        return review

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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def default_workbench_state_dir(project: Mapping[str, Any]) -> Path:
    import os

    configured = os.environ.get("SUNOFRIEND_WORKBENCH_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".local" / "share" / "sunofriend" / "workbench"
    return (base / str(project["project_id"])).resolve()


def contribution_preview(
    project: Mapping[str, Any],
    current: Mapping[str, Any],
    events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the exact metadata-only fields eligible for a later opt-in share."""

    stems = []
    current_stems = current.get("stems", {})
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
            event.get("event_type") != "candidate_auditioned" for event in events
        ),
        "excluded": [
            "audio",
            "midi files",
            "absolute paths",
            "free-text notes",
            "play counts and dwell time",
        ],
        "submission_enabled": False,
    }


def _validated_event(project: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
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

    if event_type in {"candidate_decision", "candidate_auditioned"} and not candidate_id:
        raise ValueError(f"{event_type} requires candidate_id")
    payload: dict[str, Any]
    if event_type == "candidate_decision":
        decision = request.get("decision")
        if decision not in _CANDIDATE_DECISIONS:
            raise ValueError("unsupported candidate decision")
        if (
            decision in {"main", "optional"}
            and candidates[str(candidate_id)].get("audition_blocked")
        ):
            raise ValueError(
                "this candidate is diagnostic-only because it contains no playable "
                "notes or an extreme AI decoder burst; choose needs correction or reject"
            )
        context = request.get("context", "solo")
        if context not in _LISTENING_CONTEXTS:
            raise ValueError("unsupported listening context")
        problem_tags = request.get("problem_tags", [])
        if not isinstance(problem_tags, list) or any(tag not in _PROBLEM_TAGS for tag in problem_tags):
            raise ValueError("unsupported problem tag")
        notes = request.get("notes")
        if notes is not None:
            notes = _bounded_text(notes, label="notes", maximum=2000, allow_empty=True) or None
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


def _bounded_text(value: Any, *, label: str, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    if len(text) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
