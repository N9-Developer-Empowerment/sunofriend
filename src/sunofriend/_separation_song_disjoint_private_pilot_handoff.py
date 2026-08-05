"""Copy one reviewed song-disjoint result into a private two-stem handoff.

This is deliberately narrower than a product integration.  It replays the
exact human-review resolver, verifies the automatic pilot envelope and stitch,
then copies the already-reviewed vocals and instrumental PCM24 WAVs without
changing their bytes.  Reconstruction is retained as a diagnostic only.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    _FALSE_PERMISSIONS,
)
from ._separation_song_disjoint_private_pilot import (
    _load_verified_song_disjoint_private_pilot_evidence,
)
from ._separation_song_disjoint_private_pilot_review import (
    REPORT_NAME as REVIEW_RESULT_NAME,
    RESULT_SCHEMA as REVIEW_RESULT_SCHEMA,
    RESULT_STATUS_AUTHORIZED,
    _resolve_private_song_disjoint_pilot_review,
)


SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-handoff.v1"
STATUS = "bounded_private_two_stem_handoff_complete"
POLICY_ID = "exact-reviewed-two-stem-private-handoff-v1"
REPORT_NAME = "private-separation-song-disjoint-pilot-handoff.json"
_PRIMARY_ROLES = ("vocals", "instrumental")
_DIAGNOSTIC_ROLES = ("reconstruction",)


def _prepare_private_song_disjoint_pilot_handoff(
    review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    pilot_evidence_path: str | Path,
    package_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one fresh exact-byte private two-stem handoff directory."""

    output = Path(out_dir).expanduser().absolute()
    _require_private_directory(
        output.parent,
        "song-disjoint private pilot handoff parent",
    )
    if os.path.lexists(output):
        raise FileExistsError(f"song-disjoint private pilot handoff exists: {output}")

    context = _load_context(
        review_result_path,
        reviewed_export_path=reviewed_export_path,
        pilot_evidence_path=pilot_evidence_path,
        package_dir=package_dir,
    )
    _require_output_disjoint(output, context=context)

    output.mkdir(mode=0o700)
    stems_root = output / "STEMS"
    diagnostic_root = output / "DIAGNOSTIC"
    stems_root.mkdir(mode=0o700)
    diagnostic_root.mkdir(mode=0o700)

    stitch = context["stitch"]
    copied: dict[str, dict[str, Any]] = {}
    for role in _PRIMARY_ROLES:
        copied[role] = _copy_artifact(
            context["package"],
            stitch["artifacts"][role],
            target=stems_root / f"{role}.wav",
            output_path=f"STEMS/{role}.wav",
            label=f"song-disjoint private pilot {role}",
        )
    for role in _DIAGNOSTIC_ROLES:
        copied[role] = _copy_artifact(
            context["package"],
            stitch["artifacts"][role],
            target=diagnostic_root / f"{role}.wav",
            output_path=f"DIAGNOSTIC/{role}.wav",
            label=f"song-disjoint private pilot {role}",
        )

    _reverify_context(context)
    review_result = context["review_result"]["document"]
    pilot = context["pilot"]["document"]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "pilot_evidence_sha256": context["pilot"]["sha256"],
            "pilot_evidence_document_sha256": pilot["document_sha256"],
            "review_result_sha256": context["review_result"]["sha256"],
            "review_result_document_sha256": review_result["document_sha256"],
            "review_export_sha256": review_result["bindings"][
                "review_export_sha256"
            ],
            "stitch_report_sha256": context["stitch_sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
        },
        "track": {
            "track_id": pilot["source_distinction"]["pilot_track_id"],
            "track_title": pilot["source_distinction"]["pilot_track_title"],
        },
        "clock": deepcopy(stitch["clock"]),
        "handoff": {
            "kind": "two_stem_vocals_and_instrumental",
            "primary_roles": list(_PRIMARY_ROLES),
            "diagnostic_roles": list(_DIAGNOSTIC_ROLES),
            "source_audio_included": False,
            "audio_sample_values_changed": False,
            "all_copies_match_reviewed_stitch_sha256": True,
            "private_pilot_scope": "this_exact_reviewed_output_only",
        },
        "artifacts": copied,
        "human_review": {
            "full_song_ratings": deepcopy(
                review_result["review_summary"]["full_song_ratings"]
            ),
            "reviewed_boundary_count": review_result["review_summary"][
                "reviewed_boundary_count"
            ],
            "audible_join_boundaries_by_role": deepcopy(
                review_result["review_summary"][
                    "audible_join_boundaries_by_role"
                ]
            ),
            "cannot_tell_boundaries_by_role": deepcopy(
                review_result["review_summary"][
                    "cannot_tell_boundaries_by_role"
                ]
            ),
            "listener_notes_copied": False,
        },
        "readiness": {
            "automatic_pilot_evidence_complete": True,
            "human_review_complete": True,
            "exact_output_authorized_for_bounded_private_pilot": True,
            "two_stem_handoff_complete": True,
            "separator_selected_or_accepted": False,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "permissions": {
            **dict(_FALSE_PERMISSIONS),
            "bounded_private_pilot_output_use": True,
        },
        "effects": {
            "audio_bytes_copied": True,
            "audio_sample_values_mutated": False,
            "handoff_created": True,
            "human_review_completed_or_mutated": False,
            "model_run": False,
            "product_contract_mutated": False,
            "publication_state_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This handoff contains an exact reviewed two-stem result, not a general or accepted separator.",
            "Vocals and instrumental are primary private-pilot outputs; reconstruction is diagnostic only.",
            "The original source is intentionally not copied into the handoff.",
            "Boundary findings remain listening diagnostics and are not rewritten by this handoff.",
            "Simple, Studio, TUI, CLI, source-graph, download and publication routes remain disabled.",
            "Input evidence is rechecked serially rather than held as one atomic filesystem snapshot.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    report = output / REPORT_NAME
    _write_json_exclusive(report, document)
    _verify_output(output, document)
    return {**document, "handoff_dir": str(output), "report": str(report)}


def _load_context(
    review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    pilot_evidence_path: str | Path,
    package_dir: str | Path,
) -> dict[str, Any]:
    review_result = _load_private_json_snapshot(
        review_result_path,
        "song-disjoint private pilot review result",
    )
    if review_result["path"].name != REVIEW_RESULT_NAME:
        raise ValueError("song-disjoint private pilot review result filename differs")
    replay = _replay_review_result(
        reviewed_export_path,
        pilot_evidence_path=pilot_evidence_path,
        package_dir=package_dir,
    )
    if review_result["document"] != replay:
        raise ValueError("song-disjoint private pilot review result differs")
    if (
        replay.get("schema") != REVIEW_RESULT_SCHEMA
        or replay.get("status") != RESULT_STATUS_AUTHORIZED
        or replay.get("permissions", {}).get("bounded_private_pilot_output_use")
        is not True
        or replay.get("readiness", {}).get(
            "bounded_private_pilot_output_use_permitted"
        )
        is not True
    ):
        raise ValueError("song-disjoint private pilot output is not authorized")

    pilot = _load_verified_song_disjoint_private_pilot_evidence(
        pilot_evidence_path
    )
    package = Path(package_dir).expanduser().absolute()
    _require_private_directory(package, "song-disjoint private pilot stitch package")
    stitch_path = package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(package, stitch)
    bindings = replay["bindings"]
    if (
        bindings.get("pilot_evidence_sha256") != pilot["sha256"]
        or bindings.get("pilot_evidence_document_sha256")
        != pilot["document"]["document_sha256"]
        or bindings.get("pilot_stitch_sha256") != _sha256(stitch_path)
        or bindings.get("pilot_stitch_document_sha256")
        != stitch["document_sha256"]
        or stitch.get("clock")
        != pilot["document"]["automatic_execution"]["clock"]
    ):
        raise ValueError("song-disjoint private pilot handoff binding differs")
    return {
        "review_result": review_result,
        "reviewed_export_path": Path(reviewed_export_path).expanduser().absolute(),
        "pilot": pilot,
        "package": package,
        "stitch_path": stitch_path,
        "stitch": stitch,
        "stitch_sha256": _sha256(stitch_path),
        "pilot_evidence_path": Path(pilot_evidence_path).expanduser().absolute(),
    }


def _replay_review_result(
    reviewed_export_path: str | Path,
    *,
    pilot_evidence_path: str | Path,
    package_dir: str | Path,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="sunofriend-song-disjoint-handoff-review-"
    ) as temporary_name:
        temporary = Path(temporary_name)
        temporary.chmod(0o700)
        replay = _resolve_private_song_disjoint_pilot_review(
            reviewed_export_path,
            pilot_evidence_path=pilot_evidence_path,
            package_dir=package_dir,
            out=temporary / REVIEW_RESULT_NAME,
        )
    return {key: deepcopy(value) for key, value in replay.items() if key != "report"}


def _reverify_context(context: Mapping[str, Any]) -> None:
    replay = _replay_review_result(
        context["reviewed_export_path"],
        pilot_evidence_path=context["pilot_evidence_path"],
        package_dir=context["package"],
    )
    if replay != context["review_result"]["document"]:
        raise ValueError("song-disjoint private pilot handoff evidence changed")
    pilot = _load_verified_song_disjoint_private_pilot_evidence(
        context["pilot_evidence_path"]
    )
    stitch = _load_stitch_report(context["stitch_path"])
    _verify_stitch_audio(context["package"], stitch)
    if (
        pilot["sha256"] != context["pilot"]["sha256"]
        or pilot["document"] != context["pilot"]["document"]
        or _sha256(context["stitch_path"]) != context["stitch_sha256"]
        or stitch != context["stitch"]
    ):
        raise ValueError("song-disjoint private pilot handoff evidence changed")


def _copy_artifact(
    package: Path,
    claim: Mapping[str, Any],
    *,
    target: Path,
    output_path: str,
    label: str,
) -> dict[str, Any]:
    relative = _safe_relative_path(claim.get("path"), label)
    source = package.joinpath(*relative.parts)
    _require_private_regular(source, label)
    resolved_package = package.resolve(strict=True)
    resolved_source = source.resolve(strict=True)
    if resolved_package not in resolved_source.parents:
        raise ValueError(f"{label} escapes the stitch package")

    source_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    target_flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    source_descriptor = os.open(source, source_flags)
    source_before = os.fstat(source_descriptor)
    try:
        if source_before.st_size != claim.get("bytes"):
            raise ValueError(f"{label} byte count differs")
        target_descriptor = os.open(target, target_flags, 0o600)
        try:
            digest = hashlib.sha256()
            copied = 0
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                offset = 0
                while offset < len(chunk):
                    written = os.write(target_descriptor, chunk[offset:])
                    if written <= 0:
                        raise RuntimeError(f"{label} copy made no progress")
                    offset += written
                    copied += written
            os.fsync(target_descriptor)
            target_state = os.fstat(target_descriptor)
        finally:
            os.close(target_descriptor)
        source_after = os.fstat(source_descriptor)
    finally:
        os.close(source_descriptor)

    expected_hash = claim.get("sha256")
    if (
        _file_identity(source_before) != _file_identity(source_after)
        or copied != source_before.st_size
        or target_state.st_size != copied
        or digest.hexdigest() != expected_hash
        or _sha256(target) != expected_hash
    ):
        raise ValueError(f"{label} changed during exact copy")
    return {
        "path": output_path,
        "sha256": expected_hash,
        "bytes": copied,
        "geometry": deepcopy(claim["geometry"]),
        "copied_byte_identically": True,
        "sample_values_changed": False,
    }


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ValueError(f"{label} path differs")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ValueError(f"{label} path differs")
    return relative


def _file_identity(state: os.stat_result) -> tuple[int, int, int, int]:
    return (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns)


def _verify_output(output: Path, document: Mapping[str, Any]) -> None:
    if (
        set(path.name for path in output.iterdir())
        != {"STEMS", "DIAGNOSTIC", REPORT_NAME}
        or set(path.name for path in (output / "STEMS").iterdir())
        != {"vocals.wav", "instrumental.wav"}
        or set(path.name for path in (output / "DIAGNOSTIC").iterdir())
        != {"reconstruction.wav"}
    ):
        raise ValueError("song-disjoint private pilot handoff inventory differs")
    for role, record in document["artifacts"].items():
        path = output.joinpath(*PurePosixPath(record["path"]).parts)
        _require_private_regular(path, f"song-disjoint handoff {role}")
        if path.stat().st_size != record["bytes"] or _sha256(path) != record["sha256"]:
            raise ValueError("song-disjoint private pilot handoff artifact differs")
    report = output / REPORT_NAME
    snapshot = _load_private_json_snapshot(report, "song-disjoint pilot handoff")
    if snapshot["document"] != document:
        raise ValueError("song-disjoint private pilot handoff report differs")


def _require_output_disjoint(
    output: Path,
    *,
    context: Mapping[str, Any],
) -> None:
    files = (
        context["review_result"]["path"],
        context["reviewed_export_path"],
        context["pilot_evidence_path"],
        context["stitch_path"],
    )
    for value in files:
        if output == Path(value).resolve(strict=True):
            raise ValueError("song-disjoint private pilot handoff overlaps evidence")
    package = context["package"].resolve(strict=True)
    if output == package or package in output.parents:
        raise ValueError("song-disjoint private pilot handoff overlaps evidence")


__all__: tuple[str, ...] = ()
