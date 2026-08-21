from __future__ import annotations

from copy import deepcopy
from typing import Any

from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
)
from sunofriend.remix_identity import (
    create_remix_identity_state,
    create_remix_request,
    create_remix_result,
)
from sunofriend.source_receipt import document_sha256


def remix_fixture(*, suffix: str = "001", middle_db: float = -3.0) -> dict[str, Any]:
    state = musical_state(suffix)
    identity = create_remix_identity_state(
        state,
        separation_estimates=[
            {
                "source_estimate_id": f"grouped-other-{suffix}",
                "source_kind": "separation_estimate",
                "estimated_role": "grouped_other",
                "role_interpretation": "estimate_not_ground_truth",
                "audio_sha256": _sha(suffix, "a"),
                "audio_bytes": 96_044,
                "geometry": {"sample_rate_hz": 8_000, "channels": 1, "frames": 32_000},
            }
        ],
        owner_anchors=[
            {
                "anchor_id": f"hook-{suffix}",
                "anchor_kind": "motif",
                "owner_label": "Owner-recognised accompaniment hook",
                "label_authority": "explicit_owner_label",
                "source_estimate_id": f"grouped-other-{suffix}",
                "geometry": {
                    "sample_rate_hz": 8_000,
                    "start_frame": 8_000,
                    "end_frame": 16_000,
                },
            }
        ],
    )
    left_request = request(identity, middle_db)
    right_request = request(identity, middle_db - 2.0)
    left_result = result(left_request, identity, _sha(suffix, "b"))
    right_result = result(right_request, identity, _sha(suffix, "c"))
    return {
        "state": state,
        "identity": identity,
        "control": {
            "audio_sha256": _sha(suffix, "d"),
            "audio_bytes": 96_044,
            "geometry": {"sample_rate_hz": 8_000, "channels": 1, "frames": 32_000},
        },
        "left_request": left_request,
        "left_result": left_result,
        "right_request": right_request,
        "right_result": right_result,
    }


def request(identity: dict[str, Any], middle_db: float) -> dict[str, Any]:
    anchor = identity["owner_anchors"][0]
    return create_remix_request(
        identity,
        anchor_id=anchor["anchor_id"],
        source_estimate_id=anchor["source_estimate_id"],
        delta_envelope_points=[
            {"frame": 8_000, "delta_db": 0.0},
            {"frame": 12_000, "delta_db": middle_db},
            {"frame": 16_000, "delta_db": 0.0},
        ],
    )


def result(
    remix_request: dict[str, Any], identity: dict[str, Any], audio_sha256: str
) -> dict[str, Any]:
    return create_remix_result(
        remix_request,
        identity,
        output_audio_sha256=audio_sha256,
        output_audio_bytes=96_044,
        output_geometry={"sample_rate_hz": 8_000, "channels": 1, "frames": 32_000},
    )


def musical_state(suffix: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema": MUSICAL_STATE_SCHEMA,
        "status": "complete_unreviewed_no_selection",
        "state_scope": "audio_native_vocal_foundation",
        "method_natures": ["D", "H"],
        "clock": {
            "origin": "common_recorded_song_zero",
            "bpm": 100.0,
            "tuning_hz": 440.0,
        },
        "authorization": {
            "rights_category": "owned",
            "rights_confirmed": True,
            "common_recorded_zero_confirmed": True,
        },
        "lyrics": {
            "canonical": _file_record("LYRICS/lyrics.txt", _sha(suffix, "1")),
            "authority": "user_supplied_canonical",
            "automatic_rewrite_permitted": False,
        },
        "structure": {
            "phrase_timeline": _file_record(
                "TIMELINE/reviewed-phrase-timeline.json", _sha(suffix, "2")
            ),
            "phrase_timeline_schema": VOCAL_COMP_TIMELINE_SCHEMA,
            "review_status": "reviewed",
            "phrases": [
                {
                    "phrase_id": f"chorus-{suffix}",
                    "start_seconds": 1.0,
                    "end_seconds": 2.0,
                    "lyrics": "The heart sees",
                }
            ],
        },
        "vocal_performance_state": {
            "schema": VOCAL_PERFORMANCE_STATE_SCHEMA,
            "processing_chain": "dry",
            "reference": None,
            "takes": [],
            "continuous_f0_evidence": [],
            "lyric_phoneme_evidence": [],
            "non_pitched_event_evidence": [],
            "signal_quality_evidence": [],
            "explicit_phrase_decisions": [],
            "edit_maps": [],
            "correction_derivatives": [],
            "selection_authority": "human_only",
        },
        "optional_derived_evidence": {"midi": [], "notes": []},
        "training": {
            "explicit_labels": [],
            "training_eligible": False,
            "reason": "no explicit phrase comparison decision in this state",
        },
        "network_used": False,
        "effects": {
            "source_mutated": False,
            "lyrics_mutated": False,
            "selection_created": False,
            "human_decision_created": False,
            "audio_comp_rendered": False,
            "pitch_correction_applied": False,
            "training_started": False,
            "model_weights_changed": False,
            "remix_rendered": False,
        },
    }
    rehash(state)
    return state


def rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def changed(document: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(document)


def _file_record(path: str, sha256: str) -> dict[str, Any]:
    return {"path": path, "bytes": 1, "sha256": sha256}


def _sha(suffix: str, fill: str) -> str:
    # Deterministic and distinct for the compact synthetic contract fixtures.
    return (fill * 56 + suffix.encode("utf-8").hex())[:64].ljust(64, fill)
