"""Build a fresh full-song review package for one verified v2 candidate.

The targeted join review is a narrow gate, not full-song acceptance.  This
module therefore requires an exact, passing v2 review result before copying
the unchanged source and candidate roles into a new 17-boundary listening
package.  It runs no model, selects nothing and publishes no product route.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_result_v2 import (
    RESULT_SCHEMA as V2_REVIEW_RESULT_SCHEMA,
    RESULT_STATUS as V2_REVIEW_RESULT_STATUS,
)
from ._separation_full_song_join_remediation_review_v2 import (
    POLICY_ID as V2_REVIEW_POLICY_ID,
    _FALSE_EFFECTS as V2_REVIEW_FALSE_EFFECTS,
    _load_review_inputs,
    _reverify_inputs,
    _source_bindings,
)
from ._separation_full_song_stitch import (
    REVIEW_NAME as ORIGINAL_REVIEW_NAME,
    REVIEW_SCHEMA as ORIGINAL_REVIEW_SCHEMA,
    _immutable_review,
    _make_private_tree,
    _write_boundary_review,
)


SCHEMA = "sunofriend.private-separation-candidate-full-song-review-package.v1"
STATUS = "unreviewed_candidate_bound_full_song_and_boundaries"
REPORT_NAME = "private-separation-candidate-full-song-review-package.json"
TARGET_SAMPLE_RATE = 44_100
_ROLES = ("source", "vocals", "instrumental", "reconstruction")
_CANDIDATE_ROLES = ("vocals", "instrumental", "reconstruction")
_FALSE_EFFECTS = {
    "candidate_accepted": False,
    "candidate_selected": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_audio_mutated": False,
    "source_graph_mutated": False,
}


def _build_private_candidate_full_song_review(
    v2_review_result_path: str | Path,
    *,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one no-overwrite review package after the targeted v2 pass."""

    import numpy as np
    import soundfile

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"private candidate full-song review already exists: {destination}"
        )
    _require_private_directory(
        destination.parent, "private candidate full-song review parent"
    )

    context = _load_review_inputs(
        v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    review_result_snapshot = _load_private_json_snapshot(
        v2_review_result_path, "private resolved v2 join review result"
    )
    _verify_passing_v2_review_result(review_result_snapshot, context=context)

    evidence_paths = (
        review_result_snapshot["path"],
        context["v2_snapshot"]["path"],
        context["v2_plan_snapshot"]["path"],
        context["stitch_snapshot"]["path"],
        context["v1_execution_snapshot"]["path"],
        context["v1_candidate_snapshot"]["path"],
        *context["authority_paths"],
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(
            context["v1_root"],
            context["v2_root"],
            context["stitch_root"],
            *(path.parent for path in evidence_paths),
        ),
        evidence_paths=evidence_paths,
    )

    boundary_evidence = _verified_original_boundary_evidence(context)
    boundaries = boundary_evidence["boundaries"]
    destination.mkdir(mode=0o700)
    try:
        sources = destination / "SOURCE"
        stems = destination / "STEMS"
        sources.mkdir(mode=0o700)
        stems.mkdir(mode=0o700)
        copied = _copy_review_audio(
            destination,
            context=context,
            soundfile=soundfile,
        )
        role_paths = {
            "source": sources / "source-44100.wav",
            **{role: stems / f"{role}.wav" for role in _CANDIDATE_ROLES},
        }
        boundary_review = _write_boundary_review(
            destination,
            title=f"{boundary_evidence['title']} — expanded-context candidate",
            boundaries=boundaries,
            role_paths=role_paths,
            soundfile=soundfile,
            np=np,
        )
        _require_review_result_unchanged(review_result_snapshot)
        if _verified_original_boundary_evidence(context) != boundary_evidence:
            raise ValueError("private original full-song boundaries changed")
        _reverify_inputs(context)
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "candidate_identity": "v2_expanded_context_join_remediation",
            "bindings": {
                "v2_review_result_sha256": review_result_snapshot["sha256"],
                "v2_review_result_document_sha256": review_result_snapshot[
                    "document"
                ]["document_sha256"],
                "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
                "v2_execution_document_sha256": context["v2_report"][
                    "document_sha256"
                ],
                "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
                "stitch_document_sha256": context["stitch"]["document_sha256"],
                "targeted_review_package_commitment": review_result_snapshot[
                    "document"
                ]["package_commitment"],
            },
            "clock": {
                **dict(context["stitch"]["clock"]),
                "boundary_count": len(boundaries),
            },
            "artifacts": copied,
            "boundary_review": boundary_review,
            "readiness": {
                "targeted_v2_absolute_cleanliness_pass": True,
                "candidate_full_song_review_package_complete": True,
                "new_candidate_full_song_review_complete": False,
                "new_candidate_alignment_complete": False,
                "original_audible_joins_resolved": False,
                "publication_ready": False,
            },
            "interpretation": {
                "targeted_pass_is_full_song_acceptance": False,
                "full_song_and_all_boundaries_require_fresh_human_review": True,
                "automatic_winner_selected": False,
                "separator_accepted": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {
                **dict(_FALSE_EFFECTS),
                "private_review_audio_copied": True,
            },
            "limitations": [
                "The package copies verified source and v2 candidate PCM24 audio; it runs no model.",
                "The targeted v2 pass did not establish full-song quality or alignment.",
                "A clean boundary does not establish separator accuracy.",
                "Completing this page cannot select, accept or publish a separator.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(destination / REPORT_NAME, document)
        _verify_completed_package(destination, document, soundfile=soundfile)
        _require_review_result_unchanged(review_result_snapshot)
        if _verified_original_boundary_evidence(context) != boundary_evidence:
            raise ValueError("private original full-song boundaries changed")
        _reverify_inputs(context)
        _make_private_tree(destination)
    except BaseException:
        # Preserve a failed fresh root for diagnosis, but never leave a
        # completion report claiming success.
        try:
            (destination / REPORT_NAME).unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "review_html": str(destination / boundary_review["html"]),
        "output_directory": str(destination),
    }


def _verify_passing_v2_review_result(
    snapshot: Mapping[str, Any], *, context: Mapping[str, Any]
) -> None:
    document = snapshot["document"]
    readiness = document.get("readiness_evidence")
    bindings = document.get("bindings")
    expected_bindings = _source_bindings(context)
    if (
        document.get("schema") != V2_REVIEW_RESULT_SCHEMA
        or document.get("status") != V2_REVIEW_RESULT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != V2_REVIEW_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != V2_REVIEW_FALSE_EFFECTS
        or not isinstance(bindings, Mapping)
        or any(bindings.get(key) != value for key, value in expected_bindings.items())
        or not isinstance(readiness, Mapping)
    ):
        raise ValueError("private resolved v2 join review result differs")
    required_true = (
        "targeted_v2_review_complete",
        "all_targeted_v2_boundary_versions_clean",
        "all_v2_patch_edges_clean",
        "targeted_v2_absolute_cleanliness_pass",
        "fresh_candidate_bound_full_song_review_eligible",
    )
    required_false = (
        "new_candidate_full_song_review_complete",
        "new_candidate_alignment_complete",
        "original_audible_joins_resolved",
        "publication_ready",
    )
    if any(readiness.get(key) is not True for key in required_true) or any(
        readiness.get(key) is not False for key in required_false
    ):
        raise ValueError("private resolved v2 join review did not pass")


def _require_review_result_unchanged(snapshot: Mapping[str, Any]) -> None:
    current = _load_private_json_snapshot(
        snapshot["path"], "private resolved v2 join review result"
    )
    if (
        current["sha256"] != snapshot["sha256"]
        or current["document"] != snapshot["document"]
    ):
        raise ValueError("private resolved v2 join review result changed")


def _verified_original_boundary_evidence(
    context: Mapping[str, Any],
) -> dict[str, Any]:
    stitch = context["stitch"]
    seed_path = context["stitch_root"] / "BOUNDARY-REVIEW" / ORIGINAL_REVIEW_NAME
    _require_private_regular(seed_path, "private original full-song review seed")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    claim = stitch["boundary_review"]
    if (
        seed.get("schema") != ORIGINAL_REVIEW_SCHEMA
        or seed.get("status") != "unreviewed"
        or _sha256(seed_path) != claim.get("seed_sha256")
        or seed.get("package_commitment") != claim.get("package_commitment")
        or seed.get("package_commitment")
        != hashlib.sha256(canonical_json_bytes(_immutable_review(seed))).hexdigest()
    ):
        raise ValueError("private original full-song review seed differs")
    units = seed.get("units")
    expected_count = int(stitch["clock"]["boundary_count"])
    if not isinstance(units, list) or len(units) != expected_count:
        raise ValueError("private original full-song boundary inventory differs")
    boundaries: list[int] = []
    for index, unit in enumerate(units, start=1):
        frame = unit.get("frame") if isinstance(unit, Mapping) else None
        if (
            unit.get("boundary_index") != index
            or not isinstance(frame, int)
            or isinstance(frame, bool)
            or frame <= 0
            or (boundaries and frame <= boundaries[-1])
        ):
            raise ValueError("private original full-song boundary order differs")
        boundaries.append(frame)
    title = seed.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 500:
        raise ValueError("private original full-song review title differs")
    return {"title": title, "boundaries": boundaries}


def _copy_review_audio(
    destination: Path,
    *,
    context: Mapping[str, Any],
    soundfile: Any,
) -> dict[str, Any]:
    total_frames = int(context["stitch"]["clock"]["frames"])
    source_record = context["stitch"]["artifacts"]["source"]
    source_path = context["stitch_root"] / source_record["path"]
    inputs = {
        "source": source_path,
        **{
            role: context["v2_root"] / context["v2_report"]["artifacts"][role]["path"]
            for role in _CANDIDATE_ROLES
        },
    }
    outputs = {
        "source": destination / "SOURCE/source-44100.wav",
        **{
            role: destination / f"STEMS/{role}.wav" for role in _CANDIDATE_ROLES
        },
    }
    claims: dict[str, Any] = {}
    for role in _ROLES:
        source = inputs[role]
        target = outputs[role]
        _require_private_regular(source, f"private candidate review {role} source")
        with source.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        target.chmod(0o600)
        expected = (
            source_record
            if role == "source"
            else context["v2_report"]["artifacts"][role]
        )
        observed = _read_pcm24_snapshot(
            target,
            expected,
            expected_frames=total_frames,
            label=f"private candidate review copied {role} audio",
        )
        info = soundfile.info(target)
        claims[role] = {
            "path": target.relative_to(destination).as_posix(),
            "sha256": observed["sha256"],
            "bytes": observed["bytes"],
            "geometry": {
                "sample_rate": int(info.samplerate),
                "channels": int(info.channels),
                "frames": int(info.frames),
                "sample_width_bytes": 3,
            },
            "pcm24_int32_sequence_sha256": observed[
                "pcm24_int32_sequence_sha256"
            ],
        }
    return claims


def _verify_completed_package(
    root: Path, document: Mapping[str, Any], *, soundfile: Any
) -> None:
    report = root / REPORT_NAME
    _require_private_regular(report, "private candidate full-song review report")
    if json.loads(report.read_text(encoding="utf-8")) != document:
        raise ValueError("private candidate full-song review report differs")
    expected_frames = int(document["clock"]["frames"])
    for role, record in document["artifacts"].items():
        path = root / record["path"]
        observed = _read_pcm24_snapshot(
            path,
            record,
            expected_frames=expected_frames,
            label=f"private completed candidate review {role} audio",
        )
        info = soundfile.info(path)
        if (
            int(info.samplerate) != TARGET_SAMPLE_RATE
            or int(info.channels) != 2
            or int(info.frames) != expected_frames
            or observed["pcm24_int32_sequence_sha256"]
            != record["pcm24_int32_sequence_sha256"]
        ):
            raise ValueError("private candidate full-song review audio differs")
    review_root = root / "BOUNDARY-REVIEW"
    for relative, expected in (
        (document["boundary_review"]["seed"], document["boundary_review"]["seed_sha256"]),
        (document["boundary_review"]["html"], document["boundary_review"]["html_sha256"]),
    ):
        path = root / relative
        _require_private_regular(path, "private candidate full-song review artifact")
        if _sha256(path) != expected:
            raise ValueError("private candidate full-song review artifact differs")
    _require_private_directory(review_root / "audio", "private candidate review audio")


__all__: tuple[str, ...] = ()
