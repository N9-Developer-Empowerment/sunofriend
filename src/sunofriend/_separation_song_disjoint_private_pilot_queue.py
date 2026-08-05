"""Inventory explicit song-disjoint private-pilot human reviews.

This developer-only helper verifies completed automatic pilot envelopes and
maps explicitly supplied browser exports by immutable package commitment.  It
never opens an answer key, resolves a review, selects a separator, or discovers
files outside the caller's bounded inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
from typing import Any, Iterable, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_song_disjoint_private_pilot import (
    REPORT_NAME as EVIDENCE_REPORT_NAME,
    _load_verified_song_disjoint_private_pilot_evidence,
)
from ._separation_song_disjoint_private_pilot_pipeline import (
    EVIDENCE_DIRECTORY,
    _FALSE_PERMISSIONS as PIPELINE_FALSE_PERMISSIONS,
    REPORT_NAME as PIPELINE_REPORT_NAME,
    SCHEMA as PIPELINE_SCHEMA,
    STATUS as PIPELINE_STATUS,
    STITCH_DIRECTORY,
)
from ._separation_song_disjoint_private_pilot_review import (
    _status_private_song_disjoint_pilot_review,
)


SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-review-queue.v1"
STATUS = "private_review_queue_verified_no_activation"
REPORT_NAME = "private-separation-song-disjoint-pilot-review-queue.json"
REVIEW_SCHEMA = "sunofriend.private-separation-boundary-review.v1"
REVIEW_SEED_NAME = "separation_boundary_review.json"
REVIEW_HTML_NAME = "separation_boundary_review.html"
REVIEW_RELATIVE_DIRECTORY = Path("BOUNDARY-REVIEW")
MAXIMUM_PILOTS = 32
MAXIMUM_REVIEW_FILES = 256
MAXIMUM_REVIEW_DIRECTORIES = 8
MAXIMUM_REVIEW_BYTES = 8 * 1024 * 1024
_SHA256_LENGTH = 64


def _build_song_disjoint_private_pilot_review_queue(
    pipeline_roots: Sequence[str | Path],
    *,
    review_paths: Sequence[str | Path] = (),
    review_directories: Sequence[str | Path] = (),
    out: str | Path | None = None,
) -> dict[str, Any]:
    """Verify an explicit bounded review queue and optionally persist it."""

    roots = _canonical_distinct_paths(
        pipeline_roots,
        label="private pilot pipeline root",
        maximum=MAXIMUM_PILOTS,
    )
    if not roots:
        raise ValueError("at least one private pilot pipeline root is required")
    explicit_reviews = _canonical_distinct_paths(
        review_paths,
        label="private pilot reviewed export",
        maximum=MAXIMUM_REVIEW_FILES,
    )
    review_dirs = _canonical_distinct_paths(
        review_directories,
        label="private pilot review directory",
        maximum=MAXIMUM_REVIEW_DIRECTORIES,
    )
    review_inventory = _discover_review_exports(
        explicit_reviews,
        review_directories=review_dirs,
    )
    contexts = [_load_pipeline_context(root) for root in roots]
    commitments = [item["package_commitment"] for item in contexts]
    if len(set(commitments)) != len(commitments):
        raise ValueError("private pilot queue package commitments must be distinct")

    entries: list[dict[str, Any]] = []
    local_actions: list[dict[str, Any]] = []
    matched_export_hashes: set[str] = set()
    for context in contexts:
        matches = _matching_review_exports(
            review_inventory,
            package_commitment=context["package_commitment"],
        )
        entry, action, used_hashes = _queue_entry(context, matches=matches)
        entries.append(entry)
        local_actions.append(action)
        matched_export_hashes.update(used_hashes)

    state_counts = {
        state: sum(entry["state"] == state for entry in entries)
        for state in (
            "human_review_pending",
            "matching_review_export_requires_owner_only_mode",
            "matching_review_export_conflict",
            "matching_review_export_failed_verification",
            "complete_review_verified_unresolved",
        )
    }
    report_created = out is not None
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "summary": {
            "pilot_count": len(entries),
            "reviewed_export_candidate_count": len(review_inventory),
            "matched_reviewed_export_content_count": len(matched_export_hashes),
            "unmatched_reviewed_export_content_count": len(
                {item["sha256"] for item in review_inventory}
                - matched_export_hashes
            ),
            "state_counts": state_counts,
            "all_reviews_verified_complete": all(
                entry["state"] == "complete_review_verified_unresolved"
                for entry in entries
            ),
        },
        "pilots": entries,
        "permissions": {
            **dict(PIPELINE_FALSE_PERMISSIONS),
            "bounded_private_pilot_output_use": False,
        },
        "effects": {
            "answer_key_opened": False,
            "audio_created_or_mutated": False,
            "human_review_completed_or_mutated": False,
            "model_run": False,
            "product_contract_mutated": False,
            "queue_report_created": report_created,
            "review_resolved": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "Only explicitly supplied pipeline roots and review files or directories were inspected.",
            "Review-directory discovery is bounded, non-recursive and limited to review-schema JSON files.",
            "A verified complete export is still unresolved human evidence and authorizes no output here.",
            "The queue does not open answer keys, infer choices, run a model or enable a product route.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)

    report_path: Path | None = None
    if out is not None:
        report_path = _write_queue_report(out, document=document, contexts=contexts)
    return {
        **document,
        "report": None if report_path is None else str(report_path),
        "local_actions": local_actions,
    }


def _load_pipeline_context(root: Path) -> dict[str, Any]:
    _require_private_directory(root, "private pilot review queue pipeline")
    report = _load_private_json_snapshot(
        root / PIPELINE_REPORT_NAME,
        "private pilot pipeline report",
    )
    document = report["document"]
    permissions = document.get("permissions")
    stages = document.get("stages")
    bindings = document.get("bindings")
    if (
        document.get("schema") != PIPELINE_SCHEMA
        or document.get("status") != PIPELINE_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(permissions, Mapping)
        or dict(permissions) != PIPELINE_FALSE_PERMISSIONS
        or not isinstance(stages, Mapping)
        or stages.get("human_review") != "pending"
        or not isinstance(bindings, Mapping)
    ):
        raise ValueError("private pilot pipeline report differs")

    evidence_path = root / EVIDENCE_DIRECTORY / EVIDENCE_REPORT_NAME
    evidence = _load_verified_song_disjoint_private_pilot_evidence(evidence_path)
    evidence_document = evidence["document"]
    evidence_bindings = evidence_document["bindings"]
    if (
        bindings.get("automatic_evidence_sha256") != evidence["sha256"]
        or bindings.get("automatic_evidence_document_sha256")
        != evidence_document["document_sha256"]
        or bindings.get("pilot_review_seed_sha256")
        != evidence_bindings["pilot_review_seed_sha256"]
        or document.get("human_review") != evidence_document["human_review"]
        or document.get("clock") != evidence_document["automatic_execution"]["clock"]
    ):
        raise ValueError("private pilot pipeline evidence binding differs")

    review_root = root / STITCH_DIRECTORY / REVIEW_RELATIVE_DIRECTORY
    review_seed_path = review_root / REVIEW_SEED_NAME
    review_html_path = review_root / REVIEW_HTML_NAME
    review_seed = _load_private_json_snapshot(
        review_seed_path,
        "private pilot review seed",
    )
    seed_document = review_seed["document"]
    human_review = evidence_document["human_review"]
    if (
        seed_document.get("schema") != REVIEW_SCHEMA
        or seed_document.get("status") != "unreviewed"
        or seed_document.get("evidence_scope") != "private_development_only"
        or seed_document.get("package_commitment")
        != human_review["package_commitment"]
        or review_seed["sha256"] != evidence_bindings["pilot_review_seed_sha256"]
        or _sha256(review_html_path) != human_review["html_sha256"]
    ):
        raise ValueError("private pilot review package differs")
    distinction = evidence_document["source_distinction"]
    return {
        "root": root,
        "pipeline_report": report,
        "evidence_path": evidence_path,
        "evidence": evidence,
        "package_dir": root / STITCH_DIRECTORY,
        "review_html": review_html_path,
        "package_commitment": human_review["package_commitment"],
        "track_id": distinction["pilot_track_id"],
        "track_title": distinction["pilot_track_title"],
        "boundary_count": human_review["boundary_count"],
        "full_song_role_count": human_review["full_song_role_count"],
    }


def _queue_entry(
    context: Mapping[str, Any],
    *,
    matches: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    by_hash: dict[str, list[Mapping[str, Any]]] = {}
    for item in matches:
        by_hash.setdefault(item["sha256"], []).append(item)
    base = {
        "track_id": context["track_id"],
        "track_title": context["track_title"],
        "pipeline_document_sha256": context["pipeline_report"]["document"][
            "document_sha256"
        ],
        "automatic_evidence_document_sha256": context["evidence"]["document"][
            "document_sha256"
        ],
        "package_commitment": context["package_commitment"],
        "boundary_count": context["boundary_count"],
        "full_song_role_count": context["full_song_role_count"],
        "review_page": str(
            Path(STITCH_DIRECTORY) / REVIEW_RELATIVE_DIRECTORY / REVIEW_HTML_NAME
        ),
        "reviewed_export_sha256": None,
        "review_status_document_sha256": None,
        "would_authorize_bounded_private_pilot_output_use": None,
    }
    action: dict[str, Any] = {
        "track_id": context["track_id"],
        "review_html": str(context["review_html"]),
        "reviewed_export": None,
        "next_command": None,
    }
    used_hashes = set(by_hash)
    if not by_hash:
        return (
            {
                **base,
                "state": "human_review_pending",
                "next_action": "complete_and_export_the_local_review",
            },
            action,
            used_hashes,
        )
    if len(by_hash) > 1:
        return (
            {
                **base,
                "state": "matching_review_export_conflict",
                "next_action": "supply_one_exact_review_export_explicitly",
            },
            action,
            used_hashes,
        )

    same_content = next(iter(by_hash.values()))
    secure = [item for item in same_content if item["owner_only"]]
    chosen = secure[0] if secure else same_content[0]
    action["reviewed_export"] = str(chosen["path"])
    base["reviewed_export_sha256"] = chosen["sha256"]
    if not secure:
        action["next_command"] = f"chmod 600 {shlex.quote(str(chosen['path']))}"
        return (
            {
                **base,
                "state": "matching_review_export_requires_owner_only_mode",
                "next_action": "make_the_matching_export_owner_only_then_recheck",
            },
            action,
            used_hashes,
        )

    try:
        verified = _status_private_song_disjoint_pilot_review(
            chosen["path"],
            pilot_evidence_path=context["evidence_path"],
            package_dir=context["package_dir"],
        )
    except (OSError, ValueError):
        return (
            {
                **base,
                "state": "matching_review_export_failed_verification",
                "next_action": "retain_the_export_and_repeat_or_diagnose_the_review",
            },
            action,
            used_hashes,
        )
    base["review_status_document_sha256"] = verified["document_sha256"]
    base["would_authorize_bounded_private_pilot_output_use"] = verified[
        "assessment_preview"
    ]["would_authorize_bounded_private_pilot_output_use"]
    action["next_command"] = _resolution_command(context, chosen["path"])
    return (
        {
            **base,
            "state": "complete_review_verified_unresolved",
            "next_action": "resolve_the_verified_review_into_a_fresh_private_result",
        },
        action,
        used_hashes,
    )


def _resolution_command(context: Mapping[str, Any], review: Path) -> str:
    result_placeholder = (
        "<fresh-owner-only-directory>/"
        "private-separation-song-disjoint-pilot-review-result.json"
    )
    parts = (
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "scripts/private-separation-song-disjoint-pilot-review.py",
        "--resolve",
        str(review),
        "--pilot-evidence",
        str(context["evidence_path"]),
        "--package-dir",
        str(context["package_dir"]),
        "--out",
        result_placeholder,
    )
    return " ".join(shlex.quote(item) for item in parts)


def _discover_review_exports(
    explicit_paths: Sequence[Path],
    *,
    review_directories: Sequence[Path],
) -> list[dict[str, Any]]:
    candidates: dict[Path, bool] = {path: True for path in explicit_paths}
    for directory in review_directories:
        try:
            before = os.lstat(directory)
        except OSError as error:
            raise ValueError("private pilot review directory is unavailable") from error
        if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise ValueError("private pilot review directory must be a non-link directory")
        names = sorted(
            path
            for path in directory.iterdir()
            if path.name.lower().endswith(".json")
        )
        if len(names) > MAXIMUM_REVIEW_FILES:
            raise ValueError("private pilot review directory contains too many JSON files")
        for path in names:
            candidates.setdefault(path.absolute(), False)
    if len(candidates) > MAXIMUM_REVIEW_FILES:
        raise ValueError("too many private pilot review JSON candidates")

    discovered: list[dict[str, Any]] = []
    for path, explicit in sorted(candidates.items(), key=lambda item: str(item[0])):
        try:
            snapshot = _read_review_candidate(path)
        except ValueError:
            if explicit:
                raise
            continue
        document = snapshot["document"]
        if (
            document.get("schema") != REVIEW_SCHEMA
            or document.get("status") != "reviewed"
            or document.get("evidence_scope") != "private_development_only"
            or not _valid_sha256(document.get("package_commitment"))
        ):
            if explicit:
                raise ValueError("explicit private pilot review export differs")
            continue
        discovered.append(
            {
                **snapshot,
                "package_commitment": document["package_commitment"],
            }
        )
    return discovered


def _read_review_candidate(path: Path) -> dict[str, Any]:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ValueError("review export cannot be opened without link protection")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as error:
        raise ValueError("review export must be a regular non-link file") from error
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_size <= 0
            or before.st_size > MAXIMUM_REVIEW_BYTES
        ):
            raise ValueError("review export file identity is invalid")
        contents = os.read(descriptor, MAXIMUM_REVIEW_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _stat_identity(before) != _stat_identity(after) or len(contents) != before.st_size:
        raise ValueError("review export changed while it was read")
    try:
        document = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("review export differs") from error
    if not isinstance(document, dict):
        raise ValueError("review export differs")
    return {
        "path": path,
        "document": document,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "owner_only": stat.S_IMODE(before.st_mode) & 0o077 == 0,
    }


def _matching_review_exports(
    inventory: Iterable[Mapping[str, Any]],
    *,
    package_commitment: str,
) -> list[Mapping[str, Any]]:
    return [
        item
        for item in inventory
        if item.get("package_commitment") == package_commitment
    ]


def _write_queue_report(
    value: str | Path,
    *,
    document: Mapping[str, Any],
    contexts: Sequence[Mapping[str, Any]],
) -> Path:
    output = Path(value).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private pilot review queue filename must be {REPORT_NAME}")
    _require_private_directory(output.parent, "private pilot review queue parent")
    if os.path.lexists(output):
        raise FileExistsError(f"private pilot review queue report exists: {output}")
    roots = [Path(context["root"]).resolve(strict=True) for context in contexts]
    if any(root == output or root in output.parents for root in roots):
        raise ValueError("private pilot review queue output overlaps pipeline evidence")
    _write_json_exclusive(output, document)
    return output


def _canonical_distinct_paths(
    values: Sequence[str | Path],
    *,
    label: str,
    maximum: int,
) -> list[Path]:
    if len(values) > maximum:
        raise ValueError(f"too many {label} values")
    paths = [Path(value).expanduser().absolute() for value in values]
    if len(set(paths)) != len(paths):
        raise ValueError(f"{label} values must be distinct")
    return paths


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


__all__: tuple[str, ...] = ()
