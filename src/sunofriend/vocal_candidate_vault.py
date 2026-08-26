"""Owner-only provisional vocal attempts and reversible working choices.

The vault deliberately sits outside the canonical Musical State.  Keeping a
capture admits source evidence only; a working choice is a zero-authority UI
draft.  Phrase decisions, state transitions, renders and training labels stay
behind their existing explicit operations.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from .musical_state import validate_musical_state
from .source_receipt import canonical_json_bytes, document_sha256
from .vocal_capture import validate_vocal_capture


VOCAL_CANDIDATE_ENTRY_SCHEMA = "sunofriend.vocal-candidate-vault-entry.v1"
VOCAL_WORKING_CHOICES_SCHEMA = "sunofriend.vocal-working-choices.v1"


class VocalCandidateVaultConflictError(RuntimeError):
    """Raised when a vault write is stale or would replace retained evidence."""


class VocalCandidateVault:
    """Keep provisional captures and working choices behind one small facade."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().absolute()
        if self.root.is_symlink():
            raise ValueError("candidate vault root must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.entries_root = self.root / "entries"
        if self.entries_root.is_symlink():
            raise ValueError("candidate entries root must not be a symlink")
        self.entries_root.mkdir(exist_ok=True, mode=0o700)
        os.chmod(self.entries_root, 0o700)
        self.working_path = self.root / "working-choices.json"

    def keep(
        self,
        musical_state: Mapping[str, Any],
        *,
        capture_receipt: Mapping[str, Any],
        wav_bytes: bytes,
        label: str,
    ) -> dict[str, Any]:
        """Atomically retain one exact unreviewed capture without state admission."""

        state = validate_musical_state(musical_state)
        receipt = validate_vocal_capture(capture_receipt, state)
        audio = bytes(wav_bytes)
        _validate_audio_bytes(audio, receipt=receipt)
        normalized_label = _candidate_label(label)
        entry = _entry_document(state, receipt=receipt, label=normalized_label)
        destination = self.entries_root / entry["entry_id"]
        if destination.exists() or destination.is_symlink():
            raise VocalCandidateVaultConflictError("candidate is already kept")
        with tempfile.TemporaryDirectory(
            prefix=".candidate-", dir=self.entries_root
        ) as temporary_name:
            temporary = Path(temporary_name)
            os.chmod(temporary, 0o700)
            _private_bytes(temporary / "capture.wav", audio)
            _private_bytes(
                temporary / "capture-receipt.json", canonical_json_bytes(receipt)
            )
            _private_bytes(temporary / "entry.json", canonical_json_bytes(entry))
            temporary.replace(destination)
        _secure_tree(destination)
        return entry

    def entries(self, musical_state: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return verified path-free entries for the exact Musical State."""

        state = validate_musical_state(musical_state)
        rows = [self._read_entry(path, state=state) for path in self._entry_dirs()]
        return sorted(rows, key=lambda row: row["entry_id"])

    def media_records(self, musical_state: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return verified private media records for the loopback server only."""

        state = validate_musical_state(musical_state)
        records = []
        for path in self._entry_dirs():
            entry = self._read_entry(path, state=state)
            records.append(
                {
                    "source_id": entry["source_id"],
                    "source_class": "unreviewed_vocal_candidate",
                    "audio_sha256": entry["audio"]["sha256"],
                    "audio_bytes": entry["audio"]["bytes"],
                    "private_path": str(path / entry["artifacts"]["audio"]),
                    "playback_start_seconds": entry["placement"][
                        "source_phrase_start_seconds"
                    ],
                    "playback_end_seconds": entry["placement"][
                        "source_phrase_end_seconds"
                    ],
                    "bound_phrase_id": entry["phrase"]["phrase_id"],
                }
            )
        return records

    def save_working_choices(
        self,
        musical_state: Mapping[str, Any],
        working_source_by_phrase: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Replace the reversible choice projection after an exact revision check."""

        state = validate_musical_state(musical_state)
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer")
        current = self.load_working_choices(state)
        current_revision = int(current["revision"]) if current else 0
        if current_revision != expected_revision:
            raise VocalCandidateVaultConflictError(
                f"working choice revision conflict: expected {expected_revision}, "
                f"current {current_revision}"
            )
        choices = _validate_choice_request(
            state,
            working_source_by_phrase,
            entries=self.entries(state),
        )
        document: dict[str, Any] = {
            "schema": VOCAL_WORKING_CHOICES_SCHEMA,
            "revision": current_revision + 1,
            "binding": {
                "musical_state_sha256": state["document_sha256"],
            },
            "choices": choices,
            "authority": "none",
            "effects": _zero_effects(),
            "network_used": False,
        }
        document["document_sha256"] = document_sha256(document)
        _atomic_private_json(self.working_path, document)
        return document

    def load_working_choices(
        self, musical_state: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Load and revalidate the current zero-authority working projection."""

        state = validate_musical_state(musical_state)
        if not self.working_path.exists():
            return None
        document = _json_object(self.working_path, "working choices")
        _validate_working_document(document, state=state, entries=self.entries(state))
        return document

    def _entry_dirs(self) -> Sequence[Path]:
        return tuple(
            path
            for path in self.entries_root.iterdir()
            if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")
        )

    def _read_entry(self, path: Path, *, state: Mapping[str, Any]) -> dict[str, Any]:
        entry = _json_object(path / "entry.json", "candidate entry")
        _validate_entry(entry, state=state)
        receipt = _json_object(
            path / entry["artifacts"]["receipt"], "candidate capture receipt"
        )
        receipt = validate_vocal_capture(receipt, state)
        if receipt["document_sha256"] != entry["capture_receipt_sha256"]:
            raise ValueError("candidate receipt identity changed")
        expected_entry = _entry_document(
            state,
            receipt=receipt,
            label=_candidate_label(entry.get("label")),
        )
        if entry != expected_entry:
            raise ValueError("candidate entry projection changed")
        audio_path = path / entry["artifacts"]["audio"]
        if audio_path.is_symlink() or not audio_path.is_file():
            raise ValueError("candidate audio artifact is missing or unsafe")
        audio = audio_path.read_bytes()
        _validate_audio_bytes(audio, receipt=receipt)
        if (
            hashlib.sha256(audio).hexdigest() != entry["audio"]["sha256"]
            or len(audio) != entry["audio"]["bytes"]
        ):
            raise ValueError("candidate audio artifact identity changed")
        return entry


def _entry_document(
    state: Mapping[str, Any], *, receipt: Mapping[str, Any], label: str
) -> dict[str, Any]:
    sample_rate = int(receipt["audio"]["sample_rate"])
    placement = receipt["placement"]
    document: dict[str, Any] = {
        "schema": VOCAL_CANDIDATE_ENTRY_SCHEMA,
        "entry_id": f"candidate-{receipt['document_sha256']}",
        "status": "kept_unreviewed_candidate",
        "binding": {"musical_state_sha256": state["document_sha256"]},
        "source_id": receipt["capture"]["source_id"],
        "source_class": "unreviewed_vocal_candidate",
        "label": label,
        "phrase": {
            "phrase_id": receipt["phrase"]["phrase_id"],
            "lyrics": receipt["phrase"]["lyrics"],
        },
        "audio": dict(receipt["audio"]),
        "placement": {
            "source_phrase_start_seconds": (
                placement["source_phrase_start_frame"] / sample_rate
            ),
            "source_phrase_end_seconds": (
                placement["source_phrase_end_frame"] / sample_rate
            ),
            "destination_start_seconds": placement["destination_start_seconds"],
            "destination_end_seconds": placement["destination_end_seconds"],
        },
        "capture_receipt_sha256": receipt["document_sha256"],
        "artifacts": {
            "audio": "capture.wav",
            "receipt": "capture-receipt.json",
        },
        "authority": {
            "source_evidence_only": True,
            "working_choice_authority": "none",
            "phrase_decision_created": False,
            "render_authorized": False,
            "training_label_created": False,
        },
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _candidate_label(value: Any) -> str:
    label = str(value).strip()
    if not label or len(label) > 200:
        raise ValueError("candidate label must contain 1 to 200 characters")
    return label


def _validate_entry(entry: Mapping[str, Any], *, state: Mapping[str, Any]) -> None:
    if not isinstance(entry, Mapping):
        raise ValueError("candidate entry must be an object")
    supplied = str(entry.get("document_sha256", ""))
    unsigned = dict(entry)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("candidate entry document SHA-256 does not match")
    if entry.get("schema") != VOCAL_CANDIDATE_ENTRY_SCHEMA:
        raise ValueError("candidate entry schema is unsupported")
    if entry.get("binding") != {"musical_state_sha256": state["document_sha256"]}:
        raise ValueError("candidate entry binds another Musical State")
    if entry.get("status") != "kept_unreviewed_candidate":
        raise ValueError("candidate entry status changed")
    if entry.get("source_class") != "unreviewed_vocal_candidate":
        raise ValueError("candidate entry source class changed")
    if entry.get("artifacts") != {
        "audio": "capture.wav",
        "receipt": "capture-receipt.json",
    }:
        raise ValueError("candidate entry artifacts changed")
    if entry.get("authority") != {
        "source_evidence_only": True,
        "working_choice_authority": "none",
        "phrase_decision_created": False,
        "render_authorized": False,
        "training_label_created": False,
    }:
        raise ValueError("candidate entry claims unsupported authority")
    if (
        entry.get("effects") != _zero_effects()
        or entry.get("network_used") is not False
    ):
        raise ValueError("candidate entry claims unsupported effects")


def _validate_choice_request(
    state: Mapping[str, Any],
    requested: Mapping[str, Any],
    *,
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    if not isinstance(requested, Mapping):
        raise ValueError("working_source_by_phrase must be an object")
    phrases = {row["phrase_id"] for row in state["structure"]["phrases"]}
    by_source = {row["source_id"]: row for row in entries}
    result: dict[str, dict[str, str]] = {}
    for phrase_id, source_value in requested.items():
        if phrase_id not in phrases or not isinstance(source_value, str):
            raise ValueError("working choice must bind a known phrase and source")
        entry = by_source.get(source_value)
        if entry is None or entry["phrase"]["phrase_id"] != phrase_id:
            raise ValueError("working choice candidate is missing or bound elsewhere")
        result[phrase_id] = {
            "source_id": entry["source_id"],
            "source_class": entry["source_class"],
            "source_audio_sha256": entry["audio"]["sha256"],
        }
    return dict(sorted(result.items()))


def _validate_working_document(
    document: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
) -> None:
    supplied = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("working choices document SHA-256 does not match")
    if document.get("schema") != VOCAL_WORKING_CHOICES_SCHEMA:
        raise ValueError("working choices schema is unsupported")
    if document.get("binding") != {"musical_state_sha256": state["document_sha256"]}:
        raise ValueError("working choices bind another Musical State")
    revision = document.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise ValueError("working choices revision is invalid")
    choices = document.get("choices")
    if not isinstance(choices, Mapping):
        raise ValueError("working choices must be an object")
    if any(not isinstance(choice, Mapping) for choice in choices.values()):
        raise ValueError("working choice projections must be objects")
    expected = _validate_choice_request(
        state,
        {phrase_id: choice.get("source_id") for phrase_id, choice in choices.items()},
        entries=entries,
    )
    if document.get("choices") != expected:
        raise ValueError("working choices projection changed")
    if (
        document.get("authority") != "none"
        or document.get("effects") != _zero_effects()
    ):
        raise ValueError("working choices claim musical authority")
    if document.get("network_used") is not False:
        raise ValueError("working choices must record network_used=false")


def _validate_audio_bytes(payload: bytes, *, receipt: Mapping[str, Any]) -> None:
    audio = receipt["audio"]
    if len(payload) != audio["bytes"]:
        raise ValueError("candidate audio byte count changed")
    if hashlib.sha256(payload).hexdigest() != audio["sha256"]:
        raise ValueError("candidate audio SHA-256 changed")
    if not payload.startswith(b"RIFF") or payload[8:12] != b"WAVE":
        raise ValueError("candidate audio must remain a WAV file")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} artifact is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be readable JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _atomic_private_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _private_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _secure_tree(root: Path) -> None:
    os.chmod(root, 0o700)
    for path in root.rglob("*"):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)


def _zero_effects() -> dict[str, bool]:
    return {
        "musical_state_changed": False,
        "phrase_decision_created": False,
        "source_map_changed": False,
        "audio_rendered": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
    }


__all__ = [
    "VOCAL_CANDIDATE_ENTRY_SCHEMA",
    "VOCAL_WORKING_CHOICES_SCHEMA",
    "VocalCandidateVault",
    "VocalCandidateVaultConflictError",
]
