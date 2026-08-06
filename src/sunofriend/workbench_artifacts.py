"""Content-addressed Workbench previews, arrangements, and DAW handoffs.

The Workbench never edits a discovered MIDI file.  These helpers create clearly
labelled audition proxies beneath the local Workbench state directory and keep
the original selected MIDI byte-for-byte in the GarageBand handoff.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import stat
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import read_midi_clips
from .garageband_pack_acceptance import (
    create_garageband_pack_acceptance_review,
    verify_garageband_pack_acceptance_artifacts,
    verify_garageband_pack_archive,
)
from .instrument_catalog import starter_program_for_role
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .note_alignment import AlignmentEvent, align_events
from .render import find_soundfont, render_midi_to_wav
from .role_semantics import is_drum_role
from .workbench_balanced_contract import BALANCED_MIX_CONTRACT
from .workbench_mix import (
    BALANCED_ARRANGEMENT_SCHEMA,
    BALANCED_MIX_POLICY,
    BALANCED_MIX_REPORT_SCHEMA,
    build_balanced_midi_audition,
    garageband_mix_recipe,
    measure_balanced_audio,
)
from .workbench_instrument_policy import (
    complete_instrument_programs,
    complete_instrument_roles,
)
from .workbench_privacy import path_free_role
from .workbench_semantics import terminal_no_selection_outcome


NEUTRAL_PREVIEW_SCHEMA = "sunofriend.workbench-neutral-preview.v1"
DECODED_STEM_LOOP_SCHEMA = "sunofriend.workbench-decoded-stem-loop.v1"
ARRANGEMENT_SELECTION_SCHEMA = "sunofriend.workbench-arrangement-selection.v1"
INSTRUMENT_REVIEW_CONTEXT_SCHEMA = "sunofriend.workbench-instrument-review.context.v1"
DECODED_ARRANGEMENT_LOOP_SCHEMA = "sunofriend.workbench-decoded-arrangement-loop.v1"
DECODED_ARRANGEMENT_STREAM_SCHEMA = "sunofriend.workbench-decoded-arrangement-stream.v1"
DECODED_ARRANGEMENT_CHUNK_SCHEMA = "sunofriend.workbench-decoded-arrangement-chunk.v1"
ARRANGEMENT_SCHEMA = "sunofriend.workbench-arrangement.v1"
GARAGEBAND_HANDOFF_SCHEMA = "sunofriend.workbench-garageband-handoff.v1"
GARAGEBAND_PACK_PLAN_SCHEMA = "sunofriend.workbench-garageband-pack-plan.v1"
GARAGEBAND_PACK_BASKET_SCHEMA = "sunofriend.workbench-garageband-pack-basket.v1"
GARAGEBAND_PACK_SCHEMA = "sunofriend.workbench-garageband-pack.v1"
SELECTED_MIDI_OVERLAP_SCHEMA = "sunofriend.workbench-selected-midi-overlap.v1"
_RENDER_POLICY = "role-neutral-general-midi-v3"
_DECODED_LOOP_POLICY = "recorded-zero-source-frame-window-level-matched-v2"
_DECODED_STEM_LEVEL_POLICY = "common-target-active-block-rms-v1"
_DECODED_ARRANGEMENT_LOOP_POLICY = "recorded-zero-selected-arrangement-window-v1"
_DECODED_ARRANGEMENT_STREAM_POLICY = (
    "recorded-zero-selected-arrangement-chunk-stream-v1"
)
_DECODED_LOOP_MINIMUM_SECONDS = 0.5
_DECODED_LOOP_MAXIMUM_SECONDS = 15.0
_DECODED_LOOP_MAXIMUM_CANDIDATES = 6
_DECODED_ARRANGEMENT_MAXIMUM_TRACKS = 24
_DECODED_ARRANGEMENT_STREAM_PRESETS = frozenset(
    {"source-only", "selected-midi", "hybrid", "main-only"}
)
_DECODED_STREAM_MAXIMUM_SECONDS = 20 * 60
_DECODED_STREAM_MAXIMUM_CHUNK_SECONDS = 5
_DECODED_STREAM_MAXIMUM_CHUNKS = 480
_DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES = 32 * 1024 * 1024
_DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES = 192 * 1024 * 1024
_DECODED_STREAM_CACHE_MAXIMUM_BYTES = 2 * 1024 * 1024 * 1024
_DECODED_STREAM_CACHE_MAXIMUM_ENTRIES = 8
_BALANCED_CACHE_MAXIMUM_BYTES = 2 * 1024 * 1024 * 1024
_BALANCED_CACHE_MAXIMUM_ENTRIES = 8
_BALANCED_DEFERRED_CACHE_SCHEMA = "sunofriend.workbench-balanced-deferred-cache.v1"
_BALANCED_DEFERRED_MARKER_NAME = ".deferred-cache.json"
_BALANCED_DEFERRED_MAXIMUM_CLAIMS = 1024
_BALANCED_DEFERRED_STALE_SECONDS = 6 * 60 * 60
_BALANCED_RENDER_HORIZON_POLICY = BALANCED_MIX_CONTRACT.render_horizon_policy
_BALANCED_MIX_RECEIPT_SCHEMA = BALANCED_MIX_CONTRACT.receipt_schema
_BALANCED_RENDERER_BACKEND = BALANCED_MIX_CONTRACT.renderer_backend
_BALANCED_MIX_LABEL = BALANCED_MIX_CONTRACT.label
_BALANCED_MASTERING_BOUNDARY = BALANCED_MIX_CONTRACT.mastering_boundary
_BALANCED_WINDOW_SECONDS = BALANCED_MIX_CONTRACT.window_seconds
_BALANCED_SOURCE_MATCH_GAIN_DB = BALANCED_MIX_CONTRACT.source_match_gain_db
_BALANCED_DRUM_OVERLAP_MEDIAN_TARGET_DB = (
    BALANCED_MIX_CONTRACT.drum_overlap_median_target_db
)
_BALANCED_DRUM_OVERLAP_P95_MAXIMUM_DB = (
    BALANCED_MIX_CONTRACT.drum_overlap_p95_maximum_db
)
_BALANCED_MAXIMUM_DRUM_ATTENUATION_DB = (
    BALANCED_MIX_CONTRACT.maximum_drum_bus_attenuation_db
)
_BALANCED_AUDITION_TARGET_GATED_RMS_DBFS = (
    BALANCED_MIX_CONTRACT.audition_target_gated_rms_dbfs
)
_BALANCED_SAMPLE_PEAK_CEILING_DBFS = BALANCED_MIX_CONTRACT.sample_peak_ceiling_dbfs
_BALANCED_MAXIMUM_NORMALISATION_BOOST_DB = (
    BALANCED_MIX_CONTRACT.maximum_normalisation_boost_db
)
_BALANCED_NORMALISATION_TARGET_TOLERANCE_DB = (
    BALANCED_MIX_CONTRACT.normalisation_target_tolerance_db
)
_BALANCED_MEASUREMENT_STATISTIC = BALANCED_MIX_CONTRACT.measurement_statistic
_BALANCED_MEASUREMENT_PEAK_KIND = BALANCED_MIX_CONTRACT.measurement_peak_kind
_BALANCED_DRUM_GUARD_POLICY = BALANCED_MIX_CONTRACT.drum_guard_policy
_VERIFIED_STREAM_CACHE_MAXIMUM_ENTRIES = 8
_DECODED_LOOP_MAXIMUM_OUTPUT_BYTES = 64 * 1024 * 1024
_DECODED_LOOP_MAXIMUM_INPUT_BYTES = 2 * 1024 * 1024 * 1024
_DECODED_LOOP_CACHE_MAXIMUM_BYTES = 256 * 1024 * 1024
_DECODED_LOOP_CACHE_MAXIMUM_ENTRIES = 32
_DECODED_LOOP_BUILDING_MAXIMUM_AGE_SECONDS = 6 * 60 * 60
_DECODED_LOOP_MAXIMUM_START_SECONDS = 24 * 60 * 60
_DECODED_LOOP_MINIMUM_SAMPLE_RATE = 8_000
_DECODED_LOOP_MAXIMUM_SAMPLE_RATE = 96_000
_DECODED_PCM16_WAV_HEADER_BUDGET_BYTES = 4 * 1024
_NEUTRAL_PREVIEW_MAXIMUM_SECONDS = 20 * 60
_OVERLAP_ONSET_TOLERANCE_SECONDS = 0.080
_SUBSTANTIAL_OVERLAP_MINIMUM_MATCHED_NOTES = 8
_SUBSTANTIAL_OVERLAP_MINIMUM_RATIO = 0.80
_MELODIC_CHANNELS = tuple(channel for channel in range(16) if channel != 9)
class WorkbenchPackConflictError(ValueError):
    """The requested pack no longer describes the current Workbench state."""


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
        self._verified_stream_cache: dict[str, dict[str, Any]] = {}
        self._verified_balanced_cache: dict[str, dict[str, Any]] = {}
        self._balanced_live_deferred_cache_keys: set[str] = set()
        self._lock = threading.RLock()

    def developer_verified_stream_entry_count(self) -> int:
        """Return one path-free in-memory cache count for the opt-in inspector."""

        with self._lock:
            return len(self._verified_stream_cache)

    def cached_candidate_preview(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_id: str,
        *,
        role_override: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            stem, candidate = _candidate(catalog, stem_id, candidate_id)
            try:
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
            except ValueError:
                return None
            expected = {
                "source_midi_sha256": candidate["midi"]["sha256"],
                "role": _preview_role(stem, role_override),
                "bpm": _project_bpm(catalog),
                "policy": _RENDER_POLICY,
            }
            soundfont_sha256 = self._available_soundfont_sha256()
            if not soundfont_sha256:
                return None
            expected["soundfont_sha256"] = soundfont_sha256
            return self._find_cached("previews", NEUTRAL_PREVIEW_SCHEMA, expected)

    def render_candidate_preview(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_id: str,
        *,
        role_override: str | None = None,
    ) -> dict[str, Any]:
        stem, candidate = _candidate(catalog, stem_id, candidate_id)
        if candidate.get("audition_blocked"):
            raise ValueError(
                "candidate audition is blocked because AI diagnostics found no "
                "playable evidence or an extreme decoder burst"
            )
        self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
        bpm = _project_bpm(catalog)
        role = _preview_role(stem, role_override)
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
            channel = 9 if is_drum_role(role) else 0
            program = 0 if channel == 9 else _program_for_role(role)
            work, final = self._building_directory("previews", cache_key)
            _restrict_private_permissions(work, 0o700)
            try:
                source_midi = _write_verified_private_snapshot(
                    Path(str(candidate["midi_path"])),
                    candidate["midi"],
                    work / ".verified-source.mid",
                    label="candidate MIDI",
                )
                source_soundfont = _write_verified_private_snapshot(
                    Path(str(soundfont["path"])),
                    soundfont,
                    work / ".verified-soundfont.sf2",
                    label="SoundFont",
                )
                clips = read_midi_clips(source_midi, role=role)
                notes = _clips_to_notes(clips)
                if not notes:
                    raise ValueError(
                        "selected candidate MIDI contains no playable notes"
                    )
                if max(note.end for note in notes) > _NEUTRAL_PREVIEW_MAXIMUM_SECONDS:
                    raise ValueError(
                        "selected candidate MIDI exceeds the 20 minute neutral-preview "
                        "rendering limit"
                    )
                tracks = [MidiTrack(_track_name(role), channel, program, notes)]
                midi_path = work / "neutral-preview.mid"
                wav_path = work / "neutral-preview.wav"
                write_midi_file(midi_path, tracks, bpm=bpm)
                render_midi_to_wav(
                    midi_path,
                    wav_path,
                    soundfont_path=source_soundfont,
                )
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
                self._verify_catalog_record(
                    soundfont,
                    label="SoundFont",
                    restart_hint=True,
                )
                source_midi.unlink()
                source_soundfont.unlink()
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "program": program,
                    "program_label": _program_label(role, program, channel),
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

    def prepare_decoded_stem_loop(
        self,
        catalog: Mapping[str, Any],
        stem_id: str,
        candidate_ids: Sequence[str],
        start_seconds: float,
        end_seconds: float,
    ) -> dict[str, Any]:
        """Build private PCM16 source/candidate windows for decoded switching."""

        start, end = _decoded_loop_window(start_seconds, end_seconds)
        requested_ids = _decoded_loop_candidate_ids(candidate_ids)
        stem = _stem(catalog, stem_id)
        source_record = stem.get("source")
        if not isinstance(source_record, Mapping):
            raise ValueError("selected stem has no catalogued source audio")

        candidates: list[Mapping[str, Any]] = []
        for candidate_id in requested_ids:
            _, candidate = _candidate(catalog, stem_id, candidate_id)
            if candidate.get("audition_blocked"):
                raise ValueError(
                    "candidate audition is blocked because AI diagnostics found no "
                    "playable evidence or an extreme decoder burst"
                )
            candidates.append(candidate)

        with self._lock:
            declared_input_bytes = _decoded_declared_input_bytes(
                [("source audio", source_record)]
                + [
                    ("candidate MIDI", candidate.get("midi"))
                    for candidate in candidates
                ]
            )
            _require_decoded_input_limit(declared_input_bytes)
            if self._soundfont_cache is not None:
                soundfont_size = _decoded_declared_input_bytes(
                    [("SoundFont", self._soundfont_cache)]
                )
            else:
                soundfont_path = self.soundfont_path or Path(find_soundfont()).resolve()
                try:
                    soundfont_size = soundfont_path.stat().st_size
                except OSError as exc:
                    raise ValueError(
                        f"SoundFont file does not exist: {soundfont_path}"
                    ) from exc
            _require_decoded_input_limit(declared_input_bytes + soundfont_size)

            source_path = self._verify_catalog_record(
                source_record, label="source audio"
            )
            for candidate in candidates:
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
            soundfont_record = self._soundfont()
            pre_render_input_bytes = _decoded_declared_input_bytes(
                [("source audio", source_record), ("SoundFont", soundfont_record)]
                + [
                    ("candidate MIDI", candidate.get("midi"))
                    for candidate in candidates
                ]
            )
            _require_decoded_input_limit(pre_render_input_bytes)
            np, soundfile = _decoded_audio_modules()
            required_soundfont_sha256 = str(soundfont_record["sha256"])

            previews: list[dict[str, Any]] = []
            for candidate_id in requested_ids:
                preview = self.cached_candidate_preview(catalog, stem_id, candidate_id)
                if preview is None:
                    preview = self.render_candidate_preview(
                        catalog, stem_id, candidate_id
                    )
                previews.append(preview)
            self._require_preview_renderer_consistency(
                previews,
                expected_soundfont_sha256=required_soundfont_sha256,
            )

            # Rendering a missing neutral preview can take long enough for an input
            # to change. Recheck all original inputs before reading any audio.
            source_path = self._verify_catalog_record(
                source_record, label="source audio"
            )
            for candidate in candidates:
                self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
            preview_paths = [
                self._verify_catalog_record(
                    preview["preview"], label="neutral candidate preview"
                )
                for preview in previews
            ]
            aggregate_input_bytes = pre_render_input_bytes + sum(
                int(preview["preview"]["bytes"]) for preview in previews
            )
            _require_decoded_input_limit(aggregate_input_bytes)

            source_info = _decoded_audio_info(
                soundfile, source_path, label="source audio"
            )
            source_start_frame = _nearest_audio_frame(start, source_info["sample_rate"])
            source_end_frame = _nearest_audio_frame(end, source_info["sample_rate"])
            if source_end_frame <= source_start_frame:
                raise ValueError("decoded loop window contains no source audio frames")
            quantized_start = source_start_frame / source_info["sample_rate"]
            quantized_end = source_end_frame / source_info["sample_rate"]

            inputs: list[dict[str, Any]] = [
                {
                    "track_id": "source",
                    "kind": "source",
                    "input_path": source_path,
                    "input_sha256": str(source_record["sha256"]),
                    "input_bytes": int(source_record["bytes"]),
                    "sample_rate": source_info["sample_rate"],
                    "channels": source_info["channels"],
                    "input_frames": source_info["frames"],
                    "start_frame": source_start_frame,
                    "end_frame": source_end_frame,
                }
            ]
            for index, (candidate_id, candidate, preview, preview_path) in enumerate(
                zip(requested_ids, candidates, previews, preview_paths),
                start=1,
            ):
                info = _decoded_audio_info(
                    soundfile,
                    preview_path,
                    label=f"neutral candidate preview {index}",
                )
                candidate_start = _nearest_audio_frame(
                    quantized_start, info["sample_rate"]
                )
                candidate_end = _nearest_audio_frame(quantized_end, info["sample_rate"])
                if candidate_end <= candidate_start:
                    raise ValueError(
                        "decoded loop window contains no candidate preview frames"
                    )
                inputs.append(
                    {
                        "track_id": f"candidate-{index}",
                        "kind": "candidate",
                        "candidate_id": candidate_id,
                        "input_path": preview_path,
                        "input_sha256": str(preview["preview"]["sha256"]),
                        "input_bytes": int(preview["preview"]["bytes"]),
                        "source_midi_sha256": str(candidate["midi"]["sha256"]),
                        "neutral_preview_cache_key": str(preview["cache_key"]),
                        "neutral_preview_policy": str(preview["policy"]),
                        "soundfont_sha256": str(preview["soundfont_sha256"]),
                        "sample_rate": info["sample_rate"],
                        "channels": info["channels"],
                        "input_frames": info["frames"],
                        "start_frame": candidate_start,
                        "end_frame": candidate_end,
                    }
                )

            input_fingerprints = [
                {key: value for key, value in item.items() if key != "input_path"}
                for item in inputs
            ]
            key_payload = {
                "schema": DECODED_STEM_LOOP_SCHEMA,
                "project_id": catalog.get("project_id"),
                "stem_id": stem_id,
                "candidate_ids": list(requested_ids),
                "window": {
                    "source_start_frame": source_start_frame,
                    "source_end_frame": source_end_frame,
                    "quantized_start_seconds": quantized_start,
                    "quantized_end_seconds": quantized_end,
                    "logical_duration_seconds": quantized_end - quantized_start,
                },
                "input_fingerprints": input_fingerprints,
                "policy": _DECODED_LOOP_POLICY,
                "renderer": {
                    "policy": _RENDER_POLICY,
                    "soundfont_sha256": required_soundfont_sha256,
                },
                "encoding": {
                    "container": "WAV",
                    "subtype": "PCM_16",
                    "sample_rate_policy": "preserve each decoded input rate",
                    "channel_policy": "preserve mono or stereo",
                },
                "audition_level": {
                    "policy": _DECODED_STEM_LEVEL_POLICY,
                    "target_gated_rms_dbfs": (_BALANCED_AUDITION_TARGET_GATED_RMS_DBFS),
                    "sample_peak_ceiling_dbfs": (_BALANCED_SAMPLE_PEAK_CEILING_DBFS),
                    "maximum_positive_boost_db": (
                        _BALANCED_MAXIMUM_NORMALISATION_BOOST_DB
                    ),
                    "minimum_gain_db": _BALANCED_SOURCE_MATCH_GAIN_DB[0],
                    "measurement_statistic": _BALANCED_MEASUREMENT_STATISTIC,
                    "peak_kind": _BALANCED_MEASUREMENT_PEAK_KIND,
                    "boundary": (
                        "gain-only private audition matching; source, preview "
                        "audio and MIDI remain unchanged; not mastering"
                    ),
                },
                "resource_limits": {
                    "aggregate_input_bytes": aggregate_input_bytes,
                    "maximum_input_bytes": _DECODED_LOOP_MAXIMUM_INPUT_BYTES,
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                },
            }
            cache_key = _document_hash(key_payload)
            cached = self._load_decoded_stem_loop(cache_key, key_payload)
            if cached is not None:
                self._verify_decoded_loop_inputs(
                    source_record=source_record,
                    candidates=candidates,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                self._touch_and_prune_decoded_loop_cache(cache_key)
                cached["cache_hit"] = True
                return cached

            work, final = self._private_building_directory(
                "decoded-stem-loops", cache_key
            )
            try:
                decode_paths = [
                    _write_verified_private_snapshot(
                        Path(item["input_path"]),
                        source_record if index == 0 else previews[index - 1]["preview"],
                        work / f".verified-input-{index:02d}",
                        label=(
                            "source audio"
                            if index == 0
                            else f"neutral candidate preview {index}"
                        ),
                    )
                    for index, item in enumerate(inputs)
                ]
                for index, (item, decode_path) in enumerate(zip(inputs, decode_paths)):
                    snapshot_info = _decoded_audio_info(
                        soundfile,
                        decode_path,
                        label=(
                            "source audio snapshot"
                            if index == 0
                            else f"neutral candidate preview snapshot {index}"
                        ),
                    )
                    if (
                        snapshot_info["sample_rate"] != item["sample_rate"]
                        or snapshot_info["channels"] != item["channels"]
                        or snapshot_info["frames"] != item["input_frames"]
                    ):
                        raise ValueError(
                            "verified decoded audio snapshot metadata changed"
                        )
                tracks: list[dict[str, Any]] = []
                for index, item in enumerate(inputs):
                    output_path = work / f"{index:02d}-{item['kind']}.wav"
                    output_frames = int(item["end_frame"]) - int(item["start_frame"])
                    samples = _read_padded_audio_window(
                        np,
                        soundfile,
                        decode_paths[index],
                        start_frame=int(item["start_frame"]),
                        frames=output_frames,
                        channels=int(item["channels"]),
                    )
                    soundfile.write(
                        str(output_path),
                        samples,
                        int(item["sample_rate"]),
                        format="WAV",
                        subtype="PCM_16",
                    )
                    _restrict_private_permissions(output_path, 0o600)
                    written = soundfile.info(str(output_path))
                    if (
                        written.format != "WAV"
                        or written.subtype != "PCM_16"
                        or int(written.samplerate) != int(item["sample_rate"])
                        or int(written.channels) != int(item["channels"])
                        or int(written.frames) != output_frames
                    ):
                        raise RuntimeError(
                            "decoded loop PCM16 output verification failed"
                        )
                    audio_record = _relative_file_record(output_path, work)
                    audition_level = _decoded_stem_audition_level(output_path)
                    track = {
                        "track_id": item["track_id"],
                        "kind": item["kind"],
                        "audio": audio_record,
                        "sample_rate": int(written.samplerate),
                        "channels": int(written.channels),
                        "frames": int(written.frames),
                        "start_frame": int(item["start_frame"]),
                        "silence_padded_frames": max(
                            0,
                            int(item["end_frame"])
                            - max(
                                int(item["start_frame"]),
                                min(
                                    int(item["end_frame"]),
                                    int(item["input_frames"]),
                                ),
                            ),
                        ),
                        "audition_gain_db": audition_level["applied_gain_db"],
                        "audition_level": audition_level,
                    }
                    if item["kind"] == "candidate":
                        track["candidate_id"] = item["candidate_id"]
                    tracks.append(track)

                aggregate_bytes = sum(int(track["audio"]["bytes"]) for track in tracks)
                if aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES:
                    raise ValueError(
                        "decoded loop aggregate output exceeds the 64 MiB limit"
                    )

                self._verify_decoded_loop_inputs(
                    source_record=source_record,
                    candidates=candidates,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                for decode_path in decode_paths:
                    decode_path.unlink()
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "start_seconds": quantized_start,
                    "end_seconds": quantized_end,
                    "duration_seconds": quantized_end - quantized_start,
                    "tracks": tracks,
                    "aggregate_output_bytes": aggregate_bytes,
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                    "path_free_manifest": True,
                    "private_audio": True,
                    "effects": {
                        "midi_mutated": False,
                        "selection_changed": False,
                        "feedback_recorded": False,
                        "event_appended": False,
                    },
                }
                manifest_path = work / "manifest.json"
                _write_json(manifest_path, manifest)
                _restrict_private_permissions(manifest_path, 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_decoded_stem_loop(cache_key, key_payload)
            if result is None:
                raise RuntimeError("decoded stem loop cache verification failed")
            self._touch_and_prune_decoded_loop_cache(cache_key)
            result["cache_hit"] = False
            return result

    def decoded_arrangement_selection_manifest(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return the canonical path-free tracks and preset groups for audition."""

        return decoded_arrangement_selection_manifest(catalog, current)

    def instrument_review_context(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        track_id: str,
        selection_manifest_sha256: str,
    ) -> dict[str, Any]:
        """Resolve one selected bass or keys part for a fixed-MIDI review.

        This is an internal, path-bearing bridge between the immutable
        Workbench catalog and the private review service.  Nothing returned
        here changes a decision, candidate, preset, pack, or export.
        """

        (
            manifest,
            _source_groups,
            selection,
        ) = _decoded_arrangement_selection(catalog, current)
        if (
            not _is_sha256(selection_manifest_sha256)
            or selection_manifest_sha256 != manifest["selection_manifest_sha256"]
        ):
            raise ValueError(
                "the selected arrangement changed; reload it before preparing "
                "an instrument review"
            )
        checked_track_id = str(track_id)
        matches = [
            item for item in selection if str(item["track_id"]) == checked_track_id
        ]
        if len(matches) != 1:
            raise ValueError(
                "instrument review track_id must identify one selected MIDI part"
            )
        selected = matches[0]
        role = path_free_role(selected.get("role"))[0]
        if role not in complete_instrument_roles():
            raise ValueError(
                "complete-instrument review is available only for selected "
                "bass or keys MIDI"
            )
        self._verify_selection([selected])
        stem = _stem(catalog, str(selected["stem_id"]))
        source_record = dict(stem["source"])
        self._verify_catalog_record(source_record, label=f"{role} source stem")
        soundfont = self._soundfont()
        self._verify_catalog_record(
            soundfont,
            label="instrument-review SoundFont",
            restart_hint=True,
        )
        return {
            "schema": INSTRUMENT_REVIEW_CONTEXT_SCHEMA,
            "project_id": str(catalog.get("project_id", "")),
            "selection_manifest_sha256": selection_manifest_sha256,
            "bpm": _project_bpm(catalog),
            "track": {
                "track_id": checked_track_id,
                "stem_id": str(selected["stem_id"]),
                "candidate_id": str(selected["candidate_id"]),
                "role": role,
                "decision": str(selected["decision"]),
                "selection_index": int(selected["selection_index"]),
                "midi": dict(selected["midi"]),
            },
            "source": source_record,
            "soundfont": soundfont,
            "programs": complete_instrument_programs(role),
            "effects": {
                "midi_mutated": False,
                "selection_changed": False,
                "automatic_selection": False,
                "automatic_ranking": False,
                "default_selection_changed": False,
                "pack_changed": False,
                "product_completion_changed": False,
            },
        }

    def prepare_decoded_arrangement_loop(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        selection_manifest_sha256: str,
        start_seconds: float,
        end_seconds: float,
    ) -> dict[str, Any]:
        """Build one private short-loop bundle for the selected arrangement."""

        start, end = _decoded_loop_window(start_seconds, end_seconds)
        (
            selection_manifest,
            source_groups,
            selection,
        ) = _decoded_arrangement_selection(catalog, current)
        if (
            not _is_sha256(selection_manifest_sha256)
            or selection_manifest_sha256
            != selection_manifest["selection_manifest_sha256"]
        ):
            raise ValueError(
                "the decoded arrangement selection changed; reload the current "
                "arrangement before preparing it"
            )
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before preparing "
                "a decoded arrangement"
            )
        if len(source_groups) + len(selection) > _DECODED_ARRANGEMENT_MAXIMUM_TRACKS:
            raise ValueError(
                "decoded arrangement comparison supports at most 24 source and "
                "selected MIDI tracks"
            )

        with self._lock:
            source_records = [group["records"][0] for group in source_groups]
            declared_input_bytes = _decoded_declared_input_bytes(
                [("source audio", record) for record in source_records]
                + [("selected candidate MIDI", item.get("midi")) for item in selection]
            )
            _require_decoded_input_limit(declared_input_bytes)
            if self._soundfont_cache is not None:
                soundfont_size = _decoded_declared_input_bytes(
                    [("SoundFont", self._soundfont_cache)]
                )
            else:
                soundfont_path = self.soundfont_path or Path(find_soundfont()).resolve()
                try:
                    soundfont_size = soundfont_path.stat().st_size
                except OSError as exc:
                    raise ValueError(
                        f"SoundFont file does not exist: {soundfont_path}"
                    ) from exc
            _require_decoded_input_limit(declared_input_bytes + soundfont_size)

            for group in source_groups:
                for record in group["records"]:
                    self._verify_catalog_record(record, label="source audio")
            self._verify_selection(selection)
            soundfont_record = self._soundfont()
            pre_render_input_bytes = _decoded_declared_input_bytes(
                [("source audio", record) for record in source_records]
                + [("selected candidate MIDI", item.get("midi")) for item in selection]
                + [("SoundFont", soundfont_record)]
            )
            _require_decoded_input_limit(pre_render_input_bytes)

            previews: list[dict[str, Any]] = []
            aggregate_input_bytes = pre_render_input_bytes
            for item in selection:
                preview = self.cached_candidate_preview(
                    catalog,
                    str(item["stem_id"]),
                    str(item["candidate_id"]),
                    role_override=str(item["role"]),
                )
                if preview is None:
                    preview = self.render_candidate_preview(
                        catalog,
                        str(item["stem_id"]),
                        str(item["candidate_id"]),
                        role_override=str(item["role"]),
                    )
                preview_bytes = _decoded_declared_input_bytes(
                    [("neutral selected MIDI preview", preview.get("preview"))]
                )
                try:
                    _require_decoded_input_limit(aggregate_input_bytes + preview_bytes)
                except ValueError:
                    if preview.get("cache_hit") is False:
                        self._discard_new_preview(preview)
                    raise
                aggregate_input_bytes += preview_bytes
                previews.append(preview)
            required_soundfont_sha256 = str(soundfont_record["sha256"])
            self._require_preview_renderer_consistency(
                previews,
                expected_soundfont_sha256=required_soundfont_sha256,
            )

            self._verify_decoded_arrangement_inputs(
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                expected_soundfont_sha256=required_soundfont_sha256,
            )
            source_paths = [
                self._verify_catalog_record(record, label="source audio")
                for record in source_records
            ]
            preview_paths = [
                self._verify_catalog_record(
                    preview["preview"], label="neutral selected MIDI preview"
                )
                for preview in previews
            ]
            np, soundfile = _decoded_audio_modules()
            source_infos = [
                _decoded_audio_info(soundfile, path, label="source audio")
                for path in source_paths
            ]
            if not source_infos:
                raise ValueError("decoded arrangement requires source audio")
            anchor_sample_rate = int(source_infos[0]["sample_rate"])
            anchor_start_frame = _nearest_audio_frame(start, anchor_sample_rate)
            anchor_end_frame = _nearest_audio_frame(end, anchor_sample_rate)
            if anchor_end_frame <= anchor_start_frame:
                raise ValueError(
                    "decoded arrangement window contains no source audio frames"
                )
            quantized_start = anchor_start_frame / anchor_sample_rate
            quantized_end = anchor_end_frame / anchor_sample_rate

            inputs: list[dict[str, Any]] = []
            for group, record, path, info in zip(
                source_groups, source_records, source_paths, source_infos
            ):
                input_start = _nearest_audio_frame(
                    quantized_start, int(info["sample_rate"])
                )
                input_end = _nearest_audio_frame(
                    quantized_end, int(info["sample_rate"])
                )
                inputs.append(
                    {
                        "track_id": group["track_id"],
                        "kind": "source",
                        "stem_ids": list(group["stem_ids"]),
                        "roles": list(group["roles"]),
                        "source_sha256": str(record["sha256"]),
                        "input_path": path,
                        "expected_record": record,
                        "input_sha256": str(record["sha256"]),
                        "input_bytes": int(record["bytes"]),
                        "sample_rate": int(info["sample_rate"]),
                        "channels": int(info["channels"]),
                        "input_frames": int(info["frames"]),
                        "start_frame": input_start,
                        "end_frame": input_end,
                    }
                )

            for item, preview, path in zip(selection, previews, preview_paths):
                info = _decoded_audio_info(
                    soundfile,
                    path,
                    label="neutral selected MIDI preview",
                )
                input_start = _nearest_audio_frame(
                    quantized_start, int(info["sample_rate"])
                )
                input_end = _nearest_audio_frame(
                    quantized_end, int(info["sample_rate"])
                )
                inputs.append(
                    {
                        "track_id": item["track_id"],
                        "kind": "selected_midi",
                        "stem_id": item["stem_id"],
                        "candidate_id": item["candidate_id"],
                        "role": item["role"],
                        "decision": item["decision"],
                        "source_midi_sha256": str(item["midi"]["sha256"]),
                        "neutral_preview_cache_key": str(preview["cache_key"]),
                        "neutral_preview_policy": str(preview["policy"]),
                        "soundfont_sha256": str(preview["soundfont_sha256"]),
                        "input_path": path,
                        "expected_record": preview["preview"],
                        "input_sha256": str(preview["preview"]["sha256"]),
                        "input_bytes": int(preview["preview"]["bytes"]),
                        "sample_rate": int(info["sample_rate"]),
                        "channels": int(info["channels"]),
                        "input_frames": int(info["frames"]),
                        "start_frame": input_start,
                        "end_frame": input_end,
                    }
                )

            pcm16_output_upper_bound_bytes = _decoded_pcm16_output_upper_bound(inputs)
            if pcm16_output_upper_bound_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES:
                raise ValueError(
                    "decoded arrangement aggregate output exceeds the 64 MiB limit"
                )

            input_fingerprints = [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"input_path", "expected_record"}
                }
                for item in inputs
            ]
            key_payload = {
                "schema": DECODED_ARRANGEMENT_LOOP_SCHEMA,
                "project_id": catalog.get("project_id"),
                "selection_manifest_sha256": selection_manifest_sha256,
                "sources": selection_manifest["sources"],
                "selected_midi": selection_manifest["selected_midi"],
                "groups": selection_manifest["groups"],
                "window": {
                    "anchor_sample_rate": anchor_sample_rate,
                    "anchor_start_frame": anchor_start_frame,
                    "anchor_end_frame": anchor_end_frame,
                    "quantized_start_seconds": quantized_start,
                    "quantized_end_seconds": quantized_end,
                    "logical_duration_seconds": quantized_end - quantized_start,
                },
                "input_fingerprints": input_fingerprints,
                "policy": _DECODED_ARRANGEMENT_LOOP_POLICY,
                "renderer": {
                    "policy": _RENDER_POLICY,
                    "soundfont_sha256": required_soundfont_sha256,
                },
                "encoding": {
                    "container": "WAV",
                    "subtype": "PCM_16",
                    "sample_rate_policy": "preserve each decoded input rate",
                    "channel_policy": "preserve mono or stereo",
                },
                "resource_limits": {
                    "track_count": len(inputs),
                    "maximum_track_count": _DECODED_ARRANGEMENT_MAXIMUM_TRACKS,
                    "aggregate_input_bytes": aggregate_input_bytes,
                    "maximum_input_bytes": _DECODED_LOOP_MAXIMUM_INPUT_BYTES,
                    "pcm16_output_upper_bound_bytes": (pcm16_output_upper_bound_bytes),
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                },
            }
            cache_key = _document_hash(key_payload)
            cached = self._load_decoded_arrangement_loop(cache_key, key_payload)
            if cached is not None:
                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                self._touch_and_prune_decoded_cache(
                    "decoded-arrangement-loops", cache_key
                )
                cached["cache_hit"] = True
                return cached

            work, final = self._private_building_directory(
                "decoded-arrangement-loops", cache_key
            )
            try:
                tracks: list[dict[str, Any]] = []
                for index, item in enumerate(inputs):
                    snapshot_path = work / f".verified-input-{index:02d}"
                    snapshot = _write_verified_private_snapshot(
                        Path(item["input_path"]),
                        item["expected_record"],
                        snapshot_path,
                        label=(
                            "source audio"
                            if item["kind"] == "source"
                            else "neutral selected MIDI preview"
                        ),
                    )
                    try:
                        snapshot_info = _decoded_audio_info(
                            soundfile,
                            snapshot,
                            label="verified decoded arrangement audio snapshot",
                        )
                        if (
                            snapshot_info["sample_rate"] != item["sample_rate"]
                            or snapshot_info["channels"] != item["channels"]
                            or snapshot_info["frames"] != item["input_frames"]
                        ):
                            raise ValueError(
                                "verified decoded arrangement snapshot metadata changed"
                            )
                        output_frames = int(item["end_frame"]) - int(
                            item["start_frame"]
                        )
                        if output_frames <= 0:
                            raise ValueError(
                                "decoded arrangement track has no output frames"
                            )
                        samples = _read_padded_audio_window(
                            np,
                            soundfile,
                            snapshot,
                            start_frame=int(item["start_frame"]),
                            frames=output_frames,
                            channels=int(item["channels"]),
                        )
                        output_path = work / f"{index:02d}-{item['kind']}.wav"
                        soundfile.write(
                            str(output_path),
                            samples,
                            int(item["sample_rate"]),
                            format="WAV",
                            subtype="PCM_16",
                        )
                        _restrict_private_permissions(output_path, 0o600)
                        written = soundfile.info(str(output_path))
                        if (
                            written.format != "WAV"
                            or written.subtype != "PCM_16"
                            or int(written.samplerate) != int(item["sample_rate"])
                            or int(written.channels) != int(item["channels"])
                            or int(written.frames) != output_frames
                        ):
                            raise RuntimeError(
                                "decoded arrangement PCM16 output verification failed"
                            )
                    finally:
                        snapshot.unlink(missing_ok=True)

                    track = {
                        key: item[key]
                        for key in (
                            "track_id",
                            "kind",
                            "stem_ids",
                            "roles",
                            "source_sha256",
                            "stem_id",
                            "candidate_id",
                            "role",
                            "decision",
                            "source_midi_sha256",
                        )
                        if key in item
                    }
                    track.update(
                        {
                            "audio": _relative_file_record(output_path, work),
                            "sample_rate": int(written.samplerate),
                            "channels": int(written.channels),
                            "frames": int(written.frames),
                            "start_frame": int(item["start_frame"]),
                            "silence_padded_frames": max(
                                0,
                                int(item["end_frame"])
                                - max(
                                    int(item["start_frame"]),
                                    min(
                                        int(item["end_frame"]),
                                        int(item["input_frames"]),
                                    ),
                                ),
                            ),
                        }
                    )
                    tracks.append(track)

                aggregate_bytes = sum(int(track["audio"]["bytes"]) for track in tracks)
                if aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES:
                    raise ValueError(
                        "decoded arrangement aggregate output exceeds the 64 MiB limit"
                    )
                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                manifest = {
                    **key_payload,
                    "cache_key": cache_key,
                    "start_seconds": quantized_start,
                    "end_seconds": quantized_end,
                    "duration_seconds": quantized_end - quantized_start,
                    "tracks": tracks,
                    "aggregate_output_bytes": aggregate_bytes,
                    "maximum_output_bytes": _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES,
                    "path_free_manifest": True,
                    "private_audio": True,
                    "effects": _decoded_arrangement_effects(),
                }
                manifest_path = work / "manifest.json"
                _write_json(manifest_path, manifest)
                _restrict_private_permissions(manifest_path, 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_decoded_arrangement_loop(cache_key, key_payload)
            if result is None:
                raise RuntimeError("decoded arrangement loop cache verification failed")
            self._touch_and_prune_decoded_cache("decoded-arrangement-loops", cache_key)
            result["cache_hit"] = False
            return result

    def prepare_decoded_arrangement_stream(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        selection_manifest_sha256: str,
        preset: str,
    ) -> dict[str, Any]:
        """Prepare a bounded, immutable full-song decoded-stream plan.

        The returned plan contains no local paths.  Source and rendered MIDI
        audio used by later chunks is copied once into owner-only verified
        snapshots stored with the private stream record.
        """

        selected_preset = _decoded_arrangement_stream_preset(preset)
        (
            selection_manifest,
            source_groups,
            selection,
        ) = _decoded_arrangement_selection(catalog, current)
        _require_decoded_arrangement_selection_hash(
            selection_manifest, selection_manifest_sha256
        )
        preset_track_ids = tuple(selection_manifest["groups"][selected_preset])
        if not preset_track_ids:
            raise ValueError(
                f"decoded arrangement preset {selected_preset!r} has no current tracks"
            )
        if len(preset_track_ids) > _DECODED_ARRANGEMENT_MAXIMUM_TRACKS:
            raise ValueError("decoded arrangement streaming supports at most 24 tracks")

        with self._lock:
            selection_by_track_id = {str(item["track_id"]): item for item in selection}
            source_group_by_track_id = {
                str(group["track_id"]): group for group in source_groups
            }
            midi_track_ids = tuple(
                track_id
                for track_id in preset_track_ids
                if track_id in selection_by_track_id
            )
            relevant_selection = [
                selection_by_track_id[track_id] for track_id in midi_track_ids
            ]
            declared_records: list[tuple[str, Any]] = [
                ("source audio", group["records"][0]) for group in source_groups
            ]
            declared_records.extend(
                ("selected candidate MIDI", item.get("midi"))
                for item in relevant_selection
            )
            declared_input_bytes = _decoded_declared_input_bytes(declared_records)
            _require_decoded_input_limit(declared_input_bytes)
            early_soundfont_size = 0
            if midi_track_ids:
                if self._soundfont_cache is not None:
                    early_soundfont_size = _decoded_declared_input_bytes(
                        [("SoundFont", self._soundfont_cache)]
                    )
                else:
                    soundfont_path = (
                        self.soundfont_path or Path(find_soundfont()).resolve()
                    )
                    try:
                        early_soundfont_size = soundfont_path.stat().st_size
                    except OSError as exc:
                        raise ValueError(
                            f"SoundFont file does not exist: {soundfont_path}"
                        ) from exc
                _require_decoded_input_limit(
                    declared_input_bytes + int(early_soundfont_size)
                )

            np, soundfile = _decoded_audio_modules()
            del np  # planning needs decoder metadata but does not allocate samples
            source_clock: list[dict[str, Any]] = []
            source_paths: dict[str, Path] = {}
            source_records: dict[str, Mapping[str, Any]] = {}
            for group in source_groups:
                for record in group["records"]:
                    self._verify_catalog_record(record, label="source audio")
                record = group["records"][0]
                path = self._verify_catalog_record(record, label="source audio")
                info = _decoded_audio_info(soundfile, path, label="source audio")
                track_id = str(group["track_id"])
                source_paths[track_id] = path
                source_records[track_id] = record
                source_clock.append(
                    {
                        "track_id": track_id,
                        "source_sha256": str(record["sha256"]),
                        "source_bytes": int(record["bytes"]),
                        "sample_rate": int(info["sample_rate"]),
                        "channels": int(info["channels"]),
                        "frames": int(info["frames"]),
                    }
                )
            if not source_clock:
                raise ValueError("decoded arrangement streaming requires source audio")

            longest_source = _longest_decoded_source(source_clock)
            if (
                int(longest_source["frames"])
                > int(longest_source["sample_rate"]) * _DECODED_STREAM_MAXIMUM_SECONDS
            ):
                raise ValueError(
                    "decoded arrangement streaming supports songs up to 20 minutes"
                )
            anchor_sample_rate = int(source_clock[0]["sample_rate"])
            anchor_song_end_frame = _ceil_scaled_frame(
                int(longest_source["frames"]),
                anchor_sample_rate,
                int(longest_source["sample_rate"]),
            )
            if anchor_song_end_frame <= 0:
                raise ValueError("decoded arrangement source audio has no frames")

            previews_by_track_id: dict[str, dict[str, Any]] = {}
            preview_paths: dict[str, Path] = {}
            renderer: dict[str, Any] | None = None
            aggregate_input_bytes = declared_input_bytes
            if midi_track_ids:
                self._verify_selection(relevant_selection)
                soundfont_record = self._soundfont()
                if int(soundfont_record["bytes"]) != int(early_soundfont_size):
                    raise ValueError("SoundFont size changed while preparing stream")
                aggregate_input_bytes += int(early_soundfont_size)
                for track_id, item in zip(midi_track_ids, relevant_selection):
                    preview = self.cached_candidate_preview(
                        catalog,
                        str(item["stem_id"]),
                        str(item["candidate_id"]),
                        role_override=str(item["role"]),
                    )
                    if preview is None:
                        preview = self.render_candidate_preview(
                            catalog,
                            str(item["stem_id"]),
                            str(item["candidate_id"]),
                            role_override=str(item["role"]),
                        )
                    preview_bytes = _decoded_declared_input_bytes(
                        [("neutral selected MIDI preview", preview.get("preview"))]
                    )
                    try:
                        _require_decoded_input_limit(
                            aggregate_input_bytes + preview_bytes
                        )
                    except ValueError:
                        if preview.get("cache_hit") is False:
                            self._discard_new_preview(preview)
                        raise
                    aggregate_input_bytes += preview_bytes
                    previews_by_track_id[track_id] = preview
                required_soundfont_sha256 = str(soundfont_record["sha256"])
                self._require_preview_renderer_consistency(
                    list(previews_by_track_id.values()),
                    expected_soundfont_sha256=required_soundfont_sha256,
                )
                for track_id, preview in previews_by_track_id.items():
                    preview_paths[track_id] = self._verify_catalog_record(
                        preview["preview"],
                        label="neutral selected MIDI preview",
                    )
                renderer = {
                    "policy": _RENDER_POLICY,
                    "soundfont_sha256": required_soundfont_sha256,
                }

            inputs: list[dict[str, Any]] = []
            private_inputs: list[dict[str, Any]] = []
            for track_id in preset_track_ids:
                if track_id in source_group_by_track_id:
                    group = source_group_by_track_id[track_id]
                    record = source_records[track_id]
                    path = source_paths[track_id]
                    clock = next(
                        row for row in source_clock if row["track_id"] == track_id
                    )
                    item = {
                        "track_id": track_id,
                        "kind": "source",
                        "stem_ids": list(group["stem_ids"]),
                        "roles": list(group["roles"]),
                        "source_sha256": str(record["sha256"]),
                        "input_sha256": str(record["sha256"]),
                        "input_bytes": int(record["bytes"]),
                        "sample_rate": int(clock["sample_rate"]),
                        "channels": int(clock["channels"]),
                        "input_frames": int(clock["frames"]),
                    }
                    inputs.append(item)
                    private_inputs.append(
                        {**item, "input_path": path, "expected_record": record}
                    )
                    continue
                selected = selection_by_track_id.get(track_id)
                preview = previews_by_track_id.get(track_id)
                path = preview_paths.get(track_id)
                if selected is None or preview is None or path is None:
                    raise ValueError(
                        "decoded arrangement preset does not match the canonical "
                        "selection roster"
                    )
                info = _decoded_audio_info(
                    soundfile, path, label="neutral selected MIDI preview"
                )
                item = {
                    "track_id": track_id,
                    "kind": "selected_midi",
                    "stem_id": str(selected["stem_id"]),
                    "candidate_id": str(selected["candidate_id"]),
                    "role": str(selected["role"]),
                    "decision": str(selected["decision"]),
                    "source_midi_sha256": str(selected["midi"]["sha256"]),
                    "neutral_preview_cache_key": str(preview["cache_key"]),
                    "neutral_preview_policy": str(preview["policy"]),
                    "soundfont_sha256": str(preview["soundfont_sha256"]),
                    "input_sha256": str(preview["preview"]["sha256"]),
                    "input_bytes": int(preview["preview"]["bytes"]),
                    "sample_rate": int(info["sample_rate"]),
                    "channels": int(info["channels"]),
                    "input_frames": int(info["frames"]),
                }
                inputs.append(item)
                private_inputs.append(
                    {
                        **item,
                        "input_path": path,
                        "expected_record": preview["preview"],
                    }
                )

            chunk_plan = _decoded_stream_chunk_plan(
                anchor_sample_rate=anchor_sample_rate,
                anchor_song_end_frame=anchor_song_end_frame,
                inputs=inputs,
            )
            key_payload: dict[str, Any] = {
                "schema": DECODED_ARRANGEMENT_STREAM_SCHEMA,
                "project_id": catalog.get("project_id"),
                "selection_manifest_sha256": selection_manifest_sha256,
                "preset": selected_preset,
                "preset_track_ids": list(preset_track_ids),
                "source_clock": source_clock,
                "tracks": inputs,
                "anchor": {
                    "sample_rate": anchor_sample_rate,
                    "song_end_frame": anchor_song_end_frame,
                    "duration_seconds": (anchor_song_end_frame / anchor_sample_rate),
                    "longest_source_track_id": longest_source["track_id"],
                },
                "chunking": chunk_plan,
                "policy": _DECODED_ARRANGEMENT_STREAM_POLICY,
                "renderer": renderer,
                "encoding": {
                    "container": "WAV",
                    "subtype": "PCM_16",
                    "sample_rate_policy": "preserve each decoded input rate",
                    "channel_policy": "preserve mono or stereo",
                },
                "resource_limits": {
                    "track_count": len(inputs),
                    "maximum_track_count": _DECODED_ARRANGEMENT_MAXIMUM_TRACKS,
                    "verified_input_bytes": aggregate_input_bytes,
                    "maximum_input_bytes": _DECODED_LOOP_MAXIMUM_INPUT_BYTES,
                    "maximum_song_seconds": _DECODED_STREAM_MAXIMUM_SECONDS,
                    "maximum_chunk_seconds": (_DECODED_STREAM_MAXIMUM_CHUNK_SECONDS),
                    "maximum_chunk_count": _DECODED_STREAM_MAXIMUM_CHUNKS,
                    "maximum_chunk_pcm16_bytes": (
                        _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES
                    ),
                    "maximum_two_chunk_float_bytes": (
                        _DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES
                    ),
                },
                "path_free_manifest": True,
                "private_audio": True,
                "effects": _decoded_arrangement_effects(),
            }
            stream_sha256 = _document_hash(key_payload)
            key_payload["stream_sha256"] = stream_sha256
            cached = self._load_decoded_arrangement_stream(
                stream_sha256, expected_manifest=key_payload
            )
            if cached is not None:
                self._verify_decoded_arrangement_stream_current(
                    catalog=catalog,
                    current=current,
                    stream=cached[0],
                )
                self._remember_verified_decoded_arrangement_stream(
                    catalog=catalog,
                    current=current,
                    stream=cached[0],
                    snapshots=cached[1],
                )
                self._touch_and_prune_decoded_stream_cache(stream_sha256)
                result = dict(cached[0])
                result["cache_hit"] = True
                return result

            self._verify_decoded_arrangement_stream_current(
                catalog=catalog,
                current=current,
                stream=key_payload,
                prepared_previews=previews_by_track_id,
            )
            work, final = self._private_building_directory(
                "decoded-arrangement-streams", stream_sha256
            )
            try:
                input_directory = work / "inputs"
                input_directory.mkdir(mode=0o700)
                _restrict_private_permissions(input_directory, 0o700)
                snapshots: dict[str, dict[str, Any]] = {}
                private_records: list[dict[str, Any]] = []
                for item in private_inputs:
                    digest = str(item["input_sha256"])
                    snapshot_record = snapshots.get(digest)
                    if snapshot_record is None:
                        snapshot = _write_verified_private_snapshot(
                            Path(item["input_path"]),
                            item["expected_record"],
                            input_directory / f"{digest}.audio",
                            label=(
                                "source audio"
                                if item["kind"] == "source"
                                else "neutral selected MIDI preview"
                            ),
                        )
                        snapshot_info = _decoded_audio_info(
                            soundfile,
                            snapshot,
                            label="verified decoded stream audio snapshot",
                        )
                        if (
                            snapshot_info["sample_rate"] != item["sample_rate"]
                            or snapshot_info["channels"] != item["channels"]
                            or snapshot_info["frames"] != item["input_frames"]
                        ):
                            raise ValueError(
                                "verified decoded stream snapshot metadata changed"
                            )
                        snapshot_record = _relative_file_record(snapshot, work)
                        snapshots[digest] = snapshot_record
                    elif (
                        snapshot_record["bytes"] != item["input_bytes"]
                        or snapshot_record["sha256"] != digest
                    ):
                        raise ValueError(
                            "decoded stream input hash has inconsistent content"
                        )
                    private_records.append(
                        {
                            "track_id": item["track_id"],
                            "snapshot": snapshot_record,
                        }
                    )

                self._verify_decoded_arrangement_stream_current(
                    catalog=catalog,
                    current=current,
                    stream=key_payload,
                    prepared_previews=previews_by_track_id,
                )
                _write_json(work / "manifest.json", key_payload)
                private_record = {
                    "schema": (
                        "sunofriend.workbench-decoded-arrangement-stream-record.v1"
                    ),
                    "stream_sha256": stream_sha256,
                    "manifest_sha256": _document_hash(key_payload),
                    "inputs": private_records,
                }
                _write_json(work / "record.json", private_record)
                _restrict_private_permissions(work / "manifest.json", 0o600)
                _restrict_private_permissions(work / "record.json", 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            loaded = self._load_decoded_arrangement_stream(
                stream_sha256, expected_manifest=key_payload
            )
            if loaded is None:
                raise RuntimeError("decoded arrangement stream verification failed")
            self._remember_verified_decoded_arrangement_stream(
                catalog=catalog,
                current=current,
                stream=loaded[0],
                snapshots=loaded[1],
            )
            self._touch_and_prune_decoded_stream_cache(stream_sha256)
            result = dict(loaded[0])
            result["cache_hit"] = False
            return result

    def prepare_decoded_arrangement_chunk(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        stream_sha256: str,
        chunk_index: int,
    ) -> dict[str, Any]:
        """Build one exact, contiguous PCM16 chunk from a prepared stream."""

        if not _is_sha256(stream_sha256):
            raise ValueError("decoded arrangement stream identity is invalid")
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
            raise ValueError("decoded arrangement chunk index must be an integer")
        with self._lock:
            loaded = self._cached_verified_decoded_arrangement_stream(
                catalog=catalog,
                current=current,
                stream_sha256=stream_sha256,
            )
            fully_verified = loaded is not None
            if loaded is None:
                loaded = self._load_decoded_arrangement_stream(stream_sha256)
            if loaded is None:
                raise ValueError(
                    "decoded arrangement stream is missing or changed; prepare it again"
                )
            stream, snapshots = loaded
            chunks = stream.get("chunking", {}).get("chunks", [])
            if not isinstance(chunks, list) or not 0 <= chunk_index < len(chunks):
                raise ValueError("decoded arrangement chunk index is out of range")
            boundary = chunks[chunk_index]
            if not isinstance(boundary, Mapping):
                raise ValueError("decoded arrangement chunk boundary is invalid")
            if not fully_verified:
                self._verify_decoded_arrangement_stream_current(
                    catalog=catalog,
                    current=current,
                    stream=stream,
                )
                self._remember_verified_decoded_arrangement_stream(
                    catalog=catalog,
                    current=current,
                    stream=stream,
                    snapshots=snapshots,
                )
            self._touch_and_prune_decoded_stream_cache(stream_sha256)
            anchor = stream.get("anchor")
            tracks = stream.get("tracks")
            if not isinstance(anchor, Mapping) or not isinstance(tracks, list):
                raise ValueError("decoded arrangement stream plan is invalid")
            anchor_sample_rate = int(anchor["sample_rate"])
            anchor_start_frame = int(boundary["anchor_start_frame"])
            anchor_end_frame = int(boundary["anchor_end_frame"])
            input_fingerprints: list[dict[str, Any]] = []
            for track in tracks:
                if not isinstance(track, Mapping):
                    raise ValueError("decoded arrangement stream track is invalid")
                input_start_frame = _nearest_scaled_frame(
                    anchor_start_frame,
                    int(track["sample_rate"]),
                    anchor_sample_rate,
                )
                input_end_frame = _nearest_scaled_frame(
                    anchor_end_frame,
                    int(track["sample_rate"]),
                    anchor_sample_rate,
                )
                if input_end_frame <= input_start_frame:
                    raise ValueError(
                        "decoded arrangement chunk contains no input audio frames"
                    )
                input_fingerprints.append(
                    {
                        **dict(track),
                        "start_frame": input_start_frame,
                        "end_frame": input_end_frame,
                    }
                )

            pcm16_upper_bound = _decoded_pcm16_output_upper_bound(input_fingerprints)
            if pcm16_upper_bound > _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES:
                raise ValueError(
                    "decoded arrangement chunk exceeds the 32 MiB PCM16 limit"
                )
            two_chunk_float_bytes = _decoded_browser_two_chunk_float_bytes(
                anchor_end_frame - anchor_start_frame,
                input_fingerprints,
            )
            if two_chunk_float_bytes > _DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES:
                raise ValueError(
                    "decoded arrangement chunk exceeds the 192 MiB two-chunk "
                    "float-memory limit"
                )
            key_payload = {
                "schema": DECODED_ARRANGEMENT_CHUNK_SCHEMA,
                "stream_sha256": stream_sha256,
                "selection_manifest_sha256": stream["selection_manifest_sha256"],
                "preset": stream["preset"],
                "chunk_index": chunk_index,
                "chunk_count": len(chunks),
                "anchor": {
                    "sample_rate": anchor_sample_rate,
                    "start_frame": anchor_start_frame,
                    "end_frame": anchor_end_frame,
                    "song_end_frame": int(anchor["song_end_frame"]),
                    "start_seconds": anchor_start_frame / anchor_sample_rate,
                    "end_seconds": anchor_end_frame / anchor_sample_rate,
                    "logical_end": chunk_index == len(chunks) - 1,
                },
                "input_fingerprints": input_fingerprints,
                "policy": _DECODED_ARRANGEMENT_STREAM_POLICY,
                "encoding": stream["encoding"],
                "resource_limits": {
                    "pcm16_output_upper_bound_bytes": pcm16_upper_bound,
                    "maximum_chunk_pcm16_bytes": (
                        _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES
                    ),
                    "projected_two_chunk_float_bytes": two_chunk_float_bytes,
                    "maximum_two_chunk_float_bytes": (
                        _DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES
                    ),
                },
            }
            chunk_sha256 = _document_hash(key_payload)
            key_payload["chunk_sha256"] = chunk_sha256
            cached = self._load_decoded_arrangement_chunk(
                chunk_sha256, expected_manifest=key_payload
            )
            if cached is not None:
                self._touch_and_prune_decoded_cache(
                    "decoded-arrangement-chunks", chunk_sha256
                )
                cached["cache_hit"] = True
                return cached

            np, soundfile = _decoded_audio_modules()
            work, final = self._private_building_directory(
                "decoded-arrangement-chunks", chunk_sha256
            )
            try:
                output_tracks: list[dict[str, Any]] = []
                for index, item in enumerate(input_fingerprints):
                    snapshot_record = snapshots.get(str(item["track_id"]))
                    if snapshot_record is None:
                        raise ValueError(
                            "decoded arrangement stream snapshot roster changed"
                        )
                    snapshot = Path(str(snapshot_record.get("path", ""))).resolve()
                    _regular_file_stat_signature(
                        snapshot, int(snapshot_record["bytes"])
                    )
                    snapshot_info = _decoded_audio_info(
                        soundfile,
                        snapshot,
                        label="decoded arrangement stream snapshot",
                    )
                    if (
                        snapshot_info["sample_rate"] != item["sample_rate"]
                        or snapshot_info["channels"] != item["channels"]
                        or snapshot_info["frames"] != item["input_frames"]
                    ):
                        raise ValueError(
                            "decoded arrangement stream snapshot metadata changed"
                        )
                    output_frames = int(item["end_frame"]) - int(item["start_frame"])
                    samples = _read_padded_audio_window(
                        np,
                        soundfile,
                        snapshot,
                        start_frame=int(item["start_frame"]),
                        frames=output_frames,
                        channels=int(item["channels"]),
                    )
                    output_path = work / f"{index:02d}-{item['kind']}.wav"
                    soundfile.write(
                        str(output_path),
                        samples,
                        int(item["sample_rate"]),
                        format="WAV",
                        subtype="PCM_16",
                    )
                    _restrict_private_permissions(output_path, 0o600)
                    written = soundfile.info(str(output_path))
                    if (
                        written.format != "WAV"
                        or written.subtype != "PCM_16"
                        or int(written.samplerate) != int(item["sample_rate"])
                        or int(written.channels) != int(item["channels"])
                        or int(written.frames) != output_frames
                    ):
                        raise RuntimeError(
                            "decoded arrangement chunk PCM16 verification failed"
                        )
                    output_track = {
                        key: item[key]
                        for key in (
                            "track_id",
                            "kind",
                            "stem_ids",
                            "roles",
                            "source_sha256",
                            "stem_id",
                            "candidate_id",
                            "role",
                            "decision",
                            "source_midi_sha256",
                        )
                        if key in item
                    }
                    output_track.update(
                        {
                            "audio": _relative_file_record(output_path, work),
                            "sample_rate": int(written.samplerate),
                            "channels": int(written.channels),
                            "frames": int(written.frames),
                            "start_frame": int(item["start_frame"]),
                            "end_frame": int(item["end_frame"]),
                            "silence_padded_frames": max(
                                0,
                                int(item["end_frame"])
                                - max(
                                    int(item["start_frame"]),
                                    min(
                                        int(item["end_frame"]),
                                        int(item["input_frames"]),
                                    ),
                                ),
                            ),
                        }
                    )
                    output_tracks.append(output_track)

                aggregate_output_bytes = sum(
                    int(track["audio"]["bytes"]) for track in output_tracks
                )
                if aggregate_output_bytes > _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES:
                    raise ValueError(
                        "decoded arrangement chunk exceeds the 32 MiB PCM16 limit"
                    )
                reloaded_stream = self._cached_verified_decoded_arrangement_stream(
                    catalog=catalog,
                    current=current,
                    stream_sha256=stream_sha256,
                )
                if reloaded_stream is None:
                    reloaded_stream = self._load_decoded_arrangement_stream(
                        stream_sha256
                    )
                    if reloaded_stream is not None:
                        self._verify_decoded_arrangement_stream_current(
                            catalog=catalog,
                            current=current,
                            stream=reloaded_stream[0],
                        )
                        self._remember_verified_decoded_arrangement_stream(
                            catalog=catalog,
                            current=current,
                            stream=reloaded_stream[0],
                            snapshots=reloaded_stream[1],
                        )
                if reloaded_stream is None or reloaded_stream[0] != stream:
                    raise ValueError(
                        "decoded arrangement stream changed while rendering a chunk"
                    )
                manifest = {
                    **key_payload,
                    "tracks": output_tracks,
                    "aggregate_output_bytes": aggregate_output_bytes,
                    "path_free_manifest": True,
                    "private_audio": True,
                    "effects": _decoded_arrangement_effects(),
                }
                _write_json(work / "manifest.json", manifest)
                _restrict_private_permissions(work / "manifest.json", 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_decoded_arrangement_chunk(
                chunk_sha256, expected_manifest=key_payload
            )
            if result is None:
                raise RuntimeError("decoded arrangement chunk verification failed")
            self._touch_and_prune_decoded_cache(
                "decoded-arrangement-chunks", chunk_sha256
            )
            result["cache_hit"] = False
            return result

    def cached_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock:
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
            tracks = build_arrangement_tracks(selection)
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

    def cached_balanced_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Return a verified source-referenced MIDI balance without creating it."""

        with self._lock:
            self._reclaim_stale_balanced_deferred_caches()
            balanced_root = self.root / "balanced-arrangements"
            if not balanced_root.is_dir() or not any(
                balanced_root.glob("*/manifest.json")
            ):
                # /api/project polls this read-only path.  On a fresh project
                # there is no cache to authenticate, so avoid source/MIDI/
                # preview hashing and any renderer discovery until the user
                # explicitly asks to create a balanced audition.
                return None
            selection_manifest, source_groups, selection = (
                _decoded_arrangement_selection(catalog, current)
            )
            if not selection:
                return None
            expected = {
                "schema": BALANCED_ARRANGEMENT_SCHEMA,
                "project_id": catalog.get("project_id"),
                "selection_manifest_sha256": selection_manifest[
                    "selection_manifest_sha256"
                ],
                "bpm": _project_bpm(catalog),
                "policy": BALANCED_MIX_POLICY,
                "render_horizon_policy": _BALANCED_RENDER_HORIZON_POLICY,
            }
            if not self._balanced_cache_might_match(expected):
                # Old balance caches from another selection are cheap to rule
                # out from their path-free manifests. Authenticate large
                # source, MIDI, preview and SoundFont files only when a cache
                # could actually be returned.
                return None
            for cache_key in self._matching_balanced_cache_keys(expected):
                verified = self._cached_verified_balanced_arrangement(
                    catalog=catalog,
                    current=current,
                    cache_key=cache_key,
                )
                if verified is not None:
                    verified["cache_hit"] = True
                    return verified
            try:
                self._verify_selection(selection)
            except ValueError:
                return None
            soundfont_sha256 = self._available_soundfont_sha256()
            if not soundfont_sha256:
                return None
            previews: list[dict[str, Any]] = []
            for item in selection:
                preview = self.cached_candidate_preview(
                    catalog,
                    str(item["stem_id"]),
                    str(item["candidate_id"]),
                    role_override=str(item["role"]),
                )
                if preview is None:
                    return None
                previews.append(preview)
            try:
                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=soundfont_sha256,
                )
            except ValueError:
                return None
            soundfont = self._soundfont_cache
            if soundfont is None:
                return None
            expected_key_payload = _balanced_key_payload(
                catalog=catalog,
                selection_manifest_sha256=selection_manifest[
                    "selection_manifest_sha256"
                ],
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                soundfont=soundfont,
            )
            cache_key = _document_hash(expected_key_payload)
            result = self._load_balanced_arrangement(
                cache_key,
                expected_key_payload=expected_key_payload,
            )
            if result is not None:
                self._remember_verified_balanced_arrangement(
                    catalog=catalog,
                    current=current,
                    result=result,
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    soundfont=soundfont,
                )
                result["cache_hit"] = True
            return result

    def render_balanced_arrangement(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        selection_manifest_sha256: str,
        *,
        promote_cache: bool = True,
    ) -> dict[str, Any]:
        """Render an opt-in gain-only selected-MIDI balance.

        The current dry arrangement proxy and all selected MIDI remain unchanged.
        Source stems are used only as absolute-level references.
        """

        selection_manifest, source_groups, selection = _decoded_arrangement_selection(
            catalog, current
        )
        _require_decoded_arrangement_selection_hash(
            selection_manifest, selection_manifest_sha256
        )
        if not selection:
            raise ValueError(
                "choose at least one candidate as main or optional before balancing"
            )
        if len(selection) > _DECODED_ARRANGEMENT_MAXIMUM_TRACKS:
            raise ValueError("balanced MIDI audition supports at most 24 tracks")
        self._verify_selection(selection)

        with self._lock:
            self._reclaim_stale_balanced_deferred_caches()
            soundfont = self._soundfont()
            declared_sources = {
                str(group["source_sha256"]): group["records"][0]
                for group in source_groups
            }
            declared_midis = {
                str(item["midi"]["sha256"]): item["midi"] for item in selection
            }
            _require_decoded_input_limit(
                _decoded_declared_input_bytes(
                    [("source audio", record) for record in declared_sources.values()]
                    + [
                        ("selected candidate MIDI", record)
                        for record in declared_midis.values()
                    ]
                    + [("SoundFont", soundfont)]
                )
            )
            previews: list[dict[str, Any]] = []
            for item in selection:
                preview = self.cached_candidate_preview(
                    catalog,
                    str(item["stem_id"]),
                    str(item["candidate_id"]),
                    role_override=str(item["role"]),
                )
                if preview is None:
                    preview = self.render_candidate_preview(
                        catalog,
                        str(item["stem_id"]),
                        str(item["candidate_id"]),
                        role_override=str(item["role"]),
                    )
                previews.append(preview)
            self._verify_decoded_arrangement_inputs(
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                expected_soundfont_sha256=str(soundfont["sha256"]),
            )

            source_by_stem_id: dict[str, Mapping[str, Any]] = {}
            unique_records: dict[str, Mapping[str, Any]] = {}
            for group in source_groups:
                record = group["records"][0]
                source_digest = str(record["sha256"])
                unique_records[source_digest] = record
                for stem_id in group["stem_ids"]:
                    source_by_stem_id[str(stem_id)] = record
            key_payload = _balanced_key_payload(
                catalog=catalog,
                selection_manifest_sha256=selection_manifest_sha256,
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                soundfont=soundfont,
            )
            renderer_identity = key_payload["renderer"]
            input_fingerprints = key_payload["input_fingerprints"]
            project_source_fingerprints = input_fingerprints["project_sources"]
            cache_key = _document_hash(key_payload)
            cached = self._load_balanced_arrangement(
                cache_key, expected_key_payload=key_payload
            )
            if cached is not None:
                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=str(soundfont["sha256"]),
                )
                self._remember_verified_balanced_arrangement(
                    catalog=catalog,
                    current=current,
                    result=cached,
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    soundfont=soundfont,
                )
                if promote_cache:
                    promoted = self.promote_balanced_arrangement(cache_key)
                    promoted["cache_hit"] = True
                    return promoted
                claim_token = self._claim_deferred_balanced_arrangement(
                    cache_key,
                    newly_created=False,
                )
                cached["cache_hit"] = True
                if claim_token is not None:
                    cached["_deferred_cache_claim"] = claim_token
                return cached

            unique_previews: dict[str, Mapping[str, Any]] = {
                str(preview["preview"]["sha256"]): preview["preview"]
                for preview in previews
            }
            aggregate_input_bytes = _decoded_declared_input_bytes(
                [("source audio", record) for record in unique_records.values()]
                + [
                    ("selected candidate MIDI", record)
                    for record in declared_midis.values()
                ]
                + [
                    ("neutral selected MIDI preview", record)
                    for record in unique_previews.values()
                ]
                + [("SoundFont", soundfont)]
            )
            _require_decoded_input_limit(aggregate_input_bytes)

            work, final = self._private_building_directory(
                "balanced-arrangements", cache_key
            )
            try:
                source_snapshots: dict[str, Path] = {}
                for index, (digest, record) in enumerate(unique_records.items()):
                    source_snapshots[digest] = _write_verified_private_snapshot(
                        Path(str(record["path"])),
                        record,
                        work / f".verified-source-{index:02d}",
                        label="source audio",
                    )
                preview_snapshots: dict[str, Path] = {}
                for index, (digest, record) in enumerate(unique_previews.items()):
                    preview_snapshots[digest] = _write_verified_private_snapshot(
                        Path(str(record["path"])),
                        record,
                        work / f".verified-preview-{index:02d}",
                        label="neutral selected MIDI preview",
                    )

                _np, soundfile = _decoded_audio_modules()
                preview_infos = [
                    _decoded_audio_info(
                        soundfile,
                        preview_snapshots[str(preview["preview"]["sha256"])],
                        label="neutral selected MIDI preview snapshot",
                    )
                    for preview in previews
                ]
                preview_sample_rate = int(preview_infos[0]["sample_rate"])
                maximum_preview_frames = max(
                    int(info["frames"]) for info in preview_infos
                )
                source_infos = {
                    digest: _decoded_audio_info(
                        soundfile,
                        path,
                        label="source audio snapshot",
                    )
                    for digest, path in source_snapshots.items()
                }
                maximum_source_frames = max(
                    _ceil_scaled_frame(
                        int(info["frames"]),
                        preview_sample_rate,
                        int(info["sample_rate"]),
                    )
                    for info in source_infos.values()
                )
                # The source song, rather than a renderer tail or a transcription
                # that strays beyond it, owns the audition horizon.  This keeps
                # the derivative aligned with the stems in GarageBand while the
                # immutable neutral previews remain available as evidence.
                output_frames = maximum_source_frames
                source_horizon_rows: list[dict[str, Any]] = []
                for source_fingerprint in project_source_fingerprints:
                    source_digest = str(source_fingerprint["source_sha256"])
                    source_info = source_infos[source_digest]
                    scaled_frames = _ceil_scaled_frame(
                        int(source_info["frames"]),
                        preview_sample_rate,
                        int(source_info["sample_rate"]),
                    )
                    source_horizon_rows.append(
                        {
                            **source_fingerprint,
                            "source_sample_rate": int(source_info["sample_rate"]),
                            "source_channels": int(source_info["channels"]),
                            "source_frames": int(source_info["frames"]),
                            "output_rate_frames": scaled_frames,
                            "owns_output_horizon": (
                                scaled_frames == maximum_source_frames
                            ),
                        }
                    )
                lane_horizon_rows: list[dict[str, Any]] = []
                for item, preview, preview_info in zip(
                    selection,
                    previews,
                    preview_infos,
                ):
                    preview_frames = int(preview_info["frames"])
                    lane_horizon_rows.append(
                        {
                            "track_id": str(item["track_id"]),
                            "stem_id": str(item["stem_id"]),
                            "candidate_id": str(item["candidate_id"]),
                            "selection_index": int(item["selection_index"]),
                            "garageband_pack_archive_member": str(
                                item["garageband_pack_archive_member"]
                            ),
                            "neutral_preview_sha256": str(preview["preview"]["sha256"]),
                            "neutral_preview_frames": preview_frames,
                            "excluded_neutral_preview_tail_frames": max(
                                0,
                                preview_frames - output_frames,
                            ),
                            "padded_output_frames": max(
                                0,
                                output_frames - preview_frames,
                            ),
                        }
                    )
                render_horizon = {
                    "policy": _BALANCED_RENDER_HORIZON_POLICY,
                    "sample_rate": preview_sample_rate,
                    "output_frames": output_frames,
                    "maximum_source_frames": maximum_source_frames,
                    "maximum_neutral_preview_frames": maximum_preview_frames,
                    "excluded_neutral_preview_tail_frames": max(
                        0,
                        maximum_preview_frames - output_frames,
                    ),
                    "padded_output_frames": max(
                        0,
                        output_frames - maximum_preview_frames,
                    ),
                    "sources": source_horizon_rows,
                    "lanes": lane_horizon_rows,
                }
                lanes: list[dict[str, Any]] = []
                for item, preview in zip(selection, previews):
                    source = source_by_stem_id[str(item["stem_id"])]
                    source_digest = str(source["sha256"])
                    preview_digest = str(preview["preview"]["sha256"])
                    lanes.append(
                        {
                            "track_id": str(item["track_id"]),
                            "stem_id": str(item["stem_id"]),
                            "candidate_id": str(item["candidate_id"]),
                            "role": str(item["role"]),
                            "decision": str(item["decision"]),
                            "selection_index": int(item["selection_index"]),
                            "garageband_pack_archive_member": str(
                                item["garageband_pack_archive_member"]
                            ),
                            "source_path": source_snapshots[source_digest],
                            "source_sha256": source_digest,
                            "source_bytes": int(source["bytes"]),
                            "source_midi_sha256": str(item["midi"]["sha256"]),
                            "preview_path": preview_snapshots[preview_digest],
                            "preview_sha256": preview_digest,
                            "preview_bytes": int(preview["preview"]["bytes"]),
                            "neutral_preview_cache_key": str(preview["cache_key"]),
                        }
                    )

                wav_path = work / "balanced-selected-midi-preview.wav"
                internal_mix_report_path = work / ".balanced-mix-report.internal.json"
                receipt_path = work / "balanced-mix-receipt.json"
                recipe_path = work / "garageband-mix-recipe.md"
                mix_report = build_balanced_midi_audition(
                    lanes,
                    output_path=wav_path,
                    report_path=internal_mix_report_path,
                    recipe_path=recipe_path,
                    output_frames=output_frames,
                )

                self._verify_decoded_arrangement_inputs(
                    source_groups=source_groups,
                    selection=selection,
                    previews=previews,
                    expected_soundfont_sha256=str(soundfont["sha256"]),
                )
                for snapshot in [
                    *source_snapshots.values(),
                    *preview_snapshots.values(),
                ]:
                    snapshot.unlink()
                internal_mix_report_path.unlink()
                preview_file_record = _relative_file_record(wav_path, work)
                recipe_file_record = _relative_file_record(recipe_path, work)
                receipt_preview_record = {
                    "filename": str(preview_file_record["name"]),
                    "bytes": int(preview_file_record["bytes"]),
                    "sha256": str(preview_file_record["sha256"]),
                }
                receipt_recipe_record = {
                    "filename": str(recipe_file_record["name"]),
                    "bytes": int(recipe_file_record["bytes"]),
                    "sha256": str(recipe_file_record["sha256"]),
                }
                receipt_payload = {
                    "schema": _BALANCED_MIX_RECEIPT_SCHEMA,
                    "project_id": catalog.get("project_id"),
                    "selection_manifest_sha256": selection_manifest_sha256,
                    "bpm": _project_bpm(catalog),
                    "policy": BALANCED_MIX_POLICY,
                    "render_horizon_policy": _BALANCED_RENDER_HORIZON_POLICY,
                    "selection": _public_selection(selection),
                    "renderer": renderer_identity,
                    "input_fingerprints": input_fingerprints,
                    "render_horizon": render_horizon,
                    "preview": receipt_preview_record,
                    "recipe": receipt_recipe_record,
                    "mix_report": mix_report,
                    "mastered": False,
                    "mastering_boundary": mix_report["mastering_boundary"],
                    "effects": _decoded_arrangement_effects(),
                }
                if not _balanced_path_free_document(receipt_payload):
                    raise RuntimeError("balanced mix receipt contains a local path")
                receipt = {
                    **receipt_payload,
                    "receipt_sha256": _document_hash(receipt_payload),
                }
                _write_json(receipt_path, receipt)
                manifest_payload = {
                    **key_payload,
                    "cache_key": cache_key,
                    "preview": preview_file_record,
                    "report": _relative_file_record(receipt_path, work),
                    "recipe": recipe_file_record,
                    "mix_report": mix_report,
                    "render_horizon": render_horizon,
                    "mastered": False,
                    "mastering_boundary": mix_report["mastering_boundary"],
                    "path_free_manifest": True,
                    "private_audio": True,
                    "effects": _decoded_arrangement_effects(),
                }
                manifest = {
                    **manifest_payload,
                    "manifest_sha256": _document_hash(manifest_payload),
                }
                _write_json(work / "manifest.json", manifest)
                _restrict_private_permissions(wav_path, 0o600)
                _restrict_private_permissions(receipt_path, 0o600)
                _restrict_private_permissions(recipe_path, 0o600)
                _restrict_private_permissions(work / "manifest.json", 0o600)
                work.replace(final)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise

            result = self._load_balanced_arrangement(
                cache_key, expected_key_payload=key_payload
            )
            if result is None:
                raise RuntimeError("balanced arrangement cache verification failed")
            self._remember_verified_balanced_arrangement(
                catalog=catalog,
                current=current,
                result=result,
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                soundfont=soundfont,
            )
            if promote_cache:
                self._touch_and_prune_balanced_cache(cache_key)
            else:
                try:
                    claim_token = self._claim_deferred_balanced_arrangement(
                        cache_key,
                        newly_created=True,
                    )
                except Exception:
                    _remove_generated_path(final)
                    self._verified_balanced_cache.pop(cache_key, None)
                    raise
                result["_deferred_cache_claim"] = claim_token
            result["cache_hit"] = False
            return result

    def promote_balanced_arrangement(
        self,
        cache_key: str,
        *,
        claim_token: str | None = None,
    ) -> dict[str, Any]:
        """Adopt, verify, and make one completed balanced cache recently used."""

        if not _is_sha256(cache_key):
            raise ValueError("balanced arrangement cache key is invalid")
        if claim_token is not None and not _is_balanced_deferred_claim(claim_token):
            raise ValueError("balanced arrangement deferred claim is invalid")
        with self._lock:
            result = self._load_balanced_arrangement(cache_key)
            if result is None:
                raise ValueError(
                    "balanced arrangement cache entry is missing or failed verification"
                )
            marker_path = self._balanced_deferred_marker_path(cache_key)
            if _path_exists_or_is_symlink(marker_path):
                marker = self._read_balanced_deferred_marker(cache_key)
                if marker is None:
                    raise ValueError(
                        "balanced arrangement deferred cache marker is invalid"
                    )
                if claim_token is not None and claim_token not in marker["claims"]:
                    raise ValueError(
                        "balanced arrangement deferred claim is not current"
                    )
                marker_path.unlink()
                self._balanced_live_deferred_cache_keys.discard(cache_key)
            self._touch_and_prune_balanced_cache(cache_key)
            result["cache_hit"] = True
            return result

    def discard_deferred_balanced_arrangement(
        self,
        cache_key: str,
        claim_token: str,
    ) -> bool:
        """Release one failed request and remove only its last unadopted cache.

        A marker can exist only for a cache first created by a deferred render.
        Existing or already promoted caches have no marker and are never removed.
        """

        if not _is_sha256(cache_key):
            raise ValueError("balanced arrangement cache key is invalid")
        if not _is_balanced_deferred_claim(claim_token):
            raise ValueError("balanced arrangement deferred claim is invalid")
        with self._lock:
            marker = self._read_balanced_deferred_marker(cache_key)
            if marker is None or claim_token not in marker["claims"]:
                return False
            result = self._load_balanced_arrangement(cache_key)
            if (
                result is None
                or result.get("manifest_sha256") != marker["manifest_sha256"]
            ):
                return False
            remaining_claims = [
                value for value in marker["claims"] if value != claim_token
            ]
            if remaining_claims:
                self._write_balanced_deferred_marker(
                    cache_key,
                    {**marker, "claims": remaining_claims},
                )
                return False
            root = self.root / "balanced-arrangements" / cache_key
            if root.is_symlink() or not root.is_dir() or root.name != cache_key:
                return False
            _remove_generated_path(root)
            self._verified_balanced_cache.pop(cache_key, None)
            self._balanced_live_deferred_cache_keys.discard(cache_key)
            return True

    def _claim_deferred_balanced_arrangement(
        self,
        cache_key: str,
        *,
        newly_created: bool,
    ) -> str | None:
        """Claim a deferred cache, or leave an established cache unowned."""

        result = self._load_balanced_arrangement(cache_key)
        if result is None:
            raise ValueError(
                "balanced arrangement cache entry is missing or failed verification"
            )
        marker_path = self._balanced_deferred_marker_path(cache_key)
        marker_exists = _path_exists_or_is_symlink(marker_path)
        if newly_created:
            if marker_exists:
                raise ValueError(
                    "new balanced arrangement already has a deferred marker"
                )
            marker: dict[str, Any] = {
                "schema": _BALANCED_DEFERRED_CACHE_SCHEMA,
                "cache_key": cache_key,
                "manifest_sha256": str(result["manifest_sha256"]),
                "created_ns": time.time_ns(),
                "claims": [],
            }
        else:
            if not marker_exists:
                # This entry predates the request or has already been adopted.
                # A stale request must never gain authority to remove it.
                return None
            loaded_marker = self._read_balanced_deferred_marker(cache_key)
            if loaded_marker is None:
                raise ValueError(
                    "balanced arrangement deferred cache marker is invalid"
                )
            marker = loaded_marker
            if marker["manifest_sha256"] != result["manifest_sha256"]:
                raise ValueError("balanced arrangement deferred cache identity changed")
        if len(marker["claims"]) >= _BALANCED_DEFERRED_MAXIMUM_CLAIMS:
            raise ValueError("balanced arrangement has too many deferred claims")
        claim_token = uuid.uuid4().hex
        self._write_balanced_deferred_marker(
            cache_key,
            {**marker, "claims": [*marker["claims"], claim_token]},
        )
        self._balanced_live_deferred_cache_keys.add(cache_key)
        return claim_token

    def _balanced_deferred_marker_path(self, cache_key: str) -> Path:
        return (
            self.root
            / "balanced-arrangements"
            / cache_key
            / _BALANCED_DEFERRED_MARKER_NAME
        )

    def _read_balanced_deferred_marker(
        self,
        cache_key: str,
    ) -> dict[str, Any] | None:
        marker_path = self._balanced_deferred_marker_path(cache_key)
        if marker_path.is_symlink():
            return None
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(marker, dict)
            or set(marker)
            != {
                "schema",
                "cache_key",
                "manifest_sha256",
                "created_ns",
                "claims",
            }
            or marker.get("schema") != _BALANCED_DEFERRED_CACHE_SCHEMA
            or marker.get("cache_key") != cache_key
            or not _is_sha256(marker.get("manifest_sha256"))
            or not _valid_nonnegative_int(marker.get("created_ns"))
            or not isinstance(marker.get("claims"), list)
            or not 1 <= len(marker["claims"]) <= _BALANCED_DEFERRED_MAXIMUM_CLAIMS
            or len(set(marker["claims"])) != len(marker["claims"])
            or not all(_is_balanced_deferred_claim(value) for value in marker["claims"])
        ):
            return None
        return marker

    def _write_balanced_deferred_marker(
        self,
        cache_key: str,
        marker: Mapping[str, Any],
    ) -> None:
        marker_path = self._balanced_deferred_marker_path(cache_key)
        root = marker_path.parent
        if (
            not _is_sha256(cache_key)
            or root.is_symlink()
            or not root.is_dir()
            or root.name != cache_key
        ):
            raise ValueError("balanced arrangement cache storage is unsafe")
        temporary = marker_path.with_name(
            f".{_BALANCED_DEFERRED_MARKER_NAME}.writing-{uuid.uuid4().hex}"
        )
        try:
            _write_json(temporary, marker)
            _restrict_private_permissions(temporary, 0o600)
            temporary.replace(marker_path)
            _restrict_private_permissions(marker_path, 0o600)
        finally:
            if _path_exists_or_is_symlink(temporary):
                temporary.unlink()

    def _reclaim_stale_balanced_deferred_caches(self) -> None:
        """Remove only authenticated orphan claims older than six hours."""

        parent = self.root / "balanced-arrangements"
        if not parent.is_dir():
            return
        cutoff_ns = time.time_ns() - (_BALANCED_DEFERRED_STALE_SECONDS * 1_000_000_000)
        for root in parent.iterdir():
            cache_key = root.name
            if (
                cache_key in self._balanced_live_deferred_cache_keys
                or not _is_sha256(cache_key)
                or root.is_symlink()
                or not root.is_dir()
            ):
                continue
            marker = self._read_balanced_deferred_marker(cache_key)
            if marker is None or int(marker["created_ns"]) > cutoff_ns:
                continue
            manifest_path = root / "manifest.json"
            if manifest_path.is_symlink():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(manifest, dict):
                continue
            manifest_sha256 = manifest.get("manifest_sha256")
            unsigned_manifest = {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha256"
            }
            if (
                manifest.get("cache_key") != cache_key
                or manifest_sha256 != marker["manifest_sha256"]
                or not _is_sha256(manifest_sha256)
                or _document_hash(unsigned_manifest) != manifest_sha256
            ):
                continue
            try:
                _remove_generated_path(root)
            except OSError:
                continue
            self._verified_balanced_cache.pop(cache_key, None)

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
                    for item in selection:
                        self._verify_catalog_record(
                            item["midi"], label="selected candidate MIDI"
                        )
                        _zip_file(
                            archive,
                            str(item["garageband_pack_archive_member"]),
                            Path(item["midi_path"]),
                        )
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

    def garageband_pack_plan(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return the path-free, hash-pinned inventory for a custom DAW pack."""

        selection = selected_candidates(catalog, current)
        self._verify_selection(selection)
        overlap = _selected_midi_overlap(selection)
        selection_sha256 = _selection_hash(catalog, selection)
        basket_scope_sha256 = _pack_basket_scope_hash(catalog, selection)
        items, _ = _garageband_pack_inventory(
            catalog,
            selection,
            basket_scope_sha256=basket_scope_sha256,
        )
        block_reasons: list[str] = []
        if not selection:
            block_reasons.append("no-selected-midi")
        if overlap["unconfirmed_substantial_overlap_pair_count"]:
            block_reasons.append("selected-midi-overlap-needs-full-mix-confirmation")
        setup = catalog.get("setup", {})
        plan: dict[str, Any] = {
            "schema": GARAGEBAND_PACK_PLAN_SCHEMA,
            "project_id": catalog.get("project_id"),
            "selection_sha256": selection_sha256,
            "basket_scope_sha256": basket_scope_sha256,
            "items": items,
            "build_blocked": bool(block_reasons),
            "block_reasons": block_reasons,
            "selected_midi_overlap": overlap,
            "setup": {
                "bpm": setup.get("bpm"),
                "key": setup.get("key"),
                "tuning_hz": setup.get("tuning_hz"),
                "downbeat": setup.get("downbeat"),
            },
            "policies": {
                "musical_selection": (
                    "current explicit main and optional decisions define the result "
                    "space; the basket independently chooses copied files"
                ),
                "selected_midi": (
                    "checked MIDI files are copied byte-for-byte and remain "
                    "authoritative"
                ),
                "source_audio": (
                    "excluded by default and allowed only with explicit local opt-in"
                ),
                "arrangement_proxy": (
                    "one generated dry MIDI/WAV audition pair; not an authoritative "
                    "GarageBand instrument choice"
                ),
            },
            "effects": {
                "musical_selection_changed": False,
                "midi_mutated": False,
                "feedback_recorded": False,
                "mixer_state_used": False,
            },
        }
        default_ids = [
            str(item["item_id"]) for item in items if item.get("default_included")
        ]
        if default_ids:
            plan["default_basket"] = canonical_garageband_pack_basket(
                plan,
                default_ids,
                source_audio_opt_in=False,
            )
        else:
            empty_basket = {
                "schema": GARAGEBAND_PACK_BASKET_SCHEMA,
                "project_id": catalog.get("project_id"),
                "basket_scope_sha256": basket_scope_sha256,
                "included_item_ids": [],
                "source_audio_opt_in": False,
            }
            empty_basket["basket_sha256"] = _document_hash(empty_basket)
            plan["default_basket"] = empty_basket
        plan["plan_sha256"] = _pack_plan_hash(plan)
        return plan

    def build_garageband_pack(
        self,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        plan_sha256: str,
        basket: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build one deterministic ZIP from a previously displayed pack basket."""

        plan = self.garageband_pack_plan(catalog, current)
        if plan_sha256 != plan["plan_sha256"]:
            raise WorkbenchPackConflictError(
                "GarageBand pack plan changed; review the current basket before building"
            )
        if basket.get("basket_scope_sha256") != plan["basket_scope_sha256"]:
            raise WorkbenchPackConflictError(
                "GarageBand basket no longer describes the current musical selection"
            )
        included_item_ids = basket.get("included_item_ids")
        source_audio_opt_in = basket.get("source_audio_opt_in")
        canonical = canonical_garageband_pack_basket(
            plan,
            included_item_ids,
            source_audio_opt_in=source_audio_opt_in,
        )
        for key in (
            "schema",
            "project_id",
            "basket_scope_sha256",
            "included_item_ids",
            "source_audio_opt_in",
            "basket_sha256",
        ):
            if basket.get(key) != canonical[key]:
                raise ValueError("GarageBand basket changed after it was canonicalised")
        if plan["build_blocked"]:
            reasons = ", ".join(str(value) for value in plan["block_reasons"])
            raise ValueError(f"GarageBand pack build is blocked: {reasons}")

        selection = selected_candidates(catalog, current)
        self._verify_selection(selection)
        public_items, internal_items = _garageband_pack_inventory(
            catalog,
            selection,
            basket_scope_sha256=str(plan["basket_scope_sha256"]),
        )
        if public_items != plan["items"]:
            raise WorkbenchPackConflictError(
                "GarageBand pack inventory changed; reload the current plan"
            )
        included_ids = set(canonical["included_item_ids"])
        included_items = [
            item for item in public_items if item["item_id"] in included_ids
        ]
        verified_input_payloads: dict[str, bytes] = {}
        for item in included_items:
            if item["kind"] == "arrangement_proxy":
                continue
            item_id = str(item["item_id"])
            internal = internal_items.get(item_id)
            if internal is None:
                raise WorkbenchPackConflictError(
                    "GarageBand pack item is no longer available"
                )
            kind = str(item["kind"])
            verified_input_payloads[item_id] = _verified_record_bytes(
                internal["record"],
                label=(
                    "selected candidate MIDI"
                    if kind == "selected_midi"
                    else "source audio"
                ),
            )
        include_proxy = any(
            item["kind"] == "arrangement_proxy" for item in included_items
        )
        arrangement = (
            self.render_arrangement(catalog, current) if include_proxy else None
        )
        copied: list[dict[str, Any]] = []
        payloads: list[tuple[str, bytes]] = []
        for item in included_items:
            item_id = str(item["item_id"])
            kind = str(item["kind"])
            if kind == "arrangement_proxy":
                if arrangement is None:  # pragma: no cover - guarded above
                    raise RuntimeError("arrangement proxy was not prepared")
                proxy_records = (
                    (
                        "MIDI/selected-arrangement-proxy.mid",
                        arrangement["midi"],
                        "arrangement proxy MIDI",
                    ),
                    (
                        "PREVIEW/selected-arrangement-proxy.wav",
                        arrangement["preview"],
                        "arrangement proxy preview",
                    ),
                )
                for archive_path, record, label in proxy_records:
                    data = _verified_record_bytes(record, label=label)
                    payloads.append((archive_path, data))
                    copied.append(
                        _pack_manifest_item(
                            item_id=item_id,
                            kind=kind,
                            archive_path=archive_path,
                            data=data,
                        )
                    )
                continue
            data = verified_input_payloads[item_id]
            archive_path = str(item["archive_paths"][0])
            payloads.append((archive_path, data))
            copied.append(
                _pack_manifest_item(
                    item_id=item_id,
                    kind=kind,
                    archive_path=archive_path,
                    data=data,
                )
            )

        key_payload: dict[str, Any] = {
            "schema": GARAGEBAND_PACK_SCHEMA,
            "project_id": catalog.get("project_id"),
            "selection_sha256": plan["selection_sha256"],
            "basket_scope_sha256": plan["basket_scope_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "basket_sha256": canonical["basket_sha256"],
            "included_item_ids": list(canonical["included_item_ids"]),
        }
        if arrangement is not None:
            key_payload["arrangement_proxy"] = {
                "midi_sha256": arrangement["midi"]["sha256"],
                "preview_sha256": arrangement["preview"]["sha256"],
            }
        cache_key = _document_hash(key_payload)
        source_count = sum(item["kind"] == "source_audio" for item in included_items)
        midi_count = sum(item["kind"] == "selected_midi" for item in included_items)
        pack_manifest = {
            **key_payload,
            "cache_key": cache_key,
            "schema": GARAGEBAND_PACK_SCHEMA,
            "setup": dict(plan["setup"]),
            "included_items": copied,
            "selected_midi_count": midi_count,
            "source_audio_count": source_count,
            "source_audio_included": source_count > 0,
            "source_audio_opt_in": canonical["source_audio_opt_in"],
            "arrangement_proxy_included": include_proxy,
            "selected_midi_overlap": plan["selected_midi_overlap"],
            "selection_policy": (
                "the basket is explicit and separate from current musical "
                "main/optional decisions"
            ),
            "private_notes_included": False,
            "absolute_paths_included": False,
            "original_midi_mutated": False,
        }
        pack_dir = self.root / "packs" / cache_key
        zip_path = pack_dir / "sunofriend-garageband-pack.zip"
        manifest_path = pack_dir / "manifest.json"
        with self._lock:
            cached = self._load_pack(
                zip_path,
                manifest_path,
                expected_key_payload=key_payload,
                expected_pack_manifest=pack_manifest,
            )
            if cached is not None:
                cached["cache_hit"] = True
                return cached
            work = pack_dir.with_name(f".{pack_dir.name}.building-{uuid.uuid4().hex}")
            _remove_generated_path(pack_dir)
            work.mkdir(parents=True, exist_ok=False)
            try:
                zip_build = work / zip_path.name
                with zipfile.ZipFile(
                    zip_build, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    _zip_text(
                        archive,
                        "README.txt",
                        _garageband_pack_readme(
                            catalog,
                            selected_midi_count=midi_count,
                            source_audio_count=source_count,
                            arrangement_proxy_included=include_proxy,
                        ),
                    )
                    _zip_text(
                        archive,
                        "sunofriend-garageband-pack.json",
                        json.dumps(pack_manifest, indent=2, sort_keys=True) + "\n",
                    )
                    for archive_path, data in payloads:
                        _zip_bytes(archive, archive_path, data)
                acceptance_dir = work / "acceptance-review"
                acceptance = create_garageband_pack_acceptance_review(
                    zip_build,
                    acceptance_dir,
                )
                manifest = {
                    **pack_manifest,
                    "zip": _relative_file_record(zip_build, work),
                    "acceptance_review": _relative_file_record(
                        Path(acceptance["html"]), work
                    ),
                    "acceptance_seed": _relative_file_record(
                        Path(acceptance["seed"]), work
                    ),
                }
                _write_json(work / "manifest.json", manifest)
                work.replace(pack_dir)
            except Exception:
                shutil.rmtree(work, ignore_errors=True)
                raise
            result = self._load_pack(
                zip_path,
                manifest_path,
                expected_key_payload=key_payload,
                expected_pack_manifest=pack_manifest,
            )
            if result is None:
                raise RuntimeError("GarageBand pack cache verification failed")
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

    def _discard_new_preview(self, preview: Mapping[str, Any]) -> None:
        """Remove only a preview created by the current bounded operation."""

        cache_key = preview.get("cache_key")
        if preview.get("cache_hit") is not False or not _is_sha256(cache_key):
            return
        path = self.root / "previews" / str(cache_key)
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)

    def _find_cached(
        self,
        family: str,
        schema: str,
        expected: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        parent = self.root / family
        if not parent.is_dir():
            return None
        manifests: list[tuple[int, Path]] = []
        for path in parent.glob("*/manifest.json"):
            if not _is_sha256(path.parent.name):
                continue
            try:
                modified = path.stat().st_mtime_ns
            except OSError:
                continue
            manifests.append((modified, path))
        manifests.sort(key=lambda item: item[0], reverse=True)
        for _modified, path in manifests:
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

    def _balanced_cache_might_match(
        self,
        expected: Mapping[str, Any],
    ) -> bool:
        """Check small manifests before authenticating any large input file."""

        return bool(self._matching_balanced_cache_keys(expected))

    def _matching_balanced_cache_keys(
        self,
        expected: Mapping[str, Any],
    ) -> list[str]:
        """Return recent small-manifest matches without hashing large inputs."""

        parent = self.root / "balanced-arrangements"
        if not parent.is_dir():
            return []
        matches: list[tuple[int, str]] = []
        for path in parent.glob("*/manifest.json"):
            if not _is_sha256(path.parent.name):
                continue
            if _path_exists_or_is_symlink(path.parent / _BALANCED_DEFERRED_MARKER_NAME):
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                modified = path.stat().st_mtime_ns
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(document, Mapping):
                continue
            if all(document.get(key) == value for key, value in expected.items()):
                matches.append((modified, path.parent.name))
        matches.sort(reverse=True)
        return [cache_key for _modified, cache_key in matches]

    def _load_balanced_arrangement(
        self,
        cache_key: str,
        *,
        expected_key_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        root = self.root / "balanced-arrangements" / cache_key
        manifest_path = root / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        manifest_keys = {
            "schema",
            "project_id",
            "selection_manifest_sha256",
            "bpm",
            "policy",
            "render_horizon_policy",
            "soundfont_sha256",
            "selection",
            "renderer",
            "input_fingerprints",
            "cache_key",
            "preview",
            "report",
            "recipe",
            "mix_report",
            "render_horizon",
            "mastered",
            "mastering_boundary",
            "path_free_manifest",
            "private_audio",
            "effects",
            "manifest_sha256",
        }
        if not isinstance(document, dict) or set(document) != manifest_keys:
            return None
        manifest_sha256 = document.get("manifest_sha256")
        unsigned_manifest = {
            key: value for key, value in document.items() if key != "manifest_sha256"
        }
        if (
            not _is_sha256(manifest_sha256)
            or _document_hash(unsigned_manifest) != manifest_sha256
        ):
            return None
        if (
            document.get("schema") != BALANCED_ARRANGEMENT_SCHEMA
            or document.get("cache_key") != cache_key
        ):
            return None
        key_payload = {
            key: document.get(key)
            for key in (
                "schema",
                "project_id",
                "selection_manifest_sha256",
                "bpm",
                "policy",
                "render_horizon_policy",
                "soundfont_sha256",
                "selection",
                "renderer",
                "input_fingerprints",
            )
        }
        if _document_hash(key_payload) != cache_key:
            return None
        if (
            expected_key_payload is not None
            and dict(expected_key_payload) != key_payload
        ):
            return None
        if not _valid_balanced_manifest_semantics(document):
            return None
        result = dict(document)
        expected_artifact_names = {
            "preview": "balanced-selected-midi-preview.wav",
            "report": "balanced-mix-receipt.json",
            "recipe": "garageband-mix-recipe.md",
        }
        for key, expected_name in expected_artifact_names.items():
            record = document.get(key)
            if (
                not _valid_balanced_artifact_record(record)
                or record.get("path") != expected_name
                or record.get("name") != expected_name
            ):
                return None
            materialized = self._materialize_file_record(record, root)
            if materialized is None:
                return None
            result[key] = materialized
        try:
            recipe_text = Path(str(result["recipe"]["path"])).read_text(
                encoding="utf-8"
            )
            expected_recipe = garageband_mix_recipe(document["mix_report"])
        except (KeyError, OSError, TypeError, UnicodeError, ValueError):
            return None
        if recipe_text != expected_recipe:
            return None
        try:
            receipt = json.loads(
                Path(str(result["report"]["path"])).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return None
        if not _valid_balanced_receipt(receipt, document):
            return None
        try:
            _np, soundfile = _decoded_audio_modules()
            raw_wav_info = soundfile.info(str(result["preview"]["path"]))
            wav_info = _decoded_audio_info(
                soundfile,
                Path(str(result["preview"]["path"])),
                label="balanced selected-MIDI preview",
            )
            measured_output = measure_balanced_audio(
                Path(str(result["preview"]["path"]))
            )
        except (OSError, RuntimeError, ValueError):
            return None
        render_horizon = document["render_horizon"]
        mix_report = document["mix_report"]
        if (
            str(raw_wav_info.format) != "WAV"
            or str(raw_wav_info.subtype) != "PCM_24"
            or int(wav_info["sample_rate"]) != int(render_horizon["sample_rate"])
            or int(wav_info["frames"]) != int(render_horizon["output_frames"])
            or int(wav_info["sample_rate"]) != int(mix_report["sample_rate"])
            or int(wav_info["channels"]) != int(mix_report["channels"])
            or int(wav_info["frames"]) != int(mix_report["frames"])
            or int(mix_report["output"]["pre_master"]["frames"])
            != int(wav_info["frames"])
            or int(mix_report["output"]["post_master"]["frames"])
            != int(wav_info["frames"])
            or measured_output != mix_report["output"]["post_master"]
        ):
            return None
        result["receipt"] = receipt
        return result

    def _remember_verified_balanced_arrangement(
        self,
        *,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        result: Mapping[str, Any],
        source_groups: Sequence[Mapping[str, Any]],
        selection: Sequence[Mapping[str, Any]],
        previews: Sequence[Mapping[str, Any]],
        soundfont: Mapping[str, Any],
    ) -> None:
        """Remember one fully hash-verified balance behind cheap stat guards."""

        cache_key = str(result.get("cache_key", ""))
        if not _is_sha256(cache_key):
            return
        try:
            selection_manifest, expected_groups, expected_selection = (
                _decoded_arrangement_selection(catalog, current)
            )
            if (
                expected_groups != list(source_groups)
                or expected_selection != list(selection)
                or selection_manifest.get("selection_manifest_sha256")
                != result.get("selection_manifest_sha256")
            ):
                raise ValueError("balanced arrangement current binding changed")
            expected_key_payload = _balanced_key_payload(
                catalog=catalog,
                selection_manifest_sha256=str(
                    selection_manifest["selection_manifest_sha256"]
                ),
                source_groups=source_groups,
                selection=selection,
                previews=previews,
                soundfont=soundfont,
            )
            if result.get("cache_key") != _document_hash(expected_key_payload) or any(
                result.get(key) != value for key, value in expected_key_payload.items()
            ):
                raise ValueError("balanced arrangement input fingerprints changed")
            binding = _balanced_verification_binding(
                selection_manifest=selection_manifest,
                source_groups=source_groups,
                selection=selection,
                soundfont=soundfont,
            )
            files: dict[Path, int] = {}

            def add_record(record: Mapping[str, Any], *, label: str) -> None:
                path = Path(str(record.get("path", ""))).resolve()
                byte_count = record.get("bytes")
                if not _valid_nonnegative_int(byte_count):
                    raise ValueError(f"{label} byte count is invalid")
                files[path] = int(byte_count)

            for group in source_groups:
                for record in group["records"]:
                    add_record(record, label="source audio")
            for item in selection:
                add_record(item["midi"], label="selected candidate MIDI")
            add_record(soundfont, label="SoundFont")
            for preview in previews:
                preview_record = preview.get("preview")
                midi_record = preview.get("midi")
                if not isinstance(preview_record, Mapping) or not isinstance(
                    midi_record, Mapping
                ):
                    raise ValueError("neutral preview evidence is invalid")
                add_record(preview_record, label="neutral preview")
                add_record(midi_record, label="neutral preview MIDI")
                preview_root = Path(str(preview_record["path"])).resolve().parent
                preview_manifest = preview_root / "manifest.json"
                files[preview_manifest] = preview_manifest.stat().st_size
            for key in ("preview", "report", "recipe"):
                record = result.get(key)
                if not isinstance(record, Mapping):
                    raise ValueError("balanced artifact record is invalid")
                add_record(record, label=f"balanced {key}")
            manifest = (
                Path(str(result["preview"]["path"])).resolve().parent / "manifest.json"
            )
            files[manifest] = manifest.stat().st_size
            signatures = {
                str(path): _regular_file_stat_signature(path, expected_bytes)
                for path, expected_bytes in files.items()
            }
        except (KeyError, OSError, TypeError, ValueError):
            self._verified_balanced_cache.pop(cache_key, None)
            return
        self._verified_balanced_cache.pop(cache_key, None)
        self._verified_balanced_cache[cache_key] = {
            "binding": binding,
            "result": json.loads(json.dumps(result)),
            "files": {str(path): size for path, size in files.items()},
            "signatures": signatures,
        }
        while len(self._verified_balanced_cache) > _BALANCED_CACHE_MAXIMUM_ENTRIES:
            oldest = next(iter(self._verified_balanced_cache))
            self._verified_balanced_cache.pop(oldest, None)

    def _cached_verified_balanced_arrangement(
        self,
        *,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        cache_key: str,
    ) -> dict[str, Any] | None:
        cached = self._verified_balanced_cache.get(cache_key)
        if cached is None:
            return None
        try:
            if self._soundfont_cache is None:
                raise ValueError("balanced SoundFont identity is not cached")
            selection_manifest, source_groups, selection = (
                _decoded_arrangement_selection(catalog, current)
            )
            binding = _balanced_verification_binding(
                selection_manifest=selection_manifest,
                source_groups=source_groups,
                selection=selection,
                soundfont=self._soundfont_cache,
            )
            if binding != cached["binding"]:
                raise ValueError("balanced arrangement current binding changed")
            files = cached["files"]
            signatures = {
                path: _regular_file_stat_signature(
                    Path(path),
                    int(expected_bytes),
                )
                for path, expected_bytes in files.items()
            }
            if signatures != cached["signatures"]:
                raise ValueError("balanced arrangement file identity changed")
        except (KeyError, OSError, TypeError, ValueError):
            self._verified_balanced_cache.pop(cache_key, None)
            return None
        self._verified_balanced_cache.pop(cache_key, None)
        self._verified_balanced_cache[cache_key] = cached
        return json.loads(json.dumps(cached["result"]))

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

    def _verify_decoded_loop_inputs(
        self,
        *,
        source_record: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        previews: Sequence[Mapping[str, Any]],
        expected_soundfont_sha256: str,
    ) -> None:
        self._verify_catalog_record(source_record, label="source audio")
        for candidate in candidates:
            self._verify_catalog_record(candidate["midi"], label="candidate MIDI")
        self._require_preview_renderer_consistency(
            previews,
            expected_soundfont_sha256=expected_soundfont_sha256,
        )
        for preview in previews:
            record = preview.get("preview")
            if not isinstance(record, Mapping):
                raise ValueError("neutral candidate preview record is invalid")
            self._verify_catalog_record(record, label="neutral candidate preview")

    def _verify_decoded_arrangement_inputs(
        self,
        *,
        source_groups: Sequence[Mapping[str, Any]],
        selection: Sequence[Mapping[str, Any]],
        previews: Sequence[Mapping[str, Any]],
        expected_soundfont_sha256: str,
    ) -> None:
        for group in source_groups:
            for record in group["records"]:
                self._verify_catalog_record(record, label="source audio")
        self._verify_selection(selection)
        self._require_preview_renderer_consistency(
            previews,
            expected_soundfont_sha256=expected_soundfont_sha256,
        )
        for preview in previews:
            record = preview.get("preview")
            if not isinstance(record, Mapping):
                raise ValueError("neutral selected MIDI preview record is invalid")
            self._verify_catalog_record(record, label="neutral selected MIDI preview")

    def _verify_decoded_arrangement_stream_current(
        self,
        *,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        stream: Mapping[str, Any],
        prepared_previews: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Fail closed when the canonical selection or any stream input changed."""

        (
            selection_manifest,
            source_groups,
            selection,
        ) = _decoded_arrangement_selection(catalog, current)
        selection_manifest_sha256 = stream.get("selection_manifest_sha256")
        _require_decoded_arrangement_selection_hash(
            selection_manifest, selection_manifest_sha256
        )
        preset = _decoded_arrangement_stream_preset(stream.get("preset"))
        expected_track_ids = list(selection_manifest["groups"][preset])
        if stream.get("preset_track_ids") != expected_track_ids:
            raise ValueError(
                "decoded arrangement stream no longer matches the canonical preset"
            )
        tracks = stream.get("tracks")
        source_clock = stream.get("source_clock")
        if not isinstance(tracks, list) or not isinstance(source_clock, list):
            raise ValueError("decoded arrangement stream plan is invalid")
        if [track.get("track_id") for track in tracks] != expected_track_ids:
            raise ValueError(
                "decoded arrangement stream track roster is no longer canonical"
            )

        _np, soundfile = _decoded_audio_modules()
        expected_source_clock: list[dict[str, Any]] = []
        source_by_track_id: dict[str, Mapping[str, Any]] = {}
        for group in source_groups:
            for record in group["records"]:
                self._verify_catalog_record(record, label="source audio")
            record = group["records"][0]
            path = self._verify_catalog_record(record, label="source audio")
            info = _decoded_audio_info(soundfile, path, label="source audio")
            track_id = str(group["track_id"])
            source_by_track_id[track_id] = group
            expected_source_clock.append(
                {
                    "track_id": track_id,
                    "source_sha256": str(record["sha256"]),
                    "source_bytes": int(record["bytes"]),
                    "sample_rate": int(info["sample_rate"]),
                    "channels": int(info["channels"]),
                    "frames": int(info["frames"]),
                }
            )
        if source_clock != expected_source_clock:
            raise ValueError("decoded arrangement source duration evidence changed")
        anchor = stream.get("anchor")
        if not isinstance(anchor, Mapping) or not expected_source_clock:
            raise ValueError("decoded arrangement stream anchor is invalid")
        longest_source = _longest_decoded_source(expected_source_clock)
        anchor_sample_rate = int(expected_source_clock[0]["sample_rate"])
        anchor_song_end_frame = _ceil_scaled_frame(
            int(longest_source["frames"]),
            anchor_sample_rate,
            int(longest_source["sample_rate"]),
        )
        expected_anchor = {
            "sample_rate": anchor_sample_rate,
            "song_end_frame": anchor_song_end_frame,
            "duration_seconds": anchor_song_end_frame / anchor_sample_rate,
            "longest_source_track_id": longest_source["track_id"],
        }
        if dict(anchor) != expected_anchor:
            raise ValueError("decoded arrangement stream anchor evidence changed")

        selection_by_track_id = {str(item["track_id"]): item for item in selection}
        midi_tracks = [
            track for track in tracks if track.get("kind") == "selected_midi"
        ]
        if not midi_tracks:
            if preset != "source-only" or stream.get("renderer") is not None:
                raise ValueError("decoded arrangement stream renderer plan is invalid")
        else:
            relevant_selection: list[Mapping[str, Any]] = []
            for track in midi_tracks:
                selected = selection_by_track_id.get(str(track.get("track_id")))
                if selected is None:
                    raise ValueError("decoded arrangement selected MIDI roster changed")
                expected_identity = {
                    "track_id": str(selected["track_id"]),
                    "kind": "selected_midi",
                    "stem_id": str(selected["stem_id"]),
                    "candidate_id": str(selected["candidate_id"]),
                    "role": str(selected["role"]),
                    "decision": str(selected["decision"]),
                    "source_midi_sha256": str(selected["midi"]["sha256"]),
                }
                if any(
                    track.get(key) != value for key, value in expected_identity.items()
                ):
                    raise ValueError(
                        "decoded arrangement selected MIDI identity changed"
                    )
                relevant_selection.append(selected)
            self._verify_selection(relevant_selection)
            soundfont = self._soundfont()
            renderer = stream.get("renderer")
            if renderer != {
                "policy": _RENDER_POLICY,
                "soundfont_sha256": str(soundfont["sha256"]),
            }:
                raise ValueError(
                    "decoded arrangement stream requires the current SoundFont "
                    "and neutral renderer policy"
                )
            for track, selected in zip(midi_tracks, relevant_selection):
                track_id = str(track["track_id"])
                preview = (
                    prepared_previews.get(track_id)
                    if prepared_previews is not None
                    else self.cached_candidate_preview(
                        catalog,
                        str(selected["stem_id"]),
                        str(selected["candidate_id"]),
                        role_override=str(selected["role"]),
                    )
                )
                if preview is None:
                    raise ValueError(
                        "decoded arrangement neutral MIDI preview is missing or changed"
                    )
                self._require_preview_renderer_consistency(
                    [preview],
                    expected_soundfont_sha256=str(soundfont["sha256"]),
                )
                preview_record = preview.get("preview")
                if not isinstance(preview_record, Mapping):
                    raise ValueError(
                        "decoded arrangement neutral MIDI preview record is invalid"
                    )
                self._verify_catalog_record(
                    preview_record, label="neutral selected MIDI preview"
                )
                expected_preview = {
                    "neutral_preview_cache_key": str(preview["cache_key"]),
                    "neutral_preview_policy": str(preview["policy"]),
                    "soundfont_sha256": str(preview["soundfont_sha256"]),
                    "input_sha256": str(preview_record["sha256"]),
                    "input_bytes": int(preview_record["bytes"]),
                }
                if any(
                    track.get(key) != value for key, value in expected_preview.items()
                ):
                    raise ValueError("decoded arrangement neutral MIDI preview changed")

        for track in tracks:
            if track.get("kind") != "source":
                continue
            group = source_by_track_id.get(str(track.get("track_id")))
            if group is None:
                raise ValueError("decoded arrangement source roster changed")
            record = group["records"][0]
            clock = next(
                row
                for row in expected_source_clock
                if row["track_id"] == track["track_id"]
            )
            expected_source = {
                "kind": "source",
                "stem_ids": list(group["stem_ids"]),
                "roles": list(group["roles"]),
                "source_sha256": str(record["sha256"]),
                "input_sha256": str(record["sha256"]),
                "input_bytes": int(record["bytes"]),
                "sample_rate": int(clock["sample_rate"]),
                "channels": int(clock["channels"]),
                "input_frames": int(clock["frames"]),
            }
            if any(track.get(key) != value for key, value in expected_source.items()):
                raise ValueError("decoded arrangement source stream input changed")

    def _require_preview_renderer_consistency(
        self,
        previews: Sequence[Mapping[str, Any]],
        *,
        expected_soundfont_sha256: str,
    ) -> None:
        if not previews:
            raise ValueError("decoded comparison requires at least one preview")
        for preview in previews:
            if (
                preview.get("schema") != NEUTRAL_PREVIEW_SCHEMA
                or preview.get("policy") != _RENDER_POLICY
                or preview.get("soundfont_sha256") != expected_soundfont_sha256
            ):
                raise ValueError(
                    "decoded comparison requires every MIDI preview to use the "
                    "same current SoundFont and neutral renderer policy"
                )

    def _decoded_arrangement_stream_verification_evidence(
        self,
        *,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        stream: Mapping[str, Any],
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> tuple[str, dict[Path, int | None]]:
        """Describe cheap evidence for a stream which was fully hash-verified."""

        selection_manifest, source_groups, selection = _decoded_arrangement_selection(
            catalog, current
        )
        _require_decoded_arrangement_selection_hash(
            selection_manifest, stream.get("selection_manifest_sha256")
        )
        preset = _decoded_arrangement_stream_preset(stream.get("preset"))
        expected_track_ids = list(selection_manifest["groups"][preset])
        tracks = stream.get("tracks")
        if (
            stream.get("preset_track_ids") != expected_track_ids
            or not isinstance(tracks, list)
            or [track.get("track_id") for track in tracks] != expected_track_ids
        ):
            raise ValueError("decoded arrangement stream roster changed")

        files: dict[Path, int | None] = {}

        def add_file(path: Path, expected_bytes: int | None = None) -> None:
            resolved = path.expanduser().resolve()
            existing = files.get(resolved)
            if existing is not None and expected_bytes is not None:
                if existing != expected_bytes:
                    raise ValueError("decoded arrangement stream file size conflicts")
            elif resolved not in files or expected_bytes is not None:
                files[resolved] = expected_bytes

        def record_identity(record: Mapping[str, Any]) -> dict[str, Any]:
            path = Path(str(record.get("path", ""))).expanduser().resolve()
            expected_bytes = record.get("bytes")
            if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int):
                raise ValueError("decoded arrangement stream record size is invalid")
            add_file(path, expected_bytes)
            return {
                "path": str(path),
                "bytes": expected_bytes,
                "sha256": record.get("sha256"),
            }

        source_identity = [
            {
                "track_id": group.get("track_id"),
                "records": [record_identity(record) for record in group["records"]],
            }
            for group in source_groups
        ]
        selection_by_track_id = {str(item["track_id"]): item for item in selection}
        midi_identity: list[dict[str, Any]] = []
        preview_identity: list[dict[str, Any]] = []
        for track in tracks:
            if track.get("kind") != "selected_midi":
                continue
            track_id = str(track.get("track_id"))
            selected = selection_by_track_id.get(track_id)
            if selected is None:
                raise ValueError("decoded arrangement selected MIDI roster changed")
            midi_identity.append(
                {
                    "track_id": track_id,
                    "stem_id": selected.get("stem_id"),
                    "candidate_id": selected.get("candidate_id"),
                    "role": selected.get("role"),
                    "decision": selected.get("decision"),
                    "midi": record_identity(selected["midi"]),
                }
            )
            preview_root = (
                self.root / "previews" / str(track.get("neutral_preview_cache_key", ""))
            )
            add_file(preview_root / "manifest.json")
            add_file(preview_root / "neutral-preview.mid")
            add_file(preview_root / "neutral-preview.wav", int(track["input_bytes"]))
            preview_identity.append(
                {
                    key: track.get(key)
                    for key in (
                        "track_id",
                        "neutral_preview_cache_key",
                        "neutral_preview_policy",
                        "soundfont_sha256",
                        "input_sha256",
                        "input_bytes",
                    )
                }
            )

        soundfont_identity: dict[str, Any] | None = None
        if midi_identity:
            if self._soundfont_cache is None:
                raise ValueError("decoded arrangement SoundFont is not verified")
            soundfont_identity = record_identity(self._soundfont_cache)

        stream_sha256 = str(stream.get("stream_sha256", ""))
        stream_root = self.root / "decoded-arrangement-streams" / stream_sha256
        if stream_root.is_symlink() or (stream_root / "inputs").is_symlink():
            raise ValueError("decoded arrangement stream storage is unsafe")
        add_file(stream_root / "manifest.json")
        add_file(stream_root / "record.json")
        snapshot_identity: list[dict[str, Any]] = []
        for track_id in expected_track_ids:
            snapshot = snapshots.get(str(track_id))
            if not isinstance(snapshot, Mapping):
                raise ValueError("decoded arrangement stream snapshot roster changed")
            snapshot_identity.append(
                {"track_id": track_id, "snapshot": record_identity(snapshot)}
            )

        identity = _document_hash(
            {
                "stream_sha256": stream_sha256,
                "selection_manifest": selection_manifest,
                "sources": source_identity,
                "selected_midi": midi_identity,
                "previews": preview_identity,
                "soundfont": soundfont_identity,
                "snapshots": snapshot_identity,
            }
        )
        return identity, files

    def _remember_verified_decoded_arrangement_stream(
        self,
        *,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        stream: Mapping[str, Any],
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> None:
        stream_sha256 = str(stream.get("stream_sha256", ""))
        try:
            identity, files = self._decoded_arrangement_stream_verification_evidence(
                catalog=catalog,
                current=current,
                stream=stream,
                snapshots=snapshots,
            )
            signatures = {
                str(path): _regular_file_stat_signature(path, expected_bytes)
                for path, expected_bytes in files.items()
            }
        except (OSError, TypeError, ValueError):
            self._verified_stream_cache.pop(stream_sha256, None)
            return
        self._verified_stream_cache.pop(stream_sha256, None)
        self._verified_stream_cache[stream_sha256] = {
            "identity": identity,
            "stream": json.loads(json.dumps(stream)),
            "snapshots": json.loads(json.dumps(snapshots)),
            "files": {str(path): expected for path, expected in files.items()},
            "signatures": signatures,
        }
        while len(self._verified_stream_cache) > _VERIFIED_STREAM_CACHE_MAXIMUM_ENTRIES:
            oldest = next(iter(self._verified_stream_cache))
            self._verified_stream_cache.pop(oldest, None)

    def _cached_verified_decoded_arrangement_stream(
        self,
        *,
        catalog: Mapping[str, Any],
        current: Mapping[str, Any],
        stream_sha256: str,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]] | None:
        cached = self._verified_stream_cache.get(stream_sha256)
        if cached is None:
            return None
        try:
            stream = cached["stream"]
            snapshots = cached["snapshots"]
            identity, files = self._decoded_arrangement_stream_verification_evidence(
                catalog=catalog,
                current=current,
                stream=stream,
                snapshots=snapshots,
            )
            if (
                identity != cached["identity"]
                or {str(path): expected for path, expected in files.items()}
                != cached["files"]
            ):
                raise ValueError("decoded arrangement stream identity changed")
            signatures = {
                str(path): _regular_file_stat_signature(path, expected_bytes)
                for path, expected_bytes in files.items()
            }
            if signatures != cached["signatures"]:
                raise ValueError("decoded arrangement stream file identity changed")
        except (KeyError, OSError, TypeError, ValueError):
            self._verified_stream_cache.pop(stream_sha256, None)
            return None
        self._verified_stream_cache.pop(stream_sha256, None)
        self._verified_stream_cache[stream_sha256] = cached
        return (
            json.loads(json.dumps(stream)),
            json.loads(json.dumps(snapshots)),
        )

    def _touch_and_prune_decoded_loop_cache(self, keep_cache_key: str) -> None:
        self._touch_and_prune_decoded_cache("decoded-stem-loops", keep_cache_key)

    def _touch_and_prune_decoded_stream_cache(self, keep_stream_sha256: str) -> None:
        """Bound private full-song snapshots independently from decoded chunks."""

        parent = self.root / "decoded-arrangement-streams"
        current = parent / keep_stream_sha256
        try:
            if current.is_dir() and not current.is_symlink():
                current.touch(exist_ok=True)
        except OSError:
            pass

        try:
            children = list(parent.iterdir())
        except OSError:
            return

        entries: list[tuple[Path, int, int]] = []
        for path in children:
            if not _is_sha256(path.name):
                continue
            try:
                if path.is_symlink() or not path.is_dir():
                    continue
                modified_ns = path.stat().st_mtime_ns
                entry_bytes = _directory_regular_file_bytes(path)
            except OSError:
                continue
            entries.append((path, modified_ns, entry_bytes))

        entries.sort(
            key=lambda entry: (entry[0] == current, entry[1]),
            reverse=True,
        )
        retained_entries = 0
        retained_bytes = 0
        for entry, _modified_ns, entry_bytes in entries:
            keep = entry == current or (
                retained_entries < _DECODED_STREAM_CACHE_MAXIMUM_ENTRIES
                and retained_bytes + entry_bytes <= _DECODED_STREAM_CACHE_MAXIMUM_BYTES
            )
            if keep:
                retained_entries += 1
                retained_bytes += entry_bytes
                continue
            try:
                _remove_generated_path(entry)
            except OSError:
                # Another request or cleanup may have removed or changed it.
                pass
            self._verified_stream_cache.pop(entry.name, None)
        for cached_sha256 in tuple(self._verified_stream_cache):
            cached_root = parent / cached_sha256
            try:
                retained = cached_root.is_dir() and not cached_root.is_symlink()
            except OSError:
                retained = False
            if not retained:
                self._verified_stream_cache.pop(cached_sha256, None)

    def _touch_and_prune_decoded_cache(
        self, keep_family: str, keep_cache_key: str
    ) -> None:
        families = (
            "decoded-stem-loops",
            "decoded-arrangement-loops",
            "decoded-arrangement-chunks",
        )
        if keep_family not in families:
            raise ValueError("unknown decoded cache family")
        current = self.root / keep_family / keep_cache_key
        if current.is_dir() and not current.is_symlink():
            current.touch(exist_ok=True)
        entries: list[Path] = []
        for family in families:
            parent = self.root / family
            if not parent.is_dir():
                continue
            entries.extend(
                path
                for path in parent.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and len(path.name) == 64
                and all(character in "0123456789abcdef" for character in path.name)
            )
        entries.sort(
            key=lambda path: (path == current, path.stat().st_mtime_ns),
            reverse=True,
        )
        retained_entries = 0
        retained_bytes = 0
        for entry in entries:
            entry_bytes = _directory_regular_file_bytes(entry)
            keep = entry == current or (
                retained_entries < _DECODED_LOOP_CACHE_MAXIMUM_ENTRIES
                and retained_bytes + entry_bytes <= _DECODED_LOOP_CACHE_MAXIMUM_BYTES
            )
            if keep:
                retained_entries += 1
                retained_bytes += entry_bytes
                continue
            _remove_generated_path(entry)

    def _touch_and_prune_balanced_cache(self, keep_cache_key: str) -> None:
        self._reclaim_stale_balanced_deferred_caches()
        parent = self.root / "balanced-arrangements"
        current = parent / keep_cache_key
        if current.is_dir() and not current.is_symlink():
            current.touch(exist_ok=True)
        if not parent.is_dir():
            return
        entries = [
            path
            for path in parent.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and _is_sha256(path.name)
            and not _path_exists_or_is_symlink(path / _BALANCED_DEFERRED_MARKER_NAME)
        ]
        entries.sort(
            key=lambda path: (path == current, path.stat().st_mtime_ns),
            reverse=True,
        )
        retained_entries = 0
        retained_bytes = 0
        for entry in entries:
            entry_bytes = _directory_regular_file_bytes(entry)
            keep = entry == current or (
                retained_entries < _BALANCED_CACHE_MAXIMUM_ENTRIES
                and retained_bytes + entry_bytes <= _BALANCED_CACHE_MAXIMUM_BYTES
            )
            if keep:
                retained_entries += 1
                retained_bytes += entry_bytes
                continue
            _remove_generated_path(entry)
            self._verified_balanced_cache.pop(entry.name, None)
        for cached_key in tuple(self._verified_balanced_cache):
            cached_root = parent / cached_key
            if not cached_root.is_dir() or cached_root.is_symlink():
                self._verified_balanced_cache.pop(cached_key, None)

    def _private_building_directory(
        self, family: str, cache_key: str
    ) -> tuple[Path, Path]:
        parent = self.root / family
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _restrict_private_permissions(parent, 0o700)
        if family in {
            "decoded-stem-loops",
            "decoded-arrangement-loops",
            "decoded-arrangement-streams",
            "decoded-arrangement-chunks",
            "balanced-arrangements",
        }:
            _prune_stale_private_builds(parent)
        final = parent / cache_key
        if family == "decoded-arrangement-streams":
            self._verified_stream_cache.pop(cache_key, None)
        if family == "balanced-arrangements":
            self._verified_balanced_cache.pop(cache_key, None)
        _remove_generated_path(final)
        work = parent / f".{cache_key}.building-{uuid.uuid4().hex}"
        work.mkdir(mode=0o700, parents=False, exist_ok=False)
        _restrict_private_permissions(work, 0o700)
        return work, final

    def _load_decoded_stem_loop(
        self,
        cache_key: str,
        expected_key_payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        root = self.root / "decoded-stem-loops" / cache_key
        manifest_path = root / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            document.get("schema") != DECODED_STEM_LOOP_SCHEMA
            or document.get("cache_key") != cache_key
            or root.name != cache_key
            or any(
                document.get(key) != value
                for key, value in expected_key_payload.items()
            )
        ):
            return None
        expected_window = expected_key_payload.get("window")
        if not isinstance(expected_window, Mapping) or (
            document.get("start_seconds")
            != expected_window.get("quantized_start_seconds")
            or document.get("end_seconds")
            != expected_window.get("quantized_end_seconds")
            or document.get("duration_seconds")
            != expected_window.get("logical_duration_seconds")
            or document.get("maximum_output_bytes")
            != _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
            or document.get("path_free_manifest") is not True
            or document.get("private_audio") is not True
            or document.get("effects")
            != {
                "midi_mutated": False,
                "selection_changed": False,
                "feedback_recorded": False,
                "event_appended": False,
            }
        ):
            return None
        records = document.get("tracks")
        fingerprints = expected_key_payload.get("input_fingerprints")
        if (
            not isinstance(records, list)
            or not isinstance(fingerprints, list)
            or len(records) != 1 + len(expected_key_payload.get("candidate_ids", []))
            or len(records) != len(fingerprints)
        ):
            return None
        materialized_tracks: list[dict[str, Any]] = []
        aggregate_bytes = 0
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                return None
            fingerprint = fingerprints[index]
            if not isinstance(fingerprint, Mapping):
                return None
            audio = record.get("audio")
            if not isinstance(audio, Mapping):
                return None
            relative_path = Path(str(audio.get("path", "")))
            if relative_path.is_absolute() or len(relative_path.parts) != 1:
                return None
            expected_kind = "source" if index == 0 else "candidate"
            if (
                record.get("kind") != expected_kind
                or record.get("track_id")
                != ("source" if index == 0 else f"candidate-{index}")
                or not isinstance(record.get("sample_rate"), int)
                or not isinstance(record.get("channels"), int)
                or not isinstance(record.get("frames"), int)
                or int(record["frames"]) <= 0
                or record.get("sample_rate") != fingerprint.get("sample_rate")
                or record.get("channels") != fingerprint.get("channels")
                or record.get("start_frame") != fingerprint.get("start_frame")
                or record.get("frames")
                != int(fingerprint.get("end_frame", 0))
                - int(fingerprint.get("start_frame", 0))
            ):
                return None
            if (
                index > 0
                and record.get("candidate_id")
                != expected_key_payload.get("candidate_ids", [])[index - 1]
            ):
                return None
            materialized_audio = self._materialize_file_record(audio, root)
            if materialized_audio is None:
                return None
            expected_audition_level = _decoded_stem_audition_level(
                Path(str(materialized_audio["path"]))
            )
            if (
                record.get("audition_level") != expected_audition_level
                or record.get("audition_gain_db")
                != expected_audition_level["applied_gain_db"]
            ):
                return None
            aggregate_bytes += int(materialized_audio["bytes"])
            materialized_track = dict(record)
            materialized_track["audio"] = materialized_audio
            materialized_tracks.append(materialized_track)
        if (
            aggregate_bytes != document.get("aggregate_output_bytes")
            or aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
        ):
            return None
        _restrict_private_permissions(root, 0o700)
        _restrict_private_permissions(manifest_path, 0o600)
        for track in materialized_tracks:
            _restrict_private_permissions(Path(track["audio"]["path"]), 0o600)
        result = dict(document)
        result["tracks"] = materialized_tracks
        return result

    def _load_decoded_arrangement_loop(
        self,
        cache_key: str,
        expected_key_payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        root = self.root / "decoded-arrangement-loops" / cache_key
        manifest_path = root / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            document.get("schema") != DECODED_ARRANGEMENT_LOOP_SCHEMA
            or document.get("cache_key") != cache_key
            or root.name != cache_key
            or any(
                document.get(key) != value
                for key, value in expected_key_payload.items()
            )
        ):
            return None
        expected_window = expected_key_payload.get("window")
        if not isinstance(expected_window, Mapping) or (
            document.get("start_seconds")
            != expected_window.get("quantized_start_seconds")
            or document.get("end_seconds")
            != expected_window.get("quantized_end_seconds")
            or document.get("duration_seconds")
            != expected_window.get("logical_duration_seconds")
            or document.get("maximum_output_bytes")
            != _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
            or document.get("path_free_manifest") is not True
            or document.get("private_audio") is not True
            or document.get("effects") != _decoded_arrangement_effects()
        ):
            return None
        records = document.get("tracks")
        fingerprints = expected_key_payload.get("input_fingerprints")
        if (
            not isinstance(records, list)
            or not isinstance(fingerprints, list)
            or len(records) != len(fingerprints)
            or len(records) < 2
            or len(records) > _DECODED_ARRANGEMENT_MAXIMUM_TRACKS
        ):
            return None
        identity_keys = (
            "track_id",
            "kind",
            "stem_ids",
            "roles",
            "source_sha256",
            "stem_id",
            "candidate_id",
            "role",
            "decision",
            "source_midi_sha256",
        )
        materialized_tracks: list[dict[str, Any]] = []
        aggregate_bytes = 0
        for record, fingerprint in zip(records, fingerprints):
            if not isinstance(record, Mapping) or not isinstance(fingerprint, Mapping):
                return None
            audio = record.get("audio")
            if not isinstance(audio, Mapping):
                return None
            relative_path = Path(str(audio.get("path", "")))
            expected_frames = int(fingerprint.get("end_frame", 0)) - int(
                fingerprint.get("start_frame", 0)
            )
            silence_padded = record.get("silence_padded_frames")
            if (
                relative_path.is_absolute()
                or len(relative_path.parts) != 1
                or record.get("kind") not in {"source", "selected_midi"}
                or any(
                    record.get(key) != fingerprint.get(key)
                    for key in identity_keys
                    if key in fingerprint
                )
                or record.get("sample_rate") != fingerprint.get("sample_rate")
                or record.get("channels") != fingerprint.get("channels")
                or record.get("start_frame") != fingerprint.get("start_frame")
                or record.get("frames") != expected_frames
                or not isinstance(silence_padded, int)
                or isinstance(silence_padded, bool)
                or silence_padded < 0
                or silence_padded > expected_frames
            ):
                return None
            materialized_audio = self._materialize_file_record(audio, root)
            if materialized_audio is None:
                return None
            aggregate_bytes += int(materialized_audio["bytes"])
            materialized_track = dict(record)
            materialized_track["audio"] = materialized_audio
            materialized_tracks.append(materialized_track)
        if (
            aggregate_bytes != document.get("aggregate_output_bytes")
            or aggregate_bytes > _DECODED_LOOP_MAXIMUM_OUTPUT_BYTES
        ):
            return None
        expected_ids = {
            str(track_id)
            for group in expected_key_payload.get("groups", {}).values()
            for track_id in group
        }
        if expected_ids != {str(track["track_id"]) for track in materialized_tracks}:
            return None
        _restrict_private_permissions(root, 0o700)
        _restrict_private_permissions(manifest_path, 0o600)
        for track in materialized_tracks:
            _restrict_private_permissions(Path(track["audio"]["path"]), 0o600)
        result = dict(document)
        result["tracks"] = materialized_tracks
        return result

    def _load_decoded_arrangement_stream(
        self,
        stream_sha256: str,
        *,
        expected_manifest: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]] | None:
        root = self.root / "decoded-arrangement-streams" / stream_sha256
        manifest_path = root / "manifest.json"
        record_path = root / "record.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            private_record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        unhashed_manifest = {
            key: value for key, value in manifest.items() if key != "stream_sha256"
        }
        if (
            manifest.get("schema") != DECODED_ARRANGEMENT_STREAM_SCHEMA
            or manifest.get("stream_sha256") != stream_sha256
            or root.name != stream_sha256
            or _document_hash(unhashed_manifest) != stream_sha256
            or manifest.get("path_free_manifest") is not True
            or manifest.get("private_audio") is not True
            or manifest.get("effects") != _decoded_arrangement_effects()
            or (
                expected_manifest is not None
                and dict(manifest) != dict(expected_manifest)
            )
        ):
            return None
        preset = manifest.get("preset")
        try:
            _decoded_arrangement_stream_preset(preset)
        except ValueError:
            return None
        tracks = manifest.get("tracks")
        preset_track_ids = manifest.get("preset_track_ids")
        chunking = manifest.get("chunking")
        anchor = manifest.get("anchor")
        if (
            not isinstance(tracks, list)
            or not 1 <= len(tracks) <= _DECODED_ARRANGEMENT_MAXIMUM_TRACKS
            or not isinstance(preset_track_ids, list)
            or preset_track_ids != [track.get("track_id") for track in tracks]
            or len(set(preset_track_ids)) != len(preset_track_ids)
            or not isinstance(chunking, Mapping)
            or not isinstance(anchor, Mapping)
            or not _valid_decoded_stream_chunk_plan(chunking, anchor, tracks)
        ):
            return None
        if private_record != {
            "schema": "sunofriend.workbench-decoded-arrangement-stream-record.v1",
            "stream_sha256": stream_sha256,
            "manifest_sha256": _document_hash(manifest),
            "inputs": private_record.get("inputs"),
        }:
            return None
        records = private_record.get("inputs")
        if not isinstance(records, list) or len(records) != len(tracks):
            return None
        snapshots: dict[str, dict[str, Any]] = {}
        for track, record in zip(tracks, records):
            if not isinstance(track, Mapping) or not isinstance(record, Mapping):
                return None
            track_id = track.get("track_id")
            snapshot = record.get("snapshot")
            if record.get("track_id") != track_id or not isinstance(snapshot, Mapping):
                return None
            relative_path = Path(str(snapshot.get("path", "")))
            if (
                relative_path.is_absolute()
                or len(relative_path.parts) != 2
                or relative_path.parts[0] != "inputs"
                or relative_path.name != f"{track.get('input_sha256')}.audio"
                or snapshot.get("sha256") != track.get("input_sha256")
                or snapshot.get("bytes") != track.get("input_bytes")
            ):
                return None
            materialized = self._materialize_file_record(snapshot, root)
            if materialized is None:
                return None
            snapshots[str(track_id)] = materialized
        if set(snapshots) != set(preset_track_ids):
            return None
        _restrict_private_permissions(root, 0o700)
        _restrict_private_permissions(manifest_path, 0o600)
        _restrict_private_permissions(record_path, 0o600)
        input_root = root / "inputs"
        if input_root.is_dir() and not input_root.is_symlink():
            _restrict_private_permissions(input_root, 0o700)
        for snapshot in snapshots.values():
            _restrict_private_permissions(Path(snapshot["path"]), 0o600)
        return dict(manifest), snapshots

    def _load_decoded_arrangement_chunk(
        self,
        chunk_sha256: str,
        *,
        expected_manifest: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        root = self.root / "decoded-arrangement-chunks" / chunk_sha256
        manifest_path = root / "manifest.json"
        unhashed_expected = {
            key: value
            for key, value in expected_manifest.items()
            if key != "chunk_sha256"
        }
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            document.get("schema") != DECODED_ARRANGEMENT_CHUNK_SCHEMA
            or document.get("chunk_sha256") != chunk_sha256
            or root.name != chunk_sha256
            or _document_hash(unhashed_expected) != chunk_sha256
            or any(
                document.get(key) != value for key, value in expected_manifest.items()
            )
            or document.get("path_free_manifest") is not True
            or document.get("private_audio") is not True
            or document.get("effects") != _decoded_arrangement_effects()
        ):
            return None
        tracks = document.get("tracks")
        fingerprints = expected_manifest.get("input_fingerprints")
        if (
            not isinstance(tracks, list)
            or not isinstance(fingerprints, list)
            or len(tracks) != len(fingerprints)
            or not 1 <= len(tracks) <= _DECODED_ARRANGEMENT_MAXIMUM_TRACKS
        ):
            return None
        identity_keys = (
            "track_id",
            "kind",
            "stem_ids",
            "roles",
            "source_sha256",
            "stem_id",
            "candidate_id",
            "role",
            "decision",
            "source_midi_sha256",
        )
        materialized_tracks: list[dict[str, Any]] = []
        aggregate_bytes = 0
        for track, fingerprint in zip(tracks, fingerprints):
            if not isinstance(track, Mapping) or not isinstance(fingerprint, Mapping):
                return None
            audio = track.get("audio")
            if not isinstance(audio, Mapping):
                return None
            relative_path = Path(str(audio.get("path", "")))
            expected_frames = int(fingerprint.get("end_frame", 0)) - int(
                fingerprint.get("start_frame", 0)
            )
            silence_padded_frames = track.get("silence_padded_frames")
            if (
                relative_path.is_absolute()
                or len(relative_path.parts) != 1
                or any(
                    track.get(key) != fingerprint.get(key)
                    for key in identity_keys
                    if key in fingerprint
                )
                or track.get("sample_rate") != fingerprint.get("sample_rate")
                or track.get("channels") != fingerprint.get("channels")
                or track.get("start_frame") != fingerprint.get("start_frame")
                or track.get("end_frame") != fingerprint.get("end_frame")
                or track.get("frames") != expected_frames
                or isinstance(silence_padded_frames, bool)
                or not isinstance(silence_padded_frames, int)
                or not 0 <= silence_padded_frames <= expected_frames
            ):
                return None
            materialized_audio = self._materialize_file_record(audio, root)
            if materialized_audio is None:
                return None
            aggregate_bytes += int(materialized_audio["bytes"])
            materialized_track = dict(track)
            materialized_track["audio"] = materialized_audio
            materialized_tracks.append(materialized_track)
        if (
            aggregate_bytes != document.get("aggregate_output_bytes")
            or aggregate_bytes > _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES
        ):
            return None
        _restrict_private_permissions(root, 0o700)
        _restrict_private_permissions(manifest_path, 0o600)
        for track in materialized_tracks:
            _restrict_private_permissions(Path(track["audio"]["path"]), 0o600)
        result = dict(document)
        result["tracks"] = materialized_tracks
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

    def _load_pack(
        self,
        zip_path: Path,
        manifest_path: Path,
        *,
        expected_key_payload: Mapping[str, Any],
        expected_pack_manifest: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if document.get("schema") != GARAGEBAND_PACK_SCHEMA:
            return None
        expected_cache_key = _document_hash(expected_key_payload)
        if (
            document.get("cache_key") != expected_cache_key
            or zip_path.parent.name != expected_cache_key
            or any(
                document.get(key) != value
                for key, value in expected_key_payload.items()
            )
            or any(
                document.get(key) != value
                for key, value in expected_pack_manifest.items()
            )
        ):
            return None
        record = document.get("zip")
        if not isinstance(record, Mapping):
            return None
        materialized = self._materialize_file_record(record, manifest_path.parent)
        if materialized is None or materialized["path"] != str(zip_path):
            return None
        try:
            verified_pack = verify_garageband_pack_archive(zip_path)
        except ValueError:
            return None
        receipt = verified_pack.get("receipt")
        if (
            not isinstance(receipt, Mapping)
            or dict(receipt) != dict(expected_pack_manifest)
            or any(document.get(key) != value for key, value in receipt.items())
        ):
            return None
        review_record = document.get("acceptance_review")
        seed_record = document.get("acceptance_seed")
        if not isinstance(review_record, Mapping) or not isinstance(
            seed_record, Mapping
        ):
            return None
        materialized_review = self._materialize_file_record(
            review_record, manifest_path.parent
        )
        materialized_seed = self._materialize_file_record(
            seed_record, manifest_path.parent
        )
        if materialized_review is None or materialized_seed is None:
            return None
        try:
            verified_acceptance = verify_garageband_pack_acceptance_artifacts(
                zip_path,
                materialized_seed["path"],
                materialized_review["path"],
            )
        except ValueError:
            return None
        if verified_acceptance.get("pack_sha256") != materialized.get("sha256"):
            return None
        result = dict(document)
        result["zip"] = materialized
        result["acceptance_review"] = materialized_review
        result["acceptance_seed"] = materialized_seed
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


def decoded_arrangement_selection_manifest(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the canonical, path-free selected-arrangement audition manifest."""

    manifest, _source_groups, _selection = _decoded_arrangement_selection(
        catalog, current
    )
    return manifest


def selected_candidates(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Resolve only active explicit main and explicit optional choices."""

    states = current.get("stems", {})
    selected: list[dict[str, Any]] = []
    for stem in catalog.get("stems", []):
        stem_id = str(stem["stem_id"])
        state = states.get(stem_id, {})
        outcome = state.get("outcome")
        if isinstance(outcome, Mapping) and terminal_no_selection_outcome(
            outcome.get("value")
        ):
            continue
        main_id = state.get("main_candidate_id")
        decisions = state.get("candidates", {})
        role, _ = path_free_role(
            state.get("role") or stem.get("role") or "unclassified"
        )
        for candidate in stem.get("candidates", []):
            candidate_id = str(candidate["candidate_id"])
            decision = decisions.get(candidate_id, {})
            value = decision.get("decision")
            if decision.get("selection_active") is False:
                continue
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
    for selection_index, item in enumerate(selected, start=1):
        item["selection_index"] = selection_index
        item["garageband_pack_archive_member"] = _selected_midi_archive_member(
            selection_index,
            str(item["role"]),
            str(item["decision"]),
        )
    return selected


def _decoded_arrangement_selection(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    source_groups = _decoded_arrangement_source_groups(catalog, current)
    selection = selected_candidates(catalog, current)
    selected_rows: list[dict[str, Any]] = []
    decorated_selection: list[dict[str, Any]] = []
    track_ids = {str(group["track_id"]) for group in source_groups}
    for item in selection:
        midi = _decoded_record_identity(item.get("midi"), label="candidate MIDI")
        track_id = (
            "midi-"
            + _document_hash(
                {
                    "stem_id": item.get("stem_id"),
                    "candidate_id": item.get("candidate_id"),
                    "midi_sha256": midi["sha256"],
                }
            )[:24]
        )
        if track_id in track_ids:
            raise ValueError("decoded arrangement track identities are not unique")
        track_ids.add(track_id)
        selected_rows.append(
            {
                "track_id": track_id,
                "stem_id": str(item["stem_id"]),
                "candidate_id": str(item["candidate_id"]),
                "role": path_free_role(item.get("role"))[0],
                "decision": str(item["decision"]),
                "selection_index": int(item["selection_index"]),
                "garageband_pack_archive_member": str(
                    item["garageband_pack_archive_member"]
                ),
                "midi_sha256": midi["sha256"],
                "midi_bytes": midi["bytes"],
            }
        )
        decorated_selection.append({**item, "track_id": track_id})

    public_sources = [
        {
            "track_id": group["track_id"],
            "source_sha256": group["source_sha256"],
            "source_bytes": group["source_bytes"],
            "stem_ids": list(group["stem_ids"]),
            "roles": list(group["roles"]),
        }
        for group in source_groups
    ]
    source_ids = [str(source["track_id"]) for source in public_sources]
    midi_ids = [str(item["track_id"]) for item in selected_rows]
    groups = {
        "source-only": source_ids,
        "selected-midi": midi_ids,
        "hybrid": source_ids + midi_ids,
        "main-only": [
            str(item["track_id"])
            for item in selected_rows
            if item["decision"] == "main"
        ],
    }
    manifest: dict[str, Any] = {
        "schema": ARRANGEMENT_SELECTION_SCHEMA,
        "project_id": catalog.get("project_id"),
        "bpm": _project_bpm(catalog),
        "sources": public_sources,
        "selected_midi": selected_rows,
        "groups": groups,
    }
    manifest["selection_manifest_sha256"] = _document_hash(manifest)
    return manifest, source_groups, decorated_selection


def _decoded_arrangement_source_groups(
    catalog: Mapping[str, Any], current: Mapping[str, Any]
) -> list[dict[str, Any]]:
    states = current.get("stems", {})
    if not isinstance(states, Mapping):
        states = {}
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for stem in catalog.get("stems", []):
        if not isinstance(stem, Mapping):
            raise ValueError("decoded arrangement contains an invalid stem")
        stem_id = str(stem.get("stem_id", ""))
        if not stem_id:
            raise ValueError("decoded arrangement stem has no identity")
        record = stem.get("source")
        identity = _decoded_record_identity(record, label="source audio")
        digest = str(identity["sha256"])
        state = states.get(stem_id, {})
        if not isinstance(state, Mapping):
            state = {}
        role = path_free_role(state.get("role") or stem.get("role"))[0]
        if digest not in groups:
            order.append(digest)
            groups[digest] = {
                "track_id": f"source-{digest[:24]}",
                "source_sha256": digest,
                "source_bytes": identity["bytes"],
                "stem_ids": [],
                "roles": [],
                "records": [],
            }
        group = groups[digest]
        if group["source_bytes"] != identity["bytes"]:
            raise ValueError("duplicate source hash has inconsistent byte counts")
        group["stem_ids"].append(stem_id)
        if role not in group["roles"]:
            group["roles"].append(role)
        group["records"].append(record)
    if not order:
        raise ValueError("decoded arrangement requires at least one source stem")
    return [groups[digest] for digest in order]


def _decoded_record_identity(record: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError(f"{label} record is invalid")
    digest = record.get("sha256")
    byte_count = record.get("bytes")
    if not _is_sha256(digest):
        raise ValueError(f"{label} has no valid content hash")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise ValueError(f"{label} byte count is invalid")
    return {"sha256": str(digest), "bytes": byte_count}


def _decoded_arrangement_effects() -> dict[str, bool]:
    return {
        "source_audio_mutated": False,
        "midi_mutated": False,
        "selection_changed": False,
        "feedback_recorded": False,
        "event_appended": False,
        "automatic_selection": False,
        "automatic_ranking": False,
        "default_selection_changed": False,
    }


def _valid_balanced_manifest_semantics(document: Mapping[str, Any]) -> bool:
    try:
        if (
            not isinstance(document.get("project_id"), str)
            or not document["project_id"]
            or not _is_sha256(document.get("selection_manifest_sha256"))
            or not _is_sha256(document.get("soundfont_sha256"))
            or document.get("policy") != BALANCED_MIX_POLICY
            or document.get("render_horizon_policy") != _BALANCED_RENDER_HORIZON_POLICY
            or document.get("mastered") is not False
            or document.get("path_free_manifest") is not True
            or document.get("private_audio") is not True
            or document.get("effects") != _decoded_arrangement_effects()
        ):
            return False
        bpm = document.get("bpm")
        if (
            isinstance(bpm, bool)
            or not isinstance(bpm, (int, float))
            or not math.isfinite(float(bpm))
            or float(bpm) <= 0
        ):
            return False
        renderer = document.get("renderer")
        if not isinstance(renderer, Mapping) or set(renderer) != {
            "policy",
            "backend",
            "soundfont_sha256",
            "soundfont_bytes",
        }:
            return False
        if (
            renderer.get("policy") != _RENDER_POLICY
            or renderer.get("backend") != _BALANCED_RENDERER_BACKEND
            or renderer.get("soundfont_sha256") != document["soundfont_sha256"]
            or not _valid_nonnegative_int(renderer.get("soundfont_bytes"))
        ):
            return False

        selection = document.get("selection")
        inputs = document.get("input_fingerprints")
        if (
            not isinstance(selection, list)
            or not 1 <= len(selection) <= _DECODED_ARRANGEMENT_MAXIMUM_TRACKS
            or not isinstance(inputs, Mapping)
            or set(inputs) != {"project_sources", "selected_lanes", "soundfont"}
        ):
            return False
        soundfont = inputs.get("soundfont")
        if (
            not isinstance(soundfont, Mapping)
            or set(soundfont) != {"sha256", "bytes"}
            or soundfont.get("sha256") != renderer["soundfont_sha256"]
            or soundfont.get("bytes") != renderer["soundfont_bytes"]
        ):
            return False
        project_sources = inputs.get("project_sources")
        selected_lanes = inputs.get("selected_lanes")
        if (
            not isinstance(project_sources, list)
            or not project_sources
            or not isinstance(selected_lanes, list)
            or len(selected_lanes) != len(selection)
        ):
            return False
        if not _valid_balanced_selection_and_inputs(
            selection,
            project_sources,
            selected_lanes,
        ):
            return False
        render_horizon = document.get("render_horizon")
        if not _valid_balanced_render_horizon(
            render_horizon,
            project_sources,
            selected_lanes,
        ):
            return False
        mix_report = document.get("mix_report")
        if not _valid_balanced_mix_report(
            mix_report,
            selected_lanes,
            render_horizon,
        ):
            return False
        return document.get("mastering_boundary") == mix_report.get(
            "mastering_boundary"
        )
    except (KeyError, TypeError, ValueError):
        return False


def _balanced_key_payload(
    *,
    catalog: Mapping[str, Any],
    selection_manifest_sha256: str,
    source_groups: Sequence[Mapping[str, Any]],
    selection: Sequence[Mapping[str, Any]],
    previews: Sequence[Mapping[str, Any]],
    soundfont: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a balance cache to the exact current source, MIDI and render inputs."""

    if len(selection) != len(previews):
        raise ValueError("balanced arrangement preview count is inconsistent")
    project_source_fingerprints: list[dict[str, Any]] = []
    source_by_stem_id: dict[str, Mapping[str, Any]] = {}
    for group in source_groups:
        records = group.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("balanced arrangement source group is invalid")
        record = records[0]
        if not isinstance(record, Mapping):
            raise ValueError("balanced arrangement source record is invalid")
        source_digest = record.get("sha256")
        source_bytes = record.get("bytes")
        if not _is_sha256(source_digest) or not _valid_nonnegative_int(source_bytes):
            raise ValueError("balanced arrangement source identity is invalid")
        stem_ids = [str(value) for value in group["stem_ids"]]
        project_source_fingerprints.append(
            {
                "track_id": str(group["track_id"]),
                "source_sha256": str(source_digest),
                "source_bytes": int(source_bytes),
                "stem_ids": stem_ids,
                "roles": [str(value) for value in group["roles"]],
            }
        )
        for stem_id in stem_ids:
            source_by_stem_id[stem_id] = record

    selected_lane_fingerprints: list[dict[str, Any]] = []
    for item, preview in zip(selection, previews):
        source = source_by_stem_id.get(str(item["stem_id"]))
        preview_record = preview.get("preview")
        if not isinstance(source, Mapping) or not isinstance(preview_record, Mapping):
            raise ValueError("selected MIDI has no matching balance evidence")
        selected_lane_fingerprints.append(
            {
                "track_id": str(item["track_id"]),
                "stem_id": str(item["stem_id"]),
                "candidate_id": str(item["candidate_id"]),
                "role": str(item["role"]),
                "decision": str(item["decision"]),
                "selection_index": int(item["selection_index"]),
                "garageband_pack_archive_member": str(
                    item["garageband_pack_archive_member"]
                ),
                "source_sha256": str(source["sha256"]),
                "source_bytes": int(source["bytes"]),
                "source_midi_sha256": str(item["midi"]["sha256"]),
                "source_midi_bytes": int(item["midi"]["bytes"]),
                "neutral_preview_sha256": str(preview_record["sha256"]),
                "neutral_preview_bytes": int(preview_record["bytes"]),
                "neutral_preview_cache_key": str(preview["cache_key"]),
            }
        )
    renderer_identity = {
        "policy": _RENDER_POLICY,
        "backend": _BALANCED_RENDERER_BACKEND,
        "soundfont_sha256": str(soundfont["sha256"]),
        "soundfont_bytes": int(soundfont["bytes"]),
    }
    input_fingerprints = {
        "project_sources": project_source_fingerprints,
        "selected_lanes": selected_lane_fingerprints,
        "soundfont": {
            "sha256": str(soundfont["sha256"]),
            "bytes": int(soundfont["bytes"]),
        },
    }
    return {
        "schema": BALANCED_ARRANGEMENT_SCHEMA,
        "project_id": catalog.get("project_id"),
        "selection_manifest_sha256": selection_manifest_sha256,
        "bpm": _project_bpm(catalog),
        "policy": BALANCED_MIX_POLICY,
        "render_horizon_policy": _BALANCED_RENDER_HORIZON_POLICY,
        "soundfont_sha256": str(soundfont["sha256"]),
        "selection": _public_selection(selection),
        "renderer": renderer_identity,
        "input_fingerprints": input_fingerprints,
    }


def _balanced_verification_binding(
    *,
    selection_manifest: Mapping[str, Any],
    source_groups: Sequence[Mapping[str, Any]],
    selection: Sequence[Mapping[str, Any]],
    soundfont: Mapping[str, Any],
) -> str:
    """Bind cached stat signatures to the current catalogued input identities."""

    def record_identity(record: Mapping[str, Any], *, label: str) -> dict[str, Any]:
        path = record.get("path")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        if (
            not isinstance(path, str)
            or not path
            or not _is_sha256(digest)
            or not _valid_nonnegative_int(byte_count)
        ):
            raise ValueError(f"{label} identity is invalid")
        return {
            "path": str(Path(path).resolve()),
            "sha256": str(digest),
            "bytes": int(byte_count),
        }

    sources = []
    for group in source_groups:
        sources.append(
            {
                "track_id": str(group["track_id"]),
                "source_sha256": str(group["source_sha256"]),
                "source_bytes": int(group["source_bytes"]),
                "stem_ids": [str(value) for value in group["stem_ids"]],
                "roles": [str(value) for value in group["roles"]],
                "records": [
                    record_identity(record, label="source audio")
                    for record in group["records"]
                ],
            }
        )
    selected = []
    for item in selection:
        selected.append(
            {
                **_public_selection([item])[0],
                "track_id": str(item["track_id"]),
                "midi": record_identity(
                    item["midi"],
                    label="selected candidate MIDI",
                ),
            }
        )
    return _document_hash(
        {
            "selection_manifest": dict(selection_manifest),
            "sources": sources,
            "selection": selected,
            "soundfont": record_identity(soundfont, label="SoundFont"),
        }
    )


def _valid_balanced_selection_and_inputs(
    selection: Sequence[Any],
    project_sources: Sequence[Any],
    selected_lanes: Sequence[Any],
) -> bool:
    selection_keys = {
        "stem_id",
        "candidate_id",
        "role",
        "decision",
        "selection_index",
        "garageband_pack_archive_member",
        "process",
        "midi_sha256",
        "midi_bytes",
        "candidate_origin_source_audio_sha256",
        "candidate_origin_source_audio_sha256_basis",
    }
    source_keys = {
        "track_id",
        "source_sha256",
        "source_bytes",
        "stem_ids",
        "roles",
    }
    lane_keys = {
        "track_id",
        "stem_id",
        "candidate_id",
        "role",
        "decision",
        "selection_index",
        "garageband_pack_archive_member",
        "source_sha256",
        "source_bytes",
        "source_midi_sha256",
        "source_midi_bytes",
        "neutral_preview_sha256",
        "neutral_preview_bytes",
        "neutral_preview_cache_key",
    }
    source_by_sha256: dict[str, Mapping[str, Any]] = {}
    source_track_ids: set[str] = set()
    for source in project_sources:
        if not isinstance(source, Mapping) or set(source) != source_keys:
            return False
        digest = source.get("source_sha256")
        track_id = source.get("track_id")
        stem_ids = source.get("stem_ids")
        roles = source.get("roles")
        if (
            not _is_sha256(digest)
            or not isinstance(track_id, str)
            or track_id != f"source-{str(digest)[:24]}"
            or track_id in source_track_ids
            or digest in source_by_sha256
            or not _valid_nonnegative_int(source.get("source_bytes"))
            or not isinstance(stem_ids, list)
            or not stem_ids
            or len(set(stem_ids)) != len(stem_ids)
            or not all(isinstance(value, str) and value for value in stem_ids)
            or not isinstance(roles, list)
            or not roles
            or len(set(roles)) != len(roles)
            or not all(isinstance(value, str) and value for value in roles)
        ):
            return False
        source_track_ids.add(track_id)
        source_by_sha256[str(digest)] = source

    lane_track_ids: set[str] = set()
    archive_members: set[str] = set()
    for expected_index, (selected, lane) in enumerate(
        zip(selection, selected_lanes),
        start=1,
    ):
        if (
            not isinstance(selected, Mapping)
            or set(selected) != selection_keys
            or not isinstance(lane, Mapping)
            or set(lane) != lane_keys
        ):
            return False
        role = selected.get("role")
        decision = selected.get("decision")
        archive_member = selected.get("garageband_pack_archive_member")
        if (
            selected.get("selection_index") != expected_index
            or not isinstance(role, str)
            or not role
            or not isinstance(decision, str)
            or decision not in {"main", "optional"}
            or archive_member
            != _selected_midi_archive_member(expected_index, role, decision)
            or archive_member in archive_members
            or not _is_sha256(selected.get("midi_sha256"))
            or not _valid_nonnegative_int(selected.get("midi_bytes"))
            or not isinstance(selected.get("stem_id"), str)
            or not selected["stem_id"]
            or not isinstance(selected.get("candidate_id"), str)
            or not selected["candidate_id"]
            or (
                selected.get("process") is not None
                and not isinstance(selected.get("process"), str)
            )
            or not _is_sha256(selected.get("candidate_origin_source_audio_sha256"))
            or selected.get("candidate_origin_source_audio_sha256_basis")
            not in {"verified-ai-source", "review-stem-source-fallback"}
        ):
            return False
        archive_members.add(str(archive_member))
        lane_track_id = lane.get("track_id")
        expected_lane_track_id = (
            "midi-"
            + _document_hash(
                {
                    "stem_id": selected["stem_id"],
                    "candidate_id": selected["candidate_id"],
                    "midi_sha256": selected["midi_sha256"],
                }
            )[:24]
        )
        if (
            not isinstance(lane_track_id, str)
            or lane_track_id != expected_lane_track_id
            or lane_track_id in lane_track_ids
            or lane.get("stem_id") != selected["stem_id"]
            or lane.get("candidate_id") != selected["candidate_id"]
            or lane.get("role") != role
            or lane.get("decision") != decision
            or lane.get("selection_index") != expected_index
            or lane.get("garageband_pack_archive_member") != archive_member
            or lane.get("source_midi_sha256") != selected["midi_sha256"]
            or lane.get("source_midi_bytes") != selected["midi_bytes"]
            or not _is_sha256(lane.get("source_sha256"))
            or not _valid_nonnegative_int(lane.get("source_bytes"))
            or not _is_sha256(lane.get("neutral_preview_sha256"))
            or not _valid_nonnegative_int(lane.get("neutral_preview_bytes"))
            or not _is_sha256(lane.get("neutral_preview_cache_key"))
        ):
            return False
        lane_track_ids.add(lane_track_id)
        source = source_by_sha256.get(str(lane["source_sha256"]))
        if (
            source is None
            or lane["source_bytes"] != source["source_bytes"]
            or lane["stem_id"] not in source["stem_ids"]
        ):
            return False
    return True


def _valid_balanced_render_horizon(
    horizon: Any,
    project_sources: Sequence[Mapping[str, Any]],
    selected_lanes: Sequence[Mapping[str, Any]],
) -> bool:
    if not isinstance(horizon, Mapping) or set(horizon) != {
        "policy",
        "sample_rate",
        "output_frames",
        "maximum_source_frames",
        "maximum_neutral_preview_frames",
        "excluded_neutral_preview_tail_frames",
        "padded_output_frames",
        "sources",
        "lanes",
    }:
        return False
    if horizon.get("policy") != _BALANCED_RENDER_HORIZON_POLICY:
        return False
    sample_rate = horizon.get("sample_rate")
    output_frames = horizon.get("output_frames")
    if (
        not _valid_positive_int(sample_rate)
        or not 8_000 <= int(sample_rate) <= 96_000
        or not _valid_positive_int(output_frames)
        or int(output_frames) > int(sample_rate) * _DECODED_STREAM_MAXIMUM_SECONDS
    ):
        return False
    sources = horizon.get("sources")
    lanes = horizon.get("lanes")
    if (
        not isinstance(sources, list)
        or len(sources) != len(project_sources)
        or not isinstance(lanes, list)
        or len(lanes) != len(selected_lanes)
    ):
        return False
    source_geometry_keys = {
        "track_id",
        "source_sha256",
        "source_bytes",
        "stem_ids",
        "roles",
        "source_sample_rate",
        "source_channels",
        "source_frames",
        "output_rate_frames",
        "owns_output_horizon",
    }
    scaled_frames: list[int] = []
    for fingerprint, row in zip(project_sources, sources):
        if not isinstance(row, Mapping) or set(row) != source_geometry_keys:
            return False
        if any(
            row.get(key) != fingerprint.get(key)
            for key in (
                "track_id",
                "source_sha256",
                "source_bytes",
                "stem_ids",
                "roles",
            )
        ):
            return False
        if (
            not _valid_positive_int(row.get("source_sample_rate"))
            or not 8_000 <= int(row["source_sample_rate"]) <= 96_000
            or row.get("source_channels") not in {1, 2}
            or not _valid_positive_int(row.get("source_frames"))
            or not _valid_positive_int(row.get("output_rate_frames"))
            or not isinstance(row.get("owns_output_horizon"), bool)
        ):
            return False
        expected_scaled_frames = _ceil_scaled_frame(
            int(row["source_frames"]),
            int(sample_rate),
            int(row["source_sample_rate"]),
        )
        if row["output_rate_frames"] != expected_scaled_frames:
            return False
        scaled_frames.append(expected_scaled_frames)
    if not scaled_frames or max(scaled_frames) != int(output_frames):
        return False
    if horizon.get("maximum_source_frames") != max(scaled_frames) or any(
        bool(row["owns_output_horizon"])
        != (int(row["output_rate_frames"]) == int(output_frames))
        for row in sources
    ):
        return False

    lane_geometry_keys = {
        "track_id",
        "stem_id",
        "candidate_id",
        "selection_index",
        "garageband_pack_archive_member",
        "neutral_preview_sha256",
        "neutral_preview_frames",
        "excluded_neutral_preview_tail_frames",
        "padded_output_frames",
    }
    preview_frames: list[int] = []
    for fingerprint, row in zip(selected_lanes, lanes):
        if not isinstance(row, Mapping) or set(row) != lane_geometry_keys:
            return False
        if any(
            row.get(row_key) != fingerprint.get(fingerprint_key)
            for row_key, fingerprint_key in (
                ("track_id", "track_id"),
                ("stem_id", "stem_id"),
                ("candidate_id", "candidate_id"),
                ("selection_index", "selection_index"),
                (
                    "garageband_pack_archive_member",
                    "garageband_pack_archive_member",
                ),
                ("neutral_preview_sha256", "neutral_preview_sha256"),
            )
        ):
            return False
        frames = row.get("neutral_preview_frames")
        if (
            not _valid_positive_int(frames)
            or row.get("excluded_neutral_preview_tail_frames")
            != max(0, int(frames) - int(output_frames))
            or row.get("padded_output_frames")
            != max(0, int(output_frames) - int(frames))
        ):
            return False
        preview_frames.append(int(frames))
    maximum_preview_frames = max(preview_frames)
    return (
        horizon.get("maximum_neutral_preview_frames") == maximum_preview_frames
        and horizon.get("excluded_neutral_preview_tail_frames")
        == max(0, maximum_preview_frames - int(output_frames))
        and horizon.get("padded_output_frames")
        == max(0, int(output_frames) - maximum_preview_frames)
    )


def _valid_balanced_mix_report(
    report: Any,
    selected_lanes: Sequence[Mapping[str, Any]],
    render_horizon: Mapping[str, Any],
) -> bool:
    report_keys = {
        "schema",
        "policy",
        "label",
        "path_free_report",
        "mastered",
        "mastering_boundary",
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
        "measurement",
        "source_groups",
        "limits",
        "lanes",
        "drum_bus",
        "output",
        "processing",
        "effects",
    }
    if (
        not isinstance(report, Mapping)
        or set(report) != report_keys
        or report.get("schema") != BALANCED_MIX_REPORT_SCHEMA
        or report.get("policy") != BALANCED_MIX_POLICY
        or report.get("label") != _BALANCED_MIX_LABEL
        or report.get("mastered") is not False
        or report.get("path_free_report") is not True
        or report.get("mastering_boundary") != _BALANCED_MASTERING_BOUNDARY
        or report.get("effects") != _decoded_arrangement_effects()
        or report.get("sample_rate") != render_horizon.get("sample_rate")
        or report.get("frames") != render_horizon.get("output_frames")
        or report.get("channels") not in {1, 2}
        or not _finite_number(report.get("duration_seconds"))
        or not math.isclose(
            float(report["duration_seconds"]),
            int(report["frames"]) / int(report["sample_rate"]),
            abs_tol=1e-5,
        )
    ):
        return False
    measurement = report.get("measurement")
    limits = report.get("limits")
    expected_measurement = BALANCED_MIX_CONTRACT.measurement_document()
    expected_limits = BALANCED_MIX_CONTRACT.limits_document()
    if (
        not isinstance(measurement, Mapping)
        or dict(measurement) != expected_measurement
        or not isinstance(limits, Mapping)
        or dict(limits) != expected_limits
    ):
        return False
    if not _valid_balanced_drum_overlap(
        report.get("drum_bus"),
        sample_rate=int(report["sample_rate"]),
        channels=int(report["channels"]),
        frames=int(report["frames"]),
    ):
        return False
    if not _valid_balanced_lanes_and_source_groups(
        report,
        selected_lanes,
        render_horizon,
    ):
        return False
    output = report.get("output")
    if not _valid_balanced_output(
        output,
        sample_rate=int(report["sample_rate"]),
        channels=int(report["channels"]),
        frames=int(report["frames"]),
    ):
        return False
    processing = report.get("processing")
    processing_keys = {
        "per_lane_gain",
        "summed_source_group_calibration",
        "drum_bus_gain",
        "global_output_gain",
        "sample_peak_protection",
        "compression",
        "limiter",
        "equalisation",
        "saturation",
        "reverb",
        "chorus",
        "stereo_widening",
    }
    required_disabled_processing = {
        "compression",
        "limiter",
        "equalisation",
        "saturation",
        "reverb",
        "chorus",
        "stereo_widening",
    }
    if (
        not isinstance(processing, Mapping)
        or set(processing) != processing_keys
        or processing.get("per_lane_gain") is not True
        or processing.get("summed_source_group_calibration") is not True
        or processing.get("sample_peak_protection") is not True
        or any(processing.get(key) is not False for key in required_disabled_processing)
        or processing.get("drum_bus_gain")
        is not (
            not math.isclose(
                float(report["drum_bus"]["guard_gain_db"]),
                0.0,
                abs_tol=1e-9,
            )
        )
        or processing.get("global_output_gain")
        is not (
            not math.isclose(
                float(output["master_output_gain_db"]),
                0.0,
                abs_tol=1e-9,
            )
        )
    ):
        return False
    return True


def _valid_balanced_lanes_and_source_groups(
    report: Mapping[str, Any],
    selected_lanes: Sequence[Mapping[str, Any]],
    render_horizon: Mapping[str, Any],
) -> bool:
    lanes = report.get("lanes")
    source_groups = report.get("source_groups")
    if (
        not isinstance(lanes, list)
        or len(lanes) != len(selected_lanes)
        or not isinstance(source_groups, list)
    ):
        return False
    lane_keys = {
        "track_id",
        "stem_id",
        "candidate_id",
        "role",
        "decision",
        "selection_index",
        "garageband_pack_archive_member",
        "source_sha256",
        "source_bytes",
        "source_midi_sha256",
        "preview_sha256",
        "preview_bytes",
        "neutral_preview_cache_key",
        "source_metrics",
        "preview_metrics",
        "source_duplicate_count",
        "provisional_source_match_gain_db",
        "source_group_calibration_gain_db",
        "raw_source_match_gain_db",
        "source_match_gain_db",
        "source_match_clamped",
        "fallback_reason",
        "drum_bus_gain_db",
        "garageband_track_trim_db",
    }
    horizon_lanes = {
        (
            int(row["selection_index"]),
            str(row["garageband_pack_archive_member"]),
        ): row
        for row in render_horizon["lanes"]
    }
    horizon_sources = {
        str(row["source_sha256"]): row for row in render_horizon["sources"]
    }
    lanes_by_source: dict[str, list[Mapping[str, Any]]] = {}
    guard_gain = float(report["drum_bus"]["guard_gain_db"])
    for fingerprint, lane in zip(selected_lanes, lanes):
        if not isinstance(lane, Mapping) or set(lane) != lane_keys:
            return False
        if any(
            lane.get(key) != fingerprint.get(fingerprint_key)
            for key, fingerprint_key in (
                ("track_id", "track_id"),
                ("stem_id", "stem_id"),
                ("candidate_id", "candidate_id"),
                ("role", "role"),
                ("decision", "decision"),
                ("selection_index", "selection_index"),
                (
                    "garageband_pack_archive_member",
                    "garageband_pack_archive_member",
                ),
                ("source_sha256", "source_sha256"),
                ("source_bytes", "source_bytes"),
                ("source_midi_sha256", "source_midi_sha256"),
                ("preview_sha256", "neutral_preview_sha256"),
                ("preview_bytes", "neutral_preview_bytes"),
                ("neutral_preview_cache_key", "neutral_preview_cache_key"),
            )
        ):
            return False
        horizon_lane = horizon_lanes.get(
            (
                int(lane["selection_index"]),
                str(lane["garageband_pack_archive_member"]),
            )
        )
        horizon_source = horizon_sources.get(str(lane["source_sha256"]))
        if horizon_lane is None or horizon_source is None:
            return False
        source_frames = min(
            int(horizon_source["source_frames"]),
            _ceil_scaled_frame(
                int(render_horizon["output_frames"]),
                int(horizon_source["source_sample_rate"]),
                int(render_horizon["sample_rate"]),
            ),
        )
        preview_frames = min(
            int(horizon_lane["neutral_preview_frames"]),
            int(render_horizon["output_frames"]),
        )
        source_metrics = lane.get("source_metrics")
        preview_metrics = lane.get("preview_metrics")
        if not _valid_balanced_metrics(
            source_metrics,
            sample_rate=int(horizon_source["source_sample_rate"]),
            channels=int(horizon_source["source_channels"]),
            frames=source_frames,
            require_active=False,
        ) or not _valid_balanced_metrics(
            preview_metrics,
            sample_rate=int(report["sample_rate"]),
            channels=int(report["channels"]),
            frames=preview_frames,
            require_active=True,
        ):
            return False
        if int(preview_metrics["full_scale_sample_count"]) != 0:
            return False
        numeric_fields = (
            "provisional_source_match_gain_db",
            "source_group_calibration_gain_db",
            "raw_source_match_gain_db",
            "source_match_gain_db",
            "drum_bus_gain_db",
            "garageband_track_trim_db",
        )
        if (
            not all(_finite_number(lane.get(key)) for key in numeric_fields)
            or not _valid_positive_int(lane.get("source_duplicate_count"))
            or not isinstance(lane.get("source_match_clamped"), bool)
        ):
            return False
        source_level = source_metrics["gated_rms_dbfs"]
        expected_fallback = None
        if source_level is None:
            expected_provisional = -6.0 if is_drum_role(lane["role"]) else 0.0
            expected_fallback = (
                "source stem had no measurable active blocks; conservative role "
                "fallback used"
            )
        else:
            expected_provisional = float(source_level) - float(
                preview_metrics["gated_rms_dbfs"]
            )
        expected_drum_gain = guard_gain if is_drum_role(lane["role"]) else 0.0
        if (
            not math.isclose(
                float(lane["provisional_source_match_gain_db"]),
                expected_provisional,
                abs_tol=2e-5,
            )
            or lane.get("fallback_reason") != expected_fallback
            or not math.isclose(
                float(lane["drum_bus_gain_db"]),
                expected_drum_gain,
                abs_tol=2e-5,
            )
            or not math.isclose(
                float(lane["garageband_track_trim_db"]),
                float(lane["source_match_gain_db"]) + expected_drum_gain,
                abs_tol=2e-5,
            )
        ):
            return False
        lanes_by_source.setdefault(str(lane["source_sha256"]), []).append(lane)

    expected_source_order = sorted(lanes_by_source)
    if len(source_groups) != len(expected_source_order):
        return False
    source_group_keys = {
        "source_sha256",
        "selected_lane_count",
        "target_gated_rms_dbfs",
        "target_reason",
        "before_calibration",
        "calibration_gain_db",
        "after_calibration",
        "residual_level_error_db",
        "clamped_lane_count",
    }
    for expected_source_sha256, source_group in zip(
        expected_source_order,
        source_groups,
    ):
        if (
            not isinstance(source_group, Mapping)
            or set(source_group) != source_group_keys
            or source_group.get("source_sha256") != expected_source_sha256
        ):
            return False
        group_lanes = lanes_by_source[expected_source_sha256]
        if (
            source_group.get("selected_lane_count") != len(group_lanes)
            or not _finite_number(source_group.get("target_gated_rms_dbfs"))
            or not _finite_number(source_group.get("calibration_gain_db"))
            or not _valid_nonnegative_int(source_group.get("clamped_lane_count"))
        ):
            return False
        before = source_group.get("before_calibration")
        after = source_group.get("after_calibration")
        if not _valid_balanced_metrics(
            before,
            sample_rate=int(report["sample_rate"]),
            channels=int(report["channels"]),
            frames=int(report["frames"]),
            require_active=True,
        ) or not _valid_balanced_metrics(
            after,
            sample_rate=int(report["sample_rate"]),
            channels=int(report["channels"]),
            frames=int(report["frames"]),
            require_active=False,
        ):
            return False
        first_source_metrics = group_lanes[0]["source_metrics"]
        if any(lane["source_metrics"] != first_source_metrics for lane in group_lanes):
            return False
        source_level = first_source_metrics["gated_rms_dbfs"]
        if source_level is None:
            target_level = max(
                float(lane["preview_metrics"]["gated_rms_dbfs"])
                + float(lane["provisional_source_match_gain_db"])
                for lane in group_lanes
            )
            target_reason = (
                "loudest conservatively adjusted selected preview because the "
                "source stem had no measurable active blocks"
            )
        else:
            target_level = float(source_level)
            target_reason = "measured source-stem gated RMS"
        calibration_gain = target_level - float(before["gated_rms_dbfs"])
        after_level = after["gated_rms_dbfs"]
        expected_residual = (
            None if after_level is None else float(after_level) - target_level
        )
        residual = source_group.get("residual_level_error_db")
        if (
            not math.isclose(
                float(source_group["target_gated_rms_dbfs"]),
                target_level,
                abs_tol=2e-5,
            )
            or source_group.get("target_reason") != target_reason
            or not math.isclose(
                float(source_group["calibration_gain_db"]),
                calibration_gain,
                abs_tol=2e-5,
            )
            or (expected_residual is None and residual is not None)
            or (
                expected_residual is not None
                and (
                    not _finite_number(residual)
                    or not math.isclose(
                        float(residual),
                        expected_residual,
                        abs_tol=2e-5,
                    )
                )
            )
        ):
            return False
        clamped_count = 0
        for lane in group_lanes:
            raw_gain = (
                float(lane["provisional_source_match_gain_db"]) + calibration_gain
            )
            matched_gain = max(
                _BALANCED_SOURCE_MATCH_GAIN_DB[0],
                min(_BALANCED_SOURCE_MATCH_GAIN_DB[1], raw_gain),
            )
            rounded_at_boundary = math.isclose(
                raw_gain,
                matched_gain,
                abs_tol=1e-6,
            )
            expected_clamped = not rounded_at_boundary
            if (
                not math.isclose(
                    float(lane["source_group_calibration_gain_db"]),
                    calibration_gain,
                    abs_tol=2e-5,
                )
                or not math.isclose(
                    float(lane["raw_source_match_gain_db"]),
                    raw_gain,
                    abs_tol=2e-5,
                )
                or not math.isclose(
                    float(lane["source_match_gain_db"]),
                    matched_gain,
                    abs_tol=2e-5,
                )
                or (
                    lane["source_match_clamped"] is not expected_clamped
                    and not (
                        rounded_at_boundary
                        and lane["source_match_clamped"] is True
                        and math.isclose(
                            matched_gain,
                            _BALANCED_SOURCE_MATCH_GAIN_DB[0],
                            abs_tol=1e-6,
                        )
                        or rounded_at_boundary
                        and lane["source_match_clamped"] is True
                        and math.isclose(
                            matched_gain,
                            _BALANCED_SOURCE_MATCH_GAIN_DB[1],
                            abs_tol=1e-6,
                        )
                    )
                )
                or lane["source_duplicate_count"] != len(group_lanes)
            ):
                return False
            clamped_count += int(bool(lane["source_match_clamped"]))
        if source_group["clamped_lane_count"] != clamped_count:
            return False
    return True


def _valid_balanced_metrics(
    metrics: Any,
    *,
    sample_rate: int,
    channels: int,
    frames: int,
    require_active: bool,
) -> bool:
    metric_keys = {
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
        "block_count",
        "active_block_count",
        "gated_rms_dbfs",
        "active_block_p95_dbfs",
        "sample_peak_dbfs",
        "full_scale_sample_count",
    }
    if (
        not isinstance(metrics, Mapping)
        or set(metrics) != metric_keys
        or metrics.get("sample_rate") != sample_rate
        or metrics.get("channels") != channels
        or metrics.get("frames") != frames
        or not _finite_number(metrics.get("duration_seconds"))
        or not math.isclose(
            float(metrics["duration_seconds"]),
            frames / sample_rate,
            abs_tol=1e-5,
        )
        or not _valid_positive_int(metrics.get("block_count"))
        or not _valid_nonnegative_int(metrics.get("active_block_count"))
        or int(metrics["active_block_count"]) > int(metrics["block_count"])
        or not _valid_nonnegative_int(metrics.get("full_scale_sample_count"))
        or int(metrics["full_scale_sample_count"]) > frames * channels
    ):
        return False
    block_frames = max(
        1,
        int(round(sample_rate * _BALANCED_WINDOW_SECONDS)),
    )
    if int(metrics["block_count"]) != (frames + block_frames - 1) // block_frames:
        return False
    active_count = int(metrics["active_block_count"])
    gated = metrics.get("gated_rms_dbfs")
    p95 = metrics.get("active_block_p95_dbfs")
    peak = metrics.get("sample_peak_dbfs")
    if active_count:
        return _finite_number(gated) and _finite_number(p95) and _finite_number(peak)
    return (
        not require_active
        and gated is None
        and p95 is None
        and (peak is None or _finite_number(peak))
    )


def _valid_balanced_output(
    output: Any,
    *,
    sample_rate: int,
    channels: int,
    frames: int,
) -> bool:
    output_keys = {
        "pre_master",
        "raw_normalisation_gain_db",
        "requested_normalisation_gain_db",
        "available_sample_peak_room_db",
        "master_output_gain_db",
        "post_master",
        "post_master_target_error_db",
        "normalisation_target_met",
        "normalisation_limit",
    }
    if not isinstance(output, Mapping) or set(output) != output_keys:
        return False
    pre_master = output.get("pre_master")
    post_master = output.get("post_master")
    if not _valid_balanced_output_metrics(
        pre_master,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
    ) or not _valid_balanced_output_metrics(
        post_master,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
    ):
        return False
    raw_gain = output.get("raw_normalisation_gain_db")
    requested_gain = output.get("requested_normalisation_gain_db")
    peak_room = output.get("available_sample_peak_room_db")
    master_gain = output.get("master_output_gain_db")
    target_error = output.get("post_master_target_error_db")
    if not all(
        _finite_number(value)
        for value in (
            raw_gain,
            requested_gain,
            peak_room,
            master_gain,
            target_error,
        )
    ):
        return False
    expected_raw_gain = _BALANCED_AUDITION_TARGET_GATED_RMS_DBFS - float(
        pre_master["gated_rms_dbfs"]
    )
    expected_requested_gain = min(
        expected_raw_gain,
        _BALANCED_MAXIMUM_NORMALISATION_BOOST_DB,
    )
    expected_peak_room = _BALANCED_SAMPLE_PEAK_CEILING_DBFS - float(
        pre_master["sample_peak_dbfs"]
    )
    expected_master_gain = min(expected_requested_gain, expected_peak_room)
    expected_target_error = (
        float(post_master["gated_rms_dbfs"]) - _BALANCED_AUDITION_TARGET_GATED_RMS_DBFS
    )
    expected_target_met = (
        abs(expected_target_error) <= _BALANCED_NORMALISATION_TARGET_TOLERANCE_DB
    )
    expected_limit = None
    if expected_requested_gain < expected_raw_gain:
        expected_limit = "maximum_positive_boost"
    if expected_master_gain < expected_requested_gain:
        expected_limit = "sample_peak_ceiling"
    if (
        not math.isclose(float(raw_gain), expected_raw_gain, abs_tol=2e-5)
        or not math.isclose(
            float(requested_gain),
            expected_requested_gain,
            abs_tol=2e-5,
        )
        or not math.isclose(float(peak_room), expected_peak_room, abs_tol=2e-5)
        or not math.isclose(
            float(master_gain),
            expected_master_gain,
            abs_tol=2e-5,
        )
        or not math.isclose(
            float(target_error),
            expected_target_error,
            abs_tol=2e-5,
        )
        or output.get("normalisation_target_met") is not expected_target_met
        or output.get("normalisation_limit") != expected_limit
        or int(post_master["full_scale_sample_count"]) != 0
        or float(post_master["sample_peak_dbfs"])
        > _BALANCED_SAMPLE_PEAK_CEILING_DBFS + 0.001
    ):
        return False
    # A uniform gain shifts the sample peak directly. It does not necessarily
    # shift the gated RMS or active-block p95 by the same amount: crossing the
    # absolute −70 dBFS gate can legitimately change which blocks are active.
    return math.isclose(
        float(post_master["sample_peak_dbfs"]),
        float(pre_master["sample_peak_dbfs"]) + float(master_gain),
        abs_tol=0.01,
    )


def _valid_balanced_output_metrics(
    metrics: Any,
    *,
    sample_rate: int,
    channels: int,
    frames: int,
) -> bool:
    metric_keys = {
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
        "block_count",
        "active_block_count",
        "gated_rms_dbfs",
        "active_block_p95_dbfs",
        "sample_peak_dbfs",
        "full_scale_sample_count",
    }
    if (
        not isinstance(metrics, Mapping)
        or set(metrics) != metric_keys
        or metrics.get("sample_rate") != sample_rate
        or metrics.get("channels") != channels
        or metrics.get("frames") != frames
        or not _finite_number(metrics.get("duration_seconds"))
        or not math.isclose(
            float(metrics["duration_seconds"]),
            frames / sample_rate,
            abs_tol=1e-5,
        )
        or not _valid_positive_int(metrics.get("block_count"))
        or not _valid_positive_int(metrics.get("active_block_count"))
        or int(metrics["active_block_count"]) > int(metrics["block_count"])
        or not _valid_nonnegative_int(metrics.get("full_scale_sample_count"))
        or int(metrics["full_scale_sample_count"]) > frames * channels
        or not all(
            _finite_number(metrics.get(key))
            for key in (
                "gated_rms_dbfs",
                "active_block_p95_dbfs",
                "sample_peak_dbfs",
            )
        )
    ):
        return False
    block_frames = max(
        1,
        int(round(sample_rate * _BALANCED_WINDOW_SECONDS)),
    )
    return int(metrics["block_count"]) == (frames + block_frames - 1) // block_frames


def _valid_balanced_drum_overlap(
    drum_bus: Any,
    *,
    sample_rate: int,
    channels: int,
    frames: int,
) -> bool:
    if (
        not isinstance(drum_bus, Mapping)
        or set(drum_bus)
        != {
            "before_guard",
            "non_drum_reference",
            "before_guard_overlap",
            "required_guard_gain_db",
            "guard_gain_db",
            "guard_clamped",
            "after_guard",
            "after_guard_non_drum_reference",
            "after_guard_overlap",
            "target_applicable",
            "overlap_median_target_met",
            "overlap_p95_target_met",
            "target_met",
            "policy",
        }
        or drum_bus.get("policy") != _BALANCED_DRUM_GUARD_POLICY
    ):
        return False
    before_drum = drum_bus.get("before_guard")
    before_non_drum = drum_bus.get("non_drum_reference")
    after_drum = drum_bus.get("after_guard")
    after_non_drum = drum_bus.get("after_guard_non_drum_reference")
    bus_metrics = (
        before_drum,
        before_non_drum,
        after_drum,
        after_non_drum,
    )
    if any(
        not _valid_balanced_metrics(
            metrics,
            sample_rate=sample_rate,
            channels=channels,
            frames=frames,
            require_active=False,
        )
        for metrics in bus_metrics
    ):
        return False
    assert isinstance(before_drum, Mapping)
    assert isinstance(before_non_drum, Mapping)
    assert isinstance(after_drum, Mapping)
    assert isinstance(after_non_drum, Mapping)
    if dict(after_non_drum) != dict(before_non_drum):
        return False

    before = drum_bus.get("before_guard_overlap")
    after = drum_bus.get("after_guard_overlap")
    overlap_keys = {
        "block_count",
        "overlap_block_count",
        "drum_gate_dbfs",
        "non_drum_gate_dbfs",
        "drum_vs_non_drum_median_db",
        "drum_vs_non_drum_p95_db",
    }
    if (
        not isinstance(before, Mapping)
        or set(before) != overlap_keys
        or not isinstance(after, Mapping)
        or set(after) != overlap_keys
        or not _valid_nonnegative_int(before.get("block_count"))
        or not _valid_nonnegative_int(before.get("overlap_block_count"))
        or before["overlap_block_count"] > before["block_count"]
        or before["block_count"] != before_drum["block_count"]
        or after.get("block_count") != before["block_count"]
        or after.get("overlap_block_count") != before["overlap_block_count"]
        or after.get("non_drum_gate_dbfs") != before.get("non_drum_gate_dbfs")
    ):
        return False
    required = drum_bus.get("required_guard_gain_db")
    guard = drum_bus.get("guard_gain_db")
    if not _finite_number(required) or not _finite_number(guard):
        return False
    before_peak = before_drum.get("sample_peak_dbfs")
    after_peak = after_drum.get("sample_peak_dbfs")
    if before_peak is None:
        if after_peak is not None:
            return False
    elif (
        not _finite_number(before_peak)
        or not _finite_number(after_peak)
        or not math.isclose(
            float(after_peak),
            float(before_peak) + float(guard),
            abs_tol=2e-5,
        )
    ):
        return False
    if float(guard) > 1e-9 or float(guard) < (
        _BALANCED_MAXIMUM_DRUM_ATTENUATION_DB - 1e-9
    ):
        return False
    if math.isclose(float(guard), 0.0, abs_tol=1e-9):
        if dict(after_drum) != dict(before_drum):
            return False
    elif int(after_drum["active_block_count"]) > int(
        before_drum["active_block_count"]
    ) or int(after_drum["full_scale_sample_count"]) > int(
        before_drum["full_scale_sample_count"]
    ):
        return False
    elif int(after_drum["active_block_count"]) == int(
        before_drum["active_block_count"]
    ):
        for key in ("gated_rms_dbfs", "active_block_p95_dbfs"):
            before_value = before_drum.get(key)
            after_value = after_drum.get(key)
            if before_value is None:
                if after_value is not None:
                    return False
            elif not _finite_number(after_value) or not math.isclose(
                float(after_value),
                float(before_value) + float(guard),
                abs_tol=2e-5,
            ):
                return False

    overlap_count = int(before["overlap_block_count"])
    before_median = before.get("drum_vs_non_drum_median_db")
    before_p95 = before.get("drum_vs_non_drum_p95_db")
    applicable = overlap_count > 0
    if applicable:
        if (
            int(before_drum["active_block_count"]) < 1
            or int(before_non_drum["active_block_count"]) < 1
            or int(after_non_drum["active_block_count"]) < 1
            or not _finite_number(before_median)
            or not _finite_number(before_p95)
            or not _finite_number(before.get("drum_gate_dbfs"))
            or not _finite_number(before.get("non_drum_gate_dbfs"))
        ):
            return False
    elif before_median is not None or before_p95 is not None:
        return False
    if (before_drum.get("sample_peak_dbfs") is None) is not (
        before.get("drum_gate_dbfs") is None
    ) or (before_non_drum.get("sample_peak_dbfs") is None) is not (
        before.get("non_drum_gate_dbfs") is None
    ):
        return False
    expected_required = (
        min(
            0.0,
            _BALANCED_DRUM_OVERLAP_MEDIAN_TARGET_DB - float(before_median),
            _BALANCED_DRUM_OVERLAP_P95_MAXIMUM_DB - float(before_p95),
        )
        if applicable
        else 0.0
    )
    expected_guard = max(
        _BALANCED_MAXIMUM_DRUM_ATTENUATION_DB,
        min(0.0, expected_required),
    )
    if (
        not math.isclose(float(required), expected_required, abs_tol=1e-5)
        or not math.isclose(float(guard), expected_guard, abs_tol=1e-5)
        or drum_bus.get("guard_clamped")
        is not (expected_required < _BALANCED_MAXIMUM_DRUM_ATTENUATION_DB)
    ):
        return False
    if after.get("drum_gate_dbfs") != before.get("drum_gate_dbfs"):
        return False
    for key in (
        "drum_vs_non_drum_median_db",
        "drum_vs_non_drum_p95_db",
    ):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value is None:
            if after_value is not None:
                return False
        elif (
            not _finite_number(before_value)
            or not _finite_number(after_value)
            or not math.isclose(
                float(after_value),
                float(before_value) + float(guard),
                abs_tol=2e-5,
            )
        ):
            return False
    after_median = after.get("drum_vs_non_drum_median_db")
    after_p95 = after.get("drum_vs_non_drum_p95_db")
    target_applicable = overlap_count > 0
    if target_applicable:
        if not _finite_number(after_median) or not _finite_number(after_p95):
            return False
    elif after_median is not None or after_p95 is not None:
        return False
    median_met = (
        float(after_median) <= _BALANCED_DRUM_OVERLAP_MEDIAN_TARGET_DB + 1e-6
        if target_applicable
        else None
    )
    p95_met = (
        float(after_p95) <= _BALANCED_DRUM_OVERLAP_P95_MAXIMUM_DB + 1e-6
        if target_applicable
        else None
    )
    return (
        drum_bus.get("target_applicable") is target_applicable
        and drum_bus.get("overlap_median_target_met") is median_met
        and drum_bus.get("overlap_p95_target_met") is p95_met
        and drum_bus.get("target_met")
        is (median_met and p95_met if target_applicable else None)
    )


def _valid_balanced_receipt(
    receipt: Any,
    manifest: Mapping[str, Any],
) -> bool:
    receipt_keys = {
        "schema",
        "project_id",
        "selection_manifest_sha256",
        "bpm",
        "policy",
        "render_horizon_policy",
        "selection",
        "renderer",
        "input_fingerprints",
        "render_horizon",
        "preview",
        "recipe",
        "mix_report",
        "mastered",
        "mastering_boundary",
        "effects",
        "receipt_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
        return False
    unsigned_receipt = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    if (
        not _is_sha256(receipt.get("receipt_sha256"))
        or _document_hash(unsigned_receipt) != receipt["receipt_sha256"]
        or not _balanced_path_free_document(receipt)
    ):
        return False
    for key in (
        "project_id",
        "selection_manifest_sha256",
        "bpm",
        "policy",
        "render_horizon_policy",
        "selection",
        "renderer",
        "input_fingerprints",
        "render_horizon",
        "mix_report",
        "mastered",
        "mastering_boundary",
        "effects",
    ):
        if receipt.get(key) != manifest.get(key):
            return False
    for key in ("preview", "recipe"):
        receipt_record = receipt.get(key)
        manifest_record = manifest.get(key)
        if (
            not isinstance(receipt_record, Mapping)
            or set(receipt_record) != {"filename", "bytes", "sha256"}
            or not isinstance(manifest_record, Mapping)
            or receipt_record.get("filename") != manifest_record.get("name")
            or receipt_record.get("bytes") != manifest_record.get("bytes")
            or receipt_record.get("sha256") != manifest_record.get("sha256")
        ):
            return False
    return True


def _valid_balanced_artifact_record(record: Any) -> bool:
    return bool(
        isinstance(record, Mapping)
        and set(record) == {"path", "name", "bytes", "sha256"}
        and isinstance(record.get("path"), str)
        and record.get("path") == record.get("name")
        and "/" not in str(record.get("path"))
        and "\\" not in str(record.get("path"))
        and str(record.get("path")) not in {"", ".", ".."}
        and _valid_nonnegative_int(record.get("bytes"))
        and _is_sha256(record.get("sha256"))
    )


def _balanced_path_free_document(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                return False
            lowered = key.lower()
            if lowered == "path" or lowered.endswith("_path"):
                return False
            if not _balanced_path_free_document(child):
                return False
        return True
    if isinstance(value, list):
        return all(_balanced_path_free_document(child) for child in value)
    if isinstance(value, str):
        lowered = value.lower()
        if (
            value.startswith(("/", "~/", "../", ".\\"))
            or lowered.startswith("file://")
            or (len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"})
        ):
            return False
    return True


def _valid_nonnegative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _valid_positive_int(value: Any) -> bool:
    return _valid_nonnegative_int(value) and int(value) > 0


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def canonical_garageband_pack_basket(
    plan: Mapping[str, Any],
    included_item_ids: Sequence[str] | Any,
    source_audio_opt_in: bool,
) -> dict[str, Any]:
    """Validate and canonicalise one explicit basket in server plan order."""

    if plan.get("schema") != GARAGEBAND_PACK_PLAN_SCHEMA:
        raise ValueError("unsupported GarageBand pack plan schema")
    recorded_plan_hash = plan.get("plan_sha256")
    if recorded_plan_hash is not None and recorded_plan_hash != _pack_plan_hash(plan):
        raise ValueError("GarageBand pack plan hash is invalid")
    project_id = plan.get("project_id")
    basket_scope_sha256 = plan.get("basket_scope_sha256")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("GarageBand pack plan has no project identity")
    if not _is_sha256(basket_scope_sha256):
        raise ValueError("GarageBand pack plan has no valid basket scope")
    if not isinstance(source_audio_opt_in, bool):
        raise ValueError("source_audio_opt_in must be true or false")
    if not isinstance(included_item_ids, (list, tuple)):
        raise ValueError("included_item_ids must be a list")
    if len(included_item_ids) > 512:
        raise ValueError("GarageBand basket contains too many items")
    if any(not isinstance(item_id, str) for item_id in included_item_ids):
        raise ValueError("GarageBand basket item IDs must be text")
    if len(set(included_item_ids)) != len(included_item_ids):
        raise ValueError("GarageBand basket item IDs must not be repeated")
    items = plan.get("items")
    if not isinstance(items, list):
        raise ValueError("GarageBand pack plan has no item inventory")
    inventory: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("GarageBand pack plan contains an invalid item")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or item_id in inventory:
            raise ValueError("GarageBand pack plan contains an invalid item ID")
        inventory[item_id] = item
    unknown = [item_id for item_id in included_item_ids if item_id not in inventory]
    if unknown:
        raise ValueError("GarageBand basket contains an unknown item ID")
    included = set(included_item_ids)
    canonical_ids = [
        str(item["item_id"]) for item in items if item["item_id"] in included
    ]
    selected_midi_count = sum(
        inventory[item_id].get("kind") == "selected_midi" for item_id in canonical_ids
    )
    if selected_midi_count < 1:
        raise ValueError("GarageBand basket must include at least one selected MIDI")
    source_audio_count = sum(
        inventory[item_id].get("kind") == "source_audio" for item_id in canonical_ids
    )
    if source_audio_count and not source_audio_opt_in:
        raise ValueError("source audio requires a separate explicit local pack opt-in")
    basket = {
        "schema": GARAGEBAND_PACK_BASKET_SCHEMA,
        "project_id": project_id,
        "basket_scope_sha256": basket_scope_sha256,
        "included_item_ids": canonical_ids,
        "source_audio_opt_in": source_audio_opt_in,
    }
    basket["basket_sha256"] = _document_hash(basket)
    return basket


def _pack_basket_scope_hash(
    catalog: Mapping[str, Any], selection: Sequence[Mapping[str, Any]]
) -> str:
    """Hash export eligibility while deliberately ignoring listening context."""

    setup = catalog.get("setup", {})
    return _document_hash(
        {
            "schema": GARAGEBAND_PACK_BASKET_SCHEMA,
            "project_id": catalog.get("project_id"),
            "setup": {
                "bpm": setup.get("bpm"),
                "key": setup.get("key"),
                "tuning_hz": setup.get("tuning_hz"),
                "downbeat": setup.get("downbeat"),
            },
            "selection": _public_selection(selection),
        }
    )


def _garageband_pack_inventory(
    catalog: Mapping[str, Any],
    selection: Sequence[Mapping[str, Any]],
    *,
    basket_scope_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return a public inventory plus server-only records for copied inputs."""

    items: list[dict[str, Any]] = []
    internal: dict[str, dict[str, Any]] = {}
    for selected in selection:
        role = str(selected["role"])
        decision = str(selected["decision"])
        selection_index = int(selected["selection_index"])
        archive_path = str(selected["garageband_pack_archive_member"])
        if archive_path != _selected_midi_archive_member(
            selection_index, role, decision
        ):
            raise ValueError("selected MIDI GarageBand archive identity changed")
        item_id = _pack_item_id(
            {
                "kind": "selected_midi",
                "stem_id": selected["stem_id"],
                "candidate_id": selected["candidate_id"],
                "midi_sha256": selected["midi"]["sha256"],
                "basket_scope_sha256": basket_scope_sha256,
            }
        )
        item = {
            "item_id": item_id,
            "kind": "selected_midi",
            "label": f"{role.replace('_', ' ').title()} — {decision}",
            "stem_id": selected["stem_id"],
            "candidate_id": selected["candidate_id"],
            "candidate_label": selected.get("candidate_label"),
            "process": selected.get("process"),
            "role": role,
            "decision": decision,
            "selection_index": selection_index,
            "garageband_pack_archive_member": archive_path,
            "default_included": True,
            "generated": False,
            "archive_paths": [archive_path],
            "bytes": selected["midi"]["bytes"],
            "content_sha256": selected["midi"]["sha256"],
        }
        items.append(item)
        internal[item_id] = {"record": dict(selected["midi"])}

    if selection:
        proxy_id = _pack_item_id(
            {
                "kind": "arrangement_proxy",
                "basket_scope_sha256": basket_scope_sha256,
            }
        )
        items.append(
            {
                "item_id": proxy_id,
                "kind": "arrangement_proxy",
                "label": "Dry selected-arrangement proxy MIDI and WAV",
                "default_included": True,
                "generated": True,
                "archive_paths": [
                    "MIDI/selected-arrangement-proxy.mid",
                    "PREVIEW/selected-arrangement-proxy.wav",
                ],
            }
        )

    source_groups: dict[str, dict[str, Any]] = {}
    for stem in catalog.get("stems", []):
        record = stem.get("source")
        if not isinstance(record, Mapping):
            continue
        sha256 = str(record.get("sha256", ""))
        if not _is_sha256(sha256):
            raise ValueError("Workbench source audio has no valid content hash")
        group = source_groups.setdefault(
            sha256,
            {
                "record": dict(record),
                "roles": [],
                "labels": [],
                "stem_ids": [],
            },
        )
        role = path_free_role(stem.get("role"))[0]
        label = str(stem.get("label") or role.replace("_", " ").title())
        if role not in group["roles"]:
            group["roles"].append(role)
        if label not in group["labels"]:
            group["labels"].append(label)
        stem_id = str(stem.get("stem_id") or "")
        if stem_id and stem_id not in group["stem_ids"]:
            group["stem_ids"].append(stem_id)
    for source_index, (sha256, group) in enumerate(source_groups.items(), start=1):
        roles = list(group["roles"])
        record = group["record"]
        suffix = Path(str(record.get("name") or record.get("path") or ".wav")).suffix
        suffix = suffix.lower() if suffix else ".wav"
        if not suffix.startswith(".") or not suffix[1:].isalnum():
            suffix = ".wav"
        role_token = _safe_token(roles[0] if len(roles) == 1 else "shared-source")
        archive_path = f"STEMS/{source_index:02d}-{role_token}-source{suffix}"
        item_id = _pack_item_id(
            {
                "kind": "source_audio",
                "source_sha256": sha256,
                "basket_scope_sha256": basket_scope_sha256,
            }
        )
        items.append(
            {
                "item_id": item_id,
                "kind": "source_audio",
                "label": " / ".join(group["labels"]),
                "roles": roles,
                "stem_ids": list(group["stem_ids"]),
                "source_index": source_index,
                "default_included": False,
                "generated": False,
                "archive_paths": [archive_path],
                "bytes": record.get("bytes"),
                "content_sha256": sha256,
            }
        )
        internal[item_id] = {"record": record}
    return items, internal


def _pack_item_id(payload: Mapping[str, Any]) -> str:
    return "pack-item-" + _document_hash(payload)


def _pack_plan_hash(plan: Mapping[str, Any]) -> str:
    return _document_hash(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_balanced_deferred_claim(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def _path_exists_or_is_symlink(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def build_arrangement_tracks(
    selection: Sequence[Mapping[str, Any]],
) -> list[MidiTrack]:
    """Build one role-neutral GM proxy from an explicit selection.

    This is a rendering helper only.  It does not choose, rank, persist or
    review any candidate, so both the human-reviewed Workbench and the
    separately labelled automatic Simple workflow can share identical proxy
    construction without sharing decision state.
    """

    drum_notes: list[NoteEvent] = []
    melodic: list[tuple[Mapping[str, Any], list[NoteEvent]]] = []
    for item in selection:
        clips = read_midi_clips(item["midi_path"], role=str(item["role"]))
        notes = _clips_to_notes(clips)
        if not notes:
            continue
        if is_drum_role(str(item["role"])):
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
        decision = str(item.get("decision") or "selected")
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


# Backwards-compatible private name retained for older internal tests and
# callers.  New code should use the explicitly side-effect-free public helper.
_arrangement_tracks = build_arrangement_tracks


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


def _decoded_loop_window(start_seconds: Any, end_seconds: Any) -> tuple[float, float]:
    if isinstance(start_seconds, bool) or isinstance(end_seconds, bool):
        raise ValueError("decoded loop bounds must be finite numbers")
    try:
        start = float(start_seconds)
        end = float(end_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("decoded loop bounds must be finite numbers") from exc
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("decoded loop bounds must be finite numbers")
    if start < 0.0:
        raise ValueError("decoded loop start must be zero or greater")
    if start > _DECODED_LOOP_MAXIMUM_START_SECONDS:
        raise ValueError("decoded loop start must be within the first 24 hours")
    duration = end - start
    if not _DECODED_LOOP_MINIMUM_SECONDS <= duration <= _DECODED_LOOP_MAXIMUM_SECONDS:
        raise ValueError("decoded loop duration must be between 0.5 and 15.0 seconds")
    return start, end


def _decoded_arrangement_stream_preset(value: Any) -> str:
    if not isinstance(value, str) or value not in _DECODED_ARRANGEMENT_STREAM_PRESETS:
        raise ValueError(
            "decoded arrangement preset must be exactly source-only, "
            "selected-midi, hybrid, or main-only"
        )
    return value


def _require_decoded_arrangement_selection_hash(
    manifest: Mapping[str, Any], expected_sha256: Any
) -> None:
    if not _is_sha256(expected_sha256) or expected_sha256 != manifest.get(
        "selection_manifest_sha256"
    ):
        raise ValueError(
            "the decoded arrangement selection changed; reload the current "
            "arrangement before preparing it"
        )


def _longest_decoded_source(
    source_clock: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    if not source_clock:
        raise ValueError("decoded arrangement streaming requires source audio")
    longest = source_clock[0]
    for item in source_clock[1:]:
        if int(item["frames"]) * int(longest["sample_rate"]) > int(
            longest["frames"]
        ) * int(item["sample_rate"]):
            longest = item
    return longest


def _ceil_scaled_frame(frame: int, target_rate: int, source_rate: int) -> int:
    if frame < 0 or target_rate <= 0 or source_rate <= 0:
        raise ValueError("decoded arrangement frame scaling is invalid")
    numerator = frame * target_rate
    return (numerator + source_rate - 1) // source_rate


def _nearest_scaled_frame(frame: int, target_rate: int, source_rate: int) -> int:
    """Scale an integer frame exactly, retaining Python's ties-to-even rule."""

    if frame < 0 or target_rate <= 0 or source_rate <= 0:
        raise ValueError("decoded arrangement frame scaling is invalid")
    quotient, remainder = divmod(frame * target_rate, source_rate)
    doubled = remainder * 2
    if doubled < source_rate:
        return quotient
    if doubled > source_rate:
        return quotient + 1
    return quotient + (quotient % 2)


def _decoded_stream_chunk_plan(
    *,
    anchor_sample_rate: int,
    anchor_song_end_frame: int,
    inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if anchor_sample_rate <= 0 or anchor_song_end_frame <= 0 or not inputs:
        raise ValueError("decoded arrangement stream geometry is invalid")
    maximum_anchor_frames = min(
        anchor_song_end_frame,
        anchor_sample_rate * _DECODED_STREAM_MAXIMUM_CHUNK_SECONDS,
    )

    def projected(anchor_frames: int) -> tuple[int, int]:
        conservative: list[dict[str, int]] = []
        for item in inputs:
            scaled_frames = (
                _ceil_scaled_frame(
                    anchor_frames,
                    int(item["sample_rate"]),
                    anchor_sample_rate,
                )
                + 1
            )
            conservative.append(
                {
                    "start_frame": 0,
                    "end_frame": scaled_frames,
                    "channels": int(item["channels"]),
                }
            )
        return (
            _decoded_pcm16_output_upper_bound(conservative),
            _decoded_browser_two_chunk_float_bytes(anchor_frames, inputs),
        )

    low = 1
    high = maximum_anchor_frames
    selected_frames = 0
    while low <= high:
        candidate = (low + high) // 2
        pcm16_bytes, float_bytes = projected(candidate)
        if (
            pcm16_bytes <= _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES
            and float_bytes <= _DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES
        ):
            selected_frames = candidate
            low = candidate + 1
        else:
            high = candidate - 1
    if selected_frames <= 0:
        raise ValueError(
            "decoded arrangement tracks cannot fit one frame inside the chunk "
            "resource limits"
        )
    chunk_count = (anchor_song_end_frame + selected_frames - 1) // selected_frames
    if chunk_count > _DECODED_STREAM_MAXIMUM_CHUNKS:
        raise ValueError(
            "decoded arrangement needs more than 480 safe chunks; reduce the "
            "selected preset track count"
        )

    chunks: list[dict[str, Any]] = []
    maximum_pcm16_bytes = 0
    maximum_two_chunk_float_bytes = 0
    for index in range(chunk_count):
        start_frame = index * selected_frames
        end_frame = min(anchor_song_end_frame, start_frame + selected_frames)
        exact_inputs: list[dict[str, int]] = []
        for item in inputs:
            exact_inputs.append(
                {
                    "start_frame": _nearest_scaled_frame(
                        start_frame,
                        int(item["sample_rate"]),
                        anchor_sample_rate,
                    ),
                    "end_frame": _nearest_scaled_frame(
                        end_frame,
                        int(item["sample_rate"]),
                        anchor_sample_rate,
                    ),
                    "channels": int(item["channels"]),
                }
            )
        pcm16_bytes = _decoded_pcm16_output_upper_bound(exact_inputs)
        two_chunk_float_bytes = _decoded_browser_two_chunk_float_bytes(
            end_frame - start_frame,
            inputs,
        )
        if pcm16_bytes > _DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES:
            raise ValueError(
                "decoded arrangement chunk plan exceeds the 32 MiB PCM16 limit"
            )
        if two_chunk_float_bytes > _DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES:
            raise ValueError(
                "decoded arrangement chunk plan exceeds the 192 MiB two-chunk "
                "float-memory limit"
            )
        maximum_pcm16_bytes = max(maximum_pcm16_bytes, pcm16_bytes)
        maximum_two_chunk_float_bytes = max(
            maximum_two_chunk_float_bytes, two_chunk_float_bytes
        )
        chunks.append(
            {
                "chunk_index": index,
                "anchor_start_frame": start_frame,
                "anchor_end_frame": end_frame,
                "start_seconds": start_frame / anchor_sample_rate,
                "end_seconds": end_frame / anchor_sample_rate,
                "logical_end": index == chunk_count - 1,
            }
        )
    return {
        "chunk_anchor_frames": selected_frames,
        "chunk_seconds": selected_frames / anchor_sample_rate,
        "chunk_count": chunk_count,
        "maximum_pcm16_output_bytes": maximum_pcm16_bytes,
        "maximum_two_chunk_float_bytes": maximum_two_chunk_float_bytes,
        "chunks": chunks,
    }


def _valid_decoded_stream_chunk_plan(
    chunking: Mapping[str, Any],
    anchor: Mapping[str, Any],
    tracks: Sequence[Mapping[str, Any]],
) -> bool:
    try:
        sample_rate = anchor.get("sample_rate")
        song_end_frame = anchor.get("song_end_frame")
        if (
            isinstance(sample_rate, bool)
            or not isinstance(sample_rate, int)
            or isinstance(song_end_frame, bool)
            or not isinstance(song_end_frame, int)
        ):
            return False
        expected = _decoded_stream_chunk_plan(
            anchor_sample_rate=sample_rate,
            anchor_song_end_frame=song_end_frame,
            inputs=tracks,
        )
    except (KeyError, TypeError, ValueError):
        return False
    return dict(chunking) == expected


def _decoded_declared_input_bytes(records: Sequence[tuple[str, Any]]) -> int:
    """Validate and sum catalogued input sizes before expensive rendering."""

    total = 0
    for label, record in records:
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} record is invalid")
        value = record.get("bytes")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} byte count is invalid")
        total += value
    return total


def _require_decoded_input_limit(total_bytes: int) -> None:
    if total_bytes > _DECODED_LOOP_MAXIMUM_INPUT_BYTES:
        raise ValueError("decoded loop inputs exceed the 2 GiB aggregate safety limit")


def _decoded_pcm16_output_upper_bound(inputs: Sequence[Mapping[str, Any]]) -> int:
    """Return a conservative pre-write bound for separate PCM16 WAV tracks."""

    total = 0
    for item in inputs:
        start_frame = item.get("start_frame")
        end_frame = item.get("end_frame")
        channels = item.get("channels")
        if (
            isinstance(start_frame, bool)
            or not isinstance(start_frame, int)
            or isinstance(end_frame, bool)
            or not isinstance(end_frame, int)
            or end_frame <= start_frame
            or isinstance(channels, bool)
            or not isinstance(channels, int)
            or channels not in {1, 2}
        ):
            raise ValueError("decoded arrangement output geometry is invalid")
        total += (
            end_frame - start_frame
        ) * channels * 2 + _DECODED_PCM16_WAV_HEADER_BUDGET_BYTES
    return total


def _decoded_browser_two_chunk_float_bytes(
    anchor_frames: int,
    inputs: Sequence[Mapping[str, Any]],
) -> int:
    """Project two Web Audio float32 chunks after anchor-rate decoding.

    ``decodeAudioData`` resamples every WAV to the AudioContext rate.  Native
    chunk frame counts therefore cannot safely estimate browser memory when the
    anchor clock has a higher sample rate than one or more inputs.
    """

    if (
        isinstance(anchor_frames, bool)
        or not isinstance(anchor_frames, int)
        or anchor_frames <= 0
    ):
        raise ValueError("decoded arrangement anchor geometry is invalid")
    total = 0
    for item in inputs:
        channels = item.get("channels")
        if (
            isinstance(channels, bool)
            or not isinstance(channels, int)
            or channels not in {1, 2}
        ):
            raise ValueError("decoded arrangement float geometry is invalid")
        total += anchor_frames * channels * 4 * 2
    return total


def _decoded_loop_candidate_ids(candidate_ids: Any) -> tuple[str, ...]:
    if isinstance(candidate_ids, (str, bytes)) or not isinstance(
        candidate_ids, Sequence
    ):
        raise ValueError("candidate_ids must be a sequence of catalog candidate IDs")
    values = tuple(candidate_ids)
    if not values:
        raise ValueError("choose at least one candidate for decoded comparison")
    if len(values) > _DECODED_LOOP_MAXIMUM_CANDIDATES:
        raise ValueError("decoded comparison supports at most 6 candidates")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("candidate_ids must contain non-empty strings")
    if len(set(values)) != len(values):
        raise ValueError("decoded comparison candidate IDs must be unique")
    return values


def _decoded_audio_modules() -> tuple[Any, Any]:
    try:
        import numpy as np
        import soundfile
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "decoded stem comparison requires the optional audio dependencies "
            "numpy and soundfile; install Sunofriend with the convert extra"
        ) from exc
    return np, soundfile


def _decoded_audio_info(soundfile: Any, path: Path, *, label: str) -> dict[str, int]:
    try:
        info = soundfile.info(str(path))
    except Exception as exc:
        raise ValueError(f"{label} is not a readable local audio file") from exc
    sample_rate = int(info.samplerate)
    channels = int(info.channels)
    frames = int(info.frames)
    if (
        not _DECODED_LOOP_MINIMUM_SAMPLE_RATE
        <= sample_rate
        <= (_DECODED_LOOP_MAXIMUM_SAMPLE_RATE)
    ):
        raise ValueError(f"{label} sample rate must be between 8 and 96 kHz")
    if channels not in {1, 2}:
        raise ValueError(f"{label} must be mono or stereo")
    if frames <= 0:
        raise ValueError(f"{label} must contain at least one audio frame")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
    }


def _nearest_audio_frame(seconds: float, sample_rate: int) -> int:
    """Quantise seconds to the nearest frame using Python's ties-to-even rule."""

    return int(round(seconds * sample_rate))


def _read_padded_audio_window(
    np: Any,
    soundfile: Any,
    path: Path,
    *,
    start_frame: int,
    frames: int,
    channels: int,
) -> Any:
    output = np.zeros((frames, channels), dtype=np.float32)
    try:
        with soundfile.SoundFile(str(path), mode="r") as source:
            if int(source.channels) != channels:
                raise ValueError("audio channel count changed while decoding")
            available = max(0, int(len(source)) - start_frame)
            readable = min(frames, available)
            if readable:
                source.seek(start_frame)
                samples = source.read(
                    frames=readable,
                    dtype="float32",
                    always_2d=True,
                )
                if samples.shape != (readable, channels):
                    raise ValueError("decoded audio window has unexpected geometry")
                output[:readable, :] = samples
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("audio changed or became unreadable while decoding") from exc
    return output


def _restrict_private_permissions(path: Path, mode: int) -> None:
    """Set owner-only permissions for private decoded excerpts where supported."""

    try:
        path.chmod(mode)
    except NotImplementedError:  # pragma: no cover - platform-specific fallback
        pass


def _write_verified_private_snapshot(
    source_path: Path,
    expected_record: Mapping[str, Any],
    destination: Path,
    *,
    label: str,
) -> Path:
    """Copy one open input handle and verify the bytes used for decoding."""

    expected_bytes = expected_record.get("bytes")
    expected_sha256 = str(expected_record.get("sha256", ""))
    digest = hashlib.sha256()
    written = 0
    try:
        with source_path.open("rb") as source, destination.open("xb") as target:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                target.write(block)
                digest.update(block)
                written += len(block)
        _restrict_private_permissions(destination, 0o600)
        if written != expected_bytes or digest.hexdigest() != expected_sha256:
            raise ValueError(f"{label} changed while creating a verified snapshot")
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _directory_regular_file_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _regular_file_stat_signature(
    path: Path, expected_bytes: int | None = None
) -> tuple[int, int, int, int, int, int]:
    """Return a cheap identity for content which was hash-verified earlier."""

    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError("verified decoded stream input is no longer a regular file")
    if expected_bytes is not None and file_stat.st_size != expected_bytes:
        raise ValueError("verified decoded stream input size changed")
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
        file_stat.st_mode,
    )


def _prune_stale_private_builds(parent: Path) -> None:
    cutoff = time.time() - _DECODED_LOOP_BUILDING_MAXIMUM_AGE_SECONDS
    for path in parent.iterdir():
        if (
            not path.name.startswith(".")
            or ".building-" not in path.name
            or path.is_symlink()
        ):
            continue
        try:
            stale = path.is_dir() and path.stat().st_mtime < cutoff
        except OSError:
            continue
        if stale:
            _remove_generated_path(path)


def _stem(catalog: Mapping[str, Any], stem_id: str) -> Mapping[str, Any]:
    for stem in catalog.get("stems", []):
        if stem.get("stem_id") == stem_id:
            return stem
    raise ValueError("unknown workbench stem_id")


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


def _preview_role(stem: Mapping[str, Any], role_override: str | None) -> str:
    return path_free_role(stem.get("role") if role_override is None else role_override)[
        0
    ]


def _program_for_role(role: str) -> int:
    return starter_program_for_role(role)


def _program_label(role: str, program: int, channel: int) -> str:
    if channel == 9:
        return "General MIDI drum kit proxy"
    if role.lower() == "bass" and program == 38:
        return "GM 39 Synth Bass 1 proxy"
    return f"General MIDI program {program + 1} proxy"


def _decoded_stem_audition_level(path: Path) -> dict[str, Any]:
    """Return a deterministic, disclosed browser gain for one short-loop track."""

    metrics = measure_balanced_audio(path)
    measured_level = metrics.get("gated_rms_dbfs")
    measured_peak = metrics.get("sample_peak_dbfs")
    if measured_level is None:
        return {
            "policy": _DECODED_STEM_LEVEL_POLICY,
            "audible": False,
            "measurement": metrics,
            "raw_target_gain_db": None,
            "bounded_target_gain_db": 0.0,
            "peak_room_db": None,
            "applied_gain_db": 0.0,
            "limit": "no_active_blocks",
        }

    raw_gain = _BALANCED_AUDITION_TARGET_GATED_RMS_DBFS - float(measured_level)
    bounded_gain = max(
        float(_BALANCED_SOURCE_MATCH_GAIN_DB[0]),
        min(float(_BALANCED_MAXIMUM_NORMALISATION_BOOST_DB), raw_gain),
    )
    peak_room = (
        None
        if measured_peak is None
        else _BALANCED_SAMPLE_PEAK_CEILING_DBFS - float(measured_peak)
    )
    applied_gain = bounded_gain if peak_room is None else min(bounded_gain, peak_room)
    limit = None
    if bounded_gain < raw_gain:
        limit = "maximum_positive_boost"
    elif bounded_gain > raw_gain:
        limit = "minimum_gain"
    if peak_room is not None and applied_gain < bounded_gain:
        limit = "sample_peak_ceiling"
    return {
        "policy": _DECODED_STEM_LEVEL_POLICY,
        "audible": True,
        "measurement": metrics,
        "raw_target_gain_db": round(raw_gain, 6),
        "bounded_target_gain_db": round(bounded_gain, 6),
        "peak_room_db": (None if peak_room is None else round(peak_room, 6)),
        "applied_gain_db": round(applied_gain, 6),
        "limit": limit,
    }


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
            "selection_index": item["selection_index"],
            "garageband_pack_archive_member": item["garageband_pack_archive_member"],
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


def _garageband_pack_readme(
    catalog: Mapping[str, Any],
    *,
    selected_midi_count: int,
    source_audio_count: int,
    arrangement_proxy_included: bool,
) -> str:
    setup = catalog.get("setup", {})
    lines = [
        "Sunofriend GarageBand pack",
        "============================",
        "",
        f"Project: {catalog.get('name')}",
        f"Selected MIDI files: {selected_midi_count}",
        f"Opted-in source stems: {source_audio_count}",
        f"Set GarageBand tempo to: {setup.get('bpm')} BPM",
        f"Project key: {setup.get('key') or 'not inferred'}",
        f"Source tuning: {setup.get('tuning_hz') or 'not inferred'} Hz",
        (
            f"Downbeat: {setup.get('downbeat')}"
            if setup.get("downbeat") is not None
            else "Downbeat: not confirmed"
        ),
        "",
        "1. Set the GarageBand tempo above before importing files.",
        "2. Drag each checked file in MIDI/ onto its own Software Instrument track.",
        "3. Choose a playable GarageBand patch for every MIDI track.",
    ]
    if source_audio_count:
        lines.append(
            "4. Source audio in STEMS/ was included only by your explicit local opt-in."
        )
    else:
        lines.append("4. No source audio is included in this pack.")
    if arrangement_proxy_included:
        lines.append(
            "5. The selected-arrangement proxy is a dry convenience audition only."
        )
    else:
        lines.append("5. No generated arrangement proxy was requested.")
    lines.extend(
        [
            "",
            "The numbered MIDI files are byte-for-byte copies of the checked explicit",
            "choices. They are authoritative; the basket does not alter musical choices,",
            "MIDI notes, timing, velocities or GarageBand instruments.",
            "",
        ]
    )
    return "\n".join(lines)


def _verified_record_bytes(record: Mapping[str, Any], *, label: str) -> bytes:
    """Read once, then verify the exact bytes which will enter an archive."""

    path = Path(str(record.get("path", ""))).resolve()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} no longer exists: {path}") from exc
    if len(data) != record.get("bytes") or hashlib.sha256(
        data
    ).hexdigest() != record.get("sha256"):
        raise ValueError(f"{label} changed after it was catalogued")
    return data


def _pack_manifest_item(
    *,
    item_id: str,
    kind: str,
    archive_path: str,
    data: bytes,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "kind": kind,
        "archive_path": archive_path,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


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


def _selected_midi_archive_member(
    selection_index: int,
    role: str,
    decision: str,
) -> str:
    if (
        isinstance(selection_index, bool)
        or not isinstance(selection_index, int)
        or selection_index < 1
    ):
        raise ValueError("selected MIDI selection index is invalid")
    return f"MIDI/{selection_index:02d}-{_safe_token(role)}-{_safe_token(decision)}.mid"


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
    "BALANCED_ARRANGEMENT_SCHEMA",
    "DECODED_ARRANGEMENT_CHUNK_SCHEMA",
    "DECODED_ARRANGEMENT_STREAM_SCHEMA",
    "DECODED_STEM_LOOP_SCHEMA",
    "GARAGEBAND_HANDOFF_SCHEMA",
    "GARAGEBAND_PACK_BASKET_SCHEMA",
    "GARAGEBAND_PACK_PLAN_SCHEMA",
    "GARAGEBAND_PACK_SCHEMA",
    "NEUTRAL_PREVIEW_SCHEMA",
    "SELECTED_MIDI_OVERLAP_SCHEMA",
    "WorkbenchArtifacts",
    "WorkbenchPackConflictError",
    "canonical_garageband_pack_basket",
    "selected_candidates",
    "build_arrangement_tracks",
]
