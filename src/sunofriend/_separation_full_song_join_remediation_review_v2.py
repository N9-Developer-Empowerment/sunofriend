"""Create a sealed blind review for the model-free v2 join candidate.

This private-development package compares only the two human-equivalent v1
boundary-role candidates with their expanded-context v2 replacements.  It also
creates one unchanged v2 PCM24 clip for each patch edge.  The package contains
no complete-song review, cannot select either candidate, and cannot alter a
publication-readiness gate.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME as V1_CANDIDATE_REPORT_NAME,
    REPORT_NAME as V1_EXECUTION_REPORT_NAME,
    SCHEMA as V1_EXECUTION_SCHEMA,
    STATUS_COMPLETE as V1_EXECUTION_STATUS,
    _FALSE_PERMISSIONS,
    _state_sha256,
    _verify_candidate_report as _verify_v1_candidate_report,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    REPORT_NAME as V2_EXECUTION_REPORT_NAME,
    SCHEMA as V2_EXECUTION_SCHEMA,
    STATUS as V2_EXECUTION_STATUS,
    _EFFECTS as V2_EXECUTION_EFFECTS,
    _REPORT_KEYS as V2_EXECUTION_REPORT_KEYS,
    _bind_output_parent,
    _load_execution_inputs,
    _open_directory_at,
    _read_pcm24_at,
    _read_pcm24_snapshot,
    _rename_directory_exclusive_at,
    _require_execution_geometry,
    _require_plan_identity,
    _require_plan_rederivation,
    _reverify_input_audio,
    _verify_published_candidate,
    _write_pcm24_exclusive,
)
from ._separation_full_song_join_remediation_plan_v2 import (
    PATCH_DURATION_FRAMES,
    PATCH_HALF_FRAMES,
    POLICY_ID as V2_PLAN_POLICY_ID,
    TARGET_SAMPLE_RATE,
    _private_child_regular,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME


SCHEMA = "sunofriend.private-separation-full-song-join-remediation-review.v2"
STATUS = "unreviewed"
POLICY_ID = "blind-v1-versus-v2-expanded-context-cleanliness-v2"
REPORT_NAME = "private-separation-full-song-join-remediation-review-v2.json"
HTML_NAME = "join_remediation_review_v2.html"
ANSWER_KEY_NAME = "private-separation-full-song-join-remediation-answer-key-v2.json"
AUDIO_DIRECTORY = "audio"
_BOUNDARY_KIND = "boundary_candidate_pair"
_EDGE_KIND = "v2_patch_edge"
_ABSOLUTE_CHOICES = ("clean", "audible_join", "cannot_tell")
_COMPARATIVE_CHOICES = ("A", "B", "equivalent", "neither", "cannot_tell")
_ROLES = ("vocals", "instrumental")
_FULL_SONG_ROLES = (*_ROLES, "reconstruction")
_PAIR_HALF_FRAMES = 2 * TARGET_SAMPLE_RATE
_EDGE_HALF_FRAMES = TARGET_SAMPLE_RATE
_MINIMUM_REVIEW_RMS = 10 ** (-60 / 20)
_FALSE_EFFECTS = {
    "candidate_audio_mutated": False,
    "candidate_audio_selected": False,
    "preference_inferred": False,
    "publication_state_mutated": False,
    "readiness_gate_closed": False,
    "review_evidence_resolved": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _prepare_private_join_remediation_review_v2(
    v2_execution_dir: str | Path,
    *,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create a fresh owner-only targeted v1-versus-v2 listening package."""

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
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"private v2 join review exists: {destination}")
    evidence_roots = (
        context["v1_root"],
        context["v2_root"],
        context["stitch_root"],
        context["v2_plan_snapshot"]["path"].parent,
        *(path.parent for path in context["authority_paths"]),
    )
    evidence_paths = (
        context["v2_plan_snapshot"]["path"],
        context["stitch_snapshot"]["path"],
        context["v1_execution_snapshot"]["path"],
        context["v1_candidate_snapshot"]["path"],
        context["v2_snapshot"]["path"],
        *context["authority_paths"],
        *(
            audio["path"]
            for audio in context["execution_inputs"]["worker_audio"].values()
        ),
        *(
            audio["path"]
            for identity in ("v1_audio", "v2_audio")
            for audio in context[identity].values()
        ),
    )
    parent_descriptor = _bind_output_parent(
        destination,
        evidence_roots=evidence_roots,
        evidence_paths=evidence_paths,
    )

    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=".sunofriend-v2-join-review-building-"))
        staging.chmod(0o700)
        audio_root = staging / AUDIO_DIRECTORY
        audio_root.mkdir(mode=0o700)
        public_units: list[dict[str, Any]] = []
        boundary_answers: list[dict[str, Any]] = []

        windows = context["v2_report"]["windows"]
        for window in windows:
            unit, answer = _boundary_pair_unit(
                window,
                context=context,
                audio_root=audio_root,
                package_root=staging,
            )
            public_units.append(unit)
            boundary_answers.append(answer)
        for window in windows:
            for edge_name in ("start", "end"):
                public_units.append(
                    _edge_unit(
                        window,
                        edge_name=edge_name,
                        context=context,
                        audio_root=audio_root,
                        package_root=staging,
                    )
                )

        expected_counts = {
            "boundary_comparison_units": 2,
            "v2_patch_edge_units": 4,
            "total_units": 6,
            "anonymous_boundary_audio_clips": 4,
            "v2_edge_audio_clips": 4,
            "total_audio_references": 8,
        }
        if (
            len(public_units) != expected_counts["total_units"]
            or len(boundary_answers) != expected_counts["boundary_comparison_units"]
        ):
            raise ValueError("private v2 join review unit count differs")

        audio_manifest = {
            "schema": (
                "sunofriend.private-separation-full-song-join-remediation-audio.v2"
            ),
            "units": [
                {"unit_id": unit["unit_id"], "audio": unit["audio"]}
                for unit in public_units
            ],
        }
        audio_manifest_sha256 = hashlib.sha256(
            canonical_json_bytes(audio_manifest)
        ).hexdigest()
        source_bindings = _source_bindings(context)
        source_bindings_commitment = hashlib.sha256(
            canonical_json_bytes(source_bindings)
        ).hexdigest()
        answer_key: dict[str, Any] = {
            "schema": (
                "sunofriend.private-separation-full-song-join-remediation-answer-key.v2"
            ),
            "status": "sealed_do_not_open_before_review",
            "nonce": secrets.token_hex(32),
            "bindings": {
                **source_bindings,
                "source_bindings_commitment": source_bindings_commitment,
                "audio_manifest_sha256": audio_manifest_sha256,
            },
            "boundary_assignments": boundary_answers,
            "permissions": dict(_FALSE_PERMISSIONS),
        }
        answer_key["document_sha256"] = _document_sha256(answer_key)
        _write_json_exclusive(staging / ANSWER_KEY_NAME, answer_key)
        answer_key_sha256 = _sha256(staging / ANSWER_KEY_NAME)
        commitment = hashlib.sha256(
            (
                f"{answer_key_sha256}:{answer_key['document_sha256']}:"
                f"{audio_manifest_sha256}"
            ).encode("ascii")
        ).hexdigest()

        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "policy_id": POLICY_ID,
            "package_commitment": commitment,
            "question": (
                "Does the expanded-context candidate produce clean target joins "
                "and clean patch edges compared with the preserved candidate?"
            ),
            "instructions": [
                "For each anonymous boundary comparison, hear A and B before deciding.",
                "Rate A and B independently as clean, audible join or cannot tell.",
                "Then record which is preferable; equivalent, neither and cannot tell are valid.",
                "Finally hear each expanded-candidate patch edge and rate its absolute cleanliness.",
                "This review does not select, accept or publish either candidate.",
                "Do not open the separate answer key before exporting the completed review.",
            ],
            "bindings": {
                "source_bindings_commitment": source_bindings_commitment,
                "audio_manifest_sha256": audio_manifest_sha256,
                "answer_key_sha256": answer_key_sha256,
                "answer_key_document_sha256": answer_key["document_sha256"],
            },
            "expected_counts": expected_counts,
            "units": public_units,
            "summary": {
                "reviewed_units": 0,
                "total_units": len(public_units),
                "complete": False,
            },
            "readiness": {
                "targeted_v2_review_complete": False,
                "new_candidate_full_song_review_complete": False,
                "new_candidate_alignment_complete": False,
                "original_audible_joins_resolved": False,
                "publication_ready": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_FALSE_EFFECTS),
            "limitations": [
                "Boundary-pair sample-RMS matching only attenuates the louder clip and is not LUFS matching.",
                "Single patch-edge clips preserve the exact v2 PCM24 samples and receive no level processing.",
                "This targeted package contains no complete-song review and no alignment evidence.",
                "Absolute cleanliness and comparative preference are separate human judgements.",
                "A completed review cannot select, accept or publish a separator.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(staging / REPORT_NAME, document)
        _write_text_exclusive(staging / HTML_NAME, _review_html(document))
        _verify_staged_package(staging, document, answer_key, context=context)
        publication_claims = _publication_claims(staging, document)

        _reverify_inputs(context)
        _publish_package_no_overwrite(
            staging,
            destination,
            document=document,
            answer_key=answer_key,
            claims=publication_claims,
            context=context,
            parent_descriptor=parent_descriptor,
        )
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        _close_best_effort(parent_descriptor)

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "review_html": str(destination / HTML_NAME),
        "output_directory": str(destination),
    }


def _load_review_inputs(
    v2_execution_dir: str | Path,
    *,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
) -> dict[str, Any]:
    v1_root = Path(v1_execution_dir).expanduser().absolute()
    v2_root = Path(v2_execution_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    for path, label in (
        (v1_root, "private v1 remediation execution root"),
        (v2_root, "private v2 remediation execution root"),
        (stitch_root, "private stitch package"),
    ):
        _require_private_directory(path, label)

    v2_plan_snapshot = _load_private_json_snapshot(
        v2_plan_path, "private v2 join-remediation plan"
    )
    _require_plan_identity(v2_plan_snapshot)
    v2_plan = v2_plan_snapshot["document"]

    v1_execution_path = v1_root / V1_EXECUTION_REPORT_NAME
    v1_candidate_path = v1_root / V1_CANDIDATE_REPORT_NAME
    authority_arguments = {
        "package_dir": stitch_root,
        "full_song_review_result_path": Path(full_song_review_result_path)
        .expanduser()
        .absolute(),
        "v1_plan_path": Path(v1_plan_path).expanduser().absolute(),
        "v1_execution_report_path": v1_execution_path,
        "v1_candidate_report_path": v1_candidate_path,
        "resolved_join_review_result_path": Path(resolved_join_review_result_path)
        .expanduser()
        .absolute(),
        "publication_readiness_path": Path(publication_readiness_path)
        .expanduser()
        .absolute(),
    }
    _require_plan_rederivation(v2_plan, **authority_arguments)
    execution_inputs = _load_execution_inputs(
        v2_plan,
        package_dir=stitch_root,
        v1_plan_path=authority_arguments["v1_plan_path"],
        v1_execution_report_path=v1_execution_path,
        v1_candidate_report_path=v1_candidate_path,
    )
    _require_execution_geometry(v2_plan, execution_inputs)

    stitch_path = stitch_root / STITCH_REPORT_NAME
    stitch_snapshot = _load_private_json_snapshot(
        stitch_path, "private full-song stitch report"
    )
    stitch = _load_stitch_report(stitch_path)
    if stitch != stitch_snapshot["document"]:
        raise ValueError("private full-song stitch report changed")
    _verify_stitch_audio(stitch_root, stitch)

    v1_execution_snapshot = _load_private_json_snapshot(
        v1_execution_path, "private v1 remediation execution"
    )
    v1_state = v1_execution_snapshot["document"]
    if (
        v1_state.get("schema") != V1_EXECUTION_SCHEMA
        or v1_state.get("status") != V1_EXECUTION_STATUS
        or v1_state.get("state_sha256") != _state_sha256(v1_state)
        or v1_state.get("permissions") != _FALSE_PERMISSIONS
        or v1_state.get("summary", {}).get("candidate_audio_complete") is not True
        or v1_state.get("summary", {}).get("human_candidate_review_complete")
        is not False
    ):
        raise ValueError("private v1 remediation execution is not review-ready")
    v1_candidate = _verify_v1_candidate_report(v1_root, v1_state, stitch=stitch)
    v1_candidate_snapshot = _load_private_json_snapshot(
        v1_candidate_path, "private v1 remediation candidate"
    )
    if v1_candidate_snapshot["document"] != v1_candidate:
        raise ValueError("private v1 remediation candidate changed")

    v2_execution_path = v2_root / V2_EXECUTION_REPORT_NAME
    v2_snapshot = _load_private_json_snapshot(
        v2_execution_path, "private v2 remediation execution"
    )
    v2_report = v2_snapshot["document"]
    _verify_v2_report(
        v2_report,
        stitch=stitch,
        stitch_snapshot=stitch_snapshot,
        v1_state=v1_state,
        v1_execution_snapshot=v1_execution_snapshot,
        v1_candidate=v1_candidate,
        v1_candidate_snapshot=v1_candidate_snapshot,
        v2_plan=v2_plan,
        v2_plan_snapshot=v2_plan_snapshot,
    )
    _verify_published_candidate(v2_root, v2_report, inputs=execution_inputs)

    total_frames = int(stitch["clock"]["frames"])
    v1_audio: dict[str, dict[str, Any]] = {}
    v2_audio: dict[str, dict[str, Any]] = {}
    for role in _ROLES:
        v1_path = _private_child_regular(
            v1_root,
            v1_candidate["artifacts"][role]["path"],
            f"private v1 {role} candidate audio",
        )
        v1_audio[role] = _read_pcm24_snapshot(
            v1_path,
            v1_candidate["artifacts"][role],
            expected_frames=total_frames,
            label=f"private v1 {role} candidate audio",
        )
        v1_audio[role]["path"] = v1_path

        v2_path = _private_child_regular(
            v2_root,
            v2_report["artifacts"][role]["path"],
            f"private v2 {role} candidate audio",
        )
        v2_audio[role] = _read_pcm24_snapshot(
            v2_path,
            v2_report["artifacts"][role],
            expected_frames=total_frames,
            label=f"private v2 {role} candidate audio",
        )
        v2_audio[role]["path"] = v2_path

    return {
        "v1_root": v1_root,
        "v2_root": v2_root,
        "stitch_root": stitch_root,
        "stitch": stitch,
        "v2_plan_snapshot": v2_plan_snapshot,
        "v2_plan": v2_plan,
        "stitch_snapshot": stitch_snapshot,
        "v1_execution_snapshot": v1_execution_snapshot,
        "v1_state": v1_state,
        "v1_candidate_snapshot": v1_candidate_snapshot,
        "v1_candidate": v1_candidate,
        "v2_snapshot": v2_snapshot,
        "v2_report": v2_report,
        "authority_arguments": authority_arguments,
        "authority_paths": tuple(
            path for name, path in authority_arguments.items() if name != "package_dir"
        ),
        "execution_inputs": execution_inputs,
        "v1_audio": v1_audio,
        "v2_audio": v2_audio,
    }


def _verify_v2_report(
    report: Mapping[str, Any],
    *,
    stitch: Mapping[str, Any],
    stitch_snapshot: Mapping[str, Any],
    v1_state: Mapping[str, Any],
    v1_execution_snapshot: Mapping[str, Any],
    v1_candidate: Mapping[str, Any],
    v1_candidate_snapshot: Mapping[str, Any],
    v2_plan: Mapping[str, Any],
    v2_plan_snapshot: Mapping[str, Any],
) -> None:
    bindings = report.get("bindings")
    windows = report.get("windows")
    readiness = report.get("readiness")
    summary = report.get("summary")
    if (
        set(report) != V2_EXECUTION_REPORT_KEYS
        or report.get("schema") != V2_EXECUTION_SCHEMA
        or report.get("status") != V2_EXECUTION_STATUS
        or report.get("evidence_scope") != "private_development_only"
        or report.get("policy_id") != V2_PLAN_POLICY_ID
        or report.get("document_sha256") != _document_sha256(report)
        or report.get("permissions") != _FALSE_PERMISSIONS
        or report.get("effects") != V2_EXECUTION_EFFECTS
        or report.get("clock") != stitch["clock"]
        or not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256") != stitch_snapshot["sha256"]
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("v1_execution_report_sha256") != v1_execution_snapshot["sha256"]
        or bindings.get("v1_execution_state_sha256") != v1_state["state_sha256"]
        or bindings.get("v1_candidate_report_sha256") != v1_candidate_snapshot["sha256"]
        or bindings.get("v1_candidate_document_sha256")
        != v1_candidate["document_sha256"]
        or bindings.get("v2_plan_sha256") != v2_plan_snapshot["sha256"]
        or bindings.get("v2_plan_document_sha256") != v2_plan["document_sha256"]
        or not isinstance(v2_plan.get("protocol"), Mapping)
        or report.get("protocol") != v2_plan.get("protocol")
        or not isinstance(windows, list)
        or len(windows) != 2
        or len(v2_plan.get("windows", [])) != 2
        or not isinstance(summary, Mapping)
        or summary.get("targeted_boundary_role_pair_count") != 2
        or summary.get("executed_model_call_count") != 0
        or summary.get("v1_candidate_is_assembly_base") is not True
        or not isinstance(readiness, Mapping)
        or set(readiness)
        != {
            "v2_candidate_audio_complete",
            "v2_candidate_integrity_verified",
            "v2_candidate_review_complete",
            "new_candidate_full_song_review_complete",
            "new_candidate_alignment_complete",
            "original_audible_joins_resolved",
            "publication_ready",
        }
        or readiness.get("v2_candidate_audio_complete") is not True
        or readiness.get("v2_candidate_integrity_verified") is not True
        or readiness.get("v2_candidate_review_complete") is not False
        or readiness.get("new_candidate_full_song_review_complete") is not False
        or readiness.get("new_candidate_alignment_complete") is not False
        or readiness.get("original_audible_joins_resolved") is not False
        or readiness.get("publication_ready") is not False
        or set(report.get("artifacts", {})) != set(_FULL_SONG_ROLES)
    ):
        raise ValueError("private v2 remediation execution is not review-ready")

    plan_windows: dict[tuple[int, str], Mapping[str, Any]] = {}
    for planned in v2_plan["windows"]:
        if not isinstance(planned, Mapping):
            raise ValueError("private v2 remediation plan window differs")
        key = (
            _exact_int(planned.get("boundary_index"), "planned boundary index"),
            str(planned.get("patch_target_role")),
        )
        if key[1] not in _ROLES or key in plan_windows:
            raise ValueError("private v2 remediation plan window differs")
        plan_windows[key] = planned

    seen: set[tuple[int, str]] = set()
    for window in windows:
        if not isinstance(window, Mapping):
            raise ValueError("private v2 remediation review window differs")
        if set(window) != {
            "window_index",
            "boundary_index",
            "role",
            "source_start_frame",
            "source_end_frame",
            "patch_start_frame",
            "patch_end_frame",
            "worker_local_patch_start_frame",
            "worker_local_patch_end_frame",
            "edge_blend_frames",
            "v1_worker_output_sha256",
            "changed_pcm24_sample_values",
            "interior_pcm24_samples_match_worker",
            "outside_target_pcm24_samples_match_v1_candidate",
            "model_run",
        }:
            raise ValueError("private v2 remediation review window differs")
        boundary_index = _exact_int(window.get("boundary_index"), "boundary index")
        role = window.get("role")
        patch_start = _exact_int(window.get("patch_start_frame"), "patch start")
        patch_end = _exact_int(window.get("patch_end_frame"), "patch end")
        edge_blend = _exact_int(window.get("edge_blend_frames"), "edge blend")
        changed_values = _exact_int(
            window.get("changed_pcm24_sample_values"), "changed sample count"
        )
        boundary_frame = (patch_start + patch_end) // 2
        key = (boundary_index, str(role))
        planned = plan_windows.get(key)
        if (
            role not in _ROLES
            or key in seen
            or planned is None
            or planned.get("boundary_frame") != boundary_frame
            or patch_end - patch_start != PATCH_DURATION_FRAMES
            or patch_start != boundary_frame - PATCH_HALF_FRAMES
            or patch_end != boundary_frame + PATCH_HALF_FRAMES
            or edge_blend != 4_410
            or window.get("interior_pcm24_samples_match_worker") is not True
            or window.get("outside_target_pcm24_samples_match_v1_candidate") is not True
            or window.get("model_run") is not False
            or changed_values < 1
            or window.get("window_index") != planned.get("window_index")
            or window.get("source_start_frame") != planned.get("source_start_frame")
            or window.get("source_end_frame") != planned.get("source_end_frame")
            or patch_start != planned.get("patch_start_frame")
            or patch_end != planned.get("patch_end_frame")
            or window.get("worker_local_patch_start_frame")
            != planned.get("worker_local_patch_start_frame")
            or window.get("worker_local_patch_end_frame")
            != planned.get("worker_local_patch_end_frame")
            or window.get("v1_worker_output_sha256")
            != planned.get("v1_worker_output_sha256")
            or edge_blend != v2_plan["protocol"].get("edge_blend_frames")
        ):
            raise ValueError("private v2 remediation review window differs")
        seen.add(key)
    if seen != set(plan_windows):
        raise ValueError("private v2 remediation plan-to-execution window set differs")


def _boundary_pair_unit(
    window: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    audio_root: Path,
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np

    boundary_index = int(window["boundary_index"])
    role = str(window["role"])
    centre = (int(window["patch_start_frame"]) + int(window["patch_end_frame"])) // 2
    start = centre - _PAIR_HALF_FRAMES
    end = centre + _PAIR_HALF_FRAMES
    if start != window["patch_start_frame"] or end != window["patch_end_frame"]:
        raise ValueError("private v2 boundary review window differs")
    sources = {
        "v1_candidate": context["v1_audio"][role]["samples"][start:end],
        "v2_candidate": context["v2_audio"][role]["samples"][start:end],
    }
    floats = {
        identity: samples.astype("float64") / 2_147_483_648.0
        for identity, samples in sources.items()
    }
    rms = {identity: _sample_rms(value, np=np) for identity, value in floats.items()}
    target_rms = min(rms.values())
    if target_rms <= _MINIMUM_REVIEW_RMS:
        raise ValueError("private v2 boundary review clip is too quiet")
    gains = {identity: target_rms / rms[identity] for identity in floats}
    assignment = _assignment()
    unit_id = f"target-boundary-{boundary_index:02d}-{role}"
    audio: dict[str, Any] = {}
    rendered_hashes: dict[str, str] = {}
    for slot in ("A", "B"):
        identity = assignment[slot]
        path = audio_root / f"{unit_id}-{slot}.wav"
        _write_pcm24_exclusive(path, floats[identity] * gains[identity])
        observed = _read_pcm24_snapshot(
            path,
            None,
            expected_frames=end - start,
            label=f"private v2 boundary review {slot}",
        )
        rendered_hashes[slot] = observed["pcm24_int32_sequence_sha256"]
        audio[slot] = _audio_record(path, root=package_root, observed=observed)
    if rendered_hashes["A"] == rendered_hashes["B"]:
        raise ValueError("private v2 boundary review pair is PCM24-identical")

    public = {
        "unit_id": unit_id,
        "kind": _BOUNDARY_KIND,
        "title": f"Boundary {boundary_index}: {role}",
        "focus": (
            "Rate each version independently for an audible join, then compare "
            f"which better preserves the musical continuity of the {role}."
        ),
        "source_window": _source_window(start, end),
        "level_policy": "attenuate-louder-to-quieter-whole-window-sample-rms-v2",
        "audio": audio,
        "heard": {"A": False, "B": False},
        "absolute_cleanliness": {"A": None, "B": None},
        "comparative_choice": None,
        "notes": "",
    }
    answer = {
        "unit_id": unit_id,
        "assignment": assignment,
        "v1_candidate_gain": round(gains["v1_candidate"], 12),
        "v2_candidate_gain": round(gains["v2_candidate"], 12),
        "v1_candidate_rms": round(rms["v1_candidate"], 12),
        "v2_candidate_rms": round(rms["v2_candidate"], 12),
    }
    return public, answer


def _edge_unit(
    window: Mapping[str, Any],
    *,
    edge_name: str,
    context: Mapping[str, Any],
    audio_root: Path,
    package_root: Path,
) -> dict[str, Any]:
    import numpy as np

    if edge_name not in {"start", "end"}:
        raise ValueError("private v2 patch-edge name differs")
    boundary_index = int(window["boundary_index"])
    role = str(window["role"])
    centre = int(window[f"patch_{edge_name}_frame"])
    start = centre - _EDGE_HALF_FRAMES
    end = centre + _EDGE_HALF_FRAMES
    source = context["v2_audio"][role]["samples"][start:end]
    if source.shape != (2 * _EDGE_HALF_FRAMES, 2):
        raise ValueError("private v2 patch-edge review window differs")
    if (
        _sample_rms(source.astype("float64") / 2_147_483_648.0, np=np)
        <= _MINIMUM_REVIEW_RMS
    ):
        raise ValueError("private v2 patch-edge review clip is too quiet")
    unit_id = f"v2-edge-boundary-{boundary_index:02d}-{role}-{edge_name}"
    path = audio_root / f"{unit_id}.wav"
    _write_pcm24_exclusive(path, source.astype("float64") / 2_147_483_648.0)
    observed = _read_pcm24_snapshot(
        path,
        None,
        expected_frames=end - start,
        label="private v2 patch-edge review audio",
    )
    if not bool(np.array_equal(observed["samples"], source)):
        raise ValueError("private v2 patch-edge PCM24 samples differ")
    return {
        "unit_id": unit_id,
        "kind": _EDGE_KIND,
        "title": f"Boundary {boundary_index}: {role} expanded patch {edge_name} edge",
        "focus": (
            "Is this edge clean? Listen for a click, level jump, cut-off sound "
            "or sudden tone change."
        ),
        "source_window": _source_window(start, end),
        "level_policy": "unchanged-v2-pcm24-window-no-level-processing",
        "audio": {"clip": _audio_record(path, root=package_root, observed=observed)},
        "heard": False,
        "absolute_cleanliness": None,
        "notes": "",
    }


def _assignment() -> dict[str, str]:
    if secrets.randbelow(2):
        return {"A": "v1_candidate", "B": "v2_candidate"}
    return {"A": "v2_candidate", "B": "v1_candidate"}


def _source_bindings(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
        "stitch_document_sha256": context["stitch"]["document_sha256"],
        "v1_execution_report_sha256": context["v1_execution_snapshot"]["sha256"],
        "v1_execution_state_sha256": context["v1_state"]["state_sha256"],
        "v1_candidate_report_sha256": context["v1_candidate_snapshot"]["sha256"],
        "v1_candidate_document_sha256": context["v1_candidate"]["document_sha256"],
        "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
        "v2_execution_document_sha256": context["v2_report"]["document_sha256"],
        "v2_plan_sha256": context["v2_plan_snapshot"]["sha256"],
        "v2_plan_document_sha256": context["v2_plan"]["document_sha256"],
    }


def _sample_rms(value: Any, *, np: Any) -> float:
    result = float(np.sqrt(np.mean(np.square(value, dtype="float64"))))
    if not math.isfinite(result) or result <= 0:
        raise ValueError("private v2 join review RMS differs")
    return result


def _source_window(start: int, end: int) -> dict[str, Any]:
    return {
        "start_frame": start,
        "end_frame": end,
        "start_seconds": start / TARGET_SAMPLE_RATE,
        "end_seconds": end / TARGET_SAMPLE_RATE,
    }


def _audio_record(
    path: Path, *, root: Path, observed: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": observed["sha256"],
        "bytes": observed["bytes"],
        "geometry": {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 2,
            "sample_width_bytes": 3,
            "frames": len(observed["samples"]),
        },
        "pcm24_int32_sequence_sha256": observed["pcm24_int32_sequence_sha256"],
    }


def _verify_staged_package(
    root: Path,
    document: Mapping[str, Any],
    answer_key: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
) -> None:
    _require_private_directory(root, "private v2 review staging root")
    _require_private_directory(root / AUDIO_DIRECTORY, "private v2 review audio root")
    if (
        json.loads((root / REPORT_NAME).read_text(encoding="utf-8")) != document
        or json.loads((root / ANSWER_KEY_NAME).read_text(encoding="utf-8"))
        != answer_key
        or document.get("document_sha256") != _document_sha256(document)
        or answer_key.get("document_sha256") != _document_sha256(answer_key)
        or set(document.get("bindings", {}))
        != {
            "source_bindings_commitment",
            "audio_manifest_sha256",
            "answer_key_sha256",
            "answer_key_document_sha256",
        }
        or answer_key.get("bindings", {}).get("source_bindings_commitment")
        != document["bindings"]["source_bindings_commitment"]
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != _FALSE_EFFECTS
    ):
        raise ValueError("private v2 join review package differs")
    _verify_public_units(document["units"], root=root, context=context)
    page = (root / HTML_NAME).read_text(encoding="utf-8")
    if (
        "v1_candidate" in page
        or "v2_candidate" in page
        or "boundary_assignments" in page
        or ANSWER_KEY_NAME in page
    ):
        raise ValueError("private v2 join review page reveals a candidate identity")


def _verify_public_units(
    units: list[Mapping[str, Any]], *, root: Path, context: Mapping[str, Any]
) -> None:
    import numpy as np

    if len(units) != 6:
        raise ValueError("private v2 join review unit inventory differs")
    references: set[Path] = set()
    boundary_count = 0
    edge_count = 0
    for unit in units:
        kind = unit.get("kind")
        if kind == _BOUNDARY_KIND:
            boundary_count += 1
            if (
                set(unit["audio"]) != {"A", "B"}
                or unit.get("heard") != {"A": False, "B": False}
                or unit.get("absolute_cleanliness") != {"A": None, "B": None}
                or unit.get("comparative_choice") is not None
            ):
                raise ValueError("private v2 boundary review unit differs")
        elif kind == _EDGE_KIND:
            edge_count += 1
            if (
                set(unit["audio"]) != {"clip"}
                or unit.get("heard") is not False
                or unit.get("absolute_cleanliness") is not None
                or "comparative_choice" in unit
            ):
                raise ValueError("private v2 patch-edge review unit differs")
        else:
            raise ValueError("private v2 join review unit kind differs")
        for record in unit["audio"].values():
            path = _private_child_regular(
                root,
                record["path"],
                "private v2 join review audio",
            )
            if path in references:
                raise ValueError("private v2 join review audio is reused")
            references.add(path)
            observed = _read_pcm24_snapshot(
                path,
                record,
                expected_frames=record["geometry"]["frames"],
                label="private v2 join review audio",
            )
            if (
                observed["pcm24_int32_sequence_sha256"]
                != record["pcm24_int32_sequence_sha256"]
            ):
                raise ValueError("private v2 join review audio differs")
        if kind == _EDGE_KIND:
            parts = unit["unit_id"].split("-")
            boundary_index = int(parts[3])
            role = parts[4]
            edge_name = parts[5]
            window = next(
                row
                for row in context["v2_report"]["windows"]
                if int(row["boundary_index"]) == boundary_index and row["role"] == role
            )
            centre = int(window[f"patch_{edge_name}_frame"])
            expected = context["v2_audio"][role]["samples"]
            expected = expected[centre - _EDGE_HALF_FRAMES : centre + _EDGE_HALF_FRAMES]
            record = unit["audio"]["clip"]
            observed = _read_pcm24_snapshot(
                root / record["path"],
                record,
                expected_frames=2 * _EDGE_HALF_FRAMES,
                label="private v2 patch-edge review audio",
            )
            if not bool(np.array_equal(observed["samples"], expected)):
                raise ValueError("private v2 patch-edge PCM24 samples differ")
    if boundary_count != 2 or edge_count != 4 or len(references) != 8:
        raise ValueError("private v2 join review unit inventory differs")


def _reverify_inputs(context: Mapping[str, Any]) -> None:
    for snapshot, label in (
        (context["v2_plan_snapshot"], "private v2 join-remediation plan"),
        (context["stitch_snapshot"], "private full-song stitch report"),
        (context["v1_execution_snapshot"], "private v1 remediation execution"),
        (context["v1_candidate_snapshot"], "private v1 remediation candidate"),
        (context["v2_snapshot"], "private v2 remediation execution"),
    ):
        current = _load_private_json_snapshot(snapshot["path"], label)
        if (
            current["sha256"] != snapshot["sha256"]
            or current["document"] != snapshot["document"]
        ):
            raise ValueError(f"{label} changed during v2 review preparation")
    _require_plan_rederivation(
        context["v2_plan"],
        **context["authority_arguments"],
    )
    _require_execution_geometry(
        context["v2_plan"],
        context["execution_inputs"],
    )
    _reverify_input_audio(context["execution_inputs"])
    _verify_published_candidate(
        context["v2_root"],
        context["v2_report"],
        inputs=context["execution_inputs"],
    )
    _verify_stitch_audio(context["stitch_root"], context["stitch"])
    for identity in ("v1_audio", "v2_audio"):
        for role, audio in context[identity].items():
            current = _read_pcm24_snapshot(
                audio["path"],
                {"sha256": audio["sha256"], "bytes": audio["bytes"]},
                expected_frames=audio["frames"],
                label=(f"private {identity.replace('_audio', '')} {role} candidate"),
            )
            if (
                current["pcm24_int32_sequence_sha256"]
                != audio["pcm24_int32_sequence_sha256"]
            ):
                raise ValueError(
                    f"private {identity.replace('_audio', '')} {role} candidate PCM24 source changed"
                )


def _publication_claims(staging: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    audio: dict[str, Mapping[str, Any]] = {}
    for unit in document["units"]:
        for record in unit["audio"].values():
            relative = Path(record["path"])
            if relative.parent != Path(AUDIO_DIRECTORY) or relative.name in audio:
                raise ValueError(
                    "private v2 review publication audio inventory differs"
                )
            path = _private_child_regular(
                staging,
                record["path"],
                "private v2 review staged audio",
            )
            if (
                _sha256(path) != record["sha256"]
                or path.stat().st_size != record["bytes"]
            ):
                raise ValueError("private v2 review staged audio claim differs")
            audio[relative.name] = record
    if len(audio) != 8:
        raise ValueError("private v2 review publication audio inventory differs")
    files: dict[str, dict[str, Any]] = {}
    for name in (ANSWER_KEY_NAME, HTML_NAME, REPORT_NAME):
        path = staging / name
        _require_private_regular(path, "private v2 review staged file")
        files[name] = {"sha256": _sha256(path), "bytes": path.stat().st_size}
    if files[ANSWER_KEY_NAME]["sha256"] != document["bindings"]["answer_key_sha256"]:
        raise ValueError("private v2 review staged answer key differs")
    expected_page = _review_html(document).encode("utf-8")
    if files[HTML_NAME]["sha256"] != hashlib.sha256(expected_page).hexdigest() or files[
        HTML_NAME
    ]["bytes"] != len(expected_page):
        raise ValueError("private v2 review staged HTML differs")
    return {"audio": audio, "files": files}


def _publish_package_no_overwrite(
    staging: Path,
    destination: Path,
    *,
    document: Mapping[str, Any],
    answer_key: Mapping[str, Any],
    claims: Mapping[str, Any],
    context: Mapping[str, Any],
    parent_descriptor: int,
) -> None:
    build_name = f".{destination.name}.{secrets.token_hex(32)}.building"
    destination_descriptor: int | None = None
    audio_descriptor: int | None = None
    published = False
    audio_names = sorted(claims["audio"])
    os.mkdir(build_name, mode=0o700, dir_fd=parent_descriptor)
    build_state = os.stat(
        build_name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    os.fsync(parent_descriptor)
    try:
        destination_descriptor = _open_directory_at(
            parent_descriptor,
            build_name,
            "private v2 review hidden build root",
            expected_identity=(build_state.st_dev, build_state.st_ino),
        )
    except BaseException:
        try:
            os.rmdir(build_name, dir_fd=parent_descriptor)
        except OSError:
            pass
        raise
    try:
        os.mkdir(AUDIO_DIRECTORY, mode=0o700, dir_fd=destination_descriptor)
        audio_state = os.stat(
            AUDIO_DIRECTORY,
            dir_fd=destination_descriptor,
            follow_symlinks=False,
        )
        audio_descriptor = _open_directory_at(
            destination_descriptor,
            AUDIO_DIRECTORY,
            "private v2 review hidden audio root",
            expected_identity=(audio_state.st_dev, audio_state.st_ino),
        )
        for name in audio_names:
            _copy_regular_exclusive(
                staging / AUDIO_DIRECTORY / name,
                audio_descriptor,
                name,
                claim=claims["audio"][name],
            )
        os.fsync(audio_descriptor)
        for name in (ANSWER_KEY_NAME, HTML_NAME, REPORT_NAME):
            _copy_regular_exclusive(
                staging / name,
                destination_descriptor,
                name,
                claim=claims["files"][name],
            )
        os.fsync(destination_descriptor)
        _verify_bound_package(
            destination_descriptor,
            audio_descriptor,
            document=document,
            answer_key=answer_key,
            claims=claims,
        )
        report_state = os.stat(
            REPORT_NAME,
            dir_fd=destination_descriptor,
            follow_symlinks=False,
        )
        report_identity = (report_state.st_dev, report_state.st_ino)
        try:
            _rename_directory_exclusive_at(
                parent_descriptor,
                build_name,
                destination.name,
            )
        except FileExistsError as error:
            raise FileExistsError(
                f"private v2 join review exists: {destination}"
            ) from error
        published = True
        try:
            _verify_visible_review_binding(
                destination,
                parent_descriptor=parent_descriptor,
                destination_descriptor=destination_descriptor,
                audio_descriptor=audio_descriptor,
            )
            _verify_bound_package(
                destination_descriptor,
                audio_descriptor,
                document=document,
                answer_key=answer_key,
                claims=claims,
            )
            _reverify_inputs(context)
            os.fsync(audio_descriptor)
            os.fsync(destination_descriptor)
            os.fsync(parent_descriptor)
        except BaseException:
            _revoke_bound_report(
                destination_descriptor,
                expected_identity=report_identity,
            )
            raise
    finally:
        if not published:
            if audio_descriptor is not None:
                for name in audio_names:
                    try:
                        os.unlink(name, dir_fd=audio_descriptor)
                    except FileNotFoundError:
                        pass
            for name in (ANSWER_KEY_NAME, HTML_NAME, REPORT_NAME):
                try:
                    os.unlink(name, dir_fd=destination_descriptor)
                except FileNotFoundError:
                    pass
            try:
                os.rmdir(AUDIO_DIRECTORY, dir_fd=destination_descriptor)
            except OSError:
                pass
            try:
                os.rmdir(build_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if audio_descriptor is not None:
            _close_best_effort(audio_descriptor)
        if destination_descriptor is not None:
            _close_best_effort(destination_descriptor)


def _close_best_effort(descriptor: int) -> None:
    """Do not turn a completed, fsynced publication into a reported failure."""

    try:
        os.close(descriptor)
    except OSError:
        pass


def _copy_regular_exclusive(
    source: Path,
    directory_descriptor: int,
    name: str,
    *,
    claim: Mapping[str, Any],
) -> None:
    _require_private_regular(source, "private v2 review staged file")
    source_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    source_descriptor = os.open(source, source_flags)
    source_before = os.fstat(source_descriptor)
    target_flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        if source_before.st_size != claim.get("bytes"):
            raise ValueError("private v2 review staged file size differs")
        target_descriptor = os.open(
            name,
            target_flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        try:
            source_hash = hashlib.sha256()
            copied = 0
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                source_hash.update(chunk)
                offset = 0
                while offset < len(chunk):
                    written = os.write(target_descriptor, chunk[offset:])
                    if written <= 0:
                        raise RuntimeError(
                            "private v2 review publication made no progress"
                        )
                    offset += written
                    copied += written
            os.fsync(target_descriptor)
            source_after = os.fstat(source_descriptor)
            target_state = os.fstat(target_descriptor)
            if (
                _file_snapshot_identity(source_before)
                != _file_snapshot_identity(source_after)
                or copied != source_before.st_size
                or target_state.st_size != copied
                or source_hash.hexdigest() != claim.get("sha256")
            ):
                raise ValueError("private v2 review publication copy differs")
        finally:
            os.close(target_descriptor)
    finally:
        os.close(source_descriptor)


def _verify_bound_package(
    destination_descriptor: int,
    audio_descriptor: int,
    *,
    document: Mapping[str, Any],
    answer_key: Mapping[str, Any],
    claims: Mapping[str, Any],
) -> None:
    if set(os.listdir(destination_descriptor)) != {
        ANSWER_KEY_NAME,
        HTML_NAME,
        REPORT_NAME,
        AUDIO_DIRECTORY,
    } or set(os.listdir(audio_descriptor)) != set(claims["audio"]):
        raise ValueError("private v2 review bound publication inventory differs")
    report_payload = _read_regular_at(
        destination_descriptor,
        REPORT_NAME,
        claims["files"][REPORT_NAME],
        label="private v2 review bound report",
    )
    answer_payload = _read_regular_at(
        destination_descriptor,
        ANSWER_KEY_NAME,
        claims["files"][ANSWER_KEY_NAME],
        label="private v2 review bound answer key",
    )
    page = _read_regular_at(
        destination_descriptor,
        HTML_NAME,
        claims["files"][HTML_NAME],
        label="private v2 review bound HTML",
    ).decode("utf-8")
    if (
        json.loads(report_payload) != document
        or json.loads(answer_payload) != answer_key
    ):
        raise ValueError("private v2 review bound JSON differs")
    if any(
        secret in page
        for secret in (
            "v1_candidate",
            "v2_candidate",
            "boundary_assignments",
            ANSWER_KEY_NAME,
        )
    ):
        raise ValueError("private v2 review bound page reveals a candidate identity")
    for name, record in claims["audio"].items():
        observed = _read_pcm24_at(
            audio_descriptor,
            name,
            record,
            expected_frames=record["geometry"]["frames"],
            label="private v2 review bound audio",
        )
        if (
            observed["pcm24_int32_sequence_sha256"]
            != record["pcm24_int32_sequence_sha256"]
        ):
            raise ValueError("private v2 review bound audio differs")


def _read_regular_at(
    directory_descriptor: int,
    name: str,
    claim: Mapping[str, Any],
    *,
    label: str,
) -> bytes:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError(f"{label} cannot be opened without no-follow support")
    descriptor = os.open(
        name,
        os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory_descriptor,
    )
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        visible_before = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or (before.st_dev, before.st_ino)
            != (visible_before.st_dev, visible_before.st_ino)
            or before.st_size != claim.get("bytes")
        ):
            raise ValueError(f"{label} is not an owner-only bound file")
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        visible_after = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if (
            _file_snapshot_identity(before) != _file_snapshot_identity(after)
            or (after.st_dev, after.st_ino)
            != (visible_after.st_dev, visible_after.st_ino)
            or digest.hexdigest() != claim.get("sha256")
        ):
            raise ValueError(f"{label} changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _verify_visible_review_binding(
    destination: Path,
    *,
    parent_descriptor: int,
    destination_descriptor: int,
    audio_descriptor: int,
) -> None:
    parent_state = os.fstat(parent_descriptor)
    destination_state = os.fstat(destination_descriptor)
    audio_state = os.fstat(audio_descriptor)
    try:
        visible_parent = destination.parent.lstat()
        visible_by_parent = os.stat(
            destination.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        visible_destination = destination.lstat()
        visible_audio_by_destination = os.stat(
            AUDIO_DIRECTORY,
            dir_fd=destination_descriptor,
            follow_symlinks=False,
        )
        visible_audio = (destination / AUDIO_DIRECTORY).lstat()
    except OSError as error:
        raise RuntimeError(
            "private v2 review visible output binding changed"
        ) from error
    if (
        (parent_state.st_dev, parent_state.st_ino)
        != (visible_parent.st_dev, visible_parent.st_ino)
        or (destination_state.st_dev, destination_state.st_ino)
        != (visible_by_parent.st_dev, visible_by_parent.st_ino)
        or (destination_state.st_dev, destination_state.st_ino)
        != (visible_destination.st_dev, visible_destination.st_ino)
        or (audio_state.st_dev, audio_state.st_ino)
        != (visible_audio_by_destination.st_dev, visible_audio_by_destination.st_ino)
        or (audio_state.st_dev, audio_state.st_ino)
        != (visible_audio.st_dev, visible_audio.st_ino)
        or stat.S_IMODE(destination_state.st_mode) != 0o700
        or stat.S_IMODE(audio_state.st_mode) != 0o700
    ):
        raise RuntimeError("private v2 review visible output binding changed")


def _revoke_bound_report(
    destination_descriptor: int,
    *,
    expected_identity: tuple[int, int],
) -> None:
    try:
        current = os.stat(
            REPORT_NAME,
            dir_fd=destination_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) != expected_identity:
        raise RuntimeError(
            "private v2 review report identity changed before revocation"
        )
    os.unlink(REPORT_NAME, dir_fd=destination_descriptor)
    os.fsync(destination_descriptor)


def _file_snapshot_identity(state: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        state.st_dev,
        state.st_ino,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )


def _review_html(document: Mapping[str, Any]) -> str:
    seed = json.dumps(document, ensure_ascii=False).replace("</", "<\\/")
    absolute = "".join(
        f'<label><input type="radio" name="absolute-TEMPLATE" value="{value}"> '
        f"{html.escape(value.replace('_', ' '))}</label>"
        for value in _ABSOLUTE_CHOICES
    )
    comparative = "".join(
        f'<label><input type="radio" name="compare-TEMPLATE" value="{value}"> '
        f"{html.escape(value.replace('_', ' '))}</label>"
        for value in _COMPARATIVE_CHOICES
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend expanded join review</title>
<style>
body{{margin:0;background:#08111d;color:#e8f1ff;font:18px/1.45 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:32px}}
.privacy{{background:#104a32;padding:12px 24px;font-weight:700}}.card{{background:#101e2c;border:1px solid #29435b;border-radius:18px;padding:24px;margin:22px 0}}
h1{{font-size:42px}}h2{{color:#63d7ff}}h3{{margin-bottom:6px}}audio{{width:100%;margin:8px 0 10px}}label{{display:inline-block;margin:7px 16px 7px 0}}textarea{{width:100%;min-height:80px;background:#0a1724;color:#fff;border:1px solid #3b607d;border-radius:8px}}
button{{background:#1d789c;color:#fff;border:0;border-radius:9px;padding:14px 20px;font-size:17px;margin-right:10px}}button:disabled{{opacity:.45}}.status{{color:#ffd253;font-weight:700}}.hint{{color:#b7c9da}}
</style></head><body><div class="privacy">Private local developer review — no audio or review is uploaded</div><main>
<div class="card"><h1>Expanded-context join review</h1><p>{html.escape(document["question"])}</p>
<p>First review <strong>2 anonymous boundary comparisons</strong>, rating each version independently. Then review <strong>4 single expanded-candidate patch edges</strong>. There is no complete-song review in this package.</p>
<p><strong>Do not open the separate answer key before exporting this review.</strong></p><p class="status" id="progress">Reviewed 0 of {len(document["units"])} units</p></div>
<div id="units"></div><div class="card"><button id="complete">Mark review complete</button><button id="export" disabled>Export reviewed JSON</button><p id="message"></p></div>
<script id="seed" type="application/json">{seed}</script><script>
const review=JSON.parse(document.getElementById('seed').textContent);const host=document.getElementById('units');
const absoluteTemplate={json.dumps(absolute)};const comparativeTemplate={json.dumps(comparative)};
function absoluteGroup(i,slot){{return absoluteTemplate.replaceAll('absolute-TEMPLATE','absolute-'+i+'-'+slot);}}
function render(){{review.units.forEach((u,i)=>{{const c=document.createElement('section');c.className='card';
if(u.kind==='boundary_candidate_pair'){{c.innerHTML=`<h2>${{i+1}}. ${{u.title}}</h2><p>${{u.focus}}</p><h3>Candidate A</h3><audio controls preload="metadata" src="${{u.audio.A.path}}"></audio><label><input type="checkbox" data-heard="A"> I heard A</label><p class="hint">How clean is A?</p><div data-absolute="A">${{absoluteGroup(i,'A')}}</div><h3>Candidate B</h3><audio controls preload="metadata" src="${{u.audio.B.path}}"></audio><label><input type="checkbox" data-heard="B"> I heard B</label><p class="hint">How clean is B?</p><div data-absolute="B">${{absoluteGroup(i,'B')}}</div><p class="hint">After rating each independently, which do you prefer?</p><div data-compare>${{comparativeTemplate.replaceAll('compare-TEMPLATE','compare-'+i)}}</div>`;
c.querySelectorAll('[data-heard]').forEach(x=>x.onchange=()=>{{u.heard[x.dataset.heard]=x.checked;update();}});c.querySelectorAll('[data-absolute]').forEach(group=>group.querySelectorAll('input').forEach(x=>x.onchange=()=>{{u.absolute_cleanliness[group.dataset.absolute]=x.value;update();}}));c.querySelectorAll('[data-compare] input').forEach(x=>x.onchange=()=>{{u.comparative_choice=x.value;update();}});
}}else{{c.innerHTML=`<h2>${{i+1}}. ${{u.title}}</h2><p>${{u.focus}}</p><audio controls preload="metadata" src="${{u.audio.clip.path}}"></audio><label><input type="checkbox" data-heard="clip"> I heard this edge</label><p class="hint">How clean is this edge?</p><div data-edge-absolute>${{absoluteGroup(i,'edge')}}</div>`;c.querySelector('[data-heard]').onchange=e=>{{u.heard=e.target.checked;update();}};c.querySelectorAll('[data-edge-absolute] input').forEach(x=>x.onchange=()=>{{u.absolute_cleanliness=x.value;update();}});}}
c.insertAdjacentHTML('beforeend','<p>Optional private notes</p><textarea maxlength="1000"></textarea>');c.querySelector('textarea').oninput=e=>u.notes=e.target.value;host.appendChild(c);}});}}
function unitComplete(u){{if(u.kind==='boundary_candidate_pair')return u.heard.A&&u.heard.B&&u.absolute_cleanliness.A&&u.absolute_cleanliness.B&&u.comparative_choice;return u.heard&&u.absolute_cleanliness;}}
function update(){{const done=review.units.filter(unitComplete).length;review.summary.reviewed_units=done;document.getElementById('progress').textContent=`Reviewed ${{done}} of ${{review.units.length}} units`;}}
document.getElementById('complete').onclick=()=>{{update();if(review.summary.reviewed_units!==review.units.length){{document.getElementById('message').textContent='Hear and rate every clip, and make both anonymous comparative choices first.';return;}}review.status='reviewed';review.summary.complete=true;document.getElementById('export').disabled=false;document.getElementById('message').textContent='Complete. Export the reviewed JSON.';}};
document.getElementById('export').onclick=()=>{{const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='join_remediation_review_v2.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};render();update();
</script></main></body></html>"""


def _write_text_exclusive(path: Path, value: str) -> None:
    payload = value.encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("private v2 review HTML write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"private v2 review {label} differs")
    return value


__all__: tuple[str, ...] = ()
