"""Execute one review-derived private join-remediation iteration.

The executor re-verifies the complete evidence chain, delegates only the exact
planned source windows to the audited private Kim worker, and creates a new
candidate from the immutable v2 audio.  It cannot select, accept, publish or
activate a separator, and it never mutates the v2 candidate.
"""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from typing import Any, Callable, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_join_remediation_plan import (
    POLICY_ID,
    REPORT_NAME as PLAN_REPORT_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
    _FALSE_EFFECTS as PLAN_FALSE_EFFECTS,
    _plan_private_candidate_join_remediation,
)
from ._separation_candidate_readiness_reassessment import _reverify_all
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor import (
    REPORT_NAME as WORKER_REPORT_NAME,
    _execute_private_separation_full_song_join_remediation,
    _selected_attempt_record,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _apply_equal_power_patch,
    _audio_claim,
    _outside_ranges_exact,
    _quantize_float_to_pcm24_int32,
    _read_pcm24_snapshot,
    _rename_directory_exclusive_at,
    _require_exclusive_directory_rename_available,
    _require_output_disjoint_from_inputs,
    _write_pcm24_exclusive,
)
from ._separation_full_song_join_remediation_plan import (
    POLICY_ID as WORKER_PLAN_POLICY_ID,
    REPORT_NAME as WORKER_PLAN_REPORT_NAME,
    SCHEMA as WORKER_PLAN_SCHEMA,
    STATUS as WORKER_PLAN_STATUS,
    _FALSE_EFFECTS as WORKER_PLAN_FALSE_EFFECTS,
    _FALSE_PERMISSIONS,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
)
from ._separation_full_song_join_remediation_review_v2 import _load_review_inputs
from ._separation_melroformer_native_attempt_darwin import (
    _run_private_melroformer_native_attempt_darwin,
)


SCHEMA = "sunofriend.private-separation-candidate-join-remediation-execution.v1"
STATUS_INCOMPLETE = "review_derived_join_reinference_incomplete_not_selected"
STATUS_COMPLETE = "review_derived_join_reinference_candidate_complete_review_required"
REPORT_NAME = "private-separation-candidate-join-remediation-execution.json"
CANDIDATE_REPORT_NAME = "private-separation-candidate-join-remediation-candidates.json"
WORKER_PLAN_DIRECTORY = "WORKER-PLAN"
WORKER_EXECUTION_DIRECTORY = "WORKER-EXECUTION"
CANDIDATES_DIRECTORY = "CANDIDATES"
_ROLES = ("vocals", "instrumental")
_FULL_SONG_ROLES = (*_ROLES, "reconstruction")
_EFFECTS_COMPLETE = {
    "candidate_audio_created": True,
    "model_run": True,
    "publication_state_mutated": False,
    "review_evidence_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "v2_candidate_mutated": False,
}
AttemptRunner = Callable[..., Mapping[str, Any]]


def _execute_private_candidate_join_remediation(
    plan_path: str | Path,
    *,
    v2_review_result_path: str | Path,
    candidate_review_result_path: str | Path,
    candidate_alignment_result_path: str | Path,
    readiness_reassessment_path: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    source_plan_path: str | Path,
    out_dir: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str = "gpu",
    maximum_windows: int | None = 1,
    attempt_runner: AttemptRunner = _run_private_melroformer_native_attempt_darwin,
) -> dict[str, Any]:
    """Resume exact workers, then publish one separate review-required candidate."""

    plan_snapshot = _load_private_json_snapshot(
        plan_path, "private candidate join-remediation plan"
    )
    plan = plan_snapshot["document"]
    _require_plan_identity(plan)
    evidence_arguments = {
        "candidate_review_result_path": candidate_review_result_path,
        "candidate_alignment_result_path": candidate_alignment_result_path,
        "readiness_reassessment_path": readiness_reassessment_path,
        "v2_execution_dir": v2_execution_dir,
        "v2_plan_path": v2_plan_path,
        "v1_execution_dir": v1_execution_dir,
        "stitch_package_dir": stitch_package_dir,
        "full_song_review_result_path": full_song_review_result_path,
        "v1_plan_path": v1_plan_path,
        "resolved_join_review_result_path": resolved_join_review_result_path,
        "publication_readiness_path": publication_readiness_path,
    }
    _require_plan_rederivation(
        plan,
        v2_review_result_path=v2_review_result_path,
        **evidence_arguments,
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
    review_snapshot = _load_private_json_snapshot(
        candidate_review_result_path, "private candidate full-song review result"
    )
    alignment_snapshot = _load_private_json_snapshot(
        candidate_alignment_result_path, "private candidate alignment result"
    )
    v2_review_snapshot = _load_private_json_snapshot(
        v2_review_result_path, "private resolved v2 join review result"
    )
    _reverify_all(v2_review_snapshot, review_snapshot, alignment_snapshot, context)

    destination = Path(out_dir).expanduser().absolute()
    evidence_paths = (
        plan_snapshot["path"],
        Path(readiness_reassessment_path).expanduser().absolute(),
        Path(source_plan_path).expanduser().absolute(),
        review_snapshot["path"],
        alignment_snapshot["path"],
        v2_review_snapshot["path"],
        context["v2_snapshot"]["path"],
        context["v2_plan_snapshot"]["path"],
        context["stitch_snapshot"]["path"],
        context["v1_execution_snapshot"]["path"],
        context["v1_candidate_snapshot"]["path"],
        *context["authority_paths"],
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(context["v1_root"], context["v2_root"], context["stitch_root"]),
        evidence_paths=evidence_paths,
    )
    if os.path.lexists(destination):
        _require_private_directory(destination, "private candidate remediation root")
    else:
        destination.mkdir(parents=True, mode=0o700)
        destination.chmod(0o700)

    adapter_path = _load_or_write_worker_plan(
        destination,
        plan=plan,
        plan_snapshot=plan_snapshot,
        context=context,
    )
    worker_root = destination / WORKER_EXECUTION_DIRECTORY
    worker = _execute_private_separation_full_song_join_remediation(
        adapter_path,
        package_dir=stitch_package_dir,
        source_plan_path=source_plan_path,
        out_dir=worker_root,
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
        device=device,
        maximum_windows=maximum_windows,
        build_candidates=False,
        attempt_runner=attempt_runner,
    )
    if not worker["summary"]["all_worker_runs_complete"]:
        return {
            "schema": SCHEMA,
            "status": STATUS_INCOMPLETE,
            "report": None,
            "candidate_report_path": None,
            "output_directory": str(destination),
            "worker_report": worker["report"],
            "windows_executed_this_invocation": worker[
                "windows_executed_this_invocation"
            ],
            "summary": {
                "planned_worker_windows": len(plan["windows"]),
                "verified_worker_windows": worker["summary"]["verified_windows"],
                "remaining_worker_windows": worker["summary"]["remaining_windows"],
                "candidate_audio_complete": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
        }

    candidate = _load_or_build_candidate(
        destination,
        plan=plan,
        plan_snapshot=plan_snapshot,
        context=context,
        worker_root=worker_root,
        worker_state=worker,
    )
    report_path = destination / REPORT_NAME
    if os.path.lexists(report_path):
        execution_snapshot = _load_private_json_snapshot(
            report_path, "private candidate remediation execution"
        )
        document = execution_snapshot["document"]
        _verify_execution_document(
            document,
            plan=plan,
            plan_snapshot=plan_snapshot,
            worker_root=worker_root,
            worker_state=worker,
            candidate=candidate,
            destination=destination,
            context=context,
        )
    else:
        document = _execution_document(
            plan=plan,
            plan_snapshot=plan_snapshot,
            adapter_path=adapter_path,
            worker_root=worker_root,
            worker_state=worker,
            candidate=candidate,
            destination=destination,
            context=context,
        )
        _reverify_all(v2_review_snapshot, review_snapshot, alignment_snapshot, context)
        _write_json_exclusive(report_path, document)
    return {
        **document,
        "report": str(report_path),
        "candidate_report_path": str(
            destination / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME
        ),
        "output_directory": str(destination),
        "worker_report": worker["report"],
        "windows_executed_this_invocation": worker[
            "windows_executed_this_invocation"
        ],
    }


def _require_plan_identity(plan: Mapping[str, Any]) -> None:
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("status") != PLAN_STATUS
        or plan.get("policy_id") != POLICY_ID
        or plan.get("document_sha256") != _document_sha256(plan)
        or plan.get("permissions") != _FALSE_PERMISSIONS
        or plan.get("effects") != PLAN_FALSE_EFFECTS
        or not isinstance(plan.get("windows"), list)
        or not plan["windows"]
    ):
        raise ValueError("private candidate join-remediation plan differs")


def _require_plan_rederivation(
    plan: Mapping[str, Any],
    *,
    v2_review_result_path: str | Path,
    **arguments: Any,
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="sunofriend-candidate-plan-check-"))
    temporary.chmod(0o700)
    try:
        expected = _plan_private_candidate_join_remediation(
            v2_review_result_path,
            **arguments,
            out=temporary / PLAN_REPORT_NAME,
        )
        expected.pop("report", None)
        if dict(plan) != expected:
            raise ValueError("private candidate join-remediation plan derivation differs")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _worker_plan_document(
    plan: Mapping[str, Any],
    *,
    plan_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    stitch = context["stitch"]
    document: dict[str, Any] = {
        "schema": WORKER_PLAN_SCHEMA,
        "status": WORKER_PLAN_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": WORKER_PLAN_POLICY_ID,
        "bindings": {
            "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "raw_vocals_audio_sha256": stitch["artifacts"]["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": stitch["artifacts"]["instrumental"][
                "sha256"
            ],
            "raw_reconstruction_audio_sha256": stitch["artifacts"][
                "reconstruction"
            ]["sha256"],
            "plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "execution_state_sha256": stitch["bindings"]["execution_state_sha256"],
            "candidate_remediation_plan_sha256": plan_snapshot["sha256"],
            "candidate_remediation_plan_document_sha256": plan["document_sha256"],
        },
        "clock": deepcopy(plan["clock"]),
        "protocol": deepcopy(plan["protocol"]),
        "windows": deepcopy(plan["windows"]),
        "summary": {
            "planned_model_call_count": len(plan["windows"]),
            "candidate_assembly_delegated": False,
            "worker_only_adapter": True,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(WORKER_PLAN_FALSE_EFFECTS),
        "limitations": [
            "This adapter exists only to reuse the audited private worker runner.",
            "The worker runner must stop before its raw-stitch candidate builder.",
            "The review-derived executor separately assembles from immutable v2 audio.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _load_or_write_worker_plan(
    destination: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Path:
    root = destination / WORKER_PLAN_DIRECTORY
    if os.path.lexists(root):
        _require_private_directory(root, "private candidate worker-plan root")
    else:
        root.mkdir(mode=0o700)
    path = root / WORKER_PLAN_REPORT_NAME
    expected = _worker_plan_document(
        plan, plan_snapshot=plan_snapshot, context=context
    )
    if os.path.lexists(path):
        actual = _load_private_json_snapshot(
            path, "private candidate worker adapter plan"
        )["document"]
        if actual != expected:
            raise ValueError("private candidate worker adapter plan changed")
    else:
        _write_json_exclusive(path, expected)
    return path


def _load_or_build_candidate(
    destination: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_root = destination / CANDIDATES_DIRECTORY
    if os.path.lexists(candidate_root):
        return _verify_candidate(
            candidate_root,
            plan=plan,
            plan_snapshot=plan_snapshot,
            context=context,
            worker_root=worker_root,
            worker_state=worker_state,
        )
    _require_exclusive_directory_rename_available()
    staging = destination / f".{CANDIDATES_DIRECTORY}.{secrets.token_hex(16)}.building"
    staging.mkdir(mode=0o700)
    try:
        _build_candidate(
            staging,
            plan=plan,
            plan_snapshot=plan_snapshot,
            context=context,
            worker_root=worker_root,
            worker_state=worker_state,
        )
        _verify_candidate(
            staging,
            plan=plan,
            plan_snapshot=plan_snapshot,
            context=context,
            worker_root=worker_root,
            worker_state=worker_state,
        )
        descriptor = os.open(
            destination,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            _rename_directory_exclusive_at(
                descriptor, staging.name, CANDIDATES_DIRECTORY
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return _verify_candidate(
        candidate_root,
        plan=plan,
        plan_snapshot=plan_snapshot,
        context=context,
        worker_root=worker_root,
        worker_state=worker_state,
    )


def _build_candidate(
    root: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> dict[str, Any]:
    import numpy as np

    total_frames = int(plan["clock"]["frames"])
    blend = int(plan["protocol"]["edge_blend_frames"])
    worker_by_index = {
        int(item["window_index"]): item for item in worker_state["windows"]
    }
    artifacts: dict[str, Any] = {}
    patch_records: list[dict[str, Any]] = []
    written: dict[str, Any] = {}
    for role in _ROLES:
        base = context["v2_audio"][role]["samples"]
        candidate = base.astype("float64") / 2_147_483_648.0
        ranges: list[tuple[int, int]] = []
        for window in plan["windows"]:
            if role not in window["patch_target_roles"]:
                continue
            state = worker_by_index[int(window["window_index"])]
            selected = _selected_attempt_record(state)
            worker_path = (
                worker_root
                / selected["path"]
                / "staging"
                / "quarantine"
                / "STEMS"
                / f"{role}.wav"
            )
            worker = _read_pcm24_snapshot(
                worker_path,
                selected["outputs"][role],
                expected_frames=int(window["source_end_frame"])
                - int(window["source_start_frame"]),
                label=f"private candidate worker {window['window_index']} {role}",
            )
            start = int(window["patch_start_frame"])
            end = int(window["patch_end_frame"])
            local_start = start - int(window["source_start_frame"])
            local_end = end - int(window["source_start_frame"])
            replacement = (
                worker["samples"][local_start:local_end].astype("float64")
                / 2_147_483_648.0
            )
            _apply_equal_power_patch(
                candidate,
                replacement,
                start=start,
                end=end,
                blend_frames=blend,
                np=np,
            )
            ranges.append((start, end))
            patch_records.append(
                {
                    "window_index": window["window_index"],
                    "boundary_index": window["boundary_index"],
                    "role": role,
                    "source_start_frame": window["source_start_frame"],
                    "source_end_frame": window["source_end_frame"],
                    "patch_start_frame": start,
                    "patch_end_frame": end,
                    "worker_local_patch_start_frame": local_start,
                    "worker_local_patch_end_frame": local_end,
                    "edge_blend_frames": blend,
                    "worker_output_sha256": worker["sha256"],
                    "model_run": True,
                }
            )
        peak = float(np.max(np.abs(candidate))) if candidate.size else 0.0
        if not math.isfinite(peak) or peak > 1.0:
            raise ValueError("private candidate remediated role would clip")
        target = root / f"{role}.wav"
        _write_pcm24_exclusive(target, candidate)
        observed = _read_pcm24_snapshot(
            target,
            None,
            expected_frames=total_frames,
            label=f"private candidate staged {role}",
        )
        _outside_ranges_exact(base, observed["samples"], ranges=ranges, np=np)
        role_records = [item for item in patch_records if item["role"] == role]
        for record in role_records:
            state = worker_by_index[int(record["window_index"])]
            selected = _selected_attempt_record(state)
            worker_path = (
                worker_root
                / selected["path"]
                / "staging"
                / "quarantine"
                / "STEMS"
                / f"{role}.wav"
            )
            worker = _read_pcm24_snapshot(
                worker_path,
                selected["outputs"][role],
                expected_frames=int(record["source_end_frame"])
                - int(record["source_start_frame"]),
                label=f"private candidate worker {record['window_index']} {role}",
            )["samples"]
            start = int(record["patch_start_frame"])
            end = int(record["patch_end_frame"])
            local_start = int(record["worker_local_patch_start_frame"])
            local_end = int(record["worker_local_patch_end_frame"])
            changed = int(np.count_nonzero(observed["samples"][start:end] != base[start:end]))
            if changed < 1 or not bool(
                np.array_equal(
                    observed["samples"][start + blend : end - blend],
                    worker[local_start + blend : local_end - blend],
                )
            ):
                raise ValueError("private candidate target projection differs")
            record["changed_pcm24_sample_values"] = changed
            record["interior_pcm24_samples_match_worker"] = True
            record["outside_target_pcm24_samples_match_v2_candidate"] = True
        claim = _audio_claim(target, root=root, snapshot=observed)
        claim.update(
            {
                "v2_candidate_base_sha256": context["v2_audio"][role]["sha256"],
                "peak_before_write": round(peak, 9),
                "target_patch_count": len(ranges),
                "outside_target_pcm24_samples_match_v2_candidate": True,
            }
        )
        artifacts[role] = claim
        written[role] = observed["samples"]

    reconstruction_float = (
        written["vocals"].astype("float64")
        + written["instrumental"].astype("float64")
    ) / 2_147_483_648.0
    pre_peak = (
        float(np.max(np.abs(reconstruction_float)))
        if reconstruction_float.size
        else 0.0
    )
    if not math.isfinite(pre_peak):
        raise ValueError("private candidate reconstruction is not finite")
    gain = min(1.0, 0.98 / pre_peak) if pre_peak else 1.0
    reconstruction_path = root / "reconstruction.wav"
    _write_pcm24_exclusive(reconstruction_path, reconstruction_float * gain)
    reconstruction = _read_pcm24_snapshot(
        reconstruction_path,
        None,
        expected_frames=total_frames,
        label="private candidate staged reconstruction",
    )
    expected = _quantize_float_to_pcm24_int32(
        reconstruction_float * gain, np=np
    )
    if not bool(np.array_equal(reconstruction["samples"], expected)):
        raise ValueError("private candidate reconstruction projection differs")
    reconstruction_claim = _audio_claim(
        reconstruction_path, root=root, snapshot=reconstruction
    )
    reconstruction_claim.update(
        {
            "source_role_sha256": {role: artifacts[role]["sha256"] for role in _ROLES},
            "pre_gain_peak": round(pre_peak, 9),
            "global_gain": round(gain, 9),
            "attenuation_only": True,
            "canonical_pcm24_projection_verified": True,
        }
    )
    artifacts["reconstruction"] = reconstruction_claim
    patch_records.sort(key=lambda item: (item["boundary_index"], item["role"]))
    document: dict[str, Any] = {
        "schema": "sunofriend.private-separation-candidate-join-remediation-candidates.v1",
        "status": "candidate_audio_complete_review_required",
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "candidate_remediation_plan_sha256": plan_snapshot["sha256"],
            "candidate_remediation_plan_document_sha256": plan["document_sha256"],
            "worker_execution_state_sha256": worker_state["state_sha256"],
            "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
            "v2_execution_document_sha256": context["v2_report"]["document_sha256"],
            "v2_vocals_audio_sha256": context["v2_audio"]["vocals"]["sha256"],
            "v2_instrumental_audio_sha256": context["v2_audio"]["instrumental"][
                "sha256"
            ],
        },
        "clock": deepcopy(plan["clock"]),
        "protocol": deepcopy(plan["protocol"]),
        "patches": patch_records,
        "artifacts": artifacts,
        "summary": {
            "verified_worker_window_count": len(plan["windows"]),
            "patched_boundary_role_pair_count": len(patch_records),
            "candidate_role_count": 3,
            "v2_candidate_control_count": 1,
            "v2_candidate_hashes_unchanged": True,
            "private_listener_notes_copied": False,
        },
        "readiness": {
            "worker_runs_complete": True,
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS_COMPLETE),
        "limitations": [
            "Candidate integrity and exact preservation do not prove musical improvement.",
            "Every targeted boundary and patch edge requires fresh human listening.",
            "A new candidate-bound full-song review and alignment result remain required.",
            "No public CLI, TUI, Simple, Studio or source-graph route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    _write_json_exclusive(root / CANDIDATE_REPORT_NAME, document)
    return document


def _verify_candidate(
    root: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> dict[str, Any]:
    _require_private_directory(root, "private candidate remediation audio root")
    snapshot = _load_private_json_snapshot(
        root / CANDIDATE_REPORT_NAME, "private candidate remediation candidate report"
    )
    document = snapshot["document"]
    if (
        document.get("schema")
        != "sunofriend.private-separation-candidate-join-remediation-candidates.v1"
        or document.get("status") != "candidate_audio_complete_review_required"
        or document.get("policy_id") != POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != _EFFECTS_COMPLETE
        or document.get("clock") != plan["clock"]
        or document.get("protocol") != plan["protocol"]
        or document.get("bindings", {}).get("candidate_remediation_plan_sha256")
        != plan_snapshot["sha256"]
        or document.get("bindings", {}).get("worker_execution_state_sha256")
        != worker_state["state_sha256"]
    ):
        raise ValueError("private candidate remediation candidate report differs")
    total_frames = int(plan["clock"]["frames"])
    observed: dict[str, Any] = {}
    for role in _FULL_SONG_ROLES:
        claim = document["artifacts"][role]
        if claim.get("path") != f"{role}.wav":
            raise ValueError("private candidate remediation artifact path differs")
        observed[role] = _read_pcm24_snapshot(
            root / claim["path"],
            claim,
            expected_frames=total_frames,
            label=f"private candidate remediation {role}",
        )
    _verify_candidate_samples(
        document,
        plan=plan,
        context=context,
        worker_root=worker_root,
        worker_state=worker_state,
        observed=observed,
    )
    return document


def _verify_candidate_samples(
    document: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    context: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
    observed: Mapping[str, Mapping[str, Any]],
) -> None:
    import numpy as np

    worker_by_index = {
        int(item["window_index"]): item for item in worker_state["windows"]
    }
    patches_by_role = {
        role: [item for item in document["patches"] if item["role"] == role]
        for role in _ROLES
    }
    for role in _ROLES:
        base = context["v2_audio"][role]["samples"]
        ranges = [
            (int(item["patch_start_frame"]), int(item["patch_end_frame"]))
            for item in patches_by_role[role]
        ]
        _outside_ranges_exact(base, observed[role]["samples"], ranges=ranges, np=np)
        expected = base.astype("float64") / 2_147_483_648.0
        for patch in patches_by_role[role]:
            state = worker_by_index[int(patch["window_index"])]
            selected = _selected_attempt_record(state)
            worker = _read_pcm24_snapshot(
                worker_root
                / selected["path"]
                / "staging"
                / "quarantine"
                / "STEMS"
                / f"{role}.wav",
                selected["outputs"][role],
                expected_frames=int(patch["source_end_frame"])
                - int(patch["source_start_frame"]),
                label=f"private candidate verified worker {patch['window_index']} {role}",
            )["samples"]
            local_start = int(patch["worker_local_patch_start_frame"])
            local_end = int(patch["worker_local_patch_end_frame"])
            _apply_equal_power_patch(
                expected,
                worker[local_start:local_end].astype("float64") / 2_147_483_648.0,
                start=int(patch["patch_start_frame"]),
                end=int(patch["patch_end_frame"]),
                blend_frames=int(patch["edge_blend_frames"]),
                np=np,
            )
        if not bool(
            np.array_equal(
                observed[role]["samples"],
                _quantize_float_to_pcm24_int32(expected, np=np),
            )
        ):
            raise ValueError("private candidate remediated role differs")
    reconstruction_float = (
        observed["vocals"]["samples"].astype("float64")
        + observed["instrumental"]["samples"].astype("float64")
    ) / 2_147_483_648.0
    pre_peak = (
        float(np.max(np.abs(reconstruction_float)))
        if reconstruction_float.size
        else 0.0
    )
    exact_gain = min(1.0, 0.98 / pre_peak) if pre_peak else 1.0
    stored_gain = float(document["artifacts"]["reconstruction"]["global_gain"])
    if not math.isclose(stored_gain, exact_gain, rel_tol=0.0, abs_tol=5.0e-10):
        raise ValueError("private candidate reconstruction gain differs")
    expected = _quantize_float_to_pcm24_int32(
        reconstruction_float * exact_gain, np=np
    )
    if not bool(np.array_equal(observed["reconstruction"]["samples"], expected)):
        raise ValueError("private candidate reconstruction audio differs")


def _execution_document(
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    adapter_path: Path,
    worker_root: Path,
    worker_state: Mapping[str, Any],
    candidate: Mapping[str, Any],
    destination: Path,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    adapter_snapshot = _load_private_json_snapshot(
        adapter_path, "private candidate worker adapter plan"
    )
    worker_snapshot = _load_private_json_snapshot(
        worker_root / WORKER_REPORT_NAME, "private candidate worker execution"
    )
    candidate_path = destination / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS_COMPLETE,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "candidate_remediation_plan_sha256": plan_snapshot["sha256"],
            "candidate_remediation_plan_document_sha256": plan["document_sha256"],
            "worker_adapter_plan_sha256": adapter_snapshot["sha256"],
            "worker_adapter_plan_document_sha256": adapter_snapshot["document"][
                "document_sha256"
            ],
            "worker_execution_report_sha256": worker_snapshot["sha256"],
            "worker_execution_state_sha256": worker_state["state_sha256"],
            "candidate_report_sha256": _sha256(candidate_path),
            "candidate_document_sha256": candidate["document_sha256"],
            "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
            "v2_execution_document_sha256": context["v2_report"]["document_sha256"],
        },
        "clock": deepcopy(plan["clock"]),
        "protocol": deepcopy(plan["protocol"]),
        "artifacts": {
            role: {
                **dict(candidate["artifacts"][role]),
                "path": f"{CANDIDATES_DIRECTORY}/{candidate['artifacts'][role]['path']}",
            }
            for role in _FULL_SONG_ROLES
        },
        "summary": {
            "planned_model_call_count": len(plan["windows"]),
            "executed_model_call_count": len(plan["windows"]),
            "verified_worker_window_count": len(plan["windows"]),
            "patched_boundary_role_pair_count": len(candidate["patches"]),
            "candidate_role_count": 3,
            "v2_candidate_is_assembly_base": True,
            "v2_candidate_hashes_unchanged": True,
            "private_listener_notes_copied": False,
        },
        "readiness": {
            "worker_runs_complete": True,
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "final_human_acceptance_review_eligible": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS_COMPLETE),
        "limitations": [
            "The candidate is a technical result, not a selected or accepted separator.",
            "Ten role-boundary repairs derive from seven fresh private model windows.",
            "The v2 candidate remains the immutable comparison control.",
            "Targeted listening, complete-song review and alignment remain required.",
            "No public product route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _verify_execution_document(
    document: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
    candidate: Mapping[str, Any],
    destination: Path,
    context: Mapping[str, Any],
) -> None:
    expected = _execution_document(
        plan=plan,
        plan_snapshot=plan_snapshot,
        adapter_path=destination / WORKER_PLAN_DIRECTORY / WORKER_PLAN_REPORT_NAME,
        worker_root=worker_root,
        worker_state=worker_state,
        candidate=candidate,
        destination=destination,
        context=context,
    )
    if dict(document) != expected:
        raise ValueError("private candidate remediation execution report differs")


__all__: tuple[str, ...] = ()
