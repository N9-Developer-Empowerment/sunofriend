"""Explicit, append-only Clip transform previews and creation.

Phase 6.2 deliberately keeps this write boundary separate from ordinary Clip
browsing.  A preview is a zero-effect deterministic projection pinned to one
parent object and one verified library state.  Creation accepts that exact
projection only and can append one immutable child; it never updates the
parent, a reuse placement, the current arrangement, a pack or feedback.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .clip import KeySignature, MidiClip, resolve_export_timing
from .library import ClipLibrary, ClipSummary
from .transform import retime_bpm, transpose_same_mode
from .workbench_clips import (
    WorkbenchClipService,
    _LibraryState,
    _duration_projection,
    _safe_identifier,
    _safe_role,
)


CLIP_TRANSFORM_CAPABILITY_SCHEMA = (
    "sunofriend.workbench-clip-transform-capability.v1"
)
CLIP_TRANSFORM_PREVIEW_SCHEMA = "sunofriend.workbench-clip-transform-preview.v1"
CLIP_TRANSFORM_RESULT_SCHEMA = "sunofriend.workbench-clip-transform-result.v1"
_TRANSFORM_INTENT_SCHEMA = "sunofriend.workbench-clip-transform-intent.v1"
_MAX_NOTES = 20_000
_MAX_DURATION_SECONDS = 20.0 * 60.0
_MIN_BPM = 20.0
_MAX_BPM = 400.0
_MIN_BPM_RATIO = 0.25
_MAX_BPM_RATIO = 4.0
_PREVIEW_KEYS = {
    "parent_clip_id",
    "parent_object_sha256",
    "library_state_sha256",
    "transform",
}
_CREATE_KEYS = _PREVIEW_KEYS | {"action", "projection_sha256"}
_EFFECT_KEYS = {
    "library_mutated",
    "child_clip_created",
    "source_clip_mutated",
    "transform_applied",
    "reuse_plan_changed",
    "placement_changed",
    "current_arrangement_changed",
    "pack_changed",
    "hybrid_created",
    "feedback_recorded",
    "data_submitted",
}
_DRUM_ROLES = {
    "drum",
    "drums",
    "drum kit",
    "drum set",
    "drumset",
    "drumkit",
    "acoustic drums",
    "electronic drums",
    "kit",
    "percussion",
    "kick",
    "snare",
    "hat",
    "hats",
    "hi hat",
    "hi hats",
    "hihat",
    "hihats",
    "cymbal",
    "cymbals",
    "tom",
    "toms",
    "other kit",
    "otherkit",
}


class WorkbenchClipTransformError(ValueError):
    """Base error for a rejected explicit Clip transform request."""


class WorkbenchClipTransformConflictError(WorkbenchClipTransformError):
    """The exact parent, object, library or projection pin is stale."""


class WorkbenchClipTransformNotFoundError(WorkbenchClipTransformError):
    """The explicitly requested parent Clip is not in the verified library."""


class WorkbenchClipTransformService:
    """Preview and append one reversible Clip child at a time."""

    def __init__(
        self,
        *,
        clip_service: WorkbenchClipService,
        writer: ClipLibrary,
    ) -> None:
        self._clip_service = clip_service
        self._writer = writer

    @classmethod
    def open(
        cls,
        *,
        clip_service: WorkbenchClipService,
        library_root: str | Path,
    ) -> "WorkbenchClipTransformService":
        """Open the exact verified existing library without initializing it."""

        if not isinstance(clip_service, WorkbenchClipService):
            raise TypeError("clip_service must be a WorkbenchClipService")
        requested = Path(os.path.abspath(Path(library_root).expanduser()))
        if requested.is_symlink():
            raise ValueError("Clip transform library root must not be a symlink")
        if requested != clip_service._transform_library_identity():
            raise ValueError("Clip transform library must match the verified Clip library")
        writer = ClipLibrary.open_existing_writer(requested)
        if writer.root != requested.resolve():
            raise ValueError("Clip transform library identity changed while opening")
        return cls(clip_service=clip_service, writer=writer)

    def capability(self) -> dict[str, Any]:
        """Describe the separately gated, one-child append boundary."""

        state = self._snapshot()
        append_available = self._clip_service._transform_has_append_capacity(state)
        return {
            "schema": CLIP_TRANSFORM_CAPABILITY_SCHEMA,
            "enabled": True,
            "write_scope": "one-new-immutable-child-after-explicit-preview-and-create",
            "idempotency": "exact-create-request",
            "actions": {
                "preview": append_available,
                "create": append_available,
            },
            "transforms": {
                "same_mode_key": {
                    "enabled": True,
                    "directions": ["nearest", "up", "down"],
                    "cross_mode": False,
                    "drum_family": False,
                },
                "bpm": {
                    "enabled": True,
                    "timing_modes": ["musical", "stem_locked"],
                },
                "tuning": False,
                "downbeat": False,
            },
            "library": {
                "state_sha256": state.state_sha256,
                "clip_count": len(state.summaries),
            },
            "limits": {
                "maximum_notes": _MAX_NOTES,
                "maximum_duration_seconds": _MAX_DURATION_SECONDS,
                "minimum_bpm": _MIN_BPM,
                "maximum_bpm": _MAX_BPM,
                "minimum_bpm_ratio": _MIN_BPM_RATIO,
                "maximum_bpm_ratio": _MAX_BPM_RATIO,
                "operations_per_child": 1,
            },
            "effects": _effects(),
        }

    def preview(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Return a path-free, deterministic and zero-effect transform projection."""

        parsed = _parse_request(request, create=False)
        state = self._snapshot()
        if parsed["library_state_sha256"] != state.state_sha256:
            raise WorkbenchClipTransformConflictError(
                "Clip library state changed; request a fresh transform preview"
            )
        if not self._clip_service._transform_has_append_capacity(state):
            raise WorkbenchClipTransformError(
                "Clip library has reached the 10000 Clip transform limit"
            )
        parent, summary = _parent_from_state(state, parsed)
        return _project(parent=parent, summary=summary, request=parsed)

    def create(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Append the exact previewed child, or return its idempotent replay."""

        parsed = _parse_request(request, create=True)
        try:
            state = self._clip_service._transform_create_snapshot(
                expected_state_sha256=parsed["library_state_sha256"],
            )
        except RuntimeError as exc:
            raise WorkbenchClipTransformConflictError(
                "Verified Clip library state changed; restart or request a fresh preview"
            ) from exc
        parent, summary = _parent_from_state(state, parsed)
        projection = _project(parent=parent, summary=summary, request=parsed)
        if parsed["projection_sha256"] != projection["projection_sha256"]:
            raise WorkbenchClipTransformConflictError(
                "Transform projection changed; request a fresh preview"
            )
        child = _transformed_child(parent, parsed["transform"], projection["intent_sha256"])
        expected_child_hash = projection["child"]["object_sha256"]
        if hashlib.sha256(child.canonical_bytes()).hexdigest() != expected_child_hash:
            raise RuntimeError("Transform child projection is not deterministic")
        try:
            append = self._clip_service._append_transform_child(
                writer=self._writer,
                expected_state_sha256=parsed["library_state_sha256"],
                parent_clip_id=parsed["parent_clip_id"],
                expected_parent_object_hash=parsed["parent_object_sha256"],
                child=child,
            )
        except KeyError as exc:
            raise WorkbenchClipTransformNotFoundError(
                "Parent Clip is no longer available"
            ) from exc
        except RuntimeError as exc:
            if "conflict" in str(exc).casefold() or "changed" in str(exc).casefold():
                raise WorkbenchClipTransformConflictError(
                    "Clip library changed; request a fresh transform preview"
                ) from exc
            raise

        replayed = append.replayed
        return {
            "schema": CLIP_TRANSFORM_RESULT_SCHEMA,
            "status": "replayed" if replayed else "created",
            "operation": "clip-transform-create",
            "projection_sha256": projection["projection_sha256"],
            "replayed": replayed,
            "transform": dict(projection["transform"]),
            "parent": dict(projection["parent"]),
            "child": dict(projection["child"]),
            "diff": dict(projection["diff"]),
            "warnings": list(projection["warnings"]),
            "library": {
                "expected_state_sha256": parsed["library_state_sha256"],
                "previous_state_sha256": append.previous_state_sha256,
                "current_state_sha256": append.current_state.state_sha256,
            },
            "effects": _effects(
                library_mutated=not replayed,
                child_clip_created=not replayed,
                transform_applied=not replayed,
            ),
        }

    def _snapshot(self) -> _LibraryState:
        try:
            return self._clip_service._transform_snapshot()
        except RuntimeError as exc:
            raise WorkbenchClipTransformConflictError(
                "Verified Clip library state changed; restart or request a fresh preview"
            ) from exc


def _parse_request(request: Mapping[str, Any], *, create: bool) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise WorkbenchClipTransformError("Clip transform request must be an object")
    expected_keys = _CREATE_KEYS if create else _PREVIEW_KEYS
    if set(request) != expected_keys:
        raise WorkbenchClipTransformError(
            "Clip transform request fields do not match the exact contract"
        )
    if create and request.get("action") != "create":
        raise WorkbenchClipTransformError("Clip transform create action must be 'create'")
    parent_clip_id = _safe_identifier(request.get("parent_clip_id"), "parent_clip_id")
    parent_hash = _sha256_value(request.get("parent_object_sha256"), "parent_object_sha256")
    library_hash = _sha256_value(request.get("library_state_sha256"), "library_state_sha256")
    transform = _parse_transform(request.get("transform"))
    parsed: dict[str, Any] = {
        "parent_clip_id": parent_clip_id,
        "parent_object_sha256": parent_hash,
        "library_state_sha256": library_hash,
        "transform": transform,
    }
    if create:
        parsed["action"] = "create"
        parsed["projection_sha256"] = _sha256_value(
            request.get("projection_sha256"), "projection_sha256"
        )
    return parsed


def _parse_transform(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkbenchClipTransformError("transform must be an object")
    kind = value.get("kind")
    if kind == "key":
        if set(value) != {"kind", "target_key", "direction"}:
            raise WorkbenchClipTransformError(
                "Key transform requires exactly kind, target_key and direction"
            )
        target_raw = value.get("target_key")
        if not isinstance(target_raw, str) or len(target_raw) > 32:
            raise WorkbenchClipTransformError("target_key must be a bounded full key")
        try:
            target = KeySignature.parse(target_raw)
        except ValueError as exc:
            raise WorkbenchClipTransformError(
                "target_key must include tonic and major/minor mode"
            ) from exc
        assert target is not None
        direction = value.get("direction")
        if direction not in {"nearest", "up", "down"}:
            raise WorkbenchClipTransformError(
                "direction must be 'nearest', 'up' or 'down'"
            )
        return {"kind": "key", "target_key": str(target), "direction": direction}
    if kind == "bpm":
        if set(value) != {"kind", "target_bpm", "timing_mode"}:
            raise WorkbenchClipTransformError(
                "BPM transform requires exactly kind, target_bpm and timing_mode"
            )
        target_bpm = _finite_number(value.get("target_bpm"), "target_bpm")
        if not _MIN_BPM <= target_bpm <= _MAX_BPM:
            raise WorkbenchClipTransformError(
                f"target_bpm must be between {_MIN_BPM:g} and {_MAX_BPM:g}"
            )
        timing_mode = value.get("timing_mode")
        if timing_mode not in {"musical", "stem_locked"}:
            raise WorkbenchClipTransformError(
                "timing_mode must be 'musical' or 'stem_locked'"
            )
        return {
            "kind": "bpm",
            "target_bpm": target_bpm,
            "timing_mode": timing_mode,
        }
    raise WorkbenchClipTransformError("transform kind must be 'key' or 'bpm'")


def _parent_from_state(
    state: _LibraryState,
    request: Mapping[str, Any],
) -> tuple[MidiClip, ClipSummary]:
    parent_id = str(request["parent_clip_id"])
    try:
        parent = state.clips[parent_id]
        summary = next(row for row in state.summaries if row.clip_id == parent_id)
    except (KeyError, StopIteration) as exc:
        raise WorkbenchClipTransformNotFoundError("Unknown parent Clip") from exc
    if summary.object_hash != request["parent_object_sha256"]:
        raise WorkbenchClipTransformConflictError(
            "Parent Clip object changed; request a fresh transform preview"
        )
    _validate_parent_bounds(parent)
    return parent, summary


def _project(
    *,
    parent: MidiClip,
    summary: ClipSummary,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    transform = dict(request["transform"])
    intent = {
        "schema": _TRANSFORM_INTENT_SCHEMA,
        "parent_clip_id": request["parent_clip_id"],
        "parent_object_sha256": request["parent_object_sha256"],
        "library_state_sha256": request["library_state_sha256"],
        "transform": transform,
    }
    intent_sha256 = _document_hash(intent)
    child = _transformed_child(parent, transform, intent_sha256)
    _validate_child_bounds(child)
    child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
    diff = _diff(parent, child, transform)
    warnings = _warnings(transform)
    document: dict[str, Any] = {
        "schema": CLIP_TRANSFORM_PREVIEW_SCHEMA,
        "status": "previewed",
        "operation": "clip-transform-preview",
        "intent_sha256": intent_sha256,
        "library": {"state_sha256": request["library_state_sha256"]},
        "transform": transform,
        "parent": _clip_identity(summary=summary, clip=parent),
        "child": _child_identity(
            parent_summary=summary,
            child=child,
            object_hash=child_hash,
        ),
        "diff": diff,
        "warnings": warnings,
        "effects": _effects(),
    }
    document["projection_sha256"] = _document_hash(document)
    return document


def _transformed_child(
    parent: MidiClip,
    transform: Mapping[str, Any],
    intent_sha256: str,
) -> MidiClip:
    if transform["kind"] == "key":
        if _is_drum_family(parent):
            raise WorkbenchClipTransformError(
                "Drum-family Clips cannot use a pitched key transform"
            )
        if parent.key is None:
            raise WorkbenchClipTransformError(
                "Same-mode key transform requires a keyed parent Clip"
            )
        target = KeySignature.parse(str(transform["target_key"]))
        assert target is not None
        if target.mode != parent.key.mode:
            raise WorkbenchClipTransformError(
                "Cross-mode key changes are deferred; target mode must match the parent"
            )
        if target.tonic_pc == parent.key.tonic_pc:
            raise WorkbenchClipTransformError("Key transform would be a no-op")
        transformed = transpose_same_mode(
            parent,
            target.tonic,
            direction=str(transform["direction"]),
        )
    else:
        target_bpm = float(transform["target_bpm"])
        if math.isclose(target_bpm, parent.bpm, rel_tol=0.0, abs_tol=1e-9):
            raise WorkbenchClipTransformError("BPM transform would be a no-op")
        ratio = target_bpm / parent.bpm
        if not _MIN_BPM_RATIO <= ratio <= _MAX_BPM_RATIO:
            raise WorkbenchClipTransformError(
                "target_bpm ratio must be between 0.25 and 4 times the parent BPM"
            )
        transformed = retime_bpm(
            parent,
            target_bpm,
            mode=str(transform["timing_mode"]),
        )
    return replace(transformed, clip_id=f"sf-transform-{intent_sha256}")


def _validate_parent_bounds(clip: MidiClip) -> None:
    if len(clip.notes) > _MAX_NOTES:
        raise WorkbenchClipTransformError("Parent Clip exceeds the 20000 note limit")
    if _maximum_duration(clip) > _MAX_DURATION_SECONDS + 1e-9:
        raise WorkbenchClipTransformError("Parent Clip exceeds the 20 minute limit")


def _validate_child_bounds(clip: MidiClip) -> None:
    if len(clip.notes) > _MAX_NOTES:
        raise WorkbenchClipTransformError("Child Clip exceeds the 20000 note limit")
    if _maximum_duration(clip) > _MAX_DURATION_SECONDS + 1e-9:
        raise WorkbenchClipTransformError("Transform child exceeds the 20 minute limit")


def _maximum_duration(clip: MidiClip) -> float:
    mode, bpm = resolve_export_timing(
        clip,
        timing_mode="auto",
        garageband_bpm=None,
    )
    duration = _duration_projection(clip, mode, bpm)
    return max(
        float(duration["source_end_seconds"]),
        float(duration["export_seconds"]),
    )


def _clip_identity(*, summary: ClipSummary, clip: MidiClip) -> dict[str, Any]:
    role, role_redacted = _safe_role(clip.instrument.role)
    return {
        "clip_id": clip.clip_id,
        "object_sha256": summary.object_hash,
        "parent_clip_id": clip.parent_clip_id,
        "lineage_id": summary.lineage_id,
        "revision": clip.revision,
        "key": None if clip.key is None else str(clip.key),
        "bpm": clip.bpm,
        "role": role,
        "role_redacted": role_redacted,
        "note_count": len(clip.notes),
        "chord_count": len(clip.chords),
        "pitch_range": _pitch_range(clip),
        "duration_seconds": _maximum_duration(clip),
    }


def _child_identity(
    *,
    parent_summary: ClipSummary,
    child: MidiClip,
    object_hash: str,
) -> dict[str, Any]:
    role, role_redacted = _safe_role(child.instrument.role)
    return {
        "clip_id": child.clip_id,
        "object_sha256": object_hash,
        "parent_clip_id": child.parent_clip_id,
        "lineage_id": parent_summary.lineage_id,
        "revision": child.revision,
        "key": None if child.key is None else str(child.key),
        "bpm": child.bpm,
        "role": role,
        "role_redacted": role_redacted,
        "note_count": len(child.notes),
        "chord_count": len(child.chords),
        "pitch_range": _pitch_range(child),
        "duration_seconds": _maximum_duration(child),
    }


def _diff(
    parent: MidiClip,
    child: MidiClip,
    transform: Mapping[str, Any],
) -> dict[str, Any]:
    if transform["kind"] == "key":
        parameters = child.transform_recipe.parameters_dict if child.transform_recipe else {}
        return {
            "kind": "key",
            "key_before": None if parent.key is None else str(parent.key),
            "key_after": None if child.key is None else str(child.key),
            "semitones": int(parameters.get("semitones", 0)),
            "note_pitches_changed": sum(
                before.pitch != after.pitch
                for before, after in zip(parent.notes, child.notes)
            ),
            "chord_symbols_changed": sum(
                before.symbol != after.symbol
                for before, after in zip(parent.chords, child.chords)
            ),
            "note_count_before": len(parent.notes),
            "note_count_after": len(child.notes),
            "chord_count_before": len(parent.chords),
            "chord_count_after": len(child.chords),
            "bpm_changed": False,
            "timing_changed": False,
        }
    timing_mode = str(transform["timing_mode"])
    return {
        "kind": "bpm",
        "bpm_before": parent.bpm,
        "bpm_after": child.bpm,
        "ratio": child.bpm / parent.bpm,
        "timing_mode": timing_mode,
        "note_count_before": len(parent.notes),
        "note_count_after": len(child.notes),
        "chord_count_before": len(parent.chords),
        "chord_count_after": len(child.chords),
        "beat_positions_changed": timing_mode == "stem_locked",
        "source_seconds_changed": timing_mode == "musical",
        "pitch_changed": False,
        "key_changed": False,
    }


def _warnings(transform: Mapping[str, Any]) -> list[str]:
    fixed = [
        "The source Clip remains immutable.",
        "Existing reuse placements remain pinned to the source Clip until explicitly replaced.",
        "Creation adds one library version only; it does not change the current arrangement or pack.",
        "Retrying this exact create request is idempotent; a later fresh preview is a deliberate new branch.",
    ]
    if transform["kind"] == "key":
        return fixed + [
            "This is a mechanical same-mode transposition; major/minor mode is unchanged.",
            "The transposed MIDI will not match untreated source-stem pitch.",
        ]
    if transform["timing_mode"] == "musical":
        return fixed + [
            "Musical retiming keeps beat positions and changes elapsed time, so untreated source audio will not stay aligned."
        ]
    return fixed + [
        "Stem-locked retiming preserves source seconds and moves beat positions; set GarageBand to the target BPM."
    ]


def _is_drum_family(clip: MidiClip) -> bool:
    if clip.instrument.is_drums:
        return True
    role = " ".join(
        clip.instrument.role.casefold().replace("-", " ").replace("_", " ").split()
    )
    tokens = set(role.split())
    return (
        role in _DRUM_ROLES
        or bool(tokens & {"kick", "snare", "hihat", "hihats", "cymbal", "cymbals", "tom", "toms"})
        or "percussion" in tokens
        or (bool(tokens & {"drum", "drums", "drumkit", "drumset"}) and "steel" not in tokens)
    )


def _pitch_range(clip: MidiClip) -> dict[str, int] | None:
    if not clip.notes:
        return None
    pitches = [note.pitch for note in clip.notes]
    return {"minimum": min(pitches), "maximum": max(pitches)}


def _effects(**changes: bool) -> dict[str, bool]:
    effects = {key: False for key in sorted(_EFFECT_KEYS)}
    for key, value in changes.items():
        if key not in _EFFECT_KEYS or not isinstance(value, bool):
            raise ValueError("Unknown Clip transform effect")
        effects[key] = value
    return effects


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkbenchClipTransformError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise WorkbenchClipTransformError(f"{label} must be a finite number")
    return number


def _sha256_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise WorkbenchClipTransformError(
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


__all__ = [
    "CLIP_TRANSFORM_CAPABILITY_SCHEMA",
    "CLIP_TRANSFORM_PREVIEW_SCHEMA",
    "CLIP_TRANSFORM_RESULT_SCHEMA",
    "WorkbenchClipTransformConflictError",
    "WorkbenchClipTransformError",
    "WorkbenchClipTransformNotFoundError",
    "WorkbenchClipTransformService",
]
