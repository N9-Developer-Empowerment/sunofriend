"""Bounded, immutable Clip pitch correction for the local Workbench.

This Phase 6 boundary is deliberately smaller than a general piano roll.  A
window is a read-only projection of one exact Clip at the 480-TPQ export grid;
a preview may change only the pitches of explicitly referenced notes; and a
create action may append only the exact projected child.  Timing, expression,
key, chords, instrument and provenance remain byte-semantically unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .chords import MAJOR_SCALE, MINOR_SCALE, parse_chord_name
from .clip import (
    ChordEvent,
    ClipNote,
    MidiClip,
    TempoPoint,
    TransformRecipe,
    resolve_export_timing,
)
from .library import ClipLibrary, ClipSummary
from .workbench_clips import (
    WorkbenchClipService,
    _LibraryState,
    _safe_identifier,
    _safe_text,
)
from .workbench_transform import (
    _child_identity,
    _clip_identity,
    _is_drum_family,
)


CLIP_CORRECTION_CAPABILITY_SCHEMA = (
    "sunofriend.workbench-clip-correction-capability.v2"
)
CLIP_CORRECTION_WINDOW_SCHEMA = "sunofriend.workbench-clip-correction-window.v1"
CLIP_CORRECTION_PREVIEW_SCHEMA = "sunofriend.workbench-clip-correction-preview.v1"
CLIP_CORRECTION_RESULT_SCHEMA = "sunofriend.workbench-clip-correction-result.v1"
CLIP_CORRECTION_SUMMARY_SCHEMA = "sunofriend.workbench-clip-correction-summary.v1"
_NOTE_REF_SCHEMA = "sunofriend.workbench-clip-note-ref.v1"
_INTENT_SCHEMA = "sunofriend.workbench-clip-correction-intent.v1"
_RECIPE_CONTRACT_VERSION = 1
_TICKS_PER_BEAT = 480
_MAX_WINDOW_TICKS = 32 * _TICKS_PER_BEAT
_MAX_WINDOW_SECONDS = 15.0
_MAX_VISIBLE_NOTES = 512
_MAX_EDITABLE_NOTES = 256
_MAX_WINDOW_CHORDS = 64
_MAX_CHANGES = 64
_MAX_PITCH_DELTA = 24
_MAX_NOTES = 20_000
_MAX_CHORDS = 20_000
_MAX_DURATION_SECONDS = 20.0 * 60.0
_MAX_ABSOLUTE_TICK = 0x0FFFFFFF
_MAX_TEMPO_MICROSECONDS = 0xFFFFFF
_MAX_META_PAYLOAD_BYTES = 0x0FFFFFFF
_WINDOW_REQUEST_KEYS = {
    "parent_clip_id",
    "parent_object_sha256",
    "library_state_sha256",
    "window",
}
_PREVIEW_REQUEST_KEYS = _WINDOW_REQUEST_KEYS | {"window_sha256", "correction"}
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
_EFFECT_KEYS = {
    "library_mutated",
    "child_clip_created",
    "source_clip_mutated",
    "correction_applied",
    "note_pitch_changed",
    "note_timing_changed",
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


class WorkbenchClipCorrectionError(ValueError):
    """Base error for a rejected explicit Clip correction request."""


class WorkbenchClipCorrectionConflictError(WorkbenchClipCorrectionError):
    """The exact parent, object, library, window or projection pin is stale."""


class WorkbenchClipCorrectionNotFoundError(WorkbenchClipCorrectionError):
    """The requested Clip is absent from the verified library."""


def _request_correction_kind(request: Mapping[str, Any]) -> Any:
    """Return only the explicit nested discriminator used for route dispatch."""

    if not isinstance(request, Mapping):
        return None
    correction = request.get("correction")
    if not isinstance(correction, Mapping):
        return None
    return correction.get("kind")


class WorkbenchClipCorrectionService:
    """Dispatch one bounded immutable note correction at a time."""

    def __init__(
        self,
        *,
        clip_service: WorkbenchClipService,
        writer: ClipLibrary,
    ) -> None:
        self._clip_service = clip_service
        self._writer = writer
        self._velocity_corrections: Any | None = None
        self._deletion_corrections: Any | None = None

    @classmethod
    def open(
        cls,
        *,
        clip_service: WorkbenchClipService,
        library_root: str | Path,
    ) -> "WorkbenchClipCorrectionService":
        """Open only the exact existing library already verified for browsing."""

        if not isinstance(clip_service, WorkbenchClipService):
            raise TypeError("clip_service must be a WorkbenchClipService")
        requested = Path(os.path.abspath(Path(library_root).expanduser()))
        if requested.is_symlink():
            raise ValueError("Clip correction library root must not be a symlink")
        if requested != clip_service._transform_library_identity():
            raise ValueError("Clip correction library must match the verified Clip library")
        writer = ClipLibrary.open_existing_writer(requested)
        if writer.root != requested.resolve():
            raise ValueError("Clip correction library identity changed while opening")
        return cls(clip_service=clip_service, writer=writer)

    def capability(self) -> dict[str, Any]:
        """Describe the separately gated bounded note-correction boundary."""

        state = self._snapshot()
        append_available = self._clip_service._transform_has_append_capacity(state)
        return {
            "schema": CLIP_CORRECTION_CAPABILITY_SCHEMA,
            "enabled": True,
            "scope": "bounded-note-correction-immutable-child",
            "actions": {
                "window": True,
                "preview": append_available,
                "create": append_available,
            },
            "corrections": {
                "pitch_patch": {
                    "enabled": True,
                    "drum_family": False,
                },
                "attack_velocity_patch": {
                    "enabled": True,
                    "drum_family": True,
                },
                "note_delete_patch": {
                    "enabled": True,
                    "drum_family": True,
                },
                "timing": False,
                "add_delete": False,
            },
            "library": {
                "state_sha256": state.state_sha256,
                "clip_count": len(state.summaries),
            },
            "limits": {
                "ticks_per_beat": _TICKS_PER_BEAT,
                "maximum_window_ticks": _MAX_WINDOW_TICKS,
                "maximum_window_seconds": _MAX_WINDOW_SECONDS,
                "maximum_visible_notes": _MAX_VISIBLE_NOTES,
                "maximum_editable_notes": _MAX_EDITABLE_NOTES,
                "maximum_window_chords": _MAX_WINDOW_CHORDS,
                "maximum_changes": _MAX_CHANGES,
                "maximum_pitch_delta_semitones": _MAX_PITCH_DELTA,
                "minimum_attack_velocity": 1,
                "maximum_attack_velocity": 127,
                "maximum_clip_notes": _MAX_NOTES,
                "maximum_clip_chords": _MAX_CHORDS,
                "maximum_clip_duration_seconds": _MAX_DURATION_SECONDS,
                "maximum_absolute_tick": _MAX_ABSOLUTE_TICK,
                "maximum_tempo_microseconds_per_quarter": (
                    _MAX_TEMPO_MICROSECONDS
                ),
                "maximum_meta_payload_bytes": _MAX_META_PAYLOAD_BYTES,
            },
            "effects": _effects(),
        }

    def window(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Return one deterministic, path-free note/chord editing window."""

        if isinstance(request, Mapping) and "correction_kind" in request:
            kind = request.get("correction_kind")
            if kind == "attack_velocity_patch":
                return self._velocity_service().window(request)
            if kind == "note_delete_patch":
                return self._deletion_service().window(request)
            raise WorkbenchClipCorrectionError(
                "unknown Clip correction window kind; fields do not match the exact contract"
            )

        parsed = _parse_window_request(request)
        state = self._snapshot()
        _require_library_pin(state, parsed["library_state_sha256"])
        parent, summary = _parent_from_state(state, parsed)
        return _window_projection(
            parent=parent,
            summary=summary,
            request=parsed,
        )

    def preview(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Return a zero-write pitch-patch projection for one exact window."""

        kind = _request_correction_kind(request)
        if kind == "attack_velocity_patch":
            return self._velocity_service().preview(request)
        if kind == "note_delete_patch":
            return self._deletion_service().preview(request)
        if kind not in {None, "pitch_patch"}:
            raise WorkbenchClipCorrectionError("unknown Clip correction kind")

        parsed = _parse_preview_request(request, create=False)
        state = self._snapshot()
        _require_library_pin(state, parsed["library_state_sha256"])
        if not self._clip_service._transform_has_append_capacity(state):
            raise WorkbenchClipCorrectionError(
                "Clip library has reached the 10000 Clip correction limit"
            )
        parent, summary = _parent_from_state(state, parsed)
        window = _window_projection(parent=parent, summary=summary, request=parsed)
        if parsed["window_sha256"] != window["window_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip correction window changed; load the window again"
            )
        return _project(
            parent=parent,
            summary=summary,
            request=parsed,
            window=window,
        )

    def create(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Append the exact projected child or return an idempotent replay."""

        kind = _request_correction_kind(request)
        if kind == "attack_velocity_patch":
            return self._velocity_service().create(request)
        if kind == "note_delete_patch":
            return self._deletion_service().create(request)
        if kind not in {None, "pitch_patch"}:
            raise WorkbenchClipCorrectionError("unknown Clip correction kind")

        parsed = _parse_preview_request(request, create=True)
        try:
            state = self._clip_service._transform_create_snapshot(
                expected_state_sha256=parsed["library_state_sha256"],
            )
        except RuntimeError as exc:
            raise WorkbenchClipCorrectionConflictError(
                "Verified Clip library changed; load a fresh correction window"
            ) from exc
        parent, summary = _parent_from_state(state, parsed)
        window = _window_projection(parent=parent, summary=summary, request=parsed)
        if parsed["window_sha256"] != window["window_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip correction window changed; load the window again"
            )
        projection = _project(
            parent=parent,
            summary=summary,
            request=parsed,
            window=window,
        )
        if parsed["projection_sha256"] != projection["projection_sha256"]:
            raise WorkbenchClipCorrectionConflictError(
                "Clip correction projection changed; review the correction again"
            )
        child = _corrected_child(
            parent,
            request=parsed,
            intent_sha256=projection["intent_sha256"],
            resolved_changes=_resolve_changes(parent, parsed, window),
        )
        child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
        if child_hash != projection["child"]["object_sha256"]:
            raise RuntimeError("Clip correction child projection is not deterministic")
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
                    "Clip library changed; load a fresh correction window"
                ) from exc
            raise

        replayed = append.replayed
        return {
            "schema": CLIP_CORRECTION_RESULT_SCHEMA,
            "status": "replayed" if replayed else "created",
            "operation": "clip-correction-create",
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
                note_pitch_changed=not replayed,
            ),
        }

    def correction_summary(self, clip_id: str) -> dict[str, Any] | None:
        """Re-derive the recognized correction diff after a restart."""

        requested = _safe_clip_identifier(clip_id, "clip_id")
        state = self._snapshot()
        try:
            child = state.clips[requested]
        except KeyError as exc:
            raise WorkbenchClipCorrectionNotFoundError("Unknown corrected Clip") from exc
        operation = (
            None
            if child.transform_recipe is None
            else child.transform_recipe.operation
        )
        if operation == "correct_note_attack_velocities":
            return self._velocity_service().correction_summary_from_state(
                requested,
                state,
            )
        if operation == "delete_clip_notes":
            return self._deletion_service().correction_summary_from_state(
                requested,
                state,
            )
        if operation != "correct_note_pitches":
            return None
        if child.parent_clip_id is None or child.parent_clip_id not in state.clips:
            raise WorkbenchClipCorrectionError(
                "Recognized correction child has no verified parent"
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
            },
        )
        if retained_window["window_sha256"] != parameters["window_sha256"]:
            raise WorkbenchClipCorrectionError(
                "Correction recipe window evidence does not match its parent"
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

    def _velocity_service(self) -> Any:
        """Load the separate velocity policy only when its request is explicit."""

        if self._velocity_corrections is None:
            from .workbench_velocity import WorkbenchClipVelocityCorrectionService

            self._velocity_corrections = WorkbenchClipVelocityCorrectionService(
                clip_service=self._clip_service,
                writer=self._writer,
            )
        return self._velocity_corrections

    def _deletion_service(self) -> Any:
        """Load the separate deletion policy only for its explicit requests."""

        if self._deletion_corrections is None:
            from .workbench_deletion import WorkbenchClipDeletionCorrectionService

            self._deletion_corrections = WorkbenchClipDeletionCorrectionService(
                clip_service=self._clip_service,
                writer=self._writer,
            )
        return self._deletion_corrections


def _derive_correction_summary(parent: MidiClip, child: MidiClip) -> dict[str, Any]:
    """Validate the retained recipe fields that depend only on parent and child.

    The service method additionally reconstructs the historical window with
    its verified catalog summary before exposing this path-free document.
    Keeping this helper private prevents callers from mistaking structural
    parent/child verification for that complete restart audit.
    """

    if child.transform_recipe is None or child.transform_recipe.operation != (
        "correct_note_pitches"
    ):
        raise WorkbenchClipCorrectionError(
            "Clip does not contain a recognized pitch-correction recipe"
        )
    if child.parent_clip_id != parent.clip_id or child.revision != parent.revision + 1:
        raise WorkbenchClipCorrectionError("Correction lineage does not match its parent")
    parameters = child.transform_recipe.parameters_dict
    if set(parameters) != _RECIPE_PARAMETER_KEYS:
        raise WorkbenchClipCorrectionError("Correction recipe fields are invalid")
    if parameters.get("contract_version") != _RECIPE_CONTRACT_VERSION:
        raise WorkbenchClipCorrectionError("Correction recipe version is unsupported")
    if parameters.get("ticks_per_beat") != _TICKS_PER_BEAT:
        raise WorkbenchClipCorrectionError("Correction recipe TPQ is invalid")
    parent_hash = hashlib.sha256(parent.canonical_bytes()).hexdigest()
    if parameters.get("parent_object_sha256") != parent_hash:
        raise WorkbenchClipCorrectionError("Correction recipe parent object does not match")
    library_state_sha256 = _sha256_value(
        parameters.get("library_state_sha256"), "library_state_sha256"
    )
    window_sha256 = _sha256_value(
        parameters.get("window_sha256"), "window_sha256"
    )
    window = _parse_window(parameters.get("window"))
    _bounded_window_content(parent, parent_hash, window)
    recipe_changes = _parse_recipe_changes(
        parameters.get("changes"), parent, parent_hash, window
    )
    correction = _parse_correction(parameters.get("correction"))
    expected_correction = _correction_from_recipe_changes(recipe_changes)
    if correction != expected_correction:
        raise WorkbenchClipCorrectionError(
            "Correction recipe patch does not match its retained edit diff"
        )
    intent_sha256 = _sha256_value(parameters.get("intent_sha256"), "intent_sha256")
    expected_intent_sha256 = _document_hash(
        _intent_document(
            parent_clip_id=parent.clip_id,
            parent_object_sha256=parent_hash,
            library_state_sha256=library_state_sha256,
            window=window,
            window_sha256=window_sha256,
            correction=correction,
        )
    )
    if intent_sha256 != expected_intent_sha256:
        raise WorkbenchClipCorrectionError(
            "Correction recipe intent digest does not match its retained evidence"
        )
    if child.clip_id != f"sf-correction-{intent_sha256}":
        raise WorkbenchClipCorrectionError("Correction child identity is invalid")
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
            "Correction child does not match the exact retained edit diff"
        )
    _validate_metadata_unchanged(parent, child)
    _reject_new_export_collisions(parent, child, recipe_changes)
    public_changes = [
        _public_change(parent, change) for change in recipe_changes
    ]
    return {
        "schema": CLIP_CORRECTION_SUMMARY_SCHEMA,
        "operation": "correct_note_pitches",
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


def _parse_window_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping) or set(request) != _WINDOW_REQUEST_KEYS:
        raise WorkbenchClipCorrectionError(
            "Clip correction window fields do not match the exact contract"
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
    }


def _parse_preview_request(
    request: Mapping[str, Any],
    *,
    create: bool,
) -> dict[str, Any]:
    expected = _CREATE_REQUEST_KEYS if create else _PREVIEW_REQUEST_KEYS
    if not isinstance(request, Mapping) or set(request) != expected:
        raise WorkbenchClipCorrectionError(
            "Clip correction request fields do not match the exact contract"
        )
    if create and request.get("action") != "create":
        raise WorkbenchClipCorrectionError("Clip correction action must be 'create'")
    parsed = {
        **_parse_window_request(
            {key: request[key] for key in _WINDOW_REQUEST_KEYS}
        ),
        "window_sha256": _sha256_value(
            request.get("window_sha256"), "window_sha256"
        ),
        "correction": _parse_correction(request.get("correction")),
    }
    if create:
        parsed["action"] = "create"
        parsed["projection_sha256"] = _sha256_value(
            request.get("projection_sha256"), "projection_sha256"
        )
    return parsed


def _parse_window(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {"start_tick", "end_tick"}:
        raise WorkbenchClipCorrectionError(
            "window requires exactly integer start_tick and end_tick"
        )
    start = _exact_int(value.get("start_tick"), "start_tick")
    end = _exact_int(value.get("end_tick"), "end_tick")
    if start < 0 or end <= start:
        raise WorkbenchClipCorrectionError(
            "window ticks must satisfy 0 <= start_tick < end_tick"
        )
    if end - start > _MAX_WINDOW_TICKS:
        raise WorkbenchClipCorrectionError("correction window exceeds 32 beats")
    if end > _MAX_ABSOLUTE_TICK:
        raise WorkbenchClipCorrectionError(
            "correction window exceeds the four-byte SMF VLQ tick limit"
        )
    return {"start_tick": start, "end_tick": end}


def _parse_correction(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"kind", "changes"}:
        raise WorkbenchClipCorrectionError(
            "correction requires exactly kind and changes"
        )
    if value.get("kind") != "pitch_patch":
        raise WorkbenchClipCorrectionError("correction kind must be 'pitch_patch'")
    rows = value.get("changes")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_CHANGES:
        raise WorkbenchClipCorrectionError("pitch patch requires 1 to 64 changes")
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"note_ref", "target_pitch"}:
            raise WorkbenchClipCorrectionError(
                "each pitch change requires exactly note_ref and target_pitch"
            )
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        target = _exact_int(row.get("target_pitch"), "target_pitch")
        if not 0 <= target <= 127:
            raise WorkbenchClipCorrectionError(
                "target_pitch must be an integer from 0 to 127"
            )
        if note_ref in seen:
            raise WorkbenchClipCorrectionError("pitch changes must use unique note refs")
        seen.add(note_ref)
        changes.append({"note_ref": note_ref, "target_pitch": target})
    changes.sort(key=lambda row: row["note_ref"])
    return {"kind": "pitch_patch", "changes": changes}


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


def _correction_from_recipe_changes(
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [
        {
            "note_ref": str(row["note_ref"]),
            "target_pitch": int(row["after"]["pitch"]),
        }
        for row in changes
    ]
    rows.sort(key=lambda row: row["note_ref"])
    return {"kind": "pitch_patch", "changes": rows}


def _window_projection(
    *,
    parent: MidiClip,
    summary: ClipSummary,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    window = dict(request["window"])
    parent_hash = str(request["parent_object_sha256"])
    content = _bounded_window_content(parent, parent_hash, window)
    duration_seconds = float(content["duration_seconds"])
    notes = content["notes"]
    editable_count = int(content["editable_note_count"])
    chords = content["chords"]
    timing_mode, timing_bpm = resolve_export_timing(
        parent, timing_mode="auto", garageband_bpm=None
    )
    document: dict[str, Any] = {
        "schema": CLIP_CORRECTION_WINDOW_SCHEMA,
        "operation": "clip-correction-window",
        "library": {"state_sha256": request["library_state_sha256"]},
        "parent": _clip_identity(summary=summary, clip=parent),
        "window": {
            **window,
            "ticks_per_beat": _TICKS_PER_BEAT,
            "duration_seconds": duration_seconds,
            "origin": "recorded-zero",
        },
        "timing": {
            "resolved_mode": timing_mode,
            "export_bpm": timing_bpm,
        },
        "notes": notes,
        "visible_note_count": len(notes),
        "editable_note_count": editable_count,
        "chords": chords,
        "policies": {
            "editable_membership": "note-on tick in half-open window",
            "context_membership": "export interval intersects window",
            "correction_scope": "pitch only",
        },
        "effects": _effects(),
    }
    document["window_sha256"] = _document_hash(document)
    return document


def _project(
    *,
    parent: MidiClip,
    summary: ClipSummary,
    request: Mapping[str, Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    parent_hash = str(request["parent_object_sha256"])
    resolved = _resolve_changes(parent, request, window)
    intent = _intent_document(
        parent_clip_id=str(request["parent_clip_id"]),
        parent_object_sha256=parent_hash,
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
    _validate_metadata_unchanged(parent, child)
    _reject_new_export_collisions(parent, child, resolved)
    child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
    diff = _diff(parent, child, resolved)
    document: dict[str, Any] = {
        "schema": CLIP_CORRECTION_PREVIEW_SCHEMA,
        "status": "previewed",
        "operation": "clip-correction-preview",
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
        "warnings": _warnings(parent, diff),
        "effects": _effects(),
    }
    document["projection_sha256"] = _document_hash(document)
    return document


def _resolve_changes(
    parent: MidiClip,
    request: Mapping[str, Any],
    window: Mapping[str, Any],
) -> list[dict[str, Any]]:
    parent_hash = str(request["parent_object_sha256"])
    editable = {
        row["note_ref"]: row
        for row in window["notes"]
        if row["editable"] is True
    }
    ref_to_index = {
        _note_ref(parent_hash, index, note): index
        for index, note in enumerate(parent.notes)
    }
    resolved: list[dict[str, Any]] = []
    for row in request["correction"]["changes"]:
        note_ref = row["note_ref"]
        if note_ref not in editable or note_ref not in ref_to_index:
            raise WorkbenchClipCorrectionError(
                "pitch correction references a note outside the editable window"
            )
        index = ref_to_index[note_ref]
        before = parent.notes[index]
        target = int(row["target_pitch"])
        delta = target - before.pitch
        if delta == 0:
            raise WorkbenchClipCorrectionError("pitch correction contains a no-op")
        if abs(delta) > _MAX_PITCH_DELTA:
            raise WorkbenchClipCorrectionError(
                "pitch correction is limited to 24 semitones per note"
            )
        after = replace(before, pitch=target)
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
        int(row["parent_note_index"]): int(row["after"]["pitch"])
        for row in recipe_changes
    }
    notes = tuple(
        replace(note, pitch=changes_by_index.get(index, note.pitch))
        for index, note in enumerate(parent.notes)
    )
    recipe = TransformRecipe.create(
        "correct_note_pitches",
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


def _parse_recipe_changes(
    value: Any,
    parent: MidiClip,
    parent_hash: str,
    window: Mapping[str, int],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_CHANGES:
        raise WorkbenchClipCorrectionError("Correction recipe changes are invalid")
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
            raise WorkbenchClipCorrectionError("Correction recipe change is invalid")
        note_ref = _sha256_value(row.get("note_ref"), "note_ref")
        index = _exact_int(row.get("parent_note_index"), "parent_note_index")
        if index < 0 or index >= len(parent.notes):
            raise WorkbenchClipCorrectionError("Correction recipe note index is invalid")
        if note_ref in seen_refs or index in seen_indices:
            raise WorkbenchClipCorrectionError("Correction recipe changes are duplicated")
        seen_refs.add(note_ref)
        seen_indices.add(index)
        before = _note_mapping(row.get("before"), "before")
        after = _note_mapping(row.get("after"), "after")
        parent_note = parent.notes[index]
        if before != _note_payload(parent_note):
            raise WorkbenchClipCorrectionError(
                "Correction recipe before-note does not match its parent"
            )
        if note_ref != _note_ref(parent_hash, index, parent_note):
            raise WorkbenchClipCorrectionError("Correction recipe note ref is invalid")
        before_tick, _ = _note_ticks(parent, parent_note)
        if not window["start_tick"] <= before_tick < window["end_tick"]:
            raise WorkbenchClipCorrectionError(
                "Correction recipe note is outside its editable window"
            )
        changed_fields = {
            key for key in before if before.get(key) != after.get(key)
        }
        if changed_fields != {"pitch"}:
            raise WorkbenchClipCorrectionError(
                "Correction recipe may change pitch only"
            )
        target = after["pitch"]
        if not isinstance(target, int) or isinstance(target, bool) or not 0 <= target <= 127:
            raise WorkbenchClipCorrectionError("Correction recipe pitch is invalid")
        if not 1 <= abs(target - parent_note.pitch) <= _MAX_PITCH_DELTA:
            raise WorkbenchClipCorrectionError("Correction recipe pitch delta is invalid")
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


def _note_mapping(value: Any, label: str) -> dict[str, Any]:
    keys = set(_note_payload(_example_note()))
    if not isinstance(value, Mapping) or set(value) != keys:
        raise WorkbenchClipCorrectionError(f"Correction recipe {label}-note is invalid")
    try:
        note = ClipNote(**dict(value))
    except (TypeError, ValueError) as exc:
        raise WorkbenchClipCorrectionError(
            f"Correction recipe {label}-note is invalid"
        ) from exc
    return _note_payload(note)


def _example_note() -> ClipNote:
    return ClipNote(0.0, 1.0, 60, 90, 0.0, 0.5)


def _bounded_window_content(
    parent: MidiClip,
    parent_hash: str,
    window: Mapping[str, int],
) -> dict[str, Any]:
    _validate_parent_bounds(parent)
    if _is_drum_family(parent):
        raise WorkbenchClipCorrectionError(
            "Drum-family Clips cannot use pitched note correction"
        )
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

    notes: list[dict[str, Any]] = []
    editable_count = 0
    for index, note in enumerate(parent.notes):
        start_tick, end_tick = _note_ticks(parent, note)
        if start_tick >= window["end_tick"] or end_tick <= window["start_tick"]:
            continue
        editable = window["start_tick"] <= start_tick < window["end_tick"]
        editable_count += int(editable)
        notes.append(
            {
                "note_ref": _note_ref(parent_hash, index, note),
                "editable": editable,
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
        "horizon_tick": horizon_tick,
        "notes": notes,
        "editable_note_count": editable_count,
        "chords": chords,
    }


def _parent_from_state(
    state: _LibraryState,
    request: Mapping[str, Any],
) -> tuple[MidiClip, ClipSummary]:
    parent_id = str(request["parent_clip_id"])
    try:
        parent = state.clips[parent_id]
        summary = next(row for row in state.summaries if row.clip_id == parent_id)
    except (KeyError, StopIteration) as exc:
        raise WorkbenchClipCorrectionNotFoundError("Unknown parent Clip") from exc
    if summary.object_hash != request["parent_object_sha256"]:
        raise WorkbenchClipCorrectionConflictError(
            "Parent Clip object changed; load a fresh correction window"
        )
    _validate_parent_bounds(parent)
    return parent, summary


def _validate_parent_bounds(clip: MidiClip) -> None:
    if len(clip.notes) > _MAX_NOTES:
        raise WorkbenchClipCorrectionError("Parent Clip exceeds the 20000 note limit")
    if len(clip.chords) > _MAX_CHORDS:
        raise WorkbenchClipCorrectionError("Parent Clip exceeds the 20000 chord limit")
    _validate_exportable_tempo(clip)
    _validate_exportable_metadata(clip)
    _clip_horizon_tick(clip)
    if _maximum_duration_seconds(clip) > _MAX_DURATION_SECONDS + 1e-9:
        raise WorkbenchClipCorrectionError("Parent Clip exceeds the 20 minute limit")


def _clip_horizon_tick(clip: MidiClip) -> int:
    note_ends = (_note_ticks(clip, note)[1] for note in clip.notes)
    chord_ends = (_chord_ticks(clip, chord)[1] for chord in clip.chords)
    mode, _bpm = resolve_export_timing(
        clip, timing_mode="auto", garageband_bpm=None
    )
    tempo_ticks = (
        (0,)
        if mode == "stem_locked"
        else tuple(_tempo_tick(point) for point in clip.tempo_map.tempo_points)
    )
    horizon = max(0, *note_ends, *chord_ends, *tempo_ticks)
    if horizon > _MAX_ABSOLUTE_TICK:
        raise WorkbenchClipCorrectionError(
            "Parent Clip exceeds the four-byte SMF VLQ tick limit"
        )
    return horizon


def _validate_exportable_tempo(clip: MidiClip) -> None:
    for point in clip.tempo_map.tempo_points:
        _tempo_tick(point)
        _tempo_microseconds(point.bpm)
    _mode, resolved_bpm = resolve_export_timing(
        clip, timing_mode="auto", garageband_bpm=None
    )
    _tempo_microseconds(resolved_bpm)


def _tempo_tick(point: TempoPoint) -> int:
    try:
        tick = max(0, int(round(point.beat * _TICKS_PER_BEAT)))
    except (OverflowError, ValueError) as exc:
        raise WorkbenchClipCorrectionError(
            "Parent Clip tempo timing exceeds the four-byte SMF VLQ tick limit"
        ) from exc
    if tick > _MAX_ABSOLUTE_TICK:
        raise WorkbenchClipCorrectionError(
            "Parent Clip tempo timing exceeds the four-byte SMF VLQ tick limit"
        )
    return tick


def _tempo_microseconds(bpm: float) -> int:
    try:
        microseconds = int(round(60_000_000.0 / bpm))
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        raise WorkbenchClipCorrectionError(
            "Parent Clip tempo cannot be encoded in the three-byte SMF tempo field"
        ) from exc
    if not 1 <= microseconds <= _MAX_TEMPO_MICROSECONDS:
        raise WorkbenchClipCorrectionError(
            "Parent Clip tempo cannot be encoded in the three-byte SMF tempo field"
        )
    return microseconds


def _validate_exportable_metadata(clip: MidiClip) -> None:
    denominator_power = clip.time_signature.denominator.bit_length() - 1
    numerator = clip.time_signature.numerator
    if (
        isinstance(numerator, bool)
        or not isinstance(numerator, int)
        or not 1 <= numerator <= 0xFF
        or denominator_power > 0xFF
    ):
        raise WorkbenchClipCorrectionError(
            "Parent Clip time signature cannot be encoded in the SMF byte fields"
        )
    _validate_meta_text(clip.title, "track title")
    for chord in clip.chords:
        _validate_meta_text(chord.symbol, "chord symbol")


def _validate_meta_text(value: str, label: str) -> None:
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise WorkbenchClipCorrectionError(
            f"Parent Clip {label} is not valid UTF-8 text"
        ) from exc
    if size > _MAX_META_PAYLOAD_BYTES:
        raise WorkbenchClipCorrectionError(
            f"Parent Clip {label} exceeds the four-byte SMF VLQ payload limit"
        )


def _maximum_duration_seconds(clip: MidiClip) -> float:
    mode, bpm = resolve_export_timing(
        clip, timing_mode="auto", garageband_bpm=None
    )
    export_end = _ticks_seconds(clip, 0, _clip_horizon_tick(clip), mode, bpm)
    source_ends = [note.source_end_seconds for note in clip.notes]
    source_ends.extend(
        chord.source_end_seconds
        if chord.source_end_seconds is not None
        else clip.tempo_map.source_seconds_at(chord.end_beat)
        for chord in clip.chords
    )
    return max(export_end, max([0.0, *source_ends]))


def _require_library_pin(state: _LibraryState, expected: str) -> None:
    if state.state_sha256 != expected:
        raise WorkbenchClipCorrectionConflictError(
            "Clip library state changed; load a fresh correction window"
        )


def _note_ref(parent_object_sha256: str, index: int, note: ClipNote) -> str:
    return _document_hash(
        {
            "schema": _NOTE_REF_SCHEMA,
            "parent_object_sha256": parent_object_sha256,
            "canonical_note_index": index,
            "note": _note_payload(note),
        }
    )


def _note_payload(note: ClipNote) -> dict[str, Any]:
    return {
        "start_beat": note.start_beat,
        "duration_beats": note.duration_beats,
        "pitch": note.pitch,
        "velocity": note.velocity,
        "source_start_seconds": note.source_start_seconds,
        "source_end_seconds": note.source_end_seconds,
        "microtiming_seconds": note.microtiming_seconds,
        "end_microtiming_seconds": note.end_microtiming_seconds,
        "release_velocity": note.release_velocity,
        "articulation": note.articulation,
    }


def _note_ticks(clip: MidiClip, note: ClipNote) -> tuple[int, int]:
    mode, bpm = resolve_export_timing(clip, timing_mode="auto", garageband_bpm=None)
    try:
        if mode == "stem_locked":
            start = int(
                round(note.source_start_seconds * bpm * _TICKS_PER_BEAT / 60.0)
            )
            end = int(
                round(note.source_end_seconds * bpm * _TICKS_PER_BEAT / 60.0)
            )
        else:
            start_beat = note.start_beat + clip.tempo_map.seconds_delta_to_beats(
                note.microtiming_seconds, note.start_beat
            )
            grid_end = note.end_beat
            end_beat = grid_end + clip.tempo_map.seconds_delta_to_beats(
                note.end_microtiming_seconds, grid_end
            )
            start = int(round(start_beat * _TICKS_PER_BEAT))
            end = int(round(end_beat * _TICKS_PER_BEAT))
    except (OverflowError, ValueError) as exc:
        raise WorkbenchClipCorrectionError(
            "Parent Clip note timing exceeds the four-byte SMF VLQ tick limit"
        ) from exc
    if start < 0:
        raise WorkbenchClipCorrectionError(
            "Parent Clip contains a note before the deterministic MIDI origin"
        )
    end = max(start + 1, end)
    if end > _MAX_ABSOLUTE_TICK:
        raise WorkbenchClipCorrectionError(
            "Parent Clip note timing exceeds the four-byte SMF VLQ tick limit"
        )
    return start, end


def _chord_ticks(clip: MidiClip, chord: ChordEvent) -> tuple[int, int]:
    mode, bpm = resolve_export_timing(clip, timing_mode="auto", garageband_bpm=None)
    try:
        if mode == "stem_locked":
            source_start = (
                chord.source_start_seconds
                if chord.source_start_seconds is not None
                else clip.tempo_map.source_seconds_at(chord.start_beat)
            )
            source_end = (
                chord.source_end_seconds
                if chord.source_end_seconds is not None
                else clip.tempo_map.source_seconds_at(chord.end_beat)
            )
            start = int(round(source_start * bpm * _TICKS_PER_BEAT / 60.0))
            end = int(round(source_end * bpm * _TICKS_PER_BEAT / 60.0))
        else:
            start = max(0, int(round(chord.start_beat * _TICKS_PER_BEAT)))
            end = max(0, int(round(chord.end_beat * _TICKS_PER_BEAT)))
    except (OverflowError, ValueError) as exc:
        raise WorkbenchClipCorrectionError(
            "Parent Clip chord timing exceeds the four-byte SMF VLQ tick limit"
        ) from exc
    if start < 0:
        raise WorkbenchClipCorrectionError(
            "Parent Clip contains a chord before the deterministic MIDI origin"
        )
    end = max(start + 1, end)
    if end > _MAX_ABSOLUTE_TICK:
        raise WorkbenchClipCorrectionError(
            "Parent Clip chord timing exceeds the four-byte SMF VLQ tick limit"
        )
    return start, end


def _window_seconds(clip: MidiClip, window: Mapping[str, int]) -> float:
    mode, bpm = resolve_export_timing(clip, timing_mode="auto", garageband_bpm=None)
    return _ticks_seconds(
        clip,
        int(window["start_tick"]),
        int(window["end_tick"]),
        mode,
        bpm,
    )


def _ticks_seconds(
    clip: MidiClip,
    start_tick: int,
    end_tick: int,
    mode: str,
    bpm: float,
) -> float:
    if mode == "stem_locked":
        return (end_tick - start_tick) * 60.0 / (bpm * _TICKS_PER_BEAT)
    start_beat = start_tick / _TICKS_PER_BEAT
    end_beat = end_tick / _TICKS_PER_BEAT
    return max(
        0.0,
        clip.tempo_map.musical_seconds_at(end_beat)
        - clip.tempo_map.musical_seconds_at(start_beat),
    )


def _window_chords(
    clip: MidiClip,
    window: Mapping[str, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chord in clip.chords:
        start_tick, end_tick = _chord_ticks(clip, chord)
        if start_tick >= window["end_tick"] or end_tick <= window["start_tick"]:
            continue
        symbol, redacted = _safe_text(
            chord.symbol, fallback="private chord", maximum=80
        )
        rows.append(
            {
                "start_tick": start_tick,
                "end_tick": end_tick,
                "start_beat": chord.start_beat,
                "duration_beats": chord.duration_beats,
                "symbol": symbol,
                "symbol_redacted": redacted,
            }
        )
    return rows


def _reject_new_export_collisions(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> None:
    changed = {int(row["parent_note_index"]) for row in changes}
    parent_ticks = [_note_ticks(parent, note) for note in parent.notes]
    # The child tuple can reorder after pitch changes, so use the canonical
    # after payloads by original parent index rather than child tuple indices.
    after_pitches = [note.pitch for note in parent.notes]
    for row in changes:
        after_pitches[int(row["parent_note_index"])] = int(row["after"]["pitch"])
    for left in changed:
        for right in range(len(parent.notes)):
            if left == right or (right in changed and right < left):
                continue
            if after_pitches[left] != after_pitches[right]:
                continue
            if not _intervals_overlap(parent_ticks[left], parent_ticks[right]):
                continue
            before_collision = (
                parent.notes[left].pitch == parent.notes[right].pitch
                and _intervals_overlap(parent_ticks[left], parent_ticks[right])
            )
            if not before_collision:
                raise WorkbenchClipCorrectionError(
                    "Pitch correction would introduce a same-pitch MIDI overlap or collapse"
                )


def _intervals_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _validate_metadata_unchanged(parent: MidiClip, child: MidiClip) -> None:
    fields = (
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
    if any(getattr(parent, field) != getattr(child, field) for field in fields):
        raise WorkbenchClipCorrectionError(
            "Pitch correction changed protected Clip metadata"
        )
    if len(parent.notes) != len(child.notes):
        raise WorkbenchClipCorrectionError("Pitch correction changed the note count")


def _diff(
    parent: MidiClip,
    child: MidiClip,
    changes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    public = [_public_change(parent, row) for row in changes]
    return {
        "kind": "pitch_patch",
        "changed_note_count": len(public),
        "changes": public,
        "note_count_before": len(parent.notes),
        "note_count_after": len(child.notes),
        "pitch_range_before": _pitch_range(parent.notes),
        "pitch_range_after": _pitch_range(child.notes),
        "unchanged": _unchanged_projection(),
        "new_export_collisions": 0,
    }


def _public_change(parent: MidiClip, row: Mapping[str, Any]) -> dict[str, Any]:
    before = dict(row["before"])
    after = dict(row["after"])
    index = int(row["parent_note_index"])
    note = parent.notes[index]
    start_tick, end_tick = _note_ticks(parent, note)
    chord = _chord_at_export_tick(parent, start_tick)
    chord_symbol = None
    chord_redacted = False
    chord_pcs = None
    if chord is not None:
        chord_symbol, chord_redacted = _safe_text(
            chord.symbol, fallback="private chord", maximum=80
        )
        chord_pcs = parse_chord_name(chord.symbol)
    return {
        "note_ref": str(row["note_ref"]),
        "start_tick": start_tick,
        "end_tick": end_tick,
        "start_beat": before["start_beat"],
        "duration_beats": before["duration_beats"],
        "source_start_seconds": before["source_start_seconds"],
        "source_end_seconds": before["source_end_seconds"],
        "before_pitch": before["pitch"],
        "after_pitch": after["pitch"],
        "semitones": after["pitch"] - before["pitch"],
        "key_relation_before": _key_relation(parent, int(before["pitch"])),
        "key_relation_after": _key_relation(parent, int(after["pitch"])),
        "chord_relation_before": _chord_relation(chord_pcs, int(before["pitch"])),
        "chord_relation_after": _chord_relation(chord_pcs, int(after["pitch"])),
        "chord_symbol": chord_symbol,
        "chord_symbol_redacted": chord_redacted,
    }


def _key_relation(clip: MidiClip, pitch: int) -> str:
    if clip.key is None:
        return "unknown"
    scale = MINOR_SCALE if clip.key.mode == "minor" else MAJOR_SCALE
    allowed = {(clip.key.tonic_pc + interval) % 12 for interval in scale}
    return "in-key" if pitch % 12 in allowed else "chromatic"


def _chord_relation(pitch_classes: Sequence[int] | None, pitch: int) -> str:
    if not pitch_classes:
        return "unknown"
    return "chord-tone" if pitch % 12 in pitch_classes else "non-chord-tone"


def _chord_at_export_tick(clip: MidiClip, tick: int) -> ChordEvent | None:
    for chord in clip.chords:
        start_tick, end_tick = _chord_ticks(clip, chord)
        if start_tick <= tick < end_tick:
            return chord
    return None


def _pitch_range(notes: Sequence[ClipNote]) -> dict[str, int] | None:
    if not notes:
        return None
    pitches = [note.pitch for note in notes]
    return {"minimum": min(pitches), "maximum": max(pitches)}


def _unchanged_projection() -> dict[str, bool]:
    return {
        "note_count": True,
        "note_onsets": True,
        "note_durations": True,
        "source_seconds": True,
        "microtiming": True,
        "velocity": True,
        "release_velocity": True,
        "articulation": True,
        "tempo_map": True,
        "timing_mode": True,
        "key": True,
        "chords": True,
        "instrument": True,
        "provenance": True,
    }


def _warnings(parent: MidiClip, diff: Mapping[str, Any]) -> list[str]:
    warnings = [
        "The source Clip remains immutable; creation adds one child alternative only.",
        "Only the named note pitches change. Timing, velocity, expression, key and chords remain unchanged.",
        "Key and chord relations are advisory musical context, not correctness scores or snapping rules.",
        "The child is not selected, placed, auditioned or added to a GarageBand Pack automatically.",
    ]
    if parent.key is None:
        warnings.append("This Clip has no key metadata, so key relation is unknown.")
    if any(row["key_relation_after"] == "chromatic" for row in diff["changes"]):
        warnings.append(
            "At least one corrected pitch is chromatic to the retained key; chromatic notes can be intentional."
        )
    if any(
        row["chord_relation_after"] == "non-chord-tone" for row in diff["changes"]
    ):
        warnings.append(
            "At least one corrected pitch is not a tone of the chord active at its onset; passing notes can be intentional."
        )
    return warnings


def _effects(**changes: bool) -> dict[str, bool]:
    effects = {key: False for key in sorted(_EFFECT_KEYS)}
    for key, value in changes.items():
        if key not in _EFFECT_KEYS or not isinstance(value, bool):
            raise ValueError("Unknown Clip correction effect")
        effects[key] = value
    return effects


def _exact_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkbenchClipCorrectionError(f"{label} must be an integer")
    return value


def _safe_clip_identifier(value: Any, label: str) -> str:
    try:
        return _safe_identifier(value, label)
    except ValueError as exc:
        raise WorkbenchClipCorrectionError(str(exc)) from exc


def _sha256_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WorkbenchClipCorrectionError(
            f"{label} must be a lower-case SHA-256 digest"
        )
    return value


def _document_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


__all__ = [
    "CLIP_CORRECTION_CAPABILITY_SCHEMA",
    "CLIP_CORRECTION_PREVIEW_SCHEMA",
    "CLIP_CORRECTION_RESULT_SCHEMA",
    "CLIP_CORRECTION_SUMMARY_SCHEMA",
    "CLIP_CORRECTION_WINDOW_SCHEMA",
    "WorkbenchClipCorrectionConflictError",
    "WorkbenchClipCorrectionError",
    "WorkbenchClipCorrectionNotFoundError",
    "WorkbenchClipCorrectionService",
]
