"""Gated, read-only Clip v1 browsing and derived audition artifacts.

This module is the deliberately small Phase 6 entry boundary.  Ordinary browse,
detail and artifact operations do not import clips, edit metadata, transform
notes or write to the Clip library.  A resolved Phase 5 GarageBand acceptance
result and its exact ZIP are verified before the library is opened through
:class:`~sunofriend.library.ClipLibrary`'s read-only mode.  The separately
gated transform service may call one private compare-and-swap append/adoption
method after its explicit review/create contract; that method is not exposed to
ordinary Clip browsing.

The public projections contain no filesystem paths, provenance/source fields,
private notes or transform parameters.  The path-bearing artifact record is an
internal server hand-off only; callers must use :func:`public_artifact` before
serialising a response.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sqlite3
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .clip import KeySignature, MidiClip, resolve_export_timing, write_clip_midi
from .garageband_pack_acceptance import verify_garageband_pack_archive
from .library import MAXIMUM_CLIP_COUNT, ClipLibrary, ClipSummary
from .render import find_fluidsynth, find_soundfont, render_midi_to_wav
from .workbench_privacy import contains_local_path, path_free_role


ACCEPTANCE_RESULT_SCHEMA = (
    "sunofriend.workbench-garageband-pack-acceptance-result.v1"
)
CLIP_CAPABILITY_SCHEMA = "sunofriend.workbench-clip-capability.v1"
CLIP_BROWSE_SCHEMA = "sunofriend.workbench-clip-browse.v1"
CLIP_DETAIL_SCHEMA = "sunofriend.workbench-clip-detail.v1"
CLIP_ARTIFACT_SCHEMA = "sunofriend.workbench-clip-artifact.v1"
_CLIP_ARTIFACT_MANIFEST_SCHEMA = "sunofriend.workbench-clip-artifact-cache.v1"
_EXPORT_POLICY = "clip-v1-auto-timing-tpq480.v1"
_PREVIEW_POLICY = {
    "renderer": "fluidsynth",
    "sample_rate": 44_100,
    "gain": 0.7,
    "reverb": False,
    "chorus": False,
    "timeout_seconds": 120.0,
}
_MAX_ACCEPTANCE_BYTES = 4 * 1024 * 1024
_MAX_LIBRARY_CLIPS = MAXIMUM_CLIP_COUNT
_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 50
_MAXIMUM_ARTIFACT_SECONDS = 20.0 * 60.0
_HASH_BLOCK_BYTES = 1024 * 1024
_SAFE_EFFECTS = {
    "library_mutated": False,
    "clip_mutated": False,
    "source_candidate_mutated": False,
    "transform_applied": False,
    "selection_changed": False,
    "feedback_recorded": False,
    "preview_changed_library": False,
    "data_submitted": False,
}
_ACCEPTANCE_EFFECT_KEYS = {
    "tutorial_changed_project",
    "quiz_selected_candidate",
    "feedback_recorded",
    "musical_selection_changed",
    "pack_basket_changed",
    "midi_mutated",
    "candidate_promoted",
    "default_changed",
    "data_submitted",
    "phase6_started_automatically",
}
_ACCEPTANCE_CHECKS = {
    "garageband-pack": 6,
    "local-usability": 6,
}


@dataclass(frozen=True)
class _AcceptanceState:
    result_sha256: str
    result_bytes: int
    pack_sha256: str
    pack_bytes: int
    developer_code_binding_sha256: str | None


@dataclass(frozen=True)
class _LibraryState:
    state_sha256: str
    summaries: tuple[ClipSummary, ...]
    clips: Mapping[str, MidiClip]
    lineage_count: int


@dataclass(frozen=True)
class _TransformAppendState:
    summary: ClipSummary
    previous_state_sha256: str
    current_state: _LibraryState
    replayed: bool


class WorkbenchClipService:
    """Read-only Phase 6 Clip service suitable for Workbench route handlers.

    Use :meth:`open` rather than constructing this class directly.  Every
    operation revalidates the exact acceptance result, the exact GarageBand
    pack and all catalogued Clip object hashes against the state captured at
    open time.  Unexpected drift requires an explicit service restart.  The
    only exception is the separately gated transform service's private exact
    append path, which re-verifies and adopts one proven child addition.
    """

    def __init__(
        self,
        *,
        library: ClipLibrary,
        library_root: Path,
        cache_root: Path,
        acceptance_result_path: Path,
        garageband_pack_path: Path,
        acceptance: _AcceptanceState,
        library_state: _LibraryState,
        soundfont_path: Path | None,
        fluidsynth_path: Path | None,
    ) -> None:
        self._library = library
        self._library_root = library_root
        self._cache_root = cache_root
        self._acceptance_result_path = acceptance_result_path
        self._garageband_pack_path = garageband_pack_path
        self._acceptance = acceptance
        self._library_state = library_state
        self._soundfont_path = soundfont_path
        self._fluidsynth_path = fluidsynth_path
        self._soundfont_record: dict[str, Any] | None = None
        self._fluidsynth_record: dict[str, Any] | None = None
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        *,
        acceptance_result_path: str | Path,
        garageband_pack_path: str | Path,
        library_root: str | Path,
        cache_root: str | Path,
        soundfont_path: str | Path | None = None,
        fluidsynth_path: str | Path | None = None,
    ) -> "WorkbenchClipService":
        """Verify the Phase 5 gate, then open one explicit existing library.

        The ordering is intentional: a failed or altered acceptance gate must
        not even open the Clip catalog.  The cache is prepared only after the
        gate and library have both verified.
        """

        # Preserve the caller's final path component so a symlink cannot be
        # hidden by ``resolve()`` before the regular-file gate runs.
        result_path = _unresolved_absolute(acceptance_result_path)
        pack_path = _unresolved_absolute(garageband_pack_path)
        acceptance = _validate_acceptance(result_path, pack_path)

        library_path = _unresolved_absolute(library_root)
        if (
            not library_path.exists()
            or not library_path.is_dir()
            or library_path.is_symlink()
        ):
            raise ValueError("Clip library must be an explicit existing directory")
        _require_regular_file(
            library_path / "catalog.sqlite3",
            "Clip library database",
        )
        objects_path = library_path / "objects"
        if (
            not objects_path.exists()
            or not objects_path.is_dir()
            or objects_path.is_symlink()
        ):
            raise ValueError("Clip library objects must be a real directory")
        try:
            library = ClipLibrary(library_path, read_only=True)
        except TypeError as exc:  # pragma: no cover - protects mixed installations
            raise RuntimeError("This Sunofriend build lacks read-only Clip library support") from exc
        library_state = _capture_library_state(library)

        cache_path = _unresolved_absolute(cache_root)
        if cache_path.is_symlink():
            raise ValueError("Clip artifact cache root must be a real directory")
        canonical_library_path = library_path.resolve()
        canonical_cache_path = cache_path.resolve(strict=False)
        if _is_relative_to(canonical_cache_path, canonical_library_path):
            raise ValueError("Clip artifact cache must be outside the read-only library")
        _prepare_cache_root(cache_path)

        explicit_soundfont = (
            None if soundfont_path is None else _absolute(soundfont_path)
        )
        explicit_fluidsynth = (
            None if fluidsynth_path is None else _absolute(fluidsynth_path)
        )
        return cls(
            library=library,
            library_root=library_path,
            cache_root=cache_path,
            acceptance_result_path=result_path,
            garageband_pack_path=pack_path,
            acceptance=acceptance,
            library_state=library_state,
            soundfont_path=explicit_soundfont,
            fluidsynth_path=explicit_fluidsynth,
        )

    def capability(self) -> dict[str, Any]:
        """Return path-free gate, inventory and zero-effect capability facts."""

        state = self._stable_state()
        roles = sorted({_safe_role(clip.instrument.role)[0] for clip in state.clips.values()})
        keys = sorted({str(clip.key) for clip in state.clips.values() if clip.key is not None})
        bpms = [clip.bpm for clip in state.clips.values()]
        return {
            "schema": CLIP_CAPABILITY_SCHEMA,
            "enabled": True,
            "read_only": True,
            "acceptance": {
                "schema": ACCEPTANCE_RESULT_SCHEMA,
                "status": "passed",
                "phase6_read_only_clip_entry_ready": True,
                "explicit_hybrid_construction_ready": False,
                "result_sha256": self._acceptance.result_sha256,
                "pack_sha256": self._acceptance.pack_sha256,
                "developer_code_binding_sha256": (
                    self._acceptance.developer_code_binding_sha256
                ),
            },
            "library": {
                "state_sha256": state.state_sha256,
                "clip_count": len(state.summaries),
                "lineage_count": state.lineage_count,
                "verified_object_count": len(state.clips),
                "roles": roles,
                "keys": keys,
                "bpm_range": (
                    None
                    if not bpms
                    else {"minimum": min(bpms), "maximum": max(bpms)}
                ),
            },
            "features": {
                "browse": True,
                "detail": True,
                "lineage": True,
                "deterministic_midi_export": True,
                "optional_neutral_preview": True,
                "editing": False,
                "transformation": False,
                "hybrid_construction": False,
            },
            "limits": {
                "maximum_page_size": _MAX_PAGE_SIZE,
                "maximum_clip_count": _MAX_LIBRARY_CLIPS,
                "maximum_artifact_duration_seconds": _MAXIMUM_ARTIFACT_SECONDS,
            },
            "effects": _effects(),
        }

    def _transform_library_identity(self) -> Path:
        """Return the already verified library root to the gated transform service."""

        return self._library_root

    def _transform_snapshot(self) -> _LibraryState:
        """Return one verified immutable snapshot under the shared service lock."""

        with self._lock:
            return self._stable_state()

    def _transform_create_snapshot(
        self,
        *,
        expected_state_sha256: str,
    ) -> _LibraryState:
        """Return the exact preview baseline needed to verify a create retry.

        A second Workbench process may observe the first process's valid append
        before it reaches the catalog CAS.  Creation may still recompute the
        deterministic child from its already verified launch snapshot, but the
        append boundary below must prove that the newer catalog contains only
        that exact child before adopting it.  Ordinary browsing remains strict.
        """

        with self._lock:
            current = self._verified_current_library_state()
            if current.state_sha256 == self._library_state.state_sha256:
                return current
            if expected_state_sha256 == self._library_state.state_sha256:
                return self._library_state
            raise RuntimeError("Clip library state conflict")

    @staticmethod
    def _transform_has_append_capacity(state: _LibraryState) -> bool:
        """Return whether one more child can fit within the accepted inventory."""

        return len(state.summaries) < _MAX_LIBRARY_CLIPS

    def _append_transform_child(
        self,
        *,
        writer: ClipLibrary,
        expected_state_sha256: str,
        parent_clip_id: str,
        expected_parent_object_hash: str,
        child: MidiClip,
    ) -> _TransformAppendState:
        """Append and adopt exactly one verified child without weakening browsing.

        This is intentionally private to the separately gated Phase 6 transform
        service.  Ordinary Workbench Clip browsing continues to use a SQLite
        read-only connection and cannot obtain the append-only writer.
        """

        with self._lock:
            baseline = self._library_state
            before = self._verified_current_library_state()
            child_hash = hashlib.sha256(child.canonical_bytes()).hexdigest()
            existing = before.clips.get(child.clip_id)
            exact_existing_child = False
            existing_summary = None
            if existing == child:
                existing_summary = next(
                    row for row in before.summaries if row.clip_id == child.clip_id
                )
                exact_existing_child = (
                    existing_summary.object_hash == child_hash
                    and existing_summary.parent_clip_id == parent_clip_id
                )

            if before.state_sha256 != baseline.state_sha256:
                if not exact_existing_child or existing_summary is None:
                    raise RuntimeError("Clip library state conflict")
                _validate_exact_transform_append(
                    baseline,
                    before,
                    child=child,
                    child_hash=child_hash,
                    summary=existing_summary,
                )
                self._library_state = before
                return _TransformAppendState(
                    summary=existing_summary,
                    previous_state_sha256=before.state_sha256,
                    current_state=before,
                    replayed=True,
                )

            if before.state_sha256 != expected_state_sha256:
                if exact_existing_child and existing_summary is not None:
                    return _TransformAppendState(
                        summary=existing_summary,
                        previous_state_sha256=before.state_sha256,
                        current_state=before,
                        replayed=True,
                    )
                raise RuntimeError("Clip library state conflict")
            if not self._transform_has_append_capacity(before):
                raise RuntimeError("Clip library maximum clip count reached")

            receipt = writer.append_version_if_state(
                parent_clip_id,
                child,
                expected_state_sha256=expected_state_sha256,
                expected_parent_object_hash=expected_parent_object_hash,
            )
            after = _capture_library_state(self._library)
            _validate_exact_transform_append(
                before,
                after,
                child=child,
                child_hash=child_hash,
                summary=receipt.summary,
            )
            self._library_state = after
            return _TransformAppendState(
                summary=receipt.summary,
                previous_state_sha256=before.state_sha256,
                current_state=after,
                replayed=receipt.replayed,
            )

    def browse(
        self,
        text: str | None = None,
        *,
        role: str | None = None,
        key: str | KeySignature | None = None,
        bpm: float | None = None,
        bpm_tolerance: float = 0.01,
        tags: Iterable[str] = (),
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search sanitized Clip fields and return one bounded path-free page."""

        state = self._stable_state()
        query = _browse_query(
            text=text,
            role=role,
            key=key,
            bpm=bpm,
            bpm_tolerance=bpm_tolerance,
            tags=tags,
            limit=limit,
            offset=offset,
        )
        matching: list[tuple[ClipSummary, MidiClip]] = []
        for summary in state.summaries:
            clip = state.clips[summary.clip_id]
            projection = _summary_projection(summary, clip)
            if _matches_query(projection, query):
                matching.append((summary, clip))
        page_rows = matching[query["offset"] : query["offset"] + query["limit"]]
        return {
            "schema": CLIP_BROWSE_SCHEMA,
            "read_only": True,
            "library_state_sha256": state.state_sha256,
            "query": dict(query),
            "page": {
                "limit": query["limit"],
                "offset": query["offset"],
                "total": len(matching),
                "returned": len(page_rows),
                "has_more": query["offset"] + len(page_rows) < len(matching),
            },
            "clips": [_summary_projection(summary, clip) for summary, clip in page_rows],
            "effects": _effects(),
        }

    def detail(self, clip_id: str) -> dict[str, Any]:
        """Return musical facts and sanitized lineage for one verified clip."""

        requested = _safe_identifier(clip_id, "clip_id")
        state = self._stable_state()
        try:
            clip = state.clips[requested]
        except KeyError as exc:
            raise KeyError("Unknown clip_id") from exc
        summary = next(row for row in state.summaries if row.clip_id == requested)
        lineage_rows = sorted(
            (
                row
                for row in state.summaries
                if row.lineage_id == summary.lineage_id
            ),
            key=lambda row: (row.revision, row.created_at, row.clip_id),
        )
        timing_mode, timing_bpm = resolve_export_timing(
            clip,
            timing_mode="auto",
            garageband_bpm=None,
        )
        duration = _duration_projection(clip, timing_mode, timing_bpm)
        timing = _timing_projection(clip, timing_mode, timing_bpm)
        versions = [
            _lineage_projection(row, state.clips[row.clip_id])
            for row in lineage_rows
        ]
        return {
            "schema": CLIP_DETAIL_SCHEMA,
            "read_only": True,
            "library_state_sha256": state.state_sha256,
            "clip": {
                **_summary_projection(summary, clip),
                "note_count": len(clip.notes),
                "chord_count": len(clip.chords),
                "duration": duration,
                "duration_seconds": duration["export_seconds"],
                "pitch_range": _integer_range(note.pitch for note in clip.notes),
                "velocity_range": _integer_range(note.velocity for note in clip.notes),
                "timing_contract": timing,
                "export_timing": timing,
                "program": clip.instrument.program,
                "channel": clip.instrument.channel,
                "instrument": {
                    "program": clip.instrument.program,
                    "channel": clip.instrument.channel,
                    "is_drums": clip.instrument.is_drums,
                    **_suggestions_projection(clip.instrument.suggestions),
                },
                "transform": (
                    None
                    if clip.transform_recipe is None
                    else {
                        "operation": _safe_text(
                            clip.transform_recipe.operation,
                            fallback="private transform",
                            maximum=80,
                        )[0],
                        "parameters_exposed": False,
                        "seed_exposed": False,
                    }
                ),
            },
            "lineage": {
                "lineage_id": summary.lineage_id,
                "version_count": len(lineage_rows),
                "current_clip_id": requested,
                "versions": versions,
            },
            "effects": _effects(),
        }

    def prepare_artifact(
        self,
        clip_id: str,
        *,
        include_preview: bool = False,
    ) -> dict[str, Any]:
        """Build or load one content-addressed auto-timing MIDI artifact.

        The returned record intentionally includes local paths for a trusted
        Workbench server to register as capabilities.  It must never be sent to
        a browser directly; use :func:`public_artifact` for that projection.
        """

        if not isinstance(include_preview, bool):
            raise ValueError("include_preview must be a boolean")
        requested = _safe_identifier(clip_id, "clip_id")
        with self._lock:
            state = self._stable_state()
            try:
                clip = state.clips[requested]
            except KeyError as exc:
                raise KeyError("Unknown clip_id") from exc
            summary = next(row for row in state.summaries if row.clip_id == requested)
            timing_mode, timing_bpm = resolve_export_timing(
                clip,
                timing_mode="auto",
                garageband_bpm=None,
            )
            duration = _export_duration_seconds(clip, timing_mode, timing_bpm)
            if duration > _MAXIMUM_ARTIFACT_SECONDS + 1e-9:
                raise ValueError("Clip exceeds the 20 minute artifact limit")
            renderer: dict[str, Any] | None = None
            if include_preview:
                if not clip.notes:
                    raise ValueError("A neutral preview requires at least one MIDI note")
                renderer = self._renderer_inputs()
            key_payload = {
                "schema": _CLIP_ARTIFACT_MANIFEST_SCHEMA,
                "export_policy": _EXPORT_POLICY,
                "clip_id": requested,
                "clip_object_sha256": summary.object_hash,
                "library_state_sha256": state.state_sha256,
                "acceptance_result_sha256": self._acceptance.result_sha256,
                "garageband_pack_sha256": self._acceptance.pack_sha256,
                "timing": {
                    "mode": timing_mode,
                    "bpm": timing_bpm,
                    "ticks_per_beat": 480,
                },
                "preview": (
                    None
                    if renderer is None
                    else {
                        "policy": dict(_PREVIEW_POLICY),
                        "soundfont_sha256": renderer["soundfont"]["sha256"],
                        "fluidsynth_sha256": renderer["fluidsynth"]["sha256"],
                    }
                ),
            }
            artifact_id = _document_hash(key_payload)
            artifacts_root = self._cache_root / "clip-artifacts"
            _ensure_directory(artifacts_root)
            final = artifacts_root / artifact_id
            cached = _load_artifact(final, key_payload, include_preview)
            if cached is not None:
                return _internal_artifact(cached, final, cache_hit=True)

            work = Path(tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=artifacts_root))
            _chmod(work, 0o700)
            try:
                midi_path = work / "clip.mid"
                write_clip_midi(midi_path, clip, timing_mode="auto")
                _chmod(midi_path, 0o600)
                midi_record = _relative_file_record(midi_path, work)
                preview_record: dict[str, Any] | None = None
                soundfont_public: dict[str, Any] | None = None
                renderer_public: dict[str, Any] | None = None
                if renderer is not None:
                    soundfont_snapshot = work / ".verified-soundfont.sf2"
                    _verified_snapshot(
                        Path(renderer["soundfont"]["path"]),
                        renderer["soundfont"],
                        soundfont_snapshot,
                    )
                    wav_path = work / "neutral-preview.wav"
                    render_midi_to_wav(
                        midi_path,
                        wav_path,
                        sample_rate=int(_PREVIEW_POLICY["sample_rate"]),
                        gain=float(_PREVIEW_POLICY["gain"]),
                        timeout_seconds=float(_PREVIEW_POLICY["timeout_seconds"]),
                        soundfont_path=soundfont_snapshot,
                        fluidsynth_path=renderer["fluidsynth"]["path"],
                    )
                    soundfont_snapshot.unlink()
                    _chmod(wav_path, 0o600)
                    preview_record = _relative_file_record(wav_path, work)
                    soundfont_public = {
                        "bytes": renderer["soundfont"]["bytes"],
                        "sha256": renderer["soundfont"]["sha256"],
                    }
                    renderer_public = {
                        "name": "FluidSynth",
                        "sha256": renderer["fluidsynth"]["sha256"],
                        "policy": dict(_PREVIEW_POLICY),
                    }
                public = _artifact_public_projection(
                    artifact_id=artifact_id,
                    summary=summary,
                    clip=clip,
                    timing_mode=timing_mode,
                    timing_bpm=timing_bpm,
                    duration_seconds=duration,
                    midi=midi_record,
                    preview=preview_record,
                    soundfont=soundfont_public,
                    renderer=renderer_public,
                    cache_hit=False,
                )
                manifest = {
                    **key_payload,
                    "artifact_id": artifact_id,
                    "duration_seconds": duration,
                    "midi": midi_record,
                    "preview_file": preview_record,
                    "public": {key: value for key, value in public.items() if key != "cache_hit"},
                    "effects": _effects(),
                }
                _write_json(work / "manifest.json", manifest)
                _chmod(work / "manifest.json", 0o600)

                # Recheck every immutable input after rendering and before the
                # directory is published atomically.
                self._stable_state()
                if renderer is not None:
                    self._verify_renderer_inputs(renderer)
                if final.exists():
                    existing = _load_artifact(final, key_payload, include_preview)
                    if existing is None:
                        raise RuntimeError("Clip artifact cache collision is invalid")
                    shutil.rmtree(work)
                    return _internal_artifact(existing, final, cache_hit=True)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            loaded = _load_artifact(final, key_payload, include_preview)
            if loaded is None:
                raise RuntimeError("Clip artifact cache verification failed")
            return _internal_artifact(loaded, final, cache_hit=False)

    def _stable_state(self) -> _LibraryState:
        state = self._verified_current_library_state()
        if state.state_sha256 != self._library_state.state_sha256:
            raise RuntimeError("Clip library changed; restart required")
        return state

    def _verified_current_library_state(self) -> _LibraryState:
        """Re-verify the acceptance gate and current on-disk Clip inventory."""

        try:
            acceptance = _validate_acceptance(
                self._acceptance_result_path,
                self._garageband_pack_path,
            )
            if acceptance != self._acceptance:
                raise RuntimeError(
                    "Phase 5 acceptance evidence changed; restart required"
                )
            # Each verification pass intentionally uses fresh read-only SQLite
            # snapshots.  A concurrent atomic append can land between the two
            # inventory reads inside ``_capture_library_state``; retry that
            # transient observation, while persistent drift still fails closed.
            capture_error = None
            for _attempt in range(3):
                try:
                    return _capture_library_state(self._library)
                except RuntimeError as exc:
                    capture_error = exc
            assert capture_error is not None
            raise capture_error
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise RuntimeError(
                "Immutable Phase 6 evidence changed; restart required"
            ) from exc

    def _renderer_inputs(self) -> dict[str, Any]:
        if self._soundfont_record is None:
            soundfont = self._soundfont_path or _absolute(find_soundfont())
            self._soundfont_record = _input_file_record(soundfont, "SoundFont")
        if self._fluidsynth_record is None:
            fluidsynth = self._fluidsynth_path or _absolute(find_fluidsynth())
            self._fluidsynth_record = _input_file_record(
                fluidsynth,
                "FluidSynth executable",
                executable=True,
                allow_symlink=True,
            )
        renderer = {
            "soundfont": dict(self._soundfont_record),
            "fluidsynth": dict(self._fluidsynth_record),
        }
        self._verify_renderer_inputs(renderer)
        return renderer

    @staticmethod
    def _verify_renderer_inputs(renderer: Mapping[str, Any]) -> None:
        _verify_input_record(renderer["soundfont"], "SoundFont")
        _verify_input_record(
            renderer["fluidsynth"],
            "FluidSynth executable",
            executable=True,
            allow_symlink=True,
        )


def public_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Return the safe browser projection from an internal artifact record."""

    public = artifact.get("public")
    if not isinstance(public, Mapping):
        raise ValueError("Internal Clip artifact has no public projection")
    projected = json.loads(json.dumps(public, sort_keys=True))
    if _contains_key(projected, "path"):
        raise RuntimeError("Clip artifact public projection contains a path")
    return projected


def _validate_acceptance(result_path: Path, pack_path: Path) -> _AcceptanceState:
    result_record = _input_file_record(
        result_path,
        "Phase 5 acceptance result",
        maximum_bytes=_MAX_ACCEPTANCE_BYTES,
    )
    pack_record = _input_file_record(pack_path, "exact GarageBand pack")
    document = _read_json(result_path, maximum_bytes=_MAX_ACCEPTANCE_BYTES)
    if document.get("schema") != ACCEPTANCE_RESULT_SCHEMA:
        raise ValueError("Unsupported Phase 5 acceptance result schema")
    if document.get("operation") != "garageband-pack-acceptance-resolve":
        raise ValueError("Phase 5 acceptance result operation is invalid")
    if document.get("status") != "passed":
        raise ValueError("Phase 5 acceptance result has not passed")
    if document.get("phase6_read_only_clip_entry_ready") is not True:
        raise ValueError("Phase 6 read-only Clip entry is not ready")
    if document.get("explicit_hybrid_construction_ready") is not False:
        raise ValueError("Explicit hybrid construction must remain separately gated")
    if document.get("remaining_local_studio_acceptance_gates") != []:
        raise ValueError("Local Studio acceptance gates remain open")

    tutorial = document.get("tutorial")
    if (
        not isinstance(tutorial, Mapping)
        or tutorial.get("completed") is not True
        or _exact_int(tutorial.get("slide_count")) != 8
    ):
        raise ValueError("Developer tutorial evidence is incomplete")
    quiz = document.get("quiz")
    if (
        not isinstance(quiz, Mapping)
        or _exact_int(quiz.get("question_count")) != 10
        or _exact_int(quiz.get("score")) != 10
        or _exact_int(quiz.get("pass_score")) != 10
        or quiz.get("passed") is not True
    ):
        raise ValueError("Developer quiz must be passed at 10/10")

    checks = document.get("acceptance_checks")
    if not isinstance(checks, list) or len(checks) != len(_ACCEPTANCE_CHECKS):
        raise ValueError("Both named human acceptance checks are required")
    seen: set[str] = set()
    for check in checks:
        if not isinstance(check, Mapping):
            raise ValueError("Human acceptance check is invalid")
        check_id = check.get("check_id")
        if check_id not in _ACCEPTANCE_CHECKS or check_id in seen:
            raise ValueError("Human acceptance check identity is invalid")
        seen.add(str(check_id))
        if (
            check.get("outcome") != "passed"
            or _exact_int(check.get("pass_count")) != _ACCEPTANCE_CHECKS[str(check_id)]
            or _exact_int(check.get("issue_count")) != 0
            or _exact_int(check.get("cannot_tell_count")) != 0
        ):
            raise ValueError("Both human acceptance checks must pass without issues")
    if seen != set(_ACCEPTANCE_CHECKS):
        raise ValueError("Both named human acceptance checks are required")

    effects = document.get("effects")
    if not isinstance(effects, Mapping) or set(effects) != _ACCEPTANCE_EFFECT_KEYS:
        raise ValueError("Phase 5 acceptance effects are incomplete")
    if any(value is not False for value in effects.values()):
        raise ValueError("Phase 5 acceptance result declares a non-zero effect")

    expected_pack = document.get("pack")
    if not isinstance(expected_pack, Mapping):
        raise ValueError("Phase 5 acceptance result has no exact pack evidence")
    expected_hash = expected_pack.get("sha256")
    expected_bytes = _exact_int(expected_pack.get("bytes"))
    if not _is_sha256(expected_hash) or expected_bytes is None or expected_bytes < 1:
        raise ValueError("Phase 5 acceptance pack evidence is invalid")
    if (
        pack_record["sha256"] != expected_hash
        or pack_record["bytes"] != expected_bytes
    ):
        raise ValueError("GarageBand pack does not match the Phase 5 acceptance result")
    # This rechecks the ZIP member/receipt integrity without rebuilding the
    # old tutorial seed, whose code-binding correctly describes prior code.
    verify_garageband_pack_archive(pack_path)

    developer = document.get("developer_evidence")
    binding = (
        developer.get("code_binding_sha256")
        if isinstance(developer, Mapping)
        else None
    )
    if binding is not None and not _is_sha256(binding):
        raise ValueError("Developer code-binding evidence is invalid")
    return _AcceptanceState(
        result_sha256=str(result_record["sha256"]),
        result_bytes=int(result_record["bytes"]),
        pack_sha256=str(pack_record["sha256"]),
        pack_bytes=int(pack_record["bytes"]),
        developer_code_binding_sha256=None if binding is None else str(binding),
    )


def _capture_library_state(library: ClipLibrary) -> _LibraryState:
    summaries = tuple(library.list(limit=_MAX_LIBRARY_CLIPS, offset=0))
    if library.list(limit=1, offset=_MAX_LIBRARY_CLIPS):
        raise ValueError("Clip library exceeds the bounded Phase 6 inventory limit")
    clips: dict[str, MidiClip] = {}
    rows: list[dict[str, Any]] = []
    for summary in summaries:
        _validate_summary_identifiers(summary)
        object_path = library.object_path(summary.object_hash)
        _require_regular_file(object_path, "Clip object")
        if _sha256(object_path) != summary.object_hash:
            raise RuntimeError("Clip object checksum mismatch")
        clip = library.get(summary.clip_id)
        _validate_summary_matches_clip(summary, clip)
        clips[summary.clip_id] = clip
        rows.append(
            {
                "clip_id": summary.clip_id,
                "parent_clip_id": summary.parent_clip_id,
                "lineage_id": summary.lineage_id,
                "revision": summary.revision,
                "object_sha256": summary.object_hash,
                "created_at": summary.created_at,
                "canonical_sha256": hashlib.sha256(clip.canonical_bytes()).hexdigest(),
            }
        )
    second = tuple(library.list(limit=_MAX_LIBRARY_CLIPS, offset=0))
    if summaries != second:
        raise RuntimeError("Clip library changed while it was being verified")
    _validate_lineages(summaries)
    rows.sort(key=lambda row: row["clip_id"])
    return _LibraryState(
        state_sha256=_document_hash(
            {
                "schema": "sunofriend.workbench-clip-library-state.v1",
                "clips": rows,
            }
        ),
        summaries=summaries,
        clips=clips,
        lineage_count=len({summary.lineage_id for summary in summaries}),
    )


def _validate_exact_transform_append(
    before: _LibraryState,
    after: _LibraryState,
    *,
    child: MidiClip,
    child_hash: str,
    summary: ClipSummary,
) -> None:
    """Prove that an append changed nothing except the requested child row/object."""

    before_summaries = {row.clip_id: row for row in before.summaries}
    after_summaries = {row.clip_id: row for row in after.summaries}
    if any(after_summaries.get(clip_id) != row for clip_id, row in before_summaries.items()):
        raise RuntimeError("Existing Clip metadata changed during transform append")
    if any(after.clips.get(clip_id) != clip for clip_id, clip in before.clips.items()):
        raise RuntimeError("Existing immutable Clip changed during transform append")
    additions = set(after_summaries) - set(before_summaries)
    expected_additions = set() if child.clip_id in before_summaries else {child.clip_id}
    if additions != expected_additions or len(after_summaries) != len(before_summaries) + len(expected_additions):
        raise RuntimeError("Transform append changed an unexpected Clip-library row")
    if after.clips.get(child.clip_id) != child:
        raise RuntimeError("Transform append child object does not match its projection")
    actual = after_summaries.get(child.clip_id)
    if (
        actual is None
        or actual != summary
        or actual.object_hash != child_hash
        or actual.parent_clip_id != child.parent_clip_id
        or actual.revision != child.revision
    ):
        raise RuntimeError("Transform append child metadata does not match its projection")


def _validate_summary_matches_clip(summary: ClipSummary, clip: MidiClip) -> None:
    expected_key = None if clip.key is None else str(clip.key)
    if (
        clip.clip_id != summary.clip_id
        or clip.parent_clip_id != summary.parent_clip_id
        or clip.revision != summary.revision
        or clip.title != summary.title
        or expected_key != summary.key
        or clip.bpm != summary.bpm
        or clip.instrument.role != summary.role
        or clip.tags != summary.tags
        or clip.engine_version != summary.engine_version
        or hashlib.sha256(clip.canonical_bytes()).hexdigest() != summary.object_hash
    ):
        raise RuntimeError("Clip catalog metadata does not match its immutable object")


def _validate_summary_identifiers(summary: ClipSummary) -> None:
    _safe_identifier(summary.clip_id, "catalog clip_id")
    _safe_identifier(summary.lineage_id, "catalog lineage_id")
    if summary.parent_clip_id is not None:
        _safe_identifier(summary.parent_clip_id, "catalog parent_clip_id")
    if not _is_sha256(summary.object_hash):
        raise RuntimeError("Clip catalog object hash is invalid")


def _validate_lineages(summaries: Sequence[ClipSummary]) -> None:
    by_id = {row.clip_id: row for row in summaries}
    for row in summaries:
        if row.parent_clip_id is None:
            if row.revision != 1 or row.lineage_id != row.clip_id:
                raise RuntimeError("Clip root lineage metadata is inconsistent")
            continue
        parent = by_id.get(row.parent_clip_id)
        if (
            parent is None
            or parent.lineage_id != row.lineage_id
            or parent.revision + 1 != row.revision
        ):
            raise RuntimeError("Clip version lineage metadata is inconsistent")


def _summary_projection(summary: ClipSummary, clip: MidiClip) -> dict[str, Any]:
    title, title_redacted = _safe_text(clip.title, fallback="Untitled clip", maximum=120)
    role, role_redacted = _safe_role(clip.instrument.role)
    tags, tags_redacted = _safe_values(clip.tags, fallback="private tag", maximum=80)
    timing_mode, timing_bpm = resolve_export_timing(
        clip,
        timing_mode="auto",
        garageband_bpm=None,
    )
    return {
        "clip_id": summary.clip_id,
        "title": title,
        "title_redacted": title_redacted,
        "revision": summary.revision,
        "parent_clip_id": summary.parent_clip_id,
        "lineage_id": summary.lineage_id,
        "key": summary.key,
        "bpm": summary.bpm,
        "role": role,
        "role_redacted": role_redacted,
        "tags": tags,
        "tags_redacted_count": tags_redacted,
        "engine_version": _safe_text(
            summary.engine_version,
            fallback="unknown engine",
            maximum=80,
        )[0],
        "object_sha256": summary.object_hash,
        "created_at": _safe_text(
            summary.created_at,
            fallback="unknown",
            maximum=48,
        )[0],
        "note_count": len(clip.notes),
        "chord_count": len(clip.chords),
        "duration_seconds": _export_duration_seconds(
            clip,
            timing_mode,
            timing_bpm,
        ),
    }


def _lineage_projection(summary: ClipSummary, clip: MidiClip) -> dict[str, Any]:
    projection = _summary_projection(summary, clip)
    return {
        "clip_id": projection["clip_id"],
        "title": projection["title"],
        "title_redacted": projection["title_redacted"],
        "revision": projection["revision"],
        "parent_clip_id": projection["parent_clip_id"],
        "key": projection["key"],
        "bpm": projection["bpm"],
        "role": projection["role"],
        "role_redacted": projection["role_redacted"],
        "object_sha256": projection["object_sha256"],
        "transform_operation": (
            None
            if clip.transform_recipe is None
            else _safe_text(
                clip.transform_recipe.operation,
                fallback="private transform",
                maximum=80,
            )[0]
        ),
        "transform_parameters_exposed": False,
    }


def _browse_query(
    *,
    text: str | None,
    role: str | None,
    key: str | KeySignature | None,
    bpm: float | None,
    bpm_tolerance: float,
    tags: Iterable[str],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    query_text = None if text is None else _query_text(text, "text", maximum=120)
    query_role = None if role is None else _query_text(role, "role", maximum=80)
    if isinstance(key, str):
        parsed_key = KeySignature.parse(key)
    elif key is None or isinstance(key, KeySignature):
        parsed_key = key
    else:
        raise ValueError("key must be a key signature string")
    query_bpm = None if bpm is None else _positive_finite(bpm, "bpm")
    tolerance = _nonnegative_finite(bpm_tolerance, "bpm_tolerance")
    query_tags = tuple(_query_text(tag, "tag", maximum=80) for tag in tags)
    page_limit = _exact_int(limit)
    page_offset = _exact_int(offset)
    if page_limit is None or not 1 <= page_limit <= _MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {_MAX_PAGE_SIZE}")
    if page_offset is None or page_offset < 0:
        raise ValueError("offset cannot be negative")
    return {
        "text": query_text,
        "role": query_role,
        "key": None if parsed_key is None else str(parsed_key),
        "bpm": query_bpm,
        "bpm_tolerance": tolerance,
        "tags": list(query_tags),
        "limit": page_limit,
        "offset": page_offset,
    }


def _matches_query(projection: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
    text = query["text"]
    if text is not None:
        haystack = " ".join(
            [
                str(projection["title"]),
                str(projection["role"]),
                *[str(tag) for tag in projection["tags"]],
            ]
        ).casefold()
        if str(text).casefold() not in haystack:
            return False
    if query["role"] is not None and str(projection["role"]).casefold() != str(query["role"]).casefold():
        return False
    if query["key"] is not None and projection["key"] != query["key"]:
        return False
    if query["bpm"] is not None and abs(float(projection["bpm"]) - float(query["bpm"])) > float(query["bpm_tolerance"]):
        return False
    available_tags = {str(tag).casefold() for tag in projection["tags"]}
    if any(str(tag).casefold() not in available_tags for tag in query["tags"]):
        return False
    return True


def _duration_projection(
    clip: MidiClip,
    timing_mode: str,
    timing_bpm: float,
) -> dict[str, Any]:
    source_end = max(
        [0.0]
        + [note.source_end_seconds for note in clip.notes]
        + [
            chord.source_end_seconds
            if chord.source_end_seconds is not None
            else clip.tempo_map.source_seconds_at(chord.end_beat)
            for chord in clip.chords
        ]
    )
    return {
        "beats": clip.duration_beats,
        "source_end_seconds": source_end,
        "export_seconds": _export_duration_seconds(clip, timing_mode, timing_bpm),
    }


def _timing_projection(
    clip: MidiClip,
    timing_mode: str,
    timing_bpm: float,
) -> dict[str, Any]:
    return {
        "requested_mode": "auto",
        "resolved_mode": timing_mode,
        "export_bpm": timing_bpm,
        "garageband_tempo_required": timing_mode == "stem_locked",
        "tempo_point_count": len(clip.tempo_map.tempo_points),
        "warp_anchor_count": len(clip.tempo_map.warp_points),
        "time_signature": {
            "numerator": clip.time_signature.numerator,
            "denominator": clip.time_signature.denominator,
        },
    }


def _export_duration_seconds(clip: MidiClip, timing_mode: str, timing_bpm: float) -> float:
    if not clip.notes:
        return 0.0
    if timing_mode == "stem_locked":
        return max(0.0, max(note.source_end_seconds for note in clip.notes))
    zero = clip.tempo_map.musical_seconds_at(0.0)
    ends = []
    for note in clip.notes:
        grid_end = note.end_beat + clip.tempo_map.seconds_delta_to_beats(
            note.end_microtiming_seconds,
            note.end_beat,
        )
        ends.append(max(0.0, clip.tempo_map.musical_seconds_at(grid_end) - zero))
    return max(ends, default=0.0)


def _artifact_public_projection(
    *,
    artifact_id: str,
    summary: ClipSummary,
    clip: MidiClip,
    timing_mode: str,
    timing_bpm: float,
    duration_seconds: float,
    midi: Mapping[str, Any],
    preview: Mapping[str, Any] | None,
    soundfont: Mapping[str, Any] | None,
    renderer: Mapping[str, Any] | None,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "schema": CLIP_ARTIFACT_SCHEMA,
        "status": "ready",
        "artifact_id": artifact_id,
        "cache_hit": cache_hit,
        "read_only": True,
        "clip": _summary_projection(summary, clip),
        "timing_contract": _timing_projection(clip, timing_mode, timing_bpm),
        "duration_seconds": duration_seconds,
        "midi": _without_path(midi),
        "preview": None if preview is None else _without_path(preview),
        "soundfont": None if soundfont is None else dict(soundfont),
        "renderer": None if renderer is None else dict(renderer),
        "interpretation": (
            "The MIDI is a deterministic auto-timing reconstruction from the "
            "immutable Clip v1 object, not a byte-identical copy of an original "
            "import. The optional dry preview uses this exact exported MIDI."
        ),
        "effects": _effects(),
    }


def _load_artifact(
    directory: Path,
    key_payload: Mapping[str, Any],
    include_preview: bool,
) -> dict[str, Any] | None:
    if not directory.exists():
        return None
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError("Clip artifact cache entry is invalid")
    manifest_path = directory / "manifest.json"
    _require_regular_file(manifest_path, "Clip artifact manifest")
    manifest = _read_json(manifest_path, maximum_bytes=_MAX_ACCEPTANCE_BYTES)
    for key, value in key_payload.items():
        if manifest.get(key) != value:
            raise RuntimeError("Clip artifact cache manifest does not match its key")
    if manifest.get("artifact_id") != directory.name:
        raise RuntimeError("Clip artifact cache identity mismatch")
    if manifest.get("effects") != _effects():
        raise RuntimeError("Clip artifact cache declares a non-zero effect")
    midi = _verify_relative_artifact_file(directory, manifest.get("midi"), "clip.mid")
    preview_record = manifest.get("preview_file")
    if include_preview:
        preview = _verify_relative_artifact_file(
            directory,
            preview_record,
            "neutral-preview.wav",
        )
    else:
        if preview_record is not None or (directory / "neutral-preview.wav").exists():
            raise RuntimeError("MIDI-only Clip artifact unexpectedly contains a preview")
        preview = None
    expected_names = {"manifest.json", "clip.mid"}
    if include_preview:
        expected_names.add("neutral-preview.wav")
    if {item.name for item in directory.iterdir()} != expected_names:
        raise RuntimeError("Clip artifact cache member set is invalid")
    result = dict(manifest)
    result["midi"] = midi
    result["preview_file"] = preview
    return result


def _internal_artifact(
    manifest: Mapping[str, Any],
    directory: Path,
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    midi = dict(manifest["midi"])
    midi["path"] = str(directory / str(midi["name"]))
    preview = manifest.get("preview_file")
    preview_with_path = None
    if isinstance(preview, Mapping):
        preview_with_path = dict(preview)
        preview_with_path["path"] = str(directory / str(preview["name"]))
    public = dict(manifest["public"])
    public["cache_hit"] = cache_hit
    return {
        "schema": _CLIP_ARTIFACT_MANIFEST_SCHEMA,
        "artifact_id": manifest["artifact_id"],
        "cache_hit": cache_hit,
        "clip_id": manifest["clip_id"],
        "timing": dict(manifest["timing"]),
        "duration_seconds": manifest["duration_seconds"],
        "midi": midi,
        "preview": preview_with_path,
        "manifest": _file_record(directory / "manifest.json"),
        "public": public,
        "effects": _effects(),
    }


def _verify_relative_artifact_file(
    directory: Path,
    record: Any,
    expected_name: str,
) -> dict[str, Any]:
    if not isinstance(record, Mapping) or set(record) != {"name", "bytes", "sha256"}:
        raise RuntimeError("Clip artifact file record is invalid")
    if record.get("name") != expected_name:
        raise RuntimeError("Clip artifact filename is invalid")
    path = directory / expected_name
    _require_regular_file(path, "Clip artifact file")
    if path.stat().st_size != _exact_int(record.get("bytes")) or _sha256(path) != record.get("sha256"):
        raise RuntimeError("Clip artifact file changed after caching")
    return dict(record)


def _suggestions_projection(values: Iterable[str]) -> dict[str, Any]:
    suggestions, redacted = _safe_values(
        values,
        fallback="private suggestion",
        maximum=100,
    )
    return {
        "suggestions": suggestions,
        "suggestions_redacted_count": redacted,
    }


def _safe_values(
    values: Iterable[Any],
    *,
    fallback: str,
    maximum: int,
) -> tuple[list[str], int]:
    safe: list[str] = []
    redacted = 0
    for value in values:
        projected, was_redacted = _safe_text(value, fallback=fallback, maximum=maximum)
        if was_redacted:
            redacted += 1
        if projected not in safe:
            safe.append(projected)
    return safe, redacted


def _safe_role(value: Any) -> tuple[str, bool]:
    return path_free_role(value, fallback="unclassified")


def _safe_text(value: Any, *, fallback: str, maximum: int) -> tuple[str, bool]:
    if not isinstance(value, str):
        return fallback, True
    text = value.strip()
    if (
        not text
        or len(text) > maximum
        or any(ord(character) < 32 for character in text)
        or contains_local_path(text)
    ):
        return fallback, True
    return text, False


def _query_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if (
        not text
        or len(text) > maximum
        or any(ord(character) < 32 for character in text)
        or contains_local_path(text)
    ):
        raise ValueError(f"{label} must be one-line path-free text")
    return text


def _safe_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if (
        not text
        or len(text) > 128
        or any(ord(character) < 33 or ord(character) > 126 for character in text)
        or contains_local_path(text)
    ):
        raise ValueError(f"{label} must be a bounded path-free identifier")
    return text


def _integer_range(values: Iterable[int]) -> dict[str, int] | None:
    numbers = list(values)
    if not numbers:
        return None
    return {"minimum": min(numbers), "maximum": max(numbers)}


def _positive_finite(value: Any, label: str) -> float:
    number = _nonnegative_finite(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return number


def _nonnegative_finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a non-negative finite number")
    return number


def _exact_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _input_file_record(
    path: Path,
    label: str,
    *,
    maximum_bytes: int | None = None,
    executable: bool = False,
    allow_symlink: bool = False,
) -> dict[str, Any]:
    _require_regular_file(path, label, allow_symlink=allow_symlink)
    size = path.stat().st_size
    if maximum_bytes is not None and size > maximum_bytes:
        raise ValueError(f"{label} is too large")
    if executable and not os.access(path, os.X_OK):
        raise ValueError(f"{label} is not executable")
    return {"path": str(path), "bytes": size, "sha256": _sha256(path)}


def _verify_input_record(
    record: Mapping[str, Any],
    label: str,
    *,
    executable: bool = False,
    allow_symlink: bool = False,
) -> None:
    path = _absolute(str(record.get("path", "")))
    actual = _input_file_record(
        path,
        label,
        executable=executable,
        allow_symlink=allow_symlink,
    )
    if actual != dict(record):
        raise RuntimeError(f"{label} changed; retry with a fresh service")


def _verified_snapshot(source: Path, record: Mapping[str, Any], destination: Path) -> None:
    _verify_input_record(record, "SoundFont")
    digest = hashlib.sha256()
    copied = 0
    with source.open("rb") as input_handle, destination.open("xb") as output_handle:
        for block in iter(lambda: input_handle.read(_HASH_BLOCK_BYTES), b""):
            digest.update(block)
            copied += len(block)
            output_handle.write(block)
        output_handle.flush()
        os.fsync(output_handle.fileno())
    _chmod(destination, 0o600)
    if copied != record["bytes"] or digest.hexdigest() != record["sha256"]:
        destination.unlink(missing_ok=True)
        raise RuntimeError("SoundFont changed while it was being snapshotted")


def _prepare_cache_root(path: Path) -> None:
    if path.exists() and (not path.is_dir() or path.is_symlink()):
        raise ValueError("Clip artifact cache root must be a real directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _chmod(path, 0o700)


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Clip artifact cache directory is invalid")
    _chmod(path, 0o700)


def _require_regular_file(
    path: Path,
    label: str,
    *,
    allow_symlink: bool = False,
) -> None:
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise ValueError(f"{label} does not exist") from exc
    if not stat.S_ISREG(mode) or (path.is_symlink() and not allow_symlink):
        raise ValueError(f"{label} must be a regular non-symlink file")


def _read_json(path: Path, *, maximum_bytes: int) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("JSON evidence cannot be read") from exc
    if len(raw) > maximum_bytes:
        raise ValueError("JSON evidence is too large")

    def reject_constant(value: str) -> None:
        raise ValueError(f"JSON evidence contains non-finite number {value}")

    try:
        value = json.loads(raw, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON evidence is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON evidence must be an object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    path.write_bytes(payload)


def _relative_file_record(path: Path, root: Path) -> dict[str, Any]:
    if path.parent != root:
        raise RuntimeError("Clip artifact file escaped its cache directory")
    record = _file_record(path)
    return _without_path(record)


def _file_record(path: Path) -> dict[str, Any]:
    _require_regular_file(path, "generated Clip artifact")
    return {
        "path": str(path),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _without_path(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "path"}


def _effects() -> dict[str, bool]:
    return dict(_SAFE_EFFECTS)


def _contains_key(value: Any, wanted: str) -> bool:
    if isinstance(value, Mapping):
        return wanted in value or any(_contains_key(item, wanted) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, wanted) for item in value)
    return False


def _document_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_HASH_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _absolute(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _unresolved_absolute(value: str | Path) -> Path:
    return Path(os.path.abspath(Path(value).expanduser()))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError as exc:
        raise RuntimeError("Clip artifact permissions could not be restricted") from exc


__all__ = [
    "ACCEPTANCE_RESULT_SCHEMA",
    "CLIP_ARTIFACT_SCHEMA",
    "CLIP_BROWSE_SCHEMA",
    "CLIP_CAPABILITY_SCHEMA",
    "CLIP_DETAIL_SCHEMA",
    "WorkbenchClipService",
    "public_artifact",
]
