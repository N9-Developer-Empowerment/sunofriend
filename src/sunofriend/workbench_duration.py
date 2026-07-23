"""Bounded immutable Clip note-end correction.

This policy is deliberately separate from the published pitch, attack-velocity,
deletion and onset contracts. It shifts explicitly referenced existing Note Off
events on the 480-TPQ export grid, reconciles the Clip's beat and source-second
coordinates, and accepts a child only when normalized MIDI replaces exactly the
named lifetimes without changing any onset or surviving interval.
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
    _MAX_ABSOLUTE_TICK,
    _MAX_EDITABLE_NOTES,
    _MAX_VISIBLE_NOTES,
    _MAX_WINDOW_CHORDS,
    _MAX_WINDOW_SECONDS,
    _TICKS_PER_BEAT,
    _chord_ticks,
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
    _tempo_tick,
    _validate_parent_bounds,
    _window_chords,
    _window_seconds,
)
from .workbench_transform import _child_identity, _clip_identity


CLIP_NOTE_END_WINDOW_SCHEMA = "sunofriend.workbench-clip-note-end-window.v1"
CLIP_NOTE_END_PREVIEW_SCHEMA = "sunofriend.workbench-clip-note-end-preview.v1"
CLIP_NOTE_END_RESULT_SCHEMA = "sunofriend.workbench-clip-note-end-result.v1"
CLIP_NOTE_END_SUMMARY_SCHEMA = "sunofriend.workbench-clip-note-end-summary.v1"
_INTENT_SCHEMA = "sunofriend.workbench-clip-note-end-intent.v1"
_RECIPE_CONTRACT_VERSION = 1
_CORRECTION_KIND = "note_end_shift_patch"
_OPERATION = "shift_note_ends"
_MAX_CHANGES = 64
_MAX_END_DELTA_TICKS = _TICKS_PER_BEAT
_MIN_DURATION_TICKS = 1
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
    "context-note-outside-window",
    "duplicate-export-note-on",
    "normalized-lifetime-dependent",
    "unsupported-stem-locked-microtiming",
)
_EFFECT_KEYS = {
    "library_mutated",
    "child_clip_created",
    "source_clip_mutated",
    "correction_applied",
    "note_onset_changed",
    "note_timing_changed",
    "note_duration_changed",
    "note_pitch_changed",
    "note_attack_velocity_changed",
    "release_velocity_changed",
    "note_count_changed",
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


class WorkbenchClipDurationCorrectionService:
    """Project and append one exact existing-note end correction at a time."""

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
                "Clip note-end window changed; load the window again"
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
                "Verified Clip library changed; load a fresh note-end window"
            ) from exc
        parent, summary = _parent_from_state(state, parsed)
        window = _window_projection(
            parent=parent,
            summary=summary,
            request=_window_request_from_patch(parsed),
        )
        if parsed["window_sha256"] != window["window_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip note-end window changed; load the window again"
            )
        projection = _project(
            parent=parent,
            summary=summary,
            request=parsed,
            window=window,
        )
        if parsed["projection_sha256"] != projection["projection_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip note-end projection changed; review the correction again"
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
            raise RuntimeError("Clip note-end child projection is not deterministic")
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
                    "Clip library changed; load a fresh note-end window"
                ) from exc
            raise

        replayed = append.replayed
        return {
            "schema": CLIP_NOTE_END_RESULT_SCHEMA,
            "status": "replayed" if replayed else "created",
            "operation": "clip-note-end-correction-create",
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
                note_duration_changed=not replayed,
                note_timing_changed=not replayed,
            ),
        }

    def correction_summary_from_state(
        self,
        clip_id: str,
        state: _LibraryState,
    ) -> dict[str, Any]:
        """Re-derive one recognized note-end correction after restart."""

        requested = _safe_clip_identifier(clip_id, "clip_id")
        try:
            child = state.clips[requested]
        except KeyError as exc:
            raise WorkbenchClipCorrectionNotFoundError(
                "Unknown corrected Clip"
            ) from exc
        if child.transform_recipe is None or child.transform_recipe.operation != _OPERATION:
            raise WorkbenchClipCorrectionError(
                "Clip does not contain a recognized note-end recipe"
            )
        if child.parent_clip_id is None or child.parent_clip_id not in state.clips:
            raise WorkbenchClipCorrectionError(
                "Recognized note-end child has no verified parent"
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
                "Note-end recipe window evidence does not match its parent"
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
            "Clip note-end window fields do not match the exact contract"
        )
    if request.get("correction_kind") != _CORRECTION_KIND:
        raise WorkbenchClipCorrectionError(
            "correction_kind must be 'note_end_shift_patch'"
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
            "Clip note-end request fields do not match the exact contract"
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
            "correction kind must be 'note_end_shift_patch'"
        )
    rows = value.get("changes")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_CHANGES:
        raise WorkbenchClipCorrectionError(
            "note-end shift patch requires 1 to 64 changes"
        )
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "note_ref",
            "target_end_tick",
        }:
            raise WorkbenchClipCorrectionError(
                "each note-end change requires exactly note_ref and target_end_tick"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        target = _exact_int(row.get("target_end_tick"), "target_end_tick")
        if not 0 <= target <= _MAX_ABSOLUTE_TICK:
            raise WorkbenchClipCorrectionError(
                "target_end_tick must be an integer within the SMF tick range"
            )
        if note_ref in seen:
            raise WorkbenchClipCorrectionError(
                "note-end changes must use unique note refs"
            )
        seen.add(note_ref)
        changes.append({"note_ref": note_ref, "target_end_tick": target})
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
        "schema": CLIP_NOTE_END_WINDOW_SCHEMA,
        "operation": "clip-note-end-window",
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
                "unique exact normalized MIDI lifetime fully contained in the loaded half-open window"
            ),
            "context_membership": (
                "export interval intersects the window but is not fully contained"
            ),
            "correction_scope": (
                "bounded existing-note end shift only; stem-locked notes require zero microtiming"
            ),
            "maximum_end_delta_ticks": _MAX_END_DELTA_TICKS,
            "minimum_duration_ticks": _MIN_DURATION_TICKS,
            "duplicate_export_note_on": (
                "same channel, start tick and pitch is visible but not editable"
            ),
            "normalized_lifetime": (
                "notes whose own Note Off is changed by normalization are not editable"
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
    if int(window["start_tick"]) > _clip_horizon_tick(parent):
        raise WorkbenchClipCorrectionError(
            "correction window starts after the Clip export horizon"
        )
    duration_seconds = _window_seconds(parent, window)
    if duration_seconds > _MAX_WINDOW_SECONDS + 1e-9:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds 15 export seconds"
        )

    ticks = [_note_ticks(parent, note) for note in parent.notes]
    visible = [
        (index, note, start_tick, end_tick)
        for index, (note, (start_tick, end_tick)) in enumerate(
            zip(parent.notes, ticks)
        )
        if start_tick < window["end_tick"] and end_tick > window["start_tick"]
    ]
    if len(visible) > _MAX_VISIBLE_NOTES:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds the 512 visible-note limit"
        )
    group_sizes = _export_note_on_group_sizes(parent, ticks=ticks)
    exact_sources = _source_interval_exactness(parent, ticks=ticks)
    timing_mode, _timing_bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    reason_counts = {reason: 0 for reason in _BLOCK_REASONS}
    notes: list[dict[str, Any]] = []
    editable_count = 0
    for index, note, start_tick, end_tick in visible:
        if not (
            window["start_tick"] <= start_tick
            and end_tick <= window["end_tick"]
        ):
            block_reason = "context-note-outside-window"
        elif group_sizes[(parent.instrument.channel, start_tick, note.pitch)] != 1:
            block_reason = "duplicate-export-note-on"
        elif not exact_sources[index]:
            block_reason = "normalized-lifetime-dependent"
        elif timing_mode == "stem_locked" and (
            note.microtiming_seconds != 0.0
            or note.end_microtiming_seconds != 0.0
        ):
            block_reason = "unsupported-stem-locked-microtiming"
        else:
            block_reason = None
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
                "duration_ticks": end_tick - start_tick,
                "start_beat": note.start_beat,
                "duration_beats": note.duration_beats,
                "source_start_seconds": note.source_start_seconds,
                "source_end_seconds": note.source_end_seconds,
                "microtiming_seconds": note.microtiming_seconds,
                "end_microtiming_seconds": note.end_microtiming_seconds,
                "articulation": _public_articulation(note.articulation),
            }
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


def _source_interval_exactness(
    parent: MidiClip,
    *,
    ticks: Sequence[tuple[int, int]],
) -> tuple[bool, ...]:
    """Return whether each unique source owns its normalized Note Off exactly.

    Moving only an end leaves every onset in place, so a source may remain
    editable even when its onset truncates a preceding same-pitch note. Only a
    duplicate onset or an end truncated by the next distinct onset makes the
    source lifetime ambiguous for this operation.
    """

    voices: dict[tuple[int, int], dict[int, list[tuple[int, int]]]] = {}
    channel = parent.instrument.channel
    for index, (note, (start_tick, end_tick)) in enumerate(zip(parent.notes, ticks)):
        starts = voices.setdefault((channel, note.pitch), {})
        starts.setdefault(start_tick, []).append((index, end_tick))

    exact = [False] * len(parent.notes)
    for starts in voices.values():
        ordered_starts = sorted(starts)
        for position, start_tick in enumerate(ordered_starts):
            group = starts[start_tick]
            if len(group) != 1:
                continue
            index, end_tick = group[0]
            next_start = (
                ordered_starts[position + 1]
                if position + 1 < len(ordered_starts)
                else None
            )
            source_unchanged = next_start is None or end_tick <= next_start
            exact[index] = source_unchanged
    return tuple(exact)


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
    _validate_duration_only(parent, child, resolved)
    _reject_target_interactions(parent, resolved)
    _validate_normalized_midi_delta(parent, child, resolved)
    _validate_horizons(parent, child)
    child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
    diff = _diff(parent, resolved)
    document: dict[str, Any] = {
        "schema": CLIP_NOTE_END_PREVIEW_SCHEMA,
        "status": "previewed",
        "operation": "clip-note-end-correction-preview",
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
    mode, bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    resolved: list[dict[str, Any]] = []
    for row in request["correction"]["changes"]:
        note_ref = row["note_ref"]
        visible_note = visible.get(note_ref)
        if visible_note is None or note_ref not in ref_to_index:
            raise WorkbenchClipCorrectionError(
                "note-end correction references a note outside the editable window"
            )
        if visible_note["editable"] is not True:
            raise WorkbenchClipCorrectionError(
                "note-end correction is blocked: "
                + str(visible_note["edit_block_reason"])
            )
        index = ref_to_index[note_ref]
        before = parent.notes[index]
        before_start, before_end = _note_ticks(parent, before)
        target = int(row["target_end_tick"])
        if not (
            request["window"]["start_tick"] <= before_start
            and before_end <= request["window"]["end_tick"]
        ):
            raise WorkbenchClipCorrectionError(
                "original note interval is not fully inside the loaded window"
            )
        delta = target - before_end
        if delta == 0:
            raise WorkbenchClipCorrectionError(
                "note-end correction contains a no-op"
            )
        if abs(delta) > _MAX_END_DELTA_TICKS:
            raise WorkbenchClipCorrectionError(
                "note-end correction exceeds the 480 tick end-delta limit"
            )
        if target < before_start + _MIN_DURATION_TICKS:
            raise WorkbenchClipCorrectionError(
                "note-end correction requires at least one MIDI tick of duration"
            )
        if target > request["window"]["end_tick"]:
            raise WorkbenchClipCorrectionError(
                "target note interval must remain fully inside the loaded window"
            )
        if target > _MAX_ABSOLUTE_TICK:
            raise WorkbenchClipCorrectionError(
                "note-end correction would exceed the SMF tick range"
            )
        after = _shift_note_end(
            parent,
            before,
            tick_delta=delta,
            timing_mode=mode,
            export_bpm=bpm,
        )
        after_start, after_end = _note_ticks(parent, after)
        if (after_start, after_end) != (before_start, target):
            raise WorkbenchClipCorrectionError(
                "note-end dual-time update does not round-trip to the requested MIDI ticks"
            )
        resolved.append(
            {
                "note_ref": note_ref,
                "parent_note_index": index,
                "before": _note_payload(before),
                "after": _note_payload(after),
                "before_start_tick": before_start,
                "before_end_tick": before_end,
                "after_start_tick": after_start,
                "after_end_tick": after_end,
            }
        )
    resolved.sort(key=lambda item: item["parent_note_index"])
    _reject_target_interactions(parent, resolved)
    return resolved


def _shift_note_end(
    clip: MidiClip,
    note: ClipNote,
    *,
    tick_delta: int,
    timing_mode: str,
    export_bpm: float,
) -> ClipNote:
    if timing_mode == "musical":
        duration_beats = note.duration_beats + tick_delta / _TICKS_PER_BEAT
        if duration_beats <= 0:
            raise WorkbenchClipCorrectionError(
                "note-end correction cannot derive positive beat timing"
            )
        end_beat = note.start_beat + duration_beats
        source_end = (
            clip.tempo_map.source_seconds_at(end_beat)
            + note.end_microtiming_seconds
        )
        if source_end <= note.source_start_seconds:
            raise WorkbenchClipCorrectionError(
                "note-end correction would create reversed source timing"
            )
        return replace(
            note,
            duration_beats=duration_beats,
            source_end_seconds=source_end,
        )

    if (
        note.microtiming_seconds != 0.0
        or note.end_microtiming_seconds != 0.0
    ):
        raise WorkbenchClipCorrectionError(
            "stem-locked note-end correction requires zero microtiming"
        )
    seconds_delta = tick_delta * 60.0 / (export_bpm * _TICKS_PER_BEAT)
    source_end = note.source_end_seconds + seconds_delta
    if source_end <= note.source_start_seconds:
        raise WorkbenchClipCorrectionError(
            "note-end correction would create reversed source timing"
        )
    end_beat = clip.tempo_map.beat_at_source_seconds(
        source_end - note.end_microtiming_seconds
    )
    duration_beats = end_beat - note.start_beat
    if duration_beats <= 0:
        raise WorkbenchClipCorrectionError(
            "note-end correction cannot derive positive beat timing"
        )
    return replace(
        note,
        duration_beats=duration_beats,
        source_end_seconds=source_end,
    )


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
    replacements = {
        int(row["parent_note_index"]): ClipNote(**dict(row["after"]))
        for row in recipe_changes
    }
    notes = tuple(
        replacements.get(index, note)
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
            "Clip does not contain a recognized note-end recipe"
        )
    if child.parent_clip_id != parent.clip_id or child.revision != parent.revision + 1:
        raise WorkbenchClipCorrectionError(
            "Note-end correction lineage does not match its parent"
        )
    parameters = child.transform_recipe.parameters_dict
    if set(parameters) != _RECIPE_PARAMETER_KEYS:
        raise WorkbenchClipCorrectionError(
            "Note-end correction recipe fields are invalid"
        )
    if parameters.get("contract_version") != _RECIPE_CONTRACT_VERSION:
        raise WorkbenchClipCorrectionError(
            "Note-end correction recipe version is unsupported"
        )
    if parameters.get("ticks_per_beat") != _TICKS_PER_BEAT:
        raise WorkbenchClipCorrectionError(
            "Note-end correction recipe TPQ is invalid"
        )
    parent_hash = hashlib.sha256(parent.canonical_bytes()).hexdigest()
    if parameters.get("parent_object_sha256") != parent_hash:
        raise WorkbenchClipCorrectionError(
            "Note-end recipe parent object does not match"
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
    if correction != _correction_from_recipe_changes(recipe_changes):
        raise WorkbenchClipCorrectionError(
            "Note-end patch does not match its retained edit diff"
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
            "Note-end recipe intent digest does not match its retained evidence"
        )
    if child.clip_id != f"sf-correction-{intent_sha256}":
        raise WorkbenchClipCorrectionError(
            "Note-end correction child identity is invalid"
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
            "Note-end child does not match the exact retained edit diff"
        )
    _validate_duration_only(parent, child, recipe_changes)
    _reject_target_interactions(parent, recipe_changes)
    _validate_normalized_midi_delta(parent, child, recipe_changes)
    _validate_horizons(parent, child)
    mode, bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    public_changes = [
        _public_change(parent, row, mode=mode, bpm=bpm)
        for row in recipe_changes
    ]
    return {
        "schema": CLIP_NOTE_END_SUMMARY_SCHEMA,
        "operation": _OPERATION,
        "contract_version": _RECIPE_CONTRACT_VERSION,
        "parent_clip_id": parent.clip_id,
        "parent_object_sha256": parent_hash,
        "child_clip_id": child.clip_id,
        "child_object_sha256": hashlib.sha256(child.canonical_bytes()).hexdigest(),
        "window": {**window, "ticks_per_beat": _TICKS_PER_BEAT},
        "changed_note_count": len(public_changes),
        "timing_mode": mode,
        "export_bpm": bpm,
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
        raise WorkbenchClipCorrectionError("Note-end recipe changes are invalid")
    window_content = _bounded_window_content(parent, parent_hash, window)
    visible = {row["note_ref"]: row for row in window_content["notes"]}
    ticks = [_note_ticks(parent, note) for note in parent.notes]
    mode, bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    seen_refs: set[str] = set()
    seen_indices: set[int] = set()
    rows: list[dict[str, Any]] = []
    for row in value:
        expected_fields = {
            "note_ref",
            "parent_note_index",
            "before",
            "after",
            "before_start_tick",
            "before_end_tick",
            "after_start_tick",
            "after_end_tick",
        }
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise WorkbenchClipCorrectionError(
                "Note-end recipe change is invalid"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        index = _exact_int(row.get("parent_note_index"), "parent_note_index")
        if index < 0 or index >= len(parent.notes):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe note index is invalid"
            )
        if note_ref in seen_refs or index in seen_indices:
            raise WorkbenchClipCorrectionError(
                "Note-end recipe changes are duplicated"
            )
        seen_refs.add(note_ref)
        seen_indices.add(index)
        before = _note_mapping(row.get("before"), "before")
        after = _note_mapping(row.get("after"), "after")
        parent_note = parent.notes[index]
        if _document_hash(before) != _document_hash(_note_payload(parent_note)):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe before-note does not match its parent"
            )
        if note_ref != _note_ref(parent_hash, index, parent_note):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe note ref is invalid"
            )
        before_start, before_end = ticks[index]
        stored_ticks = tuple(
            _exact_int(row.get(field), field)
            for field in (
                "before_start_tick",
                "before_end_tick",
                "after_start_tick",
                "after_end_tick",
            )
        )
        if stored_ticks[:2] != (before_start, before_end):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe source ticks do not match its parent"
            )
        window_row = visible.get(note_ref)
        if window_row is None or window_row["editable"] is not True:
            raise WorkbenchClipCorrectionError(
                "Note-end recipe source note is outside its editable window"
            )
        if not (
            window["start_tick"] <= stored_ticks[2]
            and stored_ticks[3] <= window["end_tick"]
        ):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe target interval is outside its window"
            )
        if stored_ticks[2] != before_start:
            raise WorkbenchClipCorrectionError(
                "Note-end recipe changed the MIDI onset"
            )
        delta = stored_ticks[3] - before_end
        if delta == 0 or abs(delta) > _MAX_END_DELTA_TICKS:
            raise WorkbenchClipCorrectionError(
                "Note-end recipe tick delta is invalid"
            )
        if (
            stored_ticks[3] < before_start + _MIN_DURATION_TICKS
            or stored_ticks[3] > _MAX_ABSOLUTE_TICK
        ):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe duration or MIDI bound is invalid"
            )
        expected_after = _shift_note_end(
            parent,
            parent_note,
            tick_delta=delta,
            timing_mode=mode,
            export_bpm=bpm,
        )
        if _document_hash(after) != _document_hash(_note_payload(expected_after)):
            raise WorkbenchClipCorrectionError(
                "Note-end recipe dual-time coordinates are invalid"
            )
        if _note_ticks(parent, expected_after) != stored_ticks[2:]:
            raise WorkbenchClipCorrectionError(
                "Note-end recipe does not round-trip to its retained MIDI ticks"
            )
        rows.append(
            {
                "note_ref": note_ref,
                "parent_note_index": index,
                "before": before,
                "after": after,
                "before_start_tick": stored_ticks[0],
                "before_end_tick": stored_ticks[1],
                "after_start_tick": stored_ticks[2],
                "after_end_tick": stored_ticks[3],
            }
        )
    rows.sort(key=lambda item: item["parent_note_index"])
    _reject_target_interactions(parent, rows)
    return rows


def _correction_from_recipe_changes(
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [
        {
            "note_ref": str(row["note_ref"]),
            "target_end_tick": int(row["after_end_tick"]),
        }
        for row in changes
    ]
    rows.sort(key=lambda row: row["note_ref"])
    return {"kind": _CORRECTION_KIND, "changes": rows}


def _validate_duration_only(
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
            "Note-end correction changed protected Clip metadata"
        )
    replacements = {
        int(row["parent_note_index"]): ClipNote(**dict(row["after"]))
        for row in changes
    }
    expected_notes = tuple(
        sorted(
            (
                replacements.get(index, note)
                for index, note in enumerate(parent.notes)
            ),
            key=lambda note: (note.start_beat, note.pitch, note.duration_beats),
        )
    )
    exact_notes = len(child.notes) == len(expected_notes) and all(
        _document_hash(_note_payload(expected))
        == _document_hash(_note_payload(observed))
        for expected, observed in zip(expected_notes, child.notes)
    )
    if len(parent.notes) != len(child.notes) or not exact_notes:
        raise WorkbenchClipCorrectionError(
            "Note-end correction changed an unaffected note or unexpected field"
        )
    for row in changes:
        before = dict(row["before"])
        after = dict(row["after"])
        protected_before = {
            field: before[field]
            for field in (
                "start_beat",
                "pitch",
                "velocity",
                "source_start_seconds",
                "release_velocity",
                "microtiming_seconds",
                "end_microtiming_seconds",
                "articulation",
            )
        }
        protected_after = {field: after[field] for field in protected_before}
        if _document_hash(protected_before) != _document_hash(protected_after):
            raise WorkbenchClipCorrectionError(
                "Note-end correction changed its onset, pitch or expression"
            )
        if int(row["before_start_tick"]) != int(row["after_start_tick"]):
            raise WorkbenchClipCorrectionError(
                "Note-end correction changed its MIDI onset"
            )
        if int(row["before_end_tick"]) == int(row["after_end_tick"]):
            raise WorkbenchClipCorrectionError(
                "Note-end correction contains a no-op"
            )


def _reject_target_interactions(
    parent: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    starts_by_pitch: dict[int, list[int]] = {}
    for note, (start_tick, _end_tick) in zip(
        parent.notes,
        (_note_ticks(parent, note) for note in parent.notes),
    ):
        starts_by_pitch.setdefault(note.pitch, []).append(start_tick)
    distinct_starts = {
        pitch: sorted(set(starts))
        for pitch, starts in starts_by_pitch.items()
    }
    for row in changes:
        note = parent.notes[int(row["parent_note_index"])]
        start_tick = int(row["after_start_tick"])
        target_end = int(row["after_end_tick"])
        next_start = next(
            (
                candidate
                for candidate in distinct_starts[note.pitch]
                if candidate > start_tick
            ),
            None,
        )
        if next_start is not None and target_end > next_start:
            raise WorkbenchClipCorrectionError(
                "Note-end target would overlap a later same-pitch MIDI onset"
            )


def _export_note_on_group_sizes(
    clip: MidiClip,
    *,
    ticks: Sequence[tuple[int, int]] | None = None,
) -> dict[tuple[int, int, int], int]:
    note_ticks = list(ticks) if ticks is not None else [
        _note_ticks(clip, note) for note in clip.notes
    ]
    groups: dict[tuple[int, int, int], int] = {}
    for note, (start_tick, _end_tick) in zip(clip.notes, note_ticks):
        key = (clip.instrument.channel, start_tick, note.pitch)
        groups[key] = groups.get(key, 0) + 1
    return groups


def _raw_interval(
    clip: MidiClip,
    index: int,
    ticks: tuple[int, int],
) -> MidiNoteInterval:
    note = clip.notes[index]
    return MidiNoteInterval(
        owner=0,
        channel=clip.instrument.channel,
        start_tick=ticks[0],
        end_tick=ticks[1],
        pitch=note.pitch,
        velocity=note.velocity,
        release_velocity=note.release_velocity,
    )


def _normalized_intervals(
    clip: MidiClip,
    *,
    ticks: Sequence[tuple[int, int]] | None = None,
) -> list[MidiNoteInterval]:
    note_ticks = list(ticks) if ticks is not None else [
        _note_ticks(clip, note) for note in clip.notes
    ]
    return normalize_midi_intervals(
        _raw_interval(clip, index, note_tick)
        for index, note_tick in enumerate(note_ticks)
    )


def _normalized_key(note: MidiNoteInterval) -> tuple[int, int, int]:
    return note.channel, note.start_tick, note.pitch


def _validate_normalized_midi_delta(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    before = _normalized_intervals(parent)
    after = _normalized_intervals(child)
    old_keys: set[tuple[int, int, int]] = set()
    replacements: list[MidiNoteInterval] = []
    for row in changes:
        index = int(row["parent_note_index"])
        note = parent.notes[index]
        old_key = (parent.instrument.channel, int(row["before_start_tick"]), note.pitch)
        if old_key in old_keys:
            raise WorkbenchClipCorrectionError(
                "Note-end correction source identity is ambiguous"
            )
        old_keys.add(old_key)
        source_matches = [item for item in before if _normalized_key(item) == old_key]
        if len(source_matches) != 1 or source_matches[0].end_tick != int(
            row["before_end_tick"]
        ):
            raise WorkbenchClipCorrectionError(
                "Note-end correction source interval is normalization-dependent"
            )
        replacements.append(
            MidiNoteInterval(
                owner=0,
                channel=parent.instrument.channel,
                start_tick=int(row["after_start_tick"]),
                end_tick=int(row["after_end_tick"]),
                pitch=note.pitch,
                velocity=note.velocity,
                release_velocity=note.release_velocity,
            )
        )
    survivors = [item for item in before if _normalized_key(item) not in old_keys]
    expected = sorted(
        [*survivors, *replacements],
        key=lambda note: (
            note.start_tick,
            note.channel,
            note.pitch,
            note.end_tick,
            note.owner,
            -note.velocity,
        ),
    )
    if len(expected) != len(before) or after != expected:
        raise WorkbenchClipCorrectionError(
            "Note-end correction changed a surviving or unexpected normalized MIDI interval"
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


def _export_event_horizon_tick(clip: MidiClip) -> int:
    normalized_note_ends = (note.end_tick for note in _normalized_intervals(clip))
    chord_starts = (_chord_ticks(clip, chord)[0] for chord in clip.chords)
    mode, _bpm = resolve_export_timing(
        clip, timing_mode="auto", garageband_bpm=None
    )
    tempo_ticks = (
        (0,)
        if mode == "stem_locked"
        else tuple(_tempo_tick(point) for point in clip.tempo_map.tempo_points)
    )
    return max(0, *normalized_note_ends, *chord_starts, *tempo_ticks)


def _horizons(clip: MidiClip) -> tuple[float, int, float]:
    return (
        clip.duration_beats,
        _export_event_horizon_tick(clip),
        _source_horizon_seconds(clip),
    )


def _validate_horizons(parent: MidiClip, child: MidiClip) -> None:
    if _horizons(parent) != _horizons(child):
        raise WorkbenchClipCorrectionError(
            "Note-end correction changed the Clip beat, export or source horizon"
        )


def _diff(
    parent: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    mode, bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    return {
        "kind": _CORRECTION_KIND,
        "changed_note_count": len(changes),
        "timing_mode": mode,
        "export_bpm": bpm,
        "changes": [
            _public_change(parent, row, mode=mode, bpm=bpm) for row in changes
        ],
    }


def _public_change(
    parent: MidiClip,
    row: Mapping[str, Any],
    *,
    mode: str,
    bpm: float,
) -> dict[str, Any]:
    before = dict(row["before"])
    after = dict(row["after"])
    start_tick = int(row["before_start_tick"])
    before_end = int(row["before_end_tick"])
    after_end = int(row["after_end_tick"])
    return {
        "note_ref": str(row["note_ref"]),
        "channel": parent.instrument.channel,
        "pitch": before["pitch"],
        "start_tick": start_tick,
        "before_end_tick": before_end,
        "after_end_tick": after_end,
        "before_duration_ticks": before_end - start_tick,
        "after_duration_ticks": after_end - start_tick,
        "tick_delta": after_end - before_end,
        "milliseconds_delta": _export_milliseconds_delta(
            parent,
            before_end_tick=before_end,
            after_end_tick=after_end,
            timing_mode=mode,
            export_bpm=bpm,
        ),
        "start_beat": before["start_beat"],
        "before_duration_beats": before["duration_beats"],
        "after_duration_beats": after["duration_beats"],
        "source_start_seconds": before["source_start_seconds"],
        "before_source_end_seconds": before["source_end_seconds"],
        "after_source_end_seconds": after["source_end_seconds"],
    }


def _export_milliseconds_delta(
    clip: MidiClip,
    *,
    before_end_tick: int,
    after_end_tick: int,
    timing_mode: str,
    export_bpm: float,
) -> float:
    if timing_mode == "stem_locked":
        seconds = (
            (after_end_tick - before_end_tick)
            * 60.0
            / (export_bpm * _TICKS_PER_BEAT)
        )
    else:
        seconds = clip.tempo_map.musical_seconds_at(
            after_end_tick / _TICKS_PER_BEAT
        ) - clip.tempo_map.musical_seconds_at(
            before_end_tick / _TICKS_PER_BEAT
        )
    return seconds * 1000.0


def _public_articulation(value: Any) -> str | None:
    if value is None:
        return None
    return _safe_text(
        value,
        fallback="private articulation",
        maximum=120,
    )[0]


def _unchanged_projection() -> dict[str, bool]:
    return {
        "note_count": True,
        "unaffected_note_payloads": True,
        "note_pitches": True,
        "note_onsets": True,
        "source_start_seconds": True,
        "velocity": True,
        "release_velocity": True,
        "microtiming": True,
        "articulation": True,
        "clip_horizons": True,
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
        "Only the named existing note ends and durations change; their onsets, pitches and expression remain exact.",
        "Beat-duration and source-end coordinates are reconciled under the retained timing contract and must round-trip to the requested 480-TPQ Note Off ticks.",
        "Targets that cross a later same-pitch onset or change the global beat, export or source horizon are rejected.",
        "The child is not selected, placed, auditioned or added to a GarageBand Pack automatically.",
    ]


def _effects(**changes: bool) -> dict[str, bool]:
    effects = {key: False for key in sorted(_EFFECT_KEYS)}
    for key, value in changes.items():
        if key not in _EFFECT_KEYS or not isinstance(value, bool):
            raise ValueError("Unknown Clip note-end correction effect")
        effects[key] = value
    return effects


__all__ = [
    "CLIP_NOTE_END_PREVIEW_SCHEMA",
    "CLIP_NOTE_END_RESULT_SCHEMA",
    "CLIP_NOTE_END_SUMMARY_SCHEMA",
    "CLIP_NOTE_END_WINDOW_SCHEMA",
    "WorkbenchClipDurationCorrectionService",
]
