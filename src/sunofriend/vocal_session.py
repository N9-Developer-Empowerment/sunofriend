"""Path-free, resumable state for a dedicated local vocal-comp session."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Mapping, Sequence
import uuid
from datetime import datetime, timezone

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import canonical_json_bytes, document_sha256
from .vocal_phrase_decision import validate_phrase_decision


VOCAL_SESSION_SCHEMA = "sunofriend.vocal-comp-session.v1"
VOCAL_SESSION_DRAFT_SCHEMA = "sunofriend.vocal-comp-session-draft.v1"
VOCAL_SESSION_EVENT_SCHEMA = "sunofriend.vocal-comp-session-event.v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DRAFT_KEYS = frozenset(
    {"active_phrase_id", "notes_by_phrase", "filter", "recorder_settings"}
)


class VocalSessionDraftConflictError(RuntimeError):
    """Raised when a draft save is based on an old revision."""


class VocalSessionStore:
    """Owner-only drafts plus append-only explicit phrase-decision events."""

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_dir, 0o700)
        self.database = self.state_dir / "vocal-session.sqlite3"
        self.draft_path = self.state_dir / "draft.json"
        self._initialize()

    def save_draft(
        self,
        session: Mapping[str, Any],
        draft: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        session_doc = dict(session)
        if session_doc.get("schema") != VOCAL_SESSION_SCHEMA:
            raise ValueError("draft requires a vocal session")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")
        payload = dict(draft)
        if not set(payload).issubset(_DRAFT_KEYS) or _contains_decision_authority(
            payload
        ):
            raise ValueError(
                "draft must remain non-authoritative and contain no decision"
            )
        phrases = {row["phrase_id"] for row in session_doc.get("phrases", [])}
        active = payload.get("active_phrase_id")
        if active is not None and active not in phrases:
            raise ValueError("draft active phrase is unknown")
        notes = payload.get("notes_by_phrase", {})
        if not isinstance(notes, Mapping) or any(
            key not in phrases or not isinstance(value, str)
            for key, value in notes.items()
        ):
            raise ValueError("draft notes must bind known phrases and text")
        current = self.load_draft(session_doc)
        current_revision = int(current["revision"]) if current is not None else 0
        if current_revision != expected_revision:
            raise VocalSessionDraftConflictError(
                f"draft revision conflict: expected {expected_revision}, "
                f"current {current_revision}"
            )
        document: dict[str, Any] = {
            "schema": VOCAL_SESSION_DRAFT_SCHEMA,
            "revision": current_revision + 1,
            "binding": {
                "session_id": session_doc["session_id"],
                "musical_state_sha256": session_doc["binding"]["musical_state_sha256"],
            },
            "draft": payload,
            "authority": "none",
            "effects": _zero_effects(),
            "network_used": False,
        }
        document["document_sha256"] = document_sha256(document)
        _atomic_private_json(self.draft_path, document)
        return document

    def load_draft(self, session: Mapping[str, Any]) -> dict[str, Any] | None:
        if not self.draft_path.exists():
            return None
        value = json.loads(self.draft_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("saved vocal session draft is invalid")
        expected = str(value.get("document_sha256", ""))
        unsigned = dict(value)
        unsigned.pop("document_sha256", None)
        if expected != document_sha256(unsigned):
            raise ValueError("saved vocal session draft hash does not match")
        if value.get("schema") != VOCAL_SESSION_DRAFT_SCHEMA:
            raise ValueError("saved vocal session draft schema is unsupported")
        binding = value.get("binding")
        if binding != {
            "session_id": session["session_id"],
            "musical_state_sha256": session["binding"]["musical_state_sha256"],
        }:
            raise ValueError("saved vocal session draft binds another session")
        if value.get("authority") != "none" or value.get("effects") != _zero_effects():
            raise ValueError("saved vocal session draft claims musical authority")
        return value

    def append(
        self, session: Mapping[str, Any], request: Mapping[str, Any]
    ) -> dict[str, Any]:
        if request.get("event_type") != "phrase_decision":
            raise ValueError("event_type must be an explicit phrase_decision")
        decision = request.get("decision")
        if not isinstance(decision, Mapping):
            raise ValueError("phrase_decision event requires a decision document")
        state_sha = session.get("binding", {}).get("musical_state_sha256")
        if decision.get("binding", {}).get("musical_state_sha256") != state_sha:
            raise ValueError("phrase decision binds another musical state hash")
        expected_hash = str(decision.get("document_sha256", ""))
        unsigned = dict(decision)
        unsigned.pop("document_sha256", None)
        if expected_hash != document_sha256(unsigned):
            raise ValueError("phrase decision document SHA-256 does not match")
        phrase_ids = {row["phrase_id"] for row in session.get("phrases", [])}
        if decision.get("phrase", {}).get("phrase_id") not in phrase_ids:
            raise ValueError("phrase decision refers to an unknown phrase")
        event: dict[str, Any] = {
            "schema": VOCAL_SESSION_EVENT_SCHEMA,
            "event_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "event_type": "phrase_decision",
            "session_id": session["session_id"],
            "musical_state_sha256": state_sha,
            "decision_document_sha256": expected_hash,
            "decision": dict(decision),
        }
        event["event_document_sha256"] = document_sha256(event)
        encoded = canonical_json_bytes(event).decode("utf-8")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO vocal_session_events "
                "(event_id, session_id, event_type, event_json) VALUES (?, ?, ?, ?)",
                (
                    event["event_id"],
                    event["session_id"],
                    event["event_type"],
                    encoded,
                ),
            )
        self._secure_database_files()
        return event

    def events(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM vocal_session_events "
                "WHERE session_id = ? ORDER BY sequence",
                (session_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def current_session(self, musical_state: Mapping[str, Any]) -> dict[str, Any]:
        empty = build_vocal_session(musical_state)
        decisions = [event["decision"] for event in self.events(empty["session_id"])]
        return build_vocal_session(musical_state, decisions)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS vocal_session_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK (event_type = 'phrase_decision'),
                    event_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS vocal_session_events_no_update
                BEFORE UPDATE ON vocal_session_events
                BEGIN
                    SELECT RAISE(ABORT, 'append-only event store');
                END;
                CREATE TRIGGER IF NOT EXISTS vocal_session_events_no_delete
                BEFORE DELETE ON vocal_session_events
                BEGIN
                    SELECT RAISE(ABORT, 'append-only event store');
                END;
                """
            )
        self._secure_database_files()

    def _secure_database_files(self) -> None:
        for path in self.state_dir.glob("vocal-session.sqlite3*"):
            os.chmod(path, 0o600)


def build_vocal_session(
    musical_state: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Project the reviewed song state and explicit decisions for a local UI."""

    state = validate_musical_state(musical_state)
    validated = [validate_phrase_decision(item, state) for item in decisions]
    by_phrase: dict[str, dict[str, Any]] = {}
    for decision in validated:
        phrase_id = decision["phrase"]["phrase_id"]
        if phrase_id in by_phrase:
            raise ValueError("vocal session contains a duplicate phrase decision")
        by_phrase[phrase_id] = decision
    phrases = []
    for phrase in state["structure"]["phrases"]:
        decision = by_phrase.get(phrase["phrase_id"])
        phrases.append(
            {
                "phrase_id": phrase["phrase_id"],
                "start_seconds": phrase["start_seconds"],
                "end_seconds": phrase["end_seconds"],
                "lyrics": phrase["lyrics"],
                "decision": _decision_summary(decision),
            }
        )
    sources = []
    reference = state["vocal_performance_state"].get("reference")
    if isinstance(reference, Mapping):
        sources.append(_source_projection(reference, "authorised_ai_vocal_reference"))
    sources.extend(
        _source_projection(take, "human_vocal_take")
        for take in state["vocal_performance_state"]["takes"]
    )
    decision_count = len(validated)
    document: dict[str, Any] = {
        "schema": VOCAL_SESSION_SCHEMA,
        "session_id": f"vocal-session-{state['document_sha256'][:24]}",
        "status": (
            "reviewed_unrendered"
            if decision_count == len(phrases)
            else "in_progress_unrendered"
        ),
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "phrases": phrases,
        "sources": sources,
        "coverage": {
            "phrase_count": len(phrases),
            "decision_count": decision_count,
            "remaining_phrase_count": len(phrases) - decision_count,
        },
        "authority": {
            "selection_authority": "explicit_human_decision_only",
            "playback_creates_decision": False,
            "dwell_creates_decision": False,
            "draft_creates_decision": False,
        },
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_session(document, state)


def validate_vocal_session(
    session: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a portable session projection against an exact Musical State."""

    state = validate_musical_state(musical_state)
    document = dict(session)
    if document.get("schema") != VOCAL_SESSION_SCHEMA:
        raise ValueError("unsupported vocal session schema")
    expected_hash = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected_hash != document_sha256(unsigned):
        raise ValueError("vocal session document SHA-256 does not match")
    if document.get("binding") != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }:
        raise ValueError("vocal session does not bind this musical state")
    if document.get("session_id") != f"vocal-session-{state['document_sha256'][:24]}":
        raise ValueError("vocal session identity changed")
    expected_phrases = state["structure"]["phrases"]
    rows = document.get("phrases")
    if not isinstance(rows, list) or len(rows) != len(expected_phrases):
        raise ValueError("vocal session phrase roster changed")
    source_identities = _state_source_identities(state)
    decision_count = 0
    for row, phrase in zip(rows, expected_phrases):
        if (
            not isinstance(row, Mapping)
            or {
                key: row.get(key)
                for key in ("phrase_id", "start_seconds", "end_seconds", "lyrics")
            }
            != phrase
        ):
            raise ValueError("vocal session phrase geometry or lyrics changed")
        decision = row.get("decision")
        if decision is not None:
            if not isinstance(decision, Mapping):
                raise ValueError("vocal session decision summary is invalid")
            decision_count += 1
            source_id = decision.get("selected_source_id")
            source_sha = decision.get("selected_source_sha256")
            if source_id is None:
                if source_sha is not None:
                    raise ValueError("unresolved decision cannot bind source audio")
            elif source_identities.get(source_id) != source_sha:
                raise ValueError("vocal session decision source identity changed")
            if not _SHA256.fullmatch(str(decision.get("decision_document_sha256", ""))):
                raise ValueError("vocal session decision document hash is invalid")
    expected_sources = []
    reference = state["vocal_performance_state"].get("reference")
    if isinstance(reference, Mapping):
        expected_sources.append(
            _source_projection(reference, "authorised_ai_vocal_reference")
        )
    expected_sources.extend(
        _source_projection(take, "human_vocal_take")
        for take in state["vocal_performance_state"]["takes"]
    )
    if document.get("sources") != expected_sources:
        raise ValueError("vocal session source roster changed")
    expected_coverage = {
        "phrase_count": len(expected_phrases),
        "decision_count": decision_count,
        "remaining_phrase_count": len(expected_phrases) - decision_count,
    }
    if document.get("coverage") != expected_coverage:
        raise ValueError("vocal session coverage changed")
    expected_status = (
        "reviewed_unrendered"
        if decision_count == len(expected_phrases)
        else "in_progress_unrendered"
    )
    if document.get("status") != expected_status:
        raise ValueError("vocal session status changed")
    if document.get("authority") != {
        "selection_authority": "explicit_human_decision_only",
        "playback_creates_decision": False,
        "dwell_creates_decision": False,
        "draft_creates_decision": False,
    }:
        raise ValueError("vocal session authority is excessive")
    if (
        document.get("effects") != _zero_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError("vocal session cannot render, correct, train or use a network")
    _reject_paths(document)
    return document


def _decision_summary(decision: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "decision_document_sha256": decision["document_sha256"],
        "outcome": decision["outcome"],
        "selected_source_id": decision["selected_source_id"],
        "selected_source_sha256": decision["selected_source_sha256"],
    }


def _source_projection(source: Mapping[str, Any], source_class: str) -> dict[str, Any]:
    audio = source["audio"]
    return {
        "source_id": source["source_id"],
        "source_class": source_class,
        "label": source.get("label", source["source_id"]),
        "audio_sha256": audio["sha256"],
        "audio_bytes": audio["bytes"],
    }


def _state_source_identities(state: Mapping[str, Any]) -> dict[str, str]:
    vocal = state["vocal_performance_state"]
    result = {take["source_id"]: take["audio"]["sha256"] for take in vocal["takes"]}
    reference = vocal.get("reference")
    if isinstance(reference, Mapping):
        result[reference["source_id"]] = reference["audio"]["sha256"]
    return result


def _contains_decision_authority(value: Any) -> bool:
    forbidden = {"outcome", "selected_source_id", "preferred_take", "decision"}
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in forbidden or _contains_decision_authority(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_decision_authority(item) for item in value)
    return False


def _atomic_private_json(path: Path, document: Mapping[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "path" in str(key).casefold():
                raise ValueError("vocal session projection must be path-free")
            _reject_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str):
        if value.startswith(("/", "\\\\")) or (
            len(value) >= 3 and value[1:3] in {":/", ":\\"}
        ):
            raise ValueError("vocal session projection must not contain absolute paths")


def _zero_effects() -> dict[str, bool]:
    return {
        "human_phrase_decision_created": False,
        "audio_comp_rendered": False,
        "join_created": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
    }


__all__ = [
    "VOCAL_SESSION_DRAFT_SCHEMA",
    "VOCAL_SESSION_EVENT_SCHEMA",
    "VOCAL_SESSION_SCHEMA",
    "VocalSessionDraftConflictError",
    "VocalSessionStore",
    "build_vocal_session",
    "validate_vocal_session",
]
