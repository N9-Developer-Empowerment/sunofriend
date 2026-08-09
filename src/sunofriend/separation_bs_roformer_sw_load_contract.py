"""Pure contract for one network-denied BS-RoFormer-SW strict load."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .separation_fine_stem_canary_contract import (
    SW_CHECKPOINT,
    SW_CONFIG,
    SW_NATIVE_ROLES,
)
from .separation_other_refinement_next_model_load_contract import RUNTIME, SOURCE


SW_LOAD_REPORT_SCHEMA = "sunofriend.bs-roformer-sw-restricted-model-load.v1"
SW_LOAD_REPORT_STATUS = "exact_sw_mlx_model_constructed_and_strictly_loaded_offline"
SW_PROFILE_ID = "bs-roformer-sw-guitar-v1"
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
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def sw_load_report_sha256(value: Mapping[str, Any]) -> str:
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


def _inventory(value: Any, label: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("key_count"), int)
        or value["key_count"] <= 0
        or not isinstance(value.get("total_numel"), int)
        or value["total_numel"] <= 0
        or _SHA256.fullmatch(str(value.get("inventory_sha256"))) is None
    ):
        raise ValueError(f"BS-RoFormer-SW {label} inventory differs")
    return value


def validate_sw_load_report(value: Mapping[str, Any]) -> dict[str, Any]:
    document = json.loads(json.dumps(value, allow_nan=False))
    if document.get("schema") != SW_LOAD_REPORT_SCHEMA:
        raise ValueError("BS-RoFormer-SW load report schema differs")
    if document.get("status") != SW_LOAD_REPORT_STATUS:
        raise ValueError("BS-RoFormer-SW load report status differs")
    if document.get("profile_id") != SW_PROFILE_ID:
        raise ValueError("BS-RoFormer-SW load profile differs")
    if document.get("checkpoint") != SW_CHECKPOINT or document.get("config") != SW_CONFIG:
        raise ValueError("BS-RoFormer-SW load artifacts differ")
    if document.get("source") != SOURCE or document.get("runtime") != RUNTIME:
        raise ValueError("BS-RoFormer-SW load runtime/source differs")
    if document.get("guards") != EXPECTED_GUARDS:
        raise ValueError("BS-RoFormer-SW load guards differ")
    if document.get("effects") != EXPECTED_EFFECTS:
        raise ValueError("BS-RoFormer-SW load effects differ")
    digest = document.get("report_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("BS-RoFormer-SW load report hash is invalid")
    if digest != sw_load_report_sha256(document):
        raise ValueError("BS-RoFormer-SW load report hash differs")
    model = document.get("model")
    if not isinstance(model, dict):
        raise ValueError("BS-RoFormer-SW model evidence is missing")
    if model.get("architecture") != "BSRoformerMLX, six-role SW checkpoint":
        raise ValueError("BS-RoFormer-SW architecture differs")
    if any(
        model.get(key) is not True
        for key in (
            "state_keys_equal",
            "state_shapes_equal",
            "state_dtypes_equal",
            "load_strict",
            "model_retained_until_process_exit",
        )
    ):
        raise ValueError("BS-RoFormer-SW strict state contract differs")
    checkpoint = _inventory(model.get("checkpoint_inventory"), "checkpoint")
    converted = _inventory(model.get("converted_inventory"), "converted")
    constructed = _inventory(model.get("constructed_inventory"), "constructed")
    loaded = _inventory(model.get("loaded_inventory"), "loaded")
    if converted != constructed or constructed != loaded:
        raise ValueError("BS-RoFormer-SW converted/loaded inventories differ")
    if checkpoint["key_count"] < converted["key_count"]:
        raise ValueError("BS-RoFormer-SW conversion added unexpected state keys")
    if model.get("native_roles") != list(SW_NATIVE_ROLES):
        raise ValueError("BS-RoFormer-SW native roles differ")
    if model.get("native_role_count") != len(SW_NATIVE_ROLES):
        raise ValueError("BS-RoFormer-SW native role count differs")
    if model.get("target_role") != "guitar" or model.get("target_role_index") != 4:
        raise ValueError("BS-RoFormer-SW guitar role mapping differs")
    if (
        model.get("chunk_size") != 588_800
        or model.get("num_overlap") != 2
        or model.get("stft_hop_length") != 512
    ):
        raise ValueError("BS-RoFormer-SW chunk clock differs")
    return document


__all__ = [
    "EXPECTED_EFFECTS",
    "EXPECTED_GUARDS",
    "SW_LOAD_REPORT_SCHEMA",
    "SW_LOAD_REPORT_STATUS",
    "SW_PROFILE_ID",
    "sw_load_report_sha256",
    "validate_sw_load_report",
]
