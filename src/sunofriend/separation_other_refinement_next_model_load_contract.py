"""Pure evidence contract for the Mega-53 construction and strict-load gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


MODEL_LOAD_REPORT_SCHEMA = "sunofriend.mega53-restricted-model-load.v1"
MODEL_LOAD_REPORT_STATUS = "exact_mlx_model_constructed_and_strictly_loaded_offline"
MODEL_LOAD_RECEIPT_SCHEMA = "sunofriend.mega53-restricted-model-load-approval.v1"
MODEL_LOAD_RECEIPT_STATUS = "restricted_model_load_complete_no_inference_authority"
PROFILE_ID = "bs-roformer-mega-53-synth-v1"
SOURCE_REVISION = "de35ada5817b878da0194ee2860253dda3a9c2b2"
CHECKPOINT = {
    "file": "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt",
    "bytes": 1_368_919_887,
    "sha256": "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f",
}
CONFIG = {
    "file": "mvsep_mega_model_bs_roformer_53_stems.yaml",
    "bytes": 4_184,
    "sha256": "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103",
}
SOURCE = {
    "revision": SOURCE_REVISION,
    "archive_bytes": 144_791,
    "archive_sha256": "9b95036b8219eb5cd7be61a29868e6633dd42df0078eda55a0f3710123551c73",
    "evidence_sha256": "982ce7c2e9355be9a79d701c8f505237ada7da6ebad41695b48b70dc8c6aad97",
    "file_count": 64,
    "logical_bytes": 522_358,
}
RUNTIME = {
    "python": "3.12.10",
    "machine": "arm64",
    "torch": "2.2.2",
    "numpy": "1.26.4",
    "mlx": "0.31.2",
    "mlx-spectro": "0.7.0",
    "pyyaml": "6.0.3",
}
EXPECTED_GUARDS = {
    "audio_open_attempts": 0,
    "external_checkpoint_open_attempts": 0,
    "network_attempts": 0,
    "os_network_denial_required": True,
    "restricted_torch_load_calls": 1,
    "forward_calls": 0,
}
EXPECTED_EFFECTS = {
    "checkpoint_loaded": True,
    "model_constructed": True,
    "inference_runs": 0,
    "audio_reads": 0,
    "audio_writes": 0,
    "public_activation": False,
    "source_selection": False,
    "midi_created": False,
    "hosting": False,
    "redistribution": False,
}
EXPECTED_MODEL_INVENTORIES = {
    "checkpoint": {
        "key_count": 13_595,
        "total_numel": 681_663_596,
        "inventory_sha256": (
            "1855b41c7ff9cfe6a9d248a4fa1635b7abeb8be4044be7c19ecd9245fd725b10"
        ),
    },
    "converted": {
        "key_count": 13_571,
        "total_numel": 681_662_828,
        "inventory_sha256": (
            "565a9430061391486c8686d80eb4b6b65fdfd402b4bdeb603ab4ef5cf8c41fd8"
        ),
    },
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def model_load_report_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "report_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _validate_inventory(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"Mega-53 {label} inventory is missing")
    if not isinstance(value.get("key_count"), int) or value["key_count"] <= 0:
        raise ValueError(f"Mega-53 {label} key count is invalid")
    if not isinstance(value.get("total_numel"), int) or value["total_numel"] <= 0:
        raise ValueError(f"Mega-53 {label} tensor count is invalid")
    digest = value.get("inventory_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError(f"Mega-53 {label} inventory hash is invalid")


def validate_model_load_report(value: Any) -> dict[str, Any]:
    """Validate a completed no-inference report without importing its runtime."""

    if not isinstance(value, dict):
        raise ValueError("Mega-53 model-load report must be an object")
    if value.get("schema") != MODEL_LOAD_REPORT_SCHEMA:
        raise ValueError("Mega-53 model-load report schema differs")
    if value.get("status") != MODEL_LOAD_REPORT_STATUS:
        raise ValueError("Mega-53 model-load report status differs")
    if value.get("profile_id") != PROFILE_ID:
        raise ValueError("Mega-53 model-load profile differs")
    digest = value.get("report_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("Mega-53 model-load report hash is invalid")
    if digest != model_load_report_sha256(value):
        raise ValueError("Mega-53 model-load report hash differs")
    if value.get("checkpoint") != CHECKPOINT or value.get("config") != CONFIG:
        raise ValueError("Mega-53 model-load artifact identity differs")
    if value.get("source") != SOURCE:
        raise ValueError("Mega-53 model-load source identity differs")
    if value.get("runtime") != RUNTIME:
        raise ValueError("Mega-53 model-load runtime identity differs")
    if value.get("guards") != EXPECTED_GUARDS:
        raise ValueError("Mega-53 model-load guards differ")
    if value.get("effects") != EXPECTED_EFFECTS:
        raise ValueError("Mega-53 model-load effects differ")
    model = value.get("model")
    if not isinstance(model, dict):
        raise ValueError("Mega-53 model-load model evidence is missing")
    if model.get("architecture") != "BSRoformerMLX, 53 stems, stock MLP heads":
        raise ValueError("Mega-53 constructed architecture differs")
    if model.get("state_keys_equal") is not True:
        raise ValueError("Mega-53 state keys were not equal")
    if model.get("state_shapes_equal") is not True:
        raise ValueError("Mega-53 state shapes were not equal")
    if model.get("state_dtypes_equal") is not True:
        raise ValueError("Mega-53 state dtypes were not equal")
    if model.get("load_strict") is not True:
        raise ValueError("Mega-53 load was not strict")
    if model.get("model_retained_until_process_exit") is not True:
        raise ValueError("Mega-53 model was not retained through reporting")
    if model.get("config_declared_mlp_expansion_factor") != 2:
        raise ValueError("Mega-53 published expansion factor differs")
    if model.get("checkpoint_derived_mlp_expansion_factor") != 4:
        raise ValueError("Mega-53 checkpoint-derived expansion factor differs")
    if model.get("checkpoint_derived_mask_estimator_expansion_factor") != 2:
        raise ValueError("Mega-53 checkpoint-derived mask expansion factor differs")
    if model.get("checkpoint_parameter_dtype") != "mlx.core.float16":
        raise ValueError("Mega-53 checkpoint parameter dtype differs")
    remediation = model.get("architecture_remediation")
    if not isinstance(remediation, dict) or remediation.get("cycles_used") != 1:
        raise ValueError("Mega-53 bounded architecture remediation differs")
    if remediation.get("maximum_cycles") != 1:
        raise ValueError("Mega-53 architecture remediation cap differs")
    if remediation.get("derivation") != "checkpoint tensor shapes and dtypes only":
        raise ValueError("Mega-53 architecture remediation derivation differs")
    for label in ("checkpoint", "converted", "constructed", "loaded"):
        _validate_inventory(model.get(f"{label}_inventory"), label)
    if model["checkpoint_inventory"] != EXPECTED_MODEL_INVENTORIES["checkpoint"]:
        raise ValueError("Mega-53 checkpoint inventory identity differs")
    if model["converted_inventory"] != EXPECTED_MODEL_INVENTORIES["converted"]:
        raise ValueError("Mega-53 converted inventory identity differs")
    if model["checkpoint_inventory"]["key_count"] - model["converted_inventory"]["key_count"] != 24:
        raise ValueError("Mega-53 skipped rotary-buffer count differs")
    if model["checkpoint_inventory"]["total_numel"] - model["converted_inventory"]["total_numel"] != 768:
        raise ValueError("Mega-53 skipped rotary-buffer tensor count differs")
    for field in ("key_count", "total_numel", "inventory_sha256"):
        if model["converted_inventory"][field] != model["constructed_inventory"][field]:
            raise ValueError("Mega-53 converted and constructed inventories differ")
        if model["constructed_inventory"][field] != model["loaded_inventory"][field]:
            raise ValueError("Mega-53 constructed and loaded inventories differ")
    if model.get("native_role_count") != 53 or model.get("target_role") != "synth":
        raise ValueError("Mega-53 role contract differs")
    if model.get("chunk_alignment_valid_for_inference") is not False:
        raise ValueError("Mega-53 unaligned upstream chunk size was not recorded")
    return json.loads(json.dumps(value))


def build_model_load_receipt(
    report: Any, *, published_root: Path, recorded_at: str
) -> dict[str, Any]:
    validated = validate_model_load_report(report)
    if not published_root.is_absolute() or not recorded_at:
        raise ValueError("Mega-53 receipt publication details are invalid")
    return {
        "schema": MODEL_LOAD_RECEIPT_SCHEMA,
        "status": MODEL_LOAD_RECEIPT_STATUS,
        "recorded_at": recorded_at,
        "profile_id": PROFILE_ID,
        "published_root": str(published_root),
        "model_load_report_sha256": validated["report_sha256"],
        "approved_action": (
            "network-denied construction of the minimal BS-RoFormer Mega-53 MLX "
            "adapter and one exact weights-only CPU checkpoint load with strict "
            "converted state key, shape and dtype verification"
        ),
        "checkpoint_loaded": True,
        "model_constructed": True,
        "network_denied": True,
        "inference_performed": False,
        "audio_processed": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "not_approved": [
            "inference",
            "audio_processing",
            "public_activation",
            "source_selection",
            "midi",
            "hosting",
            "redistribution",
        ],
    }


__all__ = [
    "CHECKPOINT",
    "CONFIG",
    "EXPECTED_EFFECTS",
    "EXPECTED_GUARDS",
    "EXPECTED_MODEL_INVENTORIES",
    "MODEL_LOAD_REPORT_SCHEMA",
    "MODEL_LOAD_REPORT_STATUS",
    "PROFILE_ID",
    "RUNTIME",
    "SOURCE",
    "SOURCE_REVISION",
    "build_model_load_receipt",
    "model_load_report_sha256",
    "validate_model_load_report",
]
