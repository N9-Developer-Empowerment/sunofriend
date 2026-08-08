"""Immutable local-input contract for the approved Banquet reference canary."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .separation_other_refinement_query_reference_plan import (
    build_query_reference_plan,
)


QUERY_REFERENCE_INPUT_SCHEMA = (
    "sunofriend.other-refinement-query-reference-input-contract.v1"
)

_INPUT_IDENTITIES: dict[str, dict[str, Any]] = {
    "query:guitar": {
        "bytes": 52_976_756,
        "sha256": "4aa330ae07309f6b35503c0d8514091302e1741de95708b38069e049631778ef",
        "sample_rate_hz": 48_000,
        "channels": 2,
        "sample_width_bytes": 2,
        "frames": 13_244_160,
    },
    "query:keyboard": {
        "bytes": 52_976_756,
        "sha256": "f7f5a1b3ceec02110bc1b6312ee05af2edb64ebe6e763f6f6fb1be4e9e10de9a",
        "sample_rate_hz": 48_000,
        "channels": 2,
        "sample_width_bytes": 2,
        "frames": 13_244_160,
    },
    "query:synth": {
        "bytes": 52_976_756,
        "sha256": "cf073340772a56d577b2a0b43170706ef5c3112c2ed4bfe13b7b6e1d0de6ac37",
        "sample_rate_hz": 48_000,
        "channels": 2,
        "sample_width_bytes": 2,
        "frames": 13_244_160,
    },
    "mixture:be-alone": {
        "bytes": 50_411_692,
        "sha256": "68156218501b952703fcff76addea5ade377dbdab92f25375ecd4515b3efca5d",
        "sample_rate_hz": 48_000,
        "channels": 2,
        "sample_width_bytes": 2,
        "frames": 12_602_880,
    },
    "mixture:in-the-way": {
        "bytes": 59_846_068,
        "sha256": "32a7a4e28dc37d0a5459d41433c0ed5550eb5f8db2f9add9d8c2c551adb3f540",
        "sample_rate_hz": 44_100,
        "channels": 2,
        "sample_width_bytes": 3,
        "frames": 9_961_340,
    },
    "mixture:tell-me-that-i-do-it-bitch": {
        "bytes": 35_781_292,
        "sha256": "9962cc03f077290b293ca3bf40dff7359e6166c34c12e74bc5919bd9b5aa811d",
        "sample_rate_hz": 48_000,
        "channels": 2,
        "sample_width_bytes": 2,
        "frames": 8_945_280,
    },
}


def query_reference_input_contract_sha256(value: Mapping[str, Any]) -> str:
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


def build_query_reference_input_contract() -> dict[str, Any]:
    """Bind the six approved files after the authorised read-only preflight."""

    plan = build_query_reference_plan()
    inputs: list[dict[str, Any]] = []
    for query in plan["query_bank"]["queries"]:
        label = f"query:{query['target_id']}"
        inputs.append(
            {
                "label": label,
                "kind": "provider_query_estimate_not_truth",
                "relative_path": query["relative_path"],
                **_INPUT_IDENTITIES[label],
            }
        )
    for mixture in plan["test_mixtures"]:
        label = f"mixture:{mixture['track_id']}"
        inputs.append(
            {
                "label": label,
                "kind": "owner_authorised_original_mixture",
                "relative_path": mixture["relative_path"],
                **_INPUT_IDENTITIES[label],
            }
        )
    contract: dict[str, Any] = {
        "schema": QUERY_REFERENCE_INPUT_SCHEMA,
        "document_sha256": "",
        "plan_document_sha256": plan["document_sha256"],
        "rights_category": "owned",
        "owner_credit": "Music by Ezzye — https://soundcloud.com/ezzye-1",
        "inputs": inputs,
        "effects": {
            "input_audio_modified": False,
            "provider_labels_treated_as_truth": False,
            "audio_uploaded": False,
        },
    }
    contract["document_sha256"] = query_reference_input_contract_sha256(contract)
    return contract


def validate_query_reference_input_contract(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    expected = build_query_reference_input_contract()
    if dict(value) != expected:
        raise ValueError("query reference input contract differs")
    if value["document_sha256"] != query_reference_input_contract_sha256(value):
        raise ValueError("query reference input contract hash differs")
    return expected


__all__ = [
    "QUERY_REFERENCE_INPUT_SCHEMA",
    "build_query_reference_input_contract",
    "query_reference_input_contract_sha256",
    "validate_query_reference_input_contract",
]
