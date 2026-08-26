"""Deterministic, uncorrected dry-vocal comp rendering.

This first renderer is intentionally conservative.  It consumes one exact
owner-only Musical State and one complete human-decided source map.  It does
not select a take, infer a boundary, resample, time-stretch, tune, normalise,
limit or create training data.
"""

from __future__ import annotations

import html
import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .audio_formats import file_sha256
from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import canonical_json_bytes, document_sha256
from .vocal_phrase_decision import (
    VOCAL_RENDER_SOURCE_MAP_SCHEMA,
    validate_vocal_render_source_map,
)


VOCAL_DRY_RENDER_PLAN_SCHEMA = "sunofriend.vocal-comp-dry-render-plan.v0"
VOCAL_DRY_RENDER_RESULT_SCHEMA = "sunofriend.vocal-comp-dry-render-result.v0"
VOCAL_DRY_EDIT_MAP_SCHEMA = "sunofriend.vocal-comp-dry-edit-map.v0"
VOCAL_DRY_RENDER_AUTHORIZATION_SCHEMA = (
    "sunofriend.vocal-comp-dry-render-authorization.v0"
)
VOCAL_DRY_ROUND_TRIP_VERIFICATION_SCHEMA = (
    "sunofriend.vocal-comp-dry-round-trip-verification.v0"
)

_MAX_RENDER_FRAMES = 96_000 * 60 * 20
_MAX_RENDER_BYTES = 2 * 1024 * 1024 * 1024
_MAX_FADE_SECONDS = 0.010
_RENDER_SCOPES = frozenset(
    {"phrase_only", "reviewed_phrase_excerpt", "complete_state_timeline"}
)


def _audio_name(render_scope: str) -> str:
    return {
        "phrase_only": "dry-vocal-phrase-preview.wav",
        "reviewed_phrase_excerpt": "dry-vocal-excerpt-preview.wav",
        "complete_state_timeline": "dry-vocal-comp.wav",
    }[render_scope]


def _plan_status(render_scope: str) -> str:
    return {
        "phrase_only": "ready_phrase_only_dry_uncorrected_preview",
        "reviewed_phrase_excerpt": "ready_reviewed_excerpt_dry_uncorrected_preview",
        "complete_state_timeline": "ready_complete_dry_uncorrected",
    }[render_scope]


def _result_status(render_scope: str) -> str:
    return {
        "phrase_only": "complete_unreviewed_uncorrected_phrase_preview",
        "reviewed_phrase_excerpt": "complete_unreviewed_uncorrected_excerpt_preview",
        "complete_state_timeline": "complete_unreviewed_uncorrected",
    }[render_scope]


def _confirmation_scope(render_scope: str) -> str:
    return {
        "phrase_only": "one_dry_uncorrected_phrase_preview",
        "reviewed_phrase_excerpt": "one_dry_uncorrected_reviewed_phrase_excerpt",
        "complete_state_timeline": "one_dry_uncorrected_complete_vocal_comp",
    }[render_scope]


def create_dry_vocal_render_authorization(
    musical_state_manifest: str | Path,
    source_map: Mapping[str, Any],
    *,
    render_scope: str,
    phrase_id: str | None = None,
    confirm_dry_uncorrected_scope: bool = False,
    confirm_complete_intended_vocal_roster: bool = False,
    confirm_authorised_ai_fallback_render: bool = False,
) -> dict[str, Any]:
    """Create exact owner authority for one scope without rendering audio."""

    _path, _root, state = _load_exact_state(musical_state_manifest)
    checked_map = validate_vocal_render_source_map(source_map, state)
    if confirm_dry_uncorrected_scope is not True:
        raise ValueError("owner must explicitly confirm the dry uncorrected scope")
    selected = _source_map_rows_for_scope(
        state, checked_map, render_scope=render_scope, phrase_id=phrase_id
    )
    ai_rows = [row for row in selected if row["outcome"] == "ai_fallback"]
    if ai_rows and confirm_authorised_ai_fallback_render is not True:
        raise ValueError(
            "AI fallback needs separate explicit owner render authorization"
        )
    if not ai_rows and confirm_authorised_ai_fallback_render:
        raise ValueError("human-only scope cannot claim AI fallback authorization")
    if render_scope == "complete_state_timeline":
        if confirm_complete_intended_vocal_roster is not True:
            raise ValueError(
                "complete timeline needs explicit owner confirmation of the roster"
            )
        if checked_map["status"] != "complete_unrendered":
            raise ValueError("complete timeline authorization requires every phrase")
    elif confirm_complete_intended_vocal_roster:
        raise ValueError(
            "excerpt or phrase-only authorization cannot claim complete coverage"
        )
    document: dict[str, Any] = {
        "schema": VOCAL_DRY_RENDER_AUTHORIZATION_SCHEMA,
        "status": "explicit_owner_authorization",
        "method_natures": ["H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
            "vocal_source_map_schema": VOCAL_RENDER_SOURCE_MAP_SCHEMA,
            "vocal_source_map_sha256": checked_map["document_sha256"],
        },
        "render_scope": render_scope,
        "phrase_id": phrase_id,
        "owner_confirmation": {
            "dry_uncorrected_scope": True,
            "complete_intended_vocal_roster": (
                render_scope == "complete_state_timeline"
            ),
            "authorised_ai_fallback_render": bool(ai_rows),
            "ai_fallback_sources": [
                {
                    "source_id": row["source_id"],
                    "source_audio_sha256": row["source_audio_sha256"],
                }
                for row in ai_rows
            ],
        },
        "authority_limits": {
            "one_exact_plan_scope_only": True,
            "pitch_correction_authorized": False,
            "timing_correction_authorized": False,
            "normalisation_authorized": False,
            "limiting_authorized": False,
            "training_authorized": False,
        },
        "effects": _plan_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_dry_vocal_render_authorization(document, state, checked_map)


def validate_dry_vocal_render_authorization(
    authorization: Mapping[str, Any],
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact owner authority without inferring it from playback."""

    document = dict(authorization)
    _verify_document(
        document, VOCAL_DRY_RENDER_AUTHORIZATION_SCHEMA, "dry render authorization"
    )
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "render_scope",
        "phrase_id",
        "owner_confirmation",
        "authority_limits",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("dry render authorization fields changed")
    expected_binding = {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
        "vocal_source_map_schema": VOCAL_RENDER_SOURCE_MAP_SCHEMA,
        "vocal_source_map_sha256": source_map["document_sha256"],
    }
    if (
        document.get("status") != "explicit_owner_authorization"
        or document.get("method_natures") != ["H"]
        or document.get("binding") != expected_binding
    ):
        raise ValueError("dry render authorization binding or authority changed")
    render_scope = document.get("render_scope")
    phrase_id = document.get("phrase_id")
    selected = _source_map_rows_for_scope(
        state, source_map, render_scope=render_scope, phrase_id=phrase_id
    )
    ai_rows = [row for row in selected if row["outcome"] == "ai_fallback"]
    expected_confirmation = {
        "dry_uncorrected_scope": True,
        "complete_intended_vocal_roster": render_scope == "complete_state_timeline",
        "authorised_ai_fallback_render": bool(ai_rows),
        "ai_fallback_sources": [
            {
                "source_id": row["source_id"],
                "source_audio_sha256": row["source_audio_sha256"],
            }
            for row in ai_rows
        ],
    }
    if document.get("owner_confirmation") != expected_confirmation:
        raise ValueError("dry render owner confirmation is incomplete or excessive")
    if document.get("authority_limits") != {
        "one_exact_plan_scope_only": True,
        "pitch_correction_authorized": False,
        "timing_correction_authorized": False,
        "normalisation_authorized": False,
        "limiting_authorized": False,
        "training_authorized": False,
    }:
        raise ValueError("dry render authorization limits changed")
    if (
        document.get("effects") != _plan_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError("dry render authorization cannot create an effect")
    _reject_paths(document)
    return document


def create_dry_vocal_comp_plan(
    musical_state_manifest: str | Path,
    source_map: Mapping[str, Any],
    render_authorization: Mapping[str, Any],
    *,
    render_scope: str,
    phrase_id: str | None = None,
) -> dict[str, Any]:
    """Create a path-free, no-write dry-comp or phrase-preview plan."""

    state_path, state_root, state = _load_exact_state(musical_state_manifest)
    checked_map = validate_vocal_render_source_map(source_map, state)
    checked_authorization = validate_dry_vocal_render_authorization(
        render_authorization, state, checked_map
    )
    _validate_dry_plan_scope(
        state,
        checked_map,
        checked_authorization,
        render_scope=render_scope,
        phrase_id=phrase_id,
    )
    inventory = _source_inventory(state, state_root)
    phrases = {row["phrase_id"]: row for row in state["structure"]["phrases"]}
    selected_map_rows, horizon = _select_dry_plan_horizon(
        state,
        checked_map,
        inventory=inventory,
        phrases=phrases,
        render_scope=render_scope,
        phrase_id=phrase_id,
    )
    sample_rate = horizon["sample_rate"]
    channels = horizon["channels"]
    horizon_frames = horizon["frames"]
    if horizon_frames > _MAX_RENDER_FRAMES:
        raise ValueError("dry vocal render exceeds the 20-minute frame bound")
    segments = _build_dry_plan_segments(
        state,
        selected_map_rows=selected_map_rows,
        inventory=inventory,
        phrases=phrases,
        horizon=horizon,
    )
    expected_phrase_order = (
        [phrase_id]
        if render_scope == "phrase_only"
        else [row["phrase_id"] for row in state["structure"]["phrases"]]
    )
    if [row["phrase_id"] for row in segments] != expected_phrase_order:
        raise ValueError("source map segments must follow the requested phrase order")
    joins = (
        []
        if render_scope == "phrase_only"
        else _join_plan(segments, horizon_frames, sample_rate)
    )
    plan: dict[str, Any] = {
        "schema": VOCAL_DRY_RENDER_PLAN_SCHEMA,
        "status": _plan_status(render_scope),
        "render_scope": render_scope,
        "phrase_id": phrase_id,
        "method_natures": ["D", "H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
            "vocal_source_map_schema": VOCAL_RENDER_SOURCE_MAP_SCHEMA,
            "vocal_source_map_sha256": checked_map["document_sha256"],
            "render_authorization_schema": VOCAL_DRY_RENDER_AUTHORIZATION_SCHEMA,
            "render_authorization_sha256": checked_authorization["document_sha256"],
        },
        "horizon": {
            "authority": horizon["authority"],
            "source_audio_sha256": horizon["source_audio_sha256"],
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": horizon_frames,
            "song_zero_frame": 0,
            "destination_origin_song_frame": horizon["destination_origin_song_frame"],
            "destination_end_song_frame": horizon["destination_end_song_frame"],
        },
        "coverage": {
            "reviewed_roster_phrase_count": len(state["structure"]["phrases"]),
            "rendered_phrase_count": len(segments),
            "source_segment_count": len(segments),
            "whole_song_coverage_claimed": render_scope == "complete_state_timeline",
            "unresolved_count": checked_map["coverage"]["unresolved_count"],
            "undecided_count": checked_map["coverage"]["undecided_count"],
        },
        "segments": segments,
        "joins": joins,
        "render_policy": {
            "name": "exact-frame-dry-vocal-comp-v0",
            "encoding": "WAV_PCM_24",
            "timeline_gaps": "explicit_zero_with_equal_power_guard_fades",
            "phrase_only_window": "exact_reviewed_core_no_boundary_join",
            "contiguous_same_source": "exact_continuation",
            "contiguous_source_switch": "rejected_without_reviewed_join",
            "maximum_fade_seconds": _MAX_FADE_SECONDS,
            "resampling": False,
            "timing_correction": False,
            "pitch_correction": False,
            "gain_trim": False,
            "normalisation": False,
            "limiting": False,
            "clipping_permitted": False,
        },
        "authority": {
            "source_choices_are_explicit_human_decisions": True,
            "render_confirmation_required": True,
            "playback_creates_decision": False,
            "join_review_complete": False,
            "correction_authorised": False,
        },
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": _plan_effects(),
    }
    plan["document_sha256"] = document_sha256(plan)
    _validate_plan(plan, state, checked_map, checked_authorization)
    del state_path
    return plan


def _validate_dry_plan_scope(
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
    authorization: Mapping[str, Any],
    *,
    render_scope: str,
    phrase_id: str | None,
) -> None:
    if state["vocal_performance_state"].get("processing_chain") != "dry":
        raise ValueError("first dry renderer requires sources declared as dry")
    _validate_requested_render_scope(
        authorization, render_scope=render_scope, phrase_id=phrase_id
    )
    if render_scope == "reviewed_phrase_excerpt":
        _validate_reviewed_excerpt_scope(state, source_map)
    if render_scope == "complete_state_timeline":
        _validate_complete_timeline_scope(state, source_map)


def _validate_requested_render_scope(
    authorization: Mapping[str, Any], *, render_scope: str, phrase_id: str | None
) -> None:
    """Validate scope vocabulary and its exact owner authorization binding."""

    if render_scope not in _RENDER_SCOPES:
        raise ValueError(
            "render_scope must be phrase_only, reviewed_phrase_excerpt or "
            "complete_state_timeline"
        )
    if (
        authorization["render_scope"] != render_scope
        or authorization["phrase_id"] != phrase_id
    ):
        raise ValueError("dry render authorization binds another scope")
    if render_scope == "phrase_only":
        if not isinstance(phrase_id, str) or not phrase_id:
            raise ValueError("phrase_only rendering requires one explicit phrase_id")
    elif phrase_id is not None:
        raise ValueError("multi-phrase rendering must not select one phrase_id")


def _validate_reviewed_excerpt_scope(
    state: Mapping[str, Any], source_map: Mapping[str, Any]
) -> None:
    """Require a complete, decided multi-phrase excerpt."""

    if len(state["structure"]["phrases"]) < 2:
        raise ValueError("reviewed phrase excerpt requires at least two phrases")
    if source_map["status"] != "complete_unrendered":
        raise ValueError("reviewed phrase excerpt requires every reviewed phrase")
    if source_map["unresolved_phrases"] or source_map["undecided_phrase_ids"]:
        raise ValueError("reviewed phrase excerpt cannot contain unresolved phrases")


def _validate_complete_timeline_scope(
    state: Mapping[str, Any], source_map: Mapping[str, Any]
) -> None:
    """Require explicit full-roster coverage before whole-song rendering."""

    if source_map["status"] != "complete_unrendered":
        raise ValueError("complete dry vocal comp requires every phrase source")
    if source_map["unresolved_phrases"] or source_map["undecided_phrase_ids"]:
        raise ValueError("complete dry vocal comp cannot contain unresolved phrases")
    if (
        state.get("structure", {}).get("coverage_scope")
        != "reviewed_complete_intended_vocal_roster"
    ):
        raise ValueError(
            "whole-song rendering requires the reviewed roster itself to declare "
            "complete intended vocal coverage"
        )


def _select_dry_plan_horizon(
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
    *,
    inventory: Mapping[str, Mapping[str, Any]],
    phrases: Mapping[str, Mapping[str, Any]],
    render_scope: str,
    phrase_id: str | None,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    selected_map_rows = list(source_map["segments"])
    if render_scope == "phrase_only":
        if phrase_id not in phrases:
            raise ValueError("phrase_only phrase is not in the reviewed roster")
        selected_map_rows = [
            row for row in selected_map_rows if row["phrase_id"] == phrase_id
        ]
        if len(selected_map_rows) != 1:
            raise ValueError(
                "phrase_only rendering requires one explicit source-bearing decision"
            )
        source = inventory[selected_map_rows[0]["source_id"]]
        phrase = phrases[phrase_id]
        sample_rate = source["audio_properties"]["sample_rate"]
        song_start = round(float(phrase["start_seconds"]) * sample_rate)
        song_end = round(float(phrase["end_seconds"]) * sample_rate)
        horizon = {
            "authority": "exact_reviewed_phrase_window_only",
            "source_audio_sha256": source["audio"]["sha256"],
            "sample_rate": sample_rate,
            "channels": source["audio_properties"]["channels"],
            "frames": song_end - song_start,
            "song_zero_frame": 0,
            "destination_origin_song_frame": song_start,
            "destination_end_song_frame": song_end,
        }
    elif render_scope == "reviewed_phrase_excerpt":
        first_source = inventory[selected_map_rows[0]["source_id"]]
        properties = first_source["audio_properties"]
        sample_rate = properties["sample_rate"]
        song_start = round(
            float(state["structure"]["phrases"][0]["start_seconds"]) * sample_rate
        )
        song_end = round(
            float(state["structure"]["phrases"][-1]["end_seconds"]) * sample_rate
        )
        horizon = {
            "authority": "exact_reviewed_phrase_excerpt_window",
            "source_audio_sha256": first_source["audio"]["sha256"],
            "sample_rate": sample_rate,
            "channels": properties["channels"],
            "frames": song_end - song_start,
            "song_zero_frame": 0,
            "destination_origin_song_frame": song_start,
            "destination_end_song_frame": song_end,
        }
    else:
        horizon = _render_horizon(state, inventory)
        horizon["destination_origin_song_frame"] = 0
        horizon["destination_end_song_frame"] = horizon["frames"]
    return selected_map_rows, horizon


def _build_dry_plan_segments(
    state: Mapping[str, Any],
    *,
    selected_map_rows: Sequence[Mapping[str, Any]],
    inventory: Mapping[str, Mapping[str, Any]],
    phrases: Mapping[str, Mapping[str, Any]],
    horizon: Mapping[str, Any],
) -> list[dict[str, Any]]:
    sample_rate = horizon["sample_rate"]
    channels = horizon["channels"]
    horizon_frames = horizon["frames"]
    destination_origin = horizon["destination_origin_song_frame"]
    segments: list[dict[str, Any]] = []
    for map_row in selected_map_rows:
        phrase = phrases[map_row["phrase_id"]]
        source = inventory[map_row["source_id"]]
        properties = source["audio_properties"]
        if (
            properties["sample_rate"] != sample_rate
            or properties["channels"] != channels
        ):
            raise ValueError(
                "selected vocal sources must match the exact horizon clock and channels"
            )
        song_destination_start = round(float(phrase["start_seconds"]) * sample_rate)
        song_destination_end = round(float(phrase["end_seconds"]) * sample_rate)
        destination_start = song_destination_start - destination_origin
        destination_end = song_destination_end - destination_origin
        if not 0 <= destination_start < destination_end <= horizon_frames:
            raise ValueError("phrase destination escapes the exact render horizon")
        if source["source_class"] == "human_vocal_phrase_capture":
            source_start = _integer(map_row.get("source_start_frame"), "source start")
            source_end = _integer(map_row.get("source_end_frame"), "source end")
        else:
            source_start = song_destination_start
            source_end = song_destination_end
        if source_end - source_start != destination_end - destination_start:
            raise ValueError(
                "dry vocal comp forbids timing correction or source-length padding"
            )
        if not 0 <= source_start < source_end <= properties["frames"]:
            raise ValueError("source phrase geometry escapes the selected vocal source")
        if map_row["source_audio_sha256"] != source["audio"]["sha256"]:
            raise ValueError("source map audio identity changed")
        if map_row["outcome"] == "ai_fallback":
            reference = state["vocal_performance_state"].get("reference")
            if not isinstance(reference, Mapping) or source[
                "source_id"
            ] != reference.get("source_id"):
                raise ValueError(
                    "AI fallback must use the exact authorised reference vocal"
                )
        elif source["source_class"] not in {
            "human_vocal_take",
            "human_vocal_phrase_capture",
        }:
            raise ValueError("human phrase outcome must use an exact human source")

        segment = {
            "phrase_id": phrase["phrase_id"],
            "decision_document_sha256": map_row["decision_document_sha256"],
            "outcome": map_row["outcome"],
            "source_id": source["source_id"],
            "source_class": source["source_class"],
            "source_audio_sha256": source["audio"]["sha256"],
            "destination_start_frame": destination_start,
            "destination_end_frame": destination_end,
            "song_destination_start_frame": song_destination_start,
            "song_destination_end_frame": song_destination_end,
            "source_start_frame": source_start,
            "source_end_frame": source_end,
            "available_pre_guard_frames": source_start,
            "available_post_guard_frames": properties["frames"] - source_end,
            "used_pre_guard_frames": 0,
            "used_post_guard_frames": 0,
        }
        segments.append(segment)
    return segments


def render_dry_vocal_comp(
    musical_state_manifest: str | Path,
    source_map: Mapping[str, Any],
    render_authorization: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    out_dir: str | Path,
    confirm_dry_uncorrected_render: bool = False,
) -> dict[str, Any]:
    """Render one fresh owner-only dry comp and local review package."""

    if confirm_dry_uncorrected_render is not True:
        raise ValueError("explicit dry uncorrected render confirmation is required")
    _state_path, state_root, state = _load_exact_state(musical_state_manifest)
    checked_map = validate_vocal_render_source_map(source_map, state)
    checked_authorization = validate_dry_vocal_render_authorization(
        render_authorization, state, checked_map
    )
    checked_plan = _validate_plan(plan, state, checked_map, checked_authorization)
    expected_plan = create_dry_vocal_comp_plan(
        musical_state_manifest,
        checked_map,
        checked_authorization,
        render_scope=checked_plan["render_scope"],
        phrase_id=checked_plan["phrase_id"],
    )
    if checked_plan != expected_plan:
        raise ValueError("dry vocal render plan is stale or was altered")

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise FileExistsError(f"dry vocal comp output already exists: {destination}")
    if destination == state_root or state_root in destination.parents:
        raise ValueError("dry vocal comp output must be outside the Musical State")
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("dry vocal comp output parent must be an existing directory")
    if stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise PermissionError("dry vocal comp output parent must be owner-only")

    soundfile, numpy = _audio_dependencies()
    inventory = _source_inventory(state, state_root)
    decoded: dict[str, Any] = {}
    source_pre_hashes: dict[str, str] = {}
    for segment in checked_plan["segments"]:
        source_id = segment["source_id"]
        if source_id in decoded:
            continue
        source = inventory[source_id]
        path = source["path"]
        source_pre_hashes[source_id] = file_sha256(path)
        values, rate = soundfile.read(path, dtype="float64", always_2d=True)
        if rate != checked_plan["horizon"]["sample_rate"] or values.shape != (
            source["audio_properties"]["frames"],
            checked_plan["horizon"]["channels"],
        ):
            raise ValueError("selected vocal source decoded geometry changed")
        if not numpy.isfinite(values).all():
            raise ValueError("selected vocal source contains non-finite samples")
        decoded[source_id] = values
    _verify_source_stability(inventory, source_pre_hashes)

    horizon = checked_plan["horizon"]
    output = numpy.zeros((horizon["frames"], horizon["channels"]), dtype=numpy.float64)
    for segment in checked_plan["segments"]:
        output[
            segment["destination_start_frame"] : segment["destination_end_frame"]
        ] = decoded[segment["source_id"]][
            segment["source_start_frame"] : segment["source_end_frame"]
        ]
    for join in checked_plan["joins"]:
        _render_join(join, checked_plan["segments"], decoded, output, numpy)
    if not numpy.isfinite(output).all():
        raise ValueError("dry vocal comp contains non-finite samples")
    peak = float(numpy.max(numpy.abs(output), initial=0.0))
    if peak >= 1.0:
        raise ValueError("dry vocal comp would clip; no limiter or normaliser was used")
    _verify_source_stability(inventory, source_pre_hashes)

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=parent))
    staging.chmod(0o700)
    try:
        audio_dir = staging / "AUDIO"
        review_dir = staging / "REVIEW"
        technical_dir = staging / "TECHNICAL"
        for directory in (audio_dir, review_dir, technical_dir):
            directory.mkdir(mode=0o700)
        audio_name = _audio_name(checked_plan["render_scope"])
        audio_path = audio_dir / audio_name
        soundfile.write(
            audio_path,
            output,
            horizon["sample_rate"],
            format="WAV",
            subtype="PCM_24",
        )
        audio_path.chmod(0o600)
        audio_record = _inspect_output(audio_path)
        if audio_record["geometry"] != {
            "sample_rate": horizon["sample_rate"],
            "channels": horizon["channels"],
            "frames": horizon["frames"],
        }:
            raise ValueError("published dry vocal comp changed the exact horizon")
        if audio_record["bytes"] > _MAX_RENDER_BYTES:
            raise ValueError("published dry vocal comp exceeds the 2 GiB bound")

        edit_map = _edit_map(checked_plan, audio_record)
        edit_map_path = technical_dir / "dry-vocal-edit-map.json"
        _write_private(edit_map_path, canonical_json_bytes(edit_map))
        review_path = review_dir / "dry-vocal-comp-review.html"
        _write_private(review_path, _review_html(edit_map).encode("utf-8"))
        result: dict[str, Any] = {
            "schema": VOCAL_DRY_RENDER_RESULT_SCHEMA,
            "status": _result_status(checked_plan["render_scope"]),
            "render_scope": checked_plan["render_scope"],
            "phrase_id": checked_plan["phrase_id"],
            "method_natures": ["D", "H"],
            "binding": {
                "musical_state_sha256": state["document_sha256"],
                "vocal_source_map_sha256": checked_map["document_sha256"],
                "render_authorization_sha256": checked_authorization["document_sha256"],
                "render_plan_sha256": checked_plan["document_sha256"],
                "edit_map_document_sha256": edit_map["document_sha256"],
            },
            "render_confirmation": {
                "explicit": True,
                "scope": _confirmation_scope(checked_plan["render_scope"]),
            },
            "artifacts": {
                "dry_vocal_wav": {
                    **audio_record,
                    "relative_path": f"AUDIO/{audio_name}",
                    "encoding": "WAV_PCM_24",
                },
                "edit_map": _file_record(edit_map_path, staging),
                "review_html": _file_record(review_path, staging),
            },
            "signal": {
                "sample_peak": peak,
                "finite": True,
                "clipped": False,
                "normalised": False,
                "limited": False,
            },
            "review": {
                "status": "not_reviewed",
                "playback_creates_decision": False,
                "join_review_complete": False,
                "selected_for_product": False,
            },
            "processing": {
                "pitch_correction": False,
                "timing_correction": False,
                "resampling": False,
                "gain_trim": False,
                "normalisation": False,
                "limiting": False,
            },
            "model_used": False,
            "training_used": False,
            "network_used": False,
            "effects": {
                "source_mutated": False,
                "source_choice_created": False,
                "audio_comp_rendered": True,
                "join_preview_rendered": bool(checked_plan["joins"]),
                "pitch_correction_applied": False,
                "timing_correction_applied": False,
                "normalisation_applied": False,
                "limiting_applied": False,
                "human_review_created": False,
                "training_label_created": False,
                "model_weights_changed": False,
            },
        }
        result["document_sha256"] = document_sha256(result)
        validate_dry_vocal_comp_result(result, checked_plan)
        receipt_path = technical_dir / "dry-vocal-render-receipt.json"
        _write_private(receipt_path, canonical_json_bytes(result))
        _verify_source_stability(inventory, source_pre_hashes)
        os.rename(staging, destination)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_dry_vocal_comp_round_trip(
    output_dir: str | Path,
    *,
    plan: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Read and verify one returned dry-comp package without changing it."""

    checked_plan = dict(plan)
    _verify_document(checked_plan, VOCAL_DRY_RENDER_PLAN_SCHEMA, "dry render plan")
    checked_result = validate_dry_vocal_comp_result(result, checked_plan)
    root = Path(output_dir).expanduser().absolute()
    audio_name = _audio_name(checked_plan["render_scope"])
    expected_roster = {
        f"AUDIO/{audio_name}",
        "REVIEW/dry-vocal-comp-review.html",
        "TECHNICAL/dry-vocal-edit-map.json",
        "TECHNICAL/dry-vocal-render-receipt.json",
    }
    paths = _verify_dry_package_roster(root, expected_roster)

    receipt_bytes = _read_stable_regular_file(
        paths["TECHNICAL/dry-vocal-render-receipt.json"],
        label="dry render receipt",
        maximum_bytes=16 * 1024 * 1024,
    )
    if receipt_bytes != canonical_json_bytes(checked_result):
        raise ValueError("dry render receipt file differs from the exact result")

    audio_path = paths[f"AUDIO/{audio_name}"]
    before = audio_path.stat()
    actual_audio = _inspect_output(audio_path)
    soundfile, numpy = _audio_dependencies()
    values, sample_rate = soundfile.read(audio_path, dtype="float64", always_2d=True)
    after = audio_path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("dry vocal audio changed during round-trip verification")
    if file_sha256(audio_path) != actual_audio["sha256"]:
        raise ValueError("dry vocal audio changed during round-trip verification")
    expected_audio = checked_result["artifacts"]["dry_vocal_wav"]
    if actual_audio != {
        "sha256": expected_audio["sha256"],
        "bytes": expected_audio["bytes"],
        "geometry": expected_audio["geometry"],
    }:
        raise ValueError("dry vocal audio file differs from its result receipt")
    if sample_rate != checked_plan["horizon"]["sample_rate"] or values.shape != (
        checked_plan["horizon"]["frames"],
        checked_plan["horizon"]["channels"],
    ):
        raise ValueError("dry vocal audio decoded geometry changed")
    if not numpy.isfinite(values).all():
        raise ValueError("dry vocal audio contains non-finite samples")
    actual_peak = float(numpy.max(numpy.abs(values), initial=0.0))
    if actual_peak >= 1.0:
        raise ValueError("dry vocal audio clips")
    if abs(actual_peak - float(checked_result["signal"]["sample_peak"])) > 2**-22:
        raise ValueError("dry vocal audio peak differs from its result receipt")

    edit_map_bytes = _read_stable_regular_file(
        paths["TECHNICAL/dry-vocal-edit-map.json"],
        label="dry edit map",
        maximum_bytes=16 * 1024 * 1024,
    )
    try:
        edit_map = json.loads(edit_map_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry edit map is not valid UTF-8 JSON") from exc
    if not isinstance(edit_map, dict):
        raise ValueError("dry edit map must be a JSON object")
    expected_edit_map = _edit_map(checked_plan, actual_audio)
    if edit_map != expected_edit_map or edit_map_bytes != canonical_json_bytes(
        expected_edit_map
    ):
        raise ValueError("dry edit map differs from the exact render plan and audio")

    review_bytes = _read_stable_regular_file(
        paths["REVIEW/dry-vocal-comp-review.html"],
        label="dry review page",
        maximum_bytes=16 * 1024 * 1024,
    )
    if review_bytes != _review_html(expected_edit_map).encode("utf-8"):
        raise ValueError("dry review page differs from the exact edit map")

    verification: dict[str, Any] = {
        "schema": VOCAL_DRY_ROUND_TRIP_VERIFICATION_SCHEMA,
        "status": "verified_technical_artifacts_unreviewed",
        "render_plan_sha256": checked_plan["document_sha256"],
        "render_result_sha256": checked_result["document_sha256"],
        "artifacts": {
            "dry_vocal_wav": actual_audio,
            "edit_map_sha256": hashlib.sha256(edit_map_bytes).hexdigest(),
            "review_html_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "render_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        },
        "signal": {
            "sample_peak": actual_peak,
            "finite": True,
            "clipped": False,
        },
        "checks": {
            "fixed_regular_file_roster": True,
            "symlinks_absent": True,
            "actual_bytes_and_sha256": True,
            "wav_pcm24_geometry": True,
            "finite_unclipped_audio": True,
            "edit_map_exact": True,
            "review_content_exact": True,
            "receipt_content_exact": True,
        },
        "authority": {
            "technical_verification_only": True,
            "human_review_created": False,
            "selected_for_product": False,
            "correction_authorized": False,
            "training_authorized": False,
        },
        "network_used": False,
    }
    verification["document_sha256"] = document_sha256(verification)
    return verification


def _source_map_rows_for_scope(
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
    *,
    render_scope: Any,
    phrase_id: Any,
) -> list[Mapping[str, Any]]:
    phrases = [row["phrase_id"] for row in state["structure"]["phrases"]]
    if render_scope == "phrase_only":
        if not isinstance(phrase_id, str) or phrase_id not in phrases:
            raise ValueError("phrase-only authorization requires one reviewed phrase")
        selected = [
            row for row in source_map["segments"] if row["phrase_id"] == phrase_id
        ]
        if len(selected) != 1:
            raise ValueError("phrase-only authorization requires one explicit source")
        return selected
    if render_scope not in {"reviewed_phrase_excerpt", "complete_state_timeline"}:
        raise ValueError("dry render authorization scope is unsupported")
    if phrase_id is not None:
        raise ValueError("multi-phrase authorization cannot bind one phrase")
    if (
        source_map["status"] != "complete_unrendered"
        or source_map["unresolved_phrases"]
        or source_map["undecided_phrase_ids"]
        or [row["phrase_id"] for row in source_map["segments"]] != phrases
    ):
        raise ValueError(
            "multi-phrase authorization requires every phrase in the reviewed roster"
        )
    if render_scope == "reviewed_phrase_excerpt" and len(phrases) < 2:
        raise ValueError("reviewed phrase excerpt requires at least two phrases")
    return list(source_map["segments"])


def _load_exact_state(path: str | Path) -> tuple[Path, Path, dict[str, Any]]:
    manifest = Path(path).expanduser().absolute()
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Musical State manifest must be a regular local file")
    root = manifest.parent.resolve()
    return manifest, root, validate_musical_state(manifest, root=root)


def _source_inventory(
    state: Mapping[str, Any], root: Path
) -> dict[str, dict[str, Any]]:
    vocal = state["vocal_performance_state"]
    rows: list[Mapping[str, Any]] = [*vocal["takes"]]
    if isinstance(vocal.get("reference"), Mapping):
        rows.append(vocal["reference"])
    rows.extend(vocal.get("phrase_captures", []))
    inventory: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = str(row["source_id"])
        record = row["audio"]
        relative = PurePosixPath(str(record["path"]))
        path = (root / Path(*relative.parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("vocal source escapes its Musical State") from exc
        if not path.is_file() or path.is_symlink():
            raise ValueError("vocal source is missing or linked")
        if row.get("source_class") == "reference_vocal":
            source_class = "reference_vocal"
        else:
            source_class = str(row["source_class"])
        inventory[source_id] = {
            "source_id": source_id,
            "source_class": source_class,
            "audio": dict(record),
            "audio_properties": dict(row["audio_properties"]),
            "path": path,
        }
    return inventory


def _render_horizon(
    state: Mapping[str, Any], inventory: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    reference = state["vocal_performance_state"].get("reference")
    if isinstance(reference, Mapping):
        source = inventory[str(reference["source_id"])]
        properties = source["audio_properties"]
        return {
            "authority": "exact_authorised_reference_vocal_horizon",
            "reference_source_id": source["source_id"],
            "source_audio_sha256": source["audio"]["sha256"],
            "sample_rate": properties["sample_rate"],
            "channels": properties["channels"],
            "frames": properties["frames"],
        }
    takes = [
        row for row in inventory.values() if row["source_class"] == "human_vocal_take"
    ]
    geometries = {
        (
            row["audio_properties"]["sample_rate"],
            row["audio_properties"]["channels"],
            row["audio_properties"]["frames"],
        )
        for row in takes
    }
    if len(geometries) != 1:
        raise ValueError(
            "without a reference vocal, all common-zero takes must share one exact horizon"
        )
    sample_rate, channels, frames = next(iter(geometries))
    return {
        "authority": "identical_common_zero_human_take_horizon",
        "source_audio_sha256": document_sha256(
            {"take_audio_sha256": sorted(row["audio"]["sha256"] for row in takes)}
        ),
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
    }


def _join_plan(
    segments: list[dict[str, Any]], horizon_frames: int, sample_rate: int
) -> list[dict[str, Any]]:
    if not segments:
        raise ValueError("dry vocal comp requires at least one phrase segment")
    joins: list[dict[str, Any]] = []
    maximum = max(2, round(_MAX_FADE_SECONDS * sample_rate))

    first = segments[0]
    opening_gap = first["destination_start_frame"]
    if opening_gap:
        used = min(maximum, opening_gap, first["available_pre_guard_frames"])
        if used < 2:
            raise ValueError("opening timeline gap lacks a safe retained source handle")
        first["used_pre_guard_frames"] = used
        joins.append(
            {
                "join_id": "join-opening",
                "kind": "equal_power_silence_to_source",
                "gap_start_frame": 0,
                "gap_end_frame": first["destination_start_frame"],
                "left_phrase_id": None,
                "right_phrase_id": first["phrase_id"],
                "right_guard_frames": used,
                "gain_curve": "sin_0_to_pi_over_2",
            }
        )

    for index, (left, right) in enumerate(zip(segments, segments[1:]), 1):
        gap = right["destination_start_frame"] - left["destination_end_frame"]
        if gap < 0:
            raise ValueError("reviewed vocal phrases overlap")
        if gap == 0:
            if (
                left["source_id"] != right["source_id"]
                or left["source_end_frame"] != right["source_start_frame"]
            ):
                raise ValueError(
                    "contiguous source switch requires a separately reviewed join"
                )
            joins.append(
                {
                    "join_id": f"join-{index:03d}",
                    "kind": "exact_continuous_same_source",
                    "gap_start_frame": left["destination_end_frame"],
                    "gap_end_frame": right["destination_start_frame"],
                    "left_phrase_id": left["phrase_id"],
                    "right_phrase_id": right["phrase_id"],
                    "left_guard_frames": 0,
                    "right_guard_frames": 0,
                    "gain_curve": "unity",
                }
            )
            continue
        if gap < 4:
            raise ValueError("timeline gap is too short for two explicit guard fades")
        allowance = gap // 2
        left_used = min(maximum, allowance, left["available_post_guard_frames"])
        right_used = min(maximum, allowance, right["available_pre_guard_frames"])
        if left_used < 2 or right_used < 2:
            raise ValueError("timeline gap lacks safe retained source handles")
        left["used_post_guard_frames"] = left_used
        right["used_pre_guard_frames"] = right_used
        joins.append(
            {
                "join_id": f"join-{index:03d}",
                "kind": "separated_equal_power_guard_fades",
                "gap_start_frame": left["destination_end_frame"],
                "gap_end_frame": right["destination_start_frame"],
                "left_phrase_id": left["phrase_id"],
                "right_phrase_id": right["phrase_id"],
                "left_guard_frames": left_used,
                "right_guard_frames": right_used,
                "gain_curve": "cos_out_and_sin_in_with_explicit_zero_middle",
            }
        )

    last = segments[-1]
    closing_gap = horizon_frames - last["destination_end_frame"]
    if closing_gap:
        used = min(maximum, closing_gap, last["available_post_guard_frames"])
        if used < 2:
            raise ValueError("closing timeline gap lacks a safe retained source handle")
        last["used_post_guard_frames"] = used
        joins.append(
            {
                "join_id": "join-closing",
                "kind": "equal_power_source_to_silence",
                "gap_start_frame": last["destination_end_frame"],
                "gap_end_frame": horizon_frames,
                "left_phrase_id": last["phrase_id"],
                "right_phrase_id": None,
                "left_guard_frames": used,
                "gain_curve": "cos_0_to_pi_over_2",
            }
        )
    return joins


def _render_join(
    join: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    decoded: Mapping[str, Any],
    output: Any,
    numpy: Any,
) -> None:
    by_phrase = {row["phrase_id"]: row for row in segments}
    kind = join["kind"]
    if kind == "exact_continuous_same_source":
        return
    left_id = join.get("left_phrase_id")
    if left_id is not None:
        left = by_phrase[left_id]
        count = int(join["left_guard_frames"])
        source = decoded[left["source_id"]]
        values = source[left["source_end_frame"] : left["source_end_frame"] + count]
        weights = numpy.cos(numpy.linspace(0.0, math.pi / 2.0, count))[:, None]
        destination_start = left["destination_end_frame"]
        output[destination_start : destination_start + count] = values * weights
    right_id = join.get("right_phrase_id")
    if right_id is not None:
        right = by_phrase[right_id]
        count = int(join["right_guard_frames"])
        source = decoded[right["source_id"]]
        values = source[
            right["source_start_frame"] - count : right["source_start_frame"]
        ]
        weights = numpy.sin(numpy.linspace(0.0, math.pi / 2.0, count))[:, None]
        destination_end = right["destination_start_frame"]
        output[destination_end - count : destination_end] = values * weights


def _edit_map(
    plan: Mapping[str, Any], audio_record: Mapping[str, Any]
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": VOCAL_DRY_EDIT_MAP_SCHEMA,
        "status": _result_status(plan["render_scope"]),
        "render_scope": plan["render_scope"],
        "phrase_id": plan["phrase_id"],
        "binding": {
            "render_plan_sha256": plan["document_sha256"],
            "musical_state_sha256": plan["binding"]["musical_state_sha256"],
            "vocal_source_map_sha256": plan["binding"]["vocal_source_map_sha256"],
            "render_authorization_sha256": plan["binding"][
                "render_authorization_sha256"
            ],
            "output_audio_sha256": audio_record["sha256"],
        },
        "horizon": plan["horizon"],
        "segments": plan["segments"],
        "joins": plan["joins"],
        "processing": plan["render_policy"],
        "review_status": "not_reviewed",
        "playback_creates_decision": False,
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _validate_plan(
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
    render_authorization: Mapping[str, Any],
) -> dict[str, Any]:
    document = dict(plan)
    _verify_document(document, VOCAL_DRY_RENDER_PLAN_SCHEMA, "dry render plan")
    if set(document) != {
        "schema",
        "status",
        "render_scope",
        "phrase_id",
        "method_natures",
        "binding",
        "horizon",
        "coverage",
        "segments",
        "joins",
        "render_policy",
        "authority",
        "model_used",
        "training_used",
        "network_used",
        "effects",
        "document_sha256",
    }:
        raise ValueError("dry render plan fields changed")
    render_scope = _validate_dry_plan_identity(
        document,
        state=state,
        source_map=source_map,
        render_authorization=render_authorization,
    )
    _validate_dry_plan_coverage(
        document, state=state, source_map=source_map, render_scope=render_scope
    )
    _validate_dry_plan_policy(document)
    _reject_paths(document)
    return document


def _validate_dry_plan_identity(
    document: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
    render_authorization: Mapping[str, Any],
) -> str:
    render_scope = document.get("render_scope")
    phrase_id = document.get("phrase_id")
    expected_status = (
        _plan_status(render_scope) if render_scope in _RENDER_SCOPES else None
    )
    if expected_status is None or document.get("status") != expected_status:
        raise ValueError("dry render plan scope or status is not render-ready")
    if render_scope == "phrase_only":
        if not isinstance(phrase_id, str) or phrase_id not in {
            row["phrase_id"] for row in state["structure"]["phrases"]
        }:
            raise ValueError("dry phrase preview binds an unknown phrase")
    elif phrase_id is not None:
        raise ValueError("multi-phrase dry render cannot claim a phrase-only scope")
    if document.get("binding") != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
        "vocal_source_map_schema": VOCAL_RENDER_SOURCE_MAP_SCHEMA,
        "vocal_source_map_sha256": source_map["document_sha256"],
        "render_authorization_schema": VOCAL_DRY_RENDER_AUTHORIZATION_SCHEMA,
        "render_authorization_sha256": render_authorization["document_sha256"],
    }:
        raise ValueError("dry render plan binding changed")
    return str(render_scope)


def _validate_dry_plan_coverage(
    document: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    source_map: Mapping[str, Any],
    render_scope: str,
) -> None:
    expected_rendered = (
        1 if render_scope == "phrase_only" else len(state["structure"]["phrases"])
    )
    if document.get("coverage") != {
        "reviewed_roster_phrase_count": len(state["structure"]["phrases"]),
        "rendered_phrase_count": expected_rendered,
        "source_segment_count": expected_rendered,
        "whole_song_coverage_claimed": render_scope == "complete_state_timeline",
        "unresolved_count": source_map["coverage"]["unresolved_count"],
        "undecided_count": source_map["coverage"]["undecided_count"],
    }:
        raise ValueError("dry render plan phrase coverage changed")
    if render_scope == "complete_state_timeline" and (
        source_map["status"] != "complete_unrendered"
        or source_map["unresolved_phrases"]
        or source_map["undecided_phrase_ids"]
        or state.get("structure", {}).get("coverage_scope")
        != "reviewed_complete_intended_vocal_roster"
    ):
        raise ValueError("complete dry render lacks complete roster authority")
    if render_scope == "reviewed_phrase_excerpt" and (
        len(state["structure"]["phrases"]) < 2
        or source_map["status"] != "complete_unrendered"
        or source_map["unresolved_phrases"]
        or source_map["undecided_phrase_ids"]
    ):
        raise ValueError("reviewed phrase excerpt lacks complete excerpt authority")


def _validate_dry_plan_policy(document: Mapping[str, Any]) -> None:
    if document.get("authority") != {
        "source_choices_are_explicit_human_decisions": True,
        "render_confirmation_required": True,
        "playback_creates_decision": False,
        "join_review_complete": False,
        "correction_authorised": False,
    }:
        raise ValueError("dry render plan authority expanded")
    policy = document.get("render_policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(key) is not False
        for key in (
            "resampling",
            "timing_correction",
            "pitch_correction",
            "gain_trim",
            "normalisation",
            "limiting",
            "clipping_permitted",
        )
    ):
        raise ValueError("dry render plan enables unsupported processing")
    if (
        document.get("method_natures") != ["D", "H"]
        or document.get("model_used") is not False
        or document.get("training_used") is not False
        or document.get("network_used") is not False
        or document.get("effects") != _plan_effects()
    ):
        raise ValueError("dry render plan claims unsupported effects")


def validate_dry_vocal_comp_result(
    result: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one path-free result receipt against its exact render plan."""

    document = dict(result)
    _verify_document(document, VOCAL_DRY_RENDER_RESULT_SCHEMA, "dry render result")
    if set(document) != {
        "schema",
        "status",
        "render_scope",
        "phrase_id",
        "method_natures",
        "binding",
        "render_confirmation",
        "artifacts",
        "signal",
        "review",
        "processing",
        "model_used",
        "training_used",
        "network_used",
        "effects",
        "document_sha256",
    }:
        raise ValueError("dry render result fields changed")
    binding = _validate_dry_result_identity(document, plan=plan)
    _validate_dry_result_signal_and_review(document, plan=plan)
    audio = _validate_dry_result_artifacts(document, plan=plan)
    _validate_dry_result_derived_artifacts(
        document, plan=plan, binding=binding, audio=audio
    )
    _validate_dry_result_effects(document, plan=plan)
    return document


def _validate_dry_result_identity(
    document: Mapping[str, Any], *, plan: Mapping[str, Any]
) -> Mapping[str, Any]:
    expected_status = _result_status(plan["render_scope"])
    if (
        document.get("status") != expected_status
        or document.get("render_scope") != plan["render_scope"]
        or document.get("phrase_id") != plan["phrase_id"]
    ):
        raise ValueError("dry render result status changed")
    binding = document.get("binding")
    if not isinstance(binding, Mapping) or set(binding) != {
        "musical_state_sha256",
        "vocal_source_map_sha256",
        "render_authorization_sha256",
        "render_plan_sha256",
        "edit_map_document_sha256",
    }:
        raise ValueError("dry render result binding fields changed")
    if binding != {
        "musical_state_sha256": plan["binding"]["musical_state_sha256"],
        "vocal_source_map_sha256": plan["binding"]["vocal_source_map_sha256"],
        "render_authorization_sha256": plan["binding"]["render_authorization_sha256"],
        "render_plan_sha256": plan["document_sha256"],
        "edit_map_document_sha256": binding.get("edit_map_document_sha256"),
    } or not _is_sha256(binding.get("edit_map_document_sha256")):
        raise ValueError("dry render result exact binding changed")
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError("dry render result method nature changed")
    return binding


def _validate_dry_result_signal_and_review(
    document: Mapping[str, Any], *, plan: Mapping[str, Any]
) -> None:
    expected_confirmation_scope = _confirmation_scope(plan["render_scope"])
    if document.get("render_confirmation") != {
        "explicit": True,
        "scope": expected_confirmation_scope,
    }:
        raise ValueError("dry render result lacks explicit confirmation")
    signal = document.get("signal")
    if (
        not isinstance(signal, Mapping)
        or set(signal) != {"sample_peak", "finite", "clipped", "normalised", "limited"}
        or signal.get("finite") is not True
        or signal.get("clipped") is not False
        or signal.get("normalised") is not False
        or signal.get("limited") is not False
        or not isinstance(signal.get("sample_peak"), (int, float))
        or isinstance(signal.get("sample_peak"), bool)
        or not 0.0 <= float(signal["sample_peak"]) < 1.0
    ):
        raise ValueError("dry render result signal evidence changed")
    if document.get("review") != {
        "status": "not_reviewed",
        "playback_creates_decision": False,
        "join_review_complete": False,
        "selected_for_product": False,
    }:
        raise ValueError("dry render result cannot claim review or selection")
    if document.get("processing") != {
        "pitch_correction": False,
        "timing_correction": False,
        "resampling": False,
        "gain_trim": False,
        "normalisation": False,
        "limiting": False,
    }:
        raise ValueError("dry render result processing declaration changed")


def _validate_dry_result_artifacts(
    document: Mapping[str, Any], *, plan: Mapping[str, Any]
) -> Mapping[str, Any]:
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "dry_vocal_wav",
        "edit_map",
        "review_html",
    }:
        raise ValueError("dry render result artifact roster changed")
    audio = artifacts.get("dry_vocal_wav")
    expected_audio_path = f"AUDIO/{_audio_name(plan['render_scope'])}"
    if not isinstance(audio, Mapping) or set(audio) != {
        "sha256",
        "bytes",
        "geometry",
        "relative_path",
        "encoding",
    }:
        raise ValueError("dry render audio artifact fields changed")
    if (
        not _is_sha256(audio.get("sha256"))
        or not _positive_integer(audio.get("bytes"))
        or audio.get("geometry")
        != {
            "sample_rate": plan["horizon"]["sample_rate"],
            "channels": plan["horizon"]["channels"],
            "frames": plan["horizon"]["frames"],
        }
        or audio.get("relative_path") != expected_audio_path
        or audio.get("encoding") != "WAV_PCM_24"
    ):
        raise ValueError("dry render audio artifact identity or geometry changed")
    for key, expected_path in (
        ("edit_map", "TECHNICAL/dry-vocal-edit-map.json"),
        ("review_html", "REVIEW/dry-vocal-comp-review.html"),
    ):
        record = artifacts.get(key)
        if (
            not isinstance(record, Mapping)
            or set(record) != {"relative_path", "bytes", "sha256"}
            or record.get("relative_path") != expected_path
            or not _positive_integer(record.get("bytes"))
            or not _is_sha256(record.get("sha256"))
        ):
            raise ValueError(f"dry render {key} artifact record changed")
    return audio


def _validate_dry_result_derived_artifacts(
    document: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    binding: Mapping[str, Any],
    audio: Mapping[str, Any],
) -> None:
    artifacts = document["artifacts"]
    expected_edit_map = _edit_map(
        plan,
        {
            "sha256": audio["sha256"],
            "bytes": audio["bytes"],
            "geometry": audio["geometry"],
        },
    )
    expected_edit_map_file_sha256 = hashlib.sha256(
        canonical_json_bytes(expected_edit_map)
    ).hexdigest()
    if (
        binding["edit_map_document_sha256"] != expected_edit_map["document_sha256"]
        or artifacts["edit_map"]["sha256"] != expected_edit_map_file_sha256
        or artifacts["edit_map"]["bytes"]
        != len(canonical_json_bytes(expected_edit_map))
    ):
        raise ValueError("dry render edit-map binding or artifact changed")
    expected_review_bytes = _review_html(expected_edit_map).encode("utf-8")
    if (
        artifacts["review_html"]["bytes"] != len(expected_review_bytes)
        or artifacts["review_html"]["sha256"]
        != hashlib.sha256(expected_review_bytes).hexdigest()
    ):
        raise ValueError("dry render review artifact changed")


def _validate_dry_result_effects(
    document: Mapping[str, Any], *, plan: Mapping[str, Any]
) -> None:
    expected_effects = {
        "source_mutated": False,
        "source_choice_created": False,
        "audio_comp_rendered": True,
        "join_preview_rendered": bool(plan["joins"]),
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "normalisation_applied": False,
        "limiting_applied": False,
        "human_review_created": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }
    if document.get("effects") != expected_effects:
        raise ValueError("dry render result effects changed")
    if (
        document.get("model_used") is not False
        or document.get("training_used") is not False
        or document.get("network_used") is not False
    ):
        raise ValueError(
            "dry render result cannot claim model, training or network use"
        )


def _verify_source_stability(
    inventory: Mapping[str, Mapping[str, Any]], hashes: Mapping[str, str]
) -> None:
    for source_id, expected in hashes.items():
        source = inventory[source_id]
        path = source["path"]
        if (
            path.stat().st_size != source["audio"]["bytes"]
            or file_sha256(path) != expected
        ):
            raise ValueError("selected vocal source changed during dry rendering")
        if expected != source["audio"]["sha256"]:
            raise ValueError("selected vocal source no longer matches Musical State")


def _inspect_output(path: Path) -> dict[str, Any]:
    soundfile, _numpy = _audio_dependencies()
    info = soundfile.info(path)
    if info.format != "WAV" or info.subtype != "PCM_24":
        raise ValueError("dry vocal comp must remain WAV PCM_24")
    return {
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        "geometry": {
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "frames": int(info.frames),
        },
    }


def _review_html(edit_map: Mapping[str, Any]) -> str:
    render_scope = edit_map["render_scope"]
    title = {
        "phrase_only": "Dry vocal phrase preview — review required",
        "reviewed_phrase_excerpt": "Dry vocal excerpt preview — review required",
        "complete_state_timeline": "Dry vocal comp — review required",
    }[render_scope]
    notice = {
        "phrase_only": (
            "Phrase preview complete but unreviewed. This is only the exact reviewed "
            "phrase window; it makes no whole-song coverage claim."
        ),
        "reviewed_phrase_excerpt": (
            "Reviewed phrase excerpt rendered but unreviewed. It spans only the "
            "reviewed excerpt and makes no whole-song coverage claim."
        ),
        "complete_state_timeline": "Complete state-timeline render, but unreviewed.",
    }[render_scope]
    audio_name = _audio_name(render_scope)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['phrase_id']))}</td>"
        f"<td>{html.escape(str(row['outcome']))}</td>"
        f"<td>{html.escape(str(row['source_id']))}</td>"
        f"<td>{row['destination_start_frame']}–{row['destination_end_frame']}</td>"
        "</tr>"
        for row in edit_map["segments"]
    )
    joins = "".join(
        f"<li>{html.escape(str(row['join_id']))}: {html.escape(str(row['kind']))}</li>"
        for row in edit_map["joins"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font:16px system-ui;max-width:920px;margin:2rem auto;padding:0 1rem;background:#101417;color:#eef4f7}}
.notice{{padding:1rem;border:1px solid #5b7380;border-radius:.7rem;background:#182126}}
audio{{width:100%;margin:1rem 0}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.6rem;border-bottom:1px solid #40515a;text-align:left}}code{{color:#9ce1ff}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="notice"><strong>{html.escape(notice)}</strong> This is the exact dry,
uncorrected audio. Playback creates no decision. No tuning, timing correction,
gain trim, normalisation or limiting was used.</div>
<audio controls preload="metadata" src="../AUDIO/{audio_name}"></audio>
<p>Render identity: <code>{html.escape(str(edit_map["document_sha256"]))}</code></p>
<h2>Phrase source map</h2><table><thead><tr><th>Phrase</th><th>Outcome</th><th>Source</th><th>Destination frames</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Technical joins</h2><ul>{joins}</ul>
<p>These joins have not been accepted. Continue to a separate listening decision;
do not infer approval from this page being opened or played.</p>
</body></html>"""


def _plan_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "source_choice_created": False,
        "audio_comp_rendered": False,
        "join_preview_rendered": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "normalisation_applied": False,
        "limiting_applied": False,
        "human_review_created": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }


def _verify_document(document: Mapping[str, Any], schema: str, label: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"unsupported {label} schema")
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 does not match")


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in {"path", "absolute_path", "relative_path"}:
                raise ValueError("portable dry vocal plan may not contain paths")
            _reject_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_paths(item)


def _verify_dry_package_roster(root: Path, expected_files: set[str]) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("dry vocal package must be a regular local directory")
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise PermissionError("dry vocal package must remain owner-only")
    expected_directories = {"AUDIO", "REVIEW", "TECHNICAL"}
    observed_root = {item.name for item in root.iterdir()}
    if observed_root != expected_directories:
        raise ValueError("dry vocal package directory roster changed")
    result: dict[str, Path] = {}
    for directory_name in sorted(expected_directories):
        directory = root / directory_name
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("dry vocal package directory is missing or linked")
        if stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise PermissionError("dry vocal package directory must remain owner-only")
        expected_names = {
            PurePosixPath(relative).name
            for relative in expected_files
            if PurePosixPath(relative).parent.as_posix() == directory_name
        }
        observed_names = {item.name for item in directory.iterdir()}
        if observed_names != expected_names:
            raise ValueError("dry vocal package file roster changed")
        for name in sorted(expected_names):
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("dry vocal package artifact is missing or linked")
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise PermissionError(
                    "dry vocal package artifact must remain owner-only"
                )
            result[f"{directory_name}/{name}"] = path
    if set(result) != expected_files:
        raise ValueError("dry vocal package fixed artifact roster changed")
    return result


def _read_stable_regular_file(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular local file")
    before = path.stat()
    if before.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds the verification size limit")
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} could not be read") from exc
    after = path.stat()
    if (
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_size,
        after.st_mtime_ns,
    ) or len(value) != before.st_size:
        raise ValueError(f"{label} changed during round-trip verification")
    return value


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _write_private(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive_integer(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _audio_dependencies() -> tuple[Any, Any]:
    try:
        import numpy
        import soundfile
    except ImportError as exc:  # pragma: no cover - core runtime dependency
        raise RuntimeError("dry vocal rendering requires NumPy and SoundFile") from exc
    return soundfile, numpy


__all__ = [
    "VOCAL_DRY_EDIT_MAP_SCHEMA",
    "VOCAL_DRY_RENDER_AUTHORIZATION_SCHEMA",
    "VOCAL_DRY_RENDER_PLAN_SCHEMA",
    "VOCAL_DRY_RENDER_RESULT_SCHEMA",
    "VOCAL_DRY_ROUND_TRIP_VERIFICATION_SCHEMA",
    "create_dry_vocal_comp_plan",
    "create_dry_vocal_render_authorization",
    "render_dry_vocal_comp",
    "validate_dry_vocal_comp_result",
    "validate_dry_vocal_render_authorization",
    "verify_dry_vocal_comp_round_trip",
]
