"""Promote an explicitly reviewed dry continuation into the next vocal base.

This module copies exact evidence only.  It does not migrate phrase decisions,
render audio, correct a performance, create a training label or authorize a
release.  The resulting owner-only package is a stable input for the next
iterative phrase session.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .audio_formats import file_sha256
from .source_receipt import canonical_json_bytes, document_sha256
from .vocal_comp_continuation import (
    VOCAL_CONTINUATION_PLAN_SCHEMA,
    VOCAL_CONTINUATION_RESULT_SCHEMA,
    VOCAL_CONTINUATION_REVIEW_SCHEMA,
    validate_vocal_continuation_review,
    verify_vocal_continuation_result,
)


VOCAL_ITERATION_BASE_SCHEMA = "sunofriend.vocal-iteration-base.v0"


def create_vocal_iteration_base(
    render_root: str | Path,
    plan: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    out_dir: str | Path,
    expected_review_sha256: str,
    confirm_next_iteration_base: bool = False,
) -> dict[str, Any]:
    """Copy one exact reviewed continuation into a fresh owner-only package."""

    root = Path(render_root).expanduser().resolve(strict=True)
    checked_review = validate_vocal_continuation_review(
        review, output_dir=root, plan=plan
    )
    if checked_review["document_sha256"] != expected_review_sha256:
        raise ValueError("owner review identity changed")
    if confirm_next_iteration_base is not True:
        raise ValueError("explicit next-iteration base confirmation is required")
    if (
        checked_review["authority"]["usable_as_next_iteration_base"] is not True
        or checked_review["decision"]["whole_excerpt"]
        != "usable_as_next_iteration_base"
    ):
        raise ValueError(
            "owner review did not accept this exact continuation as a base"
        )

    result_path = root / "TECHNICAL/dry-continuation-result.json"
    result = _read_json(result_path, VOCAL_CONTINUATION_RESULT_SCHEMA, "result")
    verify_vocal_continuation_result(root, plan, result)
    audio_record = result["artifacts"]["continuation_audio"]
    audio_path = _artifact(root, audio_record, "continuation audio")

    destination = Path(out_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("vocal iteration base output already exists")
    for immutable_root in (root,):
        try:
            destination.relative_to(immutable_root)
        except ValueError:
            continue
        raise ValueError("vocal iteration base output must be outside render evidence")

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    parent.chmod(0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=parent)
    )
    temporary.chmod(0o700)
    try:
        for name in ("AUDIO", "EVIDENCE"):
            (temporary / name).mkdir(mode=0o700)
        copied_audio = temporary / "AUDIO/reviewed-vocal-base.wav"
        _copy_private(audio_path, copied_audio)
        plan_path = temporary / "EVIDENCE/continuation-plan.json"
        result_copy = temporary / "EVIDENCE/continuation-result.json"
        review_path = temporary / "EVIDENCE/owner-review.json"
        _write_private(plan_path, canonical_json_bytes(plan))
        _copy_private(result_path, result_copy)
        _write_private(review_path, canonical_json_bytes(checked_review))

        document: dict[str, Any] = {
            "schema": VOCAL_ITERATION_BASE_SCHEMA,
            "status": "complete_immutable_reviewed_vocal_base",
            "method_natures": ["D", "H"],
            "binding": {
                "plan_schema": VOCAL_CONTINUATION_PLAN_SCHEMA,
                "plan_sha256": plan["document_sha256"],
                "result_schema": VOCAL_CONTINUATION_RESULT_SCHEMA,
                "result_sha256": result["document_sha256"],
                "review_schema": VOCAL_CONTINUATION_REVIEW_SCHEMA,
                "review_sha256": checked_review["document_sha256"],
            },
            "scope": dict(checked_review["scope"]),
            "clock": {
                "sample_rate": plan["clock"]["sample_rate"],
                "channels": plan["clock"]["channels"],
                "frames": plan["clock"]["output_frames"],
            },
            "artifacts": {
                "audio": _record(copied_audio, temporary),
                "plan": _record(plan_path, temporary),
                "result": _record(result_copy, temporary),
                "owner_review": _record(review_path, temporary),
            },
            "processing": dict(plan["processing"]),
            "authority": {
                "usable_as_next_iteration_base": True,
                "decisions_migrated": False,
                "phrase_selection_changed": False,
                "render_authorized": False,
                "correction_authorized": False,
                "release_authorized": False,
                "training_label_created": False,
                "training_execution_authorized": False,
            },
            "effects": {
                "source_mutated": False,
                "audio_rendered": False,
                "audio_copied_exactly": True,
                "decision_created": False,
                "correction_applied": False,
                "training_started": False,
                "model_weights_changed": False,
            },
            "network_used": False,
        }
        document["document_sha256"] = document_sha256(document)
        _write_private(
            temporary / "vocal-iteration-base.json", canonical_json_bytes(document)
        )
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return verify_vocal_iteration_base(destination)


def verify_vocal_iteration_base(root_value: str | Path) -> dict[str, Any]:
    """Reopen every retained byte and validate one iteration-base package."""

    root = Path(root_value).expanduser().resolve(strict=True)
    _validate_base_roster(root)
    document = _read_json(
        root / "vocal-iteration-base.json", VOCAL_ITERATION_BASE_SCHEMA, "base"
    )
    _validate_base_document(document)
    plan, result, review = _load_bound_evidence(root, document)
    _validate_base_binding(document, plan, result, review)
    _validate_base_audio_and_scope(document, result, review)
    _validate_base_policy(document)
    return document


def _validate_base_roster(root: Path) -> None:
    """Own the immutable package-root and exact-file-roster policy."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError("vocal iteration base root is unsafe")
    expected_files = {
        "AUDIO/reviewed-vocal-base.wav",
        "EVIDENCE/continuation-plan.json",
        "EVIDENCE/continuation-result.json",
        "EVIDENCE/owner-review.json",
        "vocal-iteration-base.json",
    }
    actual_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual_files != expected_files or any(
        path.is_symlink() for path in root.rglob("*")
    ):
        raise ValueError("vocal iteration base file roster changed")


def _validate_base_document(document: Mapping[str, Any]) -> None:
    """Own the stable top-level schema and completed-status contract."""

    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "scope",
        "clock",
        "artifacts",
        "processing",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("vocal iteration base fields changed")
    if document["status"] != "complete_immutable_reviewed_vocal_base":
        raise ValueError("vocal iteration base status changed")


def _load_bound_evidence(
    root: Path, document: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Open every artifact through its hash-bound package record."""

    for record in document["artifacts"].values():
        _artifact(root, record, "base artifact")
    plan = _read_json(
        root / document["artifacts"]["plan"]["path"],
        VOCAL_CONTINUATION_PLAN_SCHEMA,
        "plan",
    )
    result = _read_json(
        root / document["artifacts"]["result"]["path"],
        VOCAL_CONTINUATION_RESULT_SCHEMA,
        "result",
    )
    review = _read_json(
        root / document["artifacts"]["owner_review"]["path"],
        VOCAL_CONTINUATION_REVIEW_SCHEMA,
        "review",
    )
    return plan, result, review


def _validate_base_binding(
    document: Mapping[str, Any],
    plan: Mapping[str, Any],
    result: Mapping[str, Any],
    review: Mapping[str, Any],
) -> None:
    """Own cross-document identity binding for the retained evidence."""

    if document["binding"] != {
        "plan_schema": VOCAL_CONTINUATION_PLAN_SCHEMA,
        "plan_sha256": plan["document_sha256"],
        "result_schema": VOCAL_CONTINUATION_RESULT_SCHEMA,
        "result_sha256": result["document_sha256"],
        "review_schema": VOCAL_CONTINUATION_REVIEW_SCHEMA,
        "review_sha256": review["document_sha256"],
    }:
        raise ValueError("vocal iteration base binding changed")


def _validate_base_audio_and_scope(
    document: Mapping[str, Any],
    result: Mapping[str, Any],
    review: Mapping[str, Any],
) -> None:
    """Require byte identity, explicit owner acceptance and matching scope."""

    audio = document["artifacts"]["audio"]
    if (
        audio["sha256"] != result["artifacts"]["continuation_audio"]["sha256"]
        or review["binding"]["continuation_audio_sha256"] != audio["sha256"]
        or review["authority"]["usable_as_next_iteration_base"] is not True
        or review["decision"]["whole_excerpt"] != "usable_as_next_iteration_base"
    ):
        raise ValueError("vocal iteration base audio or owner authority changed")
    if document["scope"] != review["scope"]:
        raise ValueError("vocal iteration base scope changed")


def _validate_base_policy(document: Mapping[str, Any]) -> None:
    """Keep processing, authority and side effects at their reviewed limits."""

    if document["processing"] != {
        "resampling": False,
        "timing_correction": False,
        "pitch_correction": False,
        "gain_change": False,
        "normalisation": False,
        "limiting": False,
        "crossfade": False,
    }:
        raise ValueError("vocal iteration base processing changed")
    if document["authority"] != {
        "usable_as_next_iteration_base": True,
        "decisions_migrated": False,
        "phrase_selection_changed": False,
        "render_authorized": False,
        "correction_authorized": False,
        "release_authorized": False,
        "training_label_created": False,
        "training_execution_authorized": False,
    }:
        raise ValueError("vocal iteration base authority expanded")
    if (
        document["effects"]
        != {
            "source_mutated": False,
            "audio_rendered": False,
            "audio_copied_exactly": True,
            "decision_created": False,
            "correction_applied": False,
            "training_started": False,
            "model_weights_changed": False,
        }
        or document["network_used"] is not False
    ):
        raise ValueError("vocal iteration base effects changed")


def _read_json(path: Path, schema: str, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be readable JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ValueError(f"{label} schema changed")
    expected = value.get("document_sha256")
    unsigned = dict(value)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 changed")
    return value


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _artifact(root: Path, record: Mapping[str, Any], label: str) -> Path:
    relative = record.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} path is invalid")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "." in posix.parts:
        raise ValueError(f"{label} path escapes its root")
    path = (root / Path(*posix.parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes its root") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    if path.stat().st_size != record.get("bytes") or file_sha256(path) != record.get(
        "sha256"
    ):
        raise ValueError(f"{label} identity changed")
    return path


def _copy_private(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError("source artifact is unsafe")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())
    if file_sha256(source) != file_sha256(destination):
        raise ValueError("exact evidence copy changed")


def _write_private(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


__all__ = [
    "VOCAL_ITERATION_BASE_SCHEMA",
    "create_vocal_iteration_base",
    "verify_vocal_iteration_base",
]
