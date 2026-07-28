"""Honest automatic-primary selection for Sunofriend Simple mode.

The Workbench event store records human listening decisions.  Simple mode must
not fabricate those events, so this module derives a separate, in-memory plan
only from the exact primary MIDI paths published by the production conversion
summaries.  The result is explicitly automatic, unreviewed and suitable for
rendering a useful first-pass song interpretation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import read_midi_clips


AUTOMATIC_SELECTION_SCHEMA = "sunofriend.automatic-selection.v1"
AUTOMATIC_SELECTION_POLICY = "automatic-primary-from-production-summary-v1"
_MAXIMUM_SUMMARY_BYTES = 16 * 1024 * 1024
_MAXIMUM_SELECTED_LANES = 24


class AutomaticSelectionError(ValueError):
    """The production summaries cannot support an honest automatic plan."""


@dataclass(frozen=True)
class AutomaticSelectionPlan:
    """Private render inputs plus a path-free public receipt."""

    selected: tuple[dict[str, Any], ...]
    omitted: tuple[dict[str, Any], ...]
    receipt: dict[str, Any]


def plan_automatic_selection(
    catalog: Mapping[str, Any],
    summary_paths: Sequence[str | Path],
    *,
    result_root: str | Path,
) -> AutomaticSelectionPlan:
    """Choose only exact production-summary primaries without writing state."""

    root = Path(result_root).expanduser().resolve()
    if not root.is_dir():
        raise AutomaticSelectionError(
            "the verified conversion result folder does not exist"
        )
    published, summary_records = _published_primary_rows(summary_paths, root)
    if not published:
        raise AutomaticSelectionError(
            "conversion published no exact primary MIDI paths for Simple mode"
        )

    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    used_stems: set[str] = set()
    used_midi: set[str] = set()
    for row in published:
        matches = _catalog_matches(catalog, row)
        if len(matches) != 1:
            omitted.append(
                {
                    "role": row["role"],
                    "reason": (
                        "primary_not_in_catalog"
                        if not matches
                        else "ambiguous_source_pairing"
                    ),
                    "summary_sha256": row["summary_sha256"],
                    "midi_sha256": row["midi"]["sha256"],
                }
            )
            continue
        stem, candidate = matches[0]
        stem_id = str(stem["stem_id"])
        midi_sha256 = str(candidate["midi"]["sha256"])
        if stem_id in used_stems or midi_sha256 in used_midi:
            omitted.append(
                {
                    "stem_id": stem_id,
                    "role": str(stem.get("role") or row["role"]),
                    "reason": "duplicate_primary",
                    "summary_sha256": row["summary_sha256"],
                    "midi_sha256": midi_sha256,
                }
            )
            continue
        reason = _candidate_block_reason(stem, candidate)
        if reason is not None:
            omitted.append(
                {
                    "stem_id": stem_id,
                    "role": str(stem.get("role") or row["role"]),
                    "reason": reason,
                    "summary_sha256": row["summary_sha256"],
                    "midi_sha256": midi_sha256,
                }
            )
            continue
        source_record = dict(stem["source"])
        midi_record = dict(candidate["midi"])
        source_path = _verify_record(source_record, label="source stem")
        midi_path = _verify_record(midi_record, label="automatic primary MIDI")
        if midi_path != row["midi_path"]:
            raise AutomaticSelectionError(
                "the catalogued automatic primary no longer matches its summary"
            )
        selected.append(
            {
                "stem_id": stem_id,
                "stem_label": str(stem.get("label") or stem.get("role") or "Stem"),
                "candidate_id": str(candidate["candidate_id"]),
                "candidate_label": str(
                    candidate.get("label") or "Production primary"
                ),
                "process": candidate.get("process"),
                "role": str(stem.get("role") or row["role"]),
                "selection_basis": "automatic_primary",
                "review_status": "not_reviewed",
                "quality_status": "review_recommended",
                "source_path": source_path,
                "source": source_record,
                "midi_path": midi_path,
                "midi": midi_record,
                "summary_sha256": row["summary_sha256"],
            }
        )
        used_stems.add(stem_id)
        used_midi.add(midi_sha256)

    selected_stem_ids = {str(row["stem_id"]) for row in selected}
    for stem in catalog.get("stems", []):
        stem_id = str(stem.get("stem_id") or "")
        if stem_id and stem_id not in selected_stem_ids and not any(
            item.get("stem_id") == stem_id for item in omitted
        ):
            omitted.append(
                {
                    "stem_id": stem_id,
                    "role": str(stem.get("role") or "unclassified"),
                    "reason": "no_published_primary",
                }
            )

    if not selected:
        raise AutomaticSelectionError(
            "no published primary could be paired with a playable source stem"
        )
    if len(selected) > _MAXIMUM_SELECTED_LANES:
        raise AutomaticSelectionError(
            "Simple mode supports at most 24 automatic primary lanes; use Studio "
            "to choose a smaller arrangement"
        )

    for index, item in enumerate(selected, start=1):
        item["selection_index"] = index
        item["decision"] = "automatic-baseline"
        item["garageband_pack_archive_member"] = (
            f"MIDI/{index:02d}-{_safe_token(str(item['role']))}"
            "-automatic-primary.mid"
        )

    public_selected = [
        {
            "selection_index": int(item["selection_index"]),
            "stem_id": str(item["stem_id"]),
            "candidate_id": str(item["candidate_id"]),
            "role": str(item["role"]),
            "process": item.get("process"),
            "selection_basis": str(item["selection_basis"]),
            "review_status": str(item["review_status"]),
            "quality_status": str(item["quality_status"]),
            "source_sha256": str(item["source"]["sha256"]),
            "source_bytes": int(item["source"]["bytes"]),
            "midi_sha256": str(item["midi"]["sha256"]),
            "midi_bytes": int(item["midi"]["bytes"]),
            "summary_sha256": str(item["summary_sha256"]),
            "archive_member": str(item["garageband_pack_archive_member"]),
        }
        for item in selected
    ]
    receipt_payload = {
        "schema": AUTOMATIC_SELECTION_SCHEMA,
        "policy": AUTOMATIC_SELECTION_POLICY,
        "project_id": str(catalog.get("project_id") or ""),
        "project": {
            "bpm": catalog.get("setup", {}).get("bpm"),
            "key": catalog.get("setup", {}).get("key"),
            "tuning_hz": catalog.get("setup", {}).get("tuning_hz"),
        },
        "selected": public_selected,
        "omitted": omitted,
        "conversion_summaries": summary_records,
        "review_status": "not_reviewed",
        "quality_status": "review_recommended",
        "effects": {
            "automatic_selection": True,
            "automatic_ranking": False,
            "human_decision_events": 0,
            "workbench_state_changed": False,
            "feedback_recorded": False,
            "source_audio_mutated": False,
            "source_midi_mutated": False,
        },
    }
    receipt = {
        **receipt_payload,
        "selection_manifest_sha256": _document_hash(receipt_payload),
    }
    return AutomaticSelectionPlan(
        selected=tuple(selected),
        omitted=tuple(omitted),
        receipt=receipt,
    )


def _published_primary_rows(
    summary_paths: Sequence[str | Path],
    result_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for raw_path in summary_paths:
        path = Path(raw_path).expanduser().resolve()
        if result_root not in path.parents:
            raise AutomaticSelectionError(
                "a conversion summary is outside the verified result folder"
            )
        document, record = _read_summary(path)
        records.append(record)
        parts = document.get("parts")
        if isinstance(parts, Mapping):
            for role in sorted(parts):
                item = parts[role]
                if not isinstance(item, Mapping) or item.get("status") != "ok":
                    continue
                midi_path = _reported_result_path(
                    item.get("midi"),
                    summary_path=path,
                    result_root=result_root,
                )
                if midi_path is None:
                    continue
                rows.append(
                    _published_row(
                        role=str(role),
                        midi_path=midi_path,
                        summary_record=record,
                        source_path=None,
                    )
                )
            continue
        midi_path = _reported_result_path(
            document.get("primary_midi"),
            summary_path=path,
            result_root=result_root,
        )
        if midi_path is None:
            continue
        source_path = _reported_source_path(document.get("source_stem"))
        role = {
            "lead": "vocals",
            "backing": "backing_vocals",
        }.get(str(document.get("role") or ""), str(document.get("role") or "vocals"))
        rows.append(
            _published_row(
                role=role,
                midi_path=midi_path,
                summary_record=record,
                source_path=source_path,
            )
        )
    return rows, records


def _published_row(
    *,
    role: str,
    midi_path: Path,
    summary_record: Mapping[str, Any],
    source_path: Path | None,
) -> dict[str, Any]:
    return {
        "role": role,
        "midi_path": midi_path,
        "midi": _file_record(midi_path),
        "source_path": source_path,
        "summary_sha256": str(summary_record["sha256"]),
    }


def _catalog_matches(
    catalog: Mapping[str, Any],
    published: Mapping[str, Any],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    matches: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for stem in catalog.get("stems", []):
        if str(stem.get("role") or "") != str(published["role"]):
            continue
        source_path = published.get("source_path")
        if source_path is not None and Path(str(stem.get("source_path"))).resolve() != (
            source_path
        ):
            continue
        for candidate in stem.get("candidates", []):
            try:
                candidate_path = Path(str(candidate.get("midi_path"))).resolve()
            except (OSError, RuntimeError):
                continue
            if candidate_path == published["midi_path"]:
                matches.append((stem, candidate))
    return matches


def _candidate_block_reason(
    stem: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> str | None:
    if candidate.get("audition_blocked"):
        return "audition_blocked"
    if candidate.get("diagnostic_only"):
        return "diagnostic_only"
    if candidate.get("primary") is not True:
        return "not_catalogued_primary"
    try:
        clips = read_midi_clips(
            str(candidate["midi_path"]),
            role=str(stem.get("role") or "unclassified"),
        )
    except Exception:
        return "unreadable_midi"
    if not any(getattr(clip, "notes", ()) for clip in clips):
        return "no_playable_notes"
    return None


def _read_summary(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size > _MAXIMUM_SUMMARY_BYTES:
            raise AutomaticSelectionError("a conversion summary is unavailable")
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except AutomaticSelectionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutomaticSelectionError(
            "a conversion summary is unreadable or invalid"
        ) from exc
    if not isinstance(document, dict):
        raise AutomaticSelectionError("a conversion summary must contain an object")
    return document, {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "kind": (
            "instrumental" if isinstance(document.get("parts"), Mapping) else "vocal"
        ),
    }


def _reported_result_path(
    value: Any,
    *,
    summary_path: Path,
    result_root: Path,
) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    entered = Path(value).expanduser()
    candidates = (
        (entered.resolve(),)
        if entered.is_absolute()
        else (entered.resolve(), (summary_path.parent / entered).resolve())
    )
    for path in candidates:
        if path.is_file() and result_root in path.parents:
            return path
    return None


def _reported_source_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        path = Path(value).expanduser().resolve()
    except OSError:
        return None
    return path if path.is_file() else None


def _verify_record(record: Mapping[str, Any], *, label: str) -> Path:
    path_value = record.get("path")
    digest = record.get("sha256")
    byte_count = record.get("bytes")
    if (
        not isinstance(path_value, str)
        or not isinstance(digest, str)
        or len(digest) != 64
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise AutomaticSelectionError(f"{label} has invalid catalog evidence")
    path = Path(path_value).expanduser().resolve()
    try:
        if not path.is_file() or path.stat().st_size != byte_count:
            raise AutomaticSelectionError(f"{label} changed after cataloguing")
    except OSError as exc:
        raise AutomaticSelectionError(f"{label} changed after cataloguing") from exc
    if _sha256(path) != digest:
        raise AutomaticSelectionError(f"{label} changed after cataloguing")
    return path


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_token(value: str) -> str:
    token = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value.strip()
    )
    return "-".join(part for part in token.split("-") if part) or "part"


__all__ = [
    "AUTOMATIC_SELECTION_POLICY",
    "AUTOMATIC_SELECTION_SCHEMA",
    "AutomaticSelectionError",
    "AutomaticSelectionPlan",
    "plan_automatic_selection",
]
