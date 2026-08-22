"""Exact carried-base plus one-phrase dry vocal continuation previews.

This bounded bridge exists for iterative vocal work.  It preserves one exact
owner-reviewed usable-base excerpt and appends one exact human phrase capture
at the next reviewed phrase boundary.  Planning and authorization do not write
audio.  Rendering is a dry sample concatenation only: no fade, normalization,
limiting, timing change, pitch change, resampling or training effect.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .audio_formats import file_sha256
from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import canonical_json_bytes, document_sha256
from .vocal_phrase_decision import validate_phrase_decision


VOCAL_CONTINUATION_PLAN_SCHEMA = "sunofriend.vocal-dry-continuation-plan.v0"
VOCAL_CONTINUATION_AUTHORIZATION_SCHEMA = (
    "sunofriend.vocal-dry-continuation-render-authorization.v0"
)
VOCAL_CONTINUATION_RESULT_SCHEMA = "sunofriend.vocal-dry-continuation-result.v0"
VOCAL_CONTINUATION_EDIT_MAP_SCHEMA = "sunofriend.vocal-dry-continuation-edit-map.v0"
VOCAL_CONTINUATION_VERIFICATION_SCHEMA = (
    "sunofriend.vocal-dry-continuation-verification.v0"
)
VOCAL_CONTINUATION_REVIEW_SCHEMA = "sunofriend.vocal-dry-continuation-owner-review.v0"

_BASE_BINDING_SCHEMA = "sunofriend.private-vocal-continuation-base-binding.v0"
_BASE_REVIEW_SCHEMA = "sunofriend.private-vocal-excerpt-review-result.v0"
_BASE_RECEIPT_SCHEMA = "sunofriend.private-vocal-tail-reviewed-render-result.v0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_vocal_continuation_plan(
    base_binding_path: str | Path,
    musical_state_manifest: str | Path,
    phrase_decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one path-free, no-effect continuation plan."""

    base_path, base, base_audio, base_review, base_receipt = _load_base(
        base_binding_path
    )
    state_path, state_root, state = _load_state(musical_state_manifest)
    decision = validate_phrase_decision(phrase_decision, state)
    if decision["outcome"] != "human_take":
        raise ValueError("continuation requires one explicit human_take decision")
    if decision["selected_source_class"] != "human_vocal_phrase_capture":
        raise ValueError("continuation requires one browser phrase capture")

    phrases = state["structure"]["phrases"]
    base_phrase_ids = list(base["scope"]["phrase_ids"])
    if len(base_phrase_ids) < 1 or len(base_phrase_ids) >= len(phrases):
        raise ValueError("usable base must precede one reviewed continuation phrase")
    expected_base = [row["phrase_id"] for row in phrases[: len(base_phrase_ids)]]
    if base_phrase_ids != expected_base:
        raise ValueError("usable base does not cover the leading reviewed phrases")
    appended = phrases[len(base_phrase_ids)]
    if decision["phrase"]["phrase_id"] != appended["phrase_id"]:
        raise ValueError("decision is not for the next reviewed phrase")
    if len(phrases) != len(base_phrase_ids) + 1:
        raise ValueError("bounded continuation must cover exactly one new phrase")
    if float(base["scope"]["song_start_seconds"]) != float(
        phrases[0]["start_seconds"]
    ) or float(base["scope"]["song_end_seconds"]) != float(appended["start_seconds"]):
        raise ValueError("usable base clock does not end at the next phrase boundary")

    capture = _capture_for_decision(state, decision)
    capture_audio = _artifact_path(state_root, capture["audio"], "capture audio")
    base_properties = _pcm24_properties(base_audio)
    capture_properties = _pcm24_properties(capture_audio)
    if (
        base_properties["sample_rate"] != capture_properties["sample_rate"]
        or base_properties["channels"] != capture_properties["channels"]
    ):
        raise ValueError("usable base and phrase capture must share one exact clock")
    sample_rate = base_properties["sample_rate"]
    expected_base_frames = round(
        (
            float(base["scope"]["song_end_seconds"])
            - float(base["scope"]["song_start_seconds"])
        )
        * sample_rate
    )
    if base_properties["frames"] != expected_base_frames:
        raise ValueError("usable-base audio does not match its reviewed window")
    placement = capture["placement"]
    source_start = _integer(placement["source_phrase_start_frame"], "source start")
    source_end = _integer(placement["source_phrase_end_frame"], "source end")
    expected_phrase_frames = round(
        (float(appended["end_seconds"]) - float(appended["start_seconds"]))
        * sample_rate
    )
    if source_end - source_start != expected_phrase_frames:
        raise ValueError("selected capture does not match the reviewed phrase duration")
    if not 0 <= source_start < source_end <= capture_properties["frames"]:
        raise ValueError("selected capture phrase slice escapes its source")

    artifacts = base["artifacts"]
    document: dict[str, Any] = {
        "schema": VOCAL_CONTINUATION_PLAN_SCHEMA,
        "status": "ready_dry_uncorrected_three_phrase_preview",
        "method_natures": ["D", "H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
            "phrase_decision_schema": decision["schema"],
            "phrase_decision_sha256": decision["document_sha256"],
            "base_binding_schema": _BASE_BINDING_SCHEMA,
            "base_binding_sha256": base["document_sha256"],
            "base_audio_sha256": artifacts["audio"]["sha256"],
            "base_review_sha256": base_review["document_sha256"],
            "base_render_receipt_sha256": base_receipt["document_sha256"],
        },
        "scope": {
            "phrase_ids": [row["phrase_id"] for row in phrases],
            "carried_base_phrase_ids": base_phrase_ids,
            "appended_phrase_id": appended["phrase_id"],
            "song_start_seconds": float(base["scope"]["song_start_seconds"]),
            "song_end_seconds": float(appended["end_seconds"]),
            "render_scope": "reviewed_three_phrase_excerpt_preview",
        },
        "clock": {
            "sample_rate": sample_rate,
            "channels": base_properties["channels"],
            "base_frames": base_properties["frames"],
            "appended_frames": expected_phrase_frames,
            "output_frames": base_properties["frames"] + expected_phrase_frames,
        },
        "segments": [
            {
                "kind": "carried_reviewed_usable_base",
                "phrase_ids": base_phrase_ids,
                "source_audio_sha256": artifacts["audio"]["sha256"],
                "source_start_frame": 0,
                "source_end_frame": base_properties["frames"],
                "destination_start_frame": 0,
                "destination_end_frame": base_properties["frames"],
                "review_sha256": base_review["document_sha256"],
            },
            {
                "kind": "explicit_human_phrase_capture",
                "phrase_ids": [appended["phrase_id"]],
                "source_id": decision["selected_source_id"],
                "source_audio_sha256": decision["selected_source_sha256"],
                "source_start_frame": source_start,
                "source_end_frame": source_end,
                "destination_start_frame": base_properties["frames"],
                "destination_end_frame": (
                    base_properties["frames"] + expected_phrase_frames
                ),
                "decision_sha256": decision["document_sha256"],
            },
        ],
        "join": {
            "song_time_seconds": float(appended["start_seconds"]),
            "destination_frame": base_properties["frames"],
            "policy": "exact_boundary_concatenation_no_fade",
            "review_status": "not_reviewed",
            "automatic_join_acceptance": False,
        },
        "processing": _no_processing(),
        "authority": {
            "plan_only": True,
            "separate_owner_render_authorization_required": True,
            "usable_base_carried_without_decision_migration": True,
            "phrase_decision_revalidated": True,
            "join_remains_unreviewed": True,
            "release_authorized": False,
        },
        "effects": _no_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    _reject_paths(document)
    # Keep the loaded paths live until all identity checks above complete.
    if base_path.parent == state_path.parent and base_path == state_path:
        raise ValueError("base binding and musical state must be distinct artifacts")
    return document


def validate_vocal_continuation_plan(
    plan: Mapping[str, Any],
    base_binding_path: str | Path,
    musical_state_manifest: str | Path,
    phrase_decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Recreate the exact plan and reject stale or altered projections."""

    document = dict(plan)
    _verify_document(document, VOCAL_CONTINUATION_PLAN_SCHEMA, "continuation plan")
    expected = create_vocal_continuation_plan(
        base_binding_path, musical_state_manifest, phrase_decision
    )
    if document != expected:
        raise ValueError("vocal continuation plan is stale or altered")
    return document


def create_vocal_continuation_render_authorization(
    plan: Mapping[str, Any],
    *,
    confirm_dry_uncorrected_preview: bool = False,
) -> dict[str, Any]:
    """Record explicit owner authority for one exact preview plan."""

    checked = _validate_plan_shape(plan)
    if confirm_dry_uncorrected_preview is not True:
        raise ValueError("owner must explicitly authorize the dry continuation preview")
    return _authorization_document(checked)


def _authorization_document(plan: Mapping[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": VOCAL_CONTINUATION_AUTHORIZATION_SCHEMA,
        "status": "explicit_owner_authorization",
        "method_natures": ["H"],
        "binding": {
            "plan_schema": VOCAL_CONTINUATION_PLAN_SCHEMA,
            "plan_sha256": plan["document_sha256"],
            "musical_state_sha256": plan["binding"]["musical_state_sha256"],
            "phrase_decision_sha256": plan["binding"]["phrase_decision_sha256"],
            "base_audio_sha256": plan["binding"]["base_audio_sha256"],
        },
        "owner_confirmation": {
            "one_dry_uncorrected_three_phrase_preview": True,
            "exact_boundary_join_may_be_auditioned": True,
            "join_is_not_accepted_by_rendering": True,
        },
        "authority_limits": {
            "one_exact_plan_only": True,
            "pitch_correction_authorized": False,
            "timing_correction_authorized": False,
            "normalisation_authorized": False,
            "limiting_authorized": False,
            "join_acceptance_authorized": False,
            "release_authorized": False,
            "training_authorized": False,
        },
        "effects": _no_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def validate_vocal_continuation_render_authorization(
    authorization: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _validate_plan_shape(plan)
    document = dict(authorization)
    _verify_document(
        document,
        VOCAL_CONTINUATION_AUTHORIZATION_SCHEMA,
        "continuation render authorization",
    )
    expected = _authorization_document(checked)
    if document != expected:
        raise ValueError("continuation render authorization is stale or altered")
    return document


def render_vocal_continuation(
    base_binding_path: str | Path,
    musical_state_manifest: str | Path,
    phrase_decision: Mapping[str, Any],
    plan: Mapping[str, Any],
    authorization: Mapping[str, Any],
    *,
    out_dir: str | Path,
    expected_plan_sha256: str,
    confirm_dry_uncorrected_render: bool = False,
) -> dict[str, Any]:
    """Render one fresh owner-only dry continuation listening package."""

    checked = validate_vocal_continuation_plan(
        plan, base_binding_path, musical_state_manifest, phrase_decision
    )
    checked_authorization = validate_vocal_continuation_render_authorization(
        authorization, checked
    )
    if expected_plan_sha256 != checked["document_sha256"]:
        raise ValueError("expected continuation plan SHA-256 changed")
    if confirm_dry_uncorrected_render is not True:
        raise ValueError("dry continuation render requires separate confirmation")

    base_path, _base, base_audio, _review, _receipt = _load_base(base_binding_path)
    _state_path, state_root, state = _load_state(musical_state_manifest)
    decision = validate_phrase_decision(phrase_decision, state)
    capture = _capture_for_decision(state, decision)
    capture_audio = _artifact_path(state_root, capture["audio"], "capture audio")

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"continuation output already exists: {destination}")
    for protected_root in (base_path.parent.resolve(), state_root.resolve()):
        if destination == protected_root or protected_root in destination.parents:
            raise ValueError(
                "continuation output must stay outside immutable source evidence"
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        audio_dir = temporary / "AUDIO"
        technical_dir = temporary / "TECHNICAL"
        review_dir = temporary / "REVIEW"
        for folder in (audio_dir, technical_dir, review_dir):
            folder.mkdir(mode=0o700)

        base_values, sample_rate = _read_audio(base_audio)
        capture_values, capture_rate = _read_audio(capture_audio)
        if sample_rate != capture_rate:
            raise ValueError("source sample rate changed before rendering")
        appended = checked["segments"][1]
        phrase_values = capture_values[
            appended["source_start_frame"] : appended["source_end_frame"]
        ]
        if phrase_values.shape[0] != checked["clock"]["appended_frames"]:
            raise ValueError("selected phrase slice changed before rendering")
        _np, sf = _audio_dependencies()
        combined = _np.concatenate((base_values, phrase_values), axis=0)
        if combined.shape != (
            checked["clock"]["output_frames"],
            checked["clock"]["channels"],
        ):
            raise ValueError("continuation output geometry changed")
        if not _np.isfinite(combined).all():
            raise ValueError("continuation contains non-finite samples")
        peak = float(_np.max(_np.abs(combined))) if combined.size else 0.0
        if peak >= 1.0:
            raise ValueError("continuation would clip at full scale")

        base_copy = audio_dir / "carried-two-phrase-usable-base.wav"
        phrase_copy = audio_dir / "selected-phrase-3-dry.wav"
        continuation = audio_dir / "dry-three-phrase-continuation.wav"
        shutil.copyfile(base_audio, base_copy)
        os.chmod(base_copy, 0o600)
        sf.write(
            phrase_copy,
            phrase_values,
            sample_rate,
            format="WAV",
            subtype="PCM_24",
        )
        os.chmod(phrase_copy, 0o600)
        sf.write(
            continuation,
            combined,
            sample_rate,
            format="WAV",
            subtype="PCM_24",
        )
        os.chmod(continuation, 0o600)

        rendered, rendered_rate = _read_audio(continuation)
        rendered_phrase, rendered_phrase_rate = _read_audio(phrase_copy)
        if rendered_rate != sample_rate or rendered_phrase_rate != sample_rate:
            raise ValueError("rendered continuation sample rate changed")
        if not _np.array_equal(rendered, combined) or not _np.array_equal(
            rendered_phrase, phrase_values
        ):
            raise ValueError("PCM24 continuation changed source sample values")

        edit_map = _edit_map(checked, checked_authorization)
        edit_path = technical_dir / "dry-continuation-edit-map.json"
        _write_private_json(edit_path, edit_map)
        page_path = review_dir / "dry-continuation-review.html"
        page = _review_page(checked)
        _write_private_bytes(page_path, page.encode("utf-8"))

        result: dict[str, Any] = {
            "schema": VOCAL_CONTINUATION_RESULT_SCHEMA,
            "status": "complete_unreviewed_dry_continuation_preview",
            "method_natures": ["D", "H"],
            "binding": {
                "plan_sha256": checked["document_sha256"],
                "authorization_sha256": checked_authorization["document_sha256"],
                "musical_state_sha256": checked["binding"]["musical_state_sha256"],
                "phrase_decision_sha256": checked["binding"]["phrase_decision_sha256"],
                "base_review_sha256": checked["binding"]["base_review_sha256"],
            },
            "artifacts": {
                "carried_base_audio": _result_artifact(base_copy, temporary),
                "selected_phrase_audio": _result_artifact(phrase_copy, temporary),
                "continuation_audio": _result_artifact(continuation, temporary),
                "edit_map": _result_artifact(edit_path, temporary),
                "review_page": _result_artifact(page_path, temporary),
            },
            "signal": {
                "sample_rate": sample_rate,
                "channels": combined.shape[1],
                "frames": combined.shape[0],
                "sample_peak": peak,
                "finite": True,
                "clipped": False,
                "exact_pcm24_sample_concatenation_verified": True,
            },
            "join": dict(checked["join"]),
            "processing": _no_processing(),
            "authority": {
                "playback_creates_decision": False,
                "join_reviewed": False,
                "usable_base_updated": False,
                "release_authorized": False,
                "training_label_created": False,
            },
            "effects": {
                **_no_effects(),
                "audio_preview_rendered": True,
            },
            "network_used": False,
        }
        result["document_sha256"] = document_sha256(result)
        result_path = technical_dir / "dry-continuation-result.json"
        _write_private_json(result_path, result)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return verify_vocal_continuation_result(destination, checked, result)


def verify_vocal_continuation_result(
    output_dir: str | Path,
    plan: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a returned package without granting listening authority."""

    root = Path(output_dir).expanduser().resolve(strict=True)
    checked = _validate_plan_shape(plan)
    document = dict(result)
    _verify_document(document, VOCAL_CONTINUATION_RESULT_SCHEMA, "continuation result")
    if document["binding"]["plan_sha256"] != checked["document_sha256"]:
        raise ValueError("continuation result binds another plan")
    declared = document.get("artifacts")
    if not isinstance(declared, Mapping) or set(declared) != {
        "carried_base_audio",
        "selected_phrase_audio",
        "continuation_audio",
        "edit_map",
        "review_page",
    }:
        raise ValueError("continuation result artifact roster changed")
    expected_files = {
        "AUDIO/carried-two-phrase-usable-base.wav",
        "AUDIO/selected-phrase-3-dry.wav",
        "AUDIO/dry-three-phrase-continuation.wav",
        "TECHNICAL/dry-continuation-edit-map.json",
        "TECHNICAL/dry-continuation-result.json",
        "REVIEW/dry-continuation-review.html",
    }
    actual_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("continuation result file roster changed")
    for record in declared.values():
        path = _artifact_path(root, record, "result artifact")
        if (
            path.stat().st_size != record["bytes"]
            or file_sha256(path) != record["sha256"]
        ):
            raise ValueError("continuation result artifact identity changed")
    disk_result = json.loads(
        (root / "TECHNICAL/dry-continuation-result.json").read_text(encoding="utf-8")
    )
    if disk_result != document:
        raise ValueError("continuation result document changed on disk")
    continuation, sample_rate = _read_audio(
        root / "AUDIO/dry-three-phrase-continuation.wav"
    )
    base, base_rate = _read_audio(root / "AUDIO/carried-two-phrase-usable-base.wav")
    phrase, phrase_rate = _read_audio(root / "AUDIO/selected-phrase-3-dry.wav")
    _np, _sf = _audio_dependencies()
    if sample_rate != base_rate or sample_rate != phrase_rate:
        raise ValueError("continuation result clocks changed")
    if not _np.array_equal(continuation[: len(base)], base) or not _np.array_equal(
        continuation[len(base) :], phrase
    ):
        raise ValueError("continuation is not the exact carried-base concatenation")
    verification: dict[str, Any] = {
        "schema": VOCAL_CONTINUATION_VERIFICATION_SCHEMA,
        "status": "technically_verified_unreviewed_preview",
        "binding": {
            "plan_sha256": checked["document_sha256"],
            "result_sha256": document["document_sha256"],
            "continuation_audio_sha256": declared["continuation_audio"]["sha256"],
        },
        "checks": {
            "artifact_hashes": True,
            "file_roster": True,
            "pcm24_geometry": True,
            "exact_concatenation": True,
            "join_reviewed": False,
        },
        "authority": "technical_only_no_listening_decision",
        "effects": _no_effects(),
        "network_used": False,
    }
    verification["document_sha256"] = document_sha256(verification)
    return verification


def create_vocal_continuation_review(
    output_dir: str | Path,
    plan: Mapping[str, Any],
    *,
    phrase_outcome: str,
    join_outcome: str,
    heard_full_preview: bool,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record one explicit owner review of the exact rendered continuation."""

    checked_plan = _validate_plan_shape(plan)
    result = _continuation_result_from_root(output_dir)
    verify_vocal_continuation_result(output_dir, checked_plan, result)
    document = _continuation_review_document(
        checked_plan,
        result,
        phrase_outcome=phrase_outcome,
        join_outcome=join_outcome,
        heard_full_preview=heard_full_preview,
        notes=notes,
    )
    return validate_vocal_continuation_review(
        document, output_dir=output_dir, plan=checked_plan
    )


def validate_vocal_continuation_review(
    review: Mapping[str, Any],
    *,
    output_dir: str | Path,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Reverify the render and reject altered or excessive review authority."""

    checked_plan = _validate_plan_shape(plan)
    result = _continuation_result_from_root(output_dir)
    verify_vocal_continuation_result(output_dir, checked_plan, result)
    document = dict(review)
    _verify_document(document, VOCAL_CONTINUATION_REVIEW_SCHEMA, "continuation review")
    decision = document.get("decision")
    heard = document.get("heard")
    if not isinstance(decision, Mapping) or not isinstance(heard, Mapping):
        raise ValueError("continuation review decision or heard evidence is missing")
    expected = _continuation_review_document(
        checked_plan,
        result,
        phrase_outcome=decision.get("phrase_3"),
        join_outcome=decision.get("join_at_reviewed_boundary"),
        heard_full_preview=heard.get("full_three_phrase_preview"),
        notes=document.get("notes"),
    )
    if document != expected:
        raise ValueError("continuation review is stale, altered or excessive")
    return document


def _continuation_review_document(
    plan: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    phrase_outcome: Any,
    join_outcome: Any,
    heard_full_preview: Any,
    notes: Any,
) -> dict[str, Any]:
    if phrase_outcome not in {"usable", "not_usable", "cannot_tell"}:
        raise ValueError("continuation phrase outcome is unsupported")
    if join_outcome not in {"natural", "audible", "cannot_tell"}:
        raise ValueError("continuation join outcome is unsupported")
    if heard_full_preview is not True:
        raise ValueError("continuation review requires the full preview to be heard")
    if not isinstance(notes, (str, type(None))):
        raise ValueError("continuation review notes must be text or null")
    if isinstance(notes, str) and len(notes) > 2_000:
        raise ValueError("continuation review notes are too long")
    usable_base = phrase_outcome == "usable" and join_outcome == "natural"
    document: dict[str, Any] = {
        "schema": VOCAL_CONTINUATION_REVIEW_SCHEMA,
        "status": "complete_explicit_owner_continuation_review",
        "method_natures": ["H"],
        "binding": {
            "plan_schema": VOCAL_CONTINUATION_PLAN_SCHEMA,
            "plan_sha256": plan["document_sha256"],
            "result_schema": VOCAL_CONTINUATION_RESULT_SCHEMA,
            "result_sha256": result["document_sha256"],
            "continuation_audio_sha256": result["artifacts"]["continuation_audio"][
                "sha256"
            ],
            "musical_state_sha256": plan["binding"]["musical_state_sha256"],
            "phrase_decision_sha256": plan["binding"]["phrase_decision_sha256"],
        },
        "scope": {
            "phrase_ids": list(plan["scope"]["phrase_ids"]),
            "appended_phrase_id": plan["scope"]["appended_phrase_id"],
            "song_start_seconds": plan["scope"]["song_start_seconds"],
            "song_end_seconds": plan["scope"]["song_end_seconds"],
            "join_song_time_seconds": plan["join"]["song_time_seconds"],
        },
        "heard": {"full_three_phrase_preview": True},
        "decision": {
            "phrase_3": phrase_outcome,
            "join_at_reviewed_boundary": join_outcome,
            "whole_excerpt": (
                "usable_as_next_iteration_base" if usable_base else "needs_iteration"
            ),
        },
        "notes": notes,
        "authority": {
            "usable_as_next_iteration_base": usable_base,
            "join_accepted_for_this_exact_dry_excerpt": join_outcome == "natural",
            "phrase_selection_changed": False,
            "release_authorized": False,
            "correction_authorized": False,
            "training_label_created": False,
            "checkpoint_promotion_authorized": False,
        },
        "effects": _no_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    _reject_paths(document)
    return document


def _continuation_result_from_root(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve(strict=True)
    return _read_hashed_json(
        root / "TECHNICAL/dry-continuation-result.json",
        VOCAL_CONTINUATION_RESULT_SCHEMA,
        "continuation result",
    )


def _load_base(
    base_binding_path: str | Path,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any], dict[str, Any]]:
    path = Path(base_binding_path).expanduser().resolve(strict=True)
    base = _read_hashed_json(path, _BASE_BINDING_SCHEMA, "usable-base binding")
    if base.get("status") != "complete_immutable_usable_base_reference":
        raise ValueError("usable-base binding is not complete")
    authority = base.get("authority")
    if (
        not isinstance(authority, Mapping)
        or authority.get("usable_as_next_iteration_base") is not True
    ):
        raise ValueError("usable base lacks explicit next-iteration authority")
    if any(
        authority.get(key) is not False
        for key in (
            "decisions_migrated",
            "phrase_3_take_selected",
            "comp_render_authorized",
            "pitch_correction_authorized",
            "timing_correction_authorized",
            "training_label_created",
        )
    ):
        raise ValueError("usable-base binding claims excessive authority")
    if any(base.get("effects", {}).values()) or base.get("network_used") is not False:
        raise ValueError("usable-base binding must be no-effect local evidence")
    artifacts = base.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("usable-base artifact binding is missing")
    audio = _artifact_path(path.parent, artifacts["audio"], "usable-base audio")
    if file_sha256(audio) != artifacts["audio"]["sha256"]:
        raise ValueError("usable-base audio hash changed")
    review_path = _named_artifact(path.parent, artifacts["usable_base_review"])
    receipt_path = _named_artifact(path.parent, artifacts["render_receipt"])
    review = _read_hashed_json(review_path, _BASE_REVIEW_SCHEMA, "usable-base review")
    receipt = _read_hashed_json(
        receipt_path, _BASE_RECEIPT_SCHEMA, "usable-base render receipt"
    )
    if (
        file_sha256(review_path) != artifacts["usable_base_review"]["file_sha256"]
        or review["document_sha256"]
        != artifacts["usable_base_review"]["document_sha256"]
        or file_sha256(receipt_path) != artifacts["render_receipt"]["file_sha256"]
        or receipt["document_sha256"] != artifacts["render_receipt"]["document_sha256"]
    ):
        raise ValueError("usable-base review or render receipt identity changed")
    if (
        review.get("status") != "complete_explicit_owner_usable_base"
        or review.get("decision", {}).get("outcome") != "usable_base"
        or review.get("authority", {}).get("usable_as_next_iteration_base") is not True
        or review.get("binding", {}).get("audio_sha256") != artifacts["audio"]["sha256"]
    ):
        raise ValueError("usable-base review does not authorize continuation use")
    if (
        any(review.get("effects", {}).values())
        or review.get("network_used") is not False
    ):
        raise ValueError("usable-base review claims an unsupported effect")
    if (
        receipt.get("artifacts", {}).get("audio", {}).get("sha256")
        != artifacts["audio"]["sha256"]
        or any(receipt.get("processing", {}).values())
        or receipt.get("network_used") is not False
    ):
        raise ValueError("usable-base receipt is not the exact dry audio")
    return path, base, audio, review, receipt


def _load_state(path_value: str | Path) -> tuple[Path, Path, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve(strict=True)
    root = path.parent
    return path, root, validate_musical_state(path, root=root)


def _capture_for_decision(
    state: Mapping[str, Any], decision: Mapping[str, Any]
) -> dict[str, Any]:
    for row in state["vocal_performance_state"].get("phrase_captures", []):
        if row["source_id"] != decision["selected_source_id"]:
            continue
        if row["audio"]["sha256"] != decision["selected_source_sha256"]:
            raise ValueError("selected phrase capture hash changed")
        return dict(row)
    raise ValueError("selected phrase capture is absent from the exact state")


def _pcm24_properties(path: Path) -> dict[str, int]:
    _np, sf = _audio_dependencies()
    info = sf.info(path)
    if info.format != "WAV" or info.subtype != "PCM_24":
        raise ValueError("continuation sources must be PCM24 WAV")
    if info.channels < 1 or info.channels > 2 or info.frames <= 0:
        raise ValueError("continuation source audio geometry is unsupported")
    return {
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
    }


def _read_audio(path: Path) -> tuple[Any, int]:
    _np, sf = _audio_dependencies()
    values, sample_rate = sf.read(path, dtype="float64", always_2d=True)
    return values, int(sample_rate)


def _audio_dependencies() -> tuple[Any, Any]:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise RuntimeError(
            "vocal continuation rendering needs NumPy and SoundFile"
        ) from exc
    return np, sf


def _edit_map(
    plan: Mapping[str, Any], authorization: Mapping[str, Any]
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": VOCAL_CONTINUATION_EDIT_MAP_SCHEMA,
        "status": "complete_unreviewed_exact_concatenation",
        "binding": {
            "plan_sha256": plan["document_sha256"],
            "authorization_sha256": authorization["document_sha256"],
        },
        "scope": dict(plan["scope"]),
        "clock": dict(plan["clock"]),
        "segments": list(plan["segments"]),
        "join": dict(plan["join"]),
        "processing": _no_processing(),
        "authority": {
            "reversible_source_map": True,
            "join_reviewed": False,
            "correction_authorized": False,
        },
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _review_page(plan: Mapping[str, Any]) -> str:
    phrases = " / ".join(html.escape(item) for item in plan["scope"]["phrase_ids"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dry three-phrase continuation review</title><style>
body{{font:16px system-ui,sans-serif;background:#10141b;color:#eef2f7;margin:0}}main{{max-width:820px;margin:auto;padding:32px}}section{{background:#1b2330;padding:20px;border-radius:14px;margin:16px 0}}audio{{width:100%}}.warn{{color:#ffd38a}}code{{overflow-wrap:anywhere}}small{{color:#aeb8c6}}
</style></head><body><main><h1>Dry three-phrase continuation</h1>
<p class="warn"><strong>Unreviewed preview.</strong> Playback creates no decision. The phrase-boundary join has no fade and remains unreviewed.</p>
<p>{phrases}</p>
<section><h2>Full three-phrase continuation</h2><audio controls preload="metadata" src="../AUDIO/dry-three-phrase-continuation.wav"></audio></section>
<section><h2>Carried two-phrase usable base</h2><audio controls preload="metadata" src="../AUDIO/carried-two-phrase-usable-base.wav"></audio></section>
<section><h2>Selected phrase 3 — dry</h2><audio controls preload="metadata" src="../AUDIO/selected-phrase-3-dry.wav"></audio></section>
<section><h2>What to judge</h2><p>Hear whether phrase 3 is usable and whether the exact boundary at {plan["join"]["song_time_seconds"]:.2f}s sounds natural. If not, record again or request a separate reviewed join treatment. Do not judge pitch correction: none was applied.</p></section>
<p><small>Plan <code>{plan["document_sha256"]}</code>. No tuning, timing correction, resampling, fade, gain change, normalization, limiting, training or network use.</small></p>
</main></body></html>"""


def _validate_plan_shape(plan: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(plan)
    _verify_document(document, VOCAL_CONTINUATION_PLAN_SCHEMA, "continuation plan")
    if document.get("status") != "ready_dry_uncorrected_three_phrase_preview":
        raise ValueError("continuation plan status changed")
    if document.get("processing") != _no_processing():
        raise ValueError("continuation plan processing changed")
    if (
        document.get("effects") != _no_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError("continuation plan claims an effect")
    if document.get("join", {}).get("review_status") != "not_reviewed":
        raise ValueError("continuation plan cannot pre-approve the join")
    _reject_paths(document)
    return document


def _result_artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _artifact_path(root: Path, record: Mapping[str, Any], label: str) -> Path:
    relative = _safe_relative(record.get("path"))
    path = (root / Path(*relative.parts)).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes its owner-only root") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe")
    if "bytes" in record and path.stat().st_size != record["bytes"]:
        raise ValueError(f"{label} byte count changed")
    if "sha256" in record and file_sha256(path) != record["sha256"]:
        raise ValueError(f"{label} hash changed")
    return path


def _named_artifact(root: Path, record: Mapping[str, Any]) -> Path:
    return _artifact_path(root, {"path": record["path"]}, "base evidence")


def _safe_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValueError("artifact path must be non-empty text")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("artifact path must stay relative")
    return path


def _read_hashed_json(path: Path, schema: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be readable JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ValueError(f"{label} schema changed")
    expected = value.get("document_sha256")
    unsigned = dict(value)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 changed")
    return value


def _verify_document(document: Mapping[str, Any], schema: str, label: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"{label} schema changed")
    expected = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 changed")


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    _write_private_bytes(path, canonical_json_bytes(document))


def _write_private_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _reject_paths(document: Mapping[str, Any]) -> None:
    def visit(value: Any, key: str | None = None) -> None:
        if key is not None and (
            "path" in key.casefold() or key.casefold().endswith("dir")
        ):
            raise ValueError("path-free continuation document contains a path field")
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and (value.startswith("/") or ":\\" in value):
            raise ValueError("path-free continuation document contains a local path")

    visit(document)


def _no_processing() -> dict[str, bool]:
    return {
        "resampling": False,
        "timing_correction": False,
        "pitch_correction": False,
        "gain_change": False,
        "normalisation": False,
        "limiting": False,
        "crossfade": False,
    }


def _no_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "decision_created": False,
        "audio_preview_rendered": False,
        "join_accepted": False,
        "usable_base_updated": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_started": False,
        "model_weights_changed": False,
    }


__all__ = [
    "VOCAL_CONTINUATION_AUTHORIZATION_SCHEMA",
    "VOCAL_CONTINUATION_EDIT_MAP_SCHEMA",
    "VOCAL_CONTINUATION_PLAN_SCHEMA",
    "VOCAL_CONTINUATION_REVIEW_SCHEMA",
    "VOCAL_CONTINUATION_RESULT_SCHEMA",
    "VOCAL_CONTINUATION_VERIFICATION_SCHEMA",
    "create_vocal_continuation_plan",
    "create_vocal_continuation_review",
    "create_vocal_continuation_render_authorization",
    "render_vocal_continuation",
    "validate_vocal_continuation_plan",
    "validate_vocal_continuation_review",
    "validate_vocal_continuation_render_authorization",
    "verify_vocal_continuation_result",
]
