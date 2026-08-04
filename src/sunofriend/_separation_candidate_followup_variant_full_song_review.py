"""Build fresh all-boundary reviews for every eligible remediation variant.

The targeted blind variant review may make zero, one or both variants eligible
for the next listening stage.  This module re-resolves that exact human export,
requires at least one eligible variant and creates one independent complete-song
and all-original-boundary package per eligible variant.  It never chooses
between eligible variants and never accepts or activates a separator.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_followup_full_song_review import (
    _verify_stitch_bound_to_v2,
)
from ._separation_candidate_followup_variant_review import (
    _FALSE_EFFECTS as VARIANT_REVIEW_FALSE_EFFECTS,
    _input_bindings,
    _load_verified_variant_inputs,
)
from ._separation_candidate_followup_variant_review_result import (
    RESULT_SCHEMA as VARIANT_RESULT_SCHEMA,
    RESULT_STATUS as VARIANT_RESULT_STATUS,
    _resolve_private_candidate_followup_variant_review,
)
from ._separation_candidate_full_song_review import (
    _verified_original_boundary_evidence,
)
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
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    _make_private_tree,
    _write_boundary_review,
)


SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "full-song-review-package.v1"
)
STATUS = "unreviewed_eligible_variants_bound_full_song_and_all_boundaries"
REPORT_NAME = (
    "private-separation-candidate-followup-variant-full-song-review-package.json"
)
TARGET_SAMPLE_RATE = 44_100
_ROLES = ("source", "vocals", "instrumental", "reconstruction")
_CANDIDATE_ROLES = ("vocals", "instrumental", "reconstruction")
_PACKAGE_EFFECTS = {
    "candidate_accepted": False,
    "candidate_selected": False,
    "model_run": False,
    "private_review_audio_copied": True,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_audio_mutated": False,
    "source_graph_mutated": False,
}
_PACKAGE_READINESS = {
    "variant_targeted_review_complete": True,
    "eligible_variant_full_song_reviews_complete": False,
    "eligible_variant_alignments_complete": False,
    "original_audible_joins_resolved": False,
    "publication_ready": False,
}
_LIMITATIONS = [
    "Every eligible variant receives a separate fresh complete-song and all-boundary review.",
    "The package runs no model and copies only verified private PCM24 evidence.",
    "Eligibility is not selection, acceptance, separator accuracy or publication readiness.",
    "A clean boundary does not prove source separation quality.",
    "Input JSON and WAV descriptors are not one atomic snapshot; keep every evidence tree quiescent.",
]


def _build_private_candidate_followup_variant_full_song_review(
    variant_review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Build one no-overwrite parent containing every eligible review."""

    import numpy as np
    import soundfile

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"private eligible-variant full-song review already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_private_directory(
        destination.parent, "private eligible-variant full-song review parent"
    )

    review_package = Path(variant_review_package_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    for path, label in (
        (review_package, "private follow-up variant review package"),
        (stitch_root, "private original stitch root"),
    ):
        _require_private_directory(path, label)

    context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=review_package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    eligible_ids = _eligible_variant_ids(result, context=context)

    stitch_snapshot = _load_private_json_snapshot(
        stitch_root / STITCH_REPORT_NAME, "private original stitch report"
    )
    stitch = _load_stitch_report(stitch_snapshot["path"])
    _verify_stitch_audio(stitch_root, stitch)
    _verify_stitch_bound_to_v2(stitch_snapshot, inputs=context["inputs"])
    boundary_evidence = _verified_original_boundary_evidence(
        {"stitch": stitch, "stitch_root": stitch_root}
    )
    result_snapshot = _load_private_json_snapshot(
        variant_review_result_path, "private follow-up variant review result"
    )
    reviewed_export = Path(reviewed_export_path).expanduser().absolute()
    evidence_paths = (
        result_snapshot["path"],
        reviewed_export,
        context["plan_snapshot"]["path"],
        context["execution_snapshot"]["path"],
        context["candidates_snapshot"]["path"],
        context["inputs"]["execution_snapshot"]["path"],
        context["inputs"]["candidate_snapshot"]["path"],
        context["inputs"]["v2_snapshot"]["path"],
        stitch_snapshot["path"],
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(
            context["base_root"],
            context["v2_root"],
            context["variant_root"],
            review_package,
            stitch_root,
        ),
        evidence_paths=evidence_paths,
    )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        variant_packages: list[dict[str, Any]] = []
        for index, variant_id in enumerate(eligible_ids, start=1):
            package_root = temporary / f"variant-{index:02d}"
            package_root.mkdir(mode=0o700)
            (package_root / "SOURCE").mkdir(mode=0o700)
            (package_root / "STEMS").mkdir(mode=0o700)
            artifacts = _copy_variant_review_audio(
                package_root,
                variant_id=variant_id,
                context=context,
                stitch=stitch,
                stitch_root=stitch_root,
                soundfile=soundfile,
            )
            role_paths = {
                "source": package_root / "SOURCE/source-44100.wav",
                **{
                    role: package_root / f"STEMS/{role}.wav"
                    for role in _CANDIDATE_ROLES
                },
            }
            boundary_review = _write_boundary_review(
                package_root,
                title=(
                    f"{boundary_evidence['title']} - eligible remediation "
                    f"variant {index} of {len(eligible_ids)}"
                ),
                boundaries=boundary_evidence["boundaries"],
                role_paths=role_paths,
                soundfile=soundfile,
                np=np,
            )
            _verify_variant_package(
                package_root,
                artifacts=artifacts,
                boundary_review=boundary_review,
                expected_frames=int(stitch["clock"]["frames"]),
                soundfile=soundfile,
            )
            variant_packages.append(
                {
                    "review_id": f"eligible-variant-{index:02d}",
                    "variant_id": variant_id,
                    "directory": package_root.relative_to(temporary).as_posix(),
                    "artifacts": artifacts,
                    "boundary_review": boundary_review,
                    "readiness": {
                        "eligible_for_fresh_all_boundary_review": True,
                        "complete_song_review_complete": False,
                        "all_original_boundaries_review_complete": False,
                        "alignment_complete": False,
                        "selected": False,
                        "accepted": False,
                    },
                }
            )

        _reverify_inputs(
            result=result,
            variant_review_result_path=variant_review_result_path,
            reviewed_export_path=reviewed_export_path,
            variant_review_package_dir=review_package,
            plan_path=plan_path,
            execution_dir=execution_dir,
            v2_execution_dir=v2_execution_dir,
            variant_execution_dir=variant_execution_dir,
            context=context,
            stitch_snapshot=stitch_snapshot,
            stitch_root=stitch_root,
            boundary_evidence=boundary_evidence,
        )
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "bindings": {
                **_input_bindings(context),
                "variant_review_result_sha256": result_snapshot["sha256"],
                "variant_review_result_document_sha256": result["document_sha256"],
                "variant_review_export_sha256": result["bindings"][
                    "review_export_sha256"
                ],
                "stitch_report_sha256": stitch_snapshot["sha256"],
                "stitch_document_sha256": stitch["document_sha256"],
            },
            "clock": {**dict(stitch["clock"]), "boundary_count": len(boundary_evidence["boundaries"])},
            "eligible_variant_ids": eligible_ids,
            "eligible_variant_count": len(eligible_ids),
            "required_review_count": len(eligible_ids),
            "variant_packages": variant_packages,
            "readiness": dict(_PACKAGE_READINESS),
            "interpretation": {
                "every_eligible_variant_included": True,
                "eligible_variants_may_be_multiple": True,
                "automatic_winner_selected": False,
                "separator_accepted": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_PACKAGE_EFFECTS),
            "limitations": list(_LIMITATIONS),
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(temporary / REPORT_NAME, document)
        _verify_parent_package(temporary, document, soundfile=soundfile)
        _make_private_tree(temporary)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "review_html": [
            str(destination / item["directory"] / item["boundary_review"]["html"])
            for item in variant_packages
        ],
        "output_directory": str(destination),
    }


def _verified_exact_variant_result(
    result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    variant_review_package_dir: Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
) -> dict[str, Any]:
    """Re-resolve the completed export and require byte-exact result semantics."""

    result_snapshot = _load_private_json_snapshot(
        result_path, "private follow-up variant review result"
    )
    with tempfile.TemporaryDirectory(prefix="sunofriend-variant-full-song-gate-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        derived_path = root / "resolved.json"
        derived = _resolve_private_candidate_followup_variant_review(
            reviewed_export_path,
            plan_path=plan_path,
            review_package_dir=variant_review_package_dir,
            execution_dir=execution_dir,
            v2_execution_dir=v2_execution_dir,
            variant_execution_dir=variant_execution_dir,
            out=derived_path,
        )
        derived.pop("report", None)
    document = result_snapshot["document"]
    if (
        document != derived
        or document.get("schema") != VARIANT_RESULT_SCHEMA
        or document.get("status") != VARIANT_RESULT_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != VARIANT_REVIEW_FALSE_EFFECTS
        or not isinstance(document.get("readiness_evidence"), Mapping)
    ):
        raise ValueError("private follow-up variant review result differs")
    return document


def _eligible_variant_ids(
    result: Mapping[str, Any], *, context: Mapping[str, Any]
) -> list[str]:
    known = [
        item["variant_id"]
        for item in context["plan"]["protocol"]["candidate_variants"]
    ]
    raw = result.get("fresh_all_boundary_review_eligible_variant_ids")
    readiness = result.get("readiness_evidence")
    gate = result.get("candidate_gate_evidence")
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) != len(set(raw))
        or any(not isinstance(item, str) or item not in known for item in raw)
        or not isinstance(readiness, Mapping)
        or readiness.get("variant_review_complete") is not True
        or readiness.get("one_or_more_variants_eligible_for_fresh_all_boundary_review")
        is not True
        or readiness.get("variant_selected") is not False
        or readiness.get("fresh_all_boundary_review_complete") is not False
        or readiness.get("alignment_complete") is not False
        or readiness.get("original_audible_joins_resolved") is not False
        or readiness.get("publication_ready") is not False
        or not isinstance(gate, Mapping)
    ):
        raise ValueError("no verified variant is eligible for fresh all-boundary review")
    ordered = [variant_id for variant_id in known if variant_id in raw]
    if len(ordered) != len(raw):
        raise ValueError("eligible variant inventory differs")
    for variant_id in known:
        evidence = gate.get(variant_id)
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("selected") is not False
            or evidence.get("eligible_for_fresh_all_boundary_review")
            != (variant_id in ordered)
        ):
            raise ValueError("eligible variant gate evidence differs")
    return ordered


def _copy_variant_review_audio(
    destination: Path,
    *,
    variant_id: str,
    context: Mapping[str, Any],
    stitch: Mapping[str, Any],
    stitch_root: Path,
    soundfile: Any,
) -> dict[str, Any]:
    total_frames = int(stitch["clock"]["frames"])
    source_record = stitch["artifacts"]["source"]
    variant_record = next(
        item for item in context["candidates"]["variants"] if item["variant_id"] == variant_id
    )
    source_paths = {
        "source": stitch_root / source_record["path"],
        **context["variant_paths"][variant_id],
    }
    target_paths = {
        "source": destination / "SOURCE/source-44100.wav",
        **{role: destination / f"STEMS/{role}.wav" for role in _CANDIDATE_ROLES},
    }
    claims: dict[str, Any] = {}
    for role in _ROLES:
        source = source_paths[role]
        target = target_paths[role]
        _require_private_regular(source, f"private eligible-variant review {role} source")
        with source.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        target.chmod(0o600)
        expected = source_record if role == "source" else variant_record["artifacts"][role]
        observed = _read_pcm24_snapshot(
            target,
            expected,
            expected_frames=total_frames,
            label=f"private eligible-variant copied {role} audio",
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
            "pcm24_int32_sequence_sha256": observed["pcm24_int32_sequence_sha256"],
        }
    return claims


def _verify_variant_package(
    root: Path,
    *,
    artifacts: Mapping[str, Any],
    boundary_review: Mapping[str, Any],
    expected_frames: int,
    soundfile: Any,
) -> None:
    for role, record in artifacts.items():
        path = root / record["path"]
        observed = _read_pcm24_snapshot(
            path,
            record,
            expected_frames=expected_frames,
            label=f"private completed eligible-variant {role} audio",
        )
        info = soundfile.info(path)
        if (
            int(info.samplerate) != TARGET_SAMPLE_RATE
            or int(info.channels) != 2
            or int(info.frames) != expected_frames
            or observed["pcm24_int32_sequence_sha256"]
            != record["pcm24_int32_sequence_sha256"]
        ):
            raise ValueError("private eligible-variant full-song audio differs")
    for key, hash_key in (("seed", "seed_sha256"), ("html", "html_sha256")):
        path = root / boundary_review[key]
        _require_private_regular(path, "private eligible-variant review artifact")
        if _sha256(path) != boundary_review[hash_key]:
            raise ValueError("private eligible-variant review artifact differs")
    _require_private_directory(
        root / "BOUNDARY-REVIEW/audio", "private eligible-variant boundary audio"
    )


def _verify_parent_package(
    root: Path, document: Mapping[str, Any], *, soundfile: Any
) -> None:
    report = root / REPORT_NAME
    _require_private_regular(report, "private eligible-variant full-song review report")
    if json.loads(report.read_text(encoding="utf-8")) != document:
        raise ValueError("private eligible-variant full-song review report differs")
    if len(document["variant_packages"]) != document["eligible_variant_count"]:
        raise ValueError("private eligible-variant package count differs")
    for item in document["variant_packages"]:
        _verify_variant_package(
            root / item["directory"],
            artifacts=item["artifacts"],
            boundary_review=item["boundary_review"],
            expected_frames=int(document["clock"]["frames"]),
            soundfile=soundfile,
        )


def _reverify_inputs(
    *,
    result: Mapping[str, Any],
    variant_review_result_path: str | Path,
    reviewed_export_path: str | Path,
    variant_review_package_dir: Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    context: Mapping[str, Any],
    stitch_snapshot: Mapping[str, Any],
    stitch_root: Path,
    boundary_evidence: Mapping[str, Any],
) -> None:
    current_result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=variant_review_package_dir,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    if current_result != result:
        raise ValueError("private follow-up variant review result changed")
    current_context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    if (
        _input_bindings(current_context) != _input_bindings(context)
        or current_context["candidates"] != context["candidates"]
    ):
        raise ValueError("private follow-up variant execution evidence changed")
    current_stitch = _load_private_json_snapshot(
        stitch_snapshot["path"], "private original stitch report"
    )
    if (
        current_stitch["sha256"] != stitch_snapshot["sha256"]
        or current_stitch["document"] != stitch_snapshot["document"]
    ):
        raise ValueError("private original stitch changed")
    _verify_stitch_audio(stitch_root, current_stitch["document"])
    if _verified_original_boundary_evidence(
        {"stitch": current_stitch["document"], "stitch_root": stitch_root}
    ) != boundary_evidence:
        raise ValueError("private original boundary inventory changed")


__all__: tuple[str, ...] = ()
