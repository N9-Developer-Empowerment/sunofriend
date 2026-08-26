from __future__ import annotations

from copy import deepcopy
import math

import pytest

from sunofriend.remix_source_state import (
    REMIX_SOURCE_STATE_SCHEMA,
    create_remix_source_state,
    validate_remix_project_state,
    validate_remix_source_state,
)
from sunofriend.source_receipt import document_sha256


def test_source_state_binds_owned_excerpt_without_vocal_or_training_authority() -> None:
    state = _state()
    assert state["schema"] == REMIX_SOURCE_STATE_SCHEMA
    assert state["source_control"] == {
        "audio_sha256": "a" * 64,
        "audio_bytes": 3_969_044,
        "geometry": {
            "sample_rate_hz": 44_100,
            "channels": 2,
            "frames": 661_500,
        },
    }
    assert state["clock"] == {
        "origin": "bounded_source_excerpt_zero",
        "source_start_seconds": 191.0,
        "source_end_seconds": 206.0,
        "duration_seconds": 15.0,
    }
    assert "lyrics" not in state
    assert "vocal_performance_state" not in state
    assert all(value is False for value in state["effects"].values())
    assert state["authority"]["owner_anchor_confirmed"] is False
    assert state["authority"]["training_execution_authorized"] is False
    assert validate_remix_source_state(state) == state
    assert validate_remix_project_state(state) == state


@pytest.mark.parametrize(
    "changes,pattern",
    [
        ({"rights_category": "licensed"}, "owner-controlled"),
        ({"owner_local_training_approved": False}, "approval"),
        ({"cloud_training_approved": True}, "cloud training"),
        ({"source_start_seconds": 190.0}, "clock"),
        ({"source_end_seconds": math.inf}, "finite"),
        ({"state_id": "C:/private/song"}, "safe identifier"),
    ],
)
def test_source_state_refuses_unsafe_or_unconfirmed_inputs(
    changes: dict, pattern: str
) -> None:
    values = _arguments()
    values.update(changes)
    with pytest.raises(ValueError, match=pattern):
        create_remix_source_state(**values)


def test_source_state_rejects_rehashed_false_authority_or_path() -> None:
    state = _state()
    forged = deepcopy(state)
    forged["training_approved"] = True
    _rehash(forged)
    with pytest.raises(ValueError, match="fields changed"):
        validate_remix_source_state(forged)

    forged = deepcopy(state)
    forged["state_id"] = "/Users/private/song.wav"
    _rehash(forged)
    with pytest.raises(ValueError, match="safe identifier"):
        validate_remix_source_state(forged)


def test_source_state_rejects_geometry_or_clock_drift() -> None:
    state = _state()
    forged = deepcopy(state)
    forged["source_control"]["geometry"]["frames"] -= 1
    _rehash(forged)
    with pytest.raises(ValueError, match="clock"):
        validate_remix_source_state(forged)


def _state() -> dict:
    return create_remix_source_state(**_arguments())


def _arguments() -> dict:
    return {
        "state_id": "be-alone-191-206-source-001",
        "composition_id": "be-alone",
        "group_id": "be-alone-source-001",
        "source_control": {
            "audio_sha256": "a" * 64,
            "audio_bytes": 3_969_044,
            "geometry": {
                "sample_rate_hz": 44_100,
                "channels": 2,
                "frames": 661_500,
            },
        },
        "rights_category": "owned",
        "source_start_seconds": 191.0,
        "source_end_seconds": 206.0,
        "owner_local_training_approved": True,
        "cloud_training_approved": False,
    }


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
