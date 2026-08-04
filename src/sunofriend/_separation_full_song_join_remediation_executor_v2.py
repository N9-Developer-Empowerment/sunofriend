"""Build one model-free expanded-context join-remediation candidate.

This private-development executor consumes the complete evidence chain used to
derive a v2 plan.  It independently re-derives that plan, starts from the
verified v1 candidate audio, and reuses only the already sealed v1 worker
outputs.  It has no model runner, runtime, checkpoint or device interface.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_plan_v2 import (
    PATCH_DURATION_FRAMES,
    PATCH_HALF_FRAMES,
    POLICY_ID,
    REPORT_NAME as PLAN_REPORT_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
    TARGET_SAMPLE_RATE,
    _plan_private_separation_full_song_join_remediation_v2,
    _private_child_regular,
    _require_disjoint_patch_regions,
    _verified_v1_patch_inventory,
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
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES


SCHEMA = "sunofriend.private-separation-full-song-join-remediation-execution.v2"
STATUS = "model_free_expanded_context_candidate_complete_review_required"
REPORT_NAME = "private-separation-full-song-join-remediation-execution-v2.json"
CANDIDATES_DIRECTORY = "CANDIDATES"
_ROLES = ("vocals", "instrumental")
_FULL_SONG_ROLES = (*_ROLES, "reconstruction")
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}
_EFFECTS = {
    "candidate_audio_created": True,
    "model_run": False,
    "publication_state_mutated": False,
    "raw_stitch_mutated": False,
    "review_evidence_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "v1_candidate_audio_mutated": False,
    "v1_worker_output_mutated": False,
}
_REPORT_KEYS = {
    "schema",
    "status",
    "evidence_scope",
    "policy_id",
    "bindings",
    "clock",
    "protocol",
    "windows",
    "artifacts",
    "summary",
    "readiness",
    "interpretation",
    "permissions",
    "effects",
    "limitations",
    "document_sha256",
}


def _execute_private_separation_full_song_join_remediation_v2(
    v2_plan_path: str | Path,
    *,
    package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    v1_execution_report_path: str | Path,
    v1_candidate_report_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Build and exclusively publish one review-required v2 candidate."""

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"private v2 remediation output exists: {destination}")

    plan_snapshot = _load_private_json_snapshot(
        v2_plan_path, "private v2 join-remediation plan"
    )
    plan = plan_snapshot["document"]
    _require_plan_identity(plan_snapshot)

    evidence_arguments = {
        "package_dir": package_dir,
        "full_song_review_result_path": full_song_review_result_path,
        "v1_plan_path": v1_plan_path,
        "v1_execution_report_path": v1_execution_report_path,
        "v1_candidate_report_path": v1_candidate_report_path,
        "resolved_join_review_result_path": resolved_join_review_result_path,
        "publication_readiness_path": publication_readiness_path,
    }
    _require_plan_rederivation(plan, **evidence_arguments)

    inputs = _load_execution_inputs(
        plan,
        package_dir=package_dir,
        v1_plan_path=v1_plan_path,
        v1_execution_report_path=v1_execution_report_path,
        v1_candidate_report_path=v1_candidate_report_path,
    )
    evidence_paths = (
        plan_snapshot["path"],
        Path(full_song_review_result_path).expanduser().absolute(),
        inputs["v1_plan_snapshot"]["path"],
        inputs["execution_snapshot"]["path"],
        inputs["candidate_snapshot"]["path"],
        Path(resolved_join_review_result_path).expanduser().absolute(),
        Path(publication_readiness_path).expanduser().absolute(),
        inputs["stitch_snapshot"]["path"],
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(
            inputs["package"],
            inputs["execution_root"],
            *(path.parent for path in evidence_paths),
        ),
        evidence_paths=evidence_paths,
    )
    _require_execution_geometry(plan, inputs)

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=parent)
    )
    staging.chmod(0o700)
    try:
        document = _build_staged_candidate(
            staging,
            plan=plan,
            plan_snapshot=plan_snapshot,
            inputs=inputs,
        )
        _verify_staged_candidate(staging, document, inputs=inputs)

        # Re-derive the human target set and recheck every bound v1 JSON/WAV
        # immediately before anything becomes visible at the requested path.
        _require_snapshot_unchanged(plan_snapshot, "private v2 join-remediation plan")
        _require_plan_rederivation(plan, **evidence_arguments)
        _reverify_input_audio(inputs)

        _publish_verified_candidate(staging, destination, document)
        _verify_published_candidate(destination, document, inputs=inputs)

        # The report is the completion marker.  Recheck the complete chain one
        # final time after audio publication, then publish it exclusively.
        _require_snapshot_unchanged(plan_snapshot, "private v2 join-remediation plan")
        _require_plan_rederivation(plan, **evidence_arguments)
        _reverify_input_audio(inputs)
        _verify_published_candidate(destination, document, inputs=inputs)
        _write_json_exclusive(destination / REPORT_NAME, document)
        _verify_report(destination / REPORT_NAME, document)
        _fsync_directory(destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "output_directory": str(destination),
    }


def _require_plan_identity(snapshot: Mapping[str, Any]) -> None:
    path = snapshot["path"]
    plan = snapshot["document"]
    if (
        path.name != PLAN_REPORT_NAME
        or plan.get("schema") != PLAN_SCHEMA
        or plan.get("status") != PLAN_STATUS
        or plan.get("evidence_scope") != "private_development_only"
        or plan.get("policy_id") != POLICY_ID
        or plan.get("document_sha256") != _document_sha256(plan)
        or plan.get("permissions") != _FALSE_PERMISSIONS
        or not _all_false(plan.get("effects"))
        or not isinstance(plan.get("windows"), list)
        or not plan["windows"]
    ):
        raise ValueError("private v2 join-remediation plan identity differs")


def _require_plan_rederivation(
    plan: Mapping[str, Any],
    *,
    package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    v1_execution_report_path: str | Path,
    v1_candidate_report_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
) -> None:
    """Rebuild the deterministic plan from its whole authority chain."""

    temporary_root = Path(tempfile.mkdtemp(prefix=".sunofriend-v2-rederive-"))
    temporary_root.chmod(0o700)
    try:
        expected = _plan_private_separation_full_song_join_remediation_v2(
            package_dir,
            full_song_review_result_path=full_song_review_result_path,
            v1_plan_path=v1_plan_path,
            v1_execution_report_path=v1_execution_report_path,
            v1_candidate_report_path=v1_candidate_report_path,
            resolved_join_review_result_path=resolved_join_review_result_path,
            publication_readiness_path=publication_readiness_path,
            out=temporary_root / PLAN_REPORT_NAME,
        )
        expected.pop("report", None)
        if dict(plan) != expected:
            raise ValueError("private v2 join-remediation plan derivation differs")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def _load_execution_inputs(
    plan: Mapping[str, Any],
    *,
    package_dir: str | Path,
    v1_plan_path: str | Path,
    v1_execution_report_path: str | Path,
    v1_candidate_report_path: str | Path,
) -> dict[str, Any]:
    package = Path(package_dir).expanduser().absolute()
    _require_private_directory(package, "private stitch package")
    stitch_path = package / STITCH_REPORT_NAME
    stitch_snapshot = _load_private_json_snapshot(
        stitch_path, "private full-song stitch report"
    )
    stitch = _load_stitch_report(stitch_path)
    if stitch != stitch_snapshot["document"]:
        raise ValueError("private full-song stitch report changed")
    _verify_stitch_audio(package, stitch)

    v1_plan_snapshot = _load_private_json_snapshot(
        v1_plan_path, "private v1 join-remediation plan"
    )
    execution_snapshot = _load_private_json_snapshot(
        v1_execution_report_path, "private v1 join-remediation execution"
    )
    candidate_snapshot = _load_private_json_snapshot(
        v1_candidate_report_path, "private v1 join-remediation candidate report"
    )
    execution = execution_snapshot["document"]
    candidate = candidate_snapshot["document"]
    execution_root = execution_snapshot["path"].parent
    if candidate_snapshot["path"].parent != execution_root:
        raise ValueError("private v1 candidate root differs")
    patch_inventory = _verified_v1_patch_inventory(
        candidate,
        execution=execution,
        execution_root=execution_root,
    )

    bindings = plan["bindings"]
    if (
        stitch_snapshot["sha256"] != bindings["stitch_report_sha256"]
        or stitch["document_sha256"] != bindings["stitch_document_sha256"]
        or v1_plan_snapshot["sha256"] != bindings["v1_plan_sha256"]
        or v1_plan_snapshot["document"]["document_sha256"]
        != bindings["v1_plan_document_sha256"]
        or execution_snapshot["sha256"] != bindings["v1_execution_report_sha256"]
        or execution["state_sha256"] != bindings["v1_execution_state_sha256"]
        or candidate_snapshot["sha256"] != bindings["v1_candidate_report_sha256"]
        or candidate["document_sha256"] != bindings["v1_candidate_document_sha256"]
    ):
        raise ValueError("private v2 execution input binding differs")

    candidate_paths = {
        role: _private_child_regular(
            execution_root,
            candidate["artifacts"][role]["path"],
            f"private v1 {role} candidate audio",
        )
        for role in _ROLES
    }
    base_audio = {
        role: _read_pcm24_snapshot(
            candidate_paths[role],
            candidate["artifacts"][role],
            expected_frames=int(stitch["clock"]["frames"]),
            label=f"private v1 {role} candidate audio",
        )
        for role in _ROLES
    }
    worker_audio: dict[tuple[int, str], dict[str, Any]] = {}
    for item in plan["windows"]:
        key = (int(item["boundary_index"]), str(item["patch_target_role"]))
        patch = patch_inventory.get(key)
        if patch is None:
            raise ValueError("private v2 target has no verified v1 worker output")
        worker_audio[key] = _read_pcm24_snapshot(
            patch["worker_output_path"],
            {
                "sha256": patch["worker_output_sha256"],
                "bytes": patch["worker_output_bytes"],
            },
            expected_frames=int(patch["worker_output_frames"]),
            label=f"private v1 {key[1]} worker output",
        )

    return {
        "package": package,
        "stitch": stitch,
        "stitch_snapshot": stitch_snapshot,
        "v1_plan_snapshot": v1_plan_snapshot,
        "execution_snapshot": execution_snapshot,
        "candidate_snapshot": candidate_snapshot,
        "execution": execution,
        "candidate": candidate,
        "execution_root": execution_root,
        "patch_inventory": patch_inventory,
        "candidate_paths": candidate_paths,
        "base_audio": base_audio,
        "worker_audio": worker_audio,
    }


def _require_execution_geometry(
    plan: Mapping[str, Any], inputs: Mapping[str, Any]
) -> None:
    windows = plan["windows"]
    _require_disjoint_patch_regions(windows)
    target_keys = {
        (int(item["boundary_index"]), str(item["patch_target_role"]))
        for item in windows
    }
    if len(target_keys) != len(windows):
        raise ValueError("private v2 target inventory contains duplicates")
    for item in windows:
        role = item["patch_target_role"]
        source_start = _exact_int(item.get("source_start_frame"), "source start")
        source_end = _exact_int(item.get("source_end_frame"), "source end")
        patch_start = _exact_int(item.get("patch_start_frame"), "patch start")
        patch_end = _exact_int(item.get("patch_end_frame"), "patch end")
        local_start = _exact_int(
            item.get("worker_local_patch_start_frame"), "worker local patch start"
        )
        local_end = _exact_int(
            item.get("worker_local_patch_end_frame"), "worker local patch end"
        )
        if (
            role not in _ROLES
            or source_end - source_start != MAXIMUM_EXCERPT_FRAMES
            or patch_end - patch_start != PATCH_DURATION_FRAMES
            or patch_start != int(item["boundary_frame"]) - PATCH_HALF_FRAMES
            or patch_end != int(item["boundary_frame"]) + PATCH_HALF_FRAMES
            or local_start != patch_start - source_start
            or local_end != patch_end - source_start
            or local_end - local_start != PATCH_DURATION_FRAMES
            or local_start < 0
            or local_end > MAXIMUM_EXCERPT_FRAMES
        ):
            raise ValueError("private v2 expanded-window coverage differs")
        key = (int(item["boundary_index"]), role)
        worker = inputs["worker_audio"].get(key)
        if worker is None or len(worker["samples"]) != MAXIMUM_EXCERPT_FRAMES:
            raise ValueError("private v2 worker geometry differs")

    for key, patch in inputs["patch_inventory"].items():
        if key in target_keys:
            continue
        for target in windows:
            if target["patch_target_role"] != key[1]:
                continue
            if int(target["patch_start_frame"]) < int(patch["end_frame"]) and int(
                patch["start_frame"]
            ) < int(target["patch_end_frame"]):
                raise ValueError(
                    "private v2 target overlaps a preserved same-role v1 patch"
                )


def _build_staged_candidate(
    staging: Path,
    *,
    plan: Mapping[str, Any],
    plan_snapshot: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    import numpy as np

    candidate_root = staging / CANDIDATES_DIRECTORY
    candidate_root.mkdir(mode=0o700)
    total_frames = int(plan["clock"]["frames"])
    edge_blend = int(plan["protocol"]["edge_blend_frames"])
    artifacts: dict[str, Any] = {}
    window_records: list[dict[str, Any]] = []
    written_samples: dict[str, Any] = {}

    for role in _ROLES:
        base_int32 = inputs["base_audio"][role]["samples"]
        candidate = base_int32.astype("float64") / 2_147_483_648.0
        role_windows = [
            item for item in plan["windows"] if item["patch_target_role"] == role
        ]
        ranges: list[tuple[int, int]] = []
        for item in role_windows:
            key = (int(item["boundary_index"]), role)
            worker_int32 = inputs["worker_audio"][key]["samples"]
            local_start = int(item["worker_local_patch_start_frame"])
            local_end = int(item["worker_local_patch_end_frame"])
            start = int(item["patch_start_frame"])
            end = int(item["patch_end_frame"])
            replacement = (
                worker_int32[local_start:local_end].astype("float64") / 2_147_483_648.0
            )
            _apply_equal_power_patch(
                candidate,
                replacement,
                start=start,
                end=end,
                blend_frames=edge_blend,
                np=np,
            )
            ranges.append((start, end))

        peak = float(np.max(np.abs(candidate))) if candidate.size else 0.0
        if not math.isfinite(peak) or peak > 1.0:
            raise ValueError("private v2 candidate role would clip")
        target = candidate_root / f"{role}.wav"
        _write_pcm24_exclusive(target, candidate)
        observed = _read_pcm24_snapshot(
            target,
            None,
            expected_frames=total_frames,
            label=f"private v2 staged {role} candidate",
        )
        samples = observed["samples"]
        outside_exact = _outside_ranges_exact(
            base_int32,
            samples,
            ranges=ranges,
            np=np,
        )
        preserved = _preserved_patch_checks(
            role,
            base_int32=base_int32,
            candidate_int32=samples,
            target_keys={(int(item["boundary_index"]), role) for item in role_windows},
            patch_inventory=inputs["patch_inventory"],
            np=np,
        )
        for item in role_windows:
            key = (int(item["boundary_index"]), role)
            start = int(item["patch_start_frame"])
            end = int(item["patch_end_frame"])
            local_start = int(item["worker_local_patch_start_frame"])
            local_end = int(item["worker_local_patch_end_frame"])
            worker = inputs["worker_audio"][key]["samples"]
            changed = int(np.count_nonzero(samples[start:end] != base_int32[start:end]))
            if changed < 1:
                raise ValueError("private v2 target made no PCM24 sample change")
            if not bool(
                np.array_equal(
                    samples[start + edge_blend : end - edge_blend],
                    worker[local_start + edge_blend : local_end - edge_blend],
                )
            ):
                raise ValueError("private v2 target interior differs from worker slice")
            window_records.append(
                {
                    "window_index": item["window_index"],
                    "boundary_index": item["boundary_index"],
                    "role": role,
                    "source_start_frame": item["source_start_frame"],
                    "source_end_frame": item["source_end_frame"],
                    "patch_start_frame": start,
                    "patch_end_frame": end,
                    "worker_local_patch_start_frame": local_start,
                    "worker_local_patch_end_frame": local_end,
                    "edge_blend_frames": edge_blend,
                    "v1_worker_output_sha256": inputs["worker_audio"][key]["sha256"],
                    "changed_pcm24_sample_values": changed,
                    "interior_pcm24_samples_match_worker": True,
                    "outside_target_pcm24_samples_match_v1_candidate": True,
                    "model_run": False,
                }
            )
        artifact = _audio_claim(target, root=staging, snapshot=observed)
        artifact.update(
            {
                "v1_candidate_base_sha256": inputs["base_audio"][role]["sha256"],
                "peak_before_write": round(peak, 9),
                "target_patch_count": len(role_windows),
                "outside_v2_target_pcm24_samples_exact": outside_exact,
                "preserved_v1_patch_checks": preserved,
            }
        )
        artifacts[role] = artifact
        written_samples[role] = samples

    reconstruction_float = (
        written_samples["vocals"].astype("float64")
        + written_samples["instrumental"].astype("float64")
    ) / 2_147_483_648.0
    pre_gain_peak = (
        float(np.max(np.abs(reconstruction_float)))
        if reconstruction_float.size
        else 0.0
    )
    if not math.isfinite(pre_gain_peak):
        raise ValueError("private v2 diagnostic reconstruction is not finite")
    global_gain = min(1.0, 0.98 / pre_gain_peak) if pre_gain_peak else 1.0
    reconstruction_float *= global_gain
    reconstruction = candidate_root / "reconstruction.wav"
    _write_pcm24_exclusive(reconstruction, reconstruction_float)
    reconstruction_observed = _read_pcm24_snapshot(
        reconstruction,
        None,
        expected_frames=total_frames,
        label="private v2 staged diagnostic reconstruction",
    )
    expected_reconstruction = _quantize_float_to_pcm24_int32(
        reconstruction_float, np=np
    )
    if not bool(
        np.array_equal(reconstruction_observed["samples"], expected_reconstruction)
    ):
        delta = reconstruction_observed["samples"].astype(
            "int64"
        ) - expected_reconstruction.astype("int64")
        raise ValueError(
            "private v2 reconstruction PCM24 projection differs "
            f"at {int(np.count_nonzero(delta))} values; "
            f"delta range {int(np.min(delta))}..{int(np.max(delta))}"
        )
    reconstruction_claim = _audio_claim(
        reconstruction,
        root=staging,
        snapshot=reconstruction_observed,
    )
    reconstruction_claim.update(
        {
            "source_role_sha256": {role: artifacts[role]["sha256"] for role in _ROLES},
            "pre_gain_peak": round(pre_gain_peak, 9),
            "global_gain": round(global_gain, 9),
            "attenuation_only": True,
            "canonical_pcm24_projection_verified": True,
        }
    )
    artifacts["reconstruction"] = reconstruction_claim

    window_records.sort(key=lambda item: (item["boundary_index"], item["role"]))
    preserved_pairs = sorted(
        set(inputs["patch_inventory"])
        - {
            (int(item["boundary_index"]), str(item["patch_target_role"]))
            for item in plan["windows"]
        }
    )
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "v2_plan_sha256": plan_snapshot["sha256"],
            "v2_plan_document_sha256": plan["document_sha256"],
            **dict(plan["bindings"]),
        },
        "clock": dict(plan["clock"]),
        "protocol": dict(plan["protocol"]),
        "windows": window_records,
        "artifacts": artifacts,
        "summary": {
            "targeted_boundary_role_pair_count": len(window_records),
            "preserved_v1_boundary_role_pair_count": len(preserved_pairs),
            "planned_model_call_count": 0,
            "executed_model_call_count": 0,
            "reused_sealed_v1_worker_output_count": len(window_records),
            "candidate_role_count": 3,
            "v1_candidate_is_assembly_base": True,
            "v1_candidate_source_hashes_unchanged": True,
            "private_listener_notes_copied": False,
        },
        "readiness": {
            "v2_candidate_audio_complete": True,
            "v2_candidate_integrity_verified": True,
            "v2_candidate_review_complete": False,
            "new_candidate_full_song_review_complete": False,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "expanded_context_is_repair_success": False,
            "candidate_integrity_is_musical_quality": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_EFFECTS),
        "limitations": [
            "This executor reused sealed v1 worker audio and ran no model.",
            "Only the human-equivalent boundary-role pairs in the exact re-derived v2 plan were repatched.",
            "PCM24 equality proves sample preservation, not musical improvement.",
            "The diagnostic reconstruction is derived from the written v2 role WAVs and may use disclosed attenuation.",
            "Blind v1-versus-v2 boundary review, patch-edge checks, a new candidate-bound full-song review and alignment remain required.",
            "No public CLI, TUI, Simple, Studio or source-graph route is enabled.",
            "Inputs are reverified before report publication but descriptors are not held for the whole operation; the private evidence trees must remain quiescent.",
        ],
    }
    if set(document) != _REPORT_KEYS - {"document_sha256"}:
        raise AssertionError("private v2 execution report construction differs")
    document["document_sha256"] = _document_sha256(document)
    return document


def _verify_staged_candidate(
    staging: Path,
    document: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
) -> None:
    _verify_candidate_tree(staging, document, inputs=inputs)


def _verify_published_candidate(
    destination: Path,
    document: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
) -> None:
    _require_private_directory(destination, "private v2 remediation output")
    _verify_candidate_tree(destination, document, inputs=inputs)


def _verify_candidate_tree(
    root: Path,
    document: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
) -> None:
    import numpy as np

    if (
        set(document) != _REPORT_KEYS
        or document.get("schema") != SCHEMA
        or document.get("status") != STATUS
        or document.get("policy_id") != POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != _EFFECTS
    ):
        raise ValueError("private v2 execution report differs")
    candidate_root = root / CANDIDATES_DIRECTORY
    _require_private_directory(candidate_root, "private v2 candidate root")
    observed: dict[str, Any] = {}
    for role in _FULL_SONG_ROLES:
        claim = document["artifacts"][role]
        path = _private_child_regular(root, claim["path"], f"private v2 {role} audio")
        observed[role] = _read_pcm24_snapshot(
            path,
            claim,
            expected_frames=int(document["clock"]["frames"]),
            label=f"private v2 {role} audio",
        )

    windows_by_role = {
        role: [row for row in document["windows"] if row["role"] == role]
        for role in _ROLES
    }
    for role in _ROLES:
        base = inputs["base_audio"][role]["samples"]
        samples = observed[role]["samples"]
        ranges = [
            (int(row["patch_start_frame"]), int(row["patch_end_frame"]))
            for row in windows_by_role[role]
        ]
        _outside_ranges_exact(base, samples, ranges=ranges, np=np)
        for row in windows_by_role[role]:
            key = (int(row["boundary_index"]), role)
            worker = inputs["worker_audio"][key]["samples"]
            start = int(row["patch_start_frame"])
            end = int(row["patch_end_frame"])
            local_start = int(row["worker_local_patch_start_frame"])
            local_end = int(row["worker_local_patch_end_frame"])
            blend = int(row["edge_blend_frames"])
            if not bool(
                np.array_equal(
                    samples[start + blend : end - blend],
                    worker[local_start + blend : local_end - blend],
                )
            ):
                raise ValueError("private v2 published target interior differs")

    reconstruction_float = (
        observed["vocals"]["samples"].astype("float64")
        + observed["instrumental"]["samples"].astype("float64")
    ) / 2_147_483_648.0
    gain = float(document["artifacts"]["reconstruction"]["global_gain"])
    # Stored gain is rounded to nine places; the unrounded value must be
    # recoverable from the stored written roles for exact projection.
    pre_peak = (
        float(np.max(np.abs(reconstruction_float)))
        if reconstruction_float.size
        else 0.0
    )
    exact_gain = min(1.0, 0.98 / pre_peak) if pre_peak else 1.0
    if not math.isclose(gain, exact_gain, rel_tol=0.0, abs_tol=5.0e-10):
        raise ValueError("private v2 reconstruction gain differs")
    expected = _quantize_float_to_pcm24_int32(
        reconstruction_float * exact_gain,
        np=np,
    )
    if not bool(np.array_equal(observed["reconstruction"]["samples"], expected)):
        raise ValueError("private v2 reconstruction audio differs")


def _publish_verified_candidate(
    staging: Path,
    destination: Path,
    document: Mapping[str, Any],
) -> None:
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as error:
        raise FileExistsError(
            f"private v2 remediation output exists: {destination}"
        ) from error
    _fsync_directory(destination.parent)
    candidate_root = destination / CANDIDATES_DIRECTORY
    candidate_root.mkdir(mode=0o700)
    for role in _FULL_SONG_ROLES:
        relative = document["artifacts"][role]["path"]
        source = _private_child_regular(staging, relative, "private v2 staged audio")
        target = destination / relative
        _copy_regular_exclusive(source, target)
    _fsync_directory(candidate_root)
    _fsync_directory(destination)
    _fsync_directory(destination.parent)


def _write_pcm24_exclusive(path: Path, samples: Any) -> None:
    """Write one staged WAV through the exact exclusively-created descriptor."""

    import soundfile

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError(
            "private v2 audio cannot be written without no-follow support"
        )
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    created = os.fstat(descriptor)
    try:
        os.set_inheritable(descriptor, False)
        os.fchmod(descriptor, 0o600)
        with soundfile.SoundFile(
            descriptor,
            mode="w",
            samplerate=TARGET_SAMPLE_RATE,
            channels=2,
            subtype="PCM_24",
            format="WAV",
            closefd=False,
        ) as handle:
            handle.write(samples)
            handle.flush()
        os.fsync(descriptor)
        final_state = os.fstat(descriptor)
        visible = path.lstat()
        if (
            _owner_identity(created) != _owner_identity(final_state)
            or (visible.st_dev, visible.st_ino) != (created.st_dev, created.st_ino)
            or final_state.st_size <= 0
        ):
            raise RuntimeError("private v2 staged audio identity changed")
    finally:
        os.close(descriptor)


def _copy_regular_exclusive(source: Path, target: Path) -> None:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeError(
            "private v2 audio cannot be copied without no-follow support"
        )
    source_fd = os.open(
        source,
        os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.set_inheritable(source_fd, False)
        source_state = os.fstat(source_fd)
        target_fd = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | no_follow
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            os.set_inheritable(target_fd, False)
            os.fchmod(target_fd, 0o600)
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                offset = 0
                while offset < len(block):
                    written = os.write(target_fd, block[offset:])
                    if written <= 0:
                        raise RuntimeError("private v2 audio copy made no progress")
                    offset += written
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
        if _snapshot_identity(source_state) != _snapshot_identity(os.fstat(source_fd)):
            raise ValueError("private v2 staged audio changed during publication")
    finally:
        os.close(source_fd)


def _read_pcm24_snapshot(
    path: Path,
    claim: Mapping[str, Any] | None,
    *,
    expected_frames: int,
    label: str,
) -> dict[str, Any]:
    import numpy as np
    import soundfile

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ValueError(f"{label} cannot be opened without symbolic-link protection")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o077
            or before.st_size <= 0
        ):
            raise ValueError(f"{label} is not an owner-only single-link file")
        first_hash = _hash_descriptor(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        with soundfile.SoundFile(descriptor, mode="r", closefd=False) as handle:
            if (
                int(handle.samplerate) != TARGET_SAMPLE_RATE
                or int(handle.channels) != 2
                or int(handle.frames) != expected_frames
                or handle.subtype != "PCM_24"
            ):
                raise ValueError(f"{label} geometry differs")
            samples = handle.read(dtype="int32", always_2d=True)
        if samples.shape != (expected_frames, 2) or samples.dtype != np.int32:
            raise ValueError(f"{label} decoded geometry differs")
        second_hash = _hash_descriptor(descriptor)
        after = os.fstat(descriptor)
        if (
            _snapshot_identity(before) != _snapshot_identity(after)
            or first_hash != second_hash
        ):
            raise ValueError(f"{label} changed while it was read")
        if claim is not None and (
            first_hash != claim.get("sha256") or before.st_size != claim.get("bytes")
        ):
            raise ValueError(f"{label} binding differs")
        return {
            "path": path,
            "sha256": first_hash,
            "bytes": before.st_size,
            "frames": expected_frames,
            "samples": samples,
            "pcm24_int32_sequence_sha256": hashlib.sha256(
                samples.astype("<i4", copy=False).tobytes(order="C")
            ).hexdigest(),
        }
    finally:
        os.close(descriptor)


def _reverify_input_audio(inputs: Mapping[str, Any]) -> None:
    for role in _ROLES:
        original = inputs["base_audio"][role]
        current = _read_pcm24_snapshot(
            inputs["candidate_paths"][role],
            {"sha256": original["sha256"], "bytes": original["bytes"]},
            expected_frames=original["frames"],
            label=f"private v1 {role} candidate audio",
        )
        if (
            current["pcm24_int32_sequence_sha256"]
            != original["pcm24_int32_sequence_sha256"]
        ):
            raise ValueError("private v1 candidate PCM24 source changed")
    for key, original in inputs["worker_audio"].items():
        patch = inputs["patch_inventory"][key]
        current = _read_pcm24_snapshot(
            patch["worker_output_path"],
            {"sha256": original["sha256"], "bytes": original["bytes"]},
            expected_frames=original["frames"],
            label=f"private v1 {key[1]} worker output",
        )
        if (
            current["pcm24_int32_sequence_sha256"]
            != original["pcm24_int32_sequence_sha256"]
        ):
            raise ValueError("private v1 worker PCM24 source changed")


def _require_output_disjoint_from_inputs(
    destination: Path,
    *,
    evidence_roots: tuple[Path, ...],
    evidence_paths: tuple[Path, ...],
) -> None:
    """Keep new output outside every mutable input evidence tree."""

    resolved_destination = destination.resolve(strict=False)
    resolved_roots = {root.resolve(strict=True) for root in evidence_roots}
    for resolved_root in resolved_roots:
        if (
            resolved_destination == resolved_root
            or resolved_root in resolved_destination.parents
        ):
            raise ValueError("private v2 output must be outside input evidence roots")
    for path in evidence_paths:
        resolved_path = path.resolve(strict=True)
        if resolved_destination == resolved_path:
            raise ValueError("private v2 output must differ from input evidence paths")


def _preserved_patch_checks(
    role: str,
    *,
    base_int32: Any,
    candidate_int32: Any,
    target_keys: set[tuple[int, str]],
    patch_inventory: Mapping[tuple[int, str], Mapping[str, Any]],
    np: Any,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key, patch in sorted(patch_inventory.items()):
        if key[1] != role or key in target_keys:
            continue
        start = int(patch["start_frame"])
        end = int(patch["end_frame"])
        if not bool(np.array_equal(base_int32[start:end], candidate_int32[start:end])):
            raise ValueError("private v2 preserved v1 patch changed")
        result.append(
            {
                "boundary_index": key[0],
                "role": role,
                "start_frame": start,
                "end_frame": end,
                "pcm24_samples_exact": True,
            }
        )
    return result


def _outside_ranges_exact(
    base: Any,
    candidate: Any,
    *,
    ranges: list[tuple[int, int]],
    np: Any,
) -> bool:
    if base.shape != candidate.shape:
        raise ValueError("private v2 candidate round-trip geometry differs")
    mask = np.ones((len(base),), dtype=bool)
    for start, end in ranges:
        if start < 0 or end > len(base) or start >= end:
            raise ValueError("private v2 candidate comparison range differs")
        mask[start:end] = False
    if not bool(np.array_equal(base[mask], candidate[mask])):
        raise ValueError("private v2 candidate changed outside target ranges")
    return True


def _apply_equal_power_patch(
    destination: Any,
    replacement: Any,
    *,
    start: int,
    end: int,
    blend_frames: int,
    np: Any,
) -> None:
    if (
        destination.ndim != 2
        or replacement.shape != (end - start, destination.shape[1])
        or start < 0
        or end > len(destination)
        or end - start <= 2 * blend_frames
        or blend_frames < 1
    ):
        raise ValueError("private v2 patch geometry differs")
    before = destination[start:end].copy()
    theta = np.linspace(0.0, np.pi / 2.0, blend_frames, endpoint=True)
    destination[start : start + blend_frames] = (
        before[:blend_frames] * np.cos(theta)[:, None]
        + replacement[:blend_frames] * np.sin(theta)[:, None]
    )
    destination[start + blend_frames : end - blend_frames] = replacement[
        blend_frames:-blend_frames
    ]
    destination[end - blend_frames : end] = (
        replacement[-blend_frames:] * np.cos(theta)[:, None]
        + before[-blend_frames:] * np.sin(theta)[:, None]
    )


def _quantize_float_to_pcm24_int32(value: Any, *, np: Any) -> Any:
    # libsndfile first projects normalized floating point to signed int32,
    # rounding to nearest, then PCM24 retains the high 24 bits.  Express
    # both stages explicitly so reconstruction verification is independent of
    # the WAV container bytes.
    scaled = np.rint(value * 2_147_483_648.0)
    clipped = np.clip(scaled, -2_147_483_648, 2_147_483_647).astype("int64")
    return ((clipped >> 8) << 8).astype("int32")


def _audio_claim(
    path: Path,
    *,
    root: Path,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": snapshot["sha256"],
        "bytes": snapshot["bytes"],
        "pcm24_int32_sequence_sha256": snapshot["pcm24_int32_sequence_sha256"],
        "geometry": {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 2,
            "sample_width_bytes": 3,
            "frames": snapshot["frames"],
        },
    }


def _verify_report(path: Path, expected: Mapping[str, Any]) -> None:
    snapshot = _load_private_json_snapshot(path, "private v2 execution report")
    if snapshot["document"] != expected:
        raise ValueError("private v2 execution report changed during publication")


def _require_snapshot_unchanged(snapshot: Mapping[str, Any], label: str) -> None:
    current = _load_private_json_snapshot(snapshot["path"], label)
    if (
        current["sha256"] != snapshot["sha256"]
        or current["document"] != snapshot["document"]
    ):
        raise ValueError(f"{label} changed during v2 execution")


def _hash_descriptor(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        block = os.read(descriptor, 1024 * 1024)
        if not block:
            break
        digest.update(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _snapshot_identity(value: os.stat_result) -> tuple[int, ...]:
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


def _owner_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.set_inheritable(descriptor, False)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"private v2 {label} differs")
    return value


def _all_false(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(item is False for item in value.values())
    )


__all__: tuple[str, ...] = ()
