"""Resolve one exact private full-song and chunk-boundary listening review.

The browser export is human evidence only.  Resolution re-verifies the sealed
stitch, seed and every referenced audio file, then records what the listener
entered without accepting, selecting or exposing a separator to the product.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import _require_private_directory, _require_private_regular
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_NAME,
    REVIEW_SCHEMA,
    SCHEMA as STITCH_SCHEMA,
    STATUS as STITCH_STATUS,
    _FALSE_PERMISSIONS,
    _ROLES,
    _immutable_review,
)
from ._separation_melroformer_precision_review import _browser_json_equal


SCHEMA = "sunofriend.private-separation-full-song-review-result.v1"
STATUS = "complete_review_no_activation"
_BOUNDARY_RATINGS = frozenset(("clean", "audible_join", "cannot_tell"))
_FULL_SONG_RATINGS = frozenset(
    ("useful", "noticeable_problems", "not_useful", "cannot_tell")
)
_RATED_ROLES = ("vocals", "instrumental", "reconstruction")
_MAXIMUM_NOTES_CHARACTERS = 2_000
_FALSE_EFFECTS = {
    "separator_selected": False,
    "separator_accepted": False,
    "source_audio_mutated": False,
    "stitched_audio_mutated": False,
    "source_graph_mutated": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
}


def _resolve_private_separation_full_song_review(
    review_path: str | Path,
    *,
    package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Verify and record one complete listener export without activation."""

    package = Path(package_dir).expanduser().absolute()
    _require_private_directory(package, "private full-song stitch root")
    review_file = Path(review_path).expanduser().absolute()
    _require_private_regular(review_file, "reviewed full-song export")
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"private full-song review result already exists: {output}")

    stitch_path = package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    review_root = package / "BOUNDARY-REVIEW"
    _require_private_directory(review_root, "private full-song review package")
    seed_path = review_root / REVIEW_NAME
    seed = _load_json(seed_path, "private full-song review seed")
    review = _load_json(review_file, "reviewed full-song export")

    boundary_claim = stitch.get("boundary_review") or {}
    if (
        seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != "unreviewed"
        or seed.get("evidence_scope") != "private_development_only"
        or _sha256(seed_path) != boundary_claim.get("seed_sha256")
        or seed.get("package_commitment") != boundary_claim.get("package_commitment")
        or seed.get("package_commitment")
        != hashlib.sha256(canonical_json_bytes(_immutable_review(seed))).hexdigest()
    ):
        raise ValueError("private full-song review package seed differs")
    if not _browser_json_equal(_immutable_review(review), _immutable_review(seed)):
        raise ValueError("private full-song review export changed immutable evidence")
    _validate_completed_review(review, boundary_count=stitch["clock"]["boundary_count"])
    _verify_stitch_audio(package, stitch)
    _verify_review_audio(package, review)

    full_song = review["full_song"]
    units = review["units"]
    counts = {
        role: {rating: 0 for rating in sorted(_BOUNDARY_RATINGS)}
        for role in _RATED_ROLES
    }
    audible_join_boundaries = {role: [] for role in _RATED_ROLES}
    for unit in units:
        for role in _RATED_ROLES:
            rating = unit["ratings"][role]
            counts[role][rating] += 1
            if rating == "audible_join":
                audible_join_boundaries[role].append(unit["boundary_index"])

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "review_seed_sha256": _sha256(seed_path),
            "review_export_sha256": _sha256(review_file),
            "package_commitment": review["package_commitment"],
            "plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "execution_state_sha256": stitch["bindings"]["execution_state_sha256"],
        },
        "clock": deepcopy(stitch["clock"]),
        "full_song": {
            "heard_all": True,
            "ratings": deepcopy(full_song["ratings"]),
            "notes": full_song["notes"],
        },
        "boundary_summary": {
            "reviewed_boundaries": len(units),
            "rating_counts_by_role": counts,
            "audible_join_boundaries_by_role": audible_join_boundaries,
        },
        "boundaries": [
            {
                "boundary_index": unit["boundary_index"],
                "frame": unit["frame"],
                "seconds": unit["seconds"],
                "ratings": deepcopy(unit["ratings"]),
                "notes": unit["notes"],
            }
            for unit in units
        ],
        "readiness": {
            "worker_runs_complete": True,
            "stitched_outputs_complete": True,
            "exact_duration_and_frame_count_verified": True,
            "full_song_and_boundary_listening_complete": True,
            "full_song_quality_accepted": False,
            "publication_ready": False,
        },
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "clean_boundary_is_separator_accuracy": False,
            "review_completion_is_quality_acceptance": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_atomic(output, result)
    return {**result, "report": str(output)}


def _load_stitch_report(path: Path) -> dict[str, Any]:
    document = _load_json(path, "private full-song stitch report")
    clock = document.get("clock")
    boundary = document.get("boundary_review")
    if (
        document.get("schema") != STITCH_SCHEMA
        or document.get("status") != STITCH_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or not isinstance(clock, Mapping)
        or not isinstance(boundary, Mapping)
        or clock.get("boundary_count") != boundary.get("boundary_count")
        or not isinstance(clock.get("boundary_count"), int)
        or clock["boundary_count"] < 1
    ):
        raise ValueError("private full-song stitch report differs")
    return document


def _validate_completed_review(review: Mapping[str, Any], *, boundary_count: int) -> None:
    full_song = review.get("full_song")
    units = review.get("units")
    summary = review.get("summary")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "reviewed"
        or review.get("evidence_scope") != "private_development_only"
        or review.get("permissions") != _FALSE_PERMISSIONS
        or not isinstance(full_song, Mapping)
        or not isinstance(units, list)
        or len(units) != boundary_count
        or summary
        != {
            "full_song_reviewed": True,
            "reviewed_boundaries": boundary_count,
            "boundary_count": boundary_count,
        }
    ):
        raise ValueError("private full-song review is incomplete")
    _validate_ratings(
        full_song,
        allowed=_FULL_SONG_RATINGS,
        label="private full-song ratings",
    )
    for index, unit in enumerate(units, start=1):
        if not isinstance(unit, Mapping) or unit.get("boundary_index") != index:
            raise ValueError("private full-song boundary review order differs")
        _validate_ratings(
            unit,
            allowed=_BOUNDARY_RATINGS,
            label="private full-song boundary ratings",
        )


def _validate_ratings(
    item: Mapping[str, Any], *, allowed: frozenset[str], label: str
) -> None:
    ratings = item.get("ratings")
    notes = item.get("notes")
    if (
        item.get("heard_all") is not True
        or not isinstance(ratings, Mapping)
        or set(ratings) != set(_RATED_ROLES)
        or any(value not in allowed for value in ratings.values())
        or not isinstance(notes, str)
        or len(notes) > _MAXIMUM_NOTES_CHARACTERS
    ):
        raise ValueError(f"{label} are incomplete")


def _verify_stitch_audio(package: Path, stitch: Mapping[str, Any]) -> None:
    artifacts = stitch.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(_ROLES):
        raise ValueError("private full-song stitch artifact inventory differs")
    for role in _ROLES:
        _verify_audio_record(
            package,
            artifacts[role],
            label=f"private full-song {role} artifact",
            path_key="path",
        )


def _verify_review_audio(package: Path, review: Mapping[str, Any]) -> None:
    review_root = package / "BOUNDARY-REVIEW"
    referenced: set[str] = set()
    for role in _ROLES:
        record = review["full_song"]["audio"][role]
        path = _verify_audio_record(
            review_root,
            record,
            label=f"private full-song review {role} audio",
            path_key="path",
            required_root=package,
        )
        referenced.add(path.as_posix())
    for unit in review["units"]:
        audio = unit.get("audio")
        if not isinstance(audio, Mapping) or set(audio) != set(_ROLES):
            raise ValueError("private full-song boundary audio inventory differs")
        for role in _ROLES:
            path = _verify_audio_record(
                review_root,
                audio[role],
                label="private full-song boundary audio",
                path_key="path",
                required_root=review_root,
            )
            referenced.add(path.as_posix())
    expected_count = len(_ROLES) * (1 + len(review["units"]))
    if len(referenced) != expected_count:
        raise ValueError("private full-song review audio references differ")


def _verify_audio_record(
    root: Path,
    record: object,
    *,
    label: str,
    path_key: str,
    required_root: Path | None = None,
) -> Path:
    if not isinstance(record, Mapping):
        raise ValueError(f"{label} claim differs")
    relative = record.get(path_key)
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError(f"{label} path differs")
    unresolved = root / relative
    try:
        state = unresolved.lstat()
        path = unresolved.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} changed") from error
    boundary = required_root or root
    if (
        boundary != path
        and boundary not in path.parents
        or stat.S_ISLNK(state.st_mode)
        or not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) & 0o077
        or path.stat().st_size != record.get("bytes")
        or _sha256(path) != record.get("sha256")
    ):
        raise ValueError(f"{label} changed")
    return path


def _load_json(path: Path, label: str) -> dict[str, Any]:
    _require_private_regular(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} differs") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} differs")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.chmod(0o600)
        temporary.write_text(
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__: tuple[str, ...] = ()
