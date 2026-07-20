"""Blind, source-aligned and fixed-window RMS-matched MIDI A/B reviews."""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import soundfile

from .clip import read_midi_clips
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .render import find_fluidsynth, find_soundfont, render_midi_to_wav


MIDI_AB_REVIEW_SCHEMA = "sunofriend.midi-ab-review.v1"
MIDI_AB_ANSWER_KEY_SCHEMA = "sunofriend.midi-ab-answer-key.v1"
MIDI_AB_RESULT_SCHEMA = "sunofriend.midi-ab-result.v1"
MIDI_AB_AUDIO_MANIFEST_SCHEMA = "sunofriend.midi-ab-audio-manifest.v1"

_CHOICES = {"candidate_a", "candidate_b", "equivalent", "neither", "cannot_tell"}
_RENDER_GAIN = 0.7
_MAX_INTERVAL_SECONDS = 15.0
_MIN_INTERVAL_SECONDS = 0.5
_MAX_PAIR_ATTENUATION_DB = 18.0
_MAX_RMS_MISMATCH_DB = 0.05
_MIN_CANDIDATE_RMS_DBFS = -60.0
_FULL_SCALE_GUARD = 0.9999
_MELODIC_CHANNELS = tuple(channel for channel in range(16) if channel != 9)


def create_midi_ab_review(
    source_audio_path: str | Path,
    first_midi_path: str | Path,
    second_midi_path: str | Path,
    intervals: Sequence[tuple[float, float, str]],
    out_dir: str | Path,
    *,
    bpm: float,
    midi_time_at_source_start_seconds: float,
    gm_program: int = 4,
    soundfont_path: str | Path | None = None,
    question: str = (
        "Which candidate is more musically useful without distracting missing, "
        "extra, mistimed or wrongly pitched notes?"
    ),
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one local blind review without changing source audio or MIDI.

    Candidate loudness is matched pairwise inside each fixed source-time window.
    The louder render is attenuated to the quieter render's channel-energy RMS;
    the source remains an unlevelled reference and no limiter, time shift, stretch,
    compression or EQ is applied.
    """

    source = Path(source_audio_path).expanduser().resolve()
    first = Path(first_midi_path).expanduser().resolve()
    second = Path(second_midi_path).expanduser().resolve()
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"MIDI A/B review already exists: {destination}")
    _require_file(source, "source audio")
    _require_file(first, "first MIDI")
    _require_file(second, "second MIDI")
    if first == second:
        raise ValueError("MIDI A/B review inputs must be different files")
    tempo = _positive_finite(bpm, "bpm")
    midi_time_at_source_start = _finite(
        midi_time_at_source_start_seconds,
        "midi_time_at_source_start_seconds",
    )
    program = _midi_value(gm_program, "gm_program")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("MIDI A/B review question must not be empty")

    source_values, sample_rate = soundfile.read(source, dtype="float64", always_2d=True)
    if not len(source_values) or not np.all(np.isfinite(source_values)):
        raise ValueError("MIDI A/B source audio is empty or non-finite")
    source_duration = len(source_values) / int(sample_rate)
    checked_intervals = _validated_intervals(intervals, source_duration)
    midi_frame_offset = round(midi_time_at_source_start * sample_rate)
    if not math.isclose(
        midi_time_at_source_start * sample_rate,
        midi_frame_offset,
        rel_tol=0.0,
        abs_tol=1e-7,
    ):
        raise ValueError(
            "midi_time_at_source_start_seconds must align to a source sample frame"
        )
    if (
        min(round(start * sample_rate) for start, _, _ in checked_intervals)
        + midi_frame_offset
        < 0
    ):
        raise ValueError("MIDI A/B interval begins before candidate MIDI time zero")
    required_candidate_frames = max(
        round(end * sample_rate) + midi_frame_offset for _, end, _ in checked_intervals
    )

    soundfont = (
        Path(soundfont_path).expanduser().resolve()
        if soundfont_path is not None
        else Path(find_soundfont()).expanduser().resolve()
    )
    _require_file(soundfont, "SoundFont")
    fluidsynth = Path(find_fluidsynth()).expanduser().resolve()
    renderer = _renderer_record(fluidsynth)
    soundfont_record = _file_record(soundfont)
    source_record = _file_record(source)
    first_record = _file_record(first)
    second_record = _file_record(second)
    render_contract = {
        "policy": "one-neutral-program-dry-fluidsynth-v1",
        "renderer": renderer,
        "soundfont": _without_path(soundfont_record),
        "program": program,
        "channels": list(_MELODIC_CHANNELS),
        "sample_rate": int(sample_rate),
        "render_gain": _RENDER_GAIN,
        "reverb": False,
        "chorus": False,
        "output_subtype": "PCM_24",
    }
    alignment_contract = {
        "policy": "explicit-common-midi-time-at-source-start-v1",
        "midi_time_at_source_start_seconds": midi_time_at_source_start,
        "midi_frame_offset": midi_frame_offset,
        "sample_rate": int(sample_rate),
        "same_offset_for_both_candidates": True,
        "time_shift_inferred": False,
    }
    interval_contract = [
        {
            "start_seconds": start,
            "end_seconds": end,
            "listening_focus": focus,
        }
        for start, end, focus in checked_intervals
    ]
    package_contract = {
        "source_sha256": source_record["sha256"],
        "first_midi_sha256": first_record["sha256"],
        "second_midi_sha256": second_record["sha256"],
        "bpm": tempo,
        "intervals": interval_contract,
        "render_contract": render_contract,
        "alignment_contract": alignment_contract,
    }
    package_commitment = _document_hash(package_contract)
    blind_nonce = secrets.token_bytes(32)
    blind_nonce_commitment = hashlib.sha256(
        blind_nonce + bytes.fromhex(package_commitment)
    ).hexdigest()

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise FileExistsError(f"MIDI A/B review already exists: {destination}") from exc
    work = destination
    try:
        private_dir = work / "private-evidence"
        audio_dir = work / "audio"
        private_dir.mkdir()
        audio_dir.mkdir()

        input_rows = []
        raw_audio: dict[str, np.ndarray] = {}
        for identity, midi_path, midi_record in (
            ("input_1", first, first_record),
            ("input_2", second, second_record),
        ):
            proxy = private_dir / f"{identity}-neutral.mid"
            proxy_audit = _write_neutral_proxy(
                midi_path,
                proxy,
                bpm=tempo,
                program=program,
            )
            raw_path = private_dir / f"{identity}-raw.wav"
            render_midi_to_wav(
                proxy,
                raw_path,
                sample_rate=int(sample_rate),
                gain=_RENDER_GAIN,
                soundfont_path=soundfont,
                fluidsynth_path=fluidsynth,
            )
            values, rendered_rate = soundfile.read(
                raw_path, dtype="float64", always_2d=True
            )
            if int(rendered_rate) != int(sample_rate):
                raise ValueError("MIDI A/B renders do not share the source sample rate")
            if values.shape[1] != source_values.shape[1]:
                if source_values.shape[1] == 1 and values.shape[1] == 2:
                    source_values = np.repeat(source_values, 2, axis=1)
                else:
                    raise ValueError(
                        "MIDI A/B source and renders must have compatible channels"
                    )
            if not len(values) or not np.all(np.isfinite(values)):
                raise ValueError(f"MIDI A/B {identity} render is empty or non-finite")
            raw_audio[identity] = _fit_frames(values, required_candidate_frames)
            input_rows.append(
                {
                    "identity": identity,
                    "midi": midi_record,
                    "proxy_midi": _file_record(proxy),
                    "proxy_audit": proxy_audit,
                    "raw_render": _file_record(raw_path),
                }
            )

        _verify_unchanged(fluidsynth, renderer, label="FluidSynth executable")
        _verify_unchanged(soundfont, soundfont_record, label="SoundFont")
        _verify_unchanged(source, source_record, label="source audio")
        _verify_unchanged(first, first_record, label="first MIDI")
        _verify_unchanged(second, second_record, label="second MIDI")

        manifest_files: list[dict[str, Any]] = []
        answer_units: list[dict[str, Any]] = []
        units: list[dict[str, Any]] = []
        for index, (start, end, focus) in enumerate(checked_intervals, start=1):
            unit_id = f"{index:02d}-loop"
            mapping = _blind_mapping(blind_nonce, package_commitment, unit_id)
            start_frame = round(start * sample_rate)
            end_frame = round(end * sample_rate)
            candidate_start_frame = start_frame + midi_frame_offset
            candidate_end_frame = end_frame + midi_frame_offset
            source_crop = np.array(source_values[start_frame:end_frame], copy=True)
            input_crops = {
                identity: np.array(
                    values[candidate_start_frame:candidate_end_frame], copy=True
                )
                for identity, values in raw_audio.items()
            }
            matched, level_evidence = _pairwise_level_match(
                input_crops,
                minimum_rms_dbfs=_MIN_CANDIDATE_RMS_DBFS,
            )

            source_path = audio_dir / f"{unit_id}-source.wav"
            _write_pcm24(source_path, source_crop, int(sample_rate))
            anonymous: dict[str, dict[str, Any]] = {}
            for candidate_name in ("candidate_a", "candidate_b"):
                identity = mapping[candidate_name]
                path = audio_dir / f"{unit_id}-{candidate_name[-1]}.wav"
                _write_pcm24(path, matched[identity], int(sample_rate))
                anonymous[candidate_name] = _audio_record(
                    path,
                    work,
                    expected_frames=end_frame - start_frame,
                    expected_rate=int(sample_rate),
                )
            source_audio_record = _audio_record(
                source_path,
                work,
                expected_frames=end_frame - start_frame,
                expected_rate=int(sample_rate),
            )
            final_mismatch = abs(
                anonymous["candidate_a"]["rms_dbfs"]
                - anonymous["candidate_b"]["rms_dbfs"]
            )
            if final_mismatch > _MAX_RMS_MISMATCH_DB:
                raise RuntimeError(
                    "MIDI A/B final PCM candidate RMS mismatch exceeds 0.05 dB"
                )
            level_evidence["final_pcm24"] = {
                "candidate_a_rms_dbfs": anonymous["candidate_a"]["rms_dbfs"],
                "candidate_b_rms_dbfs": anonymous["candidate_b"]["rms_dbfs"],
                "mismatch_db": round(final_mismatch, 6),
                "within_tolerance": True,
            }
            for purpose, record in (
                ("source-reference", source_audio_record),
                ("blinded-candidate-a", anonymous["candidate_a"]),
                ("blinded-candidate-b", anonymous["candidate_b"]),
            ):
                manifest_files.append(
                    {
                        "path": record["audio"],
                        "sha256": record["sha256"],
                        "purpose": purpose,
                    }
                )
            unit = {
                "unit_id": unit_id,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": round(end - start, 9),
                "frame_start": start_frame,
                "frame_end": end_frame,
                "frame_count": end_frame - start_frame,
                "sample_rate": int(sample_rate),
                "candidate_frame_start": candidate_start_frame,
                "candidate_frame_end": candidate_end_frame,
                "midi_time_at_source_start_seconds": midi_time_at_source_start,
                "listening_focus": focus,
                "source": source_audio_record,
                "candidate_a": anonymous["candidate_a"],
                "candidate_b": anonymous["candidate_b"],
                "heard": {
                    "source": False,
                    "candidate_a": False,
                    "candidate_b": False,
                },
                "choice": None,
                "notes": "",
            }
            units.append(unit)
            answer_units.append(
                {
                    "unit_id": unit_id,
                    "candidate_a": mapping["candidate_a"],
                    "candidate_b": mapping["candidate_b"],
                    "level_match": level_evidence,
                    "immutable_review_unit_sha256": _document_hash(
                        _immutable_review_unit(unit)
                    ),
                }
            )

        manifest = {
            "schema": MIDI_AB_AUDIO_MANIFEST_SCHEMA,
            "operation": "midi-ab-review-audio",
            "package_commitment": package_commitment,
            "file_count": len(manifest_files),
            "files": manifest_files,
        }
        manifest_path = work / "midi_ab_audio_manifest.json"
        _write_json(manifest_path, manifest)
        manifest_hash = _sha256(manifest_path)

        answer_key = {
            "schema": MIDI_AB_ANSWER_KEY_SCHEMA,
            "operation": "midi-ab-answer-key",
            "status": "complete",
            "package_commitment": package_commitment,
            "mapping_policy": "secret-random-per-unit-v1",
            "blind_nonce_hex": blind_nonce.hex(),
            "blind_nonce_commitment": blind_nonce_commitment,
            "package_contract": package_contract,
            "source": source_record,
            "inputs": input_rows,
            "units": answer_units,
        }
        answer_path = work / "midi_ab_answer_key.json"
        _write_json(answer_path, answer_key)
        answer_hash = _sha256(answer_path)

        seed = {
            "schema": MIDI_AB_REVIEW_SCHEMA,
            "operation": "midi-ab-review",
            "status": "unreviewed",
            "blind": True,
            "review_required": True,
            "package_commitment": package_commitment,
            "question": question.strip(),
            "policy": {
                "choices": sorted(_CHOICES),
                "candidate_identity_hidden_in_html": True,
                "source_reference_is_not_a_candidate": True,
                "source_reference_level_matched": False,
                "candidate_level_method": "pairwise-fixed-window-rms-attenuation-only-v1",
                "level_claim": "sample RMS, not LUFS or true peak",
                "minimum_candidate_rms_dbfs": _MIN_CANDIDATE_RMS_DBFS,
                "time_shift_seconds": 0.0,
                "time_stretch_ratio": 1.0,
                "limiter_used": False,
                "compression_used": False,
                "equalisation_used": False,
            },
            "render_contract": render_contract,
            "alignment_contract": alignment_contract,
            "source": {
                **_without_path(source_record),
                "sample_rate": int(sample_rate),
                "channels": int(source_values.shape[1]),
                "frames": int(len(source_values)),
                "duration_seconds": round(source_duration, 9),
            },
            "provenance": _json_copy(provenance or {}),
            "review_evidence": {
                "package_directory": ".",
                "seed": "midi_ab_review.json",
                "manifest": "midi_ab_audio_manifest.json",
                "manifest_sha256": manifest_hash,
                "audio_file_count": len(manifest_files),
            },
            "answer_key": {
                "path": "midi_ab_answer_key.json",
                "sha256": answer_hash,
                "embedded_in_html": False,
            },
            "blind_assignment": {
                "policy": "secret-random-per-unit-v1",
                "nonce_commitment": blind_nonce_commitment,
                "same_mapping_required_for_every_unit": False,
            },
            "summary": {
                "unit_count": len(units),
                "reviewed_unit_count": 0,
            },
            "units": units,
            "effects": _zero_effects(),
            "warnings": [
                "Candidate identities are intentionally absent from the HTML; do not open the separate answer key before reviewing.",
                "Only candidate A/B are fixed-window RMS matched. The source is an unlevelled reference.",
                "The common candidate-to-source time origin was supplied explicitly; no alignment offset was inferred.",
                "Sample RMS is not LUFS, perceived loudness or true peak; a final GarageBand check may still disagree.",
                "This review cannot change MIDI, select a winner, promote a preset or change a default.",
            ],
        }
        seed_path = work / "midi_ab_review.json"
        _write_json(seed_path, seed)
        html_path = work / "midi_ab_review.html"
        html_path.write_text(_review_html(seed), encoding="utf-8")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    return {
        "schema": MIDI_AB_REVIEW_SCHEMA,
        "status": "complete",
        "out_dir": str(destination),
        "unit_count": len(units),
        "html": str(destination / "midi_ab_review.html"),
        "seed": str(destination / "midi_ab_review.json"),
        "answer_key": str(destination / "midi_ab_answer_key.json"),
        "answer_key_sha256": answer_hash,
        "audio_manifest": str(destination / "midi_ab_audio_manifest.json"),
        "audio_manifest_sha256": manifest_hash,
        "effects": _zero_effects(),
    }


def resolve_midi_ab_review(
    review_path: str | Path,
    out: str | Path,
    *,
    package_dir: str | Path,
) -> dict[str, Any]:
    """Resolve explicit blinded choices without applying or promoting either MIDI."""

    review_file = Path(review_path).expanduser().resolve()
    package = Path(package_dir).expanduser().resolve()
    if not package.is_dir():
        raise ValueError(f"MIDI A/B package directory does not exist: {package}")
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"MIDI A/B result already exists: {output}")
    review = _read_json(review_file)
    if review.get("schema") != MIDI_AB_REVIEW_SCHEMA:
        raise ValueError("Unsupported MIDI A/B review schema")
    seed_path = package / "midi_ab_review.json"
    seed = _read_json(seed_path)
    if (
        seed.get("schema") != MIDI_AB_REVIEW_SCHEMA
        or seed.get("status") != "unreviewed"
        or seed.get("blind") is not True
    ):
        raise ValueError("MIDI A/B package seed is invalid")
    if not _browser_json_equal(
        _immutable_review_document(review),
        _immutable_review_document(seed),
    ):
        raise ValueError("MIDI A/B reviewed export changed immutable package fields")
    if review.get("status") != "reviewed" or review.get("blind") is not True:
        raise ValueError("MIDI A/B review is not complete and blinded")
    units = list(review.get("units") or [])
    summary = review.get("summary") or {}
    if not units or int(summary.get("unit_count", -1)) != len(units):
        raise ValueError("MIDI A/B review unit count is invalid")
    if int(summary.get("reviewed_unit_count", -1)) != len(units):
        raise ValueError("MIDI A/B review is not marked complete for every unit")
    unit_ids = [str(unit.get("unit_id")) for unit in units]
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError("MIDI A/B review contains duplicate units")
    for unit in units:
        if unit.get("choice") not in _CHOICES:
            raise ValueError(f"MIDI A/B unit {unit.get('unit_id')} has no valid choice")
        heard = unit.get("heard")
        if (
            not isinstance(heard, Mapping)
            or set(heard) != {"source", "candidate_a", "candidate_b"}
            or any(
                heard.get(name) is not True
                for name in ("source", "candidate_a", "candidate_b")
            )
        ):
            raise ValueError(f"MIDI A/B unit {unit.get('unit_id')} is not marked heard")
        if not isinstance(unit.get("notes"), str):
            raise ValueError(f"MIDI A/B unit {unit.get('unit_id')} notes must be text")
    if review.get("effects") != _zero_effects():
        raise ValueError("MIDI A/B review declares an automatic effect")

    _verify_review_audio(review, package)
    answer_record = seed.get("answer_key") or {}
    answer_path = _package_file(package, answer_record.get("path"), "answer key")
    if not answer_path.is_file() or _sha256(answer_path) != answer_record.get("sha256"):
        raise ValueError("MIDI A/B answer key changed or is missing")
    answer = _read_json(answer_path)
    if (
        answer.get("schema") != MIDI_AB_ANSWER_KEY_SCHEMA
        or answer.get("status") != "complete"
        or answer.get("package_commitment") != review.get("package_commitment")
    ):
        raise ValueError("MIDI A/B answer key is incompatible")
    answer_unit_rows = list(answer.get("units") or [])
    answer_units = {str(unit.get("unit_id")): unit for unit in answer_unit_rows}
    if len(answer_units) != len(answer_unit_rows) or set(answer_units) != set(unit_ids):
        raise ValueError("MIDI A/B answer key units do not match the review")
    _verify_private_inputs(answer)
    _verify_package_contract(answer, seed)
    _verify_blind_assignments(answer, seed, units)

    counts = {identity: 0 for identity in (*_CHOICES, "input_1", "input_2")}
    resolved_units = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        choice = str(unit["choice"])
        key = answer_units[unit_id]
        if {key.get("candidate_a"), key.get("candidate_b")} != {
            "input_1",
            "input_2",
        }:
            raise ValueError(f"MIDI A/B answer mapping is invalid for {unit_id}")
        if choice in {"candidate_a", "candidate_b"}:
            resolved_identity = str(key[choice])
        else:
            resolved_identity = choice
        counts[resolved_identity] += 1
        resolved_units.append(
            {
                "unit_id": unit_id,
                "start_seconds": unit.get("start_seconds"),
                "end_seconds": unit.get("end_seconds"),
                "listening_focus": unit.get("listening_focus"),
                "choice": choice,
                "resolved_identity": resolved_identity,
                "notes": str(unit.get("notes") or ""),
            }
        )

    result = {
        "schema": MIDI_AB_RESULT_SCHEMA,
        "operation": "midi-ab-review-resolve",
        "status": "complete",
        "blind_review": True,
        "package_commitment": review.get("package_commitment"),
        "review": {"path": str(review_file), "sha256": _sha256(review_file)},
        "package": {"path": str(package), "seed_sha256": _sha256(seed_path)},
        "answer_key": {"path": str(answer_path), "sha256": _sha256(answer_path)},
        "summary": {
            "unit_count": len(resolved_units),
            "input_1_preferred_count": counts["input_1"],
            "input_2_preferred_count": counts["input_2"],
            "equivalent_count": counts["equivalent"],
            "neither_count": counts["neither"],
            "cannot_tell_count": counts["cannot_tell"],
        },
        "units": resolved_units,
        "promotion_allowed": False,
        "default_changed": False,
        "effects": _zero_effects(),
        "interpretation": (
            "Resolved listening evidence only. The result does not edit either "
            "MIDI, select a project candidate, promote a preset or change a default."
        ),
    }
    _write_json_atomic(output, result)
    return result


def _validated_intervals(
    intervals: Sequence[tuple[float, float, str]], source_duration: float
) -> list[tuple[float, float, str]]:
    if isinstance(intervals, (str, bytes)) or not intervals:
        raise ValueError("MIDI A/B review needs at least one interval")
    result = []
    for index, interval in enumerate(intervals, start=1):
        if not isinstance(interval, (tuple, list)) or len(interval) != 3:
            raise ValueError(f"MIDI A/B interval {index} must be start, end, focus")
        start = _nonnegative_finite(interval[0], f"interval {index} start")
        end = _positive_finite(interval[1], f"interval {index} end")
        focus = interval[2]
        if not isinstance(focus, str) or not focus.strip():
            raise ValueError(f"MIDI A/B interval {index} focus must not be empty")
        duration = end - start
        if duration < _MIN_INTERVAL_SECONDS or duration > _MAX_INTERVAL_SECONDS:
            raise ValueError(
                f"MIDI A/B interval {index} duration must be from "
                f"{_MIN_INTERVAL_SECONDS:g} to {_MAX_INTERVAL_SECONDS:g} seconds"
            )
        if end > source_duration + 1e-9:
            raise ValueError(f"MIDI A/B interval {index} extends beyond the source")
        result.append((start, end, focus.strip()))
    result.sort(key=lambda row: (row[0], row[1], row[2]))
    for previous, current in zip(result, result[1:]):
        if current[0] < previous[1]:
            raise ValueError("MIDI A/B review intervals must not overlap")
    return result


def _write_neutral_proxy(
    source: Path,
    output: Path,
    *,
    bpm: float,
    program: int,
) -> dict[str, Any]:
    clips = read_midi_clips(source)
    if not clips:
        raise ValueError(f"MIDI A/B input contains no playable notes: {source}")
    if len(clips) > len(_MELODIC_CHANNELS):
        raise ValueError("MIDI A/B v1 supports at most 15 note-bearing layers")
    tracks = []
    source_notes = []
    for index, clip in enumerate(clips):
        notes = [
            NoteEvent(
                start=float(note.source_start_seconds),
                end=float(note.source_end_seconds),
                pitch=int(note.pitch),
                velocity=int(note.velocity),
            )
            for note in clip.notes
        ]
        source_notes.extend(notes)
        tracks.append(
            MidiTrack(
                f"Neutral layer {index + 1}",
                _MELODIC_CHANNELS[index],
                program,
                notes,
            )
        )
    write_midi_file(output, tracks, bpm=bpm)
    proxy_notes = [
        NoteEvent(
            start=float(note.source_start_seconds),
            end=float(note.source_end_seconds),
            pitch=int(note.pitch),
            velocity=int(note.velocity),
        )
        for clip in read_midi_clips(output)
        for note in clip.notes
    ]
    before = _note_signatures(source_notes)
    after = _note_signatures(proxy_notes)
    if len(before) != len(after):
        raise ValueError("Neutral MIDI proxy changed the note count")
    tick_seconds = 60.0 / bpm / 480.0
    maximum_start_error = 0.0
    maximum_end_error = 0.0
    for left, right in zip(before, after):
        if left[2:] != right[2:]:
            raise ValueError("Neutral MIDI proxy changed pitch or velocity")
        maximum_start_error = max(maximum_start_error, abs(left[0] - right[0]))
        maximum_end_error = max(maximum_end_error, abs(left[1] - right[1]))
    if (
        maximum_start_error > tick_seconds + 1e-9
        or maximum_end_error > tick_seconds + 1e-9
    ):
        raise ValueError("Neutral MIDI proxy changed note timing beyond one tick")
    return {
        "policy": "same-program-distinct-melodic-channels-v1",
        "source_note_count": len(before),
        "proxy_note_count": len(after),
        "pitch_velocity_preserved": True,
        "maximum_start_error_seconds": round(maximum_start_error, 9),
        "maximum_end_error_seconds": round(maximum_end_error, 9),
        "one_tick_seconds": round(tick_seconds, 9),
        "original_midi_mutated": False,
    }


def _note_signatures(notes: Sequence[NoteEvent]) -> list[tuple[float, float, int, int]]:
    return sorted(
        (
            float(note.start),
            float(note.end),
            int(note.pitch),
            int(note.velocity),
        )
        for note in notes
    )


def _pairwise_level_match(
    values: Mapping[str, np.ndarray],
    *,
    minimum_rms_dbfs: float,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    if set(values) != {"input_1", "input_2"}:
        raise ValueError("MIDI A/B level matching requires exactly two inputs")
    rms = {name: _rms(audio) for name, audio in values.items()}
    if any(
        not math.isfinite(level) or _dbfs(level) < minimum_rms_dbfs
        for level in rms.values()
    ):
        raise ValueError(
            "MIDI A/B candidate render is silent, non-finite or below the "
            f"{minimum_rms_dbfs:g} dBFS review floor"
        )
    peaks = {name: float(np.max(np.abs(audio))) for name, audio in values.items()}
    if any(
        not math.isfinite(peak) or peak >= _FULL_SCALE_GUARD for peak in peaks.values()
    ):
        raise ValueError("MIDI A/B raw render is clipped or non-finite")
    target = min(rms.values())
    scales = {name: target / level for name, level in rms.items()}
    attenuation = {
        name: 20.0 * math.log10(scale) if scale > 0 else -math.inf
        for name, scale in scales.items()
    }
    if any(value < -_MAX_PAIR_ATTENUATION_DB for value in attenuation.values()):
        raise ValueError("MIDI A/B candidates differ by more than 18 dB")
    matched = {
        name: np.asarray(audio * scales[name], dtype=np.float64)
        for name, audio in values.items()
    }
    after = {name: _rms(audio) for name, audio in matched.items()}
    mismatch = abs(_dbfs(after["input_1"]) - _dbfs(after["input_2"]))
    if mismatch > 1e-7:
        raise RuntimeError("MIDI A/B in-memory RMS matching failed")
    return matched, {
        "method": "pairwise-fixed-window-rms-attenuation-only-v1",
        "target_rms": round(target, 12),
        "minimum_candidate_rms_dbfs": minimum_rms_dbfs,
        "maximum_allowed_mismatch_db": _MAX_RMS_MISMATCH_DB,
        "limiter_used": False,
        "inputs": {
            name: {
                "rms_before": round(rms[name], 12),
                "rms_before_dbfs": round(_dbfs(rms[name]), 6),
                "sample_peak_before": round(peaks[name], 12),
                "sample_peak_before_dbfs": round(_dbfs(peaks[name]), 6),
                "linear_scale": round(scales[name], 12),
                "gain_db": round(attenuation[name], 6),
                "rms_after": round(after[name], 12),
                "rms_after_dbfs": round(_dbfs(after[name]), 6),
            }
            for name in ("input_1", "input_2")
        },
    }


def _audio_record(
    path: Path,
    root: Path,
    *,
    expected_frames: int,
    expected_rate: int,
) -> dict[str, Any]:
    audio, sample_rate = soundfile.read(path, dtype="float64", always_2d=True)
    if int(sample_rate) != expected_rate or len(audio) != expected_frames:
        raise RuntimeError("MIDI A/B final audio geometry changed")
    if not np.all(np.isfinite(audio)):
        raise RuntimeError("MIDI A/B final audio contains non-finite samples")
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    rms = _rms(audio)
    if peak >= _FULL_SCALE_GUARD:
        raise RuntimeError("MIDI A/B final audio is clipped")
    return {
        "audio": str(path.relative_to(root)),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "sample_rate": int(sample_rate),
        "channels": int(audio.shape[1]),
        "frames": int(len(audio)),
        "rms_dbfs": round(_dbfs(rms), 6),
        "peak_dbfs": round(_dbfs(peak), 6),
    }


def _verify_review_audio(review: Mapping[str, Any], package: Path) -> None:
    evidence = review.get("review_evidence") or {}
    manifest_path = _package_file(package, evidence.get("manifest"), "audio manifest")
    if not manifest_path.is_file() or _sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError("MIDI A/B audio manifest changed or is missing")
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != MIDI_AB_AUDIO_MANIFEST_SCHEMA or manifest.get(
        "package_commitment"
    ) != review.get("package_commitment"):
        raise ValueError("MIDI A/B audio manifest is incompatible")
    files = list(manifest.get("files") or [])
    if len(files) != int(evidence.get("audio_file_count", -1)) or len(files) != int(
        manifest.get("file_count", -1)
    ):
        raise ValueError("MIDI A/B audio manifest count differs")
    rows = {str(row.get("path")): row for row in files}
    if len(rows) != len(files):
        raise ValueError("MIDI A/B audio manifest contains duplicate paths")
    referenced = set()
    for unit in review.get("units", []):
        for name in ("source", "candidate_a", "candidate_b"):
            record = unit.get(name) or {}
            relative = str(record.get("audio", ""))
            row = rows.get(relative)
            path = _package_file(package, relative, "review audio")
            if (
                row is None
                or not path.is_file()
                or _sha256(path) != row.get("sha256")
                or record.get("sha256") != row.get("sha256")
            ):
                raise ValueError(f"MIDI A/B review audio changed: {path}")
            referenced.add(relative)
    if referenced != set(rows):
        raise ValueError("MIDI A/B review audio references differ from its manifest")


def _immutable_review_unit(unit: Mapping[str, Any]) -> dict[str, Any]:
    immutable = _json_copy(unit)
    immutable.pop("heard", None)
    immutable.pop("choice", None)
    immutable.pop("notes", None)
    return immutable


def _immutable_review_document(document: Mapping[str, Any]) -> dict[str, Any]:
    immutable = _json_copy(document)
    immutable["status"] = "unreviewed"
    summary = immutable.get("summary")
    if isinstance(summary, dict):
        summary["reviewed_unit_count"] = 0
    units = immutable.get("units")
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict):
                unit["heard"] = {
                    "source": False,
                    "candidate_a": False,
                    "candidate_b": False,
                }
                unit["choice"] = None
                unit["notes"] = ""
    return immutable


def _browser_json_equal(reviewed: Any, seed: Any) -> bool:
    """Compare reviewed JSON with its seed after browser number serialisation.

    JavaScript has one numeric type and serialises integer-valued JSON floats such
    as ``0.0`` as ``0``.  Accept only that directional representation change;
    in particular, booleans must not compare equal to integers as they normally
    do in Python.
    """

    if isinstance(reviewed, Mapping) or isinstance(seed, Mapping):
        if not isinstance(reviewed, Mapping) or not isinstance(seed, Mapping):
            return False
        if set(reviewed) != set(seed):
            return False
        return all(
            _browser_json_equal(reviewed[key], seed[key]) for key in reviewed
        )
    if isinstance(reviewed, list) or isinstance(seed, list):
        if not isinstance(reviewed, list) or not isinstance(seed, list):
            return False
        return len(reviewed) == len(seed) and all(
            _browser_json_equal(reviewed_item, seed_item)
            for reviewed_item, seed_item in zip(reviewed, seed)
        )
    if isinstance(reviewed, bool) or isinstance(seed, bool):
        return (
            type(reviewed) is bool and type(seed) is bool and reviewed is seed
        )
    if isinstance(reviewed, (int, float)) or isinstance(seed, (int, float)):
        if not isinstance(reviewed, (int, float)) or not isinstance(
            seed, (int, float)
        ):
            return False
        if not math.isfinite(float(reviewed)) or not math.isfinite(float(seed)):
            return False
        if type(reviewed) is type(seed):
            return reviewed == seed
        if isinstance(reviewed, int) and isinstance(seed, float):
            return seed.is_integer() and reviewed == int(seed)
        return False
    return type(reviewed) is type(seed) and reviewed == seed


def _verify_package_contract(
    answer: Mapping[str, Any],
    seed: Mapping[str, Any],
) -> None:
    contract = answer.get("package_contract")
    commitment = seed.get("package_commitment")
    if (
        not isinstance(contract, Mapping)
        or not isinstance(commitment, str)
        or _document_hash(contract) != commitment
        or answer.get("package_commitment") != commitment
    ):
        raise ValueError("MIDI A/B package commitment is invalid")
    source = answer.get("source")
    inputs = {
        str(row.get("identity")): row
        for row in answer.get("inputs", [])
        if isinstance(row, Mapping)
    }
    if (
        not isinstance(source, Mapping)
        or source.get("sha256") != contract.get("source_sha256")
        or (seed.get("source") or {}).get("sha256") != contract.get("source_sha256")
        or (inputs.get("input_1") or {}).get("midi", {}).get("sha256")
        != contract.get("first_midi_sha256")
        or (inputs.get("input_2") or {}).get("midi", {}).get("sha256")
        != contract.get("second_midi_sha256")
        or seed.get("render_contract") != contract.get("render_contract")
        or seed.get("alignment_contract") != contract.get("alignment_contract")
    ):
        raise ValueError("MIDI A/B package evidence differs from its commitment")
    public_intervals = [
        {
            "start_seconds": unit.get("start_seconds"),
            "end_seconds": unit.get("end_seconds"),
            "listening_focus": unit.get("listening_focus"),
        }
        for unit in seed.get("units", [])
        if isinstance(unit, Mapping)
    ]
    if public_intervals != contract.get("intervals"):
        raise ValueError("MIDI A/B intervals differ from the package commitment")


def _verify_blind_assignments(
    answer: Mapping[str, Any],
    seed: Mapping[str, Any],
    units: Sequence[Mapping[str, Any]],
) -> None:
    try:
        nonce = bytes.fromhex(str(answer.get("blind_nonce_hex", "")))
        commitment_bytes = bytes.fromhex(str(seed.get("package_commitment", "")))
    except ValueError as exc:
        raise ValueError("MIDI A/B blind nonce evidence is invalid") from exc
    if len(nonce) != 32 or len(commitment_bytes) != 32:
        raise ValueError("MIDI A/B blind nonce evidence is invalid")
    nonce_commitment = hashlib.sha256(nonce + commitment_bytes).hexdigest()
    public_blind = seed.get("blind_assignment") or {}
    if (
        answer.get("mapping_policy") != "secret-random-per-unit-v1"
        or answer.get("blind_nonce_commitment") != nonce_commitment
        or public_blind.get("policy") != "secret-random-per-unit-v1"
        or public_blind.get("nonce_commitment") != nonce_commitment
    ):
        raise ValueError("MIDI A/B blind assignment commitment is invalid")
    answer_units = {
        str(unit.get("unit_id")): unit
        for unit in answer.get("units", [])
        if isinstance(unit, Mapping)
    }
    seed_units = {
        str(unit.get("unit_id")): unit
        for unit in seed.get("units", [])
        if isinstance(unit, Mapping)
    }
    if set(seed_units) != {str(unit.get("unit_id")) for unit in units}:
        raise ValueError("MIDI A/B package seed units do not match the review")
    package_commitment = str(seed["package_commitment"])
    for unit in units:
        unit_id = str(unit.get("unit_id"))
        key = answer_units.get(unit_id) or {}
        expected = _blind_mapping(nonce, package_commitment, unit_id)
        if any(key.get(name) != identity for name, identity in expected.items()):
            raise ValueError(f"MIDI A/B answer mapping is invalid for {unit_id}")
        if key.get("immutable_review_unit_sha256") != _document_hash(
            _immutable_review_unit(seed_units[unit_id])
        ):
            raise ValueError(f"MIDI A/B immutable review unit changed: {unit_id}")


def _verify_private_inputs(answer: Mapping[str, Any]) -> None:
    source = answer.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("MIDI A/B answer key has no source evidence")
    _verify_file_record(source, "source audio")
    inputs = list(answer.get("inputs") or [])
    if len(inputs) != 2 or {
        row.get("identity") for row in inputs if isinstance(row, Mapping)
    } != {"input_1", "input_2"}:
        raise ValueError("MIDI A/B answer key input identities are invalid")
    for row in inputs:
        if not isinstance(row, Mapping) or not isinstance(row.get("midi"), Mapping):
            raise ValueError("MIDI A/B answer key input evidence is invalid")
        _verify_file_record(row["midi"], f"{row.get('identity')} MIDI")


def _package_file(package: Path, value: Any, label: str) -> Path:
    relative = Path(str(value or ""))
    if relative.is_absolute() or not relative.parts:
        raise ValueError(f"MIDI A/B {label} path must be package-relative")
    resolved = (package / relative).resolve()
    if resolved == package or package not in resolved.parents:
        raise ValueError(f"MIDI A/B {label} path leaves the package")
    return resolved


def _blind_mapping(
    nonce: bytes,
    commitment: str,
    unit_id: str,
) -> dict[str, str]:
    decision = hashlib.sha256(
        nonce + bytes.fromhex(commitment) + unit_id.encode("utf-8")
    ).digest()[0]
    if decision % 2:
        return {"candidate_a": "input_2", "candidate_b": "input_1"}
    return {"candidate_a": "input_1", "candidate_b": "input_2"}


def _renderer_record(path: Path) -> dict[str, Any]:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"FluidSynth executable is unavailable: {path}")
    try:
        result = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"FluidSynth version check failed: {exc}") from exc
    if result.returncode != 0:
        raise ValueError("FluidSynth version check failed")
    lines = [
        line.strip()
        for line in (result.stdout + result.stderr).splitlines()
        if line.strip()
    ]
    return {
        **_without_path(_file_record(path)),
        "name": path.name,
        "version": lines[0] if lines else "unreported",
    }


def _fit_frames(audio: np.ndarray, frames: int) -> np.ndarray:
    if len(audio) < frames:
        return np.pad(audio, ((0, frames - len(audio)), (0, 0)))
    return np.asarray(audio[:frames], dtype=np.float64)


def _write_pcm24(path: Path, values: np.ndarray, sample_rate: int) -> None:
    soundfile.write(path, values, sample_rate, subtype="PCM_24")


def _rms(values: np.ndarray) -> float:
    return math.sqrt(float(np.mean(np.square(np.asarray(values, dtype=np.float64)))))


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _without_path(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in record.items() if key != "path"}


def _verify_file_record(record: Mapping[str, Any], label: str) -> None:
    path = Path(str(record.get("path", ""))).expanduser().resolve()
    if (
        not path.is_file()
        or path.stat().st_size != record.get("bytes")
        or _sha256(path) != record.get("sha256")
    ):
        raise ValueError(f"MIDI A/B {label} changed or is missing")


def _verify_unchanged(path: Path, record: Mapping[str, Any], *, label: str) -> None:
    if path.stat().st_size != record.get("bytes") or _sha256(path) != record.get(
        "sha256"
    ):
        raise ValueError(f"MIDI A/B {label} changed during the build")


def _zero_effects() -> dict[str, Any]:
    return {
        "source_audio_mutated": False,
        "source_midis_mutated": 0,
        "midi_notes_changed": 0,
        "review_choices_inferred": 0,
        "selection_changed": False,
        "promotion_allowed": False,
        "default_changed": False,
    }


def _review_html(seed: Mapping[str, Any]) -> str:
    payload = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend blind MIDI A/B review</title>
<style>
body{{font-family:system-ui,sans-serif;background:#101820;color:#edf4f8;margin:0;padding:2rem;line-height:1.45}}main{{max-width:1050px;margin:auto}}.card,.intro{{background:#192631;border:1px solid #405565;border-radius:16px;padding:1.3rem;margin:1rem 0}}.players{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}}audio{{width:100%}}label{{display:block;margin:.5rem 0}}button{{font-size:1rem;padding:.7rem 1rem;margin:.3rem;border-radius:9px;border:0;background:#2d638c;color:white}}textarea{{width:100%;min-height:4rem;background:#0e1720;color:white;border:1px solid #60798c;border-radius:8px}}.status{{color:#ffd166;font-size:1.2rem}}.warning{{border-left:4px solid #ffd166;padding:.7rem;background:#2a261a}}code{{color:#8fd3ff}}</style>
</head><body><main><h1>Sunofriend blind MIDI A/B review</h1>
<section class="intro"><p><b>{_html(seed["question"])}</b></p><p>Each source, A and B file is cut from the same source-time window. A and B use the same dry renderer, SoundFont and GM program. Only A/B are fixed-window sample-RMS matched; the source remains an unlevelled reference.</p><p class="warning">Judge recognisable notes, timing, pitch, useful detail and distracting clutter—not loudness alone. Sample RMS is not LUFS or true peak. Equivalent, neither and cannot tell are valid.</p><p>Candidate identity is in a separate answer key. Do not open it before exporting the review.</p></section>
<p class="status" id="status">Reviewed 0 of {len(seed["units"])} loops</p><div id="units"></div>
<button id="mark">Mark all choices reviewed</button><button id="export">Export reviewed JSON</button>
<script>
const review={payload};const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const root=document.getElementById('units');const playheads={{}};let current=null;
function switchTo(audio,unit){{document.querySelectorAll('audio').forEach(a=>a.pause());const playhead=playheads[unit]||0;audio.currentTime=Math.min(playhead,Math.max(0,(audio.duration||0)-0.01));current=audio;audio.play();}}
review.units.forEach((u,i)=>{{const card=document.createElement('section');card.className='card';card.dataset.i=i;card.innerHTML=`<h2>Loop ${{i+1}} · ${{u.start_seconds.toFixed(2)}}–${{u.end_seconds.toFixed(2)}} s</h2><p><b>Listen for:</b> ${{esc(u.listening_focus)}}</p><div class="players">${{[['source','Source reference'],['candidate_a','Candidate A'],['candidate_b','Candidate B']].map(([key,label])=>`<div><b>${{label}}</b><audio id="audio-${{i}}-${{key}}" data-unit="${{i}}" controls loop preload="metadata" src="${{esc(u[key].audio)}}"></audio><label><input type="checkbox" data-heard="${{key}}"> I heard ${{label}}</label></div>`).join('')}}</div><div>${{[['source','Source'],['candidate_a','A'],['candidate_b','B']].map(([key,label])=>`<button type="button" data-unit="${{i}}" data-switch="audio-${{i}}-${{key}}">Play ${{label}} from same point</button>`).join('')}}</div><h3>Which is more musically useful?</h3>${{[['candidate_a','Candidate A'],['candidate_b','Candidate B'],['equivalent','Equivalent / no clear preference'],['neither','Neither is useful'],['cannot_tell','I cannot tell']].map(([value,label])=>`<label><input type="radio" name="choice-${{i}}" value="${{value}}"> ${{label}}</label>`).join('')}}<label>Optional private listening note<textarea></textarea></label>`;root.appendChild(card);}});
document.querySelectorAll('audio').forEach(audio=>{{const unit=audio.dataset.unit;audio.onplay=()=>{{if(current&&current!==audio)current.pause();current=audio;playheads[unit]=audio.currentTime}};audio.ontimeupdate=()=>{{if(current===audio)playheads[unit]=audio.currentTime}};audio.onended=()=>{{playheads[unit]=0;if(current===audio)current=null}}}});document.querySelectorAll('[data-switch]').forEach(button=>button.onclick=()=>switchTo(document.getElementById(button.dataset.switch),button.dataset.unit));
function complete(){{return review.units.every(u=>u.choice&&Object.values(u.heard).every(Boolean))}}function sync(){{review.units.forEach((u,i)=>{{const card=root.querySelector(`[data-i="${{i}}"]`),choice=card.querySelector('input[type=radio]:checked');u.choice=choice?choice.value:null;u.notes=card.querySelector('textarea').value;for(const key of ['source','candidate_a','candidate_b'])u.heard[key]=card.querySelector(`[data-heard="${{key}}"]`).checked;}});review.summary.reviewed_unit_count=review.units.filter(u=>u.choice).length;if(!complete())review.status='unreviewed';document.getElementById('status').textContent=review.status==='reviewed'?`Reviewed all ${{review.summary.unit_count}} loops`:`Reviewed ${{review.summary.reviewed_unit_count}} of ${{review.summary.unit_count}} loops`;}}
root.addEventListener('change',sync);root.addEventListener('input',sync);document.getElementById('mark').onclick=()=>{{sync();if(!complete()){{alert('Hear source, A and B and choose one outcome for every loop.');return}}review.status='reviewed';document.getElementById('status').textContent=`Reviewed all ${{review.summary.unit_count}} loops`;}};document.getElementById('export').onclick=()=>{{sync();if(review.status!=='reviewed'||!complete()){{alert('Mark all choices reviewed before exporting.');return}}const blob=new Blob([JSON.stringify(review,null,2)+String.fromCharCode(10)],{{type:'application/json'}}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='midi_ab_review.reviewed.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}};
</script></main></body></html>"""


def _html(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise FileExistsError(f"MIDI A/B result already exists: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read MIDI A/B JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"MIDI A/B JSON must be an object: {path}")
    return value


def _document_hash(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"MIDI A/B {label} does not exist: {path}")


def _positive_finite(value: Any, label: str) -> float:
    number = _nonnegative_finite(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _nonnegative_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite and nonnegative")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


def _midi_value(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 127:
        raise ValueError(f"{label} must be an integer from 0 to 127")
    return value


__all__ = [
    "MIDI_AB_ANSWER_KEY_SCHEMA",
    "MIDI_AB_RESULT_SCHEMA",
    "MIDI_AB_REVIEW_SCHEMA",
    "create_midi_ab_review",
    "resolve_midi_ab_review",
]
