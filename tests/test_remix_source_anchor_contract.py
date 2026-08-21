from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from remix_learning_contract_fixtures import musical_state
from sunofriend.remix_anchor_preflight import create_remix_anchor_preflight_state
from sunofriend.remix_identity import create_remix_identity_state
from sunofriend.remix_source_anchor import (
    REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA,
    REMIX_SOURCE_ANCHOR_PREFLIGHT_SCHEMA,
    REMIX_SOURCE_IDENTITY_SCHEMA,
    REMIX_SOURCE_OWNER_REGISTRY_SCHEMA,
    confirm_remix_source_anchor_preflight,
    create_remix_source_anchor_preflight,
    create_remix_source_identity_state,
    create_remix_source_owner_registry,
    validate_remix_source_anchor_confirmation,
    validate_remix_source_anchor_preflight,
    validate_remix_source_identity_state,
    validate_remix_source_owner_registry,
)
from sunofriend.remix_source_state import (
    REMIX_SOURCE_STATE_SCHEMA,
    create_remix_source_state,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256


def _control() -> dict:
    return {
        "audio_sha256": "1" * 64,
        "audio_bytes": 3_969_044,
        "geometry": {"sample_rate_hz": 44_100, "channels": 2, "frames": 661_500},
    }


def _estimate() -> dict:
    return {
        "source_estimate_id": "grouped-other-estimate-001",
        "source_kind": "separation_estimate",
        "estimated_role": "grouped_other",
        "role_interpretation": "estimate_not_ground_truth",
        "audio_sha256": "2" * 64,
        "audio_bytes": 3_969_044,
        "geometry": {"sample_rate_hz": 44_100, "channels": 2, "frames": 661_500},
    }


def _state() -> dict:
    return create_remix_source_state(
        state_id="be-alone-191-206",
        composition_id="be-alone-owner-composition",
        group_id="be-alone-six-source-v2",
        source_control=_control(),
        rights_category="owned",
        source_start_seconds=191.0,
        source_end_seconds=206.0,
        owner_local_training_approved=True,
    )


def _anchor() -> dict:
    return {
        "anchor_id": "be-alone-hook",
        "anchor_kind": "motif",
        "owner_label": "Keep the repeating accompaniment hook recognisable",
        "label_authority": "explicit_owner_label",
        "source_estimate_id": "grouped-other-estimate-001",
        "geometry": {
            "sample_rate_hz": 44_100,
            "start_frame": 44_100,
            "end_frame": 220_500,
        },
    }


def _preflight(state: dict) -> dict:
    return create_remix_source_anchor_preflight(
        state,
        separation_estimate=_estimate(),
        owner_label=_anchor()["owner_label"],
        anchor_kind="motif",
        start_frame=44_100,
        end_frame=220_500,
        preservation_requirement="must_remain_recognisable",
        heard_source=True,
        heard_estimate=True,
    )


def test_source_identity_v1_binds_exact_source_state_without_vocal_fields() -> None:
    state = _state()
    identity = create_remix_source_identity_state(
        state, separation_estimates=[_estimate()], owner_anchors=[_anchor()]
    )
    assert identity["schema"] == REMIX_SOURCE_IDENTITY_SCHEMA
    assert identity["binding"] == {
        "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
        "source_state_sha256": state["document_sha256"],
    }
    assert "musical_state_sha256" not in str(identity)
    assert "lyrics" not in str(identity)
    assert identity["owner_anchors"] == [_anchor()]
    assert not any(identity["effects"].values())
    assert validate_remix_source_identity_state(identity, state) == identity


def test_source_registry_v1_infers_composition_group_only_from_bound_state() -> None:
    state = _state()
    identity = create_remix_source_identity_state(
        state, separation_estimates=[_estimate()], owner_anchors=[_anchor()]
    )
    registry = create_remix_source_owner_registry(
        state, identity, registry_id="be-alone-registry-001"
    )
    assert registry["schema"] == REMIX_SOURCE_OWNER_REGISTRY_SCHEMA
    assert registry["binding"]["source_state_sha256"] == state["document_sha256"]
    assert registry["entries"][0]["composition_id"] == state["composition_id"]
    assert registry["entries"][0]["group_id"] == state["group_id"]
    assert registry["authority"] == {
        "owner_confirmed_relationships": True,
        "automatic_relationship_inference": False,
        "training_execution_authorized": False,
        "product_selection_authorized": False,
    }
    assert validate_remix_source_owner_registry(registry, state, identity) == registry


def test_source_preflight_and_confirmation_have_no_downstream_authority() -> None:
    state = _state()
    pending = _preflight(state)
    assert pending["schema"] == REMIX_SOURCE_ANCHOR_PREFLIGHT_SCHEMA
    assert pending["binding"] == {
        "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
        "source_state_sha256": state["document_sha256"],
    }
    assert pending["source_control"] == state["source_control"]
    assert pending["explicitly_heard"] == {
        "source_control": True,
        "separation_estimate": True,
    }
    assert not any(pending["effects"].values())
    assert validate_remix_source_anchor_preflight(pending, state) == pending

    result = confirm_remix_source_anchor_preflight(
        pending,
        state,
        identity_state_id="be-alone-identity-001",
        registry_id="be-alone-registry-001",
    )
    confirmation = result["confirmation"]
    assert confirmation["schema"] == REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA
    assert confirmation["binding"]["source_state_sha256"] == state["document_sha256"]
    assert confirmation["authority"] == {
        "owner_anchor_confirmed": True,
        "remix_render_authorized": False,
        "pairwise_label_created": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_selection_authorized": False,
    }
    assert not any(confirmation["effects"].values())
    assert (
        validate_remix_source_anchor_confirmation(
            confirmation,
            pending,
            state,
            result["identity_state"],
            result["owner_registry"],
        )
        == confirmation
    )


def test_v1_rejects_state_estimate_binding_and_authority_tampering() -> None:
    state = _state()
    pending = _preflight(state)
    changed_state = deepcopy(state)
    changed_state["source_control"]["audio_sha256"] = "9" * 64
    changed_state.pop("document_sha256")
    changed_state["document_sha256"] = document_sha256(changed_state)
    with pytest.raises(ValueError, match="source.state|binding|SHA|hash"):
        validate_remix_source_anchor_preflight(pending, changed_state)

    changed = deepcopy(pending)
    changed["separation_estimate"]["audio_sha256"] = "8" * 64
    with pytest.raises(ValueError, match="SHA|hash"):
        validate_remix_source_anchor_preflight(changed, state)

    result = confirm_remix_source_anchor_preflight(
        pending, state, identity_state_id="identity-001", registry_id="registry-001"
    )
    forged = deepcopy(result["confirmation"])
    forged["authority"]["remix_render_authorized"] = True
    forged.pop("document_sha256")
    forged["document_sha256"] = document_sha256(forged)
    with pytest.raises(ValueError, match="authority|render"):
        validate_remix_source_anchor_confirmation(
            forged,
            pending,
            state,
            result["identity_state"],
            result["owner_registry"],
        )


def test_legacy_v0_identity_and_preflight_bytes_remain_unchanged() -> None:
    legacy = musical_state("legacy-v0-unchanged")
    estimate = {
        **_estimate(),
        "source_estimate_id": "legacy-estimate",
        "geometry": {"sample_rate_hz": 8_000, "channels": 1, "frames": 32_000},
    }
    anchor = {
        **_anchor(),
        "anchor_id": "legacy-hook",
        "source_estimate_id": "legacy-estimate",
        "geometry": {
            "sample_rate_hz": 8_000,
            "start_frame": 8_000,
            "end_frame": 16_000,
        },
    }
    control = {
        "audio_sha256": "3" * 64,
        "audio_bytes": 96_044,
        "geometry": {"sample_rate_hz": 8_000, "channels": 1, "frames": 32_000},
    }
    before_identity = canonical_json_bytes(
        create_remix_identity_state(
            legacy, separation_estimates=[estimate], owner_anchors=[anchor]
        )
    )
    before_pending = canonical_json_bytes(
        create_remix_anchor_preflight_state(
            legacy,
            source_control=control,
            separation_estimate={
                key: estimate[key]
                for key in (
                    "source_estimate_id",
                    "estimated_role",
                    "audio_sha256",
                    "audio_bytes",
                    "geometry",
                )
            },
            owner_label=anchor["owner_label"],
            anchor_kind="motif",
            start_frame=8_000,
            end_frame=16_000,
            preservation_requirement="must_remain_recognisable",
            heard_source=True,
            heard_estimate=True,
        )
    )
    _ = _preflight(_state())
    after_identity = canonical_json_bytes(
        create_remix_identity_state(
            legacy, separation_estimates=[estimate], owner_anchors=[anchor]
        )
    )
    after_pending = canonical_json_bytes(
        create_remix_anchor_preflight_state(
            legacy,
            source_control=control,
            separation_estimate={
                key: estimate[key]
                for key in (
                    "source_estimate_id",
                    "estimated_role",
                    "audio_sha256",
                    "audio_bytes",
                    "geometry",
                )
            },
            owner_label=anchor["owner_label"],
            anchor_kind="motif",
            start_frame=8_000,
            end_frame=16_000,
            preservation_requirement="must_remain_recognisable",
            heard_source=True,
            heard_estimate=True,
        )
    )
    assert after_identity == before_identity
    assert after_pending == before_pending
