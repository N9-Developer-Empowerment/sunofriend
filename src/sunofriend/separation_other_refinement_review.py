"""Validate and seal explicit listening feedback for an other refinement.

The refinement result stays immutable.  A completed browser export is bound to
that exact result and written as a separate owner-only evidence document.  This
module never selects a source frontier, activates MIDI, runs a model or changes
profile availability.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .audio_formats import file_sha256
from .separation_other_refinement import (
    validate_other_refinement_plan,
    validate_other_refinement_result,
)


OTHER_REFINEMENT_REVIEW_SCHEMA = "sunofriend.other-refinement-listening.v1"
OTHER_REFINEMENT_FEEDBACK_SCHEMA = "sunofriend.other-refinement-feedback.v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LEGACY_FIELDS = frozenset(
    {
        "schema",
        "result_sha256",
        "target_id",
        "listened",
        "usefulness",
        "notes",
        "activation_choice",
    }
)
_DETAILED_FIELDS = frozenset(
    {
        *_LEGACY_FIELDS,
        "bleed",
        "missing_content",
        "artefacts",
        "timing_or_join_problems",
        "downstream_midi",
    }
)
_USEFULNESS = frozenset({"useful", "mixed", "not_useful", "cannot_tell"})
_PROBLEM = frozenset({"none", "some", "severe", "cannot_tell"})
_MIDI = frozenset({"improved", "no_change", "worse", "cannot_tell", "not_tested"})
_NOT_RECORDED = "not_recorded_by_legacy_page"


def validate_other_refinement_review(
    document: Mapping[str, Any], *, result: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one complete browser export against one exact result."""

    value = _json_copy(document)
    fields = frozenset(value)
    detailed_fields = fields - {"exported_at"}
    if detailed_fields == _LEGACY_FIELDS and "exported_at" not in fields:
        variant = "legacy_minimal"
    elif detailed_fields == _DETAILED_FIELDS:
        variant = "detailed"
    else:
        raise ValueError("other-refinement review fields differ")
    if value.get("schema") != OTHER_REFINEMENT_REVIEW_SCHEMA:
        raise ValueError("unsupported other-refinement review schema")
    if value.get("result_sha256") != result.get("document_sha256"):
        raise ValueError("other-refinement review result binding differs")
    target_id = result.get("request", {}).get("target_id")
    if value.get("target_id") != target_id:
        raise ValueError("other-refinement review target binding differs")
    if value.get("listened") is not True:
        raise ValueError("other-refinement review must confirm listening")
    if value.get("usefulness") not in _USEFULNESS:
        raise ValueError("other-refinement review usefulness is invalid")
    notes = value.get("notes")
    if not isinstance(notes, str) or len(notes) > 5_000:
        raise ValueError("other-refinement review notes are invalid")
    if value.get("activation_choice") != "none":
        raise ValueError("other-refinement review cannot activate a candidate")
    if variant == "detailed":
        for field in (
            "bleed",
            "missing_content",
            "artefacts",
            "timing_or_join_problems",
        ):
            if value.get(field) not in _PROBLEM:
                raise ValueError(f"other-refinement review {field} is invalid")
        if value.get("downstream_midi") not in _MIDI:
            raise ValueError(
                "other-refinement review downstream MIDI outcome is invalid"
            )
    if "exported_at" in value:
        _timestamp(value["exported_at"], "other-refinement review exported_at")
    value["_validated_variant"] = variant
    return value


def record_other_refinement_review(
    result_root: str | Path,
    review_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Reverify one result and publish separate, path-free listening evidence."""

    root = Path(result_root).expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("other-refinement result root must be a real directory")
    plan_path = root / "TECHNICAL/other-refinement-plan.json"
    result_path = root / "TECHNICAL/other-refinement-result.json"
    plan = _load_json(plan_path, "other-refinement plan", maximum_bytes=1024 * 1024)
    result = _load_json(
        result_path, "other-refinement result", maximum_bytes=1024 * 1024
    )
    plan = validate_other_refinement_plan(plan)
    result = validate_other_refinement_result(result, plan=plan, root=root)

    source_review = Path(review_path).expanduser().absolute()
    review = _load_json(
        source_review, "other-refinement reviewed export", maximum_bytes=64 * 1024
    )
    validated = validate_other_refinement_review(review, result=result)
    variant = validated.pop("_validated_variant")
    detailed = variant == "detailed"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record: dict[str, Any] = {
        "schema": OTHER_REFINEMENT_FEEDBACK_SCHEMA,
        "status": "valid_local_listening_evidence_no_activation",
        "binding": {
            "scope_id": result["scope_id"],
            "contract_profile_id": result["contract_profile_id"],
            "execution_profile_id": result["execution"]["profile_id"],
            "target_id": result["request"]["target_id"],
            "plan_document_sha256": plan["document_sha256"],
            "result_document_sha256": result["document_sha256"],
            "result_file_sha256": file_sha256(result_path),
            "parent_audio_sha256": result["parent"]["sha256"],
            "review_export_sha256": file_sha256(source_review),
        },
        "review": validated,
        "review_format": {
            "variant": variant,
            "detailed_problem_fields_recorded": detailed,
            "omitted_fields_mean_pass": False,
        },
        "historical_plan": {
            "blockers_preserved": bool(plan["blockers"]),
            "blockers": list(plan["blockers"]),
            "review_validation_does_not_authorize_reexecution": True,
        },
        "observations": {
            "usefulness": validated["usefulness"],
            "bleed": validated.get("bleed", _NOT_RECORDED),
            "missing_content": validated.get("missing_content", _NOT_RECORDED),
            "artefacts": validated.get("artefacts", _NOT_RECORDED),
            "timing_or_join_problems": validated.get(
                "timing_or_join_problems", _NOT_RECORDED
            ),
            "downstream_midi": validated.get("downstream_midi", _NOT_RECORDED),
        },
        "feedback_policy": {
            "valid_report_count_delta": 1,
            "review_trigger": "30 days or 10 valid reports, whichever occurs first",
            "poor_or_mixed_feedback_disables_profile": False,
            "musical_feedback_is_stop_ship_evidence": False,
            "objective_stop_ship_assessed_by_this_review": False,
        },
        "permissions": {
            "candidate_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "midi_activation_permitted": False,
            "model_promotion_permitted": False,
            "profile_pause_permitted": False,
        },
        "effects": {
            "audio_mutated": False,
            "model_executed": False,
            "network_used": False,
            "candidate_selected": False,
            "source_graph_mutated": False,
            "midi_created": False,
            "profile_status_changed": False,
        },
        "recorded_at": now,
    }
    record["document_sha256"] = _document_sha256(record)
    _write_new_private_json(Path(out).expanduser().absolute(), record)
    return record


def _load_json(path: Path, label: str, *, maximum_bytes: int) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular file")
    if path.stat().st_size > maximum_bytes:
        raise ValueError(f"{label} is too large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _write_new_private_json(path: Path, value: Mapping[str, Any]) -> None:
    if os.path.lexists(path):
        raise FileExistsError(f"review evidence output already exists: {path}")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("review evidence output parent must be a real directory")
    payload = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    )
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _document_sha256(document: Mapping[str, Any]) -> str:
    value = dict(document)
    value.pop("document_sha256", None)
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        copied = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("other-refinement review must be finite JSON") from exc
    if not isinstance(copied, dict):
        raise ValueError("other-refinement review must be a JSON object")
    return copied


__all__ = [
    "OTHER_REFINEMENT_FEEDBACK_SCHEMA",
    "OTHER_REFINEMENT_REVIEW_SCHEMA",
    "record_other_refinement_review",
    "validate_other_refinement_review",
]
