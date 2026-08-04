"""Build the gated full-song review for a verified follow-up candidate.

The preceding blind comparison covers only changed boundaries, patch edges and
three complete-song A/B pairs.  A passing result permits this module to copy
the exact follow-up candidate into a fresh, source-referenced review of every
original chunk boundary.  It does not select or accept the candidate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_full_song_review import (
    _verified_original_boundary_evidence,
)
from ._separation_candidate_join_remediation_review import (
    _FALSE_EFFECTS as TARGETED_REVIEW_FALSE_EFFECTS,
    _load_verified_inputs,
)
from ._separation_candidate_join_remediation_review_result import (
    RESULT_SCHEMA as TARGETED_RESULT_SCHEMA,
    RESULT_STATUS as TARGETED_RESULT_STATUS,
    _resolve_private_candidate_join_remediation_review,
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


SCHEMA = "sunofriend.private-separation-candidate-followup-full-song-review-package.v1"
STATUS = "unreviewed_followup_bound_full_song_and_all_boundaries"
REPORT_NAME = "private-separation-candidate-followup-full-song-review-package.json"
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
    "targeted_followup_listening_pass": True,
    "followup_full_song_review_package_complete": True,
    "followup_complete_song_review_complete": False,
    "followup_alignment_complete": False,
    "original_audible_joins_resolved": False,
    "publication_ready": False,
}
_PACKAGE_INTERPRETATION = {
    "targeted_pass_is_full_song_acceptance": False,
    "all_original_boundaries_require_fresh_human_review": True,
    "automatic_winner_selected": False,
    "separator_accepted": False,
}
_LIMITATIONS = [
    "The package copies verified source and follow-up candidate PCM24 audio; it runs no model.",
    "The targeted follow-up pass did not establish all-boundary quality or alignment.",
    "A clean boundary does not establish separator accuracy.",
    "Completing this page cannot select, accept or publish a separator.",
]


def _build_private_candidate_followup_full_song_review(
    targeted_review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    targeted_review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create a no-overwrite all-boundary package after an exact targeted pass."""

    import numpy as np
    import soundfile

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"private follow-up full-song review already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_private_directory(
        destination.parent, "private follow-up full-song review parent"
    )

    execution = Path(execution_dir).expanduser().absolute()
    v2_execution = Path(v2_execution_dir).expanduser().absolute()
    targeted_package = Path(targeted_review_package_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    for path, label in (
        (execution, "private follow-up execution root"),
        (v2_execution, "private v2 execution root"),
        (targeted_package, "private targeted follow-up review root"),
        (stitch_root, "private original stitch root"),
    ):
        _require_private_directory(path, label)

    inputs = _load_verified_inputs(execution, v2_execution)
    targeted_result = _verified_passing_targeted_result(
        targeted_review_result_path,
        reviewed_export_path=reviewed_export_path,
        targeted_review_package_dir=targeted_package,
        execution_dir=execution,
        v2_execution_dir=v2_execution,
    )
    stitch_snapshot = _load_private_json_snapshot(
        stitch_root / STITCH_REPORT_NAME, "private original stitch report"
    )
    stitch = _load_stitch_report(stitch_snapshot["path"])
    _verify_stitch_audio(stitch_root, stitch)
    _verify_stitch_bound_to_v2(stitch_snapshot, inputs=inputs)
    boundary_evidence = _verified_original_boundary_evidence(
        {"stitch": stitch, "stitch_root": stitch_root}
    )

    result_snapshot = _load_private_json_snapshot(
        targeted_review_result_path, "private targeted follow-up review result"
    )
    reviewed_export = Path(reviewed_export_path).expanduser().absolute()
    evidence_paths = (
        result_snapshot["path"],
        reviewed_export,
        inputs["execution_snapshot"]["path"],
        inputs["candidate_snapshot"]["path"],
        inputs["v2_snapshot"]["path"],
        stitch_snapshot["path"],
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(execution, v2_execution, targeted_package, stitch_root),
        evidence_paths=evidence_paths,
    )

    boundaries = boundary_evidence["boundaries"]
    destination.mkdir(mode=0o700)
    try:
        (destination / "SOURCE").mkdir(mode=0o700)
        (destination / "STEMS").mkdir(mode=0o700)
        artifacts = _copy_review_audio(
            destination,
            inputs=inputs,
            stitch=stitch,
            stitch_root=stitch_root,
            soundfile=soundfile,
        )
        role_paths = {
            "source": destination / "SOURCE/source-44100.wav",
            **{
                role: destination / f"STEMS/{role}.wav"
                for role in _CANDIDATE_ROLES
            },
        }
        boundary_review = _write_boundary_review(
            destination,
            title=f"{boundary_evidence['title']} - follow-up candidate",
            boundaries=boundaries,
            role_paths=role_paths,
            soundfile=soundfile,
            np=np,
        )
        _reverify_inputs(
            inputs=inputs,
            targeted_result=targeted_result,
            targeted_review_result_path=targeted_review_result_path,
            stitch_snapshot=stitch_snapshot,
            stitch_root=stitch_root,
            boundary_evidence=boundary_evidence,
        )
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "candidate_identity": "review_derived_followup_join_remediation",
            "bindings": {
                "targeted_review_result_sha256": result_snapshot["sha256"],
                "targeted_review_result_document_sha256": targeted_result[
                    "document_sha256"
                ],
                "targeted_review_export_sha256": targeted_result["bindings"][
                    "review_export_sha256"
                ],
                "followup_execution_report_sha256": inputs["execution_snapshot"][
                    "sha256"
                ],
                "followup_execution_document_sha256": inputs["execution"][
                    "document_sha256"
                ],
                "followup_candidate_report_sha256": inputs["candidate_snapshot"][
                    "sha256"
                ],
                "followup_candidate_document_sha256": inputs["candidate"][
                    "document_sha256"
                ],
                "v2_execution_report_sha256": inputs["v2_snapshot"]["sha256"],
                "v2_execution_document_sha256": inputs["v2"]["document_sha256"],
                "stitch_report_sha256": stitch_snapshot["sha256"],
                "stitch_document_sha256": stitch["document_sha256"],
            },
            "clock": {**dict(stitch["clock"]), "boundary_count": len(boundaries)},
            "artifacts": artifacts,
            "boundary_review": boundary_review,
            "readiness": dict(_PACKAGE_READINESS),
            "interpretation": dict(_PACKAGE_INTERPRETATION),
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_PACKAGE_EFFECTS),
            "limitations": list(_LIMITATIONS),
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(destination / REPORT_NAME, document)
        _verify_completed_package(destination, document, soundfile=soundfile)
        _reverify_inputs(
            inputs=inputs,
            targeted_result=targeted_result,
            targeted_review_result_path=targeted_review_result_path,
            stitch_snapshot=stitch_snapshot,
            stitch_root=stitch_root,
            boundary_evidence=boundary_evidence,
        )
        _make_private_tree(destination)
    except BaseException:
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


def _verified_passing_targeted_result(
    result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    targeted_review_package_dir: Path,
    execution_dir: Path,
    v2_execution_dir: Path,
) -> dict[str, Any]:
    """Re-resolve the completed blind export and require the targeted pass."""

    document = _verified_exact_targeted_result(
        result_path,
        reviewed_export_path=reviewed_export_path,
        targeted_review_package_dir=targeted_review_package_dir,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
    )
    readiness = document["readiness_evidence"]
    required_true = (
        "targeted_followup_review_complete",
        "all_targeted_boundaries_followup_preferred",
        "all_patch_edges_followup_or_equivalent",
        "all_complete_songs_followup_or_equivalent",
        "targeted_followup_listening_pass",
        "fresh_all_boundaries_review_eligible",
    )
    required_false = (
        "followup_complete_song_review_complete",
        "followup_alignment_complete",
        "original_audible_joins_resolved",
        "publication_ready",
    )
    if any(readiness.get(key) is not True for key in required_true) or any(
        readiness.get(key) is not False for key in required_false
    ):
        raise ValueError("private targeted follow-up review did not pass")
    return document


def _verified_exact_targeted_result(
    result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    targeted_review_package_dir: Path,
    execution_dir: Path,
    v2_execution_dir: Path,
) -> dict[str, Any]:
    """Re-resolve a completed blind export and require byte-exact semantics."""

    result_snapshot = _load_private_json_snapshot(
        result_path, "private targeted follow-up review result"
    )
    with tempfile.TemporaryDirectory(prefix="sunofriend-followup-gate-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        derived_path = root / "resolved.json"
        derived = _resolve_private_candidate_join_remediation_review(
            reviewed_export_path,
            review_package_dir=targeted_review_package_dir,
            execution_dir=execution_dir,
            v2_execution_dir=v2_execution_dir,
            out=derived_path,
        )
        derived.pop("report", None)
    document = result_snapshot["document"]
    if (
        document != derived
        or document.get("schema") != TARGETED_RESULT_SCHEMA
        or document.get("status") != TARGETED_RESULT_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != TARGETED_REVIEW_FALSE_EFFECTS
        or not isinstance(document.get("readiness_evidence"), Mapping)
    ):
        raise ValueError("private targeted follow-up review result differs")
    return document


def _verify_stitch_bound_to_v2(
    stitch_snapshot: Mapping[str, Any], *, inputs: Mapping[str, Any]
) -> None:
    stitch = stitch_snapshot["document"]
    v2 = inputs["v2"]
    bindings = v2.get("bindings")
    if (
        not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256") != stitch_snapshot["sha256"]
        or bindings.get("stitch_document_sha256") != stitch.get("document_sha256")
        or bindings.get("source_audio_sha256")
        != stitch.get("artifacts", {}).get("source", {}).get("sha256")
        or v2.get("clock") != stitch.get("clock")
    ):
        raise ValueError("private original stitch is not bound to v2 control")


def _copy_review_audio(
    destination: Path,
    *,
    inputs: Mapping[str, Any],
    stitch: Mapping[str, Any],
    stitch_root: Path,
    soundfile: Any,
) -> dict[str, Any]:
    total_frames = int(stitch["clock"]["frames"])
    source_record = stitch["artifacts"]["source"]
    source_paths = {
        "source": stitch_root / source_record["path"],
        **inputs["candidate_paths"],
    }
    target_paths = {
        "source": destination / "SOURCE/source-44100.wav",
        **{
            role: destination / f"STEMS/{role}.wav" for role in _CANDIDATE_ROLES
        },
    }
    claims: dict[str, Any] = {}
    for role in _ROLES:
        source = source_paths[role]
        target = target_paths[role]
        _require_private_regular(source, f"private follow-up review {role} source")
        with source.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        target.chmod(0o600)
        expected = (
            source_record if role == "source" else inputs["candidate"]["artifacts"][role]
        )
        observed = _read_pcm24_snapshot(
            target,
            expected,
            expected_frames=total_frames,
            label=f"private follow-up review copied {role} audio",
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
    _require_private_regular(report, "private follow-up full-song review report")
    if json.loads(report.read_text(encoding="utf-8")) != document:
        raise ValueError("private follow-up full-song review report differs")
    expected_frames = int(document["clock"]["frames"])
    for role, record in document["artifacts"].items():
        path = root / record["path"]
        observed = _read_pcm24_snapshot(
            path,
            record,
            expected_frames=expected_frames,
            label=f"private completed follow-up review {role} audio",
        )
        info = soundfile.info(path)
        if (
            int(info.samplerate) != TARGET_SAMPLE_RATE
            or int(info.channels) != 2
            or int(info.frames) != expected_frames
            or observed["pcm24_int32_sequence_sha256"]
            != record["pcm24_int32_sequence_sha256"]
        ):
            raise ValueError("private follow-up full-song review audio differs")
    for relative, expected in (
        (document["boundary_review"]["seed"], document["boundary_review"]["seed_sha256"]),
        (document["boundary_review"]["html"], document["boundary_review"]["html_sha256"]),
    ):
        path = root / relative
        _require_private_regular(path, "private follow-up full-song review artifact")
        if _sha256(path) != expected:
            raise ValueError("private follow-up full-song review artifact differs")
    _require_private_directory(
        root / "BOUNDARY-REVIEW/audio", "private follow-up review audio"
    )


def _reverify_inputs(
    *,
    inputs: Mapping[str, Any],
    targeted_result: Mapping[str, Any],
    targeted_review_result_path: str | Path,
    stitch_snapshot: Mapping[str, Any],
    stitch_root: Path,
    boundary_evidence: Mapping[str, Any],
) -> None:
    for key, label in (
        ("execution_snapshot", "private follow-up execution"),
        ("candidate_snapshot", "private follow-up candidate"),
        ("v2_snapshot", "private v2 execution"),
    ):
        current = _load_private_json_snapshot(inputs[key]["path"], label)
        if current["sha256"] != inputs[key]["sha256"] or current["document"] != inputs[key]["document"]:
            raise ValueError(f"{label} changed")
    current_result = _load_private_json_snapshot(
        targeted_review_result_path, "private targeted follow-up review result"
    )
    if current_result["document"] != targeted_result:
        raise ValueError("private targeted follow-up review result changed")
    current_stitch = _load_private_json_snapshot(
        stitch_snapshot["path"], "private original stitch report"
    )
    if current_stitch["sha256"] != stitch_snapshot["sha256"] or current_stitch["document"] != stitch_snapshot["document"]:
        raise ValueError("private original stitch changed")
    _verify_stitch_audio(stitch_root, current_stitch["document"])
    if _verified_original_boundary_evidence(
        {"stitch": current_stitch["document"], "stitch_root": stitch_root}
    ) != boundary_evidence:
        raise ValueError("private original boundary inventory changed")


__all__: tuple[str, ...] = ()
