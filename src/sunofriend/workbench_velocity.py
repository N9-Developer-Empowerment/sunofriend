"""Bounded immutable Clip attack-velocity correction.

This policy is deliberately separate from the frozen Phase 6.3a pitch
contract.  It accepts only an explicit velocity request, exposes a distinct
window/preview/result schema, and appends a child whose targeted MIDI Note On
velocity bytes are the only musical values allowed to change.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any, Mapping, Sequence

from .clip import ClipNote, MidiClip, TransformRecipe, resolve_export_timing
from .library import ClipLibrary, ClipSummary
from .note_safety import MidiNoteInterval, normalize_midi_intervals
from .workbench_clips import WorkbenchClipService, _LibraryState
from .workbench_correction import (
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionNotFoundError,
    _MAX_EDITABLE_NOTES,
    _MAX_VISIBLE_NOTES,
    _MAX_WINDOW_CHORDS,
    _MAX_WINDOW_SECONDS,
    _TICKS_PER_BEAT,
    _clip_horizon_tick,
    _document_hash,
    _exact_int,
    _json_copy,
    _note_mapping,
    _note_payload,
    _note_ref,
    _note_ticks,
    _parent_from_state,
    _parse_window,
    _require_library_pin,
    _safe_clip_identifier,
    _sha256_value,
    _validate_parent_bounds,
    _window_chords,
    _window_seconds,
)
from .workbench_transform import _child_identity, _clip_identity


CLIP_ATTACK_VELOCITY_WINDOW_SCHEMA = (
    "sunofriend.workbench-clip-attack-velocity-window.v1"
)
CLIP_ATTACK_VELOCITY_PREVIEW_SCHEMA = (
    "sunofriend.workbench-clip-attack-velocity-preview.v1"
)
CLIP_ATTACK_VELOCITY_RESULT_SCHEMA = (
    "sunofriend.workbench-clip-attack-velocity-result.v1"
)
CLIP_ATTACK_VELOCITY_SUMMARY_SCHEMA = (
    "sunofriend.workbench-clip-attack-velocity-summary.v1"
)
_INTENT_SCHEMA = "sunofriend.workbench-clip-attack-velocity-intent.v1"
_RECIPE_CONTRACT_VERSION = 1
_CORRECTION_KIND = "attack_velocity_patch"
_OPERATION = "correct_note_attack_velocities"
_MAX_CHANGES = 64
_BASE_WINDOW_REQUEST_KEYS = {
    "parent_clip_id",
    "parent_object_sha256",
    "library_state_sha256",
    "window",
}
_WINDOW_REQUEST_KEYS = _BASE_WINDOW_REQUEST_KEYS | {"correction_kind"}
_PREVIEW_REQUEST_KEYS = _BASE_WINDOW_REQUEST_KEYS | {
    "window_sha256",
    "correction",
}
_CREATE_REQUEST_KEYS = _PREVIEW_REQUEST_KEYS | {"action", "projection_sha256"}
_RECIPE_PARAMETER_KEYS = {
    "contract_version",
    "intent_sha256",
    "parent_object_sha256",
    "library_state_sha256",
    "window_sha256",
    "ticks_per_beat",
    "window",
    "correction",
    "changes",
}
_VELOCITY_EFFECT_KEYS = {
    "library_mutated",
    "child_clip_created",
    "source_clip_mutated",
    "correction_applied",
    "note_attack_velocity_changed",
    "note_pitch_changed",
    "note_timing_changed",
    "note_count_changed",
    "release_velocity_changed",
    "key_changed",
    "chords_changed",
    "instrument_changed",
    "provenance_changed",
    "reuse_plan_changed",
    "placement_changed",
    "current_arrangement_changed",
    "pack_changed",
    "hybrid_created",
    "feedback_recorded",
    "data_submitted",
}


class WorkbenchClipVelocityCorrectionService:
    """Project and append one explicit attack-velocity correction at a time."""

    def __init__(
        self,
        *,
        clip_service: WorkbenchClipService,
        writer: ClipLibrary,
    ) -> None:
        self._clip_service = clip_service
        self._writer = writer

    def window(self, request: Mapping[str, Any]) -> dict[str, Any]:
        parsed = _parse_window_request(request)
        state = self._snapshot()
        _require_library_pin(state, parsed["library_state_sha256"])
        parent, summary = _parent_from_state(state, parsed)
        return _window_projection(parent=parent, summary=summary, request=parsed)

    def preview(self, request: Mapping[str, Any]) -> dict[str, Any]:
        parsed = _parse_preview_request(request, create=False)
        state = self._snapshot()
        _require_library_pin(state, parsed["library_state_sha256"])
        if not self._clip_service._transform_has_append_capacity(state):
            raise WorkbenchClipCorrectionError(
                "Clip library has reached the 10000 Clip correction limit"
            )
        parent, summary = _parent_from_state(state, parsed)
        window = _window_projection(
            parent=parent,
            summary=summary,
            request=_window_request_from_patch(parsed),
        )
        if parsed["window_sha256"] != window["window_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip attack-velocity window changed; load the window again"
            )
        return _project(parent=parent, summary=summary, request=parsed, window=window)

    def create(self, request: Mapping[str, Any]) -> dict[str, Any]:
        parsed = _parse_preview_request(request, create=True)
        try:
            state = self._clip_service._transform_create_snapshot(
                expected_state_sha256=parsed["library_state_sha256"],
            )
        except RuntimeError as exc:
            raise WorkbenchClipCorrectionConflictError(
                "Verified Clip library changed; load a fresh attack-velocity window"
            ) from exc
        parent, summary = _parent_from_state(state, parsed)
        window = _window_projection(
            parent=parent,
            summary=summary,
            request=_window_request_from_patch(parsed),
        )
        if parsed["window_sha256"] != window["window_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip attack-velocity window changed; load the window again"
            )
        projection = _project(
            parent=parent,
            summary=summary,
            request=parsed,
            window=window,
        )
        if parsed["projection_sha256"] != projection["projection_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip attack-velocity projection changed; review the correction again"
            )
        resolved = _resolve_changes(parent, parsed, window)
        child = _corrected_child(
            parent,
            request=parsed,
            intent_sha256=projection["intent_sha256"],
            resolved_changes=resolved,
        )
        child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
        if child_hash != projection["child"]["object_sha256"]:
            raise RuntimeError(
                "Clip attack-velocity child projection is not deterministic"
            )
        try:
            append = self._clip_service._append_transform_child(
                writer=self._writer,
                expected_state_sha256=parsed["library_state_sha256"],
                parent_clip_id=parsed["parent_clip_id"],
                expected_parent_object_hash=parsed["parent_object_sha256"],
                child=child,
            )
        except KeyError as exc:
            raise WorkbenchClipCorrectionNotFoundError(
                "Parent Clip is no longer available"
            ) from exc
        except RuntimeError as exc:
            if "conflict" in str(exc).casefold() or "changed" in str(exc).casefold():
                raise WorkbenchClipCorrectionConflictError(
                    "Clip library changed; load a fresh attack-velocity window"
                ) from exc
            raise

        replayed = append.replayed
        return {
            "schema": CLIP_ATTACK_VELOCITY_RESULT_SCHEMA,
            "status": "replayed" if replayed else "created",
            "operation": "clip-attack-velocity-correction-create",
            "projection_sha256": projection["projection_sha256"],
            "replayed": replayed,
            "window": dict(projection["window"]),
            "correction": _json_copy(projection["correction"]),
            "parent": dict(projection["parent"]),
            "child": dict(projection["child"]),
            "diff": _json_copy(projection["diff"]),
            "warnings": list(projection["warnings"]),
            "library": {
                "expected_state_sha256": parsed["library_state_sha256"],
                "previous_state_sha256": append.previous_state_sha256,
                "current_state_sha256": append.current_state.state_sha256,
            },
            "effects": _effects(
                library_mutated=not replayed,
                child_clip_created=not replayed,
                correction_applied=not replayed,
                note_attack_velocity_changed=not replayed,
            ),
        }

    def correction_summary_from_state(
        self,
        clip_id: str,
        state: _LibraryState,
    ) -> dict[str, Any]:
        """Re-derive one recognized velocity correction from a verified snapshot."""

        requested = _safe_clip_identifier(clip_id, "clip_id")
        try:
            child = state.clips[requested]
        except KeyError as exc:
            raise WorkbenchClipCorrectionNotFoundError(
                "Unknown corrected Clip"
            ) from exc
        if (
            child.transform_recipe is None
            or child.transform_recipe.operation != _OPERATION
        ):
            raise WorkbenchClipCorrectionError(
                "Clip does not contain a recognized attack-velocity recipe"
            )
        if child.parent_clip_id is None or child.parent_clip_id not in state.clips:
            raise WorkbenchClipCorrectionError(
                "Recognized attack-velocity child has no verified parent"
            )
        parent = state.clips[child.parent_clip_id]
        parent_summary = next(
            row for row in state.summaries if row.clip_id == parent.clip_id
        )
        child_summary = next(
            row for row in state.summaries if row.clip_id == child.clip_id
        )
        summary = _derive_correction_summary(parent, child)
        parameters = child.transform_recipe.parameters_dict
        retained_window = _window_projection(
            parent=parent,
            summary=parent_summary,
            request={
                "parent_clip_id": parent.clip_id,
                "parent_object_sha256": summary["parent_object_sha256"],
                "library_state_sha256": parameters["library_state_sha256"],
                "window": parameters["window"],
                "correction_kind": _CORRECTION_KIND,
            },
        )
        if retained_window["window_sha256"] != parameters["window_sha256"]:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe window evidence does not match its parent"
            )
        return {
            **summary,
            "library_state_sha256": state.state_sha256,
            "parent": _clip_identity(summary=parent_summary, clip=parent),
            "child": _clip_identity(summary=child_summary, clip=child),
            "effects": _effects(),
        }

    def _snapshot(self) -> _LibraryState:
        try:
            return self._clip_service._transform_snapshot()
        except RuntimeError as exc:
            raise WorkbenchClipCorrectionConflictError(
                "Verified Clip library changed; restart or load a fresh window"
            ) from exc


def _parse_window_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping) or set(request) != _WINDOW_REQUEST_KEYS:
        raise WorkbenchClipCorrectionError(
            "Clip attack-velocity window fields do not match the exact contract"
        )
    if request.get("correction_kind") != _CORRECTION_KIND:
        raise WorkbenchClipCorrectionError(
            "correction_kind must be 'attack_velocity_patch'"
        )
    return {
        "parent_clip_id": _safe_clip_identifier(
            request.get("parent_clip_id"), "parent_clip_id"
        ),
        "parent_object_sha256": _sha256_value(
            request.get("parent_object_sha256"), "parent_object_sha256"
        ),
        "library_state_sha256": _sha256_value(
            request.get("library_state_sha256"), "library_state_sha256"
        ),
        "window": _parse_window(request.get("window")),
        "correction_kind": _CORRECTION_KIND,
    }


def _parse_preview_request(
    request: Mapping[str, Any],
    *,
    create: bool,
) -> dict[str, Any]:
    expected = _CREATE_REQUEST_KEYS if create else _PREVIEW_REQUEST_KEYS
    if not isinstance(request, Mapping) or set(request) != expected:
        raise WorkbenchClipCorrectionError(
            "Clip attack-velocity request fields do not match the exact contract"
        )
    if create and request.get("action") != "create":
        raise WorkbenchClipCorrectionError("Clip correction action must be 'create'")
    parsed = {
        "parent_clip_id": _safe_clip_identifier(
            request.get("parent_clip_id"), "parent_clip_id"
        ),
        "parent_object_sha256": _sha256_value(
            request.get("parent_object_sha256"), "parent_object_sha256"
        ),
        "library_state_sha256": _sha256_value(
            request.get("library_state_sha256"), "library_state_sha256"
        ),
        "window": _parse_window(request.get("window")),
        "window_sha256": _sha256_value(request.get("window_sha256"), "window_sha256"),
        "correction": _parse_correction(request.get("correction")),
    }
    if create:
        parsed["action"] = "create"
        parsed["projection_sha256"] = _sha256_value(
            request.get("projection_sha256"), "projection_sha256"
        )
    return parsed


def _parse_correction(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"kind", "changes"}:
        raise WorkbenchClipCorrectionError(
            "correction requires exactly kind and changes"
        )
    if value.get("kind") != _CORRECTION_KIND:
        raise WorkbenchClipCorrectionError(
            "correction kind must be 'attack_velocity_patch'"
        )
    rows = value.get("changes")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_CHANGES:
        raise WorkbenchClipCorrectionError(
            "attack-velocity patch requires 1 to 64 changes"
        )
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "note_ref",
            "target_velocity",
        }:
            raise WorkbenchClipCorrectionError(
                "each attack-velocity change requires exactly note_ref and target_velocity"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        target = _exact_int(row.get("target_velocity"), "target_velocity")
        if not 1 <= target <= 127:
            raise WorkbenchClipCorrectionError(
                "target_velocity must be an integer from 1 to 127"
            )
        if note_ref in seen:
            raise WorkbenchClipCorrectionError(
                "attack-velocity changes must use unique note refs"
            )
        seen.add(note_ref)
        changes.append({"note_ref": note_ref, "target_velocity": target})
    changes.sort(key=lambda row: row["note_ref"])
    return {"kind": _CORRECTION_KIND, "changes": changes}


def _window_request_from_patch(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "parent_clip_id": request["parent_clip_id"],
        "parent_object_sha256": request["parent_object_sha256"],
        "library_state_sha256": request["library_state_sha256"],
        "window": dict(request["window"]),
        "correction_kind": _CORRECTION_KIND,
    }


def _window_projection(
    *,
    parent: MidiClip,
    summary: ClipSummary,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    window = dict(request["window"])
    parent_hash = str(request["parent_object_sha256"])
    content = _bounded_window_content(parent, parent_hash, window)
    timing_mode, timing_bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    document: dict[str, Any] = {
        "schema": CLIP_ATTACK_VELOCITY_WINDOW_SCHEMA,
        "operation": "clip-attack-velocity-window",
        "correction_kind": _CORRECTION_KIND,
        "library": {"state_sha256": request["library_state_sha256"]},
        "parent": _clip_identity(summary=summary, clip=parent),
        "window": {
            **window,
            "ticks_per_beat": _TICKS_PER_BEAT,
            "duration_seconds": float(content["duration_seconds"]),
            "origin": "recorded-zero",
        },
        "timing": {
            "resolved_mode": timing_mode,
            "export_bpm": timing_bpm,
        },
        "notes": content["notes"],
        "visible_note_count": len(content["notes"]),
        "editable_note_count": int(content["editable_note_count"]),
        "blocked_duplicate_note_on_count": int(
            content["blocked_duplicate_note_on_count"]
        ),
        "chords": content["chords"],
        "policies": {
            "editable_membership": "unambiguous note-on tick in half-open window",
            "context_membership": "export interval intersects window",
            "correction_scope": "MIDI Note On attack velocity only",
            "duplicate_export_note_on": (
                "same channel, start tick and pitch is visible but not editable"
            ),
        },
        "effects": _effects(),
    }
    document["window_sha256"] = _document_hash(document)
    return document


def _bounded_window_content(
    parent: MidiClip,
    parent_hash: str,
    window: Mapping[str, int],
) -> dict[str, Any]:
    _validate_parent_bounds(parent)
    horizon_tick = _clip_horizon_tick(parent)
    if int(window["start_tick"]) > horizon_tick:
        raise WorkbenchClipCorrectionError(
            "correction window starts after the Clip export horizon"
        )
    duration_seconds = _window_seconds(parent, window)
    if duration_seconds > _MAX_WINDOW_SECONDS + 1e-9:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds 15 export seconds"
        )

    ticks = [_note_ticks(parent, note) for note in parent.notes]
    group_sizes: dict[tuple[int, int, int], int] = {}
    for note, (start_tick, _end_tick) in zip(parent.notes, ticks):
        key = (parent.instrument.channel, start_tick, note.pitch)
        group_sizes[key] = group_sizes.get(key, 0) + 1

    notes: list[dict[str, Any]] = []
    editable_count = 0
    blocked_duplicate_count = 0
    for index, (note, (start_tick, end_tick)) in enumerate(zip(parent.notes, ticks)):
        if start_tick >= window["end_tick"] or end_tick <= window["start_tick"]:
            continue
        note_on_in_window = window["start_tick"] <= start_tick < window["end_tick"]
        group_size = group_sizes[(parent.instrument.channel, start_tick, note.pitch)]
        duplicate = group_size > 1
        editable = note_on_in_window and not duplicate
        if editable:
            editable_count += 1
        elif note_on_in_window and duplicate:
            blocked_duplicate_count += 1
        blocked_reason = None
        if duplicate:
            blocked_reason = "duplicate-export-note-on"
        elif not note_on_in_window:
            blocked_reason = "context-note-on-outside-window"
        notes.append(
            {
                "note_ref": _note_ref(parent_hash, index, note),
                "editable": editable,
                "edit_block_reason": blocked_reason,
                "export_note_on_group_size": group_size,
                "channel": parent.instrument.channel,
                "pitch": note.pitch,
                "velocity": note.velocity,
                "start_tick": start_tick,
                "end_tick": end_tick,
                "start_beat": note.start_beat,
                "duration_beats": note.duration_beats,
                "source_start_seconds": note.source_start_seconds,
                "source_end_seconds": note.source_end_seconds,
            }
        )
    if len(notes) > _MAX_VISIBLE_NOTES:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds the 512 visible-note limit"
        )
    if editable_count > _MAX_EDITABLE_NOTES:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds the 256 editable-note limit"
        )
    chords = _window_chords(parent, window)
    if len(chords) > _MAX_WINDOW_CHORDS:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds the 64 chord limit"
        )
    return {
        "duration_seconds": duration_seconds,
        "notes": notes,
        "editable_note_count": editable_count,
        "blocked_duplicate_note_on_count": blocked_duplicate_count,
        "chords": chords,
    }


def _project(
    *,
    parent: MidiClip,
    summary: ClipSummary,
    request: Mapping[str, Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_changes(parent, request, window)
    intent = _intent_document(
        parent_clip_id=str(request["parent_clip_id"]),
        parent_object_sha256=str(request["parent_object_sha256"]),
        library_state_sha256=str(request["library_state_sha256"]),
        window=request["window"],
        window_sha256=str(request["window_sha256"]),
        correction=request["correction"],
    )
    intent_sha256 = _document_hash(intent)
    child = _corrected_child(
        parent,
        request=request,
        intent_sha256=intent_sha256,
        resolved_changes=resolved,
    )
    _validate_velocity_only(parent, child, resolved)
    _validate_normalized_midi_delta(parent, child, resolved)
    child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
    diff = _diff(parent, child, resolved)
    document: dict[str, Any] = {
        "schema": CLIP_ATTACK_VELOCITY_PREVIEW_SCHEMA,
        "status": "previewed",
        "operation": "clip-attack-velocity-correction-preview",
        "intent_sha256": intent_sha256,
        "library": {"state_sha256": request["library_state_sha256"]},
        "window": dict(window["window"]),
        "correction": _json_copy(request["correction"]),
        "parent": _clip_identity(summary=summary, clip=parent),
        "child": _child_identity(
            parent_summary=summary,
            child=child,
            object_hash=child_hash,
        ),
        "diff": diff,
        "warnings": _warnings(),
        "effects": _effects(),
    }
    document["projection_sha256"] = _document_hash(document)
    return document


def _intent_document(
    *,
    parent_clip_id: str,
    parent_object_sha256: str,
    library_state_sha256: str,
    window: Mapping[str, int],
    window_sha256: str,
    correction: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": _INTENT_SCHEMA,
        "parent_clip_id": parent_clip_id,
        "parent_object_sha256": parent_object_sha256,
        "library_state_sha256": library_state_sha256,
        "window": dict(window),
        "window_sha256": window_sha256,
        "correction": _json_copy(correction),
    }


def _resolve_changes(
    parent: MidiClip,
    request: Mapping[str, Any],
    window: Mapping[str, Any],
) -> list[dict[str, Any]]:
    parent_hash = str(request["parent_object_sha256"])
    visible = {row["note_ref"]: row for row in window["notes"]}
    ref_to_index = {
        _note_ref(parent_hash, index, note): index
        for index, note in enumerate(parent.notes)
    }
    resolved: list[dict[str, Any]] = []
    for row in request["correction"]["changes"]:
        note_ref = row["note_ref"]
        visible_note = visible.get(note_ref)
        if visible_note is not None and visible_note["edit_block_reason"] == (
            "duplicate-export-note-on"
        ):
            raise WorkbenchClipCorrectionError(
                "attack-velocity correction references an ambiguous duplicate exported Note On"
            )
        if (
            visible_note is None
            or visible_note["editable"] is not True
            or note_ref not in ref_to_index
        ):
            raise WorkbenchClipCorrectionError(
                "attack-velocity correction references a note outside the editable window"
            )
        index = ref_to_index[note_ref]
        before = parent.notes[index]
        target = int(row["target_velocity"])
        if target == before.velocity:
            raise WorkbenchClipCorrectionError(
                "attack-velocity correction contains a no-op"
            )
        after = replace(before, velocity=target)
        resolved.append(
            {
                "note_ref": note_ref,
                "parent_note_index": index,
                "before": _note_payload(before),
                "after": _note_payload(after),
            }
        )
    resolved.sort(key=lambda row: row["parent_note_index"])
    return resolved


def _corrected_child(
    parent: MidiClip,
    *,
    request: Mapping[str, Any],
    intent_sha256: str,
    resolved_changes: Sequence[Mapping[str, Any]],
) -> MidiClip:
    return _child_from_recipe(
        parent,
        intent_sha256=intent_sha256,
        parent_object_sha256=str(request["parent_object_sha256"]),
        library_state_sha256=str(request["library_state_sha256"]),
        window_sha256=str(request["window_sha256"]),
        window=dict(request["window"]),
        correction=request["correction"],
        recipe_changes=resolved_changes,
    )


def _child_from_recipe(
    parent: MidiClip,
    *,
    intent_sha256: str,
    parent_object_sha256: str,
    library_state_sha256: str,
    window_sha256: str,
    window: Mapping[str, int],
    correction: Mapping[str, Any],
    recipe_changes: Sequence[Mapping[str, Any]],
) -> MidiClip:
    changes_by_index = {
        int(row["parent_note_index"]): int(row["after"]["velocity"])
        for row in recipe_changes
    }
    notes = tuple(
        replace(note, velocity=changes_by_index.get(index, note.velocity))
        for index, note in enumerate(parent.notes)
    )
    recipe = TransformRecipe.create(
        _OPERATION,
        contract_version=_RECIPE_CONTRACT_VERSION,
        intent_sha256=intent_sha256,
        parent_object_sha256=parent_object_sha256,
        library_state_sha256=library_state_sha256,
        window_sha256=window_sha256,
        ticks_per_beat=_TICKS_PER_BEAT,
        window=dict(window),
        correction=_json_copy(correction),
        changes=[_json_copy(row) for row in recipe_changes],
    )
    child = parent.child(recipe=recipe, notes=notes)
    return replace(child, clip_id=f"sf-correction-{intent_sha256}")


def _derive_correction_summary(parent: MidiClip, child: MidiClip) -> dict[str, Any]:
    if child.transform_recipe is None or child.transform_recipe.operation != _OPERATION:
        raise WorkbenchClipCorrectionError(
            "Clip does not contain a recognized attack-velocity recipe"
        )
    if child.parent_clip_id != parent.clip_id or child.revision != parent.revision + 1:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction lineage does not match its parent"
        )
    parameters = child.transform_recipe.parameters_dict
    if set(parameters) != _RECIPE_PARAMETER_KEYS:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction recipe fields are invalid"
        )
    if parameters.get("contract_version") != _RECIPE_CONTRACT_VERSION:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction recipe version is unsupported"
        )
    if parameters.get("ticks_per_beat") != _TICKS_PER_BEAT:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction recipe TPQ is invalid"
        )
    parent_hash = hashlib.sha256(parent.canonical_bytes()).hexdigest()
    if parameters.get("parent_object_sha256") != parent_hash:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity recipe parent object does not match"
        )
    library_state_sha256 = _sha256_value(
        parameters.get("library_state_sha256"), "library_state_sha256"
    )
    window_sha256 = _sha256_value(parameters.get("window_sha256"), "window_sha256")
    window = _parse_window(parameters.get("window"))
    _bounded_window_content(parent, parent_hash, window)
    recipe_changes = _parse_recipe_changes(
        parameters.get("changes"), parent, parent_hash, window
    )
    correction = _parse_correction(parameters.get("correction"))
    expected_correction = _correction_from_recipe_changes(recipe_changes)
    if correction != expected_correction:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity patch does not match its retained edit diff"
        )
    intent_sha256 = _sha256_value(parameters.get("intent_sha256"), "intent_sha256")
    expected_intent = _document_hash(
        _intent_document(
            parent_clip_id=parent.clip_id,
            parent_object_sha256=parent_hash,
            library_state_sha256=library_state_sha256,
            window=window,
            window_sha256=window_sha256,
            correction=correction,
        )
    )
    if intent_sha256 != expected_intent:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity recipe intent digest does not match its retained evidence"
        )
    if child.clip_id != f"sf-correction-{intent_sha256}":
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction child identity is invalid"
        )
    expected = _child_from_recipe(
        parent,
        intent_sha256=intent_sha256,
        parent_object_sha256=parent_hash,
        library_state_sha256=library_state_sha256,
        window_sha256=window_sha256,
        window=window,
        correction=correction,
        recipe_changes=recipe_changes,
    )
    if expected != child:
        raise WorkbenchClipCorrectionError(
            "Attack-velocity child does not match the exact retained edit diff"
        )
    _validate_velocity_only(parent, child, recipe_changes)
    _validate_normalized_midi_delta(parent, child, recipe_changes)
    public_changes = [_public_change(parent, row) for row in recipe_changes]
    return {
        "schema": CLIP_ATTACK_VELOCITY_SUMMARY_SCHEMA,
        "operation": _OPERATION,
        "contract_version": _RECIPE_CONTRACT_VERSION,
        "parent_clip_id": parent.clip_id,
        "parent_object_sha256": parent_hash,
        "child_clip_id": child.clip_id,
        "child_object_sha256": hashlib.sha256(child.canonical_bytes()).hexdigest(),
        "window": {**window, "ticks_per_beat": _TICKS_PER_BEAT},
        "changed_note_count": len(public_changes),
        "changes": public_changes,
        "unchanged": _unchanged_projection(),
    }


def _parse_recipe_changes(
    value: Any,
    parent: MidiClip,
    parent_hash: str,
    window: Mapping[str, int],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_CHANGES:
        raise WorkbenchClipCorrectionError("Attack-velocity recipe changes are invalid")
    group_sizes = _export_note_on_group_sizes(parent)
    seen_refs: set[str] = set()
    seen_indices: set[int] = set()
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {
            "note_ref",
            "parent_note_index",
            "before",
            "after",
        }:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe change is invalid"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        index = _exact_int(row.get("parent_note_index"), "parent_note_index")
        if index < 0 or index >= len(parent.notes):
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe note index is invalid"
            )
        if note_ref in seen_refs or index in seen_indices:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe changes are duplicated"
            )
        seen_refs.add(note_ref)
        seen_indices.add(index)
        before = _note_mapping(row.get("before"), "before")
        after = _note_mapping(row.get("after"), "after")
        parent_note = parent.notes[index]
        if before != _note_payload(parent_note):
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe before-note does not match its parent"
            )
        if note_ref != _note_ref(parent_hash, index, parent_note):
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe note ref is invalid"
            )
        start_tick, _end_tick = _note_ticks(parent, parent_note)
        if not window["start_tick"] <= start_tick < window["end_tick"]:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe note is outside its editable window"
            )
        group_key = (parent.instrument.channel, start_tick, parent_note.pitch)
        if group_sizes[group_key] != 1:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe note has an ambiguous duplicate exported Note On"
            )
        changed_fields = {key for key in before if before.get(key) != after.get(key)}
        if changed_fields != {"velocity"}:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe may change velocity only"
            )
        target = after["velocity"]
        if (
            not isinstance(target, int)
            or isinstance(target, bool)
            or not 1 <= target <= 127
            or target == parent_note.velocity
        ):
            raise WorkbenchClipCorrectionError(
                "Attack-velocity recipe target is invalid"
            )
        rows.append(
            {
                "note_ref": note_ref,
                "parent_note_index": index,
                "before": before,
                "after": after,
            }
        )
    rows.sort(key=lambda row: row["parent_note_index"])
    return rows


def _correction_from_recipe_changes(
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [
        {
            "note_ref": str(row["note_ref"]),
            "target_velocity": int(row["after"]["velocity"]),
        }
        for row in changes
    ]
    rows.sort(key=lambda row: row["note_ref"])
    return {"kind": _CORRECTION_KIND, "changes": rows}


def _validate_velocity_only(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    protected = (
        "title",
        "tempo_map",
        "time_signature",
        "key",
        "chords",
        "instrument",
        "provenance",
        "engine_version",
        "tags",
        "schema_version",
    )
    if any(getattr(parent, field) != getattr(child, field) for field in protected):
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction changed protected Clip metadata"
        )
    if len(parent.notes) != len(child.notes):
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction changed the note count"
        )
    changed = {int(row["parent_note_index"]) for row in changes}
    for index, (before, after) in enumerate(zip(parent.notes, child.notes)):
        before_payload = _note_payload(before)
        after_payload = _note_payload(after)
        differing = {
            key for key in before_payload if before_payload[key] != after_payload[key]
        }
        if index in changed:
            if differing != {"velocity"}:
                raise WorkbenchClipCorrectionError(
                    "Attack-velocity correction changed a field other than velocity"
                )
        elif differing:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity correction changed an unaffected note"
            )


def _export_note_on_group_sizes(clip: MidiClip) -> dict[tuple[int, int, int], int]:
    groups: dict[tuple[int, int, int], int] = {}
    for note in clip.notes:
        start_tick, _end_tick = _note_ticks(clip, note)
        key = (clip.instrument.channel, start_tick, note.pitch)
        groups[key] = groups.get(key, 0) + 1
    return groups


def _normalized_intervals(clip: MidiClip) -> list[MidiNoteInterval]:
    intervals: list[MidiNoteInterval] = []
    for note in clip.notes:
        start_tick, end_tick = _note_ticks(clip, note)
        intervals.append(
            MidiNoteInterval(
                owner=0,
                channel=clip.instrument.channel,
                start_tick=start_tick,
                end_tick=end_tick,
                pitch=note.pitch,
                velocity=note.velocity,
                release_velocity=note.release_velocity,
            )
        )
    return normalize_midi_intervals(intervals)


def _validate_normalized_midi_delta(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    group_sizes = _export_note_on_group_sizes(parent)
    targets: dict[tuple[int, int, int], int] = {}
    for row in changes:
        note = parent.notes[int(row["parent_note_index"])]
        start_tick, _end_tick = _note_ticks(parent, note)
        key = (parent.instrument.channel, start_tick, note.pitch)
        if group_sizes.get(key) != 1 or key in targets:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity edit is not one-to-one with an exported Note On"
            )
        targets[key] = int(row["after"]["velocity"])

    before = _normalized_intervals(parent)
    after = _normalized_intervals(child)
    if len(before) != len(after):
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction changed normalized MIDI event count"
        )
    before_by_key = {(row.channel, row.start_tick, row.pitch): row for row in before}
    after_by_key = {(row.channel, row.start_tick, row.pitch): row for row in after}
    if set(before_by_key) != set(after_by_key):
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction changed normalized MIDI note identity"
        )
    observed_changed: set[tuple[int, int, int]] = set()
    for key, before_row in before_by_key.items():
        after_row = after_by_key[key]
        if (
            before_row.owner != after_row.owner
            or before_row.channel != after_row.channel
            or before_row.start_tick != after_row.start_tick
            or before_row.end_tick != after_row.end_tick
            or before_row.pitch != after_row.pitch
            or before_row.release_velocity != after_row.release_velocity
        ):
            raise WorkbenchClipCorrectionError(
                "Attack-velocity correction changed normalized MIDI structure"
            )
        expected_velocity = targets.get(key, before_row.velocity)
        if after_row.velocity != expected_velocity:
            raise WorkbenchClipCorrectionError(
                "Attack-velocity correction changed an unexpected MIDI velocity"
            )
        if after_row.velocity != before_row.velocity:
            observed_changed.add(key)
    if observed_changed != set(targets):
        raise WorkbenchClipCorrectionError(
            "Attack-velocity correction did not change exactly its targeted Note Ons"
        )


def _diff(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    public = [_public_change(parent, row) for row in changes]
    return {
        "kind": _CORRECTION_KIND,
        "changed_note_count": len(public),
        "changes": public,
        "note_count_before": len(parent.notes),
        "note_count_after": len(child.notes),
        "velocity_range_before": _velocity_range(parent.notes),
        "velocity_range_after": _velocity_range(child.notes),
        "unchanged": _unchanged_projection(),
        "ambiguous_export_note_ons_changed": 0,
    }


def _public_change(parent: MidiClip, row: Mapping[str, Any]) -> dict[str, Any]:
    before = dict(row["before"])
    after = dict(row["after"])
    note = parent.notes[int(row["parent_note_index"])]
    start_tick, end_tick = _note_ticks(parent, note)
    return {
        "note_ref": str(row["note_ref"]),
        "channel": parent.instrument.channel,
        "start_tick": start_tick,
        "end_tick": end_tick,
        "start_beat": before["start_beat"],
        "duration_beats": before["duration_beats"],
        "source_start_seconds": before["source_start_seconds"],
        "source_end_seconds": before["source_end_seconds"],
        "pitch": before["pitch"],
        "before_velocity": before["velocity"],
        "after_velocity": after["velocity"],
        "velocity_delta": after["velocity"] - before["velocity"],
    }


def _velocity_range(notes: Sequence[ClipNote]) -> dict[str, int] | None:
    if not notes:
        return None
    velocities = [note.velocity for note in notes]
    return {"minimum": min(velocities), "maximum": max(velocities)}


def _unchanged_projection() -> dict[str, bool]:
    return {
        "note_count": True,
        "note_pitches": True,
        "note_onsets": True,
        "note_durations": True,
        "source_seconds": True,
        "microtiming": True,
        "release_velocity": True,
        "articulation": True,
        "tempo_map": True,
        "timing_mode": True,
        "key": True,
        "chords": True,
        "instrument": True,
        "provenance": True,
    }


def _warnings() -> list[str]:
    return [
        "The source Clip remains immutable; creation adds one child alternative only.",
        "Only the named MIDI Note On attack velocities change; pitch, timing, duration, release velocity and metadata remain unchanged.",
        "MIDI attack velocity is patch-dependent and can affect loudness, brightness or sample layers; it is not audio gain, CC11 expression or a source-energy estimate.",
        "Duplicate exported Note Ons are blocked because MIDI normalization represents each shared channel/start/pitch group as one event.",
        "The child is not selected, placed, auditioned or added to a GarageBand Pack automatically.",
    ]


def _effects(**changes: bool) -> dict[str, bool]:
    effects = {key: False for key in sorted(_VELOCITY_EFFECT_KEYS)}
    for key, value in changes.items():
        if key not in _VELOCITY_EFFECT_KEYS or not isinstance(value, bool):
            raise ValueError("Unknown Clip attack-velocity correction effect")
        effects[key] = value
    return effects


__all__ = [
    "CLIP_ATTACK_VELOCITY_PREVIEW_SCHEMA",
    "CLIP_ATTACK_VELOCITY_RESULT_SCHEMA",
    "CLIP_ATTACK_VELOCITY_SUMMARY_SCHEMA",
    "CLIP_ATTACK_VELOCITY_WINDOW_SCHEMA",
    "WorkbenchClipVelocityCorrectionService",
]
