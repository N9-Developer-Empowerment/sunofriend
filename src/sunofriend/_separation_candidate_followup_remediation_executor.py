"""Execute the failed-review follow-up plan as separate blind-review candidates.

The executor starts from the exact first follow-up candidate, restores any
human-preferred v2 control region, runs only the plan's shifted source windows,
and materialises both declared edge hypotheses.  It never ranks the variants.
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
from ._separation_candidate_followup_remediation_plan import (
    POLICY_ID,
    REPORT_NAME as PLAN_REPORT_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
    _FALSE_EFFECTS as PLAN_FALSE_EFFECTS,
    _plan_private_candidate_followup_remediation,
)
from ._separation_candidate_join_remediation_executor import (
    WORKER_EXECUTION_DIRECTORY,
    WORKER_PLAN_DIRECTORY,
    _load_or_write_worker_plan,
)
from ._separation_candidate_join_remediation_review import _load_verified_inputs
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor import (
    REPORT_NAME as WORKER_REPORT_NAME,
    _execute_private_separation_full_song_join_remediation,
    _selected_attempt_record,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _apply_equal_power_patch,
    _audio_claim,
    _quantize_float_to_pcm24_int32,
    _read_pcm24_snapshot,
    _rename_directory_exclusive_at,
    _require_exclusive_directory_rename_available,
    _require_output_disjoint_from_inputs,
    _write_pcm24_exclusive,
)
from ._separation_full_song_join_remediation_plan import (
    REPORT_NAME as WORKER_PLAN_REPORT_NAME,
    _FALSE_PERMISSIONS,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import _load_stitch_report
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME
from ._separation_melroformer_native_attempt_darwin import (
    _run_private_melroformer_native_attempt_darwin,
)


SCHEMA = "sunofriend.private-separation-candidate-followup-remediation-execution.v1"
STATUS_INCOMPLETE = "shifted_context_followup_workers_incomplete_not_selected"
STATUS_COMPLETE = "shifted_context_followup_variants_complete_review_required"
REPORT_NAME = "private-separation-candidate-followup-remediation-execution.json"
CANDIDATES_DIRECTORY = "CANDIDATES"
CANDIDATE_REPORT_NAME = "private-separation-candidate-followup-remediation-candidates.json"
_ROLES = ("vocals", "instrumental")
_FULL_ROLES = (*_ROLES, "reconstruction")
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


def _execute_private_candidate_followup_remediation(
    plan_path: str | Path,
    *,
    targeted_review_result_path: str | Path,
    reviewed_export_path: str | Path,
    targeted_review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    stitch_package_dir: str | Path,
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
    """Resume shifted workers and publish two unranked candidate variants."""

    plan_snapshot = _load_private_json_snapshot(
        plan_path, "private follow-up remediation plan"
    )
    plan = plan_snapshot["document"]
    _require_plan_identity(plan)
    _require_plan_rederivation(
        plan,
        targeted_review_result_path=targeted_review_result_path,
        reviewed_export_path=reviewed_export_path,
        targeted_review_package_dir=targeted_review_package_dir,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
    )
    execution = Path(execution_dir).expanduser().absolute()
    v2_execution = Path(v2_execution_dir).expanduser().absolute()
    inputs = _load_verified_inputs(execution, v2_execution)
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    stitch_path = stitch_root / STITCH_REPORT_NAME
    stitch_snapshot = _load_private_json_snapshot(stitch_path, "private source stitch")
    stitch = _load_stitch_report(stitch_path)
    if stitch_snapshot["document"] != stitch or stitch["clock"] != plan["clock"]:
        raise ValueError("private follow-up source stitch differs")

    destination = Path(out_dir).expanduser().absolute()
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(execution, v2_execution, stitch_root),
        evidence_paths=(
            plan_snapshot["path"],
            Path(targeted_review_result_path).expanduser().absolute(),
            Path(reviewed_export_path).expanduser().absolute(),
            inputs["execution_snapshot"]["path"],
            inputs["candidate_snapshot"]["path"],
            inputs["v2_snapshot"]["path"],
            stitch_snapshot["path"],
        ),
    )
    if os.path.lexists(destination):
        _require_private_directory(destination, "private follow-up execution root")
    else:
        destination.mkdir(parents=True, mode=0o700)
        destination.chmod(0o700)

    worker_plan = _worker_adapter_plan(plan)
    context = {"stitch": stitch, "stitch_snapshot": stitch_snapshot}
    adapter_path = _load_or_write_worker_plan(
        destination,
        plan=worker_plan,
        plan_snapshot=plan_snapshot,
        context=context,
    )
    worker_root = destination / WORKER_EXECUTION_DIRECTORY
    worker = _execute_private_separation_full_song_join_remediation(
        adapter_path,
        package_dir=stitch_root,
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
                "planned_worker_windows": plan["summary"]["planned_model_call_count"],
                "verified_worker_windows": worker["summary"]["verified_windows"],
                "remaining_worker_windows": worker["summary"]["remaining_windows"],
                "candidate_audio_complete": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
        }

    candidates = _load_or_build_candidates(
        destination,
        plan=plan,
        plan_snapshot=plan_snapshot,
        inputs=inputs,
        worker_root=worker_root,
        worker_state=worker,
    )
    report_path = destination / REPORT_NAME
    expected = _execution_document(
        plan=plan,
        plan_snapshot=plan_snapshot,
        inputs=inputs,
        destination=destination,
        worker_root=worker_root,
        worker_state=worker,
        candidates=candidates,
    )
    if os.path.lexists(report_path):
        actual = _load_private_json_snapshot(
            report_path, "private follow-up remediation execution"
        )["document"]
        if actual != expected:
            raise ValueError("private follow-up remediation execution changed")
    else:
        _write_json_exclusive(report_path, expected)
    return {
        **expected,
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
    variants = plan.get("protocol", {}).get("candidate_variants")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("status") != PLAN_STATUS
        or plan.get("policy_id") != POLICY_ID
        or plan.get("document_sha256") != _document_sha256(plan)
        or plan.get("permissions") != _FALSE_PERMISSIONS
        or plan.get("effects") != PLAN_FALSE_EFFECTS
        or not isinstance(plan.get("windows"), list)
        or not isinstance(variants, list)
        or len(variants) != 2
        or len({item.get("variant_id") for item in variants}) != 2
        or plan.get("summary", {}).get("planned_model_call_count", 0) < 1
    ):
        raise ValueError("private follow-up remediation plan differs")


def _require_plan_rederivation(
    plan: Mapping[str, Any],
    *,
    targeted_review_result_path: str | Path,
    **arguments: Any,
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="sunofriend-followup-plan-check-"))
    temporary.chmod(0o700)
    try:
        expected = _plan_private_candidate_followup_remediation(
            targeted_review_result_path,
            **arguments,
            out=temporary / PLAN_REPORT_NAME,
        )
        expected.pop("report", None)
        if dict(plan) != expected:
            raise ValueError("private follow-up remediation plan derivation differs")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _worker_adapter_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    windows: list[dict[str, Any]] = []
    for window in plan["windows"]:
        model_roles = [
            role
            for role, action in window["role_actions"].items()
            if action["model_call_required"]
        ]
        if not model_roles:
            continue
        starts = {window["role_actions"][role]["patch_start_frame"] for role in model_roles}
        ends = {window["role_actions"][role]["patch_end_frame"] for role in model_roles}
        if len(starts) != 1 or len(ends) != 1:
            raise ValueError("private follow-up worker patch geometry differs")
        windows.append(
            {
                "window_index": window["window_index"],
                "boundary_index": window["boundary_index"],
                "source_start_frame": window["source_start_frame"],
                "source_end_frame": window["source_end_frame"],
                "patch_start_frame": starts.pop(),
                "patch_end_frame": ends.pop(),
                "patch_target_roles": sorted(model_roles),
            }
        )
    if len(windows) != plan["summary"]["planned_model_call_count"]:
        raise ValueError("private follow-up worker window count differs")
    return {
        "clock": deepcopy(plan["clock"]),
        "protocol": deepcopy(plan["protocol"]),
        "windows": windows,
        "document_sha256": plan["document_sha256"],
    }


def _load_or_build_candidates(
    destination: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    inputs: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> dict[str, Any]:
    root = destination / CANDIDATES_DIRECTORY
    if os.path.lexists(root):
        return _verify_candidates(
            root,
            plan=plan,
            plan_snapshot=plan_snapshot,
            inputs=inputs,
            worker_root=worker_root,
            worker_state=worker_state,
        )
    _require_exclusive_directory_rename_available()
    staging = destination / f".{CANDIDATES_DIRECTORY}.{secrets.token_hex(16)}.building"
    staging.mkdir(mode=0o700)
    try:
        _build_candidates(
            staging,
            plan=plan,
            plan_snapshot=plan_snapshot,
            inputs=inputs,
            worker_root=worker_root,
            worker_state=worker_state,
        )
        _verify_candidates(
            staging,
            plan=plan,
            plan_snapshot=plan_snapshot,
            inputs=inputs,
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
    return _verify_candidates(
        root,
        plan=plan,
        plan_snapshot=plan_snapshot,
        inputs=inputs,
        worker_root=worker_root,
        worker_state=worker_state,
    )


def _input_audio(inputs: Mapping[str, Any], role: str, *, base: bool) -> dict[str, Any]:
    document = inputs["candidate"] if base else inputs["v2"]
    path = inputs["candidate_paths"][role] if base else inputs["v2_paths"][role]
    return _read_pcm24_snapshot(
        path,
        document["artifacts"][role],
        expected_frames=int(document["clock"]["frames"]),
        label=f"private {'follow-up base' if base else 'v2 control'} {role}",
    )


def _worker_audio(
    window: Mapping[str, Any],
    role: str,
    *,
    worker_root: Path,
    worker_by_index: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    state = worker_by_index[int(window["window_index"])]
    selected = _selected_attempt_record(state)
    return _read_pcm24_snapshot(
        worker_root
        / selected["path"]
        / "staging"
        / "quarantine"
        / "STEMS"
        / f"{role}.wav",
        selected["outputs"][role],
        expected_frames=int(window["source_end_frame"])
        - int(window["source_start_frame"]),
        label=f"private shifted worker {window['window_index']} {role}",
    )


def _expected_variant(
    plan: Mapping[str, Any],
    variant: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import numpy as np

    base = {role: _input_audio(inputs, role, base=True) for role in _ROLES}
    v2 = {role: _input_audio(inputs, role, base=False) for role in _ROLES}
    result = {
        role: base[role]["samples"].astype("float64") / 2_147_483_648.0
        for role in _ROLES
    }
    worker_by_index = {
        int(item["window_index"]): item for item in worker_state["windows"]
    }
    patches: list[dict[str, Any]] = []
    for window in plan["windows"]:
        for role, action in window["role_actions"].items():
            start = int(action["patch_start_frame"])
            end = int(action["patch_end_frame"])
            record = {
                "variant_id": variant["variant_id"],
                "window_index": window["window_index"],
                "boundary_index": window["boundary_index"],
                "role": role,
                "action": action["action"],
                "patch_start_frame": start,
                "patch_end_frame": end,
            }
            if action["action"] == "revert_patch_to_v2_control":
                result[role][start:end] = (
                    v2[role]["samples"][start:end].astype("float64")
                    / 2_147_483_648.0
                )
                record.update(
                    {
                        "source_kind": "exact_v2_control",
                        "edge_blend_frames": 0,
                        "model_run": False,
                    }
                )
            else:
                if (
                    action["action"] == "edge_aware_reinference_and_blend_search"
                    and variant["failed_edge_source"]
                    == "exact_followup_candidate_patch"
                ):
                    replacement = (
                        base[role]["samples"][start:end].astype("float64")
                        / 2_147_483_648.0
                    )
                    edge_track = (
                        v2[role]["samples"].astype("float64")
                        / 2_147_483_648.0
                    )
                    blend = int(variant["failed_edge_blend_frames"])
                    _apply_equal_power_patch(
                        edge_track,
                        replacement,
                        start=start,
                        end=end,
                        blend_frames=blend,
                        np=np,
                    )
                    result[role][start:end] = edge_track[start:end]
                    record.update(
                        {
                            "source_kind": "followup_centre_with_extended_v2_edge",
                            "edge_blend_frames": blend,
                            "model_run": False,
                        }
                    )
                else:
                    worker = _worker_audio(
                        window,
                        role,
                        worker_root=worker_root,
                        worker_by_index=worker_by_index,
                    )
                    local_start = start - int(window["source_start_frame"])
                    local_end = end - int(window["source_start_frame"])
                    replacement = (
                        worker["samples"][local_start:local_end].astype("float64")
                        / 2_147_483_648.0
                    )
                    blend = (
                        int(variant["failed_edge_blend_frames"])
                        if action["action"]
                        == "edge_aware_reinference_and_blend_search"
                        else int(action["edge_blend_frames"])
                    )
                    _apply_equal_power_patch(
                        result[role],
                        replacement,
                        start=start,
                        end=end,
                        blend_frames=blend,
                        np=np,
                    )
                    record.update(
                        {
                            "source_kind": "shifted_context_worker",
                            "source_start_frame": window["source_start_frame"],
                            "source_end_frame": window["source_end_frame"],
                            "worker_local_patch_start_frame": local_start,
                            "worker_local_patch_end_frame": local_end,
                            "worker_output_sha256": worker["sha256"],
                            "edge_blend_frames": blend,
                            "model_run": True,
                        }
                    )
            patches.append(record)
    return result, patches


def _build_candidates(
    root: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    inputs: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> dict[str, Any]:
    import numpy as np

    variants: list[dict[str, Any]] = []
    total_frames = int(plan["clock"]["frames"])
    for definition in plan["protocol"]["candidate_variants"]:
        variant_root = root / definition["variant_id"]
        variant_root.mkdir(mode=0o700)
        expected, patches = _expected_variant(
            plan,
            definition,
            inputs=inputs,
            worker_root=worker_root,
            worker_state=worker_state,
        )
        artifacts: dict[str, Any] = {}
        observed: dict[str, Any] = {}
        for role in _ROLES:
            peak = float(np.max(np.abs(expected[role]))) if expected[role].size else 0.0
            if not math.isfinite(peak) or peak > 1.0:
                raise ValueError("private follow-up candidate role would clip")
            path = variant_root / f"{role}.wav"
            _write_pcm24_exclusive(path, expected[role])
            observed[role] = _read_pcm24_snapshot(
                path,
                None,
                expected_frames=total_frames,
                label=f"private follow-up variant {definition['variant_id']} {role}",
            )
            artifacts[role] = _audio_claim(path, root=variant_root, snapshot=observed[role])
        reconstruction_float = (
            observed["vocals"]["samples"].astype("float64")
            + observed["instrumental"]["samples"].astype("float64")
        ) / 2_147_483_648.0
        pre_peak = float(np.max(np.abs(reconstruction_float))) if total_frames else 0.0
        gain = min(1.0, 0.98 / pre_peak) if pre_peak else 1.0
        reconstruction_path = variant_root / "reconstruction.wav"
        _write_pcm24_exclusive(reconstruction_path, reconstruction_float * gain)
        reconstruction = _read_pcm24_snapshot(
            reconstruction_path,
            None,
            expected_frames=total_frames,
            label=f"private follow-up variant {definition['variant_id']} reconstruction",
        )
        artifacts["reconstruction"] = _audio_claim(
            reconstruction_path, root=variant_root, snapshot=reconstruction
        )
        artifacts["reconstruction"].update(
            {"pre_gain_peak": round(pre_peak, 9), "global_gain": round(gain, 9)}
        )
        variants.append(
            {
                "variant_id": definition["variant_id"],
                "definition": deepcopy(definition),
                "artifacts": artifacts,
                "patches": sorted(
                    patches, key=lambda item: (item["boundary_index"], item["role"])
                ),
                "review_status": "not_reviewed",
                "selected": False,
            }
        )
    document: dict[str, Any] = {
        "schema": "sunofriend.private-separation-candidate-followup-remediation-candidates.v1",
        "status": "candidate_variants_complete_review_required",
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "followup_remediation_plan_sha256": plan_snapshot["sha256"],
            "followup_remediation_plan_document_sha256": plan["document_sha256"],
            "worker_execution_state_sha256": worker_state["state_sha256"],
            "followup_candidate_report_sha256": inputs["candidate_snapshot"]["sha256"],
            "v2_execution_report_sha256": inputs["v2_snapshot"]["sha256"],
        },
        "clock": deepcopy(plan["clock"]),
        "protocol": deepcopy(plan["protocol"]),
        "variants": variants,
        "summary": {
            "candidate_variant_count": len(variants),
            "planned_model_call_count": plan["summary"]["planned_model_call_count"],
            "automatic_winner_selected": False,
            "private_listener_notes_copied": False,
        },
        "readiness": {
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS_COMPLETE),
        "limitations": [
            "The two variants are hypotheses and have no automatic ranking.",
            "A fresh blind targeted review must compare every changed region.",
            "No public product route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    _write_json_exclusive(root / CANDIDATE_REPORT_NAME, document)
    return document


def _verify_candidates(
    root: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    inputs: Mapping[str, Any],
    worker_root: Path,
    worker_state: Mapping[str, Any],
) -> dict[str, Any]:
    import numpy as np

    _require_private_directory(root, "private follow-up candidate root")
    snapshot = _load_private_json_snapshot(
        root / CANDIDATE_REPORT_NAME, "private follow-up candidate variants"
    )
    document = snapshot["document"]
    if (
        document.get("schema")
        != "sunofriend.private-separation-candidate-followup-remediation-candidates.v1"
        or document.get("status") != "candidate_variants_complete_review_required"
        or document.get("policy_id") != POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != _EFFECTS_COMPLETE
        or document.get("bindings", {}).get("followup_remediation_plan_sha256")
        != plan_snapshot["sha256"]
        or len(document.get("variants", [])) != 2
    ):
        raise ValueError("private follow-up candidate variants differ")
    definitions = {
        item["variant_id"]: item for item in plan["protocol"]["candidate_variants"]
    }
    total_frames = int(plan["clock"]["frames"])
    for variant in document["variants"]:
        definition = definitions[variant["variant_id"]]
        expected, patches = _expected_variant(
            plan,
            definition,
            inputs=inputs,
            worker_root=worker_root,
            worker_state=worker_state,
        )
        if variant["patches"] != sorted(
            patches, key=lambda item: (item["boundary_index"], item["role"])
        ):
            raise ValueError("private follow-up candidate patch evidence differs")
        observed: dict[str, Any] = {}
        variant_root = root / variant["variant_id"]
        _require_private_directory(variant_root, "private follow-up variant root")
        for role in _FULL_ROLES:
            claim = variant["artifacts"][role]
            observed[role] = _read_pcm24_snapshot(
                variant_root / claim["path"],
                claim,
                expected_frames=total_frames,
                label=f"private follow-up verified {variant['variant_id']} {role}",
            )
        for role in _ROLES:
            if not bool(
                np.array_equal(
                    observed[role]["samples"],
                    _quantize_float_to_pcm24_int32(expected[role], np=np),
                )
            ):
                raise ValueError("private follow-up candidate role audio differs")
        reconstruction_float = (
            observed["vocals"]["samples"].astype("float64")
            + observed["instrumental"]["samples"].astype("float64")
        ) / 2_147_483_648.0
        peak = float(np.max(np.abs(reconstruction_float))) if total_frames else 0.0
        gain = min(1.0, 0.98 / peak) if peak else 1.0
        if not bool(
            np.array_equal(
                observed["reconstruction"]["samples"],
                _quantize_float_to_pcm24_int32(reconstruction_float * gain, np=np),
            )
        ):
            raise ValueError("private follow-up reconstruction differs")
    return document


def _execution_document(
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    inputs: Mapping[str, Any],
    destination: Path,
    worker_root: Path,
    worker_state: Mapping[str, Any],
    candidates: Mapping[str, Any],
) -> dict[str, Any]:
    adapter = _load_private_json_snapshot(
        destination / WORKER_PLAN_DIRECTORY / WORKER_PLAN_REPORT_NAME,
        "private follow-up worker adapter",
    )
    worker = _load_private_json_snapshot(
        worker_root / WORKER_REPORT_NAME, "private follow-up worker execution"
    )
    candidate_path = destination / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS_COMPLETE,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "followup_remediation_plan_sha256": plan_snapshot["sha256"],
            "followup_remediation_plan_document_sha256": plan["document_sha256"],
            "worker_adapter_plan_sha256": adapter["sha256"],
            "worker_execution_report_sha256": worker["sha256"],
            "worker_execution_state_sha256": worker_state["state_sha256"],
            "candidate_report_sha256": _sha256(candidate_path),
            "candidate_document_sha256": candidates["document_sha256"],
            "followup_candidate_report_sha256": inputs["candidate_snapshot"]["sha256"],
            "v2_execution_report_sha256": inputs["v2_snapshot"]["sha256"],
        },
        "clock": deepcopy(plan["clock"]),
        "protocol": deepcopy(plan["protocol"]),
        "summary": {
            "planned_model_call_count": plan["summary"]["planned_model_call_count"],
            "executed_model_call_count": plan["summary"]["planned_model_call_count"],
            "candidate_variant_count": len(candidates["variants"]),
            "automatic_winner_selected": False,
            "private_listener_notes_copied": False,
        },
        "readiness": {
            "worker_runs_complete": True,
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS_COMPLETE),
        "limitations": [
            "Candidate creation is not preference, repair success or separator acceptance.",
            "Both variants require a fresh blind targeted review.",
            "No public CLI, TUI, Simple, Studio or source-graph route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


__all__: tuple[str, ...] = ()
