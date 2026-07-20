"""Content-addressed Workbench previews, arrangements, and DAW handoffs.

The Workbench never edits a discovered MIDI file.  These helpers create clearly
labelled audition proxies beneath the local Workbench state directory and keep
the original selected MIDI byte-for-byte in the GarageBand handoff.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import read_midi_clips
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .note_alignment import AlignmentEvent, align_events
from .render import find_soundfont, render_midi_to_wav


NEUTRAL_PREVIEW_SCHEMA = "sunofriend.workbench-neutral-preview.v1"
ARRANGEMENT_SCHEMA = "sunofriend.workbench-arrangement.v1"
GARAGEBAND_HANDOFF_SCHEMA = "sunofriend.workbench-garageband-handoff.v1"
SELECTED_MIDI_OVERLAP_SCHEMA = "sunofriend.workbench-selected-midi-overlap.v1"
_RENDER_POLICY = "role-neutral-general-midi-v1"
_OVERLAP_ONSET_TOLERANCE_SECONDS = 0.080
_SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES = 8
_SUBSTANTIAL_OVERLAP_MINIMUM_RATIO = 0.80
_DRUM_ROLES = {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums"}
_MELODIC_CHANNELS = tuple(channel for channel in range(16) if channel != 9)
_ROLE_PROGRAMS = {
    "bass": 33,
    "keys": 4,
    "piano": 0,
    "strings": 48,
    "pads": 89,
    "synth": 81,
    "lead": 81,
    "vocals": 73,
    "vocal": 73,
    "backing_vocals": 52,
    "rhythm": 27,
    "wind": 71,
}


class WorkbenchArtifacts:
    """Build and reuse immutable local artifacts for one Workbench project."""

    def __init__(
        self,
        root: str | Path,
        *,
        soundfont_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.soundfont_path = (
            Path(soundfont_path).expanduser().resolve() if soundfont_path else None
        )
        self._soundfont_cache: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def cached_candidate_preview(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_id: str,
    ) -> dict[str, Any] | None:
        stem, candidate = _candidate(catalog, stem_id, candidate_id)
        try:
            self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
        except ValueError:
            return None
        expected = {
            "source_midi_sha256": candidate["midi"]["sha256"],
            "role": stem.get("role"),
            "bpm": _project_bpm(catalog),
            "policy": _RENDER_POLICY,
        }
        soundfont_sha256 = self._available_soundfont_sha256()
        if soundfont_sha256:
            expected["soundfont_sha256"] = soundfont_sha256
        return self._find_cached("previews", NEUTRAL_PREVIEW_SCHEMA, expected)

    def render_candidate_preview(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        stem, candidate = _candidate(catalog, stem_id, candidate_id)
        if candidate.get("audition_blocked"):
            raise ValueError(
                "candidate audition is blocked because AI diagnostics found no "
                "playable evidence or an extreme decoder burst"
            )
        self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
        bpm = _project_bpm(catalog)
        role = str(stem.get("role") or "unclassified")
        soundfont = self._soundfont()
        key_payload = {
            "schema": NEUTRAL_PREVIEW_SCHEMA,
            "source_midi_sha256": candidate["midi"]["sha256"],
            "role": role,
            "bpm": bpm,
            "policy": _RENDER_POLICY,
            "soundfont_sha256": soundfont["sha256"],
        }
        cache_key = _document_hash(key_payload)
        with self._lock:
            cached = self._load_cached("previews", cache_key, NEUTRAL_PREVIEW_SCHEMA)
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            clips = read_midi_clips(candidate["midi_path"], role=role)
            notes = _clips_to_notes(clips)
            if not notes:
                raise ValueError("selected candidate MIDI contains no playable notes")
            channel = 9 if _is_drum_role(role) else 0
            program = 0 if channel == 9 else _program_for_role(role)
            tracks = [MidiTrack(_track_name(role), channel, program, notes)]
            work, final = self._building_directory("previews", cache_key)
            try:
                midi_path = work / "neutral-preview.mid"
                wav_path = work / "neutral-preview.wav"
                write_midi_file(midi_path, tracks, bpm=bpm)
                render_midi_to_wav(
                    midi_path,
                    wav_path,
                    soundfont_path=soundfont["path"],
                )
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "program": program,
                    "channel": channel,
                    "source_candidate_id": candidate_id,
                    "source_stem_id": stem_id,
                    "soundfont": _without_path(soundfont),
                    "midi": _relative_file_record(midi_path, work),
                    "preview": _relative_file_record(wav_path, work),
                    "original_midi_mutated": False,
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_cached("previews", cache_key, NEUTRAL_PREVIEW_SCHEMA)
            if result is None:
                raise RuntimeError("neutral preview cache verification failed")
            result["cache_hit"] = False
            return result

    def cached_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        selection = selected_candidates(catalog, current)
        if not selection:
            return None
        try:
            self._verify_selection(selection)
        except ValueError:
            return None
        overlap = _selected_midi_overlap(selection)
        expected = {
            "selection_sha256": _selection_hash(catalog, selection),
            "selected_midi_overlap_sha256": _document_hash(overlap),
            "bpm": _project_bpm(catalog),
            "policy": _RENDER_POLICY,
        }
        soundfont_sha256 = self._available_soundfont_sha256()
        if soundfont_sha256:
            expected["soundfont_sha256"] = soundfont_sha256
        return self._find_cached("arrangements", ARRANGEMENT_SCHEMA, expected)

    def selected_midi_overlap(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return path-free overlap evidence for the active explicit selection."""

        selection = selected_candidates(catalog, current)
        self._verify_selection(selection)
        return _selected_midi_overlap(selection)

    def render_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        selection = selected_candidates(catalog, current)
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before rendering"
            )
        self._verify_selection(selection)
        bpm = _project_bpm(catalog)
        soundfont = self._soundfont()
        selection_sha256 = _selection_hash(catalog, selection)
        overlap = _selected_midi_overlap(selection)
        key_payload = {
            "schema": ARRANGEMENT_SCHEMA,
            "selection_sha256": selection_sha256,
            "selected_midi_overlap_sha256": _document_hash(overlap),
            "bpm": bpm,
            "policy": _RENDER_POLICY,
            "soundfont_sha256": soundfont["sha256"],
        }
        cache_key = _document_hash(key_payload)
        with self._lock:
            cached = self._load_cached("arrangements", cache_key, ARRANGEMENT_SCHEMA)
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            tracks = _arrangement_tracks(selection)
            work, final = self._building_directory("arrangements", cache_key)
            try:
                midi_path = work / "selected-arrangement-proxy.mid"
                wav_path = work / "selected-arrangement-proxy.wav"
                write_midi_file(midi_path, tracks, bpm=bpm)
                render_midi_to_wav(
                    midi_path,
                    wav_path,
                    soundfont_path=soundfont["path"],
                )
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "soundfont": _without_path(soundfont),
                    "selection": _public_selection(selection),
                    "selected_midi_overlap": overlap,
                    "track_count": len(tracks),
                    "midi": _relative_file_record(midi_path, work),
                    "preview": _relative_file_record(wav_path, work),
                    "timing_policy": (
                        "source MIDI note times preserved in seconds; proxy tempo set "
                        "to the inferred project BPM"
                    ),
                    "original_midi_mutated": False,
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_cached("arrangements", cache_key, ARRANGEMENT_SCHEMA)
            if result is None:
                raise RuntimeError("arrangement cache verification failed")
            result["cache_hit"] = False
            return result

    def build_garageband_handoff(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        selection = selected_candidates(catalog, current)
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before exporting"
            )
        self._verify_selection(selection)
        overlap = _selected_midi_overlap(selection)
        unresolved_overlap = [
            pair
            for pair in overlap["pairs"]
            if pair["substantial_overlap"]
            and not pair["both_decisions_confirmed_in_full_mix"]
        ]
        if unresolved_overlap:
            raise ValueError(
                "GarageBand handoff is blocked because selected candidates derived "
                "from the same candidate-origin source audio have substantial "
                "exact-pitch/onset overlap; review and save both choices in full_mix "
                "context before exporting"
            )
        arrangement = self.render_arrangement(catalog, current)
        selection_sha256 = _selection_hash(catalog, selection)
        key_payload = {
            "schema": GARAGEBAND_HANDOFF_SCHEMA,
            "selection_sha256": selection_sha256,
            "selected_midi_overlap_sha256": _document_hash(overlap),
            "arrangement_sha256": arrangement["midi"]["sha256"],
            "arrangement_preview_sha256": arrangement["preview"]["sha256"],
        }
        cache_key = _document_hash(key_payload)
        pack_dir = self.root / "handoffs" / cache_key
        zip_path = pack_dir / "sunofriend-garageband-handoff.zip"
        manifest_path = pack_dir / "manifest.json"
        with self._lock:
            cached = self._load_handoff(zip_path, manifest_path)
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            work = pack_dir.with_name(f".{pack_dir.name}.building-{uuid.uuid4().hex}")
            _remove_generated_path(pack_dir)
            work.mkdir(parents=True, exist_ok=False)
            try:
                pack_manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "project": {
                        "project_id": catalog.get("project_id"),
                        "name": catalog.get("name"),
                        "bpm": catalog.get("setup", {}).get("bpm"),
                        "key": catalog.get("setup", {}).get("key"),
                        "tuning_hz": catalog.get("setup", {}).get("tuning_hz"),
                        "downbeat": catalog.get("setup", {}).get("downbeat"),
                    },
                    "selection": _public_selection(selection),
                    "selected_midi_overlap": overlap,
                    "selection_policy": (
                        "only the latest explicit main choice and explicit optional "
                        "choices are included"
                    ),
                    "original_midi_mutated": False,
                    "arrangement_proxy": {
                        "sha256": arrangement["midi"]["sha256"],
                        "preview_sha256": arrangement["preview"]["sha256"],
                        "policy": arrangement["policy"],
                    },
                    "private_notes_included": False,
                    "source_audio_included": False,
                }
                zip_build = work / zip_path.name
                with zipfile.ZipFile(
                    zip_build, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    _zip_text(
                        archive,
                        "README.txt",
                        _garageband_readme(catalog, len(selection)),
                    )
                    _zip_text(
                        archive,
                        "sunofriend-garageband-handoff.json",
                        json.dumps(pack_manifest, indent=2, sort_keys=True) + "\n",
                    )
                    for index, item in enumerate(selection, start=1):
                        self._verify_catalog_record(
                            item["midi"], label="selected candidate MIDI"
                        )
                        role = _safe_token(str(item["role"]))
                        decision = _safe_token(str(item["decision"]))
                        name = f"{index:02d}-{role}-{decision}.mid"
                        _zip_file(archive, f"MIDI/{name}", Path(item["midi_path"]))
                    _zip_file(
                        archive,
                        "MIDI/selected-arrangement-proxy.mid",
                        Path(arrangement["midi"]["path"]),
                    )
                    _zip_file(
                        archive,
                        "PREVIEW/selected-arrangement-proxy.wav",
                        Path(arrangement["preview"]["path"]),
                    )
                manifest = {
                    **pack_manifest,
                    "zip": _relative_file_record(zip_build, work),
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(pack_dir)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_handoff(zip_path, manifest_path)
            if result is None:
                raise RuntimeError("GarageBand handoff cache verification failed")
            result["cache_hit"] = False
            return result

    def _soundfont(self) -> dict[str, Any]:
        if self._soundfont_cache is not None:
            self._verify_catalog_record(
                self._soundfont_cache, label="SoundFont", restart_hint=True
            )
            return dict(self._soundfont_cache)
        path = self.soundfont_path or Path(find_soundfont()).resolve()
        if not path.is_file():
            raise ValueError(f"SoundFont file does not exist: {path}")
        self._soundfont_cache = _file_record(path)
        return dict(self._soundfont_cache)

    def _verify_selection(self, selection: Sequence[Mapping[str, Any]]) -> None:
        for item in selection:
            if item.get("audition_blocked"):
                reasons = ", ".join(
                    str(value) for value in item.get("block_reasons", [])
                )
                raise ValueError(
                    "a previously selected AI candidate is now diagnostic-only"
                    + (f": {reasons}" if reasons else "")
                )
            self._verify_catalog_record(item["midi"], label="selected candidate MIDI")

    def _verify_catalog_record(
        self,
        record: Mapping[str, Any],
        *,
        label: str,
        restart_hint: bool = False,
    ) -> Path:
        path = Path(str(record.get("path", ""))).resolve()
        if not path.is_file():
            raise ValueError(f"{label} no longer exists: {path}")
        stat = path.stat()
        expected_bytes = record.get("bytes")
        expected_sha256 = str(record.get("sha256", ""))
        verified = stat.st_size == expected_bytes and _sha256(path) == expected_sha256
        if not verified:
            suffix = (
                "; restart the Workbench to catalog it again" if restart_hint else ""
            )
            raise ValueError(f"{label} changed after it was catalogued{suffix}")
        return path

    def _available_soundfont_sha256(self) -> str | None:
        if self._soundfont_cache is not None or self.soundfont_path is not None:
            return str(self._soundfont()["sha256"])
        try:
            return str(self._soundfont()["sha256"])
        except (OSError, RuntimeError, ValueError):
            # A machine with no renderer/bank can still inspect existing
            # candidates. Once a bank is explicit or has been used in this
            # session, however, drift is an integrity error and is never hidden.
            return None

    def _building_directory(self, family: str, cache_key: str) -> tuple[Path, Path]:
        parent = self.root / family
        parent.mkdir(parents=True, exist_ok=True)
        final = parent / cache_key
        _remove_generated_path(final)
        work = parent / f".{cache_key}.building-{uuid.uuid4().hex}"
        work.mkdir(parents=True, exist_ok=False)
        return work, final

    def _find_cached(
        self,
        family: str,
        schema: str,
        expected: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        parent = self.root / family
        if not parent.is_dir():
            return None
        manifests = sorted(
            parent.glob("*/manifest.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for path in manifests:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if document.get("schema") != schema:
                continue
            if any(document.get(key) != value for key, value in expected.items()):
                continue
            result = self._materialize(document, path.parent)
            if result is not None:
                result["cache_hit"] = True
                return result
        return None

    def _load_cached(
        self, family: str, cache_key: str, schema: str
    ) -> dict[str, Any] | None:
        root = self.root / family / cache_key
        path = root / "manifest.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("schema") != schema or document.get("cache_key") != cache_key:
            return None
        return self._materialize(document, root)

    def _materialize(
        self, document: Mapping[str, Any], root: Path
    ) -> dict[str, Any] | None:
        result = dict(document)
        for key in ("midi", "preview"):
            record = document.get(key)
            if not isinstance(record, Mapping):
                return None
            materialized = self._materialize_file_record(record, root)
            if materialized is None:
                return None
            result[key] = materialized
        return result

    def _load_handoff(
        self, zip_path: Path, manifest_path: Path
    ) -> dict[str, Any] | None:
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("schema") != GARAGEBAND_HANDOFF_SCHEMA:
            return None
        record = document.get("zip")
        if not isinstance(record, Mapping):
            return None
        materialized = self._materialize_file_record(record, manifest_path.parent)
        if materialized is None or materialized["path"] != str(zip_path):
            return None
        result = dict(document)
        result["zip"] = materialized
        return result

    def _materialize_file_record(
        self, record: Mapping[str, Any], root: Path
    ) -> dict[str, Any] | None:
        path = (root / str(record.get("path", ""))).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return None
        if not path.is_file() or path.stat().st_size != record.get("bytes"):
            return None
        verified = _sha256(path) == record.get("sha256")
        if not verified:
            return None
        result = dict(record)
        result["path"] = str(path)
        return result


def selected_candidates(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Resolve only active explicit main and explicit optional choices."""

    states = current.get("stems", {})
    selected: list[dict[str, Any]] = []
    for stem in catalog.get("stems", []):
        stem_id = str(stem["stem_id"])
        state = states.get(stem_id, {})
        main_id = state.get("main_candidate_id")
        decisions = state.get("candidates", {})
        role = str(state.get("role") or stem.get("role") or "unclassified")
        for candidate in stem.get("candidates", []):
            candidate_id = str(candidate["candidate_id"])
            decision = decisions.get(candidate_id, {})
            value = decision.get("decision")
            if not (
                (value == "main" and candidate_id == main_id) or value == "optional"
            ):
                continue
            ai_diagnostics = candidate.get("ai_diagnostics") or {}
            candidate_origin_sha256 = ai_diagnostics.get("source_audio_sha256")
            if candidate_origin_sha256:
                candidate_origin_basis = "verified-ai-source"
            else:
                candidate_origin_sha256 = stem["source"]["sha256"]
                candidate_origin_basis = "review-stem-source-fallback"
            selected.append(
                {
                    "stem_id": stem_id,
                    "stem_label": stem.get("label"),
                    "candidate_id": candidate_id,
                    "candidate_label": candidate.get("label"),
                    "process": candidate.get("process"),
                    "role": role,
                    "decision": value,
                    "decision_context": decision.get("context"),
                    "candidate_origin_source_audio_sha256": (candidate_origin_sha256),
                    "candidate_origin_source_audio_sha256_basis": (
                        candidate_origin_basis
                    ),
                    "audition_blocked": bool(candidate.get("audition_blocked")),
                    "block_reasons": list(
                        (candidate.get("ai_diagnostics") or {}).get("block_reasons", [])
                    ),
                    "midi_path": candidate["midi_path"],
                    "midi": dict(candidate["midi"]),
                }
            )
    return selected


def _arrangement_tracks(selection: Sequence[Mapping[str, Any]]) -> list[MidiTrack]:
    drum_notes: list[NoteEvent] = []
    melodic: list[tuple[Mapping[str, Any], list[NoteEvent]]] = []
    for item in selection:
        clips = read_midi_clips(item["midi_path"], role=str(item["role"]))
        notes = _clips_to_notes(clips)
        if not notes:
            continue
        if _is_drum_role(str(item["role"])):
            drum_notes.extend(notes)
        else:
            melodic.append((item, notes))
    if len(melodic) > len(_MELODIC_CHANNELS):
        raise ValueError(
            "the proxy arrangement supports at most 15 selected pitched parts; "
            "mark fewer alternatives optional"
        )
    tracks: list[MidiTrack] = []
    if drum_notes:
        tracks.append(MidiTrack("Selected drums", 9, 0, drum_notes))
    for channel, (item, notes) in zip(_MELODIC_CHANNELS, melodic):
        role = str(item["role"])
        decision = str(item["decision"])
        tracks.append(
            MidiTrack(
                f"{_track_name(role)} ({decision})",
                channel,
                _program_for_role(role),
                notes,
            )
        )
    if not tracks:
        raise ValueError("the selected MIDI files contain no playable notes")
    return tracks


def _clips_to_notes(clips: Sequence[Any]) -> list[NoteEvent]:
    notes = []
    for clip in clips:
        for note in clip.notes:
            notes.append(
                NoteEvent(
                    start=float(note.source_start_seconds),
                    end=float(note.source_end_seconds),
                    pitch=int(note.pitch),
                    velocity=int(note.velocity),
                )
            )
    return sorted(notes, key=lambda note: (note.start, note.pitch, note.end))


def _candidate(
    catalog: Mapping[str, Any], stem_id: str, candidate_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    for stem in catalog.get("stems", []):
        if stem.get("stem_id") != stem_id:
            continue
        for candidate in stem.get("candidates", []):
            if candidate.get("candidate_id") == candidate_id:
                return stem, candidate
        raise ValueError("candidate_id does not belong to the selected stem")
    raise ValueError("unknown workbench stem_id")


def _project_bpm(catalog: Mapping[str, Any]) -> float:
    value = catalog.get("setup", {}).get("bpm")
    if value is None:
        raise ValueError(
            "the Workbench needs an inferred project BPM to render aligned previews"
        )
    bpm = float(value)
    if not 1.0 <= bpm <= 1000.0:
        raise ValueError("project BPM must be between 1 and 1000")
    return bpm


def _program_for_role(role: str) -> int:
    return _ROLE_PROGRAMS.get(role.lower(), 0)


def _is_drum_role(role: str) -> bool:
    return role.lower() in _DRUM_ROLES


def _track_name(role: str) -> str:
    return "Neutral " + role.replace("_", " ").strip().title()


def _selection_hash(
    catalog: Mapping[str, Any], selection: Sequence[Mapping[str, Any]]
) -> str:
    return _document_hash(
        {
            "project_id": catalog.get("project_id"),
            "bpm": catalog.get("setup", {}).get("bpm"),
            "selection": [
                {
                    **row,
                    "decision_context": item.get("decision_context"),
                }
                for item, row in zip(selection, _public_selection(selection))
            ],
        }
    )


def _selected_midi_overlap(
    selection: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare same-origin selected MIDI as bounded listening diagnostics only."""

    note_cache: dict[str, list[NoteEvent]] = {}

    def notes_for(item: Mapping[str, Any]) -> list[NoteEvent]:
        midi_sha256 = str(item["midi"]["sha256"])
        if midi_sha256 not in note_cache:
            clips = read_midi_clips(item["midi_path"], role=str(item["role"]))
            note_cache[midi_sha256] = _clips_to_notes(clips)
        return note_cache[midi_sha256]

    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(selection):
        for right in selection[left_index + 1 :]:
            candidate_origin_sha256 = str(
                left.get("candidate_origin_source_audio_sha256") or ""
            )
            if not candidate_origin_sha256 or candidate_origin_sha256 != right.get(
                "candidate_origin_source_audio_sha256"
            ):
                continue
            left_notes = notes_for(left)
            right_notes = notes_for(right)
            matched_note_count = _greedy_exact_pitch_onset_matches(
                left_notes,
                right_notes,
                tolerance_seconds=_OVERLAP_ONSET_TOLERANCE_SECONDS,
            )
            left_ratio = matched_note_count / len(left_notes) if left_notes else 0.0
            right_ratio = matched_note_count / len(right_notes) if right_notes else 0.0
            substantial = (
                matched_note_count >= _SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES
                and left_ratio >= _SUBSTANTIAL_OVERLAP_MINIMUM_RATIO
                and right_ratio >= _SUBSTANTIAL_OVERLAP_MINIMUM_RATIO
            )
            left_context = left.get("decision_context")
            right_context = right.get("decision_context")
            pairs.append(
                {
                    "candidate_origin_source_audio_sha256": (candidate_origin_sha256),
                    "left": {
                        "stem_id": left["stem_id"],
                        "candidate_id": left["candidate_id"],
                        "midi_sha256": left["midi"]["sha256"],
                        "decision_context": left_context,
                        "candidate_origin_source_audio_sha256_basis": left.get(
                            "candidate_origin_source_audio_sha256_basis"
                        ),
                    },
                    "right": {
                        "stem_id": right["stem_id"],
                        "candidate_id": right["candidate_id"],
                        "midi_sha256": right["midi"]["sha256"],
                        "decision_context": right_context,
                        "candidate_origin_source_audio_sha256_basis": right.get(
                            "candidate_origin_source_audio_sha256_basis"
                        ),
                    },
                    "left_note_count": len(left_notes),
                    "right_note_count": len(right_notes),
                    "matched_note_count": matched_note_count,
                    "left_overlap_ratio": round(left_ratio, 6),
                    "right_overlap_ratio": round(right_ratio, 6),
                    "substantial_overlap": substantial,
                    "both_decisions_confirmed_in_full_mix": (
                        left_context == "full_mix" and right_context == "full_mix"
                    ),
                }
            )
    return {
        "schema": SELECTED_MIDI_OVERLAP_SCHEMA,
        "heuristic": {
            "policy": "greedy-earliest-compatible-exact-pitch-onset-v1",
            "onset_tolerance_ms": 80,
            "minimum_matched_notes_for_substantial": (
                _SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES
            ),
            "minimum_overlap_ratio_for_each_candidate": (
                _SUBSTANTIAL_OVERLAP_MINIMUM_RATIO
            ),
        },
        "same_candidate_origin_pair_count": len(pairs),
        "substantial_overlap_pair_count": sum(
            1 for pair in pairs if pair["substantial_overlap"]
        ),
        "unconfirmed_substantial_overlap_pair_count": sum(
            1
            for pair in pairs
            if pair["substantial_overlap"]
            and not pair["both_decisions_confirmed_in_full_mix"]
        ),
        "pairs": pairs,
        "interpretation": (
            "diagnostic only: candidates are grouped by verified AI source audio, "
            "or by review-stem source for non-AI fallback; overlap does not establish "
            "accuracy, role separation, or preference and never changes a selection"
        ),
    }


def _greedy_exact_pitch_onset_matches(
    left: Sequence[NoteEvent],
    right: Sequence[NoteEvent],
    *,
    tolerance_seconds: float,
) -> int:
    """Count deterministic earliest-compatible matches within each exact pitch."""

    result = align_events(
        [
            AlignmentEvent(
                source_index=index,
                onset=note.start,
                pitch=note.pitch,
            )
            for index, note in enumerate(left)
        ],
        [
            AlignmentEvent(
                source_index=index,
                onset=note.start,
                pitch=note.pitch,
            )
            for index, note in enumerate(right)
        ],
        left_offset=0.0,
        right_offset=0.0,
        tolerance=tolerance_seconds,
        pitch_policy="exact_integer",
        require_exact_label=False,
    )
    return len(result.matches)


def _public_selection(selection: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stem_id": item["stem_id"],
            "candidate_id": item["candidate_id"],
            "role": item["role"],
            "decision": item["decision"],
            "process": item.get("process"),
            "midi_sha256": item["midi"]["sha256"],
            "midi_bytes": item["midi"]["bytes"],
            "candidate_origin_source_audio_sha256": item.get(
                "candidate_origin_source_audio_sha256"
            ),
            "candidate_origin_source_audio_sha256_basis": item.get(
                "candidate_origin_source_audio_sha256_basis"
            ),
        }
        for item in selection
    ]


def _garageband_readme(catalog: Mapping[str, Any], count: int) -> str:
    setup = catalog.get("setup", {})
    downbeat = setup.get("downbeat")
    return (
        "Sunofriend GarageBand handoff\n"
        "================================\n\n"
        f"Project: {catalog.get('name')}\n"
        f"Selected parts: {count}\n"
        f"Set GarageBand tempo to: {setup.get('bpm')} BPM\n"
        f"Project key: {setup.get('key') or 'not inferred'}\n"
        f"Source tuning: {setup.get('tuning_hz') or 'not inferred'} Hz\n"
        f"Downbeat: {downbeat if downbeat is not None else 'not confirmed'}\n\n"
        "1. Create or open a GarageBand project and set the tempo above before import.\n"
        "2. Drag each file in MIDI/ onto its own Software Instrument track.\n"
        "3. Choose a playable GarageBand patch for each track in the Library.\n"
        "4. Use selected-arrangement-proxy.mid only as a convenience full-mix audition.\n"
        "5. The numbered MIDI files are byte-for-byte copies of your explicit choices; "
        "they are the authoritative handoff.\n\n"
        "The proxy WAV uses one consistent local GM SoundFont and role-based programs. "
        "It is not a claim that those are the final GarageBand instruments.\n"
    )


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _relative_file_record(path: Path, root: Path) -> dict[str, Any]:
    record = _file_record(path)
    record["path"] = str(path.relative_to(root))
    return record


def _without_path(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "path"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    data = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _remove_generated_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _safe_token(value: str) -> str:
    token = "-".join(value.lower().replace("_", " ").split())
    return "".join(char for char in token if char.isalnum() or char == "-") or "part"


def _zip_text(archive: zipfile.ZipFile, name: str, value: str) -> None:
    _zip_bytes(archive, name, value.encode("utf-8"))


def _zip_file(archive: zipfile.ZipFile, name: str, source: Path) -> None:
    _zip_bytes(archive, name, source.read_bytes())


def _zip_bytes(archive: zipfile.ZipFile, name: str, value: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, value)


__all__ = [
    "ARRANGEMENT_SCHEMA",
    "GARAGEBAND_HANDOFF_SCHEMA",
    "NEUTRAL_PREVIEW_SCHEMA",
    "SELECTED_MIDI_OVERLAP_SCHEMA",
    "WorkbenchArtifacts",
    "selected_candidates",
]
