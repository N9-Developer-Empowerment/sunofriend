"""Effects-free plan for completing a stopped six-role canary from receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_integration_plan import (
    validate_fine_stem_six_role_integration_plan,
)


SCHEMA = "sunofriend.fine-stem-six-role-integration-completion-plan.v1"
STATUS = "awaiting_explicit_partial_completion_approval"


def completion_plan_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fine-stem completion evidence must be an object")
    return value


def _worker(
    partial: Path,
    relative_path: str,
    *,
    mode: str,
    cases: int,
    attempts: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = (partial / relative_path).resolve(strict=True)
    if partial not in path.parents:
        raise ValueError("fine-stem completion worker receipt escaped partial root")
    document = _json(path)
    if (
        document.get("schema")
        != "sunofriend.fine-stem-six-role-integration-worker.v1"
        or document.get("status")
        != "complete_unpublished_private_temporary_estimates"
        or document.get("mode") != mode
        or len(document.get("cases", [])) != cases
        or document.get("effects", {}).get("model_loads") != 1
        or document.get("effects", {}).get("inference_attempts") != attempts
        or document.get("effects", {}).get("network_attempts") != 0
    ):
        raise ValueError("fine-stem completion worker receipt differs")
    for case in document["cases"]:
        for identity in case.get("outputs", {}).values():
            recorded = Path(identity["path"])
            try:
                temporary_index = recorded.parts.index("TEMP")
            except ValueError as error:
                raise ValueError(
                    "fine-stem completion estimate lacks TEMP binding"
                ) from error
            output = (partial / Path(*recorded.parts[temporary_index:])).resolve(
                strict=True
            )
            if (
                partial not in output.parents
                or output.stat().st_size != identity["bytes"]
                or file_sha256(output) != identity["sha256"]
            ):
                raise ValueError("fine-stem completion temporary estimate differs")
    return document, {
        "relative_path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def load_completed_worker_receipt(
    partial_root: str | Path, relative_path: str
) -> dict[str, Any]:
    """Load one validated receipt and remap renamed staging paths in memory."""

    partial = Path(partial_root).resolve(strict=True)
    document = _json((partial / relative_path).resolve(strict=True))
    for case in document.get("cases", []):
        for identity in case.get("outputs", {}).values():
            recorded = Path(identity["path"])
            if "TEMP" not in recorded.parts:
                raise ValueError("fine-stem completion estimate lacks TEMP binding")
            index = recorded.parts.index("TEMP")
            output = (partial / Path(*recorded.parts[index:])).resolve(strict=True)
            if (
                partial not in output.parents
                or output.stat().st_size != identity["bytes"]
                or file_sha256(output) != identity["sha256"]
            ):
                raise ValueError("fine-stem completion temporary estimate differs")
            identity["path"] = str(output)
    return document


def build_completion_plan(
    original_plan: Mapping[str, Any], partial_root: str | Path
) -> dict[str, Any]:
    plan = validate_fine_stem_six_role_integration_plan(original_plan)
    partial = Path(partial_root).resolve(strict=True)
    failure_path = (partial / "FAILED-REPORT.json").resolve(strict=True)
    failure = _json(failure_path)
    if (
        failure.get("schema")
        != "sunofriend.fine-stem-six-role-integration-failure.v1"
        or failure.get("status") != "objective_failure_retained_no_retry"
        or failure.get("plan_sha256") != plan["document_sha256"]
        or "No module named 'bs_roformer'" not in failure.get("failure", "")
    ):
        raise ValueError("fine-stem completion failure binding differs")
    scnet, scnet_identity = _worker(
        partial,
        "TEMP/scnet-result.json",
        mode="scnet",
        cases=8,
        attempts=8,
    )
    synth, synth_identity = _worker(
        partial,
        "TEMP/mega53-synth-result.json",
        mode="mega53-synth",
        cases=4,
        attempts=4,
    )
    if scnet["model"].get("profile_id") != plan["profiles"]["core_four"]:
        raise ValueError("fine-stem completion SCNet profile differs")
    if synth["model"].get("profile_id") != plan["profiles"]["synth"]:
        raise ValueError("fine-stem completion synth profile differs")
    value: dict[str, Any] = {
        "schema": SCHEMA,
        "document_sha256": "",
        "status": STATUS,
        "original_plan_sha256": plan["document_sha256"],
        "partial_failure": {
            "failure_report": {
                "relative_path": "FAILED-REPORT.json",
                "bytes": failure_path.stat().st_size,
                "sha256": file_sha256(failure_path),
            },
            "completed_worker_receipts": {
                "scnet": scnet_identity,
                "synth": synth_identity,
            },
            "completed_model_loads": 2,
            "completed_inference_attempts": 12,
            "completed_temporary_estimates": 36,
            "network_attempts": 0,
        },
        "remaining_execution": {
            "profile_id": plan["profiles"]["guitar"],
            "model_loads": 1,
            "inference_attempts": 4,
            "cases": [
                case["case_id"]
                for case in plan["cases"]
                if case["new_complementary_estimate"]["role"] == "guitar"
            ],
            "network_denied": True,
            "automatic_retry": False,
            "reuse_scnet_without_rerun": True,
            "reuse_synth_without_rerun": True,
        },
        "post_inference": {
            "fixed_projection": True,
            "single_pcm24_writer": True,
            "private_review_package": True,
        },
        "effects": {
            "new_checkpoint_loads": 0,
            "new_model_constructions": 0,
            "new_inference_attempts": 0,
            "new_audio_writes": 0,
            "network_attempts": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
        "approval_text": (
            "I approve one network-denied partial completion for the exact "
            "completion-plan SHA-256 I cite. Reuse the verified SCNet and "
            "Mega-53 temporary estimates without rerunning them; load "
            "BS-RoFormer-SW once for four guitar attempts, then perform the "
            "fixed projection and private PCM24 write. No retry or other "
            "activation, selection, MIDI, hosting, redistribution or upload "
            "is approved."
        ),
    }
    value["document_sha256"] = completion_plan_sha256(value)
    return value


__all__ = [
    "SCHEMA",
    "STATUS",
    "build_completion_plan",
    "completion_plan_sha256",
    "load_completed_worker_receipt",
]
