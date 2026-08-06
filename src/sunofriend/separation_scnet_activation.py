"""Bind completed SCNet evidence into one public-opt-in activation decision."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .audio_formats import file_sha256
from .core_four_approval import validate_core_four_approval_document
from .separation_profiles import SCNET_RELEASE_PROFILE_ID
from .separation_rollout import (
    ROLLOUT_POLICY_ID,
    STOP_SHIP_GATES,
    evaluate_preview_admission,
)
from .separation_scnet_full_song_canaries import (
    RUN_SCHEMA,
    validate_canary_listen_document,
)


ACTIVATION_SCHEMA = "sunofriend.scnet-public-opt-in-activation.v1"


def record_scnet_public_opt_in_activation(
    full_song_root: str | Path,
    listen: str | Path,
    synthetic_roots: Sequence[str | Path],
    output: str | Path,
) -> dict[str, Any]:
    """Validate the finite evidence set and atomically record admission."""

    if len(synthetic_roots) != 3:
        raise ValueError("SCNet activation requires exactly three synthetic repeats")
    root = Path(full_song_root).expanduser().resolve(strict=True)
    run_path = root / "CANARY-RUN.json"
    approval_path = root / "APPROVAL/approved.json"
    run = _read_mapping(run_path)
    approval = validate_core_four_approval_document(_read_mapping(approval_path))
    listen_path = Path(listen).expanduser().resolve(strict=True)
    review = validate_canary_listen_document(_read_mapping(listen_path), run=run)
    if (
        run.get("schema") != RUN_SCHEMA
        or run.get("status") != "technical_pass_listening_pending"
        or run.get("profile_id") != SCNET_RELEASE_PROFILE_ID
        or run.get("objective_gates_passed") is not True
        or approval.get("status") != "approvals_complete_for_verified_delivery"
        or approval["approvals"]["supported_machine"]["decision"]
        != "verify_36_gib_first"
    ):
        raise ValueError("SCNet full-song activation binding differs")
    listen_by_coverage = {item["coverage_id"]: item for item in review["songs"]}
    category_map = {
        "vocal_forward": "vocal_forward",
        "dense_electronic": "dense_or_electronic",
        "acoustic_mixed": "acoustic_or_mixed",
    }
    canaries: list[dict[str, Any]] = []
    canary_evidence: list[dict[str, Any]] = []
    for item in run["canaries"]:
        coverage = item["coverage_id"]
        receipt_path = root / item["receipt"]
        receipt = _read_mapping(receipt_path)
        worker_path = receipt_path.parent / receipt["worker_report"]
        worker = _read_mapping(worker_path)
        listen_result = listen_by_coverage[coverage]
        if (
            receipt.get("status") != "technical_pass_listening_pending"
            or not all(receipt.get("objective_gates", {}).values())
            or listen_result.get("complete") is not True
            or listen_result.get("result") != "no_catastrophic_defect"
        ):
            raise ValueError(f"SCNet activation canary differs: {coverage}")
        canaries.append(
            {
                "category": category_map[coverage],
                "source_sha256": receipt["source"]["sha256"],
                "authorised": True,
                "catastrophic_listen_complete": True,
                "mislabelled_corrupt_silent_or_mistimed": False,
                "duration_seconds": worker["duration_seconds"],
                "elapsed_seconds": worker["resources"]["elapsed_seconds"],
                "peak_unified_memory_bytes": worker["resources"][
                    "peak_unified_memory_bytes"
                ],
            }
        )
        canary_evidence.append(
            {
                "coverage_id": coverage,
                "receipt_sha256": file_sha256(receipt_path),
                "worker_report_sha256": file_sha256(worker_path),
                "listen_result": listen_result["result"],
            }
        )

    repeats: list[dict[str, Any]] = []
    repeat_evidence: list[dict[str, Any]] = []
    for synthetic_root in synthetic_roots:
        synthetic = Path(synthetic_root).expanduser().resolve(strict=True)
        canary_path = synthetic / "CANARY.json"
        worker_path = synthetic / "worker-result.json"
        canary = _read_mapping(canary_path)
        worker = _read_mapping(worker_path)
        if (
            canary.get("status") != "technical_pass_unreviewed"
            or not all(canary.get("objective_gates", {}).values())
            or worker.get("profile_id") != SCNET_RELEASE_PROFILE_ID
            or worker.get("runtime", {}).get("network_used") is not False
        ):
            raise ValueError("SCNet synthetic repeat evidence differs")
        repeats.append(
            {
                "machine_id": "apple-m3-max-36-gib-first-verified-class",
                "machine_memory_bytes": 36 * 1024**3,
                "source_sha256": worker["outputs"]["source_reference"]["sha256"],
                "duration_seconds": worker["duration_seconds"],
                "elapsed_seconds": worker["resources"]["elapsed_seconds"],
                "peak_unified_memory_bytes": worker["resources"][
                    "peak_unified_memory_bytes"
                ],
            }
        )
        repeat_evidence.append(
            {
                "canary_sha256": file_sha256(canary_path),
                "worker_report_sha256": file_sha256(worker_path),
            }
        )

    admission_record = {
        "policy_id": ROLLOUT_POLICY_ID,
        "baseline_configuration_count": 1,
        "remediation_cycles": 1,
        "objective_gates": {name: True for name in STOP_SHIP_GATES},
        "synthetic_demo": {"passed": True},
        "authorised_song_canaries": canaries,
        "repeat_resource_runs": repeats,
    }
    admission = evaluate_preview_admission(admission_record)
    if (
        admission.get("objective_gates_passed") is not True
        or admission.get("decision") != "admit_public_opt_in"
    ):
        raise RuntimeError(f"SCNet public opt-in admission failed: {admission}")
    activation = {
        "schema": ACTIVATION_SCHEMA,
        "status": "public_opt_in_admitted",
        "profile_id": SCNET_RELEASE_PROFILE_ID,
        "scope_id": "core-four-stems-v1",
        "approval": {
            "approval_id": approval["approval_id"],
            "sha256": file_sha256(approval_path),
            "conditional_public_activation": True,
            "repository_publication": approval["approvals"][
                "repository_publication"
            ],
        },
        "evidence": {
            "full_song_run_sha256": file_sha256(run_path),
            "listen_sha256": file_sha256(listen_path),
            "full_song_canaries": canary_evidence,
            "synthetic_repeats": repeat_evidence,
        },
        "admission_record": admission_record,
        "admission": admission,
        "support": {
            "first_verified_machine_class": "Apple M3 Max with 36 GB unified memory",
            "other_apple_silicon_classes": "accessible_but_unverified",
            "supervision_remains_active": True,
        },
        "boundaries": {
            "default_two_stem_route_unchanged": True,
            "core_four_requires_explicit_scope": True,
            "automatic_midi_or_create": False,
            "subjective_usefulness_gate": None,
            "audio_uploaded": False,
        },
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    target = Path(output).expanduser().absolute()
    if os.path.lexists(target):
        raise FileExistsError(f"SCNet activation record already exists: {target}")
    temporary = target.with_name(f".{target.name}.building-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(activation, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {**activation, "path": str(target), "sha256": file_sha256(target)}


def _read_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"SCNet evidence must be a JSON object: {path}")
    return dict(value)


__all__ = ["ACTIVATION_SCHEMA", "record_scnet_public_opt_in_activation"]
