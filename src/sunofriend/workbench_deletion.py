"""Bounded immutable Clip note deletion.

This Phase 6.3c policy is deliberately separate from the published pitch and
attack-velocity contracts.  A deletion is offered only when removing one exact
source note removes exactly one normalized MIDI interval, leaves every
surviving interval byte-semantically unchanged, and preserves the Clip's beat,
export-tick and source-second horizons.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any, Mapping, Sequence

from .clip import ClipNote, MidiClip, TransformRecipe, resolve_export_timing
from .library import ClipLibrary, ClipSummary
from .note_safety import MidiNoteInterval, normalize_midi_intervals
from .workbench_clips import WorkbenchClipService, _LibraryState, _safe_text
from .workbench_correction import (
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionError,
    WorkbenchClipCorrectionNotFoundError,
    _MAX_EDITABLE_NOTES,
    _MAX_VISIBLE_NOTES,
    _MAX_WINDOW_CHORDS,
    _MAX_WINDOW_SECONDS,
    _TICKS_PER_BEAT,
    _chord_ticks,
    _document_hash,
    _json_copy,
    _maximum_duration_seconds,
    _note_mapping,
    _note_payload,
    _note_ref,
    _note_ticks,
    _parent_from_state,
    _parse_window,
    _require_library_pin,
    _safe_clip_identifier,
    _sha256_value,
    _tempo_tick,
    _validate_parent_bounds,
    _window_chords,
    _window_seconds,
)
from .workbench_transform import _child_identity, _clip_identity


CLIP_NOTE_DELETION_WINDOW_SCHEMA = (
    "sunofriend.workbench-clip-note-deletion-window.v1"
)
CLIP_NOTE_DELETION_PREVIEW_SCHEMA = (
    "sunofriend.workbench-clip-note-deletion-preview.v1"
)
CLIP_NOTE_DELETION_RESULT_SCHEMA = (
    "sunofriend.workbench-clip-note-deletion-result.v1"
)
CLIP_NOTE_DELETION_SUMMARY_SCHEMA = (
    "sunofriend.workbench-clip-note-deletion-summary.v1"
)
_INTENT_SCHEMA = "sunofriend.workbench-clip-note-deletion-intent.v1"
_RECIPE_CONTRACT_VERSION = 1
_CORRECTION_KIND = "note_delete_patch"
_OPERATION = "delete_clip_notes"
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
_BLOCK_REASONS = (
    "context-note-on-outside-window",
    "duplicate-export-note-on",
    "retained-note-lifetime-would-change",
    "clip-horizon-would-change",
    "only-note-in-clip",
)
_DELETION_EFFECT_KEYS = {
    "library_mutated",
    "child_clip_created",
    "source_clip_mutated",
    "correction_applied",
    "note_deleted",
    "note_count_changed",
    "note_pitch_changed",
    "note_attack_velocity_changed",
    "note_timing_changed",
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


class WorkbenchClipDeletionCorrectionService:
    """Project and append one exact note-deletion correction at a time."""

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
                "Clip note-deletion window changed; load the window again"
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
                "Verified Clip library changed; load a fresh note-deletion window"
            ) from exc
        parent, summary = _parent_from_state(state, parsed)
        window = _window_projection(
            parent=parent,
            summary=summary,
            request=_window_request_from_patch(parsed),
        )
        if parsed["window_sha256"] != window["window_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip note-deletion window changed; load the window again"
            )
        projection = _project(
            parent=parent,
            summary=summary,
            request=parsed,
            window=window,
        )
        if parsed["projection_sha256"] != projection["projection_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip note-deletion projection changed; review the correction again"
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
            raise RuntimeError("Clip note-deletion child projection is not deterministic")
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
                    "Clip library changed; load a fresh note-deletion window"
                ) from exc
            raise

        replayed = append.replayed
        return {
            "schema": CLIP_NOTE_DELETION_RESULT_SCHEMA,
            "status": "replayed" if replayed else "created",
            "operation": "clip-note-deletion-correction-create",
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
                note_deleted=not replayed,
                note_count_changed=not replayed,
            ),
        }

    def correction_summary_from_state(
        self,
        clip_id: str,
        state: _LibraryState,
    ) -> dict[str, Any]:
        """Re-derive one recognized deletion from a verified library snapshot."""

        requested = _safe_clip_identifier(clip_id, "clip_id")
        try:
            child = state.clips[requested]
        except KeyError as exc:
            raise WorkbenchClipCorrectionNotFoundError(
                "Unknown corrected Clip"
            ) from exc
        if child.transform_recipe is None or child.transform_recipe.operation != _OPERATION:
            raise WorkbenchClipCorrectionError(
                "Clip does not contain a recognized note-deletion recipe"
            )
        if child.parent_clip_id is None or child.parent_clip_id not in state.clips:
            raise WorkbenchClipCorrectionError(
                "Recognized note-deletion child has no verified parent"
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
                "Note-deletion recipe window evidence does not match its parent"
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
            "Clip note-deletion window fields do not match the exact contract"
        )
    if request.get("correction_kind") != _CORRECTION_KIND:
        raise WorkbenchClipCorrectionError(
            "correction_kind must be 'note_delete_patch'"
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
            "Clip note-deletion request fields do not match the exact contract"
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
            "correction kind must be 'note_delete_patch'"
        )
    rows = value.get("changes")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_CHANGES:
        raise WorkbenchClipCorrectionError(
            "note-deletion patch requires 1 to 64 changes"
        )
    changes: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"note_ref"}:
            raise WorkbenchClipCorrectionError(
                "each note deletion requires exactly note_ref"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        if note_ref in seen:
            raise WorkbenchClipCorrectionError(
                "note deletions must use unique note refs"
            )
        seen.add(note_ref)
        changes.append({"note_ref": note_ref})
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
        "schema": CLIP_NOTE_DELETION_WINDOW_SCHEMA,
        "operation": "clip-note-deletion-window",
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
        "blocked_note_count": int(content["blocked_note_count"]),
        "blocked_reason_counts": dict(content["blocked_reason_counts"]),
        "chords": content["chords"],
        "policies": {
            "editable_membership": (
                "one exact normalized MIDI interval removable with all survivors and horizons unchanged"
            ),
            "context_membership": "export interval intersects window",
            "correction_scope": "exact existing note deletion only",
            "duplicate_export_note_on": (
                "same channel, start tick and pitch is visible but not editable"
            ),
            "retained_note_lifetime": (
                "deletion may not lengthen, shorten or otherwise change a surviving normalized MIDI note"
            ),
            "clip_horizon": (
                "deletion may not change beat, export-tick or source-second horizon"
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
    horizon_tick = _export_event_horizon_tick(parent)
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
    group_sizes = _export_note_on_group_sizes(parent, ticks=ticks)
    before_normalized = _normalized_intervals(parent, ticks=ticks)
    parent_horizons = _horizons(parent)
    reason_counts = {reason: 0 for reason in _BLOCK_REASONS}
    notes: list[dict[str, Any]] = []
    editable_count = 0
    for index, (note, (start_tick, end_tick)) in enumerate(zip(parent.notes, ticks)):
        if start_tick >= window["end_tick"] or end_tick <= window["start_tick"]:
            continue
        note_on_in_window = window["start_tick"] <= start_tick < window["end_tick"]
        if not note_on_in_window:
            block_reason = "context-note-on-outside-window"
        else:
            block_reason = _single_deletion_block_reason(
                parent,
                index,
                ticks=ticks,
                group_sizes=group_sizes,
                before_normalized=before_normalized,
                parent_horizons=parent_horizons,
            )
        editable = block_reason is None
        if editable:
            editable_count += 1
        else:
            assert block_reason in reason_counts
            reason_counts[block_reason] += 1
        notes.append(
            {
                "note_ref": _note_ref(parent_hash, index, note),
                "editable": editable,
                "edit_block_reason": block_reason,
                "export_note_on_group_size": group_sizes[
                    (parent.instrument.channel, start_tick, note.pitch)
                ],
                "channel": parent.instrument.channel,
                "pitch": note.pitch,
                "velocity": note.velocity,
                "release_velocity": note.release_velocity,
                "start_tick": start_tick,
                "end_tick": end_tick,
                "start_beat": note.start_beat,
                "duration_beats": note.duration_beats,
                "source_start_seconds": note.source_start_seconds,
                "source_end_seconds": note.source_end_seconds,
                "articulation": _public_articulation(note.articulation),
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
        "blocked_note_count": len(notes) - editable_count,
        "blocked_reason_counts": reason_counts,
        "chords": chords,
    }


def _single_deletion_block_reason(
    parent: MidiClip,
    index: int,
    *,
    ticks: Sequence[tuple[int, int]],
    group_sizes: Mapping[tuple[int, int, int], int],
    before_normalized: Sequence[MidiNoteInterval],
    parent_horizons: tuple[float, int, float],
) -> str | None:
    if len(parent.notes) <= 1:
        return "only-note-in-clip"
    note = parent.notes[index]
    start_tick, _end_tick = ticks[index]
    key = (parent.instrument.channel, start_tick, note.pitch)
    if group_sizes.get(key) != 1:
        return "duplicate-export-note-on"
    simulated = replace(
        parent,
        notes=tuple(note for position, note in enumerate(parent.notes) if position != index),
    )
    expected = [row for row in before_normalized if _normalized_key(row) != key]
    if (
        len(expected) != len(before_normalized) - 1
        or _normalized_intervals(simulated) != expected
    ):
        return "retained-note-lifetime-would-change"
    if _horizons(simulated) != parent_horizons:
        return "clip-horizon-would-change"
    return None


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
    _validate_deletion_only(parent, child, resolved)
    _validate_normalized_midi_delta(parent, child, resolved)
    _validate_horizons(parent, child)
    child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
    diff = _diff(parent, child, resolved)
    document: dict[str, Any] = {
        "schema": CLIP_NOTE_DELETION_PREVIEW_SCHEMA,
        "status": "previewed",
        "operation": "clip-note-deletion-correction-preview",
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
        if visible_note is not None and visible_note["edit_block_reason"] is not None:
            raise WorkbenchClipCorrectionError(
                "note deletion is blocked: " + str(visible_note["edit_block_reason"])
            )
        if (
            visible_note is None
            or visible_note["editable"] is not True
            or note_ref not in ref_to_index
        ):
            raise WorkbenchClipCorrectionError(
                "note deletion references a note outside the editable window"
            )
        index = ref_to_index[note_ref]
        resolved.append(
            {
                "note_ref": note_ref,
                "parent_note_index": index,
                "before": _note_payload(parent.notes[index]),
            }
        )
    resolved.sort(key=lambda row: row["parent_note_index"])
    if len(parent.notes) - len(resolved) < 1:
        raise WorkbenchClipCorrectionError(
            "note deletion child must retain at least one note"
        )
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
    deleted = {int(row["parent_note_index"]) for row in recipe_changes}
    notes = tuple(
        note for index, note in enumerate(parent.notes) if index not in deleted
    )
    if not notes:
        raise WorkbenchClipCorrectionError(
            "note deletion child must retain at least one note"
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
            "Clip does not contain a recognized note-deletion recipe"
        )
    if child.parent_clip_id != parent.clip_id or child.revision != parent.revision + 1:
        raise WorkbenchClipCorrectionError(
            "Note-deletion correction lineage does not match its parent"
        )
    parameters = child.transform_recipe.parameters_dict
    if set(parameters) != _RECIPE_PARAMETER_KEYS:
        raise WorkbenchClipCorrectionError(
            "Note-deletion correction recipe fields are invalid"
        )
    if parameters.get("contract_version") != _RECIPE_CONTRACT_VERSION:
        raise WorkbenchClipCorrectionError(
            "Note-deletion correction recipe version is unsupported"
        )
    if parameters.get("ticks_per_beat") != _TICKS_PER_BEAT:
        raise WorkbenchClipCorrectionError(
            "Note-deletion correction recipe TPQ is invalid"
        )
    parent_hash = hashlib.sha256(parent.canonical_bytes()).hexdigest()
    if parameters.get("parent_object_sha256") != parent_hash:
        raise WorkbenchClipCorrectionError(
            "Note-deletion recipe parent object does not match"
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
            "Note-deletion patch does not match its retained edit diff"
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
            "Note-deletion recipe intent digest does not match its retained evidence"
        )
    if child.clip_id != f"sf-correction-{intent_sha256}":
        raise WorkbenchClipCorrectionError(
            "Note-deletion correction child identity is invalid"
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
    if expected.canonical_bytes() != child.canonical_bytes():
        raise WorkbenchClipCorrectionError(
            "Note-deletion child does not match the exact retained edit diff"
        )
    _validate_deletion_only(parent, child, recipe_changes)
    _validate_normalized_midi_delta(parent, child, recipe_changes)
    _validate_horizons(parent, child)
    public_changes = [_public_change(parent, row) for row in recipe_changes]
    return {
        "schema": CLIP_NOTE_DELETION_SUMMARY_SCHEMA,
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
        raise WorkbenchClipCorrectionError("Note-deletion recipe changes are invalid")
    window_content = _bounded_window_content(parent, parent_hash, window)
    visible = {row["note_ref"]: row for row in window_content["notes"]}
    seen_refs: set[str] = set()
    seen_indices: set[int] = set()
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {
            "note_ref",
            "parent_note_index",
            "before",
        }:
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe change is invalid"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        index = row.get("parent_note_index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe note index is invalid"
            )
        if index < 0 or index >= len(parent.notes):
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe note index is invalid"
            )
        if note_ref in seen_refs or index in seen_indices:
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe changes are duplicated"
            )
        seen_refs.add(note_ref)
        seen_indices.add(index)
        before = _note_mapping(row.get("before"), "before")
        parent_note = parent.notes[index]
        if _document_hash(before) != _document_hash(_note_payload(parent_note)):
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe before-note does not match its parent"
            )
        if note_ref != _note_ref(parent_hash, index, parent_note):
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe note ref is invalid"
            )
        window_row = visible.get(note_ref)
        if window_row is None or window_row["editable"] is not True:
            raise WorkbenchClipCorrectionError(
                "Note-deletion recipe note is outside its editable window"
            )
        rows.append(
            {
                "note_ref": note_ref,
                "parent_note_index": index,
                "before": before,
            }
        )
    rows.sort(key=lambda row: row["parent_note_index"])
    if len(parent.notes) - len(rows) < 1:
        raise WorkbenchClipCorrectionError(
            "note deletion child must retain at least one note"
        )
    return rows


def _correction_from_recipe_changes(
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [{"note_ref": str(row["note_ref"])} for row in changes]
    rows.sort(key=lambda row: row["note_ref"])
    return {"kind": _CORRECTION_KIND, "changes": rows}


def _validate_deletion_only(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    parent_metadata = parent.to_dict()
    child_metadata = child.to_dict()
    for document in (parent_metadata, child_metadata):
        for field in (
            "clip_id",
            "parent_clip_id",
            "revision",
            "transform_recipe",
            "notes",
        ):
            document.pop(field)
    if _document_hash(parent_metadata) != _document_hash(child_metadata):
        raise WorkbenchClipCorrectionError(
            "Note deletion changed protected Clip metadata"
        )
    deleted = {int(row["parent_note_index"]) for row in changes}
    expected_notes = tuple(
        note for index, note in enumerate(parent.notes) if index not in deleted
    )
    exact_notes = len(child.notes) == len(expected_notes) and all(
        _document_hash(_note_payload(before))
        == _document_hash(_note_payload(after))
        for before, after in zip(expected_notes, child.notes)
    )
    if not expected_notes or not exact_notes:
        raise WorkbenchClipCorrectionError(
            "Note deletion changed a retained note or removed an unexpected note"
        )


def _export_note_on_group_sizes(
    clip: MidiClip,
    *,
    ticks: Sequence[tuple[int, int]] | None = None,
) -> dict[tuple[int, int, int], int]:
    note_ticks = list(ticks) if ticks is not None else [_note_ticks(clip, note) for note in clip.notes]
    groups: dict[tuple[int, int, int], int] = {}
    for note, (start_tick, _end_tick) in zip(clip.notes, note_ticks):
        key = (clip.instrument.channel, start_tick, note.pitch)
        groups[key] = groups.get(key, 0) + 1
    return groups


def _normalized_intervals(
    clip: MidiClip,
    *,
    ticks: Sequence[tuple[int, int]] | None = None,
) -> list[MidiNoteInterval]:
    note_ticks = list(ticks) if ticks is not None else [_note_ticks(clip, note) for note in clip.notes]
    intervals = [
        MidiNoteInterval(
            owner=0,
            channel=clip.instrument.channel,
            start_tick=start_tick,
            end_tick=end_tick,
            pitch=note.pitch,
            velocity=note.velocity,
            release_velocity=note.release_velocity,
        )
        for note, (start_tick, end_tick) in zip(clip.notes, note_ticks)
    ]
    return normalize_midi_intervals(intervals)


def _normalized_key(note: MidiNoteInterval) -> tuple[int, int, int]:
    return note.channel, note.start_tick, note.pitch


def _validate_normalized_midi_delta(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    group_sizes = _export_note_on_group_sizes(parent)
    targets: set[tuple[int, int, int]] = set()
    for row in changes:
        note = parent.notes[int(row["parent_note_index"])]
        start_tick, _end_tick = _note_ticks(parent, note)
        key = (parent.instrument.channel, start_tick, note.pitch)
        if group_sizes.get(key) != 1 or key in targets:
            raise WorkbenchClipCorrectionError(
                "Note deletion is not one-to-one with a normalized MIDI note"
            )
        targets.add(key)
    before = _normalized_intervals(parent)
    after = _normalized_intervals(child)
    expected = [row for row in before if _normalized_key(row) not in targets]
    if len(expected) != len(before) - len(targets) or after != expected:
        raise WorkbenchClipCorrectionError(
            "Note deletion changed a retained normalized MIDI note"
        )


def _source_horizon_seconds(clip: MidiClip) -> float:
    ends = [note.source_end_seconds for note in clip.notes]
    ends.extend(
        chord.source_end_seconds
        if chord.source_end_seconds is not None
        else clip.tempo_map.source_seconds_at(chord.end_beat)
        for chord in clip.chords
    )
    return max(0.0, *ends)


def _horizons(clip: MidiClip) -> tuple[float, int, float]:
    return (
        clip.duration_beats,
        _export_event_horizon_tick(clip),
        _source_horizon_seconds(clip),
    )


def _export_event_horizon_tick(clip: MidiClip) -> int:
    """Return the last event tick emitted by the deterministic SMF writer."""

    normalized_note_ends = (note.end_tick for note in _normalized_intervals(clip))
    chord_starts = (_chord_ticks(clip, chord)[0] for chord in clip.chords)
    mode, _bpm = resolve_export_timing(
        clip,
        timing_mode="auto",
        garageband_bpm=None,
    )
    tempo_ticks = (
        (0,)
        if mode == "stem_locked"
        else tuple(_tempo_tick(point) for point in clip.tempo_map.tempo_points)
    )
    return max(0, *normalized_note_ends, *chord_starts, *tempo_ticks)


def _validate_horizons(parent: MidiClip, child: MidiClip) -> None:
    if _horizons(parent) != _horizons(child):
        raise WorkbenchClipCorrectionError(
            "Note deletion changed the Clip beat, export or source horizon"
        )


def _diff(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    public = [_public_change(parent, row) for row in changes]
    before_normalized = _normalized_intervals(parent)
    after_normalized = _normalized_intervals(child)
    return {
        "kind": _CORRECTION_KIND,
        "changed_note_count": len(public),
        "changes": public,
        "note_count_before": len(parent.notes),
        "note_count_after": len(child.notes),
        "normalized_midi_note_count_before": len(before_normalized),
        "normalized_midi_note_count_after": len(after_normalized),
        "pitch_range_before": _pitch_range(parent.notes),
        "pitch_range_after": _pitch_range(child.notes),
        "duration_beats_before": parent.duration_beats,
        "duration_beats_after": child.duration_beats,
        "duration_seconds_before": _maximum_duration_seconds(parent),
        "duration_seconds_after": _maximum_duration_seconds(child),
        "retained_normalized_notes_changed": 0,
        "unchanged": _unchanged_projection(),
    }


def _public_change(parent: MidiClip, row: Mapping[str, Any]) -> dict[str, Any]:
    before = dict(row["before"])
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
        "velocity": before["velocity"],
        "release_velocity": before["release_velocity"],
        "articulation": _public_articulation(before["articulation"]),
    }


def _pitch_range(notes: Sequence[ClipNote]) -> dict[str, int] | None:
    if not notes:
        return None
    pitches = [note.pitch for note in notes]
    return {"minimum": min(pitches), "maximum": max(pitches)}


def _public_articulation(value: Any) -> str | None:
    """Project optional articulation text without exposing a local path."""

    if value is None:
        return None
    return _safe_text(
        value,
        fallback="private articulation",
        maximum=120,
    )[0]


def _unchanged_projection() -> dict[str, bool]:
    return {
        "retained_note_payloads": True,
        "normalized_midi_survivors": True,
        "note_pitches": True,
        "note_onsets": True,
        "note_durations": True,
        "source_seconds": True,
        "microtiming": True,
        "velocity": True,
        "release_velocity": True,
        "articulation": True,
        "clip_horizon": True,
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
        "Only the named notes are removed. Every retained ClipNote and normalized MIDI lifetime remains exact.",
        "Notes whose removal would expose a duplicate, retime a surviving note or shorten the Clip horizon are blocked.",
        "The child retains at least one note and is not selected, placed, auditioned or added to a GarageBand Pack automatically.",
    ]


def _effects(**changes: bool) -> dict[str, bool]:
    effects = {key: False for key in sorted(_DELETION_EFFECT_KEYS)}
    for key, value in changes.items():
        if key not in _DELETION_EFFECT_KEYS or not isinstance(value, bool):
            raise ValueError("Unknown Clip note-deletion correction effect")
        effects[key] = value
    return effects


__all__ = [
    "CLIP_NOTE_DELETION_PREVIEW_SCHEMA",
    "CLIP_NOTE_DELETION_RESULT_SCHEMA",
    "CLIP_NOTE_DELETION_SUMMARY_SCHEMA",
    "CLIP_NOTE_DELETION_WINDOW_SCHEMA",
    "WorkbenchClipDeletionCorrectionService",
]
