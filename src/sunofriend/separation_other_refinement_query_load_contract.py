"""Pure contracts for the restricted Banquet/PaSST construction-load gate.

This module deliberately imports no model or audio dependency. Setup scripts,
tests and public audit documents can validate evidence without constructing a
model, opening a checkpoint or widening execution authority.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


QUERY_MODEL_LOAD_REPORT_SCHEMA = (
    "sunofriend.other-refinement-query-restricted-model-load.v1"
)
QUERY_MODEL_LOAD_REPORT_STATUS = (
    "two_exact_models_constructed_and_strictly_loaded_network_denied"
)
QUERY_MODEL_LOAD_RECEIPT_SCHEMA = (
    "sunofriend.other-refinement-query-restricted-model-load-approval.v1"
)
QUERY_MODEL_LOAD_RECEIPT_STATUS = (
    "restricted_model_load_gate_complete_no_inference_authority"
)
QUERY_BANDIT_SOURCE_REVISION = "79ed5bb75e5c3a40cd319d9d990cee913fc65c26"
QUERY_PROFILE_ID = "query-bandit-ev-pre-aug-v1"

EXPECTED_CHECKPOINTS: dict[str, dict[str, Any]] = {
    "banquet": {
        "file": "ev-pre-aug.ckpt",
        "bytes": 645_470_187,
        "sha256": (
            "657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2"
        ),
    },
    "passt": {
        "file": "openmic-passt-s-f128-10sec-p16-s10-ap.85.pt",
        "bytes": 341_546_630,
        "sha256": (
            "dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da"
        ),
    },
}

EXPECTED_MODEL_STATES: dict[str, dict[str, Any]] = {
    "banquet": {
        "key_count": 1_069,
        "total_numel": 111_234_333,
        "inventory_sha256": (
            "c562cc6f0b6807470d4d36ee4f6a048870e917afac9d7f92b2e35d7b9efec27f"
        ),
    },
    "passt": {
        "key_count": 159,
        "total_numel": 85_373_992,
        "inventory_sha256": (
            "ed94f5ea73d96f5965b1f67f11e84264f0afadd2efbbfad4d22783a4fc2aef96"
        ),
    },
}

EXPECTED_GUARDS = {
    "audio_open_attempts": 0,
    "network_attempts": 0,
    "os_network_denial_required": True,
    "pretrained_network_resolution": False,
    "restricted_torch_load_calls": 2,
    "unapproved_checkpoint_open_attempts": 0,
}

EXPECTED_EFFECTS = {
    "audio_reads": 0,
    "audio_writes": 0,
    "checkpoint_loaded": True,
    "inference_runs": 0,
    "midi_created": False,
    "model_constructed": True,
    "public_activation": False,
    "source_selection": False,
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def query_model_load_report_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical report digest with its self-hash omitted."""

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


def validate_query_model_load_report(value: Any) -> dict[str, Any]:
    """Validate one completed report without importing the model runtime."""

    if not isinstance(value, dict):
        raise ValueError("query model-load report must be an object")
    if value.get("schema") != QUERY_MODEL_LOAD_REPORT_SCHEMA:
        raise ValueError("query model-load report schema differs")
    if value.get("status") != QUERY_MODEL_LOAD_REPORT_STATUS:
        raise ValueError("query model-load report status differs")
    if value.get("source_revision") != QUERY_BANDIT_SOURCE_REVISION:
        raise ValueError("query model-load source revision differs")
    report_sha256 = value.get("report_sha256")
    if not isinstance(report_sha256, str) or not _SHA256_RE.fullmatch(report_sha256):
        raise ValueError("query model-load report SHA-256 is invalid")
    if report_sha256 != query_model_load_report_sha256(value):
        raise ValueError("query model-load report SHA-256 differs")
    if value.get("checkpoints") != EXPECTED_CHECKPOINTS:
        raise ValueError("query model-load checkpoint identities differ")
    if value.get("guards") != EXPECTED_GUARDS:
        raise ValueError("query model-load guards differ")
    if value.get("effects") != EXPECTED_EFFECTS:
        raise ValueError("query model-load effects differ")

    runtime = value.get("runtime")
    if not isinstance(runtime, dict) or runtime != {
        "numpy": "1.26.4",
        "python": "3.12.10",
        "torch": "2.2.2",
        "torchaudio": "2.2.2",
    }:
        raise ValueError("query model-load runtime identity differs")
    models = value.get("models")
    if not isinstance(models, dict) or set(models) != {
        "banquet",
        "passt",
        "models_retained_until_process_exit",
    }:
        raise ValueError("query model-load model records differ")
    if models.get("models_retained_until_process_exit") is not True:
        raise ValueError("query model-load models were not retained through reporting")
    for label, expected in EXPECTED_MODEL_STATES.items():
        model = models.get(label)
        if not isinstance(model, dict):
            raise ValueError(f"query model-load {label} record is missing")
        for field, expected_value in expected.items():
            if model.get(field) != expected_value:
                raise ValueError(f"query model-load {label} {field} differs")
        for field in ("keys_equal", "shapes_equal", "dtypes_equal"):
            if model.get(field) is not True:
                raise ValueError(f"query model-load {label} {field} is not true")
        if model.get("strict_load_missing_keys") != []:
            raise ValueError(f"query model-load {label} has missing keys")
        if model.get("strict_load_unexpected_keys") != []:
            raise ValueError(f"query model-load {label} has unexpected keys")
    if models["banquet"].get("checkpoint_root_prefix_removed_for_load") != "model.":
        raise ValueError("query model-load Banquet root transformation differs")
    if "pretrained=False" not in str(models["banquet"].get("architecture")):
        raise ValueError("query model-load embedded PaSST construction differs")
    if "pretrained=False" not in str(models["passt"].get("architecture")):
        raise ValueError("query model-load standalone PaSST construction differs")
    return value


def build_query_model_load_receipt(
    report: Any,
    *,
    published_root: Path,
    recorded_at: str,
) -> dict[str, Any]:
    """Build the narrow approval receipt for a validated completed report."""

    validated = validate_query_model_load_report(report)
    if not published_root.is_absolute():
        raise ValueError("query model-load published root must be absolute")
    if not isinstance(recorded_at, str) or not recorded_at:
        raise ValueError("query model-load receipt time is required")
    return {
        "schema": QUERY_MODEL_LOAD_RECEIPT_SCHEMA,
        "status": QUERY_MODEL_LOAD_RECEIPT_STATUS,
        "recorded_at": recorded_at,
        "profile_id": QUERY_PROFILE_ID,
        "published_root": str(published_root),
        "model_load_report_sha256": validated["report_sha256"],
        "approved_action": (
            "network-denied construction of the minimal Banquet and PaSST adapter "
            "and weights-only loading of the two exact local checkpoints with strict "
            "state-dict key, shape and dtype verification"
        ),
        "checkpoint_loaded": True,
        "model_constructed": True,
        "network_denied": True,
        "audio_processed": False,
        "inference_performed": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "not_approved": [
            "inference",
            "audio_processing",
            "public_activation",
            "source_selection",
            "midi",
        ],
    }


__all__ = [
    "EXPECTED_CHECKPOINTS",
    "EXPECTED_EFFECTS",
    "EXPECTED_GUARDS",
    "EXPECTED_MODEL_STATES",
    "QUERY_BANDIT_SOURCE_REVISION",
    "QUERY_MODEL_LOAD_RECEIPT_SCHEMA",
    "QUERY_MODEL_LOAD_RECEIPT_STATUS",
    "QUERY_MODEL_LOAD_REPORT_SCHEMA",
    "QUERY_MODEL_LOAD_REPORT_STATUS",
    "QUERY_PROFILE_ID",
    "build_query_model_load_receipt",
    "query_model_load_report_sha256",
    "validate_query_model_load_report",
]
