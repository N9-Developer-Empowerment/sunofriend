from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from remix_learning_contract_fixtures import musical_state
from sunofriend.remix_anchor_preflight import (
    REMIX_ANCHOR_CONFIRMATION_SCHEMA,
    REMIX_ANCHOR_PREFLIGHT_SCHEMA,
    confirm_remix_anchor_preflight,
    create_remix_anchor_preflight_state,
    validate_remix_anchor_confirmation,
    validate_remix_anchor_preflight_state,
)
from sunofriend.source_receipt import document_sha256


def test_explicit_anchor_confirmation_creates_no_remix_or_training_authority() -> None:
    state, control, estimate = _fixture()
    pending = _pending(state, control, estimate)
    assert pending["schema"] == REMIX_ANCHOR_PREFLIGHT_SCHEMA
    assert pending["status"] == "pending_explicit_owner_confirmation"
    assert pending["authority"]["owner_confirmation_recorded"] is False
    assert all(value is False for value in pending["effects"].values())

    result = confirm_remix_anchor_preflight(
        pending,
        state,
        identity_state_id="heart-chorus-identity-001",
        registry_id="owner-remix-registry-001",
        composition_id="the-heart-sees",
        group_id="the-heart-sees-source-001",
    )
    identity = result["identity_state"]
    registry = result["owner_registry"]
    receipt = result["confirmation"]
    assert receipt["schema"] == REMIX_ANCHOR_CONFIRMATION_SCHEMA
    assert receipt["status"] == "complete_explicit_owner_anchor_no_remix"
    assert identity["owner_anchors"] == [
        {
            "anchor_id": "heart-chorus-identity-001.anchor",
            "anchor_kind": "motif",
            "owner_label": "Keep the repeating accompaniment hook recognisable",
            "label_authority": "explicit_owner_label",
            "source_estimate_id": "grouped-other-estimate-001",
            "geometry": {
                "sample_rate_hz": 8_000,
                "start_frame": 8_000,
                "end_frame": 16_000,
            },
        }
    ]
    assert registry["entries"][0]["composition_id"] == "the-heart-sees"
    assert registry["entries"][0]["group_id"] == "the-heart-sees-source-001"
    assert registry["privacy"] == {
        "local_training_approved": True,
        "cloud_training_approved": False,
        "paths_embedded": False,
    }
    assert receipt["authority"]["owner_anchor_confirmed"] is True
    assert receipt["authority"]["remix_render_authorized"] is False
    assert receipt["authority"]["training_execution_authorized"] is False
    assert receipt["authority"]["product_selection_authorized"] is False
    assert all(value is False for value in receipt["effects"].values())
    assert (
        validate_remix_anchor_confirmation(receipt, pending, state, identity, registry)
        == receipt
    )


@pytest.mark.parametrize("heard_source,heard_estimate", [(False, True), (True, False)])
def test_preflight_requires_explicit_listening(
    heard_source: bool, heard_estimate: bool
) -> None:
    state, control, estimate = _fixture()
    with pytest.raises(ValueError, match="hear both"):
        create_remix_anchor_preflight_state(
            state,
            source_control=control,
            separation_estimate=estimate,
            owner_label="Keep the repeating accompaniment hook recognisable",
            anchor_kind="motif",
            start_frame=8_000,
            end_frame=16_000,
            preservation_requirement="must_remain_recognisable",
            heard_source=heard_source,
            heard_estimate=heard_estimate,
        )


@pytest.mark.parametrize(
    "change,pattern",
    [
        ({"anchor_kind": "automatic_best_hook"}, "anchor kind"),
        ({"owner_label": "/Users/private/song.wav"}, "path"),
        ({"start_frame": -1}, "outside"),
        ({"end_frame": 40_000}, "outside"),
        ({"preservation_requirement": "may_change"}, "preservation"),
    ],
)
def test_preflight_rejects_inferred_path_like_or_out_of_range_anchor(
    change: dict, pattern: str
) -> None:
    state, control, estimate = _fixture()
    values = {
        "owner_label": "Keep the repeating accompaniment hook recognisable",
        "anchor_kind": "motif",
        "start_frame": 8_000,
        "end_frame": 16_000,
        "preservation_requirement": "must_remain_recognisable",
    }
    values.update(change)
    with pytest.raises(ValueError, match=pattern):
        create_remix_anchor_preflight_state(
            state,
            source_control=control,
            separation_estimate=estimate,
            heard_source=True,
            heard_estimate=True,
            **values,
        )


def test_preflight_requires_synchronised_source_and_estimate_geometry() -> None:
    state, control, estimate = _fixture()
    estimate["geometry"]["frames"] -= 1
    with pytest.raises(ValueError, match="geometry differ"):
        _pending(state, control, estimate)


def test_rehashed_extra_authority_and_changed_binding_are_rejected() -> None:
    state, control, estimate = _fixture()
    pending = _pending(state, control, estimate)
    forged = deepcopy(pending)
    forged["release_authorized"] = True
    _rehash(forged)
    with pytest.raises(ValueError, match="fields changed"):
        validate_remix_anchor_preflight_state(forged, state)

    result = confirm_remix_anchor_preflight(
        pending,
        state,
        identity_state_id="identity-001",
        registry_id="registry-001",
        composition_id="composition-001",
        group_id="group-001",
    )
    receipt = deepcopy(result["confirmation"])
    receipt["binding"]["identity_state_sha256"] = "f" * 64
    _rehash(receipt)
    with pytest.raises(ValueError, match="binding changed"):
        validate_remix_anchor_confirmation(
            receipt,
            pending,
            state,
            result["identity_state"],
            result["owner_registry"],
        )


def test_confirmation_rejects_unsafe_or_too_long_identities() -> None:
    state, control, estimate = _fixture()
    pending = _pending(state, control, estimate)
    with pytest.raises(ValueError, match="safe identifier"):
        confirm_remix_anchor_preflight(
            pending,
            state,
            identity_state_id="../../private",
            registry_id="registry-001",
            composition_id="composition-001",
            group_id="group-001",
        )
    with pytest.raises(ValueError, match="too long"):
        confirm_remix_anchor_preflight(
            pending,
            state,
            identity_state_id="i" * 96,
            registry_id="registry-001",
            composition_id="composition-001",
            group_id="group-001",
        )


def _fixture() -> tuple[dict, dict, dict]:
    state = musical_state("anchor")
    geometry = {"sample_rate_hz": 8_000, "channels": 1, "frames": 32_000}
    control = {
        "audio_sha256": "a" * 64,
        "audio_bytes": 96_044,
        "geometry": deepcopy(geometry),
    }
    estimate = {
        "source_estimate_id": "grouped-other-estimate-001",
        "estimated_role": "grouped other estimate",
        "audio_sha256": "b" * 64,
        "audio_bytes": 96_044,
        "geometry": deepcopy(geometry),
    }
    return state, control, estimate


def _pending(state: dict, control: dict, estimate: dict) -> dict:
    return create_remix_anchor_preflight_state(
        state,
        source_control=control,
        separation_estimate=estimate,
        owner_label="Keep the repeating accompaniment hook recognisable",
        anchor_kind="motif",
        start_frame=8_000,
        end_frame=16_000,
        preservation_requirement="must_remain_recognisable",
        heard_source=True,
        heard_estimate=True,
    )


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
